"""Layered quality evaluation and candidate comparison.

The module keeps three questions separate:

* **hard** -- did the board violate a hard constraint: a real schematic/PCB
  DRC error, a schematic-to-PCB (or intent) pad-net mismatch, an
  outline/locked/keepout violation, a hard finding reported by the schematic
  audit, or a hard rule explicitly declared by the caller?
* **engineering** -- did measured DFM/electrical checks report a deterministic
  defect (confirmed issue) or a condition-dependent risk that needs a
  re-check?  PCB ``check`` findings, ``design_engine.critical`` findings,
  power/return/thermal/sensitive-node checks carried by the observation and
  caller-declared engineering rules all land here.
* **readability** -- are texts/attributes overlapping, labels folded or
  reversed, parts too far apart, or the drawing outside its frame?  These are
  suggestions only and can never block a design or offset a hard failure.

There is deliberately no total score.  ``verdict`` is derived from layer
status in a fixed order: hard failure wins, an unknown required input cannot
be reported as a pass, engineering findings produce ``pass_with_warnings``,
and only a fully measured clean board is ``pass``.

Expected observation layout (all keys optional except when a section is
present; the module never guesses a missing DRC result)::

    {
      "project": {"uuid": ..., "name": ...},
      "documents": [...],
      "schematic": {
         "document_uuid": ...,
         "drc": {...},                 # required when this section exists
         "audit": {...},               # optional schematic audit output
         "readability": {...},         # optional readability findings/score
         "pad_net": {...},             # optional SCH<->PCB comparison
         "components": [...],          # optional raw pins for pad-net check
         "sensitive_nodes": [...]      # optional engineering checks
      },
      "pcb": {
         "document_uuid": ...,
         "drc": {...},                 # required when this section exists
         "check": {...},               # pcb check findings/summary
         "critical": {...},            # critical-pin distance findings
         "outline": {...}, "locked": {...}, "keepout": {...},
         "power_paths": [...], "return_paths": [...],
         "thermal": [...], "sensitive_nodes": [...],
         "components": [...],          # optional raw pads for pad-net check
         "pad_net": {...}
      },
      "drc": {...},                    # accepted when no section DRC exists
      "readability": {...},
      "engineering_checks": {...},
      "unknown": [{"field": ..., "reason": ...}]
    }

DRC payloads may be raw CLI envelopes (``{"ok": true, "result": {...}}``) or
normalised results.  A result is a pass only when the source says so and no
fatal/error count or error-level violation contradicts it.  ``not_run``,
``unknown``, ``blocked``, a missing key or an unreadable payload stay unknown;
they are never converted to pass.

``compare_candidates`` compares already-evaluated candidates.  Hard failures
are rejected first; a candidate that is worse than the reference on a key
metric beyond the declared tolerance is rejected even when its drawing is
neater.  Selection is lexicographic over an explicit objective, not a sum.
Rejection entries carry machine-readable reason codes: ``hard_violation``,
``path_regression``, ``scope_regression``, ``metric_regression`` and
``unknown_metric``.
"""
from __future__ import annotations

import math
import re

try:  # package import (feedback.evaluate)
    from . import schemas
except ImportError:  # pragma: no cover - flat import used by tests/tools
    import schemas

try:  # optional: the observation layer already ships this parser
    import pcb_evidence as _pcb_evidence
except ImportError:  # pragma: no cover - flat test layout
    _pcb_evidence = None

# ---------------------------------------------------------------------------
# finding vocabulary
# ---------------------------------------------------------------------------

#: Finding codes that belong to the schematic readability layer even when the
#: source declared them "hard" (audit.py marks text overlaps as hard geometry;
#: this contract makes them advisory, as required for readability).
READABILITY_CODES = frozenset({
    'text-overlap',
    'text-component-overlap',
    'text-attribute-overlap',
    'attribute-overlap',
    'attribute-text-overlap',
    'label-overlap',
    'label-proximity',
    'net-label-overlap',
    'net-label-over-text',
    'net-label-over-component',
    'folded-label',
    'folded-labels',
    'reversed-label',
    'reversed-labels',
    'proximity',
    'frame-fit',
    'frame-overflow',
    'text-outside-frame',
    'outside-page',
    'outside-inner-border',
    'title-block-overlap',
    'off-grid',
    'body-tight-spacing',
    'wire-enters-text',
    'wire-touches-text-bbox',
    'different-named-wires-cross',
    'missing-partition',
    'readability-proximity',
    'readability-frame-fit',
})

#: Readability codes whose finding is a measurement (deterministic) rather
#: than a taste judgement.  Advisory either way.
READABILITY_HEURISTIC = frozenset({
    'proximity', 'readability-proximity', 'frame-fit', 'readability-frame-fit',
    'missing-partition',
})

#: Hard-layer finding codes produced by this module.
HARD_CODES = frozenset({
    'drc-violation',
    'drc-failed',
    'pad-net-mismatch',
    'pad-net-intent-mismatch',
    'pad-net-intent-missing',
    'outline-violation',
    'locked-violation',
    'locked-object-moved',
    'keepout-violation',
    'hard-rule',
})

#: Engineering finding codes that are measured facts.  No threshold is
#: invented here: the source (pcb check, critical checks, an explicit rule)
#: supplies the measurement and the limit.
ENGINEERING_DETERMINISTIC = frozenset({
    'decap-too-far',
    'decap-too-far-bulk',
    'power-not-poured',
    'gnd-not-poured',
    'width-under-spec',
    'width-mismatch',
    'dangling-end',
    'dangling-ends',
    'acute-angle',
    'acute-angles',
    'floating-island',
    'floating-islands',
    'floating-track-island',
    'floating-track-islands',
    'connector-plug-clearance',
    'connector-mating-blocked',
    'connector-opening-inward',
    'connector-escape',
    'via-in-pad',
    'netless-via-in-pad',
    'overlapping-via',
    'single-layer-via',
    'duplicate-segment',
    'silk-over-pad',
    'silk-off-board',
    'copper-near-edge',
    'via-crosses-plane',
    'zone-violation',
    'internal-on-edge',
    'non-orthogonal',
    'track-over-pad',
    'fiducial-missing',
    'hole-to-copper',
    'drill-to-copper',
    'netless-pour',
    'critical-decoupling-far',
    'critical-protection-far',
    'critical-crystal-far',
    'critical-feedback-far',
    'body-overlap',
    'wire-enters-component',
    'dangling-wire-endpoint',
    'pin-multiple-nets',
    'label-net-mismatch',
    'label-anchor-off-connection',
    'net-label-wire-name-mismatch',
    'module-frames-overlap',
    'pin-reconciliation-pin-net-mismatch',
    'pin-reconciliation-nc-pin-connected',
    'pin-reconciliation-pin-net-without-connection',
    'pin-reconciliation-nc-pin-has-net',
})

#: Engineering codes whose meaning depends on context the observation does
#: not carry (stackup, current, return path, intended function).
ENGINEERING_HEURISTIC = frozenset({
    'parallel-coupling',
    'crosstalk',
    'antenna-keepout',
    'thermal',
    'thermal-relief',
    'return-path',
    'power-path',
    'current-density',
    'sensitive-node',
    'sensitive-nodes',
    'emc',
    'si',
    'pi',
    'pcb-check-summary-only',
    'pcb-check-summary-gap',
    'pcb-check-failed-without-findings',
    'drc-warning',
})

_HARD_TOKENS = frozenset({
    'pass', 'passed', 'ok', 'true', 'success', 'succeeded', 'clean', 'match',
    'matched', 'good',
})
_FAIL_TOKENS = frozenset({
    'fail', 'failed', 'failure', 'error', 'errors', 'violation', 'violations',
    'mismatch', 'mismatched', 'bad', 'reject', 'rejected',
})
_WARN_TOKENS = frozenset({'warn', 'warning', 'warnings', 'review', 'degraded'})
_UNKNOWN_TOKENS = frozenset({
    'unknown', 'not-run', 'notrun', 'unavailable', 'pending', 'unmeasured',
    'incomplete', 'blocked', 'timeout', 'skipped', 'none', 'null', 'ran',
    'not-comparable', 'not-compared',
})

_KEY_METRICS = {
    'hpwl': 'hpwl',
    'half-perimeter-wire-length': 'hpwl',
    'wire-length': 'hpwl',
    'ratsnest': 'hpwl',
    'crossings': 'crossings',
    'crossing': 'crossings',
    'decap-distance': 'decap_distance',
    'decap-distance-mil': 'decap_distance',
    'decap-far': 'decap_distance',
    'keepout-usage': 'keepout_usage',
    'keepout-area': 'keepout_usage',
    'keepout-utilization': 'keepout_usage',
    'track-count': 'track_count',
    'track-count-total': 'track_count',
    'tracks': 'track_count',
    'net-path': 'net_path',
    'net-paths-found': 'net_paths_found',
    'net-path-found': 'net_paths_found',
    'net-paths-missing': 'net_paths_missing',
    'missing-net-paths': 'net_paths_missing',
    'net-path-missing': 'net_paths_missing',
}

_METRIC_DIRECTIONS = {
    'hpwl': 'minimize',
    'crossings': 'minimize',
    'decap_distance': 'minimize',
    'keepout_usage': 'minimize',
    'track_count': 'minimize',
    'net_path': 'maximize',
    'net_paths_found': 'maximize',
    'net_paths_missing': 'minimize',
}

_PATH_METRICS = frozenset({'net_path', 'net_paths_found', 'net_paths_missing'})

_READABILITY_DIMS = frozenset({
    'folded-labels', 'reversed-labels', 'proximity', 'frame-fit',
    'text-overlap', 'attribute-overlap', 'label-overlap',
})


# ---------------------------------------------------------------------------
# small normalisers
# ---------------------------------------------------------------------------

def _status_token(value):
    """Map a source status to ``pass``/``fail``/``warn``/``unknown``."""
    if value is True:
        return 'pass'
    if value is False:
        return 'fail'
    if not isinstance(value, str):
        return None
    token = value.strip().lower().replace('_', '-').replace(' ', '-')
    if token in _HARD_TOKENS:
        return 'pass'
    if token in _FAIL_TOKENS:
        return 'fail'
    if token in _WARN_TOKENS:
        return 'warn'
    if token in _UNKNOWN_TOKENS:
        return 'unknown'
    return None


def _bool_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in ('true', 'yes', '1'):
            return True
        if token in ('false', 'no', '0'):
            return False
    return None


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_code(value):
    """Return a stable dashed-lower spelling of a finding code."""
    text = _text(str(value)) if value is not None else None
    if not text:
        return 'unknown'
    if text.startswith('finding:'):
        parts = text.split(':')
        if len(parts) > 1 and parts[1]:
            text = parts[1]
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', text)
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()
    return text or 'unknown'


def _code_of(finding, prefer=None):
    if not isinstance(finding, dict):
        return 'unknown'
    order = ('code', 'type', 'rule', 'id')
    if prefer:
        order = (prefer,) + tuple(key for key in order if key != prefer)
    for key in order:
        value = finding.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_code(value)
    return 'unknown'


def _severity(finding):
    if not isinstance(finding, dict):
        return schemas.SEVERITY_UNKNOWN
    for key in ('severity', 'level'):
        value = finding.get(key)
        if not isinstance(value, str):
            continue
        token = value.strip().lower()
        if token in schemas.SEVERITIES:
            return token
        if token in ('fatal', 'error', 'critical', 'fail', 'failed', 'blocking'):
            return schemas.SEVERITY_BLOCKING
        if token in ('warn', 'warning', 'major'):
            return schemas.SEVERITY_MAJOR
        if token in ('minor', 'moderate'):
            return schemas.SEVERITY_MINOR
        if token in ('info', 'information', 'advisory', 'hint', 'note'):
            return schemas.SEVERITY_INFO
    return schemas.SEVERITY_UNKNOWN


def _explicit_deterministic(finding):
    if not isinstance(finding, dict):
        return None
    for key in ('deterministic', 'is_deterministic'):
        if isinstance(finding.get(key), bool):
            return finding[key]
    basis = finding.get('basis')
    if isinstance(basis, dict) and isinstance(basis.get('deterministic'), bool):
        return basis['deterministic']
    if finding.get('heuristic') is True:
        return False
    if finding.get('scope') == 'hard':
        return True
    confidence = finding.get('confidence')
    if confidence == 'deterministic':
        return True
    if confidence in ('heuristic', 'name-only', 'structural', 'incomplete'):
        return False
    return None


def _basis_text(finding, code, layer, deterministic):
    if isinstance(finding, dict):
        basis = finding.get('basis')
        if isinstance(basis, str) and basis.strip():
            return basis.strip()
        if isinstance(basis, dict):
            reason = _text(basis.get('reason') or basis.get('method'))
            if reason:
                return reason
    if layer == schemas.LAYER_HARD:
        return 'hard input violation reported by the observation or a declared rule'
    if layer == schemas.LAYER_READABILITY:
        return 'schematic readability measurement; advisory only, never blocking'
    if deterministic:
        return 'measured DFM/electrical finding; the source supplies the limit'
    if code in ENGINEERING_HEURISTIC:
        return ('condition-dependent engineering risk; its interpretation needs '
                'stackup/current/return-path or intent evidence not present here')
    return ('unclassified finding code; treated as conditional until a rule or '
            'measurement is supplied')


