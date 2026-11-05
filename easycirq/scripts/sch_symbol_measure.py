"""从 `lib symbol export-source` 的 .elibz2 里量出引脚坐标（离线度量）。

**这一步解决的是**：S3 的 `lib-layout` 要 `measurements`（每件 bbox + 引脚坐标），
而块库只有 parts / internal_nets / ports，**没有原理图几何**。所以以前只能
"先落图再量"——那正好绕过「未过 S2 不得进器件」。

现在有了这条路：**读库符号的原始导出**（只读，不落任何器件）就能离线量出
每件的引脚位置。**读库不等于进器件**，所以流程不破。

原始探针说明：

.eilibz2（export-source 产物）里有两个成员：
  • symbol2.json —— 只有元数据
  • ProLib_*.elibu —— **真正的符号文档**，行内 JSON 记录流：
        {"type":"PIN","id":"e3"}                      引脚记录
        {"x":-55,"y":-30,"length":20,"rotation":0}    紧跟的几何
        {"parentId":"e3","key":"Pin Name","value":"VIN"}  引脚的属性（名字）
    记录之间用 `|` 分隔，几何行没有 type 字段。
"""
import json
import os
import pathlib
import zipfile

ARCHIVE = pathlib.Path(os.environ.get("EASY_SYMBOL_ARCHIVE")
                        or (pathlib.Path(os.environ.get("TEMP", ".")) / "xl1509.elibz2"))


def parse_elibu(text: str):
    """把 .elibu 的记录流拆成 {id: {...}} 与引脚列表。"""
    records = []
    for raw in text.split("|"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    pins = {}
    shapes = {}
    pending = None          # 上一个 type 记录，用来接收紧随其后的几何
    for r in records:
        if "type" in r:
            pending = r
            t = r["type"]
            if t == "PIN":
                pins[r.get("id")] = {"id": r.get("id"), "name": "", "attrs": {}}
            elif t in ("RECT", "POLYLINE", "CIRCLE", "ARC", "ELLIPSE"):
                shapes[r.get("id")] = {"kind": t, "id": r.get("id")}
            continue

        # 没有 type = 某个记录的属性/几何
        if pending is None:
            continue
        t = pending.get("type")
        if "parentId" in r:
            # 属性：归属 parentId
            pid = r["parentId"]
            if t == "ATTR" and pid in pins:
                if r.get("key") == "Pin Name":
                    pins[pid]["name"] = r.get("value") or ""
                pins[pid]["attrs"][r.get("key") or ""] = r.get("value")
            continue
        # 几何：归属最近一个 type 记录
        rid = pending.get("id")
        if t == "PIN" and rid in pins:
            pins[rid].update({k: r.get(k) for k in
                              ("x", "y", "length", "rotation", "pinShape")})
        elif rid in shapes:
            shapes[rid].update(r)
    return pins, shapes, records


def connection_point(pin):
    """引脚与导线的接触点。

    **`.elibu` 里的 `x,y` 本身就是连接点**（引脚外端的自由端），
    `rotation` 指的是从该点**朝本体**画线的方向，`length` 是线长。

    所以连接点就是 `(x, y)`，不要再沿 rotation 走一段 ——
    那样会把连接点推进本体内部，导致求解器报
    `pin-exit-blocked: ... minimum outward segment crosses <part> body`。
    实测踩过：全部器件的引脚都"朝内"，求解器一个位置都排不下。
    """
    x, y = pin.get("x"), pin.get("y")
    if x is None or y is None:
        return None
    return (round(float(x), 2), round(float(y), 2))


def body_rect(shapes):
    """符号本体矩形（由 RECT 记录求并）。

    **不用引脚范围猜本体**：`.elibu` 里有真正的 RECT（如 TPS54360 是
    x -40..40 / y -25..25），用它判"引脚在本体外侧的哪一边"才准。
    实测：靠"离引脚中心最远的主轴"来判，EP（外露焊盘）会判错 ——
    它在引脚范围中间，朝外就成了"朝内"。
    """
    boxes = []
    for sh in (shapes or {}).values():
        if sh.get("kind") != "RECT":
            continue
        x1, y1 = sh.get("dotX1"), sh.get("dotY1")
        x2, y2 = sh.get("dotX2"), sh.get("dotY2")
        if None in (x1, y1, x2, y2):
            continue
        boxes.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def outward_rotation(pin, body=None):
    """世界「朝外」角（度）。

    优先按**本体矩形**判：引脚落在本体的哪一侧外侧，就朝那边。
    本体判不出来时退回 `.elibu` 的 rotation + 180（对普通引脚成立）。
    """
    x, y = pin.get("x"), pin.get("y")
    if body and x is not None and y is not None:
        minx, miny, maxx, maxy = body
        if x < minx:
            return 180.0
        if x > maxx:
            return 0.0
        if y < miny:
            return 270.0
        if y > maxy:
            return 90.0
    rot = pin.get("rotation")
    if rot is None:
        return None
    return (float(rot) + 180.0) % 360.0


def main():
    if not ARCHIVE.is_file():
        print("找不到导出文件：%s" % ARCHIVE)
        return 1
    z = zipfile.ZipFile(ARCHIVE)
    name = next(n for n in z.namelist() if n.endswith(".elibu"))
    text = z.read(name).decode("utf-8", errors="replace")
    pins, shapes, records = parse_elibu(text)

    print("  .elibu 记录 %d 条 → 引脚 %d 个，图形 %d 个" % (len(records), len(pins), len(shapes)))
    print()
    print("  %-4s %-8s %-8s %-8s %-6s %-8s %s" %
          ("id", "name", "x", "y", "rot", "len", "接触点"))
    for pid, p in sorted(pins.items(), key=lambda kv: kv[1].get("name") or ""):
        cp = connection_point(p)
        print("  %-4s %-8s %-8s %-8s %-6s %-8s %s" %
              (pid, p.get("name") or "?", p.get("x"), p.get("y"),
               p.get("rotation"), p.get("length"), cp))

    # 符号本体范围（由引脚与图形粗略推）
    xs = [p["x"] for p in pins.values() if p.get("x") is not None]
    ys = [p["y"] for p in pins.values() if p.get("y") is not None]
    if xs and ys:
        print()
        print("  引脚范围: x %.0f..%.0f  y %.0f..%.0f" % (min(xs), max(xs), min(ys), max(ys)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
