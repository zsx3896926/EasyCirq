"""Authorization-gated write probe: W04 (schematic write), W05 (PCB write),
W09 (save -> close -> reopen -> readback).

Safety model (task book section 4, made executable here):

* The script refuses to run without a JSON authorization file created by the
  operator (``zhigou.a2-coverage.write-authorization/v1``) whose scope includes
  W04/W05/W09 and whose ``project_root`` is under the system temp directory.
* The source project is only **read**; a fresh copy is made inside
  ``<project_root>/run-<timestamp>/`` and all writes target that copy.
* Only ``origin:"cli"`` sessions opened by this script are driven; sessions are
  closed with ``--destroy`` at the end.  User sessions are recorded before/after
  and never touched.
* The ``write-probe-passed.json`` marker is written **only** if every check
  passes; the A2 retire PR (Step 3) is gated on that marker.

Usage::

    python spike/a2-coverage/probe_writes.py --dry-run \
        --authorization docs/evidence/a2-coverage-2026-10-28/write-probe/authorization.json \
        --fixture %TEMP%\\a2-spike-20261028-1050\\fixture\\a2spike-quickstart.eprj2

    python spike/a2-coverage/probe_writes.py \
        --authorization ... --fixture ...

Exit codes: 0 pass, 2 authorization/input refused, 3 environment refused,
4 probe ran but one or more checks failed (evidence kept).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import official_cli  # noqa: E402
from common import (  # noqa: E402
    enable_utf8_stdout,
    now_iso,
    sha256_file,
    tree_diff,
    tree_snapshot,
    write_json,
    write_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence"
AUTH_SCHEMA = "zhigou.a2-coverage.write-authorization/v1"
RUN_SCHEMA = "zhigou.a2-coverage.write-probe/v1"
MARKER_SCHEMA = "zhigou.a2-coverage.write-probe-passed/v1"
REQUIRED_SCOPE = ("W04", "W05", "W09")
NET = "A2PROBE_NET"
VCC = "A2PROBE_VCC"
DEVICE_X = 200
DEVICE_Y = 600

# ---------------------------------------------------------------------------
# JS snippets
# ---------------------------------------------------------------------------

_JS_COMMON = r"""
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function waitProject(timeoutMs) {
  const t0 = Date.now();
  let proj = null;
  while (Date.now() - t0 < timeoutMs) {
    proj = await eda.dmt_Project.getCurrentProjectInfo();
    if (proj && proj.data && proj.data.length) return proj;
    await sleep(500);
  }
  return proj;
}
async function activateSchematic(proj) {
  const board = proj.data[0];
  const page = board.schematic && board.schematic.page && board.schematic.page[0];
  if (!page) return { page: null, tabId: null };
  const tabId = await eda.dmt_EditorControl.openDocument(page.uuid);
  const activated = await eda.dmt_EditorControl.activateDocument(tabId);
  const t0 = Date.now();
  while (Date.now() - t0 < 45000) {
    const comps = await eda.sch_PrimitiveComponent.getAll(undefined, true);
    if (comps && comps.length) break;
    await sleep(500);
  }
  return { page: {uuid: page.uuid, name: page.name}, tabId, activated };
}
"""

JS_W04 = _JS_COMMON + r"""
const proj = await waitProject(120000);
if (!proj || !proj.data || !proj.data.length) return {fatal: 'project not loaded'};
const sch = await activateSchematic(proj);
const beforeComps = await eda.sch_PrimitiveComponent.getAll(undefined, true);
const beforeWires = await eda.sch_PrimitiveWire.getAll();
let libs = {};
try { libs.project = await eda.lib_LibrariesList.getProjectLibraryUuid() || null; } catch (e) { libs.projectErr = String(e); }
try { libs.system = await eda.lib_LibrariesList.getSystemLibraryUuid() || null; } catch (e) { libs.systemErr = String(e); }
let search = null, searchErr = null;
try { search = await eda.lib_Device.search('0402', libs.system || libs.project || undefined); } catch (e) { searchErr = String(e); }
const candidates = Array.isArray(search) ? search.slice(0, 3) : [];
let createRes = null, createErr = null, chosen = null;
for (const cand of candidates) {
  try {
    const created = await eda.sch_PrimitiveComponent.create(cand, 200, 600, undefined, 0, false, true, true);
    if (created) { createRes = created; chosen = {uuid: cand.uuid, name: cand.name, libraryUuid: cand.libraryUuid}; break; }
  } catch (e) { createErr = String(e); }
}
await sleep(1500);
let pins = null, pinErr = null;
try {
  const pid = createRes && (createRes.primitiveId || createRes.id);
  if (pid) pins = await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(pid);
} catch (e) { pinErr = String(e); }
const p0 = (pins && pins.length) ? pins[0] : null;
const wx1 = p0 ? p0.x : 220;
const wy1 = p0 ? p0.y : 600;
let wire = null, wireErr = null;
try { wire = await eda.sch_PrimitiveWire.create([wx1, wy1, wx1 + 40, wy1], 'A2PROBE_NET'); } catch (e) { wireErr = String(e); }
let label = null, labelErr = null;
try { label = await eda.sch_PrimitiveAttribute.createNetLabel(wx1 + 40, wy1, 'A2PROBE_NET'); } catch (e) { labelErr = String(e); }
let flag = null, flagErr = null;
try { flag = await eda.sch_PrimitiveComponent.createNetFlag('Power', 'A2PROBE_VCC', 200, 540); } catch (e) { flagErr = String(e); }
await sleep(1500);
const afterComps = await eda.sch_PrimitiveComponent.getAll(undefined, true);
const afterWires = await eda.sch_PrimitiveWire.getAll();
let saveRes = null, saveErr = null;
try { saveRes = await eda.sch_Document.save(); } catch (e) { saveErr = String(e); }
await sleep(1500);
const lastComps = await eda.sch_PrimitiveComponent.getAll(undefined, true);
const lastWires = await eda.sch_PrimitiveWire.getAll();
const newComp = createRes && lastComps ? lastComps.find(c => (c.primitiveId || c.id) === (createRes.primitiveId || createRes.id)) : null;
return {
  page: sch.page, activated: sch.activated,
  libs, candidateCount: candidates.length, searchErr,
  chosen, createRes: createRes ? {primitiveId: createRes.primitiveId, designator: createRes.designator, name: createRes.name, x: createRes.x, y: createRes.y} : null,
  createErr, pins: pins ? pins.length : null, pinErr,
  wire: wire ? {primitiveId: wire.primitiveId, net: wire.net} : null, wireErr,
  label: label ? {primitiveId: label.primitiveId} : null, labelErr,
  flag: flag ? {primitiveId: flag.primitiveId, name: flag.name} : null, flagErr,
  before: {components: (beforeComps || []).length, wires: (beforeWires || []).length},
  afterSave: {components: (lastComps || []).length, wires: (lastWires || []).length,
              newComponentFound: !!newComp,
              flagSample: (lastComps || []).filter(c => String(c.name || '').indexOf('A2PROBE') >= 0).map(c => ({name: c.name, x: c.x, y: c.y}))},
  saveRes, saveErr
};
"""

JS_W05 = _JS_COMMON + r"""
const proj = await waitProject(120000);
if (!proj || !proj.data || !proj.data.length) return {fatal: 'project not loaded'};
const board = proj.data[0];
const sch = await activateSchematic(proj);
await sleep(800);
let importRes = null, importErr = null;
try { importRes = await eda.sch_Document.importChanges(false); } catch (e) { importErr = String(e); }
await sleep(3000);
const pcb = board.pcb;
if (!pcb) return {fatal: 'project has no PCB'};
const pcbTab = await eda.dmt_EditorControl.openDocument(pcb.uuid);
const pcbActivated = await eda.dmt_EditorControl.activateDocument(pcbTab);
const t0 = Date.now();
let comps = [];
while (Date.now() - t0 < 60000) {
  comps = await eda.pcb_PrimitiveComponent.getAll();
  if (comps && comps.length) break;
  await sleep(500);
}
const designatorOf = (c) => c && (c.designator || c.name || null);
const target = (comps || []).find(c => designatorOf(c) && designatorOf(c) !== '?') || null;
let expected = null, moveRes = null, moveErr = null;
if (target) {
  expected = {designator: designatorOf(target), x: (target.x || 0) + 50, y: (target.y || 0) + 50};
  try { moveRes = await eda.pcb_PrimitiveComponent.modify(target.primitiveId, {x: expected.x, y: expected.y}); } catch (e) { moveErr = String(e); }
}
await sleep(1200);
const after = await eda.pcb_PrimitiveComponent.getAll();
const found = expected ? (after || []).find(c => designatorOf(c) === expected.designator) : null;
let saveRes = null, saveErr = null;
try { saveRes = await eda.pcb_Document.save(); } catch (e) { saveErr = String(e); }
await sleep(1500);
const last = await eda.pcb_PrimitiveComponent.getAll();
const lastFound = expected ? (last || []).find(c => designatorOf(c) === expected.designator) : null;
return {
  schematicActivated: sch.activated, importRes, importErr,
  pcbActivated, componentCount: (comps || []).length,
  target: target ? {primitiveId: target.primitiveId, designator: designatorOf(target), x: target.x, y: target.y, rotation: target.rotation} : null,
  expected,
  moveRes: moveRes ? {x: moveRes.x, y: moveRes.y} : null, moveErr,
  found: found ? {designator: designatorOf(found), x: found.x, y: found.y} : null,
  lastFound: lastFound ? {designator: designatorOf(lastFound), x: lastFound.x, y: lastFound.y} : null,
  saveRes, saveErr
};
"""

JS_W09 = _JS_COMMON + r"""
const args = (typeof __CLI__ !== 'undefined' && __CLI__.args) ? __CLI__.args : {};
const proj = await waitProject(120000);
if (!proj || !proj.data || !proj.data.length) return {fatal: 'project not loaded'};
const board = proj.data[0];
const sch = await activateSchematic(proj);
const comps = await eda.sch_PrimitiveComponent.getAll(undefined, true) || [];
const wires = await eda.sch_PrimitiveWire.getAll() || [];
const text = (v) => JSON.stringify(v === undefined ? null : v);
const flagFound = comps.some(c => c && (text(c).indexOf(args.vcc || 'A2PROBE_VCC') >= 0));
const wireFound = wires.some(w => text(w).indexOf(args.net || 'A2PROBE_NET') >= 0);
const devFound = comps.some(c => c && Math.abs((c.x || 0) - (args.deviceX || 200)) <= 80 && Math.abs((c.y || 0) - (args.deviceY || 600)) <= 80);
const pcb = board.pcb;
let pcbResult = null;
if (pcb) {
  const pcbTab = await eda.dmt_EditorControl.openDocument(pcb.uuid);
  await eda.dmt_EditorControl.activateDocument(pcbTab);
  const t0 = Date.now();
  let pcbs = [];
  while (Date.now() - t0 < 60000) {
    pcbs = await eda.pcb_PrimitiveComponent.getAll();
    if (pcbs && pcbs.length) break;
    await sleep(500);
  }
  const designatorOf = (c) => c && (c.designator || c.name || null);
  const found = pcbs.find(c => designatorOf(c) === args.pcbDesignator);
  pcbResult = {componentCount: pcbs.length, designator: args.pcbDesignator,
               found: found ? {designator: designatorOf(found), x: found.x, y: found.y} : null};
}
return {projectUuid: proj.uuid, flagFound, wireFound, devFound,
        componentCount: comps.length, wireCount: wires.length, pcb: pcbResult};
