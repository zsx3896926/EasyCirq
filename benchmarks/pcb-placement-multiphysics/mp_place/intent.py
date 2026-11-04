"""Layout intent: hierarchical module tree (HMT) + relative constraints (CCG).

The P1/P2 stack needs an explicit placement for every evaluation.  A *layout
intent* is the human/engineering-level description of that placement instead:
which parts form which functional module (电源 / 模拟 / 数字 / 接口 / RF), where
they sit, and which relative placement relations (near / clearance / cluster /
edge) the layout is supposed to preserve.  It is plain JSON-friendly data, so a
template + intent pair can be stored, diffed, reviewed and replayed without the
solver or any simulator.

Definitions used here
---------------------
HMT (hierarchical module tree)
    ``intent["module_tree"]`` is a two-level tree.  The root is the board; its
    children are the five stable module ids in :data:`MODULE_KEYS`.  Each module
    node lists its member component refs, the nets it touches, its geometric
    extent (bbox/centroid) and its total power dissipation.

CCG (component constraint graph)
    ``intent["constraints"]`` is a flat list of relative constraints whose
    ``type`` is one of ``near``, ``clearance``, ``cluster`` or ``edge``.  The
    constraints are derived from the concrete placement handed to
    :func:`build_intent`, so they are satisfied by that placement by
    construction.  :func:`intent_violations` is an independent checker.

Round trip
----------
``build_intent`` -> ``json.dumps`` -> ``json.loads`` -> ``intent_to_plan``
restores the exact centre coordinates (JSON doubles round-trip bit-exactly)
and therefore reproduces a hard-feasible placement.

Pure standard library; depends only on :mod:`mp_place.model`.
"""

from __future__ import annotations

import math
from typing import Dict, List, Mapping, Optional, Tuple

from .model import Placement, Scenario, bbox, comp_pad_distance

INTENT_SCHEMA = "easycirq.intent"
INTENT_VERSION = 1

#: Stable module ids of the HMT, in canonical order.
MODULE_KEYS: Tuple[str, ...] = ("power", "analog", "digital", "interface", "rf")

MODULE_LABELS: Dict[str, str] = {
    "power": "电源模块",
    "analog": "模拟模块",
    "digital": "数字模块",
    "interface": "接口模块",
    "rf": "射频模块",
}

CCG_TYPES: Tuple[str, ...] = ("near", "clearance", "cluster", "edge")

#: Pairs of modules that should stay physically separated (noise/isolation).
_CLEARANCE_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("rf", "power"),
    ("rf", "analog"),
    ("rf", "digital"),
    ("analog", "power"),
)

#: Component kind -> HMT module.  Kinds not listed fall back to net classes.
_KIND_MODULE: Dict[str, str] = {
    "connector": "interface",
    "header": "interface",
    "terminal": "interface",
    "antenna": "rf",
    "rf": "rf",
    "rf_module": "rf",
    "transceiver": "rf",
    "mcu": "digital",
    "cpu": "digital",
    "fpga": "digital",
    "logic": "digital",
    "memory": "digital",
    "power_switch": "power",
    "inductor": "power",
    "ferrite": "power",
    "input_cap": "power",
    "output_cap": "power",
    "ldo": "power",
    "regulator": "power",
    "pmic": "power",
    "crystal": "analog",
    "analog": "analog",
    "opamp": "analog",
    "adc": "analog",
    "dac": "analog",
    "sensor": "analog",
    "diode": "analog",
}

#: Net class -> HMT module; ``generic`` maps to ``None`` (no opinion).
_CLASS_MODULE: Dict[str, Optional[str]] = {
    "power": "power",
    "ground": "power",
    "analog": "analog",
    "digital": "digital",
    "rf": "rf",
    "generic": None,
}

#: Priority used when only net classes are available (e.g. decoupling caps).
_FALLBACK_PRIORITY: Tuple[str, ...] = ("power", "analog", "rf", "digital")

#: CCG ``near`` constraints are emitted for net-connected pins closer than this.
_NEAR_LIMIT_MM = 15.0

