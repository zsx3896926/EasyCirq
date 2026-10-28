"""Subprocess-only helpers for the placement-intent CLI test suite.

Design rules (mirrored from the task book):

* every CLI interaction is a real ``python -m placement_intent`` subprocess;
* the implementation package is never imported into the test process;
* no ``sys.path`` insertion at import time (subprocesses get ``PYTHONPATH``);
* every assertion message carries the command, exit code and stdout/stderr
  tails so a failure can be reproduced without re-running by hand.

Only the standard library is used.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "easycirq" / "scripts"
IMPLEMENTATION = SCRIPTS / "placement_intent"
TOOL_VERSION = "0.1.0"

STDOUT_TAIL = 4000
STDERR_TAIL = 2000


class CliResult:
    """Result of one CLI invocation with failure-friendly rendering."""

    __slots__ = ("args", "cwd", "returncode", "stdout", "stderr")

    def __init__(self, args, cwd, returncode, stdout, stderr):
        self.args = list(args)
        self.cwd = str(cwd)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @staticmethod
    def _tail(text, limit):
        if not text:
            return "<empty>"
        if len(text) <= limit:
            return text
        return "..." + text[-limit:]

    def context(self):
        return (
            "command: python -m placement_intent {args}\n"
            "cwd: {cwd}\n"
            "exit code: {code}\n"
            "stdout (tail):\n{stdout}\n"
            "stderr (tail):\n{stderr}".format(
                args=" ".join(self.args),
                cwd=self.cwd,
                code=self.returncode,
                stdout=self._tail(self.stdout, STDOUT_TAIL),
                stderr=self._tail(self.stderr, STDERR_TAIL),
            )
        )

    def payload(self):
        problem = single_json_problem(self.stdout)
        if problem is not None:
            raise AssertionError(problem + "\n" + self.context())
        return json.loads(self.stdout)


def single_json_problem(stream):
    """Return None when ``stream`` is exactly one JSON object, else a message."""
    text = (stream or "").strip()
    if not text:
        return "stdout is empty; expected exactly one JSON object"
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(text)
    except json.JSONDecodeError as error:
        return "stdout is not valid JSON: %s" % error
    if text[end:].strip():
        return "stdout has trailing content after the first JSON value: %r" % text[end:][:200]
    if not isinstance(value, dict):
        return "stdout JSON must be an object, got %s" % type(value).__name__
    return None


def cli_environment():
    """Environment for the CLI subprocess (implementation importable, no .pyc)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONSTARTUP", None)
    return env


