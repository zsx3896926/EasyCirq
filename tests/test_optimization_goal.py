"""优化目标的守卫：目标文档里的门禁基线不许被悄悄改动。

这份文档是"要做什么"的契约。里面的等价性基线 SHA 是硬约束——
改了它们等于放宽门禁，所以用测试钉住。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "optimization-goal.md"
LAYOUT = ROOT / "easycirq" / "scripts" / "layout"


def test_goal_doc_exists_and_picks_one_direction():
    assert DOC.is_file(), "优化目标文档不见了"
    s = DOC.read_text(encoding="utf-8")
    assert "## 三、目标（一条）" in s, "没有明确选出一条目标"
    # 必须是"一条"，不是六个并列
    assert s.count("## 三、目标") == 1


def test_goal_pins_the_equivalence_baseline():
    """基线 SHA 必须与 .bench/equivalence.json 里记录的一致。"""
    import json
    doc = DOC.read_text(encoding="utf-8")
    store = LAYOUT / ".bench" / "equivalence.json"
    assert store.is_file(), "没有等价性基线，目标里的门禁无从谈起"
    rec = json.loads(store.read_text(encoding="utf-8"))["spots"]
    for name, row in rec.items():
        sha = row["plan_sha256"]
        assert sha in doc, f"目标文档没钉住 {name} 的基线 {sha[:16]}…"


def test_goal_states_what_it_does_not_do():
    s = DOC.read_text(encoding="utf-8")
    assert "明确不做" in s
    for must in ("打包", "搜索语义", "精度"):
        assert must in s, f"没写清不做 {must}"


def test_scale_numbers_match_the_code():
    """文档里的节点数与缓冲大小必须与代码的分配方式一致（8 字节 × 4 数组）。"""
    s = DOC.read_text(encoding="utf-8")
    pyx = (LAYOUT / "_astar_c.pyx").read_text(encoding="utf-8")
    # 代码里确实是 4 个 n_nodes×8 字节的数组
    for arr in ("_best", "_best_gen", "_came", "_came_gen"):
        assert arr in pyx, f"代码里没有 {arr}"
    assert "n_nodes = L * stride_l" in pyx, "节点数不再是 L*W*H"
    # 文档要写出这个算式
    assert "38.9 MB" in s
    assert "1.22M" in s or "1,216," in s


def test_goal_admits_the_earlier_arithmetic_error():
    """我先前把"面积 10×"当成"每维 10×"，文档里要留更正痕迹。"""
    s = DOC.read_text(encoding="utf-8")
    assert "更正一处我先前写错的估算" in s
