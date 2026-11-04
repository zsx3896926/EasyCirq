"""规模墙的守卫。

三条纪律：
  1. 预检必须在**动手之前**拒绝，且说清"什么都没写"
  2. 预检不许静默降级、不许偷偷降精度
  3. "明确不做换缓冲"这个结论必须带数字留在文档里（否则以后有人会重做一遍）
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAY = ROOT / "easycirq" / "scripts" / "layout"
DOC = ROOT / "docs" / "scale-wall.md"
sys.path.insert(0, str(LAY))


def test_guard_constants_and_defaults():
    import ec_layout

    assert ec_layout.DEFAULT_MAX_NODES >= 100_000_000
    assert ec_layout.BYTES_PER_NODE > 0
    # 默认上限乘上每节点字节数，应该落在 16 GB 量级
    gb = ec_layout.DEFAULT_MAX_NODES * ec_layout.BYTES_PER_NODE / 1e9
    assert 10 < gb < 25, f"默认上限换算成 {gb:.1f} GB，不合理"


def test_guard_refuses_before_allocating(monkeypatch):
    """超限必须在 route 入口就抛，且**什么都没写**。"""
    import ec_layout

    class B:
        w, h = 5000, 5000

    monkeypatch.setenv("EASYCIRQ_MAX_NODES", "1000")
    with pytest.raises(MemoryError) as ei:
        ec_layout.check_scale(B(), 4)
    msg = str(ei.value)
    for want in ("nodes", "limit", "Nothing was routed and no plan was written",
                 "EASYCIRQ_MAX_NODES"):
        assert want in msg, f"报错缺 {want!r}：{msg}"
    # 报了节点数与估算内存
    assert "5000 x 5000" in msg
    assert "GB" in msg


def test_guard_passes_when_under_the_limit(monkeypatch):
    import ec_layout

    class B:
        w, h = 10, 10

    monkeypatch.setenv("EASYCIRQ_MAX_NODES", "100000")
    assert ec_layout.check_scale(B(), 4) == 400


def test_guard_env_override_and_bad_values(monkeypatch):
    import ec_layout

    monkeypatch.setenv("EASYCIRQ_MAX_NODES", "54321")
    assert ec_layout.max_nodes() == 54321

    # 非数字 / 非正数 → 退回默认，不崩
    for bad in ("abc", "0", "-5", ""):
        monkeypatch.setenv("EASYCIRQ_MAX_NODES", bad)
        assert ec_layout.max_nodes() == ec_layout.DEFAULT_MAX_NODES, bad


def test_route_calls_the_guard_first(monkeypatch):
    """route() 一进来就要查——不是等搜索跑起来才发现。"""
    import ec_layout

    seen = {}
    real = ec_layout.check_scale

    def spy(board, layers):
        seen["called"] = (board.w, board.h, layers)
        raise MemoryError("stopped by test")

    monkeypatch.setattr(ec_layout, "check_scale", spy)

    class B:
        w, h = 7000, 7000

    with pytest.raises(MemoryError):
        ec_layout.route(B(), iters=1, layers=2)
    assert seen.get("called") == (7000, 7000, 2), "route 没先调用预检"


def test_doc_keeps_the_numbers_that_justify_not_doing_it():
    s = DOC.read_text(encoding="utf-8")
    for must in ("38%", "62%", "9%", "7,027 MB", "28 GB", "127 字节/节点"):
        assert must in s, f"规模墙文档缺 {must}"
    assert "NOT RUN" in s
    # 必须明确写出"不做"，否则以后会有人重做一遍
    assert "明确不做" in s


def test_doc_has_the_customer_facing_sentence():
    s = DOC.read_text(encoding="utf-8")
    assert "给客户的一句话" in s
    assert "不会跑到一半莫名崩掉" in s


def test_equivalence_baseline_still_holds():
    """预检不许改变正常路径的产物。"""
    store = json.loads((LAY / ".bench" / "equivalence.json").read_text(encoding="utf-8"))
    assert store["spots"]["retrocam/frontier-i"]["plan_sha256"].startswith(
        "27a311f6f7f3332e")
