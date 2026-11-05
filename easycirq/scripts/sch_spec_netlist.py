#!/usr/bin/env python3
"""从 S1 的 spec.json + 块库生成**规范网表**（connectivity.Document），不连 EDA。

为什么需要它：S2 的 style-plan 只画了框（每块占哪一片），S3 的度量却要一张
**器件级**网表。中间这一步以前是空白，于是只能"先落图再量"——那正好绕过了
「未过 S2 不得进器件」。这条脚本把这一步补上：纯离线，只读块库。

不做的事（重要）：
  • 不发明几何。块库只有 parts / internal_nets / ports，**没有原理图坐标**。
    所以输出里**不含** bbox 与引脚坐标，`lib-layout` 仍然需要一份实测几何。
  • 不猜引脚号。块库用引脚**名**（`U5.VIN` / `U5.GND*`），离线拿不到编号，
    所以 number 与 name 都填这个名字，并在 issues 里如实标注。

输出：connectivity.Document 形态
  { schemaVersion, projectId, components[], nets[], connections[], modules[], issues[] }
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# connectivity.Document.Validate() 要求**精确等于** "1.4"。
# 注意它的报错写的是 "schemaVersion is required"，字段明明在 —— 见 friction #43。
SCHEMA = "1.4"

# 器件 id 前缀 → 位号前缀。块库的 part 形如 `res.1k_0402`、`ic.xl1509_5v_buck`。
PREFIX = {
    "res": "R", "cap": "C", "ind": "L", "ic": "U", "diode": "D", "led": "D",
    "conn": "J", "term": "J", "hdr": "J", "xtal": "Y", "sw": "SW",
    "fuse": "F", "mos": "Q", "fet": "Q", "tvs": "D", "opt": "U", "relay": "K",
}


def block_name(block_id: str) -> str:
    return block_id[len("block."):] if block_id.startswith("block.") else block_id


def ref_prefix(part_id: str) -> str:
    head = (part_id or "").split(".", 1)[0].lower()
    return PREFIX.get(head, "X")


def load_block(blocks_dir: pathlib.Path, block_id: str):
    p = blocks_dir / (block_name(block_id) + ".json")
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def generate(spec_path: pathlib.Path, blocks_dir: pathlib.Path):
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    modules = spec.get("modules") or []
    pages = spec.get("pages") or {}
    if not modules:
        raise ValueError("spec 里没有 modules")

    components, nets, connections, out_modules, issues = [], [], [], [], []
    nc_pins: list[dict] = []
    counters: dict[str, int] = {}
    net_by_name: dict[str, dict] = {}

    def ensure_net(name: str, scope: str = "global", role: str = "") -> dict:
        if name not in net_by_name:
            nid = "n%d" % (len(nets) + 1)
            n = {"id": nid, "name": name, "scope": scope}
            if role:
                n["role"] = role
            nets.append(n)
            net_by_name[name] = n
        return net_by_name[name]

    def next_ref(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return "%s%d" % (prefix, counters[prefix])

    for m in modules:
        mid = m.get("id") or "?"
        blk = load_block(blocks_dir, m.get("block") or "")
        if blk is None:
            issues.append({"severity": "error",
                           "message": "%s: 块 %r 不存在" % (mid, m.get("block"))})
            continue

        parts = blk.get("parts") or {}
        role_to_ref: dict[str, str] = {}
        mod_comp_ids: list[str] = []

        # ── 器件：为每个角色分配全工程唯一的位号 ──────────────────────
        for role, pspec in parts.items():
            part_id = (pspec or {}).get("part") or ""
            ref = next_ref(ref_prefix(part_id))
            role_to_ref[role] = ref
            cid = "c%d" % (len(components) + 1)
            mod_comp_ids.append(cid)
            components.append({
                "id": cid,
                "ref": ref,
                "role": role,
                # moduleId 让下游（S2 的区块、S3 的 layoutModules、S5 的落块）
                # 不用靠"器件顺序"去猜归属 —— 猜错会让整条链对错块。
                "moduleId": mid,
                "device": {"deviceUuid": "", "name": part_id},
                "pins": [],
                "pageName": m.get("page") or "",
                # lib-layout 在多页文档里要求每件有 pageId（"requires pageId in an
                # all-pages document"）。pageName 是人看的，pageId 才是判据。
                "pageId": pages.get(m.get("page") or "", ""),
            })

        # ── 内部网：`ROLE.PIN` 成员 + 可选的 `PORT:NAME` ──────────────
        port_bind = {p: (v or {}).get("bind_to")
                     for p, v in (m.get("ports") or {}).items()}
        unknown_pins = 0
        for k, members in enumerate(blk.get("internal_nets") or []):
            port_names = [x.split(":", 1)[1] for x in members
                          if isinstance(x, str) and x.startswith("PORT:")]
            plain = [x for x in members
                     if isinstance(x, str) and not x.startswith("PORT:")]

            if port_names:
                # 端口网：按 spec 的 bind_to 命名；没绑就退回块的 default_net
                pname = port_names[0]
                spec_port = (m.get("ports") or {}).get(pname) or {}
                spec_nc = spec_port.get("nc")

                # **NC 的引脚不许有网。** 给它一张"只有它自己"的网，
                # 在 KPI #1（未连接/悬空=0）里就是一条违规 —— 而 spec 明说它不接。
                # 所以要把它落成 noConnected 引脚，不产生任何连接。
                if spec_nc:
                    for member in plain:
                        if "." not in member:
                            continue
                        role, pin = member.split(".", 1)
                        ref = role_to_ref.get(role)
                        if ref is None:
                            continue
                        comp = next(c for c in components if c["ref"] == ref)
                        if not any(p_["number"] == pin for p_ in comp["pins"]):
                            comp["pins"].append({"number": pin, "name": pin})
                        comp["pins"] = [
                            dict(p_, noConnected=True)
                            if p_["number"] == pin else p_ for p_ in comp["pins"]]
                    nc_pins.append({"module": mid, "port": pname,
                                    "pin": plain[0] if plain else "",
                                    "reason": spec_nc})
                    continue

                net_name = port_bind.get(pname) or spec_port.get("default_net")
                if not net_name:
                    issues.append({"severity": "error",
                                   "message": "%s: 端口 %r 既没 bind_to 也没 default_net"
                                              % (mid, pname)})
                    continue
                scope = "global"
            else:
                # 块内部网：用第一个成员所在器件命名，保证实例之间不撞
                first = plain[0] if plain else ""
                owner_role = first.split(".", 1)[0] if "." in first else "X"
                net_name = "%s_N%d" % (role_to_ref.get(owner_role, "X"), k + 1)
                scope = "local"

            n = ensure_net(net_name, scope, "power" if net_name.upper() in
                           ("GND", "+5V", "+3V3", "+3V8", "VBAT_RAW", "+12V_FILT") else "")

            for member in plain:
                if "." not in member:
                    issues.append({"severity": "warn",
                                   "message": "%s: 成员 %r 不是 ROLE.PIN 形态" % (mid, member)})
                    continue
                role, pin = member.split(".", 1)
                ref = role_to_ref.get(role)
                if ref is None:
                    issues.append({"severity": "error",
                                   "message": "%s: 内部网引用了不存在的角色 %r" % (mid, role)})
                    continue
                cid = mod_comp_ids[[r for r, x in role_to_ref.items() if x == ref][0]
                                   and list(role_to_ref).index(role)]
                comp = next(c for c in components if c["id"] == cid)
                if not any(p["number"] == pin for p in comp["pins"]):
                    comp["pins"].append({"number": pin, "name": pin})
                    unknown_pins += 1
                # `Connection.Kind` 是**连接方式**，取值见 connectivity/design.go：
                #   "", pin_net, netlist, wire, netflag, netport, netlabel,
                #   power, ground, net_port_in/out/bi
                # `local`/`global` 是 `Net.Scope`，不是 Kind —— 两者混用会被拒。
                if net_name.upper() == "GND":
                    kind = "ground"
                elif net_name.upper() in ("+5V", "+3V3", "+3V8", "+12V_FILT",
                                          "VBAT_RAW", "+12V_RAW", "VSYS",
                                          "VBUS_L0", "BOOST_OUT"):
                    kind = "power"
                elif port_names:
                    kind = "netport"
                else:
                    kind = "wire"
                if not any(c_ for c_ in connections
                           if c_["componentId"] == cid and c_["pinNumber"] == pin):
                    connections.append({"componentId": cid, "pinNumber": pin,
                                        "netId": n["id"], "kind": kind})

        if unknown_pins:
            issues.append({"severity": "info",
                           "message": "%s: %d 个引脚用块库的引脚**名**当编号（离线拿不到真实脚号）"
                                      % (mid, unknown_pins)})

        out_modules.append({
            "id": mid,
            "name": (m.get("role") or mid),
            "coreComponents": mod_comp_ids,
            "internalNets": [],
            "ports": [],
        })

    doc = {
        "schemaVersion": SCHEMA,
        "projectId": spec.get("projectUuid") or "",
        "components": components,
        "nets": nets,
        "connections": connections,
        "modules": out_modules,
        "issues": issues,
        "noConnectDeclarations": nc_pins,
    }
    return doc


def summarise(doc) -> list[str]:
    out = []
    pages: dict[str, int] = {}
    for c in doc["components"]:
        pages[c.get("pageName") or "?"] = pages.get(c.get("pageName") or "?", 0) + 1
    out.append("器件 %d，网络 %d，连接 %d" %
               (len(doc["components"]), len(doc["nets"]), len(doc["connections"])))
    out.append("按页：" + "  ".join("%s=%d" % kv for kv in sorted(pages.items())))
    global_nets = [n["name"] for n in doc["nets"] if n.get("scope") == "global"]
    out.append("全局网（跨页）：" + ", ".join(global_nets))
    errs = [i for i in doc["issues"] if i["severity"] == "error"]
    warns = [i for i in doc["issues"] if i["severity"] == "warn"]
    ncs = doc.get("noConnectDeclarations") or []
    if ncs:
        out.append("NC（显式不接）：" + ", ".join(
            "%s:%s" % (x["module"], x["port"]) for x in ncs))
    out.append("问题：error %d，warn %d" % (len(errs), len(warns)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="从 spec.json + 块库生成规范网表")
    ap.add_argument("spec")
    ap.add_argument("--blocks-dir", default="runtime/internal/blocks/data")
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    spec_path = pathlib.Path(args.spec)
    blocks_dir = pathlib.Path(args.blocks_dir)
    if not spec_path.is_file():
        print("找不到 spec：%s" % spec_path, file=sys.stderr)
        return 2
    try:
        doc = generate(spec_path, blocks_dir)
    except (OSError, ValueError, KeyError) as exc:
        print("生成失败：%s" % exc, file=sys.stderr)
        return 2

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    errs = [i for i in doc["issues"] if i["severity"] == "error"]
    if args.json:
        print(json.dumps({"out": str(out), "summary": summarise(doc)},
                         ensure_ascii=False, indent=2))
    else:
        print("规范网表 → %s" % out)
        for line in summarise(doc):
            print("  " + line)
        for i in doc["issues"]:
            if i["severity"] != "info":
                print("  %s: %s" % (i["severity"], i["message"]))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
