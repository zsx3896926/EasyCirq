"""Test-package bootstrap.

When the repository runner imports this directory as the package
``annotation_layout``, the tests still need the *shipped* package
(``design-hardware/scripts/annotation_layout``) under the same name.  Load it
explicitly from its file path (never by name, which could recurse back here) and
extend its search path with this test directory so unittest discovery can still
import ``annotation_layout.test_*`` modules.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parents[1] / "design-hardware" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

if __name__ != "tests.annotation_layout":
    _package_dir = _SCRIPTS / "annotation_layout"
    _package_init = _package_dir / "__init__.py"
    _current = sys.modules.get("annotation_layout")
    if _package_init.is_file() and (_current is None
                                    or _current is sys.modules.get(__name__)):
        try:
            _spec = importlib.util.spec_from_file_location(
                "annotation_layout", _package_init,
                submodule_search_locations=[str(_package_dir)])
            if _spec is not None and _spec.loader is not None:
                _impl = importlib.util.module_from_spec(_spec)
                sys.modules["annotation_layout"] = _impl
                _spec.loader.exec_module(_impl)
                _impl.__path__ = list(_impl.__path__) + [str(_HERE)]
        except Exception:
            # Leave the environment usable for a clear test failure rather than
            # hiding it behind an import-time crash.
            pass
