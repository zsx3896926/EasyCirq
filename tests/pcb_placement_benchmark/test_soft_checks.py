"""Soft checks: pad distances, HPWL, congestion, review vs acceptable."""
from . import fixtures as f
from . import support


def _pad_case(pin_offset, max_mm, *, c1_center=(26, 15), expected=None,
              nets=None, rubric=None):
    components = [
        f.component("U1", 20, 15, 10, 10, pins={"VDD": pin_offset}),
        f.component("C1", c1_center[0], c1_center[1], 2, 2,
                    pins={"1": (-1, 0)}),
    ]
    return f.case(
        components=components,
        placement={"U1": f.placed(20, 15),
                   "C1": f.placed(c1_center[0], c1_center[1])},
        checks=[f.check("ck-decoup", "max_distance",
                        [["C1", "1"], ["U1", "VDD"]], max_mm)],
        nets=nets if nets is not None else [],
        rubric=rubric,
        expected=expected if expected is not None else f.expected())


class PadDistanceTests(support.CliTestCase):
    def test_distance_uses_pads_not_component_centers(self):
        # Centers are 6 mm apart; the pads are 9 mm apart (VDD on the far
        # side).  A center-based shortcut would pass this case; the contract
        # fails it.
        document = _pad_case(
            (-4, 0), 7.0,
            expected=f.expected("review", ["distance_far"], ["ck-decoup"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "review")
        self.assert_hard(result, payload)
        self.assert_soft_fail(result, payload, "ck-decoup")
        entry = support.soft_entries(payload)[0]
        self.assertEqual(entry["code"], "distance_far")
        self.assertAlmostEqual(entry["value_mm"], 9.0, places=9,
                               msg=result.context())
        self.assert_match(result, payload)

    def test_close_pads_are_acceptable_even_when_centers_are_far(self):
        # Center distance 6 mm, pad distance 1 mm: must not be failed.
        document = _pad_case((4, 0), 2.0)
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_soft_fail(result, payload)
        entry = support.soft_entries(payload)[0]
        self.assertAlmostEqual(entry["value_mm"], 1.0, places=9,
                               msg=result.context())
        self.assertTrue(entry["ok"], msg=result.context())

    def test_pad_distance_equal_to_the_limit_passes(self):
        components = [
            f.component("U1", 20, 15, 8, 8, pins={"P": (2, 0)}),
            f.component("U2", 25, 15, 2, 2, pins={"Q": (0, 0)}, fixed=True,
                        fixed_xy=(25, 15)),
        ]
        document = f.case(
            components=components,
            placement={"U1": f.placed(20, 15)},
            checks=[f.check("ck-limit", "max_distance",
                            [["U1", "P"], ["U2", "Q"]], 3.0)])
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        entry = support.soft_entries(payload)[0]
        self.assertAlmostEqual(entry["value_mm"], 3.0, places=9,
                               msg=result.context())
        self.assertTrue(entry["ok"], msg=result.context())

    def test_soft_check_entry_has_the_contract_fields(self):
        document = _pad_case((4, 0), 2.0)
        result = self.judge(document)
        payload = self.assert_single_json(result)
        entries = support.soft_entries(payload)
        self.assertEqual(len(entries), 1, msg=result.context())
        self.assertEqual(
            set(entries[0]), {"check_id", "code", "value_mm", "max_mm", "ok",
                              "basis"},
            msg=result.context())


class LoopSpanTests(support.CliTestCase):
    def test_loop_span_failure_uses_loop_large(self):
        components = [f.component("U1", 20, 15, 10, 10,
                                  pins={"A": (-4, 0), "B": (4, 0)})]
        document = f.case(
            components=components,
            placement={"U1": f.placed(20, 15)},
            checks=[f.check("ck-loop", "loop_span",
                            [["U1", "A"], ["U1", "B"]], 5.0)],
            expected=f.expected("review", ["loop_large"], ["ck-loop"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "review")
        self.assert_soft_fail(result, payload, "ck-loop")
        entry = support.soft_entries(payload)[0]
        self.assertEqual(entry["code"], "loop_large")
        self.assertAlmostEqual(entry["value_mm"], 8.0, places=9,
                               msg=result.context())
        self.assert_match(result, payload)


class GlobalProxyTests(support.CliTestCase):
    @staticmethod
    def _hpwl_components():
        components = [
            f.component("U1", 20, 15, 10, 10,
                        pins={"A": (-4, 0), "B": (4, 0)}),
            f.component("C1", 26, 15, 2, 2, pins={"1": (-1, 0)}),
        ]
        nets = [
            f.net("N1", "power", [["U1", "A"], ["U1", "B"]]),
            f.net("N2", "signal", [["U1", "B"], ["C1", "1"]]),
        ]
        return components, nets

    def test_hpwl_and_by_class_metrics(self):
        components, nets = self._hpwl_components()
        document = f.case(
            components=components, nets=nets,
            placement={"U1": f.placed(20, 15), "C1": f.placed(26, 15)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        metrics = payload["metrics"]
        self.assertAlmostEqual(metrics["hpwl_mm"], 9.0, places=9,
                               msg=result.context())
        self.assertEqual(metrics["hpwl_by_class"],
                         {"power": 8.0, "signal": 1.0},
                         msg=result.context())
        self.assertEqual(metrics["congestion_max"], 2,
                         msg=result.context())

    def test_hpwl_over_limit_produces_hpwl_high(self):
        components, nets = self._hpwl_components()
        document = f.case(
            components=components, nets=nets,
            placement={"U1": f.placed(20, 15), "C1": f.placed(26, 15)},
            rubric={**f.DEFAULT_RUBRIC, "hpwl_max_mm": 8.0})
        result = self.judge(document)
        payload = self.assert_verdict(result, "review")
        self.assert_match(result, payload, verdict=False, codes=False)
        self.assert_mismatch_contains(result, payload,
                                      "unexpected code: hpwl_high")
        self.assertEqual(payload["metrics"]["hpwl_mm"], 9.0)
        for entry in support.soft_entries(payload):
            self.assertNotEqual(entry["code"], "hpwl_high",
                                msg="global proxies must not enter soft\n"
                                    + result.context())

    def test_congestion_over_limit_produces_congestion_hotspot(self):
        components = [
            f.component("U1", 20, 15, 10, 10,
                        pins={"A": (-8, -8), "B": (8, 8)}),
            f.component("C1", 26, 15, 2, 2,
                        pins={"P1": (-14, -8), "P2": (2, 8)}),
        ]
        nets = [
            f.net("N1", "signal", [["U1", "A"], ["U1", "B"]]),
            f.net("N2", "signal", [["C1", "P1"], ["C1", "P2"]]),
        ]
        document = f.case(
            components=components, nets=nets,
            placement={"U1": f.placed(20, 15), "C1": f.placed(26, 15)},
            rubric={**f.DEFAULT_RUBRIC, "congestion_max": 1})
        result = self.judge(document)
        payload = self.assert_verdict(result, "review")
        self.assertEqual(payload["metrics"]["congestion_max"], 2,
                         msg=result.context())
        self.assert_match(result, payload, verdict=False, codes=False)
        self.assert_mismatch_contains(result, payload,
                                      "unexpected code: congestion_hotspot")

    def test_low_hpwl_does_not_mask_a_hard_failure(self):
        board = f.board_document(
            keepouts=[f.keepout("ko-antenna", [10, 10, 30, 20])])
        document = f.case(
            board=board,
            components=[f.component("U1", 20, 15, 8, 8)],
            placement={"U1": f.placed(20, 15)},
            expected=f.expected("blocking", ["keepout_violation"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assertEqual(payload["metrics"]["hpwl_mm"], 0.0,
                         msg=result.context())
        self.assert_hard(result, payload, "keepout_violation")
        self.assert_match(result, payload)

    def test_empty_and_single_pin_nets_do_not_affect_the_proxies(self):
        components = [f.component("U1", 20, 15, 8, 8,
                                  pins={"A": (0, 0)})]
        nets = [
            f.net("EMPTY", "ground", []),
            f.net("SINGLE", "signal", [["U1", "A"]]),
        ]
        document = f.case(components=components, nets=nets,
                          placement={"U1": f.placed(20, 15)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assertEqual(payload["metrics"]["hpwl_mm"], 0.0,
                         msg=result.context())
        self.assertEqual(payload["metrics"]["hpwl_by_class"], {},
                         msg=result.context())
        self.assertEqual(payload["metrics"]["congestion_max"], 0,
                         msg=result.context())


class CodeSetTests(support.CliTestCase):
    def test_two_failing_checks_report_both_specific_codes(self):
        components = [f.component("U1", 20, 15, 10, 10,
                                  pins={"A": (-4, 0), "B": (4, 0)})]
        checks = [
            f.check("ck-distance", "max_distance",
                    [["U1", "A"], ["U1", "B"]], 5.0),
            f.check("ck-loop", "loop_span",
                    [["U1", "A"], ["U1", "B"]], 5.0),
        ]
        document = f.case(
            components=components,
            placement={"U1": f.placed(20, 15)},
            checks=checks,
            expected=f.expected("review", ["loop_large", "distance_far"],
                                ["ck-loop", "ck-distance"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "review")
        self.assert_soft_fail(result, payload, "ck-distance", "ck-loop")
        self.assert_match(result, payload,
                          verdict=True, codes=True, soft_fail=True)
        self.assertEqual(
            [entry["code"] for entry in support.soft_entries(payload)],
            ["distance_far", "loop_large"], msg=result.context())

    def test_passing_checks_are_reported_with_ok_true(self):
        document = _pad_case((4, 0), 2.0)
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        entries = support.soft_entries(payload)
        self.assertEqual(len(entries), 1, msg=result.context())
        self.assertIs(entries[0]["ok"], True, msg=result.context())
