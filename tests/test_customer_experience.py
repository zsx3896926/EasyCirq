"""Acceptance metrics for the customer experience, measured on real CLI output.

Metric 2 (tool terms the customer must understand), metric 4 (every refusal
carries a next step) and metric 6 (the card never claims more than the
evidence supports) are testable without a physical board: run the installed
CLI and inspect what the customer actually sees.

These tests skip when the easycirq CLI is not on PATH.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P1_REPORT = ROOT / "reports" / "p1-pipeline" / "kpi-report.json"
EXE = shutil.which("easycirq")

# words a customer must never have to decode (metric 2)
FORBIDDEN = ["daemon", "connector", "typed action", "gate token", "kpi",
             "snapshot", "readback", "typed-action", "gate-token"]
# a refusal without one of these is not explainable (metric 4)
NEXT_MARKERS = ["下一步", "next", "重跑", "重新", "补齐", "修完", "运行 easycirq"]


INLINE_CODE = re.compile(r"`[^`]*`")


def strip_inline_code(text):
    """去掉反引号里的命令字面量，只留散文。

    为什么要这么做：指标 2 数的是"客户**需要理解**的术语"。
    `easycirq daemon start` 是一条客户原样复制的命令——他不需要知道
    daemon 是什么也能跑；而散文里出现"daemon"才是真的要求他理解这个概念。

    这一步不是放宽判据，而是把判据对准它本来要测的东西。
    命令字面量另有约束：见 CustomerTerms 里的 test_commands_it_names_exist
    （它点名的命令必须真的存在，不能是死命令）。
    """
    return INLINE_CODE.sub(" ", text)


def run(*args, cwd=None):
    return subprocess.run([EXE, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd,
                          timeout=180)


@unittest.skipUnless(EXE, "easycirq CLI not on PATH")
class CustomerTerms(unittest.TestCase):
    def assert_no_jargon(self, text, label):
        prose = strip_inline_code(text)
        lowered = prose.lower()
        hits = [word for word in FORBIDDEN if word in lowered]
        self.assertEqual(hits, [], f"{label} leaks jargon in prose: {hits}\n{text}")

    def test_commands_it_names_exist(self):
        """面向客户的文本里点名的 easycirq 子命令必须真的存在。

        为什么扫源码而不是扫运行输出：输出会随环境变（后台起着时 setup 只报
        "一切就绪"，一句命令都不提；后台停了才给引导）。靠运行输出测，
        结果取决于当时后台在不在跑——那不是测试，那是碰运气。

        源码是确定的：客户会看到的那六个文件里出现的每个 `easycirq <子命令>`，
        都必须能 `--help` 解析。
        """
        sources = [
            ROOT / "runtime" / "internal" / "app" / "cmd_setup.go",
            ROOT / "runtime" / "internal" / "app" / "cmd_status.go",
            ROOT / "runtime" / "internal" / "app" / "cmd_card.go",
            ROOT / "runtime" / "internal" / "app" / "cmd_acceptance.go",
            ROOT / "easycirq" / "scripts" / "sch_status.py",
            ROOT / "easycirq" / "scripts" / "sch_delivery_card.py",
        ]
        mentioned = set()
        for path in sources:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"easycirq ([a-z][a-z0-9-]*)", text):
                mentioned.add(match.group(1))
        # 这些是命令行里的选项词，不是子命令
        skip = {"--help", "-h", "setup", "status", "card", "acceptance"}
        to_probe = sorted(m for m in mentioned if not m.startswith("-"))
        self.assertTrue(to_probe, "面向客户的源码里没有点名任何子命令，测试前提不成立")
        for subcommand in to_probe:
            probe = run(subcommand, "--help")
            combined = (probe.stdout or "") + (probe.stderr or "")
            self.assertNotIn("没有这个命令", combined,
                             f"客户文本里点名的 `easycirq {subcommand}` 并不存在")
            self.assertNotIn("unknown command", combined.lower(),
                             f"客户文本里点名的 `easycirq {subcommand}` 并不存在")

    def test_guidance_prose_has_no_tool_jargon(self):
        """后台没跑时 setup 会给一段引导；那段引导的散文里不许有术语。

        直接检查渲染出来的引导文本走不通（要先把后台停掉），
        所以退一步查源码里的中文文案：这才是客户真正会读到的东西。
        """
        setup = ROOT / "runtime" / "internal" / "app" / "cmd_setup.go"
        if not setup.is_file():
            self.skipTest("cmd_setup.go 不在仓库里")
        text = setup.read_text(encoding="utf-8", errors="replace")
        # 取所有含中文的字符串字面量
        chinese_literals = [m for m in re.findall(r'"([^"\n]*)"', text)
                            if re.search(r"[\u4e00-\u9fff]", m)]
        self.assertTrue(chinese_literals, "cmd_setup.go 里没有找到中文文案")
        offenders = []
        for literal in chinese_literals:
            prose = strip_inline_code(literal).lower()
            hits = [word for word in FORBIDDEN if word in prose]
            if hits:
                offenders.append((hits, literal[:80]))
        self.assertEqual(offenders, [], f"setup 的引导散文里出现术语: {offenders}")

    def test_status_uses_no_tool_jargon(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("status", "--kpi-report", str(P1_REPORT))
        self.assert_no_jargon(result.stdout, "status")

    def test_card_uses_no_tool_jargon(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("card", "--kpi-report", str(P1_REPORT))
        self.assert_no_jargon(result.stdout, "card")

    def test_setup_uses_no_tool_jargon(self):
        result = run("setup")
        self.assert_no_jargon(result.stdout, "setup")


@unittest.skipUnless(EXE, "easycirq CLI not on PATH")
class RefusalsExplainThemselves(unittest.TestCase):
    def assert_has_next(self, text, label):
        self.assertTrue(any(marker in text for marker in NEXT_MARKERS),
                        f"{label} has no next step: {text}")

    def test_status_refusal_has_next(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("status", "--kpi-report", str(P1_REPORT))
        if result.returncode == 0:
            self.skipTest("report is PASS, nothing to refuse")
        self.assert_has_next(result.stdout, "status")

    def test_card_refusal_has_next(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("card", "--kpi-report", str(P1_REPORT))
        if result.returncode == 0:
            self.skipTest("report is ready, nothing to refuse")
        self.assert_has_next(result.stdout, "card")

    def test_acceptance_with_a_malformed_record_is_explained(self):
        # a silent non-zero exit is not explainable: the customer must be told
        # what is wrong and what to do next
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{ not json", encoding="utf-8")
            result = run("acceptance", "--file", str(bad))
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stdout.strip(), "the failure printed nothing")
            self.assert_has_next(result.stdout, "acceptance(bad)")

    def test_acceptance_without_record_has_next(self):
        with tempfile.TemporaryDirectory() as d:
            result = run("acceptance", "--file", str(Path(d) / "missing.json"))
            self.assertNotEqual(result.returncode, 0)
            self.assert_has_next(result.stdout, "acceptance")


@unittest.skipUnless(EXE, "easycirq CLI not on PATH")
class CardNeverOverclaims(unittest.TestCase):
    def write_report(self, folder, verdict, apply_allowed):
        path = Path(folder) / "kpi.json"
        path.write_text(json.dumps({
            "schema": "easycirq-sch-kpi-report/v1", "project": "P", "page": "P1",
            "verdict": verdict,
            "kpis": [
                {"no": 1, "id": "unconnected", "status": "pass"},
                {"no": 2, "id": "erc", "status": "missing"},
            ],
            "blockers": [{"kpi": "erc", "reason": "缺证据"}],
            "stability": {"apply_allowed": apply_allowed},
        }), encoding="utf-8")
        return path

    def test_pass_verdict_with_missing_evidence_is_not_ready(self):
        # a report that claims PASS while a check has no evidence must not be
        # turned into "can be ordered" by the card
        with tempfile.TemporaryDirectory() as d:
            report = self.write_report(d, "PASS", False)
            result = run("card", "--kpi-report", str(report))
            self.assertNotIn("✅", result.stdout)
            self.assertIn("还不能判断", result.stdout)
            self.assertIn(result.returncode, (1, 2))

    def test_blocked_verdict_is_never_ready(self):
        with tempfile.TemporaryDirectory() as d:
            report = self.write_report(d, "BLOCKED", False)
            result = run("card", "--kpi-report", str(report))
            self.assertNotIn("✅", result.stdout)
            # blocked-by-defect says "还不能打样"; blocked-only-by-evidence says
            # "还不能判断" -- neither may claim ready
            self.assertTrue("还不能打样" in result.stdout
                            or "还不能判断" in result.stdout)
            self.assertIn(result.returncode, (1, 2))


if __name__ == "__main__":
    unittest.main()
