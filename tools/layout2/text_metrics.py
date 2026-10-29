"""Offline text metrics for the layout engine v2 (``easycirq-text-metrics/v1``).

The module is pure geometry: it never imports EDA tooling and never calls a
renderer.  Numbers come only from the measured asset
``easycirq/assets/text-metrics.json`` (single source of truth, see
``docs/method/layout-engine-v2-contract.md``); nothing here caches a private
copy of the table.

Coordinate system
-----------------
EasyEDA raw schematic units (1 unit = 0.01 inch), y **up** (the measured A4
sheet is ``0..1170 x 0..825`` with the title block at the bottom-right, i.e.
small y).  A bounding box is ``[minX, minY, maxX, maxY]``.

``text_size(text, size, anchor)`` returns ``{"w", "h", "bbox"}``.  ``bbox`` is
expressed relative to the anchor point (optionally translated by ``x``/``y``);
the anchor names describe where that point sits on the line box:

``left_top``
    top-left corner of the line box at the anchor point (box extends to the
    right and downwards, i.e. ``maxY == y``);
``left_center``
    left edge at the anchor point, vertically centred;
``center``
    centre of the line box at the anchor point;
``right_top``
    top-right corner of the line box at the anchor point (``maxX == x``).

Width accounting: wide (CJK / full-width, ``unicodedata.east_asian_width`` in
``W``/``F``) characters use ``cjk_char_w``, ASCII spaces use ``space_w``, every
other character uses the measured Latin/ASCII per-character width.  The asset
``safety_margin`` (10 %) is applied to both dimensions so the box is
deliberately conservative for the R5 collision gate.

Failure is closed: a missing / invalid asset or an unlisted font size raises
``ValueError`` ("blocked") instead of interpolating a default.
"""

from __future__ import annotations

import json
import math
import os
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

__all__ = [
    "ANCHORS",
    "DEFAULT_METRICS_PATH",
    "REQUIRED_SIZES",
    "SCHEMA",
    "SizeMetrics",
    "TextMetrics",
    "collisions",
    "frame_line_hit",
    "load_metrics",
    "text_bbox",
    "text_size",
]

#: Schema id of the text metrics asset.
SCHEMA = "easycirq-text-metrics/v1"

#: Anchor points accepted by :func:`text_size` (y-up sheet coordinates).
ANCHORS = ("left_top", "left_center", "center", "right_top")

#: Font sizes the contract requires the asset to cover (``contract 1.2``).
REQUIRED_SIZES = (7, 8, 9, 10, 12, 14, 20)

#: Default measured asset, resolved from the repository root.
DEFAULT_METRICS_PATH = (
    Path(__file__).resolve().parents[2] / "easycirq" / "assets" / "text-metrics.json"
)

_SIZE_FIELDS = ("height", "ascii_char_w", "cjk_char_w", "space_w")


@dataclass(frozen=True)
class SizeMetrics:
    """Measured metrics for one font size (all lengths in raw schematic units)."""

    size: int
    height: float
    ascii_char_w: float
    cjk_char_w: float
    space_w: float
    provenance: str = ""


@dataclass(frozen=True)
class TextMetrics:
    """Validated, immutable view of ``easycirq-text-metrics/v1``."""

    schema: str
    measured_at: str
    safety_margin: float
    sizes: Mapping[int, SizeMetrics]
    source: Mapping[str, object]
    path: Path | None = None

    def available_sizes(self) -> tuple[int, ...]:
        """Return the covered font sizes in ascending order."""

        return tuple(sorted(self.sizes))

    def size_metrics(self, size: object) -> SizeMetrics:
        """Return the entry for ``size`` or raise ``ValueError`` if unlisted."""

        key = _normalize_size(size)
        entry = self.sizes.get(key)
        if entry is None:
            supported = ", ".join(str(item) for item in self.available_sizes())
            raise _blocked(
                f"font size {size!r} is not in the text metrics asset "
                f"(covered: {supported}); no interpolation, re-measure it first"
            )
        return entry


