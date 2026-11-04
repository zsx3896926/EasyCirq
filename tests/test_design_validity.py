"""设计有效性检查的测试。

这些测试要证明的不是"脚本能跑"，而是**它能抓到当初靠人读电路才发现的那三个缺陷**：

  1. 阈值分压算出的动作温度 25°C，而目标是 60°C
  2. 三极管基极没有直流通路 → 蜂鸣器永远不响
  3. 比较器没有正反馈 → 做不到要求的回差

并且要证明它**不是橡皮图章**：故意改错一个阻值，必须从 pass 变成 fail。
"""
from __future__ import annotations

import json
import re
import pathlib
import subprocess
import tempfile
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_design_validity.py"
BEFORE = ROOT / "tests" / "fixtures" / "design-before-fixes" / "list.json"
AFTER = ROOT / "deliverables" / "alarm" / "design" / "snapshot" / "list.json"
INTENT = ROOT / "deliverables" / "alarm" / "design" / "intent.json"


def run(netlist, intent=INTENT, out=None):
    args = [sys.executable, str(SCRIPT), "--netlist", str(netlist)]
    if intent is not None:
        args += ["--intent", str(intent)]
    if out is not None:
        args += ["--out", str(out)]
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def check_status(stdout: str, check_id: str) -> str:
    """从检查器的文本输出里取某一项的状态。

    不要用 assertIn("inductive_load    pass") 这种写法——列宽是 <18 补空格，
    不同长度的 id 空格数不同（threshold_sanity 16 字符 → 3 个空格，
    inductive_load 14 字符 → 5 个空格）。按行解析才不脆。
    """
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == check_id:
            return parts[1]
    raise AssertionError(f"输出里找不到 {check_id} 的状态行")


class BeforeFixesTests(unittest.TestCase):
    """修之前的快照：三个缺陷必须都被指出来。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(__file__).parent / "_dv_before.json"
        cls.proc = run(BEFORE, out=cls.tmp)
        cls.report = load(cls.tmp) if cls.tmp.is_file() else {}

    @classmethod
    def tearDownClass(cls):
        if cls.tmp.is_file():
            cls.tmp.unlink()

    def test_exit_code_is_fail(self):
        self.assertEqual(self.proc.returncode, 1, self.proc.stderr[-800:])
        self.assertEqual(self.report.get("verdict"), "fail")

    def test_threshold_defect_is_named(self):
        codes = {f["code"] for f in self.report.get("findings") or []}
        self.assertIn("THRESHOLD_OUT_OF_TARGET", codes)
        check = next(c for c in self.report["checks"]
                     if c["id"] == "threshold_sanity")
        metrics = check["metrics"]
        # 当初人算出来就是 25.0°C，不是 60°C
        self.assertAlmostEqual(metrics["trip_c"], 25.0, delta=0.5)
        self.assertAlmostEqual(metrics["threshold_v"], 2.5, delta=0.01)
        self.assertEqual(metrics["divider"], "R2/R3")
        self.assertLess(metrics["delta_c"], -30)

    def test_base_drive_defect_is_named(self):
        codes = {f["code"] for f in self.report.get("findings") or []}
        self.assertIn("NO_DC_BIAS_PATH", codes)
        finding = next(f for f in self.report["findings"]
                       if f["code"] == "NO_DC_BIAS_PATH")
        self.assertEqual(finding["part"], "Q1")
        self.assertEqual(finding["net"], "BASE")

    def test_hysteresis_defect_is_named(self):
        codes = {f["code"] for f in self.report.get("findings") or []}
        self.assertIn("NO_HYSTERESIS", codes)


class AfterFixesTests(unittest.TestCase):
    """修之后的快照：三项都必须通过。

    这一组曾经断言"回差仍然 fail，因为确实没加"。2026-11-01 加上 R6（22kΩ，
    从 ALARM 正反馈到 NTC_MID，算出回差 3.23°C）之后，回差这一项也转了绿。
    断言跟着实际行为走，而不是跟着"当初没修"的旧状态走。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(__file__).parent / "_dv_after.json"
        cls.proc = run(AFTER, out=cls.tmp)
        cls.report = load(cls.tmp) if cls.tmp.is_file() else {}
        cls.checks = {c["id"]: c for c in cls.report.get("checks") or []}

    @classmethod
    def tearDownClass(cls):
        if cls.tmp.is_file():
            cls.tmp.unlink()

    def test_threshold_passes(self):
        self.assertEqual(self.checks["threshold_sanity"]["status"], "pass")
        metrics = self.checks["threshold_sanity"]["metrics"]
        # R3 改成 2.4k 之后算出来是 61°C
        self.assertAlmostEqual(metrics["trip_c"], 61.0, delta=1.0)
        self.assertLessEqual(abs(metrics["delta_c"]), 5)

    def test_drive_passes_with_r5(self):
        check = self.checks["switch_drive"]
        self.assertEqual(check["status"], "pass")
        switch = check["switches"][0]
        self.assertEqual(switch["part"], "Q1")
        self.assertEqual(switch["pullup"], "R5")
        # 0.425mA 基极电流 × 120 ≈ 51mA，够 30mA 蜂鸣器
        self.assertGreater(switch["base_ma"], 0.3)
        self.assertGreater(switch["ic_ma"], 30)

    def test_hysteresis_passes_with_r6(self):
        # R6 = 22k 从 ALARM 反馈到 NTC_MID，构成正反馈
        check = self.checks["hysteresis"]
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["metrics"]["feedback_parts"], ["R6"])
        self.assertEqual(self.report.get("verdict"), "pass")

    def test_all_applicable_checks_pass(self):
        # 报警板上没有电感负载，所以 inductive_load 是 not_run（不适用）——
        # 它不该把整体判定拖成 unknown。这里同时把这条约束钉住。
        statuses = {c["id"]: c["status"] for c in self.report["checks"]}
        self.assertEqual(statuses, {"threshold_sanity": "pass",
                                    "switch_drive": "pass",
                                    "hysteresis": "pass",
                                    "inductive_load": "not_run",
                                    "supply_domains": "not_run",
                                    # 报警板意图没声明 vds_max / ratings[]，
                                    # 没有额定值可比 → not_run，不拖累整体
                                    "ratings": "not_run"})
        self.assertEqual(self.report["verdict"], "pass")


