"""Analysis-only before/after SVG overlays.

The files are explicitly labelled ``analysis_not_official_export``.  They are a
debugging/readability aid generated from geometry, not an EDA export, not a
visual acceptance test and not a replacement for the official schematic image.
"""
from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .model import Input, Rect

SVG_NS = "http://www.w3.org/2000/svg"
BANNER = "analysis_not_official_export"
COLORS = {
    "page": "#333333",
    "usable": "#888888",
    "title": "#cc4444",
    "zone": "#aa8844",
    "component": "#666666",
    "wire": "#444444",
    "fixed_text": "#999999",
    "movable": "#2266cc",
    "changed": "#118844",
    "hard": "#cc2222",
    "soft": "#cc8800",
    "background": "#ffffff",
}


def _screen_y(raw_y: float, page: Rect) -> float:
    return page.y1 - raw_y


def _rect_attrs(box: Rect, page: Rect) -> Dict[str, str]:
    x = box.x0 - page.x0
    y = _screen_y(box.y1, page)
    return {"x": _fmt(x), "y": _fmt(y), "width": _fmt(box.width),
            "height": _fmt(box.height)}


def _fmt(value: float) -> str:
    number = round(float(value), 6)
    if number == int(number):
        return str(int(number))
    return f"{number:.6f}".rstrip("0").rstrip(".")


def _text(x: float, y: float, content: str, **attrs: str) -> ET.Element:
    element = ET.Element(f"{{{SVG_NS}}}text", {"x": _fmt(x), "y": _fmt(y)})
    element.set("font-family", "monospace")
    for key, value in attrs.items():
        element.set(key.replace("_", "-"), value)
    element.text = content
    return element


def _short(content: str, limit: int = 42) -> str:
    content = "".join(ch if ch >= " " else " " for ch in content)
    return content if len(content) <= limit else content[:limit - 1] + "…"


