#!/usr/bin/env python3
"""Read/apply/save/export bridge for JLCEDA Pro (嘉立创EDA专业版).

This is a constrained executor adapter, not a general EDA API. It uses the
client's official CLI (`lceda-pro`) and the `eda` command space. The workflow is
deliberately read-first:

    read snapshot -> reconcile plan in Python -> send only typed primitive
    actions -> read back -> verify -> optionally save -> optionally reopen

It never sends user-supplied JavaScript. The only code sent to the client is the
fixed operation templates in this file plus JSON data. It does not place orders,
buy parts, or access the network.

Verified client: JLCEDA Pro 4.1.78.34f5b8d9 on Windows 11 (2026-10-21).
Other versions may expose different API signatures; run `doctor` first and
consult `lceda-pro doc api` rather than assuming this file is version-proof.

Exit codes:
  0  operation completed (or no candidates found)
  1  conflicts / partial / verification mismatch (inspect JSON)
  2  invalid input or unsafe session operation
  3  CLI unavailable or command failed before a result
  4  invoke timed out; objects may exist, re-read before retrying
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXIT_OK = 0
EXIT_REVIEW = 1
EXIT_INPUT = 2
EXIT_UNAVAILABLE = 3
EXIT_TIMEOUT = 4

PART_KEYS = {
    'designator', 'name', 'manufacturer', 'manufacturer_id', 'supplier',
    'supplier_id', 'other_property',
}
MATCH_KEYS = {'designator', 'unique_id', 'part', 'supplier_id', 'position'}
OP_KEYS = {
    'part': {'op', 'key', 'match', 'place', 'properties', 'add_into_bom', 'add_into_pcb', 'note'},
    'net_flag': {'op', 'key', 'net', 'type', 'at', 'rotation', 'mirror', 'note'},
    'net_port': {'op', 'key', 'net', 'direction', 'at', 'rotation', 'mirror', 'note'},
    'wire': {'op', 'key', 'net', 'points', 'note'},
    'delete': {'op', 'key', 'target', 'note'},
}
DELETE_KINDS = {'part', 'net_flag', 'net_port', 'wire'}
DELETE_EXPECTED_FIELDS = {
    'part': {'designator', 'unique_id', 'x', 'y', 'component'},
    'net_flag': {'name', 'net', 'x', 'y'},
    'net_port': {'net', 'direction', 'x', 'y'},
    'wire': {'net'},
}
# Deletion is destructive: these fields are mandatory identity/state checks.
DELETE_REQUIRED_FIELDS = {
    'part': ('designator', 'component', 'x', 'y'),
    'net_flag': ('name', 'x', 'y'),
    'net_port': ('net', 'direction', 'x', 'y'),
    'wire': ('net',),
}
NET_FLAG_TYPES = {'Power', 'Ground', 'AnalogGround', 'ProtectGround'}
NET_PORT_DIRECTIONS = {'IN', 'OUT', 'BI'}
# Client versions on which the readback semantics in this adapter were probed.
# A write is refused on other versions unless the caller explicitly overrides.
VERIFIED_CLIENT_PREFIXES = ('4.1.78',)


class EdaError(Exception):
    """Base error carrying a stable code for JSON output."""

    def __init__(self, message, code='EDA_ERROR', detail=None):
        super().__init__(message)
        self.code = code
        self.detail = detail


class EdaUnavailable(EdaError):
    def __init__(self, message, detail=None):
        super().__init__(message, 'EDA_UNAVAILABLE', detail)


class EdaCommandError(EdaError):
    def __init__(self, message, code='EDA_COMMAND_FAILED', detail=None):
        super().__init__(message, code, detail)


class EdaTimeout(EdaError):
    def __init__(self, message, detail=None):
        super().__init__(message, 'EDA_TIMEOUT', detail)


class EdaInputError(EdaError):
    def __init__(self, message, detail=None):
        super().__init__(message, 'INVALID_INPUT', detail)


def _finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise EdaInputError(f'{label}: finite number required')
    return float(value)


def _coord(value, label):
    number = _finite(value, label)
    if not -1_000_000 <= number <= 1_000_000:
        raise EdaInputError(f'{label}: outside allowed coordinate range')
    return number


def _text(value, label, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise EdaInputError(f'{label}: non-empty string required')
    return value


def _bool(value, label):
    if type(value) is not bool:
        raise EdaInputError(f'{label}: boolean required')
    return value


def _round(value):
    return round(float(value), 3)


def _canonical_segments(points):
    """Return an order-insensitive segment set for duplicate detection."""
    if isinstance(points, list) and points and isinstance(points[0], list):
        flat = [v for segment in points for v in segment]
    else:
        flat = list(points)
    if len(flat) < 4 or len(flat) % 2:
        raise EdaInputError('points: flat even-length coordinate list of at least 2 points required')
    coords = [_coord(v, 'points') for v in flat]
    pts = [(_round(coords[i]), _round(coords[i + 1])) for i in range(0, len(coords), 2)]
    segments = []
    for a, b in zip(pts, pts[1:]):
        if a == b:
            continue
        if a[0] != b[0] and a[1] != b[1]:
            raise EdaInputError('points: each segment must be horizontal or vertical')
        segments.append(tuple(sorted((a, b))))
    if not segments:
        raise EdaInputError('points: at least one non-zero segment required')
    return tuple(sorted(segments)), pts


def _zero_length_line(line):
    """True for a well-formed wire whose points are all identical.

    4.1.78 leaves such zero-length wire primitives on schematics. They carry
    no geometry and are editor normalization, not an unparsed wire.
    """
    try:
        if isinstance(line, list) and line and isinstance(line[0], list):
            flat = [value for segment in line for value in segment]
        else:
            flat = list(line)
        if len(flat) < 4 or len(flat) % 2:
            return False
        coords = [float(value) for value in flat]
        points = list(zip(coords[0::2], coords[1::2]))
        return all(a == b for a, b in zip(points, points[1:]))
    except (TypeError, ValueError):
        return False


def _segments_from_line(line):
    """Return (segments, parsed).

    A zero-length wire is parsed as an empty segment set. A line the adapter
    cannot parse (for example a diagonal wire) is reported as unparsed, never
    silently treated as absent.
    """
    try:
        segments, _ = _canonical_segments(line)
        return segments, True
    except EdaInputError:
        if _zero_length_line(line):
            return (), True
        return (), False


def _merge_intervals(intervals):
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _segment_covered(segment, actual_segments):
    """True when collinear actual segments jointly cover the target segment."""
    a, b = segment
    intervals = []
    if a[1] == b[1]:
        lo, hi = sorted((a[0], b[0]))
        for c, d in actual_segments:
            if c[1] == d[1] == a[1]:
                intervals.append(tuple(sorted((c[0], d[0]))))
    elif a[0] == b[0]:
        lo, hi = sorted((a[1], b[1]))
        for c, d in actual_segments:
            if c[0] == d[0] == a[0]:
                intervals.append(tuple(sorted((c[1], d[1]))))
    else:
        return False
    return any(start <= lo + 1e-9 and hi <= end + 1e-9 for start, end in _merge_intervals(intervals))


def _segments_overlap(first, second):
    """Positive-length collinear overlap; endpoint touching is not overlap."""
    a, b = first
    c, d = second
    if a[1] == b[1] == c[1] == d[1]:
        lo1, hi1 = sorted((a[0], b[0]))
        lo2, hi2 = sorted((c[0], d[0]))
        return min(hi1, hi2) - max(lo1, lo2) > 1e-9
    if a[0] == b[0] == c[0] == d[0]:
        lo1, hi1 = sorted((a[1], b[1]))
        lo2, hi2 = sorted((c[1], d[1]))
        return min(hi1, hi2) - max(lo1, lo2) > 1e-9
    return False


def _normalized_wire_net(snapshot):
    """Merge collinear same-net segments so editor splits do not look different."""
    by_net = {}
    for wire in snapshot.get('wires') or []:
        segments, _ = _segments_from_line(wire.get('line') or [])
        by_net.setdefault(wire.get('net') or '', []).extend(segments)
    normalized = set()
    for net, segments in by_net.items():
        horizontal, vertical = {}, {}
        for a, b in segments:
            if a[1] == b[1]:
                horizontal.setdefault(a[1], []).append(tuple(sorted((a[0], b[0]))))
            elif a[0] == b[0]:
                vertical.setdefault(a[0], []).append(tuple(sorted((a[1], b[1]))))
        for y, intervals in horizontal.items():
            for lo, hi in _merge_intervals(intervals):
                normalized.add((net, tuple(sorted(((lo, y), (hi, y))))))
        for x, intervals in vertical.items():
            for lo, hi in _merge_intervals(intervals):
                normalized.add((net, tuple(sorted(((x, lo), (x, hi))))))
    return normalized


def _is_cli_payload(value):
    """The CLI contract is a JSON object with ok/value at the top level.

    Ordinary log lines may also be JSON objects; accepting the first object
    would turn `{"level":"info"}` into a command result.
    """
    return isinstance(value, dict) and ('ok' in value or 'value' in value)


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    try:
        value = json.loads(text)
        if _is_cli_payload(value):
            return value
    except json.JSONDecodeError:
        pass
    for start, ch in enumerate(text):
        if ch != '{':
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
            if _is_cli_payload(value):
                return value
        except json.JSONDecodeError:
            continue
    return None


def find_cli(explicit=None):
    """Find the official client CLI without assuming a single install path."""
    candidates = []
    if explicit:
        resolved = shutil.which(explicit)
        candidates.append(resolved or explicit)
    for name in ('LCEDA_PRO_EXE', 'JLCEDA_PRO_EXE'):
        if os.environ.get(name):
            candidates.append(os.environ[name])
    for name in ('lceda-pro', 'lceda-pro.exe', 'easyeda-pro', 'easyeda-pro.exe'):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    home = Path.home()
    if os.name == 'nt':
        local = os.environ.get('LOCALAPPDATA')
        program_files = os.environ.get('ProgramFiles')
        if local:
            candidates.append(str(Path(local) / 'Programs' / 'lceda-pro' / 'lceda-pro.exe'))
        if program_files:
            candidates.append(str(Path(program_files) / 'lceda-pro' / 'lceda-pro.exe'))
        candidates.append(str(home / 'AppData' / 'Local' / 'Programs' / 'lceda-pro' / 'lceda-pro.exe'))
    else:
        candidates.extend([
            '/Applications/JLCEDA Pro.app/Contents/MacOS/lceda-pro',
            '/opt/lceda-pro/lceda-pro',
            str(home / 'Applications' / 'lceda-pro' / 'lceda-pro'),
        ])
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        try:
            path = Path(candidate).expanduser().resolve()
        except OSError:
            continue
        if path.is_file() and str(path) not in seen:
            seen.add(str(path))
            return str(path)
    return None


class LcedaPro:
    """Thin, typed wrapper over the official CLI. It does not parse JS itself."""

    def __init__(self, exe=None, timeout_ms=120000):
        self.exe = find_cli(exe)
        if not self.exe:
            raise EdaUnavailable(
                'lceda-pro CLI not found; install JLCEDA Pro or set LCEDA_PRO_EXE',
                {'searched': ['LCEDA_PRO_EXE', 'PATH', 'LOCALAPPDATA/Programs/lceda-pro']},
            )
        self.timeout_ms = timeout_ms

    def _run(self, args, timeout_ms=None):
        effective = timeout_ms or self.timeout_ms
        try:
            proc = subprocess.run(
                [self.exe, *args],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=effective / 1000.0,
            )
        except subprocess.TimeoutExpired as error:
            raise EdaTimeout(
                f'lceda-pro {args[0]} exceeded {effective} ms; inspect the project before retrying',
                {'stdout': (error.stdout or '')[-2000:], 'stderr': (error.stderr or '')[-2000:]},
            )
        except OSError as error:
            raise EdaUnavailable(f'cannot start lceda-pro: {error}')
        payload = _extract_json(proc.stdout) or _extract_json(proc.stderr)
        if payload is None:
            raise EdaCommandError(
                f'lceda-pro {args[0]} returned no JSON',
                'EDA_BAD_OUTPUT',
                {'exit_code': proc.returncode, 'stdout': proc.stdout[-2000:], 'stderr': proc.stderr[-2000:]},
            )
        if payload.get('ok') is False:
            error = payload.get('error')
            if not isinstance(error, dict):
                error = {'message': str(error) if error else 'lceda-pro reported failure'}
            code = error.get('code') or 'EDA_COMMAND_FAILED'
            message = error.get('message') or 'lceda-pro reported failure'
            if code in {'REQUEST_TIMEOUT', 'TIMEOUT'}:
                raise EdaTimeout(message, {'payload': payload})
            raise EdaCommandError(message, code, {'payload': payload})
        if 'value' not in payload:
            raise EdaCommandError(
                f'lceda-pro {args[0]} returned ok without a value',
                'EDA_BAD_OUTPUT',
                {'payload': payload},
            )
        return payload.get('value')

    def doctor(self):
        return self._run(['doctor'])

    def sessions(self):
        return self._run(['session', 'list']) or []

    def open_project(self, project, headless=True):
        path = str(Path(project).expanduser().resolve())
        if not Path(path).exists():
            raise EdaInputError(f'project path does not exist: {path}')
        args = ['open', '--path', path]
        if headless:
            args += ['--headless', 'true']
        value = self._run(args)
        if not isinstance(value, dict) or not value.get('sessionId'):
            raise EdaCommandError('open did not return a sessionId', 'EDA_OPEN_FAILED', {'value': value})
        return value['sessionId']

    def close_session(self, session, destroy=True):
        args = ['session', 'close', '--session', session]
        if destroy:
            args.append('--destroy')
        return self._run(args)

    def functions(self, session):
        return self._run(['functions', '--session', session])

    def invoke(self, session, code, args=None, timeout_ms=None):
        payload = _json_for_js(args if args is not None else {})
        source = f'const __ARGS__ = {payload};\n{code}'
        with tempfile.TemporaryDirectory(prefix='eda_exec_') as temp:
            op_path = Path(temp) / 'operation.js'
            op_path.write_text(source, encoding='utf-8')
            return self._run(
                [
                    'invoke', '--session', session, '--ext-uuid', 'eda',
                    '--code-file', str(op_path),
                    '--timeout', str(timeout_ms or self.timeout_ms),
                ],
                timeout_ms=timeout_ms,
            )


def _json_for_js(value):
    """JSON that is also a safe JavaScript literal for embedded strings."""
    text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return text.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Fixed operation templates. Keep these small and typed; do not accept user JS.
# ---------------------------------------------------------------------------

PAGE_SELECT_JS = r'''
const sleep = ms => new Promise(r => setTimeout(r, ms));
const safe = (fn, fallback = null) => { try { return fn(); } catch (e) { return fallback; } };
const safeAsync = async (fn, fallback = null) => { try { return await fn(); } catch (e) { return fallback; } };
const P = (A.page && typeof A.page === 'object') ? A.page : A;
let schs = [];
for (let i = 0; i < 12; i++) {
  schs = await safeAsync(() => eda.dmt_Schematic.getAllSchematicsInfo(), []);
  if (schs && schs.length) break;
  await sleep(600);
}
const allPages = [];
for (const s of (schs || [])) for (const p of (s.page || [])) allPages.push({ s, p });
let selected = null;
if (P.page_uuid) selected = allPages.find(x => x.p.uuid === P.page_uuid) || null;
else if (P.schematic_name) {
  const s = (schs || []).find(x => x.name === P.schematic_name || x.uuid === P.schematic_name);
  if (s) {
    const pages = s.page || [];
    if (!P.page_name && pages.length > 1) {
      // Picking the first page of a multi-page schematic is a guess, and a
      // guess here means writing to the wrong page. Require an explicit page.
      return { ok: false, error: 'ambiguous_schematic_page', schematic: s.name,
               pages: pages.map(p => p.name) };
    }
    const p = P.page_name ? pages.find(x => x.name === P.page_name) : pages[0];
    if (p) selected = { s, p };
  }
} else {
  const current = await safeAsync(() => eda.dmt_SelectControl.getCurrentDocumentInfo());
  if (current && current.documentType === 1) selected = allPages.find(x => x.p.uuid === current.uuid) || null;
}
if (!selected) return { ok: false, error: 'page_not_found', selection: P };
let tabId = null;
try {
  tabId = await eda.dmt_EditorControl.openDocument(selected.p.uuid);
  // openDocument opens a tab but does not necessarily give it focus (4.1.78).
  // Export/netlist follow the active document, so activate it explicitly.
  if (tabId) await safeAsync(() => eda.dmt_EditorControl.activateDocument(tabId));
} catch (e) {
  return { ok: false, error: 'open_document_failed', message: String(e && e.message || e), page: selected.p.uuid };
}
await Promise.race([
  safeAsync(() => eda.dmt_EditorControl.waitForDocumentReady(8000)),
  sleep(8500),
]);
let activatedConfirmed = false;
for (let i = 0; i < 12; i++) {
  const current = await safeAsync(() => eda.dmt_SelectControl.getCurrentDocumentInfo());
  if (current && current.documentType === 1 && current.uuid === selected.p.uuid) {
    activatedConfirmed = true;
    break;
  }
  await sleep(300);
}
if (!activatedConfirmed) {
  return { ok: false, error: 'page_not_activated', page: selected.p.uuid,
           note: 'openDocument/activateDocument did not make the requested page the active document' };
}
const settle = Number.isFinite(Number(P.settle_ms)) ? Math.max(0, Math.min(30000, Number(P.settle_ms))) : 300;
await sleep(settle);
'''

SNAPSHOT_JS = r'''
const A = __ARGS__;
''' + PAGE_SELECT_JS + r'''
const env = {
  online: safe(() => eda.sys_Environment.isOnlineMode()),
  half_offline: safe(() => eda.sys_Environment.isHalfOfflineMode()),
  offline: safe(() => eda.sys_Environment.isOfflineMode()),
  version: safe(() => eda.sys_Environment.getEditorCurrentVersion()),
  client: safe(() => eda.sys_Environment.isClient()),
  jlc_pro: safe(() => eda.sys_Environment.isJLCEDAProEdition()),
};
const read_errors = [];
const errorText = (e) => String((e && e.message) || e);
const fail = (scope, field, e, extra) => {
  read_errors.push(Object.assign({ scope, field, error: errorText(e) }, extra || {}));
};
const readField = (obj, field, fn, scope, extra) => {
  try { return fn(); } catch (e) { fail(scope, field, e, extra); return null; }
};
const primitiveId = (c) => safe(() => c.getState_PrimitiveId());
const componentName = (c) => {
  const value = safe(() => c.getState_Component());
  return value && value.name ? value.name : null;
};
const symbolName = (c) => {
  const value = safe(() => c.getState_Symbol());
  return value && value.name ? value.name : null;
};
const flagTypeOf = (name) => {
  if (!name) return null;
  if (/ProtectGround/i.test(name)) return 'ProtectGround';
  if (/AnalogGround/i.test(name)) return 'AnalogGround';
  if (/Ground/i.test(name)) return 'Ground';
  if (/Power/i.test(name)) return 'Power';
  return null;
};
const portDirectionOf = (name) => {
  const match = /Netport-(IN|OUT|BI)/i.exec(name || '');
  return match ? match[1].toUpperCase() : null;
};
const project = await safeAsync(() => eda.dmt_Project.getCurrentProjectInfo());
const pageInfo = await safeAsync(() => eda.dmt_Schematic.getSchematicPageInfo(selected.p.uuid));
const tb = (pageInfo && pageInfo.titleBlockData) || {};
const pageFacts = {
  width: safe(() => tb.Width.value),
  height: safe(() => tb.Height.value),
  size: safe(() => tb.Size.value),
  title_block_position: safe(() => tb['Title Block Position'].value),
  border: safe(() => tb.Border.value),
  title_block: safe(() => tb['Title Block'].value),
};
const comps = await eda.sch_PrimitiveComponent.getAll();
const wires = await eda.sch_PrimitiveWire.getAll();
let pinsComplete = A.include_pins !== false;
const pinBudget = A.max_pins || 6000;
let pinsUsed = 0;
const parts = [];
const netflags = [];
const netports = [];
const unclassified = [];
for (const c of comps) {
  const pid = primitiveId(c);
  let componentType = null;
  try { componentType = c.getState_ComponentType(); }
  catch (e) { fail('component', 'getState_ComponentType', e, { primitive_id: pid }); }
  if (componentType === 'part') {
    parts.push({
      primitive_id: readField(c, 'getState_PrimitiveId', () => c.getState_PrimitiveId(), 'part', { primitive_id: pid }),
      component_type: componentType,
      designator: readField(c, 'getState_Designator', () => c.getState_Designator(), 'part', { primitive_id: pid }),
      name: readField(c, 'getState_Name', () => c.getState_Name(), 'part', { primitive_id: pid }),
      x: readField(c, 'getState_X', () => c.getState_X(), 'part', { primitive_id: pid }),
      y: readField(c, 'getState_Y', () => c.getState_Y(), 'part', { primitive_id: pid }),
      rotation: readField(c, 'getState_Rotation', () => c.getState_Rotation(), 'part', { primitive_id: pid }),
      mirror: readField(c, 'getState_Mirror', () => c.getState_Mirror(), 'part', { primitive_id: pid }),
      add_into_bom: readField(c, 'getState_AddIntoBom', () => c.getState_AddIntoBom(), 'part', { primitive_id: pid }),
      add_into_pcb: readField(c, 'getState_AddIntoPcb', () => c.getState_AddIntoPcb(), 'part', { primitive_id: pid }),
      unique_id: readField(c, 'getState_UniqueId', () => c.getState_UniqueId(), 'part', { primitive_id: pid }),
      component: readField(c, 'getState_Component', () => c.getState_Component(), 'part', { primitive_id: pid }),
      symbol: readField(c, 'getState_Symbol', () => c.getState_Symbol(), 'part', { primitive_id: pid }),
      footprint: readField(c, 'getState_Footprint', () => c.getState_Footprint(), 'part', { primitive_id: pid }),
      sub_part_name: readField(c, 'getState_SubPartName', () => c.getState_SubPartName(), 'part', { primitive_id: pid }),
      manufacturer: readField(c, 'getState_Manufacturer', () => c.getState_Manufacturer(), 'part', { primitive_id: pid }),
      manufacturer_id: readField(c, 'getState_ManufacturerId', () => c.getState_ManufacturerId(), 'part', { primitive_id: pid }),
      supplier: readField(c, 'getState_Supplier', () => c.getState_Supplier(), 'part', { primitive_id: pid }),
      supplier_id: readField(c, 'getState_SupplierId', () => c.getState_SupplierId(), 'part', { primitive_id: pid }),
      other_property: A.include_properties === false ? null
        : readField(c, 'getState_OtherProperty', () => c.getState_OtherProperty(), 'part', { primitive_id: pid }),
      pins: [],
    });
  } else if (componentType === 'netflag') {
    const sym = symbolName(c);
    netflags.push({
      primitive_id: readField(c, 'getState_PrimitiveId', () => c.getState_PrimitiveId(), 'netflag', { primitive_id: pid }),
      component_type: componentType,
      name: readField(c, 'getState_Name', () => c.getState_Name(), 'netflag', { primitive_id: pid }),
      net: readField(c, 'getState_Net', () => c.getState_Net(), 'netflag', { primitive_id: pid }),
      flag_type: flagTypeOf(sym || componentName(c)),
      symbol_name: sym,
      component_name: componentName(c),
      x: readField(c, 'getState_X', () => c.getState_X(), 'netflag', { primitive_id: pid }),
      y: readField(c, 'getState_Y', () => c.getState_Y(), 'netflag', { primitive_id: pid }),
      rotation: readField(c, 'getState_Rotation', () => c.getState_Rotation(), 'netflag', { primitive_id: pid }),
      mirror: readField(c, 'getState_Mirror', () => c.getState_Mirror(), 'netflag', { primitive_id: pid }),
    });
  } else if (componentType === 'netport') {
    const sym = symbolName(c);
    netports.push({
      primitive_id: readField(c, 'getState_PrimitiveId', () => c.getState_PrimitiveId(), 'netport', { primitive_id: pid }),
      component_type: componentType,
      net: readField(c, 'getState_Net', () => c.getState_Net(), 'netport', { primitive_id: pid }),
      name: readField(c, 'getState_Name', () => c.getState_Name(), 'netport', { primitive_id: pid }),
      direction: portDirectionOf(sym || componentName(c)),
      symbol_name: sym,
      component_name: componentName(c),
      x: readField(c, 'getState_X', () => c.getState_X(), 'netport', { primitive_id: pid }),
      y: readField(c, 'getState_Y', () => c.getState_Y(), 'netport', { primitive_id: pid }),
      rotation: readField(c, 'getState_Rotation', () => c.getState_Rotation(), 'netport', { primitive_id: pid }),
      mirror: readField(c, 'getState_Mirror', () => c.getState_Mirror(), 'netport', { primitive_id: pid }),
    });
  } else {
    unclassified.push({ primitive_id: pid, component_type: componentType });
  }
}
if (pinsComplete) {
  for (const part of parts) {
    if (pinsUsed >= pinBudget) {
      pinsComplete = false;
      fail('pins', 'max_pins', new Error('pin budget exhausted'), { primitive_id: part.primitive_id, limit: pinBudget });
      break;
    }
    try {
      const pins = await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(part.primitive_id);
      part.pins = (pins || []).map(p => ({ ...p }));
      pinsUsed += part.pins.length;
    } catch (e) {
      pinsComplete = false;
      fail('pins', 'getAllPinsByPrimitiveId', e, { primitive_id: part.primitive_id });
    }
  }
}
let attributes = [];
let attributesComplete = null;
if (A.include_attributes) {
  attributesComplete = true;
  try {
    const raw = await eda.sch_PrimitiveAttribute.getAll();
    if (raw.length > 500) {
      attributesComplete = false;
      fail('attributes', 'truncated', new Error('attribute count exceeds 500'), { count: raw.length });
    }
    attributes = raw.slice(0, 500).map(a => {
      const names = Object.getOwnPropertyNames(Object.getPrototypeOf(a)).filter(k => k.startsWith('getState_'));
      return Object.fromEntries(names.map(k => [k, safe(() => a[k]())]));
    });
  } catch (e) {
    attributesComplete = false;
    fail('attributes', 'getAll', e);
  }
}
const classified = parts.length + netflags.length + netports.length + unclassified.length;
const componentsConsistent = comps.length === classified;
if (!componentsConsistent) {
  fail('snapshot', 'component_count_mismatch', new Error('classified count does not equal getAll count'),
       { components: comps.length, classified });
}
const complete = read_errors.length === 0 && pinsComplete
  && (A.include_attributes !== true || attributesComplete === true)
  && componentsConsistent;
return {
  ok: true,
  env,
  project: project ? {
    uuid: project.uuid,
    friendly_name: project.friendlyName,
    name: project.name,
    path: project.path,
  } : null,
  selection: {
    basis: A.page_uuid ? 'page_uuid' : (A.schematic_name ? 'schematic_name' : 'current_or_first'),
    schematic_uuid: selected.s.uuid,
    schematic_name: selected.s.name,
    page_uuid: selected.p.uuid,
    page_name: selected.p.name,
  },
  page: pageFacts,
  counts: {
    components: comps.length,
    parts: parts.length,
    netflags: netflags.length,
    netports: netports.length,
    unclassified: unclassified.length,
    wires: wires.length,
    attributes: A.include_attributes ? attributes.length : null,
  },
  integrity: {
    status: complete ? 'complete' : 'incomplete',
    read_errors,
    pins_complete: pinsComplete,
    pins_used: pinsUsed,
    attributes_complete: attributesComplete,
    components_consistent: componentsConsistent,
    components_seen: comps.length,
    components_classified: classified,
  },
  parts,
  netflags,
  netports,
  unclassified,
  wires: wires.map(w => ({
    primitive_id: safe(() => w.getState_PrimitiveId()),
    net: safe(() => w.getState_Net()),
    line: safe(() => w.getState_Line()),
    color: safe(() => w.getState_Color()),
    line_width: safe(() => w.getState_LineWidth()),
    line_type: safe(() => w.getState_LineType()),
  })),
  attributes,
  coverage: {
    pins_complete: pinsComplete,
    pins_used: pinsUsed,
    attributes_included: A.include_attributes === true,
    attributes_complete: attributesComplete,
    read_errors: read_errors.length,
    not_checked: [
      'netlist pin-net equivalence until getNetlistFile is parsed',
      'PCB binding/placement', 'DRC', 'saved state and reopen persistence',
      'user edits made after this snapshot',
    ],
  },
};
'''

PROJECT_PROBE_JS = r'''
const safe = (fn, fallback = null) => { try { return fn(); } catch (e) { return fallback; } };
const safeAsync = async (fn, fallback = null) => { try { return await fn(); } catch (e) { return fallback; } };
const env = {
  online: safe(() => eda.sys_Environment.isOnlineMode()),
  half_offline: safe(() => eda.sys_Environment.isHalfOfflineMode()),
  offline: safe(() => eda.sys_Environment.isOfflineMode()),
  version: safe(() => eda.sys_Environment.getEditorCurrentVersion()),
};
const project = await safeAsync(() => eda.dmt_Project.getCurrentProjectInfo());
const schs = await safeAsync(() => eda.dmt_Schematic.getAllSchematicsInfo(), []);
return {
  ok: true,
  env,
  project: project ? { uuid: project.uuid, friendly_name: project.friendlyName, name: project.name, path: project.path } : null,
  schematics: (schs || []).map(s => ({ uuid: s.uuid, name: s.name, pages: (s.page || []).map(p => ({ uuid: p.uuid, name: p.name })) })),
};
'''

PROJECT_DESIGNATORS_JS = r'''
const A = __ARGS__;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const safe = (fn, fallback = null) => { try { return fn(); } catch (e) { return fallback; } };
const safeAsync = async (fn, fallback = null) => { try { return await fn(); } catch (e) { return fallback; } };
const env = {
  online: safe(() => eda.sys_Environment.isOnlineMode()),
  half_offline: safe(() => eda.sys_Environment.isHalfOfflineMode()),
  offline: safe(() => eda.sys_Environment.isOfflineMode()),
  version: safe(() => eda.sys_Environment.getEditorCurrentVersion()),
};
const project = await safeAsync(() => eda.dmt_Project.getCurrentProjectInfo());
const original = await safeAsync(() => eda.dmt_SelectControl.getCurrentDocumentInfo());
let schs = [];
for (let i = 0; i < 12; i++) {
  schs = await safeAsync(() => eda.dmt_Schematic.getAllSchematicsInfo(), []);
  if (schs && schs.length) break;
  await sleep(600);
}
const pages = [];
const designators = [];
const errors = [];
for (const s of (schs || [])) {
  for (const p of (s.page || [])) {
    try {
      const tab = await eda.dmt_EditorControl.openDocument(p.uuid);
      if (tab) await safeAsync(() => eda.dmt_EditorControl.activateDocument(tab));
      let active = false;
      for (let i = 0; i < 24; i++) {
        await sleep(250);
        const current = await safeAsync(() => eda.dmt_SelectControl.getCurrentDocumentInfo());
        if (current && current.uuid === p.uuid) { active = true; break; }
      }
      if (!active) {
        errors.push({ page_uuid: p.uuid, page_name: p.name, error: 'page_not_activated' });
        continue;
      }
      const comps = await eda.sch_PrimitiveComponent.getAll();
      let count = 0;
      for (const c of comps) {
        let componentType = null;
        try { componentType = c.getState_ComponentType(); }
        catch (e) {
          errors.push({ page_uuid: p.uuid, page_name: p.name, error: 'component_type_read_failed',
                        message: String((e && e.message) || e) });
          continue;
        }
        if (componentType !== 'part') continue;
        count += 1;
        const component = safe(() => c.getState_Component());
        designators.push({
          designator: safe(() => c.getState_Designator()),
          unique_id: safe(() => c.getState_UniqueId()),
          primitive_id: safe(() => c.getState_PrimitiveId()),
          component_name: component && component.name ? component.name : null,
          supplier_id: safe(() => c.getState_SupplierId()),
          schematic_uuid: s.uuid, schematic_name: s.name,
          page_uuid: p.uuid, page_name: p.name,
        });
      }
      pages.push({ schematic_uuid: s.uuid, schematic_name: s.name,
                   page_uuid: p.uuid, page_name: p.name, parts: count });
    } catch (e) {
      errors.push({ page_uuid: p.uuid, page_name: p.name, error: 'page_scan_failed',
                    message: String((e && e.message) || e) });
    }
  }
}
if (original && original.uuid) {
  try {
    const tab = await eda.dmt_EditorControl.openDocument(original.uuid);
    if (tab) await safeAsync(() => eda.dmt_EditorControl.activateDocument(tab));
  } catch (e) { /* restoring focus is best effort */ }
}
return {
  ok: true,
  env,
  project: project ? { uuid: project.uuid, friendly_name: project.friendlyName, name: project.name, path: project.path } : null,
  pages, designators, errors,
  complete: errors.length === 0,
  note: 'scanning pages changes the active document in this owned CLI session; focus is restored best-effort',
};
'''

PCB_SELECT_JS = r'''
const sleep = ms => new Promise(r => setTimeout(r, ms));
const safe = (fn, fallback = null) => { try { return fn(); } catch (e) { return fallback; } };
const safeAsync = async (fn, fallback = null) => { try { return await fn(); } catch (e) { return fallback; } };
const P = (A.pcb && typeof A.pcb === 'object') ? A.pcb : A;
let pcbs = [];
for (let i = 0; i < 12; i++) {
  pcbs = await safeAsync(() => eda.dmt_Pcb.getAllPcbsInfo(), []);
  if (pcbs && pcbs.length) break;
  await sleep(600);
}
const pcbId = (x) => x && (x.uuid || x.pcbUuid);
let selected = null;
if (P.pcb_uuid) selected = (pcbs || []).find(x => pcbId(x) === P.pcb_uuid) || null;
else if (P.pcb_name) {
  const matches = (pcbs || []).filter(x => x.name === P.pcb_name);
  if (matches.length !== 1) {
    return { ok: false, error: matches.length === 0 ? 'pcb_not_found' : 'ambiguous_pcb_name',
             pcb_name: P.pcb_name,
             candidates: matches.map(x => ({ uuid: pcbId(x), name: x.name })) };
  }
  selected = matches[0];
} else if ((pcbs || []).length === 1) {
  // Exactly one PCB in the project: selection is deterministic, not a guess.
  selected = pcbs[0];
} else {
  const current = await safeAsync(() => eda.dmt_SelectControl.getCurrentDocumentInfo());
  if (current && current.documentType === 3) {
    selected = (pcbs || []).find(x => pcbId(x) === current.uuid) || null;
  }
}
if (!selected) {
  return { ok: false, error: 'pcb_not_found', selection: P,
           pcbs: (pcbs || []).map(x => ({ uuid: pcbId(x), name: x.name })) };
}
const pcbUuid = pcbId(selected);
let tabId = null;
try {
  tabId = await eda.dmt_EditorControl.openDocument(pcbUuid);
  // openDocument opens a tab but does not necessarily give it focus (4.1.78).
  if (tabId) await safeAsync(() => eda.dmt_EditorControl.activateDocument(tabId));
} catch (e) {
  return { ok: false, error: 'open_document_failed', message: String(e && e.message || e), pcb_uuid: pcbUuid };
}
await Promise.race([
  safeAsync(() => eda.dmt_EditorControl.waitForDocumentReady(8000)),
  sleep(8500),
]);
let activatedConfirmed = false;
for (let i = 0; i < 12; i++) {
  const current = await safeAsync(() => eda.dmt_SelectControl.getCurrentDocumentInfo());
  if (current && current.documentType === 3 && current.uuid === pcbUuid) {
    activatedConfirmed = true;
    break;
  }
  await sleep(300);
}
if (!activatedConfirmed) {
  return { ok: false, error: 'pcb_not_activated', pcb_uuid: pcbUuid,
           note: 'openDocument/activateDocument did not make the requested PCB the active document' };
}
const settle = Number.isFinite(Number(P.settle_ms)) ? Math.max(0, Math.min(30000, Number(P.settle_ms))) : 300;
await sleep(settle);
'''

PCB_SNAPSHOT_JS = r'''
const A = __ARGS__;
''' + PCB_SELECT_JS + r'''
const env = {
  online: safe(() => eda.sys_Environment.isOnlineMode()),
  half_offline: safe(() => eda.sys_Environment.isHalfOfflineMode()),
  offline: safe(() => eda.sys_Environment.isOfflineMode()),
  version: safe(() => eda.sys_Environment.getEditorCurrentVersion()),
  client: safe(() => eda.sys_Environment.isClient()),
};
const read_errors = [];
const field_notes = [];
const errorText = (e) => String((e && e.message) || e);
const fail = (scope, field, e) => {
  read_errors.push({ scope, field, error: errorText(e) });
};
const note = (scope, field, e) => {
  field_notes.push({ scope, field, error: errorText(e) });
};
const readField = async (fn, scope, field) => {
  try { return await fn(); } catch (e) { fail(scope, field, e); return null; }
};
const budget = Number.isFinite(Number(A.max_primitives)) ? Math.max(1, Math.min(10000, Number(A.max_primitives))) : 2000;
const project = await safeAsync(() => eda.dmt_Project.getCurrentProjectInfo());
const counts = {};
const list = async (name, fn) => {
  const items = await readField(fn, name, 'getAll');
  counts[name] = Array.isArray(items) ? items.length : null;
  return items;
};
const components = await list('components', () => eda.pcb_PrimitiveComponent.getAll());
const lines = await list('lines', () => eda.pcb_PrimitiveLine.getAll());
const vias = await list('vias', () => eda.pcb_PrimitiveVia.getAll());
const pours = await list('pours', () => eda.pcb_PrimitivePour.getAll());
const poured = await list('poured', () => eda.pcb_PrimitivePoured.getAll());
const pads = await list('pads', () => eda.pcb_PrimitivePad.getAll());
const trimmed = (items) => {
  const total = Array.isArray(items) ? items.length : 0;
  return { items: (items || []).slice(0, budget), truncated: total > budget, total };
};
// Field-level getter failures are recorded as notes, not errors: an unknown
// getter name means we do not read that field, while a failed getAll means we
// cannot trust the class count at all. Only the latter blocks writes.
const state = (obj, fn, scope, field) => {
  try { return fn(obj); } catch (e) { note(scope, field, e); return null; }
};
const silentOf = (obj, names) => {
  for (const name of names) {
    try { const value = obj[name](); if (value !== null && value !== undefined) return value; } catch (e) { /* optional field */ }
  }
  return null;
};
const firstOf = (obj, getters, scope, field) => {
  for (const name of getters) {
    try { return obj[name](); } catch (e) { /* try the next candidate */ }
  }
  note(scope, field, 'no getter matched: ' + getters.join(', '));
  return null;
};
const nameOf = (value) => {
  if (value && typeof value === 'object' && value.name) return value.name;
  if (typeof value === 'string') return value;
  return null;
};
const componentRows = trimmed(components || []).items.map((c) => ({
  id: state(c, (x) => x.getState_PrimitiveId(), 'components', 'primitive_id'),
  designator: state(c, (x) => x.getState_Designator(), 'components', 'designator'),
  layer: state(c, (x) => x.getState_Layer(), 'components', 'layer'),
  x: firstOf(c, ['getState_X', 'getState_PositionX'], 'components', 'x'),
  y: firstOf(c, ['getState_Y', 'getState_PositionY'], 'components', 'y'),
  rotation: firstOf(c, ['getState_Rotation', 'getState_Angle'], 'components', 'rotation'),
  footprint: nameOf(state(c, (x) => x.getState_Footprint(), 'components', 'footprint')),
  component: nameOf(state(c, (x) => x.getState_Component(), 'components', 'component')),
}));
const lineRows = trimmed(lines || []).items.map((l) => ({
  id: state(l, (x) => x.getState_PrimitiveId(), 'lines', 'primitive_id'),
  net: state(l, (x) => x.getState_Net(), 'lines', 'net'),
  layer: state(l, (x) => x.getState_Layer(), 'lines', 'layer'),
  x1: firstOf(l, ['getState_StartX', 'getState_X1'], 'lines', 'x1'),
  y1: firstOf(l, ['getState_StartY', 'getState_Y1'], 'lines', 'y1'),
  x2: firstOf(l, ['getState_EndX', 'getState_X2'], 'lines', 'x2'),
  y2: firstOf(l, ['getState_EndY', 'getState_Y2'], 'lines', 'y2'),
  width: state(l, (x) => x.getState_LineWidth(), 'lines', 'width'),
}));
const viaRows = trimmed(vias || []).items.map((v) => ({
  id: state(v, (x) => x.getState_PrimitiveId(), 'vias', 'primitive_id'),
  net: state(v, (x) => x.getState_Net(), 'vias', 'net'),
  x: firstOf(v, ['getState_X', 'getState_PositionX'], 'vias', 'x'),
  y: firstOf(v, ['getState_Y', 'getState_PositionY'], 'vias', 'y'),
  hole: state(v, (x) => x.getState_HoleDiameter(), 'vias', 'hole'),
  diameter: state(v, (x) => x.getState_Diameter(), 'vias', 'diameter'),
}));
const pourRows = trimmed(pours || []).items.map((p) => ({
  id: state(p, (x) => x.getState_PrimitiveId(), 'pours', 'primitive_id'),
  net: state(p, (x) => x.getState_Net(), 'pours', 'net'),
  layer: state(p, (x) => x.getState_Layer(), 'pours', 'layer'),
  name: silentOf(p, ['getState_Name']),
}));
const pouredRows = trimmed(poured || []).items.map((p) => ({
  id: state(p, (x) => x.getState_PrimitiveId(), 'poured', 'primitive_id'),
  net: silentOf(p, ['getState_Net']),
  layer: silentOf(p, ['getState_Layer']),
}));
const padRows = trimmed(pads || []).items.map((p) => ({
  id: state(p, (x) => x.getState_PrimitiveId(), 'pads', 'primitive_id'),
  net: state(p, (x) => x.getState_Net(), 'pads', 'net'),
}));
const netNames = await readField(() => eda.pcb_Net.getAllNetsName(), 'nets', 'getAllNetsName');
const netRows = [];
if (Array.isArray(netNames)) {
  for (const n of netNames.slice(0, budget)) {
    const length = await readField(() => eda.pcb_Net.getNetLength(n), 'nets', 'getNetLength');
    const prims = await readField(() => eda.pcb_Net.getAllPrimitivesByNet(n), 'nets', 'getAllPrimitivesByNet');
    netRows.push({ net: n, length, primitive_count: Array.isArray(prims) ? prims.length : null });
  }
}
const outlineLines = (lines || []).filter(l => { try { return l.getState_Layer() === 11; } catch (e) { return false; } })
  .map(l => ({ id: state(l, (x) => x.getState_PrimitiveId(), 'lines', 'primitive_id'), layer: 11 }));
return {
  ok: true,
  env,
  project: project ? { uuid: project.uuid, friendly_name: project.friendlyName, name: project.name, path: project.path } : null,
  pcbs: (pcbs || []).map(x => ({ uuid: pcbId(x), name: x.name })),
  selection: { pcb_uuid: pcbUuid, pcb_name: selected.name },
  counts,
  components: { rows: componentRows, truncated: trimmed(components || []).truncated, total: trimmed(components || []).total },
  lines: { rows: lineRows, truncated: trimmed(lines || []).truncated, total: trimmed(lines || []).total },
  vias: { rows: viaRows, truncated: trimmed(vias || []).truncated, total: trimmed(vias || []).total },
  pours: { rows: pourRows, truncated: trimmed(pours || []).truncated, total: trimmed(pours || []).total },
  poured: { rows: pouredRows, truncated: trimmed(poured || []).truncated, total: trimmed(poured || []).total },
  pads: { rows: padRows, truncated: trimmed(pads || []).truncated, total: trimmed(pads || []).total },
  nets: netRows,
  outline: { lines: outlineLines, count: outlineLines.length },
  rule_config: safe(() => eda.pcb_Drc.getCurrentRuleConfigurationName()),
  read_errors,
  field_notes,
  note: 'pours counts the outline, poured counts actual copper fills; they are not interchangeable',
};
'''

PCB_APPLY_JS = r'''
const A = __ARGS__;
''' + PCB_SELECT_JS + r'''
const errorText = (e) => String((e && e.message) || e);
const state = (obj, fn) => { try { return fn(obj); } catch (e) { return null; } };
const pouredCount = async () => {
  const v = await safeAsync(() => eda.pcb_PrimitivePoured.getAll(), null);
  return Array.isArray(v) ? v.length : null;
};
const readback = (prim) => {
  if (!prim) return { created: false, error: 'create returned nothing' };
  return {
    created: true,
    id: state(prim, (x) => x.getState_PrimitiveId()),
    net: state(prim, (x) => x.getState_Net()),
    layer: state(prim, (x) => x.getState_Layer()),
    width: state(prim, (x) => x.getState_LineWidth()),
    hole: state(prim, (x) => x.getState_HoleDiameter()),
    diameter: state(prim, (x) => x.getState_Diameter()),
    designator: state(prim, (x) => x.getState_Designator()),
    name: state(prim, (x) => x.getState_Name()),
  };
};
const results = [];
const poured_before = await pouredCount();
for (const action of (A.actions || [])) {
  try {
    let prim = null;
    if (action.op === 'line') {
      prim = await eda.pcb_PrimitiveLine.create(action.net, action.layer, action.x1, action.y1, action.x2, action.y2, action.width, false);
    } else if (action.op === 'via') {
      prim = await eda.pcb_PrimitiveVia.create(action.net, action.x, action.y, action.hole, action.diameter, 0, null, null, false);
    } else if (action.op === 'pour_outline') {
      const poly = await eda.pcb_MathPolygon.createComplexPolygon([['R', action.x, action.y, action.w, action.h, 0, 0]]);
      if (!poly) throw new Error('polygon create returned nothing');
      prim = await eda.pcb_PrimitivePour.create(action.net, action.layer, poly, 'solid', false, action.name, 0, 10, false);
    } else if (action.op === 'component_flat') {
      prim = await eda.pcb_PrimitiveComponent.create({ libraryUuid: action.library_uuid, uuid: action.component_uuid }, action.layer, action.x, action.y, action.rotation, false);
    } else if (action.op === 'component_search') {
      const found = await eda.lib_Device.search(action.name, undefined, undefined, undefined, 5, 1);
      if (!Array.isArray(found) || !found.length) throw new Error('no search result for ' + action.name);
      const match = found.find(d => d.name === action.name) || found[0];
      prim = await eda.pcb_PrimitiveComponent.create(match, action.layer, action.x, action.y, action.rotation, false);
    } else {
      throw new Error('unknown op ' + action.op);
    }
    await sleep(500);
    results.push(Object.assign({ key: action.key, op: action.op }, readback(prim)));
  } catch (e) {
    results.push({ key: action.key, op: action.op, created: false, error: errorText(e) });
  }
}
const poured_after = await pouredCount();
return {
  ok: true,
  results,
  poured_before,
  poured_after,
  poured_delta: (poured_before === null || poured_after === null) ? null : (poured_after - poured_before),
  note: 'pour outlines create the border only; a non-zero poured_delta means the client recomputed copper fills',
};
'''

PCB_SAVE_JS = r'''
const A = __ARGS__;
''' + PCB_SELECT_JS + r'''
const saved = await safeAsync(() => eda.pcb_Document.save(), false);
const counts = {};
for (const [name, fn] of [
  ['components', () => eda.pcb_PrimitiveComponent.getAll()],
  ['lines', () => eda.pcb_PrimitiveLine.getAll()],
  ['vias', () => eda.pcb_PrimitiveVia.getAll()],
  ['pours', () => eda.pcb_PrimitivePour.getAll()],
  ['poured', () => eda.pcb_PrimitivePoured.getAll()],
]) {
  const v = await safeAsync(fn, null);
  counts[name] = Array.isArray(v) ? v.length : null;
}
return { ok: true, saved: saved === true, saved_value: saved, counts };
'''

PCB_DRC_JS = r'''
const A = __ARGS__;
''' + PCB_SELECT_JS + r'''
const raw = await safeAsync(() => eda.pcb_Drc.check(false, false, false), null);
const structure = raw === null ? 'null' : Array.isArray(raw) ? 'array' : typeof raw;
return {
  ok: true,
  ran: raw !== null,
  structure,
  item_count: Array.isArray(raw) ? raw.length : null,
  raw,
  note: 'raw DRC result; interpretation is the caller\'s job, zero items does not mean manufacturable',
};
'''

PCB_EXPORT_JS = r'''
const A = __ARGS__;
''' + PCB_SELECT_JS + r'''
const getters = {
  gerber: () => eda.pcb_ManufactureData.getGerberFile(),
  pickandplace: () => eda.pcb_ManufactureData.getPickAndPlaceFile(),
  bom: () => eda.pcb_ManufactureData.getBomFile(),
  pdf: () => eda.pcb_ManufactureData.getPdfFile(),
  pcb_info: () => eda.pcb_ManufactureData.getPcbInfoFile(),
};
const fn = getters[A.kind];
if (!fn) return { ok: false, error: 'unknown_export_kind', kind: A.kind };
const raw = await safeAsync(fn, null);
const structure = raw === null ? 'null' : Array.isArray(raw) ? 'array' : typeof raw;
let hint = null;
if (typeof raw === 'string') hint = raw.slice(0, 200);
else if (raw && typeof raw === 'object') hint = Object.keys(raw).slice(0, 12);
return { ok: true, kind: A.kind, structure, hint, raw,
         note: 'ordering methods (placePcbOrder and friends) are intentionally not exposed' };
'''

APPLY_JS = r'''
const A = __ARGS__;
''' + PAGE_SELECT_JS + r'''
const componentName = (c) => {
  const value = safe(() => c.getState_Component());
  return value && value.name ? value.name : null;
};
const symbolNameOf = (c) => {
  const value = safe(() => c.getState_Symbol());
  return value && value.name ? value.name : null;
};
const portDirectionOf = (name) => {
  const match = /Netport-(IN|OUT|BI)/i.exec(name || '');
  return match ? match[1].toUpperCase() : null;
};
const flagTypeOf = (name) => {
  if (!name) return null;
  if (/ProtectGround/i.test(name)) return 'ProtectGround';
  if (/AnalogGround/i.test(name)) return 'AnalogGround';
  if (/Ground/i.test(name)) return 'Ground';
  if (/Power/i.test(name)) return 'Power';
  return null;
};
const env = {
  online: safe(() => eda.sys_Environment.isOnlineMode()),
  half_offline: safe(() => eda.sys_Environment.isHalfOfflineMode()),
  offline: safe(() => eda.sys_Environment.isOfflineMode()),
  version: safe(() => eda.sys_Environment.getEditorCurrentVersion()),
};
const project = await safeAsync(() => eda.dmt_Project.getCurrentProjectInfo());
const sleep2 = ms => new Promise(r => setTimeout(r, ms));
const stateOf = (c) => c ? {
  designator: safe(() => c.getState_Designator()),
  unique_id: safe(() => c.getState_UniqueId()),
  x: safe(() => c.getState_X()), y: safe(() => c.getState_Y()),
  rotation: safe(() => c.getState_Rotation()), mirror: safe(() => c.getState_Mirror()),
  manufacturer: safe(() => c.getState_Manufacturer()),
  manufacturer_id: safe(() => c.getState_ManufacturerId()),
  supplier: safe(() => c.getState_Supplier()),
  supplier_id: safe(() => c.getState_SupplierId()),
  name: safe(() => c.getState_Name()),
} : null;
const results = [];
const preflight = [];
for (const act of (A.actions || [])) {
  if (act.action === 'create_part') {
    try {
      const devices = await eda.lib_Device.search(act.part, undefined, undefined, undefined, 10, 1);
      const device = (devices || []).find(d => d.name === act.part && (!act.supplier_id || d.supplierId === act.supplier_id));
      if (!device) {
        preflight.push({
          key: act.key, error: 'part_not_found',
          expected: { part: act.part, supplier_id: act.supplier_id || null },
          candidates: (devices || []).map(d => ({ name: d.name, supplier_id: d.supplierId, footprint: d.footprintName })),
        });
      } else {
        act._device = device;
      }
    } catch (e) {
      preflight.push({ key: act.key, error: 'library_search_failed', message: String(e && e.message || e) });
    }
  }
}
if (preflight.length) return { ok: false, status: 'preflight_failed', preflight, results: [] };

// Capture the pre-write page state once. It is used to refuse a create that
// would duplicate a designator and to adopt a leftover auto-numbered orphan.
const existing = await eda.sch_PrimitiveComponent.getAll();
const partsBefore = existing.filter(c => {
  try { return c.getState_ComponentType() === 'part'; } catch (e) { return false; }
});
const designatorsBefore = new Set(partsBefore.map(c => safe(() => c.getState_Designator())).filter(Boolean));

let wireSettled = false;
for (const act of (A.actions || [])) {
  try {
    // Wires drawn into freshly created parts/flags fail silently on 4.1.78
    // until the canvas has committed those primitives. Settle once, visibly.
    if (act.action === 'create_wire' && !wireSettled) {
      await sleep2(2500);
      wireSettled = true;
    }
    if (act.action === 'create_part') {
      if (act.designator && designatorsBefore.has(act.designator)) {
        results.push({
          key: act.key, ok: false, action: act.action, error: 'designator_already_exists',
          designator: act.designator,
          note: 'another part on this page already uses the planned designator; no write was sent for this action',
        });
        await sleep2(120);
        continue;
      }
      const orphan = partsBefore.find(c => {
        const component = safe(() => c.getState_Component());
        const samePart = component && component.name === act.part;
        const x = Number(safe(() => c.getState_X()));
        const y = Number(safe(() => c.getState_Y()));
        const samePosition = Math.abs(x - act.x) <= 0.01 && Math.abs(y - act.y) <= 0.01;
        const designator = safe(() => c.getState_Designator());
        const autoNumbered = !designator || /^[A-Za-z]+\?$/.test(designator);
        return samePart && samePosition && autoNumbered;
      });
      if (orphan && act.designator) {
        const orphanId = orphan.getState_PrimitiveId();
        const changes = Object.assign({}, act.post_modify || {}, { designator: act.designator });
        await eda.sch_PrimitiveComponent.modify(orphanId, changes);
        await sleep2(500);
        const adopted = await eda.sch_PrimitiveComponent.get(orphanId);
        designatorsBefore.add(act.designator);
        results.push({
          key: act.key, ok: true, action: act.action, adopted: true, primitive_id: orphanId,
          expected: { designator: act.designator }, observed: stateOf(adopted),
        });
        await sleep2(120);
        continue;
      }
      const comp = await eda.sch_PrimitiveComponent.create(
        act._device, act.x, act.y, undefined, act.rotation || 0, !!act.mirror,
        act.add_into_bom !== false, act.add_into_pcb !== false
      );
      const id = comp.getState_PrimitiveId();
      // The renderer commits a new primitive asynchronously; modifying it in
      // the same tick is silently dropped on 4.1.78.
      await sleep2(800);
      let changes = act.post_modify || null;
      if (act.designator) changes = { ...(changes || {}), designator: act.designator };
      if (changes && Object.keys(changes).length) {
        await eda.sch_PrimitiveComponent.modify(id, changes);
        await sleep2(350);
      }
      // The editor may assign an automatic number and ignore the requested
      // designator. Poll before declaring the create successful.
      let after = null;
      let designator = null;
      for (let i = 0; i < 12; i++) {
        after = await eda.sch_PrimitiveComponent.get(id);
        designator = after ? safe(() => after.getState_Designator()) : null;
        if (!act.designator || designator === act.designator) break;
        await sleep2(250);
      }
      if (act.designator && designator !== act.designator) {
        results.push({
          key: act.key, ok: false, action: act.action, primitive_id: id,
          error: 'designator_not_applied', expected: { designator: act.designator },
          observed: stateOf(after),
        });
        await sleep2(120);
        continue;
      }
      designatorsBefore.add(act.designator || designator || '');
      results.push({
        key: act.key, ok: true, action: act.action, primitive_id: id,
        expected: { designator: act.designator }, observed: stateOf(after),
      });
    } else if (act.action === 'modify_part') {
      const before = await eda.sch_PrimitiveComponent.get(act.primitive_id);
      if (!before) {
        results.push({ key: act.key, ok: false, action: act.action, error: 'target_not_found',
                       primitive_id: act.primitive_id });
        await sleep2(120);
        continue;
      }
      const actual = stateOf(before);
      if (act.expected) {
        const drift = [];
        for (const field of ['designator', 'unique_id', 'rotation', 'mirror']) {
          if (field in act.expected && actual[field] !== act.expected[field]) drift.push(field);
        }
        for (const field of ['x', 'y']) {
          if (field in act.expected && Math.abs(Number(actual[field]) - Number(act.expected[field])) > 0.01) drift.push(field);
        }
        if (drift.length) {
          results.push({ key: act.key, ok: false, action: act.action, error: 'stale_target',
                         drift, expected: act.expected, observed: actual });
          await sleep2(120);
          continue;
        }
      }
      await eda.sch_PrimitiveComponent.modify(act.primitive_id, act.changes);
      await sleep2(350);
      const after = await eda.sch_PrimitiveComponent.get(act.primitive_id);
      const nextDesignator = after ? safe(() => after.getState_Designator()) : null;
      if (nextDesignator) designatorsBefore.add(nextDesignator);
      results.push({
        key: act.key, ok: true, action: act.action, primitive_id: act.primitive_id,
        expected: act.expected || null, observed: stateOf(after),
      });
    } else if (act.action === 'create_net_flag') {
      const flag = await eda.sch_PrimitiveComponent.createNetFlag(
        act.type, act.net, act.x, act.y, act.rotation || 0, !!act.mirror
      );
      await sleep2(500);
      results.push({ key: act.key, ok: true, action: act.action, primitive_id: flag.getState_PrimitiveId(),
                     expected: { type: act.type, net: act.net }, observed: stateOf(flag) });
    } else if (act.action === 'create_net_port') {
      const port = await eda.sch_PrimitiveComponent.createNetPort(
        act.direction, act.net, act.x, act.y, act.rotation || 0, !!act.mirror
      );
      await sleep2(500);
      results.push({ key: act.key, ok: true, action: act.action, primitive_id: port.getState_PrimitiveId(),
                     expected: { direction: act.direction, net: act.net }, observed: stateOf(port) });
    } else if (act.action === 'create_wire') {
      const wire = await eda.sch_PrimitiveWire.create(act.segments || act.points, act.net);
      await sleep2(300);
      results.push({
        key: act.key, ok: true, action: act.action, primitive_id: wire.getState_PrimitiveId(),
        net: wire.getState_Net(), line: wire.getState_Line(),
      });
    } else if (act.action === 'delete_primitive') {
      const collection = act.kind === 'wire' ? eda.sch_PrimitiveWire : eda.sch_PrimitiveComponent;
      const target = await safeAsync(() => collection.get(act.primitive_id), null);
      if (!target) {
        results.push({ key: act.key, ok: false, action: act.action,
                       error: 'target_not_found', primitive_id: act.primitive_id });
        await sleep2(120);
        continue;
      }
      const checks = act.expected || {};
      if (!Object.keys(checks).length) {
        results.push({ key: act.key, ok: false, action: act.action,
                       error: 'missing_expected',
                       note: 'delete requires identity/state checks; primitive_id alone is not enough' });
        await sleep2(120);
        continue;
      }
      const component = safe(() => target.getState_Component());
      const actual = {
        designator: safe(() => target.getState_Designator()),
        name: safe(() => target.getState_Name()),
        net: safe(() => target.getState_Net()),
        x: safe(() => target.getState_X()),
        y: safe(() => target.getState_Y()),
        component: component && component.name ? component.name : null,
        direction: portDirectionOf(symbolNameOf(target) || (component && component.name)),
        flag_type: flagTypeOf(symbolNameOf(target) || (component && component.name)),
      };
      const drift = [];
      for (const field of Object.keys(checks)) {
        if (field === 'x' || field === 'y') {
          if (Math.abs(Number(actual[field]) - Number(checks[field])) > 0.01) drift.push(field);
        } else if (actual[field] !== checks[field]) {
          drift.push(field);
        }
      }
      if (drift.length) {
        results.push({ key: act.key, ok: false, action: act.action, error: 'stale_target',
                       drift, expected: checks, observed: actual });
        await sleep2(120);
        continue;
      }
      const returned = await collection.delete(act.primitive_id);
      await sleep2(400);
      const still = await safeAsync(() => collection.get(act.primitive_id), null);
      results.push({
        key: act.key, ok: !still, action: act.action, primitive_id: act.primitive_id,
        deleted: !still, still_present: !!still, returned,
      });
    } else {
      throw new Error('unsupported action: ' + act.action);
    }
  } catch (e) {
    results.push({ key: act.key, ok: false, action: act.action, error: String(e && e.message || e) });
  }
  await sleep2(120);
}
await sleep2(800);
return {
  ok: true,
  results,
  env,
  project: project ? { uuid: project.uuid, friendly_name: project.friendlyName, name: project.name, path: project.path } : null,
  selection: { schematic_uuid: selected.s.uuid, schematic_name: selected.s.name,
               page_uuid: selected.p.uuid, page_name: selected.p.name },
};
'''

SAVE_JS = r'''
const A = __ARGS__;
''' + PAGE_SELECT_JS + r'''
const saved = await eda.sch_Document.save();
const comps = await eda.sch_PrimitiveComponent.getAll();
const wires = await eda.sch_PrimitiveWire.getAll();
return { ok: true, saved: !!saved, counts: { components: comps.length, wires: wires.length }, page: { uuid: selected.p.uuid, name: selected.p.name } };
'''

DRC_JS = r'''
const A = __ARGS__;
''' + PAGE_SELECT_JS + r'''
const checked = await eda.sch_Drc.check(A.strict !== false, false, true);
return {
  ok: true,
  strict: A.strict !== false,
  result: checked,
  page: { uuid: selected.p.uuid, name: selected.p.name,
          schematic_uuid: selected.s.uuid, schematic_name: selected.s.name },
};
'''

EXPORT_JS = r'''
const A = __ARGS__;
''' + PAGE_SELECT_JS + r'''
let file = null;
if (A.kind === 'png') {
  file = await eda.sch_ManufactureData.getPngFile(A.name || 'export', A.resolution || { width: 1600 });
} else if (A.kind === 'netlist') {
  file = await eda.sch_ManufactureData.getNetlistFile(A.name || 'export', A.netlist_type || 'Protel2');
} else if (A.kind === 'svg') {
  file = await eda.sch_ManufactureData.getSvgFile(A.name || 'export');
} else {
  return { ok: false, error: 'unsupported export kind: ' + A.kind };
}
if (!file) return { ok: false, error: 'export returned undefined' };
const buf = await file.arrayBuffer();
const bytes = new Uint8Array(buf);
let binary = '';
const chunk = 0x8000;
for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
return { ok: true, name: file.name, size: file.size, base64: btoa(binary) };
'''


# ---------------------------------------------------------------------------
# Plan validation and deterministic reconciliation
# ---------------------------------------------------------------------------

def validate_plan(plan):
    if not isinstance(plan, dict):
        raise EdaInputError('plan: JSON object required')
    unknown = set(plan) - {'version', 'page', 'operations', 'note'}
    if unknown:
        raise EdaInputError(f'plan: unknown fields {sorted(unknown)}')
    if plan.get('version') != 1:
        raise EdaInputError('plan.version: must be 1')
    page = plan.get('page')
    if not isinstance(page, dict):
        raise EdaInputError('plan.page: object required')
    unknown = set(page) - {'page_uuid', 'schematic_name', 'page_name', 'current', 'settle_ms'}
    if unknown:
        raise EdaInputError(f'plan.page: unknown fields {sorted(unknown)}')
    if not any(page.get(k) for k in ('page_uuid', 'schematic_name', 'current')):
        raise EdaInputError('plan.page: one of page_uuid, schematic_name, current is required')
    if 'current' in page and (type(page['current']) is not bool or page['current'] is not True):
        raise EdaInputError('plan.page.current: when present it must be true')
    if page.get('page_uuid') is not None:
        _text(page['page_uuid'], 'plan.page.page_uuid')
    if page.get('schematic_name') is not None:
        _text(page['schematic_name'], 'plan.page.schematic_name')
    if page.get('page_name') is not None:
        _text(page['page_name'], 'plan.page.page_name')
    if page.get('settle_ms') is not None:
        value = _finite(page['settle_ms'], 'plan.page.settle_ms')
        if value < 0 or value > 30000:
            raise EdaInputError('plan.page.settle_ms: 0..30000 required')
    operations = plan.get('operations')
    if not isinstance(operations, list) or not 1 <= len(operations) <= 200:
        raise EdaInputError('plan.operations: list of 1..200 operations required')
    keys = set()
    final_designators = {}
    normalized = []
    for index, op in enumerate(operations):
        where = f'plan.operations[{index}]'
        if not isinstance(op, dict):
            raise EdaInputError(f'{where}: object required')
        kind = op.get('op')
        if kind not in OP_KEYS:
            raise EdaInputError(f'{where}.op: one of {sorted(OP_KEYS)} required')
        unknown = set(op) - OP_KEYS[kind]
        if unknown:
            raise EdaInputError(f'{where}: unknown fields {sorted(unknown)}')
        key = _text(op.get('key'), f'{where}.key')
        if key in keys:
            raise EdaInputError(f'{where}.key: duplicate key {key!r}')
        keys.add(key)
        if kind == 'part':
            match = op.get('match')
            if not isinstance(match, dict):
                raise EdaInputError(f'{where}.match: object required')
            unknown = set(match) - MATCH_KEYS
            if unknown:
                raise EdaInputError(f'{where}.match: unknown fields {sorted(unknown)}')
            if not any(match.get(k) for k in ('designator', 'unique_id', 'part', 'position')):
                raise EdaInputError(f'{where}.match: designator, unique_id, part or position required')
            if not (match.get('designator') or match.get('unique_id')):
                raise EdaInputError(f'{where}.match: designator or unique_id required for stable identity')
            if match.get('designator') is not None:
                _text(match['designator'], f'{where}.match.designator')
            if match.get('unique_id') is not None:
                _text(match['unique_id'], f'{where}.match.unique_id')
            if match.get('part') is not None:
                _text(match['part'], f'{where}.match.part')
            if match.get('supplier_id') is not None:
                supplier = _text(match['supplier_id'], f'{where}.match.supplier_id')
                if not re.fullmatch(r'C\d+', supplier):
                    raise EdaInputError(f'{where}.match.supplier_id: LCSC C-number required')
            if match.get('position') is not None:
                pos = match['position']
                if not isinstance(pos, list) or len(pos) != 2:
                    raise EdaInputError(f'{where}.match.position: [x,y] required')
                _coord(pos[0], f'{where}.match.position[0]')
                _coord(pos[1], f'{where}.match.position[1]')
            place = op.get('place')
            if place is not None:
                if not isinstance(place, dict):
                    raise EdaInputError(f'{where}.place: object required')
                unknown = set(place) - {'x', 'y', 'rotation', 'mirror'}
                if unknown:
                    raise EdaInputError(f'{where}.place: unknown fields {sorted(unknown)}')
                _coord(place.get('x'), f'{where}.place.x')
                _coord(place.get('y'), f'{where}.place.y')
                _rotation(place.get('rotation', 0), f'{where}.place.rotation')
                if 'mirror' in place:
                    _bool(place['mirror'], f'{where}.place.mirror')
            props = op.get('properties')
            if props is not None:
                if not isinstance(props, dict):
                    raise EdaInputError(f'{where}.properties: object required')
                unknown = set(props) - PART_KEYS
                if unknown:
                    raise EdaInputError(f'{where}.properties: unknown fields {sorted(unknown)}')
                if 'designator' in props:
                    _text(props['designator'], f'{where}.properties.designator')
                for name in ('name', 'manufacturer', 'manufacturer_id', 'supplier', 'supplier_id'):
                    if name in props:
                        _text(props[name], f'{where}.properties.{name}')
                if 'supplier_id' in props and not re.fullmatch(r'C\d+', props['supplier_id']):
                    raise EdaInputError(f'{where}.properties.supplier_id: LCSC C-number required')
                if 'other_property' in props and not isinstance(props['other_property'], dict):
                    raise EdaInputError(f'{where}.properties.other_property: object required')
            for name in ('add_into_bom', 'add_into_pcb'):
                if name in op:
                    _bool(op[name], f'{where}.{name}')
            if op.get('place') is None and not (match.get('designator') or match.get('unique_id')):
                raise EdaInputError(f'{where}: creating a part needs place; modifying needs designator/unique_id')
            planned_designator = (op.get('properties') or {}).get('designator') or match.get('designator')
            if planned_designator:
                if planned_designator in final_designators:
                    raise EdaInputError(
                        f'{where}: designator {planned_designator!r} is already used by '
                        f'operation {final_designators[planned_designator]!r}; one designator can name only one part')
                final_designators[planned_designator] = key
            normalized.append({**op, 'op': 'part'})
        elif kind == 'net_flag':
            _text(op.get('net'), f'{where}.net')
            if op.get('type') not in NET_FLAG_TYPES:
                raise EdaInputError(f'{where}.type: one of {sorted(NET_FLAG_TYPES)} required')
            _at(op.get('at'), f'{where}.at')
            _rotation(op.get('rotation', 0), f'{where}.rotation')
            if 'mirror' in op:
                _bool(op['mirror'], f'{where}.mirror')
            normalized.append(op)
        elif kind == 'net_port':
            _text(op.get('net'), f'{where}.net')
            if op.get('direction') not in NET_PORT_DIRECTIONS:
                raise EdaInputError(f'{where}.direction: one of {sorted(NET_PORT_DIRECTIONS)} required')
            _at(op.get('at'), f'{where}.at')
            _rotation(op.get('rotation', 0), f'{where}.rotation')
            if 'mirror' in op:
                _bool(op['mirror'], f'{where}.mirror')
            normalized.append(op)
        elif kind == 'wire':
            _text(op.get('net'), f'{where}.net')
            _canonical_segments(op.get('points'))
            normalized.append(op)
        elif kind == 'delete':
            target = op.get('target')
            if not isinstance(target, dict):
                raise EdaInputError(f'{where}.target: object required')
            unknown = set(target) - {'kind', 'primitive_id', 'expected'}
            if unknown:
                raise EdaInputError(f'{where}.target: unknown fields {sorted(unknown)}')
            target_kind = target.get('kind')
            if target_kind not in DELETE_KINDS:
                raise EdaInputError(f'{where}.target.kind: one of {sorted(DELETE_KINDS)} required')
            _text(target.get('primitive_id'), f'{where}.target.primitive_id')
            expected = target.get('expected') or {}
            if not isinstance(expected, dict):
                raise EdaInputError(f'{where}.target.expected: object required')
            unknown = set(expected) - DELETE_EXPECTED_FIELDS[target_kind]
            if unknown:
                raise EdaInputError(
                    f'{where}.target.expected: unknown fields for {target_kind}: {sorted(unknown)}')
            required = DELETE_REQUIRED_FIELDS[target_kind]
            missing = [field for field in required if field not in expected]
            if missing:
                raise EdaInputError(
                    f'{where}.target.expected: missing required fields {missing} for '
                    f'{target_kind}; delete requires identity and state, not only primitive_id')
            for field in required:
                if field in ('x', 'y'):
                    continue
                value = expected[field]
                if not isinstance(value, str) or (field != 'net' and not value.strip()):
                    raise EdaInputError(
                        f'{where}.target.expected.{field}: non-empty string required')
            for field in ('x', 'y'):
                if field in expected:
                    _coord(expected[field], f'{where}.target.expected.{field}')
            if 'designator' in expected:
                _text(expected['designator'], f'{where}.target.expected.designator')
            if 'component' in expected:
                _text(expected['component'], f'{where}.target.expected.component')
            if 'direction' in expected and expected['direction'] not in NET_PORT_DIRECTIONS:
                raise EdaInputError(f'{where}.target.expected.direction: one of {sorted(NET_PORT_DIRECTIONS)}')
            normalized.append(op)
    return {**plan, 'operations': normalized}


def _at(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise EdaInputError(f'{label}: [x,y] required')
    _coord(value[0], f'{label}[0]')
    _coord(value[1], f'{label}[1]')
    return value


def _rotation(value, label):
    number = _finite(value, label)
    if number not in (0, 90, 180, 270):
        raise EdaInputError(f'{label}: 0/90/180/270 required')
    return number


def _part_name(part):
    component = part.get('component')
    if isinstance(component, dict):
        return component.get('name')
    return None


def _footprint_name(part):
    footprint = part.get('footprint')
    if isinstance(footprint, dict):
        return footprint.get('name')
    return None


def _wire_prop(name):
    return {
        'designator': 'designator', 'name': 'name', 'manufacturer': 'manufacturer',
        'manufacturer_id': 'manufacturerId', 'supplier': 'supplier',
        'supplier_id': 'supplierId', 'other_property': 'otherProperty',
    }[name]


def _same_position(a, b, tolerance=0.6):
    try:
        return abs(float(a[0]) - float(b[0])) <= tolerance and abs(float(a[1]) - float(b[1])) <= tolerance
    except (TypeError, ValueError):
        return False


def _part_matches(part, match):
    """Select by stable identity only; part/supplier are checked as identity."""
    if match.get('unique_id') and part.get('unique_id') != match['unique_id']:
        return False
    if match.get('designator') and part.get('designator') != match['designator']:
        return False
    if match.get('position') and not _same_position((part.get('x'), part.get('y')), match['position'], tolerance=0.01):
        return False
    return True


def _flag_type_from_names(*names):
    """Derive the power/ground flag type from the library symbol name.

    4.1.78 exposes no dedicated getState_ flag-type accessor; the symbol name
    is the only reliable readback (for example Power-5V, Ground, Netport-BI).
    """
    for name in names:
        if not isinstance(name, str):
            continue
        if re.search(r'ProtectGround', name, re.I):
            return 'ProtectGround'
        if re.search(r'AnalogGround', name, re.I):
            return 'AnalogGround'
        if re.search(r'Ground', name, re.I):
            return 'Ground'
        if re.search(r'Power', name, re.I):
            return 'Power'
    return None


def _port_direction_from_names(*names):
    for name in names:
        if not isinstance(name, str):
            continue
        match = re.search(r'Netport-(IN|OUT|BI)', name, re.I)
        if match:
            return match.group(1).upper()
    return None


def _part_expected_state(part):
    return {
        'designator': part.get('designator'),
        'unique_id': part.get('unique_id'),
        'x': part.get('x'),
        'y': part.get('y'),
        'rotation': part.get('rotation'),
        'mirror': part.get('mirror'),
    }


def snapshot_integrity(snapshot):
    """Classify a snapshot as usable for write verification or not.

    A read error or a truncated part/pin/attribute list must never be treated
    as "the object is absent" or as "the readback passed".
    """
    integrity = snapshot.get('integrity')
    if not isinstance(integrity, dict):
        return {
            'status': 'incomplete',
            'reason': 'integrity_block_missing',
            'read_errors': [{'scope': 'snapshot', 'field': 'integrity', 'error': 'missing integrity block'}],
        }
    errors = list(integrity.get('read_errors') or [])
    pins_complete = integrity.get('pins_complete') is not False
    attributes_complete = integrity.get('attributes_complete')
    components_consistent = integrity.get('components_consistent') is not False
    complete = (
        integrity.get('status') == 'complete'
        and not errors
        and pins_complete
        and attributes_complete is not False
        and components_consistent
    )
    return {
        'status': 'complete' if complete else 'incomplete',
        'reason': None if complete else 'integrity_not_complete',
        'read_errors': errors,
        'pins_complete': pins_complete,
        'attributes_complete': attributes_complete,
        'components_consistent': components_consistent,
    }


def client_version_verified(env):
    version = (env or {}).get('version')
    if not isinstance(version, str):
        return False
    return any(version.startswith(prefix) for prefix in VERIFIED_CLIENT_PREFIXES)


def reconcile(snapshot, plan, project_designators=None):
    """Compare the plan with a live snapshot; never guess on ambiguity."""
    parts = snapshot.get('parts') or []
    netflags = snapshot.get('netflags') or []
    netports = snapshot.get('netports') or []
    wires = snapshot.get('wires') or []
    items, actions, conflicts = [], [], []
    designator_scope = 'page' if project_designators is None else 'project'

    designator_index = {}
    null_designator_parts = []
    for part in parts:
        designator = part.get('designator')
        if designator is None:
            null_designator_parts.append(part)
        else:
            designator_index.setdefault(designator, []).append(part)

    project_index = {}
    for row in (project_designators or []):
        if isinstance(row, dict) and row.get('designator'):
            project_index.setdefault(row['designator'], []).append(row)

    def conflict(item, reason, detail=None):
        item['status'] = 'conflict'
        item['reason'] = reason
        if detail is not None:
            item['detail'] = detail
        conflicts.append(item)

    def owners_of(designator, exclude_primitive=None):
        return [p for p in designator_index.get(designator, [])
                if p.get('primitive_id') != exclude_primitive]

    for op in plan['operations']:
        key = op['key']
        item = {'key': key, 'op': op['op'], 'status': 'skip'}
        if op['op'] == 'part':
            match = op['match']
            props = op.get('properties') or {}
            place = op.get('place') or {}
            candidates = [p for p in parts if _part_matches(p, match)]
            # A position-only match is intentionally not used when a stable key exists.
            if len(candidates) > 1:
                conflict(item, 'ambiguous_match', {'count': len(candidates), 'designators': [p.get('designator') for p in candidates]})
            elif len(candidates) == 1:
                existing = candidates[0]
                if match.get('part') and _part_name(existing) != match['part']:
                    conflict(item, 'part_identity_changed', {'existing': _part_name(existing), 'planned': match['part']})
                elif match.get('supplier_id') and existing.get('supplier_id') != match['supplier_id']:
                    conflict(item, 'supplier_identity_changed', {'existing': existing.get('supplier_id'), 'planned': match['supplier_id']})
                else:
                    changes = {}
                    for field, attr in (('x', 'x'), ('y', 'y'), ('rotation', 'rotation'), ('mirror', 'mirror')):
                        if field in place:
                            current = existing.get(attr)
                            planned = place[field]
                            if field in ('x', 'y'):
                                if not _same_position((current, 0), (planned, 0), tolerance=0.01):
                                    changes[field] = planned
                            elif current != planned:
                                changes[field] = planned
                    for field, value in props.items():
                        if field == 'other_property':
                            current = existing.get('other_property') or {}
                            if current != value:
                                changes[_wire_prop(field)] = value
                        elif field in PART_KEYS:
                            current = existing.get(field)
                            if current != value:
                                changes[_wire_prop(field)] = value
                    # Membership flags cannot be modified through the typed
                    # action set; report that instead of silently skipping.
                    unsupported = [
                        name for name in ('add_into_bom', 'add_into_pcb')
                        if name in op and existing.get(name) is not None
                        and bool(existing.get(name)) != bool(op[name])
                    ]
                    if unsupported:
                        conflict(item, 'unsupported_property_change', {
                            'fields': unsupported,
                            'note': 'existing-part BOM/PCB membership changes are not supported by this adapter',
                        })
                    elif changes:
                        prim = existing.get('primitive_id')
                        collision = None
                        project_collision = []
                        if 'designator' in changes:
                            collision = owners_of(changes['designator'], exclude_primitive=prim)
                            project_collision = [
                                row for row in project_index.get(changes['designator'], [])
                                if row.get('unique_id') != existing.get('unique_id')
                            ]
                        if not prim:
                            conflict(item, 'missing_primitive_id')
                        elif collision:
                            conflict(item, 'designator_already_exists', {
                                'designator': changes['designator'],
                                'owners': [{'primitive_id': p.get('primitive_id'),
                                            'unique_id': p.get('unique_id')} for p in collision[:10]],
                            })
                        elif project_collision:
                            item['designator_scope'] = designator_scope
                            conflict(item, 'designator_already_exists_project', {
                                'designator': changes['designator'],
                                'owners': [{'page_uuid': row.get('page_uuid'),
                                            'page_name': row.get('page_name'),
                                            'unique_id': row.get('unique_id')}
                                           for row in project_collision[:10]],
                            })
                        else:
                            item.update({'status': 'modify', 'changes': changes, 'primitive_id': prim,
                                         'designator': changes.get('designator', existing.get('designator')),
                                         'designator_scope': designator_scope})
                            actions.append({
                                'action': 'modify_part', 'key': key, 'primitive_id': prim,
                                'changes': changes, 'expected': _part_expected_state(existing),
                            })
                    else:
                        item['status'] = 'skip'
                        item['reason'] = 'already_matches'
            else:
                if not place or not match.get('part'):
                    conflict(item, 'create_needs_part_and_place')
                elif not (match.get('designator') or props.get('designator')):
                    conflict(item, 'create_needs_stable_designator')
                else:
                    designator = props.get('designator') or match.get('designator')
                    if null_designator_parts:
                        conflict(item, 'snapshot_incomplete', {
                            'reason': 'a part on this page has an unreadable designator; absence of the planned designator cannot be proven',
                            'primitive_ids': [p.get('primitive_id') for p in null_designator_parts[:10]],
                        })
                    else:
                        occupants = owners_of(designator)
                        project_occupants = project_index.get(designator, [])
                        if occupants:
                            reason = 'identity_mismatch' if match.get('unique_id') else 'designator_already_exists'
                            conflict(item, reason, {
                                'designator': designator,
                                'owners': [{'primitive_id': p.get('primitive_id'),
                                            'unique_id': p.get('unique_id')} for p in occupants[:10]],
                            })
                        elif project_occupants:
                            item['designator_scope'] = designator_scope
                            conflict(item, 'designator_already_exists_project', {
                                'designator': designator,
                                'owners': [{'page_uuid': row.get('page_uuid'),
                                            'page_name': row.get('page_name'),
                                            'unique_id': row.get('unique_id')}
                                           for row in project_occupants[:10]],
                            })
                        else:
                            post = {
                                _wire_prop(k): v
                                for k, v in props.items()
                                if k != 'designator'
                            }
                            action = {
                                'action': 'create_part', 'key': key, 'part': match['part'],
                                'supplier_id': match.get('supplier_id'),
                                'x': place['x'], 'y': place['y'],
                                'rotation': place.get('rotation', 0), 'mirror': place.get('mirror', False),
                                'designator': designator,
                                'add_into_bom': op.get('add_into_bom', True),
                                'add_into_pcb': op.get('add_into_pcb', True),
                                'post_modify': post or None,
                            }
                            item.update({'status': 'create', 'designator': designator,
                                         'part': match['part'], 'designator_scope': designator_scope})
                            actions.append(action)
            # Identity is only as strong as the supplied match.
            if match.get('designator') or match.get('unique_id'):
                item['stable_identity'] = True
            else:
                item['warning'] = 'identity_not_stable_without_designator_or_unique_id'
            items.append(item)
        elif op['op'] == 'net_flag':
            # Power/ground symbols are normally repeated at several pins.
            # Idempotency is per net+position, and the type must match too.
            same_position = [f for f in netflags if f.get('name') == op['net']
                             and _same_position((f.get('x'), f.get('y')), op['at'], tolerance=0.01)]
            if len(same_position) > 1:
                conflict(item, 'duplicate_net_flag_at_position', {'count': len(same_position)})
            elif same_position:
                found = same_position[0]
                flag_type = found.get('flag_type') or _flag_type_from_names(
                    found.get('symbol_name'), found.get('component_name'))
                if flag_type is None:
                    conflict(item, 'net_flag_type_unverified', {'primitive_id': found.get('primitive_id'),
                                                              'symbol_name': found.get('symbol_name')})
                elif flag_type != op['type']:
                    conflict(item, 'net_flag_type_mismatch', {'existing': flag_type, 'planned': op['type'],
                                                             'primitive_id': found.get('primitive_id')})
                elif found.get('rotation') != op.get('rotation', 0) or bool(found.get('mirror')) != bool(op.get('mirror', False)):
                    conflict(item, 'net_flag_geometry_mismatch', {
                        'rotation': [found.get('rotation'), op.get('rotation', 0)],
                        'mirror': [bool(found.get('mirror')), bool(op.get('mirror', False))],
                    })
                else:
                    item['status'] = 'skip'
                    item['reason'] = 'already_matches'
            else:
                action = {'action': 'create_net_flag', 'key': key, 'type': op['type'], 'net': op['net'],
                          'x': op['at'][0], 'y': op['at'][1], 'rotation': op.get('rotation', 0),
                          'mirror': op.get('mirror', False)}
                item.update({'status': 'create', 'net': op['net']})
                actions.append(action)
            items.append(item)
        elif op['op'] == 'net_port':
            same_position = [p for p in netports if p.get('net') == op['net']
                             and _same_position((p.get('x'), p.get('y')), op['at'], tolerance=0.01)]
            if len(same_position) > 1:
                conflict(item, 'duplicate_net_port_at_position', {'count': len(same_position)})
            elif same_position:
                found = same_position[0]
                direction = found.get('direction') or _port_direction_from_names(
                    found.get('symbol_name'), found.get('component_name'))
                if direction is None:
                    conflict(item, 'net_port_direction_unverified', {'primitive_id': found.get('primitive_id'),
                                                                    'symbol_name': found.get('symbol_name')})
                elif direction != op['direction']:
                    conflict(item, 'net_port_direction_mismatch', {'existing': direction,
                                                                  'planned': op['direction'],
                                                                  'primitive_id': found.get('primitive_id')})
                elif found.get('rotation') != op.get('rotation', 0) or bool(found.get('mirror')) != bool(op.get('mirror', False)):
                    conflict(item, 'net_port_geometry_mismatch', {
                        'rotation': [found.get('rotation'), op.get('rotation', 0)],
                        'mirror': [bool(found.get('mirror')), bool(op.get('mirror', False))],
                    })
                else:
                    item['status'] = 'skip'
                    item['reason'] = 'already_matches'
            else:
                action = {'action': 'create_net_port', 'key': key, 'direction': op['direction'], 'net': op['net'],
                          'x': op['at'][0], 'y': op['at'][1], 'rotation': op.get('rotation', 0),
                          'mirror': op.get('mirror', False)}
                item.update({'status': 'create', 'net': op['net']})
                actions.append(action)
            items.append(item)
        elif op['op'] == 'wire':
            target_segments, _ = _canonical_segments(op['points'])
            existing_by_net = {}
            unparsed_same_net = []
            for wire in wires:
                segments, parsed = _segments_from_line(wire.get('line') or [])
                if not parsed:
                    if (wire.get('net') or '') == op['net']:
                        unparsed_same_net.append({
                            'primitive_id': wire.get('primitive_id'), 'net': wire.get('net'),
                            'line': wire.get('line'),
                        })
                    continue
                existing_by_net.setdefault(wire.get('net') or '', []).extend(segments)
            if unparsed_same_net:
                conflict(item, 'unparsed_wire_on_net', {'wires': unparsed_same_net[:10]})
            else:
                conflicting = []
                for segment in target_segments:
                    for net, segments in existing_by_net.items():
                        if net == op['net']:
                            continue
                        for other in segments:
                            if _segments_overlap(segment, other):
                                conflicting.append({'segment': segment, 'owner': net})
                                break
                if conflicting:
                    conflict(item, 'wire_segment_net_conflict', {'segments': conflicting[:10]})
                else:
                    same_net = existing_by_net.get(op['net'], [])
                    missing = [segment for segment in target_segments
                               if not _segment_covered(segment, same_net)]
                    if not missing:
                        item['status'] = 'skip'
                        item['reason'] = 'already_matches'
                    else:
                        for index, (a, b) in enumerate(missing):
                            action = {
                                'action': 'create_wire', 'key': f'{key}#{index}', 'net': op['net'],
                                'points': [a[0], a[1], b[0], b[1]],
                                'segments': [[a[0], a[1], b[0], b[1]]],
                            }
                            actions.append(action)
                        item.update({'status': 'create', 'net': op['net'],
                                     'segments': len(missing), 'existing_segments': len(target_segments) - len(missing)})
            items.append(item)
        elif op['op'] == 'delete':
            target = op['target']
            target_kind = target['kind']
            primitive_id = target['primitive_id']
            expected = target.get('expected') or {}
            if not expected:
                conflict(item, 'missing_expected', {
                    'kind': target_kind,
                    'required': list(DELETE_REQUIRED_FIELDS[target_kind]),
                    'note': 'delete requires identity/state checks; primitive_id alone is not enough',
                })
                items.append(item)
                continue
            collections = {
                'part': parts, 'net_flag': netflags,
                'net_port': netports, 'wire': wires,
            }
            found = next((row for row in collections[target_kind]
                          if row.get('primitive_id') == primitive_id), None)
            if found is None:
                conflict(item, 'target_not_found', {
                    'kind': target_kind, 'primitive_id': primitive_id,
                })
            else:
                mismatches = []
                observed = {}
                for field, value in expected.items():
                    if field == 'component' and target_kind == 'part':
                        actual = _part_name(found)
                    else:
                        actual = found.get(field)
                    observed[field] = actual
                    if field in ('x', 'y'):
                        if not _same_position((actual, 0), (value, 0), tolerance=0.01):
                            mismatches.append(field)
                    elif actual != value:
                        mismatches.append(field)
                if mismatches:
                    conflict(item, 'target_identity_mismatch', {
                        'kind': target_kind, 'primitive_id': primitive_id,
                        'mismatched_fields': mismatches, 'observed': observed,
                    })
                else:
                    item.update({
                        'status': 'delete', 'kind': target_kind,
                        'primitive_id': primitive_id, 'expected': expected,
                    })
                    actions.append({
                        'action': 'delete_primitive', 'key': key,
                        'kind': target_kind, 'primitive_id': primitive_id,
                        'expected': expected,
                    })
            items.append(item)
    return {
        'items': items,
        'actions': actions,
        'conflicts': conflicts,
        'status': 'blocked' if conflicts else ('changes' if actions else 'no_changes'),
    }


def _execution_by_key(execution):
    mapping = {}
    if isinstance(execution, dict):
        for row in execution.get('results') or []:
            if isinstance(row, dict) and row.get('key'):
                mapping[row['key']] = row
    return mapping


def verify_against_snapshot(snapshot, plan, items, execution=None):
    """Read-back verification. It never treats a write response as proof.

    Every attribute that was actually requested is compared against the
    readback; the execution response is used only to resolve the object id,
    never as evidence that a property was applied.
    """
    parts = snapshot.get('parts') or []
    netflags = snapshot.get('netflags') or []
    netports = snapshot.get('netports') or []
    wires = snapshot.get('wires') or []
    executed = _execution_by_key(execution)
    results = []
    for item in items:
        key = item['key']
        if item['status'] == 'conflict':
            results.append({**item, 'verification': 'conflict'})
            continue
        op = next(x for x in plan['operations'] if x['key'] == key)
        passed, detail = False, {}
        if op['op'] == 'part':
            match = op['match']
            props = op.get('properties') or {}
            place = op.get('place') or {}
            expected_designator = props.get('designator') or item.get('designator') or match.get('designator')
            exec_row = executed.get(key) or {}
            candidate = None
            for primitive_id in (exec_row.get('primitive_id'), item.get('primitive_id')):
                if primitive_id:
                    candidate = next((p for p in parts if p.get('primitive_id') == primitive_id), None)
                    if candidate is not None:
                        break
            if candidate is None and match.get('unique_id'):
                candidate = next((p for p in parts if p.get('unique_id') == match['unique_id']), None)
            if candidate is None and expected_designator:
                candidate = next((p for p in parts if p.get('designator') == expected_designator), None)
            if candidate is None and match.get('position'):
                candidate = next((p for p in parts if _same_position((p.get('x'), p.get('y')), match['position'], tolerance=0.01)), None)
            if candidate is None:
                near_orphan = None
                if 'x' in place and 'y' in place:
                    near_orphan = next((
                        p for p in parts
                        if _same_position((p.get('x'), p.get('y')), (place['x'], place['y']), tolerance=0.01)
                        and re.fullmatch(r'[A-Za-z]+\?', str(p.get('designator') or ''))
                    ), None)
                if near_orphan is not None:
                    detail = {'reason': 'designator_not_applied',
                              'observed': _part_expected_state(near_orphan),
                              'candidate_primitive_id': near_orphan.get('primitive_id')}
                else:
                    detail = {'reason': 'part_not_found_after_apply',
                              'execution': exec_row}
            else:
                expected, observed, failures = {}, {}, []

                def check(field, expected_value, observed_value):
                    expected[field] = expected_value
                    observed[field] = observed_value
                    if expected_value is not None and observed_value != expected_value:
                        failures.append(field)

                check('designator', expected_designator, candidate.get('designator'))
                if match.get('unique_id'):
                    check('unique_id', match['unique_id'], candidate.get('unique_id'))
                check('component', match.get('part'), _part_name(candidate))
                check('supplier_id', props.get('supplier_id', match.get('supplier_id')),
                      candidate.get('supplier_id'))
                for name in ('name', 'manufacturer', 'manufacturer_id', 'supplier'):
                    if name in props:
                        check(name, props[name], candidate.get(name))
                if 'other_property' in props:
                    wanted = props['other_property']
                    actual = candidate.get('other_property') or {}
                    expected['other_property'] = wanted
                    observed['other_property'] = actual
                    if not isinstance(actual, dict) or any(actual.get(k) != v for k, v in wanted.items()):
                        failures.append('other_property')
                for field in ('x', 'y'):
                    if field in place:
                        expected[field] = place[field]
                        observed[field] = candidate.get(field)
                        if not _same_position((candidate.get(field), 0), (place[field], 0), tolerance=0.01):
                            failures.append(field)
                if 'rotation' in place:
                    check('rotation', place['rotation'], candidate.get('rotation'))
                if 'mirror' in place:
                    check('mirror', bool(place['mirror']), bool(candidate.get('mirror')))
                for name in ('add_into_bom', 'add_into_pcb'):
                    if name in op:
                        check(name, op[name], candidate.get(name))
                passed = not failures
                detail = {'expected': expected, 'observed': observed}
                if failures:
                    detail['reason'] = 'field_mismatch'
                    detail['mismatched_fields'] = failures
                    if 'designator' in failures and re.fullmatch(
                            r'[A-Za-z]+\?', str(candidate.get('designator') or '')):
                        detail['reason'] = 'designator_not_applied'
        elif op['op'] == 'net_flag':
            exec_row = executed.get(key) or {}
            candidate = None
            if exec_row.get('primitive_id'):
                candidate = next((f for f in netflags if f.get('primitive_id') == exec_row['primitive_id']), None)
            if candidate is None:
                candidate = next((f for f in netflags if f.get('name') == op['net']
                                  and _same_position((f.get('x'), f.get('y')), op['at'], tolerance=0.01)), None)
            if candidate is None:
                detail = {'reason': 'net_flag_not_found', 'net': op['net'], 'at': op['at']}
            else:
                flag_type = candidate.get('flag_type') or _flag_type_from_names(
                    candidate.get('symbol_name'), candidate.get('component_name'))
                failures = []
                if flag_type is None:
                    failures.append('flag_type_unreadable')
                elif flag_type != op['type']:
                    failures.append('flag_type')
                if candidate.get('rotation') != op.get('rotation', 0):
                    failures.append('rotation')
                if bool(candidate.get('mirror')) != bool(op.get('mirror', False)):
                    failures.append('mirror')
                passed = not failures
                detail = {'expected': {'type': op['type'], 'net': op['net'],
                                       'rotation': op.get('rotation', 0), 'mirror': bool(op.get('mirror', False))},
                          'observed': {'flag_type': flag_type, 'net': candidate.get('name') or candidate.get('net'),
                                       'rotation': candidate.get('rotation'), 'mirror': candidate.get('mirror')}}
                if failures:
                    detail['reason'] = 'field_mismatch'
                    detail['mismatched_fields'] = failures
        elif op['op'] == 'net_port':
            exec_row = executed.get(key) or {}
            candidate = None
            if exec_row.get('primitive_id'):
                candidate = next((p for p in netports if p.get('primitive_id') == exec_row['primitive_id']), None)
            if candidate is None:
                candidate = next((p for p in netports if p.get('net') == op['net']
                                  and _same_position((p.get('x'), p.get('y')), op['at'], tolerance=0.01)), None)
            if candidate is None:
                detail = {'reason': 'net_port_not_found', 'net': op['net'], 'at': op['at']}
            else:
                direction = candidate.get('direction') or _port_direction_from_names(
                    candidate.get('symbol_name'), candidate.get('component_name'))
                failures = []
                if direction is None:
                    failures.append('direction_unreadable')
                elif direction != op['direction']:
                    failures.append('direction')
                if candidate.get('rotation') != op.get('rotation', 0):
                    failures.append('rotation')
                if bool(candidate.get('mirror')) != bool(op.get('mirror', False)):
                    failures.append('mirror')
                passed = not failures
                detail = {'expected': {'direction': op['direction'], 'net': op['net'],
                                       'rotation': op.get('rotation', 0), 'mirror': bool(op.get('mirror', False))},
                          'observed': {'direction': direction, 'net': candidate.get('net'),
                                       'rotation': candidate.get('rotation'), 'mirror': candidate.get('mirror')}}
                if failures:
                    detail['reason'] = 'field_mismatch'
                    detail['mismatched_fields'] = failures
        elif op['op'] == 'wire':
            target_segments, _ = _canonical_segments(op['points'])
            actual = []
            unparsed = []
            for wire in wires:
                if wire.get('net') != op['net']:
                    continue
                segments, parsed = _segments_from_line(wire.get('line') or [])
                if not parsed:
                    unparsed.append({'primitive_id': wire.get('primitive_id'),
                                     'net': wire.get('net'), 'line': wire.get('line')})
                actual.extend(segments)
            if unparsed:
                passed = False
                detail = {'reason': 'unparsed_wire_on_net', 'net': op['net'],
                          'unparsed_wires': unparsed[:10]}
            else:
                missing = [segment for segment in target_segments
                           if not _segment_covered(segment, actual)]
                passed = not missing
                detail = {'net': op['net'], 'segments': len(target_segments),
                          'missing_segments': missing[:10], 'missing_count': len(missing)}
        elif op['op'] == 'delete':
            target = op['target']
            target_kind = target['kind']
            primitive_id = target['primitive_id']
            collections = {
                'part': parts, 'net_flag': netflags,
                'net_port': netports, 'wire': wires,
            }
            found = next((row for row in collections[target_kind]
                          if row.get('primitive_id') == primitive_id), None)
            passed = found is None
            detail = {'kind': target_kind, 'primitive_id': primitive_id,
                      'still_present': found is not None}
            if found is not None:
                detail['reason'] = 'target_still_present'
                detail['observed'] = found
        results.append({**item, 'verification': 'verified' if passed else 'failed', 'observed': detail})
    statuses = {r['verification'] for r in results}
    if 'failed' in statuses or 'conflict' in statuses:
        status = 'partial' if any(r['verification'] == 'verified' for r in results) else 'failed'
    else:
        status = 'verified'
    return results, status


def compare_snapshots(before, after, tolerance=0.01):
    """Compare stable identity/connectivity, ignoring volatile primitive IDs.

    The comparison is deliberately wider than the apply verifier: a reopen
    check that cannot see a port, a mirror flip or a duplicate designator is
    not evidence of persistence.
    """
    differences = []

    def identity(snapshot):
        return {
            'project_uuid': (snapshot.get('project') or {}).get('uuid'),
            'page_uuid': (snapshot.get('selection') or {}).get('page_uuid'),
        }

    before_identity, after_identity = identity(before), identity(after)
    for field in ('project_uuid', 'page_uuid'):
        if before_identity[field] and after_identity[field] and before_identity[field] != after_identity[field]:
            differences.append({'kind': 'identity', 'field': field,
                                'before': before_identity[field], 'after': after_identity[field]})

    def designator_counts(snapshot):
        counts = {}
        for part in snapshot.get('parts') or []:
            designator = part.get('designator')
            counts[designator] = counts.get(designator, 0) + 1
        return counts

    for side, snapshot in (('before', before), ('after', after)):
        for designator, count in designator_counts(snapshot).items():
            if designator is not None and count > 1:
                differences.append({'kind': 'duplicate_designators', 'side': side,
                                    'designator': designator, 'count': count})

    def parts_by_key(snapshot):
        result = {}
        for index, part in enumerate(snapshot.get('parts') or []):
            key = part.get('unique_id') or part.get('designator') or part.get('primitive_id') or f'#{index}'
            result[key] = part
        return result

    def part_view(part):
        component = part.get('component') or {}
        symbol = part.get('symbol') or {}
        footprint = part.get('footprint') or {}
        return {
            'designator': part.get('designator'), 'part': _part_name(part),
            'name': part.get('name'),
            'supplier_id': part.get('supplier_id'), 'footprint': _footprint_name(part),
            'unique_id': part.get('unique_id'), 'rotation': part.get('rotation'),
            'mirror': bool(part.get('mirror')) if part.get('mirror') is not None else None,
            'add_into_bom': part.get('add_into_bom'), 'add_into_pcb': part.get('add_into_pcb'),
            'manufacturer': part.get('manufacturer'),
            'manufacturer_id': part.get('manufacturer_id'),
            'supplier': part.get('supplier'),
            'component_uuid': component.get('uuid'),
            'symbol_uuid': symbol.get('uuid'),
            'footprint_uuid': footprint.get('uuid'),
            'other_property': part.get('other_property'),
        }

    before_parts, after_parts = parts_by_key(before), parts_by_key(after)
    for key in sorted(set(before_parts) | set(after_parts)):
        left, right = before_parts.get(key), after_parts.get(key)
        if left is None or right is None:
            differences.append({'kind': 'part', 'key': key, 'field': 'presence',
                                'before': part_view(left) if left else None,
                                'after': part_view(right) if right else None})
            continue
        left_view, right_view = part_view(left), part_view(right)
        for field in left_view:
            if left_view[field] != right_view[field]:
                differences.append({'kind': 'part', 'key': key, 'field': field,
                                    'before': left_view[field], 'after': right_view[field]})
        left_xy = (left.get('x'), left.get('y'))
        right_xy = (right.get('x'), right.get('y'))
        if not _same_position(left_xy, right_xy, tolerance=tolerance):
            differences.append({'kind': 'part', 'key': key, 'field': 'position',
                                'before': list(left_xy), 'after': list(right_xy),
                                'dx': (right.get('x') - left.get('x')) if left.get('x') is not None and right.get('x') is not None else None,
                                'dy': (right.get('y') - left.get('y')) if left.get('y') is not None and right.get('y') is not None else None})

    def wires_set(snapshot):
        return sorted(_normalized_wire_net(snapshot), key=repr)

    def unparsed_wires(snapshot):
        rows = []
        for wire in snapshot.get('wires') or []:
            segments, parsed = _segments_from_line(wire.get('line') or [])
            if not parsed:
                rows.append({'primitive_id': wire.get('primitive_id'), 'net': wire.get('net'),
                             'line': wire.get('line')})
        return rows

    before_wires, after_wires = wires_set(before), wires_set(after)
    if before_wires != after_wires:
        differences.append({'kind': 'wires', 'before_count': len(before_wires), 'after_count': len(after_wires),
                            'missing': [x for x in before_wires if x not in after_wires][:10],
                            'added': [x for x in after_wires if x not in before_wires][:10]})
    before_unparsed, after_unparsed = unparsed_wires(before), unparsed_wires(after)
    if before_unparsed or after_unparsed:
        differences.append({'kind': 'unparsed_wires',
                            'before': before_unparsed[:10], 'after': after_unparsed[:10],
                            'note': 'geometry of these wires cannot be compared; persistence is not proven'})

    def zero_length_wires(snapshot):
        # A zero-length wire can be the actual pin-to-port/flag connection.
        # Its geometry is irrelevant, but its presence, net and position are
        # connection evidence and must not be ignored.
        rows = []
        for wire in snapshot.get('wires') or []:
            line = wire.get('line') or []
            if _zero_length_line(line) and len(line) >= 2:
                rows.append((wire.get('net') or '',
                             _round(line[0]) if line[0] is not None else None,
                             _round(line[1]) if line[1] is not None else None))
        return sorted(rows, key=repr)

    before_zero, after_zero = zero_length_wires(before), zero_length_wires(after)
    if before_zero != after_zero:
        differences.append({
            'kind': 'zero_length_wires',
            'before_count': len(before_zero), 'after_count': len(after_zero),
            'missing': [x for x in before_zero if x not in after_zero][:20],
            'added': [x for x in after_zero if x not in before_zero][:20],
            'note': ('zero-length wires can be pin-to-port connection primitives; '
                     'a change means connectivity equivalence is not proven'),
        })

    def flags_set(snapshot):
        rows = []
        for flag in snapshot.get('netflags') or []:
            flag_type = flag.get('flag_type') or _flag_type_from_names(
                flag.get('symbol_name'), flag.get('component_name'))
            rows.append((flag.get('name'), flag_type, _round(flag.get('x')) if flag.get('x') is not None else None,
                         _round(flag.get('y')) if flag.get('y') is not None else None,
                         flag.get('rotation'), bool(flag.get('mirror'))))
        return sorted(rows, key=repr)

    def ports_set(snapshot):
        rows = []
        for port in snapshot.get('netports') or []:
            direction = port.get('direction') or _port_direction_from_names(
                port.get('symbol_name'), port.get('component_name'))
            rows.append((port.get('net'), port.get('name'), direction,
                         _round(port.get('x')) if port.get('x') is not None else None,
                         _round(port.get('y')) if port.get('y') is not None else None,
                         port.get('rotation'), bool(port.get('mirror'))))
        return sorted(rows, key=repr)

    before_flags, after_flags = flags_set(before), flags_set(after)
    if before_flags != after_flags:
        differences.append({'kind': 'netflags', 'before': before_flags, 'after': after_flags,
                            'missing': [x for x in before_flags if x not in after_flags][:10],
                            'added': [x for x in after_flags if x not in before_flags][:10]})
    before_ports, after_ports = ports_set(before), ports_set(after)
    if before_ports != after_ports:
        differences.append({'kind': 'netports', 'before': before_ports, 'after': after_ports,
                            'missing': [x for x in before_ports if x not in after_ports][:10],
                            'added': [x for x in after_ports if x not in before_ports][:10]})

    before_attributes = before.get('attributes')
    after_attributes = after.get('attributes')
    if before_attributes is not None or after_attributes is not None:
        left = sorted(json.dumps(a, ensure_ascii=False, sort_keys=True) for a in (before_attributes or []))
        right = sorted(json.dumps(a, ensure_ascii=False, sort_keys=True) for a in (after_attributes or []))
        if left != right:
            differences.append({'kind': 'attributes', 'before_count': len(left), 'after_count': len(right),
                                'missing': [x for x in left if x not in right][:5],
                                'added': [x for x in right if x not in left][:5]})

    return {
        'match': not differences,
        'differences': differences,
        'counts': {
            'parts_before': len(before_parts), 'parts_after': len(after_parts),
            'netflags_before': len(before_flags), 'netflags_after': len(after_flags),
            'netports_before': len(before_ports), 'netports_after': len(after_ports),
            'wires_before': len(before_wires), 'wires_after': len(after_wires),
        },
        'compared_fields': ['identity', 'parts(designator,part,name,supplier_id,footprint,unique_id,position,'
                            'rotation,mirror,add_into_bom,add_into_pcb,manufacturer,manufacturer_id,supplier,'
                            'component_uuid,symbol_uuid,footprint_uuid,other_property)',
                            'duplicate_designators', 'netflags(name,type,position,rotation,mirror)',
                            'netports(net,name,direction,position,rotation,mirror)', 'wires', 'unparsed_wires',
                            'zero_length_wires(net,position)', 'attributes'],
    }


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

def _page_args(args):
    result = {}
    for name in ('page_uuid', 'schematic_name', 'page_name'):
        if getattr(args, name, None):
            result[name] = getattr(args, name)
    return result


# ---------------------------------------------------------------------------
# PCB command family (beta). Same read-first discipline as the schematic
# bridge: read a snapshot -> reconcile a typed plan in Python -> send only
# typed primitive actions -> read back -> verify -> optionally save -> reopen.
# ---------------------------------------------------------------------------

PCB_COUNT_KEYS = ('components', 'lines', 'vias', 'pours', 'poured', 'pads')
PCB_OPS = {
    'line': {'net', 'layer', 'x1', 'y1', 'x2', 'y2', 'width'},
    'via': {'net', 'x', 'y', 'hole', 'diameter'},
    'pour_outline': {'net', 'layer', 'name', 'x', 'y', 'w', 'h'},
    'component_flat': {'library_uuid', 'component_uuid', 'layer', 'x', 'y', 'rotation'},
    'component_search': {'name', 'layer', 'x', 'y', 'rotation'},
}
PCB_EXPECTED = {
    'line': {'net', 'layer', 'width'},
    'via': {'net', 'hole', 'diameter'},
    'pour_outline': {'net', 'layer', 'name'},
    'component_flat': {'layer', 'designator'},
    'component_search': {'layer', 'designator'},
}
PCB_WRITE_SUPPORT = {
    # Verified by the round-3 audit (2026-10-22) against JLCEDA Pro 4.1.78
    # bridge 4.1.78.34f5b8d9 in a half-offline CLI session on a scratch copy.
    'verified': ['line', 'via', 'pour_outline', 'component_flat', 'component_search'],
    'known_broken': [
        'component via state footprint/component object (create throws; use the flat ref or search path)',
        'pour fill recompute (outline create does not change the poured count; fills need a GUI recompute)',
    ],
    'not_probed': ['board_outline_primitive', 'component_move', 'component_rotate', 'delete', 'rule_config_write'],
    'source': 'round3-audit-2026-10-22',
}


def _pcb_args(args):
    result = {}
    for name in ('pcb_uuid', 'pcb_name'):
        if getattr(args, name, None):
            result[name] = getattr(args, name)
    return result


def read_pcb_snapshot(pro, session, pcb_args, max_primitives=2000):
    value = pro.invoke(session, PCB_SNAPSHOT_JS, {'pcb': pcb_args, 'max_primitives': max_primitives})
    if not isinstance(value, dict):
        raise EdaCommandError('pcb snapshot returned no object', 'EDA_PCB_SNAPSHOT_FAILED', {'value': value})
    if value.get('ok') is False:
        error = value.get('error') or 'pcb_snapshot_failed'
        detail = {'value': value}
        if error in ('pcb_not_found', 'ambiguous_pcb_name'):
            raise EdaInputError('pcb not found: check pcb_uuid/pcb_name', detail)
        if error in ('pcb_not_activated', 'open_document_failed'):
            raise EdaCommandError(error, 'EDA_PCB_NOT_ACTIVATED', detail)
        raise EdaCommandError(f'pcb snapshot failed: {error}', 'EDA_PCB_SNAPSHOT_FAILED', detail)
    return value


def read_pcb_with_retry(pro, session, pcb_args, attempts=3, max_primitives=2000):
    last = None
    for attempt in range(attempts):
        try:
            snapshot = read_pcb_snapshot(pro, session, pcb_args, max_primitives=max_primitives)
            if snapshot.get('selection', {}).get('pcb_uuid'):
                return snapshot
            last = {'error': 'pcb snapshot missing pcb identity', 'value': snapshot}
        except EdaInputError:
            raise
        except EdaTimeout as error:
            last = {'error': str(error), 'code': error.code}
        except EdaCommandError as error:
            last = {'error': str(error), 'code': error.code, 'detail': error.detail}
        if attempt + 1 < attempts:
            time.sleep(1.0 + attempt)
    raise EdaCommandError('pcb not readable after retries', 'EDA_PCB_NOT_READY', {'last': last})


def invoke_pcb_with_retry(pro, session, code, args, attempts=3, timeout_ms=None):
    """Retry only the activation race. pcb_not_activated is reported before any
    action runs, so retrying it cannot duplicate a write; every other failure
    is returned as-is."""
    last = None
    for attempt in range(attempts):
        value = pro.invoke(session, code, args, timeout_ms=timeout_ms)
        if isinstance(value, dict) and value.get('ok') is False and value.get('error') == 'pcb_not_activated':
            last = value
            time.sleep(1.0 + attempt)
            continue
        return value
    return last


def pcb_snapshot_integrity(snapshot):
    """A snapshot used as the basis for a write must have complete counts and
    no class-level read errors. Field-level getter misses are notes, not blockers."""
    if not isinstance(snapshot, dict) or snapshot.get('ok') is not True:
        return {'status': 'invalid', 'missing': [], 'read_errors': []}
    selection = snapshot.get('selection') or {}
    missing = [key for key in PCB_COUNT_KEYS if snapshot.get('counts', {}).get(key) is None]
    if not selection.get('pcb_uuid'):
        missing.append('pcb_uuid')
    read_errors = snapshot.get('read_errors') or []
    field_notes = snapshot.get('field_notes') or []
    status = 'complete' if not missing and not read_errors else 'incomplete'
    return {'status': status, 'missing': missing,
            'read_error_count': len(read_errors), 'read_errors': read_errors[:20],
            'field_note_count': len(field_notes), 'field_notes': field_notes[:10]}


def validate_pcb_plan(plan):
    if not isinstance(plan, dict):
        raise EdaInputError('plan: JSON object required')
    unknown = set(plan) - {'version', 'pcb', 'items', 'note'}
    if unknown:
        raise EdaInputError(f'plan: unknown fields {sorted(unknown)}')
    if plan.get('version') != 1:
        raise EdaInputError('plan.version: must be 1')
    pcb = plan.get('pcb')
    if pcb is not None:
        if not isinstance(pcb, dict):
            raise EdaInputError('plan.pcb: object required')
        unknown = set(pcb) - {'pcb_uuid'}
        if unknown:
            raise EdaInputError(f'plan.pcb: unknown fields {sorted(unknown)}')
        if pcb.get('pcb_uuid') is not None:
            _text(pcb['pcb_uuid'], 'plan.pcb.pcb_uuid')
    items = plan.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise EdaInputError('plan.items: list of 1..200 items required')
    keys = set()
    for index, item in enumerate(items):
        where = f'plan.items[{index}]'
        if not isinstance(item, dict):
            raise EdaInputError(f'{where}: object required')
        op = item.get('op')
        if op not in PCB_OPS:
            raise EdaInputError(f'{where}.op: one of {sorted(PCB_OPS)} required')
        unknown = set(item) - PCB_OPS[op] - {'op', 'key', 'expected'}
        if unknown:
            raise EdaInputError(f'{where}: unknown fields {sorted(unknown)}')
        missing = [name for name in PCB_OPS[op] if name not in item]
        if missing:
            raise EdaInputError(f'{where}: missing fields {sorted(missing)} for op {op!r}')
        key = _text(item.get('key'), f'{where}.key')
        if key in keys:
            raise EdaInputError(f'{where}.key: duplicate key {key!r}')
        keys.add(key)
        if op in ('line', 'via', 'pour_outline'):
            _text(item.get('net'), f'{where}.net')
        for name in ('x1', 'y1', 'x2', 'y2', 'x', 'y'):
            if name in item:
                _coord(item[name], f'{where}.{name}')
        for name in ('width', 'hole', 'diameter', 'w', 'h'):
            if name in item:
                value = _finite(item[name], f'{where}.{name}')
                if value <= 0:
                    raise EdaInputError(f'{where}.{name}: positive value required')
        layer = item.get('layer')
        if layer is not None:
            value = _finite(layer, f'{where}.layer')
            if op in ('component_flat', 'component_search'):
                if value not in (1, 2):
                    raise EdaInputError(f'{where}.layer: 1 (top) or 2 (bottom) required for components')
            elif not 1 <= value <= 64:
                raise EdaInputError(f'{where}.layer: 1..64 required')
        if op == 'component_flat':
            _text(item.get('library_uuid'), f'{where}.library_uuid')
            _text(item.get('component_uuid'), f'{where}.component_uuid')
        if op == 'component_search':
            _text(item.get('name'), f'{where}.name')
        if op == 'pour_outline':
            _text(item.get('name'), f'{where}.name')
        if op in ('component_flat', 'component_search'):
            _rotation(item['rotation'], f'{where}.rotation')
        expected = item.get('expected')
        if expected is not None:
            if not isinstance(expected, dict):
                raise EdaInputError(f'{where}.expected: object required')
            unknown = set(expected) - PCB_EXPECTED[op]
            if unknown:
                raise EdaInputError(f'{where}.expected: unknown fields {sorted(unknown)} for op {op!r}')
    return plan


def _pcb_lines_contain(lines, net, layer, x1, y1, x2, y2, tolerance=0.6):
    for row in lines:
        if row.get('net') != net or row.get('layer') != layer:
            continue
        if None in (row.get('x1'), row.get('y1'), row.get('x2'), row.get('y2')):
            return None  # cannot tell without endpoint geometry
        same = (abs(row['x1'] - x1) <= tolerance and abs(row['y1'] - y1) <= tolerance
                and abs(row['x2'] - x2) <= tolerance and abs(row['y2'] - y2) <= tolerance)
        flipped = (abs(row['x1'] - x2) <= tolerance and abs(row['y1'] - y2) <= tolerance
                   and abs(row['x2'] - x1) <= tolerance and abs(row['y2'] - y1) <= tolerance)
        if same or flipped:
            return True
    return False


def reconcile_pcb(snapshot, plan):
    items, actions, conflicts = [], [], []
    selection = snapshot.get('selection') or {}
    plan_pcb = plan.get('pcb') or {}
    if plan_pcb.get('pcb_uuid') and plan_pcb['pcb_uuid'] != selection.get('pcb_uuid'):
        conflicts.append({'key': None, 'error': 'pcb_uuid_mismatch',
                          'planned': plan_pcb['pcb_uuid'], 'actual': selection.get('pcb_uuid')})
    nets = {row.get('net') for row in (snapshot.get('nets') or []) if row.get('net')}
    lines = (snapshot.get('lines') or {}).get('rows', [])
    vias = (snapshot.get('vias') or {}).get('rows', [])
    pours = (snapshot.get('pours') or {}).get('rows', [])
    for item in plan['items']:
        op = item['op']
        row = {'key': item['key'], 'op': op, 'action': None, 'dedup': 'checked'}
        if op in ('line', 'via', 'pour_outline') and item['net'] not in nets:
            conflicts.append({'key': item['key'], 'op': op, 'error': 'net_not_found',
                              'net': item['net'], 'note': 'creating copper on a net missing from the PCB'})
            row['action'] = 'skip_conflict'
        elif op == 'line':
            present = _pcb_lines_contain(lines, item['net'], item['layer'],
                                         item['x1'], item['y1'], item['x2'], item['y2'])
            if present is True:
                row['action'] = 'already_present'
            elif present is None:
                row['action'] = 'create'
                row['dedup'] = 'incomplete_read'
            else:
                row['action'] = 'create'
        elif op == 'via':
            match = [v for v in vias if v.get('net') == item['net']
                     and v.get('x') is not None and v.get('y') is not None
                     and _same_position([v['x'], v['y']], [item['x'], item['y']])]
            row['action'] = 'already_present' if match else 'create'
            if not match and any(v.get('net') == item['net'] and v.get('x') is None for v in vias):
                row['dedup'] = 'incomplete_read'
        elif op == 'pour_outline':
            match = [p for p in pours if p.get('net') == item['net'] and p.get('layer') == item['layer']
                     and (p.get('name') is None or p.get('name') == item['name'])]
            row['action'] = 'already_present' if match else 'create'
            if not match and any(p.get('net') == item['net'] and p.get('layer') == item['layer'] for p in pours):
                row['dedup'] = 'incomplete_read'
        else:
            # Components get auto designators; re-running the plan would create
            # duplicates, so components are always create and never dedup.
            row['action'] = 'create'
            row['dedup'] = 'never'
        if row['action'] == 'create':
            actions.append({key: item[key] for key in PCB_OPS[op]} | {'key': item['key'], 'op': op})
        items.append(row)
    return {'items': items, 'actions': actions, 'conflicts': conflicts,
            'counts': {'items': len(items), 'actions': len(actions), 'conflicts': len(conflicts)}}


def verify_pcb_items(execution, plan, reconcile_items, after):
    by_key = {result.get('key'): result for result in (execution.get('results') or [])}
    rows = []
    failed = 0
    for item in reconcile_items:
        if item.get('action') not in ('create',):
            # skipped conflicts and already-present items were never sent;
            # their absence from the execution results is expected
            continue
        row = {'key': item['key'], 'op': item['op'], 'status': 'verified', 'mismatches': []}
        result = by_key.get(item['key'])
        if result is None:
            row['status'] = 'missing_result'
            row['error'] = 'the client returned no row for this action'
        elif not result.get('created'):
            row['status'] = 'create_failed'
            row['error'] = result.get('error') or 'create failed'
        elif not result.get('id'):
            row['status'] = 'create_failed'
            row['error'] = 'create returned no primitive id'
        else:
            row['id'] = result['id']
            planned = next((p for p in plan['items'] if p.get('key') == item['key']), {})
            expected = planned.get('expected') or {}
            for field, want in expected.items():
                got = result.get(field)
                if got != want:
                    row['status'] = 'mismatch'
                    row['mismatches'].append({'field': field, 'expected': want, 'actual': got})
        if row['status'] != 'verified':
            failed += 1
        rows.append(row)
    status = 'verified' if failed == 0 else 'conflict'
    poured_before = execution.get('poured_before')
    poured_after = execution.get('poured_after')
    pour_fill = {'poured_before': poured_before, 'poured_after': poured_after,
                 'delta': (poured_after - poured_before) if poured_before is not None and poured_after is not None else None}
    pour_fill['fill_recomputed'] = pour_fill['delta'] is not None and pour_fill['delta'] > 0
    return rows, status, pour_fill


def compare_pcb_snapshots(before, after, tolerance=0.01):
    diffs = []
    before_sel = (before or {}).get('selection') or {}
    after_sel = (after or {}).get('selection') or {}
    if before_sel.get('pcb_uuid') != after_sel.get('pcb_uuid'):
        diffs.append({'domain': 'pcb_identity', 'before': before_sel.get('pcb_uuid'),
                      'after': after_sel.get('pcb_uuid')})
    for key in PCB_COUNT_KEYS:
        before_count = (before or {}).get('counts', {}).get(key)
        after_count = (after or {}).get('counts', {}).get(key)
        if before_count != after_count:
            diffs.append({'domain': 'counts', 'class': key, 'before': before_count, 'after': after_count})
    for key in PCB_COUNT_KEYS:
        before_ids = sorted({row.get('id') for row in (before or {}).get(key, {}).get('rows', []) if row.get('id')})
        after_ids = sorted({row.get('id') for row in (after or {}).get(key, {}).get('rows', []) if row.get('id')})
        if before_ids != after_ids:
            removed = sorted(set(before_ids) - set(after_ids))
            added = sorted(set(after_ids) - set(before_ids))
            diffs.append({'domain': 'primitive_ids', 'class': key,
                          'removed': removed[:20], 'removed_count': len(removed),
                          'added': added[:20], 'added_count': len(added)})
    before_nets = sorted({row.get('net') for row in (before or {}).get('nets', []) if row.get('net')})
    after_nets = sorted({row.get('net') for row in (after or {}).get('nets', []) if row.get('net')})
    if before_nets != after_nets:
        diffs.append({'domain': 'nets', 'removed': sorted(set(before_nets) - set(after_nets)),
                      'added': sorted(set(after_nets) - set(before_nets))})
    return {'match': not diffs, 'diff_count': len(diffs), 'diffs': diffs}



def read_snapshot(pro, session, page_args, include_attributes=False, include_pins=True):
    args = {**page_args, 'include_attributes': include_attributes, 'include_pins': include_pins}
    value = pro.invoke(session, SNAPSHOT_JS, args)
    if not isinstance(value, dict):
        raise EdaCommandError('snapshot returned no object', 'EDA_SNAPSHOT_FAILED', {'value': value})
    if value.get('ok') is False:
        error = value.get('error') or 'snapshot_failed'
        detail = {'value': value}
        if error == 'page_not_found':
            raise EdaInputError('page not found: check page_uuid/schematic_name/page_name', detail)
        if error == 'ambiguous_schematic_page':
            raise EdaInputError('schematic has multiple pages; pass page_uuid or page_name', detail)
        if error in ('page_not_activated', 'open_document_failed'):
            raise EdaCommandError(error, 'EDA_PAGE_NOT_ACTIVATED', detail)
        raise EdaCommandError(f'snapshot failed: {error}', 'EDA_SNAPSHOT_FAILED', detail)
    return value


def read_with_retry(pro, session, page_args, attempts=3):
    """Retry transient read failures only; invalid page input is not transient."""
    last = None
    for attempt in range(attempts):
        try:
            snapshot = read_snapshot(pro, session, page_args)
            if snapshot.get('selection', {}).get('page_uuid'):
                return snapshot
            last = {'error': 'snapshot missing page identity', 'value': snapshot}
        except EdaInputError:
            raise
        except EdaTimeout as error:
            last = {'error': str(error), 'code': error.code}
        except EdaCommandError as error:
            last = {'error': str(error), 'code': error.code, 'detail': error.detail}
        if attempt + 1 < attempts:
            time.sleep(1.0 + attempt)
    raise EdaCommandError('project/page not readable after retries', 'EDA_PROJECT_NOT_READY', {'last': last})


def session_origin(pro, session):
    for entry in pro.sessions():
        if entry.get('sessionId') == session:
            return entry
    return None


def session_info(pro, session):
    entry = session_origin(pro, session)
    return {
        'sessionId': session,
        'origin': entry.get('origin') if entry else None,
        'path': entry.get('path') if entry else None,
        'found': entry is not None,
    }


def close_owned(pro, session, force=False):
    entry = session_origin(pro, session)
    if entry is None:
        return {'closed': False, 'reason': 'session_not_found_or_already_closed'}
    origin = entry.get('origin')
    if origin != 'cli' and not force:
        raise EdaInputError(
            f'refusing to close a session with origin {origin!r}; close it yourself or pass --force')
    return {'closed': True, 'session': pro.close_session(session)}


def _open_for_command(pro, args):
    """Return (session, owned, entry). Existing sessions are never closed implicitly."""
    if getattr(args, 'session', None):
        entry = session_origin(pro, args.session)
        if entry is None:
            raise EdaInputError(f'session not found: {args.session}')
        origin = entry.get('origin')
        allow_user = bool(getattr(args, 'allow_user_session', False))
        if origin == 'user' and not allow_user:
            raise EdaInputError(
                'refusing to drive a user-opened GUI session; pass --allow-user-session only if you own it')
        if origin not in ('cli', 'user') and not allow_user:
            raise EdaInputError(f'refusing to drive a session with unrecognized origin {origin!r}')
        return args.session, False, entry
    project = getattr(args, 'project', None)
    if not project:
        raise EdaInputError('--session or --project is required')
    return pro.open_project(project, headless=True), True, {
        'origin': 'cli', 'path': str(Path(project).resolve()), 'sessionId': None,
    }


def command_doctor(args):
    result = {
        'status': 'ok',
        'host': {'platform': sys.platform, 'os_name': os.name, 'python': sys.version.split()[0]},
        'checks': {
            'tool_present': False,
            'tool_connected': False,
            'project_readable': 'not_probed',
            'project_writable': 'not_tested',
        },
        'capabilities': {
            'sch_read': 'available',
            'sch_write_components_wires_flags_ports': 'available',
            'sch_save': 'available',
            'sch_export_png_svg_netlist': 'available',
            'sch_export_bom': 'not_implemented_in_this_adapter',
            'sch_drc': 'available',
            'sch_drc_api': 'wrapped_as_drc_command',
            'pcb_read_write': 'available_beta',
            'pcb_api': 'wrapped_as_pcb_command',
            'pcb_pour_fill': 'outline_only; fill recompute needs a GUI session',
            'project_designators': 'available',
            'net_label_idempotent_apply': 'not_implemented',
            'verified_client_prefixes': list(VERIFIED_CLIENT_PREFIXES),
            'source': 'lceda-pro 4.1.78 doc api + live probe 2026-10-21/22',
        },
        'warnings': [],
        'not_checked': ['PCB DFM', 'factory DFM', 'orders', 'realtime LCSC stock/price'],
    }
    explicit = args.exe or os.environ.get('LCEDA_PRO_EXE')
    cli = find_cli(explicit)
    result['cli'] = {'path': cli, 'explicit': bool(explicit)}
    if not cli:
        result['status'] = 'unavailable'
        result['checks']['tool_present'] = False
        result['error'] = 'lceda-pro CLI not found'
        return result, EXIT_UNAVAILABLE
    result['checks']['tool_present'] = True
    pro = LcedaPro(cli, timeout_ms=args.timeout)
    try:
        doctor = pro.doctor()
        result['doctor'] = doctor
        result['checks']['tool_connected'] = bool(doctor.get('connected')) if isinstance(doctor, dict) else False
        result['checks']['version_match'] = bool(doctor.get('versionMatch')) if isinstance(doctor, dict) else False
        result['checks']['result_channel'] = bool(doctor.get('resultChannel')) if isinstance(doctor, dict) else False
        result['checks']['version_verified'] = client_version_verified(
            {'version': (doctor or {}).get('bridgeVersion')} if isinstance(doctor, dict) else {})
        result['sessions'] = pro.sessions()
        if not result['checks']['tool_connected']:
            result['status'] = 'disconnected'
            result['warnings'].append('client is installed but the endpoint is not connected; start JLCEDA Pro')
            return result, EXIT_UNAVAILABLE
        if not result['checks']['version_match']:
            result['status'] = 'version_mismatch'
            result['warnings'].append('client version does not match the CLI bridge; writes should be refused')
        if not result['checks']['result_channel']:
            result['warnings'].append('doctor did not report a result channel')
        if not result['checks']['version_verified']:
            result['warnings'].append('client version is outside the probed list; apply refuses writes without an override')
        owned = [s for s in result['sessions'] if s.get('origin') == 'cli']
        if owned:
            try:
                result['functions_sample_session'] = owned[0].get('sessionId')
                functions = pro.functions(owned[0].get('sessionId'))
                result['functions'] = [
                    {
                        'name': (f.get('config') or {}).get('name'),
                        'display_name': (f.get('config') or {}).get('displayName'),
                        'version': (f.get('config') or {}).get('version'),
                        'uuid': f.get('uuid') or (f.get('config') or {}).get('uuid'),
                    }
                    for f in (functions or [])
                ]
            except EdaError as error:
                result['functions_error'] = str(error)
        else:
            result['functions'] = 'not_probed_no_cli_session'
        if args.project:
            session = pro.open_project(args.project, headless=True)
            try:
                probe = None
                for attempt in range(6):
                    probe = pro.invoke(session, PROJECT_PROBE_JS, {})
                    if probe.get('project') and probe.get('schematics'):
                        break
                    import time
                    time.sleep(0.75 + attempt * 0.5)
                result['project_probe'] = probe
                result['checks']['project_readable'] = bool(probe.get('project') and probe.get('schematics'))
                if not result['checks']['project_readable']:
                    result['warnings'].append('project opened but no readable project/schematic tree after retries')
                result['checks']['project_writable'] = 'not_tested'
                result['not_checked'].append('write capability on this project was not probed; use apply --dry-run/--save on an authorized copy')
            finally:
                close_owned(pro, session)
        return result, EXIT_OK
    except EdaTimeout:
        raise
    except EdaError as error:
        result['status'] = 'error'
        result['error'] = str(error)
        result['code'] = error.code
        return result, EXIT_UNAVAILABLE


def command_open(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session = pro.open_project(args.project, headless=not args.visible)
    return {'status': 'opened', 'session': session, 'project': str(Path(args.project).resolve()),
            'owned': True, 'note': 'keep this session for later commands; close it explicitly when done'}, EXIT_OK


def command_sessions(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    return {'status': 'ok', 'sessions': pro.sessions()}, EXIT_OK


def command_read(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        snapshot = read_with_retry(pro, session, _page_args(args))
        output_path = None
        if args.output:
            Path(args.output).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
            snapshot['output'] = str(Path(args.output).resolve())
            output_path = snapshot['output']
        return {'status': 'ok', 'snapshot': snapshot, 'output': output_path,
                'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}}, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def _load_json_file(path, label):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except OSError as error:
        raise EdaInputError(f'cannot read {label}: {error}')
    except json.JSONDecodeError as error:
        raise EdaInputError(f'{label} is not valid JSON: {error}')


def command_designators(args):
    """Scan every schematic page and return the project-level designator list."""
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        value = pro.invoke(session, PROJECT_DESIGNATORS_JS, {}, timeout_ms=args.invoke_timeout)
        if not isinstance(value, dict) or value.get('ok') is False:
            raise EdaCommandError('designator scan failed', 'EDA_DESIGNATORS_FAILED', {'value': value})
        rows = value.get('designators') or []
        counts = {}
        for row in rows:
            designator = row.get('designator')
            counts[designator] = counts.get(designator, 0) + 1
        duplicates = [{'designator': designator, 'count': count,
                       'entries': [r for r in rows if r.get('designator') == designator]}
                      for designator, count in sorted(counts.items()) if designator and count > 1]
        value['counts'] = {'pages': len(value.get('pages') or []), 'parts': len(rows),
                           'duplicate_designators': len(duplicates)}
        value['duplicates'] = duplicates
        value['session'] = {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}
        if args.output:
            Path(args.output).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            value['output'] = str(Path(args.output).resolve())
        status = 'ok' if value.get('complete') and not duplicates else 'incomplete'
        return {'status': status, 'project_designators': value,
                'output': value.get('output')}, EXIT_OK if status == 'ok' else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def _load_plan(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except OSError as error:
        raise EdaInputError(f'cannot read plan: {error}')
    except json.JSONDecodeError as error:
        raise EdaInputError(f'plan is not valid JSON: {error}')
    return validate_plan(data)


def command_apply(args):
    plan = _load_plan(args.plan)
    project_designators = None
    if getattr(args, 'project_designators', None):
        payload = _load_json_file(args.project_designators, 'project designator list')
        if isinstance(payload, dict) and isinstance(payload.get('project_designators'), dict):
            payload = payload['project_designators']
        project_designators = payload.get('designators') if isinstance(payload, dict) else None
        if not isinstance(project_designators, list):
            raise EdaInputError('project designator list must contain a designators array')
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        page_args = {k: v for k, v in plan['page'].items()
                     if k in ('page_uuid', 'schematic_name', 'page_name', 'settle_ms')}
        before = read_with_retry(pro, session, page_args)
        integrity = snapshot_integrity(before)
        result = {
            'status': 'ok',
            'plan': args.plan,
            'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned},
            'env': before.get('env'),
            'page': before.get('selection'),
            'before_counts': before.get('counts'),
            'integrity': integrity,
            'dry_run': bool(args.dry_run),
        }
        if integrity['status'] != 'complete':
            result['status'] = 'snapshot_incomplete'
            result['note'] = 'snapshot has read errors or incomplete lists; reconcile and write were refused'
            return result, EXIT_REVIEW

        # Freeze the page identity now; current/schematic-name must never be
        # re-resolved between the before read, the write and the after read.
        pinned_page = {
            'page_uuid': before['selection']['page_uuid'],
            'settle_ms': plan['page'].get('settle_ms', 300),
        }
        reconciliation = reconcile(before, plan, project_designators=project_designators)
        result.update({
            'status': reconciliation['status'],
            'items': reconciliation['items'],
            'actions': reconciliation['actions'],
            'conflicts': reconciliation['conflicts'],
            'pinned_page': {
                'page_uuid': before['selection']['page_uuid'],
                'schematic_name': before['selection'].get('schematic_name'),
                'page_name': before['selection'].get('page_name'),
            },
        })
        if args.dry_run:
            result['status'] = 'dry_run'
            result['note'] = 'no write was sent'
            return result, EXIT_OK if not reconciliation['conflicts'] else EXIT_REVIEW
        if any(op['op'] == 'delete' for op in plan['operations']) and not args.allow_delete:
            result['status'] = 'delete_requires_flag'
            result['note'] = ('plan contains delete operations; review the targets with --dry-run, '
                              'then pass --allow-delete to write')
            return result, EXIT_INPUT
        if reconciliation['conflicts'] and not args.allow_partial:
            result['status'] = 'blocked'
            result['note'] = 'conflicts present; nothing was written. Resolve them or inspect with read.'
            return result, EXIT_REVIEW
        if not reconciliation['actions']:
            result['status'] = 'no_changes'
            result['verification'] = 'not_needed'
            return result, EXIT_OK
        if owned and not args.save:
            result['status'] = 'needs_save'
            result['note'] = ('a temporary --project session would lose writes on close; '
                              're-run with --save or use an explicitly retained --session')
            return result, EXIT_INPUT
        if not client_version_verified(before.get('env')) and not args.allow_unverified_version:
            result['status'] = 'version_unsupported'
            result['note'] = (f'client version {before.get("env", {}).get("version")!r} is not in the verified '
                              f'list {list(VERIFIED_CLIENT_PREFIXES)}; pass --allow-unverified-version to override')
            return result, EXIT_REVIEW

        try:
            execution = pro.invoke(
                session, APPLY_JS,
                {'page': pinned_page, 'actions': reconciliation['actions']},
                timeout_ms=args.invoke_timeout,
            )
        except EdaTimeout as error:
            partial = None
            try:
                partial = read_snapshot(pro, session, pinned_page)
            except EdaError as read_error:
                partial = {'error': str(read_error), 'code': read_error.code}
            result['status'] = 'partial_unknown'
            result['error'] = str(error)
            result['partial_counts'] = partial.get('counts') if isinstance(partial, dict) else None
            result['partial_integrity'] = (
                snapshot_integrity(partial)
                if isinstance(partial, dict) and partial.get('ok') is True else None
            )
            result['note'] = ('invoke timed out; objects may exist. Re-read before retrying; '
                              'do not replay the whole plan.')
            if args.output:
                Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                result['output'] = str(Path(args.output).resolve())
            return result, EXIT_TIMEOUT

        result['execution'] = execution
        if not isinstance(execution, dict) or execution.get('ok') is False:
            result['status'] = 'preflight_failed'
            result['note'] = 'no write was sent because one or more parts could not be resolved'
            return result, EXIT_REVIEW
        time.sleep(1.0)
        after = read_with_retry(pro, session, pinned_page)
        after_integrity = snapshot_integrity(after)
        result['after_counts'] = after.get('counts')
        result['after_integrity'] = after_integrity
        result['page_after'] = after.get('selection')
        if after_integrity['status'] != 'complete':
            result['status'] = 'readback_incomplete'
            result['note'] = 'write was sent, but the readback is incomplete; verification and save are refused'
            return result, EXIT_REVIEW
        if after.get('selection', {}).get('page_uuid') != before.get('selection', {}).get('page_uuid'):
            result['status'] = 'page_changed'
            result['note'] = 'the active page changed between the before and after reads; no verification or save'
            return result, EXIT_REVIEW
        before_project = (before.get('project') or {}).get('uuid')
        after_project = (after.get('project') or {}).get('uuid')
        if before_project and after_project and before_project != after_project:
            result['status'] = 'project_changed'
            result['note'] = 'the active project changed between the before and after reads; no verification or save'
            return result, EXIT_REVIEW

        verified_items, verification_status = verify_against_snapshot(
            after, plan, reconciliation['items'], execution)
        result['verification'] = {'status': verification_status, 'items': verified_items}
        result['status'] = verification_status
        save_confirmed = False
        if args.save:
            if verification_status == 'verified':
                save_outcome = pro.invoke(session, SAVE_JS, {'page': pinned_page})
                result['save'] = save_outcome if isinstance(save_outcome, dict) else {'invalid': save_outcome}
                save_confirmed = isinstance(save_outcome, dict) and save_outcome.get('saved') is True
                if not save_confirmed:
                    result['status'] = 'save_failed'
                    result['note'] = ('plan verified in memory, but the editor did not confirm save; '
                                      'do not report persistence')
                else:
                    saved_readback = read_with_retry(pro, session, pinned_page)
                    result['saved_readback'] = saved_readback.get('counts')
                    result['saved_integrity'] = snapshot_integrity(saved_readback)
            else:
                result['save'] = {'not_attempted': 'verification did not pass; inspect before saving'}
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        return result, EXIT_OK if verification_status == 'verified' and (not args.save or save_confirmed) else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def command_save(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        outcome = pro.invoke(session, SAVE_JS, {'page': _page_args(args)})
        session_meta = {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}
        if not isinstance(outcome, dict):
            return {'status': 'save_failed', 'save': {'invalid': outcome}, 'session': session_meta}, EXIT_REVIEW
        saved = outcome.get('saved') is True
        return {'status': 'ok' if saved else 'save_failed', 'save': outcome,
                'session': session_meta}, EXIT_OK if saved else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def command_drc(args):
    """Run the schematic design-rule check on the selected page.

    The raw result is returned as-is: a boolean or a list of violations varies
    by client build. Never translate "no exception" into "DRC passed".
    """
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        value = pro.invoke(session, DRC_JS,
                           {'page': _page_args(args), 'strict': not args.no_strict},
                           timeout_ms=args.invoke_timeout)
        if not isinstance(value, dict) or value.get('ok') is False:
            raise EdaCommandError('DRC failed', 'EDA_DRC_FAILED', {'value': value})
        result = {
            'status': 'checked',
            'drc': value,
            'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned},
        }
        checked = value.get('result')
        if checked is True or checked == [] or checked == {}:
            result['summary'] = 'no_violations_reported'
        elif checked is False:
            result['summary'] = 'check_returned_false'
        elif isinstance(checked, list):
            result['summary'] = 'violations_reported'
            result['violation_count'] = len(checked)
            by_type = {}
            by_rule = {}
            for row in checked:
                if isinstance(row, dict):
                    by_type[row.get('type')] = by_type.get(row.get('type'), 0) + 1
                    by_rule[row.get('rule')] = by_rule.get(row.get('rule'), 0) + 1
            result['by_type'] = by_type
            result['by_rule'] = by_rule
        else:
            result['summary'] = 'result_reported'
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        return result, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def command_export(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        payload = {'kind': args.kind, 'name': args.name, 'netlist_type': args.netlist_type}
        if args.kind == 'png':
            resolution = {}
            if args.width:
                resolution['width'] = args.width
            if args.height:
                resolution['height'] = args.height
            payload['resolution'] = resolution or {'width': 1600}
        value = pro.invoke(session, EXPORT_JS, {'page': _page_args(args), **payload})
        if not isinstance(value, dict) or value.get('ok') is False:
            raise EdaCommandError('export failed', 'EDA_EXPORT_FAILED', {'value': value})
        data = value.pop('base64', None)
        if not data:
            raise EdaCommandError('export returned no data', 'EDA_EXPORT_EMPTY', {'value': value})
        import base64
        raw = base64.b64decode(data)
        Path(args.output).write_bytes(raw)
        value['output'] = str(Path(args.output).resolve())
        value['sha256'] = __import__('hashlib').sha256(raw).hexdigest()
        value['decoded_size'] = len(raw)
        return {'status': 'ok', 'export': value, 'output': value['output'],
                'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}}, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def command_reopen_check(args):
    expected = _load_json_file(args.snapshot, 'snapshot')
    if not isinstance(expected, dict):
        raise EdaInputError('snapshot must be a JSON object')
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    closed = None
    if args.session:
        entry = session_origin(pro, args.session)
        if entry is None:
            raise EdaInputError(f'session not found: {args.session}')
        if entry.get('origin') != 'cli' and not args.force_close:
            raise EdaInputError(
                f'refusing to use a session with origin {entry.get("origin")!r}; '
                'pass --force-close only if you own it')
        expected_project = (expected.get('project') or {}).get('uuid')
        if expected_project:
            probe = pro.invoke(args.session, PROJECT_PROBE_JS, {})
            actual_project = (probe.get('project') or {}).get('uuid') if isinstance(probe, dict) else None
            if actual_project and actual_project != expected_project:
                raise EdaInputError(
                    'the supplied session belongs to a different project than the snapshot; refusing to close it')
        if entry.get('path') and Path(entry['path']).resolve() != Path(args.project).resolve():
            raise EdaInputError(
                'the supplied session path does not match --project; refusing to close it')
        closed = close_owned(pro, args.session, force=args.force_close)
    session = pro.open_project(args.project, headless=True)
    try:
        actual = read_with_retry(pro, session, _page_args(args))
        actual_integrity = snapshot_integrity(actual)
        result = {
            'project': str(Path(args.project).resolve()),
            'snapshot': str(Path(args.snapshot).resolve()),
            'closed_session': closed,
            'actual_counts': actual.get('counts'),
            'actual_integrity': actual_integrity,
        }
        if actual_integrity['status'] != 'complete':
            result['status'] = 'incomplete'
            result['note'] = 'the reopened read is incomplete; a match cannot be claimed'
            return result, EXIT_REVIEW
        comparison = compare_snapshots(expected, actual)
        result['comparison'] = comparison
        result['status'] = 'match' if comparison['match'] else 'mismatch'
        return result, EXIT_OK if comparison['match'] else EXIT_REVIEW
    finally:
        close_owned(pro, session)


def command_close(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    result = close_owned(pro, args.session, force=args.force)
    if not result.get('closed'):
        return {'status': 'not_found', **result}, EXIT_REVIEW
    return {'status': 'closed', **result}, EXIT_OK


def command_pcb_doctor(args):
    """Diagnose PCB API availability without writing. Write support is reported
    from probe evidence, not from this run."""
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        value = invoke_pcb_with_retry(pro, session, PCB_SNAPSHOT_JS,
                                     {'pcb': _pcb_args(args), 'max_primitives': 10},
                                     timeout_ms=args.invoke_timeout)
        if not isinstance(value, dict) or value.get('ok') is not True:
            error = (value or {}).get('error', 'pcb_probe_failed') if isinstance(value, dict) else 'pcb_probe_failed'
            result = {'status': 'probe_failed', 'error': error, 'value': value,
                      'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}}
            return result, EXIT_REVIEW
        integrity = pcb_snapshot_integrity(value)
        result = {
            'status': integrity['status'],
            'env': value.get('env'),
            'pcbs': value.get('pcbs'),
            'selection': value.get('selection'),
            'counts': value.get('counts'),
            'nets_read': len(value.get('nets') or []),
            'rule_config': value.get('rule_config'),
            'read_errors': integrity['read_errors'],
            'write_support': PCB_WRITE_SUPPORT,
            'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned},
            'note': 'write support comes from prior probe evidence; re-probe after a client upgrade',
        }
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        return result, EXIT_OK if integrity['status'] == 'complete' else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def command_pcb_read(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        snapshot = read_pcb_with_retry(pro, session, _pcb_args(args),
                                       max_primitives=args.max_primitives)
        snapshot['integrity'] = pcb_snapshot_integrity(snapshot)
        snapshot['session'] = {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}
        if args.output:
            Path(args.output).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
            snapshot['output'] = str(Path(args.output).resolve())
        return {'status': 'ok', 'snapshot': snapshot, 'output': snapshot.get('output'),
                'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}}, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def _load_pcb_plan(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except OSError as error:
        raise EdaInputError(f'cannot read plan: {error}')
    except json.JSONDecodeError as error:
        raise EdaInputError(f'plan is not valid JSON: {error}')
    return validate_pcb_plan(data)


def command_pcb_apply(args):
    plan = _load_pcb_plan(args.plan)
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        pcb_args = _pcb_args(args)
        before = read_pcb_with_retry(pro, session, pcb_args)
        integrity = pcb_snapshot_integrity(before)
        result = {
            'status': 'ok',
            'plan': args.plan,
            'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned},
            'env': before.get('env'),
            'pcb': before.get('selection'),
            'before_counts': before.get('counts'),
            'integrity': integrity,
            'dry_run': bool(args.dry_run),
        }
        if integrity['status'] != 'complete':
            result['status'] = 'snapshot_incomplete'
            result['note'] = 'pcb snapshot has missing counts or read errors; reconcile and write were refused'
            return result, EXIT_REVIEW
        pinned_pcb = {'pcb_uuid': before['selection']['pcb_uuid']}
        reconciliation = reconcile_pcb(before, plan)
        result.update({
            'status': reconciliation['conflicts'] and 'conflict' or 'ok',
            'items': reconciliation['items'],
            'actions': reconciliation['actions'],
            'conflicts': reconciliation['conflicts'],
            'pinned_pcb': pinned_pcb,
        })
        if args.dry_run:
            result['status'] = 'dry_run'
            result['note'] = 'no write was sent'
            return result, EXIT_OK if not reconciliation['conflicts'] else EXIT_REVIEW
        if reconciliation['conflicts'] and not args.allow_partial:
            result['status'] = 'blocked'
            result['note'] = 'conflicts present; nothing was written. Resolve them or inspect with pcb read.'
            return result, EXIT_REVIEW
        if not reconciliation['actions']:
            result['status'] = 'no_changes'
            result['verification'] = 'not_needed'
            return result, EXIT_OK
        if owned and not args.save:
            result['status'] = 'needs_save'
            result['note'] = ('a temporary --project session would lose writes on close; '
                              're-run with --save or use an explicitly retained --session')
            return result, EXIT_INPUT
        if not client_version_verified(before.get('env')) and not args.allow_unverified_version:
            result['status'] = 'version_unsupported'
            result['note'] = (f'client version {before.get("env", {}).get("version")!r} is not in the verified '
                              f'list {list(VERIFIED_CLIENT_PREFIXES)}; pass --allow-unverified-version to override')
            return result, EXIT_REVIEW

        try:
            execution = invoke_pcb_with_retry(
                pro, session, PCB_APPLY_JS,
                {'pcb': pinned_pcb, 'actions': reconciliation['actions']},
                timeout_ms=args.invoke_timeout,
            )
        except EdaTimeout as error:
            partial = None
            try:
                partial = read_pcb_snapshot(pro, session, pinned_pcb)
            except EdaError as read_error:
                partial = {'error': str(read_error), 'code': read_error.code}
            result['status'] = 'partial_unknown'
            result['error'] = str(error)
            result['partial_counts'] = partial.get('counts') if isinstance(partial, dict) else None
            result['partial_integrity'] = (
                pcb_snapshot_integrity(partial)
                if isinstance(partial, dict) and partial.get('ok') is True else None
            )
            result['note'] = ('invoke timed out; objects may exist. Re-read before retrying; '
                              'do not replay the whole plan.')
            if args.output:
                Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                result['output'] = str(Path(args.output).resolve())
            return result, EXIT_TIMEOUT

        result['execution'] = execution
        if not isinstance(execution, dict) or execution.get('ok') is not True:
            result['status'] = 'preflight_failed'
            result['note'] = 'the client did not return a clean execution envelope'
            return result, EXIT_REVIEW
        time.sleep(1.0)
        after = read_pcb_with_retry(pro, session, pinned_pcb)
        after_integrity = pcb_snapshot_integrity(after)
        result['after_counts'] = after.get('counts')
        result['after_integrity'] = after_integrity
        if after_integrity['status'] != 'complete':
            result['status'] = 'readback_incomplete'
            result['note'] = 'write was sent, but the readback is incomplete; verification and save are refused'
            return result, EXIT_REVIEW
        if after.get('selection', {}).get('pcb_uuid') != before.get('selection', {}).get('pcb_uuid'):
            result['status'] = 'pcb_changed'
            result['note'] = 'the active pcb changed between the before and after reads; no verification or save'
            return result, EXIT_REVIEW
        before_project = (before.get('project') or {}).get('uuid')
        after_project = (after.get('project') or {}).get('uuid')
        if before_project and after_project and before_project != after_project:
            result['status'] = 'project_changed'
            result['note'] = 'the active project changed between the before and after reads; no verification or save'
            return result, EXIT_REVIEW

        verified_items, verification_status, pour_fill = verify_pcb_items(
            execution, plan, reconciliation['items'], after)
        result['verification'] = {'status': verification_status, 'items': verified_items,
                                  'pour_fill': pour_fill}
        result['status'] = verification_status
        save_confirmed = False
        if args.save:
            if verification_status == 'verified':
                save_outcome = invoke_pcb_with_retry(pro, session, PCB_SAVE_JS, {'pcb': pinned_pcb})
                result['save'] = save_outcome if isinstance(save_outcome, dict) else {'invalid': save_outcome}
                save_confirmed = isinstance(save_outcome, dict) and save_outcome.get('saved') is True
                if not save_confirmed:
                    result['status'] = 'save_failed'
                    result['note'] = ('plan verified in memory, but the editor did not confirm save; '
                                      'do not report persistence')
                else:
                    result['saved_counts'] = save_outcome.get('counts')
            else:
                result['save'] = {'not_attempted': 'verification did not pass; inspect before saving'}
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        return result, EXIT_OK if verification_status == 'verified' and (not args.save or save_confirmed) else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def command_pcb_save(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        outcome = invoke_pcb_with_retry(pro, session, PCB_SAVE_JS, {'pcb': _pcb_args(args)}, timeout_ms=args.invoke_timeout)
        session_meta = {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}
        if not isinstance(outcome, dict):
            return {'status': 'save_failed', 'save': {'invalid': outcome}, 'session': session_meta}, EXIT_REVIEW
        if outcome.get('saved') is not True:
            return {'status': 'save_failed', 'save': outcome, 'session': session_meta,
                    'note': 'the editor did not confirm save; do not report persistence'}, EXIT_REVIEW
        return {'status': 'ok', 'save': outcome, 'session': session_meta,
                'note': 'saved flag is the client\'s confirmation; reopen-check is the persistence proof'}, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def command_pcb_drc(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        value = invoke_pcb_with_retry(pro, session, PCB_DRC_JS, {'pcb': _pcb_args(args)}, timeout_ms=args.invoke_timeout)
        if not isinstance(value, dict) or value.get('ok') is not True:
            raise EdaCommandError('pcb drc failed', 'EDA_PCB_DRC_FAILED', {'value': value})
        result = {
            'status': 'ran' if value.get('ran') else 'nothing_returned',
            'structure': value.get('structure'),
            'item_count': value.get('item_count'),
            'raw': value.get('raw'),
            'note': value.get('note'),
            'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned},
        }
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        return result, EXIT_OK if value.get('ran') else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def _pcb_export_write(raw, structure, kind, out_dir, name):
    """Persist whatever the client returned, without guessing about content.

    A returned file path is copied and hashed. Anything else is captured
    verbatim with a structural hint, and the caller must inspect it before
    treating it as manufacturing data."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if structure == 'string' and isinstance(raw, str) and len(raw) < 4000:
        candidate = Path(raw)
        try:
            candidate = candidate.expanduser().resolve()
        except OSError:
            candidate = None
        if candidate and candidate.is_file():
            destination = out_dir / f'{name}-{kind}{candidate.suffix}'
            shutil.copy2(candidate, destination)
            return {'disposition': 'file_copied', 'path': str(destination),
                    'source': str(candidate), 'bytes': destination.stat().st_size,
                    'sha256': sha256_file(destination)}
    capture = out_dir / f'{name}-{kind}-raw.json'
    capture.write_text(json.dumps({'kind': kind, 'structure': structure, 'raw': raw},
                                  ensure_ascii=False, indent=2), encoding='utf-8')
    return {'disposition': 'captured_raw', 'path': str(capture),
            'bytes': capture.stat().st_size, 'sha256': sha256_file(capture),
            'note': 'the client returned no usable file path; the raw value was captured verbatim'}


