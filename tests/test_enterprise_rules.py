"""企业规则：可执行的部分。

这个模块的核心承诺是「企业写的规则，下一次真的会执行」。
所以每条测试都是**故意违反 → 必须报错**，而不是"加载成功了"。
"""
import json
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "easycirq" / "scripts" / "enterprise_rules.py"
EXAMPLE = ROOT / "examples" / "enterprise-knowledge" / "rules.company.json"


def run(args, env=None):
    import os
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, cwd=str(ROOT), env=e)


def board(footprint="R0603", mpn="0603WAF1002T5E", nets=("PWR5V", "GND")):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "manufacturerId": mpn,
         "footprintRef": {"name": footprint},
         "otherProperty": {"Manufacturer Part": mpn},
         "pins": [{"pinNumber": str(i + 1), "net": n}
                  for i, n in enumerate(nets)]},
    ]}


def write_rules(dirpath, rules, name="rules.json"):
    path = pathlib.Path(dirpath) / name
    path.write_text(json.dumps({"schema": "easycirq-enterprise-rules/v1",
                                "rules": rules}, ensure_ascii=False),
                    encoding="utf-8")
    return path


def run_rules(rule_file, netlist):
    with tempfile.TemporaryDirectory() as tmp:
        nl = pathlib.Path(tmp) / "list.json"
        nl.write_text(json.dumps(netlist, ensure_ascii=False), encoding="utf-8")
        return run(["--netlist", str(nl), "--rule", str(rule_file),
                    "--json"])


def test_forbidden_footprint_actually_fails():
    """企业禁用 0402，板上真有 0402 → 必须 fail 且退出码 1。"""
    proc = run_rules(EXAMPLE, board(footprint="R0402"))
    assert proc.returncode == 1, proc.stdout[-800:]
    report = json.loads(proc.stdout[proc.stdout.find("{"):])
    assert report["verdict"] == "fail"
    rule = next(r for r in report["results"] if r["id"] == "no-0402-packaging")
    assert rule["status"] == "fail"
    assert "R0402" in " ".join(rule["violations"])
    # 违规要说清找谁
    assert rule.get("owner")
    assert rule.get("evidence")


def test_clean_board_passes():
    proc = run_rules(EXAMPLE, board(footprint="R0603", mpn="0603WAF1002T5E"))
    assert proc.returncode == 0, proc.stdout[-800:]
    report = json.loads(proc.stdout[proc.stdout.find("{"):])
    assert report["verdict"] == "pass"


def test_banned_part_fails():
    proc = run_rules(EXAMPLE, board(mpn="S8050"))
    assert proc.returncode == 1, proc.stdout[-800:]
    report = json.loads(proc.stdout[proc.stdout.find("{"):])
    rule = next(r for r in report["results"] if r["id"] == "banned-transistor")
    assert rule["status"] == "fail"


def test_advisory_rule_warns_without_failing():
    """advisory 规则违反时只提示，退出码仍是 0 —— 这是"不能阻断"的那一类。"""
    proc = run_rules(EXAMPLE, board(nets=("TEST_POINT", "GND")))
    assert proc.returncode == 0, proc.stdout[-800:]
    report = json.loads(proc.stdout[proc.stdout.find("{"):])
    rule = next(r for r in report["results"] if r["id"] == "no-test-net-naming")
    assert rule["status"] == "fail"
    assert rule["kind"] == "advisory"
    assert report["verdict"] == "advisory"


def test_unknown_predicate_is_a_problem_not_silently_skipped():
    """不认识的谓词 = 执行不了。**不许静默跳过**，否则企业以为规则生效了。"""
    with tempfile.TemporaryDirectory() as tmp:
        rule_file = write_rules(tmp, [{
            "id": "made-up", "kind": "hard", "title": "假规则",
            "predicate": {"type": "does_not_exist"},
        }])
        proc = run_rules(rule_file, board())
        report = json.loads(proc.stdout[proc.stdout.find("{"):])
        assert report["problems"], "不支持的谓词必须进 problems"
        assert any("does_not_exist" in p["error"] for p in report["problems"])
        assert report["verdict"] == "not_run"


def test_missing_explicit_path_is_an_error():
    """显式给的规则文件不存在 → 必须报错，不许当"没有规则"通过。"""
    proc = run(["--describe", "--rule", "no/such/rules.json"])
    assert proc.returncode != 0, proc.stdout[-500:]
    assert "不存在" in proc.stdout or "不存在" in (proc.stderr or "")


def test_enterprise_layer_is_loaded_without_explicit_flag():
    """企业把规则放进知识目录，**不加任何参数**也要被加载并执行。"""
    with tempfile.TemporaryDirectory() as tmp:
        write_rules(tmp, [{
            "id": "no-0402-packaging", "kind": "hard", "title": "禁用 0402",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
        }])
        nl = pathlib.Path(tmp) / "list.json"
        nl.write_text(json.dumps(board(footprint="R0402"), ensure_ascii=False),
                      encoding="utf-8")
        proc = run(["--netlist", str(nl)],
                   env={"EASYCIRQ_KNOWLEDGE_DIR": tmp})
        assert proc.returncode == 1, proc.stdout[-800:]
        report = json.loads(proc.stdout[proc.stdout.find("{"):]) \
            if "--json" in proc.args else None
        assert "no-0402-packaging" in proc.stdout
        assert "fail" in proc.stdout


def test_project_layer_overrides_enterprise_layer():
    """同 id 的规则，项目层覆盖企业层 —— 优先级的实现要真的生效。"""
    with tempfile.TemporaryDirectory() as ent, tempfile.TemporaryDirectory() as proj:
        write_rules(ent, [{
            "id": "shared", "kind": "hard", "title": "企业版",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
        }], name="ent.json")
        kdir = pathlib.Path(proj) / ".easycirq" / "knowledge"
        kdir.mkdir(parents=True)
        write_rules(kdir, [{
            "id": "shared", "kind": "advisory", "title": "项目版",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
        }], name="proj.json")
        nl = pathlib.Path(proj) / "list.json"
        nl.write_text(json.dumps(board(footprint="R0402"), ensure_ascii=False),
                      encoding="utf-8")
        proc = run(["--netlist", str(nl), "--project-dir", proj, "--json"],
                   env={"EASYCIRQ_KNOWLEDGE_DIR": ent})
        report = json.loads(proc.stdout[proc.stdout.find("{"):])
        rule = next(r for r in report["results"] if r["id"] == "shared")
        # 项目版把 hard 降成 advisory，所以整体不该是 fail
        assert rule["kind"] == "advisory", report["results"]
        assert report["verdict"] == "advisory"
