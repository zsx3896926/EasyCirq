"""Shared fixtures and CLI helpers for delivery-audit tests.

Fixtures are synthetic unless a test says otherwise.  They are deliberately
small and deterministic so a failing case can be inspected by hand.  The
builders are also used by the frozen CLI benchmark.

Nothing here executes an input file or calls EDA/network.
"""

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "easycirq" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))


def _ensure_subject_package():
    """Import the real ``delivery_audit`` CLI package for tests.

    ``python -m unittest discover -s tests`` imports this directory as the
    top-level package``delivery_audit``, which would shadow the package under
    test.  Support is imported before any test imports ``delivery_audit``, so we
    bind the real package (from ``easycirq/scripts``) and append this test
    directory to its ``__path__`` so discovery can still find test modules.
    """
    tests_dir = Path(__file__).resolve().parent
    scripts_pkg = SCRIPTS / "delivery_audit"
    current = sys.modules.get("delivery_audit")
    current_file = Path(getattr(current, "__file__", "") or "").resolve() \
        if current is not None else None
    if current is not None and current_file.parent == scripts_pkg:
        subject = current
    else:
        # Load the implementation package explicitly from its own directory.
        # Importing by name after the pop would pick whichever ``delivery_audit``
        # is first on ``sys.path``; with several parallel tools' test packages in
        # the same discovery run the tests directory can precede README scripts
        # and the test package would be re-imported as the subject.
        import importlib.util  # noqa: PLC0415

        sys.modules.pop("delivery_audit", None)
        spec = importlib.util.spec_from_file_location(
            "delivery_audit", scripts_pkg / "__init__.py",
            submodule_search_locations=[str(scripts_pkg)])
        if spec is None or spec.loader is None:  # pragma: no cover
            raise ImportError("cannot load delivery_audit implementation")
        subject = importlib.util.module_from_spec(spec)
        sys.modules["delivery_audit"] = subject
        spec.loader.exec_module(subject)
    paths = list(getattr(subject, "__path__", []))
    if str(tests_dir) not in paths:
        subject.__path__ = paths + [str(tests_dir)]
    return subject


subject = _ensure_subject_package()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def write_bytes(root, rel, data):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def _gerber_coord(value_mm, decimals=6):
    return str(int(round(value_mm * (10 ** decimals))))


def gerber_layer(function="Copper,L1,Top", units="MM", fmt="FSLAX46Y46",
                 decimals=6, objects=True, flash=True, aperture="C,0.250000",
                 extra=()):
    """Build a small but structurally complete RS-274X file.

    The copper rectangle spans 0..30 mm x 0..20 mm.  Coordinates use the 4.6
    format declared in ``fmt`` (X46Y46).
    """
    lines = [
        "%TF.GenerationSoftware,synthetic,delivery-audit-fixture,1*%",
        "%%TF.FileFunction,%s*%%" % function,
        "%TF.FilePolarity,Positive*%",
        "%%%s*%%" % fmt,
        "%%MO%s*%%" % units,
        "%ADD10" + aperture + "*%",
        "%ADD11R,1.000000X1.000000*%",
        "G01*",
        "D10*",
        "X%sY%sD02*" % (_gerber_coord(1, decimals), _gerber_coord(1, decimals)),
    ]
    if objects:
        points = [(1, 1), (29, 1), (29, 19), (1, 19), (1, 1)]
        for index, (x, y) in enumerate(points):
            op = "D01" if index else "D01"
            lines.append("X%sY%s%s*" % (_gerber_coord(x, decimals),
                                        _gerber_coord(y, decimals), op))
    lines.extend(extra)
    if flash:
        lines.append("D11*")
        lines.append("X%sY%sD03*" % (_gerber_coord(15, decimals),
                                     _gerber_coord(10, decimals)))
    lines.append("M02*")
    return "\n".join(lines) + "\n"


def outline_gerber(width=30.0, height=20.0, close=True, extras=()):
    lines = [
        "%TF.FileFunction,Profile,NP*%",
        "%FSLAX46Y46*%",
        "%MOMM*%",
        "%ADD10C,0.100000*%",
        "G01*",
        "D10*",
        "X0Y0D02*",
        "X%sY0D01*" % _gerber_coord(width),
        "X%sY%sD01*" % (_gerber_coord(width), _gerber_coord(height)),
        "X0Y%sD01*" % _gerber_coord(height),
    ]
    if close:
        lines.append("X0Y0D01*")
    lines.extend(extras)
    lines.append("M02*")
    return "\n".join(lines) + "\n"


