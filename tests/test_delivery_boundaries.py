"""守一条：交付文档必须写明「真实模型未验」。

这不是"多写一句话"，是让客户在交付清单上看得见——
埋在某份参考文档的第十节里等于没写。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCAL = ROOT / "easycirq" / "references" / "enterprise-local.md"
RUN = ROOT / "easycirq" / "references" / "harness-run.md"


def test_local_delivery_lists_known_boundaries():
    s = LOCAL.read_text(encoding="utf-8")
    assert "已知交付边界" in s, "本地交付说明里没有「已知交付边界」这一节"
    for must in ("真实模型没有端到端跑过", "自动布线不能交付",
                 "不做账号体系", "只支持嘉立创 EDA"):
        assert must in s, f"边界清单缺 {must!r}"


def test_boundary_says_it_is_a_limitation_not_a_todo():
    """必须写清这是「没做到」而不是「待办」，否则会被当成排期项。"""
    s = LOCAL.read_text(encoding="utf-8")
    assert "不是待办" in s
    assert "交付清单" in s


def test_boundary_gives_the_command_to_close_it():
    """给出补验的方法，客户/同事才能自己关掉这条。"""
    s = LOCAL.read_text(encoding="utf-8")
    i = s.find("真实模型未验")
    tail = s[i:i + 2500]
    assert "easycirq run --goal" in tail
    assert "--endpoint" in tail


def test_harness_doc_states_why_it_cannot_run_here():
    s = RUN.read_text(encoding="utf-8")
    assert "交付边界" in s
    assert "全部为空" in s, "没写清哪些 key 变量是空的"
    assert "不是没跑" in s


def test_boundary_names_what_was_actually_verified():
    """写边界的同时要说清已经验了什么，否则读起来像什么都没做。"""
    s = LOCAL.read_text(encoding="utf-8")
    assert "tools: 5" in s
    assert "工具结果确实回灌进了对话" in s
