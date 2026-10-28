"""Input fixtures for the placement-intent CLI tests.

Fixtures are plain Python dicts written to a temporary directory as JSON by
the tests.  They never touch the implementation.  Lengths are in millimetres
unless ``units == "mil"`` is requested explicitly.

The hand-checkable geometry expectations live next to the fixture functions in
the comments so the tests can assert independently computed bounding boxes
instead of copying implementation output.
"""
from __future__ import annotations

import copy

SCHEMA_INPUT = "easycirq.placement-intent.input/v1"
SNAPSHOT_SHA = "0123456789abcdef" * 4  # 64 lowercase hex characters
CAPTURED_AT = "2026-10-27T09:00:00+08:00"


def _copy(value):
    return copy.deepcopy(value)


def provenance(kind="synthetic", sources=None, note=None):
    return {
        "kind": kind,
        "sources": [] if sources is None else sources,
        "note": note or ("Synthetic fixture for placement-intent contract "
                         "tests; not a real board and not derived from one."),
    }


def document(modules, components, constraints, *, units="mm", board="auto",
             policy=None, provenance_value=None, unknowns=None, project=None,
             snapshot=None):
    """Assemble a complete input document around explicit arrays."""
    doc = {
        "schema": SCHEMA_INPUT,
        "project": project or {
            "project_id": "pi-test-demo",
            "revision": "r1",
            "document_id": "sheet-1",
        },
        "snapshot": snapshot or {
            "captured_at": CAPTURED_AT,
            "content_sha256": SNAPSHOT_SHA,
            "source_type": "synthetic_fixture",
            "missing_fields": [],
        },
        "units": {"length": units},
        "modules": _copy(modules),
        "components": _copy(components),
        "constraints": _copy(constraints),
        "provenance": provenance_value or provenance(),
    }
    if board == "auto":
        doc["board"] = {"width_mm": 40.0, "height_mm": 30.0}
    elif board is not None:
        doc["board"] = _copy(board)
    if policy is not None:
        doc["policy"] = _copy(policy)
    if unknowns is not None:
        doc["unknowns"] = _copy(unknowns)
    return doc


