#!/usr/bin/env python3
"""Derive the frozen ``derived-mcu-i2c-plan`` benchmark case, offline.

The derivation is a pure text transform of two read-only files that already
live in this repository::

    easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/placement-plan.json
    easycirq/cases/mcu-i2c-s3-2026-10-26/README.md

It never reads ``*.epro2``, never starts EDA / daemon / connector, never touches
the network and never writes into the source case directory.  The only output is
``cases/derived-mcu-i2c-plan/input.json`` inside this benchmark.

What is derived and what is not
-------------------------------
* The source places 23 designators at absolute coordinates in **mil**
  (``placement-plan.json``).  This script groups them into five functional
  module blocks (hand assignment below) and turns the absolute coordinates into
  a HMT (module tree) plus a CCG (relative offsets ``dx/dy`` in mil, rotation in
  0/90/180 for R90, R91, U2, J1).
* The source contains no component/module footprint sizes and no board
  thickness.  This script therefore **declares no size_mm at all**: the
  derived plan can only be ``planned_constraints_only`` with ``size_unknown``
  entries.  Sizes are not fabricated.
* The board outline (2590 x 1771.7 mil = 65.79 x 45 mm) is quoted from the case
  README, whose SHA-256 is recorded as a second provenance source.
* ``snapshot.content_sha256`` is declared as the SHA-256 of the placement-plan
  artifact itself, i.e. a *frozen-content proxy* for the derived snapshot.  It
  is not a host-export hash and no host snapshot was re-read.

Run from the repository root::

    python benchmarks/placement-intent/derive_mcu_i2c_plan.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[1]
SOURCE_CASE = ROOT / "easycirq" / "cases" / "mcu-i2c-s3-2026-10-26"
SOURCE_PLAN = SOURCE_CASE / "evidence" / "placement-plan.json"
SOURCE_README = SOURCE_CASE / "README.md"
OUTPUT = BENCH / "cases" / "derived-mcu-i2c-plan" / "input.json"

MIL_TO_MM = 0.0254

#: Functional blocking chosen by reading the ``reason`` field of every
#: placement.  Every one of the 23 designators appears in exactly one block.
BLOCKS = (
    ("mod:usb", "USB-C input, ESD and CC pulldowns",
     ("J1", "D1", "D2", "R1", "R2")),
    ("mod:power", "3V3 LDO and its input/output capacitors",
     ("U1", "C2", "C3", "C1")),
    ("mod:mcu", "ESP32-S3-WROOM-1 module and its local support parts",
     ("U2", "R92", "R93", "C4", "C6", "C5", "R3")),
    ("mod:sensor", "SHT40 sensor and its I2C pull-ups",
     ("U90", "C90", "R90", "R91")),
    ("mod:ui", "BOOT/RESET buttons and the boot pull-up",
     ("SW1", "SW2", "R4")),
)

#: Rotations declared by the source placement plan for these designators.
DECLARED_ROTATION = {"U2": 180, "J1": 180, "R90": 90, "R91": 90}


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_placements():
    data = json.loads(SOURCE_PLAN.read_text(encoding="utf-8"))
    placements = {}
    for entry in data["placements"]:
        designator = entry["designator"]
        placements[designator] = {
            "x": int(entry["x"]),
            "y": int(entry["y"]),
            "rotation": int(entry.get("rotation", 0)),
            "reason": entry.get("reason", ""),
        }
    return placements


def component_id(designator):
    return "cmp:" + designator


def build_input():
    placements = load_placements()
    assigned = [name for _module, _label, names in BLOCKS for name in names]
    missing = sorted(set(placements) - set(assigned))
    duplicated = sorted({name for name in assigned
                         if assigned.count(name) > 1})
    if missing or duplicated:
        raise SystemExit("blocking must cover every designator exactly once; "
                         "missing=%r duplicated=%r" % (missing, duplicated))
    for designator, rotation in DECLARED_ROTATION.items():
        if placements[designator]["rotation"] != rotation:
            raise SystemExit("source rotation of %s changed: %r != %r"
                             % (designator, placements[designator]["rotation"],
                                rotation))

    modules = [{
        "id": "mod:board",
        "name": "mcu-i2c-s3-2026-10-26 (derived functional blocks)",
        "parent": None,
        "children": [module_id for module_id, _label, _names in BLOCKS],
        "components": [],
        "allowed_rotations": [0],
        "source": {"kind": "derived", "ref": "placement-plan.json#placements"},
    }]
    components = []
    constraints = []
    for module_id, label, designators in BLOCKS:
        anchor_x = min(placements[name]["x"] for name in designators)
        anchor_y = min(placements[name]["y"] for name in designators)
        modules.append({
            "id": module_id,
            "name": label,
            "parent": "mod:board",
            "children": [],
            "components": [component_id(name) for name in designators],
            "allowed_rotations": [0, 90, 180, 270],
            "source": {"kind": "derived", "ref": "placement-plan.json#placements"},
        })
        constraints.append({
            "id": "ccg:m-" + module_id.split(":", 1)[1],
            "from": "mod:board",
            "to": module_id,
            "dx_mm": anchor_x,
            "dy_mm": anchor_y,
            "rotation_deg": 0,
            "weight": 1.0,
            "source": {"kind": "derived",
                       "ref": "placement-plan.json#placements"},
            "note": "derived from the minimum x/y of the block members (mil)",
        })
        for name in designators:
            placement = placements[name]
            rotation = placement["rotation"]
            if rotation not in (0, 90, 180, 270):
                raise SystemExit("non 90-degree rotation in source: %r" % name)
            components.append({
                "instance_id": component_id(name),
                "designator": name,
                "allowed_rotations": sorted({0, rotation}),
                "source": {"kind": "derived",
                           "ref": "placement-plan.json#placements"},
            })
            constraints.append({
                "id": "ccg:c-" + name,
                "from": module_id,
                "to": component_id(name),
                "dx_mm": placement["x"] - anchor_x,
                "dy_mm": placement["y"] - anchor_y,
                "rotation_deg": rotation,
                "weight": 1.0,
                "source": {"kind": "derived",
                           "ref": "placement-plan.json#placements"},
                "note": "derived absolute mil coordinate minus block anchor",
            })

    plan_sha = sha256_file(SOURCE_PLAN)
    readme_sha = sha256_file(SOURCE_README)
    return {
        "schema": "easycirq.placement-intent.input/v1",
        "project": {
            "project_id": "mcu-i2c-s3-20261026-derived",
            "revision": "derived-r1",
            "document_id": "placement-plan",
        },
        "snapshot": {
            "schema": "easycirq.placement-intent.snapshot/v1",
            "captured_at": "2026-10-26T00:00:00+08:00",
            "content_sha256": plan_sha,
            "source_type": "derived",
            "missing_fields": [],
        },
        "units": {"length": "mil"},
        "board": {"width_mm": 2590.0, "height_mm": 1771.7},
        "modules": modules,
        "components": components,
        "constraints": constraints,
        "policy": {
            "max_depth": 6,
            "default_allowed_rotations": [0, 90, 180, 270],
            "position_tolerance_mm": 1e-6,
            "weight_epsilon": 1e-9,
        },
        "provenance": {
            "kind": "derived",
            "sources": [
                {
                    "ref": "easycirq/cases/mcu-i2c-s3-2026-10-26/"
                           "evidence/placement-plan.json",
                    "sha256": plan_sha,
                    "note": "absolute mil placements of 23 designators; "
                            "derived into relative CCG offsets offline",
                },
                {
                    "ref": "easycirq/cases/mcu-i2c-s3-2026-10-26/"
                           "README.md",
                    "sha256": readme_sha,
                    "note": "board outline 2590 x 1771.7 mil quoted from the "
                            "case report",
                },
            ],
            "note": (
                "Offline derivation for the placement-intent benchmark. NOT a "
                "real board read: no EDA/daemon/connector call, no .epro2 read, "
                "no size_mm is declared because the source has no footprint "
                "sizes. planned_constraints_only with size_unknown is the "
                "expected, honest outcome."
            ),
        },
        "unknowns": [],
    }


def write_case(payload):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    OUTPUT.write_bytes(text.encode("utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(argv)
    payload = build_input()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    target = Path(args.output)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))
    print(json.dumps({
        "output": str(target),
        "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "output_bytes": len(text.encode("utf-8")),
        "source_plan_sha256": sha256_file(SOURCE_PLAN),
        "source_readme_sha256": sha256_file(SOURCE_README),
        "modules": len(payload["modules"]),
        "components": len(payload["components"]),
        "constraints": len(payload["constraints"]),
        "units": payload["units"]["length"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
