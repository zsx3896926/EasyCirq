"""Run the repository's offline audit CLIs and normalise their results.

Design rules:

* the audited input is never written to; reports are produced in a private
  temporary directory and deleted after they are read;
* the module's own verdict/status stays authoritative (``status`` /
  ``overall_status``); exit codes are only a fallback and a consistency check;
* ``real_eda``/``eda_calls`` are reported honestly: this wrapper invokes only
  Python audit modules and never an EDA executable, so the wrapper-level value
  is ``NOT RUN`` / ``0`` even when the module report has no such field.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import RESULT_SCHEMA
from .errors import ToolError

SCRIPTS = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS.parents[1]

DEFAULT_TIMEOUT_S = 120
MAX_TIMEOUT_S = 600
MAX_REPORT_BYTES = 8 * 1024 * 1024
TAIL_LINES = 10
MAX_UNKNOWN_ITEMS = 50

ENV = dict(os.environ)
_existing = ENV.get("PYTHONPATH", "")
ENV["PYTHONPATH"] = str(SCRIPTS) + (os.pathsep + _existing if _existing else "")
ENV["PYTHONIOENCODING"] = "utf-8"
ENV.setdefault("HDS_OFFLINE", "1")

NOT_PROOF = [
    "offline audit only: no EDA/daemon/connector call, no host DRC, no save/reopen, "
    "no manufacturing order and no physical test",
    "pass_with_scope covers only the declared input and evaluated rules; it is not "
    "a whole-board, hardware, safety or EMC acceptance",
    "review_required / incomplete / unknown items must be resolved by a human and "
    "are never converted to a pass",
]

_EXPECTED_EXITS = {
    "electrical_review": {0, 1, 2, 3, 4},
    "return_path_audit": {0, 1, 2, 3, 4},
    "delivery_audit.inspect": {0},
    "delivery_audit.audit": {0, 1, 2, 3},
}

_EXIT_FALLBACK = {
    "electrical_review": {0: "pass_with_scope", 1: "fail", 2: "invalid_input",
                          3: "review_required", 4: "incomplete"},
    "return_path_audit": {0: "pass_with_scope", 1: "fail", 2: "review_required",
                          3: "incomplete", 4: "input_invalid"},
    "delivery_audit.inspect": {0: "inspected"},
    "delivery_audit.audit": {0: "pass_with_scope", 1: "fail", 2: "input_invalid",
                             3: "incomplete"},
}

_VERDICT_CLASS = {
    "pass_with_scope": "pass_with_scope",
    "fail": "fail",
    "review_required": "review_required",
    "incomplete": "incomplete",
    "invalid_input": "invalid_input",
    "input_invalid": "invalid_input",
    "inspected": "inventory_only",
}


def resolve_path(raw, field: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("invalid_path", "%s must be a non-empty string" % field)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        path = path.resolve()
    except OSError as exc:  # pragma: no cover - defensive
        raise ToolError("invalid_path", "%s cannot be resolved: %s" % (field, exc))
    if not path.exists():
        raise ToolError("input_not_found", "%s does not exist: %s" % (field, path),
                        {"field": field, "path": str(path)})
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_signature(path: Path) -> str:
    """Cheap read-only signature: sorted relative names + sizes (not content)."""
    rows = []
    for item in sorted(path.rglob("*")):
        if item.is_file():
            try:
                rows.append("%s\t%d" % (item.relative_to(path).as_posix(),
                                        item.stat().st_size))
            except OSError:
                continue
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _tail(text: str) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-TAIL_LINES:])


def _run_module(args, timeout_s: int):
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", *args],
            cwd=str(SCRIPTS), env=ENV, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            "timeout",
            "audit module exceeded %ss; no report was used" % timeout_s,
            {"module": args[0], "timeout_s": timeout_s,
             "stdout_tail": _tail(exc.stdout or ""),
             "stderr_tail": _tail(exc.stderr or "")},
        )
    except OSError as exc:
        raise ToolError("module_not_runnable",
                        "cannot start %s: %s" % (args[0], exc))
    duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
    return proc, duration_ms


def _load_report(path: Path):
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ToolError("report_missing", "audit module wrote no report: %s" % exc)
    if size > MAX_REPORT_BYTES:
        raise ToolError(
            "report_too_large",
            "report exceeds the %d-byte MCP tool limit; use the module CLI directly"
            % MAX_REPORT_BYTES,
            {"report_bytes": size, "report_sha256": _sha256_file(path)},
        )
    raw = path.read_bytes()
    try:
        report = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ToolError("report_invalid", "report is not valid UTF-8 JSON: %s" % exc)
    if not isinstance(report, dict):
        raise ToolError("report_invalid", "report is not a JSON object")
    return report, hashlib.sha256(raw).hexdigest(), size


def _extract_real_eda(report: dict):
    if isinstance(report.get("real_eda"), str):
        return report["real_eda"], "report"
    run = report.get("run")
    if isinstance(run, dict) and isinstance(run.get("real_eda"), str):
        return run["real_eda"], "report.run"
    return "NOT RUN", "wrapper"


def _unknown_items(report: dict):
    items = []
    findings = report.get("findings")
    if isinstance(findings, list):
        for item in findings:
            if not isinstance(item, dict):
                continue
            state = item.get("status", item.get("state"))
            if state == "unknown":
                items.append({key: item.get(key) for key in
                              ("rule_id", "message", "status", "severity", "code")
                              if key in item})
    else:
        for item in report.get("unknowns") or []:
            if isinstance(item, dict):
                items.append({key: item.get(key) for key in
                              ("rule_id", "message", "status", "severity", "code")
                              if key in item})
            elif isinstance(item, str):
                items.append({"message": item})
    return items


def _summary(tool: str, report: dict) -> dict:
    if tool == "offline_electrical_review":
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        return {
            "finding_count": summary.get("finding_count"),
            "rule_counts": {rid: row.get("status")
                            for rid, row in (summary.get("rules") or {}).items()},
            "coverage": report.get("coverage"),
            "not_checked": report.get("not_checked"),
        }
    if tool == "offline_return_path_audit":
        return {
            "checked_scope": report.get("scope"),
            "coverage": report.get("coverage"),
            "finding_count": len(report.get("findings") or []),
            "unknown_count": len(report.get("unknowns") or []),
        }
    if tool == "offline_delivery_inspect":
        return {
            "file_count": len(report.get("files") or []),
            "risk_count": len(report.get("risks") or []),
            "scope": report.get("scope"),
        }
    if tool == "offline_delivery_audit":
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        return {
            "profile": report.get("profile"),
            "finding_count": summary.get("findings"),
            "by_status": summary.get("by_status"),
            "by_severity": summary.get("by_severity"),
            "coverage": report.get("coverage"),
        }
    return {}


def _verdict_class(status):
    return _VERDICT_CLASS.get(status, "unknown_status")


def _build_payload(tool, module, proc, report, report_sha, report_size,
                   duration_ms, input_info, detail, status_field, exit_key,
                   expected_exits):
    status = report.get(status_field) if isinstance(report, dict) else None
    if status is None:
        status = _EXIT_FALLBACK.get(exit_key, {}).get(proc.returncode)
    is_error = proc.returncode not in expected_exits or report is None
    real_eda, real_eda_source = (_extract_real_eda(report)
                                 if isinstance(report, dict) else ("NOT RUN", "wrapper"))
    unknowns = _unknown_items(report) if isinstance(report, dict) else []
    payload = {
        "schema": RESULT_SCHEMA,
        "tool": tool,
        "module": module,
        "command": {"module": module, "argv": [str(a) for a in proc.args[2:]],
                    "cwd": "easycirq/scripts"},
        "exit_code": proc.returncode,
        "expected_exits": sorted(expected_exits),
        "status": status,
        "verdict_class": _verdict_class(status),
        "is_pass_with_scope": status == "pass_with_scope",
        "is_error": is_error,
        "offline": True,
        "real_eda": real_eda,
        "real_eda_source": real_eda_source,
        "eda_calls": 0,
        "eda_calls_source": "wrapper (no EDA executable or daemon is started)",
        "input": input_info,
        "summary": _summary(tool, report) if isinstance(report, dict) else None,
        "unknown_count": len(unknowns),
        "unknown_items": unknowns[:MAX_UNKNOWN_ITEMS],
        "unknown_items_truncated": len(unknowns) > MAX_UNKNOWN_ITEMS,
        "not_checked": (report.get("not_checked") if isinstance(report, dict)
                        and isinstance(report.get("not_checked"), list) else []),
        "limits": (report.get("limits") if isinstance(report, dict)
                   and isinstance(report.get("limits"), list) else []),
        "report_schema": report.get("schema") if isinstance(report, dict) else None,
        "report_sha256": report_sha,
        "report_bytes": report_size,
        "detail": detail,
        "report_omitted": detail != "full",
        "report": report if detail == "full" else None,
        "duration_ms": duration_ms,
        "stderr_tail": _tail(proc.stderr),
        "not_proof": NOT_PROOF,
    }
    if is_error:
        payload["error"] = {
            "code": "module_exit_%s" % proc.returncode,
            "message": "audit module exited %s (expected %s); no verdict is claimed"
                       % (proc.returncode, sorted(expected_exits)),
            "stderr_tail": _tail(proc.stderr),
        }
    return payload


def _detail(arguments) -> str:
    detail = arguments.get("detail", "summary")
    return detail if detail in ("summary", "full") else "summary"


def _timeout(arguments) -> int:
    timeout = arguments.get("timeout_s", DEFAULT_TIMEOUT_S)
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        return DEFAULT_TIMEOUT_S
    return max(1, min(MAX_TIMEOUT_S, timeout))


def run_file_audit(tool, module, arguments, cli_args, status_field, exit_key):
    """Run a file-input audit whose report is written to a temporary file.

    ``cli_args(target, tmp_dir)`` returns the module argv.
    """
    target = resolve_path(arguments.get("input_path"), "input_path")
    if target.is_dir():
        raise ToolError("input_not_a_file",
                        "input_path must be a file for %s: %s" % (tool, target))
    detail = _detail(arguments)
    timeout_s = _timeout(arguments)
    before = _sha256_file(target)
    tmp = Path(tempfile.mkdtemp(prefix="easycirq-mcp-"))
    try:
        proc, duration_ms = _run_module(cli_args(target, tmp), timeout_s)
        after = _sha256_file(target)
        report = report_sha = report_size = None
        # Convention: each module writes its report to <tmp>/report.json.
        report_path = tmp / "report.json"
        if report_path.is_file():
            report, report_sha, report_size = _load_report(report_path)
        input_info = {
            "path": str(target),
            "kind": "file",
            "sha256_before": before,
            "sha256_after": after,
            "unchanged": before == after,
        }
        return _build_payload(tool, module, proc, report, report_sha, report_size,
                              duration_ms, input_info, detail, status_field,
                              exit_key, _EXPECTED_EXITS[exit_key])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_delivery_inspect(arguments):
    target = resolve_path(arguments.get("input_path"), "input_path")
    detail = _detail(arguments)
    timeout_s = _timeout(arguments)
    is_file = target.is_file()
    before_hash = _sha256_file(target) if is_file else None
    before_sig = None if is_file else _directory_signature(target)
    proc, duration_ms = _run_module(
        ["delivery_audit", "inspect", "--input", str(target)], timeout_s)
    after_hash = _sha256_file(target) if is_file else None
    after_sig = None if is_file else _directory_signature(target)
    if is_file:
        input_info = {"path": str(target), "kind": "file",
                      "sha256_before": before_hash, "sha256_after": after_hash,
                      "unchanged": before_hash == after_hash}
    else:
        input_info = {"path": str(target), "kind": "directory",
                      "signature": "names+sizes", "sha256_before": before_sig,
                      "sha256_after": after_sig,
                      "unchanged": before_sig == after_sig,
                      "unchanged_note": "directory signature covers relative "
                                        "names and sizes, not full content"}
    report = report_sha = report_size = None
    raw = (proc.stdout or "").strip()
    if raw:
        report_bytes = raw.encode("utf-8")
        if len(report_bytes) > MAX_REPORT_BYTES:
            raise ToolError("report_too_large",
                            "report exceeds the %d-byte MCP tool limit"
                            % MAX_REPORT_BYTES,
                            {"report_bytes": len(report_bytes)})
        try:
            report = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToolError("report_invalid",
                            "inspect stdout is not JSON: %s" % exc)
        if not isinstance(report, dict):
            raise ToolError("report_invalid", "inspect report is not an object")
        report_sha = hashlib.sha256(report_bytes).hexdigest()
        report_size = len(report_bytes)
    return _build_payload("offline_delivery_inspect", "delivery_audit", proc,
                          report, report_sha, report_size, duration_ms,
                          input_info, detail, "status",
                          "delivery_audit.inspect",
                          _EXPECTED_EXITS["delivery_audit.inspect"])


# ── customer-facing status / card / setup ─────────────────────────────────

def _load_script_module(name):
    """Import one of the sibling scripts/ modules without touching sys.path."""
    import importlib.util
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _status_payload(tool, schema, result, offline, note):
    return {
        "schema": schema,
        "tool": tool,
        "state": result["state"],
        "headline": result["headline"],
        "next": result["next"],
        "blockers": result.get("blockers", []),
        "missing": result.get("missing", []),
        "project": result.get("project"),
        "page": result.get("page"),
        "offline": offline,
        "eda": "NOT RUN",
        "note": note,
    }


def run_status(arguments):
    """One state + one next action from the last offline KPI report."""
    module = _load_script_module("sch_status")
    report = None
    kpi_path = (arguments or {}).get("kpi_report")
    if kpi_path:
        try:
            report = module._load(resolve_path(kpi_path, "kpi_report"))
        except (OSError, ValueError) as exc:
            raise ToolError("KPI_REPORT_UNREADABLE", str(exc),
                            "point kpi_report at the kpi-report.json the pipeline wrote")
    gate = (arguments or {}).get("gate")
    result = module.analyze(report, gate)
    return _status_payload("easycirq_status", "easycirq.mcp.status/v1", result,
                           True, "只读：读 KPI 报告与通行证，不连 EDA")


def run_card(arguments):
    """The customer delivery card: can this board be ordered?"""
    module = _load_script_module("sch_delivery_card")
    kpi_path = (arguments or {}).get("kpi_report")
    if not kpi_path:
        raise ToolError("KPI_REPORT_REQUIRED", "缺少 kpi_report",
                        "传入门禁产出的 kpi-report.json 路径")
    try:
        report = module._load(resolve_path(kpi_path, "kpi_report"))
    except (OSError, ValueError) as exc:
        raise ToolError("KPI_REPORT_UNREADABLE", str(exc))
    gate = (arguments or {}).get("gate")
    pcb = None
    pcb_path = (arguments or {}).get("pcb_drc")
    if pcb_path:
        try:
            raw = json.loads(resolve_path(pcb_path, "pcb_drc").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ToolError("PCB_DRC_UNREADABLE", str(exc))
        violations = raw.get("violations") or []
        passed = raw.get("passed")
        pcb = {
            "checked": True,
            "passed": bool(passed) if passed is not None else not violations,
            "violations": len(violations),
            "reason": (violations[0].get("message") if violations else ""),
        }
    result = module.analyze(report, gate, pcb)
    return _status_payload("easycirq_card", "easycirq.mcp.card/v1", result,
                           True, "只读：有通行证才说「可以打样」")


def run_setup(arguments):
    """Run the local `easycirq setup --json` check (needs the CLI on PATH)."""
    exe = shutil.which("easycirq")
    if not exe:
        raise ToolError("EASYCIRQ_CLI_NOT_FOUND",
                        "本机 PATH 上没有 easycirq",
                        "先安装 EasyCirq 工具链，再调用这个工具")
    timeout = min(int((arguments or {}).get("timeout_s", 60)), 300)
    try:
        proc = subprocess.run([exe, "setup", "--json"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError("EASYCIRQ_SETUP_TIMEOUT", f"easycirq setup 超过 {timeout}s")
    # setup exits 0 when ready and 2 when something is missing; both carry a report
    if proc.returncode not in (0, 2):
        raise ToolError("EASYCIRQ_SETUP_FAILED",
                        (proc.stderr or proc.stdout or "")[:400])
    try:
        report = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise ToolError("EASYCIRQ_SETUP_UNPARSEABLE",
                        (proc.stdout or "")[:400])
    checks = report.get("checks") or []
    return {
        "schema": "easycirq.mcp.setup/v1",
        "tool": "easycirq_setup",
        "state": "ready" if str(report.get("verdict", "")).lower() == "ok" else "not_ready",
        "headline": ("一切就绪" if str(report.get("verdict", "")).lower() == "ok"
                     else "还差一步，按 next 里的步骤做"),
        "next": report.get("nextSteps") or [],
        "runtime": (report.get("runtime") or {}).get("version"),
        "daemon": (report.get("daemon") or {}).get("status"),
        "connector": (report.get("connector") or {}).get("status"),
        "checks": checks,
        "offline": False,
        "eda": "NOT RUN",
        "note": "读本机安装状态；不安装、不导入连接器、不改工程",
    }


def _gate_answer(gate_path):
    """(live, detail) for a gate token, reusing the offline checker's rules."""
    module = _load_script_module("sch_status")
    if not gate_path:
        return False, "没有指定通行证"
    try:
        state, detail = module._gate_state(gate_path)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as-is
        return False, f"通行证读不出来：{exc}"
    # _gate_state returns "live" | "stale" | "missing"; only "live" may proceed
    return state == "live", detail


