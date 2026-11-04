"""Subdivide a functional group into smaller sub-modules (finer frames).

Four big frames hide empty space and mix unrelated parts.  This module splits a
group by electrical role instead:

* every core part (U / MK / Q / Y) becomes its own sub-module together with the
  passives that share a **non-rail** net with it (programming resistors, FB
  dividers, coupling caps),
* passives that only touch power/ground rails become a ``去耦/滤波`` module,
* groups without a core part split by reference family (J / TP / D / R / C ...),
  e.g. an interface group becomes 排针 / 测试点 / ESD 保护.

Rails (GND, 3V3, 5V, VBATT, VBUS, VSYS ...) are ignored so they do not glue
everything into one blob.  Output schema: ``easycirq-subdivision/v1``.
"""

from __future__ import annotations

import re

SCHEMA = "easycirq-subdivision/v1"
_RAIL_RE = re.compile(
    r"(?i)^(?:\+?\d+V\d?|VBUS\w*|VBAT\w*|VSYS|VIN|VOUT|3V3\w*|5V\w*|GND\w*|AGND|DGND|PGND|VSS)$")
CORE_HEADS = ("U", "MK", "Q", "Y")
RAIL_NAMES = {"GND", "AGND", "DGND", "PGND", "VSS"}


def is_rail(name):
    return bool(_RAIL_RE.match(str(name or "")))


def _head(ref):
    return "".join(ch for ch in str(ref) if ch.isalpha())


def _nets(comp):
    return {str(p.get("net")) for p in comp.get("pins") or []
            if p.get("net") and not is_rail(p.get("net"))}


def subdivide(snapshot, group):
    """Return the sub-modules of ``group`` (list of {id,title,designators})."""
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or [] if c.get("ref")}
    designators = [ref for ref in group.get("designators") or [] if ref in by_ref]
    if not designators:
        return []
    cores = [ref for ref in designators if _head(ref) in CORE_HEADS]
    others = [ref for ref in designators if ref not in cores]
    net_of = {ref: _nets(by_ref[ref]) for ref in designators}
    base = group.get("id") or "group"
    subs = []

    if cores:
        for core in cores:
            attached = [ref for ref in others
                        if net_of[ref] & net_of[core]]
            others = [ref for ref in others if ref not in attached]
            subs.append({"id": "%s::%s" % (base, core),
                         "title": "核心 %s" % core,
                         "designators": [core] + attached})
        by_family = {}
        for ref in others:
            by_family.setdefault(_head(ref), []).append(ref)
        for head, refs in sorted(by_family.items()):
            title = "去耦/滤波" if head in ("C", "L", "FB") else "%s 组" % head
            subs.append({"id": "%s::%s" % (base, head), "title": title,
                         "designators": refs})
    else:
        by_family = {}
        for ref in designators:
            by_family.setdefault(_head(ref), []).append(ref)
        names = {"J": "排针/接口", "TP": "测试点", "D": "ESD 保护",
                 "R": "电阻", "C": "电容", "L": "电感", "FB": "磁珠", "SW": "开关"}
        for head, refs in sorted(by_family.items()):
            subs.append({"id": "%s::%s" % (base, head),
                         "title": names.get(head, "%s 组" % head),
                         "designators": refs})
    return _merge_tiny(subs)


def _merge_tiny(subs, min_parts=2):
    """Fold 1-part leftovers into the biggest sibling so tiny cards do not
    waste a frame and its margins."""
    if len(subs) <= 1:
        return subs
    changed = True
    while changed:
        changed = False
        for sub in list(subs):
            if len(sub["designators"]) >= min_parts:
                continue
            siblings = [s for s in subs if s is not sub]
            if not siblings:
                break
            target = max(siblings, key=lambda s: len(s["designators"]))
            target["designators"].extend(sub["designators"])
            subs.remove(sub)
            changed = True
            break
    return subs


def subdivide_all(snapshot, groups):
    """Flatten every group into its sub-modules (drops empty groups)."""
    subs = []
    for group in groups:
        subs.extend(subdivide(snapshot, group))
    return subs


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA}, ensure_ascii=False))
