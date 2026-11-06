"""PNG 侧"文字相压"门禁的测试。

为什么必须有：此前几轮的真实缺陷（网标压引脚名、图签跑出纸外）都是
**放大看图**才发现的，检查器全绿。验收只看 SVG，**PNG 没有文字级门禁**。

本门禁把"用眼睛看"变成自动判据：记录每次 text() 的框，
排除页头/图签/标尺这些刻意叠放后，两两相交即为缺陷。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("rev", str(REVIEW))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_recording_draw_captures_text_boxes():
    s = REVIEW.read_text(encoding="utf-8")
    assert "class _RecordingDraw" in s
    assert "self.texts.append" in s


def test_count_text_overlaps_detects_synthetic_overlap():
    m = _load()
    texts = [("A", (100, 100, 140, 110)),
             ("B", (130, 100, 170, 110))]     # 横向叠 10px
    hits = m.count_text_overlaps(texts, 800, 600, None)
    assert len(hits) == 1
    assert hits[0]["overlap"][0] >= 9.0


def test_count_text_overlaps_ignores_chrome():
    m = _load()
    # 页头（y<85）与底部标尺带里的叠放不算缺陷
    texts = [("H1", (10, 10, 200, 30)), ("H2", (100, 10, 300, 30)),
             ("R1", (10, 580, 200, 596)), ("R2", (100, 580, 300, 596))]
    assert m.count_text_overlaps(texts, 800, 600, None) == []


def test_gate_fails_on_text_overlap():
    """源码层：相压 >0 必须把 verdict 判成 fail（不许只打印不拦）。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("文字相压并入质量结论")
    assert i > 0
    seg = s[i:i + 400]
    assert 'q["problems"].append' in seg
    assert 'q["verdict"] = "fail"' in seg
