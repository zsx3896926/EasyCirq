"""Load the shipped ``annotation_layout`` implementation under its own name.

The test directory is also called ``annotation_layout``.  During
``python -m unittest discover -s tests`` the test directory would be imported as
that top-level package, shadowing the implementation.  Load the implementation
explicitly from its file path instead of by name, then extend its search path
with this test directory so discovery can still import
``annotation_layout.test_*``.

Important: this module must not mutate ``sys.path``.  The repository test suite
discovers several task packages whose top-level names also exist under
``design-hardware/scripts``; inserting that directory at ``sys.path[0]`` while a
package is imported makes later test packages resolve to their implementations
instead of their test directories (import-time ``ModuleNotFoundError``).  See
``docs/parallel-annotation-layout/handoff-current.md``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "design-hardware" / "scripts"
IMPLEMENTATION = SCRIPTS / "annotation_layout"


def ensure_impl():
    """Return the shipped package, bound as ``annotation_layout``."""
    current = sys.modules.get("annotation_layout")
    current_file = None
    if current is not None:
        try:
            current_file = Path(getattr(current, "__file__", "") or "").resolve()
        except (OSError, TypeError):
            current_file = None
    is_impl = (current is not None and current_file is not None
               and IMPLEMENTATION in current_file.parents)
    if is_impl:
        impl = current
    else:
        init = IMPLEMENTATION / "__init__.py"
        if not init.is_file():  # pragma: no cover - defensive
            return current
        spec = importlib.util.spec_from_file_location(
            "annotation_layout", init,
            submodule_search_locations=[str(IMPLEMENTATION)])
        if spec is None or spec.loader is None:  # pragma: no cover
            return current
        impl = importlib.util.module_from_spec(spec)
        sys.modules["annotation_layout"] = impl
        spec.loader.exec_module(impl)
    paths = list(getattr(impl, "__path__", []))
    if str(HERE) not in paths:
        impl.__path__ = paths + [str(HERE)]
    return impl
