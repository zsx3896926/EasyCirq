# Frozen benchmark: `task-launcher` (B1-LAUNCH)

Offline, deterministic, end-to-end benchmark of the Zhigou task launcher:

```text
trigger surface (stub connector)  ->  launcher HTTP sidecar  ->  fake agent
        POST /task/start             127.0.0.1, JSON API           bundled
        GET  /task/<id>/events                                   task_launcher.fake_agent
        POST /task/<id>/cancel
        GET  /task/<id>/result
```

Every case starts a **fresh** `python -m task_launcher serve` process on an
OS-assigned loopback port (fake agent only), runs
`python -m task_launcher.stub_connector` as a subprocess against it, asserts the
stub's single JSON stdout document plus the launcher-owned evidence in the task
workspace, and records timing.

## Honesty boundary

```text
simulated: true        agent: fake        offline: true
real_eda: "NOT RUN"    eda_calls: 0      project_writes: 0   network_calls: 0
```

No EDA tool, daemon, connector, hardware, network or real model is used. A real
Claude Code run is **OPTIONAL / NOT RUN** and is never launched by this
benchmark; `--real-claude` only marks the real-Claude cases `NOT RUN` and still
requires every simulated case to pass for exit code `0`.

## Run

```bash
python benchmarks/task-launcher/run_benchmark.py
python benchmarks/task-launcher/run_benchmark.py --real-claude
python benchmarks/task-launcher/run_benchmark.py --cases DIR --output PATH
```

Exit codes: `0` all cases passed, `1` a case failed, `2` benchmark cannot run
(bad `--cases` directory / no cases). `--cases` defaults to `cases/`, `--output`
defaults to `results.json`.

Requirements: Python 3.10+ (stdlib only), run from a clean checkout; the launcher
builds one shared plugin cache per benchmark run under the system temporary
directory (keyed by the Skill fingerprint), so the 13 MB plugin tree is built
once, not once per case. The temporary tree is removed at the end.

## Case layout

`cases/<id>/request.json` is a real `zhigou.task-launcher.start/v1` request.
Its `toolchain` uses the placeholders `@launcher` / `@skill` / `@plugin` instead of
hard-coded versions: the runner resolves them to the launcher/Skill/plugin
versions of the installation under test, so a Skill version bump on `main` does
not silently invalidate the frozen benchmark. The three deliberate
`version-mismatch` cases keep their literal wrong version (they must still get
`409 VERSION_MISMATCH`).
`cases/<id>/expected.json` is declarative:

```json
{
  "schema": "zhigou.task-launcher.benchmark-case/v1",
  "id": "09-cancel-mid-run",
  "description": "Cancel: slow fake agent is cancelled after the first observed event.",
  "launcher": {
    "agent_profile": "fake",
    "fake_scenario": "slow",
    "max_concurrent": 1,
    "claude_exe": null
  },
  "stub_args": {
    "poll_interval": 0.05,
    "timeout": 120.0,
    "cancel_after_events": 1,
    "concurrent_task_id": null
  },
  "http_status": 202,
  "final_status": "cancelled",
  "exit_code": 1,
  "checks": [
    {"path": "result.status", "equals": "cancelled"},
    {"path": "result.cancelled", "equals": true}
  ],
  "workspace_checks": [
    {"kind": "event_count_min", "min": 4},
    {"kind": "event_type_present", "type": "cancel_requested"},
    {"kind": "result_file_exists"},
    {"kind": "no_orphan_agent"}
  ]
}
```

Field semantics:

| field | meaning |
| --- | --- |
| `launcher.agent_profile` | `--agent-profile` (`fake` only in this frozen benchmark; `claude` is used solely for the *unavailable* case) |
| `launcher.fake_scenario` | `--fake-scenario`: `stream`, `slow`, `stuck`, `badjson`, `fail` |
| `launcher.max_concurrent` | `--max-concurrent` |
| `launcher.claude_exe` | optional `--claude-exe`; the agent-unavailable case uses a never-installed name, never a real path |
| `stub_args.*` | stub connector flags: `--poll-interval`, `--timeout`, `--cancel-after-events`, `--concurrent-task-id` |
| `http_status` | expected `summary.start_http_status` (202, 409, 422 or 503) |
| `final_status` | expected `summary.final_status`; `null` for rejected starts |
| `exit_code` | expected stub connector process exit code (0 completed, 1 failed/timeout/cancelled, 2 protocol error) |
| `checks` | declarative dotted-path equality checks on the stub summary; numbers and booleans are type-strict (`true != 1`, `1 != 1.0`) |
| `workspace_checks` | assertions on launcher evidence under the per-run state dir (see below) |

Always-enforced invariants (independent of `expected.json`):

* stub stdout is exactly one JSON document (`json.loads(whole stdout)`);
* stub `schema` is `zhigou.task-launcher.stub-result/v1` and
  `summary.exit_code == process exit code`;
* stub summary honesty fields are `real_eda="NOT RUN"`, `eda_calls=0`,
  `project_writes=0`, `agent="fake"`;
* the stub's event sequence numbers are strictly increasing and event types are
  not dropped (`event_seq_monotonic == true`, all events replayable);
