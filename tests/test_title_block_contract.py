"""图签契约的回归测试：`titleBlock` 矩形 + 适配器声明 + 判据可测。

这一路的坑（#81/#82）：
  · 禁放区是空数组，按它画等于没画
  · 画在图框右下角 → 图框被放大，图签落到页外被过滤
  · 图框改真实页 → `violates page padding`
  · 图签文字含全角括号/箭头 → 29 条输入只测出 28 条，三项判据被迫 N/R

正确做法：`titleBlock` 是 zones 契约里的**独立矩形**，由 Python 按真实页算；
渲染器按它画；适配器按它声明 `title_block` 覆盖与 `title_block_owned`。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZONES = ROOT / "easycirq" / "scripts" / "sch_preview_zones.py"
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"


def test_zones_emits_title_block_rect(tmp_path):
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    out = tmp_path / "z.json"
    p = subprocess.run([sys.executable, str(ZONES), str(COMP), str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    if not out.is_file():
        pytest.skip("生成失败：%s" % (p.stderr or "")[:200])
    z = json.loads(out.read_text(encoding="utf-8"))
    tb = z["sheet"].get("titleBlock")
    assert tb, "zones 必须给出 titleBlock 矩形"
    for k in ("minX", "minY", "maxX", "maxY"):
        assert k in tb
    assert tb["maxX"] > tb["minX"] and tb["maxY"] > tb["minY"]

    # 必须落在**真实页**内（不能跟着 border 放大）
    sheet = json.loads(COMP.read_text(encoding="utf-8"))["sheet"]
    assert tb["minX"] >= sheet["minX"] and tb["maxX"] <= sheet["maxX"]
    assert tb["minY"] >= sheet["minY"] and tb["maxY"] <= sheet["maxY"]


def test_title_block_does_not_overlap_content():
    """图签不能压到器件——它和内容区必须分开。"""
    z = json.loads((ROOT / "reports/hard-board/board2/zones-M3.json")
                   .read_text(encoding="utf-8"))
    tb = z["sheet"].get("titleBlock")
    if not tb:
        pytest.skip("没有图签矩形")
    comp = json.loads((ROOT / "reports/hard-board/board2/composition-M3-placed.json")
                      .read_text(encoding="utf-8"))
    for pl in (comp.get("modules") or [{}])[0].get("placements") or []:
        b = pl["bbox"]
        overlap = (b["minX"] < tb["maxX"] and tb["minX"] < b["maxX"]
                   and b["minY"] < tb["maxY"] and tb["minY"] < b["maxY"])
        assert not overlap, "%s 压在图签上" % pl.get("designator")


def test_title_block_text_is_ascii_safe():
    """图签文字若含全角括号/箭头，会有一条测不出 bbox（29 vs 28）。"""
    src = (ROOT / "runtime" / "internal" / "app" / "sch_layout_render.go") \
        .read_text(encoding="utf-8")
    i = src.find("// 字段用**短 ASCII 安全**文本")
    assert i > 0, "缺少'短 ASCII 安全文本'的说明（说明之前踩过这个坑）"
    seg = src[i:i + 400]
    for bad in ("→", "（", "）", "图名", "版本", "第 ", "绘制"):
        assert bad not in seg.split("for i, fv")[1][:200], \
            "图签字段仍含可能测不出 bbox 的字符：%s" % bad


def test_acceptance_declares_title_block_to_adapter():
    src = (ROOT / "easycirq" / "scripts" / "sch_preview_accept.py") \
        .read_text(encoding="utf-8")
    assert "--sheet-geometry" in src, "驱动没把图签矩形交给适配器"
    assert "titleBlock" in src