_RECHECK_BY_CODE = {
    'decap-too-far': (
        're-check after moving the capacitor or changing the declared '
        'decoupling limit'),
    'power-not-poured': 're-check after creating/refreshing the pour and reading back pour-list',
    'gnd-not-poured': 're-check after creating/refreshing the ground pour and reading it back',
    'width-under-spec': 're-check after widening the track and re-running the source check',
    'width-mismatch': 're-check after reconciling the track width with the net class',
    'dangling-end': 're-check after removing or terminating the track end',
    'acute-angle': 're-check after rerouting the corner',
    'floating-island': 're-check after deleting or connecting the isolated copper',
    'floating-track-island': 're-check after deleting or connecting the isolated copper',
    'parallel-coupling': 're-check after measuring the coupled length and the actual stackup',
    'netless-pour': 're-check after confirming the pour is intentional and net-assigned',
    'antenna-keepout': 're-check after measuring the antenna keepout against its declared rule',
    'connector-plug-clearance': (
        're-check after moving the connector or obstacle and re-running the '
        'source check'),
    'connector-mating-blocked': (
        're-check after clearing the mating path and re-running the source '
        'check'),
    'connector-opening-inward': (
        're-check after rotating/moving the connector and re-running the '
        'source check'),
}


def _recheck_text(finding, code, deterministic):
    if isinstance(finding, dict):
        for key in ('recheck', 'recheck_condition', 'condition'):
            value = _text(finding.get(key))
            if value:
                return value
        improvement = finding.get('improvement')
        if isinstance(improvement, dict):
            predicate = _text(improvement.get('predicate'))
            if predicate:
                return predicate
    if deterministic:
        return None
    if code in _RECHECK_BY_CODE:
        return _RECHECK_BY_CODE[code]
    if code.startswith('connector-'):
        return ('re-check after moving the connector/obstacle and re-running the '
                'source check')
    return ('re-check after supplying the missing measurement/rule and '
            're-running the source check')


def classify_finding(finding):
    """Classify one finding without inventing a threshold.

    The result names the layer, whether the source makes the finding
    deterministic, the source severity (or ``unknown``), whether it blocks,
    the basis and -- for conditional findings -- a re-check condition.
    Readability findings are never blocking.
    """
    finding = finding if isinstance(finding, dict) else {}
    code = _code_of(finding)

    explicit_layer = _text(finding.get('layer'))
    explicit_layer = explicit_layer.lower() if explicit_layer else None
    if explicit_layer not in schemas.LAYERS:
        explicit_layer = None

    if explicit_layer:
        layer = explicit_layer
    elif code in READABILITY_CODES:
        layer = schemas.LAYER_READABILITY
    elif code.startswith('critical-'):
        # critical.py uses scope="hard" for a constraint strength, not for the
        # evaluation layer: a far decoupling cap is an engineering finding.
        layer = schemas.LAYER_ENGINEERING
    elif code in HARD_CODES or finding.get('scope') == 'hard':
        layer = schemas.LAYER_HARD
    else:
        layer = schemas.LAYER_ENGINEERING

    severity = _severity(finding)
    explicit = _explicit_deterministic(finding)
    if explicit is not None:
        deterministic = explicit
    elif layer == schemas.LAYER_HARD:
        deterministic = True
    elif layer == schemas.LAYER_READABILITY:
        deterministic = code not in READABILITY_HEURISTIC
    elif code in ENGINEERING_DETERMINISTIC:
        deterministic = True
    else:
        deterministic = False

    if layer == schemas.LAYER_READABILITY and severity == schemas.SEVERITY_UNKNOWN:
        severity = schemas.SEVERITY_INFO

    basis = _basis_text(finding, code, layer, deterministic)
    recheck = _recheck_text(finding, code, deterministic)
    if layer == schemas.LAYER_HARD:
        status = 'hard_violation'
        blocking = True
    elif layer == schemas.LAYER_READABILITY:
        status = 'suggestion'
        blocking = False
    elif deterministic:
        status = 'confirmed_issue'
        blocking = False
    else:
        status = 'conditional_risk'
        blocking = False

    return {
        'code': code,
        'layer': layer,
        'deterministic': deterministic,
        'severity': severity,
        'status': status,
        'blocking': blocking,
        'basis': basis,
        'recheck': recheck,
    }


def _rulebook(rules):
    """Normalise the ``rules`` argument into (classifier specs, declarations).

    Accepted shapes::

        [{"id": "R1", "layer": "hard", "status": "fail", ...}, ...]
        {"rules": [...]}
        {"decap-too-far": {"severity": "major", "deterministic": true}}
        {"hard": [...], "engineering": [...], "readability": [...]}
    """
    entries = []
    if isinstance(rules, list):
        entries = [item for item in rules if isinstance(item, dict)]
    elif isinstance(rules, dict):
        if isinstance(rules.get('rules'), list):
            entries = [item for item in rules['rules'] if isinstance(item, dict)]
        else:
            for group in schemas.LAYERS:
                value = rules.get(group)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            entry = dict(item)
                            entry.setdefault('layer', group)
                            entries.append(entry)
            for key, value in rules.items():
                if key in schemas.LAYERS or key == 'rules':
                    continue
                if isinstance(value, dict):
                    entry = dict(value)
                    entry.setdefault('code', key)
                    entries.append(entry)
    specs, declared = {}, []
    for entry in entries:
        code = entry.get('code') or entry.get('id')
        if code:
            specs[_normalize_code(code)] = entry
        if (entry.get('status') is not None or entry.get('passed') is not None
                or entry.get('findings') or entry.get('violations')):
            declared.append(entry)
    return specs, declared


def _classify_with_rules(finding, specs):
    result = classify_finding(finding)
    spec = specs.get(result['code']) if specs else None
    if not spec:
        return result
    if spec.get('layer') in schemas.LAYERS:
        result['layer'] = spec['layer']
    if isinstance(spec.get('deterministic'), bool):
        result['deterministic'] = spec['deterministic']
    severity = spec.get('severity')
    if severity in schemas.SEVERITIES:
        result['severity'] = severity
    if _text(spec.get('basis')):
        result['basis'] = spec['basis'].strip()
    if _text(spec.get('recheck')):
        result['recheck'] = spec['recheck'].strip()

    layer = result['layer']
    if layer == schemas.LAYER_HARD:
        result['status'] = 'hard_violation'
        result['blocking'] = True
    elif layer == schemas.LAYER_READABILITY:
        result['status'] = 'suggestion'
        result['blocking'] = False
    elif result['deterministic']:
        result['status'] = 'confirmed_issue'
        result['blocking'] = False
    else:
        result['status'] = 'conditional_risk'
        result['blocking'] = False
    if layer == schemas.LAYER_READABILITY and \
            result['severity'] == schemas.SEVERITY_UNKNOWN:
        result['severity'] = schemas.SEVERITY_INFO
    return result


# ---------------------------------------------------------------------------
# finding / issue materialisation
# ---------------------------------------------------------------------------

def _message(finding):
    if isinstance(finding, str):
        return finding
    if not isinstance(finding, dict):
        return ''
    for key in ('message', 'description', 'reason', 'note', 'rule'):
        value = _text(finding.get(key))
        if value:
            return value
    return ''


def _objects(finding):
    if not isinstance(finding, dict):
        return []
    raw = finding.get('objects')
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, (str, int, float))]
    objects = []
    for key in ('designator', 'ref', 'pin', 'pad', 'net', 'object'):
        value = finding.get(key)
        if isinstance(value, (str, int, float)):
            objects.append(value)
    return objects


def _finding_record(classification, raw, source, index):
    return {
        'id': 'finding:%s:%d' % (source, index),
        'code': classification['code'],
        'layer': classification['layer'],
        'severity': classification['severity'],
        'deterministic': classification['deterministic'],
        'blocking': classification['blocking'],
        'message': _message(raw) or classification['code'],
        'objects': _objects(raw),
        'evidence': {'source': source, 'finding': raw},
        'basis': classification['basis'],
        'recheck': classification['recheck'],
        'source': source,
    }


def _dedupe(records):
    result, seen = [], set()
    for record in records:
        key = (record.get('code'), tuple(str(item) for item in
                                         record.get('objects') or []),
               record.get('message'))
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _assign_ids(records, prefix):
    for index, record in enumerate(records, start=1):
        record['id'] = '%s:%d' % (prefix, index)
    return records


def _issue_from_record(record, target, index):
    """Build a schema-valid issue from a confirmed/conditional record."""
    deterministic = bool(record['deterministic'])
    if deterministic:
        basis = {'deterministic': True,
                 'reason': record['basis'],
                 'source': record.get('source')}
    else:
        basis = {'heuristic': record['basis'],
                 'source': record.get('source')}
    evidence = record.get('evidence') or {'source': record.get('source')}
    original_id = _text(record.get('source_id')) \
        if record.get('source') == 'issues' else None
    issue_id = original_id or 'auto-%s-%d' % (record['code'], index)
    issue = schemas.new_issue(
        issue_id=issue_id,
        target=target,
        description=record['message'],
        basis=basis,
        severity=record['severity'],
        evidence=[evidence],
        status='open',
    )
    schemas.validate_issue(issue)
    issue['layer'] = record['layer']
    issue['code'] = record['code']
    issue['recheck'] = record.get('recheck')
    issue['source'] = record.get('source')
    for key in ('role', 'role_basis', 'auto_action_allowed'):
        if key in record:
            issue[key] = record[key]
    return issue


# ---------------------------------------------------------------------------
# DRC normalisation
# ---------------------------------------------------------------------------

def _drc_counts(mapping):
    counts = {}
    if not isinstance(mapping, dict):
        return counts
    for key in ('summary', 'counts'):
        value = mapping.get(key)
        if isinstance(value, dict):
            for name, raw in value.items():
                number = _number(raw)
                if number is not None:
                    counts[str(name).strip().lower()] = number
    for key in ('fatal', 'error', 'errors', 'warn', 'warning', 'warnings',
                'info', 'total', 'unknown'):
        number = _number(mapping.get(key))
        if number is not None and key not in counts:
            counts[key] = number
    return counts


def _category_sum(counts, tokens):
    total = 0.0
    found = False
    for key, value in counts.items():
        if any(token in key for token in tokens):
            total += value
            found = True
    return total if found else None


def _first_value(result, data, keys):
    for key in keys:
        if isinstance(result, dict) and key in result:
            return result.get(key)
        if isinstance(data, dict) and key in data:
            return data.get(key)
    return None


def _violation_list(mapping):
    if not isinstance(mapping, dict):
        return []
    for key in ('violations', 'findings', 'items'):
        value = mapping.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {'message': str(item)}
                    for item in value if isinstance(item, (dict, str))]
    return []


def _violation_severity(finding):
    severity = _severity(finding)
    if severity != schemas.SEVERITY_UNKNOWN:
        return severity
    label = ' '.join(str(finding.get(key, '')) for key in
                     ('rule', 'ruleName', 'type', 'category')).lower()
    if 'fatal' in label:
        return schemas.SEVERITY_BLOCKING
    if 'error' in label:
        return schemas.SEVERITY_BLOCKING
    if 'warn' in label:
        return schemas.SEVERITY_MAJOR
    if 'info' in label or 'note' in label:
        return schemas.SEVERITY_INFO
    return schemas.SEVERITY_UNKNOWN


def _missing_drc(where, reason):
    return {'where': where, 'present': False, 'state': 'unknown',
            'findings': [], 'warnings': [], 'reason': reason,
            'evidence': {}}


