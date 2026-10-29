"""Unit tests for mp_place.verify (P4-F verification / certificate / renderers).

Run with:  python -m unittest tests.test_verify -v

The router is stubbed through ``mp_place.verify._load_router`` so the suite is
deterministic and fast whether or not ``mp_place/router.py`` has been
delivered yet; one separate test exercises a real router when importable.
"""

import json
import math
import random
import unittest
from types import SimpleNamespace
from unittest import mock

from mp_place import verify
from mp_place.features import FEATURE_NAMES, extract_features
from mp_place.model import Component, Scenario
from mp_place.scenarios import build_scenarios
from mp_place.solver import random_feasible_placement

NO_ROUTER = (None, "mp_place.router is not available (module missing)")


def feasible_placement(sc, seed=0):
    return random_feasible_placement(sc, random.Random(seed))


def scenario(name, seed=0):
    for sc in build_scenarios(seed):
        if sc.name == name:
            return sc
    raise AssertionError("unknown scenario %r" % (name,))


def custom_scenario(ref="A&B", kind="mcu", name="custom"):
    comp = Component(ref=ref, kind=kind, w=4.0, h=4.0)
    return Scenario(
        name=name,
        board_w=20.0,
        board_h=10.0,
        components={ref: comp},
        nets=[],
        keepouts=[],
        edge_tol=2.0,
        base_placement={},
    )


class JudgeTestCase(unittest.TestCase):
    """Base class: stub the router out unless a test overrides it."""

    def setUp(self):
        patcher = mock.patch.object(verify, "_load_router",
                                    return_value=NO_ROUTER)
        patcher.start()
        self.addCleanup(patcher.stop)