class NegativeTests(unittest.TestCase):
    """故意改坏：pass 必须变成 fail。这是"不是橡皮图章"的证明。"""

    def setUp(self):
        self.tmpdir = pathlib.Path(__file__).parent / "_dv_neg"
        self.tmpdir.mkdir(exist_ok=True)

    def tearDown(self):
        for path in self.tmpdir.glob("*"):
            path.unlink()
        self.tmpdir.rmdir()

    def _mutate(self, designator, new_value):
        data = load(AFTER)
        hit = False
        for comp in data.get("components") or []:
            if comp.get("designator") == designator:
                comp.setdefault("otherProperty", {})["Value"] = new_value
                hit = True
        self.assertTrue(hit, f"网表里没有 {designator}")
        target = self.tmpdir / "mutated.json"
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return target

    def test_wrong_r3_turns_threshold_red(self):
        # R3 改回 10k（就是当初的缺陷），阈值必须重新报 fail
        mutated = self._mutate("R3", "10kΩ")
        proc = run(mutated)
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])
        self.assertIn("THRESHOLD_OUT_OF_TARGET", proc.stdout)
        self.assertIn("25.0", proc.stdout)

    def test_missing_pullup_turns_drive_red(self):
        # 把 R5 的阻值抹掉，等于它不再是上拉 → 驱动必须报 fail
        mutated = self._mutate("R5", "")
        proc = run(mutated)
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])
        self.assertIn("NO_DC_BIAS_PATH", proc.stdout)

    def test_removing_r6_turns_hysteresis_red(self):
        """把 R6 从网表里删掉，回差必须重新报 fail。

        这条是"检查器不是橡皮图章"的第三个证据：不是只有初始缺陷会红，
        修好之后再破坏它，同样会红。
        """
        data = load(AFTER)
        before = len(data.get("components") or [])
        data["components"] = [c for c in data.get("components") or []
                              if c.get("designator") != "R6"]
        self.assertEqual(len(data["components"]), before - 1)
        target = self.tmpdir / "no-r6.json"
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        proc = run(target)
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])
        self.assertIn("NO_HYSTERESIS", proc.stdout)

    def test_drive_insufficient_is_reported(self):
        # R5 换成 1M：基极电流只有 4µA，带不动 30mA 蜂鸣器
        mutated = self._mutate("R5", "1M")
        proc = run(mutated)
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])
        self.assertIn("DRIVE_INSUFFICIENT", proc.stdout)


