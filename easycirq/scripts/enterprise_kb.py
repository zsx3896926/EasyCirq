"""企业知识库的浏览与导出：可查、可见。

`enterprise_selfcheck.py` 回答"我的库健康吗"；这个脚本回答
"我的库里到底有什么、每条是谁加的、有没有生效过"。

用法：

    enterprise_kb.py --list               终端列出（规则/知识/器件三类）
    enterprise_kb.py --show R-001         看一条的全文（JSON）
    enterprise_kb.py --html-out kb.html   导出自包含 HTML

## 为什么 HTML 要自包含

企业多半把文件放到内网共享目录，有人从浏览器打开。**不能依赖 CDN**：
内网常常出不去，一旦引了外部 CSS/字体，页面就是一堆裸文本。
所以 CSS 全部内联，不引任何外部资源，也不引 JS。

## 报告必须回答的三件事

1. 有哪些条目（三类分开）
2. **每条规则拦过什么**（`verified_on` 是人对"它真的有用"的背书）
3. **哪些条目从未生效**（死规则 / 死知识）——
   这一项比"有多少条"重要，也是本目标反复强调的那条线
"""
import argparse
import html
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import enterprise_parts  # noqa: E402
import enterprise_rules  # noqa: E402
import knowledge_search  # noqa: E402

CSS = """
:root { --fg:#1a1a1a; --muted:#666; --line:#e2e2e2; --bg:#fff;
        --ok:#0a7d32; --bad:#c1121f; --warn:#a15c00; --tint:#f7f7f8; }
* { box-sizing: border-box; }
body { margin:0; padding:32px 28px 64px; font:15px/1.6 -apple-system,
       "Segoe UI","Microsoft YaHei",sans-serif; color:var(--fg); background:var(--bg);
       max-width:1100px; }
h1 { font-size:22px; margin:0 0 4px; }
h2 { font-size:17px; margin:36px 0 10px; padding-bottom:6px;
     border-bottom:1px solid var(--line); }
.sub { color:var(--muted); font-size:13px; margin:0 0 20px; }
table { width:100%; border-collapse:collapse; font-size:14px; margin:0 0 8px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line);
        vertical-align:top; }
th { background:var(--tint); font-weight:600; white-space:nowrap; }
code { background:var(--tint); padding:1px 5px; border-radius:3px;
       font:13px/1.5 ui-monospace,Consolas,monospace; }
.mono { font:13px/1.5 ui-monospace,Consolas,monospace; }
.ok{color:var(--ok);font-weight:600} .bad{color:var(--bad);font-weight:600}
.warn{color:var(--warn);font-weight:600}
.tag { display:inline-block; background:var(--tint); border:1px solid var(--line);
       border-radius:10px; padding:0 8px; font-size:12px; margin-right:4px; }
.card { border:1px solid var(--line); border-radius:8px; padding:14px 16px;
        margin:0 0 14px; }
.empty { color:var(--muted); font-style:italic; }
.foot { margin-top:40px; color:var(--muted); font-size:12px;
        border-top:1px solid var(--line); padding-top:12px; }
"""


def esc(value):
    return html.escape("" if value is None else str(value))


def load_all(project_dir=None, explicit=None):
    rules, rule_src, rule_prob = enterprise_rules.load_rules(
        project_dir=project_dir, explicit=explicit)
    known, know_src, know_prob = knowledge_search.collect_knowledge(
        project_dir=project_dir, explicit=explicit)
    parts, part_src, part_prob = enterprise_parts.load_parts(
        project_dir=project_dir, explicit=explicit)
    # load_parts 已认得兄弟 schema，不再报假错
    return {
        "rules": rules, "knowledge": known, "parts": parts,
        "sources": rule_src + [s for s in know_src if s not in rule_src]
                   + [s for s in part_src if s not in know_src],
        "problems": rule_prob + know_prob + part_prob,
    }


def dead_knowledge(known):
    return knowledge_search.audit(known)


def rules_without_evidence(rules):
    return [r for r in rules if not str(r.get("verified_on") or "").strip()]


