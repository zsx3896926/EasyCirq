"""Spike: verify the host @beta manufacture exports (Gerber / CPL / netlist / 3D).

Runs against the live connector 0.1.4 and the acceptance board PCB. Every export is
attached as an artifact by the daemon under <project>/.zhigou/artifacts; this
script inspects what actually came out instead of trusting the action's ok flag.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import subprocess
import sys
import time
import zipfile

REPO = pathlib.Path(r"C:\Users\jlc\work\zhigou-toolchain")
Z = REPO / "runtime/dist/zhigou.exe"
EVID = REPO / "docs/toolchain-integration/evidence/manufacture-spike"
PROJECT_UUID = "43ebf71ffd34473f9b08aaa118aa2d5e"  # zhigou-integrated-dual-button-led-20261027
WIN = ""  # target window that runs connector 0.1.4 (set by main)


def run(*args, timeout=300):
    cmd = [str(Z), *args]
    if WIN and "--window" not in args and "--project" not in args:
        cmd += ["--window", WIN]
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def call(action: str, payload: dict, timeout=600):
    proc = run("call", action, "--payload", json.dumps(payload), timeout=timeout)
    try:
        text = proc.stdout
        i = text.find("{")
        return json.loads(text[i:]), proc
    except Exception:
        return None, proc


def save(name: str, obj) -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def connector_version():
    proc = run("health")
    try:
        d = json.loads(proc.stdout)
    except Exception:
        return None, None
    ws = ((d.get("found") or {}).get("raw") or {}).get("windows") or []
    for w in ws:
        if str(w.get("connectorVersion")) == "0.1.4":
            return "0.1.4", w.get("windowId")
    return (ws[0].get("connectorVersion") if ws else None), (ws[0].get("windowId") if ws else None)


def latest_artifact(kind: str, after: float):
    """Find the newest artifact written by the daemon for this export."""
    roots = [pathlib.Path.cwd(), REPO]
    candidates = []
    for root in roots:
        for p in root.glob("**/.zhigou/artifacts/*"):
            try:
                if p.stat().st_mtime >= after - 1:
                    candidates.append(p)
            except OSError:
                pass
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1] if candidates else None


def main() -> int:
    global WIN
    EVID.mkdir(parents=True, exist_ok=True)
    ver, win = connector_version()
    print("connector:", ver, "| window:", win)
    if ver != "0.1.4" or not win:
        print("BLOCKED: connector 0.1.4 is not loaded (got %r). Import the 0.1.4 .eext and restart EDA." % ver)
        (EVID / "BLOCKED.txt").write_text("connector %r, expected 0.1.4" % ver, encoding="utf-8")
        return 2
    WIN = win

    # activate the acceptance board PCB
    print(run("call", "project.open", "--payload",
              json.dumps({"projectUuid": PROJECT_UUID, "allowDiscardUnsaved": True})).stdout[-160:])
    docs = run("doc", "ls")
    pcb = ""
    for line in docs.stdout.splitlines():
        parts = line.replace("★", " ").split()
        if len(parts) >= 3 and parts[0] == "pcb":
            pcb = parts[2]
    if not pcb:
        print("BLOCKED: no PCB document")
        return 2
    print(run("doc", "open", pcb).stdout.strip()[-120:])
    time.sleep(1)

    results: dict[str, object] = {"connector": ver, "pcb": pcb}

    # --- Gerber ---
    t0 = time.time()
    gerber, proc = call("pcb.manufacture.gerber", {"fileName": "acceptance-gerber", "unit": "mm", "drill": True})
    save("01-gerber.json", gerber if gerber else {"stdout": proc.stdout, "stderr": proc.stderr})
    if gerber and gerber.get("ok"):
        art = latest_artifact("pcb_gerber", t0)
        info = {"size": (gerber.get("result") or {}).get("size"), "file": art.name if art else None}
        if art and zipfile.is_zipfile(art):
            with zipfile.ZipFile(art) as z:
                names = z.namelist()
                gbr = [n for n in names if n.lower().endswith(
                    (".gbr", ".gtl", ".gbl", ".gto", ".gbo", ".gts", ".gbs", ".gtp", ".gko", ".gdl", ".g1", ".g2"))]
                drl = [n for n in names if n.lower().endswith((".drl", ".xln", ".drill")) or "drill" in n.lower()]
                info.update({"entries": len(names), "gerberLayers": sorted(gbr), "drillFiles": sorted(drl),
                             "totalUncompressed": sum(z.getinfo(n).file_size for n in names)})
                (EVID / "01-gerber-listing.json").write_text(
                    json.dumps({"entries": names}, ensure_ascii=False, indent=2), encoding="utf-8")
        results["gerber"] = info
        print("gerber:", json.dumps(info, ensure_ascii=False)[:400])
    else:
        results["gerber"] = {"error": (gerber or {}).get("error") or proc.stdout[-300:]}
        print("gerber FAILED:", results["gerber"])

    # --- CPL ---
    t0 = time.time()
    cpl, proc = call("pcb.manufacture.cpl", {"fileName": "acceptance-cpl", "fileType": "csv", "unit": "mm"})
    save("02-cpl.json", cpl if cpl else {"stdout": proc.stdout, "stderr": proc.stderr})
    if cpl and cpl.get("ok"):
        art = latest_artifact("pcb_cpl", t0)
        info = {"size": (cpl.get("result") or {}).get("size"), "file": art.name if art else None}
        if art:
            raw = art.read_bytes()
            if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                enc = "utf-16"
            else:
                enc = "utf-8-sig"
            try:
                text = raw.decode(enc)
            except UnicodeDecodeError:
                enc = "gbk"
                text = raw.decode("gbk", errors="replace")
            rows = list(csv.reader(text.splitlines()))
            info.update({"encoding": enc, "rows": len(rows) - 1 if rows else 0, "header": rows[0] if rows else [], "designators": [r[0] for r in rows[1:12] if r]})
        results["cpl"] = info
        print("cpl:", json.dumps(info, ensure_ascii=False)[:400])
    else:
        results["cpl"] = {"error": (cpl or {}).get("error") or proc.stdout[-300:]}
        print("cpl FAILED:", results["cpl"])

    # --- netlist (PCB side; schematic side returned no file) ---
    t0 = time.time()
    net, proc = call("pcb.manufacture.netlist", {"fileName": "acceptance-netlist", "netlistType": "JLCEDA"})
    save("03-netlist.json", net if net else {"stdout": proc.stdout, "stderr": proc.stderr})
    if net and net.get("ok"):
        art = latest_artifact("pcb_netlist", t0)
        info = {"size": (net.get("result") or {}).get("size"), "file": art.name if art else None}
        if art:
            raw = art.read_bytes()
            info["head"] = raw[:400].decode("utf-8", errors="replace")
            info["lines"] = raw.count(b"\n")
        results["netlist"] = info
        print("netlist:", json.dumps({k: info[k] for k in ("size", "file", "lines")}, ensure_ascii=False))
    else:
        results["netlist"] = {"error": (net or {}).get("error") or proc.stdout[-300:]}
        print("netlist FAILED:", results["netlist"])

    # --- 3D (existing action, verify geometry not just binding) ---
    for ftype in ("obj", "step"):
        t0 = time.time()
        three, proc = call("pcb.export.3d", {"fileType": ftype, "fileName": f"acceptance-3d-{ftype}",
                                            "autoGenerateModels": True}, timeout=900)
        save(f"04-3d-{ftype}.json", three if three else {"stdout": proc.stdout, "stderr": proc.stderr})
        if three and three.get("ok"):
            art = latest_artifact("pcb_3d", t0)
            info = {"size": (three.get("result") or {}).get("size"), "file": art.name if art else None}
            if art:
                raw = art.read_bytes()
                if ftype == "obj":
                    head = raw[:400].decode("utf-8", errors="replace")
                    info["head"] = head[:200]
                    info["objVertices"] = sum(1 for line in raw[:200000].splitlines() if line.startswith(b"v "))
                else:
                    info["head"] = raw[:200].decode("utf-8", errors="replace").strip()
                    info["isStep"] = b"ISO-10303-21" in raw[:500]
            results[f"3d_{ftype}"] = info
            print(f"3d {ftype}:", json.dumps({k: info[k] for k in ("size", "file")}, ensure_ascii=False))
        else:
            results[f"3d_{ftype}"] = {"error": (three or {}).get("error") or proc.stdout[-300:]}
            print(f"3d {ftype} FAILED:", results[f"3d_{ftype}"])

    save("99-summary.json", results)
    ok = all(not (isinstance(v, dict) and v.get("error")) for k, v in results.items()
             if k in ("gerber", "cpl", "netlist"))
    print("SPIKE:", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
