"""Re-layout a finished page: compact groups, label-aware spacing, label sides.

Why: post-hoc additions (interface headers, test points, ESD guards, extra
decoupling) were dropped into free coordinates after the fact, so they hang off
the block frames and their net labels collide.  Keeping the original wide spread
also cannot fit a label-aware plan, so groups must be re-packed compactly.

Pipeline (all offline, deterministic):

1. ``compact_group``   — parts of one group are packed into a compact grid
                         (ICs first, then passives, sorted by ref);
2. ``build_modules``   — each group becomes a layout module whose size is the
                         compact footprint and whose halo comes from its net
                         label text (``regroup_plan.label_halo``);
3. ``plan_page``       — ``layout_engine.plan_project`` places the modules on the
                         A4 sheet with those halos;
4. ``place_parts``     — module zone origin + compact offset gives every part an
                         absolute position on the 5-unit grid;
5. ``label_sides``     — every net label gets a stub side chosen by
                         ``label_solver`` (8 directions, collision avoiding).

Output schema: ``easycirq-page-relayout/v1``.  ``render_preview`` draws the plan
with Pillow so the result can be inspected before touching EDA.
"""

from __future__ import annotations

import math
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "layout2"))
import label_solver  # noqa: E402
import layout_engine  # noqa: E402
import balanced_pack  # noqa: E402
import regroup_plan  # noqa: E402
import text_metrics  # noqa: E402

SCHEMA = "easycirq-page-relayout/v1"
GRID = 5.0
PART_GAP = 30.0
LABEL_SIZE = 10.0
STUB = 20.0


def _snap(value):
    return round(round(float(value) / GRID) * GRID, 1)


def _bbox(comp):
    b = comp.get("bbox") or {}
    try:
        return (float(b["minX"]), float(b["minY"]),
                float(b["maxX"]), float(b["maxY"]))
    except (KeyError, TypeError, ValueError):
        return None


def _kind(ref):
    head = "".join(ch for ch in str(ref) if ch.isalpha())
    return "active" if head in ("U", "MK", "J", "Q", "SW", "Y", "L", "FB", "TP", "D") else "passive"


def compact_group(snapshot, designators, *, columns=4, part_gap=PART_GAP):
    """Pack the group's parts into a compact grid; returns relative placements."""
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or [] if c.get("ref")}
    parts = []
    for ref in designators:
        comp = by_ref.get(ref)
        rect = _bbox(comp) if comp else None
        if not rect:
            continue
        parts.append({"ref": ref, "w": rect[2] - rect[0], "h": rect[3] - rect[1],
                      "nets": [str(p.get("net")) for p in comp.get("pins") or []
                               if p.get("net")]})
    parts.sort(key=lambda p: (0 if _kind(p["ref"]) == "active" else 1, p["ref"]))
    rows = []
    cursor_x = cursor_y = 0.0
    row_h = 0.0
    for index, part in enumerate(parts):
        if index and index % columns == 0:
            cursor_x = 0.0
            cursor_y -= row_h + part_gap
            row_h = 0.0
        part["x"] = _snap(cursor_x + part["w"] / 2.0)
        part["y"] = _snap(cursor_y + part["h"] / 2.0)
        cursor_x += part["w"] + part_gap
        row_h = max(row_h, part["h"])
    width = max((p["x"] + p["w"] / 2.0 for p in parts), default=0.0)
    top = max((p["y"] + p["h"] / 2.0 for p in parts), default=0.0)
    bottom = min((p["y"] - p["h"] / 2.0 for p in parts), default=0.0)
    return {"parts": parts, "w": _snap(width), "h": _snap(top - bottom)}


