"""板1 落器件：按功能块批量放置，并把每个失败写进 friction。

产物：reports/hard-board/board1/bom-placed.json（实际落下的器件清单）
      reports/hard-board/board1/place-failures.json（查不到/放不下的）
"""
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path(r"C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method")
OUT = ROOT / "reports" / "hard-board" / "board1"
EXE = pathlib.Path(os.environ["LOCALAPPDATA"]) / "EasyCirq" / "bin" / "easycirq.exe"
PROJECT = "d3e50b4c213d409d8f641a6f484213e9"


def run(args, timeout=600):
    p = subprocess.run([str(EXE)] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    t = (p.stdout or "") + (p.stderr or "")
    i = t.find("{")
    if i < 0:
        return None, t
    try:
        return json.JSONDecoder().raw_decode(t[i:])[0], t
    except Exception:                                        # noqa: BLE001
        return None, t


def search(q, limit=3, want=None):
    d, _ = run(["lib", "search", "--query", q, "--limit", str(limit)])
    comps = ((d or {}).get("result") or {}).get("components") or []
    if want:
        for c in comps:
            blob = " ".join(str(c.get(k) or "") for k in
                            ("name", "description", "value", "manufacturerId")).lower()
            if all(w.lower() in blob for w in want):
                return c
    return comps[0] if comps else None


# (块, 查询, 期望关键字, 位号, 数量, 每行间距)
BOM = [
    ("输入", "USB Type-C 16P", ["type-c"], "J1", 1, 0),
    ("输入", "5.1k 0603", ["5.1k"], "RCC1", 1, 0),
    ("输入", "5.1k 0603", ["5.1k"], "RCC2", 1, 0),
    ("输入", "TVS SMBJ", [], "D_TVS1", 1, 0),
    ("输入", "保险丝 1206", ["保险"], "F1", 1, 0),
    ("输入", "MOSFET P沟道", ["mosfet"], "Q_REV", 1, 0),
    ("Buck5V", "TPS54331", ["tps54331"], "U1", 1, 0),
    ("Buck5V", "电感 10uH", ["电感"], "L1", 1, 0),
    ("Buck5V", "22uF 1206", ["22uf"], "C1", 1, 0),
    ("Buck5V", "22uF 1206", ["22uf"], "C2", 1, 0),
    ("Buck5V", "22uF 1206", ["22uf"], "C3", 1, 0),
    ("Buck5V", "10k 0603", ["10k"], "RFB1", 1, 0),
    ("Buck5V", "3.3k 0603", ["3.3k"], "RFB2", 1, 0),
    ("Buck5V", "100nF 0603", ["100nf"], "CB1", 1, 0),
    ("Buck3V3", "TPS54331", ["tps54331"], "U2", 1, 0),
    ("Buck3V3", "电感 10uH", ["电感"], "L2", 1, 0),
    ("Buck3V3", "22uF 1206", ["22uf"], "C4", 1, 0),
    ("Buck3V3", "22uF 1206", ["22uf"], "C5", 1, 0),
    ("Buck3V3", "10k 0603", ["10k"], "RFB3", 1, 0),
    ("Buck3V3", "6.8k 0603", ["6.8k"], "RFB4", 1, 0),
    ("LDO1V8", "AMS1117 1.8", ["1.8"], "U3", 1, 0),
    ("LDO1V8", "10uF 0805", ["10uf"], "C6", 1, 0),
    ("LDO1V8", "10uF 0805", ["10uf"], "C7", 1, 0),
    ("LDO4V0", "AMS1117 3.3", ["3.3"], "U4", 1, 0),
    ("LDO4V0", "10uF 0805", ["10uf"], "C8", 1, 0),
    ("LDO4V0", "10uF 0805", ["10uf"], "C9", 1, 0),
    ("时序", "100k 0603", ["100k"], "RSEQ1", 1, 0),
    ("时序", "100nF 0603", ["100nf"], "CSEQ1", 1, 0),
    ("时序", "100k 0603", ["100k"], "RSEQ2", 1, 0),
    ("时序", "100nF 0603", ["100nf"], "CSEQ2", 1, 0),
    ("采样", "10k 0603", ["10k"], "RAD1", 1, 0),
    ("采样", "2.2k 0603", ["2.2k"], "RAD2", 1, 0),
    ("采样", "10k 0603", ["10k"], "RAD3", 1, 0),
    ("采样", "3.3k 0603", ["3.3k"], "RAD4", 1, 0),
    ("采样", "100nF 0603", ["100nf"], "CAD1", 1, 0),
    ("采样", "100nF 0603", ["100nf"], "CAD2", 1, 0),
    ("MCU", "STM32F030C8T6", ["stm32f030"], "U5", 1, 0),
    ("MCU", "100nF 0603", ["100nf"], "CD1", 1, 0),
    ("MCU", "100nF 0603", ["100nf"], "CD2", 1, 0),
    ("MCU", "10k 0603", ["10k"], "RRST", 1, 0),
    ("MCU", "100nF 0603", ["100nf"], "CRST", 1, 0),
    ("指示", "LED 0603 red", ["led"], "D1", 1, 0),
    ("指示", "LED 0603 red", ["led"], "D2", 1, 0),
    ("指示", "LED 0603 red", ["led"], "D3", 1, 0),
    ("指示", "LED 0603 red", ["led"], "D4", 1, 0),
    ("指示", "1k 0603", ["1k"], "RL1", 1, 0),
    ("指示", "1k 0603", ["1k"], "RL2", 1, 0),
    ("指示", "1k 0603", ["1k"], "RL3", 1, 0),
    ("指示", "1k 0603", ["1k"], "RL4", 1, 0),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    placed, failed = [], []
    x, y = 100.0, 100.0
    per_row = 0
    cache = {}

    for block, q, want, des, _qty, _ in BOM:
        key = (q, tuple(want))
        if key not in cache:
            cache[key] = search(q, want=want)
        comp = cache[key]
        if not comp:
            failed.append({"block": block, "designator": des, "query": q,
                           "reason": "库查询无结果"})
            print("  查不到 %-10s %s" % (des, q))
            continue

        d, raw = run(["sch", "place", "--project", PROJECT,
                      "--lib", comp["libraryUuid"], "--uuid", comp["uuid"],
                      "--x", str(x), "--y", str(y), "--designator", des])
        ok = bool(d and d.get("ok"))
        if ok:
            placed.append({"block": block, "designator": des,
                           "lcsc": comp.get("lcsc"), "name": comp.get("name"),
                           "x": x, "y": y})
            print("  ✓ %-10s %-22s %s" % (des, comp.get("name"), comp.get("lcsc")))
        else:
            failed.append({"block": block, "designator": des, "query": q,
                           "reason": "放置失败", "raw": raw[:200]})
            print("  ✗ %-10s 放置失败" % des)

        per_row += 1
        x += 40
        if per_row >= 8:
            per_row = 0
            x = 100.0
            y += 60

    (OUT / "bom-placed.json").write_text(
        json.dumps(placed, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "place-failures.json").write_text(
        json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("  落下 %d 个，失败 %d 个" % (len(placed), len(failed)))
    time.sleep(1)
    d, _ = run(["sch", "list", "--project", PROJECT, "--json"])
    comps = ((d or {}).get("result") or {}).get("components") or []
    parts = [c for c in comps if c.get("componentType") == "part"]
    print("  读回器件数（排除图框）:", len(parts))
    return 0 if len(parts) >= 40 else 1


if __name__ == "__main__":
    raise SystemExit(main())
