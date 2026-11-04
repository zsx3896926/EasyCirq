"""BOM 与原理图一致检查的自测。

用真实的旧 BOM 做回归样本：那份 BOM 缺 Q1/R4、多 D1/R11，
正是它让"按 BOM 配单做出来的板子永远不响"这件事差点发生在客户身上。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_bom_match.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sch_bom_match", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sch_bom_match"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


def write_schematic(path: Path, designators):
    import json

    payload = {
        "ok": True,
        "result": {
            "components": [
                {"designator": d, "componentType": "part", "x": 0, "y": 0}
                for d in designators
            ]
            + [{"designator": "", "componentType": "sheet_frame"}],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_bom(path: Path, rows, delimiter="\t"):
    import csv

    header = ["No.", "Quantity", "Comment", "Designator", "Footprint", "Value"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(header)
        for index, (comment, designators) in enumerate(rows, 1):
            writer.writerow([str(index), "1", comment, designators, "FP", ""])
    return path


def test_matching_bom_passes(module, tmp_path):
    sch = write_schematic(tmp_path / "list.json", ["U1", "Q1", "R4"])
    bom = write_bom(tmp_path / "bom.csv", [("LM393", "U1"), ("S8050", "Q1"), ("10k", "R4")])
    result = module.compare(module.schematic_designators(module.read_json(sch)),
                            module.bom_designators(bom))
    assert result["ok"], result


def test_missing_part_is_reported(module, tmp_path):
    sch = write_schematic(tmp_path / "list.json", ["U1", "Q1", "R4"])
    bom = write_bom(tmp_path / "bom.csv", [("LM393", "U1"), ("10k", "R4")])
    result = module.compare(module.schematic_designators(module.read_json(sch)),
                            module.bom_designators(bom))
    assert not result["ok"]
    assert result["missing_from_bom"] == ["Q1"]


def test_phantom_designator_is_reported(module, tmp_path):
    """旧 BOM 里的 D1 / R11 已经不存在了。"""
    sch = write_schematic(tmp_path / "list.json", ["U1", "Q1"])
    bom = write_bom(tmp_path / "bom.csv", [("LM393", "U1"), ("S8050", "Q1"), ("LED", "D1"), ("10k", "R11")])
    result = module.compare(module.schematic_designators(module.read_json(sch)),
                            module.bom_designators(bom))
    assert not result["ok"]
    assert result["not_in_schematic"] == ["D1", "R11"]


def test_comma_separated_bom_is_read(module, tmp_path):
    sch = write_schematic(tmp_path / "list.json", ["R1", "R2"])
    bom = write_bom(tmp_path / "bom.csv", [("10k", "R1,R2")], delimiter=",")
    assert module.bom_designators(bom) == {"R1", "R2"}


def test_sheet_frame_is_ignored(module, tmp_path):
    """图框不是器件，不该被要求出现在 BOM 里。"""
    sch = write_schematic(tmp_path / "list.json", ["U1"])
    assert module.schematic_designators(module.read_json(sch)) == {"U1"}


def test_xlsx_is_refused_with_an_explanation(module, tmp_path):
    bom = tmp_path / "bom.xlsx"
    bom.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    with pytest.raises(ValueError) as excinfo:
        module.bom_designators(bom)
    assert "xlsx" in str(excinfo.value)


def test_exit_code_two_when_mismatched(module, tmp_path):
    sch = write_schematic(tmp_path / "list.json", ["U1", "Q1"])
    bom = write_bom(tmp_path / "bom.csv", [("LM393", "U1")])
    assert module.main(["--schematic", str(sch), "--bom", str(bom)]) == 2


def test_exit_code_zero_when_matched(module, tmp_path):
    sch = write_schematic(tmp_path / "list.json", ["U1"])
    bom = write_bom(tmp_path / "bom.csv", [("LM393", "U1")])
    assert module.main(["--schematic", str(sch), "--bom", str(bom)]) == 0