def build_modules(snapshot, groups, *, columns=4):
    modules, detail = [], []
    for group in groups:
        compact = compact_group(snapshot, group.get("designators") or [],
                                columns=columns)
        if not compact["parts"]:
            detail.append({"id": group.get("id"), "skipped": "no parts"})
            continue
        nets = set()
        for part in compact["parts"]:
            nets.update(part["nets"])
        halo = regroup_plan.label_halo(nets)
        modules.append({"id": group["id"],
                        "title": group.get("title") or group["id"],
                        "w": max(compact["w"], 1.0),
                        "h": max(compact["h"], 1.0),
                        "halo": {k: _snap(v) for k, v in halo.items()}})
        detail.append({"id": group["id"], "parts": len(compact["parts"]),
                       "w": modules[-1]["w"], "h": modules[-1]["h"],
                       "halo": modules[-1]["halo"], "compact": compact})
    return modules, detail


def plan_page(snapshot, groups, *, columns=None, page_template=None):
    """Compact groups -> balanced centred packing -> absolute part positions."""
    modules, detail = build_modules(snapshot, groups,
                                    columns=columns or 4)
    packed = balanced_pack.pack(modules)
    placements = {}
    for entry in detail:
        module_place = packed["placements"].get(entry["id"])
        if not module_place:
            continue
        compact = entry["compact"]
        top = module_place["y"] + float(module_place["h"]) / 2.0
        left = module_place["x"] - float(module_place["w"]) / 2.0
        min_x = min(part["x"] - part["w"] / 2.0 for part in compact["parts"])
        max_y = max(part["y"] + part["h"] / 2.0 for part in compact["parts"])
        for part in compact["parts"]:
            placements[part["ref"]] = {
                "x": _snap(left + (part["x"] - part["w"] / 2.0 - min_x) + part["w"] / 2.0),
                "y": _snap(top - (max_y - (part["y"] + part["h"] / 2.0)) - part["h"] / 2.0),
                "w": part["w"], "h": part["h"], "group": entry["id"],
                "module": module_place,
            }
    return {"schema": SCHEMA, "pack": {k: v for k, v in packed.items()
                                       if k != "placements"},
            "groups": detail, "placements": placements,
            "counts": {"groups": len(detail), "parts": len(placements),
                       "fits": packed.get("fit", False)},
            "verdict": "pass" if packed.get("fit") else "blocked"}


def _pin_anchors(snapshot, placements):
    """Approximate pin anchors on part edges so labels get distinct slots."""
    anchors = {}
    for comp in snapshot.get("components") or []:
        ref = comp.get("ref")
        place = placements.get(ref)
        if not place:
            continue
        pins = [p for p in comp.get("pins") or [] if p.get("net")]
        if not pins:
            continue
        w, h, x, y = place["w"], place["h"], place["x"], place["y"]
        for index, pin in enumerate(pins):
            side = index % 4
            if side == 0:
                anchor = (x + w / 2.0, y - h / 2.0 + h * (index + 1) / (len(pins) + 1))
            elif side == 1:
                anchor = (x - w / 2.0, y - h / 2.0 + h * (index + 1) / (len(pins) + 1))
            elif side == 2:
                anchor = (x - w / 2.0 + w * (index + 1) / (len(pins) + 1), y + h / 2.0)
            else:
                anchor = (x - w / 2.0 + w * (index + 1) / (len(pins) + 1), y - h / 2.0)
            anchors["%s:%s" % (ref, pin.get("number"))] = anchor
    return anchors


def label_sides(snapshot, placements, *, label_size=LABEL_SIZE):
    """Choose a stub side for every net label with the collision-avoiding solver."""
    occupied = []
    for place in placements.values():
        occupied.append((place["x"] - place["w"] / 2.0, place["y"] - place["h"] / 2.0,
                         place["x"] + place["w"] / 2.0, place["y"] + place["h"] / 2.0))
    anchors = _pin_anchors(snapshot, placements)
    labels = []
    for key, anchor in anchors.items():
        ref, _, number = key.partition(":")
        comp = next((c for c in snapshot.get("components") or []
                     if c.get("ref") == ref), None)
        net = None
        if comp:
            for pin in comp.get("pins") or []:
                if str(pin.get("number")) == number:
                    net = pin.get("net")
        if not net:
            continue
        labels.append({"id": key, "text": str(net), "size": label_size,
                       "anchor": [anchor[0], anchor[1]],
                       "preferred": ["right", "left", "top", "bottom"]})
    page = (0.0, 0.0, 1170.0, 825.0)
    result = label_solver.solve_label_plan(labels, occupied, page)
    sides = {}
    boxes = {}
    for item in result.get("placements") or []:
        key = item.get("id")
        direction = item.get("direction") or item.get("side")
        if key and direction:
            sides[key] = direction
            boxes[key] = item.get("bbox")
    return {"sides": sides, "boxes": boxes, "labels": len(labels),
            "unplaced": len(result.get("unplaced") or [])}


