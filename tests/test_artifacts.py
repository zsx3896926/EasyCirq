"""P4「历史与产物」的验收。

面板要能回答"我这块板产出过哪些证据文件、在哪、什么时候生成的"，
而且**清单不能看起来就是全部**——被 --limit 截断时必须说清总数。
"""
import json
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"
HTML = ROOT / "runtime" / "internal" / "app" / "panel" / "index.html"

pytestmark = pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")


def _artifacts(*args):
    p = subprocess.run([str(EXE), "artifacts", "--json"] + list(args),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    assert p.returncode == 0, p.stderr[:400]
    return json.loads(p.stdout)


def test_artifacts_lists_known_evidence_files(tmp_path):
    """只认已知文件名：产物清单里出现的每一项都必须能说出它是什么。"""
    # 造一份最小证据目录
    d = tmp_path / "reports" / "demo"
    d.mkdir(parents=True)
    (d / "kpi-report.json").write_text("{}", encoding="utf-8")
    (d / "kpi-history.jsonl").write_text("{}\n", encoding="utf-8")
    (d / "random.txt").write_text("x", encoding="utf-8")  # 不该被列出

    rep = _artifacts("--root", str(tmp_path / "reports"), "--limit", "0")
    paths = [a["path"] for a in rep["artifacts"]]
    assert any(p.endswith("kpi-report.json") for p in paths), "交付卡读的那份没被列出"
    assert any(p.endswith("kpi-history.jsonl") for p in paths)
    assert not any(p.endswith("random.txt") for p in paths), "不该把无关文件也列进产物"
    for a in rep["artifacts"]:
        assert a["kind"], "每一项都要说清它是什么：%r" % a
        assert a["bytes"] >= 0 and a["modified"]


def test_artifacts_reports_total_when_truncated(tmp_path):
    """被 --limit 截断时必须给出总数 —— 清单不能看起来就是全部。"""
    # 同名文件在不同批次目录里 —— 这才是真实布局（reports/<批次>/kpi-report.json）
    for i in range(5):
        d = tmp_path / "reports" / ("batch%d" % i)
        d.mkdir(parents=True)
        (d / "kpi-report.json").write_text("{}", encoding="utf-8")
    rep = _artifacts("--root", str(tmp_path / "reports"), "--limit", "2")
    assert len(rep["artifacts"]) == 2, "limit 没生效"
    assert rep["total"] >= 5, "total 必须如实反映扫到的总数，得到 %r" % rep.get("total")


def test_panel_renders_artifacts_and_states_the_total():
    page = HTML.read_text(encoding="utf-8")
    assert 'id="artifactsCard"' in page, "面板没有产物卡"
    assert "function renderArtifacts" in page
    assert "renderArtifacts(snap.artifacts)" in page, "render 里没调用"
    # 截断说明必须在页面上，而不是只写在 CLI 里
    assert "只显示最近" in page, "面板没说明清单被截断过"


def test_artifacts_empty_state_says_what_to_do(tmp_path):
    """没有任何产物时要说下一步，不是空列表。"""
    (tmp_path / "reports").mkdir()
    rep = _artifacts("--root", str(tmp_path / "reports"))
    assert rep["artifacts"] == []
    assert rep.get("note"), "空清单必须给下一步提示"