def write_analysis_svg(inp: Input, planned_bboxes: Mapping[str, Rect],
                       path: str | Path, label: str,
                       violations: Optional[Sequence[Mapping[str, Any]]] = None,
                       before_bboxes: Optional[Mapping[str, Rect]] = None) -> Dict[str, Any]:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    page = inp.page.bbox
    width = page.width
    height = page.height
    root = ET.Element(f"{{{SVG_NS}}}svg", {
        "xmlns": SVG_NS,
        "width": _fmt(width),
        "height": _fmt(height),
        "viewBox": f"0 0 {_fmt(width)} {_fmt(height)}",
        "role": "img",
        "aria-label": f"{BANNER}: annotation layout analysis overlay",
    })
    title = ET.SubElement(root, f"{{{SVG_NS}}}title")
    title.text = f"{label} — {BANNER}"
    # background
    ET.SubElement(root, f"{{{SVG_NS}}}rect", {
        "x": "0", "y": "0", "width": _fmt(width), "height": _fmt(height),
        "fill": COLORS["background"],
    })
    # page + usable area
    ET.SubElement(root, f"{{{SVG_NS}}}rect", {
        **_rect_attrs(page, page), "fill": "none",
        "stroke": COLORS["page"], "stroke-width": "2",
    })
    ET.SubElement(root, f"{{{SVG_NS}}}rect", {
        **_rect_attrs(inp.page.usable_bbox, page), "fill": "none",
        "stroke": COLORS["usable"], "stroke-width": "1", "stroke-dasharray": "6 4",
    })
    if inp.page.title_block is not None:
        ET.SubElement(root, f"{{{SVG_NS}}}rect", {
            **_rect_attrs(inp.page.title_block, page), "fill": "#ffeeee",
            "fill-opacity": "0.7", "stroke": COLORS["title"], "stroke-width": "1",
        })
        ET.SubElement(root, f"{{{SVG_NS}}}text", {
            "x": _fmt(inp.page.title_block.x0 - page.x0 + 4),
            "y": _fmt(_screen_y(inp.page.title_block.y1, page) + 14),
            "font-family": "monospace", "font-size": "11", "fill": COLORS["title"],
        }).text = "TITLE BLOCK keep-out"
    for zone in inp.page.zones:
        ET.SubElement(root, f"{{{SVG_NS}}}rect", {
            **_rect_attrs(zone.bbox, page), "fill": "none",
            "stroke": COLORS["zone"], "stroke-width": "1", "stroke-dasharray": "8 6",
        })
        ET.SubElement(root, f"{{{SVG_NS}}}text", {
            "x": _fmt(zone.bbox.x0 - page.x0 + 4),
            "y": _fmt(_screen_y(zone.bbox.y1, page) + 12),
            "font-family": "monospace", "font-size": "10", "fill": COLORS["zone"],
        }).text = _short(zone.name, 30)
    # component bodies
    for component in inp.components:
        ET.SubElement(root, f"{{{SVG_NS}}}rect", {
            **_rect_attrs(component.bbox, page), "fill": "#f2f2f2",
            "stroke": COLORS["component"], "stroke-width": "1",
        })
    # wires
    for wire in inp.wires:
        points = " ".join(
            f"{_fmt(point[0] - page.x0)},{_fmt(_screen_y(point[1], page))}"
            for point in wire.points)
        element = ET.SubElement(root, f"{{{SVG_NS}}}polyline", {
            "points": points, "fill": "none", "stroke": COLORS["wire"],
            "stroke-width": "1",
        })
        element.set("data-wire", wire.id)
    # fixed text
    for text in inp.fixed_texts:
        ET.SubElement(root, f"{{{SVG_NS}}}rect", {
            **_rect_attrs(text.bbox, page), "fill": "none",
            "stroke": COLORS["fixed_text"], "stroke-width": "0.6",
        })
    # conflict boxes
    conflict_ids = set()
    for item in violations or ():
        for identity in item.get("objects") or ():
            conflict_ids.add(identity)
    # annotations (before ghost + planned)
    for ann in inp.annotations:
        planned = planned_bboxes.get(ann.id, ann.current.bbox)
        before = (before_bboxes or {}).get(ann.id, ann.current.bbox)
        moved = (abs(planned.x0 - before.x0) > 1e-9
                 or abs(planned.y0 - before.y0) > 1e-9)
        conflict = any(ann.id in (item.get("annotation_ids") or ())
                       or ann.id in (item.get("objects") or ())
                       for item in violations or ())
        color = COLORS["hard"] if conflict else (
            COLORS["changed"] if moved else COLORS["movable"])
        if moved:
            ghost = ET.SubElement(root, f"{{{SVG_NS}}}rect", {
                **_rect_attrs(before, page), "fill": "none",
                "stroke": COLORS["movable"], "stroke-width": "0.8",
                "stroke-dasharray": "3 3", "opacity": "0.7",
            })
            ghost.set("data-before", ann.id)
        box = ET.SubElement(root, f"{{{SVG_NS}}}rect", {
            **_rect_attrs(planned, page), "fill": "none",
            "stroke": color, "stroke-width": "1.6" if (moved or conflict) else "1",
        })
        box.set("data-annotation", ann.id)
        label_text = f"{ann.role}:{_short(ann.content, 24)}"
        tx = planned.x0 - page.x0
        ty = _screen_y(planned.y1, page) - 2
        ET.SubElement(root, f"{{{SVG_NS}}}text", {
            "x": _fmt(tx), "y": _fmt(ty), "font-family": "monospace",
            "font-size": "7", "fill": color,
        }).text = label_text
        if moved:
            ET.SubElement(root, f"{{{SVG_NS}}}line", {
                "x1": _fmt(before.center[0] - page.x0),
                "y1": _fmt(_screen_y(before.center[1], page)),
                "x2": _fmt(planned.center[0] - page.x0),
                "y2": _fmt(_screen_y(planned.center[1], page)),
                "stroke": COLORS["changed"], "stroke-width": "1",
                "stroke-dasharray": "2 2",
            })
    # banner + legend
    ET.SubElement(root, f"{{{SVG_NS}}}rect", {
        "x": "0", "y": "0", "width": _fmt(width), "height": "36",
        "fill": "#fff8d8", "stroke": "#aa8800", "stroke-width": "1",
    })
    ET.SubElement(root, f"{{{SVG_NS}}}text", {
        "x": "8", "y": "15", "font-family": "monospace", "font-size": "13",
        "font-weight": "bold", "fill": "#663300",
    }).text = f"{BANNER} — {label}"
    ET.SubElement(root, f"{{{SVG_NS}}}text", {
        "x": "8", "y": "30", "font-family": "monospace", "font-size": "10",
        "fill": "#663300",
    }).text = ("analysis overlay from geometry only; NOT an official EDA export, "
               "no rendering/visual/electrical acceptance")
    legend_y = height - 40
    legend = [
        ("page/usable", COLORS["usable"]),
        ("component bbox", COLORS["component"]),
        ("wire", COLORS["wire"]),
        ("movable text", COLORS["movable"]),
        ("changed", COLORS["changed"]),
        ("conflict", COLORS["hard"]),
    ]
    for index, (name, color) in enumerate(legend):
        x = 10 + index * 150
        ET.SubElement(root, f"{{{SVG_NS}}}line", {
            "x1": _fmt(x), "y1": _fmt(legend_y), "x2": _fmt(x + 24),
            "y2": _fmt(legend_y), "stroke": color, "stroke-width": "3",
        })
        ET.SubElement(root, f"{{{SVG_NS}}}text", {
            "x": _fmt(x + 30), "y": _fmt(legend_y + 4),
            "font-family": "monospace", "font-size": "9", "fill": "#333333",
        }).text = name
    payload = ET.tostring(root, encoding="unicode", xml_declaration=False)
    data = ('<?xml version="1.0" encoding="UTF-8"?>\n' + payload + "\n").encode("utf-8")
    tmp = output.with_name(output.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, output)
    validation = validate_svg(output)
    current = {ann.id: ann.current.bbox for ann in inp.annotations}
    moved = sum(1 for identity, box in planned_bboxes.items()
                if identity in current
                and (abs(box.x0 - current[identity].x0) > 1e-9
                     or abs(box.y0 - current[identity].y0) > 1e-9))
    return {"path": str(output), "bytes": len(data), "validation": validation,
            "label": BANNER, "moved": moved, "host_execution": "not_executed"}


