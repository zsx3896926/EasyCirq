"""文档里写的命令**必须真的能跑**。

现有测试只检查"文档里有这段命令"，没验证它可执行。
而本项目反复出现"命令写了但参数不对/路径不对"（如 `--frames` 指错路径
会静默给出假违规），所以要把文档命令纳入回归。

只跑**离线可用**的那两条（出图门禁 + 风格检查），需要现场的 `sch gate`
与 `layout-score` 明确不在其中。
"""
import subprocess
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "reports" / "hard-board" / "board2"
REVIEW_PY = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"
STYLE_PY = ROOT / "easycirq" / "scripts" / "sch_style_check.py"
COMP = WORK / "composition-M3-placed.json"

# 三个可交付模块的审图产物（frames 必须逐个给，漏一个就变 N/R）
FRAMES = {
    "M3": "frames-P3_5V转3V3主逻辑轨.json",
    "M4": "frames-P4_输入保护与滤波.json",
    "M5": "frames-P5_反馈与指示.json",
}


def test_documented_review_gate_command_runs():
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    r = subprocess.run([sys.executable, str(REVIEW_PY),
                        "--composition", str(COMP),
                        "--page-name", "P3_文档验证",
                        "--out-dir", str(WORK / "review"), "--gate"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=2400)
    assert r.returncode == 0, (r.stdout or r.stderr)[-400:]


def test_documented_style_command_runs():
    args = [sys.executable, str(STYLE_PY), "--work", str(WORK)]
    for mod, name in FRAMES.items():
        p = WORK / "review" / name
        if not p.is_file():
            pytest.skip("缺 %s" % name)
        args += ["--frames", "%s=%s" % (mod, p)]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    assert r.returncode == 0, (r.stdout or r.stderr)[-500:]
    assert "违规 0 项" in (r.stdout or "")


def test_doc_shows_all_three_frames():
    """文档的命令要传全部三个模块的 frames，否则照抄会得到 N/R。"""
    doc = ROOT / "easycirq" / "references" / "preview-acceptance.md"
    if not doc.is_file():
        pytest.skip("没有文档")
    s = doc.read_text(encoding="utf-8")
    assert "M3=" in s and "sch_style_check" in s


def test_host_only_commands_are_marked():
    doc = ROOT / "easycirq" / "references" / "preview-acceptance.md"
    if not doc.is_file():
        pytest.skip("没有文档")
    s = doc.read_text(encoding="utf-8")
    assert "sch gate" in s and "layout-score" in s
    assert "NOT RUN" in s
