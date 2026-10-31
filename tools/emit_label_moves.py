"""Emit one `attribute-move` payload per planned net-label move.

The Go validator requires `expected` to hold EXACTLY the 17 native attribute
fields; the enumeration record also carries `wireId` for bookkeeping, so it is
stripped here rather than at the call site.
"""

import json
import pathlib
import sys

FIELDS = ["primitiveId", "X", "Y", "Rotation", "Color", "FontName", "FontSize", "Bold",
          "Italic", "UnderLine", "AlignMode", "FillColor", "Key", "Value", "KeyVisible",
          "ValueVisible", "ParentPrimitiveId"]


def main():
    plan = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    project, doc, outdir = sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4])
    outdir.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, move in enumerate(plan["moves"]):
        expected = {k: move["expected"].get(k) for k in FIELDS}
        if any(k not in move["expected"] for k in FIELDS):
            raise SystemExit("missing field in %s" % move["label"])
        payload = {"projectUuid": project, "documentUuid": doc,
                   "primitiveId": move["primitiveId"], "expected": expected,
                   "x": move["new_x"], "y": move["new_y"]}
        name = "%02d-%s-%s.json" % (i, move["label"].replace("/", "_"), move["primitiveId"][:8])
        (outdir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        written += 1
    print(json.dumps({"written": written, "dir": str(outdir)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
