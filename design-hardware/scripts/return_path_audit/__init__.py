"""Public package surface for the offline reference-path auditor."""

from .model import TOOL_NAME, TOOL_VERSION, Model, InputError, load, validate
from .report import REPORT_SCHEMA, EXIT_CODES, build_report, render_text

__all__ = [
    "TOOL_NAME", "TOOL_VERSION", "REPORT_SCHEMA", "EXIT_CODES",
    "Model", "InputError", "load", "validate", "build_report", "render_text",
]
