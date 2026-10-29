"""P4-F: offline placement verification, certificate and ASCII/SVG rendering.

Scope / safety contract
-----------------------
This module is an **offline geometry + feature proxy**.  It re-uses the P1
hard-constraint checker (``mp_place.model.hard_violations``) and the
10-dimensional multi-physics feature extractor
(``mp_place.features.extract_features``), and optionally runs the offline grid
router (``mp_place.router.GridRouter``) when that module is importable.  It
never applies a placement, never runs DRC, never calls EDA and never touches
the network.  Every result therefore hard-codes the safety fields
``routing_verified: false``, ``drc: "NOT RUN"`` and ``eda_calls: 0``.

Router degradation
------------------
The router is imported lazily.  When ``mp_place.router`` is missing, broken or
raises at run time, ``routability.status`` becomes ``"NOT RUN"`` with a
machine-readable reason and the rest of the verification still completes;
no exception escapes :func:`verify_placement`.

Determinism
-----------
For the same scenario and placement the verification dict, the certificate and
both renderers are byte-for-byte reproducible.  The router's wall-clock
``runtime_s`` is reported by :func:`verify_placement` (it is useful when
diagnosing the oracle) but is deliberately **excluded** from the certificate,
which only contains reproducible values.

Public API
----------
- ``verify_placement(scenario, placement) -> dict``
- ``certificate(scenario, placement, extra=None) -> dict`` (JSON serializable)
- ``render_ascii(scenario, placement, width=60) -> str``
- ``render_svg(scenario, placement) -> str``

Plus the small pure helpers ``placement_digest`` and ``scenario_digest`` which
are also exposed for tests / pipeline reporting.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as _xml_escape

from .features import FEATURE_NAMES, extract_features
from .model import Placement, Scenario, bbox, hard_violations

VERIFY_SCHEMA = "mp_place.verify/v1"
CERTIFICATE_SCHEMA = "mp_place.placement-certificate/v1"

#: Hard-coded safety fields.  These are NEVER computed from scenario data.
FIXED_FIELDS: Dict[str, Any] = {
    "routing_verified": False,
    "drc": "NOT RUN",
    "eda_calls": 0,
}

LIMITS: List[str] = [
    "offline geometry/feature proxy only; not DRC, not a routability proof",
    "routing completion is an offline grid-maze oracle when mp_place.router is available, else NOT RUN",
    "no SPICE/FEA/EMC/thermal simulation and no manufacturing sign-off",
    "the certificate records what the offline judge checked, nothing about a real board",
]

#: Attribute names of ``mp_place.router.RouteResult`` (INTERFACES.md section B).
_ROUTE_FIELDS = ("completion", "failed_nets", "wirelength_mm", "vias",
                 "overflow", "runtime_s")

#: First letter used as the movable-component glyph in the ASCII map.
_KIND_GLYPH = {
    "connector": "J",
    "mcu": "U",
    "power_switch": "P",
    "inductor": "L",
    "decap": "C",
    "input_cap": "C",
    "output_cap": "C",
    "analog": "A",
    "crystal": "Y",
    "antenna": "R",
    "rf": "R",
}


# ---------------------------------------------------------------------------
# small helpers


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_json(payload).encode("utf-8")).hexdigest()


def _as_float(value: Any) -> Optional[float]:
    """Return a finite float or None (booleans are not numbers)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value: Any) -> Optional[int]:
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


def _json_safe(value: Any) -> Any:
    """Recursively convert ``value`` to plain JSON types (non-finite -> None)."""
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
    # Anything else (dataclass, set, custom object) is rendered as text so the
    # certificate stays JSON serializable instead of failing deep in json.dumps.
    return str(value)


def _normalised_placement(pl: Placement) -> List[Tuple[str, float, float, int]]:
    """Sorted deterministic ``(ref, x, y, rot)`` view of a placement."""
    items: List[Tuple[str, float, float, int]] = []
    for ref, value in pl.items():
        try:
            x, y, rot = value
        except (TypeError, ValueError):
            continue
        xf = _as_float(x)
        yf = _as_float(y)
        if xf is None or yf is None:
            continue
        try:
            rotation = int(rot) % 360
        except (TypeError, ValueError):
            continue
        items.append((str(ref), xf, yf, rotation))
    items.sort(key=lambda item: item[0])
    return items


