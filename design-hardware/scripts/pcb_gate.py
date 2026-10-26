#!/usr/bin/env python3
"""Offline PCB acceptance gate (PG1..PG8).

This tool reads already-captured evidence.  It never talks to EDA, never opens a
project and never writes anything except its own report.  It exists so a PCB
delivery cannot be declared "done" from a README table: every stage either has a
machine-checked proof, is honestly ``blocked``/``not_run``, or fails.

Contract: ``docs/round10/interface-contract.md`` section 4.

Exit codes:
  0  pass / pass_with_gaps
  1  fail / blocked
  2  argument, IO or evidence-schema error

The gate deliberately reuses ``pcb_evidence`` parsers and the
``design_engine.pcb_workflow`` diff/placement formats instead of re-implementing
them.  It does not import the old ``gate_check`` design-state schema.
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import os
import struct
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcb_cli import load_json, sha256_file, utc_now, write_json  # noqa: E402
import pcb_evidence  # noqa: E402
from design_engine.pcb_workflow import diff_boards  # noqa: E402

try:  # keep Windows consoles from mangling non-ASCII case paths
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

REPORT_SCHEMA = 'design-engine-pcb-gate/v1'
PROFILES = ('full', 'regression')
STATUS_PASS = 'pass'
STATUS_PASS_WITH_GAPS = 'pass_with_gaps'
STATUS_FAIL = 'fail'
STATUS_BLOCKED = 'blocked'
STATUS_NOT_RUN = 'not_run'

EXIT_CODES = {
    STATUS_PASS: 0,
    STATUS_PASS_WITH_GAPS: 0,
    STATUS_FAIL: 1,
    STATUS_BLOCKED: 1,
}

STAGE_IDS = (
    'PG1_placement',
    'PG2_layout',
    'PG3_drc',
    'PG4_check',
    'PG5_netpath',
    'PG6_sch_pcb',
    'PG7_save_reload',
    'PG8_delivery',
)

STAGE_TITLES = {
    'PG1_placement': 'Placement constraints / measured placement check',
    'PG2_layout': 'Layout lint quality',
    'PG3_drc': 'Native PCB DRC',
    'PG4_check': 'PCB check errors + WARN dispositions',
    'PG5_netpath': 'Key-net continuity (net-path)',
    'PG6_sch_pcb': 'SCH-PCB component/pin reconciliation',
    'PG7_save_reload': 'Save -> reload -> fresh dump persistence',
    'PG8_delivery': 'Delivery artifacts (images/BOM/archive)',
}

# Stages that are mandatory in the regression profile.  PG1/PG2 are optional
# there (run only when their evidence exists); PG4/PG5 are full-only by
# contract and are reported as not_run.
REGRESSION_REQUIRED = {'PG3_drc', 'PG6_sch_pcb', 'PG7_save_reload', 'PG8_delivery'}

# Roles discovered from the case evidence directory.  ``--file ROLE=PATH`` (or
# ``--role ROLE=PATH``) and the dedicated options override any role.
ROLE_PATTERNS = {
    'constraints': ('constraints*.json', 'pcb-constraints*.json'),
    'placement': ('placement-check*.json', 'pcb-placement-check*.json',
                  'placement-apply-report*.json'),
    'plan': ('placement-plan*.json', 'pcb-placement-plan*.json'),
    'intent': ('pcb-intent*.json', 'intent*.json'),
    'lint': ('pcb-layout-lint*.json', 'pcb_layout_lint*.json', '*layout*lint*.json'),
    'drc': ('pcb-drc*.json', 'pcb_drc*.json', '*pcb*drc*.json'),
    'check': ('pcb-check*.json', 'pcb_check*.json', '*pcb*check*.json'),
    'netpath': ('netpath*connections*.json', 'net-path*.json', 'net_path*.json',
                '*netpath*.json'),
    'sch_pcb': ('sch-pcb-compare*.json', 'sch_pcb_compare*.json',
                '*sch*pcb*compare*.json'),
    'sch': ('sch-connectivity*.json', 'sch-read*.json', 'sch_read*.json'),
    'save_reload': ('save-reload-diff*.json', '*reload*diff*.json',
                    'save_reload*.json'),
    'warn_disposition': ('warn-disposition*.json', 'pcb-warn-disposition*.json'),
    'plan_base_dump': ('pcb-dump-plan-base*.json', '*plan*base*dump*.json'),
    'dump_before': ('pcb-dump-final*.json', 'pcb-dump-before*.json',
                    '*dump*before*.json'),
    'dump_after': ('pcb-dump-after-reload*.json', 'pcb-dump-after*.json',
                   '*after*reload*.json'),
    'image_top': ('pcb-final-top*.png', '*top*.png'),
    'image_bottom': ('pcb-final-bottom*.png', '*bottom*.png'),
    'actual_svg': ('pcb-final-actual*.svg', '*actual*.svg', '*.svg'),
    'bom': ('BOM*.csv', 'bom*.csv'),
    'archive': ('*.epro2',),
}

ROLE_EXCLUDES = {
    'drc': ('drc-rules', 'drc_rules'),
    'check': ('drc-rules', 'drc_rules'),
    'dump_before': ('after',),
}

BINARY_ROLES = {'image_top', 'image_bottom', 'actual_svg', 'bom', 'archive'}

# Auxiliary evidence: a corrupt copy must not fail the whole gate, because the
# stage either does not consume it or can prove the same fact another way.
SOFT_PARSE_ROLES = {'intent', 'plan', 'sch', 'save_reload'}

# Archive/diff discovery must not silently pick a scratch/edit copy over the
# shipped artifact when both live in the same evidence directory.
SCRATCH_NAME_NOISE = ('edit', 'copy', 'backup', 'tmp', 'scratch')
NOISE_SENSITIVE_ROLES = {'archive', 'save_reload'}

NAMED_ROLE_OPTIONS = (
    ('dump_before', 'dump_before'),
    ('dump_after', 'dump_after'),
    ('constraints', 'constraints'),
    ('plan', 'plan'),
    ('intent', 'intent'),
    ('check', 'check'),
    ('drc', 'drc'),
    ('lint', 'lint'),
    ('netpath', 'netpath'),
    ('sch_pcb', 'sch_pcb'),
    ('sch', 'sch'),
    ('warn_disposition', 'warn_disposition'),
)

DELIVERY_ROLES = ('image_top', 'image_bottom', 'actual_svg', 'bom', 'archive')

ROLE_STAGE = {
    'constraints': 'PG1_placement', 'placement': 'PG1_placement',
    'plan': 'PG1_placement',
    'lint': 'PG2_layout',
    'drc': 'PG3_drc',
    'check': 'PG4_check', 'warn_disposition': 'PG4_check',
    'netpath': 'PG5_netpath',
    'sch': 'PG6_sch_pcb', 'sch_pcb': 'PG6_sch_pcb',
    'dump_before': 'PG7_save_reload', 'dump_after': 'PG7_save_reload',
    'plan_base_dump': 'PG1_placement',
    'save_reload': 'PG7_save_reload',
    'image_top': 'PG8_delivery', 'image_bottom': 'PG8_delivery',
    'actual_svg': 'PG8_delivery', 'bom': 'PG8_delivery',
    'archive': 'PG8_delivery',
}

BASELINE_ROLE_ALIASES = {
    'image_top': 'image_top',
    'pcb_image_top': 'image_top',
    'top_image': 'image_top',
    'top': 'image_top',
    'top_png': 'image_top',
    'pcb_top': 'image_top',
    'pcb_final_top': 'image_top',
    'final_top': 'image_top',
    'image_bottom': 'image_bottom',
    'pcb_image_bottom': 'image_bottom',
    'bottom_image': 'image_bottom',
    'bottom': 'image_bottom',
    'bottom_png': 'image_bottom',
    'pcb_bottom': 'image_bottom',
    'pcb_final_bottom': 'image_bottom',
    'final_bottom': 'image_bottom',
    'actual_svg': 'actual_svg',
    'pcb_actual_svg': 'actual_svg',
    'svg': 'actual_svg',
    'actual': 'actual_svg',
    'render_svg': 'actual_svg',
    'bom': 'bom',
    'bom_csv': 'bom',
    'archive': 'archive',
    'epro2': 'archive',
    'project_epro2': 'archive',
    'archive_epro2': 'archive',
    'project_archive': 'archive',
}


def canonical_baseline_role(role):
    raw_key = _text(role).lower().replace('-', '_').replace(' ', '_')
    key = raw_key
    for suffix in ('.png', '.svg', '.csv', '.json', '.epro2'):
        if key.endswith(suffix):
            key = key[:-len(suffix)]
            break
    if key in BASELINE_ROLE_ALIASES:
        return BASELINE_ROLE_ALIASES[key]
    for prefix in ('pcb_', 'pcb_final_', 'final_', 'board_'):
        if key.startswith(prefix):
            stripped = key[len(prefix):]
            if stripped in BASELINE_ROLE_ALIASES:
                return BASELINE_ROLE_ALIASES[stripped]
    # Last resort for file-name-like roles (e.g. "photo-led-pcb-final.epro2").
    if 'archive' in raw_key or 'epro2' in raw_key:
        return 'archive'
    if 'bom' in raw_key:
        return 'bom'
    if 'svg' in raw_key:
        return 'actual_svg'
    if 'bottom' in raw_key:
        return 'image_bottom'
    if 'top' in raw_key:
        return 'image_top'
    return None

PLACEMENT_SCHEMA = 'design-engine-pcb-placement/v1'
CONSTRAINTS_SCHEMA = 'design-engine-pcb-constraints/v1'

LAYOUT_MIN_SCORE = 60
LAYOUT_MAX_CROSSINGS = 8


class InputError(Exception):
    """Bad CLI input or an explicitly named evidence file that cannot be read."""


# ---------------------------------------------------------------------------
# small helpers


def _text(value):
    if value is None:
        return ''
    return str(value).strip()


def _int(value, default=0):
    try:
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _unwrap(payload):
    """Return ``payload.result`` when it is the CLI envelope, else the payload."""
    if isinstance(payload, dict):
        result = payload.get('result')
        if isinstance(result, dict):
            return result
    return payload if isinstance(payload, dict) else {}


def _unwrap_or_value(value):
    """Unwrap a CLI envelope while preserving list payloads."""
    if isinstance(value, dict):
        result = value.get('result')
        if isinstance(result, (dict, list)):
            return result
    return value


def _parse_time(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # Windows/CLI captures may carry more than six fractional-second digits;
    # truncate so older Python versions can parse them.
    if '.' in text:
        head, _, tail = text.partition('.')
        digits = ''
        rest = ''
        for index, char in enumerate(tail):
            if char.isdigit():
                digits += char
            else:
                rest = tail[index:]
                break
        text = head + ('.' + digits[:6] if digits else '') + rest
    try:
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(moment):
    if moment is None:
        return None
    return moment.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _mtime(path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def _captured_time(payload):
    """Best-effort capture timestamp carried by an evidence payload."""
    if not isinstance(payload, dict):
        return None
    for key in ('capturedAt', 'captured_at', 'generated_at', 'created_at',
                'createdAt', 'savedAt', 'completedAt'):
        parsed = _parse_time(payload.get(key))
        if parsed:
            return parsed
    capture = payload.get('capture')
    if isinstance(capture, dict):
        for key in ('completedAt', 'capturedAt', 'startedAt'):
            parsed = _parse_time(capture.get(key))
            if parsed:
                return parsed
    nested = payload.get('result')
    if isinstance(nested, dict) and nested is not payload:
        return _captured_time(nested)
    return None


def _payload_identity(payload):
    """Extract the project/document identity an evidence payload carries.

    Returns a tuple or ``None``.  Only fields that are actually present are
    compared; an absent identity is never guessed from a filename.
    """
    if not isinstance(payload, dict):
        return None
    sources = [payload]
    for key in ('result', 'capture', 'source'):
        nested = payload.get(key)
        if isinstance(nested, dict):
            sources.append(nested)
    project = document = None
    for item in sources:
        for key in ('projectUuid', 'project_uuid', 'projectId', 'projectID'):
            value = _text(item.get(key))
            if value:
                project = value
                break
        for key in ('documentUuid', 'document_uuid', 'documentId',
                    'documentID', 'pageId'):
            value = _text(item.get(key))
            if value:
                document = value
                break
    if not project and not document:
        return None
    return (project or '', document or '')


def _dump_semantic(dump):
    if not isinstance(dump, dict):
        return None
    value = dump.get('semanticSha256')
    if not value:
        source = dump.get('source')
        if isinstance(source, dict):
            value = source.get('semantic_sha256')
    return _text(value) or None


def _dump_capture(dump, key):
    if not isinstance(dump, dict):
        return None
    capture = dump.get('capture')
    if isinstance(capture, dict) and capture.get(key):
        return _text(capture.get(key))
    source = dump.get('source')
    if isinstance(source, dict):
        mapped = {'projectUuid': 'project_uuid', 'projectName': 'project_name',
                  'documentUuid': 'document_uuid'}.get(key)
        if mapped and source.get(mapped):
            return _text(source.get(mapped))
    return None


def _dump_component_count(dump):
    if not isinstance(dump, dict):
        return None
    components = dump.get('components')
    return len(components) if isinstance(components, list) else None


def _finding(code, message, severity='hard', **extra):
    item = {'code': code, 'severity': severity, 'message': message}
    item.update(extra)
    return item


def _stage(stage_id, required, status, findings=None, evidence=None, metrics=None):
    return {
        'id': stage_id,
        'title': STAGE_TITLES[stage_id],
        'status': status,
        'required': bool(required),
        'findings': findings or [],
        'evidence': evidence or [],
        'metrics': metrics or {},
    }


def _stage_required(profile, stage_id):
    if profile == 'full':
        return True
    return stage_id in REGRESSION_REQUIRED


# ---------------------------------------------------------------------------
# evidence discovery


class Evidence:
    def __init__(self, role, path, payload=None, error=None, candidates=1,
                 selected_because='', alternatives=None, conflict=None,
                 manifest_entry=None, binding=None):
        self.role = role
        self.path = Path(path)
        self.payload = payload
        self.error = error
        self.candidates = candidates
        self.selected_because = selected_because
        self.alternatives = alternatives or []
        self.conflict = conflict
        self.manifest_entry = manifest_entry
        self.binding = binding or {}

    @property
    def usable(self):
        if self.error:
            return False
        if self.role in BINARY_ROLES:
            try:
                return self.path.is_file() and self.path.stat().st_size > 0
            except OSError:
                return False
        return self.payload is not None

    def meta(self):
        item = {
            'role': self.role,
            'path': str(self.path),
            'candidates': self.candidates,
            'selected_because': self.selected_because,
        }
        try:
            item['sha256'] = sha256_file(str(self.path))
            item['bytes'] = self.path.stat().st_size
            item['mtime'] = _iso(_mtime(self.path))
        except OSError as exc:
            item['error'] = 'unreadable: %s' % exc
        if self.payload is not None:
            try:
                item['semantic_sha256'] = pcb_evidence.semantic_sha256(
                    self.payload)
            except (TypeError, ValueError):
                item['semantic_sha256'] = None
        if self.error:
            item['error'] = self.error
        captured, basis = _evidence_time_with_basis(self)
        if captured:
            item['captured_at'] = _iso(captured)
            item['freshness_basis'] = basis
        if self.alternatives:
            item['alternatives'] = self.alternatives
        if self.conflict:
            item['conflict'] = self.conflict
        if self.manifest_entry:
            item['manifest'] = {
                'sha256': self.manifest_entry.get('sha256'),
                'source_dump_sha256': self.manifest_entry.get('source_dump_sha256'),
                'produced_at': self.manifest_entry.get('produced_at'),
                'source_binding': self.manifest_entry.get('source_binding'),
            }
        if self.binding:
            item['binding'] = dict(self.binding)
        return item


def _resolve_path(value, evidence_dir):
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if candidate.is_file():
        return candidate
    return Path(evidence_dir) / candidate


def _read_role_file(role, path):
    if role in BINARY_ROLES:
        try:
            if not path.is_file():
                return None, 'file missing'
        except OSError as exc:
            return None, 'unreadable: %s' % exc
        return None, None
    try:
        return load_json(str(path)), None
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return None, 'JSON parse failed: %s' % exc


def _shape_ok(role, payload):
    """Conservative shape check used to skip an unrelated newest candidate."""
    if role in BINARY_ROLES:
        return True
    if payload is None:
        return False
    if role in ('dump_before', 'dump_after'):
        if not isinstance(payload, dict):
            return False
        components = payload.get('components')
        if not isinstance(components, list):
            return False
        for component in components:
            if not isinstance(component, dict):
                return False
            pads = component.get('pads')
            if pads is not None and (not isinstance(pads, list) or
                                     any(not isinstance(pad, dict)
                                         for pad in pads)):
                return False
        return True
    if role == 'netpath' and isinstance(payload, list):
        return True
    if not isinstance(payload, dict):
        return False
    data = _unwrap(payload)
    if role == 'constraints':
        return isinstance(data.get('constraints'), list)
    if role == 'placement':
        return ('hard_ok' in data or isinstance(data.get('check'), dict) or
                data.get('schema') == PLACEMENT_SCHEMA)
    if role == 'plan':
        return isinstance(data.get('placements'), list)
    if role == 'intent':
        return isinstance(data.get('constraints'), list) or \
            isinstance(data.get('modules'), list)
    if role == 'lint':
        return ('score' in data or 'crossings' in data or
                isinstance(data.get('report'), dict))
    if role == 'drc':
        return any(key in data for key in ('passed', 'total', 'violations'))
    if role == 'check':
        return isinstance(data.get('findings'), list) or \
            isinstance(data.get('summary'), dict)
    if role == 'netpath':
        return isinstance(data.get('rows'), list)
    if role == 'sch_pcb':
        return any(key in data for key in ('status', 'mismatches', 'pins'))
    if role == 'sch':
        return isinstance(data.get('components'), list) or \
            isinstance(data.get('connections'), list)
    if role == 'save_reload':
        return 'status' in data and any(
            key in data for key in ('identity_changes', 'unrelated_changes', 'counts'))
    if role == 'warn_disposition':
        return isinstance(data.get('findings'), list)
    return True


def _sort_key(role, path):
    try:
        stamp = path.stat().st_mtime
    except OSError:
        stamp = 0.0
    name = path.name.lower()
    noisy = any(word in name for word in SCRATCH_NAME_NOISE)
    # An explicitly final artifact is the intended delivery evidence; a
    # scratch/edit copy or a non-final intermediate must not win only because
    # its mtime is newer.
    final = 'final' in name
    return (1 if noisy else 0, 0 if final else 1, -stamp)


def discover_role(role, evidence_dir, override=None, preferred=None,
                  manifest_entry=None, manifest_path=None):
    if override:
        path = _resolve_path(override, evidence_dir)
        if not path.is_file():
            raise InputError('%s evidence not found: %s' % (role, path))
        payload, error = _read_role_file(role, path)
        if error:
            raise InputError('%s evidence is not readable JSON (%s): %s' % (
                role, error, path))
        if role not in BINARY_ROLES and not _shape_ok(role, payload):
            raise InputError('%s evidence has an unexpected structure: %s' % (
                role, path))
        entry = manifest_entry
        if entry:
            declared = Path(entry.get('resolved_path') or '')
            try:
                same = declared.resolve() == path.resolve()
            except OSError:
                same = str(declared) == str(path)
            if not same:
                # An explicit override is a different artifact; do not bind it
                # to the manifest's hashes/timestamp for another file.
                entry = None
        return Evidence(role, path, payload, None, 1, 'explicit override',
                        manifest_entry=entry,
                        binding={'basis': 'explicit_override'})

    paths = []
    for pattern in ROLE_PATTERNS.get(role, ()):
        for path in Path(evidence_dir).glob(pattern):
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            name = path.name.lower()
            if any(needle in name for needle in ROLE_EXCLUDES.get(role, ())):
                continue
            paths.append(path)

    unique, seen = [], set()
    for path in paths:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    unique.sort(key=lambda item: _sort_key(role, item))

    parsed = []
    for path in unique:
        payload, error = _read_role_file(role, path)
        parsed.append((path, payload, error))
    compatible = [(path, payload) for path, payload, error in parsed
                  if error is None and _shape_ok(role, payload)]
    chosen = None
    if preferred:
        preferred_path = Path(preferred)
        if preferred_path.is_file():
            payload, error = _read_role_file(role, preferred_path)
            if error:
                raise InputError('%s evidence declared by %s is unreadable (%s): %s'
                                 % (role, manifest_path or 'the case manifest',
                                    error, preferred_path))
            if role not in BINARY_ROLES and not _shape_ok(role, payload):
                raise InputError('%s evidence declared by %s has an unexpected '
                                 'structure: %s'
                                 % (role, manifest_path or 'the case manifest',
                                    preferred_path))
            return Evidence(
                role, preferred_path, payload, None, 1,
                'path declared by %s' % (manifest_path or 'the case manifest'),
                manifest_entry=manifest_entry,
                binding={'basis': 'manifest' if manifest_entry else 'discovery'})
        try:
            preferred_key = str(preferred_path.resolve())
        except OSError:
            preferred_key = str(preferred_path)
        for path, payload in compatible:
            try:
                path_key = str(path.resolve())
            except OSError:
                path_key = str(path)
            if path_key == preferred_key:
                chosen = (path, payload)
                break
        if chosen is None:
            # The manifest names this artifact but the file is missing or has
            # an incompatible shape.  Do not silently fall back to a sibling.
            raise InputError(
                '%s evidence declared by %s is missing or unreadable: %s'
                % (role, manifest_path or 'the case manifest', preferred))
    if chosen is None and compatible:
        chosen = compatible[0]
    if chosen is not None:
        path, payload = chosen
        alternatives = []
        for other_path, other_payload in compatible:
            if other_path == path:
                continue
            try:
                other_sha = sha256_file(str(other_path))
            except OSError:
                other_sha = None
            alternatives.append({'path': str(other_path), 'sha256': other_sha})
        conflict = None
        if compatible:
            try:
                selected_sha = sha256_file(str(path))
            except OSError:
                selected_sha = None
            differing = [item for item in alternatives
                         if item.get('sha256') != selected_sha]
            if differing:
                identities = {_payload_identity(payload)}
                for other_path, other_payload in compatible:
                    if other_path == path:
                        continue
                    identities.add(_payload_identity(other_payload))
                identities.discard(None)
                if len(identities) > 1:
                    conflict = {'kind': 'identity_conflict',
                                'identities': sorted(identities, key=str),
                                'selected': str(path),
                                'alternatives': [item['path'] for item in differing]}
                else:
                    conflict = {'kind': 'multiple_candidates',
                                'selected': str(path),
                                'alternatives': [item['path'] for item in differing]}
        return Evidence(
            role, path, payload, None, len(unique),
            ('path declared by %s' % (manifest_path or 'the case manifest')
             if preferred else
             'newest compatible match among %d candidate(s)' % len(unique)),
            alternatives=alternatives, conflict=conflict,
            manifest_entry=manifest_entry,
            binding={'basis': 'manifest' if manifest_entry else 'discovery'})
    parse_failures = [item for item in parsed if item[2] is not None]
    if parsed and len(parse_failures) == len(parsed) and \
            role not in SOFT_PARSE_ROLES:
        path, _, error = parsed[0]
        raise InputError(
            '%s evidence has no parseable JSON candidate (%s): %s'
            % (role, error, path))
    if parsed:
        path, payload, error = parsed[0]
        return Evidence(role, path, payload, error or 'unrecognised structure',
                        len(unique), 'newest candidate but no compatible parse')
    return None


def _infer_role_from_path(value):
    """Infer a single role for a bare ``--file PATH``/``--role PATH``."""
    name = os.path.basename(str(value)).lower()
    matches = []
    for role, patterns in ROLE_PATTERNS.items():
        if any(needle in name for needle in ROLE_EXCLUDES.get(role, ())):
            continue
        if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in patterns):
            matches.append(role)
    return matches


def collect_overrides(args):
    overrides = {}
    for item in list(getattr(args, 'file', None) or []) + \
            list(getattr(args, 'role', None) or []):
        if '=' not in item:
            matches = _infer_role_from_path(item)
            if len(matches) != 1:
                raise InputError(
                    '--file/--role needs ROLE=PATH (could not infer one role '
                    'from %r; candidates: %s)'
                    % (item, ', '.join(matches) or 'none'))
            overrides[matches[0]] = item.strip()
            continue
        role, value = item.split('=', 1)
        role = role.strip()
        if role not in ROLE_PATTERNS:
            raise InputError('unknown evidence role %r (known: %s)' % (
                role, ', '.join(sorted(ROLE_PATTERNS))))
        if not value.strip():
            raise InputError('--file/--role %s needs a path' % role)
        overrides[role] = value.strip()
    for attribute, role in NAMED_ROLE_OPTIONS:
        value = getattr(args, attribute, None)
        if value:
            overrides[role] = value
    return overrides


def _manifest_role(role):
    """Map a pcb_case manifest role to a gate evidence role."""
    key = _text(role).lower().replace('-', '_').replace(' ', '_')
    for suffix in ('.json', '.png', '.svg', '.csv', '.epro2'):
        if key.endswith(suffix):
            key = key[:-len(suffix)]
            break
    if 'dump' in key:
        if 'plan' in key and 'base' in key:
            return 'plan_base_dump'
        if 'after' in key:
            return 'dump_after'
        if 'before' in key:
            return 'dump_before'
        return 'dump_before'
    if 'warn' in key or 'disposition' in key:
        return 'warn_disposition'
    if 'netpath' in key or 'net_path' in key:
        return 'netpath'
    if 'sch' in key and 'pcb' in key and ('compare' in key or 'cross' in key):
        return 'sch_pcb'
    if key.startswith('sch') and ('read' in key or 'connectivity' in key):
        return 'sch'
    if 'drc' in key:
        return 'drc'
    if 'layout' in key and 'lint' in key:
        return 'lint'
    if 'check' in key and 'pcb' in key:
        return 'check'
    if 'constraint' in key:
        return 'constraints'
    if 'placement' in key:
        return 'placement'
    if 'plan' in key:
        return 'plan'
    if 'intent' in key:
        return 'intent'
    if 'save' in key and 'reload' in key:
        return 'save_reload'
    if 'bom' in key:
        return 'bom'
    if 'archive' in key or 'epro2' in key:
        return 'archive'
    if 'bottom' in key:
        return 'image_bottom'
    if 'top' in key:
        return 'image_top'
    if 'svg' in key or 'actual' in key:
        return 'actual_svg'
    return None


def load_case_manifest(case_dir):
    """Load a pcb_case manifest as evidence provenance, if one exists.

    A manifest is optional for backwards compatibility, but when present its
    artifact hashes and ``source_dump_sha256`` bindings win over filename
    discovery and file mtimes.
    """
    case_dir = Path(case_dir)
    for name in ('manifest.json', 'case-manifest.json',
                 'pcb-case-manifest.json'):
        path = case_dir / name
        if not path.is_file():
            continue
        try:
            data = load_json(str(path))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise InputError('case manifest is unreadable: %s (%s)' % (path, exc))
        if not isinstance(data, dict):
            raise InputError('case manifest must be a JSON object: %s' % path)
        schema = _text(data.get('schema'))
        if schema and not schema.startswith('design-engine-pcb-case'):
            raise InputError('unsupported case manifest schema %r: %s'
                             % (schema, path))
        artifacts = data.get('artifacts')
        if not isinstance(artifacts, list):
            raise InputError('case manifest artifacts must be a list: %s' % path)
        roles = {}
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            role = _manifest_role(item.get('role'))
            if not role or not _text(item.get('path')):
                continue
            entry = dict(item)
            raw_path = _text(item.get('path'))
            resolved = ((case_dir / raw_path).resolve()
                        if not os.path.isabs(raw_path)
                        else Path(raw_path).resolve())
            try:
                inside = resolved == case_dir.resolve() or \
                    resolved.is_relative_to(case_dir.resolve())
            except AttributeError:  # pragma: no cover - Python < 3.9
                inside = str(resolved).startswith(str(case_dir.resolve()))
            if not inside:
                raise InputError(
                    'case manifest artifact escapes the case directory: %s'
                    % raw_path)
            entry['resolved_path'] = str(resolved)
            roles.setdefault(role, []).append(entry)
        return {'path': str(path), 'schema': schema, 'artifacts': artifacts,
                'roles': roles, 'source': data.get('source') or {}}
    return None


def load_all_evidence(evidence_dir, overrides, images_dir, manifest=None,
                      case_dir=None):
    roles = {}
    manifest_roles = (manifest or {}).get('roles') or {}
    case_dir = Path(case_dir) if case_dir is not None else Path(evidence_dir)
    for role in ROLE_PATTERNS:
        directory = images_dir if role in ('image_top', 'image_bottom',
                                           'actual_svg') else evidence_dir
        entries = manifest_roles.get(role) or []
        entry = entries[0] if entries else None
        if len(entries) > 1:
            keys = {(item.get('resolved_path'), item.get('sha256'))
                    for item in entries}
            if len(keys) != 1:
                # Do not silently drop the manifest's hashes/timestamps and
                # fall back to a filename that happens to sort first.
                roles[role] = Evidence(
                    role, entries[0].get('resolved_path') or evidence_dir,
                    None,
                    error='case manifest declares %d different artifacts for '
                          'this role' % len(entries),
                    selected_because='ambiguous manifest role',
                    binding={'basis': 'manifest',
                             'error': 'manifest_role_ambiguous'})
                continue
            entry = entries[0]
        preferred = entry.get('resolved_path') if entry else None
        if preferred and not Path(preferred).is_file():
            # A stale manifest must not silently fall back to another file.
            roles[role] = Evidence(
                role, preferred, None,
                error='manifest artifact is missing: %s' % preferred,
                selected_because='declared by %s' % manifest.get('path'),
                manifest_entry=entry,
                binding={'basis': 'manifest', 'error': 'missing_artifact'})
            continue
        roles[role] = discover_role(
            role, directory, overrides.get(role), preferred=preferred,
            manifest_entry=entry,
            manifest_path=(manifest or {}).get('path') if entry else None)
    return roles


# ---------------------------------------------------------------------------
# freshness


def _evidence_time_with_basis(evidence):
    """Return ``(time, basis)``; a manifest timestamp outranks file mtime.

    A copied file with ``touch`` updates mtime but cannot change the manifest's
    ``produced_at`` or the artifact hash.  Payload capture time is the next
    strongest fact.  mtime is only an auxiliary signal and is labelled as
    such.
    """
    if evidence is None:
        return None, 'none'
    entry = evidence.manifest_entry or {}
    # pcb_case --skip-live fills produced_at from the file mtime and labels it
    # inferred_mtime.  That is not a recorded production time, so it must not
    # outrank the payload capture or allow a touched copy to look fresh.
    if entry.get('source_binding') != 'inferred_mtime':
        produced = _parse_time(entry.get('produced_at'))
        if produced:
            return produced, 'manifest_produced_at'
    captured = _captured_time(evidence.payload) if evidence.payload is not None else None
    if captured:
        return captured, 'payload_capture'
    return _mtime(evidence.path), 'file_mtime'


def _evidence_time(evidence):
    return _evidence_time_with_basis(evidence)[0]


def _payload_project(payload):
    identity = _payload_identity(payload)
    return identity[0] if identity else None


def _sha256_normalized(path):
    """Hash text evidence after CRLF->LF, matching a git checkout.

    ``pcb_case`` records the bytes of the working tree; a later git checkout on
    another platform can legitimately change only line endings.  Keep the raw
    hash as the primary identity and accept a declared hash that matches the
    normalized text, recording which basis was used.
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return hashlib.sha256(data).hexdigest()
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def _hash_matches(declared, path):
    """Return ``(matched, raw, normalized)`` for a declared artifact hash."""
    declared = _text(declared)
    try:
        raw = sha256_file(str(path))
    except OSError:
        return False, None, None
    normalized = _sha256_normalized(path)
    return (declared in (raw, normalized)), raw, normalized


