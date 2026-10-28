#!/usr/bin/env python3
"""Offline single-layer, multi-width A* route candidates. Uses measured rules and returns incomplete for missing/unsupported copper. No EDA calls or executable shell output."""
from __future__ import annotations

import argparse
import heapq
import json
import math
import sys

try:
    from . import pcbgeom as G
    from .contract import finite, coverage, provenance, write_json
except ImportError:
    import pcbgeom as G
    from contract import finite, coverage, provenance, write_json

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
SQRT2 = math.sqrt(2.0)

# Requirement per obstacle class; bodies only need the placement gap because they
# are not a DRC item on their own (see the package README).
COPPER_KINDS = ("line", "via", "pad", "fill", "edge", "extra-line", "extra-via", "extra-pad")


def parse_xy(text):
    x, y = text.split(",")
    return float(x), float(y)


def parse_region(text):
    values = [float(part) for part in text.split(",")]
    if len(values) != 4:
        raise ValueError("region wants x0,y0,x1,y1 (got %r)" % text)
    x0, y0, x1, y1 = values
    if x1 <= x0 or y1 <= y0:
        raise ValueError("region must be ordered x0<x1, y0<y1 (got %r)" % text)
    return (x0, y0, x1, y1)


def split_ids(text):
    return [part for part in (text or "").replace(" ", "").split(",") if part]


def default_region(board, margin=80.0):
    if board.outline:
        xs = [pt[0] for pt in board.outline]
        ys = [pt[1] for pt in board.outline]
        return (min(xs), min(ys), max(xs), max(ys))
    xs, ys = [], []
    for line in board.lines:
        xs += [line["x1"], line["x2"]]
        ys += [line["y1"], line["y2"]]
    for pad in board.pads:
        xs.append(pad["x"])
        ys.append(pad["y"])
    if not xs:
        raise ValueError("board dump has no copper and no outline")
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


