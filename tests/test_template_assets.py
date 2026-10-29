"""Shipped block templates must be replayable: concrete pin numbers required."""

import glob
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.layout2 import templates  # noqa: E402

ASSETS = sorted(glob.glob(str(ROOT / "easycirq" / "assets" / "block-templates"
                                 / "*.template.json")))


class ShippedTemplateTests(unittest.TestCase):
    def test_assets_exist(self):
        self.assertGreaterEqual(len(ASSETS), 3)

    def test_every_pin_carries_concrete_numbers(self):
        for path in ASSETS:
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            for index, pin in enumerate(data["pins"]):
                self.assertTrue(pin.get("numbers"),
                                "%s pins[%d] has no numbers" % (path, index))
                for number in pin["numbers"]:
                    self.assertIsInstance(number, str)
                    self.assertTrue(number)

    def test_instantiation_emits_numeric_members(self):
        for path in ASSETS:
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            applied = templates.instantiate_template(data, "p1", [100, 100])
            for net in applied["nets"]:
                for ref, pin in net["members"]:
                    self.assertIsInstance(pin, str)
                    self.assertTrue(pin)

    def test_instantiation_has_no_negative_parts(self):
        for path in ASSETS:
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            rel = data["bbox"]
            applied = templates.instantiate_template(
                data, "p1", [100 - rel["minX"], 100 - rel["minY"]])
            for part in applied["parts"]:
                self.assertGreaterEqual(part["x"], 0, part)
                self.assertGreaterEqual(part["y"], 0, part)


if __name__ == "__main__":
    unittest.main()
