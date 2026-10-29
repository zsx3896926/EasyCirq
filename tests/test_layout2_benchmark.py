"""Tests for the offline layout v2 benchmark (tools/layout2/benchmark.py).

Covers: page usable-area geometry, the area page lower bound, deterministic
corpus construction and its size cap/filter, the internal first-fit packer,
per-combination scoring, aggregates/examples, and the CLI contract
(``--sizes 2,3 --top 10 --out bench.json`` writes deterministic JSON).
"""
from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2 import benchmark as bench  # noqa: E402
from tools.layout2.benchmark import Rect  # noqa: E402

SCRIPT = ROOT / "tools" / "layout2" / "benchmark.py"
ENVELOPES = ROOT / "easycirq" / "assets" / "block-envelopes.json"

# Hand-computed from page 1170x825, margin 12, title block 610..1170 x 12..380:
#   left slab  598 *  801 = 478,998
#   lower slab 548 *  433 = 237,284
EXPECTED_USABLE_AREA = 716_282


def _sha_rank(combo: tuple[str, ...]) -> str:
    return hashlib.sha256("\x1f".join(combo).encode("utf-8")).hexdigest()


def _block(envelopes: dict, name: str) -> tuple[float, float]:
    raw = envelopes["blocks"][name]
    return float(raw["w"]), float(raw["h"])


class GeometryTests(unittest.TestCase):
    """Usable region and page lower bound from the contract's page template."""

    @classmethod
    def setUpClass(cls):
        cls.envelopes, cls.digest, cls.asset = bench.load_envelopes()
        cls.geometry = bench.page_geometry(cls.envelopes)

    def test_usable_area_matches_hand_computation(self):
        self.assertEqual(self.geometry["usable_area"], EXPECTED_USABLE_AREA)
        self.assertEqual(self.geometry["width"], 1170)
        self.assertEqual(self.geometry["height"], 825)
        self.assertEqual(self.geometry["margin"], 12)
        self.assertEqual(len(self.geometry["usable_rects"]), 2)
        self.assertAlmostEqual(
            sum(r.area for r in self.geometry["usable_rects"]), EXPECTED_USABLE_AREA
        )

    def test_usable_rects_exclude_title_block(self):
        title_block = self.geometry["title_block"]
        for rect in self.geometry["usable_rects"]:
            self.assertIsNone(bench.intersect(rect, title_block))
            self.assertTrue(rect.area > 0)
        # Usable rects are mutually disjoint.
        rects = self.geometry["usable_rects"]
        for a, b in itertools.combinations(rects, 2):
            self.assertIsNone(bench.intersect(a, b))

    def test_page_lower_bound_is_area_ceil_with_floor_one(self):
        self.assertEqual(bench.estimate_page_lower_bound(0, EXPECTED_USABLE_AREA), 1)
        self.assertEqual(
            bench.estimate_page_lower_bound(EXPECTED_USABLE_AREA, EXPECTED_USABLE_AREA), 1
        )
        self.assertEqual(
            bench.estimate_page_lower_bound(EXPECTED_USABLE_AREA + 1, EXPECTED_USABLE_AREA), 2
        )
        self.assertEqual(
            bench.estimate_page_lower_bound(3 * EXPECTED_USABLE_AREA, EXPECTED_USABLE_AREA), 3
        )
        with self.assertRaises(ValueError):
            bench.estimate_page_lower_bound(10, 0)


