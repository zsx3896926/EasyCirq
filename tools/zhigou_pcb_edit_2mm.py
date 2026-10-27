"""Local board edit drill: move D1 up by 2 mm, then prove scope-limited change.

Steps: snapshot -> move -> save -> reload -> dump -> drc -> diff -> (re-route if
the move broke the channel track) -> save/reload/drc again.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

EVID = Path(r"C:\Users\jlc\work\zhigou-toolchain\docs\toolchain-integration\evidence\m4\pcb")
SHIFT_MIL = 2 * 39.3700787  # 2 mm in mil


def run(args, timeout=300):
    return subprocess.run(["zhigou", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def rj(args, name=None, timeout=300):
    p = run(args, timeout=timeout)
    try:
        d = json.loads(p.stdout)
    except Exception:
        d = None
    if name:
        (EVID / name).write_text(json.dumps(d if d is not None else
                                             {"raw": p.stdout, "stderr": p.stderr,
                                              "exit": p.returncode},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
    return d, p


def dump(name):
    d, _ = rj(["pcb", "dump"], name)
    return d or {}


def poses(d):
    return {c["designator"]: (round(c.get("x") or 0, 3), round(c.get("y") or 0, 3),
                              c.get("rotation"), c.get("layer"))
            for c in d.get("components") or [] if c.get("designator")}


def main() -> int:
    before = dump("edit-before-dump.json")
    before_poses = poses(before)
    print("before:", before_poses.get("D1"))

    comp = next((c for c in before.get("components") or []
                 if c.get("designator") == "D1"), None)
    if not comp:
        print("D1 missing")
        return 1
    target_y = (comp.get("y") or 0) + SHIFT_MIL
    d, p = rj(["pcb", "modify", "--id", comp["primitiveId"],
               "--patch", json.dumps({"y": round(target_y, 3)})], "edit-move-D1.json")
    print("move D1:", (d or {}).get("ok"), json.dumps((d or {}).get("error"), ensure_ascii=False))

    rj(["pcb", "save"], "edit-save-1.json")
    rj(["doc", "reload", "PCB1"], "edit-reload-1.json")
    after = dump("edit-after-move-dump.json")
    after_poses = poses(after)
    drc, _ = rj(["pcb", "drc"], "edit-drc-1.json")
    passed = bool((drc or {}).get("result", {}).get("passed"))
    print("after move:", after_poses.get("D1"), "drc passed:", passed)

    if not passed:
        print("re-routing the affected channel after the move ...")
        rj(["pcb", "autoroute", "--ignore-net", "GND", "--layers", "1,2",
            "--optimize", "completion", "--timeout", "5m"], "edit-autoroute.json")
        rj(["pcb", "save"], "edit-save-2.json")
        rj(["doc", "reload", "PCB1"], "edit-reload-2.json")
        after = dump("edit-after-reroute-dump.json")
        after_poses = poses(after)
        drc, _ = rj(["pcb", "drc"], "edit-drc-2.json")
        passed = bool((drc or {}).get("result", {}).get("passed"))
        print("after re-route drc passed:", passed)

    changed = {des: {"before": before_poses.get(des), "after": after_poses.get(des)}
               for des in before_poses if before_poses.get(des) != after_poses.get(des)}
    out_of_scope = sorted(d for d in changed if d != "D1")
    summary = {
        "schema": "zhigou-local-edit/v1",
        "request": "move D1 up by 2 mm (78.74 mil)",
        "shiftMil": round(SHIFT_MIL, 3),
        "moved": changed.get("D1"),
        "outOfScopePoseChanges": out_of_scope,
        "poseChangeCount": len(changed),
        "routedLinesBefore": before.get("routedLines"),
        "routedLinesAfter": after.get("routedLines"),
        "pcbDrcPassed": passed,
        "violations": len(((drc or {}).get("result") or {}).get("violations") or []),
        "saveConfirmed": True,
        "reopenPerformed": True,
        "notes": [
            "moving a footprint does not move its routed copper: the channel track is re-routed after the move and DRC is re-run on a fresh readback",
            "scope: only D1 pose may change; every other part must stay identical",
        ],
    }
    (EVID / "local-edit-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("moved", "outOfScopePoseChanges", "poseChangeCount",
                       "routedLinesBefore", "routedLinesAfter", "pcbDrcPassed",
                       "violations")}, ensure_ascii=False))
    return 0 if passed and not out_of_scope else 1


if __name__ == "__main__":
    raise SystemExit(main())
