"""BOM parsing for the offline delivery audit (contract §7.3).

The parser reads exported BOM bytes and returns the contract shape
``{kind, file, status, facts, capability, findings}``.  It never writes files,
never reaches the network and never raises on malformed content (only caller
programming errors such as a non-bytes payload or an unknown options value raise
``ValueError``).

Policy decisions (documented so a reviewer does not have to infer them):

* Encoding: default ``utf-8-sig`` (a UTF-8 BOM is accepted).  An explicit
  ``options['encoding']`` is validated with :func:`codecs.lookup`; an unknown
  codec name is a caller error.  Undecodable bytes are a content problem and are
  reported as ``bom.encoding_unspecified`` (fail); decoding never uses
  ``errors='replace'``, so no U+FFFD characters are invented.
* Delimiter: ``options['delimiter']`` wins; otherwise the first non-empty line is
  sniffed deterministically among ``,``, ``;`` and tab (counts outside quotes).
  A tie is ambiguous: comma is assumed and ``bom.delimiter_ambiguous`` is
  reported as unknown.  The CSV module handles quoting and embedded newlines.
* Column aliases ignore case, whitespace, underscores, hyphens and brackets and
  are exactly the documented ones (contract §7.3).
* Designators: comma/semicolon/whitespace separated lists plus same-prefix
  ascending ranges ``R1-R3`` and ``R1-3``.  Anything else is reported (a
  finding); vendor-specific formats are never guessed.
* DNP accepts only ``1/0/true/false/yes/no/y/n`` (case-insensitive; empty means
  not DNP).  Assembly accepts only ``smt/tht/hand/mechanical/dnp``.
* Severity policy: ``blocking`` for a file that cannot be used at all (empty,
  undecodable, no designator column), ``major`` for definite row/column data
  violations, ``minor`` for checks that stay ``unknown`` (ambiguous delimiter,
  resource limit).  The returned ``status`` is ``fail`` if any fail finding
  exists, else ``unknown`` if any unknown finding exists, else ``pass``.

Other delivery-audit modules (``cpl.py``) reuse the generic CSV helpers defined
here (:func:`resolve_encoding`, :func:`resolve_delimiter`, :func:`decode_bytes`,
:func:`resolve_limit`, :func:`resolve_required_fields`, :func:`normalize_header`,
:func:`map_columns`, :func:`aggregate_status`, :func:`cell_text`, :func:`text_of`).
"""

from __future__ import annotations

import codecs
import csv
import io
import re

from .model import finding

DEFAULT_ENCODING = "utf-8-sig"
DEFAULT_MAX_ROWS = 100000
DEFAULT_REQUIRED_FIELDS = ("designator", "quantity")

MAX_RANGE_EXPANSION = 10000
MAX_EVIDENCE_ITEMS = 50

DELIMITER_CANDIDATES = (",", ";", "\t")

BOM_FIELDS = (
    "designator",
    "quantity",
    "value",
    "footprint",
    "mpn",
    "manufacturer",
    "lcsc",
    "dnp",
    "assembly",
    "side",
)

# Documented aliases (contract §7.3).  Matching ignores case, spaces,
# underscores, hyphens and brackets; Chinese aliases are those used by the
# accepted export tools.
_BOM_ALIASES = {
    "designator": ("designator", "designators", "ref", "refs", "reference",
                   "references", "位号"),
    "quantity": ("quantity", "qty", "数量"),
    "value": ("value", "comment", "值"),
    "footprint": ("footprint", "package", "封装"),
    "mpn": ("mpn", "manufacturer part number", "型号"),
    "manufacturer": ("manufacturer", "厂商"),
    "lcsc": ("lcsc", "supplier part", "C号"),
    "dnp": ("dnp", "do not populate", "不贴"),
    "assembly": ("assembly", "装配"),
    "side": ("side", "layer", "面"),
}

DNP_TRUE = frozenset(("1", "true", "yes", "y"))
DNP_FALSE = frozenset(("0", "false", "no", "n"))
ASSEMBLY_TYPES = ("smt", "tht", "hand", "mechanical", "dnp")

DESIGNATOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
QUANTITY_RE = re.compile(r"^[0-9]+$")
_RANGE_RE = re.compile(r"^([A-Za-z_]+)([0-9]+)-([A-Za-z_]*)([0-9]+)$")

