"""Wire + verify the Zhigou acceptance board schematic (2-button / 2-LED, 5 V).

Run order:
  python build_board_wire.py rotate   # flip LEDs so anode faces the resistor
  python build_board_wire.py wire     # power/ground flags + four channel wires
  python build_board_wire.py verify   # save -> reopen -> read back -> assert nets
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = "zhigou-integrated-dual-button-led-20261027"
PAGE = "P1"
EVID = Path(r"C:\Users\jlc\work\zhigou-toolchain\docs\toolchain-integration\evidence\m4")
EVID.mkdir(parents=True, exist_ok=True)


def run(args):
    proc = subprocess.run(["zhigou", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=240)
    return proc


def rj(args, evidence=None, print_out=False):
    proc = run(args)
    try:
        parsed = json.loads(proc.stdout)
    except Exception:
        parsed = None
    if evidence:
        payload = parsed if parsed is not None else {
            "raw": proc.stdout, "stderr": proc.stderr, "exit": proc.returncode}
        (EVID / evidence).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    if print_out:
        print(" ", proc.returncode, (parsed and json.dumps(parsed.get("result"), ensure_ascii=False)[:160])
              or proc.stderr.strip()[:160])
    return parsed, proc


def measured(evidence="wire-list.json"):
    d, p = rj(["sch", "list", "--include-pins", "--include-bbox", "--include-device-identity"],
              evidence)
    comps = {}
    for c in (d or {}).get("result", {}).get("components") or []:
        des = c.get("designator")
        if not des or c.get("componentType") == "sheet":
            continue
        pins = {}
        for pin in c.get("pins") or []:
            pins[pin.get("pinNumber")] = {
                "name": pin.get("pinName"), "x": pin.get("x"), "y": pin.get("y"),
                "net": pin.get("net"), "noConnected": pin.get("noConnected"),
            }
        comps[des] = {"x": c.get("x"), "y": c.get("y"), "pins": pins,
                      "primitiveId": c.get("primitiveId")}
    return comps, p


def pin(comps, ref, number=None, name=None):
    c = comps[ref]
    for num, data in c["pins"].items():
        if number is not None and str(num) == str(number):
            return data
        if name is not None and (data.get("name") or "").upper() == name.upper():
            return data
    raise KeyError(f"{ref} pin number={number} name={name} not found in {list(c['pins'])}")


def cmd_rotate():
    comps, _ = measured("rotate-before.json")
    for des in ("D1", "D2"):
        c = comps[des]
        a = pin(comps, des, name="A")
        if a["x"] < c["x"]:
            print(f"{des}: anode already on the resistor side")
            continue
        d, p = rj(["sch", "modify", "--id", c["primitiveId"], "--rotation", "180"],
                  f"rotate-{des}.json", print_out=True)
        print(f"rotate {des}:", (d or {}).get("ok"))
    return 0


def cmd_wire():
    comps, _ = measured("wire-before.json")
    # 1) power / ground via typed flags on measured pins (short stub, no long runs)
    flags = [
        ("J1", None, "1", "power", "VIN"),
        ("J1", None, "2", "gnd", "GND"),
        ("F1", None, "1", "power", "VIN"),
        ("F1", None, "2", "power", "+5V"),
        ("C1", None, "1", "power", "+5V"),
        ("C1", None, "2", "gnd", "GND"),
        ("R1", None, "1", "power", "+5V"),
        ("R2", None, "1", "power", "+5V"),
        ("SW1", None, "2", "gnd", "GND"),
        ("SW2", None, "2", "gnd", "GND"),
    ]
    results = []
    for ref, _unused, num, kind, net in flags:
        current = (comps.get(ref, {}).get("pins", {}).get(str(num)) or {}).get("net") or ""
        if current.strip() == net:
            results.append({"ref": ref, "pin": num, "kind": kind, "net": net,
                            "ok": True, "skipped": "already on net"})
            print(f"flag {ref}:{num} {kind} {net}: already connected")
            continue
        d, p = rj(["sch", "autoconnect", "--pin", f"{ref}:{num}", "--kind", kind,
                   "--net", net], f"connect-{ref}-{num}.json")
        ok = bool((d or {}).get("ok"))
        results.append({"ref": ref, "pin": num, "kind": kind, "net": net, "ok": ok,
                        "error": (d or {}).get("error")})
        print(f"flag {ref}:{num} {kind} {net}: ok={ok}")
        if not ok:
            print("   ", json.dumps((d or {}).get("error"), ensure_ascii=False)[:200])

    # 2) channel wires: R.pin2 -> LED anode, LED cathode -> SW.pin1 (straight runs)
    comps, _ = measured("wire-mid.json")
    wires = []
    for ch, (r, led, sw) in enumerate((("R1", "D1", "SW1"), ("R2", "D2", "SW2")), start=1):
        r_out = pin(comps, r, number="2")
        anode = pin(comps, led, name="A")
        cathode = pin(comps, led, name="K")
        sw_in = pin(comps, sw, number="1")
        for label, a, b, net in (
            (f"ch{ch}_r_to_anode", r_out, anode, f"LED{ch}_A"),
            (f"ch{ch}_cathode_to_switch", cathode, sw_in, f"LED{ch}_K"),
        ):
            points = [[a["x"], a["y"]], [b["x"], b["y"]]]
            d, p = rj(["sch", "wire", "--points", json.dumps(points), "--net", net],
                      f"wire-{label}.json")
            ok = bool((d or {}).get("ok"))
            wires.append({"wire": label, "points": points, "net": net, "ok": ok,
                          "error": (d or {}).get("error")})
            print(f"wire {label} {points} net={net}: ok={ok}")
            if not ok:
                print("   ", json.dumps((d or {}).get("error"), ensure_ascii=False)[:200])

    (EVID / "wiring-summary.json").write_text(
        json.dumps({"flags": results, "wires": wires}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return 0 if all(r["ok"] for r in results) and all(w["ok"] for w in wires) else 1


def cmd_verify():
    d, p = rj(["sch", "save"], "verify-save.json")
    saved = (d or {}).get("result", {}).get("saved") is True
    print("save saved:", saved, "exit:", p.returncode)

    d, p = rj(["doc", "reload", PAGE], "verify-reload.json")
    print("reload exit:", p.returncode)

    comps, _ = measured("verify-list.json")
    d, p = rj(["sch", "read"], "verify-read.json")
    read = (d or {}).get("result") or {}
    nets = {}
    for c in read.get("components") or []:
        des = c.get("designator")
        for pn in c.get("pins") or []:
            net = (pn.get("net") or "").strip()
            if not net:
                continue
            nets.setdefault(net, set()).add(f"{des}.{pn.get('number')}")

    expected = {
        "VIN": {"J1.1", "F1.1"},
        "+5V": {"F1.2", "C1.1", "R1.1", "R2.1"},
        "GND": {"J1.2", "C1.2", "SW1.2", "SW2.2"},
        "LED1_A": {"R1.2", "D1.2"},
        "LED1_K": {"D1.1", "SW1.1"},
        "LED2_A": {"R2.2", "D2.2"},
        "LED2_K": {"D2.1", "SW2.1"},
    }
    checks = {}
    for net, want in expected.items():
        got = nets.get(net)
        checks[net] = {"expected": sorted(want),
                       "measured": sorted(got) if got else None,
                       "match": got == want}
    floats = [f for f in (read.get("floatingPins") or [])]
    summary = {
        "schema": "zhigou-m4-schematic-verify/v1",
        "project": PROJECT, "page": PAGE,
        "componentCount": read.get("componentCount"),
        "netCount": read.get("netCount"),
        "floatingPinCount": read.get("floatingPinCount"),
        "saveConfirmed": saved,
        "resources": (EVID / "verify-read.json").name,
        "nets": checks,
        "allNetsMatch": all(c["match"] for c in checks.values()),
        "unexpectedNets": {n: sorted(v) for n, v in nets.items() if n not in expected},
        "check": read.get("check"),
    }
    (EVID / "schematic-verify.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print(json.dumps({"components": summary["componentCount"], "nets": summary["netCount"],
                      "floating": summary["floatingPinCount"],
                      "allNetsMatch": summary["allNetsMatch"],
                      "netDetail": {k: v["match"] for k, v in checks.items()}},
                     ensure_ascii=False, indent=1))
    return 0 if saved and summary["allNetsMatch"] else 1


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "verify"
    raise SystemExit({"rotate": cmd_rotate, "wire": cmd_wire, "verify": cmd_verify}[action]())
