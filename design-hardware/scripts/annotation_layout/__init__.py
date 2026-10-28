"""Offline annotation-pose planner for schematic readability (智构 task K).

The package is deliberately standalone: it reads versioned JSON geometry
snapshots, plans bounded text translations, verifies them independently of the
solver and writes analysis-only artifacts.  It never calls EDA, the network or
the existing layout engine, and it never edits an input file.

Entry point::

    cd design-hardware/scripts
    python -m annotation_layout --help

Modules:
    model       frozen data types and deterministic JSON hashing
    geometry    2-D math, y-up checks and a deterministic spatial index
    schema      strict annotation-layout/v1 parser
    conflicts   fast fixed-geometry / pair conflict evaluation
    candidates  K1 bounded candidate generation
    solver      K2-K4 bounded cluster search and failure taxonomy
    baseline    reference per-annotation greedy for benchmark comparison
    planner     orchestration input -> candidates -> solver -> plan
    verify      K5 independent recheck + existing checker bridge
    svg_analysis analysis-only before/after overlays
    report      machine JSON and short Markdown report
    convert     frozen photo-led fixture -> v1 input
    probe_record validate onsite host-probe records and derive the host block
    benchmark   same-domain baseline vs improved measurement
    cli         command-line dispatch, atomic UTF-8 IO
"""
from __future__ import annotations

from .model import SCHEMA_ID, TOOL_NAME, TOOL_VERSION

__all__ = ["SCHEMA_ID", "TOOL_NAME", "TOOL_VERSION"]
__version__ = TOOL_VERSION