def bind_manifest_evidence(roles, manifest, case_dir):
    """Attach manifest/hash/identity binding diagnostics to each evidence role.

    This is deliberately separate from parsing: a valid JSON file can still be
    the wrong object (another project, an old dump, or a copy with a touched
    mtime).  Any hard binding problem is later attached to the stage that uses
    the role.
    """
    final = _final_dump(roles)
    final_sha = None
    if final is not None and final.usable:
        try:
            final_sha = sha256_file(str(final.path))
        except OSError:
            final_sha = None
    final_identity = _payload_identity(final.payload) if final is not None else None
    final_project = final_identity[0] if final_identity else None
    final_document = final_identity[1] if final_identity else None
    for role, evidence in roles.items():
        if evidence is None:
            continue
        binding = dict(evidence.binding or {})
        entry = evidence.manifest_entry
        if entry:
            path = Path(entry.get('resolved_path') or evidence.path)
            declared = _text(entry.get('sha256'))
            matched, actual, normalized = _hash_matches(declared, path)
            binding['declared_sha256'] = declared or None
            binding['actual_sha256'] = actual
            binding['normalized_sha256'] = normalized
            if actual is not None:
                binding['hash_basis'] = ('raw' if declared == actual else
                                         ('crlf_normalized' if matched
                                          else 'mismatch'))
            if declared and actual and not matched:
                binding['error'] = 'manifest_sha256_mismatch'
            source_dump = _text(entry.get('source_dump_sha256'))
            checkable = role not in ('dump_before', 'dump_after',
                                     'plan_base_dump')
            if checkable and entry.get('run_after_final_reload') is False:
                checkable = False
            if checkable and source_dump and final_sha and \
                    not _hash_matches(source_dump, final.path)[0]:
                binding['error'] = 'source_dump_changed'
                binding['source_dump_sha256'] = source_dump
                binding['final_dump_sha256'] = final_sha
            if entry.get('source_binding'):
                binding['source_binding'] = entry.get('source_binding')
            if manifest.get('status') == 'failed' and \
                    entry.get('run_after_final_reload'):
                binding['error'] = 'manifest_status_failed'
            binding['manifest_status'] = manifest.get('status')
        identity = _payload_identity(evidence.payload) if evidence.payload else None
        project = identity[0] if identity else None
        document = identity[1] if identity else None
        if final_project and project and project != final_project:
            binding['error'] = 'project_identity_mismatch'
            binding['evidence_project'] = project
            binding['final_project'] = final_project
        elif role not in ('sch', 'sch_pcb') and final_document and document and \
                document != final_document:
            # A schematic page UUID is legitimately different from the PCB
            # document UUID; for PCB evidence a page/document mismatch is not.
            binding['error'] = 'document_identity_mismatch'
            binding['evidence_document'] = document
            binding['final_document'] = final_document
        evidence.binding = binding


