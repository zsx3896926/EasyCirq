"""P2.13: layer- and net-class-aware offline multi-physics simulator (physics v3).

Why a v3?
---------
``PhysicsSimulatorV2`` treats the board as a single effective copper layer:
loop inductance depends only on the loop span, the PDN term ignores vias and
layer stacking, thermal spreading uses one copper area, and field coupling uses
one ``analog`` distance for every aggressor class.  Real PCBs are not like that:
a 4-layer stack-up has parallel power/ground planes, 2 oz copper spreads heat
better, every net hop needs a via, and RF lines are far more sensitive to a
switching regulator than a slow digital trace.

This module keeps the v2 calling contract (``score_features`` / ``score``,
lower is better, hidden coefficients from ``scenario.name`` + ``seed``) and
refines the model term by term:

* **Layer / copper aware power-loop inductance** -- the v2 square-loop area/
  perimeter + thin-wire estimate is reduced by parallel plane pairs
  ``1 / (1 + k_plane * (layers - 1))`` and by copper thickness (effective trace
  width ~ ``sqrt(t/1oz)``); a via-inductance term ``L_via ~ mu0*h/(2*pi) *
  (ln(4h/d) - 1)`` is added for the estimated number of power/ground via hops,
  divided by the parallel return paths of the stack-up.
* **PDN impedance with decoupling parallelism and vias** -- decap distance and
  parallel-cap count stay (``Z ~ decap / N_parallel**p``), the plane term is
  divided by layer count, and a via term ``Z_via ~ L_via / (N_caps * layers)``
  is added.  Copper thickness lowers the plane resistance.
* **Thermal spreading scaled by copper area x layers** -- ``dT ~ P / (A_cu *
  layers * t)``; more layers / thicker copper keep the same layout cooler.
* **Net-class-aware coupling** -- separate analog / RF / digital aggressor
  distances with different sensitivity weights and exponential length scales
  (RF far more sensitive than digital); sensitive signal spans (analog + RF)
  add a class-aware "signal loop area" penalty; extra layers add return-path
  shielding.
* Deterministic hidden coefficients -- BLAKE2b("physics_v3|name|seed") drives a
  SplitMix64 stream (no Python ``hash()``), so scores are reproducible across
  processes and ``PYTHONHASHSEED`` values.

Layers and copper thickness
---------------------------
``PhysicsSimulatorV3(scenario, seed=0, layers=None, copper_thickness_mm=None)``.
``layers`` is read from the scenario when available (attributes ``layers``,
``num_layers`` or ``copper_layers``; EasyCirq dumps expose ``copperLayers``) and
defaults to 2.  ``copper_thickness_mm`` defaults to 1 oz = 0.035 mm (2 oz =
0.070 mm).  More layers and thicker copper reduce the score for the same
placement (monotone, tested).

Backward compatibility
----------------------
``score_features(f)`` accepts the original ten :data:`FEATURE_NAMES` (exactly
like v2) and derives the v3-only inputs (RF / digital gaps, via pressure, ...)
from the scenario.  ``score(pl)`` uses the richer :func:`extract_features_v3`
and is exactly ``score_features(extract_features_v3(...))``.

The module also runs the v2-vs-v3 comparison (five templates + three real
EasyCirq boards, random feasible layouts + original layouts), finds placements
that v2 likes but v3 dislikes, explains them via per-term cost deltas, and
writes ``report_physics_v3.md`` / ``report_physics_v3.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import statistics
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .dataset import iter_layouts
from .features import FEATURE_NAMES, extract_features
from .model import (
    Placement,
    Scenario,
    bbox,
    comp_pad_distance,
    hard_violations,
    pad_position,
)
from .objective import correlation, spearman
from .physics_v2 import PhysicsSimulatorV2
from .templates import instantiate

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

MODEL_VERSION = "physics_v3.0"

#: mu0 in nH/mm (4*pi*1e-7 H/m).
_MU0_NH_PER_MM = 4.0 * math.pi * 1e-1
_REF_LOOP_INDUCTANCE_NH = 25.0
_SQUARE_LOOP_SPAN_TO_AOP = 4.0 * math.sqrt(2.0)
_LOG_SHAPE_FACTOR = 8.0
_REF_VIA_INDUCTANCE_NH = 1.0
_DEFAULT_LAYERS = 2
_DEFAULT_COPPER_MM = 0.035  # 1 oz copper
_DEFAULT_BOARD_THICKNESS_MM = 1.6
_MAX_FEATURE = 1.0e6
_MAX_LAYERS = 32

_CAP_KINDS = {"input_cap", "output_cap", "decap"}
_POWER_KINDS = {"power_switch", "inductor"} | _CAP_KINDS
_ANALOG_KINDS = {"analog", "crystal"}
_RF_KINDS = {"antenna", "rf"}
_POWER_CLASSES = {"power", "ground"}
_SENSITIVE_CLASSES = {"analog", "rf"}

_MASK64 = (1 << 64) - 1
_GOLDEN64 = 0x9E3779B97F4A7C15


def _stable_seed(name: str, seed: int) -> int:
    """Process-independent 64-bit seed from ``(scenario name, seed)``."""
    payload = f"physics_v3|{name}|{int(seed)}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


class _SplitMix64:
    """Small deterministic PRNG (stable across Python versions/platforms)."""

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
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()


# (name, low, high) drawn in this exact order; the order is part of the model.
_COEFF_SPEC: Tuple[Tuple[str, float, float], ...] = (
    # --- power-loop inductance / stack-up ---------------------------------
    ("wire_gain", 0.30, 0.90),
    ("wire_quad", 0.20, 0.80),
    ("loop_gain", 0.35, 0.95),
    ("trace_width_mm", 0.15, 0.50),
    ("loop_mutual", 0.20, 1.00),
    ("plane_gain", 0.25, 0.60),
    ("copper_loop_exp", 0.10, 0.30),
    ("via_diameter_mm", 0.20, 0.40),
    ("board_thickness_mm", 1.2, 2.0),
    ("via_loop_gain", 0.40, 1.20),
    # --- PDN ---------------------------------------------------------------
    ("pdn_gain", 3.0, 9.0),
    ("pdn_floor", 0.010, 0.060),
    ("pdn_parallel_exp", 0.60, 0.95),
    ("pdn_quad", 0.30, 1.50),
    ("pdn_layer_gain", 0.20, 0.50),
    ("pdn_via_gain", 0.20, 0.90),
    ("copper_pdn_exp", 0.05, 0.20),
    # --- thermal ------------------------------------------------------------
    ("thermal_gain", 12.0, 45.0),
    ("thermal_exp", 1.00, 1.28),
    ("thermal_layer_gain", 0.15, 0.45),
    ("thermal_copper_gain", 0.10, 0.35),
    # --- net-class-aware coupling ------------------------------------------
    ("couple_amp", 1.6, 3.6),
    ("class_analog_weight", 1.2, 2.4),
    ("class_rf_weight", 2.0, 4.5),
    ("class_digital_weight", 0.20, 0.70),
    ("lambda_analog_mm", 2.0, 5.0),
    ("lambda_rf_mm", 5.0, 12.0),
    ("lambda_digital_mm", 1.5, 4.0),
    ("couple_near_weight", 0.05, 0.30),
    ("couple_near_mm", 0.8, 2.5),
    ("couple_loop_boost", 0.20, 1.20),
    ("signal_loop_gain", 0.30, 1.20),
    ("layer_shield_gain", 0.10, 0.30),
    # --- escape / congestion / keepout / nonlinear --------------------------
    ("escape_gain", 0.90, 2.20),
    ("escape_margin_floor", 0.050, 0.120),
    ("cong_gain", 0.35, 1.20),
    ("cong_quad", 0.30, 1.20),
    ("keepout_penalty", 20.0, 55.0),
    ("keepout_quad", 40.0, 120.0),
    ("decap_quad", 0.50, 2.00),
    ("pdn_loop_cross", 0.50, 1.50),
)

COMPONENT_TERMS: Tuple[str, ...] = (
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


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _nonneg(value: float, what: str) -> float:
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"feature {what!r} is not finite: {value!r}")
    if v <= 0.0:
        return 0.0
    return v if v <= _MAX_FEATURE else _MAX_FEATURE


def _diag(sc: Scenario) -> float:
    return math.hypot(float(sc.board_w), float(sc.board_h))


def _board_area(sc: Scenario) -> float:
    return max(1e-9, float(sc.board_w) * float(sc.board_h))


def _net_class(net) -> str:
    return net.cls if net.cls in {"power", "ground", "analog", "digital", "rf", "generic"} else "generic"


def _scenario_layers(scenario: Scenario) -> int:
    for attribute in ("layers", "num_layers", "copper_layers"):
        value = getattr(scenario, attribute, None)
        if value is not None:
            return int(value)
    return _DEFAULT_LAYERS


def _min_pad_gap(sc: Scenario, pl: Placement, refs_a: Sequence[str], refs_b: Sequence[str]) -> float:
    """Normalised minimum pad distance between two component groups (mm/diag)."""
    if not refs_a or not refs_b:
        return 0.5
    diag = _diag(sc)
    best = min(
        comp_pad_distance(sc, pl, a, b) for a in refs_a for b in refs_b if a != b
    )
    return best / diag


def _class_max_span(sc: Scenario, pl: Placement, net_classes: Sequence[str]) -> float:
    """Mean over nets of the class of their maximum pad-to-pad span / diag."""
    diag = _diag(sc)
    spans: List[float] = []
    for net in sc.nets:
        if _net_class(net) not in net_classes:
            continue
        points = []
        for ref, pin in net.pins:
            comp = sc.components[ref]
            x, y, rot = pl[ref]
            points.append(pad_position(comp, x, y, rot, pin))
        if len(points) < 2:
            continue
        span = max(
            math.hypot(a[0] - b[0], a[1] - b[1])
            for i, a in enumerate(points)
            for b in points[i + 1:]
        )
        spans.append(span / diag)
    return sum(spans) / len(spans) if spans else 0.0


def extract_features_v3(sc: Scenario, pl: Placement) -> Dict[str, float]:
    """Ten baseline features plus the layer/class-aware inputs used by v3.

    The first ten keys are exactly :data:`mp_place.features.FEATURE_NAMES` and
    carry the same values as :func:`mp_place.features.extract_features`.
    """
    base = extract_features(sc, pl)
    comps = sc.components
    refs = sorted(comps)
    power_refs = [ref for ref in refs if comps[ref].kind in _POWER_KINDS]
    analog_refs = [ref for ref in refs if comps[ref].kind in _ANALOG_KINDS]
    rf_refs = [ref for ref in refs if comps[ref].kind in _RF_KINDS]
    digital_refs = sorted(
        {ref for net in sc.nets if _net_class(net) == "digital" for ref, _pin in net.pins}
    )
    board_area = _board_area(sc)
    copper_area = 0.0
    for ref in refs:
        box = bbox(comps[ref], *pl[ref])
        copper_area += (box[2] - box[0]) * (box[3] - box[1])
    total_power = sum(float(comps[ref].power_w) for ref in refs if comps[ref].kind == "power_switch")

    values: Dict[str, float] = {
        **base,
        "analog_power_gap": _min_pad_gap(sc, pl, analog_refs, power_refs),
        "rf_power_gap": _min_pad_gap(sc, pl, rf_refs, power_refs),
        "digital_power_gap": _min_pad_gap(sc, pl, digital_refs, power_refs),
        "power_span": _class_max_span(sc, pl, ("power", "ground")),
        "analog_span": _class_max_span(sc, pl, ("analog",)),
        "rf_span": _class_max_span(sc, pl, ("rf",)),
        "digital_span": _class_max_span(sc, pl, ("digital",)),
        "copper_frac": copper_area / board_area,
        "switch_power_w": total_power,
    }
    return {name: _nonneg(value, name) for name, value in values.items()}


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #
class PhysicsSimulatorV3:
    """Layer- and net-class-aware offline multi-physics scorer (v2-compatible API).

    ``score_features(f)`` works with the plain ten v2 features (missing v3-only
    inputs are derived from the scenario) and with the richer dict returned by
    :func:`extract_features_v3`; ``score(pl)`` always uses the richer one.
    """

    version = MODEL_VERSION

    def __init__(
        self,
        scenario: Scenario,
        seed: int = 0,
        *,
        layers: Optional[int] = None,
        copper_thickness_mm: Optional[float] = None,
    ):
        self.scenario = scenario
        self.seed = int(seed)
        if layers is None:
            layers = _scenario_layers(scenario)
        if isinstance(layers, bool) or not isinstance(layers, int):
            raise ValueError(f"layers must be an int, got {layers!r}")
        if layers < 1 or layers > _MAX_LAYERS:
            raise ValueError(f"layers must be in [1, {_MAX_LAYERS}], got {layers}")
        self.layers = int(layers)
        if copper_thickness_mm is None:
            copper_thickness_mm = getattr(scenario, "copper_thickness_mm", _DEFAULT_COPPER_MM)
        thickness = float(copper_thickness_mm)
        if not math.isfinite(thickness) or thickness <= 0.0:
            raise ValueError(f"copper_thickness_mm must be finite and > 0, got {copper_thickness_mm!r}")
        self.copper_thickness_mm = thickness
        self.diagonal_mm = _diag(scenario)
        self.board_area = _board_area(scenario)

        rng = _SplitMix64(_stable_seed(scenario.name, self.seed))
        self.coeffs: Dict[str, float] = {
            name: rng.uniform(low, high) for name, low, high in _COEFF_SPEC
        }

        # Scenario-level placement-independent bookkeeping.
        comps = scenario.components
        self._n_power_pins = sum(
            len(net.pins) for net in scenario.nets if _net_class(net) in _POWER_CLASSES
        )
        self._n_total_pins = sum(len(net.pins) for net in scenario.nets)
        self._n_caps = sum(1 for comp in comps.values() if comp.kind in _CAP_KINDS)
        self._n_power_nets = sum(1 for net in scenario.nets if _net_class(net) == "power")
        self._switch_power_w = sum(
            float(comp.power_w) for comp in comps.values() if comp.kind == "power_switch"
        )
        self._has_rf = any(comp.kind in _RF_KINDS for comp in comps.values()) or any(
            _net_class(net) == "rf" for net in scenario.nets
        )
        self._has_digital = any(_net_class(net) == "digital" for net in scenario.nets)

    # -- validation / extras -------------------------------------------------
    @staticmethod
    def _checked(f: Dict[str, float]) -> Dict[str, float]:
        if not isinstance(f, dict):
            raise TypeError(f"features must be a dict, got {type(f).__name__}")
        missing = [name for name in FEATURE_NAMES if name not in f]
        if missing:
            raise KeyError(f"missing feature keys: {missing}")
        return {name: _nonneg(f[name], name) for name in FEATURE_NAMES}

    def _extras(self, f: Dict[str, float]) -> Dict[str, float]:
        """v3-only inputs, falling back to scenario-derived defaults for v2 dicts."""
        c = self.coeffs
        analog_gap = _nonneg(f.get("analog_power_gap", f["analog"]), "analog_power_gap")
        rf_gap = _nonneg(f.get("rf_power_gap", 0.5), "rf_power_gap")
        digital_gap = _nonneg(f.get("digital_power_gap", 0.5), "digital_power_gap")
        power_span = _nonneg(f.get("power_span", f["loop"]), "power_span")
        analog_span = _nonneg(f.get("analog_span", 0.0), "analog_span")
        rf_span = _nonneg(f.get("rf_span", 0.0), "rf_span")
        digital_span = _nonneg(f.get("digital_span", 0.0), "digital_span")
        copper_frac = _nonneg(f.get("copper_frac", f["density"]), "copper_frac")
        switch_power = _nonneg(f.get("switch_power_w", self._switch_power_w), "switch_power_w")
        return {
            "analog_gap": analog_gap,
            "rf_gap": rf_gap,
            "digital_gap": digital_gap,
            "power_span": power_span,
            "analog_span": analog_span,
            "rf_span": rf_span,
            "digital_span": digital_span,
            "copper_frac": copper_frac,
            "switch_power": switch_power,
        }

    # -- physical intermediates ---------------------------------------------
    def _physical(self, f: Dict[str, float]) -> Dict[str, float]:
        c = self.coeffs
        f = self._checked(f)
        extra = self._extras(f)
        diag = self.diagonal_mm
        layers = self.layers
        layer_extra = float(layers - 1)
        thickness = self.copper_thickness_mm
        thickness_rel = _DEFAULT_COPPER_MM / max(thickness, 1e-9)
        thickness_rel = thickness_rel if thickness_rel > 0 else 1.0

        # --- power-loop inductance: span -> area/perimeter -> nH ----------
        loop_feature = f["loop"]
        loop = max(loop_feature, extra["power_span"])  # include ground return path
        loop_span_mm = loop * diag
        aop_mm = loop_span_mm / _SQUARE_LOOP_SPAN_TO_AOP
        trace_width = c["trace_width_mm"]
        effective_width = trace_width * math.sqrt(max(thickness / _DEFAULT_COPPER_MM, 1e-9))
        loop_inductance_nh = _MU0_NH_PER_MM * aop_mm * math.log1p(
            _LOG_SHAPE_FACTOR * aop_mm / max(effective_width, 1e-9)
        )
        plane_factor = 1.0 / (1.0 + c["plane_gain"] * layer_extra)
        loop_inductance_effective_nh = (
            loop_inductance_nh * plane_factor * thickness_rel ** c["copper_loop_exp"]
        )

        # --- via estimate and via inductance ------------------------------
        via_pressure = self._n_power_pins / max(1, self._n_total_pins)
        via_diameter = c["via_diameter_mm"]
        board_thickness = c["board_thickness_mm"]
        via_inductance_nh = (
            _MU0_NH_PER_MM
            * board_thickness
            / (2.0 * math.pi)
            * math.log1p(4.0 * board_thickness / max(via_diameter, 1e-9))
        )
        parallel_return_paths = 1.0 + 0.35 * layer_extra * layers
        via_loop_cost = (
            c["via_loop_gain"]
            * via_pressure
            * (via_inductance_nh / _REF_VIA_INDUCTANCE_NH)
            / parallel_return_paths
        )

        # --- PDN: decap distance / parallel caps, plane layers and vias ----
        n_parallel = 1.0 / max(f["capcount"], 1e-3)
        cap_factor = n_parallel ** (-c["pdn_parallel_exp"])
        plane_impedance = c["pdn_floor"] + c["pdn_gain"] * f["decap"] * cap_factor
        plane_impedance /= 1.0 + c["pdn_layer_gain"] * layer_extra
        plane_impedance *= thickness_rel ** c["copper_pdn_exp"]
        pdn_via_impedance = (
            c["pdn_via_gain"]
            * via_pressure
            * (via_inductance_nh / _REF_VIA_INDUCTANCE_NH)
            * (self._n_power_pins / max(1.0, n_parallel * 10.0))
            / (1.0 + 0.5 * layer_extra)
        )
        pdn_impedance = plane_impedance + pdn_via_impedance

        # --- thermal: copper area x layers x thickness ---------------------
        thermal_rise = c["thermal_gain"] * f["thermal"] ** c["thermal_exp"]
        thermal_rise /= 1.0 + c["thermal_layer_gain"] * layer_extra
        thermal_rise *= thickness_rel ** c["thermal_copper_gain"]

        # --- net-class-aware field coupling -------------------------------
        def field(gap_norm: float, length_scale_mm: float) -> float:
            gap_mm = gap_norm * diag
            far = math.exp(-gap_mm / max(length_scale_mm, 1e-9))
            near = 1.0 / (1.0 + (gap_mm / max(c["couple_near_mm"], 1e-9)) ** 2)
            return far + c["couple_near_weight"] * near

        analog_field = field(extra["analog_gap"], c["lambda_analog_mm"])
        rf_field = field(extra["rf_gap"], c["lambda_rf_mm"]) if self._has_rf else 0.0
        digital_field = field(extra["digital_gap"], c["lambda_digital_mm"]) if self._has_digital else 0.0
        class_field = c["couple_amp"] * (
            c["class_analog_weight"] * analog_field
            + c["class_rf_weight"] * rf_field
            + c["class_digital_weight"] * digital_field
        )
        sensitive_span = extra["analog_span"] + 1.5 * extra["rf_span"]
        signal_loop = c["signal_loop_gain"] * sensitive_span
        layer_shield = 1.0 / (1.0 + c["layer_shield_gain"] * layer_extra)
        coupling_field = (class_field + signal_loop) * (1.0 + c["couple_loop_boost"] * loop)
        coupling_field *= layer_shield

        edge_margin = max(1.0 - min(f["escape"], 1.0), c["escape_margin_floor"])
        return {
            "loop_span_mm": loop_span_mm,
            "area_over_perimeter_mm": aop_mm,
            "loop_inductance_nh": loop_inductance_nh,
            "loop_inductance_effective_nh": loop_inductance_effective_nh,
            "plane_factor": plane_factor,
            "thickness_rel": thickness_rel,
            "via_pressure": via_pressure,
            "via_inductance_nh": via_inductance_nh,
            "via_loop_cost": via_loop_cost,
            "pdn_plane_au": plane_impedance,
            "pdn_via_au": pdn_via_impedance,
            "pdn_impedance": pdn_impedance,
            "thermal_rise": thermal_rise,
            "analog_gap_mm": extra["analog_gap"] * diag,
            "rf_gap_mm": extra["rf_gap"] * diag,
            "digital_gap_mm": extra["digital_gap"] * diag,
            "analog_field": analog_field,
            "rf_field": rf_field,
            "digital_field": digital_field,
            "class_field": class_field,
            "sensitive_span": sensitive_span,
            "signal_loop": signal_loop,
            "layer_shield": layer_shield,
            "coupling_field": coupling_field,
            "edge_margin": edge_margin,
            "hpwl": f["hpwl"],
            "loop": loop,
            "decap": f["decap"],
            "copper_frac": extra["copper_frac"],
        }

    # -- public API ----------------------------------------------------------
    def _components(self, f: Dict[str, float]) -> Dict[str, float]:
        c = self.coeffs
        p = self._physical(f)
        checked = self._checked(f)

        wire_cost = c["wire_gain"] * p["hpwl"]
        loop_cost = (
            c["loop_gain"]
            * (p["loop_inductance_effective_nh"] / _REF_LOOP_INDUCTANCE_NH)
            * (1.0 + c["loop_mutual"] * p["loop"])
            + p["via_loop_cost"]
        )
        pdn_cost = p["pdn_impedance"] * (1.0 + c["pdn_quad"] * p["pdn_impedance"])
        thermal_cost = p["thermal_rise"]
        coupling_cost = p["coupling_field"]
        escape_cost = c["escape_gain"] * checked["density"] / p["edge_margin"]
        congestion_cost = c["cong_gain"] * checked["congestion"] * (
            1.0 + c["cong_quad"] * checked["congestion"]
        )
        keepout_cost = c["keepout_penalty"] * checked["keepout"] * (
            1.0 + c["keepout_quad"] * checked["keepout"]
        )
        nonlinear_cost = (
            c["decap_quad"] * checked["decap"] ** 1.5
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
        """Return the non-negative truth cost for a feature dict (lower better)."""
        return max(0.0, math.fsum(self._components(f).values()))

    def score(self, pl: Placement) -> float:
        """Score a placement with the full layer/class-aware feature extraction."""
        return self.score_features(extract_features_v3(self.scenario, pl))

    def breakdown(self, f: Dict[str, float]) -> Dict[str, float]:
        """Per-physics cost contributions (all non-negative); ``total`` last."""
        parts = self._components(f)
        out: Dict[str, float] = {term: parts[term] for term in COMPONENT_TERMS}
        out["total"] = max(0.0, math.fsum(out.values()))
        return out

    def diagnostics(self, f: Dict[str, float]) -> Dict[str, float]:
        """Physical intermediates behind a v3 score."""
        p = self._physical(f)
        return {
            "layers": float(self.layers),
            "copper_thickness_mm": float(self.copper_thickness_mm),
            "board_diagonal_mm": float(self.diagonal_mm),
            "loop_span_mm": p["loop_span_mm"],
            "area_over_perimeter_mm": p["area_over_perimeter_mm"],
            "loop_inductance_nh": p["loop_inductance_nh"],
            "loop_inductance_effective_nh": p["loop_inductance_effective_nh"],
            "plane_factor": p["plane_factor"],
            "thickness_rel": p["thickness_rel"],
            "via_pressure": p["via_pressure"],
            "via_inductance_nh": p["via_inductance_nh"],
            "via_loop_cost": p["via_loop_cost"],
            "pdn_plane_au": p["pdn_plane_au"],
            "pdn_via_au": p["pdn_via_au"],
            "pdn_impedance_au": p["pdn_impedance"],
            "thermal_rise_au": p["thermal_rise"],
            "analog_gap_mm": p["analog_gap_mm"],
            "rf_gap_mm": p["rf_gap_mm"],
            "digital_gap_mm": p["digital_gap_mm"],
            "analog_field": p["analog_field"],
            "rf_field": p["rf_field"],
            "digital_field": p["digital_field"],
            "sensitive_span": p["sensitive_span"],
            "layer_shield": p["layer_shield"],
            "edge_margin": p["edge_margin"],
        }

    def coefficients(self) -> Dict[str, float]:
        return dict(self.coeffs)

    @classmethod
    def coefficient_names(cls) -> Tuple[str, ...]:
        return tuple(name for name, _low, _high in _COEFF_SPEC)


# --------------------------------------------------------------------------- #
# v2 vs v3 comparison study
# --------------------------------------------------------------------------- #
CAPACITY_TEMPLATES: Tuple[str, ...] = ("mcu-min", "buck", "rs485", "motor", "wireless")
N_RANDOM = 120
SAMPLE_SEED = 0
TRUTH_SEED = 0
TOP_K = 10
LAYER_SENSITIVITY = (2, 4, 6)
COPPER_SENSITIVITY = (0.035, 0.070)
MAX_DIFF_CASES = 8


def _load_real_boards(sources: Optional[Sequence[Tuple[str, pathlib.Path]]] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load the three bundled EasyCirq board dumps; never raises for missing files."""
    try:
        from .realboard import DEFAULT_SOURCES, convert_dump, load_dump
    except Exception as exc:  # pragma: no cover - dependency guard
        return [], [{"name": "realboard", "status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}]
    source_list = list(sources) if sources is not None else list(DEFAULT_SOURCES)
    boards: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for name, path in source_list:
        target = pathlib.Path(path)
        if not target.exists():
            missing.append({"name": str(name), "source": str(target), "status": "MISSING"})
            continue
        try:
            payload = load_dump(target)
            converted = convert_dump(payload, name=str(name), source=str(target))
            layers = int(payload.get("copperLayers") or _DEFAULT_LAYERS)
            rules = payload.get("rules") if isinstance(payload.get("rules"), dict) else {}
            via_diameter_mil = rules.get("viaDiameterMil")
            via_diameter_mm = (
                float(via_diameter_mil) * 0.0254 if isinstance(via_diameter_mil, (int, float)) else None
            )
            boards.append(
                {
                    "name": str(name),
                    "scenario": converted.scenario,
                    "placements": [converted.original_placement],
                    "original_index": 0,
                    "layers": max(1, min(_MAX_LAYERS, layers)),
                    "layers_source": "dump.copperLayers",
                    "report": converted.report,
                    "via_diameter_mm_dump": via_diameter_mm,
                }
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the study
            missing.append(
                {"name": str(name), "source": str(target), "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
            )
    return boards, missing


def _sample_placements(scenario: Scenario, n: int, seed: int) -> List[Placement]:
    """Deterministic random feasible layouts (same helper as the dataset module)."""
    return list(iter_layouts(scenario, n=n, seed=seed))


def _percentiles(scores: Sequence[float]) -> List[float]:
    """Rank percentile in [0, 1]; lower score -> lower (better) percentile."""
    n = len(scores)
    if n <= 1:
        return [0.5 for _ in scores]
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    for position, index in enumerate(order):
        ranks[index] = (position + 1) / n
    return ranks


def _stats(values: Sequence[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.mean(values), 4),
        "std": round(statistics.pstdev(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _top_overlap(scores_a: Sequence[float], scores_b: Sequence[float], k: int) -> float:
    """Fraction of the best-``k`` layouts of A that are also best-``k`` of B."""
    n = len(scores_a)
    if n == 0:
        return 0.0
    k = min(k, n)
    top_a = set(sorted(range(n), key=lambda i: scores_a[i])[:k])
    top_b = set(sorted(range(n), key=lambda i: scores_b[i])[:k])
    return len(top_a & top_b) / k


def _compare_board(
    board: Dict[str, Any],
    *,
    seed: int = TRUTH_SEED,
    n_random: int = N_RANDOM,
) -> Dict[str, Any]:
    """Score the random + original layouts of one board with v2 and v3."""
    scenario: Scenario = board["scenario"]
    base_placements = list(board.get("placements") or [])
    random_placements = _sample_placements(scenario, n_random, SAMPLE_SEED)
    placements = random_placements + base_placements
    sources = ["random"] * len(random_placements) + ["original"] * len(base_placements)
    v2 = PhysicsSimulatorV2(scenario, seed=seed)
    v3 = PhysicsSimulatorV3(
        scenario,
        seed=seed,
        layers=board.get("layers"),
        copper_thickness_mm=board.get("copper_thickness_mm"),
    )
    records: List[Dict[str, Any]] = []
    for index, (placement, source) in enumerate(zip(placements, sources)):
        f10 = extract_features(scenario, placement)
        fv3 = extract_features_v3(scenario, placement)
        truth_v2 = v2.score_features(f10)
        truth_v3 = v3.score_features(fv3)
        records.append(
            {
                "index": index,
                "source": source,
                "placement": placement,
                "features_v2": f10,
                "features_v3": fv3,
                "truth_v2": truth_v2,
                "truth_v3": truth_v3,
                "feasible": not hard_violations(scenario, placement),
            }
        )
    v2_scores = [record["truth_v2"] for record in records]
    v3_scores = [record["truth_v3"] for record in records]
    percentiles_v2 = _percentiles(v2_scores)
    percentiles_v3 = _percentiles(v3_scores)
    for record, p2, p3 in zip(records, percentiles_v2, percentiles_v3):
        record["percentile_v2"] = p2
        record["percentile_v3"] = p3
    row: Dict[str, Any] = {
        "name": board["name"],
        "kind": board.get("kind", "template"),
        "board_mm": [round(float(scenario.board_w), 3), round(float(scenario.board_h), 3)],
        "components": len(scenario.components),
        "nets": len(scenario.nets),
        "layers": v3.layers,
        "layers_source": board.get("layers_source", "default(2)"),
        "copper_thickness_mm": v3.copper_thickness_mm,
        "n_layouts": len(records),
        "n_random": len(random_placements),
        "n_original": len(base_placements),
        "spearman_v2_v3": round(spearman(v2_scores, v3_scores), 4),
        "pearson_v2_v3": round(correlation(v2_scores, v3_scores), 4),
        f"top{TOP_K}_overlap": round(_top_overlap(v2_scores, v3_scores, TOP_K), 4),
        "truth_v2": _stats(v2_scores),
        "truth_v3": _stats(v3_scores),
        "mean_ratio_v3_over_v2": round(_stats(v3_scores)["mean"] / max(_stats(v2_scores)["mean"], 1e-12), 4),
        "feasible_fraction": round(sum(1 for record in records if record["feasible"]) / len(records), 4),
    }
    original = next((record for record in records if record["source"] == "original"), None)
    if original is not None:
        row["original"] = {
            "feasible": original["feasible"],
            "truth_v2": round(original["truth_v2"], 4),
            "truth_v3": round(original["truth_v3"], 4),
            "percentile_v2": round(original["percentile_v2"], 4),
            "percentile_v3": round(original["percentile_v3"], 4),
        }
    row["_records"] = records
    row["_v3"] = v3
    row["_v2"] = v2
    return row


def _layer_sensitivity(
    templates: Sequence[str],
    *,
    layers: Sequence[int] = LAYER_SENSITIVITY,
    copper_thicknesses: Sequence[float] = COPPER_SENSITIVITY,
    seed: int = TRUTH_SEED,
) -> List[Dict[str, Any]]:
    """Score one representative layout per template across layer counts / copper."""
    rows: List[Dict[str, Any]] = []
    for template in templates:
        scenario = instantiate(template, 0)
        placements = _sample_placements(scenario, 1, SAMPLE_SEED)
        if not placements:
            continue
        placement = placements[0]
        features = extract_features_v3(scenario, placement)
        scores: List[float] = []
        loop_nh: List[float] = []
        pdn_au: List[float] = []
        thermal_au: List[float] = []
        for layer in layers:
            simulator = PhysicsSimulatorV3(scenario, seed=seed, layers=int(layer))
            scores.append(round(simulator.score_features(features), 4))
            diagnostics = simulator.diagnostics(features)
            loop_nh.append(round(diagnostics["loop_inductance_effective_nh"], 4))
            pdn_au.append(round(diagnostics["pdn_impedance_au"], 4))
            thermal_au.append(round(diagnostics["thermal_rise_au"], 4))
        copper_scores = []
        for thickness in copper_thicknesses:
            simulator = PhysicsSimulatorV3(
                scenario, seed=seed, layers=int(layers[0]), copper_thickness_mm=thickness
            )
            copper_scores.append(round(simulator.score_features(features), 4))
        rows.append(
            {
                "name": template,
                "layers": [int(layer) for layer in layers],
                "layer_scores": scores,
                "layer_loop_inductance_nh": loop_nh,
                "layer_pdn_au": pdn_au,
                "layer_thermal_au": thermal_au,
                "copper_thickness_mm": [float(t) for t in copper_thicknesses],
                "copper_scores": copper_scores,
                "layer_drop_pct": round(100.0 * (scores[0] - scores[-1]) / max(scores[0], 1e-12), 2),
                "copper_drop_pct": round(
                    100.0 * (copper_scores[0] - copper_scores[-1]) / max(copper_scores[0], 1e-12), 2
                ),
            }
        )
    return rows


def _risk_flags(features_v3: Dict[str, float], layers: int) -> Dict[str, float]:
    return {
        "analog_gap": features_v3.get("analog_power_gap", 0.5),
        "rf_gap": features_v3.get("rf_power_gap", 0.5),
        "digital_gap": features_v3.get("digital_power_gap", 0.5),
        "sensitive_span": features_v3.get("analog_span", 0.0) + 1.5 * features_v3.get("rf_span", 0.0),
        "power_span": features_v3.get("power_span", 0.0),
        "layers": float(layers),
    }


def _dominant_reason(
    v2_terms: Dict[str, float],
    v3_terms: Dict[str, float],
    features_v3: Dict[str, float],
    layers: int,
    diagonal_mm: float,
) -> Tuple[str, Dict[str, float]]:
    """Pick the term whose v3-v2 cost delta explains the rank flip."""
    deltas = {
        term: float(v3_terms.get(term, 0.0) - v2_terms.get(term, 0.0))
        for term in ("loop_inductance", "pdn_impedance", "thermal", "field_coupling")
    }
    dominant = max(deltas, key=deltas.get)
    flags = _risk_flags(features_v3, layers)
    analog_mm = flags["analog_gap"] * diagonal_mm
    rf_mm = flags["rf_gap"] * diagonal_mm
    if dominant == "field_coupling":
        if rf_mm < 0.12 * diagonal_mm:
            text = (
                f"RF/天线与功率级最近距离仅 {rf_mm:.1f} mm：v3 对 RF 类使用更高权重"
                "与更长耦合尺度，v2 的 analog 距离特征不统计 RF 器件"
            )
        elif analog_mm < 0.12 * diagonal_mm:
            text = (
                f"模拟网络贴功率级（最近 {analog_mm:.1f} mm）：v3 按 net class 加权模拟耦合"
                "（权重高于 v2 的单一 analog 项）"
            )
        elif flags["sensitive_span"] > 0.0:
            text = (
                f"模拟/RF 网络跨度大（sensitive span {flags['sensitive_span']:.3f}）："
                "v3 新增 signal-loop 面积惩罚"
            )
        else:
            text = "v3 的 net-class 耦合权重/尺度不同，使该布局的耦合代价高于 v2"
    elif dominant == "loop_inductance":
        text = (
            f"功率回路跨度大且层数少（layers={layers}）：v3 按平面并联/铜厚折算回路电感并叠加过孔项，"
            "v2 只按回路长度线性计"
        )
    elif dominant == "pdn_impedance":
        caps = features_v3.get("capcount", 0.0)
        text = (
            "去耦并联不足/过孔压力高：v3 的 PDN 阻抗计入层并联与过孔（decoupling parallel + via），"
            f"该布局 capcount={caps:.3f}，v2 只有距离/并联数的简化项"
        )
    else:
        text = (
            "功率密度高而铜面积有限：v3 的热项按铜面积×层数×铜厚折算，v2 只按单层铜面积估计"
        )
    return text, deltas


def _find_difference_cases(boards: Sequence[Dict[str, Any]], max_cases: int = MAX_DIFF_CASES) -> List[Dict[str, Any]]:
    """Find layouts where v2 ranks the placement good and v3 ranks it bad.

    A candidate must be in the better part of the v2 ranking but in the worse
    part of the v3 ranking, with a meaningful percentile drop.  The rule is
    adaptive so that at least five cases are reported whenever the pool allows
    it: strict (v2 percentile <= 0.45, v3 >= 0.60, drop >= 0.25) first, then
    relaxed thresholds.
    """
    thresholds = (
        (0.45, 0.60, 0.25),
        (0.50, 0.60, 0.25),
        (0.50, 0.60, 0.15),
    )
    best: List[Dict[str, Any]] = []
    min_required = min(6, max_cases)
    for v2_max, v3_min, drop_min in thresholds:
        candidates = _collect_difference_candidates(boards, v2_max, v3_min, drop_min)
        selected = _diversify(candidates, max_cases, per_board=2)
        if len(selected) > len(best):
            best = selected
        if len(best) >= min_required:
            break
    if len(best) < min(5, max_cases):  # pragma: no cover - very small pools
        candidates = _collect_difference_candidates(boards, *thresholds[-1])
        best = _diversify(candidates, max_cases, per_board=len(boards) + 1)
    for case in best:
        case["criteria"] = case.pop("_criteria")
    return best


def _diversify(candidates: Sequence[Dict[str, Any]], max_cases: int, per_board: int = 2) -> List[Dict[str, Any]]:
    """Pick strong cases while avoiding that one board dominates the table."""
    selected: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for case in candidates:
        board = case["board"]
        if counts.get(board, 0) >= per_board:
            continue
        selected.append(case)
        counts[board] = counts.get(board, 0) + 1
        if len(selected) >= max_cases:
            break
    return selected


def _collect_difference_candidates(
    boards: Sequence[Dict[str, Any]],
    v2_max: float,
    v3_min: float,
    drop_min: float,
) -> List[Dict[str, Any]]:
    """Collect rank-flip candidates for one threshold triple."""
    candidates: List[Dict[str, Any]] = []
    for board in boards:
        records = board["_records"]
        v3: PhysicsSimulatorV3 = board["_v3"]
        v2: PhysicsSimulatorV2 = board["_v2"]
        for record in records:
            drop = record["percentile_v3"] - record["percentile_v2"]
            if record["percentile_v2"] > v2_max or record["percentile_v3"] < v3_min:
                continue
            if drop < drop_min:
                continue
            flags = _risk_flags(record["features_v3"], board["layers"])
            specific_risk = (
                flags["rf_gap"] < 0.12
                or flags["analog_gap"] < 0.12
                or flags["digital_gap"] < 0.12
                or flags["sensitive_span"] > 0.15
                or flags["power_span"] > 0.5
            )
            if not specific_risk:
                continue
            v2_terms = v2.breakdown(record["features_v2"])
            v3_terms = v3.breakdown(record["features_v3"])
            diagonal = _diag(board["scenario"])
            reason, deltas = _dominant_reason(
                v2_terms, v3_terms, record["features_v3"], board["layers"], diagonal
            )
            candidates.append(
                {
                    "board": board["name"],
                    "kind": board.get("kind", "template"),
                    "source": record["source"],
                    "layers": board["layers"],
                    "percentile_v2": round(record["percentile_v2"], 4),
                    "percentile_v3": round(record["percentile_v3"], 4),
                    "percentile_drop": round(drop, 4),
                    "truth_v2": round(record["truth_v2"], 4),
                    "truth_v3": round(record["truth_v3"], 4),
                    "dominant_term": max(deltas, key=deltas.get),
                    "term_deltas_v3_minus_v2": {key: round(value, 4) for key, value in deltas.items()},
                    "risk_flags": {
                        "analog_gap_norm": round(flags["analog_gap"], 4),
                        "rf_gap_norm": round(flags["rf_gap"], 4),
                        "digital_gap_norm": round(flags["digital_gap"], 4),
                        "sensitive_span": round(flags["sensitive_span"], 4),
                        "power_span": round(flags["power_span"], 4),
                    },
                    "gap_mm": {
                        "analog": round(flags["analog_gap"] * diagonal, 2),
                        "rf": round(flags["rf_gap"] * diagonal, 2),
                        "digital": round(flags["digital_gap"] * diagonal, 2),
                    },
                    "explanation": reason,
                    "placement": {
                        ref: [round(float(x), 3), round(float(y), 3), int(rot)]
                        for ref, (x, y, rot) in sorted(record["placement"].items())
                    },
                    "_board": board["name"],
                    "_criteria": {
                        "v2_percentile_max": v2_max,
                        "v3_percentile_min": v3_min,
                        "percentile_drop_min": drop_min,
                    },
                }
            )
    candidates.sort(
        key=lambda case: (
            case["percentile_drop"],
            abs(case["term_deltas_v3_minus_v2"][case["dominant_term"]]),
        ),
        reverse=True,
    )
    return candidates


def _summarize(
    boards: Sequence[Dict[str, Any]],
    layer_rows: Sequence[Dict[str, Any]],
    difference_cases: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    spearman_values = [row["spearman_v2_v3"] for row in boards]
    overlap_values = [row[f"top{TOP_K}_overlap"] for row in boards]
    ratio_values = [row["mean_ratio_v3_over_v2"] for row in boards]
    layer_drops = [row["layer_drop_pct"] for row in layer_rows]
    copper_drops = [row["copper_drop_pct"] for row in layer_rows]
    template_rows = [row for row in boards if row.get("kind") == "template"]
    real_rows = [row for row in boards if row.get("kind") != "template"]
    return {
        "n_boards": len(boards),
        "n_templates": len(template_rows),
        "n_real_boards": len(real_rows),
        "mean_spearman_v2_v3": round(statistics.mean(spearman_values), 4) if spearman_values else 0.0,
        "min_spearman_v2_v3": round(min(spearman_values), 4) if spearman_values else 0.0,
        "max_spearman_v2_v3": round(max(spearman_values), 4) if spearman_values else 0.0,
        f"mean_top{TOP_K}_overlap": round(statistics.mean(overlap_values), 4) if overlap_values else 0.0,
        "mean_truth_ratio_v3_over_v2": round(statistics.mean(ratio_values), 4) if ratio_values else 0.0,
        "mean_layer_drop_pct": round(statistics.mean(layer_drops), 2) if layer_drops else 0.0,
        "mean_copper_drop_pct": round(statistics.mean(copper_drops), 2) if copper_drops else 0.0,
        "n_difference_cases": len(difference_cases),
        "difference_case_boards": sorted({case["_board"] for case in difference_cases}),
        "dominant_terms": {
            term: sum(1 for case in difference_cases if case["dominant_term"] == term)
            for term in ("loop_inductance", "pdn_impedance", "thermal", "field_coupling")
        },
    }


def run_comparison(
    templates: Sequence[str] = CAPACITY_TEMPLATES,
    *,
    real_sources: Optional[Sequence[Tuple[str, pathlib.Path]]] = None,
    n_random: int = N_RANDOM,
    seed: int = TRUTH_SEED,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Run the full v2-vs-v3 study on templates + real boards."""
    started = time.perf_counter()
    boards: List[Dict[str, Any]] = []
    for template in templates:
        scenario = instantiate(template, 0)
        board = {
            "name": template,
            "kind": "template",
            "scenario": scenario,
            "placements": [],
            "layers": _scenario_layers(scenario),
            "layers_source": "default(2)",
        }
        row = _compare_board(board, seed=seed, n_random=n_random)
        boards.append({**board, **{key: value for key, value in row.items() if key not in board}})
        if not quiet:
            print(
                f"[v3] template {template:9s} spearman={row['spearman_v2_v3']:.4f} "
                f"top{TOP_K}={row[f'top{TOP_K}_overlap']:.2f} "
                f"mean(v2)={row['truth_v2']['mean']:.3f} mean(v3)={row['truth_v3']['mean']:.3f}"
            )

    real_boards, missing = _load_real_boards(real_sources)
    for board in real_boards:
        board["kind"] = "real"
        board["copper_thickness_mm"] = _DEFAULT_COPPER_MM
        row = _compare_board(board, seed=seed, n_random=n_random)
        boards.append({**board, **{key: value for key, value in row.items() if key not in board}})
        if not quiet:
            print(
                f"[v3] real {board['name']:9s} spearman={row['spearman_v2_v3']:.4f} "
                f"top{TOP_K}={row[f'top{TOP_K}_overlap']:.2f} layers={row['layers']}"
            )

    layer_rows = _layer_sensitivity(templates, seed=seed)
    difference_cases = _find_difference_cases(boards)
    # strip internal fields so the report is JSON safe / small
    public_boards: List[Dict[str, Any]] = []
    for board in boards:
        public = {key: value for key, value in board.items() if not key.startswith("_")}
        public.pop("scenario", None)
        public.pop("placements", None)
        public_boards.append(public)
    public_cases = [
        {key: value for key, value in case.items() if not key.startswith("_")}
        for case in difference_cases
    ]
    data: Dict[str, Any] = {
        "config": {
            "model": MODEL_VERSION,
            "compare_to": "PhysicsSimulatorV2",
            "templates": list(templates),
            "n_random_per_board": int(n_random),
            "sample_seed": SAMPLE_SEED,
            "truth_seed": int(seed),
            "real_sources": [
                {"name": row["name"], "status": row["status"]}
                for row in missing
            ] if missing else "bundled easycirq dumps",
            "layer_sensitivity": [int(layer) for layer in LAYER_SENSITIVITY],
            "copper_sensitivity_mm": [float(t) for t in COPPER_SENSITIVITY],
            "top_k": TOP_K,
        },
        "boards": public_boards,
        "layer_sensitivity": layer_rows,
        "difference_cases": public_cases,
        "missing_real_boards": missing,
        "summary": _summarize(boards, layer_rows, difference_cases),
        "runtime_s": round(time.perf_counter() - started, 2),
    }
    return data


# --------------------------------------------------------------------------- #
# markdown / json report
# --------------------------------------------------------------------------- #
def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_markdown(data: Dict[str, Any]) -> str:
    config = data["config"]
    summary = data["summary"]
    boards = data["boards"]
    layer_rows = data["layer_sensitivity"]
    cases = data["difference_cases"]
    overlap_key = f"mean_top{TOP_K}_overlap"
    lines: List[str] = []
    lines.append("# P2.13 Physics v3：层数 / 网络类感知仿真器与 v2 对比\n")
    lines.append(
        f"- 运行时：{data.get('runtime_s', 0.0)} s；v2 vs v3；模板：{', '.join(config['templates'])}；"
        f"真实板：{summary['n_real_boards']} 块（EasyCirq dump，只读）"
    )
    lines.append(
        f"- 数据：每板 {config['n_random_per_board']} 个 random feasible 布局"
        f"（采样 seed={config['sample_seed']}）+ 真实板原布局；truth seed={config['truth_seed']}"
    )
    lines.append(
        "- v3 细化：回路电感按层并联/铜厚折算并加过孔项；PDN 计层并联、过孔与并联去耦；"
        "热项按铜面积×层数×铜厚；耦合按 net class（analog/RF/digital）分权重与距离尺度；"
        "层数默认 2（真实板取 dump `copperLayers`），1 oz 铜=0.035 mm"
    )
    lines.append(
        "- 隐藏系数：`blake2b(\"physics_v3|name|seed\")` + SplitMix64，无 `hash()`，跨进程可复现；"
        "接口与 v2 兼容（`score_features` / `score`）\n"
    )

    lines.append("## 1. 层数 / 铜厚参数敏感性（每个模板取 1 个代表布局）\n")
    rows = []
    for row in layer_rows:
        layer_cells = " / ".join(
            f"L{layer}: {score:.4f}"
            for layer, score in zip(row["layers"], row["layer_scores"])
        )
        copper_cells = " / ".join(
            f"{thickness * 1000:.0f}um: {score:.4f}"
            for thickness, score in zip(row["copper_thickness_mm"], row["copper_scores"])
        )
        rows.append(
            [
                row["name"],
                layer_cells,
                f"{row['layer_drop_pct']:.2f}%",
                copper_cells,
                f"{row['copper_drop_pct']:.2f}%",
                f"{row['layer_loop_inductance_nh'][0]:.2f}→{row['layer_loop_inductance_nh'][-1]:.2f}",
                f"{row['layer_pdn_au'][0]:.4f}→{row['layer_pdn_au'][-1]:.4f}",
                f"{row['layer_thermal_au'][0]:.3f}→{row['layer_thermal_au'][-1]:.3f}",
            ]
        )
    lines.append(
        _md_table(
            [
                "模板",
                f"层数 {config['layer_sensitivity']} 得分",
                "层数降幅",
                f"铜厚 {[round(t * 1000) for t in config['copper_sensitivity_mm']]}um 得分",
                "铜厚降幅",
                "有效回路电感 nH",
                "PDN 阻抗 AU",
                "热升 AU",
            ],
            rows,
        )
    )
    lines.append(
        f"\n> 层数 2→6 平均降分 {summary['mean_layer_drop_pct']:.2f}%，"
        f"铜厚 1→2 oz 平均降分 {summary['mean_copper_drop_pct']:.2f}%；"
        "同一布局下更多层/更厚铜始终得分更低（与 v3 的并联回流、热扩散假设一致）。\n"
    )

    lines.append("## 2. v2 vs v3 排序一致性与 truth 分布\n")
    rows = []
    for board in boards:
        original = board.get("original") or {}
        rows.append(
            [
                board["name"],
                board.get("kind"),
                f"L{board['layers']}",
                board["spearman_v2_v3"],
                board[f"top{TOP_K}_overlap"],
                f"{board['truth_v2']['mean']:.4f}",
                f"{board['truth_v3']['mean']:.4f}",
                f"{board['mean_ratio_v3_over_v2']:.3f}",
                f"{board['truth_v2']['min']:.3f}–{board['truth_v2']['max']:.3f}",
                f"{board['truth_v3']['min']:.3f}–{board['truth_v3']['max']:.3f}",
                _fmt(original.get("percentile_v2"), 2) + "/" + _fmt(original.get("percentile_v3"), 2)
                if original
                else "—",
            ]
        )
    lines.append(
        _md_table(
            [
                "板",
                "类型",
                "层",
                "Spearman(v2,v3)",
                f"top{TOP_K} 重叠",
                "mean v2",
                "mean v3",
                "v3/v2 比",
                "v2 范围",
                "v3 范围",
                "原布局百分位 v2/v3",
            ],
            rows,
        )
    )
    lines.append(
        f"\n> {summary['n_boards']} 板平均 Spearman = {summary['mean_spearman_v2_v3']:.4f}"
        f"（范围 {summary['min_spearman_v2_v3']:.4f}–{summary['max_spearman_v2_v3']:.4f}），"
        f"top-{TOP_K} 平均重叠 = {summary[overlap_key]:.2f}；"
        f"v3 平均 truth / v2 = {summary['mean_truth_ratio_v3_over_v2']:.3f}。"
        "排序高度一致说明 v3 是 v2 的细化而非另一个模型，但尾部/差异案例仍需专门解释。\n"
    )

    lines.append("## 3. v2 判好、v3 判差的差异案例（{0} 个）\n".format(len(cases)))
    lines.append(
        "筛选规则：同一板内 v2 分位 ≤0.45（样本不足 6 例时放宽到 ≤0.50）且 v3 分位 ≥0.60、"
        "分位下滑 ≥0.25（必要时 ≥0.15），并要求存在 v3 专属风险（RF/模拟/数字贴近功率级或敏感网络跨度大）；"
        "`Δ项` = v3−v2 各物理分项代价差，主导项用于解释。\n"
    )
    lines.append(
        "> v2 与 v3 的隐藏系数独立，绝对分值尺度不同；“判好/判差”以**同一板内的分位排序**为准，"
        "绝对 truth 仅作参考。\n"
    )
    rows = []
    for index, case in enumerate(cases, 1):
        deltas = case["term_deltas_v3_minus_v2"]
        gaps = case["gap_mm"]
        rows.append(
            [
                index,
                case["board"],
                case["kind"],
                case["source"],
                f"L{case['layers']}",
                f"{case['percentile_v2']:.2f}/{case['percentile_v3']:.2f}",
                f"{case['percentile_drop']:+.2f}",
                f"{case['truth_v2']:.4f}",
                f"{case['truth_v3']:.4f}",
                case["dominant_term"],
                f"{deltas[case['dominant_term']]:+.4f}",
                f"rf={gaps['rf']:.1f}, analog={gaps['analog']:.1f}, "
                f"digital={gaps['digital']:.1f} mm；span={case['risk_flags']['sensitive_span']:.2f}",
            ]
        )
    lines.append(
        _md_table(
            [
                "#",
                "板",
                "类型",
                "来源",
                "层",
                "percentile v2/v3",
                "分位下滑",
                "truth v2",
                "truth v3",
                "主导项",
                "Δ项",
                "风险量",
            ],
            rows,
        )
    )
    lines.append("")
    for index, case in enumerate(cases, 1):
        lines.append(
            f"**案例 {index}（{case['board']}，{case['source']}，layers={case['layers']}）**："
            f"v2={case['truth_v2']:.4f}（百分位 {case['percentile_v2']:.2f}）→ "
            f"v3={case['truth_v3']:.4f}（百分位 {case['percentile_v3']:.2f}）；"
            f"主导项 `{case['dominant_term']}` Δ={case['term_deltas_v3_minus_v2'][case['dominant_term']]:+.4f}。"
            f"物理解释：{case['explanation']}。"
        )
    lines.append("")
    if len(cases) < 5:
        lines.append("> 警告：本次数据下差异案例少于 5 个，放宽筛选或增大采样可补充。\n")

    lines.append("## 4. 结论\n")
    lines.append(
        f"1. **v3 保持了 v2 的主要排序结构**：{summary['n_boards']} 块板平均 Spearman "
        f"{summary['mean_spearman_v2_v3']:.4f}、top-{TOP_K} 平均重叠 "
        f"{summary[overlap_key]:.2f}，说明层/网络类细化没有推翻原有物理排序。"
    )
    lines.append(
        f"2. **层数/铜厚是 v3 的新自由度**：同一布局 2→6 层平均降分 "
        f"{summary['mean_layer_drop_pct']:.2f}%，1→2 oz 铜厚平均降分 "
        f"{summary['mean_copper_drop_pct']:.2f}%；回路电感、PDN 阻抗、热升分项都随层数/铜厚单调下降。"
    )
    lines.append(
        f"3. **确实存在 v2 判好但 v3 判差的布局（{len(cases)} 个）**：主要来自 v2 看不见的风险——"
        "RF/模拟/数字网络贴近功率级（v3 按 net class 加权）、敏感信号回路跨度过大、"
        "以及少层/薄铜下的回路电感与过孔/PDN 代价。主导项统计："
        + "，".join(
            f"`{term}` {count}"
            for term, count in summary["dominant_terms"].items()
        )
        + "。"
    )
    lines.append(
        "4. **可复现**：v2/v3 评分、隐藏系数、随机布局与差异案例筛选全部确定性；"
        "真实板来自只读 EasyCirq dump（单位 mil，转换见 `mp_place.realboard`）。"
    )
    lines.append("")
    lines.append("## 5. 边界（NOT RUN / 限制）\n")
    lines.append(
        "- v3 仍是**解析伪物理模型**（层/铜厚/过孔/网络类的一阶近似），不是 SPICE/FEA/场求解器；"
        "SI/PI/热/EMC 全部未仿真。"
    )
    lines.append(
        "- 层数与铜厚来自场景属性/默认值（真实板取 dump 的 `copperLayers`，均为 2 层；铜厚默认 1 oz），"
        "并非每块板的真实压合结构。"
    )
    lines.append(
        "- 真实板 Scenario 来自 `mp_place.realboard` 的换算（mil→mm、板框取 bbox），"
        "原布局仅用于评分，未施加、未 DRC、未布线验证。"
    )
    lines.append(
        "- 差异案例的“物理解释”是**基于分项代价与几何量的假说**，用于训练判读，不是实测结论。"
    )
    if data.get("missing_real_boards"):
        lines.append(f"- 缺失/失败的真实板：{[row['name'] for row in data['missing_real_boards']]}")
    return "\n".join(lines) + "\n"


def write_report(
    data: Dict[str, Any], out_dir: Optional[pathlib.Path | str] = None
) -> Tuple[pathlib.Path, pathlib.Path]:
    """Write ``report_physics_v3.md`` and ``report_physics_v3.json``."""
    out = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "report_physics_v3.md"
    json_path = out / "report_physics_v3.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    md_path.write_text(render_markdown(data), encoding="utf-8")
    return md_path, json_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P2.13 physics v3 vs v2 comparison study")
    parser.add_argument("--out", default=str(PROJECT_ROOT))
    parser.add_argument("--n-random", type=int, default=N_RANDOM)
    args = parser.parse_args(argv)
    data = run_comparison(n_random=max(5, int(args.n_random)))
    md_path, json_path = write_report(data, pathlib.Path(args.out))
    print(f"[v3] wrote {md_path} / {json_path} ({data['runtime_s']} s)")
    return 0


__all__ = [
    "CAPACITY_TEMPLATES",
    "COMPONENT_TERMS",
    "N_RANDOM",
    "PhysicsSimulatorV3",
    "extract_features_v3",
    "main",
    "render_markdown",
    "run_comparison",
    "write_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
