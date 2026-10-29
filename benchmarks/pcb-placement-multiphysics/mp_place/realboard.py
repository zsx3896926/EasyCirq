"""P4.5/P4.6: real EasyCirq PCB dumps -> placement Scenario + optimisation comparison.

The EasyCirq case repository contains *real* PCB read-back dumps produced by the
EasyCirq EDA bridge.  This module turns such a dump into the stable
:class:`mp_place.model.Scenario` the rest of the framework understands, then
compares three placements on it:

1. ``original``  -- the real board layout as captured by the dump;
2. ``optimized`` -- ``solver_v2.solve`` with the adaptive route-aware objective
   (``route_cost.tuned_objective``, proxy + tuned routability penalty);
3. ``repair``    -- ``route_opt.repair_routes`` (solver + routability-gated
   local repair) on the same objective.

Metrics are ``physics_v2`` truth, offline grid-router completion / failed nets /
vias / wirelength and hard feasibility.

v2 (P4.6)
---------
* **Polygon board outline**: the real outline is an arc-polyline polygon
  (``outline.points``).  The placement model still uses the axis-aligned
  bounding rectangle (solver/features unchanged), but every converted board now
  carries a :class:`BoardPolygon` and reports ray-casting point-in-polygon
  validation: polygon point count/area/area-vs-bbox ratio and components whose
  bbox corners fall outside the real outline (with distance and an
  edge-overhang allowance).
* **Auto-discovery**: :func:`discover_cases` scans the EasyCirq ``cases`` tree
  for dump-like JSON (``components`` list + ``outline`` object) and picks one
  preferred dump per case (``pcb-dump-final`` > ``pcb-board-final`` >
  ``board-baseline`` > other dumps); cases without a dump (e.g.
  ``feedback-r12``) are reported as skipped with a reason.
* **Edge-overhang components** (e.g. a connector whose captured body sticks a
  fraction of a millimetre past the outline) are kept when the overhang is
  ``<= EDGE_OVERHANG_MM``; the board rectangle is expanded just enough to keep
  them hard-feasible and the expansion is reported.
* **Keepouts**: when a sibling ``placement-plan-final.json`` / 
  ``placement-plan.json`` carries ``keepouts`` (mounting-hole washer circles),
  they are converted (mil -> mm, circle -> axis-aligned square approximation)
  and wired into ``Scenario.keepouts``; otherwise the board reports
  ``keepouts: NOT RUN`` with the reason.
* Reports: ``report_realboard_v2.md/json`` (schema ``mp_place.realboard/v2``).

Conversion contract
-------------------
* **Units**: dump coordinates are in **mil** (1 mil = 0.0254 mm).  This is
  verified before conversion: 0402-class passive bboxes come out ~74.8 mil
  (= 1.90 mm) which is physically plausible, while interpreting the same
  numbers as millimetres would give 1.9 m boards.  :func:`verify_units` records
  the evidence; :func:`convert_dump` refuses a dump that is not plausible.
* **Body size**: component ``w``/``h`` are reverse-engineered from the capture
  bbox (for 90/270 degree rotation the axis-aligned bbox dims are swapped so the
  unrotated body frame is recovered).  The capture bbox includes silk/courtyard,
  so it is a slightly conservative blocker.
* **Pads**: absolute pad positions become local offsets
  ``local = R(-rotation) * (pad_center - component_center)`` (rotation in
  degrees CCW, matching :func:`mp_place.model.pad_position`).  Pads sharing a
  pad number (e.g. thermal pads) are merged into one pin at their mean offset.
* **Nets**: grouped by the pad ``net`` name; empty net names (unconnected copper)
  are ignored and nets with fewer than two pins are dropped (a single-pin net is
  not routable).  Net classes use a small name heuristic (GND -> ground,
  ``+3V3``/``VIN``/``VBUS`` -> power, USB/I2C -> digital, else generic).
* **Filtering**: a component is kept only when it has a designator, a finite
  non-degenerate bbox of plausible size, at least one usable pad and its bbox
  does not overhang the outline bbox by more than ``EDGE_OVERHANG_MM``.  Every
  dropped object is reported with a reason.
* **Board**: the outline polygon is validated with ray casting; the placement
  model uses its axis-aligned bounding rectangle (expanded for edge overhangs),
  recorded in the report.  Keepouts are applied only when parseable.
* **Fixed parts**: reference prefixes ``J`` (connectors) and ``SW`` (buttons) are
  pinned to their captured position; everything else is movable.  If a dump has
  no such prefix the conversion records ``all_movable`` and finishes without
  fixed parts.

Limits: the router is the offline 1 mm / 2-layer grid oracle (not DRC, not a
routability proof); ``physics_v2`` is a pseudo-physics truth model.  The capture
bbox is a conservative body approximation of a real footprint; the polygon is
used for validation, not for collision in the solver.  Nothing here applies a
placement, runs DRC, calls EDA or touches the network.

CLI
---
``python -m mp_place.realboard`` (v2, default) auto-discovers every dump under
the EasyCirq cases tree, runs the comparison and writes
``report_realboard_v2.md`` / ``report_realboard_v2.json`` at the project root.
``--v1`` keeps the original three-case report.  Useful flags: ``--steps``,
``--seed``, ``--max-routes``, ``--cases-root DIR``, ``--source NAME=PATH``
(repeatable), ``--out DIR`` and ``--json``.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import pathlib
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .model import (
    Component,
    Net,
    Placement,
    Scenario,
    bbox,
    hard_violations,
    rect_overlap_area,
)
from .objective import PhysicsSimulator
from .physics_v2 import PhysicsSimulatorV2
from .route_cost import select_config, tuned_objective
from .route_opt import repair_routes
from .router import GridRouter
from .solver_v2 import solve

MIL_TO_MM = 0.0254
REALBOARD_SCHEMA = "mp_place.realboard/v1"
REALBOARD_SCHEMA_V2 = "mp_place.realboard/v2"
REALBOARD_SCHEMA_V3 = "mp_place.realboard/v3"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT_MD = "report_realboard.md"
REPORT_JSON = "report_realboard.json"
REPORT_MD_V2 = "report_realboard_v2.md"
REPORT_JSON_V2 = "report_realboard_v2.json"
REPORT_MD_V3 = "report_realboard_v3.md"
REPORT_JSON_V3 = "report_realboard_v3.json"

def _resolve_cases_root() -> pathlib.Path:
    """Locate the EasyCirq ``easycirq/cases`` tree without hard-coding a machine path.

    Resolution order: ``MPLACE_CASES_ROOT`` env var, then walking up from this
    file (works for both the dev workspace layout and the in-repo benchmark
    layout), then a repo-relative fallback.
    """
    import os

    env = os.environ.get("MPLACE_CASES_ROOT")
    if env:
        return pathlib.Path(env)
    here = pathlib.Path(__file__).resolve()
    for base in here.parents:
        for parts in (("hardware-design-skill", "easycirq", "cases"), ("easycirq", "cases")):
            candidate = base.joinpath(*parts)
            if candidate.is_dir():
                return candidate
    return pathlib.Path("easycirq/cases")


#: Default read-only source root (EasyCirq case repository on this machine/repo).
DEFAULT_CASES_ROOT = _resolve_cases_root()
DEFAULT_SOURCES: Tuple[Tuple[str, pathlib.Path], ...] = (
    (
        "mcu-i2c",
        DEFAULT_CASES_ROOT / "mcu-i2c-s3-2026-10-26" / "evidence" / "pcb-dump-final.json",
    ),
    (
        "photo-led",
        DEFAULT_CASES_ROOT / "photo-led-pcb-2026-10-26" / "evidence" / "pcb-dump-final.json",
    ),
    (
        "dual-button",
        DEFAULT_CASES_ROOT
        / "dual-button-led-night-20261027"
        / "negative-direct-move"
        / "board-baseline.json",
    ),
)

DEFAULT_STEPS = 400
DEFAULT_SEED = 0
DEFAULT_MAX_ROUTES = 30
ROUTER_GRID_MM = 1.0
ROUTER_LAYERS = 2

EXAMPLE_0402_MIL = 74.8  # documented 0402-class capture bbox long side

#: A captured component body may overhang the outline rectangle by this much
#: (e.g. an edge connector) and still be kept; the board rect is expanded to fit.
EDGE_OVERHANG_MM = 2.0
#: Geometric tolerance for the ray-casting boundary test (mm).
POLYGON_EPS_MM = 1e-6
#: Body-overlap area below which a *captured* pair is reported as a courtyard
#: approximation artifact (real boards are legal; capture bboxes include silk).
CAPTURE_OVERLAP_TOL_MM2 = 1.0
#: v2/v3 default solver budget (larger real boards need more moves than the templates).
DEFAULT_STEPS_V2 = 800
DEFAULT_STEPS_V3 = 800
#: Sibling evidence files that may carry placement keepouts (mil, circle/rect).
KEEPOUT_PLAN_CANDIDATES: Tuple[str, ...] = (
    "placement-plan-final.json",
    "placement-plan.json",
)

#: Readable aliases for the known EasyCirq cases (fallback strips the date).
_CASE_ALIASES: Dict[str, str] = {
    "mcu-i2c-s3-2026-10-26": "mcu-i2c",
    "photo-led-pcb-2026-10-26": "photo-led",
    "dual-button-led-night-20261027": "dual-button",
    "temp-alarm-2026-10-24": "temp-alarm",
}

LIMITS: Tuple[str, ...] = (
    "placement solver uses the axis-aligned outline bbox; polygon is validation/report only",
    "polygon outline approximated from arc-polyline points; edge-overhang components are allowed up to 2.0 mm",
    "circular washer keepouts are approximated by axis-aligned squares",
    "capture bbox includes silkscreen/courtyard, so component bodies are conservative blockers",
    "mechanical parts (J/SW/ANT prefixes) are pinned to their captured position; original-layout conflicts are reported, not fatal",
    "router completion is the offline 1mm/2-layer grid-maze oracle, not DRC and not a routability proof",
    "physics_v2 truth is an offline pseudo-physics model, not a measurement",
    "dual-button dump is a trimmed regression fixture (copper/silk requests trimmed; routedLines empty)",
    "nothing is applied to a board; eda_calls=0, drc='NOT RUN', routing_verified=false",
)

#: Reference-designator prefixes that stay fixed at the captured position.
#: Connectors (J), buttons/switches (SW) and antennas (ANT) are mechanical parts.
MECHANICAL_PREFIXES: Tuple[str, ...] = ("ANT", "SW", "J")
#: Role label per mechanical reference prefix (longest prefix first).
MECHANICAL_ROLES: Tuple[Tuple[str, str], ...] = (
    ("ANT", "antenna"),
    ("SW", "switch"),
    ("J", "connector"),
)
#: Backwards-compatible alias (v1/v2 reports used ``FIXED_PREFIXES``).
FIXED_PREFIXES: Tuple[str, ...] = MECHANICAL_PREFIXES

#: Reference prefixes treated as "passive/mechanical small parts" by the unit check.
_PASSIVE_PREFIXES: Tuple[str, ...] = ("C", "R", "L", "D", "Q", "LED", "LDR", "RV")

_PREFIX_KINDS: Tuple[Tuple[str, str], ...] = (
    ("ANT", "antenna"),
    ("LED", "diode"),
    ("LDR", "sensor"),
    ("RV", "analog"),
    ("SW", "switch"),
    ("J", "connector"),
    ("C", "decap"),
    ("L", "inductor"),
    ("D", "diode"),
    ("Q", "analog"),
    ("R", "analog"),
    ("U", "ic"),
    ("Y", "crystal"),
)

_POWER_TOKENS: Tuple[str, ...] = ("+3V3", "+5V", "VBUS", "VIN", "VDD", "VCC", "3V3", "VREF")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _round(value: Optional[float], digits: int = 6) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rot_local(dx: float, dy: float, rotation: int) -> Tuple[float, float]:
    """``R(-rotation) * (dx, dy)`` -- absolute pad offset -> local body offset."""
    theta = math.radians(int(rotation) % 360)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (dx * cos_t + dy * sin_t, -dx * sin_t + dy * cos_t)


def _component_kind(ref: str) -> str:
    upper = ref.upper()
    for prefix, kind in _PREFIX_KINDS:
        if upper.startswith(prefix):
            return kind
    return "generic"


def _net_class(name: str) -> str:
    upper = name.upper().strip()
    if upper in {"GND", "AGND", "DGND", "PGND"} or upper.startswith("GND"):
        return "ground"
    if upper.startswith("+") or any(token in upper for token in _POWER_TOKENS):
        return "power"
    if "USB" in upper or "I2C" in upper or upper in {"RXD", "TXD", "UART", "EN", "BOOT"}:
        return "digital"
    return "generic"


def _outline_bbox(payload: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """Return the outline bbox in dump units (mil), falling back to its points."""
    outline = payload.get("outline")
    if not isinstance(outline, dict):
        return None
    raw = outline.get("bbox")
    if isinstance(raw, dict):
        coords = []
        for key in ("minX", "minY", "maxX", "maxY"):
            number = _finite(raw.get(key))
            if number is None:
                coords = []
                break
            coords.append(number)
        if len(coords) == 4 and coords[2] > coords[0] and coords[3] > coords[1]:
            return (coords[0], coords[1], coords[2], coords[3])
    points = outline.get("points") or []
    xs: List[float] = []
    ys: List[float] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        x, y = _finite(point[0]), _finite(point[1])
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)
    if not xs or not ys:
        return None
    bbox = (min(xs), min(ys), max(xs), max(ys))
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


# --------------------------------------------------------------------------- #
# polygon board outline (ray casting)
# --------------------------------------------------------------------------- #
def _outline_points_mil(payload: Dict[str, Any]) -> Tuple[List[Tuple[float, float]], bool]:
    """Return the outline polygon points (mil) and whether the dump closes it."""
    outline = payload.get("outline") if isinstance(payload, dict) else None
    points: List[Tuple[float, float]] = []
    for point in (outline or {}).get("points") or []:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            x, y = _finite(point[0]), _finite(point[1])
            if x is not None and y is not None:
                points.append((x, y))
    closed = len(points) >= 2 and points[0] == points[-1]
    if closed:
        points = points[:-1]
    return points, closed


def _point_segment_distance(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_in_polygon(
    px: float,
    py: float,
    polygon: Sequence[Tuple[float, float]],
    eps: float = POLYGON_EPS_MM,
) -> bool:
    """Ray-casting point-in-polygon test; boundary points count as inside."""
    n = len(polygon)
    if n < 3:
        return False
    for index in range(n):
        ax, ay = polygon[index]
        bx, by = polygon[(index + 1) % n]
        if _point_segment_distance(px, py, ax, ay, bx, by) <= eps:
            return True
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > py) != (yj > py):
            cross_x = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < cross_x:
                inside = not inside
        j = i
    return inside


def polygon_boundary_distance(
    px: float,
    py: float,
    polygon: Sequence[Tuple[float, float]],
) -> float:
    """Shortest distance from a point to the polygon boundary (mm)."""
    n = len(polygon)
    if n < 3:
        return float("inf")
    return min(
        _point_segment_distance(px, py, polygon[i][0], polygon[i][1],
                                polygon[(i + 1) % n][0], polygon[(i + 1) % n][1])
        for i in range(n)
    )


def polygon_area(points: Sequence[Tuple[float, float]]) -> float:
    """Shoelace polygon area (absolute, square millimetres)."""
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for index in range(n):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % n]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


@dataclass
class BoardPolygon:
    """A closed board-outline polygon in millimetres with ray-casting helpers."""

    points: List[Tuple[float, float]]
    closed: bool = True

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise ValueError("board polygon needs at least 3 points")

    @property
    def area_mm2(self) -> float:
        return polygon_area(self.points)

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        xs = [point[0] for point in self.points]
        ys = [point[1] for point in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def contains(self, px: float, py: float, eps: float = POLYGON_EPS_MM) -> bool:
        return point_in_polygon(px, py, self.points, eps=eps)

    def boundary_distance(self, px: float, py: float) -> float:
        return polygon_boundary_distance(px, py, self.points)

    def rect_outside(self, rect: Tuple[float, float, float, float]) -> Tuple[int, float]:
        """Count rect corners outside the polygon and the worst overhang (mm)."""
        x0, y0, x1, y1 = rect
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        outside = 0
        worst = 0.0
        for px, py in corners:
            if not self.contains(px, py):
                outside += 1
                worst = max(worst, self.boundary_distance(px, py))
        return outside, worst



# --------------------------------------------------------------------------- #
# unit verification
# --------------------------------------------------------------------------- #
def verify_units(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Verify the dump's mil interpretation against 0402-class passives.

    Returns a JSON-safe evidence dict with ``mil_interpretation_plausible``.
    """
    components = payload.get("components") or []
    bbox = _outline_bbox(payload) or (0.0, 0.0, 1.0, 1.0)
    board_w_mil = bbox[2] - bbox[0]
    board_h_mil = bbox[3] - bbox[1]
    longs: List[float] = []
    entries: List[Tuple[float, Dict[str, Any]]] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ref = str(comp.get("designator") or "")
        raw = comp.get("bbox") or {}
        if not isinstance(raw, dict):
            continue
        w = _finite(raw.get("maxX"))
        h = _finite(raw.get("maxY"))
        min_x = _finite(raw.get("minX"))
        min_y = _finite(raw.get("minY"))
        if w is None or h is None or min_x is None or min_y is None:
            continue
        width, height = w - min_x, h - min_y
        if width <= 0.0 or height <= 0.0:
            continue
        if not ref.upper().startswith(_PASSIVE_PREFIXES):
            continue
        long_side = max(width, height)
        if not (5.0 <= long_side <= 800.0):
            continue
        longs.append(long_side)
        entries.append(
            (
                long_side,
                {
                    "ref": ref,
                    "device": comp.get("device"),
                    "bbox_mil": [round(width, 3), round(height, 3)],
                    "bbox_mm": [round(width * MIL_TO_MM, 3), round(height * MIL_TO_MM, 3)],
                },
            )
        )
    examples = [
        item for _long, item in sorted(entries, key=lambda pair: abs(pair[0] - EXAMPLE_0402_MIL))[:5]
    ]
    evidence: Dict[str, Any] = {
        "declared_unit": "mil",
        "scale_to_mm": MIL_TO_MM,
        "board_mil": [round(board_w_mil, 3), round(board_h_mil, 3)],
        "board_mm": [round(board_w_mil * MIL_TO_MM, 3), round(board_h_mil * MIL_TO_MM, 3)],
        "passive_count": len(longs),
        "passive_bbox_long_side_mm": {
            "min": _round(min(longs) * MIL_TO_MM, 4) if longs else None,
            "median": _round(statistics.median(longs) * MIL_TO_MM, 4) if longs else None,
            "max": _round(max(longs) * MIL_TO_MM, 4) if longs else None,
        },
        "examples": examples,
        "note": (
            "0402-class capture bbox is ~74.8 mil = 1.90 mm; treating the same "
            "numbers as millimetres would mean metres-sized parts/boards."
        ),
    }
    median_mil = statistics.median(longs) if longs else None
    board_ok = (
        10.0 <= board_w_mil * MIL_TO_MM <= 250.0
        and 5.0 <= board_h_mil * MIL_TO_MM <= 250.0
    )
    passive_ok = median_mil is not None and 0.5 <= median_mil * MIL_TO_MM <= 15.0
    evidence["mil_interpretation_plausible"] = bool(board_ok and passive_ok)
    evidence["mm_interpretation_rejected"] = bool(
        board_w_mil > 250.0
        or board_h_mil > 250.0
        or (median_mil is not None and median_mil > 5.0)
    )
    evidence["closest_to_0402_mil"] = (
        _round(min(longs, key=lambda value: abs(value - EXAMPLE_0402_MIL)), 2) if longs else None
    )
    return evidence


