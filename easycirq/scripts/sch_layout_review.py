#!/usr/bin/env python3
"""上机前审图：出图（带模块框与标题）、出框数据、出质量判据。

**这是 S5 之前的强制一道门。** 一张 19 项 KPI 全绿但导线乱穿器件的图，
不该因为"指标没这一项"就被判为可落图。

一个脚本做三件事：

  1. **出图**：把排版稿画成 PNG —— 器件本体、引脚、导线、网标，
     **外加模块框与模块标题**，页头写清图纸名（按模块命名）
  2. **出框数据**：`frames-<page>.json`，可直接喂
     `easycirq sch frame apply --from`（schemaVersion:1，y-UP raw）
  3. **出质量判据**：导线穿器件、器件重叠、版面利用率
     —— `--gate` 时任一不过就退出码 1，不允许进 S5

用法：
  python scripts/sch_layout_review.py \\
      --composition reports/x/composition-M1.json \\
      --page-name "P1_车辆输入" --out-dir reports/x/review [--gate]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:                                        # pragma: no cover
    Image = None

def load_style_tokens():
    """读技能自带的 style-tokens.json；缺失时退回内置 THEME。"""
    home = pathlib.Path(os.environ.get("USERPROFILE") or pathlib.Path.home())
    for base in (home / ".agents" / "skills" / "easycirq" / "assets" / "style-reference",
                 pathlib.Path(__file__).resolve().parent.parent / "assets" / "style-reference"):
        f = base / "style-tokens.json"
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return {}


THEME = {
    "body": (245, 245, 250), "body_edge": (35, 35, 35),
    "pin": (205, 60, 60), "wire": (55, 105, 195), "gnd": (0, 140, 120),
    "flag": (125, 70, 165), "frame": (170, 0, 170), "title": (110, 0, 110),
    "sheet": (205, 205, 205),
}
FRAME_PAD = 18.0          # 模块框相对器件包围盒的外扩（raw）
PAGE_MARGIN_RAW = 19.7    # 5 mm 页边距（style-tokens.layout.page_margin_mm）
ZONE_AREA_MIN = 0.25      # style-tokens.layout.zone_area_ratio[0]
ZONE_AREA_MAX = 0.80      # style-tokens.layout.zone_area_ratio[1]
TITLE_SIZE = 20           # 0.2 inch 标题 → fontSize 20（frame apply 的约定）
MIN_UTILIZATION = 0.05    # 版面占用低于此值只**提醒**，不拦（不是缺陷）
MAX_CROSSINGS = 0         # 导线穿**别人**器件本体的允许处数（硬拦）

# **判据要和 Go 侧一致。** `schguard.SegmentEntersBody` 把框缩小 epsilon
# 再判相交，所以"导线沿器件边缘走"不算穿越 —— 而同一排器件的母线**必然**
# 沿引脚所在的那条边走过去。用未缩小的框去求交会全是误报
# （实测 16/16 全是贴边、真穿入 0）。
BODY_EPS = 0.5


# ── 几何工具 ──────────────────────────────────────────────────────────
def seg_hits_box(p1, p2, box):
    x1, y1 = p1
    x2, y2 = p2
    minx, miny, maxx, maxy = box
    t0, t1 = 0.0, 1.0
    dx, dy = x2 - x1, y2 - y1
    for p, q in ((-dx, x1 - minx), (dx, maxx - x1), (-dy, y1 - miny), (dy, maxy - y1)):
        if p == 0:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


def inside(pt, box, tol=1.0):
    return (box[0] - tol <= pt[0] <= box[2] + tol and
            box[1] - tol <= pt[1] <= box[3] + tol)


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def expand(box, pad):
    return (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)


# ── 抽取几何 ──────────────────────────────────────────────────────────
def extract(doc):
    parts, wires, flags, modules = {}, [], [], []
    for mod in doc.get("modules") or []:
        refs = []
        for pl in mod.get("placements") or []:
            b = pl["bbox"]
            parts[pl["designator"]] = (b["minX"], b["minY"], b["maxX"], b["maxY"])
            refs.append(pl["designator"])
        for w in mod.get("wires") or []:
            wires.append(([tuple(pt) for pt in (w.get("points") or [])],
                          w.get("net") or ""))
        for fl in mod.get("flags") or []:
            x, y = fl.get("pinX"), fl.get("pinY")
            if x is not None and y is not None:
                flags.append((x, y, fl.get("net") or "", fl.get("kind") or ""))
        modules.append({"id": mod.get("id"), "title": mod.get("title") or "",
                        "refs": refs})
    return parts, wires, flags, modules


# ── 质量判据 ──────────────────────────────────────────────────────────
def quality(parts, wires, sheet):
    minx, miny, maxx, maxy = union(list(parts.values())) if parts else (0, 0, 1, 1)
    avail_w = max(1.0, sheet["maxX"] - sheet["minX"])
    avail_h = max(1.0, sheet["maxY"] - sheet["minY"])
    util = ((maxx - minx) * (maxy - miny)) / (avail_w * avail_h)

    crossings = []
    for pts, net in wires:
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            for ref, box in parts.items():
                if inside(a, box) or inside(b, box):
                    continue
                # 缩框后再判：贴边走不算穿越（与 schguard.SegmentEntersBody 对齐）
                shrunk = (box[0] + BODY_EPS, box[1] + BODY_EPS,
                          box[2] - BODY_EPS, box[3] - BODY_EPS)
                if shrunk[0] >= shrunk[2] or shrunk[1] >= shrunk[3]:
                    continue
                if seg_hits_box(a, b, shrunk):
                    crossings.append({"part": ref, "net": net, "from": list(a),
                                      "to": list(b)})
                    break

    overlaps = []
    refs = list(parts)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = parts[refs[i]], parts[refs[j]]
            if (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]):
                overlaps.append([refs[i], refs[j]])

    problems = []
    if crossings:
        problems.append("导线穿过别的器件本体 %d 处（允许 %d）"
                        % (len(crossings), MAX_CROSSINGS))
    if overlaps:
        problems.append("器件本体互相重叠 %d 对" % len(overlaps))
    notes = []
    if util < MIN_UTILIZATION:
        # **提醒，不拦。** 排得偏挤不是缺陷，纸型可以后面再调；
        # 拦住交付的只该是"导线穿本体"和"器件重叠"这类真缺陷。
        notes.append("版面只占用 %.1f%%（低于 %.0f%%）—— 建议换小一号纸或拉开间距"
                     % (util * 100, MIN_UTILIZATION * 100))
    return {
        "crossings": crossings, "overlaps": overlaps,
        "utilization": round(util, 4),
        "partBBox": {"minX": minx, "minY": miny, "maxX": maxx, "maxY": maxy},
        "problems": problems,
        "notes": notes,
        "verdict": "pass" if not problems else "fail",
    }


# ── 框数据（给 sch frame apply）──────────────────────────────────────
TB_SCALE = 1.6        # 图签尺寸换算用的名义比例（只影响纸内的相对大小）
TB_MAX_W = 520        # 图签最大宽度（像素，与绘制端一致）


def title_block_page(sheet):
    """图签的**页面坐标**矩形。只依赖页面，导出端与绘制端共用，避免两边不一致。"""
    if not sheet:
        return (0.0, 0.0, 0.0, 0.0)
    sx0, sy0, sx1, sy1 = (sheet["minX"], sheet["minY"], sheet["maxX"], sheet["maxY"])
    tbw = min((sx1 - sx0) * 0.42, TB_MAX_W / TB_SCALE)
    tbh = 86.0 / TB_SCALE
    inset = 6.0 / TB_SCALE
    ruler = 22.0 / TB_SCALE
    return (sx1 - tbw - inset, sy0 + ruler, sx1 - inset, sy0 + ruler + tbh)


def zone_rect(doc, content, tb_page, scale):
    """分区框：铺满可用区（受 tokens 80% 上限），并**避开图签**。

    `frames_doc` 与 `render` 必须共用这一个算法 —— 算两遍就会出现
    "画出来的框"和"导出的框"不一致（#91 踩过）。
    """
    r = content
    sheet = doc.get("sheet") or {}
    if not sheet:
        return r
    pg = (sheet["minX"], sheet["minY"], sheet["maxX"], sheet["maxY"])
    pa = max(1e-9, (pg[2] - pg[0]) * (pg[3] - pg[1]))

    def ratio(b):
        return max(0.0, (b[2] - b[0]) * (b[3] - b[1])) / pa

    if ratio(content) >= ZONE_AREA_MIN:
        return r
    r = expand(pg, -PAGE_MARGIN_RAW)
    # 框会压住图签 → 把下沿抬到图签上方（tokens 把框压图签算违规）
    if (r[0] < tb_page[2] and tb_page[0] < r[2]
            and r[1] < tb_page[3] and tb_page[1] < r[3]):
        r = (r[0], max(r[1], tb_page[3] + 6.0 / scale), r[2], r[3])
    t = 0
    while t < 40:
        if ratio(r) <= ZONE_AREA_MAX:
            break
        n = expand(r, -6.0)
        if (n[0] > content[0] or n[1] > content[1]
                or n[2] < content[2] or n[3] < content[3]):
            break
        r = n
        t += 1
    return r


def frames_doc(doc, modules, parts, page_name, color="#AA00AA"):
    frames = []
    for m in modules:
        boxes = [parts[r] for r in m["refs"] if r in parts]
        if not boxes:
            continue
        content = expand(union(boxes), FRAME_PAD)
        r = zone_rect(doc, content, title_block_page(doc.get("sheet")),
                      TB_SCALE)
        frames.append({
            "id": m["id"],
            "title": page_name and ("%s · %s" % (page_name, m["title"])) or m["title"],
            "rect": {"minX": r[0], "minY": r[1], "maxX": r[2], "maxY": r[3]},
            # titleX/titleY 是 LEFT_TOP 锚点：放在框左上内侧
            "titleX": r[0] + 4,
            "titleY": r[3] - 4,
            "fontSize": TITLE_SIZE,
            "color": color,
            "lineType": 1,
        })
    return {"schemaVersion": 1,
            "documentId": (doc.get("connectivity") or {}).get("documentId") or "",
            "frames": frames}


# ── 出图 ──────────────────────────────────────────────────────────────
def extract_pins(doc):
    """ref → [{"number","name","x","y","rotation","net"}]（只读，不改数据）。"""
    out = {}
    for mod in doc.get("modules") or []:
        for pl in mod.get("placements") or []:
            out[pl.get("designator")] = [
                {"number": str(q.get("number") or ""),
                 "name": str(q.get("name") or ""),
                 "x": q.get("x"), "y": q.get("y"),
                 "rotation": q.get("rotation") or 0,
                 "net": q.get("net") or ""}
                for q in (pl.get("pins") or []) if q.get("x") is not None
            ]
    return out


BOX_PREFIXES = ("U", "X", "IC", "J", "F", "K", "SW", "Y")


def _net_text_color(net):
    """按 tokens 给网标文字取色：地蓝 / 电源红 / 信号黑。"""
    n = (net or "").strip()
    u = n.upper()
    if u in ("GND", "AGND", "DGND", "PGND") or "GND" in u:
        return (0, 0, 204)          # #0000CC
    if n.startswith("+"):
        return (204, 0, 0)          # #CC0000
    return (0, 0, 0)                # #000000


def draw_symbol(d, px, ref, box, pins, f_tiny, f_small, body_edge, body_fill):
    """按位号前缀画符号。坐标仍走 px()，所以和器件/导线严格同一坐标系。"""
    x1, y1, x2, y2 = box
    prefix = (ref or "")[:1].upper()
    try:
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        w, h = abs(x2 - x1), abs(y2 - y1)
    except TypeError:
        return

    # 引脚引线：从引脚端点连到本体边（这条线让"引脚"看得见）
    for q in pins:
        qx, qy = q["x"], q["y"]
        tx = min(max(qx, x1), x2)
        ty = min(max(qy, y1), y2)
        d.line([px(qx, qy), px(tx, ty)], fill=body_edge, width=1)

    if prefix == "C" and w and h:
        # 电容：两块极板（垂直于长轴）
        if w >= h:      # 极板竖直
            gap = min(w * 0.15, 6.0)
            d.line([px(cx - gap, y1), px(cx - gap, y2)], fill=body_edge, width=2)
            d.line([px(cx + gap, y1), px(cx + gap, y2)], fill=body_edge, width=2)
        else:
            gap = min(h * 0.15, 6.0)
            d.line([px(x1, cy - gap), px(x2, cy - gap)], fill=body_edge, width=2)
            d.line([px(x1, cy + gap), px(x2, cy + gap)], fill=body_edge, width=2)
    elif prefix == "D" and w and h:
        # 二极管：三角 + 横杠
        if w >= h:
            d.polygon([px(x1, cy + h / 2), px(x2, cy), px(x1, cy - h / 2)],
                      outline=body_edge, fill=body_fill)
            d.line([px(x2, y1), px(x2, y2)], fill=body_edge, width=2)
        else:
            d.polygon([px(cx + w / 2, y1), px(cx, y2), px(cx - w / 2, y1)],
                      outline=body_edge, fill=body_fill)
            d.line([px(x1, y2), px(x2, y2)], fill=body_edge, width=2)
    elif prefix == "L" and w and h:
        # 电感：方框 + 中缝
        d.rectangle([px(x1, y2), px(x2, y1)], outline=body_edge, width=2,
                    fill=body_fill)
        if w >= h:
            d.line([px(x1, cy), px(x2, cy)], fill=body_edge, width=1)
        else:
            d.line([px(cx, y1), px(cx, y2)], fill=body_edge, width=1)
    else:
        d.rectangle([px(x1, y2), px(x2, y1)], outline=body_edge, width=2,
                    fill=body_fill)

    # 方框类器件：引脚名写框内、引脚号写框外 —— 但要先看**密度**
    if prefix in BOX_PREFIXES:
        # **按最近边归类**：引脚端点在本体外（引线长度约 10 raw），
        # 所以不能用"贴着边"的判据，否则一个都匹配不上。
        sides = {"L": [], "R": [], "B": [], "T": []}
        for q in pins:
            qx, qy = q["x"], q["y"]
            dist = {"L": abs(qx - x1), "R": abs(qx - x2),
                    "B": abs(qy - y1), "T": abs(qy - y2)}
            sides[min(dist, key=dist.get)].append(q)

        def spacing(group, span):
            return span / max(1, len(group))

        room = {"L": spacing(sides["L"], h), "R": spacing(sides["R"], h),
                "B": spacing(sides["B"], w), "T": spacing(sides["T"], w)}
        drawn_boxes = []          # 已画标签的像素框，用于去重

        def clashes(box):
            for b in drawn_boxes:
                if (box[0] < b[2] and b[0] < box[2]
                        and box[1] < b[3] and b[1] < box[3]):
                    return True
            return False

        for side, group in sides.items():
            # 间距太窄就别写名字（宁缺勿叠），引脚号总是写
            show_name = room[side] >= 9.0
            for q in group:
                qx, qy = q["x"], q["y"]
                tx = min(max(qx, x1), x2)
                ty = min(max(qy, y1), y2)
                # 引脚名/号**对齐成列**：名字贴固定内缩列，号贴固定外偏列，
                # 不随引脚 jitter（否则一列字看起来是歪的）
                inset = 3.0
                ix = x1 + inset if side == "L" else (x2 - inset if side == "R" else tx)
                iy = y1 + inset if side == "B" else (y2 - inset if side == "T" else ty)
                gx, gy = px(ix, iy)
                if show_name and q["name"]:
                    tw = d.textlength(q["name"], font=f_tiny)
                    nx = gx if side == "L" else gx - tw
                    # 去重：夹到同一条边的引脚会撞在一起（实测 U3 左侧四名叠成一团）
                    box = (nx, gy - 6, nx + tw, gy + 4)
                    if not clashes(box):
                        d.text((nx, gy - 6), q["name"], fill=(70, 70, 80),
                               font=f_tiny)
                        drawn_boxes.append(box)
                # **别画两遍**：库里 number 常与 name 相同（如 LX/LX），
                # 框外再写一遍同一字符串只是噪声。
                if q["number"] and str(q["number"]) != str(q["name"] or ""):
                    ox, oy = px(qx, qy)
                    d.text((ox + 2, oy - 12), q["number"], fill=(150, 60, 60),
                           font=f_tiny)


def render(doc, parts, wires, flags, modules, page_name, out_path, q):
    if Image is None:
        return None
    sheet = doc.get("sheet") or {"minX": 0, "minY": 0, "maxX": 297, "maxY": 210}
    minx, maxx = sheet["minX"], sheet["maxX"]
    miny, maxy = sheet["minY"], sheet["maxY"]
    scale = min(2400.0 / max(1.0, maxx - minx), 1600.0 / max(1.0, maxy - miny))
    scale = max(0.8, min(scale, 2.2))
    pad = 34
    w = int((maxx - minx) * scale) + 2 * pad
    h = int((maxy - miny) * scale) + 2 * pad + 26

    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    pins_of = extract_pins(doc)

    tokens = load_style_tokens()
    palette = ((tokens.get("palette") or {}).get("zone_border")
               or ["#00B3B3", "#C800C8", "#0066CC", "#009944", "#E07800"])
    net_colors = (tokens.get("palette") or {}).get("text") or {}
    power_col = net_colors.get("net_power", "#CC0000")
    ground_col = net_colors.get("net_ground", "#0000CC")
    signal_col = net_colors.get("net_signal", "#000000")
    typo = tokens.get("typography") or {}

    def _rgb(hex_str, fallback):
        try:
            v = hex_str.lstrip("#")
            return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
        except (ValueError, IndexError):
            return fallback

    def net_color(net):
        n = (net or "").upper()
        if n in ("GND", "AGND", "DGND", "PGND") or "GND" in n:
            return _rgb(ground_col, (0, 0, 204))
        if n.startswith("+") or n in ("VBAT_RAW", "VBAT", "VSYS", "VIN", "VCC"):
            return _rgb(power_col, (204, 0, 0))
        return _rgb(signal_col, (0, 0, 0))

    def font(size):
        for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\arial.ttf"):
            if pathlib.Path(p).is_file():
                try:
                    return ImageFont.truetype(p, size)
                except OSError:
                    continue
        return ImageFont.load_default()

    f_small, f_mid, f_title = font(11), font(14), font(17)

    def px(x, y):
        # EasyEDA 原理图是 y-UP，图片是 y-DOWN → 翻转
        return (pad + (x - minx) * scale, pad + 26 + (maxy - y) * scale)

    # ── 网格底纹：每 10 raw 一条，浅到不影响读图 ────────────────────
    grid_raw = float(((tokens.get("sheet") or {}).get("grid_mil") or 10))
    if grid_raw <= 0:
        grid_raw = 10.0
    grid_col = (238, 240, 243)
    gx = minx
    while gx <= maxx + 1e-6:
        d.line([px(gx, miny), px(gx, maxy)], fill=grid_col, width=1)
        gx += grid_raw
    gy = miny
    while gy <= maxy + 1e-6:
        d.line([px(minx, gy), px(maxx, gy)], fill=grid_col, width=1)
        gy += grid_raw

    # ── 图纸边框 + 行列标尺（A/B/C… 与 1/2/3…）──────────────────────
    d.rectangle([px(minx, maxy), px(maxx, miny)], outline=(150, 150, 155), width=2)
    sheet_w = maxx - minx
    sheet_h = maxy - miny
    cells_x = max(1, int(sheet_w // 50))
    cells_y = max(1, int(sheet_h // 50))
    # 图签水平范围（与下方图签公式保持一致，供标尺避让）
    tb_left = w - int(min(w * 0.42, 520)) - pad
    tb_right = w - pad
    for i in range(cells_x):
        x0 = minx + sheet_w * i / cells_x
        x1 = minx + sheet_w * (i + 1) / cells_x
        d.line([px(x0, miny), px(x0, maxy)], fill=(190, 190, 195), width=1)
        cx0 = px((x0 + x1) / 2, maxy)[0]
        d.text((cx0 - 3, px(x0, maxy)[1] + 3), str(i + 1), fill=(120, 120, 128),
               font=f_small)
        # 图签会盖住右下角一段底部标尺 —— 落在它范围内的数字直接不画，
        # 免得和表头文字叠在一起
        if not (tb_left <= cx0 <= tb_right):
            d.text((cx0 - 3, px(x0, miny)[1] - 16), str(i + 1),
                   fill=(120, 120, 128), font=f_small)
    for j in range(cells_y):
        y0 = miny + sheet_h * j / cells_y
        y1 = miny + sheet_h * (j + 1) / cells_y
        d.line([px(minx, y0), px(maxx, y0)], fill=(190, 190, 195), width=1)
        cy0 = px(minx, (y0 + y1) / 2)[1]
        letter = chr(ord("A") + j % 26)
        d.text((px(minx, y0)[0] + 4, cy0 - 6), letter, fill=(120, 120, 128),
               font=f_small)
        # 右侧行标若落在图签纵向范围内就不画，免得压在表头上
        tb_top = h - 86 - pad - 22
        if cy0 < tb_top - 4:
            d.text((px(maxx, y0)[0] - 14, cy0 - 6), letter, fill=(120, 120, 128),
                   font=f_small)

    # 图签的**页面坐标**矩形：右下角，让开底部标尺带。
    # 先算好，供分区框避让（框压住图签正是 tokens 要拦的情况）。
    # 图签矩形**只由页面决定**（与导出端共用同一函数），
    # 用像素/scale 反推会让两边算出不同的框。
    tb_page = title_block_page({"minX": minx, "minY": miny,
                                "maxX": maxx, "maxY": maxy})
    _tb_w_px = int((tb_page[2] - tb_page[0]) * scale)
    _tb_h_px = int((tb_page[3] - tb_page[1]) * scale)

    # 模块框 + **色块标题**（基准图的视觉语言：大字号区名放在框角）
    zone_font = font(max(13, min(18, int(typo.get("zone_title", {}).get("max", 16)))))
    for bi, m in enumerate(modules):
        boxes = [parts[r] for r in m["refs"] if r in parts]
        if not boxes:
            continue
        content = expand(union(boxes), FRAME_PAD)
        # 分区框取**可用区**（页面减页边距），受 tokens 的 80% 上限约束。
        # 只按器件包围盒外扩时，小电路的分区只占页面 5.5%，
        # 违反 style-tokens.layout.zone_area_ratio（要求 25%~80%）。
        r = content
        _sheet = doc.get("sheet") or {}
        if _sheet:
            _pg = (_sheet["minX"], _sheet["minY"], _sheet["maxX"], _sheet["maxY"])
            _pa = max(1e-9, (_pg[2] - _pg[0]) * (_pg[3] - _pg[1]))
            if (max(0.0, (content[2] - content[0]) * (content[3] - content[1]))
                    / _pa) < ZONE_AREA_MIN:
                r = expand(_pg, -PAGE_MARGIN_RAW)
                # 框会压住图签 → 把下沿抬到图签上方
                if (r[0] < tb_page[2] and tb_page[0] < r[2]
                        and r[1] < tb_page[3] and tb_page[1] < r[3]):
                    r = (r[0], max(r[1], tb_page[3] + 6.0 / scale),
                         r[2], r[3])
                _t = 0
                while _t < 40:
                    _a = max(0.0, (r[2] - r[0]) * (r[3] - r[1])) / _pa
                    if _a <= ZONE_AREA_MAX:
                        break
                    _n = expand(r, -6.0)
                    if (_n[0] > content[0] or _n[1] > content[1]
                            or _n[2] < content[2] or _n[3] < content[3]):
                        break
                    r = _n
                    _t += 1
        zc = _rgb(palette[bi % len(palette)], (0, 179, 179))
        d.rectangle([px(r[0], r[3]), px(r[2], r[1])], outline=zc, width=2)
        label = m["title"] or m.get("id") or ""
        if not label:
            continue
        ax, ay = px(r[0], r[3])
        tb = d.textbbox((0, 0), label, font=zone_font)
        pad = 4
        chip_w, chip_h = tb[2] - tb[0] + 2 * pad, tb[3] - tb[1] + 2 * pad
        # **画在框外上方**：画在框内会压住器件（实测 C15 被盖住）
        cy0 = ay - chip_h - 2
        if cy0 < 26:                      # 顶到页头就翻到框内底线之上
            cy0 = ay + 2
        d.rectangle([ax, cy0, ax + chip_w, cy0 + chip_h], fill=zc)
        d.text((ax + pad, cy0 + pad - 1), label, fill="white", font=zone_font)

    # 导线
    for pts, net in wires:
        if len(pts) < 2:
            continue
        d.line([px(*p) for p in pts], fill=net_color(net), width=1)

    # 结点圆点：只画**同网**的连接点（≥3 个线段端点落在同一点）。
    # 跨网交叉不给点 —— 那会让人以为是两个网络连在一起（SVG 渲染器同一规则）。
    ends = {}
    for pts, net in wires:
        if len(pts) < 2:
            continue
        # 变量名不能用 q —— render() 的参数 q 是质量字典，会被覆盖（踩过）
        for jp in (pts[0], pts[-1]):
            key = (net, round(jp[0], 3), round(jp[1], 3))
            ends[key] = ends.get(key, 0) + 1
        for jp in pts[1:-1]:
            key = (net, round(jp[0], 3), round(jp[1], 3))
            ends[key] = ends.get(key, 0) + 1
    for (net, jx, jy), count in ends.items():
        if count >= 3:
            cx, cy = px(jx, jy)
            d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=net_color(net))

    # 器件本体 + 位号
    f_tiny = font(8)
    for ref, box in parts.items():
        draw_symbol(d, px, ref, box, pins_of.get(ref) or [], f_tiny, f_small,
                    THEME["body_edge"], THEME["body"])
        # 位号画在本体**上方外侧**（基准图的做法），不压本体、不压引脚
        x1, y1, x2, y2 = box
        tx, ty = px(x1, y2)
        d.text((tx, ty - 13), ref, fill=(15, 15, 15), font=f_small)

    # 引脚
    for pts, _net in []:
        pass
    # 网标
    for (x, y, net, kind) in flags:
        cxp, cyp = px(x, y)
        kind_l = (kind or "").lower()
        if "ground" in kind_l or net.upper() in ("GND", "AGND", "DGND"):
            # 地：三横递减（标准画法）
            for i, half in enumerate((7, 4.5, 2)):
                yy = cyp + i * 4
                d.line([(cxp - half, yy), (cxp + half, yy)],
                       fill=net_color(net), width=2)
        elif "power" in kind_l or net.startswith("+"):
            # 电源：横杠 + 引线
            d.line([(cxp, cyp), (cxp, cyp - 8)], fill=net_color(net), width=1)
            d.line([(cxp - 6, cyp - 8), (cxp + 6, cyp - 8)],
                   fill=net_color(net), width=2)
        else:
            d.polygon([(cxp, cyp - 5), (cxp + 6, cyp), (cxp, cyp + 5),
                       (cxp - 6, cyp)], outline=THEME["flag"])
        # 网名**不截断**：+3V3 被切成 +3V 会误导。按可用宽度缩小字号。
        net_font = f_small
        if d.textlength(net, font=f_small) > 90:
            net_font = font(9)
        # 标签朝**背离器件**的一侧：旗标落在引脚上，朝右往往就是本体内部，
        # 会把引脚名压住（实测 GND 压 EN、+5V 压 IN）。
        tw = d.textlength(net, font=net_font)
        near = None
        for _ref, b in parts.items():
            if (b[0] - 20 <= x <= b[2] + 20
                    and b[1] - 20 <= y <= b[3] + 20):
                near = b
                break
        to_left = bool(near) and x <= (near[0] + near[2]) / 2.0
        # 文字颜色跟**网络类别**（tokens：地蓝 / 电源红 / 信号黑）。
        # 原来用 THEME["flag"] 紫色，与旗标符号的 net_color() 是两套，语义丢了。
        label_fill = _net_text_color(net)
        if to_left:
            d.text((cxp - 8 - tw, cyp - 6), net, fill=label_fill, font=net_font)
        else:
            d.text((cxp + 8, cyp - 6), net, fill=label_fill, font=net_font)

    # 页头：图纸名 + 质量结论
    head = "%s　·　%d 件 / %d 导线 / %d 网标　·　占用 %.0f%%　·　穿器件 %d　·　%s" % (
        page_name or "（未命名）", len(parts), len(wires), len(flags),
        q["utilization"] * 100, len(q["crossings"]),
        "可审查" if q["verdict"] == "pass" else "**有问题**")
    d.text((pad, 4), head, fill=(0, 0, 0), font=f_title)

    # ── 图签（右下角）────────────────────────────────────────────
    # 基准图的图签含：图名 / 版本 / 页 / 日期 / 作者。
    # 这里只写**已知**信息；不知道的留空，不编造。
    # 用**页面坐标**落图（原来按图像右下角定位，图纸有内边距时图签会跑到纸外）
    tb_w, tb_h = _tb_w_px, _tb_h_px
    # 底部有标尺带，图签要让开它（实测压住过 8/9/10/11 这些数字）
    ruler_band = 22
    x0, y0 = px(tb_page[0], tb_page[3])
    x0, y0 = int(x0), int(y0)
    d.rectangle([x0, y0, x0 + tb_w, y0 + tb_h], outline=(40, 40, 40), width=2)
    rows = [
        ("图名", page_name or "（未命名）"),
        ("版本", str(doc.get("version") or "v1.0")),
        ("页", "%d / %d" % (int(doc.get("pageIndex") or 1),
                           int(doc.get("pageCount") or 1))),
        ("日期", str(doc.get("date") or "")),
        ("绘制", str(doc.get("author") or "")),
    ]
    rh = tb_h / len(rows)
    key_w = 54
    val_room = tb_w - key_w - 10

    def fit(text, fnt):
        """按可用宽度截断，超长用省略号 —— 不许画出框外。"""
        t = str(text or "")
        if d.textlength(t, font=fnt) <= val_room:
            return t
        while t and d.textlength(t + "…", font=fnt) > val_room:
            t = t[:-1]
        return (t + "…") if t else ""

    for i, (k, v) in enumerate(rows):
        yy = y0 + i * rh
        d.line([x0, yy, x0 + tb_w, yy], fill=(120, 120, 120), width=1)
        d.text((x0 + 6, yy + rh / 2 - 7), k, fill=(90, 90, 90), font=f_small)
        d.text((x0 + key_w, yy + rh / 2 - 7), fit(v, f_small),
               fill=(20, 20, 20), font=f_small)

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="上机前审图：出图 + 出框 + 质量门")
    ap.add_argument("--composition", action="append", required=True)
    ap.add_argument("--page-name", action="append", default=None,
                    help="图纸名（按模块命名，如 P1_车辆输入）；多块时逐个对应")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--gate", action="store_true", help="质量不过就退出 1")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = args.page_name or []
    results = []

    for i, cp in enumerate(args.composition):
        doc = json.loads(pathlib.Path(cp).read_text(encoding="utf-8"))
        sheet = doc.get("sheet") or {"minX": 0, "minY": 0, "maxX": 297, "maxY": 210}
        parts, wires, flags, modules = extract(doc)
        stem = pathlib.Path(cp).stem
        page_name = names[i] if i < len(names) else (
            (modules[0].get("id") if modules else stem))

        q = quality(parts, wires, sheet)
        png = render(doc, parts, wires, flags, modules, page_name,
                     out / ("%s.png" % page_name.replace("/", "_")), q)
        fr = frames_doc(doc, modules, parts, page_name)
        fr_path = out / ("frames-%s.json" % page_name.replace("/", "_"))
        fr_path.write_text(json.dumps(fr, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

        results.append({
            "composition": cp, "pageName": page_name, "image": png,
            "frames": str(fr_path), "quality": q,
            "parts": len(parts), "wires": len(wires), "flags": len(flags),
        })
        print("  %-22s %-18s 件 %2d 导线 %3d 占用 %4.1f%% 穿器件 %2d  %s"
              % (stem, page_name, len(parts), len(wires),
                 q["utilization"] * 100, len(q["crossings"]),
                 "✅" if q["verdict"] == "pass" else "❌"))
        for pr in q["problems"]:
            print("       ✗ %s" % pr)
        for nt in q.get("notes") or []:
            print("       · %s" % nt)

    bad = [r for r in results if r["quality"]["verdict"] != "pass"]
    if args.json:
        print(json.dumps({"results": results,
                          "verdict": "pass" if not bad else "fail"},
                         ensure_ascii=False, indent=2))
    elif bad:
        print()
        print("  **%d 块未通过审图，不允许上机。** 图已出在 %s，先看图再改。" % (len(bad), out))
    return 0 if (not bad or not args.gate) else 1


if __name__ == "__main__":
    sys.exit(main())
