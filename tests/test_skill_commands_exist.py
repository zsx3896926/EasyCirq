"""SKILL.md 里提到的每条命令都必须真实存在。

为什么需要：文档写了 `easycirq pcb outline-fit` 但工具没有这条子命令，比文档
缺一句话更糟——照着做的 agent 会卡在一个不存在的命令上，而且很难判断是自己
拼错了还是工具没有。

这个测试把「文档里出现过的命令」逐条跑 `--help`，确认不是 unknown command。
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "easycirq" / "SKILL.md"

# Frontmatter keys and prose that the crude regex picks up. Kept as a small
# allowlist rather than a smarter parser: the point is the command coverage, not
# YAML fidelity.
NOT_COMMANDS = {"description", "name"}


def mentioned_commands():
    text = SKILL.read_text(encoding="utf-8")
    found = set()
    for raw in re.findall(r"easycirq\s+([a-z][\w.-]*(?:\s+[a-z][\w.-]*)?)", text):
        command = " ".join(raw.split())
        if not command or command.startswith("-"):
            continue
        parts = command.split()
        if len(parts) > 2:
            continue
        if parts[0] in NOT_COMMANDS:
            continue
        found.add(command)
    return sorted(found)


def resolves(command: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["easycirq"] + command.split() + ["--help"],
        capture_output=True, timeout=30,
    )
    text = (proc.stdout or b"").decode("utf-8", "replace") + \
           (proc.stderr or b"").decode("utf-8", "replace")
    return "unknown command" not in text.lower(), text


def test_skill_exists():
    assert SKILL.is_file(), "SKILL.md missing"
    assert mentioned_commands(), "no commands found - did the regex break?"


@pytest.mark.parametrize("command", mentioned_commands())
def test_mentioned_command_exists(command):
    ok, text = resolves(command)
    assert ok, f"SKILL.md mentions 'easycirq {command}' but the CLI does not have it:\n{text[:300]}"


def test_skill_names_all_four_customer_commands():
    """四个客户命令必须都在契约里出现过。

    不能断言 "easycirq card" 这个完整字符串：文中写作
    "`easycirq status` / `card`" 这类缩写形式，命令名单独出现即算提到。
    """
    text = SKILL.read_text(encoding="utf-8")
    for verb in ("setup", "status", "card", "acceptance"):
        assert re.search(r"\b" + verb + r"\b", text), \
            f"SKILL.md never mentions the '{verb}' command"