class CorpusTests(unittest.TestCase):
    """Deterministic, capped, size-filtered combination corpus."""

    @classmethod
    def setUpClass(cls):
        cls.envelopes, _, _ = bench.load_envelopes()

    def test_corpus_is_deterministic(self):
        first = bench.build_corpus(self.envelopes, (1, 2, 3, 4), 40)
        second = bench.build_corpus(self.envelopes, (1, 2, 3, 4), 40)
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )
        counts = {}
        for combo in first:
            counts[combo["size"]] = counts.get(combo["size"], 0) + 1
        self.assertEqual(counts, {1: 11, 2: 40, 3: 40, 4: 40})

    def test_size_filter_selects_requested_sizes_only(self):
        only_two = bench.build_corpus(self.envelopes, (2,), 10)
        self.assertTrue(only_two)
        self.assertEqual({combo["size"] for combo in only_two}, {2})
        self.assertEqual(len(only_two), min(55, 10))
        # Ids are stable and sorted within the run.
        self.assertEqual([c["id"] for c in only_two], [f"s2-{i:04d}" for i in range(10)])

        two_and_three = bench.build_corpus(self.envelopes, (2, 3), 10)
        self.assertEqual(len(two_and_three), 20)
        self.assertEqual({combo["size"] for combo in two_and_three}, {2, 3})

        self.assertEqual(bench.build_corpus(self.envelopes, (4,), 0)[0]["size"], 4)
        self.assertEqual(len(bench.build_corpus(self.envelopes, (4,), 0)), 330)

    def test_cap_is_per_size_and_zero_means_uncapped(self):
        capped = bench.build_corpus(self.envelopes, (1, 2, 3, 4), 3)
        self.assertEqual(len(capped), 12)
        self.assertEqual(
            {size: sum(1 for c in capped if c["size"] == size) for size in (1, 2, 3, 4)},
            {1: 3, 2: 3, 3: 3, 4: 3},
        )
        self.assertEqual(len(bench.build_corpus(self.envelopes, (1, 2, 3, 4), 0)), 561)

    def test_cap_selection_follows_sha256_ranking(self):
        names = sorted(self.envelopes["blocks"])
        expected = sorted(
            itertools.combinations(names, 3),
            key=lambda combo: (_sha_rank(combo), combo),
        )[:5]
        corpus = bench.build_corpus(self.envelopes, (3,), 5)
        self.assertEqual([tuple(c["modules"]) for c in corpus], list(expected))

    def test_corpus_modules_are_real_unique_blocks(self):
        known = set(self.envelopes["blocks"])
        corpus = bench.build_corpus(self.envelopes, (1, 2, 3, 4), 6)
        ids = [c["id"] for c in corpus]
        self.assertEqual(len(ids), len(set(ids)))
        for combo in corpus:
            self.assertEqual(len(combo["modules"]), combo["size"])
            self.assertEqual(len(set(combo["modules"])), combo["size"])
            self.assertTrue(set(combo["modules"]) <= known)

    def test_invalid_sizes_are_rejected(self):
        for bad in ([0], [5], [], (2, 0)):
            with self.assertRaises(ValueError):
                bench.normalize_sizes(bad)
        self.assertEqual(bench.parse_sizes("2,3"), (2, 3))
        self.assertEqual(bench.parse_sizes("3, 2, 3"), (2, 3))
        with self.assertRaises(ValueError):
            bench.parse_sizes("")
        with self.assertRaises(ValueError):
            bench.parse_sizes("a,b")


class PackerTests(unittest.TestCase):
    """Internal first-fit packer: splitting, page limits and leftovers."""

    def test_first_fit_splits_free_rect_and_reports_leftovers(self):
        base = [Rect(0, 0, 100, 100)]
        a = bench.Module("a", 60, 60)
        b = bench.Module("b", 60, 60)
        pages, leftover = bench.pack_pages([a, b], base, 1)
        self.assertEqual(len(pages), 1)
        self.assertEqual([p["id"] for p in pages[0]], ["a"])
        self.assertEqual([m.name for m in leftover], ["b"])
        # Placed inside the page and inside the original free rect.
        placed = pages[0][0]
        self.assertLessEqual(placed["x"] + placed["w"], 100)
        self.assertLessEqual(placed["y"] + placed["h"], 100)

    def test_second_page_takes_the_leftover(self):
        base = [Rect(0, 0, 100, 100)]
        a = bench.Module("a", 60, 60)
        b = bench.Module("b", 60, 60)
        pages, leftover = bench.pack_pages([a, b], base, 2)
        self.assertEqual(leftover, [])
        self.assertEqual(
            [[p["id"] for p in page] for page in pages], [["a"], ["b"]]
        )

    def test_oversized_module_is_never_placed(self):
        base = [Rect(0, 0, 100, 100)]
        huge = bench.Module("huge", 101, 10)
        pages, leftover = bench.pack_pages([huge], base, 2)
        self.assertEqual(pages, [])
        self.assertEqual([m.name for m in leftover], ["huge"])


