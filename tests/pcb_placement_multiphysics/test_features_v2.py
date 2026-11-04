"""Unit tests for the P2.7 40-dim feature set (``mp_place.features_v2``).

Run from the project root::

    python -m unittest tests.test_features_v2 -v

Coverage: feature-contract/dimension checks, finiteness and determinism
(including a fresh process with a different ``PYTHONHASHSEED``), feature range
sanity, a small Ridge(10)-vs-Ridge(40) capacity comparison and the report
writer.  The capacity fixture uses one template and a tiny budget so the tests
stay in the ~1 s range.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest

from mp_place.features import FEATURE_NAMES, extract_features
from mp_place.features_v2 import (
    BASELINE_COLUMNS,
    FEATURE_GROUPS,
    FEATURE_NAMES_V2,
    FULL_COLUMNS,
    GEOMETRY_COLUMNS,
    KERNEL_FEATURE_NAMES,
    NEW_FEATURE_NAMES,
    extract_features_v2,
    f2,
    feature_vector_v2,
    render_markdown,
    run_capacity_experiment,
    sample_feature_pool,
    write_report,
)
from mp_place.solver import random_feasible_placement
from mp_place.templates import instantiate, template_names

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"
_HEX = set("0123456789abcdef")


class FeatureContractTests(unittest.TestCase):
    """Static contract of the 40-dimension feature vector."""

    def test_dimension_and_prefix(self):
        self.assertEqual(len(FEATURE_NAMES_V2), 40)  # task range: 24..40
        self.assertEqual(FEATURE_NAMES_V2[: len(FEATURE_NAMES)], tuple(FEATURE_NAMES))
        self.assertEqual(len(NEW_FEATURE_NAMES), 30)
        self.assertEqual(set(FEATURE_NAMES_V2), set(FEATURE_NAMES) | set(NEW_FEATURE_NAMES))
        self.assertEqual(len(set(FEATURE_NAMES_V2)), 40)  # unique names

    def test_feature_groups_partition(self):
        grouped = [name for names in FEATURE_GROUPS.values() for name in names]
        self.assertEqual(len(grouped), 40)
        self.assertEqual(set(grouped), set(FEATURE_NAMES_V2))
        for label, names in FEATURE_GROUPS.items():
            self.assertTrue(names, label)

    def test_kernel_and_column_indices(self):
        self.assertEqual(len(KERNEL_FEATURE_NAMES), 7)
        for name in KERNEL_FEATURE_NAMES:
            self.assertTrue(name.startswith("kernel_"))
            self.assertNotIn(name, FEATURE_NAMES)
        expected_geometry = {
            index
            for index, name in enumerate(FEATURE_NAMES_V2)
            if name not in KERNEL_FEATURE_NAMES
        }
        self.assertEqual(set(GEOMETRY_COLUMNS), expected_geometry)
        self.assertEqual(set(FULL_COLUMNS), set(range(40)))
        # geometry columns start with the baseline ten, and kernels are excluded
        self.assertEqual(tuple(GEOMETRY_COLUMNS[:10]), tuple(BASELINE_COLUMNS))
        self.assertEqual(len(GEOMETRY_COLUMNS) + len(KERNEL_FEATURE_NAMES), 40)


class FeatureExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = []
        for name in template_names():
            scenario = instantiate(name, 0)
            rng = random.Random(4)
            placement = random_feasible_placement(scenario, rng)
            cls.samples.append((scenario, placement))

    def test_keys_order_and_baseline_identity(self):
        for scenario, placement in self.samples:
            base = extract_features(scenario, placement)
            features = extract_features_v2(scenario, placement)
            self.assertEqual(tuple(features.keys()), FEATURE_NAMES_V2)
            self.assertEqual(len(features), 40)
            for name in FEATURE_NAMES:
                self.assertEqual(features[name], base[name], f"{scenario.name}:{name}")

    def test_values_finite_and_non_negative(self):
        for scenario, placement in self.samples:
            features = extract_features_v2(scenario, placement)
            for name, value in features.items():
                self.assertTrue(math.isfinite(value), f"{scenario.name}:{name}")
                self.assertGreaterEqual(value, 0.0, f"{scenario.name}:{name}")
            vector = feature_vector_v2(features)
            self.assertEqual(len(vector), 40)
            self.assertTrue(all(math.isfinite(value) for value in vector))

    def test_interpretable_ranges(self):
        for scenario, placement in self.samples:
            f = extract_features_v2(scenario, placement)
            # normalized coordinates / fractions
            for name in ("centroid_power_x", "centroid_power_y"):
                self.assertGreaterEqual(f[name], 0.0, name)
                self.assertLessEqual(f[name], 1.0, name)
            for name in (
                "bbox_power_area",
                "bbox_all_area",
                "edge_component_frac",
                "mcu_escape_sides",
                "keepout_margin",
                "fixed_min_dist",
            ):
                self.assertGreaterEqual(f[name], 0.0, name)
                self.assertLessEqual(f[name], 1.0, name)
            for name in ("kernel_coupling_near", "kernel_coupling_mid", "kernel_coupling_far"):
                self.assertGreaterEqual(f[name], 0.0, name)
                self.assertLessEqual(f[name], 1.0, name)
            # count-like features
            self.assertGreaterEqual(f["pdn_parallel_mean"], 0.0)
            self.assertGreaterEqual(f["pdn_parallel_min"], 0.0)
            self.assertGreaterEqual(f["power_density"], 0.0)
            self.assertGreaterEqual(f["mcu_edge_clearance"], 0.0)

    def test_determinism_and_f2_alias(self):
        scenario, placement = self.samples[1]
        first = extract_features_v2(scenario, placement)
        second = extract_features_v2(scenario, placement)
        self.assertEqual(first, second)
        self.assertEqual(f2(scenario, placement), first)
        # a freshly instantiated scenario gives the identical scenario + result
        fresh = instantiate(scenario.name, 0)
        self.assertEqual(extract_features_v2(fresh, placement), first)

    def test_two_layouts_differ(self):
        scenario = instantiate("buck", 0)
        rng = random.Random(11)
        a = extract_features_v2(scenario, random_feasible_placement(scenario, rng))
        b = extract_features_v2(scenario, random_feasible_placement(scenario, rng))
        self.assertNotEqual(feature_vector_v2(a), feature_vector_v2(b))

    def test_deterministic_across_processes(self):
        """No Python hash()/randomness: PYTHONHASHSEED must not change features."""
        snippet = (
            "import random\n"
            "from mp_place.templates import instantiate\n"
            "from mp_place.solver import random_feasible_placement\n"
            "from mp_place.features_v2 import extract_features_v2, feature_vector_v2\n"
            "sc = instantiate('buck', 0)\n"
            "pl = random_feasible_placement(sc, random.Random(4))\n"
            "print(repr(feature_vector_v2(extract_features_v2(sc, pl))))\n"
        )

        def run(hash_seed):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = hash_seed
            return subprocess.check_output(
                [sys.executable, "-c", snippet],
                cwd=str(_PROJECT_ROOT),
                env=env,
                text=True,
                encoding="utf-8",
            ).strip()

        out_a = run("0")
        out_b = run("987654")
        self.assertEqual(out_a, out_b)
        scenario = instantiate("buck", 0)
        placement = random_feasible_placement(scenario, random.Random(4))
        local = repr(feature_vector_v2(extract_features_v2(scenario, placement)))
        self.assertEqual(out_a, local)


class CapacitySmokeTests(unittest.TestCase):
    """Small end-to-end capacity experiment + report writer."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.data = run_capacity_experiment(
            templates=("buck",),
            sizes=(240, 1000),
            downstream_templates=("buck",),
            downstream_sizes=(240,),
            downstream_seeds=(0,),
            steps=60,
            test_size=200,
            quiet=True,
        )
        cls.capacity = cls.data["capacity"]
        cls.downstream = cls.data["downstream"]
        cls.summary = cls.data["summary"]

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_sample_pool_is_paired(self):
        pool = sample_feature_pool("buck", 60, sample_seed=0)
        self.assertEqual(len(pool["X10"]), len(pool["X40"]))
        self.assertEqual(len(pool["X10"]), len(pool["y"]))
        self.assertEqual(len(pool["X10"][0]), 10)
        self.assertEqual(len(pool["X40"][0]), 40)
        for row10, row40 in zip(pool["X10"], pool["X40"]):
            self.assertEqual(tuple(row40[:10]), tuple(row10))

    def test_capacity_rows_complete(self):
        self.assertEqual(len(self.capacity), 5)  # ridge10/40 x 2 sizes + geom32
        sets = {row["feature_set"] for row in self.capacity}
        self.assertEqual(sets, {"ridge10", "ridge40", "ridge32_geom"})
        for row in self.capacity:
            self.assertIn(row["template"], ("buck",))
            self.assertTrue(math.isfinite(row["r2_test"]))
            self.assertTrue(math.isfinite(row["spearman_test"]))
            self.assertTrue(math.isfinite(row["tail_spearman"]))
            self.assertIn("top100_regret", row)
            self.assertGreaterEqual(row["n_kept"], 1)
            self.assertLessEqual(row["n_kept"], row["n_features"])
            for name in row["kept_features"]:
                self.assertIn(name, FEATURE_NAMES_V2)
        # the richer representation must fit clearly better on buck
        row10 = next(r for r in self.capacity if r["feature_set"] == "ridge10" and r["n"] == 1000)
        row40 = next(r for r in self.capacity if r["feature_set"] == "ridge40" and r["n"] == 1000)
        self.assertGreater(row40["r2_test"], row10["r2_test"] + 0.01)
        self.assertGreater(row40["tail_spearman"], row10["tail_spearman"])
        self.assertLess(row40["top100_regret"], row10["top100_regret"])

    def test_summary_fields(self):
        summary = self.summary
        self.assertEqual(summary["n_features"], 40)
        self.assertEqual(summary["sizes"], [240, 1000])
        self.assertIn("ridge40", summary["capacity_mean"])
        self.assertIn("ridge10", summary["capacity_mean"])
        delta = summary["capacity_delta_40_minus_10"]["r2_test"]
        self.assertEqual(set(delta), {"240", "1000"})
        self.assertGreater(delta["1000"], 0.0)
        self.assertIn("ridge32_geom", summary["ablation_n1000"])
        self.assertIn("ridge40", summary["ablation_n1000"])
        improvement = summary["downstream_improvement_40_vs_10_pct"]
        self.assertIn("240", improvement)

    def test_downstream_rows_complete(self):
        objectives = {row["objective"] for row in self.downstream}
        self.assertEqual(
            objectives, {"oracle_v2", "surrogate10_n240", "surrogate40_n240"}
        )
        for row in self.downstream:
            self.assertEqual(row["template"], "buck")
            self.assertTrue(math.isfinite(row["mean_truth"]))
            self.assertGreaterEqual(row["mean_truth"], 0.0)
            self.assertEqual(row["max_violations"], 0)
            self.assertEqual(len(row["per_seed_truth"]), 1)
            self.assertEqual(row["solver"], "portfolio-v2")

    def test_report_writer(self):
        md_path, json_path = write_report(self.data, self.tmp / "report")
        self.assertTrue(md_path.exists())
        self.assertTrue(json_path.exists())
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(parsed),
            {"config", "features", "capacity", "downstream", "summary", "runtime_s"},
        )
        self.assertEqual(len(parsed["features"]["names"]), 40)
        text = md_path.read_text(encoding="utf-8")
        for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."):
            self.assertIn(section, text)
        self.assertIn("Ridge(10)", text)
        self.assertIn("Ridge(40)", text)
        self.assertIn("40 维", text)
        self.assertGreaterEqual(text.count("|"), 20)
        self.assertIsInstance(render_markdown(self.data), str)
        # same data -> identical bytes
        md2, json2 = write_report(self.data, self.tmp / "report")
        self.assertEqual(md2.read_bytes(), md_path.read_bytes())
        self.assertEqual(json2.read_bytes(), json_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
