"""Channel-reserved paginated layout: the systemic fix for label collisions.

Root cause (2026-10-30, C board): labels are the only page objects whose size we
cannot choose, yet the old layout reserved space from part footprints only.
Dense IC pins (10-unit pitch) put two labels on the same 20-unit ring, EDA's
geometry guard rejects both, and the write channel degraded.

This module reserves the space labels actually need *before* anything is
written:

1. each part gets a **per-side channel** = stub + its widest label on that side;
2. parts are packed so neighbouring channels never share a ring;
3. a card = parts + channels (labels can never leave it);
4. cards are paginated greedily (a page is filled until the next card no longer
   fits), so the sheet size decides the number of pages instead of the layout
   being squeezed into one.
"""

from __future__ import annotations

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import balanced_pack  # noqa: E402
import grid_snap  # noqa: E402
import stub_planner  # noqa: E402

SCHEMA = "easycirq-channel-layout/v1"
STUB = 20.0
PAD = 4.0
PAGE = (10.0, 10.0, 1160.0, 815.0)
TITLE_BLOCK = (460.0, 10.0, 1160.0, 190.0)


def part_channels(ref, geometry, *, stub=STUB, label_size=10.0):
    """Per-side channel width for one part (stub + widest label on that side)."""
    info = (geometry.get("parts") or {}).get(ref) or {}
    channels = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    for pin in (info.get("pins") or {}).values():
        net = pin.get("net")
        side = stub_planner.SIDE_TO_DIRECTION.get(pin.get("side") or "right", "right")
        need = stub + (max(24.0, 7.0 * len(str(net))) if net else 24.0)
        if side in ("left", "right"):
            channels[side] = max(channels[side], need)
        else:
            channels["top" if side == "up" else "bottom"] = max(
                channels["top" if side == "up" else "bottom"], max(30.0, stub + 14.0))
    return channels


def build_cards(snapshot, groups, geometry, *, columns=3):
    """Lay each group out with channels and return cards + relative packing."""
    cards = []
    for group in groups:
        parts = []
        for ref in group.get("designators") or []:
            comp = next((c for c in snapshot.get("components") or []
                         if c.get("ref") == ref), None)
            bbox = (comp or {}).get("bbox") or {}
            if not bbox:
                continue
            channels = part_channels(ref, geometry)
            parts.append({"ref": ref,
                          "w": bbox["maxX"] - bbox["minX"],
                          "h": bbox["maxY"] - bbox["minY"],
                          "channels": channels})
        if not parts:
            continue
        parts.sort(key=lambda p: (0 if p["ref"][:1] in ("U", "Q", "M") else 1, p["ref"]))
        cursor_x = cursor_y = 0.0
        row_h = 0.0
        placed = []
        for index, part in enumerate(parts):
            if index and index % columns == 0:
                cursor_x = 0.0
                cursor_y -= row_h + PAD
                row_h = 0.0
            left = part["channels"]["left"]
            top = part["channels"]["top"]
            x = cursor_x + left + part["w"] / 2.0
            y = cursor_y - top - part["h"] / 2.0
            placed.append({"ref": part["ref"], "x": x, "y": y,
                           "w": part["w"], "h": part["h"], "channels": part["channels"]})
            cursor_x += left + part["w"] + part["channels"]["right"] + PAD
            row_h = max(row_h, top + part["h"] + part["channels"]["bottom"])
        min_x = min(p["x"] - p["w"] / 2.0 - p["channels"]["left"] for p in placed)
        max_x = max(p["x"] + p["w"] / 2.0 + p["channels"]["right"] for p in placed)
        min_y = min(p["y"] - p["h"] / 2.0 - p["channels"]["bottom"] for p in placed)
        max_y = max(p["y"] + p["h"] / 2.0 + p["channels"]["top"] for p in placed)
        cards.append({"id": group["id"], "title": group.get("title") or group["id"],
                      "w": max_x - min_x + 2 * PAD, "h": max_y - min_y + 2 * PAD,
                      "parts": placed, "origin": (min_x - PAD, min_y - PAD)})
    return cards


def paginate(cards, *, page=PAGE, title_block=TITLE_BLOCK, gap=8.0, col_gap=20.0):
    """Shelf pagination: rows first, then pages; first card always lands on page 1."""
    x0, y0 = page[0] + 6, title_block[3] + 6
    x1, y1 = page[2] - 6, page[3] - 6
    usable_w, usable_h = x1 - x0, y1 - y0
    pages, current = [], []
    cursor_x, cursor_y, row_h = 0.0, usable_h, 0.0
    for card in sorted(cards, key=lambda c: (-(c["w"] * c["h"]), c["id"])):
        w, h = card["w"], card["h"]
        if w > usable_w or h > usable_h:
            raise ValueError("card %s (%.0fx%.0f) does not fit the sheet"
                             % (card["id"], w, h))
        if cursor_x + w > usable_w:                 # next row
            cursor_x, cursor_y, row_h = 0.0, cursor_y - row_h - gap, 0.0
        if cursor_y - h < 0:                        # next page
            pages.append(current)
            current = []
            cursor_x, cursor_y, row_h = 0.0, usable_h, 0.0
        current.append(dict(card, page=len(pages), px=x0 + cursor_x,
                            py=y0 + cursor_y - h))
        cursor_x += w + gap
        row_h = max(row_h, h)
    if current:
        pages.append(current)
    return pages