class ScoringTests(unittest.TestCase):
    """Per-combination metrics and verdicts."""

    @classmethod
    def setUpClass(cls):
        cls.envelopes, _, _ = bench.load_envelopes()
        cls.geometry = bench.page_geometry(cls.envelopes)
        cls.results = [
            bench.score_combo(combo, cls.envelopes, cls.geometry)
            for combo in bench.build_corpus(cls.envelopes, (1, 2, 3, 4), 8)
        ]

    def test_metric_fields_and_invariants(self):
        verdicts = {bench.VERDICT_FIT, bench.VERDICT_OVER, bench.VERDICT_FAIL}
        for result in self.results:
            self.assertEqual(result["module_count"], result["size"])
            self.assertIn(result["fit_verdict"], verdicts)
            self.assertGreaterEqual(result["page_count_lower_bound"], 1)
            if result["fit_verdict"] == bench.VERDICT_FIT:
                self.assertEqual(result["pages_used"], result["page_count_lower_bound"])
            if result["pages_used"] is not None:
                self.assertGreaterEqual(
                    result["pages_used"], result["page_count_lower_bound"]
                )
                self.assertLessEqual(result["estimated_utilization"], 1.0 + 1e-9)
                placed = [mid for page in result["page_modules"] for mid in page]
                self.assertEqual(sorted(placed), sorted(result["modules"]))
                self.assertEqual(len(result["page_modules"]), result["pages_used"])
            else:
                self.assertIsNone(result["estimated_utilization"])
                self.assertIsNone(result["page_modules"])

    def test_single_block_always_fits_one_page(self):
        results = [
            bench.score_combo(combo, self.envelopes, self.geometry)
            for combo in bench.build_corpus(self.envelopes, (1,), 0)
        ]
        self.assertEqual(len(results), 11)
        for result in results:
            self.assertEqual(result["fit_verdict"], bench.VERDICT_FIT)
            self.assertEqual(result["pages_used"], 1)
            width, height = _block(self.envelopes, result["modules"][0])
            expected = round(
                (width * height) / EXPECTED_USABLE_AREA, 4
            )
            self.assertEqual(result["estimated_utilization"], expected)

    def test_small_pair_reaches_the_lower_bound(self):
        names = ("block.bmi270_imu_i2c", "block.ams1117_ldo_3v3")
        combo = {"id": "hand-1", "size": 2, "modules": list(names)}
        result = bench.score_combo(combo, self.envelopes, self.geometry)
        self.assertEqual(result["page_count_lower_bound"], 1)
        self.assertEqual(result["pages_used"], 1)
        self.assertEqual(result["fit_verdict"], bench.VERDICT_FIT)
        self.assertGreater(result["estimated_utilization"], 0.0)
        self.assertLessEqual(result["estimated_utilization"], 1.0)

    def test_scoring_is_repeatable(self):
        combo = bench.build_corpus(self.envelopes, (3,), 1)[0]
        self.assertEqual(
            bench.score_combo(combo, self.envelopes, self.geometry),
            bench.score_combo(combo, self.envelopes, self.geometry),
        )


