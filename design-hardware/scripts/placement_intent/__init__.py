"""Offline placement-intent (HMT + CCG) validation and planning.

This package is stdlib-only.  It reads one JSON file, validates a hierarchical
module tree (HMT) plus a relative constraint graph (CCG), and -- when the input
is self-sufficient -- derives a module-relative, hierarchical "plan only"
layout.  It never writes to a project, never calls EDA/daemon/connector and
never touches the network.
"""
from __future__ import annotations

TOOL_NAME = "placement_intent"
TOOL_VERSION = "0.1.0"
MIN_PYTHON = (3, 10)

SCHEMA_INPUT = "zhigou.placement-intent.input/v1"
SCHEMA_VALIDATION = "zhigou.placement-intent.validation/v1"
SCHEMA_PLAN = "zhigou.placement-intent.plan/v1"
SCHEMA_EXPLAIN = "zhigou.placement-intent.explain/v1"
SCHEMA_ERROR = "zhigou.placement-intent.error/v1"

ROTATIONS = (0, 90, 180, 270)
ANCHORS = ("top-left", "top-right", "bottom-left", "bottom-right", "center")
SUPPORTED_ANCHORS = ("top-left",)

SOURCE_TYPES = (
    "host_export",
    "manual_declaration",
    "synthetic_fixture",
    "derived",
)
PROVENANCE_KINDS = ("synthetic", "derived", "manual")
NODE_SOURCE_KINDS = ("user", "guideline", "derived")
CONSTRAINT_SOURCE_KINDS = (
    "user",
    "guideline",
    "derived",
    "datasheet",
    "project_policy",
    "synthetic",
)

HEX64 = frozenset("0123456789abcdef")

DEFAULT_POLICY = {
    "max_depth": 6,
    "default_allowed_rotations": [0, 90, 180, 270],
    "position_tolerance_mm": 1e-6,
    "weight_epsilon": 1e-9,
}

#: Tolerance used when comparing rotations (degrees); not configurable.
ROTATION_TOLERANCE_DEG = 1e-6

#: Fixed "NOT RUN" list attached to every plan and validation payload.
NOT_CHECKED = (
    "absolute board coordinates were not computed",
    "placement was not applied to any project or EDA document",
    "routing and copper connectivity were not verified",
    "host DRC / electrical rule check was not run",
    "SI / PI / EM / thermal performance was not evaluated",
    "manufacturing, assembly and physical test were not performed",
    "schematic-to-PCB equivalence was not checked",
)

#: Fixed "limits" list (scope of what the tool actually proves).
LIMITS = (
    "axis-aligned bounding boxes of rotated rectangles (multiples of 90 degrees)",
    "relative frames only; the plan is not a final placement and not board geometry",
    "constraints are reported, never optimized, solved or silently resolved",
    "unknowns are reported, never filled with default sizes/rotations/positions",
    "overlap and fixed-position findings require a human decision",
)

SCOPE_NOTE = (
    "Module-relative placement intent plan. Not board coordinates; nothing was "
    "applied and no routing, DRC or simulation was performed."
)
