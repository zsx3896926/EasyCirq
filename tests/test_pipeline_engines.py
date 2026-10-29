"""Engine-selection tests for the one-command pipeline."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class EngineTests(unittest.TestCase):
    def test_freeform_engine_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            spec = {"name": "ff", "engine": "freeform",
                    "modules": [{"id": "m1", "title": "m1", "w": 300, "h": 200},
                                {"id": "m2", "title": "m2", "w": 300, "h": 200}]}
            _write(tmp / "spec.json", spec)
            result = subprocess.run([sys.executable, str(ROOT / "tools" / "pipeline.py"),
                                     "--spec", str(tmp / "spec.json"),
                                     "--out-dir", str(tmp / "out")],
                                    capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            plan = json.loads((tmp / "out" / "ff.plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan.get("engine"), "freeform")
            block = plan["pages"][0]["blocks"][0]
            self.assertIn("zone_rects", block)
            self.assertEqual(plan["pages"][0]["page"], 1)

    def test_templates_engine_expands_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            template = {
                "schema": "easycirq-block-template/v1", "block": "demo",
                "origin": {"role": "U", "ref": "U1", "x": 0, "y": 0},
                "bbox": [-10, -10, 10, 10],
                "parts": [{"role": "U", "designator": "U1", "dx": 0, "dy": 0,
                           "rotation": 0, "bbox": [-10, -10, 10, 10]}],
                "pins": [],
            }
            _write(tmp / "demo.template.json", template)
            spec = {"name": "tp", "engine": "templates",
                    "modules": [{"id": "m1", "title": "m1", "w": 300, "h": 200}],
                    "templates": {"m1": "demo.template.json"}}
            _write(tmp / "spec.json", spec)
            result = subprocess.run([sys.executable, str(ROOT / "tools" / "pipeline.py"),
                                     "--spec", str(tmp / "spec.json"),
                                     "--out-dir", str(tmp / "out")],
                                    capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            bundle = json.loads((tmp / "out" / "tp.apply.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle.get("engine"), "templates")
            placement = bundle["pages"][0]["placements"][0]
            self.assertEqual(placement["parts"][0]["ref"], "U1")
            # min-origin alignment: part x = bbox.minX - template.bbox.minX
            self.assertEqual(placement["parts"][0]["x"],
                             placement["bbox"][0] + 10)
            self.assertTrue(all(p["x"] >= 0 and p["y"] >= 0
                                for p in placement["parts"]))

    def test_invalid_engine_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            _write(tmp / "spec.json", {"name": "bad", "engine": "nope",
                                       "modules": [{"id": "m1", "w": 10, "h": 10}]})
            result = subprocess.run([sys.executable, str(ROOT / "tools" / "pipeline.py"),
                                     "--spec", str(tmp / "spec.json"),
                                     "--out-dir", str(tmp / "out"), "--dry-run"],
                                    capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
