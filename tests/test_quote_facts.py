"""报价参数计算的自测。

这个工具的立场是「不给价格，只给驱动价格的板子属性」——所以测试既要证明
各项算得对，也要证明它**不会**凭空给出 price。
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "quote_facts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("quote_facts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["quote_facts"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


def write_pcb(path: Path, width_mil=1000, height_mil=800, layers=2, top=3, bottom=0):
    payload = {
        "ok": True,
        "result": {
            "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": width_mil, "maxY": height_mil},
                        "source": "polygon"},
            "copperLayers": layers,
            "components": [{"designator": f"T{i}", "layer": 1} for i in range(top)]
                          + [{"designator": f"B{i}", "layer": 2} for i in range(bottom)],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_bom(path: Path, rows, delimiter="\t"):
    import csv

    header = ["No.", "Quantity", "Comment", "Designator", "Footprint", "Value", "Supplier Part"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(header)
        for index, (qty, designator, footprint, part) in enumerate(rows, 1):
            writer.writerow([str(index), str(qty), "x", designator, footprint, "", part])
    return path


def test_area_is_computed_from_the_outline(module, tmp_path):
    pcb = write_pcb(tmp_path / "b.json", width_mil=1000, height_mil=800)
    facts = module.board_facts(module.read_json(pcb))
    # 1000 mil = 25.4 mm, 800 mil = 20.32 mm
    assert facts["width_mm"] == pytest.approx(25.4, abs=0.01)
    assert facts["height_mm"] == pytest.approx(20.32, abs=0.01)
    assert facts["area_cm2"] == pytest.approx(5.16, abs=0.02)


def test_top_and_bottom_are_counted(module, tmp_path):
    pcb = write_pcb(tmp_path / "b.json", top=4, bottom=2)
    facts = module.board_facts(module.read_json(pcb))
    assert facts["components_top"] == 4
    assert facts["components_bottom"] == 2


def test_through_hole_placements_are_separated(module, tmp_path):
    bom = write_bom(tmp_path / "bom.csv", [
        (4, "R1,R2,R3,R4", "R0603", "C25804"),
        (1, "NTC1", "RES-TH_BD2.8", "C9900004021"),
    ])
    facts = module.bom_facts(bom)
    assert facts["smt_placements"] == 4
    assert facts["tht_placements"] == 1
    assert facts["drilling_required"] is True


def test_no_through_hole_means_no_drilling(module, tmp_path):
    bom = write_bom(tmp_path / "bom.csv", [(2, "C1,C2", "C0603", "C1")])
    facts = module.bom_facts(bom)
    assert facts["drilling_required"] is False


def test_missing_part_number_is_noted(module, tmp_path):
    pcb = write_pcb(tmp_path / "b.json")
    bom = write_bom(tmp_path / "bom.csv", [
        (1, "U1", "SOP-8", "C504553"),
        (1, "U2", "SOP-8", ""),          # no part number
    ])
    result = module.combine(module.board_facts(module.read_json(pcb)), module.bom_facts(bom))
    assert result["bom"]["line_items_with_part_number"] == 1
    assert any("没有供应商编号" in note for note in result["notes"])


def test_all_parts_on_top_is_noted(module, tmp_path):
    pcb = write_pcb(tmp_path / "b.json", top=3, bottom=0)
    bom = write_bom(tmp_path / "bom.csv", [(3, "R1,R2,R3", "R0603", "C1")])
    result = module.combine(module.board_facts(module.read_json(pcb)), module.bom_facts(bom))
    assert any("全在顶层" in note for note in result["notes"])


def test_price_is_never_invented(module, tmp_path):
    """核心立场：没有询价就不给数字。"""
    pcb = write_pcb(tmp_path / "b.json")
    bom = write_bom(tmp_path / "bom.csv", [(1, "U1", "SOP-8", "C504553")])
    result = module.combine(module.board_facts(module.read_json(pcb)), module.bom_facts(bom))
    assert result["price"] is None
    assert result["leadtime"] is None
    assert result["price_status"] == "NOT RUN"
    assert result["leadtime_status"] == "NOT RUN"


def test_xlsx_bom_is_refused(module, tmp_path):
    bom = tmp_path / "bom.xlsx"
    bom.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    with pytest.raises(ValueError) as excinfo:
        module.bom_facts(bom)
    assert "xlsx" in str(excinfo.value)


def test_exit_code_three_when_input_is_unreadable(module, tmp_path):
    pcb = tmp_path / "missing.json"
    bom = write_bom(tmp_path / "bom.csv", [(1, "U1", "SOP-8", "C1")])
    assert module.main(["--pcb", str(pcb), "--bom", str(bom)]) == 3


def test_exit_code_zero_on_real_shapes(module, tmp_path):
    pcb = write_pcb(tmp_path / "b.json")
    bom = write_bom(tmp_path / "bom.csv", [(1, "U1", "SOP-8", "C1")])
    assert module.main(["--pcb", str(pcb), "--bom", str(bom), "--json"]) == 0