def load_metrics(path: object | None = None) -> TextMetrics:
    """Read and validate a text metrics asset.

    ``path`` defaults to :data:`DEFAULT_METRICS_PATH`.  Any read / JSON /
    schema / value problem raises ``ValueError`` with a ``blocked`` message:
    an invalid ruler must never silently become a pass.
    """

    target = DEFAULT_METRICS_PATH if path is None else _as_path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise _blocked(f"cannot read text metrics asset {target}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _blocked(
            f"invalid JSON in text metrics asset {target}: {exc.msg} "
            f"(line {exc.lineno} column {exc.colno})"
        ) from exc
    return _parse_metrics(data, path=target)


def text_size(
    text: str,
    size: object,
    anchor: str = "left_top",
    *,
    x: float = 0.0,
    y: float = 0.0,
    metrics: object | None = None,
) -> dict[str, Any]:
    """Estimate a text line box for ``text`` at font ``size``.

    Parameters
    ----------
    text:
        Rendered string.  Empty text is allowed and yields ``w == 0``.
    size:
        Font size in raw schematic units.  It must be listed in the asset
        (no interpolation); unlisted sizes raise ``ValueError``.
    anchor:
        One of :data:`ANCHORS` (``left_top``, ``left_center``, ``center``,
        ``right_top``).
    x, y:
        Anchor point in sheet coordinates; default is the origin.
    metrics:
        Optional :class:`TextMetrics`, asset path, or metrics mapping.  The
        measured default asset is used when omitted.

    Returns
    -------
    dict
        ``{"w": float, "h": float, "bbox": [minX, minY, maxX, maxY]}`` with
        the asset ``safety_margin`` already applied to ``w`` and ``h``.
    """

    if not isinstance(text, str):
        raise _blocked(f"text must be a string, got {type(text).__name__}")
    resolved = _resolve_metrics(metrics)
    entry = resolved.size_metrics(size)
    anchor_name = _normalize_anchor(anchor)
    anchor_x = _finite(x, "x")
    anchor_y = _finite(y, "y")

    wide = sum(1 for char in text if _is_wide(char))
    spaces = sum(1 for char in text if char == " ")
    latin = len(text) - wide - spaces
    raw_width = (
        wide * entry.cjk_char_w
        + latin * entry.ascii_char_w
        + spaces * entry.space_w
    )
    factor = 1.0 + resolved.safety_margin
    width = raw_width * factor
    height = entry.height * factor
    return {
        "w": width,
        "h": height,
        "bbox": _anchor_bbox(anchor_x, anchor_y, width, height, anchor_name),
    }


def text_bbox(
    text: str,
    size: object,
    anchor: str = "left_top",
    **kwargs: Any,
) -> dict[str, Any]:
    """Contract name for :func:`text_size` (``{w, h, bbox}``)."""

    return text_size(text, size, anchor, **kwargs)


def collisions(
    boxes: Sequence[object],
    gap: float = 2.0,
) -> list[tuple[int, int]]:
    """Return the index pairs whose boxes are closer than ``gap``.

    Each box is ``[minX, minY, maxX, maxY]`` or a ``{"minX", ...}`` mapping.
    Two boxes collide when they are closer than ``gap`` in *both* axes, i.e.
    neither axis keeps the requested clearance.  Touching boxes are a
    collision for positive ``gap``; with ``gap == 0`` they only collide when
    their interiors overlap (edge contact is not an intersection).  Pairs are
    returned in ascending ``(i, j)`` order, so the result is deterministic.
    """

    clearance = _nonnegative(gap, "gap")
    rects = [_rect(box, f"boxes[{index}]") for index, box in enumerate(boxes)]
    hits: list[tuple[int, int]] = []
    for first in range(len(rects)):
        for second in range(first + 1, len(rects)):
            if _rects_collide(rects[first], rects[second], clearance):
                hits.append((first, second))
    return hits


def frame_line_hit(
    box: object,
    frame_rects: Sequence[object],
    *,
    stroke: float = 0.0,
) -> bool:
    """True when ``box`` touches or crosses any frame outline in ``frame_rects``.

    ``frame_rects`` are module-frame rectangles (``[minX, minY, maxX, maxY]``
    or mappings).  A text box living entirely inside a frame is *not* a hit:
    only the outline counts (contract R5: text must not press module frame
    lines).  ``stroke`` widens the outline by the frame's drawn stroke width;
    touching the outline counts as a hit.
    """

    core = _rect(box, "box")
    width = _nonnegative(stroke, "stroke")
    for index, raw in enumerate(frame_rects):
        frame = _rect(raw, f"frame_rects[{index}]")
        if _box_touches_outline(core, frame, width):
            return True
    return False


