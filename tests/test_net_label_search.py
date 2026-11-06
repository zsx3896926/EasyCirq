"""网标落点搜索的两条补强。

1. **远距候选**：网标落在三线交汇处时，近处候选全被占 → 往更远处放（26/36/48px）。
2. **阻挡清单用"所有已画文字"**：只列网标框和位号框会漏掉**已画的引脚名** ——
   实测远距候选躲开导线后压到了 `PGND`/`SGND`。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def test_far_candidates_exist():
    s = REVIEW.read_text(encoding="utf-8")
    assert "远距候选" in s
    i = s.find("远距候选")
    seg = s[i:i + 500]
    assert "for far in" in seg and "26" in seg


def test_blockers_use_all_drawn_texts():
    s = REVIEW.read_text(encoding="utf-8")
    assert s.count('blockers = [b for _t, b in getattr(d, "texts", [])]') == 2, \
        "位号与网标两处搜索都要用所有已画文字做阻挡"


def test_net_label_search_avoids_pin_names():
    """源码层：阻挡清单里不能只有 flag_boxes / ref_boxes。"""
    s = REVIEW.read_text(encoding="utf-8")
    assert "blockers = list(flag_boxes) + list(ref_boxes)" not in s, \
        "仍在使用不完整的阻挡清单（会漏引脚名）"
