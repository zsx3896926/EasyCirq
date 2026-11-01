"""给 R5 找一个不打架的落点：遍历候选位置，各自布线 + DRC，取违规最少的。

为什么不手工试：
  前两次手选 (320,-1085) 得 11 处、auto-place 到 (667.8,-544.7) 得 6 处、
  再改到 (540,-1095) 得 8 处。**每挪一次都要重布线才看得出真实结果**，
  靠眼看着图纸猜位置，既慢又不可靠。
  这个脚本把「移动 → 布线 → DRC → 计数」变成可比较的实验。
"""
import json
import os
import subprocess
import sys

PROJECT = "KPI-S5-Verify"
PCB = "PCB1"
TEMP = os.environ["TEMP"]

# 板框：x 183.8..941.1, y -1177.4..-332.2；底部一排器件在 y≈-1028，
# U1 在 -784，所以 -880 ～ -960 这一带是相对空的中间区域。
# R5 连 BASE（Q1 基极，约 480,-1033）和 PWR5V（U1 的 VDD，约 558,-784）。
# 理想落点是这两点之间，让两段线都短。这里只扫这条走廊。
CANDIDATES = [
    (500.0, -900.0),
    (500.0, -950.0),
    (450.0, -880.0),
    (540.0, -880.0),
    (620.0, -900.0),
    (430.0, -950.0),
]


def run(*args, **kwargs):
    return subprocess.run(list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1800, **kwargs)


def r5_id():
    out = os.path.join(TEMP, "scan-pcb.json")
    run("easycirq", "--project", PROJECT, "--doc", PCB, "pcb", "dump", "--out", out)
    data = json.load(open(out, encoding="utf-8"))
    root = data.get("result") or data
    for comp in root.get("components") or []:
        if comp.get("designator") == "R5":
            return comp.get("primitiveId")
    return None


def drc_count():
    out = os.path.join(TEMP, "scan-drc.json")
    proc = run("easycirq", "--project", PROJECT, "--doc", PCB, "pcb", "drc", "--json")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(proc.stdout or "")
    parsed = run(sys.executable, "tools/read_drc.py", out)
    first = (parsed.stdout or "").strip().splitlines()[:1]
    line = first[0] if first else "passed: ? total: ?"
    try:
        total = int(line.split("total:")[1].strip())
    except (IndexError, ValueError):
        total = 999
    return total, "\n".join((parsed.stdout or "").strip().splitlines()[:4])


def main():
    target = r5_id()
    if not target:
        print("找不到 R5")
        return 3
    print(f"R5 primitiveId = {target}\n")

    best = None
    for x, y in CANDIDATES:
        moved = run("easycirq", "--project", PROJECT, "--doc", PCB, "pcb", "modify",
                    "--id", target, "--x", str(x), "--y", str(y), "--center")
        if '"ok": true' not in (moved.stdout or ""):
            print(f"({x},{y}) 移动失败，跳过")
            continue
        run("easycirq", "--project", PROJECT, "--doc", PCB, "pcb", "autoroute")
        total, detail = drc_count()
        print(f"({x:>6.0f},{y:>7.0f})  DRC violations: {total}")
        if best is None or total < best[2]:
            best = ((x, y), detail, total)

    print()
    if best is None:
        print("所有候选都失败")
        return 1
    (x, y), detail, total = best
    print(f"最佳落点：({x:.0f}, {y:.0f})，违规 {total} 处")
    print(detail)
    # leave the board at the best position
    run("easycirq", "--project", PROJECT, "--doc", PCB, "pcb", "modify",
        "--id", target, "--x", str(x), "--y", str(y), "--center")
    run("easycirq", "--project", PROJECT, "--doc", PCB, "pcb", "autoroute")
    total2, _ = drc_count()
    print(f"落位并重新布线后 DRC：{total2} 处")
    return 0 if total2 == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
