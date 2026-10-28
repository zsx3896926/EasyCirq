import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "easycirq"
REFS = SKILL / "references"
DEC = REFS / "decisions"
CASES = DEC / "cases"
ASSETS = SKILL / "assets" / "decisions"
SCRIPTS = SKILL / "scripts"
SOURCE_REGISTER = REFS / "source-register.md"

REF_IDS = {
    "a01-architecture-decision.md": ("R4-A01", "[A]"),
    "b01-pin-resource-planning.md": ("R4-B01", "[B]"),
    "c01-state-transition-contract.md": ("R4-C01", "[C]"),
    "d01-tolerance-and-worst-case.md": ("R4-D", "[D]"),
    "e01-interface-contract.md": ("R4-E01", "[E]"),
    "f01-harness-and-board-external.md": ("R4-F", "[F]"),
    "g01-product-variants.md": ("R4-G", "[G]"),
    "h01-calibration-and-identity.md": ("R4-H", "[H]"),
    "i01-change-impact.md": ("R4-I", "[I]"),
    "j01-module-reuse.md": ("R4-J", "[J]"),
    "k01-controlled-experiment.md": ("R4-K", "[K]"),
    "l01-asset-validity.md": ("R4-L", "[L]"),
}

CASE_IDS = {
    "r4-case-a01-requirement-change.md": ("R4-CASE-A01", "R4-P2"),
    "r4-case-a02-overdesign-gate.md": ("R4-CASE-A02", "R4-P1"),
    "r4-case-b01-pin-allocation-conflict.md": ("R4-CASE-B01", "R4-P1"),
    "r4-case-c01-battery-plus-external-supply-states.md": ("R4-CASE-C01", "R4-P2"),
    "r4-case-d01-acquisition-tolerance.md": ("R4-CASE-D01", "R4-P3"),
    "r4-case-e01-multiboard-interface-contract.md": ("R4-CASE-E01", "R4-P4"),
    "r4-case-f01-multiboard-harness.md": ("R4-CASE-F01", "R4-P4"),
    "r4-case-g01-two-sales-configs-one-board.md": ("R4-CASE-G01", "R4-P5"),
    "r4-case-h01-measurement-node-calibration.md": ("R4-CASE-H01", "R4-P3"),
    "r4-case-i01-legacy-product-revision.md": ("R4-CASE-I01", "R4-P6"),
    "r4-case-j01-charger-power-path-reuse.md": ("R4-CASE-J01", "R4-P2"),
    "r4-case-k01-acquisition-single-variable.md": ("R4-CASE-K01", "R4-P3"),
    "r4-case-l01-asset-validity-conflict.md": ("R4-CASE-L01", "R4-P6"),
}

TEMPLATES = [
    "decision-record.template.md",
    "pin-plan.template.json",
    "state-transition.template.json",
    "interface-contract.template.json",
    "tolerance-budget.template.md",
    "experiment-record.template.md",
    "harness-package.template.md",
    "variant-matrix.template.md",
    "variant-bom.template.json",
    "calibration-record.template.json",
    "change-record.template.json",
    "change-impact-graph.template.json",
    "module-reuse-record.template.md",
    "asset-index.template.md",
]

DECISION_SCRIPTS = [
    "pin_plan_check.py",
    "interface_contract_check.py",
    "harness_check.py",
    "variant_bom.py",
    "decision_record_check.py",
    "decision_asset_check.py",
]

DECISION_TESTS = [
    "test_decisions_ab.py",
    "test_decisions_ce.py",
    "test_decisions_dk.py",
    "test_decisions_fg.py",
    "test_decisions_hi.py",
    "test_decisions_jl.py",
]

REQUIRED_RECORD_TYPES = {
    "refuted-assumption",
    "unknown-retained",
    "requirement-change",
    "local-only",
    "reuse-rejected",
}


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    data = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def body_lines(path):
    return len(path.read_text(encoding="utf-8").splitlines())


def md_files(directory):
    return sorted(p for p in directory.glob("*.md") if p.name.lower() != "readme.md")


