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
CARD_PAD = 6.0
HALO_CAP = 16.0
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


def compact_group(snapshot, designators, *, columns=None, part_gap=PART_GAP,
                  geometry=None, target_width=None):
    if columns is None:
        per_row = max(1.0, float(target_width or 400.0) / 90.0)
        columns = max(2, min(2 + len(designators), int(round(per_row))))
    """Pack a group's parts into a compact grid (IC first, then net-clustered)."""
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or [] if c.get("ref")}
    parts = []
    for ref in designators:
        comp = by_ref.get(ref)
        rect = _bbox(comp) if comp else None
        if not rect:
            continue
        nets = [str(p.get("net")) for p in comp.get("pins") or [] if p.get("net")]
        widest = tallest = 0.0
        for net in nets:
            try:
                size = text_metrics.text_size(net, LABEL_SIZE, "left_center")
            except Exception:  # noqa: BLE001
                continue
            widest = max(widest, float(size.get("w") or 0.0))
            tallest = max(tallest, float(size.get("h") or 0.0))
        parts.append({"ref": ref, "w": rect[2] - rect[0], "h": rect[3] - rect[1],
                      "nets": nets, "label_w": widest, "label_h": tallest,
                      "active": _kind(ref) == "active"})
    parts.sort(key=lambda q: (0 if q["active"] else 1, q["ref"]))
    for part in parts:                      # room for this part's own labels
        gap = 64.0 if _kind(part["ref"]) == "active" else 14.0
        part["cell_w"] = part["w"] + gap
        part["cell_h"] = part["h"] + gap
    pending = list(parts)
    ordered = []
    while pending:                          # net-clustered order keeps related parts adjacent
        if not ordered:
            pick = pending.pop(0)
        else:
            placed_nets = set()
            for part in ordered:
                placed_nets.update(part["nets"])
            pick = max(pending, key=lambda q: (sum(1 for n in q["nets"] if n in placed_nets),
                                               -pending.index(q)))
            pending.remove(pick)
        ordered.append(pick)
    cursor_x = cursor_y = 0.0
    row_h = 0.0
    for index, part in enumerate(ordered):
        if index and index % columns == 0:
            cursor_x = 0.0
            cursor_y -= row_h + part_gap
            row_h = 0.0
        part["x"] = _snap(cursor_x + part["cell_w"] / 2.0)
        part["y"] = _snap(cursor_y + part["cell_h"] / 2.0)
        cursor_x += part["cell_w"]
        row_h = max(row_h, part["cell_h"])
    width = max((part["x"] + part["w"] / 2.0 for part in ordered), default=0.0)
    top = max((part["y"] + part["h"] / 2.0 for part in ordered), default=0.0)
    bottom = min((part["y"] - part["h"] / 2.0 for part in ordered), default=0.0)
    for part in ordered:
        part["x"] = _snap(part["x"] + CARD_PAD)
        part["y"] = _snap(part["y"] - bottom + CARD_PAD)
    return {"parts": ordered, "w": _snap(width + 2 * CARD_PAD),
            "h": _snap(top - bottom + 2 * CARD_PAD)}


def build_modules(snapshot, groups, *, columns=4):
    modules, detail = [], []
    for group in groups:
        designators = group.get("designators") or []
        if columns:
            compact = compact_group(snapshot, designators, columns=columns)
        else:
            # choose the column count that gives the smallest card area
            best = None
            for count in range(3, 8):
                candidate = compact_group(snapshot, designators, columns=count)
                if not candidate["parts"]:
                    continue
                area = candidate["w"] * candidate["h"]
                if best is None or area < best[0] - 1e-6:
                    best = (area, candidate)
            compact = best[1] if best else compact_group(snapshot, designators, columns=3)
        if not compact["parts"]:
            detail.append({"id": group.get("id"), "skipped": "no parts"})
            continue
        nets = set()
        for part in compact["parts"]:
            nets.update(part["nets"])
        halo = regroup_plan.label_halo(nets)
        halo = {k: _snap(min(HALO_CAP, max(0.0, float(v)))) for k, v in halo.items()}
        # the card contains its own label halo: wires/labels can never leave it
        modules.append({"id": group["id"],
                        "title": group.get("title") or group["id"],
                        "w": max(_snap(compact["w"]) + halo["left"] + halo["right"], 1.0),
                        "h": max(_snap(compact["h"]) + halo["top"] + halo["bottom"], 1.0),
                        "footprint": {"w": max(_snap(compact["w"]), 1.0),
                                      "h": max(_snap(compact["h"]), 1.0)},
                        "halo": halo})
        detail.append({"id": group["id"], "parts": len(compact["parts"]),
                       "w": modules[-1]["w"], "h": modules[-1]["h"],
                       "halo": modules[-1]["halo"], "compact": compact})
    return modules, detail


