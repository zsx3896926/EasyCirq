"""Unit tests for P2-E dataset sampling + JSON cache (stdlib unittest only).

Covered contract points (task-10 / INTERFACES.md):
* sample_layouts returns random *hard-feasible* placements, deterministically;
* build_dataset streams (no Placement list kept) and matches features.extract_features;
* X/y/meta lengths agree, placements_hash is stable for a fixed (scenario, n, seed);
* save_dataset/load_dataset round-trip, including gzip, byte-for-byte deterministic;
* load_or_build_dataset reuses only a still-valid cache (scenario/simulator/n/seed);
* n=200 works on every bundled scenario and n=10k stays fast and small in memory.
"""

import copy
import gzip
import hashlib
import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile
import tracemalloc
import types
import unittest
from unittest import mock

from mp_place import dataset as dataset_mod
from mp_place.dataset import (
    DATASET_SCHEMA,
    build_dataset,
    dataset_matches,
    iter_layouts,
    iter_samples,
    load_dataset,
    load_or_build_dataset,
    sample_layouts,
    save_dataset,
    scenario_fingerprint,
    simulator_fingerprint,
)
from mp_place.features import FEATURE_NAMES, extract_features, feature_vector
from mp_place.model import hard_violations
from mp_place.objective import PhysicsSimulator
from mp_place.scenarios import build_scenarios

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"
_SCENARIOS = {scenario.name: scenario for scenario in build_scenarios(seed=0)}


def _scenario(name="buck"):
    return _SCENARIOS[name]


def _sim(name="buck", seed=0):
    scenario = _scenario(name)
    return PhysicsSimulator(scenario, seed=seed)


def _write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


class SamplingTests(unittest.TestCase):
    def test_sample_layouts_are_hard_feasible(self):
        for name in ("mcu-min", "rs485", "wireless"):
            scenario = _scenario(name)
            placements = sample_layouts(scenario, None, n=12, seed=0)
            self.assertEqual(len(placements), 12, name)
            for placement in placements:
                self.assertEqual(hard_violations(scenario, placement), [], name)
                self.assertEqual(set(placement), set(scenario.components), name)

    def test_sample_layouts_deterministic_per_seed(self):
        scenario = _scenario()
        first = sample_layouts(scenario, None, n=10, seed=3)
        second = sample_layouts(scenario, None, n=10, seed=3)
        other = sample_layouts(scenario, None, n=10, seed=4)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_sample_layouts_accepts_none_or_simulator(self):
        # experiment_v2._sample calls sample_layouts(scenario, None, n, seed);
        # the simulator argument must be optional and must not change sampling.
        scenario = _scenario()
        with_none = sample_layouts(scenario, None, n=5, seed=1)
        with_sim = sample_layouts(scenario, _sim(), n=5, seed=1)
        self.assertEqual(with_none, with_sim)

    def test_iter_layouts_is_lazy_and_validates_n(self):
        scenario = _scenario("rs485")
        stream = iter_layouts(scenario, n=4, seed=0)
        self.assertIsInstance(stream, types.GeneratorType)
        head = [next(stream) for _ in range(2)]
        self.assertEqual(len(head), 2)
        self.assertEqual(len(list(stream)), 2)
        self.assertEqual(len(sample_layouts(scenario, None, n=0, seed=0)), 0)
        with self.assertRaises(ValueError):
            list(iter_layouts(scenario, n=-1, seed=0))
        with self.assertRaises(TypeError):
            list(iter_layouts(scenario, n=3.5, seed=0))

    def test_invalid_n_rejected_by_build_dataset(self):
        with self.assertRaises(ValueError):
            build_dataset(_scenario(), _sim(), n=-2, seed=0)


