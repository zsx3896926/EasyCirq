"""D1: read-only Markdown discovery, anchors, links, script references, graph."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from . import CATALOG_VERSION, NOT_PROOF
from .common import (
    DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_TOTAL_CHARS, SKIP_DIRS, AuditError,
    base_result, column_of_offset, git_sha_for, is_external_target,
    is_within, line_of_offset, looks_placeholder, normalise_target,
    posix_rel, read_text, sha256_bytes, utc_now,
)

ENTRY = "SKILL.md"
MAX_REQUIRED_DEPTH = 3

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})", re.MULTILINE)
ATX_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
INLINE_LINK_RE = re.compile(
    r"\]\(\s*(?:<([^>]*)>|([^)\s]+))(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REF_DEF_RE = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*<?([^\s>]+)>?", re.MULTILINE)
SCRIPT_RE = re.compile(
    r"(?<![\w./-])((?:\.{1,2}/)*(?:scripts|tools)/[A-Za-z0-9_./-]+\.py)"
    r"((?:\s+[^\s`'\"<>|]+)*)")
PYTHON_SCRIPT_RE = re.compile(
    r"\bpython3?\s+((?:\.{1,2}/)*(?:scripts|tools)/[A-Za-z0-9_./-]+\.py)")

REQUIRED_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"(?:先|必须|务必|始终|一律|一定)(?:要)?(?:读|阅读|遵循|加载|按|执行)",
        r"必读", r"read\s+(?:this\s+)?first", r"must\s+read",
        r"required\s+reading", r"always\s+read", r"required\s*[:：]",
    )
]
CONDITIONAL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"按需", r"按任务", r"按阶段", r"需要时",
        r"[^。；;\n]{0,24}时[，,。]?\s*(?:再|先)?(?:读|阅读|加载|参考)",
        r"\bwhen\b", r"\bif\s+needed\b", r"\bas\s+needed\b", r"\bwhenever\b",
    )
]
EXAMPLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"示例", r"范例", r"样例", r"例[子如]", r"\bexample", r"\bsample",
    )
]
BACKGROUND_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"背景", r"延伸", r"更多", r"资料入口", r"可选", r"参考(?!设计)",
        r"\boptional\b", r"\bbackground\b", r"see\s+also", r"\bmore\b",
    )
]
PLACEHOLDER_PATH_RE = re.compile(r"[<>{}*$]|\.\.\.|…")


def slugify_heading(text):
    """GitHub-style heading anchor for the subset of characters we need."""
    out = []
    for ch in text.strip().lower():
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        elif ch.isspace():
            out.append("-")
    return "".join(out)


@dataclass
class Heading:
    level: int
    text: str
    line: int
    anchor: str
    occurrence: int = 0


@dataclass
class Link:
    line: int
    column: int
    text: str
    target: str
    kind: str = "unknown"
    role: str = "unknown"
    role_evidence: str = ""
    role_section: str = ""
    image: bool = False
    in_code_fence: bool = False
    external: bool = False
    placeholder: bool = False
    resolved: str | None = None
    anchor: str | None = None
    exists: bool | None = None
    anchor_exists: bool | None = None
    anchor_prefix: bool = False
    anchor_compat: bool = False
    case_mismatch: bool = False
    escapes_root: bool = False
    line_anchor: bool = False
    detail: str = ""


@dataclass
class ScriptRef:
    line: int
    path: str
    exists: bool
    placeholder: bool
    arguments: str = ""
    resolved: str | None = None


@dataclass
class FileRecord:
    path: str
    abspath: Path
    sha256: str
    bytes: int
    chars: int
    lines: int
    frontmatter: dict = field(default_factory=dict)
    title: str = ""
    headings: list = field(default_factory=list)
    links: list = field(default_factory=list)
    script_refs: list = field(default_factory=list)
    sections: list = field(default_factory=list)


def _strip_frontmatter(text):
    """Parse a leading ``---`` block as flat key/value pairs.

    Returns (frontmatter, body_start_offset).  A missing closing fence is
    treated as ordinary body text rather than guessed.
    """
    front = {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return front, 0
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        return front, 0
    for line in lines[1:closing]:
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            front[key.strip()] = value.strip()
    offset = sum(len(line) + 1 for line in lines[:closing + 1])
    return front, min(offset, len(text))


def _fence_spans(text):
    spans = []
    start = None
    marker = None
    for match in FENCE_RE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        if line_start != match.start() and text[line_start:match.start()].strip():
            continue
        char = match.group(1)[0]
        if start is None:
            start = match.start()
            marker = char
        elif marker == char:
            spans.append((start, match.end()))
            start = None
            marker = None
    if start is not None:
        spans.append((start, len(text)))
    return spans


def _inside(spans, offset):
    for start, end in spans:
        if start <= offset < end:
            return True
    return False


def _parse_headings(text, fences):
    headings = []
    seen = {}

    def add(raw, level, line_no):
        raw = re.sub(r"\s+#+\s*$", "", raw.strip()).strip()
        if not raw:
            return
        anchor = slugify_heading(raw)
        occurrence = seen.get(anchor, 0)
        seen[anchor] = occurrence + 1
        if occurrence:
            anchor = "%s-%d" % (anchor, occurrence)
        headings.append({
            "level": level, "text": raw, "line": line_no, "anchor": anchor,
        })

    lines = text.split("\n")
    offset = 0
    for index, line in enumerate(lines):
        if not _inside(fences, offset):
            match = ATX_RE.match(line)
            if match:
                add(match.group(2), len(match.group(1)), index + 1)
            elif SETEXT_RE.match(line) and index > 0:
                previous = lines[index - 1].strip()
                if previous and not previous.startswith(
                        ("#", "|", "-", "*", ">", "`")) \
                        and not SETEXT_RE.match(lines[index - 1]):
                    add(previous, 1 if line.strip().startswith("=") else 2,
                        index)
        offset += len(line) + 1
    return headings


def _nearest_heading(headings, line):
    current = ""
    for heading in headings:
        if heading["line"] <= line:
            current = heading["text"]
        else:
            break
    return current


def _classify_role(line_text, target, section, image):
    evidence = ""
    kind = "unknown"
    lower_target = target.lower()
    if is_external_target(target):
        return "external", "external_reference", ""
    if lower_target.split("#", 1)[0].split("?", 1)[0].endswith(".py"):
        kind = "script"
    elif lower_target.split("#", 1)[0].split("?", 1)[0].endswith(
            (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".pdf")):
        kind = "local_asset"
    elif image:
        kind = "local_asset"
    else:
        kind = "local_markdown"
    text = line_text or ""
    required_hit = None
    conditional_hit = None
    for pattern in REQUIRED_PATTERNS:
        match = pattern.search(text)
        if match and (required_hit is None or match.start() < required_hit.start()):
            required_hit = match
    for pattern in CONDITIONAL_PATTERNS:
        match = pattern.search(text)
        if match and (conditional_hit is None or
                      match.start() < conditional_hit.start()):
            conditional_hit = match
    # "涉及……时，先读……" is conditional even though it contains 先读.
    if conditional_hit is not None and (
            required_hit is None or conditional_hit.start() < required_hit.start()):
        return kind, "conditional_read", conditional_hit.group(0)
    if required_hit is not None:
        return kind, "required_read", required_hit.group(0)
    for pattern in EXAMPLE_PATTERNS:
        match = pattern.search(text)
        if match:
            return kind, "example", match.group(0)
    for pattern in BACKGROUND_PATTERNS:
        match = pattern.search(text)
        if match:
            return kind, "background", match.group(0)
    if "按需" in section or "索引" in section:
        return kind, "conditional_read", "section: " + section
    return kind, "unknown", ""


def _extract_links(text, fences, headings):
    links = []
    lines = text.split("\n")
    offsets = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1
    for match in INLINE_LINK_RE.finditer(text):
        raw = match.group(1) or match.group(2) or ""
        offset = match.start()
        fence = _inside(fences, offset)
        line_no = line_of_offset(text, offset)
        column = column_of_offset(text, offset)
        image = offset > 0 and text[offset - 1] == "!"
        line_text = lines[line_no - 1] if line_no - 1 < len(lines) else ""
        section = _nearest_heading(headings, line_no)
        link = Link(
            line=line_no, column=column,
            text=text[max(0, offset - 120):offset].strip()[-80:],
            target=raw.strip(), image=image, in_code_fence=fence,
        )
        link.kind, link.role, link.role_evidence = _classify_role(
            line_text, link.target, section, image)
        link.role_section = section
        links.append(link)
    for match in REF_DEF_RE.finditer(text):
        target = match.group(2).strip()
        offset = match.start(2)
        line_no = line_of_offset(text, offset)
        if _inside(fences, match.start()):
            continue
        link = Link(
            line=line_no, column=column_of_offset(text, offset),
            text=match.group(1), target=target,
            kind="external" if is_external_target(target) else "local_markdown",
            role="background" if is_external_target(target) else "unknown",
            role_evidence="reference definition",
            role_section=_nearest_heading(headings, line_no),
        )
        link.external = is_external_target(target)
        links.append(link)
    return links


def _script_refs(text, fences):
    refs = []
    seen = set()
    for regex in (PYTHON_SCRIPT_RE, SCRIPT_RE):
        for match in regex.finditer(text):
            if _inside(fences, match.start()) and regex is SCRIPT_RE:
                pass
            path = match.group(1)
            rest = match.group(2) if regex is SCRIPT_RE and match.lastindex and match.lastindex >= 2 else ""
            key = (line_of_offset(text, match.start()), path)
            if key in seen:
                continue
            seen.add(key)
            refs.append(ScriptRef(
                line=key[0], path=path, exists=False,
                placeholder=bool(looks_placeholder(path)),
                arguments=(rest or "").strip(),
            ))
    refs.sort(key=lambda item: (item.line, item.path))
    return refs


def _walk_files(root, exclude_abs):
    root = root.resolve()
    files = []
    dirs = set()
    symlink_escapes = []
    seen_real = {}
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        kept_dirs = []
        for name in sorted(dirnames):
            candidate = current_path / name
            rel_dir_name = posix_rel(candidate, root)
            if name in SKIP_DIRS:
                continue
            if candidate.is_symlink():
                try:
                    real_dir = candidate.resolve()
                except OSError:
                    continue
                if not is_within(real_dir, root):
                    symlink_escapes.append({
                        "path": rel_dir_name, "severity": "error",
                        "check": "symlink_escape", "source": rel_dir_name,
                        "line": 1, "target": str(real_dir),
                        "detail": "directory symlink resolves outside the "
                                  "declared root; not followed",
                    })
                continue
            if any(candidate.resolve() == excluded
                   or excluded in candidate.resolve().parents
                   for excluded in exclude_abs):
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        rel_dir = current_path.resolve().relative_to(root).as_posix()
        if rel_dir != ".":
            dirs.add(rel_dir)
        for name in sorted(filenames):
            path = current_path / name
            rel = path.resolve().relative_to(root).as_posix()
            if any(path.resolve() == excluded
                   or excluded in path.resolve().parents for excluded in exclude_abs):
                continue
            try:
                real = path.resolve()
            except OSError:
                continue
            if not is_within(real, root):
                symlink_escapes.append({
                    "path": rel, "severity": "error", "check": "symlink_escape",
                    "source": rel, "line": 1,
                    "target": str(real),
                    "detail": "symlink resolves outside the declared root",
                })
                continue
            if real in seen_real:
                continue
            seen_real[real] = rel
            files.append((rel, path))
            dirs.add(rel_dir if rel_dir != "." else ".")
    return files, dirs, symlink_escapes


def _resolve_link(link, source_path, root, all_files, all_dirs, case_map,
                  files_by_path):
    """Resolve one local link; populate existence/anchor/security fields."""
    target = link.target
    if not target:
        link.detail = "empty link target"
        return
    if is_external_target(target):
        link.external = True
        link.kind = "external"
        link.role = "external_reference" if link.role != "background" else link.role
        return
    if target.startswith("#"):
        link.kind = "anchor_only"
        link.resolved = source_path
        link.exists = True
        link.anchor = unquote(target[1:])
        _check_anchor(link, files_by_path.get(source_path))
        return
    path_part, anchor, _query = normalise_target(target)
    if not path_part:
        link.detail = "link has no path"
        return
    if looks_placeholder(path_part):
        link.placeholder = True
        link.detail = "placeholder path; not checked as a live reference"
        return
    if path_part.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", path_part):
        link.escapes_root = True
        link.detail = "absolute path is outside the declared root"
        return
    source_dir = Path(source_path).parent.as_posix()
    joined = path_part if source_dir in ("", ".") else source_dir + "/" + path_part
    normalised = os.path.normpath(joined).replace("\\", "/")
    if normalised == ".":
        normalised = ""
    if normalised.startswith("../") or normalised == ".." or normalised.startswith("/"):
        link.escapes_root = True
        link.detail = "relative path escapes the declared root"
        return
    if normalised in all_dirs or normalised in ("", "."):
        link.resolved = normalised
        link.exists = True
        link.detail = "directory link"
        return
    candidate = normalised
    if candidate not in all_files:
        case_candidate = case_map.get(candidate.casefold())
        if case_candidate is not None:
            link.case_mismatch = True
            candidate = case_candidate
        else:
            link.exists = False
            link.detail = "path does not exist"
            return
    link.resolved = candidate
    link.exists = True
    target_file = files_by_path.get(candidate)
    if target_file is not None and anchor:
        link.anchor = anchor
        _check_anchor(link, target_file)


def _check_anchor(link, target_file):
    if target_file is None:
        return
    anchor = link.anchor or ""
    match = re.fullmatch(r"L(\d+)", anchor)
    if match:
        link.line_anchor = True
        link.anchor_exists = int(match.group(1)) <= max(1, target_file.lines)
        return
    if not anchor:
        link.anchor_exists = True
        return
    wanted = unquote(anchor).strip()
    anchors = {heading["anchor"] for heading in target_file.headings}
    ascii_lower = {heading["anchor"].lower() for heading in target_file.headings}
    texts = {slugify_heading(heading["text"]) for heading in target_file.headings}
    if wanted in anchors or wanted.lower() in ascii_lower or wanted in texts:
        link.anchor_exists = True
        return
    import unicodedata
    folded = {unicodedata.normalize("NFKC", name) for name in anchors}
    if unicodedata.normalize("NFKC", wanted) in folded:
        link.anchor_exists = True
        link.anchor_compat = True
        link.detail = "anchor matches only after Unicode compatibility folding"
        return
    # Some pages link to a heading truncated at a parenthesis ("#g1-ldo" for
    # "## G1 LDO（...）").  That is not an exact GitHub slug; keep it visible
    # as a structural warning instead of pretending it resolves exactly.
    if len(wanted) >= 3 and any(
            candidate.startswith(wanted) for candidate in anchors):
        link.anchor_exists = True
        link.anchor_prefix = True
        link.detail = "anchor matches a heading only by prefix"
        return
    link.anchor_exists = False


def load_ignore_file(path):
    import json
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"cannot read ignore file {path}: {exc}")
    if not isinstance(data, dict) or data.get("schema") != "ska-ignore/v1":
        raise AuditError("ignore file must be an object with schema ska-ignore/v1")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise AuditError("ignore file 'rules' must be a list")
    checked = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise AuditError(f"ignore rule {index} must be an object")
        reason = str(rule.get("reason") or "").strip()
        target = str(rule.get("target") or "").strip()
        scope = str(rule.get("scope") or "").strip()
        check = str(rule.get("check") or "").strip()
        if not reason:
            raise AuditError(f"ignore rule {index}: reason is required")
        if not target or target in ("*", "**"):
            raise AuditError(f"ignore rule {index}: exact target is required")
        if not check:
            raise AuditError(f"ignore rule {index}: check is required")
        if not scope.startswith(("file:", "finding:")):
            raise AuditError(
                f"ignore rule {index}: scope must be file:<path> or finding:<id>")
        if "*" in scope or "**" in scope:
            raise AuditError(f"ignore rule {index}: wildcard scope is not allowed")
        checked.append({
            "id": str(rule.get("id") or "IGN-%03d" % (index + 1)),
            "check": check, "target": target, "scope": scope,
            "reason": reason,
        })
    return checked


def _apply_ignores(findings, ignores):
    applied = []
    for finding in findings:
        for rule in ignores:
            if finding["check"] != rule["check"]:
                continue
            if finding.get("target") != rule["target"] \
                    and finding.get("link_target") != rule["target"]:
                continue
            scope = rule["scope"]
            allowed = False
            if scope.startswith("file:"):
                allowed = finding.get("source", "").startswith(scope[5:])
            elif scope.startswith("finding:"):
                allowed = finding.get("id") == scope[8:]
            if allowed:
                finding["ignored"] = True
                finding["ignore_id"] = rule["id"]
                finding["ignore_reason"] = rule["reason"]
                applied.append({
                    "id": rule["id"], "finding": finding["id"],
                    "check": finding["check"], "target": finding.get("target"),
                    "reason": rule["reason"],
                })
                break
    return applied


def scan_root(root, *, max_file_bytes=DEFAULT_MAX_FILE_BYTES,
              max_total_chars=DEFAULT_MAX_TOTAL_CHARS,
              exclude_abs=(), ignore_rules=None, started=None):
    """Scan ``root`` and return a JSON-serialisable result plus parsed index."""
    started_at = started or utc_now()
    begin = time.perf_counter()
    root = Path(root)
    if not root.is_dir():
        raise AuditError(f"scan root is not a directory: {root}")
    root = root.resolve()
    if not (root / ENTRY).is_file():
        raise AuditError(f"scan root has no {ENTRY}: {root}")
    exclude_abs = tuple(Path(item).resolve() for item in exclude_abs if item)
    files, dirs, symlink_escapes = _walk_files(root, exclude_abs)
    md_files = [(rel, path) for rel, path in files
                if path.suffix.lower() in (".md", ".markdown")]
    if not md_files:
        raise AuditError(f"no Markdown files found under {root}")

    all_files = {rel for rel, _ in files}
    all_dirs = set(dirs)
    all_dirs.add(".")
    case_map = {}
    for rel in sorted(all_files | all_dirs):
        case_map.setdefault(rel.casefold(), rel)
    files_by_path = {}
    records = {}
    repo_root = root.parent if (root.parent / "tools").is_dir() else None
    total_chars = 0
    for rel, path in md_files:
        if path.stat().st_size > max_file_bytes:
            raise AuditError(
                f"input file exceeds max_file_bytes ({max_file_bytes}): {rel}")
        try:
            text, raw = read_text(path)
        except UnicodeDecodeError:
            raise AuditError(f"Markdown file is not valid UTF-8: {rel}")
        total_chars += len(text)
        if total_chars > max_total_chars:
            raise AuditError(
                f"input exceeds max_total_chars ({max_total_chars})")
        frontmatter, _ = _strip_frontmatter(text)
        fences = _fence_spans(text)
        headings = _parse_headings(text, fences)
        title = ""
        for heading in headings:
            if heading["level"] == 1:
                title = heading["text"]
                break
        if not title and headings:
            title = headings[0]["text"]
        record = FileRecord(
            path=rel, abspath=path, sha256=sha256_bytes(raw),
            bytes=len(raw), chars=len(text), lines=text.count("\n") + 1,
            frontmatter=frontmatter, title=title, headings=headings,
        )
        record.links = _extract_links(text, fences, headings)
        record.script_refs = _script_refs(text, fences)
        records[rel] = record
    if ENTRY not in records and "design-hardware/SKILL.md" in records:
        pass

    findings = []
    finding_seq = [0]

    def add_finding(severity, check, source, line, target, detail, **extra):
        finding_seq[0] += 1
        item = {
            "id": "F%04d" % finding_seq[0],
            "severity": severity,
            "check": check,
            "source": source,
            "line": line,
            "target": target,
            "detail": detail,
        }
        item.update(extra)
        findings.append(item)
        return item

    for escape in symlink_escapes:
        add_finding("error", "symlink_escape", escape["source"],
                    escape["line"], escape["target"], escape["detail"])

    # Resolve links after every file's headings are known.
    for rel in sorted(records):
        record = records[rel]
        for link in record.links:
            original = link.target
            _resolve_link(link, rel, root, all_files, all_dirs, case_map,
                          records)
            if link.in_code_fence:
                add_finding("info", "link_in_code_fence", rel, link.line,
                            original,
                            "link inside a fenced code block; not a live "
                            "dependency")
                continue
            if link.external:
                continue
            if link.placeholder:
                add_finding("info", "placeholder_link", rel, link.line,
                            original, link.detail)
                continue
            if link.escapes_root:
                add_finding("error", "unsafe_target", rel, link.line,
                            original, link.detail,
                            link_target=original)
                continue
            if link.exists is False:
                add_finding("error", "broken_link", rel, link.line, original,
                            "target path missing: %s" % (link.resolved or ""),
                            link_target=original)
                continue
            if link.case_mismatch:
                add_finding("warning", "case_mismatch", rel, link.line,
                            original,
                            "resolved with different letter case: %s"
                            % link.resolved, link_target=original)
            if link.anchor_prefix:
                add_finding("warning", "anchor_prefix_match", rel, link.line,
                            original,
                            "anchor matches a heading only by prefix: #%s"
                            % link.anchor, link_target=original)
            if link.anchor_compat:
                add_finding("warning", "anchor_compat_match", rel, link.line,
                            original,
                            "anchor matches only after NFKC folding: #%s"
                            % link.anchor, link_target=original)
            if link.anchor and link.anchor_exists is False:
                add_finding("error", "missing_anchor", rel, link.line,
                            original,
                            "anchor not found in %s: #%s"
                            % (link.resolved, link.anchor),
                            link_target=original)
        # duplicate heading anchors within one file
        anchors = {}
        for heading in record.headings:
            anchors.setdefault(heading["anchor"], []).append(heading)
        for anchor, items in anchors.items():
            if len(items) > 1:
                add_finding("warning", "duplicate_heading_anchor", rel,
                            items[1]["line"], "#" + anchor,
                            "%d headings share the generated anchor" % len(items))
        # script references, resolved against root then file directory
        for ref in record.script_refs:
            ref.path = ref.path.replace("\\", "/")
            if ref.placeholder:
                add_finding("info", "placeholder_script", rel, ref.line,
                            ref.path, "placeholder script path")
                continue
            candidates = []
            if ref.path.startswith("./"):
                candidates.append(os.path.normpath(
                    Path(rel).parent.as_posix() + "/" + ref.path[2:]))
            candidates.append(os.path.normpath(ref.path).replace("\\", "/"))
            candidates.append(os.path.normpath(
                Path(rel).parent.as_posix() + "/" + ref.path).replace("\\", "/"))
            ref.resolved = next((item for item in candidates
                                 if item in all_files), None)
            ref.exists = ref.resolved is not None
            if not ref.exists and repo_root is not None and \
                    ref.path.startswith(("tools/", "./tools/")):
                repo_candidate = (repo_root / ref.path.lstrip("./")).resolve()
                if is_within(repo_candidate, repo_root) and repo_candidate.is_file():
                    ref.resolved = os.path.relpath(
                        repo_candidate, root).replace("\\", "/")
                    ref.exists = True
            if not ref.exists:
                add_finding("error", "broken_script_ref", rel, ref.line,
                            ref.path, "script path is not in the package")

    # duplicate titles / same basenames across the corpus (structure hints)
    title_groups = {}
    basename_groups = {}
    for rel, record in records.items():
        if record.title:
            key = re.sub(r"[\s\W_]+", "", record.title.lower())
            if len(key) >= 4:
                title_groups.setdefault(key, []).append(rel)
        if Path(rel).name.lower() not in ("readme.md", "index.md"):
            basename_groups.setdefault(Path(rel).name.casefold(), []).append(rel)
    duplicate_topics = []
    for key, paths in sorted(title_groups.items()):
        if len(paths) > 1:
            duplicate_topics.append({
                "kind": "duplicate_title",
                "topic": records[paths[0]].title,
                "paths": sorted(paths),
            })
    for name, paths in sorted(basename_groups.items()):
        if len(paths) > 1 and not any(p in [d["paths"] for d in []] for p in []):
            duplicate_topics.append({
                "kind": "duplicate_basename",
                "topic": name,
                "paths": sorted(paths),
            })

    md_edges = []
    for rel, record in records.items():
        for link in record.links:
            if link.external or link.in_code_fence:
                continue
            if link.resolved in records:
                md_edges.append({
                    "source": rel, "target": link.resolved,
                    "line": link.line, "role": link.role,
                    "required": link.role == "required_read" and
                    not link.escapes_root and link.exists is not False,
                })

    required_closure, depth, over_deep, required_missing = _required_closure(
        records, md_edges)
    cycles = _cycles(records, md_edges)
    orphans = _orphans(records, md_edges)
    unreachable = _unreachable(records, md_edges, ENTRY)

    applied_ignores = _apply_ignores(findings, ignore_rules or [])
    counts = {"files": len(records), "links": 0, "required_links": 0,
              "errors": 0, "warnings": 0, "info": 0, "ignored": 0}
    for record in records.values():
        counts["links"] += len(record.links)
        counts["required_links"] += sum(
            1 for link in record.links if link.role == "required_read")
    severity_keys = {"error": "errors", "warning": "warnings", "info": "info"}
    for finding in findings:
        if finding.get("ignored"):
            counts["ignored"] += 1
            continue
        key = severity_keys[finding["severity"]]
        counts[key] = counts.get(key, 0) + 1
    findings.sort(key=lambda item: (
        item["source"], item["line"], item["check"], item["target"]))
    duration_ms = round((time.perf_counter() - begin) * 1000, 3)

    result = base_result("scan", root, git_sha_for(root), started_at,
                         duration_ms, counts.get("errors", 0) == 0)
    result.update({
        "catalog_version": CATALOG_VERSION,
        "limits": {"max_file_bytes": max_file_bytes,
                   "max_total_chars": max_total_chars},
        "excluded_outputs": [str(item) for item in exclude_abs],
        "counts": counts,
        "files": [_file_to_json(record) for record in
                  sorted(records.values(), key=lambda item: item.path)],
        "graph": {
            "entry": ENTRY,
            "required_closure": required_closure,
            "required_depth": depth,
            "over_deep_required": over_deep,
            "required_missing": required_missing,
            "cycles": cycles,
            "orphans": orphans,
            "unreachable": unreachable,
            "duplicate_topics": duplicate_topics,
        },
        "ignored": applied_ignores,
        "findings": findings,
        "not_proof": NOT_PROOF + " 本命令不验证外链，也不执行任何脚本。",
    })
    result["ok"] = counts.get("errors", 0) == 0
    index = {
        "root": root, "records": records, "files": all_files,
        "dirs": all_dirs, "excluded": exclude_abs,
        "limits": {"max_file_bytes": max_file_bytes,
                   "max_total_chars": max_total_chars},
    }
    return result, index


def _file_to_json(record):
    return {
        "path": record.path,
        "sha256": record.sha256,
        "bytes": record.bytes,
        "chars": record.chars,
        "lines": record.lines,
        "title": record.title,
        "frontmatter": record.frontmatter,
        "headings": record.headings,
        "links": [{
            "line": link.line, "column": link.column,
            "text": link.text, "target": link.target,
            "kind": link.kind, "role": link.role,
            "role_evidence": link.role_evidence,
            "role_section": link.role_section,
            "resolved": link.resolved, "anchor": link.anchor,
            "exists": link.exists, "anchor_exists": link.anchor_exists,
            "anchor_prefix": link.anchor_prefix,
            "anchor_compat": link.anchor_compat,
            "external": link.external, "placeholder": link.placeholder,
            "case_mismatch": link.case_mismatch,
            "escapes_root": link.escapes_root,
            "line_anchor": link.line_anchor,
            "in_code_fence": link.in_code_fence,
            "image": link.image, "detail": link.detail,
        } for link in record.links],
        "script_refs": [{
            "line": ref.line, "path": ref.path, "exists": ref.exists,
            "placeholder": ref.placeholder, "arguments": ref.arguments,
            "resolved": ref.resolved,
        } for ref in record.script_refs],
    }


def _required_closure(records, edges):
    required_edges = {}
    for edge in edges:
        if edge["required"]:
            required_edges.setdefault(edge["source"], []).append(edge["target"])
    for key in required_edges:
        required_edges[key] = sorted(set(required_edges[key]))
    closure = []
    depth = {}
    over_deep = []
    missing = []
    queue = [(ENTRY, 0)] if ENTRY in records else []
    while queue:
        node, level = queue.pop(0)
        if node in depth and depth[node] <= level:
            continue
        depth[node] = level
        closure.append(node)
        if level > MAX_REQUIRED_DEPTH:
            over_deep.append({"path": node, "depth": level})
            continue
        for target in required_edges.get(node, []):
            if target not in records:
                missing.append({"source": node, "target": target,
                                "depth": level + 1})
                continue
            queue.append((target, level + 1))
    closure.sort()
    return closure, (max(depth.values()) if depth else 0), \
        sorted(over_deep, key=lambda item: (item["depth"], item["path"])), \
        sorted(missing, key=lambda item: (item["source"], item["target"]))


def _cycles(records, edges):
    """Tarjan SCC over Markdown files; return sorted non-trivial components."""
    graph = {}
    for edge in edges:
        if edge["source"] == edge["target"]:
            graph.setdefault(edge["source"], set()).add(edge["target"])
        else:
            graph.setdefault(edge["source"], set()).add(edge["target"])
    index = {}
    low = {}
    stack = []
    on_stack = set()
    components = []
    counter = [0]

    def strongconnect(node):
        index[node] = counter[0]
        low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph.get(node, ())):
            if target not in graph and target not in records:
                continue
            if target not in index:
                strongconnect(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], index[target])
        if low[node] == index[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.discard(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1 or (len(component) == 1 and
                                      component[0] in graph.get(component[0], ())):
                components.append(sorted(component))

    for node in sorted(records):
        if node not in index:
            strongconnect(node)
    return sorted(components)


def _orphans(records, edges):
    inbound = set()
    for edge in edges:
        if edge["source"] != edge["target"]:
            inbound.add(edge["target"])
    return sorted(path for path in records if path != ENTRY and path not in inbound)


def _unreachable(records, edges, entry):
    graph = {}
    for edge in edges:
        graph.setdefault(edge["source"], set()).add(edge["target"])
    seen = set()
    queue = [entry] if entry in records else []
    while queue:
        node = queue.pop()
        if node in seen:
            continue
        seen.add(node)
        for target in sorted(graph.get(node, ())):
            if target in records and target not in seen:
                queue.append(target)
    return sorted(path for path in records if path != entry and path not in seen)


def discover_default_root(cwd):
    cwd = Path(cwd).resolve()
    if (cwd / "design-hardware" / ENTRY).is_file():
        return cwd / "design-hardware"
    if (cwd / ENTRY).is_file():
        return cwd
    if cwd.name in ("scripts", "skill_knowledge_audit") and \
            (cwd.parent / ENTRY).is_file():
        return cwd.parent
    raise AuditError(
        "cannot infer scan root; pass --root <design-hardware directory>")
