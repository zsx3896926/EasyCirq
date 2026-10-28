"""Strict request-schema tests (task book §3.3 / §4.1).

Every case is sent over the real loopback HTTP API; the launcher must answer
with a stable error code and the appropriate 400/422 status.  No agent is
started for these requests.
"""

from __future__ import annotations

import json
import unittest

from .support import LauncherProcess, base_request


class SchemaTests(unittest.TestCase):
    launcher: LauncherProcess

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LauncherProcess()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.launcher.close()

    # -- helpers -----------------------------------------------------------
    def post(self, request):
        return self.launcher.start(request)

    def assert_code(self, response, http_status: int, code: str) -> dict:
        status, document = response
        self.assertEqual(status, http_status, document)
        self.assertIn("error", document)
        self.assertEqual(document["error"]["code"], code, document)
        self.assertIn("message", document["error"])
        return document["error"]

    def test_missing_schema(self) -> None:
        request = base_request()
        del request["schema"]
        self.assert_code(self.post(request), 422, "MISSING_FIELD")

    def test_unsupported_schema_version(self) -> None:
        request = base_request()
        request["schema"] = "zhigou.task-launcher.start/v2"
        self.assert_code(self.post(request), 422, "UNSUPPORTED_SCHEMA")

    def test_task_id_format_is_strict(self) -> None:
        for task_id in ("-bad", ".bad", "with space", "中文", "a" * 65, "", "x/y"):
            with self.subTest(task_id=task_id):
                request = base_request()
                request["task_id"] = task_id
                self.assert_code(self.post(request), 422, "INVALID_FORMAT")

    def test_task_id_type_and_unknown_fields(self) -> None:
        request = base_request()
        request["task_id"] = 42
        self.assert_code(self.post(request), 422, "INVALID_TYPE")
        request = base_request()
        request["extra"] = True
        self.assert_code(self.post(request), 422, "UNKNOWN_FIELD")
        request = base_request()
        request["context"]["unexpected"] = 1
        self.assert_code(self.post(request), 422, "UNKNOWN_FIELD")

    def test_mode_is_read_only(self) -> None:
        for mode in ("write", "read_write", "Read_Only", "banana"):
            with self.subTest(mode=mode):
                request = base_request(mode=mode)
                error = self.assert_code(self.post(request), 422, "WRITE_MODE_NOT_SUPPORTED")
                self.assertEqual(error["detail"]["supported_modes"], ["read_only"])

    def test_limits_type_strictness(self) -> None:
        for value in (True, "180", 180.0, None):
            with self.subTest(value=value):
                request = base_request()
                request["limits"]["timeout_s"] = value
                self.assert_code(self.post(request), 422, "INVALID_TYPE")
        request = base_request()
        request["limits"]["timeout_s"] = 5
        self.assert_code(self.post(request), 422, "VALUE_OUT_OF_RANGE")
        request = base_request()
        request["limits"]["timeout_s"] = 99999
        self.assert_code(self.post(request), 422, "VALUE_OUT_OF_RANGE")
        request = base_request()
        request["limits"]["max_events"] = True
        self.assert_code(self.post(request), 422, "INVALID_TYPE")
        request = base_request()
        request["limits"]["unknown"] = 1
        self.assert_code(self.post(request), 422, "UNKNOWN_FIELD")

    def test_empty_user_prompt_is_rejected(self) -> None:
        request = base_request()
        request["goal"]["user_prompt"] = "   \n\t "
        self.assert_code(self.post(request), 422, "EMPTY_REQUIRED")
        request = base_request()
        request["goal"]["user_prompt"] = 5
        self.assert_code(self.post(request), 422, "INVALID_TYPE")

    def test_invalid_enums(self) -> None:
        request = base_request()
        request["goal"]["intent"] = "make_it"
        self.assert_code(self.post(request), 422, "INVALID_FORMAT")
        request = base_request()
        request["context"]["document"]["kind"] = "gerber"
        self.assert_code(self.post(request), 422, "INVALID_FORMAT")
        request = base_request()
        request["context"]["selection"] = [{"kind": "footprint"}]
        self.assert_code(self.post(request), 422, "INVALID_FORMAT")

    def test_snapshot_must_be_declared_when_unknown(self) -> None:
        request = base_request()
        request["context"]["snapshot_sha256"] = None
        request["context"]["missing_fields"] = ["pcb_geometry"]
        self.assert_code(self.post(request), 422, "MISSING_SNAPSHOT_DECLARATION")
        request = base_request()
        del request["context"]["snapshot_sha256"]
        del request["context"]["missing_fields"]
        self.assert_code(self.post(request), 422, "MISSING_SNAPSHOT_DECLARATION")
        request = base_request()
        request["context"]["snapshot_sha256"] = "NOT-A-HASH"
        self.assert_code(self.post(request), 422, "INVALID_FORMAT")
        request = base_request()
        request["context"]["snapshot_sha256"] = "A" * 64
        self.assert_code(self.post(request), 422, "INVALID_FORMAT")

    def test_launcher_version_is_validated_in_toolchain(self) -> None:
        request = base_request(launcher_version="not-a-version")
        self.assert_code(self.post(request), 422, "INVALID_FORMAT")

    def test_malformed_json(self) -> None:
        status, document = self.launcher.send_start_bytes(b'{"schema": ')
        self.assertEqual(status, 400, document)
        self.assertEqual(document["error"]["code"], "INVALID_JSON")
        status, document = self.launcher.send_start_bytes(b"")
        self.assertEqual(status, 400, document)
        self.assertEqual(document["error"]["code"], "INVALID_JSON")
        status, document = self.launcher.send_start_bytes(b"[]")
        self.assertEqual(status, 400, document)
        self.assertEqual(document["error"]["code"], "INVALID_REQUEST")

    def test_duplicate_json_keys_are_rejected(self) -> None:
        request = base_request()
        text = json.dumps(request, ensure_ascii=False)
        duplicated = text[:-1] + ', "task_id": "task-other"}'
        status, document = self.launcher.send_start_bytes(duplicated.encode("utf-8"))
        self.assertEqual(status, 400, document)
        self.assertEqual(document["error"]["code"], "DUPLICATE_KEY")

    def test_nan_and_infinity_are_rejected(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                request = base_request()
                text = json.dumps(request, ensure_ascii=False)
                broken = text.replace('"timeout_s": 60', f'"timeout_s": {constant}')
                status, document = self.launcher.send_start_bytes(broken.encode("utf-8"))
                self.assertEqual(status, 400, document)
                self.assertEqual(document["error"]["code"], "NON_FINITE_NUMBER")

    def test_content_type_and_payload_size(self) -> None:
        request = base_request()
        status, document = self.launcher.send_start_bytes(json.dumps(request).encode("utf-8"), content_type="text/plain")
        self.assertEqual(status, 400, document)
        self.assertEqual(document["error"]["code"], "INVALID_REQUEST")
        huge = b'{"schema":"' + b"a" * (1024 * 1024 + 10) + b'"}'
        status, document = self.launcher.send_start_bytes(huge)
        self.assertEqual(status, 413, document)
        self.assertEqual(document["error"]["code"], "PAYLOAD_TOO_LARGE")

    def test_defaults_are_accepted_when_limits_are_absent(self) -> None:
        request = base_request("task-schema-defaults")
        del request["limits"]
        status, accepted = self.post(request)
        self.assertEqual(status, 202, accepted)
        self.assertEqual(accepted["status"], "accepted")
        status, task = self.launcher.task("task-schema-defaults")
        self.assertEqual(status, 200, task)
        self.assertEqual(task["limits"], {"timeout_s": 180, "max_events": 10000})
        self.launcher.wait_terminal("task-schema-defaults")


if __name__ == "__main__":
    unittest.main()
