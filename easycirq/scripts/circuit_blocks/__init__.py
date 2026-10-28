"""Parameterized standard circuit blocks for the EasyCirq skill.

Offline, deterministic generators that turn declared constraints into a
mathematical + connectivity contract for a small set of recurring circuits.
They do **not** bind EDA library parts, query marketplaces, draw production
schematics or claim hardware sign-off.  See
``docs/parallel-circuit-blocks/contract.md``.

Entry point: ``python -m circuit_blocks`` (run from ``easycirq/scripts``
or with that directory on ``PYTHONPATH``).
"""
from __future__ import annotations

__all__ = ['__version__', 'TOOL_NAME', 'RESULT_SCHEMA', 'DESIGN_SCHEMA']

TOOL_NAME = 'circuit-blocks'
__version__ = '0.1.0'
RESULT_SCHEMA = 'circuit-blocks/module-result/1'
DESIGN_SCHEMA = 'circuit-blocks/design/1'