class AggregateTests(unittest.TestCase):
    """Aggregate pass rate by size and top/bottom examples."""

    @classmethod
    def setUpClass(cls):
        cls.report = bench.run_benchmark(sizes=(2, 3), max_combos=6, top=4)
        cls.results = cls.report["results"]

    def test_aggregates_reconcile_with_results(self):
        by_size = {row["size"]: row for row in self.report["aggregates"]["by_size"]}
        self.assertEqual(sorted(by_size), [2, 3])
        self.assertEqual(
            sum(row["combinations"] for row in by_size.values()), len(self.results)
        )
        for size, row in by_size.items():
            subset = [r for r in self.results if r["size"] == size]
            self.assertEqual(row["combinations"], len(subset))
            self.assertEqual(
                row["fit"] + row["over"] + row["fail"], len(subset)
            )
            self.assertEqual(
                row["pass_rate"], round(row["fit"] / len(subset), 4)
            )
            self.assertGreaterEqual(row["pass_rate"], 0.0)
            self.assertLessEqual(row["pass_rate"], 1.0)
            utils = [
                r["estimated_utilization"]
                for r in subset
                if r["estimated_utilization"] is not None
            ]
            if utils:
                self.assertAlmostEqual(
                    row["mean_estimated_utilization"], sum(utils) / len(utils), places=4
                )
            else:
                self.assertIsNone(row["mean_estimated_utilization"])

        overall = self.report["aggregates"]
        self.assertEqual(overall["combinations"], len(self.results))
        self.assertEqual(overall["sizes"], [2, 3])
        self.assertEqual(
            overall["fit"] + overall["over"] + overall["fail"], len(self.results)
        )
        self.assertEqual(
            overall["pass_rate"], round(overall["fit"] / len(self.results), 4)
        )

    def test_top_and_bottom_examples_are_ordered(self):
        examples = self.report["examples"]
        self.assertEqual(len(examples["top"]), 4)
        self.assertEqual(len(examples["bottom"]), 4)
        top_utils = [e["estimated_utilization"] for e in examples["top"]]
        bottom_utils = [e["estimated_utilization"] for e in examples["bottom"]]
        self.assertEqual(top_utils, sorted(top_utils, reverse=True))
        self.assertEqual(bottom_utils, sorted(bottom_utils))
        all_utils = [
            r["estimated_utilization"]
            for r in self.results
            if r["estimated_utilization"] is not None
        ]
        self.assertEqual(examples["top"][0]["estimated_utilization"], max(all_utils))
        self.assertEqual(examples["bottom"][0]["estimated_utilization"], min(all_utils))
        for example in examples["top"] + examples["bottom"]:
            self.assertIn(
                example["id"], {r["id"] for r in self.results}
            )
            self.assertEqual(len(example["modules"]), example["size"])

    def test_report_contains_page_and_corpus_metadata(self):
        self.assertEqual(self.report["schema"], bench.SCHEMA)
        self.assertTrue(self.report["offline"])
        page = self.report["page"]
        self.assertEqual((page["width"], page["height"], page["margin"]), (1170, 825, 12))
        self.assertEqual(page["usable_area"], EXPECTED_USABLE_AREA)
        corpus = self.report["corpus"]
        self.assertEqual(corpus["block_count"], 11)
        self.assertEqual(corpus["sizes"], [2, 3])
        self.assertEqual(corpus["combinations"], 12)
        self.assertEqual(corpus["max_combos_per_size"], 6)
        self.assertEqual(len(corpus["sha256"]), 64)


class CliTests(unittest.TestCase):
    """The documented CLI: ``--sizes 2,3 --top 10 --out bench.json``."""

    def _run(self, out_path: Path, cwd: Path, extra=None):
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--sizes",
            "2,3",
            "--top",
            "3",
            "--max-combos",
            "4",
            "--out",
            str(out_path),
        ]
        if extra:
            cmd.extend(extra)
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )

    def test_cli_writes_json_in_a_self_contained_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "nested" / "bench.json"
            proc = self._run(out, tmp_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("wrote", proc.stdout)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], bench.SCHEMA)
            self.assertEqual(report["corpus"]["sizes"], [2, 3])
            self.assertEqual(report["corpus"]["combinations"], 8)
            self.assertEqual(len(report["results"]), 8)
            self.assertEqual({r["size"] for r in report["results"]}, {2, 3})
            self.assertEqual(len(report["examples"]["top"]), 3)
            self.assertEqual(len(report["examples"]["bottom"]), 3)
            self.assertEqual(report["aggregates"]["by_size"][0]["size"], 2)
            self.assertTrue(
                out.read_bytes().endswith(b"\n"),
                "output JSON must be newline terminated",
            )

    def test_cli_output_is_byte_identical_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "a.json"
            second = tmp_path / "b.json"
            proc_a = self._run(first, tmp_path)
            proc_b = self._run(second, tmp_path)
            self.assertEqual(proc_a.returncode, 0, proc_a.stderr)
            self.assertEqual(proc_b.returncode, 0, proc_b.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_cli_rejects_out_of_range_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--sizes",
                    "5",
                    "--out",
                    str(tmp_path / "bench.json"),
                ],
                cwd=str(tmp_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=300,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("out of range", proc.stderr)
            self.assertFalse((tmp_path / "bench.json").exists())

    def test_cli_stdout_mode_prints_the_same_report(self):
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--sizes",
            "1",
            "--top",
            "2",
            "--max-combos",
            "1",
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["corpus"]["combinations"], 1)
        self.assertEqual(report["results"][0]["size"], 1)


if __name__ == "__main__":
    unittest.main()
