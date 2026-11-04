"""企业知识的检索：让「知识类」条目真的被用上。

# 为什么需要这个模块

`review-ledger` 把经验分成两类。规则类已经能阻断（`enterprise_rules.py`）。
知识类如果只是"存起来了"，它就等于 `pcb_layout` 那个字段——**没人读的装饰**。

这个模块负责让知识类条目在**审阅一块板时被检索出来**，并说清为什么。

# 三条设计约束

1. **检索必须可解释**：每条召回都给出 `matched_on`（命中了什么词）。
   说不出为什么召回的检索，人没法判断该不该信。

2. **检索不阻断**：这是知识不是规则。返回码只在**输入错误**或**知识失效**时非零，
   召回本身永远不改变交付判定。知识伪装成门禁会被误报拖垮。

3. **没被召回的知识是死的**：`--audit` 专门查这个——一条谁都召回不到的知识，
   和没写没区别。要么补 tags，要么删掉。**这一点比"存了多少条"重要得多。**

# 检索方式：关键词 + 标签，不用向量也不用 LLM

因为要**可测**。向量相似度不可解释、LLM 检索不可复现，两者都无法写成
"故意构造一个上下文 → 必须召回某条"的测试。关键词匹配牺牲召回率，换来可验证。

## 已知局限（不装）

- **同义词不匹配**：写"去耦"不会命中只写了"decoupling"的条目
- **中文分词是朴素的**：按 2 字以上连续中文切，会切出怪词
- 所以 `--audit` 会报告"没有任何可检索文本"的条目，提示补 tags
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

LEDGER_SCHEMA = "easycirq-review-ledger/v1"
KNOWLEDGE_DIR_NAMES = ("knowledge", "knowledge.json")

# 同一个企业目录里三类文件并存，认得彼此
SIBLING_SCHEMAS = ("easycirq-enterprise-rules/v1",
                   "easycirq-enterprise-parts/v1")

# 这些词太泛，匹配上说明不了什么，反而让每条都召回
STOPWORDS = {"the", "and", "for", "with", "this", "that", "一个", "这个", "我们", "需要"}


def layer_dirs(project_dir=None):
    import os
    out = []
    env = os.environ.get("EASYCIRQ_KNOWLEDGE_DIR", "").strip()
    out.append(("enterprise(env)" if env else "enterprise(默认)",
                pathlib.Path(env) if env else pathlib.Path.home() / ".easycirq" / "knowledge"))
    if project_dir:
        out.append(("project", pathlib.Path(project_dir) / ".easycirq" / "knowledge"))
    return out


def collect_knowledge(project_dir=None, explicit=None):
    """收所有层的知识条目。返回 (entries, sources, problems)。

    知识条目有两个来源：
      - review-ledger 文件里 disposition=knowledge 的条目
      - 直接放在知识目录下的 knowledge-*.json（schema: enterprise-knowledge/v1）
    """
    entries = []
    sources = []
    problems = []

    candidates = []
    if explicit:
        candidates.append(("explicit", pathlib.Path(explicit)))
    candidates.extend(layer_dirs(project_dir))

    for layer, base in candidates:
        if base.is_file():
            files = [base]
            sources.append({"layer": layer, "dir": str(base.parent),
                            "files": [base.name]})
        elif base.is_dir():
            files = sorted(base.glob("*.json"))
            sources.append({"layer": layer, "dir": str(base),
                            "files": [f.name for f in files]})
        else:
            if layer == "explicit":
                problems.append({"file": str(base), "error": "显式路径不存在"})
            else:
                sources.append({"layer": layer, "dir": str(base),
                                "files": [], "note": "目录不存在，跳过"})
            continue

        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception as exc:  # noqa: BLE001
                problems.append({"file": str(path), "error": f"读不出来: {exc}"})
                continue

            if data.get("schema") == LEDGER_SCHEMA:
                for entry in data.get("entries") or []:
                    if entry.get("disposition") != "knowledge":
                        continue
                    kn = entry.get("knowledge") or {}
                    entries.append({
                        "id": entry.get("id"),
                        "title": kn.get("title") or "",
                        "body": kn.get("body") or "",
                        "tags": kn.get("tags") or [],
                        # 这一栏是「规则不许降级成知识」的凭据，报告要看得见
                        "why_not_rule": kn.get("why_not_rule") or "",
                        "from": str(path), "layer": layer,
                    })
            elif data.get("schema") == "easycirq-enterprise-knowledge/v1":
                for item in data.get("knowledge") or []:
                    entries.append({
                        "id": item.get("id"),
                        "title": item.get("title") or "",
                        "body": item.get("body") or "",
                        "tags": item.get("tags") or [],
                        "why_not_rule": item.get("why_not_rule") or "",
                        "from": str(path), "layer": layer,
                    })
            else:
                # 认得的兄弟（规则/器件）静默跳过；不认识的才报
                if data.get("schema") in SIBLING_SCHEMAS:
                    continue
                problems.append({
                    "file": str(path),
                    "error": f"schema {data.get('schema')!r} 不是知识来源，跳过"})
    return entries, sources, problems


def tokenize(text):
    """朴素分词：中文按 2 字以上连续段，英文/数字按词。"""
    text = text.lower()
    tokens = set()
    for run in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text):
        if run in STOPWORDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", run):
            # 中文长串也切 2-gram，否则整个短语只能整段命中
            for i in range(len(run) - 1):
                tokens.add(run[i:i + 2])
            tokens.add(run)
        else:
            # **纯数字不算词。**
            # 实测：正文里的 "XH2.54" 会切出 "54"，于是连接器那条知识
            # 被任何含 54 的板召回（风扇板就因为别的原因召回了它）。
            # 带单位的数字（200ma / 12v）留着，它们有意义。
            if not run.isdigit():
                tokens.add(run)
    return tokens


# ── 概念派生：板子隐含了什么
#
# 问题（2026-11-03 实测）：检索上下文原本只有网表 + 意图的字面值，于是
# 「负载类型 inductive」和客户写的「感性负载必须续流」**一个词都不重合**——
# 风扇板明明就是感性负载，那条最该命中的知识却召回不到。5 条典型经验只召回 1 条。
#
# 这一层把板子的事实翻译成该领域的概念词，中英都加，因为客户两种都会写。
#
# **这是同义词表，不是语义理解。** 它只能覆盖下面列出的映射；表里没有的概念
# 仍然召回不到。`--audit` 会报告永远召不回的条目，但不会替你补这颗表。
CONCEPTS = {
    "inductive": ["感性负载", "感性", "续流", "反向尖峰", "尖峰", "flyback",
                  "反激", "二极管", "继电器", "电机", "线圈"],
    "ntc": ["热敏", "热敏电阻", "ntc", "温度", "测温", "分压", "阈值"],
    "rail": ["电源", "供电", "轨", "去耦", "退耦", "decoupling", "旁路"],
    "switch": ["驱动", "开关", "三极管", "mosfet", "上拉", "下拉", "栅极", "基极"],
    "hysteresis": ["回差", "迟滞", "抖动", "反复启停", "hysteresis"],
    "tolerance": ["容差", "精度", "公差", "误差", "tolerance"],
    "load": ["负载", "电流", "功耗", "发热"],
    "comparator": ["比较器", "运放", "opamp", "lm393", "比较"],
    "connector": ["连接器", "端子", "接口", "对外", "出机壳", "esd", "静电", "tvs"],
}


def derived_concepts(netlist, intent=None):
    """从板子的事实推出该领域的概念词。返回 (tokens, facts)。"""
    toks = set()
    facts = []

    # ── 网表侧的检测先做：它不依赖 intent，不能被下面的 early return 跳过
    try:
        for comp in (netlist or {}).get("components") or []:
            if comp.get("componentType") != "part":
                continue
            if str(comp.get("designator") or "").upper().startswith("J"):
                toks.update(CONCEPTS["connector"])
                facts.append("板上有连接器 → 补入接口/静电保护概念")
                break
    except Exception:  # noqa: BLE001
        pass
    try:
        for comp in (netlist or {}).get("components") or []:
            mpn = str(comp.get("manufacturerId") or "").lower()
            if any(k in mpn for k in ("lm393", "lm358", "opamp", "comparator")):
                toks.update(CONCEPTS["comparator"])
                facts.append(f"有比较器 {mpn.upper()} → 补入比较器概念")
                break
    except Exception:  # noqa: BLE001
        pass

    if not intent:
        return toks, facts

    sw = (intent.get("switches") or [{}])[0]
    kind = str(sw.get("load_kind") or "").lower()
    if "induct" in kind:
        toks.update(CONCEPTS["inductive"])
        facts.append("板上有感性负载 → 补入续流/尖峰相关概念")
    if sw.get("load_ma") or sw.get("load"):
        toks.update(CONCEPTS["load"])
        facts.append("有负载电流 → 补入负载/发热概念")
    if sw.get("part") or sw.get("kind"):
        toks.update(CONCEPTS["switch"])
        facts.append("有开关管 → 补入驱动相关概念")

    sensor = str(((intent.get("threshold") or {}).get("sensor") or {})
                 .get("kind") or "").lower()
    if sensor:
        toks.update(CONCEPTS["ntc"])
        facts.append(f"传感器 {sensor} → 补入测温/分压概念")

    if (intent.get("threshold") or {}).get("hysteresis_c"):
        toks.update(CONCEPTS["hysteresis"])
        facts.append("有回差要求 → 补入迟滞概念")

    if (intent.get("threshold") or {}).get("tolerances"):
        toks.update(CONCEPTS["tolerance"])
        facts.append("有容差声明 → 补入精度概念")

    if intent.get("rails"):
        toks.update(CONCEPTS["rail"])
        facts.append("有电源轨 → 补入去耦/供电概念")

    return toks, facts


def board_context(netlist, intent=None):

    """从网表 + 意图抽特征词。返回 (tokens, 描述用的事实)。"""
    parts = [c for c in (netlist.get("components") or [])
             if c.get("componentType") == "part"]
    bits = []
    for comp in parts:
        designator = str(comp.get("designator") or "")
        if designator:
            bits.append(designator)
        footprint = (comp.get("footprintRef") or {}).get("name") \
            or comp.get("footprint") or ""
        if footprint:
            bits.append(str(footprint))
        value = str((comp.get("otherProperty") or {}).get("Value") or "")
        if value:
            bits.append(value)
    for net in {p.get("net") for c in parts for p in c.get("pins") or [] if p.get("net")}:
        bits.append(net)

    facts = []
    if intent:
        sw = (intent.get("switches") or [{}])[0]
        if sw.get("load_ma"):
            bits.append(f"{sw['load_ma']}ma")
            facts.append(f"负载 {sw['load_ma']}mA")
        if sw.get("load_kind"):
            bits.append(str(sw["load_kind"]))
            facts.append(f"负载类型 {sw['load_kind']}")
        for net, volt in (intent.get("rails") or {}).items():
            bits.append(f"{volt}v")
            bits.append(f"{int(volt)}v")
            facts.append(f"{net}={volt}V")
        spec = intent.get("threshold") or {}
        if spec.get("hysteresis_c"):
            bits.append(f"{spec['hysteresis_c']}c")
            facts.append(f"回差 {spec['hysteresis_c']}°C")
        sensor = (spec.get("sensor") or {}).get("kind")
        if sensor:
            bits.append(str(sensor))
            facts.append(f"传感器 {sensor}")
        if (intent.get("threshold") or {}).get("tolerances"):
            bits.append("tolerance")
            bits.append("容差")
            facts.append("有容差声明")

    query = " ".join(str(b) for b in bits)
    tokens = tokenize(query)
    # 并入派生概念（同义词表，见 CONCEPTS 的说明）
    derived, derived_facts = derived_concepts(netlist, intent)
    tokens |= derived
    facts = facts + derived_facts
    return tokens, facts


def score(entry, query_tokens):
    """返回 (分数, matched_on)。标签命中权重高——那是人特意标的。"""
    matched = []
    total = 0
    for tag in entry.get("tags") or []:
        tag_tokens = tokenize(str(tag))
        hit = tag_tokens & query_tokens
        if hit:
            total += 10
            matched.append(f"tag:{tag}")
        elif str(tag).lower() in " ".join(query_tokens):
            total += 10
            matched.append(f"tag:{tag}")

    body_tokens = tokenize(entry.get("title", "") + " " + entry.get("body", ""))
    hit = body_tokens & query_tokens
    # 只算像样的词，单字不算
    hit = {h for h in hit if len(h) >= 2}
    if hit:
        total += len(hit)
        matched.append("body:" + ",".join(sorted(hit)[:6]))
    return total, matched


def search(entries, query_tokens, min_score=1):
    ranked = []
    for entry in entries:
        s, matched = score(entry, query_tokens)
        if s >= min_score:
            ranked.append((s, entry, matched))
    ranked.sort(key=lambda x: -x[0])
    return [{"id": e["id"], "title": e["title"], "score": s,
             "matched_on": m, "from": e["from"], "layer": e["layer"]}
            for s, e, m in ranked]


def audit(entries):
    """检查两件事，两件都是"存了但用不上"。

    ### 1. 没有任何可检索文本
    标题/标签/正文全是停用词或空——永远不会被召回。

    ### 2. **用自己的标签检索，召不回自己**
    这一条更隐蔽：条目有标签，但标签和正文对不上（比如标签写"布局"、正文
    却在讲成本）。它平时能靠正文偶然命中，但靠标签是召不回的，
    说明标签没起到"分拣"的作用。

    自洽检查的做法：拿这条自己的 tags + title 当查询，看它排不排得进结果。
    """
    dead = []
    for entry in entries:
        text = " ".join([entry.get("title", "")] + list(entry.get("tags") or [])
                        + [entry.get("body", "")])
        if not tokenize(text):
            dead.append({"id": entry["id"], "reason": "标题/标签/正文都没有可检索的词"})
            continue
        # 自洽：用自己当查询
        own = tokenize(" ".join([entry.get("title", "")]
                                + [str(t) for t in entry.get("tags") or []]))
        if own:
            hits = search([entry], own)
            if not hits:
                dead.append({
                    "id": entry["id"],
                    "reason": "用自己的标签+标题检索，召不回自己——标签和内容对不上"})
    return dead


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--netlist", help="网表（检索上下文）")
    ap.add_argument("--intent", help="意图文件（补充上下文）")
    ap.add_argument("--project-dir")
    ap.add_argument("--knowledge", action="append", default=[],
                    help="显式指定知识来源（文件或目录，可重复）")
    ap.add_argument("--audit", action="store_true",
                    help="检查有没有「永远不会被召回」的知识条目")
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    sources_all = []
    problems_all = []
    entries = []
    targets = args.knowledge or [None]
    for target in targets:
        got, src, prob = collect_knowledge(project_dir=args.project_dir,
                                           explicit=target)
        entries.extend(got)
        sources_all.extend(src)
        problems_all.extend(prob)

    # 同 id 后层覆盖前层
    merged = {}
    order = []
    for entry in entries:
        if entry["id"] not in merged:
            order.append(entry["id"])
        merged[entry["id"]] = entry
    entries = [merged[i] for i in order]

    if args.audit:
        dead = audit(entries)
        report = {"schema": "easycirq-knowledge-audit/v1",
                  "knowledge_entries": len(entries),
                  "never_retrievable": dead, "sources": sources_all}
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"知识审计：{len(entries)} 条")
            if dead:
                print(f"  ✗ 有 {len(dead)} 条**永远不会被召回**：")
                for d in dead:
                    print(f"      {d['id']}: {d['reason']}")
                print("  这些和没写一样——补 tags 或删掉。")
            else:
                print("  ✓ 每条都有可检索文本")
        return 2 if dead else 0

    if args.describe or not args.netlist:
        if args.json:
            print(json.dumps({"sources": sources_all,
                              "knowledge_entries": len(entries),
                              "ids": [e["id"] for e in entries],
                              "problems": problems_all},
                             ensure_ascii=False, indent=2))
        else:
            print(f"企业知识：{len(entries)} 条")
            for src in sources_all:
                note = src.get("note") or f"{len(src['files'])} 个文件"
                print(f"  [{src['layer']}] {src['dir']}  {note}")
            for e in entries:
                tags = ",".join(e.get("tags") or []) or "(无标签)"
                print(f"    - {e['id']}  {e['title']}  [{tags}]")
        return 0

    netlist = json.loads(pathlib.Path(args.netlist).read_text(encoding="utf-8-sig"))
    netlist = netlist.get("result") or netlist
    intent = None
    if args.intent:
        intent = json.loads(pathlib.Path(args.intent).read_text(encoding="utf-8-sig"))
        intent = intent.get("result") or intent

    query_tokens, facts = board_context(netlist, intent)
    hits = search(entries, query_tokens)

    report = {"schema": "easycirq-knowledge-search/v1",
              "context": facts, "knowledge_entries": len(entries),
              "hits": hits, "problems": problems_all,
              "note": "知识只做参考，不影响交付判定"}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"这块板检索到 {len(hits)} 条企业知识（共 {len(entries)} 条）")
        if facts:
            print("  上下文：" + "；".join(facts))
        for h in hits:
            print(f"  · [{h['score']:>2}] {h['id']}  {h['title']}")
            print(f"         命中：{'；'.join(h['matched_on'])}")
        if not hits:
            print("  （没有相关的企业知识；这不代表板子没问题，只是知识库里没有可参考的）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
