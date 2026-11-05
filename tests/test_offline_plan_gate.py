"""机制三件套的验收：闸门（拦）→ 交付卡（不放绿）→ 面板（看得见）。

背景 friction #40：产品文档写着「未过 S2 不得进器件」「apply_allowed 才允许上机」，
但那只是**一句话**。板1/板2 前几十轮跳过 S1–S4 直接落图，之后一直在补几何。
文档管不住人，机制才管得住 —— 这三条分别钉住机制的三层。
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


def _run(*args):
    p = subprocess.run([str(EXE)] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def test_plan_status_reports_all_four_stages():
    """面板要渲染四阶段，所以 CLI 必须逐阶段给出状态，不能只说"没有回执"。"""
    code, out, _ = _run("sch", "plan-status", "--json",
                        "--project", "__plan-status-test__")
    d = json.loads(out)
    ids = [s["id"] for s in d.get("stages") or []]
    assert ids == ["S1", "S2", "S3", "S4"], "四阶段都要在，顺序 S1→S4：%r" % ids
    assert d.get("gate") in ("open", "closed")
    # 没回执时必须是 closed 且给出怎么补
    assert d["gate"] == "closed"
    assert d.get("howTo"), "闸门关着就要给凑证据的步骤"
    for st in d["stages"]:
        assert st.get("status") in ("done", "pending", "missing"), st
        assert st.get("name"), "每一阶段都要有可读名字"


def test_block_apply_refuses_without_plan_receipt():
    """闸门第一层：没有回执，落块必须被拒（不是警告）。"""
    code, out, err = _run("sch", "block-apply", "block.led_indicator_gpio",
                          "--project", "__no-such-project-for-gate-test__")
    text = out + err
    assert code != 0, "没有离线规划回执时 block-apply 必须非零退出"
    assert "离线规划闸门" in text, "要说清被哪道门拦的"
    assert "plan-ack" in text, "要给出凑证据的确切命令"


def test_card_refuses_a_board_without_plan_receipt():
    """闸门第二层：交付卡不许给绕过流程的板子绿卡。

    这是"能起点火，还要有烟雾报警"的那一半 —— 只拦落块不够，
    因为 `--unplanned` 可以绕过落块，但它不该能绕过交付判词。
    """
    code, out, _ = _run("card", "--project", "__no-such-project-for-card-test__")
    text = out
    # 没测过的板子保持 not_measured（A5 的判据），但**必须同时说出流程缺口** ——
    # 否则用户以为"去跑一次检查就行"，而实际连离线规划都没做。
    assert ("还不能打样" in text) or ("还没检查过" in text), \
        "绕过流程的板子不能是绿卡：%r" % text[:300]
    assert "离线规划" in text, "必须把流程缺口说出来：%r" % text[:300]
    assert ("S1" in text and "S4" in text), "要说清缺的是哪几阶段：%r" % text[:300]


def test_panel_visualises_the_offline_plan():
    """闸门第三层：面板上要能看见卡在哪一步。"""
    page = HTML.read_text(encoding="utf-8")
    assert 'id="planCard"' in page, "面板没有离线规划卡"
    assert "function renderPlan" in page, "没有渲染函数"
    assert "renderPlan(snap.plan)" in page, "render 里没调用"
    # 状态必须"色+文+图标"三件套，不能只靠颜色
    assert '"✓"' in page and '"✗"' in page, "阶段状态要用图标，不能只靠颜色"
    # 闸门关着时要说清它意味着什么
    assert "未过 S2 不得进器件" in page, "要把这句话直接显示在面板上"

    go = (ROOT / "runtime" / "internal" / "app" / "cmd_panel.go").read_text(encoding="utf-8")
    assert '"sch", "plan-status", "--json"' in go, "snapshot 没有取 plan-status"
