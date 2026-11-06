"""`--frames` 指向不存在的文件时必须**硬报错**，不能静默按估算算。

实测：传了不存在的路径，检查器不吭声、改用器件外框估算，
报出 6 项**假违规**（面积 10.9% / 内距 0.00 mm）。
正确的框文件（审图渲染器产出的 `review/frames-<页名>.json`）下是
**0 违规**（面积 73.1%/77.6%/73.1%，内距 14.9/10.9/20.0 mm）。
"""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "easycirq" / "scripts" / "sch_style_check.py"
WORK = ROOT / "reports" / "hard-board" / "board2"


def test_missing_frames_file_fails_loudly(tmp_path):
    r = subprocess.run([sys.executable, str(CHECK), "--work", str(WORK),
                        "--frames", "M3=%s" % (tmp_path / "nope.json")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    assert r.returncode != 0, "缺文件时不该返回 0"
    assert "不存在" in (r.stdout + r.stderr), "没给出明确原因"


def test_guard_message_explains_the_fallback():
    s = CHECK.read_text(encoding="utf-8")
    assert "不许静默回退" in s
    assert "SystemExit" in s


def test_real_frames_give_zero_violations():
    """真实 frames 下应当 0 违规（回归保护）。"""
    fr = WORK / "review" / "frames-P3_5V转3V3主逻辑轨.json"
    if not fr.is_file():
        pytest.skip("没有审图产出的 frames")
    r = subprocess.run([sys.executable, str(CHECK), "--work", str(WORK),
                        "--frames", "M3=%s" % fr],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    out = r.stdout or ""
    assert "违规 0 项" in out or "0 项" in out, out[-300:]
