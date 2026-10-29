#!/usr/bin/env python3
"""Serial EDA measurement runner for ``easycirq-device-metrics/v1``.

This is the ONLY writer of ``easycirq/assets/device-metrics.json`` besides hand
edits. It measures device geometry on a live EasyEDA client, one primitive at a
time, and merges the results back without touching fields it did not measure.
It is deliberately not unit-tested: it talks to a real client, so its protocol
is documented here and its offline half (validation + merge) is covered by
``tests/test_layout2_device_metrics.py``.

Why serial
----------
Only one EDA writer may exist. This runner never runs measurements in parallel,
never retries a failed write blindly, and re-reads the page after every mutation
before it uses the result. Do not run it while ``tools/sch_layout_apply.py``,
``easycirq sch`` transformations or a human editor are writing the same window.

Measurement protocol (order matters)
------------------------------------
0. PRECONDITIONS
   a. ``easycirq doctor`` reports a connected window, and a scratch schematic
      page exists whose contents you are willing to destroy.
   b. The same page UUID is passed as ``--page``; every command is pinned with
      the root ``--doc <page-uuid>`` flag so measurements cannot land on the
      wrong tab.

1. PER-PART SYMBOL / PINS / DESIGNATOR  (one part at a time)
   a. ``easycirq sch clear --doc PAGE`` — delete every page primitive.
   b. ``easycirq sch list --doc PAGE`` — REQUIRE zero parts. A page that did
      not clear is a hard abort (stale parts poison the bbox measurement).
   c. ``easycirq sch place --lib <libraryUuid> --uuid <deviceUuid> --x X --y Y
      --doc PAGE`` — the device UUID comes from ``easycirq/references/
      standard-parts.json`` (library uuid at the document root, device uuid
      per part), never from a placed instance id.
   d. ``easycirq sch list --doc PAGE --include-bbox --include-pins`` — the
      placed symbol's rendered ``bbox`` gives ``symbol.w = maxX - minX`` and
      ``symbol.h = maxY - minY``; ``pins`` gives the pin count.
   e. ``easycirq sch designator-geometry --doc PAGE`` — the official per-
      attribute bbox of the visible Designator gives ``designator.w``. The
      ``designator.size`` (pt) is a style default, kept from the existing entry.
   f. Value width is NOT exposed by any current read path, so it stays at its
      existing default and the provenance string says so.

2. PER-BLOCK HALO  (one block at a time)
   a. Clear + verify zero parts again (same guard as 1b).
   b. ``easycirq sch block-apply <block-id> --at X,Y --parts <standard-parts>
      --doc PAGE`` — instantiate the block; block-apply does its own place +
      wire + readback and fails loudly instead of landing dirty geometry.
   c. ``easycirq sch list --doc PAGE --include-bbox --include-pins
      --include-wires`` — union of part bboxes is the symbol extent; union of
      part + net-flag/net-port + wire-segment geometry is the decorated extent.
      Per side: ``halo = max(0, symbol_side - decorated_side)``. The decorated
      width/height must reproduce ``easycirq/assets/block-envelopes.json``
      within 25%; a mismatch means wrong page/scale or a changed block, so the
      sample is refused instead of written (re-measure the envelope first).
   d. Repeat over every selected block. Each part that appears in a measured
      block collects one halo sample per block; the written halo is the P90
      (nearest-rank) of those samples. Parts with no block sample keep their
      previous halo and its "defaults pending measurement" provenance.

3. MERGE + WRITE
   ``device_metrics.merge_part`` writes only the measured fields, keeps every
   unmeasured field/provenance, stamps per-part ``measured_at`` and a provenance
   string naming this runner, validates the whole document, then writes the
   asset in its stable one-space-indent JSON style.

Safety defaults
---------------
* Importing this module performs NO EDA call, no subprocess and no file write.
* Without ``--execute`` the runner is a dry run: it prints the exact serial
  command plan and exits 0 without touching the client or the asset.
* ``--execute`` requires ``--page``; every mutation is preceded by the empty-
  page guard, and a failed item is reported and skipped instead of retried.
* ``--no-write`` measures and reports without writing the asset (useful for a
  first supervised run).

Exit codes: 0 all requested measurements succeeded (or dry run),
1 partial failure (asset written for the successful items), 2 invalid input.

Usage::

    # print the protocol for the given parts/blocks, no EDA
    python tools/layout2/measure_device_metrics.py --parts res.10k_0402,ic.es8311

    # measure symbols/pins/designator widths for every part in the asset
    python tools/layout2/measure_device_metrics.py --parts all --execute \
        --page <page-uuid>

    # measure halo P90 for two blocks
    python tools/layout2/measure_device_metrics.py --blocks \
        block.ams1117_ldo_3v3,block.bmi270_imu_i2c --execute --page <page-uuid>

    # full serial run, report only
    python tools/layout2/measure_device_metrics.py --parts all --blocks all \
        --execute --page <page-uuid> --no-write
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:  # package import (python -m tools.layout2.measure_device_metrics)
    from . import device_metrics
except ImportError:  # direct script execution (python tools/layout2/...)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import device_metrics  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[2]
ASSET_PATH = ROOT / "easycirq" / "assets" / "device-metrics.json"
STANDARD_PARTS_PATH = ROOT / "easycirq" / "references" / "standard-parts.json"
BLOCKS_DIR = ROOT / "runtime" / "internal" / "blocks" / "data"

# Placement anchors only need to be on an empty page; they are not geometry.
PART_ANCHOR = (300.0, 300.0)
BLOCK_ANCHOR = (400.0, 400.0)
# The client autosaves in the background; small pauses keep readbacks honest.
# Same scale as tools/sch_layout_apply.py (3-7 s around block mutations, 1-2 s
# for reads). Exposed as a flag because slower machines need more.
DEFAULT_SETTLE_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 180.0
EMPTY_PAGE_ATTEMPTS = 3
DEFAULT_DESIGNATOR_SIZE = 7  # pt; EasyEDA default, kept unless a style changes it
HALO_PERCENTILE = 0.90  # contract §1.3: typical stub/flag/net-label expansion, P90
# A measured block footprint should reproduce block-envelopes.json. A larger
# deviation means the wrong page/scale or a changed block, and the halo sample
# would be silently wrong; refuse to write it instead.
ENVELOPE_TOLERANCE = 0.25


class MeasurementError(RuntimeError):
    """A serial measurement step could not produce evidence it trusts."""


@dataclass
class PartMeasurement:
    """Fields measured for one part in one run, plus the provenance notes."""

    fields: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CLI / EDA bridge (all calls pass through here; nothing runs at import)
# ---------------------------------------------------------------------------
class EdaClient:
    def __init__(self, binary: str, page: str, *, execute: bool,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 settle: float = DEFAULT_SETTLE_SECONDS) -> None:
        self.binary = binary
        self.page = page
        self.execute = execute
        self.timeout = timeout
        self.settle = settle

    def run(self, args: Sequence[str], *, mutate: bool = False) -> Optional[str]:
        argv = [self.binary, *[str(arg) for arg in args], "--doc", self.page]
        if not self.execute:
            print("[dry-run] " + " ".join(argv))
            return None
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=self.timeout)
        except FileNotFoundError as exc:
            raise MeasurementError(f"EDA CLI not found: {self.binary!r} ({exc})") from exc
        except subprocess.TimeoutExpired as exc:
            raise MeasurementError(
                f"EDA command timed out after {self.timeout:g}s: {' '.join(argv)}"
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else "no output"
            raise MeasurementError(
                f"EDA command failed (exit {proc.returncode}): {' '.join(argv)}: {tail}"
            )
        if mutate:
            time.sleep(self.settle)
        return proc.stdout or ""

    def json_result(self, args: Sequence[str], *, mutate: bool = False,
                    what: str = "EDA read") -> Dict[str, Any]:
        stdout = self.run(args, mutate=mutate)
        if stdout is None:  # dry run
            return {}
        payload = _first_json_object(stdout)
        if payload is None:
            raise MeasurementError(f"{what}: command printed no JSON object")
        result = payload.get("result")
        return result if isinstance(result, dict) else payload


def _first_json_object(text: str) -> Optional[Dict[str, Any]]:
    start = text.find("{")
    while start >= 0:
        try:
            value, _end = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        return value if isinstance(value, dict) else None
    return None


def _components(client: EdaClient, *, wires: bool = False) -> Dict[str, Any]:
    args = ["sch", "list", "--include-bbox", "--include-pins"]
    if wires:
        args.append("--include-wires")
    return client.json_result(args, what="sch list")


def _page_parts(client: EdaClient, *, wires: bool = False) -> List[Dict[str, Any]]:
    result = _components(client, wires=wires)
    components = result.get("components")
    if not isinstance(components, list):
        raise MeasurementError("sch list returned no components array")
    return [c for c in components
            if isinstance(c, dict) and c.get("componentType") == "part"]


def _ensure_empty_page(client: EdaClient) -> None:
    """FT-01 guard: a failed clear must abort instead of stacking measurements."""
    last_count: Optional[int] = None
    last_error: Optional[str] = None
    for _attempt in range(EMPTY_PAGE_ATTEMPTS):
        try:
            client.run(["sch", "clear"], mutate=True)
        except MeasurementError as exc:  # a no-op clear on an empty page is fine
            last_error = str(exc)
        try:
            parts = _page_parts(client)
        except MeasurementError as exc:  # transient read while the client settles
            last_error = str(exc)
            time.sleep(client.settle)
            continue
        last_count = len(parts)
        if last_count == 0:
            return
    detail = f" ({last_error})" if last_error else ""
    raise MeasurementError(
        f"sch clear did not empty the page ({last_count} part(s) left){detail}; "
        "refusing to measure on top of stale parts — save/restart the client, then rerun"
    )


def _bbox_of(component: Dict[str, Any]) -> Dict[str, float]:
    bbox = component.get("bbox")
    if not isinstance(bbox, dict) or not all(
            key in bbox for key in ("minX", "minY", "maxX", "maxY")):
        raise MeasurementError(
            f"component {component.get('designator') or component.get('primitiveId')!r} "
            "has no usable bbox (sch list --include-bbox)"
        )
    return {key: float(bbox[key]) for key in ("minX", "minY", "maxX", "maxY")}


def _union_bbox(boxes: Iterable[Dict[str, float]]) -> Optional[Dict[str, float]]:
    boxes = list(boxes)
    if not boxes:
        return None
    return {
        "minX": min(box["minX"] for box in boxes),
        "minY": min(box["minY"] for box in boxes),
        "maxX": max(box["maxX"] for box in boxes),
        "maxY": max(box["maxY"] for box in boxes),
    }


def _wire_points(wire: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Flatten the native wire ``line`` geometry into points (either shape)."""
    line = wire.get("line")
    points: List[Tuple[float, float]] = []
    if isinstance(line, list) and line and all(isinstance(v, (int, float)) for v in line):
        if len(line) % 2 == 0:
            for index in range(0, len(line), 2):
                points.append((float(line[index]), float(line[index + 1])))
    elif isinstance(line, list):
        for item in line:
            if (isinstance(item, (list, tuple)) and len(item) >= 2
                    and all(isinstance(v, (int, float)) for v in item[:2])):
                points.append((float(item[0]), float(item[1])))
    return points


