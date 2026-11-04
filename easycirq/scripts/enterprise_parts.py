"""企业器件库：用实测参数覆盖手册值，且每个字段都能说出它来自哪一层。

# 为什么需要

器件手册给的是保证范围，不是实际值。企业自己测过一批料，得到了更准的数
（比如 AO3400A 的 Vgs(th) 实测 1.3V，手册标 1.05V），这个数应该被子设计判据用上，
而不是每次手填进意图文件。

# 必须避开的一个坑

本目标的前身栽过一次：同一个 `standard-parts.json` 装了三个副本，解析器静默取了
第一个命中的，报错只说文件名不说路径，排查花了三轮。

所以这里：

1. **分层解析与规则库一致**：企业层 → 项目层，后者覆盖前者
2. **每个字段标注来源层**：`--resolve` 能看出这个 `vgs_th` 是人测的还是内置的
3. **加载失败说清读了哪一份**：不存在 / schema 不对 / 字段非法，逐条报出路径

# 合并语义：**字段级合并，每个字段标注来源**

我最初写的是"整条替换，不做字段级合并"，理由是"各字段来自不同来源很难解释"。
**那个理由站不住，而且文档和代码不一致**（代码一直是字段级合并）。

字段级合并其实更有用：企业只想补一个实测 `vgs_th`，不该被迫把 `deviceUuid`、
`footprint` 也抄一遍——抄漏一个就变成一条坏料。

歧义靠**逐字段标注来源**消解：`--resolve` 会把每个字段的层标出来。
看见 `vgs_th ← enterprise` 和 `deviceUuid ← builtin`，人立刻知道哪些是企业改的、
哪些还是内置的。**可解释的合并就不是歧义。**
"""
import argparse
import json
import pathlib
import sys

SCHEMA = "easycirq-enterprise-parts/v1"

# 同一个企业目录里三类文件并存，认得彼此
SIBLING_SCHEMAS = ("easycirq-enterprise-rules/v1",
                   "easycirq-enterprise-knowledge/v1",
                   "easycirq-review-ledger/v1")


def layer_dirs(project_dir=None):
    import os
    out = []
    env = os.environ.get("EASYCIRQ_KNOWLEDGE_DIR", "").strip()
    out.append(("enterprise(env)" if env else "enterprise(默认)",
                pathlib.Path(env) if env else pathlib.Path.home() / ".easycirq" / "knowledge"))
    if project_dir:
        out.append(("project", pathlib.Path(project_dir) / ".easycirq" / "knowledge"))
    return out


def load_parts(project_dir=None, explicit=None):
    """返回 (parts, sources, problems)。

    parts: key -> {"...条目字段...", "_layer", "_file"}
    """
    parts = {}
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
            if data.get("schema") != SCHEMA:
                # 知识目录里规则/知识/器件三类文件并存，是**正常用法**。
                # 认得的兄弟静默跳过；不认识的才报。
                #
                # 这一层改成静默（原来是报 problem），因为过滤逻辑放在调用方
                # 会在每个调用方漏一次——2026-11-03 enterprise_review 就没过滤，
                # 把另外两类文件报成了「加载问题」，把真问题盖住了。
                if data.get("schema") in SIBLING_SCHEMAS:
                    continue
                problems.append({
                    "file": str(path),
                    "error": f"schema {data.get('schema')!r} 不是器件库，已跳过"})
                continue
            for key, entry in (data.get("parts") or {}).items():
                if not isinstance(entry, dict):
                    problems.append({"file": str(path),
                                     "error": f"{key}: 条目必须是对象"})
                    continue
                merged = dict(entry)
                merged["_layer"] = layer
                merged["_file"] = str(path)
                if key in parts:
                    merged["_overrides"] = parts[key]["_file"]
                parts[key] = merged
    return parts, sources, problems


def builtin_parts():
    """内置标准件库。找不到就返回空——**不假装有**。"""
    here = pathlib.Path(__file__).resolve().parents[1]
    for cand in (here / "references" / "standard-parts.json",
                 here / "references" / "standard-parts.json"):
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}, None
            return data.get("parts") or {}, cand
    return {}, None


