"""声明式电源网络检查：不靠引脚名，靠计划里的声明。

盲区背景：KPI 16 原先只靠 pinName（VCC/VDD/…）识别电源脚。符号用通用引脚名
（"1"/"2"）时它返回 n/a，和真正没有电源脚的纯无源板输出一样——两个完全不同的
风险共用一个结论。

现在计划可以声明 `power_nets`，检查改为按名字核对：声明了就必须真的存在于图上。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_power_net_check.py"


def run(tmp_path, components, plan=None):
    listing = {"components": components}
    list_path = tmp_path / "list.json"
    list_path.write_text(json.dumps(listing, ensure_ascii=False), encoding="utf-8")
    cmd = [sys.executable, str(SCRIPT), "--list", str(list_path)]
    if plan is not None:
        plan_path = tmp_path / "pinplan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        cmd += ["--plan", str(plan_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, json.loads(proc.stdout)


def generic_part(designator, net_by_pin):
    """A symbol whose pins are named 1/2 - invisible to the pin-name heuristic."""
    return {
        "designator": designator,
        "pins": [
            {"pinNumber": number, "pinName": number, "net": net}
            for number, net in net_by_pin.items()
        ],
    }


def test_declared_net_missing_is_blocking(tmp_path):
    """通用引脚名 + 电源接错：靠声明才抓得到。"""
    components = [generic_part("U1", {"1": "GND", "2": "NTC_MID"}),
                  generic_part("R1", {"1": "GND", "2": "NTC_MID"})]
    code, result = run(tmp_path, components, {"power_nets": ["PWR5V"]})
    assert code == 1
    assert result["status"] == "fail"
    assert result["source"] == "declared"
    assert "POWER_NET_DECLARED_MISSING" in {f["code"] for f in result["findings"]}


def test_declared_net_present_passes_even_with_generic_pins(tmp_path):
    components = [generic_part("U1", {"1": "PWR5V", "2": "GND"}),
                  generic_part("R1", {"1": "PWR5V", "2": "NTC_MID"})]
    code, result = run(tmp_path, components, {"power_nets": ["PWR5V"]})
    assert code == 0
    assert result["status"] == "pass"
    assert result["source"] == "declared"


def test_declaring_ground_as_supply_is_blocking(tmp_path):
    components = [generic_part("U1", {"1": "GND"})]
    code, result = run(tmp_path, components, {"power_nets": ["GND"]})
    assert code == 1
    assert "POWER_ON_GROUND" in {f["code"] for f in result["findings"]}


def test_declared_but_undistributed_warns(tmp_path):
    components = [generic_part("U1", {"1": "PWR5V"})]
    code, result = run(tmp_path, components, {"power_nets": ["PWR5V"]})
    assert code == 0  # warning only
    assert "POWER_NET_UNDISTRIBUTED" in {f["code"] for f in result["findings"]}


def test_without_declaration_falls_back_to_pin_names(tmp_path):
    components = [generic_part("U1", {"1": "GND"})]
    code, result = run(tmp_path, components)
    assert code == 0
    assert result["status"] == "n/a"
    assert result["source"] == "pin-name"


def test_unreadable_plan_is_unavailable(tmp_path):
    list_path = tmp_path / "list.json"
    list_path.write_text('{"components": []}', encoding="utf-8")
    bad = tmp_path / "pinplan.json"
    bad.write_text("{not json", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--list", str(list_path), "--plan", str(bad)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["status"] == "unavailable"
