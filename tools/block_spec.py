"""Build pipeline spec modules from measured block envelopes.

Pre-layout must reserve room for **routed wires and their net-label text**,
otherwise the applied page looks cramped and labels overlap neighbouring parts.
The measured asset ``easycirq/assets/block-envelopes.json`` already carries that
information per block:

* ``w``/``h`` — the block's part footprint,
* ``halo``    — measured P90 clearance consumed by auto-wired stubs, flags and
  net labels (per side),
* ``label_bbox`` — the label-extended bounding box used to sanity-check the halo.

This module turns ``[block_id, ...]`` into pipeline ``modules`` that use the
measured halo instead of a hand-written small number (the old specs passed
``halo: 8`` and lost ~100 units of label space per side).
"""

from __future__ import annotations

import json
import pathlib

SCHEMA = "easycirq-spec-modules/v1"
DEFAULT_ENVELOPES = (pathlib.Path(__file__).resolve().parent.parent
                     / "easycirq" / "assets" / "block-envelopes.json")
FALLBACK_HALO = {"left": 8.0, "right": 8.0, "top": 8.0, "bottom": 8.0}


def load_envelopes(path=None):
    data = json.loads(pathlib.Path(path or DEFAULT_ENVELOPES).read_text(encoding="utf-8"))
    return data.get("blocks") or {}


def halo_of(block, envelopes):
    """Measured halo for ``block``; raises if the block is unknown (fail closed)."""
    entry = envelopes.get(block)
    if not entry:
        raise ValueError("unknown block %r (not in block-envelopes.json)" % block)
    halo = entry.get("halo") or {}
    return {side: float(halo.get(side, FALLBACK_HALO[side]))
            for side in ("left", "right", "top", "bottom")}


def label_clearance(block, envelopes):
    """Extra space the labels need beyond the part footprint, per side."""
    entry = envelopes.get(block) or {}
    w = float(entry.get("w") or 0.0)
    h = float(entry.get("h") or 0.0)
    label = entry.get("label_bbox") or {}
    lw = float(label.get("w") or w)
    lh = float(label.get("h") or h)
    return {"extra_w": max(0.0, lw - w), "extra_h": max(0.0, lh - h)}


def modules_for(block_ids, envelopes=None, *, halo_scale=1.0):
    """Pipeline ``modules`` for the given blocks (label-aware halos)."""
    envelopes = envelopes if envelopes is not None else load_envelopes()
    modules = []
    for block in block_ids:
        entry = envelopes.get(block)
        if not entry:
            raise ValueError("unknown block %r" % block)
        halo = halo_of(block, envelopes)
        halo = {side: round(value * float(halo_scale), 1) for side, value in halo.items()}
        modules.append({"id": block, "title": block, "block": block,
                        "w": float(entry["w"]), "h": float(entry["h"]),
                        "halo": halo})
    return modules


def spec(name, block_ids, *, envelope_path=None, halo_scale=1.0, **extra):
    """Full pipeline spec skeleton with label-aware module halos."""
    data = {"name": name, "engine": "templates",
            "modules": modules_for(block_ids, load_envelopes(envelope_path),
                                   halo_scale=halo_scale)}
    data.update(extra)
    return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("blocks", nargs="+")
    parser.add_argument("--envelopes")
    parser.add_argument("--halo-scale", type=float, default=1.0)
    parser.add_argument("--emit")
    args = parser.parse_args()
    data = spec(args.name, args.blocks, envelope_path=args.envelopes,
                halo_scale=args.halo_scale)
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if args.emit:
        pathlib.Path(args.emit).write_text(text + "\n", encoding="utf-8")
    print(text)
