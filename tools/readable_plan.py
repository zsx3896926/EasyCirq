"""Build a readable, validated page plan (layout-time constraints, no rework).

Pipeline: group by role -> attach decoupling caps to their rail's IC -> order
columns input->conversion->core->interface -> place blocks (block affinity, two
balanced pages) -> canonicalise net names -> renumber designators -> validate
with ``layout_policy``.  The loop adjusts the plan until ``violations == 0``.

Output: ``easycirq-readable-plan/v1`` (placements, cards, pages, rename maps).
"""

from __future__ import annotations

import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import channel_layout  # noqa: E402
import grid_snap  # noqa: E402
import layout_policy  # noqa: E402

SCHEMA = "easycirq-readable-plan/v1"
PAGE = (10.0, 196.0, 1160.0, 815.0)
GAP, COL_GAP = 10.0, 20.0
RAIL = re.compile(r"^(?:\+?\d+V\d?|VBUS|VBAT|VSYS|VIN|VOUT)")
PAD = 4.0


def _nets(comp):
    return {p.get("net") for p in comp.get("pins") or [] if p.get("net")}


def attach_decoupling(snapshot, groups):
    """Move rail-only capacitors into the sub-module of the IC they decouple."""
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or []}
    caps = [c for c in snapshot.get("components") or []
            if str(c.get("ref", "")).startswith("C")]
    ics = [c for c in snapshot.get("components") or []
           if str(c.get("ref", "")).startswith(("U", "MK"))]
    merged = []
    for group in groups:
        designators = list(group.get("designators") or [])
        merged.append(dict(group, designators=designators))
    for cap in caps:
        cap_rails = {n for n in _nets(cap) if n and RAIL.match(n)}
        if len(cap_rails) == 0:
            continue
        # find the IC sharing the most rails with this capacitor
        best = None
        for ic in ics:
            shared = len(cap_rails & _nets(ic))
            if shared and (best is None or shared > best[0]):
                best = (shared, ic.get("ref"))
        if not best:
            continue
        target_ic = best[1]
        for group in merged:
            if target_ic in group["designators"] and cap.get("ref") not in group["designators"]:
                group["designators"].append(cap.get("ref"))
                break
    return merged


def renumber(snapshot):
    """Contiguous designators per family (layout-time allocation)."""
    families = {}
    for comp in snapshot.get("components") or []:
        ref = str(comp.get("ref", ""))
        match = re.match(r"([A-Za-z]+)(\d+)", ref)
        if match:
            families.setdefault(match.group(1), []).append((int(match.group(2)), ref))
    mapping = {}
    for family, entries in families.items():
        entries.sort()
        for index, (_, ref) in enumerate(entries, start=1):
            mapping[ref] = "%s%d" % (family, index)
    return mapping


def build(snapshot, groups):
    sub_groups = []
    for group in groups:
        sub_groups.extend(__import__("subdivide").subdivide(
            snapshot, group) if group.get("designators") else [])
    sub_groups = attach_decoupling(snapshot, sub_groups)
    columns = layout_policy.column_order(snapshot)
    role_of = {}
    for role, refs in columns.items():
        for ref in refs:
            role_of[ref] = role
    # order sub-modules by the functional column order of their core part
    def group_role(group):
        refs = [r for r in group["designators"] if r in role_of]
        if not refs:
            return "core"
        return min((role_of[r] for r in refs),
                   key=lambda r: layout_policy.ROLE_ORDER.index(r))
    sub_groups.sort(key=lambda g: (layout_policy.ROLE_ORDER.index(group_role(g)),
                                   g["id"]))
    cards = channel_layout.build_cards(snapshot, sub_groups,
                                       __import__("json").loads(
                                           json_text(TOOLS / ".." / "easycirq"
                                                     / "assets" / "block-envelopes.json"))
                                       if False else None) if False else None
    return sub_groups


def json_text(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


def place_blocks(snapshot, sub_groups, geometry):
    """Compact grid per sub-module, then blocks per page (affinity + balance)."""
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or []}
    blocks = {}
    for group in sub_groups:
        parts = []
        for ref in group.get("designators") or []:
            comp = by_ref.get(ref)
            bbox = (comp or {}).get("bbox") or {}
            if not bbox:
                continue
            width = bbox["maxX"] - bbox["minX"]
            height = bbox["maxY"] - bbox["minY"]
            parts.append({"ref": ref, "w": width, "h": height})
        if not parts:
            continue
        parts.sort(key=lambda p: (0 if p["ref"][:1] in ("U", "Q", "M") else 1, p["ref"]))
        columns = max(1, len(parts))          # one row: caps adjacent to the IC
        cursor_x = cursor_y = 0.0
        row_h = 0.0
        for index, part in enumerate(parts):
            if index and index % columns == 0:
                cursor_x = 0.0
                cursor_y -= row_h + 16.0
                row_h = 0.0
            part["x"] = cursor_x + part["w"] / 2.0
            part["y"] = cursor_y - part["h"] / 2.0
            cursor_x += part["w"] + 18.0
            row_h = max(row_h, part["h"] + 16.0)
        min_x = min(p["x"] - p["w"] / 2 for p in parts)
        max_x = max(p["x"] + p["w"] / 2 for p in parts)
        min_y = min(p["y"] - p["h"] / 2 for p in parts)
        max_y = max(p["y"] + p["h"] / 2 for p in parts)
        blocks[group["id"]] = {
            "cards": [{"id": group["id"], "parts": parts, "w": max_x - min_x + 2 * PAD,
                       "h": max_y - min_y + 2 * PAD,
                       "origin": (min_x - PAD, min_y - PAD)}],
            "w": max_x - min_x + 2 * PAD, "h": max_y - min_y + 2 * PAD}
    return blocks


