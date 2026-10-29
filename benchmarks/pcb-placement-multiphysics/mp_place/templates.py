"""Parametric product-family templates for the EasyCirq placement framework (P3).

Every entry of :data:`TEMPLATES` describes one common board family as plain
Python data: board-size ranges, edge-mounted fixed connectors, the power /
analog / digital / interface / RF module parameters, per-seed component size
ranges, nets and keepout rules.  :func:`instantiate` samples that description
with a deterministic RNG and returns a fully populated
:class:`~mp_place.model.Scenario` that the P1 solver consumes directly.

The eight families cover the P1 procedural study (``mcu-min``, ``buck``,
``rs485``, ``motor``, ``wireless``) plus three P3.5 product families
(``esp32-sensor``, ``can-node``, ``bldc-driver``).  They are parameterised
rather than fixed: the same template at different ``seed`` values yields
different board sizes, part dimensions, connector positions and power levels
while keeping the same electrical topology.  This is what lets an auto-layout
pipeline handle a whole product family without a model or a hand-made board.

Pure standard library.  The module only depends on the stable P1 interfaces
(:mod:`mp_place.model`, :mod:`mp_place.solver`).
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from .model import Component, Net, Scenario, bbox
from .solver import feasible_partial

Rect = Tuple[float, float, float, float]

#: Rotation options allowed for movable parts (fixed parts stay at rotation 0).
_ROT_ALL = (0, 90, 180, 270)

#: Keepout rule kinds understood by :func:`instantiate`.
#:
#: * ``antenna_clearance`` -- RF keepout around a fixed antenna (covers the
#:   antenna body plus ``expand_mm`` on the board side).
#: * ``connector_clearance`` -- insertion/creepage strip in front of a fixed
#:   edge connector (``depth_mm`` inward, ``side_mm`` beyond each end).
_KEEPOUT_KINDS = ("antenna_clearance", "connector_clearance")


# --------------------------------------------------------------------------- #
# Small geometry helpers
# --------------------------------------------------------------------------- #
def _u(rng: random.Random, spec) -> float:
    """Draw one uniform value from a ``float`` or a ``(lo, hi)`` range spec."""
    if isinstance(spec, (tuple, list)):
        lo, hi = float(spec[0]), float(spec[1])
        if hi < lo:
            raise ValueError(f"invalid range spec {spec!r}")
        return rng.uniform(lo, hi)
    return float(spec)


def _pad_offsets(w: float, h: float) -> Dict[str, Tuple[float, float]]:
    """Four generic pad offsets in the unrotated component frame."""
    return {
        "1": (-w / 2.0, 0.0),
        "2": (w / 2.0, 0.0),
        "3": (0.0, h / 2.0),
        "4": (0.0, -h / 2.0),
    }


def _pin_offsets(w: float, h: float, n: int, style: str) -> Dict[str, Tuple[float, float]]:
    """Build ``n`` named pad offsets.

    ``style="pads"`` numbers pads 1..n on the generic four-point template
    (a two-pin part only exposes pads 1 and 2); ``style="ic"`` cycles through
    the four sides of the body, matching how the P1 scenarios model ICs.
    """
    n = max(1, int(n))
    base = _pad_offsets(w, h)
    if style == "ic":
        return {str(i + 1): base[str((i % 4) + 1)] for i in range(n)}
    if style != "pads":
        raise ValueError(f"unknown pin style {style!r}")
    return {str(i + 1): base[str(i + 1)] for i in range(min(n, 4))}


def _edge_center(
    edge: str,
    board_w: float,
    board_h: float,
    w: float,
    h: float,
    frac: float,
) -> Tuple[float, float]:
    """Centre a fixed connector on its declared board edge.

    ``frac`` slides the connector along the edge; the resulting body bbox
    touches the edge exactly, so the hard ``connector_off_edge`` constraint is
    satisfied with margin to spare.
    """
    if edge == "left":
        return (w / 2.0, board_h * frac)
    if edge == "right":
        return (board_w - w / 2.0, board_h * frac)
    if edge == "bottom":
        return (board_w * frac, h / 2.0)
    if edge == "top":
        return (board_w * frac, board_h - h / 2.0)
    raise ValueError(f"unknown board edge {edge!r}")


def _antenna_center(
    board_w: float, board_h: float, w: float, h: float, margin: float
) -> Tuple[float, float]:
    """Pin a fixed antenna to the top-right corner (``margin`` mm inset)."""
    return (board_w - margin - w / 2.0, board_h - margin - h / 2.0)


def _antenna_keepout(
    board_w: float,
    board_h: float,
    cx: float,
    cy: float,
    w: float,
    h: float,
    expand: float,
) -> Rect:
    """Keepout rectangle covering the antenna plus an RF clearance band."""
    x0 = max(0.5, cx - w / 2.0 - expand)
    y0 = max(0.5, cy - h / 2.0 - expand)
    x1 = min(board_w - 0.5, cx + w / 2.0 + expand)
    y1 = min(board_h - 0.5, cy + h / 2.0 + expand)
    return (round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3))


def _connector_keepout(
    comp: Component,
    cx: float,
    cy: float,
    depth: float,
    side: float,
    board_w: float,
    board_h: float,
) -> Rect:
    """Keepout strip in front of a fixed edge connector, inside the board.

    The strip starts exactly at the connector's inner face (so it never
    overlaps the fixed connector itself) and widens ``side`` past both ends of
    the body to model mating / creepage clearance.
    """
    if comp.edge not in {"left", "right", "bottom", "top"}:
        raise ValueError(f"component {comp.ref!r} has no usable board edge")
    x0, y0, x1, y1 = bbox(comp, cx, cy, 0)
    if comp.edge == "left":
        nx0, nx1 = x1, x1 + depth
        ny0, ny1 = y0 - side, y1 + side
    elif comp.edge == "right":
        nx0, nx1 = x0 - depth, x0
        ny0, ny1 = y0 - side, y1 + side
    elif comp.edge == "bottom":
        nx0, nx1 = x0 - side, x1 + side
        ny0, ny1 = y1, y1 + depth
    else:  # top
        nx0, nx1 = x0 - side, x1 + side
        ny0, ny1 = y0 - depth, y0
    nx0, ny0 = max(0.0, nx0), max(0.0, ny0)
    nx1, ny1 = min(board_w, nx1), min(board_h, ny1)
    if not (nx0 < nx1 and ny0 < ny1):
        raise ValueError(
            f"connector keepout for {comp.ref!r} collapses to an empty rectangle"
        )
    return (nx0, ny0, nx1, ny1)


# --------------------------------------------------------------------------- #
# The eight product-family templates
# --------------------------------------------------------------------------- #
# Schema of one template (all numeric fields accept either a scalar or a
# (min, max) range that :func:`instantiate` samples per seed):
#   family, title, description              human-readable identity
#   board: {w, h}                           board-size ranges (mm)
#   edge_tol                                connector-to-edge tolerance (mm)
#   connectors: [{ref, w, h, pins, pin_style, edge, center_frac}]
#                                           fixed edge-mounted connectors
#   antenna: {ref, kind, w, h, pins, margin} | None
#   parts: [{ref, kind, w, h, pins, pin_style, power_w?, rotations?}]
#   modules: {power, analog, digital, interface, rf} design parameters
#   keepout_rules: [{kind, linked, expand_mm | depth_mm, side_mm?}]
#   nets: [{name, cls, pins: [[ref, pin], ...]}]
TEMPLATES: Dict[str, dict] = {
    "mcu-min": {
        "family": "mcu-min",
        "title": "MCU minimal system",
        "description": "LDO-powered MCU with crystal and decoupling; one edge connector.",
        "board": {"w": (74.0, 86.0), "h": (46.0, 54.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (7.5, 8.5),
                "h": (5.5, 6.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "left",
                "center_frac": (0.40, 0.60),
            }
        ],
        "antenna": None,
        "parts": [
            {"ref": "U1", "kind": "mcu", "w": (6.5, 7.5), "h": (6.5, 7.5),
             "pins": 8, "pin_style": "ic", "power_w": 0.15},
            {"ref": "Y1", "kind": "crystal", "w": (3.0, 3.4), "h": (2.3, 2.7), "pins": 2},
            {"ref": "U2", "kind": "power_switch", "w": (2.8, 3.4), "h": (2.8, 3.4),
             "pins": 3, "pin_style": "ic", "power_w": (0.5, 1.0)},
            {"ref": "L1", "kind": "inductor", "w": (5.5, 6.5), "h": (4.5, 5.5), "pins": 2},
            {"ref": "C1", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C2", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C3", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C4", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C5", "kind": "input_cap", "w": (1.8, 2.2), "h": (1.1, 1.3), "pins": 2},
            {"ref": "C6", "kind": "output_cap", "w": (1.8, 2.2), "h": (1.1, 1.3), "pins": 2},
        ],
        "modules": {
            "power": {"stage": "ldo", "vin_v": 5.0, "vout_v": 3.3,
                      "iout_a": (0.25, 0.55), "efficiency": 0.70},
            "analog": {"crystal_mhz": 8.0, "adc_bits": 10, "channels": 2},
            "digital": {"core": "mcu", "clock_mhz": 8.0, "uart": 1},
            "interface": {"connectors": ["J1"], "signals": 4},
            "rf": None,
        },
        "keepout_rules": [],
        "nets": [
            {"name": "VIN", "cls": "power",
             "pins": [["J1", "1"], ["C5", "1"], ["U2", "1"]]},
            {"name": "SW", "cls": "power", "pins": [["U2", "2"], ["L1", "1"]]},
            {"name": "VOUT", "cls": "power",
             "pins": [["L1", "2"], ["C6", "1"], ["U2", "3"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J1", "2"], ["C1", "2"], ["C2", "2"], ["C3", "2"],
                      ["C4", "2"], ["U1", "4"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["L1", "2"], ["C1", "1"], ["C2", "1"], ["C3", "1"],
                      ["C4", "1"], ["U1", "1"]]},
            {"name": "XTAL_IN", "cls": "analog", "pins": [["Y1", "1"], ["U1", "2"]]},
            {"name": "XTAL_OUT", "cls": "analog", "pins": [["Y1", "2"], ["U1", "3"]]},
            {"name": "UART_TX", "cls": "digital", "pins": [["U1", "5"], ["J1", "3"]]},
            {"name": "ADC_IN", "cls": "analog", "pins": [["J1", "4"], ["U1", "6"]]},
        ],
    },
    "buck": {
        "family": "buck",
        "title": "Synchronous buck converter",
        "description": "12 V to 3.3 V buck stage with feedback divider and UART telemetry.",
        "board": {"w": (86.0, 96.0), "h": (50.0, 60.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (7.5, 8.5),
                "h": (5.5, 6.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "left",
                "center_frac": (0.40, 0.60),
            }
        ],
        "antenna": None,
        "parts": [
            {"ref": "U1", "kind": "power_switch", "w": (3.6, 4.4), "h": (3.6, 4.4),
             "pins": 4, "pin_style": "ic", "power_w": (1.1, 1.9)},
            {"ref": "L1", "kind": "inductor", "w": (7.0, 9.0), "h": (5.5, 6.5), "pins": 2},
            {"ref": "U2", "kind": "mcu", "w": (5.5, 6.5), "h": (5.5, 6.5),
             "pins": 6, "pin_style": "ic", "power_w": 0.12},
            {"ref": "C1", "kind": "input_cap", "w": (2.8, 3.6), "h": (2.2, 2.8), "pins": 2},
            {"ref": "C2", "kind": "input_cap", "w": (2.8, 3.6), "h": (2.2, 2.8), "pins": 2},
            {"ref": "C3", "kind": "output_cap", "w": (2.8, 3.6), "h": (2.2, 2.8), "pins": 2},
            {"ref": "C4", "kind": "output_cap", "w": (2.8, 3.6), "h": (2.2, 2.8), "pins": 2},
            {"ref": "C5", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C6", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "R1", "kind": "analog", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "R2", "kind": "analog", "w": 1.6, "h": 0.8, "pins": 2},
        ],
        "modules": {
            "power": {"stage": "buck", "vin_v": 12.0, "vout_v": 3.3,
                      "iout_a": (1.0, 1.5), "fsw_khz": (450, 650), "efficiency": 0.90},
            "analog": {"feedback": "resistor_divider", "channels": 1},
            "digital": {"core": "mcu", "uart": 1},
            "interface": {"connectors": ["J1"], "signals": 3},
            "rf": None,
        },
        "keepout_rules": [],
        "nets": [
            {"name": "VIN", "cls": "power",
             "pins": [["J1", "1"], ["C1", "1"], ["C2", "1"], ["U1", "1"]]},
            {"name": "SW", "cls": "power", "pins": [["U1", "2"], ["L1", "1"]]},
            {"name": "VOUT", "cls": "power",
             "pins": [["L1", "2"], ["C3", "1"], ["C4", "1"], ["U2", "1"]]},
            {"name": "FB", "cls": "analog",
             "pins": [["L1", "2"], ["R1", "1"], ["R2", "1"], ["U2", "2"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J1", "2"], ["C1", "2"], ["C2", "2"], ["C3", "2"],
                      ["C4", "2"], ["U1", "4"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["C3", "1"], ["C5", "1"], ["C6", "1"], ["U2", "1"]]},
            {"name": "UART", "cls": "digital", "pins": [["U2", "3"], ["J1", "3"]]},
        ],
    },
    "rs485": {
        "family": "rs485",
        "title": "Isolated RS485 interface",
        "description": "Isolated 485 transceiver between two edge connectors with a local MCU.",
        "board": {"w": (66.0, 76.0), "h": (42.0, 50.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (6.5, 7.5),
                "h": (4.5, 5.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "left",
                "center_frac": (0.38, 0.62),
            },
            {
                "ref": "J2",
                "w": (6.5, 7.5),
                "h": (4.5, 5.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "right",
                "center_frac": (0.38, 0.62),
            },
        ],
        "antenna": None,
        "parts": [
            {"ref": "U1", "kind": "mcu", "w": (5.5, 6.5), "h": (5.5, 6.5),
             "pins": 6, "pin_style": "ic", "power_w": 0.10},
            {"ref": "U2", "kind": "analog", "w": (4.6, 5.4), "h": (3.6, 4.4),
             "pins": 4, "pin_style": "ic"},
            {"ref": "U3", "kind": "power_switch", "w": (3.6, 4.4), "h": (3.6, 4.4),
             "pins": 4, "pin_style": "ic", "power_w": (0.3, 0.6)},
            {"ref": "C1", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C2", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C3", "kind": "input_cap", "w": (1.8, 2.2), "h": (1.1, 1.3), "pins": 2},
            {"ref": "Y1", "kind": "crystal", "w": 3.2, "h": 2.5, "pins": 2},
            {"ref": "R1", "kind": "analog", "w": 1.6, "h": 0.8, "pins": 2},
        ],
        "modules": {
            "power": {"stage": "isolated_dcdc", "vin_v": 5.0, "vout_v": 3.3,
                      "iout_a": (0.10, 0.25), "isolation_kv": 2.5},
            "analog": {"transceiver": "rs485", "baud": (9600, 115200),
                       "termination_ohm": 120},
            "digital": {"core": "mcu", "uart": 2},
            "interface": {"connectors": ["J1", "J2"], "signals": 4},
            "rf": None,
        },
        "keepout_rules": [],
        "nets": [
            {"name": "VIN", "cls": "power",
             "pins": [["J1", "1"], ["C3", "1"], ["U3", "1"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["U3", "2"], ["C1", "1"], ["C2", "1"], ["U1", "1"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J1", "2"], ["C3", "2"], ["C1", "2"], ["C2", "2"],
                      ["U1", "4"]]},
            {"name": "A", "cls": "analog",
             "pins": [["U2", "1"], ["J2", "1"], ["R1", "1"]]},
            {"name": "B", "cls": "analog",
             "pins": [["U2", "2"], ["J2", "2"], ["R1", "2"]]},
            {"name": "RXD", "cls": "digital", "pins": [["U2", "3"], ["U1", "2"]]},
            {"name": "XTAL", "cls": "analog", "pins": [["Y1", "1"], ["U1", "3"]]},
        ],
    },
    "motor": {
        "family": "motor",
        "title": "Motor driver",
        "description": "24 V H-bridge with current sense, encoder connector and bulk input caps.",
        "board": {"w": (94.0, 106.0), "h": (56.0, 66.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (8.5, 9.5),
                "h": (6.5, 7.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "bottom",
                "center_frac": (0.40, 0.60),
            },
            {
                "ref": "J2",
                "w": (6.5, 7.5),
                "h": (4.5, 5.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "right",
                "center_frac": (0.50, 0.70),
            },
        ],
        "antenna": None,
        "parts": [
            {"ref": "U1", "kind": "power_switch", "w": (5.5, 6.5), "h": (5.5, 6.5),
             "pins": 4, "pin_style": "ic", "power_w": (1.6, 2.6)},
            {"ref": "U2", "kind": "mcu", "w": (6.5, 7.5), "h": (6.5, 7.5),
             "pins": 8, "pin_style": "ic", "power_w": 0.15},
            {"ref": "L1", "kind": "inductor", "w": (6.5, 7.5), "h": (4.5, 5.5), "pins": 2},
            {"ref": "C1", "kind": "input_cap", "w": (3.6, 4.4), "h": (2.8, 3.2), "pins": 2},
            {"ref": "C2", "kind": "input_cap", "w": (3.6, 4.4), "h": (2.8, 3.2), "pins": 2},
            {"ref": "C3", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C4", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "R1", "kind": "analog", "w": (1.8, 2.2), "h": (0.9, 1.1), "pins": 2},
            {"ref": "D1", "kind": "analog", "w": (2.8, 3.2), "h": (1.8, 2.2), "pins": 2},
        ],
        "modules": {
            "power": {"stage": "h_bridge", "vin_v": 24.0, "iout_a": (1.5, 3.0),
                      "pwm_khz": (16, 25), "efficiency": 0.92},
            "analog": {"current_sense": "shunt", "shunt_mohm": (5, 20)},
            "digital": {"core": "mcu", "pwm_channels": 2, "encoder": True},
            "interface": {"connectors": ["J1", "J2"], "signals": 4},
            "rf": None,
        },
        "keepout_rules": [],
        "nets": [
            {"name": "VIN", "cls": "power",
             "pins": [["J1", "1"], ["C1", "1"], ["C2", "1"], ["U1", "1"]]},
            {"name": "MOTOR_A", "cls": "power",
             "pins": [["U1", "2"], ["L1", "1"], ["J1", "3"], ["D1", "1"]]},
            {"name": "MOTOR_B", "cls": "power",
             "pins": [["U1", "3"], ["L1", "2"], ["J1", "4"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J1", "2"], ["C1", "2"], ["C2", "2"], ["U1", "4"], ["D1", "2"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["C3", "1"], ["C4", "1"], ["U2", "1"]]},
            {"name": "ISENSE", "cls": "analog",
             "pins": [["R1", "1"], ["U1", "4"], ["U2", "2"]]},
            {"name": "PWM", "cls": "digital", "pins": [["U2", "3"], ["U1", "2"]]},
            {"name": "FAULT", "cls": "digital", "pins": [["U2", "4"], ["U1", "3"]]},
            {"name": "ENC_A", "cls": "digital", "pins": [["U2", "5"], ["J2", "1"]]},
            {"name": "ENC_B", "cls": "digital", "pins": [["U2", "6"], ["J2", "2"]]},
        ],
    },
    "wireless": {
        "family": "wireless",
        "title": "Wireless sensor node",
        "description": "2.4 GHz sensor node with chip antenna, RF keepout and analog front end.",
        "board": {"w": (80.0, 92.0), "h": (56.0, 64.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (7.5, 8.5),
                "h": (5.5, 6.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "left",
                "center_frac": (0.40, 0.60),
            }
        ],
        "antenna": {
            "ref": "ANT1",
            "kind": "antenna",
            "w": (9.0, 11.0),
            "h": (5.0, 7.0),
            "pins": 2,
            "margin": 1.0,
        },
        "parts": [
            {"ref": "U1", "kind": "mcu", "w": (6.5, 7.5), "h": (6.5, 7.5),
             "pins": 8, "pin_style": "ic", "power_w": 0.18},
            {"ref": "U2", "kind": "analog", "w": (4.6, 5.4), "h": (4.6, 5.4),
             "pins": 4, "pin_style": "ic"},
            {"ref": "U3", "kind": "power_switch", "w": (3.6, 4.4), "h": (3.6, 4.4),
             "pins": 4, "pin_style": "ic", "power_w": (0.4, 0.8)},
            {"ref": "L1", "kind": "inductor", "w": (5.5, 6.5), "h": (4.5, 5.5), "pins": 2},
            {"ref": "Y1", "kind": "crystal", "w": 3.2, "h": 2.5, "pins": 2},
            {"ref": "C1", "kind": "input_cap", "w": (1.8, 2.2), "h": (1.1, 1.3), "pins": 2},
            {"ref": "C2", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C3", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "R1", "kind": "analog", "w": 1.6, "h": 0.8, "pins": 2},
        ],
        "modules": {
            "power": {"stage": "ldo", "vin_v": 5.0, "vout_v": 3.3,
                      "iout_a": (0.20, 0.50)},
            "analog": {"sensor_afe": True, "channels": 2, "crystal_mhz": 16.0},
            "digital": {"core": "mcu", "radio": "integrated"},
            "interface": {"connectors": ["J1"], "signals": 3},
            "rf": {"band_mhz": (2400, 2480), "tx_dbm": (0, 8), "antenna": "chip"},
        },
        "keepout_rules": [
            {"kind": "antenna_clearance", "linked": "ANT1", "expand_mm": (1.5, 3.5)}
        ],
        "nets": [
            {"name": "VIN", "cls": "power",
             "pins": [["J1", "1"], ["C1", "1"], ["U3", "1"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["U3", "2"], ["C2", "1"], ["C3", "1"], ["U1", "1"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J1", "2"], ["C1", "2"], ["C2", "2"], ["C3", "2"],
                      ["U1", "4"], ["ANT1", "2"]]},
            {"name": "RF", "cls": "rf", "pins": [["U1", "5"], ["ANT1", "1"]]},
            {"name": "AFE", "cls": "analog",
             "pins": [["U2", "1"], ["U1", "2"], ["R1", "1"]]},
            {"name": "SENSOR", "cls": "analog", "pins": [["U2", "2"], ["J1", "3"]]},
            {"name": "XTAL", "cls": "analog", "pins": [["Y1", "1"], ["U1", "3"]]},
            {"name": "PWR_IN", "cls": "power", "pins": [["U3", "1"], ["L1", "1"]]},
        ],
    },
    # ------------------------------------------------------------------ #
    # P3.5 product families
    # ------------------------------------------------------------------ #
    "esp32-sensor": {
        "family": "esp32-sensor",
        "title": "ESP32-C3 wireless sensor node",
        "description": "USB-C powered ESP32-C3 with I2C temperature/humidity sensor, LDO and chip antenna.",
        "board": {"w": (62.0, 72.0), "h": (42.0, 50.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (8.5, 9.5),
                "h": (6.5, 7.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "bottom",
                "center_frac": (0.45, 0.60),
            }
        ],
        "antenna": {
            "ref": "ANT1",
            "kind": "antenna",
            "w": (8.0, 10.0),
            "h": (4.5, 6.0),
            "pins": 2,
            "margin": 1.0,
        },
        "parts": [
            {"ref": "U1", "kind": "mcu", "w": (6.5, 7.5), "h": (6.5, 7.5),
             "pins": 8, "pin_style": "ic", "power_w": (0.20, 0.30)},
            {"ref": "U2", "kind": "analog", "w": (2.8, 3.4), "h": (2.8, 3.4),
             "pins": 4, "pin_style": "ic", "power_w": 0.01},
            {"ref": "U3", "kind": "power_switch", "w": (3.0, 3.6), "h": (3.0, 3.6),
             "pins": 3, "pin_style": "ic", "power_w": (0.20, 0.40)},
            {"ref": "C1", "kind": "input_cap", "w": (1.8, 2.2), "h": (1.1, 1.3), "pins": 2},
            {"ref": "C2", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C3", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "R1", "kind": "analog", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "R2", "kind": "analog", "w": 1.6, "h": 0.8, "pins": 2},
        ],
        "modules": {
            "power": {"stage": "ldo", "vin_v": 5.0, "vout_v": 3.3,
                      "iout_a": (0.15, 0.40), "efficiency": 0.65},
            "analog": {"sensor": "temp_humidity", "bus": "i2c", "channels": 2},
            "digital": {"core": "esp32-c3", "wifi": True, "ble": True, "usb": "fs"},
            "interface": {"connectors": ["J1"], "usb": "type-c", "signals": 4},
            "rf": {"band_mhz": (2400, 2480), "tx_dbm": (0, 10), "antenna": "chip"},
        },
        "keepout_rules": [
            {"kind": "antenna_clearance", "linked": "ANT1", "expand_mm": (1.5, 3.0)},
            {"kind": "connector_clearance", "linked": "J1",
             "depth_mm": (2.0, 3.5), "side_mm": 1.0},
        ],
        "nets": [
            {"name": "VBUS", "cls": "power",
             "pins": [["J1", "1"], ["C1", "1"], ["U3", "1"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["U3", "2"], ["C2", "1"], ["C3", "1"], ["U1", "1"],
                      ["U2", "4"], ["R1", "1"], ["R2", "1"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J1", "2"], ["C1", "2"], ["C2", "2"], ["C3", "2"],
                      ["U1", "4"], ["U2", "2"], ["U3", "3"], ["ANT1", "2"]]},
            {"name": "USB_D_P", "cls": "digital", "pins": [["J1", "3"], ["U1", "2"]]},
            {"name": "USB_D_N", "cls": "digital", "pins": [["J1", "4"], ["U1", "3"]]},
            {"name": "I2C_SCL", "cls": "digital",
             "pins": [["U1", "5"], ["R1", "2"], ["U2", "1"]]},
            {"name": "I2C_SDA", "cls": "digital",
             "pins": [["U1", "6"], ["R2", "2"], ["U2", "3"]]},
            {"name": "RF", "cls": "rf", "pins": [["U1", "7"], ["ANT1", "1"]]},
        ],
    },
    "can-node": {
        "family": "can-node",
        "title": "Isolated CAN bus node",
        "description": "CAN transceiver with common-mode choke, TVS protection and LDO-powered MCU.",
        "board": {"w": (66.0, 78.0), "h": (44.0, 54.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (7.5, 8.5),
                "h": (5.5, 6.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "left",
                "center_frac": (0.38, 0.62),
            },
            {
                "ref": "J2",
                "w": (6.5, 7.5),
                "h": (4.5, 5.5),
                "pins": 2,
                "pin_style": "ic",
                "edge": "bottom",
                "center_frac": (0.45, 0.65),
            },
        ],
        "antenna": None,
        "parts": [
            {"ref": "U1", "kind": "mcu", "w": (5.5, 6.5), "h": (5.5, 6.5),
             "pins": 6, "pin_style": "ic", "power_w": 0.12},
            {"ref": "U2", "kind": "analog", "w": (4.6, 5.4), "h": (3.6, 4.4),
             "pins": 6, "pin_style": "ic"},
            {"ref": "U3", "kind": "power_switch", "w": (3.0, 3.6), "h": (3.0, 3.6),
             "pins": 3, "pin_style": "ic", "power_w": (0.20, 0.50)},
            {"ref": "L1", "kind": "inductor", "w": (4.0, 4.8), "h": (3.0, 3.6), "pins": 4},
            {"ref": "D1", "kind": "diode", "w": (2.0, 2.4), "h": (1.2, 1.6), "pins": 2},
            {"ref": "D2", "kind": "diode", "w": (2.0, 2.4), "h": (1.2, 1.6), "pins": 2},
            {"ref": "R1", "kind": "analog", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C1", "kind": "input_cap", "w": (1.8, 2.2), "h": (1.1, 1.3), "pins": 2},
            {"ref": "C2", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C3", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
        ],
        "modules": {
            "power": {"stage": "ldo", "vin_v": 24.0, "vout_v": 3.3,
                      "iout_a": (0.10, 0.30), "input_protection": "tvs"},
            "analog": {"transceiver": "can", "baud": (125000, 1000000),
                       "termination_ohm": 120, "common_mode_choke": True},
            "digital": {"core": "mcu", "can_controller": 1, "uart": 1},
            "interface": {"connectors": ["J1", "J2"], "signals": 4},
            "rf": None,
        },
        "keepout_rules": [
            {"kind": "connector_clearance", "linked": "J1",
             "depth_mm": (2.5, 4.0), "side_mm": 1.2},
            {"kind": "connector_clearance", "linked": "J2",
             "depth_mm": (2.0, 3.0), "side_mm": 1.0},
        ],
        "nets": [
            {"name": "VIN", "cls": "power",
             "pins": [["J2", "1"], ["C1", "1"], ["U3", "1"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["U3", "2"], ["C2", "1"], ["C3", "1"], ["U1", "1"], ["U2", "3"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J2", "2"], ["J1", "3"], ["J1", "4"], ["C1", "2"],
                      ["C2", "2"], ["C3", "2"], ["U1", "4"], ["U2", "4"],
                      ["U3", "3"], ["D1", "2"], ["D2", "2"]]},
            {"name": "TXD", "cls": "digital", "pins": [["U1", "2"], ["U2", "1"]]},
            {"name": "RXD", "cls": "digital", "pins": [["U1", "3"], ["U2", "2"]]},
            {"name": "CANH_FILT", "cls": "analog", "pins": [["U2", "5"], ["L1", "1"]]},
            {"name": "CANH_BUS", "cls": "analog",
             "pins": [["L1", "2"], ["D1", "1"], ["R1", "1"], ["J1", "1"]]},
            {"name": "CANL_FILT", "cls": "analog", "pins": [["U2", "6"], ["L1", "3"]]},
            {"name": "CANL_BUS", "cls": "analog",
             "pins": [["L1", "4"], ["D2", "1"], ["R1", "2"], ["J1", "2"]]},
        ],
    },
    "bldc-driver": {
        "family": "bldc-driver",
        "title": "Three-phase BLDC driver",
        "description": "24 V three-phase bridge with low-side shunt current sense and hall inputs.",
        "board": {"w": (86.0, 98.0), "h": (56.0, 66.0)},
        "edge_tol": 2.0,
        "connectors": [
            {
                "ref": "J1",
                "w": (11.0, 13.0),
                "h": (7.0, 8.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "bottom",
                "center_frac": (0.42, 0.58),
            },
            {
                "ref": "J2",
                "w": (8.5, 9.5),
                "h": (6.0, 7.0),
                "pins": 2,
                "pin_style": "ic",
                "edge": "left",
                "center_frac": (0.32, 0.48),
            },
            {
                "ref": "J3",
                "w": (6.5, 7.5),
                "h": (4.5, 5.5),
                "pins": 4,
                "pin_style": "ic",
                "edge": "right",
                "center_frac": (0.55, 0.75),
            },
        ],
        "antenna": None,
        "parts": [
            {"ref": "U1", "kind": "power_switch", "w": (9.0, 10.5), "h": (8.0, 9.5),
             "pins": 8, "pin_style": "ic", "power_w": (2.0, 3.2)},
            {"ref": "U2", "kind": "mcu", "w": (6.5, 7.5), "h": (6.5, 7.5),
             "pins": 8, "pin_style": "ic", "power_w": 0.15},
            {"ref": "U3", "kind": "analog", "w": (3.6, 4.4), "h": (3.0, 3.8),
             "pins": 4, "pin_style": "ic", "power_w": 0.05},
            {"ref": "U4", "kind": "power_switch", "w": (3.6, 4.4), "h": (3.6, 4.4),
             "pins": 4, "pin_style": "ic", "power_w": (0.5, 1.0)},
            {"ref": "L1", "kind": "inductor", "w": (7.0, 8.0), "h": (4.5, 5.5), "pins": 2},
            {"ref": "R1", "kind": "analog", "w": (3.2, 4.0), "h": (1.4, 1.8), "pins": 2},
            {"ref": "C1", "kind": "input_cap", "w": (3.6, 4.4), "h": (2.8, 3.2), "pins": 2},
            {"ref": "C2", "kind": "input_cap", "w": (2.8, 3.6), "h": (2.2, 2.8), "pins": 2},
            {"ref": "C3", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
            {"ref": "C4", "kind": "decap", "w": 1.6, "h": 0.8, "pins": 2},
        ],
        "modules": {
            "power": {"stage": "three_phase_bridge", "vin_v": 24.0,
                      "phase_current_a": (2.0, 6.0), "pwm_khz": (16, 25),
                      "efficiency": 0.93},
            "analog": {"current_sense": "low_side_shunt", "shunt_mohm": (1, 5),
                       "amp_gain": (10, 50)},
            "digital": {"core": "mcu", "pwm_channels": 3, "hall_inputs": 3},
            "interface": {"connectors": ["J1", "J2", "J3"], "signals": 4},
            "rf": None,
        },
        "keepout_rules": [
            {"kind": "connector_clearance", "linked": "J1",
             "depth_mm": (2.5, 4.0), "side_mm": 1.2},
            {"kind": "connector_clearance", "linked": "J2",
             "depth_mm": (2.0, 3.0), "side_mm": 1.0},
        ],
        "nets": [
            {"name": "VIN_RAW", "cls": "power",
             "pins": [["J2", "1"], ["L1", "1"], ["C1", "1"]]},
            {"name": "VIN", "cls": "power",
             "pins": [["L1", "2"], ["C2", "1"], ["U1", "1"], ["U4", "1"]]},
            {"name": "PHASE_A", "cls": "power", "pins": [["U1", "2"], ["J1", "1"]]},
            {"name": "PHASE_B", "cls": "power", "pins": [["U1", "3"], ["J1", "2"]]},
            {"name": "PHASE_C", "cls": "power", "pins": [["U1", "4"], ["J1", "3"]]},
            {"name": "GND_DRIVER", "cls": "ground",
             "pins": [["U1", "5"], ["R1", "1"], ["U3", "1"]]},
            {"name": "GND", "cls": "ground",
             "pins": [["J2", "2"], ["J1", "4"], ["C1", "2"], ["C2", "2"],
                      ["R1", "2"], ["U3", "2"], ["U4", "3"], ["C3", "2"],
                      ["C4", "2"], ["J3", "4"]]},
            {"name": "VDD", "cls": "power",
             "pins": [["U4", "2"], ["C3", "1"], ["C4", "1"], ["U2", "1"]]},
            {"name": "ISENSE", "cls": "analog", "pins": [["U3", "3"], ["U2", "2"]]},
            {"name": "HALL_A", "cls": "digital", "pins": [["U2", "3"], ["J3", "1"]]},
            {"name": "HALL_B", "cls": "digital", "pins": [["U2", "4"], ["J3", "2"]]},
            {"name": "HALL_C", "cls": "digital", "pins": [["U2", "5"], ["J3", "3"]]},
            {"name": "PWM_A", "cls": "digital", "pins": [["U2", "6"], ["U1", "6"]]},
            {"name": "PWM_B", "cls": "digital", "pins": [["U2", "7"], ["U1", "7"]]},
            {"name": "PWM_C", "cls": "digital", "pins": [["U2", "8"], ["U1", "8"]]},
        ],
    },
}


# --------------------------------------------------------------------------- #
# Instantiation
# --------------------------------------------------------------------------- #
def _build_component(
    rng: random.Random,
    part: dict,
    *,
    fixed: bool = False,
    edge: Optional[str] = None,
) -> Component:
    """Create one :class:`Component` from a part spec, sampling its ranges."""
    w = _u(rng, part["w"])
    h = _u(rng, part["h"])
    return Component(
        ref=str(part["ref"]),
        kind=str(part.get("kind", "connector")),
        w=w,
        h=h,
        fixed=fixed,
        rotations=(0,) if fixed else tuple(part.get("rotations", _ROT_ALL)),
        power_w=_u(rng, part.get("power_w", 0.0)),
        edge=edge,
        pins=_pin_offsets(w, h, part.get("pins", 2), part.get("pin_style", "pads")),
    )


def _validate(sc: Scenario, n_refs: int) -> None:
    """Fail loudly if a sampled scenario would be unusable downstream."""
    # 1) Every fixed part has a base coordinate and vice versa.
    fixed = sorted(r for r, c in sc.components.items() if c.fixed)
    if sorted(sc.base_placement) != fixed:
        raise RuntimeError(f"{sc.name}: base_placement does not match fixed parts")
    fixed_pl = {ref: sc.base_placement[ref] for ref in fixed}
    if not feasible_partial(sc, fixed_pl):
        raise RuntimeError(f"{sc.name}: fixed connectors/antenna are not feasible")

    # 2) No duplicated component reference (dict collapse would hide it).
    if len(sc.components) != n_refs:
        raise RuntimeError(f"{sc.name}: duplicate component refs in template spec")

    # 3) Nets are complete and every pin exists on its component.
    covered = set()
    for net in sc.nets:
        if len(net.pins) < 2:
            raise RuntimeError(f"{sc.name}: net {net.name} has fewer than 2 pins")
        for ref, pin in net.pins:
            if ref not in sc.components:
                raise RuntimeError(f"{sc.name}: net {net.name} references unknown {ref}")
            if pin not in sc.components[ref].pins:
                raise RuntimeError(f"{sc.name}: {ref} has no pin {pin!r} ({net.name})")
            covered.add(ref)
    if covered != set(sc.components):
        missing = sorted(set(sc.components) - covered)
        raise RuntimeError(f"{sc.name}: components without nets: {missing}")

    # 4) Keepouts are inside the board and do not swallow fixed connectors.
    for x0, y0, x1, y1 in sc.keepouts:
        if not (0.0 <= x0 < x1 <= sc.board_w and 0.0 <= y0 < y1 <= sc.board_h):
            raise RuntimeError(f"{sc.name}: keepout {x0, y0, x1, y1} outside board")
    for ref in fixed:
        comp = sc.components[ref]
        if comp.kind in {"antenna", "rf"}:
            continue
        box = bbox(comp, *sc.base_placement[ref])
        for x0, y0, x1, y1 in sc.keepouts:
            overlap_w = min(box[2], x1) - max(box[0], x0)
            overlap_h = min(box[3], y1) - max(box[1], y0)
            if overlap_w > 1e-6 and overlap_h > 1e-6:
                raise RuntimeError(f"{sc.name}: keepout overlaps fixed connector {ref}")


def instantiate(name: str, seed: int = 0) -> Scenario:
    """Sample template ``name`` into a fresh :class:`Scenario`.

    The RNG is seeded with ``(name, seed)`` so the result is deterministic and
    independent of call order.  Fixed connectors/antenna are placed exactly on
    their board edges (or slot) and the whole scenario is validated to be
    directly consumable by :func:`mp_place.solver.random_feasible_placement`.
    """
    spec = TEMPLATES.get(name)
    if spec is None:
        raise KeyError(f"unknown template {name!r}; known templates: {sorted(TEMPLATES)}")

    rng = random.Random(f"easycirq-template:{name}:{seed}")
    board_w = round(_u(rng, spec["board"]["w"]), 1)
    board_h = round(_u(rng, spec["board"]["h"]), 1)
    edge_tol = float(spec.get("edge_tol", 2.0))

    components: Dict[str, Component] = {}
    base_placement: Dict[str, Tuple[float, float, int]] = {}

    # --- fixed edge connectors -------------------------------------------
    for conn in spec["connectors"]:
        comp = _build_component(rng, conn, fixed=True, edge=str(conn["edge"]))
        frac = _u(rng, conn["center_frac"])
        x, y = _edge_center(comp.edge, board_w, board_h, comp.w, comp.h, frac)
        components[comp.ref] = comp
        base_placement[comp.ref] = (x, y, 0)

    # --- fixed RF antenna ------------------------------------------------
    keepouts: List[Rect] = []
    antenna_spec = spec.get("antenna")
    if antenna_spec is not None:
        comp = _build_component(rng, antenna_spec, fixed=True)
        cx, cy = _antenna_center(
            board_w, board_h, comp.w, comp.h, float(antenna_spec.get("margin", 1.0))
        )
        components[comp.ref] = comp
        base_placement[comp.ref] = (cx, cy, 0)

    # --- keepout rules ---------------------------------------------------
    for rule in spec.get("keepout_rules", []):
        kind = rule.get("kind")
        if kind not in _KEEPOUT_KINDS:
            raise ValueError(f"{name}: unknown keepout rule kind {kind!r}")
        ref = str(rule["linked"])
        if ref not in components or not components[ref].fixed:
            raise ValueError(f"{name}: keepout rule linked to non-fixed {ref!r}")
        comp = components[ref]
        cx, cy = base_placement[ref][0], base_placement[ref][1]
        if kind == "antenna_clearance":
            expand = _u(rng, rule["expand_mm"])
            keepouts.append(
                _antenna_keepout(board_w, board_h, cx, cy, comp.w, comp.h, expand)
            )
        else:  # connector_clearance
            depth = _u(rng, rule["depth_mm"])
            side = _u(rng, rule.get("side_mm", 1.0))
            keepouts.append(
                _connector_keepout(comp, cx, cy, depth, side, board_w, board_h)
            )

    # --- movable modules -------------------------------------------------
    for part in spec["parts"]:
        comp = _build_component(rng, part, fixed=False)
        components[comp.ref] = comp

    # --- electrical nets -------------------------------------------------
    nets = [
        Net(
            name=str(net["name"]),
            cls=str(net["cls"]),
            pins=tuple((str(ref), str(pin)) for ref, pin in net["pins"]),
        )
        for net in spec["nets"]
    ]

    scenario = Scenario(
        name=name,
        board_w=board_w,
        board_h=board_h,
        components=components,
        nets=nets,
        keepouts=keepouts,
        edge_tol=edge_tol,
        base_placement=base_placement,
    )
    n_refs = len(spec["connectors"]) + (1 if antenna_spec is not None else 0) + len(spec["parts"])
    _validate(scenario, n_refs)
    return scenario


def template_names() -> List[str]:
    """Return the registered template names in deterministic order."""
    return sorted(TEMPLATES)


__all__ = ["TEMPLATES", "instantiate", "template_names"]
