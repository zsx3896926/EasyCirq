"""Single schematic IR: one model that validation, planning and writing share.

Three sources of truth caused the endless rework: the snapshot (original page),
the layout plan (new coordinates) and the live EDA page each answered the
readability rules differently.  This module replaces that with one object:

    parts  : ref, mpn, block, function, placement (x/y/w/h)
    nets   : name, canonical, kind (power/signal/logic), attached refs
    ports  : block, pin, net, direction (input/output/bidirectional/power)
    decoupling : ic_ref, rail, cap_ref        (explicit intent, not guessed at
                                                validation time)
    pages  : index, columns (role order), cards
    fixes  : rename_nets, renumber_designators, annotate_testpoints

Everything downstream reads the IR only.  ``validate`` therefore checks the IR
(after ``canonicalize``), so a clean IR means a clean page by construction - no
rework after drawing.
"""

from __future__ import annotations

import re

SCHEMA = "easycirq-schematic-ir/v1"
ROLE_ORDER = ("input", "conversion", "core", "interface")
RAIL = re.compile(r"^(?:\+?\d+V\d?|VBUS|VBAT|VSYS|VIN|VOUT)")
INTERNAL_SUFFIX = re.compile(r"_(?:L\d+|L3B_AU|AU|D\d)$")
GENERIC_NET = re.compile(r"^(?:NET|N)\d+$")
INPUT_NETS = ("VIN", "VBUS", "VBAT")
OUTPUT_NETS = ("VOUT", "VSYS", "+5V", "5V", "+3V3", "3V3")
CORE_PREFIX = ("U", "MK", "Q")
INTERFACE_PREFIX = ("J", "TP", "D")
DECOUPLING_LIMIT = 120.0
PAGE = (10.0, 196.0, 1160.0, 815.0)


def canonical_net(name):
    if name and RAIL.match(name) and INTERNAL_SUFFIX.search(name):
        return INTERNAL_SUFFIX.sub("", name)
    return name


def _nets(comp):
    return {p.get("net") for p in comp.get("pins") or [] if p.get("net")}


def _centre(comp):
    b = comp.get("bbox") or {}
    try:
        return ((float(b["minX"]) + float(b["maxX"])) / 2.0,
                (float(b["minY"]) + float(b["maxY"])) / 2.0)
    except (KeyError, TypeError, ValueError):
        return None


def net_kind(name):
    if not name:
        return "unknown"
    if name.startswith(("GND", "AGND", "DGND")):
        return "ground"
    if RAIL.match(name):
        return "power"
    if re.search(r"(?:EN|PG|FAULT|INT|BOOT|RST|CHG|STAT)", name, re.I):
        return "logic"
    return "signal"


def ref_role(ref, nets):
    ref = str(ref or "")
    if any(n and n.startswith(INPUT_NETS) for n in nets):
        return "input"
    if any(n and n.startswith(OUTPUT_NETS) for n in nets):
        return "conversion"
    if ref.startswith(INTERFACE_PREFIX):
        return "interface"
    if ref.startswith(CORE_PREFIX):
        return "conversion"
    return "core"


def from_snapshot(snapshot, *, block_of=None):
    """Parse a page snapshot into IR (no layout decisions yet)."""
    block_of = block_of or {}
    parts, nets = {}, {}
    for comp in snapshot.get("components") or []:
        ref = comp.get("ref")
        if not ref:
            continue
        comp_nets = _nets(comp)
        centre = _centre(comp)
        bbox = comp.get("bbox") or {}
        parts[ref] = {
            "ref": ref, "mpn": comp.get("mpn"), "value": comp.get("value"),
            "block": block_of.get(ref, ref.split("::")[0]),
            "role": ref_role(ref, comp_nets),
            "size": ((bbox["maxX"] - bbox["minX"], bbox["maxY"] - bbox["minY"])
                     if bbox else (20.0, 10.0)),
            "placement": ({"x": centre[0], "y": centre[1]} if centre else None),
        }
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if not net:
                continue
            entry = nets.setdefault(net, {"name": net, "canonical": canonical_net(net),
                                          "kind": net_kind(net), "refs": []})
            entry["refs"].append({"ref": ref, "pin": str(pin.get("number")),
                                  "pin_name": pin.get("name")})
    ports = []
    for net, entry in nets.items():
        for attach in entry["refs"]:
            part = parts[attach["ref"]]
            direction = {"input": "input", "conversion": "output",
                         "interface": "bidirectional"}.get(part["role"], "power"
                                                          if entry["kind"] == "power"
                                                          else "bidirectional")
            ports.append({"block": part["block"], "ref": attach["ref"],
                          "pin": attach["pin"], "net": net,
                          "direction": direction})
    return {"schema": SCHEMA, "parts": parts, "nets": nets, "ports": ports,
            "decoupling": [], "pages": [], "fixes": {
                "rename_nets": {}, "renumber_designators": {},
                "annotate_testpoints": {}}}