def _placement_payload(pl: Placement) -> Dict[str, List[float]]:
    return {ref: [x, y, float(rot)]
            for ref, x, y, rot in _normalised_placement(pl)}


def placement_digest(pl: Placement, sc: Optional[Scenario] = None) -> str:
    """Deterministic sha256 over a placement (optionally bound to a scenario)."""
    payload: Dict[str, Any] = {"placement": _placement_payload(pl)}
    if sc is not None:
        payload["scenario"] = {"name": sc.name,
                               "board_w": _as_float(sc.board_w),
                               "board_h": _as_float(sc.board_h)}
    return _digest(payload)


def scenario_digest(sc: Scenario) -> str:
    """Deterministic sha256 over the parts of a scenario the judge can see."""
    components = []
    for ref in sorted(sc.components):
        comp = sc.components[ref]
        components.append({
            "ref": ref,
            "kind": comp.kind,
            "w": _as_float(comp.w),
            "h": _as_float(comp.h),
            "fixed": bool(comp.fixed),
            "rotations": [int(rot) % 360 for rot in comp.rotations],
            "power_w": _as_float(comp.power_w),
            "edge": comp.edge,
            "pins": {name: [_as_float(dx), _as_float(dy)]
                     for name, (dx, dy) in sorted(comp.pins.items())},
        })
    nets = []
    for net in sc.nets:
        nets.append({"name": net.name, "cls": net.cls,
                     "pins": [[str(ref), str(pin)] for ref, pin in net.pins]})
    payload = {
        "name": sc.name,
        "board_w": _as_float(sc.board_w),
        "board_h": _as_float(sc.board_h),
        "edge_tol": _as_float(sc.edge_tol),
        "keepouts": [[_as_float(v) for v in ko] for ko in sc.keepouts],
        "components": components,
        "nets": nets,
    }
    return _digest(payload)


# ---------------------------------------------------------------------------
# router integration (lazy, always graceful)


def _load_router():
    """Return ``(GridRouter class or None, reason or None)``.

    Imported lazily so this module works while ``mp_place.router`` is still
    being developed in parallel.  Tests patch this function to exercise both
    the available and the unavailable branch deterministically.
    """
    try:
        from .router import GridRouter  # noqa: WPS433 (lazy import by design)
    except ImportError:
        return None, "mp_place.router is not available (module missing)"
    except Exception as exc:  # pragma: no cover - only for a broken module
        return None, "mp_place.router import failed: %s: %s" % (
            type(exc).__name__, exc)
    return GridRouter, None


def _route_field(result: Any, name: str) -> Any:
    if isinstance(result, dict):
        return result.get(name)
    return getattr(result, name, None)


def _routability(sc: Scenario, pl: Placement) -> Dict[str, Any]:
    """Run the offline grid router when available; always return evidence."""
    report: Dict[str, Any] = {
        "status": "NOT RUN",
        "source": "mp_place.router",
        "completion": None,
        "failed_nets": [],
        "wirelength_mm": None,
        "vias": None,
        "overflow": None,
        "runtime_s": None,
        "reason": "router not available",
    }
    router_cls, reason = _load_router()
    if router_cls is None:
        report["reason"] = reason or "router not available"
        return report
    report["source"] = "mp_place.router.GridRouter"
    try:
        router = router_cls(sc)
        result = router.route(pl)
    except Exception as exc:
        report["reason"] = "router failed: %s: %s" % (type(exc).__name__, exc)
        return report

    completion = _as_float(_route_field(result, "completion"))
    failed_nets_raw = _route_field(result, "failed_nets") or []
    try:
        failed_nets = sorted(str(name) for name in failed_nets_raw)
    except TypeError:
        failed_nets = []
    report.update({
        "completion": completion,
        "failed_nets": failed_nets,
        "wirelength_mm": _as_float(_route_field(result, "wirelength_mm")),
        "vias": _as_int(_route_field(result, "vias")),
        "overflow": _as_int(_route_field(result, "overflow")),
        "runtime_s": _as_float(_route_field(result, "runtime_s")),
    })
    if completion is None:
        report["status"] = "NOT RUN"
        report["reason"] = "router returned no usable completion value"
    else:
        report["status"] = "ROUTED"
        report["reason"] = "ok"
    return report


