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


def bbox_of_pins(points, pad=2.0):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if not xs:
        return {"minX": -pad, "minY": -pad, "maxX": pad, "maxY": pad}
    return {"minX": round(min(xs) - pad, 2), "minY": round(min(ys) - pad, 2),
            "maxX": round(max(xs) + pad, 2), "maxY": round(max(ys) + pad, 2)}


def build(netlist_path, measure_path, style_plans, out_path, max_candidates=20000):
    net = json.loads(pathlib.Path(netlist_path).read_text(encoding="utf-8"))
    meas = json.loads(pathlib.Path(measure_path).read_text(encoding="utf-8"))

    # 页 → 区块（从 style-plan 拿名义放置区）
    zones_by_page: dict[str, list] = {}
    for sp in style_plans:
        spd = json.loads(pathlib.Path(sp).read_text(encoding="utf-8"))
        page = ((spd.get("titleBlock") or {}).get("page") or "").strip()
        zones_by_page[page] = spd.get("zones") or []

    by_ref = {c["ref"]: c for c in net["components"]}
    conns_by_comp: dict[str, list] = {}
    net_name = {n["id"]: n.get("name") or n["id"] for n in net["nets"]}
    for c in net["connections"]:
        conns_by_comp.setdefault(c["componentId"], []).append(c)

    problems: list[str] = []
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
            cols = max(1, int((rw - 10) // 40))
            for i, comp in enumerate(members):
                cx = rx + 8 + (i % cols) * 40
                cy = ry + 14 + (i // cols) * 34
                pid = comp["device"]["name"]
                mp = meas["parts"].get(pid)
                if mp is None:
                    problems.append("%s: 型号 %s 没有引脚几何" % (comp["ref"], pid))
                    continue
                pins = []
                pts = []
                for pname, g in (mp.get("pins") or {}).items():
                    base = pname.split("#")[0]
                    conn = next((c for c in conns_by_comp.get(comp["id"], [])
                                 if c["pinNumber"] == base), None)
                    # 全角变体（GND*）也要能匹配
                    if conn is None:
                        conn = next((c for c in conns_by_comp.get(comp["id"], [])
                                     if c["pinNumber"].rstrip("*") == base), None)
                    wx = round(cx + (g.get("connectionPoint") or [0, 0])[0], 2)
                    wy = round(cy + (g.get("connectionPoint") or [0, 0])[1], 2)
                    pins.append({
                        "number": pname, "name": base,
                        "net": net_name.get(conn["netId"], "") if conn else "",
                        "x": wx, "y": wy,
                    })
                    pts.append((wx, wy))
                measurements.append({
                    "primitiveId": comp["id"],
                    "designator": comp["ref"],
                    "x": cx, "y": cy, "rotation": 0, "mirror": False,
                    "bbox": bbox_of_pins(pts),
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
                per = {"componentId": c["id"]}
                if target:
                    per["pinNumber"] = next((cn["pinNumber"] for cn in
                                             conns_by_comp.get(c["id"], [])
                                             if cn["netId"] == target), None)
                    per["attachTo"] = {"componentId": core["id"],
                                       "pinNumber": core_net_of[target]}
                peripherals.append(per)
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
    args = ap.parse_args()

    net = json.loads(pathlib.Path(args.netlist).read_text(encoding="utf-8"))
    if not any("moduleId" in c for c in net["components"]):
        print("⚠ 网表里没有 moduleId —— 器件将按区块顺序均分，归属可能不准",
              file=sys.stderr)

    src, problems = build(args.netlist, args.measurements, args.style_plan, args.out)
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