def _final_dump(roles):
    after = roles.get('dump_after')
    if after is not None and after.usable:
        return after
    before = roles.get('dump_before')
    if before is not None and before.usable:
        return before
    return None


def _reference_dump(roles):
    """Dump a plan/reference hash is expected to describe (pre-apply first)."""
    plan_base = roles.get('plan_base_dump')
    if plan_base is not None and plan_base.usable:
        return plan_base
    before = roles.get('dump_before')
    if before is not None and before.usable:
        return before
    return _final_dump(roles)


def _check_freshness(evidence, final_evidence, stage_id, findings, not_checked,
                     label):
    """Return True when fresh, False when stale, None when unprovable."""
    if evidence is None or not evidence.usable:
        return None
    final_time = _evidence_time(final_evidence) if final_evidence is not None else None
    if final_time is None:
        not_checked.append({
            'stage': stage_id,
            'check': 'freshness_%s' % label,
            'reason': 'no readable final dump is available to bind %s' % label,
        })
        return None
    evidence_time, basis = _evidence_time_with_basis(evidence)
    if evidence_time is None:
        not_checked.append({
            'stage': stage_id,
            'check': 'freshness_%s' % label,
            'reason': 'no manifest timestamp, capture timestamp or mtime on %s'
                      % label,
        })
        return None
    if basis == 'file_mtime':
        not_checked.append({
            'stage': stage_id,
            'check': 'freshness_basis_%s' % label,
            'reason': 'freshness for %s rests on file mtime only; a copied file '
                      'with a touched timestamp can look fresh. Bind it with a '
                      'case manifest (produced_at + sha256 + '
                      'source_dump_sha256) for a content-bound claim.' % label,
        })
    if evidence_time < final_time:
        findings.append(_finding(
            'STALE_EVIDENCE',
            '%s is older than the final dump; it cannot prove the delivered board' % label,
            path=str(evidence.path),
            observed=_iso(evidence_time),
            final_dump=_iso(final_time),
        ))
        return False
    return True


