#!/usr/bin/env python3
"""把 `lib-layout` 的排版稿（composition）**合成 S3 度量要的快照**。

为什么需要它：`sch_offline_pipeline.py` 吃的是"冻结快照"（`list.json` /
`connectivity.json`），那是从**活体画布**读出来的。而 S3 发生在**落图之前** ——
这时画布上什么都没有，只有 `lib-layout` 算出来的排版稿。

于是形成死结：**要先落图才能度量，而落图又该在度量通过之后**。
这个脚本解的就是这个死结：排版稿里有完整的 placement（bbox + 引脚坐标 + 网）
和 wire（折线 + 网），足以合成一份等价快照，**不需要碰画布**。

产出的快照目录可直接喂给：

    python scripts/sch_offline_pipeline.py --snapshot-dir <out> \\
        --project <P> --page <P> --out-dir <reports>

快照内容：
    connectivity.json   排版稿自带的 connectivity（schemaVersion 1.4）
    list.json           从 modules[].placements / wires 合成的等价 list 响应

**声明边界**：合成快照里的 `svg-text.json` 没有（没有渲染图），所以文字覆盖类
检查会缺证据 —— 按管线规则这应当是 `BLOCKED`/`missing`，**不是通过**。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-composition-snapshot/v1"


def build(composition_paths, out_dir):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    components, wires, flags = [], [], []
    connectivity = None
    sheet = None
    page_id = ""

    for cp in composition_paths:
        doc = json.loads(pathlib.Path(cp).read_text(encoding="utf-8"))
        conn = doc.get("connectivity") or {}
        connectivity = connectivity or conn
        sheet = sheet or doc.get("sheet")
        page_id = page_id or (conn.get("documentId") or "")

        # **显式 NC 必须带进快照。**
        #
        # 技能文档早写过：连接度量要同时给 `--list`，否则显式 NC 引脚会被算成
        # 悬空（IR 不带 NC 标记）。第一版合成的快照把 `noConnected` 丢了，
        # 于是 spec 里标了 NC 的 `IGN_12V`（落在 J1 pin 2）被报成 floating_pin
        # —— 一个**假缺陷**，而假缺陷会让人去改本来正确的东西。
        pins_nc = {}
        for c in conn.get("components") or []:
            pins_nc[c.get("id")] = {p.get("number"): bool(p.get("noConnected"))
                                    for p in (c.get("pins") or [])}

        for mod in doc.get("modules") or []:
            for pl in mod.get("placements") or []:
                nc_map = pins_nc.get(pl.get("primitiveId")) or {}
                components.append({
                    "componentType": "part",
                    "primitiveId": pl.get("primitiveId"),
                    "designator": pl.get("designator"),
                    "x": pl.get("x"),
                    "y": pl.get("y"),
                    "rotation": pl.get("rotation"),
                    "mirror": pl.get("mirror", False),
                    "bbox": pl.get("bbox"),
                    # 适配器读 pinNumber / pinName / net / x / y
                    "pins": [
                        {"pinNumber": p.get("number"),
                         "pinName": p.get("name"),
                         "net": p.get("net"),
                         "x": p.get("x"),
                         "y": p.get("y"),
                         "rotation": p.get("rotation"),
                         "noConnected": bool(nc_map.get(p.get("number")))}
                        for p in (pl.get("pins") or [])
                    ],
                    "moduleId": mod.get("id"),
                })
            for w in mod.get("wires") or []:
                wires.append({
                    "Line": w.get("points") or [],
                    "Net": w.get("net") or "",
                    "primitiveId": w.get("primitiveId") or "",
                })
            for f in mod.get("flags") or []:
                flags.append({
                    "net": f.get("net"),
                    "kind": f.get("kind"),
                    "x": f.get("pinX"),
                    "y": f.get("pinY"),
                    "direction": f.get("direction"),
                })

    # `layout_from_easycirq.py` 从 `components[]` 里找 `componentType: "sheet"`
    # 的图元来取页边界；没有它就直接报
    # "sheet bbox or sheet-geometry bbox required for page bounds"。
    # 所以合成快照必须补一条 sheet 图元。
    if sheet:
        components.append({
            "componentType": "sheet",
            "primitiveId": "sheet",
            "bbox": sheet,
        })

    list_doc = {
        "ok": True,
        "result": {
            "pageId": page_id,
            "sheet": sheet,
            "components": components,
            "wires": wires,
            # 适配器按 dict 读 pagePrimitives（.get('texts')），给 [] 会崩
            "pagePrimitives": {},
            "netflags": flags,
        },
        # 合成来源：说明这份快照**不是**活体读数
        "source": {
            "kind": "composition",
            "note": "由 lib-layout 排版稿合成；没有渲染图，故无 svg-text.json",
            "inputs": [str(p) for p in composition_paths],
        },
    }

    (out / "list.json").write_text(
        json.dumps(list_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "connectivity.json").write_text(
        json.dumps(connectivity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "schema": SCHEMA,
        "outDir": str(out),
        "components": len(components),
        "wires": len(wires),
        "flags": len(flags),
        "nets": len(connectivity.get("nets") or []),
        "pageId": page_id,
        "hasRenderedText": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="composition → S3 快照")
    ap.add_argument("--composition", action="append", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    for cp in args.composition:
        if not pathlib.Path(cp).is_file():
            print("找不到排版稿：%s" % cp, file=sys.stderr)
            return 2

    info = build(args.composition, args.out_dir)
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print("快照 → %s" % info["outDir"])
        print("  器件 %d，导线 %d，网标 %d，网 %d"
              % (info["components"], info["wires"], info["flags"], info["nets"]))
        print("  pageId: %s" % info["pageId"])
        print("  ⚠ 没有渲染图 → 无 svg-text.json；文字覆盖类检查会缺证据")
        print("    按管线规则这应当是 BLOCKED/missing，**不是通过**。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
