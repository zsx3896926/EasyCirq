"""客户视角冷启动演练必须一直能走通。

这个测试模拟一个**只有安装包**的客户：在临时目录里建库、写规则、跑自检、
拿一块（合成的）板跑规则、故意改坏看它报不报。

和 `test_verify_enterprise.py` 的区别：那个用仓库里的风扇板样例，
客户机器上没有；这个只用包里的脚本 + 临时目录，谁都能跑。
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"


def run(script, args, cwd, env=None):
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(cwd), env=e)


def board(footprint="R0603", designator="R1"):
    return {"components": [
        {"designator": designator, "componentType": "part",
         "footprintRef": {"name": footprint},
         "otherProperty": {"Manufacturer Part": "X"},
         "pins": [{"pinNumber": "1", "net": "A"},
                  {"pinNumber": "2", "net": "B"}]},
    ]}


def test_customer_can_go_from_empty_to_enforcing():
    """空目录 → 建库 → 自检通过 → 板子过 → 改坏 → 拦住。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        lib = work / "knowledge"
        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib)}

        # 1. 还没建库：自检不能说"有问题"，要说"还没开始建"
        proc = run("enterprise_selfcheck.py", [], work, env)
        assert proc.returncode == 0, proc.stdout[-600:]
        assert "库里是空的" in proc.stdout

        # 2. 建库：一条能执行、带 verified_on 的规则
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [{
                "id": "no-0402", "kind": "hard", "title": "禁用 0402 封装",
                "predicate": {"type": "footprint_forbidden",
                              "patterns": ["0402"]},
                "evidence": "产线贴片下限 0603",
                "verified_on": "用一块 R0402 的板跑过，报 fail",
            }]}, ensure_ascii=False), encoding="utf-8")

        # 3. 自检通过
        proc = run("enterprise_selfcheck.py", [], work, env)
        assert proc.returncode == 0, proc.stdout[-800:]
        assert "全部可加载" in proc.stdout

        # 4. 干净板放行
        (work / "good.json").write_text(json.dumps(board("R0603")),
                                        encoding="utf-8")
        proc = run("enterprise_rules.py", ["--netlist", "good.json"], work, env)
        assert proc.returncode == 0, proc.stdout[-600:]

        # 5. 改坏必须拦住
        (work / "bad.json").write_text(json.dumps(board("R0402")),
                                       encoding="utf-8")
        proc = run("enterprise_rules.py", ["--netlist", "bad.json"], work, env)
        assert proc.returncode == 1, proc.stdout[-600:]
        assert "R0402" in proc.stdout


def test_scripts_work_from_a_copy_outside_the_repo():
    """客户机器上没有这个仓库。脚本必须能从任意目录独立运行。

    做法：把 scripts/ 整个复制到临时目录，在那里跑——如果脚本偷偷依赖
    仓库里的相对路径，这里就会失败。
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        shutil.copytree(SCRIPTS, work / "scripts")
        lib = work / "knowledge"
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [{"id": "r1", "kind": "hard", "title": "示例",
                       "predicate": {"type": "footprint_forbidden",
                                     "patterns": ["0402"]},
                       "evidence": "e", "verified_on": "v"}]},
            ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(work / "scripts" / "enterprise_selfcheck.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, cwd=str(work),
            env={**os.environ, "EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        assert proc.returncode == 0, (proc.stdout + proc.stderr)[-900:]
        assert "全部可加载" in proc.stdout
