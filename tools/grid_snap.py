"""Snap layout anchors onto the 5-unit schematic grid - pin by pin, before writes.

Why this module exists (2026-10-30, C board): EasyEDA attaches a net label with a
20-unit stub whose *pin end* must sit on the schematic grid (``SCH_GRID = 5`` in
``connector/src/actions.ts``: a horizontal stub checks the pin's **Y**, a vertical
stub checks its **X**).  The re-layout plan ``smoke-b10-4-C.json`` carried
anchors such as ``C1 = (682.8, 760.5)``, so the live pin ``C1:1`` landed on
``(662.8, 760.5)`` - off grid - and every connect was rejected
(``verify5.log``: ``FAIL C1:1=+3V3 (left)``, then the channel reported degraded).

The fix is *not* a new layout algorithm.  A part's pin offsets ``(dx, dy)`` are
already multiples of 5, so snapping the **anchor** to the grid puts every pin of
that part on the grid.  This module performs that snap and refuses to hand back a
plan that the EDA would still reject:

a. every ``geometry.parts[*].pins[*]`` offset ``(dx, dy)`` is a multiple of the
   grid - otherwise the part can never be fully on-grid wherever it is placed;
b. after snapping, every pin ``x + dx`` / ``y + dy`` is on the grid (tolerance
   ``TOL``) - the stronger check; the EDA only needs one axis per stub direction;
c. no two parts overlap (see ``OVERLAP RULE`` below);
d. every pin stays inside the sheet.  Page bounds are read from
   ``apply_engine.SHEET`` (imported lazily to avoid an import cycle) so there is
   no second page model here.

Any of (a)-(d) raises ``ValueError`` and **no plan is returned**: a half-snapped
plan is worse than no plan, because it burns the live write channel.

OVERLAP RULE - two parts overlap when their *pin-extent boxes* (min/max of
``x + dx`` / ``y + dy``) intersect with a strictly positive area
(``min(rights) - max(lefts) > gap`` on both axes), or when any of their pins
share the exact same page coordinate.  Touching along a shared edge is allowed: a
decoupling capacitor legitimately sits on the same pin row as its IC, so boxes
that merely abut are not a collision.  ``gap`` defaults to 0.0 (any positive-area
overlap is reported); pass a positive ``gap`` to demand clearance.  The plan's
``ew``/``eh`` envelopes are deliberately *not* used - they are label/channel
reservations and neighbouring envelopes overlap by design.

Schema: ``easycirq-grid-snap/v1``.
"""

from __future__ import annotations

import json
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import pin_geometry  # noqa: E402  (shared rotation table / geometry schema)

SCHEMA = "easycirq-grid-snap/v1"
GRID = 5.0
TOL = 1e-6
DEFAULT_GAP = 0.0


# --------------------------------------------------------------------------- #
# grid primitives
# --------------------------------------------------------------------------- #
def snap_value(value, grid=GRID):
    """Nearest grid multiple of ``value`` (``round(v / 5) * 5``).

    Ties (``v`` at an exact half-grid) are equally close in both directions, so
    Python's round-half-to-even is harmless here.
    """
    return round(float(value) / grid) * grid


def on_grid(value, grid=GRID, tol=TOL):
    """True when ``value`` is a multiple of ``grid`` (within ``tol``)."""
    value = float(value)
    return abs(value - round(value / grid) * grid) <= tol


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def placements_of(plan):
    """``{ref: {x, y, ...}}`` from a plan dict or from a bare placements map."""
    if not isinstance(plan, dict):
        raise ValueError("grid_snap: plan must be a mapping, got %s"
                         % type(plan).__name__)
    inner = plan.get("placements")
    return inner if isinstance(inner, dict) else plan


def pin_offsets(geometry):
    """Yield ``(ref, pin, dx, dy)`` for every pin of ``geometry``, sorted."""
    parts = (geometry or {}).get("parts") or {}
    for ref in sorted(parts):
        pins = (parts[ref] or {}).get("pins") or {}
        for number in sorted(pins):
            dx = _num((pins[number] or {}).get("dx"))
            dy = _num((pins[number] or {}).get("dy"))
            if dx is None or dy is None:
                raise ValueError("grid_snap: pin %s:%s has no numeric dx/dy in the "
                                 "geometry" % (ref, number))
            yield str(ref), str(number), dx, dy


def page_bounds():
    """Sheet bounds from the apply engine (single source of truth)."""
    import apply_engine  # local import: apply_engine imports this module

    return tuple(apply_engine.SHEET)