#: CCG ``clearance`` constraints need at least this pad gap to be meaningful.
_CLEARANCE_MIN_MM = 2.0


# --------------------------------------------------------------------------- #
# Module classification (HMT)
# --------------------------------------------------------------------------- #
def _net_classes_by_ref(sc: Scenario) -> Dict[str, set]:
    """Map component ref -> set of net classes it participates in."""
    out: Dict[str, set] = {ref: set() for ref in sc.components}
    for net in sc.nets:
        for ref, _pin in net.pins:
            if ref in out:
                out[ref].add(net.cls)
    return out


def component_module(
    sc: Scenario, ref: str, net_classes: Optional[set] = None
) -> str:
    """Return the HMT module id for one component (always one of MODULE_KEYS).

    The component ``kind`` is authoritative; parts with an engineering kind
    that does not encode a module (e.g. ``decap``) fall back to the classes of
    the nets they touch.  Unclassifiable parts land in ``digital`` so the module
    tree always partitions the whole design.
    """
    comp = sc.components[ref]
    kind = comp.kind.strip().lower()
    module = _KIND_MODULE.get(kind)
    if module is not None:
        return module
    if comp.edge is not None:
        return "interface"
    if net_classes is None:
        net_classes = _net_classes_by_ref(sc).get(ref, set())
    mapped = {
        m for m in (_CLASS_MODULE.get(cls) for cls in net_classes) if m is not None
    }
    for key in _FALLBACK_PRIORITY:
        if key in mapped:
            return key
    return "digital"


def module_members(sc: Scenario) -> Dict[str, List[str]]:
    """Partition all components into HMT modules (sorted, deterministic)."""
    classes = _net_classes_by_ref(sc)
    members: Dict[str, List[str]] = {key: [] for key in MODULE_KEYS}
    for ref in sc.components:
        members[component_module(sc, ref, classes.get(ref, set()))].append(ref)
    for key in MODULE_KEYS:
        members[key].sort()
    return members


# --------------------------------------------------------------------------- #
# Small coordinate helpers
# --------------------------------------------------------------------------- #
def _coord(value) -> Tuple[float, float, int]:
    """Normalise a placement entry to ``(float x, float y, int rot)``."""
    if isinstance(value, Mapping):
        value = (value.get("x"), value.get("y"), value.get("rot", 0))
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f"bad placement coordinate {value!r}; expected [x, y, rot]")
    try:
        x, y, rot_f = float(value[0]), float(value[1]), float(value[2])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bad placement coordinate {value!r}") from exc
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"non-finite placement coordinate {value!r}")
    rot = int(rot_f)
    if rot != rot_f:
        raise ValueError(f"rotation must be whole degrees, got {value[2]!r}")
    return x, y, rot


def _edge_distance(sc: Scenario, box: Tuple[float, float, float, float], edge: str) -> float:
    """Distance from a component bbox to the named board edge."""
    if edge == "left":
        return box[0]
    if edge == "right":
        return sc.board_w - box[2]
    if edge == "top":
        return sc.board_h - box[3]
    if edge == "bottom":
        return box[1]
    raise ValueError(f"unknown board edge {edge!r}")


