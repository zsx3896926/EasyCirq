"""CPL parsing for the offline delivery audit (contract §7.4).

Returns the contract shape ``{kind, file, status, facts, capability, findings}``.
It never writes files, never reaches the network and never raises on malformed
content (only caller programming errors such as a non-bytes payload or a
non-string option raise ``ValueError``).

Policy decisions (documented so a reviewer does not have to infer them):

* Encoding / CSV: the same strict handling as :mod:`delivery_audit.bom` --
  default ``utf-8-sig``, ``options['encoding']`` validated with
  :func:`codecs.lookup`, no ``errors='replace'``; delimiter from
  ``options['delimiter']`` else a deterministic sniff of the first non-empty
  line (tie -> comma + ``cpl.delimiter_ambiguous`` unknown).
* Units: the header wins over a declared unit.  A unit may be declared in the
  X/Y header text (``X(mm)``), by a unit column, or by ``options['unit']``
  (``unit_source`` is then ``header`` or ``declared``).  Supported units are
  ``mm``, ``mil`` (0.0254 mm) and ``inch``/``in`` (25.4 mm); facts store the raw
  value plus ``x_mm``/``y_mm``.  No unit at all is a fail (``cpl.unit_missing``),
  never a guess.  An unrecognized unit in a cell is ``cpl.position_unit_unknown``.
* Numeric values are parsed strictly: empty, ``NaN``, ``Infinity``, booleans,
  malformed exponents and non-finite values are rejected
  (``cpl.position_not_numeric`` / ``cpl.rotation_not_numeric``).
* Sides map only ``top/bottom/T/B/back/front`` (case-insensitive); a missing
  side column is ``cpl.side_missing`` and an unknown value ``cpl.side_unknown``.
* Rotation keeps the raw numeric value and a normalized ``% 360`` value.
* Severity policy: ``blocking`` when coordinates cannot be trusted at all (no
  unit, empty, undecodable, no designator column), ``major`` for definite row
  data violations, ``minor`` for unknown/ambiguous/limit findings.

The contract §7.4 rule list has no dedicated rule for a CSV structural error;
this parser reports such a record as ``cpl.required_field_missing`` (fail) with
the CSV error in ``evidence`` and names the limitation in the module docstring.
"""

from __future__ import annotations

import csv
import io
import math
import re

from .bom import (
    DEFAULT_MAX_ROWS,
    DESIGNATOR_RE,
    aggregate_status,
    cell_text,
    copy_capability,
    decode_bytes,
    normalize_header,
    options_as_dict,
    resolve_delimiter,
    resolve_encoding,
    resolve_limit,
    resolve_required_fields,
)
from .model import finding

DEFAULT_REQUIRED_FIELDS = ("designator", "x", "y", "layer", "rotation")

CPL_FIELDS = ("designator", "x", "y", "layer", "rotation", "unit")

MAX_EVIDENCE_ITEMS = 50

_CPL_ALIASES = {
    "designator": ("designator", "designators", "ref", "refs", "reference",
                   "references", "位号"),
    "x": ("x", "mid x", "center x", "posx"),
    "y": ("y", "mid y", "center y", "posy"),
    "layer": ("layer", "side", "面", "层"),
    "rotation": ("rotation", "rot", "angle"),
    "unit": ("unit", "units", "单位"),
}

# Recognized unit words -> canonical unit; None marks a known-but-unsupported
# unit word so it can be reported instead of silently treated as "no unit".
_UNIT_WORDS = {
    "mm": "mm",
    "mil": "mil",
    "mils": "mil",
    "inch": "inch",
    "inches": "inch",
    "in": "inch",
    "um": None,
    "\u00b5m": None,
    "cm": None,
}

_UNIT_FACTORS = {"mm": 1.0, "mil": 0.0254, "inch": 25.4}

_UNIT_WORD_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(inches|inch|mils|mil|mm|\u00b5m|um|cm|in)"
    r"(?![A-Za-z0-9])")

_SIDE_MAP = {
    "top": "top",
    "t": "top",
    "front": "top",
    "bottom": "bottom",
    "b": "bottom",
    "back": "bottom",
}

_NUMBER_LITERALS = frozenset((
    "nan", "+nan", "-nan",
    "inf", "+inf", "-inf",
    "infinity", "+infinity", "-infinity",
    "true", "false", "yes", "no", "y", "n",
))
_NUMBER_RE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
                        r"(?:[eE][+-]?[0-9]+)?$")