# --------------------------------------------------------------------------- #
# conversion
# --------------------------------------------------------------------------- #
@dataclass
class ConvertedBoard:
    """One converted real board plus everything needed for the report."""

    name: str
    source: str
    source_sha256: str
    source_bytes: int
    scenario: Scenario
    original_placement: Placement
    report: Dict[str, Any]


def _drop(report: Dict[str, Any], ref: str, reason: str) -> None:
    report["dropped_components"].append({"ref": ref, "reason": reason})


def _keepout_rect_mil(entry: Any) -> Optional[Tuple[float, float, float, float]]:
    """Parse one placement-plan keepout entry into a mil rectangle, if possible."""
    if not isinstance(entry, dict):
        return None
    center = entry.get("center")
    radius = _finite(entry.get("radius"))
    if isinstance(center, (list, tuple)) and len(center) >= 2 and radius is not None and radius > 0:
        cx, cy = _finite(center[0]), _finite(center[1])
        if cx is not None and cy is not None:
            return (cx - radius, cy - radius, cx + radius, cy + radius)
    raw_rect = entry.get("rect")
    if isinstance(raw_rect, (list, tuple)) and len(raw_rect) >= 4:
        values = [_finite(item) for item in raw_rect[:4]]
        if all(value is not None for value in values):
            return (values[0], values[1], values[2], values[3])  # type: ignore[return-value]
    raw_bbox = entry.get("bbox")
    if isinstance(raw_bbox, dict):
        values = [_finite(raw_bbox.get(key)) for key in ("minX", "minY", "maxX", "maxY")]
        if all(value is not None for value in values):
            return (values[0], values[1], values[2], values[3])  # type: ignore[return-value]
    return None


def _convert_keepouts(
    plan: Optional[Dict[str, Any]],
    plan_source: Optional[object],
    scene_x0_mm: float,
    scene_y0_mm: float,
    board_w: float,
    board_h: float,
) -> Tuple[List[Tuple[float, float, float, float]], Dict[str, Any]]:
    """Convert placement-plan keepouts (mil) into Scenario rects (mm)."""
    report: Dict[str, Any] = {
        "status": "NOT RUN",
        "source": str(plan_source) if plan_source is not None else None,
        "count": 0,
        "geometry": [],
        "reason": None,
        "approximation": "circular washer keepout -> axis-aligned square",
    }
    if not isinstance(plan, dict):
        report["reason"] = "no parseable placement-plan keepouts next to the dump"
        return [], report
    raw = plan.get("keepouts")
    if raw is None:
        report["reason"] = "placement plan found but has no 'keepouts' field"
        return [], report
    if not isinstance(raw, list):
        report["reason"] = "placement plan 'keepouts' is not a list"
        return [], report
    rects: List[Tuple[float, float, float, float]] = []
    unparsed: List[Dict[str, Any]] = []
    for index, entry in enumerate(raw):
        rect_mil = _keepout_rect_mil(entry)
        if rect_mil is None:
            unparsed.append({"index": index, "entry": _json_safe(entry)})
            continue
        x0 = rect_mil[0] * MIL_TO_MM - scene_x0_mm
        y0 = rect_mil[1] * MIL_TO_MM - scene_y0_mm
        x1 = rect_mil[2] * MIL_TO_MM - scene_x0_mm
        y1 = rect_mil[3] * MIL_TO_MM - scene_y0_mm
        x0, x1 = max(0.0, x0), min(board_w, x1)
        y0, y1 = max(0.0, y0), min(board_h, y1)
        if x1 - x0 <= 1e-9 or y1 - y0 <= 1e-9:
            unparsed.append({"index": index, "entry": _json_safe(entry), "reason": "outside board"})
            continue
        rect = (round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6))
        rects.append(rect)
        item: Dict[str, Any] = {
            "index": index,
            "id": entry.get("id"),
            "source": entry.get("source"),
            "rect_mm": list(rect),
            "shape": "circle" if entry.get("center") is not None else "rect",
        }
        radius = _finite(entry.get("radius"))
        if radius is not None:
            item["radius_mm"] = round(radius * MIL_TO_MM, 6)
        report["geometry"].append(item)
    report["count"] = len(rects)
    if unparsed:
        report["unparsed"] = unparsed
    if rects:
        report["status"] = "APPLIED"
    else:
        report["reason"] = "placement plan keepouts present but none parseable inside the board"
    return rects, report


def _capture_body_overlaps(
    scenario: Scenario,
    placement: Placement,
) -> List[Dict[str, Any]]:
    """Report small body overlaps of the captured placement (courtyard artifacts).

    Real boards are legal, but the capture bbox includes silk/courtyard, so two
    neighbouring parts can overlap by a fraction of a mm in this model.  Only
    overlaps ``<= CAPTURE_OVERLAP_TOL_MM2`` are classified as artifacts.
    """
    overlaps: List[Dict[str, Any]] = []
    refs = sorted(scenario.components)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            ref_a, ref_b = refs[i], refs[j]
            box_a = bbox(scenario.components[ref_a], *placement[ref_a])
            box_b = bbox(scenario.components[ref_b], *placement[ref_b])
            area = rect_overlap_area(box_a, box_b)
            if area > 1e-9 and area <= CAPTURE_OVERLAP_TOL_MM2 + 1e-9:
                overlaps.append(
                    {
                        "pair": [ref_a, ref_b],
                        "area_mm2": round(area, 6),
                        "reason": "capture bbox includes silk/courtyard; small approximation overlap",
                    }
                )
    return overlaps


def _mechanical_role(ref: str) -> Optional[str]:
    """Role of a mechanical reference (connector/switch/antenna) or ``None``."""
    upper = ref.upper()
    for prefix, role in MECHANICAL_ROLES:
        if upper.startswith(prefix):
            return role
    return None


def _mechanical_fixed_entries(
    components: Dict[str, Component],
    placements: Placement,
) -> List[Dict[str, Any]]:
    """List the mechanically pinned parts (J/SW/ANT) of the captured layout."""
    entries: List[Dict[str, Any]] = []
    for ref in sorted(components):
        if not components[ref].fixed:
            continue
        role = _mechanical_role(ref) or "mechanical"
        prefix = next(
            (item_prefix for item_prefix, _role in MECHANICAL_ROLES if ref.upper().startswith(item_prefix)),
            None,
        )
        x, y, rot = placements[ref]
        entries.append(
            {
                "ref": ref,
                "role": role,
                "prefix": prefix,
                "x_mm": round(x, 6),
                "y_mm": round(y, 6),
                "rotation": int(rot),
                "source": "captured_layout",
            }
        )
    return entries


