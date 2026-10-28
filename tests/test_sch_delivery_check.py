import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
VERIFIER = SCRIPTS / "sch_delivery_check.py"

sys.path.insert(0, str(SCRIPTS))
import sch_text_audit as _text_audit  # noqa: E402


def frame(fid, order, title, purpose, tid, pid):
    return {"id": fid, "order": order, "title": title, "purpose": purpose,
            "title_text_id": tid, "purpose_text_id": pid}


def frame_plan(frames):
    return {"schema": "design-engine-sch-frame-plan/v1", "frames": frames}


def text_source(overlap=False):
    items = [
        {"id": "a", "bbox": [0, 0, 10, 10], "parentId": "U1"},
        {"id": "b", "bbox": [20, 0, 30, 10], "parentId": "U1"},
    ]
    if overlap:
        items[1]["bbox"] = [5, 0, 15, 10]
    return {"count": len(items), "unmeasured": [],
            "coverage": dict.fromkeys(_text_audit.TEXT_CLASSES, True),
            "items": items}


class DeliveryGate(unittest.TestCase):
    def invoke(self, folder, args):
        r = subprocess.run(
            [sys.executable, str(VERIFIER), *args], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8")
        return r.returncode, json.loads(r.stdout)

    def test_pass_with_complete_frame_and_clear_text(self):
        with tempfile.TemporaryDirectory() as d:
            fp = Path(d) / "frame.json"; fp.write_text(json.dumps(frame_plan([
                frame("a", 1, "输入", "端子与保护", "t1", "p1"),
                frame("b", 2, "通道", "LED 与开关", "t2", "p2")])), encoding="utf-8")
            ta = Path(d) / "text.json"; ta.write_text(json.dumps(text_source()), encoding="utf-8")
            code, rep = self.invoke(d, ["--frame-plan", str(fp), "--text-audit", str(ta), "--skip-layout", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(rep["verdict"], "pass")

    def test_blocked_on_missing_purpose(self):
        with tempfile.TemporaryDirectory() as d:
            fp = Path(d) / "frame.json"; fp.write_text(json.dumps(frame_plan([
                frame("a", 1, "输入", "端子与保护", "t1", "")])), encoding="utf-8")
            ta = Path(d) / "text.json"; ta.write_text(json.dumps(text_source()), encoding="utf-8")
            code, rep = self.invoke(d, ["--frame-plan", str(fp), "--text-audit", str(ta), "--skip-layout", "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(rep["verdict"], "blocked")

    def test_review_on_text_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            fp = Path(d) / "frame.json"; fp.write_text(json.dumps(frame_plan([
                frame("a", 1, "输入", "端子与保护", "t1", "p1")])), encoding="utf-8")
            ta = Path(d) / "text.json"; ta.write_text(json.dumps(text_source(overlap=True)), encoding="utf-8")
            code, rep = self.invoke(d, ["--frame-plan", str(fp), "--text-audit", str(ta), "--skip-layout", "--json"])
            self.assertEqual(code, 1)
            self.assertEqual(rep["verdict"], "review")

    def test_blocked_without_layout_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            fp = Path(d) / "frame.json"; fp.write_text(json.dumps(frame_plan([
                frame("a", 1, "输入", "端子与保护", "t1", "p1")])), encoding="utf-8")
            ta = Path(d) / "text.json"; ta.write_text(json.dumps(text_source()), encoding="utf-8")
            code, rep = self.invoke(d, ["--frame-plan", str(fp), "--text-audit", str(ta), "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(rep["verdict"], "blocked")
            self.assertTrue(any("layout snapshot" in g for g in rep["gaps"]))


if __name__ == "__main__":
    unittest.main()

