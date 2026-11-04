"""Re-fit the dashed block frames on the live page (real EDA, read + frame write).

Why: the legacy frame pass unioned only part *bodies*, so routed wires and the
net flags at their ends stuck out of the dashed box.  This script reads the
live page (part/flag bboxes, text primitives, connectivity), computes frames
that cover the drawn content, applies them with ``sch frame apply`` and verifies
with ``sch frame check``.

Usage:
  python tools/refit_frames.py --project <uuid> --page <uuid> --blocks <json> \
      [--lang zh] [--window <id>] [--dry-run]

``<blocks>`` is a JSON list: ``[{"id","designators":[...],"title"?,"nets"?}]``
(``title`` is optional; with ``--lang zh`` the block-titles asset is used).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"
TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = TOOLS.parent
ASSET = ROOT / "easycirq" / "assets" / "block-titles.json"
sys.path.insert(0, str(TOOLS))
import frame_fit  # noqa: E402


def cli(*args, timeout=240):
    r = subprocess.run([BIN, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    text = (r.stdout or "") + (r.stderr or "")
    start = text.find("{")
    data = {}
    if start >= 0:
        try:
            data, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            data = {}
    return r.returncode, data, text


def _titles(lang):
    if not ASSET.is_file():
        return {}
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    key = "zh" if lang.startswith("zh") else "en"
    return {block: pair.get(key) or pair.get("en") or block
            for block, pair in (data.get("titles") or {}).items()}


def read_page(doc):
    """Live page -> (parts, flags, texts, connectivity{ref:{pin:net}})."""
    code, data, text = cli("call", "schematic.components.list",
                           "--payload", '{"includeBBox":true,"includePins":true}', *doc)
    parts, flags = [], []
    for comp in (data.get("result") or {}).get("components") or []:
        kind = comp.get("componentType")
        ref = comp.get("designator")
        bbox = comp.get("bbox")
        if kind == "part" and ref:
            parts.append({"ref": ref, "bbox": bbox})
        elif kind in ("netflag", "netport") and bbox:
            flags.append({"name": comp.get("name"), "bbox": bbox})
    code, data, text = cli("sch", "text-list", *doc)
    texts = []
    for item in (data.get("items") or data.get("result") or []):
        if not isinstance(item, dict):
            continue
        content = item.get("content") or item.get("text")
        bbox = item.get("bbox") or item.get("rect")
        if content is not None and bbox:
            texts.append({"content": content, "bbox": bbox})
    code, data, text = cli("sch", "connectivity", *doc)
    connectivity = {}
    nets = {n["id"]: n.get("name") for n in data.get("nets") or []}
    refs = {c["id"]: c.get("ref") for c in data.get("components") or []}
    for conn in data.get("connections") or []:
        ref = refs.get(conn.get("componentId"))
        if ref is None:
            continue
        connectivity.setdefault(ref, {})[str(conn.get("pinNumber"))] = \
            nets.get(conn.get("netId"))
    return parts, flags, texts, connectivity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--blocks", required=True, help="blocks JSON path")
    parser.add_argument("--window")
    parser.add_argument("--lang", default="zh")
    parser.add_argument("--out", default="frames.zones.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    doc = []
    if args.window:
        doc += ["--window", args.window]
    blocks = json.loads(pathlib.Path(args.blocks).read_text(encoding="utf-8"))
    titles = _titles(args.lang)
    for block in blocks:
        if not block.get("title"):
            block["title"] = titles.get(block["id"], block["id"])
    parts, flags, texts, connectivity = read_page(doc)
    report = frame_fit.build(blocks, parts, flags, texts, connectivity=connectivity)
    spec = {"schemaVersion": 1, "documentId": args.page,
            "frames": [{"id": f["id"], "title": f["title"],
                        "rect": {"minX": f["rect"][0], "minY": f["rect"][1],
                                 "maxX": f["rect"][2], "maxY": f["rect"][3]},
                        "titleX": f["titleX"], "titleY": f["titleY"],
                        "fontSize": f["fontSize"], "color": f["color"],
                        "lineType": f["lineType"]} for f in report["frames"]]}
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps({"frames": len(spec["frames"]), "out": str(out),
                      "titles": [f["title"] for f in spec["frames"]]},
                     ensure_ascii=False))
    if args.dry_run:
        return
    code, data, text = cli("sch", "frame", "apply", "--from", str(out), *doc)
    print("apply:", code, data.get("ok") if data else text[-160:])
    code, data, text = cli("sch", "frame", "check", "--from", str(out), *doc)
    print("check:", code, data.get("ok") if data else text[-160:])


if __name__ == "__main__":
    main()