BOM_CAPABILITY = {
    "supported": (
        "csv_utf8_bom",
        "declared_encoding",
        "declared_delimiter",
        "delimiter_sniff",
        "csv_quotes_newlines",
        "column_aliases",
        "designator_lists",
        "designator_ranges_same_prefix",
        "dnp_strict_truth_values",
        "assembly_types",
    ),
    "unsupported": (
        "xlsx_bom",
        "vendor_complex_designator_formats",
        "nested_bom",
        "alternative_parts",
        "implicit_quantity",
    ),
    "unknown": (),
}


# ---------------------------------------------------------------------------
# Generic options / CSV helpers (also used by cpl.py)


def options_as_dict(options):
    """Return ``options`` as a dict; ``None`` means no options."""
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise ValueError("options must be a dict or None")
    return options


def normalize_header(text):
    """Canonical header key: ignore case/space/underscore/hyphen/brackets."""
    return re.sub(r"[\s_\-()\[\]]+", "", str(text)).casefold()


def resolve_encoding(options=None, default=DEFAULT_ENCODING):
    """Resolve the decode codec; unknown declared names are a caller error."""
    declared = options_as_dict(options).get("encoding")
    if declared is None:
        return default, "default"
    if not isinstance(declared, str) or not declared.strip():
        raise ValueError("options['encoding'] must be a non-empty string")
    try:
        codec = codecs.lookup(declared.strip())
    except (LookupError, TypeError):
        raise ValueError("unknown encoding declared: %r" % (declared,))
    return codec.name, "declared"


def decode_bytes(data, encoding):
    """Decode bytes strictly.  Returns ``(text, error_message_or_None)``."""
    try:
        text = data.decode(encoding)
    except UnicodeError as exc:
        return None, str(exc)
    except LookupError:  # defensive: resolve_encoding already validated
        return None, "unknown encoding %r" % (encoding,)
    if text.startswith("\ufeff"):
        text = text[1:]
    return text, None


def resolve_limit(options, key="max_rows", default=DEFAULT_MAX_ROWS):
    value = options_as_dict(options).get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("options[%r] must be a positive integer" % (key,))
    return value


def resolve_required_fields(options, allowed, default=DEFAULT_REQUIRED_FIELDS):
    raw = options_as_dict(options).get("required_fields")
    if raw is None:
        return list(default)
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise ValueError("options['required_fields'] must be a list of field names")
    result = []
    for name in raw:
        if not isinstance(name, str):
            raise ValueError("options['required_fields'] must contain strings")
        key = name.strip().casefold()
        if key not in allowed:
            raise ValueError("unknown required field: %r" % (name,))
        if key not in result:
            result.append(key)
    return result


def first_non_empty_line(text):
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


def count_delimiters(line):
    """Count candidate delimiters outside double-quoted spans."""
    counts = {candidate: 0 for candidate in DELIMITER_CANDIDATES}
    in_quotes = False
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if in_quotes:
            if char == '"':
                if index + 1 < length and line[index + 1] == '"':
                    index += 2
                    continue
                in_quotes = False
            index += 1
            continue
        if char == '"':
            in_quotes = True
            index += 1
            continue
        if char in counts:
            counts[char] += 1
        index += 1
    return counts


def sniff_delimiter(text):
    """Return ``(delimiter, counts, ambiguous)`` for the first non-empty line."""
    counts = count_delimiters(first_non_empty_line(text))
    best = max(counts.values())
    if best == 0:
        return ",", counts, False
    winners = [candidate for candidate in DELIMITER_CANDIDATES
               if counts[candidate] == best]
    if len(winners) > 1:
        return ",", counts, True
    return winners[0], counts, False


def resolve_delimiter(options, text):
    """Return ``(delimiter, source, ambiguous_counts_or_None)``."""
    declared = options_as_dict(options).get("delimiter")
    if declared is not None:
        if (not isinstance(declared, str) or len(declared) != 1
                or declared in "\r\n"):
            raise ValueError(
                "options['delimiter'] must be a single non-newline character")
        return declared, "declared", None
    delimiter, counts, ambiguous = sniff_delimiter(text)
    return delimiter, "sniffed", (counts if ambiguous else None)


def cell_text(record, index):
    """Return a CSV cell as text (missing cells are empty)."""
    if index is None or index < 0 or index >= len(record):
        return ""
    value = record[index]
    return value if isinstance(value, str) else str(value)


def text_of(record, index):
    """Return a stripped cell, or ``None`` when empty/missing."""
    value = cell_text(record, index).strip()
    return value or None


