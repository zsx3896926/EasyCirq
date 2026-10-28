"""Convert the frozen photo-led v14 adapter fixture into an annotation-layout/v1
input document.

Sources (all read-only, never modified):
* ``layout.json``      - ``layout_from_easyeda.py`` output: checker-contract
                         geometry, text kinds/owners/content and module frames;
* ``list.json``        - retained ``easycirq sch list`` response: component
                         designators and page-text anchor/rotation/font metadata;
* ``rendered-text.json`` - browser-measured SVG text bboxes (y is negated once);
* ``sheet.json``       - official-SVG sheet geometry (inner frame, title block).

The converter copies the four source files next to the output (optional) and
records their SHA-256, so a later validate/plan run rejects stale provenance.
It never calls EDA or the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .model import SCHEMA_ID, TOOL_NAME, TOOL_VERSION, canonical_json

BASE_COMMIT = "9a951edc21481dc3ae91460acc11aa3e08a7be8a"
CREATED = "2026-10-27"
RAW_PER_MM = 1.0 / 0.254  # 10 raw = 0.1 inch = 2.54 mm

_SOURCE_KINDS = ("layout", "list", "rendered", "sheet")


class ConvertError(ValueError):
    pass


def _read(path: Path) -> Any:
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConvertError(f"{path}: invalid UTF-8 JSON ({exc})") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _box(value: Any) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        numbers = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
        return None
    return numbers


def _dict_box(value: Any) -> Optional[List[float]]:
    if not isinstance(value, dict):
        return None
    try:
        return _box([value["minX"], value["minY"], value["maxX"], value["maxY"]])
    except (KeyError, TypeError):
        return None


def _center(box: Sequence[float]) -> Tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _inside(point: Tuple[float, float], box: Sequence[float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _area(box: Sequence[float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _pick_zone(zones: Sequence[Mapping[str, Any]],
               box: Sequence[float]) -> Optional[Mapping[str, Any]]:
    """Smallest declared zone that contains the box's center, if any."""
    point = _center(box)
    matches = [zone for zone in zones if _inside(point, zone["bbox"])]
    if not matches:
        return None
    return min(matches, key=lambda zone: (_area(zone["bbox"]), zone["id"]))


def _pick_zone_strict(zones: Sequence[Mapping[str, Any]],
                      box: Sequence[float]) -> Optional[Mapping[str, Any]]:
    matches = [zone for zone in zones
               if zone["bbox"][0] <= box[0] and zone["bbox"][1] <= box[1]
               and zone["bbox"][2] >= box[2] and zone["bbox"][3] >= box[3]]
    if not matches:
        return None
    return min(matches, key=lambda zone: (_area(zone["bbox"]), zone["id"]))


