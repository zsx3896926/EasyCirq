"""把 24 件的 M1 按电学拆成子模块，**两处 modules 同时改**。

上次失败原因：只改了 `layoutModules`，而成员集合来自 `connectivity.modules`，
所以搜索空间一点没变（候选数一个字节不差）。这次两边一起改。

拆法有电学含义：
  • 主子模块：core + 与 core 有**非电源网**相连的件（信号路径）
  • 电源子模块：只挂在电源/地上的件（去耦、旁路）—— 本来就该贴着走
"""
import json
import os
import pathlib
import subprocess

EXE = str(pathlib.Path(os.environ["LOCALAPPDATA"]) / "EasyCirq" / "bin" / "easycirq.exe")
POWER_NETS = {"GND", "+5V", "+3V3", "+3V8", "+12V_FILT", "VBAT_RAW",
              "+12V_RAW", "VSYS", "VBUS_L0", "BOOST_OUT"}


def split(inp, out, page):
    d = json.loads(pathlib.Path(inp).read_text(encoding="utf-8"))
    conn = d["connectivity"]
    netname = {n["id"]: n.get("name") or "" for n in conn["nets"]}
    nets_of = {}
    for x in conn["connections"]:
        nets_of.setdefault(x["componentId"], set()).add(netname.get(x["netId"], ""))
    title_of = {m["id"]: m.get("title") or m["id"] for m in d["layoutModules"]}
    intent = {m["id"]: m for m in d["layoutModules"]}

    new_conn_mods, new_intent = [], []
    for cm in conn["modules"]:
        members = list(cm.get("coreComponents") or []) + list(
            cm.get("peripheralComponents") or [])
        if len(members) <= 12:
            new_conn_mods.append(cm)
            new_intent.append(intent[cm["id"]])
            continue
        core = (cm.get("coreComponents") or [None])[0]
        signal, power = [], []
        for cid in members:
            if cid == core:
                continue
            (power if nets_of.get(cid, set()) <= POWER_NETS else signal).append(cid)
        print("  %s(%d 件) → 信号 %d / 电源 %d"
              % (cm["id"], len(members), len(signal) + 1, len(power)))
        new_conn_mods.append({"id": cm["id"], "name": cm.get("name"),
                              "coreComponents": [core],
                              "peripheralComponents": signal})
        it = dict(intent[cm["id"]])
        it["peripherals"] = [{"componentId": c} for c in signal]
        new_intent.append(it)

        if power:
            pid = cm["id"] + "P"
            new_conn_mods.append({"id": pid, "name": (cm.get("name") or "") + "（电源）",
                                  "coreComponents": [power[0]],
                                  "peripheralComponents": power[1:]})
            # 电源子模块的网络策略要覆盖它自己用到的所有网
            pol = {}
            used = set()
            for cid in power:
                used |= nets_of.get(cid, set())
            by_name = {v: k for k, v in netname.items()}
            for nm in used:
                nid = by_name.get(nm)
                if not nid:
                    continue
                pol[nid] = ("local_ground" if nm.upper() == "GND"
                            else ("local_power" if nm.upper() in POWER_NETS else "direct"))
            new_intent.append({"id": pid, "title": title_of.get(cm["id"], "") + "（电源）",
                               "coreComponentId": power[0],
                               "peripherals": [{"componentId": c} for c in power[1:]],
                               "netPolicies": pol})

    d["connectivity"]["modules"] = new_conn_mods
    d["layoutModules"] = new_intent
    d["maxCandidates"] = 1000000
    pathlib.Path(out).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print("  模块:", [(m["id"], len(m.get("peripheralComponents") or []) + 1)
                      for m in new_conn_mods])


def run(inp, out):
    p = subprocess.run([EXE, "sch", "lib-layout", "--from", str(inp), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=2400)
    return (p.stdout or "") + (p.stderr or "")


for page in ("P1", "P2"):
    src = "reports/hard-board/board2/layout-input-%s.json" % page
    dst = "reports/hard-board/board2/layout-split-%s.json" % page
    print("===", page)
    split(src, dst, page)
    out = run(dst, "reports/hard-board/board2/composition-%s.json" % page)
    print("  " + (out.strip()[:220] if out.strip() else "✅ 成功"))
    print()