"""


# ---------------------------------------------------------------------------
# authorization
# ---------------------------------------------------------------------------


def validate_authorization(auth_path: Path, fixture: Path) -> tuple[dict, list]:
    problems: list[str] = []
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"cannot read authorization JSON: {exc}"]
    if data.get("schema") != AUTH_SCHEMA:
        problems.append(f"schema must be {AUTH_SCHEMA}")
    if not str(data.get("granted_by") or "").strip():
        problems.append("granted_by is required (who granted the write authorization)")
    scope = set(data.get("scope") or [])
    if not set(REQUIRED_SCOPE) <= scope:
        problems.append(f"scope must include {list(REQUIRED_SCOPE)}")
    temp_root = Path(tempfile.gettempdir()).resolve()
    project_root = Path(str(data.get("project_root") or "")).resolve()
    if temp_root not in project_root.parents and project_root != temp_root:
        problems.append("project_root must be under the system temp directory")
    stated_fixture = Path(str(data.get("fixture_source") or "")).resolve()
    if stated_fixture != fixture:
        problems.append("fixture_source in the authorization does not match --fixture")
    if temp_root not in fixture.parents:
        problems.append("--fixture must live under the system temp directory")
    expires = data.get("expires_at")
    if expires:
        try:
            when = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        except ValueError:
            problems.append("expires_at is not ISO-8601")
        else:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when < datetime.now(timezone.utc):
                problems.append("authorization has expired")
    return data, problems


def _sessions_snapshot(payload) -> dict:
    origins = official_cli.sessions_by_origin(payload)
    return {
        "user": [s.get("sessionId") for s in origins.get("user", [])],
        "cli": [s.get("sessionId") for s in origins.get("cli", [])],
        "raw": payload,
    }


# ---------------------------------------------------------------------------
# probe driver
# ---------------------------------------------------------------------------


class WriteProbe:
    def __init__(self, exe: str, copy: Path, evidence_dir: Path, authorization: dict):
        self.exe = exe
        self.copy = copy
        self.evidence = evidence_dir
        self.auth = authorization
        self.raw_dir = evidence_dir / "write-probe" / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.session_id: str | None = None
        self.receipt: dict = {
            "schema": RUN_SCHEMA,
            "started_at": now_iso(),
            "authorization": {
                "granted_by": authorization.get("granted_by"),
                "granted_at": authorization.get("granted_at"),
                "scope": authorization.get("scope"),
                "project_root": authorization.get("project_root"),
                "authorization_file_sha256": sha256_file(
                    evidence_dir / "write-probe" / "authorization.json"
                ),
            },
            "fixture": {"source_sha256": None, "copy": str(copy), "copy_sha256_before": None},
            "steps": [],
        }

    def _save(self, name: str, result: official_cli.CliResult, keep_json: bool = True) -> None:
        if result.stdout:
            write_text(self.raw_dir / f"{name}.stdout.json", result.stdout)
        if result.stderr:
            write_text(self.raw_dir / f"{name}.stderr.txt", result.stderr)
        self.receipt["steps"].append(
            {
                "name": name,
                "argv": result.argv,
                "exit_code": result.exit_code,
                "duration_ms": round(result.duration_ms, 1),
                "json_ok": result.json is not None,
                "stdout_file": f"docs/evidence/{self.evidence.name}/write-probe/raw/{name}.stdout.json",
            }
        )

    def _invoke(self, name: str, code: str, args: dict | None = None, timeout_ms: int = 180000):
        assert self.session_id, "no session"
        if args is None:
            result = official_cli.invoke(self.exe, self.session_id, code, timeout_ms=timeout_ms)
        else:
            result = official_cli.run(
                self.exe,
                [
                    "invoke",
                    "--session",
                    self.session_id,
                    "--code",
                    code,
                    "--args",
                    json.dumps(args),
                    "--timeout",
                    str(timeout_ms),
                ],
                timeout_s=timeout_ms / 1000.0 + 120,
            )
        self._save(name, result)
        value = result.json.get("value") if isinstance(result.json, dict) else None
        return result, value

    def open(self) -> None:
        opened = official_cli.open_project(self.exe, str(self.copy), headless=True)
        self._save("W00-open", opened)
        self.session_id = official_cli.session_id_from_open(opened)
        if not self.session_id:
            raise RuntimeError("open did not return a sessionId")
        listing = official_cli.session_list(self.exe)
        self._save("W00-sessions-after-open", listing)
        ours = [s for s in official_cli.sessions_by_origin(listing.json).get("cli", []) if s.get("sessionId") == self.session_id]
        if not ours:
            raise RuntimeError("our session is not visible as origin=cli")

    def close(self, label: str) -> None:
        if not self.session_id:
            return
        closed = official_cli.close_session(self.exe, self.session_id, destroy=True)
        self._save(label, closed)
        self.session_id = None
        time.sleep(1.0)

    def run(self) -> dict:
        before_tree = tree_snapshot(self.copy)
        self.receipt["fixture"]["copy_sha256_before"] = sha256_file(self.copy)
        self.open()
        try:
            _, w04 = self._invoke("W04-sch-write", JS_W04, timeout_ms=240000)
            _, w05 = self._invoke("W05-pcb-write", JS_W05, timeout_ms=300000)
            self.close("W09-close")
            after_write_tree = tree_snapshot(self.copy)
            self.receipt["fixture"]["copy_sha256_after_write"] = sha256_file(self.copy)

            reopened = official_cli.open_project(self.exe, str(self.copy), headless=True)
            self._save("W09-reopen", reopened)
            self.session_id = official_cli.session_id_from_open(reopened)
            if not self.session_id:
                raise RuntimeError("reopen did not return a sessionId")
            _, w09 = self._invoke(
                "W09-readback",
                JS_W09,
                args={
                    "net": NET,
                    "vcc": VCC,
                    "deviceX": DEVICE_X,
                    "deviceY": DEVICE_Y,
                    "pcbDesignator": (w05 or {}).get("expected", {}).get("designator") if w05 else None,
                },
                timeout_ms=180000,
            )
        finally:
            self.close("W99-close")
        after_tree = tree_snapshot(self.copy)
        self.receipt["fixture"]["copy_sha256_after"] = sha256_file(self.copy)
        self.receipt["fixture"]["tree_diff"] = tree_diff(before_tree, after_tree)

        checks = evaluate(w04, w05, w09, self.receipt["fixture"])
        self.receipt["checks"] = checks
        self.receipt["w04"] = w04
        self.receipt["w05"] = w05
        self.receipt["w09"] = w09
        self.receipt["finished_at"] = now_iso()
        write_json(self.evidence / "write-probe" / "write-probe-run.json", self.receipt)
        write_json(self.evidence / "write-probe" / "project-before.json", before_tree)
        write_json(self.evidence / "write-probe" / "project-after.json", after_tree)
        return self.receipt


def evaluate(w04: dict | None, w05: dict | None, w09: dict | None, fixture_info: dict) -> dict:
    w04 = w04 or {}
    w05 = w05 or {}
    w09 = w09 or {}
    after_save = w04.get("afterSave") or {}
    last_found = w05.get("lastFound") or {}
    expected = w05.get("expected") or {}
    pcb_found = (w09.get("pcb") or {}).get("found") or {}
    pose_ok = False
    if expected and pcb_found and last_found:
        pose_ok = (
            abs(float(pcb_found.get("x", 0)) - float(expected.get("x", 0))) <= 2
            and abs(float(pcb_found.get("y", 0)) - float(expected.get("y", 0))) <= 2
        )
    hash_changed = fixture_info.get("copy_sha256_before") != fixture_info.get("copy_sha256_after")
    checks = {
        "W04": {
            "device_created": bool(w04.get("chosen")) and bool(w04.get("createRes")),
            "wire_created": bool(w04.get("wire")),
            "net_label_created": bool(w04.get("label")),
            "save_true": w04.get("saveRes") is True,
            "readback_component_found": bool(after_save.get("newComponentFound")),
            "readback_counts_increased": (after_save.get("components", 0) > (w04.get("before") or {}).get("components", 0)),
        },
        "W05": {
            "import_changes_returned": w05.get("importRes") is True,
            "component_moved": bool(w05.get("lastFound")) and bool(expected),
            "move_delta_ok": bool(last_found) and pose_ok is not None and (
                abs(float(last_found.get("x", 0)) - float(expected.get("x", 0))) <= 2
                and abs(float(last_found.get("y", 0)) - float(expected.get("y", 0))) <= 2
            ),
            "save_true": w05.get("saveRes") is True,
        },
        "W09": {
            "net_flag_persisted": bool(w09.get("flagFound")),
            "wire_persisted": bool(w09.get("wireFound")),
            "device_persisted": bool(w09.get("devFound")),
            "pcb_pose_persisted": bool(pose_ok),
            "project_file_changed": bool(hash_changed),
        },
    }
    checks["passed"] = {
        "W04": all(checks["W04"].values()),
        "W05": all(checks["W05"].values()),
        "W09": all(checks["W09"].values()),
    }
    checks["all_passed"] = all(checks["passed"].values())
    return checks


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--authorization", required=True, help="path to the operator authorization JSON")
    parser.add_argument("--fixture", required=True, help="read-only source project under the system temp dir")
    parser.add_argument("--evidence-date", default="2026-10-28")
    parser.add_argument("--exe", default=None)
    parser.add_argument("--dry-run", action="store_true", help="validate authorization and print the plan only")
    args = parser.parse_args(argv)

    fixture = Path(args.fixture).resolve()
    auth_path = Path(args.authorization).resolve()
    if not auth_path.is_file():
        print(f"REFUSED: authorization file not found: {auth_path}", file=sys.stderr)
        return 2
    auth, problems = validate_authorization(auth_path, fixture)
    if problems:
        print("REFUSED: authorization is not valid:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    if not fixture.is_file():
        print(f"REFUSED: fixture not found: {fixture}", file=sys.stderr)
        return 2

    evidence = EVIDENCE_ROOT / f"a2-coverage-{args.evidence_date}"
    marker = evidence / "write-probe-passed.json"
    print("authorized by:", auth.get("granted_by"))
    print("scope:", auth.get("scope"))
    print("fixture:", fixture)
    print("project_root:", auth.get("project_root"))
    print("evidence:", evidence)
    print("writes: W04 schematic (device/wire/net label/net flag) -> W05 PCB (importChanges/move/save) -> W09 save/reopen readback")
    if args.dry_run:
        print("dry-run: authorization valid; no EDA started")
        print("marker would be:", marker)
        return 0

    try:
        exe = official_cli.find_exe(args.exe)
    except FileNotFoundError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    doctor = official_cli.doctor(exe)
    if not (doctor.json or {}).get("ok"):
        print("REFUSED: lceda-pro doctor failed; EDA endpoint not reachable", file=sys.stderr)
        return 3

    project_root = Path(auth["project_root"]).resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    run_dir = project_root / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=False)
    copy = run_dir / f"a2write-{run_dir.name}.eprj2"
    shutil.copy2(fixture, copy)
    source_hash_before = sha256_file(fixture)

    evidence.mkdir(parents=True, exist_ok=True)
    write_json(evidence / "write-probe" / "authorization.json", auth)
    sessions_before = official_cli.session_list(exe)
    write_json(evidence / "write-probe" / "sessions-before.json", sessions_before.json)

    probe = WriteProbe(exe, copy, evidence, auth)
    probe.receipt["fixture"]["source_sha256"] = source_hash_before
    print("copy:", copy)
    try:
        receipt = probe.run()
    finally:
        source_hash_after = sha256_file(fixture)
    receipt["fixture"]["source_sha256_after"] = source_hash_after
    receipt["fixture"]["source_unchanged"] = source_hash_after == source_hash_before
    sessions_after = official_cli.session_list(exe)
    write_json(evidence / "write-probe" / "sessions-after.json", sessions_after.json)
    receipt["sessions"] = {
        "before": _sessions_snapshot(sessions_before.json),
        "after": _sessions_snapshot(sessions_after.json),
    }
    write_json(evidence / "write-probe" / "write-probe-run.json", receipt)

    checks = receipt["checks"]
    print("checks:")
    for workflow in REQUIRED_SCOPE:
        print(f"  {workflow}: {checks['passed'][workflow]} {checks[workflow]}")
    if checks["all_passed"]:
        write_json(
            marker,
            {
                "schema": MARKER_SCHEMA,
                "generated_at": now_iso(),
                "authorization": receipt["authorization"],
                "scope": list(REQUIRED_SCOPE),
                "checks": checks,
                "evidence": [
                    "docs/evidence/{}/write-probe/write-probe-run.json".format(evidence.name),
                    "docs/evidence/{}/write-probe/authorization.json".format(evidence.name),
                ],
                "temp_project": str(copy),
                "cleanup": f"delete {run_dir} after review",
            },
        )
        print("PASS: W04/W05/W09 covered; marker ->", marker)
        return 0
    print("FAIL: probe ran but checks failed; evidence kept, no marker written", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
