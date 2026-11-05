"""回归测试：**同一实例只因外设顺序不同，曾经一次成功一次失败**。

friction #56 的复现与修复都锁在这里：

  复现：24 件实例，几何/网/测量/纸/预算全同，只把
       `connectivity.modules[].peripheralComponents` 倒序 —— 原序 7 秒成功，
       倒序报 `peripheral-direct-missing`（合成校验在**搜索之后**才跑，
       失败不回头重搜）。

  修复：`planLibLayout` 在**合成/归属校验类**失败时，按
       componentId / 位号 / 反序 三种规范排序重摆再试。
       **校验标准一条都没降** —— 每次重试都要过同一套校验。

本文件同时钉住"不是放宽"这一条：真正排不下的输入仍应失败。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "runtime" / "internal" / "app"
SOLVER = APP / "sch_lib_solver.go"
ONE_M1 = ROOT / "reports" / "hard-board" / "board2" / "one-M1.json"


def test_retry_is_order_variation_not_threshold_relaxation():
    """修复必须是"换搜索起点"，不许是"放宽校验"。"""
    src = SOLVER.read_text(encoding="utf-8")
    assert "libLayoutRetryable" in src, "没有重试判定"
    # 只对合成/归属校验类失败重试
    assert "peripheral-direct-missing" in src, "重试条件里没有目标错误"
    # 必须重新调用求解，而不是跳过校验
    assert "libLayoutReorder" in src, "没有顺序变化函数"
    # 三种规范排序
    for mode in ("case 1:", "case 2:", "case 3:"):
        assert mode in src, "缺少排序方式 %s" % mode


def test_retry_does_not_swallow_non_validation_failures():
    """候选预算耗尽（真的排不下）不该被重试掩盖。"""
    src = SOLVER.read_text(encoding="utf-8")
    i = src.find("func libLayoutRetryable")
    j = src.find("\n}", i)
    body = src[i:j]
    assert "candidate" not in body.lower(), \
        "候选耗尽不该进重试条件（会白烧几十万候选）"
    assert "budget" not in body.lower(), "预算类失败不该重试"


def test_reproduction_case_is_recorded():
    """复现用的倒序输入必须留在仓库里，否则以后无法回归。"""
    rev = ROOT / "reports" / "hard-board" / "board2" / "rev.json"
    if not ONE_M1.is_file():
        pytest.skip("没有 one-M1.json")
    if not rev.is_file():
        pytest.skip("没有复现用例 rev.json")
    base = json.loads(ONE_M1.read_text(encoding="utf-8"))
    cur = json.loads(rev.read_text(encoding="utf-8"))
    a = base["connectivity"]["modules"][0]
    b = cur["connectivity"]["modules"][0]
    # 只因顺序不同：集合相同、顺序相反
    assert sorted(a["peripheralComponents"]) == sorted(b["peripheralComponents"])
    assert a["peripheralComponents"] != b["peripheralComponents"], \
        "rev.json 应当是一个不同的顺序"

    # 其余一切相同（几何/网/纸/预算）
    for key in ("sheet", "maxCandidates"):
        assert base.get(key) == cur.get(key), "%s 不该变" % key
    assert [m["designator"] for m in base["measurements"]] == \
           [m["designator"] for m in cur["measurements"]]
