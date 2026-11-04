"""Capture real pin geometry from the live page for offline re-layout.

``schematic.components.list --includePins`` exposes every pin's page coordinate
(``x``/``y``) and the rotation that says which way the pin points, which is what
net labels attach to.  Storing the offsets relative to each part's centre lets
the offline relayout place labels exactly where EDA will draw the stubs instead
of approximating them on the part's four edges.

Schema: ``easycirq-pin-geometry/v1``.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import time

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"
SCHEMA = "easycirq-pin-geometry/v1"
SIDE_BY_ROTATION = {0: "right", 90: "top", 180: "left", 270: "bottom"}


def _cli(*args, timeout=300):
    result = subprocess.run([BIN, *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    return (result.stdout or "") + (result.stderr or "")


def _json(text):
    start = text.find("{")
    if start < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:
        return {}


def capture(project, page, window=None):
    """Return the pin geometry of ``page`` (page coordinates -> part offsets)."""
    doc = ["--window", window] if window else []
    _cli("project", "open", "--project-uuid", project, "--allow-discard-unsaved", *doc)
    time.sleep(6)
    _cli("doc", "open", page, *doc)
    time.sleep(4)
    data = _json(_cli("call", "schematic.components.list", "--payload",
                      '{"includePins":true,"includeBBox":true}', *doc))
    parts = {}
    for comp in (data.get("result") or {}).get("components") or []:
        if comp.get("componentType") != "part":
            continue
        ref = comp.get("designator")
        cx = float(comp.get("x") or 0.0)
        cy = float(comp.get("y") or 0.0)
        pins = {}
        for pin in comp.get("pins") or []:
            px = float(pin.get("x") or 0.0)
            py = float(pin.get("y") or 0.0)
            rotation = int(pin.get("rotation") or 0) % 360
            pins[str(pin.get("pinNumber"))] = {
                "dx": round(px - cx, 1), "dy": round(py - cy, 1),
                "rotation": rotation,
                "side": SIDE_BY_ROTATION.get(rotation, "right"),
                "net": pin.get("net"),
            }
        parts[ref] = {"cx": cx, "cy": cy, "pins": pins}
    return {"schema": SCHEMA, "project": project, "page": page,
            "parts": parts, "counts": {"parts": len(parts),
                                       "pins": sum(len(p["pins"]) for p in parts.values())}}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--window")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    asset = capture(args.project, args.page, args.window)
    pathlib.Path(args.out).write_text(
        json.dumps(asset, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(asset["counts"], ensure_ascii=False))
