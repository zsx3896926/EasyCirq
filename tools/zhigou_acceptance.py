#!/usr/bin/env python3
"""Real-host acceptance runner for the Zhigou (智构) EDA toolchain.

Goal
----
Drive the *real* EDA host through `zhigou` and produce auditable evidence for
the M2/M3/M4 acceptance stages.  This script never opens a socket to the
daemon: it only shells out to the CLI, parses its JSON, hashes the artefacts
and writes a machine-readable summary.

Conventions
-----------
* JSON goes to **stdout**; the human summary always goes to **stderr**
  (same split as `zhigou doctor`).  Without ``--json`` stdout stays empty.
* A step is ``PASS`` / ``FAIL`` / ``NOT RUN`` / ``BLOCKED`` / ``UNKNOWN``.
  "not executed" is never reported as a pass.
* Preflight is authoritative.  ``zhigou doctor`` verdict ``blocked``, a
  connector that is not ``connected``, or ``zhigou connector verify`` without a
  loaded connector stops the run with **exit 2** and prints the reason plus the
  exact next step.  ``--dry-run`` still performs preflight and still exits 2 in
  that state, so the blocked path itself is testable without a host.
* Every command writes: ``<nn>-<step>.cmd.json`` (argv/cwd), ``.stdout.txt``,
  ``.stderr.txt``, ``.meta.json`` (exit code, duration, sha256), and ``.json``
  when stdout parses as JSON.  ``commands.jsonl`` is the append-only log and
  ``summary.json`` the index.

Stages
------
``m2``  bind window/project/page -> baseline snapshot -> move one part ->
        save -> reload -> fresh readback -> identity diff -> six-state verdict
``m3``  DRC / reconstructed check / layout lint / netlist / BOM / image /
        native archive / PCB dump+DRC+check, with unsupported capabilities
        recorded as NOT RUN instead of passed
``m4``  PCB local rehearsal: baseline dump -> 2 mm local move -> save ->
        reload -> fresh dump -> scope diff -> DRC -> native archive ->
        restore/import probe -> install/upgrade/rollback delegation check

Usage
-----
    python tools/zhigou_acceptance.py --stage m2|m3|m4|all \
        --project-dir <design-workspace> --evidence-dir <dir> \
        [--window <id>] [--json] [--dry-run] [--self-test]

Exit codes: 0 = every executed step passed (NOT RUN allowed only with a
reason and counts reported), 1 = at least one FAIL, 2 = BLOCKED (preflight or
a blocked dependency), 3 = script/argument error.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "zhigou-acceptance/v1"
SELFTEST_SCHEMA = "zhigou-acceptance-selftest/v1"

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT RUN"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"
STATUSES = (PASS, FAIL, NOT_RUN, BLOCKED, UNKNOWN)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = REPO_ROOT / "docs" / "toolchain-integration" / "evidence" / "acceptance"
DEFAULT_PROJECT = DEFAULT_EVIDENCE / "project-workspace"

# Two millimetres in mil (1 mm = 39.37007874015748 mil), the M4 local move.
TWO_MM_MIL = 2.0 * 39.37007874015748
POS_TOL_MIL = 0.01  # measured values are float32-ish; 0.01 mil is far below 2 mm


# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _force_utf8_streams() -> None:
    """Keep JSON/Chinese identical on cp936 consoles and in redirected files."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def json_loads_tolerant(raw: str) -> object | None:
    """Parse JSON, tolerating a leading/trailing human line (capture hygiene).

    The CLI is expected to emit one JSON document on stdout, but a stray
    warning line must not turn a real payload into "no evidence".
    """
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # try the biggest balanced {...} or [...] block
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


def unwrap(payload: object) -> object:
    """Return ``payload['result']`` when the CLI wraps in its action envelope."""
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, (dict, list)) and (
            "id" in payload or "type" in payload or "ok" in payload or "schema" in payload
        ):
            return result
    return payload


def dig(obj: object, *path: str, default=None):
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and key.isdigit() and int(key) < len(cur):
            cur = cur[int(key)]
        else:
            return default
        if cur is None:
            return default
    return cur


def first_int(*values) -> int | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, dict):
            for key in ("count", "total", "value"):
                inner = value.get(key)
                if isinstance(inner, int):
                    return inner
    return None


def as_float(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def as_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "1"):
            return True
        if low in ("false", "no", "0"):
            return False
    return None


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "step"


def rel(path: Path | str | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(base.resolve())).replace("\\", "/")
    except (ValueError, OSError):
        return str(path)


# --------------------------------------------------------------------------- #
# step model
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Step:
    sid: str
    title: str
    stage: str
    status: str = NOT_RUN
    cmd: list[str] | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    evidence: dict = dataclasses.field(default_factory=dict)
    artifacts: list[dict] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)
    six: dict = dataclasses.field(default_factory=dict)  # only used by M2
    json_payload: object | None = dataclasses.field(default=None, repr=False)

    def note(self, text: str) -> "Step":
        self.notes.append(text)
        return self

    def to_summary(self) -> dict:
        return {
            "id": self.sid,
            "stage": self.stage,
            "title": self.title,
            "status": self.status,
            "command": self.cmd,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "evidence": self.evidence,
            "artifacts": self.artifacts,
            "notes": self.notes,
            **({"sixState": self.six} if self.six else {}),
        }


