"""企业器件库的「存了不生效」防护。

三条状态必须分清：
  ① 库非空但没人声明 part_key   → 必须告警（否则客户以为生效了）
  ② part_key 写了但库里没有      → 必须告警并列出库里有什么
  ③ 键对上了                      → 用实测值，且不告警
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
PARTS = SCRIPTS / "enterprise_parts.py"

sys.path.insert(0, str(ROOT / "tests"))
from test_enterprise_parts import board, intent  # noqa: E402


def run_dv(with_key, key_value="AO3400A", lib_key="AO3400A"):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "list.json").write_text(json.dumps(board()), encoding="utf-8")
        (tmp / "intent.json").write_text(
            json.dumps(intent(part_key=key_value if with_key else None),
                       ensure_ascii=False), encoding="utf-8")
        (tmp / "parts.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-parts/v1",
            "parts": {lib_key: {"value": "AO3400A",
                                "measured": {"vgs_th": 1.3}}},
        }, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ}
        env.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / "sch_design_validity.py"),
             "--netlist", str(tmp / "list.json"),
             "--intent", str(tmp / "intent.json"),
             "--enterprise-parts", str(tmp / "parts.json")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")


def test_library_without_any_part_key_is_flagged():
    """客户把实测值放进库，却没人声明 part_key —— 必须说出来。"""
    rc, out = run_dv(False)
    assert "ENTERPRISE_PARTS_UNUSED" in out, out[-900:]
    assert '"vgs_th": 1.5' in out, "没有 part_key 时应回落到默认值"


def test_wrong_part_key_is_flagged():
    """键写错了：不能静默忽略，要告诉客户库里有哪些键。"""
    rc, out = run_dv(True, key_value="WRONG_KEY")
    assert "ENTERPRISE_PART_KEY_NOT_FOUND" in out, out[-900:]
    assert "WRONG_KEY" in out


def test_matching_key_is_used_and_silent():
    rc, out = run_dv(True)
    assert '"vgs_th": 1.3' in out, out[-900:]
    assert "企业实测" in out
    assert "ENTERPRISE_PART" not in out, "命中时不该有多余告警"


def test_list_builtin_makes_keys_discoverable():
    """客户要覆盖内置器件，必须先能查到它的键。"""
    proc = subprocess.run(
        [sys.executable, str(PARTS), "--list-builtin", "--filter", "mosfet",
         "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stdout[-600:]
    report = json.loads(proc.stdout[proc.stdout.find("{"):])
    assert report["total"] > 50, "内置库应该有很多键"
    assert any("mosfet.ao3400a" in k for k in report["keys"]), report["keys"]
