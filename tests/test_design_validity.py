"""设计有效性检查的测试。

这些测试要证明的不是"脚本能跑"，而是**它能抓到当初靠人读电路才发现的那三个缺陷**：

  1. 阈值分压算出的动作温度 25°C，而目标是 60°C
  2. 三极管基极没有直流通路 → 蜂鸣器永远不响
  3. 比较器没有正反馈 → 做不到要求的回差

并且要证明它**不是橡皮图章**：故意改错一个阻值，必须从 pass 变成 fail。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
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

    def test_all_three_checks_pass(self):
        statuses = {c["id"]: c["status"] for c in self.report["checks"]}
        self.assertEqual(statuses, {"threshold_sanity": "pass",
                                    "switch_drive": "pass",
                                    "hysteresis": "pass"})


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
