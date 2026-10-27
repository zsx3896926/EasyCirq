import copy
import json
import unittest

from . import fixtures, support

io_module = support.module("io")


def short_status(data):
    return support.review(data)["status"]


def codes(data):
    return support.finding_codes(support.review(data))


class DeformationTests(unittest.TestCase):
    def test_component_and_pin_order_do_not_change_verdict(self):
        base = fixtures.case_r5_ep_ok()
        shuffled = copy.deepcopy(base)
        shuffled["components"] = list(reversed(shuffled["components"]))
        shuffled["components"][0]["pins"] = list(
            reversed(shuffled["components"][0]["pins"]))
        self.assertEqual(short_status(base), short_status(shuffled))
        self.assertEqual(codes(base), codes(shuffled))

    def test_net_rename_preserves_conclusion(self):
        base = fixtures.case_r1_ok()
        renamed = copy.deepcopy(base)
        for component_row in renamed["components"]:
            for pin_row in component_row["pins"]:
                if pin_row.get("net") == "CP":
                    pin_row["net"] = "BOOT_P"
                elif pin_row.get("net") == "CN":
                    pin_row["net"] = "BOOT_N"
        role = renamed["intent"]["capacitor_roles"][0]
        for terminal in role["expected_terminals"]:
            terminal["net"] = {"CP": "BOOT_P", "CN": "BOOT_N"}[terminal["net"]]
        self.assertEqual(short_status(base), short_status(renamed))
        self.assertEqual(short_status(base), "pass_with_scope")

    def test_ref_rename_with_stable_instance_id(self):
        base = fixtures.case_r3_ok()
        renamed = copy.deepcopy(base)
        renamed["components"][0]["ref"] = "SW99"
        renamed["intent"]["switch_requirements"][0]["component"] = "SW99"
        self.assertEqual(short_status(base), short_status(renamed))
        self.assertEqual(short_status(base), "pass_with_scope")

    def test_unit_conversion_mil_to_mm(self):
        base = fixtures.case_r6_ok()
        converted = copy.deepcopy(base)
        for component_row in converted["components"]:
            for pin_row in component_row["pins"]:
                if pin_row.get("position"):
                    pin_row["position"]["x"] = round(
                        pin_row["position"]["x"] * 0.0254, 9)
                    pin_row["position"]["y"] = round(
                        pin_row["position"]["y"] * 0.0254, 9)
                    pin_row["position"]["units"] = "mm"
            if component_row.get("placement"):
                component_row["placement"]["x"] *= 0.0254
                component_row["placement"]["y"] *= 0.0254
                component_row["placement"]["units"] = "mm"
        converted["design"]["units"]["length"] = "mm"
        self.assertEqual(short_status(base), short_status(converted))

    def test_voltage_unit_conversion_mv(self):
        base = fixtures.case_r2_overvoltage()
        converted = copy.deepcopy(base)
        attributes = converted["components"][0]["attributes"]
        attributes["rated_voltage"]["value"] = 16000
        attributes["rated_voltage"]["unit"] = "mV"
        attributes["max_differential_stress"]["value"] = 24000
        attributes["max_differential_stress"]["unit"] = "mV"
        self.assertEqual(short_status(base), short_status(converted))
        self.assertEqual(short_status(base), "fail")

    def test_shorting_a_correct_flying_capacitor_must_fail(self):
        base = fixtures.case_r1_ok()
        broken = copy.deepcopy(base)
        broken["components"][1]["pins"][1]["net"] = "CP"
        broken["intent"]["capacitor_roles"][0].pop("expected_terminals")
        report = support.review(broken)
        self.assertEqual(report["status"], "fail")
        self.assertIn("flying_capacitor_shorted",
                      [item.get("code") for item in report["findings"]])

    def test_project_identity_changes_hashes_not_conclusion(self):
        base = fixtures.case_r3_ok()
        other = copy.deepcopy(base)
        other["design"]["project_id"] = "other-project"
        self.assertEqual(short_status(base), short_status(other))
        self.assertNotEqual(io_module.semantic_sha256(base),
                            io_module.semantic_sha256(other))

    def test_snapshot_hash_binding_is_on_the_report(self):
        with support.temporary_dir() as folder:
            from pathlib import Path
            first = support.write_json(Path(folder) / "a.json",
                                       fixtures.case_r1_ok())
            second = support.write_json(Path(folder) / "b.json",
                                        fixtures.case_r1_ok())
            payload = second.read_text(encoding="utf-8").replace(
                '"project_id": "r1-ok"', '"project_id": "r1-ok-v2"')
            second.write_text(payload, encoding="utf-8")
            first_report = support.cli(["review", str(first)])
            second_report = support.cli(["review", str(second)])
            self.assertNotEqual(json.loads(first_report.stdout)["input"]["sha256"],
                                json.loads(second_report.stdout)["input"]["sha256"])
            self.assertNotEqual(
                json.loads(first_report.stdout)["input"]["semantic_sha256"],
                json.loads(second_report.stdout)["input"]["semantic_sha256"])

    def test_unknown_unit_conversion_is_invalid(self):
        base = fixtures.case_r6_ok()
        broken = copy.deepcopy(base)
        broken["components"][0]["pins"][0]["position"]["units"] = "furlong"
        with self.assertRaises(support.module("contract").InputError):
            support.validate(broken)

    def test_rotation_does_not_affect_pad_distance(self):
        base = fixtures.case_r6_ok()
        rotated = copy.deepcopy(base)
        for component_row in rotated["components"]:
            component_row["placement"] = {"x": 0, "y": 0, "units": "mil",
                                          "rotation": 90}
        self.assertEqual(short_status(base), short_status(rotated))


if __name__ == "__main__":
    unittest.main()
