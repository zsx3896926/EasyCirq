"""Readability checks for finished schematics (engineer-facing lint).

The ace rules cover electrical correctness; these checks cover what makes a
schematic *readable*: net naming, decoupling proximity, signal flow, test-point
labelling, functional-group contiguity and designator continuity.

All checks are snapshot-only (parts, pins, nets, bboxes), deterministic and
EDA-free.  Schema: ``easycirq-readability/v1``.
"""

from __future__ import annotations

import re

SCHEMA = "easycirq-readability/v1"
RAIL_PREFIXES = ("+3V3", "3V3", "+5V", "5V", "VBUS", "VBAT", "VSYS", "VIN", "GND", "AGND")
INTERNAL_SUFFIX = re.compile(r"_(?:L\d+|L3B_AU|AU|D\d)$")
GENERIC_NET = re.compile(r"^(?:NET|N)\d+$|^unnamed|^\\$")
LOGIC_NET = re.compile(r"(?:EN|PG|FAULT|INT|BOOT|RST|RESET|CHG|STAT|PGOOD)\b", re.I)

DECOUPLING_DISTANCE = 120.0
MIN_DECOUPLING = 1


def _pins(comp):
    return comp.get("pins") or []


def _nets(comp):
    return {p.get("net") for p in _pins(comp) if p.get("net")}


def _centre(comp):
    b = comp.get("bbox") or {}
    try:
        return ((float(b["minX"]) + float(b["maxX"])) / 2.0,
                (float(b["minY"]) + float(b["maxY"])) / 2.0)
    except (KeyError, TypeError, ValueError):
        return None


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def check_net_naming(snapshot):
    """Internal suffixes / generic names / odd characters in net names."""
    findings = []
    seen = set()
    for comp in snapshot.get("components") or []:
        for pin in _pins(comp):
            net = pin.get("net")
            if not net or net in seen:
                continue
            seen.add(net)
            if INTERNAL_SUFFIX.search(net):
                findings.append({"rule": "R31", "severity": "warning", "net": net,
                                 "message": "network name carries an internal suffix "
                                            "(layer/domain marker) - rename to the "
                                            "rail or signal it really is"})
            elif GENERIC_NET.match(net):
                findings.append({"rule": "R31", "severity": "warning", "net": net,
                                 "message": "auto-generated network name - give it a "
                                            "functional name"})
            elif re.search(r"\s", net):
                findings.append({"rule": "R31", "severity": "error", "net": net,
                                 "message": "network name contains whitespace"})
    return findings


def check_decoupling(snapshot):
    """Every IC power pin should have a nearby capacitor on the same rail."""
    findings = []
    parts = snapshot.get("components") or []
    caps = [c for c in parts if str(c.get("ref", "")).startswith("C")]
    for comp in parts:
        ref = str(comp.get("ref", ""))
        if not ref.startswith(("U", "MK", "Q")):
            continue
        rails = {net for net in _nets(comp) if net and net.startswith(
            ("+3V3", "3V3", "+5V", "5V", "VBUS", "VBAT", "VSYS"))}
        centre = _centre(comp)
        if not rails or centre is None:
            continue
        for rail in sorted(rails):
            near = [cap for cap in caps if rail in _nets(cap)
                    and _centre(cap) and _dist(_centre(cap), centre) <= DECOUPLING_DISTANCE]
            if len(near) < MIN_DECOUPLING:
                findings.append({"rule": "R32", "severity": "warning", "ref": ref,
                                 "net": rail,
                                 "message": "IC rail %s has no decoupling capacitor "
                                            "within %.0f units" % (rail, DECOUPLING_DISTANCE)})
    return findings


def check_signal_flow(snapshot):
    """Input rails should sit left of output rails (left-to-right power flow)."""
    inputs, outputs = [], []
    for comp in snapshot.get("components") or []:
        centre = _centre(comp)
        if centre is None:
            continue
        nets = _nets(comp)
        if any(n.startswith(("VIN", "VBUS", "VBAT")) for n in nets if n):
            inputs.append(centre[0])
        if any(n.startswith(("VOUT", "VSYS", "+5V", "5V", "+3V3")) for n in nets if n):
            outputs.append(centre[0])
    findings = []
    if inputs and outputs:
        mean_in = sum(inputs) / len(inputs)
        mean_out = sum(outputs) / len(outputs)
        if mean_out < mean_in:
            findings.append({"rule": "R33", "severity": "warning",
                             "message": "power flow runs right-to-left "
                                        "(input mean x=%.0f, output mean x=%.0f) - "
                                        "mirror the page so inputs enter on the left"
                                        % (mean_in, mean_out)})
    return findings


def check_testpoints(snapshot):
    """Test points must say what they are (value/annotation), not just TPn."""
    findings = []
    for comp in snapshot.get("components") or []:
        ref = str(comp.get("ref", ""))
        if not ref.startswith("TP"):
            continue
        value = str(comp.get("value") or "").strip()
        if not value or value == ref:
            findings.append({"rule": "R34", "severity": "warning", "ref": ref,
                             "message": "test point %s has no annotation - state the "
                                        "signal and expected level" % ref})
    return findings


def check_functional_groups(snapshot):
    """Parts sharing nets should form spatial clusters, not interleave."""
    parts = snapshot.get("components") or []
    parent = {c.get("ref"): c.get("ref") for c in parts}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    owner = {}
    for comp in parts:
        for net in _nets(comp):
            if not net or net.startswith(("GND", "AGND", "DGND")):
                continue
            if net in owner:
                union(owner[net], comp.get("ref"))
            else:
                owner[net] = comp.get("ref")
    clusters = {}
    for comp in parts:
        clusters.setdefault(find(comp.get("ref")), []).append(comp)
    boxes = []
    for refs in clusters.values():
        centres = [c for c in (_centre(x) for x in refs) if c]
        if len(centres) < 2:
            continue
        xs = [c[0] for c in centres]
        ys = [c[1] for c in centres]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    findings = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if (min(a[2], b[2]) > max(a[0], b[0])
                    and min(a[3], b[3]) > max(a[1], b[1])):
                findings.append({"rule": "R35", "severity": "warning",
                                 "message": "two functional clusters overlap on page - "
                                            "keep one function per area"})
    return findings


def check_designators(snapshot):
    """Designator families should be contiguous inside a functional block."""
    families = {}
    for comp in snapshot.get("components") or []:
        ref = str(comp.get("ref", ""))
        match = re.match(r"([A-Za-z]+)(\d+)", ref)
        if match:
            families.setdefault(match.group(1), []).append(int(match.group(2)))
    findings = []
    for family, numbers in families.items():
        numbers.sort()
        gaps = [b for a, b in zip(numbers, numbers[1:]) if b - a > 1]
        if gaps:
            findings.append({"rule": "R36", "severity": "info", "family": family,
                             "message": "%s numbering has gaps (%s) - allocate "
                                        "contiguous designators per block"
                                        % (family, ", ".join("..%d" % g for g in gaps))})
    return findings


CHECKS = (check_net_naming, check_decoupling, check_signal_flow,
          check_testpoints, check_functional_groups, check_designators)


def review(snapshot):
    findings = []
    for check in CHECKS:
        findings.extend(check(snapshot))
    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {"schema": SCHEMA, "findings": findings,
            "metrics": {"errors": errors, "warnings": warnings,
                        "info": len(findings) - errors - warnings},
            "verdict": "review" if (errors or warnings) else "pass"}


if __name__ == "__main__":
    import json
    import sys
    snapshot = json.loads(open(sys.argv[1], encoding="utf-8").read())
    print(json.dumps(review(snapshot), ensure_ascii=False, indent=1))
