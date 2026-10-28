"""Zhigou task launcher (B1-LAUNCH) — offline sidecar PoC.

The launcher is the "controlled agent" half of B1: an EDA-side trigger surface
calls this local HTTP sidecar with a ``task.start`` request, the sidecar builds
a Claude Code plugin (Skill + routing prompt + offline MCP tools), starts a
headless agent with a fixed argv (never a shell string) and streams
``stream-json`` events and a final result back to the caller.

Scope of this PoC:

* read-only tasks only (``mode == "read_only"``); write mode is refused;
* no EDA, no daemon, no connector, no network calls are made by the launcher;
* task state is written below the launcher state directory only
  (``~/.zhigou-launcher`` or ``%LOCALAPPDATA%\\zhigou-launcher``),
  never into the repository or a project directory;
* the only agent used by the tests and the benchmark is the bundled fake
  agent; a real Claude Code run is OPTIONAL and reported as ``NOT RUN``
  unless explicitly requested.

Version constants are intentionally independent of the design-hardware Skill
version and of the (unmerged) EDA toolchain runtime on the parallel branch.
"""

from __future__ import annotations

__version__ = "0.1.0"

#: Schema identifier of the trigger-side request (EDA plugin -> launcher).
START_SCHEMA = "zhigou.task-launcher.start/v1"
#: Schema identifier of the terminal result document.
RESULT_SCHEMA = "zhigou.task-launcher.result/v1"
#: Schema identifier of a single streamed event.
EVENT_SCHEMA = "zhigou.task-launcher.event/v1"
#: Schema identifier of the plugin build manifest.
PLUGIN_MANIFEST_SCHEMA = "zhigou.task-launcher.plugin-manifest/v1"
#: Schema identifier of the frozen benchmark result document.
BENCHMARK_SCHEMA = "zhigou.task-launcher.benchmark/v1"

#: Local HTTP endpoint. 23121 follows the (unmerged) toolchain's 23111-23120
#: daemon range on purpose: one port block for "zhigou on the loopback".
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 23121

#: Read-only mode is the only mode this PoC accepts.
READ_ONLY_MODE = "read_only"
SUPPORTED_MODES = (READ_ONLY_MODE,)

#: Per-task agent timeout bounds (seconds) and event cap.
DEFAULT_TIMEOUT_S = 180
MIN_TIMEOUT_S = 10
MAX_TIMEOUT_S = 1800
DEFAULT_MAX_EVENTS = 10000
MIN_MAX_EVENTS = 100
MAX_MAX_EVENTS = 100000

#: Claude Code plugin identity. The plugin *package* version is owned by this
#: launcher (`PLUGIN_VERSION`); the bundled Skill version is carried next to it
#: in ``plugin.json`` as ``skill_version`` so the two never get confused. That
#: mapping is what the request's ``toolchain.plugin`` field is compared with.
#: The plugin package name stays stable across the Skill rename
#: (design-hardware -> easycirq); the bundled skill directory and the
#: ``skill_version`` follow the actual Skill on disk.
PLUGIN_NAME = "zhigou-design-hardware"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = (
    "Controlled hardware-design Skill loader for the Zhigou task launcher: "
    "read-only EDA review tasks with the offline audit MCP tools."
)
PLUGIN_LICENSE = "Apache-2.0"
#: Skill directory names accepted by the launcher, in preference order.
#: The 2026-10 rename moved ``design-hardware/`` to ``easycirq/``; both layouts
#: are recognised so the launcher also works on a pre-rename checkout.
SKILL_DIR_CANDIDATES = ("easycirq", "design-hardware")

#: Name of the offline MCP server mounted into the task (already on main).
MCP_SERVER_NAME = "zhigou-offline-audit"
#: The 2026-10 rebrand renamed the module `zhigou_mcp` -> `easycirq_mcp`.
#: Both are accepted; ``mcpconfig.detect_mcp_module()`` picks the one that
#: actually exists in the mounted Skill scripts directory.
MCP_MODULE_CANDIDATES = ("easycirq_mcp", "zhigou_mcp")
MCP_MODULE = "zhigou_mcp"  # legacy default kept for callers/tests

#: B1-Bound supervisor mounted alongside (or instead of) the offline audit MCP.
BOUND_SERVER_NAME = "zhigou_bound"
BOUND_MODULE = "task_launcher.bound"
BOUND_SERVE_ARGS = ("-m", "task_launcher.bound", "serve")