CPL_CAPABILITY = {
    "supported": (
        "csv_utf8_bom",
        "declared_encoding",
        "declared_delimiter",
        "delimiter_sniff",
        "csv_quotes_newlines",
        "column_aliases",
        "unit_header",
        "unit_column",
        "unit_declared",
        "unit_mm",
        "unit_mil",
        "unit_inch",
        "side_top_bottom",
        "rotation_preserved",
        "rotation_normalized",
    ),
    "unsupported": (
        "xlsx_cpl",
        "arbitrary_units",
        "um_units",
        "bottom_side_mirror_transform",
        "rotation_offset_application",
        "coordinate_transform",
    ),
    "unknown": (),
}


# ---------------------------------------------------------------------------
# CPL-specific helpers


def parse_number(text):
    """Strictly parse a finite number.  Returns ``(value, problem_or_None)``."""
    if text is None:
        return None, "empty"
    value = str(text).strip()
    if not value:
        return None, "empty"
    lowered = value.casefold()
    if lowered in _NUMBER_LITERALS:
        return None, "non_finite_or_boolean"
    if not _NUMBER_RE.match(value):
        return None, "malformed"
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None, "malformed"
    if not math.isfinite(number):
        return None, "non_finite"
    return number, None


def _extract_header_units(cell):
    """Return ``(unit_matches, residual_text)`` for one header cell."""
    matches = []
    for match in _UNIT_WORD_RE.finditer(cell):
        word = match.group(1).casefold()
        matches.append((word, _UNIT_WORDS.get(word)))
    return matches, _UNIT_WORD_RE.sub(" ", cell)


def _map_columns(header_cells):
    lookup = {}
    for field_name, names in _CPL_ALIASES.items():
        for name in names:
            lookup.setdefault(normalize_header(name), field_name)
    mapping = {}
    raw_mapping = {}
    ignored = []
    unrecognized = []
    header_units = []
    for index, cell in enumerate(header_cells):
        cell = str(cell)
        unit_matches, residual = _extract_header_units(cell)
        header_units.extend(unit_matches)
        field_name = lookup.get(normalize_header(residual))
        if field_name is None:
            unrecognized.append(cell)
        elif field_name in mapping:
            ignored.append(cell)
        else:
            mapping[field_name] = index
            raw_mapping[field_name] = cell.strip()
    return mapping, raw_mapping, ignored, unrecognized, header_units


def _resolve_header_unit(header_units):
    """Return ``(unit_or_None, problem_or_None)`` from header unit words."""
    known = []
    unsupported = []
    for word, canonical in header_units:
        if canonical is None:
            if word not in unsupported:
                unsupported.append(word)
        elif canonical not in known:
            known.append(canonical)
    if len(known) > 1:
        return None, ("conflict", sorted(known))
    if known and unsupported:
        return None, ("malformed", sorted(set(known + unsupported)))
    if known:
        return known[0], None
    if unsupported:
        return None, ("unsupported", sorted(unsupported))
    return None, None


def _resolve_declared_unit(options):
    raw = options_as_dict(options).get("unit")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("options['unit'] must be a non-empty string")
    return _UNIT_WORDS.get(raw.strip().casefold())


def _resolve_row_unit(unit_text, header_unit, declared_unit):
    """Return ``(unit, source, unknown_text)`` for one placement."""
    if unit_text:
        key = unit_text.casefold()
        canonical = _UNIT_WORDS.get(key)
        if canonical is not None:
            return canonical, "header", None
        return None, None, unit_text
    if header_unit is not None:
        return header_unit, "header", None
    if declared_unit is not None:
        return declared_unit, "declared", None
    return None, None, None


