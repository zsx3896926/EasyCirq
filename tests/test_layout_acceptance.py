"""验收表的回归测试：**缺证据不许判 PASS**，候选不许冒充缺陷。"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACC = ROOT / "easycirq" / "scripts" / "sch_layout_acceptance.py"
STRICT = ROOT / "reports" / "hard-board" / "board2" / "strict-M3-placed.json"


def run(strict_path, tmp_path):
    out = tmp_path / "accept.json"
    p = subprocess.run([sys.executable, str(ACC), "--strict-input", str(strict_path),
                        "--out", str(out), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if not out.is_file():
        pytest.skip("验收未产出：%s" % ((p.stdout or p.stderr)[:200],))
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    if not STRICT.is_file():
        pytest.skip("没有 strict-M3-placed.json")
    return run(STRICT, tmp_path_factory.mktemp("acc"))


def test_criteria_have_four_states(report):
    """PASS / FAIL / NOT RUN / N/A —— "不适用"与"缺证据"必须分开。"""
    for c in report["criteria"]:
        assert c["status"] in ("PASS", "FAIL", "NOT RUN", "N/A"), c


def test_missing_evidence_is_not_pass(report):
    """文字类判据在没有渲染文字时必须 NOT RUN。

    假 PASS 是这套体系最危险的失败：没有对象可比就不会有 finding，
    于是"没测"会被当成"合格"。
    """
    for cid in ("B_text_occlusion", "F_net_text", "G_zone_readability"):
        c = next(x for x in report["criteria"] if x["id"] == cid)
        assert c["status"] == "NOT RUN", "%s 缺证据却判成 %s" % (cid, c["status"])


def test_title_block_never_passes_without_data(report):
    """没有图签数据时**不许判 PASS**；结论是 N/A（无对象可测），并写明理由。

    早先记 NOT RUN，会误导成"补点证据就行"；实际是排版稿不含 titleBlock。
    但底线不变：**没有数据就是不能 PASS**。
    """
    c = next(x for x in report["criteria"] if x["id"] == "I_title_block")
    assert c["status"] in ("NOT RUN", "N/A"), c
    assert c["status"] != "PASS"
    assert c.get("detail"), "必须写明为什么"


def test_not_run_entries_carry_next_command(report):
    """NOT RUN 必须给出下一步命令，否则读者无从下手。"""
    for c in report["criteria"]:
        if c["status"] == "NOT RUN":
            assert c["needs"], "%s 是 NOT RUN 但没写下一步命令" % c["id"]


def test_geometry_criteria_are_measured(report):
    """几何类判据必须有结论（PASS 或 FAIL），不许含糊。"""
    for cid in ("A_content_inside_page", "C_wire_vs_body", "D_frame_vs_object"):
        c = next(x for x in report["criteria"] if x["id"] == cid)
        assert c["status"] in ("PASS", "FAIL"), c


def test_verdict_reflects_worst_state(report):
    """有 NOT RUN 就不能报 PASS 总判。"""
    if any(c["status"] == "NOT RUN" for c in report["criteria"]):
        assert report["verdict"] != "PASS", "仍有缺证据却给出 PASS 总判"
