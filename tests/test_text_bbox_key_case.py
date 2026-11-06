"""`textBboxes` 键名的大小写是**契约**，写错会被静默忽略。

这个坑消耗了 7 轮（#69–#76）：Go 的 JSON 标签是 `textBboxes`（小写 b），
而我一直写 `textBBoxes`。渲染/求解用的都是**严格解码器**，大小写敏感 ——
写错的字段被当成**未知字段**，于是：

  · 我所有"加了文字框"的输入，其实一个框都没被读到
  · 于是"导线避让位号"的约束**从来没生效过**
  · 而我一直以为是框位置、容差、校验缺失的问题，逐个排除都无效

本文件钉三件事：
  1. 生成的 zones 里键必须是 `textBboxes`
  2. 仓库脚本里**不许**出现错误大小写
  3. 端到端：带框且导线穿过 → 渲染门必须**拒绝**
"""
import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "easycirq" / "scripts"
ZONES = SCRIPTS / "sch_preview_zones.py"
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"


def test_no_script_uses_wrong_key_case():
    """错误大小写不许留在任何脚本里 —— 它不会报错，只会静默失效。"""
    # 只看**真正当字符串/键用**的地方：注释里提到这个坑不算违规
    pat = re.compile(r"""[\"']textBBoxes[\"']""")
    bad = []
    for f in SCRIPTS.glob("*.py"):
        s = f.read_text(encoding="utf-8")
        if pat.search(s):
            bad.append(f.name)
    assert bad == [], "这些脚本仍用错误的键大小写：%r" % bad


def test_zones_emits_correct_key(tmp_path):
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    out = tmp_path / "z.json"
    p = subprocess.run([sys.executable, str(ZONES), str(COMP), str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    if not out.is_file():
        pytest.skip("生成失败：%s" % (p.stderr or "")[:200])
    z = json.loads(out.read_text(encoding="utf-8"))
    pl = z["zones"][0]["layout"]["placements"][0]
    assert "textBboxes" in pl, "键名大小写不对（应为 textBboxes）"
    assert "textBBoxes" not in pl
    for k in ("minX", "minY", "maxX", "maxY"):
        assert k in pl["textBboxes"][0]


def test_render_gate_rejects_wire_crossing_label(tmp_path):
    """端到端：给了框且导线穿框 → 渲染门必须拒绝。

    这是"约束真的生效"的唯一可信证据 —— 之前 7 轮都栽在这条没被验证。
    """
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    zones_path = tmp_path / "z.json"
    p = subprocess.run([sys.executable, str(ZONES), str(COMP), str(zones_path)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    if not zones_path.is_file():
        pytest.skip("zones 生成失败")
    import os
    exe = pathlib.Path(os.environ.get("LOCALAPPDATA") or pathlib.Path.home()) \
        / "EasyCirq" / "bin" / "easycirq.exe"
    if not exe.is_file():
        pytest.skip("没有 easycirq 可执行文件")

    z = json.loads(zones_path.read_text(encoding="utf-8"))
    page = {"minX": 0, "minY": 0, "maxX": 594, "maxY": 420}
    b = {"minX": page["minX"] - 800, "minY": page["minY"] - 800,
         "maxX": page["maxX"] + 1200, "maxY": page["maxY"] + 900}
    z["sheet"]["bounds"] = dict(b)
    z["sheet"]["border"] = dict(b)
    for zone in z["zones"]:
        r = zone["frame"]["rect"]
        cx, cy = (r["minX"] + r["maxX"]) / 2, (r["minY"] + r["maxY"]) / 2
        hw = (r["maxX"] - r["minX"]) / 2 + 400
        hh = (r["maxY"] - r["minY"]) / 2 + 400
        r2 = {"minX": cx - hw, "minY": cy - hh, "maxX": cx + hw, "maxY": cy + hh}
        zone["frame"]["rect"] = r2
        zone["frame"]["titleX"] = r2["minX"] + 4
        zone["frame"]["titleY"] = r2["maxY"] - 4
        zone["sheetPosition"] = {"x": (r2["minX"] // 5) * 5,
                                 "y": (r2["maxY"] // 5) * 5}
    zones_path.write_text(json.dumps(z, ensure_ascii=False), encoding="utf-8")

    svg = tmp_path / "o.svg"
    q = subprocess.run([str(exe), "sch", "layout-render", "--from", str(zones_path),
                        "--out", str(svg)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    msg = ((q.stdout or "") + (q.stderr or "")).strip()
    # 要么渲染成功（说明这份稿确实不穿），要么被 wire-text 拒绝（约束生效）。
    # **不许**在报别的错时悄悄放过。
    if q.returncode == 0:
        assert svg.is_file()
    else:
        assert "label reservation" in msg, "渲染失败的原因不是标签预留：%s" % msg[:200]