def plan_page(snapshot, groups, *, columns=None, page_template=None, geometry=None):
    """Two-pass relayout: solve labels locally, size each card, pack cards.

    Pass 1 places a group's parts on a local grid and solves its labels locally,
    so each group's card size is exactly ``union(parts, labels) + 2``.
    Pass 2 packs those cards (no overlaps by construction) and translates the
    parts and labels rigidly into place.  Every label therefore stays inside its
    own card and cards never collide.
    """
    modules = []
    for group in groups:
        designators = list(group.get("designators") or [])
        if columns:
            compact = compact_group(snapshot, designators, columns=columns,
                                    geometry=geometry)
        else:
            best = None
            for width in (260.0, 320.0, 380.0, 440.0, 500.0):
                candidate = compact_group(snapshot, designators,
                                          geometry=geometry, target_width=width)
                if not candidate["parts"]:
                    continue
                area = candidate["w"] * candidate["h"]
                if best is None or area < best[0] - 1e-6:
                    best = (area, candidate)
            compact = best[1] if best else compact_group(snapshot, designators,
                                                         geometry=geometry)
        if not compact["parts"]:
            continue
        local = {}
        for part in compact["parts"]:
            local[part["ref"]] = {"x": part["x"], "y": part["y"],
                                  "w": part["w"], "h": part["h"],
                                  "group": group["id"]}
        labels = label_sides(snapshot, local, geometry=geometry,
                             page=(-2000.0, -2000.0, 2000.0, 2000.0))
        boxes = [b for b in (labels.get("boxes") or {}).values() if b]
        part_boxes = [(place["x"] - place["w"] / 2.0, place["y"] - place["h"] / 2.0,
                       place["x"] + place["w"] / 2.0, place["y"] + place["h"] / 2.0)
                      for place in local.values()]
        all_boxes = part_boxes + [tuple(b) for b in boxes]
        left = min(b[0] for b in all_boxes) - 2.0
        bottom = min(b[1] for b in all_boxes) - 2.0
        right = max(b[2] for b in all_boxes) + 2.0
        top = max(b[3] for b in all_boxes) + 2.0
        modules.append({"id": group["id"],
                        "title": group.get("title") or group["id"],
                        "w": round(right - left, 1), "h": round(top - bottom, 1),
                        "halo": {"left": 0, "right": 0, "top": 0, "bottom": 0},
                        "local": {"parts": local, "labels": labels,
                                  "origin": (left, bottom)}})
    packed = balanced_pack.pack(modules, halo_in_size=True, max_columns=min(len(modules), 4))
    placements = {}
    cards = {}
    all_labels = {"sides": {}, "boxes": {}, "texts": {},
                  "labels": 0, "unplaced": 0}
    for module in modules:
        place = packed["placements"].get(module["id"])
        if not place:
            continue
        module_left = place["x"] - place["w"] / 2.0
        module_top = place["y"] + place["h"] / 2.0
        local = module["local"]
        left, bottom = local["origin"]
        local_top = bottom + module["h"]
        dx = module_left - left
        dy = module_top - local_top
        cards[module["id"]] = [round(module_left, 1), round(module_top - module["h"], 1),
                               round(module_left + module["w"], 1), round(module_top, 1)]
        for ref, lplace in local["parts"].items():
            placements[ref] = {"x": _snap(lplace["x"] + dx),
                               "y": _snap(lplace["y"] + dy),
                               "w": lplace["w"], "h": lplace["h"],
                               "group": module["id"]}
        for key, box in (local["labels"].get("boxes") or {}).items():
            if box:
                all_labels["boxes"][key] = [box[0] + dx, box[1] + dy,
                                            box[2] + dx, box[3] + dy]
        all_labels["sides"].update(local["labels"].get("sides") or {})
        all_labels["texts"].update(local["labels"].get("texts") or {})
        all_labels["labels"] += local["labels"].get("labels", 0)
        all_labels["unplaced"] += local["labels"].get("unplaced", 0)
    fits = bool(cards) and all(
        10.0 <= c[0] + 0.0 and c[2] <= 1160.0 and 196.0 <= c[1] and c[3] <= 815.0
        for c in cards.values())
    if cards and not fits:
        dx = dy = 0.0
        min_x = min(c[0] for c in cards.values())
        max_x = max(c[2] for c in cards.values())
        min_y = min(c[1] for c in cards.values())
        max_y = max(c[3] for c in cards.values())
        if min_x < 10.0:
            dx = 10.0 - min_x
        elif max_x > 1160.0:
            dx = 1160.0 - max_x
        if min_y < 196.0:
            dy = 196.0 - min_y
        elif max_y > 815.0:
            dy = 815.0 - max_y
        if dx or dy:
            for place in placements.values():
                place["x"] = _snap(place["x"] + dx)
                place["y"] = _snap(place["y"] + dy)
            for key, box in all_labels["boxes"].items():
                all_labels["boxes"][key] = [box[0] + dx, box[1] + dy,
                                            box[2] + dx, box[3] + dy]
            cards = {k: [round(c[0] + dx, 1), round(c[1] + dy, 1),
                         round(c[2] + dx, 1), round(c[3] + dy, 1)]
                     for k, c in cards.items()}
        fits = all(10.0 <= c[0] and c[2] <= 1160.0 and 196.0 <= c[1] and c[3] <= 815.0
                   for c in cards.values())
    total = sum((c[2] - c[0]) * (c[3] - c[1]) for c in cards.values()) if cards else 0.0
    span_w = (max(c[2] for c in cards.values()) - min(c[0] for c in cards.values())
              if cards else 0.0)
    span_h = (max(c[3] for c in cards.values()) - min(c[1] for c in cards.values())
              if cards else 0.0)
    packed["utilization"] = round(total / (span_w * span_h), 3) if span_w and span_h else 0.0
    return {"schema": SCHEMA, "cards": cards, "pack": packed,
            "groups": [{"id": m["id"], "title": m["title"]} for m in modules],
            "placements": placements, "labels": all_labels,
            "counts": {"groups": len(modules), "parts": len(placements),
                       "labels": all_labels["labels"],
                       "unplaced": all_labels["unplaced"], "fits": fits,
                       "card_overlaps": _overlaps(cards)},
            "verdict": "pass" if fits and not _overlaps(cards) else "blocked"}


