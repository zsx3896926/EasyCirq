"""调色板对齐的回归测试：电源红 / 地蓝 / 信号黑。

实测违反（friction #94）：三类网标原来**同色**（`#176bc0`），
基准图靠颜色区分电源/地/信号，颜色是语义不是装饰。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SVG = ROOT / "reports" / "hard-board" / "board2" / "preview-M3.svg"
TOKENS = ROOT / "easycirq" / "assets" / "style-reference" / "style-tokens.json"
RENDER = ROOT / "runtime" / "internal" / "app" / "sch_layout_render.go"


def test_net_stroke_helper_exists():
    s = RENDER.read_text(encoding="utf-8")
    assert "func netStroke(" in s, "缺按网络取色的函数"
    assert "#CC0000" in s and "#0000CC" in s and "#000000" in s


def test_power_and_ground_are_distinct():
    """电源与地必须是**不同**颜色 —— 之前都是 #176bc0。"""
    if not SVG.is_file():
        pytest.skip("没有 SVG")
    s = SVG.read_text(encoding="utf-8")
    pairs = re.findall(r'class="marker-name"[^>]*fill="(#[0-9A-Fa-f]{6})"[^>]*>([^<]*)</text>', s)
    if not pairs:
        pytest.skip("没有网标文字")
    by_net = {}
    for col, net in pairs:
        by_net[net] = col.upper()
    power = [c for n, c in by_net.items() if n.startswith("+")]
    ground = [c for n, c in by_net.items() if n.upper() in ("GND", "AGND")]
    if power and ground:
        assert set(power) != set(ground), "电源与地同色：%r" % by_net
        assert set(power) == {"#CC0000"}, power
        assert set(ground) == {"#0000CC"}, ground


def test_signal_nets_are_black():
    if not SVG.is_file():
        pytest.skip("没有 SVG")
    s = SVG.read_text(encoding="utf-8")
    pairs = re.findall(r'class="marker-name"[^>]*fill="(#[0-9A-Fa-f]{6})"[^>]*>([^<]*)</text>', s)
    sig = [c.upper() for c, n in pairs
           if not n.startswith("+") and n.upper() not in ("GND", "AGND")]
    if sig:
        assert set(sig) == {"#000000"}, sig


def test_no_green_wires_left():
    """导线原来是 #07814d（绿，不在调色板）。"""
    s = RENDER.read_text(encoding="utf-8")
    assert "#07814d" not in s, "还有绿色导线"


def test_all_schematic_colors_in_palette():
    """图面语义色必须在调色板内（页面装饰色除外）。"""
    if not SVG.is_file():
        pytest.skip("没有 SVG")
    toks = __import__("json").loads(TOKENS.read_text(encoding="utf-8"))
    pal = {c.upper() for c in toks["palette"]["zone_border"]}
    for v in (toks["palette"]["text"] or {}).values():
        pal.add(v.upper())
    pal |= {c.upper() for c in toks["palette"].get("extra_allowed") or []}
    chrome = {"#F8FAFC", "#94A3B8", "#C74747", "#4A998E"}   # 页面装饰，不在 tokens 管辖
    s = SVG.read_text(encoding="utf-8")
    used = {c.upper() for c in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', s)}
    off = used - pal - chrome
    assert not off, "不在调色板内的颜色：%r" % sorted(off)
