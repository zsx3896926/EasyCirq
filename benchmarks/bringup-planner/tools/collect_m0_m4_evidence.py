"""Collect M0-M4 evidence for the merged bringup-planner task (offline).

Run from any directory; the repository is derived from this file's location:

    python benchmarks/bringup-planner/tools/collect_m0_m4_evidence.py

Outputs a machine-readable JSON to ``$BP_EVIDENCE_OUT`` (or a temp path).
No instrument, no power-on, no flashing, no UART/JTAG, no EDA, no network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parents[3]
SCRIPTS = W / 'easycirq' / 'scripts'
TMP = Path(tempfile.mkdtemp(prefix='bp-m-evidence-'))
ENV = dict(os.environ)
ENV['PYTHONPATH'] = str(SCRIPTS)
PR_BASE = '9a951edc21481dc3ae91460acc11aa3e08a7be8a'
MERGED_HEAD = 'b407d72f11237001d7c7e1260beb8de770f46f1e'
rows = []


def run(name, command, cwd=W, *, env=None, timeout=1200):
    result = subprocess.run(command, cwd=str(cwd), env=env or ENV,
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout)
    rows.append({'name': name, 'command': command,
                 'exit_code': result.returncode,
                 'stdout': result.stdout[-12000:],
                 'stderr': result.stderr[-4000:]})
    return result


def cli(name, args):
    return run(name, [sys.executable, '-m', 'bringup_planner'] + args, SCRIPTS)


def payload(result):
    start = result.stdout.find('{')
    return json.loads(result.stdout[start:]) if start >= 0 else {}


def sanitise(value):
    if isinstance(value, str):
        return value.replace(str(W), '<worktree>')
    if isinstance(value, dict):
        return {key: sanitise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitise(item) for item in value]
    return value


# ---- M0 identity / isolation / merged PR --------------------------------
run('M0.head', ['git', 'rev-parse', 'HEAD'])
run('M0.branch', ['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
run('M0.start_base', ['git', 'rev-parse', PR_BASE])
run('M0.status', ['git', 'status', '--short'])
run('M0.worktrees', ['git', 'worktree', 'list'])
r = run('M0.pr_range_diff',
        ['git', 'diff', '--name-only', PR_BASE + '...' + MERGED_HEAD])
pr_files = [line for line in r.stdout.splitlines() if line.strip()]
run('M0.main_has_docs',
    ['git', 'cat-file', '-e',
     'HEAD:docs/parallel-bringup-planner/acceptance-matrix.md'])
run('M0.main_has_scripts',
    ['git', 'cat-file', '-e',
     'HEAD:easycirq/scripts/bringup_planner/plan.py'])
r = run('M0.pr_state', ['gh', 'pr', 'view', '39', '--json',
                        'number,state,isDraft,mergedAt,mergedBy,mergeCommit,'
                        'headRefOid,baseRefName,url,changedFiles,additions,'
                        'deletions'])
pr = json.loads(r.stdout) if r.returncode == 0 else {}
r = run('M0.origin_main', ['git', 'rev-parse', 'origin/main'])

# ---- M1 validate / plan / combination boards ----------------------------
fixture = W / 'tests' / 'bringup_planner_tests' / 'fixtures' / 'minimal-input.json'
r = cli('M1.validate', ['validate', '--input', str(fixture), '--json'])
m1_validate = payload(r)
out = TMP / 'm1-plan'
r = cli('M1.plan', ['plan', '--input', str(fixture), '--out', str(out), '--json'])
m1_plan = payload(r)
m1_doc = json.loads((out / 'plan.json').read_text(encoding='utf-8'))

cases = {}
for case in ('mcu-sensor-board', 'load-control-board'):
    src = W / 'benchmarks' / 'bringup-planner' / 'cases' / case / 'input.json'
    case_out = TMP / ('case-' + case)
    r = cli('M1.plan.' + case,
            ['plan', '--input', str(src), '--out', str(case_out), '--json'])
    p = payload(r)
    d = json.loads((case_out / 'plan.json').read_text(encoding='utf-8'))
    cases[case] = {'exit': r.returncode, 'scope': p.get('scope'),
                   'steps': p.get('steps'), 'ready': p.get('ready'),
                   'blocked': p.get('blocked'),
                   'plan_sha256': p.get('plan_sha256'),
                   'fault_trees': len(d.get('fault_trees') or [])}
r = cli('M1.explain',
        ['explain', '--input', str(fixture), '--step', 'I2-SEQ-VIN_5V',
         '--json'])
m1_explain = payload(r)

# ---- M2 I1-I6 behaviours -------------------------------------------------
scen = W / 'benchmarks' / 'bringup-planner' / 'scenarios'
eval_rows = {}
for name in ('eval-pass-real-evidence', 'eval-stop-propagation',
             'eval-stale-revision', 'eval-unit-conflict',
             'eval-missing-evidence', 'eval-partial-tests',
             'eval-synthetic-only'):
    eval_out = TMP / ('eval-' + name)
    r = cli('M2.evaluate.' + name,
            ['evaluate', '--plan', str(scen / name / 'plan.json'),
             '--results', str(scen / name / 'results.json'),
             '--evidence-root', str(scen / name / 'evidence'),
             '--out', str(eval_out), '--json'])
    p = payload(r)
    eval_rows[name] = {'exit': r.returncode, 'verdict': p.get('verdict'),
                       'hardware_pass': p.get('hardware_pass')}

i1_step = next(s for s in m1_doc['steps'] if s['step_id'] == 'I1-OFF-RES-VIN_5V')
m2_i1 = {'criterion': (i1_step.get('measurement') or {}).get('criterion_status'),
         'range': (i1_step.get('measurement') or {}).get('range'),
         'prerequisites': [p.get('step_id') for p in i1_step['prerequisites']]}

out = TMP / 'missing-startup'
r = cli('M2.plan.missing-startup-current',
        ['plan', '--input', str(scen / 'missing-startup-current' / 'input.json'),
         '--out', str(out), '--json'])
missing = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
missing_raw = (out / 'plan.json').read_text(encoding='utf-8')
blocked = [s for s in missing['steps'] if s['status'] == 'blocked']
m2_missing = {
    'exit': r.returncode,
    'blocked_steps': [s['step_id'] for s in blocked],
    'missing_info_mentions_startup': any(
        'startup_current' in ' '.join(s.get('missing_information') or [])
        for s in blocked),
    'invented_default_tokens': [t for t in ('100 mA', '100mA', '500 mA',
                                            '500mA', '0.1 A', '0.5 A')
                                if t in missing_raw],
}

out = TMP / 'btl'
r = cli('M2.plan.btl',
        ['plan', '--input', str(scen / 'btl-wrong-grounding' / 'input.json'),
         '--out', str(out), '--json'])
btl = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
btl_raw = (out / 'plan.json').read_text(encoding='utf-8')
btl_steps = [s for s in btl['steps'] if s['step_id'].startswith('I4-')]
m2_btl = {'exit': r.returncode,
          'blocked': [s['step_id'] for s in btl_steps
                      if s['status'] == 'blocked'],
          'mentions_differential': 'differential' in btl_raw.lower(),
          'equipment_gap_codes': [e['code'] for e in btl['equipment_gaps']]}

out = TMP / 'unsupported'
r = cli('M2.plan.unsupported-mains',
        ['plan', '--input', str(scen / 'unsupported-mains-ac' / 'input.json'),
         '--out', str(out), '--json'])
unsupported = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
m2_unsupported = {'exit': r.returncode,
                  'scope': unsupported['scope']['status'],
                  'ready_steps': [s['step_id'] for s in unsupported['steps']
                                  if s['status'] == 'ready'],
                  'steps_total': len(unsupported['steps'])}

r = cli('M2.validate.invalid-semantic',
        ['validate', '--input',
         str(scen / 'invalid-input-self-dependency' / 'input.json'), '--json'])
m2_invalid_semantic = {'exit': r.returncode,
                       'error_codes': [item['code'] for item in
                                       (payload(r).get('diagnostics') or [])
                                       if item.get('severity') == 'error']}
r = cli('M2.validate.invalid-json',
        ['validate', '--input', str(scen / 'invalid-input-json' / 'input.json'),
         '--json'])
m2_invalid_json = {'exit': r.returncode, 'payload': payload(r)}
out = TMP / 'stale-plan'
r = cli('M2.plan.invalid-json',
        ['plan', '--input', str(scen / 'invalid-input-json' / 'input.json'),
         '--out', str(out), '--json'])
m2_invalid_plan = {'exit': r.returncode,
                   'plan_exists': (out / 'plan.json').exists(),
                   'invalid_marker': (out / 'input-invalid.json').exists()}

# ---- M3 dedicated tests / frozen CLI benchmark --------------------------
r = run('M3.unittest',
        [sys.executable, '-m', 'unittest', 'discover', '-s',
         'tests/bringup_planner_tests', '-p', 'test_*.py', '-q'])
unit_tail = (r.stdout + r.stderr)[-800:]
bench_out = TMP / 'bench.json'
r = run('M3.benchmark',
        [sys.executable,
         str(W / 'benchmarks' / 'bringup-planner' / 'run_benchmark.py'),
         '--json', '--out', str(bench_out)])
bench = json.loads(bench_out.read_text(encoding='utf-8')) if bench_out.exists() else {}
m3 = {
    'unit_exit': next(row['exit_code'] for row in rows
                      if row['name'] == 'M3.unittest'),
    'unit_tail': unit_tail,
    'bench_exit': r.returncode,
    'ok': bench.get('ok'),
    'counts': bench.get('counts'),
    'missing_categories': bench.get('missing_categories'),
    'baseline': bench.get('baseline'),
    'elapsed_seconds': bench.get('elapsed_seconds'),
    'holdouts': {item['id']: item['status']
                 for item in bench.get('holdouts', [])},
    'cases': {item['id']: item['status'] for item in bench.get('cases', [])},
    'verdicts': sorted({(item.get('evaluate') or {}).get('actual', {}).get(
        'verdict') for item in bench.get('scenarios', [])
        if (item.get('evaluate') or {}).get('actual')}),
}

# ---- M4 repo regression / docs / path audit / PR ------------------------
r = run('M4.offline_suite',
        [sys.executable, str(W / 'tools' / 'offline_suite.py'),
         '--out', str(TMP / 'offline.json')])
m4_offline_exit = r.returncode
offline = json.loads((TMP / 'offline.json').read_text(encoding='utf-8'))
module_errors = {}
for line in (r.stdout + r.stderr).splitlines():
    if line.startswith('ERROR: ') and '.' in line:
        module = line[len('ERROR: '):].split('.')[0].strip()
        module_errors[module] = module_errors.get(module, 0) + 1
r = run('M4.skill_selftest',
        [sys.executable, str(W / 'easycirq' / 'scripts' /
                             'skill_selftest.py')])
m4_selftest_exit = r.returncode
m4_selftest_tail = (r.stdout + r.stderr)[-900:]
docs = sorted(path.name for path in (W / 'docs' / 'parallel-bringup-planner').glob('*.md'))
r = run('M4.pr_range_audit',
        ['git', 'diff', '--name-only', PR_BASE + '...' + MERGED_HEAD])
audit_files = [line for line in r.stdout.splitlines() if line.strip()]
outside = [item for item in audit_files
           if not item.startswith(('benchmarks/bringup-planner/',
                                   'easycirq/scripts/bringup_planner/',
                                   'docs/parallel-bringup-planner/',
                                   'tests/bringup_planner'))]

evidence = {
    'schema': 'bringup-planner-m0-m4-evidence/v1',
    'captured_at_local': '2026-10-28',
    'implementation_head': MERGED_HEAD,
    'current_worktree_head': next(row['stdout'].strip() for row in rows
                                  if row['name'] == 'M0.head'),
    'branch': next(row['stdout'].strip() for row in rows
                   if row['name'] == 'M0.branch'),
    'start_base': PR_BASE,
    'origin_main_at_capture': next(row['stdout'].strip() for row in rows
                                   if row['name'] == 'M0.origin_main'),
    'pr': pr,
    'pr_range': {'base': PR_BASE, 'head': MERGED_HEAD,
                 'files': len(audit_files), 'outside_allowed': outside},
    'm1': {'validate': {'status': m1_validate.get('status'),
                        'revision': m1_validate.get('revision'),
                        'diagnostics': len(m1_validate.get('diagnostics')
                                           or [])},
           'plan': {key: m1_plan.get(key) for key in
                    ('status', 'scope', 'steps', 'ready', 'blocked',
                     'plan_sha256')},
           'steps': len(m1_doc['steps']),
           'fault_trees': len(m1_doc['fault_trees']),
           'explain': {'status': m1_explain.get('status')}},
    'cases': cases,
    'm2': {'evaluate': eval_rows, 'i1_resistance': m2_i1,
           'missing_startup': m2_missing, 'btl': m2_btl,
           'unsupported': m2_unsupported,
           'invalid_semantic': m2_invalid_semantic,
           'invalid_json': m2_invalid_json,
           'invalid_plan': m2_invalid_plan},
    'm3': m3,
    'm4': {'offline_suite': {'exit': m4_offline_exit,
                             'status': offline.get('status'),
                             'tests_run': offline.get('tests_run'),
                             'failures': offline.get('failures'),
                             'errors': offline.get('errors'),
                             'error_modules': module_errors},
           'selftest': {'exit': m4_selftest_exit,
                        'tail': m4_selftest_tail},
           'docs': sorted(docs),
           'pr_range_audit': {'files': len(audit_files),
                              'outside_allowed': outside}},
}
evidence = sanitise(evidence)
target = Path(os.environ.get(
    'BP_EVIDENCE_OUT',
    r'C:\Users\jlc\AppData\Local\Temp\bp-m0-m4-evidence.json'))
target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n',
                  encoding='utf-8')
print(json.dumps({
    'out': str(target),
    'implementation_head': evidence['implementation_head'],
    'worktree_head': evidence['current_worktree_head'],
    'origin_main': evidence['origin_main_at_capture'],
    'pr_state': pr.get('state'),
    'pr_files': evidence['pr_range']['files'],
    'outside': len(outside),
    'unit_exit': m3['unit_exit'],
    'bench_exit': m3['bench_exit'],
    'bench_ok': m3['ok'],
    'counts': m3['counts'],
    'offline_exit': m4_offline_exit,
    'offline': evidence['m4']['offline_suite']['status'],
    'offline_errors': evidence['m4']['offline_suite']['errors'],
    'error_modules': module_errors,
    'selftest_exit': m4_selftest_exit,
}, ensure_ascii=False))
