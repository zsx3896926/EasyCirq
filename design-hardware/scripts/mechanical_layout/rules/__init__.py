"""Rule registry.  Each ``gN`` module exposes ``run(model) -> list[finding]``."""
from __future__ import annotations

import importlib

GROUPS = ('G1', 'G2', 'G3', 'G4')
MODULES = {'G1': 'g1', 'G2': 'g2', 'G3': 'g3', 'G4': 'g4'}


def run_rules(model, groups=None):
    selected = tuple(groups) if groups else GROUPS
    for group in selected:
        if group not in GROUPS:
            raise ValueError(f'unknown rule group {group!r}')
    findings = []
    for group in selected:
        module = importlib.import_module(f'.{MODULES[group]}', __package__)
        findings.extend(module.run(model))
    return findings


def rule_groups():
    return list(GROUPS)
