"""Operator-driven read-only probe of the official EasyEDA Pro CLI.

Isolation rules enforced here (task book section 4):
  * only a *copy* of a fixture project under the system temp directory is opened;
  * only sessions opened by this script (``origin:"cli"``) are driven;
  * the user's own editor window is never activated, reloaded or closed;
  * no design content is written: this script only reads, checks, exports and
    reopens.  Write probes (W04/W05/W09-save) require explicit authorization and
    are deliberately absent.

Run:
  python spike/a2-coverage/probe_official.py --evidence-date 2026-10-28 --fixture <copy>
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import official_cli  # noqa: E402
from common import (  # noqa: E402
    enable_utf8_stdout,
    now_iso,
    sha256_bytes,
    sha256_file,
    tree_diff,
    tree_snapshot,
    write_json,
    write_text,
)

# ---------------------------------------------------------------------------
# JS snippets (embedded, so each receipt is reproducible from this file)
# ---------------------------------------------------------------------------

JS_WAIT_PROJECT = r"""
const t0 = Date.now();
let proj = null;
while (Date.now() - t0 < 120000) {
  proj = await eda.dmt_Project.getCurrentProjectInfo();
  const boards = proj && proj.data ? proj.data : [];
  if (boards.length > 0) break;
  await new Promise(r => setTimeout(r, 500));
}
const boards = proj && proj.data ? proj.data : [];
let readyState = null, readyErr = null;
try { readyState = await eda.dmt_Project.getReadyState(); } catch (e) { readyErr = String(e); }
return {
  elapsedMs: Date.now() - t0,
  boardCount: boards.length,
  readyState, readyErr,
  projectUuid: proj ? proj.uuid : null,
  projectFriendlyName: proj ? proj.friendlyName : null
};
"""

JS_ACTIVATE_SCH = r"""
const t0 = Date.now();
let proj = null;
while (Date.now() - t0 < 60000) {
  proj = await eda.dmt_Project.getCurrentProjectInfo();
  if (proj && proj.data && proj.data.length) break;
  await new Promise(r => setTimeout(r, 500));
}
const board = (proj && proj.data && proj.data.length) ? proj.data[0] : null;
const sch = board && board.schematic ? board.schematic : null;
const page = sch && sch.page && sch.page.length ? sch.page[0] : null;
let tabId = null, activated = false, err = null, waitMs = Date.now() - t0;
try {
  if (page) {
    tabId = await eda.dmt_EditorControl.openDocument(page.uuid);
    activated = await eda.dmt_EditorControl.activateDocument(tabId);
    const t1 = Date.now();
    while (Date.now() - t1 < 45000) {
      const comps = await eda.sch_PrimitiveComponent.getAll(undefined, true);
      if (comps && comps.length) break;
      await new Promise(r => setTimeout(r, 500));
    }
    waitMs = Date.now() - t0;
  }
} catch (e) { err = String(e); }
return {page: page ? {uuid: page.uuid, name: page.name} : null,
        schematic: sch ? {uuid: sch.uuid, name: sch.name, pageCount: (sch.page || []).length} : null,
        tabId, activated, waitMs, err};
