"""Tests for the offline single-shot apply compiler (tools/layout2)."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.layout2.sch_layout_apply2 import (  # noqa: E402
    EXEC_SCHEMA,
    PLAN_SCHEMA,
    SCHEMA,
    compile_apply_plan,
)

PROJECT = {
    "project_uuid": "proj-uuid-0001",
    "page": "page-uuid-0001",
    "parts_path": "parts/board.parts.json",
}


def make_page_plan(*, title_block=True, labels=True):
    plan = {
        "schema": "easycirq-sch-layout-v2/v1",
        "page": 1,
        "page_count": 2,
        "frames": [
            {"id": "zone-00", "title": "电源", "rect": {"minX": 12, "minY": 400,
                                                        "maxX": 560, "maxY": 800}},
            {"id": "zone-01", "title": "MCU", "rect": {"minX": 600, "minY": 400,
                                                       "maxX": 1150, "maxY": 800}},
        ],
        "blocks": [
            {"id": "block.power", "title": "电源", "bbox": [40, 440, 360, 640],
             "zone": [12, 400, 560, 800], "at": "90,490"},
            {"id": "block.mcu", "title": "MCU", "bbox": [620, 450, 1000, 700],
             "zone": [600, 400, 1150, 800], "at": "670,500"},
        ],
        "labels": (
            [{"text": "I2S", "bbox": [620, 700, 680, 720], "anchor": [650, 710]}]
            if labels else []
        ),
    }
    if title_block:
        plan["title_block"] = {"rect": {"minX": 610, "minY": 12,
                                       "maxX": 1170, "maxY": 380},
                               "provenance": "sch sheet-geometry"}
    return plan


class CompileApplyPlan(unittest.TestCase):
    def compile(self, plan=None, project=None):
        return compile_apply_plan(plan if plan is not None else make_page_plan(),
                                  project if project is not None else dict(PROJECT))

    # -- ready path ------------------------------------------------------

    def test_ready_status_and_top_level_contract(self):
        result = self.compile()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["verdict"], "ready")
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["findings"], [])
        for key in ("exec_spec", "commands", "artifacts", "decision_record"):
            self.assertIn(key, result)
        json.dumps(result, ensure_ascii=False)

    def test_exec_spec_is_compatible_with_sch_layout_apply(self):
        result = self.compile()
        spec = result["exec_spec"]
        self.assertEqual(spec["schema"], EXEC_SCHEMA)
        self.assertEqual(spec["project_uuid"], PROJECT["project_uuid"])
        self.assertEqual(spec["page"], PROJECT["page"])
        self.assertEqual(spec["parts"], PROJECT["parts_path"])
        self.assertEqual(spec["out_dir"], "out/layout2")
        self.assertEqual(spec["export_name"], "layout2-p01")
        self.assertEqual(spec["plan"], "out/layout2/layout2-p01.plan.json")
        # tools/sch_layout_apply.py consumes project_uuid/page/plan/parts/
        # out_dir/export_name and plan["placements"] with bbox + at.
        placements = spec["plan_payload"]["placements"]
        self.assertEqual(spec["plan_payload"]["schema"], PLAN_SCHEMA)
        self.assertEqual([row["id"] for row in placements],
                         ["block.power", "block.mcu"])
        for row in placements:
            self.assertEqual(len(row["bbox"]), 4)
            self.assertRegex(row["at"], r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")
            self.assertIn("zone", row)
            self.assertIn("title", row)

    def test_commands_order_frame_then_blocks_then_text(self):
        result = self.compile()
        commands = result["commands"]
        self.assertEqual(len(commands), 4)
        self.assertTrue(commands[0].startswith(
            "easycirq sch frame apply --from out/layout2/layout2-p01.frames.json"))
        self.assertIn("sch block-apply block.power --at 90,490", commands[1])
        self.assertIn("sch block-apply block.mcu --at 670,500", commands[2])
        self.assertTrue(commands[3].startswith(
            "easycirq sch apply out/layout2/layout2-p01.texts.json"))
        self.assertEqual(commands[0].count("--doc page-uuid-0001"), 1)
        self.assertIn("--doc page-uuid-0001", commands[1])
        self.assertIn("--parts parts/board.parts.json", commands[1])

    def test_artifacts_cover_every_referenced_file(self):
        result = self.compile()
        artifacts = result["artifacts"]
        self.assertEqual(sorted(artifacts), [
            "out/layout2/layout2-p01.frames.json",
            "out/layout2/layout2-p01.plan.json",
            "out/layout2/layout2-p01.texts.json",
        ])
        frames = artifacts["out/layout2/layout2-p01.frames.json"]
        self.assertEqual(frames["documentId"], PROJECT["page"])
        self.assertEqual([row["id"] for row in frames["frames"]],
                         ["zone-00", "zone-01"])
        self.assertEqual(frames["frames"][0]["rect"],
                         {"minX": 12, "minY": 400, "maxX": 560, "maxY": 800})
        self.assertEqual(len(artifacts["out/layout2/layout2-p01.plan.json"]
                             ["placements"]), 2)
        text_steps = artifacts["out/layout2/layout2-p01.texts.json"]["steps"]
        self.assertEqual(text_steps, [{
            "id": "label-00", "action": "create_text", "x": 650, "y": 710,
            "content": "I2S", "rotation": 0, "font_size": 10,
        }])
        # frames/texts are referenced by commands; the plan artifact is the
        # path tools/sch_layout_apply.py reads (exec_spec["plan"]).
        joined = "\n".join(result["commands"])
        self.assertIn("out/layout2/layout2-p01.frames.json", joined)
        self.assertIn("out/layout2/layout2-p01.texts.json", joined)
        self.assertEqual(result["exec_spec"]["plan"],
                         "out/layout2/layout2-p01.plan.json")
        self.assertIn(result["exec_spec"]["plan"], artifacts)

    def test_decision_record_page_count_placements_and_rationale(self):
        record = self.compile()["decision_record"]
        self.assertIn("page: 1 of 2", record)
        self.assertIn("- placements: 2", record)
        self.assertIn("| 1 | `block.power` |", record)
        self.assertIn("| 2 | `block.mcu` |", record)
        self.assertIn("Title block keep-out", record)
        self.assertIn("## Rationale", record)
        self.assertIn("frame apply", record)
        self.assertIn("## Next steps", record)
        self.assertIn("tools/sch_layout_apply.py", record)

    def test_at_is_derived_from_bbox_when_missing(self):
        plan = make_page_plan(labels=False)
        plan["blocks"][0].pop("at")
        result = self.compile(plan)
        self.assertEqual(
            result["exec_spec"]["plan_payload"]["placements"][0]["at"], "90,490")
        self.assertIn("--at 90,490", result["commands"][1])

    # -- refusal path ----------------------------------------------------

    def test_blocked_when_block_bbox_overlaps_title_block(self):
        plan = make_page_plan(labels=False)
        plan["blocks"].append({"id": "block.intruder", "title": "越界",
                               "bbox": [700, 100, 900, 220],
                               "zone": [700, 100, 900, 220],
                               "at": "750,150"})
        result = self.compile(plan)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["verdict"], "blocked")
        self.assertIsNone(result["exec_spec"])
        self.assertEqual(result["commands"], [])
        self.assertEqual(result["artifacts"], {})
        rules = [(row["rule"], row["id"]) for row in result["findings"]]
        self.assertIn(("title_block_overlap", "block.intruder"), rules)
        record = result["decision_record"]
        self.assertIn("**blocked**", record)
        self.assertIn("block.intruder", record)
        self.assertIn("Refused before any EDA write", record)

    def test_blocked_when_zone_overlaps_title_block(self):
        plan = make_page_plan(labels=False)
        plan["blocks"][1]["bbox"] = [500, 300, 600, 350]
        plan["blocks"][1]["zone"] = [500, 100, 700, 350]
        plan["blocks"][1]["at"] = "550,350"
        result = self.compile(plan)
        self.assertEqual(result["status"], "blocked")
        finding = next(row for row in result["findings"]
                       if row["id"] == "block.mcu")
        self.assertEqual(finding["rule"], "title_block_overlap")
        self.assertIn("zone", finding["fields"])
        self.assertEqual(result["commands"], [])

    def test_blocked_when_frame_overlaps_title_block(self):
        plan = make_page_plan(labels=False)
        plan["frames"][0]["rect"] = {"minX": 700, "minY": 100,
                                     "maxX": 900, "maxY": 300}
        result = self.compile(plan)
        self.assertEqual(result["status"], "blocked")
        finding = next(row for row in result["findings"]
                       if row["kind"] == "frame")
        self.assertEqual(finding["id"], "zone-00")
        self.assertEqual(finding["rule"], "title_block_overlap")
        self.assertEqual(result["commands"], [])

    def test_blocked_when_block_has_no_bbox(self):
        plan = make_page_plan(labels=False)
        plan["blocks"].append({"id": "block.lost", "title": "unplaced",
                               "zone": [100, 100, 200, 200]})
        result = self.compile(plan)
        self.assertEqual(result["status"], "blocked")
        self.assertIn(("missing_bbox", "block.lost"),
                      [(row["rule"], row["id"]) for row in result["findings"]])
        self.assertIsNone(result["exec_spec"])
        self.assertIn("no bbox", result["decision_record"])

    # -- edge cases ------------------------------------------------------

    def test_no_title_block_still_compiles(self):
        result = self.compile(make_page_plan(title_block=False))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["findings"], [])
        self.assertIn("No title block was supplied", result["decision_record"])

    def test_labels_without_anchor_emit_no_text_ops(self):
        plan = make_page_plan()
        plan["labels"] = [{"text": "note", "bbox": [10, 10, 60, 20]}]
        result = self.compile(plan)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["commands"]), 3)  # frame + 2 blocks
        self.assertFalse(any("sch apply" in command
                             for command in result["commands"]))
        self.assertEqual(len(result["artifacts"]), 2)
        self.assertIn("no text ops", result["decision_record"])

    def test_compile_is_deterministic_and_leaves_input_untouched(self):
        plan = make_page_plan()
        project = dict(PROJECT)
        before_plan = copy.deepcopy(plan)
        before_project = copy.deepcopy(project)
        first = compile_apply_plan(plan, project)
        second = compile_apply_plan(plan, project)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, ensure_ascii=False),
                         json.dumps(second, ensure_ascii=False))
        self.assertEqual(plan, before_plan)
        self.assertEqual(project, before_project)

    def test_export_name_and_out_dir_can_be_overridden(self):
        project = dict(PROJECT, out_dir="build/apply/", export_name="board-v2")
        result = self.compile(project=project)
        self.assertEqual(result["exec_spec"]["out_dir"], "build/apply")
        self.assertEqual(result["exec_spec"]["export_name"], "board-v2")
        self.assertEqual(result["exec_spec"]["plan"],
                         "build/apply/board-v2.plan.json")
        self.assertTrue(result["commands"][0].startswith(
            "easycirq sch frame apply --from build/apply/board-v2.frames.json"))

    def test_title_block_accepts_list_form_and_project_fallback(self):
        plan = make_page_plan(title_block=False)
        plan["title_block"] = [610, 12, 1170, 380]
        result = self.compile(plan)
        self.assertEqual(result["status"], "ready")
        self.assertIn("title block keep-out: [610, 12, 1170, 380]",
                      result["decision_record"])

        plan = make_page_plan(title_block=False)
        plan["blocks"][0]["bbox"] = [700, 100, 900, 220]
        plan["blocks"][0]["zone"] = [700, 100, 900, 220]
        project = dict(PROJECT, title_block={"rect": {"minX": 610, "minY": 12,
                                                      "maxX": 1170, "maxY": 380}})
        result = compile_apply_plan(plan, project)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["findings"][0]["kind"], "block")

    def test_invalid_project_is_rejected(self):
        plan = make_page_plan()
        with self.assertRaises(ValueError):
            compile_apply_plan(plan, {"project_uuid": "p", "page": "d"})
        with self.assertRaises(ValueError):
            compile_apply_plan(plan, dict(PROJECT, project_uuid=" "))

    def test_at_accepts_list_coordinates(self):
        plan = make_page_plan(labels=False)
        plan["blocks"][1]["at"] = [670, 500]
        result = self.compile(plan)
        self.assertEqual(
            result["exec_spec"]["plan_payload"]["placements"][1]["at"],
            "670,500")
        self.assertIn("--at 670,500", result["commands"][2])


if __name__ == "__main__":
    unittest.main()


class ApplyOffsetTests(unittest.TestCase):
    def test_offsets_back_calculate_at(self):
        from tools.layout2.sch_layout_apply2 import compile_apply_plan
        page = {"page": 1, "frames": [], "labels": [],
                "blocks": [{"id": "b1", "title": "t",
                            "bbox": [100, 200, 300, 400],
                            "zone": [90, 190, 310, 440]}]}
        project = {"project_uuid": "p", "page": "pg", "parts_path": "parts.json",
                   "apply_offsets": {"b1": {"dx": -10, "dy": -20}}}
        bundle = compile_apply_plan(page, project)
        placements = bundle["exec_spec"]["plan_payload"]["placements"]
        self.assertEqual(placements[0]["at"], "110,220")

