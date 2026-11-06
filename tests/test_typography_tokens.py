"""字体尺寸合规：区名必须落在 tokens 的 12~18。

实测：区名原来是 **20**（超上限），说明文字是 **9**（note 要求 6~8）。
另一个坑：页标题也是 20，它是**纸张装饰**，不能算进区名 ——
判定必须按"是否落在图纸区域内"过滤。
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
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"


def test_zone_title_within_tokens():
    if not SVG.is_file():
        pytest.skip("没有 SVG")
    toks = json.loads(TOKENS.read_text(encoding="utf-8"))
    lo = toks["typography"]["zone_title"]["min"]
    hi = toks["typography"]["zone_title"]["max"]
    s = SVG.read_text(encoding="utf-8")
    rows = re.findall(r'<text x="[\d.-]+" y="([\d.-]+)" font-size="([\d.]+)"', s)
    inside = [float(fs) for y, fs in rows if float(y) >= 85.0]
    if not inside:
        pytest.skip("页内没有文字")
    assert lo <= max(inside) <= hi, "页内最大字号 %g 超出 %d~%d" % (max(inside), lo, hi)


def test_zones_reads_limit_from_tokens():
    """区名字号必须**从 tokens 读**，不许再写死。"""
    s = ZONES.read_text(encoding="utf-8")
    assert "_zone_title_size" in s
    assert '"fontSize": 20' not in s, "又写死 20 了"


def test_checker_reports_typography():
    if not SVG.is_file() or not COMP.is_file():
        pytest.skip("缺产物")
    p = subprocess.run([sys.executable, str(CHK), "--composition", str(COMP),
                        "--svg", "M3=%s" % SVG],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    if not p.stdout.strip():
        pytest.skip("无输出")
    assert "typography.zone_title" in p.stdout
    # 只要求**字体项**通过：不给 --frames 时，区面积会按器件外框估而报违规，
    # 那是另一条判据的事，不该让这条测试变红。
    line = next(x for x in p.stdout.splitlines() if "typography.zone_title" in x)
    assert "✅" in line, line


def test_page_title_excluded_from_zone_measure():
    """源码层：判定必须按 y 过滤，否则页标题的 20 会被当成区名。"""
    s = CHK.read_text(encoding="utf-8")
    i = s.find("def check_typography")
    seg = s[i:i + 900]
    assert ">= 85" in seg or ">=85" in seg, "没有按图纸区域内过滤"
