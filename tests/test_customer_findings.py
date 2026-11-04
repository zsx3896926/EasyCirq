"""客户资料分析的守卫测试。

防的是：以后有人把"已答"改回"待问"，或把资料来源丢掉。
"""
import pytest
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FINDINGS = ROOT / "docs" / "enterprise-customer-findings.md"
DISCOVERY = ROOT / "docs" / "enterprise-discovery.md"
CORPUS = ROOT / "reports" / "customer-docs"


def test_findings_doc_exists_and_separates_known_from_unknown():
    s = FINDINGS.read_text(encoding="utf-8")
    assert "已确认的事实" in s, "没有分开「文档写了什么」和「还要问什么」"
    assert "还没答的问题" in s


def test_findings_records_answered_items_with_evidence():
    s = FINDINGS.read_text(encoding="utf-8")
    # 每条已答都必须能指到文档原文
    for must in ("allegro", "Protel2", "Electron", "MySQL 8.4.2",
                 "开放API与丰富的插件生态"):
        assert must in s, f"已答项缺依据：{must}"


def test_findings_flags_the_version_line_mismatch():
    """私有部署客户端 1.12.1 vs 公有专业版 4.1.78 —— 这条不齐会误判 A2。"""
    s = FINDINGS.read_text(encoding="utf-8")
    assert "1.12.1" in s and "4.1.78" in s
    assert "两条" in s and "版本线" in s


def test_findings_says_accounts_should_not_be_rebuilt():
    """核心结论：客户已有账号体系，自建会重复造轮子。"""
    s = FINDINGS.read_text(encoding="utf-8")
    assert "账号体系不该自建" in s
    assert "系统对接API接口文档" in s, "没指出该要哪份文档"


def test_discovery_marks_answered_items():
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "已答" in s, "接入清单没有标出已答项"
    assert ".enet" in s, "没把网表样本列为待要的东西"
    # 仍然要保留未答的标记，不能把没答的也标成已答
    assert "仍未答" in s or "未答" in s


def test_corpus_is_kept_for_traceability():
    """提取的纯文本要留档，否则以后无法核对结论。"""
    # 未跟踪的证据产物：全新 checkout 里不存在，与代码无关。
    # 产物在就跑真断言，不在就明确 skip（不伪装成通过）。
    if not (ROOT / "reports/customer-docs").exists():
        pytest.skip("缺少本地产物 reports/customer-docs（客户官方文档语料）；这是可再生的证据，不入库")
    files = list(CORPUS.glob("*.txt"))
    assert len(files) >= 5, f"客户资料文本只剩 {len(files)} 份"
    joined = "\n".join(f.read_text(encoding="utf-8") for f in files)
    # 几条关键原文
    assert "嘉立创EDA(专业版)私有部署" in joined
    assert "Protel2" in joined
