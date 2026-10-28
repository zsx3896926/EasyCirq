"""Diagnose footprint-embedded board-outline defects from real PCB DRC output.

Field evidence (2026-10-28, EasyEDA Pro 4.1.78 + easycirq-connector 0.1.2):
a footprint that embeds a BOARD_OUTLINE object makes native DRC report
"Board Outline to SMD Pad" clearance errors *inside the same footprint*.
The offending object is a child primitive of the component: it is NOT returned by
`pcb_PrimitiveLine/Arc/Polyline.getAll()` (so a layer-11 scan cannot see it), and
deleting it by id reports success but the engine materialises it again on
save+reload. The reliable fix is therefore at the component/footprint level
(`sch replace` to a device without that outline, or fix the library footprint).

This tool turns that evidence into a deterministic diagnosis instead of a failed
delete: it reads fresh DRC + component inventory and names the exact designators,
pads and offending primitive ids, with the recommended repair path.

    python tools/easycirq_footprint_outline_diagnose.py [--json] [--evidence-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_EVID = REPO / "docs/toolchain-integration/evidence/outline-foreign"


def easycirq(*args: str, timeout: int = 300):
    return subprocess.run(["easycirq", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def load_json_output(proc) -> dict | None:
    text = proc.stdout
    idx = text.find("{")
    if idx < 0:
        return None
    try:
        return json.loads(text[idx:])
    except Exception:
        return None


def walk_violations(node, out):
    """Flatten the native DRconstructor violation tree into leaf errors."""
    if isinstance(node, dict):
        if "errorObjType" in node or ("errorType" in node and "explanation" in node):
            out.append(node)
        for value in node.values():
            walk_violations(value, out)
    elif isinstance(node, list):
        for value in node:
            walk_violations(value, out)


def leaf_errors(violations) -> list[dict]:
    leaves: list[dict] = []
    walk_violations(violations, leaves)
    # keep only leaves (no nested lists)
    return [v for v in leaves if not isinstance(v.get("list"), list)]


def designator_from_suffix(suffix: str) -> str:
    # e.g. ": SW1_3" -> SW1 ; ": e0e19" -> ""
    m = re.match(r"^:\s*([A-Za-z_]+\d+)_\d+\s*$", suffix or "")
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--evidence-dir", default=str(DEFAULT_EVID))
    args = ap.parse_args()
    evid = Path(args.evidence_dir)
    evid.mkdir(parents=True, exist_ok=True)

    drc_proc = easycirq("pcb", "drc")
    drc = load_json_output(drc_proc)
    if not drc:
        print("BLOCKED: pcb drc did not return JSON:", (drc_proc.stderr or drc_proc.stdout)[:200])
        return 2
    result = drc.get("result") or {}
    leaves = leaf_errors(result.get("violations") or [])

    comps_proc = easycirq("pcb", "list")
    comps_doc = load_json_output(comps_proc) or {}
    designs = {c.get("designator") for c in (comps_doc.get("result") or {}).get("components") or []
               if c.get("designator")}

    defects: dict[str, dict] = {}
    other = 0
    for leaf in leaves:
        err = (leaf.get("explanation") or {}).get("errData") or {}
        obj1_type = str(err.get("obj1Type") or "")
        obj2_type = str(err.get("obj2Type") or "")
        if "Board Outline" not in obj1_type and "Board Outline" not in obj2_type:
            other += 1
            continue
        same = bool(err.get("isInSameComponent"))
        suffix = str(err.get("obj2Suffix") or err.get("obj1Suffix") or "")
        des = designator_from_suffix(suffix)
        if not des:
            for d in designs:
                if d and (f"{d}_" in suffix):
                    des = d
                    break
        if not des:
            other += 1
            continue
        item = defects.setdefault(des, {
            "designator": des,
            "violations": 0,
            "affectedPads": set(),
            "outlineObjectIds": set(),
            "sameFootprint": same,
            "rule": str(err.get("name") or ""),
            "minDistanceMm": round(float(err.get("minDistance") or 0) * 0.0254, 4),
            "requiredMm": round(float(err.get("clearance") or 0) * 0.0254, 4),
        })
        item["violations"] += 1
        item["sameFootprint"] = item["sameFootprint"] or same
        if obj2_type == "SMD Pad" or "Pad" in obj2_type:
            item["affectedPads"].add(str(err.get("obj2Suffix") or "").strip(": "))
        if "Board Outline" in obj1_type and err.get("obj1"):
            item["outlineObjectIds"].add(str(err["obj1"]))
        if "Board Outline" in obj2_type and err.get("obj2"):
            item["outlineObjectIds"].add(str(err["obj2"]))

    for item in defects.values():
        item["affectedPads"] = sorted(p for p in item["affectedPads"] if p)
        item["outlineObjectIds"] = sorted(item["outlineObjectIds"])
        item["diagnosis"] = (
            "该器件的封装内含 Board Outline 图形；原生 DRC 会把它和同一封装的焊盘比间距，"
            "产生永久违规。该对象不是层 11 的普通图元，按 id 删除后引擎会在保存/重载时重建，"
            "因此删除不是可靠修复。"
        )
        item["recommendedFix"] = [
            "换器件：sch replace --designator %s --lib <lib> --uuid <无内嵌 outline 的同类器件>，再同步 PCB" % item["designator"],
            "或换封装：sch rebind-footprint（同电气、不同 footprint）后重新同步",
            "或改库：在封装编辑里删除该 Board Outline 图形（根因修复）",
            "修复后必须 pcb save → doc reload → pcb drc 复验",
        ]

    summary = {
        "schema": "easycirq-footprint-outline-diagnose/v1",
        "pcbDrcPassed": bool(result.get("passed")),
        "violationCount": len(result.get("violations") or []),
        "leafErrorCount": len(leaves),
        "footprintOutlineDefects": list(defects.values()),
        "otherLeafErrors": other,
        "verdict": "DEFECT_FOUND" if defects else ("PASS" if result.get("passed") else "OTHER_ERRORS"),
        "evidence": {
            "drc": "pcb drc output captured by the caller",
            "note": "delete-by-id was tested on this host: it reported success but the primitive "
                    "was present again after save+reload, so the tool recommends a component/"
                    "footprint-level fix instead of pretending to remove it",
        },
    }
    (evid / "diagnose.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                        encoding="utf-8")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("PCB DRC passed:", summary["pcbDrcPassed"],
              "| violations:", summary["violationCount"], "| leaf errors:", len(leaves))
        if not defects:
            print("verdict:", summary["verdict"], "(no footprint-embedded outline defect found)")
        for item in summary["footprintOutlineDefects"]:
            print(f"\n器件 {item['designator']}: {item['violations']} 条同封装 Board Outline 违规"
                  f"（影响焊盘 {len(item['affectedPads'])} 个，最小间距 {item['minDistanceMm']} mm < "
                  f"{item['requiredMm']} mm）")
            print("  outline object ids:", ", ".join(item["outlineObjectIds"]))
            print("  诊断:", item["diagnosis"])
            print("  建议修复:")
            for fix in item["recommendedFix"]:
                print("   -", fix)
    return 0 if not defects else 1


if __name__ == "__main__":
    sys.exit(main())