def union_cards(cards, placements, label_boxes, group_of):
    """Resize each card to include its parts AND its labels (never overflow)."""
    rects = {}
    for ref, place in placements.items():
        try:
            w, h = float(place["w"]), float(place["h"])
        except (KeyError, TypeError, ValueError):
            w, h = 20.0, 10.0
        rect = rects.setdefault(group_of.get(ref, ref),
                                [place["x"], place["y"], place["x"], place["y"]])
        rect[0] = min(rect[0], place["x"] - w / 2.0)
        rect[1] = min(rect[1], place["y"] - h / 2.0)
        rect[2] = max(rect[2], place["x"] + w / 2.0)
        rect[3] = max(rect[3], place["y"] + h / 2.0)
    for pin, box in label_boxes.items():
        group = group_of.get(pin.split(":")[0])
        if group is None:
            continue
        rect = rects.setdefault(group, list(box))
        rect[0], rect[1] = min(rect[0], box[0]), min(rect[1], box[1])
        rect[2], rect[3] = max(rect[2], box[2]), max(rect[3], box[3])
    return [{"id": group, "w": (r[2] - r[0]) + 2 * PAD, "h": (r[3] - r[1]) + 2 * PAD,
             "src": (r[0] - PAD, r[1] - PAD)} for group, r in rects.items()]


def paginate_blocks(blocks, *, page=PAGE, title_block=TITLE_BLOCK,
                    gap=10.0, col_gap=20.0):
    """Balance blocks over pages (lightest-page first) with two columns per page.

    ``blocks`` = ``{block_id: {"cards": [...], "w": float, "h": float}}``.
    Returns ``[[(block_id, {"cards", "px", "py"}) ...]]`` per page; every block
    stays whole on one page.
    """
    x0, y0 = page[0] + 6, title_block[3] + 6
    x1, y1 = page[2] - 6, page[3] - 6
    usable_w, usable_h = x1 - x0, y1 - y0
    order = sorted(blocks.items(), key=lambda kv: (-(kv[1]["w"] * kv[1]["h"]), kv[0]))
    for count in (1, 2, 3, 4, 5):
        bins = [[] for _ in range(count)]
        loads = [0.0] * count
        for block_id, info in order:
            target = min(range(count), key=lambda i: loads[i])
            bins[target].append((block_id, info))
            loads[target] += info["w"] * info["h"]
        pages = []
        ok = True
        for bin_blocks in bins:
            if not bin_blocks:
                continue
            columns = [[], []]
            heights = [0.0, 0.0]
            for block_id, info in sorted(bin_blocks, key=lambda kv: -kv[1]["h"]):
                target = 0 if heights[0] <= heights[1] else 1
                columns[target].append((block_id, info))
                heights[target] += info["h"] + gap
            need_w = sum(max((i["w"] for _, i in col), default=0.0) for col in columns) + col_gap
            need_h = max(sum(i["h"] for _, i in col) + gap * max(0, len(col) - 1)
                         for col in columns)
            if need_w > usable_w or need_h > usable_h:
                ok = False
                break
            pages.append([col for col in columns if col])
        if ok:
            return pages
    raise ValueError("blocks do not fit the sheet even across five pages")


def plan(snapshot, groups, geometry):
    """Cards -> pages -> absolute placements + label boxes (channels reserved).

    Every page's anchors are snapped to the schematic grid with
    ``grid_snap.snap_plan`` before they are published, so the plan can never hand
    a pin-off-grid placement to the write channel; the per-page ``grid_snap``
    report (and a summary under ``result["grid_snap"]``) carries the evidence.
    """
    geometry = geometry or {}
    cards = build_cards(snapshot, groups, geometry)
    pages = paginate(cards)
    result = {"schema": SCHEMA, "pages": []}
    reports = []
    for index, page_cards in enumerate(pages):
        placements, boxes = {}, {}
        for card in page_cards:
            ox, oy = card["origin"]
            for part in card["parts"]:
                placements[part["ref"]] = {
                    "x": round(card["px"] + (part["x"] - ox), 1),
                    "y": round(card["py"] + (part["y"] - oy), 1),
                    "w": part["w"], "h": part["h"], "group": card["id"],
                    "page": index}
        snapped = grid_snap.snap_plan(placements, geometry)
        reports.append(snapped["report"])
        result["pages"].append({
            "page": index,
            "cards": [{"id": c["id"], "rect": [round(c["px"], 1), round(c["py"], 1),
                                               round(c["px"] + c["w"], 1),
                                               round(c["py"] + c["h"], 1)]}
                      for c in page_cards],
            "grid_snap": snapped["report"],
            "placements": snapped["placements"]})
    result["grid_snap"] = {
        "schema": grid_snap.SCHEMA,
        "pages": reports,
        "pins_off_grid_before": sum(r["pins_off_grid_before"] for r in reports),
        "pins_off_grid_after": sum(r["pins_off_grid_after"] for r in reports),
        "max_displacement": max((r["max_displacement"] for r in reports), default=0.0)}
    result["counts"] = {"cards": len(cards), "pages": len(pages),
                        "parts": sum(len(p["placements"]) for p in result["pages"]),
                        "pins_off_grid_after": result["grid_snap"]["pins_off_grid_after"]}
    return result


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA}, ensure_ascii=False))
