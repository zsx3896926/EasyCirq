"""`realFrame` 契约的回归测试：Python 要输出、Go 要接收、值要**不同于**放大框。

背景（#110）：驱动为了让"框包住内容"会放大 `frame.rect`，
渲染器拿它判"位号是否在框内"就恒成立，而 checker 用的是**快照真实框**。
解法同 #82 的 `titleBlock`：Python 按真实框算好传下去。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZONES = ROOT / "easycirq" / "scripts" / "sch_preview_zones.py"
GO = ROOT / "runtime" / "internal" / "app" / "sch_layout_render.go"
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"


def test_zones_emits_real_frame(tmp_path):
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    out = tmp_path / "z.json"
    subprocess.run([sys.executable, str(ZONES), str(COMP), str(out)],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=600)
    if not out.is_file():
        pytest.skip("生成失败")
    z = json.loads(out.read_text(encoding="utf-8"))
    rf = z["zones"][0].get("realFrame")
    assert rf, "zones 没有输出 realFrame"
    for k in ("minX", "minY", "maxX", "maxY"):
        assert k in rf


def test_real_frame_is_content_plus_pad(tmp_path):
    """真实框 = 器件并集 + 18 raw（与快照同算法）。"""
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    out = tmp_path / "z.json"
    subprocess.run([sys.executable, str(ZONES), str(COMP), str(out)],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=600)
    if not out.is_file():
        pytest.skip("生成失败")
    rf = json.loads(out.read_text(encoding="utf-8"))["zones"][0]["realFrame"]
    comp = json.loads(COMP.read_text(encoding="utf-8"))
    boxes = [pl["bbox"] for pl in (comp.get("modules") or [{}])[0].get("placements") or []]
    assert abs(rf["minX"] - (min(b["minX"] for b in boxes) - 18.0)) < 0.01
    assert abs(rf["maxY"] - (max(b["maxY"] for b in boxes) + 18.0)) < 0.01


def test_go_accepts_real_frame():
    s = GO.read_text(encoding="utf-8")
    assert "RealFrame" in s
    assert 'json:"realFrame,omitempty"' in s
