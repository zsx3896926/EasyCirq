import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
HOOK = SCRIPTS / "sch_delivery_hook.py"
GATE = SCRIPTS / "sch_delivery_check.py"
SETTINGS_GEN = SCRIPTS / "sch_task_settings.py"

sys.path.insert(0, str(SCRIPTS))
import sch_text_audit as _text_audit  # noqa: E402


def frame_plan():
    return {"schema": "design-engine-sch-frame-plan/v1", "frames": [
        {"id": "a", "order": 1, "title": "CODEC", "purpose": "音频",
         "title_text_id": "t1", "purpose_text_id": "p1"}]}


def text_source(overlap=False):
    items = [{"id": "a", "bbox": [0, 0, 10, 10], "parentId": "U1"},
             {"id": "b", "bbox": [20, 0, 30, 10], "parentId": "U1"}]
    if overlap:
        items[1]["bbox"] = [5, 0, 15, 10]
    return {"count": 2, "unmeasured": [],
            "coverage": dict.fromkeys(_text_audit.TEXT_CLASSES, True),
            "items": items}


def style_input(bad=False):
    d = {"schema": "easycirq-sch-style-input/v1",
         "sheet": {"width_mm": 297, "height_mm": 210, "size": "A4"},
         "zones": [
             {"id": "a", "title": "CODEC", "order": 1, "purpose": "音频",
              "rect_mm": [10, 10, 120, 80], "borderColor": "#00B3B3", "titleSize": 14},
             {"id": "b", "title": "PA", "order": 2, "purpose": "功放",
              "rect_mm": [150, 110, 120, 80], "borderColor": "#C800C8", "titleSize": 14}],
         "texts": [],
         "titleBlock": {"project": "ESP32", "version": "V0.4", "date": "2026-10-28",
                        "sheet": "Schematic2", "page": "3/5", "size": "A4"}}
    if bad:
        d["zones"][0]["title"] = ""
    return d


class StopHook(unittest.TestCase):
    def run_hook(self, evidence, stdin=None, extra=None):
        args = [sys.executable, str(HOOK), "--evidence", str(evidence)]
        if extra:
            args += extra
        r = subprocess.run(args, input=stdin, capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout.strip()

    def test_block_when_evidence_missing(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = self.run_hook(Path(d) / "delivery.json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["decision"], "block")

    def test_allow_when_verdict_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "delivery.json"
            p.write_text(json.dumps({"schema": "x", "verdict": "pass"}), encoding="utf-8")
            code, out = self.run_hook(p)
            self.assertEqual(out, "")

    def test_allow_when_stop_hook_active(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = self.run_hook(Path(d) / "delivery.json",
                                      stdin=json.dumps({"stop_hook_active": True}))
            self.assertEqual(out, "")

    def _inputs(self, d, bad=False):
        d = Path(d)
        (d / "frame-plan.json").write_text(json.dumps(frame_plan()), encoding="utf-8")
        (d / "text-audit.json").write_text(json.dumps(text_source()), encoding="utf-8")
        (d / "style-input.json").write_text(json.dumps(style_input(bad=bad)), encoding="utf-8")
        return ["--gate", str(GATE),
                "--frame-plan", str(d / "frame-plan.json"),
                "--text-audit", str(d / "text-audit.json"),
                "--style", str(d / "style-input.json"),
                "--skip-layout", "--require-style"]

    def test_trusted_recheck_ignores_fake_pass(self):
        # A fake PASS evidence file must not help: the actual style input is bad,
        # so the hook's re-check blocks and overwrites the evidence.
        with tempfile.TemporaryDirectory() as d:
            evidence = Path(d) / "delivery.json"
            evidence.write_text(json.dumps({"verdict": "pass", "fake": True}), encoding="utf-8")
            extra = self._inputs(d, bad=True)
            code, out = self.run_hook(evidence, extra=extra)
            self.assertEqual(json.loads(out)["decision"], "block")
            self.assertEqual(json.loads(evidence.read_text(encoding="utf-8"))["verdict"], "blocked")

    def test_trusted_recheck_passes_real_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            evidence = Path(d) / "delivery.json"
            extra = self._inputs(d, bad=False)
            code, out = self.run_hook(evidence, extra=extra)
            self.assertEqual(out, "")
            self.assertEqual(json.loads(evidence.read_text(encoding="utf-8"))["verdict"], "pass")


class SettingsGen(unittest.TestCase):
    def test_generates_trusted_recheck_stop_hook(self):
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            r = subprocess.run(
                [sys.executable, str(SETTINGS_GEN), "--workdir", str(wd),
                 "--out", "settings.json"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0)
            settings = json.loads((wd / "settings.json").read_text(encoding="utf-8"))
            cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
            for token in ("sch_delivery_hook.py", "--gate", "sch_delivery_check.py",
                          "frame-plan.json", "layout.json", "text-audit.json",
                          "style-input.json", "--require-style"):
                self.assertIn(token, cmd)


if __name__ == "__main__":
    unittest.main()