def _drc_entry(where, data):
    entry = {'where': where, 'present': data is not None,
             'state': 'unknown', 'findings': [], 'warnings': [],
             'reason': None, 'evidence': {}}
    if data is None:
        entry['reason'] = 'DRC input is null'
        return entry
    if not isinstance(data, dict):
        entry['reason'] = 'DRC input is not an object'
        entry['evidence'] = {'value': repr(data)}
        return entry

    result = data.get('result') if isinstance(data.get('result'), dict) else data
    parsed_report = any(key in data for key in
                        ('schema', 'measured', 'parser_version', 'passed'))
    if data.get('ok') is False and result is data and not parsed_report:
        entry['reason'] = 'DRC envelope reported ok=false'
        entry['evidence'] = {'error': data.get('error') or data.get('message')}
        return entry

    counts = _drc_counts(result)
    if not counts:
        counts = _drc_counts(data)
    violations = _violation_list(result) or _violation_list(data)
    native = result.get('nativeResult') if isinstance(result, dict) else None
    if not violations and isinstance(native, dict):
        violations = _violation_list(native)

    status = _status_token(_first_value(
        result, data, ('status', 'state', 'verdict')))
    passed = _bool_value(_first_value(
        result, data, ('passed', 'nativePassed')))
    counts_available = _bool_value(_first_value(
        result, data, ('countsAvailable', 'counts_available')))
    measured = _bool_value(_first_value(
        result, data, ('measured',)))
    connection = _number(_first_value(
        result, data, ('connection_violations', 'connectionViolations'))) or 0.0
    contradictions = _first_value(
        result, data, ('contradictions',))
    if not isinstance(contradictions, list):
        contradictions = []
    ok_value = _bool_value(_first_value(result, data, ('ok',)))

    fatal = counts.get('fatal')
    if fatal is None:
        fatal = _category_sum(counts, ('fatal',))
    error = counts.get('error', counts.get('errors'))
    if error is None:
        error = _category_sum(counts, ('error',))
    warn = counts.get('warn', counts.get('warning', counts.get('warnings')))
    if warn is None:
        warn = _category_sum(counts, ('warn',))
    info = counts.get('info')
    if info is None:
        info = _category_sum(counts, ('info',))
    total = counts.get('total')
    error_like = (fatal or 0.0) + (error or 0.0) + connection

    graded = [(_violation_severity(item), item) for item in violations]
    blocking_items = [item for severity, item in graded
                      if severity == schemas.SEVERITY_BLOCKING]
    warning_items = [item for severity, item in graded
                     if severity in (schemas.SEVERITY_MAJOR,
                                     schemas.SEVERITY_MINOR,
                                     schemas.SEVERITY_INFO)]
    unknown_items = [item for severity, item in graded
                     if severity == schemas.SEVERITY_UNKNOWN]
    known_severity = any(value is not None
                         for value in (fatal, error, warn, info))

    if measured is False:
        state = 'unknown'
        entry['reason'] = 'DRC report says it is not a measurement'
    elif counts_available is False and passed is None and status is None:
        state = 'unknown'
        entry['reason'] = 'DRC reports countsAvailable=false without a pass/fail verdict'
    elif error_like > 0:
        state = 'fail'
    elif passed is False:
        # A strict DRC can report passed=false for warnings only.  With a
        # complete count table and no error count, keep the hard layer pass and
        # record the warnings; otherwise the explicit failure stands.
        if counts and error_like == 0 and (warn or 0) > 0 and not blocking_items:
            state = 'pass'
            entry['reason'] = 'source failed only on warnings; no fatal/error count'
        elif violations and not blocking_items and counts and error_like == 0:
            state = 'pass'
            entry['reason'] = 'source failed only on non-error violations'
        else:
            state = 'fail'
    elif status == 'fail':
        state = 'fail'
    elif passed is True:
        state = 'fail' if blocking_items else 'pass'
    elif status == 'pass':
        state = 'fail' if blocking_items else 'pass'
    elif status == 'warn':
        state = 'fail' if blocking_items else 'pass'
    elif counts and error_like == 0 and known_severity:
        state = 'fail' if blocking_items else 'pass'
    elif counts and total == 0:
        state = 'pass'
    elif violations:
        state = 'fail' if blocking_items else 'pass'
    else:
        state = 'unknown'
        entry['reason'] = ('DRC input has no usable passed/status/counts '
                           'verdict')

    if contradictions or ok_value is False:
        # A self-contradictory receipt (or one the native parser refused) is
        # not clean even when the passed flag says so.
        if state == 'pass':
            state = 'fail'
        if state == 'fail':
            entry['reason'] = 'DRC receipt is internally inconsistent'
            entry['findings'].append({
                'code': 'drc-contradiction',
                'severity': schemas.SEVERITY_BLOCKING,
                'message': 'DRC receipt contradicts itself: %s'
                           % ('; '.join(str(item) for item in contradictions[:3])
                              or 'native parser marked ok=false'),
                'evidence': {'counts': counts,
                             'contradictions': contradictions},
                'rule': 'drc',
                'objects': [],
            })
    elif state == 'pass' and unknown_items:
        # A violation the source did not grade cannot be called clean.
        state = 'unknown'
        entry['reason'] = ('DRC lists %d violation(s) without a recognised '
                           'severity' % len(unknown_items))

    entry['state'] = state
    entry['evidence'] = {
        'counts': counts,
        'passed': passed,
        'status': status,
        'violations': len(violations),
    }
    if connection:
        entry['evidence']['connection_violations'] = connection
    if contradictions:
        entry['evidence']['contradictions'] = list(contradictions)
    if counts_available is False:
        entry['evidence']['counts_available'] = False

    if state == 'fail':
        hard_items = blocking_items + unknown_items
        if not hard_items and not entry['findings']:
            entry['findings'].append({
                'code': 'drc-failed',
                'severity': schemas.SEVERITY_BLOCKING,
                'message': 'DRC reported a failure without error-level itemised '
                           'violations',
                'evidence': entry['evidence'],
                'rule': 'drc',
                'objects': [],
            })
        for item in hard_items:
            severity = _violation_severity(item)
            rule = _text(item.get('rule') or item.get('ruleName') or
                         item.get('type')) or 'violation'
            record = dict(item)
            record.setdefault('severity', severity)
            record.setdefault('message',
                              'DRC violation: %s' % rule)
            record['rule'] = rule
            record['code'] = 'drc-' + _normalize_code(rule)
            entry['findings'].append(record)
    elif state == 'pass':
        for item in blocking_items:
            # A pass verdict contradicted by error-level items is a failure.
            severity = _violation_severity(item)
            rule = _text(item.get('rule') or item.get('type')) or 'violation'
            record = dict(item)
            record.setdefault('severity', severity)
            record.setdefault('message', 'DRC violation: %s' % rule)
            record['rule'] = rule
            record['code'] = 'drc-' + _normalize_code(rule)
            entry['findings'].append(record)
        if entry['findings']:
            entry['state'] = 'fail'

    if entry['state'] == 'pass':
        for item in warning_items:
            record = dict(item)
            record.setdefault('severity', _violation_severity(item))
            record.setdefault('message', 'DRC warning')
            rule = _text(item.get('rule') or item.get('type')) or 'warning'
            record['code'] = 'drc-warning-' + _normalize_code(rule)
            entry['warnings'].append(record)
        if (warn or 0) > 0 and not warning_items:
            entry['warnings'].append({
                'code': 'drc-warning',
                'severity': schemas.SEVERITY_MAJOR,
                'message': 'DRC reported %d warning(s) without itemised detail'
                           % int(warn),
                'count': int(warn),
            })
    return entry


def _drc_entries(observation):
    observation = observation if isinstance(observation, dict) else {}
    entries = []
    for name in ('schematic', 'pcb'):
        section = observation.get(name)
        if not isinstance(section, dict) or not section:
            continue
        found = False
        for key in ('drc', 'erc', 'native_drc'):
            if key in section:
                entries.append(_drc_entry('%s.%s' % (name, key),
                                          section.get(key)))
                found = True
        if not found:
            entries.append(_missing_drc(
                '%s.drc' % name,
                'required %s DRC input is missing' % name))

    top = observation.get('drc')
    if isinstance(top, dict):
        nested = {name: top.get(name) for name in ('schematic', 'pcb')
                  if name in top}
        if nested:
            for name, data in nested.items():
                if any(item['where'].startswith(name + '.') and item['present']
                       for item in entries):
                    continue
                entries = [item for item in entries
                           if item['where'] != '%s.drc' % name]
                entries.append(_drc_entry('drc.%s' % name, data))
        elif not any(item['where'] in ('schematic.drc', 'pcb.drc')
                     for item in entries):
            entries.append(_drc_entry('drc', top))
    if not entries:
        entries.append(_missing_drc('drc', 'no DRC input was supplied'))
    return entries


# ---------------------------------------------------------------------------
# pad-net identity
# ---------------------------------------------------------------------------

def _pad_net_finding(source, item, kind=None):
    if not isinstance(item, dict):
        item = {'message': str(item)}
    kind = kind or item.get('kind') or item.get('type') or 'mismatch'
    code = 'pad-net-mismatch'
    if kind not in ('mismatch', 'pad-net-mismatch', 'pad_net_mismatch'):
        code = 'pad-net-' + _normalize_code(kind)
    severity = _severity(item)
    if severity == schemas.SEVERITY_UNKNOWN:
        severity = schemas.SEVERITY_UNKNOWN
    record = dict(item)
    record.setdefault('severity', severity)
    record.setdefault('message', 'pad/net mismatch (%s)' % kind)
    record['code'] = code
    record['_source'] = source
    return record


def _pad_net_source(source, value):
    findings, unknown, present = [], [], False
    if value is None:
        return findings, unknown, present
    present = True
    if isinstance(value, list):
        for item in value:
            findings.append(_pad_net_finding(source, item))
        return findings, unknown, present
    if not isinstance(value, dict):
        unknown.append({'field': source,
                        'reason': 'pad-net evidence is not an object or list'})
        return findings, unknown, present

    status = _status_token(_first_value(value, value,
                                        ('status', 'state', 'verdict')))
    passed = _bool_value(_first_value(value, value, ('passed', 'ok', 'match')))
    mismatches = []
    for key in ('mismatches', 'findings', 'issues', 'component_mismatches'):
        candidate = value.get(key)
        if isinstance(candidate, list):
            mismatches.extend(item for item in candidate if isinstance(item, dict))
    rows = value.get('rows')
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and _status_token(row.get('status')) == 'fail':
                mismatches.append(row)

    if mismatches:
        for item in mismatches:
            findings.append(_pad_net_finding(source, item))
        return findings, unknown, present
    if status == 'unknown' or (passed is None and status is None and
                               value.get('not_comparable')):
        unknown.append({'field': source,
                        'reason': 'pad-net comparison is unknown/not comparable'})
        return findings, unknown, present
    if status == 'fail' or passed is False:
        findings.append(_pad_net_finding(source, {
            'message': 'pad-net comparison reported mismatch without itemised rows',
            'evidence': value,
        }))
    return findings, unknown, present


def _raw_pin_nets(section):
    result = {}
    if not isinstance(section, dict):
        return result
    components = section.get('components')
    if not isinstance(components, list):
        return result
    for component in components:
        if not isinstance(component, dict):
            continue
        ref = _text(component.get('designator') or component.get('ref') or
                    component.get('name'))
        if not ref:
            continue
        pins = component.get('pins')
        if not isinstance(pins, list):
            pins = component.get('pads')
        if not isinstance(pins, list):
            continue
        for pin in pins or []:
            if not isinstance(pin, dict):
                continue
            number = pin.get('number')
            if number is None:
                number = pin.get('padNumber')
            if number is None:
                number = pin.get('name')
            if number is None:
                continue
            net = pin.get('net')
            if net is None:
                net = pin.get('netName')
            if net is None:
                net = pin.get('net_name')
            if isinstance(net, dict):
                net = net.get('name')
            result.setdefault((str(ref), str(number)), set()).add(
                _text(net) if isinstance(net, str) else None)
    return result


def _net_partition_roots(pin_nets):
    """Union shared pins by net; returns ``{pin_key: partition_root_key}``."""
    parent = {key: key for key in pin_nets}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(first, second):
        left, right = find(first), find(second)
        if left != right:
            parent[right] = left

    by_net = {}
    for key, nets in pin_nets.items():
        for net in nets:
            if net:
                by_net.setdefault(net, []).append(key)
    for members in by_net.values():
        for member in members[1:]:
            union(members[0], member)
    return {key: find(key) for key in pin_nets}


def _raw_pad_net_mismatches(schematic, pcb):
    """Compare net *partitions* when pcb_evidence is unavailable.

    A consistent net rename keeps the partition and is not a mismatch; two
    pins grouped on one side and separated on the other are.  Missing
    components/pads are left to ``pcb_evidence`` (this fallback does not claim
    them).
    """
    findings = []
    sch_nets = _raw_pin_nets(schematic)
    pcb_nets = _raw_pin_nets(pcb)
    if not sch_nets or not pcb_nets:
        return findings
    shared = sorted(key for key in set(sch_nets) & set(pcb_nets)
                    if any(sch_nets[key]) and any(pcb_nets[key]))
    if len(shared) < 2:
        return findings
    sch_roots = _net_partition_roots(sch_nets)
    pcb_roots = _net_partition_roots(pcb_nets)
    for index, first in enumerate(shared):
        for second in shared[index + 1:]:
            if (sch_roots[first] == sch_roots[second]) == \
                    (pcb_roots[first] == pcb_roots[second]):
                continue
            findings.append(_pad_net_finding('pad_net.sch_pcb_raw', {
                'designator': first[0],
                'pin': first[1],
                'other_designator': second[0],
                'other_pin': second[1],
                'schematic_nets': sorted(sch_nets[first] | sch_nets[second]),
                'pcb_nets': sorted(pcb_nets[first] | pcb_nets[second]),
                'message': '%s.%s and %s.%s are grouped differently on the '
                           'schematic and the PCB'
                           % (first[0], first[1], second[0], second[1]),
            }, kind='sch_pcb_partition_mismatch'))
    return findings


