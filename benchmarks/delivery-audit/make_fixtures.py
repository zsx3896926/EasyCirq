#!/usr/bin/env python3
"""Freeze the delivery-audit benchmark fixtures.

Run from the repository root:

    python benchmarks/delivery-audit/make_fixtures.py

The generated ``fixtures/<case>/`` content is committed.  Rebuild only when a
fixture intentionally changes; the recorded content digest then changes too and
the benchmark will require a reviewed update.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import cases as case_defs  # noqa: E402
import digest  # noqa: E402
from tests.delivery_audit import support  # noqa: E402

FIXTURES = HERE / "fixtures"
REAL_SAMPLE = HERE / "real-sample"


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")


def build_input(case_dir, spec):
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    if "files" in spec:
        files = spec["files"]()
        if spec.get("input_kind") == "zip":
            archive = input_dir / "package.zip"
            archive.write_bytes(case_defs.zip_bytes(files))
            return input_dir, "input/package.zip", "zip", files
        support.build_dir(input_dir, files)
        return input_dir, "input", "files", files
    if "raw" in spec:
        for name, data in spec["raw"].items():
            (input_dir / name).write_bytes(data)
        names = sorted(spec["raw"])
        return input_dir, "input/" + names[0], "single", spec["raw"]
    input_dir.mkdir(parents=True, exist_ok=True)
    return input_dir, "input", "files", {}


def build_declarations(case_dir, spec, files):
    if not spec.get("declarations"):
        return
    with tempfile.TemporaryDirectory(prefix="da-decl-") as tmp:
        staging = Path(tmp)
        support.build_dir(staging, files)
        data = support.declarations_for(staging, files,
                                        profile=spec.get("profile",
                                                         "pcb-fabrication"))
    mutate = spec.get("declarations")
    if callable(mutate):
        mutate(data)
    write_json(case_dir / "declarations.json", data)


def real_sample_files():
    if not REAL_SAMPLE.is_dir():
        return None
    files = {}
    for path in sorted(REAL_SAMPLE.rglob("*")):
        if not path.is_file():
            continue
        name = path.name.upper()
        if name in ("SOURCE.MD", "LICENSE", "LICENSE-APACHE-2.0.TXT"):
            continue
        suffix = path.suffix.casefold()
        if suffix in (".gbr", ".gko", ".gm1", ".gtl", ".gbl", ".gts", ".gbs",
                      ".gto", ".gbo", ".drl", ".drd", ".xln", ".csv"):
            files["real/" + path.name] = path.read_bytes()
    return files or None


def observed_expectations(package_path):
    """Freeze what the current CLI reports for an unbound real sample.

    This is a replay regression baseline, not an acceptance claim.  No
    declarations are supplied, so provenance stays unverified by design.
    """
    proc = support.run_cli(["audit", "--input", str(package_path),
                            "--profile", "pcb-fabrication",
                            "--generated-at", case_defs.AT])
    report = support.cli_report(proc)
    if report is None:
        return {"exit": proc.returncode, "status": "no_json"}
    rules = {}
    for item in report.get("findings") or []:
        if item["status"] in ("fail", "unknown"):
            rules[item["rule_id"]] = item["status"]
    return {"exit": proc.returncode, "status": report["status"],
            "rules": rules, "no_real_eda": True}


def main():
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)
    FIXTURES.mkdir(parents=True)
    specs = list(case_defs.CASES)

    sample = real_sample_files()
    if sample:
        spec = dict(case_defs.REAL_SAMPLE_CASE)
        spec["files"] = lambda sample=sample: sample
        specs.append(spec)

    generated = []
    for spec in specs:
        case_dir = FIXTURES / spec["id"]
        case_dir.mkdir(parents=True)
        input_dir, input_rel, input_kind, files = build_input(case_dir, spec)
        build_declarations(case_dir, spec, files)
        if spec.get("reference"):
            write_json(case_dir / "reference.json", spec["reference"]())
        if input_kind == "files":
            entries = digest.directory_entries(input_dir)
        elif input_kind == "zip":
            entries = digest.zip_entries(input_dir / "package.zip")
        else:
            entries = digest.file_entries(input_dir / Path(input_rel).name)
        metadata = {
            "id": spec["id"],
            "title": spec["title"],
            "command": spec.get("command", "audit"),
            "profile": spec.get("profile"),
            "input": input_rel,
            "input_kind": input_kind,
            "declarations": "declarations.json" if spec.get("declarations") else None,
            "reference": "reference.json" if spec.get("reference") else None,
            "args": list(spec.get("args") or []),
            "touch": spec.get("touch"),
            "expect": dict(spec.get("expect") or {}),
            "simulated": spec.get("simulated", True),
            "notes": spec.get("notes"),
            "content_digest": digest.content_digest(entries),
            "files": digest.describe(entries),
        }
        if spec["id"] == case_defs.REAL_SAMPLE_CASE["id"]:
            metadata["expect"] = observed_expectations(input_dir)
            metadata["notes"] = (case_defs.REAL_SAMPLE_CASE["notes"]
                                 + " Expectations frozen from the replay run on "
                                   "2026-10-27; they are not manufacturing claims.")
        if input_kind in ("zip", "single"):
            target = input_dir / Path(input_rel).name
            metadata["input_sha256"] = digest.content_digest(
                digest.file_entries(target))
        write_json(case_dir / "case.json", metadata)
        generated.append(spec["id"])

    print("generated %d frozen cases under %s" % (len(generated), FIXTURES))
    for case_id in generated:
        print(" -", case_id)


if __name__ == "__main__":
    main()