class VerifyPlacementTests(JudgeTestCase):
    def test_feasible_placement_has_no_violations(self):
        for sc in build_scenarios(seed=0):
            pl = feasible_placement(sc)
            report = verify.verify_placement(sc, pl)
            self.assertEqual(report["schema"], verify.VERIFY_SCHEMA, sc.name)
            self.assertTrue(report["feasible"], sc.name)
            self.assertEqual(report["violations"], [], sc.name)
            self.assertEqual(report["missing_components"], [], sc.name)
            self.assertEqual(report["fixed_fields"], verify.FIXED_FIELDS,
                             sc.name)
            self.assertEqual(tuple(report["features"]), FEATURE_NAMES, sc.name)
            for value in report["features"].values():
                self.assertTrue(math.isfinite(value), sc.name)

    def test_features_match_the_shared_extractor(self):
        sc = scenario("buck")
        pl = feasible_placement(sc)
        report = verify.verify_placement(sc, pl)
        expected = extract_features(sc, pl)
        self.assertEqual(report["features"], expected)

    def test_out_of_board_placement_is_infeasible(self):
        sc = scenario("mcu-min")
        pl = feasible_placement(sc)
        ref = next(r for r, c in sorted(sc.components.items()) if not c.fixed)
        x, y, rot = pl[ref]
        pl[ref] = (sc.board_w + 50.0, sc.board_h + 50.0, rot)
        report = verify.verify_placement(sc, pl)
        self.assertFalse(report["feasible"])
        self.assertTrue(
            any(v.startswith("out_of_board:" + ref) for v in report["violations"]),
            report["violations"])

    def test_missing_placement_degrades_without_crashing(self):
        sc = scenario("rs485")
        pl = feasible_placement(sc)
        missing_ref = next(r for r, c in sorted(sc.components.items())
                           if not c.fixed)
        del pl[missing_ref]
        report = verify.verify_placement(sc, pl)
        self.assertFalse(report["feasible"])
        self.assertIn("missing_placement:" + missing_ref, report["violations"])
        self.assertEqual(report["missing_components"], [missing_ref])
        self.assertIsNone(report["features"],
                          "features must not be invented for an incomplete "
                          "placement")
        self.assertEqual(report["evidence"]["features"]["status"], "skipped")

    def test_infeasible_router_status_is_not_run(self):
        sc = scenario("motor")
        report = verify.verify_placement(sc, feasible_placement(sc))
        routability = report["routability"]
        self.assertEqual(routability["status"], "NOT RUN")
        self.assertIsNone(routability["completion"])
        self.assertEqual(routability["source"], "mp_place.router")
        self.assertIn("not available", routability["reason"])
        self.assertEqual(report["evidence"]["routability"]["status"],
                         "NOT RUN")

    def test_broken_router_degrades_without_crashing(self):
        class BrokenRouter:
            def __init__(self, sc):
                raise RuntimeError("boom")

        sc = scenario("motor")
        with mock.patch.object(verify, "_load_router",
                               return_value=(BrokenRouter, None)):
            report = verify.verify_placement(sc, feasible_placement(sc))
        routability = report["routability"]
        self.assertEqual(routability["status"], "NOT RUN")
        self.assertIn("router failed: RuntimeError", routability["reason"])

    def test_router_result_is_reported(self):
        seen = {}

        class FakeRouter:
            def __init__(self, sc, **kwargs):
                seen["scenario"] = sc

            def route(self, placement, critical_nets=None):
                seen["placement"] = dict(placement)
                return SimpleNamespace(completion=0.75,
                                       failed_nets=["N2", "N1"],
                                       wirelength_mm=12.5, vias=3,
                                       overflow=1, runtime_s=0.01)

        sc = scenario("buck")
        pl = feasible_placement(sc)
        with mock.patch.object(verify, "_load_router",
                               return_value=(FakeRouter, None)):
            report = verify.verify_placement(sc, pl)
        routability = report["routability"]
        self.assertEqual(routability["status"], "ROUTED")
        self.assertEqual(routability["source"], "mp_place.router.GridRouter")
        self.assertAlmostEqual(routability["completion"], 0.75)
        self.assertEqual(routability["failed_nets"], ["N1", "N2"])
        self.assertAlmostEqual(routability["wirelength_mm"], 12.5)
        self.assertEqual(routability["vias"], 3)
        self.assertEqual(routability["overflow"], 1)
        self.assertAlmostEqual(routability["runtime_s"], 0.01)
        self.assertIs(seen["scenario"], sc)
        self.assertEqual(seen["placement"], pl)

    def test_router_dict_result_is_supported(self):
        class DictRouter:
            def __init__(self, sc):
                pass

            def route(self, placement):
                return {"completion": 0.5, "failed_nets": [],
                        "wirelength_mm": 7.0, "vias": 1, "overflow": 0,
                        "runtime_s": 0.0}

        sc = scenario("wireless")
        with mock.patch.object(verify, "_load_router",
                               return_value=(DictRouter, None)):
            report = verify.verify_placement(sc, feasible_placement(sc))
        self.assertEqual(report["routability"]["status"], "ROUTED")
        self.assertAlmostEqual(report["routability"]["completion"], 0.5)

    def test_verify_is_deterministic(self):
        sc = scenario("mcu-min")
        pl = feasible_placement(sc)
        first = verify.verify_placement(sc, pl)
        second = verify.verify_placement(sc, pl)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_evidence_documents_value_sources(self):
        sc = scenario("buck")
        report = verify.verify_placement(sc, feasible_placement(sc))
        evidence = report["evidence"]
        self.assertEqual(evidence["violations"]["source"],
                         "mp_place.model.hard_violations")
        self.assertEqual(evidence["features"]["source"],
                         "mp_place.features.extract_features")
        self.assertEqual(evidence["features"]["status"], "computed")
        self.assertEqual(evidence["features"]["numeric_sources"].keys()
                         .__len__(), len(FEATURE_NAMES))
        self.assertIn("source", evidence["routability"])
        self.assertEqual(evidence["fixed_fields"]["values"],
                         verify.FIXED_FIELDS)

    def test_fixed_fields_are_hard_coded(self):
        expected = {"routing_verified": False, "drc": "NOT RUN",
                    "eda_calls": 0}
        self.assertEqual(verify.FIXED_FIELDS, expected)
        sc = scenario("motor")
        pl = feasible_placement(sc)
        ref = next(r for r, c in sorted(sc.components.items()) if not c.fixed)
        pl[ref] = (sc.board_w + 10.0, sc.board_h + 10.0, pl[ref][2])
        for report in (verify.verify_placement(sc, pl),
                       verify.certificate(sc, pl)):
            self.assertEqual(report["fixed_fields"], expected)


