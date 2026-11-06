"""审图 PNG 的结点圆点：只画同网 ≥3 段交汇，跨网交叉绝不给点。

SVG 渲染器早就有 `class="junction"` 的圆点，注释写明"不能凭空造结点，
跨网交叉绝不给点"；但**审图 PNG 一个都没有** —— 而 PNG 才是拿去审的图。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def test_png_draws_junction_dots():
    s = REVIEW.read_text(encoding="utf-8")
    assert "结点圆点" in s, "PNG 渲染器没有结点圆点"
    assert "ellipse" in s


def test_junction_rule_is_same_net_only():
    """跨网交叉不许给点——那会让人以为两个网络连在一起。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("结点圆点")
    seg = s[i:i + 900]
    assert "同网" in seg or "跨网" in seg, "没写清只画同网"
    assert ">= 3" in seg or "≥3" in seg, "没有'≥3 段交汇'的门槛"


def test_junction_block_does_not_shadow_quality_param():
    """踩过的坑：循环变量取名 q，覆盖了 render() 的质量字典参数。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("结点圆点")
    seg = s[i:i + 900]
    assert "for q in" not in seg, "循环变量又用了 q，会覆盖质量字典"


def test_png_renderer_still_runs():
    """能跑通比规则正确更重要——这条防的是改完就崩。"""
    import subprocess
    import sys
    comp = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"
    if not comp.is_file():
        import pytest
        pytest.skip("没有排版稿")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = subprocess.run([sys.executable, str(REVIEW), "--composition", str(comp),
                            "--page-name", "t", "--out-dir", td],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1800)
        assert p.returncode == 0, (p.stdout or p.stderr)[-400:]
        assert (pathlib.Path(td) / "t.png").is_file()
