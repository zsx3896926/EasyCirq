"""Deterministic EDA acceptance plan from an apply bundle (offline).

Turns an ``easycirq-sch-apply/v1`` document into an ordered, replayable
acceptance run: clear page -> draw frames -> place parts/block -> save ->
snapshot + review -> export image.  Emits ``easycirq`` CLI command strings and
machine-readable checks; it does not execute them.

Output schema: ``easycirq-accept/v1``.
"""

from __future__ import annotations

import json
import pathlib

SCHEMA = "easycirq-accept/v1"
BIN = "easycirq"
PAGE = 1170, 825
TITLE_BLOCK = [460, 10, 1160, 190]


def _check_inside_page(bbox):
    x0, y0, x1, y1 = bbox
    inside = x0 >= 0 and y0 >= 0 and x1 <= PAGE[0] and y1 <= PAGE[1]
    overlap_title = not (x1 < TITLE_BLOCK[0] or x0 > TITLE_BLOCK[2]
                         or y1 < TITLE_BLOCK[1] or y0 > TITLE_BLOCK[3])
    return {"check": "geometry", "inside_page": bool(inside),
            "title_block_hit": bool(overlap_title), "bbox": [x0, y0, x1, y1]}


def build(apply_document, *, project_uuid, page, parts_path=None):
    commands = []
    checks = []
    # 0) open + clear page
    commands.append("%s project open --project-uuid %s --allow-discard-unsaved"
                    % (BIN, project_uuid))
    commands.append('%s call document.open --payload "{\\"uuid\\":\\"%s\\"}"'
                    % (BIN, page))
    commands.append("%s sch clear-page" % BIN)
    checks.append({"check": "parts_count", "expect": 0})
    # 1) frames then placements
    for pg in apply_document.get("pages") or []:
        for frame in pg.get("frames") or []:
            rect = frame.get("rect") or []
            commands.append("%s sch frame-add --x %s --y %s --w %s --h %s --title %s"
                            % (BIN, rect[0], rect[1], rect[2] - rect[0],
                               rect[3] - rect[1], frame.get("title", frame["id"])))
        for placement in pg.get("placements") or []:
            bbox = placement.get("bbox") or []
            checks.append(_check_inside_page(bbox))
            if placement.get("parts"):
                for part in placement["parts"]:
                    commands.append(
                        "%s sch place --designator %s --x %s --y %s --rotation %s"
                        % (BIN, part.get("ref"), part.get("x"),
                           part.get("y"), part.get("rotation", 0)))
            else:
                commands.append("%s sch block-apply --at %s --project %s"
                                % (BIN, placement.get("at"),
                                   apply_document.get("project")))
    # 2) save-after-apply invariant
    post = apply_document.get("post_apply") or {}
    if post.get("save"):
        commands.append("%s %s" % (BIN, post["save"]))
    # 3) verify: snapshot + review + image
    commands.append("%s tools/ace_snapshot.py %s snapshot.json" % ("python", page))
    commands.append("python tools/ace_review.py snapshot.json --gate")
    commands.append("%s sch export-image --format png --scope page --out out.png --doc %s"
                    % (BIN, page))
    checks.append({"check": "save_after_apply", "required": bool(post.get("required"))})
    return {"schema": SCHEMA, "commands": commands, "checks": checks,
            "counts": {"commands": len(commands), "checks": len(checks)}}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("apply_bundle")
    parser.add_argument("--project-uuid", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--emit")
    args = parser.parse_args()
    bundle = json.loads(pathlib.Path(args.apply_bundle).read_text(encoding="utf-8"))
    result = build(bundle, project_uuid=args.project_uuid, page=args.page)
    if args.emit:
        pathlib.Path(args.emit).write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False))
