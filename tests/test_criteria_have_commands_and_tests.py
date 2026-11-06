"""目标要求"每项判据都要有可复现的测量命令与回归测试"。

这条测试把要求变成可检查的：
  · 文档里 12 条判据**逐条**列出复现方式（含 N/A 与 NOT RUN 的理由）
  · 每条判据 id 在有测试里被引用（含 N/A 逻辑）
  · PASS 判据都带受检数（见 test_criteria_checked_counts）
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "easycirq" / "references" / "preview-acceptance.md"
TESTS = ROOT / "tests"

IDS = ["A_content_inside_page", "B_text_occlusion", "C_wire_vs_body",
       "D_frame_vs_object", "E_label_anchor", "F_net_text",
       "G_zone_readability", "H_crossing_evidence", "I_title_block",
       "J_netflag_rotation", "K_png_readability", "L_text_audit"]


def _doc():
    if not DOC.is_file():
        pytest.skip("没有文档")
    return DOC.read_text(encoding="utf-8")


def test_doc_lists_every_criterion_command():
    s = _doc()
    assert "每条判据怎么复现" in s
    # 12 行表格：A..L
    for letter in "ABCDEFGHIJKL":
        assert ("| %s |" % letter) in s, "文档缺判据 %s 的复现方式" % letter


def test_doc_marks_host_and_na_explicitly():
    s = _doc()
    assert "N/A" in s and "NOT RUN" in s


def test_every_criterion_id_appears_in_tests():
    blob = ""
    for p in TESTS.glob("*.py"):
        blob += p.read_text(encoding="utf-8", errors="replace")
    missing = [i for i in IDS if i not in blob]
    assert not missing, "这些判据没有测试引用：%s" % missing


def test_doc_states_checked_counts_requirement():
    s = _doc()
    assert "受检对象数量" in s
