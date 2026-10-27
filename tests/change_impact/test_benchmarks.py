"""Run the frozen CLI benchmark corpus and verify it is exactly rebuildable."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / 'benchmarks' / 'change-impact'

sys.path.insert(0, str(BENCH))
import run_benchmark  # noqa: E402
import build_scenarios  # noqa: E402


class BenchmarkTest(unittest.TestCase):
    def test_all_frozen_cases_pass(self):
        result = run_benchmark.run_all()
        failures = [item for item in result['results'] if not item['passed']]
        self.assertEqual(
            failures, [],
            'benchmark failures: ' + json.dumps(
                [{'id': item['id'], 'problems': item['problems']}
                 for item in failures], ensure_ascii=False, indent=1))
        self.assertGreaterEqual(result['total'], 50)
        self.assertEqual(result['passed'], result['total'])
        for item in result['results']:
            self.assertGreaterEqual(item['timing_ms'], 0)

    def test_manifest_declares_coverage_and_not_run(self):
        manifest = run_benchmark.load_manifest()
        counts = manifest['counts']
        self.assertGreaterEqual(counts['scenarios'], 24)
        self.assertGreaterEqual(counts['composite'], 2)
        self.assertGreaterEqual(counts['holdout'], 4)
        self.assertGreaterEqual(counts['variants'], 6)
        self.assertGreaterEqual(counts['invalid'], 8)
        self.assertGreaterEqual(counts['compare'], 2)
        self.assertEqual(manifest['real_eda'], 'NOT RUN')
        self.assertEqual(manifest['physical_test'], 'NOT RUN')
        for entry in manifest['files']:
            self.assertTrue((BENCH / entry['input']).is_file(), entry['input'])
            self.assertTrue((BENCH / entry['expected']).is_file(),
                            entry['expected'])

    def test_corpus_is_exactly_rebuildable(self):
        with tempfile.TemporaryDirectory() as directory:
            rebuilt = Path(directory)
            manifest = build_scenarios.build(rebuilt)
            self.assertEqual(len(manifest['files']),
                             len(run_benchmark.load_manifest()['files']))
            committed = []
            for path in sorted(BENCH.rglob('*.json')):
                if path.name == 'manifest.json':
                    continue
                committed.append(path)
            for path in committed:
                relative = path.relative_to(BENCH)
                rebuilt_path = rebuilt / relative
                self.assertTrue(rebuilt_path.is_file(), str(relative))
                self.assertEqual(
                    path.read_bytes().replace(b'\r\n', b'\n'),
                    rebuilt_path.read_bytes().replace(b'\r\n', b'\n'),
                    f'frozen file drifted: {relative}')
            committed_manifest = json.loads(
                (BENCH / 'manifest.json').read_text(encoding='utf-8'))
            rebuilt_manifest = json.loads(
                (rebuilt / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(committed_manifest, rebuilt_manifest)

    def test_expected_results_are_independent_assertions(self):
        for path in sorted((BENCH / 'expected').glob('*.json')):
            payload = json.loads(path.read_text(encoding='utf-8'))
            self.assertIn('derivation', payload)
            self.assertTrue(payload['derivation'])
            self.assertIn('expected_status', payload)
            self.assertEqual(payload['real_eda'], 'NOT RUN')
            self.assertEqual(payload['physical_test'], 'NOT RUN')


if __name__ == '__main__':
    unittest.main()
