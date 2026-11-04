"""Capture an offline ACE-review snapshot from the live schematic page.

No mutations: only read-only actions (components, connectivity, title block).

The snapshot is the only input of ``tools/ace_review.py``.  Newer rules
(R11-R30) can use optional fields when the host exposes them; when a field is
missing the reviewer emits an ``info`` finding with the word "unknown" instead
of guessing or crashing.  Optional component fields:

    value, mpn, type, voltage, polarity, page, i2c_address, keyed,
    params{dropout_mv, voltage, ...}

Optional snapshot fields:

    net_voltage{net: volts}, nets_by_page{page: [net, ...]},
    cross_page_nets[...]

Multi-page consistency (R28) needs a merged snapshot: use :func:`merge` on
per-page snapshots captured with :func:`build`.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"

SCHEMA = "easycirq-ace-snapshot/v1"

_PROP_KEYS = {
    "value": ("value", "valuetext", "devicevalue", "comment", "commenttext"),
    "mpn": ("manufacturer part", "manufacturer part number", "mpn", "part number",
            "supplier part", "lcsc part", "device"),
    "type": ("type", "component type", "kind", "category"),
    "polarity": ("polarity", "orientation", "polarity/orientation"),
    "voltage": ("voltage", "rated voltage", "voltage rating", "vrating"),
    "page": ("page", "sheet", "page number"),
    "i2c_address": ("i2c address", "i2c_address", "address", "addr"),
    "keyed": ("keyed", "polarized", "reverse protected", "reverse-protected"),
    "dropout_mv": ("dropout", "dropout_mv", "dropout voltage"),
}


def _properties(raw):
    """Best-effort property map from a host component record."""
    for key in ("properties", "attributes", "props", "attrs"):
        value = raw.get(key)
        if isinstance(value, dict):
            return {str(k).lower(): v for k, v in value.items()}
        if isinstance(value, list):
            out = {}
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("key") or item.get("id")
                if name:
                    out[str(name).lower()] = item.get("value", item.get("valueText"))
            if out:
                return out
    return {}


def _prop(props, names):
    for name in names:
        if name in props:
            return props[name]
    for key, value in props.items():
        for name in names:
            if name in key:
                return value
    return None


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "keyed")
    return None


def infer_net_voltage(name):
    """Infer a supply voltage from a net name (deterministic heuristic)."""
    if not name:
        return None
    text = str(name).replace("-", "_")
    m = re.match(r"^\+?([0-9]+)V([0-9])$", text, re.IGNORECASE)
    if m:  # 3V3 -> 3.3, 1V8 -> 1.8
        return float(m.group(1)) + float("0." + m.group(2))
    m = re.match(r"^\+?([0-9]+(?:\.[0-9]+)?)V$", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    if text.upper() in ("VBUS", "USB_VBUS", "5V0"):
        return 5.0
    return None


_PLACEHOLDER_RE = re.compile(r"^=\{[^}]*\}$")


def _real_or_none(value):
    """EasyEDA stores unresolved parameters as '={Value}' placeholders."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _PLACEHOLDER_RE.match(text):
        return None
    return text


def _component(raw, conn_pins, pin_net):
    """Normalize one component; optional fields are only added when present."""
    props = _properties(raw)
    ref = raw.get("designator") or raw.get("ref")
    bbox = raw.get("bbox") or {}
    pins = []
    for p in conn_pins.get(ref) or []:
        number = str(p.get("number"))
        entry = {
            "number": number,
            "name": p.get("name"),
            "net": pin_net.get((ref, number)),
        }
        nc = p.get("nc")
        if nc is None:
            nc = p.get("noConnect")
        if nc is not None:
            entry["nc"] = bool(nc)
        pins.append(entry)
    comp = {
        "ref": ref,
        "mpn": _real_or_none((raw.get("component") or {}).get("name"))
        or _real_or_none(_prop(props, _PROP_KEYS["mpn"])),
        "value": _real_or_none((raw.get("device") or {}).get("name"))
        or _real_or_none(_prop(props, _PROP_KEYS["value"])),
        "bbox": {k: bbox.get(k) for k in ("minX", "minY", "maxX", "maxY")} if bbox else None,
        "pins": pins,
    }
    for field in ("type", "polarity", "voltage", "page", "i2c_address"):
        value = _prop(props, _PROP_KEYS[field])
        if value not in (None, ""):
            comp[field] = value
    keyed = _prop(props, _PROP_KEYS["keyed"])
    if keyed is not None:
        converted = _as_bool(keyed)
        if converted is not None:
            comp["keyed"] = converted
    params = {}
    for field in ("dropout_mv", "voltage"):
        value = _prop(props, _PROP_KEYS[field])
        if value not in (None, ""):
            params[field] = value
    if params:
        comp["params"] = params
    return comp


_FLOATING_RE = re.compile(r"floating-pin\s+(\S+)\s+\d+\s.*?\[([^\]]+)\]")