def render_preview(result, labels, path, *, page_w=1170.0, page_h=825.0, scale=1.6,
                   show_labels=True):
    """Draw a clean plan preview (Pillow): sheet, module cards, chips, labels."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 11)
        small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 9)
        title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
    except OSError:
        font = small = title_font = ImageFont.load_default()
    width, height = int(page_w * scale), int(page_h * scale)
    img = Image.new("RGB", (width + 40, height + 70), "#ffffff")
    draw = ImageDraw.Draw(img, "RGBA")

    def sx(value):
        return 20 + int(float(value) * scale)

    def sy(value):
        return 40 + int((page_h - float(value)) * scale)

    draw.rectangle([sx(0), sy(page_h), sx(page_w), sy(0)], fill="#fbfbfd",
                   outline="#444", width=2)
    draw.rectangle([sx(10), sy(815), sx(1160), sy(10)], outline="#9aa" , width=1)
    # title block keepout
    draw.rectangle([sx(460), sy(190), sx(1160), sy(10)], fill="#f0f0f4",
                   outline="#c9c9d6")
    draw.text((sx(470), sy(100)), "标题栏区域", fill="#8a8a99", font=small)
    util = result.get("pack", {}).get("utilization")
    draw.text((sx(12), sy(815) - 16),
              "利用率 %.0f%%   分页 %d   器件 %d"
              % ((util or 0) * 100, 1 if result.get("verdict") == "pass" else 0,
                 result.get("counts", {}).get("parts", 0)),
              fill="#333", font=font)

    palette = ["#e8f0ff", "#eafbea", "#fff0e6", "#f6e8ff", "#e6fbff"]
    for index, group in enumerate(result.get("groups") or []):
        module = (group.get("module") if group.get("module")
                  else next((p["module"] for p in result["placements"].values()
                             if p.get("group") == group["id"]), None))
        if not module:
            continue
        left = module["x"] - module["w"] / 2.0
        top = module["y"] + module["h"] / 2.0
        right = module["x"] + module["w"] / 2.0
        bottom = module["y"] - module["h"] / 2.0
        fill = palette[index % len(palette)]
        draw.rounded_rectangle([sx(left), sy(top), sx(right), sy(bottom)],
                               radius=6, fill=fill, outline="#AA00AA", width=2)
        draw.text((sx(left) + 6, sy(top) + 4),
                  str(group.get("title") or group["id"]), fill="#7a007a", font=font)
    for ref, place in (result.get("placements") or {}).items():
        x, y, w, h = place["x"], place["y"], place["w"], place["h"]
        draw.rounded_rectangle([sx(x - w / 2), sy(y + h / 2), sx(x + w / 2), sy(y - h / 2)],
                               radius=3, fill="#ffffff", outline="#0055AA", width=1)
        draw.text((sx(x - w / 2) + 2, sy(y + h / 2) + 1), ref, fill="#003366", font=small)
    if show_labels:
        for key, direction in (labels.get("sides") or {}).items():
            box = (labels.get("boxes") or {}).get(key)
            if not box:
                continue
            draw.rectangle([sx(box[0]), sy(box[3]), sx(box[2]), sy(box[1])],
                           fill="#fff8cc", outline="#d4b800")
    draw.text((20, 8), "EasyCirq 重排预览（紧凑分组 + 标签感知留白 + 居中排布）",
              fill="#222", font=title_font)
    img.save(path)
    return path


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA,
                      "usage": "plan_page(snapshot, groups)"}, ensure_ascii=False))