def _intent_pad_net_mismatches(intent, observation):
    if not isinstance(intent, dict):
        return []
    mapping = (intent.get('pad_net') or intent.get('pin_nets') or
               intent.get('expected_pad_nets'))
    if not isinstance(mapping, dict):
        return []
    schematic = observation.get('schematic') if isinstance(observation, dict) else {}
    actual = _raw_pin_nets(schematic)
    if not actual:
        return []
    findings = []
    for ref, pins in mapping.items():
        if not isinstance(pins, dict):
            continue
        for pin, expected in pins.items():
            nets = actual.get((str(ref), str(pin)))
            if nets is None:
                findings.append(_pad_net_finding('intent.pad_net', {
                    'designator': ref, 'pin': pin, 'expected': expected,
                    'message': '%s.%s is declared by intent but is absent from the schematic'
                               % (ref, pin),
                }, kind='intent_missing'))
                continue
            wanted = _text(expected) if isinstance(expected, str) else expected
            if wanted and {net for net in nets if net} and \
                    wanted not in {net for net in nets if net}:
                findings.append(_pad_net_finding('intent.pad_net', {
                    'designator': ref, 'pin': pin,
                    'expected': wanted, 'actual': sorted(net for net in nets if net),
                    'message': '%s.%s expected net %s but schematic has %s'
                               % (ref, pin, wanted, sorted(net for net in nets if net)),
                }, kind='intent_mismatch'))
    return findings


def _parsed_pad_net(observation):
    """Use the observation layer's SCH/PCB comparison when available.

    ``pcb_evidence.compare_sch_pcb`` distinguishes an electrical mismatch from
    a net rename with an unchanged partition; the local raw fallback only
    compares net names.  Returns ``(findings, unknown, ran)``.
    """
    if _pcb_evidence is None:
        return [], [], False
    schematic = observation.get('schematic')
    pcb = observation.get('pcb')
    if not isinstance(schematic, dict) or not isinstance(pcb, dict):
        return [], [], False
    if not schematic.get('components') or not pcb.get('components'):
        return [], [], False
    aliases = observation.get('pin_aliases')
    if aliases is None:
        aliases = schematic.get('pin_aliases')
    ignored = observation.get('ignore_designators')
    if ignored is None:
        ignored = pcb.get('ignore_designators')
    try:
        result = _pcb_evidence.compare_sch_pcb(
            schematic, pcb, pin_aliases=aliases, ignore_designators=ignored)
    except (TypeError, ValueError):
        return [], [{'field': 'pad_net.sch_pcb',
                     'reason': 'SCH/PCB comparison parser rejected the data'}], True
    status = result.get('status')
    if status == 'mismatch':
        findings = []
        for item in result.get('mismatches') or []:
            if isinstance(item, dict):
                findings.append(_pad_net_finding('pad_net.sch_pcb', item))
        if not findings:
            findings.append(_pad_net_finding('pad_net.sch_pcb', {
                'message': 'SCH/PCB comparison reported a mismatch without '
                           'itemised rows',
                'evidence': {'mismatches': result.get('mismatches')},
            }))
        return findings, [], True
    if status == 'not_comparable':
        coverage = result.get('coverage') or {}
        if coverage.get('schematic_components') and \
                coverage.get('pcb_components'):
            return [], [{'field': 'pad_net.sch_pcb',
                         'reason': result.get('reason') or
                                   'SCH/PCB comparison is not comparable'}], True
        return [], [], True
    return [], [], True


def _pad_net_evidence(observation, intent):
    findings, unknown, checks = [], [], []
    present = False
    observation = observation if isinstance(observation, dict) else {}
    for source, value in (
            ('pad_net', observation.get('pad_net')),
            ('netlist_diff', observation.get('netlist_diff'))):
        items, gaps, seen = _pad_net_source(source, value)
        findings.extend(items)
        unknown.extend(gaps)
        present = present or seen
        if seen:
            checks.append(source)
    for section_name in ('schematic', 'pcb'):
        section = observation.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in ('pad_net', 'netlist_diff', 'pad_net_mismatches'):
            if key not in section:
                continue
            items, gaps, seen = _pad_net_source(
                '%s.%s' % (section_name, key), section.get(key))
            findings.extend(items)
            unknown.extend(gaps)
            present = present or seen
            if seen:
                checks.append('%s.%s' % (section_name, key))

    intent_findings = _intent_pad_net_mismatches(intent, observation)
    if intent_findings:
        findings.extend(intent_findings)
        present = True
        checks.append('intent.pad_net')
    if not present:
        parsed_findings, parsed_unknown, ran = _parsed_pad_net(observation)
        if parsed_findings or parsed_unknown:
            findings.extend(parsed_findings)
            unknown.extend(parsed_unknown)
            present = present or bool(parsed_findings)
            checks.append('pad_net.sch_pcb')
        elif ran:
            present = True
            checks.append('pad_net.sch_pcb')
        else:
            raw = _raw_pad_net_mismatches(observation.get('schematic'),
                                          observation.get('pcb'))
            if raw:
                findings.extend(raw)
                present = True
                checks.append('pad_net.sch_pcb_raw')
    return findings, unknown, checks, present


# ---------------------------------------------------------------------------
# outline / locked / keepout and hard rules
# ---------------------------------------------------------------------------

def _check_state(value):
    """Return (status, items) for a small check object/list/bool."""
    if value is None:
        return None, []
    if isinstance(value, bool):
        return ('pass' if value else 'fail'), []
    if isinstance(value, list):
        return ('fail' if value else 'pass'), [
            item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return 'unknown', []
    status = _status_token(_first_value(value, value,
                                        ('status', 'state', 'verdict')))
    passed = _bool_value(_first_value(value, value, ('passed', 'ok')))
    items = []
    for key in ('violations', 'findings', 'issues'):
        candidate = value.get(key)
        if isinstance(candidate, list):
            items.extend(item for item in candidate if isinstance(item, dict))
    if status is None and passed is not None:
        status = 'pass' if passed else 'fail'
    if status is None:
        status = 'fail' if items else None
    return status, items


_INVARIANTS = {
    'pcb_outline': ('outline', 'outline-violation'),
    'pcb-locked': ('locked', 'locked-violation'),
    'pcb_locked': ('locked', 'locked-violation'),
    'keepout': ('keepout', 'keepout-violation'),
    'pcb_keepout': ('keepout', 'keepout-violation'),
    'outline': ('outline', 'outline-violation'),
    'locked': ('locked', 'locked-violation'),
}


def _looks_like_violation(item):
    if isinstance(item, str):
        return False
    return isinstance(item, dict) and any(
        key in item for key in ('message', 'code', 'kind', 'severity',
                                'violation', 'expected', 'actual', 'rule'))


def _invariant_evidence(observation, intent):
    findings, unknown, checks = [], [], []
    observation = observation if isinstance(observation, dict) else {}
    pcb = observation.get('pcb') if isinstance(observation.get('pcb'), dict) else {}

    for key, code in (
            ('outline', 'outline-violation'),
            ('outline_check', 'outline-violation'),
            ('locked', 'locked-violation'),
            ('locked_check', 'locked-violation'),
            ('keepout', 'keepout-violation'),
            ('keepout_check', 'keepout-violation')):
        if key not in pcb:
            continue
        value = pcb.get(key)
        if isinstance(value, list):
            # ``outline``/``keepout`` can also carry the geometry itself.  A
            # bare point list is not a violation list and must not create a
            # hard failure.
            if not value or not all(_looks_like_violation(item)
                                    for item in value):
                continue
        status, items = _check_state(value)
        label = 'pcb.%s' % key
        if status == 'fail':
            if items:
                for item in items:
                    findings.append(dict(item, code=code,
                                         _source=label))
            else:
                findings.append({'code': code, 'message': '%s check failed' % key,
                                 'severity': schemas.SEVERITY_UNKNOWN,
                                 'evidence': {'value': pcb.get(key)},
                                 '_source': label})
        elif status == 'unknown':
            unknown.append({'field': label,
                            'reason': '%s check state is unknown' % key})
        else:
            checks.append(label)

    for key, code in (
            ('outline_violations', 'outline-violation'),
            ('locked_violations', 'locked-violation'),
            ('keepout_violations', 'keepout-violation')):
        if key not in pcb:
            continue
        value = pcb.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    findings.append(dict(item, code=code,
                                         _source='pcb.%s' % key))
                else:
                    findings.append({'code': code, 'message': str(item),
                                     'severity': schemas.SEVERITY_UNKNOWN,
                                     '_source': 'pcb.%s' % key})
            checks.append('pcb.%s' % key)
        elif value not in (None, False, []):
            findings.append({'code': code, 'message': str(value),
                             'severity': schemas.SEVERITY_UNKNOWN,
                             '_source': 'pcb.%s' % key})

    for key, code in (
            ('outline_ok', 'outline-violation'),
            ('locked_ok', 'locked-violation'),
            ('keepout_ok', 'keepout-violation')):
        if key in pcb:
            ok = _bool_value(pcb.get(key))
            if ok is False:
                findings.append({'code': code,
                                 'message': '%s is false' % key,
                                 'severity': schemas.SEVERITY_UNKNOWN,
                                 '_source': 'pcb.%s' % key})
            elif ok is True:
                checks.append('pcb.%s' % key)
            else:
                unknown.append({'field': 'pcb.%s' % key,
                                'reason': '%s is not a boolean' % key})

    invariants = pcb.get('invariants')
    if isinstance(invariants, list):
        for index, item in enumerate(invariants):
            if not isinstance(item, dict):
                continue
            kind = item.get('kind')
            mapped = _INVARIANTS.get(kind)
            if not mapped:
                continue
            code = mapped[1]
            status, nested = _check_state(item)
            label = 'pcb.invariants[%d]' % index
            if status == 'fail':
                findings.append(dict(item, code=code, _source=label))
            elif status == 'unknown':
                unknown.append({'field': label,
                                'reason': 'invariant %s is unknown' % kind})
            elif status == 'pass':
                checks.append(label)

    fixed = intent.get('fixed') if isinstance(intent, dict) else None
    moved = pcb.get('moved_objects') or pcb.get('moved_locked') or \
        pcb.get('locked_moved')
    if isinstance(moved, list):
        moved_names = set()
        for item in moved:
            if isinstance(item, str):
                moved_names.add(item)
            elif isinstance(item, dict):
                name = item.get('object') or item.get('designator') or \
                    item.get('id')
                if name:
                    moved_names.add(str(name))
        if isinstance(fixed, list):
            for item in fixed:
                if not isinstance(item, dict):
                    continue
                name = item.get('object') or item.get('designator')
                if name and str(name) in moved_names:
                    findings.append({
                        'code': 'locked-object-moved',
                        'message': 'intent declares %s fixed but the observation '
                                   'reports it moved' % name,
                        'severity': schemas.SEVERITY_UNKNOWN,
                        'objects': [name],
                        '_source': 'pcb.moved_objects',
                    })
        checks.append('pcb.moved_objects')
    return findings, unknown, checks


def _declared_rule_evidence(declared):
    """Evaluate declared rules; return hard records plus non-hard outcomes."""
    findings, unknown, checks, other, other_unknown = [], [], [], [], []
    for index, rule in enumerate(declared):
        layer = rule.get('layer')
        if layer not in schemas.LAYERS:
            layer = schemas.LAYER_ENGINEERING
        rule_id = str(rule.get('id') or rule.get('code') or 'rule-%d' % index)
        status = _status_token(_first_value(rule, rule,
                                            ('status', 'state', 'verdict')))
        passed = _bool_value(rule.get('passed'))
        if status is None and passed is not None:
            status = 'pass' if passed else 'fail'
        items = []
        for key in ('findings', 'violations', 'issues'):
            value = rule.get(key)
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        if status is None:
            status = 'fail' if items else 'unknown'

        if layer == schemas.LAYER_HARD:
            if status == 'fail':
                if items:
                    for item in items:
                        findings.append(dict(item, code='hard-rule',
                                             rule_id=rule_id,
                                             layer=schemas.LAYER_HARD,
                                             _source='rule:%s' % rule_id))
                else:
                    findings.append({
                        'code': 'hard-rule',
                        'rule_id': rule_id,
                        'message': _text(rule.get('message')) or
                                   'declared hard rule %s failed' % rule_id,
                        'severity': rule.get('severity', schemas.SEVERITY_UNKNOWN),
                        'evidence': rule.get('evidence') or rule,
                        'layer': schemas.LAYER_HARD,
                        '_source': 'rule:%s' % rule_id,
                    })
            elif status == 'unknown':
                unknown.append({'field': 'rules.%s' % rule_id,
                                'reason': 'declared hard rule is unknown/not run'})
            else:
                checks.append('rule:%s' % rule_id)
        else:
            if status == 'unknown':
                other_unknown.append({'field': 'rules.%s' % rule_id,
                                      'reason': 'declared %s rule is unknown/not run'
                                                % layer})
            elif status == 'fail' or items:
                other.append((rule, layer, status, items, rule_id))
            else:
                checks.append('rule:%s' % rule_id)
    return findings, unknown, checks, other, other_unknown


# ---------------------------------------------------------------------------
# engineering checks
# ---------------------------------------------------------------------------

def _iter_engineering_sources(observation):
    observation = observation if isinstance(observation, dict) else {}
    schematic = observation.get('schematic') if isinstance(
        observation.get('schematic'), dict) else {}
    pcb = observation.get('pcb') if isinstance(observation.get('pcb'), dict) else {}
    sources = []
    for container, name, key, kind in (
            (pcb, 'pcb', 'check', 'pcb_check'),
            (pcb, 'pcb', 'dfm', 'pcb_check'),
            (pcb, 'pcb', 'critical', 'critical'),
            (pcb, 'pcb', 'power_paths', 'power'),
            (pcb, 'pcb', 'return_paths', 'return'),
            (pcb, 'pcb', 'thermal', 'thermal'),
            (pcb, 'pcb', 'sensitive_nodes', 'sensitive'),
            (schematic, 'schematic', 'sensitive_nodes', 'sensitive'),
            (schematic, 'schematic', 'power_paths', 'power'),
            (schematic, 'schematic', 'audit', 'schematic_audit')):
        if key in container:
            sources.append(('%s.%s' % (name, key), container.get(key), kind))
    for key, kind in (
            ('pcb_check', 'pcb_check'),
            ('critical', 'critical'),
            ('engineering_checks', 'engineering_check'),
            ('engineering', 'engineering_check'),
            ('checks', 'engineering_check')):
        if key in observation:
            sources.append((key, observation.get(key), kind))
    return sources


def _walk_engineering(label, value, kind, out):
    """Append ``(label, finding, kind)`` and coverage notes to ``out``."""
    if value is None:
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict) and any(
                    key in item for key in ('findings', 'issues', 'status',
                                            'passed', 'result')):
                _walk_engineering('%s[%d]' % (label, index), item, kind, out)
            elif isinstance(item, dict):
                out['findings'].append((label, item, kind))
            elif isinstance(item, (str, int, float)):
                out['findings'].append((label, {'message': str(item)}, kind))
        return
    if not isinstance(value, dict):
        out['coverage'].append({'source': label, 'kind': kind,
                                'status': 'unknown',
                                'reason': 'source is not an object/list'})
        return

    if isinstance(value.get('result'), dict) and not any(
            key in value for key in ('findings', 'issues')):
        _walk_engineering(label + '.result', value['result'], kind, out)
        return

    findings = None
    for key in ('findings', 'issues'):
        candidate = value.get(key)
        if isinstance(candidate, list):
            findings = candidate
            break
    status = _status_token(_first_value(value, value,
                                        ('status', 'state', 'verdict')))
    passed = _bool_value(_first_value(value, value, ('passed', 'ok')))
    if status is None and passed is not None:
        status = 'pass' if passed else 'fail'
    if kind == 'critical' and value.get('status') == 'blocked':
        # audit_critical uses "blocked" for a hard finding, not for a check
        # that failed to run.
        status = 'fail' if findings else 'unknown'
    if status is None and isinstance(value.get('summary'), dict):
        status = 'pass' if not any(
            (number or 0) > 0 for number in
            (_number(raw) for raw in value['summary'].values())) else 'fail'
    if status is None and findings is not None:
        status = 'fail' if findings else 'pass'

    if findings is not None:
        if status == 'unknown':
            out['coverage'].append({'source': label, 'kind': kind,
                                    'status': 'unknown',
                                    'reason': 'check status is unknown'})
        elif status in ('pass', 'fail', 'warn'):
            out['coverage'].append({'source': label, 'kind': kind,
                                    'status': status, 'summary': value.get('summary')})
        for item in findings:
            if isinstance(item, dict):
                out['findings'].append((label, item, kind))
            else:
                out['findings'].append((label, {'message': str(item)}, kind))
        if kind == 'pcb_check':
            out['pcb_check'].append((label, value, findings))
        return

    if 'summary' in value or 'counts' in value:
        out['coverage'].append({'source': label, 'kind': kind,
                                'status': status or 'unknown',
                                'summary': value.get('summary') or value.get('counts')})
        if kind == 'pcb_check':
            out['pcb_check'].append((label, value, []))
        return

    if status in ('pass', 'fail', 'warn', 'unknown'):
        out['coverage'].append({'source': label, 'kind': kind,
                                'status': status,
                                'summary': value.get('summary')})
        if status in ('fail', 'warn') and kind in (
                'power', 'return', 'thermal', 'sensitive',
                'engineering_check'):
            # A named check carried as a single result object is itself the
            # finding; there is no separate findings list to walk.
            record = dict(value)
            record.setdefault('code', {
                'power': 'power-path',
                'return': 'return-path',
                'thermal': 'thermal',
                'sensitive': 'sensitive-node',
            }.get(kind, label.rsplit('.', 1)[-1]))
            out['findings'].append((label, record, kind))
        return

    # A dictionary of named sub-checks.
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            _walk_engineering('%s.%s' % (label, key), item, kind, out)