def resolve(part_key, enterprise=None):
    """合并后的**有效参数** + 每个字段来自哪一层。

    语义：企业层覆盖内置层（整条替换）；都没有就是 unknown，不猜。
    """
    builtin, builtin_path = builtin_parts()
    out = {}
    origin = {}

    if part_key in builtin:
        for k, v in builtin[part_key].items():
            out[k] = v
            origin[k] = "builtin"
    if enterprise and part_key in enterprise:
        entry = enterprise[part_key]
        for k, v in entry.items():
            if k.startswith("_"):
                continue
            out[k] = v
            origin[k] = entry.get("_layer", "enterprise")
        origin["_entry"] = f"{entry.get('_file')}" + (
            f"（覆盖 {entry['_overrides']}）" if entry.get("_overrides") else "")
    if not out:
        return None, {}, builtin_path
    return out, origin, builtin_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list-builtin", action="store_true",
                    help="列出内置标准件库的全部键（要覆盖某个内置器件时，"
                         "先在这里查它的键）")
    ap.add_argument("--filter", default="",
                    help="配合 --list-builtin 按子串过滤，如 --filter mosfet")
    ap.add_argument("--resolve", help="显示某个器件键的合并后有效参数")
    ap.add_argument("--project-dir")
    ap.add_argument("--parts", action="append", default=[],
                    help="显式指定企业器件库（文件或目录，可重复）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    enterprise = {}
    sources_all = []
    problems_all = []
    for target in (args.parts or [None]):
        got, src, prob = load_parts(project_dir=args.project_dir, explicit=target)
        enterprise.update(got)
        sources_all.extend(src)
        problems_all.extend(prob)

    if args.list_builtin:
        builtin, builtin_path = builtin_parts()
        needle = args.filter.strip().lower()
        keys = sorted(k for k in builtin
                      if not needle or needle in k.lower())
        report = {"schema": "easycirq-enterprise-parts-builtin/v1",
                  "file": str(builtin_path) if builtin_path else None,
                  "total": len(builtin), "shown": len(keys),
                  "keys": keys}
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"内置标准件库：{len(builtin)} 个键"
                  + (f"，匹配 {needle!r} 的 {len(keys)} 个" if needle else ""))
            print(f"  来源：{builtin_path or '（找不到）'}")
            for k in keys:
                entry = builtin[k]
                label = entry.get("mpn") or entry.get("value") or ""
                print(f"    {k:34} {label}")
            if not keys:
                print("    （没有匹配的键；不加 --filter 看全部）")
            print()
            print("要覆盖其中某个器件，就在你的 parts.*.json 里用同一个键。")
        return 0

    if args.resolve:
        params, origin, builtin_path = resolve(args.resolve, enterprise)
        report = {"schema": "easycirq-enterprise-parts-resolve/v1",
                  "key": args.resolve,
                  "builtin_file": str(builtin_path) if builtin_path else None,
                  "effective": params, "origin": origin,
                  "problems": problems_all}
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            if params is None:
                print(f"{args.resolve}: 内置库和企业库里都没有这个键")
                print(f"  内置库: {builtin_path or '(找不到)'}")
                for src in sources_all:
                    print(f"  企业库[{src['layer']}]: {src['dir']}  "
                          f"{src.get('note') or str(len(src['files'])) + ' 个文件'}")
            else:
                print(f"{args.resolve} 的有效参数：")
                for k, v in params.items():
                    print(f"  {k:16} = {v!r:32} ← {origin.get(k, '?')}")
                if origin.get("_entry"):
                    print(f"  条目来源: {origin['_entry']}")
        return 0 if params else 2

    # 默认：列出企业库
    report = {"schema": "easycirq-enterprise-parts-report/v1",
              "sources": sources_all, "parts": sorted(enterprise),
              "problems": problems_all}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"企业器件库：{len(enterprise)} 条")
        for src in sources_all:
            note = src.get("note") or f"{len(src['files'])} 个文件"
            print(f"  [{src['layer']}] {src['dir']}  {note}")
        for key in sorted(enterprise):
            entry = enterprise[key]
            over = "（覆盖内置）" if entry.get("_overrides") else ""
            print(f"    - {key}{over}  {entry.get('mpn') or entry.get('value') or ''}")
        print()
        print("要用实测值覆盖某个内置器件？先查它的键：")
        print("  python easycirq/scripts/enterprise_parts.py --list-builtin --filter mosfet")
        if problems_all:
            print("\n问题：")
            for p in problems_all:
                print(f"  ! {p.get('file')}: {p['error']}")
    return 2 if problems_all and not enterprise else 0


if __name__ == "__main__":
    sys.exit(main())