class CertificateTests(JudgeTestCase):
    def test_certificate_json_roundtrip(self):
        sc = scenario("buck")
        pl = feasible_placement(sc)
        cert = verify.certificate(sc, pl,
                                  extra={"solver": "sa", "steps": 10})
        text = json.dumps(cert, ensure_ascii=False, allow_nan=False)
        loaded = json.loads(text)
        self.assertEqual(loaded, cert)
        self.assertEqual(cert["schema"], verify.CERTIFICATE_SCHEMA)
        self.assertEqual(cert["verdict"], "feasible")
        self.assertIs(cert["feasible"], True)
        self.assertEqual(cert["fixed_fields"], verify.FIXED_FIELDS)
        self.assertEqual(tuple(cert["features"]), FEATURE_NAMES)
        self.assertIn("sha256:", cert["placement_digest"])
        self.assertEqual(cert["extra"], {"solver": "sa", "steps": 10})
        self.assertTrue(cert["scenario"]["digest"].startswith("sha256:"))

    def test_certificate_is_deterministic(self):
        sc = scenario("rs485")
        pl = feasible_placement(sc)
        first = verify.certificate(sc, pl)
        second = verify.certificate(sc, pl)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_certificate_excludes_wall_clock_runtime(self):
        state = {"calls": 0}

        class TickingRouter:
            def __init__(self, sc):
                pass

            def route(self, placement):
                state["calls"] += 1
                return SimpleNamespace(completion=0.5, failed_nets=[],
                                       wirelength_mm=5.0, vias=2, overflow=0,
                                       runtime_s=0.01 * state["calls"])

        sc = scenario("motor")
        pl = feasible_placement(sc)
        with mock.patch.object(verify, "_load_router",
                               return_value=(TickingRouter, None)):
            first = verify.verify_placement(sc, pl)
            second = verify.verify_placement(sc, pl)
            self.assertNotEqual(first["routability"]["runtime_s"],
                                second["routability"]["runtime_s"])
            cert_a = verify.certificate(sc, pl)
            cert_b = verify.certificate(sc, pl)
        self.assertNotIn("runtime_s", cert_a["routability"])
        self.assertEqual(json.dumps(cert_a, sort_keys=True),
                         json.dumps(cert_b, sort_keys=True))

    def test_certificate_sanitizes_non_finite_extra(self):
        sc = scenario("mcu-min")
        pl = feasible_placement(sc)
        cert = verify.certificate(
            sc, pl,
            extra={"nan": float("nan"), "inf": float("inf"),
                   "nested": [float("-inf"), 1.5]})
        text = json.dumps(cert, ensure_ascii=False, allow_nan=False)
        loaded = json.loads(text)
        self.assertIsNone(loaded["extra"]["nan"])
        self.assertIsNone(loaded["extra"]["inf"])
        self.assertEqual(loaded["extra"]["nested"], [None, 1.5])

    def test_certificate_placement_is_plain_lists(self):
        sc = scenario("wireless")
        pl = feasible_placement(sc)
        cert = verify.certificate(sc, pl)
        for ref, value in cert["placement"].items():
            self.assertIsInstance(value, list)
            self.assertEqual(len(value), 3)
            self.assertIsInstance(value[0], float)
            self.assertIsInstance(value[1], float)
        self.assertEqual(sorted(cert["placement"]), sorted(pl))

    def test_certificate_digest_tracks_the_placement(self):
        sc = scenario("buck")
        pl = feasible_placement(sc)
        same = dict(pl)
        moved = dict(pl)
        ref = next(r for r, c in sorted(sc.components.items()) if not c.fixed)
        x, y, rot = moved[ref]
        moved[ref] = (x + 3.0, y, rot)
        self.assertEqual(verify.placement_digest(pl, sc),
                         verify.placement_digest(same, sc))
        self.assertNotEqual(verify.placement_digest(pl, sc),
                            verify.placement_digest(moved, sc))
        self.assertEqual(verify.scenario_digest(sc),
                         verify.scenario_digest(scenario("buck")))

    def test_incomplete_placement_certificate_is_infeasible(self):
        sc = scenario("rs485")
        pl = feasible_placement(sc)
        ref = next(r for r, c in sorted(sc.components.items()) if not c.fixed)
        del pl[ref]
        cert = verify.certificate(sc, pl)
        self.assertEqual(cert["verdict"], "infeasible")
        self.assertIs(cert["feasible"], False)
        self.assertEqual(cert["missing_components"], [ref])
        self.assertIsNone(cert["features"])