def drill_text(holes=None, units="METRIC", tools=None, end=True, header=True):
    """Build a decimal-coordinate Excellon drill file (common modern export)."""
    holes = holes if holes is not None else [(5.0, 5.0, 1), (10.0, 5.0, 1),
                                             (15.0, 5.0, 2), (20.0, 10.0, 2)]
    tools = tools if tools is not None else {1: 0.4, 2: 0.8}
    lines = []
    if header:
        lines += ["M48", ";DRILL file {synthetic}", ";FORMAT={-:-/ absolute / metric / decimal}",
                  "FMAT,2", units + ",TZ"]
        for code in sorted(tools):
            lines.append("T%dC%.3f" % (code, tools[code]))
        lines += ["%", "G90", "G05"]
    if holes:
        current = None
        for x, y, tool in holes:
            if tool != current:
                lines.append("T%d" % tool)
                current = tool
            lines.append("X%.3fY%.3f" % (x, y))
    if end:
        lines.append("M30")
    return "\n".join(lines) + "\n"


BOM_HEADER = ["Comment", "Designator", "Footprint", "Quantity", "MPN",
              "Manufacturer", "LCSC", "DNP", "Assembly"]


def bom_text(rows, header=None, delimiter=","):
    import csv
    header = header or BOM_HEADER
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(name, "") for name in header])
    return out.getvalue()


def default_bom_rows():
    return [
        {"Comment": "10k", "Designator": "R1", "Footprint": "0402", "Quantity": "1",
         "MPN": "RC0402FR-0710KL", "Manufacturer": "Yageo", "LCSC": "C12345",
         "DNP": "", "Assembly": "smt"},
        {"Comment": "100nF", "Designator": "C1,C2", "Footprint": "0402",
         "Quantity": "2", "MPN": "CL05B104KO5NNNC", "Manufacturer": "Samsung",
         "LCSC": "C54321", "DNP": "", "Assembly": "smt"},
        {"Comment": "LED", "Designator": "D1", "Footprint": "0603", "Quantity": "1",
         "MPN": "LTST-C190KGKT", "Manufacturer": "Lite-On", "LCSC": "C1234",
         "DNP": "", "Assembly": "smt"},
        {"Comment": "2.54 header", "Designator": "J1", "Footprint": "PinHeader",
         "Quantity": "1", "MPN": "PZ254V-11-04P", "Manufacturer": "XKB",
         "LCSC": "C2691448", "DNP": "", "Assembly": "tht"},
    ]


CPL_HEADER = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]


def cpl_text(rows, header=None, delimiter=",", unit="mm"):
    import csv
    header = header or CPL_HEADER
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(name, "") for name in header])
    return out.getvalue()


def default_cpl_rows():
    return [
        {"Designator": "R1", "Mid X": "10.000", "Mid Y": "10.000",
         "Layer": "Top", "Rotation": "0"},
        {"Designator": "C1", "Mid X": "15.000", "Mid Y": "10.000",
         "Layer": "Top", "Rotation": "90"},
        {"Designator": "C2", "Mid X": "20.000", "Mid Y": "10.000",
         "Layer": "Top", "Rotation": "270"},
        {"Designator": "D1", "Mid X": "25.000", "Mid Y": "10.000",
         "Layer": "Top", "Rotation": "180"},
    ]


def two_layer_package():
    """Return {logical path: bytes} for a legal 2-layer fabrication package."""
    return {
        "gerber/copper_top.gbr": gerber_layer("Copper,L1,Top").encode(),
        "gerber/copper_bottom.gbr": gerber_layer("Copper,L2,Bot").encode(),
        "gerber/profile.gbr": outline_gerber().encode(),
        "gerber/drill.drl": drill_text().encode(),
        "gerber/soldermask_top.gbr": gerber_layer("Soldermask,Top", objects=False).encode(),
        "gerber/soldermask_bottom.gbr": gerber_layer("Soldermask,Bot", objects=False).encode(),
    }


def four_layer_package():
    return {
        "gerber/copper_top.gbr": gerber_layer("Copper,L1,Top").encode(),
        "gerber/copper_inner1.gbr": gerber_layer("Copper,L2,Inr").encode(),
        "gerber/copper_inner2.gbr": gerber_layer("Copper,L3,Inr").encode(),
        "gerber/copper_bottom.gbr": gerber_layer("Copper,L4,Bot").encode(),
        "gerber/profile.gbr": outline_gerber().encode(),
        "gerber/drill.drl": drill_text().encode(),
    }


def smt_package():
    files = two_layer_package()
    files["bom.csv"] = bom_text(default_bom_rows()).encode()
    files["cpl.csv"] = cpl_text(default_cpl_rows()).encode()
    return files


def build_dir(root, files):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        write_bytes(root, rel, data)
    return root


def build_zip(path, files, compression=zipfile.ZIP_DEFLATED):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for rel, data in files.items():
            archive.writestr(rel, data if isinstance(data, bytes) else data.encode())
    return path


def zip_members(path):
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def hash_files(root, files):
    root = Path(root)
    return {rel: sha256_file(root / rel) for rel in sorted(files)}


