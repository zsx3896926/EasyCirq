"""BOM 与原理图是否一致。

由来：2026-11-01 发现交付包里的 BOM 是**修复前**导出的旧版——含早已删掉的 `D1`、`R11`，
缺 `Q1`、`R4`（正是让蜂鸣器能响的那两颗）。客户按那份 BOM 配单，
板子会少一颗三极管和一颗基极电阻，**永远不响**。

这和 KPI 17（图板一致）是同一类错误，只是对象换成 BOM。所以单独成检：
原理图里有的每个器件都必须出现在 BOM 里，BOM 里不许有不存在的位号。

用法：
    python scripts/sch_bom_match.py --schematic list.json --bom bom.csv
    python scripts/sch_bom_match.py --schematic list.json --bom bom.tsv --json

退出码：0 = 一致；2 = 不一致；3 = 输入无法解析。
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

DESIGNATOR_HINTS = ("designator", "位号", "reference", "ref")


def read_json(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path}: no JSON object found")
    return json.loads(text[start:])


def schematic_designators(payload) -> set:
    """Non-empty designators of real parts (skips frame/text entries)."""
    root = payload.get("result") or payload
    components = root.get("components") or []
    found = set()
    for item in components:
        kind = (item.get("componentType") or "").lower()
        if kind and kind not in ("part", "component"):
            continue
        designator = (item.get("designator") or "").strip()
        if designator:
            found.add(designator)
    return found


def _delimiter(text: str) -> str:
    first = text.splitlines()[0] if text.splitlines() else ""
    return "\t" if first.count("\t") >= first.count(",") else ","


def bom_designators(path: Path) -> set:
    """Designators listed in a BOM, tolerating tab or comma separated files."""
    raw = path.read_bytes()
    if raw[:4] == b"PK\x03\x04":
        raise ValueError(
            f"{path} is an .xlsx; export a CSV/TSV instead (Excel BOM exports cannot be read here)"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace")
    delimiter = _delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError(f"{path}: no header row")

    column = None
    for name in reader.fieldnames:
        if any(hint in (name or "").lower() for hint in DESIGNATOR_HINTS):
            column = name
            break
    if column is None:
        raise ValueError(f"{path}: no designator column in {reader.fieldnames}")

    found = set()
    for row in reader:
        cell = (row.get(column) or "").strip()
        for part in cell.split(","):
            part = part.strip()
            if part:
                found.add(part)
    return found


def compare(schematic: set, bom: set) -> dict:
    return {
        "schematic_count": len(schematic),
        "bom_count": len(bom),
        "missing_from_bom": sorted(schematic - bom),
        "not_in_schematic": sorted(bom - schematic),
        "ok": schematic == bom,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--schematic", required=True, help="sch list --include-pins 的 JSON 输出")
    parser.add_argument("--bom", required=True, help="BOM 的 CSV / TSV")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        schematic = schematic_designators(read_json(Path(args.schematic)))
        bom = bom_designators(Path(args.bom))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else f"BLOCKED: {exc}")
        return 3

    result = compare(schematic, bom)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        verdict = "PASS" if result["ok"] else "FAIL"
        print(f"BOM 与原理图 {verdict}：原理图 {result['schematic_count']} 个位号，"
              f"BOM {result['bom_count']} 个")
        if result["missing_from_bom"]:
            print("  原理图有、BOM 没有：" + ", ".join(result["missing_from_bom"]))
            print("  → 按这份 BOM 配单会缺件，板子做不出来")
        if result["not_in_schematic"]:
            print("  BOM 有、原理图没有：" + ", ".join(result["not_in_schematic"]))
            print("  → 这份 BOM 是旧版，或者引用了已删除的器件")

    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
