#!/usr/bin/env python3
"""把实测文字（页坐标）转成 `sch_text_audit.py` 要的可见文字格式。

为什么要单独一步：`svg_text_bbox.py` 的输出是 `{count,rows,viewBox,...}`，
而文字审计要的是 `{result:{count,items,unmeasured}}`，且 bbox 维度命名不同。
两边都量的是**同一批渲染文字**，只是承载格式不同。

用法：
  python scripts/sch_preview_textaudit.py --texts texts-M3.json \\
      --visible visible-M3.json --out visible-M3.audit.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def build(texts_path, visible_path, gap=2.0):
    texts = json.loads(pathlib.Path(texts_path).read_text(encoding="utf-8"))
    vis = json.loads(pathlib.Path(visible_path).read_text(encoding="utf-8"))
    boxes = {it["id"]: it["bbox"] for it in (vis.get("items") or [])}

    items, unmeasured = [], []
    for t in texts:
        b = boxes.get(t.get("primitiveId"))
        if not b:
            # `unmeasured` 必须是**数组**（审计要逐条知道哪些文字没测到框），
            # 不是计数。给数字会被判 invalid_input。
            unmeasured.append({"id": t.get("primitiveId"),
                               "text": t.get("Content") or ""})
            continue
        items.append({
            "id": t.get("primitiveId"),
            "text": t.get("Content") or "",
            "bbox": {"minX": b["minX"], "minY": b["minY"],
                     "maxX": b["maxX"], "maxY": b["maxY"]},
        })
    # coverage：TEXT_CLASSES 里**真正采集到的**才写 true。
    # 我只测了渲染器画出来的自由文字与网名，其余类别如实标未采集。
    coverage = {"free_text": True, "net_labels": True,
                "designators": True, "values": False,
                "pin_names": False, "wire_names": False, "title_block": False}
    return {"result": {"count": len(items), "items": items,
                       "unmeasured": unmeasured, "coverage": coverage},
            "gap": gap,
            "source": {"texts": str(texts_path), "visible": str(visible_path)}}


def main() -> int:
    ap = argparse.ArgumentParser(description="实测文字 → 文字审计输入")
    ap.add_argument("--texts", required=True)
    ap.add_argument("--visible", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gap", type=float, default=2.0)
    args = ap.parse_args()
    doc = build(args.texts, args.visible, args.gap)
    pathlib.Path(args.out).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  文字审计输入 → %s（%d 条实测，%d 条无框）"
          % (args.out, doc["result"]["count"],
             len(doc["result"]["unmeasured"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