# --------------------------------------------------------------------------- #
# the four checks
# --------------------------------------------------------------------------- #
def offset_violations(geometry, *, grid=GRID, tol=TOL):
    """(a) pins whose own ``(dx, dy)`` is not a grid multiple - unplaceable part."""
    bad = []
    for ref, pin, dx, dy in pin_offsets(geometry):
        if not (on_grid(dx, grid, tol) and on_grid(dy, grid, tol)):
            bad.append({"ref": ref, "pin": pin, "dx": dx, "dy": dy})
    return bad


def pin_grid_violations(placements, geometry, *, grid=GRID, tol=TOL):
    """(b) pins that are still off grid at the planned anchor ``(x + dx)``."""
    bad = []
    for ref, pin, dx, dy in pin_offsets(geometry):
        place = placements.get(ref)
        if place is None:
            continue
        x = _num(place.get("x"))
        y = _num(place.get("y"))
        if x is None or y is None:
            raise ValueError("grid_snap: placement %s has no numeric x/y" % ref)
        px, py = x + dx, y + dy
        if not (on_grid(px, grid, tol) and on_grid(py, grid, tol)):
            bad.append({"ref": ref, "pin": pin, "x": px, "y": py})
    return bad


def pin_boxes(placements, geometry):
    """``{ref: (min_x, min_y, max_x, max_y)}`` of the pin extents at the plan."""
    boxes = {}
    for ref in (geometry or {}).get("parts") or {}:
        place = placements.get(ref)
        pins = ((geometry["parts"][ref] or {}).get("pins") or {})
        if place is None or not pins:
            continue
        x = _num(place.get("x"))
        y = _num(place.get("y"))
        if x is None or y is None:
            raise ValueError("grid_snap: placement %s has no numeric x/y" % ref)
        xs = [x + float((p or {}).get("dx") or 0.0) for p in pins.values()]
        ys = [y + float((p or {}).get("dy") or 0.0) for p in pins.values()]
        boxes[ref] = (min(xs), min(ys), max(xs), max(ys))
    return boxes


def overlaps(placements, geometry, *, gap=DEFAULT_GAP):
    """(c) part pairs whose pin-extent boxes overlap with positive area."""
    boxes = pin_boxes(placements, geometry)
    refs = sorted(boxes)
    found = []
    for index, ref in enumerate(refs):
        ax0, ay0, ax1, ay1 = boxes[ref]
        for other in refs[index + 1:]:
            bx0, by0, bx1, by1 = boxes[other]
            if min(ax1, bx1) - max(ax0, bx0) > gap and \
                    min(ay1, by1) - max(ay0, by0) > gap:
                found.append({"a": ref, "b": other,
                              "a_box": [round(v, 1) for v in boxes[ref]],
                              "b_box": [round(v, 1) for v in boxes[other]]})
    return found


def pin_collisions(placements, geometry):
    """Pins of different parts sharing one exact page coordinate."""
    seen, found = {}, []
    for ref, pin, dx, dy in pin_offsets(geometry):
        place = placements.get(ref)
        if place is None:
            continue
        point = (_num(place.get("x")) + dx, _num(place.get("y")) + dy)
        if point in seen:
            found.append({"x": point[0], "y": point[1],
                          "pins": [seen[point], "%s:%s" % (ref, pin)]})
        else:
            seen[point] = "%s:%s" % (ref, pin)
    return found


def out_of_page(placements, geometry, *, page=None):
    """(d) pins that fall outside the sheet."""
    x0, y0, x1, y1 = page or page_bounds()
    found = []
    for ref, pin, dx, dy in pin_offsets(geometry):
        place = placements.get(ref)
        if place is None:
            continue
        px = _num(place.get("x")) + dx
        py = _num(place.get("y")) + dy
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            found.append({"ref": ref, "pin": pin, "x": px, "y": py})
    return found


# --------------------------------------------------------------------------- #
# geometry from an offline snapshot (no EDA, no capture)
# --------------------------------------------------------------------------- #
def geometry_from_snapshot(snapshot):
    """Build ``easycirq-pin-geometry/v1`` from a snapshot carrying pin coords.

    Accepts a page snapshot (``components[*].ref|designator``, ``x``/``y`` and
    ``pins[*].x|y|pinNumber|rotation|net``) or one that already stores pin
    offsets (``dx``/``dy``).  Returns an empty ``parts`` map when the snapshot has
    no usable coordinates - callers then snap anchors only.
    """
    parts = {}
    for comp in (snapshot or {}).get("components") or []:
        ref = comp.get("ref") or comp.get("designator")
        pins = comp.get("pins") or []
        if not ref or not pins:
            continue
        cx = _num(comp.get("x"))
        cy = _num(comp.get("y"))
        out = {}
        for pin in pins:
            number = pin.get("pinNumber", pin.get("number", pin.get("pin")))
            if number is None:
                continue
            dx = _num(pin.get("dx"))
            dy = _num(pin.get("dy"))
            if dx is None or dy is None:
                px, py = _num(pin.get("x")), _num(pin.get("y"))
                if None in (cx, cy, px, py):
                    continue
                dx, dy = round(px - cx, 1), round(py - cy, 1)
            rotation = int(pin.get("rotation") or 0) % 360
            out[str(number)] = {"dx": dx, "dy": dy, "rotation": rotation,
                                "side": pin_geometry.SIDE_BY_ROTATION.get(rotation, "right"),
                                "net": pin.get("net")}
        if out:
            parts[ref] = {"cx": cx, "cy": cy, "pins": out}
    return {"schema": pin_geometry.SCHEMA, "parts": parts,
            "counts": {"parts": len(parts),
                       "pins": sum(len(p["pins"]) for p in parts.values())}}


