"""DELIVER 前置条件的守卫：空板子、悬空引脚都不许"可交付"。

这两条都是**实测发现**的，不是设计时想到的：
  · 空板子让 `sch gate` trivially pass（没有可检查的问题）
  · 悬空引脚在默认非严格门下只是 warn，判词仍是 pass
两者都会让 DELIVER 放行不该放行的板子。
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "phase.py"


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("EASYCIRQ_PHASE_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("phase_mod2", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _at_s6_with_s5_pass(m, tmp_path):
    """造一个 S5 已 pass、当前在 S6 的状态。"""
    d = m.load("x")
    d["phase"] = "S6"
    d["evidence"] = {"S5": {"verdict": m.PASS, "fingerprint": "fp"}}
    m.save("x", d)
    return m.load("x")


def _stub_facts(m, monkeypatch, parts, floating):
    monkeypatch.setattr(m, "board_facts", lambda project: (parts, floating))


def test_empty_board_cannot_be_delivered(mod, tmp_path, monkeypatch):
    d = _at_s6_with_s5_pass(mod, tmp_path)
    _stub_facts(mod, monkeypatch, 0, 0)
    ok, msg, bad = mod.advance("x", d, "fp", "DELIVER")
    assert not ok
    assert "no parts" in msg
    assert ("PARTS", "empty") in bad


def test_floating_pins_block_delivery(mod, tmp_path, monkeypatch):
    """默认 sch gate 只把悬空引脚当 warn，所以 S5 会 pass —— 必须在这里拦住。"""
    d = _at_s6_with_s5_pass(mod, tmp_path)
    _stub_facts(mod, monkeypatch, 1, 2)
    ok, msg, bad = mod.advance("x", d, "fp", "DELIVER")
    assert not ok, "2 个悬空引脚竟然通过了 DELIVER"
    assert "floating pin" in msg
    assert ("PINS", "2 floating") in bad


def test_unreadable_board_blocks_delivery(mod, tmp_path, monkeypatch):
    """读不到板子 = 判不了 = 阻塞，不是放行。"""
    d = _at_s6_with_s5_pass(mod, tmp_path)
    _stub_facts(mod, monkeypatch, None, None)
    ok, msg, bad = mod.advance("x", d, "fp", "DELIVER")
    assert not ok
    assert ("PARTS", "unknown") in bad


def test_unknown_floating_count_blocks_delivery(mod, tmp_path, monkeypatch):
    d = _at_s6_with_s5_pass(mod, tmp_path)
    _stub_facts(mod, monkeypatch, 1, None)
    ok, msg, bad = mod.advance("x", d, "fp", "DELIVER")
    assert not ok, "数不出悬空引脚却放行了"
    assert ("PINS", "unknown") in bad


def test_clean_board_reaches_deliver(mod, tmp_path, monkeypatch):
    """真有器件、没有悬空引脚、S5 pass → 放行。"""
    d = _at_s6_with_s5_pass(mod, tmp_path)
    _stub_facts(mod, monkeypatch, 3, 0)
    ok, msg, bad = mod.advance("x", d, "fp", "DELIVER")
    assert ok, msg
    assert d["phase"] == "DELIVER"


def test_advancing_to_the_current_phase_is_not_reported_as_progress(mod, tmp_path,
                                                                    monkeypatch):
    d = mod.load("y")
    d["phase"] = "DELIVER"
    ok, msg, _ = mod.advance("y", d, "fp", "DELIVER")
    assert not ok, "同相位竟然报成功"
    assert "already at" in msg


def test_board_facts_reads_both_numbers(mod, monkeypatch):
    """一次 sch read 同时拿器件数与悬空引脚数（不重复调用）。"""
    calls = {"n": 0}

    class FakeRun:
        returncode = 0
        stdout = ('{"result": {"componentCount": 3, "floatingPinCount": 2,'
                  ' "components": [{"componentType": "sheet"},'
                  ' {"componentType": "part"}, {"componentType": "part"}]}}')

    def fake_subprocess(*a, **k):
        calls["n"] += 1
        return FakeRun()

    monkeypatch.setattr(mod.subprocess, "run", fake_subprocess)
    n, fp = mod.board_facts("p")
    assert (n, fp) == (2, 2), (n, fp)      # sheet 不算器件
    assert calls["n"] == 1, "应该只调一次 sch read"
