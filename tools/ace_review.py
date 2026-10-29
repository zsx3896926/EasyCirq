"""Ace-review: deterministic checklist reviewer for schematic snapshots.

The checklist encodes "ace engineer" questions that a senior reviewer asks
before signing off a schematic.  Input is a snapshot JSON (components, pins,
nets, geometry) captured from a live page; output is findings + a verdict.

No EDA, no LLM: every rule is a pure function over the snapshot.
"""

from __future__ import annotations

import math
import re

SCHEMA = "easycirq-ace-snapshot/v1"
REVIEW_SCHEMA = "easycirq-ace-review/v1"

POWER_RE = re.compile(
    r"^(?:\+?[0-9]+V[0-9]*|[A-Z0-9_]*VDD[A-Z0-9_]*|[A-Z0-9_]*VCC[A-Z0-9_]*|"
    r"VBUS[A-Z0-9_]*|VBAT[A-Z0-9_]*|VSYS[A-Z0-9_]*|VIN[A-Z0-9_]*|"
    r"3V3[A-Z0-9_]*|5V[A-Z0-9_]*)$",
    re.IGNORECASE,
)
GROUND_RE = re.compile(r"^(?:A?GND[A-Z0-9_]*|PGND[A-Z0-9_]*|DGND[A-Z0-9_]*|VSS[A-Z0-9_]*)$",
                       re.IGNORECASE)
I2C_RE = re.compile(r"(?i)(?:I2C|SCL|SDA|SCX|SDX|SCLK|SDATA)")
FB_RE = re.compile(r"(?i)^(?:FB|ADJ|VFB|FB_[A-Z0-9_]+|.*_FB)$")
ENABLE_RE = re.compile(r"(?i)^(?:EN[_0-9A-Z#]*|CE#?|SHDN#?)$")
AUTO_NET_RE = re.compile(r"^[A-Z]{1,3}[0-9]+_N[0-9]+$")

DESIGNATOR_KIND = (
    ("C", "capacitor"), ("R", "resistor"), ("L", "inductor"), ("D", "diode"),
    ("Q", "transistor"), ("U", "ic"), ("J", "connector"), ("CN", "connector"),
    ("FB", "ferrite"), ("SW", "switch"), ("Y", "crystal"), ("X", "crystal"),
    ("TP", "testpoint"), ("MK", "ic"), ("F", "fuse"),
)


def designator_kind(ref: str) -> str:
    for prefix, kind in DESIGNATOR_KIND:
        if ref.startswith(prefix):
            return kind
    return "other"


def _pins(snapshot):
    out = {}
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            out[(comp["ref"], str(pin.get("number")))] = pin
    return out


def _nets(snapshot):
    """name -> set of (ref, pin)"""
    out = {}
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if net:
                out.setdefault(net, set()).add((comp["ref"], str(pin.get("number"))))
    return out


def _comp(snapshot, ref):
    for comp in snapshot.get("components") or []:
        if comp["ref"] == ref:
            return comp
    return None


def _bbox_center(comp):
    b = comp.get("bbox") or {}
    if not b:
        return None
    return ((b["minX"] + b["maxX"]) / 2.0, (b["minY"] + b["maxY"]) / 2.0)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def rule_floating_pins(snapshot, findings):
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            if pin.get("net") is None and not pin.get("nc"):
                findings.append({
                    "rule": "R01-floating-pin", "severity": "warn",
                    "message": "%s:%s (%s) is floating" % (
                        comp["ref"], pin.get("number"), pin.get("name")),
                    "refs": [comp["ref"]],
                })


def rule_i2c_pullups(snapshot, findings):
    nets = _nets(snapshot)
    for name, pins in nets.items():
        if not I2C_RE.match(name.replace("-", "_")):
            continue
        has_pull = False
        for ref, _pin in pins:
            comp = _comp(snapshot, ref)
            if comp and designator_kind(ref) == "resistor":
                for p in comp.get("pins") or []:
                    target = p.get("net")
                    if target and target != name and (
                            POWER_RE.match(target.replace("-", "_"))):
                        has_pull = True
        if not has_pull:
            findings.append({
                "rule": "R02-i2c-pullup", "severity": "error",
                "message": "I2C net %r has no pull-up to a power rail" % name,
                "refs": sorted({r for r, _ in pins}),
            })


def rule_decoupling(snapshot, findings, max_dist=180.0):
    nets = _nets(snapshot)
    for comp in snapshot.get("components") or []:
        if designator_kind(comp["ref"]) != "ic":
            continue
        ic_center = _bbox_center(comp)
        for pin in comp.get("pins") or []:
            pname = str(pin.get("name") or "").upper()
            pnet = pin.get("net") or ""
            if pname not in ("VDD", "VDDIO", "VCC", "AVDD", "DVDD", "PVDD",
                             "VDDA", "VDDD", "VBAT", "VSYS", "VIN"):
                continue
            if not (POWER_RE.match(pnet.replace("-", "_")) or GROUND_RE.match(pnet)):
                continue
            ok = False
            for ref, _ in nets.get(pnet, set()):
                if designator_kind(ref) != "capacitor":
                    continue
                cap = _comp(snapshot, ref)
                cpos = _bbox_center(cap)
                if ic_center and cpos and _dist(ic_center, cpos) <= max_dist:
                    for cp in cap.get("pins") or []:
                        other = cp.get("net")
                        if other and GROUND_RE.match(other.replace("-", "_")):
                            ok = True
            if not ok:
                findings.append({
                    "rule": "R03-decoupling", "severity": "error",
                    "message": "%s power pin %s (%s) has no nearby ground cap"
                               % (comp["ref"], pin.get("number"), pname),
                    "refs": [comp["ref"]],
                })


