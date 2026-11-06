"""图签归属必须被登记，否则图签自己会被报成缺陷。

实测（#83）：`title_block_owned` 是空数组时，那 5 条图签文字被
`overlaps_title_block` 报成 blocking（27→32），净效果是**加了图签反而更差**。

两个坑：
  1. 适配器按渲染行打标，id 命名空间与 page_texts 不一定对齐 → owned 为空
  2. 我第一版把"按几何补登记"写在**适配器执行之前**，那时 strict 文件还不存在，
     异常被 except 吞掉，静默无效

修法：在适配器**执行之后**，按"框心是否落在图签矩形内"补登记。
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "reports" / "hard-board" / "board2"
ACC = ROOT / "easycirq" / "scripts" / "sch_preview_accept.py"


@pytest.mark.parametrize("module", ["M3", "M4", "M5"])
def test_title_block_texts_are_owned(module):
    """图签矩形内的文字必须都登记为 owned，否则会被报成"压到图签"。"""
    strict = WORK / ("strict-%s-full.json" % module)
    zones = WORK / ("zones-%s.json" % module)
    if not strict.is_file() or not zones.is_file():
        pytest.skip("缺严格输入或 zones")
    doc = json.loads(strict.read_text(encoding="utf-8"))
    tb = (json.loads(zones.read_text(encoding="utf-8")).get("sheet") or {}).get("titleBlock")
    if not tb:
        pytest.skip("没有图签矩形")
    owned = set(doc.get("title_block_owned") or [])
    assert owned, "title_block_owned 是空的 —— 图签文字会被报成缺陷"
    inside = []
    for t in doc.get("texts") or []:
        b = t.get("bbox")
        if not b:
            continue
        cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        if tb["minX"] <= cx <= tb["maxX"] and tb["minY"] <= cy <= tb["maxY"]:
            inside.append(t["id"])
    missing = [i for i in inside if i not in owned]
    assert missing == [], "这些落在图签里的文字没登记：%r" % missing


def test_ownership_runs_after_adapter():
    """源码层：补登记必须在适配器执行**之后**（踩过：提前读文件被 except 吞掉）。"""
    s = ACC.read_text(encoding="utf-8")
    i_run = s.find("run_py(acmd)")
    i_own = s.find("按**几何**补登记图签归属")
    assert i_run > 0 and i_own > 0
    assert i_run < i_own, "补登记在适配器之前，会静默失效"


def test_no_title_block_findings_remain():
    """端到端：直接检查里不该再有 overlaps_title_block。"""
    import subprocess
    import sys
    home = pathlib.Path.home()
    checker = home / ".agents" / "skills" / "easycirq" / "scripts" / "sch_layout_check.py"
    strict = WORK / "strict-M3-full.json"
    if not checker.is_file() or not strict.is_file():
        pytest.skip("缺检查器或输入")
    p = subprocess.run([sys.executable, str(checker), str(strict), "--strict"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    if not p.stdout.strip():
        pytest.skip("检查器无输出")
    d = json.loads(p.stdout)
    codes = {f.get("code") for f in (d.get("blocking_findings") or [])}
    assert "overlaps_title_block" not in codes, "图签文字仍被报成压到图签"
    assert "wire_enters_title_block" not in codes
