"""企业规则：可执行的部分。

## 这个模块只装「能执行」的东西

企业给 EasyCirq 的「经验」分两类，性质完全不同，**混在一起会出事**：

| 类型 | 例子 | 处置 | 能否阻断交付 |
|---|---|---|---|
| **可执行规则**（本模块） | 「禁用 0402 封装」「这颗料不许用」 | 变成判据，进检查链 | **能** |
| **可检索知识**（不在本模块） | 「上次某拓扑振荡的原因」「客户偏好先出方案」 | 检索库，AI 审阅时参考 | **不能** |

两条铁律：

1. **知识不许伪装成规则**：执行不了的条目不许进出门禁。否则它天天误报，
   最后被人关掉，等于没写。
2. **规则不许降级成知识**：能自动查的必须自动查。写进知识库 =
   下次没人看，等于没执行。

## 加载分层与优先级

顺序（**后者覆盖/优先于前者**，同名规则以更近的层为准）：

1. 内置层：随发布包下发的通用规则（当前为空，预留给以后）
2. 企业层：`$EASYCIRQ_KNOWLEDGE_DIR`，或默认 `~/.easycirq/knowledge/`
3. 项目层：`<项目>/.easycirq/knowledge/`

**加载失败必须说清读了哪一份。** 本目标的前身已经在这上面栽过：
同一个 `standard-parts.json` 装了三份，报错只说文件名不说路径，
排查用了好几轮。

## 规则格式（enterprise-rules/v1）

```json
{
  "schema": "easycirq-enterprise-rules/v1",
  "layer": "enterprise",
  "rules": [
    {
      "id": "no-0402-packaging",
      "kind": "hard",
      "title": "禁用 0402 封装",
      "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
      "evidence": "企业设计规范 DS-2024-07 §3.2",
      "owner": "硬件部"
    }
  ]
}
```

`kind` 只有两个值，语义必须分明：

- `hard` —— 违反即失败（进返回码）
- `advisory` —— 违反只提示（不改变返回码）

**默认是 `hard`，必须显式写 `advisory` 才能降级。** 反过来（默认 advisory）
会让企业以为规则生效了其实没有。
"""
import argparse
import fnmatch
import json
import os
import pathlib
import sys

SCHEMA = "easycirq-enterprise-rules/v1"

# 同一个企业目录里会并存这三类文件，各自加载器要认得彼此
SIBLING_SCHEMAS = ("easycirq-enterprise-parts/v1",
                   "easycirq-enterprise-knowledge/v1",
                   "easycirq-review-ledger/v1")

# 支持的谓词。每个都必须能对**网表**直接判定，判不了就报 unknown，不猜。
PREDICATES = ("footprint_forbidden", "part_forbidden", "net_name_required",
              "net_name_forbidden")


def layer_dirs(project_dir=None):
    """返回 [(层名, 目录)]，按优先级从低到高。"""
    out = []
    env = os.environ.get("EASYCIRQ_KNOWLEDGE_DIR", "").strip()
    if env:
        out.append(("enterprise(env)", pathlib.Path(env)))
    else:
        home = pathlib.Path.home() / ".easycirq" / "knowledge"
        out.append(("enterprise(默认)", home))
    if project_dir:
        out.append(("project", pathlib.Path(project_dir) / ".easycirq" / "knowledge"))
    return out


