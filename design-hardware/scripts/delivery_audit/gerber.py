"""Bounded, offline Gerber (RS-274X) parser for the delivery audit.

This module reads already-exported Gerber bytes and returns a JSON-ready
dictionary with ``kind``/``file``/``status``/``facts``/``capability``/``findings``
as frozen by ``docs/parallel-delivery-audit/contract.md`` section 7.

The parser is a real token/state machine, not a set of whole-file regular
expressions: an input is split into ``%...%`` extended blocks and ``*``-terminated
word commands, and each command is interpreted in order while modal state
(units, format, current aperture, current point, interpolation mode, region
mode) is maintained.

Supported subset
----------------

* extended commands ``%...*%`` and word commands ``...*``; optional whitespace
  between commands; ``M02`` is required as the last command;
* units ``%MOMM`` / ``%MOIN`` (legacy ``G70``/``G71`` are accepted as the same
  declaration); conflicting declarations are a failure;
* format ``%FS`` with L (leading zero omission) or T (trailing zero omission)
  and absolute notation only.  Coordinates may also be written with a decimal
  point, in which case the value is used as-is in the declared unit;
* apertures ``%ADD`` with templates C (diameter), R (width x height),
  O (width x height) and P (outer diameter, vertices, optional rotation, hole),
  including the optional ``X<hole>`` parameter;
* ``G01`` linear draws, ``D02`` moves, ``D03`` flashes, modal D-codes and
  omitted X/Y axes, ``G54``/``G55`` aperture selection, ``G04`` comments,
  ``%TF.FileFunction``/``%TF.FilePolarity``/``%TF.Part`` X2 metadata and other
  ``%TF``/``%TA``/``%TO``/``%TD`` attributes (metadata only).

Explicitly unsupported (an ``unknown`` finding is always emitted, never a
``pass``)
------------------------------------------------------------------------

``AM``/``AB`` macros, ``%SR`` step and repeat, ``G36``/``G37`` regions,
``G02``/``G03`` arcs, non-default polarity (``%LPC`` or a negative
``%TF.FilePolarity``), ``%LM``/``%LR``/``%LS`` image transforms, ``%IPNEG``
image negative, ``%MI``/``%OF``/``%SF``/``%AS`` image parameters, incremental
coordinates (``%FSI`` or ``G91``), unknown D-codes/aperture templates,
unrecognised extended/word commands and trailing data after ``M02``.  When any
of these is seen the affected geometry cannot be trusted: ``contours_exact``
and ``extent.exact`` become ``false`` and the conservative basis is stated.

``facts`` shape
---------------

``units`` / ``format`` / ``file_function`` / ``file_polarity`` / ``part``,
``apertures`` (list sorted by code), ``graphical_objects``, ``draws``,
``flashes``, ``regions``, ``arcs``, ``macros``, ``contours`` (linear contours
with ``points``, ``closed``, ``aperture``, ``width_mm``), ``contours_exact``,
``path_extent`` (mm, coordinates only), ``extent`` (mm, coordinates expanded by
aperture half-size / flash size, with ``exact`` and ``basis``),
``end_of_file``, ``encoding``, ``errors``, ``unsupported``.  ``extent`` and
``path_extent`` are ``None`` when units or coordinates cannot be interpreted.

Options
-------

``options`` is ``None`` or a dict.  ``max_objects`` (and its alias
``max_tokens``) override the default 2,000,000 command/object budget.  When the
budget is exceeded the parser stops cleanly with a ``gerber.limit_objects``
unknown finding; it never silently truncates and reports ``pass``.

Content problems never raise; only programming errors (wrong argument types or
invalid option values) raise ``ValueError``.  Input is ``bytes`` only; this
module performs no I/O.
"""

from __future__ import annotations

import bisect
import math
import re

from .model import finding, sort_findings

KIND = "gerber"
DEFAULT_MAX_OBJECTS = 2_000_000

_SUPPORTED = [
    "RS-274X extended commands %...*% and * terminated word commands",
    "M02 end of file",
    "%MOMM/%MOIN units (legacy G70/G71 accepted)",
    "%FS L/T zero omission with absolute notation",
    "%ADD apertures C/R/O/P including optional hole parameter",
    "G01 linear draw",
    "D02 move and D03 flash",
    "modal D-code and omitted-axis coordinates",
    "G54/G55 aperture selection",
    "G04 comments",
    "X2 %TF.FileFunction/%TF.FilePolarity/%TF.Part and TF/TA/TO/TD metadata",
    "object budget with gerber.limit_objects unknown finding",
]

_UNSUPPORTED = [
    "AM/AB aperture macros",
    "%SR step and repeat",
    "G36/G37 regions",
    "G02/G03 arcs",
    "%LPC non-default polarity",
    "%LM/%LR/%LS image transforms",
    "%IPNEG image negative",
    "%MI/%OF/%SF/%AS image parameters",
    "incremental coordinates (%FSI or G91)",
    "unknown D-codes and aperture templates",
    "unrecognised extended commands",
    "trailing data after M02",
]

