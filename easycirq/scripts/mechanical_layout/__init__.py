"""Mechanical layout planner for the 智构 hardware design skill.

Offline, deterministic 2D/2.5D mechanical anchoring analysis.  It is *not* an
EDA executor and never writes a PCB: every candidate is an ``only_planned``
pose proposal that a later, separately reviewed integration may use.

Schemas:
  * input:  ``mechanical-layout/v1``   (:mod:`mechanical_layout.model`)
  * audit:  ``mechanical-layout-report/v1``
  * plan:   ``mechanical-layout-plan/v1``
"""
from __future__ import annotations

__version__ = '0.1.0'

INPUT_SCHEMA = 'mechanical-layout/v1'
AUDIT_SCHEMA = 'mechanical-layout-report/v1'
PLAN_SCHEMA = 'mechanical-layout-plan/v1'

# Exit codes are part of the CLI contract; tests assert them.
EXIT_OK = 0
EXIT_REVIEW = 1
EXIT_INVALID = 2
EXIT_BLOCKED = 3
EXIT_NO_CANDIDATE = 3
EXIT_SEARCH_INCOMPLETE = 4
EXIT_NOT_FOUND = 5

ANALYSIS_WATERMARK = 'analysis_not_official_export'
