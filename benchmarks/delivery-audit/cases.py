"""Benchmark case definitions for the delivery audit.

Each case is a frozen synthetic fixture with explicit expectations.  ``make_fixtures.py``
materialises the cases under ``fixtures/<id>/`` and records the input digests in
``case.json``; ``run_benchmarks.py`` replays them with the real CLI.  The cases are
synthetic (``simulated: true``); a real permissively-licensed export may be added as
an explicitly labelled replay case by the source worker.
"""

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.delivery_audit import support  # noqa: E402  (fixture builders)

ZIP_DATE = (2026, 1, 1, 0, 0, 0)
AT = "2026-10-27T00:00:00+00:00"


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel, data in files.items():
            info = zipfile.ZipInfo(rel, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def _four_layer_missing_inner():
    files = support.four_layer_package()
    del files["gerber/copper_inner2.gbr"]
    return files


def _duplicate_inner_candidates():
    files = support.four_layer_package()
    files["gerber/copper_inner2_duplicate.gbr"] = support.gerber_layer(
        "Copper,L3,Inr").encode()
    return files


def _empty_gerber():
    files = support.two_layer_package()
    files["gerber/copper_top.gbr"] = b""
    return files


def _truncated_gerber():
    files = support.two_layer_package()
    files["gerber/copper_top.gbr"] = support.gerber_layer().replace(
        "M02*\n", "").encode()
    return files


def _arc_gerber():
    files = support.two_layer_package()
    files["gerber/copper_top.gbr"] = support.gerber_layer(
        extra=["G02*", "X100Y100I50J0D01*"]).encode()
    return files


def _macro_gerber():
    files = support.two_layer_package()
    files["gerber/copper_top.gbr"] = support.gerber_layer().replace(
        "%ADD11R,1.000000X1.000000*%",
        "%AMOC8*5,1,8,0,0,1.08239X0*%\n%ADD11OC8*%").encode()
    return files


def _drill_bad_units():
    files = support.two_layer_package()
    files["gerber/drill.drl"] = support.drill_text(units="").encode()
    return files


def _drill_undefined_tool():
    files = support.two_layer_package()
    files["gerber/drill.drl"] = support.drill_text(holes=[(5, 5, 9)]).encode()
    return files


def _drill_slot():
    files = support.two_layer_package()
    files["gerber/drill.drl"] = support.drill_text().replace(
        "M30", "X5.000Y5.000G85X6.000Y5.000\nM30").encode()
    return files


def _bom_quantity_mismatch():
    files = support.smt_package()
    rows = support.default_bom_rows()
    rows[1]["Quantity"] = "3"
    files["bom.csv"] = support.bom_text(rows).encode()
    return files


def _cpl_duplicate():
    files = support.smt_package()
    rows = support.default_cpl_rows()
    rows.append(dict(rows[0], **{"Mid X": "11.000"}))
    files["cpl.csv"] = support.cpl_text(rows).encode()
    return files


def _dnp_in_cpl():
    files = support.smt_package()
    rows = support.default_bom_rows()
    rows[0]["DNP"] = "1"
    files["bom.csv"] = support.bom_text(rows).encode()
    return files


def _cpl_header_units():
    files = support.smt_package()
    header = ["Designator", "Mid X(mm)", "Mid Y(mm)", "Layer", "Rotation"]
    rows = [{"Designator": row["Designator"], "Mid X(mm)": row["Mid X"],
             "Mid Y(mm)": row["Mid Y"], "Layer": row["Layer"],
             "Rotation": row["Rotation"]} for row in support.default_cpl_rows()]
    files["cpl.csv"] = support.cpl_text(rows, header=header).encode()
    return files


def _bottom_package():
    files = _cpl_header_units()
    rows = support.default_bom_rows()
    rows.append({"Comment": "1k", "Designator": "R2", "Footprint": "0402",
                 "Quantity": "1", "MPN": "RC0402FR-071KL",
                 "Manufacturer": "Yageo", "LCSC": "C11702", "DNP": "",
                 "Assembly": "smt"})
    files["bom.csv"] = support.bom_text(rows).encode()
    cpl_rows = support.default_cpl_rows()
    cpl_rows.append({"Designator": "R2", "Mid X": "25.000", "Mid Y": "15.000",
                     "Layer": "Bottom", "Rotation": "0"})
    files["cpl.csv"] = support.cpl_text(cpl_rows).encode()
    return files


REFERENCE_PLACEMENTS = [
    {"designator": "R1", "x": 10.0, "y": 10.0, "side": "top", "rotation": 0},
    {"designator": "C1", "x": 15.0, "y": 10.0, "side": "top", "rotation": 90},
    {"designator": "C2", "x": 20.0, "y": 10.0, "side": "top", "rotation": 270},
    {"designator": "D1", "x": 25.0, "y": 10.0, "side": "top", "rotation": 180},
    {"designator": "R2", "x": 5.0, "y": 15.0, "side": "bottom", "rotation": 0},
]


def reference_data():
    return {
        "schema": "delivery-coordinate-reference/v1",
        "source": "benchmark-independent-reference",
        "unit": "mm",
        "board_extent": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 20},
        "placements": REFERENCE_PLACEMENTS,
    }


