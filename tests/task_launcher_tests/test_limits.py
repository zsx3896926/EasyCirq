"""Event-cap limits: max_events fail path and its kill/error evidence (#84/#87)."""

from __future__ import annotations

import unittest

from .support import LauncherTestCase, base_request


class MaxEventsTests(LauncherTestCase):
    def test_max_events_kills_and_reports_stable_error(self) -> None:
        launcher = self.make_launcher(fake_scenario="spam")
        request = base_request("task-max-events-01", max_events=100)
        status, accepted = launcher.start(request)
        self.assertEqual(status, 202, accepted)
        self.assertEqual(accepted["agent"], "fake")
        self.assertEqual(accepted["agent_profile"], "fake")

        launcher.wait_terminal("task-max-events-01", timeout=60.0)
        status, result = launcher.result("task-max-events-01")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["max_events_exceeded"])
        self.assertEqual(result["error"]["code"], "MAX_EVENTS_EXCEEDED")
        self.assertEqual(result["error"]["detail"]["max_events"], 100)
        self.assertTrue(result["kill"]["killed"], result["kill"])
        self.assertNotEqual(result["kill"]["method"], "none")

        status, events_doc = launcher.events("task-max-events-01", 0)
        self.assertEqual(status, 200, events_doc)
        types = [event["type"] for event in events_doc["events"]]
        self.assertIn("max_events_exceeded", types)
        self.assertEqual(events_doc["events"][-1]["type"], "task_finished")
        seqs = [event["seq"] for event in events_doc["events"]]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        self.assertEqual(result["event_count"], len(seqs))

    def test_event_limit_is_validated(self) -> None:
        launcher = self.make_launcher()
        request = base_request("task-max-events-bad")
        request["limits"]["max_events"] = 99
        status, document = launcher.start(request)
        self.assertEqual(status, 422, document)
        self.assertEqual(document["error"]["code"], "VALUE_OUT_OF_RANGE")


if __name__ == "__main__":
    unittest.main()
