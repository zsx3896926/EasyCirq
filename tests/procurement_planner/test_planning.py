"""Quantity, pricing, channel, inventory, fee and budget CLI scenarios."""

import copy
import tempfile
import unittest

from . import support as S


class PlanningCli(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pp-plan-")
        self.addCleanup(self.tmp.cleanup)

    def run_doc(self, data, *args):
        path = S.write_input(self.tmp.name, data)
        proc, report = S.run_cli([*args, "--input", path])
        return proc, report, path

    def plan(self, data, *args):
        return self.run_doc(data, "plan", *args)

    def make(self, rows, offers, snapshots=None, fees=None, board=10,
             demand=None, attrition=None, policies=None):
        return S.input_doc(
            rows=rows, offers=offers,
            snapshots=snapshots if snapshots is not None
            else [S.snapshot("SNAP-1")],
            fees=fees, board=board, demand=demand, attrition=attrition,
            policies=policies)

    def demand_without_due_date(self, **overrides):
        demand = {
            "channels": ["lcsc_mall", "jlc_smt"],
            "assembly_strategy": "smt",
            "hand_solder_allowed": False,
            "self_supply_allowed": False,
            "budget": {"amount": "1000.00", "currency": "CNY"},
            "channel_preference": ["lcsc_mall", "jlc_smt"],
        }
        demand.update(overrides)
        return demand

    # -- quantity / price -------------------------------------------------
    def test_moq_mpq_rounding_uses_single_formula(self):
        row = S.row(line_id="L1", designators=["R1", "R2", "R3"],
                    qty_per_board=3, lcsc="C1001")
        offer = S.offer(moq=100, mpq=50)
        proc, report, _ = self.plan(self.make([row], [offer]))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        line = report["plan"]["lines"][0]
        # 30 assembled -> orderable = ceil(max(30,100)/50)*50 = 100.
        self.assertEqual(line["purchase_need"], 30)
        self.assertEqual(line["ordered_qty"], 100)
        self.assertEqual(line["overbuy_qty"], 70)
        self.assertEqual(line["orders"][0]["base_qty"], 100)
        self.assertEqual(line["orders"][0]["line_total"], "1.00")

    def test_higher_tier_can_lower_total_within_overbuy_cap(self):
        row = S.row(line_id="L1", designators=["R%d" % (i + 1)
                                              for i in range(10)],
                    qty_per_board=10)
        offer = S.offer(tiers=[
            {"min_qty": 1, "unit_price": "0.1000"},
            {"min_qty": 100, "unit_price": "0.0800"},
        ])
        proc, report, _ = self.plan(self.make([row], [offer], board=9))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        line = report["plan"]["lines"][0]
        order = line["orders"][0]
        # 90 needed -> 100 bought because < 90 * 0.10 = 9.00; total 8.00.
        self.assertEqual(line["purchase_need"], 90)
        self.assertEqual(order["qty"], 100)
        self.assertEqual(order["line_total"], "8.00")
        self.assertEqual(order["overbuy_qty"], 10)
        self.assertEqual(order["selection_reason"],
                         "higher_tier_lower_total")

    def test_overbuy_cap_prevents_unbounded_bulk_build(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer(tiers=[
            {"min_qty": 1, "unit_price": "0.1000"},
            {"min_qty": 1000, "unit_price": "0.0010"},
        ])
        proc, report, _ = self.plan(self.make([row], [offer]))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        order = report["plan"]["lines"][0]["orders"][0]
        # 10 needed, cap = min(50, floor(10*0.2)) = 2 -> 12 max; 1000 is out.
        self.assertEqual(order["qty"], 10)
        self.assertEqual(order["line_total"], "1.00")

    def test_progressive_pricing_total(self):
        row = S.row(line_id="L1", designators=["R1", "R2", "R3"],
                    qty_per_board=3)
        offer = S.offer(price_mode="progressive", tiers=[
            {"min_qty": 1, "max_qty": 9, "unit_price": "1.0000"},
            {"min_qty": 10, "max_qty": 99, "unit_price": "0.8000"},
            {"min_qty": 100, "unit_price": "0.6000"},
        ])
        proc, report, _ = self.plan(self.make([row], [offer], board=5))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        order = report["plan"]["lines"][0]["orders"][0]
        # 15 pcs = 9 * 1.00 + 6 * 0.80 = 13.80
        self.assertEqual(order["qty"], 15)
        self.assertEqual(order["line_total"], "13.80")
        self.assertEqual(order["pricing"]["basis"], "progressive")
        self.assertEqual(order["pricing"]["segments"][0]["units"], 9)
        self.assertEqual(order["pricing"]["segments"][1]["units"], 6)

    def test_per_pack_price_unit_is_converted_to_each(self):
        row = S.row(line_id="L1", designators=["R%d" % (i + 1)
                                              for i in range(10)],
                    qty_per_board=10)
        offer = S.offer(
            price_unit={"kind": "per_pack", "pack_qty": 100},
            tiers=[{"min_qty": 1, "unit_price": "5.0000"}])
        proc, report, _ = self.plan(self.make([row], [offer], board=12))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        order = report["plan"]["lines"][0]["orders"][0]
        # 120 pcs at 5.00 per 100 pcs -> 0.05 each -> 6.00
        self.assertEqual(order["qty"], 120)
        self.assertEqual(order["line_total"], "6.00")

    def test_missing_price_tier_gap_marks_unknown_price(self):
        row = S.row(line_id="L1", designators=["R%d" % (i + 1)
                                              for i in range(10)],
                    qty_per_board=10)
        offer = S.offer(tiers=[
            {"min_qty": 1, "max_qty": 50, "unit_price": "1.0000"},
            {"min_qty": 100, "unit_price": "0.8000"},
        ])
        proc, report, _ = self.plan(self.make([row], [offer], board=6))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        line = report["plan"]["lines"][0]
        self.assertEqual(line["status"], "partial_unknown")
        self.assertEqual(line["ordered_qty"], 0)
        self.assertIn("L1", report["unknowns"]["unknown_price_lines"])
        self.assertEqual(report["status"], "planned_with_unknowns")

    # -- fees / tax / budget ---------------------------------------------
    def test_tax_excluded_offer_with_tax_fee(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer(tiers=[{"min_qty": 1, "unit_price": "1.0000"}],
                        tax_basis="excl")
        fees = [
            S.fee("FEE-SHIP", kind="shipping", amount="0.00"),
            S.fee("FEE-TAX", kind="tax", basis="percent_of_subtotal",
                  rate="0.13", tax_basis="excl", amount=None),
        ]
        proc, report, _ = self.plan(
            self.make([row], [offer], board=10, fees=fees,
                      demand=self.demand_without_due_date()))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        tax = [item for item in report["plan"]["fees"]["known"]
               if item["kind"] == "tax"][0]
        # 10 pcs * 1.00 = 10.00 excl; tax 13% = 1.30
        self.assertEqual(tax["amount"], "1.30")
        self.assertEqual(report["plan"]["budget"]["converted_total"], "11.30")
        self.assertEqual(report["plan"]["budget"]["status"], "within_budget")

    def test_undeclared_shipping_is_unknown_not_zero(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer()
        snap = S.snapshot("SNAP-1", source="official_api_export",
                          truth="official_export")
        proc, report, _ = self.plan(
            self.make([row], [offer], snapshots=[snap], fees=[],
                      demand=self.demand_without_due_date()))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        kinds = {item["kind"] for item in report["plan"]["fees"]["unknown"]}
        self.assertIn("shipping", kinds)
        self.assertEqual(report["plan"]["fees"]["known"], [])
        self.assertEqual(report["plan"]["budget"]["status"],
                         "undetermined_unknowns")
        self.assertEqual(report["status"], "planned_with_unknowns")

    def test_planned_with_evidence_when_all_known(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer()
        snap = S.snapshot("SNAP-1", source="official_api_export",
                          truth="official_export")
        fees = [S.fee("FEE-SHIP", kind="shipping", amount="5.00")]
        proc, report, _ = self.plan(
            self.make([row], [offer], snapshots=[snap], fees=fees,
                      demand=self.demand_without_due_date()))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "planned_with_evidence")
        self.assertFalse(report["limits"]["simulated_data"])
        self.assertEqual(report["plan"]["budget"]["converted_total"], "5.10")

    def test_budget_exceeded_is_unsatisfied(self):
        row = S.row(line_id="L1", designators=["R%d" % (i + 1)
                                               for i in range(10)],
                    qty_per_board=10)
        offer = S.offer(tiers=[{"min_qty": 1, "unit_price": "5.0000"}])
        fees = [S.fee("FEE-SHIP", amount="0.00")]
        demand = self.demand_without_due_date()
        demand["budget"] = {"amount": "10.00", "currency": "CNY"}
        proc, report, _ = self.plan(
            self.make([row], [offer], fees=fees, demand=demand))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["status"], "unsatisfied")
        self.assertIn("budget_exceeded",
                      [item["code"] for item in report["blockers"]])
        self.assertEqual(report["plan"]["budget"]["status"], "exceeded")

    def test_mixed_currency_without_fx_is_reported_separately(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer(currency="USD",
                        tiers=[{"min_qty": 1, "unit_price": "1.2000"}])
        fees = [S.fee("FEE-USD", amount="0.00", currency="USD")]
        proc, report, _ = self.plan(
            self.make([row], [offer], fees=fees, board=5,
                      demand=self.demand_without_due_date()))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["currency"]["order_currencies"], ["USD"])
        self.assertEqual(report["plan"]["budget"]["status"],
                         "undetermined_currency")
        self.assertIsNone(report["plan"]["budget"]["converted_total"])
        self.assertEqual(report["status"], "planned_with_unknowns")

    def test_fx_rate_allows_budget_comparison_without_fake_total(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        cny = S.offer(offer_id="OF-CNY", currency="CNY",
                      tiers=[{"min_qty": 1, "unit_price": "10.0000"}])
        usd = S.offer(offer_id="OF-USD", currency="USD", product_id="C2",
                      tiers=[{"min_qty": 1, "unit_price": "1.2000"}])
        fees = [
            S.fee("FEE-CNY", amount="0.00"),
            S.fee("FEE-USD", amount="0.00", currency="USD"),
        ]
        data = self.make([row], [cny, usd], fees=fees, board=5,
                         demand=self.demand_without_due_date())
        data["fx_rates"] = [{
            "base": "USD", "quote": "CNY", "rate": "7.2000",
            "source": "test fixture", "captured_at": S.CAPTURED,
        }]
        proc, report, _ = self.plan(data)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        order = report["plan"]["orders"][0]
        # 1.20 USD * 7.2 = 8.64 CNY < 10.00 CNY
        self.assertEqual(order["offer_id"], "OF-USD")
        self.assertEqual(report["plan"]["budget"]["converted_total"], "43.20")
        self.assertEqual(report["plan"]["budget"]["status"], "within_budget")

    # -- inventory --------------------------------------------------------
    def test_known_out_of_stock_is_unsatisfied(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer(stock={"qty": 0, "status": "out_of_stock",
                               "reserved": 0, "independent": True,
                               "pool_id": "POOL-1"})
        fees = [S.fee("FEE-SHIP", amount="0.00")]
        proc, report, _ = self.plan(
            self.make([row], [offer], fees=fees))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["status"], "unsatisfied")
        self.assertEqual(report["plan"]["lines"][0]["status"],
                         "uncovered_known")
        self.assertIn("known_shortage",
                      [b["code"] for b in report["plan"]["blockers"]])

    def test_unknown_stock_is_unknown_not_shortage(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer(stock={"qty": None, "status": "unknown",
                               "reserved": 0, "independent": True,
                               "pool_id": "POOL-1"})
        proc, report, _ = self.plan(self.make([row], [offer]))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "planned_with_unknowns")
        line = report["plan"]["lines"][0]
        self.assertEqual(line["status"], "partial_unknown")
        self.assertEqual(line["ordered_qty"], 0)
        self.assertIn("L1", report["unknowns"]["unknown_stock_lines"])

    def test_shared_pool_is_not_double_counted(self):
        board = 10
        rows = [
            S.row(line_id="L1", designators=["R1", "R2"],
                  qty_per_board=2, lcsc="C1001"),
            S.row(line_id="L2", designators=["R3", "R4"],
                  qty_per_board=2, lcsc="C1001"),
        ]
        offer = S.offer(stock={"qty": 30, "status": "in_stock",
                               "reserved": 0, "independent": True,
                               "pool_id": "POOL-SHARED"})
        fees = [S.fee("FEE-SHIP", amount="0.00")]
        proc, report, _ = self.plan(
            self.make(rows, [offer], board=board, fees=fees))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["plan"]["lines"][0]["ordered_qty"], 20)
        self.assertEqual(report["plan"]["lines"][1]["ordered_qty"], 10)
        self.assertEqual(report["plan"]["lines"][1]["shortage_qty"], 10)
        self.assertEqual(sum(line["ordered_qty"]
                             for line in report["plan"]["lines"]), 30)
        self.assertEqual(report["status"], "unsatisfied")

    def test_shared_pool_with_unknown_offer_is_unknown_not_unsatisfied(self):
        rows = [
            S.row(line_id="L1", designators=["R1", "R2"],
                  qty_per_board=2, lcsc="C1001"),
            S.row(line_id="L2", designators=["R3", "R4"],
                  qty_per_board=2, lcsc="C1001"),
        ]
        known = S.offer(offer_id="OF-KNOWN",
                        stock={"qty": 30, "status": "in_stock",
                               "reserved": 0, "independent": True,
                               "pool_id": "POOL-SHARED"})
        unknown = S.offer(
            offer_id="OF-UNKNOWN",
            stock={"qty": None, "status": "unknown", "reserved": 0,
                   "independent": True, "pool_id": "POOL-OTHER"},
            tiers=[{"min_qty": 1, "unit_price": "0.0050"}])
        proc, report, _ = self.plan(self.make(rows, [known, unknown]))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "planned_with_unknowns")
        self.assertEqual(report["plan"]["lines"][1]["ordered_qty"], 10)
        self.assertIn("L2", report["unknowns"]["unknown_stock_lines"])

    def test_reserved_stock_reduces_available(self):
        row = S.row(line_id="L1", designators=["R%d" % (i + 1)
                                               for i in range(10)],
                    qty_per_board=10)
        offer = S.offer(stock={"qty": 5, "status": "in_stock",
                               "reserved": 3, "independent": True,
                               "pool_id": "POOL-1"})
        proc, report, _ = self.plan(self.make([row], [offer], board=1))
        self.assertEqual(proc.returncode, 1)
        line = report["plan"]["lines"][0]
        self.assertEqual(line["orders"][0]["stock_before"], 2)
        self.assertEqual(line["ordered_qty"], 2)
        self.assertEqual(line["shortage_qty"], 8)

    def test_duplicate_pool_quantity_conflict_uses_conservative_minimum(self):
        row = S.row(line_id="L1", designators=["R%d" % (i + 1)
                                               for i in range(10)],
                    qty_per_board=10)
        first = S.offer(offer_id="OF-A", stock={
            "qty": 100, "status": "in_stock", "reserved": 0,
            "independent": False, "pool_id": "POOL-DUP"})
        second = S.offer(offer_id="OF-B", stock={
            "qty": 50, "status": "in_stock", "reserved": 0,
            "independent": False, "pool_id": "POOL-DUP"})
        proc, report, _ = self.plan(self.make([row], [first, second],
                                              board=1))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("pool_quantity_conflict",
                      [finding["code"] for finding in report["warnings"]])
        self.assertEqual(sum(order["qty"]
                             for order in report["plan"]["orders"]), 10)
        self.assertEqual(report["plan"]["lines"][0]["shortage_qty"], 0)
        self.assertEqual(report["plan"]["lines"][0]["ordered_qty"], 10)

    # -- channels ---------------------------------------------------------
    def test_mall_stock_does_not_imply_smt_attachability(self):
        row = S.row(line_id="U1", designators=["U1"], qty_per_board=1,
                    mpn="IC-1", footprint="SOT-23-5", lcsc="C2001")
        mall = S.offer(offer_id="OF-MALL", mpn="IC-1", footprint="SOT-23-5",
                       product_id="C2001")
        fees = [S.fee("FEE-SHIP", amount="0.00")]
        proc, report, _ = self.plan(self.make([row], [mall], fees=fees))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        conclusions = report["plan"]["lines"][0]["channel_conclusions"]
        self.assertEqual(conclusions["mall"]["status"],
                         "purchasable_with_snapshot_evidence")
        self.assertEqual(conclusions["smt"]["status"], "no_smt_offer")

    def test_smt_evidence_is_independent_and_reported(self):
        row = S.row(line_id="U1", designators=["U1"], qty_per_board=1,
                    mpn="IC-1", footprint="SOT-23-5", lcsc="C2001")
        smt = S.offer(
            offer_id="OF-SMT", mpn="IC-1", footprint="SOT-23-5",
            product_id="SMT-IC-1", channel="jlc_smt",
            snapshot_id="SNAP-SMT",
            smt={"attachability": "basic",
                 "evidence": {"source": "test fixture SMT page",
                              "captured_at": S.CAPTURED,
                              "note": "synthetic"}})
        snapshots = [S.snapshot("SNAP-1"),
                     S.snapshot("SNAP-SMT", channel="jlc_smt")]
        fees = [S.fee("FEE-SHIP", amount="0.00"),
                S.fee("FEE-SHIP-SMT", amount="0.00", channel="jlc_smt"),
                S.fee("FEE-SMT", kind="smt_extended_part_fee",
                      channel="jlc_smt", basis="per_part", amount="1.00"),
                S.fee("FEE-SMT-BOARD", kind="smt_board_fee",
                      channel="jlc_smt", basis="per_board", amount="0.00")]
        proc, report, _ = self.plan(self.make([row], [smt],
                                              snapshots=snapshots,
                                              fees=fees))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        line = report["plan"]["lines"][0]
        self.assertEqual(line["channel_conclusions"]["smt"]["status"],
                         "candidate_with_evidence")
        self.assertEqual(line["orders"][0]["channel"], "jlc_smt")

    def test_tht_cannot_be_fulfilled_by_smt_only_channel(self):
        row = S.row(line_id="J1", designators=["J1"], qty_per_board=1,
                    mpn="CONN", footprint="THT-2P", assembly="tht")
        offer = S.offer(mpn="CONN", footprint="THT-2P", channel="jlc_smt",
                        snapshot_id="SNAP-SMT")
        snapshots = [S.snapshot("SNAP-1"),
                     S.snapshot("SNAP-SMT", channel="jlc_smt")]
        demand = self.demand_without_due_date(channels=["jlc_smt"])
        proc, report, _ = self.plan(self.make([row], [offer],
                                              snapshots=snapshots,
                                              demand=demand))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["status"], "unsatisfied")
        self.assertIn("tht_not_supported_by_smt",
                      [b["code"] for b in report["blockers"]])

    def test_channel_strategy_changes_selected_offer(self):
        row = S.row(line_id="U1", designators=["U1"], qty_per_board=1,
                    mpn="IC-1", footprint="SOT-23-5", lcsc="C2001")
        mall = S.offer(offer_id="OF-MALL", mpn="IC-1",
                       footprint="SOT-23-5", product_id="C2001",
                       tiers=[{"min_qty": 1, "unit_price": "2.5000"}])
        smt = S.offer(offer_id="OF-SMT", mpn="IC-1", footprint="SOT-23-5",
                      product_id="SMT-IC-1", channel="jlc_smt",
                      snapshot_id="SNAP-SMT",
                      tiers=[{"min_qty": 1, "unit_price": "2.2000"}],
                      smt={"attachability": "extended",
                           "evidence": {"source": "test fixture",
                                        "captured_at": S.CAPTURED}})
        snapshots = [S.snapshot("SNAP-1"),
                     S.snapshot("SNAP-SMT", channel="jlc_smt")]
        fees = [S.fee("FEE-SHIP", amount="0.00"),
                S.fee("FEE-SHIP-SMT", amount="0.00", channel="jlc_smt"),
                S.fee("FEE-SMT", kind="smt_extended_part_fee",
                      channel="jlc_smt", basis="per_part", amount="0.00"),
                S.fee("FEE-SMT-BOARD", kind="smt_board_fee",
                      channel="jlc_smt", basis="per_board", amount="0.00")]
        data = self.make([row], [mall, smt], snapshots=snapshots,
                         fees=fees, board=5,
                         demand=self.demand_without_due_date())
        proc, report, _ = self.plan(data)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        strategies = {item["strategy"]: item for item in report["strategies"]}
        known_orders = report["plan"]["orders"]
        self.assertEqual(known_orders[0]["offer_id"], "OF-SMT")
        self.assertEqual(strategies["channel_split"]["line_statuses"][0]
                         ["status"], "covered_with_unknowns")
        # channel_split prefers the first preferred channel (mall) at higher
        # known cost; that difference must be visible, not hidden.
        differences = {item["strategy"]: item
                       for item in report["comparison"]["differences"]}
        self.assertIn("channel_split", differences)

    # -- lead time / demand policies -------------------------------------
    def test_late_estimated_lead_time_is_reported(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer(lead_time={"kind": "estimated", "days_min": 8,
                                   "days_max": 10})
        fees = [S.fee("FEE-SHIP", amount="0.00")]
        demand = self.demand_without_due_date(
            due_date="2026-11-01T00:00:00+08:00")
        proc, report, _ = self.plan(self.make([row], [offer], fees=fees,
                                              demand=demand))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        line = report["plan"]["lines"][0]
        self.assertEqual(line["orders"][0]["lead_time"]["status"], "late")
        self.assertEqual(line["lead_time"]["status"], "late")
        self.assertEqual(report["status"], "planned_with_unknowns")

    def test_missing_lead_time_cannot_be_promised_on_time(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer()
        del offer["lead_time"]
        proc, report, _ = self.plan(self.make([row], [offer]))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["plan"]["lines"][0]["lead_time"]["status"],
                         "unknown")
        self.assertIn("missing_lead_time",
                      [finding["code"] for finding in report["warnings"]])

    def test_attrition_and_self_supply_chain(self):
        row = S.row(line_id="L1", designators=["R1", "R2"],
                    qty_per_board=2, consigned=3)
        offer = S.offer(moq=4, mpq=2)
        attrition = {"ratio": "0.25", "fixed": 2, "minimum": 5,
                     "order": ["ratio", "fixed", "minimum"]}
        demand = self.demand_without_due_date(self_supply_allowed=True)
        proc, report, _ = self.plan(
            self.make([row], [offer], board=4, attrition=attrition,
                      demand=demand))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        item = report["demand"][0]
        # 8 assembled; ratio spare ceil(2)=2; +2 fixed = 4; min 5 -> 5.
        self.assertEqual(item["assembled_qty"], 8)
        self.assertEqual(item["attrition"]["ratio_spare"], 2)
        self.assertEqual(item["attrition"]["spare_total"], 5)
        self.assertEqual(item["target_qty"], 13)
        self.assertEqual(item["consigned_applied"], 3)
        self.assertEqual(item["purchase_need"], 10)
        # MOQ 4 / MPQ 2 keeps 10 legal.
        self.assertEqual(report["plan"]["lines"][0]["ordered_qty"], 10)

    def test_self_supply_above_demand_is_clamped(self):
        row = S.row(line_id="L1", designators=["R1", "R2"],
                    qty_per_board=2, consigned=20)
        offer = S.offer()
        demand = self.demand_without_due_date(self_supply_allowed=True)
        proc, report, _ = self.plan(
            self.make([row], [offer], board=4, demand=demand))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        item = report["demand"][0]
        self.assertEqual(item["consigned_applied"], item["target_qty"])
        self.assertEqual(item["purchase_need"], 0)
        self.assertIn("consigned_exceeds_need",
                      [finding["code"] for finding in report["warnings"]])

    def test_identity_conflict_offer_is_not_silently_used(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1,
                    lcsc="C1001")
        wrong_mpn = S.offer(product_id="C1001", mpn="OTHER-MPN",
                            footprint="R0603")
        proc, report, _ = self.plan(self.make([row], [wrong_mpn]))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        line = report["plan"]["lines"][0]
        self.assertEqual(line["ordered_qty"], 0)
        self.assertEqual(line["status"], "partial_unknown")
        self.assertEqual(line["identity_conflicts"][0]["reason"],
                         "supply_id_mpn_conflict")

    def test_max_orders_total_is_enforced(self):
        rows = [
            S.row(line_id="L1", designators=["R1"], qty_per_board=1,
                  mpn="A", lcsc="C1"),
            S.row(line_id="L2", designators=["R2"], qty_per_board=1,
                  mpn="B", lcsc="C2"),
        ]
        offers = [
            S.offer(offer_id="OF-A", mpn="A", product_id="C1",
                    stock=100),
            S.offer(offer_id="OF-B", mpn="B", product_id="C2",
                    stock=100),
        ]
        demand = self.demand_without_due_date()
        demand["split_policy"] = {"allow_multi_offer": True,
                                  "max_orders_per_line": 3,
                                  "max_orders_total": 1}
        proc, report, _ = self.plan(
            self.make(rows, offers, board=1, demand=demand,
                      fees=[S.fee("FEE-SHIP", amount="0.00")]))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["status"], "unsatisfied")
        codes = [blocker["code"] for blocker in report["blockers"]]
        self.assertIn("max_orders_total_reached", codes)
        statuses = {line["line_id"]: line["status"]
                    for line in report["plan"]["lines"]}
        self.assertIn(statuses["L1"], ("covered", "covered_with_unknowns"))
        self.assertEqual(statuses["L2"], "uncovered_known")

    def test_budget_exceeded_lists_affected_lines(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        offer = S.offer(tiers=[{"min_qty": 1, "unit_price": "5.0000"}])
        demand = self.demand_without_due_date()
        demand["budget"] = {"amount": "10.00", "currency": "CNY"}
        proc, report, _ = self.plan(
            self.make([row], [offer], fees=[S.fee("FEE-SHIP",
                                                  amount="0.00")],
                      demand=demand))
        self.assertEqual(proc.returncode, 1)
        lines = report["plan"]["budget"]["lines_by_known_cost"]
        self.assertEqual(lines[0]["line_id"], "L1")
        self.assertEqual(lines[0]["amount"], "50.00")

    def test_snapshot_channel_is_required(self):
        data = self.make([S.row(line_id="L1", designators=["R1"],
                                qty_per_board=1)],
                         [S.offer()])
        del data["supply_snapshots"][0]["channel"]
        proc, report, _ = self.run_doc(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing_text", str(report))

    def test_per_pack_price_requires_pack_quantity(self):
        data = self.make([S.row(line_id="L1", designators=["R1"],
                                qty_per_board=1)],
                         [S.offer(price_unit={"kind": "per_pack"})])
        proc, report, _ = self.run_doc(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing_pack_qty", str(report))

    def test_search_step_budget_exhaustion_is_explicit(self):
        rows = [
            S.row(line_id="L1", designators=["R1"], qty_per_board=1,
                  mpn="A", lcsc="C1"),
            S.row(line_id="L2", designators=["R2"], qty_per_board=1,
                  mpn="B", lcsc="C2"),
        ]
        offers = [
            S.offer(offer_id="OF-A", mpn="A", product_id="C1", stock=100),
            S.offer(offer_id="OF-B", mpn="B", product_id="C2", stock=100),
        ]
        policies = {
            "attrition": {"ratio": "0", "fixed": 0, "minimum": 0},
            "overbuy": {"max_extra_qty": 50, "max_extra_ratio": "0.20",
                        "allow_price_break_extra": True},
            "order_policy": "moq_mpq",
            "search": {"max_search_steps": 1},
            "substitution": {"enabled": False,
                             "allowed_grades": ["exact_identity"]},
            "channel_preference": ["lcsc_mall"],
        }
        demand = self.demand_without_due_date(channels=["lcsc_mall"])
        data = S.input_doc(rows, offers,
                           snapshots=[S.snapshot("SNAP-1")],
                           fees=[S.fee("FEE-SHIP", amount="0.00")],
                           board=1, demand=demand, policies=policies)
        proc, report, _ = self.plan(data)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "planned_with_unknowns")
        self.assertTrue(report["plan"]["bounded_search"][
            "search_budget_exhausted"])
        self.assertEqual(report["plan"]["bounded_search"]["search_steps"], 1)
        statuses = {line["line_id"]: line["status"]
                    for line in report["plan"]["lines"]}
        self.assertEqual(statuses["L2"], "partial_unknown")
        self.assertTrue(any(reason["code"] == "search_budget_exhausted"
                            for line in report["plan"]["lines"]
                            for reason in line["unknown_reasons"]))

    def test_plan_single_strategy_flag(self):
        row = S.row(line_id="L1", designators=["R1"], qty_per_board=1)
        proc, report, _ = self.plan(
            self.make([row], [S.offer()]), "--strategy", "known_cost")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(report["strategies"]), 1)
        self.assertEqual(report["preferred_strategy"], "known_cost")


if __name__ == "__main__":
    unittest.main()
