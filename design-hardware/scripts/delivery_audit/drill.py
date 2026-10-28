"""Bounded, offline Excellon/NC drill parser (not a Gerber image parser).

The parser is a two-phase line/state machine: an ``M48`` header section declares
units, coordinate format and the tool table, then the body selects tools and
emits ``X``/``Y`` holes until ``M30``.  It returns the JSON-ready contract
dictionary (``kind``/``file``/``status``/``facts``/``capability``/``findings``)
from ``docs/parallel-delivery-audit/contract.md`` section 7.2.

Supported subset
----------------

* ``M48`` header, ``METRIC`` / ``INCH`` units (optional ``,TZ`` or ``,LZ`` zero
  suppression suffix, legacy ``M71``/``M72`` accepted), ``FMAT`` and benign
  header parameters;
* header tool table ``TnCd`` (diameter) and ``T`` tool selection in the body;
* ``%`` or ``M95`` header terminator;
* ``X``/``Y`` holes with explicit decimal coordinates, or integer coordinates
  when the header declares both the digit format and the zero suppression;
* modal axes (a line may carry only X or only Y);
* ``M30`` (``M00`` accepted) end of program, ``G90`` absolute mode and ``G05``
  drill mode;
* ``T0`` deselects the current tool.

Coordinate handling and zero suppression
----------------------------------------

A coordinate containing a decimal point is used as-is in the declared unit.
An integer coordinate is only interpreted when BOTH are known from the header:
the digit format (for example ``;FORMAT={2:4/ ...}``) and the zero suppression
(``METRIC,TZ`` / ``METRIC,LZ``).  ``TZ`` means trailing zeros are suppressed:
the digit string is padded on the right to ``integer_digits + decimal_digits``
before the implied decimal point is applied.  ``LZ`` means leading zeros are
suppressed: the digit string is used directly (its right-most
``decimal_digits`` positions are the fraction).  If either piece is missing the
file gets ``drill.coordinate_unknown_format`` (unknown) and no position is
guessed.

Explicitly unsupported (always an ``unknown`` finding, never a ``pass``)
-----------------------------------------------------------------------

``G85`` slots, ``M15``/``M16``/``M17`` routing (tool down/up) and routing moves
``G00``/``G01``, repeat holes (``Rnn``), incremental coordinates (``G91``),
integer coordinates without a determinable format, and unknown body commands.
Undefined tool references, non-positive tool diameters, missing units, a
missing/truncated header or end marker, no holes, invalid coordinates and the
object budget are failures (``fail``), not unknowns.

``facts`` shape
---------------

``units``, ``format`` (mode/digits/zero suppression), ``header``,
``end_of_file``, ``tool_count``, ``hole_count``, ``slots``, ``routing``,
``tools``, ``undefined_tools``, ``duplicate_tools``, ``extent`` (mm, hole
centres expanded by tool radius, with ``exact`` and ``basis``) and
``unsupported``.

Options
-------

``options`` is ``None`` or a dict.  ``max_objects`` (alias ``max_tokens``)
overrides the default 2,000,000 line/object budget.  On exhaustion the parser
stops cleanly with a ``drill.limit_objects`` unknown finding.

Content problems never raise; only wrong argument types or invalid option
values raise ``ValueError``.  Input is ``bytes`` only; no I/O is performed.
"""

from __future__ import annotations

import math
import re

from .model import finding, sort_findings

KIND = "drill"
DEFAULT_MAX_OBJECTS = 2_000_000

_SUPPORTED = [
    "M48 header and %/M95 header terminator",
    "METRIC/INCH units with optional TZ/LZ declaration",
    "header tool table TnCd and body T tool selection",
    "X/Y holes with explicit decimal coordinates",
    "integer coordinates when header format digits and zero suppression are declared",
    "M30/M00 end of program",
    "G90 absolute and G05 drill mode",
    "modal X/Y axes",
    "object budget with drill.limit_objects unknown finding",
]

_UNSUPPORTED = [
    "G85 slots",
    "M15/M16/M17 routing and G00/G01 routing moves",
    "repeat holes (Rnn)",
    "incremental coordinates (G91)",
    "integer coordinates without a determinable format",
    "unknown body commands",
]

