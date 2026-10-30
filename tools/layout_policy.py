"""Readability as layout-time constraints, not a post-hoc review.

Reviewing a finished page and then reworking it is the expensive path.  This
module turns every readability rule into *planner input*: a plan is checked
before it is written, and the checker returns the **fixes to apply while
planning** (canonical net names, test-point annotations, column order), so the
layout loop can iterate to clean without redrawing the page.

Schema: ``easycirq-layout-policy/v1``.
"""

from __future__ import annotations

import re

SCHEMA = "easycirq-layout-policy/v1"
DECOUPLING_DISTANCE = 120.0

#: functional column order (left -> right); unknown roles land in the core column
ROLE_ORDER = ("input", "conversion", "core", "interface")
INPUT_NETS = ("VIN", "VBUS", "VBAT", "USB")
CONVERSION_NETS = ("VOUT", "VSYS", "+5V", "5V", "+3V3", "3V3", "BOOST", "LDO")
INTERFACE_REF_PREFIX = ("J", "TP", "D")
CORE_REF_PREFIX = ("U", "MK", "Q")
INTERNAL_SUFFIX = re.compile(r"_(?:L\d+|L3B_AU|AU|D\d)$")
GENERIC_NET = re.compile(r"^(?:NET|N)\d+$")
RAIL_LIKE = re.compile(r"^(?:\+?\d+V\d?|VBUS|VBAT|VSYS|VIN|VOUT)")


def canonical_net(net):
    """Strip internal layer/domain markers from a rail-like name."""
    if not net:
        return net
    if RAIL_LIKE.match(net) and INTERNAL_SUFFIX.search(net):
        return INTERNAL_SUFFIX.sub("", net)
    return net


def rename_plan(snapshot):
    """Net -> canonical name, for nets that would otherwise fail R31."""
    mapping = {}
    seen = set()
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if not net or net in seen:
                continue
            seen.add(net)
            canonical = canonical_net(net)
            if canonical != net:
                mapping[net] = canonical
    return mapping


def _role(comp):
    ref = str(comp.get("ref", ""))
    nets = {p.get("net") for p in comp.get("pins") or [] if p.get("net")}
    if any(str(n).startswith(INPUT_NETS) for n in nets):
        return "input"
    if any(str(n).startswith(CONVERSION_NETS) for n in nets) and ref.startswith(CORE_REF_PREFIX):
        return "conversion"
    if ref.startswith(INTERFACE_REF_PREFIX):
        return "interface"
    if ref.startswith(CORE_REF_PREFIX):
        return "conversion"
    return "core"


def column_order(snapshot):
    """Reference designators grouped into the left-to-right functional columns."""
    columns = {name: [] for name in ROLE_ORDER}
    for comp in snapshot.get("components") or []:
        columns[_role(comp)].append(comp.get("ref"))
    return columns


def testpoint_annotations(snapshot):
    """Suggested annotation for each test point (signal + rail it sits on)."""
    annotations = {}
    for comp in snapshot.get("components") or []:
        ref = str(comp.get("ref", ""))
        if not ref.startswith("TP"):
            continue
        nets = [p.get("net") for p in comp.get("pins") or [] if p.get("net")]
        signal = nets[0] if nets else "?"
        annotations[ref] = "%s: %s" % (ref, signal)
    return annotations


def _centre(comp):
    b = comp.get("bbox") or {}
    try:
        return ((float(b["minX"]) + float(b["maxX"])) / 2.0,
                (float(b["minY"]) + float(b["maxY"])) / 2.0)
    except (KeyError, TypeError, ValueError):
        return None


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _nets(comp):
    return {p.get("net") for p in comp.get("pins") or [] if p.get("net")}


def validate(snapshot, placements, *, decoupling_distance=DECOUPLING_DISTANCE):
    """Check a *planned* page and return violations plus the planner fixes.

    ``placements`` = ``{ref: {"x", "y"}}`` from the layout plan (not the EDA).
    """
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or []}
    violations = []
    fixes = {"rename_nets": rename_plan(snapshot),
             "annotate_testpoints": testpoint_annotations(snapshot)}

    # R31 naming: report only nets that cannot be canonicalised automatically
    for comp in snapshot.get("components") or []:
        for net in _nets(comp):
            if net and GENERIC_NET.match(net):
                violations.append({"rule": "R31", "net": net,
                                   "message": "generic network name needs a manual "
                                              "functional name"})

    # R32 decoupling distance, measured on the planned positions
    caps = [c for c in snapshot.get("components") or []
            if str(c.get("ref", "")).startswith("C")]
    for comp in snapshot.get("components") or []:
        ref = str(comp.get("ref", ""))
        if not ref.startswith(CORE_REF_PREFIX):
            continue
        centre = placements.get(ref)
        if not centre:
            continue
        rails = {n for n in _nets(comp) if n and RAIL_LIKE.match(n)}
        for rail in sorted(rails):
            nearest = None
            for cap in caps:
                if rail not in _nets(cap):
                    continue
                cap_place = placements.get(cap.get("ref"))
                if not cap_place:
                    continue
                distance = _dist((centre["x"], centre["y"]),
                                 (cap_place["x"], cap_place["y"]))
                nearest = distance if nearest is None else min(nearest, distance)
            if nearest is None or nearest > decoupling_distance:
                violations.append({"rule": "R32", "ref": ref, "net": rail,
                                   "message": "plan puts the nearest %s decoupling %.0f "
                                              "units away (limit %.0f) - place it next "
                                              "to the IC in the same sub-module"
                                              % (rail, nearest or -1, decoupling_distance)})

    # R33 signal flow: input column must sit left of the interface column
    columns = column_order(snapshot)
    xs = {}
    for role, refs in columns.items():
        points = [placements[r] for r in refs if r in placements]
        if points:
            xs[role] = sum(p["x"] for p in points) / len(points)
    if "input" in xs and "interface" in xs and xs["input"] > xs["interface"]:
        violations.append({"rule": "R33",
                           "message": "plan puts inputs right of interfaces "
                                      "(input x=%.0f > interface x=%.0f) - reorder the "
                                      "columns input->conversion->core->interface"
                                      % (xs["input"], xs["interface"])})

    # R36 designator continuity
    families = {}
    for comp in snapshot.get("components") or []:
        match = re.match(r"([A-Za-z]+)(\d+)", str(comp.get("ref", "")))
        if match:
            families.setdefault(match.group(1), []).append(int(match.group(2)))
    for family, numbers in families.items():
        numbers.sort()
        gaps = [b for a, b in zip(numbers, numbers[1:]) if b - a > 1]
        if gaps:
            violations.append({"rule": "R36", "family": family,
                               "message": "designator family %s has gaps before %s - "
                                          "reallocate contiguous numbers at plan time"
                                          % (family, ", ".join(str(g) for g in gaps))})

    return {"schema": SCHEMA, "violations": violations, "fixes": fixes,
            "columns": {role: refs for role, refs in columns.items() if refs},
            "metrics": {"violations": len(violations)},
            "verdict": "pass" if not violations else "review"}


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA}, ensure_ascii=False))