_WORD_TOKEN = re.compile(r"([A-Za-z])([+-]?(?:\d+(?:\.\d*)?|\.\d+)?)")
_FS_BODY = re.compile(r"^X(\d)(\d)Y(\d)(\d)(?:D(\d)(\d))?$")
_ADD_BODY = re.compile(r"^ADD(\d+)([^,]*)(?:,(.*))?$")
_COMMENT_WORD = re.compile(r"^G0*4(?![0-9])")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

class _LineMap:
    """Map byte offsets in the decoded text to 1-based line numbers."""

    __slots__ = ("_starts",)

    def __init__(self, text):
        starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                starts.append(index + 1)
        self._starts = starts

    def line(self, offset):
        return bisect.bisect_right(self._starts, offset)


def _iter_blocks(text):
    """Yield ``(kind, content, offset)`` for each command block.

    ``kind`` is ``word`` (content is the text between separators, trailing ``*``
    removed), ``extended`` (content between the two ``%`` characters),
    ``word_unterminated`` or ``extended_unterminated``.  The two unterminated
    kinds are how truncation in the middle of a command is detected.
    """
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in " \t\r\n":
            index += 1
            continue
        if char == "%":
            end = text.find("%", index + 1)
            if end < 0:
                yield "extended_unterminated", text[index + 1:], index
                return
            yield "extended", text[index + 1:end], index
            index = end + 1
        else:
            end = text.find("*", index)
            if end < 0:
                yield "word_unterminated", text[index:], index
                return
            yield "word", text[index:end], index
            index = end + 1


