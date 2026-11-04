"""循环的守卫：**模型跳不过步骤**。

这些测试都不需要 API key —— 用假模型（固定剧本）驱动，于是
"想跳步会不会被拒""门没过能不能推进"是确定性可测的。

这一层是"方法论做成代码"的最后一段：门已经写进 `phase.py`，
但如果循环不拦、模型照样能绕。所以这里每条都在证明一次**拒绝**。
"""
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location("run_mod", SCRIPTS / "run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def runmod(tmp_path, monkeypatch):
    monkeypatch.setenv("EASYCIRQ_PHASE_DIR", str(tmp_path))
    return _load()


def _script(seq):
    return [[{"name": n, "args": a}] for n, a in seq]


def _drive(runmod, script, rounds=12):
    h = runmod.Harness("demo", max_rounds=rounds, verbose=False)
    fake = runmod.FakeModel(_script(script))
    return runmod.loop(h, lambda _m: {"tool_calls": fake.next_calls(), "text": ""},
                       rounds, verbose=False), h


# ── 白名单：按词边界，且越界就拒 ─────────────────────────────────────
def test_whitelist_matches_on_word_boundaries(runmod):
    assert runmod.is_allowed("S3", ["sch", "place", "--x", "1"])
    # 裸 startswith 会把这条放过去
    assert not runmod.is_allowed("S3", ["sch", "placeX"])


def test_model_cannot_place_before_its_phase(runmod):
    """S0 时调 sch place 必须被拒——这是"跳不过步骤"的最小证明。"""
    res, h = _drive(runmod, [("easycirq",
                              {"argv": ["sch", "place", "--x", "1", "--y", "1"]}),
                             ("finish", {"summary": "x"})], rounds=3)
    refused = [e for e in h.log if "REFUSED" in e["msg"]]
    assert refused, "S0 调 sch place 竟然没被拒\n" + json.dumps(h.log, ensure_ascii=False)
    assert "S0" in refused[0]["msg"]


def test_refusal_tells_the_model_what_is_allowed(runmod):
    h = runmod.Harness("demo", max_rounds=2, verbose=False)
    out = h.execute("easycirq", {"argv": ["sch", "place"]})
    assert out.get("refused") is True
    assert "allowedInThisPhase" in out
    assert "phase_status" in out["allowedInThisPhase"]


# ── 门没过，推进不了 ─────────────────────────────────────────────────
def test_cannot_advance_past_an_unrun_gate(runmod):
    """S5 有门没跑 → 推进到 S6 必须被拒。"""
    h = runmod.Harness("demo", max_rounds=2, verbose=False)
    d = runmod.ph.load("demo")
    d["phase"] = "S5"
    runmod.ph.save("demo", d)
    out = h.execute("phase_advance", {})
    assert out["ok"] is False
    assert any(b["phase"] == "S5" for b in out["blockers"])


def test_blocked_gate_does_not_release_advance(runmod):
    """`blocked`（检查器没跑成）不是通过。"""
    h = runmod.Harness("demo", max_rounds=2, verbose=False)
    d = runmod.ph.load("demo")
    d["phase"] = "S5"
    d["evidence"] = {"S5": {"verdict": "blocked", "fingerprint": None}}
    runmod.ph.save("demo", d)
    out = h.execute("phase_advance", {})
    assert out["ok"] is False
    assert any(b["state"] == "blocked" for b in out["blockers"])


# ── 正常路径也能走 ───────────────────────────────────────────────────
def test_loop_advances_through_unenforced_phases(runmod):
    """未接门的相位不阻塞，循环能推着往前走。"""
    seq = [("phase_advance", {})] * 5 + [("finish", {"summary": "x"})]
    res, h = _drive(runmod, seq, rounds=8)
    assert h.state()[0]["phase"] in ("S5", "S6", "DELIVER")
    assert h.rounds > 1


def test_loop_stops_at_deliver_and_reports(runmod):
    _res, h = _drive(runmod, [("finish", {"summary": "done"})], rounds=2)
    assert h.rounds >= 1


# ── 工具面 ───────────────────────────────────────────────────────────
def test_status_blob_exposes_phase_evidence_and_allowed(runmod):
    h = runmod.Harness("demo", max_rounds=1, verbose=False)
    blob = h.execute("phase_status", {})
    assert "phase" in blob and "evidence" in blob
    assert "allowedActions" in blob
    assert "phase_advance" in blob["allowedActions"]


def test_unknown_tool_is_refused_not_executed(runmod):
    h = runmod.Harness("demo", max_rounds=1, verbose=False)
    out = h.execute("rm_rf_everything", {})
    assert "error" in out


def test_every_phase_allows_the_meta_tools(runmod):
    for p in runmod.ph.PHASES:
        allowed = runmod.allowed_for(p)
        for meta in runmod.META_TOOLS:
            assert meta in allowed, f"{p} 连 {meta} 都不许，循环会卡死"


def test_fake_model_exhaustion_finishes_instead_of_hanging(runmod):
    h = runmod.Harness("demo", max_rounds=8, verbose=False)
    fake = runmod.FakeModel([])
    res = runmod.loop(h, lambda _m: {"tool_calls": fake.next_calls(), "text": ""},
                      8, verbose=False)
    assert res["rounds"] <= 2, "剧本用完后应该立刻 finish，不该空转"
