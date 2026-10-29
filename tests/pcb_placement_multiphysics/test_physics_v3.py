"""Unit tests for the P2.13 layer/net-class-aware simulator (``mp_place.physics_v3``).

Run from the project root::

    python -m unittest tests.test_physics_v3 -v                                     

Coverage: determinism (including a fresh process with a different
``PYTHONHASHSEED``), v2-compatible interface, energy/monotonicity checks for bad
decoupling and bad analog coupling, layer/copper parameters taking effect and
being validated, rank correlation against v2, the comparison/report pipeline and
the difference-case reason classifier.
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
from mp_place.model import hard_violations
from mp_place.objective import spearman
from mp_place.physics_v2 import PhysicsSimulatorV2
from mp_place.physics_v3 import (
    COMPONENT_TERMS,
    PhysicsSimulatorV3,
    _collect_difference_candidates,
    _diversify,
    _dominant_reason,
    _load_real_boards,
    _percentiles,
    extract_features_v3,
    render_markdown,
    run_comparison,
    write_report,
)
from mp_place.solver import random_feasible_placement
from mp_place.scenarios import build_scenarios
from mp_place.templates import instantiate

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"


def _p2_buck_scenario():
    """The P1 buck scenario, whose fixed J1 matches the hand-built layouts below."""
    return build_scenarios(seed=0)[1]


def _buck_good_layout():
    """Buck layout with caps hugging their nets and the analog divider far away."""
    return {
        "J1": (5.0, 27.5, 0),
        "U1": (20.0, 40.0, 0),
        "L1": (35.0, 40.0, 0),
        "U2": (55.0, 40.0, 0),
        "C1": (20.0, 30.0, 0),
        "C2": (28.0, 30.0, 0),
        "C3": (45.0, 30.0, 0),
        "C4": (53.0, 30.0, 0),
        "C5": (60.5, 41.0, 0),
        "C6": (60.5, 39.0, 0),
        "R1": (70.0, 12.0, 0),
        "R2": (75.0, 12.0, 0),
    }


def _buck_bad_caps_layout():
    """Same board, caps spread into the far corners (bad PDN / power loop)."""
    layout = _buck_good_layout()
    layout.update(
        {
            "C1": (12.0, 8.0, 0),
            "C2": (30.0, 8.0, 0),
            "C3": (80.0, 8.0, 0),
            "C4": (80.0, 45.0, 0),
            "C5": (60.0, 8.0, 0),
            "C6": (80.0, 30.0, 0),
        }
    )
    return layout


def _buck_bad_analog_layout():
    """Same board, analog divider moved next to the switching power stage."""
    layout = _buck_good_layout()
    layout.update({"R1": (23.5, 40.0, 0), "R2": (23.5, 37.0, 0)})
    return layout


class FeatureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = instantiate("buck", 0)
        cls.placement = random_feasible_placement(cls.scenario, random.Random(3))

    def test_baseline_prefix_and_extras(self):
        base = extract_features(self.scenario, self.placement)
        features = extract_features_v3(self.scenario, self.placement)
        self.assertGreater(len(features), len(FEATURE_NAMES))
        for name in FEATURE_NAMES:
            self.assertEqual(features[name], base[name], name)
        for name in (
            "analog_power_gap",
            "rf_power_gap",
            "digital_power_gap",
            "power_span",
            "analog_span",
            "rf_span",
            "digital_span",
            "copper_frac",
            "switch_power_w",
        ):
            self.assertIn(name, features)
        for name, value in features.items():
            self.assertTrue(math.isfinite(value), name)
            self.assertGreaterEqual(value, 0.0, name)

    def test_extraction_is_deterministic(self):
        first = extract_features_v3(self.scenario, self.placement)
        second = extract_features_v3(self.scenario, self.placement)
        self.assertEqual(first, second)
        fresh = instantiate("buck", 0)
        self.assertEqual(extract_features_v3(fresh, self.placement), first)


class InterfaceAndDeterminismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = instantiate("buck", 0)
        cls.placement = random_feasible_placement(cls.scenario, random.Random(5))
        cls.base = extract_features(cls.scenario, cls.placement)

    def test_v2_compatible_interface(self):
        v2 = PhysicsSimulatorV2(self.scenario, seed=0)
        v3 = PhysicsSimulatorV3(self.scenario, seed=0)
        for simulator in (v2, v3):
            self.assertTrue(callable(simulator.score_features))
            self.assertTrue(callable(simulator.score))
        score_from_v2_features = v3.score_features(self.base)
        self.assertTrue(math.isfinite(score_from_v2_features))
        self.assertGreaterEqual(score_from_v2_features, 0.0)
        self.assertEqual(
            v3.score(self.placement),
            v3.score_features(extract_features_v3(self.scenario, self.placement)),
        )

    def test_reproducible_with_same_seed(self):
        a = PhysicsSimulatorV3(self.scenario, seed=0)
        b = PhysicsSimulatorV3(self.scenario, seed=0)
        self.assertEqual(a.coefficients(), b.coefficients())
        self.assertEqual(a.score(self.placement), b.score(self.placement))
        self.assertEqual(a.score(self.placement), a.score(self.placement))

    def test_seed_changes_coefficients(self):
        a = PhysicsSimulatorV3(self.scenario, seed=0)
        b = PhysicsSimulatorV3(self.scenario, seed=1)
        self.assertNotEqual(a.coefficients(), b.coefficients())

    def test_deterministic_across_processes(self):
        snippet = (
            "import random\n"
            "from mp_place.templates import instantiate\n"
            "from mp_place.solver import random_feasible_placement\n"
            "from mp_place.features import extract_features\n"
            "from mp_place.physics_v3 import PhysicsSimulatorV3\n"
            "sc = instantiate('buck', 0)\n"
            "pl = random_feasible_placement(sc, random.Random(5))\n"
            "f = extract_features(sc, pl)\n"
            "out = []\n"
            "for layers in (2, 4):\n"
            "    sim = PhysicsSimulatorV3(sc, seed=0, layers=layers)\n"
            "    out.append(repr(sim.score(pl)))\n"
            "    out.append(repr(sim.diagnostics(f)['via_pressure']))\n"
            "print('|'.join(out))\n"
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
        out_b = run("777777")
        self.assertEqual(out_a, out_b)


class PhysicsSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = _p2_buck_scenario()
        cls.good = _buck_good_layout()
        cls.bad_caps = _buck_bad_caps_layout()
        cls.bad_analog = _buck_bad_analog_layout()
        sim = PhysicsSimulatorV3(cls.scenario, seed=0)
        good_features = extract_features_v3(cls.scenario, cls.good)
        cls.good_score = sim.score(cls.good)
        cls.good_field = sim.breakdown(good_features)["field_coupling"]
        cls.good_pdn = sim.breakdown(good_features)["pdn_impedance"]

    def test_layouts_are_hard_feasible(self):
        for layout in (self.good, self.bad_caps, self.bad_analog):
            self.assertEqual(hard_violations(self.scenario, layout), [])

    def test_bad_decoupling_scores_worse(self):
        for seed in (0, 1, 2):
            sim = PhysicsSimulatorV3(self.scenario, seed=seed)
            good = sim.score(self.good)
            bad = sim.score(self.bad_caps)
            self.assertGreater(bad, good, f"seed={seed}")
            bad_terms = sim.breakdown(extract_features_v3(self.scenario, self.bad_caps))
            self.assertGreater(bad_terms["pdn_impedance"], self.good_pdn if seed == 0 else 0.0)

    def test_bad_analog_coupling_scores_worse(self):
        for seed in (0, 2, 4):
            sim = PhysicsSimulatorV3(self.scenario, seed=seed)
            good = sim.score(self.good)
            bad = sim.score(self.bad_analog)
            self.assertGreater(bad, good, f"seed={seed}")
            bad_terms = sim.breakdown(extract_features_v3(self.scenario, self.bad_analog))
            self.assertGreater(bad_terms["field_coupling"], 0.0)

    def test_layers_take_effect_monotonically(self):
        sims = [PhysicsSimulatorV3(self.scenario, seed=0, layers=layers) for layers in (2, 4, 6)]
        scores = [sim.score(self.good) for sim in sims]
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])
        diagnostics = [sim.diagnostics(extract_features_v3(self.scenario, self.good)) for sim in sims]
        loops = [diag["loop_inductance_effective_nh"] for diag in diagnostics]
        pdn = [diag["pdn_impedance_au"] for diag in diagnostics]
        thermal = [diag["thermal_rise_au"] for diag in diagnostics]
        for values in (loops, pdn, thermal):
            self.assertGreater(values[0], values[1])
            self.assertGreater(values[1], values[2])
        self.assertEqual(sims[1].layers, 4)

    def test_copper_thickness_takes_effect(self):
        sims = [
            PhysicsSimulatorV3(self.scenario, seed=0, copper_thickness_mm=thickness)
            for thickness in (0.035, 0.070, 0.105)
        ]
        scores = [sim.score(self.good) for sim in sims]
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])

    def test_layers_from_scenario_attribute(self):
        scenario = _p2_buck_scenario()
        scenario.layers = 4
        auto = PhysicsSimulatorV3(scenario)
        self.assertEqual(auto.layers, 4)
        explicit = PhysicsSimulatorV3(scenario, layers=4)
        self.assertEqual(auto.score(self.good), explicit.score(self.good))
        self.assertEqual(PhysicsSimulatorV3(scenario, layers=6).layers, 6)

    def test_invalid_parameters_rejected(self):
        for layers in (0, -1, 2.5, True, 100):
            with self.assertRaises(ValueError):
                PhysicsSimulatorV3(self.scenario, layers=layers)  # type: ignore[arg-type]
        for thickness in (0.0, -0.035, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                PhysicsSimulatorV3(self.scenario, copper_thickness_mm=thickness)

    def test_breakdown_consistent(self):
        sim = PhysicsSimulatorV3(self.scenario, seed=0)
        features = extract_features_v3(self.scenario, self.good)
        parts = sim.breakdown(features)
        self.assertEqual(set(parts), set(COMPONENT_TERMS) | {"total"})
        for term in COMPONENT_TERMS:
            self.assertGreaterEqual(parts[term], 0.0)
            self.assertTrue(math.isfinite(parts[term]))
        self.assertAlmostEqual(
            math.fsum(parts[term] for term in COMPONENT_TERMS), parts["total"], places=12
        )
        self.assertAlmostEqual(parts["total"], sim.score(self.good), places=12)

    def test_rank_agreement_with_v2(self):
        v2 = PhysicsSimulatorV2(self.scenario, seed=0)
        v3 = PhysicsSimulatorV3(self.scenario, seed=0)
        rng = random.Random(11)
        placements = [random_feasible_placement(self.scenario, rng) for _ in range(20)]
        scores_v2 = [v2.score(placement) for placement in placements]
        scores_v3 = [v3.score(placement) for placement in placements]
        self.assertGreater(spearman(scores_v2, scores_v3), 0.5)


class ComparisonAndReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.data = run_comparison(
            templates=("buck", "wireless"),
            real_sources=[],
            n_random=20,
            quiet=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_board_rows_structure(self):
        self.assertEqual(len(self.data["boards"]), 2)
        for board in self.data["boards"]:
            self.assertIn(board["name"], ("buck", "wireless"))
            self.assertEqual(board["kind"], "template")
            self.assertGreaterEqual(board["layers"], 1)
            self.assertTrue(-1.0 <= board["spearman_v2_v3"] <= 1.0)
            self.assertTrue(0.0 <= board[f"top10_overlap"] <= 1.0)
            for key in ("mean", "std", "min", "max"):
                self.assertIn(key, board["truth_v2"])
                self.assertIn(key, board["truth_v3"])
                self.assertTrue(math.isfinite(board["truth_v2"][key]))
            self.assertGreater(board["mean_ratio_v3_over_v2"], 0.0)

    def test_layer_sensitivity_rows(self):
        rows = self.data["layer_sensitivity"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(len(row["layer_scores"]), 3)
            self.assertGreater(row["layer_scores"][0], row["layer_scores"][-1])
            self.assertGreater(row["copper_scores"][0], row["copper_scores"][-1])
            self.assertGreater(row["layer_drop_pct"], 0.0)
            self.assertEqual(len(row["layer_loop_inductance_nh"]), 3)

    def test_summary_and_missing_boards(self):
        summary = self.data["summary"]
        self.assertEqual(summary["n_boards"], 2)
        self.assertEqual(summary["n_real_boards"], 0)
        self.assertIn("mean_spearman_v2_v3", summary)
        self.assertIn("mean_layer_drop_pct", summary)
        self.assertEqual(self.data["missing_real_boards"], [])

    def test_missing_real_board_is_reported(self):
        data = run_comparison(
            templates=("buck",),
            real_sources=[("not-a-board", self.tmp / "does-not-exist.json")],
            n_random=5,
            quiet=True,
        )
        self.assertEqual(len(data["boards"]), 1)
        self.assertEqual(data["missing_real_boards"][0]["status"], "MISSING")

    def test_report_writer_and_renderer(self):
        md_path, json_path = write_report(self.data, self.tmp / "report")
        self.assertTrue(md_path.exists())
        self.assertTrue(json_path.exists())
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(parsed),
            {"config", "boards", "layer_sensitivity", "difference_cases", "missing_real_boards", "summary", "runtime_s"},
        )
        text = md_path.read_text(encoding="utf-8")
        for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5."):
            self.assertIn(section, text)
        self.assertIn("physics v3", text.lower())
        self.assertIn("v2", text)
        self.assertGreaterEqual(text.count("|"), 15)
        self.assertIsInstance(render_markdown(self.data), str)
        md2, json2 = write_report(self.data, self.tmp / "report")
        self.assertEqual(md2.read_bytes(), md_path.read_bytes())
        self.assertEqual(json2.read_bytes(), json_path.read_bytes())


class DifferenceCaseRuleTests(unittest.TestCase):
    def test_percentiles_lower_is_better(self):
        percentiles = _percentiles([5.0, 1.0, 3.0, 2.0])
        self.assertEqual(percentiles[1], 0.25)  # score 1.0 is best
        self.assertEqual(percentiles[0], 1.0)  # score 5.0 is worst

    def test_diversify_limits_per_board(self):
        candidates = [{"board": "a"}] * 4 + [{"board": "b"}] * 3
        selected = _diversify(candidates, max_cases=10, per_board=2)
        self.assertEqual([case["board"] for case in selected], ["a", "a", "b", "b"])

    def test_dominant_reason_classification(self):
        features = {
            "analog_power_gap": 0.02,
            "rf_power_gap": 0.5,
            "digital_power_gap": 0.5,
            "analog_span": 0.2,
            "rf_span": 0.0,
            "power_span": 0.4,
            "capcount": 0.25,
        }
        base = {term: 0.0 for term in ("loop_inductance", "pdn_impedance", "thermal", "field_coupling")}
        coupling_terms = dict(base, field_coupling=1.5)
        explanation, deltas = _dominant_reason(base, coupling_terms, features, 2, 100.0)
        self.assertEqual(max(deltas, key=deltas.get), "field_coupling")
        self.assertIn("mm", explanation)

        pdn_terms = dict(base, pdn_impedance=0.9)
        explanation, deltas = _dominant_reason(base, pdn_terms, features, 2, 100.0)
        self.assertEqual(max(deltas, key=deltas.get), "pdn_impedance")
        self.assertIn("PDN", explanation)

        loop_terms = dict(base, loop_inductance=1.1)
        explanation, _ = _dominant_reason(base, loop_terms, features, 4, 100.0)
        self.assertIn("回路", explanation)

        thermal_terms = dict(base, thermal=2.0)
        explanation, _ = _dominant_reason(base, thermal_terms, features, 2, 100.0)
        self.assertIn("铜面积", explanation)

    def test_candidate_collection_shape(self):
        """Candidate collection returns JSON-safe dicts with the documented keys."""
        # A tiny synthetic board pool: two layouts with a perfect rank flip.
        scenario = _p2_buck_scenario()
        good = _buck_good_layout()
        bad = _buck_bad_analog_layout()
        records = []
        v2 = PhysicsSimulatorV2(scenario, 0)
        v3 = PhysicsSimulatorV3(scenario, 0)
        for placement in (good, bad):
            f10 = extract_features(scenario, placement)
            fv3 = extract_features_v3(scenario, placement)
            records.append(
                {
                    "source": "random",
                    "placement": placement,
                    "features_v2": f10,
                    "features_v3": fv3,
                    "truth_v2": v2.score_features(f10),
                    "truth_v3": v3.score_features(fv3),
                }
            )
        # v2 considers "good" better; force v3 to consider it worse by hand.
        records[0]["truth_v2"], records[1]["truth_v2"] = 1.0, 2.0
        records[0]["truth_v3"], records[1]["truth_v3"] = 2.0, 1.0
        percentiles_v2 = _percentiles([record["truth_v2"] for record in records])
        percentiles_v3 = _percentiles([record["truth_v3"] for record in records])
        for record, p2, p3 in zip(records, percentiles_v2, percentiles_v3):
            record["percentile_v2"] = p2
            record["percentile_v3"] = p3
        board = {
            "name": "buck",
            "kind": "template",
            "layers": 2,
            "scenario": scenario,
            "_records": records,
            "_v2": v2,
            "_v3": v3,
        }
        cases = _collect_difference_candidates([board], v2_max=0.75, v3_min=0.75, drop_min=0.25)
        self.assertEqual(len(cases), 1)
        case = cases[0]
        for key in (
            "board",
            "percentile_v2",
            "percentile_v3",
            "percentile_drop",
            "dominant_term",
            "term_deltas_v3_minus_v2",
            "explanation",
            "placement",
            "gap_mm",
        ):
            self.assertIn(key, case)
        self.assertGreater(case["percentile_drop"], 0.0)
        self.assertTrue(json.dumps(case, ensure_ascii=False))


class RealBoardTests(unittest.TestCase):
    def test_real_board_loading_when_available(self):
        boards, missing = _load_real_boards()
        if not boards:
            self.skipTest(f"no real EasyCirq dumps available: {missing}")
        for board in boards:
            scenario = board["scenario"]
            placement = board["placements"][0]
            self.assertGreater(len(scenario.components), 0)
            self.assertGreater(len(scenario.nets), 0)
            self.assertGreaterEqual(board["layers"], 1)
            v2 = PhysicsSimulatorV2(scenario, seed=0)
            v3 = PhysicsSimulatorV3(scenario, seed=0, layers=board["layers"])
            for simulator in (v2, v3):
                value = simulator.score(placement)
                self.assertTrue(math.isfinite(value))
                self.assertGreaterEqual(value, 0.0)


if __name__ == "__main__":
    unittest.main()
