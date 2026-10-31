import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
GATE = SCRIPTS / "sch_kpi.py"
DEFINITION = ROOT / "metrics" / "schematic-kpi.v1.json"

sys.path.insert(0, str(SCRIPTS))
import sch_kpi  # noqa: E402

CLEAN = {
    "connectivity": {"floating_pins": 0, "single_node_nets": 0,
                     "bus_members_missing": 0, "diff_pair_mismatch": 0,
                     "duplicate_net_names": 0, "auto_net_residue": 0},
    "layout": {"cross_zone_crossings": 0, "overlaps": 0,
               "unowned_visible_text": 0},
    "wire": {"longest_wire_mm": 40.0, "avg_wire_mm": 20.0,
             "short_lead_ratio": 0.8, "zone_balance_deviation": 0.1,
             "cross_zone_crossings": 0},
    "text": {"overlaps": 0, "unowned_visible_text": 0, "duplicate_net_text": 0,
             "port_mismatch": 0, "duplicate_net_names": 0, "auto_net_residue": 0},
    "quality": {"zone_balance_deviation": 0.1},
    "erc": {"erc_violations": 0},
    "pinplan": {"pin_mux_conflicts": 0},
    "power": {"decap_missing": 0},
    "identity": {"bom_mapping_missing": 0, "footprint_mismatch": 0},
    "netlist": {"netlist_diff": 0},
    "readback": {"readback_diff": 0},
}


def payload(**overrides):
    checks = []
    for cid, metrics in CLEAN.items():
        metrics = dict(metrics)
        metrics.update(overrides.pop(cid, {}))
        checks.append({"id": cid, "tool": sch_kpi.DEFAULTS["sources"][cid]["tool"],
                       "verdict": "pass", "metrics": metrics,
                       "findings": [], "evidence": f"reports/{cid}.json"})
    data = {"schema": sch_kpi.SCHEMA_INPUT, "project": "p", "page": "Sheet1",
            "round": 1, "profile": "default", "checks": checks}
    data.update(overrides)
    return data


