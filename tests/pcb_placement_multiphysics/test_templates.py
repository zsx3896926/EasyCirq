"""Unit tests for P3/P3.5: product-family templates + layout intent (HMT/CCG).

Covers the eight registered product families (five P1 families plus the three
P3.5 extensions ``esp32-sensor`` / ``can-node`` / ``bldc-driver``), the intent
JSON round trip and one end-to-end ``pipeline.run_pipeline`` run on a new
template.

Run with::

    python -m unittest tests.test_templates -v
"""

import json
import random
import unittest

from mp_place.intent import (
    CCG_TYPES,
    INTENT_SCHEMA,
    INTENT_VERSION,
    MODULE_KEYS,
    build_intent,
    intent_to_plan,
    intent_violations,
)
from mp_place.model import bbox, hard_violations, rect_overlap_area
from mp_place.pipeline import PIPELINE_SCHEMA, run_pipeline
from mp_place.scenarios import build_scenarios
from mp_place.solver import feasible_partial, random_feasible_placement
from mp_place.templates import TEMPLATES, instantiate, template_names

EXPECTED_TEMPLATES = (
    "bldc-driver",
    "buck",
    "can-node",
    "esp32-sensor",
    "mcu-min",
    "motor",
    "rs485",
    "wireless",
)
NEW_TEMPLATES = ("esp32-sensor", "can-node", "bldc-driver")
NET_CLASSES = {"power", "ground", "analog", "digital", "rf", "generic"}
EDGES = {"left", "right", "top", "bottom"}
KEEPOUT_KINDS = {"antenna_clearance", "connector_clearance"}


def _feasible_case(name, seed=0):
    """Instantiate a template and draw one hard-feasible placement."""
    sc = instantiate(name, seed=seed)
    placement = random_feasible_placement(sc, random.Random(seed))
    return sc, placement


def _intent_case(name, seed=0):
    """Build an intent and push it through a real JSON text round trip."""
    sc, placement = _feasible_case(name, seed=seed)
    intent = build_intent(sc, placement)
    loaded = json.loads(json.dumps(intent, allow_nan=False))
    return sc, placement, intent, loaded


