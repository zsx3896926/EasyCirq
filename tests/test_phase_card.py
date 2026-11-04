"""`card` 接进 DELIVER 的守卫。

关键一条：`not_measured`（exit 2）必须映射成 pending。
它没报错、退出码也不是 1，但**什么也没证明**——正好是本目标要消灭的
"看起来没事"。
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "phase.py"


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("EASYCIRQ_PHASE_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("phase_mod3", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _stub_card(m, monkeypatch, state, rc):
    class P:
        returncode = rc
        stdout = '{"state": "%s", "headline": "x"}' % state
        stderr = ""

    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: P())


def test_card_ready_maps_to_pass(mod, monkeypatch):
    _stub_card(mod, monkeypatch, "ready", 0)
    st, _ = mod.card_state("p")
    assert st == mod.PASS


def test_card_not_ready_maps_to_fail(mod, monkeypatch):
    _stub_card(mod, monkeypatch, "not_ready", 1)
    st, _ = mod.card_state("p")
    assert st == mod.FAIL


def test_card_not_measured_maps_to_pending_not_pass(mod, monkeypatch):
    """这是本模块最重要的一条映射。

    exit=2 / state=not_measured 没有报错，但不是通过——它是 NOT RUN。
    """
    _stub_card(mod, monkeypatch, "not_measured", 2)
    st, _ = mod.card_state("p")
    assert st == mod.PENDING, (
        "not_measured 被映射成了 %r —— 没测量不等于通过" % st)
    assert not mod.is_release(st)


def test_card_garbage_maps_to_unknown(mod, monkeypatch):
    class P:
        returncode = 7
        stdout = "not json"
        stderr = ""
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: P())
    st, _ = mod.card_state("p")
    assert st == mod.UNKNOWN
    assert not mod.is_release(st)


def test_deliver_refuses_when_card_is_pending(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "board_facts", lambda p: (3, 0))
    _stub_card(mod, monkeypatch, "not_measured", 2)
    d = mod.load("x")
    d["phase"] = "S6"
    d["evidence"] = {"S5": {"verdict": mod.PASS, "fingerprint": "fp"}}
    mod.save("x", d)
    ok, msg, bad = mod.advance("x", d, "fp", "DELIVER")
    assert not ok
    assert ("CARD", mod.PENDING) in bad, bad
    assert "not been measured" in msg


def test_deliver_passes_only_when_card_is_ready(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "board_facts", lambda p: (3, 0))
    _stub_card(mod, monkeypatch, "ready", 0)
    d = mod.load("y")
    d["phase"] = "S6"
    d["evidence"] = {"S5": {"verdict": mod.PASS, "fingerprint": "fp"}}
    mod.save("y", d)
    ok, msg, bad = mod.advance("y", d, "fp", "DELIVER")
    assert ok, msg
    assert d["phase"] == "DELIVER"
    # 证据里要留下 CARD 这一条
    assert (d.get("evidence") or {}).get("CARD", {}).get("verdict") == mod.PASS
