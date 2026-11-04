"""Deterministic EDA-autofix playbook from an ACE fix-plan (offline).

Reads an ``easycirq-ace-fix-plan/v1`` document and turns every *supported*
action into an ordered, replayable list of ``easycirq`` CLI command strings
plus per-step ``expected_rule``/``rationale``.  Unsupported actions are kept in
``pending`` with a reason so nothing is silently dropped.

Output schema: ``easycirq-autofix/v1``.
"""

from __future__ import annotations

import json
import pathlib

SCHEMA = "easycirq-autofix/v1"
BIN = "easycirq"

_LIB = "0819f05c4eef4c71ace90d822a990e87"
_DEFAULT_DEVICES = {
    "capacitor": "87bb635d0b2f489a9f60e7cd225beb3c",   # 100nF 0402
    "resistor": "3c6cd697d7c742bc8177ac96f91ce532",   # 4.7k 0402
    "testpoint": "ef0e3a4b3bc942b1af34075e46c8eda8",  # TP
}


def _load_parts(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("parts") or []
    out = {}
    for e in entries:
        key = str(e.get("value") or e.get("name") or e.get("key") or "").lower()
        if key:
            out[key] = e
    return out


def _device(action, parts):
    kind = action.get("kind")
    value = str(action.get("value") or "").lower()
    if kind == "testpoint" or action.get("type") == "add_testpoint":
        return _DEFAULT_DEVICES["testpoint"], "TP"
    if parts and value:
        entry = parts.get(value)
        if entry and entry.get("deviceUuid"):
            return entry["deviceUuid"], value
    if kind in _DEFAULT_DEVICES:
        return _DEFAULT_DEVICES[kind], action.get("value") or kind
    return None, None


def _xy(action):
    pos = action.get("target_xy")
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        return float(pos[0]), float(pos[1])
    if isinstance(pos, dict):
        return float(pos.get("x", 400)), float(pos.get("y", 400))
    return 400.0, 400.0


def _next_designator(prefix, used):
    n = len([d for d in used if d.startswith(prefix)]) + 1
    return "%s%d" % (prefix, n)


def build(fix_plan, *, parts_path=None, snapshot=None):
    parts = _load_parts(parts_path) if parts_path else {}
    steps = []
    pending = []
    used = set()
    for item in fix_plan.get("actions") or []:
        action = item.get("action") if isinstance(item.get("action"), dict) else item
        rule = item.get("rule")
        rationale = item.get("rationale", "")
        typ = action.get("type")
        if typ == "add_component":
            device, value = _device(action, parts)
            if not device:
                pending.append({"id": item.get("id"), "type": typ,
                                "reason": "no device for value %r" % action.get("value")})
                continue
            x, y = _xy(action)
            designator = _next_designator("C" if action.get("kind") == "capacitor"
                                          else "R", used)
            used.add(designator)
            pins = action.get("pins") or []
            cmds = ["%s sch place --lib %s --uuid %s --x %s --y %s --designator %s"
                    % (BIN, _LIB, device, x, y, designator)]
            for index, (net_a, net_b) in enumerate(pins, start=1):
                cmds.append('%s sch connect --pin %s:%d --kind net_label --net "%s"'
                            % (BIN, designator, index, net_a))
            steps.append({"id": item.get("id"), "type": typ, "rule": rule,
                          "rationale": rationale,
                          "commands": cmds})
        elif typ == "add_testpoint":
            device, _ = _device(action, parts)
            x, y = _xy(action)
            designator = _next_designator("TP", used)
            used.add(designator)
            steps.append({"id": item.get("id"), "type": typ, "rule": rule,
                          "rationale": rationale,
                          "commands": [
                              "%s sch place --lib %s --uuid %s --x %s --y %s --designator %s"
                              % (BIN, _LIB, device, x, y, designator),
                              '%s sch connect --pin %s:1 --kind net_label --net "%s"'
                              % (BIN, designator, action.get("net")),
                          ]})
        elif typ == "move_component":
            x, y = _xy(action)
            steps.append({"id": item.get("id"), "type": typ, "rule": rule,
                          "rationale": rationale,
                          "commands": ["%s sch modify --designator %s --x %s --y %s"
                                       % (BIN, action.get("ref"), x, y)]})
        elif typ == "rename_net":
            members = _members_of(snapshot, action.get("from")) if snapshot else []
            cmds = []
            if members:
                for ref, pin in members:
                    cmds.append("%s sch disconnect --pin %s:%s" % (BIN, ref, pin))
                for ref, pin in members:
                    cmds.append('%s sch connect --pin %s:%s --kind net_label --net "%s"'
                                % (BIN, ref, pin, action.get("to")))
            else:
                pending.append({"id": item.get("id"), "type": typ,
                                "reason": "no snapshot members; run tools/net_rename.py first"})
                continue
            steps.append({"id": item.get("id"), "type": typ, "rule": rule,
                          "rationale": rationale, "commands": cmds})
        else:
            pending.append({"id": item.get("id"), "type": typ,
                            "reason": "unsupported action type"})
    return {"schema": SCHEMA, "steps": steps, "pending": pending,
            "counts": {"steps": len(steps),
                       "commands": sum(len(s["commands"]) for s in steps),
                       "pending": len(pending)}}


def _members_of(snapshot, net):
    out = []
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            if pin.get("net") == net:
                out.append([comp["ref"], str(pin.get("number"))])
    out.sort(key=lambda item: (item[0], item[1]))
    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("fix_plan")
    parser.add_argument("--parts-path")
    parser.add_argument("--snapshot")
    parser.add_argument("--emit")
    args = parser.parse_args()
    fix = json.loads(pathlib.Path(args.fix_plan).read_text(encoding="utf-8"))
    snap = (json.loads(pathlib.Path(args.snapshot).read_text(encoding="utf-8"))
            if args.snapshot else None)
    result = build(fix, parts_path=args.parts_path, snapshot=snap)
    if args.emit:
        pathlib.Path(args.emit).write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False))
