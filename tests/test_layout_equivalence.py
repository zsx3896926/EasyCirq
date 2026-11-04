"""等价性门禁的守卫测试。

这道闸的存在理由：`bench --compare` 比 KPI 指纹，而**两个不同的 plan 可以给出同一组 KPI**。
改内循环时必须证明产物没变，不是数字没变。
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "easycirq" / "scripts" / "layout"
EQ = LAYOUT / "equivalence.py"
STORE = LAYOUT / ".bench" / "equivalence.json"


def run(args, timeout=1200):
    return subprocess.run([sys.executable, str(EQ), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, cwd=str(LAYOUT))


def test_gate_script_exists_and_uses_emit_apply_identity():
    """哈希口径必须和 emit_apply 拒绝上板用的一致，不许另造一套。"""
    s = EQ.read_text(encoding="utf-8")
    assert "from emit_apply import normalise" in s, "没有复用 emit_apply 的归一化"
    assert "sort_keys=True" in s


def test_gate_demands_write_or_compare():
    """不带 --write/--compare 时必须报错——这道闸不是用来'看看'的。"""
    p = run([])
    assert p.returncode != 0
    assert "--write 或 --compare" in (p.stdout + p.stderr)


def test_recorded_baseline_exists():
    assert STORE.is_file(), "没有基线记录，门禁无从比对"
    import json
    d = json.loads(STORE.read_text(encoding="utf-8"))
    assert "spots" in d and d["spots"], "基线里没有 spot"
    for name, row in d["spots"].items():
        assert len(row.get("plan_sha256") or "") == 64, f"{name} 的 sha 不合规"


def test_gate_passes_on_unchanged_code():
    """同代码同轮次：必须 identical。"""
    p = run(["--iters", "3", "--compare"])
    out = p.stdout + p.stderr
    assert p.returncode == 0, out[-1200:]
    assert "产物逐字节相同" in out


def test_gate_fails_when_the_plan_differs():
    """故意用 1 轮对 3 轮的记录：必须报 PLAN CHANGED 并退 1。

    这条是这道闸存在的全部意义——不会失败的门禁等于没有。
    """
    p = run(["--iters", "1", "--compare"])
    out = p.stdout + p.stderr
    assert p.returncode == 1, f"产物变了却没退 1：\n{out[-1200:]}"
    assert "PLAN CHANGED" in out


def test_astar_keeps_its_dictionaries():
    """§193 的结论：dict→list 实测无收益，已回退。别又改回去而不重新量。"""
    s = (LAYOUT / "ec_layout.py").read_text(encoding="utf-8")
    assert "get_best = best.get" in s, (
        "A* 的 g 表不再是 dict —— §193 量过换成列表没有收益，"
        "要改先跑 equivalence.py 与 bench.py --compare 并记录数字")
    assert "_best_buffer" not in s, "缓冲区版本已回退，不要残留"