class Corridor:
    """A search problem: one net, one layer, one frozen board."""

    def __init__(self, board, net, layer, step, region, clr, body_gap=5.0,
                 body_scope="auto", edge_margin=None, use_fills=True,
                 skip_lines=(), skip_vias=(), skip_des=(), extra=()):
        self.board = board
        self.net = net
        self.layer = layer
        self.step = finite(step, 'step', positive=True)
        self.clr = max(finite(clr, 'clearance', nonnegative=True), board.rules['clearance'], board.rules['track_track'])
        self.body_gap = finite(body_gap, 'body_gap', nonnegative=True)
        self.body_scope = body_scope
        self.edge_margin = max(board.rules["copper_to_edge"], finite(edge_margin, "edge_margin", nonnegative=True)) if edge_margin is not None else board.rules["copper_to_edge"]
        self.use_fills = use_fills
        self.skip_lines = set(skip_lines)
        self.skip_vias = set(skip_vias)
        self.skip_des = set(skip_des)
        self.extra = [obj for obj in extra if obj]
        self.region = tuple(finite(v, 'region') for v in region)
        if len(self.region) != 4 or self.region[0] >= self.region[2] or self.region[1] >= self.region[3]:
            raise ValueError('region: ordered bounds required')
        count = getattr(board, 'raw_dump', {}).get('copperLayers')
        allowed = {1,2} | (set(range(15,15+count-2)) if type(count) is int and count >= 2 else set())
        if type(layer) is not int or layer not in allowed:
            raise ValueError('invalid copper layer id')
        self.layers_by_des = board.pad_layers_by_designator()

        self.lines = [line for line in board.lines
                      if line["layer"] == layer and line["net"] != net
                      and line["id"] not in self.skip_lines]
        self.vias = [via for via in board.vias if via["net"] != net
                     and via["id"] not in self.skip_vias]
        self.pads = [pad for pad in board.pads
                     if pad["net"] != net and pad["des"] not in self.skip_des
                     and pad["layer"] in (None, G.LAYER_THROUGH, layer)]
        self.fills = ([fill for fill in board.fills
                       if fill["net"] != net and fill["id"] not in self.skip_lines
                       and fill["layer"] in (None, G.LAYER_THROUGH, layer)]
                      if use_fills else [])
        if body_scope == "none":
            self.bodies = []
        else:
            hard = [body for body in board.bodies
                    if body["des"] not in self.skip_des and board.hard_body(body["des"])]
            if body_scope == "all":
                self.bodies = hard
            else:
                on_layer = board.designators_on(layer, self.layers_by_des)
                self.bodies = [body for body in hard if body["des"] in on_layer]

    # ------------------------------------------------------------------ grid
    def grid(self):
        x0, y0, x1, y1 = self.region
        nx = int(math.floor((x1 - x0) / self.step)) + 1
        ny = int(math.floor((y1 - y0) / self.step)) + 1
        return x0, y0, nx, ny

    def cell_of(self, x, y):
        x0, y0, _nx, _ny = self.grid()
        return (int(round((x - x0) / self.step)), int(round((y - y0) / self.step)))

    def build_mask(self, width):
        finite(width, 'width', positive=True)
        if width < self.board.rules['min_width']:
            raise ValueError('width below board minimum')
        x0, y0, nx, ny = self.grid()
        step = self.step
        mask = bytearray(nx * ny)
        half = width / 2.0

        def mark(bx0, by0, bx1, by1, predicate):
            i0 = max(0, int(math.floor((bx0 - x0) / step)))
            i1 = min(nx - 1, int(math.ceil((bx1 - x0) / step)))
            j0 = max(0, int(math.floor((by0 - y0) / step)))
            j1 = min(ny - 1, int(math.ceil((by1 - y0) / step)))
            for i in range(i0, i1 + 1):
                px = x0 + i * step
                base = i * ny
                for j in range(j0, j1 + 1):
                    if mask[base + j]:
                        continue
                    if predicate(px, y0 + j * step):
                        mask[base + j] = 1

        for line in self.lines:
            reach = half + line["w"] / 2.0 + self.clr + G.prefilter_radius(
                (min(line["x1"], line["x2"]), min(line["y1"], line["y2"]),
                 max(line["x1"], line["x2"]), max(line["y1"], line["y2"])), 0.0)
            mark(min(line["x1"], line["x2"]) - reach, min(line["y1"], line["y2"]) - reach,
                 max(line["x1"], line["x2"]) + reach, max(line["y1"], line["y2"]) + reach,
                 lambda px, py, ln=line: G.d_pt_seg(px, py, ln["x1"], ln["y1"],
                                                    ln["x2"], ln["y2"])
                 < half + ln["w"] / 2.0 + self.clr)
        for via in self.vias:
            reach = via["d"] / 2.0 + half + self.clr
            mark(via["x"] - reach, via["y"] - reach, via["x"] + reach, via["y"] + reach,
                 lambda px, py, v=via: math.hypot(px - v["x"], py - v["y"])
                 < v["d"] / 2.0 + half + self.clr)
        for pad in self.pads:
            rect = G.pad_rect(pad)
            reach = G.prefilter_radius(rect, self.clr + half)
            mark(rect[0] - reach, rect[1] - reach, rect[2] + reach, rect[3] + reach,
                 lambda px, py, p=pad: G.pad_gap_pt(px, py, p) < half + self.clr)
        for fill in self.fills:
            rect = fill["rect"]
            reach = G.prefilter_radius(rect, self.clr + half)
            mark(rect[0] - reach, rect[1] - reach, rect[2] + reach, rect[3] + reach,
                 lambda px, py, r=rect: G.d_pt_rect(px, py, r) < half + self.clr)
        for obj in self.extra:
            if obj.get("net") == self.net:
                continue
            if obj.get("kind") == "line":
                if obj.get("layer") != self.layer:
                    continue
                mark(min(obj["x1"], obj["x2"]) - half - self.clr - 40,
                     min(obj["y1"], obj["y2"]) - half - self.clr - 40,
                     max(obj["x1"], obj["x2"]) + half + self.clr + 40,
                     max(obj["y1"], obj["y2"]) + half + self.clr + 40,
                     lambda px, py, o=obj: G.d_pt_seg(px, py, o["x1"], o["y1"], o["x2"], o["y2"])
                     < half + float(o.get("w", 10)) / 2.0 + self.clr)
            elif obj.get("kind") in ("pad", "via") and obj.get("layer", G.LAYER_THROUGH) \
                    in (None, G.LAYER_THROUGH, self.layer):
                w = float(obj.get("w", obj.get("d", self.clr)))
                h = float(obj.get("h", obj.get("d", self.clr)))
                reach = math.hypot(w, h) / 2.0 + half + self.clr
                mark(obj["x"] - reach, obj["y"] - reach, obj["x"] + reach, obj["y"] + reach,
                     lambda px, py, o=obj, ww=w, hh=h: G.d_pt_rect(
                         px, py, G.rect_of(o["x"], o["y"], ww, hh)) < half + self.clr)
        for body in self.bodies:
            rect = body["rect"]
            reach = G.prefilter_radius(rect, self.body_gap + half)
            mark(rect[0] - reach, rect[1] - reach, rect[2] + reach, rect[3] + reach,
                 lambda px, py, r=rect: G.d_pt_rect(px, py, r) < half + self.body_gap)
        if self.board.outline and self.edge_margin is not None:
            reach = half + self.edge_margin
            for (ax, ay), (bx, by) in G.poly_edges(self.board.outline):
                mark(min(ax, bx) - reach, min(ay, by) - reach,
                     max(ax, bx) + reach, max(ay, by) + reach,
                     lambda px, py, a=(ax, ay), b=(bx, by): G.d_pt_seg(
                         px, py, a[0], a[1], b[0], b[1]) < reach)
            inside = G.raster_inside(self.board.outline, x0, y0, step, nx, ny)
            for index, bit in enumerate(inside):
                if not bit:
                    mask[index] = 1
        return mask, nx, ny

    # ------------------------------------------------------------------- A*
    def search(self, width, allow_corner_cut=False, turn_penalty=1.0):
        finite(width, 'width', positive=True)
        finite(turn_penalty, 'turn_penalty', nonnegative=True)
        x0, y0, nx, ny = self.grid()
        mask, nx, ny = self.build_mask(width)
        step = self.step
        free_cells = sum(1 for bit in mask if not bit)

        def is_free(i, j):
            return 0 <= i < nx and 0 <= j < ny and not mask[i * ny + j]

        start_cell = self.cell_of(*self.start)
        goal_cell = self.cell_of(*self.goal)
        stats = {"grid": [nx, ny], "free_cells": free_cells,
                 "free_pct": round(100.0 * free_cells / float(nx * ny), 1),
                 "turn_penalty": turn_penalty}
        if not is_free(*start_cell) or not is_free(*goal_cell):
            stats["blocked"] = "start" if not is_free(*start_cell) else "goal"
            return None, stats

        def heur(i, j):
            return math.hypot(goal_cell[0] - i, goal_cell[1] - j) * step

        # State carries the incoming direction so a turn can cost extra: without
        # it a 10 mil raster returns staircases instead of straight runs.
        start_state = (start_cell[0], start_cell[1], len(DIRS))
        dist = {start_state: 0.0}
        prev = {}
        heap = [(heur(*start_cell), 0.0, start_state)]
        while heap:
            _, g, state = heapq.heappop(heap)
            i, j, direction = state
            if (i, j) == goal_cell:
                break
            if g > dist.get(state, float("inf")) + 1e-9:
                continue
            for index, (di, dj) in enumerate(DIRS):
                ni, nj = i + di, j + dj
                if not is_free(ni, nj):
                    continue
                if di and dj and not allow_corner_cut:
                    if not (is_free(i + di, j) and is_free(i, j + dj)):
                        continue
                cost = (SQRT2 if di and dj else 1.0) * step
                if direction != len(DIRS) and direction != index:
                    cost += turn_penalty * step
                ng = g + cost
                key = (ni, nj, index)
                if ng < dist.get(key, float("inf")) - 1e-9:
                    dist[key] = ng
                    prev[key] = state
                    heapq.heappush(heap, (ng + heur(ni, nj), ng, key))
        goals = [state for state in dist if (state[0], state[1]) == goal_cell]
        if not goals:
            return None, stats
        state = min(goals, key=lambda item: dist[item])
        cells = [(state[0], state[1])]
        while state != start_state:
            state = prev[state]
            cells.append((state[0], state[1]))
        cells.reverse()
        stats["routed_cost"] = round(dist[min(goals, key=lambda item: dist[item])], 1)
        return [(x0 + i * step, y0 + j * step) for i, j in cells], stats

    # ---------------------------------------------------------- verification
    def worst_conflicts(self, width, points):
        """Exact-shape conflict list for one planned polyline."""
        half = width / 2.0
        worst = {}

        def consider(gap, kind, **info):
            entry = worst.get(kind)
            if entry is None or gap < entry["gap"]:
                info.update({"gap": gap, "kind": kind})
                worst[kind] = info

        for index in range(len(points) - 1):
            (x1, y1), (x2, y2) = points[index], points[index + 1]
            for line in self.lines:
                consider(G.d_seg_seg((line["x1"], line["y1"]), (line["x2"], line["y2"]),
                                     (x1, y1), (x2, y2)) - half - line["w"] / 2.0,
                         "line", net=line["net"], id=line["id"], layer=line["layer"])
            for via in self.vias:
                consider(G.d_pt_seg(via["x"], via["y"], x1, y1, x2, y2)
                         - half - via["d"] / 2.0, "via", net=via["net"], id=via["id"])
            for pad in self.pads:
                consider(G.pad_gap_seg(x1, y1, x2, y2, pad) - half,
                         "pad", net=pad["net"], des=pad["des"])
            for fill in self.fills:
                consider(G.d_seg_rect(x1, y1, x2, y2, fill["rect"]) - half,
                         "fill", id=fill["id"])
            for body in self.bodies:
                consider(G.d_seg_rect(x1, y1, x2, y2, body["rect"]) - half,
                         "body", des=body["des"])
            if self.board.outline and self.edge_margin is not None:
                consider(G.d_seg_poly(x1, y1, x2, y2, self.board.outline) - half
                         - self.edge_margin, "edge")
            for obj in self.extra:
                if obj.get("net") == self.net:
                    continue
                if obj.get("kind") == "line" and obj.get("layer") == self.layer:
                    consider(G.d_seg_seg((obj["x1"], obj["y1"]), (obj["x2"], obj["y2"]),
                                         (x1, y1), (x2, y2))
                             - half - float(obj.get("w", 10)) / 2.0,
                             "extra-line", net=obj.get("net"), id=obj.get("id"))
                elif obj.get("kind") == "via":
                    consider(G.d_pt_seg(obj["x"], obj["y"], x1, y1, x2, y2)
                             - half - float(obj.get("d", self.board.rules["via_diameter"])) / 2.0,
                             "extra-via", net=obj.get("net"), id=obj.get("id"))
                elif obj.get("kind") == "pad" and obj.get("layer", G.LAYER_THROUGH) \
                        in (None, G.LAYER_THROUGH, self.layer):
                    rect = G.rect_of(obj["x"], obj["y"], float(obj["w"]), float(obj["h"]))
                    consider(G.d_seg_rect(x1, y1, x2, y2, rect) - half,
                             "extra-pad", net=obj.get("net"), des=obj.get("des"))
        return worst

    def violations(self, width, points):
        worst = self.worst_conflicts(width, points)
        out = []
        for kind, entry in sorted(worst.items()):
            required = self.body_gap if kind == "body" else (0.0 if kind == "edge" else self.clr)
            if entry["gap"] < required - 1e-9:
                out.append(dict(entry, required=required))
        return worst, out



