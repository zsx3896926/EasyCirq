"""Shared clearance candidates over measured copper. Actual copper-layer overlap, explicit body keepouts and conservative shape bounds; not native DRC."""
from __future__ import annotations

try:
    from . import pcbgeom as G
except ImportError:
    import pcbgeom as G


def conflict(gap, kind, **info):
    entry = {"gap": float(gap), "kind": kind}
    entry.update(info)
    return entry


class Obstacles:
    """Clearance queries against a frozen board plus a set of planned objects."""

    def __init__(self, board, skip_line_ids=(), skip_via_ids=(), skip_designators=(),
                 extra=(), rules=None):
        self.board = board
        self.rules = dict(board.rules)
        if rules:
            self.rules.update(rules)
        self.clr = float(self.rules["clearance"])
        self.track_track = float(self.rules["track_track"])
        self.via_d = float(self.rules["via_diameter"])
        self.skip_lines = set(skip_line_ids)
        self.skip_vias = set(skip_via_ids)
        self.skip_des = set(skip_designators)
        self.extra = [o for o in extra if o]
        self._pads = [p for p in board.pads if p["des"] not in self.skip_des]
        self._vias = [v for v in board.vias if v["id"] not in self.skip_vias]
        self._lines = [l for l in board.lines if l["id"] not in self.skip_lines]
        self._bodies = [b for b in board.bodies if b["des"] not in self.skip_des]
        self._same_net_body_des = {}
        for pad in board.pads:
            self._same_net_body_des.setdefault(pad["net"], set()).add(pad["des"])

    # ------------------------------------------------------------------ lines
    def check_line(self, net, layer, width, x1, y1, x2, y2, required=None):
        """Query one planned track.  Returns (min_gap, worst, conflicts)."""
        required = self.clr if required is None else float(required)
        out = []
        half = width / 2.0
        for line in self._lines:
            if (net is not None and line["net"] == net) or not layers_overlap(line["layer"], layer):
                continue
            gap = G.d_seg_seg((line["x1"], line["y1"]), (line["x2"], line["y2"]),
                              (x1, y1), (x2, y2)) - half - line["w"] / 2.0
            out.append(conflict(gap, "line", net=line["net"], id=line["id"],
                                layer=line["layer"], width=line["w"]))
        for via in self._vias:
            if (net is not None and via["net"] == net):
                continue
            gap = G.d_pt_seg(via["x"], via["y"], x1, y1, x2, y2) - half - via["d"] / 2.0
            out.append(conflict(gap, "via", net=via["net"], id=via["id"]))
        for pad in self._pads:
            if (net is not None and pad["net"] == net):
                continue
            if not layers_overlap(pad["layer"], layer):
                continue
            rect = G.rect_of(pad["x"], pad["y"], pad["w"], pad["h"])
            gap = G.pad_gap_seg(x1, y1, x2, y2, pad) - half
            out.append(conflict(gap, "pad", net=pad["net"], des=pad["des"]))
        for body in self._bodies:
            des = body["des"]
            gap = G.d_seg_rect(x1, y1, x2, y2, body["rect"]) - half
            kind = "body" if self.board.hard_body(des) else "body-soft"
            out.append(conflict(gap, kind, des=des))
        for obj in self.extra:
            entry = self._extra_line(obj, net, layer, half, x1, y1, x2, y2)
            if entry:
                out.append(entry)
        self._environment(out, net, layer, segment=(x1,y1,x2,y2), radius=half, required=required)
        return self._verdict(out, required)

    def _extra_line(self, obj, net, layer, half, x1, y1, x2, y2):
        if net is not None and obj.get("net") == net:
            return None
        kind = obj.get("kind")
        if kind == "line":
            if not layers_overlap(obj.get("layer"), layer):
                return None
            gap = G.d_seg_seg((obj["x1"], obj["y1"]), (obj["x2"], obj["y2"]),
                              (x1, y1), (x2, y2)) - half - float(obj.get("w", 10)) / 2.0
            return conflict(gap, "extra-line", net=obj.get("net"), id=obj.get("id"))
        if kind == "via":
            gap = G.d_pt_seg(obj["x"], obj["y"], x1, y1, x2, y2) \
                - half - float(obj.get("d", self.via_d)) / 2.0
            return conflict(gap, "extra-via", net=obj.get("net"), id=obj.get("id"))
        if kind == "pad":
            if not layers_overlap(obj.get("layer"), layer):
                return None
            rect = G.rect_of(obj["x"], obj["y"], obj["w"], obj["h"])
            gap = G.d_seg_rect(x1, y1, x2, y2, rect) - half
            return conflict(gap, "extra-pad", net=obj.get("net"), des=obj.get("des"))
        return None

    # ------------------------------------------------------------------- vias
    def check_via(self, net, x, y, diameter=None):
        diameter = self.via_d if diameter is None else float(diameter)
        out = []
        half = diameter / 2.0
        for line in self._lines:
            if (net is not None and line["net"] == net):
                continue
            gap = G.d_pt_seg(x, y, line["x1"], line["y1"], line["x2"], line["y2"]) \
                - half - line["w"] / 2.0
            out.append(conflict(gap, "line", net=line["net"], id=line["id"],
                                layer=line["layer"], width=line["w"]))
        for via in self._vias:
            if (net is not None and via["net"] == net):
                continue
            gap = ((x - via["x"]) ** 2 + (y - via["y"]) ** 2) ** 0.5 - half - via["d"] / 2.0
            out.append(conflict(gap, "via", net=via["net"], id=via["id"]))
        for pad in self._pads:
            if (net is not None and pad["net"] == net):
                continue
            rect = G.rect_of(pad["x"], pad["y"], pad["w"], pad["h"])
            gap = G.pad_gap_pt(x, y, pad) - half
            if gap < -1.0:                       # inside the pad: distance is undefined
                gap = -1.0
            out.append(conflict(gap, "pad", net=pad["net"], des=pad["des"]))
        for body in self._bodies:
            des = body["des"]
            gap = G.d_pt_rect(x, y, body["rect"]) - half
            kind = "body" if self.board.hard_body(des) else "body-soft"
            out.append(conflict(gap, kind, des=des))
        for obj in self.extra:
            if net is not None and obj.get("net") == net:
                continue
            if obj.get("kind") == "pad":
                rect = G.rect_of(obj["x"], obj["y"], obj["w"], obj["h"])
                out.append(conflict(G.d_pt_rect(x, y, rect) - half, "extra-pad",
                                    net=obj.get("net"), des=obj.get("des")))
            elif obj.get("kind") == "line":
                gap = G.d_pt_seg(x, y, obj["x1"], obj["y1"], obj["x2"], obj["y2"]) \
                    - half - float(obj.get("w", 10)) / 2.0
                out.append(conflict(gap, "extra-line", net=obj.get("net"), id=obj.get("id")))
            elif obj.get("kind") == "via":
                gap = ((x - obj["x"]) ** 2 + (y - obj["y"]) ** 2) ** 0.5 \
                    - half - float(obj.get("d", self.via_d)) / 2.0
                out.append(conflict(gap, "extra-via", net=obj.get("net"), id=obj.get("id")))
        self._environment(out, net, G.LAYER_THROUGH, segment=(x,y,x,y), radius=half)
        return self._verdict(out, self.clr)

    # ------------------------------------------------------------------- pads
    def check_pad(self, net, layer, cx, cy, w, h, required=None):
        """Query one planned footprint pad rectangle."""
        required = self.clr if required is None else float(required)
        out = []
        rect = G.rect_of(cx, cy, w, h)
        for line in self._lines:
            if (net is not None and line["net"] == net) or not layers_overlap(line["layer"], layer):
                continue
            gap = G.d_seg_rect(line["x1"], line["y1"], line["x2"], line["y2"], rect) \
                - line["w"] / 2.0
            out.append(conflict(gap, "line", net=line["net"], id=line["id"],
                                layer=line["layer"], width=line["w"]))
        for via in self._vias:
            if (net is not None and via["net"] == net):
                continue
            out.append(conflict(G.d_pt_rect(via["x"], via["y"], rect) - via["d"] / 2.0,
                                "via", net=via["net"], id=via["id"]))
        for pad in self._pads:
            if (net is not None and pad["net"] == net):
                continue
            if not layers_overlap(pad["layer"], layer):
                continue
            other = G.rect_of(pad["x"], pad["y"], pad["w"], pad["h"])
            out.append(conflict(G.d_rect_rect(rect, other), "pad", net=pad["net"],
                                des=pad["des"]))
        for body in self._bodies:
            des = body["des"]
            kind = "body" if self.board.hard_body(des) else "body-soft"
            out.append(conflict(G.d_rect_rect(rect, body["rect"]), kind, des=des))
        for obj in self.extra:
            if net is not None and obj.get("net") == net:
                continue
            if obj.get("kind") == "line" and layers_overlap(obj.get("layer"), layer):
                gap = G.d_seg_rect(obj["x1"], obj["y1"], obj["x2"], obj["y2"], rect) \
                    - float(obj.get("w", 10)) / 2.0
                out.append(conflict(gap, "extra-line", net=obj.get("net"), id=obj.get("id")))
            elif obj.get("kind") in ("pad", "via"):
                size = obj.get("w", obj.get("d", self.via_d))
                height = obj.get("h", obj.get("d", self.via_d))
                if obj.get("kind") == "via" or layers_overlap(obj.get("layer"), layer):
                    other = G.rect_of(obj["x"], obj["y"], size, height)
                    out.append(conflict(G.d_rect_rect(rect, other),
                                        "extra-" + obj["kind"], net=obj.get("net"),
                                        des=obj.get("des"), id=obj.get("id")))
        self._environment(out, net, layer, rect=rect, required=required)
        return self._verdict(out, required)

    def _environment(self, out, net, layer, segment=None, radius=0, rect=None, required=None):
        for fill in self.board.fills:
            if (net is not None and fill["net"] == net) or not layers_overlap(fill["layer"], layer):
                continue
            gap = (G.d_rect_rect(rect, fill["rect"]) if rect is not None else
                   G.d_seg_rect(*segment, fill["rect"]) - radius)
            out.append(conflict(gap, "fill", id=fill["id"], approx=True))
        outline = self.board.outline
        if outline:
            points = G.rect_pts(rect) if rect is not None else [(segment[0],segment[1]),(segment[2],segment[3])]
            edges = G.poly_edges(points) if rect is not None else [(points[0],points[1])]
            distance = min(G.d_seg_poly(*a,*b,outline) for a,b in edges) - radius
            if not all(point_inside(p, outline) for p in points):
                distance = -1.0
            # Convert the edge rule into the same clearance threshold used by callers.
            out.append(conflict(distance - self.rules["copper_to_edge"] + (self.clr if required is None else required),
                                "edge", physical_gap=distance))

    # --------------------------------------------------------------- verdicts
    @staticmethod
    def _verdict(conflicts, required):
        hard = [c for c in conflicts if c["kind"] != "body-soft"]
        if not hard:
            return float("inf"), None, conflicts
        worst = min(hard, key=lambda c: c["gap"])
        return worst["gap"], worst, conflicts


def layers_overlap(a, b):
    return a in (None, G.LAYER_THROUGH) or b in (None, G.LAYER_THROUGH) or a == b


def point_inside(point, polygon):
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in G.poly_edges(polygon):
        if (ay > y) != (by > y) and x < ax + (y-ay)*(bx-ax)/(by-ay):
            inside = not inside
    return inside