def load_rules(project_dir=None, explicit=None):
    """读所有层的规则文件，合并。返回 (rules, sources, problems)。

    rules 保持 dict 形态并记下**来自哪个文件**——只报「规则 no-0402 失败」而不说
    它是谁加的，人根本没法去改。
    """
    sources = []
    problems = []
    rules = {}
    order = []

    candidates = []
    if explicit:
        candidates.append(("explicit", pathlib.Path(explicit)))
    candidates.extend(layer_dirs(project_dir))

    for layer, base in candidates:
        # explicit 可以是**文件**也可以是目录。
        # 上一版只按目录处理，于是 `--rule 某个规则.json` 被报成"目录不存在，跳过"，
        # 还返回 0 —— 企业给了规则、工具说读不到、却算通过。
        # 这正是本目标要防的"存了不等于生效"。
        if base.is_file():
            files = [base]
            entry = {"layer": layer, "dir": str(base.parent),
                     "files": [base.name]}
            sources.append(entry)
        elif base.is_dir():
            files = sorted(base.glob("*.json"))
            sources.append({"layer": layer, "dir": str(base),
                            "files": [f.name for f in files]})
        else:
            # 显式指定的路径不存在 = 错误；默认层不存在 = 正常（企业还没建库）
            if layer == "explicit":
                problems.append({"file": str(base),
                                 "error": "显式指定的规则路径不存在"})
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
            if data.get("schema") != SCHEMA:
                # 知识目录是三类文件共用的。认得的兄弟 schema 静默跳过；
                # 只有**不认识的**才报错——否则自检会被一堆假问题淹没，
                # 然后没人再看它（和误报太多的门禁一个下场）。
                if data.get("schema") in SIBLING_SCHEMAS:
                    continue
                problems.append({"file": str(path),
                                 "error": f"schema 必须是 {SCHEMA}，实际 "
                                          f"{data.get('schema')!r}"})
                continue
            for rule in data.get("rules") or []:
                rid = rule.get("id")
                if not rid:
                    problems.append({"file": str(path), "error": "有规则缺 id"})
                    continue
                pred = (rule.get("predicate") or {}).get("type")
                if pred not in PREDICATES:
                    # 不认识的谓词 = 执行不了。**不许静默跳过**，
                    # 否则企业以为规则生效了。
                    problems.append({
                        "file": str(path), "rule": rid,
                        "error": f"谓词 {pred!r} 不支持；支持的是 {list(PREDICATES)}"})
                    continue
                kind = (rule.get("kind") or "hard").lower()
                if kind not in ("hard", "advisory"):
                    problems.append({"file": str(path), "rule": rid,
                                     "error": f"kind 必须是 hard/advisory，实际 {kind!r}"})
                    continue
                merged = dict(rule)
                merged["kind"] = kind
                merged["_file"] = str(path)
                merged["_layer"] = layer
                if rid not in rules:
                    order.append(rid)
                else:
                    merged["_overrides"] = rules[rid].get("_file")
                rules[rid] = merged
    return [rules[r] for r in order], sources, problems


def _pins_net_of(part):
    return {p.get("net") for p in part.get("pins") or [] if p.get("net")}


def evaluate(rules, netlist):
    """对网表跑所有规则。返回 (results, findings)。

    每个结果都带 `evidence` 与 `owner`——人看到违规要知道**找谁**。
    """
    parts = [c for c in netlist.get("components") or []
             if c.get("componentType") == "part"]
    nets = sorted({p.get("net") for c in parts
                   for p in c.get("pins") or [] if p.get("net")})

    results = []
    findings = []
    for rule in rules:
        pred = rule["predicate"]
        ptype = pred["type"]
        violated = []
        status = "pass"

        if ptype == "footprint_forbidden":
            patterns = pred.get("patterns") or []
            if not patterns:
                status = "unknown"
            for comp in parts:
                footprint = (comp.get("footprintRef") or {}).get("name") \
                    or comp.get("footprint") or ""
                for pat in patterns:
                    if fnmatch.fnmatch(str(footprint).lower(), f"*{pat.lower()}*"):
                        violated.append(f"{comp.get('designator')} 的封装是 {footprint}")
                        break

        elif ptype == "part_forbidden":
            banned = {str(x).lower() for x in (pred.get("parts") or [])}
            lcsc = {str(x).lower() for x in (pred.get("lcsc") or [])}
            if not banned and not lcsc:
                status = "unknown"
            for comp in parts:
                mpn = str((comp.get("otherProperty") or {}).get("Manufacturer Part")
                          or comp.get("manufacturerId") or "").lower()
                code = str((comp.get("otherProperty") or {}).get("Supplier Part")
                           or "").lower()
                if (mpn and mpn in banned) or (code and code in lcsc):
                    violated.append(f"{comp.get('designator')} 的器件是 {mpn or code}")

        elif ptype in ("net_name_required", "net_name_forbidden"):
            patterns = pred.get("patterns") or []
            if not patterns:
                status = "unknown"
            elif ptype == "net_name_required":
                required = pred.get("required_for") or []
                for req in required:
                    if not any(n.startswith(req) for n in nets):
                        violated.append(f"没有任何网络以 {req} 开头")
            else:
                for net in nets:
                    for pat in patterns:
                        if fnmatch.fnmatch(net.lower(), pat.lower()):
                            violated.append(f"网络名 {net} 命中禁用模式 {pat}")

        if status == "unknown":
            results.append({"id": rule["id"], "kind": rule["kind"],
                            "status": "unknown", "title": rule.get("title", ""),
                            "reason": "规则没有给出可判定的参数（patterns/parts 为空）",
                            "file": rule.get("_file")})
            continue

        if violated:
            results.append({"id": rule["id"], "kind": rule["kind"],
                            "status": "fail", "title": rule.get("title", ""),
                            "violations": violated,
                            "evidence": rule.get("evidence", ""),
                            "owner": rule.get("owner", ""),
                            "file": rule.get("_file"), "layer": rule.get("_layer")})
            findings.append({
                "code": "ENTERPRISE_RULE_" + rule["id"].upper().replace("-", "_"),
                "status": "confirmed" if rule["kind"] == "hard" else "advisory",
                "message": (f"{rule.get('title') or rule['id']}："
                            f"{'；'.join(violated[:3])}"
                            + (f"（另有 {len(violated)-3} 处）" if len(violated) > 3 else "")),
            })
        else:
            results.append({"id": rule["id"], "kind": rule["kind"],
                            "status": "pass", "title": rule.get("title", ""),
                            "file": rule.get("_file")})
    return results, findings


