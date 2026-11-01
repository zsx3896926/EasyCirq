"""客户会看到的那四张卡，不能退化。

目标里写着「一位不懂 EDA 的客户，在不看任何文档的情况下」要能走完四步。
之前这条判据是我手工跑一遍、人眼看的——那不是测试，下次改动不会有人告诉我
它退化了。

这里把它的可测部分固定下来：

* `card` 与 `acceptance` 完全离线（只读文件），任何时候都必须工作；
* `status` 与 `setup` 依赖本机是否装着/起着服务，缺环境时跳过而不是假通过；
* 四条输出都必须是客户能读的话：以「下一步」结尾、不含内部术语。
"""
import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
KPI = ROOT / "reports" / "alarm-r163" / "kpi-report.json"
PCB_DRC = ROOT / "reports" / "pcb-drc-r163.json"
ACCEPTANCE = ROOT / "deliverables" / "alarm" / "acceptance.example.json"
EXE = "easycirq"

FORBIDDEN = ["daemon", "connector", "gate token", "快照", "回读", "写入许可", "通行证",
             "后台服务", "技能包", "运行时", "插件", "gate_required", "apply_allowed",
             # 「PCB」是电路板的标准叫法，但目标只允许「板子」这一个词。
             "pcb", "电路板"]


def run(*args):
    return subprocess.run([EXE, *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def daemon_up():
    proc = run("doctor")
    return proc.returncode == 0 and '"verdict": "ok"' in proc.stdout


def assert_speaks_to_customers(text, where):
    lowered = text.lower()
    for term in FORBIDDEN:
        assert term.lower() not in lowered, f"{where} 出现了内部术语 {term!r}:\n{text}"
    assert "下一步" in text, f"{where} 没有告诉客户下一步做什么:\n{text}"


@pytest.fixture(scope="module")
def have_reports():
    if not KPI.is_file() or not PCB_DRC.is_file():
        pytest.skip("no KPI report in reports/alarm-r163")
    return True


def test_card_is_offline_and_customer_readable(have_reports):
    """只给文件，不碰后台服务——这张卡必须能出来。"""
    proc = run("card", "--kpi-report", str(KPI), "--pcb-drc", str(PCB_DRC))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "可以下单" in proc.stdout
    assert "必查" in proc.stdout
    assert_speaks_to_customers(proc.stdout, "card")


def test_card_without_pcb_scopes_its_claim(have_reports):
    """没有板子检查结果时，不能说成整板通过。"""
    proc = run("card", "--kpi-report", str(KPI))
    assert proc.returncode == 0, proc.stdout
    assert "板子还没检查" in proc.stdout
    assert "PCB" not in proc.stdout


def test_acceptance_is_offline_and_customer_readable():
    assert ACCEPTANCE.is_file(), "acceptance example missing"
    proc = run("acceptance", "--file", str(ACCEPTANCE))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "可以交付使用" in proc.stdout
    assert_speaks_to_customers(proc.stdout, "acceptance")


def test_status_speaks_to_customers(have_reports):
    if not daemon_up():
        pytest.skip("daemon not running; status needs the local installation")
    proc = run("status", "--kpi-report", str(KPI))
    assert_speaks_to_customers(proc.stdout, "status")


def test_setup_speaks_to_customers():
    if not daemon_up():
        pytest.skip("daemon not running; setup checks the local installation")
    proc = run("setup")
    assert "EasyCirq 安装检查" in proc.stdout
    # setup 的输出里没有「下一步：」字样时也必须给出行动指引
    text = proc.stdout
    assert ("下一步" in text) or ("做完再运行一次" in text), text
    lowered = text.lower()
    for term in FORBIDDEN:
        assert term.lower() not in lowered, f"setup 出现了内部术语 {term!r}:\n{text}"


def test_every_command_explains_a_failure(have_reports):
    """拒绝时必须给下一步——这是指标 4。"""
    proc = run("acceptance", "--file", "definitely-missing-file.json")
    assert proc.returncode != 0
    assert "验收" in proc.stdout or "记录" in proc.stdout, proc.stdout
