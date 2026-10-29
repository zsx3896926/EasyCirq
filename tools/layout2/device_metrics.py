#!/usr/bin/env python3
"""Device metrics table for layout engine v2 (``easycirq-device-metrics/v1``).

Offline-only geometry knowledge for the module planner. Values come from live
EDA measurements (empty-page placement + ``schematic.components.list
includeBBox``), never from guessed datasheet dimensions. The asset file lives at
``easycirq/assets/device-metrics.json`` and is written by
``tools/layout2/measure_device_metrics.py``; this module only reads/validates it
and merges new measurements, so importing or testing it never touches EDA.

Document shape::

    {
      "schema": "easycirq-device-metrics/v1",
      "measured_at": "2026-10-29",          # document-level default
      "source": {"client": "...", "method": "..."},
      "parts": {
        "cap.100nf_0402": {
          "symbol":     {"w": 21.0, "h": 17.0},   # measured rendered bbox
          "pins":       2,                        # null = not measured yet
          "designator": {"size": 7, "w": 7.7},    # size pt, w raw units
          "value":      {"size": 7, "w": 7.7},
          "halo":       {"left": 22, "right": 22, "top": 16, "bottom": 10},
          "measured_at": "2026-10-29",            # optional per-part override
          "provenance": "measured ... / defaults pending measurement"
        }
      }
    }

Units are raw schematic units (0.01 inch). Raw Y grows downward, so
``halo.top`` expands ``bbox.minY`` and ``halo.bottom`` expands ``bbox.maxY``.
``halo`` is the P90 extra clearance consumed by auto-wired stubs, flags and net
labels around the symbol; ``with_halo()`` turns a symbol bbox into the block
bbox that must fit inside its zone (contract §0 rule 3).

Public API::

    metrics = load()                      # default asset
    metrics = load("path/to/metrics.json")
    part = metrics.get("cap.100nf_0402")  # KeyError with a fix hint if unknown
    part = get("cap.100nf_0402")          # module-level shorthand (cached table)
    part.with_halo(bbox)                  # symbol bbox -> haloed bbox
    metrics.with_halo(bbox, "cap.100nf_0402")
    with_halo(bbox, "cap.100nf_0402")     # module-level part-name shorthand
    with_halo(bbox, {"left": 22, ...})    # explicit halo, no part lookup
    validate(raw_document)                # raises DeviceMetricsError
    merge_part(doc, "res.10k_0402", {"symbol": {"w": 21.0, "h": 9.0}},
               measured_at="2026-10-30", provenance="...")   # returns new doc
    save(doc)                             # validated JSON write, style-stable

Bboxes are accepted as a mapping with ``minX/minY/maxX/maxY`` (the convention
used by ``schematic.components.list``) or a 4-number sequence
``(minX, minY, maxX, maxY)``; ``with_halo`` returns the same shape it was given.
"""
from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

SCHEMA = "easycirq-device-metrics/v1"

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "easycirq" / "assets" / "device-metrics.json"

HALO_SIDES = ("left", "right", "top", "bottom")
BBOX_KEYS = ("minX", "minY", "maxX", "maxY")
_NESTED_KEYS = ("symbol", "designator", "value", "halo")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

BBox = Union[Mapping[str, Any], Sequence[Any]]


class DeviceMetricsError(ValueError):
    """The device metrics document is malformed; the message names the field."""


# ---------------------------------------------------------------------------
# scalar validation
# ---------------------------------------------------------------------------
def _where(path: Optional[Union[str, Path]]) -> str:
    return f"{path}: " if path else ""


def _fail(path: Optional[Union[str, Path]], field: str, message: str) -> None:
    raise DeviceMetricsError(f"{_where(path)}{field}: {message}")


def _is_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _number(value: Any, field: str, *, path=None, minimum: Optional[float] = None,
            exclusive: bool = False, integer: bool = False) -> float:
    """Validate one finite number; ``minimum`` is inclusive unless ``exclusive``."""
    if not _is_number(value):
        _fail(path, field, f"must be a finite number, got {value!r}")
    number = float(value)
    if integer and number != int(number):
        _fail(path, field, f"must be an integer, got {value!r}")
    if minimum is not None:
        if exclusive and number <= minimum:
            _fail(path, field, f"must be > {minimum:g}, got {number:g}")
        if not exclusive and number < minimum:
            _fail(path, field, f"must be >= {minimum:g}, got {number:g}")
    return int(number) if integer else number


def _text(value: Any, field: str, *, path=None) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, field, f"must be a non-empty string, got {value!r}")
    return value.strip()