# --------------------------------------------------------------------------- #
# the plan-level entry point
# --------------------------------------------------------------------------- #
def _fmt(items, key, limit=20):
    shown = ["%s:%s" % (item.get("ref"), item.get("pin")) if key == "pin"
             else str(item.get(key)) for item in items[:limit]]
    more = "" if len(items) <= limit else " (+%d more)" % (len(items) - limit)
    return ", ".join(shown) + more


def snap_plan(plan, geometry, *, page=None, grid=GRID, tol=TOL, gap=DEFAULT_GAP,
              strict=True):
    """Snap every anchor to the grid and verify the result pin by pin.

    ``plan`` = a plan dict with ``placements`` (or a bare placements map);
    ``geometry`` = ``easycirq-pin-geometry/v1`` (``parts[ref].pins[pin].dx/dy``).
    ``page`` = ``(x0, y0, x1, y1)`` sheet bounds, defaults to
    ``apply_engine.SHEET``.  ``strict`` = also refuse overlaps / shared pins (c);
    with ``strict=False`` those are reported but do not raise, for callers that
    must inspect a plan the layout stage produced.

    Returns ``{"placements": {...snapped...}, "report": {...}}``.

    Raises ``ValueError`` - and returns nothing - when (a) a pin offset is not a
    grid multiple, (b) a pin is still off grid after snapping, (c) two parts
    overlap (``OVERLAP RULE``) or two pins share a coordinate (only when
    ``strict``), or (d) a pin falls outside the sheet.  The anchor is snapped with
    ``round(v / grid) * grid``; an ``x0``/``y0`` envelope in the placement is
    shifted by the same displacement so the envelope keeps tracking its anchor.
    """
    placements = placements_of(plan)
    parts = (geometry or {}).get("parts") or {}
    bounds = tuple(page) if page else page_bounds()

    # (a) an off-grid pin offset can never be fixed by moving the anchor
    bad_offsets = offset_violations(geometry, grid=grid, tol=tol)
    if bad_offsets:
        raise ValueError(
            "grid_snap: %d pin offset(s) are not multiples of %g, so their part "
            "can never be fully on-grid: %s"
            % (len(bad_offsets), grid, _fmt(bad_offsets, "pin")))

    snapped, per_part = {}, {}
    worst = 0.0
    moved = 0
    before_pins, after_pins = [], []
    pins_total = 0
    for ref in sorted(placements):
        place = placements[ref]
        x, y = _num((place or {}).get("x")), _num((place or {}).get("y"))
        if x is None or y is None:
            raise ValueError("grid_snap: placement %s has no numeric x/y" % ref)
        sx, sy = snap_value(x, grid), snap_value(y, grid)
        shift_x, shift_y = sx - x, sy - y
        worst = max(worst, abs(shift_x), abs(shift_y))
        if shift_x or shift_y:
            moved += 1
        out = dict(place)
        out["x"], out["y"] = sx, sy
        for key, shift in (("x0", shift_x), ("y0", shift_y)):
            if _num(place.get(key)) is not None:
                out[key] = round(_num(place[key]) + shift, 6)
        snapped[ref] = out
        info = parts.get(ref) or {}
        pin_count = len(info.get("pins") or {})
        pins_total += pin_count
        ref_before = ref_after = 0
        for number, pin in (info.get("pins") or {}).items():
            dx = float((pin or {}).get("dx") or 0.0)
            dy = float((pin or {}).get("dy") or 0.0)
            if not (on_grid(x + dx, grid, tol) and on_grid(y + dy, grid, tol)):
                ref_before += 1
                before_pins.append("%s:%s" % (ref, number))
            if not (on_grid(sx + dx, grid, tol) and on_grid(sy + dy, grid, tol)):
                ref_after += 1
                after_pins.append("%s:%s" % (ref, number))
        per_part[ref] = {"x": x, "y": y, "x_snapped": sx, "y_snapped": sy,
                         "shift": [round(shift_x, 3), round(shift_y, 3)],
                         "pins": pin_count,
                         "pins_off_grid_before": ref_before,
                         "pins_off_grid_after": ref_after}

    # (b) pins on grid, (c) no overlap / no shared pin, (d) pins inside the sheet
    after_grid = pin_grid_violations(snapped, geometry, grid=grid, tol=tol)
    box_hits = overlaps(snapped, geometry, gap=gap)
    collisions = pin_collisions(snapped, geometry)
    outside = out_of_page(snapped, geometry, page=bounds)
    problems = []
    if after_grid:
        problems.append("%d pin(s) still off the %g-grid after snapping: %s"
                        % (len(after_grid), grid, _fmt(after_grid, "pin")))
    if strict and box_hits:
        problems.append("%d overlapping part pair(s): %s"
                        % (len(box_hits),
                           ", ".join("%s/%s" % (h["a"], h["b"]) for h in box_hits[:20])))
    if strict and collisions:
        problems.append("%d shared pin coordinate(s): %s"
                        % (len(collisions),
                           ", ".join("/".join(c["pins"]) for c in collisions[:20])))
    if outside:
        problems.append("%d pin(s) outside the sheet %s: %s"
                        % (len(outside), list(bounds), _fmt(outside, "pin")))
    if problems:
        raise ValueError("grid_snap: refused to produce a plan - " + "; ".join(problems))

    report = {
        "schema": SCHEMA,
        "grid": grid,
        "tolerance": tol,
        "gap": gap,
        "strict": strict,
        "page": list(bounds),
        "parts": len(placements),
        "parts_with_geometry": len([r for r in placements if r in parts]),
        "parts_without_geometry": sorted(r for r in placements if r not in parts),
        "geometry_parts_unplaced": sorted(r for r in parts if r not in placements),
        "moved_parts": moved,
        "pins_total": pins_total,
        "pins_off_grid_before": len(before_pins),
        "pins_off_grid_after": len(after_pins),
        "off_grid_pins_before": before_pins,
        "off_grid_pins_after": after_pins,
        "max_displacement": round(worst, 3),
        "overlaps": box_hits,
        "pin_collisions": collisions,
        "out_of_page": outside,
        "pin_offset_violations": [],
        "per_part": per_part,
    }
    return {"placements": snapped, "report": report}


