"""Smoke tests: the launcher boots, serves JSON, and completes a fake task."""

from __future__ import annotations

import unittest

from .support import (
    LAUNCHER_VERSION,
    PLUGIN_VERSION,
    RESULT_SCHEMA,
    SKILL_VERSION,
    LauncherTestCase,
    base_request,
)


class SmokeTests(LauncherTestCase):
    def test_health_needs_no_token(self) -> None:
        launcher = self.make_launcher()
        status, document = launcher.health()
        self.assertEqual(status, 200, document)
        self.assertEqual(document["status"], "ok")
        self.assertEqual(document["version"], LAUNCHER_VERSION)
        self.assertEqual(document["skill_version"], SKILL_VERSION)
        self.assertEqual(document["plugin_version"], PLUGIN_VERSION)
        self.assertEqual(document["tasks_running"], 0)
        self.assertIn(launcher.base_url, f"http://127.0.0.1:{launcher.port}")

    def test_happy_path_completes_with_honest_result(self) -> None:
        launcher = self.make_launcher()
        request = base_request("task-smoke-001")
        status, accepted = launcher.start(request)
        self.assertEqual(status, 202, accepted)
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["task_id"], "task-smoke-001")
        status, result = launcher.request("GET", "/task/task-smoke-001/result")
        self.assertEqual(status, 409, result)
        self.assertEqual(result["error"]["code"], "RESULT_NOT_READY")
        launcher.wait_terminal("task-smoke-001")
        status, result = launcher.result("task-smoke-001")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["agent"], "fake")
        self.assertEqual(result["real_eda"], "NOT RUN")
        self.assertEqual(result["eda_calls"], 0)
        self.assertEqual(result["project_writes"], 0)
        self.assertEqual(result["exit_code"], 0)

    def test_unknown_endpoint_is_404(self) -> None:
        launcher = self.make_launcher()
        status, document = launcher.request("GET", "/nope")
        self.assertEqual(status, 404, document)
        self.assertEqual(document["error"]["code"], "NOT_FOUND")

    def test_start_requires_bearer_token(self) -> None:
        launcher = self.make_launcher()
        request = base_request("task-smoke-auth")
        status, document = launcher.start(request, token=None)
        self.assertEqual(status, 401, document)
        self.assertEqual(document["error"]["code"], "UNAUTHORIZED")
        status, document = launcher.start(request, token="wrong")
        self.assertEqual(status, 401, document)
        # And with the real token the same request is accepted.
        status, document = launcher.start(request)
        self.assertEqual(status, 202, document)

    def test_second_task_is_busy(self) -> None:
        launcher = self.make_launcher(fake_scenario="slow")
        first = base_request("task-smoke-busy-1")
        second = base_request("task-smoke-busy-2")
        status, _ = launcher.start(first)
        self.assertEqual(status, 202)
        status, document = launcher.start(second)
        self.assertEqual(status, 429, document)
        self.assertEqual(document["error"]["code"], "BUSY")
        launcher.wait_terminal("task-smoke-busy-1")


if __name__ == "__main__":
    unittest.main()
