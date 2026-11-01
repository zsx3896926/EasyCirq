"""把 PWR5V 的所有走线删掉再让自动布线重布。

为什么这样修：
  上一轮手工删了一条横穿 R4 焊盘的线，PWR5V 因此断成两段，
  而 autoroute 认为"已经有线了"不去补，于是 DRC 报两处 disconnected。

  留着残线去补，等于在不知道哪段属于谁的情况下猜；
  全部删掉重布，让路由器从零开始连这个网，是更干净的做法。

安全措施：先把要删的 id 列表存到文件，万一重布失败还能对照、手工补。
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, "tools")
from find_bad_traces import load_stripped  # noqa: E402

TEMP = os.environ["TEMP"]
NET = "PWR5V"


def fetch_lines():
    proc = subprocess.run(
        ["easycirq", "--project", "KPI-S5-Verify", "--doc", "PCB1",
         "call", "pcb.line.list"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    path = os.path.join(TEMP, "lines4.json")
    open(path, "w", encoding="utf-8").write(proc.stdout or "")
    data = load_stripped(path)
    root = data.get("result") or data
    return root.get("lines") or []


def drc_total():
    proc = subprocess.run(
        ["easycirq", "--project", "KPI-S5-Verify", "--doc", "PCB1",
         "pcb", "drc", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    path = os.path.join(TEMP, "step-drc.json")
    open(path, "w", encoding="utf-8").write(proc.stdout or "")
    parsed = subprocess.run([sys.executable, "tools/read_drc.py", path],
                            capture_output=True, text=True, encoding="utf-8")
    lines = (parsed.stdout or "").strip().splitlines()
    head = lines[0] if lines else "?"
    try:
        total = int(head.split("total:")[1].strip())
    except (IndexError, ValueError):
        total = 999
    return total, lines[:4]


def main():
    lines = [l for l in fetch_lines() if l.get("net") == NET]
    ids = [l.get("primitiveId") for l in lines if l.get("primitiveId")]
    print(f"{NET} segments: {len(ids)}")
    if not ids:
        print("没有可删的线")
        return 3

    backup = os.path.join(TEMP, "pwr5v-deleted-ids.json")
    json.dump({"ids": ids, "segments": lines}, open(backup, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"id 列表已存: {backup}")

    payload = json.dumps({"primitiveIds": ids})
    proc = subprocess.run(
        ["easycirq", "--project", "KPI-S5-Verify", "--doc", "PCB1",
         "call", "pcb.route.delete", "--payload", payload],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = '"ok": true' in (proc.stdout or "")
    print(f"删除: {'ok' if ok else '失败'}")
    if not ok:
        print((proc.stdout or "")[:400])
        return 1

    proc = subprocess.run(
        ["easycirq", "--project", "KPI-S5-Verify", "--doc", "PCB1", "pcb", "autoroute"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f"重布: {'ok' if '\"ok\": true' in (proc.stdout or '') else '返回非 ok'}")

    subprocess.run(["easycirq", "--project", "KPI-S5-Verify", "--doc", "PCB1",
                    "pcb", "save"], capture_output=True)
    subprocess.run(["easycirq", "--project", "KPI-S5-Verify", "doc", "reload",
                    "34de0a1c7592ff1e"], capture_output=True)

    total, detail = drc_total()
    print()
    print(f"DRC: {total} 处")
    for line in detail:
        print("  " + line)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
