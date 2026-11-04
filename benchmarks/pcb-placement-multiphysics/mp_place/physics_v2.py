"""Realistic offline multi-physics simulator (the P2 "truth" model).

This module is the P2 replacement for :class:`mp_place.objective.PhysicsSimulator`.
It keeps the same calling contract (``score_features`` / ``score``) but replaces
the flat weighted sum with formula-shaped physics: PCB power-loop inductance,
PDN impedance, thermal spreading, near/far field coupling, escape routing and
wire length, plus a few mild nonlinear cross terms.

Physics sketch.  All scale factors are *hidden* and drawn deterministically from
``scenario.name`` + ``seed`` (a stable BLAKE2 digest feeds a SplitMix64 stream;
Python's ``hash()`` is never used, so scores are reproducible across processes
and ``PYTHONHASHSEED`` values):

* Power-loop inductance: a current loop is approximated by a square with
  diagonal ``D = loop * board_diagonal`` mm; its area/perimeter ratio is
  ``A/P = D / (4*sqrt(2))``.  A thin-wire estimate is
  ``L ~ mu0 * (A/P) * ln(1 + 8*(A/P)/a)`` with effective trace width ``a``.
  Mutual coupling grows the estimate as ``(1 + k_m * loop)``.
* PDN impedance: ``Z ~ Z_floor + k_z * decap / N_parallel**p`` where the
  feature ``capcount = 1/N_parallel`` carries the parallel decap count and
  ``decap`` is the normalised cap-to-load distance (current-path length).
* Thermal spreading: ``dT ~ k_t * thermal**e``; the feature already has the
  physical ``P / A_copper`` form, and ``e > 1`` models the extra rise from
  spreading resistance / radiation at high power density.
* Field coupling: ``H ~ exp(-d/lambda) + w_nf / (1 + (d/d_nf)**2)`` where
  ``d = analog * board_diagonal`` is the aggressor-to-sensitive-block gap
  (``analog`` is a distance, so small is bad).  Radiation grows with loop area.
* Escape routing: ``E ~ density / max(1 - escape, floor)``, i.e. local density
  divided by the free board-edge margin, plus a local-congestion term.
* Wire length and keepout usage remain weighted linear terms.

The simulator is pure standard library and only reads the ten keys of
:data:`mp_place.features.FEATURE_NAMES`; it never touches the placement model.
"""

from __future__ import annotations

import hashlib
import math
from typing import Dict, Sequence, Tuple

from .features import FEATURE_NAMES, extract_features
from .model import Placement, Scenario

MODEL_VERSION = "physics_v2.0"

# mu0 expressed in nH/mm: 4*pi*1e-7 H/m * 1e9 nH/H * 1e-3 m/mm.
_MU0_NH_PER_MM = 4.0 * math.pi * 1e-1
# Normalisation so that a typical short loop contributes O(1) to the cost.
_REF_LOOP_INDUCTANCE_NH = 25.0
# Square-loop geometry: A/P = D / (4*sqrt(2)) for a diagonal span D.
_SQUARE_LOOP_SPAN_TO_AOP = 4.0 * math.sqrt(2.0)
# Thin-wire loop shape factor inside the logarithm.
_LOG_SHAPE_FACTOR = 8.0
# Feature values above this are clipped; real features are ~[0, 1].
_MAX_FEATURE = 1.0e6

_MASK64 = (1 << 64) - 1
_GOLDEN64 = 0x9E3779B97F4A7C15


def _stable_seed(name: str, seed: int) -> int:
    """Process-independent 64-bit seed from ``(scenario name, seed)``.

    ``hash()`` is deliberately avoided: it is salted per process for strings, so
    it would make the hidden coefficients irreproducible across runs.
    """
    payload = f"physics_v2|{name}|{int(seed)}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


class _SplitMix64:
    """Tiny deterministic PRNG (stable across Python versions and platforms)."""

    __slots__ = ("state",)

    def __init__(self, seed: int):
        self.state = seed & _MASK64

    def next_u64(self) -> int:
        self.state = (self.state + _GOLDEN64) & _MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return z ^ (z >> 31)

    def random(self) -> float:
        """Uniform float in [0, 1) with 53 random bits."""
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()