def summarize(results):
    hard_fail = [r for r in results if r["status"] == "fail" and r["kind"] == "hard"]
    soft = [r for r in results if r["status"] == "fail" and r["kind"] == "advisory"]
    unknown = [r for r in results if r["status"] == "unknown"]
    if hard_fail:
        return "fail"
    if unknown:
        return "unknown"
    if soft:
        return "advisory"
    return "pass" if results else "not_run"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--netlist", help="要检查的网表（list.json）")
    ap.add_argument("--rule", action="append", default=[],
                    help="显式指定规则文件（可重复，优先级最高）")
    ap.add_argument("--project-dir", help="项目目录（读其 .easycirq/knowledge）")
    ap.add_argument("--describe", action="store_true",
                    help="只说明加载了哪些层/哪些文件，不检查")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.rule:
        rules = []
        sources = []
        problems = []
        for path in args.rule:
            r, s, p = load_rules(project_dir=args.project_dir, explicit=path)
            rules, sources, problems = r, sources + s, problems + p
    else:
        rules, sources, problems = load_rules(project_dir=args.project_dir)

    if args.describe or not args.netlist:
        report = {"schema": "enterprise-rules-report/v1",
                  "sources": sources,
                  "rules_loaded": len(rules),
                  "rule_ids": [r["id"] for r in rules],
                  "problems": problems}
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"企业规则：加载 {len(rules)} 条")
            for src in sources:
                note = src.get("note") or f"{len(src['files'])} 个文件"
                print(f"  [{src['layer']}] {src['dir']}  {note}")
                for name in src["files"]:
                    print(f"      - {name}")
            if problems:
                print("\n问题（这些规则**没有生效**）：")
                for prob in problems:
                    print(f"  ! {prob.get('file')}: {prob['error']}")
        return 2 if problems else 0

    netlist = json.loads(pathlib.Path(args.netlist).read_text(encoding="utf-8-sig"))
    netlist = netlist.get("result") or netlist
    results, findings = evaluate(rules, netlist)
    verdict = summarize(results)

    report = {"schema": "enterprise-rules-report/v1", "verdict": verdict,
              "sources": sources, "results": results, "findings": findings,
              "problems": problems}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"企业规则判定：{verdict}")
        for r in results:
            mark = {"pass": "✓", "fail": "✗", "unknown": "?"}[r["status"]]
            extra = ""
            if r["status"] == "fail":
                extra = f"  [{r['kind']}] " + "；".join(r["violations"][:3])
            print(f"  {mark} {r['id']:28} {r.get('title','')}{extra}")
        if problems:
            print("\n有规则没生效（这是问题，不是通过）：")
            for prob in problems:
                print(f"  ! {prob.get('file')}: {prob['error']}")

    if verdict == "fail":
        return 1
    if verdict == "unknown":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