class TemplateRegistryTests(unittest.TestCase):
    def test_eight_parameterised_families_registered(self):
        self.assertEqual(set(TEMPLATES), set(EXPECTED_TEMPLATES))
        self.assertEqual(len(TEMPLATES), 8)
        self.assertEqual(template_names(), sorted(EXPECTED_TEMPLATES))
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                spec = TEMPLATES[name]
                self.assertEqual(spec["family"], name)
                self.assertTrue(spec["title"])
                # board-size ranges
                for axis in ("w", "h"):
                    lo, hi = spec["board"][axis]
                    self.assertGreater(hi, lo, f"{name}.board.{axis}")
                # fixed edge connectors
                self.assertTrue(spec["connectors"])
                fixed_refs = set()
                for conn in spec["connectors"]:
                    self.assertIn(conn["edge"], EDGES)
                    self.assertTrue(conn["ref"].startswith("J"))
                    self.assertGreaterEqual(conn["pins"], 2)
                    fixed_refs.add(conn["ref"])
                antenna = spec["antenna"]
                if antenna is not None:
                    fixed_refs.add(antenna["ref"])
                # module parameters: power / analog / digital / interface / rf
                self.assertEqual(set(spec["modules"]), set(MODULE_KEYS))
                self.assertIsInstance(spec["modules"]["power"], dict)
                self.assertIsInstance(spec["modules"]["analog"], dict)
                rf = spec["modules"]["rf"]
                self.assertTrue(rf is None or isinstance(rf, dict))
                # keepout rules and electrical nets
                self.assertIsInstance(spec["keepout_rules"], list)
                for rule in spec["keepout_rules"]:
                    self.assertIn(rule["kind"], KEEPOUT_KINDS)
                    self.assertIn(rule["linked"], fixed_refs)
                    if rule["kind"] == "antenna_clearance":
                        self.assertEqual(len(rule["expand_mm"]), 2)
                    else:
                        self.assertEqual(len(rule["depth_mm"]), 2)
                self.assertTrue(spec["nets"])
                for net in spec["nets"]:
                    self.assertIn(net["cls"], NET_CLASSES)
                    self.assertGreaterEqual(len(net["pins"]), 2)

    def test_p3_5_templates_declare_keepout_rules(self):
        for name in NEW_TEMPLATES:
            with self.subTest(template=name):
                rules = TEMPLATES[name]["keepout_rules"]
                self.assertTrue(rules, f"{name} must declare keepout rules")
                self.assertTrue(
                    any(r["kind"] == "connector_clearance" for r in rules), name
                )
        # the two RF families also keep an antenna keepout
        for name in ("wireless", "esp32-sensor"):
            with self.subTest(template=name):
                kinds = {r["kind"] for r in TEMPLATES[name]["keepout_rules"]}
                self.assertIn("antenna_clearance", kinds)

    def test_instantiate_is_deterministic(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                a = instantiate(name, seed=3)
                b = instantiate(name, seed=3)
                self.assertEqual(a, b)
                self.assertIsNot(a, b)

    def test_seed_varies_geometry(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                self.assertNotEqual(instantiate(name, seed=0), instantiate(name, seed=1))

    def test_unknown_template_rejected(self):
        with self.assertRaises(KeyError):
            instantiate("does-not-exist")

    def test_components_nets_keepouts_are_complete(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                sc = instantiate(name, seed=0)
                self.assertEqual(sc.name, name)
                self.assertGreater(len(sc.components), 3)

                # fixed parts have base coordinates, and only fixed parts do
                fixed = sorted(r for r, c in sc.components.items() if c.fixed)
                self.assertTrue(fixed)
                self.assertEqual(set(fixed), set(sc.base_placement))
                for ref in fixed:
                    self.assertEqual(sc.base_placement[ref][2], 0)

                # every component is on at least one net; every pin exists
                covered = set()
                for net in sc.nets:
                    self.assertGreaterEqual(len(net.pins), 2, net.name)
                    for ref, pin in net.pins:
                        self.assertIn(ref, sc.components)
                        self.assertIn(pin, sc.components[ref].pins, f"{name}:{ref}:{pin}")
                        covered.add(ref)
                self.assertEqual(covered, set(sc.components), name)

                # keepouts are valid rectangles inside the board
                for x0, y0, x1, y1 in sc.keepouts:
                    self.assertLess(x0, x1)
                    self.assertLess(y0, y1)
                    self.assertGreaterEqual(x0, 0.0)
                    self.assertGreaterEqual(y0, 0.0)
                    self.assertLessEqual(x1, sc.board_w)
                    self.assertLessEqual(y1, sc.board_h)
                # one sampled keepout per declared rule
                self.assertEqual(
                    len(sc.keepouts), len(TEMPLATES[name]["keepout_rules"]), name
                )

                # the fixed subset alone is feasible (connectors on their edges)
                fixed_pl = {ref: sc.base_placement[ref] for ref in fixed}
                self.assertTrue(feasible_partial(sc, fixed_pl), name)


class TemplatePlacementTests(unittest.TestCase):
    def test_random_feasible_placement_for_every_template(self):
        for name in EXPECTED_TEMPLATES:
            for seed in (0, 1, 2):
                with self.subTest(template=name, seed=seed):
                    sc, placement = _feasible_case(name, seed=seed)
                    self.assertEqual(set(placement), set(sc.components))
                    self.assertEqual(hard_violations(sc, placement), [])

    def test_rf_templates_keep_antenna_clearance(self):
        for name in ("wireless", "esp32-sensor"):
            with self.subTest(template=name):
                sc = instantiate(name, seed=0)
                rules = TEMPLATES[name]["keepout_rules"]
                antenna_ref = TEMPLATES[name]["antenna"]["ref"]
                index = next(
                    i for i, rule in enumerate(rules)
                    if rule["kind"] == "antenna_clearance"
                )
                antenna = sc.components[antenna_ref]
                self.assertTrue(antenna.fixed)
                ax, ay, _rot = sc.base_placement[antenna_ref]
                x0, y0, x1, y1 = sc.keepouts[index]
                self.assertLessEqual(x0, ax - antenna.w / 2.0)
                self.assertLessEqual(y0, ay - antenna.h / 2.0)
                self.assertGreaterEqual(x1, ax + antenna.w / 2.0)
                self.assertGreaterEqual(y1, ay + antenna.h / 2.0)

    def test_connector_clearance_keepouts_are_valid(self):
        checked = 0
        for name in EXPECTED_TEMPLATES:
            rules = TEMPLATES[name]["keepout_rules"]
            indices = [
                i for i, rule in enumerate(rules)
                if rule["kind"] == "connector_clearance"
            ]
            if not indices:
                continue
            sc = instantiate(name, seed=0)
            for index in indices:
                with self.subTest(template=name, index=index):
                    ref = rules[index]["linked"]
                    comp = sc.components[ref]
                    self.assertTrue(comp.fixed)
                    x, y, rot = sc.base_placement[ref]
                    box = bbox(comp, x, y, rot)
                    x0, y0, x1, y1 = sc.keepouts[index]
                    # the strip starts at the connector's inner face, never on it
                    self.assertAlmostEqual(
                        rect_overlap_area(box, (x0, y0, x1, y1)), 0.0, delta=1e-9
                    )
                    if comp.edge == "left":
                        self.assertAlmostEqual(x0, box[2], delta=1e-12, msg=name)
                    elif comp.edge == "right":
                        self.assertAlmostEqual(x1, box[0], delta=1e-12, msg=name)
                    elif comp.edge == "bottom":
                        self.assertAlmostEqual(y0, box[3], delta=1e-12, msg=name)
                    else:  # top
                        self.assertAlmostEqual(y1, box[1], delta=1e-12, msg=name)
                    checked += 1
        self.assertGreaterEqual(checked, 1)


class IntentTests(unittest.TestCase):
    def test_intent_is_json_round_trippable_and_complete(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                sc, _placement, intent, loaded = _intent_case(name)
                self.assertEqual(loaded, intent)
                self.assertEqual(intent["schema"], INTENT_SCHEMA)
                self.assertEqual(intent["schema_version"], INTENT_VERSION)

                # schema envelope: five-module HMT root
                root = intent["module_tree"]["root"]
                self.assertEqual(root["id"], "root")
                self.assertEqual(root["children"], list(MODULE_KEYS))
                self.assertEqual(set(intent["modules"]), set(MODULE_KEYS))

                # modules partition all components exactly once
                bag = []
                for key in MODULE_KEYS:
                    node = intent["modules"][key]
                    self.assertEqual(node["id"], key)
                    self.assertEqual(node["depth"], 1)
                    self.assertEqual(node["parent"], "root")
                    self.assertEqual(node["children"], [])
                    bag.extend(node["members"])
                self.assertEqual(len(bag), len(set(bag)))
                self.assertEqual(set(bag), set(sc.components))

                # every component has a JSON coordinate with a legal rotation
                coords = intent["coordinates"]
                self.assertEqual(set(coords), set(sc.components))
                for ref, value in coords.items():
                    self.assertIsInstance(value, list)
                    self.assertEqual(len(value), 3)
                    self.assertIsInstance(value[2], int)
                    self.assertIn(value[2], sc.components[ref].rotations)
                fixed = sorted(r for r, c in sc.components.items() if c.fixed)
                self.assertEqual(intent["fixed"], fixed)
                self.assertEqual(len(intent["nets"]), len(sc.nets))
                self.assertEqual(len(intent["keepouts"]), len(sc.keepouts))

                # constraints are a non-empty, consistently counted CCG list
                constraints = intent["constraints"]
                self.assertTrue(constraints)
                self.assertEqual(
                    [c["id"] for c in constraints],
                    [f"ccg-{i:04d}" for i in range(1, len(constraints) + 1)],
                )
                for c in constraints:
                    self.assertIn(c["type"], CCG_TYPES)
                counts = intent["constraint_counts"]
                self.assertEqual(set(counts), set(CCG_TYPES))
                self.assertEqual(sum(counts.values()), len(constraints))
                self.assertEqual(intent["summary"]["constraints"], len(constraints))

    def test_intent_replays_exact_coordinates(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                sc, placement, _intent, loaded = _intent_case(name)
                plan = intent_to_plan(sc, loaded)
                self.assertEqual(set(plan), set(sc.components))
                for ref in sc.components:
                    for got, want in zip(plan[ref], placement[ref]):
                        self.assertAlmostEqual(got, want, delta=1e-9, msg=f"{name}:{ref}")
                # replay is deterministic and stays hard-feasible
                self.assertEqual(plan, intent_to_plan(sc, loaded))
                self.assertEqual(hard_violations(sc, plan), [])

    def test_all_ccg_constraints_hold_on_source_placement(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                sc, placement, _intent, loaded = _intent_case(name)
                self.assertEqual(intent_violations(sc, placement, loaded), [])

    def test_constraint_types_are_covered(self):
        observed = set()
        templates_with_constraints = 0
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                _sc, _placement, intent, _loaded = _intent_case(name)
                self.assertGreater(len(intent["constraints"]), 0)
                templates_with_constraints += 1
                for ctype, count in intent["constraint_counts"].items():
                    if count:
                        observed.add(ctype)
        self.assertEqual(templates_with_constraints, len(EXPECTED_TEMPLATES))
        self.assertEqual(observed, set(CCG_TYPES))

    def test_edge_constraints_match_declared_connectors(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                sc, _placement, intent, _loaded = _intent_case(name)
                edge_refs = {
                    c["ref"] for c in intent["constraints"] if c["type"] == "edge"
                }
                expected = {
                    ref for ref, comp in sc.components.items() if comp.edge is not None
                }
                self.assertEqual(edge_refs, expected)

    def test_constraint_violations_are_detected(self):
        sc, placement, _intent, loaded = _intent_case("wireless")
        connector = next(
            ref for ref, comp in sc.components.items() if comp.edge is not None
        )
        moved = dict(placement)
        x, y, rot = moved[connector]
        moved[connector] = (x + 12.0, y, rot)
        violations = intent_violations(sc, moved, loaded)
        self.assertTrue(any(":edge:" in v for v in violations), violations)

    def test_bad_intent_payloads_are_rejected(self):
        sc, _placement, _intent, loaded = _intent_case("mcu-min")
        with self.assertRaises(ValueError):
            intent_to_plan(sc, {"schema": "not-an-intent", "schema_version": 1})
        with self.assertRaises(ValueError):
            intent_to_plan(sc, {"schema": INTENT_SCHEMA, "schema_version": 99})
        with self.assertRaises(TypeError):
            intent_to_plan(sc, ["not", "a", "mapping"])

        incomplete = json.loads(json.dumps(loaded))
        incomplete["coordinates"].pop(next(iter(incomplete["coordinates"])))
        with self.assertRaises(ValueError):
            intent_to_plan(sc, incomplete)

    def test_intent_also_works_on_p1_scenarios(self):
        sc = build_scenarios(seed=0)[0]
        placement = random_feasible_placement(sc, random.Random(4))
        intent = build_intent(sc, placement)
        loaded = json.loads(json.dumps(intent, allow_nan=False))
        self.assertEqual(intent_violations(sc, placement, loaded), [])
        plan = intent_to_plan(sc, loaded)
        self.assertEqual(hard_violations(sc, plan), [])
        bag = []
        for key in MODULE_KEYS:
            bag.extend(loaded["modules"][key]["members"])
        self.assertEqual(set(bag), set(sc.components))


class PipelineSmokeTest(unittest.TestCase):
    """At least one P3.5 family must run through the full offline pipeline."""

    @classmethod
    def setUpClass(cls):
        cls.scenario = instantiate("esp32-sensor", seed=0)
        cls.report = run_pipeline("esp32-sensor", budget_steps=120, seed=0)

    def test_new_template_pipeline_is_feasible(self):
        report = self.report
        self.assertEqual(report["schema"], PIPELINE_SCHEMA)
        self.assertEqual(report["scenario"]["name"], "esp32-sensor")
        self.assertTrue(report["feasible"])
        self.assertEqual(report["violations"], [])
        placement = {
            ref: (float(coord[0]), float(coord[1]), int(coord[2]))
            for ref, coord in report["placement"].items()
        }
        self.assertEqual(set(placement), set(self.scenario.components))
        self.assertEqual(hard_violations(self.scenario, placement), [])

    def test_new_template_pipeline_intent_and_router(self):
        report = self.report
        self.assertTrue(report["intent_replay_ok"])
        self.assertEqual(report["intent_replay_violations"], [])
        self.assertGreater(report["intent_total_constraints"], 0)
        self.assertEqual(report["router"]["status"], "ROUTED")
        self.assertGreaterEqual(report["router"]["completion"], 0.0)
        self.assertLessEqual(report["router"]["completion"], 1.0)
        self.assertEqual(
            report["fixed_fields"],
            {"routing_verified": False, "drc": "NOT RUN", "eda_calls": 0},
        )

    def test_new_template_pipeline_report_is_json(self):
        report = self.report
        loaded = json.loads(json.dumps(report, ensure_ascii=False, sort_keys=True))
        self.assertEqual(loaded, report)
        self.assertIsInstance(loaded["placement"], dict)
        self.assertTrue(loaded["placement"])


if __name__ == "__main__":
    unittest.main()
