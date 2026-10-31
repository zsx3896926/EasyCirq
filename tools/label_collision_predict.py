"""Planned-label collision predictor: prove the layout in the MODEL, not on canvas.

Same idea as ``stub_geom_preflight`` (decide geometry offline, write once), one
level up: it takes the planner's label boxes and the MEASURED text boxes of every
designator / value / pin number on the live page, and counts the collisions that
would appear if this plan were written.

The 2026-10-30 C page showed why this must exist: 67 text collisions on canvas
while every gate reported "clean" — ``sch check`` counts marker-vs-body only and
``layout-lint`` explicitly skips non-part primitives. Without a predictor, the
only way to discover a label pile-up is to look at a PNG after writing 109 stubs.

Schema: ``easycirq-label-collision-prediction/v1``.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROLES_AVOID = ("designator", "value", "designator?", "pin_name")
ROLES_AVOID_SOFT = ("pin_number", "other", "titleblock")


def _area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return x1 - x0, y1 - y0


def _cover_ratio(a, b):
    inter = _intersection(a, b)
    if not inter:
        return 0.0
    smaller = min(_area(a), _area(b))
    if smaller <= 0:
        return 0.0
    return (inter[0] * inter[1]) / smaller


def load_text_boxes(path):
    """Split measured text into avoid (hard) / soft lists by role."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rows = data["rows"] if isinstance(data, dict) else data
    hard, soft = [], []
    for row in rows:
        role = row.get("role") or ""
        if role in ROLES_AVOID:
            hard.append({"text": row["text"], "role": role, "bbox": row["bbox"]})
        elif role in ROLES_AVOID_SOFT:
            soft.append({"text": row["text"], "role": role, "bbox": row["bbox"]})
    return hard, soft


def predict(planned, hard, soft, *, min_ratio=0.20):
    """planned = [{"pin", "net", "label_bbox"}]; hard/soft = measured text boxes."""
    label_vs_label, label_vs_hard, label_vs_soft = [], [], []
    for i in range(len(planned)):
        for j in range(i + 1, len(planned)):
            ratio = _cover_ratio(planned[i]["label_bbox"], planned[j]["label_bbox"])
            if ratio >= min_ratio:
                label_vs_label.append({"a": planned[i]["pin"], "b": planned[j]["pin"],
                                       "nets": [planned[i]["net"], planned[j]["net"]],
                                       "ratio": round(ratio, 3)})
    for item in planned:
        for other in hard:
            ratio = _cover_ratio(item["label_bbox"], other["bbox"])
            if ratio >= min_ratio:
                label_vs_hard.append({"pin": item["pin"], "net": item["net"],
                                      "text": other["text"], "role": other["role"],
                                      "ratio": round(ratio, 3)})
        for other in soft:
            ratio = _cover_ratio(item["label_bbox"], other["bbox"])
            if ratio >= min_ratio:
                label_vs_soft.append({"pin": item["pin"], "net": item["net"],
                                      "text": other["text"], "role": other["role"],
                                      "ratio": round(ratio, 3)})
    total = len(label_vs_label) + len(label_vs_hard)
    return {
        "schema": "easycirq-label-collision-prediction/v1",
        "labels": len(planned),
        "label_vs_label": len(label_vs_label),
        "label_vs_text": len(label_vs_hard),
        "label_vs_soft": len(label_vs_soft),
        "collisions": total,
        "details": {"label_vs_label": label_vs_label[:20],
                    "label_vs_text": label_vs_hard[:20],
                    "label_vs_soft": label_vs_soft[:20]},
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--planned", required=True, help="plan JSON with rows[].label_bbox")
    parser.add_argument("--texts", required=True, help="text-bboxes.json (rows with role)")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    planned = json.loads(pathlib.Path(args.planned).read_text(encoding="utf-8"))
    rows = [row for row in planned.get("rows") or [] if row.get("label_bbox")]
    hard, soft = load_text_boxes(args.texts)
    report = predict(rows, hard, soft)
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "details"}, ensure_ascii=False))
    for item in report["details"]["label_vs_label"][:10]:
        print("  LABEL x LABEL %-10s(%s) x %-10s(%s) %.0f%%"
              % (item["a"], item["nets"][0], item["b"], item["nets"][1], 100 * item["ratio"]))
    for item in report["details"]["label_vs_text"][:10]:
        print("  LABEL x %-9s %-10s(%s) over %-8s %.0f%%"
              % (item["role"], item["pin"], item["net"], item["text"], 100 * item["ratio"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
