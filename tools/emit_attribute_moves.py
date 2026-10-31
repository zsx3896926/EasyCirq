"""Emit one ``attribute-move`` payload file per planned designator move.

Contract enforced by the Go CLI (``sch attribute-move --from``) and restated here
so a bad plan fails before it can reach the editor:

* exactly six top-level keys: projectUuid, documentUuid, primitiveId, expected, x, y;
* ``expected`` carries ALL 17 native attribute fields read through
  ``getState_*`` (X, Y, Rotation, Color, FontName, FontSize, Bold, Italic,
  UnderLine, AlignMode, FillColor, Key, Value, KeyVisible, ValueVisible,
  ParentPrimitiveId, primitiveId);
* ``expected.primitiveId == primitiveId`` and ``Key`` is Name or Designator.

Nothing is sent here; this only writes files. The caller runs the moves.
"""

from __future__ import annotations

import json
import pathlib
import sys

FIELDS = ["X", "Y", "Rotation", "Color", "FontName", "FontSize", "Bold", "Italic",
          "UnderLine", "AlignMode", "FillColor", "Key", "Value", "KeyVisible",
          "ValueVisible", "ParentPrimitiveId"]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--doc", required=True)
    parser.add_argument("--dir", required=True)
    args = parser.parse_args()

    plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
    outdir = pathlib.Path(args.dir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for move in plan["moves"]:
        expected = move["expected"]
        missing = [f for f in FIELDS if f not in expected]
        if missing:
            raise SystemExit(f"{move['designator']}: expected missing {missing}")
        if expected["primitiveId"] != move["primitiveId"]:
            raise SystemExit(f"{move['designator']}: primitiveId mismatch")
        if expected["Key"] not in ("Name", "Designator"):
            raise SystemExit(f"{move['designator']}: Key={expected['Key']!r} not movable")
        payload = {
            "projectUuid": args.project,
            "documentUuid": args.doc,
            "primitiveId": move["primitiveId"],
            "expected": expected,
            "x": move["new_x"],
            "y": move["new_y"],
        }
        path = outdir / f'{move["designator"]}.json'
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(str(path))
    print(json.dumps({"written": len(written), "dir": str(outdir)}, ensure_ascii=False))
    for w in written:
        print(" ", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
