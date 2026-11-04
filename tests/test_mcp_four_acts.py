"""MCP 层必须覆盖四幕，第四幕（验收卡）曾是缺口。

2026-11-01 之前 MCP 只有 status / card / setup / apply。前三幕都能在 agents 客户端里
拿到，**唯独验收卡拿不到**——而终局判据的第四步正是「打样回来后拿到验收卡」。

Claude/Cursor 这类宿主通过 MCP 接进来，所以这一层缺一个工具，
客户就少一幕。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))

from easycirq_mcp import tools  # noqa: E402

ACCEPTANCE = ROOT / "deliverables" / "alarm" / "acceptance.example.json"
KPI = ROOT / "reports" / "alarm-r163" / "kpi-report.json"


def tool_names():
    return {item["name"] for item in tools.list_tools()}


def test_all_four_acts_are_reachable_through_mcp():
    """装 / 状态 / 卡片 / 验收 —— 四幕一个都不能少。"""
    names = tool_names()
    for required in ("easycirq_setup", "easycirq_status", "easycirq_card",
                     "easycirq_acceptance"):
        assert required in names, f"MCP 缺少 {required}，客户端会少一幕"


def test_acceptance_tool_returns_the_customer_card():
    result = tools.call_tool("easycirq_acceptance", {"record": str(ACCEPTANCE)})
    payload = json.loads(result["content"][0]["text"])
    assert payload.get("state") == "accepted", payload
    assert "交付使用" in str(payload.get("headline"))


def test_acceptance_tool_reports_a_missing_record_instead_of_passing(tmp_path):
    result = tools.call_tool("easycirq_acceptance",
                             {"record": str(tmp_path / "nope.json")})
    payload = json.loads(result["content"][0]["text"])
    assert payload.get("state") != "accepted", payload
    assert "交付使用" not in str(payload.get("headline"))


def test_acceptance_tool_schema_is_read_only():
    spec = next(t for t in tools.list_tools() if t["name"] == "easycirq_acceptance")
    annotations = spec.get("annotations") or {}
    assert annotations.get("readOnlyHint") is True
    assert annotations.get("destructiveHint") is False
    assert (spec.get("inputSchema") or {}).get("additionalProperties") is False
