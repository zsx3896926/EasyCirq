"""Deterministic auto-net renamer over an ACE snapshot (offline, no EDA).

EasyEDA / block-apply often leaves nets named like ``C11_N9`` (auto-generated).
Those names carry no design intent, so this planner derives an intent name from
the pins that sit on the net and groups every member so the rename is atomic.

Output schema: ``easycirq-net-rename/v1``.
"""

from __future__ import annotations

import re

SCHEMA = "easycirq-net-rename/v1"
AUTO_RE = re.compile(r"^[A-Z]{1,3}[0-9]+_N[0-9]+$")


def _pins(snapshot):
    for comp in snapshot.get("components") or []:
        for pin in comp.get("pins") or []:
            yield comp, pin


def _members(snapshot):
    """net -> sorted list of (ref, pin_number)"""
    out = {}
    for comp, pin in _pins(snapshot):
        net = pin.get("net")
        if not net:
            continue
        out.setdefault(net, []).append((comp["ref"], str(pin.get("number"))))
    for net in out:
        out[net].sort(key=lambda item: (item[0], item[1]))
    return out


def _suggest_name(snapshot, members):
    """Deterministic intent name from the first (sorted) member pin.

    Prefers a meaningful pin name (e.g. U1_AVDD); falls back to U1_11.
    """
    def pin_name_of(ref, number):
        for comp in snapshot.get("components") or []:
            if comp.get("ref") != ref:
                continue
            for pin in comp.get("pins") or []:
                if str(pin.get("number")) == str(number):
                    return pin.get("name")
        return None

    for ref, number in members:
        pin_name = pin_name_of(ref, number)
        if pin_name and str(pin_name).strip() not in ("", "1", "2"):
            return _sanitize("%s_%s" % (ref, pin_name))
    ref, number = members[0]
    return _sanitize("%s_%s" % (ref, number))


def _sanitize(text):
    name = re.sub(r"[^0-9A-Za-z_]", "_", str(text))
    name = re.sub(r"_+", "_", name).strip("_").upper()
    return name or "NET"


def plan(snapshot):
    members = _members(snapshot)
    renames = []
    used = set()
    for net in sorted(members):
        if not AUTO_RE.match(net):
            continue
        base = _suggest_name(snapshot, members[net])
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = "%s_%d" % (base, suffix)
            suffix += 1
        used.add(candidate)
        renames.append({
            "from": net,
            "to": candidate,
            "members": [[ref, pin] for ref, pin in members[net]],
        })
    return {
        "schema": SCHEMA,
        "renames": renames,
        "stats": {"auto_nets": len(renames),
                  "pins_renamed": sum(len(r["members"]) for r in renames)},
    }


if __name__ == "__main__":
    import json
    import pathlib
    import sys
    snapshot = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(plan(snapshot), ensure_ascii=False, indent=1))
