"""技能自带的 `sch_text_audit --strict` 必须真正进链并跑通。

目标点名要求以它为基准。此前预览链只跑了 `sch_layout_check`，
`sch_text_audit` 从没跑过 —— 这是目标里的一处实际缺口。

接进去要满足它的输入结构：
    {"count": N, "items": [...], "unmeasured": [], "coverage": {类: true}}
缺 `count` 会报 `count must match items`，缺 `unmeasured` 会报 `array required`。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "reports" / "hard-board" / "board2"
ACC = ROOT / "easycirq" / "scripts" / "sch_preview_accept.py"
SK = pathlib.Path.home() / ".agents" / "skills" / "easycirq" / "scripts"


def test_chain_runs_text_audit():
    s = ACC.read_text(encoding="utf-8")
    assert "sch_text_audit.py" in s, "验收链没调用技能的文字审计"
    assert "L_text_audit" in s, "审计结论没进判据"


def test_visible_has_audit_shape():
    f = WORK / "visible-M3.json"
    if not f.is_file():
        pytest.skip("没有 visible 产物")
    d = json.loads(f.read_text(encoding="utf-8"))
    v = d.get("visible") or d
    assert isinstance(v.get("count"), int)
    assert v["count"] == len(v.get("items") or [])
    assert isinstance(v.get("unmeasured"), list)
    assert isinstance(v.get("coverage"), dict)


def test_skill_audit_reports_clear():
    f = WORK / "visible-M3.json"
    if not f.is_file() or not (SK / "sch_text_audit.py").is_file():
        pytest.skip("缺产物或技能脚本")
    r = subprocess.run([sys.executable, str(SK / "sch_text_audit.py"), str(f),
                        "--strict"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    assert r.returncode == 0, (r.stdout or r.stderr)[-300:]
    assert '"clear"' in (r.stdout or "")


def test_acceptance_has_text_audit_row():
    """磁盘产物里必须出现这条判据。"""
    p = WORK / "acceptance-M3.json"
    if not p.is_file():
        pytest.skip("没有验收产物")
    d = json.loads(p.read_text(encoding="utf-8"))
    row = [c for c in d["criteria"] if c["id"] == "L_text_audit"]
    assert row, "产物里没有文字审计判据"
    assert row[0]["status"] in ("PASS", "FAIL", "NOT RUN")
