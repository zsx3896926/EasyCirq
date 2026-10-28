"""Test-package bootstrap for ``unittest discover -s tests``.

The test directory is named ``annotation_layout`` like the shipped package.
Load the implementation explicitly (see ``_bootstrap.py``) and extend its search
path with this directory so ``annotation_layout.test_*`` remains discoverable.

This package intentionally does **not** insert ``design-hardware/scripts`` into
``sys.path``: doing so while other test packages are being discovered makes
their top-level names resolve to the implementation packages, which breaks
their later submodule imports.  Tests that need an implementation import use the
alias established here (or in ``helpers.py`` for directory-mode discovery).
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "_annotation_layout_test_bootstrap", _HERE / "_bootstrap.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_bootstrap = _load_bootstrap()
if _bootstrap is not None:
    _bootstrap.ensure_impl()
