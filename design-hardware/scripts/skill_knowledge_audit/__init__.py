"""Read-only Skill knowledge audit: static structure, rules and reading plans.

The package never writes inside a scanned root.  Outputs are explicit and
atomic.  It does not execute source snippets, call EDA, or touch the network.
"""
from __future__ import annotations

VERSION = "0.1.0"
SCHEMA = "skill-knowledge-audit/v1"
CATALOG_VERSION = "2026-10-27.1"
TOOL_NAME = "skill_knowledge_audit"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

NOT_PROOF = (
    "本结果只证明静态文档结构与引用关系，不证明 Skill 被客户端加载、"
    "模型遵守规则、阅读行为改变或硬件设计正确。"
)