# ---------------------------------------------------------------------------
# stage PG1: placement constraints / measured placement check


def _placement_payload(payload):
    data = _unwrap(payload)
    nested = data.get('check')
    if isinstance(nested, dict) and 'hard_ok' not in data:
        return nested
    return data


def evaluate_pg1(ctx):
    stage_id = 'PG1_placement'
    required = _stage_required(ctx['profile'], stage_id)
    roles = ctx['roles']
    constraints = roles.get('constraints')
    placement = roles.get('placement')
    missing = [role for role, evidence in (('constraints', constraints),
                                           ('placement', placement))
               if evidence is None or not evidence.usable]
    if missing:
        return _missing_stage(ctx, stage_id, required, missing,
                              'placement/constraint evidence missing')

    data_c = _unwrap(constraints.payload)
    data_p = _placement_payload(placement.payload)
    findings = []
    metrics = {}

    if data_c.get('schema') not in (None, CONSTRAINTS_SCHEMA):
        findings.append(_finding(
            'constraints_schema',
            'unexpected constraints schema %r' % (data_c.get('schema'),),
            severity='advisory'))
    if data_c.get('status') != 'compiled':
        findings.append(_finding(
            'constraints_not_compiled',
            'constraints status=%r; only compiled may gate a delivery'
            % (data_c.get('status'),)))
    raw_conflicts = data_c.get('conflicts')
    if isinstance(raw_conflicts, list):
        conflicts = [item for item in raw_conflicts if isinstance(item, dict)]
    elif raw_conflicts:
        conflicts = [raw_conflicts if isinstance(raw_conflicts, dict)
                     else {'kind': str(raw_conflicts)}]
    else:
        conflicts = []
    blocking_conflicts = [item for item in conflicts
                          if item.get('kind') != 'edge_fixed_requires_pose_check']
    if blocking_conflicts:
        findings.append(_finding(
            'constraint_conflicts',
            '%d constraint conflict(s) other than the benign edge/fixed pose check'
            % len(blocking_conflicts),
            kinds=sorted({_text(item.get('kind')) for item in blocking_conflicts})))
    raw_unknown = data_c.get('unknown')
    if isinstance(raw_unknown, list):
        unknown = [item for item in raw_unknown if isinstance(item, dict)]
    elif raw_unknown:
        unknown = [raw_unknown if isinstance(raw_unknown, dict)
                   else {'object': str(raw_unknown)}]
    else:
        unknown = []
    if unknown:
        findings.append(_finding(
            'constraint_unknown_objects',
            '%d constraint reference(s) could not be resolved on the measured board'
            % len(unknown), details=unknown[:10]))

    if data_p.get('schema') not in (None, PLACEMENT_SCHEMA):
        findings.append(_finding(
            'placement_schema',
            'unexpected placement schema %r' % (data_p.get('schema'),),
            severity='advisory'))
    if data_p.get('status') != 'pass':
        findings.append(_finding(
            'placement_not_pass',
            'placement status=%r; expected pass' % (data_p.get('status'),)))
    if data_p.get('hard_ok') is not True:
        findings.append(_finding('placement_hard_failed',
                                 'placement hard_ok is not true'))
    counts = data_p.get('counts') if isinstance(data_p.get('counts'), dict) else {}
    hard_failed = _int(counts.get('hard_failed'))
    hard_unmeasured = _int(counts.get('hard_unmeasured'))
    constraint_rows = _int(counts.get('constraint_rows'))
    if hard_failed:
        findings.append(_finding('placement_hard_failed',
                                 '%d hard placement finding(s)' % hard_failed))
    if hard_unmeasured:
        findings.append(_finding('placement_hard_unmeasured',
                                 '%d hard constraint(s) are unmeasured' % hard_unmeasured))
    if constraint_rows <= 0:
        findings.append(_finding(
            'placement_no_constraints',
            'placement check has constraint_rows=0; a pass without measured '
            'constraints is not proof (fixed/edge/near-pin/keepout unchecked)'))

    plan = roles.get('plan')
    metrics['plan_base_match'] = None
    if plan is None or not plan.usable:
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'plan_base_semantic_sha256',
            'reason': 'no placement plan was supplied; base hash is not checked',
        })
    else:
        data_plan = _unwrap(plan.payload)
        base = _text(data_plan.get('base_semantic_sha256'))
        final = _reference_dump(roles)
        if not base:
            ctx['not_checked'].append({
                'stage': stage_id,
                'check': 'plan_base_semantic_sha256',
                'reason': 'plan has no base_semantic_sha256 field',
            })
        elif final is None:
            ctx['not_checked'].append({
                'stage': stage_id,
                'check': 'plan_base_semantic_sha256',
                'reason': 'no measured dump is available to compare the plan hash',
            })
        else:
            current = _dump_semantic(final.payload)
            if not current:
                ctx['not_checked'].append({
                    'stage': stage_id,
                    'check': 'plan_base_semantic_sha256',
                    'reason': 'dump has no semanticSha256 to compare the plan hash',
                })
            elif base != current:
                findings.append(_finding(
                    'stale_plan',
                    'plan base_semantic_sha256 does not match the measured dump',
                    plan=base, dump=current))
                metrics['plan_base_match'] = False
            else:
                metrics['plan_base_match'] = True

    metrics.update({
        'constraint_status': data_c.get('status'),
        'constraint_count': len(data_c.get('constraints') or []),
        'constraint_conflicts': len(conflicts),
        'constraint_unknown': len(unknown),
        'placement_status': data_p.get('status'),
        'placement_hard_ok': data_p.get('hard_ok'),
        'constraint_rows': constraint_rows,
        'hard_failed': hard_failed,
        'hard_unmeasured': hard_unmeasured,
    })
    status = STATUS_FAIL if _hard(findings) else STATUS_PASS
    return _stage(stage_id, required, status, findings,
                  [constraints.meta(), placement.meta()] +
                  ([plan.meta()] if plan is not None else []), metrics)


# ---------------------------------------------------------------------------
# stage PG2: layout lint


def evaluate_pg2(ctx):
    stage_id = 'PG2_layout'
    required = _stage_required(ctx['profile'], stage_id)
    roles = ctx['roles']
    lint_evidence = roles.get('lint')
    if lint_evidence is None or not lint_evidence.usable:
        return _missing_stage(ctx, stage_id, required, ['lint'],
                              'layout-lint evidence missing')

    payload = _unwrap(lint_evidence.payload)
    lint = pcb_evidence.parse_layout_lint(lint_evidence.payload)
    if not lint.get('measured'):
        return _missing_stage(ctx, stage_id, required, ['lint'],
                              'layout-lint lacks score/crossings/component/'
                              'overlap coverage fields; it is not a measurement')
    findings = []
    if lint.get('diagnostics'):
        findings.append(_finding(
            'lint_diagnostics',
            '%d invalid field(s) in the layout-lint receipt; values were not '
            'coerced to zero' % len(lint['diagnostics']),
            details=lint['diagnostics'][:10]))
    if not lint.get('trusted', True):
        findings.append(_finding(
            'lint_envelope_failed',
            'layout-lint outer JSON reports ok=false; an inner report does not '
            'make the command successful'))
    if not lint.get('coverage_complete'):
        findings.append(_finding('lint_coverage_incomplete',
                                 'layout-lint coverage.complete is not true'))
    if lint.get('incomplete'):
        findings.append(_finding('lint_incomplete',
                                 'layout-lint marks the measurement incomplete'))
    if lint.get('score', 0) < LAYOUT_MIN_SCORE:
        findings.append(_finding(
            'lint_score',
            'layout-lint score %s < %d' % (lint.get('score'), LAYOUT_MIN_SCORE)))
    if lint.get('crossings', 0) > LAYOUT_MAX_CROSSINGS:
        findings.append(_finding(
            'lint_crossings',
            'layout-lint crossings %s > %d'
            % (lint.get('crossings'), LAYOUT_MAX_CROSSINGS)))
    for key, label in (('overlap', 'overlap'), ('off_board', 'off-board'),
                       ('short', 'short')):
        if lint.get(key, 0):
            findings.append(_finding('lint_%s' % key,
                                     'layout-lint %s=%s' % (label, lint.get(key))))
    if lint.get('tight', 0):
        findings.append(_finding('lint_tight',
                                 '%s tight pair(s); advisory' % lint.get('tight'),
                                 severity='advisory'))
    if lint.get('silk_over_pad', 0):
        findings.append(_finding('lint_silk_over_pad',
                                 '%s silk-over-pad item(s); advisory'
                                 % lint.get('silk_over_pad'),
                                 severity='advisory'))

    final = _final_dump(roles)
    components = _int(lint.get('components'), 0)
    if final is not None and components:
        dump_components = _dump_component_count(final.payload)
        if dump_components is not None and components != dump_components:
            findings.append(_finding(
                'lint_component_count',
                'layout-lint components %d != final dump %d; the lint may be stale'
                % (components, dump_components),
                severity='advisory'))

    _check_freshness(lint_evidence, final, stage_id, findings,
                     ctx['not_checked'], 'layout-lint')

    metrics = {key: lint.get(key) for key in
               ('score', 'crossings', 'components', 'overlap', 'off_board',
                'short', 'tight', 'silk_over_pad', 'coverage_complete',
                'incomplete')}
    status = STATUS_FAIL if _hard(findings) else STATUS_PASS
    return _stage(stage_id, required, status, findings,
                  [lint_evidence.meta()], metrics)


# ---------------------------------------------------------------------------
# stage PG3: native DRC


