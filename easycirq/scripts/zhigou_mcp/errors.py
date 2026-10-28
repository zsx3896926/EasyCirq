"""Exceptions shared by the MCP server, tools and runners."""

from __future__ import annotations


class InvalidParams(Exception):
    """Request arguments do not satisfy the tool's JSON Schema."""


class ToolError(Exception):
    """A tool could not complete; returned to the caller as isError=true."""

    def __init__(self, code: str, message: str, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