# ---------------------------------------------------------------------------
# verification


def _evidence(sc: Scenario, violations: List[str],
              features: Optional[Dict[str, float]], feature_note: str,
              routability: Dict[str, Any]) -> Dict[str, Any]:
    """Provenance for every numeric / boolean value in the result."""
    return {
        "feasible": {
            "source": "derived",
            "rule": "feasible = (len(violations) == 0)",
        },
        "violations": {
            "source": "mp_place.model.hard_violations",
            "checked": [
                "missing_placement", "rotation_not_allowed", "out_of_board",
                "fixed_moved", "connector_off_edge", "body_overlap",
                "keepout_violation",
            ],
            "result_count": len(violations),
            "numeric_sources": {
                "result_count": "len(mp_place.model.hard_violations(sc, pl))",
            },
        },
        "features": {
            "source": "mp_place.features.extract_features",
            "feature_names": list(FEATURE_NAMES),
            "status": "computed" if features is not None else "skipped",
            "reason": feature_note,
            "numeric_sources": {
                "hpwl": "sum of net bounding-box half-perimeters / board diagonal / len(nets)",
                "decap": "mean cap-to-connected-pin pad distance / board diagonal",
                "loop": "mean max pin-pair span on power nets / board diagonal",
                "analog": "min analog-to-power pad distance / board diagonal",
                "thermal": "switch power_w / (copper bbox area within 8 mm + 10)",
                "density": "sum component bbox area / board area",
                "congestion": "max components per 2 mm cell / component count",
                "escape": "1 - min MCU distance to a board edge / board diagonal",
                "keepout": "component bbox area inside keepouts / board area",
                "capcount": "1 / number of decoupling capacitors",
            },
        },
        "routability": {
            "source": routability["source"],
            "status": routability["status"],
            "reason": routability["reason"],
            "numeric_sources": {
                "completion": "fraction of critical nets completed by the offline GridRouter",
                "wirelength_mm": "router total wire length",
                "vias": "router layer-change count",
                "overflow": "router grid overflow count",
                "runtime_s": "router wall-clock time (excluded from certificates)",
            },
        },
        "fixed_fields": {
            "source": "hard-coded safety fields; never computed from scenario data",
            "values": dict(FIXED_FIELDS),
        },
    }


def verify_placement(sc: Scenario, pl: Placement) -> Dict[str, Any]:
    """Judge one placement offline.

    Returns a plain-dict report with:

    * ``feasible`` / ``violations`` -- P1 hard constraints;
    * ``features`` -- the 10-dimensional proxy (``None`` when the placement is
      incomplete, because a feature cannot be invented for a missing part);
    * ``routability`` -- offline grid-router completion or ``NOT RUN``;
    * ``fixed_fields`` -- hard-coded ``placement_applied:false``,
      ``routing_verified:false``, ``drc:"NOT RUN"``, ``eda_calls:0``;
    * ``evidence`` -- where every value came from.
    """
    violations = list(hard_violations(sc, pl))
    missing = [ref for ref in sorted(sc.components) if ref not in pl]

    features: Optional[Dict[str, float]] = None
    feature_note = "placement covers every component"
    if missing:
        feature_note = ("skipped: placement is missing %d component(s): %s"
                        % (len(missing), ",".join(missing)))
    else:
        try:
            extracted = extract_features(sc, pl)
            features = {name: _as_float(extracted.get(name))
                        for name in FEATURE_NAMES}
            if any(value is None for value in features.values()):
                feature_note = "computed (some values were non-finite and " \
                               "are reported as null)"
        except Exception as exc:  # never crash the judge on a bad placement
            feature_note = "skipped: extract_features failed: %s: %s" % (
                type(exc).__name__, exc)

    routability = _routability(sc, pl)
    feasible = not violations

    report: Dict[str, Any] = {
        "schema": VERIFY_SCHEMA,
        "scenario": {
            "name": sc.name,
            "board_w": _as_float(sc.board_w),
            "board_h": _as_float(sc.board_h),
            "components": len(sc.components),
            "nets": len(sc.nets),
            "keepouts": len(sc.keepouts),
            "edge_tol": _as_float(sc.edge_tol),
        },
        "placement_digest": placement_digest(pl, sc),
        "feasible": feasible,
        "violations": violations,
        "missing_components": missing,
        "features": features,
        "routability": routability,
        "fixed_fields": dict(FIXED_FIELDS),
        "evidence": _evidence(sc, violations, features, feature_note,
                              routability),
        "limits": list(LIMITS),
    }
    return report


