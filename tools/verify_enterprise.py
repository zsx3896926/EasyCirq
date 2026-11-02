"""企业知识系统的一次完整演练：一条命令跑完 S1–S5，并且**每条都给出生效证据**。

# 为什么要有这个

前面几轮各做了一块：规则加载、人审记录、知识检索、企业器件库。
分散的工具没人跑就等于没有——本目标第 30 轮已经栽过一次
（`pcb_layout` 字段没有任何代码读）。

所以这里不是"列出数量"，而是**每条资产都跑一次正反例**：

| 资产 | 怎么证明它活着 |
|---|---|
| 规则 | 造一块违规板 → 必须 fail；干净板 → 必须 pass |
| 知识 | 给一个相关上下文 → 必须召回；给一个无关上下文 → 不许召回 |
| 器件实测值 | 意图不写该参数 → 判据输出里必须出现企业实测值且标出来源 |

**只报"加载了 3 条"是不算数的。**
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
KNOW = ROOT / "examples" / "enterprise-knowledge"


def run(script, args, env=None):
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, cwd=str(ROOT), env=e)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def mark(ok):
    return "✓" if ok else "✗"


def section(title):
    print()
    print(f"── {title} " + "─" * max(0, 60 - len(title)))


def main():
    steps = []

    # ── 1. 规则：加载 + 正反例
    section("S1/S3 企业规则")
    rc, out = run("enterprise_rules.py",
                  ["--describe", "--rule", str(KNOW / "rules.company.json")])
    loaded = "加载 3 条" in out
    print(f"  {mark(loaded)} 加载：{'3 条' if loaded else '失败'}")
    steps.append(loaded)

    bad = ROOT / "reports/fan-controller/evidence/21-enterprise-violations.json"
    clean = ROOT / "deliverables/fan-controller/snapshot/list.json"
    rc_bad, out_bad = run("enterprise_rules.py",
                          ["--netlist", str(bad),
                           "--rule", str(KNOW / "rules.company.json")])
    rc_ok, out_ok = run("enterprise_rules.py",
                        ["--netlist", str(clean),
                         "--rule", str(KNOW / "rules.company.json")])
    blocked = rc_bad == 1 and "no-0402-packaging" in out_bad
    allowed = rc_ok == 0
    print(f"  {mark(blocked)} 故意违规板 → 必须拦住（实际 exit={rc_bad}）")
    print(f"  {mark(allowed)} 干净板 → 必须放行（实际 exit={rc_ok}）")
    steps.extend([blocked, allowed])

    # ── 2. 知识：检索 + 正反例
    section("S4 企业知识检索")
    ledger = KNOW / "review-ledger.example.json"
    it = ROOT / "deliverables/fan-controller/design/intent.json"
    rc, out = run("knowledge_search.py",
                  ["--netlist", str(clean), "--intent", str(it),
                   "--knowledge", str(ledger), "--json"])
    report = json.loads(out[out.find("{"):]) if "{" in out else {}
    hits = report.get("hits") or []
    recalled = any(h["id"] == "R-2026-11-02-002" for h in hits)
    explained = all(h.get("matched_on") for h in hits)
    print(f"  {mark(recalled)} 相关的被召回："
          f"{[h['id'] for h in hits] or '（无）'}")
    print(f"  {mark(explained)} 每条召回都说得出命中什么")
    steps.extend([recalled, explained])

    # 反例：造一块只有数字相关的板，不许召回连接器那条
    with tempfile.TemporaryDirectory() as tmp:
        noise = pathlib.Path(tmp) / "noise.json"
        noise.write_text(json.dumps({"components": [
            {"designator": "R1", "componentType": "part",
             "footprintRef": {"name": "R0603"},
             "pins": [{"pinNumber": "1", "net": "NET54"},
                      {"pinNumber": "2", "net": "GND"}]}]}, ensure_ascii=False),
            encoding="utf-8")
        rc, out = run("knowledge_search.py",
                      ["--netlist", str(noise), "--knowledge", str(ledger),
                       "--json"])
        rep = json.loads(out[out.find("{"):])
        no_noise = not any("R-2026-11-02-003" in json.dumps(h)
                           for h in rep.get("hits") or [])
        print(f"  {mark(no_noise)} 无关上下文不误召回（数字噪声）")
        steps.append(no_noise)

    # ── 3. 器件实测值：判据真的用上
    section("S5 企业器件库")
    rc, out = run("enterprise_parts.py",
                  ["--parts", str(KNOW / "parts.company.json"),
                   "--resolve", "mosfet.ao3400a_sot23", "--json"])
    rep = json.loads(out[out.find("{"):]) if "{" in out else {}
    has_measured = (rep.get("effective") or {}).get("measured", {}).get("vgs_th") == 1.3
    provenance = (rep.get("origin") or {}).get("measured") != "builtin"
    print(f"  {mark(has_measured)} 实测 vgs_th=1.3 在有效参数里")

    with tempfile.TemporaryDirectory() as tmp:
        intent = json.loads(it.read_text(encoding="utf-8"))
        sw = intent["switches"][0]
        sw.pop("vgs_th", None)
        sw["part_key"] = "mosfet.ao3400a_sot23"
        ip = pathlib.Path(tmp) / "intent.json"
        ip.write_text(json.dumps(intent, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        rc, out = run("sch_design_validity.py",
                      ["--netlist", str(clean), "--intent", str(ip),
                       "--enterprise-parts", str(KNOW / "parts.company.json")])
    used = '"vgs_th": 1.3' in out and "企业实测" in out
    print(f"  {mark(used)} 意图不写该参数时，判据用企业实测值并标出来源")
    steps.extend([has_measured, provenance, used])

    # ── 4. 人审 → 推进 → 下次生效
    section("S2 人审记录闭环")
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "knowledge"
        rc, out = run("review_ledger.py",
                      ["--ledger", str(ledger), "--verify"])
        valid = rc == 0 and "全部合格" in out
        rc2, out2 = run("review_ledger.py",
                        ["--ledger", str(ledger), "--promote",
                         "--target", str(target)])
        written = rc2 == 0 and "回读确认" in out2
        # 推进后不加参数，违规板必须被拦住
        board = pathlib.Path(tmp) / "bad.json"
        board.write_text(json.dumps({"components": [
            {"designator": "R1", "componentType": "part",
             "footprintRef": {"name": "R0402"},
             "pins": [{"pinNumber": "1", "net": "A"},
                      {"pinNumber": "2", "net": "B"}]}]}, ensure_ascii=False),
            encoding="utf-8")
        rc3, out3 = run("enterprise_rules.py", ["--netlist", str(board)],
                        env={"EASYCIRQ_KNOWLEDGE_DIR": str(target)})
        effective = rc3 == 1
        print(f"  {mark(valid)} 记录校验（选边 + verified_on）")
        print(f"  {mark(written)} 推进并回读确认加载")
        print(f"  {mark(effective)} **不加任何参数**，下一块违规板被拦住"
              f"（实际 exit={rc3}）")
        steps.extend([valid, written, effective])

    # ── 5. 审阅报告：把规则/知识合成给人看的一份结论
    section("审阅报告（终态：能指出违反贵司规范）")
    rc, out = run("enterprise_review.py",
                  ["--netlist", str(clean), "--intent", str(it),
                   "--label", "Fan-Controller-12V"],
                  env={"EASYCIRQ_KNOWLEDGE_DIR": str(KNOW)})
    cites = "命中：" in out and "来源：" in out
    clean_verdict = "没有违反已知的企业规范" in out
    print(f"  {mark(cites)} 引用了具体的知识条目并说出命中什么")
    print(f"  {mark(clean_verdict)} 干净板结论明确")

    # 造一块真违规板：必须给出违反项 + 依据 + 找谁
    with tempfile.TemporaryDirectory() as tmp2:
        bad2 = json.loads(clean.read_text(encoding="utf-8"))
        root2 = bad2.get("result") or bad2
        for comp in root2.get("components") or []:
            if comp.get("designator") == "R1":
                comp["footprintRef"] = {"name": "R0402"}
        bp = pathlib.Path(tmp2) / "bad2.json"
        bp.write_text(json.dumps(root2, ensure_ascii=False), encoding="utf-8")
        rc2, out2 = run("enterprise_review.py",
                        ["--netlist", str(bp), "--intent", str(it)],
                        env={"EASYCIRQ_KNOWLEDGE_DIR": str(KNOW)})
    blocked_review = (rc2 == 1 and "违反企业规范" in out2
                      and "依据：" in out2 and "找谁：" in out2)
    print(f"  {mark(blocked_review)} 违规板：说违反、给依据、给找人")
    steps.extend([cites, clean_verdict, blocked_review])

    # ── 汇总
    print()
    print("=" * 64)
    ok = sum(1 for s in steps if s)
    print(f"生效验证：{ok}/{len(steps)} 项通过")
    if ok == len(steps):
        print("企业知识系统闭环成立：规则能拦、知识能检索、实测值能用、人审能沉淀。")
        return 0
    print("有项目没通过，不能算闭环成立。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
