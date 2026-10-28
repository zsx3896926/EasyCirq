"""Shared helpers for skill_knowledge_audit tests."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "easycirq" / "scripts"
SKILL_ROOT = REPO / "easycirq"
BENCH = REPO / "benchmarks" / "skill-knowledge-audit"

sys.path.append(str(SCRIPTS))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_corpus(tmp):
    """A small Skill-like tree exercising link and anchor edge cases."""
    root = Path(tmp) / "easycirq"
    write(root / "SKILL.md", """---
name: demo-skill
description: demo
---

# Demo Skill

## 开始

先读 [流程](refs/workflow.md)。
当涉及 PCB 时读取 [PCB 布局](refs/pcb.md#pcb-布局)。
背景资料：[背景](refs/background.md)。
[坏路径](refs/missing.md)
[坏锚点](refs/workflow.md#不存在的锚点)
[前缀锚点](refs/pcb.md#g1-ldo)
[占位路径](<path/to/example.md>)
![示意图](assets/diagram.png)

```text
[代码块里的链接](refs/not-a-page.md)
python scripts/tool.py --demo
```

真实脚本引用：`python scripts/tool.py`，缺失脚本 `scripts/missing_tool.py`。

## G1 LDO（低压差）

正文。
""")
    write(root / "refs" / "workflow.md", """# 流程

先读 [PCB 布局](pcb.md#pcb-布局)。
""")
    write(root / "refs" / "pcb.md", """# PCB 布局

## G1 LDO（低压差）

正文。
""")
    write(root / "refs" / "background.md", "# 背景\n\n背景资料。\n")
    write(root / "assets" / "diagram.png", "not-a-real-png")
    write(root / "scripts" / "tool.py", "# demo tool\n")
    return root


def tree_hashes(root):
    hashes = {}
    for path in sorted(Path(root).rglob("*")):
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def strip_volatile(result):
    clone = json.loads(json.dumps(result))
    source = clone.get("source") or {}
    source.pop("scanned_at", None)
    source.pop("duration_ms", None)
    source.pop("root", None)
    clone.pop("written", None)
    clone.pop("load_warnings", None)
    return clone


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def first_scenario(scenarios, task_type):
    for scenario in scenarios:
        if scenario["intent"]["task_type"] == task_type:
            return scenario
    raise AssertionError("no scenario for task type " + task_type)
