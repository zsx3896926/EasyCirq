"""Shared helpers for the annotation-layout test suite.

The tests exercise the real CLI where the contract requires it
(``python -m annotation_layout`` in a subprocess) and import the package
directly for unit-level checks.  No EDA, network or host write is involved.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / "design-hardware" / "scripts"
FIXTURES = HERE / "fixtures"
SYNTHETIC = FIXTURES / "synthetic"
HOLDOUT = FIXTURES / "holdout"
INVALID = FIXTURES / "invalid"
REAL = FIXTURES / "photo-led-v14" / "input.json"
BENCH_CASES = ROOT / "benchmarks" / "annotation-layout" / "cases"

# Bind the shipped package under the name ``annotation_layout`` without touching
# ``sys.path``: this file is imported both as ``annotation_layout.helpers``
# (package-mode discovery) and as ``helpers`` (directory-mode discovery).
try:
    from . import _bootstrap  # type: ignore[import-not-found]
except ImportError:  # directory-mode discovery
    import importlib.util as _importlib_util

    _spec = _importlib_util.spec_from_file_location(
        "_annotation_layout_test_bootstrap", HERE / "_bootstrap.py")
    _bootstrap = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_bootstrap)
_bootstrap.ensure_impl()

ENV = dict(os.environ)
ENV["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + ENV.get("PYTHONPATH", "")
ENV["PYTHONIOENCODING"] = "utf-8"
ENV.setdefault("PYTHONDONTWRITEBYTECODE", "1")


def run_cli(args: Sequence[str], *, timeout: int = 300) -> Tuple[int, Any, str, str]:
    """Run the real module entry point; return (exit, parsed stdout, stderr, raw)."""
    command = [sys.executable, "-m", "annotation_layout", *args]
    completed = subprocess.run(command, cwd=str(SCRIPTS), env=ENV,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", timeout=timeout)
    stdout = completed.stdout.strip()
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout is not a single JSON document: {exc}\nstdout head: "
                f"{stdout[:400]!r}\nstderr: {completed.stderr[:400]!r}") from exc
    return completed.returncode, parsed, completed.stderr, stdout


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def synthetic(name: str) -> Path:
    return SYNTHETIC / f"{name}.json"


def holdout(name: str) -> Path:
    return HOLDOUT / f"{name}.json"


def invalid(name: str) -> Path:
    return INVALID / name


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_sha256(path: Path) -> str:
    """Provenance hash over LF-normalized bytes (same rule as schema.py)."""
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def canonical_hash(document: Mapping[str, Any]) -> str:
    source = json.dumps(document, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def load_document(path: Path) -> Dict[str, Any]:
    return read_json(path)


def apply_changes(document: Mapping[str, Any],
                  changes: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return a copy of the input with the accepted annotation poses applied."""
    updated = copy.deepcopy(document)
    by_id = {item["id"]: item for item in updated["movable_annotations"]}
    for change in changes:
        identity = change["id"]
        after = change["after"]
        target = by_id[identity]
        target["current"]["bbox"] = [float(value) for value in after["bbox"]]
        target["current"]["anchor"] = after.get("anchor")
    return updated


def plan_document(document: Mapping[str, Any], tmp: Path, *,
                  extra: Sequence[str] = ()) -> Tuple[int, Any, str]:
    input_path = tmp / "input.json"
    write_json(input_path, document)
    code, payload, stderr, _ = run_cli(["plan", str(input_path), *extra])
    return code, payload, stderr


def plan_fixture(path: Path, tmp: Path, *, extra: Sequence[str] = ()) -> Tuple[int, Any, str]:
    code, payload, stderr, _ = run_cli(["plan", str(path), *extra])
    return code, payload, stderr