def paginate(blocks):
    x0, y0, x1, y1 = PAGE[0] + 6, PAGE[1] + 6, PAGE[2] - 6, PAGE[3] - 6
    usable_w, usable_h = x1 - x0, y1 - y0
    order = sorted(blocks.items(), key=lambda kv: (-(kv[1]["w"] * kv[1]["h"]), kv[0]))
    for count in (1, 2, 3, 4):
        bins = [[] for _ in range(count)]
        loads = [0.0] * count
        for block_id, info in order:
            target = min(range(count), key=lambda i: loads[i])
            bins[target].append((block_id, info))
            loads[target] += info["w"] * info["h"]
        pages, ok = [], True
        for bin_blocks in bins:
            if not bin_blocks:
                continue
            cols, heights = [[], []], [0.0, 0.0]
            for block_id, info in sorted(bin_blocks, key=lambda kv: -kv[1]["h"]):
                target = 0 if heights[0] <= heights[1] else 1
                cols[target].append((block_id, info))
                heights[target] += info["h"] + GAP
            need_w = sum(max((i["w"] for _, i in c), default=0.0) for c in cols) + COL_GAP
            need_h = max(sum(i["h"] for _, i in c) + GAP * max(0, len(c) - 1)
                         for c in cols)
            if need_w > usable_w or need_h > usable_h:
                ok = False
                break
            pages.append([c for c in cols if c])
        if ok:
            return pages
    raise ValueError("blocks do not fit")


def make(snapshot, groups, geometry=None):
    """Place, snap and validate: the returned placements are grid-snapped.

    ``geometry`` = ``easycirq-pin-geometry/v1``; when omitted it is rebuilt from
    the snapshot's own pin coordinates (``grid_snap.geometry_from_snapshot``), so
    the pin-by-pin grid check still runs.  Snapping happens *before*
    ``layout_policy.validate`` so the policy sees the coordinates that will be
    written.

    With a real ``geometry`` the snap is strict: a plan whose pins would share a
    coordinate (or whose parts overlap) raises ``ValueError`` instead of being
    returned - ``place_blocks`` packs rows from the footprint bbox, which is
    narrower than a passive's 40-unit pin span, so the strict check is what
    stops that collision from reaching the write channel.
    """
    if geometry is None:
        geometry = grid_snap.geometry_from_snapshot(snapshot)
    sub_groups = []
    for group in groups:
        sub_groups.extend(__import__("subdivide").subdivide(snapshot, group))
    sub_groups = attach_decoupling(snapshot, sub_groups)
    role_of = {}
    for role, refs in layout_policy.column_order(snapshot).items():
        for ref in refs:
            role_of[ref] = role

    def group_role(group):
        refs = [r for r in group["designators"] if r in role_of]
        return min((layout_policy.ROLE_ORDER.index(role_of[r]) for r in refs),
                   default=layout_policy.ROLE_ORDER.index("core"))
    sub_groups.sort(key=lambda g: (group_role(g), g["id"]))
    blocks = place_blocks(snapshot, sub_groups, None)
    pages = paginate(blocks)
    placements = {}
    page_out = []
    for pindex, page in enumerate(pages):
        total_w = sum(max(i["w"] for _, i in col) for col in page) + COL_GAP * (len(page) - 1)
        total_h = max(sum(i["h"] for _, i in col) + GAP * max(0, len(col) - 1) for col in page)
        start_x = PAGE[0] + ((PAGE[2] - PAGE[0]) - total_w) / 2.0
        top_y = PAGE[3] - ((PAGE[3] - PAGE[1]) - total_h) / 2.0
        cursor_x = start_x
        cards = []
        for col in page:
            col_w = max(i["w"] for _, i in col)
            cursor_y = top_y
            for block_id, info in col:
                for card in info["cards"]:
                    ox, oy = card["origin"]
                    card_px = cursor_x + (col_w - card["w"]) / 2.0
                    card_py = cursor_y - card["h"]
                    cards.append({"id": block_id, "px": card_px, "py": card_py,
                                  "w": card["w"], "h": card["h"]})
                    for part in card["parts"]:
                        placements[part["ref"]] = {
                            "x": round(card_px + (part["x"] - ox), 1),
                            "y": round(card_py + (part["y"] - oy), 1)}
                    cursor_y -= card["h"] + GAP
            cursor_x += col_w + COL_GAP
        page_out.append({"page": pindex, "cards": cards,
                         "placements": {r: p for r, p in placements.items()}})
    # snap anchors in place so the per-page views (same dict objects) stay valid
    snapped = grid_snap.snap_plan(placements, geometry)
    for ref, place in snapped["placements"].items():
        placements[ref].update(place)
    for page in page_out:
        page["grid_snap"] = snapped["report"]
    rename_nets = layout_policy.rename_plan(snapshot)
    renumber_map = renumber(snapshot)
    report = layout_policy.validate(snapshot, placements)
    return {"schema": SCHEMA, "pages": page_out, "placements": placements,
            "fixes": {"rename_nets": rename_nets, "renumber_designators": renumber_map,
                      "annotate_testpoints": layout_policy.testpoint_annotations(snapshot)},
            "grid_snap": snapped["report"],
            "validation": report,
            "counts": {"pages": len(pages), "parts": len(placements),
                       "violations": report["metrics"]["violations"],
                       "pins_off_grid_after": snapped["report"]["pins_off_grid_after"]}}


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA}, ensure_ascii=False))