def map_columns(header_cells, aliases):
    """Map field -> column index using the documented aliases.

    The first matching column for a field wins; later duplicates are recorded in
    ``ignored_columns`` so the mapping stays deterministic and reviewable.
    """
    lookup = {}
    for field_name, names in aliases.items():
        for name in names:
            lookup.setdefault(normalize_header(name), field_name)
    mapping = {}
    raw_mapping = {}
    ignored = []
    unrecognized = []
    for index, cell in enumerate(header_cells):
        cell = str(cell)
        field_name = lookup.get(normalize_header(cell))
        if field_name is None:
            unrecognized.append(cell)
        elif field_name in mapping:
            ignored.append(cell)
        else:
            mapping[field_name] = index
            raw_mapping[field_name] = cell.strip()
    return mapping, raw_mapping, ignored, unrecognized


def aggregate_status(findings):
    """Contract §7 status aggregation for a parse/cross-check result."""
    if any(item.get("status") == "fail" for item in findings):
        return "fail"
    if any(item.get("status") == "unknown" for item in findings):
        return "unknown"
    return "pass"


def copy_capability(capability):
    return {key: list(value) for key, value in capability.items()}


# ---------------------------------------------------------------------------
# BOM-specific helpers


def parse_designator_cell(raw):
    """Expand one designator cell.

    Returns ``(designators, rule, problems)`` where ``rule`` is one of
    ``single``/``list``/``range``/``list_range``/``invalid`` and ``problems`` is
    a list of ``(rule_id, token, reason)`` tuples.  The caller reports the
    problems; no vendor-specific syntax is guessed here.
    """
    text = raw.strip() if isinstance(raw, str) else ""
    tokens = [token for token in re.split(r"[,;\s]+", text) if token]
    if not tokens:
        return [], "invalid", []
    designators = []
    problems = []
    saw_range = False
    for token in tokens:
        match = _RANGE_RE.match(token)
        if match:
            prefix = match.group(1)
            start_text = match.group(2)
            second_prefix = match.group(3)
            end_text = match.group(4)
            if second_prefix and second_prefix != prefix:
                problems.append((
                    "bom.designator_range_invalid", token,
                    "range endpoints use different prefixes"))
                continue
            start = int(start_text)
            end = int(end_text)
            if end < start:
                problems.append((
                    "bom.designator_range_invalid", token,
                    "descending ranges are not expanded"))
                continue
            if end - start + 1 > MAX_RANGE_EXPANSION:
                problems.append((
                    "bom.designator_range_invalid", token,
                    "range larger than the supported expansion limit"))
                continue
            width = len(start_text) if (len(start_text) > 1
                                        and start_text.startswith("0")) else 0
            for number in range(start, end + 1):
                if width:
                    designators.append("%s%0*d" % (prefix, width, number))
                else:
                    designators.append("%s%d" % (prefix, number))
            saw_range = True
        elif "-" in token:
            problems.append((
                "bom.designator_range_invalid", token,
                "unrecognized range syntax"))
        elif DESIGNATOR_RE.match(token):
            designators.append(token)
        else:
            problems.append((
                "bom.designator_missing_invalid", token,
                "unrecognized designator token"))
    if problems:
        rule = "invalid"
    elif saw_range and len(tokens) > 1:
        rule = "list_range"
    elif saw_range:
        rule = "range"
    elif len(tokens) > 1:
        rule = "list"
    else:
        rule = "single"
    return designators, rule, problems