def _points_bbox(points: Iterable[Tuple[float, float]]) -> Optional[Dict[str, float]]:
    points = list(points)
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}


def _load_standard_parts(path: Path = STANDARD_PARTS_PATH) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MeasurementError(f"cannot read {path}: {exc}") from exc
    parts = document.get("parts")
    if not isinstance(parts, dict):
        raise MeasurementError(f"{path}: missing 'parts' object")
    return {"libraryUuid": document.get("libraryUuid"), "parts": parts, "path": path}


def _load_block(block_id: str) -> Dict[str, Any]:
    name = block_id[len("block."):] if block_id.startswith("block.") else block_id
    path = BLOCKS_DIR / f"{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MeasurementError(f"cannot read block {block_id!r} at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MeasurementError(f"{path}: invalid JSON: {exc}") from exc


def _block_part_keys(block: Dict[str, Any]) -> List[str]:
    keys = []
    for spec in (block.get("parts") or {}).values():
        if isinstance(spec, dict) and isinstance(spec.get("part"), str):
            keys.append(spec["part"])
    return keys


def _block_envelope(block_id: str) -> Optional[Dict[str, float]]:
    """Known rendered envelope for a block, if block-envelopes.json has one."""
    path = ROOT / "easycirq" / "assets" / "block-envelopes.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    blocks = document.get("blocks")
    envelope = blocks.get(block_id) if isinstance(blocks, dict) else None
    if not isinstance(envelope, dict):
        return None
    try:
        return {"w": float(envelope["w"]), "h": float(envelope["h"])}
    except (KeyError, TypeError, ValueError):
        return None