def validate_svg(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"status": "invalid", "reason": f"cannot read: {exc}"}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return {"status": "invalid", "reason": f"XML parse error: {exc}"}
    tag = root.tag.rsplit("}", 1)[-1]
    if tag != "svg":
        return {"status": "invalid", "reason": f"root element is {tag!r}, not svg"}
    width = _number(root.get("width"))
    height = _number(root.get("height"))
    view_box = root.get("viewBox", "").split()
    if not width or not height or width <= 0 or height <= 0:
        return {"status": "invalid", "reason": "width/height missing or non-positive"}
    if len(view_box) != 4 or any(_number(item) is None for item in view_box):
        return {"status": "invalid", "reason": "viewBox missing or malformed"}
    elements = list(root.iter())
    shapes = sum(1 for item in elements
                 if item.tag.rsplit("}", 1)[-1] in ("rect", "line", "polyline", "text"))
    texts = [item.text or "" for item in elements
             if item.tag.rsplit("}", 1)[-1] == "text"]
    if not any(BANNER in item for item in texts):
        return {"status": "invalid", "reason": f"banner {BANNER!r} missing"}
    if len(texts) < 3 or shapes < 5:
        return {"status": "invalid", "reason": "overlay has too few elements"}
    return {"status": "ok", "bytes": len(raw), "elements": len(elements),
            "shapes": shapes, "render_basic_check": "xml+geometry only; "
            "raster preview NOT RUN (no rasterizer guaranteed)"}


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