def command_pcb_export(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned, entry = _open_for_command(pro, args)
    try:
        value = invoke_pcb_with_retry(pro, session, PCB_EXPORT_JS, {'pcb': _pcb_args(args), 'kind': args.kind},
                                     timeout_ms=args.invoke_timeout)
        if not isinstance(value, dict) or value.get('ok') is not True:
            error = (value or {}).get('error', 'export_failed') if isinstance(value, dict) else 'export_failed'
            return {'status': 'export_failed', 'error': error, 'kind': args.kind,
                    'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}}, EXIT_REVIEW
        raw = value.get('raw')
        structure = value.get('structure')
        if structure == 'null' or raw is None:
            result = {'status': 'nothing_returned', 'kind': args.kind, 'structure': structure,
                      'note': 'the client returned no data for this export kind; treat as NOT RUN, not as a file',
                      'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}}
            return result, EXIT_REVIEW
        written = _pcb_export_write(raw, structure, args.kind, args.out_dir, args.name)
        result = {'status': written['disposition'], 'kind': args.kind, 'structure': structure,
                  'hint': value.get('hint'), 'written': written,
                  'note': value.get('note'),
                  'session': {'sessionId': session, 'origin': entry.get('origin'), 'owned': owned}}
        return result, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def command_pcb_reopen_check(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    before = None
    first_session = None
    second_session = None
    try:
        if args.session:
            entry = session_origin(pro, args.session)
            if entry is None:
                raise EdaInputError(f'session not found: {args.session}')
            if entry.get('origin') != 'cli' and not args.force_close:
                raise EdaInputError(
                    f'refusing to close a session with origin {entry.get("origin")!r}; pass --force-close to proceed')
            first_session = args.session
            before = read_pcb_with_retry(pro, first_session, _pcb_args(args),
                                         max_primitives=args.max_primitives)
        elif args.project:
            first_session = pro.open_project(args.project, headless=True)
            before = read_pcb_with_retry(pro, first_session, _pcb_args(args),
                                         max_primitives=args.max_primitives)
        else:
            raise EdaInputError('--session or --project is required')
        pinned = {'pcb_uuid': before['selection']['pcb_uuid']}
        closed = close_owned(pro, first_session, force=args.force_close)
        second_session = pro.open_project(args.project, headless=True)
        after = read_pcb_with_retry(pro, second_session, pinned,
                                    max_primitives=args.max_primitives)
        comparison = compare_pcb_snapshots(before, after)
        result = {
            'status': 'match' if comparison['match'] else 'mismatch',
            'comparison': comparison,
            'pcb': before.get('selection'),
            'before_counts': before.get('counts'),
            'after_counts': after.get('counts'),
            'closed': closed,
            'before_integrity': pcb_snapshot_integrity(before),
            'after_integrity': pcb_snapshot_integrity(after),
            'note': 'match covers pcb identity, counts, primitive ids and net names on this snapshot budget',
        }
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        return result, EXIT_OK if comparison['match'] else EXIT_REVIEW
    finally:
        for owned_session in (first_session, second_session):
            if owned_session:
                try:
                    close_owned(pro, owned_session, force=True)
                except EdaError:
                    pass


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--exe', help='path to lceda-pro (default: LCEDA_PRO_EXE, PATH, common installs)')
    parser.add_argument('--timeout', type=int, default=120000, help='CLI timeout in ms (default 120000)')
    sub = parser.add_subparsers(dest='command', required=True)

    doctor = sub.add_parser('doctor', help='diagnose host, CLI, connection and optional project readability')
    doctor.add_argument('--project', help='read-only project probe path')
    doctor.set_defaults(func=command_doctor)

    open_cmd = sub.add_parser('open', help='open a project and return an owned session')
    open_cmd.add_argument('--project', required=True)
    open_cmd.add_argument('--visible', action='store_true', help='open a visible window instead of headless')
    open_cmd.set_defaults(func=command_open)

    sessions = sub.add_parser('sessions', help='list sessions (read-only)')
    sessions.set_defaults(func=command_sessions)

    read = sub.add_parser('read', help='read a page snapshot without writing')
    read.add_argument('--session')
    read.add_argument('--project')
    read.add_argument('--page', dest='page_uuid')
    read.add_argument('--schematic', dest='schematic_name')
    read.add_argument('--page-name', dest='page_name')
    read.add_argument('--output')
    read.add_argument('--allow-user-session', action='store_true',
                      help='allow driving a session opened by the user (default: refuse)')
    read.set_defaults(func=command_read)

    designators = sub.add_parser('designators', help='scan every schematic page for project-level designators')
    designators.add_argument('--session')
    designators.add_argument('--project')
    designators.add_argument('--invoke-timeout', type=int, default=180000)
    designators.add_argument('--output')
    designators.add_argument('--allow-user-session', action='store_true')
    designators.set_defaults(func=command_designators)

    apply_cmd = sub.add_parser('apply', help='reconcile and apply a constrained plan, then read back')
    apply_cmd.add_argument('--session')
    apply_cmd.add_argument('--project')
    apply_cmd.add_argument('--plan', required=True)
    apply_cmd.add_argument('--save', action='store_true', help='save after successful verification')
    apply_cmd.add_argument('--dry-run', action='store_true', help='reconcile only; write nothing')
    apply_cmd.add_argument('--allow-partial', action='store_true', help='execute non-conflicting actions')
    apply_cmd.add_argument('--allow-delete', action='store_true',
                           help='allow delete operations after reviewing their targets')
    apply_cmd.add_argument('--project-designators',
                           help='JSON from the designators command; enables project-level uniqueness checks')
    apply_cmd.add_argument('--allow-unverified-version', action='store_true',
                           help='allow a write on a client version outside the probed list')
    apply_cmd.add_argument('--allow-user-session', action='store_true',
                           help='allow driving a session opened by the user (default: refuse)')
    apply_cmd.add_argument('--invoke-timeout', type=int, default=180000)
    apply_cmd.add_argument('--output')
    apply_cmd.set_defaults(func=command_apply)

    save = sub.add_parser('save', help='save the current document and read counts back')
    save.add_argument('--session')
    save.add_argument('--project')
    save.add_argument('--page', dest='page_uuid')
    save.add_argument('--schematic', dest='schematic_name')
    save.add_argument('--page-name', dest='page_name')
    save.add_argument('--allow-user-session', action='store_true')
    save.set_defaults(func=command_save)

    drc = sub.add_parser('drc', help='run schematic DRC on the selected page and return the raw result')
    drc.add_argument('--session')
    drc.add_argument('--project')
    drc.add_argument('--page', dest='page_uuid')
    drc.add_argument('--schematic', dest='schematic_name')
    drc.add_argument('--page-name', dest='page_name')
    drc.add_argument('--no-strict', action='store_true', help='call sch_Drc.check with strict=false')
    drc.add_argument('--invoke-timeout', type=int, default=180000)
    drc.add_argument('--allow-user-session', action='store_true')
    drc.add_argument('--output')
    drc.set_defaults(func=command_drc)

    export = sub.add_parser('export', help='export PNG/netlist/SVG from the current page')
    export.add_argument('--session')
    export.add_argument('--project')
    export.add_argument('--allow-user-session', action='store_true')
    export.add_argument('--kind', required=True, choices=['png', 'netlist', 'svg'])
    export.add_argument('--output', required=True)
    export.add_argument('--name', default='eda-export')
    export.add_argument('--width', type=int)
    export.add_argument('--height', type=int)
    export.add_argument('--netlist-type', default='Protel2')
    export.add_argument('--page', dest='page_uuid')
    export.add_argument('--schematic', dest='schematic_name')
    export.add_argument('--page-name', dest='page_name')
    export.set_defaults(func=command_export)

    reopen = sub.add_parser('reopen-check', help='close, reopen and compare stable identity/connectivity')
    reopen.add_argument('--project', required=True)
    reopen.add_argument('--snapshot', required=True)
    reopen.add_argument('--session', help='owned session to close first')
    reopen.add_argument('--force-close', action='store_true')
    reopen.add_argument('--page', dest='page_uuid')
    reopen.add_argument('--schematic', dest='schematic_name')
    reopen.add_argument('--page-name', dest='page_name')
    reopen.add_argument('--output')
    reopen.set_defaults(func=command_reopen_check)

    close = sub.add_parser('close', help='close a session; refuses user sessions unless --force')
    close.add_argument('--session', required=True)
    close.add_argument('--force', action='store_true')
    close.set_defaults(func=command_close)

    pcb = sub.add_parser('pcb', help='read/apply/save/check the PCB document (beta command family)')
    pcb_sub = pcb.add_subparsers(dest='pcb_command', required=True)

    def pcb_session_args(p):
        p.add_argument('--session')
        p.add_argument('--project')
        p.add_argument('--pcb', dest='pcb_uuid')
        p.add_argument('--pcb-name', dest='pcb_name')
        p.add_argument('--allow-user-session', action='store_true',
                       help='allow driving a session opened by the user (default: refuse)')
        p.add_argument('--invoke-timeout', type=int, default=180000)

    pcb_doctor = pcb_sub.add_parser('doctor',
                                    help='diagnose pcb API availability without writing')
    pcb_session_args(pcb_doctor)
    pcb_doctor.add_argument('--output')
    pcb_doctor.set_defaults(func=command_pcb_doctor)

    pcb_read = pcb_sub.add_parser('read', help='read a pcb snapshot without writing')
    pcb_session_args(pcb_read)
    pcb_read.add_argument('--max-primitives', type=int, default=2000)
    pcb_read.add_argument('--output')
    pcb_read.set_defaults(func=command_pcb_read)

    pcb_apply = pcb_sub.add_parser('apply', help='reconcile and apply a typed pcb plan, then read back')
    pcb_session_args(pcb_apply)
    pcb_apply.add_argument('--plan', required=True)
    pcb_apply.add_argument('--save', action='store_true', help='save after successful verification')
    pcb_apply.add_argument('--dry-run', action='store_true', help='reconcile only; write nothing')
    pcb_apply.add_argument('--allow-partial', action='store_true', help='execute non-conflicting actions')
    pcb_apply.add_argument('--allow-unverified-version', action='store_true',
                           help='allow a write on a client version outside the probed list')
    pcb_apply.add_argument('--output')
    pcb_apply.set_defaults(func=command_pcb_apply)

    pcb_save = pcb_sub.add_parser('save', help='save the pcb document and read counts back')
    pcb_session_args(pcb_save)
    pcb_save.set_defaults(func=command_pcb_save)

    pcb_drc = pcb_sub.add_parser('drc', help='run pcb DRC and return the raw result')
    pcb_session_args(pcb_drc)
    pcb_drc.add_argument('--output')
    pcb_drc.set_defaults(func=command_pcb_drc)

    pcb_export = pcb_sub.add_parser('export', help='capture manufacturing exports from the pcb document')
    pcb_session_args(pcb_export)
    pcb_export.add_argument('--kind', required=True,
                            choices=['gerber', 'pickandplace', 'bom', 'pdf', 'pcb_info'])
    pcb_export.add_argument('--out-dir', required=True)
    pcb_export.add_argument('--name', default='eda-pcb-export')
    pcb_export.set_defaults(func=command_pcb_export)

    pcb_reopen = pcb_sub.add_parser('reopen-check', help='close, reopen and compare pcb identity/connectivity')
    pcb_reopen.add_argument('--session')
    pcb_reopen.add_argument('--project', required=True)
    pcb_reopen.add_argument('--pcb', dest='pcb_uuid')
    pcb_reopen.add_argument('--pcb-name', dest='pcb_name')
    pcb_reopen.add_argument('--force-close', action='store_true')
    pcb_reopen.add_argument('--max-primitives', type=int, default=2000)
    pcb_reopen.add_argument('--invoke-timeout', type=int, default=180000)
    pcb_reopen.add_argument('--output')
    pcb_reopen.set_defaults(func=command_pcb_reopen_check)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result, code = args.func(args)
        if getattr(args, 'output', None) and 'output' not in result:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except EdaTimeout as error:
        print(json.dumps({'status': 'timeout', 'error': str(error), 'code': error.code,
                          'warning': 'the operation may have partially changed the project; re-read before retrying',
                          'detail': error.detail}, ensure_ascii=False, indent=2))
        return EXIT_TIMEOUT
    except EdaInputError as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error), 'code': error.code,
                          'detail': error.detail}, ensure_ascii=False, indent=2))
        return EXIT_INPUT
    except EdaUnavailable as error:
        print(json.dumps({'status': 'unavailable', 'error': str(error), 'code': error.code,
                          'detail': error.detail}, ensure_ascii=False, indent=2))
        return EXIT_UNAVAILABLE
    except EdaError as error:
        print(json.dumps({'status': 'error', 'error': str(error), 'code': error.code,
                          'detail': error.detail}, ensure_ascii=False, indent=2))
        return EXIT_UNAVAILABLE
    except KeyboardInterrupt:
        print(json.dumps({'status': 'interrupted', 'error': 'interrupted by user'}, ensure_ascii=False))
        return 130


if __name__ == '__main__':
    sys.exit(main())
