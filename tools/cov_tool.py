"""五块：快照 → 适配器 → 覆盖度汇总（可复用）。"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path("reports/hard-board/board2")
SK = pathlib.Path(os.environ["USERPROFILE"]) / ".agents/skills/easycirq/scripts"


def run(modules=("M1", "M2", "M3", "M4", "M5")):
    rows = []
    for m in modules:
        comp = ROOT / ("composition-%s-placed.json" % m)
        snap = ROOT / ("snap-%s-placed" % m)
        strict = ROOT / ("strict-%s-placed.json" % m)
        subprocess.run([sys.executable, "easycirq/scripts/sch_composition_snapshot.py",
                        "--composition", str(comp), "--out-dir", str(snap)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
        p = subprocess.run([sys.executable, str(SK / "layout_from_easycirq.py"),
                            "--list", str(snap / "list.json"),
                            "--out", str(strict)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        out = p.stdout.strip()
        i = out.find("{")
        d = json.loads(out[i:]) if i >= 0 else {}
        c = d.get("coverage") or {}
        rows.append((m, d.get("components", 0), d.get("texts", 0),
                     d.get("wires", 0), d.get("net_flags", 0),
                     d.get("module_frames", 0),
                     (c.get("texts") or {}).get("status"),
                     (c.get("wires") or {}).get("status")))
    return rows


if __name__ == "__main__":
    print("  模块  件  文字  导线  网标  框   文字覆盖  导线覆盖")
    for r in run():
        print("  %-4s %2d  %4d  %4d  %4d  %2d   %-9s %s" % r)
