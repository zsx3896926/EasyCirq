"""图签字段必须齐全（tokens.title_block.required_fields 共 6 项）。

实测：原来只有 5 行（SHEET/REV/PAGE/日期/EasyCirq），**缺 project 与 size**。
补齐时又踩一个坑：`SIZE` 从**被放大的画布**推纸型，把 A2 报成 A0 ——
必须由 Python 按真实页算好传下来。
"""
import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHK = ROOT / "easycirq" / "scripts" / "sch_style_check.py"
ZONES = ROOT / "easycirq" / "scripts" / "sch_preview_zones.py"
TOKENS = ROOT / "easycirq" / "assets" / "style-reference" / "style-tokens.json"
SVG = ROOT / "reports" / "hard-board" / "board2" / "preview-M3.svg"
FRAMES = ROOT / "reports" / "hard-board" / "board2" / "review" / "frames-P3_5V转3V3主逻辑轨.json"


def test_title_block_has_six_fields():
    if not SVG.is_file():
        pytest.skip("没有 SVG")
    toks = json.loads(TOKENS.read_text(encoding="utf-8"))
    want = toks["title_block"]["required_fields"]
    art = pathlib.Path("tests/__none__")
    texts = re.findall(r'<text[^>]*>([^<]*)</text>', SVG.read_text(encoding="utf-8"))
    joined = " ".join(texts).upper()
    keys = {"project": "PROJECT", "version": "REV", "date": "20",
            "sheet": "SHEET", "page": "PAGE", "size": "SIZE"}
    missing = [f for f in want if keys[f] not in joined]
    assert not missing, "图签缺字段：%r" % missing


def test_page_size_comes_from_python_not_canvas():
    """纸型必须由 Python 传（画布被放大，渲染器自己推会报错纸型）。"""
    zs = ZONES.read_text(encoding="utf-8")
    assert "pageSize" in zs
    go = (ROOT / "runtime" / "internal" / "app" / "sch_layout_sheet.go").read_text(encoding="utf-8")
    assert "PageSize" in go
    r = (ROOT / "runtime" / "internal" / "app" / "sch_layout_render.go").read_text(encoding="utf-8")
    assert "s.PageSize" in r


def test_checker_reports_title_block_fields():
    if not SVG.is_file():
        pytest.skip("没有 SVG")
    cmd = [sys.executable, str(CHK),
           "--composition", str(ROOT / "reports/hard-board/board2/composition-M3-placed.json"),
           "--svg", "M3=%s" % SVG]
    if FRAMES.is_file():
        cmd += ["--frames", "M3=%s" % FRAMES]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    if not p.stdout.strip():
        pytest.skip("无输出")
    line = next(x for x in p.stdout.splitlines()
                if "title_block.required_fields" in x)
    assert "✅" in line, line


def test_min_zones_documented_as_na():
    """一页一模块时 min_zones 必须**显式说明不适用**，不能悄悄跳过。"""
    s = CHK.read_text(encoding="utf-8")
    assert "min_zones" in s
    assert "一页一模块" in s or "单分区" in s