class TransistorKindTests(unittest.TestCase):
    """BJT 和 MOSFET 不能用同一个模型判。

    2026-11-01 做 12V 风扇板时撞到：检查器只懂 BJT，把 MOSFET 也拿去乘 hFE，
    于是 100k 的栅极上拉被判成"带不动 200mA"——**假失败**。反过来，
    一颗真 BJT 配 100k 上拉确实是带不动的，那种情况必须仍然报 fail。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-kind-"))
        base = ["NTC1", "R1", "U1", "R2", "R3"]
        parts = [
            {"designator": "NTC1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "NTC/10K",
             "pins": [{"pinNumber": "1", "pinName": "1", "net": "NTC_MID"},
                      {"pinNumber": "2", "pinName": "2", "net": "GND"}]},
            {"designator": "R1", "componentType": "part", "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "NTC_MID"}]},
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "GATE"}, {"pinNumber": "2", "net": "TH"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R2", "componentType": "part", "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH"}]},
            {"designator": "R3", "componentType": "part", "otherProperty": {"Value": "4.3kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH"}, {"pinNumber": "2", "net": "GND"}]},
        ]
        # 栅极/基极上拉 100k：对 MOSFET 合理，对 BJT 远远不够
        pullup = {"designator": "R5", "componentType": "part",
                  "otherProperty": {"Value": "100kΩ"},
                  "pins": [{"pinNumber": "1", "net": "PWR5V"},
                           {"pinNumber": "2", "net": "GATE"}]}
        cls.mosfet = {"designator": "Q1", "componentType": "part",
                      "manufacturerId": "AO3400", "otherProperty": {},
                      "pins": [{"pinNumber": "1", "pinName": "G", "net": "GATE"},
                               {"pinNumber": "2", "pinName": "S", "net": "GND"},
                               {"pinNumber": "3", "pinName": "D", "net": "FAN_M"}]}
        cls.bjt = {"designator": "Q1", "componentType": "part",
                   "manufacturerId": "S8050", "otherProperty": {},
                   "pins": [{"pinNumber": "1", "pinName": "B", "net": "GATE"},
                            {"pinNumber": "2", "pinName": "E", "net": "GND"},
                            {"pinNumber": "3", "pinName": "C", "net": "FAN_M"}]}
        cls.base = parts + [pullup]

        cls.intent = {
            "schema": "easycirq-design-intent/v1",
            "power_rail": "PWR5V", "ground": "GND",
            "threshold": {"comparator": "U1", "target_c": 45, "tolerance_c": 3,
                          "vcc": 5.0,
                          "sensor": {"kind": "ntc", "r25": 10000, "b": 3950}},
            "switches": [{"part": "Q1", "load": "FAN", "load_ma": 200,
                          "vgs_th": 1.5, "id_max_a": 4.0}],
        }

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _run(self, switch_part, intent_patch=None):
        data = {"components": self.base + [switch_part]}
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        intent = json.loads(json.dumps(self.intent))
        if intent_patch:
            intent["switches"][0].update(intent_patch)
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        return proc

    def test_mosfet_with_100k_gate_pullup_passes(self):
        # 栅极静态不取电流，100k 上拉完全够——不能被 hFE 模型判死。
        # 断言盯 switch_drive 这一项，而不是整体退出码：意图里没声明回差时
        # 整体 verdict 会是 unknown（这是有意的诚实行为，不是失败）。
        proc = self._run(self.mosfet)
        self.assertEqual(check_status(proc.stdout, "switch_drive"), "pass")
        self.assertIn('"kind": "mosfet"', proc.stdout)
        self.assertIn("静态不取电流", proc.stdout)
        self.assertNotIn("DRIVE_INSUFFICIENT", proc.stdout)

    def test_bjt_with_100k_base_pullup_fails(self):
        # 同样的 100k，换成一个真要基极电流的 BJT，必须报驱动不足
        proc = self._run(self.bjt)
        self.assertIn("DRIVE_INSUFFICIENT", proc.stdout)
        self.assertIn('"kind": "bjt"', proc.stdout)
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])

    def test_mosfet_without_gate_path_fails(self):
        data = self.base + [self.mosfet]
        data = [c for c in data if c["designator"] != "R5"]   # 去掉栅极上拉
        netlist = self.tmp / "nopath.json"
        netlist.write_text(json.dumps({"components": data}, ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "i.json"
        intent_path.write_text(json.dumps(self.intent, ensure_ascii=False),
                               encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])
        self.assertIn("NO_GATE_PATH", proc.stdout)

    def test_mosfet_load_beyond_rating_fails(self):
        proc = self._run(self.mosfet, {"load_ma": 9000, "id_max_a": 4.0})
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])
        self.assertIn("LOAD_EXCEEDS_RATING", proc.stdout)


class InductiveLoadTests(unittest.TestCase):
    """感性负载必须有续流二极管，且方向要对。

    这是风扇板探针暴露的第四类判据：18+1 项门禁里没有一条会查它，
    而缺二极管的后果是开关管被反电动势击穿。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-ind-"))
        cls.base = [
            {"designator": "NTC1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "NTC/10K",
             "pins": [{"pinNumber": "1", "pinName": "1", "net": "NTC_MID"},
                      {"pinNumber": "2", "pinName": "2", "net": "GND"}]},
            {"designator": "R1", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "NTC_MID"}]},
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "GATE"}, {"pinNumber": "2", "net": "TH"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R2", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH"}]},
            {"designator": "R3", "componentType": "part",
             "otherProperty": {"Value": "4.3kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH"}, {"pinNumber": "2", "net": "GND"}]},
            {"designator": "R5", "componentType": "part",
             "otherProperty": {"Value": "100kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "GATE"}]},
            {"designator": "Q1", "componentType": "part", "manufacturerId": "AO3400",
             "otherProperty": {},
             "pins": [{"pinNumber": "1", "pinName": "G", "net": "GATE"},
                      {"pinNumber": "2", "pinName": "S", "net": "GND"},
                      {"pinNumber": "3", "pinName": "D", "net": "FAN_M"}]},
            # 风扇：一端接 12V，一端接漏极
            {"designator": "FAN1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "FAN-12V",
             "pins": [{"pinNumber": "1", "pinName": "+", "net": "PWR12V"},
                      {"pinNumber": "2", "pinName": "-", "net": "FAN_M"}]},
        ]
        cls.intent = {
            "schema": "easycirq-design-intent/v1",
            "power_rail": "PWR5V", "load_rail": "PWR12V", "ground": "GND",
            "switches": [{"part": "Q1", "load": "FAN1", "load_ma": 200,
                          "kind": "mosfet", "vgs_th": 1.05, "id_max_a": 4.0,
                          "load_kind": "inductive"}],
        }

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _diode(self, anode_net, cathode_net, designator="D1"):
        return {"designator": designator, "componentType": "part",
                "manufacturerId": "1N4148", "otherProperty": {},
                "pins": [{"pinNumber": "1", "pinName": "A", "net": anode_net},
                         {"pinNumber": "2", "pinName": "K", "net": cathode_net}]}

    def _run(self, extra):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps({"components": self.base + extra},
                                      ensure_ascii=False), encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(self.intent, ensure_ascii=False),
                               encoding="utf-8")
        return run(netlist, intent=intent_path)

    def test_missing_flywheel_diode_fails(self):
        proc = self._run([])
        self.assertIn("NO_FLYWHEEL_DIODE", proc.stdout)
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])

    def test_correct_flywheel_diode_passes(self):
        # 阳极接开关侧，阴极接 12V
        proc = self._run([self._diode("FAN_M", "PWR12V")])
        self.assertEqual(check_status(proc.stdout, "inductive_load"), "pass")
        self.assertNotIn("NO_FLYWHEEL_DIODE", proc.stdout)
        self.assertNotIn("FLYWHEEL_DIODE_REVERSED", proc.stdout)

    def test_reversed_flywheel_diode_fails(self):
        # 接反了：一上电就正向导通，把 12V 短路
        proc = self._run([self._diode("PWR12V", "FAN_M")])
        self.assertIn("FLYWHEEL_DIODE_REVERSED", proc.stdout)
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])

    def test_non_inductive_load_is_not_run(self):
        intent = json.loads(json.dumps(self.intent))
        intent["switches"][0]["load_kind"] = "resistive"
        intent_path = self.tmp / "i2.json"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
        netlist = self.tmp / "l2.json"
        netlist.write_text(json.dumps({"components": self.base}, ensure_ascii=False),
                           encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        self.assertEqual(check_status(proc.stdout, "inductive_load"), "not_run")
        self.assertNotIn("NO_FLYWHEEL_DIODE", proc.stdout)


class SupplyDomainTests(unittest.TestCase):
    """双电源域：查拓扑，不查器件额定。

    风扇板是 5V 逻辑 + 12V 负载。画图时最常犯的错是看错电源符号：
    风扇漏极接到 5V 上，两端同电位，永远不转。power_net 不会报这个。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-supply-"))

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _parts(self, drain_net="FAN_M", extra_diode=True, ground_tie=True,
               short_resistor=False):
        parts = [
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "GATE"}, {"pinNumber": "8", "net": "PWR5V"},
                      {"pinNumber": "4", "net": "GND"}]},
            {"designator": "R5", "componentType": "part",
             "otherProperty": {"Value": "100kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "GATE"}]},
            {"designator": "Q1", "componentType": "part", "manufacturerId": "AO3400",
             "otherProperty": {},
             "pins": [{"pinNumber": "1", "pinName": "G", "net": "GATE"},
                      {"pinNumber": "2", "pinName": "S", "net": "GND"},
                      {"pinNumber": "3", "pinName": "D", "net": drain_net}]},
            {"designator": "FAN1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "FAN-12V",
             "pins": [{"pinNumber": "1", "pinName": "+", "net": "PWR12V"},
                      {"pinNumber": "2", "pinName": "-", "net": "FAN_M"}]},
        ]
        if extra_diode:
            parts.append({"designator": "D1", "componentType": "part",
                          "manufacturerId": "1N4148", "otherProperty": {},
                          "pins": [{"pinNumber": "1", "pinName": "A", "net": "FAN_M"},
                                   {"pinNumber": "2", "pinName": "K", "net": "PWR12V"}]})
        if short_resistor:
            parts.append({"designator": "R9", "componentType": "part",
                          "otherProperty": {"Value": "0Ω"},
                          "pins": [{"pinNumber": "1", "net": "PWR5V"},
                                   {"pinNumber": "2", "net": "PWR12V"}]})
        if ground_tie:
            parts.append({"designator": "R10", "componentType": "part",
                          "otherProperty": {"Value": "0Ω"},
                          "pins": [{"pinNumber": "1", "net": "GND"},
                                   {"pinNumber": "2", "net": "PGND"}]})
        return parts

    def _intent(self, grounds=None):
        return {
            "schema": "easycirq-design-intent/v1",
            "power_rail": "PWR5V", "load_rail": "PWR12V", "ground": "GND",
            "rails": {"PWR5V": 5.0, "PWR12V": 12.0},
            "grounds": grounds or ["GND"],
            "switches": [{"part": "Q1", "load": "FAN1", "load_ma": 200,
                          "kind": "mosfet", "vgs_th": 1.05, "id_max_a": 4.0,
                          "load_kind": "inductive", "load_rail": "PWR12V"}],
        }

    def _run(self, parts, grounds=None):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps({"components": parts}, ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(self._intent(grounds), ensure_ascii=False),
                               encoding="utf-8")
        return run(netlist, intent=intent_path)

    def test_healthy_dual_supply_passes(self):
        proc = self._run(self._parts())
        self.assertEqual(check_status(proc.stdout, "supply_domains"), "pass")
        self.assertNotIn("RAIL_SHORTED", proc.stdout)

    def test_drain_on_logic_rail_fails(self):
        # 风扇漏极接到 5V：两端同电位，永远不转
        proc = self._run(self._parts(drain_net="PWR5V"))
        self.assertIn("SWITCH_LOAD_ON_LOGIC_RAIL", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "supply_domains"), "fail")
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])

    def test_rails_shorted_fails(self):
        proc = self._run(self._parts(short_resistor=True))
        self.assertIn("RAIL_SHORTED", proc.stdout)
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])

    def test_grounds_not_joined_fails(self):
        parts = self._parts(ground_tie=False)
        proc = self._run(parts, grounds=["GND", "PGND"])
        self.assertIn("GROUNDS_DISCONNECTED", proc.stdout)
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])

    def test_grounds_joined_by_zero_ohm_passes(self):
        parts = self._parts(ground_tie=True)
        proc = self._run(parts, grounds=["GND", "PGND"])
        self.assertNotIn("GROUNDS_DISCONNECTED", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "supply_domains"), "pass")

    def test_no_rails_declared_is_not_run(self):
        netlist = self.tmp / "nr.json"
        netlist.write_text(json.dumps({"components": self._parts()},
                                      ensure_ascii=False), encoding="utf-8")
        intent = self._intent()
        intent.pop("rails")
        intent_path = self.tmp / "nr-intent.json"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        self.assertEqual(check_status(proc.stdout, "supply_domains"), "not_run")
        self.assertNotIn("RAIL_SHORTED", proc.stdout)


class MissingDesignatorTests(unittest.TestCase):
    """意图里的位号在网表里不存在时，必须说清网表里有什么。

    2026-11-02 实测：`block-apply` 会重新分配位号（块的角色 LOAD 被分到 J1），
    而意图文件里写的是手工搭板时的 FAN1。判据于是报 unknown ——
    **而 unknown 最容易被当成"没事"略过**，实际是这一项根本没验。

    实测中还有个更隐蔽的问题：诊断信息写对了，但打印器只输出 metrics/switches，
    loads[].reason 被吞掉，屏幕上只剩三个字母的 unknown。这里两条都钉住。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-missing-"))

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _netlist(self):
        # 只有比较器、阈值分压和一颗开关，没有意图里写的 FAN1
        return {"components": [
            {"designator": "NTC1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "NTC/10K",
             "pins": [{"pinNumber": "1", "pinName": "1", "net": "NTC_MID"},
                      {"pinNumber": "2", "pinName": "2", "net": "GND"}]},
            {"designator": "R1", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "NTC_MID"}]},
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "GATE"}, {"pinNumber": "2", "net": "TH"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R2", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH"}]},
            {"designator": "R3", "componentType": "part",
             "otherProperty": {"Value": "4.3kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH"}, {"pinNumber": "2", "net": "GND"}]},
            {"designator": "Q1", "componentType": "part", "manufacturerId": "AO3400",
             "otherProperty": {},
             "pins": [{"pinNumber": "1", "pinName": "G", "net": "GATE"},
                      {"pinNumber": "2", "pinName": "S", "net": "GND"},
                      {"pinNumber": "3", "pinName": "D", "net": "FAN_M"}]},
        ]}

    def _intent(self, load="FAN1"):
        return {
            "schema": "easycirq-design-intent/v1",
            "power_rail": "PWR5V", "load_rail": "PWR12V", "ground": "GND",
            "rails": {"PWR5V": 5.0, "PWR12V": 12.0},
            "threshold": {"comparator": "U1", "target_c": 45, "tolerance_c": 3,
                          "vcc": 5.0,
                          "sensor": {"kind": "ntc", "r25": 10000, "b": 3950}},
            "switches": [{"part": "Q1", "load": load, "load_ma": 200,
                          "kind": "mosfet", "vgs_th": 1.05, "id_max_a": 4.0,
                          "load_kind": "inductive", "load_rail": "PWR12V"}],
        }

    def _run(self, load):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps(self._netlist(), ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(self._intent(load), ensure_ascii=False),
                               encoding="utf-8")
        return run(netlist, intent=intent_path)

    def test_missing_load_designator_lists_what_exists(self):
        proc = self._run("FAN1")
        self.assertIn("inductive_load     unknown", proc.stdout)
        self.assertIn("意图写的是 FAN1", proc.stdout)
        # 必须列出网表里真实的位号，让人一眼对得上
        for designator in ("Q1", "U1", "NTC1"):
            self.assertIn(designator, proc.stdout)
        # 必须点出「块会重排位号」这个成因
        self.assertIn("block-apply", proc.stdout)

    def test_missing_designator_is_visible_in_stdout_not_just_in_json(self):
        """诊断写对了但没打印出来，等于没有。

        实测踩过：reason 写进了 loads[]，打印器只输出 metrics/switches，
        屏幕上只剩 `inductive_load     unknown` 三个字母。
        """
        proc = self._run("FAN1")
        self.assertIn("[unknown] FAN1:", proc.stdout)
        self.assertIn("网表里的器件是", proc.stdout)

    def test_correct_designator_passes(self):
        # 把 load 指到真实存在的位号，判据不该再报 unknown
        netlist = self.tmp / "ok.json"
        data = self._netlist()
        data["components"].append(
            {"designator": "J1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "FAN-12V",
             "pins": [{"pinNumber": "1", "pinName": "+", "net": "PWR12V"},
                      {"pinNumber": "2", "pinName": "-", "net": "FAN_M"}]})
        data["components"].append(
            {"designator": "D1", "componentType": "part",
             "manufacturerId": "1N4148", "otherProperty": {},
             "pins": [{"pinNumber": "1", "pinName": "K", "net": "PWR12V"},
                      {"pinNumber": "2", "pinName": "A", "net": "FAN_M"}]})
        netlist.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        intent_path = self.tmp / "i2.json"
        intent_path.write_text(json.dumps(self._intent("J1"), ensure_ascii=False),
                               encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        self.assertIn("inductive_load     pass", proc.stdout)


class HysteresisWidthTests(unittest.TestCase):
    """回差要算**多少度**，不能只回答"有没有正反馈"。

    目标里点名了这条：「客户明确要求回差：hysteresis 只判有没有正反馈，不算宽度」。
    客户原话是「别在边上疯狂启停」——宽度不够或太大都不行，所以必须算出数值来比。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-hyst-"))

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _parts(self, r_hyst):
        return {"components": [
            {"designator": "NTC1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "NTC/10K",
             "pins": [{"pinNumber": "1", "pinName": "1", "net": "NTC_MID"},
                      {"pinNumber": "2", "pinName": "2", "net": "GND"}]},
            {"designator": "R1", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"},
                      {"pinNumber": "2", "net": "NTC_MID"}]},
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "ALARM"}, {"pinNumber": "2", "net": "TH"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R2", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH"}]},
            {"designator": "R3", "componentType": "part",
             "otherProperty": {"Value": "4.3kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH"}, {"pinNumber": "2", "net": "GND"}]},
            {"designator": "R6", "componentType": "part",
             "otherProperty": {"Value": r_hyst},
             "pins": [{"pinNumber": "1", "net": "ALARM"},
                      {"pinNumber": "2", "net": "NTC_MID"}]},
        ]}

    def _intent(self, with_pull=True):
        spec = {
            "comparator": "U1", "target_c": 45, "tolerance_c": 3, "vcc": 5.0,
            "sensor": {"kind": "ntc", "r25": 10000, "b": 3950},
            "hysteresis_c": 3,
        }
        if with_pull:
            spec["r_pull_ohms"] = 10000
        return {"schema": "easycirq-design-intent/v1", "power_rail": "PWR5V",
                "ground": "GND", "threshold": spec}

    def _run(self, r_hyst, with_pull=True):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps(self._parts(r_hyst), ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(self._intent(with_pull), ensure_ascii=False),
                               encoding="utf-8")
        return run(netlist, intent=intent_path)

    def test_width_is_computed_not_just_presence(self):
        proc = self._run("39kΩ")
        self.assertEqual(check_status(proc.stdout, "hysteresis"), "pass")
        # 必须有具体数值，不能只有 feedback_parts
        self.assertIn('"width_c"', proc.stdout)
        self.assertIn('"trip_c"', proc.stdout)
        self.assertIn('"release_c"', proc.stdout)
        match = re.search(r'"width_c":\s*([0-9.]+)', proc.stdout)
        self.assertIsNotNone(match, "没算出回差宽度")
        width = float(match.group(1))
        # 39k 应该落在 3°C 附近（工具算的是 2.97）
        self.assertGreater(width, 2.0)
        self.assertLess(width, 4.0)

    def test_wrong_hysteresis_resistor_fails(self):
        """故意换一颗差很多的回差电阻 → 必须报宽度不对，而不是"有正反馈就 pass"。"""
        proc = self._run("4.7kΩ")
        self.assertIn("HYSTERESIS_WIDTH_OFF", proc.stdout)
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])

    def test_missing_pull_value_is_unknown_not_pass(self):
        """算宽度需要上拉阻值；没给就如实说判不了，不许默认 pass。"""
        proc = self._run("39kΩ", with_pull=False)
        self.assertEqual(check_status(proc.stdout, "hysteresis"), "unknown")
        self.assertIn("算不出宽度", proc.stdout)


class MultiComparatorTests(unittest.TestCase):
    """一块板上有两个阈值（窗口比较器 / 高低双限）时，两组都要判。

    原来意图里的 `threshold.comparator` 是单个字符串，一块板只能表达一个阈值。
    现在接受 `thresholds: [...]`，缺省仍回落到单个 `threshold` —— 旧文件不用改。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-multi-"))

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _netlist(self):
        # 两个独立的分压 + 两个比较器（都用内置器件表里的 LM393 引脚名）
        parts = [
            {"designator": "NTC1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "NTC/10K",
             "pins": [{"pinNumber": "1", "pinName": "1", "net": "NTC_MID"},
                      {"pinNumber": "2", "pinName": "2", "net": "GND"}]},
            {"designator": "R1", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "NTC_MID"}]},
            # 比较器 A：TH_A = 10k/4.3k → 约 45°C
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "ALARM_A"}, {"pinNumber": "2", "net": "TH_A"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R2", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH_A"}]},
            {"designator": "R3", "componentType": "part",
             "otherProperty": {"Value": "4.3kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH_A"}, {"pinNumber": "2", "net": "GND"}]},
            # 比较器 B：TH_B = 10k/22k → 约 5°C
            {"designator": "U2", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "ALARM_B"}, {"pinNumber": "2", "net": "TH_B"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R4", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH_B"}]},
            {"designator": "R5", "componentType": "part",
             "otherProperty": {"Value": "22kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH_B"}, {"pinNumber": "2", "net": "GND"}]},
        ]
        return {"components": parts}

    def _intent(self, specs):
        return {
            "schema": "easycirq-design-intent/v1",
            "power_rail": "PWR5V", "ground": "GND",
            "thresholds": specs,
        }

    def _run(self, specs):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps(self._netlist(), ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(self._intent(specs), ensure_ascii=False),
                               encoding="utf-8")
        return run(netlist, intent=intent_path)

    def _spec(self, comparator, target_c):
        return {"comparator": comparator, "target_c": target_c, "tolerance_c": 3,
                "vcc": 5.0, "sensor": {"kind": "ntc", "r25": 10000, "b": 3950}}

    def test_two_comparators_both_checked(self):
        # U1 的 10k/4.3k 分压 → 45.3°C；U2 的 10k/22k → 3.4375V → 8.3°C。
        # （第一版我把 U2 的靶温写成 5°C，实测 8.3°C 被判偏 3.3°C —— 那是我的测试写错，
        #   不是判据错。判据算出来的 8.3°C 是对的。）
        proc = self._run([self._spec("U1", 45), self._spec("U2", 8)])
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "pass")
        # 两组都必须出现在输出里，各带自己的分压与算出温度
        self.assertIn("[pass] U1:", proc.stdout)
        self.assertIn("[pass] U2:", proc.stdout)
        self.assertIn("R2/R3", proc.stdout)
        self.assertIn("R4/R5", proc.stdout)
        self.assertIn('"trip_c": 45.3', proc.stdout)
        self.assertIn('"trip_c": 8.3', proc.stdout)

    def test_second_comparator_wrong_target_fails(self):
        """第二组的靶温写错时必须 fail —— 多比较器不能让任何一组蒙混过关。"""
        proc = self._run([self._spec("U1", 45), self._spec("U2", 30)])
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "fail")
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])

    def test_second_comparator_missing_part_is_unknown(self):
        """第二组指向不存在的位号 → unknown，不能因为第一组 pass 就整体 pass。"""
        proc = self._run([self._spec("U1", 45), self._spec("U9", 8)])
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "unknown")

    def test_single_threshold_still_works(self):
        """旧写法 `threshold`（单对象）必须继续工作 —— 34 个既有测试都靠它。"""
        netlist = self.tmp / "one.json"
        netlist.write_text(json.dumps(self._netlist(), ensure_ascii=False),
                           encoding="utf-8")
        intent = {
            "schema": "easycirq-design-intent/v1",
            "power_rail": "PWR5V", "ground": "GND",
            "threshold": self._spec("U1", 45),
        }
        intent_path = self.tmp / "one-intent.json"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "pass")
        # 单比较器不打印逐条明细，保持旧输出形状（34 个既有测试靠这个形状）
        self.assertNotIn("[pass] U1:", proc.stdout)
        self.assertIn('"trip_c": 45.3', proc.stdout)


