#!/usr/bin/env python3
"""Validate the frozen dev scenario set for the skill-knowledge-audit planner.

Usage (standard library only, Python 3.10+):

    python benchmarks/skill-knowledge-audit/scenarios/validate_scenarios.py
    python benchmarks/skill-knowledge-audit/scenarios/validate_scenarios.py --json-path <dev.json> --root <repo root>

Contract:
  - stdout carries exactly one UTF-8 JSON object: {"ok": bool, "errors": [...]}
  - exit 0 = valid; 1 = validation errors; 2 = usage / IO / invalid JSON input

Checks:
  - top-level schema strings, frozen baseline, split, exactly 15 dev scenarios,
    unique ordered ids dev-01..dev-15
  - intent schema/task_type/stage vocabularies, required field types,
    budget_chars positive int when present, already_read entry shape and paths
  - expected lists: types, no duplicate entries, count ranges, required/optional/
    excluded disjointness, all referenced paths are POSIX relative paths that
    exist as files inside the worktree, SKILL.md entry, Lead-frozen always set
    (SKILL.md + workflow.md + evidence.md) and design-gates.md for gate scoped
    task types
  - required_unknown codes in the contract §6.2 code list,
    forbidden_plan_actions in the execution_contract action list,
    required_approval_gates in the Lead-frozen gate token list and a subset of
    intent.user_decision_pending (planner copies, never infers)
  - rationale non-empty, max_selected_bytes null or positive int
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCENARIO_SCHEMA = "ska-scenarios/v1"
INTENT_SCHEMA = "ska-intent/v1"
SPLIT = "dev"
EXPECTED_IDS = [f"dev-{i:02d}" for i in range(1, 16)]
BASELINE_GIT_SHA = "9a951edc21481dc3ae91460acc11aa3e08a7be8a"
CATALOG_VERSION = "2026-10-27.1"

TASK_TYPES = {
    "schematic_new",
    "schematic_edit",
    "pcb_layout",
    "pcb_route",
    "four_layer_diff",
    "bom_only",
    "review_only",
    "delivery_audit",
    "offline_dev",
    "full_product",
    "knowledge_only",
}
STAGES = {
    "read",
    "requirements",
    "concept",
    "schematic",
    "layout",
    "route",
    "check",
    "delivery",
    "firmware",
    "build",
    "unknown",
}
# contract.md §6.2 execution_contract actions
ACTIONS = [
    "read_skill",
    "write_eda",
    "read_eda",
    "network",
    "install",
    "wait_user_approval",
    "review_only",
    "offline_analysis",
    "order_parts",
]
# contract.md §6.2 unknown codes
UNKNOWN_CODES = [
    "task_unknown",
    "stage_unspecified",
    "domain_unspecified",
    "eda_unavailable",
    "budget_insufficient",
    "cache_invalidated",
    "file_missing",
    "required_dependency_missing",
    "already_read_stale",
]
# Lead-frozen approval gate tokens (contract §6.2 addendum)
GATE_TOKENS = [
    "before_layout",
    "before_route",
    "before_delivery",
    "before_manufacturing",
    "scope_change",
    "interface_change",
    "cost_change",
    "mechanical_change",
    "missing_evidence",
]
# contract.md §6.2 item 1 + Lead decision: always protection documents
ALWAYS_INCLUDE = [
    "design-hardware/SKILL.md",
    "design-hardware/references/workflow.md",
    "design-hardware/references/evidence.md",
]
# Lead decision: design-gates.md required for schematic/PCB/layout/route/delivery
DESIGN_GATES_REQUIRED_TYPES = {
    "schematic_new",
    "schematic_edit",
    "pcb_layout",
    "pcb_route",
    "four_layer_diff",
    "delivery_audit",
    "full_product",
}
MUST_INCLUDE_MIN, MUST_INCLUDE_MAX = 3, 8
MUST_EXCLUDE_MIN, MUST_EXCLUDE_MAX = 2, 6
MAY_INCLUDE_MIN, MAY_INCLUDE_MAX = 0, 4


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _check_string_list(
    errors: list[str], where: str, value: object, *, allow_empty: bool = True
) -> bool:
    if not isinstance(value, list):
        errors.append(f"{where}: expected a list, got {type(value).__name__}")
        return False
    if not allow_empty and not value:
        errors.append(f"{where}: must not be empty")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{where}[{index}]: expected a non-empty string")
    return True


def _check_duplicates(errors: list[str], where: str, value: list[str]) -> None:
    seen: set[str] = set()
    for item in value:
        if item in seen:
            errors.append(f"{where}: duplicate entry {item!r}")
        seen.add(item)


def _resolve_relative_path(root: Path, value: str) -> Path | None:
    """Return the resolved file path for a POSIX worktree-relative path, or None."""
    if value != value.strip():
        return None
    if "\\" in value or value.startswith("/") or value.startswith("../") or ".." in value.split("/"):
        return None
    if not value.startswith("design-hardware/"):
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _check_paths(
    errors: list[str], root: Path, where: str, values: list[str]
) -> None:
    for value in values:
        resolved = _resolve_relative_path(root, value)
        if resolved is None:
            errors.append(
                f"{where}: referenced path is not an existing worktree file: {value!r}"
            )


def _check_scenario(
    errors: list[str],
    root: Path,
    scenario: object,
    index: int,
    seen_ids: set[str],
) -> None:
    where = f"scenarios[{index}]"
    if not isinstance(scenario, dict):
        errors.append(f"{where}: expected an object")
        return
    scenario_id = scenario.get("id")
    if not isinstance(scenario_id, str) or not scenario_id:
        errors.append(f"{where}.id: expected a non-empty string")
    else:
        where = scenario_id
        if scenario_id in seen_ids:
            errors.append(f"{scenario_id}: duplicate scenario id")
        seen_ids.add(scenario_id)

    if not isinstance(scenario.get("title"), str) or not scenario.get("title", "").strip():
        errors.append(f"{where}.title: expected a non-empty string")
    if not isinstance(scenario.get("rationale"), str) or not scenario.get("rationale", "").strip():
        errors.append(f"{where}.rationale: expected a non-empty string")

    intent = scenario.get("intent")
    if not isinstance(intent, dict):
        errors.append(f"{where}.intent: expected an object")
        return
    if intent.get("schema") != INTENT_SCHEMA:
        errors.append(f"{where}.intent.schema: expected {INTENT_SCHEMA!r}")
    task_type = intent.get("task_type")
    if task_type not in TASK_TYPES:
        errors.append(f"{where}.intent.task_type: invalid task type {task_type!r}")
    stage = intent.get("stage")
    if stage not in STAGES:
        errors.append(f"{where}.intent.stage: invalid stage {stage!r}")
    for flag in ("autonomous_authorized", "eda_available"):
        if not isinstance(intent.get(flag), bool):
            errors.append(f"{where}.intent.{flag}: expected a bool")

    for field in ("deliverables", "constraints", "user_decision_pending"):
        _check_string_list(errors, f"{where}.intent.{field}", intent.get(field))
    decisions = intent.get("user_decision_pending")
    if isinstance(decisions, list):
        for token in decisions:
            if token not in GATE_TOKENS:
                errors.append(
                    f"{where}.intent.user_decision_pending: unknown gate token {token!r}"
                )

    if "budget_chars" in intent and not _is_positive_int(intent["budget_chars"]):
        errors.append(f"{where}.intent.budget_chars: expected a positive int")

    already_read = intent.get("already_read")
    if not isinstance(already_read, list):
        errors.append(f"{where}.intent.already_read: expected a list")
    else:
        for read_index, entry in enumerate(already_read):
            entry_where = f"{where}.intent.already_read[{read_index}]"
            if not isinstance(entry, dict):
                errors.append(f"{entry_where}: expected an object")
                continue
            path = entry.get("path")
            if not isinstance(path, str) or _resolve_relative_path(root, path) is None:
                errors.append(f"{entry_where}.path: not an existing worktree file: {path!r}")
            sha = entry.get("sha256")
            if not isinstance(sha, str) or len(sha) != 64 or any(
                c not in "0123456789abcdef" for c in sha
            ):
                errors.append(f"{entry_where}.sha256: expected lowercase 64-hex string")
            for key in ("rules_version", "scope"):
                if not isinstance(entry.get(key), str) or not entry.get(key, "").strip():
                    errors.append(f"{entry_where}.{key}: expected a non-empty string")

    expected = scenario.get("expected")
    if not isinstance(expected, dict):
        errors.append(f"{where}.expected: expected an object")
        return

    lists: dict[str, list[str]] = {}
    for key in ("must_include", "must_exclude", "may_include"):
        value = expected.get(key)
        if not _check_string_list(errors, f"{where}.expected.{key}", value):
            continue
        lists[key] = value
        _check_duplicates(errors, f"{where}.expected.{key}", value)
        _check_paths(errors, root, f"{where}.expected.{key}", value)

    must = lists.get("must_include")
    if must is not None:
        if not (MUST_INCLUDE_MIN <= len(must) <= MUST_INCLUDE_MAX):
            errors.append(
                f"{where}.expected.must_include: expected {MUST_INCLUDE_MIN}-{MUST_INCLUDE_MAX} files, "
                f"got {len(must)}"
            )
        if "design-hardware/SKILL.md" not in must:
            errors.append(f"{where}.expected.must_include: missing entry document design-hardware/SKILL.md")
        if task_type in TASK_TYPES:
            for always in ALWAYS_INCLUDE[1:]:
                if always not in must:
                    errors.append(
                        f"{where}.expected.must_include: missing always document {always}"
                    )
            if task_type in DESIGN_GATES_REQUIRED_TYPES and (
                "design-hardware/references/design-gates.md" not in must
            ):
                errors.append(
                    f"{where}.expected.must_include: missing design-gates.md for {task_type}"
                )
    exclude = lists.get("must_exclude")
    if exclude is not None and not (
        MUST_EXCLUDE_MIN <= len(exclude) <= MUST_EXCLUDE_MAX
    ):
        errors.append(
            f"{where}.expected.must_exclude: expected {MUST_EXCLUDE_MIN}-{MUST_EXCLUDE_MAX} files, "
            f"got {len(exclude)}"
        )
    may = lists.get("may_include")
    if may is not None and not (MAY_INCLUDE_MIN <= len(may) <= MAY_INCLUDE_MAX):
        errors.append(
            f"{where}.expected.may_include: expected {MAY_INCLUDE_MIN}-{MAY_INCLUDE_MAX} files, "
            f"got {len(may)}"
        )

    if must is not None and exclude is not None:
        overlap = sorted(set(must) & set(exclude))
        if overlap:
            errors.append(f"{where}.expected: must_include overlaps must_exclude: {overlap}")
    if must is not None and may is not None:
        overlap = sorted(set(must) & set(may))
        if overlap:
            errors.append(f"{where}.expected: must_include overlaps may_include: {overlap}")
    if exclude is not None and may is not None:
        overlap = sorted(set(exclude) & set(may))
        if overlap:
            errors.append(f"{where}.expected: must_exclude overlaps may_include: {overlap}")

    unknown = expected.get("required_unknown")
    if _check_string_list(errors, f"{where}.expected.required_unknown", unknown):
        _check_duplicates(errors, f"{where}.expected.required_unknown", unknown)
        for code in unknown:
            if code not in UNKNOWN_CODES:
                errors.append(
                    f"{where}.expected.required_unknown: code not in contract §6.2 list: {code!r}"
                )

    actions = expected.get("forbidden_plan_actions")
    if _check_string_list(errors, f"{where}.expected.forbidden_plan_actions", actions):
        _check_duplicates(errors, f"{where}.expected.forbidden_plan_actions", actions)
        for action in actions:
            if action not in ACTIONS:
                errors.append(
                    f"{where}.expected.forbidden_plan_actions: action not in "
                    f"execution_contract list: {action!r}"
                )

    gates = expected.get("required_approval_gates")
    if _check_string_list(errors, f"{where}.expected.required_approval_gates", gates):
        _check_duplicates(errors, f"{where}.expected.required_approval_gates", gates)
        for gate in gates:
            if gate not in GATE_TOKENS:
                errors.append(
                    f"{where}.expected.required_approval_gates: unknown gate token {gate!r}"
                )
        if isinstance(decisions, list):
            missing = [gate for gate in gates if gate not in decisions]
            if missing:
                errors.append(
                    f"{where}.expected.required_approval_gates: {missing} not present in "
                    f"intent.user_decision_pending (planner copies, never infers)"
                )

    max_bytes = expected.get("max_selected_bytes")
    if max_bytes is not None and not _is_positive_int(max_bytes):
        errors.append(f"{where}.expected.max_selected_bytes: expected null or a positive int")


def validate(document: object, root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["document: top-level JSON value must be an object"]

    if document.get("schema") != SCENARIO_SCHEMA:
        errors.append(f"schema: expected {SCENARIO_SCHEMA!r}")
    if document.get("split") != SPLIT:
        errors.append(f"split: expected {SPLIT!r}")

    frozen = document.get("frozen")
    if not isinstance(frozen, dict):
        errors.append("frozen: expected an object")
    else:
        if frozen.get("git_sha") != BASELINE_GIT_SHA:
            errors.append(f"frozen.git_sha: expected frozen baseline {BASELINE_GIT_SHA}")
        if frozen.get("catalog_version") != CATALOG_VERSION:
            errors.append(f"frozen.catalog_version: expected {CATALOG_VERSION!r}")

    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("scenarios: expected a list")
        return errors
    if len(scenarios) != len(EXPECTED_IDS):
        errors.append(
            f"scenarios: expected exactly {len(EXPECTED_IDS)} dev scenarios, got {len(scenarios)}"
        )

    seen_ids: set[str] = set()
    for index, scenario in enumerate(scenarios):
        _check_scenario(errors, root, scenario, index, seen_ids)

    expected_set = set(EXPECTED_IDS)
    missing = sorted(expected_set - seen_ids)
    unexpected = sorted(seen_ids - expected_set)
    if missing:
        errors.append(f"scenarios: missing ids {missing}")
    if unexpected:
        errors.append(f"scenarios: unexpected ids {unexpected}")
    ordered = [
        scenario.get("id")
        for scenario in scenarios
        if isinstance(scenario, dict) and isinstance(scenario.get("id"), str)
    ]
    if ordered != EXPECTED_IDS and not missing and not unexpected:
        errors.append("scenarios: ids must be ordered dev-01 .. dev-15")
    return errors


def main(argv: list[str] | None = None) -> int:
    default_json = Path(__file__).resolve().with_name("dev.json")
    default_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Validate benchmarks/skill-knowledge-audit/scenarios/dev.json."
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=default_json,
        help="path to the scenario JSON file (default: %(default)s)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help="worktree root used to resolve scenario paths (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    def emit(ok: bool, errors: list[str], code: int) -> int:
        print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False, sort_keys=True))
        return code

    try:
        text = args.json_path.read_text(encoding="utf-8")
    except OSError as exc:
        return emit(False, [f"input: cannot read {args.json_path}: {exc}"], 2)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return emit(False, [f"input: invalid JSON in {args.json_path}: {exc}"], 2)

    root = args.root.resolve()
    if not root.is_dir():
        return emit(False, [f"input: worktree root is not a directory: {root}"], 2)
    if not (root / "design-hardware" / "SKILL.md").is_file():
        return emit(
            False,
            [f"input: worktree root does not contain design-hardware/SKILL.md: {root}"],
            2,
        )

    try:
        errors = validate(document, root)
    except Exception as exc:  # defensive: a validator bug must not masquerade as valid
        return emit(False, [f"internal: validator error: {type(exc).__name__}: {exc}"], 2)
    return emit(not errors, errors, 0 if not errors else 1)


if __name__ == "__main__":
    sys.exit(main())
