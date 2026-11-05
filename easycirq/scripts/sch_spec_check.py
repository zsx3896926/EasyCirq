#!/usr/bin/env python3
"""S1 规格自检：把「端口名打错」「绑到不存在的轨」这类错误当场抓出来。

为什么需要它：S1 的 spec.json 是后四阶段的输入。里面一个端口名写错，
S2 的 style-plan 会照着错的名字排线，S5 落到画布上才暴露 —— 那时已经
很难判断是"规划错"还是"落图错"。所以 S1 必须自己能验。

判据全部来自**块库真实数据**（runtime/internal/blocks/data/<id>.json），
不信任 spec 里的自述。

退出码：0 = 通过；1 = 有问题（逐条列出）。
"""
import argparse
import json
import pathlib
import sys


def load_block(blocks_dir: pathlib.Path, block_id: str):
    name = block_id
    if name.startswith("block."):
        name = name[len("block."):]
    p = blocks_dir / (name + ".json")
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def check(spec_path: pathlib.Path, blocks_dir: pathlib.Path, audit=None):
    problems = []
    notes = []

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not spec.get("schema"):
        problems.append("spec 缺少 schema 字段")
    if not spec.get("projectUuid"):
        problems.append("spec 缺少 projectUuid —— 后四阶段靠它定位工程")

    modules = spec.get("modules") or []
    if not modules:
        problems.append("spec 里没有任何 module")

    rails = set(((spec.get("power_tree") or {}).get("rails") or {}).keys())
    rails.add("GND")  # 地网不必在 rails 表里单列

    # ── 逐个模块：块存在、端口真实、绑定目标存在 ────────────────────────
    for m in modules:
        mid = m.get("id") or "?"
        bid = m.get("block") or ""
        blk = load_block(blocks_dir, bid)
        if blk is None:
            problems.append("%s: 块 %r 在块库里不存在" % (mid, bid))
            continue

        real_ports = blk.get("ports") or {}
        spec_ports = m.get("ports") or {}
        if not spec_ports:
            problems.append("%s: 没有声明任何 port" % mid)
        for pname, pspec in spec_ports.items():
            if pname not in real_ports:
                problems.append(
                    "%s: 端口 %r 在块 %s 里不存在（真实端口：%s）"
                    % (mid, pname, bid, ", ".join(sorted(real_ports)) or "无"))
                continue
            bind = (pspec or {}).get("bind_to")
            if bind is None:
                # 允许不绑，但必须写明理由（NC 或 note）
                if not ((pspec or {}).get("nc") or (pspec or {}).get("note")):
                    problems.append("%s: 端口 %r 没有 bind_to，也没写理由" % (mid, pname))
                continue
            if bind not in rails:
                problems.append(
                    "%s: 端口 %r 绑到 %r，但电源树里没有这张网"
                    % (mid, pname, bind))

        # 器件数：spec 可以少写，但不能和块库对不上（对不上说明记错了块）
        claimed = m.get("parts")
        real_parts = len(blk.get("parts") or [])
        if claimed is not None and claimed != real_parts:
            problems.append(
                "%s: spec 写 %s 个器件，块库里 %s 个 —— 记错了块？"
                % (mid, claimed, real_parts))

    # ── 电源树：每条边的两端都要有落点 ──────────────────────────────────
    tree = spec.get("power_tree") or {}
    for e in tree.get("edges") or []:
        for side in ("from", "to"):
            r = e.get(side)
            if not r:
                problems.append("电源树有一条边缺 %s 字段" % side)
            elif r not in rails:
                problems.append("电源树边引用了不存在的网 %r" % r)

    # ── 跨页网：必须是电源树里有的，或者是 GND ──────────────────────────
    for n in (spec.get("cross_page_nets") or {}).get("nets") or []:
        if n not in rails:
            problems.append("跨页网 %r 不在电源树里 —— 跨页会连不上" % n)

    # ── NC：必须指向真实存在的模块端口 ────────────────────────────────
    mod_ports = {}
    for m in modules:
        for pname in (m.get("ports") or {}):
            mod_ports["%s:%s" % (m.get("id"), pname)] = True
    for nc in spec.get("nc") or []:
        pin = nc.get("pin") or ""
        if pin not in mod_ports:
            problems.append("NC %s 指向 %r，但那不是任何模块声明的端口"
                            % (nc.get("id") or "?", pin))
        if not nc.get("reason"):
            problems.append("NC %s 没写理由 —— 不接也要说清为什么不接"
                            % (nc.get("id") or "?"))
        # **要么接、要么不接，不能两头都写。**
        # 实测踩过：spec 把 M4:EN 列进 nc，同时又在模块里 bind_to=+5V，
        # 于是网表里它是接的、NC 清单里它是不接的，两边都"有据"。
        if pin in mod_ports:
            mid, pname = pin.split(":", 1)
            for m in modules:
                if m.get("id") != mid:
                    continue
                bind = ((m.get("ports") or {}).get(pname) or {}).get("bind_to")
                if bind:
                    problems.append(
                        "NC %s 说 %r 不接，但模块里它 bind_to=%r —— 二者只能取一"
                        % (nc.get("id") or "?", pin, bind))

    # ── 分页：每页的模块都必须存在 ────────────────────────────────────
    ids = {m.get("id") for m in modules}
    for page, plan in (spec.get("page_plan") or {}).items():
        for mid in (plan.get("modules") or []):
            if mid not in ids:
                problems.append("page_plan %s 引用了不存在的模块 %r" % (page, mid))

    # ── 选型可用性（**前置指标**）────────────────────────────────────
    #
    # friction #42/#45：板2 按电气参数选了 AP40P05，它的库记录读不出来，
    # 一路走到 S3 要引脚几何时才炸，前面几轮全部作废。
    # **"查得到"是选型条件，不是 S3 的惊喜。**
    if audit:
        try:
            ap = json.loads(pathlib.Path(audit).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append("读不到选型审计报告 %s：%s" % (audit, exc))
        else:
            # 旧报告不能当新证据用：标准件表改过之后，报告里的 unreadable
            # 可能早就不成立了。指纹对不上就如实说"报告过期"，而不是照信。
            import hashlib
            sp_path = pathlib.Path("easycirq/references/standard-parts.json")
            stamped = ap.get("standardPartsSha256")
            if sp_path.is_file() and stamped:
                now = hashlib.sha256(sp_path.read_bytes()).hexdigest()
                if now != stamped:
                    problems.append(
                        "选型审计报告已过期（标准件表在审计之后改过）—— "
                        "重跑 sch_part_audit.py 再用")
            elif not stamped:
                notes.append("选型审计报告没有指纹，无法判断是否过期 —— 建议重跑")
            status_of = {k: (v or {}).get("status")
                         for k, v in (ap.get("parts") or {}).items()}
            used = set()
            for m in modules:
                blk = load_block(blocks_dir, m.get("block") or "")
                if blk:
                    for pspec in (blk.get("parts") or {}).values():
                        pid = (pspec or {}).get("part")
                        if pid:
                            used.add(pid)
            bad = sorted((pid, status_of.get(pid))
                         for pid in used if status_of.get(pid) != "ok")
            for pid, st in bad:
                problems.append(
                    "选型不可用：%s 的库记录状态为 %r —— 走到 S3 要几何时会炸，"
                    "现在换料比那时便宜" % (pid, st or "未审计"))
            notes.append("选型审计：本 spec 用到 %d 个型号，其中 %d 个不可用"
                         % (len(used), len(bad)))

    # ── 门槛自检（只提示，不阻断：门槛是目标，不是 S1 的产物）───────────
    req = spec.get("requirements") or {}
    total_parts = sum(len((load_block(blocks_dir, m.get("block") or "") or {}).get("parts") or [])
                      for m in modules)
    notes.append("spec 声明的模块合计 %d 个器件（块库实读）" % total_parts)
    min_parts = ((req.get("parts") or {}).get("min"))
    if min_parts and total_parts < min_parts:
        notes.append("⚠ 距器件门槛 %d 还差 %d —— 这不是 S1 的错误，是模块还没选够"
                     % (min_parts, min_parts - total_parts))

    return problems, notes


def main():
    ap = argparse.ArgumentParser(description="S1 spec.json 自检")
    ap.add_argument("spec", help="spec.json 路径")
    ap.add_argument("--blocks-dir",
                    default="runtime/internal/blocks/data",
                    help="块库数据目录")
    ap.add_argument("--audit",
                    help="选型可用性审计报告（sch_part_audit.py 产物）；给了就要求"
                         "本 spec 用到的每个器件都 ok")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    spec_path = pathlib.Path(args.spec)
    blocks_dir = pathlib.Path(args.blocks_dir)
    if not spec_path.is_file():
        print("找不到 spec：%s" % spec_path, file=sys.stderr)
        return 1
    if not blocks_dir.is_dir():
        print("找不到块库目录：%s" % blocks_dir, file=sys.stderr)
        return 1

    problems, notes = check(spec_path, blocks_dir, audit=args.audit)
    verdict = "pass" if not problems else "fail"

    if args.json:
        print(json.dumps({"verdict": verdict, "problems": problems, "notes": notes},
                         ensure_ascii=False, indent=2))
    else:
        print("S1 规格自检：%s" % verdict)
        for p in problems:
            print("  ✗ %s" % p)
        for n in notes:
            print("  · %s" % n)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