# ---------------------------------------------------------------------------
# certificate


def certificate(sc: Scenario, pl: Placement, extra: Any = None) -> Dict[str, Any]:
    """Return a deterministic, JSON-serializable placement certificate.

    The certificate carries the verdict, hard violations, features, router
    status, provenance and the hard-coded safety fields.  The router's
    wall-clock ``runtime_s`` is intentionally omitted so that two certificates
    for the same input are identical.  ``extra`` (e.g. solver statistics) is
    attached under ``"extra"`` and sanitized to plain JSON types.
    """
    report = verify_placement(sc, pl)
    routability = report["routability"]
    deterministic_route = {
        key: routability.get(key)
        for key in ("status", "source", "completion", "failed_nets",
                    "wirelength_mm", "vias", "overflow", "reason")
    }
    cert: Dict[str, Any] = {
        "schema": CERTIFICATE_SCHEMA,
        "scenario": {
            "name": sc.name,
            "board_w": _as_float(sc.board_w),
            "board_h": _as_float(sc.board_h),
            "components": len(sc.components),
            "nets": len(sc.nets),
            "keepouts": len(sc.keepouts),
            "edge_tol": _as_float(sc.edge_tol),
            "digest": scenario_digest(sc),
        },
        "placement": _placement_payload(pl),
        "placement_digest": placement_digest(pl, sc),
        "verdict": "feasible" if report["feasible"] else "infeasible",
        "feasible": report["feasible"],
        "violations": list(report["violations"]),
        "missing_components": list(report["missing_components"]),
        "features": report["features"],
        "routability": deterministic_route,
        "fixed_fields": dict(FIXED_FIELDS),
        "evidence": report["evidence"],
        "limits": list(LIMITS),
        "extra": _json_safe(extra) if extra is not None else None,
    }
    return _json_safe(cert)


# ---------------------------------------------------------------------------
# ASCII rendering


def _ascii_safe(text: Any) -> str:
    return "".join(char if 32 <= ord(char) < 127 else "?" for char in str(text))


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _grid_dimensions(sc: Scenario, width: int) -> Tuple[int, int]:
    try:
        inner_w = int(width)
    except (TypeError, ValueError):
        inner_w = 60
    inner_w = _clamp(inner_w, 24, 200)
    board_w = _as_float(sc.board_w) or 1.0
    board_h = _as_float(sc.board_h) or 1.0
    if board_w <= 0:
        board_w = 1.0
    if board_h <= 0:
        board_h = 1.0
    # A monospace character cell is roughly twice as tall as wide.
    inner_h = int(round(inner_w * (board_h / board_w) * 0.5))
    inner_h = _clamp(inner_h, 8, 80)
    return inner_w, inner_h


