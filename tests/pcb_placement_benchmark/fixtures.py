"""In-memory case documents for the judge test suite (standard library only).

The fixtures follow ``docs/pcb-placement-training/contract.md`` section 2
exactly.  They are deliberately small hand-computed cases: every expected
verdict / code / soft failure is derived by hand from the geometry, never
copied from judge output.
"""
from __future__ import annotations

CASE_SCHEMA = "easycirq.pcb-placement-case/v1"
COLLECTION_SCHEMA = "easycirq.pcb-placement-benchmarks/v1"

DEFAULT_RUBRIC = {
    "connector_edge_tol_mm": 2.0,
    "overlap_tol_mm2": 0.0,
    "hpwl_max_mm": 180.0,
    "congestion_max": 4,
}


def board_document(width=40.0, height=30.0, **optional):
    document = {"width_mm": float(width), "height_mm": float(height)}
    document.update(optional)
    return document


def component(ref, x, y, w, h, *, pins=None, allowed_rotations=None,
              fixed=False, fixed_xy=None, kind="ic", package="TEST-1"):
    """One component; ``(x, y)`` is the center used by the default placement."""
    return {
        "ref": ref,
        "kind": kind,
        "package": package,
        "size_mm": {"w": float(w), "h": float(h)},
        "fixed": bool(fixed),
        "fixed_xy_mm": (None if fixed_xy is None
                        else [float(fixed_xy[0]), float(fixed_xy[1])]),
        "allowed_rotations": [float(value) for value in
                              (allowed_rotations if allowed_rotations is not None
                               else (0, 90, 180, 270))],
        "pins": [
            {"name": name, "x_mm": float(position[0]),
             "y_mm": float(position[1])}
            for name, position in (pins or {}).items()
        ],
    }


def placed(x, y, rot=0.0):
    return {"x_mm": float(x), "y_mm": float(y), "rot_deg": float(rot)}


def net(name, net_class="signal", pins=()):
    return {"name": name, "class": net_class,
            "pins": [list(pair) for pair in pins]}


def check(check_id, code, pins, max_mm, refs=None, basis="PL00",
          reasoning="hand-authored fixture check"):
    return {
        "id": check_id,
        "code": code,
        "refs": list(refs if refs is not None
                     else sorted({pair[0] for pair in pins})),
        "pins": [list(pair) for pair in pins],
        "max_mm": float(max_mm),
        "basis": basis,
        "reasoning": reasoning,
    }


def keepout(keepout_id, rect, kind="antenna_clearance", reason="test clearance"):
    return {"id": keepout_id,
            "rect_mm": [float(value) for value in rect],
            "kind": kind,
            "reason": reason}


def connector(ref, edge, insert_dir=None):
    return {"ref": ref, "edge": edge, "insert_dir": insert_dir or edge}


def expected(verdict="acceptable", codes=(), soft_fail=()):
    return {"verdict": verdict, "codes": list(codes),
            "soft_fail": list(soft_fail)}


expected_doc = expected


def default_reference():
    return {
        "module_order": ["mcu"],
        "key_placements": [],
        "acceptable_alternatives": ["none for this fixture"],
        "rationale": ["hand-authored fixture for the offline judge tests"],
        "not_checked": ["real DRC", "routing", "impedance", "thermal"],
    }


def default_provenance():
    return {"kind": "synthetic",
            "source": "authored for the pcb_placement_benchmark test suite",
            "source_sha256": None,
            "note": "minimal hand-computed fixture, not a real board"}


def case(case_id="T-1", *, title="fixture case", domain="mcu", pair_with=None,
         problem="hand-authored fixture problem",
         target="hand-authored fixture target",
         inspection="what a real review would still have to check",
         evidence_level="synthetic", provenance=None, board=None,
         components=None, nets=None, placement=None, checks=None, rubric=None,
         expected=None, reference=None, limits=None):
    """Build one complete, schema-valid case document."""
    return {
        "schema": CASE_SCHEMA,
        "id": case_id,
        "title": title,
        "domain": domain,
        "pair_with": pair_with,
        "problem": problem,
        "target": target,
        "inspection": inspection,
        "evidence_level": evidence_level,
        "provenance": (provenance if provenance is not None
                       else default_provenance()),
        "units": {"length": "mm"},
        "board": board if board is not None else board_document(),
        "components": (components if components is not None
                       else [component("U1", 20, 15, 8, 8)]),
        "nets": nets if nets is not None else [],
        "placement": (placement if placement is not None
                      else {"U1": placed(20, 15)}),
        "checks": checks if checks is not None else [],
        "rubric": dict(DEFAULT_RUBRIC) if rubric is None else rubric,
        "expected": expected if expected is not None else expected_doc(),
        "reference": reference if reference is not None else default_reference(),
        "limits": limits if limits is not None
        else ["offline geometry/net proxy", "not DRC"],
    }


def collection(*documents):
    return {"schema": COLLECTION_SCHEMA, "cases": list(documents)}