# (name, low, high) drawn in this exact order; order is part of the model.
_COEFF_SPEC: Tuple[Tuple[str, float, float], ...] = (
    # --- wire length / generic -------------------------------------------------
    ("wire_gain", 0.30, 0.90),
    # --- power-loop inductance -------------------------------------------------
    ("loop_gain", 0.35, 0.95),
    ("trace_width_mm", 0.15, 0.50),
    ("loop_mutual", 0.20, 1.00),
    # --- PDN impedance ---------------------------------------------------------
    ("pdn_gain", 3.0, 9.0),
    ("pdn_floor", 0.010, 0.060),
    ("pdn_parallel_exp", 0.60, 0.95),
    ("pdn_quad", 0.30, 1.50),
    # --- thermal spreading -----------------------------------------------------
    ("thermal_gain", 12.0, 45.0),
    ("thermal_exp", 1.00, 1.28),
    # --- field coupling --------------------------------------------------------
    ("couple_amp", 1.6, 3.6),
    ("couple_lambda_mm", 2.5, 7.0),
    ("couple_near_weight", 0.05, 0.30),
    ("couple_near_mm", 0.8, 2.5),
    ("couple_loop_boost", 0.20, 1.20),
    # --- escape routing / congestion ------------------------------------------
    ("escape_gain", 0.90, 2.20),
    ("escape_margin_floor", 0.050, 0.120),
    ("cong_gain", 0.35, 1.20),
    # --- keepout usage ---------------------------------------------------------
    ("keepout_penalty", 20.0, 55.0),
    ("keepout_quad", 40.0, 120.0),
    # --- mild nonlinear cross terms -------------------------------------------
    ("decap_quad", 0.50, 2.00),
    ("pdn_loop_cross", 0.50, 1.50),
    ("wire_quad", 0.20, 0.80),
    ("cong_quad", 0.30, 1.20),
)

_BREAKDOWN_KEYS: Tuple[str, ...] = (
    "wirelength",
    "loop_inductance",
    "pdn_impedance",
    "thermal",
    "field_coupling",
    "escape",
    "congestion",
    "keepout",
    "nonlinear",
)


def _nonneg(value: float, what: str) -> float:
    """Coerce a feature to a finite non-negative float (clipped for robustness)."""
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"feature {what!r} is not finite: {value!r}")
    if v <= 0.0:
        return 0.0
    return v if v <= _MAX_FEATURE else _MAX_FEATURE


