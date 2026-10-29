"""Deterministic offline label placement for schematic pages.

Implements ``easycirq-sch-label-plan/v1`` (see
``docs/method/layout-engine-v2-contract.md``).  The solver never touches EDA:
given text labels, occupied boxes (symbols, frames, ...) and page bounds it
places every label around its anchor and reports the ones it cannot place.

Candidate geometry
------------------
A label's anchor is the point it belongs to (usually a pin).  For a candidate
direction the label's bounding box is offset from the anchor by ``distance``
along that axis; for cardinal directions the label is centred on the other
axis.  Eight directions are tried:

``right``, ``top``, ``left``, ``bottom``, ``right-top``, ``left-top``,
``left-bottom``, ``right-bottom``.

For every label the directions are tried in the requested ``preferred`` order
first, then the remaining canonical directions.  For each direction the
distances ``4, 8, 12, 16`` are tried in ascending order.  The first candidate
that stays inside the page and keeps a gap of at least ``2`` from every
occupied box and already-placed label wins.  Labels are processed in input
order, which makes the whole plan deterministic.

Bounding boxes are ``[minX, minY, maxX, maxY]``.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Callable, Mapping, Sequence

#: Output schema id.
SCHEMA = "easycirq-sch-label-plan/v1"

#: Minimum clearance (in page units) between a label and anything else.
GAP = 2.0

#: Candidate distances, tried in ascending order.
DISTANCES = (4, 8, 12, 16)

#: Canonical direction order; ``preferred`` moves entries to the front.
DIRECTIONS = (
    "right",
    "top",
    "left",
    "bottom",
    "right-top",
    "left-top",
    "left-bottom",
    "right-bottom",
)

_BBox = tuple[float, float, float, float]
_Point = tuple[float, float]
_Metrics = Callable[[str, float], object]

_EPS = 1e-9
_DIRECTION_ALIASES = {
    "top-right": "right-top",
    "top-left": "left-top",
    "bottom-left": "left-bottom",
    "bottom-right": "right-bottom",
}


def default_metrics(text: str, size: float) -> dict[str, float]:
    """Estimate a text box using the contract default metrics.

    Latin characters are ``0.6 * size`` wide and full-width (CJK) characters
    are ``1.0 * size`` wide; the line height is ``1.2 * size``.
    """

    width = 0.0
    for char in text:
        factor = 1.0 if unicodedata.east_asian_width(char) in ("W", "F") else 0.6
        width += size * factor
    return {"w": width, "h": size * 1.2}


def solve_label_plan(
    labels: Sequence[Mapping[str, object]],
    occupied_boxes: Sequence[object] | None,
    page: object,
    metrics: _Metrics | None = None,
    *,
    gap: float = GAP,
    distances: Sequence[float] = DISTANCES,
) -> dict[str, object]:
    """Place labels without collisions and without leaving the page.

    Parameters
    ----------
    labels:
        ``[{"id", "text", "size", "anchor": [x, y], "preferred": [...],
        "role"}]``.  ``role`` is informational and does not affect placement.
    occupied_boxes:
        Bounding boxes already taken by symbols, frames, etc.  Each item may
        be ``[minX, minY, maxX, maxY]`` or a rect mapping.
    page:
        Page bounds as ``[minX, minY, maxX, maxY]``, a rect mapping, or a
        ``{"width", "height"}`` mapping with an optional origin.
    metrics:
        Optional ``metrics(text, size)`` callable returning ``{"w", "h"}``
        (or a ``(w, h)`` pair).  Defaults to :func:`default_metrics`.
    gap:
        Required clearance between the label box and any other box.
    distances:
        Candidate distances, tried in the given order (ascending by default).

    Returns
    -------
    dict
        ``{"schema", "placements", "unplaced", "collisions_remaining",
        "verdict"}``.  ``verdict`` is ``"pass"`` when every label is placed
        and ``"review"`` otherwise.
    """

    page_bbox = _as_bbox(page, "page")
    gap_value = _as_non_negative_float(gap, "gap")
    distance_values = _as_distances(distances)

    boxes = [_as_bbox(box, "occupied_boxes entry") for box in occupied_boxes or ()]

    placements: list[dict[str, object]] = []
    unplaced: list[dict[str, str]] = []
    placed_boxes: list[_BBox] = []

    for index, label in enumerate(labels):
        label_id, text, size, anchor, preferred = _read_label(label, index)
        width, height = _measure(text, size, metrics)

        chosen: tuple[_BBox, str, float] | None = None
        for direction in _direction_order(preferred):
            for distance in distance_values:
                candidate = _candidate_bbox(anchor, width, height, direction, distance)
                if not _inside_page(candidate, page_bbox):
                    continue
                blockers = boxes + placed_boxes
                if not _clear_of(candidate, blockers, gap_value):
                    continue
                chosen = (candidate, direction, distance)
                break
            if chosen is not None:
                break

        if chosen is None:
            if width > page_bbox[2] - page_bbox[0] + _EPS or (
                height > page_bbox[3] - page_bbox[1] + _EPS
            ):
                reason = "label_larger_than_page"
            else:
                reason = "no_valid_candidate"
            unplaced.append({"id": label_id, "reason": reason})
            continue

        bbox, direction, distance = chosen
        placements.append(
            {
                "id": label_id,
                "bbox": list(bbox),
                "direction": direction,
                "distance": distance,
            }
        )
        placed_boxes.append(bbox)

    collisions_remaining = _count_collisions(placed_boxes, boxes, gap_value)

    return {
        "schema": SCHEMA,
        "placements": placements,
        "unplaced": unplaced,
        "collisions_remaining": collisions_remaining,
        "verdict": "pass" if not unplaced else "review",
    }


# ---------------------------------------------------------------------------
# Input normalisation


def _as_bbox(value: object, what: str) -> _BBox:
    if isinstance(value, Mapping):
        for key in ("rect", "bbox"):
            nested = value.get(key)
            if nested is not None:
                return _as_bbox(nested, what)
        if all(key in value for key in ("minX", "minY", "maxX", "maxY")):
            return _make_bbox(
                value["minX"], value["minY"], value["maxX"], value["maxY"], what
            )
        if all(key in value for key in ("x0", "y0", "x1", "y1")):
            return _make_bbox(value["x0"], value["y0"], value["x1"], value["y1"], what)
        if "width" in value and "height" in value:
            x0 = value.get("x", value.get("minX", 0.0))
            y0 = value.get("y", value.get("minY", 0.0))
            x1 = _as_float(x0, what) + _as_float(value["width"], what)
            y1 = _as_float(y0, what) + _as_float(value["height"], what)
            return _make_bbox(x0, y0, x1, y1, what)

    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 4
    ):
        return _make_bbox(value[0], value[1], value[2], value[3], what)

    raise ValueError(
        f"{what} must be [minX, minY, maxX, maxY] or a rect mapping, got {value!r}"
    )


def _make_bbox(x0: object, y0: object, x1: object, y1: object, what: str) -> _BBox:
    min_x = _as_float(x0, what)
    min_y = _as_float(y0, what)
    max_x = _as_float(x1, what)
    max_y = _as_float(y1, what)
    if min_x > max_x or min_y > max_y:
        raise ValueError(
            f"{what} has inverted bounds: [{min_x}, {min_y}, {max_x}, {max_y}]"
        )
    return (min_x, min_y, max_x, max_y)


def _as_point(value: object, what: str) -> _Point:
    if isinstance(value, Mapping):
        if "x" in value and "y" in value:
            return (_as_float(value["x"], what), _as_float(value["y"], what))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) == 2:
            return (_as_float(value[0], what), _as_float(value[1], what))
    raise ValueError(f"{what} must be [x, y] or a mapping with x/y, got {value!r}")


def _as_float(value: object, what: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be numeric, got {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{what} must be finite, got {value!r}")
    return number


def _as_non_negative_float(value: object, what: str) -> float:
    number = _as_float(value, what)
    if number < 0:
        raise ValueError(f"{what} must be >= 0, got {value!r}")
    return number


def _as_distances(distances: Sequence[float]) -> tuple[float, ...]:
    values = tuple(_as_float(distance, "distance") for distance in distances)
    if not values:
        raise ValueError("distances must not be empty")
    for value in values:
        if value <= 0:
            raise ValueError(f"distances must be > 0, got {value!r}")
    return values


def _read_label(
    label: Mapping[str, object], index: int
) -> tuple[str, str, float, _Point, object]:
    if not isinstance(label, Mapping):
        raise ValueError(f"labels[{index}] must be a mapping, got {label!r}")
    for key in ("id", "text", "size", "anchor"):
        if key not in label:
            raise ValueError(f"labels[{index}] is missing {key!r}")

    label_id = label["id"]
    if not isinstance(label_id, str) or not label_id:
        raise ValueError(f"labels[{index}].id must be a non-empty string")

    text = label["text"]
    if not isinstance(text, str):
        raise ValueError(f"labels[{index}].text must be a string")

    size = _as_float(label["size"], f"labels[{index}].size")
    if size <= 0:
        raise ValueError(f"labels[{index}].size must be > 0")

    anchor = _as_point(label["anchor"], f"labels[{index}].anchor")
    preferred = label.get("preferred") or ()
    return label_id, text, size, anchor, preferred


def _measure(text: str, size: float, metrics: _Metrics | None) -> tuple[float, float]:
    if metrics is None:
        result: object = default_metrics(text, size)
    else:
        result = metrics(text, size)

    if isinstance(result, Mapping):
        if "w" not in result or "h" not in result:
            raise ValueError("metrics result mapping must contain 'w' and 'h'")
        width = _as_float(result["w"], "metrics width")
        height = _as_float(result["h"], "metrics height")
    elif isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        if len(result) != 2:
            raise ValueError("metrics result must be (w, h) or a mapping with w/h")
        width = _as_float(result[0], "metrics width")
        height = _as_float(result[1], "metrics height")
    else:
        raise ValueError("metrics result must be (w, h) or a mapping with w/h")

    if width < 0 or height < 0:
        raise ValueError("metrics must not return negative sizes")
    return width, height


# ---------------------------------------------------------------------------
# Geometry


def _direction_order(preferred: object) -> tuple[str, ...]:
    ordered: list[str] = []
    if isinstance(preferred, str):
        preferred = (preferred,)
    if isinstance(preferred, Sequence):
        for raw in preferred:
            if not isinstance(raw, str):
                continue
            name = raw.strip().lower().replace("_", "-")
            name = _DIRECTION_ALIASES.get(name, name)
            if name in DIRECTIONS and name not in ordered:
                ordered.append(name)
    for direction in DIRECTIONS:
        if direction not in ordered:
            ordered.append(direction)
    return tuple(ordered)


def _candidate_bbox(
    anchor: _Point, width: float, height: float, direction: str, distance: float
) -> _BBox:
    anchor_x, anchor_y = anchor
    half_width = width / 2.0
    half_height = height / 2.0

    if direction == "right":
        min_x = anchor_x + distance
        min_y = anchor_y - half_height
    elif direction == "left":
        min_x = anchor_x - distance - width
        min_y = anchor_y - half_height
    elif direction == "top":
        min_x = anchor_x - half_width
        min_y = anchor_y - distance - height
    elif direction == "bottom":
        min_x = anchor_x - half_width
        min_y = anchor_y + distance
    elif direction == "right-top":
        min_x = anchor_x + distance
        min_y = anchor_y - distance - height
    elif direction == "left-top":
        min_x = anchor_x - distance - width
        min_y = anchor_y - distance - height
    elif direction == "left-bottom":
        min_x = anchor_x - distance - width
        min_y = anchor_y + distance
    elif direction == "right-bottom":
        min_x = anchor_x + distance
        min_y = anchor_y + distance
    else:  # pragma: no cover - guarded by _direction_order
        raise ValueError(f"unknown direction: {direction!r}")

    return (min_x, min_y, min_x + width, min_y + height)


def _inside_page(box: _BBox, page: _BBox) -> bool:
    return (
        box[0] >= page[0] - _EPS
        and box[1] >= page[1] - _EPS
        and box[2] <= page[2] + _EPS
        and box[3] <= page[3] + _EPS
    )


def _separated(first: _BBox, second: _BBox, gap: float) -> bool:
    return (
        first[2] + gap <= second[0]
        or second[2] + gap <= first[0]
        or first[3] + gap <= second[1]
        or second[3] + gap <= first[1]
    )


def _clear_of(candidate: _BBox, boxes: Sequence[_BBox], gap: float) -> bool:
    return all(_separated(candidate, box, gap) for box in boxes)


def _count_collisions(
    label_boxes: Sequence[_BBox], occupied: Sequence[_BBox], gap: float
) -> int:
    """Count remaining label/label and label/occupied pairs closer than ``gap``."""

    count = 0
    for index, box in enumerate(label_boxes):
        count += sum(1 for other in occupied if not _separated(box, other, gap))
        for other in label_boxes[index + 1 :]:
            if not _separated(box, other, gap):
                count += 1
    return count
