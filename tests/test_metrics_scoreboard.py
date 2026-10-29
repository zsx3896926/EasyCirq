import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "metrics_scoreboard.py"
REFERENCE = ROOT / "easycirq" / "assets" / "style-reference" / "esp32-schematic.png"

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def report(fits=3, blocks=3, overlaps=0, zones_ok=True, export_ok=True,
           wires_total=30, wires_ok=28, project="demo"):
    return {
        "project": project,
        "page": "page-1",
        "blocks": [{"wires": {"total": wires_total, "ok": wires_ok,
                              "failed": wires_total - wires_ok}}],
        "metrics": {"blocks": blocks, "fits": fits, "overlaps": overlaps,
                    "wires_total": wires_total, "wires_ok": wires_ok,
                    "wires_failed": wires_total - wires_ok},
        "zones_reapplied": 0 if zones_ok else 1,
        "export": 0 if export_ok else 1,
    }


def style_input(border_color="#00B3B3"):
    return {
        "schema": "easycirq-sch-style-input/v1",
        "sheet": {"width_mm": 297, "height_mm": 210, "size": "A4"},
        "zones": [
            {"id": "a", "title": "CODEC", "order": 1, "purpose": "音频编解码",
             "rect_mm": [10, 10, 120, 80], "borderColor": border_color,
             "titleSize": 14},
            {"id": "b", "title": "PA", "order": 2, "purpose": "功率放大",
             "rect_mm": [150, 110, 120, 80], "borderColor": "#C800C8",
             "titleSize": 14},
        ],
        "texts": [
            {"id": "t1", "role": "zone_title", "text": "CODEC", "size": 14,
             "color": "#000000", "bbox_mm": [12, 12, 20, 4]},
            {"id": "t2", "role": "net_label", "text": "AUD_3V3", "size": 9,
             "color": "#CC0000", "bbox_mm": [20, 40, 14, 2]},
        ],
        "titleBlock": {"project": "ESP32-S31", "version": "V0.4",
                       "date": "2026-10-28", "sheet": "Schematic2",
                       "page": "3/5", "size": "A4"},
    }


