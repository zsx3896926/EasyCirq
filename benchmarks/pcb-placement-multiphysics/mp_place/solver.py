"""Feasibility-aware simulated annealing over placements (no LLM involved).

The solver only ever visits placements that satisfy all hard constraints, so the
comparison between objectives is about the soft multi-physics quality, not about
who can repair overlaps.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .model import Placement, Scenario, bbox, hard_violations, rect_overlap_area


def _fits_inside(sc: Scenario, comp, x: float, y: float, rot: int) -> bool:
    b = bbox(comp, x, y, rot)
    return b[0] >= -1e-9 and b[1] >= -1e-9 and b[2] <= sc.board_w + 1e-9 and b[3] <= sc.board_h + 1e-9


def feasible_partial(sc: Scenario, pl: Placement) -> bool:
    """Check the placed subset only (used while building a placement)."""
    boxes = {}
    for ref, (x, y, rot) in pl.items():
        comp = sc.components[ref]
        if rot % 360 not in comp.rotations:
            return False
        b = bbox(comp, x, y, rot)
        if not _fits_inside(sc, comp, x, y, rot):
            return False
        if comp.fixed:
            bx, by, _ = sc.base_placement.get(ref, (x, y, 0))
            if abs(bx - x) > 1e-9 or abs(by - y) > 1e-9:
                return False
        if comp.edge is not None:
            if comp.edge == "left":
                dist = b[0]
            elif comp.edge == "right":
                dist = sc.board_w - b[2]
            elif comp.edge == "top":
                dist = sc.board_h - b[3]
            else:
                dist = b[1]
            if dist > sc.edge_tol + 1e-9:
                return False
        boxes[ref] = b
    refs = sorted(boxes)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            if rect_overlap_area(boxes[refs[i]], boxes[refs[j]]) > 1e-6:
                return False
    for ref, b in boxes.items():
        if sc.components[ref].kind in {"antenna", "rf"}:
            continue
        for ko in sc.keepouts:
            if rect_overlap_area(b, ko) > 1e-6:
                return False
    return True


def random_feasible_placement(sc: Scenario, rng: random.Random, max_tries: int = 500) -> Placement:
    pl: Placement = {}
    for ref, comp in sc.components.items():
        if comp.fixed:
            pl[ref] = sc.base_placement[ref]
    order = sorted(
        [r for r, c in sc.components.items() if not c.fixed],
        key=lambda r: -(sc.components[r].w * sc.components[r].h),
    )
    for ref in order:
        comp = sc.components[ref]
        placed = False
        for _ in range(max_tries):
            rot = rng.choice(comp.rotations)
            r = rot % 360
            w, h = (comp.h, comp.w) if r in (90, 270) else (comp.w, comp.h)
            margin = 0.5
            x = rng.uniform(w / 2 + margin, sc.board_w - w / 2 - margin)
            y = rng.uniform(h / 2 + margin, sc.board_h - h / 2 - margin)
            trial = dict(pl)
            trial[ref] = (x, y, rot)
            if feasible_partial(sc, trial):
                pl = trial
                placed = True
                break
        if not placed:
            raise RuntimeError(f"could not place {ref} in scenario {sc.name}")
    return pl


ObjectiveFn = Callable[[Placement], float]


class Annealer:
    """Simulated annealing over translate / swap moves with hard-feasibility gate."""

    def __init__(
        self,
        sc: Scenario,
        cost: ObjectiveFn,
        seed: int = 0,
        steps: int = 2000,
        t0: float = 0.08,
        t1: float = 0.002,
        step_mm: float = 6.0,
    ):
        self.sc = sc
        self.cost = cost
        self.rng = random.Random(seed)
        self.steps = steps
        self.t0 = t0
        self.t1 = t1
        self.step_mm = step_mm
        self.movable = [r for r, c in sc.components.items() if not c.fixed]

    def _move(self, pl: Placement) -> Optional[Placement]:
        trial = dict(pl)
        r = self.rng.random()
        if r < 0.85 or len(self.movable) < 2:
            ref = self.rng.choice(self.movable)
            comp = self.sc.components[ref]
            x, y, rot = trial[ref]
            sigma = self.step_mm * (0.3 + 0.7 * self.rng.random())
            x += self.rng.gauss(0.0, sigma)
            y += self.rng.gauss(0.0, sigma)
            if len(comp.rotations) > 1 and self.rng.random() < 0.2:
                rot = self.rng.choice(comp.rotations)
            trial[ref] = (min(max(x, 0.0), self.sc.board_w), min(max(y, 0.0), self.sc.board_h), rot)
        else:
            a, b = self.rng.sample(self.movable, 2)
            if self.sc.components[a].rotations != self.sc.components[b].rotations:
                return None
            trial[a], trial[b] = trial[b], trial[a]
        return trial

    def run(self) -> Tuple[Placement, float, List[float]]:
        cur = random_feasible_placement(self.sc, self.rng)
        cur_cost = self.cost(cur)
        best, best_cost = dict(cur), cur_cost
        trace = [best_cost]
        for i in range(self.steps):
            frac = i / max(1, self.steps - 1)
            temp = self.t0 * ((self.t1 / self.t0) ** frac)
            trial = self._move(cur)
            if trial is None or not feasible_partial(self.sc, trial):
                trace.append(best_cost)
                continue
            t_cost = self.cost(trial)
            delta = t_cost - cur_cost
            if delta <= 0 or self.rng.random() < math.exp(-delta / max(temp, 1e-12)):
                cur, cur_cost = trial, t_cost
                if t_cost < best_cost:
                    best, best_cost = dict(trial), t_cost
            trace.append(best_cost)
        return best, best_cost, trace


def run_annealer(sc: Scenario, cost: ObjectiveFn, seed: int, steps: int) -> Placement:
    pl, _cost, _trace = Annealer(sc, cost, seed=seed, steps=steps).run()
    return pl
