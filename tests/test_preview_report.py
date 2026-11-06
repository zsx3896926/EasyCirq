"""验收报告的回归测试：报告必须**如实反映**产物，不许美化。"""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REP = ROOT / "easycirq" / "scripts" / "sch_preview_report.py"
WORK = ROOT / "reports" / "hard-board" / "board2"


def test_report_lists_every_failing_criterion():
    """FAIL 的判据必须出现在"未通过/未测/不适用"章节里。"""
    if not (WORK / "acceptance-M1.json").is_file():
        pytest.skip("没有验收产物")
    md = (WORK / "ACCEPTANCE.md")
    if not md.is_file():
        pytest.skip("没有报告")
    text = md.read_text(encoding="utf-8")
    import json
    d = json.loads((WORK / "acceptance-M1.json").read_text(encoding="utf-8"))
    for c in d["criteria"]:
        if c["status"] == "FAIL":
            assert c["title"] in text, "报告的章节里缺 %s" % c["title"]


def test_report_never_claims_pass_overall():
    """五块都是 BLOCKED 时，报告里不许出现"全部通过"这类措辞。"""
    md = WORK / "ACCEPTANCE.md"
    if not md.is_file():
        pytest.skip("没有报告")
    text = md.read_text(encoding="utf-8")
    for bad in ("全部通过", "全绿", "已达标"):
        assert bad not in text, "报告出现了不该有的措辞：%s" % bad


def test_report_contains_reproduction_commands():
    md = WORK / "ACCEPTANCE.md"
    if not md.is_file():
        pytest.skip("没有报告")
    text = md.read_text(encoding="utf-8")
    assert "sch_preview_accept.py" in text
    assert "sch_text_audit.py" in text
    assert text.count("```") >= 2, "缺代码块"


def test_report_lists_known_false_positives():
    md = WORK / "ACCEPTANCE.md"
    if not md.is_file():
        pytest.skip("没有报告")
    text = md.read_text(encoding="utf-8")
    assert "已知误报" in text
    assert "引脚名" in text


def test_report_generator_is_runnable(tmp_path):
    if not (WORK / "acceptance-M1.json").is_file():
        pytest.skip("没有验收产物")
    out = tmp_path / "r.md"
    p = subprocess.run([sys.executable, str(REP), "--work", str(WORK),
                        "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    assert out.is_file(), (p.stdout or p.stderr)[:300]
    assert out.read_text(encoding="utf-8").startswith("# ")
