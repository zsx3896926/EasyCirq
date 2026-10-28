"""Task state machine — the place where "skip a step" becomes impossible.

The agent can only *request* transitions through MCP tools; the supervisor owns
the machine. Every transition is bound to exactly one tool and one receipt
(``receipts.py``), so an out-of-order or duplicated call is rejected with a
stable error code before any evidence can be produced.

Read-only (Phase 1) chain::

    CREATED --task_start--> STARTED --snapshot_read--> SNAPSHOT_READ
            --run_offline_audit--> AUDIT_RUN --evidence_emit--> EVIDENCE_EMITTED
            --finalize--> FINALIZED

Phase 2 (designed, not authorized in this delivery) extends the chain with
``plan_submit -> precheck -> apply -> readback`` before ``evidence_emit``.

Failure/cancel states (``FAILED``/``CANCELLED``/``TIMEOUT``/``INCOMPLETE``) can
never reach ``FINALIZED``; ``finalize`` on a terminal state is refused.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from . import (
    PHASE1_TOOLS,
    PHASE2_TOOLS,
    RISK_NONE,
    RISK_READ_ONLY,
    TOOL_EVIDENCE_EMIT,
    TOOL_FINALIZE,
    TOOL_PLAN_SUBMIT,
    TOOL_PRECHECK,
    TOOL_APPLY,
    TOOL_READBACK,
    TOOL_RUN_OFFLINE_AUDIT,
    TOOL_SNAPSHOT_READ,
    TOOL_TASK_ABORT,
    TOOL_TASK_START,
)
from .errors import (
    LIMIT_EXCEEDED,
    OUT_OF_ORDER,
    PHASE_NOT_ENABLED,
    STEP_ALREADY_DONE,
    TASK_CLOSED,
    TOOL_NOT_ALLOWED,
    BoundError,
)

#: Canonical state names.
CREATED = "CREATED"
STARTED = "STARTED"
SNAPSHOT_READ = "SNAPSHOT_READ"
PLAN_SUBMITTED = "PLAN_SUBMITTED"
PRECHECKED = "PRECHECKED"
APPLIED = "APPLIED"
READBACK_DONE = "READBACK_DONE"
AUDIT_RUN = "AUDIT_RUN"
EVIDENCE_EMITTED = "EVIDENCE_EMITTED"
FINALIZED = "FINALIZED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
TIMEOUT = "TIMEOUT"
INCOMPLETE = "INCOMPLETE"

TERMINAL_STATES = (FINALIZED, FAILED, CANCELLED, TIMEOUT, INCOMPLETE)
FAILURE_STATES = (FAILED, CANCELLED, TIMEOUT, INCOMPLETE)


@dataclass(frozen=True)
class Transition:
    tool: str
    required_state: str
    next_state: str
    risk: str
    phase: int


#: Phase 1 read-only transitions (order matters: it is the receipt step order).
PHASE1_TRANSITIONS: tuple[Transition, ...] = (
    Transition(TOOL_TASK_START, CREATED, STARTED, RISK_NONE, 1),
    Transition(TOOL_SNAPSHOT_READ, STARTED, SNAPSHOT_READ, RISK_READ_ONLY, 1),
    Transition(TOOL_RUN_OFFLINE_AUDIT, SNAPSHOT_READ, AUDIT_RUN, RISK_READ_ONLY, 1),
    Transition(TOOL_EVIDENCE_EMIT, AUDIT_RUN, EVIDENCE_EMITTED, RISK_READ_ONLY, 1),
    Transition(TOOL_FINALIZE, EVIDENCE_EMITTED, FINALIZED, RISK_READ_ONLY, 1),
)

#: Phase 2 controlled-write transitions (kept for the contract; not authorized).
PHASE2_TRANSITIONS: tuple[Transition, ...] = (
    Transition(TOOL_TASK_START, CREATED, STARTED, RISK_NONE, 2),
    Transition(TOOL_SNAPSHOT_READ, STARTED, SNAPSHOT_READ, RISK_READ_ONLY, 2),
    Transition(TOOL_PLAN_SUBMIT, SNAPSHOT_READ, PLAN_SUBMITTED, RISK_NONE, 2),
    Transition(TOOL_PRECHECK, PLAN_SUBMITTED, PRECHECKED, RISK_READ_ONLY, 2),
    Transition(TOOL_APPLY, PRECHECKED, APPLIED, "write", 2),
    Transition(TOOL_READBACK, APPLIED, READBACK_DONE, "write", 2),
    Transition(TOOL_RUN_OFFLINE_AUDIT, READBACK_DONE, AUDIT_RUN, RISK_READ_ONLY, 2),
    Transition(TOOL_EVIDENCE_EMIT, AUDIT_RUN, EVIDENCE_EMITTED, RISK_READ_ONLY, 2),
    Transition(TOOL_FINALIZE, EVIDENCE_EMITTED, FINALIZED, RISK_READ_ONLY, 2),
)


def transitions_for(phase: int) -> tuple[Transition, ...]:
    if phase == 1:
        return PHASE1_TRANSITIONS
    if phase == 2:
        return PHASE2_TRANSITIONS
    raise BoundError(PHASE_NOT_ENABLED, f"unsupported phase {phase!r}", {"phase": phase})


def required_steps(phase: int) -> tuple[str, ...]:
    return tuple(transition.tool for transition in transitions_for(phase))


@dataclass
class Step:
    seq: int
    tool: str
    previous_state: str
    state: str
    at: str
    risk: str = RISK_READ_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tool": self.tool,
            "from": self.previous_state,
            "to": self.state,
            "at": self.at,
            "risk": self.risk,
        }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class TaskMachine:
    task_id: str
    phase: int = 1
    state: str = CREATED
    steps: list[Step] = field(default_factory=list)
    tool_calls: int = 0
    abort_reason: str | None = None
    _transitions: tuple[Transition, ...] = field(init=False, repr=False)
    _last_call_monotonic: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._transitions = transitions_for(self.phase)

    # -- introspection -----------------------------------------------------
    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def completed_steps(self) -> list[str]:
        return [step.tool for step in self.steps]

    def next_required_step(self) -> str | None:
        done = set(self.completed_steps())
        for transition in self._transitions:
            if transition.tool not in done:
                return transition.tool
        return None

    def remaining_steps(self) -> list[str]:
        done = set(self.completed_steps())
        return [transition.tool for transition in self._transitions if transition.tool not in done]

    def find_transition(self, tool: str) -> Transition | None:
        for transition in self._transitions:
            if transition.tool == tool:
                return transition
        return None

    # -- enforcement -------------------------------------------------------
    def check_tool(self, tool: str, *, limits: Any = None) -> Transition:
        """Validate a prospective tool call without mutating the machine.

        Raises :class:`BoundError` with a stable code on any violation.
        """

        if self.terminal:
            raise BoundError(
                TASK_CLOSED,
                f"task is in terminal state {self.state}; no further tools are accepted",
                {"state": self.state, "tool": tool},
            )
        if tool == TOOL_TASK_ABORT:
            return Transition(TOOL_TASK_ABORT, self.state, CANCELLED, RISK_NONE, self.phase)
        if tool in PHASE2_TOOLS and tool not in PHASE1_TOOLS and self.phase == 1:
            raise BoundError(
                PHASE_NOT_ENABLED,
                f"{tool} is a Phase 2 write tool and Phase 2 is not enabled in this delivery",
                {"tool": tool, "phase": self.phase},
                status=403,
            )
        transition = self.find_transition(tool)
        if transition is None:
            if tool in PHASE2_TOOLS and self.phase != 2:
                raise BoundError(PHASE_NOT_ENABLED, f"{tool} is not enabled", {"tool": tool})
            raise BoundError(TOOL_NOT_ALLOWED, f"tool is not part of Phase {self.phase}", {"tool": tool})
        if tool in self.completed_steps():
            raise BoundError(
                STEP_ALREADY_DONE,
                f"{tool} already produced a signed receipt; steps cannot be repeated",
                {"tool": tool, "state": self.state},
            )
        if self.state != transition.required_state:
            raise BoundError(
                OUT_OF_ORDER,
                f"{tool} requires state {transition.required_state}, current state is {self.state}",
                {
                    "tool": tool,
                    "state": self.state,
                    "required_state": transition.required_state,
                    "next": self.next_required_step(),
                },
                status=409,
            )
        if limits is not None:
            if self.tool_calls + 1 > int(limits.max_tool_calls):
                raise BoundError(
                    LIMIT_EXCEEDED,
                    "maximum tool calls for this task exceeded",
                    {"limit": int(limits.max_tool_calls), "calls": self.tool_calls + 1},
                    status=429,
                )
            if len(self.steps) + 1 > int(limits.max_steps):
                raise BoundError(
                    LIMIT_EXCEEDED,
                    "maximum steps for this task exceeded",
                    {"limit": int(limits.max_steps), "steps": len(self.steps) + 1},
                    status=429,
                )
            interval = float(getattr(limits, "min_tool_interval_s", 0.0) or 0.0)
            if interval > 0 and self._last_call_monotonic:
                elapsed = time.monotonic() - self._last_call_monotonic
                if elapsed < interval:
                    raise BoundError(
                        "RATE_LIMITED",
                        "tool calls arrive faster than the configured rate limit",
                        {"min_interval_s": interval, "elapsed_s": round(elapsed, 3)},
                        status=429,
                    )
        return transition

    def apply(
        self,
        tool: str,
        *,
        limits: Any = None,
        now: str | None = None,
        abort_reason: str | None = None,
    ) -> Step:
        transition = self.check_tool(tool, limits=limits)
        self.tool_calls += 1
        self._last_call_monotonic = time.monotonic()
        if tool == TOOL_TASK_ABORT:
            self.abort_reason = abort_reason
            abort_step = Step(
                seq=len(self.steps),
                tool=tool,
                previous_state=self.state,
                state=CANCELLED,
                at=now or _now_iso(),
                risk=RISK_NONE,
            )
            self.steps.append(abort_step)
            self.state = CANCELLED
            return abort_step
        step = Step(
            seq=len(self.steps),
            tool=tool,
            previous_state=self.state,
            state=transition.next_state,
            at=now or _now_iso(),
            risk=transition.risk,
        )
        self.steps.append(step)
        self.state = transition.next_state
        return step

    # -- terminal helpers --------------------------------------------------
    def mark_failed(self, reason: str, *, state: str = FAILED) -> None:
        if self.terminal:
            return
        self.state = state
        self.abort_reason = reason

    def abort(self, reason: str) -> None:
        if self.terminal:
            raise BoundError(
                TASK_CLOSED,
                f"task is already terminal ({self.state})",
                {"state": self.state},
            )
        self.abort_reason = reason
        self.state = CANCELLED

    def mark_incomplete(self, reason: str) -> None:
        self.abort_reason = reason
        self.state = INCOMPLETE

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase": self.phase,
            "state": self.state,
            "terminal": self.terminal,
            "steps": [step.to_dict() for step in self.steps],
            "tool_calls": self.tool_calls,
            "remaining": self.remaining_steps(),
            "abort_reason": self.abort_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskMachine":
        machine = cls(task_id=data["task_id"], phase=int(data.get("phase", 1)))
        machine.state = data.get("state", CREATED)
        machine.tool_calls = int(data.get("tool_calls", 0))
        machine.abort_reason = data.get("abort_reason")
        for row in data.get("steps") or []:
            machine.steps.append(
                Step(
                    seq=int(row["seq"]),
                    tool=row["tool"],
                    previous_state=row["from"],
                    state=row["to"],
                    at=row["at"],
                    risk=row.get("risk", RISK_READ_ONLY),
                )
            )
        return machine
