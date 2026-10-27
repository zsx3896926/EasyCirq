#!/usr/bin/env python3
"""Offline placement compilation A/B on a frozen real dual-button board.

No EDA execution. Measures Python preparation only; compiled checkpoint counts
are planned, not live speed or persisted/electrically valid board evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'design-hardware/scripts'))
import pcb_apply_plan as adapter
import pcb_cli

FIXTURE = ROOT / 'design-hardware/cases/dual-button-led-night-20261027/negative-direct-move/board-accepted-baseline.json'


def benchmark(out_dir, runs=3):
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(FIXTURE.read_text(encoding='utf-8-sig'))
    base = dump['semanticSha256']
    modules = []
    # A small translation generates real placement commands. This is a
    # compilation workload, not an electrical ECO on the routed source board.
    for c in dump['components']:
        value = {'base_semantic_sha256': base, 'partial': True,
                 'placements': [{'designator': c['designator'],
                                 'x': c['x'] + 1, 'y': c['y'],
                                 'rotation': c['rotation'], 'layer': c['layer']}]}
        path = out / ('module-' + c['designator'] + '.json')
        pcb_cli.write_json(str(path), value)
        modules.append(path)
    common = ['--dump', str(FIXTURE), '--project', 'dual-button-led-night-20261027',
              '--doc', 'PCB1', '--out-dump', str(out/'after.json'),
              '--report', str(out/'apply-report.json'),
              '--playbook-out', str(out/'playbook.json')]
    result = {'schema': 'module-batch-benchmark/v1', 'mode': 'offline-compilation',
              'real_eda_calls': 0, 'live_validation': 'NOT RUN',
              'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
              'runs': runs, 'components': len(modules),
              'scope': 'placement preparation only; no routing, gate or physical validation'}
    mutation_sets = {}
    for label in ('per_object', 'batch'):
        times = []
        final_counts = None
        for _ in range(runs):
            counts = {'dump_file_loads': 0, 'board_normalizations': 0,
                      'save_steps': 0, 'reload_steps': 0, 'dump_steps': 0,
                      'compiled_mutations': 0}
            load, normalize = adapter._load, adapter.normalize_board
            def measured_load(path):
                if Path(path).resolve() == FIXTURE.resolve():
                    counts['dump_file_loads'] += 1
                return load(path)
            def measured_normalize(value):
                counts['board_normalizations'] += 1
                return normalize(value)
            commands = ([['--plan', str(p), '--partial'] for p in modules]
                        if label == 'per_object' else
                        [[x for p in modules for x in ('--module-plan', str(p))]])
            mutations = []
            start = time.perf_counter()
            with patch.object(adapter, '_load', measured_load), patch.object(adapter, 'normalize_board', measured_normalize), patch.object(pcb_cli, 'run', side_effect=AssertionError('unexpected EDA call')):
                for command in commands:
                    code = adapter.main(common + command)
                    report = pcb_cli.load_json(str(out/'apply-report.json'))
                    if code != 0 or report['status'] != 'dry_run':
                        raise RuntimeError(json.dumps(report, ensure_ascii=False))
                    book = pcb_cli.load_json(str(out/'playbook.json'))
                    for step in book['steps']:
                        if step['id'] in ('save', 'reload', 'dump'):
                            counts[step['id'] + '_steps'] += 1
                        else:
                            mutations.append((step['run'], step['flags']))
            times.append(time.perf_counter()-start)
            counts['compiled_mutations'] = len(mutations)
            mutation_sets[label] = mutations
            final_counts = counts
        result[label] = dict(final_counts, preparation_seconds=times,
                             median_preparation_seconds=statistics.median(times))
    result['same_ordered_mutations'] = mutation_sets['per_object'] == mutation_sets['batch']
    if not result['same_ordered_mutations']:
        raise RuntimeError('batch changed mutation sequence')
    # Preserve an executable batched dry-run command and its final artifacts.
    result['dry_run_argv'] = [sys.executable, str(ROOT/'design-hardware/scripts/pcb_apply_plan.py')] + common + [x for p in modules for x in ('--module-plan', str(p))]
    pcb_cli.write_json(str(out/'result.json'), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.runs <= 20:
        parser.error('--runs must be 1..20')
    result = benchmark(args.out_dir, args.runs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
