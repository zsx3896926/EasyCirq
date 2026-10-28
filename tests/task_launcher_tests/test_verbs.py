"""HTTP verb conformance: every verb answers JSON, never stdlib text (#86)."""

from __future__ import annotations

import http.client
import unittest

from .support import LauncherTestCase, base_request


class HttpVerbTests(LauncherTestCase):
    def test_put_delete_patch_return_json_errors(self) -> None:
        launcher = self.make_launcher()
        for method, path in (
            ("PUT", "/task/whatever"),
            ("PATCH", "/task/whatever"),
            ("DELETE", "/task/start"),
            ("PUT", "/nope"),
        ):
            with self.subTest(method=method, path=path):
                status, document = launcher.request(method, path)
                self.assertIn(status, (404, 405), document)
                self.assertIn("error", document, document)
                if path == "/nope":
                    self.assertEqual(status, 404, document)
                    self.assertEqual(document["error"]["code"], "NOT_FOUND")
                else:
                    self.assertEqual(status, 405, document)
                    self.assertEqual(document["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_unknown_verbs_are_unauthenticated_first(self) -> None:
        launcher = self.make_launcher()
        status, document = launcher.request("PUT", "/task/whatever", token=None)
        self.assertEqual(status, 401, document)
        self.assertEqual(document["error"]["code"], "UNAUTHORIZED")

    def test_head_returns_headers_without_body(self) -> None:
        launcher = self.make_launcher()
        connection = http.client.HTTPConnection("127.0.0.1", launcher.port, timeout=30)
        try:
            connection.request("HEAD", "/health")
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()
        self.assertEqual(response.status, 405)
        self.assertEqual(body, b"")
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")

    def test_delete_terminal_task_is_not_method_not_allowed(self) -> None:
        launcher = self.make_launcher()
        launcher.run_task(base_request("task-verbs-delete"))
        status, document = launcher.request("DELETE", "/task/task-verbs-delete")
        self.assertEqual(status, 200, document)
        self.assertEqual(document["status"], "deleted")


if __name__ == "__main__":
    unittest.main()
