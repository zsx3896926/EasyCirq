"""Hard-rule tests for tools/rail_planner.py (offline, no EDA, no snapshots).

The planner decides one thing only: where a spine + taps + one flag may go.
Every test builds a tiny synthetic page inside the real page frame
(x 10..1160, y 196..815), so a failure names the rule that broke:

* normal grouping           -> one rail, spine 20 away, taps along the normal
* tap through a body        -> REJECT (``wire-through-body``)
* spine out of the page     -> REJECT
* endpoint off the 5 grid   -> REJECT
* axis gap > 24             -> SPLIT into two groups
* a lone pin                -> UNROUTED, never a zero-length rail
* two rails sharing a point -> REJECT (a shared point is a junction)
* a foreign label anchor    -> REJECT (a spine through it joins two nets)
* designator/value/pin-name -> REJECT in hard mode, allowed in soft mode
* ``validate_plan``         -> catches a tampered plan
"""

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import rail_planner as rp  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def pin(x, y, rotation, net):
    return {"x": x, "y": y, "rotation": rotation, "net": net}


def build(pins, bodies=None, texts=None, nets=None, flags=None, blocks=None,
          text_obstacles="hard"):
    return rp.build_custom_context(pins, bodies or {}, texts or [], blocks=blocks,
                                   nets=nets or {}, flag_points=flags or [],
                                   text_obstacles=text_obstacles)


def plan_of(spec):
    ctx = build(**spec)
    return ctx, rp.plan(ctx, ctx.nets)


def unrouted_map(document):
    return {item["pin"]: item["why"] for item in document["unrouted"]}


class RailGeometry(unittest.TestCase):
    def test_normal_grouping_makes_one_rail(self):
        """Three same-net pins in a column facing right -> one spine, one flag."""
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 310, 0, "GND"),
                     "U1:3": pin(100, 320, 0, "GND")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 325.0)},
            "nets": {"GND": ["U1:1", "U1:2", "U1:3"]}})
        self.assertEqual(len(doc["rails"]), 1, doc["unrouted"])
        rail = doc["rails"][0]
        # spine is vertical, TAP_LEN away from the (shared) pin x
        self.assertEqual(rail["spine"], [[120.0, 300.0], [120.0, 320.0]])
        self.assertEqual(rail["spine_len"], 20.0)
        self.assertEqual(rail["max_tap"], 20.0)
        self.assertEqual(rail["pins"], ["U1:1", "U1:2", "U1:3"])
        self.assertEqual(rail["direction"], "right")
        # every tap starts at its pin and ends on the spine
        for tap, y in zip(rail["taps"], (300.0, 310.0, 320.0)):
            self.assertEqual(tap, [100.0, y, 120.0, y])
        # one flag, on a spine end, pointing the way the spine leaves it
        flag = rail["flag"]
        self.assertIn([flag["x"], flag["y"]], rail["spine"])
        self.assertEqual(flag["kind"], "ground")
        other_end = [p for p in rail["spine"]
                     if p != [flag["x"], flag["y"]]][0]
        self.assertEqual(flag["wire_leaves"],
                         rp._wire_leaves((flag["x"], flag["y"]), tuple(other_end)))
        self.assertNotIn("rotation", flag)
        # covered + unrouted == universe, and the plan re-proves itself
        self.assertEqual(doc["counts"]["covered_plus_unrouted"], 3)
        self.assertEqual(rp.validate_plan(doc, ctx, ctx.nets), [])

    def test_power_net_flag_is_not_ground(self):
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "+3V3"),
                     "U1:2": pin(100, 310, 0, "+3V3")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 315.0)},
            "nets": {"+3V3": ["U1:1", "U1:2"]}})
        self.assertEqual(doc["rails"][0]["flag"]["kind"], "power")
        self.assertEqual(rp.validate_plan(doc, ctx, ctx.nets), [])

    def test_flag_clearance_is_reported(self):
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 310, 0, "GND")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 315.0)},
            "nets": {"GND": ["U1:1", "U1:2"]}})
        clearance = doc["rails"][0]["flag_clearance"]
        self.assertIn("min_gap", clearance)
        self.assertIn("nearest", clearance)
        self.assertEqual(clearance["overlaps"], [])
        self.assertGreater(clearance["min_gap"], 0.0)
        self.assertEqual(clearance["nearest"]["kind"], "body")


