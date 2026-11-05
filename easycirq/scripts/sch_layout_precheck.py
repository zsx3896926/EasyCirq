#!/usr/bin/env python3
"""离线预检 `sch lib-layout` 的输入 —— 把求解器入口的**全部校验规则**前置成本地检查。

为什么需要它：`computeLibLayout`（237 行）一次只报**一条**规则，而每错一条都要
走一遍"构造输入 → 跑 CLI → 解析错误 → 改代码"。实测这样耗掉了 8 个回合。
规则是**静态**的，可以一次全查完，本地 0.1 秒。

覆盖的规则（逐条对应 Go 实现）：

  computeLibLayout 入口
    1. schemaVersion == 1
    2. connectivity.projectId 非空          ← "target project"
    3. connectivity.documentId 非空         ← "target page"
    4. sheet 合法矩形（minX<maxX, minY<maxY）
    5. maxCandidates 在 1..1000000

  connectivity.Document.Validate()
    6. connectivity.schemaVersion == "1.4"（精确）
    7. 位号格式；component id/ref 唯一
    8. net id 非空；net name 唯一且非空；net.scope ∈ {local, global}
    9. connection.kind ∈ 允许集合
   10. 同一引脚不能既连接又 NC
   11. 每个引脚：有网 / NC / unconnected，**恰好一个**

  逐器件
   12. device.libraryUuid 非空、deviceUuid 为 32 位、pins 非空

  逐测量
   13. designator 未知/重复
   14. bbox 合法、x/y 在 5-raw 网格、rotation 有限且是 90 的倍数
   15. len(measurement.pins) == len(component.pins)
   16. 每个测量引脚：存在、不重复、name 一致、x/y 在网格、net 与规范 IR 一致
   17. 引脚必须落在 bbox 的某一条边上（libPinSide）
   18. measurements 覆盖每个器件

  模块
   19. module id 唯一；成员存在且不重复
   20. **每个器件恰好属于一个模块**
   21. layoutModule 的 id 必须对应一个规范模块；coreComponentId 必须是该模块的 core
   22. 外设必须属于该模块且不是 core；attachTo 目标必须是同模块的另一成员
   23. 成员用到的**每条网都必须有**受支持的策略；不许有没用到的策略
   24. layoutModules 必须覆盖每个规范模块

退出码：0 = 预检通过；1 = 有问题（逐条列出，带字段路径）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

GRID = 5.0
CONN_KINDS = {"", "pin_net", "netlist", "wire", "netflag", "netport",
              "netlabel", "power", "ground", "net_port_in", "net_port_out",
              "net_port_bi"}
POLICIES = {"direct", "local_power", "local_ground", "module_port"}
REF_RE = re.compile(r"^[A-Za-z]+[0-9]+$")


class Check:
    def __init__(self):
        self.problems: list[str] = []
        self.notes: list[str] = []

    def bad(self, msg: str) -> None:
        self.problems.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def on_grid(v) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return abs(f / GRID - round(f / GRID)) < 1e-9


def box_ok(b) -> bool:
    if not isinstance(b, dict):
        return False
    try:
        return float(b["maxX"]) > float(b["minX"]) and \
               float(b["maxY"]) > float(b["minY"])
    except (KeyError, TypeError, ValueError):
        return False


def finite(v) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


def check(src: dict) -> Check:
    c = Check()

    # ── 1-5 入口 ────────────────────────────────────────────────────────
    if src.get("schemaVersion") != 1:
        c.bad("/schemaVersion 必须是 1（得到 %r）" % src.get("schemaVersion"))
    conn = src.get("connectivity") or {}
    if not (conn.get("projectId") or "").strip():
        c.bad("/connectivity/projectId 为空 —— 求解器要 'target project'")
    if not (conn.get("documentId") or "").strip():
        c.bad("/connectivity/documentId 为空 —— 求解器要 'target page'")
    if not box_ok(src.get("sheet")):
        c.bad("/sheet 不是合法矩形（需要 minX<maxX 且 minY<maxY）")
    mc = src.get("maxCandidates", 0) or 0
    if mc and not (1 <= int(mc) <= 1000000):
        c.bad("/maxCandidates 必须在 1..1000000（得到 %r）" % mc)

    # ── 6-11 connectivity.Document.Validate ─────────────────────────────
    if conn.get("schemaVersion") != "1.4":
        c.bad("/connectivity/schemaVersion 必须精确为 \"1.4\"（得到 %r）"
              % conn.get("schemaVersion"))

    comps = conn.get("components") or []
    if not comps:
        c.bad("/connectivity/components 为空")
    by_id, by_ref = {}, {}
    for i, x in enumerate(comps):
        cid, ref = x.get("id") or "", x.get("ref") or ""
        p = "/connectivity/components/%d" % i
        if not cid or not ref:
            c.bad("%s 缺 id 或 ref" % p)
            continue
        if cid in by_id:
            c.bad("%s 重复 id %r" % (p, cid))
        if ref in by_ref:
            c.bad("%s 重复位号 %r" % (p, ref))
        if not REF_RE.match(ref):
            c.bad("%s 位号 %r 不符合 字母+数字 格式" % (p, ref))
        by_id[cid], by_ref[ref] = x, x
        # 12
        dev = x.get("device") or {}
        if not (dev.get("libraryUuid") or "").strip():
            c.bad("%s(device) 缺 libraryUuid" % p)
        du = dev.get("deviceUuid") or ""
        if len(du) != 32:
            c.bad("%s(device) deviceUuid 必须是 32 位（得到 %d 位：%r）"
                  % (p, len(du), du))
        if not (x.get("pins") or []):
            c.bad("%s 没有任何引脚" % p)

    nets = conn.get("nets") or []
    net_name, seen_names = {}, set()
    for i, n in enumerate(nets):
        nid, nm = n.get("id") or "", (n.get("name") or "").strip()
        p = "/connectivity/nets/%d" % i
        if not nid:
            c.bad("%s 缺 id" % p)
            continue
        if not nm:
            c.bad("%s(%s) 网名不能为空" % (p, nid))
        elif nm in seen_names:
            c.bad("%s 网名 %r 重复" % (p, nm))
        else:
            seen_names.add(nm)
        sc = n.get("scope") or ""
        if sc and sc not in ("local", "global"):
            c.bad("%s(%s) scope 必须是 local/global（得到 %r）" % (p, nid, sc))
        net_name[nid] = nm

    pin_net: dict[tuple[str, str], str] = {}
    connected: set[tuple[str, str]] = set()
    for i, e in enumerate(conn.get("connections") or []):
        cid, pn = e.get("componentId") or "", e.get("pinNumber") or ""
        p = "/connectivity/connections/%d" % i
        if cid not in by_id:
            c.bad("%s 指向不存在的器件 %r" % (p, cid))
            continue
        k = (cid, pn)
        if k in connected:
            c.bad("%s %s.%s 被连接了两次" % (p, cid, pn))
        connected.add(k)
        pin_net[k] = e.get("netId") or ""
        kind = e.get("kind") or ""
        if kind not in CONN_KINDS:
            c.bad("%s.%s connection.kind=%r 不是允许值（%s）"
                  % (cid, pn, kind, "/".join(sorted(k for k in CONN_KINDS if k))))
        if pin_net[k] not in net_name:
            c.bad("%s.%s 指向不存在的网 %r" % (cid, pn, pin_net[k]))

    for x in comps:
        cid = x.get("id")
        for pin in (x.get("pins") or []):
            pn = pin.get("number") or ""
            if not pn:
                c.bad("%s 有引脚缺 number" % cid)
                continue
            k = (cid, pn)
            is_nc = bool(pin.get("noConnected"))
            is_unc = (pin.get("connectionState") or "") == "unconnected"
            has_net = bool(pin_net.get(k))
            if has_net and is_nc:
                c.bad("%s.%s 既连接又标了 NC" % (cid, pn))
            if sum([has_net, is_nc, is_unc]) != 1:
                c.bad("%s.%s 必须有且只有一个：网 / NC / unconnected"
                      "（现在 网=%s NC=%s unconnected=%s）"
                      % (cid, pn, has_net, is_nc, is_unc))

    # ── 13-18 测量 ──────────────────────────────────────────────────────
    measurements = src.get("measurements") or []
    seen_desig, measured = set(), {}
    for i, m in enumerate(measurements):
        desig = m.get("designator") or ""
        p = "/measurements/%d" % i
        if desig in seen_desig:
            c.bad("%s 位号 %r 重复" % (p, desig))
            continue
        seen_desig.add(desig)
        comp = by_ref.get(desig)
        if comp is None:
            c.bad("%s 位号 %r 在 connectivity 里不存在" % (p, desig))
            continue
        measured[comp["id"]] = m
        if not box_ok(m.get("bbox")):
            c.bad("%s(%s) bbox 非法（宽高必须都为正）" % (p, desig))
        if not on_grid(m.get("x")) or not on_grid(m.get("y")):
            c.bad("%s(%s) x/y 不在 5-raw 网格上（%r, %r）"
                  % (p, desig, m.get("x"), m.get("y")))
        rot = m.get("rotation")
        if not finite(rot) or abs(float(rot) % 90.0) > 1e-9:
            c.bad("%s(%s) rotation 必须是 90 的倍数（得到 %r）" % (p, desig, rot))
        if len(m.get("pins") or []) != len(comp.get("pins") or []):
            c.bad("%s(%s) 测量引脚 %d 个，connectivity 引脚 %d 个，必须相等"
                  % (p, desig, len(m.get("pins") or []),
                     len(comp.get("pins") or [])))
        cpin = {q.get("number"): q for q in (comp.get("pins") or [])}
        seen_pin = set()
        for q in (m.get("pins") or []):
            qn = q.get("number") or ""
            if qn in seen_pin:
                c.bad("%s(%s).%s 测量引脚重复" % (p, desig, qn))
                continue
            seen_pin.add(qn)
            cp = cpin.get(qn)
            if cp is None:
                c.bad("%s(%s).%s 测量有、connectivity 没有" % (p, desig, qn))
                continue
            if (cp.get("name") or "") != (q.get("name") or ""):
                c.bad("%s(%s).%s 引脚名不一致（connectivity=%r 测量=%r）"
                      % (p, desig, qn, cp.get("name"), q.get("name")))
            if not on_grid(q.get("x")) or not on_grid(q.get("y")):
                c.bad("%s(%s).%s 坐标不在 5-raw 网格（%r, %r）"
                      % (p, desig, qn, q.get("x"), q.get("y")))
            want = net_name.get(pin_net.get((comp["id"], qn), ""), "")
            if (q.get("net") or "") != want:
                c.bad("%s(%s).%s net 不一致（测量=%r 规范=%r）"
                      % (p, desig, qn, q.get("net"), want))
            # 17：**朝外那一段不能撞本体**。
            #
            # 注意 `libPinSide` 的真实行为：给了 rotation 时**只看 rotation、
            # 不看 bbox**。所以要查的不是"引脚在不在框边上"（那是我先前发明的
            # 错判据，会报出一堆假问题），而是"按这个朝向走，会不会撞进本体"。
            if box_ok(m.get("bbox")):
                b = m["bbox"]
                x, y = float(q["x"]), float(q["y"])
                out = q.get("rotation")
                if out is not None:
                    out = float(out) % 360.0
                    if out == 180.0 and x > float(b["minX"]):
                        c.bad("%s(%s).%s 朝左但 x=%g 在本体里侧（minX=%g）"
                              % (p, desig, qn, x, float(b["minX"])))
                    elif out == 0.0 and x < float(b["maxX"]):
                        c.bad("%s(%s).%s 朝右但 x=%g 在本体里侧（maxX=%g）"
                              % (p, desig, qn, x, float(b["maxX"])))
                    elif out == 90.0 and y < float(b["maxY"]):
                        c.bad("%s(%s).%s 朝上但 y=%g 在本体里侧（maxY=%g）"
                              % (p, desig, qn, y, float(b["maxY"])))
                    elif out == 270.0 and y > float(b["minY"]):
                        c.bad("%s(%s).%s 朝下但 y=%g 在本体里侧（minY=%g）"
                              % (p, desig, qn, y, float(b["minY"])))
    for cid, x in by_id.items():
        if cid not in measured:
            c.bad("器件 %s(%s) 没有测量数据" % (cid, x.get("ref")))

    # ── 19-24 模块 ──────────────────────────────────────────────────────
    modules = {}
    owners: dict[str, str] = {}
    for i, m in enumerate(conn.get("modules") or []):
        mid = m.get("id") or ""
        p = "/connectivity/modules/%d" % i
        if not mid:
            c.bad("%s 缺 id" % p)
            continue
        if mid in modules:
            c.bad("%s 模块 id %r 重复" % (p, mid))
            continue
        modules[mid] = m
        for cid in (m.get("coreComponents") or []) + \
                   (m.get("peripheralComponents") or []):
            if cid not in by_id:
                c.bad("%s 成员 %r 不存在" % (p, cid))
            elif cid in owners:
                c.bad("%s 成员 %r 同时属于 %s 与 %s"
                      % (p, cid, owners[cid], mid))
            else:
                owners[cid] = mid
    for cid in by_id:
        if cid not in owners:
            c.bad("器件 %s(%s) 不属于任何模块 —— 求解器要求每个器件恰好属于一个"
                  % (cid, by_id[cid].get("ref")))

    intents = {}
    for i, it in enumerate(src.get("layoutModules") or []):
        mid = it.get("id") or ""
        p = "/layoutModules/%d" % i
        if mid not in modules:
            c.bad("%s 模块 %r 在 connectivity.modules 里不存在" % (p, mid))
            continue
        if mid in intents:
            c.bad("%s 模块 %r 重复" % (p, mid))
            continue
        intents[mid] = it
        core = it.get("coreComponentId") or ""
        if core not in (modules[mid].get("coreComponents") or []):
            c.bad("%s coreComponentId %r 不是该模块的 core" % (p, core))
        members = set((modules[mid].get("coreComponents") or []) +
                      (modules[mid].get("peripheralComponents") or []))
        for j, per in enumerate(it.get("peripherals") or []):
            pid = (per or {}).get("componentId") or ""
            if pid not in members:
                c.bad("%s/peripherals/%d 器件 %r 不属于该模块" % (p, j, pid))
            elif pid == core:
                c.bad("%s/peripherals/%d 不能把 core 自己列成外设" % (p, j))
            att = (per or {}).get("attachTo")
            if att:
                aid = att.get("componentId") or ""
                if aid not in members or aid == pid:
                    c.bad("%s/peripherals/%d attachTo 目标必须是同模块的另一成员"
                          "（得到 %r）" % (p, j, aid))
        used = set()
        for cid in members:
            for pin in (by_id.get(cid, {}).get("pins") or []):
                nid = pin_net.get((cid, pin.get("number") or ""))
                if nid:
                    used.add(nid)
        pol = it.get("netPolicies") or {}
        for nid in used:
            if pol.get(nid) not in POLICIES:
                c.bad("%s 网络 %r(%s) 缺少受支持的策略（需要 direct/local_power/"
                      "local_ground/module_port，得到 %r）"
                      % (p, net_name.get(nid, nid), nid, pol.get(nid)))
        for nid in pol:
            if nid not in used:
                c.bad("%s 策略指向未被该模块使用的网 %r" % (p, nid))
    for mid in modules:
        if mid not in intents:
            c.bad("模块 %r 没有对应的 layoutModules 条目" % mid)

    return c


def main() -> int:
    ap = argparse.ArgumentParser(description="离线预检 sch lib-layout 输入")
    ap.add_argument("input")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = pathlib.Path(args.input)
    try:
        src = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("读不进来：%s" % exc, file=sys.stderr)
        return 2

    c = check(src)
    if args.json:
        print(json.dumps({"verdict": "pass" if not c.problems else "fail",
                          "problems": c.problems, "notes": c.notes},
                         ensure_ascii=False, indent=2))
    else:
        print("lib-layout 输入预检：%s（%d 条问题）"
              % ("pass" if not c.problems else "fail", len(c.problems)))
        for p in c.problems[:40]:
            print("  ✗ %s" % p)
        if len(c.problems) > 40:
            print("  … 还有 %d 条" % (len(c.problems) - 40))
        for n in c.notes:
            print("  · %s" % n)
    return 0 if not c.problems else 1


if __name__ == "__main__":
    sys.exit(main())
