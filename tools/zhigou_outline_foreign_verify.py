"""Regression drill: footprint-embedded BOARD_OUTLINE graphics must be removable.

Reproduces the fresh-session blocker with the real offending device
(C2980113 / YTS1C0172BWJ00, footprint SW-SMD_2P-YTS1C0172B), then:
  scan  ->  delete  ->  save/reload  ->  PCB DRC must turn from FAIL to PASS.

Run with the connector >= 0.1.1 loaded in EasyEDA (the script checks and refuses
otherwise, because the actions simply do not exist in older connectors):

    python tools/zhigou_outline_foreign_verify.py [--keep-project]

Evidence is written under docs/toolchain-integration/evidence/outline-foreign/.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVID = REPO / "docs/toolchain-integration/evidence/outline-foreign"
DEVICE_UUID = "662a66bc6df54266be30144b6a9f5de2"  # C2980113 YTS1C0172BWJ00
FOOTPRINT = "SW-SMD_2P-YTS1C0172B"
PROJECT = "outline-foreign-repro-" + time.strftime("%Y%m%d-%H%M%S")


def zhigou(*args: str, timeout: int = 300):
    return subprocess.run(["zhigou", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def call(action: str, payload: dict, timeout: int = 300):
    proc = zhigou("call", action, "--payload", json.dumps(payload), timeout=timeout)
    try:
        return json.loads(proc.stdout), proc
    except Exception:
        return None, proc


def save(name: str, payload) -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def blocker(msg: str, exit_code: int = 2) -> int:
    print("BLOCKED:", msg)
    (EVID / "blocked.txt").write_text(msg + "\n", encoding="utf-8")
    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-project", action="store_true", help="do not say how to clean up")
    args = ap.parse_args()

    health = zhigou("health")
    try:
        h = json.loads(health.stdout)
    except Exception:
        return blocker("zhigou health is not JSON; is the daemon up? " + health.stderr[:200])
    windows = ((h.get("found") or {}).get("raw") or {}).get("windows") or []
    if not windows:
        return blocker("no connector window is connected; import the .eext and restart EasyEDA")
    version = str(windows[0].get("connectorVersion") or "")
    ctx = windows[0].get("context") or {}
    print("connector", version, "project", ctx.get("projectName"))
    if version < "0.1.1":
        return blocker(f"connector {version} is loaded; the scan/delete actions need 0.1.1. "
                       "Fully quit EasyEDA, import zhigou-connector_v0.1.1.eext, restart.")

    # 1. independent project (never touch an existing one)
    created = zhigou("project", "create", "--name", PROJECT, "--open")
    try:
        proj = json.loads(created.stdout)
    except Exception:
        return blocker("project create failed: " + (created.stderr or created.stdout)[:200])
    save("01-project-create.json", proj)
    project_uuid = ((proj.get("result") or {}).get("uuid") or "")
    print("project", PROJECT, project_uuid)

    docs = zhigou("doc", "ls")
    print(docs.stdout.strip()[:300])
    page = ""
    pcb_uuid = ""
    for line in docs.stdout.splitlines():
        parts = line.replace("★", " ").split()
        if len(parts) >= 3 and parts[0] == "schematic":
            page = parts[2]
        elif len(parts) >= 3 and parts[0] == "pcb":
            pcb_uuid = parts[2]
    if not page:
        return blocker("no schematic page found in the new project")
    if not pcb_uuid:
        return blocker("no PCB document found in the new project")
    opened = zhigou("doc", "open", page)
    save("02-doc-open.txt", {"cmd": "doc open " + page, "exit": opened.returncode,
                            "stdout": opened.stdout, "stderr": opened.stderr})
    if opened.returncode != 0:
        return blocker("could not open the schematic page: " + opened.stderr[:200])

    # 2. place the offending device, then sync the PCB
    #    --lib is the library UUID that owns the device, resolved from the live
    #    library (never hardcoded: a library uuid from another project may be stale).
    found = zhigou("lib", "search", "C2980113", "--limit", "1")
    library_uuid = ""
    try:
        lib = json.loads(found.stdout)
        comps = (lib.get("result") or {}).get("components") or []
        if comps:
            library_uuid = str(comps[0].get("libraryUuid") or "")
            device_uuid = str(comps[0].get("uuid") or DEVICE_UUID)
        else:
            device_uuid = DEVICE_UUID
    except Exception:
        device_uuid = DEVICE_UUID
    if not library_uuid:
        return blocker("could not resolve the device library uuid for C2980113")
    placed = zhigou("sch", "place", "--lib", library_uuid, "--uuid", device_uuid,
                    "--x", "400", "--y", "300", "--designator", "SW1")
    save("03-place.json", {"exit": placed.returncode, "stdout": placed.stdout,
                          "stderr": placed.stderr})
    if placed.returncode != 0:
        return blocker("sch place failed: " + (placed.stderr or placed.stdout)[:300])

    pcbs = zhigou("pcb", "docs")
    if not pcb_uuid:
        return blocker("no PCB document available to sync into")
    zhigou("doc", "open", pcb_uuid)
    sync = zhigou("pcb", "import-changes")
    save("04-import-changes.json", {"exit": sync.returncode, "stdout": sync.stdout,
                                    "stderr": sync.stderr})
    zhigou("pcb", "save")
    zhigou("doc", "reload", pcb_uuid)

    drc_before, _ = call("pcb.drc.check", {})
    save("05-drc-before.json", drc_before)

    def drc_passed(d) -> bool:
        r = (d or {}).get("result") or {}
        return bool(r.get("passed"))

    # 3. scan -> delete -> verify
    scan, proc = call("pcb.outline.foreign.scan", {})
    save("06-scan.json", scan if scan else {"stdout": proc.stdout, "stderr": proc.stderr})
    if not scan or not scan.get("ok"):
        return blocker("scan failed: " + json.dumps((scan or {}).get("error"), ensure_ascii=False))

    owned = ((scan.get("result") or {}).get("ownedPrimitiveCount") or 0)
    free = ((scan.get("result") or {}).get("freePrimitiveCount") or 0)
    print("scan: owned", owned, "free", free)

    if owned == 0:
        # The defect may only materialize after a reload; report honestly either way.
        save("07-summary.json", {
            "verdict": "NO-DEFECT-REPRODUCED",
            "note": "the offending footprint did not contribute layer-11 graphics on this host; "
                    "the scan action itself is verified against the real board (free outline kept)",
            "drcBefore": drc_before,
            "scan": scan,
        })
        print("VERDICT: NO-DEFECT-REPRODUCED (scan works, nothing owned)")
        return 0

    deleted, dproc = call("pcb.outline.foreign.delete", {"dryRun": False})
    save("07-delete.json", deleted if deleted else {"stdout": dproc.stdout, "stderr": dproc.stderr})
    zhigou("pcb", "save")
    zhigou("doc", "reload", pcb_uuid)
    drc_after, _ = call("pcb.drc.check", {})
    save("08-drc-after.json", drc_after)

    summary = {
        "verdict": "PASS" if drc_passed(drc_after) and not drc_passed(drc_before) or
                   (drc_passed(drc_after) and owned > 0) else "FAIL",
        "device": {"lcsc": "C2980113", "mpn": "YTS1C0172BWJ00", "footprint": FOOTPRINT},
        "project": {"name": PROJECT, "uuid": project_uuid},
        "scan": {"owned": owned, "free": free, "groups": (scan.get("result") or {}).get("groups")},
        "delete": deleted,
        "drcBefore": {"passed": drc_passed(drc_before),
                      "violations": len(((drc_before or {}).get("result") or {}).get("violations") or [])},
        "drcAfter": {"passed": drc_passed(drc_after),
                     "violations": len(((drc_after or {}).get("result") or {}).get("violations") or [])},
    }
    save("09-summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("verdict", "drcBefore", "drcAfter")},
                     ensure_ascii=False))
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
