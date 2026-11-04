#!/usr/bin/env python3
"""harvest —— 从历史工程的 DRC 报告里长出**候选**规则。

# 它做什么

把一批 DRC 报告（EasyEDA 导出的 JSON，含 CLI 的警告/日志噪声）聚类成：
  · 每一类违规出现了多少次、涉及哪些网络、哪些位号、样例报文
  · **这一类能不能变成可执行规则**，如果能，是哪个谓词；如果不能，为什么
  · 能变的那几类，产出 review-ledger 形状的**候选**

# 它绝对不做什么

**不自动采纳。** 候选里**故意不写 `disposition`**，所以 `review_ledger.promote`
和 `validate_entry` 会当场拒绝——"这算不算公司规范"必须人定。
工具判错两边都致命：判成规则会拿常识去拦板，判成知识则永远拦不住东西。

**不做 ML、不做训练。** 这是聚类与提取，不是预测。

# 一条必须说清的事实

DRC 的两类违规**都不直接对应**我们现有的 4 个谓词
（`footprint_forbidden` / `part_forbidden` / `net_name_required` / `net_name_forbidden`，
全是网表级，没有几何谓词）：

| DRC rule | 实际含义 | 能不能变规则 |
|---|---|---|
| `Connection Error` | `<net>: U1_4 is disconnected from other objects of the same network` —— **开路/未布通** | **不能**。这是"这块板没做完"，不是设计规范。只能当知识 |
| `Clearance Error` | `(+3V3): e949 to (GND): e87 distance is 0mil, should be >= 6mil` —— **几何间距** | **不能直接**。没有几何谓词 |

**所以真正能变成规则的只有一条间接路径**：某个**器件**在违规里反复出现
（说明它的节距/焊盘尺寸与规则不兼容），于是提 `part_forbidden` 候选。

这条路径**必须有 dump 才能补上型号**（`device` 字段）；没 dump 就只报位号、不出候选。

# 用法

    python enterprise_harvest.py --drc <文件或目录> [--dump dump.json]
    python enterprise_harvest.py --drc ../retrocam-02/pcb --dump ../retrocam-02/pcb/dump2.json --out cand.json
    python enterprise_harvest.py --drc ... --json
"""
import argparse
import json
import pathlib
import re
import sys

SCHEMA_CANDIDATES = "easycirq-harvest/v1"

# 报文体里的位号：`U1_4`、`J3_20`
DESIG_RE = re.compile(r"\b([A-Z]{1,3}\d{1,3})_(\d{1,3})\b")
# 报文里的网络：`(+3V3)`、`(GND)`
NET_RE = re.compile(r"\(([^()]+)\)")
# 一句"距离应为多少"，用来读规则值
RULE_VAL_RE = re.compile(r"should be >= ([\d.]+)mil")

# 默认阈值：一条器件要被提成候选，至少这么多次、且占已归属违规的这么大比例
MIN_HITS = 50
MIN_SHARE = 0.10


