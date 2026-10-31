"""客户可见的四张卡不能出现工具内部术语。

目标写明：客户需理解的工具术语数 = 1（"板子"），且客户永远不需要知道
daemon / connector / typed action / KPI / gate token / 快照 / 回读。

这些文案散在四个 Go 文件里，改一处漏一处很难发现——2026-11-01 就是靠把四张卡
的输出拼起来人眼扫描，才发现卡片上还写着「PCB 检查」。于是改成静态扫描：
只读源码里的中文/英文文案，不启动 daemon。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "runtime" / "internal" / "app"

CUSTOMER_FILES = [
    "cmd_setup.go",
    "cmd_status.go",
    "cmd_card.go",
    "cmd_acceptance.go",
]

# Words the objective says the customer must never need to know. Matched
# case-insensitively inside string literals only.
FORBIDDEN = [
    "daemon",
    "connector",
    "typed action",
    "gate token",
    "快照",
    "回读",
    "gate_required",
    "apply_allowed",
]

# Strings that legitimately contain a forbidden-looking word because it is part
# of a command the customer has to type, or a product name.
ALLOWED_CONTEXTS = [
    "easycirq daemon start",   # the customer types this; the noun cannot be removed
    "easycirq connector path",
    "easycirq status",
    "easycirq card",
    "easycirq acceptance",
    "easycirq setup",
]

STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def customer_strings(path: Path):
    """Yield (line number, literal) for CUSTOMER-FACING string literals only.

    A literal that looks like a bare identifier (apply_allowed) is a field or JSON
    key, never prose a customer reads, so it is skipped.
    """
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        for match in STRING_LITERAL.finditer(line):
            literal = match.group(1)
            if re.fullmatch(r"[a-z0-9_]+", literal):
                continue  # identifier / json key
            yield index, literal


def is_allowed(literal: str) -> bool:
    return any(fragment in literal for fragment in ALLOWED_CONTEXTS)


@pytest.mark.parametrize("filename", CUSTOMER_FILES)
def test_customer_facing_strings_avoid_tool_terms(filename):
    path = APP / filename
    assert path.is_file(), f"{filename} missing"
    offenders = []
    for line_no, literal in customer_strings(path):
        lowered = literal.lower()
        if is_allowed(literal):
            continue
        for term in FORBIDDEN:
            if term.lower() in lowered:
                offenders.append((line_no, term, literal[:70]))
    assert not offenders, "客户可见文案里出现了内部术语:\n" + "\n".join(
        f"  {filename}:{line}  {term!r} in {text!r}" for line, term, text in offenders
    )


def test_the_word_pcb_is_not_shown_to_customers():
    """卡片上曾写「PCB 检查」；目标只允许「板子」。"""
    card = APP / "cmd_card.go"
    offenders = []
    for line_no, literal in customer_strings(card):
        if "PCB" in literal and not is_allowed(literal):
            offenders.append((line_no, literal[:70]))
    assert not offenders, "卡片文案里仍有 PCB:\n" + "\n".join(
        f"  cmd_card.go:{line}  {text!r}" for line, text in offenders
    )


def test_acceptance_card_keeps_its_three_checks():
    """验收卡必须还是焊接 / 上电 / 功能三项。"""
    text = (APP / "cmd_acceptance.go").read_text(encoding="utf-8")
    for word in ("焊接", "上电", "功能"):
        assert word in text, f"验收卡缺少「{word}」这一项"