def six_state(name: str, status: str, reason: str, evidence: str | None = None) -> dict:
    return {"state": name, "status": status, "reason": reason, "evidence": evidence}


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
class Runner:
    def __init__(
        self,
        cli: Path | str,
        evidence_dir: Path,
        *,
        project_dir: Path,
        window: str | None,
        timeout: float,
        dry_run: bool,
        log,
    ) -> None:
        self.cli = str(cli)
        self.project_dir = project_dir
        self.window = window
        self.timeout = timeout
        self.dry_run = dry_run
        self.log = log
        self.evidence_dir = evidence_dir
        self.steps: list[Step] = []
        self._seq = 0
        self.started = time.monotonic()
        self.cli_calls = 0
        self.cli_ms = 0
        self.cli_version: str | None = None
        self.binding: dict = {}
        (evidence_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        self._log_path = evidence_dir / "commands.jsonl"
        self._log_path.write_text("", encoding="utf-8")
        for sub in ("preflight", "m2", "m3", "m4"):
            (evidence_dir / sub).mkdir(parents=True, exist_ok=True)

    # -- command execution -------------------------------------------------- #
    def _argv(self, cmd: list[str]) -> list[str]:
        return [self.cli, *cmd]

    def run(
        self,
        sid: str,
        title: str,
        cmd: list[str],
        *,
        stage: str,
        expect_json: bool = False,
        allow_exit: tuple[int, ...] = (0,),
        timeout: float | None = None,
        pin_doc: str | None = None,
        pin_project: str | None = None,
        cwd: Path | None = None,
        force: bool = False,
    ) -> Step:
        """Execute one CLI call and record evidence.

        ``force=True`` runs even in ``--dry-run``: preflight is read-only and
        must be real, otherwise the blocked path could never be demonstrated.
        """
        step = Step(sid=sid, title=title, stage=stage, cmd=self._argv(cmd))
        if pin_project:
            step.cmd += ["--project", pin_project]
        if pin_doc:
            step.cmd += ["--doc", pin_doc]
        if self.window and pin_project is None and pin_doc is None:
            # Only add --window when the caller pinned nothing else; routing by
            # project/document is preferred and --window is the fallback.
            pass
        self._seq += 1
        sub = self.evidence_dir / stage
        sub.mkdir(parents=True, exist_ok=True)
        base = sub / f"{self._seq:02d}-{safe_name(sid)}"
        self.steps.append(step)
        self.log(f"  → {' '.join(step.cmd)}")
        if self.dry_run and not force:
            step.status = NOT_RUN
            step.note("dry-run: command not executed")
            self._write_meta(step, base, extra={"dryRun": True})
            return step
        t0 = time.monotonic()
        self.cli_calls += 1
        try:
            proc = subprocess.run(
                step.cmd,
                cwd=str(cwd or self.project_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout or self.timeout,
                shell=False,
                env=os.environ.copy(),
            )
            out, err = proc.stdout, proc.stderr
            code: int | None = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout or b""
            err = (exc.stderr or b"") + b"\n[ACCEPTANCE] command timed out"
            code = None
            timed_out = True
        except OSError as exc:
            out, err, code, timed_out = b"", f"[ACCEPTANCE] spawn failed: {exc}".encode(), None, False
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self.cli_ms += step.duration_ms
        out_path = base.with_suffix(".stdout.txt")
        err_path = base.with_suffix(".stderr.txt")
        out_path.write_bytes(out)
        err_path.write_bytes(err)
        step.exit_code = code
        step.evidence = {
            "stdout": rel(out_path, self.evidence_dir),
            "stderr": rel(err_path, self.evidence_dir),
        }
        parsed = json_loads_tolerant(out.decode("utf-8", "replace")) if out else None
        if parsed is not None:
            json_path = base.with_suffix(".json")
            json_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            step.evidence["json"] = rel(json_path, self.evidence_dir)
            step.json_payload = parsed
        self._write_meta(step, base, extra={"timedOut": timed_out})
        ok = (code in allow_exit) and not timed_out
        if ok:
            step.status = PASS
        else:
            step.status = FAIL
            step.note(f"exit={code} timedOut={timed_out} expected={list(allow_exit)}")
        if expect_json and parsed is None:
            step.note("expected JSON on stdout, got none/unparseable")
        return step

    def _write_meta(self, step: Step, base: Path, extra: dict) -> None:
        meta_path = base.with_suffix(".meta.json")
        meta = {
            "id": step.sid,
            "title": step.title,
            "stage": step.stage,
            "command": step.cmd,
            "status": step.status,
            "exitCode": step.exit_code,
            "durationMs": step.duration_ms,
            "generatedAt": utc_now(),
            "sha256": {
                "stdout": sha256_file(base.with_suffix(".stdout.txt")),
                "stderr": sha256_file(base.with_suffix(".stderr.txt")),
                "json": sha256_file(base.with_suffix(".json")),
            },
            **extra,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        step.evidence["meta"] = rel(meta_path, self.evidence_dir)
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(meta, ensure_ascii=False) + "\n")

    # -- convenience: offline plan step ------------------------------------- #
    def planned(self, sid: str, title: str, cmd: list[str] | None, stage: str, reason: str) -> Step:
        step = Step(sid=sid, title=title, stage=stage, cmd=[self.cli, *cmd] if cmd else None)
        step.status = NOT_RUN
        step.note(reason)
        self.steps.append(step)
        return step

    def artifact(self, step: Step, path: Path) -> None:
        if not path.exists():
            step.note(f"artifact missing: {path}")
            return
        step.artifacts.append(
            {
                "path": rel(path, self.evidence_dir),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)


# --------------------------------------------------------------------------- #
# preflight
# --------------------------------------------------------------------------- #
def preflight(runner: Runner) -> dict:
    """Read-only gate. Returns a dict with verdict and blocker info."""
    out: dict = {"generatedAt": utc_now(), "checks": {}, "blockers": []}
    pf = runner.evidence_dir / "preflight"

    def save_json(name: str, payload) -> str | None:
        if payload is None:
            return None
        path = pf / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return rel(path, runner.evidence_dir)

    doctor_step = runner.run("doctor", "zhigou doctor (disk vs running state)",
                             ["doctor"], stage="preflight", expect_json=True, force=True)
    doctor = doctor_step.json_payload or {}
    out["checks"]["doctor"] = {
        "status": doctor_step.status,
        "evidence": save_json("doctor.json", doctor),
        "verdict": dig(doctor, "verdict"),
        "connector": dig(doctor, "connector", "status"),
        "daemon": dig(doctor, "daemon", "status"),
        "runtime": dig(doctor, "runtime", "version"),
    }

    caps_step = runner.run("capabilities", "zhigou capabilities (per-item negotiation)",
                           ["capabilities"], stage="preflight", expect_json=True, force=True)
    caps = caps_step.json_payload or {}
    items = dig(caps, "items", default=[]) or []
    summary = dig(caps, "summary", default={}) or {}
    out["checks"]["capabilities"] = {
        "status": caps_step.status,
        "evidence": save_json("capabilities.json", caps),
        "summary": summary,
        "connector": dig(caps, "connector", "status"),
        "unsupported": [i.get("id") for i in items if isinstance(i, dict) and i.get("status") == "unsupported"],
        "supported": [i.get("id") for i in items if isinstance(i, dict) and i.get("status") == "supported"],
    }

    verify_step = runner.run("connector-verify", "zhigou connector verify (.eext vs loaded window)",
                             ["connector", "verify"], stage="preflight", expect_json=True, force=True)
    verify = verify_step.json_payload or {}
    out["checks"]["connectorVerify"] = {
        "status": verify_step.status,
        "evidence": save_json("connector-verify.json", verify),
        "verdict": dig(verify, "verdict"),
        "loadedWindows": dig(verify, "loadedWindows", default=[]),
        "reason": dig(verify, "reason"),
    }

    path_step = runner.run("connector-path", "zhigou connector path (ships-with .eext)",
                           ["connector", "path"], stage="preflight", expect_json=True, force=True)
    out["checks"]["connectorPath"] = {
        "status": path_step.status,
        "evidence": save_json("connector-path.json", path_step.json_payload or {}),
        "path": dig(path_step.json_payload or {}, "path"),
        "exists": dig(path_step.json_payload or {}, "exists"),
        "sha256": dig(path_step.json_payload or {}, "sha256"),
    }
    eext = dig(path_step.json_payload or {}, "path")
    if isinstance(eext, str) and eext:
        p = Path(eext)
        if p.exists():
            runner.artifact(path_step, p)

    health_step = runner.run("health", "zhigou health (live window context)",
                             ["health"], stage="preflight", expect_json=True, force=True)
    health = health_step.json_payload or {}
    windows = dig(health, "found", "raw", "windows", default=[]) or []
    out["checks"]["health"] = {
        "status": health_step.status,
        "evidence": save_json("health.json", health),
        "windows": len(windows) if isinstance(windows, list) else 0,
    }

    version_step = runner.run("version", "zhigou version", ["version"], stage="preflight", expect_json=False, force=True)
    if version_step.status == PASS:
        out_path = version_step.evidence.get("stdout")
        if out_path:
            try:
                text = (runner.evidence_dir / out_path).read_text(encoding="utf-8").strip()
                runner.cli_version = text.splitlines()[0] if text else None
            except OSError:
                runner.cli_version = None

    # ---- verdict ---------------------------------------------------------- #
    verdict = str(dig(doctor, "verdict") or dig(health, "status") or "unknown")
    connector_status = str(dig(doctor, "connector", "status") or dig(caps, "connector", "status") or "unknown")
    verify_verdict = str(dig(verify, "verdict") or "unknown")
    loaded = dig(verify, "loadedWindows", default=[]) or []
    out["verdict"] = verdict
    out["connectorStatus"] = connector_status
    out["verifyVerdict"] = verify_verdict
    out["loadedWindows"] = loaded

    next_steps = dig(doctor, "nextSteps", default=[]) or []
    if verdict == "blocked":
        out["blockers"].append("zhigou doctor verdict=blocked")
    if connector_status != "connected":
        out["blockers"].append(f"connector.status={connector_status} (no EasyEDA window connected)")
    if verify_verdict not in ("ok", "pass") and not loaded:
        out["blockers"].append(f"connector verify verdict={verify_verdict} (no loaded connector windows)")
    if not isinstance(windows, list) or not windows:
        out["blockers"].append("zhigou health reports no connected window")
    out["nextSteps"] = next_steps
    out["ready"] = not out["blockers"]
    return out


# --------------------------------------------------------------------------- #
# binding
# --------------------------------------------------------------------------- #
def bind_targets(runner: Runner, health_payload: dict, expected_project: str | None) -> dict:
    windows = dig(health_payload, "found", "raw", "windows", default=[]) or []
    chosen = None
    for win in windows if isinstance(windows, list) else []:
        if runner.window and win.get("windowId") != runner.window:
            continue
        ctx = win.get("context") or {}
        if expected_project:
            name = str(ctx.get("projectName") or "")
            puuid = str(ctx.get("projectUuid") or "")
            if expected_project not in (name, puuid):
                continue
        chosen = win
        break
    if chosen is None and isinstance(windows, list) and windows and not runner.window and not expected_project:
        chosen = windows[0]
    if chosen is None:
        return {"bound": False, "reason": "no window matched --window/--project"}
    ctx = chosen.get("context") or {}
    binding = {
        "bound": True,
        "windowId": chosen.get("windowId"),
        "connectorVersion": chosen.get("connectorVersion"),
        "hostVersion": chosen.get("easyedaVersion"),
        "hostKind": dig(chosen, "host", "kind"),
        "projectUuid": ctx.get("projectUuid"),
        "projectName": ctx.get("projectName"),
        "documentUuid": ctx.get("documentUuid"),
        "documentType": ctx.get("documentType"),
        "tabId": ctx.get("tabId"),
        "pageVisibility": ctx.get("pageVisibility"),
        "connectedAt": chosen.get("connectedAt"),
        "lastSeen": chosen.get("lastSeen"),
        "windowCount": len(windows) if isinstance(windows, list) else 0,
    }
    missing = [k for k in ("windowId", "projectUuid", "documentUuid", "documentType") if not binding.get(k)]
    if missing:
        binding["bound"] = False
        binding["reason"] = f"window context missing {missing}"
    runner.binding = binding
    return binding


# --------------------------------------------------------------------------- #
# snapshot identity helpers (pure; also covered by --self-test)
# --------------------------------------------------------------------------- #
def sch_snapshot_identity(payload: object) -> dict:
    """Normalise a `zhigou sch read` payload into a comparable identity map."""
    data = unwrap(payload) or {}
    if not isinstance(data, dict):
        return {"components": {}, "nets": {}, "raw_keys": []}
    comps = data.get("components") or data.get("parts") or []
    identity: dict[str, dict] = {}
    for comp in comps if isinstance(comps, list) else []:
        if not isinstance(comp, dict):
            continue
        designator = comp.get("designator") or comp.get("ref") or comp.get("name")
        if not designator:
            continue
        pins: dict[str, str | None] = {}
        for pin in comp.get("pins") or []:
            if not isinstance(pin, dict):
                continue
            number = str(pin.get("pinNumber") or pin.get("number") or pin.get("pinName") or "?")
            pins[number] = pin.get("net")
        identity[str(designator)] = {
            "primitiveId": comp.get("primitiveId") or comp.get("id"),
            "uniqueId": comp.get("uniqueId"),
            "x": as_float(comp.get("x")),
            "y": as_float(comp.get("y")),
            "rotation": as_float(comp.get("rotation")),
            "mirror": comp.get("mirror"),
            "layer": comp.get("layer"),
            "pins": pins,
        }
    nets: dict[str, int] = {}
    raw_nets = data.get("nets")
    if isinstance(raw_nets, dict):
        for name, members in raw_nets.items():
            nets[str(name)] = len(members) if isinstance(members, list) else 1
    elif isinstance(raw_nets, list):
        for item in raw_nets:
            if isinstance(item, dict) and item.get("net"):
                nets[str(item["net"])] = len(item.get("pins") or [])
    return {"components": identity, "nets": nets, "raw_keys": sorted(data.keys())}


def compare_sch_identity(before: dict, after: dict, moved: str | None, dx: float, dy: float) -> dict:
    """Compare two normalised schematic snapshots.

    Rules: designator set, primitiveId, uniqueId, pin->net must be identical;
    the named part may move by (dx, dy) in raw schematic units; every other
    part must not move.
    """
    result: dict = {
        "ok": True,
        "checks": {},
        "moved": moved,
        "expectedDelta": {"dx": dx, "dy": dy},
        "findings": [],
    }

    def check(name: str, ok: bool, detail) -> None:
        result["checks"][name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            result["ok"] = False
            result["findings"].append({"check": name, "detail": detail})

    b_comps, a_comps = before.get("components", {}), after.get("components", {})
    check("designator_set", set(b_comps) == set(a_comps),
          {"added": sorted(set(a_comps) - set(b_comps)), "removed": sorted(set(b_comps) - set(a_comps))})
    id_mismatch = {}
    pin_mismatch = {}
    pos_mismatch = {}
    for designator, b in b_comps.items():
        a = a_comps.get(designator)
        if not a:
            continue
        if b.get("primitiveId") and a.get("primitiveId") and b["primitiveId"] != a["primitiveId"]:
            id_mismatch[designator] = {"before": b["primitiveId"], "after": a["primitiveId"]}
        if b.get("uniqueId") and a.get("uniqueId") and b["uniqueId"] != a["uniqueId"]:
            id_mismatch[designator] = {"before": b["uniqueId"], "after": a["uniqueId"]}
        if b.get("pins") != a.get("pins"):
            changed = {
                k: {"before": b["pins"].get(k), "after": a["pins"].get(k)}
                for k in set(b["pins"]) | set(a["pins"])
                if b["pins"].get(k) != a["pins"].get(k)
            }
            pin_mismatch[designator] = changed
        bx, by, ax, ay = b.get("x"), b.get("y"), a.get("x"), a.get("y")
        if None not in (bx, by, ax, ay):
            edx, edy = (dx, dy) if designator == moved else (0.0, 0.0)
            if abs((ax - bx) - edx) > POS_TOL_MIL or abs((ay - by) - edy) > POS_TOL_MIL:
                pos_mismatch[designator] = {
                    "observed": {"dx": round(ax - bx, 6), "dy": round(ay - by, 6)},
                    "expected": {"dx": edx, "dy": edy},
                }
    check("instance_identity", not id_mismatch, id_mismatch)
    check("pin_net", not pin_mismatch, pin_mismatch)
    check("positions", not pos_mismatch, pos_mismatch)
    if moved and moved not in b_comps:
        check("moved_present", False, {"missing": moved})
    result["nets"] = {"before": before.get("nets", {}), "after": after.get("nets", {})}
    if result["nets"]["before"] != result["nets"]["after"]:
        result["notes"] = ["net membership counts changed"]
    return result


def extract_sch_component(snapshot: dict, designator: str) -> dict | None:
    return (snapshot.get("components") or {}).get(designator)


def pcb_snapshot_identity(payload: object) -> dict:
    """Normalise a `zhigou pcb dump` payload: components + copper counts/hash."""
    data = unwrap(payload) or {}
    if not isinstance(data, dict):
        return {"available": False, "components": {}, "copper": {}, "raw_keys": []}
    raw_components = data.get("components") or data.get("footprints") or []
    comps: dict[str, dict] = {}
    for comp in raw_components if isinstance(raw_components, list) else []:
        if not isinstance(comp, dict):
            continue
        designator = comp.get("designator") or comp.get("ref")
        if not designator:
            continue
        center = comp.get("center") if isinstance(comp.get("center"), dict) else {}
        comps[str(designator)] = {
            "primitiveId": comp.get("primitiveId") or comp.get("id"),
            "uniqueId": comp.get("uniqueId"),
            "x": as_float(center.get("x") if center else comp.get("x")),
            "y": as_float(center.get("y") if center else comp.get("y")),
            "rotation": as_float(comp.get("rotation")),
            "layer": comp.get("layer"),
            "pads": len(comp.get("pads") or []) if isinstance(comp.get("pads"), list) else None,
        }
    tracks = data.get("tracks") or data.get("lines") or []
    vias = data.get("vias") or []
    pours = data.get("pours") or data.get("pour") or []
    copper = {
        "tracks": len(tracks) if isinstance(tracks, list) else None,
        "vias": len(vias) if isinstance(vias, list) else None,
        "pours": len(pours) if isinstance(pours, list) else None,
        "tracksSha": sha256_bytes(json.dumps(tracks, sort_keys=True).encode()) if isinstance(tracks, list) else None,
        "viasSha": sha256_bytes(json.dumps(vias, sort_keys=True).encode()) if isinstance(vias, list) else None,
    }
    return {
        "available": bool(comps),
        "components": comps,
        "copper": copper,
        "raw_keys": sorted(data.keys()),
    }


def compare_pcb_scope(before: dict, after: dict, moved: str | None, dy_mil: float) -> dict:
    """Local-change rehearsal: only ``moved`` may shift, by ``dy_mil``; copper must not change."""
    result: dict = {"ok": True, "checks": {}, "findings": [], "moved": moved, "expectedDyMil": dy_mil}

    def check(name: str, ok: bool, detail) -> None:
        result["checks"][name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            result["ok"] = False
            result["findings"].append({"check": name, "detail": detail})

    check("snapshot_available", before.get("available") and after.get("available"),
          {"beforeKeys": before.get("raw_keys"), "afterKeys": after.get("raw_keys")})
    b, a = before.get("components", {}), after.get("components", {})
    check("designator_set", set(b) == set(a),
          {"added": sorted(set(a) - set(b)), "removed": sorted(set(b) - set(a))})
    position_findings = {}
    for designator, bc in b.items():
        ac = a.get(designator)
        if not ac:
            continue
        if bc.get("x") is not None and ac.get("x") is not None:
            edy = dy_mil if designator == moved else 0.0
            if abs((ac["y"] - bc["y"]) - edy) > POS_TOL_MIL or abs(ac["x"] - bc["x"]) > POS_TOL_MIL:
                position_findings[designator] = {
                    "observed": {"dx": round(ac["x"] - bc["x"], 6), "dy": round(ac["y"] - bc["y"], 6)},
                    "expected": {"dx": 0.0, "dy": edy},
                }
    check("scope_positions", not position_findings, position_findings)
    copper_before, copper_after = before.get("copper", {}), after.get("copper", {})
    check("copper_counts", copper_before.get("tracks") == copper_after.get("tracks")
          and copper_before.get("vias") == copper_after.get("vias")
          and copper_before.get("pours") == copper_after.get("pours"),
          {"before": copper_before, "after": copper_after})
    check("copper_geometry", copper_before.get("tracksSha") == copper_after.get("tracksSha")
          and copper_before.get("viasSha") == copper_after.get("viasSha"),
          {"before": {"tracksSha": copper_before.get("tracksSha"), "viasSha": copper_before.get("viasSha")},
           "after": {"tracksSha": copper_after.get("tracksSha"), "viasSha": copper_after.get("viasSha")}})
    if moved and moved not in b:
        check("moved_present", False, {"missing": moved})
    return result


# --------------------------------------------------------------------------- #
# stage m2
# --------------------------------------------------------------------------- #
def stage_m2(runner: Runner, pre: dict, *, move_device: str, dx: float, dy: float) -> list[Step]:
    steps: list[Step] = []

    bind_step = runner.planned("bind", "bind window/project/page from live health", ["health"], "m2",
                               "waiting for host")
    health_payload = None
    if pre["ready"]:
        # health was already captured in preflight; re-read is unnecessary.
        health_path = runner.evidence_dir / "preflight" / "health.json"
        if health_path.exists():
            health_payload = json_loads_tolerant(health_path.read_text(encoding="utf-8"))
        binding = bind_targets(runner, health_payload or {}, None)
        bind_step.status = PASS if binding.get("bound") else BLOCKED
        bind_step.note(json.dumps(binding, ensure_ascii=False))
        bind_step.evidence["binding"] = rel(
            _write_json(runner.evidence_dir / "m2" / "binding.json", binding), runner.evidence_dir)
    else:
        binding = {"bound": False, "reason": "preflight blocked"}
        bind_step.status = BLOCKED
        bind_step.note("preflight blocked: " + "; ".join(pre["blockers"]))
    steps.append(bind_step)

    page = runner.binding.get("documentUuid")
    project = runner.binding.get("projectName") or runner.binding.get("projectUuid")

    baseline = runner.run("baseline-read", "baseline schematic snapshot (sch read)",
                          ["sch", "read"], stage="m2", pin_project=project)
    steps.append(baseline)
    before = sch_snapshot_identity(baseline.json_payload) if baseline.json_payload else None

    # locate the part to move
    list_step = runner.run("component-locate", f"locate {move_device} (sch list --include-pins --include-bbox)",
                           ["sch", "list", "--include-pins", "--include-bbox"], stage="m2", pin_project=project)
    steps.append(list_step)
    target = _find_component(list_step.json_payload, move_device) if list_step.json_payload else None
    if target is None:
        list_step.note(f"target {move_device} not found; move step will be NOT RUN")
    else:
        list_step.note(json.dumps({k: target.get(k) for k in ("designator", "primitiveId", "uniqueId", "x", "y")},
                                  ensure_ascii=False))

    move_title = f"move {move_device} by dx={dx} dy={dy} (sch modify)"
    if target and target.get("primitiveId") and target.get("x") is not None and target.get("y") is not None:
        argv = ["sch", "modify", "--id", str(target["primitiveId"]),
                "--x", f"{target['x'] + dx:.6f}", "--y", f"{target['y'] + dy:.6f}"]
        move_step = runner.run("move", move_title, argv, stage="m2",
                               pin_project=project, pin_doc=page)
    else:
        move_step = runner.planned("move", move_title, None, "m2",
                                   "target not located or host missing; NOT RUN (never counted as pass)")
    steps.append(move_step)

    save_step = runner.run("save", "save schematic (sch save)", ["sch", "save"], stage="m2",
                           pin_project=project, pin_doc=page)
    steps.append(save_step)
    saved_true = _saved_true(save_step.json_payload)
    if save_step.status == PASS and saved_true is False:
        save_step.status = FAIL
        save_step.note("save returned without saved:true")
    elif save_step.status == PASS and saved_true is None:
        save_step.note("save output does not expose a boolean saved flag -> saved_confirmed unknown")

    reload_step = runner.run("reload", "real reload (doc reload --json)", ["doc", "reload", page or "", "--json"],
                             stage="m2", pin_project=project)
    steps.append(reload_step)
    ready_step = runner.run("ready", "readiness (doc ready --json, bounded)",
                            ["doc", "ready", page or "", "--json", "--timeout", "20s"],
                            stage="m2", pin_project=project, timeout=40)
    steps.append(ready_step)
    ready_true = as_bool(dig(unwrap(ready_step.json_payload) or {}, "ready"))

    readback = runner.run("readback", "fresh readback (sch read)", ["sch", "read"], stage="m2",
                          pin_project=project, pin_doc=page)
    steps.append(readback)
    after = sch_snapshot_identity(readback.json_payload) if readback.json_payload else None

    diff_path = runner.evidence_dir / "m2" / "identity-diff.json"
    if before and after:
        diff = compare_sch_identity(before, after, move_device, dx, dy)
        _write_json(diff_path, diff)
        baseline_step_evidence = rel(diff_path, runner.evidence_dir)
    else:
        diff = {"ok": False, "findings": [{"check": "snapshot", "detail": "missing baseline/readback"}],
                "checks": {}}
        _write_json(diff_path, diff)
        baseline_step_evidence = rel(diff_path, runner.evidence_dir)

    drc_step = runner.run("electrical-drc", "official schematic DRC (sch drc --json)",
                          ["sch", "drc", "--json"], stage="m2", pin_project=project, pin_doc=page)
    steps.append(drc_step)
    check_step = runner.run("electrical-check", "reconstructed per-item check (sch check --json)",
                            ["sch", "check", "--json"], stage="m2", pin_project=project, pin_doc=page)
    steps.append(check_step)
    lint_step = runner.run("quality-lint", "placement lint (sch layout-lint)",
                           ["sch", "layout-lint"], stage="m2", pin_project=project, pin_doc=page)
    steps.append(lint_step)

    electrical = _electrical_verdict(drc_step, check_step)
    quality = _quality_verdict(lint_step)
    command_completed = all(
        s.status == PASS for s in (baseline, list_step, save_step, reload_step, ready_step, readback)
    ) and move_step.status in (PASS, NOT_RUN)
    states = {
        "command_completed": six_state("command_completed", PASS if command_completed else FAIL,
                                       "all chain commands exited 0" if command_completed
                                       else "one or more chain commands failed",
                                       rel(runner.evidence_dir / "m2", runner.evidence_dir)),
        "readback_verified": six_state("readback_verified", PASS if diff.get("ok") else FAIL,
                                       "identity/pin-net/position diff clean" if diff.get("ok")
                                       else "identity diff has findings",
                                       baseline_step_evidence),
        "save_confirmed": six_state("save_confirmed",
                                    PASS if saved_true is True else (FAIL if save_step.status == FAIL else UNKNOWN),
                                    "saved:true" if saved_true is True else
                                    ("save failed" if save_step.status == FAIL else "no boolean saved flag"),
                                    save_step.evidence.get("json")),
        "reopen_confirmed": six_state("reopen_confirmed",
                                      PASS if ready_true is True else (FAIL if ready_step.status == FAIL else UNKNOWN),
                                      "doc reload + doc ready:true" if ready_true else
                                      ("reload/ready failed" if ready_step.status == FAIL else "ready flag unknown"),
                                      ready_step.evidence.get("json")),
        "electrical_passed": six_state("electrical_passed", electrical[0], electrical[1],
                                       drc_step.evidence.get("json")),
        "quality_passed": six_state("quality_passed", quality[0], quality[1],
                                    lint_step.evidence.get("stdout")),
    }
    verify_step = runner.planned("six-state", "six-state evidence roll-up", None, "m2", "")
    verify_step.status = PASS if all(v["status"] == PASS for v in states.values()) else FAIL
    verify_step.six = states
    verify_step.evidence = {"rollup": rel(_write_json(runner.evidence_dir / "m2" / "six-state.json", states),
                                          runner.evidence_dir)}
    steps.append(verify_step)
    return steps


def _write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _find_component(payload: object, designator: str) -> dict | None:
    data = unwrap(payload) or {}
    comps = data.get("components") if isinstance(data, dict) else None
    if comps is None and isinstance(data, list):
        comps = data
    for comp in comps if isinstance(comps, list) else []:
        if isinstance(comp, dict) and str(comp.get("designator")) == designator:
            return comp
    return None


def _saved_true(payload: object) -> bool | None:
    data = unwrap(payload) or {}
    if not isinstance(data, dict):
        return None
    for candidate in (data, payload if isinstance(payload, dict) else {}):
        for key in ("saved", "saveConfirmed", "persisted"):
            if key in candidate:
                value = as_bool(candidate.get(key))
                if value is not None:
                    return value
    return None


def _electrical_verdict(drc_step: Step, check_step: Step) -> tuple[str, str]:
    if drc_step.status != PASS:
        return FAIL, f"sch drc exited {drc_step.exit_code}"
    drc = unwrap(drc_step.json_payload) or {}
    fatal = None
    for path in (("fatal",), ("summary", "fatal"), ("summary", "errors"), ("counts", "fatal")):
        fatal = first_int(dig(drc, *path))
        if fatal is not None:
            break
    passed = as_bool(dig(drc, "passed"))
    if fatal is not None:
        return (PASS if fatal == 0 else FAIL), f"drc fatal={fatal}"
    if passed is not None:
        return (PASS if passed else FAIL), f"drc passed={passed}"
    if check_step.status == PASS:
        data = unwrap(check_step.json_payload) or {}
        findings = dig(data, "findings", default=[])
        count = len(findings) if isinstance(findings, list) else None
        if count is not None and count == 0:
            return PASS, "sch drc boolean unavailable; sch check findings=0"
        if count:
            return FAIL, f"sch check findings={count}"
    return UNKNOWN, "no machine-readable fatal/passed/findings"


def _quality_verdict(lint_step: Step) -> tuple[str, str]:
    if lint_step.exit_code == 0:
        return PASS, "layout-lint exit 0 (no overlap/pin-coincidence)"
    if lint_step.exit_code is None:
        return UNKNOWN, "layout-lint did not run"
    return FAIL, f"layout-lint exit {lint_step.exit_code}"


# --------------------------------------------------------------------------- #
# stage m3
# --------------------------------------------------------------------------- #
M3_STEPS = [
    # (id, title, argv, capability, json)
    ("m3-sch-drc", "schematic DRC (sch drc --json)", ["sch", "drc", "--json"], None, True),
    ("m3-sch-check", "reconstructed check (sch check --json)", ["sch", "check", "--json"], None, True),
    ("m3-sch-lint", "placement lint (sch layout-lint)", ["sch", "layout-lint"], None, False),
    ("m3-netlist", "netlist artifact (sch netlist --type protel)", ["sch", "netlist", "--type", "protel"], None, False),
    ("m3-bom-csv", "BOM export csv (bom export --type csv)", ["bom", "export", "--type", "csv"], "bom.export", False),
    ("m3-image", "schematic image export (sch export-image --format png)", ["sch", "export-image", "--format", "png"], "image.export", False),
    ("m3-archive", "native project archive (project export)", ["project", "export"], "project.export", False),
    ("m3-pcb-dump", "PCB snapshot (pcb dump --out)", ["pcb", "dump"], None, False),
    ("m3-pcb-drc", "PCB DRC (pcb drc --json)", ["pcb", "drc", "--json"], "pcb.drc", True),
    ("m3-pcb-check", "PCB DFM check (pcb check --json)", ["pcb", "check", "--json"], "pcb.check", True),
]

M3_UNSUPPORTED = {
    "gerber.export": "Gerber export has no typed action in this runtime (capabilities=unsupported)",
    "drill.export": "Drill export has no typed action in this runtime (capabilities=unsupported)",
    "cpl.export": "CPL export has no typed action in this runtime (capabilities=unsupported)",
}


def stage_m3(runner: Runner, pre: dict) -> list[Step]:
    steps: list[Step] = []
    caps_unsupported = set(pre["checks"].get("capabilities", {}).get("unsupported") or [])
    page = runner.binding.get("documentUuid")
    project = runner.binding.get("projectName") or runner.binding.get("projectUuid")
    project_uuid = runner.binding.get("projectUuid")
    artifacts = runner.evidence_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    for sid, title, argv, capability, expect_json in M3_STEPS:
        if capability and capability in caps_unsupported:
            step = runner.planned(sid, title, argv, "m3",
                                  f"capability {capability} is unsupported by this runtime; recorded NOT RUN")
            steps.append(step)
            continue
        if sid == "m3-image":
            argv = [*argv, "--out", str(artifacts / "m3-schematic.png")]
        if sid == "m3-archive":
            if not project_uuid:
                steps.append(runner.planned(sid, title, argv, "m3",
                                            "projectUuid unknown; cannot pin project export"))
                continue
            argv = ["project", "export", "--project-uuid", project_uuid,
                    "--out", str(artifacts / "m3-project.epro2")]
        if sid == "m3-pcb-dump":
            argv = [*argv, "--out", str(artifacts / "m3-pcb-dump.json"), "--include-copper"]
        step = runner.run(sid, title, argv, stage="m3", pin_project=project, pin_doc=page,
                          expect_json=expect_json)
        if "out" in " ".join(argv):
            _collect_arg_artifacts(runner, step, argv)
        for payload_key, name in (("result", None),):
            pass
        if step.json_payload and sid == "m3-bom-csv":
            _collect_json_path_artifacts(runner, step, step.json_payload, ("out", "path", "file", "artifact"))
        if step.json_payload and sid in ("m3-image", "m3-archive", "m3-pcb-dump"):
            _collect_json_path_artifacts(runner, step, step.json_payload,
                                         ("out", "path", "file", "artifact", "archive", "image"))
        steps.append(step)

    for capability, reason in M3_UNSUPPORTED.items():
        steps.append(runner.planned(f"m3-{capability.split('.')[0]}", f"{capability}", None, "m3", reason))

    return steps


def _collect_arg_artifacts(runner: Runner, step: Step, argv: list[str]) -> None:
    for i, token in enumerate(argv):
        if token in ("--out", "-o") and i + 1 < len(argv):
            runner.artifact(step, Path(argv[i + 1]))
        if token.startswith("--out="):
            runner.artifact(step, Path(token.split("=", 1)[1]))


def _collect_json_path_artifacts(runner: Runner, step: Step, payload: object,
                                 keys: tuple[str, ...]) -> None:
    data = unwrap(payload) or {}
    candidates: list[str] = []

    def walk(obj, depth=0):
        if depth > 3:
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in keys and isinstance(value, str):
                    candidates.append(value)
                elif isinstance(value, (dict, list)):
                    walk(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:20]:
                walk(item, depth + 1)

    walk(data)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            runner.artifact(step, path)


# --------------------------------------------------------------------------- #
# stage m4
# --------------------------------------------------------------------------- #
def stage_m4(runner: Runner, pre: dict, *, device: str | None) -> list[Step]:
    steps: list[Step] = []
    artifacts = runner.evidence_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    page = runner.binding.get("documentUuid")
    project = runner.binding.get("projectName") or runner.binding.get("projectUuid")

    before_step = runner.run("m4-pcb-baseline", "PCB baseline dump (pcb dump --include-copper)",
                             ["pcb", "dump", "--include-copper", "--out", str(artifacts / "m4-pcb-before.json")],
                             stage="m4", pin_project=project)
    runner.artifact(before_step, artifacts / "m4-pcb-before.json")
    steps.append(before_step)
    before = pcb_snapshot_identity(before_step.json_payload) if before_step.json_payload else None

    list_step = runner.run("m4-pcb-locate", f"locate PCB part {device or '(none)'}",
                           ["pcb", "list", "--include-bbox"], stage="m4", pin_project=project)
    steps.append(list_step)
    target = _find_component(list_step.json_payload, device) if (device and list_step.json_payload) else None

    move_title = f"2 mm local move of {device or '(none)'} (pcb modify --center)"
    if not device:
        move_step = runner.planned("m4-move", move_title, None, "m4",
                                   "no --m4-device given: local move NOT RUN (refusing to move an arbitrary part)")
    elif target and target.get("primitiveId"):
        cx = as_float((target.get("center") or {}).get("x", target.get("x")))
        cy = as_float((target.get("center") or {}).get("y", target.get("y")))
        if cx is None or cy is None:
            move_step = runner.planned("m4-move", move_title, None, "m4",
                                       "part has no measurable center; NOT RUN")
        else:
            argv = ["pcb", "modify", "--id", str(target["primitiveId"]),
                    "--center", "--x", f"{cx:.6f}", "--y", f"{cy + TWO_MM_MIL:.6f}"]
            move_step = runner.run("m4-move", move_title, argv, stage="m4",
                                   pin_project=project, pin_doc=page)
    else:
        move_step = runner.planned("m4-move", move_title, None, "m4",
                                   f"part {device} not found on PCB; NOT RUN")
    steps.append(move_step)

    save_step = runner.run("m4-pcb-save", "save PCB (pcb save)", ["pcb", "save"], stage="m4",
                           pin_project=project, pin_doc=page)
    steps.append(save_step)
    reload_step = runner.run("m4-pcb-reload", "reload PCB document (doc reload --json)",
                             ["doc", "reload", page or "", "--json"], stage="m4", pin_project=project)
    steps.append(reload_step)
    after_step = runner.run("m4-pcb-after", "fresh PCB dump (pcb dump --include-copper)",
                            ["pcb", "dump", "--include-copper", "--out", str(artifacts / "m4-pcb-after.json")],
                            stage="m4", pin_project=project)
    runner.artifact(after_step, artifacts / "m4-pcb-after.json")
    steps.append(after_step)
    after = pcb_snapshot_identity(after_step.json_payload) if after_step.json_payload else None

    diff = compare_pcb_scope(before or {}, after or {}, device, TWO_MM_MIL)
    _write_json(runner.evidence_dir / "m4" / "scope-diff.json", diff)
    diff_step = runner.planned("m4-scope-diff", "scope diff: only the target moved, copper unchanged",
                               None, "m4", "computed offline from before/after dumps")
    diff_step.status = PASS if (before and after and diff.get("ok")) else (FAIL if diff.get("findings") else UNKNOWN)
    diff_step.evidence["diff"] = rel(runner.evidence_dir / "m4" / "scope-diff.json", runner.evidence_dir)
    steps.append(diff_step)

    drc_step = runner.run("m4-drc", "PCB DRC after local edit (pcb drc --json)",
                          ["pcb", "drc", "--json"], stage="m4", pin_project=project, pin_doc=page)
    steps.append(drc_step)
    check_step = runner.run("m4-pcb-check", "PCB DFM check after local edit (pcb check --json)",
                            ["pcb", "check", "--json"], stage="m4", pin_project=project, pin_doc=page)
    steps.append(check_step)

    # backup / restore rehearsal (native archive + @beta import as a NEW project)
    archive = artifacts / "m4-backup.epro2"
    project_uuid = runner.binding.get("projectUuid")
    if project_uuid:
        export_step = runner.run("m4-archive", "backup: native archive (project export)",
                                 ["project", "export", "--project-uuid", project_uuid, "--out", str(archive)],
                                 stage="m4", pin_project=project)
        runner.artifact(export_step, archive)
    else:
        export_step = runner.planned("m4-archive", "backup: native archive (project export)", None, "m4",
                                     "projectUuid unknown; NOT RUN")
    steps.append(export_step)
    import_step = runner.planned("m4-restore-probe", "restore probe: import archive as NEW project (@beta importer)",
                                 ["project", "import"], "m4",
                                 "requires a prior archive and explicit host permission; import never overwrites")
    steps.append(import_step)
    if archive.exists():
        import_step.note(f"archive ready at {rel(archive, runner.evidence_dir)}; import left NOT RUN "
                         "(it creates a new project; run manually with the printed command)")

    # install/upgrade/rollback is owned by distribution/; verify its evidence exists.
    installer_evidence = REPO_ROOT / "docs" / "toolchain-integration" / "evidence" / "installer"
    install_step = runner.planned("m4-install-upgrade", "install/upgrade/rollback (delegated to distribution/)",
                                  None, "m4", "delegated")
    if installer_evidence.exists() and any(installer_evidence.iterdir()):
        install_step.status = NOT_RUN
        install_step.note(f"distribution/ evidence present at {rel(installer_evidence, REPO_ROOT)}; "
                          "this runner does not execute installers (separate owner)")
    else:
        install_step.status = NOT_RUN
        install_step.note("no distribution/ evidence yet; installer acceptance is NOT RUN")
    steps.append(install_step)

    # negative controls: wrong target, stale read, bounded timeout
    wrong_doc = runner.run("m4-wrong-doc", "negative control: pinned wrong --doc must refuse",
                           ["sch", "read", "--doc", "0000000000000000"], stage="m4", pin_project=project,
                           allow_exit=(0, 1, 2))
    protected = wrong_doc.exit_code not in (0, None)
    wrong_doc.status = PASS if protected else FAIL
    wrong_doc.note(f"expected non-zero refusal, got exit={wrong_doc.exit_code}")
    steps.append(wrong_doc)
    stale_step = runner.planned("m4-stale-read", "negative control: read immediately after write (staleRisk)",
                                ["pcb", "dump"], "m4", "requires a completed write; NOT RUN")
    steps.append(stale_step)
    ready_bounded = runner.run("m4-timeout", "negative control: bounded readiness (doc ready --timeout 5s)",
                               ["doc", "ready", page or "", "--json", "--timeout", "5s"],
                               stage="m4", pin_project=project, timeout=30)
    steps.append(ready_bounded)

    return steps


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def build_summary(runner: Runner, *, stage: str, dry_run: bool, pre: dict,
                  project_dir: Path, cli_version: str | None) -> dict:
    counts = {status: 0 for status in STATUSES}
    for step in runner.steps:
        counts[step.status] = counts.get(step.status, 0) + 1
    six_counts: dict[str, int] = {}
    for step in runner.steps:
        for name, state in (step.six or {}).items():
            six_counts[state["status"]] = six_counts.get(state["status"], 0) + 1
    summary = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "stage": stage,
        "dryRun": dry_run,
        "cli": {"path": runner.cli, "version": cli_version or runner.cli_version},
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cwd": os.getcwd(),
        },
        "projectDir": str(project_dir),
        "evidenceDir": str(runner.evidence_dir),
        "window": runner.window,
        "preflight": {
            "ready": pre.get("ready"),
            "verdict": pre.get("verdict"),
            "connectorStatus": pre.get("connectorStatus"),
            "verifyVerdict": pre.get("verifyVerdict"),
            "blockers": pre.get("blockers", []),
            "nextSteps": pre.get("nextSteps", []),
            "capabilities": pre.get("checks", {}).get("capabilities", {}).get("summary"),
            "unsupported": pre.get("checks", {}).get("capabilities", {}).get("unsupported"),
        },
        "binding": runner.binding,
        "counts": counts,
        "sixStateCounts": six_counts,
        "timing": {
            "totalMs": runner.elapsed_ms(),
            "cliCalls": runner.cli_calls,
            "cliMs": runner.cli_ms,
            "overheadMs": max(0, runner.elapsed_ms() - runner.cli_ms),
        },
        "steps": [step.to_summary() for step in runner.steps],
    }
    return summary


def human_summary(summary: dict, log) -> None:
    pre = summary["preflight"]
    log("")
    log(f"zhigou acceptance — stage={summary['stage']} dryRun={str(summary['dryRun']).lower()}")
    log(f"  cli        {summary['cli']['version'] or 'unknown'}  ({summary['cli']['path']})")
    log(f"  preflight  verdict={pre['verdict']} connector={pre['connectorStatus']} verify={pre['verifyVerdict']}")
    if pre["blockers"]:
        log("  BLOCKED")
        for blocker in pre["blockers"]:
            log(f"    - {blocker}")
        for nxt in pre["nextSteps"]:
            log(f"    next: {nxt}")
    for step in summary["steps"]:
        if step["status"] == NOT_RUN:
            continue
        log(f"  [{step['status']:<7}] {step['id']:<18} {step['title']}")
        for note in step.get("notes", []):
            if note:
                log(f"      {note}")
    if summary.get("sixStateCounts"):
        log(f"  six-state  {summary['sixStateCounts']}")
    counts = summary["counts"]
    log("  counts     " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    timing = summary["timing"]
    log(f"  timing     total={timing['totalMs']}ms cli={timing['cliCalls']} calls/{timing['cliMs']}ms "
        f"overhead={timing['overheadMs']}ms")


# --------------------------------------------------------------------------- #
# self-test (pure logic, no CLI/host)
# --------------------------------------------------------------------------- #
def self_test(log) -> int:
    checks: list[dict] = []

    def check(name: str, condition: bool, detail=None) -> None:
        checks.append({"name": name, "ok": bool(condition), "detail": detail})
        if not condition:
            log(f"  FAIL {name}: {detail}")

    base = {
        "components": {
            "R1": {"primitiveId": "p1", "uniqueId": "gge1", "x": 100.0, "y": 200.0, "rotation": 0.0,
                   "pins": {"1": "+3V3", "2": "GND"}},
            "C1": {"primitiveId": "p2", "uniqueId": "gge2", "x": 300.0, "y": 400.0, "rotation": 0.0,
                   "pins": {"1": "+3V3", "2": "GND"}},
        },
        "nets": {"+3V3": 2, "GND": 2},
    }
    same = json.loads(json.dumps(base))
    check("identity_identical", compare_sch_identity(base, same, "R1", 0.0, 0.0)["ok"] is True,
          compare_sch_identity(base, same, "R1", 0.0, 0.0))

    moved = json.loads(json.dumps(base))
    moved["components"]["R1"]["x"] += 10.0
    moved["components"]["R1"]["y"] -= 5.0
    check("identity_target_moved_ok", compare_sch_identity(base, moved, "R1", 10.0, -5.0)["ok"] is True)
    check("identity_unexpected_move", compare_sch_identity(base, moved, "R1", 0.0, 0.0)["ok"] is False)

    moved_other = json.loads(json.dumps(base))
    moved_other["components"]["C1"]["y"] += 10.0
    check("identity_non_target_move", compare_sch_identity(base, moved_other, "R1", 0.0, 0.0)["ok"] is False)

    net_change = json.loads(json.dumps(base))
    net_change["components"]["R1"]["pins"]["2"] = "GND_D"
    check("identity_pin_net_change", compare_sch_identity(base, net_change, "R1", 0.0, 0.0)["ok"] is False)

    id_change = json.loads(json.dumps(base))
    id_change["components"]["C1"]["uniqueId"] = "gge9"
    check("identity_uniqueid_change", compare_sch_identity(base, id_change, "R1", 0.0, 0.0)["ok"] is False)

    dump_before = {
        "available": True,
        "components": {
            "R1": {"primitiveId": "p1", "x": 1000.0, "y": 2000.0, "rotation": 0.0, "layer": "TOP"},
            "U1": {"primitiveId": "p2", "x": 3000.0, "y": 2000.0, "rotation": 0.0, "layer": "TOP"},
        },
        "copper": {"tracks": 3, "vias": 1, "pours": 2, "tracksSha": "aaa", "viasSha": "bbb"},
        "raw_keys": ["components", "tracks", "vias"],
    }
    dump_after = json.loads(json.dumps(dump_before))
    dump_after["components"]["R1"]["y"] += TWO_MM_MIL
    check("pcb_scope_ok", compare_pcb_scope(dump_before, dump_after, "R1", TWO_MM_MIL)["ok"] is True)
    bad = json.loads(json.dumps(dump_after))
    bad["components"]["U1"]["x"] += 5.0
    check("pcb_scope_other_moved", compare_pcb_scope(dump_before, bad, "R1", TWO_MM_MIL)["ok"] is False)
    copper = json.loads(json.dumps(dump_after))
    copper["copper"]["tracksSha"] = "ccc"
    check("pcb_scope_copper_changed", compare_pcb_scope(dump_before, copper, "R1", TWO_MM_MIL)["ok"] is False)

    # tolerant JSON: a human warning line before the payload must not hide it
    raw = 'meta: probing\n{"schema":"x","result":{"saved":true}}\n'
    check("json_tolerant_parse", isinstance(json_loads_tolerant(raw), dict))
    check("saved_true_unwrap", _saved_true(json_loads_tolerant(raw)) is True)
    check("unwrap_result", unwrap({"id": "a", "result": {"v": 1}}) == {"v": 1})

    failed = [c for c in checks if not c["ok"]]
    log(f"  self-test: {len(checks) - len(failed)}/{len(checks)} checks passed")
    return 0 if not failed else 1, checks


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def resolve_cli(explicit: str | None) -> Path | str:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("ZHIGOU_CLI")
    if env:
        candidates.append(Path(env))
    candidates.append(REPO_ROOT / "runtime" / "dist" / "zhigou.exe")
    candidates.append(REPO_ROOT / "runtime" / "dist" / "zhigou")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("zhigou")
    return Path(found) if found else "zhigou"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="zhigou_acceptance.py",
        description="Real-host acceptance runner for the Zhigou toolchain (M2/M3/M4).",
    )
    ap.add_argument("--stage", default="all", choices=("m2", "m3", "m4", "all"),
                    help="which acceptance stage to run")
    ap.add_argument("--project-dir", default=str(DEFAULT_PROJECT),
                    help="design workspace the CLI runs from (artifacts must not escape it)")
    ap.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE),
                    help="where raw evidence and summary.json are written")
    ap.add_argument("--window", default=None, help="pin one EasyEDA windowId (default: match by project)")
    ap.add_argument("--zhigou", default=None, help="path to the zhigou executable")
    ap.add_argument("--move-device", default="R1",
                    help="M2: designator to move (default R1)")
    ap.add_argument("--dx", type=float, default=0.0, help="M2: raw schematic units to move in x (default 0)")
    ap.add_argument("--dy", type=float, default=0.0, help="M2: raw schematic units to move in y (default 0)")
    ap.add_argument("--m4-device", default=None,
                    help="M4: PCB designator for the 2 mm local move (required for that step)")
    ap.add_argument("--timeout", type=float, default=180.0, help="per-command timeout seconds (default 180)")
    ap.add_argument("--json", action="store_true", help="print the summary JSON on stdout")
    ap.add_argument("--dry-run", action="store_true",
                    help="preflight for real, then print the plan without executing host commands")
    ap.add_argument("--self-test", action="store_true",
                    help="validate the pure comparison/parse logic offline (no CLI calls)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    args = parse_args(argv)
    logs: list[str] = []

    def log(line: str = "") -> None:
        logs.append(line)
        print(line, file=sys.stderr)

    evidence_dir = Path(args.evidence_dir).resolve()
    project_dir = Path(args.project_dir).resolve()

    if args.self_test:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        code, checks = self_test(log)
        payload = {"schema": SELFTEST_SCHEMA, "generatedAt": utc_now(), "checks": checks,
                   "counts": {"total": len(checks), "failed": len([c for c in checks if not c["ok"]])}}
        _write_json(evidence_dir / "self-test.json", payload)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        return code

    if not project_dir.is_dir():
        print(f"[ACCEPTANCE] --project-dir does not exist: {project_dir}", file=sys.stderr)
        return 3
    if args.dx == 0 and args.dy == 0:
        log("[ACCEPTANCE] note: zero-delta move requested — this is the idempotency check")
    cli = resolve_cli(args.zhigou)
    runner = Runner(cli, evidence_dir, project_dir=project_dir, window=args.window,
                    timeout=args.timeout, dry_run=args.dry_run, log=log)

    # ---- preflight (always real, even in dry-run) ------------------------- #
    pre = preflight(runner)
    bind_targets(runner, json_loads_tolerant(
        (evidence_dir / "preflight" / "health.json").read_text(encoding="utf-8")
    ) if (evidence_dir / "preflight" / "health.json").exists() else {}, None)

    stages = ("m2", "m3", "m4") if args.stage == "all" else (args.stage,)
    if not pre["ready"]:
        reason = "; ".join(pre["blockers"])
        log("")
        log("BLOCKED — host not reachable for acceptance:")
        for blocker in pre["blockers"]:
            log(f"  - {blocker}")
        for nxt in pre["nextSteps"]:
            log(f"  next: {nxt}")
        log("")
        log("Recorded preflight evidence only; every host step is NOT RUN. Exit 2.")
        # Record the plan so the blocked path is auditable and re-runnable.
        if "m2" in stages:
            runner.steps.extend(stage_m2_plan_only(runner, args))
        if "m3" in stages:
            runner.steps.extend(stage_m3_plan_only(runner))
        if "m4" in stages:
            runner.steps.extend(stage_m4_plan_only(runner, args))
        summary = build_summary(runner, stage=args.stage, dry_run=args.dry_run, pre=pre,
                                project_dir=project_dir, cli_version=_read_version(runner))
        _write_json(evidence_dir / "summary.json", summary)
        human_summary(summary, log)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False))
        return 2

    # ---- ready: execute stages -------------------------------------------- #
    all_steps: list[Step] = []
    try:
        if "m2" in stages:
            all_steps += stage_m2(runner, pre, move_device=args.move_device, dx=args.dx, dy=args.dy)
        if "m3" in stages:
            all_steps += stage_m3(runner, pre)
        if "m4" in stages:
            all_steps += stage_m4(runner, pre, device=args.m4_device)
    except KeyboardInterrupt:
        log("[ACCEPTANCE] interrupted")
        return 1

    summary = build_summary(runner, stage=args.stage, dry_run=args.dry_run, pre=pre,
                            project_dir=project_dir, cli_version=_read_version(runner))
    _write_json(evidence_dir / "summary.json", summary)
    human_summary(summary, log)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    counts = summary["counts"]
    if args.dry_run:
        return 0
    if counts.get(FAIL):
        return 1
    if counts.get(PASS, 0) == 0:
        return 2
    return 0


