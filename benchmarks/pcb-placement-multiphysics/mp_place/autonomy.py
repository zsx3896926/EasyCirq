"""P4-J: autonomous acceptance audit ("无人化验收") for the offline pipeline.

Purpose
-------
Run the end-to-end pipeline for every registered template and seed, then audit
the produced certificate and report **independently of the pipeline code's own
self-report**.  For each run the audit checks:

1. ``feasible``: the placement is hard-feasible, ``report.feasible`` and
   ``certificate.feasible`` are true, no violations / missing components;
2. ``certificate_schema``: the certificate is a JSON object, round-trips
   through ``json.dumps(..., allow_nan=False)`` and carries the certificate
   schema string;
3. ``certificate_fixed_fields``: ``fixed_fields`` is exactly
   ``{"routing_verified": false, "drc": "NOT RUN", "eda_calls": 0}`` both in
   the certificate and at report top level;
4. ``placement_digest``: the digest recomputed from the placement equals both
   ``certificate.placement_digest`` and ``report.placement_digest``, and the
   certificate's placement equals the report's placement;
5. ``certificate_matches_verify``: re-running ``mp_place.verify.certificate``
   on the same scenario/placement reproduces the stored certificate exactly;
6. ``intent_replay``: the JSON intent rebuilds, replays to a hard-feasible
   placement with no intent-constraint violations, and its digest equals the
   reported ``intent_digest``;
7. ``router_certificate_consistent``: the pipeline's router summary agrees
   with ``certificate.routability`` (status / completion / failed nets /
   wirelength / vias / overflow) and the report's own consistency flag is true;
8. ``scenario_identity``: scenario name and scenario digest agree with the
   real scenario object;
9. ``determinism``: a second pipeline run for the same input produces
   byte-identical JSON.

Anything that does not match is a **failed run**: the audit does not repair,
ignore or round-trip it away.  Tampering with a certificate (digest, schema,
fixed fields, feasibility, router completion, ...) is therefore detected.

Scope / safety
--------------
Everything is offline: no EDA, no DRC, no network, nothing is applied to a
board.  The report hard-codes the same safety fields as the pipeline and only
proves that the offline certificate chain is internally consistent on the
frozen templates -- it is not a routability, DRC or manufacturing sign-off.

CLI
---
``python -m mp_place.autonomy [--templates ...] [--seeds 0,1] [--steps 800]``
runs the audit and writes ``report_autonomy.md`` / ``report_autonomy.json``
next to the project root (``--out-dir`` overrides).  Exit code 0 only when
every audited run passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import templates
from . import verify as verify_mod
from .model import Placement, Scenario, hard_violations

AUDIT_SCHEMA = "mp_place.autonomy-audit/v1"
PIPELINE_SCHEMA = "mp_place.pipeline/v1"
CERTIFICATE_SCHEMA = verify_mod.CERTIFICATE_SCHEMA

#: The audit refuses to run if the pipeline changes these (safety contract).
REQUIRED_FIXED_FIELDS: Dict[str, Any] = {
    "routing_verified": False,
    "drc": "NOT RUN",
    "eda_calls": 0,
}

DEFAULT_SEEDS: Tuple[int, ...] = (0, 1)
DEFAULT_BUDGET_STEPS = 800
DEFAULT_ROUTE_REPAIR = True

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CHECK_NAMES: Tuple[str, ...] = (
    "feasible",
    "scenario_identity",
    "certificate_schema",
    "certificate_fixed_fields",
    "placement_digest",
    "certificate_matches_verify",
    "intent_replay",
    "router_certificate_consistent",
    "determinism",
)

AUDIT_LIMITS: Tuple[str, ...] = (
    "offline certificate-chain audit only; not DRC, not a routability proof, not manufacturing sign-off",
    "audits the frozen parameterised templates and the offline pipeline, not a real board",
    "elapsed_s values are wall-clock measurements and are not part of the audited deterministic chain",
    "the audit verifies internal consistency (feasible/certificate/digest/intent/router); it does not prove electrical correctness",
)


# ---------------------------------------------------------------------------
# JSON / comparison helpers


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _same_number(left: Any, right: Any, tol: float = 1e-6) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return abs(float(left) - float(right)) <= tol
    except (TypeError, ValueError):
        return False


def _placement_from_payload(payload: Any) -> Placement:
    """Rebuild a ``Placement`` (``ref -> (x, y, rot)``) from JSON payload."""
    placement: Placement = {}
    if not isinstance(payload, dict):
        return placement
    for ref in sorted(payload):
        value = payload[ref]
        try:
            x, y, rot = value
        except (TypeError, ValueError):
            continue
        try:
            placement[str(ref)] = (float(x), float(y), int(rot) % 360)
        except (OverflowError, TypeError, ValueError):
            continue
    return placement


def _first_diff(left: Any, right: Any, path: str = "$") -> str:
    """Human-readable first difference between two JSON-like payloads."""
    if isinstance(left, dict) and isinstance(right, dict):
        keys = sorted(set(left) | set(right))
        for key in keys:
            child = path + "." + str(key)
            if key not in left:
                return "missing in left: " + child
            if key not in right:
                return "unexpected field: " + child
            if _canonical_json(left[key]) != _canonical_json(right[key]):
                if isinstance(left[key], (dict, list)) and isinstance(
                        right[key], type(left[key])):
                    deeper = _first_diff(left[key], right[key], child)
                    if deeper:
                        return deeper
                return "field differs: " + child
        return ""
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return "%s length %d != %d" % (path, len(left), len(right))
        for index, (litem, ritem) in enumerate(zip(left, right)):
            if _canonical_json(litem) != _canonical_json(ritem):
                deeper = _first_diff(litem, ritem, "%s[%d]" % (path, index))
                if deeper:
                    return deeper
                return "item differs: %s[%d]" % (path, index)
        return ""
    return "value differs: " + path


# ---------------------------------------------------------------------------
# single-run audit


def _add(checks: Dict[str, Dict[str, Any]], name: str, ok: bool,
         detail: str) -> None:
    checks[name] = {"ok": bool(ok), "detail": str(detail)}


def audit_report(scenario: Scenario, report: Any, *,
                 seed: Optional[int] = None,
                 budget_steps: Optional[int] = None,
                 rerun: Any = None) -> Dict[str, Any]:
    """Audit one pipeline report against its scenario (pure function).

    ``rerun`` is an optional second pipeline report for the *same* input; when
    given, byte-level determinism is checked too.  Returns
    ``{"ok": bool, "checks": {name: {"ok", "detail"}}, "failures": [...],
    "metrics": {...}}`` with all :data:`CHECK_NAMES` present and in order.
    """
    checks: Dict[str, Dict[str, Any]] = {}
    if not isinstance(report, dict):
        report = {}
    raw_certificate = report.get("certificate")
    certificate: Dict[str, Any] = (
        raw_certificate if isinstance(raw_certificate, dict) else {}
    )
    placement = _placement_from_payload(report.get("placement"))
    violations = list(hard_violations(scenario, placement))
    missing = [ref for ref in sorted(scenario.components)
               if ref not in placement]

    # --- 1. feasible -----------------------------------------------------
    certificate_feasible = certificate.get("feasible")
    feasible_ok = (
        report.get("feasible") is True
        and certificate_feasible is True
        and report.get("violations") == []
        and not violations
        and not missing
        and certificate.get("missing_components") in ([], None)
    )
    _add(checks, "feasible", feasible_ok,
         "report.feasible=%r certificate.feasible=%r report.violations=%d "
         "recomputed_violations=%d missing=%d"
         % (report.get("feasible"), certificate_feasible,
            len(report.get("violations") or []), len(violations),
            len(missing)))

    # --- 2. scenario identity -------------------------------------------
    scenario_digest = verify_mod.scenario_digest(scenario)
    reported_scenario = report.get("scenario") if isinstance(
        report.get("scenario"), dict) else {}
    certificate_scenario = certificate.get("scenario") if isinstance(
        certificate.get("scenario"), dict) else {}
    scenario_ok = (
        reported_scenario.get("name") == scenario.name
        and reported_scenario.get("digest") == scenario_digest
        and certificate_scenario.get("name") == scenario.name
        and certificate_scenario.get("digest") == scenario_digest
    )
    _add(checks, "scenario_identity", scenario_ok,
         "name=%r expected_digest=%s report=%s certificate=%s"
         % (scenario.name, scenario_digest[:19],
            str(reported_scenario.get("digest"))[:19],
            str(certificate_scenario.get("digest"))[:19]))

    # --- 3. certificate schema + JSON round-trip ------------------------
    if raw_certificate is None:
        json_ok = False
        json_detail = "report has no certificate object"
    else:
        try:
            roundtripped = json.loads(
                json.dumps(certificate, ensure_ascii=False, allow_nan=False))
            json_ok = roundtripped == certificate
            json_detail = "json round-trip ok" if json_ok else \
                "json round-trip changed the payload"
        except (TypeError, ValueError) as exc:
            json_ok = False
            json_detail = "not JSON serializable: %s: %s" % (
                type(exc).__name__, exc)
    schema_ok = certificate.get("schema") == CERTIFICATE_SCHEMA
    _add(checks, "certificate_schema", schema_ok and json_ok,
         "schema=%r expected=%r %s"
         % (certificate.get("schema"), CERTIFICATE_SCHEMA, json_detail))

    # --- 4. fixed safety fields -----------------------------------------
    certificate_fixed = certificate.get("fixed_fields")
    report_fixed = report.get("fixed_fields")
    fixed_ok = (
        certificate_fixed == REQUIRED_FIXED_FIELDS
        and report_fixed == REQUIRED_FIXED_FIELDS
    )
    _add(checks, "certificate_fixed_fields", fixed_ok,
         "certificate=%r report=%r expected=%r"
         % (certificate_fixed, report_fixed, REQUIRED_FIXED_FIELDS))

    # --- 5. placement digest / placement echo ---------------------------
    expected_placement_digest = verify_mod.placement_digest(placement, scenario)
    certificate_placement = _placement_from_payload(
        certificate.get("placement"))
    digest_ok = (
        certificate.get("placement_digest") == expected_placement_digest
        and report.get("placement_digest") == expected_placement_digest
        and certificate_placement == placement
    )
    _add(checks, "placement_digest", digest_ok,
         "expected=%s certificate=%s report=%s placement_echo=%s"
         % (expected_placement_digest[:19],
            str(certificate.get("placement_digest"))[:19],
            str(report.get("placement_digest"))[:19],
            certificate_placement == placement))

    # --- 6. re-run verify.certificate and compare exactly ---------------
    try:
        recomputed = verify_mod.certificate(
            scenario, placement, extra=certificate.get("extra"))
    except Exception as exc:  # pragma: no cover - verify is defensive
        recomputed = None
        recompute_detail = "recompute failed: %s: %s" % (
            type(exc).__name__, exc)
    if recomputed is None:
        matches_verify = False
    else:
        matches_verify = _canonical_json(recomputed) == _canonical_json(
            certificate)
        recompute_detail = ("recomputed certificate is identical"
                            if matches_verify
                            else _first_diff(recomputed, certificate))
    _add(checks, "certificate_matches_verify", matches_verify,
         recompute_detail)

    # --- 7. intent replay ------------------------------------------------
    try:
        from . import intent as intent_mod
        intent = intent_mod.build_intent(scenario, placement)
        replayed = intent_mod.intent_to_plan(scenario, intent)
        replay_violations = list(hard_violations(scenario, replayed)) + \
            list(intent_mod.intent_violations(scenario, replayed, intent))
        recomputed_intent_digest = _canonical_sha256(intent)
        intent_ok = (
            report.get("intent_replay_ok") is True
            and not replay_violations
            and report.get("intent_digest") == recomputed_intent_digest
        )
        intent_detail = (
            "replayed plan hard-feasible and intent digest matches"
            if intent_ok else
            "report.intent_replay_ok=%r replay_violations=%d digest=%s/%s"
            % (report.get("intent_replay_ok"), len(replay_violations),
               str(report.get("intent_digest"))[:19],
               recomputed_intent_digest[:19]))
    except Exception as exc:
        intent_ok = False
        intent_detail = "intent rebuild/replay failed: %s: %s" % (
            type(exc).__name__, exc)
    _add(checks, "intent_replay", intent_ok, intent_detail)

    # --- 8. router summary vs certificate.routability -------------------
    router = report.get("router") if isinstance(report.get("router"),
                                                dict) else {}
    certificate_route = certificate.get("routability") if isinstance(
        certificate.get("routability"), dict) else {}
    router_ok = (
        report.get("router_certificate_consistent") is True
        and router.get("status") == certificate_route.get("status")
        and _same_number(router.get("completion"),
                         certificate_route.get("completion"))
        and list(router.get("failed_nets") or [])
        == list(certificate_route.get("failed_nets") or [])
        and _same_number(router.get("wirelength_mm"),
                         certificate_route.get("wirelength_mm"), tol=1e-3)
        and router.get("vias") == certificate_route.get("vias")
        and router.get("overflow") == certificate_route.get("overflow")
    )
    _add(checks, "router_certificate_consistent", router_ok,
         "status=%r/%r completion=%r/%r failed_nets=%r/%r "
         "wirelength=%r/%r vias=%r/%r overflow=%r/%r"
         % (router.get("status"), certificate_route.get("status"),
            router.get("completion"), certificate_route.get("completion"),
            router.get("failed_nets"), certificate_route.get("failed_nets"),
            router.get("wirelength_mm"),
            certificate_route.get("wirelength_mm"),
            router.get("vias"), certificate_route.get("vias"),
            router.get("overflow"), certificate_route.get("overflow")))

    # --- 9. determinism --------------------------------------------------
    if rerun is None:
        _add(checks, "determinism", True, "not requested (rerun is None)")
    else:
        try:
            first_text = _canonical_json(report)
            second_text = _canonical_json(rerun)
            deterministic = first_text == second_text
            determinism_detail = ("second run is byte-identical"
                                  if deterministic
                                  else _first_diff(report, rerun))
        except (TypeError, ValueError) as exc:
            deterministic = False
            determinism_detail = "cannot canonicalise reports: %s: %s" % (
                type(exc).__name__, exc)
        _add(checks, "determinism", deterministic, determinism_detail)

    ordered_checks = {name: checks[name] for name in CHECK_NAMES
                      if name in checks}
    failures = [name for name in CHECK_NAMES
                if name in ordered_checks and not ordered_checks[name]["ok"]]
    metrics = {
        "placement_digest": report.get("placement_digest"),
        "proxy_cost": report.get("proxy_cost"),
        "truth_v1": report.get("truth_v1"),
        "truth_v2": report.get("truth_v2"),
        "router_status": router.get("status"),
        "router_completion": router.get("completion"),
        "router_failed_nets": list(router.get("failed_nets") or []),
        "intent_total_constraints": report.get("intent_total_constraints"),
        "violations": len(violations),
        "missing_components": missing,
        "seed": seed,
        "budget_steps": budget_steps,
    }
    return {
        "ok": not failures,
        "checks": ordered_checks,
        "failures": failures,
        "metrics": _json_safe(metrics),
    }


# ---------------------------------------------------------------------------
# audit grid


def _run_pipeline(scenario: Scenario, budget_steps: int, seed: int,
                  route_repair: bool) -> Dict[str, Any]:
    from .pipeline import run_pipeline

    return run_pipeline(scenario, budget_steps=budget_steps, seed=seed,
                        route_repair=route_repair)


def _normalise_seeds(seeds: Iterable[Any]) -> List[int]:
    out: List[int] = []
    for seed in seeds:
        try:
            value = int(seed)
        except (TypeError, ValueError) as exc:
            raise ValueError("seeds must be integers, got %r" % (seed,)) from exc
        if value < 0:
            raise ValueError("seeds must be >= 0, got %d" % (value,))
        out.append(value)
    if not out:
        raise ValueError("seeds must not be empty")
    return out


def _normalise_templates(template_names: Optional[Iterable[str]]) -> List[str]:
    known = list(templates.template_names())
    if template_names is None:
        return sorted(known)
    names = [str(name) for name in template_names]
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ValueError("unknown template(s): %r; known: %r"
                         % (sorted(unknown), known))
    if not names:
        raise ValueError("template_names must not be empty")
    # Keep the caller's order but drop duplicates for a deterministic grid.
    seen = set()
    unique = []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def run_audit(template_names: Optional[Iterable[str]] = None,
              seeds: Iterable[int] = DEFAULT_SEEDS,
              budget_steps: int = DEFAULT_BUDGET_STEPS,
              route_repair: bool = DEFAULT_ROUTE_REPAIR,
              determinism: bool = True) -> Dict[str, Any]:
    """Run the autonomous acceptance audit over templates x seeds.

    Every run executes the pipeline once (plus once more when ``determinism``
    is true) and audits it with :func:`audit_report`.  Exceptions inside a run
    are captured as a failed run instead of aborting the audit.  The returned
    dict is JSON-serialisable and carries per-run checks, per-template
    summaries, the overall pass rate and wall-clock timings.
    """
    names = _normalise_templates(template_names)
    seed_list = _normalise_seeds(seeds)
    try:
        budget = int(budget_steps)
    except (TypeError, ValueError) as exc:
        raise ValueError("budget_steps must be an integer, got %r"
                         % (budget_steps,)) from exc
    if budget < 0:
        raise ValueError("budget_steps must be >= 0, got %d" % (budget,))

    runs: List[Dict[str, Any]] = []
    started = time.perf_counter()
    for name in names:
        for seed in seed_list:
            run_started = time.perf_counter()
            scenario_name = name
            try:
                scenario = templates.instantiate(name, seed=seed)
                scenario_name = scenario.name
                report = _run_pipeline(scenario, budget, seed, route_repair)
                rerun = (_run_pipeline(scenario, budget, seed, route_repair)
                         if determinism else None)
                result = audit_report(scenario, report, seed=seed,
                                      budget_steps=budget, rerun=rerun)
            except Exception as exc:  # a broken run must not abort the audit
                result = {
                    "ok": False,
                    "checks": {},
                    "failures": ["exception:%s:%s"
                                 % (type(exc).__name__, exc)],
                    "metrics": {},
                }
            elapsed = time.perf_counter() - run_started
            runs.append({
                "template": name,
                "scenario": scenario_name,
                "seed": seed,
                "passed": bool(result["ok"]),
                "checks": result["checks"],
                "failures": list(result["failures"]),
                "metrics": result["metrics"],
                "elapsed_s": round(elapsed, 3),
            })

    template_summaries: List[Dict[str, Any]] = []
    for name in names:
        subset = [run for run in runs if run["template"] == name]
        passed = sum(1 for run in subset if run["passed"])
        template_summaries.append({
            "template": name,
            "runs": len(subset),
            "passed": passed,
            "failed": len(subset) - passed,
            "pass_rate": round(passed / len(subset), 6) if subset else 0.0,
            "elapsed_s": round(sum(run["elapsed_s"] for run in subset), 3),
        })

    total_elapsed = time.perf_counter() - started
    total_runs = len(runs)
    passed_runs = sum(1 for run in runs if run["passed"])
    failed_runs = total_runs - passed_runs
    checks_failed = sum(len(run["failures"]) for run in runs)
    audit: Dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "generated_by": "mp_place.autonomy",
        "config": {
            "templates": names,
            "seeds": seed_list,
            "budget_steps": budget,
            "route_repair": bool(route_repair),
            "determinism": bool(determinism),
            "determinism_repeats": 1 if determinism else 0,
            "checks": list(CHECK_NAMES),
        },
        "summary": {
            "total_runs": total_runs,
            "passed": passed_runs,
            "failed": failed_runs,
            "pass_rate": round(passed_runs / total_runs, 6)
            if total_runs else 0.0,
            "templates_total": len(template_summaries),
            "templates_passed": sum(1 for item in template_summaries
                                    if item["failed"] == 0),
            "checks_total": total_runs * len(CHECK_NAMES),
            "checks_failed": checks_failed,
            "total_elapsed_s": round(total_elapsed, 3),
            "mean_elapsed_s": round(total_elapsed / total_runs, 3)
            if total_runs else 0.0,
        },
        "templates": template_summaries,
        "runs": runs,
        "fixed_fields": dict(REQUIRED_FIXED_FIELDS),
        "limits": list(AUDIT_LIMITS),
        "notes": [
            "per-run elapsed_s includes the pipeline run(s) and the audit; "
            "wall-clock values are not part of the audited deterministic chain",
            "a failed check means the offline certificate chain is not "
            "self-consistent; it never means a real board was verified",
        ],
    }
    return _json_safe(audit)


# ---------------------------------------------------------------------------
# reporting


def _percent(rate: float) -> str:
    return "%.1f%%" % (100.0 * float(rate))


def _pass_fail(flag: Any) -> str:
    return "PASS" if flag else "FAIL"


def render_markdown(audit: Dict[str, Any]) -> str:
    """Render an audit dict as the human-readable Markdown report."""
    config = audit.get("config") or {}
    summary = audit.get("summary") or {}
    runs = audit.get("runs") or []
    templates = audit.get("templates") or []
    lines: List[str] = []
    lines.append("# P4-J 无人化验收：certificate audit")
    lines.append("")
    lines.append(
        "对 %d 个参数化模板 × seeds %s 跑 `run_pipeline(..., "
        "route_repair=%s)`，每个 run 独立审计 certificate / digest / "
        "intent replay / router 一致性%s。"
        % (len(config.get("templates") or []),
           config.get("seeds"),
           config.get("route_repair"),
           " / 同输入重跑确定性" if config.get("determinism") else ""))
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|---|---|")
    lines.append("| 通过率 | **%d/%d（%s）** |"
                 % (summary.get("passed", 0), summary.get("total_runs", 0),
                    _percent(summary.get("pass_rate", 0.0))))
    lines.append("| 模板通过 | %d/%d |"
                 % (summary.get("templates_passed", 0),
                    summary.get("templates_total", 0)))
    lines.append("| 检查项 | %d/%d 通过 |"
                 % (summary.get("checks_total", 0)
                    - summary.get("checks_failed", 0),
                    summary.get("checks_total", 0)))
    lines.append("| 总耗时 | %.3f s（平均 %.3f s/run） |"
                 % (summary.get("total_elapsed_s", 0.0),
                    summary.get("mean_elapsed_s", 0.0)))
    lines.append("| 配置 | %d templates × seeds %s，budget_steps=%s，"
                 "route_repair=%s |"
                 % (len(config.get("templates") or []),
                    config.get("seeds"), config.get("budget_steps"),
                    config.get("route_repair")))
    lines.append("| 固定安全字段 | `%s` |"
                 % json.dumps(audit.get("fixed_fields") or {},
                              ensure_ascii=False, sort_keys=True))
    lines.append("")
    lines.append("## 每模板汇总")
    lines.append("")
    lines.append("| template | runs | passed | failed | pass_rate | elapsed_s |")
    lines.append("|---|---|---|---|---|---|")
    for item in templates:
        lines.append("| %s | %d | %d | %d | %s | %.3f |"
                     % (item.get("template"), item.get("runs", 0),
                        item.get("passed", 0), item.get("failed", 0),
                        _percent(item.get("pass_rate", 0.0)),
                        item.get("elapsed_s", 0.0)))
    lines.append("")
    lines.append("## 逐 run 结果")
    lines.append("")
    lines.append("| template | seed | 结果 | feasible | certificate | "
                 "digest | intent | router | determinism | elapsed_s |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for run in runs:
        checks = run.get("checks") or {}

        def ok(name: str) -> str:
            entry = checks.get(name)
            if entry is None:
                return "FAIL"
            return _pass_fail(entry.get("ok"))

        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %.3f |"
            % (run.get("template"), run.get("seed"),
               _pass_fail(run.get("passed")),
               ok("feasible"), ok("certificate_schema"),
               ok("placement_digest"), ok("intent_replay"),
               ok("router_certificate_consistent"), ok("determinism"),
               run.get("elapsed_s", 0.0)))
    lines.append("")
    lines.append("## 失败项")
    lines.append("")
    failed_entries = []
    for run in runs:
        if run.get("passed"):
            continue
        failures = run.get("failures") or []
        failed_entries.append(
            "- `%s` seed=%s：%s"
            % (run.get("template"), run.get("seed"),
               ", ".join(failures) if failures else "unknown failure"))
        checks = run.get("checks") or {}
        for name in failures:
            entry = checks.get(name)
            if isinstance(entry, dict) and entry.get("detail"):
                failed_entries.append(
                    "  - %s: %s" % (name, entry["detail"]))
    lines.extend(failed_entries if failed_entries else ["（无）"])
    lines.append("")
    lines.append("## 审计项定义")
    lines.append("")
    definitions = {
        "feasible": "placement 硬约束可行，report/certificate 的 feasible 与 "
                    "violations 一致",
        "certificate_schema": "certificate 是对象、schema 正确、JSON 往返不变",
        "certificate_fixed_fields": "fixed_fields 精确等于 "
                                    '{"routing_verified": false, '
                                    '"drc": "NOT RUN", "eda_calls": 0}',
        "placement_digest": "用 placement 重算 digest 与 report/certificate "
                            "一致，且 certificate 回显 placement 一致",
        "certificate_matches_verify": "对同 scenario/placement 重新生成 "
                                      "verify.certificate 必须与存档证书完全一致",
        "intent_replay": "intent 重建+回放后硬约束为空、intent 约束无违反、"
                         "digest 与报告一致",
        "router_certificate_consistent": "pipeline router 摘要与 "
                                         "certificate.routability 的 "
                                         "status/completion/failed/wirelength/"
                                         "vias/overflow 一致",
        "scenario_identity": "report/certificate 的 scenario name 与 digest "
                             "与真实 Scenario 一致",
        "determinism": "同输入第二次 pipeline 输出与第一次字节一致",
    }
    lines.append("| check | 含义 |")
    lines.append("|---|---|")
    for name in CHECK_NAMES:
        lines.append("| %s | %s |" % (name, definitions.get(name, "")))
    lines.append("")
    lines.append("## 边界与限制")
    lines.append("")
    for item in audit.get("limits") or []:
        lines.append("- " + item)
    lines.append("")
    return "\n".join(lines)


def _write_text_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix="." + path.name + "-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def write_reports(audit: Dict[str, Any],
                  markdown_path: Optional[Any] = None,
                  json_path: Optional[Any] = None) -> Dict[str, str]:
    """Write the audit as Markdown + JSON and return both paths."""
    markdown_target = (Path(markdown_path) if markdown_path is not None
                       else PROJECT_ROOT / "report_autonomy.md")
    json_target = (Path(json_path) if json_path is not None
                   else PROJECT_ROOT / "report_autonomy.json")
    json_text = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True,
                           allow_nan=False) + "\n"
    _write_text_atomic(json_target, json_text)
    _write_text_atomic(markdown_target, render_markdown(audit))
    return {"markdown": str(markdown_target), "json": str(json_target)}


# ---------------------------------------------------------------------------
# CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mp_place.autonomy",
        description="P4-J autonomous acceptance audit: run the offline "
                    "pipeline for every template x seed and audit the produced "
                    "certificate chain. Writes report_autonomy.md/json.")
    parser.add_argument("--templates", default=None,
                        help="comma-separated template names (default: all "
                             "registered templates)")
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in DEFAULT_SEEDS),
                        help="comma-separated non-negative seeds (default: 0,1)")
    parser.add_argument("--steps", type=int, default=DEFAULT_BUDGET_STEPS,
                        help="solver move budget per pipeline run (default: %d)"
                             % DEFAULT_BUDGET_STEPS)
    parser.add_argument("--no-route-repair", action="store_true",
                        help="disable route_repair in the pipeline (default: on)")
    parser.add_argument("--no-determinism", action="store_true",
                        help="skip the second pipeline run (determinism check "
                             "reported as not requested)")
    parser.add_argument("--out-dir", default=None,
                        help="directory for report_autonomy.md/json "
                             "(default: project root)")
    parser.add_argument("--json", action="store_true",
                        help="also print the audit summary as one JSON object "
                             "on stdout")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    template_names = (None if args.templates is None
                      else [item.strip() for item in args.templates.split(",")
                            if item.strip()])
    try:
        seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
        audit = run_audit(template_names=template_names, seeds=seeds,
                          budget_steps=args.steps,
                          route_repair=not args.no_route_repair,
                          determinism=not args.no_determinism)
    except (ValueError, KeyError) as exc:
        print("error: %s" % (exc,), file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT
    paths = write_reports(audit, out_dir / "report_autonomy.md",
                          out_dir / "report_autonomy.json")
    summary = audit.get("summary") or {}
    if args.json:
        print(json.dumps({"schema": audit.get("schema"),
                          "summary": summary, "paths": paths},
                         ensure_ascii=False, sort_keys=True))
    print("[autonomy] templates=%d seeds=%s runs=%d passed=%d failed=%d "
          "pass_rate=%s elapsed=%.3fs -> %s, %s"
          % (summary.get("templates_total", 0), audit.get("config", {}).get("seeds"),
             summary.get("total_runs", 0), summary.get("passed", 0),
             summary.get("failed", 0),
             _percent(summary.get("pass_rate", 0.0)),
             summary.get("total_elapsed_s", 0.0),
             paths["markdown"], paths["json"]),
          file=sys.stderr)
    return 0 if summary.get("failed", 1) == 0 else 1


__all__ = [
    "AUDIT_SCHEMA",
    "CHECK_NAMES",
    "REQUIRED_FIXED_FIELDS",
    "audit_report",
    "run_audit",
    "render_markdown",
    "write_reports",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
