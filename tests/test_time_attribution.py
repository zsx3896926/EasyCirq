"""时间归因与位图优化的守卫。

守两条：
  1. 等价性那三道基线 SHA 不许变（这是所有性能改动的前提）
  2. `_dirty_bitmap` 不许退回 `any(生成器)` 的写法 —— 那是 30% 的 route 时间
  3. 归因文档里的数字必须与实测一致，NOT RUN 不许被写成"通过"
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAY = ROOT / "easycirq" / "scripts" / "layout"
DOC = ROOT / "docs" / "time-attribution.md"


def test_equivalence_baseline_unchanged():
    """性能改动的底线：plan 必须逐字节相同。"""
    store = json.loads((LAY / ".bench" / "equivalence.json").read_text(encoding="utf-8"))
    assert store["spots"]["retrocam/frontier-i"]["plan_sha256"].startswith(
        "27a311f6f7f3332e")
    assert store["spots"]["selftest"]["plan_sha256"].startswith("d0c7ef5bdac4863c")


def test_dirty_bitmap_does_not_use_any_generator():
    """`any(o != net for o in owners)` 每格建一个生成器，实测占 route 的 30%。"""
    s = (LAY / "ec_layout.py").read_text(encoding="utf-8")
    i = s.find("def _dirty_bitmap")
    assert i > 0, "找不到 _dirty_bitmap"
    seg = s[i:i + 1600]
    # 只检查**代码**：函数的说明文字里会引用旧写法，那是故意的（解释为什么改）。
    # 按三引号切开，第 3 段才是 docstring 之后的代码。
    parts = seg.split('"""')
    code = parts[2] if len(parts) >= 3 else seg
    assert "any(" not in code, "倒退回了 any(生成器) 的写法"
    assert "<=" in code, "应该用集合包含判断（owners <= {net}）"


def test_dirty_bitmap_is_equivalent_to_the_old_predicate():
    """新判定必须与 `any(o != net for o in owners)` 完全等价。"""
    import sys
    sys.path.insert(0, str(LAY))
    import ec_layout

    W = H = 4
    net = "A"
    cases = [
        ({}, None),
        ({(1, 1): {"A"}}, None),                      # 只有自己 -> 不脏
        ({(1, 1): {"A", "B"}}, {(1, 1)}),             # 有别人 -> 脏
        ({(1, 1): set()}, None),                      # 空 owners -> 不脏
        ({(1, 1): {"B"}}, {(1, 1)}),
    ]
    for vb, want in cases:
        bm = ec_layout._dirty_bitmap(vb, net, W, H)
        if want is None:
            assert bm is None, f"{vb} 应该不脏，得到 {bm}"
        else:
            got = {(x, y) for y in range(H) for x in range(W) if bm[y * W + x]}
            assert got == want, f"{vb} 得到 {got}，期望 {want}"

    # 与旧谓词逐格比对（穷举几个组合）
    for owners in (set(), {"A"}, {"B"}, {"A", "B"}, {"A", "B", "C"}):
        old = any(o != net for o in owners)
        new = bool(owners) and not owners <= frozenset((net,))
        assert old == new, f"owners={owners}: 旧={old} 新={new}"


def test_doc_records_the_measured_numbers():
    s = DOC.read_text(encoding="utf-8")
    for must in ("24.2s", "13.9s", "42%", "5.65s", "41%", "0.34s"):
        assert must in s, f"归因文档缺实测值 {must}"
    assert "123.7s" in s, "缺交付档位耗时"
    assert "25 轮" in s


def test_doc_admits_both_self_corrections():
    """两处我自己推翻的判断必须留痕。"""
    s = DOC.read_text(encoding="utf-8")
    assert "混淆" in s, "没写清阶段 1 的超线性结论是混淆的"
    assert "截断" in s, "没写清 profile 函数名截断导致我一度判错"


def test_doc_has_not_run_section():
    s = DOC.read_text(encoding="utf-8")
    assert "## 六、NOT RUN" in s