def _check_envelope(block_id: str, decorated: Dict[str, float]) -> None:
    """Refuse a halo sample that does not reproduce the known block footprint."""
    envelope = _block_envelope(block_id)
    if envelope is None:
        return
    width = decorated["maxX"] - decorated["minX"]
    height = decorated["maxY"] - decorated["minY"]
    for axis, measured, known in (("w", width, envelope["w"]), ("h", height, envelope["h"])):
        if known <= 0:
            continue
        if abs(measured - known) / known > ENVELOPE_TOLERANCE:
            raise MeasurementError(
                f"block {block_id!r} decorated {axis}={measured:g} does not match the "
                f"known envelope {axis}={known:g} in block-envelopes.json "
                f"(> {ENVELOPE_TOLERANCE:.0%} deviation): wrong page/scale or a changed "
                "block — re-measure the envelope before recording halo samples"
            )


def _designator_width(client: EdaClient) -> Optional[float]:
    """Read the official Designator attribute bbox; ``None`` if unavailable."""
    try:
        result = client.json_result(["sch", "designator-geometry"],
                                    what="sch designator-geometry")
    except MeasurementError:
        return None
    rows = result.get("designators")
    if not isinstance(rows, list) or len(rows) != 1:
        return None
    bbox = rows[0].get("bbox") if isinstance(rows[0], dict) else None
    if not isinstance(bbox, dict):
        return None
    try:
        return float(bbox["maxX"]) - float(bbox["minX"])
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# measurements
# ---------------------------------------------------------------------------
def measure_part(client: EdaClient, part: str, standard_parts: Dict[str, Any],
                 existing: Dict[str, Any], measured_at: str) -> PartMeasurement:
    parts_path = standard_parts.get("path", STANDARD_PARTS_PATH)
    entry = standard_parts["parts"].get(part)
    if not isinstance(entry, dict):
        raise MeasurementError(
            f"part {part!r} is not in {parts_path}; add its deviceUuid first"
        )
    library_uuid = standard_parts.get("libraryUuid")
    device_uuid = entry.get("deviceUuid")
    if not isinstance(library_uuid, str) or not library_uuid:
        raise MeasurementError(f"{parts_path}: missing root libraryUuid")
    if not isinstance(device_uuid, str) or not device_uuid:
        raise MeasurementError(
            f"part {part!r} has no deviceUuid in {parts_path}"
        )

    _ensure_empty_page(client)
    client.run(["sch", "place", "--lib", library_uuid, "--uuid", device_uuid,
                "--x", f"{PART_ANCHOR[0]:g}", "--y", f"{PART_ANCHOR[1]:g}"],
               mutate=True)
    parts = _page_parts(client)
    if len(parts) != 1:
        raise MeasurementError(
            f"expected exactly 1 placed part for {part!r}, found {len(parts)}"
        )
    placed = parts[0]
    bbox = _bbox_of(placed)
    width = bbox["maxX"] - bbox["minX"]
    height = bbox["maxY"] - bbox["minY"]

    fields: Dict[str, Any] = {"symbol": {"w": round(width, 2), "h": round(height, 2)}}
    pins = placed.get("pins")
    if isinstance(pins, list):
        fields["pins"] = len(pins)

    notes = [f"symbol bbox measured {measured_at} via "
             "tools/layout2/measure_device_metrics.py (empty-page placement + "
             "schematic.components.list includeBBox)"]
    if "pins" in fields:
        notes.append(f"pins={fields['pins']} counted on the same placement")

    designator_width = _designator_width(client)
    if designator_width is not None:
        fields["designator"] = {"w": round(designator_width, 2)}
        notes.append("designator width measured from sch designator-geometry")
        size = existing.get("designator", {}).get("size", DEFAULT_DESIGNATOR_SIZE)
        notes.append(f"designator size kept at {size} pt (style default)")
    else:
        notes.append("designator width unchanged (no designator geometry read)")
    notes.append("value width unchanged (no read path exposes Value attribute bbox)")
    notes.append("halo unchanged unless --blocks samples a block that contains this part")
    return PartMeasurement(fields=fields, notes=notes)


