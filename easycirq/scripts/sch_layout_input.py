#!/usr/bin/env python3
"""把网表 + 引脚几何 + style-plan 拼成 `sch lib-layout` 的输入。

`lib-layout` 要：`{schemaVersion, connectivity, sheet, keepouts, measurements, layoutModules}`。

  • `connectivity` —— S2→S3 生成的规范网表
  • `measurements` —— 每件的引脚世界坐标 + bbox（由库符号几何 + 名义锚点算出）
  • `layoutModules` —— 每块的 core、外设挂靠、网络策略

**名义锚点**借 self style-plan 的区块原点：S2 已经决定"这块占哪一片"，
这里只是把器件按该区块铺开，供 `lib-layout` 有起点可解。
`lib-layout` 会自己重算位置，所以这些坐标是种子，不是结论。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# 端口/网络策略：地走 local_ground，电源走 local_power，其余直连
GROUND = {"GND"}
POWER = {"+5V", "+3V3", "+3V8", "+12V_FILT", "VBAT_RAW", "+12V_RAW", "VSYS",
         "VBUS_L0", "BOOST_OUT", "IGN_12V"}


# connectivity 包的结构体字段（Go 侧 json tag），用于严格清洗。
DOC_KEYS = ("schemaVersion", "projectId", "documentId", "designatorPolicy",
            "components", "nets", "connections", "modules", "issues")
COMPONENT_KEYS = ("id", "uniqueId", "ref", "role", "device", "footprint",
                  "footprintRef", "pins", "placement", "pageId", "pageName")
PIN_KEYS = ("number", "name", "type", "noConnected", "connectionState", "x", "y")
# connectivity.Device 的 json tag 是 `deviceUuid`，不是 `uuid`
DEVICE_KEYS = ("libraryUuid", "deviceUuid", "name")
NET_KEYS = ("id", "name", "scope", "role")
CONNECTION_KEYS = ("componentId", "pinNumber", "netId", "kind")
MODULE_KEYS = ("id", "name", "coreComponents", "peripheralComponents",
               "internalNets", "ports")


def _pick(obj, keys):
    return {k: obj[k] for k in keys if isinstance(obj, dict) and k in obj}


def sanitize_connectivity(net):
    conn = _pick(net, DOC_KEYS)
    conn["components"] = []
    for c in net.get("components") or []:
        cc = _pick(c, COMPONENT_KEYS)
        cc["device"] = _pick(c.get("device") or {}, DEVICE_KEYS)
        cc["pins"] = [_pick(pp, PIN_KEYS) for pp in (c.get("pins") or [])]
        conn["components"].append(cc)
    conn["nets"] = [_pick(n, NET_KEYS) for n in (net.get("nets") or [])]
    conn["connections"] = [_pick(x, CONNECTION_KEYS)
                           for x in (net.get("connections") or [])]
    conn["modules"] = [_pick(m, MODULE_KEYS) for m in (net.get("modules") or [])]
    if net.get("issues"):
        conn["issues"] = net["issues"]
    return conn


def body_world(body, cx, cy):
    """把符号本体矩形平移到世界坐标，并**保证每个引脚都在本体外侧**。

    两个坑都踩过：
      • 只按符号 RECT 平移 + 吸附 → 引脚吸附后可能落进本体（吸附各做各的，
        最多差 2.5 raw），求解器判 `pin-exit-blocked`；
      • 只按引脚推本体 → 没有 RECT 的符号（电感/端子）本体会退化。
    所以：以 RECT 为基准，再按引脚朝向把对应的边**收进去**，直到每脚都在外侧。
    """
    if not body:
        return None
    b = {
        "minX": snap(cx + float(body["minX"])),
        "minY": snap(cy + float(body["minY"])),
        "maxX": snap(cx + float(body["maxX"])),
        "maxY": snap(cy + float(body["maxY"])),
    }
    return b


def enforce_pin_sides(b, pins):
    """按引脚朝向把本体对应的边收进去，保证每脚都在外侧。

    **两条路径都要走这一步**：有 RECT 的按符号本体起步，没有 RECT 的按引脚
    推出本体起步 —— 但收边规则相同。否则电阻这类无 RECT 的两脚件会漏掉，
    预检报 `朝上但 y=… 在本体里侧`。
    """
    if not b:
        return b
    for (x, y, out) in (pins or []):
        if out is None:
            continue
        out = float(out) % 360.0
        if out == 180.0:      # 朝左：minX 必须 ≥ x
            if b["minX"] < x:
                b["minX"] = snap(x)
        elif out == 0.0:      # 朝右：maxX 必须 ≤ x
            if b["maxX"] > x:
                b["maxX"] = snap(x)
        elif out == 270.0:    # 朝下：minY 必须 ≥ y
            if b["minY"] < y:
                b["minY"] = snap(y)
        elif out == 90.0:     # 朝上：maxY 必须 ≤ y
            if b["maxY"] > y:
                b["maxY"] = snap(y)
    MIN_EXT = 10.0
    if b["maxX"] - b["minX"] < MIN_EXT:
        b["maxX"] = snap(b["minX"] + MIN_EXT)
    if b["maxY"] - b["minY"] < MIN_EXT:
        b["maxY"] = snap(b["minY"] + MIN_EXT)
    return b


def outward_from_centre(world: dict, pname: str) -> float:
    """引脚朝外角（度）：离器件中心更远的那根主轴方向。

    `world` 是该器件所有引脚的**世界坐标**。用主轴对齐（0/90/180/270），
    因为原理图引脚本来就只在四个方向。
    """
    if not world or pname not in world:
        return 0.0
    xs = [p[0] for p in world.values()]
    ys = [p[1] for p in world.values()]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    dx = world[pname][0] - cx
    dy = world[pname][1] - cy
    if abs(dx) >= abs(dy):
        return 0.0 if dx >= 0 else 180.0
    return 90.0 if dy >= 0 else 270.0


GRID = 5.0     # lib-layout 在 bounded five-raw grid 上搜索，输入必须对齐


def snap(v, grid=GRID):
    """吸附到 5-raw 网格。

    `lib-layout` 内部用 `plGrid()` 判每个坐标，不在网格上就报
    "incomplete measured geometry" —— 而且不告诉你是哪个坐标，所以必须提前对齐。
    """
    return round(round(float(v) / grid) * grid, 2)


MIN_EXTENT = 10.0   # 器件本体最小尺寸（raw）；退化 bbox 会被 lib-layout 拒


def bbox_of_pins(points, pad=MIN_EXTENT):
    """按引脚范围算本体外框。

    **不能只按引脚**：两脚件的引脚共线，外框会在一个轴上厚度为 0，
    而 `plBoxValid` 要求宽高都为正 —— 实测一半器件因此报
    "incomplete measured geometry"。所以既给 pad，也强制最小尺寸，
    且两者都是 5 的整数倍（否则吸附回把 pad 抹成 0）。
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if not xs:
        return {"minX": -MIN_EXTENT, "minY": -MIN_EXTENT,
                "maxX": MIN_EXTENT, "maxY": MIN_EXTENT}
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    if maxx - minx < MIN_EXTENT:
        mid = (minx + maxx) / 2
        minx, maxx = mid - MIN_EXTENT / 2, mid + MIN_EXTENT / 2
    if maxy - miny < MIN_EXTENT:
        mid = (miny + maxy) / 2
        miny, maxy = mid - MIN_EXTENT / 2, mid + MIN_EXTENT / 2
    return {"minX": round(minx - pad, 2), "minY": round(miny - pad, 2),
            "maxX": round(maxx + pad, 2), "maxY": round(maxy + pad, 2)}