class RatingStressTests(unittest.TestCase):
    """器件额定电压/功率：意图声明额定值，工具算实际应力。

    数据手册不在网表里，所以"这颗管子 Vds 上限 30V"必须由人声明。
    工具能做的是把**实际会加在它上面的电压**算出来，和声明的额定值比。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-rating-"))

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _netlist(self, extras=None):
        parts = [
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "GATE"}, {"pinNumber": "8", "net": "PWR5V"},
                      {"pinNumber": "4", "net": "GND"}]},
            {"designator": "R5", "componentType": "part",
             "otherProperty": {"Value": "100kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "GATE"}]},
            {"designator": "Q1", "componentType": "part", "manufacturerId": "AO3400",
             "otherProperty": {},
             "pins": [{"pinNumber": "1", "pinName": "G", "net": "GATE"},
                      {"pinNumber": "2", "pinName": "S", "net": "GND"},
                      {"pinNumber": "3", "pinName": "D", "net": "FAN_M"}]},
            {"designator": "FAN1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "FAN-12V",
             "pins": [{"pinNumber": "1", "pinName": "+", "net": "PWR12V"},
                      {"pinNumber": "2", "pinName": "-", "net": "FAN_M"}]},
            {"designator": "D1", "componentType": "part", "manufacturerId": "1N4148",
             "otherProperty": {},
             "pins": [{"pinNumber": "1", "pinName": "K", "net": "PWR12V"},
                      {"pinNumber": "2", "pinName": "A", "net": "FAN_M"}]},
        ]
        return {"components": parts + list(extras or [])}

    def _intent(self, vds_max=None, ratings=None, power_rail_v=5.0,
                power_rail="PWR5V"):
        sw = {"part": "Q1", "load": "FAN1", "load_ma": 200, "kind": "mosfet",
              "vgs_th": 1.05, "id_max_a": 4.0, "load_kind": "inductive",
              "load_rail": "PWR12V"}
        if vds_max is not None:
            sw["vds_max"] = vds_max
        body = {"schema": "easycirq-design-intent/v1", "power_rail": power_rail,
                "load_rail": "PWR12V", "ground": "GND",
                "rails": {power_rail: power_rail_v, "PWR12V": 12.0},
                "grounds": ["GND"], "switches": [sw]}
        if ratings:
            body["ratings"] = ratings
        return body

    def _run(self, intent, extras=None):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps(self._netlist(extras), ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False),
                               encoding="utf-8")
        return run(netlist, intent=intent_path)

    def test_over_voltage_fails(self):
        """12V 轨上装 10V 额定的管子 —— 必须 fail。这是最容易被漏掉的一类错。"""
        proc = self._run(self._intent(vds_max=10))
        self.assertIn("OVER_RATING", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "ratings"), "fail")
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])

    def test_adequate_voltage_passes(self):
        proc = self._run(self._intent(vds_max=30))
        self.assertEqual(check_status(proc.stdout, "ratings"), "pass")
        self.assertIn("实际 12.0V / 额定 30.0V", proc.stdout)

    def test_thin_margin_warns_without_failing(self):
        """12V 配 13V 额定：通过，但必须给出余量不足的提示（不是 fail，也别沉默）。"""
        proc = self._run(self._intent(vds_max=13))
        self.assertEqual(check_status(proc.stdout, "ratings"), "pass")
        self.assertIn("RATING_MARGIN_THIN", proc.stdout)

    def test_capacitor_over_voltage_fails(self):
        cap = {"designator": "C1", "componentType": "part",
               "otherProperty": {"Value": "100nF"},
               "pins": [{"pinNumber": "1", "net": "PWR12V"},
                        {"pinNumber": "2", "net": "GND"}]}
        proc = self._run(self._intent(
            ratings=[{"part": "C1", "between": ["PWR12V", "GND"], "max_v": 10}]),
            extras=[cap])
        self.assertIn("OVER_RATING", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "ratings"), "fail")

    def test_resistor_power_over_fails(self):
        res = {"designator": "R9", "componentType": "part",
               "otherProperty": {"Value": "1kΩ"},
               "pins": [{"pinNumber": "1", "net": "PWR12V"},
                        {"pinNumber": "2", "net": "GND"}]}
        proc = self._run(self._intent(
            ratings=[{"part": "R9", "between": ["PWR12V", "GND"],
                      "max_power_w": 0.05}]), extras=[res])
        self.assertIn("OVER_RATING", proc.stdout)
        self.assertIn("144.0mW", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "ratings"), "fail")

    def test_intermediate_net_gets_a_worst_case_bound(self):
        """中间节点（GATE 不是电源轨）现在算得出**最坏电位差**，不再一律 unknown。

        GATE 经 R5 可达 PWR5V（5V）、经 Q1 可达 GND（0V）→ 范围 [0, 5]。
        对 PWR5V（恒 5V）的最坏差 = max(|5-5|, |5-0|) = 5V。
        这是最坏情况，不是工作点——所以输出里标注了「最坏情况」。
        """
        proc = self._run(self._intent(
            ratings=[{"part": "R5", "between": ["GATE", "PWR5V"], "max_v": 10}]))
        self.assertEqual(check_status(proc.stdout, "ratings"), "pass")
        self.assertIn("最坏情况", proc.stdout)
        self.assertIn("实际 5.0V / 额定 10.0V", proc.stdout)

    def test_intermediate_net_over_rating_still_fails(self):
        """最坏电位差超过额定 → 必须 fail，不能因为"算的是上界"就放过。"""
        proc = self._run(self._intent(
            ratings=[{"part": "R5", "between": ["GATE", "PWR5V"], "max_v": 3}]))
        self.assertIn("OVER_RATING", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "ratings"), "fail")

    def test_net_with_no_reachable_rail_is_unknown(self):
        """孤立网络（整块连通部分够不到任何已声明轨）→ 仍然 unknown，不猜。"""
        netlist = self.tmp / "island.json"
        data = self._netlist()
        data["components"].append(
            {"designator": "R7", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "ISLAND_A"},
                      {"pinNumber": "2", "net": "ISLAND_B"}]})
        netlist.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        intent_path = self.tmp / "island-intent.json"
        intent_path.write_text(json.dumps(self._intent(
            ratings=[{"part": "R7", "between": ["ISLAND_A", "ISLAND_B"],
                      "max_v": 10}]), ensure_ascii=False), encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        self.assertEqual(check_status(proc.stdout, "ratings"), "unknown")
        self.assertIn("不猜", proc.stdout)

    def test_no_ratings_declared_is_not_run(self):
        proc = self._run(self._intent())
        self.assertEqual(check_status(proc.stdout, "ratings"), "not_run")

    def test_three_volt_rail_drive_is_not_judged_as_five(self):
        """3.3V 逻辑轨上的栅极电压必须按 3.3V 算，不能写死 5V。

        这是本轮修的一个既有缺陷：check_drive 原来取 VCC_FALLBACK=5.0，
        一颗 Vgs(th)=4.0V 的管子挂在 3.3V 轨上会被误判成"够开"。
        """
        netlist = self.tmp / "v33.json"
        netlist.write_text(json.dumps(self._netlist(), ensure_ascii=False),
                           encoding="utf-8")
        intent = self._intent(power_rail_v=3.3)
        intent["switches"][0]["vgs_th"] = 4.0   # 3.3V 打不开，5V 能打开
        intent_path = self.tmp / "v33-intent.json"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False),
                               encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        # 按 3.3V 算 → 低于 4.0V 门槛 → 必须 fail
        self.assertEqual(check_status(proc.stdout, "switch_drive"), "fail")
        self.assertIn("VGS_BELOW_THRESHOLD", proc.stdout)


class ToleranceSpreadTests(unittest.TestCase):
    """容差分析：只报标称动作温度不够，要报**最坏会摊到哪**。

    第 1 轮就记过「NTC 的 B 值容差会让 45°C 摊成 61–67°C」，但那是手算的，
    工具一直没算过。这里把它变成可算的：对每个带容差的量按 ±pct 扰动，
    **枚举全部组合**（不是逐个扰动——同向叠加会把最坏情况低估）。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-tol-"))

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _parts(self):
        return {"components": [
            {"designator": "NTC1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "NTC/10K",
             "pins": [{"pinNumber": "1", "pinName": "1", "net": "NTC_MID"},
                      {"pinNumber": "2", "pinName": "2", "net": "GND"}]},
            {"designator": "R1", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "NTC_MID"}]},
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "ALARM"}, {"pinNumber": "2", "net": "TH"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R2", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH"}]},
            {"designator": "R3", "componentType": "part",
             "otherProperty": {"Value": "4.3kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH"}, {"pinNumber": "2", "net": "GND"}]},
        ]}

    def _intent(self, tol_pct, target_tol):
        return {"schema": "easycirq-design-intent/v1", "power_rail": "PWR5V",
                "ground": "GND",
                "threshold": {"comparator": "U1", "target_c": 45,
                              "tolerance_c": target_tol, "vcc": 5.0,
                              "sensor": {"kind": "ntc", "r25": 10000, "b": 3950},
                              "r_pull_ohms": 10000,
                              "tolerances": {"resistor_pct": tol_pct,
                                             "ntc_r25_pct": tol_pct,
                                             "ntc_b_pct": tol_pct}}}

    def _run(self, tol_pct, target_tol):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps(self._parts(), ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(self._intent(tol_pct, target_tol),
                                          ensure_ascii=False), encoding="utf-8")
        return run(netlist, intent=intent_path)

    def test_one_percent_tolerances_fit_a_three_degree_target(self):
        proc = self._run(1, 3)
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "pass")
        self.assertIn('"tolerance"', proc.stdout)
        self.assertIn('"samples": 32', proc.stdout)
        self.assertIn('"spread_c"', proc.stdout)

    def test_same_circuit_fails_a_one_degree_target(self):
        """同一个电路，客户要 ±1°C 就做不到 —— 标称值在范围内也不行。

        这正是容差分析存在的理由：只报标称 45.3°C 会让这条需求看起来"满足"。
        """
        proc = self._run(1, 1)
        self.assertIn("TOLERANCE_OUT_OF_TARGET", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "fail")
        self.assertEqual(proc.returncode, 1, proc.stdout[-500:])

    def test_five_percent_parts_blow_the_target(self):
        proc = self._run(5, 3)
        self.assertIn("TOLERANCE_OUT_OF_TARGET", proc.stdout)
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "fail")
        # 5% 器件散布应该明显大于 1% 的 2.5°C
        match = re.search(r'"spread_c":\s*([0-9.]+)', proc.stdout)
        self.assertIsNotNone(match)
        self.assertGreater(float(match.group(1)), 5.0)

    def test_no_tolerances_declared_means_no_claim(self):
        """没声明容差就不算，也不能假装在容差范围内。"""
        netlist = self.tmp / "nt.json"
        netlist.write_text(json.dumps(self._parts(), ensure_ascii=False),
                           encoding="utf-8")
        intent = self._intent(1, 3)
        intent["threshold"].pop("tolerances")
        intent_path = self.tmp / "nt-intent.json"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False),
                               encoding="utf-8")
        proc = run(netlist, intent=intent_path)
        self.assertEqual(check_status(proc.stdout, "threshold_sanity"), "pass")
        self.assertNotIn('"tolerance"', proc.stdout)