def simplify(points):
    """Drop collinear midpoint samples without moving the path."""
    if len(points) < 3:
        return list(points)
    out = [points[0]]
    for index in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = out[-1], points[index], points[index + 1]
        if abs((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1)) > 1e-9:
            out.append((x1, y1))
    out.append(points[-1])
    return out


def aligned_45(x1, y1, x2, y2, tol=1.0):
    """True when the segment is within ``tol`` degrees of a 45/90 direction."""
    dx, dy = x2 - x1, y2 - y1
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return False
    angle = math.degrees(math.atan2(dy, dx)) % 45.0
    return angle < tol or angle > 45.0 - tol


def shortcut(cor, width, points, max_tries=80, style="45"):
    """Greedy shortcut pass: merge grid staircases that verify as one segment.

    A 10 mil raster turns a 45 degree run into many 10 mil steps; writing those
    to the editor costs one CLI call each and reads badly.  This pass jumps as
    far ahead as the geometry allows, keeping the classic orthogonal / 45 degree
    routing style and re-checking every candidate with the same engine.
    """
    if len(points) < 3:
        return list(points)
    out = [points[0]]
    index = 1
    while index < len(points) - 1:
        chosen = None
        tries = 0
        for candidate in range(len(points) - 1, index, -1):
            tries += 1
            if tries > max_tries:
                break
            x1, y1 = out[-1]
            x2, y2 = points[candidate]
            if style == "45" and not aligned_45(x1, y1, x2, y2):
                continue
            if cor.violations(width, [(x1, y1), (x2, y2)])[1]:
                continue
            chosen = candidate
            break
        if chosen is None:
            out.append(points[index])
            index += 1
        else:
            out.append(points[chosen])
            index = chosen + 1
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def route(cor, width, allow_corner_cut=False, style="45", turn_penalty=1.0):
    points, stats = cor.search(width, allow_corner_cut, turn_penalty)
    result = {"width": width, "feasible": False, "stats": stats}
    if not points:
        return result
    points = simplify([cor.start] + points + [cor.goal])
    points = shortcut(cor, width, points, style=style)
    result["raw_points"] = len(points)
    points = simplify(points)
    worst, violations = cor.violations(width, points)
    length = sum(math.hypot(points[i + 1][0] - points[i][0],
                            points[i + 1][1] - points[i][1])
                 for i in range(len(points) - 1))
    result.update({
        "feasible": not violations,
        "path_mil": round(length, 1),
        "points": [[round(x, 2), round(y, 2)] for x, y in points],
        "worst": worst,
        "violations": violations,
    })
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Wide-corridor A* search on a PCB dump")
    ap.add_argument("dump")
    ap.add_argument("--net", required=True)
    ap.add_argument("--start", required=True, help="x,y mil")
    ap.add_argument("--goal", required=True, help="x,y mil")
    ap.add_argument("--layer", type=int, default=G.LAYER_TOP)
    ap.add_argument("--widths", default=None, help="comma list, e.g. 60,50,40,30")
    ap.add_argument("--w", type=float, default=None, help="single width shortcut")
    ap.add_argument("--step", type=float, default=10.0, help="grid pitch, mil")
    ap.add_argument("--clr", type=float, default=None, help="required gap, mil")
    ap.add_argument("--region", default=None, help="x0,y0,x1,y1 (default: outline)")
    ap.add_argument("--body-gap", type=float, default=5.0)
    ap.add_argument("--body-scope", choices=("auto", "all", "none"), default="auto")
    ap.add_argument("--edge-margin", type=float, default=None)
    ap.add_argument("--ignore-outline", action="store_true")
    ap.add_argument("--no-fills", action="store_true")
    ap.add_argument("--skip-line", default="", help="comma ids treated as absent")
    ap.add_argument("--skip-via", default="", help="comma ids treated as absent")
    ap.add_argument("--skip-des", default="", help="comma designators ignored")
    ap.add_argument("--allow-corner-cut", action="store_true")
    ap.add_argument("--turn-penalty", type=float, default=1.0,
                    help="extra cost per turn, in grid steps")
    ap.add_argument("--style", choices=("45", "any"), default="45",
                    help="keep the shortcut pass on 45/90 directions")
    ap.add_argument("--max-cells", type=int, default=500000)
    ap.add_argument("--emit-cli", action="store_true", help="print easycirq commands")
    ap.add_argument("--emit-doc", default="PCB1")
    ap.add_argument("--verbose", action="store_true", help="print every path point")
    ap.add_argument("--json", dest="out")
    args = ap.parse_args(argv)

    try:
        if args.emit_cli:
            raise ValueError('--emit-cli removed: use JSON candidate with source binding; no unguarded delete/create commands')
        board = G.Board.load(args.dump)
        start = parse_xy(args.start)
        goal = parse_xy(args.goal)
    except Exception as exc:                                   # noqa: BLE001
        print("error: %s" % exc, file=sys.stderr)
        return 2
    layers = [line["layer"] for line in board.lines if line["layer"] is not None]
    if args.net not in {line["net"] for line in board.lines} \
            and args.net not in {pad["net"] for pad in board.pads}:
        print("error: net %r has no tracks or pads on this board" % args.net,
              file=sys.stderr)
        return 2
    if layers and args.layer not in set(layers):
        print("note: layer %d has no tracks in this dump (layers present: %s)"
              % (args.layer, sorted(set(layers))), file=sys.stderr)

    try:
        width_list = ([float(args.w)] if args.w is not None else
                      [float(part) for part in (args.widths or "60,50,40,30").split(',') if part.strip()])
        if args.clr is not None:
            finite(args.clr, 'clearance', nonnegative=True)
        if any(w < board.rules['min_width'] for w in width_list):
            raise ValueError('width below board minimum')
    except (ValueError, TypeError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 2
    if not width_list or any(not math.isfinite(w) or w <= 0 for w in width_list):
        print("error: positive finite widths required", file=sys.stderr)
        return 2
    clr = board.rules["clearance"] if args.clr is None else max(board.rules["clearance"], args.clr)
    try:
        for v in (*start, *goal):
            finite(v, 'endpoint')
        finite(args.turn_penalty, 'turn_penalty', nonnegative=True)
        if args.max_cells <= 0:
            raise ValueError('max-cells must be positive')
        region = parse_region(args.region) if args.region else default_region(board)
        cor = Corridor(
            board, args.net, args.layer, args.step, region, clr,
            body_gap=args.body_gap, body_scope=args.body_scope,
            edge_margin=None if args.ignore_outline else args.edge_margin,
            use_fills=not args.no_fills,
            skip_lines=split_ids(args.skip_line), skip_vias=split_ids(args.skip_via),
            skip_des=split_ids(args.skip_des),
        )
        cor.start, cor.goal = start, goal
        x0, y0, nx, ny = cor.grid()
        if nx * ny > args.max_cells:
            print("error: region %.0fx%.0f mil at %.0f mil step needs %d cells "
                  "(> --max-cells %d); narrow the region or coarsen --step"
                  % (region[2] - region[0], region[3] - region[1], args.step,
                     nx * ny, args.max_cells), file=sys.stderr)
            return 2
    except Exception as exc:                                   # noqa: BLE001
        print("error: %s" % exc, file=sys.stderr)
        return 2

    print("net %s  layer %d  start %s  goal %s  clr %.2f  step %.0f  region %s"
          % (args.net, args.layer, args.start, args.goal, clr, args.step,
             "(%.0f,%.0f)-(%.0f,%.0f)" % region))
    clr = cor.clr
    report = {"schema": "power-corridor/v1", "source": provenance(args.dump, board),
              "coverage": coverage(board), "live_verified": False, "board": args.dump, "net": args.net, "layer": args.layer,
              "clr": clr, "step": args.step, "region": list(region),
              "start": list(start), "goal": list(goal), "widths": []}
    best = None
    for width in sorted(width_list, reverse=True):
        result = route(cor, width, args.allow_corner_cut, style=args.style,
                       turn_penalty=args.turn_penalty)
        report["widths"].append(result)
        if "path_mil" not in result:
            stats = result["stats"]
            note = ("start blocked" if stats.get("blocked") == "start"
                    else "goal blocked" if stats.get("blocked") == "goal"
                    else "%.1f%% of %dx%d cells free"
                    % (stats["free_pct"], stats["grid"][0], stats["grid"][1]))
            print("  w=%5.1f mil  no corridor (%s)" % (width, note))
            continue
        min_gap = min((entry["gap"] for entry in result["worst"].values()),
                      default=float("inf"))
        print("  w=%5.1f mil  path %7.1f mil  %2d pts  min gap %5.2f mil%s"
              % (width, result["path_mil"], len(result["points"]), min_gap,
                 "" if result["feasible"] else "  VIOLATION"))
        for entry in result["violations"]:
            print("      violation: %s" % entry)
        if result["feasible"] and best is None:
            best = result
    if best is None:
        print("verdict: NO FEASIBLE CORRIDOR - route a different layer, widen the "
              "region, allow more vias, or relax the width target")
    else:
        print("verdict: widest modeled corridor = %.1f mil, %.1f mil long, "
              "%d segments" % (best["width"], best["path_mil"], len(best["points"]) - 1))
        if args.verbose or len(best["points"]) <= 12:
            for (x, y) in best["points"]:
                print("   (%.1f, %.1f)" % (x, y))
        else:
            print("   %d points - use --verbose or --json for coordinates"
                  % len(best["points"]))
        report["recommended"] = best["width"]
        feasible = [item for item in report["widths"] if item.get("feasible")]
        better = [item for item in feasible[1:]
                  if len(item["points"]) <= len(best["points"])
                  and item["path_mil"] < best["path_mil"] - 1.0]
        if better:
            alt = better[0]                       # widest of the shorter/cleaner set
            print("note: w=%.1f mil is %.1f mil shorter with %d segments (vs %d) "
                  "and still above the target if the current width is not mandatory"
                  % (alt["width"], best["path_mil"] - alt["path_mil"],
                     len(alt["points"]) - 1, len(best["points"]) - 1))
            report["alternatives"] = [{"width": item["width"],
                                       "path_mil": item["path_mil"],
                                       "segments": len(item["points"]) - 1}
                                      for item in feasible[1:]]
    excluded = bool(args.skip_line or args.skip_via or args.skip_des or args.no_fills or args.ignore_outline or args.body_scope == 'none')
    if excluded:
        report['coverage']['gaps'].append('caller_excluded_obstacles')
        report['coverage']['complete'] = False
    report['status'] = ('incomplete' if not report['coverage']['complete'] else
                        ('candidate' if best is not None else 'not_found_within_grid'))
    if args.out:
        write_json(args.out, report)
        print("wrote %s" % args.out)
    return 2 if report['status'] == 'incomplete' else (0 if best is not None else 1)


if __name__ == "__main__":
    sys.exit(main())