def build(netlist_path, measure_path, style_plans, out_path,
          max_candidates=20000, page=None):
    net = json.loads(pathlib.Path(netlist_path).read_text(encoding="utf-8"))
    meas = json.loads(pathlib.Path(measure_path).read_text(encoding="utf-8"))

    # 页 → 区块（从 style-plan 拿名义放置区）
    zones_by_page: dict[str, list] = {}
    for sp in style_plans:
        spd = json.loads(pathlib.Path(sp).read_text(encoding="utf-8"))
        # 注意：这里**不能**叫 page —— 会把 `--page` 参数覆盖掉（实测踩过：
        # 两个页都按最后一份 style-plan 的页过滤，P1 只拿到 17 件）。
        sp_page = ((spd.get("titleBlock") or {}).get("page") or "").strip()
        zones_by_page[sp_page] = spd.get("zones") or []

    # `lib-layout` 是**按页**规划的：它要 "target project/page and measured sheet"。
    # 所以 `--page` 时把网表收窄到那一页，避免把两页的器件塞进一张图纸。
    if page:
        keep = {c["id"] for c in net["components"]
                if (c.get("pageName") or "") == page}
        net = dict(net)
        net["components"] = [c for c in net["components"] if c["id"] in keep]
        net["connections"] = [x for x in net["connections"]
                              if x["componentId"] in keep]
        kept_nets = {x["netId"] for x in net["connections"]}
        net["nets"] = [n for n in net["nets"] if n["id"] in kept_nets]
        # 网表自带 `modules[].coreComponents` 引用的是**全工程**组件 id，
        # 过滤后会指向不存在的件（lib-layout 报 unknown/duplicate reference）。
        # 但**不能清空**：`computeLibLayout` 用 connectivity.modules 判断
        # "每个器件是否都属于某个模块"（`every component must belong to one
        # module`），清空就一个都不属于。所以下面按过滤后的成员重建。
        zones_by_page = {page: zones_by_page.get(page) or []}

    # `computeLibLayout` 要求 `connectivity.documentId` 非空 —— 这就是
    # "target project/page" 里的那个 page。projectId 是工程，documentId 是页。
    # 少一个都只会得到一句合并报错 "target project/page and measured sheet are required"，
    # 所以这里单独补齐并注明。
    page_ids = {c.get("pageId") for c in net["components"] if c.get("pageId")}
    if len(page_ids) == 1:
        net["documentId"] = next(iter(page_ids))
    elif page_ids:
        problems_by_page.append(
            "多页混在一份输入里（%r）—— lib-layout 是按页规划的，请用 --page 收窄"
            % sorted(page_ids))

    by_ref = {c["ref"]: c for c in net["components"]}
    conns_by_comp: dict[str, list] = {}
    net_name = {n["id"]: n.get("name") or n["id"] for n in net["nets"]}
    for c in net["connections"]:
        conns_by_comp.setdefault(c["componentId"], []).append(c)

    problems: list[str] = []
    problems_by_page: list[str] = []
    measurements = []
    # 每页每个区块内按行列铺开
    for page, zones in zones_by_page.items():
        comps = [c for c in net["components"] if (c.get("pageName") or "") == page]
        # 区块按网表自带的 moduleId 分组。
        #
        # 早先这里"按器件顺序均分"是错的：顺序与区块没有语义关系，
        # 猜错会让整条链对错块。网表现在带 moduleId，直接归属。
        missing_mod = [c["ref"] for c in comps if not c.get("moduleId")]
        if missing_mod:
            problems.append(
                "网表里这些器件没有 moduleId（无法归块）：%r" % missing_mod[:6])
        by_zone: dict[str, list] = {}
        for z in zones:
            mid = z.get("module")
            by_zone[mid] = [c for c in comps if c.get("moduleId") == mid]

        for z in zones:
            mid = z.get("module")
            members = by_zone.get(mid) or []
            rx, ry, rw, rh = z.get("rect_mm")
            if not members:
                continue
            # 排布必须**装进区块**：板2 的 Z1 是 140×120 却要塞 24 件，
            # 原来固定 40×35 的步长会一路排到 y=265（图纸只有 210 高）。
            # 所以按件数反算行列与步长。
            step_x, step_y = 40.0, 35.0
            cols = max(1, min(len(members), int((rw - 20) // step_x)))
            rows = max(1, (len(members) + cols - 1) // cols)
            if rows > 1:
                step_y = min(step_y, max(15.0, (rh - 25) / (rows - 1)))
            if cols > 1:
                step_x = min(step_x, max(20.0, (rw - 20) / (cols - 1)))
            for i, comp in enumerate(members):
                cx = snap(rx + 10 + (i % cols) * step_x)
                cy = snap(ry + 15 + (i // cols) * step_y)
                pid = comp["device"]["name"]
                mp = meas["parts"].get(pid)
                if mp is None:
                    problems.append("%s: 型号 %s 没有引脚几何" % (comp["ref"], pid))
                    continue
                pins = []
                pts = []
                body_pts = []
                # 先算所有脚的**世界坐标**，才能用它们的中心判"朝外"
                world = {}
                for pname, g in (mp.get("pins") or {}).items():
                    world[pname] = (
                        snap(cx + (g.get("connectionPoint") or [0, 0])[0]),
                        snap(cy + (g.get("connectionPoint") or [0, 0])[1]),
                    )

                for pname, g in (mp.get("pins") or {}).items():
                    base = pname.split("#")[0]
                    cn = next((c for c in conns_by_comp.get(comp["id"], [])
                                 if c["pinNumber"] == base), None)
                    # 全角变体（GND*）也要能匹配
                    if cn is None:
                        cn = next((c for c in conns_by_comp.get(comp["id"], [])
                                     if c["pinNumber"].rstrip("*") == base), None)
                    wx, wy = world[pname]
                    # 朝外方向**从几何推导**，不靠 `.elibu` 的 rotation。
                    #
                    # 实测：`.elibu` 的 rotation 约定并不统一 —— 侧边脚是"朝本体"，
                    # 而 EP（外露焊盘）却是"朝外"。按它推会一半对一半错，
                    # 求解器逐条报 `pin-exit-blocked: <ref>.<pin> minimum outward
                    # segment crosses <ref> body`。
                    #
                    # 稳的做法：引脚在器件中心的哪一侧，朝外就是那一侧的主轴方向。
                    _outs = float(g.get("outwardRotation")
                                  if g.get("outwardRotation") is not None
                                  else outward_from_centre(world, pname))
                    _ln = float(g.get("length") or 0)
                    body_pts.append((
                        wx - math.cos(math.radians(_outs)) * _ln,
                        wy - math.sin(math.radians(_outs)) * _ln,
                    ))
                    pins.append({
                        # **name 必须与 connectivity 里逐字相同**，否则
                        # lib-layout 报 "measured pin differs from canonical IR"。
                        # 所以用带编号的 pname，不用去后缀的 base。
                        "number": pname, "name": pname,
                        "net": net_name.get(cn["netId"], "") if cn else "",
                        "x": wx, "y": wy,
                        # **必须用朝外角**（rotation + 180）：文件里的 rotation
                        # 是引脚线朝本体的方向，直接交上去会让求解器判定
                        # "outward segment crosses body"，一个位置都排不下。
                        # measurements 里已按**符号本体**判好朝外角
                        "rotation": float(g.get("outwardRotation")
                                          if g.get("outwardRotation") is not None
                                          else outward_from_centre(world, pname)),
                    })
                    pts.append((wx, wy))
                measurements.append({
                    "primitiveId": comp["id"],
                    "designator": comp["ref"],
                    "x": cx, "y": cy, "rotation": 0, "mirror": False,
                    # **本体框用符号自己给的 RECT**，不自己造。
                    # 靠"引脚范围 + padding"当本体，会让引脚全落在框内，
                    # 求解器判定朝外段穿过本体；靠"朝内退 length"又会因
                    # `.elibu` rotation 约定不统一而在 EP 这类焊盘上判错。
                    # 符号里有真本体（TPS54360 是 x -40..40 / y -25..25），直接平移过来。
                    "bbox": enforce_pin_sides(
                        body_world(mp.get("body"), cx, cy)
                        or {k: snap(v) for k, v in bbox_of_pins(body_pts).items()},
                        [(world[pn][0], world[pn][1], g2.get("outwardRotation"))
                         for pn, g2 in (mp.get("pins") or {}).items()]),
                    "pins": pins,
                })

    # 逐块声明 core / peripherals / netPolicies
    layout_modules = []
    for page, zones in zones_by_page.items():
        for z in zones:
            mid = z.get("module")
            members = [c for c in net["components"] if c.get("moduleId") == mid]
            if not members:
                continue
            # core：优先 IC 类
            def is_ic(c):
                return (c["device"]["name"] or "").split(".")[0] in (
                    "ic", "buck", "buckboost", "ldo", "mcu")
            cores = [c for c in members if is_ic(c)]
            core = cores[0] if cores else members[0]
            core_net_of = {}
            for c in conns_by_comp.get(core["id"], []):
                core_net_of.setdefault(c["netId"], c["pinNumber"])
            peripherals = []
            for c in members:
                if c["id"] == core["id"]:
                    continue
                target = next((conns_by_comp.get(c["id"], []) and cn["netId"]
                               for cn in conns_by_comp.get(c["id"], [])
                               if cn["netId"] in core_net_of), None)
                # **不发明 attachTo。** 它是可选字段，而我们只能从网表
                # 推出"这个件和 core 有共同网"，推不出"它该贴在哪个脚、朝哪个方向"。
                # 实测：给 24 个外设都挂 attachTo 会让求解器在同一个脚上朝不同方向
                # 挣扎 —— 8.6 万到 17.5 万个候选后放弃，且换更大的图纸结果一模一样
                # （说明不是容量问题，是约束自相矛盾）。
                # 让求解器按 netPolicies 自己排，是更诚实的输入。
                peripherals.append({"componentId": c["id"]})
            policies = {}
            for nid, nm in net_name.items():
                if not any(c["netId"] == nid for m in members
                           for c in conns_by_comp.get(m["id"], [])):
                    continue
                if nm.upper() in GROUND:
                    policies[nid] = "local_ground"
                elif nm.upper() in POWER:
                    policies[nid] = "local_power"
                else:
                    policies[nid] = "direct"
            layout_modules.append({
                "id": mid or "?",
                "title": z.get("title") or "",
                "coreComponentId": core["id"],
                "peripherals": peripherals,
                "netPolicies": policies,
            })

    # `lib-layout` 对输入做**严格字段校验**（"unknown JSON field" 直接拒）。
    # 我们的网表带了一些 Document 之外的字段（`noConnectDeclarations`、组件上的
    # `moduleId`），那些是给 plan-status / 归块用的。
    # 所以嵌入前按 `connectivity` 的结构体**逐层白名单清洗**，
    # 而不是把整份网表塞进去赌它宽容 —— 赌输一次就多一轮试错。
    conn = sanitize_connectivity(net)

    # ── 用**符号引脚**重建 connectivity 的引脚，并按基础名接网 ──────────────
    #
    # 块库用 `GND*` 表示"其中一个地脚"，而符号量出来的是 `GND#1..#4`。
    # 两边名字与**数量**都对不上，而 lib-layout 要求：
    #   len(measurement.pins) == len(connectivity.pins) 且每个 pin 的 name 相同
    #   （见 sch_lib_solver.go 的 "incomplete measured geometry"）
    #
    # 所以以**符号**为准重建引脚，再把连接按基础名（去掉 #n 与 *）映射过去。
    # 电气上这也是对的：4 个地脚本来就都该接 GND，不是只接一个。
    need_pin_rebuild = {}
    for c in conn["components"]:
        mp = meas["parts"].get((c.get("device") or {}).get("name") or "")
        if not mp:
            continue
        need_pin_rebuild[c["id"]] = mp

    old_conn = list(conn["connections"])
    conn["connections"] = []
    for c in conn["components"]:
        mp = need_pin_rebuild.get(c["id"])
        if not mp:
            continue
        # 这个器件原来的引脚 → 网
        old_net = {}
        for x in old_conn:
            if x["componentId"] == c["id"]:
                old_net[x["pinNumber"]] = (x["netId"], x.get("kind") or "wire")
        c["pins"] = []
        for pname in sorted((mp.get("pins") or {})):
            base = pname.split("#")[0].rstrip("*")
            # 找一个基础名相同的旧连接
            hit = None
            for on, (nid, kind) in old_net.items():
                if on.rstrip("*").split("#")[0] == base:
                    hit = (nid, kind)
                    break
            pin = {"number": pname, "name": pname}
            if hit:
                conn["connections"].append({"componentId": c["id"],
                                            "pinNumber": pname,
                                            "netId": hit[0], "kind": hit[1]})
            else:
                pin["noConnected"] = True
            c["pins"].append(pin)


    # 器件身份要补进 connectivity：`lib-layout` 要求每件有 `libraryUuid`
    # 与 32 位 `deviceUuid`，否则报
    # "requires libraryUuid and a 32-character deviceUuid"。
    # 我们的网表只有型号名（part id），身份在 measurements 里（由 by-lcsc 解析）。
    ident_of: dict[str, tuple[str, str]] = {}
    for pid, mp in (meas.get("parts") or {}).items():
        lu = (mp.get("libraryUuid") or "").strip()
        du = (mp.get("deviceUuid") or "").strip()
        if lu and len(du) == 32:
            ident_of[pid] = (lu, du)
    missing_ident = []
    for c in conn["components"]:
        pid = (c.get("device") or {}).get("name") or ""
        ident = ident_of.get(pid)
        if ident:
            c["device"] = {"name": pid, "libraryUuid": ident[0],
                           "deviceUuid": ident[1]}
        else:
            missing_ident.append("%s(%s)" % (c.get("ref"), pid))

    # connectivity.modules 必须与 layoutModules 对齐 ——
    # 前者是 lib-layout 判"器件归属"的依据，后者是排布意图。
    # 只填 coreComponents + peripheralComponents（id 必须真实存在）。
    conn["modules"] = [
        {
            "id": m["id"],
            "name": m.get("title") or m["id"],
            "coreComponents": [m["coreComponentId"]],
            "peripheralComponents": [p["componentId"]
                                     for p in m.get("peripherals") or []
                                     if p.get("componentId")],
        }
        for m in layout_modules
    ]

    src = {
        "schemaVersion": 1,
        "connectivity": conn,
        "sheet": {"minX": 0, "minY": 0, "maxX": 297, "maxY": 210},
        "keepouts": [],
        "measurements": measurements,
        "layoutModules": layout_modules,
        "maxCandidates": max_candidates,
    }
    if missing_ident:
        src["_missingIdent"] = missing_ident
    # `_missingIdent` 只是给人看的诊断，**不能写进文件** ——
    # lib-layout 严格校验未知字段，写进去等于自己把自己拒掉。
    problems.extend(problems_by_page)
    diag = src.pop("_missingIdent", [])
    pathlib.Path(out_path).write_text(
        json.dumps(src, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for mid in diag:
        problems.append("缺 device 身份：%s" % mid)
    return src, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="拼 lib-layout 输入")
    ap.add_argument("--netlist", required=True)
    ap.add_argument("--measurements", required=True)
    ap.add_argument("--style-plan", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--page", help="只规划这一页（lib-layout 是按页规划的）")
    args = ap.parse_args()

    net = json.loads(pathlib.Path(args.netlist).read_text(encoding="utf-8"))
    if not any("moduleId" in c for c in net["components"]):
        print("⚠ 网表里没有 moduleId —— 器件将按区块顺序均分，归属可能不准",
              file=sys.stderr)

    src, problems = build(args.netlist, args.measurements, args.style_plan,
                          args.out, page=args.page)
    print("lib-layout 输入 → %s" % args.out)
    print("  measurements: %d 件" % len(src["measurements"]))
    print("  layoutModules: %d 块" % len(src["layoutModules"]))
    for m in src["layoutModules"]:
        print("    %-4s core=%s 外设%d 网络策略%d"
              % (m["id"], m["coreComponentId"], len(m["peripherals"]),
                 len(m["netPolicies"])))
    if src.get("_missingIdent"):
        print("  ✗ 缺 device 身份的器件 %d 个：%s"
              % (len(src["_missingIdent"]), ", ".join(src["_missingIdent"][:6])))
        src.pop("_missingIdent", None)
    for p in problems[:8]:
        print("  ✗ %s" % p)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