class HysteresisToleranceTests(unittest.TestCase):
    """回差宽度也要做容差分析——刚做的阈值容差没覆盖到回差。

    工程意义：客户说「别在边上疯狂启停」，回差太**小**才抖。
    所以硬判据只有一条：**某些批次回差归零或根本不动作**（必然抖）。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dv-htol-"))

    @classmethod
    def tearDownClass(cls):
        for path in cls.tmp.glob("*"):
            path.unlink()
        cls.tmp.rmdir()

    def _parts(self, r_hyst):
        return {"components": [
            {"designator": "NTC1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "NTC/10K",
             "pins": [{"pinNumber": "1", "pinName": "1", "net": "NTC_MID"},
                      {"pinNumber": "2", "pinName": "2", "net": "GND"}]},
            {"designator": "R1", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "NTC_MID"}]},
            {"designator": "U1", "componentType": "part", "otherProperty": {},
             "manufacturerId": "LM393",
             "pins": [{"pinNumber": "1", "net": "ALARM"}, {"pinNumber": "2", "net": "TH"},
                      {"pinNumber": "3", "net": "NTC_MID"}, {"pinNumber": "4", "net": "GND"},
                      {"pinNumber": "8", "net": "PWR5V"}]},
            {"designator": "R2", "componentType": "part",
             "otherProperty": {"Value": "10kΩ"},
             "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "TH"}]},
            {"designator": "R3", "componentType": "part",
             "otherProperty": {"Value": "4.3kΩ"},
             "pins": [{"pinNumber": "1", "net": "TH"}, {"pinNumber": "2", "net": "GND"}]},
            {"designator": "R6", "componentType": "part",
             "otherProperty": {"Value": r_hyst},
             "pins": [{"pinNumber": "1", "net": "ALARM"},
                      {"pinNumber": "2", "net": "NTC_MID"}]},
        ]}

    def _intent(self, tol_pct):
        return {"schema": "easycirq-design-intent/v1", "power_rail": "PWR5V",
                "ground": "GND",
                "threshold": {"comparator": "U1", "target_c": 45,
                              "tolerance_c": 3, "vcc": 5.0,
                              "sensor": {"kind": "ntc", "r25": 10000, "b": 3950},
                              "r_pull_ohms": 10000, "hysteresis_c": 3,
                              "tolerances": {"resistor_pct": tol_pct,
                                             "ntc_r25_pct": tol_pct,
                                             "ntc_b_pct": tol_pct}}}

    def _run(self, r_hyst, tol_pct):
        netlist = self.tmp / "list.json"
        netlist.write_text(json.dumps(self._parts(r_hyst), ensure_ascii=False),
                           encoding="utf-8")
        intent_path = self.tmp / "intent.json"
        intent_path.write_text(json.dumps(self._intent(tol_pct), ensure_ascii=False),
                               encoding="utf-8")
        return run(netlist, intent=intent_path)

    def test_width_spread_is_computed(self):
        """39k 回差电阻、1% 器件：宽度散布要算出来，且不该归零。"""
        proc = self._run("39kΩ", 1)
        self.assertEqual(check_status(proc.stdout, "hysteresis"), "pass")
        self.assertIn('"width_min_c"', proc.stdout)
        self.assertIn('"samples": 64', proc.stdout)
        match = re.search(r'"width_min_c":\s*([0-9.]+)', proc.stdout)
        self.assertIsNotNone(match)
        self.assertGreater(float(match.group(1)), 0.0)

    def test_width_vanishes_under_tolerance_fails(self):
        """5% 器件 + 小回差电阻：某些组合穿越不了阈值 → 必须 fail。

        这一条是回差容差的**核心**：标称值再好看，只要有一批货没有回差，
        现场就是反复启停。
        """
        proc = self._run("1kΩ", 5)
        self.assertEqual(check_status(proc.stdout, "hysteresis"), "fail")
        self.assertEqual(proc.returncode, 1, proc.stdout[-600:])


class HonestyTests(unittest.TestCase):
    """判不了的时候必须说判不了，不能默认 pass。"""

    def test_no_intent_is_not_applicable_not_pass(self):
        """没声明设计意图时判 na（不适用），绝不冒充 pass。

        na 与 not_run 的区别：not_run 是"该跑没跑"（证据缺失），
        na 是"这块板从未声明自己要做什么"（无从判起）。两者都不等于通过。
        """
        tmp = pathlib.Path(__file__).parent / "_dv_nointent.json"
        try:
            proc = run(AFTER, intent=None, out=tmp)
            self.assertEqual(proc.returncode, 2, proc.stdout[-400:])
            report = load(tmp)
            self.assertEqual(report["verdict"], "na")
            self.assertNotEqual(report["verdict"], "pass")
            for check in report["checks"]:
                self.assertEqual(check["status"], "na")
                self.assertIn("没有提供 --intent", check["reason"])
            # 没有意图就没有可确认的违规，但也绝不能算成"检查通过"
            self.assertEqual(report["metrics"]["design_violations"], 0)
            self.assertEqual(report["findings"], [])
        finally:
            if tmp.is_file():
                tmp.unlink()

    def test_unknown_device_is_not_pass(self):
        # 比较器换成不在器件表里的型号：必须 unknown，不能当 pass
        data = load(AFTER)
        for comp in data.get("components") or []:
            if comp.get("designator") == "U1":
                comp["manufacturerId"] = "LM9999"
        tmp = pathlib.Path(__file__).parent / "_dv_unknown"
        tmp.mkdir(exist_ok=True)
        netlist = tmp / "list.json"
        netlist.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        out = tmp / "report.json"
        try:
            proc = run(netlist, out=out)
            self.assertEqual(proc.returncode, 2, proc.stdout[-400:])
            check = next(c for c in load(out)["checks"]
                         if c["id"] == "threshold_sanity")
            self.assertEqual(check["status"], "unknown")
            self.assertIn("认不出来", check["reason"])
        finally:
            for path in tmp.glob("*"):
                path.unlink()
            tmp.rmdir()


if __name__ == "__main__":
    unittest.main()