def _mirror_bottom(data):
    data["coordinates"]["bottom_side"] = {
        "mirror": "x", "rotation_offset_deg": 0, "source": "user_declared"}


def _stale_copper_hash(data):
    for item in data["files"]:
        if item["path"] == "gerber/copper_top.gbr":
            item["sha256"] = "e" * 64


def _bad_content_digest(data):
    data["content_manifest"]["sha256"] = "b" * 64


def _no_coordinates(data):
    data.pop("coordinates", None)


def _native_project_role(data):
    for item in data["files"]:
        if item["path"].endswith(".epro2"):
            item["role"] = "native_project"


def _archive_package():
    return {
        "readme.txt": "archive fixture\n".encode(),
        "project.epro2": zip_bytes({"project2.json": b'{"schema":"fixture"}\n',
                                    "PCB.json": b'{"docType":"PCB"}\n'}),
    }


def _traversal_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.txt", b"x")
    return buffer.getvalue()


def _bomb_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("zeros.bin", b"\0" * (5 * 1024 * 1024))
    return buffer.getvalue()


def _duplicate_case_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BOM.csv", b"designator\nR1\n")
        archive.writestr("bom.csv", b"designator\nR2\n")
    return buffer.getvalue()


CASES = [
    {"id": "01-legal-2l-fabrication", "title": "Legal 2-layer fabrication package",
     "command": "audit", "profile": "pcb-fabrication", "files": support.two_layer_package,
     "declarations": "default",
     "expect": {"exit": 0, "status": "pass_with_scope", "no_fail": True,
                "no_unknown": True}},
    {"id": "02-legal-4l-fabrication", "title": "Legal 4-layer fabrication package",
     "command": "audit", "profile": "pcb-fabrication",
     "files": support.four_layer_package, "declarations": "default",
     "expect": {"exit": 0, "status": "pass_with_scope", "no_fail": True,
                "no_unknown": True}},
    {"id": "03-4l-missing-inner", "title": "4-layer package missing inner L3",
     "command": "audit", "profile": "pcb-fabrication",
     "files": _four_layer_missing_inner, "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"stackup.missing_copper_layer": "fail"}}},
    {"id": "04-duplicate-inner-candidates", "title": "Two conflicting inner-layer candidates",
     "command": "audit", "profile": "pcb-fabrication",
     "files": _duplicate_inner_candidates, "declarations": None,
     "expect": {"exit": 1, "status": "fail",
                "rules": {"layer.duplicate_role": "fail"}}},
    {"id": "05-empty-gerber", "title": "Empty copper Gerber",
     "command": "audit", "profile": "pcb-fabrication", "files": _empty_gerber,
     "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"package.empty_file": "fail"}}},
    {"id": "06-truncated-gerber", "title": "Truncated Gerber (no end marker)",
     "command": "audit", "profile": "pcb-fabrication", "files": _truncated_gerber,
     "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"gerber.end_missing": "fail"}}},
    {"id": "07-unsupported-arc", "title": "Unsupported arc geometry stays incomplete",
     "command": "audit", "profile": "pcb-fabrication", "files": _arc_gerber,
     "declarations": "default",
     "expect": {"exit": 3, "status": "incomplete", "no_fail": True,
                "rules": {"gerber.unsupported.arc": "unknown"}}},
    {"id": "08-unsupported-macro", "title": "Unsupported aperture macro stays incomplete",
     "command": "audit", "profile": "pcb-fabrication", "files": _macro_gerber,
     "declarations": "default",
     "expect": {"exit": 3, "status": "incomplete", "no_fail": True,
                "rules": {"gerber.unsupported.macro": "unknown"}}},
    {"id": "09-drill-units-missing", "title": "Drill file without units",
     "command": "audit", "profile": "pcb-fabrication", "files": _drill_bad_units,
     "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"drill.units_missing": "fail"}}},
    {"id": "10-drill-undefined-tool", "title": "Drill references an undefined tool",
     "command": "audit", "profile": "pcb-fabrication",
     "files": _drill_undefined_tool, "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"drill.tool_undefined": "fail"}}},
    {"id": "11-drill-slot-unsupported", "title": "Drill slot stays incomplete",
     "command": "audit", "profile": "pcb-fabrication", "files": _drill_slot,
     "declarations": "default",
     "expect": {"exit": 3, "status": "incomplete", "no_fail": True,
                "rules": {"drill.unsupported.slot": "unknown"}}},
    {"id": "12-bom-quantity-mismatch", "title": "BOM quantity/designator conflict",
     "command": "audit", "profile": "smt-assembly",
     "files": _bom_quantity_mismatch, "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"bom.quantity_mismatch": "fail"}}},
    {"id": "13-cpl-duplicate-designator", "title": "CPL duplicate designator",
     "command": "audit", "profile": "smt-assembly", "files": _cpl_duplicate,
     "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"cpl.designator_duplicate": "fail"}}},
    {"id": "14-dnp-in-cpl", "title": "DNP part illegally present in CPL",
     "command": "audit", "profile": "smt-assembly", "files": _dnp_in_cpl,
     "declarations": "default",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"assembly.dnp_in_cpl": "fail"}}},
    {"id": "15-tht-without-cpl-allowed", "title": "THT part without CPL is not an error",
     "command": "audit", "profile": "smt-assembly",
     "files": support.smt_package, "declarations": "default",
     "expect": {"exit": 0, "status": "pass_with_scope", "no_fail": True}},
    {"id": "16-no-coordinate-convention", "title": "Missing coordinate convention",
     "command": "audit", "profile": "smt-assembly", "files": _cpl_header_units,
     "declarations": _no_coordinates,
     "expect": {"exit": 3, "status": "incomplete", "no_fail": True,
                "rules": {"coordinates.convention_missing": "unknown"}}},
    {"id": "17-coordinate-reference-positive", "title": "Independent coordinate reference matches",
     "command": "audit", "profile": "smt-assembly", "files": _bottom_package,
     "declarations": _mirror_bottom, "reference": reference_data,
     "expect": {"exit": 0, "status": "pass_with_scope", "no_fail": True}},
    {"id": "18-coordinate-reference-bottom-negative",
     "title": "Bottom-side coordinate mismatch is detected",
     "command": "audit", "profile": "smt-assembly", "files": _bottom_package,
     "declarations": "default", "reference": reference_data,
     "expect": {"exit": 1, "status": "fail",
                "rules": {"coordinates.offset_mismatch": "fail"}}},
    {"id": "19-manifest-digest-conflict", "title": "Declared manifest digest conflicts",
     "command": "audit", "profile": "pcb-fabrication",
     "files": support.two_layer_package, "declarations": _bad_content_digest,
     "expect": {"exit": 1, "status": "fail",
                "rules": {"manifest.content_digest_mismatch": "fail"}}},
    {"id": "20-touch-old-file", "title": "Touching an old file does not improve provenance",
     "command": "audit", "profile": "pcb-fabrication",
     "files": support.two_layer_package, "declarations": _stale_copper_hash,
     "touch": "gerber/copper_top.gbr",
     "expect": {"exit": 1, "status": "fail",
                "rules": {"provenance.file_hash_mismatch": "fail"}}},
    {"id": "21-legal-zip-package", "title": "Legal package delivered as ZIP",
     "command": "audit", "profile": "pcb-fabrication",
     "files": support.two_layer_package, "input_kind": "zip",
     "declarations": "default",
     "expect": {"exit": 0, "status": "pass_with_scope", "no_fail": True}},
    {"id": "22-archive-profile", "title": "Archive profile with native container",
     "command": "audit", "profile": "archive", "files": _archive_package,
     "declarations": _native_project_role,
     "expect": {"exit": 0, "status": "pass_with_scope", "no_fail": True,
                "no_unknown": True}},
    {"id": "23-zip-traversal", "title": "ZIP path traversal rejected",
     "command": "inspect", "raw": {"bad.zip": _traversal_zip()},
     "expect": {"exit": 2, "status": "input_invalid",
                "error_code": "zip_unsafe_member"}},
    {"id": "24-zip-bomb", "title": "ZIP compression bomb rejected",
     "command": "inspect", "raw": {"bomb.zip": _bomb_zip()},
     "args": ["--max-ratio", "10"],
     "expect": {"exit": 2, "status": "input_invalid",
                "error_code": "input_limits_exceeded"}},
    {"id": "25-zip-case-duplicate", "title": "ZIP case-insensitive duplicate rejected",
     "command": "inspect", "raw": {"duplicate.zip": _duplicate_case_zip()},
     "expect": {"exit": 2, "status": "input_invalid",
                "error_code": "zip_duplicate_member"}},
    {"id": "26-output-inside-input", "title": "Report inside input is refused",
     "command": "output-inside", "profile": "pcb-fabrication",
     "files": support.two_layer_package, "declarations": "default",
     "expect": {"exit": 2, "status": "input_invalid",
                "error_code": "output_invalid", "output_absent": True}},
    {"id": "27-stale-output-replacement", "title": "Invalid run replaces stale PASS output",
     "command": "stale-output", "profile": "pcb-fabrication",
     "expect": {"exit": 2, "status": "input_invalid",
                "error_code": "input_not_found", "stale_replaced": True}},
]

REAL_SAMPLE_CASE = {
    "id": "28-real-sample-replay",
    "title": "Read-only replay of a real permissively licensed export",
    "command": "audit",
    "profile": "pcb-fabrication",
    "simulated": False,
    "declarations": None,
    "expect": {"exit_in": [0, 1, 3], "no_real_eda": True},
    "notes": "No declarations are supplied; the source EDA revision is not bound. "
             "This is a replay/regression case, not evidence of manufacturability.",
}