class PhysicsSimulatorV2:
    """Offline realistic multi-physics scorer with hidden per-scenario coefficients.

    Parameters
    ----------
    scenario:
        Board family; only ``scenario.name`` (plus ``board_w``/``board_h`` for
        millimetre scaling) is used, so scoring is independent of placement.
    seed:
        Hidden-coefficient seed.  ``(scenario.name, seed)`` fully determines the
        coefficients; identical inputs give bit-identical scores.

    Contract
    --------
    * ``score_features(f)`` accepts a dict with the ten feature keys and returns
      a non-negative float (lower is better).
    * ``score(pl)`` extracts features from a placement and scores them.
    * ``breakdown(f)`` returns the per-physics cost contributions.
    * ``diagnostics(f)`` returns the physical intermediates (nH, mm, AU).
    """

    _version = MODEL_VERSION

    def __init__(self, scenario: Scenario, seed: int = 0):
        self.scenario = scenario
        self.seed = int(seed)
        self.diagonal_mm = math.hypot(float(scenario.board_w), float(scenario.board_h))
        rng = _SplitMix64(_stable_seed(scenario.name, self.seed))
        self.coeffs: Dict[str, float] = {
            name: rng.uniform(low, high) for name, low, high in _COEFF_SPEC
        }

    # -- validation ---------------------------------------------------------
    @staticmethod
    def _checked(f: Dict[str, float]) -> Dict[str, float]:
        if not isinstance(f, dict):
            raise TypeError(f"features must be a dict, got {type(f).__name__}")
        missing = [name for name in FEATURE_NAMES if name not in f]
        if missing:
            raise KeyError(f"missing feature keys: {missing}")
        return {name: _nonneg(f[name], name) for name in FEATURE_NAMES}

    # -- physics intermediates ---------------------------------------------
    def _physical(self, f: Dict[str, float]) -> Dict[str, float]:
        """Map the ten features to physical intermediates (hidden coefficients used)."""
        c = self.coeffs
        loop = f["loop"]
        decap = f["decap"]
        thermal = f["thermal"]
        analog = f["analog"]
        density = f["density"]
        congestion = f["congestion"]
        escape = f["escape"]
        keepout = f["keepout"]
        capcount = f["capcount"]

        # Power-loop inductance: square-equivalent loop area / perimeter, then a
        # thin-wire inductance estimate.
        loop_span_mm = loop * self.diagonal_mm
        area_over_perimeter_mm = loop_span_mm / _SQUARE_LOOP_SPAN_TO_AOP
        inductance_nh = (
            _MU0_NH_PER_MM
            * area_over_perimeter_mm
            * math.log1p(_LOG_SHAPE_FACTOR * area_over_perimeter_mm / c["trace_width_mm"])
        )

        # PDN: decoupling distance divided by effective parallel-cap count.
        n_parallel_decaps = 1.0 / max(capcount, 1.0e-3)
        pdn_impedance = c["pdn_floor"] + c["pdn_gain"] * (
            decap * n_parallel_decaps ** (-c["pdn_parallel_exp"])
        )

        # Thermal: the feature is already power / copper_area; add spreading /
        # radiation nonlinearity through a fractional power.
        thermal_rise = c["thermal_gain"] * thermal ** c["thermal_exp"]

        # Field coupling: far field decays exponentially with the gap; a small
        # near-field capacitive term keeps very close blocks from saturating.
        coupling_gap_mm = analog * self.diagonal_mm
        far_field = math.exp(-coupling_gap_mm / c["couple_lambda_mm"])
        near_field = 1.0 / (1.0 + (coupling_gap_mm / c["couple_near_mm"]) ** 2)
        coupling_field = c["couple_amp"] * (
            far_field + c["couple_near_weight"] * near_field
        )

        # Escape routing: density divided by free edge margin.
        edge_margin = max(1.0 - min(escape, 1.0), c["escape_margin_floor"])

        return {
            "loop_span_mm": loop_span_mm,
            "area_over_perimeter_mm": area_over_perimeter_mm,
            "inductance_nh": inductance_nh,
            "parallel_decaps": n_parallel_decaps,
            "pdn_impedance": pdn_impedance,
            "thermal_rise": thermal_rise,
            "coupling_gap_mm": coupling_gap_mm,
            "coupling_field": coupling_field,
            "edge_margin": edge_margin,
            "density": density,
            "congestion": congestion,
            "keepout": keepout,
            "hpwl": f["hpwl"],
            "loop": loop,
            "thermal": thermal,
        }

    # -- public API ---------------------------------------------------------
    def _components(self, f: Dict[str, float]) -> Dict[str, float]:
        c = self.coeffs
        f = self._checked(f)
        p = self._physical(f)

        # 1) Wire length (resistive drop / routed copper).
        wire_cost = c["wire_gain"] * p["hpwl"]

        # 2) Loop inductance in nH, normalised and augmented by mutual coupling.
        loop_cost = (
            c["loop_gain"]
            * (p["inductance_nh"] / _REF_LOOP_INDUCTANCE_NH)
            * (1.0 + c["loop_mutual"] * p["loop"])
        )

        # 3) PDN impedance, with a mild high-frequency penalty on its own value.
        pdn_cost = p["pdn_impedance"] * (1.0 + c["pdn_quad"] * p["pdn_impedance"])

        # 4) Thermal spreading (already nonlinear in power density).
        thermal_cost = p["thermal_rise"]

        # 5) Field coupling; a bigger current loop radiates more efficiently.
        coupling_cost = p["coupling_field"] * (1.0 + c["couple_loop_boost"] * p["loop"])

        # 6) Escape routing plus local congestion.
        escape_cost = c["escape_gain"] * p["density"] / p["edge_margin"]
        congestion_cost = c["cong_gain"] * p["congestion"] * (
            1.0 + c["cong_quad"] * p["congestion"]
        )

        # 7) Keepout usage: near-hard penalty, steepened for large intrusions.
        keepout_cost = c["keepout_penalty"] * p["keepout"] * (
            1.0 + c["keepout_quad"] * p["keepout"]
        )

        # 8) Explicit mild nonlinear cross terms (non-separable effects).
        nonlinear_cost = (
            c["decap_quad"] * f["decap"] ** 1.5
            + c["pdn_loop_cross"] * p["loop"] * p["pdn_impedance"]
            + c["wire_quad"] * p["hpwl"] ** 2
        )

        return {
            "wirelength": wire_cost,
            "loop_inductance": loop_cost,
            "pdn_impedance": pdn_cost,
            "thermal": thermal_cost,
            "field_coupling": coupling_cost,
            "escape": escape_cost,
            "congestion": congestion_cost,
            "keepout": keepout_cost,
            "nonlinear": nonlinear_cost,
        }

    def score_features(self, f: Dict[str, float]) -> float:
        """Return the non-negative "truth" cost of a feature dict (lower is better)."""
        total = math.fsum(self._components(f).values())
        return max(0.0, total)

    def score(self, pl: Placement) -> float:
        """Extract features from ``pl`` and return the truth cost."""
        return self.score_features(extract_features(self.scenario, pl))

    def breakdown(self, f: Dict[str, float]) -> Dict[str, float]:
        """Per-physics cost contributions (all non-negative); ``total`` last."""
        parts = self._components(f)
        out: Dict[str, float] = {key: parts[key] for key in _BREAKDOWN_KEYS}
        out["total"] = max(0.0, math.fsum(out.values()))
        return out

    def diagnostics(self, f: Dict[str, float]) -> Dict[str, float]:
        """Physical intermediates behind a score (mm, nH, arbitrary units)."""
        f = self._checked(f)
        p = self._physical(f)
        return {
            "board_diagonal_mm": self.diagonal_mm,
            "loop_span_mm": p["loop_span_mm"],
            "area_over_perimeter_mm": p["area_over_perimeter_mm"],
            "loop_inductance_nh": p["inductance_nh"],
            "parallel_decaps": p["parallel_decaps"],
            "pdn_impedance_au": p["pdn_impedance"],
            "thermal_rise_au": p["thermal_rise"],
            "coupling_gap_mm": p["coupling_gap_mm"],
            "coupling_field_au": p["coupling_field"],
            "edge_margin": p["edge_margin"],
        }

    # -- introspection helpers (useful for reports / debugging) -------------
    @classmethod
    def coefficient_names(cls) -> Sequence[str]:
        return tuple(name for name, _low, _high in _COEFF_SPEC)

    def coefficients(self) -> Dict[str, float]:
        """Copy of the hidden coefficients (read-only use in reports/tests)."""
        return dict(self.coeffs)
