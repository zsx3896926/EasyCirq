"""Deterministic schematic/PCB design engine (offline, stdlib only).

The package is intentionally separate from the EDA executor:

    evidence bundle -> canonical IR -> coverage report -> findings -> plan
    -> independent verification -> (optional) eda_exec apply

It never talks to an EDA process, never writes a project, and never turns a
missing measurement into a pass.  See ``references/design-engine.md``.
"""

IR_SCHEMA = 'design-engine-ir/v1'
ENGINE_VERSION = '1.0.0'