class Scoreboard(unittest.TestCase):
    def run_tool(self, reports, style_inputs=None, exports=None,
                 style_dir_exists=True, export_dir_exists=True):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            reports_dir = root / "reports"
            reports_dir.mkdir()
            for i, rep in enumerate(reports):
                (reports_dir / ("r%d.report.json" % i)).write_text(
                    json.dumps(rep), encoding="utf-8")
            args = [sys.executable, str(TOOL), "--reports", str(reports_dir)]
            if style_inputs is not None or not style_dir_exists:
                style_dir = root / "style"
                if style_dir_exists:
                    style_dir.mkdir()
                    for project, data in (style_inputs or {}).items():
                        (style_dir / ("%s.style.json" % project)).write_text(
                            json.dumps(data), encoding="utf-8")
                args += ["--style-input-dir", str(style_dir)]
            if exports is not None or not export_dir_exists:
                export_dir = root / "exports"
                if export_dir_exists:
                    export_dir.mkdir()
                    for project, candidate in (exports or {}).items():
                        shutil.copyfile(candidate, export_dir / ("%s.png" % project))
                args += ["--export-dir", str(export_dir)]
            out = root / "scoreboard.json"
            args += ["--out", str(out)]
            r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
            data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            return r.returncode, r.stdout, data

    @staticmethod
    def row(data, project="demo"):
        return next(r for r in data["rows"] if r["project"] == project)

    def test_all_pass(self):
        code, stdout, data = self.run_tool([report(), report(project="demo2")])
        self.assertEqual(code, 0)
        self.assertEqual(data["reports"], 2)
        self.assertEqual(data["passed"], 2)
        self.assertIn("28/30", stdout)

    def test_mixed_review_and_fail_exit(self):
        code, stdout, data = self.run_tool([report(), report(overlaps=2)])
        self.assertEqual(code, 1)
        self.assertEqual(data["passed"], 1)
        self.assertTrue(any(r["verdict"] == "review" for r in data["rows"]))

    def test_fit_shortfall_marks_review(self):
        code, stdout, data = self.run_tool([report(fits=2, blocks=3)])
        self.assertEqual(data["rows"][0]["verdict"], "review")

    def test_style_pass_added_and_markdown_column(self):
        code, stdout, data = self.run_tool(
            [report()], style_inputs={"demo": style_input()})
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertEqual(row["verdict"], "pass")  # base verdict unchanged
        self.assertEqual(row["style_verdict"], "pass")
        self.assertEqual(row["style_score"], 100)
        self.assertEqual(row["style_problems"], [])
        self.assertIn("style score", stdout)
        self.assertIn("| pass |", stdout)

    def test_style_review_is_advisory(self):
        code, stdout, data = self.run_tool(
            [report()], style_inputs={"demo": style_input(border_color="#123456")})
        self.assertEqual(code, 0)  # base row still passes, exit code unaffected
        row = self.row(data)
        self.assertEqual(row["verdict"], "pass")
        self.assertEqual(row["style_verdict"], "review")
        self.assertEqual(row["style_score"], 96)
        self.assertEqual(len(row["style_problems"]), 1)
        self.assertEqual(row["style_problems"][0]["severity"], "review")

    def test_style_invalid_input_blocked_without_crash(self):
        code, stdout, data = self.run_tool(
            [report()], style_inputs={"demo": {"schema": "wrong"}})
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertEqual(row["verdict"], "pass")
        self.assertEqual(row["style_verdict"], "blocked")
        self.assertEqual(row["style_score"], 0)
        self.assertEqual(len(row["style_problems"]), 1)

    def test_missing_style_file_leaves_null(self):
        code, stdout, data = self.run_tool(
            [report(project="demo"), report(project="other")],
            style_inputs={"demo": style_input()})
        self.assertEqual(code, 0)
        self.assertEqual(self.row(data, "demo")["style_verdict"], "pass")
        missing = self.row(data, "other")
        self.assertIsNone(missing["style_verdict"])
        self.assertIsNone(missing["style_score"])
        self.assertIsNone(missing["style_problems"])
        self.assertEqual(missing["verdict"], "pass")

    def test_missing_style_dir_does_not_crash(self):
        code, stdout, data = self.run_tool([report()], style_dir_exists=False)
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertIsNone(row["style_verdict"])
        self.assertIsNone(row["style_score"])
        self.assertIsNone(row["style_problems"])
        self.assertNotIn("style score", stdout)

    def test_no_optional_dirs_keeps_legacy_columns(self):
        code, stdout, data = self.run_tool([report()])
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertNotIn("style_verdict", row)
        self.assertNotIn("visual_verdict", row)
        self.assertNotIn("| style |", stdout)
        self.assertNotIn("| similarity |", stdout)

    def test_missing_visual_png_leaves_null(self):
        code, stdout, data = self.run_tool([report()], exports={})
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertIsNone(row["visual_verdict"])
        self.assertIsNone(row["visual_similarity"])
        self.assertNotIn("similarity", stdout)

    def test_missing_export_dir_does_not_crash(self):
        code, stdout, data = self.run_tool([report()], export_dir_exists=False)
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertIsNone(row["visual_verdict"])
        self.assertIsNone(row["visual_similarity"])

    @unittest.skipUnless(HAVE_PIL, "Pillow not installed")
    def test_visual_comparison_adds_columns(self):
        self.assertTrue(REFERENCE.is_file())
        code, stdout, data = self.run_tool([report()], exports={"demo": REFERENCE})
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertEqual(row["verdict"], "pass")  # visual is advisory
        self.assertIn(row["visual_verdict"], {"pass", "review", "blocked"})
        self.assertIsNotNone(row["visual_similarity"])
        self.assertGreater(row["visual_similarity"], 0.5)
        self.assertIn("similarity", stdout)

    @unittest.skipUnless(HAVE_PIL, "Pillow not installed")
    def test_visual_review_is_advisory(self):
        with tempfile.TemporaryDirectory() as d:
            blank = Path(d) / "blank.png"
            Image.new("RGB", (594, 420), "white").save(blank)
            code, stdout, data = self.run_tool([report()], exports={"demo": blank})
        self.assertEqual(code, 0)
        row = self.row(data)
        self.assertEqual(row["verdict"], "pass")
        self.assertEqual(row["visual_verdict"], "review")


if __name__ == "__main__":
    unittest.main()