def _component_index(list_data: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for item in list_data.get("components", []) or []:
        identity = item.get("primitiveId")
        if identity:
            result[identity] = item
    return result


def _text_metadata(list_data: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    primitives = list_data.get("pagePrimitives") or {}
    for item in primitives.get("texts", []) or []:
        identity = item.get("primitiveId")
        if identity:
            result[identity] = item
    return result


def _rendered_index(rendered: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for row in rendered.get("rows", []) or []:
        identity = row.get("id")
        if identity:
            result[identity] = row
    return result


def _zone_names(layout: Mapping[str, Any]) -> Dict[str, str]:
    titles = [text for text in layout.get("texts", []) or []
              if text.get("kind") == "zone_title"]
    names: Dict[str, str] = {}
    for text in titles:
        box = _box(text.get("bbox"))
        if box is None:
            continue
        point = _center(box)
        for frame in layout.get("module_frames", []) or []:
            frame_box = _box(frame.get("bbox"))
            if frame_box is not None and _inside(point, frame_box):
                names[frame["id"]] = str(text.get("content") or frame["id"])
                break
    return names


def build_document(layout_path: Path, list_path: Path, rendered_path: Path,
                   sheet_path: Path) -> Dict[str, Any]:
    layout = _read(layout_path)
    list_data = _read(list_path)
    rendered = _read(rendered_path)
    sheet = _read(sheet_path)

    page_bbox = _box(layout.get("page_bbox"))
    if page_bbox is None:
        raise ConvertError("layout.page_bbox missing")
    page_height = page_bbox[3]
    sheet_block = sheet.get("sheet") or {}
    inner = _dict_box(sheet_block.get("innerBBox")) or list(page_bbox)
    title = _dict_box((sheet.get("titleBlock") or {}).get("bbox"))
    keepouts: List[Dict[str, Any]] = []
    for item in sheet.get("keepouts", []) or []:
        box = _dict_box(item.get("bbox"))
        if box is None:
            continue
        keepouts.append({
            "id": str(item.get("name") or f"keepout-{len(keepouts)}"),
            "bbox": box,
            "hard": bool(item.get("hard", True)),
            "reason": "title block" if item.get("name") == "titleBlock" else "declared keep-out",
        })
    frames = []
    names = _zone_names(layout)
    for index, frame in enumerate(layout.get("module_frames", []) or []):
        box = _box(frame.get("bbox"))
        if box is None:
            continue
        identity = str(frame.get("id"))
        frames.append({
            "id": identity,
            "name": names.get(identity, f"zone {index + 1}"),
            "bbox": box,
            "hard": False,
            "source": "module_frame",
        })
    if not frames:
        raise ConvertError("layout.module_frames missing; zone ownership cannot be derived")
    title_rect = {"id": "titleBlock", "bbox": title, "hard": True} if title else None

    components: List[Dict[str, Any]] = []
    component_designators: Dict[str, str] = {}
    for item in list_data.get("components", []) or []:
        if item.get("componentType") != "part":
            continue
        identity = item.get("primitiveId")
        box = _dict_box(item.get("bbox"))
        if not identity or box is None:
            continue
        designator = item.get("designator")
        zone = _pick_zone(frames, box)
        components.append({
            "id": identity,
            "bbox": box,
            "designator": designator,
            "zone_id": zone["id"] if zone else None,
        })
        if designator:
            component_designators[identity] = designator

    wires: List[Dict[str, Any]] = []
    for wire in layout.get("wires", []) or []:
        points = [[float(point[0]), float(point[1])] for point in wire.get("points", [])]
        if len(points) < 2:
            continue
        item: Dict[str, Any] = {"id": wire.get("id"), "points": points}
        if wire.get("net"):
            item["net"] = wire["net"]
        if wire.get("primitive_id"):
            item["primitive_id"] = wire["primitive_id"]
        wires.append(item)

    text_meta = _text_metadata(list_data)
    rendered_rows = _rendered_index(rendered)
    designators = {}
    for item in list_data.get("components", []) or []:
        if item.get("designator"):
            designators[str(item.get("primitiveId"))] = str(item["designator"])

    fixed_texts: List[Dict[str, Any]] = []
    annotations: List[Dict[str, Any]] = []
    for text in layout.get("texts", []) or []:
        identity = str(text.get("id"))
        box = _box(text.get("bbox"))
        if box is None:
            raise ConvertError(f"text {identity}: missing bbox")
        kind = str(text.get("kind") or "unknown")
        owner = text.get("owner")
        content = str(text.get("content") or "")
        measured = "bbox" if text.get("measurement") == "bbox" else "estimated"
        bbox_source = "measured_svg" if measured == "bbox" else "estimated"
        if kind == "attribute" and owner in designators:
            role = "designator" if content == designators[owner] else "value"
            component = next((item for item in components if item["id"] == owner), None)
            zone = _pick_zone_strict(frames, box) or (
                _pick_zone(frames, component["bbox"]) if component else None)
            translations = {
                "id": identity,
                "role": role,
                "content": content,
                "kind": kind,
                "field": text.get("field") or "attribute",
                "current": {
                    "bbox": box,
                    "anchor": None,
                    "anchor_source": "unknown",
                    "align": "unknown",
                    "rotation_deg": None,
                    "rotation_source": "unknown",
                    "font_size": None,
                    "font_source": "unknown",
                },
                "bbox_source": bbox_source,
                "owner": {"kind": "component", "id": owner, "requirement": "keep_near"},
                "net": None,
                "anchor_id": None,
                "capability": {
                    "translate": "supported",
                    "rotate": "fixed",
                    "resize": "forbidden",
                    "content_change": "forbidden",
                    "net_change": "forbidden",
                    "source": "historical_docs_not_probed",
                },
                "constraints": {
                    "zone_id": zone["id"] if zone else None,
                    "keep_in_zone": bool(zone and _pick_zone_strict(frames, box)),
                    "allowed_directions": ["left", "right", "up", "down"],
                    "max_displacement": 80,
                    "grid": 5,
                    "owner_max_distance": 250,
                    "priority": 0,
                },
            }
            annotations.append(translations)
            continue
        if kind == "free_text":
            meta = text_meta.get(identity, {})
            anchor = None
            if meta.get("X") is not None and meta.get("Y") is not None:
                anchor = [float(meta["X"]), float(meta["Y"])]
            rotation = None
            if meta.get("Rotation") is not None:
                rotation = float(meta["Rotation"])
            align = "unknown"
            align_map = {0: "left", 1: "center", 2: "right", 3: "left", 4: "center",
                         5: "right", 6: "left", 7: "center", 8: "right"}
            if meta.get("AlignMode") is not None:
                align = align_map.get(int(meta["AlignMode"]), "unknown")
            zone = _pick_zone_strict(frames, box)
            annotations.append({
                "id": identity,
                "role": "free_text",
                "content": content,
                "kind": kind,
                "field": None,
                "current": {
                    "bbox": box,
                    "anchor": anchor,
                    "anchor_source": "declared" if anchor else "unknown",
                    "align": align,
                    "rotation_deg": rotation,
                    "rotation_source": "declared" if rotation is not None else "unknown",
                    "font_size": float(meta["FontSize"]) if meta.get("FontSize") is not None else None,
                    "font_source": "declared" if meta.get("FontSize") is not None else "unknown",
                },
                "bbox_source": bbox_source,
                "owner": ({"kind": "zone", "id": zone["id"], "requirement": "inside_zone"}
                          if zone else {"kind": "page", "id": "page", "requirement": "none"}),
                "net": None,
                "anchor_id": None,
                "capability": {
                    "translate": "unverified",
                    "rotate": "fixed",
                    "resize": "forbidden",
                    "content_change": "forbidden",
                    "net_change": "forbidden",
                    "source": "historical_docs_not_probed",
                },
                "constraints": {
                    "zone_id": zone["id"] if zone else None,
                    "keep_in_zone": bool(zone),
                    "allowed_directions": ["left", "right", "up", "down"],
                    "max_displacement": 80,
                    "grid": 5,
                    "owner_max_distance": 250,
                    "priority": 0,
                },
            })
            continue
        item: Dict[str, Any] = {
            "id": identity,
            "bbox": box,
            "kind": kind,
            "content": content,
            "measurement": measured,
        }
        if owner:
            item["owner_id"] = str(owner)
            item["owner_kind"] = "component" if owner in designators else "netflag"
        if text.get("net"):
            item["net"] = text["net"]
        if text.get("anchor_id"):
            item["anchor_id"] = text["anchor_id"]
            item["anchored"] = bool(text.get("anchored", True))
        if text.get("field"):
            item["field"] = text["field"]
        fixed_texts.append(item)

    expected = dict((layout.get("expected_counts") or {}))
    if expected:
        expected = {"components": int(expected.get("components", 0)),
                    "texts": int(expected.get("texts", 0)),
                    "wires": int(expected.get("wires", 0))}

    checker_context = {
        "policy": layout.get("policy") or {},
        "title_block_owned": layout.get("title_block_owned") or [],
        "label_anchors": layout.get("label_anchors") or [],
        "net_flags": layout.get("net_flags") or [],
        "attachment_points": layout.get("attachment_points") or [],
        "no_junction_crossings": layout.get("no_junction_crossings") or [],
        "journal_placeholder": None,
        "coverage": layout.get("coverage") or {},
        "expected_counts": expected or None,
        "module_frames": layout.get("module_frames") or [],
        "page_id": layout.get("page_id"),
        "snapshot_sha256": layout.get("snapshot_sha256"),
    }
    checker_context.pop("journal_placeholder")
    if layout.get("junction_evidence") is not None:
        checker_context["junction_evidence"] = layout["junction_evidence"]

    project = {
        "name": "photo-led-5v-20261026",
        "page_id": str(layout.get("page_id")),
        "page_name": "P1",
        "snapshot_sha256": str(layout.get("snapshot_sha256")),
    }
    for item in list_data.get("components", []) or []:
        props = item.get("otherProperty") or {}
        if props.get("@Project Name"):
            project["name"] = str(props["@Project Name"])
        if props.get("@Page Name"):
            project["page_name"] = str(props["@Page Name"])

    return {
        "schema": SCHEMA_ID,
        "project": project,
        "units": {
            "name": "schematic_raw",
            "raw_per_mm": round(RAW_PER_MM, 12),
            "description": "schematic raw units; 10 raw = 0.1 inch = 2.54 mm",
        },
        "coordinate_system": {
            "name": "easyeda-schematic-raw-y-up",
            "y_axis": "up",
            "svg_y_axis": "down",
            "transform": "source SVG text bbox is flipped once by negating y (svg_y = -raw_y); "
                         "analysis overlays use screen_y = page_height - raw_y",
        },
        "page": {
            "bbox": page_bbox,
            "usable_bbox": inner,
            "title_block": title_rect,
            "keepouts": keepouts,
            "zones": frames,
        },
        "components": components,
        "wires": wires,
        "fixed_texts": fixed_texts,
        "movable_annotations": annotations,
        "constraints": {
            "grid": 5,
            "min_text_text_gap": 2,
            "min_text_symbol_gap": 2,
            "min_text_wire_gap": 0,
            "min_text_wire_clearance": 5,
            "self_text_contact_tolerance": 1,
            "label_own_wire_edge_tolerance": 1,
            "max_candidates_per_annotation": 32,
            "max_total_candidates": 2000,
            "max_search_states": 20000,
            "max_local_search_steps": 2000,
            "max_displacement": 80,
            "owner_max_distance": 250,
            "forbid_font_change": True,
            "forbid_content_change": True,
            "forbid_net_change": True,
            "forbid_component_move": True,
            "freeze_ids": [],
            "scope": "all",
            "scope_cluster_ids": [],
        },
        "host": {
            "capabilities": {
                "attribute_translate": "supported",
                "free_text_translate": "unverified",
                "net_label_detach": "unsupported",
                "attribute_rotate": "unsupported",
            },
            "capability_source": "historical_docs_requires_onsite_probe",
            "execution": "not_executed",
        },
        "uncertainty": {
            "bbox_measured": True,
            "font_metrics_known": False,
            "symbol_outline_approximate": True,
            "notes": [
                "text bboxes are measured from the official EasyEDA 4.1.78 SVG",
                "symbol bodies are bbox approximations; pin-name/number/outline glyphs are not re-measured",
                "attribute rotation/alignment/font are not supplied by the retained list read",
                "free-text move persistence was historically unreliable and is NOT probed here",
            ],
        },
        "checker_context": checker_context,
    }


def write_document(document: Mapping[str, Any], layout_path: Path, list_path: Path,
                   rendered_path: Path, sheet_path: Path, out_path: Path,
                   copy_sources: bool) -> Dict[str, Any]:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source_paths = {
        "layout": Path(layout_path),
        "list": Path(list_path),
        "rendered": Path(rendered_path),
        "sheet": Path(sheet_path),
    }
    files = []
    from .schema import normalize_source_bytes

    for name in _SOURCE_KINDS:
        path = source_paths[name]
        if copy_sources:
            target = out_path.parent / path.name
            payload = normalize_source_bytes(path.read_bytes())
            target.write_bytes(payload)
            rel = target.name
            files.append({"path": rel,
                          "sha256": hashlib.sha256(payload).hexdigest()})
        else:
            try:
                rel = os.path.relpath(path, out_path.parent)
            except ValueError:
                rel = str(path)
            from .schema import source_file_sha256
            files.append({"path": rel, "sha256": source_file_sha256(path)})
    document = dict(document)
    document["source"] = {
        "kind": "frozen_fixture",
        "adapter": f"{TOOL_NAME}.convert/v1",
        "source_commit": BASE_COMMIT,
        "created": CREATED,
        "notes": "photo-led v14 frozen fixture: official EasyEDA 4.1.78 SVG text bbox read, "
                 "sch list component/page primitives, official-SVG sheet geometry; trimmed, not live",
        "files": files,
    }
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2,
                         allow_nan=False) + "\n"
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp, out_path)
    return document


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="annotation_layout convert",
        description="Convert the frozen photo-led adapter fixture to annotation-layout/v1")
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--list", required=True, type=Path)
    parser.add_argument("--rendered", required=True, type=Path)
    parser.add_argument("--sheet", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--copy-sources", action="store_true",
                        help="copy the four source files next to --out and hash them")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        document = build_document(args.layout, args.list, args.rendered, args.sheet)
        full = write_document(document, args.layout, args.list, args.rendered,
                              args.sheet, args.out, args.copy_sources)
    except (ConvertError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.quiet:
        print(json.dumps({
            "status": "ok",
            "schema": SCHEMA_ID,
            "tool_version": TOOL_VERSION,
            "output": str(args.out),
            "counts": {
                "components": len(full["components"]),
                "wires": len(full["wires"]),
                "fixed_texts": len(full["fixed_texts"]),
                "movable_annotations": len(full["movable_annotations"]),
            },
            "source_files": [item["path"] for item in full["source"]["files"]],
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
