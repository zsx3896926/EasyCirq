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
import math
import pathlib
import sys


def _zone_title_size():
    """从 style-tokens 取区名字号上限（读不到就退回 18）。"""
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        toks = json.loads((root / "assets" / "style-reference"
                           / "style-tokens.json").read_text(encoding="utf-8"))
        spec = (toks.get("typography") or {}).get("zone_title") or {}
        hi = spec.get("max")
        return int(hi) if hi else 18
    except (OSError, ValueError):
        return 18


def build_zones_input(doc, padding=10.0, gap=10.0, label_reserve=True):
    zones = []
    for mod in doc.get("modules") or []:
        # pinStates：**无网的引脚必须显式声明状态**，否则渲染器报
        # "<ref>.<pin> lacks explicit pin state"；有网的引脚必须留空，
        # 否则报 "conflicting pin state"。合法值只有 nc / unconnected。
        pin_states = {}
        for pl in (mod.get("placements") or []):
            pid = pl.get("primitiveId") or ""
            row = {}
            for q in (pl.get("pins") or []):
                if not (q.get("net") or "").strip() and q.get("number"):
                    row[str(q["number"])] = "nc"
            if row:
                pin_states[pid] = row
        layout = {
            "schemaVersion": 1,
            "componentIds": {pl["designator"]: pl.get("primitiveId")
                             for pl in (mod.get("placements") or [])},
            "pinStates": pin_states,
            # 位号预留区：按**实测渲染偏移**给出，供渲染门执行
            # "导线不许穿过位号"（libValidateWireTextClearance）。
            # 实测（7/7 器件一致）：x 从 minX-2 起，y 从 maxY-0.5 到 maxY+7.5。
            "placements": [{
                "designator": pl["designator"],
                "x": pl["x"], "y": pl["y"],
                "rotation": pl.get("rotation", 0),
                "mirror": bool(pl.get("mirror", False)),
                "bbox": pl["bbox"],
                # 位号预留区：**默认给出**；`--no-label-boxes` 时不写。
                # 实测（#114）：不注入时 M1/M2 也能 0 穿线 —— 说明注入框
                # 比实际文字大，会误拦本来没问题的排版。
                **({"textBboxes": [{
                    "minX": round(pl["bbox"]["minX"] - 2.0, 1),
                    "minY": round(pl["bbox"]["maxY"] - 0.5, 1),
                    "maxX": round(pl["bbox"]["minX"] - 2.0
                                  + max(6.0, 0.75 * 7.0
                                        * max(1, len(pl.get("designator") or ""))), 1),
                    "maxY": round(pl["bbox"]["maxY"] + 7.5, 1),
                }]} if label_reserve else {}),
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
        # 模块框：要包住**渲染器认定的全部内容**
        # （`powerLayoutContentObstacles` = 器件 bbox + 引脚 + 导线 + 网标）。
        # 只按器件 bbox 外扩会被判 "frame clips content"。
        xs, ys = [], []
        for pl in (mod.get("placements") or []):
            b = pl.get("bbox") or {}
            if b:
                xs += [b["minX"], b["maxX"]]
                ys += [b["minY"], b["maxY"]]
            for q in (pl.get("pins") or []):
                if q.get("x") is not None:
                    xs.append(q["x"])
                    ys.append(q["y"])
        for w in (mod.get("wires") or []):
            for pt in w.get("points") or []:
                xs.append(pt[0])
                ys.append(pt[1])
        for f in (mod.get("flags") or []):
            if f.get("pinX") is not None:
                # 网标有实体（箭头/菱形）+ offset，给足余量
                off = float(f.get("offset") or 10)
                xs += [f["pinX"] - off - 20, f["pinX"] + off + 20]
                ys += [f["pinY"] - off - 20, f["pinY"] + off + 20]
        frame = None
        pos = None
        if xs:
            pad = 18.0
            r = {"minX": min(xs) - pad, "minY": min(ys) - pad,
                 "maxX": max(xs) + pad, "maxY": max(ys) + pad}
            frame = {
                "id": mod.get("id") or "",
                "title": mod.get("title") or "",
                "rect": r,
                "titleX": r["minX"] + 4,
                "titleY": r["maxY"] - 4,
                # 字号必须落在 style-tokens.typography.zone_title（12~18）内；
                # 原来写死 20，超出上限，违反图面基准。
                "fontSize": _zone_title_size(),
                "color": "#AA00AA",
                "lineType": 1,
            }
            # **sheetPosition 是框的左上角**（读 schPreviewRect 得出）：
            # 矩形往下展开 p.Y-框高 .. p.Y，往右展开 p.X .. p.X+框宽。
            # 给 {0,0} 会让框落在负 y，报 violates page padding。
            #
            # 还必须落在 5-raw 锚点网格上：Go 用
            # `plFloor(v) = floor((v+1e-8)/5)*5` 校验 `p.X == plFloor(p.X)`，
            # 所以坐标要向下取整到 5 的倍数。
            grid = 5.0
            pos = {"x": math.floor(r["minX"] / grid) * grid,
                   "y": math.floor(r["maxY"] / grid) * grid}

        zone = {"id": mod.get("id") or "",
                "title": mod.get("title") or "",
                "layout": layout}
        # **真实模块框**（内容并集 + 18 raw，与 sch_composition_snapshot 同算法）。
        # 驱动会放大 frame.rect，渲染器判"位号是否在框内"必须用这个。
        _bs = [pl["bbox"] for pl in (mod.get("placements") or []) if pl.get("bbox")]
        if _bs:
            zone["realFrame"] = {
                "minX": min(b["minX"] for b in _bs) - 18.0,
                "minY": min(b["minY"] for b in _bs) - 18.0,
                "maxX": max(b["maxX"] for b in _bs) + 18.0,
                "maxY": max(b["maxY"] for b in _bs) + 18.0,
            }
        if frame:
            zone["frame"] = frame
            zone["sheetPosition"] = pos
        zones.append(zone)

    out = {"schemaVersion": 1, "zones": zones}
    sheet = doc.get("sheet") or {}
    if sheet:
        bounds = {"minX": sheet.get("minX", 0), "minY": sheet.get("minY", 0),
                  "maxX": sheet.get("maxX", 0), "maxY": sheet.get("maxY", 0)}
        # 图签：按**真实页**右下角算（不跟 border 放大），宽 190 高 76，内缩 14。
        # 必须独立于 border：border 会被驱动放大到包住模块框，
        # 一放大图签就落到页外并被 --page-bounds 过滤（friction #81）。
        tw, th = 190.0, 76.0
        title_block = {
            "minX": bounds["maxX"] - tw - 14,
            "minY": bounds["minY"] + 14,
            "maxX": bounds["maxX"] - 14,
            "maxY": bounds["minY"] + 14 + th,
        }
        # 真实纸型：由真实页尺寸判定，供图签 `SIZE` 使用。
        # 驱动会放大画布，渲染器自己推会得出错的纸型（实测 A2 被报成 A0）。
        _w = bounds["maxX"] - bounds["minX"]
        _paper = ("A0" if _w > 1000 else "A1" if _w > 700 else
                  "A2" if _w > 500 else "A3" if _w > 380 else "A4")
        out["sheet"] = {
            "bounds": bounds,
            "pageSize": _paper,
            "border": bounds,
            "keepouts": [],
            "titleBlock": title_block,
            "padding": padding,
            "gap": gap,
        }
    return out


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])
    doc = json.loads(src.read_text(encoding="utf-8"))
    z = build_zones_input(doc, label_reserve="--no-label-boxes" not in sys.argv)
    dst.write_text(json.dumps(z, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  %s → %s（%d zone，sheet %s）"
          % (src.name, dst.name, len(z["zones"]), "有" if z.get("sheet") else "无"))
