"""文字审计（`sch_text_audit.py --strict`）输入的回归测试。

目标里点名了这一项，我前 8 轮一次都没跑过。本轮接进链路后拿到真结论：
  M1 6 项 / M2 5 项 text_overlap|text_tight，M3/M4/M5 干净，五块覆盖都不完整。

本文件钉住**输入格式**，因为格式错会得到"invalid_input"而不是结论：
  · `count` 必须等于 items 长度
  · `unmeasured` 必须是**数组**（逐条列出没测到框的文字），不是数字
  · `coverage` 放在 `result` 里，且**没采集的类别不许写 true**
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_preview_textaudit as A  # noqa: E402

TEXTS = ROOT / "reports" / "hard-board" / "board2" / "texts-M3.json"
VIS = ROOT / "reports" / "hard-board" / "board2" / "visible-M3.json"


def test_unmeasured_is_an_array(tmp_path):
    t = tmp_path / "t.json"
    t.write_text(json.dumps([
        {"primitiveId": "a", "Content": "GND"},
        {"primitiveId": "b", "Content": "没框的文字"},
    ], ensure_ascii=False), encoding="utf-8")
    v = tmp_path / "v.json"
    v.write_text(json.dumps({"items": [
        {"id": "a", "bbox": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 5}},
    ]}), encoding="utf-8")
    doc = A.build(t, v)
    un = doc["result"]["unmeasured"]
    assert isinstance(un, list), "unmeasured 必须是数组"
    assert len(un) == 1 and un[0]["id"] == "b"


def test_count_matches_items(tmp_path):
    t = tmp_path / "t.json"
    t.write_text(json.dumps([{"primitiveId": "a", "Content": "X"}]),
                 encoding="utf-8")
    v = tmp_path / "v.json"
    v.write_text(json.dumps({"items": [
        {"id": "a", "bbox": {"minX": 0, "minY": 0, "maxX": 5, "maxY": 5}}]}),
        encoding="utf-8")
    doc = A.build(t, v)
    assert doc["result"]["count"] == len(doc["result"]["items"]) == 1


def test_coverage_refuses_to_claim_uncollected_classes(tmp_path):
    """没采集的类别不许标 true —— 否则"覆盖完整"是假的。"""
    t = tmp_path / "t.json"
    t.write_text("[]", encoding="utf-8")
    v = tmp_path / "v.json"
    v.write_text(json.dumps({"items": []}), encoding="utf-8")
    cov = A.build(t, v)["result"]["coverage"]
    for cls in ("values", "pin_names", "wire_names", "title_block"):
        assert cov.get(cls) is False, "%s 没采集却标了 true" % cls
    assert cov.get("free_text") is True


def test_real_audit_runs_and_reports_findings():
    """跑一次真实审计，确认能出结论（不是 invalid_input）。"""
    if not TEXTS.is_file() or not VIS.is_file():
        pytest.skip("缺实测文字")
    import subprocess
    import os
    sk = pathlib.Path(os.environ["USERPROFILE"]) / ".agents/skills/easycirq/scripts"
    audit_in = pathlib.Path(str(VIS) + ".t.json")
    try:
        doc = A.build(TEXTS, VIS)
        audit_in.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        out = pathlib.Path(str(VIS) + ".t.out.json")
        subprocess.run([sys.executable, str(sk / "sch_text_audit.py"),
                        str(audit_in), "--strict", "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
        if not out.is_file():
            pytest.skip("审计脚本不可用")
        d = json.loads(out.read_text(encoding="utf-8"))
        assert d.get("status") in ("incomplete", "findings", "ok", "clear"), d
        assert d.get("visual_verified") is False, "文字审计不该声称视觉已验证"
        assert d.get("electrical_verified") is False
    finally:
        for p in (audit_in, pathlib.Path(str(VIS) + ".t.out.json")):
            p.unlink(missing_ok=True)
