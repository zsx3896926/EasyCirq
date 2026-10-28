"""Shared builders and real-CLI helpers for return-path-audit tests.

Tests in this package always exercise the real command line in a subprocess
(``python -m return_path_audit``), not just imported functions, so a CLI
regression cannot hide behind a unit test.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "easycirq" / "scripts"
BENCH = ROOT / "benchmarks" / "return-path-audit"
SNAPSHOT = "snap-test-1"
RAW_SHA = "a" * 64


def rect(x0, y0, x1, y1):
    """Closed rectangular ring."""
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def translate(points, dx, dy):
    return [[x + dx, y + dy] for x, y in points]


def rotate(points, degrees, origin=(0.0, 0.0)):
    import math
    angle = math.radians(degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    result = []
    for x, y in points:
        x2, y2 = x - origin[0], y - origin[1]
        result.append([x2 * cos_a - y2 * sin_a + origin[0],
                       x2 * sin_a + y2 * cos_a + origin[1]])
    return result


def scale(points, factor):
    return [[x * factor, y * factor] for x, y in points]


def default_stackup(units="mm"):
    """Standard four-layer stack: L1 signal / L2 GND / L3 PWR / L4 signal."""
    dielectrics = [0.2, 0.4, 0.2] if units == "mm" else [8.0, 16.0, 8.0]
    copper = 0.035 if units == "mm" else 1.4
    return {
        "complete": True,
        "layers": [
            {"order": 1, "copper_layer_id": "L1", "role": "signal",
             "thickness": {"value": copper, "unit": units},
             "dielectric_below": {"value": dielectrics[0], "unit": units}},
            {"order": 2, "copper_layer_id": "L2", "role": "plane", "net": "GND",
             "thickness": {"value": copper, "unit": units},
             "dielectric_below": {"value": dielectrics[1], "unit": units}},
            {"order": 3, "copper_layer_id": "L3", "role": "plane", "net": "P3V3",
             "thickness": {"value": copper, "unit": units},
             "dielectric_below": {"value": dielectrics[2], "unit": units}},
            {"order": 4, "copper_layer_id": "L4", "role": "signal",
             "thickness": {"value": copper, "unit": units}},
        ],
    }


def make_input(*, units="mm", stackup=None, board=None, copper=None, signals=None,
               vias=None, assignments=None, transitions=None, constraints=None,
               unsupported=None, external_reports=None, project=None, source=None,
               raw_sha=RAW_SHA, snapshot=SNAPSHOT):
    """Build a complete input document.

    Defaults: 100x80 board, L2 GND plane covering the board, one straight signal
    from (20,40) to (80,40) on L1 referenced to L2/GND.
    """
    width, height = _board_size(units)
    board = board or {"outline": rect(0, 0, width, height), "holes": [],
                      "complete": True, "geometry_tolerance": _tolerance(units)}
    copper = copper if copper is not None else [
        {"id": "rc-gnd-l2", "layer": "L2", "net": "GND", "availability": "actual_fill",
         "is_actual_fill": True, "connectivity_island": "gnd-l2",
         "source_snapshot": snapshot,
         "polygons": [{"id": "poly-gnd", "outer": rect(0, 0, width, height),
                       "holes": []}]},
    ]
    signals = signals if signals is not None else [
        {"id": "sig-dp", "net": "USB_DP",
         "segments": [{"id": "sig-dp.1", "kind": "straight", "layer": "L1",
                       "start": [20, 40], "end": [80, 40], "width": 0.2}]},
    ]
    if assignments is None:
        assignments = []
        if signals:
            plane_layer, plane_net = _default_reference(stackup or default_stackup(units))
            for signal in signals:
                if signal.get("segments"):
                    assignments.append({
                        "id": "ra-%s" % signal["id"],
                        "target": {"signal": signal["id"]},
                        "reference_layer": plane_layer,
                        "reference_net": plane_net,
                        "basis": "declared",
                        "source_snapshot": snapshot,
                    })
    document = {
        "schema": "return-path-audit-input/v1",
        "project": project or {"id": "test-project", "document": "pcb",
                               "snapshot": snapshot},
        "source": source or {"kind": "synthetic", "producer": "return-path-audit-tests",
                             "captured_at": "2026-10-27T14:00:00Z",
                             "raw_input_sha256": raw_sha},
        "units": units,
        "stackup": stackup or default_stackup(units),
        "board": board,
        "reference_copper": copper,
        "signals": signals,
        "vias": vias or [],
        "reference_assignment": assignments,
        "transitions": transitions or [],
        "constraints": constraints if constraints is not None else
                       {"interface": "test", "corridor": _corridor(units),
                        "max_return_via_distance": _via_distance(units)},
        "unsupported": unsupported or [],
        "external_reports": external_reports or [],
    }
    return document


def _board_size(units):
    return (100.0, 80.0) if units == "mm" else (3937.0, 3150.0)


def _default_reference(stackup):
    layers = sorted(stackup["layers"], key=lambda item: item["order"])
    for layer in layers:
        if layer.get("role") == "plane" and layer.get("net"):
            return layer["copper_layer_id"], layer["net"]
    return layers[0]["copper_layer_id"], "GND"


def _tolerance(units):
    return 0.01 if units == "mm" else 0.4


def _corridor(units):
    return 0.2 if units == "mm" else 8.0


def _via_distance(units):
    return 2.0 if units == "mm" else 79.0


def write_input(tmpdir, document, name="input.json"):
    path = pathlib.Path(tmpdir) / name
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def run_cli(args, cwd=None, timeout=120):
    """Run the real CLI; returns (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, "-m", "return_path_audit", *args],
        cwd=str(cwd or SCRIPTS), capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout, proc.stderr


def audit_document(document, tmpdir, extra_args=None):
    """Write the scene, run a real audit, return (exit, report_or_none, stderr)."""
    input_path = write_input(tmpdir, document)
    report_path = pathlib.Path(tmpdir) / "report.json"
    args = ["audit", "-i", str(input_path), "-o", str(report_path)]
    if extra_args:
        args.extend(extra_args)
    code, stdout, stderr = run_cli(args)
    report = None
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    return code, report, stderr


def rule_ids(report):
    return [item["rule_id"] for item in report.get("findings", [])]


def unknown_ids(report):
    return [item["rule_id"] for item in report.get("unknowns", [])]


def import_tool_package():
    """Import the audit tool under an alias.

    ``tests/return_path_audit`` is itself a package named ``return_path_audit``
    during ``unittest discover``, so importing the tool by its real name would
    collide.  Loading it as ``rpa_tool`` with a proper package ``__path__`` keeps
    the tool's relative imports working.
    """
    import importlib
    import importlib.util
    if "rpa_tool" in sys.modules:
        return sys.modules["rpa_tool"]
    package_dir = SCRIPTS / "return_path_audit"
    spec = importlib.util.spec_from_file_location(
        "rpa_tool", package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["rpa_tool"] = module
    spec.loader.exec_module(module)
    return module


def tool_submodule(name):
    import importlib
    import_tool_package()
    return importlib.import_module("rpa_tool.%s" % name)
