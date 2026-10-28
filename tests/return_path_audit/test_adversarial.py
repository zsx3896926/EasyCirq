"""Boundary / adversarial CLI tests for the return-path auditor.

Everything here drives the real command line in a subprocess and checks the
published contract (docs/parallel-return-path-audit/contract.md):

  * strict validation rejects, never repairs: exit 4, ``valid:false`` /
    ``overall_status=input_invalid`` (contract section 3 and the status table);
  * ``--out``/``--svg`` may never overwrite the input snapshot (section 5);
  * reports are written atomically and an invalid re-run may not leave an old
    PASS behind (sections 4/5);
  * stdout carries machine JSON only, diagnostics go to stderr (section 5);
  * ``geometry_tolerance`` is the tolerance source for degeneracy and
    near-boundary classification, it is *not* a switch that may widen away a
    real uncovered slit (section 2.3);
  * exit codes follow overall_status: 0/1/2/3/4 (status table).

Interpretation note: "validate an invalid path exits 4" is read as "the path of
an invalid input document" (a validation failure).  A *missing/unreadable*
file is a usage error in ``cli.py`` (exit 5), so it is not asserted here.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import tempfile
import unittest

try:  # package import when discovered with ``-s tests``
    from . import support
except ImportError:  # plain import when discovered with ``-s tests/return_path_audit``
    import support

STATUS_EXIT = {
    "pass_with_scope": 0,
    "fail": 1,
    "review_required": 2,
    "incomplete": 3,
    "input_invalid": 4,
}

VALIDATION_SCHEMA = "return-path-audit-validation/v1"


# ------------------------------------------------------------------- scenes
def split_fail_scene():
    """GND plane ends at x=40, trace runs to x=80 => proven copper-edge error.

    Projection half-width = 0.2/2 + 0.2 = 0.3 mm.  From x=40 the declared GND
    reference copper is gone (no other net on L2 at all), so the return plane
    ends under the trace: RP-E2-204 (error, proven) => ``fail`` / exit 1.
    """
    copper = [{
        "id": "rc-gnd-l2", "layer": "L2", "net": "GND",
        "availability": "actual_fill", "is_actual_fill": True,
        "connectivity_island": "gnd-l2",
        "source_snapshot": support.SNAPSHOT,
        "polygons": [{"id": "poly-gnd", "outer": support.rect(0, 0, 40, 80),
                      "holes": []}],
    }]
    return support.make_input(copper=copper)


def review_warning_scene():
    """Plane edge 0.2 mm above the trace: less than the 0.3 mm half-width.

    The trace stays *on* copper (no void/edge crossing), but the copper edge at
    y=40.2 leaves only 0.2 mm margin (< width/2 + corridor = 0.3 mm), so
    RP-E2-206 (warning, proven) => ``review_required`` / exit 2.
    """
    copper = [{
        "id": "rc-gnd-l2", "layer": "L2", "net": "GND",
        "availability": "actual_fill", "is_actual_fill": True,
        "connectivity_island": "gnd-l2",
        "source_snapshot": support.SNAPSHOT,
        "polygons": [{"id": "poly-gnd", "outer": support.rect(0, 0, 100, 40.2),
                      "holes": []}],
    }]
    return support.make_input(copper=copper)


def incomplete_scene():
    """Pour-boundary copper is not actual fill: coverage must stay unknown.

    Contract 2.4: only actual fill can be counted as checked; a pour boundary
    can only produce ``unknown`` -> ``incomplete`` / exit 3.
    """
    copper = [{
        "id": "rc-gnd-l2", "layer": "L2", "net": "GND",
        "availability": "pour_boundary", "is_actual_fill": False,
        "connectivity_island": "gnd-pour",
        "source_snapshot": support.SNAPSHOT,
        "polygons": [{"id": "poly-gnd", "outer": support.rect(0, 0, 100, 80),
                      "holes": []}],
    }]
    return support.make_input(copper=copper)


def slit_scene(width):
    """GND plane with a vertical slit of ``width`` mm across the trace.

    Trace: L1 y=40, x=20..80, width 0.2.  The polygon hole is
    x in [50-width/2, 50+width/2], y in [30, 50], i.e. it fully crosses the
    trace.  Any positive uncovered width is a real void in the same reference
    polygon (RP-E2-202, error, proven).  ``geometry_tolerance`` only classifies
    near-boundary intervals; shrinking the slit to/under the tolerance is not
    allowed to erase it (contract 2.3).
    """
    half = width / 2.0
    copper = [{
        "id": "rc-gnd-l2", "layer": "L2", "net": "GND",
        "availability": "actual_fill", "is_actual_fill": True,
        "connectivity_island": "gnd-l2",
        "source_snapshot": support.SNAPSHOT,
        "polygons": [{"id": "poly-gnd", "outer": support.rect(0, 0, 100, 80),
                      "holes": [support.rect(50 - half, 30, 50 + half, 50)]}],
    }]
    return support.make_input(copper=copper)


# ------------------------------------------------------------------ helpers
def _write(tmpdir, document, name="input.json"):
    return support.write_input(tmpdir, document, name)


def _run_validate(path):
    code, stdout, stderr = support.run_cli(["validate", "-i", str(path)])
    return code, stdout, stderr


def _parse_json(stdout, what):
    try:
        return json.loads(stdout)
    except ValueError as error:
        raise AssertionError("%s stdout is not one JSON document: %s\n%r"
                             % (what, error, stdout[:500]))


def invalid_cases():
    """Every (name, mutation, expected issue code) from contract section 3."""
    base = support.make_input()

    def duplicate_id(document):
        document["reference_copper"][0]["id"] = document["signals"][0]["id"]

    def bool_width(document):
        document["signals"][0]["segments"][0]["width"] = True

    def nan_coordinate(document):
        document["board"]["outline"][0][0] = float("nan")

    def negative_width(document):
        document["signals"][0]["segments"][0]["width"] = -0.2

    def unclosed_ring(document):
        document["board"]["outline"] = document["board"]["outline"][:-1]

    def self_intersecting_ring(document):
        document["board"]["outline"] = [[0, 0], [100, 80], [100, 0], [0, 80],
                                        [0, 0]]

    def missing_via_span(document):
        document["vias"] = [{"id": "via-x", "net": "GND",
                             "center": [10, 10], "diameter": 0.45,
                             "via_type": "through"}]

    def bool_threshold(document):
        document["constraints"]["corridor"] = True

    def non_contiguous_order(document):
        document["stackup"]["layers"][2]["order"] = 5

    def via_type_span_mismatch(document):
        # A through via is top-to-bottom; L2..L3 is buried.  Reject, no repair.
        document["vias"] = [{"id": "via-x", "net": "GND",
                             "center": [10, 10], "diameter": 0.45,
                             "span": {"from": "L2", "to": "L3"},
                             "via_type": "through"}]

    mutations = [
        ("duplicate_id", duplicate_id, "DUPLICATE_ID"),
        ("bool_width", bool_width, "INVALID_WIDTH"),
        ("nan_coordinate", nan_coordinate, "INVALID_NUMBER"),
        ("negative_width", negative_width, "INVALID_WIDTH"),
        ("unclosed_ring", unclosed_ring, "RING_NOT_CLOSED"),
        ("self_intersecting_ring", self_intersecting_ring,
         "SELF_INTERSECTING"),
        ("missing_via_span", missing_via_span, "MISSING_VIA_SPAN"),
        ("bool_threshold", bool_threshold, "INVALID_THRESHOLD"),
        ("non_contiguous_layer_order", non_contiguous_order,
         "NON_CONTIGUOUS_STACKUP"),
        ("via_type_span_mismatch", via_type_span_mismatch,
         "VIA_TYPE_SPAN_MISMATCH"),
    ]
    cases = []
    for name, mutate, issue_code in mutations:
        document = copy.deepcopy(base)
        mutate(document)
        cases.append((name, document, issue_code))
    return cases


# -------------------------------------------------------------------- tests
class StrictValidationTests(unittest.TestCase):
    """``validate`` must reject malformed input with exit 4, never repair it."""

    def test_invalid_input_matrix_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, document, issue_code in invalid_cases():
                with self.subTest(case=name):
                    path = _write(tmp, document, name + ".json")
                    code, stdout, stderr = _run_validate(path)
                    self.assertEqual(code, STATUS_EXIT["input_invalid"],
                                     "malformed input %r was not rejected" % name)
                    payload = _parse_json(stdout, "validate")
                    self.assertEqual(payload["schema"], VALIDATION_SCHEMA)
                    self.assertIs(payload["valid"], False)
                    self.assertTrue(payload["issues"],
                                    "valid:false without any issue entry")
                    codes = [issue["code"] for issue in payload["issues"]]
                    self.assertIn(issue_code, codes,
                                  "expected issue %r for %r, got %r"
                                  % (issue_code, name, codes))
                    self.assertIn("input_invalid", stderr,
                                  "diagnostic must go to stderr")

    def test_audit_of_invalid_input_is_input_invalid_not_a_verdict(self):
        """An invalid audit run must not produce findings/coverage conclusions."""
        bad = copy.deepcopy(support.make_input())
        bad["reference_copper"][0]["id"] = bad["signals"][0]["id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, bad)
            code, stdout, stderr = support.run_cli(["audit", "-i", str(path)])
            self.assertEqual(code, STATUS_EXIT["input_invalid"])
            report = _parse_json(stdout, "audit")
            self.assertEqual(report["overall_status"], "input_invalid")
            self.assertEqual(report["findings"], [],
                             "no audit verdict may be produced for invalid input")
            self.assertEqual(report["unknowns"], [])
            self.assertTrue(report["validation_issues"])
            self.assertTrue(stderr.strip(),
                            "invalid audit should explain itself on stderr")


class OutputGuardTests(unittest.TestCase):
    """The audit only reads the snapshot; --out/--svg may not overwrite it."""

    def test_out_same_as_input_exits_5_and_keeps_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, support.make_input())
            before = path.read_bytes()
            for flag in ("-o", "--svg"):
                with self.subTest(flag=flag):
                    code, stdout, stderr = support.run_cli(
                        ["audit", "-i", str(path), flag, str(path)])
                    self.assertEqual(code, 5,
                                     "%s over the input must be a usage error" % flag)
                    self.assertEqual(path.read_bytes(), before,
                                     "input snapshot bytes were modified")
                    self.assertIn("refusing", stderr.lower())


class NoStaleVerdictTests(unittest.TestCase):
    """A previous FAIL report may not survive as a PASS (or any verdict)."""

    def test_failing_scene_then_invalid_rerun_leaves_input_invalid(self):
        scene = split_fail_scene()
        with tempfile.TemporaryDirectory() as tmp:
            input_path = _write(tmp, scene, "scene.json")
            report_path = pathlib.Path(tmp) / "report.json"
            args = ["audit", "-i", str(input_path), "-o", str(report_path)]

            code, stdout, _ = support.run_cli(args)
            self.assertEqual(code, STATUS_EXIT["fail"])
            first = _parse_json(stdout, "audit")
            self.assertEqual(first["overall_status"], "fail",
                             "copper-edge crossing must be a proven failure")
            self.assertTrue(report_path.is_file())

            # Replace the scene with an invalid document at the same path.
            broken = copy.deepcopy(scene)
            broken["reference_copper"][0]["id"] = broken["signals"][0]["id"]
            input_path.write_text(json.dumps(broken), encoding="utf-8")

            code, stdout, _ = support.run_cli(args)
            self.assertEqual(code, STATUS_EXIT["input_invalid"])
            second = _parse_json(stdout, "audit")
            self.assertEqual(second["overall_status"], "input_invalid")
            on_disk = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["overall_status"], "input_invalid",
                             "stale report was not replaced by the invalid run")
            self.assertNotEqual(on_disk["overall_status"], "pass_with_scope")
            self.assertEqual(on_disk["findings"], [])


class AtomicWriteTests(unittest.TestCase):
    """Report/SVG writes are atomic and leave no temporary files behind."""

    def test_report_is_json_and_no_tmp_leftovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = _write(tmp, support.make_input())
            outdir = pathlib.Path(tmp) / "nested" / "reports"
            report_path = outdir / "report.json"
            svg_path = outdir / "overlay.svg"
            code, stdout, stderr = support.run_cli(
                ["audit", "-i", str(input_path), "-o", str(report_path),
                 "--svg", str(svg_path)])
            self.assertEqual(code, STATUS_EXIT["pass_with_scope"],
                             "clean default scene must pass; stderr=%r" % stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["overall_status"], "pass_with_scope")
            self.assertIn("synthetic_analysis / not_official_export",
                          svg_path.read_text(encoding="utf-8"),
                          "overlay must carry the synthetic-analysis watermark")
            names = sorted(os.listdir(outdir))
            self.assertEqual(names, ["overlay.svg", "report.json"],
                             "unexpected/leftover files in the output directory")
            leftovers = [name for name in names
                         if name.endswith(".tmp") or name.startswith(".return-path-audit-")]
            self.assertEqual(leftovers, [],
                             "atomic writer left temporary files: %r" % leftovers)


class JsonStdoutPurityTests(unittest.TestCase):
    """stdout is exactly one JSON document; diagnostics never pollute it."""

    def test_audit_stdout_is_json_while_stderr_has_messages(self):
        bad = copy.deepcopy(support.make_input())
        bad["board"]["outline"] = bad["board"]["outline"][:-1]  # unclosed ring
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, bad)
            code, stdout, stderr = support.run_cli(["audit", "-i", str(path)])
            self.assertEqual(code, STATUS_EXIT["input_invalid"])
            self.assertTrue(stderr.strip(), "stderr should carry the diagnostic")
            payload = json.loads(stdout)  # raises if stdout is not pure JSON
            self.assertEqual(payload["overall_status"], "input_invalid")

    def test_validate_stdout_is_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = _write(tmp, support.make_input(), "good.json")
            code, stdout, stderr = support.run_cli(
                ["validate", "-i", str(good)])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertIs(payload["valid"], True)
            self.assertEqual(payload["issues"], [])
            self.assertEqual(payload["schema"], VALIDATION_SCHEMA)


class ToleranceBoundaryTests(unittest.TestCase):
    """A slit at/under/over geometry_tolerance must never be erased."""

    def test_slit_width_around_geometry_tolerance_is_always_reported(self):
        tolerance = 0.01  # support.make_input default board geometry_tolerance
        for width in (0.004, tolerance, 0.02):  # <, ==, > tolerance
            with self.subTest(slit_width=width):
                scene = slit_scene(width)
                self.assertEqual(
                    scene["board"]["geometry_tolerance"], tolerance)
                with tempfile.TemporaryDirectory() as tmp:
                    input_path = _write(tmp, scene)
                    report_path = pathlib.Path(tmp) / "report.json"
                    code, stdout, stderr = support.run_cli(
                        ["audit", "-i", str(input_path),
                         "-o", str(report_path)])
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertEqual(code, STATUS_EXIT["fail"],
                                 "an uncovered slit must fail, not be smoothed")
                self.assertEqual(report["overall_status"], "fail")
                slits = [item for item in report["findings"]
                         if item["rule_id"] == "RP-E2-202"]
                self.assertEqual(len(slits), 1,
                                 "the void must be reported exactly once")
                self.assertEqual(slits[0]["severity"], "error")
                self.assertEqual(slits[0]["determinism"], "proven")
                self.assertAlmostEqual(
                    slits[0]["measured"]["void_length"], width, places=6,
                    msg="reported void width must be the geometric slit width")


class StatusExitCodeTests(unittest.TestCase):
    """Exit codes are the status table from contract section 4."""

    def test_status_to_exit_code_mapping(self):
        scenes = [
            ("pass_with_scope", support.make_input()),
            ("fail", split_fail_scene()),
            ("review_required", review_warning_scene()),
            ("incomplete", incomplete_scene()),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for expected_status, scene in scenes:
                with self.subTest(status=expected_status):
                    input_path = _write(tmp, scene, expected_status + ".json")
                    report_path = pathlib.Path(tmp) / (expected_status + ".report.json")
                    code, stdout, stderr = support.run_cli(
                        ["audit", "-i", str(input_path),
                         "-o", str(report_path)])
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    self.assertEqual(report["overall_status"], expected_status,
                                     "scene did not produce its derived status")
                    self.assertEqual(code, STATUS_EXIT[expected_status],
                                     "exit code does not match the status table")


if __name__ == "__main__":
    unittest.main()
