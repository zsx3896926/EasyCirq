"""相位的守卫：把"检测到"变成"拒绝"。

这个模块的全部价值就是**会拒绝**。所以每条测试都在证明一次拒绝，
而不是证明一次显示。
"""
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "phase.py"


def load_mod():
    spec = importlib.util.spec_from_file_location("phase_mod", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("EASYCIRQ_PHASE_DIR", str(tmp_path))
    return load_mod()


def test_only_pass_releases(mod):
    """pass 放行；fail / blocked / pending / unknown / stale 一律不放行。"""
    assert mod.is_release(mod.PASS)
    for v in (mod.FAIL, mod.BLOCKED, mod.PENDING, mod.UNKNOWN, mod.STALE):
        assert not mod.is_release(v), f"{v} must not release"


def test_enforced_gate_not_run_blocks(mod):
    """有门但没跑 = NOT RUN = 阻塞。这是本目标的核心承诺。"""
    d = {"phase": "S4", "evidence": {}}
    assert mod.evidence_state(d, "S5", "fp1") == mod.PENDING
    bad = mod.blockers(d, "DELIVER", "fp1")
    assert ("S5", mod.PENDING) in bad, bad


def test_unenforced_phase_does_not_block(mod):
    """还没接门的相位不阻塞——否则只接了 S5 时整条流程一步推不动。"""
    d = {"phase": "S0", "evidence": {}}
    assert mod.evidence_state(d, "S1", "fp") == mod.UNENFORCED
    assert mod.blockers(d, "S1", "fp") == []


def test_phase_can_advance_through_unenforced_phases(mod, tmp_path, monkeypatch):
    """S0→S5 能正常走完（未接门的不拦），但 S5→S6 会被 pending 拦住。"""
    monkeypatch.setenv("EASYCIRQ_PHASE_DIR", str(tmp_path))
    d = mod.load("p1")
    for _ in range(5):
        ok, msg, bad = mod.advance("p1", d, "fp")
        assert ok, msg
    assert d["phase"] == "S5"
    ok, msg, bad = mod.advance("p1", d, "fp")
    assert not ok, "S5 gate is NOT RUN; must not advance to S6"
    assert ("S5", mod.PENDING) in bad


def test_evidence_goes_stale_when_the_board_changes(mod):
    """板子改了，旧证据自动作废——换机器/过一夜都不能假装跑过了。"""
    d = {"phase": "S5",
         "evidence": {"S5": {"verdict": mod.PASS, "fingerprint": "aaaa"}}}
    assert mod.evidence_state(d, "S5", "aaaa") == mod.PASS
    assert mod.evidence_state(d, "S5", "bbbb") == mod.STALE
    bad = mod.blockers(d, "DELIVER", "bbbb")
    assert ("S5", mod.STALE) in bad, "stale evidence must block"


def test_blocked_verdict_blocks_just_like_fail(mod):
    """`blocked`（检查器没跑成）不是通过。这是 sch gate 三态判词的延续。"""
    d = {"phase": "S5",
         "evidence": {"S5": {"verdict": mod.BLOCKED, "fingerprint": "fp"}}}
    assert mod.blockers(d, "DELIVER", "fp") == [("S5", mod.BLOCKED)]


def test_history_records_overrides(mod):
    """强制设置必须留痕——否则"跳步"就不可查了。"""
    d = mod.load("p2")
    mod.save("p2", d)
    d["phase"] = "S6"
    d.setdefault("history", []).append({"from": "S0", "to": "S6", "by": "set (override)"})
    mod.save("p2", d)
    again = mod.load("p2")
    assert any(h.get("by", "").startswith("set") for h in again["history"])


# ── CLI 层：退出码才是"强制"的落点 ───────────────────────────────────
def _cli(tmp_path, *args):
    import os
    env = {**os.environ, "EASYCIRQ_PHASE_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, env=env)


def test_cli_advance_on_unrun_gate_exits_nonzero(tmp_path):
    p = _cli(tmp_path, "set", "S5", "--project", "x")
    assert p.returncode == 0, p.stderr
    p = _cli(tmp_path, "advance", "--project", "x")
    assert p.returncode != 0, (
        "S5 没跑门就推进成功了——那就只是显示，不是强制\n" + p.stdout)


def test_cli_show_marks_unenforced_separately(tmp_path):
    p = _cli(tmp_path, "show", "--project", "x")
    out = p.stdout
    assert "未接门" in out
    assert "NOT RUN（阻塞）" in out, "有门没跑必须显眼标出"
    assert "已接门：S5" in out


def test_cli_run_on_unwired_phase_exits_nonzero(tmp_path):
    p = _cli(tmp_path, "run", "S1", "--project", "x")
    assert p.returncode != 0, "没接门的相位跑出 0，会被当成通过"
