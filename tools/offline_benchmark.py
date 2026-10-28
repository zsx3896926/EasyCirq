#!/usr/bin/env python3
"""One-command frozen offline benchmark (no EDA, no network).

Usage:
  python tools/offline_benchmark.py --out benchmarks/offline-round11/result.json
  python tools/offline_benchmark.py --runs 3

Correctness is checked against ``benchmarks/offline-round11/expected.json``.
The expected values are derived from the frozen prior output, the v14 README
residuals and hand-checked geometry — not from the current run.  Timing is
reported with input size, environment and the statistic used; no cross-version
speed percentage is claimed.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import platform
import statistics
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
BENCH = ROOT / 'benchmarks' / 'offline-round11'
sys.path.insert(0, str(SCRIPTS))

os.environ['HDS_OFFLINE'] = '1'

import offline_guard  # noqa: E402
import pcb_apply_plan  # noqa: E402
import pcb_cli  # noqa: E402
import pcb_evidence  # noqa: E402
import pcb_gate  # noqa: E402
import sch_visual_audit  # noqa: E402
from design_engine.geometry import (circle_inside_polygon, point_in_polygon,
                                    polyline_inside_polygon,
                                    rect_inside_polygon)  # noqa: E402
from design_engine.pcb_workflow import (compile_constraints, load_templates,
                                        normalize_board, plan_candidates)  # noqa: E402
from design_engine import placement as placement_engine  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures'
PHOTO_CASE = ROOT / 'easycirq' / 'cases' / 'photo-led-pcb-2026-10-26'
PHOTO_EVIDENCE = PHOTO_CASE / 'evidence'
PHOTO_DUMP = FIXTURES / 'photo-led-pcb-board.json'
PHOTO_INTENT = FIXTURES / 'photo-led-pcb-intent.json'
PHOTO_PLAN = FIXTURES / 'photo-led-placement-plan.json'
PHOTO_CONSTRAINTS = FIXTURES / 'photo-led-pcb-constraints.json'
V14_LAYOUT = FIXTURES / 'photo-led-v14' / 'layout.json'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def gate_args(case):
    return SimpleNamespace(
        case=str(case), profile='regression', baseline_manifest=None,
        key_nets=None, warn_disposition=None, dump_before=None,
        dump_after=None, constraints=None, plan=None, intent=None,
        check=None, drc=None, lint=None, netpath=None, sch_pcb=None,
        sch=None, pin_aliases=None, ignore_designators=None, images=None,
        edit_scope=None, file=[], role=[], out=None, json=False,
        strict_advisory=False,
    )


def result(name, passed, details, inputs):
    return {'case': name, 'passed': bool(passed), 'details': details,
            'input_bytes': sum(int(item.get('bytes', 0)) for item in inputs),
            'inputs': inputs}


def _sha256_normalized(path):
    data = Path(path).read_bytes()
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return hashlib.sha256(data).hexdigest()
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def check_sources(expected):
    rows, passed = [], True
    for name, item in sorted((expected.get('sources') or {}).items()):
        path = ROOT / item['path']
        actual = sha256(path) if path.is_file() else None
        normalized = _sha256_normalized(path) if path.is_file() else None
        ok = actual == item.get('sha256') or \
            normalized == item.get('sha256')
        basis = ('raw' if actual == item.get('sha256') else
                 ('crlf_normalized' if ok else 'mismatch'))
        passed = passed and ok
        rows.append({'name': name, 'path': item['path'],
                     'expected': item.get('sha256'), 'actual': actual,
                     'normalized': normalized, 'hash_basis': basis,
                     'status': 'match' if ok else 'changed_or_missing'})
    inputs = [{'path': item['path'], 'bytes': path.stat().st_size}
              for item in (expected.get('sources') or {}).values()
              for path in [ROOT / item['path']] if path.is_file()]
    return result('source_hashes', passed, {'sources': rows}, inputs)


def check_gate(expected):
    # Run the gate on a fresh case containing ONLY the frozen inputs.  This
    # prevents an extra "passing" file in the source evidence directory from
    # being selected while the 46 listed files stay unchanged.
    frozen_prefix = str(PHOTO_EVIDENCE.relative_to(ROOT)).replace('\\', '/') + '/'
    frozen = [(name, item) for name, item in
              (expected.get('sources') or {}).items()
              if item['path'].replace('\\', '/').startswith(frozen_prefix)]
    temp = tempfile.mkdtemp(prefix='hds-bench-gate-')
    case_dir = Path(temp) / 'case'
    evidence_dir = case_dir / 'evidence'
    evidence_dir.mkdir(parents=True)
    for _name, item in frozen:
        source = ROOT / item['path']
        target = evidence_dir / Path(item['path']).name
        shutil.copyfile(str(source), str(target))
    try:
        report = pcb_gate.evaluate(gate_args(case_dir))
        stages = {stage['id']: stage['status'] for stage in report['stages']}
        expected_stages = expected['gate_photo_regression']['stages']
        passed = (report['status'] ==
                  expected['gate_photo_regression']['status'] and
                  stages == expected_stages)
        inputs = [{'path': str((ROOT / item['path']).relative_to(ROOT)),
                   'bytes': (ROOT / item['path']).stat().st_size}
                  for _name, item in frozen]
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return result('gate_photo_regression', passed,
                  {'status': report['status'], 'stages': stages,
                   'frozen_inputs': len(frozen)},
                  inputs)


def check_sch_visual(expected):
    layout = load(V14_LAYOUT)
    report = sch_visual_audit.audit(layout)
    blocking = {}
    info = {}
    for row in report['findings']:
        bucket = info if row['severity'] == 'info' else blocking
        bucket[row['code']] = bucket.get(row['code'], 0) + 1
    want = expected['sch_visual_photo']
    blocking_objects = [sorted(row['objects']) for row in report['findings']
                        if row['severity'] != 'info']
    expected_objects = [sorted(item) for item in
                        want.get('blocking_objects') or []]
    passed = (report['status'] == want['status'] and
              report['blocking_count'] == want['blocking_count'] and
              report['informational_count'] == want['informational_count'] and
              blocking == want['blocking_codes'] and
              info == want['info_codes'] and
              blocking_objects == expected_objects and
              report['font_measurement']['source'] == want['font_source'])
    return result('sch_visual_photo', passed,
                  {'status': report['status'], 'blocking': blocking,
                   'info': info, 'font': report['font_measurement']['source']},
                  [{'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size}
                   for path in (V14_LAYOUT,)])


def candidate_snapshot(result_doc):
    return {
        'status': result_doc['status'],
        'selected': result_doc.get('selected'),
        'hard_ok': {item['id']: item['hard_ok']
                    for item in result_doc['comparison']},
        'hpwl_mil': {item['id']: item['hpwl_mil']
                     for item in result_doc['comparison']},
        'module_area_mil2': (result_doc['candidates'][0]['module_area_mil2']
                             if result_doc.get('candidates') else None),
    }


def compare_hpwl(actual, expected, tolerance):
    keys = set(expected or {})
    if set(actual or {}) != keys:
        return False
    return all(abs(float(actual[key]) - float(expected[key])) <= tolerance
               for key in keys)


def check_candidates(expected):
    dump = load(PHOTO_DUMP)
    board = normalize_board(dump)
    intent = load(PHOTO_INTENT)
    constraints = compile_constraints(intent, board)
    report = plan_candidates(board, intent, load_templates(), constraints)
    snapshot = candidate_snapshot(report)
    want = expected['candidates_photo_full']
    passed = (snapshot['status'] == want['status'] and
              snapshot['selected'] == want['selected'] and
              snapshot['hard_ok'] == want['hard_ok'] and
              compare_hpwl(snapshot['hpwl_mil'], want['hpwl_mil'],
                           want['tolerance']) and
              abs(snapshot['module_area_mil2'] -
                  want['module_area_mil2']) <= want['tolerance'])
    return result('candidates_photo_full', passed,
                  {'actual': snapshot, 'expected_selected': want['selected']},
                  [{'path': str(PHOTO_DUMP.relative_to(ROOT)),
                    'bytes': PHOTO_DUMP.stat().st_size},
                   {'path': str(PHOTO_INTENT.relative_to(ROOT)),
                    'bytes': PHOTO_INTENT.stat().st_size},
                   {'path': 'easycirq/assets/pcb-placement-templates.json',
                    'bytes': (ROOT / 'easycirq/assets/pcb-placement-templates.json').stat().st_size}])


def check_structures(expected):
    dump = load(PHOTO_DUMP)
    board = normalize_board(dump)
    full_intent = load(PHOTO_INTENT)
    templates = load_templates()
    rows, passed_all = {}, True
    by_id = {item['id']: item for item in full_intent['modules']}
    for module_id in ('power-input', 'driver'):
        intent = copy.deepcopy(full_intent)
        intent['modules'] = [copy.deepcopy(by_id[module_id])]
        constraints = compile_constraints(intent, board)
        report = plan_candidates(board, intent, templates, constraints)
        snapshot = candidate_snapshot(report)
        want = expected['candidates_structures'][module_id]
        ok = (snapshot['selected'] == want['selected'] and
              snapshot['hard_ok'] == want['hard_ok'])
        if want.get('hpwl_mil'):
            ok = ok and compare_hpwl(snapshot['hpwl_mil'], want['hpwl_mil'],
                                     want.get('tolerance', 0.02))
        passed_all = passed_all and ok
        rows[module_id] = {'passed': ok, 'actual': snapshot, 'expected': want}
    ldo_board = load(BENCH / 'cases' / 'ldo-caps-board.json')
    ldo_intent = load(BENCH / 'cases' / 'ldo-caps-intent.json')
    board_ir = normalize_board(ldo_board)
    constraints = compile_constraints(ldo_intent, board_ir)
    report = plan_candidates(board_ir, ldo_intent, templates, constraints)
    snapshot = candidate_snapshot(report)
    want = expected['candidates_structures']['ldo-power']
    ok = (snapshot['selected'] == want['selected'] and
          snapshot['hard_ok'] == want['hard_ok'] and
          compare_hpwl(snapshot['hpwl_mil'],
                       {key: want['hpwl_mil'] for key in snapshot['hpwl_mil']},
                       0.02))
    passed_all = passed_all and ok
    rows['ldo-power'] = {'passed': ok, 'actual': snapshot, 'expected': want}
    inputs = [{'path': str(PHOTO_DUMP.relative_to(ROOT)),
               'bytes': PHOTO_DUMP.stat().st_size},
              {'path': str(PHOTO_INTENT.relative_to(ROOT)),
               'bytes': PHOTO_INTENT.stat().st_size},
              {'path': str((BENCH / 'cases' / 'ldo-caps-board.json')
                           .relative_to(ROOT)),
               'bytes': (BENCH / 'cases' / 'ldo-caps-board.json').stat().st_size},
              {'path': str((BENCH / 'cases' / 'ldo-caps-intent.json')
                           .relative_to(ROOT)),
               'bytes': (BENCH / 'cases' / 'ldo-caps-intent.json').stat().st_size},
              {'path': 'easycirq/assets/pcb-placement-templates.json',
               'bytes': (ROOT / 'easycirq/assets/pcb-placement-templates.json').stat().st_size}]
    return result('candidates_structures', passed_all,
                  {'structures': rows}, inputs)


def check_apply_noop(expected):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('offline benchmark must not run EDA')

    original = pcb_cli.run
    pcb_cli.run = forbidden
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            code = pcb_apply_plan.main([
                '--dump', str(PHOTO_DUMP), '--plan', str(PHOTO_PLAN),
                '--constraints', str(PHOTO_CONSTRAINTS),
                '--project', 'photo-led-pcb-20261026', '--doc', 'PCB1',
                '--out-dump', str(BENCH / '.noop-out.json'),
                '--report', str(BENCH / '.noop-report.json'),
            ])
        report = load(BENCH / '.noop-report.json')
    finally:
        pcb_cli.run = original
    want = expected['apply_noop']
    passed = (code == 0 and report['status'] == want['status'] and
              len(calls) == want['cli_calls'])
    for path in (BENCH / '.noop-out.json', BENCH / '.noop-report.json'):
        if path.exists():
            path.unlink()
    return result('apply_noop', passed,
                  {'status': report['status'], 'cli_calls': len(calls)},
                  [{'path': str(PHOTO_PLAN.relative_to(ROOT)),
                    'bytes': PHOTO_PLAN.stat().st_size},
                   {'path': str(PHOTO_DUMP.relative_to(ROOT)),
                    'bytes': PHOTO_DUMP.stat().st_size},
                   {'path': str(PHOTO_CONSTRAINTS.relative_to(ROOT)),
                    'bytes': PHOTO_CONSTRAINTS.stat().st_size}])


def check_placement_constraint_gain(expected):
    reference = {
        'outline': {
            'bbox': [0, 0, 2000, 1000],
            'points': [[0, 0], [2000, 0], [2000, 1000], [0, 1000]],
        },
        'components': [{
            'id': 'pcbpart:U1', 'designator': 'U1',
            'bbox': [100, 100, 300, 300],
            'placement': {'x': 200, 'y': 200, 'rotation': 0, 'layer': 1},
            'pads': [],
        }],
    }
    candidate = copy.deepcopy(reference['components'][0])
    constraints = {'constraints': [{
        'id': 'K1', 'type': 'keepout', 'severity': 'hard',
        'shape': 'rect', 'rect': [150, 150, 250, 250],
    }]}
    polygon = [tuple(item) for item in reference['outline']['points']]
    new_ok, problems, conflicts = placement_engine._hard_ok(
        {'components': [candidate]}, reference['outline']['bbox'],
        reference, polygon=polygon, constraints=constraints)
    # The pre-change check used only bbox containment and body overlap.
    legacy_ok = (reference['outline']['bbox'][0] <= candidate['bbox'][0]
                 and candidate['bbox'][2] <= reference['outline']['bbox'][2]
                 and reference['outline']['bbox'][1] <= candidate['bbox'][1]
                 and candidate['bbox'][3] <= reference['outline']['bbox'][3])
    want = expected['placement_constraint_gain']
    passed = (legacy_ok is want['legacy_hard_ok'] and
              new_ok is want['new_hard_ok'] and
              any(item.get('kind') == want['new_conflict_kind']
                  for item in conflicts))
    inline_bytes = len(json.dumps({'reference': reference,
                                   'candidate': candidate,
                                   'constraints': constraints}).encode('utf-8'))
    return result('placement_constraint_gain', passed,
                  {'legacy_hard_ok': legacy_ok, 'new_hard_ok': new_ok,
                   'conflicts': [item.get('kind') for item in conflicts]},
                  [{'path': 'inline:keepout-boundary', 'bytes': inline_bytes}])


def check_holdout_geometry(expected):
    case = load(BENCH / 'cases' / 'holdout-concave-keepout.json')
    board = normalize_board(case['board'])
    ops = []
    for index, raw in enumerate(case['ops']):
        ops.append({
            'op': raw['op'], 'index': index, 'net': raw['net'],
            'layer': raw['layer'], 'width_mil': raw['width_mil'],
            'points': [tuple(point) for point in raw['points']],
        })
    problems = pcb_apply_plan.validate_copper_geometry(
        ops, board, case['board'])
    refused = sorted({item.get('index') for item in problems
                      if item.get('index') is not None})
    want = case['expected']
    passed = (refused == want['refused_op_indexes'] and
              not any(item.get('index') == 1 for item in problems))
    path = BENCH / 'cases' / 'holdout-concave-keepout.json'
    return result('holdout_geometry', passed,
                  {'refused_indexes': refused, 'problems': problems,
                   'expected': want},
                  [{'path': str(path.relative_to(ROOT)),
                    'bytes': path.stat().st_size}])


def check_deformations(expected):
    sch = load(PHOTO_CASE / 'evidence' / 'sch-read.json')
    dump = load(PHOTO_CASE / 'evidence' / 'pcb-dump-final.json')
    base = pcb_evidence.compare_sch_pcb(sch, dump)
    shuffled_sch = copy.deepcopy(sch)
    shuffled_dump = copy.deepcopy(dump)
    if isinstance(shuffled_sch.get('components'), list):
        shuffled_sch['components'] = list(reversed(shuffled_sch['components']))
        for component in shuffled_sch['components']:
            if isinstance(component.get('pins'), list):
                component['pins'] = list(reversed(component['pins']))
    if isinstance(shuffled_dump.get('components'), list):
        shuffled_dump['components'] = list(reversed(shuffled_dump['components']))
        for component in shuffled_dump['components']:
            if isinstance(component.get('pads'), list):
                component['pads'] = list(reversed(component['pads']))
                for pad in component['pads']:
                    if type(pad.get('x')) in (int, float):
                        pad['x'] += 1000
                    if type(pad.get('y')) in (int, float):
                        pad['y'] += 1000
    for component in shuffled_sch.get('components') or []:
        for pin in component.get('pins') or []:
            if type(pin.get('x')) in (int, float):
                pin['x'] += 1000
            if type(pin.get('y')) in (int, float):
                pin['y'] += 1000
    shuffled = pcb_evidence.compare_sch_pcb(shuffled_sch, shuffled_dump)

    short_dump = copy.deepcopy(dump)
    changed = False
    for component in short_dump.get('components') or []:
        pads = component.get('pads') or []
        if len(pads) >= 2 and pads[0].get('net') != pads[1].get('net'):
            pads[1]['net'] = pads[0].get('net')
            changed = True
            break
    short = pcb_evidence.compare_sch_pcb(sch, short_dump)
    want = expected['deformations']
    passed = (base['status'] == 'match' and
              base['status'] == shuffled['status'] and
              want['shuffle_and_translate_semantics'] == 'same' and
              changed and short['status'] == want['pcb_short_must_be_detected'])
    inputs = [{'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size}
              for path in (PHOTO_CASE / 'evidence' / 'sch-read.json',
                           PHOTO_CASE / 'evidence' / 'pcb-dump-final.json')]
    return result('deformations', passed,
                  {'base': base['status'], 'shuffled': shuffled['status'],
                   'short': short['status'], 'short_changed': changed}, inputs)


CASES = (
    ('source_hashes', check_sources),
    ('gate_photo_regression', check_gate),
    ('sch_visual_photo', check_sch_visual),
    ('candidates_photo_full', check_candidates),
    ('candidates_structures', check_structures),
    ('apply_noop', check_apply_noop),
    ('placement_constraint_gain', check_placement_constraint_gain),
    ('holdout_geometry', check_holdout_geometry),
    ('deformations', check_deformations),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--expected', default=str(BENCH / 'expected.json'))
    parser.add_argument('--out', help='write the benchmark result JSON')
    parser.add_argument('--runs', type=int, default=1,
                        help='repeat each case and report min/median time')
    args = parser.parse_args(argv)
    if args.runs < 1:
        print('error: --runs must be >= 1', file=sys.stderr)
        return 2
    expected = load(args.expected)
    audit_path = os.path.join(tempfile.mkdtemp(prefix='hds-bench-audit-'),
                              'audit.jsonl')
    os.environ['HDS_OFFLINE_AUDIT'] = audit_path
    guard = offline_guard.Guard().install(block_network=True)
    rows = []
    try:
        for name, function in CASES:
            timings = []
            last = None
            for _ in range(args.runs):
                started = time.perf_counter()
                last = function(expected)
                timings.append(time.perf_counter() - started)
            last['timing'] = {
                'runs': args.runs,
                'min_sec': round(min(timings), 6),
                'median_sec': round(statistics.median(timings), 6),
                'max_sec': round(max(timings), 6),
            }
            rows.append(last)
    finally:
        guard.restore()
    audit_events = []
    try:
        for line in Path(audit_path).read_text(encoding='utf-8').splitlines():
            if line.strip():
                audit_events.append(json.loads(line))
    except (OSError, ValueError):
        pass
    real_eda_attempts = [
        item for item in audit_events
        if 'zhigou' in json.dumps(item, ensure_ascii=False).lower() or
        'lceda-pro' in json.dumps(item, ensure_ascii=False).lower()
    ]
    shutil.rmtree(os.path.dirname(audit_path), ignore_errors=True)
    passed = sum(1 for row in rows if row['passed'])
    if real_eda_attempts:
        passed = 0
    report = {
        'schema': 'design-engine-offline-benchmark/v1',
        'simulated': True,
        'eda_calls': len(real_eda_attempts),
        'status': 'pass' if passed == len(rows) else 'fail',
        'correctness': {'passed': passed, 'total': len(rows)},
        'coverage': {
            'cases': [row['case'] for row in rows],
            'source_classes': ['real frozen EDA evidence', 'real v14 layout',
                               'synthetic boundary case', 'frozen prior output'],
            'deformations': expected['deformations'],
        },
        'timing': {
            'runs': args.runs,
            'statistic': 'min/median/max of each case; no cross-version speed '
                         'claim',
            'environment': {
                'python': sys.version.split()[0],
                'platform': platform.platform(),
                'machine': platform.machine(),
            },
        },
        'cases': rows,
        'not_covered': [
            'real EDA CLI/daemon/connector (0 calls by contract)',
            'native DRC/check/layout-lint on a live project',
            'Gerber/CPL/drill export and board-house DFM',
            'actual routing completion, impedance, EMC, thermal and firmware',
            'image byte-level regression and visual sign-off',
            'font rendering on a machine without the measured-font environment',
        ],
        'note': 'offline correctness/timing only; no hardware or EDA acceptance',
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(encoded + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'],
                      'correctness': report['correctness'],
                      'out': str(args.out) if args.out else None},
                     ensure_ascii=False))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