# ---------------------------------------------------------------------------
# Asset parsing / validation
# ---------------------------------------------------------------------------


def _parse_metrics(data: object, *, path: Path | None) -> TextMetrics:
    if not isinstance(data, Mapping):
        raise _blocked(f"text metrics asset must be a JSON object, got {type(data).__name__}")
    schema = data.get("schema")
    if schema != SCHEMA:
        raise _blocked(f"schema must be {SCHEMA!r}, got {schema!r}")
    measured_at = data.get("measured_at", "")
    if not isinstance(measured_at, str):
        raise _blocked("measured_at must be a string when present")
    source = data.get("source", {})
    if source is None:
        source = {}
    if not isinstance(source, Mapping):
        raise _blocked("source must be a JSON object when present")
    margin = data.get("safety_margin", 0.0)
    margin_value = _nonnegative(margin, "safety_margin")

    raw_sizes = data.get("sizes")
    if not isinstance(raw_sizes, Mapping) or not raw_sizes:
        raise _blocked("sizes must be a non-empty JSON object")
    sizes: dict[int, SizeMetrics] = {}
    for raw_key, raw_entry in raw_sizes.items():
        entry = _parse_size_entry(raw_key, raw_entry)
        if entry.size in sizes:
            raise _blocked(f"duplicate font size entry: {entry.size}")
        sizes[entry.size] = entry

    missing = [size for size in REQUIRED_SIZES if size not in sizes]
    if missing:
        listed = ", ".join(str(size) for size in missing)
        raise _blocked(f"required font sizes missing from the asset: {listed}")

    return TextMetrics(
        schema=SCHEMA,
        measured_at=measured_at,
        safety_margin=margin_value,
        sizes=MappingProxyType(dict(sorted(sizes.items()))),
        source=MappingProxyType(dict(source)),
        path=path,
    )


def _parse_size_entry(raw_key: object, raw_entry: object) -> SizeMetrics:
    size = _normalize_size(raw_key)
    if not isinstance(raw_entry, Mapping):
        raise _blocked(f"size {size}: entry must be a JSON object")
    values: dict[str, float] = {}
    for field in _SIZE_FIELDS:
        if field not in raw_entry:
            raise _blocked(f"size {size}: missing measured field {field!r}")
        values[field] = _positive(raw_entry[field], f"size {size}.{field}")
    provenance = raw_entry.get("provenance", "")
    if not isinstance(provenance, str):
        raise _blocked(f"size {size}: provenance must be a string when present")
    return SizeMetrics(
        size=size,
        height=values["height"],
        ascii_char_w=values["ascii_char_w"],
        cjk_char_w=values["cjk_char_w"],
        space_w=values["space_w"],
        provenance=provenance,
    )


def _normalize_size(size: object) -> int:
    if isinstance(size, bool):
        raise _blocked(f"invalid font size {size!r}")
    if isinstance(size, int):
        value = size
    elif isinstance(size, float):
        if not math.isfinite(size) or size != int(size):
            raise _blocked(f"invalid font size {size!r}: an integer size is required")
        value = int(size)
    elif isinstance(size, str):
        text = size.strip()
        try:
            number = float(text)
        except ValueError as exc:
            raise _blocked(f"invalid font size key {size!r}") from exc
        if not math.isfinite(number) or number != int(number):
            raise _blocked(f"invalid font size key {size!r}: an integer size is required")
        value = int(number)
    else:
        raise _blocked(f"invalid font size {size!r} ({type(size).__name__})")
    if value <= 0:
        raise _blocked(f"invalid font size {size!r}: must be positive")
    return value


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _anchor_bbox(
    x: float, y: float, width: float, height: float, anchor: str
) -> list[float]:
    if anchor == "left_top":
        return [x, y - height, x + width, y]
    if anchor == "left_center":
        return [x, y - height / 2.0, x + width, y + height / 2.0]
    if anchor == "center":
        return [x - width / 2.0, y - height / 2.0, x + width / 2.0, y + height / 2.0]
    if anchor == "right_top":
        return [x - width, y - height, x, y]
    raise _blocked(f"unknown anchor {anchor!r}")  # pragma: no cover - guarded