_TOOL_DEF = re.compile(
    r"^T\s*(\d+)\s*C\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$", re.IGNORECASE)
_TOOL_SELECT = re.compile(r"^T\s*(\d+)\s*$", re.IGNORECASE)
_UNIT_LINE = re.compile(
    r"^(METRIC|INCH)\s*(?:,\s*([A-Za-z]+))?\s*$", re.IGNORECASE)
_FORMAT_DIGITS = re.compile(
    r"(?:FILE_)?FORMAT\s*=\s*\{?\s*(\d+)\s*:\s*(\d+)", re.IGNORECASE)
_TOKEN = re.compile(r"([A-Za-z])([+-]?(?:\d+(?:\.\d*)?|\.\d+)?)")
_BODY_ROUTING = re.compile(r"(?<![0-9])G0?[01](?![0-9])")
_REPEAT = re.compile(r"^R\s*\d+\s*$", re.IGNORECASE)

_END_MARKERS = ("M30", "M00", "M02")
_HEADER_END = ("%", "M95")


def _base_facts():
    return {
        "units": None,
        "format": None,
        "header": {"present": False},
        "end_of_file": False,
        "tool_count": 0,
        "hole_count": 0,
        "slots": 0,
        "routing": 0,
        "tools": [],
        "undefined_tools": [],
        "duplicate_tools": [],
        "extent": None,
        "unsupported": [],
    }


def _validate_arguments(data, file, options):
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("data must be bytes")
    if not isinstance(file, str):
        raise ValueError("file must be a logical path string")
    if options is not None and not isinstance(options, dict):
        raise ValueError("options must be a dict or None")
    limits = []
    opts = options or {}
    for key in ("max_objects", "max_tokens"):
        if key in opts:
            value = opts[key]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("options[%r] must be a positive integer" % key)
            limits.append(value)
    return min(limits) if limits else DEFAULT_MAX_OBJECTS


def _result(file, facts, findings, capability_unknown=()):
    findings = sort_findings(findings)
    if any(item["status"] == "fail" for item in findings):
        status = "fail"
    elif any(item["status"] == "unknown" for item in findings):
        status = "unknown"
    else:
        status = "pass"
    return {
        "kind": KIND,
        "file": file,
        "status": status,
        "facts": facts,
        "capability": {
            "supported": list(_SUPPORTED),
            "unsupported": list(_UNSUPPORTED),
            "unknown": sorted(set(capability_unknown)),
        },
        "findings": findings,
    }


