"""指标 5：无令牌的交付类动作，必须 100% 被拒绝。

1.3.0 起门禁是分阶段的：建板写入（放置/连线/布线）放行，只有交付类动作
（Gerber / CPL / 网表）要令牌。所以这条指标的正确范围是**交付类动作**，
不是所有写入——把范围说清楚，比笼统说"100%"重要。

这个脚本在**没有任何 gate 文件**的临时目录里逐个调用，确认每一个都被拒绝。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

# The three actions that declare GateRequired in runtime/internal/protocol/actions.go.
DELIVERY_ACTIONS = [
    "pcb.manufacture.gerber",
    "pcb.manufacture.cpl",
    "pcb.manufacture.netlist",
]

# Also exports a netlist, but does NOT declare GateRequired. Recorded separately so
# the difference is visible rather than assumed away.
UNGATED_NETLIST = "schematic.export.netlist"


def run(cwd: pathlib.Path, action: str, payload: str = "{}"):
    return subprocess.run(["easycirq", "call", action, "--payload", payload],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


def main():
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="gate-probe-"))
    # No .easycirq/gate.json here, and no --gate flag: the daemon must refuse.
    print(f"workdir: {workdir}  (no gate file)")
    print()

    rejected, wrong = [], []
    for action in DELIVERY_ACTIONS:
        proc = run(workdir, action)
        text = (proc.stdout or "") + (proc.stderr or "")
        refused = proc.returncode != 0 and ("GATE" in text.upper() or "许可" in text or "通行" in text)
        status = "refused" if refused else "NOT REFUSED"
        print(f"{action:32} exit={proc.returncode:3}  {status}")
        if not refused:
            print(f"    output: {text.strip()[:200]}")
            wrong.append(action)
        else:
            first = text.strip().splitlines()[:1]
            print(f"    {first[0][:120] if first else ''}")
        (rejected if refused else wrong)

    print()
    print(f"refused: {len(DELIVERY_ACTIONS) - len(wrong)} / {len(DELIVERY_ACTIONS)}")

    proc = run(workdir, UNGATED_NETLIST)
    text = (proc.stdout or "") + (proc.stderr or "")
    gated = "GATE" in text.upper()
    first = text.strip().splitlines()[:1]
    print(f"{UNGATED_NETLIST:32} exit={proc.returncode:3}  "
          f"{'refused' if gated else 'not gated (reached the EDA layer)'}")
    if first:
        print(f"    {first[0][:120]}")

    if wrong:
        print()
        print("NOT REFUSED:", wrong)
        print("These delivery actions ran without a token - that is a gate hole.")
        return 1
    print()
    print("三个被标为 GateRequired 的制造交付动作，无令牌时全部被拒绝。")
    print(f"{UNGATED_NETLIST} 同样导出网表，但不在门禁内 —— 2026-11-01 用户确认这是"
          "设计选择：交付类动作只指制造文件，建板阶段的导出放行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
