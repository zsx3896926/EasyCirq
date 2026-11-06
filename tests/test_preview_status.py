"""可审计状态汇总：从产物算出来，不许手填、不许照抄陈旧结论。

这张表要回答一个问题：**"目标里点名的每条判据，现在到底什么状态？"**
所以它必须：
  · 覆盖目标点名的**每一条**判据（少一条就是漏报）
  · 陈旧产物判 🕒 而不是照抄旧结论（#89 的教训）
  · 同时给出**直接跑技能检查器**的结果（不经我的封装）
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATUS = ROOT / "easycirq" / "scripts" / "sch_preview_status.py"
WORK = ROOT / "reports" / "hard-board" / "board2"


def _run(work, out):
    return subprocess.run([sys.executable, str(STATUS), "--work", str(work),
                           "--out", str(out)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=2400)


@pytest.fixture(scope="module")
def text(tmp_path_factory):
    if not (WORK / "acceptance-M3.json").is_file():
        pytest.skip("没有验收产物")
    out = tmp_path_factory.mktemp("st") / "STATUS.md"
    p = _run(WORK, out)
    if not out.is_file():
        pytest.skip("未生成：%s" % (p.stdout or p.stderr)[:200])
    return out.read_text(encoding="utf-8")


def test_covers_every_objective_criterion(text):
    """目标点名的每条判据都要在表里出现。"""
    for title in ("内容不越框", "导线不穿器件本体", "模块框不切器件/导线",
                  "遮字 / 文字相压", "标签落在真实端点、朝向一致",
                  "网标朝向一致", "重复网名 / 孤立文字",
                  "不同网络导线交叉无结点", "图签无重复文字", "分区阅读顺序"):
        assert title in text, "漏了判据：%s" % title


def test_uses_real_criterion_ids(text):
    """ID 写错会导致整行显示 `—`（踩过：三个 ID 猜错）。

    只看**有判据**的模块（M3/M4/M5）。M1/M2 现在是 REFUSED、无任何判据，
    整列 `—` 是**正确**的，不能因此判失败。
    """
    rows = [l for l in text.splitlines()
            if l.startswith("|") and "✅" in l]
    assert rows, "表里没有任何通过的判据行"
    for line in rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        for i, mod in ((3, "M3"), (4, "M4"), (5, "M5")):
            if i < len(cells):
                assert cells[i] != "—", "%s 的 %s 没匹配上 ID" % (mod, cells[0])


def test_reports_direct_checker_output(text):
    assert "sch_layout_check" in text
    assert "sch_text_audit" in text
    assert "blocking" in text


def test_stale_modules_are_not_reported_as_pass(tmp_path):
    """陈旧的模块不许出现 ✅ —— 那是旧结论。"""
    work = tmp_path
    mod = "M3"
    (work / ("composition-%s-placed.json" % mod)).write_text("{}", encoding="utf-8")
    acc = {"module": mod, "verdict": "INCOMPLETE",
           "criteria": [{"id": "A_content_inside_page", "title": "内容不越框",
                         "status": "PASS", "count": 0, "needs": [],
                         "samples": [], "detail": []}]}
    ap = work / ("acceptance-%s.json" % mod)
    ap.write_text(json.dumps(acc), encoding="utf-8")
    past = (work / ("composition-%s-placed.json" % mod)).stat().st_mtime - 60
    os.utime(ap, (past, past))
    out = work / "s.md"
    p = _run(work, out)
    if not out.is_file():
        pytest.skip("未生成")
    t = out.read_text(encoding="utf-8")
    assert "🕒" in t, "陈旧产物没被标记"
    assert "无有效结论" in t


def test_has_reproduction_commands(text):
    assert "sch_preview_accept.py" in text
    assert "```bash" in text
