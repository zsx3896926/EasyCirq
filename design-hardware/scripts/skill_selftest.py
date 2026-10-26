#!/usr/bin/env python3
"""Read-only self-test for the design-hardware skill package.

What it checks:
  1. required files exist (gate docs, templates, scripts, regression case);
  2. every relative Markdown link in design-hardware/**/*.md resolves;
  3. gate keys G0_requirements..G6_manufacturing and the four status words
     are consistent across SKILL.md, references/design-gates.md and
     scripts/gate_check.py;
  4. scripts/gate_check.py reproduces cases/temp-alarm-2026-10-24/expected.json
     (executed as a subprocess; gate logic is not duplicated here);
  5. every scripts/*.py compiles with py_compile (no script is executed).

No EDA, no network, no project writes. A pass here does not verify any board,
any manufacturing file or any physical build.

Exit codes: 0 = every check passed; 1 = at least one FAIL or NOT RUN;
2 = usage or IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

RESULT_SCHEMA = "skill-selftest/v1"
SELFTEST_ONLY = "SELF-TEST ONLY — not a hardware verification"

GATE_KEYS = [
    "G0_requirements",
    "G1_function_freeze",
    "G2_schematic",
    "G3_layout",
    "G4_power_ground",
    "G5_routing",
    "G6_manufacturing",
]
STATUS_WORDS = ["PASS", "PASS_WITH_WAIVER", "BLOCKED", "UNSUPPORTED"]
GATE_NAME_FILES = ["SKILL.md", "references/design-gates.md", "scripts/gate_check.py"]
STATUS_NAME_FILES = ["references/design-gates.md", "scripts/gate_check.py"]
CASE_REL = "cases/temp-alarm-2026-10-24"

REQUIRED_FILES = [
    "SKILL.md",
    "references/design-gates.md",
    "references/pcb-routing-strategy.md",
    "references/tool-gotchas.md",
    "assets/design-state.example.json",
    "assets/design-brief.md",
    "assets/routing-plan.md",
    "assets/design-calc.md",
    "scripts/gate_check.py",
    "scripts/bom_check.py",
    "scripts/layout_from_easyeda.py",
    "scripts/svg_text_bbox.py",
    "scripts/pin_net_intent_check.py",
    "scripts/pcb_preflight.py",
    "scripts/pcb_apply_plan.py",
    "scripts/pcb_gate.py",
    "scripts/pcb_case.py",
    "references/pcb-command-map.json",
    "cases/temp-alarm-2026-10-24/README.md",
    "cases/temp-alarm-2026-10-24/expected.json",
]

INLINE_LINK = re.compile(
    r"\]\(\s*(?:<([^>]*)>|([^)\s]+))(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
REF_DEFINITION = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?", re.MULTILINE)
FENCE = re.compile(r"```.*?```", re.DOTALL)
GATE_TOKEN = re.compile(r"\bG[0-9]+_[a-z][a-z0-9_]*\b")
GATE_SHORT = re.compile(r"^G([0-6])$", re.IGNORECASE)

SKIP_LINK_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "data:",
    "javascript:",
)


def _check(check_id, status, summary, details=None):
    return {
        "id": check_id,
        "status": status,
        "summary": summary,
        "details": details or [],
    }


def _read_text(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def _inside_span(offset, spans):
    return any(start <= offset < end for start, end in spans)


def check_required_files(root):
    missing = []
    found = []
    for rel in REQUIRED_FILES:
        path = root / rel
        if path.is_file():
            found.append(rel)
        else:
            missing.append(rel)
    docs = sorted((root / "assets/docs").glob("*.md")) if (root / "assets/docs").is_dir() else []
    if not docs:
        missing.append("assets/docs/*.md")
    else:
        found.extend(str(p.relative_to(root)).replace("\\", "/") for p in docs)
    if missing:
        return _check(
            "required-files",
            "FAIL",
            f"{len(missing)} required path(s) missing",
            [f"missing: {item}" for item in missing],
        )
    return _check(
        "required-files",
        "PASS",
        f"{len(found)} required paths present",
        found,
    )


def _iter_markdown_links(text):
    spans = [(m.start(), m.end()) for m in FENCE.finditer(text)]
    for match in INLINE_LINK.finditer(text):
        if not _inside_span(match.start(), spans):
            yield (match.group(1) or match.group(2)), match.start()
    for match in REF_DEFINITION.finditer(text):
        if not _inside_span(match.start(), spans):
            yield match.group(1), match.start()


def _is_external(target):
    lower = target.lower()
    if lower.startswith(SKIP_LINK_PREFIXES) or lower.startswith("#"):
        return True
    if target.startswith("/"):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", target):
        return True
    return False


def check_markdown_links(root):
    broken = []
    checked = 0
    files = sorted(root.rglob("*.md"))
    for md in files:
        if "__pycache__" in md.parts:
            continue
        text = _read_text(md)
        for raw, offset in _iter_markdown_links(text):
            target = raw.strip()
            if not target or _is_external(target):
                continue
            target = target.split("#", 1)[0].split("?", 1)[0]
            target = unquote(target)
            if not target:
                continue
            checked += 1
            candidate = (md.parent / target).resolve()
            if not candidate.exists():
                broken.append(
                    f"{md.relative_to(root)}:{_line_of(text, offset)} -> {raw}"
                )
    if broken:
        return _check(
            "markdown-links",
            "FAIL",
            f"{len(broken)} of {checked} relative link(s) do not resolve",
            broken,
        )
    return _check(
        "markdown-links",
        "PASS",
        f"{checked} relative link(s) in {len(files)} Markdown file(s) resolve",
    )


def check_gate_naming(root):
    missing_files = [rel for rel in STATUS_NAME_FILES if not (root / rel).is_file()]
    if not (root / "SKILL.md").is_file() and "SKILL.md" not in missing_files:
        missing_files.insert(0, "SKILL.md")
    if missing_files:
        return _check(
            "gate-naming",
            "NOT RUN",
            "gate documents or checker not present yet",
            [f"missing: {rel}" for rel in missing_files],
        )

    details = []
    failed = False
    texts = {}
    for rel in GATE_NAME_FILES:
        path = root / rel
        if not path.is_file():
            details.append(f"missing: {rel}")
            failed = True
            continue
        text = _read_text(path)
        texts[rel] = text
        absent = [key for key in GATE_KEYS if key not in text]
        if absent:
            failed = True
            details.append(f"{rel}: missing gate key(s): {', '.join(absent)}")
            if rel == "SKILL.md":
                details.append(
                    "hint: SKILL.md must spell the fixed gate keys "
                    "(a G0..G6 -> key table is enough); see references/design-gates.md"
                )
        drifted = sorted(set(GATE_TOKEN.findall(text)) - set(GATE_KEYS))
        if drifted:
            failed = True
            details.append(f"{rel}: unknown gate key(s): {', '.join(drifted)}")

    for rel in STATUS_NAME_FILES:
        text = texts.get(rel)
        if text is None:
            continue
        absent = [
            word
            for word in STATUS_WORDS
            if not re.search(rf"(?<![A-Z0-9_]){word}(?![A-Z0-9_])", text)
        ]
        if absent:
            failed = True
            details.append(f"{rel}: missing status word(s): {', '.join(absent)}")

    if failed:
        return _check("gate-naming", "FAIL", "gate names or statuses are inconsistent", details)
    return _check(
        "gate-naming",
        "PASS",
        f"{len(GATE_KEYS)} gate keys and {len(STATUS_WORDS)} status words consistent",
    )


def _canonical_gate(value):
    text = str(value).strip()
    match = GATE_SHORT.match(text)
    if match:
        return GATE_KEYS[int(match.group(1))]
    upper = text.upper()
    for key in GATE_KEYS:
        if upper == key.upper():
            return key
    return upper


def _status_of(value):
    if isinstance(value, str):
        return value.strip().upper() or None
    if isinstance(value, dict):
        for field in ("status", "expected", "result", "verdict"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip().upper()
    return None


def _is_gate_name(value):
    if not isinstance(value, str):
        return False
    return bool(GATE_SHORT.match(value)) or value.upper() in {k.upper() for k in GATE_KEYS}


def _gate_pairs_from_container(container):
    if isinstance(container, dict):
        for key, value in container.items():
            if _is_gate_name(key):
                status = _status_of(value)
                if status:
                    yield _canonical_gate(key), status
            elif isinstance(value, dict):
                gate = value.get("gate") or value.get("key") or value.get("id")
                status = _status_of(value)
                if gate and status and _is_gate_name(gate):
                    yield _canonical_gate(gate), status
    elif isinstance(container, list):
        for item in container:
            if not isinstance(item, dict):
                continue
            gate = item.get("gate") or item.get("key") or item.get("id") or item.get("name")
            status = _status_of(item)
            if gate and status and _is_gate_name(gate):
                yield _canonical_gate(gate), status


def _gate_pairs(data):
    if not isinstance(data, dict):
        return {}
    pairs = {}
    for key, value in data.items():
        if _is_gate_name(key):
            status = _status_of(value)
            if status:
                pairs[_canonical_gate(key)] = status
    for field in (
        "gates",
        "gate_results",
        "gate_status",
        "results",
        "expected",
        "expected_gates",
        "expected_results",
    ):
        if field in data:
            for gate, status in _gate_pairs_from_container(data[field]):
                pairs.setdefault(gate, status)
    return pairs


def _extract_json(text):
    stripped = text.strip()
    if not stripped:
        return None
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _case_files(root):
    case = root / CASE_REL
    expected = case / "expected.json"
    gate_check = root / "scripts/gate_check.py"
    evidence = case / "evidence"

    state = None
    for name in ("design-state.json", "design-state.example.json", "state.json"):
        candidate = case / name
        if candidate.is_file():
            state = candidate
            break
    if state is None:
        for pattern in ("design-state*.json", "*state*.json"):
            candidates = sorted(case.glob(pattern))
            if candidates:
                state = candidates[0]
                break

    waiver = None
    for name in ("waivers.json", "waiver.json"):
        candidate = case / name
        if candidate.is_file():
            waiver = candidate
            break
    if waiver is None:
        candidates = sorted(case.glob("*waiver*.json"))
        if candidates:
            waiver = candidates[0]
    return case, expected, gate_check, evidence, state, waiver


def _project_name(expected_data, case):
    if isinstance(expected_data, dict):
        for field in ("project", "project_name", "name"):
            value = expected_data.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = value.get("name") or value.get("id")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return case.name


def check_case_regression(root, timeout=180):
    case, expected_path, gate_check, evidence, state, waiver = _case_files(root)
    missing = []
    if not gate_check.is_file():
        missing.append("scripts/gate_check.py")
    if not expected_path.is_file():
        missing.append(f"{CASE_REL}/expected.json")
    if not case.is_dir():
        missing.append(CASE_REL)
    if missing:
        return _check(
            "case-regression",
            "NOT RUN",
            "gate_check.py or regression case not present yet",
            [f"missing: {item}" for item in missing],
        )

    expected_data = _extract_json(_read_text(expected_path))
    if expected_data is None:
        return _check(
            "case-regression",
            "FAIL",
            "expected.json is not valid JSON",
            [str(expected_path)],
        )
    expected = _gate_pairs(expected_data)
    if not expected:
        return _check(
            "case-regression",
            "FAIL",
            "expected.json contains no recognizable gate statuses",
            ["expected keys: G0..G6 or G0_requirements..G6_manufacturing"],
        )

    command = [
        sys.executable,
        str(gate_check),
        "--project",
        _project_name(expected_data, case),
        "--project-dir",
        str(case),
        "--evidence-dir",
        str(evidence if evidence.is_dir() else case),
        "--json",
    ]
    if state is not None:
        command.extend(["--design-state", str(state)])
    if waiver is not None:
        command.extend(["--waiver-file", str(waiver)])

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(root),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _check(
            "case-regression",
            "FAIL",
            f"could not run gate_check.py: {exc}",
            [" ".join(command)],
        )

    if proc.returncode == 2:
        return _check(
            "case-regression",
            "FAIL",
            "gate_check.py exited 2 (argument, IO or design-state schema error)",
            [" ".join(command), (proc.stderr or "").strip()[-800:]],
        )

    report = _extract_json(proc.stdout or "")
    if report is None:
        return _check(
            "case-regression",
            "FAIL",
            "gate_check.py --json produced no parseable JSON report",
            [
                " ".join(command),
                f"exit={proc.returncode}",
                (proc.stdout or "").strip()[:800],
                (proc.stderr or "").strip()[-800:],
            ],
        )

    actual = _gate_pairs(report)
    mismatches = []
    for gate in GATE_KEYS:
        if gate not in expected:
            continue
        want = expected[gate]
        got = actual.get(gate)
        if got != want:
            mismatches.append(f"{gate}: expected {want}, got {got or 'MISSING'}")
    if mismatches:
        return _check(
            "case-regression",
            "FAIL",
            f"{len(mismatches)} gate mismatch(es)",
            [
                " ".join(command),
                f"exit={proc.returncode}",
                f"report schema={report.get('schema', 'MISSING')}",
            ]
            + mismatches,
        )
    return _check(
        "case-regression",
        "PASS",
        f"{len(expected)} gate status(es) match expected.json",
        [
            " ".join(command),
            f"exit={proc.returncode}",
            f"report schema={report.get('schema', 'MISSING')}",
        ],
    )


def check_python_compile(root):
    scripts = sorted((root / "scripts").glob("*.py"))
    if not scripts:
        return _check("python-compile", "FAIL", "no scripts/*.py found")
    failures = []
    with tempfile.TemporaryDirectory(prefix="skill-selftest-") as temp_dir:
        for script in scripts:
            cfile = Path(temp_dir) / (script.stem + ".pyc")
            try:
                py_compile.compile(str(script), cfile=str(cfile), doraise=True)
            except py_compile.PyCompileError as exc:
                failures.append(f"{script.name}: {exc.msg or exc}")
            except (OSError, SyntaxError, ValueError) as exc:
                failures.append(f"{script.name}: {exc}")
    if failures:
        return _check(
            "python-compile",
            "FAIL",
            f"{len(failures)} of {len(scripts)} script(s) do not compile",
            failures,
        )
    return _check(
        "python-compile",
        "PASS",
        f"{len(scripts)} script(s) compile with py_compile",
    )


def _version(root):
    path = root / ".version"
    if not path.is_file():
        return "unknown"
    return _read_text(path).strip() or "unknown"


def run_checks(root, timeout=180):
    checks = [
        check_required_files(root),
        check_markdown_links(root),
        check_gate_naming(root),
        check_case_regression(root, timeout=timeout),
        check_python_compile(root),
    ]
    counts = {"PASS": 0, "FAIL": 0, "NOT RUN": 0}
    for check in checks:
        counts[check["status"]] += 1
    exit_code = 0 if counts["FAIL"] == 0 and counts["NOT RUN"] == 0 else 1
    return {
        "schema": RESULT_SCHEMA,
        "selftest_only": SELFTEST_ONLY,
        "skill_root": str(root),
        "skill_version": _version(root),
        "checks": checks,
        "summary": {
            "pass": counts["PASS"],
            "fail": counts["FAIL"],
            "not_run": counts["NOT RUN"],
            "exit_code": exit_code,
        },
    }


def _print_human(report, quiet=False):
    print(f"design-hardware skill self-test {report['skill_version']}")
    print(report["selftest_only"])
    print(f"root: {report['skill_root']}")
    print()
    for check in report["checks"]:
        print(f"[{check['status']}] {check['id']}: {check['summary']}")
        if not quiet:
            for detail in check["details"]:
                print(f"  - {detail}")
    summary = report["summary"]
    print()
    print(
        f"{summary['pass']} PASS, {summary['fail']} FAIL, "
        f"{summary['not_run']} NOT RUN -> exit {summary['exit_code']}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only self-test for the design-hardware skill package."
    )
    parser.add_argument(
        "--root",
        default=None,
        help="design-hardware directory (default: parent of this script directory)",
    )
    parser.add_argument("--json", action="store_true", help="emit one JSON report")
    parser.add_argument("--quiet", action="store_true", help="human summary without details")
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="seconds allowed for the gate_check.py regression run (default 180)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    if not root.is_dir():
        print(f"error: skill root is not a directory: {root}", file=sys.stderr)
        return 2
    if not (root / "SKILL.md").is_file():
        print(f"error: SKILL.md not found under skill root: {root}", file=sys.stderr)
        return 2

    try:
        report = run_checks(root, timeout=args.timeout)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report, quiet=args.quiet)
    return report["summary"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