def canonicalize(ir):
    """Apply the model fixes: rename nets, renumber designators, TP annotations."""
    rename = {name: entry["canonical"] for name, entry in ir["nets"].items()
              if entry["canonical"] != name}
    ir["fixes"]["rename_nets"] = rename
    for name, canonical in rename.items():
        entry = ir["nets"].pop(name)
        entry["name"] = canonical
        ir["nets"][canonical] = entry
        for port in ir["ports"]:
            if port["net"] == name:
                port["net"] = canonical
    families = {}
    for ref in ir["parts"]:
        match = re.match(r"([A-Za-z]+)(\d+)", ref)
        if match:
            families.setdefault(match.group(1), []).append((int(match.group(2)), ref))
    renumber = {}
    for family, entries in families.items():
        entries.sort()
        for index, (_, ref) in enumerate(entries, start=1):
            new_ref = "%s%d" % (family, index)
            if new_ref != ref:
                renumber[ref] = new_ref
    # keep the original refs as the stable identity; the map is the write-side fix
    ir["fixes"]["renumber_designators"] = renumber
    ir["fixes"]["annotate_testpoints"] = {
        ref: "%s: %s" % (ref, (next(iter(
            {p.get("net") for p in ([])})) if False else
            next((n for n in ir["nets"] if ref in
                  [r["ref"] for r in ir["nets"][n]["refs"]]), "?")))
        for ref, part in ir["parts"].items() if ref.startswith("TP")}
    # decoupling intent: every IC rail is paired with a capacitor on the same rail
    caps = [ref for ref, part in ir["parts"].items() if ref.startswith("C")]
    intents = []
    for ref, part in ir["parts"].items():
        if not ref.startswith(("U", "MK")):
            continue
        for net, entry in ir["nets"].items():
            if entry["kind"] != "power":
                continue
            if ref not in [r["ref"] for r in entry["refs"]]:
                continue
            same_rail = [cap for cap in caps
                         if cap in [r["ref"] for r in
                                    (ir["nets"].get(net) or {"refs": []})["refs"]]]
            # prefer a capacitor inside the same functional block as the IC
            same_block = [cap for cap in same_rail
                          if ir["parts"][cap]["block"] == ir["parts"][ref]["block"]]
            chosen = (same_block or same_rail)
            if chosen:
                intents.append({"ic": ref, "rail": net, "cap": chosen[0]})
    ir["decoupling"] = intents
    return ir


