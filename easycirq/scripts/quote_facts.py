"""把「这块板报价需要哪些参数」算出来。

动机：客户说「做一个能测温度、超温就响的板子」之后，第一个问题是
「能不能做、多少钱、多久」。前两个我一直在手工回答，换一块板就要重算一次。

价格本身取决于订单选项（打样几片、是否贴片、是否加急），所以这里**不给价格**，
只给板厂计价器要的那几个数——这些是板子的属性，不是订单的选项：

    板框尺寸 / 面积 / 铜层数 / 器件数 / 顶层底层分布 /
    贴片点数 / 直插件数 / BOM 料种与总用量 / 是否要钻孔

用法：
    python scripts/quote_facts.py --pcb board.json --bom bom.csv
    python scripts/quote_facts.py --pcb board.json --bom bom.csv --json

退出码：0 = 算出来了；3 = 输入读不出来。
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

import sys

# Windows consoles default to GBK; these tools print Chinese status text, so pin
# the output encoding rather than depending on the caller's environment.
for _stream in ("stdout", "stderr"):
    _handle = getattr(sys, _stream, None)
    if hasattr(_handle, "reconfigure"):
        _handle.reconfigure(encoding="utf-8", errors="replace")


MIL_TO_MM = 0.0254
THT_HINTS = ("th_", "th-", "through", "dip", "radial")


def read_json(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path}: no JSON object found")
    return json.loads(text[start:])


def _is_bottom(layer) -> bool:
    if isinstance(layer, str):
        return "bottom" in layer.lower()
    return layer == 2


def board_facts(payload) -> dict:
    root = payload.get("result") or payload
    outline = root.get("outline") or {}
    bbox = outline.get("bbox") or {}
    width_mil = float(bbox.get("maxX", 0)) - float(bbox.get("minX", 0))
    height_mil = float(bbox.get("maxY", 0)) - float(bbox.get("minY", 0))

    components = root.get("components") or []
    top = sum(1 for c in components if not _is_bottom(c.get("layer")))
    bottom = len(components) - top

    return {
        "outline_source": outline.get("source"),
        "width_mm": round(width_mil * MIL_TO_MM, 2),
        "height_mm": round(height_mil * MIL_TO_MM, 2),
        "area_cm2": round(width_mil * height_mil * MIL_TO_MM * MIL_TO_MM / 100.0, 2),
        "copper_layers": root.get("copperLayers"),
        "component_count": len(components),
        "components_top": top,
        "components_bottom": bottom,
    }


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:4] == b"PK\x03\x04":
        raise ValueError(f"{path} is an .xlsx; export CSV/TSV first")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace")


def bom_facts(path: Path) -> dict:
    text = _read_text(path)
    first = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "\t" if first.count("\t") >= first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError(f"{path}: no header row")

    def find(*hints):
        for name in reader.fieldnames:
            lowered = (name or "").lower()
            if any(hint in lowered for hint in hints):
                return name
        return None

    qty_col = find("quantity", "数量")
    des_col = find("designator", "位号")
    fp_col = find("footprint", "封装")
    part_col = find("supplier part", "manufacturer part", "c编号", "供应商")

    rows = list(reader)
    total_qty = 0
    tht_placements = 0
    smt_placements = 0
    with_part_number = 0
    for row in rows:
        try:
            qty = int(float((row.get(qty_col) or "0").strip() or 0))
        except (TypeError, ValueError):
            qty = 0
        total_qty += qty
        footprint = (row.get(fp_col) or "").lower() if fp_col else ""
        is_tht = any(hint in footprint for hint in THT_HINTS)
        if is_tht:
            tht_placements += qty
        else:
            smt_placements += qty
        if part_col and (row.get(part_col) or "").strip():
            with_part_number += 1

    return {
        "line_items": len(rows),
        "total_quantity": total_qty,
        "smt_placements": smt_placements,
        "tht_placements": tht_placements,
        "line_items_with_part_number": with_part_number,
        "drilling_required": tht_placements > 0,
    }


def combine(board: dict, bom: dict) -> dict:
    notes = []
    if bom["tht_placements"]:
        notes.append(
            f"有 {bom['tht_placements']} 个直插件：需要钻孔，贴片通常不覆盖，要单独工序或手焊"
        )
    if board["components_bottom"]:
        notes.append("底层有器件：需要双面贴片，多一次过炉")
    else:
        notes.append("器件全在顶层：一次过炉即可")
    if bom["line_items_with_part_number"] < bom["line_items"]:
        missing = bom["line_items"] - bom["line_items_with_part_number"]
        notes.append(f"{missing} 种料没有供应商编号：配单时要人工选型，可能等料")
    return {
        "schema": "easycirq-quote-facts/v1",
        "board": board,
        "bom": bom,
        "notes": notes,
        "price": None,
        "leadtime": None,
        "price_status": "NOT RUN",
        "leadtime_status": "NOT RUN",
        "why_no_price": (
            "价格由订单选项决定（打样几片、是否贴片、是否加急、表面处理），"
            "不是板子的属性。把上面这些数填进板厂计价器即可得到报价。"
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pcb", required=True, help="pcb dump 的 JSON")
    parser.add_argument("--bom", required=True, help="BOM 的 CSV / TSV")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        board = board_facts(read_json(Path(args.pcb)))
        bom = bom_facts(Path(args.bom))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"BLOCKED: {exc}" if not args.json else json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 3

    result = combine(board, bom)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    b, m = result["board"], result["bom"]
    print(f"板框      {b['width_mm']} x {b['height_mm']} mm  ({b['area_cm2']} cm²)")
    print(f"铜层      {b['copper_layers']}")
    print(f"器件      {b['component_count']} 个（顶层 {b['components_top']} / 底层 {b['components_bottom']}）")
    print(f"贴片点    {m['smt_placements']}")
    print(f"直插件    {m['tht_placements']}")
    print(f"BOM       {m['line_items']} 种料，总用量 {m['total_quantity']}")
    print(f"钻孔      {'需要' if m['drilling_required'] else '不需要'}")
    print()
    for note in result["notes"]:
        print(f"注意：{note}")
    print()
    print("价格与交期：NOT RUN —— " + result["why_no_price"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
