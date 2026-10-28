"""stream-json robustness tests (task book §3.6, §4.10).

Every test drives a real launcher subprocess with ``--fake-scenario badjson``,
which emits two malformed stdout lines, one unknown event type and then a
normal assistant/result pair.  The launcher must:

* still complete the task with exit code 0;
* record one ``parse_error`` event per malformed line (and keep the raw line);
* preserve unknown event types verbatim as ``agent_event`` payloads;
* number events gaplessly and replay them through ``?since=`` without loss or
  duplication;
* keep the raw lines in ``agent.stdout.log``.

The launcher, the task and its evidence are created once per class: every test
below only reads the already-finished task, so the suite stays fast and the
assertions are independent.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from .support import LauncherProcess, LauncherTestCase, base_request

TASK_ID = "task-streamjson-badjson"

#: The two malformed lines the fake agent writes on purpose.
RAW_NOT_JSON = "this line is not json"
RAW_BROKEN_LINE = '{"broken": '
#: ``agent.parse_stream_line`` strips the line before recording it.
RAW_BROKEN = RAW_BROKEN_LINE.strip()

EXPECTED_EVENT_TYPES = [
    "task_accepted",
    "task_running",
    "agent_event",  # system/init
    "parse_error",
    "parse_error",
    "agent_event",  # mystery_event
    "agent_event",  # assistant
    "agent_event",  # result
    "task_finished",
]


class BadJsonStreamJsonTests(LauncherTestCase):
    """One completed ``badjson`` task asserted from several independent angles."""

    launcher: LauncherProcess
    final_status: dict
    result: dict
    events: list
    events_document: dict
    workspace: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LauncherProcess(fake_scenario="badjson")
        try:
            status, accepted = cls.launcher.start(base_request(TASK_ID, timeout_s=60))
            if status != 202:
                raise AssertionError(f"badjson task was not accepted: {status} {accepted}")
            cls.final_status = cls.launcher.wait_terminal(TASK_ID, timeout=60.0)
            status, cls.result = cls.launcher.result(TASK_ID)
            if status != 200:
                raise AssertionError(f"result endpoint failed: {status} {cls.result}")
            status, cls.events_document = cls.launcher.events(TASK_ID, 0)
            if status != 200:
                raise AssertionError(f"events endpoint failed: {status} {cls.events_document}")
            cls.events = cls.events_document["events"]
            cls.workspace = cls.launcher.workspace(TASK_ID)
        except BaseException:
            cls.launcher.close()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.launcher.close()

    def test_badjson_task_completes_with_exit_code_zero(self) -> None:
        self.assertEqual(self.final_status["status"], "completed", self.final_status)
        self.assertTrue(self.final_status["terminal"])
        self.assertEqual(self.result["status"], "completed", self.result)
        self.assertEqual(self.result["exit_code"], 0)
        self.assertFalse(self.result["timed_out"])
        self.assertFalse(self.result["cancelled"])
        self.assertEqual(self.result["agent"], "fake")

    def test_parse_error_recorded_for_each_malformed_line(self) -> None:
        parse_errors = [event for event in self.events if event["type"] == "parse_error"]
        self.assertEqual(len(parse_errors), 2, parse_errors)
        # The raw malformed line is evidence: it must not be silently dropped.
        self.assertEqual([event["raw"] for event in parse_errors], [RAW_NOT_JSON, RAW_BROKEN])
        for event in parse_errors:
            self.assertTrue(event["error"].startswith("invalid_json"), event["error"])
        # A parse error never aborts the task (events after it are still there).
        self.assertEqual(self.result["status"], "completed")

    def test_unknown_event_type_is_preserved_verbatim(self) -> None:
        payloads = [event["payload"] for event in self.events if event["type"] == "agent_event"]
        self.assertEqual(
            [payload["type"] for payload in payloads],
            ["system", "mystery_event", "assistant", "result"],
            payloads,
        )
        mystery = payloads[1]
        # Exact identity: not dropped, not coerced, nothing added by the parser.
        self.assertEqual(mystery, {"type": "mystery_event", "payload": {"kept": True}})
        self.assertEqual(set(mystery), {"type", "payload"})
        self.assertIs(mystery["payload"]["kept"], True)
        # Events after the unknown type are still parsed, in order.
        self.assertEqual([payload["type"] for payload in payloads[-2:]], ["assistant", "result"])

    def test_event_sequence_is_gapless_unique_and_ordered(self) -> None:
        self.assertEqual([event["type"] for event in self.events], EXPECTED_EVENT_TYPES, self.events)
        seqs = [event["seq"] for event in self.events]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        self.assertEqual(len(seqs), len(set(seqs)), "duplicate event seq")
        self.assertEqual(self.final_status["event_count"], len(seqs))
        self.assertEqual(self.final_status["next_seq"], len(seqs) + 1)
        self.assertEqual(self.events[0]["type"], "task_accepted")
        self.assertEqual(self.events[-1]["type"], "task_finished")

    def test_events_jsonl_on_disk_matches_the_api_stream(self) -> None:
        log_path = self.workspace / "events.jsonl"
        self.assertTrue(log_path.is_file(), log_path)
        lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), len(self.events))
        for line, event in zip(lines, self.events):
            self.assertEqual(json.loads(line), event)

    def test_events_since_returns_exactly_the_newer_events(self) -> None:
        all_seqs = [event["seq"] for event in self.events]
        for since in (0, 1, 3, len(all_seqs) - 1, len(all_seqs)):
            status, document = self.launcher.events(TASK_ID, since)
            self.assertEqual(status, 200, document)
            expected = [seq for seq in all_seqs if seq > since]
            self.assertEqual([event["seq"] for event in document["events"]], expected, f"since={since}")
            self.assertEqual(document["next_seq"], len(all_seqs) + 1)
            self.assertEqual(document["task_id"], TASK_ID)
            self.assertTrue(document["terminal"])

    def test_repeated_replay_is_idempotent_and_past_the_end_is_empty(self) -> None:
        first = self.launcher.events(TASK_ID, 3)
        second = self.launcher.events(TASK_ID, 3)
        self.assertEqual(first, second, "replaying the same window must be idempotent")
        self.assertEqual(first[0], 200)
        status, document = self.launcher.events(TASK_ID, len(self.events) + 5)
        self.assertEqual(status, 200, document)
        self.assertEqual(document["events"], [])
        self.assertEqual(document["next_seq"], len(self.events) + 1)

    def test_agent_stdout_log_keeps_every_raw_line(self) -> None:
        log_path = self.workspace / "agent.stdout.log"
        log_text = log_path.read_text(encoding="utf-8")
        self.assertIn(RAW_NOT_JSON, log_text)
        self.assertIn(RAW_BROKEN_LINE, log_text)
        log_lines = log_text.splitlines()
        self.assertEqual(len(log_lines), 6, log_lines)  # 2 malformed + 4 parsed lines
        self.assertIn(RAW_NOT_JSON, log_lines)
        self.assertIn(RAW_BROKEN_LINE, log_lines)
        parsed_lines = []
        for line in log_lines:
            try:
                parsed_lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        expected_payloads = [event["payload"] for event in self.events if event["type"] == "agent_event"]
        self.assertEqual(parsed_lines, expected_payloads)


if __name__ == "__main__":
    unittest.main()
