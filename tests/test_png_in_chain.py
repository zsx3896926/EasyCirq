"""审图 PNG 门禁必须**在验收链里**，不能只靠单独跑。

目标把"审图 PNG"列为交付物的一部分，但此前验收链只跑 SVG 那条线，
审图要另外执行 `sch_layout_review.py --gate` —— 很容易漏掉，
于是"图能不能读"这件事没有进最终结论。

现在它是一条正式判据：`K_png_readability`（审图 PNG 可读性）。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACC = ROOT / "easycirq" / "scripts" / "sch_preview_accept.py"
WORK = ROOT / "reports" / "hard-board" / "board2"


def test_chain_runs_review_gate():
    s = ACC.read_text(encoding="utf-8")
    assert "sch_layout_review.py" in s, "验收链没有调用审图"
    assert '"--gate"' in s or "'--gate'" in s, "审图没带 --gate"


def test_png_criterion_registered():
    s = ACC.read_text(encoding="utf-8")
    assert "K_png_readability" in s
    assert "审图 PNG 可读性" in s


def test_png_failure_blocks_verdict():
    """相压>0 必须能把总判拖成 BLOCKED。"""
    s = ACC.read_text(encoding="utf-8")
    i = s.find("K_png_readability")
    assert i > 0
    seg = s[i:i + 900]
    assert 'rep["verdict"] = "BLOCKED"' in seg


def test_acceptance_report_has_png_row():
    """真实运行产物里必须出现这条判据。"""
    import json
    p = WORK / "acceptance-M3.json"
    if not p.is_file():
        pytest.skip("没有验收产物")
    d = json.loads(p.read_text(encoding="utf-8"))
    ids = [c["id"] for c in d["criteria"]]
    assert "K_png_readability" in ids, ids
    c = next(x for x in d["criteria"] if x["id"] == "K_png_readability")
    assert c["status"] in ("PASS", "FAIL", "NOT RUN")