def _optional_date(value: Any, field: str, *, path=None) -> Optional[str]:
    if value is None or value == "":
        return None
    text = _text(value, field, path=path)
    if not _DATE_RE.match(text):
        _fail(path, field, f"must be an ISO date YYYY-MM-DD, got {text!r}")
    try:
        date.fromisoformat(text)
    except ValueError:
        _fail(path, field, f"must be a real calendar date YYYY-MM-DD, got {text!r}")
    return text


def _mapping(value: Any, field: str, *, path=None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, field, f"must be an object, got {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# bbox + halo helpers
# ---------------------------------------------------------------------------
def _bbox_bounds(bbox: BBox, *, path=None) -> Tuple[float, float, float, float]:
    """Return ``(minX, minY, maxX, maxY)`` as floats, validating the input."""
    if isinstance(bbox, Mapping):
        missing = [key for key in BBOX_KEYS if key not in bbox]
        if missing:
            _fail(path, "bbox", f"missing key(s) {', '.join(missing)}")
        values = [bbox[key] for key in BBOX_KEYS]
    elif isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes, bytearray)):
        if len(bbox) != 4:
            _fail(path, "bbox", f"sequence bbox needs 4 numbers (minX, minY, maxX, maxY), got {len(bbox)}")
        values = list(bbox)
    else:
        _fail(path, "bbox", f"must be a mapping with {', '.join(BBOX_KEYS)} or a 4-number sequence")
    numbers = [_number(v, f"bbox[{key}]", path=path) for key, v in zip(BBOX_KEYS, values)]
    min_x, min_y, max_x, max_y = numbers
    if min_x > max_x or min_y > max_y:
        _fail(path, "bbox", f"min must not exceed max, got {tuple(numbers)}")
    return min_x, min_y, max_x, max_y


def _write_bbox(bounds: Tuple[float, float, float, float], template: BBox) -> BBox:
    if isinstance(template, Mapping):
        return dict(zip(BBOX_KEYS, bounds))
    if isinstance(template, tuple):
        return tuple(bounds)
    return list(bounds)


@dataclass(frozen=True)
class Halo:
    """Per-side extra clearance around a symbol (raw units, Y grows downward)."""

    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0

    @classmethod
    def parse(cls, value: Any, *, path=None, field: str = "halo") -> "Halo":
        data = _mapping(value, field, path=path)
        missing = [side for side in HALO_SIDES if side not in data]
        if missing:
            _fail(path, field, f"missing side(s) {', '.join(missing)}")
        sides = {side: _number(data[side], f"{field}.{side}", path=path, minimum=0.0)
                 for side in HALO_SIDES}
        return cls(**sides)

    def as_dict(self) -> Dict[str, float]:
        return {side: getattr(self, side) for side in HALO_SIDES}


def with_halo(bbox: BBox, halo: Union[Halo, Mapping[str, Any], str]) -> BBox:
    """Expand ``bbox`` by ``halo``; returns the same bbox shape it was given.

    ``halo`` is a :class:`Halo`, a ``{left,right,top,bottom}`` mapping, or a part
    name from the shipped table (convenience for the common single-arg call).
    ``top`` expands ``minY`` and ``bottom`` expands ``maxY`` (raw Y is downward),
    ``left`` expands ``minX`` and ``right`` expands ``maxX``.
    """
    if isinstance(halo, str):
        return get(halo).with_halo(bbox)
    sides = halo if isinstance(halo, Halo) else Halo.parse(halo)
    min_x, min_y, max_x, max_y = _bbox_bounds(bbox)
    return _write_bbox((min_x - sides.left, min_y - sides.top,
                        max_x + sides.right, max_y + sides.bottom), bbox)


# ---------------------------------------------------------------------------
# parsed part + table
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PartMetrics:
    """One validated part entry. ``pins=None`` means "not measured yet"."""

    part: str
    symbol_w: float
    symbol_h: float
    pins: Optional[int]
    designator_size: float
    designator_w: float
    value_size: float
    value_w: float
    halo: Halo
    measured_at: Optional[str]
    provenance: str

    @property
    def symbol(self) -> Dict[str, float]:
        return {"w": self.symbol_w, "h": self.symbol_h}

    def with_halo(self, bbox: BBox) -> BBox:
        """Expand a symbol bbox by this part's measured halo."""
        return with_halo(bbox, self.halo)

    def as_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "symbol": self.symbol,
            "pins": self.pins,
            "designator": {"size": self.designator_size, "w": self.designator_w},
            "value": {"size": self.value_size, "w": self.value_w},
            "halo": self.halo.as_dict(),
            "provenance": self.provenance,
        }
        if self.measured_at is not None:
            data["measured_at"] = self.measured_at
        return data