class HardRejections(unittest.TestCase):
    def test_tap_through_body_is_rejected(self):
        """A tap may not enter ANOTHER part's body (wire-through-body)."""
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 310, 0, "GND")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 315.0),
                       "C9": (108.0, 296.0, 118.0, 306.0)},
            "nets": {"GND": ["U1:1", "U1:2"]}})
        self.assertEqual(doc["rails"], [])
        why = unrouted_map(doc)
        self.assertIn("body:C9", why["U1:1"])
        self.assertIn("tap-blocked", why["U1:1"])
        self.assertEqual(doc["counts"]["covered_plus_unrouted"], 2)

    def test_spine_out_of_page_is_rejected(self):
        """A left-facing pin 5 units from the frame cannot host a spine."""
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(15, 300, 180, "GND"),
                     "U1:2": pin(15, 310, 180, "GND")},
            "bodies": {"U1": (20.0, 295.0, 40.0, 315.0)},
            "nets": {"GND": ["U1:1", "U1:2"]}})
        self.assertEqual(doc["rails"], [])
        self.assertIn("out-of-page", unrouted_map(doc)["U1:1"])

    def test_off_grid_pin_is_rejected(self):
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(102, 300, 0, "GND"),
                     "U1:2": pin(102, 310, 0, "GND")},
            "bodies": {"U1": (75.0, 295.0, 97.0, 315.0)},
            "nets": {"GND": ["U1:1", "U1:2"]}})
        self.assertEqual(doc["rails"], [])
        self.assertIn("off-grid", unrouted_map(doc)["U1:1"])

    def test_two_rails_may_not_share_a_point(self):
        """A shared point is a junction: the second rail must be refused.

        The GND spine is vertical at x=120 (y 300..320); the VSYS spine is
        horizontal at y=310 (x 110..130), so they cross at (120,310).
        """
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 320, 0, "GND"),
                     "U2:1": pin(110, 330, 270, "VSYS"),
                     "U2:2": pin(130, 330, 270, "VSYS")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 325.0),
                       "U2": (100.0, 335.0, 140.0, 345.0)},
            "nets": {"GND": ["U1:1", "U1:2"], "VSYS": ["U2:1", "U2:2"]}})
        self.assertEqual(len(doc["rails"]), 1, doc["unrouted"])
        self.assertEqual(doc["rails"][0]["net"], "GND")
        self.assertIn("collides-with-existing-rail", unrouted_map(doc)["U2:1"])

    def test_spine_through_a_foreign_label_anchor_is_rejected(self):
        """Every pin outside the group has a label at pin+20: never sweep it.

        This is why rule 2 stops at a 24 gap -- a longer spine would run over
        the neighbouring pin's label anchor and silently join two nets.
        """
        ctx = build(
            {"U1:1": pin(100, 300, 0, "GND"),
             "U1:2": pin(100, 340, 0, "GND"),
             "U1:5": pin(100, 320, 0, "VSYS")},   # sits between, same side
            bodies={"U1": (75.0, 295.0, 95.0, 345.0)},
            nets={"GND": ["U1:1", "U1:2"], "VSYS": ["U1:5"]})
        doc = rp.plan(ctx, ctx.nets, max_gap=60.0)    # deliberately permissive
        self.assertEqual(doc["rails"], [])
        self.assertIn("stubend:U1:5", unrouted_map(doc)["U1:1"])

    def test_text_obstacles_block_by_default_and_are_optional(self):
        pins = {"U1:1": pin(100, 300, 0, "GND"),
                "U1:2": pin(100, 310, 0, "GND")}
        texts = [{"text": "C9", "role": "designator",
                  "bbox": (106.0, 297.0, 117.0, 307.0)}]
        bodies = {"U1": (75.0, 295.0, 95.0, 315.0)}
        nets = {"GND": ["U1:1", "U1:2"]}
        ctx_hard = build(pins, bodies=bodies, texts=texts, nets=nets)
        hard = rp.plan(ctx_hard, ctx_hard.nets)
        self.assertEqual(hard["rails"], [])
        self.assertIn("text:designator:C9", unrouted_map(hard)["U1:1"])
        self.assertEqual(hard["text_obstacles"], "hard")

        ctx_soft = build(pins, bodies=bodies, texts=texts, nets=nets,
                         text_obstacles="soft")
        soft = rp.plan(ctx_soft, ctx_soft.nets)
        self.assertEqual(len(soft["rails"]), 1)
        self.assertEqual(soft["text_obstacles"], "soft")
        self.assertEqual(rp.validate_plan(soft, ctx_soft, ctx_soft.nets), [])