#: Read-only tool allow-list handed to the headless agent. No Bash/Write/Edit.
ALLOWED_TOOLS = (
    "Skill",
    "Read",
    "Glob",
    "Grep",
    "mcp__zhigou-offline-audit__offline_audit_capabilities",
    "mcp__zhigou-offline-audit__offline_electrical_review",
    "mcp__zhigou-offline-audit__offline_return_path_audit",
    "mcp__zhigou-offline-audit__offline_delivery_inspect",
    "mcp__zhigou-offline-audit__offline_delivery_audit",
)
ALLOWED_TOOLS_ARG = ",".join(ALLOWED_TOOLS)

#: Capability surface when the B1-Bound supervisor is enabled: only the bound
#: MCP tools are exposed (no direct offline-audit MCP tools), plus read-only
#: built-ins and the Skill loader.
BOUND_ALLOWED_TOOLS = (
    "Skill",
    "Read",
    "Glob",
    "Grep",
    "mcp__zhigou_bound__*",
)
BOUND_ALLOWED_TOOLS_ARG = ",".join(BOUND_ALLOWED_TOOLS)

#: Tools that must never be available to a bound task (belt-and-braces with
#: ``--allowedTools``; the supervisor is still the real gate).
DENIED_TOOLS = (
    "Bash",
    "Write",
    "Edit",
    "NotebookEdit",
    "Agent",
    "Task",
    "WebFetch",
    "WebSearch",
)
DENIED_TOOLS_ARG = ",".join(DENIED_TOOLS)

#: Permission mode used for read-only tasks. `plan` never auto-approves writes.
PERMISSION_MODE = "plan"

#: Fixed honesty fields. They are copied into every result and benchmark row.
REAL_EDA = "NOT RUN"
REAL_EDA_SOURCE = "task_launcher"
FAKE_AGENT_VERSION = "0.0.0-fake"

#: Agent profiles.
AGENT_PROFILE_FAKE = "fake"
AGENT_PROFILE_CLAUDE = "claude"
AGENT_PROFILES = (AGENT_PROFILE_FAKE, AGENT_PROFILE_CLAUDE)

#: Fake agent scenarios consumed by ``task_launcher.fake_agent``.
FAKE_SCENARIOS = ("stream", "slow", "stuck", "badjson", "fail")
DEFAULT_FAKE_SCENARIO = "stream"

#: Terminal and non-terminal task states.
TASK_ACCEPTED = "accepted"
TASK_RUNNING = "running"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"
TASK_TIMEOUT = "timeout"
TASK_CANCELLED = "cancelled"
TERMINAL_STATES = (TASK_COMPLETED, TASK_FAILED, TASK_TIMEOUT, TASK_CANCELLED)

#: CLI exit codes for ``python -m task_launcher run`` and the stub connector.
EXIT_OK = 0
EXIT_TASK_FAILURE = 1
EXIT_PROTOCOL_ERROR = 2

__all__ = [
    "__version__",
    "START_SCHEMA",
    "RESULT_SCHEMA",
    "EVENT_SCHEMA",
    "PLUGIN_MANIFEST_SCHEMA",
    "BENCHMARK_SCHEMA",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "READ_ONLY_MODE",
    "SUPPORTED_MODES",
    "DEFAULT_TIMEOUT_S",
    "MIN_TIMEOUT_S",
    "MAX_TIMEOUT_S",
    "DEFAULT_MAX_EVENTS",
    "MIN_MAX_EVENTS",
    "MAX_MAX_EVENTS",
    "PLUGIN_NAME",
    "PLUGIN_VERSION",
    "PLUGIN_DESCRIPTION",
    "PLUGIN_LICENSE",
    "SKILL_DIR_CANDIDATES",
    "MCP_SERVER_NAME",
    "MCP_MODULE",
    "ALLOWED_TOOLS",
    "ALLOWED_TOOLS_ARG",
    "PERMISSION_MODE",
    "REAL_EDA",
    "REAL_EDA_SOURCE",
    "FAKE_AGENT_VERSION",
    "AGENT_PROFILE_FAKE",
    "AGENT_PROFILE_CLAUDE",
    "AGENT_PROFILES",
    "FAKE_SCENARIOS",
    "DEFAULT_FAKE_SCENARIO",
    "TASK_ACCEPTED",
    "TASK_RUNNING",
    "TASK_COMPLETED",
    "TASK_FAILED",
    "TASK_TIMEOUT",
    "TASK_CANCELLED",
    "TERMINAL_STATES",
    "EXIT_OK",
    "EXIT_TASK_FAILURE",
    "EXIT_PROTOCOL_ERROR",
]
