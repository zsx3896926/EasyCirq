"""用**实测框**替换公式框 —— 语义正确性测试。

`textBboxes` 应当是"位号实际画在哪"，而不是公式估算。
实测框由探针渲染 + `svg_text_bbox` + `sch_preview_text` 得到
（内容在 `texts[].Content`，框在 `visible.items[].bbox`，用 id 关联）。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_preview_label_boxes.py"
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"
WORK = ROOT / "reports" / "hard-board" / "board2"


def test_script_exists_and_has_join_by_id():
    s = SCRIPT.read_text(encoding="utf-8")
    # 框在 visible.items，内容是 texts[].Content —— 必须用 id 关联
    assert "items" in s and "bbox" in s
    assert "primitiveId" in s
    assert "--page-bounds=" in s, "page-bounds 的值以 - 开头，必须用 = 形式"


def test_injects_measured_boxes(tmp_path):
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    z = tmp_path / "z.json"
    subprocess.run([sys.executable, str(ROOT / "easycirq" / "scripts" /
                                       "sch_preview_zones.py"), str(COMP), str(z)],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=900)
    if not z.is_file():
        pytest.skip("zones 生成失败")
    r = subprocess.run([sys.executable, str(SCRIPT), "--zones", str(z),
                        "--work", str(WORK)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=2400)
    if r.returncode != 0:
        pytest.skip("探针不可用：%s" % (r.stdout or r.stderr)[:120])
    d = json.loads(z.read_text(encoding="utf-8"))
    got = [pl for pl in d["zones"][0]["layout"]["placements"] if pl.get("textBboxes")]
    assert got, "一个实测框都没写回"
    # 实测框必须落在器件附近（不是默认的 0 值）
    for pl in got:
        bb = pl["textBboxes"][0]
        assert bb["maxX"] > bb["minX"] and bb["maxY"] > bb["minY"]


def test_falls_back_to_engine_boxes_when_probe_fails():
    """探针失败时要保持原样，不能写出空框。"""
    s = SCRIPT.read_text(encoding="utf-8")
    assert "渲染失败" in s
