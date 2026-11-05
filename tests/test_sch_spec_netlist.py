"""规范网表生成器的验收，以及 S1 spec 的一条新一致性规则。

「spec → 规范网表」这一步以前是空白：style-plan 只画框，而 S3 的度量要器件级网表。
补上之后有两个必须钉住的性质：

  1. **NC 的引脚不许有网**。给它一张只有它自己的网，在 KPI「未连接/悬空=0」里
     就是违规 —— 而 spec 明说它不接。
  2. **NC 与 bind_to 互斥**。实测踩过：spec 把 M4:EN 列进 nc，同时又 bind_to=+5V，
     于是网表里它是接的、NC 清单里它是不接的，两边都"有据"。
"""
import json
import pathlib
import subprocess
import sys
from collections import Counter

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = ROOT / "easycirq" / "scripts" / "sch_spec_netlist.py"
CHECK = ROOT / "easycirq" / "scripts" / "sch_spec_check.py"
SPEC = ROOT / "reports" / "hard-board" / "board2" / "spec.json"
BLOCKS = ROOT / "runtime" / "internal" / "blocks" / "data"

pytestmark = pytest.mark.skipif(
    not GEN.is_file() or not SPEC.is_file() or not BLOCKS.is_dir(),
    reason="没有生成器 / spec / 块库",
)


def generate(tmp_path, spec_path=None):
    out = tmp_path / "netlist.json"
    p = subprocess.run([sys.executable, str(GEN), str(spec_path or SPEC),
                        "--blocks-dir", str(BLOCKS), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    return p, out


def test_netlist_generates_without_dangling_nets(tmp_path):
    p, out = generate(tmp_path)
    assert p.returncode == 0, p.stderr[-800:]
    doc = json.loads(out.read_text(encoding="utf-8"))

    assert doc["schemaVersion"]
    assert doc["projectId"] == "23ce6e4eb178464cb0b709920da3b26c"
    assert len(doc["components"]) == 56, "板2 应当生成 56 个器件"
    assert len(doc["nets"]) >= 20

    # 没有单成员网 = 没有悬空
    per_net = Counter(c["netId"] for c in doc["connections"])
    single = [n["name"] for n in doc["nets"] if per_net.get(n["id"], 0) <= 1]
    assert single == [], "出现单成员网（悬空）：%r" % single

    # 每个器件至少有一个引脚
    for c in doc["components"]:
        assert c["pins"], "器件 %s 没有引脚" % c["ref"]


def test_nc_pins_are_no_connect_and_carry_no_net(tmp_path):
    """NC 的引脚必须落成 noConnected，且**不产生任何连接**。"""
    p, out = generate(tmp_path)
    assert p.returncode == 0
    doc = json.loads(out.read_text(encoding="utf-8"))

    ncs = doc.get("noConnectDeclarations") or []
    assert ncs, "板2 有 NC-1（IGN_12V），必须留下声明"
    nc_pins = {(c["ref"], pin["number"])
               for c in doc["components"] for pin in c["pins"]
               if pin.get("noConnected")}
    assert nc_pins, "没有任何 noConnected 引脚标记"

    # NC 引脚不许出现在 connections 里
    for cid, pin in {(c["id"], p_["number"]) for c in doc["components"]
                     for p_ in c["pins"] if p_.get("noConnected")}:
        hits = [c for c in doc["connections"]
                if c["componentId"] == cid and c["pinNumber"] == pin]
        assert hits == [], "NC 引脚 %s:%s 竟然有连接" % (cid, pin)


def test_spec_checker_rejects_nc_that_is_also_bound(tmp_path):
    """NC 与 bind_to 只能取一 —— 两头都写必须被拒。"""
    d = json.loads(SPEC.read_text(encoding="utf-8"))
    d["nc"].append({"id": "NC-X", "pin": "M4:EN", "reason": "故意制造矛盾"})
    bad = tmp_path / "conflict.json"
    bad.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    p = subprocess.run([sys.executable, str(CHECK), str(bad),
                        "--blocks-dir", str(BLOCKS), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    assert p.returncode != 0, "NC 与 bind_to 冲突时必须被拒"
    out = json.loads(p.stdout)
    joined = "\n".join(out["problems"])
    assert "只能取一" in joined, joined


def test_netlist_is_deterministic(tmp_path):
    """同一份 spec 跑两次必须得到同样的位号与网号 —— 否则没法做前后 diff。"""
    _, a = generate(tmp_path / "a" if (tmp_path / "a").mkdir() is None else tmp_path)
    _, b = generate(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path)
    da = json.loads(a.read_text(encoding="utf-8"))
    db = json.loads(b.read_text(encoding="utf-8"))
    assert [(c["ref"], c["device"]["name"]) for c in da["components"]] == \
           [(c["ref"], c["device"]["name"]) for c in db["components"]]
    assert [n["name"] for n in da["nets"]] == [n["name"] for n in db["nets"]]
