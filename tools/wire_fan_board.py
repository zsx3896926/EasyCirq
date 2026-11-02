"""把风扇板按网表连起来。

每个引脚打一个网络标记（net label），EasyEDA 按名字合并同名的线。
这比手工画折线可靠：折线一旦共线相接会被平台静默合并（sch wire 的帮助里明确警告过）。

网表（先写清楚再执行）：
  PWR5V    R1.1  R2.1  U1.8  R5.1
  PWR12V   FAN1.1  D1.2(阴极 K)
  GND      NTC1.2  R3.2  U1.4  Q1.2(S)
  NTC_MID  NTC1.1  R1.2  U1.3  R6.2
  TH       R2.2   R3.1  U1.2
  ALARM    U1.1   R6.1  R7.2
  GATE     R7.1   R5.2  Q1.1(G)
  FAN_M    Q1.3(D)  FAN1.2  D1.1(阳极 A)
"""
import json
import subprocess
import sys

PROJECT = "Fan-Controller-12V"
PAGE = "664436e68d969739"

NETS = {
    "PWR5V": [("R1", "1"), ("R2", "1"), ("U1", "8"), ("R5", "1")],
    "PWR12V": [("FAN1", "1"), ("D1", "2")],
    "GND": [("NTC1", "2"), ("R3", "2"), ("U1", "4"), ("Q1", "2")],
    "NTC_MID": [("NTC1", "1"), ("R1", "2"), ("U1", "3"), ("R6", "2")],
    "TH": [("R2", "2"), ("R3", "1"), ("U1", "2")],
    "ALARM": [("U1", "1"), ("R6", "1"), ("R7", "2")],
    "GATE": [("R7", "1"), ("R5", "2"), ("Q1", "1")],
    "FAN_M": [("Q1", "3"), ("FAN1", "2"), ("D1", "1")],
}

# 电源和地用专用 flag 类型，让平台画成电源符号；其余用普通网络标签
KIND = {"PWR5V": "power", "PWR12V": "power", "GND": "ground"}


def cli(*args):
    return subprocess.run(["easycirq", *[str(a) for a in args]],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def main():
    failed = []
    for net, pins in NETS.items():
        kind = KIND.get(net, "net_label")
        for designator, pin in pins:
            proc = cli("--project", PROJECT, "--doc", PAGE, "sch", "autoconnect",
                       "--pin", f"{designator}:{pin}",
                       "--kind", kind, "--net", net)
            out = (proc.stdout or "") + (proc.stderr or "")
            ok = '"ok": true' in out
            mark = "✓" if ok else "✗"
            print(f"{mark} {net:8} {designator}.{pin}")
            if not ok:
                detail = [ln.strip() for ln in out.splitlines()
                          if "✗" in ln or "error" in ln.lower() or "拒绝" in ln]
                print("    " + (" | ".join(detail)[:200] or out[:200].replace("\n", " ")))
                failed.append(f"{net}:{designator}.{pin}")
    print()
    if failed:
        print(f"失败 {len(failed)} 个：{', '.join(failed)}")
        return 1
    print("全部引脚已打标。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
