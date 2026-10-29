"""Offline tests for tools/layout2/pagination.py (``easycirq-sch-pagination/v1``).

The planner is pure geometry/arithmetic: no EDA, no connector and no filesystem
state beyond the CLI fixture written to a temporary directory.  The page
geometry matches the layout-engine-v2 contract: 1170x825 page, margin 12 and a
title-block keep-out at [610..1170] x [12..380], which leaves 716282 usable
units in an L-shape.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "layout2" / "pagination.py"
sys.path.insert(0, str(ROOT))

from tools.layout2 import pagination  # noqa: E402

PAGE = {"width": 1170, "height": 825, "margin": 12}
TITLE_BLOCK = {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380}
TEMPLATE = {"page": dict(PAGE), "title_block": dict(TITLE_BLOCK)}
USABLE_AREA = 716282  # 1146*801 - 548*368


def module(module_id, w, h, group):
    return {"id": module_id, "w": w, "h": h, "affinity_group": group}


def three_modules():
    return [
        module("m1", 400, 300, "power"),
        module("m2", 350, 300, "mcu"),
        module("m3", 300, 250, "io"),
    ]


def six_modules():
    """Three affinity groups; groups are 357500, 330000 and 226000 units."""
    return [
        module("a1", 500, 400, "A"),
        module("a2", 450, 350, "A"),
        module("b1", 480, 400, "B"),
        module("b2", 460, 300, "B"),
        module("c1", 420, 300, "C"),
        module("c2", 400, 250, "C"),
    ]


class PaginationPlannerTests(unittest.TestCase):
    def assert_clean_assignment(self, result, modules, template=TEMPLATE):
        """Every module exactly once, every page inside the usable area."""
        self.assertEqual(result["schema"], pagination.SCHEMA)
        self.assertEqual(result["verdict"], pagination.VERDICT_PASS)
        self.assertEqual(result["page_count"], len(result["pages"]))
        assigned = [mid for page in result["pages"]
                    for mid in page["modules"]]
        self.assertCountEqual(assigned, [item["id"] for item in modules])

        capacity = pagination.usable_area(template)
        by_id = {item["id"]: item for item in modules}
        for number, page in enumerate(result["pages"], start=1):
            self.assertEqual(page["page"], number)
            expected = sum(by_id[mid]["w"] * by_id[mid]["h"]
                           for mid in page["modules"])
            self.assertEqual(page["estimated_area"], expected)
            self.assertLessEqual(page["estimated_area"], capacity)
        self.assertEqual(pagination.validate_plan(result, modules, template), [])

    def test_three_modules_fit_one_page(self):
        modules = three_modules()
        result = pagination.plan_pagination(modules, TEMPLATE)

        self.assert_clean_assignment(result, modules)
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["pages"][0]["page"], 1)
        self.assertCountEqual(result["pages"][0]["modules"],
                              ["m1", "m2", "m3"])
        self.assertEqual(result["pages"][0]["estimated_area"], 300000)
        self.assertEqual(result["gaps"], [])

    def test_six_modules_two_pages_keep_affinity(self):
        modules = six_modules()
        result = pagination.plan_pagination(modules, TEMPLATE)

        self.assert_clean_assignment(result, modules)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["gaps"], [])

        # A (357500) and B (330000) share page 1; C (226000) gets page 2.
        self.assertCountEqual(result["pages"][0]["modules"],
                              ["a1", "a2", "b1", "b2"])
        self.assertCountEqual(result["pages"][1]["modules"], ["c1", "c2"])
        self.assertEqual(result["pages"][0]["estimated_area"], 687500)
        self.assertEqual(result["pages"][1]["estimated_area"], 226000)

        groups = {"A": {"a1", "a2"}, "B": {"b1", "b2"}, "C": {"c1", "c2"}}
        for group, members in groups.items():
            pages_with_group = [page for page in result["pages"]
                                if members & set(page["modules"])]
            self.assertEqual(len(pages_with_group), 1,
                             f"affinity group {group} was split across pages")

    def test_page_count_matches_area_lower_bound(self):
        # Four 500x400 modules: 800000 units > 716282 usable -> 2 pages.
        modules = [module(f"m{i}", 500, 400, f"g{i}") for i in range(1, 5)]
        total = sum(item["w"] * item["h"] for item in modules)
        lower_bound = pagination.area_lower_bound(total, USABLE_AREA)

        result = pagination.plan_pagination(modules, TEMPLATE)
        self.assert_clean_assignment(result, modules)
        self.assertEqual(lower_bound, 2)
        self.assertEqual(result["page_count"], lower_bound)
        self.assertEqual([page["estimated_area"] for page in result["pages"]],
                         [600000, 200000])

    def test_huge_module_is_blocked(self):
        modules = [
            module("ok", 300, 200, "power"),
            module("big", 2000, 900, "power"),
            module("ok2", 250, 200, "io"),
        ]
        result = pagination.plan_pagination(modules, TEMPLATE)

        self.assertEqual(result["schema"], pagination.SCHEMA)
        self.assertEqual(result["verdict"], pagination.VERDICT_BLOCKED)
        self.assertEqual(result["pages"], [])
        self.assertEqual(result["page_count"], 0)
        self.assertEqual(len(result["gaps"]), 1)
        gap = result["gaps"][0]
        self.assertEqual(gap["code"], "module_over_page")
        self.assertEqual(gap["module"], "big")
        self.assertIn("big", gap["message"])

    def test_module_fits_usable_strip_but_not_disjoint_region(self):
        # 598x700 fits the full-height left strip beside the title block even
        # though no single disjoint usable rectangle is that tall.
        tall = module("tall", 598, 700, "power")
        page = pagination.parse_template(TEMPLATE)
        self.assertTrue(any(rect.holds(598, 700)
                            for rect in page.placement_rects))
        self.assertFalse(any(rect.holds(598, 700)
                             for rect in page.usable_rects))

        result = pagination.plan_pagination([tall], TEMPLATE)
        self.assertEqual(result["verdict"], pagination.VERDICT_PASS)
        self.assertEqual(result["pages"][0]["modules"], ["tall"])

    def test_determinism(self):
        modules = six_modules()
        first = pagination.plan_pagination(modules, TEMPLATE)
        for _ in range(5):
            self.assertEqual(pagination.plan_pagination(modules, TEMPLATE),
                             first)
        self.assertEqual(json.dumps(pagination.plan_pagination(modules, TEMPLATE)),
                         json.dumps(first))

    def test_document_input_with_options(self):
        document = {"modules": three_modules(),
                    "page_template": TEMPLATE,
                    "options": {"min_pages": 2, "max_pages": 4}}
        result = pagination.plan_pagination(document)
        self.assert_clean_assignment(result, three_modules())
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["pages"][1]["modules"], [])

    def test_max_pages_blocks_when_exceeded(self):
        modules = six_modules()
        result = pagination.plan_pagination(modules, TEMPLATE, max_pages=1)
        self.assertEqual(result["verdict"], pagination.VERDICT_BLOCKED)
        self.assertEqual(result["pages"], [])
        gap = result["gaps"][0]
        self.assertEqual(gap["code"], "max_pages_exceeded")
        self.assertEqual(gap["required_pages"], 2)
        self.assertEqual(gap["max_pages"], 1)

        allowed = pagination.plan_pagination(modules, TEMPLATE, max_pages=2)
        self.assertEqual(allowed["verdict"], pagination.VERDICT_PASS)
        self.assertEqual(allowed["page_count"], 2)

    def test_min_pages_pads_with_empty_pages(self):
        result = pagination.plan_pagination(three_modules(), TEMPLATE,
                                            min_pages=3)
        self.assert_clean_assignment(result, three_modules())
        self.assertEqual(result["page_count"], 3)
        self.assertCountEqual(result["pages"][0]["modules"],
                              ["m1", "m2", "m3"])
        self.assertEqual(result["pages"][1]["modules"], [])
        self.assertEqual(result["pages"][2]["modules"], [])
        self.assertEqual(result["pages"][1]["estimated_area"], 0)

    def test_empty_module_list(self):
        result = pagination.plan_pagination([], TEMPLATE)
        self.assertEqual(result["verdict"], pagination.VERDICT_PASS)
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["pages"][0]["modules"], [])

        none = pagination.plan_pagination([], TEMPLATE, min_pages=0)
        self.assertEqual(none["page_count"], 0)
        self.assertEqual(none["pages"], [])

    def test_oversized_affinity_group_is_split_between_whole_modules(self):
        modules = [module(f"r{i}", 500, 400, "rail") for i in range(1, 6)]
        result = pagination.plan_pagination(modules, TEMPLATE)

        self.assertEqual(result["verdict"], pagination.VERDICT_PASS)
        self.assert_clean_assignment(result, modules)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(len(result["gaps"]), 1)
        gap = result["gaps"][0]
        self.assertEqual(gap["code"], "affinity_split")
        self.assertEqual(gap["group"], "rail")
        self.assertEqual(gap["pages"], [1, 2])
        # No module was split: every id still appears exactly once.
        self.assertEqual(sorted(mid for page in result["pages"]
                                for mid in page["modules"]),
                         [f"r{i}" for i in range(1, 6)])

    def test_contract_shaped_and_missing_title_block(self):
        contract_template = {
            "schema": "easycirq-page-template/v1",
            "page": dict(PAGE),
            "title_block": {"rect": dict(TITLE_BLOCK),
                            "provenance": "sch sheet-geometry"},
        }
        self.assertEqual(pagination.usable_area(contract_template),
                         USABLE_AREA)
        result = pagination.plan_pagination(three_modules(), contract_template)
        self.assert_clean_assignment(result, three_modules(), contract_template)

        no_keepout = {"page": dict(PAGE)}
        self.assertEqual(pagination.usable_area(no_keepout), 1146 * 801)
        result = pagination.plan_pagination(three_modules(), no_keepout)
        self.assert_clean_assignment(result, three_modules(), no_keepout)

    def test_flat_template_is_accepted(self):
        flat = dict(PAGE, title_block=dict(TITLE_BLOCK))
        self.assertEqual(pagination.usable_area(flat), USABLE_AREA)
        result = pagination.plan_pagination(three_modules(), flat)
        self.assert_clean_assignment(result, three_modules(), flat)

    def test_invalid_inputs_raise(self):
        cases = {
            "duplicate id": ([module("dup", 10, 10, "A"),
                              module("dup", 20, 20, "B")], TEMPLATE),
            "zero width": ([module("m", 0, 10, "A")], TEMPLATE),
            "negative height": ([module("m", 10, -1, "A")], TEMPLATE),
            "modules not a list": ("nope", TEMPLATE),
            "huge margin": (three_modules(),
                            {"page": {"width": 100, "height": 100,
                                      "margin": 50}}),
            "title block outside page": (three_modules(),
                                         {"page": dict(PAGE),
                                          "title_block": {"minX": 9000,
                                                          "minY": 0,
                                                          "maxX": 9500,
                                                          "maxY": 10}}),
            "inverted title block": (three_modules(),
                                     {"page": dict(PAGE),
                                      "title_block": {"minX": 700, "minY": 12,
                                                      "maxX": 600, "maxY": 380}}),
        }
        for name, (modules, template) in cases.items():
            with self.subTest(name):
                with self.assertRaises(pagination.PaginationError):
                    pagination.plan_pagination(modules, template)

        with self.assertRaises(pagination.PaginationError):
            pagination.plan_pagination({"not_modules": []})
        with self.assertRaises(pagination.PaginationError):
            pagination.plan_pagination(three_modules(), TEMPLATE,
                                       min_pages=3, max_pages=2)
        with self.assertRaises(pagination.PaginationError):
            pagination.plan_pagination(three_modules(), TEMPLATE, max_pages=0)

    def test_validate_plan_reports_broken_results(self):
        modules = three_modules()
        result = pagination.plan_pagination(modules, TEMPLATE)
        self.assertEqual(pagination.validate_plan(result, modules, TEMPLATE),
                         [])

        duplicated = json.loads(json.dumps(result))
        duplicated["pages"][0]["modules"].append("m1")
        issues = pagination.validate_plan(duplicated, modules)
        self.assertTrue(any("more than once" in issue for issue in issues))

        inflated = json.loads(json.dumps(result))
        inflated["pages"][0]["estimated_area"] = USABLE_AREA + 1
        issues = pagination.validate_plan(inflated, modules, TEMPLATE)
        self.assertTrue(any("exceeds usable area" in issue for issue in issues))

        wrong_count = json.loads(json.dumps(result))
        wrong_count["page_count"] = 2
        issues = pagination.validate_plan(wrong_count)
        self.assertTrue(any("page_count" in issue for issue in issues))

        self.assertTrue(pagination.validate_plan(result, modules,
                                                 min_pages=2))

    def test_cli_writes_json_and_uses_documented_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            good = tmp_path / "plan.json"
            good.write_text(json.dumps({"modules": three_modules(),
                                        "page_template": TEMPLATE}),
                            encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(good)],
                capture_output=True, text=True, encoding="utf-8",
                cwd=str(ROOT), check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["schema"], pagination.SCHEMA)
            self.assertEqual(payload["verdict"], "pass")
            self.assertEqual(payload["page_count"], 1)

            blocked = tmp_path / "blocked.json"
            blocked.write_text(json.dumps({
                "modules": [module("big", 5000, 5000, "A")],
                "page_template": TEMPLATE,
            }), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(blocked)],
                capture_output=True, text=True, encoding="utf-8",
                cwd=str(ROOT), check=False)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["verdict"], "blocked")

            out_path = tmp_path / "out.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(good),
                 "--out", str(out_path)],
                capture_output=True, text=True, encoding="utf-8",
                cwd=str(ROOT), check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(out_path.read_text(encoding="utf-8"))
                             ["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
