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
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
    'delete_wire': {'op', 'key', 'match', 'note'},
    'delete_component': {'op', 'key', 'match', 'note'},
}
NET_FLAG_TYPES = {'Power', 'Ground', 'AnalogGround', 'ProtectGround'}
NET_PORT_DIRECTIONS = {'IN', 'OUT', 'BI'}
DELETE_WIRE_MATCH_KEYS = {'primitive_id', 'net', 'points'}
DELETE_COMPONENT_MATCH_KEYS = {'primitive_id', 'component_type', 'name', 'net', 'at'}
DELETABLE_COMPONENT_TYPES = {'netflag', 'netport'}


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


def _segments_from_line(line):
    try:
        return _canonical_segments(line)
    except EdaInputError:
        return (), []


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


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i, ch in enumerate(text) if ch == '{']
    for start in starts:
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(value, dict):
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
    const p = P.page_name ? (s.page || []).find(x => x.name === P.page_name) : (s.page || [])[0];
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
await sleep(300);
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
const mapPart = (c) => ({
  primitive_id: safe(() => c.getState_PrimitiveId()),
  component_type: safe(() => c.getState_ComponentType()),
  designator: safe(() => c.getState_Designator()),
  name: safe(() => c.getState_Name()),
  x: safe(() => c.getState_X()),
  y: safe(() => c.getState_Y()),
  rotation: safe(() => c.getState_Rotation()),
  mirror: safe(() => c.getState_Mirror()),
  add_into_bom: safe(() => c.getState_AddIntoBom()),
  add_into_pcb: safe(() => c.getState_AddIntoPcb()),
  unique_id: safe(() => c.getState_UniqueId()),
  component: safe(() => c.getState_Component()),
  symbol: safe(() => c.getState_Symbol()),
  footprint: safe(() => c.getState_Footprint()),
  sub_part_name: safe(() => c.getState_SubPartName()),
  manufacturer: safe(() => c.getState_Manufacturer()),
  manufacturer_id: safe(() => c.getState_ManufacturerId()),
  supplier: safe(() => c.getState_Supplier()),
  supplier_id: safe(() => c.getState_SupplierId()),
  other_property: A.include_properties === false ? null : safe(() => c.getState_OtherProperty()),
  pins: [],
});
const parts = comps.filter(c => safe(() => c.getState_ComponentType()) === 'part').map(mapPart);
if (pinsComplete) {
  for (const part of parts) {
    if (pinsUsed >= pinBudget) { pinsComplete = false; break; }
    const pins = await safeAsync(() => eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(part.primitive_id), []);
    part.pins = (pins || []).map(p => ({ ...p }));
    pinsUsed += part.pins.length;
  }
}
const netflags = comps.filter(c => safe(() => c.getState_ComponentType()) === 'netflag').map(c => ({
  primitive_id: safe(() => c.getState_PrimitiveId()),
  name: safe(() => c.getState_Name()),
  x: safe(() => c.getState_X()),
  y: safe(() => c.getState_Y()),
  rotation: safe(() => c.getState_Rotation()),
  mirror: safe(() => c.getState_Mirror()),
}));
const netports = comps.filter(c => safe(() => c.getState_ComponentType()) === 'netport').map(c => ({
  primitive_id: safe(() => c.getState_PrimitiveId()),
  net: safe(() => c.getState_Net()),
  name: safe(() => c.getState_Name()),
  x: safe(() => c.getState_X()),
  y: safe(() => c.getState_Y()),
  rotation: safe(() => c.getState_Rotation()),
}));
let attributes = [];
let attributesComplete = true;
if (A.include_attributes) {
  const raw = await safeAsync(() => eda.sch_PrimitiveAttribute.getAll(), []);
  attributesComplete = raw.length <= 500;
  attributes = raw.slice(0, 500).map(a => {
    const names = Object.getOwnPropertyNames(Object.getPrototypeOf(a)).filter(k => k.startsWith('getState_'));
    return Object.fromEntries(names.map(k => [k, safe(() => a[k]())]));
  });
}
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
    wires: wires.length,
    attributes: A.include_attributes ? attributes.length : null,
  },
  parts,
  netflags,
  netports,
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

