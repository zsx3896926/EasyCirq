"""harness 在真实使用里的两条健壮性：

1. **续跑**：两次 `run` 之间相位与证据是持久的。harness 被中断是常态
   （模型超时、人关窗口、机器重启），状态丢了就等于白跑。
2. **重复拒绝不污染状态**：模型反复调越界动作，相位不该前进半格。

这两条都不需要模型，但它们决定 harness 到底能不能用。
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"

pytestmark = pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")


def _run(project, script, phase_dir):
    sp = phase_dir / "script.json"
    sp.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "EASYCIRQ_PHASE_DIR": str(phase_dir)}
    p = subprocess.run([str(EXE), "run", "--goal", "robustness",
                        "--project", project, "--fake", str(sp)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600, env=env)
    return ((p.stdout or "") + (p.stderr or ""))


def _phase(project, phase_dir):
    env = {**os.environ, "EASYCIRQ_PHASE_DIR": str(phase_dir)}
    p = subprocess.run([str(EXE), "phase", "show", "--project", project, "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300, env=env)
    out = p.stdout or ""
    i = out.find("{")
    return json.loads(out[i:]) if i >= 0 else {}


def test_phase_survives_between_runs(tmp_path):
    """第一次推到 S2，第二次必须从 S2 接着走，不能回到 S0。

    中断后重来一次就白跑，等于 harness 不能在真项目上用。
    """
    pd = tmp_path / "phase"
    pd.mkdir()
    _run("resume1", [[{"name": "phase_advance", "args": {}}],
                     [{"name": "phase_advance", "args": {}}],
                     [{"name": "finish", "args": {"summary": "half"}}]], pd)
    assert _phase("resume1", pd).get("phase") == "S2"

    _run("resume1", [[{"name": "phase_advance", "args": {}}],
                     [{"name": "finish", "args": {"summary": "continue"}}]], pd)
    assert _phase("resume1", pd).get("phase") == "S3", "第二次没有接着走"


def test_repeated_refusals_do_not_advance_the_phase(tmp_path):
    """连续 5 次越界，全部被拒，相位必须一动不动。"""
    pd = tmp_path / "phase"
    pd.mkdir()
    bad = [[{"name": "easycirq", "args": {"argv": ["sch", "place", "--x", "1"]}}]] * 5
    bad.append([{"name": "finish", "args": {"summary": "blocked"}}])
    out = _run("refuse1", bad, pd)
    assert out.count("REFUSED") == 5, "应该有 5 次拒绝，实际：\n" + out[-500:]
    assert _phase("refuse1", pd).get("phase") == "S0", "越界动作把相位推走了"


def test_refusal_keeps_the_reason_visible(tmp_path):
    """拒绝必须说明为什么——只打 `REFUSED refused` 等于没说。"""
    pd = tmp_path / "phase"
    pd.mkdir()
    out = _run("refuse2", [[{"name": "phase_advance", "args": {"to": "DELIVER"}}],
                           [{"name": "finish", "args": {"summary": "x"}}]], pd)
    assert "REFUSED" in out
    # 必须点名缺哪条证据（S5 或 CARD 或 PARTS/PINS）
    assert any(k in out for k in ("S5=", "CARD=", "PARTS=", "PINS=")), \
        "拒绝没说是哪一条阻塞：\n" + out[-600:]
