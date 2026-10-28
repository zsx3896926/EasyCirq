"""D5: frozen scenario benchmark, metrics and transformation checks."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import CATALOG_VERSION, NOT_PROOF, SCHEMA, TOOL_NAME, VERSION
from .common import (AuditError, atomic_write_text, canonical_json,
                     git_sha_for, stable_digest, utc_now)
from .plan import build_plan, load_catalog
from .scan import scan_root

SCENARIO_SCHEMA = "ska-scenarios/v1"
RESULT_SCHEMA = "ska-benchmark-result/v1"
ALLOWED_TASK_TYPES = {
    "schematic_new", "schematic_edit", "pcb_layout", "pcb_route",
    "four_layer_diff", "bom_only", "review_only", "delivery_audit",
    "offline_dev", "full_product", "knowledge_only",
}
UNKNOWN_CODES = {
    "task_unknown", "stage_unspecified", "domain_unspecified",
    "eda_unavailable", "budget_insufficient", "cache_invalidated",
    "file_missing", "required_dependency_missing", "already_read_stale",
}
ACTIONS = {
    "read_skill", "write_eda", "read_eda", "network", "install",
    "wait_user_approval", "review_only", "offline_analysis", "order_parts",
}
GATES = {
    "before_layout", "before_route", "before_delivery", "before_manufacturing",
    "scope_change", "interface_change", "cost_change", "mechanical_change",
    "missing_evidence",
}


def _normalise_path(path, root_name):
    path = str(path).replace("\\", "/")
    prefix = root_name + "/"
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


def load_scenarios(paths, root_name="easycirq"):
    """Load one or more scenario files or a scenarios directory."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    candidates = []
    for item in paths:
        path = Path(item)
        if path.is_dir():
            candidates.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            candidates.append(path)
        else:
            raise AuditError(f"scenario path does not exist: {item}")
    if not candidates:
        raise AuditError("no scenario JSON files found")
    scenarios = []
    warnings = []
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise AuditError(f"cannot read scenario file {path}: {exc}")
        if not isinstance(data, dict) or data.get("schema") != SCENARIO_SCHEMA:
            raise AuditError(f"{path.name}: schema must be {SCENARIO_SCHEMA}")
        split = data.get("split")
        if split not in ("dev", "holdout"):
            raise AuditError(f"{path.name}: split must be dev or holdout")
        frozen = data.get("frozen") or {}
        if frozen.get("catalog_version") not in (None, CATALOG_VERSION):
            warnings.append({
                "file": path.name, "warning": "frozen catalog_version differs",
                "frozen": frozen.get("catalog_version"),
                "current": CATALOG_VERSION,
            })
        for scenario in data.get("scenarios", []):
            scenario = dict(scenario)
            scenario["_split"] = split
            scenario["_file"] = path.name
            scenarios.append(scenario)
    ids = set()
    for scenario in scenarios:
        sid = scenario.get("id")
        if not sid or sid in ids:
            raise AuditError(f"duplicate or empty scenario id: {sid}")
        ids.add(sid)
        expected = scenario.get("expected") or {}
        for key in ("must_include", "must_exclude", "may_include",
                    "required_unknown", "forbidden_plan_actions",
                    "required_approval_gates"):
            if key not in expected:
                raise AuditError(f"{sid}: expected.{key} is required")
        intent = scenario.get("intent") or {}
        if intent.get("task_type") not in ALLOWED_TASK_TYPES:
            raise AuditError(f"{sid}: invalid task_type {intent.get('task_type')}")
        for code in expected["required_unknown"]:
            if code not in UNKNOWN_CODES:
                raise AuditError(f"{sid}: unknown required_unknown code {code}")
        for action in expected["forbidden_plan_actions"]:
            if action not in ACTIONS:
                raise AuditError(f"{sid}: unknown forbidden action {action}")
        for gate in expected["required_approval_gates"]:
            if gate not in GATES:
                raise AuditError(f"{sid}: unknown approval gate {gate}")
        if not scenario.get("rationale"):
            raise AuditError(f"{sid}: rationale is required")
    return scenarios, warnings


def _selected_paths(plan):
    return {item["path"] for item in plan.get("selected", [])}


def _required_paths(plan):
    return {item["path"] for item in plan.get("required", [])}


