"""Tests for the read-only Skill knowledge audit (D1–D5).

The test package is discovered both as ``tests.skill_knowledge_audit`` and as
``skill_knowledge_audit`` (CI uses ``unittest discover -s tests``).  That name
would collide with the implementation package of the same name, so load the
implementation once under the private alias ``ska_impl`` and import from it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "easycirq" / "scripts"
_PKG = _SCRIPTS / "skill_knowledge_audit"
if "ska_impl" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "ska_impl", _PKG / "__init__.py",
        submodule_search_locations=[str(_PKG)])
    if _spec is None or _spec.loader is None:  # pragma: no cover
        raise ImportError("cannot load skill_knowledge_audit implementation")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["ska_impl"] = _module
    _spec.loader.exec_module(_module)
