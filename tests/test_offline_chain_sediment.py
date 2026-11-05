"""沉淀的验收：离线链、页面规划、以及**技能目录同步**。

「沉淀到产品」的判据不是"仓库里有个文件"，而是：
  1. 有一条命令能跑完整条链，并报告卡在哪
  2. 技能文档里写清了怎么用、为什么这么用
  3. **各客户端技能目录里的脚本与仓库一致** —— 否则 CLI/agent 跑旧代码
"""
import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "easycirq" / "scripts"
HOME = pathlib.Path.home()

CHAIN = SCRIPTS / "sch_offline_chain.py"
PAGE_PLAN = SCRIPTS / "sch_page_plan.py"
REF = ROOT / "easycirq" / "references" / "schematic-offline-first.md"
SPEC = ROOT / "reports" / "hard-board" / "board2" / "spec.json"

# 本轮沉淀的全部脚本
NEW = [
    "sch_spec_check.py", "sch_spec_netlist.py", "sch_symbol_measure.py",
    "sch_measure_parts.py", "sch_part_audit.py", "sch_layout_input.py",
    "sch_layout_precheck.py", "sch_module_fit.py", "sch_page_plan.py",
    "sch_offline_chain.py",
]

SKILL_DIRS = [
    HOME / ".agents" / "skills" / "easycirq" / "scripts",
    HOME / ".claude" / "skills" / "easycirq" / "scripts",
    HOME / ".codex" / "skills" / "easycirq" / "scripts",
]


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_chain_and_page_plan_exist():
    assert CHAIN.is_file(), "没有统一的离线链入口"
    assert PAGE_PLAN.is_file(), "没有页面规划脚本"


@pytest.mark.parametrize("d", SKILL_DIRS, ids=lambda p: p.parts[-4])
def test_scripts_are_synced_to_the_skill_dirs(d):
    """技能目录里的脚本必须与仓库逐字节一致 —— 这是「沉淀」的硬判据。"""
    if not d.is_dir():
        pytest.skip("没有这个客户端目录")
    diff = []
    for name in NEW:
        src = SCRIPTS / name
        if not src.is_file():
            diff.append("%s 仓库缺失" % name)
            continue
        dst = d / name
        if not dst.is_file():
            diff.append("%s 未同步" % name)
        elif sha(dst) != sha(src):
            diff.append("%s 内容不一致" % name)
    assert diff == [], "技能目录与仓库不一致：%r" % diff


def test_reference_documents_the_chain():
    """文档要写清入口、两道预检、以及"先加纸别先拆"的顺序。"""
    s = REF.read_text(encoding="utf-8")
    assert "sch_offline_chain.py" in s, "文档没有链入口"
    assert "sch_layout_precheck.py" in s and "sch_module_fit.py" in s, \
        "文档没写两道预检"
    assert "先加纸" in s or "加页" in s, "文档没写『装不下先加纸』"
    assert "RECT" in s, "文档没写引脚朝外靠符号本体判定"


def test_page_plan_reports_estimate_and_confirmation_separately(tmp_path):
    """估计与确认必须分开报告 —— 公式会低估，不能拿来当定论。"""
    p1 = ROOT / "reports" / "hard-board" / "board2" / "layout-input-P1.json"
    if not p1.is_file():
        pytest.skip("没有输入")
    out = tmp_path / "plan.json"
    r = subprocess.run([sys.executable, str(PAGE_PLAN), "--input", str(p1),
                        "--out", str(out), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    assert r.returncode == 0, r.stderr[-400:]
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["schema"] == "easycirq-sch-page-plan/v1"
    assert d["confirmed"] is False, "没给 --confirm 时不许声称已确认"
    for pg in d["pages"]:
        assert "suggestedPaper" in pg
        assert pg["confirmedPaper"] is None, "未确认时 confirmedPaper 必须为空"
        assert pg["parts"] and pg["estWidth"] > 0


def test_chain_reports_where_it_stopped():
    """链要么全过、要么指出停在哪一步 —— 不许静默失败。"""
    if not CHAIN.is_file() or not SPEC.is_file():
        pytest.skip("没有链或 spec")
    r = subprocess.run([sys.executable, str(CHAIN), "--spec", str(SPEC),
                        "--out-dir", str(ROOT / "reports" / "hard-board" / "board2"),
                        "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=7200)
    d = json.loads(r.stdout[r.stdout.find("{"):])
    assert "stages" in d and d["stages"], "链没有报告任何阶段"
    for s in d["stages"]:
        assert s["name"], "阶段没有名字"
        assert s["ok"] in (True, False)
        if not s["ok"]:
            assert s["next"], "失败阶段必须给出下一步"