def evaluate_plan(scenario, plan, all_markdown_bytes):
    expected = scenario["expected"]
    root_name = "easycirq"
    must = {_normalise_path(path, root_name) for path in expected["must_include"]}
    must_not = {_normalise_path(path, root_name)
                for path in expected["must_exclude"]}
    may = {_normalise_path(path, root_name) for path in expected["may_include"]}
    selected = _selected_paths(plan)
    required = _required_paths(plan)
    unknown_codes = {item["code"] for item in plan.get("unknown", [])}
    actions = set(plan["execution_contract"]["actions"])
    gates = set(plan["execution_contract"]["approval_gates"])
    missing_critical = sorted(must - required)
    forbidden_selected = sorted(must_not & selected)
    missing_unknown = sorted(set(expected["required_unknown"]) - unknown_codes)
    forbidden_actions = sorted(set(expected["forbidden_plan_actions"]) & actions)
    missing_gates = sorted(set(expected["required_approval_gates"]) - gates)
    unrelated = sorted(selected - must - may)
    unrelated_bytes = sum(
        item["bytes"] for item in plan.get("selected", [])
        if item["path"] in unrelated)
    max_bytes = expected.get("max_selected_bytes")
    selected_bytes = plan["budget"]["selected_bytes"]
    over_budget = bool(max_bytes and selected_bytes > max_bytes)
    passed = not any((missing_critical, forbidden_selected, missing_unknown,
                      forbidden_actions, missing_gates, over_budget))
    return {
        "scenario": scenario["id"],
        "split": scenario.get("_split", scenario.get("split")),
        "title": scenario.get("title", ""),
        "pass": passed,
        "missing_critical": missing_critical,
        "required_recall": round(
            (len(must) - len(missing_critical)) / len(must), 4) if must else 1.0,
        "required_total": len(must),
        "forbidden_selected": forbidden_selected,
        "unknown_expected_missing": missing_unknown,
        "forbidden_actions": forbidden_actions,
        "missing_approval_gates": missing_gates,
        "unrelated": unrelated,
        "unrelated_bytes": unrelated_bytes,
        "selected_bytes": selected_bytes,
        "baseline_all_markdown_bytes": all_markdown_bytes,
        "selected_vs_baseline_ratio": round(
            selected_bytes / all_markdown_bytes, 4) if all_markdown_bytes else None,
        "budget_status": plan["budget"]["status"],
        "plan_ok": bool(plan.get("ok")),
        "plan_digest": stable_digest({
            "selected": sorted(_selected_paths(plan)),
            "unknown": sorted(unknown_codes),
            "gates": sorted(gates),
            "actions": sorted(actions),
        }),
        "duration_ms": plan["source"]["duration_ms"],
        "execution_contract": plan["execution_contract"],
    }


