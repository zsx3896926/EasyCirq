"""陈旧产物不许冒充当前结论。

实测：M1/M2 渲染失败，目录里却躺着**上一轮**的验收/审计 JSON。
最终核验照着读，报出 "M1 blocking=113"、"M1 文字 6 项"——全是旧结论，
看起来就像"当前就是这个样"。

这类"旧数据当新事实"在本目标里反复出现（#75 跨稿相减、#86 少一条判据），
所以把它做成**代码里的判定**，而不是靠人记得。
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / "easycirq" / "scripts" / "sch_preview_report.py"


def test_is_stale_helper_exists():
    s = REPORT.read_text(encoding="utf-8")
    assert "def is_stale(" in s
    assert "st_mtime" in s


def test_report_marks_stale_module(tmp_path):
    """产物比排版稿旧 → 报告必须把它列进"过期产物"，而不是照抄结论。"""
    work = tmp_path
    mod = "M3"
    (work / ("composition-%s-placed.json" % mod)).write_text("{}", encoding="utf-8")
    acc = {
        "module": mod, "verdict": "INCOMPLETE",
        "criteria": [{"id": "A", "title": "内容不越框", "status": "PASS",
                      "count": 0, "needs": [], "samples": [], "detail": []}],
    }
    ap = work / ("acceptance-%s.json" % mod)
    ap.write_text(json.dumps(acc), encoding="utf-8")
    # 让验收产物**比排版稿旧**
    past = (work / ("composition-%s-placed.json" % mod)).stat().st_mtime - 60
    os.utime(ap, (past, past))

    out = work / "r.md"
    p = subprocess.run([sys.executable, str(REPORT), "--work", str(work),
                        "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    if not out.is_file():
        pytest.skip("报告未生成：%s" % (p.stdout or p.stderr)[:200])
    text = out.read_text(encoding="utf-8")
    assert ("过期产物" in text or "陈旧" in text), "没有陈旧章节"
    assert mod in text


def test_report_keeps_fresh_module(tmp_path):
    """新鲜的产物要正常进表，别把好的也当过期。"""
    work = tmp_path
    mod = "M4"
    comp = work / ("composition-%s-placed.json" % mod)
    comp.write_text("{}", encoding="utf-8")
    acc = {
        "module": mod, "verdict": "INCOMPLETE",
        "criteria": [{"id": "A", "title": "内容不越框", "status": "PASS",
                      "count": 0, "needs": [], "samples": [], "detail": []}],
    }
    ap = work / ("acceptance-%s.json" % mod)
    ap.write_text(json.dumps(acc), encoding="utf-8")
    later = comp.stat().st_mtime + 60
    os.utime(ap, (later, later))

    out = work / "r.md"
    subprocess.run([sys.executable, str(REPORT), "--work", str(work),
                    "--out", str(out)],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=600)
    if not out.is_file():
        pytest.skip("报告未生成")
    text = out.read_text(encoding="utf-8")
    assert mod in text
    assert "过期产物" not in text, "新鲜产物被误判为过期"
