"""Capture an offline ACE-review snapshot from the live schematic page.

No mutations: only read-only actions (components, connectivity, title block).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"


def cli(*args):
    r = subprocess.run([BIN, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    text = (r.stdout or "") + (r.stderr or "")
    start = text.find("{")
    if start < 0:
        raise RuntimeError("no JSON in output: %s" % text[:300])
    return json.loads(text[start:]), text


def build(page_uuid: str):
    listing, _ = cli("call", "schematic.components.list",
                     "--payload", '{"includeBBox":true,"includePins":true}')
    comps_raw = [c for c in (listing.get("result") or {}).get("components") or []
                 if c.get("componentType") == "part"]
    conn, _ = cli("sch", "connectivity")
    nets = {n["id"]: {"name": n.get("name"), "role": n.get("role"),
                      "scope": n.get("scope")} for n in conn.get("nets") or []}
    refs = {c["id"]: c["ref"] for c in conn.get("components") or []}
    pin_names = {}
    for c in conn.get("components") or []:
        ref = c.get("ref")
        for p in c.get("pins") or []:
            pin_names[(ref, str(p.get("number")))] = p.get("name")
    pin_net = {}
    for cn in conn.get("connections") or []:
        ref = refs.get(cn.get("componentId"))
        if ref is None:
            continue
        pin_net[(ref, str(cn.get("pinNumber")))] = nets.get(cn.get("netId"), {}).get("name")

    conn_pins = {}
    for c in conn.get("components") or []:
        ref = c.get("ref")
        conn_pins[ref] = c.get("pins") or []

    components = []
    for c in comps_raw:
        ref = c.get("designator")
        b = c.get("bbox") or {}
        pins = []
        for p in conn_pins.get(ref) or []:
            number = str(p.get("number"))
            pins.append({
                "number": number,
                "name": p.get("name"),
                "net": pin_net.get((ref, number)),
            })
        components.append({
            "ref": ref,
            "mpn": (c.get("component") or {}).get("name"),
            "value": (c.get("device") or {}).get("name"),
            "bbox": {k: b.get(k) for k in ("minX", "minY", "maxX", "maxY")} if b else None,
            "pins": pins,
        })
    titleblock = {}
    try:
        tb, _ = cli("sch", "titleblock-get")
        fields = ((tb.get("result") or {}).get("fields")
                  or (tb.get("result") or {}).get("fieldValues") or {})
        titleblock = {"fields": fields}
    except Exception:
        titleblock = {"fields": {}}
    return {
        "schema": "easycirq-ace-snapshot/v1",
        "page": page_uuid,
        "components": sorted(components, key=lambda c: c["ref"]),
        "nets": [{"name": v["name"], "role": v.get("role")} for v in nets.values()],
        "titleblock": titleblock,
    }


if __name__ == "__main__":
    page = sys.argv[1]
    out = pathlib.Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    snap = build(page)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print("snapshot", page, "components", len(snap["components"]), "->", out)
