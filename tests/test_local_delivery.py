"""本地化交付的守卫。

钉住三件事：
  1. 讲服务端/账号/网关的文档必须带「未采用」抬头（否则客户会以为要部署服务端）
  2. 现行接入文档必须存在，且写清「不需要服务端 / 不需要预装 Python」
  3. SKILL.md 指过去的入口是本地那份，不是未采用的那份
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "easycirq" / "references"
DOCS = ROOT / "docs"

# 讲 B/S 的文档：必须标明未采用
BS_DOCS = [
    REFS / "enterprise-deployment.md",
    REFS / "enterprise-accounts-plan.md",
    REFS / "enterprise-llm-design.md",
    DOCS / "enterprise-deployment.md",
    DOCS / "enterprise-accounts-plan.md",
    DOCS / "enterprise-llm-design.md",
]

LOCAL = REFS / "enterprise-local.md"


def test_bs_docs_are_marked_not_adopted():
    for p in BS_DOCS:
        if not p.is_file():
            continue
        s = p.read_text(encoding="utf-8")
        # 抬头 600 字符内必须出现标记
        head = s[:600]
        assert "本方案未采用" in head, f"{p.name} 没标「未采用」，客户会以为要部署服务端"
        assert "enterprise-local.md" in head or "本地交付说明" in head, (
            f"{p.name} 没指向现行接入文档")


def test_local_delivery_doc_exists_and_says_local():
    assert LOCAL.is_file(), "没有《本地交付说明》"
    s = LOCAL.read_text(encoding="utf-8")
    for must in ("不部署服务端", "不需要预装 Python", "ws://127.0.0.1:23111",
                 "EASYCIRQ_KNOWLEDGE_DIR", "本机"):
        assert must in s, f"本地交付说明缺 {must!r}"


def test_local_doc_refuses_to_promise_a_finished_board():
    """不替你自动画完一块板——这条必须写在文档里，不能只在我脑子里。"""
    s = LOCAL.read_text(encoding="utf-8")
    assert "不替你自动画完一块板" in s
    assert "clearance 146" in s, "没给出我们自己的样板板失败的数字"


def test_local_doc_forbids_auto_adoption_of_candidates():
    s = LOCAL.read_text(encoding="utf-8")
    assert "必须人审" in s
    assert "永不标 pass" in s or "不标 pass" in s


def test_skill_points_at_the_local_doc():
    sk = (ROOT / "easycirq" / "SKILL.md").read_text(encoding="utf-8")
    assert "enterprise-local.md" in sk, "SKILL.md 没有指向本地交付说明"


def test_no_doc_claims_a_server_is_required():
    """现行文档里不许出现「需要先部署服务端」这类口径。

    只查 references/，且排除已标「未采用」的。
    """
    bad = []
    for p in REFS.glob("*.md"):
        s = p.read_text(encoding="utf-8")
        if "本方案未采用" in s[:600]:
            continue
        for pat in ("必须先部署服务端", "需要一台服务器", "部署服务器后才能"):
            if pat in s:
                bad.append((p.name, pat))
    assert not bad, f"这些现行文档还在说要服务端：{bad}"

def test_status_docs_mark_cancelled_items_as_cancelled():
    """「账号体系未交付」现在是**已取消**，不是待办。

    不写清的话，这份文档会一直被当成缺口去排期。
    """
    for rel in ("docs/known-failures.md", "docs/delivery-acceptance.md",
                "docs/delivery-gap.md"):
        p = ROOT / rel
        if not p.is_file():
            continue
        head = p.read_text(encoding="utf-8")[:700]
        assert "2026-11 状态更正" in head, f"{rel} 没把账号体系标成已取消"
        assert "不再是待办缺口" in head, f"{rel} 没写清它不是待办"


def test_discovery_lists_what_is_no_longer_asked():
    """discovery 是现行流程，不能整份作废，但要把作废的问题列出来。"""
    p = REFS / "enterprise-discovery.md"
    s = p.read_text(encoding="utf-8")
    head = s[:1200]
    assert "改纯本地交付" in head
    for must in ("账号体系", "B1 / B3", "D1", "A2b"):
        assert must in head, f"作废清单缺 {must}"
    # 仍然必须问的那一条要突出
    assert "A3" in head and "结构化网表" in head


def test_demo_marks_the_server_scene_as_not_adopted():
    p = REFS / "enterprise-demo.md"
    s = p.read_text(encoding="utf-8")
    assert "本幕不采用" in s, "演示脚本里服务端那一幕没标不采用"
    assert "不要照做" in s