class DatasetTests(unittest.TestCase):
    def test_build_dataset_structure_and_lengths(self):
        scenario = _scenario()
        dataset = build_dataset(scenario, _sim(), n=20, seed=2)
        self.assertEqual(set(dataset), {"meta", "X", "y", "placements_hash"})
        meta = dataset["meta"]
        self.assertEqual(meta["schema"], DATASET_SCHEMA)
        self.assertEqual(meta["scenario"], "buck")
        self.assertEqual(meta["n"], 20)
        self.assertEqual(meta["seed"], 2)
        self.assertEqual(meta["feature_names"], list(FEATURE_NAMES))
        self.assertEqual(meta["n_components"], len(scenario.components))
        self.assertEqual(meta["n_nets"], len(scenario.nets))
        self.assertEqual(meta["board_mm"], [scenario.board_w, scenario.board_h])
        self.assertEqual(meta["simulator"]["class"], "PhysicsSimulator")
        self.assertEqual(len(dataset["X"]), 20)
        self.assertEqual(len(dataset["y"]), 20)
        for row in dataset["X"]:
            self.assertEqual(len(row), len(FEATURE_NAMES))
            for value in row:
                self.assertIsInstance(value, float)
                self.assertTrue(math.isfinite(value))
        for value in dataset["y"]:
            self.assertIsInstance(value, float)
            self.assertTrue(math.isfinite(value))
        digest = dataset["placements_hash"]
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())
        int(digest, 16)  # raises ValueError if not hex

    def test_build_dataset_matches_features_directly(self):
        scenario = _scenario("buck")
        simulator = _sim("buck")
        placements = sample_layouts(scenario, simulator, n=10, seed=5)
        expected_X = [feature_vector(extract_features(scenario, pl)) for pl in placements]
        expected_y = [simulator.score_features(extract_features(scenario, pl)) for pl in placements]
        dataset = build_dataset(scenario, simulator, n=10, seed=5)
        self.assertEqual(dataset["X"], expected_X)
        self.assertEqual(dataset["y"], expected_y)

    def test_build_dataset_is_deterministic(self):
        scenario = _scenario("wireless")
        simulator = _sim("wireless")
        first = build_dataset(scenario, simulator, n=15, seed=7)
        second = build_dataset(scenario, simulator, n=15, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first["meta"], second["meta"])

    def test_placements_hash_tracks_samples(self):
        scenario = _scenario("rs485")
        simulator = _sim("rs485")
        base = build_dataset(scenario, simulator, n=8, seed=0)["placements_hash"]
        other_seed = build_dataset(scenario, simulator, n=8, seed=1)["placements_hash"]
        shorter = build_dataset(scenario, simulator, n=7, seed=0)["placements_hash"]
        empty = build_dataset(scenario, simulator, n=0, seed=0)["placements_hash"]
        self.assertEqual(len(base), 64)
        self.assertNotEqual(base, other_seed)
        self.assertNotEqual(base, shorter)
        self.assertEqual(empty, hashlib.sha256(b"").hexdigest())

    def test_iter_samples_matches_build_dataset(self):
        scenario = _scenario("mcu-min")
        simulator = _sim("mcu-min")
        rows = list(iter_samples(scenario, simulator, n=7, seed=4))
        dataset = build_dataset(scenario, simulator, n=7, seed=4)
        self.assertEqual([row for row, _truth in rows], dataset["X"])
        self.assertEqual([truth for _row, truth in rows], dataset["y"])

    def test_non_finite_truth_rejected(self):
        class BadSimulator:
            def score_features(self, features):
                return float("nan")

        with self.assertRaises(ValueError):
            build_dataset(_scenario(), BadSimulator(), n=3, seed=0)
        with self.assertRaises(TypeError):
            build_dataset(_scenario(), object(), n=3, seed=0)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.scenario = _scenario()
        self.simulator = _sim()

    def _dataset(self, n=6, seed=2):
        return build_dataset(self.scenario, self.simulator, n=n, seed=seed)

    def test_save_load_json_roundtrip(self):
        dataset = self._dataset()
        path = self.tmp / "dataset.json"
        returned = save_dataset(dataset, path)
        self.assertEqual(returned, os.fspath(path))
        loaded = load_dataset(path)
        self.assertEqual(loaded, dataset)
        raw = path.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw.count(b"\n"), 1)  # compact single-line JSON

    def test_save_load_gzip_roundtrip_and_deterministic_bytes(self):
        dataset = self._dataset()
        first = self.tmp / "a.json.gz"
        second = self.tmp / "b.json.gz"
        save_dataset(dataset, first)
        save_dataset(dataset, second)
        self.assertEqual(load_dataset(first), dataset)
        self.assertTrue(first.read_bytes().startswith(b"\x1f\x8b"))
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_save_bytes_identical_across_independent_builds(self):
        first = self.tmp / "first.json"
        second = self.tmp / "second.json"
        save_dataset(self._dataset(), first)
        save_dataset(build_dataset(self.scenario, self.simulator, n=6, seed=2), second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_save_rejects_invalid_dataset(self):
        dataset = self._dataset()
        broken = copy.deepcopy(dataset)
        broken["meta"]["n"] = 5
        with self.assertRaises(ValueError):
            save_dataset(broken, self.tmp / "broken.json")

    def test_load_rejects_invalid_files(self):
        dataset = self._dataset()
        cases = []
        cases.append("this is not json")
        missing = copy.deepcopy(dataset)
        del missing["y"]
        cases.append(json.dumps(missing))
        bad_len = copy.deepcopy(dataset)
        bad_len["meta"]["n"] = 99
        cases.append(json.dumps(bad_len))
        bad_schema = copy.deepcopy(dataset)
        bad_schema["meta"]["schema"] = "wrong/v0"
        cases.append(json.dumps(bad_schema))
        bad_hash = copy.deepcopy(dataset)
        bad_hash["placements_hash"] = "xyz"
        cases.append(json.dumps(bad_hash))
        nan_truth = copy.deepcopy(dataset)
        nan_truth["y"][0] = float("nan")
        cases.append(json.dumps(nan_truth))
        for index, text in enumerate(cases):
            path = self.tmp / f"invalid_{index}.json"
            _write_text(path, text)
            with self.assertRaises(ValueError, msg=f"case {index}"):
                load_dataset(path)

    def test_load_or_build_reuses_valid_cache(self):
        path = self.tmp / "cache.json"
        built = load_or_build_dataset(path, self.scenario, self.simulator, n=6, seed=2)
        self.assertTrue(path.exists())
        with mock.patch.object(
            dataset_mod, "build_dataset", wraps=dataset_mod.build_dataset
        ) as build_spy:
            cached = load_or_build_dataset(path, self.scenario, self.simulator, n=6, seed=2)
        self.assertEqual(build_spy.call_count, 0)
        self.assertEqual(cached, built)

    def test_load_or_build_rebuilds_when_n_changes(self):
        path = self.tmp / "cache.json"
        load_or_build_dataset(path, self.scenario, self.simulator, n=6, seed=2)
        rebuilt = load_or_build_dataset(path, self.scenario, self.simulator, n=7, seed=2)
        self.assertEqual(rebuilt["meta"]["n"], 7)
        self.assertEqual(load_dataset(path)["meta"]["n"], 7)

    def test_load_or_build_recovers_from_corrupt_cache(self):
        path = self.tmp / "cache.json"
        _write_text(path, "{broken")
        dataset = load_or_build_dataset(path, self.scenario, self.simulator, n=5, seed=1)
        self.assertEqual(dataset["meta"]["n"], 5)
        self.assertEqual(load_dataset(path), dataset)

    def test_load_or_build_rebuilds_when_simulator_changes(self):
        path = self.tmp / "cache.json"
        load_or_build_dataset(path, self.scenario, _sim(seed=0), n=5, seed=0)
        rebuilt = load_or_build_dataset(path, self.scenario, _sim(seed=9), n=5, seed=0)
        self.assertEqual(
            rebuilt["meta"]["simulator"]["fingerprint"], simulator_fingerprint(_sim(seed=9))
        )

    def test_dataset_matches_guard(self):
        dataset = self._dataset(n=8, seed=3)
        self.assertTrue(dataset_matches(dataset, self.scenario, self.simulator, 8, 3))
        self.assertFalse(dataset_matches(dataset, self.scenario, self.simulator, 9, 3))
        self.assertFalse(dataset_matches(dataset, self.scenario, self.simulator, 8, 4))
        self.assertFalse(dataset_matches(dataset, _scenario("rs485"), self.simulator, 8, 3))
        self.assertFalse(dataset_matches(dataset, self.scenario, _sim(seed=8), 8, 3))
        self.assertFalse(dataset_matches({}, self.scenario, self.simulator, 8, 3))

    def test_fingerprints_stable_and_sensitive(self):
        scenario = _scenario()
        self.assertEqual(scenario_fingerprint(scenario), scenario_fingerprint(_scenario()))
        self.assertNotEqual(scenario_fingerprint(scenario), scenario_fingerprint(_scenario("rs485")))
        self.assertEqual(len(scenario_fingerprint(scenario)), 64)
        self.assertEqual(simulator_fingerprint(_sim(seed=0)), simulator_fingerprint(_sim(seed=0)))
        self.assertNotEqual(simulator_fingerprint(_sim(seed=0)), simulator_fingerprint(_sim(seed=1)))
        self.assertEqual(len(simulator_fingerprint(_sim())), 64)


class ScaleTests(unittest.TestCase):
    def test_n200_feasible_on_every_scenario(self):
        for scenario in build_scenarios(seed=0):
            simulator = PhysicsSimulator(scenario, seed=0)
            placements = sample_layouts(scenario, None, n=200, seed=4)
            self.assertEqual(len(placements), 200, scenario.name)
            for placement in placements:
                self.assertEqual(hard_violations(scenario, placement), [], scenario.name)
            dataset = build_dataset(scenario, simulator, n=200, seed=4)
            self.assertEqual(dataset["meta"]["n"], 200)
            self.assertEqual(len(dataset["X"]), 200)
            self.assertEqual(len(dataset["y"]), 200)
            for row in dataset["X"]:
                self.assertEqual(len(row), len(FEATURE_NAMES))
                self.assertTrue(all(math.isfinite(value) for value in row))
            self.assertTrue(all(math.isfinite(value) for value in dataset["y"]))

    def test_memory_bounded_while_building(self):
        scenario = _scenario("rs485")
        simulator = _sim("rs485")
        tracemalloc.start()
        try:
            dataset = build_dataset(scenario, simulator, n=2000, seed=0)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(dataset["X"]), 2000)
        self.assertNotIn("placements", dataset)
        # Building 2k samples keeps only X/y/hash: peak must stay well under
        # 32 MB (a per-sample Placement list would be far larger in aggregate).
        self.assertLess(peak, 32 * 1024 * 1024, f"peak={peak / 1e6:.1f} MB")

    def test_10k_smoke(self):
        scenario = _scenario("rs485")
        simulator = _sim("rs485")
        dataset = build_dataset(scenario, simulator, n=10000, seed=0)
        self.assertEqual(dataset["meta"]["n"], 10000)
        self.assertEqual(len(dataset["X"]), 10000)
        self.assertEqual(len(dataset["y"]), 10000)
        self.assertEqual(len(dataset["placements_hash"]), 64)
        self.assertTrue(all(math.isfinite(value) for value in dataset["y"]))
        # The first row must be the features of the first sampled layout.
        first_layout = sample_layouts(scenario, simulator, n=1, seed=0)[0]
        self.assertEqual(dataset["X"][0], feature_vector(extract_features(scenario, first_layout)))

    def test_cross_process_determinism(self):
        scenario = _scenario()
        simulator = _sim()
        local_dataset = build_dataset(scenario, simulator, n=6, seed=3)
        with tempfile.TemporaryDirectory() as tmp:
            local_path = os.path.join(tmp, "local.json")
            remote_path = os.path.join(tmp, "remote.json")
            save_dataset(local_dataset, local_path)
            code = (
                "import sys\n"
                "from mp_place.scenarios import build_scenarios\n"
                "from mp_place.objective import PhysicsSimulator\n"
                "from mp_place.dataset import build_dataset, save_dataset\n"
                "scenario = {s.name: s for s in build_scenarios(seed=0)}['buck']\n"
                "dataset = build_dataset(scenario, PhysicsSimulator(scenario, 0), n=6, seed=3)\n"
                "save_dataset(dataset, sys.argv[1])\n"
                "print(dataset['placements_hash'])\n"
            )
            completed = subprocess.run(
                [sys.executable, "-c", code, remote_path],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), local_dataset["placements_hash"])
            with open(local_path, "rb") as local_file, open(remote_path, "rb") as remote_file:
                self.assertEqual(local_file.read(), remote_file.read())


if __name__ == "__main__":
    unittest.main()