class _DrillState:
    """Excellon header/body state machine."""

    def __init__(self, text, file, max_objects, encoding):
        self.text = text
        self.file = file
        self.max_objects = max_objects
        self.encoding = encoding
        self.findings = []
        self._finding_keys = set()
        self.errors = []
        self.unsupported = []
        self.capability_unknown = set()

        # header state
        self.header_seen = False
        self.header_terminated_by = None
        self.header_line_count = 0
        self.header_unknown = []
        self.format_hint = None
        self.format_int = None
        self.format_dec = None
        self.units = None
        self.units_declared = False
        self.units_invalid = False
        self.zeros = None

        # tools
        self.tools = {}
        self.duplicate_tools = set()
        self.referenced_tools = set()
        self.current_tool = None
        self.holes_without_tool = 0

        # body state
        self.absolute = True
        self.incremental = False
        self.drill_mode = True
        self.end_of_file = False
        self.truncated = False
        self.header_missing = False
        self.limit_exceeded = False
        self.tokens = 0
        self.hole_count = 0
        self.slots = 0
        self.routing = 0
        self.last_x = None
        self.last_y = None
        self.coordinate_mode = None
        self.coordinate_unknown_reported = False
        self.coordinate_invalid_reported = False

        # extent bookkeeping (raw file units)
        self.exp_min_x = None
        self.exp_min_y = None
        self.exp_max_x = None
        self.exp_max_y = None
        self.geometry_exact = True
        self.positions_seen = False
        self.ends_with_newline = text.endswith(("\n", "\r"))
        self.last_line_suspect = False

    # -- findings ---------------------------------------------------------

    def _add(self, rule_id, status, severity, message, *, key=None, line=None,
             obj=None, actual=None, expected=None, unit=None, evidence=None,
             suggestion=None):
        identity = (rule_id, key if key is not None else "")
        if identity in self._finding_keys:
            return
        self._finding_keys.add(identity)
        self.findings.append(finding(
            rule_id, status, severity, message,
            obj=obj, file=self.file, line=line, actual=actual, expected=expected,
            unit=unit, evidence=evidence, suggestion=suggestion,
        ))

    def _error(self, line, message):
        if len(self.errors) < 200:
            self.errors.append({"line": line, "message": message})

    def _unsupported(self, feature, line, detail=None):
        if feature not in self.unsupported:
            self.unsupported.append(feature)
        self.geometry_exact = False
        evidence = {"feature": feature}
        if detail:
            evidence["detail"] = str(detail)[:120]
        self._add(
            "drill.unsupported." + feature, "unknown", "major",
            "unsupported drill feature %r; geometry coverage is not claimed" % feature,
            key=feature, line=line, evidence=evidence,
        )

    def _limit_reached(self, line):
        self.limit_exceeded = True
        self._add(
            "drill.limit_objects", "unknown", "major",
            "line/object budget of %d exceeded; the file was not fully parsed"
            % self.max_objects,
            key="limit", line=line, actual=self.max_objects, unit="objects",
            evidence={"limit": self.max_objects, "parsed": self.tokens},
        )

    def _bump(self, line):
        self.tokens += 1
        if self.tokens > self.max_objects:
            self._limit_reached(line)
            return False
        return True

    # -- run --------------------------------------------------------------

    def run(self):
        lines = self.text.splitlines()
        header_index = None
        for index, raw in enumerate(lines):
            stripped = raw.strip()
            # Leading blank lines, ';' comments and '%' rewind lines are
            # tolerated before M48 (Eagle ncdrill exports start with '%').
            if not stripped or stripped.startswith(";") or stripped == "%":
                continue
            if stripped.upper() == "M48":
                header_index = index
            break
        if header_index is None:
            self.header_missing = True
            self._add(
                "drill.header_missing", "fail", "blocking",
                "no M48 Excellon header was found", key="header",
            )
            return _result(self.file, self._build_facts(), self.findings,
                           self.capability_unknown)

        self.header_seen = True
        header_end = None
        for index in range(header_index + 1, len(lines)):
            if lines[index].strip().upper() in _HEADER_END:
                header_end = index
                self.header_terminated_by = (
                    "%" if lines[index].strip() == "%" else "M95")
                break
        if header_end is None:
            self.truncated = True
            self._add(
                "drill.truncated", "fail", "blocking",
                "file ends inside the M48 header (no %/M95 header terminator)",
                key="truncated",
            )
            return _result(self.file, self._build_facts(), self.findings,
                           self.capability_unknown)

        self.header_line_count = header_end - header_index - 1
        for index in range(header_index + 1, header_end):
            if not self._bump(index + 1):
                break
            self._header_line(lines[index], index + 1)

        for index in range(header_end + 1, len(lines)):
            if self.end_of_file or self.limit_exceeded:
                break
            if not self._bump(index + 1):
                break
            self._body_line(lines[index], index + 1)

        if (self.last_line_suspect and not self.ends_with_newline
                and not self.end_of_file and not self.limit_exceeded):
            # The final body line ends mid-token (no trailing newline): treat the
            # file as truncated rather than inventing a complete command.
            self.truncated = True
            self._add(
                "drill.truncated", "fail", "blocking",
                "file ends inside an incomplete body command", key="truncated",
            )
        self._finalize()
        return _result(self.file, self._build_facts(), self.findings,
                       self.capability_unknown)

    # -- header -----------------------------------------------------------

    def _header_line(self, raw, line):
        stripped = raw.strip()
        if stripped.startswith(";"):
            self._parse_comment_hint(stripped, line)
            return
        text = raw.split(";", 1)[0].strip()
        if not text:
            return
        upper = text.upper()
        if upper == "M48":
            return
        if upper in ("%", "M95"):
            return
        unit_match = _UNIT_LINE.match(text)
        if unit_match:
            self._set_units(unit_match.group(1), unit_match.group(2), line)
            return
        if upper == "M71":
            self._set_units("METRIC", None, line)
            return
        if upper == "M72":
            self._set_units("INCH", None, line)
            return
        if upper.startswith("FMAT"):
            self.format_hint = text
            return
        tool_match = _TOOL_DEF.match(text)
        if tool_match:
            self._define_tool(int(tool_match.group(1)), tool_match.group(2), line)
            return
        select_match = _TOOL_SELECT.match(text)
        if select_match:
            self.current_tool = int(select_match.group(1))
            return
        known_prefixes = ("VER", "DETECT", "ICI", "R,", "S,", "M47", "TCST",
                          "ATC", "FILE_FORMAT", "TYPE", "UNITS")
        if upper.startswith(known_prefixes):
            self._parse_comment_hint(text, line)
            return
        self.header_unknown.append(text[:120])
        self.capability_unknown.add(text.split(",")[0].upper()[:24])

    def _parse_comment_hint(self, text, line):
        # Only the numeric format is taken from comments.  A comment such as
        # ";FORMAT={-:-/ absolute / metric / decimal}" lists all possible modes
        # and is NOT a units declaration; units must come from METRIC/INCH.
        match = _FORMAT_DIGITS.search(text)
        if match and self.format_int is None:
            self.format_int = int(match.group(1))
            self.format_dec = int(match.group(2))

    def _set_units(self, declaration, suffix, line):
        self.units_declared = True
        unit = "mm" if declaration.upper().startswith("METRIC") else "inch"
        if suffix:
            zero = suffix.strip().upper()
            if zero in ("TZ", "LZ"):
                if self.zeros is not None and self.zeros != zero:
                    self.units_invalid = True
                    self._add(
                        "drill.units_invalid", "fail", "blocking",
                        "conflicting zero-suppression declarations (%s vs %s)"
                        % (self.zeros, zero),
                        key="zero", line=line,
                    )
                self.zeros = zero
            else:
                self.units_invalid = True
                self._add(
                    "drill.units_invalid", "fail", "blocking",
                    "unrecognised units suffix %r" % suffix,
                    key="suffix", line=line, evidence={"declaration": declaration},
                )
        if self.units is None:
            self.units = unit
        elif self.units != unit:
            self.units_invalid = True
            self._add(
                "drill.units_invalid", "fail", "blocking",
                "units are declared more than once with different values",
                key="mixed", line=line, actual=unit, expected=self.units,
            )

    def _define_tool(self, code, diameter_text, line):
        try:
            diameter = float(diameter_text)
        except ValueError:
            diameter = None
        valid = diameter is not None and math.isfinite(diameter) and diameter > 0
        if not valid:
            self._add(
                "drill.tool_invalid", "fail", "major",
                "tool T%d has a missing, non-finite or non-positive diameter"
                % code,
                key=("invalid", code), obj="T%d" % code, line=line,
                actual=diameter_text,
            )
        if code in self.tools:
            self.duplicate_tools.add(code)
            previous = self.tools[code]
            if previous["diameter"] != diameter:
                self._add(
                    "drill.tool_invalid", "fail", "major",
                    "tool T%d is redefined with a different diameter" % code,
                    key=("redefined", code), obj="T%d" % code, line=line,
                    actual=diameter_text,
                    expected=previous["diameter_text"],
                )
            return
        self.tools[code] = {
            "tool": code,
            "diameter": diameter if valid else None,
            "diameter_text": diameter_text,
            "valid": bool(valid),
            "used": False,
        }

    # -- body -------------------------------------------------------------

    def _body_line(self, raw, line):
        self.last_line_suspect = False
        text = raw.split(";", 1)[0].strip()
        if not text:
            return
        upper = text.upper()
        if upper == "%":
            return
        if upper in _END_MARKERS:
            self.end_of_file = True
            return
        if upper.startswith("M15") or upper.startswith("M16") or upper.startswith("M17"):
            self.routing += 1
            self._unsupported("routing", line, text)
            return
        if "G85" in upper:
            self.slots += 1
            self._unsupported("slot", line, text)
            return
        if _BODY_ROUTING.search(upper):
            self.routing += 1
            self._unsupported("routing", line, text)
            return
        if _REPEAT.match(upper):
            self._unsupported("repeat", line, text)
            return

        tokens = []
        position = 0
        malformed = False
        for match in _TOKEN.finditer(text):
            if text[position:match.start()].strip():
                malformed = True
                break
            tokens.append((match.group(1).upper(), match.group(2)))
            position = match.end()
        if not malformed and text[position:].strip():
            malformed = True
        if malformed or not tokens:
            self.last_line_suspect = True
            self.capability_unknown.add("word")
            self._unsupported("command", line, text[:80])
            return

        coordinates = []
        index = 0
        while index < len(tokens):
            letter, value = tokens[index]
            if letter == "T":
                code = self._integer_code(value)
                if code is None:
                    self.last_line_suspect = True
                    self._coordinate_invalid(line, "invalid tool number")
                    return
                if (index + 1 < len(tokens) and tokens[index + 1][0] == "C"):
                    self._define_tool(code, tokens[index + 1][1], line)
                    index += 2
                    continue
                self.current_tool = code if code != 0 else None
                if code != 0:
                    self.referenced_tools.add(code)
                index += 1
                continue
            if letter == "C":
                self.capability_unknown.add("C")
                self._unsupported("command", line, text[:80])
                return
            if letter == "G":
                code = self._integer_code(value)
                if code is None:
                    self.last_line_suspect = True
                    self._coordinate_invalid(line, "invalid G-code")
                    return
                self._handle_gcode(code, line, text)
                index += 1
                continue
            if letter == "M":
                code = self._integer_code(value)
                if code is None:
                    self.last_line_suspect = True
                    self._coordinate_invalid(line, "invalid M-code")
                    return
                self._handle_mcode(code, line, text)
                index += 1
                continue
            if letter in ("X", "Y"):
                if value == "" or value in ("+", "-"):
                    self.last_line_suspect = True
                    self._coordinate_invalid(line, "%s without a value" % letter)
                    index += 1
                    continue
                coordinates.append((letter, value))
                index += 1
                continue
            self.capability_unknown.add(letter)
            self._unsupported("command", line, text[:80])
            return

        if coordinates:
            for pair in self._group_coordinates(coordinates):
                if not self._bump(line):
                    return
                self._add_hole(pair[0], pair[1], line)

    def _handle_gcode(self, code, line, text):
        if code == 90:
            self.absolute = True
            self.incremental = False
        elif code == 5:
            self.drill_mode = True
        elif code == 91:
            self.incremental = True
            self.geometry_exact = False
            self._unsupported("incremental", line, text[:80])
        else:
            self.capability_unknown.add("G%02d" % code)
            self._unsupported("command", line, "G%02d" % code)

    def _handle_mcode(self, code, line, text):
        if code in (0, 30):
            self.end_of_file = True
        elif code == 71:
            self._set_units("METRIC", None, line)
        elif code == 72:
            self._set_units("INCH", None, line)
        elif code in (15, 16, 17):
            self.routing += 1
            self._unsupported("routing", line, text[:80])
        else:
            self.capability_unknown.add("M%02d" % code)
            self._unsupported("command", line, "M%02d" % code)

    def _group_coordinates(self, coordinates):
        """Turn an ordered X/Y token stream into hole coordinate pairs."""
        holes = []
        pending_x = None
        pending_y = None
        for axis, value in coordinates:
            if axis == "X":
                if pending_x is not None and pending_y is not None:
                    holes.append((pending_x, pending_y))
                    pending_x = pending_y = None
                pending_x = value
            else:
                if pending_y is not None and pending_x is not None:
                    holes.append((pending_x, pending_y))
                    pending_x = pending_y = None
                pending_y = value
        if pending_x is not None or pending_y is not None:
            holes.append((pending_x, pending_y))
        return holes

    def _add_hole(self, x_text, y_text, line):
        self.hole_count += 1
        tool = self.tools.get(self.current_tool) if self.current_tool is not None else None
        if self.current_tool is None:
            self.holes_without_tool += 1
            self.geometry_exact = False
            self._add(
                "drill.tool_undefined", "fail", "major",
                "hole is emitted without a selected tool", key="none", line=line,
            )
        elif tool is None:
            self.referenced_tools.add(self.current_tool)
        elif not tool["valid"]:
            self.geometry_exact = False
        else:
            tool["used"] = True
        if self.current_tool is not None:
            self.referenced_tools.add(self.current_tool)

        if x_text is None:
            if self.last_x is None:
                self._coordinate_invalid(line, "hole line omits X without a modal X")
                return
            x = self.last_x
        else:
            x = self._scale_coordinate(x_text, "X", line)
            if x is not None and self.incremental:
                x = (self.last_x if self.last_x is not None else 0.0) + x
        if y_text is None:
            if self.last_y is None:
                self._coordinate_invalid(line, "hole line omits Y without a modal Y")
                return
            y = self.last_y
        else:
            y = self._scale_coordinate(y_text, "Y", line)
            if y is not None and self.incremental:
                y = (self.last_y if self.last_y is not None else 0.0) + y
        if x is None or y is None:
            return
        self.last_x, self.last_y = x, y
        self.positions_seen = True
        if tool is not None and tool["valid"]:
            radius = tool["diameter"] / 2.0
        else:
            radius = 0.0
            self.geometry_exact = False
        if self.exp_min_x is None:
            self.exp_min_x = x - radius
            self.exp_max_x = x + radius
            self.exp_min_y = y - radius
            self.exp_max_y = y + radius
        else:
            self.exp_min_x = min(self.exp_min_x, x - radius)
            self.exp_max_x = max(self.exp_max_x, x + radius)
            self.exp_min_y = min(self.exp_min_y, y - radius)
            self.exp_max_y = max(self.exp_max_y, y + radius)

    def _scale_coordinate(self, raw, axis, line):
        text = raw.strip()
        if not text:
            return None
        if "." in text:
            try:
                value = float(text)
            except ValueError:
                self._coordinate_invalid(line, "non-numeric %s value %r" % (axis, raw))
                return None
            if not math.isfinite(value):
                self._coordinate_invalid(line, "non-finite %s value %r" % (axis, raw))
                return None
            if self.coordinate_mode is None:
                self.coordinate_mode = "decimal"
            elif self.coordinate_mode == "integer":
                self.coordinate_mode = "mixed"
            return value
        if self.coordinate_mode is None:
            self.coordinate_mode = "integer"
        elif self.coordinate_mode == "decimal":
            self.coordinate_mode = "mixed"
        if self.format_int is None or self.format_dec is None or self.zeros is None:
            self.geometry_exact = False
            if not self.coordinate_unknown_reported:
                self.coordinate_unknown_reported = True
                missing = []
                if self.format_int is None:
                    missing.append("digit format")
                if self.zeros is None:
                    missing.append("zero suppression")
                self._add(
                    "drill.coordinate_unknown_format", "unknown", "major",
                    "integer coordinates but the %s is not determinable from the "
                    "header; positions are not guessed"
                    % " and ".join(missing),
                    key="unknown_format", line=line,
                    evidence={"missing": missing},
                )
            return None
        digits = text
        sign = 1
        if digits and digits[0] in "+-":
            if digits[0] == "-":
                sign = -1
            digits = digits[1:]
        if not digits.isdigit():
            self._coordinate_invalid(line, "non-numeric %s value %r" % (axis, raw))
            return None
        total = self.format_int + self.format_dec
        if self.zeros == "TZ":
            digits = digits.ljust(total, "0")
        if len(digits) > total:
            self._coordinate_invalid(
                line, "%s value %r exceeds the declared format width" % (axis, raw))
            return None
        return sign * int(digits) / (10 ** self.format_dec)

    def _coordinate_invalid(self, line, detail):
        if not self.coordinate_invalid_reported:
            self.coordinate_invalid_reported = True
            self._add(
                "drill.coordinate_invalid", "fail", "major",
                "invalid coordinate/tool data: %s" % detail,
                key="coordinate", line=line, evidence={"detail": detail},
            )

    @staticmethod
    def _integer_code(value):
        if not value or value in ("+", "-") or "." in value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    # -- finalize ---------------------------------------------------------

    def _finalize(self):
        if self.limit_exceeded:
            return
        if not self.end_of_file:
            self._add(
                "drill.end_missing", "fail", "blocking",
                "no M30 end-of-program command was found", key="end",
            )
        if self.units is None and not self.units_invalid:
            self._add(
                "drill.units_missing", "fail", "blocking",
                "no METRIC/INCH units declaration was found", key="units",
            )
        if not self.tools:
            self._add(
                "drill.tool_table_missing", "fail", "major",
                "the header contains no TnCd tool definitions", key="tools",
            )
        undefined = sorted(
            code for code in self.referenced_tools if code not in self.tools)
        for code in undefined:
            self._add(
                "drill.tool_undefined", "fail", "major",
                "tool T%d is selected or used but never defined" % code,
                key=("undefined", code), obj="T%d" % code,
            )
        if self.hole_count == 0:
            self._add(
                "drill.no_holes", "fail", "major",
                "the file contains no drill holes", key="no_holes",
            )

    def _build_facts(self):
        factor = {"mm": 1.0, "inch": 25.4}.get(self.units)
        facts = _base_facts()
        facts["units"] = self.units
        facts["header"] = {
            "present": self.header_seen,
            "terminated_by": self.header_terminated_by,
            "line_count": self.header_line_count,
            "format_hint": self.format_hint,
            "unknown": list(self.header_unknown),
        }
        facts["format"] = {
            "mode": self.coordinate_mode,
            "integer_digits": self.format_int,
            "decimal_digits": self.format_dec,
            "zero_suppression": self.zeros,
        }
        facts["end_of_file"] = self.end_of_file
        facts["tool_count"] = len(self.tools)
        facts["hole_count"] = self.hole_count
        facts["slots"] = self.slots
        facts["routing"] = self.routing
        facts["tools"] = [
            {
                "tool": code,
                "diameter": self.tools[code]["diameter"],
                "diameter_mm": (
                    round(self.tools[code]["diameter"] * factor, 9)
                    if self.tools[code]["diameter"] is not None and factor else None
                ),
                "defined": self.tools[code]["valid"],
                "used": self.tools[code]["used"],
                "duplicate": code in self.duplicate_tools,
            }
            for code in sorted(self.tools)
        ]
        facts["undefined_tools"] = sorted(
            code for code in self.referenced_tools if code not in self.tools)
        facts["duplicate_tools"] = sorted(self.duplicate_tools)
        if factor is not None and self.exp_min_x is not None:
            exact = (
                self.geometry_exact
                and not self.units_invalid
                and not self.incremental
            )
            basis = "hole centres expanded by tool radius (mm)"
            if not exact:
                basis += (
                    "; conservative or partial bound, unsupported tools/"
                    "geometry excluded"
                )
            facts["extent"] = {
                "x_min": round(self.exp_min_x * factor, 9),
                "y_min": round(self.exp_min_y * factor, 9),
                "x_max": round(self.exp_max_x * factor, 9),
                "y_max": round(self.exp_max_y * factor, 9),
                "exact": exact,
                "basis": basis,
                "unit": "mm",
            }
        facts["unsupported"] = sorted(self.unsupported)
        facts["encoding"] = self.encoding
        facts["errors"] = list(self.errors)
        facts["holes_without_tool"] = self.holes_without_tool
        facts["token_count"] = self.tokens
        facts["limit_exceeded"] = self.limit_exceeded
        return facts


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def parse_drill(data, file, options=None):
    """Parse bounded Excellon drill bytes.

    Returns the contract dictionary (``kind``/``file``/``status``/``facts``/
    ``capability``/``findings``).  Content problems are findings; only argument
    type errors and invalid option values raise ``ValueError``.
    """
    max_objects = _validate_arguments(data, file, options)
    raw = bytes(data)
    if not raw:
        findings = [finding(
            "drill.file_empty", "fail", "blocking",
            "drill file is empty (zero bytes)", file=file,
        )]
        return _result(file, _base_facts(), findings)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        facts = _base_facts()
        findings = [finding(
            "drill.header_missing", "fail", "blocking",
            "drill bytes are not valid UTF-8/ASCII; the header cannot be read",
            file=file, evidence={"offset": exc.start, "reason": exc.reason},
        )]
        return _result(file, facts, findings)
    encoding = "utf-8"
    if text.startswith("\ufeff"):
        text = text[1:]
        encoding = "utf-8-sig"
    state = _DrillState(text, file, max_objects, encoding)
    return state.run()
