"""Frozen data model for the offline annotation-layout planner.

Every object in this module is immutable except the explicit counters used to
measure search work.  No module keeps global mutable state; callers thread the
counters through explicitly.  JSON dictionaries in plans are assembled by
``to_dict`` helpers so key ordering and numeric types stay deterministic.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_ID = "annotation-layout/v1"
TOOL_NAME = "annotation_layout"
TOOL_VERSION = "0.1.0"

# Overall plan statuses (contract section 7).
STATUS_PLANNED_CLEAR = "planned_clear"
STATUS_PARTIAL = "partial"
STATUS_BLOCKED = "blocked"
STATUS_NEEDS_GEOMETRY = "needs_geometry"
STATUS_INPUT_INVALID = "input_invalid"

# Per-annotation / overall failure reasons (contract 5.5).
REASON_NO_CANDIDATES = "no_candidates"
REASON_ALL_REJECTED = "all_candidates_rejected"
REASON_BUDGET = "budget_exhausted"
REASON_GEOMETRY_UNCERTAIN = "geometry_uncertain"
REASON_HOST_UNSUPPORTED = "host_capability_unsupported"
REASON_NET_ANCHOR = "net_label_anchor_not_separable"
REASON_OWNER_UNKNOWN = "annotation_owner_unknown"
REASON_FROZEN = "frozen_by_scope"

ROLES = (
    "designator",
    "value",
    "free_text",
    "purpose_text",
    "net_label",
    "wire_name",
)
FIXED_ROLES = ("zone_title", "pin_name", "pin_number", "symbol_text", "netflag",
               "title_block", "border", "unknown")
ALL_ROLES = ROLES + FIXED_ROLES

CAPABILITIES = ("supported", "unverified", "unsupported")
HOST_CAPABILITY_KEYS = (
    "attribute_translate",
    "free_text_translate",
    "net_label_detach",
    "attribute_rotate",
    "attribute_align",
    "free_text_align",
)
DIRECTIONS = ("right", "left", "up", "down")

SEVERITY_HARD = "hard"
SEVERITY_SOFT = "soft"
SEVERITY_INFO = "info"

SCOPE_MOVABLE = "movable"
SCOPE_FIXED = "fixed"
SCOPE_MIXED = "mixed"


class InputError(ValueError):
    """Raised when the input document violates the v1 contract."""

    def __init__(self, reasons: Sequence[str]):
        self.reasons: Tuple[str, ...] = tuple(str(reason) for reason in reasons)
        super().__init__("; ".join(self.reasons))


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in schematic raw units (y-up)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def translated(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def inflated(self, amount: float) -> "Rect":
        return Rect(self.x0 - amount, self.y0 - amount, self.x1 + amount, self.y1 + amount)

    def intersects(self, other: "Rect") -> bool:
        return (min(self.x1, other.x1) > max(self.x0, other.x0)
                and min(self.y1, other.y1) > max(self.y0, other.y0))

    def contains_rect(self, other: "Rect") -> bool:
        return (self.x0 <= other.x0 and self.y0 <= other.y0
                and self.x1 >= other.x1 and self.y1 >= other.y1)

    def contains_point(self, point: Tuple[float, float]) -> bool:
        return self.x0 <= point[0] <= self.x1 and self.y0 <= point[1] <= self.y1

    def overlap_extent(self, other: "Rect") -> Tuple[float, float]:
        return (min(self.x1, other.x1) - max(self.x0, other.x0),
                min(self.y1, other.y1) - max(self.y0, other.y0))

    def as_list(self) -> List[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    def as_dict(self) -> Dict[str, float]:
        return {"minX": self.x0, "minY": self.y0, "maxX": self.x1, "maxY": self.y1}


Point = Tuple[float, float]


@dataclass(frozen=True)
class Project:
    name: str
    page_id: str
    page_name: str
    snapshot_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "page_id": self.page_id,
            "page_name": self.page_name,
            "snapshot_sha256": self.snapshot_sha256,
        }


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class Source:
    kind: str
    adapter: str
    source_commit: str
    created: str
    notes: str
    files: Tuple[SourceFile, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "adapter": self.adapter,
            "source_commit": self.source_commit,
            "created": self.created,
            "notes": self.notes,
            "files": [{"path": item.path, "sha256": item.sha256} for item in self.files],
        }


@dataclass(frozen=True)
class Units:
    name: str
    raw_per_mm: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "raw_per_mm": self.raw_per_mm,
                "description": self.description}


@dataclass(frozen=True)
class CoordinateSystem:
    name: str
    y_axis: str
    svg_y_axis: str
    transform: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "y_axis": self.y_axis,
                "svg_y_axis": self.svg_y_axis, "transform": self.transform}


@dataclass(frozen=True)
class Keepout:
    id: str
    bbox: Rect
    hard: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "bbox": self.bbox.as_list(), "hard": self.hard,
                "reason": self.reason}


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    bbox: Rect
    hard: bool
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "bbox": self.bbox.as_list(),
                "hard": self.hard, "source": self.source}


@dataclass(frozen=True)
class Page:
    bbox: Rect
    usable_bbox: Rect
    title_block: Optional[Rect]
    keepouts: Tuple[Keepout, ...]
    zones: Tuple[Zone, ...]


@dataclass(frozen=True)
class Component:
    id: str
    bbox: Rect
    designator: Optional[str]
    zone_id: Optional[str]

    def to_checker(self) -> Dict[str, Any]:
        return {"id": self.id, "bbox": self.bbox.as_list()}


@dataclass(frozen=True)
class Wire:
    id: str
    points: Tuple[Point, ...]
    net: Optional[str]
    primitive_id: str

    def segments(self) -> Iterable[Tuple[Point, Point]]:
        return zip(self.points, self.points[1:])

    def to_checker(self) -> Dict[str, Any]:
        item: Dict[str, Any] = {"id": self.id, "points": [list(p) for p in self.points]}
        if self.net:
            item["net"] = self.net
        if self.primitive_id:
            item["primitive_id"] = self.primitive_id
        return item


@dataclass(frozen=True)
class TextStyle:
    bbox: Rect
    anchor: Optional[Point]
    anchor_source: str
    align: str
    rotation_deg: Optional[float]
    rotation_source: str
    font_size: Optional[float]
    font_source: str

    def pose(self) -> Dict[str, Any]:
        return {
            "bbox": self.bbox.as_list(),
            "anchor": list(self.anchor) if self.anchor else None,
            "anchor_source": self.anchor_source,
            "align": self.align,
            "rotation_deg": self.rotation_deg,
            "rotation_source": self.rotation_source,
            "font_size": self.font_size,
            "font_source": self.font_source,
        }


@dataclass(frozen=True)
class OwnerRef:
    kind: str
    id: str
    requirement: str

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "requirement": self.requirement}


@dataclass(frozen=True)
class Capability:
    translate: str
    rotate: str
    resize: str
    content_change: str
    net_change: str
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "translate": self.translate,
            "rotate": self.rotate,
            "resize": self.resize,
            "content_change": self.content_change,
            "net_change": self.net_change,
            "source": self.source,
        }


@dataclass(frozen=True)
class AnnConstraints:
    zone_id: Optional[str]
    keep_in_zone: bool
    allowed_directions: Tuple[str, ...]
    max_displacement: float
    grid: float
    owner_max_distance: float
    priority: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "keep_in_zone": self.keep_in_zone,
            "allowed_directions": list(self.allowed_directions),
            "max_displacement": self.max_displacement,
            "grid": self.grid,
            "owner_max_distance": self.owner_max_distance,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class Annotation:
    id: str
    role: str
    content: str
    kind: str
    field: Optional[str]
    current: TextStyle
    bbox_source: str
    owner: Optional[OwnerRef]
    net: Optional[str]
    anchor_id: Optional[str]
    capability: Capability
    constraints: AnnConstraints

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    @property
    def movable(self) -> bool:
        return self.capability.translate != "unsupported"

    def with_bbox(self, bbox: Rect) -> "Annotation":
        text = TextStyle(
            bbox=bbox,
            anchor=self.current.anchor,
            anchor_source=self.current.anchor_source,
            align=self.current.align,
            rotation_deg=self.current.rotation_deg,
            rotation_source=self.current.rotation_source,
            font_size=self.current.font_size,
            font_source=self.current.font_source,
        )
        return Annotation(
            id=self.id, role=self.role, content=self.content, kind=self.kind,
            field=self.field, current=text, bbox_source=self.bbox_source,
            owner=self.owner, net=self.net, anchor_id=self.anchor_id,
            capability=self.capability, constraints=self.constraints)

    def to_checker(self) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "id": self.id,
            "bbox": self.current.bbox.as_list(),
            "kind": self.kind,
            "content": self.content,
            "measurement": "bbox" if self.bbox_source == "measured_svg" else self.bbox_source,
        }
        if self.field:
            item["field"] = self.field
        if self.owner and self.owner.kind == "component":
            item["owner"] = self.owner.id
        if self.net:
            item["net"] = self.net
        if self.anchor_id:
            item["anchor_id"] = self.anchor_id
            item["anchored"] = True
        return item


@dataclass(frozen=True)
class FixedText:
    id: str
    bbox: Rect
    kind: str
    content: str
    owner_id: Optional[str]
    owner_kind: Optional[str]
    net: Optional[str]
    anchor_id: Optional[str]
    anchored: Optional[bool]
    measurement: str
    field: Optional[str]

    def to_checker(self) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "id": self.id,
            "bbox": self.bbox.as_list(),
            "kind": self.kind,
            "content": self.content,
            "measurement": self.measurement,
        }
        if self.owner_id:
            item["owner"] = self.owner_id
        if self.field:
            item["field"] = self.field
        if self.net:
            item["net"] = self.net
        if self.anchor_id:
            item["anchor_id"] = self.anchor_id
            item["anchored"] = bool(self.anchored)
        return item


@dataclass(frozen=True)
class Constraints:
    grid: float
    min_text_text_gap: float
    min_text_symbol_gap: float
    min_text_wire_gap: float
    min_text_wire_clearance: float
    self_text_contact_tolerance: float
    label_own_wire_edge_tolerance: float
    max_candidates_per_annotation: int
    max_total_candidates: int
    max_search_states: int
    max_local_search_steps: int
    max_displacement: float
    owner_max_distance: float
    forbid_font_change: bool
    forbid_content_change: bool
    forbid_net_change: bool
    forbid_component_move: bool
    freeze_ids: Tuple[str, ...]
    scope: str
    scope_cluster_ids: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grid": self.grid,
            "min_text_text_gap": self.min_text_text_gap,
            "min_text_symbol_gap": self.min_text_symbol_gap,
            "min_text_wire_gap": self.min_text_wire_gap,
            "min_text_wire_clearance": self.min_text_wire_clearance,
            "self_text_contact_tolerance": self.self_text_contact_tolerance,
            "label_own_wire_edge_tolerance": self.label_own_wire_edge_tolerance,
            "max_candidates_per_annotation": self.max_candidates_per_annotation,
            "max_total_candidates": self.max_total_candidates,
            "max_search_states": self.max_search_states,
            "max_local_search_steps": self.max_local_search_steps,
            "max_displacement": self.max_displacement,
            "owner_max_distance": self.owner_max_distance,
            "forbid_font_change": self.forbid_font_change,
            "forbid_content_change": self.forbid_content_change,
            "forbid_net_change": self.forbid_net_change,
            "forbid_component_move": self.forbid_component_move,
            "freeze_ids": list(self.freeze_ids),
            "scope": self.scope,
            "scope_cluster_ids": list(self.scope_cluster_ids),
        }


@dataclass(frozen=True)
class Host:
    capabilities: Mapping[str, str]
    capability_source: str
    execution: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capabilities": dict(sorted(self.capabilities.items())),
            "capability_source": self.capability_source,
            "execution": self.execution,
        }


@dataclass(frozen=True)
class Uncertainty:
    bbox_measured: bool
    font_metrics_known: bool
    symbol_outline_approximate: bool
    notes: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox_measured": self.bbox_measured,
            "font_metrics_known": self.font_metrics_known,
            "symbol_outline_approximate": self.symbol_outline_approximate,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class Input:
    path: str
    canonical_sha256: str
    project: Project
    source: Source
    units: Units
    coordinate_system: CoordinateSystem
    page: Page
    components: Tuple[Component, ...]
    wires: Tuple[Wire, ...]
    fixed_texts: Tuple[FixedText, ...]
    annotations: Tuple[Annotation, ...]
    constraints: Constraints
    host: Host
    uncertainty: Uncertainty
    checker_context: Mapping[str, Any]

    def annotation(self, annotation_id: str) -> Annotation:
        for item in self.annotations:
            if item.id == annotation_id:
                return item
        raise KeyError(annotation_id)

    def component(self, component_id: str) -> Optional[Component]:
        for item in self.components:
            if item.id == component_id:
                return item
        return None

    def zone(self, zone_id: Optional[str]) -> Optional[Zone]:
        if not zone_id:
            return None
        for item in self.page.zones:
            if item.id == zone_id:
                return item
        return None

    def zone_of_component(self, component_id: str) -> Optional[str]:
        item = self.component(component_id)
        return item.zone_id if item else None

    def all_texts(self) -> Tuple[Any, ...]:
        return self.fixed_texts + self.annotations


@dataclass(frozen=True)
class Candidate:
    annotation_id: str
    dx: float
    dy: float
    bbox: Rect
    rank: int
    rationale: Tuple[str, ...]
    capability: str

    @property
    def displacement(self) -> float:
        return (self.dx * self.dx + self.dy * self.dy) ** 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dx": self.dx,
            "dy": self.dy,
            "bbox": self.bbox.as_list(),
            "rank": self.rank,
            "displacement": round(self.displacement, 6),
            "rationale": list(self.rationale),
            "capability": self.capability,
        }


@dataclass
class Counters:
    """Mutable work counters; never used to make a decision."""

    collision_checks: int = 0
    candidate_evaluations: int = 0
    states: int = 0
    iterations: int = 0
    local_steps: int = 0
    pair_cache_hits: int = 0

    def bump(self, name: str, amount: int = 1) -> None:
        setattr(self, name, getattr(self, name) + amount)

    def snapshot(self) -> Dict[str, int]:
        return {
            "collision_checks": self.collision_checks,
            "candidate_evaluations": self.candidate_evaluations,
            "states": self.states,
            "iterations": self.iterations,
            "local_steps": self.local_steps,
            "pair_cache_hits": self.pair_cache_hits,
        }


@dataclass(frozen=True)
class Violation:
    code: str
    severity: str
    objects: Tuple[str, ...]
    detail: Mapping[str, Any] = field(default_factory=dict)
    scope: str = SCOPE_MOVABLE
    annotation_ids: Tuple[str, ...] = ()

    @property
    def is_hard(self) -> bool:
        return self.severity == SEVERITY_HARD

    def key(self) -> Tuple[Any, ...]:
        return (self.code, self.objects)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "objects": list(self.objects),
            "scope": self.scope,
            "annotation_ids": list(self.annotation_ids),
            "detail": _jsonable(self.detail),
        }


@dataclass
class SearchStats:
    candidates_generated: int = 0
    candidates_possible: int = 0
    candidates_truncated: int = 0
    collision_checks: int = 0
    states: int = 0
    iterations: int = 0
    local_steps: int = 0
    clusters: int = 0
    cluster_sizes: List[int] = field(default_factory=list)
    budget_exhausted: bool = False
    budget_kind: Optional[str] = None
    freeze_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidates_generated": self.candidates_generated,
            "candidates_possible": self.candidates_possible,
            "candidates_truncated": self.candidates_truncated,
            "collision_checks": self.collision_checks,
            "states": self.states,
            "iterations": self.iterations,
            "local_steps": self.local_steps,
            "clusters": self.clusters,
            "cluster_sizes": list(self.cluster_sizes),
            "budget_exhausted": self.budget_exhausted,
            "budget_kind": self.budget_kind,
            "freeze_count": self.freeze_count,
        }


@dataclass
class SearchResult:
    status: str
    assignment: Dict[str, Candidate]
    violations: Tuple[Violation, ...]
    unknown: Tuple[Violation, ...]
    reasons: Dict[str, Any]
    stats: SearchStats
    noop: bool
    scope_ids: Tuple[str, ...] = ()

    @property
    def hard(self) -> Tuple[Violation, ...]:
        return tuple(item for item in self.violations if item.is_hard)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Rect):
        return value.as_list()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def canonical_json(value: Any) -> str:
    """Canonical JSON used for input/plan hashing (stable across platforms)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