def _overlaps(cards):
    items = list(cards.values())
    count = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if (min(a[2], b[2]) > max(a[0], b[0])
                    and min(a[3], b[3]) > max(a[1], b[1])):
                count += 1
    return count


def _pin_anchors(snapshot, placements, geometry=None):
    """Pin anchors: real offsets from the captured page when available."""
    geometry = geometry or {}
    parts = geometry.get("parts") or {}
    anchors, sides = {}, {}
    for comp in snapshot.get("components") or []:
        ref = comp.get("ref")
        place = placements.get(ref)
        if not place:
            continue
        pins = [p for p in comp.get("pins") or [] if p.get("net")]
        if not pins:
            continue
        real = (parts.get(ref) or {}).get("pins") or {}
        for index, pin in enumerate(pins):
            number = str(pin.get("number"))
            info = real.get(number)
            if info:
                anchors["%s:%s" % (ref, number)] = (place["x"] + float(info["dx"]),
                                                    place["y"] + float(info["dy"]))
                sides["%s:%s" % (ref, number)] = info.get("side") or "right"
                continue
            # fallback: distribute on the four part edges
            w, h, x, y = place["w"], place["h"], place["x"], place["y"]
            side = index % 4
            if side == 0:
                anchor = (x + w / 2.0, y - h / 2.0 + h * (index + 1) / (len(pins) + 1))
            elif side == 1:
                anchor = (x - w / 2.0, y - h / 2.0 + h * (index + 1) / (len(pins) + 1))
            elif side == 2:
                anchor = (x - w / 2.0 + w * (index + 1) / (len(pins) + 1), y + h / 2.0)
            else:
                anchor = (x - w / 2.0 + w * (index + 1) / (len(pins) + 1), y - h / 2.0)
            anchors["%s:%s" % (ref, number)] = anchor
    return anchors, sides


