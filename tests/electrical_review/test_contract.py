import copy
import json
import unittest

from . import fixtures, support

contract = support.module("contract")
io_module = support.module("io")


class ContractValidationTests(unittest.TestCase):
    def test_valid_fixture_normalises(self):
        data = support.validate(fixtures.case_r1_ok())
        self.assertEqual(data["components"][1]["pins"][0]["net"], "CP")
        self.assertTrue(data["_meta"]["intent_supplied"])

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):
            io_module.loads_strict('{"a": 1, "a": 2}')

    def test_nan_and_infinity_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(ValueError):
                io_module.loads_strict('{"value": %s}' % token)

    def test_bool_is_not_a_number(self):
        data = fixtures.case_r2_overvoltage()
        data["components"][0]["attributes"]["rated_voltage"]["value"] = True
        with self.assertRaises(contract.InputError) as caught:
            support.validate(data)
        self.assertIn("finite number", str(caught.exception))

    def test_negative_rated_voltage_rejected(self):
        data = fixtures.case_r2_overvoltage()
        data["components"][0]["attributes"]["rated_voltage"]["value"] = -5
        with self.assertRaises(contract.InputError):
            support.validate(data)

    def test_unknown_unit_rejected(self):
        data = fixtures.case_r2_overvoltage()
        data["design"]["units"]["length"] = "furlong"
        with self.assertRaises(contract.InputError):
            support.validate(data)

    def test_duplicate_ref_and_instance_and_pin(self):
        for mutate in (
                lambda d: d["components"].__setitem__(1, {
                    **d["components"][1], "ref": "U1", "instance_id": "iC2"}),
                lambda d: d["components"].__setitem__(1, {
                    **d["components"][1], "instance_id": "iU1"}),
                lambda d: d["components"][0]["pins"].append(
                    {"number": "1", "net": "X"}),
                lambda d: d["components"][1]["pins"].append(
                    {"number": "2", "net": "GND"}),
        ):
            data = fixtures.case_r1_ok()
            mutate(data)
            with self.assertRaises(contract.InputError):
                support.validate(data)

    def test_contradictory_net_declarations(self):
        data = fixtures.case_r1_ok()
        data["connectivity"] = {"pin_nets": {"C1.1": "CN"}}
        with self.assertRaises(contract.InputError) as caught:
            support.validate(data)
        self.assertEqual(caught.exception.code, "contradiction")

    def test_unknown_pin_in_connectivity(self):
        data = fixtures.case_r1_ok()
        data["connectivity"] = {"pin_nets": {"U9.1": "X"}}
        with self.assertRaises(contract.InputError):
            support.validate(data)

    def test_duplicate_pad_across_pins(self):
        data = fixtures.case_r5_ams_tab_ok()
        data["components"][0]["pins"][0]["pads"] = ["1", "TAB"]
        with self.assertRaises(contract.InputError) as caught:
            support.validate(data)
        self.assertEqual(caught.exception.code, "duplicate_pad")

    def test_pad_nets_must_match_logical_pin_net(self):
        # Codex P1 regression: TAB is a physical pad of the VOUT logical pin;
        # declaring TAB=GND while the logical pin is +3V3 is contradictory.
        data = fixtures.case_r5_ams_tab_ok()
        data["components"][0]["pins"][1]["pad_nets"] = {"TAB": "GND"}
        with self.assertRaises(contract.InputError) as caught:
            support.validate(data)
        self.assertEqual(caught.exception.code, "pad_net_conflict")

    def test_pad_nets_alias_of_same_partition_is_accepted(self):
        data = fixtures.case_r5_ams_tab_ok()
        data["components"][0]["pins"][1]["pad_nets"] = {"TAB": "+3V3_ALIAS"}
        data["connectivity"]["net_aliases"] = [["+3V3", "+3V3_ALIAS"]]
        normalized = support.validate(data)
        self.assertEqual(normalized["components"][0]["pins"][1]["net"], "+3V3")

    def test_net_alias_merges_partitions(self):
        data = fixtures.case_r1_ok()
        data["connectivity"] = {"pin_nets": {},
                                "net_aliases": [["CP", "C1P_ALIAS"]]}
        normalized = support.validate(data)
        self.assertEqual(contract.canonical_net(normalized, "CP"),
                         contract.canonical_net(normalized, "C1P_ALIAS"))

    def test_missing_connectivity_and_empty_components(self):
        data = fixtures.case_r1_ok()
        data.pop("connectivity")
        with self.assertRaises(contract.InputError):
            support.validate(data)
        data = fixtures.case_r1_ok()
        data["components"] = []
        with self.assertRaises(contract.InputError):
            support.validate(data)

    def test_unknown_source_type_rejected(self):
        data = fixtures.case_r1_ok()
        data["design"]["source_type"] = "handwave"
        with self.assertRaises(contract.InputError):
            support.validate(data)

    def test_semantic_hash_ignores_order_but_not_identity(self):
        data = fixtures.case_r1_ok()
        first = io_module.semantic_sha256(data)
        shuffled = copy.deepcopy(data)
        shuffled["components"] = list(reversed(shuffled["components"]))
        shuffled["components"][1]["pins"] = list(
            reversed(shuffled["components"][1]["pins"]))
        self.assertEqual(first, io_module.semantic_sha256(shuffled))
        renamed = copy.deepcopy(data)
        renamed["design"]["project_id"] = "another-project"
        self.assertNotEqual(first, io_module.semantic_sha256(renamed))

    def test_dangling_evidence_and_fact_references(self):
        for mutate in (
                lambda d: d["intent"]["capacitor_roles"][0].__setitem__(
                    "evidence", ["NO-SUCH-EVIDENCE"]),
                lambda d: d["intent"]["capacitor_roles"][0].__setitem__(
                    "fact_ids", ["NO-SUCH-FACT"]),
        ):
            data = fixtures.case_r1_ok()
            mutate(data)
            with self.assertRaises(contract.InputError):
                support.validate(data)

    def test_stable_json_is_sorted(self):
        text = io_module.stable_json({"b": 1, "a": [{"d": 2, "c": 3}]})
        self.assertLess(text.index('"a"'), text.index('"b"'))


if __name__ == "__main__":
    unittest.main()
