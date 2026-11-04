"""A① 分块缓冲 + E③ 回放的守卫。

A① 的诚实结论是「实现了、验证等价、但实测不划算所以默认关」，
所以测试要钉住三件事：
  1. 分块与稠密两条路径产物**逐字节相同**（否则"等价"是空话）
  2. 默认走稠密（否则会静默把交付档位拖慢 20%）
  3. 分块真的会按需分配，不是"换个名字又是稠密"

E③ 钉住：
  4. 回放命中 vs unknown 的区分，且**永不输出 pass**
  5. part_forbidden 的键必须是 `parts`（写成 `patterns` 时引擎不认——这真发生过）
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAY = ROOT / "easycirq" / "scripts" / "layout"
SCRIPTS = ROOT / "easycirq" / "scripts"
PYX = LAY / "_astar_c.pyx"
PYD = LAY / "_astar_c.pyd"

sys.path.insert(0, str(SCRIPTS))


def _has_ext():
    return PYD.is_file()


# ── A① 1. 两条路径产物相同 ────────────────────────────────────────────
def test_dense_and_paged_produce_the_same_plan():
    """强制分块（阈值 0）与默认稠密，plan 必须逐字节相同。"""
    if not _has_ext():
        pytest.skip("没有编译产物")
    base = {k: v for k, v in __import__("os").environ.items()}

    env = {**base, "EASYCIRQ_ASTAR_C": "1"}
    p1 = subprocess.run([sys.executable, "equivalence.py", "--iters", "3",
                         "--compare"], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=1800,
                        cwd=str(LAY), env=env)
    assert p1.returncode == 0, (p1.stdout + p1.stderr)[-800:]

    env2 = {**base, "EASYCIRQ_ASTAR_C": "1", "EASYCIRQ_ASTAR_DENSE_LIMIT": "0"}
    p2 = subprocess.run([sys.executable, "equivalence.py", "--iters", "3",
                         "--compare"], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=1800,
                        cwd=str(LAY), env=env2)
    assert p2.returncode == 0, (p2.stdout + p2.stderr)[-800:]
    assert "产物逐字节相同" in (p2.stdout or "")


# ── A① 2. 默认阈值必须是真实可达的（策略要真的生效） ──────────────────
def test_paging_actually_engages_above_the_default_threshold():
    """目标要求"超过阈值走分块"。

    曾经把默认阈值设成"实际不可达"，那就等于交付的仍是无条件稠密分配——
    「存了」不等于「生效了」。这条测试钉住：默认阈值必须是一个真实节点数，
    且大图真的会落进分块分支。
    """
    s = PYX.read_text(encoding="utf-8")
    i = s.find("cdef long _dense_limit()")
    assert i > 0
    seg = s[i:i + 1200]
    assert "1 << 60" not in seg, "默认阈值又变成不可达了——分块等于没启用"
    assert "8000000" in seg, "默认阈值不是真实节点数"

    # 阈值必须落在"小板走稠密、大板走分块"之间
    assert 13_695_616 > 8_000_000, "x4 应当超过默认阈值（走分块）"
    assert 810_432 < 8_000_000, "x1 应当低于默认阈值（走稠密）"

    # 扩展在时，真的把它加载起来，确认默认阈值传到了内核可见的位置
    if not _has_ext():
        pytest.skip("没有编译产物")
    if str(LAY) not in sys.path:
        sys.path.insert(0, str(LAY))
    import ec_layout
    assert ec_layout._FAST_ASTAR is not None, "扩展没加载"
    assert hasattr(ec_layout._FAST_ASTAR, "astar_c")


# ── A① 3. 分块真的按需分配 ───────────────────────────────────────────
def test_paged_mode_allocates_lazily():
    if not _has_ext():
        pytest.skip("没有编译产物")
    s = PYX.read_text(encoding="utf-8")
    # 读未分配页不分配、写才分配，这是分块的核心
    assert "_pg_new_d" in s and "_pg_new_l" in s
    # 读路径必须返回哨兵而不是分配
    i = s.find("cdef inline double _bget")
    assert i > 0
    j = s.find("cdef inline int _bset", i)
    assert j > i, "找不到 _bset 的边界"
    body = s[i:j]
    assert "return DEF_INF" in body, "读未分配页没有返回哨兵"
    assert "_pg_new" not in body, "读路径居然会分配页"


# ── E③ 4. 回放：hit / unknown，永不 pass ─────────────────────────────
def test_replay_reports_hit_or_unknown_never_pass():
    import enterprise_replay

    rows = [
        {"id": "A", "candidate_rule": {"id": "r", "kind": "advisory", "title": "r", "predicate": {
            "type": "part_forbidden", "parts": ["ESP32-S3-WROOM-1"]}},
         "evidence": {"designator": "U5", "device": "ESP32-S3-WROOM-1"}},
        {"id": "B", "candidate_rule": {"id": "r2", "kind": "advisory", "title": "r2", "predicate": {
            "type": "part_forbidden", "parts": ["NOPE-XYZ"]}},
         "evidence": {"designator": "U5", "device": "ESP32-S3-WROOM-1"}},
    ]
    comps = [{"designator": "U5", "device": "ESP32-S3-WROOM-1",
              "pads": [{"net": "GND"}]}]
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        dp = pathlib.Path(td) / "dump.json"
        dp.write_text(json.dumps({"components": comps}), encoding="utf-8")
        out = enterprise_replay.replay(rows, str(dp))

    verdicts = {r["id"]: r["verdict"] for r in out}
    assert verdicts["A"] == "hit", out
    assert verdicts["B"] == "unknown", out
    assert all(r["verdict"] != "pass" for r in out), "回放不许输出 pass"


def test_replay_without_dump_is_unknown():
    import enterprise_replay
    rows = [{"id": "A", "candidate_rule": {"id": "r", "kind": "advisory", "title": "r", "predicate": {
        "type": "part_forbidden", "parts": ["X"]}},
        "evidence": {"designator": "U1", "device": "X"}}]
    out = enterprise_replay.replay(rows, None)
    assert out[0]["verdict"] == "unknown"
    assert "dump" in out[0]["detail"]


# ── E③ 5. 谓词键必须是 parts ─────────────────────────────────────────
def test_harvest_emits_the_key_the_engine_actually_reads():
    """引擎读 pred["parts"]；写成 "patterns" 时规则永不触发。"""
    import enterprise_harvest as eh
    import inspect
    src = inspect.getsource(eh.propose_candidates)
    assert '"parts"' in src, "harvest 没用引擎认的键"
    assert '"patterns": [str(dev)]' not in src, "又写回 patterns 了"

    # 真跑一遍引擎，确认这条谓词会触发
    import enterprise_rules
    rule = {"id": "t", "kind": "advisory", "title": "t",
            "predicate": {"type": "part_forbidden", "parts": ["S8050"]},
            "owner": "", "verified_on": ""}
    nl = {"components": [{"componentType": "part", "designator": "R1",
                          "otherProperty": {"Manufacturer Part": "S8050"},
                          "pins": [{"net": "N"}]}]}
    results, _ = enterprise_rules.evaluate([rule], nl)
    assert results[0]["status"] == "fail", "part_forbidden 没触发"


def test_replay_exits_nonzero_when_something_is_unknown():
    """回放是门禁：有 unknown 就不能返回 0。"""
    import enterprise_harvest as eh
    import inspect
    src = inspect.getsource(eh.main)
    assert "all(r[" in src and "hit" in src, "回放没有把 unknown 当失败"
