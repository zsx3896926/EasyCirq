"""候选稿模式：验一份排版稿**不替换**正式稿。

为什么需要（friction #92）：
  #85 记过"铺开排版仍 8 PASS"，本轮复现却是**门拒绝**。根因是我当时的临时脚手架
  "备份 → 替换 → 跑验收 → finally 恢复"；一旦恢复先于读取，读到的就是**旧稿结论**。
  和 #89 的"陈旧产物冒充当前结论"同一个病根。

把"验候选稿"做成产品能力后，**没有替换/恢复这一步**，也就没有它带来的假结论。
"""
import importlib.util
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACC = ROOT / "easycirq" / "scripts" / "sch_preview_accept.py"
WORK = ROOT / "reports" / "hard-board" / "board2"


def test_candidate_flag_exists():
    s = ACC.read_text(encoding="utf-8")
    assert "--candidate" in s
    assert "comp_override" in s


def test_driver_does_not_swap_composition_files():
    """驱动不许自己替换正式稿 —— 那正是假结论的来源。"""
    s = ACC.read_text(encoding="utf-8")
    assert "shutil.copy2" not in s, "驱动里出现了复制替换，容易造成假结论"


def _one(module, override=None):
    spec = importlib.util.spec_from_file_location("acc_x", str(ACC))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.one(module, str(WORK), m.exe_path(), m.skill_scripts(),
                 comp_override=override)


def test_candidate_matches_official_for_same_file():
    """同一份稿走覆盖路径，结论必须与正式路径一致。"""
    comp = WORK / "composition-M3-placed.json"
    if not comp.is_file():
        pytest.skip("没有排版稿")
    a = _one("M3")
    b = _one("M3", str(comp))
    assert (a.get("verdict"), a.get("error")) == (b.get("verdict"), b.get("error"))


def test_candidate_override_actually_changes_verdict():
    """换一份（已知过不了门的）候选稿，结论必须不同 —— 否则覆盖根本没生效。"""
    comp = WORK / "composition-M3-placed.json"
    bad = WORK / "cand-M3-placed.json"
    if not comp.is_file() or not bad.is_file():
        pytest.skip("缺候选稿")
    official = _one("M3")
    cand = _one("M3", str(bad))
    assert official.get("verdict") == "INCOMPLETE", official
    assert cand.get("error"), "候选稿应当被门拒绝，却没报错：%r" % cand