def _build_result(file, facts, capability, findings):
    return {
        "kind": "cpl",
        "file": file,
        "status": aggregate_status(findings),
        "facts": facts,
        "capability": capability,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Public parser


def parse_cpl(data, file, options=None):
    """Parse CPL bytes into the contract §7.4 result.  Never raises on content."""
    file = str(file)
    options = options_as_dict(options)

    encoding, encoding_source = resolve_encoding(options)
    max_rows = resolve_limit(options, "max_rows", DEFAULT_MAX_ROWS)
    required_fields = resolve_required_fields(
        options, CPL_FIELDS, DEFAULT_REQUIRED_FIELDS)
    declared_unit = _resolve_declared_unit(options)

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("data must be bytes-like")
    payload = bytes(data)

    findings = []
    rows = []
    counts = {
        "rows": 0,
        "unique_designators": 0,
        "sides": {"top": 0, "bottom": 0, "unknown": 0},
        "by_unit": {"mm": 0, "mil": 0, "inch": 0, "unknown": 0},
    }
    facts = {
        "encoding": encoding,
        "encoding_source": encoding_source,
        "delimiter": None,
        "delimiter_source": None,
        "header": [],
        "header_line": None,
        "header_mapping": {},
        "ignored_columns": [],
        "unrecognized_columns": [],
        "required_fields": list(required_fields),
        "units": None,
        "unit_source": None,
        "row_limit": max_rows,
        "rows_truncated": False,
        "rows": rows,
        "counts": counts,
    }
    capability = copy_capability(CPL_CAPABILITY)

    if not payload:
        findings.append(finding(
            "cpl.empty", "fail", "blocking",
            "CPL file has no bytes; export the CPL again and audit the new file.",
            file=file))
        return _build_result(file, facts, capability, findings)

    text, decode_error = decode_bytes(payload, encoding)
    if text is None:
        findings.append(finding(
            "cpl.encoding_unspecified", "fail", "blocking",
            "CPL bytes are not valid %s and were not decoded with replacement "
            "characters; declare the CPL encoding explicitly "
            "(declarations encodings.cpl)." % encoding,
            file=file,
            actual=encoding,
            evidence={"decoder_error": decode_error,
                      "encoding_source": encoding_source},
            suggestion="declare the CPL encoding in the delivery declarations"))
        return _build_result(file, facts, capability, findings)

    if not text.strip():
        findings.append(finding(
            "cpl.empty", "fail", "blocking",
            "CPL file contains only whitespace.", file=file))
        return _build_result(file, facts, capability, findings)

    delimiter, delimiter_source, ambiguous_counts = resolve_delimiter(
        options, text)
    facts["delimiter"] = delimiter
    facts["delimiter_source"] = delimiter_source
    if ambiguous_counts is not None:
        findings.append(finding(
            "cpl.delimiter_ambiguous", "unknown", "minor",
            "The first non-empty CPL line matches several delimiters equally; "
            "comma is assumed and the column mapping may be wrong.",
            file=file,
            actual=",",
            evidence={"counts": ambiguous_counts}))

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = None
    header_line = None
    data_records = []
    truncated = False
    csv_error = None
    while True:
        try:
            record = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            csv_error = {"line": reader.line_num, "message": str(exc)}
            break
        line = reader.line_num
        if not any(str(cell).strip() for cell in record):
            continue
        if header is None:
            header = [str(cell) for cell in record]
            header_line = line
            continue
        if len(data_records) >= max_rows:
            truncated = True
            break
        data_records.append((line, record))

    if header is None:
        if csv_error is not None:
            findings.append(finding(
                "cpl.required_field_missing", "fail", "major",
                "CPL CSV could not be read: %s" % csv_error["message"],
                obj="row", file=file, line=csv_error["line"],
                evidence={"csv_error": csv_error["message"]}))
        else:
            findings.append(finding(
                "cpl.empty", "fail", "blocking",
                "CPL contains no non-empty line (no header found).", file=file))
        return _build_result(file, facts, capability, findings)

    facts["header"] = header
    facts["header_line"] = header_line
    mapping, raw_mapping, ignored, unrecognized, header_units = _map_columns(
        header)
    facts["header_mapping"] = raw_mapping
    facts["ignored_columns"] = ignored
    facts["unrecognized_columns"] = unrecognized
    facts["header_aliases"] = {field: list(names)
                               for field, names in _CPL_ALIASES.items()}

    header_unit, header_unit_problem = _resolve_header_unit(header_units)
    unit_problem_emitted = False
    if header_unit_problem is not None:
        reason, values = header_unit_problem
        findings.append(finding(
            "cpl.unit_missing", "fail", "blocking",
            "CPL header declares an unsupported or contradictory unit (%s: %s); "
            "coordinates cannot be normalized to millimetres."
            % (reason, ", ".join(values)),
            file=file,
            evidence={"header_units": header_units, "problem": reason}))
        unit_problem_emitted = True

    if csv_error is not None:
        findings.append(finding(
            "cpl.required_field_missing", "fail", "major",
            "CPL CSV could not be read after row %d: %s; later rows are not "
            "reliable." % (csv_error["line"], csv_error["message"]),
            obj="row", file=file, line=csv_error["line"],
            evidence={"csv_error": csv_error["message"]}))

    if "designator" not in mapping:
        findings.append(finding(
            "cpl.no_designator_column", "fail", "blocking",
            "CPL has no designator column; supported aliases: %s."
            % ", ".join(_CPL_ALIASES["designator"]),
            file=file,
            expected="designator",
            evidence={"header": header}))
        return _build_result(file, facts, capability, findings)

    # Required columns.  designator/layer/rotation have dedicated rules below,
    # so the generic check covers only the remaining required fields (x/y).
    for field_name in required_fields:
        if field_name in ("designator", "layer", "rotation"):
            continue
        if field_name not in mapping:
            findings.append(finding(
                "cpl.required_field_missing", "fail", "major",
                "Required CPL column %r is missing; supported aliases: %s."
                % (field_name, ", ".join(_CPL_ALIASES[field_name])),
                obj=field_name, file=file, expected=field_name,
                evidence={"header": header}))

    if "layer" not in mapping:
        findings.append(finding(
            "cpl.side_missing", "fail", "major",
            "CPL has no side/layer column; the placement side cannot be "
            "verified. Supported aliases: %s."
            % ", ".join(_CPL_ALIASES["layer"]),
            file=file, expected="layer", evidence={"header": header}))
    if "rotation" not in mapping:
        findings.append(finding(
            "cpl.rotation_not_numeric", "fail", "major",
            "CPL has no rotation column; rotation cannot be verified.",
            file=file, expected="rotation", evidence={"header": header}))

    if not data_records:
        findings.append(finding(
            "cpl.empty", "fail", "blocking",
            "CPL has a header but no placement rows.", file=file,
            line=header_line))
        return _build_result(file, facts, capability, findings)

    if truncated:
        facts["rows_truncated"] = True
        findings.append(finding(
            "cpl.limit_rows", "unknown", "minor",
            "CPL has more than the configured %d placement rows; parsing "
            "stopped at the resource limit, so later rows were not audited."
            % max_rows,
            file=file,
            evidence={"max_rows": max_rows}))

    designator_column = mapping["designator"]
    x_column = mapping.get("x")
    y_column = mapping.get("y")
    side_column = mapping.get("layer")
    rotation_column = mapping.get("rotation")
    unit_column = mapping.get("unit")
    seen = {}
    unresolved_unit_lines = []
    unit_problem_any = False
    used_header_unit = header_unit is not None
    used_declared_unit = False
    used_units = set()
    row_finding_lines = set()
    for line, record in data_records:
        designator = None
        designator_raw = cell_text(record, designator_column)
        designator_text = designator_raw.strip()
        if not designator_text:
            findings.append(finding(
                "cpl.designator_missing_invalid", "fail", "major",
                "CPL row has no designator.", file=file, line=line,
                actual=designator_raw,
                evidence={"designator_raw": designator_raw}))
            row_finding_lines.add(line)
        elif not DESIGNATOR_RE.match(designator_text):
            findings.append(finding(
                "cpl.designator_missing_invalid", "fail", "major",
                "CPL designator %r is not a supported designator token."
                % designator_text,
                obj=designator_text, file=file, line=line,
                actual=designator_text))
            row_finding_lines.add(line)
        else:
            designator = designator_text
            first_line = seen.get(designator)
            if first_line is not None:
                findings.append(finding(
                    "cpl.designator_duplicate", "fail", "major",
                    "Designator %r appears more than once in the CPL."
                    % designator,
                    obj=designator, file=file, line=line,
                    evidence={"first_line": first_line}))
                row_finding_lines.add(line)
            else:
                seen[designator] = line

        x = None
        y = None
        if x_column is not None:
            x_text = cell_text(record, x_column).strip()
            x, problem = parse_number(x_text)
            if problem is not None:
                findings.append(finding(
                    "cpl.position_not_numeric", "fail", "major",
                    "X coordinate %r is not a finite number (%s)."
                    % (x_text, problem),
                    obj=designator or "x", file=file, line=line,
                    actual=x_text))
                row_finding_lines.add(line)
        if y_column is not None:
            y_text = cell_text(record, y_column).strip()
            y, problem = parse_number(y_text)
            if problem is not None:
                findings.append(finding(
                    "cpl.position_not_numeric", "fail", "major",
                    "Y coordinate %r is not a finite number (%s)."
                    % (y_text, problem),
                    obj=designator or "y", file=file, line=line,
                    actual=y_text))
                row_finding_lines.add(line)

        unit_text = ""
        if unit_column is not None:
            unit_text = cell_text(record, unit_column).strip()
        unit, unit_source, unknown_unit = _resolve_row_unit(
            unit_text, header_unit, declared_unit)
        if unknown_unit is not None:
            findings.append(finding(
                "cpl.position_unit_unknown", "fail", "major",
                "Unit %r is not one of mm/mil/inch." % unknown_unit,
                obj=designator, file=file, line=line, actual=unknown_unit))
            row_finding_lines.add(line)
            unit_problem_any = True
        if unit is None:
            unresolved_unit_lines.append(line)
        else:
            used_units.add(unit)
            if unit_source == "header":
                used_header_unit = True
            elif unit_source == "declared":
                used_declared_unit = True

        x_mm = None
        y_mm = None
        if unit is not None:
            factor = _UNIT_FACTORS[unit]
            if x is not None:
                x_mm = x * factor
            if y is not None:
                y_mm = y * factor

        side = None
        if side_column is not None:
            side_text = cell_text(record, side_column).strip()
            if not side_text:
                findings.append(finding(
                    "cpl.side_unknown", "fail", "major",
                    "CPL side/layer cell is empty.", obj=designator,
                    file=file, line=line))
                row_finding_lines.add(line)
            else:
                side = _SIDE_MAP.get(side_text.casefold())
                if side is None:
                    findings.append(finding(
                        "cpl.side_unknown", "fail", "major",
                        "Side %r is not one of top/bottom/T/B/back/front."
                        % side_text,
                        obj=designator, file=file, line=line,
                        actual=side_text))
                    row_finding_lines.add(line)

        rotation = None
        rotation_norm = None
        rotation_raw = None
        if rotation_column is not None:
            rotation_text = cell_text(record, rotation_column).strip()
            rotation_raw = rotation_text
            rotation, problem = parse_number(rotation_text)
            if problem is not None:
                findings.append(finding(
                    "cpl.rotation_not_numeric", "fail", "major",
                    "Rotation %r is not a finite number (%s)."
                    % (rotation_text, problem),
                    obj=designator, file=file, line=line,
                    actual=rotation_text))
                row_finding_lines.add(line)
            else:
                rotation_norm = rotation % 360.0

        rows.append({
            "line": line,
            "designator": designator,
            "x": x,
            "y": y,
            "unit": unit,
            "x_mm": x_mm,
            "y_mm": y_mm,
            "side": side,
            "rotation": rotation,
            "rotation_norm": rotation_norm,
            "rotation_raw": rotation_raw,
        })
        counts["sides"]["top" if side == "top"
                        else "bottom" if side == "bottom"
                        else "unknown"] += 1
        counts["by_unit"][unit if unit in _UNIT_FACTORS
                          else "unknown"] += 1

    if unresolved_unit_lines and not unit_problem_any and not unit_problem_emitted:
        all_missing = len(unresolved_unit_lines) == len(rows)
        findings.append(finding(
            "cpl.unit_missing", "fail", "blocking" if all_missing else "major",
            "No unit could be determined for %d placement(s); coordinates "
            "cannot be normalized and are not judged correct."
            % len(unresolved_unit_lines),
            file=file,
            evidence={"count": len(unresolved_unit_lines),
                      "rows": unresolved_unit_lines[:MAX_EVIDENCE_ITEMS]}))

    observed_units = sorted(used_units)
    if len(observed_units) == 1:
        facts["units"] = observed_units[0]
    elif observed_units:
        facts["units"] = observed_units
    else:
        facts["units"] = None
    if used_header_unit:
        facts["unit_source"] = "header"
    elif used_declared_unit:
        facts["unit_source"] = "declared"
    else:
        facts["unit_source"] = None

    counts["rows"] = len(rows)
    counts["unique_designators"] = len(seen)
    counts["rows_with_findings"] = len(row_finding_lines)
    return _build_result(file, facts, capability, findings)