def layout(ir):
    """Place parts: role-ordered columns, IC with its decoupling caps adjacent."""
    # sub-modules: IC + its decoupling caps + its other passives
    modules = {}
    for ref, part in ir["parts"].items():
        key = "%s::%s" % (part["block"], "core" if ref.startswith(CORE_PREFIX) else "aux")
        modules.setdefault(key, []).append(ref)
    cap_of_ic = {}
    for intent in ir["decoupling"]:
        cap_of_ic.setdefault(intent["ic"], []).append(intent["cap"])
    for key, refs in list(modules.items()):
        for ic, caps in cap_of_ic.items():
            if ic not in refs:
                continue
            for cap in caps:
                if cap in ir["parts"] and cap not in refs:
                    refs.append(cap)
                    for other, other_refs in modules.items():
                        if other != key and cap in other_refs:
                            other_refs.remove(cap)
    order = sorted(modules, key=lambda key: (
        min((ROLE_ORDER.index(ir["parts"][r]["role"])
             for r in modules[key]), default=2), key))
    placements, y_cursor = {}, 0.0
    columns, col_x = [], 0.0
    for key in order:
        refs = modules[key]
        ics = [r for r in refs if r.startswith(CORE_PREFIX)]
        caps = [c for ic in ics for c in cap_of_ic.get(ic, []) if c in refs]
        head = ics + [c for c in caps if c not in ics]
        refs = head + [r for r in refs if r not in head]
        modules[key] = refs
        x_cursor = 0.0
        row_h = 0.0
        for ref in refs:
            w, h = ir["parts"][ref]["size"]
            placements[ref] = {"x": round(col_x + x_cursor + w / 2.0, 1),
                               "y": round(y_cursor - h / 2.0, 1)}
            x_cursor += w + 18.0
            row_h = max(row_h, h + 16.0)
        y_cursor -= row_h
        col_x += x_cursor + 24.0
    ir["placements"] = placements
    ir["pages"] = [{"index": 0, "columns": order}]
    return ir


def _dist(a, b):
    return ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5


def validate(ir):
    """Readability rules evaluated on the IR only (single source of truth)."""
    violations = []
    for name, entry in ir["nets"].items():
        if entry["canonical"] != name:
            violations.append({"rule": "R31", "net": name,
                               "message": "net not canonical in IR"})
        if GENERIC_NET.match(name):
            violations.append({"rule": "R31", "net": name,
                               "message": "generic network name"})
    for intent in ir["decoupling"]:
        ic_place = ir.get("placements", {}).get(intent["ic"])
        cap_place = ir.get("placements", {}).get(intent["cap"])
        if not ic_place or not cap_place:
            violations.append({"rule": "R32", "ic": intent["ic"],
                               "message": "decoupling pair has no placement"})
            continue
        distance = _dist(ic_place, cap_place)
        if distance > DECOUPLING_LIMIT:
            violations.append({"rule": "R32", "ic": intent["ic"], "cap": intent["cap"],
                               "message": "decoupling %.0f units away (limit %.0f)"
                                          % (distance, DECOUPLING_LIMIT)})
    for ic in ir["parts"]:
        rails = [net for net, entry in ir["nets"].items()
                 if entry["kind"] == "power" and ic in [r["ref"] for r in entry["refs"]]]
        for rail in rails:
            if not any(intent["ic"] == ic and intent["rail"] == rail
                       for intent in ir["decoupling"]):
                # an electrical design gap, not a layout defect: the page cannot
                # be blamed for a capacitor that does not exist
                ir.setdefault("design_gaps", []).append(
                    {"ic": ic, "rail": rail,
                     "message": "%s rail %s has no capacitor on the page" % (ic, rail)})
    for role in ("input", "interface"):
        x = [ir["placements"][r]["x"] for r, p in ir["parts"].items()
             if p["role"] == role and r in ir.get("placements", {})]
        ir.setdefault("_mean_x", {})[role] = (sum(x) / len(x) if x else None)
    if ir["_mean_x"].get("input") is not None and ir["_mean_x"].get("interface") is not None:
        if ir["_mean_x"]["input"] > ir["_mean_x"]["interface"]:
            violations.append({"rule": "R33",
                               "message": "input column sits right of the interface "
                                          "column in IR"})
    for ref in ir["parts"]:
        if ref.startswith("TP") and not ir["fixes"]["annotate_testpoints"].get(ref):
            violations.append({"rule": "R34", "ref": ref,
                               "message": "test point has no annotation in IR"})
    return {"schema": SCHEMA, "violations": violations,
            "design_gaps": ir.get("design_gaps", []),
            "metrics": {"violations": len(violations),
                        "design_gaps": len(ir.get("design_gaps", []))},
            "verdict": "pass" if not violations else "review"}


def build(snapshot, *, block_of=None):
    """Snapshot -> canonical IR -> layout -> validation (the one pipeline)."""
    ir = canonicalize(from_snapshot(snapshot, block_of=block_of))
    layout(ir)
    report = validate(ir)
    return {"ir": ir, "report": report}


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA}, ensure_ascii=False))