class Grouping(unittest.TestCase):
    def test_gap_over_24_splits_the_group(self):
        """The gap is measured between neighbouring pins; 25 already splits."""
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 320, 0, "GND"),
                     "U1:3": pin(100, 345, 0, "GND")},   # 25 away from U1:2
            "bodies": {"U1": (75.0, 295.0, 95.0, 350.0)},
            "nets": {"GND": ["U1:1", "U1:2", "U1:3"]}})
        self.assertEqual(len(doc["rails"]), 1)
        self.assertEqual(doc["rails"][0]["pins"], ["U1:1", "U1:2"])
        self.assertEqual(unrouted_map(doc)["U1:3"], "single-pin-group")

    def test_same_row_pins_are_never_bused_collinearly(self):
        """Defensive guard: a zero-length spine is refused, never emitted."""
        ctx = build({"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 300, 0, "GND")},
                    bodies={"U1": (75.0, 295.0, 95.0, 305.0)},
                    nets={"GND": ["U1:1", "U1:2"]})
        group = {"direction": "right", "perp": 100.0, "axis": "y",
                 "members": [(300.0, "U1:1"), (300.0, "U1:2")]}
        rail, reason = rp.place_group("GND", group, ctx, [])
        self.assertIsNone(rail)
        self.assertIn("degenerate-spine", reason)

    def test_single_pin_never_becomes_a_rail(self):
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 305.0)},
            "nets": {"GND": ["U1:1"]}})
        self.assertEqual(doc["rails"], [])
        self.assertEqual(doc["counts"]["pins_covered"], 0)
        self.assertEqual(doc["counts"]["unrouted"], 1)
        self.assertEqual(unrouted_map(doc)["U1:1"], "single-pin-group")

    def test_groups_need_the_same_direction(self):
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(110, 300, 180, "GND")},
            "bodies": {"U1": (95.0, 290.0, 105.0, 310.0)},
            "nets": {"GND": ["U1:1", "U1:2"]}})
        self.assertEqual(doc["rails"], [])
        self.assertEqual(set(unrouted_map(doc).values()), {"single-pin-group"})


class NetConflicts(unittest.TestCase):
    def test_live_net_disagreeing_with_the_netlist_is_reported(self):
        """The real page has U2:1/2/3 labelled GND while the netlist says
        U2_LX / EXT_5V_EN.  The planner follows the netlist and reports it."""
        ctx, doc = plan_of({
            "pins": {"U2:1": pin(120, 580, 270, "GND"),
                     "U2:2": pin(130, 580, 270, "GND"),
                     "U2:4": pin(150, 580, 270, "GND")},
            "bodies": {"U2": (109.0, 589.0, 160.0, 670.0)},
            "nets": {"GND": ["U2:4"], "U2_LX": ["U2:1", "U2:2"]}})
        conflicts = {c["pin"]: (c["authoritative"], c["live"])
                     for c in doc["net_conflicts"]}
        self.assertEqual(conflicts["U2:1"], ("U2_LX", "GND"))
        self.assertEqual(conflicts["U2:2"], ("U2_LX", "GND"))
        self.assertEqual(doc["counts"]["net_conflicts"], 2)


