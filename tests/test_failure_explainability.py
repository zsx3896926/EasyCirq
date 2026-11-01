"""客户看不到东西时，必须看到「下一步」。

指标 4 是「失败可解释率 100%」。这条不是靠抽查几条命令就能证明的——
2026-11-01 发现 `card --kpi-report <不存在>` 会说成「这块板还没检查过」，
而 `card --kpi-report <不是 JSON>` 干脆**一句话都不说**（只返回退出码 2）。

一个拼错的路径被伪装成「还没检查」，比报错更难查。
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KPI = ROOT / "reports" / "alarm-r163" / "kpi-report.json"
EXE = "easycirq"


def run(*args):
    return subprocess.run([EXE, *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def output(proc):
    return (proc.stdout or "") + (proc.stderr or "")


def test_missing_report_names_the_file_and_says_what_to_do():
    proc = run("card", "--kpi-report", "definitely-not-here.json")
    text = output(proc)
    assert proc.returncode != 0
    assert "definitely-not-here.json" in text, text
    assert "下一步" in text, text
    # 不能把"路径错"伪装成"还没检查"
    assert "还没检查过" not in text, text


def test_unparsable_report_is_not_silent(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("this is not json", encoding="utf-8")
    proc = run("card", "--kpi-report", str(bad))
    text = output(proc)
    assert proc.returncode != 0
    assert text.strip(), "读不出来时不能一句话都不说"
    assert "下一步" in text, text


def test_missing_acceptance_record_explains_itself():
    proc = run("acceptance", "--file", "no-such-record.json")
    text = output(proc)
    assert proc.returncode == 2
    assert "验收" in text, text


def test_good_report_still_works():
    assert KPI.is_file(), "expected the alarm report to be present"
    proc = run("card", "--kpi-report", str(KPI))
    assert proc.returncode == 0, output(proc)
    assert "下一步" in output(proc)


def test_unknown_command_speaks_chinese_and_gives_a_next_step():
    """Cobra's default is 'unknown command "x" for "y"' - English, no next step."""
    proc = run("frobnicate")
    text = output(proc)
    assert proc.returncode != 0
    assert "frobnicate" in text, text
    assert "下一步" in text, text
    assert "unknown command" not in text.lower(), text
