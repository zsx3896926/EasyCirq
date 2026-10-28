import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:  # directory-mode discovery
    import helpers

from annotation_layout.probe_record import (
    PROBE_SCHEMA,
    REQUIRED_CAPABILITIES,
    validate_record,
)

EXAMPLE = helpers.ROOT / "docs" / "parallel-annotation-layout" / \
    "integration-capability-record.example.json"


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class ProbeRecordValidationTest(unittest.TestCase):
    def test_example_record_is_structurally_valid(self):
        result = validate_record(example())
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["schema"], PROBE_SCHEMA)
        self.assertEqual(result["host_execution"], "not_executed")
        self.assertTrue(result["record_sha256"])
        self.assertEqual(result["host_block"]["execution"], "not_executed")
        self.assertEqual(result["host_block"]["capabilities"],
                         result["capabilities"])
        self.assertEqual(result["host_block"]["capability_source"],
                         result["capability_source"])
        for name in REQUIRED_CAPABILITIES:
            self.assertIn(name, result["capabilities"])
        self.assertTrue(any("unverified" in warning for warning in result["warnings"]))

    def test_unknown_top_level_key_is_a_warning_not_an_error(self):
        document = example()
        document["future_note"] = "unknown optional extension"
        result = validate_record(document)
        self.assertEqual(result["status"], "valid")
        self.assertTrue(any("unknown top-level key" in warning
                            for warning in result["warnings"]))

    def test_invalid_variants_are_rejected(self):
        mutations = {
            "schema": lambda doc: doc.__setitem__("schema", "wrong"),
            "execution": lambda doc: doc.__setitem__("execution", "host_verified"),
            "snapshot": lambda doc: doc["project"].__setitem__(
                "snapshot_sha256", "not-a-hash"),
            "missing capability": lambda doc: doc["capabilities"].pop(
                "free_text_translate"),
            "bad capability": lambda doc: doc["capabilities"].__setitem__(
                "attribute_translate", "maybe"),
            "bad probe result": lambda doc: doc["probes"][0].__setitem__(
                "result", "works"),
            "duplicate probe": lambda doc: doc["probes"][1].__setitem__(
                "id", doc["probes"][0]["id"]),
            "no probes": lambda doc: doc.__setitem__("probes", []),
            "not_run type": lambda doc: doc.__setitem__("not_run", "not a list"),
        }
        for name, mutate in mutations.items():
            with self.subTest(case=name):
                document = copy.deepcopy(example())
                mutate(document)
                result = validate_record(document)
                self.assertEqual(result["status"], "invalid", result)
                self.assertTrue(result["errors"])

    def test_non_object_record_is_invalid(self):
        result = validate_record(["not", "an", "object"])
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(result["errors"])
        self.assertIsNone(result["host_block"])


class ProbeBindCliTest(unittest.TestCase):
    def _bound_paths(self, directory: Path):
        document = helpers.mini_input(annotations=[], components=[])
        record = example()
        record["project"]["name"] = document["project"]["name"]
        record["project"]["page_id"] = document["project"]["page_id"]
        record["project"]["snapshot_sha256"] = document["project"]["snapshot_sha256"]
        input_path = directory / "input.json"
        record_path = directory / "record.json"
        helpers.write_json(input_path, document)
        helpers.write_json(record_path, record)
        return input_path, record_path, directory / "input-bound.json", record

    def test_probe_bind_injects_capabilities_into_a_valid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            input_path, record_path, out, record = self._bound_paths(directory)
            code, payload, stderr, _ = helpers.run_cli([
                "probe-bind", str(input_path), "--record", str(record_path),
                "--out", str(out)])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["host_execution"], "not_executed")
            self.assertEqual(payload["binding"]["page_id"], record["project"]["page_id"])
            self.assertEqual(payload["host_block"]["execution"], "not_executed")
            self.assertEqual(payload["host_block"]["capabilities"],
                             record["capabilities"])
            written = helpers.read_json(out)
            self.assertEqual(written["host"], payload["host_block"])
            self.assertEqual(helpers.run_cli(["validate", str(out)])[0], 0)

    def test_probe_bind_rejects_page_or_snapshot_mismatch(self):
        for field, value in (("page_id", "another-page"),
                             ("snapshot_sha256", "f" * 64)):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as temp:
                    directory = Path(temp)
                    input_path, record_path, out, record = self._bound_paths(directory)
                    record["project"][field] = value
                    helpers.write_json(record_path, record)
                    out.write_text('{"host": "stale"}\n', encoding="utf-8")
                    code, payload, stderr, _ = helpers.run_cli([
                        "probe-bind", str(input_path), "--record", str(record_path),
                        "--out", str(out)])
                    self.assertEqual(code, 2)
                    self.assertEqual(payload["status"], "invalid")
                    self.assertTrue(any("mismatch" in error for error in payload["errors"]))
                    written = helpers.read_json(out)
                    self.assertEqual(written["status"], "invalid")
                    self.assertNotIn("host", written)

    def test_probe_bind_rejects_invalid_record(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            input_path, record_path, out, record = self._bound_paths(directory)
            record["capabilities"]["net_label_detach"] = "maybe"
            helpers.write_json(record_path, record)
            code, payload, stderr, _ = helpers.run_cli([
                "probe-bind", str(input_path), "--record", str(record_path),
                "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "invalid")

    def test_probe_bind_refuses_output_equal_to_input(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            input_path, record_path, _out, _record = self._bound_paths(directory)
            code, payload, stderr, _ = helpers.run_cli([
                "probe-bind", str(input_path), "--record", str(record_path),
                "--out", str(input_path)])
            self.assertEqual(code, 2)
            self.assertIn("refusing", stderr.lower())


class ProbeRecordCliTest(unittest.TestCase):
    def test_probe_check_validates_and_writes_host_block(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "host-block.json"
            code, payload, stderr, raw = helpers.run_cli(
                ["probe-check", str(EXAMPLE), "--out", str(out)])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(payload["status"], "valid")
            self.assertEqual(payload["host_execution"], "not_executed")
            self.assertEqual(payload["host_block"]["execution"], "not_executed")
            json.loads(raw)  # stdout is one pure JSON document
            written = helpers.read_json(out)
            self.assertEqual(written["host"], payload["host_block"])
            self.assertEqual(written["record_sha256"], payload["record_sha256"])

    def test_probe_check_invalid_record_exits_2_and_does_not_leave_host_block(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            document = example()
            document["capabilities"]["net_label_detach"] = "maybe"
            record = directory / "record.json"
            helpers.write_json(record, document)
            out = directory / "host-block.json"
            out.write_text('{"host": "stale"}\n', encoding="utf-8")
            code, payload, stderr, _ = helpers.run_cli(
                ["probe-check", str(record), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "invalid")
            self.assertTrue(payload["errors"])
            written = helpers.read_json(out)
            self.assertEqual(written["status"], "invalid")
            self.assertNotIn("host", written)

    def test_probe_check_refuses_output_equal_to_input(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["probe-check", str(EXAMPLE), "--out", str(EXAMPLE)])
        self.assertEqual(code, 2)
        self.assertIn("refusing", stderr.lower())

    def test_probe_check_rejects_unknown_capability_record_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "not-json.json"
            path.write_text("{not json", encoding="utf-8")
            code, payload, stderr, _ = helpers.run_cli(
                ["probe-check", str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