class DecisionsIndex(unittest.TestCase):
    def test_reference_count_and_structure(self):
        files = md_files(DEC)
        self.assertEqual(len(files), 12, [p.name for p in files])
        self.assertEqual({p.name for p in files}, set(REF_IDS))
        for path in files:
            meta = frontmatter(path)
            expected_id, expected_packages = REF_IDS[path.name]
            with self.subTest(path=path.name):
                self.assertEqual(meta.get("id"), expected_id)
                self.assertEqual(meta.get("packages"), expected_packages)
                self.assertTrue(meta.get("sources"))
                self.assertGreaterEqual(body_lines(path), 60)
                self.assertLessEqual(body_lines(path), 110)
                text = path.read_text(encoding="utf-8")
                for heading in [f"## {i}." for i in range(1, 11)]:
                    self.assertIn(heading, text)
                self.assertNotIn("[TODO", text)

    def test_case_count_and_frontmatter(self):
        files = md_files(CASES)
        self.assertEqual(len(files), 13, [p.name for p in files])
        self.assertEqual({p.name for p in files}, set(CASE_IDS))
        projects = set()
        for path in files:
            meta = frontmatter(path)
            expected_id, expected_project = CASE_IDS[path.name]
            with self.subTest(path=path.name):
                self.assertEqual(meta.get("id"), expected_id)
                self.assertEqual(meta.get("project"), expected_project)
                self.assertIn(meta.get("family"), {"P01", "P02", "P03"})
                self.assertTrue(meta.get("parent"))
                self.assertTrue(meta.get("facts_source"))
                self.assertEqual(meta.get("execution"), "OFFLINE_PLANNING")
                self.assertEqual(meta.get("hardware_execution"), "NOT RUN")
                self.assertTrue(meta.get("record_types"))
                self.assertGreaterEqual(body_lines(path), 50)
                self.assertLessEqual(body_lines(path), 100)
                text = path.read_text(encoding="utf-8")
                for heading in [f"## {i}." for i in range(1, 10)]:
                    self.assertIn(heading, text)
                self.assertNotIn("[TODO", text)
                projects.add(meta.get("project"))
        self.assertEqual(projects, {"R4-P1", "R4-P2", "R4-P3", "R4-P4", "R4-P5", "R4-P6"})

    def test_template_count_and_agent_fill_rule(self):
        actual = sorted(
            [p.name for p in ASSETS.glob("*.template.md")]
            + [p.name for p in ASSETS.glob("*.template.json")]
        )
        self.assertEqual(actual, sorted(TEMPLATES))
        for name in TEMPLATES:
            path = ASSETS / name
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                if path.suffix == ".json":
                    data = json.loads(path.read_text(encoding="utf-8"))
                    marker = str(data.get("_note", "")) + str(data.get("_template", ""))
                else:
                    marker = path.read_text(encoding="utf-8")
                self.assertIn("Agent 填写", marker)
                self.assertGreaterEqual(body_lines(path), 25)
                self.assertLessEqual(body_lines(path), 70)

    def test_scripts_and_tests_exist(self):
        for name in DECISION_SCRIPTS:
            self.assertTrue((SCRIPTS / name).is_file(), name)
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertIn("board_verified", text)
            self.assertNotRegex(text, r"^\s*(import|from)\s+(requests|urllib|socket)\b", )
        for name in DECISION_TESTS:
            self.assertTrue((ROOT / "tests" / name).is_file(), name)

    def test_readme_index_covers_all_assets(self):
        readme = (DEC / "README.md").read_text(encoding="utf-8")
        cases_readme = (CASES / "README.md").read_text(encoding="utf-8")
        for token in ("D0", "D1", "D2", "OFFLINE_PLANNING", "NOT RUN"):
            self.assertIn(token, readme)
        for name in REF_IDS:
            self.assertIn(name, readme)
        for name in CASE_IDS:
            self.assertIn(name, cases_readme)
        for name in TEMPLATES:
            self.assertIn(name, readme)
        for name in DECISION_SCRIPTS:
            self.assertIn(name, readme)
        for project in ("R4-P1", "R4-P2", "R4-P3", "R4-P4", "R4-P5", "R4-P6"):
            self.assertIn(project, cases_readme)

    def test_record_type_owners(self):
        seen = set()
        for path in md_files(CASES):
            meta = frontmatter(path)
            types = {
                item.strip(" []")
                for item in meta.get("record_types", "").split(",")
                if item.strip(" []")
            }
            seen |= types
        self.assertTrue(REQUIRED_RECORD_TYPES <= seen, sorted(REQUIRED_RECORD_TYPES - seen))

    def test_relative_links_exist(self):
        files = list(DEC.rglob("*.md")) + list(ASSETS.glob("*.md"))
        for path in files:
            text = path.read_text(encoding="utf-8")
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if link.startswith(("http://", "https://", "#")):
                    continue
                target = link.split("#", 1)[0]
                if not target:
                    continue
                resolved = (path.parent / target).resolve()
                with self.subTest(path=str(path.relative_to(ROOT)), link=link):
                    self.assertTrue(resolved.is_file(), f"{path}: {link}")

    def test_source_ids_registered(self):
        text = SOURCE_REGISTER.read_text(encoding="utf-8")
        registered = set(re.findall(r"\|\s*([A-Z]{2,4}-S\d+)", text))
        missing = set()
        scan = list(DEC.rglob("*.md")) + list(ASSETS.glob("*.md")) + list(ASSETS.glob("*.json"))
        for path in scan:
            cited = set(re.findall(r"\b([A-Z]{2,4}-S\d+)\b", path.read_text(encoding="utf-8")))
            missing |= cited - registered
        self.assertEqual(missing, set(), sorted(missing))

    def test_no_unmarked_c_numbers(self):
        hits = []
        scan = list(DEC.rglob("*.md")) + list(ASSETS.glob("*.md")) + list(ASSETS.glob("*.json"))
        for path in scan:
            for line in path.read_text(encoding="utf-8").splitlines():
                if re.search(r"\bC\d{4,}\b", line) and not any(
                    marker in line for marker in ("待查", "示例", "未核对")
                ):
                    hits.append(f"{path.relative_to(ROOT)}: {line.strip()[:120]}")
        self.assertEqual(hits, [], "\n".join(hits))

    def test_no_todo_or_other_workstream(self):
        scan = list(DEC.rglob("*.md")) + list(ASSETS.glob("*.md")) + list(ASSETS.glob("*.json"))
        for path in scan:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertNotIn("[TODO", text)
                self.assertNotIn("common-hardware", text)

    def test_bq24074_min_typ_max_semantics(self):
        forbidden = ("4.20 V 档", "4.16 V 档", "锁定 4.20 V 档")
        checked = [
            DEC / "cases" / "r4-case-a01-requirement-change.md",
            DEC / "cases" / "r4-case-j01-charger-power-path-reuse.md",
            DEC / "cases" / "r4-case-c01-battery-plus-external-supply-states.md",
            DEC / "j01-module-reuse.md",
        ]
        for path in checked:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for phrase in forbidden:
                    self.assertNotIn(phrase, text)
                self.assertIn("min/typ/max", text)
                self.assertIn("4.23 V max", text)

    def test_key_assets_are_instantiated(self):
        self.assertTrue((CASES / "r4-case-l01-asset-validity-conflict.md").is_file())
        reuse = json.loads(
            (ASSETS / "module-reuse-record.r4p2.example.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(reuse.get("blocks", [])), 2)
        expected_groups = {
            "function",
            "interface",
            "input_load_environment_dependencies",
            "immutable",
            "allowed",
            "recompute",
            "source_version_licence",
            "compatibility_matrix",
            "instantiation_verification",
            "status_retirement",
        }
        for block in reuse["blocks"]:
            self.assertEqual(set(block.get("contract_groups", {})), expected_groups)
        j01 = (CASES / "r4-case-j01-charger-power-path-reuse.md").read_text(encoding="utf-8")
        self.assertIn("rejected", j01)
        self.assertIn("accepted-with-conditions", j01)
        h01 = (CASES / "r4-case-h01-measurement-node-calibration.md").read_text(encoding="utf-8")
        self.assertIn("CAL-P3-001", h01)
        self.assertTrue("record_id" in h01 or "待建" in h01)
        i01 = (CASES / "r4-case-i01-legacy-product-revision.md").read_text(encoding="utf-8")
        self.assertTrue("bom_delta" in i01 or "BOM delta" in i01)
        self.assertTrue("layout-only" in i01 or "纯重排" in i01)

    def test_skill_route_and_engineering_notes_pointer(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/decisions/README.md", skill)
        notes = (SKILL / "assets" / "engineering-notes.md").read_text(encoding="utf-8")
        self.assertIn("decisions/decision-record.template.md", notes)


if __name__ == "__main__":
    unittest.main()