def _require_schema(intent) -> None:
    """Validate the intent envelope; raise ``TypeError``/``ValueError``."""
    if not isinstance(intent, Mapping):
        raise TypeError(f"intent must be a mapping, got {type(intent).__name__}")
    if intent.get("schema") != INTENT_SCHEMA:
        raise ValueError(
            f"unsupported intent schema {intent.get('schema')!r}; expected {INTENT_SCHEMA!r}"
        )
    try:
        version = int(intent.get("schema_version"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bad intent schema_version {intent.get('schema_version')!r}") from exc
    if version != INTENT_VERSION:
        raise ValueError(f"unsupported intent version {version}; expected {INTENT_VERSION}")


# --------------------------------------------------------------------------- #
# CCG constraint derivation
# --------------------------------------------------------------------------- #
def _near_constraints(sc: Scenario, placement: Placement) -> List[dict]:
    """One ``near`` constraint per net: its closest pad pair, if tight enough."""
    out: List[dict] = []
    for net in sc.nets:
        refs = sorted({ref for ref, _pin in net.pins if ref in sc.components})
        if len(refs) < 2:
            continue
        best: Optional[Tuple[float, str, str]] = None
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                a, b = refs[i], refs[j]
                dist = comp_pad_distance(sc, placement, a, b)
                if best is None or dist < best[0]:
                    best = (dist, a, b)
        if best is not None and best[0] <= _NEAR_LIMIT_MM:
            dist, a, b = best
            out.append(
                {
                    "type": "near",
                    "a": a,
                    "b": b,
                    "net": net.name,
                    "max_mm": round(dist + 0.5, 3),
                }
            )
    out.sort(key=lambda c: (c["a"], c["b"], c["net"]))
    return out


def _clearance_constraints(sc: Scenario, placement: Placement, members: Dict[str, List[str]]) -> List[dict]:
    """Closest component pair between noise-sensitive module pairs."""
    out: List[dict] = []
    for module_a, module_b in _CLEARANCE_PAIRS:
        refs_a, refs_b = members.get(module_a, []), members.get(module_b, [])
        if not refs_a or not refs_b:
            continue
        best: Optional[Tuple[float, str, str]] = None
        for a in refs_a:
            for b in refs_b:
                dist = comp_pad_distance(sc, placement, a, b)
                if best is None or dist < best[0]:
                    best = (dist, a, b)
        if best is None:
            continue
        dist, a, b = best
        if dist >= _CLEARANCE_MIN_MM:
            out.append(
                {
                    "type": "clearance",
                    "a": a,
                    "b": b,
                    "a_module": module_a,
                    "b_module": module_b,
                    "min_mm": round(max(0.5, dist - 1.0), 3),
                }
            )
    return out


def _cluster_constraints(sc: Scenario, placement: Placement, members: Dict[str, List[str]]) -> List[dict]:
    """Keep each multi-part module inside a disc around its own centroid."""
    out: List[dict] = []
    for key in MODULE_KEYS:
        refs = members.get(key, [])
        if len(refs) < 2:
            continue
        cx = sum(placement[r][0] for r in refs) / len(refs)
        cy = sum(placement[r][1] for r in refs) / len(refs)
        max_dist = max(
            math.hypot(placement[r][0] - cx, placement[r][1] - cy) for r in refs
        )
        out.append(
            {
                "type": "cluster",
                "module": key,
                "members": list(refs),
                "center": [round(cx, 3), round(cy, 3)],
                "radius_mm": round(max_dist + 0.5, 3),
            }
        )
    return out


def _edge_constraints(sc: Scenario) -> List[dict]:
    """Every edge-declared connector keeps its board-edge relation."""
    out: List[dict] = []
    for ref in sorted(sc.components):
        edge = sc.components[ref].edge
        if edge is None:
            continue
        out.append({"type": "edge", "ref": ref, "edge": edge, "tol": float(sc.edge_tol)})
    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_intent(sc: Scenario, placement: Placement) -> dict:
    """Describe ``placement`` as a JSON-serialisable layout intent.

    Returns a dict with (among others):
      * ``schema`` / ``schema_version`` — intent envelope version;
      * ``module_tree`` — HMT root + five module nodes;
      * ``coordinates`` — ``{ref: [x_mm, y_mm, rot_deg]}`` for every part;
      * ``constraints`` — flat CCG list (near/clearance/cluster/edge, ids
        ``ccg-0001``...), plus ``constraint_counts``;
      * ``components`` / ``nets`` / ``keepouts`` / ``fixed`` — self-contained
        board description so the intent can be reviewed outside the solver.

    Raises ``ValueError`` if ``placement`` does not cover every component.
    """
    missing = [ref for ref in sc.components if ref not in placement]
    if missing:
        raise ValueError(f"placement is missing components: {sorted(missing)}")

    coords: Dict[str, List] = {}
    for ref in sc.components:
        x, y, rot = _coord(placement[ref])
        coords[ref] = [x, y, rot]

    members = module_members(sc)
    module_of: Dict[str, str] = {}
    for key in MODULE_KEYS:
        for ref in members[key]:
            module_of[ref] = key

    # --- HMT nodes -------------------------------------------------------
    modules: Dict[str, dict] = {}
    for key in MODULE_KEYS:
        refs = members[key]
        refs_set = set(refs)
        node: dict = {
            "id": key,
            "label": MODULE_LABELS[key],
            "role": key,
            "parent": "root",
            "depth": 1,
            "present": bool(refs),
            "members": list(refs),
            "nets": sorted(
                net.name
                for net in sc.nets
                if any(ref in refs_set for ref, _pin in net.pins)
            ),
            "power_w": round(sum(sc.components[r].power_w for r in refs), 4),
            "bbox": None,
            "centroid": None,
            "children": [],
        }
        if refs:
            boxes = [bbox(sc.components[r], coords[r][0], coords[r][1], coords[r][2]) for r in refs]
            node["bbox"] = [
                round(min(b[0] for b in boxes), 3),
                round(min(b[1] for b in boxes), 3),
                round(max(b[2] for b in boxes), 3),
                round(max(b[3] for b in boxes), 3),
            ]
            cx = sum(coords[r][0] for r in refs) / len(refs)
            cy = sum(coords[r][1] for r in refs) / len(refs)
            node["centroid"] = [round(cx, 3), round(cy, 3)]
        modules[key] = node

    # --- CCG constraints -------------------------------------------------
    raw_constraints = (
        _near_constraints(sc, placement)
        + _clearance_constraints(sc, placement, members)
        + _cluster_constraints(sc, placement, members)
        + _edge_constraints(sc)
    )
    constraints: List[dict] = []
    for index, item in enumerate(raw_constraints, start=1):
        entry: dict = {"id": f"ccg-{index:04d}"}
        entry.update(item)
        constraints.append(entry)
    counts = {ctype: 0 for ctype in CCG_TYPES}
    for item in constraints:
        counts[item["type"]] += 1

    # --- board description ----------------------------------------------
    nets = [
        {
            "name": net.name,
            "cls": net.cls,
            "pins": [[str(ref), str(pin)] for ref, pin in net.pins],
            "modules": sorted({module_of[ref] for ref, _pin in net.pins if ref in module_of}),
        }
        for net in sc.nets
    ]

    fixed = sorted(ref for ref, comp in sc.components.items() if comp.fixed)
    components = {
        ref: {
            "kind": comp.kind,
            "module": module_of[ref],
            "w": float(comp.w),
            "h": float(comp.h),
            "fixed": bool(comp.fixed),
            "power_w": float(comp.power_w),
            "rotations": [int(r) for r in comp.rotations],
            "pins": sorted(comp.pins),
        }
        for ref, comp in sc.components.items()
    }

    return {
        "schema": INTENT_SCHEMA,
        "schema_version": INTENT_VERSION,
        "generator": "mp_place.intent",
        "scenario": {
            "name": sc.name,
            "component_count": len(sc.components),
            "net_count": len(sc.nets),
            "keepout_count": len(sc.keepouts),
        },
        "board": {
            "w": float(sc.board_w),
            "h": float(sc.board_h),
            "edge_tol": float(sc.edge_tol),
        },
        "module_tree": {
            "schema": "hmt/1",
            "root": {
                "id": "root",
                "label": sc.name,
                "kind": "board",
                "parent": None,
                "depth": 0,
                "children": list(MODULE_KEYS),
            },
        },
        "modules": modules,
        "coordinates": coords,
        "fixed": fixed,
        "components": components,
        "nets": nets,
        "keepouts": [
            [float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])]
            for rect in sc.keepouts
        ],
        "constraints": constraints,
        "constraint_counts": counts,
        "summary": {
            "components": len(sc.components),
            "nets": len(sc.nets),
            "present_modules": sum(1 for key in MODULE_KEYS if modules[key]["present"]),
            "fixed": len(fixed),
            "constraints": len(constraints),
        },
    }


