"""原理图 ↔ PCB 网表一致性：改完原理图没重导网表，必须能被发现。"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_pcb_net_match.py"


def run(tmp_path, schematic, board):
    sch_path = tmp_path / "list.json"
    pcb_path = tmp_path / "pcb.json"
    sch_path.write_text(json.dumps(schematic, ensure_ascii=False), encoding="utf-8")
    pcb_path.write_text(json.dumps(board, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--schematic", str(sch_path), "--pcb", str(pcb_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, json.loads(proc.stdout)


def sch_part(ref, pins):
    return {"designator": ref,
            "pins": [{"pinNumber": n, "net": net} for n, net in pins]}


def pcb_part(ref, pads):
    return {"designator": ref,
            "pads": [{"padNumber": n, "net": net} for n, net in pads]}


def test_matching_netlists_pass(tmp_path):
    schematic = {"components": [sch_part("U1", [("8", "PWR5V"), ("4", "GND")])]}
    board = {"components": [pcb_part("U1", [("8", "PWR5V"), ("4", "GND")])]}
    code, result = run(tmp_path, schematic, board)
    assert code == 0
    assert result["status"] == "pass"


def test_stale_board_is_caught(tmp_path):
    """原理图改了电源，板上还是旧的 GND —— 这是本次事故的形态。"""
    schematic = {"components": [sch_part("R1", [("1", "PWR5V"), ("2", "NTC_MID")])]}
    board = {"components": [pcb_part("R1", [("1", "GND"), ("2", "NTC_MID")])]}
    code, result = run(tmp_path, schematic, board)
    assert code == 1
    assert result["status"] == "fail"
    codes = {f["code"] for f in result["findings"]}
    assert "PIN_NET_MISMATCH" in codes


def test_part_only_on_board_is_caught(tmp_path):
    schematic = {"components": [sch_part("U1", [("1", "A")])]}
    board = {"components": [pcb_part("U1", [("1", "A")]), pcb_part("Q1", [("1", "B")])]}
    code, result = run(tmp_path, schematic, board)
    assert code == 1
    assert "PART_MISSING_IN_SCHEMATIC" in {f["code"] for f in result["findings"]}


def test_part_only_on_schematic_is_caught(tmp_path):
    schematic = {"components": [sch_part("U1", [("1", "A")]), sch_part("Q1", [("1", "B")])]}
    board = {"components": [pcb_part("U1", [("1", "A")])]}
    code, result = run(tmp_path, schematic, board)
    assert code == 1
    assert "PART_MISSING_ON_BOARD" in {f["code"] for f in result["findings"]}


def test_unnamed_primitives_are_ignored(tmp_path):
    """图形/文字对象没有 designator，不能算成"板上少了一个器件"。"""
    schematic = {"components": [
        {"designator": None, "pins": [{"pinNumber": "1", "net": "X"}]},
        sch_part("U1", [("1", "A")]),
    ]}
    board = {"components": [pcb_part("U1", [("1", "A")])]}
    code, result = run(tmp_path, schematic, board)
    assert code == 0, result["findings"]
    assert result["partsOnSchematic"] == 1


def test_pad_numbers_absent_falls_back_to_net_multiset(tmp_path):
    schematic = {"components": [sch_part("U1", [("1", "PWR5V"), ("2", "GND")])]}
    board = {"components": [{"designator": "U1", "pads": [
        {"net": "PWR5V"}, {"net": "GND"}]}]}
    code, result = run(tmp_path, schematic, board)
    assert code == 0


def test_pad_net_difference_without_pad_numbers_is_caught(tmp_path):
    schematic = {"components": [sch_part("U1", [("1", "PWR5V"), ("2", "GND")])]}
    board = {"components": [{"designator": "U1", "pads": [
        {"net": "GND"}, {"net": "GND"}]}]}
    code, result = run(tmp_path, schematic, board)
    assert code == 1


def test_missing_input_is_unavailable(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--schematic", str(tmp_path / "nope.json"),
         "--pcb", str(tmp_path / "nope2.json")],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["status"] == "unavailable"