def rule_ground_tie(snapshot, findings):
    """AGND/DGND/PGND must be tied to GND exactly once (0R / net-tie)."""
    comps = snapshot.get("components") or []
    tie_refs = []
    for comp in comps:
        if designator_kind(comp["ref"]) not in ("resistor", "ferrite"):
            continue
        nets = {p.get("net") for p in comp.get("pins") or []}
        if any(n and GROUND_RE.match(n.replace("-", "_")) for n in nets) and \
           any(n and GROUND_RE.match(n.replace("-", "_")) and n.upper().startswith(("A", "D", "P")) for n in nets):
            tie_refs.append(comp["ref"])
    if len(tie_refs) != 1:
        findings.append({
            "rule": "R04-ground-tie", "severity": "error",
            "message": "expected exactly one AGND/DGND-to-GND tie; found %d (%s)"
                       % (len(tie_refs), ", ".join(tie_refs) or "none"),
            "refs": tie_refs,
        })


def rule_feedback_after_cap(snapshot, findings):
    nets = _nets(snapshot)
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            pname = str(pin.get("name") or "")
            pnet = pin.get("net") or ""
            if not (FB_RE.match(pname) or FB_RE.match(pnet)):
                continue
            # feedback net must see at least one capacitor to ground
            has_cap = any(designator_kind(ref) == "capacitor"
                          for ref, _ in nets.get(pnet, set()))
            if not has_cap:
                findings.append({
                    "rule": "R05-feedback-cap", "severity": "warn",
                    "message": "%s:%s feedback net %r has no capacitor (check "
                               "feedback taken after output cap)"
                               % (comp["ref"], pin.get("number"), pnet),
                    "refs": [comp["ref"]],
                })


def rule_enable_pull(snapshot, findings):
    for comp in snapshot.get("components") or []:
        if designator_kind(comp["ref"]) != "ic":
            continue
        for pin in comp.get("pins") or []:
            pname = str(pin.get("name") or "")
            if not ENABLE_RE.match(pname):
                continue
            if pin.get("net") is None:
                findings.append({
                    "rule": "R06-enable-net", "severity": "error",
                    "message": "%s enable pin %s (%s) is unconnected"
                               % (comp["ref"], pin.get("number"), pname),
                    "refs": [comp["ref"]],
                })


def rule_esd_connector(snapshot, findings):
    nets = _nets(snapshot)
    for comp in snapshot.get("components") or []:
        if designator_kind(comp["ref"]) != "connector":
            continue
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if not net:
                continue
            members = nets.get(net, set())
            guarded = any(designator_kind(ref) in ("diode", "resistor", "ferrite")
                          for ref, _ in members)
            if not guarded:
                findings.append({
                    "rule": "R07-esd-series", "severity": "warn",
                    "message": "connector %s pin %s net %r has no series/ESD part"
                               % (comp["ref"], pin.get("number"), net),
                    "refs": [comp["ref"]],
                })


def rule_power_testpoint(snapshot, findings):
    nets = _nets(snapshot)
    for name, pins in nets.items():
        if not POWER_RE.match(name.replace("-", "_")):
            continue
        if name.upper().startswith(("VIN", "VBUS", "VDD", "VBAT", "VSYS", "5V")) or \
           name.upper().startswith(("3V3", "+3V3", "+5V")):
            if not any(designator_kind(ref) == "testpoint" for ref, _ in pins):
                findings.append({
                    "rule": "R08-power-testpoint", "severity": "warn",
                    "message": "power net %r has no test point" % name,
                    "refs": sorted({r for r, _ in pins})[:4],
                })


def rule_net_naming(snapshot, findings):
    auto = []
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if net and AUTO_NET_RE.match(net):
                auto.append(net)
    for name in sorted(set(auto))[:20]:
        findings.append({
            "rule": "R09-auto-net-name", "severity": "warn",
            "message": "auto-generated net name %r (rename to intent name)" % name,
            "refs": [],
        })


def rule_titleblock(snapshot, findings):
    fields = (snapshot.get("titleblock") or {}).get("fields") or {}
    missing = [k for k, v in fields.items() if not str(v or "").strip()]
    if missing:
        findings.append({
            "rule": "R10-titleblock", "severity": "warn",
            "message": "title block fields empty: %s" % ", ".join(sorted(missing)[:6]),
            "refs": [],
        })


def review(snapshot):
    findings = []
    rule_floating_pins(snapshot, findings)
    rule_i2c_pullups(snapshot, findings)
    rule_decoupling(snapshot, findings)
    rule_ground_tie(snapshot, findings)
    rule_feedback_after_cap(snapshot, findings)
    rule_enable_pull(snapshot, findings)
    rule_esd_connector(snapshot, findings)
    rule_power_testpoint(snapshot, findings)
    rule_net_naming(snapshot, findings)
    rule_titleblock(snapshot, findings)
    errors = [f for f in findings if f["severity"] == "error"]
    return {
        "schema": REVIEW_SCHEMA,
        "verdict": "pass" if not errors else "blocked",
        "findings": findings,
        "metrics": {
            "errors": len(errors),
            "warnings": len(findings) - len(errors),
            "rules": sorted({f["rule"] for f in findings}),
        },
    }
