import json
import statistics
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.benchmark import render_markdown, run_benchmark
from annotation_layout.candidates import generate_candidates
from annotation_layout.model import Counters
from annotation_layout.schema import load_input


class BenchmarkTest(unittest.TestCase):
    def _suite(self, directory: Path, names):
        cases = directory / "cases"
        cases.mkdir()
        for name in names:
            target = cases / f"{name}.json"
            target.write_bytes(helpers.synthetic(name).read_bytes())
        return cases

    def test_same_domain_baseline_vs_improved_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = self._suite(Path(temp), ["text-text", "dense"])
            result = run_benchmark(suite, repeat=2, cli_timing=False)
            self.assertEqual(result["schema"], "annotation-layout-benchmark/v1")
            self.assertEqual(result["suite"]["cases"], 2)
            self.assertEqual(result["repeat"], 2)
            self.assertIn("NOT RUN", " ".join(result["not_run"]))
            for record in result["cases"]:
                self.assertEqual(len(record["baseline"]["timing"]["samples"]), 2)
                self.assertEqual(len(record["improved"]["timing"]["samples"]), 2)
                self.assertLessEqual(record["baseline"]["timing"]["min_s"],
                                     record["baseline"]["timing"]["max_s"])
                self.assertIn("quality_equal_or_better", record["comparison"])
                if record["comparison"]["speedup_claimed"]:
                    self.assertTrue(record["comparison"]["quality_equal_or_better"])
                    self.assertEqual(record["improved"]["hard_after"], 0)
                    self.assertGreater(record["comparison"]["speedup_ratio"], 0)
            json.dumps(result)  # serializable

    def test_candidate_domain_is_shared_and_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = self._suite(Path(temp), ["text-text"])
            result = run_benchmark(suite, repeat=1, cli_timing=False)
            record = result["cases"][0]
            inp = load_input(helpers.synthetic("text-text"))
            domains = generate_candidates(inp, counter=Counters())
            self.assertEqual(record["candidate_domain"]["generated"],
                             sum(len(items) for items in domains.values()))
            baseline = record["baseline"]
            improved = record["improved"]
            self.assertEqual(baseline["candidates_generated"],
                             record["candidate_domain"]["generated"])
            self.assertEqual(improved["candidates_generated"],
                             record["candidate_domain"]["generated"])

    def test_no_speedup_claim_when_quality_is_not_met(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = self._suite(Path(temp), ["no-candidates"])
            result = run_benchmark(suite, repeat=1, cli_timing=False)
            record = result["cases"][0]
            self.assertGreater(record["improved"]["hard_after"], 0)
            self.assertFalse(record["comparison"]["quality_equal_or_better"])
            self.assertFalse(record["comparison"]["speedup_claimed"])

    def test_markdown_report_is_honest(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = self._suite(Path(temp), ["text-text"])
            result = run_benchmark(suite, repeat=1, cli_timing=False)
            markdown = render_markdown(result)
            self.assertIn("NOT RUN", markdown)
            self.assertIn("median", markdown)
            self.assertIn("Baseline", markdown)
            self.assertIn("quality", markdown.lower())

    def test_cli_round_trip_section_is_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = self._suite(Path(temp), ["text-text"])
            result = run_benchmark(suite, repeat=1, cli_timing=True)
            self.assertEqual(len(result["cli_round_trip"]), 1)
            entry = result["cli_round_trip"][0]
            self.assertIn("annotation_layout", entry["command"])
            self.assertIn("NOT RUN", entry["note"])
            self.assertEqual(entry["timing"]["samples"].__len__(), 1)


if __name__ == "__main__":
    unittest.main()