def evaluate_pg3(ctx):
    stage_id = 'PG3_drc'
    required = _stage_required(ctx['profile'], stage_id)
    drc_evidence = ctx['roles'].get('drc')
    if drc_evidence is None or not drc_evidence.usable:
        return _missing_stage(ctx, stage_id, required, ['drc'],
                              'native DRC evidence missing')

    drc = pcb_evidence.parse_drc(drc_evidence.payload)
    if not drc.get('measured'):
        return _missing_stage(ctx, stage_id, required, ['drc'],
                              'native DRC has no total/violations receipt; it is '
                              'not a measurement')
    findings = []
    if drc.get('contradictions'):
        findings.append(_finding(
            'drc_inconsistent',
            'native DRC receipt contradicts itself: %s'
            % '; '.join(drc['contradictions']),
            contradictions=drc['contradictions']))
    if not drc.get('trusted', True):
        findings.append(_finding(
            'drc_envelope_failed',
            'native DRC outer JSON reports ok=false; an inner result does not '
            'make the command successful'))
    if drc.get('diagnostics'):
        findings.append(_finding(
            'drc_diagnostics',
            '%d invalid field(s) in the native DRC receipt'
            % len(drc['diagnostics']), severity='advisory',
            details=drc['diagnostics'][:10]))
    if not drc.get('ok'):
        findings.append(_finding(
            'drc_failed',
            'native DRC is not clean (passed=%r total=%s connection=%s)'
            % (drc.get('passed'), drc.get('total'),
               drc.get('connection_violations')), total=drc.get('total')))
    _check_freshness(drc_evidence, _final_dump(ctx['roles']), stage_id,
                     findings, ctx['not_checked'], 'native DRC')
    metrics = {
        'passed': drc.get('passed'),
        'total': drc.get('total'),
        'connection_violations': drc.get('connection_violations'),
        'counts': drc.get('counts'),
    }
    status = STATUS_FAIL if _hard(findings) else STATUS_PASS
    return _stage(stage_id, required, status, findings,
                  [drc_evidence.meta()], metrics)


# ---------------------------------------------------------------------------
# stage PG4: pcb check + WARN dispositions


def _check_info_dispositions(report, disposition_payload):
    """Compatibility wrapper: the shared validator now covers INFO too.

    Kept for callers that imported the round-10 helper; the gate itself calls
    ``pcb_evidence.validate_warn_disposition(..., levels=(ERROR, WARN, INFO))``
    so ERROR/WARN/INFO cannot diverge in their key or level handling.
    """
    validation = pcb_evidence.validate_warn_disposition(
        disposition_payload, report, levels=('ERROR', 'WARN', 'INFO'))
    return {'missing': [item.get('key') for item in validation.get('missing') or []],
            'stale': validation.get('stale') or [],
            'invalid': validation.get('invalid') or []}


def evaluate_pg4(ctx):
    stage_id = 'PG4_check'
    required = _stage_required(ctx['profile'], stage_id)
    if ctx['profile'] == 'regression':
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'pcb_check_dispositions',
            'reason': 'pcb check and WARN dispositions are full-profile only',
        })
        return _stage(stage_id, False, STATUS_NOT_RUN,
                      metrics={'reason': 'regression profile'})

    roles = ctx['roles']
    check_evidence = roles.get('check')
    if check_evidence is None or not check_evidence.usable:
        return _missing_stage(ctx, stage_id, required, ['check'],
                              'pcb check evidence missing')

    report = pcb_evidence.parse_pcb_check(check_evidence.payload)
    if not report.get('measured'):
        return _missing_stage(ctx, stage_id, required, ['check'],
                              'pcb check has no summary/findings counters; it is '
                              'not a measurement')
    counts = report.get('counts') or {}
    error_rows = report.get('errors') or []
    warn_rows = report.get('warnings') or []
    info_rows = report.get('infos') or []
    # Summary counters are authoritative, but findings that exist without a
    # matching counter must still be dispositioned (never silently skipped).
    errors = max(_int(counts.get('errors')), len(error_rows))
    warnings = max(_int(counts.get('warnings')), len(warn_rows))
    infos = max(_int(counts.get('infos')), len(info_rows))

    findings, failed, blocked = [], False, False
    if errors:
        failed = True
        findings.append(_finding(
            'pcb_check_errors',
            'pcb check reports %d ERROR finding(s)' % errors))
    contradictions = report.get('contradictions') or []
    if contradictions:
        failed = True
        findings.append(_finding(
            'pcb_check_inconsistent',
            'pcb check summary/finding counters contradict each other: %s'
            % '; '.join(contradictions), contradictions=contradictions))
    if not report.get('trusted', True):
        failed = True
        findings.append(_finding(
            'pcb_check_envelope_failed',
            'pcb check outer JSON reports ok=false; an inner result does not '
            'make the command successful'))
    diagnostics = report.get('diagnostics') or []
    if diagnostics:
        findings.append(_finding(
            'pcb_check_diagnostics',
            '%d invalid field(s) in the pcb check receipt' % len(diagnostics),
            severity='advisory', details=diagnostics[:10]))
    if (errors > len(error_rows) or warnings > len(warn_rows) or
            infos > len(info_rows)):
        blocked = True
        findings.append(_finding(
            'pcb_check_unmapped_findings',
            'pcb check summary declares %d error(s)/%d warning(s)/%d info(s) but '
            'only %d/%d/%d are itemised; they cannot be dispositioned'
            % (errors, warnings, infos, len(error_rows), len(warn_rows),
               len(info_rows))))

    disposition = roles.get('warn_disposition')
    disposition_meta = None
    needed = errors + warnings + infos
    if needed:
        if disposition is None or not disposition.usable:
            blocked = True
            findings.append(_finding(
                'missing_warn_disposition',
                '%d WARN/ERROR/INFO pcb-check finding(s) have no disposition table'
                % needed, warnings=warnings, errors=errors, infos=infos))
        else:
            disposition_meta = disposition.meta()
            check_meta = check_evidence.meta()
            check_sha = [item for item in (check_meta.get('sha256'),
                                           _sha256_normalized(
                                               check_evidence.path))
                         if item]
            validation = pcb_evidence.validate_warn_disposition(
                disposition.payload, report, check_sha,
                levels=('ERROR', 'WARN', 'INFO'))
            if validation.get('problems') or validation.get('stale') or \
                    validation.get('invalid'):
                failed = True
                findings.append(_finding(
                    'invalid_warn_disposition',
                    'finding disposition table is invalid/stale: %d problem(s), '
                    '%d stale, %d invalid'
                    % (len(validation.get('problems') or []),
                       len(validation.get('stale') or []),
                       len(validation.get('invalid') or [])),
                    details={
                        'problems': validation.get('problems'),
                        'stale': validation.get('stale'),
                        'invalid': validation.get('invalid'),
                    }))
            elif validation.get('missing'):
                blocked = True
                missing_keys = [item.get('key') for item in
                                validation.get('missing') or []]
                findings.append(_finding(
                    'missing_warn_disposition',
                    '%d pcb-check finding(s) have no disposition entry'
                    % len(missing_keys), keys=missing_keys))

    payload = _unwrap(check_evidence.payload)
    coverage = payload.get('coverage')
    if isinstance(coverage, dict) and coverage.get('complete') is False:
        findings.append(_finding('pcb_check_coverage_incomplete',
                                 'pcb check coverage.complete is false',
                                 severity='advisory'))
    if payload.get('incomplete') is True:
        findings.append(_finding('pcb_check_incomplete',
                                 'pcb check marks the result incomplete',
                                 severity='advisory'))

    _check_freshness(check_evidence, _final_dump(roles), stage_id,
                     findings, ctx['not_checked'], 'pcb check')

    status = STATUS_FAIL if failed else (STATUS_BLOCKED if blocked else STATUS_PASS)
    metrics = {
        'errors': errors, 'warnings': warnings, 'infos': infos,
        'total': counts.get('total'),
        'disposition_present': disposition_meta is not None,
        'disposition_required': bool(needed),
    }
    evidence = [check_evidence.meta()]
    if disposition is not None and disposition.usable:
        evidence.append(disposition.meta())
    return _stage(stage_id, required, status, findings, evidence, metrics)


# ---------------------------------------------------------------------------
# stage PG5: key-net continuity


def evaluate_pg5(ctx):
    stage_id = 'PG5_netpath'
    required = _stage_required(ctx['profile'], stage_id)
    if ctx['profile'] == 'regression':
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'key_net_continuity',
            'reason': 'key-net net-path proofs are full-profile only',
        })
        return _stage(stage_id, False, STATUS_NOT_RUN,
                      metrics={'reason': 'regression profile'})

    if not ctx.get('key_nets'):
        return _missing_stage(ctx, stage_id, required, ['key_nets'],
                              '--key-nets is required for the full profile')
    netpath = ctx['roles'].get('netpath')
    if netpath is None or not netpath.usable:
        return _missing_stage(ctx, stage_id, required, ['netpath'],
                              'net-path evidence missing')

    rows = _netpath_rows(netpath.payload)
    if rows is None:
        return _missing_stage(ctx, stage_id, required, ['netpath'],
                              'net-path evidence has no rows array')

    result = pcb_evidence.evaluate_netpath(rows, ctx['key_nets'])
    findings = []
    if result.get('status') != 'pass':
        findings.append(_finding(
            'netpath_failed',
            'key-net continuity: %d missing, %d not connected/ambiguous, '
            '%d unmeasured'
            % (len(result.get('missing') or []), len(result.get('failed') or []),
               len(result.get('unmeasured') or [])),
            missing=result.get('missing'), failed=result.get('failed'),
            unmeasured=result.get('unmeasured')))
    _check_freshness(netpath, _final_dump(ctx['roles']), stage_id,
                     findings, ctx['not_checked'], 'net-path evidence')
    ctx['not_checked'].append({
        'stage': stage_id,
        'check': 'copper_pours',
        'reason': 'net-path proves listed tracks/vias only; copper pours need '
                  'DRC + poured-list evidence',
    })
    metrics = {
        'required': result.get('required'),
        'connected': result.get('connected'),
        'missing': len(result.get('missing') or []),
        'failed': len(result.get('failed') or []),
    }
    status = STATUS_FAIL if _hard(findings) else STATUS_PASS
    return _stage(stage_id, required, status, findings,
                  [netpath.meta()], metrics)


def _netpath_rows(payload):
    data = _unwrap(payload)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    rows = data.get('rows')
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    # A single `pcb net-path` result is still useful evidence for one pair.
    if all(key in data for key in ('net', 'from', 'to')):
        return [data]
    return None


# ---------------------------------------------------------------------------
# stage PG6: SCH-PCB reconciliation


