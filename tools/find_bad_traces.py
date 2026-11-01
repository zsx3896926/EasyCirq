"""找出经过 R4 焊盘附近的 PWR5V 走线，打印它们的真实 primitiveId。

DRC 报告里的 e289/e290 是错误序号，不是图元 id，所以 pcb.route.delete 找不到。
必须从 pcb.line.list 里按几何筛。
"""
import json
import math
import os
import subprocess
import sys


def load_stripped(path):
    raw = open(path, encoding="utf-8-sig").read()
    start = raw.find("{")
    text = raw[start:]
    out = []
    depth = 0
    for line in text.splitlines():
        delta = line.count("{") + line.count("[") - line.count("}") - line.count("]")
        if depth > 0 and "staleRisk" in line:
            continue
        out.append(line)
        depth += delta
        if depth < 0:
            depth = 0
    return json.JSONDecoder().raw_decode("\n".join(out).lstrip())[0]


def dist_point_segment(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def main():
    temp = os.environ["TEMP"]
    lines_path = os.path.join(temp, "lines2.json")
    proc = subprocess.run(
        ["easycirq", "--project", "KPI-S5-Verify", "--doc", "PCB1",
         "call", "pcb.line.list"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    open(lines_path, "w", encoding="utf-8").write(proc.stdout or "")

    data = load_stripped(lines_path)
    root = data.get("result") or data
    lines = root.get("lines") or root.get("items") or []
    print(f"total lines: {len(lines)}")

    # R4 is at (362.8, -1027.72); its pads are ~±20 mil along y (rotation 90).
    targets = [(362.8, -1007.7), (362.8, -1047.7)]
    hits = []
    for line in lines:
        if line.get("net") != "PWR5V":
            continue
        x1, y1 = line.get("startX"), line.get("startY")
        x2, y2 = line.get("endX"), line.get("endY")
        if None in (x1, y1, x2, y2):
            continue
        for tx, ty in targets:
            if dist_point_segment(tx, ty, x1, y1, x2, y2) < 12:
                hits.append((line.get("primitiveId"), line.get("layer"),
                             (x1, y1), (x2, y2), line.get("lineWidth")))
                break

    print(f"PWR5V lines passing within 12 mil of R4 pads: {len(hits)}")
    for pid, layer, start, end, width in hits:
        print(f"  {pid} layer={layer} {start} -> {end} width={width}")
    if hits:
        ids = [h[0] for h in hits]
        out = os.path.join(temp, "delete-ids.json")
        json.dump({"primitiveIds": ids}, open(out, "w", encoding="utf-8"))
        print()
        print("to delete:", json.dumps({"primitiveIds": ids}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