def label_sides(snapshot, placements, *, cards=None, geometry=None,
                label_size=LABEL_SIZE, page=None):
    """Choose a stub side per net label; other module cards are obstacles."""
    cards = cards or {}
    part_boxes = {}
    for ref, place in placements.items():
        part_boxes[ref] = (place["x"] - place["w"] / 2.0, place["y"] - place["h"] / 2.0,
                           place["x"] + place["w"] / 2.0, place["y"] + place["h"] / 2.0)
    anchors, real_sides = _pin_anchors(snapshot, placements, geometry)
    by_group = {}
    for key in anchors:
        ref = key.split(":", 1)[0]
        place = placements.get(ref) or {}
        by_group.setdefault(place.get("group"), []).append(key)
    if page is None:
        page = (10.0, 10.0, 1160.0, 815.0)
    sides, boxes, texts, unplaced = {}, {}, {}, 0
    for group_id, keys in by_group.items():
        occupied = []
        for ref, place in placements.items():
            if place.get("group") == group_id:
                occupied.append(part_boxes[ref])
        for ref, place in placements.items():
            if place.get("group") != group_id:
                occupied.append((place["x"] - place["w"] / 2.0, place["y"] - place["h"] / 2.0,
                                 place["x"] + place["w"] / 2.0, place["y"] + place["h"] / 2.0))
        card = cards.get(group_id) or (0.0, 0.0, 1170.0, 825.0)
        group_page = (card[0] + 2.0, card[1] + 2.0, card[2] - 2.0, card[3] - 2.0)
        card_cx = (card[0] + card[2]) / 2.0
        card_cy = (card[1] + card[3]) / 2.0
        labels = []
        for key in keys:
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
            anchor = anchors[key]
            place = placements.get(ref) or {}
            ax = float(place.get("x", anchor[0]))
            ay = float(place.get("y", anchor[1]))
            # a real pin points outward: its label starts on that side
            outward = real_sides.get(key)
            if outward:
                preferred = [outward]
            else:
                horiz = "right" if ax < card_cx else "left"
                vert = "top" if ay < card_cy else "bottom"
                preferred = [horiz, vert,
                             "right" if horiz == "left" else "left",
                             "bottom" if vert == "top" else "top"]
            preferred = preferred + [d for d in ("right", "top", "left", "bottom")
                                     if d not in preferred]
            labels.append({"id": key, "text": str(net), "size": label_size,
                           "anchor": [anchor[0], anchor[1]],
                           "preferred": preferred})
        result = label_solver.solve_label_plan(
            labels, occupied, group_page, gap=2.0, distances=(20,))
        for item in result.get("placements") or []:
            key = item.get("id")
            direction = item.get("direction") or item.get("side")
            if key and direction:
                sides[key] = direction
                boxes[key] = item.get("bbox")
                texts[key] = next((l["text"] for l in labels if l["id"] == key), "")
        pending = [item for item in result.get("unplaced") or [] if item.get("id")]
        for shrunk in (10.0, 9.0, 8.0, 6.0):  # only the stubborn ones get smaller text
            if not pending:
                break
            retry = []
            for item in pending:
                key = item.get("id")
                label = next((l for l in labels if l["id"] == key), None)
                if not label:
                    continue
                candidate = dict(label, size=shrunk)
                retry.append(candidate)
            if not retry:
                break
            occupied_now = list(occupied) + [
                tuple(box) for box in boxes.values() if box]
            again = label_solver.solve_label_plan(
                retry, occupied_now, group_page, gap=1.0,
                distances=(20, 30, 40, 12, 8, 4))
            for item in again.get("placements") or []:
                key = item.get("id")
                direction = item.get("direction") or item.get("side")
                if key and direction:
                    sides[key] = direction
                    boxes[key] = item.get("bbox")
            pending = [item for item in again.get("unplaced") or [] if item.get("id")]
        unplaced += len(pending)
    return {"sides": sides, "boxes": boxes, "texts": texts,
            "labels": sum(len(v) for v in by_group.values()),
            "unplaced": unplaced}


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

    palette = ["#e8f0ff", "#eafbea", "#fff0e6", "#f6e8ff", "#e6fbff", "#fff3f3", "#eef7ff"]
    cards = result.get("cards") or {}
    for index, group in enumerate(result.get("groups") or []):
        card = cards.get(group["id"])
        if not card:
            continue
        left, bottom, right, top = card
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
        try:
            labelfont = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 8)
        except OSError:
            labelfont = small
        for key, direction in (labels.get("sides") or {}).items():
            box = (labels.get("boxes") or {}).get(key)
            if not box:
                continue
            draw.rectangle([sx(box[0]), sy(box[3]), sx(box[2]), sy(box[1])],
                           fill="#fff8cc", outline="#d4b800")
            text = (labels.get("texts") or {}).get(key) or ""
            if text:
                draw.text((sx(box[0]) + 2, sy(box[3]) + 1), str(text)[:14],
                          fill="#7a6a00", font=labelfont)
    draw.text((20, 8), "EasyCirq 重排预览（紧凑分组 + 标签感知留白 + 居中排布）",
              fill="#222", font=title_font)
    img.save(path)
    return path


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA,
                      "usage": "plan_page(snapshot, groups)"}, ensure_ascii=False))
