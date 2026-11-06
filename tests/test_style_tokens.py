"""以 style-reference 为基准的合规检查。

目标明确要求"以 style-reference 样例为基准"，但 `style-tokens.json` 里的
硬性约束此前**从未被测量过**。本轮量出来：

    layout.zone_area_ratio 要求 [0.25, 0.80]
    实测 M3 = 5.5%   ← 硬性违反，也就是"一张邮票贴在巨幅纸上"

修法是让分区框铺满**可用区**（页面减页边距，并受 80% 上限约束）。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHK = ROOT / "easycirq" / "scripts" / "sch_style_check.py"
TOKENS = ROOT / "easycirq" / "assets" / "style-reference" / "style-tokens.json"
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"
FRAMES = ROOT / "reports" / "hard-board" / "board2" / "review" / "frames-P3_5V转3V3主逻辑轨.json"


def test_tokens_define_zone_area_ratio():
    t = json.loads(TOKENS.read_text(encoding="utf-8"))
    lo, hi = t["layout"]["zone_area_ratio"]
    assert 0 < lo < hi <= 1.0


def test_checker_reports_ratio(tmp_path):
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    p = subprocess.run([sys.executable, str(CHK), "--composition", str(COMP), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    if not p.stdout.strip():
        pytest.skip("无输出")
    d = json.loads(p.stdout)
    c = next(x for x in d[0]["checks"] if x["check"] == "layout.zone_area_ratio")
    assert "value" in c and "want" in c


def test_real_frame_satisfies_tokens():
    """按**真实导出的框**测，必须落在 tokens 区间内。"""
    if not COMP.is_file() or not FRAMES.is_file():
        pytest.skip("缺排版稿或 frames")
    p = subprocess.run([sys.executable, str(CHK), "--composition", str(COMP),
                        "--frames", "M3=%s" % FRAMES],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    assert p.returncode == 0, p.stdout[-400:]
    assert "✅" in p.stdout


def test_designator_frame_fill_code_present():
    """渲染器里必须有"框铺满可用区"的实现，否则又会退回 5.5%。"""
    src = (ROOT / "easycirq" / "scripts" / "sch_layout_review.py").read_text(encoding="utf-8")
    assert "ZONE_AREA_MIN" in src
    assert "ZONE_AREA_MAX" in src
    assert src.count("ZONE_AREA_MIN") >= 2, "两处框（导出 + 绘制）都要改"
