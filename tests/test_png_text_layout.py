"""审图 PNG 的三处文字压叠修复（放大后才看得见的）。

这些**检查器查不出来**（SVG 侧的文字审计是 0 缺陷），只有把 PNG 放大看才有：
  1. `GND` 网标压住 `EN` 引脚名 —— 网标标签一律画在旗标右侧，而右侧正是本体内
  2. 引脚名之间可能叠 —— 超出本体的引脚被 clamp 到同一条边线
  3. PNG 完全没有结点圆点（SVG 早就有）
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def test_net_flag_label_avoids_body():
    """网标标签要朝**背离器件**的一侧，否则会压住体内引脚名。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("背离器件")
    assert i > 0, "网标标签没有背离器件的逻辑"
    seg = s[i:i + 700]
    assert "to_left" in seg, "没有左右判定"


def test_pin_names_are_deduped():
    s = REVIEW.read_text(encoding="utf-8")
    assert "drawn_boxes" in s, "引脚名没有去重"
    assert "clashes(" in s


def test_junction_dots_present():
    s = REVIEW.read_text(encoding="utf-8")
    assert "结点圆点" in s


def test_renderer_runs_and_produces_png(tmp_path):
    """改完不许崩 —— 本地已经崩过一次（变量名覆盖）。"""
    import subprocess
    import sys
    comp = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"
    if not comp.is_file():
        pytest.skip("没有排版稿")
    p = subprocess.run([sys.executable, str(REVIEW), "--composition", str(comp),
                        "--page-name", "t", "--out-dir", str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    assert p.returncode == 0, (p.stdout or p.stderr)[-400:]
    assert (tmp_path / "t.png").is_file()


def test_spread_registers_reservations_when_asked():
    """铺开图必须能带预留区——否则"不穿线"只是碰巧。"""
    sp = ROOT / "easycirq" / "scripts" / "sch_layout_spread.py"
    s = sp.read_text(encoding="utf-8")
    assert "--reserve-labels" in s
    assert "with_reservations" in s