def _decorated_and_symbol_bounds(result: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, float]]:
    components = result.get("components")
    if not isinstance(components, list):
        raise MeasurementError("sch list returned no components array")
    symbol_boxes: List[Dict[str, float]] = []
    decoration_boxes: List[Dict[str, float]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        try:
            box = _bbox_of(component)
        except MeasurementError:
            continue
        if component.get("componentType") == "part":
            symbol_boxes.append(box)
        else:  # net flags / net labels / ports / any other rendered decoration
            decoration_boxes.append(box)
    wires = result.get("wires") if isinstance(result.get("wires"), list) else []
    for wire in wires:
        if isinstance(wire, dict):
            box = _points_bbox(_wire_points(wire))
            if box is not None:
                decoration_boxes.append(box)
    symbol = _union_bbox(symbol_boxes)
    if symbol is None:
        raise MeasurementError("block produced no part bboxes to measure")
    decorated = _union_bbox([*symbol_boxes, *decoration_boxes]) or dict(symbol)
    return symbol, decorated


def _halo_from_extents(symbol: Dict[str, float],
                       decorated: Dict[str, float]) -> Dict[str, float]:
    return {
        "left": max(0.0, symbol["minX"] - decorated["minX"]),
        "right": max(0.0, decorated["maxX"] - symbol["maxX"]),
        "top": max(0.0, symbol["minY"] - decorated["minY"]),
        "bottom": max(0.0, decorated["maxY"] - symbol["maxY"]),
    }


def measure_block_halo(client: EdaClient, block_id: str, standard_parts_path: Path,
                       measured_at: str) -> Tuple[Dict[str, float], List[str]]:
    """Measure one block's decorated extent and return per-part halo samples."""
    block = _load_block(block_id)
    part_keys = _block_part_keys(block)
    if not part_keys:
        raise MeasurementError(f"block {block_id!r} declares no parts")

    _ensure_empty_page(client)
    client.run(["sch", "block-apply", block_id,
                "--at", f"{BLOCK_ANCHOR[0]:g},{BLOCK_ANCHOR[1]:g}",
                "--parts", str(standard_parts_path)], mutate=True)
    result = _components(client, wires=True)
    symbol, decorated = _decorated_and_symbol_bounds(result)
    _check_envelope(block_id, decorated)
    sample = _halo_from_extents(symbol, decorated)
    print(f"       {block_id} decorated extent measured {measured_at}: "
          f"symbol {symbol} -> decorated {decorated}")
    return sample, part_keys


def _p90(values: Sequence[float]) -> float:
    """Nearest-rank P90; a single sample is its own P90."""
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(HALO_PERCENTILE * len(ordered)))
    return ordered[rank - 1]