def _camel_code(name):
    text = re.sub(r'(.)([A-Z][a-z]+)', r'\1-\2', str(name))
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', text)
    return _normalize_code(text)


_AGGREGATE_COUNTERS = frozenset({
    'errors', 'warnings', 'infos', 'total', 'passed', 'measured', 'trusted',
    'consistent', 'rawpassed', 'parserversion', 'itemizederrors',
    'itemizedwarnings', 'itemizedinfos', 'unlevelledfindings',
})


def _summary_counters(value):
    """Per-code counters from a raw check summary.

    Parsed reports carry an aggregate ``counts`` object next to the original
    ``summary``; only the original per-code counters are findings, and
    aggregate counters must not be turned into synthetic issues.
    """
    summary = value.get('summary')
    if not isinstance(summary, dict) or not summary:
        summary = value.get('counts')
    if not isinstance(summary, dict):
        return {}
    counters = {}
    for key, raw in summary.items():
        number = _number(raw)
        if number is None or number <= 0:
            continue
        token = re.sub(r'[^a-z0-9]', '', str(key).lower())
        if token in _AGGREGATE_COUNTERS:
            continue
        counters[_camel_code(key)] = int(number)
    return counters


_DECAP_CODES = frozenset({
    'decap-too-far', 'decap-too-far-bulk', 'critical-decoupling-far',
})
_CAP_ROLES = ('bulk', 'local-decoupling', 'unknown')
_CAP_UNIT_SCALE = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'μ': 1e-6,
                   '': 1.0}
_BULK_MIN_FARAD = 1e-6


def _capacitance_far(text):
    """Parse a capacitance value such as ``100nF`` or ``10UF50VC110GL``."""
    if not isinstance(text, str):
        return None
    match = re.search(
        r'(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*([pnuµμ]?)F(?![A-Za-z])',
        text, re.IGNORECASE)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    return number * _CAP_UNIT_SCALE.get(match.group(2).lower(), 1.0)


def _observation_components(observation):
    pcb = observation.get('pcb') if isinstance(observation, dict) else None
    result = {}
    for item in (pcb or {}).get('components') or []:
        if not isinstance(item, dict):
            continue
        ref = _text(item.get('designator') or item.get('ref'))
        if ref:
            result[ref] = item
    return result


def _capacitor_role(raw, components):
    """Return ``(role, basis, auto_action_allowed)`` for a decoupling finding.

    A bulk capacitor (>= 1 uF) has a different placement intent than a local
    decoupling capacitor; without a parsed value the role is ``unknown`` and
    the finding must not drive an automatic move.
    """
    if _code_of(raw) not in _DECAP_CODES:
        return None, None, True
    if isinstance(raw, dict) and _text(raw.get('role')) in _CAP_ROLES:
        role = _text(raw.get('role'))
        return role, 'declared by the source finding', role != 'unknown'
    designator = None
    for value in _objects(raw):
        ref = _text(str(value))
        if ref and ref in components:
            designator = ref
            break
    component = components.get(designator) if designator else None
    if component:
        for key in ('value', 'name', 'device'):
            text = _text(component.get(key))
            farad = _capacitance_far(text)
            if farad is None:
                continue
            role = 'bulk' if farad >= _BULK_MIN_FARAD else 'local-decoupling'
            return (role,
                    'capacitance %s parsed from component %s.%s'
                    % (text, designator, key),
                    True)
    return ('unknown',
            'no capacitance value could be parsed for %s' % (designator or
                                                             'the object'),
            False)


def _engineering_evidence(observation, specs):
    """Return engineering records, hard extras, readability extras, coverage."""
    collected = {'findings': [], 'coverage': [], 'pcb_check': []}
    for label, source, kind in _iter_engineering_sources(observation):
        _walk_engineering(label, source, kind, collected)

    components = _observation_components(observation)
    confirmed, conditional, hard_extra, readability_extra = [], [], [], []
    for label, raw, kind in collected['findings']:
        classification = _classify_with_rules(raw, specs)
        code = classification['code']
        rule_layer = (specs.get(code) or {}).get('layer') if specs else None
        if classification['layer'] == schemas.LAYER_HARD and \
                kind != 'schematic_audit' and code not in HARD_CODES and \
                rule_layer != schemas.LAYER_HARD:
            # A pcb/critical check may carry scope="hard" meaning the
            # constraint is strict; in this contract it is still an
            # engineering finding, not a hard electrical violation.
            classification['layer'] = schemas.LAYER_ENGINEERING
            classification['blocking'] = False
            classification['status'] = (
                'confirmed_issue' if classification['deterministic']
                else 'conditional_risk')
            classification['basis'] = (
                classification['basis'] + '; source scope describes constraint '
                'strength, not the evaluation layer')
        if classification['layer'] == schemas.LAYER_HARD:
            record = _finding_record(classification, raw, label, 0)
            hard_extra.append(record)
            continue
        if classification['layer'] == schemas.LAYER_READABILITY:
            record = _finding_record(classification, raw, label, 0)
            readability_extra.append(record)
            continue
        record = _finding_record(classification, raw, label, 0)
        role, role_basis, auto_action = _capacitor_role(raw, components)
        if role is not None:
            record['role'] = role
            record['role_basis'] = role_basis
            record['auto_action_allowed'] = bool(auto_action)
            if role == 'bulk':
                # The distance limit describes local decoupling; a bulk
                # capacitor is not exempt from placement quality, but this
                # measured finding cannot be confirmed as a defect.
                record['deterministic'] = False
                record['status'] = 'conditional_risk'
                record['basis'] = (
                    record['basis'] + '; component is a bulk capacitor, so the '
                    'local-decoupling distance limit is not a confirmed defect')
                conditional.append(record)
                continue
            if role == 'unknown':
                record['basis'] = (
                    record['basis'] + '; capacitor role is unknown, so this '
                    'finding must not drive an automatic move')
        if classification['status'] == 'confirmed_issue':
            confirmed.append(record)
        else:
            conditional.append(record)

    # PCB check summary without itemised findings, or with a count gap.
    coverage_unknown = []
    for label, value, findings in collected['pcb_check']:
        if not isinstance(value, dict):
            continue
        status = _status_token(_first_value(value, value,
                                            ('status', 'state', 'verdict')))
        passed = _bool_value(_first_value(value, value, ('passed', 'ok')))
        if status is None and passed is not None:
            status = 'pass' if passed else 'fail'
        counters = _summary_counters(value)
        receipt_problems = []
        if _bool_value(value.get('measured')) is False:
            receipt_problems.append('the check report says it is not measured')
        contradictions = value.get('contradictions')
        if isinstance(contradictions, list) and contradictions:
            receipt_problems.append(
                'internal contradictions: %s'
                % '; '.join(str(item) for item in contradictions[:3]))
        if value.get('trusted') is False:
            receipt_problems.append('the check receipt is not trusted')
        if value.get('consistent') is False:
            receipt_problems.append('the check receipt is not self-consistent')
        if receipt_problems:
            coverage_unknown.append({
                'field': label + '.receipt',
                'reason': '; '.join(receipt_problems),
            })
            continue
        if status == 'unknown':
            coverage_unknown.append({
                'field': label,
                'reason': 'pcb check state is unknown/not run',
            })
            continue
        if counters and not findings:
            for code, count in sorted(counters.items()):
                record = _finding_record(
                    _classify_with_rules({
                        'code': code,
                        'layer': schemas.LAYER_ENGINEERING,
                        'severity': schemas.SEVERITY_UNKNOWN,
                        'deterministic': False,
                        'recheck': 'read back the itemised %s finding(s) and '
                                   're-run pcb check' % code,
                        'message': 'pcb check summary reports %s=%d without '
                                   'itemised findings' % (code, count),
                        'basis': 'source counter without finding detail; '
                                 'kept conditional until the item is read back',
                    }, specs),
                    {'message': 'pcb check summary reports %s=%d without '
                                'itemised findings' % (code, count),
                     'counter': code, 'count': count},
                    label, 0)
                conditional.append(record)
        elif counters and findings:
            declared = sum(counters.values())
            if declared > len(findings):
                conditional.append(_finding_record(
                    _classify_with_rules({
                        'code': 'pcb-check-summary-gap',
                        'layer': schemas.LAYER_ENGINEERING,
                        'severity': schemas.SEVERITY_UNKNOWN,
                        'message': 'pcb check summary reports %d issue(s) but '
                                   'only %d finding(s) were supplied'
                                   % (declared, len(findings)),
                        'basis': 'summary/finding count mismatch',
                    }, specs),
                    {'message': 'pcb check summary/finding count mismatch',
                     'summary_total': declared, 'findings': len(findings)},
                    label, 0))
        if passed is False and not findings and not counters:
            conditional.append(_finding_record(
                _classify_with_rules({
                    'code': 'pcb-check-failed-without-findings',
                    'layer': schemas.LAYER_ENGINEERING,
                    'severity': schemas.SEVERITY_UNKNOWN,
                    'message': 'pcb check reported failure without findings',
                    'basis': 'source reported failure; detail was not supplied',
                }, specs),
                {'message': 'pcb check reported failure without findings'},
                label, 0))

    required_kinds = {'pcb_check', 'critical', 'power', 'return', 'thermal',
                      'sensitive', 'engineering_check'}
    evidence_present = any(
        item.get('kind') in required_kinds for item in collected['coverage'])
    evidence_present = evidence_present or bool(collected['pcb_check'])
    unknown_sources = [item for item in collected['coverage']
                       if item.get('kind') in required_kinds and
                       item.get('status') == 'unknown']
    unknown_sources.extend(coverage_unknown)
    if not evidence_present:
        unknown_sources.append({
            'field': 'engineering',
            'reason': 'no pcb check, critical or power/return/thermal/'
                      'sensitive-node check evidence was supplied',
        })

    # Audit coverage gaps are recorded but do not by themselves make the
    # required engineering layer unknown; electrical/power lanes are separate.
    audit_gaps = [item for item in collected['coverage']
                  if item.get('kind') == 'schematic_audit' and
                  item.get('status') == 'unknown']
    return {
        'confirmed': confirmed,
        'conditional': conditional,
        'hard_extra': hard_extra,
        'readability_extra': readability_extra,
        'coverage': collected['coverage'],
        'unknown': unknown_sources,
        'audit_gaps': audit_gaps,
        'evidence_present': evidence_present,
    }


