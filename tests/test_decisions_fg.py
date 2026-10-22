"""R4-WS4 (F harness and G variants) document, asset and CLI tests.

Fixtures are handwritten. Expected counts and quantities are derived by hand
from the documented formula, not by importing the scripts under test to
generate them.  CLI tests exercise the real entry points and exit codes.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
DH = ROOT / "design-hardware"
REF = DH / "references" / "decisions"
CASES = REF / "cases"
ASSETS = DH / "assets" / "decisions"
SCRIPTS = DH / "scripts"
SOURCE_REGISTER = DH / "references" / "source-register.md"

F01_REF = REF / "f01-harness-and-board-external.md"
G01_REF = REF / "g01-product-variants.md"
F01_CASE = CASES / "r4-case-f01-multiboard-harness.md"
G01_CASE = CASES / "r4-case-g01-two-sales-configs-one-board.md"
HARNESS_TEMPLATE = ASSETS / "harness-package.template.md"
MATRIX_TEMPLATE = ASSETS / "variant-matrix.template.md"
BOM_TEMPLATE = ASSETS / "variant-bom.template.json"
HARNESS_EXAMPLE = ASSETS / "harness.r4p4.example.json"
VARIANTS_EXAMPLE = ASSETS / "variants.r4p5.example.json"
HARNESS_SCRIPT = SCRIPTS / "harness_check.py"
VARIANT_SCRIPT = SCRIPTS / "variant_bom.py"

OWNED = [F01_REF, G01_REF, F01_CASE, G01_CASE, HARNESS_TEMPLATE,
         MATRIX_TEMPLATE, BOM_TEMPLATE, HARNESS_EXAMPLE, VARIANTS_EXAMPLE,
         HARNESS_SCRIPT, VARIANT_SCRIPT, Path(__file__)]

REFERENCE_HEADINGS = [
    "## 目录",
    "## 1. 触发条件",
    "## 2. 输入",
    "## 3. Agent 可独立完成的判断",
    "## 4. 必须停下的条件",
    "## 5. 决策规则与表",
    "## 6. 改变哪个工程决定",
    "## 7. 完整案例",
    "## 8. 证据与验证方式",
    "## 9. 与现有资产的分工",
    "## 10. 来源、未知与重评触发",
]
CASE_HEADINGS = [
    "## 1. 触发与用户任务",
    "## 2. 产品与真实材料",
    "## 3. 初始决定（错在哪）",
    "## 4. 判定依据（path:start-end）",
    "## 5. 修正后的决定、代价与三行用户可见摘要",
    "## 6. 记录类型与 typed block",
    "## 7. 验证与证据状态",
    "## 8. 未知、停止与重评",
    "## 9. 与现有资产分工",
]


def read_text(path):
    return path.read_text(encoding="utf-8")


def frontmatter(text):
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    data = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def section(text, heading):
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start:] if nxt < 0 else text[start:nxt]


def line_count(text):
    return len(text.splitlines())


def run_cli(script, payload=None, raw=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.json"
        text = raw if raw is not None else json.dumps(payload, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    return proc


def codes(result):
    return {finding["code"] for finding in result["findings"]}


def connector(cid, side, mate, keying, **overrides):
    base = {
        "id": cid,
        "side": side,
        "mate": mate,
        "mpn": "FIXTURE-CONN-" + cid,
        "mating_housing": "FIXTURE-HOUSING-" + cid,
        "mating_terminal": "FIXTURE-TERM-" + cid,
        "crimp_tool": "FIXTURE-TOOL-" + cid,
        "status": "planned",
        "rated_current_a": 3,
        "rated_voltage_v": 250,
        "wire_gauge_range": "0.14-0.5 mm2",
        "shielding": "none",
        "keying": keying,
        "lock": "latch",
    }
    base.update(overrides)
    return base


def wire(net, board, harness, **overrides):
    base = {
        "net": net,
        "board": board,
        "harness": harness,
        "gauge": "0.5 mm2",
        "length_m": 0.3,
        "shielding": "none",
        "continuity": "pass",
        "pull_test": "pass",
        "latch_check": "pass",
        "label": "pass",
        "bend_radius_mm": 15,
        "evidence": "FIXTURE-RECORD",
    }
    base.update(overrides)
    return base


def harness_pass():
    return {
        "schema": "harness-package/v1",
        "package_id": "FIXTURE-HARNESS",
        "revisions": {"harness_rev": "H1", "board_rev": "B1",
                      "enclosure_rev": "E1", "binding": ["H1", "B1", "E1"]},
        "connectors": [
            connector("J1", "board", "P1", "A"),
            connector("P1", "harness", "J1", "A"),
            connector("J2", "board", "none", "B"),
        ],
        "wires": [
            wire("3V3", "J1.1", "P1.1"),
            wire("GND", "J1.2", "P1.2"),
        ],
        "misconnection_matrix": [
            {"a": "J1", "b": "J2", "result": "blocked", "note": "keying A/B"},
            {"a": "P1", "b": "J2", "result": "blocked", "note": "keying A/B"},
        ],
    }


def harness_unknown():
    package = harness_pass()
    package["revisions"].update(board_rev="待查", enclosure_rev="待查",
                                binding=["H1"])
    for item in package["connectors"]:
        for key in ("mpn", "mating_housing", "mating_terminal", "crimp_tool",
                    "rated_current_a", "rated_voltage_v", "wire_gauge_range",
                    "shielding", "keying", "lock"):
            item[key] = "待查"
    for item in package["wires"]:
        item.update(gauge="待查", length_m="待查", shielding="待查",
                    continuity="NOT RUN", pull_test="NOT RUN",
                    latch_check="NOT RUN", label="NOT RUN",
                    bend_radius_mm="待查", evidence="待查")
    for row in package["misconnection_matrix"]:
        row["result"] = "待查"
    return package


def variant_pass():
    return {
        "schema": "variant-bom/v1",
        "product": "FIXTURE-PRODUCT",
        "master_bom": [
            {"ref": "K1", "per_board": 1, "exclusive_group": "output-switch",
             "requires": ["D2"], "package_step": "待查"},
            {"ref": "Q2", "per_board": 1, "exclusive_group": "output-switch",
             "requires": ["Rg", "TVS"], "package_step": "待查"},
            {"ref": "D2", "per_board": 1, "package_step": "待查"},
            {"ref": "Rg", "per_board": 1, "package_step": "待查"},
            {"ref": "TVS", "per_board": 1, "package_step": "待查"},
            {"ref": "C1", "per_board": 2, "package_step": "待查"},
        ],
        "variants": [
            {"id": "V1", "boards": 5, "attrition_rate": 0.05, "min_spare": 2,
             "requires": ["K1", "C1"], "conflicts": [["K1", "Q2"]],
             "forbidden": ["Q2", "Rg", "TVS"], "dnp": ["Q2", "Rg", "TVS"],
             "firmware_config": "relay", "test_delta": "relay pull-in"},
            {"id": "V2", "boards": 25, "attrition_rate": 0.05, "min_spare": 2,
             "requires": ["Q2", "C1"], "conflicts": [["K1", "Q2"]],
             "forbidden": ["K1", "D2"], "dnp": ["K1", "D2"],
             "firmware_config": "pwm", "test_delta": "pwm load"},
        ],
    }


def needed_map(result, variant_id):
    variant = next(item for item in result["variants"]
                   if item["variant"] == variant_id)
    return {entry["ref"]: entry.get("needed") for entry in variant["needed"]}


class FilesAndEncoding(unittest.TestCase):
    def test_owned_files_exist(self):
        for path in OWNED:
            with self.subTest(path=str(path)):
                self.assertTrue(path.is_file(), path)

    def test_utf8_no_bom_lf_no_replacement_char(self):
        for path in OWNED:
            with self.subTest(path=str(path)):
                data = path.read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"), "BOM")
                self.assertNotIn(b"\r\n", data, "CRLF")
                text = data.decode("utf-8")
                self.assertNotIn(chr(0xFFFD), text)

    def test_no_todo_marker(self):
        marker = "[" + "TODO"
        for path in OWNED:
            with self.subTest(path=str(path)):
                self.assertNotIn(marker, read_text(path))


class ReferenceDocuments(unittest.TestCase):
    def test_frontmatter_and_headings(self):
        expected = {F01_REF: ("R4-F", "[F]"), G01_REF: ("R4-G", "[G]")}
        for path, (doc_id, package) in expected.items():
            with self.subTest(path=path.name):
                text = read_text(path)
                meta = frontmatter(text)
                self.assertEqual(meta.get("id"), doc_id)
                self.assertEqual(meta.get("packages"), package)
                self.assertEqual(meta.get("evidence"), "E3")
                self.assertEqual(meta.get("last_reviewed"), "2026-10-22")
                self.assertTrue(meta.get("sources"))
                last = -1
                for heading in REFERENCE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, last, heading)
                    last = pos

    def test_line_budget(self):
        for path in (F01_REF, G01_REF):
            with self.subTest(path=path.name):
                self.assertGreaterEqual(line_count(read_text(path)), 60)
                self.assertLessEqual(line_count(read_text(path)), 100)

    def test_section9_budget_and_anchors(self):
        anchor = re.compile(r"([A-Za-z0-9_./-]+\.md):(\d+)-(\d+)")
        for path in (F01_REF, G01_REF):
            with self.subTest(path=path.name):
                text = read_text(path)
                segment = section(text, "## 9. 与现有资产的分工")
                self.assertLessEqual(line_count(segment), 8)
                matches = anchor.findall(segment)
                self.assertGreaterEqual(len(matches), 2)
                for relative, start, end in matches:
                    target = ROOT / relative
                    self.assertTrue(target.is_file(), relative)
                    total = line_count(read_text(target))
                    self.assertGreaterEqual(int(start), 1, relative)
                    self.assertLessEqual(int(end), total, relative)
                    self.assertLessEqual(int(start), int(end), relative)


class CaseDocuments(unittest.TestCase):
    def test_frontmatter_and_headings(self):
        expected = {
            F01_CASE: ("R4-CASE-F01", "R4-P4", "P02", "[F]"),
            G01_CASE: ("R4-CASE-G01", "R4-P5", "P02", "[G]"),
        }
        for path, (case_id, project, family, package) in expected.items():
            with self.subTest(path=path.name):
                text = read_text(path)
                meta = frontmatter(text)
                self.assertEqual(meta.get("id"), case_id)
                self.assertEqual(meta.get("project"), project)
                self.assertEqual(meta.get("family"), family)
                self.assertEqual(meta.get("parent"), family)
                self.assertEqual(meta.get("packages"), package)
                self.assertEqual(meta.get("evidence"), "E3")
                self.assertEqual(meta.get("execution"), "OFFLINE_PLANNING")
                self.assertEqual(meta.get("hardware_execution"), "NOT RUN")
                self.assertEqual(meta.get("last_reviewed"), "2026-10-22")
                self.assertTrue(meta.get("facts_source"))
                self.assertIn("record_types", meta)
                last = -1
                for heading in CASE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, last, heading)
                    last = pos

    def test_line_budget(self):
        for path in (F01_CASE, G01_CASE):
            with self.subTest(path=path.name):
                self.assertGreaterEqual(line_count(read_text(path)), 50)
                self.assertLessEqual(line_count(read_text(path)), 90)

    def test_three_line_user_summary(self):
        for path in (F01_CASE, G01_CASE):
            with self.subTest(path=path.name):
                summary = section(read_text(path), "## 5. 修正后的决定、代价与三行用户可见摘要")
                for prefix in ("- 决定：", "- 代价：", "- 下一个检查或待查："):
                    matching = [line for line in summary.splitlines()
                                if line.startswith(prefix)]
                    self.assertEqual(len(matching), 1, prefix)

    def test_e01_is_referenced_as_path_not_link(self):
        text = read_text(F01_CASE)
        self.assertIn("e01-interface-contract.md", text)
        self.assertNotIn("](design-hardware/references/decisions/e01", text)
        self.assertNotIn("](../e01", text)


class TemplatesAndAssets(unittest.TestCase):
    def test_template_header_and_budget(self):
        for path in (HARNESS_TEMPLATE, MATRIX_TEMPLATE):
            with self.subTest(path=path.name):
                text = read_text(path)
                self.assertIn("Agent 填写，用户不填", text.splitlines()[0])
                self.assertGreaterEqual(line_count(text), 25)
                self.assertLessEqual(line_count(text), 60)
        self.assertIn("Agent 填写，用户不填", read_text(BOM_TEMPLATE))
        self.assertGreaterEqual(line_count(read_text(BOM_TEMPLATE)), 25)
        self.assertLessEqual(line_count(read_text(BOM_TEMPLATE)), 60)

    def test_sources_are_registered(self):
        registered = set(re.findall(r"\|\s*([A-Z]+-S\d+)\s*\|",
                                    read_text(SOURCE_REGISTER)))
        for path in (F01_REF, G01_REF, F01_CASE, G01_CASE):
            with self.subTest(path=path.name):
                raw = frontmatter(read_text(path)).get("sources", "")
                ids = re.findall(r"[A-Z]+-S\d+", raw)
                self.assertTrue(ids)
                self.assertTrue(set(ids) <= registered, set(ids) - registered)

    def test_relative_links_point_to_existing_files(self):
        link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for path in (F01_REF, G01_REF, F01_CASE, G01_CASE,
                     HARNESS_TEMPLATE, MATRIX_TEMPLATE):
            with self.subTest(path=path.name):
                for target in link.findall(read_text(path)):
                    if target.startswith(("http://", "https://")):
                        continue
                    relative = target.split("#", 1)[0]
                    self.assertTrue((path.parent / relative).is_file(), target)

    def test_example_assets_keep_unknowns(self):
        harness = json.loads(read_text(HARNESS_EXAMPLE))
        for item in harness["connectors"]:
            self.assertEqual(item["mpn"], "待查")
            self.assertEqual(item["mating_terminal"], "待查")
            self.assertEqual(item["crimp_tool"], "待查")
            self.assertEqual(item["rated_current_a"], "待查")
            self.assertEqual(item["rated_voltage_v"], "待查")
        for item in harness["wires"]:
            self.assertEqual(item["continuity"], "NOT RUN")
            self.assertEqual(item["bend_radius_mm"], "待查")
        variants = json.loads(read_text(VARIANTS_EXAMPLE))
        for item in variants["master_bom"]:
            self.assertEqual(item.get("mpn"), "待查")
            self.assertEqual(item.get("package_step"), "待查")
            self.assertNotIn("price", item)
            self.assertNotIn("stock", item)
            self.assertNotIn("moq", item)
        text = read_text(VARIANTS_EXAMPLE)
        self.assertNotIn('"price"', text)
        self.assertNotIn('"stock"', text)
        self.assertNotIn('"moq"', text)

    def test_json_assets_parse(self):
        for path in (BOM_TEMPLATE, HARNESS_EXAMPLE, VARIANTS_EXAMPLE):
            with self.subTest(path=path.name):
                json.loads(read_text(path))


class HarnessCheckCli(unittest.TestCase):
    def test_pass_fixture_exit_0(self):
        proc = run_cli(HARNESS_SCRIPT, harness_pass())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["board_verified"])
        self.assertEqual(result["execution"], "OFFLINE_PLANNING")
        self.assertEqual(result["hardware_execution"], "NOT RUN")
        self.assertTrue(result["not_checked"])

    def test_unknown_fixture_exit_1(self):
        proc = run_cli(HARNESS_SCRIPT, harness_unknown())
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "needs_review")
        found = codes(result)
        self.assertTrue({"revision_unknown", "connector_field_unknown",
                         "wire_test_not_run", "wire_field_unknown",
                         "matrix_unknown"} <= found, found)
        for finding in result["findings"]:
            self.assertEqual(set(finding), {"code", "severity", "message", "where"})

    def test_same_keying_without_block_exit_1(self):
        package = harness_pass()
        package["connectors"][2]["keying"] = "A"
        package["misconnection_matrix"][0]["result"] = "distinct"
        proc = run_cli(HARNESS_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("same_keying_not_blocked", codes(json.loads(proc.stdout)))

    def test_missing_matrix_row_exit_1(self):
        package = harness_pass()
        package["misconnection_matrix"] = []
        proc = run_cli(HARNESS_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertIn("matrix_incomplete", codes(result))
        blocking = [item for item in result["findings"]
                    if item["code"] == "matrix_incomplete"]
        self.assertEqual(len(blocking), 2)

    def test_approval_with_unknown_rating_exit_1(self):
        package = harness_pass()
        package["connectors"][2]["status"] = "approved"
        package["connectors"][2]["rated_current_a"] = "待查"
        proc = run_cli(HARNESS_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        found = codes(json.loads(proc.stdout))
        self.assertTrue({"connector_field_unknown",
                         "connector_approval_without_data"} <= found, found)

    def test_pass_without_evidence_exit_1(self):
        package = harness_pass()
        package["wires"][0]["evidence"] = ""
        proc = run_cli(HARNESS_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("wire_claim_without_evidence",
                      codes(json.loads(proc.stdout)))

    def test_wire_unknown_ref_exit_1(self):
        package = harness_pass()
        package["wires"][0]["board"] = "J9.1"
        proc = run_cli(HARNESS_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("wire_unknown_ref", codes(json.loads(proc.stdout)))

    def test_missing_field_exit_2(self):
        package = harness_pass()
        del package["revisions"]
        proc = run_cli(HARNESS_SCRIPT, package)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertFalse(result["board_verified"])

    def test_malformed_json_exit_2(self):
        proc = run_cli(HARNESS_SCRIPT, raw="{not json")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "invalid_input")

    def test_example_asset_exit_1_and_no_acceptance_wording(self):
        proc = run_cli(HARNESS_SCRIPT, raw=read_text(HARNESS_EXAMPLE))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertFalse(result["board_verified"])
        self.assertTrue(result["findings"])
        self.assertTrue(all(item["severity"] == "unknown"
                            for item in result["findings"]))
        self.assertNotIn("线束通过", proc.stdout)
        self.assertNotIn("可加工", proc.stdout)


class VariantBomCli(unittest.TestCase):
    def test_pass_fixture_exit_0_with_hand_calculated_needed(self):
        proc = run_cli(VARIANT_SCRIPT, variant_pass())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])
        self.assertEqual(needed_map(result, "V1"),
                         {"D2": 7, "K1": 7, "C1": 12})
        self.assertEqual(needed_map(result, "V2"),
                         {"Rg": 27, "TVS": 27, "Q2": 27, "C1": 53})
        for variant in result["variants"]:
            self.assertEqual(variant["order_qty_status"], "待查")
            for entry in variant["needed"]:
                self.assertNotIn("order_qty", entry)
                self.assertEqual(entry["order_qty_status"], "待查")
        self.assertFalse(result["board_verified"])
        self.assertEqual(result["execution"], "OFFLINE_PLANNING")
        self.assertEqual(result["hardware_execution"], "NOT RUN")

    def test_conflict_pair_exit_1(self):
        package = variant_pass()
        package["variants"][0]["requires"] = ["K1", "Q2"]
        proc = run_cli(VARIANT_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        found = codes(json.loads(proc.stdout))
        self.assertTrue({"variant_conflict", "mixup_exclusive_group"} <= found,
                        found)

    def test_required_and_forbidden_exit_1(self):
        package = variant_pass()
        package["variants"][0]["forbidden"] = ["K1"]
        package["variants"][0]["dnp"] = []
        proc = run_cli(VARIANT_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("required_forbidden", codes(json.loads(proc.stdout)))

    def test_dnp_required_exit_1(self):
        package = variant_pass()
        package["variants"][0]["dnp"] = ["K1"]
        proc = run_cli(VARIANT_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("dnp_required_conflict", codes(json.loads(proc.stdout)))

    def test_unknown_boards_exit_1(self):
        package = variant_pass()
        package["variants"][0]["boards"] = "待查"
        proc = run_cli(VARIANT_SCRIPT, package)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertIn("unknown_quantity_input", codes(result))
        variant = result["variants"][0]
        self.assertEqual(variant["needed_status"], "待查")
        for entry in variant["needed"]:
            self.assertNotIn("needed", entry)
            self.assertEqual(entry["needed_status"], "待查")

    def test_known_package_step_gives_order_qty(self):
        package = variant_pass()
        package["master_bom"][5]["package_step"] = 5
        proc = run_cli(VARIANT_SCRIPT, package)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        variant = next(item for item in result["variants"]
                       if item["variant"] == "V1")
        entry = next(item for item in variant["needed"]
                     if item["ref"] == "C1")
        self.assertEqual(entry["needed"], 12)
        self.assertEqual(entry["order_qty"], 15)
        self.assertEqual(entry["order_qty_status"], "computed")

    def test_unknown_ref_exit_2(self):
        package = variant_pass()
        package["variants"][0]["requires"] = ["NOPE"]
        proc = run_cli(VARIANT_SCRIPT, package)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "invalid_input")

    def test_forbidden_commercial_field_exit_2(self):
        package = variant_pass()
        package["master_bom"][0]["price"] = 1
        proc = run_cli(VARIANT_SCRIPT, package)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "invalid_input")

    def test_example_asset_exit_0(self):
        proc = run_cli(VARIANT_SCRIPT, raw=read_text(VARIANTS_EXAMPLE))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["board_verified"])
        self.assertEqual(needed_map(result, "V1"),
                         {"D2": 7, "K1": 7, "R1": 7, "Q1": 7, "J3": 7,
                          "U1": 7, "C1": 12})
        self.assertEqual(needed_map(result, "V2"),
                         {"Rg": 27, "TVS": 27, "Q2": 27, "J3": 27,
                          "U1": 27, "C1": 53})
        for variant in result["variants"]:
            for entry in variant["needed"]:
                self.assertNotIn("order_qty", entry)
                self.assertEqual(entry["order_qty_status"], "待查")


if __name__ == "__main__":
    unittest.main()