def run_benchmark(root, scenarios, catalog, *, stability=True, allocate_cache=True,
                  exclude_paths=()):
    results = []
    started = time.perf_counter()
    scan_context = scan_root(root, exclude_abs=exclude_paths)
    available = set(scan_context[1]["records"])
    for scenario in scenarios:
        for key in ("must_include", "must_exclude", "may_include"):
            for path in scenario["expected"].get(key, []):
                rel = _normalise_path(path, "easycirq")
                if rel not in available and not (Path(root) / rel).is_file():
                    raise AuditError(
                        f"{scenario['id']}: expected.{key} path does not exist: "
                        f"{path}")
    all_bytes = sum(record.bytes for record in scan_context[1]["records"].values())
    for scenario in scenarios:
        intent = scenario["intent"]
        plan, context = build_plan(root, intent, catalog,
                                   scan_context=scan_context)
        metrics = evaluate_plan(scenario, plan, 0)
        metrics["baseline_all_markdown_bytes"] = all_bytes
        if metrics["baseline_all_markdown_bytes"]:
            metrics["selected_vs_baseline_ratio"] = round(
                metrics["selected_bytes"]
                / metrics["baseline_all_markdown_bytes"], 4)
        if stability:
            plan2, _ = build_plan(root, intent, catalog,
                                   scan_context=scan_context)
            digest2 = stable_digest({
                "selected": sorted(_selected_paths(plan2)),
                "unknown": sorted({item["code"] for item in plan2.get("unknown", [])}),
                "gates": sorted(set(plan2["execution_contract"]["approval_gates"])),
                "actions": sorted(set(plan2["execution_contract"]["actions"])),
            })
            metrics["stable"] = digest2 == metrics["plan_digest"]
            if not metrics["stable"]:
                metrics["pass"] = False
        else:
            metrics["stable"] = None
        if allocate_cache:
            metrics["cache_hit"] = len(plan["cache"]["hit"])
            metrics["cache_invalidated"] = len(plan["cache"]["invalidated"])
        results.append(metrics)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    passed = sum(1 for item in results if item["pass"])
    dev = [item for item in results if item["split"] == "dev"]
    holdout = [item for item in results if item["split"] == "holdout"]
    required_total = sum(item["required_total"] for item in results)
    required_hit = sum(
        item["required_total"] - len(item["missing_critical"])
        for item in results)
    return {
        "schema": RESULT_SCHEMA,
        "schema_version": SCHEMA,
        "tool": {"name": TOOL_NAME, "version": VERSION},
        "source": {
            "root": str(Path(root)),
            "git_sha": git_sha_for(root),
            "scanned_at": utc_now(),
            "duration_ms": duration_ms,
        },
        "catalog_version": CATALOG_VERSION,
        "scenarios": {
            "total": len(results),
            "dev": len(dev),
            "holdout": len(holdout),
            "passed": passed,
            "failed": len(results) - passed,
        },
        "metrics": {
            "required_recall": round(required_hit / required_total, 4)
            if required_total else 1.0,
            "missing_critical_total": sum(
                len(item["missing_critical"]) for item in results),
            "forbidden_selected_total": sum(
                len(item["forbidden_selected"]) for item in results),
            "forbidden_actions_total": sum(
                len(item["forbidden_actions"]) for item in results),
            "missing_approval_gates_total": sum(
                len(item["missing_approval_gates"]) for item in results),
            "unknown_expected_missing_total": sum(
                len(item["unknown_expected_missing"]) for item in results),
            "unrelated_bytes_total": sum(
                item["unrelated_bytes"] for item in results),
            "stable_scenarios": sum(
                1 for item in results if item["stable"] is not False),
            "budget_incomplete_total": sum(
                1 for item in results
                if item["budget_status"] == "incomplete"),
            "budget_incomplete_scenarios": [
                item["scenario"] for item in results
                if item["budget_status"] == "incomplete"],
            "plan_ok_false_total": sum(
                1 for item in results
                if not item.get("plan_ok", True)),
            "duration_ms": duration_ms,
        },
        "results": sorted(results, key=lambda item: item["scenario"]),
        "limitations": [
            "baseline_all_markdown is a reference strategy (read every .md), "
            "not an observed user behavior",
            "ok/pass does not mean every plan is budget-complete; see "
            "budget_incomplete_total and the scenario's expected.required_unknown",
            "reading bytes are static file sizes; no model tokenizer was run",
            "less reading does not imply faster drawing; end-to-end model/EDA "
            "speed is NOT RUN",
            "the holdout set was designed by a separate reviewer who did not "
            "read the dev set, but this is not a blind test",
        ],
        "not_proof": NOT_PROOF,
        "ok": passed == len(results),
    }