class KpiGate(unittest.TestCase):
    def test_template_is_valid_input(self):
        out = subprocess.run([sys.executable, str(GATE), "--template"],
                             capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["schema"], sch_kpi.SCHEMA_INPUT)
        self.assertEqual([c["id"] for c in data["checks"]], sch_kpi.CHECK_IDS)

    def test_clean_single_round_passes_but_cannot_apply_yet(self):
        report = sch_kpi.evaluate(payload())
        self.assertEqual(report["verdict"], "PASS")
        self.assertFalse(report["stability"]["apply_allowed"])
        self.assertEqual(report["blockers"], [])
        self.assertEqual(len(report["kpis"]), 15)

    def test_two_consecutive_rounds_allow_apply(self):
        with tempfile.TemporaryDirectory() as d:
            history = Path(d) / "h.jsonl"
            first = sch_kpi.evaluate(payload(history=str(history)))
            with open(history, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "schema": sch_kpi.SCHEMA_HISTORY, "ts": "t", "project": "p",
                    "page": "Sheet1", "round": 1, "verdict": "PASS",
                    "kpis": {r["id"]: r["status"] for r in first["kpis"]},
                    "values": {}, "blockers": []}, ensure_ascii=False) + "\n")
            second = sch_kpi.evaluate(payload(history=str(history), round=2))
            self.assertEqual(second["verdict"], "PASS")
            self.assertTrue(second["stability"]["apply_allowed"])
            self.assertEqual(second["stability"]["rounds_pass"], 2)

    def test_hard_violation_blocks(self):
        report = sch_kpi.evaluate(payload(connectivity={"floating_pins": 3}))
        self.assertEqual(report["verdict"], "BLOCKED")
        self.assertEqual([b["kpi"] for b in report["blockers"]], ["unconnected"])
        row = next(r for r in report["kpis"] if r["id"] == "unconnected")
        self.assertEqual(row["value"], 3)
        self.assertEqual(row["status"], "fail")

    def test_missing_evidence_blocks_instead_of_passing(self):
        data = payload()
        data["checks"] = [c for c in data["checks"] if c["id"] != "readback"]
        report = sch_kpi.evaluate(data)
        self.assertEqual(report["verdict"], "BLOCKED")
        self.assertIn("readback", [b["kpi"] for b in report["blockers"]])
        row = next(r for r in report["kpis"] if r["id"] == "readback")
        self.assertEqual(row["status"], "missing")

    def test_blocked_checker_verdict_blocks(self):
        data = payload()
        next(c for c in data["checks"] if c["id"] == "erc")["verdict"] = "error"
        report = sch_kpi.evaluate(data)
        self.assertEqual(report["verdict"], "BLOCKED")
        self.assertIn("erc", [b["kpi"] for b in report["blockers"]])

    def test_fail_verdict_still_reports_measured_value(self):
        data = payload()
        check = next(c for c in data["checks"] if c["id"] == "erc")
        check["verdict"] = "fail"
        check["metrics"] = {"erc_violations": 2}
        report = sch_kpi.evaluate(data)
        row = next(r for r in report["kpis"] if r["id"] == "erc")
        self.assertEqual(row["value"], 2)
        self.assertEqual(row["status"], "fail")
        self.assertEqual(report["verdict"], "BLOCKED")

    def test_soft_kpi_miss_is_review_only(self):
        report = sch_kpi.evaluate(payload(wire={"longest_wire_mm": 130.0}))
        self.assertEqual(report["verdict"], "REVIEW")
        self.assertEqual(report["blockers"][0]["kpi"], "wire_length")

    def test_profile_changes_soft_threshold(self):
        strict = payload(profile="dense-digital", wire={"longest_wire_mm": 100.0})
        self.assertEqual(sch_kpi.evaluate(strict)["verdict"], "REVIEW")
        loose = payload(profile="power", wire={"longest_wire_mm": 100.0})
        self.assertEqual(sch_kpi.evaluate(loose)["verdict"], "PASS")

    def test_pin_plan_duplicate_is_a_hard_failure(self):
        data = payload()
        data["checks"].append({
            "id": "pinplan", "tool": "pin_plan_check.py", "verdict": "pass",
            "metrics": {},
            "findings": [{"code": "DUPLICATE_RESOURCE_PIN", "severity": "error",
                          "message": "PA0 used twice"}],
            "evidence": "reports/pinplan.json"})
        report = sch_kpi.evaluate(data)
        self.assertEqual(report["verdict"], "BLOCKED")
        row = next(r for r in report["kpis"] if r["id"] == "pin_mux")
        self.assertEqual(row["value"], 1)
        self.assertEqual(row["status"], "fail")

    def test_pin_plan_warning_only_is_not_a_hard_failure(self):
        data = payload()
        data["checks"].append({
            "id": "pinplan", "tool": "pin_plan_check.py", "verdict": "pass",
            "metrics": {},
            "findings": [{"code": "NO_PINS", "severity": "warning",
                          "message": "pins 为空"}],
            "evidence": "reports/pinplan.json"})
        report = sch_kpi.evaluate(data)
        row = next(r for r in report["kpis"] if r["id"] == "pin_mux")
        self.assertEqual(row["value"], 0)
        self.assertEqual(row["status"], "pass")

    def test_not_applicable_kpi_does_not_block(self):
        data = payload()
        next(c for c in data["checks"] if c["id"] == "pinplan")["verdict"] = "n/a"
        report = sch_kpi.evaluate(data)
        self.assertEqual(report["verdict"], "PASS")
        row = next(r for r in report["kpis"] if r["id"] == "pin_mux")
        self.assertEqual(row["status"], "na")
        self.assertNotIn("pin_mux", [b["kpi"] for b in report["blockers"]])

    def test_advisory_kpi_does_not_block(self):
        report = sch_kpi.evaluate(payload())
        self.assertEqual(report["verdict"], "PASS")
        row = next(r for r in report["kpis"] if r["id"] == "readability")
        self.assertTrue(row["advisory"])
        self.assertIn("readability", [a["kpi"] for a in report["advisory"]])

    def test_hard_kpi_cannot_be_re_limited(self):
        with self.assertRaises(ValueError):
            sch_kpi._apply_profile(sch_kpi.DEFAULTS, "default", {"unconnected": 5})

    def test_findings_are_counted_when_metrics_absent(self):
        data = payload()
        check = next(c for c in data["checks"] if c["id"] == "erc")
        check["metrics"] = {}
        check["findings"] = [
            {"severity": "error", "code": "erc_violation", "message": "U1 output clash"},
            {"severity": "error", "code": "erc_violation", "message": "U2 no driver"},
        ]
        report = sch_kpi.evaluate(data)
        row = next(r for r in report["kpis"] if r["id"] == "erc")
        self.assertEqual(row["value"], 2)
        self.assertEqual(report["verdict"], "BLOCKED")

    def test_regression_against_previous_round(self):
        with tempfile.TemporaryDirectory() as d:
            history = Path(d) / "h.jsonl"
            baseline = sch_kpi.evaluate(payload(history=str(history)))
            with open(history, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "schema": sch_kpi.SCHEMA_HISTORY, "ts": "t", "project": "p",
                    "page": "Sheet1", "round": 1, "verdict": "PASS",
                    "kpis": {r["id"]: r["status"] for r in baseline["kpis"]},
                    "values": {}, "blockers": []}, ensure_ascii=False) + "\n")
            worse = sch_kpi.evaluate(payload(history=str(history), round=2,
                                             erc={"erc_violations": 1}))
            self.assertEqual(worse["verdict"], "BLOCKED")
            self.assertTrue(worse["stability"]["regression"])
            self.assertIn("erc", worse["stability"]["new_failures"])

    def test_definition_file_matches_builtin_defaults(self):
        data = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], sch_kpi.SCHEMA_DEF)
        builtin = {k["id"]: k for k in sch_kpi.DEFAULTS["kpis"]}
        self.assertEqual([k["id"] for k in data["kpis"]], [k["id"] for k in sch_kpi.DEFAULTS["kpis"]])
        for kpi in data["kpis"]:
            ref = builtin[kpi["id"]]
            for field in ("no", "title", "kind", "aggregate", "direction", "limit", "unit"):
                self.assertEqual(kpi[field], ref[field], f"{kpi['id']}.{field}")
            self.assertEqual(kpi["reads"], ref["reads"], kpi["id"])
        self.assertEqual(data["profiles"], sch_kpi.DEFAULTS["profiles"])

    def test_cli_exit_codes_and_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            inp = Path(d) / "in.json"
            out = Path(d) / "rep.json"
            md = Path(d) / "rep.md"
            inp.write_text(json.dumps(payload()), encoding="utf-8")
            run = subprocess.run([sys.executable, str(GATE), "--input", str(inp),
                                  "--out", str(out), "--md", str(md), "--json"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["verdict"], "PASS")
            self.assertTrue(out.is_file())
            table = md.read_text(encoding="utf-8")
            self.assertIn("| 1 |", table)
            self.assertIn("PASS", table)

            bad = Path(d) / "bad.json"
            bad.write_text(json.dumps(payload(connectivity={"floating_pins": 1})),
                           encoding="utf-8")
            run = subprocess.run([sys.executable, str(GATE), "--input", str(bad)],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 2)

    def test_check_report_attachment(self):
        with tempfile.TemporaryDirectory() as d:
            inp = Path(d) / "in.json"
            data = payload()
            data["checks"] = [c for c in data["checks"] if c["id"] != "erc"]
            inp.write_text(json.dumps(data), encoding="utf-8")
            erc = Path(d) / "erc.json"
            erc.write_text(json.dumps({"verdict": "pass",
                                       "metrics": {"erc_violations": 0}}),
                           encoding="utf-8")
            run = subprocess.run([sys.executable, str(GATE), "--input", str(inp),
                                  "--check", f"erc={erc}", "--json"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