* for accepted tasks (`start_http_status == 202`):
  * `summary.event_count` equals the number of events in the launcher's
    `events.jsonl` evidence (nothing skipped between polls);
  * the evidence `seq` numbers are contiguous `1..N`;
  * `result.event_count` equals the same total (it includes `task_finished`);
  * a terminal task returns a result object whose `status` equals
    `final_status`; a rejected start returns `result: null` and `error.code`;
* the launcher token never appears in the agent command evidence.

`workspace_checks` kinds:

| kind | assertion |
| --- | --- |
| `event_count_min` (`min`) | `events.jsonl` has at least `min` events |
| `event_type_present` (`type`) | the launcher emitted an event of that type |
| `parse_error_count` (`equals` / `min`) | count of `parse_error` events |
| `agent_event_payload_type_present` (`payload_type`) | an `agent_event` kept the unknown stream-json payload type verbatim |
| `result_file_exists` | the task workspace has `result.json` |
| `agent_command_required_flags` | `agent.command.json` contains `--plugin-dir`, `--append-system-prompt-file`, `--mcp-config`, `--output-format`, `required_flags_present: true`, `token_included: false` |
| `no_orphan_agent` | the fake agent pid recorded in `agent.received.json` is dead after the task reached a terminal state |

## Cases

| id | gate under test | expected |
| --- | --- | --- |
| `01-happy-read-only` | happy path, fake agent `stream` | 202, `completed`, exit 0 |
| `02-version-mismatch-launcher` | launcher version handshake | 409 `VERSION_MISMATCH`, exit 2 |
| `03-version-mismatch-skill` | Skill version handshake (`easycirq/.version`, legacy `design-hardware/.version`) | 409 `VERSION_MISMATCH`, exit 2 |
| `04-version-mismatch-plugin` | plugin package version handshake | 409 `VERSION_MISMATCH`, exit 2 |
| `05-schema-invalid-unknown-field` | strict request schema | 422 `UNKNOWN_FIELD`, exit 2 |
| `06-write-mode-refused` | read-only write gate (`mode="write"`) | 422 `WRITE_MODE_NOT_SUPPORTED`, exit 2 |
| `07-agent-failure` | fake agent `fail` scenario | 202, `failed`, exit 1 |
| `08-timeout-stuck` | `timeout_s=10` kills a stuck agent, no orphan | 202, `timeout`, exit 1 |
| `09-cancel-mid-run` | `POST /task/<id>/cancel` mid-run | 202, `cancelled`, exit 1 |
| `10-concurrency-busy` | second start with `max_concurrent=1` | 202 + `concurrent_start_http_status=429 BUSY`, `completed`, exit 0 |
| `11-agent-unavailable` | claude profile + nonexistent `--claude-exe` | 503 `AGENT_UNAVAILABLE`, exit 2 |
| `12-badjson-stream` | malformed/unknown stream-json lines do not abort the task | 202, `completed`, exit 0, `parse_error` events kept |

## `results.json`

Written deterministically (LF newlines, `sort_keys=True`, relative paths only;
only the `duration_ms` / `elapsed_ms` fields vary between runs):

```json
{
  "schema": "zhigou.task-launcher.benchmark/v1",
  "benchmark": "task-launcher",
  "simulated": true,
  "offline": true,
  "real_eda": "NOT RUN",
  "eda_calls": 0,
  "project_writes": 0,
  "network_calls": 0,
  "hardware_test": "NOT RUN",
  "agent": "fake",
  "launcher_version": "0.1.0",
  "skill_version": "1.0.2",
  "plugin_version": "0.1.0",
  "limits": {"case_timeout_s": 180.0, "launcher_start_timeout_s": 120.0, "...": "..."},
  "cases": [
    {
      "id": "01-happy-read-only",
      "description": "...",
      "passed": true,
      "problems": [],
      "duration_ms": 2606,
      "exit_code": 0,
      "start_http_status": 202,
      "final_status": "completed",
      "event_count": 8,
      "cancel_sent": false,
      "concurrent_start_http_status": null,
      "result_status": "completed"
    }
  ],
  "totals": {"passed": 12, "total": 12},
  "elapsed_ms": 25797,
  "real_claude": {"status": "NOT RUN", "requested": false, "reason": "...", "cases": []},
  "not_run": ["real_eda", "real_claude", "hardware_test", "network_calls"],
  "not_proof": ["..."]
}
```

## NOT RUN / not proof

* `real_eda`, `real_claude` and `hardware_test` are `NOT RUN`: this benchmark
  never touches EDA, a daemon, a connector, hardware or a real model.
* `not_proof` in `results.json` restates what the numbers do **not** mean:
  fake-agent outcomes are not model-behaviour evidence, mounted plugin/system
  prompt is not proof the Skill was read, and contract checks are not
  engineering verification.

## Notes

* The event `since` cursor is **exclusive** (`GET .../events?since=N` returns
  events with `seq > N`). Polling clients must use the last observed event's
  `seq` as the next cursor; the benchmark asserts the stub connector does this
  (`event_count` == launcher evidence count).
* The launcher state dir, token file and plugin cache live in a per-run
  temporary directory and are deleted afterwards; `results.json` contains no
  absolute paths and no token.
* The benchmark is a frozen benchmark: changing an expected outcome is a
  reviewable change to `cases/*/expected.json`, not a runner tweak.