def _original_conflict_entries(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect every captured-layout conflict (reported, never fatal)."""
    conflicts: List[Dict[str, Any]] = []
    tolerated_pairs = {
        tuple(item.get("pair") or ())
        for item in (report.get("original_capture_overlaps") or [])
    }
    for violation in report.get("original_violations") or []:
        tolerated = False
        if violation.startswith("body_overlap:"):
            parts = violation[len("body_overlap:"):].split(":")
            tolerated = tuple(sorted(parts)) in tolerated_pairs
        conflicts.append(
            {
                "kind": "hard_violation",
                "detail": violation,
                "tolerated": bool(tolerated),
                "note": "capture-bbox courtyard artifact"
                if tolerated
                else "captured layout does not satisfy the bbox model",
            }
        )
    for item in report.get("edge_overhang_components") or []:
        conflicts.append(
            {
                "kind": "edge_overhang",
                "ref": item.get("ref"),
                "detail": f"{item.get('overhang_mm')} mm beyond the outline bbox",
                "tolerated": True,
                "note": "mechanical part overhangs the board edge; board rect expanded",
            }
        )
    polygon = report.get("polygon") or {}
    for item in polygon.get("components_outside") or []:
        conflicts.append(
            {
                "kind": "polygon_outside",
                "ref": item.get("ref"),
                "detail": (
                    f"corners_outside={item.get('corners_outside')} "
                    f"max_outside={item.get('max_outside_mm')} mm"
                ),
                "tolerated": bool(item.get("allowed")),
                "note": "within edge-overhang allowance"
                if item.get("allowed")
                else "outside the real outline polygon",
            }
        )
    keepouts = report.get("keepouts") or {}
    for item in keepouts.get("conflicts_with_original") or []:
        conflicts.append(
            {
                "kind": "keepout_overlap",
                "ref": item.get("ref"),
                "detail": f"keepout #{item.get('keepout_index')}",
                "tolerated": False,
                "note": "captured part overlaps a parsed keepout",
            }
        )
    return conflicts


def convert_dump(
    payload: Dict[str, Any],
    name: str,
    *,
    source: Optional[object] = None,
    source_sha256: Optional[str] = None,
    source_bytes: Optional[int] = None,
    keepout_plan: Optional[Dict[str, Any]] = None,
    keepout_source: Optional[object] = None,
) -> ConvertedBoard:
    """Convert one EasyCirq PCB dump payload into a :class:`ConvertedBoard`.

    ``keepout_plan`` is an optional parsed ``placement-plan*.json`` payload; when
    it carries ``keepouts`` they are converted into ``Scenario.keepouts``
    (mil -> mm, circle -> axis-aligned square approximation).  All filtering
    decisions are reported with a reason.  Raises :class:`ValueError` when the
    payload is not a usable PCB dump or the unit interpretation is implausible.
    """
    if not isinstance(payload, dict):
        raise ValueError("dump payload must be a JSON object")
    raw_components = payload.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ValueError("dump payload has no 'components' list")
    outline_bbox = _outline_bbox(payload)
    if outline_bbox is None:
        raise ValueError("dump payload has no usable outline bbox/points")
    polygon_points_mil, polygon_closed = _outline_points_mil(payload)
    unit_evidence = verify_units(payload)
    if not unit_evidence.get("mil_interpretation_plausible"):
        raise ValueError(
            "dump units are not plausible as mil (0402 bbox / board size check failed): "
            + json.dumps(unit_evidence, ensure_ascii=False, sort_keys=True)
        )

    report: Dict[str, Any] = {
        "source": str(source) if source is not None else None,
        "source_sha256": source_sha256,
        "source_bytes": source_bytes,
        "project": payload.get("project"),
        "captured_at": payload.get("capturedAt"),
        "semantic_sha256": payload.get("semanticSha256"),
        "fixture_note": payload.get("fixture_note"),
        "outline": {
            "format": (payload.get("outline") or {}).get("format"),
            "source": (payload.get("outline") or {}).get("source"),
            "points": len((payload.get("outline") or {}).get("points") or []),
            "bbox_mil": [round(value, 3) for value in outline_bbox],
            "board_mm": None,
            "approximation": "axis-aligned bounding rectangle of the arc-polyline outline",
        },
        "board_expansion_mm": {"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0},
        "edge_overhang_components": [],
        "units": unit_evidence,
        "components_total": len(raw_components),
        "pads_total": 0,
        "pads_used": 0,
        "pads_merged": 0,
        "dropped_components": [],
        "dropped_nets": [],
        "polygon": None,
        "polygon_ok": None,
        "keepouts": {
            "status": "NOT RUN",
            "source": None,
            "count": 0,
            "geometry": [],
            "reason": "not parsed yet",
        },
    }

    # --- phase 1: validate components, keep edge-overhang parts -----------
    tolerance = 1e-6
    candidates: List[Dict[str, Any]] = []
    seen_refs = set()
    for comp in raw_components:
        if not isinstance(comp, dict):
            continue
        pads = comp.get("pads") or []
        report["pads_total"] += len(pads) if isinstance(pads, list) else 0
        ref = str(comp.get("designator") or "").strip()
        if not ref:
            _drop(report, "", "missing_designator")
            continue
        if ref in seen_refs:
            _drop(report, ref, "duplicate_designator")
            continue
        seen_refs.add(ref)
        raw_bbox = comp.get("bbox")
        if not isinstance(raw_bbox, dict):
            _drop(report, ref, "invalid_bbox")
            continue
        try:
            bx0 = float(raw_bbox["minX"])
            by0 = float(raw_bbox["minY"])
            bx1 = float(raw_bbox["maxX"])
            by1 = float(raw_bbox["maxY"])
        except (KeyError, TypeError, ValueError):
            _drop(report, ref, "invalid_bbox")
            continue
        if (
            not all(math.isfinite(value) for value in (bx0, by0, bx1, by1))
            or bx1 <= bx0
            or by1 <= by0
        ):
            _drop(report, ref, "invalid_bbox")
            continue
        bbox_w_mm = (bx1 - bx0) * MIL_TO_MM
        bbox_h_mm = (by1 - by0) * MIL_TO_MM
        if not (0.1 <= bbox_w_mm <= 100.0 and 0.1 <= bbox_h_mm <= 100.0):
            _drop(report, ref, f"implausible_size_mm:{bbox_w_mm:.3f}x{bbox_h_mm:.3f}")
            continue
        overhang_mil = max(
            0.0,
            outline_bbox[0] - bx0,
            outline_bbox[1] - by0,
            bx1 - outline_bbox[2],
            by1 - outline_bbox[3],
        )
        overhang_mm = overhang_mil * MIL_TO_MM
        if overhang_mm > EDGE_OVERHANG_MM + 1e-9:
            _drop(report, ref, f"out_of_board:overhang={overhang_mm:.3f}mm")
            continue
        rotation = int(round(_finite(comp.get("rotation")) or 0.0)) % 360
        center_x = _finite(comp.get("x"))
        center_y = _finite(comp.get("y"))
        if center_x is None:
            center_x = (bx0 + bx1) / 2.0
        if center_y is None:
            center_y = (by0 + by1) / 2.0
        groups: Dict[str, List[Tuple[float, float]]] = {}
        for pad in pads if isinstance(pads, list) else []:
            if not isinstance(pad, dict):
                continue
            pin = str(pad.get("padNumber") or "").strip()
            if not pin:
                continue
            pad_x = _finite(pad.get("x"))
            pad_y = _finite(pad.get("y"))
            if pad_x is None or pad_y is None:
                continue
            local = _rot_local(pad_x - center_x, pad_y - center_y, rotation)
            groups.setdefault(pin, []).append(local)
        if not groups:
            _drop(report, ref, "no_usable_pads")
            continue
        candidates.append(
            {
                "ref": ref,
                "rotation": rotation,
                "bx0": bx0,
                "by0": by0,
                "bx1": bx1,
                "by1": by1,
                "bbox_w_mm": bbox_w_mm,
                "bbox_h_mm": bbox_h_mm,
                "center_x": center_x,
                "center_y": center_y,
                "groups": groups,
                "overhang_mm": overhang_mm,
            }
        )

    if not candidates:
        raise ValueError("dump payload produced no usable components")

    # --- phase 2: expand the board rectangle just enough for overhangs ----
    min_bx0 = min(item["bx0"] for item in candidates)
    min_by0 = min(item["by0"] for item in candidates)
    max_bx1 = max(item["bx1"] for item in candidates)
    max_by1 = max(item["by1"] for item in candidates)
    exp_left_mm = max(0.0, (outline_bbox[0] - min_bx0) * MIL_TO_MM)
    exp_bottom_mm = max(0.0, (outline_bbox[1] - min_by0) * MIL_TO_MM)
    exp_right_mm = max(0.0, (max_bx1 - outline_bbox[2]) * MIL_TO_MM)
    exp_top_mm = max(0.0, (max_by1 - outline_bbox[3]) * MIL_TO_MM)
    scene_x0_mm = outline_bbox[0] * MIL_TO_MM - exp_left_mm
    scene_y0_mm = outline_bbox[1] * MIL_TO_MM - exp_bottom_mm
    board_w = (outline_bbox[2] - outline_bbox[0]) * MIL_TO_MM + exp_left_mm + exp_right_mm
    board_h = (outline_bbox[3] - outline_bbox[1]) * MIL_TO_MM + exp_bottom_mm + exp_top_mm
    expansion = {
        "left": round(exp_left_mm, 6),
        "right": round(exp_right_mm, 6),
        "bottom": round(exp_bottom_mm, 6),
        "top": round(exp_top_mm, 6),
        "total_mm": round(exp_left_mm + exp_right_mm + exp_bottom_mm + exp_top_mm, 6),
    }
    report["board_expansion_mm"] = expansion
    report["outline"]["board_mm"] = [round(board_w, 4), round(board_h, 4)]
    if expansion["total_mm"] > 0.0:
        report["outline"]["approximation"] += " (expanded for edge-overhang components)"

    # --- phase 3: build Scenario components -------------------------------
    components: Dict[str, Component] = {}
    placements: Dict[str, Tuple[float, float, int]] = {}
    kept_refs: List[str] = []
    for item in candidates:
        ref = item["ref"]
        rotation = item["rotation"]
        bbox_w_mm, bbox_h_mm = item["bbox_w_mm"], item["bbox_h_mm"]
        if rotation in (90, 270):
            body_w_mm, body_h_mm = bbox_h_mm, bbox_w_mm
        else:
            body_w_mm, body_h_mm = bbox_w_mm, bbox_h_mm
        x_mm = item["center_x"] * MIL_TO_MM - scene_x0_mm
        y_mm = item["center_y"] * MIL_TO_MM - scene_y0_mm
        pins: Dict[str, Tuple[float, float]] = {}
        for pin in sorted(item["groups"]):
            points = item["groups"][pin]
            report["pads_used"] += len(points)
            report["pads_merged"] += max(0, len(points) - 1)
            pins[pin] = (
                _round(sum(point[0] for point in points) / len(points) * MIL_TO_MM) or 0.0,
                _round(sum(point[1] for point in points) / len(points) * MIL_TO_MM) or 0.0,
            )
        fixed = ref.upper().startswith(FIXED_PREFIXES)
        components[ref] = Component(
            ref=ref,
            kind=_component_kind(ref),
            w=_round(body_w_mm) or 0.0,
            h=_round(body_h_mm) or 0.0,
            fixed=fixed,
            rotations=(rotation,) if fixed else (0, 90, 180, 270),
            pins=pins,
        )
        placements[ref] = (_round(x_mm) or 0.0, _round(y_mm) or 0.0, rotation)
        kept_refs.append(ref)
        if item["overhang_mm"] > 1e-9:
            report["edge_overhang_components"].append(
                {"ref": ref, "overhang_mm": round(item["overhang_mm"], 6)}
            )

    # --- nets from pad.net -------------------------------------------------
    raw_nets: Dict[str, List[Tuple[str, str]]] = {}
    for comp in raw_components:
        if not isinstance(comp, dict):
            continue
        ref = str(comp.get("designator") or "").strip()
        if ref not in components:
            continue
        for pad in comp.get("pads") or []:
            if not isinstance(pad, dict):
                continue
            net_name = str(pad.get("net") or "").strip()
            pin = str(pad.get("padNumber") or "").strip()
            if not net_name or not pin or pin not in components[ref].pins:
                continue
            entry = (ref, pin)
            bucket = raw_nets.setdefault(net_name, [])
            if entry not in bucket:
                bucket.append(entry)
    nets: List[Net] = []
    for net_name in sorted(raw_nets):
        pins = raw_nets[net_name]
        if len(pins) < 2:
            report["dropped_nets"].append(
                {"name": net_name, "pins": len(pins), "reason": "single_pin_net"}
            )
            continue
        nets.append(Net(net_name, _net_class(net_name), tuple(pins)))
    if not nets:
        raise ValueError("dump payload produced no routable nets (>=2 pins)")

    # --- board polygon validation (ray casting) ---------------------------
    polygon: Optional[BoardPolygon] = None
    polygon_report: Dict[str, Any] = {
        "format": report["outline"]["format"],
        "source": report["outline"]["source"],
        "points": len(polygon_points_mil),
        "closed": bool(polygon_closed),
        "validation": "ray casting; boundary counts as inside",
        "area_mm2": None,
        "bbox_area_mm2": None,
        "area_ratio": None,
        "components_outside": [],
        "violations": [],
    }
    if len(polygon_points_mil) >= 3:
        polygon_mm = [
            (px * MIL_TO_MM - scene_x0_mm, py * MIL_TO_MM - scene_y0_mm)
            for px, py in polygon_points_mil
        ]
        polygon = BoardPolygon(polygon_mm, closed=polygon_closed)
        area = polygon.area_mm2
        pb = polygon.bbox
        bbox_area = max(0.0, (pb[2] - pb[0]) * (pb[3] - pb[1]))
        polygon_report.update(
            {
                "area_mm2": round(area, 4),
                "bbox_area_mm2": round(bbox_area, 4),
                "area_ratio": round(area / bbox_area, 6) if bbox_area > 0 else None,
                "bbox_mm": [round(pb[2] - pb[0], 4), round(pb[3] - pb[1], 4)],
            }
        )
        for ref, comp in components.items():
            x, y, rot = placements[ref]
            rect = bbox(comp, x, y, rot)
            corners_outside, worst = polygon.rect_outside(rect)
            if corners_outside == 0:
                continue
            allowed = worst <= EDGE_OVERHANG_MM + 1e-9
            entry = {
                "ref": ref,
                "corners_outside": corners_outside,
                "max_outside_mm": round(worst, 6),
                "allowed": bool(allowed),
            }
            polygon_report["components_outside"].append(entry)
            if not allowed:
                polygon_report["violations"].append(entry)
        polygon_report["components_outside"].sort(key=lambda item: item["ref"])
        report["polygon_ok"] = not polygon_report["violations"]
    else:
        polygon_report["reason"] = "outline has fewer than 3 points; polygon validation NOT RUN"
    report["polygon"] = polygon_report

    # --- keepouts ---------------------------------------------------------
    keepout_rects, keepout_report = _convert_keepouts(
        keepout_plan, keepout_source, scene_x0_mm, scene_y0_mm, board_w, board_h
    )
    report["keepouts"] = keepout_report
    if keepout_rects:
        conflicts = []
        for ref, comp in components.items():
            x, y, rot = placements[ref]
            rect = bbox(comp, x, y, rot)
            for index, keepout in enumerate(keepout_rects):
                if rect_overlap_area(rect, keepout) > 1e-6:
                    conflicts.append({"ref": ref, "keepout_index": index})
        if conflicts:
            keepout_report["conflicts_with_original"] = conflicts

    fixed_refs = sorted(ref for ref, comp in components.items() if comp.fixed)
    has_non_jsw_mechanical = any(
        not ref.upper().startswith(("J", "SW")) for ref in fixed_refs
    )
    if has_non_jsw_mechanical:
        fixed_mode = "mechanical_prefix"
    elif fixed_refs:
        fixed_mode = "j_sw_prefix"
    else:
        fixed_mode = "all_movable"
    if not fixed_refs:
        report["fixed_mode_note"] = (
            "no J/SW/ANT reference present; all components are movable, original layout "
            "is not preserved by any fixed part"
        )
    base_placement = {ref: placements[ref] for ref in fixed_refs}
    scenario = Scenario(
        name=f"real-{name}",
        board_w=_round(board_w) or 0.0,
        board_h=_round(board_h) or 0.0,
        components=components,
        nets=nets,
        keepouts=list(keepout_rects),
        edge_tol=2.0,
        base_placement=base_placement,
    )

    violations = list(hard_violations(scenario, placements))
    capture_overlaps = _capture_body_overlaps(scenario, placements)
    tolerated_pairs = {tuple(item["pair"]) for item in capture_overlaps}
    tolerant_violations = []
    for violation in violations:
        if violation.startswith("body_overlap:"):
            parts = violation[len("body_overlap:"):].split(":")
            pair = tuple(sorted(parts))
            if len(pair) == 2 and pair in tolerated_pairs:
                continue
        tolerant_violations.append(violation)
    report.update(
        {
            "components_kept": len(components),
            "components_dropped": len(report["dropped_components"]),
            "nets_total": len(raw_nets),
            "nets_kept": len(nets),
            "nets_dropped": len(report["dropped_nets"]),
            "fixed_refs": fixed_refs,
            "fixed_mode": fixed_mode,
            "mechanical_fixed": _mechanical_fixed_entries(components, placements),
            "movable_refs": sorted(ref for ref in components if ref not in fixed_refs),
            "keepouts_applied": len(keepout_rects),
            "original_violations": violations,
            "original_capture_overlaps": capture_overlaps,
            "original_feasible": not violations,
            "original_feasible_tolerant": not tolerant_violations,
            "component_density": _round(
                sum(comp.w * comp.h for comp in components.values()) / (board_w * board_h)
            ),
        }
    )
    report["mechanical_fixed_count"] = len(report["mechanical_fixed"])
    report["original_conflicts"] = _original_conflict_entries(report)
    report["original_conflicts_count"] = len(report["original_conflicts"])
    report["original_conflicts_tolerated"] = all(
        bool(item.get("tolerated")) for item in report["original_conflicts"]
    )
    report["components_type_counts"] = _type_counts(components)
    report["net_class_counts"] = _net_class_counts(nets)
    return ConvertedBoard(
        name=name,
        source=str(source) if source is not None else "",
        source_sha256=source_sha256 or "",
        source_bytes=int(source_bytes or 0),
        scenario=scenario,
        original_placement={ref: placements[ref] for ref in kept_refs},
        report=report,
    )


def _type_counts(components: Dict[str, Component]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for comp in components.values():
        counts[comp.kind] = counts.get(comp.kind, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _net_class_counts(nets: Sequence[Net]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for net in nets:
        counts[net.cls] = counts.get(net.cls, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def load_dump(path: object) -> Dict[str, Any]:
    """Read a dump JSON (read-only) and return its payload."""
    target = pathlib.Path(path)
    return json.loads(target.read_text(encoding="utf-8"))


def find_keepout_plan(
    dump_path: object,
) -> Tuple[Optional[pathlib.Path], Optional[Dict[str, Any]]]:
    """Locate the placement-plan evidence sibling that carries keepouts.

    The dump usually lives in ``<case>/evidence/``; the EasyCirq placement plan
    is written next to it as ``placement-plan-final.json`` or
    ``placement-plan.json``.  Returns ``(path, payload)`` or ``(None, None)``.
    """
    target = pathlib.Path(dump_path)
    search_dirs = [target.parent, target.parent.parent]
    seen = set()
    for directory in search_dirs:
        if directory in seen:
            continue
        seen.add(directory)
        for filename in KEEPOUT_PLAN_CANDIDATES:
            candidate = directory / filename
            if not candidate.exists():
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                return candidate, payload
    return None, None


def _is_dump_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("components"), list)
        and bool(payload.get("components"))
        and isinstance(payload.get("outline"), dict)
    )


def _short_case_name(case_name: str) -> str:
    if case_name in _CASE_ALIASES:
        return _CASE_ALIASES[case_name]
    stripped = case_name
    for marker in ("-2026-", "-20261027", "-2025-", "-2024-"):
        index = stripped.find(marker)
        if index > 0:
            stripped = stripped[:index]
            break
    return stripped


def _dump_preference(path: pathlib.Path) -> Tuple[int, int, str]:
    """Rank dump files within one case: final > baseline > other dumps."""
    name = path.name.lower()
    if "pcb-dump-final" in name or "pcb-board-final" in name:
        rank = 0
    elif "board-baseline" in name and "accepted" not in name:
        rank = 1
    elif "baseline" in name:
        rank = 2
    elif "final" in name:
        rank = 3
    else:
        rank = 4
    depth = len(path.parts)
    return (rank, depth, str(path))


@dataclass
class BoardSource:
    """One discovered real-board dump."""

    name: str
    case: str
    path: pathlib.Path
    alternatives: List[str] = field(default_factory=list)
    rank: int = 4
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    selection_reason: str = ""


def _dump_rank_label(rank: int) -> str:
    return {
        0: "preferred_final",
        1: "preferred_baseline",
        2: "baseline_variant",
        3: "final_variant",
        4: "other_dump",
    }.get(int(rank), "other_dump")


def discover_cases(
    cases_root: Optional[object] = None,
    *,
    detailed: bool = False,
):
    """Auto-discover one preferred dump per EasyCirq case directory.

    Every ``*.json`` under the cases root is parsed (read-only); a file qualifies
    as a dump when it has a non-empty ``components`` list and an ``outline``
    object.  Per case the preferred file wins (``pcb-dump-final`` >
    ``pcb-board-final`` > ``board-baseline`` > other dumps); the rest are kept as
    ``alternatives`` in the report and as ranked ``candidates`` on the board
    source.  Cases without any dump are returned in the skipped list with a
    reason.  With ``detailed=True`` a third list with one record per case
    (``BOARD``/``SKIPPED``, chosen file, ranked candidates, reason) is returned
    for the v3 report.
    """
    root = pathlib.Path(cases_root) if cases_root is not None else DEFAULT_CASES_ROOT
    boards: List[BoardSource] = []
    skipped: List[Dict[str, Any]] = []
    case_reports: List[Dict[str, Any]] = []
    if not root.is_dir():
        skipped.append({"case": str(root), "reason": f"cases root not found: {root}"})
        case_reports.append(
            {"case": str(root), "status": "SKIPPED", "reason": f"cases root not found: {root}"}
        )
        return (boards, skipped, case_reports) if detailed else (boards, skipped)
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        candidates: List[Tuple[Tuple[int, int, str], pathlib.Path]] = []
        json_count = 0
        for json_path in sorted(case_dir.rglob("*.json")):
            json_count += 1
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if _is_dump_payload(payload):
                candidates.append((_dump_preference(json_path), json_path))
        if not candidates:
            reason = "no dump-like JSON (components+outline) found"
            skipped.append({"case": case_dir.name, "reason": reason, "json_files": json_count})
            case_reports.append(
                {
                    "case": case_dir.name,
                    "status": "SKIPPED",
                    "reason": reason,
                    "json_files": json_count,
                    "candidates": [],
                }
            )
            continue
        candidates.sort(key=lambda item: item[0])
        candidate_records: List[Dict[str, Any]] = []
        for index, (key, path) in enumerate(candidates):
            candidate_records.append(
                {
                    "file": str(path.relative_to(root)),
                    "rank": int(key[0]),
                    "rank_label": _dump_rank_label(key[0]),
                    "selected": index == 0,
                }
            )
        chosen_path = candidates[0][1]
        alternatives = [str(path.relative_to(root)) for _key, path in candidates[1:]]
        chosen_rank = int(candidates[0][0][0])
        board_name = _short_case_name(case_dir.name)
        selection_reason = (
            f"preferred among {len(candidates)} dump-like file(s) "
            f"({_dump_rank_label(chosen_rank)})"
        )
        boards.append(
            BoardSource(
                name=board_name,
                case=case_dir.name,
                path=chosen_path,
                alternatives=alternatives,
                rank=chosen_rank,
                candidates=candidate_records,
                selection_reason=selection_reason,
            )
        )
        case_reports.append(
            {
                "case": case_dir.name,
                "status": "BOARD",
                "name": board_name,
                "chosen": str(chosen_path.relative_to(root)),
                "candidates": candidate_records,
                "json_files": json_count,
                "reason": None,
            }
        )
    if detailed:
        return boards, skipped, case_reports
    return boards, skipped


def load_and_convert(
    path: object,
    name: Optional[str] = None,
    *,
    load_keepouts: bool = True,
) -> ConvertedBoard:
    """Read a dump file, hash it, locate keepouts and convert it."""
    target = pathlib.Path(path)
    payload = load_dump(target)
    sha = sha256_file(target)
    keepout_plan = None
    keepout_source = None
    if load_keepouts:
        keepout_source, keepout_plan = find_keepout_plan(target)
    return convert_dump(
        payload,
        name=name or target.stem,
        source=str(target),
        source_sha256=sha,
        source_bytes=target.stat().st_size,
        keepout_plan=keepout_plan,
        keepout_source=keepout_source,
    )


# --------------------------------------------------------------------------- #
# metrics / comparison
# --------------------------------------------------------------------------- #
def _router_summary(result: Any) -> Dict[str, Any]:
    return {
        "status": "ROUTED",
        "completion": _round(result.completion),
        "failed_nets": [str(name) for name in result.failed_nets],
        "wirelength_mm": _round(result.wirelength_mm, 3),
        "vias": int(result.vias),
        "overflow": int(result.overflow),
        "runtime_s": _round(result.runtime_s, 3),
    }


def evaluate_placement(
    scenario: Scenario,
    placement: Placement,
    *,
    seed: int = DEFAULT_SEED,
) -> Dict[str, Any]:
    """Compute feasibility, v1/v2 truth and router metrics for one placement."""
    violations = list(hard_violations(scenario, placement))
    truth_v1 = PhysicsSimulator(scenario, seed=seed).score(placement)
    truth_v2 = PhysicsSimulatorV2(scenario, seed=seed).score(placement)
    try:
        route = GridRouter(scenario, grid_mm=ROUTER_GRID_MM, layers=ROUTER_LAYERS).route(placement)
        router = _router_summary(route)
    except Exception as exc:  # noqa: BLE001 - report, never crash the comparison
        router = {
            "status": "NOT RUN",
            "completion": None,
            "failed_nets": [],
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "feasible": not violations,
        "violations": violations,
        "truth_v1": _round(truth_v1),
        "truth_v2": _round(truth_v2),
        "router": router,
    }


def _strip_volatile(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Drop wall-clock fields so the report stays deterministic."""
    out: Dict[str, Any] = {}
    for key, value in stats.items():
        lowered = str(key).lower()
        if "runtime" in lowered or "elapsed" in lowered or "time" in lowered:
            continue
        out[str(key)] = _json_safe(value)
    return out


def _delta(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None:
        return None
    return _round(float(new) - float(old))


def _metrics_value(metrics: Dict[str, Any], path: Sequence[str]) -> Optional[float]:
    value: Any = metrics
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return _finite(value)


def run_board(
    converted: ConvertedBoard,
    *,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
) -> Dict[str, Any]:
    """Compare original / solver_v2(tuned route_cost) / route_opt repair."""
    scenario = converted.scenario
    timings: Dict[str, float] = {}
    started = time.perf_counter()
    original_metrics = evaluate_placement(scenario, converted.original_placement, seed=seed)
    timings["original"] = round(time.perf_counter() - started, 3)
    original_metrics["elapsed_s"] = timings["original"]
    row: Dict[str, Any] = {
        "name": converted.name,
        "source": converted.report.get("source"),
        "source_sha256": converted.report.get("source_sha256"),
        "source_bytes": converted.report.get("source_bytes"),
        "project": converted.report.get("project"),
        "captured_at": converted.report.get("captured_at"),
        "fixture_note": converted.report.get("fixture_note"),
        "conversion": converted.report,
        "original": original_metrics,
    }
    row["original"]["feasible_tolerant"] = bool(
        converted.report.get("original_feasible_tolerant")
    )
    row["original"]["capture_model_overlaps"] = list(
        converted.report.get("original_capture_overlaps") or []
    )
    row["mechanical_fixed"] = list(converted.report.get("mechanical_fixed") or [])
    row["original_conflicts"] = list(converted.report.get("original_conflicts") or [])
    row["optimized"] = {"status": "NOT RUN"}
    row["repair"] = {"status": "NOT RUN"}
    row["timings_s"] = timings
    if not optimise:
        return row

    try:
        objective = tuned_objective(scenario)
        config = select_config(scenario)
        row["objective"] = {
            "class": type(objective).__name__,
            "w_route": float(config["w_route"]),
            "profile": str(config["profile"]),
            "source": str(config.get("source")),
            "reason": str(config.get("reason")),
        }
        started = time.perf_counter()
        optimized_placement, proxy_cost, solver_stats = solve(
            scenario, objective.cost, seed=seed, steps=steps
        )
        solve_elapsed = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        optimized_metrics = evaluate_placement(scenario, optimized_placement, seed=seed)
        eval_elapsed = round(time.perf_counter() - started, 3)
        optimized_metrics["solve_elapsed_s"] = solve_elapsed
        optimized_metrics["elapsed_s"] = round(solve_elapsed + eval_elapsed, 3)
        row["optimized"] = optimized_metrics
        row["optimized"]["proxy_cost"] = _round(proxy_cost)
        row["solver_stats"] = _strip_volatile(solver_stats)
        timings["optimize_solve"] = solve_elapsed
        timings["optimized"] = optimized_metrics["elapsed_s"]
    except Exception as exc:  # noqa: BLE001
        row["optimized"] = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        objective = None
        config = None

    if objective is not None:
        try:
            started = time.perf_counter()
            repaired_placement, _truth, _route_result, repair_stats = repair_routes(
                scenario,
                objective.cost,
                seed=seed,
                steps=steps,
                max_routes=max_routes,
            )
            repair_elapsed = round(time.perf_counter() - started, 3)
            started = time.perf_counter()
            repair_metrics = evaluate_placement(scenario, repaired_placement, seed=seed)
            repair_eval_elapsed = round(time.perf_counter() - started, 3)
            repair_metrics["repair_stage_s"] = repair_elapsed
            repair_metrics["elapsed_s"] = round(repair_elapsed + repair_eval_elapsed, 3)
            row["repair"] = repair_metrics
            row["repair_stats"] = _strip_volatile(repair_stats)
            timings["repair_stage"] = repair_elapsed
            timings["repair"] = repair_metrics["elapsed_s"]
        except Exception as exc:  # noqa: BLE001
            row["repair"] = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

    original = row["original"]
    deltas: Dict[str, Any] = {}
    for group in ("optimized", "repair"):
        metrics = row.get(group) or {}
        deltas[f"{group}_truth_v2"] = _delta(
            _metrics_value(metrics, ("truth_v2",)), _metrics_value(original, ("truth_v2",))
        )
        deltas[f"{group}_completion"] = _delta(
            _metrics_value(metrics, ("router", "completion")),
            _metrics_value(original, ("router", "completion")),
        )
        deltas[f"{group}_feasible"] = bool(metrics.get("feasible"))
    row["deltas"] = deltas
    return row


# --------------------------------------------------------------------------- #
# experiment / report
# --------------------------------------------------------------------------- #
def _resolve_sources(
    sources: Optional[Sequence[Tuple[str, pathlib.Path]]] = None,
    cases_root: Optional[pathlib.Path] = None,
) -> List[Tuple[str, pathlib.Path]]:
    if sources:
        return [(str(name), pathlib.Path(path)) for name, path in sources]
    if cases_root is not None:
        root = pathlib.Path(cases_root)
        return [
            ("mcu-i2c", root / "mcu-i2c-s3-2026-10-26" / "evidence" / "pcb-dump-final.json"),
            ("photo-led", root / "photo-led-pcb-2026-10-26" / "evidence" / "pcb-dump-final.json"),
            (
                "dual-button",
                root / "dual-button-led-night-20261027" / "negative-direct-move" / "board-baseline.json",
            ),
        ]
    return list(DEFAULT_SOURCES)


def run_all(
    sources: Optional[Sequence[Tuple[str, pathlib.Path]]] = None,
    *,
    cases_root: Optional[pathlib.Path] = None,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
) -> Dict[str, Any]:
    """Convert every source dump and run the full comparison; returns a report."""
    started_wall = datetime.datetime.now().astimezone()
    t_start = time.perf_counter()
    source_list = _resolve_sources(sources, cases_root=cases_root)
    rows: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for name, path in source_list:
        target = pathlib.Path(path)
        if not target.exists():
            missing.append({"name": name, "source": str(target), "status": "MISSING"})
            continue
        converted = load_and_convert(target, name=name)
        rows.append(
            run_board(
                converted,
                steps=steps,
                seed=seed,
                max_routes=max_routes,
                optimise=optimise,
            )
        )
    aggregate = _aggregate(rows)
    aggregate["n_available"] = len(rows)
    aggregate["n_missing"] = len(missing)
    return {
        "schema": REALBOARD_SCHEMA,
        "generated_at": started_wall.strftime("%Y-%m-%d %H:%M:%S %z"),
        "runtime_s": round(time.perf_counter() - t_start, 2),
        "config": {
            "steps": int(steps),
            "seed": int(seed),
            "max_routes": int(max_routes),
            "optimise": bool(optimise),
            "solver": "solver_v2.solve",
            "objective": "route_cost.tuned_objective (ProxyObjective + tuned route penalty)",
            "repair": "route_opt.repair_routes",
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
            "truth": "physics_v2.PhysicsSimulatorV2 (seed) + v1 PhysicsSimulator",
            "unit_scale_mm_per_mil": MIL_TO_MM,
        },
        "sources": [{"name": name, "source": str(path)} for name, path in source_list],
        "boards": rows,
        "missing_sources": missing,
        "aggregate": aggregate,
        "limits": list(LIMITS),
    }


def _aggregate(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    def mean(group: str, path: Sequence[str]) -> Optional[float]:
        values = [
            value
            for value in (_metrics_value(row.get(group) or {}, path) for row in rows)
            if value is not None
        ]
        return _round(sum(values) / len(values)) if values else None

    return {
        "n_boards": len(rows),
        "n_available": len(rows),
        "n_missing": 0,
        "all_feasible_original": all(bool(row["original"].get("feasible")) for row in rows) if rows else None,
        "all_feasible_optimized": all(bool((row.get("optimized") or {}).get("feasible")) for row in rows) if rows else None,
        "all_feasible_repair": all(bool((row.get("repair") or {}).get("feasible")) for row in rows) if rows else None,
        "mean_original_truth_v2": mean("original", ("truth_v2",)),
        "mean_optimized_truth_v2": mean("optimized", ("truth_v2",)),
        "mean_repair_truth_v2": mean("repair", ("truth_v2",)),
        "mean_original_completion": mean("original", ("router", "completion")),
        "mean_optimized_completion": mean("optimized", ("router", "completion")),
        "mean_repair_completion": mean("repair", ("router", "completion")),
        "mean_completion_gain_optimized": _round(
            (
                mean("optimized", ("router", "completion")) or 0.0
            ) - (
                mean("original", ("router", "completion")) or 0.0
            )
        ),
        "mean_completion_gain_repair": _round(
            (
                mean("repair", ("router", "completion")) or 0.0
            ) - (
                mean("original", ("router", "completion")) or 0.0
            )
        ),
    }


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #
def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_delta(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:+.4f}"


def _metrics_row(label: str, metrics: Dict[str, Any]) -> str:
    router = metrics.get("router") or {}
    return (
        f"| {label} | {_fmt(metrics.get('feasible'))} | {_fmt(metrics.get('truth_v1'))} | "
        f"{_fmt(metrics.get('truth_v2'))} | {_fmt(router.get('completion'))} | "
        f"{_fmt(router.get('vias'))} | {_fmt(router.get('wirelength_mm'), 1)} | "
        f"`{router.get('failed_nets')}` |"
    )


def render_markdown(report: Dict[str, Any]) -> str:
    """Render the real-board comparison report as markdown."""
    aggregate = report.get("aggregate") or {}
    config = report.get("config") or {}
    lines: List[str] = []
    lines.append("# P4.5 真实板 dump → Scenario：原布局 vs 优化 vs route repair\n")
    lines.append(f"- schema：`{report.get('schema')}`")
    lines.append(
        f"- 配置：steps={config.get('steps')}，seed={config.get('seed')}，max_routes={config.get('max_routes')}；"
        f"solver=`{config.get('solver')}`，objective=`{config.get('objective')}`，router=`{config.get('router')}`"
    )
    lines.append(f"- 运行：{aggregate.get('n_boards')} 块真实板，耗时 {report.get('runtime_s')} s")
    if report.get("missing_sources"):
        lines.append(f"- 缺失源（跳过）：{[item['name'] for item in report['missing_sources']]}")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append("| 组 | mean truth_v2 | mean completion | 全部硬可行 |")
    lines.append("|---|---|---|---|")
    for group, feasible_key in (
        ("original", "all_feasible_original"),
        ("optimized", "all_feasible_optimized"),
        ("repair", "all_feasible_repair"),
    ):
        lines.append(
            f"| {group} | {_fmt(aggregate.get(f'mean_{group}_truth_v2'))} | "
            f"{_fmt(aggregate.get(f'mean_{group}_completion'))} | {aggregate.get(feasible_key)} |"
        )
    lines.append(
        f"\n- completion 增益：optimized {_fmt_delta(aggregate.get('mean_completion_gain_optimized'))}，"
        f"repair {_fmt_delta(aggregate.get('mean_completion_gain_repair'))}"
    )
    lines.append("")

    lines.append("## 单位与对象\n")
    lines.append("| 板 | source SHA256 | 器件 kept/total | pads used/total | nets kept/total | board mm | passive bbox 中位 mm | mil 可信 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in report.get("boards") or []:
        conversion = row.get("conversion") or {}
        units = conversion.get("units") or {}
        board_mm = units.get("board_mm") or ["—", "—"]
        passive = (units.get("passive_bbox_long_side_mm") or {}).get("median")
        sha = str(row.get("source_sha256") or "")[:16]
        lines.append(
            f"| {row.get('name')} | `{sha}` | "
            f"{conversion.get('components_kept')}/{conversion.get('components_total')} | "
            f"{conversion.get('pads_used')}/{conversion.get('pads_total')} | "
            f"{conversion.get('nets_kept')}/{conversion.get('nets_total')} | "
            f"{_fmt(board_mm[0], 2)} × {_fmt(board_mm[1], 2)} | {_fmt(passive, 3)} | "
            f"{_fmt(units.get('mil_interpretation_plausible'))} |"
        )
    lines.append("")

    for row in report.get("boards") or []:
        conversion = row.get("conversion") or {}
        lines.append(f"## {row.get('name')}\n")
        lines.append(f"- 源：`{row.get('source')}`（{conversion.get('source_bytes')} bytes）")
        lines.append(f"- SHA256：`{row.get('source_sha256')}`")
        lines.append(
            f"- project={conversion.get('project')} capturedAt={conversion.get('captured_at')} "
            f"semanticSha256=`{str(conversion.get('semantic_sha256') or '')[:16]}`"
        )
        if conversion.get("fixture_note"):
            lines.append(f"- fixture note：{conversion.get('fixture_note')}")
        fixed_refs = conversion.get("fixed_refs") or []
        lines.append(
            f"- 对象：器件 {conversion.get('components_kept')}/{conversion.get('components_total')} 保留"
            f"（丢弃 {conversion.get('components_dropped')}），pads {conversion.get('pads_used')}/"
            f"{conversion.get('pads_total')} 使用（合并 {conversion.get('pads_merged')}），"
            f"nets {conversion.get('nets_kept')}/{conversion.get('nets_total')} 保留"
            f"（丢弃 {conversion.get('nets_dropped')}），keepouts=0"
        )
        lines.append(
            f"- 固定件（J/SW 前缀）：{fixed_refs or '（无，全部可动）'}；"
            f"可动 {len(conversion.get('movable_refs') or [])} 个；"
            f"器件类型 {conversion.get('components_type_counts')}；"
            f"网类 {conversion.get('net_class_counts')}；"
            f"密度 {_fmt(conversion.get('component_density'))}"
        )
        drops = conversion.get("dropped_components") or []
        if drops:
            lines.append("- 丢弃器件：")
            for item in drops:
                lines.append(f"  - `{item.get('ref')}`：{item.get('reason')}")
        dropped_nets = conversion.get("dropped_nets") or []
        if dropped_nets:
            lines.append("- 丢弃网络：" + "，".join(
                f"`{item.get('name')}`({item.get('reason')})" for item in dropped_nets
            ))
        outline = conversion.get("outline") or {}
        lines.append(
            f"- 板框：{_fmt(outline.get('board_mm', [None, None])[0], 2)} × "
            f"{_fmt(outline.get('board_mm', [None, None])[1], 2)} mm"
            f"（{outline.get('format')}，{outline.get('points')} 点，"
            f"{outline.get('approximation')}）"
        )
        units = conversion.get("units") or {}
        lines.append(
            f"- 单位验证：mil × {MIL_TO_MM} → mm；passive bbox 长边 "
            f"{units.get('passive_bbox_long_side_mm')}；closest-to-0402 = "
            f"{units.get('closest_to_0402_mil')} mil；可信={units.get('mil_interpretation_plausible')}，"
            f"mm 解释被否={units.get('mm_interpretation_rejected')}"
        )
        examples = units.get("examples") or []
        if examples:
            shown = "，".join(
                f"{item.get('ref')} {item.get('bbox_mil')} mil = {item.get('bbox_mm')} mm"
                for item in examples[:3]
            )
            lines.append(f"- 例：{shown}")
        if conversion.get("original_violations"):
            lines.append(f"- 原布局硬约束违反：{conversion.get('original_violations')}")
        overlaps = conversion.get("original_capture_overlaps") or []
        if overlaps:
            lines.append(
                f"- 拍摄 bbox 近似重叠（courtyard artifact，<= {CAPTURE_OVERLAP_TOL_MM2} mm²）："
                + "，".join(
                    f"{item.get('pair')} {item.get('area_mm2')} mm²" for item in overlaps
                )
                + f"；original_feasible_tolerant={conversion.get('original_feasible_tolerant')}"
            )
        lines.append("")
        lines.append("| 组 | 硬可行 | truth_v1 | truth_v2 | router completion | vias | wirelength mm | failed_nets |")
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.append(_metrics_row("original", row.get("original") or {}))
        lines.append(_metrics_row("optimized (solver_v2+tuned)", row.get("optimized") or {}))
        lines.append(_metrics_row("repair (route_opt)", row.get("repair") or {}))
        deltas = row.get("deltas") or {}
        lines.append(
            f"\n- Δ vs original：optimized truth_v2 {_fmt_delta(deltas.get('optimized_truth_v2'))}，"
            f"completion {_fmt_delta(deltas.get('optimized_completion'))}；"
            f"repair truth_v2 {_fmt_delta(deltas.get('repair_truth_v2'))}，"
            f"completion {_fmt_delta(deltas.get('repair_completion'))}"
        )
        objective = row.get("objective") or {}
        if objective:
            lines.append(
                f"- tuned objective：w_route={objective.get('w_route')} "
                f"profile={objective.get('profile')} source={objective.get('source')} "
                f"（{objective.get('reason')}）"
            )
        solver_stats = row.get("solver_stats") or {}
        repair_stats = row.get("repair_stats") or {}
        if solver_stats:
            lines.append(
                f"- solver：{solver_stats.get('solver')} steps={solver_stats.get('steps')} "
                f"restarts={solver_stats.get('restarts')} accepted={solver_stats.get('accepted')}"
            )
        if repair_stats:
            lines.append(
                f"- repair：route_calls={repair_stats.get('routes_calls')} "
                f"moves_accepted={repair_stats.get('moves_accepted')} "
                f"completion {repair_stats.get('initial_completion')}→"
                f"{repair_stats.get('final_completion')}"
            )
        lines.append("")

    lines.append("## 边界与限制\n")
    for item in report.get("limits") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("> 本报告由 `python -m mp_place.realboard` 自动生成；源 dump 只读、未施加布局、未运行 DRC/EDA。")
    return "\n".join(lines) + "\n"


def write_reports(
    report: Dict[str, Any],
    out_dir: Optional[object] = None,
) -> Dict[str, pathlib.Path]:
    """Write ``report_realboard.md`` + ``report_realboard.json``; return paths."""
    target_dir = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / REPORT_JSON
    md_path = target_dir / REPORT_MD
    json_path.write_text(
        json.dumps(_json_safe(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


# --------------------------------------------------------------------------- #
# v2: board polygon validation + auto-discovery + keepouts
# --------------------------------------------------------------------------- #
def _conversion_of(row: Dict[str, Any]) -> Dict[str, Any]:
    conversion = row.get("conversion")
    return conversion if isinstance(conversion, dict) else {}


def _polygon_of(row: Dict[str, Any]) -> Dict[str, Any]:
    polygon = _conversion_of(row).get("polygon")
    return polygon if isinstance(polygon, dict) else {}


def _keepouts_of(row: Dict[str, Any]) -> Dict[str, Any]:
    keepouts = _conversion_of(row).get("keepouts")
    return keepouts if isinstance(keepouts, dict) else {}


def _aggregate_v2(
    rows: Sequence[Dict[str, Any]],
    skipped: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    aggregate = _aggregate(rows)
    aggregate.update(
        {
            "n_cases": len(rows) + len(skipped),
            "n_boards": len(rows),
            "n_skipped_cases": len(skipped),
            "n_polygon_ok": sum(
                1 for row in rows if _conversion_of(row).get("polygon_ok") is True
            ),
            "n_keepouts_applied": sum(
                1 for row in rows if _keepouts_of(row).get("status") == "APPLIED"
            ),
            "n_keepout_rects": sum(
                int(_keepouts_of(row).get("count") or 0) for row in rows
            ),
            "n_components_outside_polygon": sum(
                len(_polygon_of(row).get("components_outside") or []) for row in rows
            ),
            "n_polygon_violations": sum(
                len(_polygon_of(row).get("violations") or []) for row in rows
            ),
            "n_edge_overhang_components": sum(
                len(_conversion_of(row).get("edge_overhang_components") or [])
                for row in rows
            ),
            "all_feasible_original_tolerant": all(
                bool((row.get("original") or {}).get("feasible_tolerant")) for row in rows
            )
            if rows
            else None,
            "n_original_capture_overlaps": sum(
                len(_conversion_of(row).get("original_capture_overlaps") or [])
                for row in rows
            ),
            "polygon_policy": "ray casting; boundary counts as inside; outline bbox is the solver board",
            "keepouts_policy": "placement-plan keepouts applied when parseable; otherwise NOT RUN",
            "original_feasibility_note": (
                "capture bbox includes silk/courtyard; body overlaps <= 1.0 mm2 are reported "
                "as capture-model overlaps and tolerated by original_feasible_tolerant"
            ),
        }
    )
    return aggregate


def run_all_v2(
    sources: Optional[Sequence[object]] = None,
    *,
    cases_root: Optional[object] = None,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
) -> Dict[str, Any]:
    """Auto-discover real boards, convert them and run the full comparison.

    ``sources`` may be a list of ``(name, path)`` pairs or
    :class:`BoardSource` objects to bypass case discovery (used by tests and by
    the CLI ``--source`` flag); ``cases_root`` overrides the discovery root.
    Returns the ``mp_place.realboard/v2`` report.
    """
    started_wall = datetime.datetime.now().astimezone()
    t_start = time.perf_counter()
    board_sources: List[BoardSource] = []
    skipped: List[Dict[str, Any]] = []
    discovery: Dict[str, Any]
    if sources:
        for item in sources:
            if isinstance(item, BoardSource):
                board_sources.append(item)
            else:
                try:
                    name, path = item  # type: ignore[misc]
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"sources entries must be BoardSource or (name, path), got {item!r}") from exc
                target = pathlib.Path(path)
                board_sources.append(
                    BoardSource(name=str(name), case=target.parent.name, path=target)
                )
        discovery = {
            "mode": "explicit_sources",
            "cases_root": None,
            "n_cases": len(board_sources),
            "boards": [
                {
                    "name": source.name,
                    "case": source.case,
                    "path": str(source.path),
                    "alternatives": list(source.alternatives),
                }
                for source in board_sources
            ],
            "skipped_cases": [],
        }
    else:
        root = pathlib.Path(cases_root) if cases_root is not None else DEFAULT_CASES_ROOT
        board_sources, skipped = discover_cases(root)
        discovery = {
            "mode": "auto_discovery",
            "cases_root": str(root),
            "n_cases": len(board_sources) + len(skipped),
            "boards": [
                {
                    "name": source.name,
                    "case": source.case,
                    "path": str(source.path),
                    "alternatives": list(source.alternatives),
                }
                for source in board_sources
            ],
            "skipped_cases": list(skipped),
        }

    rows: List[Dict[str, Any]] = []
    for source in board_sources:
        if not source.path.exists():
            skipped.append(
                {"case": source.case, "reason": f"dump missing: {source.path}"}
            )
            continue
        converted = load_and_convert(source.path, name=source.name)
        row = run_board(
            converted,
            steps=steps,
            seed=seed,
            max_routes=max_routes,
            optimise=optimise,
        )
        row["case"] = source.case
        row["alternatives"] = list(source.alternatives)
        row["dump_rank"] = int(source.rank)
        rows.append(row)
    if skipped:
        discovery["skipped_cases"] = list(skipped)
        discovery["n_cases"] = len(rows) + len(skipped)
    aggregate = _aggregate_v2(rows, skipped)
    return {
        "schema": REALBOARD_SCHEMA_V2,
        "generated_at": started_wall.strftime("%Y-%m-%d %H:%M:%S %z"),
        "runtime_s": round(time.perf_counter() - t_start, 2),
        "config": {
            "steps": int(steps),
            "seed": int(seed),
            "max_routes": int(max_routes),
            "optimise": bool(optimise),
            "solver": "solver_v2.solve",
            "objective": "route_cost.tuned_objective (adaptive RouteAwareObjective over ProxyObjective)",
            "repair": "route_opt.repair_routes",
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
            "truth": "physics_v2.PhysicsSimulatorV2 (seed) + v1 PhysicsSimulator",
            "unit_scale_mm_per_mil": MIL_TO_MM,
            "edge_overhang_limit_mm": EDGE_OVERHANG_MM,
            "keepout_plan_candidates": list(KEEPOUT_PLAN_CANDIDATES),
        },
        "discovery": discovery,
        "boards": rows,
        "skipped_cases": list(skipped),
        "aggregate": aggregate,
        "limits": list(LIMITS),
    }


def render_markdown_v2(report: Dict[str, Any]) -> str:
    """Render the P4.6 real-board report (polygon + discovery + keepouts)."""
    aggregate = report.get("aggregate") or {}
    config = report.get("config") or {}
    discovery = report.get("discovery") or {}
    boards = report.get("boards") or []
    skipped = report.get("skipped_cases") or []
    lines: List[str] = []
    lines.append("# P4.6 真实板 dump → Scenario v2（多边形板框 + 自动发现 + keepouts）\n")
    lines.append(f"- schema：`{report.get('schema')}`")
    lines.append(
        f"- 配置：steps={config.get('steps')}，seed={config.get('seed')}，max_routes={config.get('max_routes')}；"
        f"solver=`{config.get('solver')}`，objective=`{config.get('objective')}`，router=`{config.get('router')}`"
    )
    lines.append(
        f"- 发现模式：{discovery.get('mode')}；cases root=`{discovery.get('cases_root')}`；"
        f"case 数 {discovery.get('n_cases')}，板数 {len(boards)}，跳过 case {len(skipped)}"
    )
    lines.append(f"- 运行耗时：{report.get('runtime_s')} s\n")
    if skipped:
        lines.append("### 跳过的 case\n")
        for item in skipped:
            lines.append(f"- `{item.get('case')}`：{item.get('reason')}")
        lines.append("")
    lines.append("## 汇总\n")
    lines.append("| 组 | mean truth_v2 | mean completion | 全部硬可行 |")
    lines.append("|---|---|---|---|")
    for group, feasible_key in (
        ("original", "all_feasible_original"),
        ("optimized", "all_feasible_optimized"),
        ("repair", "all_feasible_repair"),
    ):
        lines.append(
            f"| {group} | {_fmt(aggregate.get(f'mean_{group}_truth_v2'))} | "
            f"{_fmt(aggregate.get(f'mean_{group}_completion'))} | {aggregate.get(feasible_key)} |"
        )
    lines.append(
        f"\n- completion 增益：optimized {_fmt_delta(aggregate.get('mean_completion_gain_optimized'))}，"
        f"repair {_fmt_delta(aggregate.get('mean_completion_gain_repair'))}"
    )
    lines.append(
        f"- 多边形校验：polygon_ok {aggregate.get('n_polygon_ok')}/{aggregate.get('n_boards')}，"
        f"polygon violations {aggregate.get('n_polygon_violations')}，outside components "
        f"{aggregate.get('n_components_outside_polygon')}，edge-overhang {aggregate.get('n_edge_overhang_components')}"
    )
    lines.append(
        f"- keepouts：APPLIED {aggregate.get('n_keepouts_applied')}/{aggregate.get('n_boards')}"
        f"（rect 合计 {aggregate.get('n_keepout_rects')}）；未解析的板在上述 keepout 列标 NOT RUN"
    )
    lines.append(
        f"- 原布局硬可行：{aggregate.get('all_feasible_original')}（容忍拍摄 bbox 近似重叠后 "
        f"{aggregate.get('all_feasible_original_tolerant')}；capture-model overlaps "
        f"{aggregate.get('n_original_capture_overlaps')} 处，<= 1.0 mm²）\n"
    )

    lines.append("## 板级总览\n")
    lines.append("| 板 | case | source SHA256 | 器件 kept/total | pads used | nets kept/total | board mm | polygon 点/面积比 | polygon ok | outside 器件 | keepouts |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for row in boards:
        conversion = _conversion_of(row)
        outline = conversion.get("outline") or {}
        board_mm = outline.get("board_mm") or [None, None]
        polygon = _polygon_of(row)
        keepouts = _keepouts_of(row)
        keepout_label = keepouts.get("status") or "NOT RUN"
        if keepout_label == "APPLIED":
            keepout_label = f"APPLIED×{keepouts.get('count')}"
        lines.append(
            f"| {row.get('name')} | `{row.get('case')}` | `{str(row.get('source_sha256') or '')[:12]}` | "
            f"{conversion.get('components_kept')}/{conversion.get('components_total')} | "
            f"{conversion.get('pads_used')} | "
            f"{conversion.get('nets_kept')}/{conversion.get('nets_total')} | "
            f"{_fmt(board_mm[0], 2)} × {_fmt(board_mm[1], 2)} | "
            f"{polygon.get('points')} / {_fmt(polygon.get('area_ratio'), 4)} | "
            f"{_fmt(polygon.get('violations') is not None and not polygon.get('violations'))} | "
            f"{len(polygon.get('components_outside') or [])} | {keepout_label} |"
        )
    for item in skipped:
        lines.append(f"| — | `{item.get('case')}` | — | — | — | — | — | — | — | — | 跳过：{item.get('reason')} |")
    lines.append("")

    for row in boards:
        conversion = _conversion_of(row)
        outline = conversion.get("outline") or {}
        polygon = _polygon_of(row)
        keepouts = _keepouts_of(row)
        units = conversion.get("units") or {}
        lines.append(f"## {row.get('name')}（case `{row.get('case')}`）\n")
        lines.append(f"- 源：`{row.get('source')}`（{conversion.get('source_bytes')} bytes）")
        lines.append(f"- SHA256：`{row.get('source_sha256')}`")
        lines.append(
            f"- project={conversion.get('project')} capturedAt={conversion.get('captured_at')} "
            f"semanticSha256=`{str(conversion.get('semantic_sha256') or '')[:16]}`"
        )
        if conversion.get("fixture_note"):
            lines.append(f"- fixture note：{conversion.get('fixture_note')}")
        if row.get("alternatives"):
            lines.append(f"- 同 case 其它 dump（未采用）：{row.get('alternatives')}")
        fixed_refs = conversion.get("fixed_refs") or []
        lines.append(
            f"- 对象：器件 {conversion.get('components_kept')}/{conversion.get('components_total')} 保留"
            f"（丢弃 {conversion.get('components_dropped')}），pads {conversion.get('pads_used')}/"
            f"{conversion.get('pads_total')} 使用（合并 {conversion.get('pads_merged')}），"
            f"nets {conversion.get('nets_kept')}/{conversion.get('nets_total')} 保留"
            f"（丢弃 {conversion.get('nets_dropped')}）"
        )
        lines.append(
            f"- 固定件（J/SW 前缀）：{fixed_refs or '（无，全部可动）'}；"
            f"可动 {len(conversion.get('movable_refs') or [])} 个；"
            f"类型 {conversion.get('components_type_counts')}；网类 {conversion.get('net_class_counts')}；"
            f"密度 {_fmt(conversion.get('component_density'))}"
        )
        drops = conversion.get("dropped_components") or []
        if drops:
            lines.append("- 丢弃器件：")
            for item in drops:
                lines.append(f"  - `{item.get('ref')}`：{item.get('reason')}")
        dropped_nets = conversion.get("dropped_nets") or []
        if dropped_nets:
            lines.append("- 丢弃网络：" + "，".join(
                f"`{item.get('name')}`({item.get('reason')})" for item in dropped_nets
            ))
        expansion = conversion.get("board_expansion_mm") or {}
        lines.append(
            f"- 板框：{_fmt(outline.get('board_mm', [None, None])[0], 2)} × "
            f"{_fmt(outline.get('board_mm', [None, None])[1], 2)} mm"
            f"（{outline.get('format')}，{outline.get('points')} 点；放置模型={outline.get('approximation')}）"
        )
        if (expansion.get("total_mm") or 0.0) > 0.0:
            lines.append(
                f"- 边缘外扩：left={expansion.get('left')} right={expansion.get('right')} "
                f"bottom={expansion.get('bottom')} top={expansion.get('top')} mm"
                f"（用于保留越界连接器；edge-overhang={conversion.get('edge_overhang_components')}）"
            )
        lines.append(
            f"- 多边形（ray casting）：{polygon.get('points')} 点，closed={polygon.get('closed')}，"
            f"面积 {_fmt(polygon.get('area_mm2'), 2)} mm² / bbox "
            f"{_fmt(polygon.get('bbox_area_mm2'), 2)} mm²（比值 {_fmt(polygon.get('area_ratio'), 4)}）；"
            f"polygon_ok={conversion.get('polygon_ok')}；violations={polygon.get('violations')}"
        )
        outside = polygon.get("components_outside") or []
        if outside:
            lines.append("- 多边形外器件（bbox 角点）：" + "，".join(
                f"`{item.get('ref')}`(corners={item.get('corners_outside')}, "
                f"max_outside={item.get('max_outside_mm')}mm, allowed={item.get('allowed')})"
                for item in outside
            ))
        else:
            lines.append("- 多边形外器件：无")
        lines.append(
            f"- keepouts：**{keepouts.get('status')}**"
            + (f"（{keepouts.get('count')} 个，源 `{keepouts.get('source')}`）" if keepouts.get("status") == "APPLIED" else f"（{keepouts.get('reason')}）")
        )
        if keepouts.get("geometry"):
            for item in keepouts.get("geometry") or []:
                lines.append(
                    f"  - #{item.get('index')} {item.get('id')} rect={item.get('rect_mm')} mm"
                    + (f" radius={item.get('radius_mm')} mm" if item.get("radius_mm") else "")
                )
        if keepouts.get("conflicts_with_original"):
            lines.append(f"  - 原布局与 keepout 冲突：{keepouts.get('conflicts_with_original')}")
        lines.append(
            f"- 单位验证：mil × {MIL_TO_MM} → mm；passive bbox 长边 "
            f"{units.get('passive_bbox_long_side_mm')}；closest-to-0402 = "
            f"{units.get('closest_to_0402_mil')} mil；可信={units.get('mil_interpretation_plausible')}，"
            f"mm 解释被否={units.get('mm_interpretation_rejected')}"
        )
        if conversion.get("original_violations"):
            lines.append(f"- 原布局硬约束违反：{conversion.get('original_violations')}")
        overlaps = conversion.get("original_capture_overlaps") or []
        if overlaps:
            lines.append(
                f"- 拍摄 bbox 近似重叠（courtyard artifact，<= {CAPTURE_OVERLAP_TOL_MM2} mm²）："
                + "，".join(
                    f"{item.get('pair')} {item.get('area_mm2')} mm²" for item in overlaps
                )
                + f"；original_feasible_tolerant={conversion.get('original_feasible_tolerant')}"
            )
        lines.append("")
        lines.append("| 组 | 硬可行 | truth_v1 | truth_v2 | router completion | vias | wirelength mm | failed_nets |")
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.append(_metrics_row("original", row.get("original") or {}))
        lines.append(_metrics_row("optimized (solver_v2+route_aware)", row.get("optimized") or {}))
        lines.append(_metrics_row("repair (route_opt)", row.get("repair") or {}))
        deltas = row.get("deltas") or {}
        lines.append(
            f"\n- Δ vs original：optimized truth_v2 {_fmt_delta(deltas.get('optimized_truth_v2'))}，"
            f"completion {_fmt_delta(deltas.get('optimized_completion'))}；"
            f"repair truth_v2 {_fmt_delta(deltas.get('repair_truth_v2'))}，"
            f"completion {_fmt_delta(deltas.get('repair_completion'))}"
        )
        objective = row.get("objective") or {}
        if objective:
            lines.append(
                f"- tuned objective：w_route={objective.get('w_route')} profile={objective.get('profile')} "
                f"source={objective.get('source')}（{objective.get('reason')}）"
            )
        solver_stats = row.get("solver_stats") or {}
        repair_stats = row.get("repair_stats") or {}
        if solver_stats:
            lines.append(
                f"- solver：{solver_stats.get('solver')} steps={solver_stats.get('steps')} "
                f"restarts={solver_stats.get('restarts')} accepted={solver_stats.get('accepted')}"
            )
        if repair_stats:
            lines.append(
                f"- repair：route_calls={repair_stats.get('routes_calls')} "
                f"moves_accepted={repair_stats.get('moves_accepted')} "
                f"completion {repair_stats.get('initial_completion')}→{repair_stats.get('final_completion')}"
            )
        lines.append("")

    lines.append("## 边界与限制\n")
    for item in report.get("limits") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("> 本报告由 `python -m mp_place.realboard`（v2）自动生成；源 dump 只读、未施加布局、未运行 DRC/EDA。")
    return "\n".join(lines) + "\n"


def write_reports_v2(
    report: Dict[str, Any],
    out_dir: Optional[object] = None,
) -> Dict[str, pathlib.Path]:
    """Write ``report_realboard_v2.md`` + ``.json``; return the paths."""
    target_dir = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / REPORT_JSON_V2
    md_path = target_dir / REPORT_MD_V2
    json_path.write_text(
        json.dumps(_json_safe(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_v2(report), encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


# --------------------------------------------------------------------------- #
# v3: mechanical constraints + board-level suite
# --------------------------------------------------------------------------- #
#: Keys removed by :func:`strip_volatile_report` for determinism assertions.
_VOLATILE_KEYS = frozenset(
    {
        "runtime_s",
        "elapsed_s",
        "timings_s",
        "solve_elapsed_s",
        "repair_stage_s",
        "eval_elapsed_s",
        "generated_at",
        "total_runtime_s",
    }
)


def strip_volatile_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy of a report without wall-clock / generation fields.

    Used by the determinism test: the comparison itself (conversion, solver,
    router, truth) is deterministic, only wall-clock fields are not.
    """

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): clean(item)
                for key, item in value.items()
                if key not in _VOLATILE_KEYS
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(_json_safe(report))


def _board_suite_row(row: Dict[str, Any]) -> Dict[str, Any]:
    original = row.get("original") or {}
    optimized = row.get("optimized") or {}
    repair = row.get("repair") or {}
    conversion = _conversion_of(row)

    def completion(metrics: Dict[str, Any]) -> Optional[float]:
        return _metrics_value(metrics, ("router", "completion"))

    def truth(metrics: Dict[str, Any]) -> Optional[float]:
        return _metrics_value(metrics, ("truth_v2",))

    orig_c, opt_c, rep_c = completion(original), completion(optimized), completion(repair)
    orig_t, opt_t, rep_t = truth(original), truth(optimized), truth(repair)
    reduction = None
    if orig_t is not None and rep_t is not None and orig_t > 0:
        reduction = round(100.0 * (orig_t - rep_t) / orig_t, 2)
    reduction_opt = None
    if orig_t is not None and opt_t is not None and orig_t > 0:
        reduction_opt = round(100.0 * (orig_t - opt_t) / orig_t, 2)
    return {
        "name": row.get("name"),
        "case": row.get("case"),
        "completion_original": orig_c,
        "completion_optimized": opt_c,
        "completion_repair": rep_c,
        "truth_v2_original": orig_t,
        "truth_v2_optimized": opt_t,
        "truth_v2_repair": rep_t,
        "completion_gain_optimized": _delta(opt_c, orig_c),
        "completion_gain_repair": _delta(rep_c, orig_c),
        "truth_gain_optimized": _delta(orig_t, opt_t),
        "truth_gain_repair": _delta(orig_t, rep_t),
        "truth_reduction_pct_optimized": reduction_opt,
        "truth_reduction_pct_repair": reduction,
        "feasible_original": bool(original.get("feasible")),
        "feasible_original_tolerant": bool(original.get("feasible_tolerant")),
        "feasible_optimized": bool(optimized.get("feasible")),
        "feasible_repair": bool(repair.get("feasible")),
        "mechanical_fixed_count": len(conversion.get("mechanical_fixed") or []),
        "original_conflicts_count": int(conversion.get("original_conflicts_count") or 0),
    }


def _suite_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Board-level suite: means plus best/worst board under a documented ranking."""
    per_board = [_board_suite_row(row) for row in rows]
    if not per_board:
        return {
            "n_boards": 0,
            "mean_completion": {"original": None, "optimized": None, "repair": None},
            "mean_truth_v2": {"original": None, "optimized": None, "repair": None},
            "mean_completion_gain": {"optimized": None, "repair": None},
            "mean_truth_reduction_pct": {"optimized": None, "repair": None},
            "all_feasible": {
                "original": None,
                "original_tolerant": None,
                "optimized": None,
                "repair": None,
            },
            "best_board": None,
            "worst_board": None,
            "ranking": "",
            "boards": [],
        }

    def mean(key: str) -> Optional[float]:
        values = [item[key] for item in per_board if item.get(key) is not None]
        return _round(sum(values) / len(values)) if values else None

    def as_float(item: Dict[str, Any], key: str, default: float) -> float:
        value = _finite(item.get(key))
        return default if value is None else value

    def rank_key(item: Dict[str, Any]):
        return (
            as_float(item, "completion_gain_repair", -1.0),
            as_float(item, "truth_gain_repair", -1e9),
        )

    ordered = sorted(per_board, key=rank_key)
    return {
        "n_boards": len(per_board),
        "mean_completion": {
            "original": mean("completion_original"),
            "optimized": mean("completion_optimized"),
            "repair": mean("completion_repair"),
        },
        "mean_truth_v2": {
            "original": mean("truth_v2_original"),
            "optimized": mean("truth_v2_optimized"),
            "repair": mean("truth_v2_repair"),
        },
        "mean_completion_gain": {
            "optimized": mean("completion_gain_optimized"),
            "repair": mean("completion_gain_repair"),
        },
        "mean_truth_reduction_pct": {
            "optimized": mean("truth_reduction_pct_optimized"),
            "repair": mean("truth_reduction_pct_repair"),
        },
        "all_feasible": {
            "original": all(item.get("feasible_original") for item in per_board),
            "original_tolerant": all(
                item.get("feasible_original_tolerant") for item in per_board
            ),
            "optimized": all(item.get("feasible_optimized") for item in per_board),
            "repair": all(item.get("feasible_repair") for item in per_board),
        },
        "best_board": ordered[-1],
        "worst_board": ordered[0],
        "ranking": (
            "repair completion gain first, then repair truth_v2 gain "
            "(higher is better); best=max, worst=min"
        ),
        "boards": per_board,
    }


def _aggregate_v3(
    rows: Sequence[Dict[str, Any]],
    skipped: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """v3 aggregate: v2 metrics plus mechanical/conflict counters."""
    aggregate = _aggregate_v2(rows, skipped)
    conversions = [_conversion_of(row) for row in rows]
    aggregate.update(
        {
            "n_mechanical_fixed": sum(
                len(conversion.get("mechanical_fixed") or []) for conversion in conversions
            ),
            "n_original_conflicts": sum(
                int(conversion.get("original_conflicts_count") or 0)
                for conversion in conversions
            ),
            "all_original_conflicts_tolerated": all(
                bool(conversion.get("original_conflicts_tolerated"))
                for conversion in conversions
            )
            if rows
            else None,
            "mechanical_policy": "J/SW/ANT prefixes pinned to their captured position",
            "original_conflict_policy": (
                "captured-layout conflicts are listed with a tolerated flag and are never fatal"
            ),
        }
    )
    return aggregate


def run_all_v3(
    sources: Optional[Sequence[object]] = None,
    *,
    cases_root: Optional[object] = None,
    steps: int = DEFAULT_STEPS_V3,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
) -> Dict[str, Any]:
    """Full-case board suite: discover every dump, compare, and summarise.

    Unlike v2, this variant records the complete case -> dump selection
    (ranked candidates + selection reason), skips cases/dumps that cannot be
    converted with a reason instead of aborting, pins mechanical parts
    (J/SW/ANT), lists every captured-layout conflict, and adds a board-level
    suite summary (means + best/worst board).  Returns the
    ``mp_place.realboard/v3`` report.
    """
    started_wall = datetime.datetime.now().astimezone()
    t_start = time.perf_counter()
    board_sources: List[BoardSource] = []
    skipped: List[Dict[str, Any]] = []
    case_reports: List[Dict[str, Any]] = []
    root: Optional[pathlib.Path] = None
    if sources:
        for item in sources:
            if isinstance(item, BoardSource):
                board_sources.append(item)
            else:
                try:
                    name, path = item  # type: ignore[misc]
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"sources entries must be BoardSource or (name, path), got {item!r}"
                    ) from exc
                target = pathlib.Path(path)
                board_sources.append(
                    BoardSource(name=str(name), case=target.parent.name, path=target)
                )
        case_reports = [
            {
                "case": source.case,
                "status": "BOARD",
                "name": source.name,
                "chosen": str(source.path),
                "candidates": list(source.candidates),
                "json_files": None,
                "reason": None,
            }
            for source in board_sources
        ]
        discovery_mode = "explicit_sources"
    else:
        root = pathlib.Path(cases_root) if cases_root is not None else DEFAULT_CASES_ROOT
        board_sources, skipped, case_reports = discover_cases(root, detailed=True)
        discovery_mode = "auto_discovery"

    rows: List[Dict[str, Any]] = []
    for source in board_sources:
        if not source.path.exists():
            skipped.append(
                {
                    "case": source.case,
                    "name": source.name,
                    "source": str(source.path),
                    "reason": f"dump missing: {source.path}",
                }
            )
            continue
        try:
            converted = load_and_convert(source.path, name=source.name)
        except (OSError, ValueError, KeyError) as exc:
            skipped.append(
                {
                    "case": source.case,
                    "name": source.name,
                    "source": str(source.path),
                    "reason": f"conversion failed: {type(exc).__name__}: {exc}",
                }
            )
            continue
        row = run_board(
            converted,
            steps=steps,
            seed=seed,
            max_routes=max_routes,
            optimise=optimise,
        )
        row["case"] = source.case
        row["alternatives"] = list(source.alternatives)
        row["candidates"] = list(source.candidates)
        row["selection_reason"] = source.selection_reason
        row["mechanical_fixed"] = list(converted.report.get("mechanical_fixed") or [])
        row["original_conflicts"] = list(converted.report.get("original_conflicts") or [])
        rows.append(row)

    suite = _suite_summary(rows)
    aggregate = _aggregate_v3(rows, skipped)
    n_cases = len(case_reports) if case_reports else len(board_sources) + len(skipped)
    return {
        "schema": REALBOARD_SCHEMA_V3,
        "generated_at": started_wall.strftime("%Y-%m-%d %H:%M:%S %z"),
        "runtime_s": round(time.perf_counter() - t_start, 2),
        "config": {
            "steps": int(steps),
            "seed": int(seed),
            "max_routes": int(max_routes),
            "optimise": bool(optimise),
            "solver": "solver_v2.solve",
            "objective": "route_cost.tuned_objective (adaptive RouteAwareObjective over ProxyObjective)",
            "repair": "route_opt.repair_routes",
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
            "truth": "physics_v2.PhysicsSimulatorV2 (seed) + v1 PhysicsSimulator",
            "unit_scale_mm_per_mil": MIL_TO_MM,
            "edge_overhang_limit_mm": EDGE_OVERHANG_MM,
            "capture_overlap_tolerance_mm2": CAPTURE_OVERLAP_TOL_MM2,
            "mechanical_prefixes": list(MECHANICAL_PREFIXES),
            "mechanical_roles": {prefix: role for prefix, role in MECHANICAL_ROLES},
            "keepout_plan_candidates": list(KEEPOUT_PLAN_CANDIDATES),
        },
        "discovery": {
            "mode": discovery_mode,
            "cases_root": str(root) if root is not None else None,
            "n_cases": n_cases,
            "n_boards": len(rows),
            "n_skipped": len(skipped),
            "selection_rules": {
                "dump_like": "JSON object with a non-empty 'components' list and an 'outline' object",
                "preference": [
                    "pcb-dump-final",
                    "pcb-board-final",
                    "board-baseline",
                    "other baselines/finals",
                    "other dumps",
                ],
                "per_case": "exactly one preferred dump; the rest are alternatives",
            },
            "case_reports": case_reports,
            "boards": [
                {
                    "name": row.get("name"),
                    "case": row.get("case"),
                    "source": row.get("source"),
                    "source_sha256": row.get("source_sha256"),
                    "alternatives": row.get("alternatives"),
                    "candidates": row.get("candidates"),
                    "selection_reason": row.get("selection_reason"),
                }
                for row in rows
            ],
            "skipped_cases": list(skipped),
        },
        "boards": rows,
        "skipped_cases": list(skipped),
        "suite": suite,
        "aggregate": aggregate,
        "limits": list(LIMITS),
    }


def render_markdown_v3(report: Dict[str, Any]) -> str:
    """Render the P4.7 real-board suite report (mechanical + multi-board suite)."""
    config = report.get("config") or {}
    discovery = report.get("discovery") or {}
    boards = report.get("boards") or []
    suite = report.get("suite") or {}
    skipped = report.get("skipped_cases") or []
    aggregate = report.get("aggregate") or {}
    lines: List[str] = []
    lines.append("# P4.7 真实板 suite v3（全案例 + 机械约束 + 板级基准）\n")
    lines.append(f"- schema：`{report.get('schema')}`")
    lines.append(
        f"- 配置：steps={config.get('steps')}，seed={config.get('seed')}，max_routes={config.get('max_routes')}；"
        f"机械固定前缀 {config.get('mechanical_prefixes')}；"
        f"solver=`{config.get('solver')}`，objective=`{config.get('objective')}`，router=`{config.get('router')}`"
    )
    lines.append(
        f"- 发现：{discovery.get('mode')}，cases root=`{discovery.get('cases_root')}`；"
        f"case {discovery.get('n_cases')} 个 → 板 {discovery.get('n_boards')}，跳过 {discovery.get('n_skipped')}"
    )
    lines.append(f"- 运行耗时：{report.get('runtime_s')} s\n")

    lines.append("## case → dump 选择\n")
    lines.append("| case | 状态 | 选中 dump | 候选（rank/选中） | json 文件数 | 原因 |")
    lines.append("|---|---|---|---|---|---|")
    for record in discovery.get("case_reports") or []:
        candidates = record.get("candidates") or []
        candidate_text = "，".join(
            f"`{item.get('file')}`({item.get('rank_label')}{',selected' if item.get('selected') else ''})"
            for item in candidates
        ) or "—"
        lines.append(
            f"| `{record.get('case')}` | {record.get('status')} | `{record.get('chosen') or '—'}` | "
            f"{candidate_text} | {record.get('json_files')} | {record.get('reason') or '—'} |"
        )
    lines.append("")
    if skipped:
        lines.append("### 跳过的 case/dump\n")
        for item in skipped:
            lines.append(
                f"- `{item.get('case')}`" + (f" `{item.get('name')}`" if item.get("name") else "")
                + f"：{item.get('reason')}"
            )
        lines.append("")

    lines.append("## 真实板 suite 汇总\n")
    mean_completion = suite.get("mean_completion") or {}
    mean_truth = suite.get("mean_truth_v2") or {}
    mean_gain = suite.get("mean_completion_gain") or {}
    mean_red = suite.get("mean_truth_reduction_pct") or {}
    feasible = suite.get("all_feasible") or {}
    lines.append("| 指标 | original | optimized (route_aware) | repair (+repair) |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| mean completion | {_fmt(mean_completion.get('original'))} | "
        f"{_fmt(mean_completion.get('optimized'))} | {_fmt(mean_completion.get('repair'))} |"
    )
    lines.append(
        f"| mean truth_v2 | {_fmt(mean_truth.get('original'))} | "
        f"{_fmt(mean_truth.get('optimized'))} | {_fmt(mean_truth.get('repair'))} |"
    )
    lines.append(
        f"| completion 增益 | — | {_fmt_delta(mean_gain.get('optimized'))} | {_fmt_delta(mean_gain.get('repair'))} |"
    )
    lines.append(
        f"| truth_v2 降幅 | — | {_fmt(mean_red.get('optimized'), 2)}% | {_fmt(mean_red.get('repair'), 2)}% |"
    )
    lines.append(
        f"| 全部硬可行 | {feasible.get('original')}（tolerant {feasible.get('original_tolerant')}） | "
        f"{feasible.get('optimized')} | {feasible.get('repair')} |"
    )
    lines.append(f"\n- 排名规则：{suite.get('ranking') or '—'}\n")

    lines.append("### 最好板 / 最差板\n")
    lines.append("| 排名 | 板 | case | completion 原→repair | truth_v2 原→repair | repair completion 增益 | repair truth 增益 |")
    lines.append("|---|---|---|---|---|---|---|")
    for label, item in (("best", suite.get("best_board")), ("worst", suite.get("worst_board"))):
        if not item:
            continue
        lines.append(
            f"| {label} | {item.get('name')} | `{item.get('case')}` | "
            f"{_fmt(item.get('completion_original'))}→{_fmt(item.get('completion_repair'))} | "
            f"{_fmt(item.get('truth_v2_original'))}→{_fmt(item.get('truth_v2_repair'))} | "
            f"{_fmt_delta(item.get('completion_gain_repair'))} | "
            f"{_fmt(item.get('truth_reduction_pct_repair'), 2)}% |"
        )
    lines.append("")

    lines.append("## 板级总表\n")
    lines.append("| 板 | case | sha256 | 器件 | pads | nets | 多边形点 | keepouts | 机械固定 | 原始冲突 | completion 原→opt→rep | truth_v2 原→opt→rep | repair 耗时 s |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for item in suite.get("boards") or []:
        row = next((row for row in boards if row.get("name") == item.get("name")), {})
        conversion = _conversion_of(row)
        keepouts = _keepouts_of(row)
        keepout_label = keepouts.get("status") or "NOT RUN"
        if keepout_label == "APPLIED":
            keepout_label = f"APPLIED×{keepouts.get('count')}"
        lines.append(
            f"| {item.get('name')} | `{item.get('case')}` | `{str(row.get('source_sha256') or '')[:12]}` | "
            f"{conversion.get('components_kept')}/{conversion.get('components_total')} | "
            f"{conversion.get('pads_used')} | {conversion.get('nets_kept')}/{conversion.get('nets_total')} | "
            f"{(conversion.get('polygon') or {}).get('points')} | {keepout_label} | "
            f"{item.get('mechanical_fixed_count')} | {item.get('original_conflicts_count')} | "
            f"{_fmt(item.get('completion_original'))}→{_fmt(item.get('completion_optimized'))}→{_fmt(item.get('completion_repair'))} | "
            f"{_fmt(item.get('truth_v2_original'))}→{_fmt(item.get('truth_v2_optimized'))}→{_fmt(item.get('truth_v2_repair'))} | "
            f"{_fmt((row.get('timings_s') or {}).get('repair'))} |"
        )
    lines.append("")

    for row in boards:
        conversion = _conversion_of(row)
        polygon = _polygon_of(row)
        keepouts = _keepouts_of(row)
        units = conversion.get("units") or {}
        lines.append(f"## {row.get('name')}（case `{row.get('case')}`）\n")
        lines.append(f"- 源：`{row.get('source')}`（{conversion.get('source_bytes')} bytes）")
        lines.append(f"- SHA256：`{row.get('source_sha256')}`")
        lines.append(
            f"- project={conversion.get('project')} capturedAt={conversion.get('captured_at')} "
            f"semanticSha256=`{str(conversion.get('semantic_sha256') or '')[:16]}`"
        )
        if conversion.get("fixture_note"):
            lines.append(f"- fixture note：{conversion.get('fixture_note')}")
        lines.append(f"- dump 选择：{row.get('selection_reason')}；alternatives={row.get('alternatives')}")
        lines.append(
            f"- 对象：器件 {conversion.get('components_kept')}/{conversion.get('components_total')} 保留"
            f"（丢弃 {conversion.get('components_dropped')}），pads {conversion.get('pads_used')}/"
            f"{conversion.get('pads_total')}（合并 {conversion.get('pads_merged')}），"
            f"nets {conversion.get('nets_kept')}/{conversion.get('nets_total')}（丢弃 {conversion.get('nets_dropped')}）"
        )
        mechanical = conversion.get("mechanical_fixed") or []
        lines.append(f"- 机械固定（J/SW/ANT）：{len(mechanical)} 个")
        for item in mechanical:
            lines.append(
                f"  - {item.get('ref')}（{item.get('role')}）：位置 "
                f"({_fmt(item.get('x_mm'), 3)}, {_fmt(item.get('y_mm'), 3)}) mm rot={item.get('rotation')}"
            )
        conflicts = conversion.get("original_conflicts") or []
        lines.append(
            f"- 原布局冲突：{len(conflicts)} 项（tolerated={conversion.get('original_conflicts_tolerated')}，"
            f"如实记录、不判死）"
        )
        for item in conflicts:
            lines.append(
                f"  - [{item.get('kind')}] {item.get('ref') or ''} {item.get('detail')}"
                f" tolerated={item.get('tolerated')}（{item.get('note')}）"
            )
        lines.append(
            f"- 板框：{_fmt((conversion.get('outline') or {}).get('board_mm', [None, None])[0], 2)} × "
            f"{_fmt((conversion.get('outline') or {}).get('board_mm', [None, None])[1], 2)} mm；"
            f"多边形 {polygon.get('points')} 点，polygon_ok={conversion.get('polygon_ok')}，"
            f"violations={polygon.get('violations')}"
        )
        lines.append(
            f"- keepouts：**{keepouts.get('status')}**"
            + (
                f"（{keepouts.get('count')} 个，源 `{keepouts.get('source')}`）"
                if keepouts.get("status") == "APPLIED"
                else f"（{keepouts.get('reason')}）"
            )
        )
        lines.append(
            f"- 单位验证：mil × {MIL_TO_MM} → mm；passive bbox 长边 "
            f"{units.get('passive_bbox_long_side_mm')}；可信={units.get('mil_interpretation_plausible')}，"
            f"mm 解释被否={units.get('mm_interpretation_rejected')}"
        )
        lines.append("")
        lines.append("| 组 | 硬可行 | truth_v1 | truth_v2 | router completion | vias | wirelength mm | failed_nets | 耗时 s |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for label, group in (
            ("original", "original"),
            ("optimized (solver_v2+route_aware)", "optimized"),
            ("repair (route_opt)", "repair"),
        ):
            metrics = row.get(group) or {}
            router = metrics.get("router") or {}
            lines.append(
                f"| {label} | {_fmt(metrics.get('feasible'))} | {_fmt(metrics.get('truth_v1'))} | "
                f"{_fmt(metrics.get('truth_v2'))} | {_fmt(router.get('completion'))} | "
                f"{_fmt(router.get('vias'))} | {_fmt(router.get('wirelength_mm'), 1)} | "
                f"`{router.get('failed_nets')}` | {_fmt(metrics.get('elapsed_s'), 2)} |"
            )
        deltas = row.get("deltas") or {}
        lines.append(
            f"\n- Δ vs original：optimized truth_v2 {_fmt_delta(deltas.get('optimized_truth_v2'))}，"
            f"completion {_fmt_delta(deltas.get('optimized_completion'))}；"
            f"repair truth_v2 {_fmt_delta(deltas.get('repair_truth_v2'))}，"
            f"completion {_fmt_delta(deltas.get('repair_completion'))}"
        )
        objective = row.get("objective") or {}
        if objective:
            lines.append(
                f"- tuned objective：w_route={objective.get('w_route')} profile={objective.get('profile')} "
                f"source={objective.get('source')}（{objective.get('reason')}）"
            )
        solver_stats = row.get("solver_stats") or {}
        repair_stats = row.get("repair_stats") or {}
        if solver_stats:
            lines.append(
                f"- solver：{solver_stats.get('solver')} steps={solver_stats.get('steps')} "
                f"restarts={solver_stats.get('restarts')} accepted={solver_stats.get('accepted')}"
            )
        if repair_stats:
            lines.append(
                f"- repair：route_calls={repair_stats.get('routes_calls')} "
                f"moves_accepted={repair_stats.get('moves_accepted')} "
                f"completion {repair_stats.get('initial_completion')}→{repair_stats.get('final_completion')}"
            )
        lines.append("")

    lines.append("## 边界与限制\n")
    for item in report.get("limits") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("> 本报告由 `python -m mp_place.realboard`（v3）自动生成；源 dump 只读、未施加布局、未运行 DRC/EDA。")
    return "\n".join(lines) + "\n"


def write_reports_v3(
    report: Dict[str, Any],
    out_dir: Optional[object] = None,
) -> Dict[str, pathlib.Path]:
    """Write ``report_realboard_v3.md`` + ``.json``; return the paths."""
    target_dir = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / REPORT_JSON_V3
    md_path = target_dir / REPORT_MD_V3
    json_path.write_text(
        json.dumps(_json_safe(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_v3(report), encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mp_place.realboard",
        description=(
            "Convert real EasyCirq PCB dumps to Scenarios and compare original vs optimised vs "
            "repaired layouts (v3: full-case suite + mechanical constraints + polygon/keepout)."
        ),
    )
    parser.add_argument("--steps", type=int, default=None, help=f"solver move budget (v2/v3 default: {DEFAULT_STEPS_V3}; v1 default: {DEFAULT_STEPS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="solver/truth seed (default: 0)")
    parser.add_argument("--max-routes", type=int, default=DEFAULT_MAX_ROUTES, help=f"route_opt router-call budget (default: {DEFAULT_MAX_ROUTES})")
    parser.add_argument(
        "--cases-root",
        default=None,
        help="EasyCirq cases root for auto-discovery (default: resolved read-only case path)",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        metavar="NAME=PATH",
        help="explicit dump NAME=PATH (repeatable; bypasses case discovery)",
    )
    parser.add_argument(
        "--v1",
        action="store_true",
        help="write the legacy v1 report (report_realboard.md/json) instead of the v3 report",
    )
    parser.add_argument(
        "--v2",
        action="store_true",
        help="write the v2 report (report_realboard_v2.md/json) instead of the v3 report",
    )
    parser.add_argument("--out", default=None, help="report output directory (default: project root)")
    parser.add_argument("--json", action="store_true", help="print the compact JSON report on stdout")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.v1 and args.v2:
        parser.error("--v1 and --v2 are mutually exclusive")
    steps = args.steps
    if steps is None:
        if args.v1:
            steps = DEFAULT_STEPS
        elif args.v2:
            steps = DEFAULT_STEPS_V2
        else:
            steps = DEFAULT_STEPS_V3
    if steps < 0:
        parser.error("--steps must be >= 0")
    if args.seed < 0:
        parser.error("--seed must be >= 0")
    if args.max_routes < 1:
        parser.error("--max-routes must be >= 1")
    sources: Optional[List[Tuple[str, pathlib.Path]]] = None
    if args.source:
        sources = []
        for spec in args.source:
            if "=" not in spec:
                parser.error(f"--source expects NAME=PATH, got {spec!r}")
            name, path = spec.split("=", 1)
            if not name.strip() or not path.strip():
                parser.error(f"--source expects non-empty NAME and PATH, got {spec!r}")
            sources.append((name.strip(), pathlib.Path(path.strip())))
    cases_root = pathlib.Path(args.cases_root) if args.cases_root else None
    out_dir = pathlib.Path(args.out) if args.out else PROJECT_ROOT
    try:
        if args.v1:
            report = run_all(
                sources=sources,
                cases_root=cases_root,
                steps=steps,
                seed=args.seed,
                max_routes=args.max_routes,
            )
            paths = write_reports(report, out_dir=out_dir)
        elif args.v2:
            report = run_all_v2(
                sources=sources,
                cases_root=cases_root,
                steps=steps,
                seed=args.seed,
                max_routes=args.max_routes,
            )
            paths = write_reports_v2(report, out_dir=out_dir)
        else:
            report = run_all_v3(
                sources=sources,
                cases_root=cases_root,
                steps=steps,
                seed=args.seed,
                max_routes=args.max_routes,
            )
            paths = write_reports_v3(report, out_dir=out_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    aggregate = report.get("aggregate") or {}
    if args.json:
        print(json.dumps(_json_safe(report), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        if args.v1:
            print(
                f"realboard v1: boards={aggregate.get('n_boards')} "
                f"completion original={aggregate.get('mean_original_completion')} "
                f"optimized={aggregate.get('mean_optimized_completion')} "
                f"repair={aggregate.get('mean_repair_completion')} "
                f"truth_v2 original={aggregate.get('mean_original_truth_v2')} "
                f"optimized={aggregate.get('mean_optimized_truth_v2')} "
                f"repair={aggregate.get('mean_repair_truth_v2')} "
                f"runtime={report.get('runtime_s')}s"
            )
        elif args.v2:
            discovery = report.get("discovery") or {}
            print(
                f"realboard v2: mode={discovery.get('mode')} cases={discovery.get('n_cases')} "
                f"boards={aggregate.get('n_boards')} skipped={aggregate.get('n_skipped_cases')} "
                f"polygon_ok={aggregate.get('n_polygon_ok')}/{aggregate.get('n_boards')} "
                f"keepouts_applied={aggregate.get('n_keepouts_applied')}/{aggregate.get('n_boards')} "
                f"completion original={aggregate.get('mean_original_completion')} "
                f"optimized={aggregate.get('mean_optimized_completion')} "
                f"repair={aggregate.get('mean_repair_completion')} "
                f"truth_v2 original={aggregate.get('mean_original_truth_v2')} "
                f"optimized={aggregate.get('mean_optimized_truth_v2')} "
                f"repair={aggregate.get('mean_repair_truth_v2')} "
                f"runtime={report.get('runtime_s')}s"
            )
        else:
            discovery = report.get("discovery") or {}
            suite = report.get("suite") or {}
            best = suite.get("best_board") or {}
            worst = suite.get("worst_board") or {}
            mean_completion = suite.get("mean_completion") or {}
            mean_truth = suite.get("mean_truth_v2") or {}
            print(
                f"realboard v3: mode={discovery.get('mode')} cases={discovery.get('n_cases')} "
                f"boards={discovery.get('n_boards')} skipped={discovery.get('n_skipped')} "
                f"mechanical_fixed={aggregate.get('n_mechanical_fixed')} "
                f"original_conflicts={aggregate.get('n_original_conflicts')} "
                f"completion original={mean_completion.get('original')} "
                f"optimized={mean_completion.get('optimized')} "
                f"repair={mean_completion.get('repair')} "
                f"truth_v2 original={mean_truth.get('original')} "
                f"optimized={mean_truth.get('optimized')} "
                f"repair={mean_truth.get('repair')} "
                f"best={best.get('name')} worst={worst.get('name')} "
                f"runtime={report.get('runtime_s')}s"
            )
    print(f"[realboard] wrote {paths['markdown']} / {paths['json']}", file=sys.stderr)
    return 0 if (report.get("boards") or []) else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MIL_TO_MM",
    "REALBOARD_SCHEMA",
    "REALBOARD_SCHEMA_V2",
    "REALBOARD_SCHEMA_V3",
    "DEFAULT_SOURCES",
    "DEFAULT_STEPS",
    "DEFAULT_STEPS_V2",
    "DEFAULT_STEPS_V3",
    "DEFAULT_SEED",
    "DEFAULT_MAX_ROUTES",
    "EDGE_OVERHANG_MM",
    "CAPTURE_OVERLAP_TOL_MM2",
    "FIXED_PREFIXES",
    "MECHANICAL_PREFIXES",
    "MECHANICAL_ROLES",
    "KEEPOUT_PLAN_CANDIDATES",
    "BoardPolygon",
    "BoardSource",
    "ConvertedBoard",
    "sha256_file",
    "verify_units",
    "point_in_polygon",
    "polygon_area",
    "polygon_boundary_distance",
    "convert_dump",
    "load_dump",
    "load_and_convert",
    "find_keepout_plan",
    "discover_cases",
    "evaluate_placement",
    "run_board",
    "run_all",
    "run_all_v2",
    "run_all_v3",
    "strip_volatile_report",
    "render_markdown",
    "render_markdown_v2",
    "render_markdown_v3",
    "write_reports",
    "write_reports_v2",
    "write_reports_v3",
    "main",
]