def evaluate_pg6(ctx):
    stage_id = 'PG6_sch_pcb'
    required = _stage_required(ctx['profile'], stage_id)
    roles = ctx['roles']
    sch = roles.get('sch')
    after = roles.get('dump_after')
    compare = roles.get('sch_pcb')
    evidence = []

    freshness_findings = []
    if ctx.get('sch_explicit') and sch is not None and sch.usable and \
            after is not None and after.usable:
        result = pcb_evidence.compare_sch_pcb(
            sch.payload, after.payload,
            pin_aliases=ctx.get('pin_aliases'),
            ignore_designators=ctx.get('ignore_designators'))
        source = 'computed_from_sch_and_final_dump'
        evidence.extend([sch.meta(), after.meta()])
        fresh = True
    else:
        if compare is None or not compare.usable:
            missing = ['sch_pcb']
            if sch is None or not sch.usable:
                missing.append('sch')
            return _missing_stage(
                ctx, stage_id, required, missing,
                'SCH-PCB comparison evidence missing (provide --sch + --dump-after '
                'or --sch-pcb)')
        result = _unwrap(compare.payload)
        source = 'sch_pcb_evidence'
        evidence.append(compare.meta())
        fresh = _check_freshness(compare, _final_dump(roles), stage_id,
                                 freshness_findings, ctx['not_checked'],
                                 'SCH-PCB compare')

    findings = list(freshness_findings)
    status = result.get('status')
    if status == 'not_comparable':
        findings.append(_finding(
            'sch_pcb_not_comparable',
            'SCH-PCB comparison is not comparable: %s'
            % (result.get('reason') or 'empty or fully excluded side'),
            reason=result.get('reason')))
    elif status not in ('match', 'match_with_renames'):
        findings.append(_finding(
            'sch_pcb_mismatch',
            'SCH-PCB comparison status=%r; expected match or '
            'match_with_renames' % (status,)))
    elif status == 'match_with_renames':
        findings.append(_finding(
            'sch_pcb_net_renames',
            '%d net(s) have the same pin partition but a different name; '
            'connectivity is unchanged, naming needs review'
            % len(result.get('name_changes') or []),
            severity='advisory',
            renames=(result.get('name_changes') or [])[:10]))
    diagnostics = [item for item in result.get('diagnostics') or []
                   if isinstance(item, dict)]
    if diagnostics:
        findings.append(_finding(
            'sch_pcb_diagnostics',
            '%d SCH-PCB input diagnostic(s)' % len(diagnostics),
            severity='advisory', details=diagnostics[:10]))
    if result.get('partition_match') is False:
        findings.append(_finding(
            'sch_pcb_partition_mismatch',
            'pins are grouped into different nets on the schematic and PCB'))
    component_mismatches = [item for item in
                            result.get('component_mismatches') or []
                            if isinstance(item, dict)]
    mismatches = [item for item in result.get('mismatches') or []
                  if isinstance(item, dict)]
    if component_mismatches:
        findings.append(_finding(
            'sch_pcb_component_mismatch',
            '%d component-level mismatch(es)' % len(component_mismatches),
            details=component_mismatches[:10]))
    if mismatches:
        findings.append(_finding(
            'sch_pcb_pin_mismatch',
            '%d pad/pin mismatch(es)' % len(mismatches),
            details=mismatches[:10]))

    schematic_components = _int(result.get('schematic_components'), -1)
    pcb_components = _int(result.get('pcb_components'), -1)
    pins = _int(result.get('pins'), -1)
    if min(schematic_components, pcb_components, pins) < 0:
        findings.append(_finding(
            'sch_pcb_unmeasured',
            'SCH-PCB comparison does not report component/pin counts'))
    else:
        if schematic_components != pcb_components:
            findings.append(_finding(
                'sch_pcb_component_count',
                'schematic %d component(s) != PCB %d component(s)'
                % (schematic_components, pcb_components)))
        if pins <= 0:
            findings.append(_finding('sch_pcb_no_pins',
                                     'SCH-PCB comparison covered 0 pins'))

    final = _final_dump(roles)
    if final is not None and pcb_components >= 0:
        dump_components = _dump_component_count(final.payload)
        if dump_components is None:
            ctx['not_checked'].append({
                'stage': stage_id,
                'check': 'sch_pcb_dump_crosscheck',
                'reason': 'the final dump has no component count to cross-check',
            })
        elif pcb_components != dump_components:
            findings.append(_finding(
                'sch_pcb_wrong_dump',
                'SCH-PCB comparison has %d PCB components but the final dump has %d'
                % (pcb_components, dump_components)))
    else:
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'sch_pcb_dump_crosscheck',
            'reason': 'no final dump is available to cross-check the comparison',
        })

    metrics = {
        'source': source,
        'fresh': fresh,
        'status': result.get('status'),
        'schematic_components': schematic_components,
        'pcb_components': pcb_components,
        'pins': pins,
        'mismatches': len(mismatches),
        'component_mismatches': len(component_mismatches),
        'name_changes': len(result.get('name_changes') or []),
        'excluded_designators': result.get('excluded_designators') or [],
        'partition_match': result.get('partition_match'),
    }
    status = STATUS_FAIL if _hard(findings) else STATUS_PASS
    return _stage(stage_id, required, status, findings, evidence, metrics)


# ---------------------------------------------------------------------------
# stage PG7: save/reload persistence


def evaluate_pg7(ctx):
    stage_id = 'PG7_save_reload'
    required = _stage_required(ctx['profile'], stage_id)
    roles = ctx['roles']
    before = roles.get('dump_before')
    after = roles.get('dump_after')
    missing = []
    if before is None or not before.usable:
        missing.append('dump_before')
    if after is None or not after.usable:
        missing.append('dump_after')
    if missing:
        return _missing_stage(ctx, stage_id, required, missing,
                              'before/after save-reload dump missing')

    findings, failed = [], False
    before_payload, after_payload = before.payload, after.payload
    if _dump_component_count(before_payload) is None or \
            _dump_component_count(after_payload) is None:
        return _missing_stage(ctx, stage_id, required,
                              ['dump_before', 'dump_after'],
                              'dump has no components array')

    try:
        same_file = before.path.resolve() == after.path.resolve()
    except OSError:
        same_file = str(before.path) == str(after.path)
    if same_file:
        failed = True
        findings.append(_finding(
            'same_dump',
            'before and after point at the same file; this is not a reload readback'))

    scope = ctx.get('edit_scope')
    mode = 'edit' if scope is not None else 'pure_persistence'
    diff = diff_boards(before_payload, after_payload, scope)
    if scope is None:
        if diff.get('status') != 'match':
            failed = True
            findings.append(_finding(
                'save_reload_changed',
                'pure save/reload must be match, got %r' % (diff.get('status'),),
                counts=diff.get('counts')))
    else:
        if diff.get('status') not in ('match', 'changed'):
            failed = True
            findings.append(_finding(
                'save_reload_mismatch',
                'scoped edit diff status=%r; expected match or changed'
                % (diff.get('status'),), counts=diff.get('counts')))
        if diff.get('unrelated_changes'):
            failed = True
            findings.append(_finding(
                'save_reload_unrelated',
                '%d change(s) outside the declared edit scope'
                % len(diff.get('unrelated_changes') or []),
                details=diff.get('unrelated_changes')[:10]))
    if scope is None and diff.get('unrelated_changes'):
        failed = True

    hash_before = _dump_semantic(before_payload)
    hash_after = _dump_semantic(after_payload)
    if hash_before and hash_after:
        if hash_before != hash_after and scope is None:
            failed = True
            findings.append(_finding(
                'semantic_hash_changed',
                'semanticSha256 changed across a pure save/reload',
                before=hash_before, after=hash_after))
    else:
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'semantic_sha256',
            'reason': 'one or both dumps have no semanticSha256',
        })

    for key, label in (('documentUuid', 'documentUuid'),
                       ('projectUuid', 'projectUuid')):
        value_before = _dump_capture(before_payload, key)
        value_after = _dump_capture(after_payload, key)
        if value_before and value_after and value_before != value_after:
            if scope is None:
                failed = True
                findings.append(_finding(
                    'capture_identity_changed',
                    '%s changed across save/reload' % label,
                    before=value_before, after=value_after))
            else:
                findings.append(_finding(
                    'capture_identity_changed',
                    '%s differs across the edited pair (allowed in edit mode)'
                    % label, severity='advisory',
                    before=value_before, after=value_after))

    time_before = _evidence_time(before)
    time_after = _evidence_time(after)
    if time_before and time_after and time_after < time_before:
        failed = True
        findings.append(_finding(
            'dump_order',
            'after dump is older than before dump',
            before=_iso(time_before), after=_iso(time_after)))

    save_reload = roles.get('save_reload')
    evidence = [before.meta(), after.meta()]
    if save_reload is not None and save_reload.usable:
        evidence.append(save_reload.meta())
        explicit = _captured_time(save_reload.payload)
        if explicit and time_after and time_after < explicit:
            failed = True
            findings.append(_finding(
                'save_reload_after_reload',
                'after dump predates the recorded save/reload evidence',
                after_dump=_iso(time_after), reload_evidence=_iso(explicit)))
        elif not explicit:
            ctx['not_checked'].append({
                'stage': stage_id,
                'check': 'reload_timestamps',
                'reason': 'save/reload evidence carries no capture timestamp; '
                          'reload order is inferred from the two dumps only',
            })
    else:
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'save_reload_diff',
            'reason': 'no save-reload-diff report; the diff is recomputed from '
                      'the two dumps',
        })

    metrics = {
        'mode': mode,
        'scope': scope,
        'diff_status': diff.get('status'),
        'diff_counts': diff.get('counts'),
        'semantic_sha256_before': hash_before,
        'semantic_sha256_after': hash_after,
        'document_uuid': _dump_capture(after_payload, 'documentUuid'),
        'project_uuid': _dump_capture(after_payload, 'projectUuid'),
    }
    status = STATUS_FAIL if failed or _hard(findings) else STATUS_PASS
    return _stage(stage_id, required, status, findings, evidence, metrics)


# ---------------------------------------------------------------------------
# stage PG8: delivery artifacts


def _png_info(path):
    try:
        with open(path, 'rb') as handle:
            head = handle.read(24)
    except OSError as exc:
        return None, 'unreadable: %s' % exc
    if len(head) < 24 or head[:8] != b'\x89PNG\r\n\x1a\n':
        return None, 'PNG signature missing'
    if head[12:16] != b'IHDR':
        return None, 'PNG has no IHDR header'
    width, height = struct.unpack('>II', head[16:24])
    if width <= 0 or height <= 0:
        return None, 'PNG dimensions are invalid (%dx%d)' % (width, height)
    return {'width': width, 'height': height}, None


def _read_svg(path):
    try:
        with open(path, 'r', encoding='utf-8-sig', errors='replace') as handle:
            text = handle.read()
    except OSError as exc:
        return None, 'unreadable: %s' % exc
    if not text.strip():
        return None, 'SVG file is empty'
    if '<svg' not in text.lower():
        return None, 'file does not contain an <svg> element'
    return {'bytes': len(text)}, None


def _bom_info(path):
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, 'unreadable: %s' % exc
    if size <= 0:
        return None, 'BOM file is empty'
    try:
        with open(path, 'r', encoding='utf-8-sig', errors='replace',
                  newline='') as handle:
            rows = list(csv.reader(handle))
    except OSError as exc:
        return None, 'unreadable: %s' % exc
    nonempty = [row for row in rows if any(cell.strip() for cell in row)]
    if not nonempty:
        return None, 'BOM file has no rows'
    return {'bytes': size, 'rows': len(nonempty)}, None


def _epro2_info(path):
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, 'unreadable: %s' % exc
    if size <= 0:
        return None, 'archive is empty'
    if not zipfile.is_zipfile(str(path)):
        return {'bytes': size, 'zip': False}, 'archive is not a zip container (advisory)'
    return {'bytes': size, 'zip': True}, None


def _normalise_baseline_roles(manifest):
    if not isinstance(manifest, dict):
        raise InputError('baseline manifest must be a JSON object')
    artifacts = manifest.get('artifacts')
    roles = {}
    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            role = _text(item.get('role'))
            digest = _text(item.get('sha256'))
            if not role or not digest:
                continue
            canonical = canonical_baseline_role(role)
            if not canonical:
                continue
            roles.setdefault(canonical, []).append(digest)
        return roles, len(artifacts)
    # A plain {role: sha256} mapping is also accepted.
    for role, digest in manifest.items():
        if isinstance(digest, str) and len(digest) == 64:
            canonical = canonical_baseline_role(role)
            if canonical:
                roles.setdefault(canonical, []).append(digest)
    return roles, len(manifest)


def _compare_baseline(current, expected):
    changed, missing = [], []
    for role, digests in sorted(expected.items()):
        actual = current.get(role)
        if actual is None:
            missing.append({'role': role, 'expected': digests})
        elif actual not in digests:
            changed.append({'role': role, 'expected': digests, 'actual': actual})
    return {'status': 'match' if not changed and not missing else 'mismatch',
            'changed': changed, 'missing': missing}


