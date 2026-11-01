"""Text-collision audit: measure what the eye sees, which no current gate covers.

Why this exists (2026-10-30): after the C-board replay was electrically complete
(43 parts / 109 nets / 0 zero-length wires), the page still looked crowded, yet
`sch check` reported only 5 marker-overlaps. The reason is a measurement gap, not
a counting bug:

* `sch layout-lint` judges **component bodies only** (it says so: 未判定 36 个非
  part 图元);
* `sch check` counts net-marker overlaps and designator/body or designator/wire
  overlaps, but NOT label-text vs designator-text, nor value text, nor pin names;
* `sch designator-geometry` measures designator boxes only.

So the collisions a reviewer actually sees — net-label text sitting on top of a
designator, a value ("22uF"), a pin name, or another label — were invisible to
every gate. This module closes that gap: it takes the RENDERED text boxes (from
an official SVG export measured by ``svg_text_bbox.py``), classifies every box by
role, and reports pairwise collisions by role pair, plus crowding per component.

Inputs are read-only artifacts; this module never talks to EasyEDA.
Schema: ``easycirq-text-overlap-audit/v1``.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

DESIGNATOR_RE = re.compile(r"^[A-Z]{1,3}\d{1,3}$")
VALUE_RE = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:pF|nF|uF|mF|Ω|kΩ|MΩ|uH|nH|mH|V|mV|A|mA|W|%)\s*$")
PINNAME_RE = re.compile(r"^[A-Za-z~#+/_0-9.\-]{1,8}$")
TITLE_WORDS = ("原理图", "板子", "绘制", "审阅", "版本", "尺寸", "页", "共", "图页",
               "Schematic", "Board", "EasyCirq", "EasyEDA", "嘉立创", "创建日期", "更新日期")
MIN_OVERLAP_RATIO = 0.20      # share of the SMALLER box that must be covered
AREA_EPS = 1e-9


def area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersect(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def classify(text, refs, nets, designator_values):
    body = text.strip()
    if not body:
        return "blank"
    if body in refs or body in designator_values:
        return "designator"
    if body in nets:
        return "net_label"
    if any(word in body for word in TITLE_WORDS):
        return "titleblock"
    if VALUE_RE.match(body):
        return "value"
    if DESIGNATOR_RE.match(body):
        return "designator?"      # looks like a ref but is not on this page
    if re.fullmatch(r"\d{1,3}", body):
        return "pin_number"
    if PINNAME_RE.match(body):
        return "pin_name"
    return "other"


def audit(texts, bodies, refs, nets, designator_values, *, min_ratio=MIN_OVERLAP_RATIO):
    rows = []
    for text in texts:
        bbox = text["bbox"]
        rows.append({"text": text["text"], "bbox": bbox, "area": area(bbox),
                     "role": classify(text["text"], refs, nets, designator_values)})

    # One rendered label can appear as SEVERAL <text> elements at the same box
    # (the SVG exporter splits a name into runs/flags). Counting those as
    # collisions inflates the metric and sends the fix after a phantom: on
    # 2026-10-30 the raw count reported `U2_LX @(120,-570) x U2_LX @(120,-570)`
    # at 100% for a label that only existed once. Dedupe identical
    # (text, rounded bbox) pairs first, and report how many were merged.
    seen, deduped, duplicates = set(), [], 0
    for row in rows:
        key = (row["text"], round(row["bbox"][0], 1), round(row["bbox"][1], 1),
               round(row["bbox"][2], 1), round(row["bbox"][3], 1))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        deduped.append(row)
    rows = deduped

    collisions = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            inter = intersect(a["bbox"], b["bbox"])
            if inter is None:
                continue
            smaller = min(a["area"], b["area"])
            if smaller <= AREA_EPS:
                continue
            ratio = area(inter) / smaller
            if ratio < min_ratio:
                continue
            collisions.append({
                "a": a["text"], "a_role": a["role"],
                "b": b["text"], "b_role": b["role"],
                "ratio_of_smaller": round(ratio, 3),
                "pair": "|".join(sorted([a["role"], b["role"]])),
            })

    by_pair = {}
    for item in collisions:
        by_pair[item["pair"]] = by_pair.get(item["pair"], 0) + 1

    # crowding: text boxes whose centre sits inside a body expanded by `pad`
    crowd = {}
    for row in rows:
        cx = (row["bbox"][0] + row["bbox"][2]) / 2.0
        cy = (row["bbox"][1] + row["bbox"][3]) / 2.0
        for ref, box in (bodies or {}).items():
            if box[0] - 2 <= cx <= box[2] + 2 and box[1] - 2 <= cy <= box[3] + 2:
                crowd.setdefault(ref, {"texts_inside_body": 0, "roles": {}})
                crowd[ref]["texts_inside_body"] += 1
                crowd[ref]["roles"][row["role"]] = crowd[ref]["roles"].get(row["role"], 0) + 1
                break

    return {
        "schema": "easycirq-text-overlap-audit/v1",
        "texts": len(rows),
        "duplicate_texts_merged": duplicates,
        "roles": {},
        "collisions": len(collisions),
        "by_pair": by_pair,
        "min_overlap_ratio": min_ratio,
        "pairs": collisions,
        "worst": sorted(collisions, key=lambda c: -c["ratio_of_smaller"])[:15],
        "crowded_parts": sorted(crowd.items(), key=lambda kv: -kv[1]["texts_inside_body"])[:12],
        "rows": rows,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--texts", required=True, help="svg_text_bbox.py output")
    parser.add_argument("--bodies", default="", help="schematic.components.list includeBBox response")
    parser.add_argument("--nets", default="", help="nets asset (name list)")
    parser.add_argument("--designators", default="", help="sch designator-geometry output")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    texts = json.loads(pathlib.Path(args.texts).read_text(encoding="utf-8"))["rows"]
    bodies, refs, nets, designator_values = {}, set(), set(), set()
    if args.bodies:
        data = json.loads(pathlib.Path(args.bodies).read_text(encoding="utf-8"))
        for comp in (data.get("result") or data).get("components") or []:
            ref = comp.get("designator")
            box = comp.get("bbox")
            if ref and box and comp.get("componentType") == "part":
                bodies[ref] = (float(box["minX"]), float(box["minY"]),
                               float(box["maxX"]), float(box["maxY"]))
                refs.add(ref)
    if args.nets:
        data = json.loads(pathlib.Path(args.nets).read_text(encoding="utf-8"))
        nets = {n["name"] for n in data.get("nets") or data}
    if args.designators:
        data = json.loads(pathlib.Path(args.designators).read_text(encoding="utf-8"))
        designator_values = {d["value"] for d in data.get("designators") or []}

    report = audit(texts, bodies, refs, nets, designator_values)
    counts = {}
    for row in report["rows"]:
        counts[row["role"]] = counts.get(row["role"], 0) + 1
    report["roles"] = counts

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("texts", "roles", "collisions", "by_pair",
                                             "min_overlap_ratio")}, ensure_ascii=False))
    print("worst collisions:")
    for item in report["worst"][:10]:
        print("  %-8s(%s) x %-10s(%s)  cover=%.0f%%"
              % (item["a"], item["a_role"], item["b"], item["b_role"],
                 100 * item["ratio_of_smaller"]))
    print("crowded parts (texts whose centre falls inside a body):")
    for ref, info in report["crowded_parts"][:8]:
        print("  %-5s %d texts %s" % (ref, info["texts_inside_body"], info["roles"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
