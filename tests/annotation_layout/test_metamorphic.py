import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.model import canonical_sha256
from annotation_layout.planner import build_plan
from annotation_layout.schema import load_input, validate_input


def _map_box(box, fn):
    x0, y0, x1, y1 = box
    a = fn((x0, y0))
    b = fn((x1, y1))
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]


def translate_document(document, dx, dy):
    doc = copy.deepcopy(document)

    def move(point):
        return (point[0] + dx, point[1] + dy)

    page = doc["page"]
    page["bbox"] = _map_box(page["bbox"], move)
    page["usable_bbox"] = _map_box(page["usable_bbox"], move)
    if page.get("title_block"):
        page["title_block"]["bbox"] = _map_box(page["title_block"]["bbox"], move)
    for keepout in page.get("keepouts", []):
        keepout["bbox"] = _map_box(keepout["bbox"], move)
    for zone in page.get("zones", []):
        zone["bbox"] = _map_box(zone["bbox"], move)
    for component in doc["components"]:
        component["bbox"] = _map_box(component["bbox"], move)
    for wire in doc["wires"]:
        wire["points"] = [[point[0] + dx, point[1] + dy] for point in wire["points"]]
    for text in doc["fixed_texts"]:
        text["bbox"] = _map_box(text["bbox"], move)
    for annotation in doc["movable_annotations"]:
        annotation["current"]["bbox"] = _map_box(annotation["current"]["bbox"], move)
        if annotation["current"].get("anchor"):
            point = annotation["current"]["anchor"]
            annotation["current"]["anchor"] = [point[0] + dx, point[1] + dy]
    return doc


def scale_document(document, factor):
    doc = copy.deepcopy(document)

    def scale(point):
        return (point[0] * factor, point[1] * factor)

    page = doc["page"]
    page["bbox"] = _map_box(page["bbox"], scale)
    page["usable_bbox"] = _map_box(page["usable_bbox"], scale)
    if page.get("title_block"):
        page["title_block"]["bbox"] = _map_box(page["title_block"]["bbox"], scale)
    for keepout in page.get("keepouts", []):
        keepout["bbox"] = _map_box(keepout["bbox"], scale)
    for zone in page.get("zones", []):
        zone["bbox"] = _map_box(zone["bbox"], scale)
    for component in doc["components"]:
        component["bbox"] = _map_box(component["bbox"], scale)
    for wire in doc["wires"]:
        wire["points"] = [[point[0] * factor, point[1] * factor] for point in wire["points"]]
    for text in doc["fixed_texts"]:
        text["bbox"] = _map_box(text["bbox"], scale)
    for annotation in doc["movable_annotations"]:
        annotation["current"]["bbox"] = _map_box(annotation["current"]["bbox"], scale)
        constraints = annotation["constraints"]
        constraints["max_displacement"] *= factor
        constraints["grid"] *= factor
        constraints["owner_max_distance"] *= factor
    for name in ("grid", "min_text_text_gap", "min_text_symbol_gap", "min_text_wire_gap",
                 "min_text_wire_clearance", "max_displacement", "owner_max_distance"):
        doc["constraints"][name] *= factor
    doc["units"]["raw_per_mm"] /= factor
    return doc


def _moves(plan):
    return {change["id"]: (round(change["delta"]["dx"], 6),
                           round(change["delta"]["dy"], 6))
            for change in plan["changes"]}


class MetamorphicTest(unittest.TestCase):
    def setUp(self):
        self.document = helpers.read_json(helpers.synthetic("text-text"))
        self.plan = build_plan(validate_input(self.document))

    def test_object_order_does_not_change_the_solution(self):
        shuffled = copy.deepcopy(self.document)
        shuffled["movable_annotations"].reverse()
        shuffled["fixed_texts"].reverse()
        shuffled["components"].reverse()
        self.assertNotEqual(canonical_sha256(self.document), canonical_sha256(shuffled))
        plan = build_plan(validate_input(shuffled))
        self.assertEqual(_moves(plan), _moves(self.plan))
        self.assertEqual(plan["status"], self.plan["status"])

    def test_whole_page_translation_preserves_relative_solution(self):
        moved = translate_document(self.document, 1000.0, 2000.0)
        plan = build_plan(validate_input(moved))
        self.assertEqual(_moves(plan), _moves(self.plan))
        self.assertEqual(plan["status"], self.plan["status"])
        self.assertEqual(plan["metrics"]["after_hard"], 0)
        self.assertNotEqual(canonical_sha256(self.document), canonical_sha256(moved))

    def test_legal_unit_scaling_preserves_relative_solution(self):
        scaled = scale_document(self.document, 2.0)
        plan = build_plan(validate_input(scaled))
        expected = {identity: (round(dx * 2, 6), round(dy * 2, 6))
                    for identity, (dx, dy) in _moves(self.plan).items()}
        self.assertEqual(_moves(plan), expected)
        self.assertEqual(plan["status"], self.plan["status"])
        self.assertEqual(plan["metrics"]["after_hard"], 0)

    def test_grid_equivalence_keeps_hard_constraints_stable(self):
        document = copy.deepcopy(self.document)
        document["constraints"]["grid"] = 10
        for annotation in document["movable_annotations"]:
            annotation["constraints"]["grid"] = 10
        plan = build_plan(validate_input(document))
        self.assertEqual(plan["status"], "planned_clear")
        self.assertEqual(plan["metrics"]["after_hard"], 0)
        self.assertEqual(plan["verification"]["independent"]["introduced_movable"], [])

    def test_unrelated_zone_and_keepout_do_not_add_moves(self):
        document = copy.deepcopy(self.document)
        document["page"]["zones"].append({
            "id": "zFar", "name": "unrelated far zone",
            "bbox": [800.0, 500.0, 1100.0, 780.0], "hard": False,
            "source": "synthetic_declared"})
        document["page"]["keepouts"].append({
            "id": "farKeepout", "bbox": [1150.0, 700.0, 1165.0, 800.0],
            "hard": True, "reason": "unrelated synthetic keep-out"})
        plan = build_plan(validate_input(document))
        self.assertEqual(_moves(plan), _moves(self.plan))
        self.assertEqual(plan["metrics"]["after_hard"], 0)
        self.assertEqual(plan["verification"]["independent"]["introduced_movable"], [])

    def test_hashes_report_the_change_honestly(self):
        moved = translate_document(self.document, 10.0, 20.0)
        plan = build_plan(validate_input(moved))
        self.assertNotEqual(plan["input"]["canonical_sha256"],
                            self.plan["input"]["canonical_sha256"])
        self.assertEqual(plan["input"]["canonical_sha256"],
                         canonical_sha256(moved))


if __name__ == "__main__":
    unittest.main()

