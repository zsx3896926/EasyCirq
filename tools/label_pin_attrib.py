"""Attribute a net-label box to the pin it was stubbed from, using the wire dump.

Why: the 13 remaining `net_label x pin_number` collisions are cases where the flag
text sits on top of the pin number printed inside the symbol. The fix is to lengthen
that one stub, which means knowing *which* pin the label belongs to — and the label
text itself carries no pin identity. The wire polyline does: it runs pin → flag, so
the far end nearest the label box is that pin's stub.

All inputs are measured artifacts. Nothing here talks to EasyEDA.
"""

from __future__ import annotations

import json
import pathlib
import sys


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def mirror(points):
    return [(x, -y) for x, y in points]


def polylines(dump):
    out = []
    for wire in dump.get("result", {}).get("value", {}).get("wires", []):
        line = wire.get("line")
        if not isinstance(line, list) or len(line) < 4:
            continue
        pts = [(float(line[i]), float(line[i + 1])) for i in range(0, len(line) - 1, 2)]
        out.append({"id": wire.get("id"), "pts": mirror(pts)})
    return out


def box_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def pins(live):
    out = {}
    for comp in live.get("result", {}).get("components", []):
        ref = comp.get("designator")
        if comp.get("componentType") != "part" or not ref:
            continue
        for pin in comp.get("pins") or []:
            out[(ref, str(pin.get("pinNumber")))] = (float(pin["x"]), float(pin["y"]))
    return out


def main():
    texts = load(sys.argv[1])["rows"]
    wires = polylines(load(sys.argv[2]))
    live = load(sys.argv[3])
    pinmap = pins(live)
    # pin positions are schematic (Y-up); text/wire frames here are mirrored
    pinmap_svg = {k: (x, -y) for k, (x, y) in pinmap.items()}

    for row in texts:
        if row["role"] != "net_label":
            continue
        c = box_center(row["bbox"])
        best = None
        for wire in wires:
            for end in (wire["pts"][0], wire["pts"][-1]):
                d = dist(c, end)
                if best is None or d < best[0]:
                    best = (d, wire, end)
        if best is None or best[0] > 30:
            continue
        d, wire, end = best
        far = wire["pts"][-1] if end == wire["pts"][0] else wire["pts"][0]
        pin = None
        for key, pos in pinmap_svg.items():
            if dist(far, pos) < 2.0:
                pin = key
                break
        print("%-12s box=(%.0f,%.0f)-(%.0f,%.0f) wire=%s near=(%.0f,%.0f) far=(%.0f,%.0f) pin=%s"
              % (row["text"], row["bbox"][0], row["bbox"][1], row["bbox"][2], row["bbox"][3],
                 wire["id"], end[0], end[1], far[0], far[1], pin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
