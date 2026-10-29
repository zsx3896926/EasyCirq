"""Deterministic scenario generator for the P1 multi-physics placement study.

Five small-board families are generated procedurally.  Each family has a fixed
connector (mechanical constraint), a power stage, an analog/sensitive block, an
MCU with decoupling caps and (in one family) an RF module with a local keepout.

Everything is millimetres.  Boards are intentionally small (60-100 mm) so a
pure-Python simulated-annealing search can explore them in seconds.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from .model import Component, Net, Scenario

Rect = Tuple[float, float, float, float]


def _pads(w: float, h: float) -> Dict[str, Tuple[float, float]]:
    return {
        "1": (-w / 2.0, 0.0),
        "2": (w / 2.0, 0.0),
        "3": (0.0, h / 2.0),
        "4": (0.0, -h / 2.0),
    }


def _ic(w: float, h: float, n: int = 4) -> Dict[str, Tuple[float, float]]:
    d = _pads(w, h)
    return {str(i + 1): d[str((i % 4) + 1)] for i in range(n)}


def _mk(ref, kind, w, h, *, fixed=False, power=0.0, edge=None, pads=None, rot=(0,)) -> Component:
    return Component(
        ref=ref,
        kind=kind,
        w=w,
        h=h,
        fixed=fixed,
        rotations=rot,
        power_w=power,
        edge=edge,
        pins=pads if pads is not None else _pads(w, h),
    )


def _scenario(
    name: str,
    board_w: float,
    board_h: float,
    comps: List[Component],
    nets: List[Net],
    keepouts: List[Rect],
    fixed: Dict[str, Tuple[float, int]],
) -> Scenario:
    base = {}
    for ref, (x, y, rot) in fixed.items():
        base[ref] = (x, y, rot)
    return Scenario(
        name=name,
        board_w=board_w,
        board_h=board_h,
        components={c.ref: c for c in comps},
        nets=nets,
        keepouts=keepouts,
        edge_tol=2.0,
        base_placement=base,
    )


def build_scenarios(seed: int = 0) -> List[Scenario]:
    rng = random.Random(seed)
    out: List[Scenario] = []

    # --- 1) MCU minimal system -------------------------------------------
    bw, bh = 80.0, 50.0
    j1 = _mk("J1", "connector", 8.0, 6.0, fixed=True, edge="left", pads=_ic(8, 6, 4))
    u1 = _mk("U1", "mcu", 7.0, 7.0, pads=_ic(7, 7, 8))
    y1 = _mk("Y1", "crystal", 3.2, 2.5, pads=_pads(3.2, 2.5))
    l1 = _mk("L1", "inductor", 6.0, 5.0, pads=_pads(6, 5))
    u2 = _mk("U2", "power_switch", 3.0, 3.0, power=0.8, pads=_ic(3, 3, 3))
    caps = [
        _mk("C1", "decap", 1.6, 0.8),
        _mk("C2", "decap", 1.6, 0.8),
        _mk("C3", "decap", 1.6, 0.8),
        _mk("C4", "decap", 1.6, 0.8),
        _mk("C5", "input_cap", 2.0, 1.2),
        _mk("C6", "output_cap", 2.0, 1.2),
    ]
    nets = [
        Net("VIN", "power", (("J1", "1"), ("C5", "1"), ("U2", "1"))),
        Net("SW", "power", (("U2", "2"), ("L1", "1"))),
        Net("VOUT", "power", (("L1", "2"), ("C6", "1"), ("U2", "3"))),
        Net("GND", "ground", tuple((c.ref, "2") for c in caps) + (("J1", "2"), ("U1", "4"))),
        Net("VDD", "power", (("L1", "2"), ("C1", "1"), ("C2", "1"), ("C3", "1"), ("C4", "1"), ("U1", "1"))),
        Net("XTAL_IN", "analog", (("Y1", "1"), ("U1", "2"))),
        Net("XTAL_OUT", "analog", (("Y1", "2"), ("U1", "3"))),
        Net("UART_TX", "digital", (("U1", "5"), ("J1", "3"))),
        Net("ADC_IN", "analog", (("J1", "4"), ("U1", "6"))),
    ]
    comps = [j1, u1, y1, l1, u2] + caps
    out.append(_scenario("mcu-min", bw, bh, comps, nets, [], {"J1": (5.0, 25.0, 0)}))

    # --- 2) Buck converter ------------------------------------------------
    bw, bh = 90.0, 55.0
    j1 = _mk("J1", "connector", 8.0, 6.0, fixed=True, edge="left", pads=_ic(8, 6, 4))
    u1 = _mk("U1", "power_switch", 4.0, 4.0, power=1.6, pads=_ic(4, 4, 4))
    l1 = _mk("L1", "inductor", 8.0, 6.0, pads=_pads(8, 6))
    u2 = _mk("U2", "mcu", 6.0, 6.0, pads=_ic(6, 6, 6))
    comps = [
        j1,
        u1,
        l1,
        u2,
        _mk("C1", "input_cap", 3.2, 2.5),
        _mk("C2", "input_cap", 3.2, 2.5),
        _mk("C3", "output_cap", 3.2, 2.5),
        _mk("C4", "output_cap", 3.2, 2.5),
        _mk("C5", "decap", 1.6, 0.8),
        _mk("C6", "decap", 1.6, 0.8),
        _mk("R1", "analog", 1.6, 0.8),
        _mk("R2", "analog", 1.6, 0.8),
    ]
    nets = [
        Net("VIN", "power", (("J1", "1"), ("C1", "1"), ("C2", "1"), ("U1", "1"))),
        Net("SW", "power", (("U1", "2"), ("L1", "1"))),
        Net("VOUT", "power", (("L1", "2"), ("C3", "1"), ("C4", "1"), ("U2", "1"))),
        Net("FB", "analog", (("L1", "2"), ("R1", "1"), ("R2", "1"), ("U2", "2"))),
        Net("GND", "ground", (("J1", "2"), ("C1", "2"), ("C2", "2"), ("C3", "2"), ("C4", "2"), ("U1", "4"))),
        Net("VDD", "power", (("C3", "1"), ("C5", "1"), ("C6", "1"), ("U2", "1"))),
        Net("UART", "digital", (("U2", "3"), ("J1", "3"))),
    ]
    out.append(_scenario("buck", bw, bh, comps, nets, [], {"J1": (5.0, 27.5, 0)}))

    # --- 3) RS485 isolated interface -------------------------------------
    bw, bh = 70.0, 45.0
    j1 = _mk("J1", "connector", 7.0, 5.0, fixed=True, edge="left", pads=_ic(7, 5, 4))
    j2 = _mk("J2", "connector", 7.0, 5.0, fixed=True, edge="right", pads=_ic(7, 5, 4))
    comps = [
        j1,
        j2,
        _mk("U1", "mcu", 6.0, 6.0, pads=_ic(6, 6, 6)),
        _mk("U2", "analog", 5.0, 4.0, pads=_ic(5, 4, 4)),
        _mk("U3", "power_switch", 4.0, 4.0, power=0.4, pads=_ic(4, 4, 4)),
        _mk("C1", "decap", 1.6, 0.8),
        _mk("C2", "decap", 1.6, 0.8),
        _mk("C3", "input_cap", 2.0, 1.2),
        _mk("Y1", "crystal", 3.2, 2.5),
        _mk("R1", "analog", 1.6, 0.8),
    ]
    nets = [
        Net("VIN", "power", (("J1", "1"), ("C3", "1"), ("U3", "1"))),
        Net("VDD", "power", (("U3", "2"), ("C1", "1"), ("C2", "1"), ("U1", "1"))),
        Net("GND", "ground", (("J1", "2"), ("C3", "2"), ("C1", "2"), ("C2", "2"), ("U1", "4"))),
        Net("A", "analog", (("U2", "1"), ("J2", "1"), ("R1", "1"))),
        Net("B", "analog", (("U2", "2"), ("J2", "2"), ("R1", "2"))),
        Net("RXD", "digital", (("U2", "3"), ("U1", "2"))),
        Net("XTAL", "analog", (("Y1", "1"), ("U1", "3"))),
    ]
    out.append(
        _scenario(
            "rs485",
            bw,
            bh,
            comps,
            nets,
            [],
            {"J1": (4.5, 22.5, 0), "J2": (bw - 4.5, 22.5, 0)},
        )
    )

    # --- 4) Motor driver --------------------------------------------------
    bw, bh = 100.0, 60.0
    j1 = _mk("J1", "connector", 9.0, 7.0, fixed=True, edge="bottom", pads=_ic(9, 7, 4))
    comps = [
        j1,
        _mk("U1", "power_switch", 6.0, 6.0, power=2.2, pads=_ic(6, 6, 4)),
        _mk("U2", "mcu", 7.0, 7.0, pads=_ic(7, 7, 8)),
        _mk("L1", "inductor", 7.0, 5.0),
        _mk("C1", "input_cap", 4.0, 3.0),
        _mk("C2", "input_cap", 4.0, 3.0),
        _mk("C3", "decap", 1.6, 0.8),
        _mk("C4", "decap", 1.6, 0.8),
        _mk("R1", "analog", 2.0, 1.0),
        _mk("D1", "analog", 3.0, 2.0),
    ]
    nets = [
        Net("VIN", "power", (("J1", "1"), ("C1", "1"), ("C2", "1"), ("U1", "1"))),
        Net("MOTOR_A", "power", (("U1", "2"), ("L1", "1"), ("J1", "3"))),
        Net("MOTOR_B", "power", (("U1", "3"), ("L1", "2"), ("J1", "4"))),
        Net("GND", "ground", (("J1", "2"), ("C1", "2"), ("C2", "2"), ("U1", "4"))),
        Net("VDD", "power", (("C3", "1"), ("C4", "1"), ("U2", "1"))),
        Net("ISENSE", "analog", (("R1", "1"), ("U1", "4"), ("U2", "2"))),
        Net("PWM", "digital", (("U2", "3"), ("U1", "2"))),
        Net("FAULT", "digital", (("U2", "4"), ("U1", "3"))),
    ]
    out.append(_scenario("motor", bw, bh, comps, nets, [], {"J1": (5.0, 4.0, 0)}))

    # --- 5) Wireless sensor node -----------------------------------------
    bw, bh = 85.0, 60.0
    j1 = _mk("J1", "connector", 8.0, 6.0, fixed=True, edge="left", pads=_ic(8, 6, 4))
    ant = _mk("ANT1", "antenna", 10.0, 6.0, fixed=True, pads=_pads(10, 6))
    ax, ay = bw - 9.0, bh - 7.0
    keepout: Rect = (bw - 20.0, bh - 16.0, bw - 1.0, bh - 1.0)
    comps = [
        j1,
        ant,
        _mk("U1", "mcu", 7.0, 7.0, pads=_ic(7, 7, 8)),
        _mk("U2", "analog", 5.0, 5.0, pads=_ic(5, 5, 4)),
        _mk("U3", "power_switch", 4.0, 4.0, power=0.6, pads=_ic(4, 4, 4)),
        _mk("L1", "inductor", 6.0, 5.0),
        _mk("Y1", "crystal", 3.2, 2.5),
        _mk("C1", "input_cap", 2.0, 1.2),
        _mk("C2", "decap", 1.6, 0.8),
        _mk("C3", "decap", 1.6, 0.8),
        _mk("R1", "analog", 1.6, 0.8),
    ]
    nets = [
        Net("VIN", "power", (("J1", "1"), ("C1", "1"), ("U3", "1"))),
        Net("VDD", "power", (("U3", "2"), ("C2", "1"), ("C3", "1"), ("U1", "1"))),
        Net("GND", "ground", (("J1", "2"), ("C1", "2"), ("C2", "2"), ("C3", "2"), ("U1", "4"), ("ANT1", "2"))),
        Net("RF", "rf", (("U1", "5"), ("ANT1", "1"))),
        Net("AFE", "analog", (("U2", "1"), ("U1", "2"), ("R1", "1"))),
        Net("SENSOR", "analog", (("U2", "2"), ("J1", "3"))),
        Net("XTAL", "analog", (("Y1", "1"), ("U1", "3"))),
        Net("PWR_IN", "power", (("U3", "1"), ("L1", "1"))),
    ]
    out.append(
        _scenario(
            "wireless",
            bw,
            bh,
            comps,
            nets,
            [keepout],
            {"J1": (5.0, 30.0, 0), "ANT1": (ax, ay, 0)},
        )
    )

    # Sanity: fixed components must fit on the board and inside declared edges.
    for sc in out:
        for ref, comp in sc.components.items():
            if comp.fixed:
                assert ref in sc.base_placement, f"fixed {ref} without base placement in {sc.name}"
    return out