APPLY_JS = r'''
const A = __ARGS__;
''' + PAGE_SELECT_JS + r'''
const sleep2 = ms => new Promise(r => setTimeout(r, ms));
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
      const after = await eda.sch_PrimitiveComponent.get(id);
      results.push({
        key: act.key, ok: true, action: act.action, primitive_id: id,
        designator: after ? after.getState_Designator() : null,
        unique_id: after ? after.getState_UniqueId() : null,
        x: after ? after.getState_X() : null, y: after ? after.getState_Y() : null,
      });
    } else if (act.action === 'modify_part') {
      const before = await eda.sch_PrimitiveComponent.get(act.primitive_id);
      const beforeState = before ? {
        designator: before.getState_Designator(), x: before.getState_X(), y: before.getState_Y(),
        rotation: before.getState_Rotation(), mirror: before.getState_Mirror(),
      } : null;
      await eda.sch_PrimitiveComponent.modify(act.primitive_id, act.changes);
      await sleep2(350);
      const after = await eda.sch_PrimitiveComponent.get(act.primitive_id);
      results.push({
        key: act.key, ok: true, action: act.action, primitive_id: act.primitive_id,
        before: beforeState,
        after: after ? {
          designator: after.getState_Designator(), x: after.getState_X(), y: after.getState_Y(),
          rotation: after.getState_Rotation(), mirror: after.getState_Mirror(),
        } : null,
      });
    } else if (act.action === 'create_net_flag') {
      const flag = await eda.sch_PrimitiveComponent.createNetFlag(
        act.type, act.net, act.x, act.y, act.rotation || 0, !!act.mirror
      );
      await sleep2(500);
      results.push({ key: act.key, ok: true, action: act.action, primitive_id: flag.getState_PrimitiveId(), net: flag.getState_Name() });
    } else if (act.action === 'create_net_port') {
      const port = await eda.sch_PrimitiveComponent.createNetPort(
        act.direction, act.net, act.x, act.y, act.rotation || 0, !!act.mirror
      );
      await sleep2(500);
      results.push({ key: act.key, ok: true, action: act.action, primitive_id: port.getState_PrimitiveId(), net: port.getState_Net() });
    } else if (act.action === 'create_wire') {
      const wire = await eda.sch_PrimitiveWire.create(act.segments || act.points, act.net);
      await sleep2(300);
      results.push({
        key: act.key, ok: true, action: act.action, primitive_id: wire.getState_PrimitiveId(),
        net: wire.getState_Net(), line: wire.getState_Line(),
      });
    } else if (act.action === 'delete_wire') {
      const before = await eda.sch_PrimitiveWire.get(act.primitive_id);
      if (!before) throw new Error('wire_not_found: ' + act.primitive_id);
      const beforeNet = before.getState_Net();
      if (beforeNet !== act.net) throw new Error('wire_net_changed: ' + beforeNet + ' != ' + act.net);
      const deleted = await eda.sch_PrimitiveWire.delete(act.primitive_id);
      await sleep2(300);
      results.push({
        key: act.key, ok: !!deleted, action: act.action, primitive_id: act.primitive_id,
        deleted: !!deleted, before: { net: beforeNet, line: before.getState_Line() },
      });
    } else if (act.action === 'delete_component') {
      const before = await eda.sch_PrimitiveComponent.get(act.primitive_id);
      if (!before) throw new Error('component_not_found: ' + act.primitive_id);
      const beforeType = before.getState_ComponentType();
      if (beforeType !== act.component_type) {
        throw new Error('component_type_changed: ' + beforeType + ' != ' + act.component_type);
      }
      if (act.component_type !== 'netflag' && act.component_type !== 'netport') {
        throw new Error('refusing to delete component type: ' + beforeType);
      }
      const deleted = await eda.sch_PrimitiveComponent.delete(act.primitive_id);
      await sleep2(300);
      results.push({
        key: act.key, ok: !!deleted, action: act.action, primitive_id: act.primitive_id,
        deleted: !!deleted, before: {
          component_type: beforeType,
          name: safe(() => before.getState_Name()),
          net: safe(() => before.getState_Net()),
          x: safe(() => before.getState_X()), y: safe(() => before.getState_Y()),
        },
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
return { ok: true, results };
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
const raw = await eda.sch_Drc.check(true, false, true);
const violations = (raw || []).map(v => {
  if (typeof v === 'string') return v;
  try { return JSON.parse(JSON.stringify(v)); } catch (e) { return String(v); }
});
return {
  ok: true,
  page: { uuid: selected.p.uuid, name: selected.p.name },
  passed: violations.length === 0,
  count: violations.length,
  violations,
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
} else if (A.kind === 'bom') {
  file = await eda.sch_ManufactureData.getBomFile(A.name || 'export', A.bom_type || 'csv');
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
        elif kind == 'delete_wire':
            match = op.get('match')
            if not isinstance(match, dict):
                raise EdaInputError(f'{where}.match: object required')
            unknown = set(match) - DELETE_WIRE_MATCH_KEYS
            if unknown:
                raise EdaInputError(f'{where}.match: unknown fields {sorted(unknown)}')
            _text(match.get('primitive_id'), f'{where}.match.primitive_id')
            net = match.get('net')
            if not isinstance(net, str):
                raise EdaInputError(f'{where}.match.net: string required')
            if net:
                _text(net, f'{where}.match.net')
            else:
                # 4.1.78 leaves zero-length, unnamed wire stubs at net ports.
                # They carry no connectivity but must be identifiable for cleanup.
                if not match.get('points'):
                    raise EdaInputError(f'{where}.match.points: required for an unnamed wire')
                flat = match['points']
                if isinstance(flat, list) and flat and isinstance(flat[0], list):
                    flat = [v for segment in flat for v in segment]
                if len(flat) < 4 or len(flat) % 2:
                    raise EdaInputError(f'{where}.match.points: flat even-length coordinate list required')
                for value in flat:
                    _coord(value, f'{where}.match.points')
            if net and match.get('points') is not None:
                _canonical_segments(match['points'])
            normalized.append(op)
        elif kind == 'delete_component':
            match = op.get('match')
            if not isinstance(match, dict):
                raise EdaInputError(f'{where}.match: object required')
            unknown = set(match) - DELETE_COMPONENT_MATCH_KEYS
            if unknown:
                raise EdaInputError(f'{where}.match: unknown fields {sorted(unknown)}')
            _text(match.get('primitive_id'), f'{where}.match.primitive_id')
            if match.get('component_type') not in DELETABLE_COMPONENT_TYPES:
                raise EdaInputError(
                    f'{where}.match.component_type: one of {sorted(DELETABLE_COMPONENT_TYPES)} required'
                )
            if match.get('name') is not None:
                _text(match['name'], f'{where}.match.name')
            if match.get('net') is not None:
                _text(match['net'], f'{where}.match.net')
            if match.get('at') is not None:
                _at(match['at'], f'{where}.match.at')
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
    if match.get('position') and not _same_position((part.get('x'), part.get('y')), match['position']):
        return False
    return True


def reconcile(snapshot, plan):
    """Compare the plan with a live snapshot; never guess on ambiguity."""
    parts = snapshot.get('parts') or []
    netflags = snapshot.get('netflags') or []
    netports = snapshot.get('netports') or []
    wires = snapshot.get('wires') or []
    items, actions, conflicts = [], [], []

    def conflict(item, reason, detail=None):
        item['status'] = 'conflict'
        item['reason'] = reason
        if detail is not None:
            item['detail'] = detail
        conflicts.append(item)

    for op in plan['operations']:
        key = op['key']
        item = {'key': key, 'op': op['op'], 'status': 'skip'}
        if op['op'] == 'part':
            match = op['match']
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
                    place = op.get('place') or {}
                    for field, attr in (('x', 'x'), ('y', 'y'), ('rotation', 'rotation'), ('mirror', 'mirror')):
                        if field in place:
                            current = existing.get(attr)
                            planned = place[field]
                            if field in ('x', 'y'):
                                if not _same_position((current, 0), (planned, 0), tolerance=0.01):
                                    changes[field] = planned
                            elif current != planned:
                                changes[field] = planned
                    props = op.get('properties') or {}
                    for field, value in props.items():
                        if field == 'other_property':
                            current = existing.get('other_property') or {}
                            if current != value:
                                changes[_wire_prop(field)] = value
                        elif field in PART_KEYS:
                            current = existing.get(field)
                            if current != value:
                                changes[_wire_prop(field)] = value
                    if changes:
                        prim = existing.get('primitive_id')
                        if not prim:
                            conflict(item, 'missing_primitive_id')
                        else:
                            item.update({'status': 'modify', 'changes': changes, 'primitive_id': prim,
                                         'designator': changes.get('designator', existing.get('designator'))})
                            actions.append({'action': 'modify_part', 'key': key, 'primitive_id': prim, 'changes': changes})
                    else:
                        item['status'] = 'skip'
                        item['reason'] = 'already_matches'
            else:
                place = op.get('place')
                if not place or not match.get('part'):
                    conflict(item, 'create_needs_part_and_place')
                elif not (match.get('designator') or (op.get('properties') or {}).get('designator')):
                    conflict(item, 'create_needs_stable_designator')
                else:
                    designator = (op.get('properties') or {}).get('designator') or match.get('designator')
                    post = {
                        _wire_prop(k): v
                        for k, v in (op.get('properties') or {}).items()
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
                    item.update({'status': 'create', 'designator': designator, 'part': match['part']})
                    actions.append(action)
            # Identity is only as strong as the supplied match.
            if match.get('designator') or match.get('unique_id'):
                item['stable_identity'] = True
            else:
                item['warning'] = 'identity_not_stable_without_designator_or_unique_id'
            items.append(item)
        elif op['op'] == 'net_flag':
            # Power/ground symbols are normally repeated at several pins.
            # Idempotency is per net+position, not per net.
            same_position = [f for f in netflags if f.get('name') == op['net']
                             and _same_position((f.get('x'), f.get('y')), op['at'])]
            if len(same_position) > 1:
                conflict(item, 'duplicate_net_flag_at_position', {'count': len(same_position)})
            elif same_position:
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
                             and _same_position((p.get('x'), p.get('y')), op['at'])]
            if len(same_position) > 1:
                conflict(item, 'duplicate_net_port_at_position', {'count': len(same_position)})
            elif same_position:
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
            for wire in wires:
                segments, _ = _segments_from_line(wire.get('line') or [])
                existing_by_net.setdefault(wire.get('net') or '', []).extend(segments)
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
        elif op['op'] == 'delete_wire':
            match = op['match']
            existing = next((w for w in wires if w.get('primitive_id') == match['primitive_id']), None)
            if existing is None:
                item['status'] = 'skip'
                item['reason'] = 'already_absent'
            elif existing.get('net') != match['net']:
                conflict(item, 'wire_net_mismatch', {'existing': existing.get('net'), 'planned': match['net']})
            elif match.get('points') and match['net']:
                target_segments, _ = _canonical_segments(match['points'])
                actual_segments, _ = _segments_from_line(existing.get('line') or [])
                missing = [segment for segment in target_segments
                           if not _segment_covered(segment, actual_segments)]
                if missing:
                    conflict(item, 'wire_geometry_mismatch', {'missing_segments': missing[:10]})
                else:
                    action = {'action': 'delete_wire', 'key': key,
                              'primitive_id': match['primitive_id'], 'net': match['net']}
                    item.update({'status': 'delete', 'net': match['net']})
                    actions.append(action)
            else:
                action = {'action': 'delete_wire', 'key': key,
                          'primitive_id': match['primitive_id'], 'net': match['net']}
                item.update({'status': 'delete', 'net': match['net']})
                actions.append(action)
            items.append(item)
        elif op['op'] == 'delete_component':
            match = op['match']
            flag = next((f for f in netflags if f.get('primitive_id') == match['primitive_id']), None)
            port = next((p for p in netports if p.get('primitive_id') == match['primitive_id']), None)
            existing = flag or port
            actual_type = 'netflag' if flag else ('netport' if port else None)
            if existing is None:
                item['status'] = 'skip'
                item['reason'] = 'already_absent'
            elif actual_type != match['component_type']:
                conflict(item, 'component_type_mismatch', {'existing': actual_type, 'planned': match['component_type']})
            elif match.get('name') is not None and existing.get('name') != match['name']:
                conflict(item, 'component_name_mismatch', {'existing': existing.get('name'), 'planned': match['name']})
            elif match.get('net') is not None and existing.get('net') != match['net']:
                conflict(item, 'component_net_mismatch', {'existing': existing.get('net'), 'planned': match['net']})
            elif match.get('at') is not None and not _same_position(
                    (existing.get('x'), existing.get('y')), match['at']):
                conflict(item, 'component_position_mismatch', {
                    'existing': [existing.get('x'), existing.get('y')], 'planned': match['at']})
            else:
                action = {'action': 'delete_component', 'key': key,
                          'primitive_id': match['primitive_id'], 'component_type': actual_type}
                item.update({'status': 'delete', 'component_type': actual_type})
                actions.append(action)
            items.append(item)
    return {
        'items': items,
        'actions': actions,
        'conflicts': conflicts,
        'status': 'blocked' if conflicts else ('changes' if actions else 'no_changes'),
    }


def verify_against_snapshot(snapshot, plan, items):
    """Read-back verification. It never treats a write response as proof."""
    parts = snapshot.get('parts') or []
    netflags = snapshot.get('netflags') or []
    netports = snapshot.get('netports') or []
    wires = snapshot.get('wires') or []
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
            designator = item.get('designator') or props.get('designator') or match.get('designator')
            expected_part = match.get('part')
            expected_supplier = props.get('supplier_id', match.get('supplier_id'))
            candidate = None
            if item.get('primitive_id'):
                candidate = next((p for p in parts if p.get('primitive_id') == item['primitive_id']), None)
            if candidate is None and match.get('unique_id'):
                candidate = next((p for p in parts if p.get('unique_id') == match['unique_id']), None)
            if candidate is None and designator:
                candidate = next((p for p in parts if p.get('designator') == designator), None)
            if candidate is None and match.get('position'):
                candidate = next((p for p in parts if _same_position((p.get('x'), p.get('y')), match['position'])), None)
            if candidate is None:
                detail = {'reason': 'part_not_found_after_apply'}
            else:
                detail = {'designator': candidate.get('designator'), 'part': _part_name(candidate), 'supplier_id': candidate.get('supplier_id'), 'x': candidate.get('x'), 'y': candidate.get('y'), 'rotation': candidate.get('rotation')}
                passed = True
                if expected_part and _part_name(candidate) != expected_part:
                    passed = False
                    detail['reason'] = 'part_name_mismatch'
                if expected_supplier and candidate.get('supplier_id') != expected_supplier:
                    passed = False
                    detail['reason'] = 'supplier_mismatch'
                place = op.get('place') or {}
                if 'x' in place and not _same_position((candidate.get('x'), 0), (place['x'], 0), tolerance=0.01):
                    passed = False
                    detail['reason'] = 'x_mismatch'
                if 'y' in place and not _same_position((candidate.get('y'), 0), (place['y'], 0), tolerance=0.01):
                    passed = False
                    detail['reason'] = 'y_mismatch'
                if 'rotation' in place and candidate.get('rotation') != place['rotation']:
                    passed = False
                    detail['reason'] = 'rotation_mismatch'
        elif op['op'] == 'net_flag':
            candidate = next((f for f in netflags if f.get('name') == op['net'] and _same_position((f.get('x'), f.get('y')), op['at'])), None)
            passed = candidate is not None
            detail = {'net': op['net'], 'at': op['at'], 'found': candidate is not None}
        elif op['op'] == 'net_port':
            candidate = next((p for p in netports if p.get('net') == op['net'] and _same_position((p.get('x'), p.get('y')), op['at'])), None)
            passed = candidate is not None
            detail = {'net': op['net'], 'at': op['at'], 'found': candidate is not None}
        elif op['op'] == 'wire':
            target_segments, _ = _canonical_segments(op['points'])
            actual = []
            for wire in wires:
                if wire.get('net') == op['net']:
                    segments, _ = _segments_from_line(wire.get('line') or [])
                    actual.extend(segments)
            missing = [segment for segment in target_segments
                       if not _segment_covered(segment, actual)]
            passed = not missing
            detail = {'net': op['net'], 'segments': len(target_segments),
                      'missing_segments': missing[:10], 'missing_count': len(missing)}
        elif op['op'] == 'delete_wire':
            match = op['match']
            found = next((w for w in wires if w.get('primitive_id') == match['primitive_id']), None)
            passed = found is None
            detail = {'primitive_id': match['primitive_id'], 'net': match['net'],
                      'still_present': found is not None}
        elif op['op'] == 'delete_component':
            match = op['match']
            found = next((f for f in netflags + netports
                          if f.get('primitive_id') == match['primitive_id']), None)
            passed = found is None
            detail = {'primitive_id': match['primitive_id'],
                      'component_type': match['component_type'],
                      'still_present': found is not None}
        results.append({**item, 'verification': 'verified' if passed else 'failed', 'observed': detail})
    statuses = {r['verification'] for r in results}
    if 'failed' in statuses or 'conflict' in statuses:
        status = 'partial' if any(r['verification'] == 'verified' for r in results) else 'failed'
    else:
        status = 'verified'
    return results, status


def compare_snapshots(before, after):
    """Compare stable identity/connectivity, ignoring volatile primitive IDs."""
    def parts_map(snapshot):
        result = {}
        for part in snapshot.get('parts') or []:
            key = part.get('designator') or part.get('unique_id') or part.get('primitive_id')
            if not key:
                continue
            result[key] = {
                'part': _part_name(part), 'supplier_id': part.get('supplier_id'),
                'footprint': _footprint_name(part), 'unique_id': part.get('unique_id'),
                'x': _round(part.get('x')) if part.get('x') is not None else None,
                'y': _round(part.get('y')) if part.get('y') is not None else None,
                'rotation': part.get('rotation'),
            }
        return result

    def wires_set(snapshot):
        # Compare the electrical graph by normalized net+collinear segment,
        # not by editor object or by how the editor split a wire.
        return sorted(_normalized_wire_net(snapshot), key=repr)

    def flags_set(snapshot):
        return sorted((f.get('name'), _round(f.get('x')), _round(f.get('y'))) for f in (snapshot.get('netflags') or []))

    def ports_set(snapshot):
        return sorted((p.get('net'), _round(p.get('x')), _round(p.get('y')))
                      for p in (snapshot.get('netports') or []))

    bparts, aparts = parts_map(before), parts_map(after)
    bwires, awires = wires_set(before), wires_set(after)
    bflags, aflags = flags_set(before), flags_set(after)
    bports, aports = ports_set(before), ports_set(after)
    differences = []
    for key in sorted(set(bparts) | set(aparts)):
        if bparts.get(key) != aparts.get(key):
            differences.append({'kind': 'part', 'key': key, 'before': bparts.get(key), 'after': aparts.get(key)})
    if bwires != awires:
        differences.append({'kind': 'wires', 'before_count': len(bwires), 'after_count': len(awires),
                            'missing': [x for x in bwires if x not in awires][:10],
                            'added': [x for x in awires if x not in bwires][:10]})
    if bflags != aflags:
        differences.append({'kind': 'netflags', 'before': bflags, 'after': aflags})
    if bports != aports:
        differences.append({'kind': 'netports', 'before': bports, 'after': aports})
    return {'match': not differences, 'differences': differences,
            'counts': {'parts_before': len(bparts), 'parts_after': len(aparts),
                       'wires_before': len(bwires), 'wires_after': len(awires),
                       'netflags_before': len(bflags), 'netflags_after': len(aflags),
                       'netports_before': len(bports), 'netports_after': len(aports)}}


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

def _page_args(args):
    result = {}
    for name in ('page_uuid', 'schematic_name', 'page_name'):
        if getattr(args, name, None):
            result[name] = getattr(args, name)
    return result


def read_snapshot(pro, session, page_args, include_attributes=False, include_pins=True):
    args = {**page_args, 'include_attributes': include_attributes, 'include_pins': include_pins}
    value = pro.invoke(session, SNAPSHOT_JS, args)
    if not isinstance(value, dict) or value.get('ok') is False:
        raise EdaCommandError('snapshot failed', 'EDA_SNAPSHOT_FAILED', {'value': value})
    return value


def read_with_retry(pro, session, page_args, attempts=3):
    last = None
    for attempt in range(attempts):
        try:
            snapshot = read_snapshot(pro, session, page_args)
            if snapshot.get('selection', {}).get('page_uuid'):
                return snapshot
            last = snapshot
        except EdaError as error:
            last = {'error': str(error), 'code': error.code}
        if attempt + 1 < attempts:
            import time
            time.sleep(1.0 + attempt)
    raise EdaCommandError('project/page not readable after retries', 'EDA_PROJECT_NOT_READY', {'last': last})


def session_origin(pro, session):
    for entry in pro.sessions():
        if entry.get('sessionId') == session:
            return entry
    return None


def close_owned(pro, session, force=False):
    entry = session_origin(pro, session)
    if entry is None:
        return {'closed': False, 'reason': 'session_not_found_or_already_closed'}
    if entry.get('origin') == 'user' and not force:
        raise EdaInputError('refusing to close a session opened by the user; close it yourself or pass --force')
    return {'closed': True, 'session': pro.close_session(session)}


def _open_for_command(pro, args):
    """Return (session, owned). Existing sessions are never closed implicitly."""
    if getattr(args, 'session', None):
        return args.session, False
    project = getattr(args, 'project', None)
    if not project:
        raise EdaInputError('--session or --project is required')
    return pro.open_project(project, headless=True), True


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
            'sch_drc': 'not_implemented_in_this_adapter',
            'pcb_read_write': 'not_implemented_in_this_adapter',
            'net_label_idempotent_apply': 'not_implemented',
            'source': 'lceda-pro 4.1.78 doc api + live probe 2026-10-21',
        },
        'warnings': [],
        'not_checked': ['PCB', 'factory DFM', 'orders', 'realtime LCSC stock/price'],
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
        result['sessions'] = pro.sessions()
        if not result['checks']['tool_connected']:
            result['status'] = 'disconnected'
            result['warnings'].append('client is installed but the endpoint is not connected; start JLCEDA Pro')
            return result, EXIT_UNAVAILABLE
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
    session, owned = _open_for_command(pro, args)
    try:
        snapshot = read_with_retry(pro, session, _page_args(args))
        output_path = None
        if args.output:
            Path(args.output).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
            snapshot['output'] = str(Path(args.output).resolve())
            output_path = snapshot['output']
        return {'status': 'ok', 'snapshot': snapshot, 'output': output_path}, EXIT_OK
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
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned = _open_for_command(pro, args)
    page_args = {k: v for k, v in plan['page'].items() if k in ('page_uuid', 'schematic_name', 'page_name')}
    try:
        before = read_with_retry(pro, session, page_args)
        reconciliation = reconcile(before, plan)
        result = {
            'status': reconciliation['status'],
            'plan': args.plan,
            'page': before.get('selection'),
            'before_counts': before.get('counts'),
            'items': reconciliation['items'],
            'actions': reconciliation['actions'],
            'conflicts': reconciliation['conflicts'],
            'dry_run': bool(args.dry_run),
        }
        if args.dry_run:
            result['status'] = 'dry_run'
            result['note'] = 'no write was sent'
            return result, EXIT_OK if not reconciliation['conflicts'] else EXIT_REVIEW
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
        execution = pro.invoke(session, APPLY_JS, {'page': page_args, 'actions': reconciliation['actions']}, timeout_ms=args.invoke_timeout)
        result['execution'] = execution
        if not isinstance(execution, dict) or execution.get('ok') is False:
            result['status'] = 'preflight_failed'
            result['note'] = 'no write was sent because one or more parts could not be resolved'
            return result, EXIT_REVIEW
        import time
        time.sleep(1.0)
        after = read_with_retry(pro, session, page_args)
        verified_items, verification_status = verify_against_snapshot(after, plan, reconciliation['items'])
        result['after_counts'] = after.get('counts')
        result['verification'] = {'status': verification_status, 'items': verified_items}
        result['status'] = verification_status
        if args.save:
            if verification_status == 'verified':
                result['save'] = pro.invoke(session, SAVE_JS, {'page': page_args})
                result['saved_readback'] = read_with_retry(pro, session, page_args).get('counts')
                if not result['save'].get('saved'):
                    result['status'] = 'save_failed'
                    result['note'] = 'plan verified in memory, but the editor did not confirm save; do not report persistence'
            else:
                result['save'] = {'not_attempted': 'verification did not pass; inspect before saving'}
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            result['output'] = str(Path(args.output).resolve())
        return result, EXIT_OK if verification_status == 'verified' and (not args.save or result['save'].get('saved')) else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def command_save(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned = _open_for_command(pro, args)
    try:
        outcome = pro.invoke(session, SAVE_JS, {'page': _page_args(args)})
        return {'status': 'ok' if outcome.get('saved') else 'save_failed', 'save': outcome}, EXIT_OK if outcome.get('saved') else EXIT_REVIEW
    finally:
        if owned:
            close_owned(pro, session)


def command_export(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned = _open_for_command(pro, args)
    try:
        payload = {'kind': args.kind, 'name': args.name,
                   'netlist_type': args.netlist_type, 'bom_type': args.bom_type}
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
        return {'status': 'ok', 'export': value, 'output': value['output']}, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def command_drc(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    session, owned = _open_for_command(pro, args)
    try:
        payload = {'page': _page_args(args)}
        value = pro.invoke(session, DRC_JS, payload, timeout_ms=args.invoke_timeout)
        if not isinstance(value, dict) or value.get('ok') is False:
            raise EdaCommandError('schematic DRC failed', 'EDA_DRC_FAILED', {'value': value})
        return {'status': 'ok', 'drc': value}, EXIT_OK
    finally:
        if owned:
            close_owned(pro, session)


def command_reopen_check(args):
    expected = json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    closed = None
    if args.session:
        closed = close_owned(pro, args.session, force=args.force_close)
    session = pro.open_project(args.project, headless=True)
    try:
        actual = read_with_retry(pro, session, _page_args(args))
        comparison = compare_snapshots(expected, actual)
        result = {
            'status': 'match' if comparison['match'] else 'mismatch',
            'project': str(Path(args.project).resolve()),
            'snapshot': str(Path(args.snapshot).resolve()),
            'closed_session': closed,
            'comparison': comparison,
            'actual_counts': actual.get('counts'),
        }
        return result, EXIT_OK if comparison['match'] else EXIT_REVIEW
    finally:
        close_owned(pro, session)


def command_close(args):
    pro = LcedaPro(args.exe, timeout_ms=args.timeout)
    result = close_owned(pro, args.session, force=args.force)
    return {'status': 'closed', **result}, EXIT_OK


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
    read.set_defaults(func=command_read)

    apply_cmd = sub.add_parser('apply', help='reconcile and apply a constrained plan, then read back')
    apply_cmd.add_argument('--session')
    apply_cmd.add_argument('--project')
    apply_cmd.add_argument('--plan', required=True)
    apply_cmd.add_argument('--save', action='store_true', help='save after successful verification')
    apply_cmd.add_argument('--dry-run', action='store_true', help='reconcile only; write nothing')
    apply_cmd.add_argument('--allow-partial', action='store_true', help='execute non-conflicting actions')
    apply_cmd.add_argument('--invoke-timeout', type=int, default=180000)
    apply_cmd.add_argument('--output')
    apply_cmd.set_defaults(func=command_apply)

    save = sub.add_parser('save', help='save the current document and read counts back')
    save.add_argument('--session')
    save.add_argument('--project')
    save.add_argument('--page', dest='page_uuid')
    save.add_argument('--schematic', dest='schematic_name')
    save.add_argument('--page-name', dest='page_name')
    save.set_defaults(func=command_save)

    export = sub.add_parser('export', help='export PNG/netlist/SVG from the current page')
    export.add_argument('--session')
    export.add_argument('--project')
    export.add_argument('--kind', required=True, choices=['png', 'netlist', 'svg', 'bom'])
    export.add_argument('--output', required=True)
    export.add_argument('--name', default='eda-export')
    export.add_argument('--width', type=int)
    export.add_argument('--height', type=int)
    export.add_argument('--netlist-type', default='Protel2')
    export.add_argument('--bom-type', default='csv', choices=['csv', 'xlsx'])
    export.add_argument('--page', dest='page_uuid')
    export.add_argument('--schematic', dest='schematic_name')
    export.add_argument('--page-name', dest='page_name')
    export.set_defaults(func=command_export)

    drc = sub.add_parser('drc', help='run the editor schematic DRC on the current page')
    drc.add_argument('--session')
    drc.add_argument('--project')
    drc.add_argument('--page', dest='page_uuid')
    drc.add_argument('--schematic', dest='schematic_name')
    drc.add_argument('--page-name', dest='page_name')
    drc.add_argument('--invoke-timeout', type=int, default=180000)
    drc.set_defaults(func=command_drc)

    reopen = sub.add_parser('reopen-check', help='close, reopen and compare stable identity/connectivity')
    reopen.add_argument('--project', required=True)
    reopen.add_argument('--snapshot', required=True)
    reopen.add_argument('--session', help='owned session to close first')
    reopen.add_argument('--force-close', action='store_true')
    reopen.add_argument('--page', dest='page_uuid')
    reopen.add_argument('--schematic', dest='schematic_name')
    reopen.add_argument('--page-name', dest='page_name')
    reopen.set_defaults(func=command_reopen_check)

    close = sub.add_parser('close', help='close a session; refuses user sessions unless --force')
    close.add_argument('--session', required=True)
    close.add_argument('--force', action='store_true')
    close.set_defaults(func=command_close)
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
