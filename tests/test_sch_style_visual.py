import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_style_visual.py"

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def make_schematic(path, size=(594, 420), square=False):
    if square:
        size = (420, 420)
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    colors = ["#00B3B3", "#C800C8", "#0066CC"]
    for i, c in enumerate(colors):
        x = int(size[0] * (0.05 + i * 0.3))
        draw.rectangle([x, 40, x + int(size[0] * 0.22), int(size[1] * 0.6)], outline=c, width=3)
        draw.line([x + 10, 60, x + int(size[0] * 0.2), 60], fill="black", width=1)
    img.save(path)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class VisualCompare(unittest.TestCase):
    def run_cmp(self, candidate, reference, extra=None):
        args = [sys.executable, str(SCRIPT), "--candidate", str(candidate),
                "--reference", str(reference)]
        if extra:
            args += extra
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
        return r.returncode, json.loads(r.stdout)

    def test_close_export_passes_and_writes_side_by_side(self):
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"; make_schematic(ref, (594, 420))
            cand = Path(d) / "cand.png"; make_schematic(cand, (594, 420))
            sbs = Path(d) / "side.png"
            code, rep = self.run_cmp(cand, ref, ["--side-by-side", str(sbs)])
            self.assertEqual(code, 0, rep)
            self.assertEqual(rep["verdict"], "pass")
            self.assertTrue(sbs.is_file())
            self.assertIn("similarity", rep["metrics"])

    def test_wrong_aspect_is_review(self):
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"; make_schematic(ref, (594, 420))
            cand = Path(d) / "cand.png"; make_schematic(cand, square=True)
            code, rep = self.run_cmp(cand, ref)
            self.assertEqual(code, 1)
            self.assertEqual(rep["verdict"], "review")

    def test_missing_candidate_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"; make_schematic(ref)
            code, rep = self.run_cmp(Path(d) / "nope.png", ref)
            self.assertEqual(code, 2)
            self.assertEqual(rep["verdict"], "blocked")


if __name__ == "__main__":
    unittest.main()
