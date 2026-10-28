"""Capture the official CLI's offline API catalog into evidence receipts.

``lceda-pro doc api`` needs no editor session and no network.  The receipts let
the coverage matrix cite the exact method surface (create/save/export/DRC/...)
instead of relying on prose.  Run once per evidence date:

    python spike/a2-coverage/capture_api_catalog.py --evidence-date 2026-10-28
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import official_cli  # noqa: E402
from common import enable_utf8_stdout, now_iso, sha256_bytes, write_json, write_text  # noqa: E402

CLASSES = [
    "DMT_Project",
    "DMT_Schematic",
    "DMT_Pcb",
    "DMT_Board",
    "DMT_EditorControl",
    "SCH_Document",
    "SCH_Drc",
    "SCH_ManufactureData",
    "SCH_PrimitiveComponent",
    "SCH_PrimitiveWire",
    "SCH_Net",
    "SCH_Netlist",
    "PCB_Document",
    "PCB_Drc",
    "PCB_ManufactureData",
    "PCB_PrimitiveComponent",
    "PCB_Layer",
    "PCB_Net",
    "SYS_FileSystem",
    "SYS_Environment",
]

METHODS = [
    ("DMT_Project", "createProject"),
    ("DMT_Project", "openProject"),
    ("DMT_Project", "getCurrentProjectInfo"),
    ("DMT_Project", "getReadyState"),
    ("DMT_Schematic", "createSchematic"),
    ("DMT_Schematic", "createSchematicPage"),
    ("DMT_Pcb", "createPcb"),
    ("DMT_Board", "createBoard"),
    ("DMT_EditorControl", "openDocument"),
    ("DMT_EditorControl", "activateDocument"),
    ("DMT_EditorControl", "waitForDocumentReady"),
    ("SCH_Document", "save"),
    ("SCH_PrimitiveComponent", "create"),
    ("SCH_PrimitiveComponent", "modify"),
    ("SCH_PrimitiveComponent", "createNetFlag"),
    ("SCH_PrimitiveWire", "create"),
    ("SCH_PrimitiveAttribute", "createNetLabel"),
    ("SCH_Drc", "check"),
    ("SCH_ManufactureData", "getNetlistFile"),
    ("SCH_ManufactureData", "getBomFile"),
    ("SCH_ManufactureData", "getPngFile"),
    ("PCB_Document", "importChanges"),
    ("PCB_Document", "save"),
    ("PCB_PrimitiveComponent", "modify"),
    ("PCB_Document", "autoRouting"),
    ("PCB_Drc", "check"),
    ("PCB_ManufactureData", "getGerberFile"),
    ("PCB_ManufactureData", "getPickAndPlaceFile"),
    ("PCB_ManufactureData", "get3DFile"),
    ("SYS_FileSystem", "getProjectsPaths"),
    ("SYS_FileSystem", "saveFileToFileSystem"),
]


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", default=None)
    parser.add_argument("--evidence-date", default="2026-10-28")
    args = parser.parse_args(argv)

    exe = official_cli.find_exe(args.exe)
    api_dir = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "evidence"
        / f"a2-coverage-{args.evidence_date}"
        / "api"
    )
    api_dir.mkdir(parents=True, exist_ok=True)
    index: dict = {"captured_at": now_iso(), "exe": exe, "classes": {}, "methods": {}}

    classes_res = official_cli.doc_api(exe)
    write_text(api_dir / "class-list.json", classes_res.stdout)
    type_names = []
    if isinstance(classes_res.json, dict):
        type_names = [t.get("name") for t in classes_res.json.get("value", {}).get("types", [])]
    index["class_list"] = {
        "file": "api/class-list.json",
        "exit_code": classes_res.exit_code,
        "type_count": len(type_names),
        "sha256": sha256_bytes(classes_res.stdout.encode("utf-8")),
    }

    for cls in CLASSES:
        res = official_cli.doc_api(exe, class_name=cls)
        write_text(api_dir / f"{cls}.json", res.stdout)
        methods = []
        if isinstance(res.json, dict) and res.json.get("ok"):
            methods = [m.get("name") for m in res.json.get("value", {}).get("methods", [])]
        index["classes"][cls] = {
            "file": f"api/{cls}.json",
            "exit_code": res.exit_code,
            "method_count": len(methods),
            "methods": methods,
            "sha256": sha256_bytes(res.stdout.encode("utf-8")),
        }

    for cls, method in METHODS:
        res = official_cli.doc_api(exe, class_name=cls, method_name=method)
        rel = f"{cls}.{method}.json"
        write_text(api_dir / rel, res.stdout)
        entry = {"file": f"api/{rel}", "exit_code": res.exit_code, "ok": bool((res.json or {}).get("ok"))}
        if isinstance(res.json, dict) and res.json.get("ok"):
            value = res.json.get("value", {})
            entry["returns"] = (value.get("returns") or {}).get("type")
            entry["params"] = [p.get("name") for p in value.get("params", [])]
            entry["visibility"] = value.get("visibility")
        index["methods"][f"{cls}.{method}"] = entry

    write_json(api_dir / "index.json", index)
    print(f"captured {len(index['classes'])} classes, {len(index['methods'])} methods, "
          f"{len(type_names)} types -> {api_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