ROLE_ORDER = [
    ("gerber/copper_top.gbr", "copper_top"),
    ("gerber/copper_bottom.gbr", "copper_bottom"),
    ("gerber/copper_inner1.gbr", "copper_inner"),
    ("gerber/copper_inner2.gbr", "copper_inner"),
    ("gerber/profile.gbr", "board_profile"),
    ("gerber/drill.drl", "drill"),
    ("gerber/soldermask_top.gbr", "soldermask_top"),
    ("gerber/soldermask_bottom.gbr", "soldermask_bottom"),
    ("bom.csv", "bom"),
    ("cpl.csv", "cpl"),
]


def content_digest(root, files):
    """Frozen ``delivery-content/v1`` digest (same algorithm as the tool)."""
    root = Path(root)
    payload = b"delivery-content/v1\n"
    for rel in sorted(files, key=lambda item: (str(item).casefold(), str(item))):
        data = (root / rel).read_bytes()
        payload += ("%s\t%d\t%s\n" % (sha256_bytes(data), len(data), rel)).encode("utf-8")
    return sha256_bytes(payload)


def declarations_for(root, files, *, profile="pcb-fabrication", extra=None):
    """Build a declarations object whose file hashes match ``root``."""
    root = Path(root)
    declared = []
    seen = set()
    for rel, role in ROLE_ORDER:
        if rel not in files:
            continue
        seen.add(rel)
        item = {"path": rel, "role": role, "sha256": sha256_file(root / rel),
                "source": "observed"}
        if role == "copper_inner":
            item["layer_index"] = 2 if "inner1" in rel else 3
        declared.append(item)
    for rel in sorted(files):
        if rel not in seen:
            declared.append({"path": rel, "role": "other", "sha256": sha256_file(root / rel),
                             "source": "observed"})
    data = {
        "schema": "delivery-declarations/v1",
        "project_id": "fixture-project",
        "revision": "A",
        "source_snapshot": {"hash_algorithm": "sha256", "value": "0" * 64,
                            "source": "user_declared", "reference": "synthetic fixture"},
        "export_session": {"id": "fixture", "tool": "synthetic", "tool_version": "1",
                           "captured_at": "2026-10-27T00:00:00+00:00"},
        "content_manifest": {"sha256": content_digest(root, files),
                             "source": "user_declared"},
        "files": declared,
        "stackup": {"layers": 4 if "gerber/copper_inner1.gbr" in files else 2,
                    "source": "user_declared"},
        "coordinates": {
            "origin": "board_lower_left", "x_axis": "right", "y_axis": "up",
            "rotation": "ccw_positive", "unit": "mm", "source": "user_declared",
            "bottom_side": {"mirror": "none", "rotation_offset_deg": 0,
                            "source": "user_declared"},
        },
        "policies": {"dnp_in_cpl": "forbidden", "tht_requires_cpl": False,
                     "mechanical_requires_cpl": False, "strict_file_set": True},
        "encodings": {"bom": "utf-8-sig", "cpl": "utf-8-sig"},
        "csv": {"bom_delimiter": ",", "cpl_delimiter": ","},
        "bom": {"required_fields": ["designator", "quantity"]},
        "board": {"exterior_allow_objects": False},
        "provenance": {"source": "user_declared",
                       "statement": "synthetic fixture declaration"},
    }
    if extra:
        data.update(extra)
    return data


def run_cli(args, *, cwd=None, timeout=180, env_extra=None):
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-m", "delivery_audit"] + [str(item) for item in args],
        cwd=str(cwd or SCRIPTS),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    return proc


def cli_report(proc):
    text = proc.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def run_audit(package, *, profile="pcb-fabrication", declarations=None,
              args=(), out=None, cwd=None):
    cmd = ["audit", "--input", str(package), "--profile", profile,
           "--generated-at", "2026-10-27T00:00:00+00:00"]
    if declarations is not None:
        cmd += ["--declarations", str(declarations)]
    if out is not None:
        cmd += ["--out", str(out)]
    cmd += [str(item) for item in args]
    proc = run_cli(cmd, cwd=cwd)
    return proc, cli_report(proc)


class CliTestCase(unittest.TestCase):
    maxDiff = None

    def tmpdir(self):
        directory = tempfile.TemporaryDirectory(prefix="delivery-audit-")
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def assertExit(self, proc, expected):
        self.assertEqual(proc.returncode, expected,
                         "stdout=%r\nstderr=%r" % (proc.stdout[-2000:], proc.stderr[-4000:]))

    def audit(self, files, *, profile="pcb-fabrication", declarations=True,
              mutate_declarations=None, out=None, extra_args=()):
        root = self.tmpdir() / "package"
        build_dir(root, files)
        decl_path = None
        if declarations:
            data = declarations_for(root, files, profile=profile)
            if mutate_declarations:
                mutate_declarations(data)
            decl_path = write_json(self.tmpdir() / "declarations.json", data)
        proc, report = run_audit(root, profile=profile, declarations=decl_path,
                                 args=extra_args, out=out)
        return proc, report, root
