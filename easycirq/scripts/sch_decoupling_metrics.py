#!/usr/bin/env python3
"""Decoupling coverage from a connectivity IR: every IC power pin needs a capacitor.

Heuristic, declared explicitly (not a substitute for layout/AC analysis):

  * a "power pin" is a pin whose name is in ``POWER_PIN_NAMES`` (GND/AGND/VSS
    excluded by design);
  * only ICs count -- a component whose reference starts with ``U``/``IC``.
    Connector, resistor and diode power pins are not decoupling targets;
  * a power pin is covered when any other member of its net is a capacitor
    (reference starts with ``C``);
  * an explicitly no-connect pin is not a decoupling target.

Output ``easycirq-sch-power-check/v1`` with ``metrics.decap_missing`` and one
``decap_missing`` finding per uncovered IC power pin.

Exit codes: 0 = covered, 1 = uncovered pins, 2 = invalid input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-power-check/v1"
POWER_PIN_NAMES = {
    "VCC", "VDD", "VBUS", "VBAT", "VIN", "VIN_5V", "VIN_3V3",
    "AVDD", "DVDD", "AVCC", "PVDD", "VDDIO", "IOVDD", "VDD_IO",
    "3V3", "5V", "3.3V", "5.0V", "+5V", "+3V3", "VSYS", "VBAT_IN",
}
IC_PREFIX = ("U", "IC")


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(8_000_001)
    if len(raw) >= 8_000_000:
        raise ValueError(f"{path}: input exceeds 8 MB")
    return json.loads(raw.decode("utf-8-sig"))


def _is_ic(ref):
    return str(ref or "").upper().startswith(IC_PREFIX)


def _is_cap(ref):
    return str(ref or "").upper().startswith("C")


def _nc_keys(listing):
    keys = set()
    if not isinstance(listing, dict):
        return keys
    components = listing.get("components")
    if not isinstance(components, list):
        result = listing.get("result")
        components = (result or {}).get("components") if isinstance(result, dict) else None
    for component in components or []:
        if not isinstance(component, dict):
            continue
        ref = component.get("designator") or component.get("ref")
        for pin in component.get("pins") or []:
            if isinstance(pin, dict) and pin.get("noConnected"):
                number = pin.get("pinNumber", pin.get("number"))
                if ref is not None and number is not None:
                    keys.add((str(ref), str(number)))
    return keys


def analyze(ir, listing=None):
    if not isinstance(ir, dict):
        raise ValueError("connectivity IR must be an object")
    components = ir.get("components")
    connections = ir.get("connections")
    if not isinstance(components, list) or not isinstance(connections, list):
        raise ValueError("connectivity IR missing components[]/connections[]")

    nets = {n.get("id"): n.get("name", "") for n in ir.get("nets") or []}
    members = {}
    for row in connections:
        members.setdefault(row.get("netId"), []).append(
            (row.get("componentId"), str(row.get("pinNumber", ""))))

    by_id = {c.get("id"): c for c in components}
    nc = _nc_keys(listing)

    findings, checked, covered = [], 0, 0
    for component in components:
        ref = component.get("ref") or component.get("id")
        if not _is_ic(ref):
            continue
        for pin in component.get("pins") or []:
            name = str(pin.get("name", "")).upper().strip()
            if name not in POWER_PIN_NAMES:
                continue
            number = str(pin.get("number", ""))
            if (str(ref), number) in nc:
                continue
            checked += 1
            net_id = None
            for row in connections:
                if (row.get("componentId") == component.get("id")
                        and str(row.get("pinNumber", "")) == number):
                    net_id = row.get("netId")
                    break
            if net_id is None:
                findings.append({
                    "severity": "error", "code": "decap_missing",
                    "message": f"{ref} pin {number} ({name}) 未连接，无去耦",
                })
                continue
            peers = [by_id.get(cid, {}).get("ref") for cid, _ in members.get(net_id, [])
                     if cid != component.get("id")]
            if any(_is_cap(peer) for peer in peers):
                covered += 1
            else:
                findings.append({
                    "severity": "error", "code": "decap_missing",
                    "message": f"{ref} pin {number} ({name}) 所在网 "
                               f"{nets.get(net_id, '')} 没有电容",
                })

    missing = checked - covered
    return {
        "schema": SCHEMA,
        "tool": "sch_decoupling_metrics.py",
        "verdict": "fail" if missing else "pass",
        "metrics": {"decap_missing": missing, "power_pins_checked": checked,
                    "power_pins_covered": covered},
        "findings": findings,
        "note": "启发式：IC 电源脚所在网至少有一个 C* 元件；不做 AC/布局验证",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Decoupling coverage from connectivity IR -> KPI power check")
    ap.add_argument("--input", required=True, help="easycirq sch connectivity JSON")
    ap.add_argument("--list", help="sch list --include-pins JSON (NC exclusion)")
    ap.add_argument("--out", help="write the check report here")
    ap.add_argument("--json", action="store_true", help="print the report")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    args = ap.parse_args(argv)

    try:
        report = analyze(_load(args.input),
                         _load(args.list) if args.list else None)
    except (OSError, ValueError) as exc:
        print(f"sch_decoupling_metrics: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    elif not args.quiet:
        print(f"decoupling: verdict={report['verdict']} metrics={report['metrics']}")
        for finding in report["findings"][:20]:
            print(f"  - {finding['message']}")
    return 1 if report["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