@dataclass(frozen=True)
class DeviceMetrics:
    """Validated device metrics table; dict-like over part names."""

    schema: str
    measured_at: Optional[str]
    source: Mapping[str, Any]
    parts: Mapping[str, PartMetrics]
    path: Optional[Path] = None

    def get(self, part: str) -> PartMetrics:
        try:
            return self.parts[part]
        except KeyError:
            raise KeyError(self._unknown_part_message(part)) from None

    def _unknown_part_message(self, part: Any) -> str:
        known = sorted(self.parts)
        sample = ", ".join(known[:6]) + (", ..." if len(known) > 6 else "")
        location = self.path or DEFAULT_PATH
        return (
            f"unknown device part {part!r}: not in the {len(self.parts)} measured "
            f"entries (known: {sample}). Add it to {location} or measure it with "
            f"`python tools/layout2/measure_device_metrics.py --parts {part}`."
        )

    def with_halo(self, bbox: BBox, part: str) -> BBox:
        """Expand ``bbox`` by the halo of ``part`` (KeyError if unknown)."""
        return self.get(part).with_halo(bbox)

    # dict-like convenience -------------------------------------------------
    def __getitem__(self, part: str) -> PartMetrics:
        return self.get(part)

    def __contains__(self, part: object) -> bool:
        return part in self.parts

    def __iter__(self) -> Iterator[str]:
        return iter(self.parts)

    def __len__(self) -> int:
        return len(self.parts)

    def keys(self):
        return self.parts.keys()

    def as_dict(self) -> Dict[str, Any]:
        document: Dict[str, Any] = {"schema": self.schema}
        if self.measured_at is not None:
            document["measured_at"] = self.measured_at
        if self.source:
            document["source"] = copy.deepcopy(dict(self.source))
        document["parts"] = {name: part.as_dict() for name, part in self.parts.items()}
        return document


def _parse_part(name: str, raw: Any, document_date: Optional[str], *,
                path=None) -> PartMetrics:
    prefix = f"parts[{name!r}]"
    data = _mapping(raw, prefix, path=path)

    for key in ("symbol", "pins", "designator", "value", "halo", "provenance"):
        if key not in data:
            _fail(path, f"{prefix}.{key}", "required key is missing")

    symbol = _mapping(data["symbol"], f"{prefix}.symbol", path=path)
    for axis in ("w", "h"):
        if axis not in symbol:
            _fail(path, f"{prefix}.symbol.{axis}", "required key is missing")
    symbol_w = _number(symbol["w"], f"{prefix}.symbol.w", path=path, minimum=0.0, exclusive=True)
    symbol_h = _number(symbol["h"], f"{prefix}.symbol.h", path=path, minimum=0.0, exclusive=True)

    pins_raw = data["pins"]
    if pins_raw is None:
        pins: Optional[int] = None
    else:
        pins = int(_number(pins_raw, f"{prefix}.pins", path=path, minimum=0.0, integer=True))

    def dims(field: str) -> Tuple[float, float]:
        block = _mapping(data[field], f"{prefix}.{field}", path=path)
        for key in ("size", "w"):
            if key not in block:
                _fail(path, f"{prefix}.{field}.{key}", "required key is missing")
        size = _number(block["size"], f"{prefix}.{field}.size", path=path,
                       minimum=0.0, exclusive=True)
        width = _number(block["w"], f"{prefix}.{field}.w", path=path,
                        minimum=0.0, exclusive=True)
        return size, width

    designator_size, designator_w = dims("designator")
    value_size, value_w = dims("value")
    halo = Halo.parse(data["halo"], path=path, field=f"{prefix}.halo")
    provenance = _text(data["provenance"], f"{prefix}.provenance", path=path)
    measured_at = _optional_date(data.get("measured_at"), f"{prefix}.measured_at",
                                 path=path) or document_date

    return PartMetrics(
        part=name,
        symbol_w=symbol_w,
        symbol_h=symbol_h,
        pins=pins,
        designator_size=designator_size,
        designator_w=designator_w,
        value_size=value_size,
        value_w=value_w,
        halo=halo,
        measured_at=measured_at,
        provenance=provenance,
    )


def validate(document: Any, *, path: Optional[Union[str, Path]] = None) -> DeviceMetrics:
    """Validate a raw ``easycirq-device-metrics/v1`` document.

    Raises :class:`DeviceMetricsError` naming the offending field path. Unknown
    top-level/part keys are ignored so a newer measurement runner can add
    evidence fields without breaking older offline planners.
    """
    data = _mapping(document, "document", path=path)
    schema = data.get("schema")
    if schema != SCHEMA:
        _fail(path, "schema", f"must be {SCHEMA!r}, got {schema!r}")
    measured_at = _optional_date(data.get("measured_at"), "measured_at", path=path)
    source_raw = data.get("source")
    source = {} if source_raw is None else dict(_mapping(source_raw, "source", path=path))
    parts_raw = data.get("parts")
    if not isinstance(parts_raw, Mapping) or not parts_raw:
        _fail(path, "parts", "must be a non-empty object keyed by part name")
    parts: Dict[str, PartMetrics] = {}
    for name, raw in parts_raw.items():
        if not isinstance(name, str) or not name.strip():
            _fail(path, "parts", f"part name must be a non-empty string, got {name!r}")
        parts[name] = _parse_part(name, raw, measured_at, path=path)
    return DeviceMetrics(schema=SCHEMA, measured_at=measured_at, source=source,
                         parts=parts, path=Path(path) if path is not None else None)