class SelfCheck(unittest.TestCase):
    def _valid(self):
        return plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 310, 0, "GND")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 315.0)},
            "nets": {"GND": ["U1:1", "U1:2"]}})

    def test_valid_plan_has_no_violations(self):
        ctx, doc = self._valid()
        self.assertEqual(rp.validate_plan(doc, ctx, ctx.nets), [])

    def test_validate_catches_a_spine_through_a_body(self):
        ctx, doc = self._valid()
        ctx2 = rp.build_custom_context(
            {k: {"x": v["x"], "y": v["y"], "rotation": v["rotation"],
                 "net": v["net"]} for k, v in ctx.pins.items()},
            {"U1": (75.0, 295.0, 95.0, 315.0), "C9": (114.0, 303.0, 126.0, 313.0)},
            [], nets=ctx.nets)
        violations = rp.validate_plan(doc, ctx2, ctx2.nets)
        self.assertTrue(any("spine crosses body" in v for v in violations),
                        violations)

    def test_validate_catches_off_grid_endpoint(self):
        ctx, doc = self._valid()
        doc["rails"][0]["spine"] = [[122.0, 300.0], [122.0, 310.0]]
        violations = rp.validate_plan(doc, ctx, ctx.nets)
        self.assertTrue(any("off the" in v and "grid" in v for v in violations),
                        violations)

    def test_validate_catches_missing_pin(self):
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 310, 0, "GND"),
                     "U2:1": pin(200, 300, 0, "VBUS_L0")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 315.0),
                       "U2": (175.0, 295.0, 195.0, 305.0)},
            "nets": {"GND": ["U1:1", "U1:2"], "VBUS_L0": ["U2:1"]}})
        doc["unrouted"] = []
        doc["counts"]["covered_plus_unrouted"] = 2
        violations = rp.validate_plan(doc, ctx, ctx.nets)
        self.assertTrue(any("neither covered nor unrouted" in v for v in violations),
                        violations)

    def test_validate_catches_wrong_flag_kind(self):
        ctx, doc = self._valid()
        doc["rails"][0]["flag"]["kind"] = "power"
        violations = rp.validate_plan(doc, ctx, ctx.nets)
        self.assertTrue(any("flag kind" in v for v in violations), violations)

    def test_validate_catches_wrong_wire_leaves(self):
        ctx, doc = self._valid()
        flag = doc["rails"][0]["flag"]
        wrong = "down" if flag["wire_leaves"] != "down" else "up"
        flag["wire_leaves"] = wrong
        violations = rp.validate_plan(doc, ctx, ctx.nets)
        self.assertTrue(any("wire_leaves" in v for v in violations), violations)


class Prediction(unittest.TestCase):
    def test_prediction_counts_a_removed_label(self):
        """A railed pin's own label disappears; a 14x14 flag box replaces it."""
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 310, 0, "GND")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 315.0)},
            "texts": [{"text": "GND", "role": "net_label",
                       "bbox": (120.0, 297.0, 140.0, 307.0)},
                      {"text": "GND", "role": "net_label",
                       "bbox": (120.0, 307.0, 140.0, 317.0)},
                      {"text": "U1", "role": "designator",
                       "bbox": (60.0, 304.0, 70.0, 314.0)}],
            "nets": {"GND": ["U1:1", "U1:2"]}})
        predicted = doc["predicted"]
        self.assertEqual(predicted["labels_removed"], 2)
        self.assertEqual(predicted["flags_added"], 1)
        self.assertEqual(predicted["tree_savings"], 1)
        self.assertEqual(predicted["labels_not_matched"], [])
        self.assertEqual(rp.validate_plan(doc, ctx, ctx.nets), [])


class SchemaShape(unittest.TestCase):
    def test_output_matches_the_contract(self):
        ctx, doc = plan_of({
            "pins": {"U1:1": pin(100, 300, 0, "GND"),
                     "U1:2": pin(100, 310, 0, "GND"),
                     "U2:1": pin(200, 300, 0, "VBUS_L0")},
            "bodies": {"U1": (75.0, 295.0, 95.0, 315.0),
                       "U2": (175.0, 295.0, 195.0, 305.0)},
            "nets": {"GND": ["U1:1", "U1:2"], "VBUS_L0": ["U2:1"]},
            "blocks": {"U1": "charger"}})
        self.assertEqual(doc["schema"], "easycirq-rail-plan/v1")
        for key in ("rails", "unrouted", "counts", "predicted"):
            self.assertIn(key, doc)
        rail = doc["rails"][0]
        for key in ("net", "block", "pins", "spine", "taps", "flag",
                    "spine_len", "max_tap", "flag_clearance"):
            self.assertIn(key, rail)
        self.assertEqual(rail["block"], "charger")
        self.assertIsInstance(json.dumps(doc), str)
        self.assertEqual(doc["counts"]["pins_covered"], 2)
        self.assertEqual(doc["counts"]["unrouted"], 1)


if __name__ == "__main__":
    unittest.main()
