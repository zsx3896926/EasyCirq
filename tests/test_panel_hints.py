"""P1：证据详情（hints）、状态机语义、抽屉。

三条最要紧的：

1. **`stale` 真的会让证据失效**（A6）——板子改了，旧证据不许还算数。
2. **每个状态都有"下一步"的人话**，而且文案里不能有 Markdown 星号
   （面板用 textContent 渲染，`**x**` 会原样显示成星号）。
3. **面板的抽屉只是渲染 CLI 的 hints**，自己不生成任何判断。
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"
HTML = ROOT / "runtime" / "internal" / "app" / "panel" / "index.html"
sys.path.insert(0, str(SCRIPTS))


def _phase_mod():
    spec = importlib.util.spec_from_file_location("phase_mod", SCRIPTS / "phase.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── A6：板子变了，证据作废 ───────────────────────────────────────────
def test_stale_when_the_board_fingerprint_changes():
    """同一条证据，指纹对不上就必须是 stale —— 不许还算 pass。"""
    m = _phase_mod()
    d = {"evidence": {"S5": {"verdict": "pass", "fingerprint": "aaaa1111"}}}
    assert m.evidence_state(d, "S5", "aaaa1111") == "pass"
    assert m.evidence_state(d, "S5", "bbbb2222") == "stale"


def test_stale_is_not_release():
    """`stale` 绝对不能放行推进。"""
    m = _phase_mod()
    assert m.is_release("stale") is False
    assert m.is_release("pass") is True
    for bad in ("pending", "blocked", "fail", "unenforced"):
        assert m.is_release(bad) is False, bad


def test_missing_gate_and_unenforced_are_different_states():
    """有门没跑 = pending（阻塞）；没接门 = unenforced（不阻塞）。混了流程就走不动。"""
    m = _phase_mod()
    d = {"evidence": {}}
    assert m.evidence_state(d, "S5", "x") == "pending"
    assert m.evidence_state(d, "S0", "x") == "unenforced"


# ── hints：每个状态都说得出下一步 ───────────────────────────────────
def _hints_for(evidence, fp="fp1"):
    m = _phase_mod()
    d = {"phase": "S5", "evidence": evidence}
    states = {ph: m.evidence_state(d, ph, fp) for ph in m.PHASES}
    return m.build_hints(d, fp, states)


def test_every_phase_gets_a_hint():
    h = _hints_for({})
    assert set(h) == set(["S0", "S1", "S2", "S3", "S4", "S5", "S6", "DELIVER"])


@pytest.mark.parametrize("verdict", ["pass", "fail", "blocked"])
def test_hint_always_says_what_next(verdict):
    h = _hints_for({"S5": {"verdict": verdict, "fingerprint": "fp1"}})
    s5 = h["S5"]
    assert s5["state"] == verdict
    assert s5.get("next"), "状态 %s 没有 next 文案" % verdict


def test_blocked_hint_says_it_is_not_a_pass():
    """`blocked` 最容易被误读成"没问题"，文案必须明说。"""
    h = _hints_for({"S5": {"verdict": "blocked", "fingerprint": "fp1"}})
    assert "不等于通过" in h["S5"]["next"]
    assert h["S5"].get("howToFix"), "blocked 必须给一条可执行的补救命令"


def test_pending_hint_says_not_run():
    h = _hints_for({})
    assert "NOT RUN" in h["S5"]["next"] or "还没跑" in h["S5"]["next"]
    assert "phase run S5" in h["S5"]["howToFix"]


def test_stale_hint_tells_you_to_rerun():
    h = _hints_for({"S5": {"verdict": "pass", "fingerprint": "OLD"}}, fp="NEW")
    assert h["S5"]["state"] == "stale"
    assert "失效" in h["S5"]["next"]
    assert "phase run S5" in h["S5"]["howToFix"]


def test_deliver_hint_lists_the_four_preconditions():
    """DELIVER 没有"门"，说成"没有门"是错的——它有四条前置。"""
    h = _hints_for({})
    nxt = h["DELIVER"]["next"]
    for word in ("S5", "真实器件", "悬空引脚", "交付卡"):
        assert word in nxt, "DELIVER 的前置说明缺 %s：%s" % (word, nxt)


def test_hint_text_contains_no_markdown():
    """面板用 textContent 渲染，`**x**` 会原样显示成星号。"""
    for ev, fp in (({}, "fp1"),
                   ({"S5": {"verdict": "blocked", "fingerprint": "fp1"}}, "fp1"),
                   ({"S5": {"verdict": "pass", "fingerprint": "OLD"}}, "NEW")):
        blob = json.dumps(_hints_for(ev, fp), ensure_ascii=False)
        assert "**" not in blob, "hints 里还有 Markdown 星号：%s" % blob[:300]


def test_hints_carry_the_last_verdict_and_detail():
    h = _hints_for({"S5": {"verdict": "blocked", "fingerprint": "fp1",
                           "detail": "drc: native verdict BLOCKED"}})
    assert h["S5"]["lastVerdict"] == "blocked"
    assert "BLOCKED" in h["S5"]["lastDetail"]


# ── CLI 层：hints 必须出现在 phase show --json 里 ────────────────────
@pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")
def test_phase_show_json_exposes_hints(tmp_path):
    env = {**os.environ, "EASYCIRQ_PHASE_DIR": str(tmp_path)}
    p = subprocess.run([str(EXE), "phase", "show", "--project", "hintdemo", "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120, env=env)
    i = (p.stdout or "").find("{")
    assert i >= 0, p.stderr[-600:]
    doc = json.loads((p.stdout or "")[i:])
    assert "hints" in doc, "phase show --json 没带 hints"
    assert len(doc["hints"]) == 8
    assert doc["hints"]["S5"]["state"] == "pending"


# ── 抽屉：面板只是渲染 hints，自己不判断 ────────────────────────────
def test_page_has_a_drawer_not_a_modal():
    """交互规则：不弹模态框打断，用侧滑抽屉。"""
    html = HTML.read_text(encoding="utf-8")
    assert 'id="drawer"' in html
    assert 'class="drawer"' in html
    assert "position:fixed" in html


def test_drawer_renders_hints_from_the_api_not_its_own_logic():
    """抽屉里的"下一步/怎么补"必须来自 snap.phase.hints。"""
    html = HTML.read_text(encoding="utf-8")
    assert "phase.hints" in html, "抽屉没读 CLI 的 hints"
    # 抽屉里不该出现任何状态判断的 if/else 分支
    drawer_js = html[html.find("function openDrawer"):html.find("function closeDrawer")]
    for forbidden in ('=== "pass"', '!== "pass"', 'state ==', "state === "):
        assert forbidden not in drawer_js, "抽屉里出现了状态判断：%s" % forbidden


def test_phase_cells_are_clickable():
    html = HTML.read_text(encoding="utf-8")
    assert "addEventListener(\"click\"" in html
    assert "openDrawer(" in html
