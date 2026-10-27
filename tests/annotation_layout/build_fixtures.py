#!/usr/bin/env python3
"""Generate the committed synthetic, holdout and benchmark fixtures.

All cases are clearly synthetic; the real frozen case is copied from the
photo-led v14 conversion.  This script is deterministic; re-running it with the
same package version must reproduce the same bytes (timings are not embedded).

Run from the repository root with::

    PYTHONPATH=design-hardware/scripts python tests/annotation_layout/build_fixtures.py

It also searches a small deterministic space for two illustrative cases:
* a case where the naive baseline leaves a hard conflict but the batch solver
  clears it (`dense-counterexample`);
* a case whose bounded search exhausts the state budget (reported as
  `budget_exhausted`, not as infeasibility).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "design-hardware" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from annotation_layout.baseline import solve_baseline  # noqa: E402
from annotation_layout.candidates import generate_candidates  # noqa: E402
from annotation_layout.conflicts import evaluate_assignment  # noqa: E402
from annotation_layout.model import SCHEMA_ID, Counters, InputError  # noqa: E402
from annotation_layout.schema import validate_input  # noqa: E402
from annotation_layout.solver import solve  # noqa: E402

SYNTHETIC_DIR = ROOT / "tests" / "annotation_layout" / "fixtures" / "synthetic"
HOLDOUT_DIR = ROOT / "tests" / "annotation_layout" / "fixtures" / "holdout"
INVALID_DIR = ROOT / "tests" / "annotation_layout" / "fixtures" / "invalid"
BENCH_DIR = ROOT / "benchmarks" / "annotation-layout" / "cases"
REAL_INPUT = ROOT / "tests" / "annotation_layout" / "fixtures" / "photo-led-v14" / "input.json"

PAGE = [0.0, 0.0, 1170.0, 825.0]
USABLE = [10.0, 10.0, 1160.0, 815.0]
TITLE = [900.0, 10.0, 1160.0, 190.0]
ZONES = [
    {"id": "zA", "name": "1 upper left", "bbox": [40.0, 400.0, 560.0, 790.0],
     "hard": False, "source": "synthetic_declared"},
    {"id": "zB", "name": "2 upper right", "bbox": [600.0, 400.0, 1130.0, 790.0],
     "hard": False, "source": "synthetic_declared"},
    {"id": "zC", "name": "3 lower left", "bbox": [40.0, 40.0, 560.0, 380.0],
     "hard": False, "source": "synthetic_declared"},
    {"id": "zD", "name": "4 lower right", "bbox": [600.0, 200.0, 1130.0, 380.0],
     "hard": False, "source": "synthetic_declared"},
]

DEFAULT_CONSTRAINTS = {
    "grid": 5,
    "min_text_text_gap": 2,
    "min_text_symbol_gap": 2,
    "min_text_wire_gap": 0,
    "min_text_wire_clearance": 5,
    "self_text_contact_tolerance": 1,
    "label_own_wire_edge_tolerance": 1,
    "max_candidates_per_annotation": 32,
    "max_total_candidates": 800,
    "max_search_states": 20000,
    "max_local_search_steps": 2000,
    "max_displacement": 80,
    "owner_max_distance": 250,
    "forbid_font_change": True,
    "forbid_content_change": True,
    "forbid_net_change": True,
    "forbid_component_move": True,
    "freeze_ids": [],
    "scope": "all",
    "scope_cluster_ids": [],
}

DEFAULT_HOST = {
    "capabilities": {
        "attribute_translate": "supported",
        "free_text_translate": "unverified",
        "net_label_detach": "unsupported",
        "attribute_rotate": "unsupported",
    },
    "capability_source": "synthetic_declared",
    "execution": "not_executed",
}


def rect(x0: float, y0: float, width: float, height: float) -> List[float]:
    return [x0, y0, x0 + width, y0 + height]


def component(identity: str, box: Sequence[float], designator: str,
              zone_id: Optional[str]) -> Dict[str, Any]:
    return {"id": identity, "bbox": list(box), "designator": designator,
            "zone_id": zone_id}


def wire(identity: str, points: Sequence[Sequence[float]],
         net: Optional[str] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"id": identity,
                            "points": [[float(x), float(y)] for x, y in points],
                            "primitive_id": identity}
    if net:
        item["net"] = net
    return item


def fixed_text(identity: str, kind: str, content: str, box: Sequence[float],
               owner_id: Optional[str] = None, net: Optional[str] = None,
               anchor_id: Optional[str] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "id": identity, "bbox": list(box), "kind": kind, "content": content,
        "measurement": "bbox",
    }
    if owner_id:
        item["owner_id"] = owner_id
        item["owner_kind"] = "component" if kind in (
            "attribute", "pin_name", "pin_number", "symbol_text") else "netflag"
    if net:
        item["net"] = net
    if anchor_id:
        item["anchor_id"] = anchor_id
        item["anchored"] = True
    return item


def annotation(identity: str, role: str, content: str, box: Sequence[float], *,
               owner_id: Optional[str] = None, owner_kind: str = "component",
               zone_id: Optional[str] = None, keep_in_zone: bool = False,
               translate: Optional[str] = None, bbox_source: str = "measured_svg",
               rotation: Optional[float] = None, align: str = "unknown",
               anchor: Optional[Sequence[float]] = None,
               net: Optional[str] = None, anchor_id: Optional[str] = None,
               max_displacement: float = 80.0,
               allowed_directions: Sequence[str] = ("left", "right", "up", "down"),
               grid: float = 5.0, priority: int = 0) -> Dict[str, Any]:
    if translate is None:
        translate = "unverified" if role in ("free_text", "purpose_text") else "supported"
    if owner_id is None:
        owner = {"kind": "zone", "id": zone_id, "requirement": "inside_zone"} if zone_id \
            else {"kind": "page", "id": "page", "requirement": "none"}
    else:
        owner = {"kind": owner_kind, "id": owner_id,
                 "requirement": "keep_near" if owner_kind == "component" else "inside_zone"}
    return {
        "id": identity,
        "role": role,
        "content": content,
        "kind": "attribute" if role in ("designator", "value") else "free_text",
        "field": "attribute" if role in ("designator", "value") else None,
        "current": {
            "bbox": list(box),
            "anchor": list(anchor) if anchor else None,
            "anchor_source": "declared" if anchor else "unknown",
            "align": align,
            "rotation_deg": rotation,
            "rotation_source": "declared" if rotation is not None else "unknown",
            "font_size": None,
            "font_source": "unknown",
        },
        "bbox_source": bbox_source,
        "owner": owner,
        "net": net,
        "anchor_id": anchor_id,
        "capability": {
            "translate": translate,
            "rotate": "fixed",
            "resize": "forbidden",
            "content_change": "forbidden",
            "net_change": "forbidden",
            "source": "synthetic_declared",
        },
        "constraints": {
            "zone_id": zone_id,
            "keep_in_zone": keep_in_zone,
            "allowed_directions": list(allowed_directions),
            "max_displacement": max_displacement,
            "grid": grid,
            "owner_max_distance": 250,
            "priority": priority,
        },
    }


def document(name: str, *, components: Sequence[Mapping[str, Any]] = (),
             wires: Sequence[Mapping[str, Any]] = (),
             fixed_texts: Sequence[Mapping[str, Any]] = (),
             annotations: Sequence[Mapping[str, Any]] = (),
             constraints: Optional[Mapping[str, Any]] = None,
             host: Optional[Mapping[str, Any]] = None,
             zones: Optional[Sequence[Mapping[str, Any]]] = None,
             notes: str = "synthetic fixture; not a real board") -> Dict[str, Any]:
    return {
        "schema": SCHEMA_ID,
        "project": {
            "name": f"synthetic-{name}",
            "page_id": f"page-{name}",
            "page_name": "P1",
            "snapshot_sha256": hashlib.sha256(name.encode("utf-8")).hexdigest(),
        },
        "source": {
            "kind": "synthetic",
            "adapter": "tests/annotation_layout/build_fixtures.py",
            "source_commit": "9a951edc21481dc3ae91460acc11aa3e08a7be8a",
            "created": "2026-10-27",
            "notes": notes,
            "files": [],
        },
        "units": {"name": "schematic_raw", "raw_per_mm": 3.937007874015748,
                  "description": "synthetic raw units; 10 raw = 2.54 mm"},
        "coordinate_system": {
            "name": "synthetic-raw-y-up", "y_axis": "up", "svg_y_axis": "down",
            "transform": "screen_y = page_height - raw_y (analysis overlay only)",
        },
        "page": {
            "bbox": list(PAGE), "usable_bbox": list(USABLE),
            "title_block": {"id": "titleBlock", "bbox": list(TITLE), "hard": True},
            "keepouts": [{"id": "titleBlock", "bbox": list(TITLE), "hard": True,
                          "reason": "synthetic title block"}],
            "zones": [dict(zone) for zone in (zones or ZONES)],
        },
        "components": [dict(item) for item in components],
        "wires": [dict(item) for item in wires],
        "fixed_texts": [dict(item) for item in fixed_texts],
        "movable_annotations": [dict(item) for item in annotations],
        "constraints": dict(DEFAULT_CONSTRAINTS, **(constraints or {})),
        "host": host or dict(DEFAULT_HOST),
        "uncertainty": {
            "bbox_measured": True,
            "font_metrics_known": False,
            "symbol_outline_approximate": True,
            "notes": ["synthetic geometry; no real EDA snapshot"],
        },
        "checker_context": {},
    }


# ---------------------------------------------------------------------------
# scenarios


def scenario_text_text() -> Dict[str, Any]:
    return document(
        "text-text",
        components=[component("C1", rect(100, 660, 40, 30), "R1", "zA"),
                    component("C2", rect(160, 660, 40, 30), "R2", "zA")],
        annotations=[
            annotation("A1", "value", "10kΩ", rect(100, 692, 25, 10), owner_id="C1",
                       zone_id="zA"),
            annotation("A2", "value", "10kΩ", rect(118, 692, 25, 10), owner_id="C2",
                       zone_id="zA"),
        ],
        notes="two value texts overlap; deterministic synthetic conflict",
    )


def scenario_text_symbol() -> Dict[str, Any]:
    return document(
        "text-symbol",
        components=[component("C1", rect(300, 660, 40, 30), "R3", "zA")],
        annotations=[
            annotation("A1", "value", "4.7kΩ", rect(300, 687, 26, 10), owner_id="C1",
                       zone_id="zA"),
            annotation("A2", "designator", "R3", rect(300, 645, 12, 10), owner_id="C1",
                       zone_id="zA"),
        ],
        notes="value text overlaps its own symbol body by 3 raw",
    )


def scenario_text_wire() -> Dict[str, Any]:
    return document(
        "text-wire",
        wires=[wire("W1", [(80, 506), (260, 506)])],
        annotations=[
            annotation("A1", "free_text", "sensor note", rect(100, 500, 120, 12),
                       zone_id="zA", keep_in_zone=True),
        ],
        notes="free-text bbox is crossed by a wire",
    )


def scenario_rotated() -> Dict[str, Any]:
    return document(
        "rotated",
        components=[component("C1", rect(360, 460, 30, 30), "R9", "zA")],
        fixed_texts=[fixed_text("F1", "netflag", "GND", rect(405, 510, 30, 10),
                                net="GND")],
        annotations=[
            annotation("A1", "value", "100kΩ", rect(400, 500, 10, 40), owner_id="C1",
                       zone_id="zA", rotation=90.0),
        ],
        notes="declared 90-degree value text overlaps a fixed netflag text; "
              "translation only, rotation must not change",
    )


def scenario_chinese_purpose() -> Dict[str, Any]:
    return document(
        "chinese-purpose",
        wires=[wire("W1", [(60, 446), (220, 446)])],
        annotations=[
            annotation("A1", "free_text", "光敏分压滤波", rect(80, 440, 120, 12),
                       zone_id="zA", keep_in_zone=True),
        ],
        notes="Chinese purpose text crossed by a wire; stays inside its zone",
    )


def scenario_title_block() -> Dict[str, Any]:
    return document(
        "title-block",
        annotations=[
            annotation("A1", "free_text", "stray note", rect(950, 100, 100, 12),
                       max_displacement=120),
        ],
        constraints={"max_displacement": 150, "max_candidates_per_annotation": 40},
        notes="free text sits inside the title-block keep-out",
    )


def scenario_zone_boundary() -> Dict[str, Any]:
    return document(
        "zone-boundary",
        fixed_texts=[fixed_text("F1", "free_text", "fixed note",
                                rect(300, 600, 120, 12))],
        annotations=[
            annotation("A1", "free_text", "movable note", rect(380, 600, 120, 12),
                       zone_id="zA", keep_in_zone=True),
        ],
        notes="free text overlaps a fixed text and must stay inside zone zA",
    )


def scenario_lock_frozen() -> Dict[str, Any]:
    doc = scenario_text_text()
    doc["project"]["name"] = "synthetic-lock-frozen"
    doc["project"]["page_id"] = "page-lock-frozen"
    doc["constraints"]["freeze_ids"] = ["A2"]
    doc["source"]["notes"] = "same overlap as text-text but A2 is frozen by policy"
    return doc


def scenario_no_candidates() -> Dict[str, Any]:
    tiny_zone = {"id": "tiny", "name": "tiny zone", "bbox": [44.0, 404.0, 116.0, 418.0],
                 "hard": False, "source": "synthetic_declared"}
    return document(
        "no-candidates",
        zones=[tiny_zone],
        fixed_texts=[fixed_text("F1", "free_text", "blocker",
                                rect(100, 405, 40, 12))],
        annotations=[
            annotation("A1", "free_text", "stuck", rect(45, 405, 70, 12),
                       zone_id="tiny", keep_in_zone=True),
        ],
        notes="the declared zone leaves no legal grid translation; "
              "expect all_candidates_rejected rather than a fake fix",
    )


def scenario_estimated() -> Dict[str, Any]:
    doc = scenario_text_text()
    doc["project"]["name"] = "synthetic-estimated"
    doc["project"]["page_id"] = "page-estimated"
    doc["movable_annotations"][0]["bbox_source"] = "estimated"
    doc["source"]["notes"] = "first value text has an estimated bbox; no plan_verified claim"
    return doc


def scenario_net_anchor() -> Dict[str, Any]:
    return document(
        "net-anchor",
        wires=[wire("W1", [(200, 500), (400, 500)], net="VREF")],
        fixed_texts=[],
        annotations=[
            annotation("A1", "net_label", "VREF", rect(260, 495, 40, 10),
                       owner_id="W1", owner_kind="net",
                       translate="unsupported", net="VREF", anchor_id="W1"),
        ],
        notes="net label text is crossed by its own wire but host text/anchor "
              "separation is unsupported; expect a blocking host-capability reason",
    )


def scenario_clean() -> Dict[str, Any]:
    return document(
        "clean",
        components=[component("C1", rect(100, 660, 40, 30), "R1", "zA")],
        annotations=[
            annotation("A1", "value", "10kΩ", rect(100, 692, 25, 10), owner_id="C1",
                       zone_id="zA"),
            annotation("A2", "designator", "R1", rect(100, 645, 12, 10), owner_id="C1",
                       zone_id="zA"),
        ],
        notes="already clean; plan must be a no-op",
    )


def scenario_dense() -> Dict[str, Any]:
    components = [component(f"C{i}", rect(100 + i * 30, 600, 24, 20), f"R{i}", "zA")
                  for i in range(1, 7)]
    annotations = [
        annotation(f"A{i}", "value", f"{i}kΩ", rect(100 + i * 30, 630, 24, 10),
                   owner_id=f"C{i}", zone_id="zA")
        for i in range(1, 7)
    ]
    # force a chain of overlaps: shift every other value left by 12 raw
    for index, item in enumerate(annotations):
        if index % 2 == 1:
            item["current"]["bbox"][0] -= 12.0
            item["current"]["bbox"][2] -= 12.0
    return document(
        "dense",
        components=components,
        fixed_texts=[fixed_text("F1", "free_text", "keeper note", rect(120, 660, 120, 12))],
        annotations=annotations,
        notes="six value texts in a horizontal chain with overlaps; batch case",
    )


def scenario_cluster_a() -> Dict[str, Any]:
    return document(
        "cluster-a",
        annotations=[
            annotation("A1", "value", "10kΩ", rect(100, 692, 25, 10), owner_id="C1",
                       zone_id="zA"),
            annotation("A2", "value", "10kΩ", rect(118, 692, 25, 10), owner_id="C2",
                       zone_id="zA"),
            annotation("A3", "value", "1kΩ", rect(700, 692, 20, 10), owner_id="C3",
                       zone_id="zB"),
            annotation("A4", "value", "1kΩ", rect(714, 692, 20, 10), owner_id="C4",
                       zone_id="zB"),
        ],
        components=[component("C1", rect(100, 660, 40, 30), "R1", "zA"),
                    component("C2", rect(160, 660, 40, 30), "R2", "zA"),
                    component("C3", rect(700, 660, 40, 30), "R3", "zB"),
                    component("C4", rect(760, 660, 40, 30), "R4", "zB")],
        notes="two independent overlap clusters; local scope must freeze the other",
    )


def scenario_priority() -> Dict[str, Any]:
    """Designator/value pair with a free text; priority only orders ties."""
    return document(
        "priority",
        components=[component("C1", rect(100, 660, 40, 30), "R1", "zA")],
        annotations=[
            annotation("A1", "value", "10kΩ", rect(100, 692, 25, 10), owner_id="C1",
                       zone_id="zA", priority=1),
            annotation("A2", "free_text", "note", rect(110, 690, 30, 12),
                       zone_id="zA", keep_in_zone=True),
        ],
        notes="one overlap between a value and a free text",
    )


SCENARIOS = {
    "text-text": scenario_text_text,
    "text-symbol": scenario_text_symbol,
    "text-wire": scenario_text_wire,
    "rotated": scenario_rotated,
    "chinese-purpose": scenario_chinese_purpose,
    "title-block": scenario_title_block,
    "zone-boundary": scenario_zone_boundary,
    "lock-frozen": scenario_lock_frozen,
    "no-candidates": scenario_no_candidates,
    "estimated": scenario_estimated,
    "net-anchor": scenario_net_anchor,
    "clean": scenario_clean,
    "dense": scenario_dense,
    "cluster-a": scenario_cluster_a,
    "priority": scenario_priority,
}


def scenario_budget() -> Dict[str, Any]:
    """Chain where the bounded search exhausts the one-state budget.

    Found by the deterministic search in this build script (seed 20261027); the
    fixture is synthetic and exists to exercise the budget path, not to claim a
    real board is infeasible.
    """
    return document(
        "budget-exhausted",
        components=[component("C1", rect(100, 560, 24, 20), "R1", "zA"),
                    component("C2", rect(120, 560, 24, 20), "R2", "zA"),
                    component("C3", rect(140, 560, 24, 20), "R3", "zA")],
        fixed_texts=[fixed_text("F1", "free_text", "blocker", rect(60, 590, 30, 10)),
                     fixed_text("F2", "free_text", "blocker", rect(260, 590, 30, 10))],
        annotations=[
            annotation("A1", "value", "1k", rect(100, 590, 30, 10), owner_id="C1",
                       zone_id="zA", allowed_directions=["right"]),
            annotation("A2", "value", "2k", rect(120, 590, 30, 10), owner_id="C2",
                       zone_id="zA"),
            annotation("A3", "value", "3k", rect(140, 590, 30, 10), owner_id="C3",
                       zone_id="zA", allowed_directions=["left"]),
        ],
        constraints={
            "max_search_states": 1,
            "max_local_search_steps": 0,
            "max_candidates_per_annotation": 8,
            "max_total_candidates": 60,
        },
        notes="synthetic one-state budget case; expect partial + budget_exhausted",
    )


def scenario_counterexample() -> Dict[str, Any]:
    """Naive one-by-one greedy introduces a new conflict; batch search does not.

    Geometry found by the deterministic search in this build script (seed
    20261028, trial 2398).  The counterexample test asserts the introduced
    conflict and that the batch solver clears all conflicts without adding one.
    """
    return document(
        "counterexample",
        components=[component("C1", rect(180, 600, 24, 20), "R1", "zA"),
                    component("C2", rect(380, 570, 24, 20), "R2", "zA"),
                    component("C3", rect(400, 555, 24, 20), "R3", "zA"),
                    component("C4", rect(420, 555, 24, 20), "R4", "zA")],
        annotations=[
            annotation("A1", "value", "1k", rect(180, 630, 30, 10), owner_id="C1",
                       zone_id="zA", allowed_directions=["up", "right"],
                       max_displacement=60),
            annotation("A2", "value", "2k", rect(380, 600, 36, 10), owner_id="C2",
                       zone_id="zA", allowed_directions=["right"],
                       max_displacement=60),
            annotation("A3", "value", "3k", rect(400, 585, 36, 10), owner_id="C3",
                       zone_id="zA", allowed_directions=["up", "left"],
                       max_displacement=20),
            annotation("A4", "value", "4k", rect(420, 585, 36, 10), owner_id="C4",
                       zone_id="zA", max_displacement=20),
        ],
        notes="per-annotation greedy introduces a new conflict; batch search clears all",
    )


def holdouts() -> Dict[str, Dict[str, Any]]:
    h1 = document(
        "holdout-chain",
        components=[component(f"C{i}", rect(80 + i * 34, 500, 30, 24), f"R{i}", "zC")
                    for i in range(1, 6)],
        annotations=[
            annotation(f"A{i}", "value", f"{i}.0kΩ", rect(80 + i * 34, 530, 30, 10),
                       owner_id=f"C{i}", zone_id="zC")
            for i in range(1, 6)
        ],
        notes="holdout: five overlapping values in a chain across zone zC",
    )
    h1["movable_annotations"][1]["current"]["bbox"][0] -= 14
    h1["movable_annotations"][1]["current"]["bbox"][2] -= 14
    h1["movable_annotations"][3]["current"]["bbox"][0] -= 9
    h1["movable_annotations"][3]["current"]["bbox"][2] -= 9

    h2 = document(
        "holdout-rotated-cn",
        wires=[wire("W1", [(650, 470), (850, 470)])],
        annotations=[
            annotation("A1", "free_text", "阈值迟滞说明", rect(660, 462, 120, 14),
                       zone_id="zB", keep_in_zone=True, rotation=90.0,
                       align="center", anchor=[660, 462]),
        ],
        notes="holdout: rotated Chinese purpose text crossed by a wire",
    )

    h3 = document(
        "holdout-title-zone",
        fixed_texts=[fixed_text("F1", "free_text", "annotation",
                                rect(420, 760, 100, 12))],
        annotations=[
            annotation("A1", "free_text", "upper note", rect(430, 760, 100, 12),
                       zone_id="zA", keep_in_zone=True),
            annotation("A2", "free_text", "edge note", rect(1050, 320, 70, 12)),
        ],
        notes="holdout: zone-clipped overlap plus a text near page edge",
    )

    h4 = scenario_net_anchor()
    h4["project"]["name"] = "synthetic-holdout-unsupported"
    h4["project"]["page_id"] = "page-holdout-unsupported"
    h4["source"]["notes"] = "holdout: unsupported net-label detach; must not pretend to fix"
    return {
        "holdout-chain": h1,
        "holdout-rotated-cn": h2,
        "holdout-title-zone": h3,
        "holdout-unsupported": h4,
    }


HOLDOUT_EXPECTATIONS = {
    "schema": "annotation-layout-holdout-expectations/v1",
    "note": "expectations authored from the scenario design, not back-filled from output; "
            "bounds are deliberately loose",
    "cases": {
        "holdout-chain": {"acceptable_statuses": ["planned_clear"],
                          "max_hard_after": 0, "max_moved": 4,
                          "reason": "pairwise chain can be cleared by moving at most four values"},
        "holdout-rotated-cn": {"acceptable_statuses": ["planned_clear"],
                               "max_hard_after": 0, "max_moved": 1,
                               "reason": "one rotated text must move out of the wire"},
        "holdout-title-zone": {"acceptable_statuses": ["planned_clear"],
                               "max_hard_after": 0, "max_moved": 2,
                               "reason": "two independent texts, at most one move each"},
        "holdout-unsupported": {"acceptable_statuses": ["blocked", "partial"],
                                "max_hard_after": 1, "max_moved": 0,
                                "reason": "net-label anchor separation is unsupported; "
                                          "no geometric fix may be claimed"},
    },
}


INVALID_CASES = {
    "nan.json": "NaN coordinate",
    "duplicate-id.json": "duplicate object id",
    "unknown-unit.json": "unknown units.name",
    "bool-number.json": "boolean used as a number",
    "bad-bbox.json": "reversed bbox",
    "unknown-key.json": "unknown top-level key",
}


def invalid_documents() -> Dict[str, Dict[str, Any]]:
    base = scenario_clean()
    nan = json.loads(json.dumps(base))
    nan["movable_annotations"][0]["current"]["bbox"][0] = float("nan")
    duplicate = json.loads(json.dumps(base))
    duplicate["fixed_texts"] = [fixed_text("A1", "free_text", "dup", rect(900, 700, 40, 10))]
    unknown_unit = json.loads(json.dumps(base))
    unknown_unit["units"]["name"] = "pixels"
    bool_number = json.loads(json.dumps(base))
    bool_number["constraints"]["grid"] = True
    bad_bbox = json.loads(json.dumps(base))
    bad_bbox["movable_annotations"][1]["current"]["bbox"] = [12.0, 10.0, 8.0, 20.0]
    unknown_key = json.loads(json.dumps(base))
    unknown_key["surprise"] = {"not": "allowed"}
    return {
        "nan.json": nan,
        "duplicate-id.json": duplicate,
        "unknown-unit.json": unknown_unit,
        "bool-number.json": bool_number,
        "bad-bbox.json": bad_bbox,
        "unknown-key.json": unknown_key,
    }


# ---------------------------------------------------------------------------
# writer


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_sha(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _validate(doc: Mapping[str, Any], name: str) -> None:
    try:
        validate_input(doc, origin=name)
    except InputError as exc:
        raise SystemExit(f"{name}: generated invalid input: {exc.reasons}") from exc


def _before_hard(doc: Mapping[str, Any]) -> int:
    inp = validate_input(doc, origin="<generated>")
    return sum(1 for item in evaluate_assignment(inp, {}) if item.is_hard)


def _solve_outcome(doc: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    inp = validate_input(doc, origin="<generated>")
    result = solve(inp, counter=Counters())
    moved = sum(1 for candidate in result.assignment.values()
                if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9)
    return result.status, {"hard": sum(1 for item in result.violations if item.is_hard),
                           "moved": moved, "budget": result.stats.budget_exhausted,
                           "reasons": sorted(result.reasons.get("per_annotation", {}))}


def main() -> int:
    for directory in (SYNTHETIC_DIR, HOLDOUT_DIR, INVALID_DIR, BENCH_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {
        "schema": "annotation-layout-fixtures/v1",
        "generator": "tests/annotation_layout/build_fixtures.py",
        "base_main_sha": "9a951edc21481dc3ae91460acc11aa3e08a7be8a",
        "cases": {},
    }
    outcomes: Dict[str, Any] = {}
    for name, factory in SCENARIOS.items():
        doc = factory()
        _validate(doc, name)
        path = SYNTHETIC_DIR / f"{name}.json"
        _write(path, doc)
        status, outcome = _solve_outcome(doc)
        outcomes[name] = {"before_hard": _before_hard(doc), "status": status, **outcome}
        manifest["cases"][f"synthetic/{name}.json"] = _sha(path)
    # budget case, tuned by construction (verify the claim rather than assume it)
    budget = scenario_budget()
    _validate(budget, "budget-exhausted")
    status, outcome = _solve_outcome(budget)
    if not outcome["budget"]:
        raise SystemExit("budget-exhausted fixture did not exhaust the budget")
    path = SYNTHETIC_DIR / "budget-exhausted.json"
    _write(path, budget)
    outcomes["budget-exhausted"] = {"before_hard": _before_hard(budget), "status": status,
                                    **outcome}
    manifest["cases"]["synthetic/budget-exhausted.json"] = _sha(path)

    counterexample = scenario_counterexample()
    _validate(counterexample, "counterexample")
    example_status, example_outcome = _solve_outcome(counterexample)
    path = SYNTHETIC_DIR / "counterexample.json"
    _write(path, counterexample)
    outcomes["counterexample"] = {"before_hard": _before_hard(counterexample),
                                  "status": example_status, **example_outcome}
    manifest["cases"]["synthetic/counterexample.json"] = _sha(path)

    holdout_docs = holdouts()
    for name, doc in holdout_docs.items():
        _validate(doc, name)
        path = HOLDOUT_DIR / f"{name}.json"
        _write(path, doc)
        outcomes[name] = {"before_hard": _before_hard(doc), "status": _solve_outcome(doc)[0]}
        manifest["cases"][f"holdout/{name}.json"] = _sha(path)
    _write(HOLDOUT_DIR / "expectations.json", HOLDOUT_EXPECTATIONS)
    manifest["cases"]["holdout/expectations.json"] = _sha(HOLDOUT_DIR / "expectations.json")

    invalid = invalid_documents()
    for name, doc in invalid.items():
        path = INVALID_DIR / name
        _write(path, doc)
        try:
            validate_input(doc, origin=name)
        except InputError:
            pass
        else:
            raise SystemExit(f"invalid fixture {name} was accepted")
        manifest["cases"][f"invalid/{name}"] = _sha(path)

    # benchmark cases: real + selected synthetic
    source_dir = REAL_INPUT.parent
    real_doc = json.loads(REAL_INPUT.read_text(encoding="utf-8"))
    source_target = BENCH_DIR / "photo-led-src"
    source_target.mkdir(parents=True, exist_ok=True)
    for item in real_doc["source"]["files"]:
        name = Path(item["path"]).name
        target = source_target / name
        raw = (source_dir / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        target.write_bytes(raw)
        item["path"] = f"photo-led-src/{name}"
    real_target = BENCH_DIR / "real-photo-led.json"
    _write(real_target, real_doc)
    bench_sources = {
        "text-text.json": SYNTHETIC_DIR / "text-text.json",
        "text-wire.json": SYNTHETIC_DIR / "text-wire.json",
        "dense.json": SYNTHETIC_DIR / "dense.json",
        "counterexample.json": SYNTHETIC_DIR / "counterexample.json",
    }
    for name, source in bench_sources.items():
        target = BENCH_DIR / name
        target.write_bytes(source.read_bytes())
    manifest["cases"]["benchmark/real-photo-led.json"] = _sha(real_target)
    for name in bench_sources:
        manifest["cases"][f"benchmark/{name}"] = _sha(BENCH_DIR / name)
    _write(BENCH_DIR / "MANIFEST.json", {
        "schema": "annotation-layout-benchmark-cases/v1",
        "real_source": "tests/annotation_layout/fixtures/photo-led-v14",
        "cases": {path.name: _sha(path) for path in
                  sorted(BENCH_DIR.glob("*.json")) if path.name != "MANIFEST.json"},
        "photo_led_src": {path.name: _sha(path) for path in
                          sorted(source_target.glob("*.json"))},
    })
    manifest["cases"]["fixtures files"] = _dir_sha(SYNTHETIC_DIR)
    _write(ROOT / "tests" / "annotation_layout" / "fixtures" / "MANIFEST.json", manifest)

    print(json.dumps({"status": "ok",
                      "synthetic": len(SCENARIOS) + 1,
                      "holdout": len(holdout_docs),
                      "invalid": len(invalid),
                      "benchmark": len(bench_sources),
                      "outcomes": outcomes},
                     ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
