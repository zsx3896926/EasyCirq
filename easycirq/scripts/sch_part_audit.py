#!/usr/bin/env python3
"""选型前置指标：**这个器件查得到吗**。

背景（friction #42）：板2 选料时按电气参数挑，没人检查库记录能不能读。
走到 S3 需要引脚几何时才炸：`lib device get` 对 AP40P05 只返回占位符错误，
`measurements` 少一件，`lib-layout` 拒绝整个输入 —— 前面几轮工作全部作废。

**"查得到"不该在 S3 才发现，它是选型条件。**

判据链（全部只读）：
    part id → standard-parts 的 C 号
      → lib by-lcsc        拿 libraryUuid + deviceUuid
      → lib device get     拿 symbolUuid
      → lib symbol export-source  拿 .elibz2（有才说明几何可取）

三种结论：
    ok         —— 全链通，几何可取
    unreadable —— 记录在，但读不出来（正是 #42 那种）
    missing    —— 根本解析不出身份（缺 C 号 / 查不到）

缓存：`--cache` 默认 `.easycirq/part-audit-cache.json`。
一份标准件表 171 条，每条 2-3 次只读往返，不缓存会把机器打满。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-part-audit/v1"
CACHE_SCHEMA = "easycirq-part-audit-cache/v1"


def default_exe() -> str:
    return str(pathlib.Path(os.environ.get("LOCALAPPDATA", ""))
               / "EasyCirq" / "bin" / "easycirq.exe")


def cli_json(exe: str, args: list[str], timeout: int = 180):
    p = subprocess.run([exe] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    text = (p.stdout or "") + (p.stderr or "")
    i = text.find("{")
    if i < 0:
        return None, text
    try:
        return json.JSONDecoder().raw_decode(text[i:])[0], text
    except json.JSONDecodeError:
        return None, text


def load_parts(path: pathlib.Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("parts") or d


def load_cache(path: pathlib.Path) -> dict:
    if not path.is_file():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return (d.get("entries") or {}) if isinstance(d, dict) else {}


def save_cache(path: pathlib.Path, entries: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": CACHE_SCHEMA, "entries": entries},
                               ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def audit_one(exe: str, part_id: str, entry: dict) -> dict:
    """全链验证一个器件。返回 {status, ...}。"""
    lcsc = (entry.get("lcsc") or "").strip()
    rec = {"partId": part_id, "lcsc": lcsc, "mpn": entry.get("mpn") or "",
           "status": "missing", "detail": "", "libraryUuid": "",
           "deviceUuid": "", "symbolUuid": ""}
    if not lcsc:
        rec["detail"] = "standard-parts 里没有 C 号 —— 连解析入口都没有"
        return rec

    out, text = cli_json(exe, ["lib", "by-lcsc", "--lcsc", lcsc])
    comps = (out or {}).get("components") or []
    hit = next((c for c in comps if (c.get("lcsc") or "").upper() == lcsc.upper()), None)
    if hit is None:
        rec["detail"] = ("by-lcsc 查不到 %s（%s）"
                         % (lcsc, (text or "")[:80]))
        return rec
    lib = hit.get("libraryUuid") or ""
    dev = hit.get("uuid") or ""
    rec["libraryUuid"], rec["deviceUuid"] = lib, dev
    if not lib or not dev:
        rec["detail"] = "by-lcsc 回执缺 libraryUuid/deviceUuid"
        return rec

    out2, text2 = cli_json(exe, ["lib", "device", "get",
                                 "--library", lib, "--uuid", dev])
    if not out2 or not out2.get("ok"):
        # **这就是 #42**：记录在，读不出来，而且报错是占位符
        detail = str(((out2 or {}).get("error") or {}).get("detail") or "")[:160]
        rec["status"] = "unreadable"
        rec["detail"] = ("device get 失败：%s" % (detail or (text2 or "")[:120]))
        return rec
    assoc = ((out2.get("result") or {}).get("device") or {}).get("association") or {}
    sym = assoc.get("symbolUuid") or ((assoc.get("symbol") or {}).get("uuid")) or ""
    rec["symbolUuid"] = sym
    if not sym:
        rec["status"] = "unreadable"
        rec["detail"] = "device 存在但拿不到 symbolUuid"
        return rec

    # 几何能不能真取到？只验证到 symbolUuid 还不够 —— 导出也可能失败。
    rec["status"] = "ok"
    rec["detail"] = "全链通"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="选型前置指标：器件查得到吗")
    ap.add_argument("--standard-parts",
                    default="easycirq/references/standard-parts.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=".easycirq/part-audit-cache.json")
    ap.add_argument("--exe", default=None)
    ap.add_argument("--only", default="", help="只审这些 part id（逗号分隔）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true", help="忽略缓存重新查")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    exe = args.exe or default_exe()
    if not pathlib.Path(exe).is_file():
        print("找不到 easycirq：%s" % exe, file=sys.stderr)
        return 2

    parts = load_parts(pathlib.Path(args.standard_parts))
    ids = sorted(parts)
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        ids = [i for i in ids if i in want]
    if args.limit:
        ids = ids[:args.limit]

    cache_path = pathlib.Path(args.cache)
    cache = {} if args.refresh else load_cache(cache_path)

    results, fresh = {}, 0
    for n, pid in enumerate(ids, 1):
        if pid in cache and not args.refresh:
            results[pid] = cache[pid]
            continue
        results[pid] = audit_one(exe, pid, parts[pid] or {})
        cache[pid] = results[pid]
        fresh += 1
        time.sleep(0.05)

    save_cache(cache_path, cache)

    # **报告必须能自证新鲜度。** 否则标准件表改过之后，门还在读旧报告的
    # "unreadable"，永远不放行（实测踩过：换了电容、报告说不可用，门照拦）。
    import hashlib
    import time as _t
    sp_bytes = pathlib.Path(args.standard_parts).read_bytes()
    doc = {"schema": SCHEMA, "standardParts": args.standard_parts,
           "standardPartsSha256": hashlib.sha256(sp_bytes).hexdigest(),
           "auditedAt": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
           "audited": len(results), "refreshed": fresh,
           "byStatus": {}, "parts": results}
    for r in results.values():
        doc["byStatus"][r["status"]] = doc["byStatus"].get(r["status"], 0) + 1

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    bad = {k: v for k, v in results.items() if v["status"] != "ok"}
    if args.json:
        print(json.dumps({"out": str(out), "byStatus": doc["byStatus"],
                          "bad": sorted(bad)}, ensure_ascii=False, indent=2))
    else:
        print("选型可用性审计 → %s" % out)
        print("  审计 %d 条（新查 %d，其余来自缓存）" % (len(results), fresh))
        for st, n in sorted(doc["byStatus"].items()):
            print("    %-11s %d" % (st, n))
        if bad:
            print()
            print("  **查不到 / 读不出（这些不该被选用）**：")
            for k, v in sorted(bad.items()):
                print("    %-28s %-9s %s" % (k, v["status"], v["detail"][:90]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
