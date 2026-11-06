"""给 layout-render 输入补 `sheet`（带它才按原坐标渲染，不重排）。

`SchematicRenderInput` 的真实结构（读 Go 源码得出）：

    {"schemaVersion":1, "title"?, "zones":[...], "sheet":{
        "bounds":{minX,minY,maxX,maxY}, "border":{...},
        "keepouts":[], "padding":10, "gap":10, "borderSource"?}}
    zone: {"id","title","layout","sheetPosition":{"x","y"}}

**没有 sheet 时渲染器自己装行（display-only zone packing）**，文字坐标会落在
它自己的 viewBox 里，和器件坐标不是一套 —— 那样测出来的"文字相压"全是坐标系
错位造成的假象（实测报出 10 项越页 + 24 项相压）。

带 `sheet` + `sheetPosition{0,0}` 时按原坐标渲染，两边才可比。
"""
import json
import pathlib
import sys


def build_zones_input(doc, padding=10.0, gap=10.0):
    zones = []
    for mod in doc.get("modules") or []:
        layout = {
            "schemaVersion": 1,
            "componentIds": {pl["designator"]: pl.get("primitiveId")
                             for pl in (mod.get("placements") or [])},
            "pinStates": {},
            "placements": [{
                "designator": pl["designator"],
                "x": pl["x"], "y": pl["y"],
                "rotation": pl.get("rotation", 0),
                "mirror": bool(pl.get("mirror", False)),
                "bbox": pl["bbox"],
                "pins": [{"number": p.get("number"), "name": p.get("name"),
                          "net": p.get("net") or "", "x": p["x"], "y": p["y"],
                          "rotation": p.get("rotation", 0)}
                         for p in (pl.get("pins") or [])],
            } for pl in (mod.get("placements") or [])],
            "wires": [{"net": w.get("net") or "",
                       "points": w.get("points") or []}
                      for w in (mod.get("wires") or [])],
            # flags 必须齐 net/kind/pinX/pinY/direction/offset
            "flags": [{"net": f.get("net") or "",
                       "kind": f.get("kind") or "net_label",
                       "pinX": f.get("pinX"), "pinY": f.get("pinY"),
                       "direction": f.get("direction") or "right",
                       "offset": f.get("offset", 10)}
                      for f in (mod.get("flags") or [])],
        }
        zones.append({"id": mod.get("id") or "",
                      "title": mod.get("title") or "",
                      "layout": layout,
                      # 几何已在页坐标里，所以 zone 原点就是 (0,0)
                      "sheetPosition": {"x": 0, "y": 0}})

    out = {"schemaVersion": 1, "zones": zones}
    sheet = doc.get("sheet") or {}
    if sheet:
        bounds = {"minX": sheet.get("minX", 0), "minY": sheet.get("minY", 0),
                  "maxX": sheet.get("maxX", 0), "maxY": sheet.get("maxY", 0)}
        out["sheet"] = {
            "bounds": bounds,
            "border": bounds,
            "keepouts": [],
            "padding": padding,
            "gap": gap,
        }
    return out


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])
    doc = json.loads(src.read_text(encoding="utf-8"))
    z = build_zones_input(doc)
    dst.write_text(json.dumps(z, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  %s → %s（%d zone，sheet %s）"
          % (src.name, dst.name, len(z["zones"]), "有" if z.get("sheet") else "无"))