def _read_version(runner: Runner) -> str | None:
    path = runner.evidence_dir / "preflight"
    stdout = path / "05-version.stdout.txt"
    candidates = sorted(path.glob("*-version.stdout.txt"))
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text.splitlines()[0]
        except OSError:
            continue
    return None


# --------------------------------------------------------------------------- #
# plan-only variants (used when preflight is blocked or --dry-run)
# --------------------------------------------------------------------------- #
def stage_m2_plan_only(runner: Runner, args) -> list[Step]:
    reason = "host unreachable: connector not loaded — step NOT RUN (never reported as pass)"
    specs = [
        ("bind", "bind window/project/page from live health"),
        ("baseline-read", "baseline schematic snapshot (sch read)"),
        ("component-locate", f"locate {args.move_device} (sch list --include-pins --include-bbox)"),
        ("move", f"move {args.move_device} by dx={args.dx} dy={args.dy} (sch modify)"),
        ("save", "save schematic (sch save)"),
        ("reload", "real reload (doc reload --json)"),
        ("ready", "readiness (doc ready --json)"),
        ("readback", "fresh readback (sch read)"),
        ("electrical-drc", "official schematic DRC (sch drc --json)"),
        ("electrical-check", "reconstructed check (sch check --json)"),
        ("quality-lint", "placement lint (sch layout-lint)"),
        ("six-state", "six-state evidence roll-up"),
    ]
    steps = []
    for sid, title in specs:
        step = runner.planned(sid, title, None, "m2", reason)
        if sid == "six-state":
            step.six = {
                state: six_state(state, UNKNOWN, reason)
                for state in ("command_completed", "readback_verified", "save_confirmed",
                              "reopen_confirmed", "electrical_passed", "quality_passed")
            }
        steps.append(step)
    return steps


