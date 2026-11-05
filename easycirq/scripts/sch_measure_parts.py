#!/usr/bin/env python3
"""批量量出网表里每个器件的引脚几何 —— 离线度量，为 `sch lib-layout` 准备 measurements。

链路（每件一次，带缓存）：

    网表里的 part id
      → standard-parts.json 的 lcsc C 号
      → `easycirq lib by-lcsc --lcsc ...`        拿 libraryUuid + deviceUuid
      → `easycirq lib device get`                 拿 symbolUuid
      → `easycirq lib symbol export-source`       导出 .elibz2
      → 解析 ProLib_*.elibu                       拿引脚名/坐标/长度/旋转

**为什么这条链不破坏『未过 S2 不得进器件』**：以上全是**只读**。
读库不等于往画布上放器件。

缓存：导出件落在 `--cache-dir`（默认 `.easycirq/symbol-cache`），
命中就不重复请求 —— 否则每次跑都要几十次往返。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import zipfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sch_symbol_measure as measure  # noqa: E402


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


def load_standard_parts(path: pathlib.Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("parts") or d


def resolve_identities(exe: str, parts: dict, ids: list[str]):
    """part id → (libraryUuid, deviceUuid, lcsc)。按 C 号批量查一次。"""
    lcsc_of: dict[str, str] = {}
    for pid in ids:
        entry = parts.get(pid) or {}
        lcsc = (entry.get("lcsc") or "").strip()
        if lcsc:
            lcsc_of[pid] = lcsc
    if not lcsc_of:
        return {}, {}, {}

    nums = sorted(set(lcsc_of.values()))
    out, text = cli_json(exe, ["lib", "by-lcsc", "--lcsc", ",".join(nums)],
                         timeout=300)
    if out is None:
        return {}, lcsc_of, {"error": "by-lcsc 失败：" + text[:200]}

    by_lcsc = {}
    for c in out.get("components") or []:
        by_lcsc[(c.get("lcsc") or "").upper()] = c

    lib_of, dev_of = {}, {}
    for pid, lcsc in lcsc_of.items():
        c = by_lcsc.get(lcsc.upper())
        if c:
            lib_of[pid] = c.get("libraryUuid") or ""
            dev_of[pid] = c.get("uuid") or ""
    return lib_of, dev_of, lcsc_of


def symbol_uuid_of(exe: str, library: str, device: str):
    out, _ = cli_json(exe, ["lib", "device", "get",
                            "--library", library, "--uuid", device])
    if out is None:
        return None
    assoc = ((out.get("result") or {}).get("device") or {}).get("association") or {}
    return assoc.get("symbolUuid") or ((assoc.get("symbol") or {}).get("uuid"))


def export_symbol(exe: str, library: str, symbol: str, dest: pathlib.Path):
    """导出（命中缓存就直接用）。"""
    if dest.is_file() and dest.stat().st_size > 0:
        return "cache"
    dest.parent.mkdir(parents=True, exist_ok=True)
    cli_json(exe, ["lib", "symbol", "export-source",
                   "--library", library, "--uuid", symbol,
                   "--out", str(dest)], timeout=300)
    return "fetched" if dest.is_file() else "failed"


def read_archive(path: pathlib.Path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    elibu = [n for n in names if n.endswith(".elibu")]
    if not elibu:
        return None, "档案里没有 .elibu（只有 %r）" % names
    text = z.read(elibu[0]).decode("utf-8", errors="replace")
    return measure.parse_elibu(text), ""


def main() -> int:
    ap = argparse.ArgumentParser(description="批量测量器件引脚几何")
    ap.add_argument("--netlist", required=True)
    ap.add_argument("--standard-parts",
                    default="easycirq/references/standard-parts.json")
    ap.add_argument("--cache-dir", default=".easycirq/symbol-cache")
    ap.add_argument("--out", required=True)
    ap.add_argument("--exe", default=None, help="easycirq 可执行文件路径")
    ap.add_argument("--limit", type=int, default=0, help="只量前 N 个型号（调试用）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    exe = args.exe or str(
        pathlib.Path(__import__("os").environ.get("LOCALAPPDATA", ""))
        / "EasyCirq" / "bin" / "easycirq.exe")
    cache = pathlib.Path(args.cache_dir)

    netlist = json.loads(pathlib.Path(args.netlist).read_text(encoding="utf-8"))
    ids = sorted({c["device"]["name"] for c in netlist["components"] if c["device"].get("name")})
    if args.limit:
        ids = ids[:args.limit]

    parts = load_standard_parts(pathlib.Path(args.standard_parts))
    lib_of, dev_of, lcsc_of = resolve_identities(exe, parts, ids)

    results, problems = {}, []
    stats = {"cache": 0, "fetched": 0, "failed": 0}

    for n, pid in enumerate(ids, 1):
        lib = lib_of.get(pid)
        dev = dev_of.get(pid)
        if not lib or not dev:
            problems.append("%s: 拿不到 device 身份（C 号 %r）" % (pid, lcsc_of.get(pid)))
            stats["failed"] += 1
            continue
        sym = symbol_uuid_of(exe, lib, dev)
        if not sym:
            problems.append("%s: 拿不到 symbolUuid" % pid)
            stats["failed"] += 1
            continue
        dest = cache / ("%s_%s.elibz2" % (pid.replace(".", "_"), sym[:8]))
        how = export_symbol(exe, lib, sym, dest)
        stats[how] = stats.get(how, 0) + 1
        if how == "failed":
            problems.append("%s: 导出失败" % pid)
            continue
        parsed, err = read_archive(dest)
        if parsed is None:
            problems.append("%s: %s" % (pid, err))
            continue
        pins, shapes, _ = parsed
        # 同名引脚（比如 4 个 GND）要能分开，否则几何会互相覆盖。
        # 块库用 `GND*` 表示"其中一个地脚"，这里用 `GND#1..#4` 与之一一对应。
        seen: dict[str, int] = {}
        pin_map: dict[str, dict] = {}
        for _pid, p in sorted(pins.items(), key=lambda kv: kv[1].get("name") or ""):
            name = p.get("name") or _pid
            seen[name] = seen.get(name, 0) + 1
            key = name if seen[name] == 1 else "%s#%d" % (name, seen[name])
            pin_map[key] = {
                "x": p.get("x"), "y": p.get("y"),
                "length": p.get("length"), "rotation": p.get("rotation"),
                "connectionPoint": measure.connection_point(p),
            }
        results[pid] = {
            "libraryUuid": lib, "deviceUuid": dev, "symbolUuid": sym,
            "lcsc": lcsc_of.get(pid, ""),
            "archive": str(dest),
            "pins": pin_map,
            "pinCount": len(pins),
        }

    doc = {
        "schema": "easycirq-sch-measurements/v1",
        "netlist": args.netlist,
        "parts": results,
        "stats": stats,
        "problems": problems,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"out": str(out), "stats": stats,
                          "measured": len(results), "problems": problems},
                         ensure_ascii=False, indent=2))
    else:
        print("器件几何 → %s" % out)
        print("  型号 %d 个：命中缓存 %d，新取 %d，失败 %d"
              % (len(ids), stats.get("cache", 0), stats.get("fetched", 0),
                 stats.get("failed", 0)))
        print("  量出引脚几何的型号：%d" % len(results))
        for p in problems[:10]:
            print("  ✗ %s" % p)
        if len(problems) > 10:
            print("  … 还有 %d 条" % (len(problems) - 10))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
