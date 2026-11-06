"""单模块页的 `zone_area_ratio` 标 N/A，但**多分区页仍按原规则判**。

为什么要有这条：把一条判据标成"不适用"很容易滑向"永远通过"。
所以这里同时验证两种拓扑：

  · 单分区页 → N/A（框应贴合模块）
  · 多分区页 → 仍按 25%~80% 判，比例过低照样失败

背景（#126）：审图改成贴合内容的框后，比例从 73% 掉到 19%，
低于 token 下限。而那个下限是给多分区页定的 —— 一页一模块时
把框撑满整页反而荒唐（#122 就是被它逼出来的空框）。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "easycirq" / "scripts" / "sch_style_check.py"
WORK = ROOT / "reports" / "hard-board" / "board2"


def _run(frames_path, tmp):
    return subprocess.run([sys.executable, str(CHECK), "--work", str(WORK),
                           "--frames", "M3=%s" % frames_path],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)


def test_single_zone_is_na(tmp_path):
    f = tmp_path / "one.json"
    f.write_text(json.dumps({"frames": [
        {"id": "M3", "rect": {"minX": 0, "minY": 0, "maxX": 70, "maxY": 70}}]}),
        encoding="utf-8")
    r = _run(f, tmp_path)
    assert "不适用" in (r.stdout or ""), (r.stdout or "")[-300:]


def test_multi_zone_still_checked(tmp_path):
    """两个小分区 → 仍应报违规（证明判据没被架空）。"""
    f = tmp_path / "two.json"
    f.write_text(json.dumps({"frames": [
        {"id": "a", "rect": {"minX": 0, "minY": 0, "maxX": 70, "maxY": 70}},
        {"id": "b", "rect": {"minX": 80, "minY": 0, "maxX": 150, "maxY": 70}}]}),
        encoding="utf-8")
    r = _run(f, tmp_path)
    out = r.stdout or ""
    assert "不适用" not in out, "多分区页不该判 N/A"
    assert "违规" in out
    assert r.returncode != 0, "多分区页比例过低必须失败"


def test_reason_is_written():
    s = CHECK.read_text(encoding="utf-8")
    assert "本页只有 1 个分区" in s
    assert "N/A" in s
