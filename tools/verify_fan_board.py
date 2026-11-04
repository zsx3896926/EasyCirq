"""风扇板一站式验证：一条命令跑完全部判据。

## 为什么需要这个

这一局陆续加了几个新判据（额定应力、容差、去耦摆放），但它们是**分散的工具**——
没人跑就等于没有。这个入口把它们串成一条命令，并且要求每一步都留下可见输出。

## 覆盖范围

| 步骤 | 命令 | 看什么 |
|---|---|---|
| 设计有效性 | `easycirq/scripts/sch_design_validity.py` | 阈值/驱动/回差/续流/电源域/额定应力 |
| 去耦摆放 | `tools/check_decap_placement.py` | 去耦电容到 IC 电源脚的焊盘中心距 |
| 19 项 KPI 门禁 | `easycirq/scripts/sch_offline_pipeline.py` | 结构/供电/一致性 + 上机许可 |
| 交付包自检 | `tools/check_deliverable.py` | 文件齐、校验和对、卡片与报告一致 |

## 退出码

0 = 全过（warn 不算失败）
1 = 有 fail
2 = 有 unknown / not_run（判不了就别报通过）

**这不是 19 项 KPI 的替代品。** 去耦距离没有进 KPI 契约（那要改 19 项定义与阈值，
属于契约变更），所以它由这个入口负责，跑在这里就是被执行的。
"""
import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "deliverables" / "fan-controller"


def run(cmd, label):
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600,
                          cwd=str(ROOT))
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out, label


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", default="Fan-Controller-12V")
    ap.add_argument("--project-uuid", default="77ef9d0874cc48499400578c59eb2910")
    ap.add_argument("--page", default="P1")
    ap.add_argument("--package", default=str(PKG))
    args = ap.parse_args(argv)

    package = pathlib.Path(args.package)
    snap = package / "snapshot"
    intent = package / "design" / "intent.json"

    steps = []

    rc, out, _ = run([sys.executable, "easycirq/scripts/sch_design_validity.py",
                      "--netlist", str(snap / "list.json"),
                      "--intent", str(intent)], "design_validity")
    steps.append(("设计有效性", rc, out))

    rc, out, _ = run([sys.executable, "tools/check_decap_placement.py",
                      "--board", str(snap / "pcb-dump.json")], "decap")
    steps.append(("去耦摆放", rc, out))

    rc, out, _ = run([sys.executable,
                      str(pathlib.Path.home() / ".agents" / "skills" / "easycirq"
                          / "scripts" / "sch_offline_pipeline.py"),
                      "--snapshot-dir", str(snap), "--project", args.project,
                      "--project-uuid", args.project_uuid, "--page", args.page,
                      "--out-dir", "reports/fan-controller",
                      "--design-intent", str(intent)], "kpi")
    steps.append(("19 项 KPI 门禁", rc, out))

    rc, out, _ = run([sys.executable, "tools/check_deliverable.py",
                      str(package)], "deliverable")
    steps.append(("交付包自检", rc, out))

    print("=" * 68)
    print("风扇板验证汇总")
    print("=" * 68)
    worst = 0
    for label, rc, out in steps:
        if rc == 0:
            mark = "✅ pass"
        elif rc == 1:
            mark = "❌ fail"
        else:
            mark = "⚠️  unknown/not_run"
        print(f"\n{mark:22} {label}  (exit={rc})")
        # 只印最后几行，完整输出留在各自产物里
        tail = [line for line in out.strip().splitlines() if line.strip()][-3:]
        for line in tail:
            print(f"    {line.strip()[:150]}")
        worst = max(worst, 1 if rc == 1 else (2 if rc >= 2 else 0))

    print()
    print("=" * 68)
    verdict = {0: "全部通过", 1: "有失败项", 2: "有判不了的项"}[worst]
    print(f"总判定：{verdict}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