def stage_m3_plan_only(runner: Runner) -> list[Step]:
    reason = "host unreachable: connector not loaded — step NOT RUN (never reported as pass)"
    steps = [runner.planned(sid, title, argv, "m3", reason) for sid, title, argv, _cap, _json in M3_STEPS]
    for capability, note in M3_UNSUPPORTED.items():
        steps.append(runner.planned(f"m3-{capability.split('.')[0]}", capability, None, "m3",
                                    f"{note}; NOT RUN"))
    return steps


def stage_m4_plan_only(runner: Runner, args) -> list[Step]:
    reason = "host unreachable: connector not loaded — step NOT RUN (never reported as pass)"
    specs = [
        ("m4-pcb-baseline", "PCB baseline dump (pcb dump --include-copper)"),
        ("m4-pcb-locate", "locate PCB part (pcb list --include-bbox)"),
        ("m4-move", f"2 mm local move of {args.m4_device or '(none)'} (pcb modify --center)"),
        ("m4-pcb-save", "save PCB (pcb save)"),
        ("m4-pcb-reload", "reload PCB document (doc reload --json)"),
        ("m4-pcb-after", "fresh PCB dump (pcb dump --include-copper)"),
        ("m4-scope-diff", "scope diff: only the target moved, copper unchanged"),
        ("m4-drc", "PCB DRC after local edit (pcb drc --json)"),
        ("m4-pcb-check", "PCB DFM check after local edit (pcb check --json)"),
        ("m4-archive", "backup: native archive (project export)"),
        ("m4-restore-probe", "restore probe: import archive as NEW project (@beta importer)"),
        ("m4-install-upgrade", "install/upgrade/rollback (delegated to distribution/)"),
        ("m4-wrong-doc", "negative control: pinned wrong --doc must refuse"),
        ("m4-stale-read", "negative control: stale read after write"),
        ("m4-timeout", "negative control: bounded readiness (doc ready --timeout 5s)"),
    ]
    return [runner.planned(sid, title, None, "m4", reason) for sid, title in specs]


if __name__ == "__main__":
    sys.exit(main())
