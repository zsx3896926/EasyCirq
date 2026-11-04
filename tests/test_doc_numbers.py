"""文档里的数字必须与实现一致。

这个仓库已经被同一类漂移咬过三次：KPI 从 15 加到 16、再到 17，每次只改了当时
正在看的那份文档，其余几份继续说着旧数字。人眼发现不了，所以让测试来数。
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "metrics" / "schematic-kpi.v1.json"
SKILL = ROOT / "easycirq" / "SKILL.md"

# Files that quote the number of checks to a reader.
NARRATIVE_FILES = [
    ROOT / "easycirq" / "SKILL.md",
    ROOT / "docs" / "ultimate-goal.md",
    ROOT / "docs" / "traceability-alarm.md",
]


def actual_kpi_count() -> int:
    data = json.loads(METRICS.read_text(encoding="utf-8"))
    return len(data["kpis"])


def test_the_definition_is_a_sane_size():
    count = actual_kpi_count()
    assert 10 <= count <= 30, f"KPI count {count} looks wrong"


@pytest.mark.parametrize("path", NARRATIVE_FILES, ids=lambda p: p.name)
def test_narrative_docs_quote_the_real_count(path):
    """Any 'N 项 KPI' / 'N 项指标' / 'N 项门禁' must equal the real count."""
    if not path.is_file():
        pytest.skip(f"{path.name} not present")
    expected = actual_kpi_count()
    text = path.read_text(encoding="utf-8")
    wrong = []
    for match in re.finditer(r"(\d+)\s*项\s*(KPI|指标|门禁|定义)", text):
        number = int(match.group(1))
        if number != expected:
            line = text[: match.start()].count("\n") + 1
            wrong.append((line, number, match.group(0)))
    assert not wrong, (
        f"{path.name} quotes {expected - 1 if expected else '?'} or another number, "
        f"but the definition has {expected} checks:\n"
        + "\n".join(f"  line {line}: {fragment!r}" for line, _, fragment in wrong)
    )


def test_skill_never_claims_a_stale_layer_count():
    """Gerber 层数跟着板子走；写死一个数字就会过时（11 -> 12 已经发生过）。"""
    text = SKILL.read_text(encoding="utf-8")
    # A fixed claim like "11 层" alone is fine only inside the comparison table;
    # assert instead that the guidance points at the layer list.
    assert "层数不是固定的" in text or "层清单" in text, (
        "SKILL.md should tell the reader to check the layer list rather than a fixed count"
    )
