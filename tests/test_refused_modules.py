"""渲染被拒的模块，报告里必须显示 **REFUSED**，不能沿用旧结论。

发现（#132）：`ACCEPTANCE.md` 里 M1/M2 显示"内容不越框 ✅、遮字 ✅…"，
看着只差一两条 —— 那是**早前能渲染时**留下的产物。当前它们连渲染都没过。

用户读的是这份一页纸报告。显示一份"差不多通过"的旧表，比显示"未产出"更糟。
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "reports" / "hard-board" / "board2"
ACC = ROOT / "easycirq" / "scripts" / "sch_preview_accept.py"


def test_mark_refused_exists():
    s = ACC.read_text(encoding="utf-8")
    assert "def _mark_refused(" in s
    # 所有错误返回点都要先标记
    assert s.count("_mark_refused(module, work,") >= 5


def test_refused_modules_have_no_criteria():
    p = WORK / "acceptance-M1.json"
    if not p.is_file():
        pytest.skip("没有验收产物")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d.get("verdict") == "REFUSED"
    assert not d.get("criteria"), "被拒模块不该带逐条结论"
    assert d.get("note")


def test_report_shows_refused():
    p = WORK / "ACCEPTANCE.md"
    if not p.is_file():
        pytest.skip("没有报告")
    t = p.read_text(encoding="utf-8")
    assert "REFUSED" in t
    # 被拒模块不该出现在判据总表的 ✅ 里
    row = [l for l in t.splitlines() if l.startswith("| M1 |")]
    assert row, "报告缺 M1 行"
    assert "REFUSED" in row[0] or "0" in row[0]