# ---------------------------------------------------------------------------
# readability
# ---------------------------------------------------------------------------

def _readability_records(value, label, kind):
    records = []
    if value is None:
        return records, None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                records.append((label, item, kind))
        return records, 'present'
    if not isinstance(value, dict):
        return records, 'unknown'

    status = _status_token(_first_value(value, value,
                                        ('status', 'state', 'verdict')))
    findings = value.get('findings') or value.get('issues') or \
        value.get('suggestions')
    if isinstance(findings, list):
        for item in findings:
            if isinstance(item, dict):
                records.append((label, item, kind))
        if status == 'unknown' or value.get('coverage_issues'):
            return records, 'unknown'
        return records, 'present'

    if kind == 'score' or isinstance(value.get('dimensions'), list) or (
            isinstance(value.get('report'), dict) and
            isinstance(value['report'].get('dimensions'), list)):
        dimensions = value.get('dimensions')
        if isinstance(value.get('report'), dict):
            dimensions = value['report'].get('dimensions')
        if isinstance(dimensions, list):
            found = False
            for dimension in dimensions:
                if not isinstance(dimension, dict):
                    continue
                dim_id = _normalize_code(dimension.get('id') or 'unknown')
                if dim_id not in _READABILITY_DIMS and not any(
                        token in dim_id for token in
                        ('label', 'proximity', 'frame', 'text', 'overlap')):
                    continue
                attributions = dimension.get('attributions')
                if isinstance(attributions, list) and attributions:
                    found = True
                    for attr in attributions:
                        if not isinstance(attr, dict):
                            continue
                        record = dict(attr)
                        record.setdefault('code', dim_id)
                        record.setdefault('severity', schemas.SEVERITY_INFO)
                        records.append((label, record, 'score'))
                elif dimension.get('status') == 'scored':
                    score = _number(dimension.get('score'))
                    if score is not None and score < 100:
                        found = True
                        records.append((label, {
                            'code': dim_id,
                            'severity': schemas.SEVERITY_INFO,
                            'score': score,
                            'weight': dimension.get('weight'),
                            'message': 'readability dimension %s scored %s'
                                       % (dim_id, score),
                        }, 'score'))
                elif dimension.get('status') in ('degraded', 'unknown',
                                                 'not_scored'):
                    found = True
                    records.append((label, {
                        'code': dim_id,
                        'severity': schemas.SEVERITY_INFO,
                        'message': 'readability dimension %s is %s'
                                   % (dim_id, dimension.get('status')),
                    }, 'score'))
            return records, 'present'
        return records, 'present'

    if status == 'unknown' or value.get('coverage_issues'):
        return records, 'unknown'
    return records, 'present'


def _readability_evidence(observation, specs):
    observation = observation if isinstance(observation, dict) else {}
    schematic = observation.get('schematic') if isinstance(
        observation.get('schematic'), dict) else {}
    sources = []
    for container, name, key, kind in (
            (schematic, 'schematic', 'readability', 'readability'),
            (schematic, 'schematic', 'text_audit', 'text_audit'),
            (schematic, 'schematic', 'visual', 'visual'),
            (schematic, 'schematic', 'audit', 'audit'),
            (schematic, 'schematic', 'score', 'score'),
            (observation, '', 'readability', 'readability')):
        if key in container:
            label = ('%s.%s' % (name, key)) if name else key
            sources.append((label, container.get(key), kind))

    records, unknown, present = [], [], False
    for label, value, kind in sources:
        items, state = _readability_records(value, label, kind)
        if state == 'unknown':
            unknown.append({'field': label,
                            'reason': 'readability evidence is incomplete'})
        elif state == 'present':
            present = True
        for item_label, raw, item_kind in items:
            if item_kind == 'audit':
                code = _code_of(raw)
                if code not in READABILITY_CODES:
                    continue
            records.append((item_label, raw, item_kind))

    suggestions = []
    for label, raw, kind in records:
        classification = _classify_with_rules(raw, specs)
        if classification['layer'] != schemas.LAYER_READABILITY:
            # A readability source that reports a non-readability finding is
            # not silently promoted; the finding stays out of this lane.
            continue
        record = _finding_record(classification, raw, label, 0)
        record['blocking'] = False
        suggestions.append(record)
    if records:
        present = True
    return {
        'suggestions': suggestions,
        'unknown': unknown,
        'present': present,
        'sources': [label for label, _, _ in sources],
    }


# ---------------------------------------------------------------------------
# caller-supplied issues
# ---------------------------------------------------------------------------

def _issue_records(issues):
    if isinstance(issues, dict):
        issues = issues.get('issues')
    if not isinstance(issues, list):
        return [], [], [], []
    confirmed, conditional, hard_extra, readability = [], [], [], []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        status = _status_token(issue.get('status'))
        if status == 'pass' or issue.get('status') in ('closed', 'resolved',
                                                       'waived'):
            continue
        basis = issue.get('basis') if isinstance(issue.get('basis'), dict) else {}
        layer = _text(issue.get('layer')) or _text(basis.get('layer')) or \
            schemas.LAYER_ENGINEERING
        layer = layer if layer in schemas.LAYERS else schemas.LAYER_ENGINEERING
        deterministic = bool(basis.get('deterministic') or
                             issue.get('deterministic'))
        severity = issue.get('severity')
        if severity not in schemas.SEVERITIES:
            severity = schemas.SEVERITY_UNKNOWN
        record = {
            'id': issue.get('id') or 'issue',
            'source_id': issue.get('id'),
            'code': _normalize_code(issue.get('code') or issue.get('id') or
                                    'issue'),
            'layer': layer,
            'severity': severity,
            'deterministic': deterministic,
            'blocking': layer == schemas.LAYER_HARD and
                        deterministic and severity == schemas.SEVERITY_BLOCKING,
            'message': _text(issue.get('description')) or
                       _text(issue.get('message')) or 'issue',
            'objects': _objects(issue),
            'evidence': {'source': 'issues', 'issue': issue},
            'basis': _text(basis.get('reason')) or
                     ('caller-declared issue' if deterministic else
                      'caller-declared heuristic issue'),
            'recheck': _text(issue.get('recheck')) or (
                issue.get('improvement') or {}).get('predicate'),
            'source': 'issues',
        }
        if layer == schemas.LAYER_HARD:
            record['blocking'] = True
            if deterministic:
                hard_extra.append(record)
            else:
                conditional.append(record)
        elif layer == schemas.LAYER_READABILITY:
            record['blocking'] = False
            readability.append(record)
        elif deterministic:
            confirmed.append(record)
        else:
            conditional.append(record)
    return confirmed, conditional, hard_extra, readability


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def _evaluation_target(observation, intent):
    observation = observation if isinstance(observation, dict) else {}
    project = observation.get('project') if isinstance(
        observation.get('project'), dict) else {}
    documents = observation.get('documents')
    if not isinstance(documents, list):
        documents = []
    target = {
        'project_uuid': project.get('uuid'),
        'project_name': project.get('name'),
        'documents': [
            {'uuid': document.get('uuid'), 'type': document.get('type'),
             'name': document.get('name')}
            for document in documents
            if isinstance(document, dict)
        ],
    }
    if not project and isinstance(intent, dict) and isinstance(
            intent.get('target'), dict):
        target = dict(intent['target'])
    return target


def _observation_unknown(observation):
    """Copy observation-declared unknowns that can affect this evaluation."""
    observation = observation if isinstance(observation, dict) else {}
    entries = observation.get('unknown')
    if not isinstance(entries, list):
        return []
    result = []
    prefixes = ('drc', 'schematic.drc', 'pcb.drc', 'pad_net',
                'schematic.pad_net', 'pcb.pad_net', 'outline', 'locked',
                'keepout', 'readability', 'text', 'pcb.check',
                'engineering')
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        field = str(entry.get('field') or '')
        if field.startswith(prefixes):
            result.append({'field': field,
                           'reason': _text(entry.get('reason')) or
                                     'observation declared this value unknown'})
    return result


def _hard_status(findings, unknown, drc_entries):
    if findings or any(entry['state'] == 'fail' for entry in drc_entries):
        return schemas.STATUS_FAIL
    if unknown:
        return schemas.STATUS_UNKNOWN
    if any(entry['state'] == 'pass' for entry in drc_entries):
        return schemas.STATUS_PASS
    return schemas.STATUS_UNKNOWN


def _engineering_status(confirmed, conditional, unknown, evidence_present):
    if unknown:
        return schemas.STATUS_UNKNOWN
    if confirmed or conditional:
        return schemas.STATUS_WARN
    if evidence_present:
        return schemas.STATUS_PASS
    return schemas.STATUS_UNKNOWN


def _readability_status(suggestions, unknown, present):
    if suggestions:
        return schemas.STATUS_WARN
    if unknown:
        return schemas.STATUS_UNKNOWN
    if present:
        return schemas.STATUS_PASS
    return schemas.STATUS_UNKNOWN