def _build_result(file, facts, capability, findings):
    return {
        "kind": "bom",
        "file": file,
        "status": aggregate_status(findings),
        "facts": facts,
        "capability": capability,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Public parser


def parse_bom(data, file, options=None):
    """Parse BOM bytes into the contract §7.3 result.  Never raises on content."""
    file = str(file)
    options = options_as_dict(options)

    # Caller/option validation (programming errors, not content problems).
    encoding, encoding_source = resolve_encoding(options)
    max_rows = resolve_limit(options, "max_rows", DEFAULT_MAX_ROWS)
    required_fields = resolve_required_fields(
        options, BOM_FIELDS, DEFAULT_REQUIRED_FIELDS)

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("data must be bytes-like")
    payload = bytes(data)

    findings = []
    rows = []
    counts = {
        "rows": 0,
        "designator_occurrences": 0,
        "unique_designators": 0,
        "dnp_designators": 0,
        "rows_with_findings": 0,
        "assembly": {name: 0 for name in
                     ("smt", "tht", "hand", "mechanical", "dnp",
                      "missing", "unknown")},
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
        "row_limit": max_rows,
        "rows_truncated": False,
        "rows": rows,
        "counts": counts,
    }
    capability = copy_capability(BOM_CAPABILITY)

    if not payload:
        findings.append(finding(
            "bom.empty", "fail", "blocking",
            "BOM file has no bytes; export the BOM again and audit the new file.",
            file=file))
        return _build_result(file, facts, capability, findings)

    text, decode_error = decode_bytes(payload, encoding)
    if text is None:
        findings.append(finding(
            "bom.encoding_unspecified", "fail", "blocking",
            "BOM bytes are not valid %s and were not decoded with replacement "
            "characters; declare the BOM encoding explicitly "
            "(declarations encodings.bom)." % encoding,
            file=file,
            actual=encoding,
            evidence={"decoder_error": decode_error,
                      "encoding_source": encoding_source},
            suggestion="declare the BOM encoding in the delivery declarations"))
        return _build_result(file, facts, capability, findings)

    if not text.strip():
        findings.append(finding(
            "bom.empty", "fail", "blocking",
            "BOM file contains only whitespace.", file=file))
        return _build_result(file, facts, capability, findings)

    try:
        delimiter, delimiter_source, ambiguous_counts = resolve_delimiter(
            options, text)
    except ValueError:
        raise
    facts["delimiter"] = delimiter
    facts["delimiter_source"] = delimiter_source
    if ambiguous_counts is not None:
        findings.append(finding(
            "bom.delimiter_ambiguous", "unknown", "minor",
            "The first non-empty BOM line matches several delimiters equally; "
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
                "bom.row_invalid", "fail", "major",
                "BOM CSV could not be read: %s" % csv_error["message"],
                file=file, line=csv_error["line"],
                evidence={"csv_error": csv_error["message"]}))
        else:
            findings.append(finding(
                "bom.empty", "fail", "blocking",
                "BOM contains no non-empty line (no header found).", file=file))
        return _build_result(file, facts, capability, findings)

    facts["header"] = header
    facts["header_line"] = header_line
    mapping, raw_mapping, ignored, unrecognized = map_columns(
        header, _BOM_ALIASES)
    facts["header_mapping"] = raw_mapping
    facts["ignored_columns"] = ignored
    facts["unrecognized_columns"] = unrecognized
    facts["header_aliases"] = {field: list(names)
                               for field, names in _BOM_ALIASES.items()}

    if csv_error is not None:
        findings.append(finding(
            "bom.row_invalid", "fail", "major",
            "BOM CSV could not be read after row %d: %s; later rows are not "
            "reliable." % (csv_error["line"], csv_error["message"]),
            file=file, line=csv_error["line"],
            evidence={"csv_error": csv_error["message"]}))

    if "designator" not in mapping:
        findings.append(finding(
            "bom.no_designator_column", "fail", "blocking",
            "BOM has no designator column; supported aliases: %s."
            % ", ".join(_BOM_ALIASES["designator"]),
            file=file,
            expected="designator",
            evidence={"header": header}))
        return _build_result(file, facts, capability, findings)

    for field_name in required_fields:
        if field_name == "designator":
            continue
        if field_name not in mapping:
            findings.append(finding(
                "bom.required_field_missing", "fail", "major",
                "Required BOM column %r is missing; supported aliases: %s."
                % (field_name, ", ".join(_BOM_ALIASES[field_name])),
                obj=field_name, file=file,
                expected=field_name,
                evidence={"header": header}))
    if not data_records:
        findings.append(finding(
            "bom.empty", "fail", "blocking",
            "BOM has a header but no data rows.", file=file, line=header_line))
        return _build_result(file, facts, capability, findings)

    if truncated:
        facts["rows_truncated"] = True
        findings.append(finding(
            "bom.limit_rows", "unknown", "minor",
            "BOM has more than the configured %d data rows; parsing stopped at "
            "the resource limit, so later rows were not audited." % max_rows,
            file=file,
            evidence={"max_rows": max_rows}))

    designator_column = mapping["designator"]
    quantity_column = mapping.get("quantity")
    dnp_column = mapping.get("dnp")
    assembly_column = mapping.get("assembly")
    required_row_fields = [field_name for field_name in required_fields
                           if field_name not in ("designator", "quantity")]
    seen = {}
    assembly_counts = counts["assembly"]
    row_finding_lines = set()
    total_designators = 0
    dnp_designators = 0
    for line, record in data_records:
        designator_raw = cell_text(record, designator_column)
        designators, designator_rule, problems = parse_designator_cell(
            designator_raw)
        for rule_id, token, reason in problems:
            findings.append(finding(
                rule_id, "fail", "major",
                "Designator token %r in %r cannot be expanded (%s); "
                "vendor-specific formats are not guessed."
                % (token, designator_raw, reason),
                obj=token, file=file, line=line, actual=token,
                evidence={"designator_raw": designator_raw, "reason": reason}))
            row_finding_lines.add(line)
        if not designators and not problems:
            findings.append(finding(
                "bom.designator_missing_invalid", "fail", "major",
                "BOM row has no designator.", file=file, line=line,
                actual=designator_raw,
                evidence={"designator_raw": designator_raw}))
            row_finding_lines.add(line)
        for designator in designators:
            first_line = seen.get(designator)
            if first_line is not None:
                findings.append(finding(
                    "bom.designator_duplicate", "fail", "major",
                    "Designator %r appears more than once in the BOM."
                    % designator,
                    obj=designator, file=file, line=line,
                    evidence={"first_line": first_line}))
                row_finding_lines.add(line)
            else:
                seen[designator] = line
        total_designators += len(designators)

        quantity = None
        if quantity_column is not None:
            quantity_text = cell_text(record, quantity_column).strip()
            if QUANTITY_RE.match(quantity_text) and int(quantity_text) > 0:
                quantity = int(quantity_text)
            else:
                findings.append(finding(
                    "bom.quantity_invalid", "fail", "major",
                    "Quantity %r is not a positive integer." % quantity_text,
                    file=file, line=line, actual=quantity_text))
                row_finding_lines.add(line)
        if (quantity is not None and designators and not problems
                and quantity != len(designators)):
            findings.append(finding(
                "bom.quantity_mismatch", "fail", "major",
                "Quantity %d does not match %d expanded designator(s)."
                % (quantity, len(designators)),
                file=file, line=line, actual=quantity,
                expected=len(designators),
                evidence={"designators": designators[:MAX_EVIDENCE_ITEMS],
                          "designator_raw": designator_raw}))
            row_finding_lines.add(line)

        dnp = False
        if dnp_column is not None:
            dnp_text = cell_text(record, dnp_column).strip()
            if dnp_text:
                dnp_key = dnp_text.casefold()
                if dnp_key in DNP_TRUE:
                    dnp = True
                elif dnp_key in DNP_FALSE:
                    dnp = False
                else:
                    findings.append(finding(
                        "bom.dnp_invalid", "fail", "major",
                        "DNP value %r is not one of 1/0/true/false/yes/no/y/n."
                        % dnp_text,
                        file=file, line=line, actual=dnp_text))
                    row_finding_lines.add(line)
                    dnp = None

        assembly_type = None
        assembly_raw = ""
        if assembly_column is not None:
            assembly_raw = cell_text(record, assembly_column).strip()
            if assembly_raw:
                assembly_key = assembly_raw.casefold()
                if assembly_key in ASSEMBLY_TYPES:
                    assembly_type = assembly_key
                else:
                    findings.append(finding(
                        "bom.assembly_unknown", "unknown", "minor",
                        "Assembly type %r is not one of "
                        "smt/tht/hand/mechanical/dnp." % assembly_raw,
                        file=file, line=line, actual=assembly_raw))
                    row_finding_lines.add(line)
        if assembly_type is None:
            assembly_counts["unknown" if assembly_raw else "missing"] += 1
        else:
            assembly_counts[assembly_type] += 1

        for field_name in required_row_fields:
            index = mapping.get(field_name)
            if index is None:
                continue
            if not cell_text(record, index).strip():
                findings.append(finding(
                    "bom.required_field_missing", "fail", "major",
                    "Required BOM field %r is empty." % field_name,
                    obj=field_name, file=file, line=line,
                    expected=field_name))
                row_finding_lines.add(line)

        rows.append({
            "line": line,
            "designator_raw": designator_raw,
            "designators": designators,
            "designator_rule": designator_rule,
            "quantity": quantity,
            "dnp": dnp,
            "assembly": assembly_type,
            "value": text_of(record, mapping.get("value")),
            "footprint": text_of(record, mapping.get("footprint")),
            "mpn": text_of(record, mapping.get("mpn")),
            "manufacturer": text_of(record, mapping.get("manufacturer")),
            "lcsc": text_of(record, mapping.get("lcsc")),
            "side": text_of(record, mapping.get("side")),
        })
        if dnp is True:
            dnp_designators += len(designators)

    counts["rows"] = len(rows)
    counts["designator_occurrences"] = total_designators
    counts["unique_designators"] = len(seen)
    counts["dnp_designators"] = dnp_designators
    counts["rows_with_findings"] = len(row_finding_lines)
    return _build_result(file, facts, capability, findings)
