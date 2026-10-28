"""Tests for the change-impact tool.

Because ``python -m unittest discover -s tests`` imports this directory under
the top-level name ``change_impact``, the implementation package (also called
``change_impact``, under ``design-hardware/scripts``) would be shadowed.  The
implementation is therefore loaded once under the explicit alias
``change_impact_impl`` and the test modules import from that alias::

    from change_impact_impl import model, canonical, propagate

This keeps the standard discovery command working on Python 3.10 and 3.13
without renaming either package.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / 'design-hardware' / 'scripts'
IMPLEMENTATION = SCRIPTS / 'change_impact'

if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

ALIAS = 'change_impact_impl'

if ALIAS not in sys.modules:
    if not IMPLEMENTATION.is_dir():  # pragma: no cover - defensive
        raise ImportError(f'change_impact implementation not found at {IMPLEMENTATION}')
    _spec = importlib.util.spec_from_file_location(
        ALIAS, IMPLEMENTATION / '__init__.py',
        submodule_search_locations=[str(IMPLEMENTATION)])
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[ALIAS] = _module
    _spec.loader.exec_module(_module)


def load(name):
    """Import one implementation submodule (``model``, ``propagate``, ...)."""
    return importlib.import_module(f'{ALIAS}.{name}')
