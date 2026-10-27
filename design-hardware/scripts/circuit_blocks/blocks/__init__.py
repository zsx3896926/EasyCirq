"""Block registry.

Every module in this package that subclasses :class:`~circuit_blocks.blocks.base.Block`
and sets a non-empty ``MODULE_TYPE`` is discovered automatically, so adding a
block is a single-file change with no shared registry edit.  Import order is
sorted by module filename to keep help output and error ordering deterministic.
"""
from __future__ import annotations

import importlib
import pkgutil

from .base import Block

_SKIP = {'base', 'helpers'}


def _discover():
    registry = {}
    package = importlib.import_module(__name__)
    for module_info in sorted(pkgutil.iter_modules(package.__path__),
                              key=lambda item: item.name):
        if module_info.name.startswith('_') or module_info.name in _SKIP:
            continue
        module = importlib.import_module('%s.%s' % (__name__, module_info.name))
        for attribute in sorted(vars(module)):
            candidate = getattr(module, attribute)
            if (isinstance(candidate, type) and issubclass(candidate, Block)
                    and candidate is not Block and candidate.MODULE_TYPE):
                if candidate.MODULE_TYPE in registry and registry[candidate.MODULE_TYPE] is not candidate:
                    raise RuntimeError('duplicate module_type %r' % candidate.MODULE_TYPE)
                registry[candidate.MODULE_TYPE] = candidate()
    return registry


REGISTRY = _discover()


def get(module_type):
    if module_type not in REGISTRY:
        raise KeyError(module_type)
    return REGISTRY[module_type]


def module_types():
    return sorted(REGISTRY)