def _merge_measurements(document: Dict[str, Any], measurements: Dict[str, PartMeasurement],
                        measured_at: str, *, path: Path) -> Dict[str, Any]:
    for part in sorted(measurements):
        measurement = measurements[part]
        provenance = ("; ".join(dict.fromkeys(measurement.notes))
                      + "; unmeasured fields kept from the previous entry")
        document = device_metrics.merge_part(
            document, part, measurement.fields,
            measured_at=measured_at, provenance=provenance, path=path)
    return document


# ---------------------------------------------------------------------------
# selection + reporting
# ---------------------------------------------------------------------------
def _split_selection(value: Optional[str], known: Sequence[str],
                     label: str) -> List[str]:
    if value is None:
        return []
    value = value.strip()
    if not value:
        return []
    if value in ("all", "*"):
        if not known:
            raise MeasurementError(
                f"--{label} all: no {label} were discovered to select from")
        return list(known)
    selected = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in selected if item not in known]
    if unknown:
        raise MeasurementError(
            f"invalid --{label}: unknown {label[:-1]}(s) {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(known))[:400]}"
        )
    return selected


def _print_plan(parts: Sequence[str], blocks: Sequence[str], page: str,
                standard_parts_path: Path) -> None:
    print("Serial protocol (dry run; pass --execute --page <uuid> to run it):")
    print(f"  page: {page or '<--page required with --execute>'}")
    for part in parts:
        print(f"  part {part}:")
        print(f"    [1] sch clear --doc {page or '<page>'}")
        print(f"    [2] sch list  --doc {page or '<page>'}    # require 0 parts")
        print(f"    [3] sch place --lib <libraryUuid> --uuid <deviceUuid> "
              f"--x {PART_ANCHOR[0]:g} --y {PART_ANCHOR[1]:g} --doc {page or '<page>'}")
        print(f"    [4] sch list  --include-bbox --include-pins --doc {page or '<page>'}"
              "  # symbol bbox + pin count")
        print(f"    [5] sch designator-geometry --doc {page or '<page>'}"
              "        # designator width")
    for block in blocks:
        print(f"  block {block}:")
        print(f"    [1] sch clear --doc {page or '<page>'}")
        print(f"    [2] sch list  --doc {page or '<page>'}    # require 0 parts")
        print(f"    [3] sch block-apply {block} --at "
              f"{BLOCK_ANCHOR[0]:g},{BLOCK_ANCHOR[1]:g} --parts {standard_parts_path} "
              f"--doc {page or '<page>'}")
        print(f"    [4] sch list  --include-bbox --include-pins --include-wires "
              f"--doc {page or '<page>'}")
        print("    [5] halo per side = max(0, symbol_extent - decorated_extent); "
              "P90 across block samples")
    print("  merge: only measured fields are written; provenance is preserved for "
          "unmeasured fields.")


