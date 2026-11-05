"""板2：在 P1 的空白上半区加块（隔离 / RS485 / 监测），逐块查门。

P1 现有器件只占 y=380..580，上半区 y<380 是空的 —— 那里能放 2-3 块。
每落一块立刻查器件数与门；落不下就换位置，不硬来。
"""
import json
import os
import pathlib
import subprocess
import time

EXE = pathlib.Path(os.environ["LOCALAPPDATA"]) / "EasyCirq" / "bin" / "easycirq.exe"
PROJ = "23ce6e4eb178464cb0b709920da3b26c"
PAGE = "49c6dbb9567dd6af"

CANDIDATES = [
    ("block.sp3485_rs485_halfduplex", [(120, 120), (600, 120)]),
    ("block.i2c_isolation_2n7002dw", [(120, 250), (600, 250)]),
    ("block.opto_acc_ign_detect", [(600, 250), (120, 250)]),
]


def run(args, timeout=1500):
    p = subprocess.run([str(EXE)] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


def stats():
    out = run(["sch", "list", "--project", PROJ, "--json", "--include-pins", "--page", PAGE])
    i = out.find("{")
    if i < 0:
        return 0, 0, 0
    try:
        d = json.JSONDecoder().raw_decode(out[i:])[0]
    except Exception:                                        # noqa: BLE001
        return 0, 0, 0
    cs = [c for c in (d.get("result") or {}).get("components") or []
          if c.get("componentType") == "part"]
    w = sum(1 for c in cs for q in (c.get("pins") or []) if (q.get("net") or "").strip())
    nets = {q.get("net").strip() for c in cs for q in (c.get("pins") or [])
            if (q.get("net") or "").strip()}
    return len(cs), w, len(nets)


for blk, spots in CANDIDATES:
    before = stats()
    landed = False
    for (x, y) in spots:
        out = run(["sch", "block-apply", blk, "--project", PROJ, "--doc", PAGE,
                   "--at", "%d,%d" % (x, y), "--json"])
        time.sleep(2)
        after = stats()
        if after[0] > before[0]:
            print("  %-32s @(%4d,%4d) ✅ 器件 %d→%d 网络 %d→%d"
                  % (blk.replace("block.", ""), x, y, before[0], after[0], before[2], after[2]))
            landed = True
            break
        reason = ""
        for line in out.splitlines():
            if "warn:" in line or "failure:" in line or "stopped" in line:
                reason = line.strip()[:110]
                break
        print("  %-32s @(%4d,%4d) ✗ %s" % (blk.replace("block.", ""), x, y, reason))
    if not landed:
        print("     （两个位置都不行，跳过）")

time.sleep(2)
n, w, nets = stats()
print("\n  P1 现在: 器件=%d 已连=%d 网络=%d" % (n, w, nets))
g = run(["sch", "gate", "--project", PROJ])
for line in g.splitlines()[:6]:
    print("  " + line.strip()[:130])