def intent_to_plan(sc: Scenario, intent) -> Placement:
    """Replay the coordinates recorded in ``intent`` into a :class:`Placement`.

    The scenario supplies the component set (so ``intent`` may carry extra
    metadata, and refs are iterated in ``sc.components`` order).  Every
    component must have a coordinate; a missing one raises ``ValueError``.
    No feasibility repair is performed -- the intent is expected to be valid;
    validate the result with :func:`mp_place.model.hard_violations`.
    """
    _require_schema(intent)
    coordinates = intent.get("coordinates")
    if not isinstance(coordinates, Mapping):
        raise ValueError("intent has no 'coordinates' mapping")
    plan: Placement = {}
    missing: List[str] = []
    for ref in sc.components:
        if ref not in coordinates:
            missing.append(ref)
            continue
        x, y, rot = _coord(coordinates[ref])
        plan[ref] = (x, y, rot)
    if missing:
        raise ValueError(f"intent is missing coordinates for: {sorted(missing)}")
    return plan


def intent_violations(sc: Scenario, placement: Placement, intent) -> List[str]:
    """Independent checker for the CCG constraints of ``intent``.

    Returns human-readable violation strings (empty == every relative
    constraint is satisfied by ``placement``).  This is intentionally separate
    from :func:`build_intent` so a stored intent can be validated against any
    later plan.
    """
    _require_schema(intent)
    violations: List[str] = []
    for ref in sc.components:
        if ref not in placement:
            violations.append(f"missing_placement:{ref}")
    if violations:
        return violations

    known_refs = set(sc.components)
    for item in intent.get("constraints", []):
        if not isinstance(item, Mapping):
            violations.append("malformed_constraint")
            continue
        ctype = item.get("type")
        cid = item.get("id", "?")
        if ctype == "near":
            a, b = item.get("a"), item.get("b")
            if a not in known_refs or b not in known_refs:
                violations.append(f"{cid}:near:unknown_ref")
                continue
            dist = comp_pad_distance(sc, placement, a, b)
            limit = float(item["max_mm"])
            if dist > limit + 1e-9:
                violations.append(f"{cid}:near:{a}:{b}:{dist:.6f}>{limit:.6f}")
        elif ctype == "clearance":
            a, b = item.get("a"), item.get("b")
            if a not in known_refs or b not in known_refs:
                violations.append(f"{cid}:clearance:unknown_ref")
                continue
            dist = comp_pad_distance(sc, placement, a, b)
            limit = float(item["min_mm"])
            if dist < limit - 1e-9:
                violations.append(f"{cid}:clearance:{a}:{b}:{dist:.6f}<{limit:.6f}")
        elif ctype == "cluster":
            center = item.get("center") or [0.0, 0.0]
            cx, cy = float(center[0]), float(center[1])
            radius = float(item["radius_mm"])
            for ref in item.get("members", []):
                if ref not in known_refs:
                    violations.append(f"{cid}:cluster:unknown_ref:{ref}")
                    continue
                x, y, _rot = placement[ref]
                dist = math.hypot(x - cx, y - cy)
                if dist > radius + 1e-9:
                    violations.append(f"{cid}:cluster:{ref}:{dist:.6f}>{radius:.6f}")
        elif ctype == "edge":
            ref = item.get("ref")
            if ref not in known_refs:
                violations.append(f"{cid}:edge:unknown_ref")
                continue
            box = bbox(sc.components[ref], *placement[ref])
            dist = _edge_distance(sc, box, str(item.get("edge")))
            tol = float(item["tol"])
            if dist > tol + 1e-9:
                violations.append(f"{cid}:edge:{ref}:{dist:.6f}>{tol:.6f}")
        else:
            violations.append(f"{cid}:unknown_constraint_type:{ctype!r}")
    return violations


__all__ = [
    "INTENT_SCHEMA",
    "INTENT_VERSION",
    "MODULE_KEYS",
    "MODULE_LABELS",
    "CCG_TYPES",
    "build_intent",
    "intent_to_plan",
    "intent_violations",
    "component_module",
    "module_members",
]