def _wrap_text(text: str, width: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return [line[:width] for line in lines]


class _AsciiCanvas:
    def __init__(self, sc: Scenario, width: int):
        self.sc = sc
        self.inner_w, self.inner_h = _grid_dimensions(sc, width)
        self.board_w = _as_float(sc.board_w) or 1.0
        self.board_h = _as_float(sc.board_h) or 1.0
        if self.board_w <= 0:
            self.board_w = 1.0
        if self.board_h <= 0:
            self.board_h = 1.0
        self.rows = [["." for _ in range(self.inner_w)]
                     for _ in range(self.inner_h)]

    def col(self, x: float) -> int:
        return _clamp(int(float(x) / self.board_w * self.inner_w),
                      0, self.inner_w - 1)

    def row(self, y: float) -> int:
        return _clamp(self.inner_h - 1 - int(float(y) / self.board_h
                                             * self.inner_h),
                      0, self.inner_h - 1)

    def fill_rect(self, rect, char: str) -> None:
        x0, y0, x1, y1 = rect
        c0, c1 = sorted((self.col(x0), self.col(x1)))
        r0, r1 = sorted((self.row(y1), self.row(y0)))
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                self.rows[row][col] = char

    def write(self, row: int, col: int, text: str) -> None:
        if not text:
            return
        col = _clamp(col, 0, max(0, self.inner_w - len(text)))
        for offset, char in enumerate(text[:self.inner_w]):
            if col + offset >= self.inner_w:
                break
            self.rows[row][col + offset] = char

    def text_lines(self) -> List[str]:
        return ["|" + "".join(row) + "|" for row in self.rows]


def render_ascii(sc: Scenario, pl: Placement, width: int = 60) -> str:
    """Render the board, components and keepouts as a stable ASCII map.

    The returned block uses a fixed outer width (``inner_w + 2`` characters)
    for every line: a frame, header lines, the board map, and a footer legend
    with the abbreviated component references, fixed parts and any missing
    placement.  Pure standard library, no terminal size or time dependence.
    """
    canvas = _AsciiCanvas(sc, width)
    for keepout in sc.keepouts:
        canvas.fill_rect(tuple(float(v) for v in keepout), "~")

    fixed_refs: List[str] = []
    missing: List[str] = []
    placed: List[Tuple[str, Any, float, float, Any]] = []
    for ref in sorted(sc.components):
        comp = sc.components[ref]
        if ref not in pl:
            missing.append(ref)
            continue
        try:
            x, y, rot = pl[ref]
        except (TypeError, ValueError):
            missing.append(ref)
            continue
        xf = _as_float(x)
        yf = _as_float(y)
        if xf is None or yf is None:
            missing.append(ref)
            continue
        box = bbox(comp, xf, yf, int(rot) % 360)
        if comp.fixed:
            fixed_refs.append(ref)
            char = "#"
        else:
            glyph = _KIND_GLYPH.get(comp.kind, (ref[:1].upper() or "?"))
            char = _ascii_safe(glyph)[:1] or "?"
        canvas.fill_rect(box, char)
        placed.append((ref, comp, xf, yf, box))

    # Label larger components with their reference (small parts keep the glyph).
    for ref, comp, xf, yf, box in placed:
        c0 = canvas.col(box[0])
        c1 = canvas.col(box[2])
        cell_width = abs(c1 - c0) + 1
        if comp.fixed or cell_width >= len(ref):
            label = _ascii_safe(ref)
            canvas.write(canvas.row(yf), canvas.col(xf) - len(label) // 2,
                         label)

    header = _ascii_safe(
        "placement map: %s  board %gx%g mm  components=%d  nets=%d  "
        "fixed=%d  missing=%d"
        % (sc.name, float(sc.board_w), float(sc.board_h),
           len(sc.components), len(sc.nets), len(fixed_refs), len(missing)))

    footer: List[str] = [
        "legend: '#' fixed  letter movable-kind  '~' keepout  '.' empty",
        "refs: " + (" ".join(sorted(sc.components)) or "-"),
        "fixed: " + (" ".join(fixed_refs) or "-"),
    ]
    if missing:
        footer.append("missing placement: " + " ".join(missing))
    footer.append("offline map only; routing_verified:false, drc:NOT RUN, "
                  "eda_calls:0")

    inner_w = canvas.inner_w
    frame = "+" + "-" * inner_w + "+"
    out: List[str] = [frame]
    for line in _wrap_text(header, inner_w):
        out.append("|" + _ascii_safe(line).ljust(inner_w) + "|")
    out.append(frame)
    out.extend(canvas.text_lines())
    out.append(frame)
    for entry in footer:
        for line in _wrap_text(_ascii_safe(entry), inner_w):
            out.append("|" + line.ljust(inner_w) + "|")
    out.append(frame)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# SVG rendering


def _svg_number(value: float) -> str:
    text = "%.3f" % float(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def render_svg(sc: Scenario, pl: Placement) -> str:
    """Render board, keepouts and placed components as a standalone SVG string.

    Coordinates are converted from the model's bottom-left origin to SVG's
    top-left origin; the markup is deterministic (sorted references, fixed
    number formatting, no ids/timestamps) and contains the component ``ref``
    labels.  Pure standard library (``xml.sax.saxutils.escape`` only).
    """
    board_w = _as_float(sc.board_w) or 1.0
    board_h = _as_float(sc.board_h) or 1.0
    if board_w <= 0:
        board_w = 1.0
    if board_h <= 0:
        board_h = 1.0

    parts: List[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" '
        'width="%s" height="%s" role="img">'
        % (_svg_number(board_w), _svg_number(board_h),
           _svg_number(board_w), _svg_number(board_h)),
        "  <desc>%s</desc>" % _xml_escape(
            "offline placement map; placement_applied:false; "
            "routing_verified:false; drc:NOT RUN; eda_calls:0"),
        '  <rect x="0" y="0" width="%s" height="%s" fill="#fbfbfd" '
        'stroke="#222222" stroke-width="0.4"/>'
        % (_svg_number(board_w), _svg_number(board_h)),
    ]

    for keepout in sc.keepouts:
        try:
            x0, y0, x1, y1 = (float(v) for v in keepout)
        except (TypeError, ValueError):
            continue
        parts.append(
            '  <rect x="%s" y="%s" width="%s" height="%s" fill="#ffd9d9" '
            'stroke="#c96a6a" stroke-width="0.3" stroke-dasharray="1.2 0.8">'
            "<title>keepout</title></rect>"
            % (_svg_number(x0), _svg_number(board_h - y1),
               _svg_number(x1 - x0), _svg_number(y1 - y0)))

    missing: List[str] = []
    for ref in sorted(sc.components):
        comp = sc.components[ref]
        if ref not in pl:
            missing.append(ref)
            continue
        try:
            x, y, rot = pl[ref]
        except (TypeError, ValueError):
            missing.append(ref)
            continue
        xf = _as_float(x)
        yf = _as_float(y)
        if xf is None or yf is None:
            missing.append(ref)
            continue
        box = bbox(comp, xf, yf, int(rot) % 360)
        x0, y0, x1, y1 = box
        width = max(0.0, x1 - x0)
        height = max(0.0, y1 - y0)
        fill = "#4b5563" if comp.fixed else "#8fb3e8"
        title = ref + (" (fixed)" if comp.fixed else "")
        parts.append(
            '  <rect x="%s" y="%s" width="%s" height="%s" fill="%s" '
            'stroke="#1f3b66" stroke-width="%s"><title>%s</title></rect>'
            % (_svg_number(x0), _svg_number(board_h - y1),
               _svg_number(width), _svg_number(height), fill,
               "0.5" if comp.fixed else "0.3", _xml_escape(title)))
        font_size = max(0.8, min(2.0, min(width, height) * 0.45))
        parts.append(
            '  <text x="%s" y="%s" font-size="%s" font-family="monospace" '
            'text-anchor="middle" dominant-baseline="middle" fill="%s">%s'
            "</text>"
            % (_svg_number(x0 + width / 2.0), _svg_number(board_h - y1
                                                          + height / 2.0),
               _svg_number(font_size),
               "#ffffff" if comp.fixed else "#10233d",
               _xml_escape(ref)))

    parts.append(
        '  <text x="1" y="%s" font-size="1.3" font-family="monospace" '
        'fill="#555555">%s</text>'
        % (_svg_number(2.0),
           _xml_escape("%s  %gx%g mm" % (sc.name, board_w, board_h))))
    if missing:
        parts.append(
            '  <text x="1" y="%s" font-size="1.2" font-family="monospace" '
            'fill="#aa3333">%s</text>'
            % (_svg_number(4.2),
               _xml_escape("missing placement: " + ", ".join(missing))))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