def run_apply(arguments):
    """Execute a schematic playbook, dry-run by default, gated when asked.

    The tool deliberately accepts only a playbook file, never an arbitrary
    command line: the playbook is auditable and replayable. ``confirm=false``
    (the default) runs ``--dry-run`` so a caller can inspect the plan first.
    """
    playbook = resolve_path((arguments or {}).get("playbook"), "playbook")
    confirm = bool((arguments or {}).get("confirm", False))
    gate_arg = (arguments or {}).get("gate")
    gate_path = resolve_path(gate_arg, "gate") if gate_arg else None

    if confirm:
        live, detail = _gate_answer(gate_path)
        if not live:
            raise ToolError(
                "GATE_NOT_LIVE",
                "没有有效的离线检查通行证，不能写入",
                f"{detail}；先跑一轮门禁并确保 verdict=PASS、apply_allowed=true")

    exe = shutil.which("easycirq")
    if not exe:
        raise ToolError("EASYCIRQ_CLI_NOT_FOUND",
                        "本机 PATH 上没有 easycirq",
                        "先安装 EasyCirq 工具链")
    timeout = min(int((arguments or {}).get("timeout_s", 120)), 600)
    cmd = [exe, "sch", "apply", str(playbook)]
    if not confirm:
        cmd.append("--dry-run")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError("APPLY_TIMEOUT", f"apply 超过 {timeout}s")
    return {
        "schema": "easycirq.mcp.apply/v1",
        "tool": "easycirq_apply",
        "mode": "execute" if confirm else "dry_run",
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
        "gate": str(gate_path) if gate_path else None,
        "offline": False,
        "eda": "NOT RUN",
        "note": ("dry_run 只对账不写入；execute 由 daemon 再次校验通行证"
                 if not confirm else "daemon 会再次校验通行证；写入后必须回读"),
    }


