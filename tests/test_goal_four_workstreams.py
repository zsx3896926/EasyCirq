"""四线目标的守劀：基线钉住、顺序有理由、NOT RUN 纪律在。

这份文档是"要做什么"的契约，不许以后悄悄放宽。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "goal-four-workstreams.md"


def test_goal_covers_the_four_workstreams():
    s = DOC.read_text(encoding="utf-8")
    for tag in ("A｜规模天花板", "B｜剩余 34% 时间", "D｜Python 依赖",
                "E｜历史工程 → 规则"):
        assert tag in s, f"缺 {tag}"


def test_each_workstream_has_end_state_gates_and_refusals():
    s = DOC.read_text(encoding="utf-8")
    # 每条都要有"终态"、"判据"、"明确不做"
    assert s.count("### 终态") >= 3, "有工作流缺终态"
    assert s.count("### 判据") >= 3, "有工作流缺判据"
    assert s.count("### 明确不做") >= 3, "有工作流缺「不做」"


def test_goal_pins_the_baseline_shas():
    doc = DOC.read_text(encoding="utf-8")
    store = json.loads((ROOT / "easycirq/scripts/layout/.bench/equivalence.json")
                       .read_text(encoding="utf-8"))
    for name, row in store["spots"].items():
        assert row["plan_sha256"] in doc, f"目标没钉住 {name} 的 plan SHA"


def test_goal_states_the_order_and_why():
    s = DOC.read_text(encoding="utf-8")
    assert "顺序建议" in s
    # 顺序必须给出理由，且明确指出与用户列举顺序不同
    assert "与用户列举顺序不同" in s
    assert "为什么这个位置" in s


def test_goal_keeps_the_not_run_discipline():
    s = DOC.read_text(encoding="utf-8")
    assert "NOT RUN" in s
    assert "不许外推" in s or "不外推" in s


def test_goal_records_that_python_rewrite_only_solves_half():
    """D 的关键判断：只重写 enterprise 解不了一半。这条不许被删。"""
    s = DOC.read_text(encoding="utf-8")
    assert "6,809" in s or "6809" in s, "没写离线判据闭包的行数"
    assert "那只是解一半" in s or "那只解一半" in s


def test_goal_records_the_e_evidence_base():
    """E 必须写明有真实素材可用，否则像是空想。"""
    s = DOC.read_text(encoding="utf-8")
    assert "25 份 DRC" in s
    assert "3,500 条违规" in s

def test_goal_doc_is_not_a_skill_reference():
    """目标是项目规划文档，不是方法论。

    放进 references/ 会带出断链（它引用 scale-curve.md / optimization-goal.md，
    那两个在 docs/ 下），而技能参考目录里的链接必须都能解析。
    """
    stale = ROOT / "easycirq" / "references" / "goal-four-workstreams.md"
    assert not stale.exists(), "目标文档又被放进技能参考目录了"
