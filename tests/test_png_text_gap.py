"""文字相压的两个进阶要求。

1. **最小间距**：只判"相交"会放过"贴边"——实测 `GND` 与 `L5` 不重叠，
   读起来却是 "GNDL5"。现在相邻 4px 内即算缺陷。
2. **多向候选**：位号默认在本体上方，被网标占了就往左/右/下/更高处找；
   4 个候选不够（L5 四向全占），扩到 7 个才找到空位。

这两条合起来，M3/M4/M5 的 PN G 门禁从"2 处缺陷"变成 **0**。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("rev2", str(REVIEW))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_touching_texts_count_as_collision():
    """贴边（间距 < 4px）也要算缺陷。"""
    m = _load()
    texts = [("GND", (100, 100, 140, 110)),
             ("L5", (142, 100, 160, 110))]      # 间距 2px < 4
    assert len(m.count_text_overlaps(texts, 800, 600, None)) == 1


def test_far_apart_texts_are_fine():
    m = _load()
    texts = [("GND", (100, 100, 140, 110)),
             ("L5", (200, 100, 218, 110))]      # 间距 60px
    assert m.count_text_overlaps(texts, 800, 600, None) == []


def test_min_gap_constant_exists():
    s = REVIEW.read_text(encoding="utf-8")
    assert "TEXT_MIN_GAP" in s


def test_designator_has_seven_candidates():
    """L5 四向全占，必须有多于 4 个候选才找得到空位。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("cand = [")
    j = s.find("]", s.find("(tx, ty - 26)", i))
    seg = s[i:j]
    assert seg.count("(tx") + seg.count("(px") >= 6, "候选太少：%r" % seg[:200]


def test_designator_search_uses_gap():
    """搜索判据要与门禁同口径（留间距），否则会挑到贴边位置。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("cand = [")
    seg = s[i:i + 2200]
    assert "TEXT_MIN_GAP" in seg
