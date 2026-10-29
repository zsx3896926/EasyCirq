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

    counts = {"errors": sum(1 for f in findings if f["severity"] == "error"),
              "warnings": sum(1 for f in findings if f["severity"] == "warn")}
    return {
        "schema": SCHEMA,
        "nets": len(members),
        "findings": findings,
        "counts": counts,
        "verdict": "blocked" if counts["errors"] else "pass",
    }


if __name__ == "__main__":
    import json
    import pathlib
    import sys
    snapshot = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(audit(snapshot), ensure_ascii=False, indent=1))