def _resolve_binary(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    from_env = os.environ.get("EASYCIRQ_BIN", "").strip()
    if from_env:
        return from_env
    found = shutil.which("easycirq")
    if found:
        return found
    # Same default install path used by tools/sch_layout_apply.py.
    default = Path(r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe")
    return str(default) if default.exists() else "easycirq"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serially measure easycirq-device-metrics/v1 on a live EasyEDA "
                    "client and merge the results into the asset.",
        epilog=__doc__.split("Usage::", 1)[-1] if "Usage::" in __doc__ else None,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parts", help="comma-separated part keys, or 'all' for every part in the asset")
    parser.add_argument("--blocks", help="comma-separated block ids, or 'all' for every block in block-envelopes.json")
    parser.add_argument("--execute", action="store_true",
                        help="actually call the EDA client (default: dry run)")
    parser.add_argument("--page", default="",
                        help="schematic page UUID to pin every command to (required with --execute)")
    parser.add_argument("--out", default=str(ASSET_PATH),
                        help=f"asset JSON to merge into (default: {ASSET_PATH})")
    parser.add_argument("--no-write", action="store_true",
                        help="measure and report without writing the asset")
    parser.add_argument("--bin", default=None,
                        help="easycirq executable (default: $EASYCIRQ_BIN, PATH, or the standard install)")
    parser.add_argument("--measured-at", default=date.today().isoformat(),
                        help="per-part measured_at stamp (default: today)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help=f"per-command timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE_SECONDS,
                        help=f"pause after each mutation in seconds (default: {DEFAULT_SETTLE_SECONDS:g})")
    parser.add_argument("--parts-file", default=str(STANDARD_PARTS_PATH),
                        help="standard-parts.json used to resolve device UUIDs")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    try:
        if not out_path.exists():
            raise MeasurementError(f"metrics asset not found: {out_path}")
        document = json.loads(out_path.read_text(encoding="utf-8"))
        device_metrics.validate(document, path=out_path)
        standard_parts_path = Path(args.parts_file)
        standard_parts = _load_standard_parts(standard_parts_path)
        known_blocks = _known_blocks()
        parts = _split_selection(args.parts, sorted(document["parts"]), "parts")
        blocks = _split_selection(args.blocks, known_blocks, "blocks")
    except (OSError, json.JSONDecodeError, device_metrics.DeviceMetricsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except MeasurementError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not parts and not blocks:
        parser.error("nothing selected: pass --parts and/or --blocks (use 'all')")
    if not args.execute:
        _print_plan(parts, blocks, args.page, standard_parts_path)
        return 0
    if not args.page:
        parser.error("--execute requires --page <schematic-page-uuid>")

    client = EdaClient(_resolve_binary(args.bin), args.page, execute=True,
                       timeout=args.timeout, settle=args.settle)
    measurements: Dict[str, PartMeasurement] = {}
    halo_samples: Dict[str, List[float]] = {}
    halo_blocks: Dict[str, List[str]] = {}
    failures: List[str] = []

    # Phase 1: per-part symbol/pins/designator (serial).
    for part in parts:
        try:
            measurement = measure_part(client, part, standard_parts,
                                       document["parts"][part], args.measured_at)
            measurements[part] = measurement
            print(f"[ok]   part {part}: symbol {measurement.fields['symbol']}")
        except MeasurementError as exc:
            failures.append(f"part {part}: {exc}")
            print(f"[fail] part {part}: {exc}", file=sys.stderr)

    # Phase 2: per-block halo samples (serial; only selected blocks).
    for block_id in blocks:
        try:
            sample, part_keys = measure_block_halo(
                client, block_id, standard_parts_path, args.measured_at)
            for part in part_keys:
                if part not in document["parts"]:
                    continue
                halo_blocks.setdefault(part, []).append(block_id)
                for side in device_metrics.HALO_SIDES:
                    halo_samples.setdefault(f"{part}:{side}", []).append(float(sample[side]))
            print(f"[ok]   block {block_id}: halo {sample}")
        except MeasurementError as exc:
            failures.append(f"block {block_id}: {exc}")
            print(f"[fail] block {block_id}: {exc}", file=sys.stderr)

    # Fold P90 halo samples into the per-part measurements.
    for part, blocks_seen in halo_blocks.items():
        parts_seen = sorted(set(blocks_seen))
        halo = {}
        for side in device_metrics.HALO_SIDES:
            values = halo_samples.get(f"{part}:{side}") or [0.0]
            halo[side] = round(_p90(values))
        measurement = measurements.setdefault(part, PartMeasurement())
        measurement.fields["halo"] = halo
        measurement.notes.append(
            f"halo = P90 (nearest-rank) of measured stub/flag/net-label extents "
            f"over {len(parts_seen)} block sample(s) ({', '.join(parts_seen)}) "
            f"on {args.measured_at}")

    if measurements and not args.no_write:
        try:
            merged = _merge_measurements(document, measurements, args.measured_at,
                                         path=out_path)
            device_metrics.save(merged, out_path)
            print(f"wrote {len(measurements)} measured part(s) to {out_path}")
        except (device_metrics.DeviceMetricsError, OSError) as exc:
            failures.append(f"write-back: {exc}")
            print(f"[fail] write-back: {exc}", file=sys.stderr)

    if failures:
        print(f"{len(failures)} measurement step(s) failed; "
              "successful items were kept, nothing was retried", file=sys.stderr)
        return 1
    print(f"done: {len(measurements)} part(s), {len(blocks)} block(s)")
    return 0


def _known_blocks() -> List[str]:
    envelopes = ROOT / "easycirq" / "assets" / "block-envelopes.json"
    try:
        document = json.loads(envelopes.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    blocks = document.get("blocks")
    return sorted(blocks) if isinstance(blocks, dict) else []


if __name__ == "__main__":
    raise SystemExit(main())