def load(path: Optional[Union[str, Path]] = None) -> DeviceMetrics:
    """Read and validate a metrics JSON file (default: the shipped asset)."""
    target = Path(path) if path is not None else DEFAULT_PATH
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeviceMetricsError(f"cannot read device metrics {target}: {exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DeviceMetricsError(f"{target}: invalid JSON: {exc}") from exc
    return validate(document, path=target)


@lru_cache(maxsize=1)
def _default_metrics() -> DeviceMetrics:
    """Cached snapshot of the shipped asset (cleared when :func:`save` writes it)."""
    return load()


def get(part: str, path: Optional[Union[str, Path]] = None) -> PartMetrics:
    """Look up one part in the shipped table (or ``path``); KeyError with a hint."""
    metrics = load(path) if path is not None else _default_metrics()
    return metrics.get(part)


# ---------------------------------------------------------------------------
# measurement write-back (used by tools/layout2/measure_device_metrics.py)
# ---------------------------------------------------------------------------
def merge_part(document: Mapping[str, Any], part: str, fields: Mapping[str, Any], *,
               measured_at: Optional[str] = None,
               provenance: Optional[str] = None,
               allow_new: bool = False,
               path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Return a new document with ``fields`` merged into ``parts[part]``.

    Contract for measurement write-back:

    * only supplied fields are written — omitting ``halo`` keeps the previous
      halo, omitting ``symbol`` keeps the previous symbol, so a partial
      measurement cannot silently erase a better value;
    * nested ``symbol``/``designator``/``value``/``halo`` objects merge one deep
      per key; any other key is replaced;
    * existing ``provenance`` and per-part ``measured_at`` are preserved unless
      the caller passes new values, so a remeasure is attributable and defaults
      stay marked as defaults;
    * an unknown part raises ``KeyError`` (with a fix hint) unless
      ``allow_new=True``; a new entry must still validate as a complete part;
    * the merged document is validated before it is returned.
    """
    if not isinstance(document, Mapping):
        raise DeviceMetricsError(f"document must be an object, got {type(document).__name__}")
    if not isinstance(part, str) or not part.strip():
        raise DeviceMetricsError(f"part name must be a non-empty string, got {part!r}")
    if not isinstance(fields, Mapping):
        raise DeviceMetricsError(f"fields must be an object, got {type(fields).__name__}")

    output = copy.deepcopy(dict(document))
    parts = output.get("parts")
    if not isinstance(parts, Mapping):
        _fail(path, "parts", "must be an object before merging a measurement")
    parts = copy.deepcopy(dict(parts))
    entry_raw = parts.get(part)
    if entry_raw is None:
        if not allow_new:
            known = sorted(parts)
            sample = ", ".join(known[:6]) + (", ..." if len(known) > 6 else "")
            raise KeyError(
                f"unknown device part {part!r}: not in the {len(parts)} measured "
                f"entries (known: {sample}). Pass allow_new=True to add a complete "
                f"entry, or measure it with "
                f"`python tools/layout2/measure_device_metrics.py --parts {part}`."
            )
        entry: Dict[str, Any] = {}
    else:
        entry = dict(_mapping(entry_raw, f"parts[{part!r}]", path=path))

    for key, value in fields.items():
        if key in _NESTED_KEYS and isinstance(value, Mapping):
            existing = entry.get(key)
            merged = dict(existing) if isinstance(existing, Mapping) else {}
            merged.update(copy.deepcopy(dict(value)))
            entry[key] = merged
        else:
            entry[key] = copy.deepcopy(value)
    if measured_at is not None:
        entry["measured_at"] = measured_at
    if provenance is not None:
        entry["provenance"] = provenance

    parts[part] = entry
    output["parts"] = parts
    validate(output, path=path)
    return output


def save(document: Mapping[str, Any], path: Optional[Union[str, Path]] = None) -> Path:
    """Validate and write a metrics document in the asset's stable JSON style."""
    target = Path(path) if path is not None else DEFAULT_PATH
    validate(document, path=target)
    text = json.dumps(dict(document), ensure_ascii=False, indent=1) + "\n"
    target.write_text(text, encoding="utf-8", newline="\n")
    if target.resolve() == DEFAULT_PATH.resolve():
        _default_metrics.cache_clear()
    return target
