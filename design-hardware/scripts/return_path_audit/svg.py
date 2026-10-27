"""Local SVG risk overlay for locating findings.

This is an *analysis overlay*, not an official EDA export and not a rendering of
the real board by the host EDA.  The watermark states that explicitly.
"""
from __future__ import annotations

import math

WATERMARK = "synthetic_analysis / not_official_export"
WIDTH = 1000.0
MARGIN = 40.0


def _collect_points(model):
    points = list(model.board["outline"])
    for signal in model.signals:
        for segment in signal["segments"]:
            if segment.get("start"):
                points.append(segment["start"])
            if segment.get("end"):
                points.append(segment["end"])
    for copper in model.copper:
        for polygon in copper["polygons"]:
            points.extend(polygon["outer"])
    for via in model.vias:
        if via.get("center"):
            points.append(via["center"])
    return points


class Projector:
    def __init__(self, points, width=WIDTH, margin=MARGIN):
        xs = [item[0] for item in points] or [0.0, 1.0]
        ys = [item[1] for item in points] or [0.0, 1.0]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)
        span_x = max(self.max_x - self.min_x, 1e-9)
        span_y = max(self.max_y - self.min_y, 1e-9)
        self.scale = (width - 2 * margin) / max(span_x, span_y)
        self.width = width
        self.height = span_y * self.scale + 2 * margin
        self.margin = margin

    def project(self, point):
        x = self.margin + (point[0] - self.min_x) * self.scale
        # Flip Y so the overlay is not mirrored relative to a normal board view.
        y = self.margin + (self.max_y - point[1]) * self.scale
        return (x, y)


def _ring_path(projector, ring):
    points = [projector.project(item) for item in ring]
    if not points:
        return ""
    parts = ["M %.3f %.3f" % points[0]]
    for point in points[1:]:
        parts.append("L %.3f %.3f" % point)
    parts.append("Z")
    return " ".join(parts)


