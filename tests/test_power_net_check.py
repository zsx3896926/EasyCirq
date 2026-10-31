"""电源网络检查：它必须能分辨"有电源"和"没有电源"两块板。

判据的由来：2026-10-31 一块板通过全部 15 项 KPI（必查 11/11、可以下单），
但 U1.8 / R1.1 / R2.1 / C1.1 全接在 GND 上——整块板没有电源。
这组用例把那次事故固化成回归。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_power_net_check.py"


def run_check(tmp_path, components):
    listing = {"components": components}
    path = tmp_path / "list.json"
    path.write_text(json.dumps(listing, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--list", str(path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, json.loads(proc.stdout)


def part(designator, pins):
    return {
        "designator": designator,
        "pins": [
            {"pinNumber": number, "pinName": name, "net": net}
            for number, name, net in pins
        ],
    }


def test_power_on_ground_is_blocking(tmp_path):
    """事故复现：电源脚接到 GND，整块板没有电源。"""
    code, result = run_check(tmp_path, [
        part("U1", [("8", "VDD", "GND"), ("4", "GND", "GND")]),
        part("R1", [("1", "1", "GND"), ("2", "2", "NTC_MID")]),
    ])
    assert code == 1
    assert result["status"] == "fail"
    codes = {finding["code"] for finding in result["findings"]}
    assert "POWER_ON_GROUND" in codes
    assert result["metrics"]["power_net_conflicts"] >= 1


def test_healthy_supply_passes(tmp_path):
    code, result = run_check(tmp_path, [
        part("U1", [("8", "VDD", "PWR5V"), ("4", "GND", "GND")]),
        part("R1", [("1", "1", "PWR5V"), ("2", "2", "NTC_MID")]),
    ])
    assert code == 0
    assert result["status"] == "pass"
    assert result["nets"] == ["PWR5V"]


def test_split_supply_is_blocking(tmp_path):
    """一半电源脚在 PWR5V、一半在别处，也是错的。"""
    code, result = run_check(tmp_path, [
        part("U1", [("8", "VDD", "PWR5V")]),
        part("U2", [("8", "VCC", "PWR3V3")]),
    ])
    assert code == 1
    assert "POWER_SPLIT" in {f["code"] for f in result["findings"]}


def test_floating_power_pin_is_blocking(tmp_path):
    code, result = run_check(tmp_path, [
        part("U1", [("8", "VDD", "")]),
    ])
    assert code == 1
    assert "POWER_PIN_FLOATING" in {f["code"] for f in result["findings"]}


def test_passive_board_is_not_applicable(tmp_path):
    """纯无源网络没有电源脚：不适用，不是失败。"""
    code, result = run_check(tmp_path, [
        part("R1", [("1", "1", "A"), ("2", "2", "B")]),
    ])
    assert code == 0
    assert result["status"] == "n/a"


def test_missing_list_file_is_unavailable():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--list", "/nonexistent/list.json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["status"] == "unavailable"