def run_delivery_audit(arguments):
    target = resolve_path(arguments.get("input_path"), "input_path")
    detail = _detail(arguments)
    timeout_s = _timeout(arguments)
    profile = arguments.get("profile")
    if profile not in ("pcb-fabrication", "smt-assembly", "archive"):
        raise ToolError("invalid_profile", "profile must be one of pcb-fabrication, "
                                          "smt-assembly, archive")
    args = ["delivery_audit", "audit", "--input", str(target),
            "--profile", profile]
    for key, flag in (("declarations_path", "--declarations"),
                      ("bom_path", "--bom"), ("cpl_path", "--cpl")):
        raw = arguments.get(key)
        if raw is not None:
            args.extend([flag, str(resolve_path(raw, key))])
    is_file = target.is_file()
    before_hash = _sha256_file(target) if is_file else None
    before_sig = None if is_file else _directory_signature(target)
    tmp = Path(tempfile.mkdtemp(prefix="easycirq-mcp-"))
    try:
        out_dir = tmp / "out"
        proc, duration_ms = _run_module(args + ["--out", str(out_dir)], timeout_s)
        report = report_sha = report_size = None
        report_path = out_dir / "delivery-audit.json"
        if report_path.is_file():
            report, report_sha, report_size = _load_report(report_path)
        after_hash = _sha256_file(target) if is_file else None
        after_sig = None if is_file else _directory_signature(target)
        if is_file:
            input_info = {"path": str(target), "kind": "file",
                          "sha256_before": before_hash, "sha256_after": after_hash,
                          "unchanged": before_hash == after_hash}
        else:
            input_info = {"path": str(target), "kind": "directory",
                          "signature": "names+sizes", "sha256_before": before_sig,
                          "sha256_after": after_sig,
                          "unchanged": before_sig == after_sig,
                          "unchanged_note": "directory signature covers relative "
                                            "names and sizes, not full content"}
        return _build_payload("offline_delivery_audit", "delivery_audit", proc,
                              report, report_sha, report_size, duration_ms,
                              input_info, detail, "status",
                              "delivery_audit.audit",
                              _EXPECTED_EXITS["delivery_audit.audit"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