def evaluate(*, observation, intent=None, issues=None, rules=None):
    """Evaluate one observation through the three fixed layers.

    Returns a schema-valid ``hds-quality-eval/v1`` payload with no total
    score.  Missing required DRC evidence keeps the hard layer unknown; a hard
    failure always produces ``verdict = fail``; readability can only produce
    suggestions.
    """
    observation = observation if isinstance(observation, dict) else {}
    target = _evaluation_target(observation, intent)
    specs, declared = _rulebook(rules)

    hard_findings = []
    hard_unknown = []
    hard_checks = []
    hard_not_run = []

    drc_entries = _drc_entries(observation)
    for entry in drc_entries:
        if entry['state'] == 'fail':
            for raw in entry['findings']:
                source = entry['where']
                hard_source = dict(raw)
                hard_source['layer'] = schemas.LAYER_HARD
                classification = _classify_with_rules(hard_source, specs)
                hard_findings.append(_finding_record(
                    classification, raw, source, 0))
        elif entry['state'] == 'pass':
            hard_checks.append(entry['where'])
        else:
            hard_unknown.append({
                'field': entry['where'],
                'reason': entry['reason'] or 'DRC state is unknown',
            })
            hard_not_run.append(entry['where'])

    pad_findings, pad_unknown, pad_checks, pad_present = _pad_net_evidence(
        observation, intent)
    for raw in pad_findings:
        hard_source = dict(raw)
        hard_source['layer'] = schemas.LAYER_HARD
        classification = _classify_with_rules(hard_source, specs)
        hard_findings.append(_finding_record(
            classification, raw, raw.get('_source') or 'pad_net', 0))
    hard_unknown.extend(pad_unknown)
    hard_checks.extend(pad_checks)
    if not pad_present:
        hard_not_run.append('pad_net')

    inv_findings, inv_unknown, inv_checks = _invariant_evidence(
        observation, intent)
    for raw in inv_findings:
        hard_source = dict(raw)
        hard_source['layer'] = schemas.LAYER_HARD
        classification = _classify_with_rules(hard_source, specs)
        hard_findings.append(_finding_record(
            classification, raw, raw.get('_source') or 'invariant', 0))
    hard_unknown.extend(inv_unknown)
    hard_checks.extend(inv_checks)

    rule_findings, rule_unknown, rule_checks, rule_other, rule_other_unknown = \
        _declared_rule_evidence(declared)
    for raw in rule_findings:
        hard_source = dict(raw)
        hard_source['layer'] = schemas.LAYER_HARD
        classification = _classify_with_rules(hard_source, specs)
        hard_findings.append(_finding_record(
            classification, raw, raw.get('_source') or 'rules', 0))
    hard_unknown.extend(rule_unknown)
    hard_checks.extend(rule_checks)

    rule_confirmed, rule_conditional, rule_suggestions = [], [], []
    for rule, layer, status, items, rule_id in rule_other:
        payloads = items or [{
            'message': _text(rule.get('message')) or
                       'declared %s rule %s failed' % (layer, rule_id),
            'severity': rule.get('severity', schemas.SEVERITY_UNKNOWN),
            'evidence': rule.get('evidence') or rule,
        }]
        for item in payloads:
            raw = dict(item)
            raw.setdefault('layer', layer)
            if 'deterministic' not in raw and isinstance(
                    rule.get('deterministic'), bool):
                raw['deterministic'] = rule['deterministic']
            if _text(rule.get('recheck')):
                raw.setdefault('recheck', rule['recheck'])
            classification = _classify_with_rules(raw, specs)
            record = _finding_record(
                classification, raw, 'rule:%s' % rule_id, 0)
            if classification['layer'] == schemas.LAYER_READABILITY:
                record['blocking'] = False
                rule_suggestions.append(record)
            elif classification['layer'] == schemas.LAYER_HARD:
                hard_findings.append(record)
            elif classification['status'] == 'confirmed_issue':
                rule_confirmed.append(record)
            else:
                rule_conditional.append(record)

    engineering = _engineering_evidence(observation, specs)
    hard_findings.extend(engineering['hard_extra'])

    drc_warnings = []
    for entry in drc_entries:
        for raw in entry['warnings']:
            warning = dict(raw)
            warning.setdefault('layer', schemas.LAYER_ENGINEERING)
            warning_basis = ('source DRC warning, not a fatal/error violation; '
                             'kept conditional until re-run or waived')
            warning['basis'] = warning_basis
            warning['deterministic'] = False
            warning['recheck'] = ('re-run the host DRC after addressing or '
                                  'waiving the warning')
            classification = _classify_with_rules(warning, specs)
            classification['layer'] = schemas.LAYER_ENGINEERING
            classification['deterministic'] = False
            classification['status'] = 'conditional_risk'
            classification['blocking'] = False
            classification['basis'] = warning_basis
            classification['recheck'] = warning['recheck']
            drc_warnings.append(_finding_record(
                classification, warning, entry['where'], 0))

    issue_confirmed, issue_conditional, issue_hard, issue_readability = \
        _issue_records(issues)
    hard_findings.extend(issue_hard)

    readability = _readability_evidence(observation, specs)

    hard_findings = _dedupe(hard_findings)
    confirmed = _dedupe(engineering['confirmed'] + rule_confirmed +
                        issue_confirmed)
    conditional = _dedupe(engineering['conditional'] + drc_warnings +
                          rule_conditional + issue_conditional)
    suggestions = _dedupe(readability['suggestions'] +
                          engineering['readability_extra'] +
                          rule_suggestions + issue_readability)

    hard_findings = _assign_ids(hard_findings, 'eval-hard')
    confirmed = _assign_ids(confirmed, 'eval-confirmed')
    conditional = _assign_ids(conditional, 'eval-conditional')
    suggestions = _assign_ids(suggestions, 'eval-suggestion')

    confirmed_issues = [
        _issue_from_record(record, target, index)
        for index, record in enumerate(confirmed, start=1)
    ]
    conditional_risks = [
        _issue_from_record(record, target, index)
        for index, record in enumerate(conditional, start=1)
    ]

    hard_unknown = [
        dict(item, source=item.get('source') or 'evaluation')
        for item in hard_unknown + _observation_unknown(observation)
    ]
    # Duplicate unknown entries are not useful; key on field/reason.
    seen = set()
    unique_unknown = []
    for item in hard_unknown:
        key = (item.get('field'), item.get('reason'))
        if key in seen:
            continue
        seen.add(key)
        unique_unknown.append(item)
    hard_unknown = unique_unknown

    engineering_unknown = []
    seen_engineering = set()
    for item in engineering['unknown'] + rule_other_unknown:
        key = (item.get('field'), item.get('reason'))
        if key in seen_engineering:
            continue
        seen_engineering.add(key)
        engineering_unknown.append(item)
    engineering_status = _engineering_status(
        confirmed, conditional, engineering_unknown,
        engineering['evidence_present'])
    hard_status = _hard_status(hard_findings, hard_unknown, drc_entries)
    readability_status = _readability_status(
        suggestions, readability['unknown'], readability['present'])

    layers = {
        schemas.LAYER_HARD: {
            'status': hard_status,
            'findings': hard_findings,
            'checks_run': hard_checks,
            'checks_not_run': hard_not_run,
            'unknown': hard_unknown,
        },
        schemas.LAYER_ENGINEERING: {
            'status': engineering_status,
            'findings': confirmed + conditional,
            'confirmed': confirmed,
            'conditional': conditional,
            'checks_run': [item.get('source') for item in
                           engineering['coverage']
                           if item.get('status') in ('pass', 'fail', 'warn')],
            'checks_not_run': [item.get('field') for item in
                               engineering_unknown],
            'unknown': engineering_unknown,
        },
        schemas.LAYER_READABILITY: {
            'status': readability_status,
            'findings': suggestions,
            'checks_run': readability['sources'],
            'checks_not_run': ([] if readability['present'] else
                               ['readability']),
            'unknown': readability['unknown'],
            'advisory_only': True,
        },
    }

    unknown = list(hard_unknown) + list(engineering_unknown)
    evaluation = schemas.new_evaluation(
        target=target,
        layers=layers,
        confirmed_issues=confirmed_issues,
        conditional_risks=conditional_risks,
        suggestions=suggestions,
        unknown=unknown,
    )
    evaluation['note'] = (
        'no total score: a hard failure is never offset by other layers; '
        'readability findings are suggestions only')
    evaluation['drc_zero_but_quality_issues'] = drc_zero_but_poor(
        observation, evaluation)
    evaluation['simulated'] = bool(observation.get('simulated'))

    if hard_status == schemas.STATUS_FAIL:
        verdict = schemas.STATUS_FAIL
        reasons = sorted({record['code'] for record in hard_findings})
        reason = 'hard layer failed (%d finding(s): %s)' % (
            len(hard_findings), ', '.join(reasons[:5]))
    elif hard_status == schemas.STATUS_UNKNOWN:
        verdict = schemas.STATUS_UNKNOWN
        fields = sorted({item.get('field') for item in hard_unknown
                         if item.get('field')})
        reason = 'hard layer is unknown: %s' % (
            ', '.join(fields[:5]) or 'a required hard input is missing')
    elif engineering_status == schemas.STATUS_UNKNOWN:
        verdict = schemas.STATUS_UNKNOWN
        fields = sorted({item.get('field') for item in engineering_unknown
                         if item.get('field')})
        reason = 'engineering layer has incomplete evidence: %s' % (
            ', '.join(fields[:5]) or 'no required check was run')
    elif engineering_status == schemas.STATUS_WARN:
        verdict = 'pass_with_warnings'
        reason = ('hard layer passed; engineering reports %d confirmed '
                  'issue(s) and %d conditional risk(s)' % (
                      len(confirmed), len(conditional)))
    else:
        verdict = schemas.STATUS_PASS
        reason = ('hard layer passed and engineering checks ran without a '
                  'confirmed issue; readability is advisory')
    evaluation['verdict'] = verdict
    evaluation['reason'] = reason

    schemas.validate_evaluation(evaluation)
    return evaluation


def drc_zero_but_poor(observation, evaluation):
    """True only when every present DRC passed and engineering confirmed at
    least one issue.  Readability alone never makes this true."""
    if not isinstance(evaluation, dict):
        return False
    layers = evaluation.get('layers') if isinstance(
        evaluation.get('layers'), dict) else {}
    hard = layers.get(schemas.LAYER_HARD) if isinstance(
        layers.get(schemas.LAYER_HARD), dict) else {}
    if hard.get('status') != schemas.STATUS_PASS:
        return False
    engineering_confirmed = []
    for issue in evaluation.get('confirmed_issues') or []:
        if not isinstance(issue, dict):
            continue
        layer = issue.get('layer')
        basis = issue.get('basis') if isinstance(issue.get('basis'), dict) else {}
        if layer == schemas.LAYER_ENGINEERING or (
                layer is None and basis.get('deterministic') is True and
                layer != schemas.LAYER_READABILITY):
            engineering_confirmed.append(issue)
    if not engineering_confirmed:
        return False
    entries = _drc_entries(observation)
    if not entries:
        return False
    if not any(entry.get('present') for entry in entries):
        return False
    return all(entry['state'] == schemas.STATUS_PASS for entry in entries)


# ---------------------------------------------------------------------------
# candidate comparison
# ---------------------------------------------------------------------------

def _metric_key(key):
    text = str(key).strip().lower().replace('_', '-').replace(' ', '-')
    text = re.sub(r'-+', '-', text).strip('-')
    for suffix in ('-mil', '-mm', '-um', '-pct', '-percent', '-ratio'):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    return _KEY_METRICS.get(text, text.replace('-', '_'))


def _metric_value(raw):
    if isinstance(raw, bool):
        return raw
    number = _number(raw)
    if number is not None:
        return number
    if isinstance(raw, dict):
        marker = _status_token(raw.get('status') or raw.get('state'))
        if marker == 'unknown':
            return None
        for key in ('value', 'measured', 'result', 'number'):
            if key in raw:
                return _metric_value(raw[key])
        return None
    if isinstance(raw, str):
        token = raw.strip().lower()
        if token in ('unknown', 'not_run', 'not-run', 'unavailable', 'none',
                     'null', ''):
            return None
        try:
            return float(token)
        except ValueError:
            return None
    return None


def _normalize_metrics(metrics):
    result = {}
    if not isinstance(metrics, dict):
        return result
    for key, raw in metrics.items():
        canonical = _metric_key(key)
        value = _metric_value(raw)
        if canonical in result and value is None:
            continue
        result[canonical] = value
    return result


def _tolerance(metric, target, reference_value):
    raw = target.get('tolerance', target.get('metric_tolerance', 0.0))
    relative, absolute = 0.0, 0.0
    if isinstance(raw, dict):
        value = None
        for key, candidate in raw.items():
            if _metric_key(key) == metric:
                value = candidate
                break
        if isinstance(value, dict):
            relative = _number(value.get('relative')) or 0.0
            absolute = _number(value.get('absolute')) or 0.0
        else:
            absolute = _number(value) or 0.0
    else:
        relative = _number(raw) or 0.0
    base = abs(float(reference_value)) if isinstance(reference_value, (int, float)) \
        else 0.0
    return relative * base + absolute


def _direction(value):
    token = _text(value)
    if not token:
        return None
    token = token.strip().lower()
    if token in ('minimize', 'min', 'lower', 'smaller', 'less', 'fewer'):
        return 'minimize'
    if token in ('maximize', 'max', 'higher', 'larger', 'greater', 'more'):
        return 'maximize'
    return None


def _objective_specs(target, candidates):
    raw = target.get('objective', target.get('objectives'))
    entries = []
    if isinstance(raw, str):
        entries = [{'metric': raw}]
    elif isinstance(raw, dict):
        if 'metric' in raw:
            entries = [dict(raw)]
        else:
            for metric, direction in raw.items():
                entry = {'metric': metric}
                if isinstance(direction, dict):
                    entry.update(direction)
                else:
                    entry['direction'] = direction
                entries.append(entry)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                entries.append({'metric': item})
            elif isinstance(item, dict):
                entries.append(dict(item))
    specs = []
    for entry in entries:
        metric = _metric_key(entry.get('metric'))
        if not metric or metric == 'unknown':
            continue
        direction = _direction(entry.get('direction')) or \
            _METRIC_DIRECTIONS.get(metric)
        if direction is None:
            continue
        specs.append({'metric': metric, 'direction': direction,
                      'explicit': True})
    if specs:
        return specs
    for metric in ('crossings', 'hpwl', 'decap_distance', 'track_count',
                   'keepout_usage', 'net_paths_missing', 'net_paths_found'):
        if any(_measured(entry['metrics'].get(metric))
               for entry in candidates):
            specs.append({'metric': metric,
                          'direction': _METRIC_DIRECTIONS[metric],
                          'explicit': False})
    return specs