def _base_facts():
    return {
        "units": None,
        "format": None,
        "file_function": None,
        "file_polarity": None,
        "part": None,
        "apertures": [],
        "graphical_objects": 0,
        "draws": 0,
        "flashes": 0,
        "regions": 0,
        "arcs": 0,
        "macros": 0,
        "contours": [],
        "contours_exact": False,
        "path_extent": None,
        "extent": None,
        "end_of_file": False,
        "encoding": None,
        "errors": [],
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


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

class _GerberState:
    """Single-pass RS-274X state machine."""

    def __init__(self, text, file, max_objects, encoding):
        self.text = text
        self.file = file
        self.max_objects = max_objects
        self.line_map = _LineMap(text)
        self.encoding = encoding
        self.findings = []
        self._finding_keys = set()
        self.errors = []
        self.unsupported = []
        self.capability_unknown = set()

        # head declarations
        self.units = None
        self.units_declared = False
        self.units_conflict = False
        self.units_invalid = False
        self.format = None
        self.format_declared = False
        self.format_invalid = False
        self.incremental = False
        self.incremental_declared = False

        # apertures
        self.apertures = {}
        self.current_aperture = None
        self.referenced_apertures = set()
        self.redefined_apertures = set()
        self.macro_names = set()
        self.macro_count = 0

        # modal state
        self.modal_op = None
        self.interpolation = "linear"
        self.region_mode = False
        self.region_blocks = 0
        self.pos = [0.0, 0.0]
        self.pos_known = True
        self.coordinates_unscalable = False
        self.file_function = None
        self.file_polarity = None
        self.part = None

        # geometry bookkeeping (raw file units until finalize)
        self.path_min_x = None
        self.path_min_y = None
        self.path_max_x = None
        self.path_max_y = None
        self.exp_min_x = None
        self.exp_min_y = None
        self.exp_max_x = None
        self.exp_max_y = None
        self.contours = []
        self.current_contour = None
        self.geometry_uncertain = False

        # counts / state flags
        self.draws = 0
        self.arcs = 0
        self.flashes = 0
        self.graphics = 0
        self.tokens = 0
        self.end_of_file = False
        self.truncated = False
        self.limit_exceeded = False
        self.aperture_missing_reported = False
        self.draw_without_aperture_reported = False

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
        self.geometry_uncertain = True
        evidence = {"feature": feature}
        if detail:
            evidence["detail"] = str(detail)[:120]
        self._add(
            "gerber.unsupported." + feature, "unknown", "major",
            "unsupported Gerber feature %r; geometry coverage is not claimed" % feature,
            key=feature, line=line, evidence=evidence,
        )

    def _limit_reached(self, line):
        self.limit_exceeded = True
        self.geometry_uncertain = True
        self._add(
            "gerber.limit_objects", "unknown", "major",
            "command/object budget of %d exceeded; the file was not fully parsed"
            % self.max_objects,
            key="limit", line=line, actual=self.max_objects, unit="objects",
            evidence={"limit": self.max_objects, "parsed": self.tokens},
        )

    # -- run --------------------------------------------------------------

    def run(self):
        for kind, content, offset in _iter_blocks(self.text):
            if self.end_of_file or self.limit_exceeded:
                break
            self.tokens += 1
            if self.tokens > self.max_objects:
                self._limit_reached(self.line_map.line(offset))
                break
            line = self.line_map.line(offset)
            if kind == "word_unterminated" or kind == "extended_unterminated":
                self.truncated = True
                self._error(line, "file ends inside an unterminated command")
                break
            if kind == "word":
                self._handle_word(content, line)
                if self.end_of_file:
                    trailing = self.text[offset + len(content) + 1:]
                    if trailing.strip():
                        self._unsupported("trailing_data", line, trailing.strip()[:80])
                    break
            else:
                self._handle_extended(content, line)
        self._finalize()
        return _result(self.file, self._build_facts(), self.findings,
                       self.capability_unknown)

    # -- extended commands ------------------------------------------------

    def _handle_extended(self, content, line):
        body = content.strip()
        if not body:
            return
        upper = body.upper()
        if upper.startswith("AM"):
            self.macro_count += 1
            name = body[2:].split("*", 1)[0].strip()
            if name:
                self.macro_names.add(name)
            self._unsupported("macro", line, name or "AM")
            return
        if upper.startswith("AB"):
            self.macro_count += 1
            name = body[2:].split("*", 1)[0].strip()
            if name:
                self.macro_names.add(name)
            self._unsupported("macro", line, name or "AB")
            return
        for piece in body.split("*"):
            piece = piece.strip()
            if not piece:
                continue
            self._handle_extended_command(piece, line)
            if self.limit_exceeded:
                break

    def _handle_extended_command(self, command, line):
        upper = command.upper()
        if upper.startswith("FS"):
            self._parse_format(command, line)
        elif upper.startswith("MO"):
            self._parse_units(command, line)
        elif upper.startswith("ADD"):
            self._define_aperture(command, line)
        elif upper.startswith("TF."):
            self._parse_file_attribute(command, line)
        elif upper.startswith("TA") or upper.startswith("TO") or upper.startswith("TD"):
            return  # X2 object attributes are metadata only
        elif upper.startswith("SR"):
            self._unsupported("step_repeat", line, command[:60])
        elif upper.startswith("LP"):
            value = upper[2:].strip()
            if value.startswith("C"):
                self._unsupported("polarity", line, command[:60])
            elif value.startswith("D"):
                return  # default dark polarity
            else:
                self._unsupported("polarity", line, command[:60])
        elif upper.startswith("LM") or upper.startswith("LR") or upper.startswith("LS"):
            self._unsupported("transform", line, command[:60])
        elif upper.startswith("IP"):
            value = upper[2:].strip()
            if value.startswith("NEG"):
                self._unsupported("image_negative", line, command[:60])
            # %IPPOS is plain positive image metadata
        elif (upper.startswith("MI") or upper.startswith("OF")
              or upper.startswith("SF") or upper.startswith("AS")):
            self._unsupported("image_parameter", line, command[:60])
        elif upper.startswith("IN") or upper.startswith("LN") or upper.startswith("PF"):
            return  # image/layer/film name metadata
        else:
            name = re.match(r"[A-Za-z][A-Za-z.]*", command)
            token = name.group(0).upper() if name else command[:16].upper()
            self.capability_unknown.add(token)
            self._unsupported("extended_command", line, command[:60])

    def _parse_file_attribute(self, command, line):
        parts = command.split(",")
        key = parts[0][3:].strip().lower()
        value = ",".join(parts[1:]).strip()
        if key == "filefunction":
            self.file_function = value or None
        elif key == "filepolarity":
            self.file_polarity = value or None
            if value and value.strip().lower() not in ("positive", "dark"):
                self._unsupported("polarity", line, "FilePolarity=" + value[:40])
        elif key == "part":
            self.part = value or None
        # all other TF attributes are generation metadata and are ignored

    def _set_units(self, units, line, declaration):
        self.units_declared = True
        if self.units is None:
            self.units = units
        elif self.units != units:
            self.units_conflict = True
            self._add(
                "gerber.units_mixed", "fail", "major",
                "units are declared more than once with different values",
                key="mixed", line=line,
                actual=units, expected=self.units,
                evidence={"declarations": declaration},
            )
        else:
            # a repeated identical declaration is harmless
            return

    def _parse_units(self, command, line):
        raw = command[2:].strip().upper()
        if raw in ("MM", "MILLIMETER", "MILLIMETERS"):
            self._set_units("mm", line, "%MO" + raw)
        elif raw in ("IN", "INCH", "INCHES"):
            self._set_units("inch", line, "%MO" + raw)
        else:
            self.units_invalid = True
            self._add(
                "gerber.units_missing", "fail", "blocking",
                "units declaration %r is not MM or IN; units cannot be trusted"
                % ("%MO" + raw),
                key="units", line=line, evidence={"declaration": "%MO" + raw},
            )

    def _parse_format(self, command, line):
        self.format_declared = True
        body = command[2:].strip()
        if len(body) < 2 or body[0] not in "LT" or body[1] not in "AI":
            self._format_invalid(line, command, "zero omission/notation not L/T + A/I")
            return
        match = _FS_BODY.match(body[2:])
        if not match:
            self._format_invalid(line, command, "X/Y digit groups not recognisable")
            return
        zero = body[0]
        notation = body[1]
        x_int = int(match.group(1))
        x_dec = int(match.group(2))
        y_int = int(match.group(3))
        y_dec = int(match.group(4))
        if x_int <= 0 or y_int <= 0:
            self._format_invalid(line, command, "integer digit count must be positive")
            return
        declared = {
            "zero_omission": zero,
            "notation": "absolute" if notation == "A" else "incremental",
            "x_integer": x_int,
            "x_decimal": x_dec,
            "y_integer": y_int,
            "y_decimal": y_dec,
            "declared": command.strip(),
        }
        if self.format is not None and self.format != declared:
            self._format_invalid(line, command, "conflicting format declarations")
            return
        self.format = declared
        if notation == "I":
            self.incremental = True
            self.incremental_declared = True
            self._unsupported("incremental", line, command[:60])

    def _format_invalid(self, line, command, reason):
        self.format_invalid = True
        self._add(
            "gerber.format_invalid", "fail", "blocking",
            "invalid or conflicting %%FS format declaration: %s" % reason,
            key="format", line=line, evidence={"declaration": command[:80]},
        )

    def _define_aperture(self, command, line):
        match = _ADD_BODY.match(command)
        if not match:
            self.capability_unknown.add("ADD")
            self._unsupported("extended_command", line, command[:60])
            return
        code = int(match.group(1))
        template = match.group(2).strip()
        raw_params = match.group(3)
        if not template or code <= 0:
            self._add(
                "gerber.aperture_undefined", "fail", "major",
                "aperture definition for D%d has no usable template" % code,
                key=("definition", code), obj="D%d" % code, line=line,
            )
            return
        if code in self.apertures:
            self.redefined_apertures.add(code)
            self._add(
                "gerber.aperture_redefined", "fail", "major",
                "aperture D%d is defined more than once" % code,
                key=("redefined", code), obj="D%d" % code, line=line,
                evidence={"template": template, "parameters": raw_params or ""},
            )
            return
        params = []
        params_valid = True
        if raw_params is not None:
            for token in raw_params.split("X"):
                token = token.strip()
                if not token:
                    continue
                try:
                    value = float(token)
                except ValueError:
                    params_valid = False
                    break
                if not math.isfinite(value):
                    params_valid = False
                    break
                params.append(value)
        template_upper = template.upper()
        aperture = {
            "code": code,
            "template": template,
            "template_upper": template_upper,
            "parameters": params,
            "width": None,
            "height": None,
            "hole": None,
            "vertices": None,
            "half_x": 0.0,
            "half_y": 0.0,
            "supported": False,
            "macro": False,
            "reason": None,
        }
        if template_upper in ("C", "R", "O", "P"):
            self._resolve_standard_aperture(aperture, template_upper, params,
                                           params_valid, line)
        else:
            self._resolve_unknown_aperture(aperture, template, line)
        self.apertures[code] = aperture

    def _resolve_standard_aperture(self, aperture, template, params, params_valid,
                                   line):
        code = aperture["code"]
        hole = None
        if not params_valid:
            aperture["reason"] = "invalid_parameters"
            self._aperture_definition_failed(code, line, "non-numeric parameter")
            return
        if template == "C":
            # RS-274X section 4.3.1 explicitly allows a zero-diameter C
            # aperture; exporters commonly use it for board profiles and marks.
            # Zero is accepted as a valid zero-width aperture (no extent
            # expansion), while a negative or missing diameter stays invalid.
            if len(params) < 1 or params[0] < 0:
                aperture["reason"] = "invalid_parameters"
                self._aperture_definition_failed(
                    code, line, "diameter must be non-negative")
                return
            diameter = params[0]
            hole = params[1] if len(params) > 1 else None
            aperture["width"] = diameter
            aperture["height"] = diameter
            aperture["half_x"] = diameter / 2.0
            aperture["half_y"] = diameter / 2.0
        elif template in ("R", "O"):
            if len(params) < 2 or params[0] <= 0 or params[1] <= 0:
                aperture["reason"] = "invalid_parameters"
                self._aperture_definition_failed(
                    code, line, "width and height must be positive")
                return
            width, height = params[0], params[1]
            hole = params[2] if len(params) > 2 else None
            aperture["width"] = width
            aperture["height"] = height
            aperture["half_x"] = width / 2.0
            aperture["half_y"] = height / 2.0
        else:  # P: outer diameter, vertices [, rotation [, hole]]
            if len(params) < 2 or params[0] <= 0 or params[1] < 3:
                aperture["reason"] = "invalid_parameters"
                self._aperture_definition_failed(
                    code, line, "outer diameter and >=3 vertices required")
                return
            outer = params[0]
            aperture["width"] = outer
            aperture["height"] = outer
            aperture["half_x"] = outer / 2.0
            aperture["half_y"] = outer / 2.0
            aperture["vertices"] = int(params[1])
            if params[1] != int(params[1]):
                aperture["reason"] = "invalid_parameters"
                self._aperture_definition_failed(code, line, "vertices must be an integer")
                return
            hole = params[3] if len(params) > 3 else None
        if hole is not None and (not math.isfinite(hole) or hole < 0):
            aperture["reason"] = "invalid_parameters"
            self._aperture_definition_failed(code, line, "hole must be non-negative")
            return
        aperture["hole"] = hole
        aperture["supported"] = True

    def _resolve_unknown_aperture(self, aperture, template, line):
        code = aperture["code"]
        macro_names = {name.upper() for name in self.macro_names}
        if template in self.macro_names or template.upper() in macro_names:
            aperture["macro"] = True
            aperture["reason"] = "macro"
            self._unsupported("macro", line, template)
        else:
            aperture["reason"] = "unknown_template"
            self.capability_unknown.add("aperture:" + template.upper())
            self._unsupported("aperture_template", line, template)
        # A macro / unknown-template aperture is still defined: the feature is
        # explicitly unsupported (unknown), not a missing aperture definition.

    def _aperture_definition_failed(self, code, line, reason):
        self._add(
            "gerber.aperture_undefined", "fail", "major",
            "aperture D%d definition has invalid parameters: %s" % (code, reason),
            key=("bad_definition", code), obj="D%d" % code, line=line,
            evidence={"reason": reason},
        )

    # -- word commands ----------------------------------------------------

    def _handle_word(self, content, line):
        word = content.strip()
        if not word:
            return
        upper = word.upper()
        if _COMMENT_WORD.match(upper):
            return  # G04 comment, text is free-form up to the '*'

        tokens = []
        position = 0
        malformed = False
        for match in _WORD_TOKEN.finditer(word):
            if word[position:match.start()].strip():
                malformed = True
                break
            tokens.append((match.group(1).upper(), match.group(2)))
            position = match.end()
        if not malformed and word[position:].strip():
            malformed = True
        if malformed or not tokens:
            self._error(line, "unrecognised word command: %r" % word[:80])
            if "X" in upper or "Y" in upper:
                self._coordinate_invalid(line, "malformed coordinate command")
            self.capability_unknown.add("word")
            self._unsupported("command", line, word[:60])
            return

        gcodes = []
        mcodes = []
        dcode = None
        coords = {}
        arc_parameters = False
        for letter, value in tokens:
            if letter in ("X", "Y"):
                if value == "" or value in ("+", "-"):
                    self._coordinate_invalid(line, "%s without a value" % letter)
                    continue
                coords[letter] = value
            elif letter == "D":
                code = self._integer_code(value)
                if code is None:
                    self._coordinate_invalid(line, "invalid D-code %r" % value)
                    continue
                if dcode is not None and dcode != code:
                    self._error(line, "two different D-codes in one data block")
                    self._unsupported("command", line, word[:60])
                    return
                dcode = code
            elif letter == "G":
                code = self._integer_code(value)
                if code is None:
                    self._coordinate_invalid(line, "invalid G-code %r" % value)
                    return
                gcodes.append(code)
            elif letter == "M":
                code = self._integer_code(value)
                if code is None:
                    self._coordinate_invalid(line, "invalid M-code %r" % value)
                    return
                mcodes.append(code)
            elif letter in ("I", "J", "K"):
                arc_parameters = True
            else:
                self.capability_unknown.add(letter)
                self._unsupported("command", line, word[:60])
                return
        if arc_parameters:
            self._unsupported("arc", line, "I/J/K arc parameters")

        # M-codes: only M02 ends the file, M00/M01 are program stops.
        for mcode in mcodes:
            if mcode == 2:
                if coords or dcode is not None or arc_parameters:
                    self._add(
                        "gerber.end_not_last", "fail", "blocking",
                        "M02 shares a command block with geometry/operation data; "
                        "that data was not applied",
                        key=("m02_block", line), line=line,
                        evidence={"block": word[:120]},
                        suggestion="put M02 in its own command block; do not "
                                   "append data to the end marker")
                    self.geometry_uncertain = True
                    self.capability_unknown.add("m02_block")
                self.end_of_file = True
                return
            if mcode in (0, 1):
                continue
            self._unsupported("mcode", line, "M%02d" % mcode)
            return

        for gcode in gcodes:
            self._handle_gcode(gcode, line)
            if self.end_of_file or self.limit_exceeded:
                return

        # operation / aperture selection
        operation = None
        if dcode is not None:
            if dcode in (1, 2, 3):
                operation = dcode
            elif dcode >= 10:
                self.current_aperture = dcode
                self.referenced_apertures.add(dcode)
                if dcode not in self.apertures:
                    self.geometry_uncertain = True
            elif dcode > 3:
                self.capability_unknown.add("D%02d" % dcode)
                self._unsupported("dcode", line, "D%02d" % dcode)
                return
        if operation is None and not coords:
            # A pure G-code state change or a standalone aperture selection does
            # not create a data block; do not replay the modal operation.
            return
        if operation is None:
            operation = self.modal_op
            if operation is None:
                self._coordinate_invalid(
                    line, "coordinate data block without an operation code")
                operation = 2  # track the point, do not invent graphics
        if operation in (1, 2, 3):
            self.modal_op = operation

        self._apply_operation(operation, coords, line)

    def _handle_gcode(self, gcode, line):
        if gcode == 1:
            self.interpolation = "linear"
        elif gcode == 2 or gcode == 3:
            self.interpolation = "arc"
            self._unsupported("arc", line, "G%02d" % gcode)
        elif gcode == 36:
            if not self.region_mode:
                self.region_blocks += 1
            self.region_mode = True
            self._unsupported("region", line, "G36")
        elif gcode == 37:
            self.region_mode = False
        elif gcode in (54, 55):
            return
        elif gcode == 70:
            self._set_units("inch", line, "G70")
        elif gcode == 71:
            self._set_units("mm", line, "G71")
        elif gcode in (74, 75):
            return  # arc quadrant mode; arcs themselves are unsupported
        elif gcode == 90:
            self.incremental = False
        elif gcode == 91:
            self.incremental = True
            self.incremental_declared = True
            self._unsupported("incremental", line, "G91")
        else:
            self.capability_unknown.add("G%02d" % gcode)
            self._unsupported("gcode", line, "G%02d" % gcode)

    def _coordinate_invalid(self, line, detail):
        self._add(
            "gerber.coordinate_invalid", "fail", "major",
            "invalid coordinate data: %s" % detail,
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

    # -- coordinate scaling ----------------------------------------------

    def _scale_value(self, raw, axis, line):
        """Return a coordinate in file units, or None when not scalable."""
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
            return value
        if self.format is None:
            self.coordinates_unscalable = True
            self._error(line, "coordinate %r before a usable %%FS declaration" % raw)
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
        if axis == "X":
            total = self.format["x_integer"] + self.format["x_decimal"]
            decimals = self.format["x_decimal"]
        else:
            total = self.format["y_integer"] + self.format["y_decimal"]
            decimals = self.format["y_decimal"]
        if self.format["zero_omission"] == "T":
            digits = digits.ljust(total, "0")
        if len(digits) > total:
            self._coordinate_invalid(
                line, "%s value %r exceeds the declared format width" % (axis, raw))
            return None
        return sign * int(digits) / (10 ** decimals)

    # -- operations -------------------------------------------------------

    def _check_aperture(self, line):
        if self.current_aperture is None:
            if not self.apertures:
                if not self.aperture_missing_reported:
                    self.aperture_missing_reported = True
                    self.geometry_uncertain = True
                    self._add(
                        "gerber.aperture_missing", "fail", "major",
                        "graphical objects are present but the file defines no apertures",
                        key="missing", line=line,
                    )
            if not self.draw_without_aperture_reported:
                self.draw_without_aperture_reported = True
                self.geometry_uncertain = True
                self._add(
                    "gerber.draw_without_aperture", "fail", "major",
                    "draw/flash without a selected aperture",
                    key="no_selection", line=line,
                )
            return None
        aperture = self.apertures.get(self.current_aperture)
        if aperture is None:
            self.geometry_uncertain = True
            return None
        if not aperture["supported"]:
            self.geometry_uncertain = True
        return aperture

    def _apply_operation(self, operation, coords, line):
        if operation not in (1, 2, 3):
            # unknown/missing operation: still track a bare point if coordinates exist
            if coords:
                self._resolve_position(coords, line)
            return
        new_x, new_y = self._resolve_position(coords, line)
        if new_x is None:
            return
        old_x, old_y = self.pos
        had_position = self.pos_known
        if operation == 2:
            self._finish_contour()
            self._include_path(new_x, new_y)
            # Moves do not print, so an unselected aperture is not an error here.
            move_aperture = self.apertures.get(self.current_aperture)
            self._expand(new_x, new_y, "move", move_aperture)
            self.pos = [new_x, new_y]
            self.pos_known = True
            self.current_contour = {
                "points": [(new_x, new_y)],
                "aperture": self.current_aperture,
                "width": self._aperture_line_width(),
                "region": self.region_mode,
                "closed": False,
            }
            return
        if operation == 3:
            aperture = self._check_aperture(line)
            self.graphics += 1
            self.flashes += 1
            self._finish_contour()
            self._include_path(new_x, new_y)
            self._expand(new_x, new_y, "flash", aperture)
            self.pos = [new_x, new_y]
            self.pos_known = True
            return
        # operation == 1, draw
        aperture = self._check_aperture(line)
        if self.interpolation == "arc":
            self.arcs += 1
            self._unsupported("arc", line, "arc draw")
        else:
            self.draws += 1
        self.graphics += 1
        self._include_path(new_x, new_y)
        if had_position:
            self._include_path(old_x, old_y)
            self._expand(old_x, old_y, "draw", aperture)
        else:
            old_x, old_y = new_x, new_y
        self._expand(new_x, new_y, "draw", aperture)
        if self.current_contour is None:
            self.current_contour = {
                "points": [(old_x, old_y)],
                "aperture": self.current_aperture,
                "width": self._aperture_line_width(),
                "region": self.region_mode,
                "closed": False,
            }
        self.current_contour["points"].append((new_x, new_y))
        self.pos = [new_x, new_y]
        self.pos_known = True

    def _resolve_position(self, coords, line):
        new_x, new_y = self.pos
        for axis in ("X", "Y"):
            if axis not in coords:
                continue
            value = self._scale_value(coords[axis], axis, line)
            if value is None:
                return None, None
            if self.incremental:
                base = self.pos[0] if axis == "X" else self.pos[1]
                value = base + value
            if axis == "X":
                new_x = value
            else:
                new_y = value
        return new_x, new_y

    def _aperture_line_width(self):
        aperture = self.apertures.get(self.current_aperture)
        if aperture is None or not aperture["supported"]:
            return None
        width = aperture.get("width")
        height = aperture.get("height")
        if width is None:
            return None
        if height is None:
            return width
        return min(width, height)

    # -- extent / contours ------------------------------------------------

    def _include_path(self, x, y):
        if self.path_min_x is None:
            self.path_min_x = self.path_max_x = x
            self.path_min_y = self.path_max_y = y
        else:
            self.path_min_x = min(self.path_min_x, x)
            self.path_max_x = max(self.path_max_x, x)
            self.path_min_y = min(self.path_min_y, y)
            self.path_max_y = max(self.path_max_y, y)

    def _expand(self, x, y, kind, aperture):
        if aperture is not None and aperture["supported"]:
            # An axis-aligned aperture swept along a line expands the bounding
            # box by exactly half of its width / height on each axis.
            expand_x = aperture["half_x"]
            expand_y = aperture["half_y"]
        else:
            expand_x = expand_y = 0.0
            if kind in ("draw", "flash"):
                self.geometry_uncertain = True
        if self.exp_min_x is None:
            self.exp_min_x = x - expand_x
            self.exp_max_x = x + expand_x
            self.exp_min_y = y - expand_y
            self.exp_max_y = y + expand_y
        else:
            self.exp_min_x = min(self.exp_min_x, x - expand_x)
            self.exp_max_x = max(self.exp_max_x, x + expand_x)
            self.exp_min_y = min(self.exp_min_y, y - expand_y)
            self.exp_max_y = max(self.exp_max_y, y + expand_y)

    def _finish_contour(self):
        contour = self.current_contour
        self.current_contour = None
        if contour is None:
            return
        points = contour["points"]
        if len(points) >= 2:
            first = points[0]
            last = points[-1]
            contour["closed"] = (
                abs(first[0] - last[0]) <= 1e-6
                and abs(first[1] - last[1]) <= 1e-6
            )
            self.contours.append(contour)

    # -- finalize ---------------------------------------------------------

    def _finalize(self):
        self._finish_contour()
        if self.limit_exceeded:
            # The scan stopped early on purpose: do not claim missing end/format/
            # units based on content that was never read.
            return
        if self.truncated:
            self._add(
                "gerber.truncated", "fail", "blocking",
                "file ends inside an unterminated command", key="truncated",
            )
        elif not self.end_of_file:
            self._add(
                "gerber.end_missing", "fail", "blocking",
                "no M02 end-of-file command was found", key="end",
            )
        if self.format_invalid:
            pass  # already reported
        elif not self.format_declared:
            self._add(
                "gerber.format_missing", "fail", "blocking",
                "no %FS coordinate format declaration was found", key="format",
            )
        if self.units is None and not self.units_invalid:
            self._add(
                "gerber.units_missing", "fail", "blocking",
                "no %MOMM/%MOIN units declaration was found", key="units",
            )
        undefined = sorted(self.referenced_apertures - set(self.apertures))
        for code in undefined:
            self._add(
                "gerber.aperture_undefined", "fail", "major",
                "aperture D%d is used but never defined" % code,
                key=("undefined", code), obj="D%d" % code,
            )
        if self.graphics == 0 and not self.limit_exceeded:
            self._add(
                "gerber.no_graphical_objects", "fail", "major",
                "file contains no draws or flashes", key="no_graphics",
            )
    def _build_facts(self):
        factor = {"mm": 1.0, "inch": 25.4}.get(self.units)
        facts = _base_facts()
        facts["units"] = self.units
        facts["format"] = dict(self.format) if self.format else None
        facts["file_function"] = self.file_function
        facts["file_polarity"] = self.file_polarity
        facts["part"] = self.part
        facts["apertures"] = [
            self._aperture_fact(self.apertures[code], factor)
            for code in sorted(self.apertures)
        ]
        facts["graphical_objects"] = self.graphics
        facts["draws"] = self.draws
        facts["flashes"] = self.flashes
        facts["regions"] = self.region_blocks
        facts["arcs"] = self.arcs
        facts["macros"] = self.macro_count
        contours_exact = (
            factor is not None
            and not self.geometry_uncertain
            and self.format is not None
        )
        facts["contours_exact"] = contours_exact
        facts["contours"] = [
            self._contour_fact(contour, factor)
            for contour in self.contours
        ] if factor is not None else []
        if factor is not None and self.exp_min_x is not None and not self.coordinates_unscalable:
            facts["path_extent"] = {
                "x_min": round(self.path_min_x * factor, 9),
                "y_min": round(self.path_min_y * factor, 9),
                "x_max": round(self.path_max_x * factor, 9),
                "y_max": round(self.path_max_y * factor, 9),
            }
            exact = (
                not self.geometry_uncertain
                and self.format is not None
                and not self.units_conflict
                and not self.coordinates_unscalable
            )
            basis = (
                "path extent from all coordinates expanded by aperture "
                "half-size and flash size (mm)"
            )
            if not exact:
                basis += (
                    "; conservative or partial bound, unsupported/unscaled "
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
        facts["end_of_file"] = self.end_of_file
        facts["encoding"] = self.encoding
        facts["errors"] = list(self.errors)
        facts["unsupported"] = sorted(self.unsupported)
        facts["undefined_apertures"] = sorted(
            self.referenced_apertures - set(self.apertures))
        facts["redefined_apertures"] = sorted(self.redefined_apertures)
        facts["token_count"] = self.tokens
        facts["limit_exceeded"] = self.limit_exceeded
        return facts

    @staticmethod
    def _aperture_fact(aperture, factor):
        def convert(value):
            if value is None or factor is None:
                return None
            return round(value * factor, 9)

        item = {
            "code": aperture["code"],
            "template": aperture["template"],
            "parameters": [round(value, 9) for value in aperture["parameters"]],
            "width_mm": convert(aperture.get("width")),
            "height_mm": convert(aperture.get("height")),
            "hole_mm": convert(aperture.get("hole")),
            "supported": bool(aperture["supported"]),
        }
        if aperture.get("vertices") is not None:
            item["vertices"] = aperture["vertices"]
        if aperture.get("reason"):
            item["unsupported_reason"] = aperture["reason"]
        return item

    @staticmethod
    def _contour_fact(contour, factor):
        return {
            "points": [
                [round(x * factor, 9), round(y * factor, 9)]
                for x, y in contour["points"]
            ],
            "closed": bool(contour["closed"]),
            "aperture": contour["aperture"],
            "width_mm": (
                round(contour["width"] * factor, 9)
                if contour["width"] is not None and factor is not None else None
            ),
            "region": bool(contour.get("region", False)),
        }


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def parse_gerber(data, file, options=None):
    """Parse bounded RS-274X Gerber bytes.

    Returns the contract dictionary (``kind``/``file``/``status``/``facts``/
    ``capability``/``findings``).  Content problems are findings; only argument
    type errors and invalid option values raise ``ValueError``.
    """
    max_objects = _validate_arguments(data, file, options)
    raw = bytes(data)
    if not raw:
        findings = [finding(
            "gerber.file_empty", "fail", "blocking",
            "Gerber file is empty (zero bytes)", file=file,
        )]
        return _result(file, _base_facts(), findings)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        facts = _base_facts()
        findings = [finding(
            "gerber.encoding_invalid", "fail", "blocking",
            "Gerber bytes are not valid UTF-8/ASCII and cannot be decoded strictly",
            file=file, evidence={"offset": exc.start, "reason": exc.reason},
        )]
        return _result(file, facts, findings)
    encoding = "utf-8"
    if text.startswith("\ufeff"):
        text = text[1:]
        encoding = "utf-8-sig"
    state = _GerberState(text, file, max_objects, encoding)
    return state.run()