# --------------------------------------------------------------------------- #
# CLI: plan + geometry -> snapped plan (and report); no EDA involved
# --------------------------------------------------------------------------- #
def _cli(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Snap plan anchors to the schematic grid and verify every pin.")
    parser.add_argument("--plan", required=True, help="plan JSON (with placements)")
    parser.add_argument("--geometry", required=True, help="pin geometry JSON")
    parser.add_argument("--out", help="write the snapped plan here")
    parser.add_argument("--report", help="write the grid_snap report here")
    parser.add_argument("--source", help="value for the plan's 'source' field")
    parser.add_argument("--snapshot", help="optional snapshot for layout_policy")
    parser.add_argument("--page", help="x0,y0,x1,y1 sheet bounds override")
    args = parser.parse_args(argv)

    plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
    geometry = json.loads(pathlib.Path(args.geometry).read_text(encoding="utf-8"))
    page = tuple(float(v) for v in args.page.split(",")) if args.page else None
    result = snap_plan(plan, geometry, page=page)
    report = result["report"]

    if args.snapshot:
        import layout_policy

        snapshot = json.loads(pathlib.Path(args.snapshot).read_text(encoding="utf-8"))
        before = layout_policy.validate(snapshot, placements_of(plan))
        after = layout_policy.validate(snapshot, result["placements"])
        report["layout_policy"] = {
            "snapshot": str(args.snapshot),
            "violations_before": before["metrics"]["violations"],
            "violations_after": after["metrics"]["violations"],
            "verdict_after": after["verdict"],
            "rules_after": sorted({v.get("rule") for v in after["violations"]}),
            "detail_after": after["violations"],
        }

    if args.out:
        snapped = dict(plan)
        snapped["placements"] = result["placements"]
        snapped["grid_snap"] = report
        snapped["source"] = args.source or pathlib.Path(args.plan).name
        pathlib.Path(args.out).write_text(
            json.dumps(snapped, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.report:
        payload = dict(report)
        payload["commands"] = ["python tools/grid_snap.py " + " ".join(sys.argv[1:])]
        pathlib.Path(args.report).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("parts", "pins_total", "pins_off_grid_before",
                       "pins_off_grid_after", "max_displacement")},
                     ensure_ascii=False))
    print("overlaps=%d pin_collisions=%d out_of_page=%d"
          % (len(report["overlaps"]), len(report["pin_collisions"]),
             len(report["out_of_page"])))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