"""

JS_ACTIVATE_PCB = r"""
const t0 = Date.now();
let proj = null;
while (Date.now() - t0 < 60000) {
  proj = await eda.dmt_Project.getCurrentProjectInfo();
  if (proj && proj.data && proj.data.length) break;
  await new Promise(r => setTimeout(r, 500));
}
const board = (proj && proj.data && proj.data.length) ? proj.data[0] : null;
const pcb = board && board.pcb ? board.pcb : null;
let tabId = null, activated = false, err = null;
try {
  if (pcb) {
    tabId = await eda.dmt_EditorControl.openDocument(pcb.uuid);
    activated = await eda.dmt_EditorControl.activateDocument(tabId);
  }
} catch (e) { err = String(e); }
return {pcb: pcb ? {uuid: pcb.uuid, name: pcb.name} : null, tabId, activated, err};
"""

JS_PROJECT_TREE = r"""
const proj = await eda.dmt_Project.getCurrentProjectInfo();
const boards = (proj && proj.data) ? proj.data : [];
return {
  project: proj ? {uuid: proj.uuid, friendlyName: proj.friendlyName, name: proj.name, teamUuid: proj.teamUuid} : null,
  boards: boards.map(b => ({
    name: b.name,
    boardType: b.itemType,
    schematic: b.schematic ? {uuid: b.schematic.uuid, name: b.schematic.name,
      pages: (b.schematic.page || []).map(p => ({uuid: p.uuid, name: p.name}))} : null,
    pcb: b.pcb ? {uuid: b.pcb.uuid, name: b.pcb.name} : null
  }))
};
"""

JS_READ_SCH = r"""
function firstBoard(proj) { return (proj && proj.data && proj.data.length) ? proj.data[0] : null; }
const proj = await eda.dmt_Project.getCurrentProjectInfo();
const board = firstBoard(proj);
const sch = board && board.schematic ? board.schematic : null;
const page = sch && sch.page && sch.page.length ? sch.page[0] : null;
let docHandle = null, activated = false, readyByUuid = null, readyByTab = null, openErr = null;
if (page) {
  try {
    docHandle = await eda.dmt_EditorControl.openDocument(page.uuid);
    activated = await eda.dmt_EditorControl.activateDocument(docHandle);
    readyByUuid = await eda.dmt_EditorControl.waitForDocumentReady(page.uuid, 10000);
    readyByTab = await eda.dmt_EditorControl.waitForDocumentReady(docHandle, 10000);
  } catch (e) { openErr = String(e); }
}
let components = null, compErr = null;
try { components = await eda.sch_PrimitiveComponent.getAll(undefined, true); } catch (e) { compErr = String(e); }
let nets = null, netErr = null;
try { nets = await eda.sch_Net.getAllNets(); } catch (e) { netErr = String(e); }
let wires = null, wireErr = null;
try { wires = await eda.sch_PrimitiveWire.getAll(); } catch (e) { wireErr = String(e); }
let pins = null, pinErr = null;
try {
  const comp = (components || [])[0];
  if (comp) {
    const id = comp.primitiveId || comp.id || comp.uuid;
    pins = await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id);
  }
} catch (e) { pinErr = String(e); }
const compCompact = (components || []).map(c => ({
  primitiveId: c.primitiveId, designator: c.designator, name: c.name,
  component: c.component, symbol: c.symbol, footprint: c.footprint,
  x: c.x, y: c.y, rotation: c.rotation, mirror: c.mirror,
  addIntoBom: c.addIntoBom, addIntoPcb: c.addIntoPcb, supplierId: c.supplierId
}));
return {
  page: page ? {uuid: page.uuid, name: page.name} : null,
  docHandle, activated, readyByUuid, readyByTab, openErr,
  componentCount: (components || []).length, compErr,
  netCount: (nets || []).length, netErr,
  wireCount: (wires || []).length, wireErr,
  pinCount: (pins || []).length, pinErr,
  components: compCompact,
  nets,
  wires,
  pins
};
"""

JS_READ_PCB = r"""
function firstBoard(proj) { return (proj && proj.data && proj.data.length) ? proj.data[0] : null; }
const proj = await eda.dmt_Project.getCurrentProjectInfo();
const board = firstBoard(proj);
const pcb = board && board.pcb ? board.pcb : null;
let docHandle = null, activated = false, ready = null, openErr = null;
if (pcb) {
  try {
    docHandle = await eda.dmt_EditorControl.openDocument(pcb.uuid);
    activated = await eda.dmt_EditorControl.activateDocument(docHandle);
    ready = await eda.dmt_EditorControl.waitForDocumentReady(docHandle, 15000);
  } catch (e) { openErr = String(e); }
}
let pcbs = null, pErr = null;
try { pcbs = await eda.dmt_Pcb.getAllPcbsInfo(); } catch (e) { pErr = String(e); }
let layers = null, lErr = null;
try { layers = await eda.pcb_Layer.getAllLayers(); } catch (e) { lErr = String(e); }
let copperLayers = null, cErr = null;
try { copperLayers = await eda.pcb_Layer.getTheNumberOfCopperLayers(); } catch (e) { cErr = String(e); }
let nets = null, nErr = null;
try { nets = await eda.pcb_Net.getAllNets(); } catch (e) { nErr = String(e); }
let components = null, pkErr = null;
try { components = await eda.pcb_PrimitiveComponent.getAll(); } catch (e) { pkErr = String(e); }
return {
  pcb: pcb ? {uuid: pcb.uuid, name: pcb.name} : null,
  docHandle, activated, ready, openErr,
  pcbCount: (pcbs || []).length, pErr,
  layerCount: (layers || []).length, lErr,
  copperLayers, cErr,
  netCount: (nets || []).length, nErr,
  componentCount: (components || []).length, pkErr,
  layers,
  nets,
  components
};
"""

JS_SCH_DRC = r"""
const strict = false, userInterface = false, verbose = true;
let passed = null, err = null;
try { passed = await eda.sch_Drc.check(strict, userInterface, verbose); } catch (e) { err = String(e); }
return {passed, err};
"""

JS_PCB_DRC = r"""
let passed = null, err = null, rt = null;
try { passed = await eda.pcb_Drc.check(false, false, true); } catch (e) { err = String(e); }
try { rt = await eda.pcb_Drc.getRealTimeDrcStatus(); } catch (e) { rt = 'err:' + String(e); }
return {passed, err, realTimeStatus: rt};
"""

JS_SCH_NETLIST = r"""
const netlistType = (typeof ESYS_NetlistType !== 'undefined') ? ESYS_NetlistType.PROTEL2 : 'Protel2';
let netlist = null, err = null;
try { netlist = await eda.sch_Netlist.getNetlist(netlistType); } catch (e) { err = String(e); }
return {netlistType: String(netlistType), netlist, err};
"""

JS_BOM_CSV = r"""
let file = null, text = null, err = null;
try {
  file = await eda.sch_ManufactureData.getBomFile('a2spike-bom.csv', 'csv');
  if (file) text = await file.text();
} catch (e) { err = String(e); }
return {fileName: file ? file.name : null, size: file ? file.size : null, text, err};
"""

JS_NETLIST_FILE = r"""
let file = null, text = null, err = null;
try {
  file = await eda.sch_ManufactureData.getNetlistFile('a2spike.net', (typeof ESYS_NetlistType !== 'undefined') ? ESYS_NetlistType.PROTEL2 : 'Protel2');
  if (file) text = await file.text();
} catch (e) { err = String(e); }
return {fileName: file ? file.name : null, size: file ? file.size : null, text, err};
"""

JS_PNG = r"""
function b64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}
let file = null, data = null, err = null;
try {
  file = await eda.sch_ManufactureData.getPngFile('a2spike-page.png');
  if (file) data = b64(await file.arrayBuffer());
} catch (e) { err = String(e); }
return {fileName: file ? file.name : null, size: file ? file.size : null, base64: data, err};
"""

JS_GERBER = r"""
function b64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}
let file = null, data = null, err = null;
try {
  file = await eda.pcb_ManufactureData.getGerberFile('a2spike-gerber.zip');
  if (file) data = b64(await file.arrayBuffer());
} catch (e) { err = String(e); }
return {fileName: file ? file.name : null, size: file ? file.size : null, base64: data, err};
"""

JS_CPL = r"""
let file = null, text = null, err = null;
try {
  file = await eda.pcb_ManufactureData.getPickAndPlaceFile('a2spike-cpl.csv', 'csv', 'mm');
  if (file) text = await file.text();
} catch (e) { err = String(e); }
return {fileName: file ? file.name : null, size: file ? file.size : null, text, err};
"""

JS_TRIVIAL = "return {t: 1};"


# ---------------------------------------------------------------------------
# Probe driver
# ---------------------------------------------------------------------------


class Probe:
    def __init__(self, exe: str, evidence_dir: Path, fixture: Path):
        self.exe = exe
        self.evidence = evidence_dir
        self.fixture = fixture
        self.session_id: str | None = None
        self.raw_dir = evidence_dir / "raw"
        self.artifact_dir = evidence_dir / "artifacts"
        self.results: dict = {"started_at": now_iso(), "steps": []}

    # -- helpers ------------------------------------------------------------
    def _save_raw(self, name: str, result: official_cli.CliResult) -> str:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        rel = f"raw/{name}"
        if result.stdout:
            write_text(self.raw_dir / f"{name}.stdout.json", result.stdout)
        if result.stderr:
            write_text(self.raw_dir / f"{name}.stderr.txt", result.stderr)
        self.results["steps"].append(
            {
                "name": name,
                "argv": result.argv,
                "exit_code": result.exit_code,
                "duration_ms": round(result.duration_ms, 1),
                "json_ok": result.json is not None,
                "stdout_file": f"{rel}.stdout.json",
                "stderr_file": f"{rel}.stderr.txt" if result.stderr else None,
            }
        )
        return f"docs/evidence/{self.evidence.name}/{rel}.stdout.json"

    def _invoke(self, name: str, code: str, timeout_ms: int = 60000):
        assert self.session_id, "no session"
        res = official_cli.invoke(self.exe, self.session_id, code, timeout_ms=timeout_ms)
        self._save_raw(name, res)
        value = None
        if isinstance(res.json, dict):
            value = res.json.get("value")
        return res, value

    # -- probes -------------------------------------------------------------
    def w01_env_and_session(self) -> None:
        doctor = official_cli.doctor(self.exe)
        self._save_raw("W01-doctor", doctor)
        self.results["doctor"] = doctor.json
        sl_before = official_cli.session_list(self.exe)
        self._save_raw("W01-sessions-before", sl_before)
        write_json(self.evidence / "sessions-before.json", sl_before.json)

        opened = official_cli.open_project(self.exe, str(self.fixture), headless=True)
        self._save_raw("W01-open", opened)
        self.session_id = official_cli.session_id_from_open(opened)
        if not self.session_id:
            raise RuntimeError(f"open did not return a sessionId: {opened.stdout[:400]}")

        sl_after = official_cli.session_list(self.exe)
        self._save_raw("W01-sessions-after-open", sl_after)
        origins = official_cli.sessions_by_origin(sl_after.json)
        self.results["sessions_after_open"] = {
            "user_count": len(origins.get("user", [])),
            "cli_count": len(origins.get("cli", [])),
            "ours": [s for s in origins.get("cli", []) if s.get("sessionId") == self.session_id],
            "user_sessions": origins.get("user", []),
        }

        ver = official_cli.run(self.exe, ["--help"])
        self._save_raw("W01-help", ver)
        self.results["version_first_line"] = (ver.stdout.strip().splitlines() or [""])[0]

        # readiness: ``open`` returns before the project is loaded; poll explicitly.
        res, wait = self._invoke("W01-wait-project", JS_WAIT_PROJECT, timeout_ms=180000)
        self.results["open_readiness"] = {
            "value": wait,
            "exit_code": res.exit_code,
            "semantics": "open returns a sessionId before the project is loaded; "
            "getReadyState() can report notLoaded while getCurrentProjectInfo() is already populated",
        }

        # project tree + readiness semantics
        _, tree = self._invoke("W02-project-tree", JS_PROJECT_TREE, timeout_ms=60000)
        self.results["project_tree"] = tree

    def w02_schematic_read(self) -> None:
        act_res, act = self._invoke("W02-activate-sch", JS_ACTIVATE_SCH, timeout_ms=150000)
        self.results["schematic_activate"] = {"value": act, "exit_code": act_res.exit_code}
        _, value = self._invoke("W02-sch-read", JS_READ_SCH, timeout_ms=120000)
        self.results["schematic_read"] = {
            "page": (value or {}).get("page"),
            "componentCount": (value or {}).get("componentCount"),
            "netCount": (value or {}).get("netCount"),
            "wireCount": (value or {}).get("wireCount"),
            "pinCount": (value or {}).get("pinCount"),
            "readiness": {
                "readyByUuid": (value or {}).get("readyByUuid"),
                "readyByTab": (value or {}).get("readyByTab"),
                "activated": (value or {}).get("activated"),
            },
            "errors": {
                k: (value or {}).get(k)
                for k in ("compErr", "netErr", "wireErr", "pinErr", "openErr")
            },
            "sampleComponents": ((value or {}).get("components") or [])[:10],
            "samplePins": ((value or {}).get("pins") or [])[:20],
            "sampleNets": ((value or {}).get("nets") or [])[:20],
            "sampleWires": ((value or {}).get("wires") or [])[:10],
        }

    def w03_pcb_read(self) -> None:
        act_res, act = self._invoke("W03-activate-pcb", JS_ACTIVATE_PCB, timeout_ms=120000)
        self.results["pcb_activate"] = {"value": act, "exit_code": act_res.exit_code}
        _, value = self._invoke("W03-pcb-read", JS_READ_PCB, timeout_ms=120000)
        v = value or {}
        self.results["pcb_read"] = {
            "pcb": v.get("pcb"),
            "pcbCount": v.get("pcbCount"),
            "layerCount": v.get("layerCount"),
            "copperLayers": v.get("copperLayers"),
            "netCount": v.get("netCount"),
            "componentCount": v.get("componentCount"),
            "activated": v.get("activated"),
            "ready": v.get("ready"),
            "errors": {k: v.get(k) for k in ("pErr", "lErr", "cErr", "nErr", "pkErr", "openErr")},
            "layers": (v.get("layers") or [])[:20],
            "nets": (v.get("nets") or [])[:20],
            "components": (v.get("components") or [])[:10],
        }

    def w07_checks(self) -> None:
        # DRC acts on the *active* document; activate each one first.
        self._invoke("W07-activate-sch", JS_ACTIVATE_SCH, timeout_ms=150000)
        _, sch = self._invoke("W07-sch-drc", JS_SCH_DRC, timeout_ms=120000)
        self._invoke("W07-activate-pcb", JS_ACTIVATE_PCB, timeout_ms=120000)
        _, pcb = self._invoke("W07-pcb-drc", JS_PCB_DRC, timeout_ms=120000)
        self.results["checks"] = {"schematic": sch, "pcb": pcb}

    def w08_exports(self) -> None:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        out: dict = {}

        # schematic exports need the schematic document active
        self._invoke("W08-activate-sch", JS_ACTIVATE_SCH, timeout_ms=150000)

        _, netlist = self._invoke("W08-netlist-string", JS_SCH_NETLIST, timeout_ms=120000)
        if netlist and netlist.get("netlist"):
            data = netlist["netlist"].encode("utf-8")
            (self.artifact_dir / "schematic.net").write_bytes(data)
            out["netlist_string"] = {
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "file": "artifacts/schematic.net",
                "head": netlist["netlist"][:200],
            }
        else:
            out["netlist_string"] = {"error": (netlist or {}).get("err")}

        _, netfile = self._invoke("W08-netlist-file", JS_NETLIST_FILE, timeout_ms=120000)
        if netfile and netfile.get("text"):
            data = netfile["text"].encode("utf-8")
            (self.artifact_dir / "schematic-file.net").write_bytes(data)
            out["netlist_file"] = {
                "fileName": netfile.get("fileName"),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "file": "artifacts/schematic-file.net",
            }
        else:
            out["netlist_file"] = {"error": (netfile or {}).get("err")}

        _, bom = self._invoke("W08-bom", JS_BOM_CSV, timeout_ms=120000)
        if bom and bom.get("text"):
            data = bom["text"].encode("utf-8")
            (self.artifact_dir / "bom.csv").write_bytes(data)
            out["bom"] = {
                "fileName": bom.get("fileName"),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "file": "artifacts/bom.csv",
            }
        else:
            out["bom"] = {"error": (bom or {}).get("err")}

        _, png = self._invoke("W08-png", JS_PNG, timeout_ms=180000)
        if png and png.get("base64"):
            data = base64.b64decode(png["base64"])
            (self.artifact_dir / "page.png").write_bytes(data)
            out["png"] = {
                "fileName": png.get("fileName"),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "file": "artifacts/page.png",
                "magic": data[:8].hex(),
            }
        else:
            out["png"] = {"error": (png or {}).get("err")}

        # PCB exports need the PCB document active
        self._invoke("W08-activate-pcb", JS_ACTIVATE_PCB, timeout_ms=120000)

        _, gerber = self._invoke("W08-gerber", JS_GERBER, timeout_ms=240000)
        if gerber and gerber.get("base64"):
            data = base64.b64decode(gerber["base64"])
            (self.artifact_dir / "gerber.zip").write_bytes(data)
            out["gerber"] = {
                "fileName": gerber.get("fileName"),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "file": "artifacts/gerber.zip",
                "magic": data[:8].hex(),
            }
        else:
            out["gerber"] = {"error": (gerber or {}).get("err")}

        _, cpl = self._invoke("W08-cpl", JS_CPL, timeout_ms=120000)
        if cpl and cpl.get("text"):
            data = cpl["text"].encode("utf-8")
            (self.artifact_dir / "cpl.csv").write_bytes(data)
            out["cpl"] = {
                "fileName": cpl.get("fileName"),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "file": "artifacts/cpl.csv",
            }
        else:
            out["cpl"] = {"error": (cpl or {}).get("err")}

        self.results["exports"] = out

    def w06_batch_cost(self) -> None:
        # 10 separate round-trips
        t0 = time.time()
        for _ in range(10):
            official_cli.invoke(self.exe, self.session_id, JS_TRIVIAL, timeout_ms=30000)
        separate_ms = (time.time() - t0) * 1000.0

        # one round-trip that performs 10 reads
        batch_code = "const out = [];\n" + "\n".join(
            "out.push(await eda.sch_Net.getAllNetsName());" for _ in range(10)
        ) + "\nreturn out.length;"
        t1 = time.time()
        res, value = self._invoke("W06-batched-read", batch_code, timeout_ms=120000)
        batched_ms = (time.time() - t1) * 1000.0

        self.results["batch_cost"] = {
            "separate_calls": 10,
            "separate_total_ms": round(separate_ms, 1),
            "separate_per_call_ms": round(separate_ms / 10.0, 1),
            "batched_calls": 1,
            "batched_total_ms": round(batched_ms, 1),
            "batched_value": value,
            "batched_exit_code": res.exit_code,
        }

    def w10_errors(self) -> None:
        out: dict = {}
        bad_session = official_cli.invoke(self.exe, "00000000-0000-0000-0000-000000000000", JS_TRIVIAL)
        self._save_raw("W10-bad-session", bad_session)
        out["bad_session"] = bad_session.to_receipt()

        bad_args = official_cli.run(self.exe, ["invoke", "--session", self.session_id, "--code", JS_TRIVIAL, "--args", "[1,2]"])
        self._save_raw("W10-bad-args", bad_args)
        out["bad_args"] = bad_args.to_receipt()

        bad_doc = official_cli.run(self.exe, ["doc", "api", "--class-name", "DMT_NotARealClass"])
        self._save_raw("W10-bad-doc-api", bad_doc)
        out["bad_doc_api"] = bad_doc.to_receipt()

        throw_code = "throw new Error('a2spike-intentional-throw');"
        thrown = official_cli.invoke(self.exe, self.session_id, throw_code)
        self._save_raw("W10-thrown", thrown)
        out["thrown"] = thrown.to_receipt()

        # permission gate: SYS_FileSystem needs external-interaction permission
        perm_code = "let p = null, e = null; try { p = await eda.sys_FileSystem.getProjectsPaths(); } catch (x) { e = String(x); } return {p, e};"
        _, perm = self._invoke("W10-permission", perm_code)
        out["permission"] = perm

        # timeout: code that never resolves
        t0 = time.time()
        timeout_res = official_cli.run(
            self.exe,
            ["invoke", "--session", self.session_id, "--code", "await new Promise(() => {}); return 1;", "--timeout", "3000"],
            timeout_s=60,
        )
        self._save_raw("W10-timeout", timeout_res)
        out["timeout"] = {"receipt": timeout_res.to_receipt(), "wall_ms": round((time.time() - t0) * 1000.0, 1)}

        # wrong document uuid for activate
        wrong_doc = "let r = null, e = null; try { r = await eda.dmt_EditorControl.activateDocument('deadbeef@deadbeef'); } catch (x) { e = String(x); } return {r, e};"
        _, wd = self._invoke("W10-wrong-document", wrong_doc)
        out["wrong_document"] = wd
        self.results["errors"] = out

    def w09_reopen(self) -> None:
        if not self.session_id:
            return
        before = tree_snapshot(self.fixture)
        closed = official_cli.close_session(self.exe, self.session_id, destroy=True)
        self._save_raw("W09-session-close", closed)
        self.session_id = None
        time.sleep(1.0)
        reopened = official_cli.open_project(self.exe, str(self.fixture), headless=True)
        self._save_raw("W09-reopen", reopened)
        self.session_id = official_cli.session_id_from_open(reopened)
        self._invoke("W09-reopen-wait", JS_WAIT_PROJECT, timeout_ms=180000)
        _, tree = self._invoke("W09-reopen-tree", JS_PROJECT_TREE, timeout_ms=60000)
        after = tree_snapshot(self.fixture)
        self.results["reopen"] = {
            "session_closed": closed.json,
            "reopened_session": self.session_id,
            "tree": tree,
            "fixture_before": before,
            "fixture_after": after,
            "fixture_diff": tree_diff(before, after),
        }

    def w11_mcp(self) -> None:
        from mcp_stdio import probe_mcp_stdio

        self.results["mcp"] = probe_mcp_stdio(self.exe, self.raw_dir)

    def finish(self) -> None:
        if self.session_id:
            closed = official_cli.close_session(self.exe, self.session_id, destroy=True)
            self._save_raw("W99-session-close", closed)
            self.session_id = None
        sl_after = official_cli.session_list(self.exe)
        self._save_raw("W99-sessions-after", sl_after)
        write_json(self.evidence / "sessions-after.json", sl_after.json)
        after = tree_snapshot(self.fixture)
        write_json(self.evidence / "project-after.json", after)
        self.results["finished_at"] = now_iso()
        write_json(self.evidence / "probe-run.json", self.results)


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", default=None, help="path to lceda-pro.exe")
    parser.add_argument("--evidence-date", default="2026-10-28")
    parser.add_argument("--fixture", required=True, help="path to the temp fixture project copy")
    parser.add_argument("--skip", default="", help="comma separated probe names to skip")
    args = parser.parse_args(argv)

    exe = official_cli.find_exe(args.exe)
    evidence = Path(__file__).resolve().parents[2] / "docs" / "evidence" / f"a2-coverage-{args.evidence_date}"
    fixture = Path(args.fixture).resolve()
    if not fixture.exists():
        print(f"fixture does not exist: {fixture}", file=sys.stderr)
        return 2

    probe = Probe(exe, evidence, fixture)
    write_json(evidence / "project-before.json", tree_snapshot(fixture))
    steps = [
        ("w01", probe.w01_env_and_session),
        ("w02", probe.w02_schematic_read),
        ("w08", probe.w08_exports),
        ("w03", probe.w03_pcb_read),
        ("w07", probe.w07_checks),
        ("w06", probe.w06_batch_cost),
        ("w10", probe.w10_errors),
        ("w11", probe.w11_mcp),
        ("w09", probe.w09_reopen),
    ]
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    for name, fn in steps:
        if name in skip:
            print(f"skip {name}")
            continue
        started = time.time()
        print(f"[probe] {name} ...", flush=True)
        try:
            fn()
            print(f"[probe] {name} ok ({time.time() - started:.1f}s)", flush=True)
        except Exception as exc:  # keep going, record the failure
            probe.results.setdefault("failures", []).append(
                {"probe": name, "error": f"{type(exc).__name__}: {exc}"}
            )
            print(f"[probe] {name} FAILED: {type(exc).__name__}: {exc}", flush=True)
    probe.finish()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