class AsciiTests(JudgeTestCase):
    def test_ascii_is_stable_and_rectangular(self):
        for sc in build_scenarios(seed=0):
            pl = feasible_placement(sc)
            first = verify.render_ascii(sc, pl)
            second = verify.render_ascii(sc, pl)
            self.assertEqual(first, second, sc.name)
            lines = first.splitlines()
            self.assertGreater(len(lines), 5, sc.name)
            widths = {len(line) for line in lines}
            self.assertEqual(len(widths), 1,
                             "%s: non-rectangular ASCII map %r"
                             % (sc.name, widths))
            self.assertGreaterEqual(widths.pop(), 26, sc.name)

    def test_ascii_shows_components_fixed_parts_and_keepouts(self):
        sc = scenario("wireless")
        pl = feasible_placement(sc)
        text = verify.render_ascii(sc, pl)
        for ref in sorted(sc.components):
            self.assertIn(ref, text, "ref %r missing from ASCII map" % ref)
        self.assertIn("#", text, "fixed components need a '#' glyph")
        self.assertIn("~", text, "wireless keepout needs a '~' glyph")
        self.assertIn("legend:", text)
        self.assertIn("routing_verified:false", text)

    def test_ascii_width_parameter_controls_the_map(self):
        sc = scenario("buck")
        pl = feasible_placement(sc)
        narrow = verify.render_ascii(sc, pl, width=40)
        wide = verify.render_ascii(sc, pl, width=60)
        self.assertNotEqual(len(narrow.splitlines()[0]),
                            len(wide.splitlines()[0]))
        self.assertEqual(len(narrow.splitlines()[0]), 42)
        self.assertEqual(len(wide.splitlines()[0]), 62)
        self.assertEqual(verify.render_ascii(sc, pl), wide)

    def test_ascii_handles_missing_placement(self):
        sc = scenario("mcu-min")
        pl = feasible_placement(sc)
        ref = next(r for r, c in sorted(sc.components.items()) if not c.fixed)
        del pl[ref]
        text = verify.render_ascii(sc, pl)
        self.assertIn("missing placement: " + ref, text)
        self.assertIn(ref, text)

    def test_ascii_output_is_pure_ascii(self):
        for sc in build_scenarios(seed=0):
            text = verify.render_ascii(sc, feasible_placement(sc))
            text.encode("ascii")  # raises UnicodeEncodeError on failure

    def test_ascii_sanitizes_non_ascii_references(self):
        sc = custom_scenario(ref="\u03a91")
        text = verify.render_ascii(sc, {"\u03a91": (10.0, 5.0, 0)})
        text.encode("ascii")
        self.assertIn("?1", text)


class SvgTests(JudgeTestCase):
    def test_svg_contains_svg_root_and_references(self):
        for sc in build_scenarios(seed=0):
            pl = feasible_placement(sc)
            svg = verify.render_svg(sc, pl)
            self.assertTrue(svg.startswith("<svg"), sc.name)
            self.assertIn("</svg>", svg, sc.name)
            self.assertIn("<rect", svg, sc.name)
            for ref in sorted(sc.components):
                self.assertIn(ref, svg, "%s: ref %r missing from SVG"
                              % (sc.name, ref))

    def test_svg_is_deterministic(self):
        sc = scenario("motor")
        pl = feasible_placement(sc)
        self.assertEqual(verify.render_svg(sc, pl),
                         verify.render_svg(sc, pl))

    def test_svg_renders_keepouts(self):
        sc = scenario("wireless")
        svg = verify.render_svg(sc, feasible_placement(sc))
        self.assertEqual(svg.count("<title>keepout</title>"),
                         len(sc.keepouts))

    def test_svg_declares_offline_scope(self):
        sc = scenario("buck")
        svg = verify.render_svg(sc, feasible_placement(sc))
        self.assertIn("routing_verified:false", svg)
        self.assertIn("drc:NOT RUN", svg)
        self.assertIn("eda_calls:0", svg)

    def test_svg_handles_missing_placement(self):
        sc = scenario("mcu-min")
        pl = feasible_placement(sc)
        ref = next(r for r, c in sorted(sc.components.items()) if not c.fixed)
        del pl[ref]
        svg = verify.render_svg(sc, pl)
        self.assertIn("<svg", svg)
        self.assertIn("missing placement", svg)

    def test_svg_escapes_xml(self):
        sc = custom_scenario(ref="A&B")
        svg = verify.render_svg(sc, {"A&B": (10.0, 5.0, 0)})
        self.assertIn("A&amp;B", svg)
        self.assertNotIn("A&B", svg)


class RealRouterIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(verify._load_router()[0] is not None,
                         "mp_place.router is not available yet")
    def test_real_router_result_is_well_formed(self):
        sc = scenario("mcu-min")
        report = verify.verify_placement(sc, feasible_placement(sc))
        routability = report["routability"]
        self.assertIn(routability["status"], ("ROUTED", "NOT RUN"))
        if routability["status"] == "ROUTED":
            self.assertIsNotNone(routability["completion"])
            self.assertGreaterEqual(routability["completion"], 0.0)
            self.assertLessEqual(routability["completion"], 1.0)
            self.assertIsInstance(routability["failed_nets"], list)


if __name__ == "__main__":
    unittest.main()
