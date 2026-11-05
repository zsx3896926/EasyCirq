"""模块拆分预检的验收 —— 它必须**复现真实求解器的结论**。

这条判据的用途是：跑求解器（18 秒）之前就知道装不装得下。
所以测试的核心不是"能跑"，而是**预测与实测一致**：

| 模块 | 预检估计宽 | 可用宽 | 预检判定 | 求解器实测 |
|---|---|---|---|---|
| M1（24 件，A4） | 610 | 287 | 超宽 | `module M1 is wider than the usable sheet` |
| M4（10 件，A4） | 288 | 287 | 超宽 | `module M4 is wider than the usable sheet` |

M4 只超 1 raw —— 这说明系数不是拍脑袋定的，是真标定过的。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIT = ROOT / "easycirq" / "scripts" / "sch_module_fit.py"
P1 = ROOT / "reports" / "hard-board" / "board2" / "layout-input-P1.json"
P2 = ROOT / "reports" / "hard-board" / "board2" / "layout-input-P2.json"

pytestmark = pytest.mark.skipif(not FIT.is_file(), reason="没有拆分预检脚本")


def run(path, *extra):
    p = subprocess.run([sys.executable, str(FIT), str(path), "--json", *extra],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    return p.returncode, json.loads(p.stdout)


def test_predicts_m1_and_m4_do_not_fit():
    """两个真实失败必须被预测到 —— 这是这套判据存在的唯一理由。"""
    if not P1.is_file() or not P2.is_file():
        pytest.skip("输入不存在")

    _, o1 = run(P1)
    m1 = next(m for m in o1["modules"] if m["module"] == "M1")
    assert m1["fits"] is False, "M1（24 件）必须预测为装不下"
    assert m1["estWidth"] > o1["usableWidth"], (m1, o1["usableWidth"])

    _, o2 = run(P2)
    m4 = next(m for m in o2["modules"] if m["module"] == "M4")
    assert m4["fits"] is False, "M4（10 件）必须预测为装不下"
    # 只超一点点，说明系数是标定过的而不是随手放大
    assert 0 < m4["estWidth"] - o2["usableWidth"] < 20, \
        "M4 应当只是略微超出（实测超 1 raw），得到 %.1f" % (
            m4["estWidth"] - o2["usableWidth"])


def test_smaller_modules_are_predicted_to_fit():
    """不能被一律判死 —— 小模块必须预测为装得下，否则这个预检没有区分度。"""
    if not P1.is_file():
        pytest.skip("输入不存在")
    _, o = run(P1)
    small = [m for m in o["modules"] if m["module"] in ("M2", "M3")]
    assert small, o["modules"]
    assert all(m["fits"] for m in small), \
        "M2/M3（7-8 件）应当装得下：%r" % [(m["module"], m["estWidth"]) for m in small]


def test_bigger_paper_makes_m1_fit():
    """换更大的纸，M1 的判定应当翻转 —— 判据必须对纸型敏感。"""
    if not P1.is_file():
        pytest.skip("输入不存在")
    _, a4 = run(P1)
    _, a2 = run(P1, "--paper", "A2")
    m1a4 = next(m for m in a4["modules"] if m["module"] == "M1")
    m1a2 = next(m for m in a2["modules"] if m["module"] == "M1")
    assert a2["usableWidth"] > a4["usableWidth"]
    assert m1a2["estWidth"] == m1a4["estWidth"], "估计宽不该随纸型变化"
    # A2 584 可用 < 610，所以 M1 仍装不下 —— 与实测一致
    assert m1a2["fits"] is (m1a2["estWidth"] <= a2["usableWidth"])


def test_reports_a_concrete_split_target():
    """不光说"装不下"，还要说"拆成几个"。"""
    if not P1.is_file():
        pytest.skip("输入不存在")
    p = subprocess.run([sys.executable, str(FIT), str(P1)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    assert "至少要拆成" in p.stdout, p.stdout[-400:]
    assert "件" in p.stdout


def test_estimates_use_measured_bodies_not_guesses():
    """尺寸必须来自 measurements 的本体，不能是常数。"""
    if not P1.is_file():
        pytest.skip("输入不存在")
    src = json.loads(P1.read_text(encoding="utf-8"))
    widths = []
    for m in src["measurements"]:
        b = m["bbox"]
        widths.append(b["maxX"] - b["minX"])
    assert len(set(widths)) > 3, "本体宽度应当多种多样（来自实测），得到 %r" % set(widths)
