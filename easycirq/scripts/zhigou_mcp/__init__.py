"""Zhigou offline-audit MCP server (stdio).

This package exposes the repository's *offline* audit CLIs (electrical review,
return-path audit, delivery audit) as MCP tools.  It is deliberately narrow:

* read-only: it never writes into the audited input; reports go to a temporary
  directory and are returned to the caller;
* offline: no EDA/daemon/connector call, no network, no host DRC, no save/reopen;
* semantics-preserving: a module's ``unknown`` / ``review_required`` /
  ``incomplete`` status is returned verbatim and is never converted to a pass.

The protocol implementation is standard-library only and speaks MCP over stdio
(newline-delimited JSON-RPC 2.0), so any MCP-capable client can launch it with
``python -m zhigou_mcp`` (with ``easycirq/scripts`` on ``PYTHONPATH``).
"""

TOOL_VERSION = "0.1.0"
RESULT_SCHEMA = "zhigou.mcp.offline-audit-tool-result/v1"
CAPABILITIES_SCHEMA = "zhigou.mcp.offline-audit-capabilities/v1"
SERVER_NAME = "zhigou-offline-audit"

# Protocol revisions this server implements.  The initialize response echoes
# the client's revision when supported and otherwise reports our latest one.
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

__all__ = [
    "TOOL_VERSION",
    "RESULT_SCHEMA",
    "CAPABILITIES_SCHEMA",
    "SERVER_NAME",
    "PROTOCOL_VERSIONS",
    "DEFAULT_PROTOCOL_VERSION",
]