def mini_input(*, annotations: Sequence[Mapping[str, Any]],
               components: Sequence[Mapping[str, Any]] = (),
               fixed_texts: Sequence[Mapping[str, Any]] = (),
               wires: Sequence[Mapping[str, Any]] = (),
               constraints: Optional[Mapping[str, Any]] = None,
               zones: Optional[Sequence[Mapping[str, Any]]] = None,
               title_block: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """Small hand-built v1 document for unit tests (marked synthetic)."""
    page = [0.0, 0.0, 400.0, 300.0]
    usable = [5.0, 5.0, 395.0, 295.0]
    zone = {"id": "z1", "name": "zone 1", "bbox": [10.0, 10.0, 390.0, 290.0],
            "hard": False, "source": "synthetic_declared"}
    zones = list(zones or [zone])
    default = {
        "grid": 5,
        "min_text_text_gap": 2,
        "min_text_symbol_gap": 2,
        "min_text_wire_gap": 0,
        "min_text_wire_clearance": 5,
        "self_text_contact_tolerance": 1,
        "label_own_wire_edge_tolerance": 1,
        "max_candidates_per_annotation": 24,
        "max_total_candidates": 400,
        "max_search_states": 5000,
        "max_local_search_steps": 500,
        "max_displacement": 60,
        "owner_max_distance": 200,
        "forbid_font_change": True,
        "forbid_content_change": True,
        "forbid_net_change": True,
        "forbid_component_move": True,
        "freeze_ids": [],
        "scope": "all",
        "scope_cluster_ids": [],
    }
    default.update(constraints or {})
    page_dict: Dict[str, Any] = {
        "bbox": page, "usable_bbox": usable,
        "keepouts": [],
        "zones": zones,
    }
    if title_block is not None:
        page_dict["title_block"] = {"id": "titleBlock", "bbox": list(title_block),
                                    "hard": True}
        page_dict["keepouts"].append({"id": "titleBlock", "bbox": list(title_block),
                                      "hard": True, "reason": "title block"})
    return {
        "schema": "annotation-layout/v1",
        "project": {"name": "unit-test", "page_id": "page-unit", "page_name": "P1",
                    "snapshot_sha256": "0" * 64},
        "source": {"kind": "synthetic", "adapter": "tests/annotation_layout/helpers.py",
                   "source_commit": "9a951edc21481dc3ae91460acc11aa3e08a7be8a",
                   "created": "2026-10-27", "notes": "unit-test synthetic document",
                   "files": []},
        "units": {"name": "schematic_raw", "raw_per_mm": 3.937007874015748,
                  "description": "synthetic raw units"},
        "coordinate_system": {"name": "synthetic-raw-y-up", "y_axis": "up",
                              "svg_y_axis": "down",
                              "transform": "screen_y = page_height - raw_y"},
        "page": page_dict,
        "components": [dict(item) for item in components],
        "wires": [dict(item) for item in wires],
        "fixed_texts": [dict(item) for item in fixed_texts],
        "movable_annotations": [dict(item) for item in annotations],
        "constraints": default,
        "host": {
            "capabilities": {
                "attribute_translate": "supported",
                "free_text_translate": "unverified",
                "net_label_detach": "unsupported",
            },
            "capability_source": "unit_test_declared",
            "execution": "not_executed",
        },
        "uncertainty": {"bbox_measured": True, "font_metrics_known": False,
                        "symbol_outline_approximate": True, "notes": []},
        "checker_context": {},
    }


def annotation(identity: str, role: str, content: str, bbox: Sequence[float], *,
               owner_id: Optional[str] = None, zone_id: Optional[str] = "z1",
               keep_in_zone: bool = False, bbox_source: str = "measured_svg",
               rotation: Optional[float] = None, net: Optional[str] = None,
               anchor_id: Optional[str] = None, translate: Optional[str] = None,
               max_displacement: float = 60.0,
               directions: Sequence[str] = ("left", "right", "up", "down")) -> Dict[str, Any]:
    if translate is None:
        translate = "unverified" if role in ("free_text", "purpose_text") else "supported"
    return {
        "id": identity, "role": role, "content": content,
        "kind": "attribute" if role in ("designator", "value") else "free_text",
        "field": "attribute" if role in ("designator", "value") else None,
        "current": {
            "bbox": list(bbox), "anchor": None, "anchor_source": "unknown",
            "align": "unknown", "rotation_deg": rotation,
            "rotation_source": "declared" if rotation is not None else "unknown",
            "font_size": None, "font_source": "unknown",
        },
        "bbox_source": bbox_source,
        "owner": ({"kind": "component", "id": owner_id, "requirement": "keep_near"}
                  if owner_id else {"kind": "zone", "id": zone_id,
                                    "requirement": "inside_zone"}),
        "net": net, "anchor_id": anchor_id,
        "capability": {"translate": translate, "rotate": "fixed",
                       "resize": "forbidden", "content_change": "forbidden",
                       "net_change": "forbidden", "source": "unit_test_declared"},
        "constraints": {
            "zone_id": zone_id, "keep_in_zone": keep_in_zone,
            "allowed_directions": list(directions),
            "max_displacement": max_displacement, "grid": 5,
            "owner_max_distance": 200, "priority": 0,
        },
    }


def component(identity: str, bbox: Sequence[float], designator: str,
              zone_id: Optional[str] = "z1") -> Dict[str, Any]:
    return {"id": identity, "bbox": list(bbox), "designator": designator,
            "zone_id": zone_id}


def fixed_text(identity: str, kind: str, content: str, bbox: Sequence[float],
               **extra: Any) -> Dict[str, Any]:
    item = {"id": identity, "bbox": list(bbox), "kind": kind, "content": content,
            "measurement": "bbox"}
    item.update(extra)
    return item


def wire(identity: str, points: Sequence[Sequence[float]],
         net: Optional[str] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"id": identity,
                            "points": [[float(x), float(y)] for x, y in points]}
    if net:
        item["net"] = net
    return item
