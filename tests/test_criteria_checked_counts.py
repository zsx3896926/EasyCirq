"""每条 PASS 判据必须写明**受检对象数量**，否则无法区分两种 PASS：

  · 检查过了，没有缺陷
  · 根本没有对象可查（#116 那次"0 穿线"就是这种空测量）

此前 12 条判据里只有 2 条能证明自己查过东西，其余全是 `count=0` 无说明。
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "reports" / "hard-board" / "board2"
ACC = ROOT / "easycirq" / "scripts" / "sch_layout_acceptance.py"


def test_annotate_helper_exists():
    s = ACC.read_text(encoding="utf-8")
    assert "_annotate_checked" in s
    assert "_population" in s


def test_every_pass_has_checked_counts():
    p = WORK / "acceptance-M3.json"
    if not p.is_file():
        pytest.skip("没有验收产物")
    d = json.loads(p.read_text(encoding="utf-8"))
    missing = [c["title"] for c in d["criteria"]
               if c["status"] == "PASS" and not c.get("checked")]
    assert not missing, "这些 PASS 没有受检数：%s" % missing


def test_checked_counts_are_positive():
    """受检数必须 > 0 —— 0 就等于"没查"。"""
    p = WORK / "acceptance-M3.json"
    if not p.is_file():
        pytest.skip("没有验收产物")
    d = json.loads(p.read_text(encoding="utf-8"))
    for c in d["criteria"]:
        if c["status"] != "PASS" or not c.get("checked"):
            continue
        assert any(v > 0 for v in c["checked"].values()), \
            "%s 的受检数全为 0" % c["title"]


def test_detail_says_what_was_checked():
    p = WORK / "acceptance-M3.json"
    if not p.is_file():
        pytest.skip("没有验收产物")
    d = json.loads(p.read_text(encoding="utf-8"))
    row = next(c for c in d["criteria"] if c["id"] == "B_text_occlusion")
    assert row["status"] == "PASS"
    assert any("已查" in x for x in (row.get("detail") or []))
