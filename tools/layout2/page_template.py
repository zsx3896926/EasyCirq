"""Read, validate and query ``easycirq-page-template/v1`` page templates.

Offline only: this module reads the measured page template JSON and answers
geometry questions (usable regions, title-block keep-out, region lookup).  It
never imports an EDA adapter and never writes to a project.

Coordinate system
-----------------
Templates use the schematic raw vector space reported by
``easycirq sch sheet-geometry``: **y grows upward**, so a title block whose
``minY`` sits at the bottom inner border is a *bottom* title block, and the
page origin ``(0, 0)`` is the lower-left corner.  Do not re-interpret a
template with a y-down convention.

Usable area and regions
-----------------------
The usable page area is the page inset by ``page.margin``.  A measured
``inner_border`` rect may be given instead; it must agree with the margin.
A title block occupies a keep-out rectangle in one bottom corner.  The
remaining L-shaped usable area is split into two non-overlapping rectangles:

* ``bottom-right`` title block -> ``left`` (full-height left column) and
  ``top-right`` (above the title block);
* ``bottom-left`` title block  -> ``right`` (full-height right column) and
  ``top-left`` (above the title block).

The corner is derived from the measured ``title_block.rect`` (or read from the
``title_block.corner`` field and cross-checked); no corner is hard-coded, so a
customer template with a bottom-left title block works by changing data only.
Top title blocks are not supported and are rejected with a clear error.

Boundary semantics
------------------
Rectangles that only *touch* (zero-area overlap) do not intersect.  Regions
therefore touch each other and the keep-out along shared edges, which is what
the hard rules require (no positive area overlap).

Public API
----------
``load_template(path)``, ``PageTemplate``, ``Rect``, ``Region``,
``build_template_document(...)``, ``derive_corner(...)``, ``derive_regions(...)``
and ``TemplateError``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

SCHEMA = "easycirq-page-template/v1"

#: Supported title-block corners (bottom edge only, see module docstring).
SUPPORTED_CORNERS = ("bottom-left", "bottom-right")

_EPS = 1e-9

_RECT_KEYS = ("minX", "minY", "maxX", "maxY")
_TOP_KEYS = frozenset(
    {"schema", "page", "inner_border", "title_block", "regions",
     "provenance", "measured_at", "notes"}
)
_PAGE_KEYS = frozenset({"width", "height", "margin"})
_TITLE_BLOCK_KEYS = frozenset({"rect", "corner", "visible", "provenance", "source"})
_REGION_KEYS = frozenset({"name", "rect"})


class TemplateError(ValueError):
    """A page template is missing required data or is geometrically invalid."""


class Rect(NamedTuple):
    """Axis-aligned rectangle in template coordinates (y-up)."""

    minX: float
    minY: float
    maxX: float
    maxY: float

    @property
    def width(self) -> float:
        return self.maxX - self.minX

    @property
    def height(self) -> float:
        return self.maxY - self.minY

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.minX + self.maxX) / 2.0, (self.minY + self.maxY) / 2.0)

    def to_dict(self) -> Dict[str, float]:
        return {
            "minX": _json_number(self.minX),
            "minY": _json_number(self.minY),
            "maxX": _json_number(self.maxX),
            "maxY": _json_number(self.maxY),
        }

    def contains(self, other: "Rect", tolerance: float = 0.0) -> bool:
        """True when ``other`` lies inside this rect, allowing ``tolerance`` slack."""
        tol = abs(tolerance)
        return (
            other.minX >= self.minX - tol
            and other.minY >= self.minY - tol
            and other.maxX <= self.maxX + tol
            and other.maxY <= self.maxY + tol
        )

    def intersects(self, other: "Rect") -> bool:
        """True only for a positive-area overlap; edge touching is not a hit."""
        overlap_w = min(self.maxX, other.maxX) - max(self.minX, other.minX)
        overlap_h = min(self.maxY, other.maxY) - max(self.minY, other.minY)
        return overlap_w > _EPS and overlap_h > _EPS

    def expanded(self, distance: float) -> "Rect":
        d = abs(distance)
        return Rect(self.minX - d, self.minY - d, self.maxX + d, self.maxY + d)

    def clipped(self, bounds: "Rect") -> "Rect":
        """Intersection with ``bounds`` (may be empty for disjoint rects)."""
        return Rect(
            max(self.minX, bounds.minX),
            max(self.minY, bounds.minY),
            min(self.maxX, bounds.maxX),
            min(self.maxY, bounds.maxY),
        )


class Region(NamedTuple):
    """A named usable region on a page."""

    name: str
    rect: Rect


# ---------------------------------------------------------------------------
# small validation helpers
# ---------------------------------------------------------------------------


def _prefix(source: Optional[str]) -> str:
    return "%s: " % source if source else ""


def _fail(message: str, source: Optional[str] = None) -> "TemplateError":
    raise TemplateError(_prefix(source) + message)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _json_number(value: float) -> Union[int, float]:
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def _parse_number(
    value: Any,
    field: str,
    source: Optional[str],
    *,
    minimum: Optional[float] = None,
    strict_minimum: bool = False,
) -> float:
    if not _is_number(value):
        _fail("%s: expected a finite number, got %r" % (field, value), source)
    number = float(value)
    if minimum is not None:
        if strict_minimum and number <= minimum:
            _fail(
                "%s: must be greater than %s, got %s"
                % (field, _json_number(minimum), _json_number(number)),
                source,
            )
        if not strict_minimum and number < minimum:
            _fail(
                "%s: must be >= %s, got %s"
                % (field, _json_number(minimum), _json_number(number)),
                source,
            )
    return value


def _reject_unknown(
    mapping: Mapping, allowed: Iterable[str], field: str, source: Optional[str]
) -> None:
    allowed_set = set(allowed)
    unknown = sorted(set(mapping.keys()) - allowed_set)
    if unknown:
        _fail(
            "%s: unknown field(s) %s; allowed: %s"
            % (field, ", ".join(repr(item) for item in unknown), ", ".join(sorted(allowed_set))),
            source,
        )


def _require(mapping: Mapping, key: str, field: str, source: Optional[str]) -> Any:
    if key not in mapping:
        _fail("%s: missing required field %r" % (field, key), source)
    return mapping[key]


def _require_mapping(value: Any, field: str, source: Optional[str]) -> Mapping:
    if not isinstance(value, Mapping):
        _fail("%s: expected an object, got %r" % (field, type(value).__name__), source)
    return value


def _parse_rect(value: Any, field: str, source: Optional[str]) -> Rect:
    """Strictly parse ``{minX, minY, maxX, maxY}`` (JSON schema form)."""
    if isinstance(value, Rect):
        rect = value
    else:
        mapping = _require_mapping(value, field, source)
        _reject_unknown(mapping, _RECT_KEYS, field, source)
        numbers = []
        for key in _RECT_KEYS:
            numbers.append(_parse_number(_require(mapping, key, field, source), "%s.%s" % (field, key), source))
        rect = Rect(*numbers)
    if rect.width <= _EPS or rect.height <= _EPS:
        _fail(
            "%s: rect must have positive width and height, got %s"
            % (field, rect.to_dict()),
            source,
        )
    return rect


def _parse_notes(value: Any, source: Optional[str]) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        _fail("notes: expected a list of strings", source)
    notes = []
    for index, note in enumerate(value):
        if not isinstance(note, str):
            _fail("notes[%d]: expected a string, got %r" % (index, type(note).__name__), source)
        notes.append(note)
    return tuple(notes)


def _parse_provenance(value: Any, source: Optional[str]) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            _fail("provenance: must not be empty", source)
        return value
    if isinstance(value, Mapping):
        return dict(value)
    _fail("provenance: expected a string or an object", source)


def _rect_close(left: Rect, right: Rect, tolerance: float = 1e-6) -> bool:
    return (
        abs(left.minX - right.minX) <= tolerance
        and abs(left.minY - right.minY) <= tolerance
        and abs(left.maxX - right.maxX) <= tolerance
        and abs(left.maxY - right.maxY) <= tolerance
    )


def _inset(page: Rect, margin: float) -> Rect:
    return Rect(page.minX + margin, page.minY + margin, page.maxX - margin, page.maxY - margin)


# ---------------------------------------------------------------------------
# corner and region derivation
# ---------------------------------------------------------------------------


def derive_corner(page: Rect, title_block: Rect) -> str:
    """Derive the title-block corner from geometry (y-up coordinates)."""
    page_x, page_y = page.center
    block_x, block_y = title_block.center
    horizontal = "left" if block_x < page_x else "right"
    vertical = "bottom" if block_y < page_y else "top"
    return "%s-%s" % (vertical, horizontal)


def derive_regions(
    usable_area: Rect,
    title_block: Rect,
    corner: str,
) -> Tuple[Region, ...]:
    """Split the usable area (minus the title block) into two named regions.

    ``corner`` must be ``bottom-left`` or ``bottom-right`` and the title block
    must be anchored to that bottom inner edge; otherwise the complement is
    not an L-shape that two rectangles can cover, and a clear error is raised.
    """
    normalized = _normalize_corner(corner)
    if normalized == "bottom-right":
        if title_block.maxX < usable_area.maxX - _EPS:
            _fail(
                "title_block.rect %s must touch the right inner border (maxX=%s) "
                "to derive a two-region split"
                % (title_block.to_dict(), _json_number(usable_area.maxX))
            )
        if title_block.minY > usable_area.minY + _EPS:
            _fail(
                "title_block.rect %s must touch the bottom inner border (minY=%s) "
                "to derive a two-region split"
                % (title_block.to_dict(), _json_number(usable_area.minY))
            )
        keepout = Rect(
            max(title_block.minX, usable_area.minX),
            usable_area.minY,
            usable_area.maxX,
            min(title_block.maxY, usable_area.maxY),
        )
        regions = (
            Region("left", Rect(usable_area.minX, usable_area.minY, keepout.minX, usable_area.maxY)),
            Region("top-right", Rect(keepout.minX, keepout.maxY, usable_area.maxX, usable_area.maxY)),
        )
    elif normalized == "bottom-left":
        if title_block.minX > usable_area.minX + _EPS:
            _fail(
                "title_block.rect %s must touch the left inner border (minX=%s) "
                "to derive a two-region split"
                % (title_block.to_dict(), _json_number(usable_area.minX))
            )
        if title_block.minY > usable_area.minY + _EPS:
            _fail(
                "title_block.rect %s must touch the bottom inner border (minY=%s) "
                "to derive a two-region split"
                % (title_block.to_dict(), _json_number(usable_area.minY))
            )
        keepout = Rect(
            usable_area.minX,
            usable_area.minY,
            min(title_block.maxX, usable_area.maxX),
            min(title_block.maxY, usable_area.maxY),
        )
        regions = (
            Region("right", Rect(keepout.maxX, usable_area.minY, usable_area.maxX, usable_area.maxY)),
            Region("top-left", Rect(usable_area.minX, keepout.maxY, keepout.maxX, usable_area.maxY)),
        )
    else:  # pragma: no cover - _normalize_corner already raises
        raise AssertionError("unreachable")

    if keepout.width <= _EPS or keepout.height <= _EPS:
        _fail(
            "title_block.rect %s leaves no usable keep-out inside the usable page area %s"
            % (title_block.to_dict(), usable_area.to_dict())
        )
    if keepout.maxY >= usable_area.maxY - _EPS:
        _fail(
            "title_block.rect %s covers the full usable page height; "
            "cannot derive a top region" % title_block.to_dict()
        )
    for region in regions:
        if region.rect.width <= _EPS or region.rect.height <= _EPS:
            _fail(
                "derived region %r is empty (%s); check page margin and title block rect"
                % (region.name, region.rect.to_dict())
            )
    return regions


def _normalize_corner(corner: Any) -> str:
    if not isinstance(corner, str) or not corner.strip():
        _fail("title_block.corner: expected a non-empty string")
    normalized = corner.strip().lower().replace("_", "-")
    if normalized not in SUPPORTED_CORNERS:
        _fail(
            "unsupported title block corner %r; supported: %s"
            % (corner, ", ".join(SUPPORTED_CORNERS))
        )
    return normalized


# ---------------------------------------------------------------------------
# template object
# ---------------------------------------------------------------------------


class PageTemplate:
    """A validated ``easycirq-page-template/v1`` document.

    Build one with :func:`load_template` (file) or
    :meth:`PageTemplate.from_dict` (already-parsed JSON).
    """

    def __init__(self, data: Any, source: Optional[str] = None) -> None:
        self._source = source
        document = _require_mapping(data, "template", source)
        _reject_unknown(document, _TOP_KEYS, "template", source)
        for key in ("schema", "page", "title_block"):
            _require(document, key, "template", source)

        schema = document["schema"]
        if schema != SCHEMA:
            _fail(
                "schema: expected %r, got %r" % (SCHEMA, schema),
                source,
            )

        # -- page -----------------------------------------------------------
        page_data = _require_mapping(document["page"], "page", source)
        _reject_unknown(page_data, _PAGE_KEYS, "page", source)
        width = _parse_number(
            _require(page_data, "width", "page", source), "page.width", source,
            minimum=0, strict_minimum=True,
        )
        height = _parse_number(
            _require(page_data, "height", "page", source), "page.height", source,
            minimum=0, strict_minimum=True,
        )
        margin = _parse_number(
            _require(page_data, "margin", "page", source), "page.margin", source,
            minimum=0,
        )
        page_rect = Rect(0.0, 0.0, width, height)
        if margin * 2 >= min(width, height):
            _fail(
                "page.margin %s is too large for page %sx%s: it leaves no usable area"
                % (_json_number(margin), _json_number(width), _json_number(height)),
                source,
            )
        expected_usable = _inset(page_rect, margin)

        # -- optional inner border (measured usability) ---------------------
        if "inner_border" in document:
            inner_border = _parse_rect(document["inner_border"], "inner_border", source)
            if not page_rect.contains(inner_border):
                _fail(
                    "inner_border %s extends outside the page %s"
                    % (inner_border.to_dict(), page_rect.to_dict()),
                    source,
                )
            if not _rect_close(inner_border, expected_usable):
                _fail(
                    "inner_border %s disagrees with page.margin %s "
                    "(expected %s); fix page.margin or inner_border"
                    % (
                        inner_border.to_dict(),
                        _json_number(margin),
                        expected_usable.to_dict(),
                    ),
                    source,
                )
            usable_area = inner_border
        else:
            usable_area = expected_usable

        # -- title block ----------------------------------------------------
        title_data = _require_mapping(document["title_block"], "title_block", source)
        _reject_unknown(title_data, _TITLE_BLOCK_KEYS, "title_block", source)
        title_rect = _parse_rect(
            _require(title_data, "rect", "title_block", source), "title_block.rect", source
        )
        if not page_rect.contains(title_rect):
            _fail(
                "title_block.rect %s extends outside the page %s"
                % (title_rect.to_dict(), page_rect.to_dict()),
                source,
            )
        if not title_rect.intersects(usable_area):
            _fail(
                "title_block.rect %s does not overlap the usable page area %s"
                % (title_rect.to_dict(), usable_area.to_dict()),
                source,
            )
        visible: Optional[bool] = None
        if "visible" in title_data:
            visible = title_data["visible"]
            if not isinstance(visible, bool):
                _fail("title_block.visible: expected a boolean", source)
        if "provenance" in title_data:
            title_provenance = _parse_provenance(title_data["provenance"], source)
        else:
            title_provenance = None
        if "source" in title_data:
            title_source = title_data["source"]
            if not isinstance(title_source, str) or not title_source.strip():
                _fail("title_block.source: expected a non-empty string", source)
        else:
            title_source = None

        derived_corner = derive_corner(page_rect, title_rect)
        if "corner" in title_data:
            explicit_corner = _normalize_corner(title_data["corner"])
            if explicit_corner != derived_corner:
                _fail(
                    "title_block.corner %r disagrees with the measured rect position "
                    "(geometry derives %r)"
                    % (title_data["corner"], derived_corner),
                    source,
                )
            corner = explicit_corner
        else:
            corner = derived_corner
        if corner not in SUPPORTED_CORNERS:
            _fail(
                "unsupported title block corner %r: only bottom-left and bottom-right "
                "title blocks are supported (rect center %s, page center %s)"
                % (corner, title_rect.center, page_rect.center),
                source,
            )

        computed_regions = derive_regions(usable_area, title_rect, corner)

        # -- regions: manual override when present, validated strictly ------
        if "regions" in document:
            regions = _parse_regions(
                document["regions"], source, usable_area, title_rect
            )
            self._regions_overridden = True
        else:
            regions = computed_regions
            self._regions_overridden = False

        # -- informational fields ------------------------------------------
        measured_at = document.get("measured_at")
        if measured_at is not None and (not isinstance(measured_at, str) or not measured_at.strip()):
            _fail("measured_at: expected a non-empty string", source)
        provenance = _parse_provenance(document.get("provenance"), source)
        notes = _parse_notes(document.get("notes"), source)

        self._document = dict(document)
        self._margin = margin
        self._page_rect = page_rect
        self._usable_area = usable_area
        self._title_block_rect = title_rect
        self._title_block_visible = visible
        self._title_block_provenance = title_provenance
        self._title_block_source = title_source
        self._corner = corner
        self._computed_regions = computed_regions
        self._regions = regions
        self._provenance = provenance
        self._measured_at = measured_at
        self._notes = notes

    # -- construction -------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Any, source: Optional[str] = None) -> "PageTemplate":
        return cls(data, source=source)

    @property
    def source(self) -> Optional[str]:
        return self._source

    # -- basic geometry -----------------------------------------------------

    @property
    def width(self) -> float:
        return self._page_rect.width

    @property
    def height(self) -> float:
        return self._page_rect.height

    @property
    def margin(self) -> float:
        return self._margin

    @property
    def page_rect(self) -> Rect:
        """Full page rectangle ``(0, 0) - (width, height)``."""
        return self._page_rect

    @property
    def usable_area(self) -> Rect:
        """Page area after margins (and measured inner border)."""
        return self._usable_area

    #: Alias kept for callers that talk about the measured inner border.
    @property
    def inner_border(self) -> Rect:
        return self._usable_area

    @property
    def title_block_rect(self) -> Rect:
        return self._title_block_rect

    @property
    def title_block_corner(self) -> str:
        return self._corner

    @property
    def title_block_visible(self) -> Optional[bool]:
        return self._title_block_visible

    @property
    def provenance(self) -> Any:
        return self._provenance

    @property
    def measured_at(self) -> Optional[str]:
        return self._measured_at

    @property
    def notes(self) -> Tuple[str, ...]:
        return self._notes

    @property
    def regions_overridden(self) -> bool:
        """True when the JSON carried a manual ``regions`` override."""
        return self._regions_overridden

    # -- required API -------------------------------------------------------

    def usable_regions(self) -> Tuple[Region, ...]:
        """The page's usable regions (manual override or derived from page+keep-out)."""
        return self._regions

    def computed_regions(self) -> Tuple[Region, ...]:
        """Regions derived from page + title block, ignoring any manual override."""
        return self._computed_regions

    def region(self, name: str) -> Region:
        for region in self._regions:
            if region.name == name:
                return region
        raise KeyError("unknown region %r; template regions: %s" % (name, self.region_names()))

    def region_names(self) -> Tuple[str, ...]:
        return tuple(region.name for region in self._regions)

    def regions_by_name(self) -> Dict[str, Rect]:
        return {region.name: region.rect for region in self._regions}

    def title_block_hit(self, rect: "RectTypes", tolerance: float = 0.0) -> bool:
        """True when ``rect`` overlaps the title-block keep-out.

        Only a positive-area overlap is a hit: a frame that merely touches the
        keep-out edge is allowed (regions share edges with the keep-out).
        ``tolerance`` expands the keep-out, e.g. to demand stroke clearance.
        """
        parsed = _coerce_rect(rect)
        keepout = self._title_block_rect.expanded(tolerance) if tolerance else self._title_block_rect
        return parsed.intersects(keepout)

    def rect_in_page(self, rect: "RectTypes", tolerance: float = 0.0) -> bool:
        """True when ``rect`` is inside the *usable* page area.

        This is the invariant-1 check (page minus margin/inner border, title
        block excluded separately via :meth:`title_block_hit`).  Use
        :meth:`rect_in_raw_page` to include the margins.
        """
        return self._usable_area.contains(_coerce_rect(rect), tolerance)

    def rect_in_raw_page(self, rect: "RectTypes") -> bool:
        """True when ``rect`` is inside the full page rectangle, margins included."""
        return self._page_rect.contains(_coerce_rect(rect))

    def region_of(self, rect: "RectTypes", tolerance: float = 0.0) -> Optional[str]:
        """Name of the region fully containing ``rect``.

        Exact containment is tried first.  If no region contains the rect,
        ``tolerance`` is applied as slack to the region bounds; a rect that is
        only slightly outside one boundary can still be assigned.  A rect that
        spans several regions (or none even with tolerance) returns ``None``.
        """
        if tolerance < 0:
            raise ValueError("tolerance must be >= 0")
        parsed = _coerce_rect(rect)
        matches = [region.name for region in self._regions if region.rect.contains(parsed)]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return None
        if tolerance:
            matches = [
                region.name for region in self._regions if region.rect.contains(parsed, tolerance)
            ]
            if len(matches) == 1:
                return matches[0]
        return None

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Canonical JSON document (computed regions included)."""
        document: Dict[str, Any] = {"schema": SCHEMA}
        if self._measured_at is not None:
            document["measured_at"] = self._measured_at
        if self._provenance is not None:
            document["provenance"] = self._provenance
        document["page"] = {
            "width": _json_number(self.width),
            "height": _json_number(self.height),
            "margin": _json_number(self.margin),
        }
        document["inner_border"] = self._usable_area.to_dict()
        title_block: Dict[str, Any] = {
            "rect": self._title_block_rect.to_dict(),
            "corner": self._corner,
        }
        if self._title_block_visible is not None:
            title_block["visible"] = self._title_block_visible
        if self._title_block_provenance is not None:
            title_block["provenance"] = self._title_block_provenance
        if self._title_block_source is not None:
            title_block["source"] = self._title_block_source
        document["title_block"] = title_block
        document["regions"] = [
            {"name": region.name, "rect": region.rect.to_dict()} for region in self._regions
        ]
        if self._notes:
            document["notes"] = list(self._notes)
        return document

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return "PageTemplate(%sx%s margin=%s corner=%r regions=%s)" % (
            _json_number(self.width),
            _json_number(self.height),
            _json_number(self.margin),
            self._corner,
            self.region_names(),
        )


#: Union of accepted rect-ish inputs for the public geometry helpers.
RectTypes = Union[Rect, Mapping[str, Any], Sequence[float]]


def _coerce_rect(value: "RectTypes") -> Rect:
    """Accept a :class:`Rect`, a JSON-style mapping, or a 4-number sequence."""
    if isinstance(value, Rect):
        rect = value
    elif isinstance(value, Mapping):
        missing = [key for key in _RECT_KEYS if key not in value]
        if missing:
            raise TemplateError(
                "rect: missing required field(s) %s" % ", ".join(repr(key) for key in missing)
            )
        numbers = []
        for key in _RECT_KEYS:
            raw = value[key]
            if not _is_number(raw):
                raise TemplateError("rect.%s: expected a finite number, got %r" % (key, raw))
            numbers.append(float(raw))
        rect = Rect(*numbers)
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        if not all(_is_number(item) for item in value):
            raise TemplateError("rect: expected 4 finite numbers, got %r" % (value,))
        rect = Rect(*(float(item) for item in value))
    else:
        raise TemplateError(
            "rect: expected a Rect, a {minX,minY,maxX,maxY} object, or 4 numbers, got %r"
            % (type(value).__name__,)
        )
    if rect.width <= _EPS or rect.height <= _EPS:
        raise TemplateError("rect: must have positive width and height, got %s" % (rect.to_dict(),))
    return rect


def _parse_regions(
    value: Any,
    source: Optional[str],
    usable_area: Rect,
    title_block: Rect,
) -> Tuple[Region, ...]:
    if not isinstance(value, list) or not value:
        _fail("regions: expected a non-empty list", source)
    parsed: List[Region] = []
    names = set()
    for index, item in enumerate(value):
        field = "regions[%d]" % index
        mapping = _require_mapping(item, field, source)
        _reject_unknown(mapping, _REGION_KEYS, field, source)
        name = _require(mapping, "name", field, source)
        if not isinstance(name, str) or not name.strip():
            _fail("%s.name: expected a non-empty string" % field, source)
        name = name.strip()
        if name in names:
            _fail("regions: duplicate region name %r" % name, source)
        names.add(name)
        rect = _parse_rect(_require(mapping, "rect", field, source), "%s.rect" % field, source)
        if not usable_area.contains(rect):
            _fail(
                "regions[%d] %r: rect %s extends outside the usable page area %s"
                % (index, name, rect.to_dict(), usable_area.to_dict()),
                source,
            )
        if rect.intersects(title_block):
            _fail(
                "regions[%d] %r: rect %s intersects the title block keep-out %s"
                % (index, name, rect.to_dict(), title_block.to_dict()),
                source,
            )
        parsed.append(Region(name, rect))
    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            if parsed[i].rect.intersects(parsed[j].rect):
                _fail(
                    "regions %r and %r overlap (%s vs %s)"
                    % (
                        parsed[i].name,
                        parsed[j].name,
                        parsed[i].rect.to_dict(),
                        parsed[j].rect.to_dict(),
                    ),
                    source,
                )
    return tuple(parsed)


# ---------------------------------------------------------------------------
# loading and building
# ---------------------------------------------------------------------------


def load_template(path: Union[str, Path]) -> PageTemplate:
    """Load and strictly validate a page template JSON file.

    Raises :class:`TemplateError` with a message naming the file and the
    offending field for unreadable JSON, missing fields, bad numbers or
    geometrically invalid pages.
    """
    template_path = Path(path)
    try:
        text = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateError("cannot read page template %s: %s" % (template_path, exc)) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TemplateError(
            "%s: invalid JSON at line %s column %s: %s"
            % (template_path, exc.lineno, exc.colno, exc.msg)
        ) from exc
    return PageTemplate.from_dict(data, source=str(template_path))


def build_template_document(
    page: Union[Mapping[str, Any], Rect],
    title_block: Union[Mapping[str, Any], RectTypes],
    *,
    margin: Optional[float] = None,
    inner_border: Optional[Union[Mapping[str, Any], Rect]] = None,
    provenance: Any = None,
    notes: Optional[Iterable[str]] = None,
    measured_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a validated template document (computed regions included).

    ``page`` is ``{"width": ..., "height": ..., "margin": ...}`` (or a page
    :class:`Rect`); ``title_block`` is either a rect or
    ``{"rect": ..., "corner": ..., "visible": ...}``.  The corner is derived
    from the rect unless ``corner`` is supplied, in which case it is
    cross-checked.  Measurement wrappers use this to write measured templates.
    """
    source = "<build>"
    if isinstance(page, Mapping):
        _reject_unknown(page, _PAGE_KEYS, "page", source)
        width = _parse_number(
            _require(page, "width", "page", source), "page.width", source,
            minimum=0, strict_minimum=True,
        )
        height = _parse_number(
            _require(page, "height", "page", source), "page.height", source,
            minimum=0, strict_minimum=True,
        )
        page_margin = margin if margin is not None else page.get("margin")
        if page_margin is None:
            _fail("page: margin is required when not passed separately", source)
        page_margin = _parse_number(page_margin, "page.margin", source, minimum=0)
    elif isinstance(page, Rect):
        width, height = page.width, page.height
        page_margin = 0.0 if margin is None else _parse_number(margin, "page.margin", source, minimum=0)
    else:
        _fail("page: expected an object or Rect", source)

    page_rect = Rect(0.0, 0.0, width, height)
    expected_usable = _inset(page_rect, page_margin)
    if inner_border is not None:
        usable_area = _parse_rect(inner_border, "inner_border", source)
        if not _rect_close(usable_area, expected_usable):
            _fail(
                "inner_border %s disagrees with page.margin %s (expected %s)"
                % (usable_area.to_dict(), _json_number(page_margin), expected_usable.to_dict()),
                source,
            )
    else:
        usable_area = expected_usable

    if isinstance(title_block, Mapping):
        _reject_unknown(title_block, _TITLE_BLOCK_KEYS, "title_block", source)
        title_rect = _parse_rect(_require(title_block, "rect", "title_block", source), "title_block.rect", source)
        corner = title_block.get("corner")
        visible = title_block.get("visible")
        title_provenance = title_block.get("provenance")
        title_source = title_block.get("source")
    else:
        title_rect = _parse_rect(title_block, "title_block.rect", source)
        corner = None
        visible = None
        title_provenance = None
        title_source = None

    document: Dict[str, Any] = {"schema": SCHEMA}
    if measured_at is not None:
        document["measured_at"] = measured_at
    if provenance is not None:
        document["provenance"] = provenance
    document["page"] = {
        "width": _json_number(width),
        "height": _json_number(height),
        "margin": _json_number(page_margin),
    }
    document["inner_border"] = usable_area.to_dict()
    title_block_doc: Dict[str, Any] = {"rect": title_rect.to_dict()}
    if corner is not None:
        title_block_doc["corner"] = corner
    if visible is not None:
        title_block_doc["visible"] = visible
    if title_provenance is not None:
        title_block_doc["provenance"] = title_provenance
    if title_source is not None:
        title_block_doc["source"] = title_source
    document["title_block"] = title_block_doc

    # Build without regions first, so validation derives the corner/regions,
    # then persist the derived regions into the canonical document.
    template = PageTemplate.from_dict(document, source=source)
    document["regions"] = [
        {"name": region.name, "rect": region.rect.to_dict()} for region in template.usable_regions()
    ]
    if notes is not None:
        document["notes"] = list(notes)
    # Re-validate the complete document (including notes) before returning it.
    return PageTemplate.from_dict(document, source=source).to_dict()


__all__ = [
    "SCHEMA",
    "SUPPORTED_CORNERS",
    "TemplateError",
    "Rect",
    "Region",
    "PageTemplate",
    "load_template",
    "build_template_document",
    "derive_corner",
    "derive_regions",
]