def _normalize_anchor(anchor: object) -> str:
    if not isinstance(anchor, str):
        raise _blocked(f"anchor must be a string, got {type(anchor).__name__}")
    key = anchor.strip().lower().replace("-", "_")
    if key not in ANCHORS:
        supported = ", ".join(ANCHORS)
        raise _blocked(f"unknown anchor {anchor!r} (supported: {supported})")
    return key


def _is_wide(char: str) -> bool:
    return unicodedata.east_asian_width(char) in ("W", "F")


def _rects_collide(first: Sequence[float], second: Sequence[float], gap: float) -> bool:
    if first[2] + gap <= second[0] or second[2] + gap <= first[0]:
        return False
    if first[3] + gap <= second[1] or second[3] + gap <= first[1]:
        return False
    return True


def _box_touches_outline(
    box: Sequence[float], frame: Sequence[float], stroke: float
) -> bool:
    outer = (
        frame[0] - stroke,
        frame[1] - stroke,
        frame[2] + stroke,
        frame[3] + stroke,
    )
    if not _boxes_touch(box, outer):
        return False
    inner = (
        frame[0] + stroke,
        frame[1] + stroke,
        frame[2] - stroke,
        frame[3] - stroke,
    )
    if inner[0] < inner[2] and inner[1] < inner[3]:
        strictly_inside = (
            box[0] > inner[0]
            and box[1] > inner[1]
            and box[2] < inner[2]
            and box[3] < inner[3]
        )
        if strictly_inside:
            return False
    return True


def _boxes_touch(first: Sequence[float], second: Sequence[float]) -> bool:
    return (
        first[0] <= second[2]
        and first[2] >= second[0]
        and first[1] <= second[3]
        and first[3] >= second[1]
    )


def _rect(value: object, label: str) -> tuple[float, float, float, float]:
    if isinstance(value, Mapping):
        missing = [key for key in ("minX", "minY", "maxX", "maxY") if key not in value]
        if missing:
            raise _blocked(f"{label}: missing keys {', '.join(missing)}")
        raw: object = [value["minX"], value["minY"], value["maxX"], value["maxY"]]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw = value
    else:
        raise _blocked(f"{label}: expected a rect mapping or [minX, minY, maxX, maxY]")
    if len(raw) != 4:  # type: ignore[arg-type]
        raise _blocked(f"{label}: expected exactly 4 numbers")
    box = tuple(_finite(item, f"{label}[{index}]") for index, item in enumerate(raw))
    if box[2] < box[0] or box[3] < box[1]:
        raise _blocked(f"{label}: must be ordered [minX <= maxX, minY <= maxY]")
    return box


def _as_path(path: object) -> Path:
    if isinstance(path, bytes):
        raise _blocked("metrics path must be str or os.PathLike, not bytes")
    if not isinstance(path, (str, os.PathLike)):
        raise _blocked(f"metrics path must be str or os.PathLike, got {type(path).__name__}")
    return Path(path)


def _resolve_metrics(metrics: object | None) -> TextMetrics:
    if metrics is None:
        return _default_metrics()
    if isinstance(metrics, TextMetrics):
        return metrics
    if isinstance(metrics, Mapping):
        return _parse_metrics(metrics, path=None)
    return load_metrics(_as_path(metrics))


_DEFAULT_METRICS: TextMetrics | None = None


def _default_metrics() -> TextMetrics:
    global _DEFAULT_METRICS
    if _DEFAULT_METRICS is None:
        _DEFAULT_METRICS = load_metrics()
    return _DEFAULT_METRICS


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _blocked(f"{label}: finite number required, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise _blocked(f"{label}: finite number required, got {value!r}")
    return number


def _positive(value: object, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise _blocked(f"{label}: positive number required, got {value!r}")
    return number


def _nonnegative(value: object, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise _blocked(f"{label}: non-negative number required, got {value!r}")
    return number


def _blocked(message: str) -> ValueError:
    return ValueError(f"text metrics blocked: {message}")
