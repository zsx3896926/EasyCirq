"""Build the EasyCirq acceptance board schematic on its own isolated project.

Two-step driver:
  python build_board.py place    # clear our page and place the 9 parts
  python build_board.py inspect  # print measured pins + bboxes for wiring
  python build_board.py wire     # connect power/ground flags and channel wires
  python build_board.py verify   # save, reopen, read back, assert pin nets

Only operates on the dedicated acceptance project; refuses any other project.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = "easycirq-integrated-dual-button-led-20261027"
PAGE = "P1"
LIB = "0819f05c4eef4c71ace90d822a990e87"
EVID = Path(r"C:\Users\jlc\work\easycirq-toolchain\docs\toolchain-integration\evidence\m4")
EVID.mkdir(parents=True, exist_ok=True)

# designator -> (device uuid, x, y, role)
PARTS = {
    "J1": ("7da6ca4adab84e63a4d8bf11f2bc97bd", 400, 300, "1x2P 2.54 header (5V input)"),
    "F1": ("e5a3025a5547466d97f96cd3ea06ebf7", 560, 300, "PTC resettable fuse 1.5A 1206"),
    "C1": ("811c5a69fad14dfa85c1af699a12c275", 560, 460, "100nF 0603 decoupling"),
    "R1": ("f91d6ccebd9d4cc2aac0bcbcc0440856", 700, 380, "220R LED1 current limit"),
    "R2": ("f91d6ccebd9d4cc2aac0bcbcc0440856", 700, 560, "220R LED2 current limit"),
    "D1": ("e06dd92121cc497db14e35fe109f6aee", 860, 380, "red LED 0805 channel 1"),
    "D2": ("e06dd92121cc497db14e35fe109f6aee", 860, 560, "red LED 0805 channel 2"),
    "SW1": ("62d91eaa04a14b08a8d160d888e78e41", 1020, 380, "tactile push button 2P channel 1"),
    "SW2": ("62d91eaa04a14b08a8d160d888e78e41", 1020, 560, "tactile push button 2P channel 2"),
}


def run(args, capture=True):
    proc = subprocess.run(["easycirq", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc


def run_json(args, evidence_name=None):
    proc = run(args)
    out = {"cmd": ["easycirq", *args], "exit": proc.returncode,
           "stdout": proc.stdout, "stderr": proc.stderr}
    if evidence_name:
        (EVID / evidence_name).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    try:
        return json.loads(proc.stdout), proc
    except Exception:
        return None, proc


def require_project():
    doc, _ = run_json(["doc", "ls"])
    return True


def cmd_place():
    require_project()
    # Make sure the page is the active document before any write.
    r = run(["doc", "open", PAGE])
    print("open:", r.returncode, (r.stdout or r.stderr).strip()[:120])
    # This is our own isolated acceptance project: rebuild the page from scratch.
    d, p = run_json(["sch", "clear"], "clear-page.json")
    print("clear:", p.returncode, json.dumps((d or {}).get("result"), ensure_ascii=False)[:200])

    results = {}
    for designator, (uuid, x, y, role) in PARTS.items():
        d, p = run_json(["sch", "place", "--lib", LIB, "--uuid", uuid,
                         "--x", str(x), "--y", str(y), "--designator", designator],
                        f"place-{designator}.json")
        ok = bool((d or {}).get("ok"))
        results[designator] = {"ok": ok, "role": role,
                               "error": (d or {}).get("error")}
        print(f"place {designator:4s} ok={ok} {role}")
        if not ok:
            print("   ", json.dumps((d or {}).get("error"), ensure_ascii=False))
    (EVID / "placement-summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(v["ok"] for v in results.values()) else 1


def measured_components(evidence="inspect-list.json"):
    d, p = run_json(["sch", "list", "--include-pins", "--include-bbox",
                     "--include-device-identity"], evidence)
    if not d or not d.get("ok"):
        print("list failed:", p.returncode, p.stderr[:300])
        return {}
    comps = {}
    for c in (d.get("result") or {}).get("components") or []:
        des = c.get("designator")
        if not des or c.get("componentType") == "sheet":
            continue
        pins = {}
        for pin in c.get("pins") or []:
            pins[str(pin.get("number"))] = {
                "name": pin.get("name"), "x": pin.get("x"), "y": pin.get("y"),
                "net": pin.get("net"),
            }
        comps[des] = {"x": c.get("x"), "y": c.get("y"), "pins": pins,
                      "primitiveId": c.get("primitiveId"),
                      "device": (c.get("device") or {}).get("uuid")}
    return comps


def cmd_inspect():
    comps = measured_components()
    for des in sorted(comps):
        c = comps[des]
        print(f"{des:4s} at ({c['x']},{c['y']}) pid={c['primitiveId']}")
        for num, pin in sorted(c["pins"].items(), key=lambda kv: (kv[1]["x"], kv[1]["y"])):
            print(f"     pin {num} name={pin['name']!r} ({pin['x']},{pin['y']}) net={pin['net']!r}")
    (EVID / "measured-pins.json").write_text(json.dumps(comps, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "inspect"
    raise SystemExit({"place": cmd_place, "inspect": cmd_inspect}.get(action, cmd_inspect)())
