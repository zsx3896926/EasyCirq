"""Objectives and the offline multi-physics "simulator" (P1 truth model).

The simulator is a deterministic surrogate for a real multi-physics stack
(SPICE loop inductance, PDN impedance, thermal spreading, EM coupling).  It is
NOT a real field solver: its job in P1 is to provide a consistent, hidden
ground truth so we can measure whether a multi-physics objective finds layouts
that are genuinely better than HPWL-driven ones.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import Dict, List, Sequence

from .features import FEATURE_NAMES, extract_features, feature_vector
from .model import Placement, Scenario


def _seed_from(name: str, seed: int) -> int:
    return zlib.crc32(name.encode("utf-8")) ^ (seed * 2654435761) & 0xFFFFFFFF


class PhysicsSimulator:
    """Offline pseudo-physics simulator with hidden per-scenario coefficients."""

    def __init__(self, scenario: Scenario, seed: int = 0):
        rng = random.Random(_seed_from(scenario.name, seed))
        self.scenario = scenario
        self.weights = {
            "hpwl": rng.uniform(0.4, 1.2),
            "decap": rng.uniform(1.5, 3.5),
            "loop": rng.uniform(2.0, 4.5),
            "analog": rng.uniform(2.0, 4.0),
            "thermal": rng.uniform(0.5, 1.5),
            "escape": rng.uniform(0.3, 1.2),
            "congestion": rng.uniform(0.2, 0.8),
            "capcount": rng.uniform(0.3, 1.2),
        }
        self.keepout_penalty = 25.0

    # -- deterministic pseudo-physics -------------------------------------
    def _raw(self, f: Dict[str, float]) -> float:
        w = self.weights
        analog_soft = math.exp(-8.0 * f["analog"])  # proximity risk ~1 when close
        thermal_scaled = 50.0 * f["thermal"]  # bring copper/power term to O(1)
        value = (
            w["hpwl"] * f["hpwl"]
            + w["decap"] * f["decap"]
            + w["loop"] * f["loop"]
            + w["analog"] * analog_soft
            + w["thermal"] * thermal_scaled
            + w["escape"] * f["escape"]
            + w["congestion"] * f["congestion"]
            + w["capcount"] * f["capcount"]
            + self.keepout_penalty * f["keepout"]
        )
        # mild nonlinearity so a purely linear proxy cannot be perfect
        return value + 0.35 * (f["decap"] ** 1.5) + 0.2 * (f["loop"] ** 1.5)

    def score_features(self, f: Dict[str, float]) -> float:
        return self._raw(f)

    def score(self, pl: Placement) -> float:
        return self._raw(extract_features(self.scenario, pl))


class ProxyObjective:
    """Hand-designed multi-physics objective with nominal (not hidden) weights."""

    name = "multiphysics_proxy"

    def __init__(self, scenario: Scenario):
        self.scenario = scenario

    def cost_features(self, f: Dict[str, float]) -> float:
        analog_soft = math.exp(-8.0 * f["analog"])
        return (
            1.0 * f["hpwl"]
            + 3.0 * f["decap"]
            + 4.0 * f["loop"]
            + 3.0 * analog_soft
            + 1.0 * 50.0 * f["thermal"]
            + 1.0 * f["escape"]
            + 0.5 * f["congestion"]
            + 1.0 * f["capcount"]
            + 25.0 * f["keepout"]
        )

    def cost(self, pl: Placement) -> float:
        return self.cost_features(extract_features(self.scenario, pl))


class HPWLObjective:
    name = "hpwl"

    def __init__(self, scenario: Scenario):
        self.scenario = scenario

    def cost_features(self, f: Dict[str, float]) -> float:
        return f["hpwl"]

    def cost(self, pl: Placement) -> float:
        return extract_features(self.scenario, pl)["hpwl"]


class OracleObjective:
    """Not deployable: the hidden simulator itself, as an upper-bound reference."""

    name = "oracle(truth)"

    def __init__(self, scenario: Scenario, sim: PhysicsSimulator):
        self.scenario = scenario
        self.sim = sim

    def cost_features(self, f: Dict[str, float]) -> float:
        return self.sim.score_features(f)

    def cost(self, pl: Placement) -> float:
        return self.sim.score(pl)


class RidgeModel:
    """Tiny ridge regressor (standardised features, normal equations)."""

    def __init__(self, lam: float = 1e-3):
        self.lam = lam
        self.mean: List[float] = []
        self.std: List[float] = []
        self.w: List[float] = []

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> "RidgeModel":
        n, d = len(X), len(X[0])
        self.mean = [sum(X[i][j] for i in range(n)) / n for j in range(d)]
        self.std = []
        for j in range(d):
            var = sum((X[i][j] - self.mean[j]) ** 2 for i in range(n)) / n
            self.std.append(math.sqrt(var) or 1.0)
        A = [[0.0] * (d + 1) for _ in range(d + 1)]
        b = [0.0] * (d + 1)
        for i in range(n):
            row = [1.0] + [(X[i][j] - self.mean[j]) / self.std[j] for j in range(d)]
            for a in range(d + 1):
                b[a] += row[a] * y[i]
                for c in range(d + 1):
                    A[a][c] += row[a] * row[c]
        for a in range(d + 1):
            A[a][a] += self.lam if a > 0 else 1e-9
        # Gaussian elimination with partial pivoting.
        for col in range(d + 1):
            pivot = max(range(col, d + 1), key=lambda r: abs(A[r][col]))
            if abs(A[pivot][col]) < 1e-12:
                continue
            A[col], A[pivot] = A[pivot], A[col]
            b[col], b[pivot] = b[pivot], b[col]
            pv = A[col][col]
            for r in range(col + 1, d + 1):
                factor = A[r][col] / pv
                if factor == 0.0:
                    continue
                for c in range(col, d + 1):
                    A[r][c] -= factor * A[col][c]
                b[r] -= factor * b[col]
        self.w = [0.0] * (d + 1)
        for r in range(d, -1, -1):
            s = b[r] - sum(A[r][c] * self.w[c] for c in range(r + 1, d + 1))
            self.w[r] = s / A[r][r] if abs(A[r][r]) > 1e-12 else 0.0
        return self

    def predict(self, x: Sequence[float]) -> float:
        z = [1.0] + [(x[j] - self.mean[j]) / self.std[j] for j in range(len(x))]
        return sum(w * v for w, v in zip(self.w, z))


class SurrogateObjective:
    """Learned fast scorer: replaces the simulator inside the optimisation loop."""

    name = "surrogate"

    def __init__(self, scenario: Scenario, model: RidgeModel):
        self.scenario = scenario
        self.model = model

    def cost_features(self, f: Dict[str, float]) -> float:
        return self.model.predict(feature_vector(f))

    def cost(self, pl: Placement) -> float:
        return self.model.predict(feature_vector(extract_features(self.scenario, pl)))


def build_dataset(scenario: Scenario, simulator: PhysicsSimulator, placements: Sequence[Placement]):
    X, y = [], []
    for pl in placements:
        f = extract_features(scenario, pl)
        X.append(feature_vector(f))
        y.append(simulator.score_features(f))
    return X, y


def correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson correlation (0.0 when degenerate)."""
    n = len(a)
    if n == 0:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rank correlation via average ranks."""
    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    return correlation(ranks(a), ranks(b))


def r_squared(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    n = len(y_true)
    if n == 0:
        return 0.0
    mean = sum(y_true) / n
    sst = sum((y - mean) ** 2 for y in y_true)
    if sst <= 0:
        return 0.0
    sse = sum((y - p) ** 2 for y, p in zip(y_true, y_pred))
    return 1.0 - sse / sst
