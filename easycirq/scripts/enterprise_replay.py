"""E③ 回放：采纳的候选，用**产生它的那份 DRC**回放，必须命中。

# 为什么必须有这一步

候选是"从历史统计出来的"，统计上常见不等于这条规则真能拦住东西。
所以每条要落地的候选，必须能用它自己的证据证明：**这条谓词放到网表上会触发**。

回放的构造方式：
  · 从源 dump 里取出那个位号的器件（型号 = 候选的 pattern）
  · 造一个只含这一个器件的最小网表
  · 用**真正的规则引擎** `enterprise_rules.evaluate()` 跑这条候选规则
  · 触发了 → `hit`；没触发 → `unknown`（**不标 pass**）
  · 拿不到源数据 → `unknown`，并写清缺什么

不标 pass 是刻意的：`pass` 会被读成"这条规则没问题"，而实际上什么也没证明。
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import enterprise_rules  # noqa: E402


def _dump_components(dump_path):
    try:
        doc = json.loads(pathlib.Path(dump_path).read_text(encoding="utf-8"))
    except Exception as exc:                            # noqa: BLE001
        return None, "dump 读不了：%s" % exc
    r = doc.get("result") or doc
    comps = r.get("components") or []
    return comps, None


def _netlist_for(comps, designator, device):
    """造一个只含目标器件的最小网表，格式跟 rules 引擎一致。"""
    for c in comps:
        if c.get("designator") != designator:
            continue
        return {"components": [{
            "componentType": "part",
            "designator": designator,
            "device": c.get("device") or device,
            # 引擎读 otherProperty["Manufacturer Part"]；真实网表导出也是这个字段。
            "otherProperty": {"Manufacturer Part": c.get("device") or device},
            "footprint": (c.get("footprintRef") or {}).get("name") or "",
            "pins": [{"net": (p.get("net") or "")} for p in c.get("pads") or []],
        }]}
    return None


def replay(candidates, dump_path, drc_dir=None):
    """逐条回放。返回 [{id, verdict, detail}]。"""
    comps, err = _dump_components(dump_path) if dump_path else (None, "没有给 --dump")
    out = []
    for e in candidates:
        cid = e.get("id")
        rule = e.get("candidate_rule") or {}
        ev = e.get("evidence") or {}
        des = ev.get("designator")
        dev = ev.get("device")

        if err:
            out.append({"id": cid, "verdict": "unknown",
                        "detail": "无法回放：%s" % err})
            continue
        if not des:
            out.append({"id": cid, "verdict": "unknown",
                        "detail": "候选没有位号证据，无法回放"})
            continue

        nl = _netlist_for(comps, des, dev)
        if nl is None:
            out.append({"id": cid, "verdict": "unknown",
                        "detail": "源 dump 里找不到位号 %s，无法回放" % des})
            continue

        results, findings = enterprise_rules.evaluate([rule], nl)
        st = results[0]["status"] if results else "unknown"
        if st == "fail":
            out.append({"id": cid, "verdict": "hit",
                        "detail": "规则在含 %s（%s）的最小网表上触发了"
                                  % (des, dev)})
        else:
            out.append({"id": cid, "verdict": "unknown",
                        "detail": "规则在含 %s（%s）的最小网表上没有触发（status=%s）"
                                  "——**不能算通过**，说明这条谓词拦不住它自己的证据"
                                  % (des, dev, st)})
    return out


def print_replay(rows):
    print("回放（用产生候选的那份 dump 重建最小网表，跑真正的规则引擎）")
    print()
    for r in rows:
        mark = {"hit": "✓", "unknown": "?"}.get(r["verdict"], "?")
        print("  %s %-16s %-8s %s" % (mark, r["id"], r["verdict"], r["detail"]))
    hits = sum(1 for r in rows if r["verdict"] == "hit")
    unk = sum(1 for r in rows if r["verdict"] == "unknown")
    print()
    print("  命中 %d 条，unknown %d 条，**没有一条被标成 pass**" % (hits, unk))