def _hex_ok(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_overlay(model, result, title_extra=""):
    projector = Projector(_collect_points(model))
    width = projector.width
    height = max(projector.height, 240.0)
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<svg xmlns="http://www.w3.org/2000/svg" width="%.0f" height="%.0f" '
                 'viewBox="0 0 %.0f %.0f">' % (width, height, width, height))
    lines.append('<rect width="100%%" height="100%%" fill="#0f1419"/>')
    lines.append('<defs><pattern id="hatch" width="6" height="6" '
                 'patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
                 '<line x1="0" y1="0" x2="0" y2="6" stroke="#e5484d" stroke-width="2"/>'
                 '</pattern></defs>')
    lines.append('<g font-family="Consolas, monospace">')
    # board
    lines.append('<path d="%s" fill="#1b2430" stroke="#5c7a9c" stroke-width="2"/>'
                 % _ring_path(projector, model.board["outline"]))
    for hole in model.board["holes"]:
        lines.append('<path d="%s" fill="#0f1419" stroke="#5c7a9c" stroke-width="1.5"/>'
                     % _ring_path(projector, hole))
    # reference copper (per referenced layer/net only, to keep the overlay readable)
    referenced = set()
    for signal in model.signals:
        for segment in signal["segments"]:
            for assignment in model.assignment_for(signal["id"], segment["id"],
                                                   segment["layer"]):
                referenced.add((assignment["reference_layer"], assignment["reference_net"]))
    for copper in model.copper:
        if (copper["layer"], copper["net"]) not in referenced:
            continue
        actual = copper["is_actual_fill"]
        fill = "#1f4d33" if actual else "#3a2f18"
        dash = "" if actual else ' stroke-dasharray="6 3"'
        for polygon in copper["polygons"]:
            lines.append('<path d="%s" fill="%s" fill-opacity="0.85" stroke="#3ddc84" '
                         'stroke-width="1.2" stroke-opacity="0.7"%s/>'
                         % (_ring_path(projector, polygon["outer"]), fill, dash))
            for hole in polygon["holes"]:
                lines.append('<path d="%s" fill="#0f1419" stroke="#e5484d" '
                             'stroke-width="1"/>' % _ring_path(projector, hole))
    # risk intervals
    risk_segments = {}
    for coverage in result["coverages"].values():
        if not coverage.get("runs"):
            continue
        for run in coverage["runs"]:
            start, end = _run_endpoints(model, coverage, run)
            if start is None:
                continue
            a = projector.project(start)
            b = projector.project(end)
            width_px = 10 if run["void_length"] > 0 else 6
            risk_segments.setdefault(coverage["segment_id"], []).append(
                (a, b, run["void_length"] > 0, width_px))
    # signals
    for signal in model.signals:
        for segment in signal["segments"]:
            if not segment.get("start") or not segment.get("end"):
                continue
            a = projector.project(segment["start"])
            b = projector.project(segment["end"])
            lines.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#4cc2ff" '
                         'stroke-width="2.4" stroke-linecap="round"/>' % (a[0], a[1], b[0], b[1]))
            label = projector.project(((segment["start"][0] + segment["end"][0]) / 2.0,
                                       (segment["start"][1] + segment["end"][1]) / 2.0))
            lines.append('<text x="%.1f" y="%.1f" font-size="11" fill="#9fd4ff">%s</text>'
                         % (label[0] + 3, label[1] - 3, _hex_ok(segment["id"])))
    for a, b, is_void, width_px in [item for items in risk_segments.values()
                                    for item in items]:
        lines.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#e5484d" '
                     'stroke-width="%d" stroke-linecap="round" stroke-opacity="0.95"/>'
                     % (a[0], a[1], b[0], b[1], width_px))
    # vias
    for via in model.vias:
        if not via.get("center"):
            continue
        point = projector.project(via["center"])
        radius = max(2.5, (via["diameter"] or 1.0) * projector.scale / 2.0)
        lines.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="#f5c451" '
                     'fill-opacity="0.9" stroke="#0f1419" stroke-width="0.8"/>'
                     % (point[0], point[1], radius))
        lines.append('<text x="%.1f" y="%.1f" font-size="9" fill="#f5c451">%s</text>'
                     % (point[0] + radius + 2, point[1] + 3, _hex_ok(via["id"])))
    # legend and watermark
    lines.append('<rect x="12" y="12" width="360" height="86" fill="#0b1016" '
                 'fill-opacity="0.85" stroke="#33465c"/>')
    lines.append('<text x="20" y="30" font-size="12" fill="#e6edf3">ANALYSIS OVERLAY - %s</text>'
                 % _hex_ok(WATERMARK))
    lines.append('<text x="20" y="48" font-size="11" fill="#9fb3c8">status: %s</text>'
                 % _hex_ok(result.get("status", "unknown")))
    lines.append('<text x="20" y="64" font-size="11" fill="#9fb3c8">'
                 'red = uncovered/corridor risk, green = declared reference copper, '
                 'yellow = vias</text>')
    lines.append('<text x="20" y="80" font-size="11" fill="#9fb3c8">%s</text>'
                 % _hex_ok(title_extra[:70]))
    lines.append('<text x="12" y="%.1f" font-size="24" fill="#e5484d" fill-opacity="0.14" '
                 'transform="rotate(-18 12 %.1f)">%s</text>'
                 % (height - 16, height - 16, _hex_ok(WATERMARK.upper())))
    lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _run_endpoints(model, coverage, run):
    segment = model.segments.get(coverage["segment_id"])
    if not segment or not segment.get("start") or not segment.get("end"):
        return None, None
    start, end = segment["start"], segment["end"]
    t0, t1 = run["t0"], run["t1"]

    def at(t):
        return (start[0] + t * (end[0] - start[0]),
                start[1] + t * (end[1] - start[1]))
    return at(t0), at(t1)