def run_transforms(root, scenario, catalog, *, workdir=None):
    """Apply unrelated document transformations and check required coverage.

    The copy is made under a temporary directory; the scanned source is never
    modified.
    """
    root = Path(root)
    temp_parent = Path(workdir) if workdir else Path(tempfile.mkdtemp(
        prefix="ska-transform-"))
    created = not Path(workdir).exists() if workdir else True
    target = temp_parent / "easycirq"
    results = []
    try:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(root, target)
        baseline, _ = build_plan(target, scenario["intent"], catalog)
        baseline_required = _required_paths(baseline)
        baseline_digest = stable_digest(sorted(_selected_paths(baseline)))

        def record(name, plan, extra=None):
            required = _required_paths(plan)
            item = {
                "transform": name,
                "required_missing": sorted(baseline_required - required),
                "selection_changed": stable_digest(
                    sorted(_selected_paths(plan))) != baseline_digest,
                "budget_status": plan["budget"]["status"],
        "plan_ok": bool(plan.get("ok")),
                "unknown_codes": sorted(
                    {entry["code"] for entry in plan["unknown"]}),
                "ok": not (baseline_required - required),
            }
            if extra:
                item.update(extra)
            results.append(item)

        # 1. line-ending and file-order change next to the entry file
        entry = target / "SKILL.md"
        text = entry.read_text(encoding="utf-8")
        entry.write_text(text.replace("\n", "\r\n"), encoding="utf-8",
                         newline="")
        plan, _ = build_plan(target, scenario["intent"], catalog)
        record("crlf_same_file", plan)
        entry.write_text(text, encoding="utf-8", newline="\n")

        # 2. a new background link must not become a required dependency
        entry.write_text(
            text + "\n\n背景资料：[参考索引](references/sources.md)。\n",
            encoding="utf-8", newline="\n")
        plan, _ = build_plan(target, scenario["intent"], catalog)
        record("background_link_added", plan)
        entry.write_text(text, encoding="utf-8", newline="\n")

        # 3. heading rename in a selected document (unrelated to selection)
        evidence = target / "references" / "evidence.md"
        evidence_text = evidence.read_text(encoding="utf-8")
        evidence.write_text(
            evidence_text.replace("# 证据", "# 证据与记录", 1),
            encoding="utf-8", newline="\n")
        plan, _ = build_plan(target, scenario["intent"], catalog)
        record("heading_renamed", plan)
        evidence.write_text(evidence_text, encoding="utf-8", newline="\n")

        # 4. content hash change in an already-read document
        evidence.write_text(evidence_text + "\n<!-- hash change -->\n",
                            encoding="utf-8", newline="\n")
        changed_intent = dict(scenario["intent"])
        changed_intent["already_read"] = [{
            "path": "easycirq/references/evidence.md",
            "sha256": "0" * 64,
            "rules_version": CATALOG_VERSION,
            "scope": "probe",
        }]
        plan, _ = build_plan(target, changed_intent, catalog)
        record("content_hash_changed", plan, {
            "cache_codes": sorted({entry["code"] for entry in plan["unknown"]
                                   if entry["code"].startswith(("cache", "already"))}),
        })
        evidence.write_text(evidence_text, encoding="utf-8", newline="\n")

        # 5. task synonym phrasing must not change required coverage
        synonym_intent = dict(scenario["intent"])
        synonym_intent["notes"] = (
            str(synonym_intent.get("notes") or "") + " （同义改写：照这个范围做）")
        plan, _ = build_plan(target, synonym_intent, catalog)
        record("task_synonym", plan)

        # 6. smaller budget must not trim required documents
        budget_intent = dict(scenario["intent"])
        budget_intent["budget_chars"] = 1200
        plan, _ = build_plan(target, budget_intent, catalog)
        record("smaller_budget", plan, {
            "required_chars": plan["budget"]["required_chars"],
            "status": plan["budget"]["status"],
            "uncovered": len(plan["budget"]["uncovered"]),
        })
        if plan["budget"]["status"] != "incomplete":
            results[-1]["ok"] = False
            results[-1]["reason"] = "small budget did not mark incomplete"

        # 7. external modification of an unrelated file
        readme = target / "references" / "sources.md"
        readme_text = readme.read_text(encoding="utf-8")
        readme.write_text(readme_text + "\n<!-- external editor -->\n",
                          encoding="utf-8", newline="\n")
        plan, _ = build_plan(target, scenario["intent"], catalog)
        record("unrelated_external_edit", plan)
        readme.write_text(readme_text, encoding="utf-8", newline="\n")
    finally:
        if created and temp_parent.exists():
            shutil.rmtree(temp_parent, ignore_errors=True)
    return {
        "scenario": scenario["id"],
        "transforms": results,
        "ok": all(item["ok"] for item in results),
    }


def write_benchmark(path, result):
    atomic_write_text(path, canonical_json(result))


def main_benchmark(args, catalog, scenarios, root, exclude_paths=()):
    result = run_benchmark(root, scenarios, catalog,
                           stability=not args.no_stability,
                           exclude_paths=exclude_paths)
    if args.out:
        out = Path(args.out)
        if out.suffix.lower() == ".json":
            atomic_write_text(out, canonical_json(result))
        else:
            out.mkdir(parents=True, exist_ok=True)
            atomic_write_text(out / "result.json", canonical_json(result))
    if args.transforms:
        scenario = next((item for item in scenarios
                         if (item.get("_split") or item.get("split")) == "dev"),
                         scenarios[0])
        transform = run_transforms(root, scenario, catalog)
        result["transforms"] = transform
        result["ok"] = result["ok"] and transform["ok"]
        if args.out:
            out = Path(args.out)
            path = out if out.suffix.lower() == ".json" else out / "result.json"
            atomic_write_text(path, canonical_json(result))
    return result