def _measured(value):
    return isinstance(value, bool) or _number(value) is not None


def _metric_number(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return _number(value)


def _normalize_hard(hard):
    if isinstance(hard, str):
        status = _status_token(hard) or 'unknown'
        return {'status': status, 'findings': []}
    if not isinstance(hard, dict):
        return {'status': 'unknown', 'findings': []}
    status = _status_token(_first_value(hard, hard,
                                        ('status', 'state', 'verdict')))
    if status is None:
        passed = _bool_value(_first_value(hard, hard, ('passed', 'ok')))
        status = 'pass' if passed is True else ('fail' if passed is False
                                                else 'unknown')
    if status == 'warn':
        status = 'unknown'
    findings = hard.get('findings')
    if not isinstance(findings, list):
        findings = []
    return {'status': status, 'findings': findings}


def _scope_problems(entry, reference, target):
    problems = []
    metrics = entry['metrics']
    for key in ('out_of_scope', 'unrelated_changes', 'changes_outside_scope',
                'out_of_scope_changes'):
        value = metrics.get(key)
        number = _metric_number(value)
        if number is not None and number > 0:
            problems.append({
                'metric': key,
                'value': number,
                'message': 'candidate changes %s object(s) outside the writable '
                           'scope' % int(number),
            })
    if entry['metrics'].get('scope_regression') is True or \
            entry['raw'].get('scope_regression') is True:
        problems.append({'metric': 'scope_regression',
                         'message': 'candidate declares a scope regression'})
    scope = entry['raw'].get('scope')
    if isinstance(scope, dict) and scope.get('regression') is True:
        problems.append({'metric': 'scope.regression',
                         'message': 'candidate scope object declares regression'})
    for finding in entry['hard']['findings']:
        if not isinstance(finding, dict):
            continue
        code = _code_of(finding)
        if code in ('out-of-scope', 'scope-regression', 'unrelated-change',
                    'out-of-scope-change'):
            problems.append({'metric': 'hard.finding',
                             'code': code,
                             'message': _message(finding) or
                                        'candidate reports an out-of-scope change'})
    if reference is not None:
        for metric in ('scope_objects', 'scope_nets', 'scope_coverage',
                       'scope_regions'):
            left = entry['metrics'].get(metric)
            right = reference['metrics'].get(metric)
            if not _measured(left) or not _measured(right):
                continue
            left_number = _metric_number(left)
            right_number = _metric_number(right)
            if left_number is None or right_number is None:
                continue
            allowed = _tolerance(metric, target, right_number)
            if left_number < right_number - allowed - 1e-9:
                problems.append({
                    'metric': metric,
                    'reference': right_number,
                    'value': left_number,
                    'message': 'candidate scope coverage %s is below the '
                               'reference %s' % (left_number, right_number),
                })
    return problems


def _reject(entry, code, message, evidence):
    entry['reasons'].append({'code': code, 'message': message,
                             'evidence': evidence})


def _readability_count(entry):
    readability = entry['raw'].get('readability')
    if isinstance(readability, dict):
        findings = readability.get('findings')
        if isinstance(findings, list):
            return len(findings)
        count = _number(readability.get('count'))
        if count is not None:
            return int(count)
    if isinstance(readability, list):
        return len(readability)
    return None


def _rank_key(entry, objectives):
    values = []
    for spec in objectives:
        value = entry['metrics'].get(spec['metric'])
        number = _metric_number(value)
        if number is None:
            return None
        values.append(number if spec['direction'] == 'minimize' else -number)
    return tuple(values)


def compare_candidates(*, target, candidates):
    """Compare evaluated candidates without a summed score.

    Hard failures are rejected with ``hard_violation``.  A candidate whose key
    metric is worse than the reference beyond tolerance is rejected with
    ``metric_regression`` or ``path_regression`` even when its readability is
    better.  Missing key/objective metrics are ``unknown_metric``; changes
    outside the declared scope are ``scope_regression``.  The selection is a
    lexicographic comparison over the explicit objective; exact ties fall back
    to input order, never to neatness.

    ``target['tolerance']`` is either a relative fraction of the reference
    value (scalar) or a per-metric object whose plain numbers are absolute
    slack (``{"hpwl": 10}``) and whose nested form is
    ``{"hpwl": {"relative": 0.05, "absolute": 2}}``.
    """
    target = target if isinstance(target, dict) else {}
    if not isinstance(candidates, list) or not candidates:
        raise schemas.ContractError('comparison.candidates must not be empty')

    entries = []
    for index, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            raise schemas.ContractError(
                'comparison.candidates[%d] must be an object' % index)
        candidate_id = _text(raw.get('id'))
        if not candidate_id:
            raise schemas.ContractError(
                'comparison.candidates[%d].id is required' % index)
        entry = {
            'index': index,
            'raw': raw,
            'id': candidate_id,
            'hard': _normalize_hard(raw.get('hard')),
            'metrics': _normalize_metrics(raw.get('metrics')),
            'reasons': [],
        }
        entries.append(entry)

    # 1. Hard constraint gate.
    hard_pass = []
    for entry in entries:
        status = entry['hard']['status']
        if status == 'fail':
            _reject(entry, 'hard_violation',
                    'candidate fails a hard constraint',
                    {'hard': entry['hard']})
        elif status == 'unknown':
            _reject(entry, 'unknown_metric',
                    'candidate hard status is unknown; the constraint is not '
                    'proven',
                    {'hard_status': status,
                     'note': 'unknown hard evidence cannot be treated as pass'})
        elif entry['hard']['findings']:
            _reject(entry, 'hard_violation',
                    'candidate reports hard findings while declaring pass',
                    {'hard': entry['hard']})
        else:
            hard_pass.append(entry)

    # 2. Reference selection.  The explicit reference wins; otherwise use the
    #    first hard-pass candidate.  A declared reference that failed hard is
    #    not used as a baseline.
    explicit_reference = target.get('reference', target.get('baseline'))
    if isinstance(explicit_reference, dict):
        explicit_reference = explicit_reference.get('id')
    reference = None
    reference_metrics = None
    if _text(explicit_reference):
        reference = next((entry for entry in hard_pass
                          if entry['id'] == explicit_reference), None)
    if reference is None:
        reference = next((entry for entry in hard_pass
                          if not _scope_problems(entry, None, target)), None)
    if reference is None and hard_pass:
        reference = hard_pass[0]
    if isinstance(target.get('reference_metrics'), dict):
        reference_metrics = _normalize_metrics(target['reference_metrics'])
        metrics_from_target = True
    elif reference is not None:
        reference_metrics = reference['metrics']
        metrics_from_target = False
    else:
        metrics_from_target = False

    # A reference that itself changes outside the declared scope is not a
    # valid baseline.  Keep target-provided metrics, but do not select it.
    if reference is not None:
        reference_problems = _scope_problems(reference, None, target)
        if reference_problems:
            _reject(reference, 'scope_regression',
                    'reference candidate changes outside the declared scope',
                    {'problems': reference_problems,
                     'metrics': reference['metrics']})
            reference = None
            if not metrics_from_target:
                reference_metrics = None
    reference_id = 'target' if metrics_from_target else (
        reference['id'] if reference is not None else None)
    if not isinstance(reference_metrics, dict):
        reference_metrics = {}
    scope_reference = ({'metrics': reference_metrics}
                       if metrics_from_target else reference)

    # 3. Scope and key-metric regressions against the reference.
    key_metrics = [metric for metric in _KEY_METRICS.values()
                   if metric in reference_metrics and
                   _measured(reference_metrics[metric])]
    # Keep a deterministic order and remove duplicates.
    key_metrics = list(dict.fromkeys(key_metrics))
    for entry in hard_pass:
        if entry is reference and not metrics_from_target:
            continue
        problems = _scope_problems(entry, scope_reference, target)
        if problems:
            _reject(entry, 'scope_regression',
                    'candidate changes less/more than the declared scope',
                    {'problems': problems, 'metrics': entry['metrics']})
            continue
        metric_problems, path_problems, unknown = [], [], []
        for metric in key_metrics:
            reference_value = reference_metrics[metric]
            value = entry['metrics'].get(metric)
            if value is None:
                unknown.append(metric)
                continue
            reference_number = _metric_number(reference_value)
            number = _metric_number(value)
            if reference_number is None or number is None:
                continue
            allowed = _tolerance(metric, target, reference_number)
            worse = False
            if _METRIC_DIRECTIONS.get(metric, 'minimize') == 'minimize':
                worse = number > reference_number + allowed + 1e-9
            else:
                worse = number < reference_number - allowed - 1e-9
            if not worse:
                continue
            evidence = {
                'metric': metric,
                'reference': reference_number,
                'value': number,
                'tolerance': allowed,
                'direction': _METRIC_DIRECTIONS.get(metric),
            }
            if metric in _PATH_METRICS:
                path_problems.append(evidence)
            else:
                metric_problems.append(evidence)
        if unknown:
            _reject(entry, 'unknown_metric',
                    'candidate does not measure key metric(s): %s'
                    % ', '.join(unknown),
                    {'metrics': unknown, 'reference': reference_id})
            continue
        if path_problems:
            _reject(entry, 'path_regression',
                    'candidate loses connectivity proof carried by the '
                    'reference',
                    {'problems': path_problems})
            continue
        if metric_problems:
            _reject(entry, 'metric_regression',
                    'candidate is worse than the reference beyond tolerance',
                    {'problems': metric_problems})
        if entry['reasons']:
            continue

    eligible = [entry for entry in hard_pass if not entry['reasons']]
    objectives = _objective_specs(target, eligible)

    # 4. Objective-metric availability.  A metric only some candidates carry
    #    cannot be used to rank the others.
    ranked = []
    for entry in list(eligible):
        key = _rank_key(entry, objectives) if objectives else ()
        if key is None:
            _reject(entry, 'unknown_metric',
                    'candidate does not measure the objective metric(s)',
                    {'objective': objectives, 'metrics': entry['metrics']})
            eligible = [item for item in eligible if item is not entry]
            continue
        # Exact ties fall back to input order.  Readability is reported but is
        # not used to select a candidate: neatness cannot outweigh metrics.
        ranked.append((key, entry['index'], entry))

    ranked.sort(key=lambda item: (item[0], item[1]))
    selected = ranked[0][2] if ranked else None
    selected_id = selected['id'] if selected is not None else None

    summaries = []
    for entry in entries:
        reasons = [reason['code'] for reason in entry['reasons']]
        if entry is selected:
            status = 'selected'
        elif entry['reasons']:
            status = 'rejected'
        elif not entry['reasons']:
            status = 'eligible_not_selected'
        else:
            status = 'rejected'
        summary = dict(entry['raw'])
        # The comparison contract has no total score either.
        summary.pop('total_score', None)
        summary.pop('score', None)
        summary['id'] = entry['id']
        summary['hard'] = entry['hard']
        summary['metrics'] = entry['metrics']
        summary['readability'] = entry['raw'].get('readability') or {}
        summary['status'] = status
        summary['reason_codes'] = reasons
        summaries.append(summary)

    rejected = []
    for entry in entries:
        if not entry['reasons']:
            continue
        codes = list(dict.fromkeys(reason['code']
                                   for reason in entry['reasons']))
        rejected.append({
            'id': entry['id'],
            'reason_codes': codes,
            'reason': codes[0],
            'reasons': entry['reasons'],
            'evidence': {
                'metrics': entry['metrics'],
                'hard': {'status': entry['hard']['status']},
                'reference': reference_id,
            },
        })

    not_selected = []
    if selected is not None:
        for entry in eligible:
            if entry is selected:
                continue
            not_selected.append({
                'id': entry['id'],
                'reason': 'not selected by the explicit objective',
                'metrics': entry['metrics'],
                'readability_findings': _readability_count(entry),
            })

    comparison = schemas.new_candidate_comparison(
        target=target,
        candidates=summaries,
        selected=selected_id,
        rejected=rejected,
    )
    comparison['basis'] = (
        'hard constraints first; key metrics compared against the reference '
        'with declared tolerance; selection is lexicographic over the '
        'explicit objective; no summed score')
    comparison['reference'] = reference_id
    comparison['objective'] = objectives
    comparison['tolerance'] = target.get('tolerance', target.get(
        'metric_tolerance', 0.0))
    comparison['not_selected'] = not_selected
    comparison['simulated'] = any(bool(entry['raw'].get('simulated'))
                                  for entry in entries)
    comparison['unknown'] = []
    if not objectives:
        comparison['unknown'].append({
            'field': 'objective',
            'reason': 'no candidate carried a measurable key metric; '
                      'selection fell back to input order',
        })
    if selected is None:
        comparison['reason'] = ('no candidate satisfies the hard constraints '
                               'and metric safeguards')
    else:
        comparison['reason'] = ('selected %s by lexicographic objective %s'
                                % (selected_id, objectives))
    schemas.validate_candidate_comparison(comparison)
    return comparison