def _floating_pins():
    """Pins that sch check reports as genuinely floating (not NC-marked)."""
    code, text = _cli_raw("sch", "check")
    out = set()
    for line in text.splitlines():
        m = _FLOATING_RE.search(line)
        if m:
            ref = m.group(1)
            for pin in m.group(2).split(","):
                out.add((ref, pin.strip()))
    return out


def _cli_raw(*args):
    r = subprocess.run([BIN, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def build(page_uuid: str):
    listing, _ = cli("call", "schematic.components.list",
                     "--payload", '{"includeBBox":true,"includePins":true}')
    comps_raw = [c for c in (listing.get("result") or {}).get("components") or []
                 if c.get("componentType") == "part"]
    conn, _ = cli("sch", "connectivity")
    nets = {n["id"]: {"name": n.get("name"), "role": n.get("role"),
                      "scope": n.get("scope")} for n in conn.get("nets") or []}
    refs = {c["id"]: c["ref"] for c in conn.get("components") or []}
    pin_net = {}
    for cn in conn.get("connections") or []:
        ref = refs.get(cn.get("componentId"))
        if ref is None:
            continue
        pin_net[(ref, str(cn.get("pinNumber")))] = nets.get(cn.get("netId"), {}).get("name")

    conn_pins = {}
    for c in conn.get("components") or []:
        conn_pins[c.get("ref")] = c.get("pins") or []

    components = [_component(raw, conn_pins, pin_net) for raw in comps_raw]
    floating = _floating_pins()
    for comp in components:
        for pin in comp.get("pins") or []:
            if pin.get("net") is None and "nc" not in pin:
                pin["nc"] = (comp["ref"], str(pin.get("number"))) not in floating
    net_names = sorted({v["name"] for v in nets.values() if v.get("name")})
    net_voltage = {name: infer_net_voltage(name) for name in net_names}
    net_voltage = {k: v for k, v in net_voltage.items() if v is not None}
    titleblock = {}
    try:
        tb, _ = cli("sch", "titleblock-get")
        fields = ((tb.get("result") or {}).get("fields")
                  or (tb.get("result") or {}).get("fieldValues") or {})
        titleblock = {"fields": fields}
    except Exception:
        titleblock = {"fields": {}}
    return {
        "schema": SCHEMA,
        "page": page_uuid,
        "components": sorted(components, key=lambda c: str(c.get("ref"))),
        "nets": [{"name": v["name"], "role": v.get("role")} for v in nets.values()],
        "net_voltage": net_voltage,
        "titleblock": titleblock,
    }


def merge(snapshots):
    """Merge per-page snapshots into one multi-page snapshot (pure function).

    Adds ``nets_by_page`` and ``cross_page_nets`` so R28 can check cross-page
    consistency without reading the host again.  Same-named nets appearing on
    more than one page are declared cross-page automatically.
    """
    pages = []
    components = []
    page_nets = {}
    net_voltage = {}
    titleblock = {"fields": {}}
    for index, snapshot in enumerate(snapshots or []):
        if not isinstance(snapshot, dict):
            continue
        page = str(snapshot.get("page") or index + 1)
        pages.append(page)
        names = set()
        for net in snapshot.get("nets") or []:
            if isinstance(net, dict) and net.get("name"):
                names.add(str(net["name"]))
        for comp, pin in _snapshot_pins(snapshot):
            net = pin.get("net")
            if net:
                names.add(str(net))
        for comp in snapshot.get("components") or []:
            if not isinstance(comp, dict):
                continue
            merged = dict(comp)
            merged.setdefault("page", page)
            components.append(merged)
        page_nets[page] = sorted(names)
        for name, value in (snapshot.get("net_voltage") or {}).items():
            net_voltage.setdefault(str(name), value)
        if not (titleblock.get("fields")) and (snapshot.get("titleblock") or {}).get("fields"):
            titleblock = {"fields": dict(snapshot["titleblock"]["fields"])}
    where = {}
    for page, names in page_nets.items():
        for name in names:
            where.setdefault(name, set()).add(page)
    cross_page = sorted(name for name, pageset in where.items() if len(pageset) > 1)
    components.sort(key=lambda c: (str(c.get("page")), str(c.get("ref"))))
    return {
        "schema": SCHEMA,
        "page": "merged:" + ",".join(pages),
        "components": components,
        "nets": [{"name": name} for name in sorted(where)],
        "net_voltage": net_voltage,
        "nets_by_page": page_nets,
        "cross_page_nets": cross_page,
        "titleblock": titleblock,
    }


def _snapshot_pins(snapshot):
    for comp in snapshot.get("components") or []:
        if not isinstance(comp, dict):
            continue
        for pin in comp.get("pins") or []:
            if isinstance(pin, dict):
                yield comp, pin


def cli(*args):
    r = subprocess.run([BIN, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    text = (r.stdout or "") + (r.stderr or "")
    start = text.find("{")
    if start < 0:
        raise RuntimeError("no JSON in output: %s" % text[:300])
    return json.loads(text[start:]), text


if __name__ == "__main__":
    page = sys.argv[1]
    out = pathlib.Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    snap = build(page)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print("snapshot", page, "components", len(snap["components"]), "->", out)
