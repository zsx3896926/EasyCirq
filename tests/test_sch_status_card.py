import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
STATUS = SCRIPTS / "sch_status.py"
CARD = SCRIPTS / "sch_delivery_card.py"

sys.path.insert(0, str(SCRIPTS))
import sch_delivery_card as card_mod  # noqa: E402
import sch_status as status_mod  # noqa: E402


def gate_file(folder, expires_in_minutes=30, verdict="PASS", apply_allowed=True):
    path = Path(folder) / "gate.json"
    expires = (datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes))
    path.write_text(json.dumps({
        "schema": "easycirq-gate/v1", "project": "P", "page": "P1",
        "verdict": verdict, "apply_allowed": apply_allowed,
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }), encoding="utf-8")
    return path


def report(verdict, fail=(), missing=(), advisory=()):
    kpis = [{"no": i + 1, "id": k, "status": "fail"} for i, k in enumerate(fail)]
    kpis += [{"no": 20 + i, "id": k, "status": "missing"} for i, k in enumerate(missing)]
    kpis += [{"no": 40 + i, "id": k, "status": "fail", "advisory": True}
             for i, k in enumerate(advisory)]
    kpis.append({"no": 99, "id": "ok", "status": "pass"})
    blockers = [{"kpi": k, "reason": "r"} for k in fail]
    blockers += [{"kpi": k, "reason": "缺证据"} for k in missing]
    return {"project": "P", "page": "P1", "verdict": verdict,
            "kpis": kpis, "blockers": blockers}


class Status(unittest.TestCase):
    def test_not_measured(self):
        result = status_mod.analyze(None)
        self.assertEqual(result["state"], "not_measured")

    def test_blocked_when_a_check_fails(self):
        result = status_mod.analyze(report("BLOCKED", fail=["unconnected"],
                                           missing=["pin_mux"]), None)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual([b["kpi"] for b in result["blockers"]], ["unconnected"])
        self.assertEqual([m["kpi"] for m in result["missing"]], ["pin_mux"])

    def test_incomplete_when_only_evidence_is_missing(self):
        result = status_mod.analyze(report("BLOCKED", missing=["pin_mux", "readback"]), None)
        self.assertEqual(result["state"], "incomplete")
        self.assertEqual(result["blockers"], [])

    def test_ready_needs_a_live_gate(self):
        with tempfile.TemporaryDirectory() as d:
            gate = gate_file(d)
            result = status_mod.analyze(report("PASS"), gate)
            self.assertEqual(result["state"], "ready_to_write")

    def test_expired_gate_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            gate = gate_file(d, expires_in_minutes=-5)
            result = status_mod.analyze(report("PASS"), gate)
            self.assertEqual(result["state"], "gate_stale")


class DeliveryCard(unittest.TestCase):
    def test_ready_card(self):
        with tempfile.TemporaryDirectory() as d:
            gate = gate_file(d)
            result = card_mod.analyze(report("PASS"), gate)
            self.assertEqual(result["state"], "ready")
            self.assertIn("可以打样", result["headline"])

    def test_blocked_card_keeps_missing_separate(self):
        result = card_mod.analyze(
            report("BLOCKED", fail=["unconnected"], missing=["bom_map"]),
            None)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual([b["kpi"] for b in result["blockers"]], ["unconnected"])
        self.assertEqual([m["kpi"] for m in result["missing"]], ["bom_map"])

    def test_incomplete_card(self):
        result = card_mod.analyze(report("BLOCKED", missing=["bom_map"]), None)
        self.assertEqual(result["state"], "incomplete")

    def test_pass_without_gate_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            gate = gate_file(d, expires_in_minutes=-1)
            result = card_mod.analyze(report("PASS"), gate)
            self.assertEqual(result["state"], "gate_stale")

    def test_every_plain_label_has_advice(self):
        for kpi in status_mod.PLAIN:
            self.assertIn(kpi, card_mod.ADVICE, kpi)


class Cli(unittest.TestCase):
    def test_card_cli_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "kpi.json"
            path.write_text(json.dumps(report("BLOCKED", fail=["unconnected"])),
                            encoding="utf-8")
            run = subprocess.run([sys.executable, str(CARD), "--kpi-report", str(path)],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 1)
            self.assertIn("还不能打样", run.stdout)

    def test_status_cli_ready(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "kpi.json"
            path.write_text(json.dumps(report("PASS")), encoding="utf-8")
            gate = gate_file(d)
            run = subprocess.run([sys.executable, str(STATUS), "--kpi-report", str(path),
                                  "--gate", str(gate)],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("可以写入", run.stdout)


if __name__ == "__main__":
    unittest.main()