# ---------------------------------------------------------------------------
# 1. Positive case from contract.md section 11.1: three HMT levels, 8 CCG edges,
#    every size known and a declared board.
#
# Hand-computed geometry (anchor top-left, no bbox normalisation; offsets are
# relative to each node's parent frame, rotations here are all 0):
#   board children:    power @(5,5), sense @(25,5)
#   power child:       ldo   @(3,2)
#   ldo components:    U1 @(1,1) 3x3, C1 @(5,1) 1x2, C2 @(1,4) 1x2
#   sense components:  U2 @(1,1) 4x4, R1 @(6,1) 1x2
#   bbox(ldo)   = union([1,4]x[1,4], [5,6]x[1,3], [1,2]x[4,6])
#               = {x:1, y:1, w:5, h:5}
#   bbox(power) = bbox(ldo) + (3,2) = {x:4, y:3, w:5, h:5}
#   bbox(sense) = union([1,5]x[1,5], [6,7]x[1,3])
#               = {x:1, y:1, w:6, h:4}
#   bbox(board) = union(bbox(power)+(5,5), bbox(sense)+(25,5))
#               = union([9,14]x[8,13], [26,32]x[6,10])
#               = {x:9, y:6, w:23, h:7}
# ---------------------------------------------------------------------------
def three_layer_case():
    modules = [
        {"id": "mod:board", "name": "Demo board", "parent": None,
         "children": ["mod:power", "mod:sense"], "components": [],
         "size_mm": {"w": 40.0, "h": 30.0}, "allowed_rotations": [0],
         "source": {"kind": "user"}},
        {"id": "mod:power", "name": "Power", "parent": "mod:board",
         "children": ["mod:ldo"], "components": [], "confidence": 0.92,
         "size_mm": {"w": 14.0, "h": 8.0}, "allowed_rotations": [0],
         "source": {"kind": "user"}},
        {"id": "mod:ldo", "name": "LDO block", "parent": "mod:power",
         "children": [], "components": ["cmp:U1", "cmp:C1", "cmp:C2"],
         "size_mm": {"w": 8.0, "h": 6.0}, "allowed_rotations": [0],
         "source": {"kind": "user"}},
        {"id": "mod:sense", "name": "Sensor", "parent": "mod:board",
         "children": [], "components": ["cmp:U2", "cmp:R1"],
         "size_mm": {"w": 10.0, "h": 6.0}, "allowed_rotations": [0],
         "source": {"kind": "user"}},
    ]
    components = [
        {"instance_id": "cmp:U1", "designator": "U1", "kind": "ldo",
         "mpn": "TLV75533PDBV", "package": "SOT-23-5",
         "size_mm": {"w": 3.0, "h": 3.0}, "fixed": False,
         "allowed_rotations": [0], "source": {"kind": "user"}},
        {"instance_id": "cmp:C1", "designator": "C1", "kind": "capacitor",
         "size_mm": {"w": 1.0, "h": 2.0}, "allowed_rotations": [0]},
        {"instance_id": "cmp:C2", "designator": "C2", "kind": "capacitor",
         "size_mm": {"w": 1.0, "h": 2.0}, "allowed_rotations": [0]},
        {"instance_id": "cmp:U2", "designator": "U2", "kind": "sensor",
         "size_mm": {"w": 4.0, "h": 4.0}, "allowed_rotations": [0]},
        {"instance_id": "cmp:R1", "designator": "R1", "kind": "resistor",
         "size_mm": {"w": 1.0, "h": 2.0}, "allowed_rotations": [0]},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:board", "to": "mod:power",
         "dx_mm": 5.0, "dy_mm": 5.0, "rotation_deg": 0, "weight": 0.9,
         "source": {"kind": "guideline", "ref": "doc:power-layout#L12"}},
        {"id": "ccg:2", "from": "mod:board", "to": "mod:sense",
         "dx_mm": 25.0, "dy_mm": 5.0, "rotation_deg": 0, "weight": 0.7},
        {"id": "ccg:3", "from": "mod:power", "to": "mod:ldo",
         "dx_mm": 3.0, "dy_mm": 2.0, "rotation_deg": 0, "weight": 0.8},
        {"id": "ccg:4", "from": "mod:ldo", "to": "cmp:U1",
         "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.9},
        {"id": "ccg:5", "from": "mod:ldo", "to": "cmp:C1",
         "dx_mm": 5.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.6},
        {"id": "ccg:6", "from": "mod:ldo", "to": "cmp:C2",
         "dx_mm": 1.0, "dy_mm": 4.0, "rotation_deg": 0, "weight": 0.6},
        {"id": "ccg:7", "from": "mod:sense", "to": "cmp:U2",
         "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.9},
        {"id": "ccg:8", "from": "mod:sense", "to": "cmp:R1",
         "dx_mm": 6.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.5},
    ]
    return document(
        modules, components, constraints,
        board={"width_mm": 40.0, "height_mm": 30.0},
        policy={"max_depth": 6, "default_allowed_rotations": [0],
                "position_tolerance_mm": 1e-6, "weight_epsilon": 1e-9},
        unknowns=[],
    )


# ---------------------------------------------------------------------------
# Small valid case: root -> leaf -> one component.  Hand-computed bbox:
#   cmp:A @(1,1) 4x3 -> bbox {0,0,4,3}
#   bbox(leaf) = bbox(A)+(1,1) = {x:1, y:1, w:4, h:3}
#   bbox(root) = bbox(leaf)+(0,0) = {x:1, y:1, w:4, h:3}
# ---------------------------------------------------------------------------
def small_case():
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:leaf"], "components": [],
         "size_mm": {"w": 20.0, "h": 10.0}},
        {"id": "mod:leaf", "name": "Leaf", "parent": "mod:root",
         "children": [], "components": ["cmp:A"],
         "size_mm": {"w": 10.0, "h": 6.0}},
    ]
    components = [
        {"instance_id": "cmp:A", "designator": "A", "kind": "capacitor",
         "size_mm": {"w": 4.0, "h": 3.0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:leaf",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:leaf", "to": "cmp:A",
         "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 40.0, "height_mm": 30.0})


# ---------------------------------------------------------------------------
# 90 degree rotation case.  cmp:RX is an 8x2 rect rotated +90 degrees relative
# to mod:rot; rotating the local rect [0,8]x[0,2] by 90 gives x in [-2,0],
# y in [0,8].  With offset (0,0) inside mod:rot:
#   bbox(mod:rot)  = {x:-2, y:0, w:2, h:8}
# mod:rot sits at (5,5) with rotation 0 relative to mod:board, so
#   bbox(mod:board)= {x:3,  y:5, w:2, h:8}
# ---------------------------------------------------------------------------
def rotation_case():
    modules = [
        {"id": "mod:board", "name": "Board", "parent": None,
         "children": ["mod:rot"], "components": [],
         "size_mm": {"w": 50.0, "h": 40.0},
         "allowed_rotations": [0, 90, 180, 270]},
        {"id": "mod:rot", "name": "Rotated leaf", "parent": "mod:board",
         "children": [], "components": ["cmp:RX"],
         "allowed_rotations": [0, 90]},
    ]
    components = [
        {"instance_id": "cmp:RX", "designator": "RX",
         "size_mm": {"w": 8.0, "h": 2.0},
         "allowed_rotations": [0, 90]},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:board", "to": "mod:rot",
         "dx_mm": 5.0, "dy_mm": 5.0, "rotation_deg": 0, "weight": 0.9},
        {"id": "ccg:2", "from": "mod:rot", "to": "cmp:RX",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 90, "weight": 0.9},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 50.0, "height_mm": 40.0})


# ---------------------------------------------------------------------------
# Sibling overlap: two 4x3 components in the same leaf overlap by 2x2 mm.
#   A @(1,1) -> [1,5] x [1,4]
#   B @(3,2) -> [3,7] x [2,5]
#   overlap area = 2*2 = 4 > tolerance^2 -> review_required / sibling_overlap
# ---------------------------------------------------------------------------
def overlap_case():
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:leaf"], "components": [],
         "size_mm": {"w": 20.0, "h": 10.0}},
        {"id": "mod:leaf", "name": "Leaf", "parent": "mod:root",
         "children": [], "components": ["cmp:A", "cmp:B"],
         "size_mm": {"w": 10.0, "h": 6.0}},
    ]
    components = [
        {"instance_id": "cmp:A", "designator": "A",
         "size_mm": {"w": 4.0, "h": 3.0}},
        {"instance_id": "cmp:B", "designator": "B",
         "size_mm": {"w": 4.0, "h": 3.0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:leaf",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:leaf", "to": "cmp:A",
         "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:3", "from": "mod:leaf", "to": "cmp:B",
         "dx_mm": 3.0, "dy_mm": 2.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 40.0, "height_mm": 30.0})


def no_overlap_case():
    """Same geometry but B moved to (7,1): only an edge touch, area == 0."""
    doc = overlap_case()
    doc["constraints"][2]["dx_mm"] = 7.0
    doc["constraints"][2]["dy_mm"] = 1.0
    # Widen the leaf so the union [1,11]x[1,4] still fits the declared size.
    doc["modules"][1]["size_mm"] = {"w": 12.0, "h": 6.0}
    return doc


def module_overlap_case():
    """Two sibling modules whose derived bboxes overlap (2,2)-(8,8)."""
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:m1", "mod:m2"], "components": [],
         "size_mm": {"w": 40.0, "h": 30.0}},
        {"id": "mod:m1", "name": "M1", "parent": "mod:root",
         "children": [], "components": ["cmp:P"],
         "size_mm": {"w": 8.0, "h": 8.0}},
        {"id": "mod:m2", "name": "M2", "parent": "mod:root",
         "children": [], "components": ["cmp:Q"],
         "size_mm": {"w": 8.0, "h": 8.0}},
    ]
    components = [
        {"instance_id": "cmp:P", "designator": "P",
         "size_mm": {"w": 8.0, "h": 8.0}},
        {"instance_id": "cmp:Q", "designator": "Q",
         "size_mm": {"w": 8.0, "h": 8.0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:m1",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:root", "to": "mod:m2",
         "dx_mm": 2.0, "dy_mm": 2.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:3", "from": "mod:m1", "to": "cmp:P",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:4", "from": "mod:m2", "to": "cmp:Q",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 40.0, "height_mm": 30.0})


# ---------------------------------------------------------------------------
# Fixed-node conflicts (review_required, never invalid_input).
# ---------------------------------------------------------------------------
def fixed_rotation_conflict_case():
    """cmp:A is fixed with declared rotation 0 but the CCG forces rotation 90."""
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:leaf"], "components": [],
         "allowed_rotations": [0, 90]},
        {"id": "mod:leaf", "name": "Leaf", "parent": "mod:root",
         "children": [], "components": ["cmp:A"],
         "allowed_rotations": [0, 90]},
    ]
    components = [
        {"instance_id": "cmp:A", "designator": "A",
         "size_mm": {"w": 4.0, "h": 3.0}, "fixed": True,
         "allowed_rotations": [0, 90],
         "position_mm": {"x_mm": 1.0, "y_mm": 1.0, "rotation_deg": 0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:leaf",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:leaf", "to": "cmp:A",
         "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 90, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 40.0, "height_mm": 30.0})


def fixed_distance_conflict_case():
    """Two fixed components: declared distance 100 mm, CCG says 10 mm."""
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:leaf"], "components": []},
        {"id": "mod:leaf", "name": "Leaf", "parent": "mod:root",
         "children": [], "components": ["cmp:A", "cmp:B"]},
    ]
    components = [
        {"instance_id": "cmp:A", "designator": "A",
         "size_mm": {"w": 4.0, "h": 3.0}, "fixed": True,
         "position_mm": {"x_mm": 0.0, "y_mm": 0.0, "rotation_deg": 0}},
        {"instance_id": "cmp:B", "designator": "B",
         "size_mm": {"w": 4.0, "h": 3.0}, "fixed": True,
         "position_mm": {"x_mm": 100.0, "y_mm": 0.0, "rotation_deg": 0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:leaf",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:leaf", "to": "cmp:A",
         "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:3", "from": "mod:leaf", "to": "cmp:B",
         "dx_mm": 11.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 300.0, "height_mm": 300.0})


def fixed_position_unknown_case():
    """Fixed component constrained by CCG but with no declared position."""
    doc = small_case()
    doc["components"][0]["fixed"] = True
    return doc


# ---------------------------------------------------------------------------
# Units: the same geometry expressed in mil and in mm.
#   2000 mil = 50.8 mm, 1000 mil = 25.4 mm, 400 mil = 10.16 mm,
#   200 mil = 5.08 mm, 100 mil = 2.54 mm, 40 mil = 1.016 mm.
# ---------------------------------------------------------------------------
def mil_case():
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:leaf"], "components": [],
         "size_mm": {"w": 2000.0, "h": 1000.0}},
        {"id": "mod:leaf", "name": "Leaf", "parent": "mod:root",
         "children": [], "components": ["cmp:A"],
         "size_mm": {"w": 400.0, "h": 400.0}},
    ]
    components = [
        {"instance_id": "cmp:A", "designator": "A",
         "size_mm": {"w": 200.0, "h": 200.0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:leaf",
         "dx_mm": 1000.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:leaf", "to": "cmp:A",
         "dx_mm": 100.0, "dy_mm": 40.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints, units="mil",
                    board={"width_mm": 2000.0, "height_mm": 1000.0})


def mm_case():
    """Millimetre twin of :func:`mil_case` (same geometry after conversion)."""
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:leaf"], "components": [],
         "size_mm": {"w": 50.8, "h": 25.4}},
        {"id": "mod:leaf", "name": "Leaf", "parent": "mod:root",
         "children": [], "components": ["cmp:A"],
         "size_mm": {"w": 10.16, "h": 10.16}},
    ]
    components = [
        {"instance_id": "cmp:A", "designator": "A",
         "size_mm": {"w": 5.08, "h": 5.08}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:leaf",
         "dx_mm": 25.4, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:leaf", "to": "cmp:A",
         "dx_mm": 2.54, "dy_mm": 1.016, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints, units="mm",
                    board={"width_mm": 50.8, "height_mm": 25.4})


def all_sizes_missing_case():
    """three_layer_case with every component size removed: bbox must stay null."""
    doc = three_layer_case()
    for component in doc["components"]:
        component.pop("size_mm", None)
    return doc


def one_size_missing_case():
    """three_layer_case with only cmp:C1's size removed (unknown priority)."""
    doc = three_layer_case()
    for component in doc["components"]:
        if component["instance_id"] == "cmp:C1":
            component.pop("size_mm", None)
    return doc


def no_board_case():
    doc = small_case()
    doc.pop("board", None)
    return doc


def constraints_empty_case():
    doc = small_case()
    doc["constraints"] = []
    return doc


def declared_unknown_case():
    doc = small_case()
    doc["unknowns"] = [
        {"id": "unk:input:stackup", "field": "stackup",
         "reason": "layer stack-up is not part of this offline PoC"},
    ]
    return doc


def snapshot_hash_missing_case():
    """content_sha256 null and explicitly declared missing -> incomplete."""
    doc = small_case()
    doc["snapshot"]["content_sha256"] = None
    doc["snapshot"]["missing_fields"] = ["content_sha256"]
    return doc


def empty_components_case():
    """Tree is fine but there are no components at all -> design_empty."""
    doc = small_case()
    doc["modules"][1]["components"] = []
    doc["components"] = []
    doc["constraints"] = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:leaf",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return doc


def empty_modules_case():
    doc = small_case()
    doc["modules"] = []
    return doc


# ---------------------------------------------------------------------------
# Deformation helpers
# ---------------------------------------------------------------------------
def reversed_arrays_case():
    """three_layer_case with every array reversed (semantics must not change)."""
    doc = three_layer_case()
    doc["modules"] = list(reversed(doc["modules"]))
    doc["components"] = list(reversed(doc["components"]))
    doc["constraints"] = list(reversed(doc["constraints"]))
    return doc


def renamed_case():
    """three_layer_case with every node id renamed and references updated."""
    doc = three_layer_case()
    rename = {
        "mod:board": "mod:rootx",
        "mod:power": "mod:pwr",
        "mod:ldo": "mod:reg",
        "mod:sense": "mod:sns",
        "cmp:U1": "cmp:U11",
        "cmp:C1": "cmp:C11",
        "cmp:C2": "cmp:C22",
        "cmp:U2": "cmp:U22",
        "cmp:R1": "cmp:R11",
    }

    def mapped(value):
        return rename.get(value, value) if isinstance(value, str) else value

    for module in doc["modules"]:
        module["id"] = mapped(module["id"])
        module["parent"] = mapped(module["parent"])
        module["children"] = [mapped(item) for item in module["children"]]
        module["components"] = [mapped(item) for item in module["components"]]
    for component in doc["components"]:
        component["instance_id"] = mapped(component["instance_id"])
    for constraint in doc["constraints"]:
        constraint["from"] = mapped(constraint["from"])
        constraint["to"] = mapped(constraint["to"])
    return doc, rename


def translated_root_case(dx=100.0, dy=50.0):
    """Translate every edge leaving the root by (dx, dy).

    Root-relative frames of depth-1 nodes shift by (dx, dy); every node-local
    bbox and the status must not change.  The root's declared size is dropped
    because the translated content no longer sits inside it (that would raise
    the unrelated ``module_size_exceeded`` review finding).
    """
    doc = three_layer_case()
    doc["modules"][0].pop("size_mm", None)
    for constraint in doc["constraints"]:
        if constraint["from"] == "mod:board":
            constraint["dx_mm"] += dx
            constraint["dy_mm"] += dy
    return doc


def identity_cycle_case():
    """three_layer_case plus a redundant edge that closes an identity cycle.

    board -> power -> ldo synthesises (8, 7); adding board -> ldo with the same
    relative pose creates a cycle whose composition is the identity, which the
    contract allows (info finding, still planned_with_scope).
    """
    doc = three_layer_case()
    doc["constraints"].append({
        "id": "ccg:9", "from": "mod:board", "to": "mod:ldo",
        "dx_mm": 8.0, "dy_mm": 7.0, "rotation_deg": 0, "weight": 0.5,
    })
    return doc


def identity_rotation_cycle_case():
    """A redundant edge which closes a rotation-identity cycle.

    root -> a : rotation 90, a -> b : rotation 180  => b at 270
    root -> b : rotation 270 (same pose)
    The cycle composition is (90 + 180 - 270) = 0 degrees, translation zero.
    """
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:a"], "components": []},
        {"id": "mod:a", "name": "A", "parent": "mod:root",
         "children": ["mod:b"], "components": []},
        {"id": "mod:b", "name": "B", "parent": "mod:a",
         "children": [], "components": ["cmp:X"]},
    ]
    components = [
        {"instance_id": "cmp:X", "designator": "X",
         "size_mm": {"w": 4.0, "h": 2.0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:a",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 90, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:a", "to": "mod:b",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 180, "weight": 1.0},
        {"id": "ccg:3", "from": "mod:root", "to": "mod:b",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 270, "weight": 1.0},
        {"id": "ccg:4", "from": "mod:b", "to": "cmp:X",
         "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 40.0, "height_mm": 30.0})


def module_size_exceeded_case():
    """Root declared 4x3 but its derived content spans more than that."""
    doc = small_case()
    doc["modules"][0]["size_mm"] = {"w": 3.0, "h": 2.0}
    return doc


def duplicate_constraint_values_case():
    """Same (from, to) with different offsets -> contradictory constraints."""
    doc = small_case()
    doc["constraints"].append({
        "id": "ccg:9", "from": "mod:root", "to": "mod:leaf",
        "dx_mm": 2.0, "dy_mm": 2.0, "rotation_deg": 0, "weight": 1.0,
    })
    return doc


def identical_duplicate_constraint_case():
    """Same (from, to) with identical values -> deduplicated, still valid."""
    doc = small_case()
    doc["constraints"].append({
        "id": "ccg:9", "from": "mod:root", "to": "mod:leaf",
        "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0,
    })
    return doc


def multi_path_mismatch_case():
    """root->A (0,0); root->B (10,0); A->B (5,0): two paths disagree."""
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:a", "mod:b"], "components": []},
        {"id": "mod:a", "name": "A", "parent": "mod:root",
         "children": [], "components": ["cmp:A"]},
        {"id": "mod:b", "name": "B", "parent": "mod:root",
         "children": [], "components": ["cmp:B"]},
    ]
    components = [
        {"instance_id": "cmp:A", "designator": "A",
         "size_mm": {"w": 2.0, "h": 2.0}},
        {"instance_id": "cmp:B", "designator": "B",
         "size_mm": {"w": 2.0, "h": 2.0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:a",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:root", "to": "mod:b",
         "dx_mm": 10.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:3", "from": "mod:a", "to": "mod:b",
         "dx_mm": 5.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 40.0, "height_mm": 30.0})


def non_identity_cycle_case():
    """root->a->b->root closes with a non-zero translation (15, 0)."""
    modules = [
        {"id": "mod:root", "name": "Root", "parent": None,
         "children": ["mod:a"], "components": []},
        {"id": "mod:a", "name": "A", "parent": "mod:root",
         "children": ["mod:b"], "components": []},
        {"id": "mod:b", "name": "B", "parent": "mod:a",
         "children": [], "components": ["cmp:B"]},
    ]
    components = [
        {"instance_id": "cmp:B", "designator": "B",
         "size_mm": {"w": 2.0, "h": 2.0}},
    ]
    constraints = [
        {"id": "ccg:1", "from": "mod:root", "to": "mod:a",
         "dx_mm": 10.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:2", "from": "mod:a", "to": "mod:b",
         "dx_mm": 5.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
        {"id": "ccg:3", "from": "mod:b", "to": "mod:root",
         "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0},
    ]
    return document(modules, components, constraints,
                    board={"width_mm": 40.0, "height_mm": 30.0})


def chain_modules(depth, max_depth=None):
    """A root-to-leaf module chain of ``depth`` edges, one component at leaf."""
    modules = []
    for index in range(depth + 1):
        module = {
            "id": "mod:m%d" % index,
            "parent": None if index == 0 else "mod:m%d" % (index - 1),
            "children": ([] if index == depth
                         else ["mod:m%d" % (index + 1)]),
            "components": (["cmp:LEAF"] if index == depth else []),
        }
        modules.append(module)
    components = [
        {"instance_id": "cmp:LEAF", "designator": "L",
         "size_mm": {"w": 2.0, "h": 2.0}},
    ]
    constraints = []
    for index in range(depth):
        constraints.append({
            "id": "ccg:%d" % (index + 1),
            "from": "mod:m%d" % index,
            "to": "mod:m%d" % (index + 1),
            "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0,
        })
    doc = document(modules, components, constraints,
                   board={"width_mm": 40.0, "height_mm": 30.0})
    if max_depth is not None:
        doc["policy"] = {"max_depth": max_depth}
    return doc


def json_text(document_value, *, indent=2):
    """Deterministic raw JSON text used for duplicate-key / NaN tests."""
    import json
    return json.dumps(document_value, ensure_ascii=False, indent=indent,
                      allow_nan=False)
