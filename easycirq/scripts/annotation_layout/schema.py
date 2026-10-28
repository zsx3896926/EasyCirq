"""Strict parser/validator for the annotation-layout/v1 input document.

Every violation raises :class:`model.InputError` with all reasons collected so
the CLI can report ``input_invalid`` (exit 2) without leaking a partial result.
No value is coerced from bool, NaN or a string; unknown keys are rejected.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .model import (
    ALL_ROLES,
    CAPABILITIES,
    DIRECTIONS,
    FIXED_ROLES,
    SCHEMA_ID,
    AnnConstraints,
    Annotation,
    Capability,
    Component,
    Constraints,
    CoordinateSystem,
    FixedText,
    HOST_CAPABILITY_KEYS,
    Host,
    Input,
    InputError,
    Keepout,
    OwnerRef,
    Page,
    Project,
    Rect,
    Source,
    SourceFile,
    TextStyle,
    Uncertainty,
    Units,
    Wire,
    Zone,
    canonical_sha256,
    text_sha256,
)
from .geometry import finite

MAX_OBJECTS = 5000

CHECKER_CONTEXT_KEYS = {
    "policy", "title_block_owned", "label_anchors", "net_flags",
    "attachment_points", "no_junction_crossings", "junction_evidence",
    "coverage", "expected_counts", "module_frames", "page_id", "snapshot_sha256",
}

_BBOX_KEYS = ("minX", "minY", "maxX", "maxY")


class _Validator:
    def __init__(self) -> None:
        self.reasons: List[str] = []

    def fail(self, reason: str) -> None:
        self.reasons.append(reason)

    def check(self, condition: bool, reason: str) -> bool:
        if not condition:
            self.fail(reason)
        return condition

    # -- primitive helpers -------------------------------------------------
    def obj(self, value: Any, path: str, required: Iterable[str],
            optional: Iterable[str]) -> Optional[Mapping[str, Any]]:
        if not isinstance(value, dict):
            self.fail(f"{path}: object required")
            return None
        required = set(required)
        optional = set(optional)
        unknown = sorted(set(value) - required - optional)
        missing = sorted(required - set(value))
        if unknown:
            self.fail(f"{path}: unknown key(s) {', '.join(unknown)}")
        if missing:
            self.fail(f"{path}: missing key(s) {', '.join(missing)}")
        return value

    def string(self, value: Any, path: str, allow_empty: bool = False) -> Optional[str]:
        if not isinstance(value, str):
            self.fail(f"{path}: string required")
            return None
        if not allow_empty and not value.strip():
            self.fail(f"{path}: non-empty string required")
            return None
        return value

    def number(self, value: Any, path: str, positive: bool = False,
               nonnegative: bool = False) -> Optional[float]:
        if type(value) not in (int, float):
            self.fail(f"{path}: number required (booleans are not numbers)")
            return None
        number = float(value)
        if not math.isfinite(number):
            self.fail(f"{path}: finite number required")
            return None
        if positive and number <= 0:
            self.fail(f"{path}: positive number required")
            return None
        if nonnegative and number < 0:
            self.fail(f"{path}: nonnegative number required")
            return None
        return number

    def integer(self, value: Any, path: str, positive: bool = False,
                nonnegative: bool = False) -> Optional[int]:
        if type(value) is not int:
            self.fail(f"{path}: integer required (booleans are not integers)")
            return None
        if positive and value <= 0:
            self.fail(f"{path}: positive integer required")
            return None
        if nonnegative and value < 0:
            self.fail(f"{path}: nonnegative integer required")
            return None
        return value

    def boolean(self, value: Any, path: str) -> Optional[bool]:
        if type(value) is not bool:
            self.fail(f"{path}: boolean required")
            return None
        return value

    def enum(self, value: Any, path: str, allowed: Sequence[str]) -> Optional[str]:
        if not isinstance(value, str) or value not in allowed:
            self.fail(f"{path}: one of {', '.join(allowed)} required")
            return None
        return value

    def bbox(self, value: Any, path: str) -> Optional[Rect]:
        if not isinstance(value, list) or len(value) != 4:
            self.fail(f"{path}: bbox must be [left,bottom,right,top]")
            return None
        numbers: List[float] = []
        for index, item in enumerate(value):
            number = self.number(item, f"{path}[{index}]")
            if number is None:
                return None
            numbers.append(number)
        if numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
            self.fail(f"{path}: bbox must have positive ordered extent")
            return None
        return Rect(*numbers)

    def point(self, value: Any, path: str) -> Optional[Tuple[float, float]]:
        if not isinstance(value, list) or len(value) != 2:
            self.fail(f"{path}: point must be [x,y]")
            return None
        x = self.number(value[0], f"{path}[0]")
        y = self.number(value[1], f"{path}[1]")
        if x is None or y is None:
            return None
        return (x, y)

    def sha256(self, value: Any, path: str) -> Optional[str]:
        text = self.string(value, path)
        if text is None:
            return None
        if len(text) != 64 or any(char not in "0123456789abcdefABCDEF" for char in text):
            self.fail(f"{path}: 64-character hex SHA-256 required")
            return None
        return text.lower()

    def string_list(self, value: Any, path: str) -> Optional[Tuple[str, ...]]:
        if not isinstance(value, list):
            self.fail(f"{path}: list of strings required")
            return None
        result: List[str] = []
        for index, item in enumerate(value):
            text = self.string(item, f"{path}[{index}]")
            if text is not None:
                result.append(text)
        return tuple(result)


def _read_json_bytes(raw: bytes, origin: str) -> Any:
    def reject_constant(value: str) -> None:
        raise InputError([f"{origin}: {value} is not allowed"])

    def reject_duplicates(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InputError([f"{origin}: duplicate JSON key {key!r}"])
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError([f"{origin}: not valid UTF-8 ({exc})"]) from exc
    try:
        return json.loads(text, object_pairs_hook=reject_duplicates,
                          parse_constant=reject_constant)
    except InputError:
        raise
    except json.JSONDecodeError as exc:
        raise InputError([f"{origin}: invalid JSON at line {exc.lineno}: {exc.msg}"]) from exc


def load_json_file(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise InputError([f"{path}: cannot read input ({exc})"]) from exc
    return _read_json_bytes(raw, str(path))


def validate_input(document: Any, origin: str = "<memory>",
                   base_dir: Optional[Path] = None,
                   verify_source_files: bool = True) -> Input:
    if not isinstance(document, dict):
        raise InputError([f"{origin}: top-level JSON object required"])
    v = _Validator()
    top = v.obj(document, "input", ["schema", "project", "units", "coordinate_system",
                                    "page", "components", "wires", "fixed_texts",
                                    "movable_annotations", "constraints", "host",
                                    "uncertainty"],
                ["source", "checker_context"])

    if top is None:
        raise InputError(v.reasons or ["input: object required"])

    schema = v.string(document.get("schema"), "schema")
    if schema is not None and schema != SCHEMA_ID:
        v.fail(f"schema: expected {SCHEMA_ID}, got {schema}")

    project = _project(v, document.get("project"))
    source = _source(v, document.get("source"), base_dir, verify_source_files) if "source" in document else None
    units = _units(v, document.get("units"))
    coordinate_system = _coordinate_system(v, document.get("coordinate_system"))
    page = _page(v, document.get("page"))
    components = _components(v, document.get("components"))
    wires = _wires(v, document.get("wires"))
    fixed_texts = _fixed_texts(v, document.get("fixed_texts"))
    annotations = _annotations(v, document.get("movable_annotations"))
    constraints = _constraints(v, document.get("constraints"))
    host = _host(v, document.get("host"))
    uncertainty = _uncertainty(v, document.get("uncertainty"))
    checker_context = _checker_context(v, document.get("checker_context"))

    # -- cross-object identity -------------------------------------------------
    seen_ids: Dict[str, str] = {}

    def register(identity: Optional[str], group: str) -> None:
        if identity is None:
            return
        if identity in seen_ids:
            v.fail(f"duplicate object ID {identity!r} in {group} and {seen_ids[identity]}")
        else:
            seen_ids[identity] = group

    for item in components:
        register(item.id, "components")
    for item in wires:
        register(item.id, "wires")
    for item in fixed_texts:
        register(item.id, "fixed_texts")
    for item in annotations:
        register(item.id, "movable_annotations")
    if page is not None:
        for item in page.zones:
            register(item.id, "page.zones")
        for item in page.keepouts:
            register(item.id, "page.keepouts")

    component_ids = {item.id for item in components}
    wire_ids = {item.id for item in wires}
    annotation_ids = {item.id for item in annotations}
    zone_ids = {item.id for item in page.zones} if page else set()

    for index, item in enumerate(annotations):
        if item.owner is not None:
            if item.owner.kind == "component" and item.owner.id not in component_ids:
                v.fail(f"movable_annotations[{index}].owner.id: unknown component {item.owner.id!r}")
            if item.owner.kind == "zone" and item.owner.id not in zone_ids:
                v.fail(f"movable_annotations[{index}].owner.id: unknown zone {item.owner.id!r}")
        if item.constraints.zone_id and item.constraints.zone_id not in zone_ids:
            v.fail(f"movable_annotations[{index}].constraints.zone_id: unknown zone "
                   f"{item.constraints.zone_id!r}")
        if item.anchor_id and item.anchor_id not in wire_ids:
            v.fail(f"movable_annotations[{index}].anchor_id: unknown wire {item.anchor_id!r}")
        if item.role in FIXED_ROLES and item.capability.translate != "unsupported":
            v.fail(f"movable_annotations[{index}]: role {item.role!r} is fixed and cannot translate")
        if item.role in ("designator", "value") and (
                item.owner is None or item.owner.kind != "component"):
            v.fail(f"movable_annotations[{index}]: {item.role} needs owner kind=component")
        if item.role in ("free_text", "purpose_text") and item.constraints.keep_in_zone:
            if not item.constraints.zone_id and not (
                    item.owner is not None and item.owner.kind == "zone"):
                v.fail(f"movable_annotations[{index}]: keep_in_zone needs a zone_id or "
                       "owner kind=zone")
        if item.role in ("net_label", "wire_name"):
            if not item.anchor_id or not item.net:
                v.fail(f"movable_annotations[{index}]: net label needs anchor_id and net")
            if item.capability.translate != "unsupported" and host is not None and \
                    host.capabilities.get("net_label_detach") != "supported":
                v.fail(f"movable_annotations[{index}]: net-label text cannot move without "
                       "host.net_label_detach=supported")
        if item.owner and item.owner.requirement not in ("keep_near", "inside_zone", "fixed", "none"):
            v.fail(f"movable_annotations[{index}].owner.requirement: unknown requirement")

    if host is not None:
        capability_key = {
            "designator": "attribute_translate",
            "value": "attribute_translate",
            "free_text": "free_text_translate",
            "purpose_text": "free_text_translate",
            "net_label": "net_label_detach",
            "wire_name": "net_label_detach",
        }
        for index, item in enumerate(annotations):
            key = capability_key.get(item.role)
            if key is None:
                continue
            declared = host.capabilities.get(key)
            if item.capability.translate == "supported" and declared == "unsupported":
                v.fail(f"movable_annotations[{index}]: capability translate=supported "
                       f"contradicts host.capabilities.{key}=unsupported")

    if constraints is not None:
        for frozen in constraints.freeze_ids:
            if frozen not in annotation_ids:
                v.fail(f"constraints.freeze_ids: unknown annotation {frozen!r}")
        for scoped in constraints.scope_cluster_ids:
            if scoped not in annotation_ids:
                v.fail(f"constraints.scope_cluster_ids: unknown annotation {scoped!r}")
        if constraints.scope == "cluster" and not constraints.scope_cluster_ids:
            v.fail("constraints.scope_cluster_ids: required when scope=cluster")

    if page is not None:
        if not page.bbox.contains_rect(page.usable_bbox):
            v.fail("page.usable_bbox: must be inside page.bbox")
        if page.title_block is not None and not page.bbox.contains_rect(page.title_block):
            v.fail("page.title_block: must be inside page.bbox")
        for keepout in page.keepouts:
            if not page.bbox.contains_rect(keepout.bbox):
                v.fail(f"page.keepouts[{keepout.id}]: must be inside page.bbox")
        for zone in page.zones:
            if not page.bbox.contains_rect(zone.bbox):
                v.fail(f"page.zones[{zone.id}]: must be inside page.bbox")
        # all annotation/text bboxes and wire points must use the declared page
        # coordinate space; an outside pose is a conflict, not an input error,
        # but a wildly out-of-range coordinate is an extraction mistake.
        limit = Rect(page.bbox.x0 - 2 * page.bbox.width,
                     page.bbox.y0 - 2 * page.bbox.height,
                     page.bbox.x1 + 2 * page.bbox.width,
                     page.bbox.y1 + 2 * page.bbox.height)
        for item in fixed_texts:
            if not limit.contains_rect(item.bbox):
                v.fail(f"{item.id}: bbox is far outside the page; coordinate system likely wrong")
        for item in annotations:
            if not limit.contains_rect(item.current.bbox):
                v.fail(f"{item.id}: bbox is far outside the page; coordinate system likely wrong")
        for wire in wires:
            if any(not limit.contains_point(p) for p in wire.points):
                v.fail(f"{wire.id}: wire point is far outside the page; coordinate system likely wrong")

    if checker_context is not None:
        page_id = checker_context.get("page_id")
        if page_id is not None and project is not None and page_id != project.page_id:
            v.fail("checker_context.page_id: does not match project.page_id")
        snapshot = checker_context.get("snapshot_sha256")
        if snapshot is not None and project is not None and \
                str(snapshot).lower() != project.snapshot_sha256:
            v.fail("checker_context.snapshot_sha256: does not match project.snapshot_sha256")
        evidence = checker_context.get("junction_evidence")
        if isinstance(evidence, dict) and project is not None:
            if str(evidence.get("page_id")) != project.page_id or \
                    str(evidence.get("snapshot_sha256", "")).lower() != project.snapshot_sha256:
                v.fail("checker_context.junction_evidence: stale page/snapshot binding")
        if checker_context.get("no_junction_crossings") and not evidence:
            v.fail("checker_context.no_junction_crossings requires junction_evidence")

    if v.reasons:
        raise InputError(v.reasons)
    assert project is not None and units is not None and coordinate_system is not None
    assert page is not None and constraints is not None and host is not None
    assert uncertainty is not None
    assert source is not None
    return Input(
        path=origin,
        canonical_sha256=canonical_sha256(document),
        project=project,
        source=source,
        units=units,
        coordinate_system=coordinate_system,
        page=page,
        components=components,
        wires=wires,
        fixed_texts=fixed_texts,
        annotations=annotations,
        constraints=constraints,
        host=host,
        uncertainty=uncertainty,
        checker_context=checker_context or {},
    )


def load_input(path: str | Path, verify_source_files: bool = True) -> Input:
    path = Path(path)
    document = load_json_file(path)
    return validate_input(document, origin=str(path), base_dir=path.parent,
                          verify_source_files=verify_source_files)


# ---------------------------------------------------------------------------
# section parsers


def _project(v: _Validator, value: Any) -> Optional[Project]:
    item = v.obj(value, "project", ["name", "page_id", "page_name"], ["snapshot_sha256"])
    if item is None:
        return None
    name = v.string(item.get("name"), "project.name")
    page_id = v.string(item.get("page_id"), "project.page_id")
    page_name = v.string(item.get("page_name"), "project.page_name")
    snapshot = v.sha256(item.get("snapshot_sha256"), "project.snapshot_sha256")
    if None in (name, page_id, page_name, snapshot):
        return None
    return Project(name, page_id, page_name, snapshot)


def normalize_source_bytes(raw: bytes) -> bytes:
    """Line-ending-neutral source bytes used for provenance hashes.

    Repository fixtures may be checked out with LF or CRLF (git autocrlf); a
    line-ending-only difference is not a content change, so provenance is bound
    to the LF-normalized bytes on every platform.
    """
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def source_file_sha256(path: str | Path) -> str:
    return hashlib.sha256(normalize_source_bytes(Path(path).read_bytes())).hexdigest()


def _source(v: _Validator, value: Any, base_dir: Optional[Path],
            verify_files: bool) -> Optional[Source]:
    item = v.obj(value, "source", ["kind", "adapter", "source_commit", "created",
                                   "notes"], ["files"])
    if item is None:
        return None
    kind = v.enum(item.get("kind"), "source.kind",
                  ("frozen_fixture", "snapshot_conversion", "synthetic"))
    adapter = v.string(item.get("adapter"), "source.adapter")
    commit = v.string(item.get("source_commit"), "source.source_commit")
    created = v.string(item.get("created"), "source.created")
    notes = v.string(item.get("notes"), "source.notes", allow_empty=True) or ""
    files: List[SourceFile] = []
    raw_files = item.get("files", [])
    if not isinstance(raw_files, list):
        v.fail("source.files: list required")
        raw_files = []
    for index, entry in enumerate(raw_files):
        fields = v.obj(entry, f"source.files[{index}]", ["path", "sha256"], [])
        if fields is None:
            continue
        rel = v.string(fields.get("path"), f"source.files[{index}].path")
        sha = v.sha256(fields.get("sha256"), f"source.files[{index}].sha256")
        if rel is None or sha is None:
            continue
        files.append(SourceFile(rel, sha))
        if verify_files:
            target = Path(rel)
            if not target.is_absolute() and base_dir is not None:
                target = base_dir / target
            try:
                actual = source_file_sha256(target)
            except OSError:
                v.fail(f"source.files[{index}]: cannot read {target} for hash check")
                continue
            if actual != sha:
                v.fail(f"source.files[{index}]: stale source file {rel} "
                       f"(sha256 mismatch)")
    if None in (kind, adapter, commit, created):
        return None
    return Source(kind, adapter, commit, created, notes, tuple(files))


def _units(v: _Validator, value: Any) -> Optional[Units]:
    item = v.obj(value, "units", ["name", "raw_per_mm", "description"], [])
    if item is None:
        return None
    name = v.enum(item.get("name"), "units.name", ("schematic_raw",))
    rate = v.number(item.get("raw_per_mm"), "units.raw_per_mm", positive=True)
    description = v.string(item.get("description"), "units.description")
    if name is None or rate is None or description is None:
        return None
    return Units(name, rate, description)


def _coordinate_system(v: _Validator, value: Any) -> Optional[CoordinateSystem]:
    item = v.obj(value, "coordinate_system", ["name", "y_axis", "svg_y_axis",
                                              "transform"], [])
    if item is None:
        return None
    name = v.string(item.get("name"), "coordinate_system.name")
    y_axis = v.enum(item.get("y_axis"), "coordinate_system.y_axis", ("up",))
    svg_y_axis = v.enum(item.get("svg_y_axis"), "coordinate_system.svg_y_axis", ("down",))
    transform = v.string(item.get("transform"), "coordinate_system.transform")
    if None in (name, y_axis, svg_y_axis, transform):
        return None
    return CoordinateSystem(name, y_axis, svg_y_axis, transform)


def _page(v: _Validator, value: Any) -> Optional[Page]:
    item = v.obj(value, "page", ["bbox", "usable_bbox"], ["title_block", "keepouts", "zones"])
    if item is None:
        return None
    bbox = v.bbox(item.get("bbox"), "page.bbox")
    usable = v.bbox(item.get("usable_bbox"), "page.usable_bbox")
    title = None
    if "title_block" in item:
        raw_title = item.get("title_block")
        title_obj = v.obj(raw_title, "page.title_block", ["bbox"], ["id", "hard"])
        if title_obj is not None:
            title = v.bbox(title_obj.get("bbox"), "page.title_block.bbox")
            if "hard" in title_obj:
                v.boolean(title_obj.get("hard"), "page.title_block.hard")
    keepouts: List[Keepout] = []
    raw_keepouts = item.get("keepouts", [])
    if not isinstance(raw_keepouts, list):
        v.fail("page.keepouts: list required")
        raw_keepouts = []
    for index, raw in enumerate(raw_keepouts):
        entry = v.obj(raw, f"page.keepouts[{index}]", ["id", "bbox", "hard", "reason"], [])
        if entry is None:
            continue
        identity = v.string(entry.get("id"), f"page.keepouts[{index}].id")
        box = v.bbox(entry.get("bbox"), f"page.keepouts[{index}].bbox")
        hard = v.boolean(entry.get("hard"), f"page.keepouts[{index}].hard")
        reason = v.string(entry.get("reason"), f"page.keepouts[{index}].reason")
        if None not in (identity, box, hard, reason):
            keepouts.append(Keepout(identity, box, hard, reason))
    zones: List[Zone] = []
    raw_zones = item.get("zones", [])
    if not isinstance(raw_zones, list):
        v.fail("page.zones: list required")
        raw_zones = []
    for index, raw in enumerate(raw_zones):
        entry = v.obj(raw, f"page.zones[{index}]", ["id", "name", "bbox", "hard"], ["source"])
        if entry is None:
            continue
        identity = v.string(entry.get("id"), f"page.zones[{index}].id")
        name = v.string(entry.get("name"), f"page.zones[{index}].name")
        box = v.bbox(entry.get("bbox"), f"page.zones[{index}].bbox")
        hard = v.boolean(entry.get("hard"), f"page.zones[{index}].hard")
        origin = v.string(entry.get("source", "declared"), f"page.zones[{index}].source")
        if None not in (identity, name, box, hard, origin):
            zones.append(Zone(identity, name, box, hard, origin))
    if None in (bbox, usable):
        return None
    return Page(bbox, usable, title, tuple(keepouts), tuple(zones))


def _components(v: _Validator, value: Any) -> Tuple[Component, ...]:
    if not isinstance(value, list) or len(value) > MAX_OBJECTS:
        v.fail(f"components: list of at most {MAX_OBJECTS} objects required")
        return ()
    result: List[Component] = []
    for index, raw in enumerate(value):
        entry = v.obj(raw, f"components[{index}]", ["id", "bbox"], ["designator", "zone_id"])
        if entry is None:
            continue
        identity = v.string(entry.get("id"), f"components[{index}].id")
        box = v.bbox(entry.get("bbox"), f"components[{index}].bbox")
        designator = None
        if entry.get("designator") is not None:
            designator = v.string(entry.get("designator"), f"components[{index}].designator")
        zone_id = None
        if entry.get("zone_id") is not None:
            zone_id = v.string(entry.get("zone_id"), f"components[{index}].zone_id")
        if identity is not None and box is not None:
            result.append(Component(identity, box, designator, zone_id))
    return tuple(result)


def _wires(v: _Validator, value: Any) -> Tuple[Wire, ...]:
    if not isinstance(value, list) or len(value) > MAX_OBJECTS:
        v.fail(f"wires: list of at most {MAX_OBJECTS} objects required")
        return ()
    result: List[Wire] = []
    total_segments = 0
    for index, raw in enumerate(value):
        entry = v.obj(raw, f"wires[{index}]", ["id", "points"], ["net", "primitive_id"])
        if entry is None:
            continue
        identity = v.string(entry.get("id"), f"wires[{index}].id")
        raw_points = entry.get("points")
        points: List[Tuple[float, float]] = []
        if not isinstance(raw_points, list) or len(raw_points) < 2:
            v.fail(f"wires[{index}].points: at least two points required")
        else:
            for point_index, raw_point in enumerate(raw_points):
                point = v.point(raw_point, f"wires[{index}].points[{point_index}]")
                if point is None:
                    break
                if points and points[-1] == point:
                    v.fail(f"wires[{index}].points: duplicate consecutive point")
                    break
                points.append(point)
        net = None
        if entry.get("net") is not None:
            net = v.string(entry.get("net"), f"wires[{index}].net")
        primitive = None
        if entry.get("primitive_id") is not None:
            primitive = v.string(entry.get("primitive_id"), f"wires[{index}].primitive_id")
        if identity is not None and len(points) >= 2:
            total_segments += len(points) - 1
            result.append(Wire(identity, tuple(points), net, primitive or identity))
    if total_segments > 5000:
        v.fail("wires: snapshot exceeds 5000 segments; split by page")
    return tuple(result)


def _measurement(v: _Validator, value: Any, path: str) -> Optional[str]:
    return v.enum(value, path, ("bbox", "estimated"))


def _fixed_texts(v: _Validator, value: Any) -> Tuple[FixedText, ...]:
    if not isinstance(value, list) or len(value) > MAX_OBJECTS:
        v.fail(f"fixed_texts: list of at most {MAX_OBJECTS} objects required")
        return ()
    result: List[FixedText] = []
    for index, raw in enumerate(value):
        entry = v.obj(raw, f"fixed_texts[{index}]",
                      ["id", "bbox", "kind", "content"],
                      ["owner_id", "owner_kind", "net", "anchor_id", "anchored",
                       "measurement", "field"])
        if entry is None:
            continue
        identity = v.string(entry.get("id"), f"fixed_texts[{index}].id")
        box = v.bbox(entry.get("bbox"), f"fixed_texts[{index}].bbox")
        kind = v.string(entry.get("kind"), f"fixed_texts[{index}].kind")
        content = v.string(entry.get("content"), f"fixed_texts[{index}].content",
                            allow_empty=True)
        owner_id = entry.get("owner_id")
        if owner_id is not None:
            owner_id = v.string(owner_id, f"fixed_texts[{index}].owner_id")
        owner_kind = entry.get("owner_kind")
        if owner_kind is not None:
            owner_kind = v.string(owner_kind, f"fixed_texts[{index}].owner_kind")
        net = entry.get("net")
        if net is not None:
            net = v.string(net, f"fixed_texts[{index}].net")
        anchor_id = entry.get("anchor_id")
        if anchor_id is not None:
            anchor_id = v.string(anchor_id, f"fixed_texts[{index}].anchor_id")
        anchored = None
        if "anchored" in entry:
            anchored = v.boolean(entry.get("anchored"), f"fixed_texts[{index}].anchored")
        measurement = _measurement(v, entry.get("measurement", "bbox"),
                                   f"fixed_texts[{index}].measurement")
        field_name = None
        if entry.get("field") is not None:
            field_name = v.string(entry.get("field"), f"fixed_texts[{index}].field")
        if None not in (identity, box, kind, content, measurement):
            result.append(FixedText(identity, box, kind, content, owner_id, owner_kind,
                                    net, anchor_id, anchored, measurement, field_name))
    return tuple(result)


def _annotations(v: _Validator, value: Any) -> Tuple[Annotation, ...]:
    if not isinstance(value, list) or len(value) > MAX_OBJECTS:
        v.fail(f"movable_annotations: list of at most {MAX_OBJECTS} objects required")
        return ()
    result: List[Annotation] = []
    for index, raw in enumerate(value):
        path = f"movable_annotations[{index}]"
        entry = v.obj(raw, path,
                      ["id", "role", "content", "kind", "current", "bbox_source",
                       "capability", "constraints"],
                      ["field", "owner", "net", "anchor_id"])
        if entry is None:
            continue
        identity = v.string(entry.get("id"), f"{path}.id")
        role = v.enum(entry.get("role"), f"{path}.role", ALL_ROLES)
        content = v.string(entry.get("content"), f"{path}.content", allow_empty=True)
        kind = v.string(entry.get("kind"), f"{path}.kind")
        field_name = entry.get("field")
        if field_name is not None:
            field_name = v.string(field_name, f"{path}.field")
        current = _text_style(v, entry.get("current"), f"{path}.current")
        bbox_source = v.enum(entry.get("bbox_source"), f"{path}.bbox_source",
                             ("measured_svg", "measured_api", "declared", "estimated"))
        capability = _capability(v, entry.get("capability"), f"{path}.capability")
        constraints = _ann_constraints(v, entry.get("constraints"), f"{path}.constraints")
        owner = None
        if entry.get("owner") is not None:
            raw_owner = v.obj(entry.get("owner"), f"{path}.owner", ["kind", "id"], ["requirement"])
            if raw_owner is not None:
                owner_kind = v.enum(raw_owner.get("kind"), f"{path}.owner.kind",
                                    ("component", "zone", "page", "net", "unknown"))
                owner_id = v.string(raw_owner.get("id"), f"{path}.owner.id")
                requirement = v.enum(raw_owner.get("requirement", "keep_near"),
                                     f"{path}.owner.requirement",
                                     ("keep_near", "inside_zone", "fixed", "none"))
                if None not in (owner_kind, owner_id, requirement):
                    owner = OwnerRef(owner_kind, owner_id, requirement)
        net = entry.get("net")
        if net is not None:
            net = v.string(net, f"{path}.net")
        anchor_id = entry.get("anchor_id")
        if anchor_id is not None:
            anchor_id = v.string(anchor_id, f"{path}.anchor_id")
        if None not in (identity, role, content, kind, current, bbox_source,
                        capability, constraints):
            result.append(Annotation(identity, role, content, kind, field_name, current,
                                     bbox_source, owner, net, anchor_id, capability,
                                     constraints))
    return tuple(result)


def _text_style(v: _Validator, value: Any, path: str) -> Optional[TextStyle]:
    entry = v.obj(value, path,
                  ["bbox", "anchor", "anchor_source", "align", "rotation_deg",
                   "rotation_source", "font_size", "font_source"], [])
    if entry is None:
        return None
    bbox = v.bbox(entry.get("bbox"), f"{path}.bbox")
    anchor = None
    raw_anchor = entry.get("anchor")
    if raw_anchor is not None:
        anchor = v.point(raw_anchor, f"{path}.anchor")
    anchor_source = v.enum(entry.get("anchor_source"), f"{path}.anchor_source",
                           ("measured", "declared", "derived", "unknown"))
    align = v.enum(entry.get("align"), f"{path}.align",
                   ("left", "center", "right", "unknown"))
    rotation = None
    raw_rotation = entry.get("rotation_deg")
    if raw_rotation is not None:
        rotation = v.number(raw_rotation, f"{path}.rotation_deg")
    rotation_source = v.enum(entry.get("rotation_source"), f"{path}.rotation_source",
                             ("declared", "derived", "unknown"))
    font_size = None
    raw_font = entry.get("font_size")
    if raw_font is not None:
        font_size = v.number(raw_font, f"{path}.font_size", positive=True)
    font_source = v.enum(entry.get("font_source"), f"{path}.font_source",
                         ("declared", "derived", "unknown"))
    if bbox is None or anchor_source is None or align is None or rotation_source is None \
            or font_source is None:
        return None
    return TextStyle(bbox, anchor, anchor_source, align, rotation, rotation_source,
                     font_size, font_source)


def _capability(v: _Validator, value: Any, path: str) -> Optional[Capability]:
    entry = v.obj(value, path,
                  ["translate", "rotate", "resize", "content_change", "net_change",
                   "source"], [])
    if entry is None:
        return None
    translate = v.enum(entry.get("translate"), f"{path}.translate", CAPABILITIES)
    rotate = v.enum(entry.get("rotate"), f"{path}.rotate", ("fixed",))
    resize = v.enum(entry.get("resize"), f"{path}.resize", ("forbidden",))
    content_change = v.enum(entry.get("content_change"), f"{path}.content_change",
                            ("forbidden",))
    net_change = v.enum(entry.get("net_change"), f"{path}.net_change", ("forbidden",))
    source = v.string(entry.get("source"), f"{path}.source")
    if None in (translate, rotate, resize, content_change, net_change, source):
        return None
    return Capability(translate, rotate, resize, content_change, net_change, source)


def _ann_constraints(v: _Validator, value: Any, path: str) -> Optional[AnnConstraints]:
    entry = v.obj(value, path,
                  ["zone_id", "keep_in_zone", "allowed_directions", "max_displacement",
                   "grid", "owner_max_distance", "priority"], [])
    if entry is None:
        return None
    zone_id = None
    if entry.get("zone_id") is not None:
        zone_id = v.string(entry.get("zone_id"), f"{path}.zone_id")
    keep = v.boolean(entry.get("keep_in_zone"), f"{path}.keep_in_zone")
    directions = v.string_list(entry.get("allowed_directions"), f"{path}.allowed_directions")
    if directions is not None:
        for direction in directions:
            if direction not in DIRECTIONS:
                v.fail(f"{path}.allowed_directions: unknown direction {direction!r}")
        if len(set(directions)) != len(directions):
            v.fail(f"{path}.allowed_directions: duplicate direction")
    max_disp = v.number(entry.get("max_displacement"), f"{path}.max_displacement",
                        nonnegative=True)
    grid = v.number(entry.get("grid"), f"{path}.grid", nonnegative=True)
    owner_max = v.number(entry.get("owner_max_distance"), f"{path}.owner_max_distance",
                         positive=True)
    priority = v.integer(entry.get("priority"), f"{path}.priority")
    if None in (keep, directions, max_disp, grid, owner_max, priority):
        return None
    return AnnConstraints(zone_id, keep, directions, max_disp, grid, owner_max, priority)


def _constraints(v: _Validator, value: Any) -> Optional[Constraints]:
    required = ["grid", "min_text_text_gap", "min_text_symbol_gap", "min_text_wire_gap",
                "min_text_wire_clearance", "self_text_contact_tolerance",
                "label_own_wire_edge_tolerance", "max_candidates_per_annotation",
                "max_total_candidates", "max_search_states", "max_local_search_steps",
                "max_displacement", "owner_max_distance", "forbid_font_change",
                "forbid_content_change", "forbid_net_change", "forbid_component_move",
                "freeze_ids", "scope"]
    optional = ["scope_cluster_ids"]
    entry = v.obj(value, "constraints", required, optional)
    if entry is None:
        return None
    numbers = {}
    for name in required[:13]:
        numbers[name] = v.number(entry.get(name), f"constraints.{name}", nonnegative=True)
    positive = ("owner_max_distance",)
    for name in positive:
        if numbers.get(name) == 0:
            v.fail(f"constraints.{name}: positive number required")
    for name in ("max_candidates_per_annotation", "max_total_candidates",
                 "max_search_states"):
        raw = entry.get(name)
        if type(raw) is not int or raw <= 0:
            v.fail(f"constraints.{name}: positive integer required")
    local_steps = entry.get("max_local_search_steps")
    if type(local_steps) is not int or local_steps < 0:
        v.fail("constraints.max_local_search_steps: nonnegative integer required")
    flags = {}
    for name in ("forbid_font_change", "forbid_content_change", "forbid_net_change",
                 "forbid_component_move"):
        flags[name] = v.boolean(entry.get(name), f"constraints.{name}")
    freeze = v.string_list(entry.get("freeze_ids"), "constraints.freeze_ids")
    scope = v.enum(entry.get("scope"), "constraints.scope", ("all", "cluster"))
    scoped = v.string_list(entry.get("scope_cluster_ids", []),
                           "constraints.scope_cluster_ids")
    if any(number is None for number in numbers.values()) or \
            any(flag is None for flag in flags.values()) or \
            freeze is None or scope is None or scoped is None:
        return None
    return Constraints(
        grid=numbers["grid"],
        min_text_text_gap=numbers["min_text_text_gap"],
        min_text_symbol_gap=numbers["min_text_symbol_gap"],
        min_text_wire_gap=numbers["min_text_wire_gap"],
        min_text_wire_clearance=numbers["min_text_wire_clearance"],
        self_text_contact_tolerance=numbers["self_text_contact_tolerance"],
        label_own_wire_edge_tolerance=numbers["label_own_wire_edge_tolerance"],
        max_candidates_per_annotation=int(entry["max_candidates_per_annotation"]),
        max_total_candidates=int(entry["max_total_candidates"]),
        max_search_states=int(entry["max_search_states"]),
        max_local_search_steps=int(entry["max_local_search_steps"]),
        max_displacement=numbers["max_displacement"],
        owner_max_distance=numbers["owner_max_distance"],
        forbid_font_change=flags["forbid_font_change"],
        forbid_content_change=flags["forbid_content_change"],
        forbid_net_change=flags["forbid_net_change"],
        forbid_component_move=flags["forbid_component_move"],
        freeze_ids=freeze,
        scope=scope,
        scope_cluster_ids=scoped,
    )


def _host(v: _Validator, value: Any) -> Optional[Host]:
    entry = v.obj(value, "host", ["capabilities", "capability_source", "execution"], [])
    if entry is None:
        return None
    raw_capabilities = entry.get("capabilities")
    capabilities: Dict[str, str] = {}
    if not isinstance(raw_capabilities, dict):
        v.fail("host.capabilities: object required")
    else:
        allowed = set(HOST_CAPABILITY_KEYS)
        for key, raw in raw_capabilities.items():
            if key not in allowed:
                v.fail(f"host.capabilities: unknown capability {key!r}")
                continue
            value_enum = v.enum(raw, f"host.capabilities.{key}", CAPABILITIES)
            if value_enum is not None:
                capabilities[key] = value_enum
    source = v.string(entry.get("capability_source"), "host.capability_source")
    execution = v.enum(entry.get("execution"), "host.execution",
                       ("not_executed", "host_executed_unverified", "host_verified"))
    if source is None or execution is None:
        return None
    return Host(capabilities, source, execution)


def _uncertainty(v: _Validator, value: Any) -> Optional[Uncertainty]:
    entry = v.obj(value, "uncertainty",
                  ["bbox_measured", "font_metrics_known", "symbol_outline_approximate"],
                  ["notes"])
    if entry is None:
        return None
    measured = v.boolean(entry.get("bbox_measured"), "uncertainty.bbox_measured")
    fonts = v.boolean(entry.get("font_metrics_known"), "uncertainty.font_metrics_known")
    outline = v.boolean(entry.get("symbol_outline_approximate"),
                        "uncertainty.symbol_outline_approximate")
    notes = v.string_list(entry.get("notes", []), "uncertainty.notes")
    if None in (measured, fonts, outline, notes):
        return None
    return Uncertainty(measured, fonts, outline, notes)


def _checker_context(v: _Validator, value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        v.fail("checker_context: object required")
        return {}
    unknown = sorted(set(value) - CHECKER_CONTEXT_KEYS)
    if unknown:
        v.fail(f"checker_context: unknown key(s) {', '.join(unknown)}")
    return dict(value)
