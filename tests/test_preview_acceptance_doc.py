"""沉淀测试：验收文档必须存在、可复现、且写明四态与已知限制。

为什么文档也要测试：目标要求"沉淀进产品"，而文档最容易腐烂 ——
命令改名、脚本删了、限制被人"顺手修好"却没更新，都没人发现。

这里钉的是**文档里承诺的东西现在仍然成立**：
  · 提到的脚本都真实存在
  · 四态（PASS/FAIL/NOT RUN/N/A）都写了
  · 已知限制没有被悄悄删掉
  · 四个技能目录都有这份文档
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "easycirq" / "references" / "preview-acceptance.md"


def test_doc_exists():
    assert DOC.is_file(), "缺验收文档"


def test_every_named_script_exists():
    """文档里点名的脚本必须都在仓库里。"""
    if not DOC.is_file():
        pytest.skip("没有文档")
    text = DOC.read_text(encoding="utf-8")
    import re
    names = set(re.findall(r"scripts/([a-z_]+\.py)", text))
    assert names, "文档里没写任何脚本"
    missing = [n for n in sorted(names) if not (ROOT / "easycirq" / "scripts" / n).is_file()]
    assert missing == [], "文档提到的脚本不存在：%r" % missing


def test_doc_states_all_four_verdicts():
    if not DOC.is_file():
        pytest.skip("没有文档")
    text = DOC.read_text(encoding="utf-8")
    for token in ("PASS", "FAIL", "NOT RUN", "N/A"):
        assert token in text, "文档缺结论状态 %s" % token


def test_doc_records_the_designator_limitation():
    """已知限制不许被悄悄删掉 —— 它是目前唯一没解决的判据。"""
    if not DOC.is_file():
        pytest.skip("没有文档")
    text = DOC.read_text(encoding="utf-8")
    assert "位号" in text and ("网标" in text or "预留" in text)
    assert "加纸" in text or "A0" in text, "没记录'加纸无效'这个结论"


def test_doc_records_the_key_case_trap():
    """`textBboxes` 大小写这个坑必须写进文档 —— 它让 7 轮工作白费。"""
    if not DOC.is_file():
        pytest.skip("没有文档")
    text = DOC.read_text(encoding="utf-8")
    assert "textBboxes" in text
    assert "大小写" in text


def test_doc_is_synced_to_skill_dirs():
    """四个技能目录都要有这份文档（目标明确要求同步）。"""
    if not DOC.is_file():
        pytest.skip("没有文档")
    import hashlib
    home = pathlib.Path.home()
    src = hashlib.sha256(DOC.read_bytes()).hexdigest()
    checked = 0
    for n in (".agents", ".claude", ".codex", ".workbuddy"):
        base = home / n / "skills" / "easycirq"
        if not base.exists():
            continue
        dst = base / "references" / "preview-acceptance.md"
        assert dst.is_file(), "%s 缺文档" % n
        assert hashlib.sha256(dst.read_bytes()).hexdigest() == src, \
            "%s 的文档与仓库不一致" % n
        checked += 1
    if checked == 0:
        pytest.skip("本机没有技能目录")


def test_doc_explains_how_to_add_a_criterion():
    if not DOC.is_file():
        pytest.skip("没有文档")
    text = DOC.read_text(encoding="utf-8")
    assert "CRITERIA" in text, "没写怎么加新判据"
    assert "适用性" in text, "没写'适用性判定要在最前面'这个坑"
