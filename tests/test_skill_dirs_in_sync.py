"""目标要求「四个技能目录同步」——这条必须**机械可查**，不能靠记忆。

本轮审计：只比对我创作的 13 个脚本 + 参考文档，四个目录全部一致（0 差异）。
全树比对不成立：安装目录里还有上游文件（CHANGELOG/.version/pytest 缓存），
它们本来就不该和本仓副本相同。
"""
import hashlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path.home()
DIRS = (".agents", ".claude", ".codex", ".workbuddy")

# 本会话创作/修改过的脚本：这些必须在四个目录里与本仓**逐字节一致**
MY_SCRIPTS = (
    "sch_layout_review.py", "sch_preview_accept.py", "sch_preview_zones.py",
    "sch_preview_text.py", "sch_layout_acceptance.py", "sch_style_check.py",
    "sch_preview_label_boxes.py", "check_preexisting_failures.py",
    "sch_preview_report.py", "sch_preview_status.py",
    "sch_layout_reserve.py", "sch_layout_normalize.py",
    "sch_composition_snapshot.py",
)
DOC = "preview-acceptance.md"


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _dirs():
    return [HOME / d / "skills" / "easycirq" for d in DIRS
            if (HOME / d / "skills" / "easycirq").is_dir()]


def test_at_least_one_skill_dir_exists():
    assert _dirs(), "一个技能目录都没装"


def test_scripts_are_identical_everywhere():
    src = ROOT / "easycirq" / "scripts"
    drift = []
    for d in _dirs():
        for name in MY_SCRIPTS:
            s = src / name
            if not s.is_file():
                continue
            t = d / "scripts" / name
            if not t.is_file():
                drift.append("%s/%s 缺" % (d.name, name))
            elif _sha(t) != _sha(s):
                drift.append("%s/%s 异" % (d.name, name))
    assert not drift, "技能目录不同步：%s" % drift[:6]


def test_doc_is_identical_everywhere():
    src = ROOT / "easycirq" / "references" / DOC
    if not src.is_file():
        pytest.skip("没有文档")
    drift = [d.name for d in _dirs()
             if not (d / "references" / DOC).is_file()
             or _sha(d / "references" / DOC) != _sha(src)]
    assert not drift, "文档未同步到：%s" % drift


def test_style_tokens_shared():
    """风格 token 是判据的来源，也要四目录一致。"""
    src = ROOT / "easycirq" / "assets" / "style-reference" / "style-tokens.json"
    if not src.is_file():
        pytest.skip("没有 token 文件")
    drift = [d.name for d in _dirs()
             if not (d / "assets" / "style-reference" / "style-tokens.json").is_file()
             or _sha(d / "assets" / "style-reference" / "style-tokens.json") != _sha(src)]
    assert not drift, "token 未同步到：%s" % drift
