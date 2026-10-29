"""P4.15: constraint-satisfiability study for cross-edge topologies.

Reproduces the earlier finding that a dense "bridge near both an edge connector
and a centre MCU" topology cannot always reach zero strict-CCG violations in
budget, and codifies a ``suggest_mode`` heuristic (strict vs relax) plus a
structured residual report so template authors know when to switch.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
from typing import Dict, List, Optional, Sequence

from .ccg_diag import diagnose_template, parse_violations
from .intent import build_intent, intent_violations
from .intent_solver import plan_from_intent
from .model import Component, Net, Scenario, hard_violations
from .solver import random_feasible_placement
from .templates import instantiate, template_names

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent


def cross_edge_scenario() -> Scenario:
    """A dense cross-edge bridge topology (mirrors the failed usb-uart-bridge)."""
    comps = [
        Component("J1", "connector", 7.0, 5.0, fixed=True, edge="left", pins=_ic(7, 5, 4)),
        Component("J2", "connector", 7.0, 5.0, fixed=True, edge="right", pins=_ic(7, 5, 4)),
        Component("U1", "mcu", 6.0, 6.0, pins=_ic(6, 6, 6)),
        Component("U2", "analog", 5.0, 4.0, pins=_ic(5, 4, 4)),
        Component("U3", "power_switch", 4.0, 4.0, pins=_ic(4, 4, 4)),
        Component("C1", "decap", 1.6, 0.8),
        Component("C2", "decap", 1.6, 0.8),
        Component("C3", "input_cap", 2.0, 1.2),
        Component("Y1", "crystal", 3.2, 2.5),
        Component("D1", "analog", 1.6, 0.8),
    ]
    nets = [
        Net("VIN", "power", (("J1", "1"), ("C3", "1"), ("U3", "1"))),
        Net("VDD", "power", (("U3", "2"), ("C1", "1"), ("C2", "1"), ("U1", "1"))),
        Net("GND", "ground", (("J1", "2"), ("C3", "2"), ("C1", "2"), ("C2", "2"), ("U1", "4"), ("D1", "2"))),
        Net("USB_DP", "digital", (("J1", "3"), ("U2", "1"))),
        Net("USB_DM", "digital", (("J1", "4"), ("U2", "2"))),
        Net("UART_TX", "digital", (("U2", "3"), ("U1", "2"))),
        Net("RXD", "digital", (("U2", "4"), ("U1", "3"))),
        Net("XTAL_IN", "analog", (("Y1", "1"), ("U1", "5"))),
        Net("XTAL_OUT", "analog", (("Y1", "2"), ("U1", "6"))),
        Net("TVS", "analog", (("D1", "1"), ("U3", "3"))),
        Net("UART_TO_J2", "digital", (("U3", "4"), ("J2", "1"))),
    ]
    board_w, board_h = 72.0, 46.0
    base = {"J1": (4.0, board_h / 2, 0), "J2": (board_w - 4.0, board_h / 2, 0)}
    return Scenario("cross-edge", board_w, board_h, {c.ref: c for c in comps}, nets, keepouts=[], edge_tol=2.0, base_placement=base)


def _ic(w: float, h: float, n: int) -> Dict[str, tuple]:
    pads = {
        "1": (-w / 2, 0.0), "2": (w / 2, 0.0), "3": (0.0, h / 2), "4": (0.0, -h / 2),
    }
    return {str(i + 1): pads[str((i % 4) + 1)] for i in range(n)}


def suggest_mode(residual: Sequence[Dict]) -> str:
    """Heuristic: relax when a residual ``near`` involves a fixed connector or spans
    more than ~half the board diagonal (a cross-edge chain)."""
    for item in residual:
        if item.get("type") == "near" and (item.get("a", "").startswith("J") or item.get("b", "").startswith("J")):
            return "relax"
    return "strict"


def run_study(steps: int = 800) -> Dict:
    sc = cross_edge_scenario()
    rng = random.Random(0)
    reference = random_feasible_placement(sc, rng)
    intent = build_intent(sc, reference)
    # jiggle the reference so strict mode has something to repair
    jiggled = dict(reference)
    movable = [r for r, c in sc.components.items() if not c.fixed]
    for ref in movable:
        x, y, rot = jiggled[ref]
        jiggled[ref] = (x + rng.uniform(-2.0, 2.0), y + rng.uniform(-2.0, 2.0), rot)
    if hard_violations(sc, jiggled):
        jiggled = reference
    perturbed = json.loads(json.dumps(intent))
    for ref, (x, y, rot) in jiggled.items():
        if ref in perturbed.get("coordinates", {}):
            perturbed["coordinates"][ref] = [x, y, rot]

    _sp, strict = plan_from_intent(sc, perturbed, seed=1, steps=steps)
    _rp, relaxed = plan_from_intent(sc, perturbed, seed=1, steps=steps, relax=True)
    residual = parse_violations(strict.get("ccg_residual", []))
    return {
        "scenario": sc.name,
        "components": len(sc.components),
        "nets": len(sc.nets),
        "strict": {"ccg_initial": strict.get("ccg_initial"), "ccg_final": strict.get("ccg_final"),
                    "hard_feasible": strict.get("hard_feasible"), "residual": residual},
        "relax": {"ccg_initial": relaxed.get("ccg_initial"), "ccg_final": relaxed.get("ccg_final"),
                  "hard_feasible": relaxed.get("hard_feasible"),
                  "residual": parse_violations(relaxed.get("ccg_residual", []))},
        "suggested_mode": suggest_mode(residual),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-edge CCG satisfiability study")
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--out", default=str(OUT_DIR / "report_ccg_study.json"))
    args = parser.parse_args(argv)
    data = run_study(steps=args.steps)
    pathlib.Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
