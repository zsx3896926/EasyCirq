"""验收卡的判定必须能判红。

指标 6 是「交付卡与实测证据一致率 100%」。它最容易被破坏的方式不是算错数，
而是**把没有证据的东西算成通过**——一块不响的板配上「✅ 可以交付使用」。

这组测试盯的就是这条线：证据缺失、实测失败、记录不存在，三种情况都不能出绿卡。
"""
import json
import subprocess

import pytest

EXE = "easycirq"
BASE = {"schema": "easycirq-acceptance/v1", "project": "KPI-S5-Verify", "board": "probe"}


def run_acceptance(tmp_path, checks):
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps({**BASE, "checks": checks}, ensure_ascii=False), encoding="utf-8")
    return subprocess.run([EXE, "acceptance", "--file", str(path)],
                          capture_output=True, text=True, encoding="utf-8")


def check(cid, title, result, evidence):
    return {"id": cid, "title": title, "result": result, "evidence": evidence, "by": "客户"}


def test_pass_without_evidence_is_not_a_pass(tmp_path):
    """最重要的一条：写了 pass 但没有读数，不能变成绿灯。"""
    proc = run_acceptance(tmp_path, [
        check("solder", "焊接", "pass", ""),
        check("power", "上电", "pass", "5.02V"),
        check("function", "功能", "pass", "58℃ 响"),
    ])
    assert proc.returncode != 0, proc.stdout
    assert "交付使用" not in proc.stdout


def test_measured_failure_blocks_the_card(tmp_path):
    proc = run_acceptance(tmp_path, [
        check("solder", "焊接", "pass", "照片 IMG_1.jpg"),
        check("power", "上电", "pass", "5.02V"),
        check("function", "功能", "fail", "加热到 70℃ 不响"),
    ])
    assert proc.returncode != 0, proc.stdout
    assert "交付使用" not in proc.stdout


def test_three_measured_passes_are_accepted(tmp_path):
    proc = run_acceptance(tmp_path, [
        check("solder", "焊接", "pass", "照片 IMG_1.jpg"),
        check("power", "上电", "pass", "5.02V / 3.29V"),
        check("function", "功能", "pass", "58℃ 响，55℃ 停"),
    ])
    assert proc.returncode == 0, proc.stdout
    assert "可以交付使用" in proc.stdout


def test_missing_record_is_not_a_pass(tmp_path):
    proc = subprocess.run([EXE, "acceptance", "--file", str(tmp_path / "nope.json")],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 2, proc.stdout
    assert "交付使用" not in proc.stdout


def test_a_pending_check_warns_instead_of_passing(tmp_path):
    """result=pending（还没测）既不是 pass 也不是 fail。"""
    proc = run_acceptance(tmp_path, [
        check("solder", "焊接", "pass", "照片 IMG_1.jpg"),
        check("power", "上电", "pending", "还没上电"),
        check("function", "功能", "pass", "58℃ 响"),
    ])
    assert proc.returncode != 0, proc.stdout
    assert "可以交付使用" not in proc.stdout
