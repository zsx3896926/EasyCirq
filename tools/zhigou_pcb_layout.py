"""Lay out the acceptance board PCB on the real host (placement + outline).

Run: python build_pcb_layout.py [place|outline|status]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

EVID = Path(r"C:\Users\jlc\work\zhigou-toolchain\docs\toolchain-integration\evidence\m4\pcb")
EVID.mkdir(parents=True, exist_ok=True)

# designator -> (x mil, y mil, rotation) : two-channel power/switch layout,
# power entry on the left, channel 1 above the axis, channel 2 below.
LAYOUT = {
    "J1": (-700, 0, 90),
    "F1": (-520, 0, 0),
    "C1": (-360, 0, 0),
    "R1": (-100, 220, 0),
    "D1": (30, 220, 0),
    "SW1": (300, 220, 0),
    "R2": (-100, -220, 0),
    "D2": (30, -220, 0),
    "SW2": (300, -220, 0),
}


def run(args, timeout=180):
    return subprocess.run(["zhigou", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def rj(args, name=None, timeout=180):
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


def comps():
    d, _ = rj(["pcb", "list"], "layout-list.json")
    out = {}
    for c in (d or {}).get("result", {}).get("components") or []:
        if c.get("designator"):
            out[c["designator"]] = c
    return out


def cmd_place():
    current = comps()
    results = []
    for des, (x, y, rot) in LAYOUT.items():
        c = current.get(des)
        if not c:
            print(f"{des}: not on PCB")
            results.append({"designator": des, "ok": False, "error": "missing"})
            continue
        patch = json.dumps({"x": x, "y": y, "rotation": rot})
        d, p = rj(["pcb", "modify", "--id", c["primitiveId"], "--patch", patch],
                  f"modify-{des}.json")
        ok = bool((d or {}).get("ok"))
        results.append({"designator": des, "ok": ok, "patch": json.loads(patch),
                        "error": (d or {}).get("error")})
        print(f"move {des:4s} -> ({x},{y}) rot={rot}: ok={ok}")
        if not ok:
            print("   ", json.dumps((d or {}).get("error"), ensure_ascii=False)[:160])
    (EVID / "layout-summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(r["ok"] for r in results) else 1


def cmd_outline():
    d, p = rj(["pcb", "outline-fit", "--margin", "100"], "outline-fit.json")
    print("outline-fit:", (d or {}).get("ok"), json.dumps((d or {}).get("result") or
                                                         (d or {}).get("error"),
                                                         ensure_ascii=False)[:300])
    d, p = rj(["pcb", "outline-get"], "outline-after.json")
    res = (d or {}).get("result") or {}
    print("outline bbox:", res.get("bbox"), "w/h:", res.get("width"), res.get("height"))
    return 0 if (d or {}).get("ok") else 1


def cmd_status():
    d, _ = rj(["pcb", "dump"], "dump-after-layout.json")
    dump = d or {}
    print("components:", [c.get("designator") for c in dump.get("components") or []])
    print("routedLines:", dump.get("routedLines"))
    print("copperLayers:", dump.get("copperLayers"))
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    raise SystemExit({"place": cmd_place, "outline": cmd_outline, "status": cmd_status}[action]())
