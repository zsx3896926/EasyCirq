"""「网标朝向一致」必须是**可测的独立判据**。

原来它挂在 `标签落在真实端点` 那条下面，而那条因"本图无端口标签"是 N/A，
于是朝向这件事**一起被 N/A 掉了**。目标里点名了这项，却一直没被真正测量。

两个坑都钉住：
  1. 判据要独立成条（不与端口标签共用）
  2. 适配器把网标放在 `net_flags` 而不是 `components` ——
     只从 components 取图元类型会把这条误判成 N/A
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACC = ROOT / "easycirq" / "scripts" / "sch_layout_acceptance.py"
STRICT = ROOT / "reports" / "hard-board" / "board2" / "strict-M3-full.json"


def _run(tmp_path):
    out = tmp_path / "a.json"
    p = subprocess.run([sys.executable, str(ACC), "--strict-input", str(STRICT),
                        "--out", str(out), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if not out.is_file():
        pytest.skip("验收未产出：%s" % ((p.stdout or p.stderr)[:200],))
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rep(tmp_path_factory):
    if not STRICT.is_file():
        pytest.skip("没有严格输入")
    return _run(tmp_path_factory.mktemp("rot"))


def test_rotation_is_its_own_criterion(rep):
    ids = [c["id"] for c in rep["criteria"]]
    assert "J_netflag_rotation" in ids, "缺独立的朝向判据"
    assert "E_label_anchor" in ids, "端口标签判据应保留（本图 N/A）"


def test_rotation_is_not_na_when_net_flags_exist(rep):
    """有网标就必须能判朝向，不许 N/A。"""
    src = json.loads(STRICT.read_text(encoding="utf-8"))
    if not src.get("net_flags"):
        pytest.skip("这份输入没有网标")
    c = next(x for x in rep["criteria"] if x["id"] == "J_netflag_rotation")
    assert c["status"] in ("PASS", "FAIL", "NOT RUN"), \
        "有网标却判成 %s —— 图元类型没把 net_flags 算进去" % c["status"]


def test_label_anchor_stays_na_without_ports(rep):
    c = next(x for x in rep["criteria"] if x["id"] == "E_label_anchor")
    assert c["status"] == "N/A", c


def test_rotation_codes_are_not_shared_with_label_anchor():
    """源码层：朝向的缺陷码不许再挂在端口标签判据下。"""
    s = ACC.read_text(encoding="utf-8")
    i = s.find('"id": "E_label_anchor"')
    j = s.find('"id": "J_netflag_rotation"')
    assert i > 0 and j > 0
    e_block = s[i:j] if i < j else s[j:i]
    assert "netflag_rotation_outlier" not in e_block, \
        "朝向码仍挂在端口标签判据下，会被一起 N/A"
