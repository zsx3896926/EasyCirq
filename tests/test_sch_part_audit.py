"""「查得到」是选型前置指标 —— 机制与它的陈旧性守卫。

背景（friction #42/#45）：板2 按电气参数选了 AP40P05，库记录读不出来，
一路走到 S3 要引脚几何时才炸，前面几轮全部作废。
用户的判断是对的：**这个指标应该在选器件时就前置**，而不是 S3 的惊喜。

实测全表：172 个标准件里 **15 个不可用**（11 个 unreadable + 4 个 missing），
包括 `cap.1uf_0402`、`led.yellow_0805` 这种最常用的。
"""
import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIT = ROOT / "easycirq" / "scripts" / "sch_part_audit.py"
CHECK = ROOT / "easycirq" / "scripts" / "sch_spec_check.py"
REPORT = ROOT / "reports" / "part-audit.json"
SPEC = ROOT / "reports" / "hard-board" / "board2" / "spec.json"
SP = ROOT / "easycirq" / "references" / "standard-parts.json"
BLOCKS = ROOT / "runtime" / "internal" / "blocks" / "data"

pytestmark = pytest.mark.skipif(
    not AUDIT.is_file() or not CHECK.is_file() or not REPORT.is_file(),
    reason="没有审计脚本或审计报告",
)


def test_audit_report_carries_a_fingerprint():
    """报告必须能自证新鲜度 —— 否则标准件表改了，门还在读旧结论。"""
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert d.get("schema") == "easycirq-part-audit/v1"
    assert d.get("standardPartsSha256"), "报告没有标准件表指纹"
    assert d.get("auditedAt"), "报告没有审计时间"
    assert d["parts"], "报告里没有任何器件的结论"


def test_audit_finds_the_parts_we_know_are_broken():
    """已确认读不出来的器件必须被标出来，不能悄悄算 ok。"""
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    parts = d["parts"]
    # AP40P05 是 #42 的原始病例
    assert parts.get("bjt.pmos40v_sot23", {}).get("status") == "unreadable"
    # 换上去的可读件必须 ok
    assert parts.get("mos.pmos40v_powerdi3333", {}).get("status") == "ok"
    # cap.1uf_0402 是 #45 抓出来的：最常用的电容之一，记录读不出来
    assert parts.get("cap.1uf_0402", {}).get("status") == "ok", \
        "cap.1uf_0402 已重新指向可读记录，应当 ok"

    bad = [k for k, v in parts.items() if v.get("status") != "ok"]
    assert bad, "整表不可能一个都不可用 —— 若全 ok，说明审计没真跑"


def test_spec_gate_rejects_a_part_that_is_not_ok(tmp_path):
    """spec 用了不可用的器件，S1 必须当场拦 —— 不能等到 S3。"""
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    # 注入一条不可用结论
    d["parts"]["cap.1uf_0402"] = {"partId": "cap.1uf_0402", "status": "unreadable",
                                  "detail": "构造出来的不可用"}
    bad_report = tmp_path / "audit.json"
    bad_report.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    p = subprocess.run([sys.executable, str(CHECK), str(SPEC),
                        "--blocks-dir", str(BLOCKS),
                        "--audit", str(bad_report), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    assert p.returncode != 0, "不可用器件必须让 S1 失败"
    out = json.loads(p.stdout)
    joined = "\n".join(out["problems"])
    assert "选型不可用" in joined, joined
    assert "cap.1uf_0402" in joined, joined


def test_spec_gate_rejects_a_stale_audit(tmp_path):
    """审计报告过期（标准件表改过）时不许照信 —— 陈旧证据不是证据。

    实测踩过：换了电容、报告说 unreadable，门照拦，改了表也没用。
    """
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    d["standardPartsSha256"] = "0" * 64      # 伪造一个对不上的指纹
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    p = subprocess.run([sys.executable, str(CHECK), str(SPEC),
                        "--blocks-dir", str(BLOCKS),
                        "--audit", str(stale), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    out = json.loads(p.stdout)
    joined = "\n".join(out["problems"])
    assert "过期" in joined, "指纹不符必须明说过期：%r" % joined


def test_current_audit_matches_the_current_table():
    """仓库里那份报告必须与当前标准件表同指纹，否则没人能复现。"""
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    now = hashlib.sha256(SP.read_bytes()).hexdigest()
    assert d["standardPartsSha256"] == now, \
        "报告已过期 —— 改动标准件表后要重跑 sch_part_audit.py"