def render_html(bundle, title="企业知识库"):
    rules = bundle["rules"]
    known = bundle["knowledge"]
    parts = bundle["parts"]
    problems = bundle["problems"]
    dead = dead_knowledge(known)
    no_ev = rules_without_evidence(rules)

    out = []
    out.append("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">")
    out.append(f"<title>{esc(title)}</title><style>{CSS}</style></head><body>")
    out.append(f"<h1>{esc(title)}</h1>")

    total = len(rules) + len(known) + len(parts)
    if total == 0:
        out.append('<p class="sub">这个库还是空的。放文件到知识目录后再导出一次。</p>')
    else:
        out.append(f'<p class="sub">规则 {len(rules)} 条 · 知识 {len(known)} 条 · '
                   f'器件 {len(parts)} 条</p>')

    # ── 健康提示放最前面：有问题先看见
    issues = []
    for r in no_ev:
        issues.append(f'规则 <code>{esc(r["id"])}</code> 没有 verified_on'
                      f'（没写清它抓到过什么，无法判断是否真的有用）')
    for d in dead:
        issues.append(f'知识 <code>{esc(d["id"])}</code>：{esc(d["reason"])}')
    for p in problems:
        issues.append(f'加载问题 <code>{esc(p.get("file"))}</code>：{esc(p.get("error"))}')

    if issues:
        out.append('<div class="card">')
        out.append(f'<p class="bad">⚠ 有 {len(issues)} 项不会生效，先处理它们</p>')
        out.append("<ul>")
        for item in issues:
            out.append(f"<li>{item}</li>")
        out.append("</ul></div>")
    elif total:
        out.append('<div class="card"><p class="ok">✓ 全部条目可加载、'
                   '有证据、可检索</p></div>')

    # ── 规则
    out.append(f"<h2>一、可执行规则（{len(rules)} 条，违反会拦住交付）</h2>")
    if not rules:
        out.append('<p class="empty">没有规则。企业规范里能写成'
                   '「对网表做一次确定性判定」的，放这里。</p>')
    else:
        out.append("<table><tr><th>ID</th><th>标题</th><th>强度</th>"
                   "<th>依据</th><th>找谁</th><th>拦过什么</th></tr>")
        for r in rules:
            kind = r.get("kind") or "hard"
            kind_cell = ('<span class="bad">hard</span>' if kind == "hard"
                         else '<span class="warn">advisory</span>')
            ev = r.get("verified_on") or ""
            ev_cell = (esc(ev) if ev.strip()
                       else '<span class="bad">未证明会触发</span>')
            out.append(
                f'<tr><td class="mono">{esc(r["id"])}</td>'
                f'<td>{esc(r.get("title"))}</td>'
                f'<td>{kind_cell}</td>'
                f'<td>{esc(r.get("evidence"))}</td>'
                f'<td>{esc(r.get("owner"))}</td>'
                f'<td>{ev_cell}</td></tr>')
        out.append("</table>")

    # ── 知识
    out.append(f"<h2>二、可检索知识（{len(known)} 条，只提示、不阻断）</h2>")
    if not known:
        out.append('<p class="empty">没有知识条目。</p>')
    else:
        out.append("<table><tr><th>ID</th><th>标题</th><th>标签</th>"
                   "<th>为什么不能自动查</th></tr>")
        for k in known:
            tags = "".join(f'<span class="tag">{esc(t)}</span>'
                           for t in (k.get("tags") or [])) or \
                   '<span class="bad">无标签</span>'
            why = k.get("why_not_rule") or \
                '<span class="bad">未说明</span>'
            out.append(
                f'<tr><td class="mono">{esc(k["id"])}</td>'
                f'<td>{esc(k.get("title"))}</td>'
                f'<td>{tags}</td>'
                f'<td>{esc(k.get("why_not_rule")) if k.get("why_not_rule") else why}</td>'
                f'</tr>')
        out.append("</table>")

    # ── 器件
    out.append(f"<h2>三、企业器件参数（{len(parts)} 条）</h2>")
    if not parts:
        out.append('<p class="empty">没有企业器件条目。</p>')
    else:
        out.append("<table><tr><th>键</th><th>型号</th><th>实测参数</th></tr>")
        for key in sorted(parts):
            entry = parts[key]
            measured = entry.get("measured") or {}
            cells = ", ".join(f"{esc(k2)}={esc(v2)}"
                              for k2, v2 in measured.items()
                              if k2 != "note") or "—"
            out.append(f'<tr><td class="mono">{esc(key)}</td>'
                       f'<td>{esc(entry.get("mpn") or entry.get("value"))}</td>'
                       f'<td>{cells}</td></tr>')
        out.append("</table>")

    # ── 来源
    out.append("<h2>四、这份报告读了哪些文件</h2>")
    out.append("<table><tr><th>层</th><th>目录</th><th>文件</th></tr>")
    for src in bundle["sources"]:
        files = src.get("files") or []
        note = src.get("note") or (", ".join(files) if files else "—")
        out.append(f'<tr><td>{esc(src.get("layer"))}</td>'
                   f'<td class="mono">{esc(src.get("dir"))}</td>'
                   f'<td class="mono">{esc(note)}</td></tr>')
    out.append("</table>")

    out.append('<div class="foot">规则决定能不能交付；知识只是提醒，'
               '从不算通过或失败。<br>本文件自包含，不依赖网络，可直接分发。</div>')
    out.append("</body></html>")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-dir")
    ap.add_argument("--knowledge", action="append", default=[])
    ap.add_argument("--list", action="store_true", help="列出三类条目")
    ap.add_argument("--show", help="看某一条的全文（JSON）")
    ap.add_argument("--html-out", help="导出自包含 HTML 到指定路径")
    ap.add_argument("--title", default="企业知识库")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    explicit = args.knowledge[0] if args.knowledge else None
    bundle = load_all(project_dir=args.project_dir, explicit=explicit)

    if args.html_out:
        path = pathlib.Path(args.html_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_html(bundle, args.title), encoding="utf-8")
        total = sum(len(bundle[k]) for k in ("rules", "knowledge", "parts"))
        print(f"已生成 {path}（{total} 条条目，自包含，可直接分发）")
        return 0

    if args.show:
        target = args.show
        # 器件是按"键"组织的（没有 id 字段），要拿 dict 的键来比
        for key, entry in (bundle["parts"] or {}).items():
            if key == target:
                print(json.dumps(entry, ensure_ascii=False, indent=2))
                return 0
        for kind in ("rules", "knowledge"):
            for item in bundle[kind]:
                if item.get("id") == target:
                    print(json.dumps(item, ensure_ascii=False, indent=2))
                    return 0
        print(f"找不到 id 为 {target!r} 的条目", file=sys.stderr)
        return 2

    # 默认 / --list
    if args.json:
        print(json.dumps({
            "schema": "easycirq-enterprise-kb/v1",
            "rules": bundle["rules"],
            "knowledge": bundle["knowledge"],
            "parts": sorted(bundle["parts"]),
            "problems": bundle["problems"],
            "dead_knowledge": dead_knowledge(bundle["knowledge"]),
            "rules_without_evidence": [r["id"] for r in
                                       rules_without_evidence(bundle["rules"])],
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"一、可执行规则 {len(bundle['rules'])} 条")
    for r in bundle["rules"]:
        flag = "" if r.get("verified_on") else "  ⚠ 未证明会触发"
        print(f"   [{r.get('kind','hard'):8}] {r['id']}  {r.get('title','')}{flag}")
    print(f"\n二、可检索知识 {len(bundle['knowledge'])} 条")
    for k in bundle["knowledge"]:
        why = "" if k.get("why_not_rule") else "  ⚠ 未说明为何不能自动查"
        print(f"   {k['id']}  {k.get('title','')}{why}")
    print(f"\n三、企业器件参数 {len(bundle['parts'])} 条")
    for key in sorted(bundle["parts"]):
        entry = bundle["parts"][key]
        print(f"   {key}  {entry.get('mpn') or entry.get('value') or ''}")

    dead = dead_knowledge(bundle["knowledge"])
    problems = bundle["problems"]
    if dead or problems:
        print("\n⚠ 不会生效的条目：")
        for d in dead:
            print(f"   {d['id']}: {d['reason']}")
        for p in problems:
            print(f"   {p.get('file')}: {p['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
