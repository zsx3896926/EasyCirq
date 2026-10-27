"""Content-first format detection and filename role hints.

The filename is only a hint.  ``detect_kind`` reads signatures from the bytes so
a ``.gbr`` file that actually contains a mask image, a BOM or garbage is not
silently accepted because its extension looks right.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import PurePosixPath

GERBER_FS = re.compile(r"%FS[LT]?[AI]?X\d+Y\d+\*%")
GERBER_MO = re.compile(r"%MO(?:MM|IN)\*%")
GERBER_ADD = re.compile(r"%ADD\d+")
DRILL_HEADER = re.compile(r"(?m)^M48\s*$")
DRILL_TOOL = re.compile(r"(?m)^T\d+C[\d.]+")
EXTENSION_KIND = {
    ".gbr": "gerber", ".gtl": "gerber", ".gbl": "gerber", ".gts": "gerber",
    ".gbs": "gerber", ".gto": "gerber", ".gbo": "gerber", ".gtp": "gerber",
    ".gbp": "gerber", ".gm1": "gerber", ".gko": "gerber", ".ger": "gerber",
    ".drl": "drill", ".xln": "drill", ".csv": "csv", ".tsv": "csv",
    ".pdf": "pdf", ".svg": "svg", ".png": "png", ".json": "json",
    ".zip": "zip",
}
SYSTEM_FILES = {".ds_store", "thumbs.db", "desktop.ini"}


def _decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _looks_like_csv(text):
    try:
        sample = text[:65536]
        rows = list(csv.reader(io.StringIO(sample)))
    except csv.Error:
        return False
    rows = [row for row in rows[:20] if row]
    if not rows:
        return False
    width = len(rows[0])
    if width < 2:
        return False
    if any(len(row) != width for row in rows):
        # Quoted embedded newlines make short samples jagged; only trust a
        # consistent prefix when we actually saw the end of the sample.
        if len(text) > 65536 or len(rows) > 3:
            return False
        return False
    return True


def _first_content_line(text):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _looks_like_gerber(text):
    """A content signature plus a plausible Gerber opening command.

    Documentation that merely quotes ``%FS``/``M02`` must not be parsed as a
    manufacturing file; real Gerber data starts with an extended command or a
    G/D/X/Y word command.
    """
    if not (GERBER_FS.search(text)
            or (GERBER_MO.search(text) and GERBER_ADD.search(text)
                and "M02" in text)):
        return False
    first = _first_content_line(text)
    if not first:
        return False
    return bool(re.match(r"^(?:%|G0?4|G75|G01|G54|D\d+|X[-+]?\d|Y[-+]?\d)",
                         first, flags=re.IGNORECASE))


def _looks_like_drill(text):
    if not (DRILL_HEADER.search(text[:4096]) and DRILL_TOOL.search(text[:65536])):
        return False
    lines = [line.strip() for line in text[:4096].splitlines()]
    for line in lines:
        if not line or line.startswith(";") or line == "%" or line.startswith("M47"):
            continue
        return line.upper().startswith("M48")
    return False


def _is_system_artifact(name):
    parts = PurePosixPath(name).parts
    lowered = [part.casefold() for part in parts]
    if any(part in SYSTEM_FILES for part in lowered):
        return True
    return any(part == "__macosx" for part in lowered)


def detect_kind(data, name):
    """Return ``{kind, confidence, evidence, extension}`` for one file.

    ``kind`` is ``empty``/``gerber``/``drill``/``csv``/``json``/``pdf``/``svg``/
    ``png``/``zip``/``text``/``binary``/``unknown``.  ``confidence`` is
    ``content`` when the bytes were recognised and ``none`` when no content
    signature matched (the extension is only recorded as a clue).
    """
    extension = PurePosixPath(name).suffix.lower()
    if not data:
        return {"kind": "empty", "confidence": "content", "evidence": "zero bytes",
                "extension": extension}
    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        return {"kind": "zip", "confidence": "content", "evidence": "ZIP signature",
                "extension": extension}
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return {"kind": "png", "confidence": "content", "evidence": "PNG signature",
                "extension": extension}
    if data.startswith(b"%PDF-"):
        return {"kind": "pdf", "confidence": "content", "evidence": "PDF signature",
                "extension": extension}
    text = _decode_text(data[:4 * 1024 * 1024])
    if text is None:
        kind = "binary"
        return {"kind": kind, "confidence": "none",
                "evidence": "not valid UTF-8/UTF-16 text after magic checks",
                "extension": extension}
    head = text.lstrip("\ufeff \t\r\n")
    if head.startswith("<svg") or ("<svg" in head[:512] and head.startswith("<?xml")):
        return {"kind": "svg", "confidence": "content", "evidence": "SVG element",
                "extension": extension}
    if head.startswith("{") or head.startswith("["):
        try:
            json.loads(text)
        except (ValueError, RecursionError):
            pass
        else:
            return {"kind": "json", "confidence": "content", "evidence": "parsed JSON",
                    "extension": extension}
    if _looks_like_gerber(text):
        return {"kind": "gerber", "confidence": "content",
                "evidence": "RS-274X format/unit/aperture signature",
                "extension": extension}
    if _looks_like_drill(text):
        return {"kind": "drill", "confidence": "content",
                "evidence": "Excellon M48 header and tool table", "extension": extension}
    if _looks_like_csv(text):
        return {"kind": "csv", "confidence": "content",
                "evidence": "consistent delimited rows", "extension": extension}
    printable = sum(1 for char in text[:4096] if char.isprintable() or char in "\r\n\t")
    if printable >= max(1, int(0.95 * len(text[:4096]))):
        return {"kind": "text", "confidence": "none",
                "evidence": "printable text without a recognised signature",
                "extension": extension}
    return {"kind": "unknown", "confidence": "none",
            "evidence": "no recognised signature", "extension": extension}


def extension_mismatch(detection):
    """True when the extension suggests a different known content kind."""
    expected = EXTENSION_KIND.get(detection.get("extension"))
    if not expected or detection.get("kind") in ("empty",):
        return False
    if expected == detection.get("kind"):
        return False
    # A CSV detector legitimately also handles tab/semicolon BOM exports, and a
    # drill file with a .gbr extension is still a mismatch worth reporting.
    return True


def is_system_artifact(name):
    return _is_system_artifact(name)


ROLE_HINTS = (
    ("board_profile", re.compile(r"(?:^|[^a-z])(?:profile|outline|edge|contour|gko|gm1)(?:[^a-z]|$)")),
    ("drill", re.compile(r"(?:^|[^a-z])(?:drill|drl|xln|npth|pth|holes)(?:[^a-z]|$)")),
    ("copper_top", re.compile(r"(?:^|[^a-z])(?:gtl|f_cu|copper[_ -]?top|top[_ -]?copper)(?:[^a-z]|$)")),
    ("copper_bottom", re.compile(r"(?:^|[^a-z])(?:gbl|b_cu|copper[_ -]?bot(?:tom)?|bot(?:tom)?[_ -]?copper)(?:[^a-z]|$)")),
    ("copper_inner", re.compile(r"(?:^|[^a-z])(?:inr|inner|copper[_ -]?inner|g[23]|l[2-9])(?:[^a-z]|$)")),
    ("soldermask_top", re.compile(r"(?:^|[^a-z])(?:gts|f_mask|soldermask[_ -]?top|mask[_ -]?top|top[_ -]?mask|sm[_ -]?top)(?:[^a-z]|$)")),
    ("soldermask_bottom", re.compile(r"(?:^|[^a-z])(?:gbs|b_mask|soldermask[_ -]?bot(?:tom)?|mask[_ -]?bot(?:tom)?|bot(?:tom)?[_ -]?mask)(?:[^a-z]|$)")),
    ("silkscreen_top", re.compile(r"(?:^|[^a-z])(?:gto|f_silk|silk(?:screen)?[_ -]?top|top[_ -]?silk(?:screen)?|legend[_ -]?top|sst)(?:[^a-z]|$)")),
    ("silkscreen_bottom", re.compile(r"(?:^|[^a-z])(?:gbo|b_silk|silk(?:screen)?[_ -]?bot(?:tom)?|bot(?:tom)?[_ -]?silk(?:screen)?|legend[_ -]?bot(?:tom)?)(?:[^a-z]|$)")),
    ("paste_top", re.compile(r"(?:^|[^a-z])(?:gtp|f_paste|paste[_ -]?top|top[_ -]?paste|cream[_ -]?top)(?:[^a-z]|$)")),
    ("paste_bottom", re.compile(r"(?:^|[^a-z])(?:gbp|b_paste|paste[_ -]?bot(?:tom)?|bot(?:tom)?[_ -]?paste|cream[_ -]?bot(?:tom)?)(?:[^a-z]|$)")),
    ("bom", re.compile(r"(?:^|[^a-z])(?:bom|b\.o\.m|bill[_ -]?of[_ -]?materials|物料)(?:[^a-z]|$)")),
    ("cpl", re.compile(r"(?:^|[^a-z])(?:cpl|pos|pick|place|centroid|坐标|贴片)(?:[^a-z]|$)")),
    ("assembly_drawing", re.compile(r"(?:^|[^a-z])(?:assembly|装配)(?:[^a-z]|$)")),
    ("test_plan", re.compile(r"(?:^|[^a-z])(?:test[_ -]?plan|测试)(?:[^a-z]|$)")),
    ("layer_stack_doc", re.compile(r"(?:^|[^a-z])(?:stack[_ -]?up|stackup|层叠)(?:[^a-z]|$)")),
    ("schematic_pdf", re.compile(r"(?:^|[^a-z])(?:schematic|sch|原理图)(?:[^a-z]|$)")),
    ("readme", re.compile(r"(?:^|[^a-z])(?:readme)(?:[^a-z]|$)")),
)


def infer_role(name):
    """Return a filename-based role hint or ``None``.

    The hint is always ``source='inferred'``; it never proves layer identity.
    """
    path = PurePosixPath(name)
    lowered = path.name.casefold()
    suffix = path.suffix.casefold()
    if suffix in (".epro2", ".epro", ".eprj3", ".kicad_pcb", ".kicad_sch"):
        return {"role": "native_project", "layer_index": None, "source": "inferred"}
    stem = lowered[: -len(suffix)] if suffix else lowered
    for role, pattern in ROLE_HINTS:
        if pattern.search(stem):
            layer_index = None
            if role == "copper_inner":
                match = re.search(r"(?:inner|inr|l|g)([2-9])", stem)
                if match:
                    layer_index = int(match.group(1))
            if role == "schematic_pdf" and suffix not in (".pdf", ".svg", ".png"):
                continue
            return {"role": role, "layer_index": layer_index, "source": "inferred"}
    if suffix in (".pdf", ".svg") and "sch" in stem:
        return {"role": "schematic_pdf", "layer_index": None, "source": "inferred"}
    return None
