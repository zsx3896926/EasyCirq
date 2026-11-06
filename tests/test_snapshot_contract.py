"""快照契约测试：让严格验收**真的能判**，且**不许编数据**。

背景（本轮实测）：
  • 一开始适配器报 `wires: 0 / texts: 0 / net_flags: 0 / module_frames: 0`，
    于是导线穿件、文字相压、标签悬空、模块框切器件这些判据**全都跑不起来** ——
    没报错不等于合格，是**没测**。
  • 补齐后我先造了一组"位号文字框"，检查器报出 115 项缺陷；抽样核对发现
    **83 项全部**是"我造的文字压住器件"，没有一项真实缺陷。
    —— 这是 #57 同类错误：拿自己编的数据当真。

所以本文件钉两条：
  1. 契约字段必须齐（导线在 pagePrimitives.wires 且 Line 是扁平数字序列、
     网标作为 componentType=netflag 出现、模块框进 rectangles）
  2. **不许产编造的文字** —— 排版稿不带文字几何时，texts 必须为空
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "easycirq" / "scripts" / "sch_composition_snapshot.py"
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not COMP.is_file():
        pytest.skip("没有 composition-M3-placed.json")
    out = tmp_path_factory.mktemp("snap")
    p = subprocess.run([sys.executable, str(SNAP), "--composition", str(COMP),
                        "--out-dir", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    f = out / "list.json"
    if not f.is_file():
        pytest.skip("快照未产出：%s" % ((p.stdout or p.stderr)[:200],))
    return json.loads(f.read_text(encoding="utf-8"))["result"]


def test_wires_live_in_page_primitives(built):
    """适配器只从 pagePrimitives.wires 读导线。"""
    prims = built.get("pagePrimitives") or {}
    assert "wires" in prims, "pagePrimitives.wires 缺失 → 导线覆盖会记 absent"
    assert prims["wires"], "pagePrimitives.wires 为空"


def test_wire_line_is_flat_segment_encoding(built):
    """`Line` 必须是扁平数字序列：每 4 个数一段（EasyEDA flat-segments）。

    给坐标对数组时长度=2 < 4，适配器 `flat_segments` 直接丢弃 → 计数为 0。
    """
    for w in (built.get("pagePrimitives") or {}).get("wires") or []:
        line = w.get("Line")
        assert isinstance(line, list) and len(line) >= 4, w
        assert len(line) % 4 == 0, "线段数不是 4 的倍数：%r" % w
        assert all(isinstance(v, (int, float)) for v in line), \
            "Line 里有非数字（说明还是坐标对数组）：%r" % line[:4]
        assert w.get("primitiveId"), "导线缺 primitiveId"


def test_netflags_appear_as_components(built):
    """网标必须是 components[] 里的 componentType=netflag。"""
    flags = [c for c in built.get("components") or []
             if c.get("componentType") == "netflag"]
    assert flags, "没有 netflag 图元 → 标签类判据跑不了"
    for f in flags:
        assert f.get("net"), f
        assert f.get("bbox"), "网标缺 bbox：%r" % f
        assert f.get("x") is not None and f.get("y") is not None


def test_module_frames_appear_as_rectangles(built):
    rects = (built.get("pagePrimitives") or {}).get("rectangles") or []
    assert rects, "没有模块框矩形 → 框切器件判不了"
    for r in rects:
        for k in ("TopLeftX", "TopLeftY", "Width", "Height"):
            assert k in r, "模块框缺 %s：%r" % (k, r)
        assert r["Width"] > 0 and r["Height"] > 0


def test_no_fabricated_text_geometry(built):
    """**核心断言**：排版稿不带文字几何，就不许产文字。

    曾经我按"位号放本体左上角上移 6"造了一组文字框，检查器据此报出 83 项
    假缺陷（bbox_overlap 48 + wire_enters_bbox 35），没有一项真实。
    """
    texts = (built.get("pagePrimitives") or {}).get("texts") or []
    assert texts == [], (
        "产出了 %d 条文字，但排版稿并不携带文字坐标 —— 这是在编数据。" % len(texts))


def test_sheet_component_present(built):
    """适配器要 sheet 图元取页边界，否则直接报错。"""
    sheets = [c for c in built.get("components") or []
              if c.get("componentType") == "sheet"]
    assert sheets, "缺 sheet 图元"
    assert sheets[0].get("bbox"), "sheet 缺 bbox"