def evaluate_pg8(ctx):
    stage_id = 'PG8_delivery'
    required = _stage_required(ctx['profile'], stage_id)
    roles = ctx['roles']
    missing = [role for role in DELIVERY_ROLES
               if roles.get(role) is None or not roles[role].usable]
    if missing:
        return _missing_stage(ctx, stage_id, required, missing,
                              'delivery artifact missing')

    findings, failed = [], False
    metrics = {}
    evidence = []
    images = {}

    for role in ('image_top', 'image_bottom'):
        info, error = _png_info(roles[role].path)
        evidence.append(roles[role].meta())
        if error:
            failed = True
            findings.append(_finding('invalid_png', '%s: %s' % (role, error),
                                     path=str(roles[role].path)))
        else:
            images[role] = info
    svg_info, svg_error = _read_svg(roles['actual_svg'].path)
    evidence.append(roles['actual_svg'].meta())
    if svg_error:
        if 'does not contain' in svg_error:
            findings.append(_finding('svg_structure', svg_error,
                                     severity='advisory',
                                     path=str(roles['actual_svg'].path)))
        else:
            failed = True
            findings.append(_finding('invalid_svg', svg_error,
                                     path=str(roles['actual_svg'].path)))
    bom_info, bom_error = _bom_info(roles['bom'].path)
    evidence.append(roles['bom'].meta())
    if bom_error:
        failed = True
        findings.append(_finding('invalid_bom', bom_error,
                                 path=str(roles['bom'].path)))
    archive_info, archive_error = _epro2_info(roles['archive'].path)
    evidence.append(roles['archive'].meta())
    if archive_error and archive_info is None:
        failed = True
        findings.append(_finding('invalid_archive', archive_error,
                                 path=str(roles['archive'].path)))
    elif archive_error:
        findings.append(_finding('archive_structure', archive_error,
                                 severity='advisory',
                                 path=str(roles['archive'].path)))

    # Images should show the final board.  This is advisory because the dump
    # does not embed image identity; strict-advisory turns it into a failure.
    final_time = _evidence_time(_final_dump(roles)) if _final_dump(roles) else None
    if final_time is not None:
        stale_images = []
        for role in ('image_top', 'image_bottom', 'actual_svg'):
            observed, _basis = _evidence_time_with_basis(roles[role])
            if observed is not None and observed < final_time:
                stale_images.append(role)
        if stale_images:
            findings.append(_finding(
                'stale_image',
                'delivery image(s) predate the final dump: %s'
                % ', '.join(stale_images), severity='advisory',
                roles=stale_images, final_dump=_iso(final_time)))

    baseline = ctx.get('baseline')
    baseline_metrics = {'provided': baseline is not None}
    if baseline is not None:
        current = {}
        for role in DELIVERY_ROLES:
            meta = roles[role].meta()
            if meta.get('sha256'):
                current[role] = meta['sha256']
        comparison = _compare_baseline(current, baseline['roles'])
        baseline_metrics.update({
            'status': comparison['status'],
            'changed': comparison['changed'],
            'missing': comparison['missing'],
            'compared_roles': sorted(baseline['roles']),
        })
        if comparison['status'] != 'match':
            failed = True
            findings.append(_finding(
                'baseline_changed',
                'delivery hashes differ from the baseline manifest',
                changed=comparison['changed'], missing=comparison['missing']))
    else:
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'baseline_manifest',
            'reason': 'no --baseline-manifest was supplied; image/BOM/archive '
                      'hashes are recorded but not compared',
        })

    ctx['not_checked'].append({
        'stage': stage_id,
        'check': 'archive_restore',
        'reason': '.epro2 restore/open verification is not performed by this gate',
    })

    metrics.update({
        'images': images,
        'svg': svg_info,
        'bom': bom_info,
        'archive': archive_info,
        'archive_sha256': roles['archive'].meta().get('sha256'),
        'baseline': baseline_metrics,
    })
    status = STATUS_FAIL if failed or _hard(findings) else STATUS_PASS
    return _stage(stage_id, required, status, findings, evidence, metrics)


# ---------------------------------------------------------------------------
# stage helpers


def _hard(findings):
    return [item for item in findings if item.get('severity') == 'hard']


_BINDING_MESSAGES = {
    'manifest_sha256_mismatch': 'the file no longer matches the manifest hash',
    'source_dump_changed': 'the source dump changed after this evidence was produced',
    'project_identity_mismatch': 'the evidence names a different project than the final dump',
    'document_identity_mismatch': 'the evidence names a different PCB document/page than the final dump',
    'missing_artifact': 'the manifest names an artifact that does not exist',
    'manifest_role_ambiguous': 'the manifest declares multiple different '
                               'artifacts for this role',
    'manifest_status_failed': 'the case manifest itself reports failed while '
                              'this artifact claims to be post-final-reload',
}


def _apply_binding_findings(stages, roles):
    """Attach provenance/conflict findings to the stage that consumes a role."""
    by_id = {stage['id']: stage for stage in stages}
    for role, evidence in sorted(roles.items()):
        if evidence is None:
            continue
        stage = by_id.get(ROLE_STAGE.get(role))
        if stage is None:
            continue
        binding = evidence.binding or {}
        error = binding.get('error')
        if error:
            stage['findings'].append(_finding(
                'EVIDENCE_BINDING',
                '%s evidence %s: %s' % (
                    role, _BINDING_MESSAGES.get(error, error),
                    evidence.path),
                role=role, path=str(evidence.path),
                binding=binding))
            stage['status'] = STATUS_FAIL
        conflict = evidence.conflict
        if conflict:
            if conflict.get('kind') == 'identity_conflict':
                stage['findings'].append(_finding(
                    'EVIDENCE_IDENTITY_CONFLICT',
                    'multiple %s candidates describe different projects/pages'
                    % role, role=role, conflict=conflict))
                stage['status'] = STATUS_FAIL
            else:
                stage['findings'].append(_finding(
                    'EVIDENCE_AMBIGUOUS',
                    'multiple %s candidates differ; the selected one is %s; '
                    'bind it with a manifest or an explicit role override'
                    % (role, conflict.get('selected')),
                    severity='advisory', role=role, conflict=conflict))
        stage['metrics'].setdefault('evidence_binding', {})[role] = {
            'basis': binding.get('basis'),
            'error': error,
            'conflict': conflict.get('kind') if conflict else None,
            'manifest': bool(evidence.manifest_entry),
        }


def _missing_stage(ctx, stage_id, required, missing_roles, reason):
    roles = ctx['roles']
    status = STATUS_BLOCKED if required else STATUS_NOT_RUN
    findings = [_finding(
        'missing_evidence',
        '%s: %s' % (reason, ', '.join(missing_roles)),
        severity='hard' if status == STATUS_BLOCKED else 'advisory',
        roles=missing_roles)]
    evidence = []
    for role in missing_roles:
        item = roles.get(role)
        if item is not None:
            evidence.append(item.meta())
    if status == STATUS_NOT_RUN:
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'stage',
            'reason': 'optional in the %s profile and evidence is absent: %s'
                      % (ctx['profile'], ', '.join(missing_roles)),
        })
    else:
        ctx['not_checked'].append({
            'stage': stage_id,
            'check': 'stage',
            'reason': 'blocked: required evidence is missing: %s'
                      % ', '.join(missing_roles),
        })
    return _stage(stage_id, required, status, findings, evidence,
                  {'missing_roles': missing_roles, 'reason': reason})


# ---------------------------------------------------------------------------
# key-nets / baseline / scope inputs


def _parse_key_nets(path):
    try:
        data = _unwrap_or_value(load_json(str(path)))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise InputError('key-nets JSON is unreadable: %s (%s)' % (path, exc))
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get('key_nets')
        if items is None:
            items = data.get('nets')
        if items is None:
            items = data.get('required')
    else:
        raise InputError('key-nets must be a list or an object with key_nets/nets')
    if not isinstance(items, list) or not items:
        raise InputError('key-nets must contain at least one {net,from,to} entry')
    required = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise InputError('key-nets[%d] must be an object' % index)
        net = _text(item.get('net'))
        start = _text(item.get('from'))
        end = _text(item.get('to'))
        if not (net and start and end):
            raise InputError('key-nets[%d] needs non-empty net/from/to' % index)
        required.append({'net': net, 'from': start, 'to': end})
    return required


def _load_key_nets(args, evidence_dir, case_dir):
    value = getattr(args, 'key_nets', None)
    if value:
        path = _resolve_path(value, evidence_dir)
        if not path.is_file():
            raise InputError('key-nets file not found: %s' % path)
        return _parse_key_nets(path)
    for directory in (evidence_dir, case_dir):
        for pattern in ('key-nets*.json', 'key_nets*.json', 'pcb-key-nets*.json'):
            candidates = sorted(directory.glob(pattern),
                                key=lambda item: item.stat().st_mtime
                                if item.exists() else 0, reverse=True)
            if candidates:
                return _parse_key_nets(candidates[0])
    return None


def _load_baseline(args, evidence_dir):
    value = getattr(args, 'baseline_manifest', None)
    if not value:
        return None
    path = _resolve_path(value, evidence_dir)
    if not path.is_file():
        raise InputError('baseline manifest not found: %s' % path)
    try:
        data = _unwrap_or_value(load_json(str(path)))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise InputError('baseline manifest is unreadable: %s (%s)' % (path, exc))
    roles, total = _normalise_baseline_roles(data)
    if not roles:
        raise InputError(
            'baseline manifest has no delivery roles (image_top/image_bottom/'
            'actual_svg/bom/archive); found %d artifact(s)' % total)
    return {'path': str(path), 'roles': roles, 'artifacts': total}


def _load_pin_aliases(args, evidence_dir):
    value = getattr(args, 'pin_aliases', None)
    if not value:
        return None
    path = _resolve_path(value, evidence_dir)
    if not path.is_file():
        raise InputError('pin-aliases file not found: %s' % path)
    try:
        data = _unwrap_or_value(load_json(str(path)))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise InputError('pin-aliases is unreadable: %s (%s)' % (path, exc))
    if not isinstance(data, dict):
        raise InputError('pin-aliases must be an object '
                         '{designator: {schematic_pin: [pcb_pad, ...]}}')
    return data


def _load_ignore_designators(args):
    raw = getattr(args, 'ignore_designators', None)
    if not raw:
        return []
    result = []
    for item in raw:
        for value in str(item).split(','):
            value = value.strip()
            if value:
                result.append(value)
    return sorted(set(result))


def _load_edit_scope(args, evidence_dir):
    value = getattr(args, 'edit_scope', None)
    if not value:
        return None
    path = _resolve_path(value, evidence_dir)
    if not path.is_file():
        raise InputError('edit-scope file not found: %s' % path)
    try:
        data = _unwrap_or_value(load_json(str(path)))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise InputError('edit-scope is unreadable: %s (%s)' % (path, exc))
    if isinstance(data, list):
        scope = {'designators': [str(item) for item in data]}
    elif isinstance(data, dict):
        nested = data.get('scope')
        scope = nested if isinstance(nested, dict) else data
    else:
        raise InputError('edit-scope must be a list or an object')
    for key in ('designators', 'nets'):
        if key in scope and not isinstance(scope[key], (list, tuple)):
            raise InputError('edit-scope.%s must be a list' % key)
    bbox = scope.get('bbox')
    if bbox is not None:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or not all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in bbox):
            raise InputError('edit-scope.bbox must be four finite numbers '
                             '[minX,minY,maxX,maxY]')
    if not (scope.get('designators') or scope.get('nets') or scope.get('bbox')):
        raise InputError('edit-scope is empty; give designators, nets or bbox')
    return scope


# ---------------------------------------------------------------------------
# overall report


def _overall_status(stages, strict_advisory):
    if strict_advisory:
        for stage in stages:
            if stage['status'] == STATUS_PASS and any(
                    finding.get('severity') == 'advisory'
                    for finding in stage['findings']):
                stage['status'] = STATUS_FAIL
                stage['findings'].append(_finding(
                    'advisory_escalated',
                    'advisory finding escalated by --strict-advisory'))
    if any(stage['status'] == STATUS_FAIL for stage in stages):
        return STATUS_FAIL
    if any(stage['status'] == STATUS_BLOCKED for stage in stages):
        return STATUS_BLOCKED
    if any(stage['required'] and stage['status'] == STATUS_NOT_RUN
           for stage in stages):
        return STATUS_BLOCKED
    if any(stage['status'] == STATUS_NOT_RUN for stage in stages):
        return STATUS_PASS_WITH_GAPS
    return STATUS_PASS


