"""文档里写的命令**必须真的能跑**。

现有测试只检查"文档里有这段命令"，没验证它可执行。
本项目反复出现"命令写了但参数/路径不对"（`--frames` 指错路径会静默给出假违规），
所以要把文档命令纳入回归。

**文件名要动态查找**：审图产物名由模块标题净化而来，改过两次
（`P3_5V转3V3主逻辑轨` → `P3_5V_-_3.3V_主逻辑轨_SY8089`），
硬编码名字的测试会莫名其妙失效。
"""
import subprocess
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "reports" / "hard-board" / "board2"
REVIEW = WORK / "review"
REVIEW_PY = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"
STYLE_PY = ROOT / "easycirq" / "scripts" / "sch_style_check.py"
COMP = WORK / "composition-M3-placed.json"


def _frame_for(prefix):
    """按页名前缀找审图导出的 frames 文件（名字可漂移）。"""
    if not REVIEW.is_dir():
        return None
    hits = sorted(REVIEW.glob("frames-%s*.json" % prefix))
    return hits[0] if hits else None


def test_documented_review_gate_command_runs():
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    r = subprocess.run([sys.executable, str(REVIEW_PY),
                        "--composition", str(COMP),
                        "--page-name", "P3_文档验证",
                        "--out-dir", str(REVIEW), "--gate"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=2400)
    assert r.returncode == 0, (r.stdout or r.stderr)[-400:]


def test_documented_style_command_runs():
    args = [sys.executable, str(STYLE_PY), "--work", str(WORK)]
    for mod, prefix in (("M3", "P3"), ("M4", "P4"), ("M5", "P5")):
        f = _frame_for(prefix)
        if f is None:
            pytest.skip("缺 P%s 的 frames" % prefix[1:])
        args += ["--frames", "%s=%s" % (mod, f)]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    assert r.returncode == 0, (r.stdout or r.stderr)[-500:]
    assert "违规 0 项" in (r.stdout or "")


def test_doc_shows_style_command():
    doc = ROOT / "easycirq" / "references" / "preview-acceptance.md"
    if not doc.is_file():
        pytest.skip("没有文档")
    s = doc.read_text(encoding="utf-8")
    assert "sch_style_check" in s and "M3=" in s


def test_host_only_commands_are_marked():
    doc = ROOT / "easycirq" / "references" / "preview-acceptance.md"
    if not doc.is_file():
        pytest.skip("没有文档")
    s = doc.read_text(encoding="utf-8")
    assert "sch gate" in s and "layout-score" in s
    assert "NOT RUN" in s
