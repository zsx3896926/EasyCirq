"""Fit block frames around the *drawn content* of a page, not just part bodies.

The old frame code unioned only part bboxes, so routed wires and the net flags
at their ends stuck out of the dashed frame ("框不住导线").  This module
computes one frame per block from:

* the parts that belong to the block (their rendered bboxes),
* every net flag / net port whose net name belongs to the block,
* every text primitive whose content matches a block net or designator,
* a padding margin, clamped to the sheet, with block-vs-block overlap repair.

Pure/offline: input is plain JSON, output is ``easycirq-sch-frame-spec/v1``.
"""

from __future__ import annotations

import re

_RAIL_RE = re.compile(r"(?i)^(?:\+?\d+V\d?|VBUS\w*|VBAT\w*|VSYS|VIN|VOUT|3V3\w*|5V\w*|GND\w*|AGND|DGND|PGND|VSS)$")


def is_rail(name):
    return bool(_RAIL_RE.match(str(name or "")))

SCHEMA = "easycirq-sch-frame-spec/v1"
DEFAULT_PAD = 16.0
SHEET_W = 1170.0
SHEET_H = 825.0
MARGIN = 10.0
TITLE_BLOCK = (460.0, 10.0, 1160.0, 190.0)   # keepout: bottom-right of the page


def _bbox(value):
    if isinstance(value, dict):
        return (float(value.get("minX", 0)), float(value.get("minY", 0)),
                float(value.get("maxX", 0)), float(value.get("maxY", 0)))
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(float(v) for v in value)
    return None


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def collect(block, parts, flags, texts, connectivity):
    """Return the bbox union of everything visibly belonging to ``block``.

    ``block`` = {"id", "designators": [...], "nets": [...]}.
    ``parts`` = [{"ref", "bbox"}], ``flags`` = [{"name", "bbox"}],
    ``texts`` = [{"content", "bbox"}], ``connectivity`` = {ref: {pin: net}}
    (used to expand the block's net set when it is not given explicitly).
    """
    designators = set(block.get("designators") or [])
    nets = set(block.get("nets") or [])
    for ref in designators:
        for net in (connectivity.get(ref) or {}).values():
            if net:
                nets.add(str(net))
    boxes = [_bbox(p.get("bbox")) for p in parts if p.get("ref") in designators]
    local_nets = {n for n in nets if not is_rail(n)}
    boxes += [_bbox(f.get("bbox")) for f in flags if str(f.get("name")) in local_nets]
    for text in texts:
        content = str(text.get("content") or "")
        if content in local_nets or content in designators:
            boxes.append(_bbox(text.get("bbox")))
    return _union(boxes), sorted(nets)


def _clamp(rect, pad):
    x1 = max(MARGIN, rect[0] - pad)
    y1 = max(MARGIN, rect[1] - pad)
    x2 = min(SHEET_W - MARGIN, rect[2] + pad)
    y2 = min(SHEET_H - MARGIN, rect[3] + pad)
    return [x1, y1, x2, y2]


def _resolve_overlap(frames):
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            a, b = frames[i]["rect"], frames[j]["rect"]
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 0 and oy > 0:
                if ox <= oy:
                    if a[0] > b[0]:
                        a[0] = b[2] + 4
                    else:
                        b[0] = a[2] + 4
                else:
                    if a[1] > b[1]:
                        a[1] = b[3] + 4
                    else:
                        b[1] = a[3] + 4
    return frames


def build(blocks, parts, flags, texts, *, connectivity=None, pad=DEFAULT_PAD,
          fontSize=20, color="#AA00AA"):
    """Compute one dashed frame per block covering all of its drawn content."""
    connectivity = connectivity or {}
    frames, skipped = [], []
    for block in blocks:
        rect, nets = collect(block, parts, flags, texts, connectivity)
        if not rect:
            skipped.append({"id": block.get("id"), "reason": "no visible content"})
            continue
        x1, y1, x2, y2 = _clamp(rect, pad)
        frames.append({
            "id": block.get("id"),
            "title": block.get("title") or block.get("id"),
            "rect": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "titleX": round(x1 + 8, 1),
            "titleY": round(y2 - 8, 1),
            "fontSize": fontSize,
            "color": color,
            "lineType": 1,
            "nets": nets,
            "content_bbox": [round(v, 1) for v in rect],
        })
    frames = _resolve_overlap(frames)
    # keep titles inside their (possibly repaired) rects
    for frame in frames:
        rect = frame["rect"]
        frame["titleX"] = round(rect[0] + 8, 1)
        frame["titleY"] = round(rect[3] - 8, 1)
    return {"schema": SCHEMA, "frames": frames, "skipped": skipped,
            "counts": {"blocks": len(blocks), "frames": len(frames),
                       "skipped": len(skipped)}}


if __name__ == "__main__":
    import json
    import pathlib
    import sys
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(build(data["blocks"], data.get("parts") or [],
                           data.get("flags") or [], data.get("texts") or [],
                           connectivity=data.get("connectivity") or {}),
                     ensure_ascii=False, indent=1))
