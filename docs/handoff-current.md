# Current handoff — 2026-10-26: schematic readability

Repository: hardware-design-skill. Worktree: C:/Users/jlc/work/hds-merge-20261026.
Branch: fix/schematic-readability-contract, based on the exact merged main tree
b28648d98806f1004aef94b1041cbd86c751d542 (remote cd2c203).

Mandatory entry guidance and existing layout references now require functional
zones, a one-page-first plan for simple projects, justified page splits, local
short wires, anchored labels, complete text bounds and actual visual acceptance.
The existing sch_layout_check.py gains --strict and different-net collinear
collision detection. Strict mode rejects missing coverage, label text bounds,
module title/purpose references, missing/ambiguous component membership and
incomplete inventory; page checks include label and attachment anchors.

All fixtures are synthetic offline checks, not EDA evidence. No live drawing or
installed executor/skill changed. User plans a simple real project next: explicitly
load this worktree's design-hardware/SKILL.md so an older installed copy is not
mistaken for the changed source. Plan one page, then draw, export every page and
inspect whole/local views, compare pin-net, native checks, save/reopen/read back.
No restricted-domain requests or changes to the ongoing oscilloscope project.