def _project_doc(roles):
    final = _final_dump(roles)
    project = '<project>'
    doc = '<PCB>'
    if final is not None and isinstance(final.payload, dict):
        project = (_dump_capture(final.payload, 'projectName') or
                   _text(final.payload.get('project')) or project)
        doc = (_dump_capture(final.payload, 'documentName') or
               _dump_capture(final.payload, 'documentUuid') or doc)
    return project, doc


def _next_command(stages, ctx):
    case = str(ctx['case'])
    evidence = str(ctx['evidence_dir'])
    project, doc = _project_doc(ctx['roles'])
    first = next((stage for stage in stages
                  if stage['status'] in (STATUS_FAIL, STATUS_BLOCKED)), None)
    if first is None:
        if any(stage['status'] == STATUS_NOT_RUN for stage in stages):
            return 'python scripts/pcb_gate.py --case %s --profile full' % case
        return 'python scripts/pcb_gate.py --case %s --profile %s' % (
            case, ctx['profile'])
    stage_id = first['id']
    if stage_id == 'PG1_placement':
        return ('python scripts/design_engine_cli.py pcb-constraints --dump %s '
                '--intent <intent.json> --out %s --json'
                % (case, os.path.join(evidence, 'constraints.json')))
    if stage_id == 'PG2_layout':
        return ('easyeda pcb layout-lint --json --project %s --doc %s > %s'
                % (project, doc, os.path.join(evidence, 'pcb-layout-lint.json')))
    if stage_id == 'PG3_drc':
        return ('easyeda pcb drc --json --timeout 120 --project %s --doc %s > %s'
                % (project, doc, os.path.join(evidence, 'pcb-drc.json')))
    if stage_id == 'PG4_check':
        return ('easyeda pcb check --json --project %s --doc %s > %s ; then write '
                'a warn-disposition file and rerun the gate'
                % (project, doc, os.path.join(evidence, 'pcb-check.json')))
    if stage_id == 'PG5_netpath':
        return ('easyeda pcb net-path --from D.PAD --to D.PAD --net NET --json '
                '--project %s --doc %s > %s'
                % (project, doc, os.path.join(evidence, 'netpath-key-connections.json')))
    if stage_id == 'PG6_sch_pcb':
        return ('easyeda sch read --project %s --out %s ; then rerun with --sch '
                'and --dump-after' % (project,
                                      os.path.join(evidence, 'sch-read.json')))
    if stage_id == 'PG7_save_reload':
        return ('easyeda pcb save --project %s --doc %s ; easyeda doc reload %s '
                '--project %s --json ; easyeda pcb dump --project %s --doc %s '
                '--include-copper --out %s'
                % (project, doc, doc, project, project, doc,
                   os.path.join(evidence, 'pcb-dump-after-reload.json')))
    if stage_id == 'PG8_delivery':
        return ('easyeda pcb stage-snapshot --stage top --project %s --doc %s --out %s '
                '; easyeda pcb stage-snapshot --stage bottom --project %s --doc %s '
                '--out %s ; easyeda pcb layout render --actual --board %s --side both '
                '--out %s'
                % (project, doc, evidence, project, doc, evidence,
                   os.path.join(evidence, 'pcb-dump-final.json'),
                   os.path.join(evidence, 'pcb-final-actual.svg')))
    return 'python scripts/pcb_gate.py --case %s --profile full' % case


def _counts(stages):
    counts = {
        'stages': len(stages),
        'pass': 0, 'fail': 0, 'blocked': 0, 'not_run': 0,
        'required_fail': 0, 'required_blocked': 0, 'optional_not_run': 0,
        'findings': 0, 'advisory_findings': 0,
    }
    for stage in stages:
        counts[stage['status']] = counts.get(stage['status'], 0) + 1
        if stage['status'] == STATUS_FAIL and stage['required']:
            counts['required_fail'] += 1
        if stage['status'] == STATUS_BLOCKED and stage['required']:
            counts['required_blocked'] += 1
        if stage['status'] == STATUS_NOT_RUN and not stage['required']:
            counts['optional_not_run'] += 1
        for finding in stage['findings']:
            counts['findings'] += 1
            if finding.get('severity') == 'advisory':
                counts['advisory_findings'] += 1
    return counts


def evaluate(args):
    """Evaluate one case and return the report dict (no EDA, no writes)."""
    profile = getattr(args, 'profile', 'full') or 'full'
    if profile not in PROFILES:
        raise InputError('profile must be full or regression, got %r' % profile)
    case_value = getattr(args, 'case', None)
    if not case_value:
        raise InputError('--case DIR is required')
    case_dir = Path(case_value)
    if not case_dir.is_dir():
        raise InputError('case directory not found: %s' % case_dir)
    evidence_dir = case_dir / 'evidence' if (case_dir / 'evidence').is_dir() else case_dir

    images_value = getattr(args, 'images', None)
    if images_value:
        images_dir = Path(images_value)
        if not images_dir.is_dir():
            raise InputError('images directory not found: %s' % images_dir)
    else:
        images_dir = evidence_dir

    overrides = collect_overrides(args)
    manifest = load_case_manifest(case_dir)
    roles = load_all_evidence(evidence_dir, overrides, images_dir,
                              manifest=manifest, case_dir=case_dir)
    bind_manifest_evidence(roles, manifest, case_dir)
    key_nets = _load_key_nets(args, evidence_dir, case_dir)
    baseline = _load_baseline(args, evidence_dir)
    edit_scope = _load_edit_scope(args, evidence_dir)
    pin_aliases = _load_pin_aliases(args, evidence_dir)
    ignore_designators = _load_ignore_designators(args)

    ctx = {
        'profile': profile,
        'case': case_dir,
        'evidence_dir': evidence_dir,
        'images_dir': images_dir,
        'roles': roles,
        'key_nets': key_nets,
        'baseline': baseline,
        'edit_scope': edit_scope,
        'manifest': manifest,
        'pin_aliases': pin_aliases,
        'ignore_designators': ignore_designators,
        'sch_explicit': bool(getattr(args, 'sch', None) or
                             overrides.get('sch')),
        'not_checked': [],
    }

    evaluators = (
        ('PG1_placement', evaluate_pg1),
        ('PG2_layout', evaluate_pg2),
        ('PG3_drc', evaluate_pg3),
        ('PG4_check', evaluate_pg4),
        ('PG5_netpath', evaluate_pg5),
        ('PG6_sch_pcb', evaluate_pg6),
        ('PG7_save_reload', evaluate_pg7),
        ('PG8_delivery', evaluate_pg8),
    )
    stages = []
    for stage_id, function in evaluators:
        try:
            stage = function(ctx)
        except InputError:
            raise
        except Exception as exc:  # fail closed on malformed evidence
            stage = _stage(
                stage_id, _stage_required(profile, stage_id), STATUS_FAIL,
                [_finding(
                    'stage_error',
                    'stage could not be evaluated from the supplied evidence: '
                    '%s: %s' % (type(exc).__name__, exc),
                    exception=type(exc).__name__)],
                [], {'exception': type(exc).__name__})
        stages.append(stage)
    _apply_binding_findings(stages, roles)
    ctx['not_checked'].append({
        'stage': '*',
        'check': 'functional_thermal_emc_manufacturing',
        'reason': 'DRC/lint/pcb-check/net-path do not prove firmware function, '
                  'thermal, EMC, assembly or manufacturability',
    })
    status = _overall_status(stages, bool(getattr(args, 'strict_advisory', False)))
    counts = _counts(stages)

    report = {
        'schema': REPORT_SCHEMA,
        'status': status,
        'profile': profile,
        'case': str(case_dir),
        'evidence_dir': str(evidence_dir),
        'images_dir': str(images_dir),
        'generated_at': utc_now(),
        'stages': stages,
        'counts': counts,
        'not_checked': ctx['not_checked'],
        'next_command': _next_command(stages, ctx),
        'strict_advisory': bool(getattr(args, 'strict_advisory', False)),
        'key_nets': key_nets,
        'baseline_manifest': baseline['path'] if baseline else None,
        'case_manifest': manifest['path'] if manifest else None,
        'edit_scope': edit_scope,
        'evidence': {role: evidence.meta()
                     for role, evidence in sorted(roles.items())
                     if evidence is not None},
        'warnings': [
            {'role': evidence.role, 'path': str(evidence.path), 'error': evidence.error}
            for evidence in roles.values()
            if evidence is not None and evidence.error
        ],
    }
    return report


def render_human(report):
    lines = ['pcb-gate: %s' % report.get('case')]
    lines.append('profile=%s status=%s exit=%d' % (
        report['profile'], report['status'], EXIT_CODES[report['status']]))
    for stage in report['stages']:
        lines.append('  %-16s %-9s required=%s' % (
            stage['id'], stage['status'],
            'yes' if stage['required'] else 'no'))
        for finding in stage['findings']:
            if finding.get('severity') == 'advisory' and stage['status'] == STATUS_PASS:
                continue
            lines.append('    %-8s %s: %s' % (
                finding.get('severity', 'hard').upper(),
                finding.get('code'), finding.get('message')))
    lines.append('not_checked: %d item(s)' % len(report.get('not_checked') or []))
    if report.get('next_command'):
        lines.append('next: %s' % report['next_command'])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Offline PCB gate PG1..PG8. Reads evidence only; never '
                    'connects to EDA and never writes to a project.')
    parser.add_argument('--case', required=True, help='case directory')
    parser.add_argument('--profile', choices=PROFILES, default='full')
    parser.add_argument('--baseline-manifest', help='manifest with artifact role hashes')
    parser.add_argument('--key-nets', help='JSON list of {net,from,to} key nets')
    parser.add_argument('--warn-disposition', help='pcb-warn-disposition/v1 JSON')
    parser.add_argument('--dump-before', help='measured dump before save/reload')
    parser.add_argument('--dump-after', help='measured dump after save/reload')
    parser.add_argument('--constraints', help='compiled constraints JSON')
    parser.add_argument('--plan', help='placement plan JSON')
    parser.add_argument('--intent', help='PCB intent JSON')
    parser.add_argument('--check', help='pcb check JSON')
    parser.add_argument('--drc', help='native pcb drc JSON')
    parser.add_argument('--lint', help='pcb layout-lint JSON')
    parser.add_argument('--netpath', help='net-path aggregate JSON')
    parser.add_argument('--sch-pcb', help='SCH-PCB comparison JSON')
    parser.add_argument('--sch', help='schematic read/connectivity JSON')
    parser.add_argument('--pin-aliases',
                        help='JSON {designator: {sch_pin: [pcb_pad, ...]}}')
    parser.add_argument('--ignore-designators',
                        action='append', metavar='DESIGNATOR[,DESIGNATOR]',
                        help='exclude these designators from SCH-PCB compare '
                             '(reported explicitly; all-excluded is not a pass)')
    parser.add_argument('--images', help='directory with top/bottom PNG and actual SVG')
    parser.add_argument('--edit-scope', help='scope JSON for an intentional local edit')
    parser.add_argument('--file', action='append', metavar='ROLE=PATH',
                        help='explicit evidence override (repeatable)')
    parser.add_argument('--role', action='append', metavar='ROLE=PATH',
                        help='alias of --file (repeatable)')
    parser.add_argument('--out', help='report path (default: <case>/gate-report.json)')
    parser.add_argument('--json', action='store_true', help='print the full JSON report')
    parser.add_argument('--strict-advisory', action='store_true',
                        help='escalate advisory findings to failures')
    args = parser.parse_args(argv)

    try:
        report = evaluate(args)
    except InputError as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else Path(args.case) / 'gate-report.json'
    try:
        write_json(str(out_path), report)
    except (OSError, ValueError) as exc:
        print('error: could not write report %s: %s' % (out_path, exc),
              file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report))
    return EXIT_CODES[report['status']]


if __name__ == '__main__':
    sys.exit(main())
