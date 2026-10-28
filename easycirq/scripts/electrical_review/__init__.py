"""Offline electrical-intent review (智构任务 B).

Reads a single JSON design snapshot, never talks to EDA or the network, and
emits a deterministic evidence-bearing report.  See
``docs/parallel-electrical-review/`` for the contract and rule semantics.
"""

__all__ = ["SCHEMA_INPUT", "SCHEMA_REPORT", "TOOL_VERSION"]

TOOL_NAME = "electrical_review"
TOOL_VERSION = "0.1.0"
SCHEMA_INPUT = "easycirq.electrical-review.input/v1"
SCHEMA_REPORT = "easycirq.electrical-review.report/v1"
MIN_PYTHON = (3, 10)
