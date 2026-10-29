"""Deterministic fix-plan generator for ACE-review findings.

Consumes an ace snapshot (+ optional review report) and emits concrete,
ordered fix actions.  No EDA, no LLM: the same snapshot always yields the
same plan.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ace_review as ar  # noqa: E402

SCHEMA = "easycirq-ace-fix-plan/v1"
DEFAULT_CAP_VALUE = "100nF"
DEFAULT_PULLUP_VALUE = "4k7"
DEFAULT_SERIES_VALUE = "0R"


def _center(comp):
    b = comp.get("bbox")
    if not b:
        return None
    return ((b["minX"] + b["maxX"]) / 2.0, (b["minY"] + b["maxY"]) / 2.0)


def _on_net(snap, name):
    return [c for c in snap.get("components") or []
            if any(p.get("net") == name for p in c.get("pins") or [])]


def _caps_on(snap, name):
    return [c for c in _on_net(snap, name) if ar.designator_kind(c["ref"]) == "capacitor"]


def _ic_for_power_pin(snap, net):
    for comp in snap.get("components") or []:
        if ar.designator_kind(comp["ref"]) != "ic":
            continue
        for pin in comp.get("pins") or []:
            if pin.get("net") == net and str(pin.get("name") or "").upper() in (
                    "VDD", "VDDIO", "VCC", "AVDD", "DVDD", "PVDD", "VDDA",
                    "VDDD", "VBAT", "VSYS", "VIN"):
                return comp, pin
    return None, None


def _suggested_cap_position(comp):
    c = _center(comp)
    if not c:
        return None
    b = comp["bbox"]
    return [round(c[0], 1), round(b["minY"] - 25.0, 1)]


def _rename_suggestion(snap, net):
    pins = [(comp["ref"], pin) for comp in snap.get("components") or []
            for pin in comp.get("pins") or [] if pin.get("net") == net]
    if not pins:
        return None
    ref, pin = sorted(pins, key=lambda item: (item[0], str(item[1].get("number"))))[0]
    name = str(pin.get("name") or pin.get("number"))
    candidate = ("%s_%s" % (ref, name)).replace("/", "_").replace(" ", "_")
    return candidate.upper()


def build(snapshot):
    report = ar.review(snapshot)
    actions = []
    seen = set()

    def add(rule, action, rationale, refs=None):
        key = (rule, json.dumps(action, sort_keys=True))
        if key in seen:
            return
        seen.add(key)
        actions.append({"id": "fx-%02d" % (len(actions) + 1), "rule": rule,
                        "action": action, "rationale": rationale,
                        "refs": refs or []})

    for finding in report["findings"]:
        rule = finding["rule"]
        msg = finding["message"]
        if rule == "R03-decoupling":
            # message: "<ref> power pin <n> (<NAME>) has no nearby ground cap"
            import re
            m = re.search(r"^(\S+) power pin (\S+) \((\S+)\)", msg)
            if not m:
                continue
            ref, pin_no, pname = m.group(1), m.group(2), m.group(3)
            ic = next((c for c in snapshot["components"] if c["ref"] == ref), None)
            net = None
            if ic:
                for p in ic.get("pins") or []:
                    if str(p.get("number")) == pin_no:
                        net = p.get("net")
            if net:
                caps = _caps_on(snapshot, net)
                pos = _suggested_cap_position(ic) if ic else None
                if caps:
                    closest = min(caps, key=lambda c: math.dist(
                        _center(c) or (0, 0), _center(ic) or (0, 0)))
                    add(rule, {"type": "move_component", "ref": closest["ref"],
                               "target_xy": pos,
                               "target_net": net},
                        "place %s next to %s pin %s (%s)" % (closest["ref"], ref, pin_no, pname))
                else:
                    add(rule, {"type": "add_component", "kind": "capacitor",
                               "value": DEFAULT_CAP_VALUE, "pins": [[net, "GND"]],
                               "near": ref, "target_xy": pos},
                        "add %s from %s to GND next to pin %s" % (DEFAULT_CAP_VALUE, net, pname))
        elif rule == "R02-i2c-pullup":
            import re
            m = re.search(r"'(.*?)'", msg)
            net = m.group(1) if m else None
            if net:
                add(rule, {"type": "add_component", "kind": "resistor",
                           "value": DEFAULT_PULLUP_VALUE, "pins": [[net, "3V3"]],
                           "near": None},
                    "add %s pull-up from %s to 3V3" % (DEFAULT_PULLUP_VALUE, net))
        elif rule == "R04-ground-tie":
            add(rule, {"type": "add_component", "kind": "resistor",
                       "value": DEFAULT_SERIES_VALUE, "pins": [["AGND", "GND"]],
                       "near": None},
                "tie AGND to GND with a single 0R net-tie")
        elif rule == "R06-enable-net":
            import re
            m = re.search(r"^(\S+) enable pin (\S+) \((\S+)\)", msg)
            if m:
                add(rule, {"type": "add_component", "kind": "resistor",
                           "value": DEFAULT_PULLUP_VALUE, "pins": [["3V3", "EN_NET"]],
                           "near": m.group(1)},
                    "give %s enable pin a defined default (pull-up/pull-down)" % m.group(1))
        elif rule == "R07-esd-series":
            import re
            m = re.search(r"net '(.*?)'", msg)
            net = m.group(1) if m else None
            if net:
                add(rule, {"type": "add_component", "kind": "resistor",
                           "value": DEFAULT_SERIES_VALUE, "pins": [[net, "TVS_NET"]],
                           "near": None},
                    "add series/ESD protection on external net %s" % net)
        elif rule == "R08-power-testpoint":
            import re
            m = re.search(r"'(.*?)'", msg)
            if m:
                add(rule, {"type": "add_testpoint", "net": m.group(1)},
                    "add a test point on %s" % m.group(1))
        elif rule == "R09-auto-net-name":
            import re
            m = re.search(r"name '(.*?)'", msg)
            net = m.group(1) if m else None
            if net:
                suggestion = _rename_suggestion(snapshot, net)
                add(rule, {"type": "rename_net", "from": net, "to": suggestion},
                    "rename auto net %s to an intent name" % net)
        elif rule == "R10-titleblock":
            fields = (snapshot.get("titleblock") or {}).get("fields") or {}
            missing = [k for k, v in fields.items() if not str(v or "").strip()]
            if missing:
                add(rule, {"type": "set_titleblock", "fields": {k: "<fill>" for k in missing}},
                    "fill title block fields: %s" % ", ".join(sorted(missing)))
        elif rule == "R01-floating-pin":
            add(rule, {"type": "declare_nc_or_connect", "ref": finding["refs"][0]
                       if finding.get("refs") else None},
                "decide NC vs connect for floating pins: %s" % msg)
        elif rule == "R30-decoupling-count":
            # message: "IC <ref> has <N> power pin(s) but only <M> nearby decoupling cap(s) (need >= <K>)"
            import re
            m = re.search(r"IC (\S+) has (\d+) power pin\(s\) but only (\d+) nearby "
                          r"decoupling cap\(s\) \(need >= (\d+)\)", msg)
            if m:
                ref = m.group(1)
                need = int(m.group(4))
                have = int(m.group(3))
                missing = max(0, need - have)
                ic = next((c for c in snapshot["components"] if c["ref"] == ref), None)
                pos = _suggested_cap_position(ic) if ic else None
                # net from the IC's first power pin
                net = None
                if ic:
                    for pin in ic.get("pins") or []:
                        if str(pin.get("name") or "").upper() in (
                                "VDD", "VDDIO", "VCC", "AVDD", "DVDD", "PVDD",
                                "VDDA", "VDDD", "VBAT", "VSYS", "VIN") and pin.get("net"):
                            net = pin.get("net")
                            break
                for i in range(missing):
                    add(rule, {"type": "add_component", "kind": "capacitor",
                               "value": DEFAULT_CAP_VALUE,
                               "pins": [[net or "?", "GND"]],
                               "near": ref, "target_xy": pos},
                        "add decoupling cap %d/%d for %s (power pins need >= %d)"
                        % (i + 1, missing, ref, need))

    return {
        "schema": SCHEMA,
        "verdict": "fixable" if report["verdict"] != "pass" else "clean",
        "review_verdict": report["verdict"],
        "errors": report["metrics"]["errors"],
        "warnings": report["metrics"]["warnings"],
        "actions": actions,
        "counts": {"actions": len(actions)},
    }


if __name__ == "__main__":
    path = pathlib.Path(sys.argv[1])
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    plan = build(snapshot)
    print(json.dumps(plan, ensure_ascii=False, indent=1))
