"""Deterministic net-integrity audit over an ACE snapshot (offline, no EDA).

The pin-level reviewer (``tools/ace_review.py``) only sees a pin's *net name*;
it cannot tell a real connection from a net that has exactly one member.  A
single-member net means the connection is **dead**: the pin is attached to a
name that nothing else joins.

Schema: ``easycirq-net-integrity/v1``.
"""

from __future__ import annotations

import re

SCHEMA = "easycirq-net-integrity/v1"

# deterministic dead-net remediation classes
_INTERFACE_RE = re.compile(
    r"^(?:I2S|AUDIO|I2C|SPI|SD_|MCU_|UART|CAN|USB|EXT_|DAC_|ADC_|SPK_|MIC)", re.I)
_ENABLE_RE = re.compile(r"(?:^|_)EN(?:ABLE)?$|_EN$", re.I)
_AUTO_RE2 = re.compile(r"^TP_")
_AUTO_RE = re.compile(r"^[A-Z]{1,3}\d+_N\d+$")
_NORMALISE_RE = re.compile(r"[^0-9a-z]")
_USUAL = {"3v3": "3.3v", "5v": "5v", "1v8": "1.8v", "1v2": "1.2v"}


def _members(snapshot):
    out = {}
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if not net:
                continue
            out.setdefault(net, []).append(
                {"ref": comp.get("ref"), "pin": str(pin.get("number")),
                 "name": pin.get("name")})
    for net in out:
        out[net].sort(key=lambda m: (str(m["ref"]), str(m["pin"])))
    return out


def _normalise(name):
    text = _NORMALISE_RE.sub("", str(name).lower())
    return _USUAL.get(text, text)


def classify(net, ref, pin_name=None):
    """Classify a dead net into a deterministic remediation action type."""
    name = str(net or "")
    pin = str(pin_name or "")
    if _ENABLE_RE.search(name) or _ENABLE_RE.search(pin):
        return "connect_driver"
    if _INTERFACE_RE.match(name) or _INTERFACE_RE.match(pin):
        return "port_ize"
    if _AUTO_RE2.match(name):
        return "remove_dangling_part_or_connect"
    return "review_connectivity"


def audit(snapshot):
    members = _members(snapshot)
    findings = []

    for net in sorted(members):
        pins = members[net]
        if len(pins) == 1:
            pin = pins[0]
            findings.append({
                "code": "single-pin-net",
                "severity": "error",
                "net": net,
                "ref": pin["ref"],
                "pin": pin["pin"],
                "message": "net %r has exactly one member pin (%s:%s); the "
                           "connection is dead" % (net, pin["ref"], pin["pin"]),
            })

    # net-name variants: same normalised name, different spelling across nets
    groups = {}
    for net in members:
        if _AUTO_RE.match(net):
            continue
        groups.setdefault(_normalise(net), set()).add(net)
    for normalised, names in sorted(groups.items()):
        if len(names) > 1:
            findings.append({
                "code": "net-name-variant",
                "severity": "warn",
                "nets": sorted(names),
                "message": "net name variants %s normalise to %r; unify them or "
                           "the two nets stay separate" % (sorted(names), normalised),
            })

    actions = []
    for finding in findings:
        if finding["code"] != "single-pin-net":
            continue
        pin_name = None
        for comp in snapshot.get("components") or []:
            if comp.get("ref") != finding["ref"]:
                continue
            for pin in comp.get("pins") or []:
                if str(pin.get("number")) == finding["pin"]:
                    pin_name = pin.get("name")
        kind = classify(finding["net"], finding["ref"], pin_name)
        rationale = {
            "port_ize": "interface net %r is not exposed: add a net port / "
                        "connector so it reaches the rest of the system"
                        % finding["net"],
            "connect_driver": "control net %r has no driver: connect it to the "
                              "MCU/control source" % finding["net"],
            "remove_dangling_part_or_connect": "dangling part on %r: connect it "
                                               "or remove the part" % finding["net"],
            "review_connectivity": "net %r is dead: connect it to its intended "
                                   "counterpart" % finding["net"],
        }[kind]
        actions.append({"id": "nf-%02d" % (len(actions) + 1),
                        "net": finding["net"], "ref": finding["ref"],
                        "pin": finding["pin"], "type": kind,
                        "rationale": rationale})

    counts = {"errors": sum(1 for f in findings if f["severity"] == "error"),
              "warnings": sum(1 for f in findings if f["severity"] == "warn")}
    return {
        "schema": SCHEMA,
        "nets": len(members),
        "findings": findings,
        "actions": actions,
        "counts": counts,
        "verdict": "blocked" if counts["errors"] else "pass",
    }


if __name__ == "__main__":
    import json
    import pathlib
    import sys
    snapshot = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(audit(snapshot), ensure_ascii=False, indent=1))