# ── 读文件：容忍 CLI 噪声 ────────────────────────────────────────────────
def load_report(path):
    """返回 (doc, warnings, problem)。

    EasyEDA 的 DRC 导出是 **CLI 输出**，不是纯 JSON：
      · 开头可能有 `⚠ staleRisk: ...` 这类警告行
      · 结尾可能有一行日志（如 `pcb drc: native verdict failed; ...`）
    所以先扫出警告，再从第一个 `{` 起做 raw_decode，尾部多余内容只记不改。
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    warnings = [ln.strip() for ln in lines
                if ln.strip().startswith(("\u26a0", "!", "warning", "WARN"))]
    i = raw.find("{")
    if i < 0:
        return None, warnings, "找不到 JSON 起始的 {"
    try:
        doc, end = json.JSONDecoder().raw_decode(raw[i:])
    except Exception as exc:                            # noqa: BLE001
        return None, warnings, "JSON 解析失败: %s" % exc
    tail = raw[i + end:].strip()
    if tail:
        warnings.append("JSON 之后还有内容（%d 字节）：%s"
                        % (len(tail), tail.splitlines()[0][:80]))
    return doc, warnings, None


DRC_MARKERS = ("violations", "passed", "counts", "total")


def violations_of(doc):
    r = doc.get("result") or doc
    return r.get("violations") or []


def looks_like_drc(doc):
    """这像不像一份 DRC 报告？

    不能只看 `violations` 非空：**干净的 DRC 报告就是 `violations: []`**。
    所以看有没有 DRC 特有的字段（passed / counts / total / violations）。

    这条判定是必要的：给一个目录时，里面还有 dump、plan、vias 等一堆 JSON，
    全都算进来会把违规数翻倍（实测 1902 → 3500）。
    """
    r = doc.get("result") or doc
    if not isinstance(r, dict):
        return False
    return any(k in r for k in DRC_MARKERS)


# ── 聚类 ────────────────────────────────────────────────────────────────
def harvest(paths, dump_path=None):
    files_ok, files_bad, all_warn, skipped = [], [], [], []
    clusters = []          # list，不是 dict：元组键无法 JSON 序列化
    index = {}             # (rule, objType) -> 在 clusters 里的下标
    total = 0
    for p in paths:
        doc, warns, problem = load_report(p)
        if problem:
            files_bad.append({"file": str(p), "problem": problem})
            continue
        if not looks_like_drc(doc):
            skipped.append({"file": p.name,
                            "why": "没有 DRC 字段（passed/counts/total/violations），"
                                   "不是 DRC 报告，已跳过"})
            continue
        files_ok.append(str(p))
        for w in warns:
            all_warn.append({"file": p.name, "warning": w})
        for v in violations_of(doc):
            total += 1
            rule = v.get("rule") or "?"
            obj = v.get("objType") or "?"
            key = (rule, obj)
            if key not in index:
                index[key] = len(clusters)
                clusters.append({
                    "rule": rule, "objType": obj, "count": 0,
                    "nets": {}, "designators": {}, "samples": [],
                    "rule_values": {},
                })
            c = clusters[index[key]]
            c["count"] += 1
            msg = v.get("message") or ""
            for n in NET_RE.findall(msg):
                if n and not n.startswith("e"):
                    c["nets"][n] = c["nets"].get(n, 0) + 1
            for d, _pin in DESIG_RE.findall(msg):
                c["designators"][d] = c["designators"].get(d, 0) + 1
            for rv in RULE_VAL_RE.findall(msg):
                c["rule_values"][rv] = c["rule_values"].get(rv, 0) + 1
            if len(c["samples"]) < 3 and msg:
                c["samples"].append(msg[:160])

    # 位号 → 型号（靠 dump）
    dev = {}
    if dump_path:
        try:
            dd = json.loads(pathlib.Path(dump_path).read_text(encoding="utf-8"))
            r = dd.get("result") or dd
            for comp in r.get("components") or []:
                d = comp.get("designator")
                if d:
                    dev[d] = {
                        "device": comp.get("device"),
                        "pads": len(comp.get("pads") or []),
                    }
        except Exception as exc:                        # noqa: BLE001
            all_warn.append({"file": str(dump_path),
                             "warning": "dump 读不了，型号补不上：%s" % exc})

    # 位号总榜（跨类）
    desig_total = {}
    for c in clusters:
        for d, n in c["designators"].items():
            desig_total[d] = desig_total.get(d, 0) + n
    attributed = sum(desig_total.values())

    return {
        "schema": SCHEMA_CANDIDATES,
        "inputs": {
            "files_ok": files_ok,
            "files_failed": files_bad,
            "files_skipped": skipped,
            "warnings": all_warn,
            "dump": str(dump_path) if dump_path else None,
        },
        "totals": {"violations": total, "clusters": len(clusters),
                   "with_designator": attributed,
                   "without_designator": total - attributed},
        "clusters": clusters,
        "designators": desig_total,
        "devices": dev,
    }


# ── 判定：能不能变成规则 ────────────────────────────────────────────────
WHY_NOT_RULE = {
    "Connection Error":
        "开路/未布通（报文形如 «<net>: U1_4 is disconnected from other objects "
        "of the same network»）。这是「这块板没做完」，不是设计规范；写成规则会拦住"
        "所有未完成的板，等于没有规则。只能当知识。",
    "Clearance Error":
        "几何间距（报文形如 «(+3V3): e949 to (GND): e87 distance is 0mil»）。"
        "现有 4 个谓词全是网表级，没有几何谓词；要把它变成规则得先有「按网络对限距」"
        "这类新谓词，且需要几何数据。只能当知识。",
}


def propose_candidates(h, min_hits=MIN_HITS, min_share=MIN_SHARE):
    """只有「某个器件在违规里反复出现」这一条路能变成可执行规则。"""
    out = []
    attributed = h["totals"]["with_designator"]
    if attributed <= 0:
        return out, ["没有任何报文带位号，无法归属到器件，不出候选"]
    notes = []
    for d, n in sorted(h["designators"].items(), key=lambda kv: -kv[1]):
        share = n / attributed
        if n < min_hits or share < min_share:
            notes.append("%s 出现 %d 次（占 %.1f%%），低于候选阈值"
                         "（≥%d 次且 ≥%.0f%%），不提案"
                         % (d, n, 100 * share, min_hits, 100 * min_share))
            continue
        info = h["devices"].get(d)
        if not info or not info.get("device"):
            notes.append("%s 出现 %d 次（占 %.1f%%），**够阈值但缺型号**"
                         "（%s），无法生成 part_forbidden —— 补 --dump"
                         % (d, n, 100 * share,
                            "没有 dump" if not info else "dump 里这个位号没有 device"))
            continue
        dev = info["device"]
        # 同类里最典型的报文，作为证据
        sample = None
        for c in h["clusters"]:
            if d in c["designators"] and c["samples"]:
                sample = c["samples"][0]
                break
        out.append({
            "id": "HARVEST-%s" % d,
            # 关键：**故意不写 disposition**。没有它，promote 会当场拒绝。
            "found": ("历史 DRC 里位号 %s 出现 %d 次违规（占已归属的 %.1f%%），"
                      "型号 %s" % (d, n, 100 * share, dev)),
            "candidate_rule": {
                "id": "banned-part-%s" % str(dev).lower().replace("/", "-"),
                "kind": "advisory",
                "title": "禁用器件 %s（历史 DRC 高频）" % dev,
                "predicate": {"type": "part_forbidden", "patterns": [str(dev)]},
                "evidence": "历史 DRC 聚类：%s 出现 %d 次；样例：%s"
                            % (d, n, (sample or "")[:120]),
                "owner": "",
                "verified_on": "",
            },
            "evidence": {
                "designator": d,
                "device": dev,
                "hits": n,
                "share": round(100 * share, 1),
                "sample_message": sample,
            },
            "needs_human": [
                "这算不算公司规范？（工具不替人判断）",
                "禁用这个型号还是改它的封装/节距？",
                "verified_on 怎么写：你打算在哪块板上验它真的会拦？",
            ],
        })
    return out, notes


# ── 输出 ────────────────────────────────────────────────────────────────
def print_report(h, cands, notes):
    inp, tot = h["inputs"], h["totals"]
    print("DRC 历史聚类")
    print()
    print("  读入 %d 份，失败 %d 份，非 DRC 已跳过 %d 份，警告 %d 条"
          % (len(inp["files_ok"]), len(inp["files_failed"]),
             len(inp.get("files_skipped") or []), len(inp["warnings"])))
    for bad in inp["files_failed"]:
        print("    ✗ %s：%s" % (pathlib.Path(bad["file"]).name, bad["problem"]))
    for w in inp["warnings"][:8]:
        print("    ⚠ %s：%s" % (w["file"], w["warning"][:100]))
    if len(inp["warnings"]) > 8:
        print("    … 还有 %d 条警告" % (len(inp["warnings"]) - 8))
    print()
    print("  违规总数 %d，分成 %d 类；带位号 %d 条（%.0f%%），"
          "不带 %d 条"
          % (tot["violations"], tot["clusters"], tot["with_designator"],
             100.0 * tot["with_designator"] / max(1, tot["violations"]),
             tot["without_designator"]))
    print()
    print("一、按违规类型")
    for c in sorted(h["clusters"], key=lambda x: -x["count"]):
        print("   %-18s %-28s %5d 次"
              % (c["rule"], c["objType"], c["count"]))
        top_nets = sorted(c["nets"].items(), key=lambda kv: -kv[1])[:4]
        top_des = sorted(c["designators"].items(), key=lambda kv: -kv[1])[:4]
        if top_nets:
            print("      网络: " + "、".join("%s(%d)" % (k, v)
                                            for k, v in top_nets))
        if top_des:
            print("      位号: " + "、".join("%s(%d)" % (k, v)
                                            for k, v in top_des))
        why = WHY_NOT_RULE.get(c["rule"])
        if why:
            print("      ✗ 不能直接变规则：" + why[:70] + "…")
    print()
    print("二、位号总榜（占已归属违规的比例）")
    attributed = max(1, tot["with_designator"])
    for d, n in sorted(h["designators"].items(), key=lambda kv: -kv[1])[:8]:
        info = h["devices"].get(d) or {}
        print("   %-5s %5d  %5.1f%%  %s"
              % (d, n, 100.0 * n / attributed, info.get("device") or "（无型号）"))
    print()
    print("三、候选（**必须人审，工具不采纳**）")
    if cands:
        for c in cands:
            print("   %s → %s" % (c["id"], c["candidate_rule"]["title"]))
            print("      %s" % c["found"])
            print("      谓词: %s" % c["candidate_rule"]["predicate"])
    else:
        print("   没有产出候选")
    if notes:
        print()
        print("四、没被提为候选的（逐条给原因）")
        for n in notes:
            print("   · " + n)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drc", required=True,
                    help="DRC 报告文件，或包含它的目录")
    ap.add_argument("--dump", default=None,
                    help="板子 dump（补器件型号用；没有就只能报位号）")
    ap.add_argument("--out", default=None, help="把候选写进这个 JSON")
    ap.add_argument("--json", action="store_true", help="整份结果以 JSON 输出")
    ap.add_argument("--min-hits", type=int, default=MIN_HITS)
    ap.add_argument("--min-share", type=float, default=MIN_SHARE)
    a = ap.parse_args()

    src = pathlib.Path(a.drc)
    paths = sorted(src.glob("*.json")) if src.is_dir() else [src]
    if not paths:
        print("没有找到 DRC 报告：%s" % src)
        return 2

    h = harvest(paths, a.dump)
    cands, notes = propose_candidates(h, a.min_hits, a.min_share)

    if a.json:
        print(json.dumps({"harvest": h, "candidates": cands,
                          "not_proposed": notes}, ensure_ascii=False,
                         indent=2, default=str))
    else:
        print_report(h, cands, notes)

    if a.out:
        payload = {
            "schema": SCHEMA_CANDIDATES,
            "note": ("候选，不是规则。没有 disposition 字段，所以 "
                     "review_ledger.promote 会拒绝——必须先由人写明 "
                     "disposition（rule 或 knowledge）并补 verified_on。"),
            "from": {"drc": str(src), "dump": a.dump},
            "entries": cands,
            "not_proposed": notes,
        }
        pathlib.Path(a.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8")
        if not a.json:
            print()
            print("候选已写入 %s" % a.out)
            print("  **它不是规则**：没有 disposition，promote 会拒绝。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
