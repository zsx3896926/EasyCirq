"""去耦摆放检查的负向测试：故意把电容挪远 → 必须非 0。

另外两条：显式上限才算硬门；用默认经验值时只警告。
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_decap_placement.py"
BOARD = ROOT / "deliverables" / "fan-controller" / "snapshot" / "pcb-dump.json"


def run(args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(ROOT))


@pytest.mark.skipif(not BOARD.is_file(), reason="PCB 快照不存在")
def test_default_rule_of_thumb_only_warns():
    """用默认 100 mil 经验值时，超了只警告、退出码 0 —— 不拿惯例判死板子。"""
    proc = run(["--board", str(BOARD)])
    assert proc.returncode == 0, proc.stdout[-600:]
    assert "warn" in proc.stdout


@pytest.mark.skipif(not BOARD.is_file(), reason="PCB 快照不存在")
def test_explicit_limit_is_a_hard_gate():
    """显式给一个很小的上限 → 必须 fail 且退出码 1。"""
    proc = run(["--board", str(BOARD), "--max-mil", "1"])
    assert proc.returncode == 1, proc.stdout[-600:]
    assert "fail" in proc.stdout


@pytest.mark.skipif(not BOARD.is_file(), reason="PCB 快照不存在")
def test_moving_the_cap_far_away_fails():
    """故意把 C1 挪到很远 → 距离变大，显式上限下必须 fail。

    这是"故意制造该问题 → 必须报错"：如果检查器不看坐标，这条会红。
    """
    data = json.loads(BOARD.read_text(encoding="utf-8"))
    root = data.get("result") or data
    for comp in root.get("components") or []:
        if comp.get("designator") == "C1":
            for pad in comp.get("pads") or []:
                pad["x"] = float(pad.get("x", 0)) + 5000.0
    with tempfile.TemporaryDirectory() as tmp:
        moved = pathlib.Path(tmp) / "moved.json"
        moved.write_text(json.dumps(root, ensure_ascii=False), encoding="utf-8")
        proc = run(["--board", str(moved), "--max-mil", "200"])
        assert proc.returncode == 1, (
            "电容挪到 5000 单位外仍然报通过：\n" + proc.stdout[-800:])
        assert "fail" in proc.stdout
