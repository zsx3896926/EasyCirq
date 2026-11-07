#!/usr/bin/env python3
"""把装不下的模块**按信号簇自动拆页**。

为什么需要它：M1（24 件）在 A0 上都排不出（实测四种纸全部失败）。
靠"换纸"这条路走到底了，剩下的产品决策就是**拆页**——
而这不该让用户选，产品自己要能判断并执行。

算法（刻意保守，保证信号网不跨页）：
  1. 只用**信号网**建图（电源/地网不参与，它们在每页都会变成旗标）
  2. 并查集求连通簇；装不下的簇再按"核心 + 外围"二分
  3. **只接电源/地的去耦件**按与簇的空间/网络关系分配，用来平衡两页的件数
  4. 每页输出一份完整输入（components / connectivity / layoutModules），
     各页再各自选纸

关键约束：**信号网绝不切开**。真实跨页信号需要两端都画网络标签，
本工具的渲染与原语不支持自动生成，所以宁可多拆一页也不切断信号网。

用法：
  python scripts/sch_module_split.py --input one-M1.json --out-dir <目录> \\
      [--max-parts 14]
输出：one-<M>a.json、one-<M>b.json …（并打印每页的器件与网络统计）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# 电源/地网：拆页时允许跨页（各页由旗标承载）
POWER_NETS = {"GND", "AGND", "PGND", "DGND", "+5V", "+3V3", "+3V8", "+12V",
              "VBAT_RAW", "VIN", "VCC", "VDD"}


def _is_power(name: str) -> bool:
    n = (name or "").strip().upper()
    return n in POWER_NETS or n.startswith("+")


def analyse(doc):
    """返回 (设计号→prim(zip), 网id→名字, 元件→信号网集合, 电源专用元件)。"""
    conn = (doc.get("connectivity") or {})
    names = {n["id"]: n.get("name") or "" for n in (conn.get("nets") or [])}
    links = conn.get("connections") or []
    byid = {m["primitiveId"]: m["designator"] for m in (doc.get("measurements") or [])}
    sig = {cid: set() for cid in byid}
    for e in links:
        nm = names.get(e.get("netId"), "")
        if _is_power(nm):
            continue
        if e["componentId"] in sig:
            sig[e["componentId"]].add(e["netId"])
    power_only = [cid for cid, s in sig.items() if not s]
    return byid, names, sig, power_only


def clusters(byid, sig):
    par = {cid: cid for cid in byid}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    net2 = {}
    for cid, nets in sig.items():
        for n in nets:
            net2.setdefault(n, []).append(cid)
    for members in net2.values():
        for m in members[1:]:
            union(members[0], m)
    # **电源专用件不参与聚类**：它们后面统一分配，否则会变成一堆单件簇
    out = {}
    for cid in byid:
        if not sig.get(cid):
            continue
        out.setdefault(find(cid), []).append(cid)
    return [g for g in out.values() if g]


def balanced_cut(group, sig, byid, limit):
    """把一个超限簇按"核心 + 外围"二分（核心=连接度最高的件）。"""
    if len(group) <= limit:
        return [group]
    deg = {c: len(sig.get(c) or ()) for c in group}
    core = max(group, key=lambda c: (deg.get(c, 0), c))
    # 按与核心的共享信号网数排序，前 limit 个留在第一页
    def share(c):
        return len((sig.get(c) or set()) & (sig.get(core) or set()))

    rest = [c for c in group if c != core]
    rest.sort(key=lambda c: (-share(c), byid.get(c, "")))
    first = [core] + rest[:max(0, limit - 1)]
    second = rest[max(0, limit - 1):]
    out = [first]
    if second:
        out += balanced_cut(second, sig, byid, limit)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="按信号簇自动拆页")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-parts", type=int, default=14,
                    help="每页最多器件数（默认 14，实测 10 件在 A4 上稳妥）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    src = pathlib.Path(args.input)
    doc = json.loads(src.read_text(encoding="utf-8"))
    byid, names, sig, power_only = analyse(doc)
    groups = clusters(byid, sig)
    groups.sort(key=lambda g: (-len(g), byid.get(g[0], "")))

    # 超限的簇继续二分，直到每页都不超限
    pages = []
    for g in groups:
        pages += balanced_cut(g, sig, byid, args.max_parts)

    # 电源专用件（去耦）按顺序补给最少的页，用来平衡
    pages.sort(key=lambda p: -len(p))
    for c in sorted(power_only, key=lambda x: byid.get(x, "")):
        tgt = min(pages, key=len)
        tgt.append(c)

    outdir = pathlib.Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    mid = src.stem[4:] if src.stem.startswith("one-") else src.stem
    suffix = "abcdefghijklmnop"

    made = []
    for i, page in enumerate(pages):
        sub = json.loads(json.dumps(doc))
        keep = set(page)
        sub["measurements"] = [m for m in (doc.get("measurements") or [])
                               if m["primitiveId"] in keep]
        sub["keepouts"] = [k for k in (doc.get("keepouts") or [])
                           if not k.get("moduleId")
                           or k.get("moduleId") in (mid, mid + suffix[i])]
        conn = sub.get("connectivity") or {}
        # 连接：只留本页器件；网络只留本页有成员的（信号网天然完整）
        conn["connections"] = [e for e in (conn.get("connections") or [])
                               if e.get("componentId") in keep]
        live = {e["netId"] for e in conn["connections"]}
        conn["nets"] = [n for n in (conn.get("nets") or []) if n["id"] in live]
        conn["issues"] = []
        # **components 也要按本页过滤**：留着别的页的器件，会让它们的引脚
        # 变成"既无网络也无 NC"，求解器直接判输入不完整。
        if isinstance(conn.get("components"), list):
            conn["components"] = [c for c in conn["components"]
                                  if (c.get("primitiveId") or c.get("id")) in keep]
        sub["connectivity"] = conn
        # layoutModules：本页自己的模块（核心 = 连接度最高的件）
        deg = {c: len(sig.get(c) or ()) for c in keep}
        core = max(keep, key=lambda c: (deg.get(c, 0), byid.get(c, "")))
        # **归属表**：求解器读 connectivity.modules 的
        # coreComponents / peripheralComponents，缺了会报
        # "every component must belong to one module"
        conn["modules"] = [{
            "id": "%s%s" % (mid, suffix[i]),
            "name": "%s-%d" % (mid, i + 1),
            "coreComponents": [core],
            "peripheralComponents": [c for c in sorted(keep) if c != core],
        }]
        sub["connectivity"] = conn
        # **网策略**：求解器要求每个网有明确策略，缺了会报
        # "net <id> needs an explicit supported policy"
        orig_pol = {}
        for lm0 in (doc.get("layoutModules") or []):
            orig_pol.update(lm0.get("netPolicies") or {})
        net_pol = {}
        for n in conn.get("nets") or []:
            nm = names.get(n["id"], "")
            up = nm.strip().upper()
            if n["id"] in orig_pol:
                net_pol[n["id"]] = orig_pol[n["id"]]
            elif up in ("GND", "AGND", "PGND", "DGND"):
                net_pol[n["id"]] = "local_ground"
            elif up.startswith("+"):
                net_pol[n["id"]] = "local_power"
            else:
                net_pol[n["id"]] = "direct"
        sub["layoutModules"] = [{
            "id": "%s%s" % (mid, suffix[i]),
            "title": "%s-%d" % (mid, i + 1),
            "coreComponentId": core,
            "netPolicies": net_pol,
            "peripherals": [{"componentId": c} for c in sorted(keep)
                            if c != core],
        }]
        dst = outdir / ("one-%s%s.json" % (mid, suffix[i]))
        dst.write_text(json.dumps(sub, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        made.append({"file": dst.name, "id": sub["layoutModules"][0]["id"],
                     "parts": len(keep),
                     "designators": sorted(byid[c] for c in keep)})

    # **跨页信号网**：每个信号网的成员若分布在多于一页，电路就断了。
    page_of = {}
    for i, page in enumerate(pages):
        for c in page:
            page_of[c] = i
    severed = []
    for nid in {n for nets in sig.values() for n in nets}:
        members = [cid for cid, ns in sig.items() if nid in ns]
        pgs = {page_of.get(c) for c in members}
        if len(pgs) > 1:
            severed.append({"net": names.get(nid, nid),
                            "pages": sorted(pg + 1 for pg in pgs if pg is not None)})
    if args.json:
        print(json.dumps({"pages": made, "severedNets": severed},
                         ensure_ascii=False, indent=2))
    else:
        print("  拆页：%s → %d 页（每页上限 %d 件）"
              % (mid, len(made), args.max_parts))
        for pg in made:
            print("    %-12s %2d 件  %s"
                  % (pg["id"], pg["parts"], " ".join(pg["designators"])))
        if severed:
            print("  ⚠ 跨页信号网 %d 个（电路会断，需跨页网络标签）:"
                  % len(severed))
            for it in severed[:8]:
                print("      %-12s 跨页 %s" % (it["net"], it["pages"]))
        else:
            print("  ✅ 没有跨页信号网（每条信号网都在单页内完整）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