def run_cli(args, cwd=None, timeout=300):
    """Run ``python -m placement_intent <args>`` in a child process."""
    args = [str(arg) for arg in args]
    command = [sys.executable, "-m", "placement_intent", *args]
    workdir = Path(cwd) if cwd is not None else Path(tempfile.gettempdir())
    completed = subprocess.run(
        command,
        cwd=str(workdir),
        env=cli_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return CliResult(args, workdir, completed.returncode,
                     completed.stdout, completed.stderr)


def write_json(path, value):
    """Write a JSON fixture with explicit UTF-8/LF newline control."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2,
                      allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def write_raw(path, text, *, newline=False):
    """Write exact raw bytes (for duplicate keys / NaN / BOM fixtures)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text + ("\n" if newline else "")
    path.write_bytes(data.encode("utf-8"))
    return path


def write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def directory_state(path):
    """Sorted relative names of everything currently inside ``path``."""
    base = Path(path)
    return sorted(str(item.relative_to(base)) for item in base.rglob("*"))


def node_map(payload):
    """Map node id -> node object from a plan payload."""
    nodes = {}
    for level in payload.get("levels") or []:
        for node in level.get("nodes") or []:
            nodes[node.get("id")] = node
    return nodes


def node(payload, node_id):
    nodes = node_map(payload)
    if node_id not in nodes:
        raise AssertionError(
            "node %r not found in plan; ids=%r" % (node_id, sorted(nodes)))
    return nodes[node_id]


def bbox(payload, node_id):
    return node(payload, node_id).get("bbox_mm")


def frame(payload, node_id):
    return node(payload, node_id).get("frame")


def finding_codes(payload):
    return [item.get("code") for item in payload.get("findings") or []
            if isinstance(item, dict)]


def unknown_codes(payload):
    return [item.get("code") for item in payload.get("unknowns") or []
            if isinstance(item, dict)]


def unknown_subjects(payload, code):
    return sorted(item.get("subject") for item in payload.get("unknowns") or []
                  if isinstance(item, dict) and item.get("code") == code)


def constraint_ids(payload):
    return [item.get("id") for item in payload.get("normalized_constraints") or []
            if isinstance(item, dict)]


def substantive_plan(payload, rename=None):
    """Order-independent, id-normalised projection of a plan payload.

    Used by the deformation tests: array ordering and id renaming must not
    change the substance of the plan.
    """
    rename = rename or {}

    def mapped(value):
        return rename.get(value, value) if isinstance(value, str) else value

    nodes = {}
    for level in payload.get("levels") or []:
        for item in level.get("nodes") or []:
            nodes[mapped(item.get("id"))] = {
                "kind": item.get("kind"),
                "parent": mapped(item.get("parent")),
                "frame": item.get("frame"),
                "bbox_mm": item.get("bbox_mm"),
                "size_mm": item.get("size_mm"),
                "allowed_rotations": item.get("allowed_rotations"),
                "children": sorted(mapped(child) for child in item.get("children") or []),
                "components": sorted(mapped(comp) for comp in item.get("components") or []),
                "fixed": item.get("fixed"),
                "confidence": item.get("confidence"),
            }
    constraints = []
    for item in payload.get("normalized_constraints") or []:
        constraints.append({
            "id": mapped(item.get("id")),
            "from": mapped(item.get("from")),
            "to": mapped(item.get("to")),
            "dx_mm": item.get("dx_mm"),
            "dy_mm": item.get("dy_mm"),
            "rotation_deg": item.get("rotation_deg"),
            "weight": item.get("weight"),
        })
    constraints.sort(key=lambda item: (item["from"], item["to"], item["id"]))
    findings = sorted(
        (item.get("code"), item.get("severity"), mapped(item.get("subject")))
        for item in payload.get("findings") or [])
    unknowns = sorted(
        (item.get("code"), mapped(item.get("subject")), item.get("impact"),
         item.get("origin"))
        for item in payload.get("unknowns") or [])
    return {
        "status": payload.get("status"),
        "exit_code": payload.get("exit_code"),
        "nodes": nodes,
        "constraints": constraints,
        "findings": findings,
        "unknowns": unknowns,
    }


class CliTestCase(unittest.TestCase):
    """Base class: isolated temp directory + context-rich CLI assertions."""

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory(prefix="pi-test-")
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    # -- fixture helpers -------------------------------------------------
    def write_input(self, name, document):
        return write_json(self.tmpdir / name, document)

    def write_raw_input(self, name, text, *, newline=False):
        return write_raw(self.tmpdir / name, text, newline=newline)

    def write_bytes_input(self, name, data):
        return write_bytes(self.tmpdir / name, data)

    # -- invocation ------------------------------------------------------
    def cli(self, *args):
        return run_cli(list(args), cwd=self.tmpdir)

    def run_on(self, command, path, *extra):
        return self.cli(command, "--input", str(path), *extra)

    # -- assertion helpers ----------------------------------------------
    def payload(self, result):
        return result.payload()

    def assert_exit(self, result, expected):
        self.assertEqual(
            result.returncode, expected,
            msg="expected exit code %r\n%s" % (expected, result.context()))

    def assert_status(self, result, expected):
        payload = self.payload(result)
        self.assertEqual(
            payload.get("status"), expected,
            msg="expected status %r\n%s" % (expected, result.context()))
        return payload

    def assert_exit_status(self, result, expected_exit, expected_status):
        self.assert_exit(result, expected_exit)
        return self.assert_status(result, expected_status)

    def assert_single_json(self, result):
        problem = single_json_problem(result.stdout)
        self.assertIsNone(
            problem,
            msg=(problem or "") + "\n" + result.context())
        return self.payload(result)

    def assert_has_finding(self, result, code, *, severity=None):
        payload = self.payload(result)
        matches = [item for item in payload.get("findings") or []
                   if isinstance(item, dict) and item.get("code") == code]
        self.assertTrue(
            matches,
            msg="expected finding %r (severity %r); codes=%r\n%s" % (
                code, severity, finding_codes(payload), result.context()))
        if severity is not None:
            self.assertTrue(
                any(item.get("severity") == severity for item in matches),
                msg="expected finding %r with severity %r; got %r\n%s" % (
                    code, severity,
                    [(item.get("code"), item.get("severity"))
                     for item in matches], result.context()))
        return payload

    def assert_has_unknown(self, result, code, *, subject=None):
        payload = self.payload(result)
        matches = [item for item in payload.get("unknowns") or []
                   if isinstance(item, dict) and item.get("code") == code]
        if subject is not None:
            matches = [item for item in matches
                       if item.get("subject") == subject]
        self.assertTrue(
            matches,
            msg="expected unknown %r (subject %r); got %r\n%s" % (
                code, subject,
                [(item.get("code"), item.get("subject"))
                 for item in payload.get("unknowns") or []
                 if isinstance(item, dict)], result.context()))
        return payload

    def assert_close(self, result, actual, expected, tolerance=1e-9,
                     label="value"):
        context = result.context() if hasattr(result, "context") else ""
        self.assertIsInstance(
            actual, (int, float),
            msg="%s is %r, expected number %r\n%s" % (
                label, actual, expected, context))
        self.assertAlmostEqual(
            actual, expected, delta=tolerance,
            msg="%s is %r, expected %r (+-%r)\n%s" % (
                label, actual, expected, tolerance, context))

    def assert_bbox(self, result, payload, node_id, x, y, w, h,
                    tolerance=1e-9):
        box = bbox(payload, node_id)
        self.assertIsNotNone(
            box, msg="node %r has null bbox_mm\n%s" % (
                node_id, result.context()))
        self.assert_close(result, box.get("x"), x, tolerance,
                          "%s bbox.x" % node_id)
        self.assert_close(result, box.get("y"), y, tolerance,
                          "%s bbox.y" % node_id)
        self.assert_close(result, box.get("w"), w, tolerance,
                          "%s bbox.w" % node_id)
        self.assert_close(result, box.get("h"), h, tolerance,
                          "%s bbox.h" % node_id)
        return box

    def assert_invalid(self, result, *expected_codes):
        """Assert a ``validate`` payload for an invalid input (exit 2).

        Contract.md section 6: the validation report's own ``status`` is only
        ``valid`` / ``invalid`` (``invalid_input`` is the plan-status spelling);
        error findings carry ``status="invalid_input"``.
        """
        self.assert_exit(result, 2)
        payload = self.assert_single_json(result)
        self.assertEqual(payload.get("status"), "invalid",
                         msg="expected validate status 'invalid'\n"
                             + result.context())
        self.assertIs(payload.get("valid"), False,
                      msg="valid must be false\n" + result.context())
        self.assertEqual(payload.get("exit_code"), 2,
                         msg="embedded exit_code must be 2\n" + result.context())
        self.assertEqual(payload.get("schema"),
                         "easycirq.placement-intent.validation/v1",
                         msg=result.context())
        codes = finding_codes(payload)
        for expected in expected_codes:
            self.assertIn(
                expected, codes,
                msg="expected finding %r; codes=%r\n%s" % (
                    expected, codes, result.context()))
        errors = [item for item in payload.get("findings") or []
                  if item.get("severity") == "error"]
        self.assertTrue(errors,
                        msg="invalid_input requires at least one error finding\n"
                            + result.context())
        for item in errors:
            self.assertEqual(item.get("status"), "invalid_input",
                             msg="error findings must carry status "
                                 "invalid_input: %r\n%s" % (item,
                                                            result.context()))
        return payload

    def check_invalid(self, document, *expected_codes, name="invalid.json"):
        """Write ``document``, run ``validate`` and assert it is rejected."""
        path = self.write_input(name, document)
        result = self.run_on("validate", path)
        payload = self.assert_invalid(result, *expected_codes)
        return result, payload

    def assert_null_bbox(self, result, payload, node_id):
        box = bbox(payload, node_id)
        self.assertIsNone(
            box, msg="node %r must have null bbox_mm, got %r\n%s" % (
                node_id, box, result.context()))
