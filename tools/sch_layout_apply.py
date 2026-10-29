"""Apply a sch_layout_plan plan to EasyEDA: place one block at a time, measure its
rendered bbox, snap it onto the planned box, rebuild zones from measured boxes and
export a PNG. Requires the easycirq daemon + a connected EasyEDA window.

Usage:
    python tools/sch_layout_apply.py <spec.json>

spec: {project_uuid, page, plan, parts, out_dir, export_name, window}

This avoids cumulative drift: each block is corrected onto its planned bbox
before the next block consumes space.
"""
import json
import pathlib
import subprocess
import sys
import time

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"



def cli(*args, timeout=120):
    last = None
    for _ in range(6):
        try:
            r = subprocess.run([BIN, *args], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            time.sleep(6)
            continue
        last = r
        text = (r.stdout or "") + (r.stderr or "")
        if "document transition is being verified" in text:
            time.sleep(8)
            continue
        return r.returncode, r.stdout, r.stderr
    if last is not None:
        return last.returncode, last.stdout, last.stderr
    return 1, "", "timeout"


def parse(out):
    s = (out or "").strip()
    i = s.find("{")
    if i < 0:
        return None
    try:
        return json.loads(s[i:])
    except Exception:
        return None


def components():
    code, out, err = cli("call", "schematic.components.list",
                         "--payload", '{"includeBBox":true}')
    d = parse(out) or {}
    return ((d.get("result") or {}).get("components") or [])


def union_bbox(comps, designators):
    xs = []
    for c in comps:
        if c.get("componentType") != "part":
            continue
        if c.get("designator") in designators and c.get("bbox"):
            b = c["bbox"]
            xs.append((b["minX"], b["minY"], b["maxX"], b["maxY"]))
    if not xs:
        return None
    return [min(x[0] for x in xs), min(x[1] for x in xs),
            max(x[2] for x in xs), max(x[3] for x in xs)]


def run(project_uuid, page, plan_path, parts, out_dir, export_name, window):
    plan = json.loads(pathlib.Path(plan_path).read_text(encoding="utf-8"))
    out_dir = pathlib.Path(out_dir)
    doc = ["--doc", page]
    report = {"page": page, "blocks": [], "moves": []}

    # activate project + page
    if not window:
        raise ValueError("spec.window is required (use `easycirq doctor` to find it)")
    # window ids change when the connector reconnects; resolve the live one
    c, o, e = cli("project", "info")
    info = parse(o) or {}
    live_window = info.get("windowId") or (info.get("context") or {}).get("windowId") or window
    if not live_window:
        raise ValueError("no connected EasyEDA window (run `easycirq doctor`)")
    cli("project", "open", "--window", live_window, "--project-uuid", project_uuid,
        "--allow-discard-unsaved")
    time.sleep(4)
    cli("call", "document.open", "--payload", json.dumps({"uuid": page}))
    # wait until the daemon/editor accepts reads again (writes settle after reopen)
    for _ in range(20):
        time.sleep(3)
        c, o, e = cli("call", "schematic.components.list", "--payload", "{}")
        if c == 0:
            break
    time.sleep(5)

    # clear must actually succeed and the page must report zero parts
    cleared = False
    for attempt in range(10):
        code, out, err = cli("sch", "clear", *doc)
        time.sleep(5)
        comps = [c for c in components() if c.get("componentType") == "part"]
        if code == 0 and not comps:
            cleared = True
            break
    report["clear"] = code
    if not cleared:
        report["error"] = "clear did not empty the page; refusing to place blocks on top of stale parts"
        report["metrics"] = {"blocks": 0, "fits": 0, "overlaps": 0, "verdict": "blocked"}
        (out_dir / (export_name + ".report.json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        return report

    # place blocks one at a time, snapping each onto its planned bbox
    for i, p in enumerate(plan["placements"]):
        if not p.get("bbox"):
            report["blocks"].append({"id": p["id"], "skipped": "unplaced"})
            continue
        planned = p["bbox"]
        before = {c.get("designator") for c in components()
                  if c.get("componentType") == "part"}
        # NOTE: --json on a real apply can stall for minutes; diff designators instead
        code, out, err = cli("sch", "block-apply", p["id"], "--at", p["at"],
                             "--parts", parts, *doc)
        time.sleep(3)
        after = [c for c in components() if c.get("componentType") == "part"]
        desig = [c.get("designator") for c in after
                 if c.get("designator") and c.get("designator") not in before]
        group = "blk-%02d" % (i + 1)
        # block-apply already records provenance groups "<blockId>(<instance>)/..."
        codeg, outg, errg = cli("sch", "group", "list", "--json", *doc)
        gdata = parse(outg) or {}
        groups = ((gdata.get("groupsByPage") or {}).get(page)
                  or gdata.get("groups")
                  or (gdata.get("result") or {}).get("groups") or [])
        short = p["id"].split(".", 1)[-1]
        block_groups = [str(g.get("id") or g.get("name")) for g in groups
                        if str(g.get("name", "")).startswith(short + "(")]
        time.sleep(7)
        actual = union_bbox(components(), set(desig)) if desig else None
        moved = None
        if actual:
            dx = planned[0] - actual[0]
            dy = planned[1] - actual[1]
            if abs(dx) > 8 or abs(dy) > 8:
                if block_groups:
                    code2, out2, err2 = cli("sch", "group-move", "--groups", ",".join(block_groups),
                                            "--dx", str(round(dx, 1)), "--dy", str(round(dy, 1)), *doc)
                else:
                    code2, out2, err2 = cli("sch", "group-move", "--group", group,
                                            "--dx", str(round(dx, 1)), "--dy", str(round(dy, 1)), *doc)
                time.sleep(5)
                actual = union_bbox(components(), set(desig))
                moved = {"dx": dx, "dy": dy, "exit": code2}
        report["blocks"].append({"id": p["id"], "group": group, "groups": locals().get("block_groups", []), "designators": desig,
                                 "apply": code, "actual": actual, "moved": moved})
        report["moves"].append(moved)

    # rebuild zones from measured bboxes (single frame apply)
    zframes = []
    for i, blk in enumerate(report["blocks"]):
        a = blk.get("actual")
        if not a:
            continue
        title = plan["placements"][i]["title"]
        zx1, zy1 = int(max(12, round(a[0] - 16))), int(max(12, round(a[1] - 16)))
        zx2, zy2 = int(min(1158, round(a[2] + 16))), int(min(813, round(a[3] + 16 + 36)))
        zframes.append({"id": "zone-%02d" % (i + 1), "title": title,
                        "rect": {"minX": zx1, "minY": zy1, "maxX": zx2, "maxY": zy2},
                        "titleX": zx1 + 8, "titleY": zy2 - 8, "fontSize": 20,
                        "color": "#AA00AA", "lineType": 1})
    for i in range(len(zframes)):
        for j in range(i + 1, len(zframes)):
            a, b = zframes[i], zframes[j]
            ar, br = a["rect"], b["rect"]
            ox = max(0, min(ar["maxX"], br["maxX"]) - max(ar["minX"], br["minX"]))
            oy = max(0, min(ar["maxY"], br["maxY"]) - max(ar["minY"], br["minY"]))
            if ox > 0 and oy > 0:
                if ox <= oy:
                    if ar["minX"] > br["minX"]:
                        ar["minX"] = br["maxX"] + 4
                    else:
                        br["minX"] = ar["maxX"] + 4
                else:
                    if ar["minY"] > br["minY"]:
                        ar["minY"] = br["maxY"] + 4
                    else:
                        br["minY"] = ar["maxY"] + 4
                a["titleY"] = ar["maxY"] - 8
                b["titleY"] = br["maxY"] - 8
    zf = {"schemaVersion": 1, "documentId": page, "frames": zframes}
    zpath = out_dir / (export_name + ".zones.json")
    zpath.write_text(json.dumps(zf, ensure_ascii=False, indent=1), encoding="utf-8")
    code, out, err = cli("sch", "frame", "apply", "--from", str(zpath), *doc)
    report["zones_reapplied"] = code
    time.sleep(4)

    # metrics
    boxes = [(b["id"], b["actual"]) for b in report["blocks"] if b.get("actual")]
    fits = sum(1 for _, a in boxes if a[0] >= 12 and a[1] >= 12 and a[2] <= 1158 and a[3] <= 813)
    overlaps = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
            iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
            if ix * iy > 0:
                overlaps += 1
    report["metrics"] = {"blocks": len(boxes), "fits": fits, "overlaps": overlaps,
                         "verdict": "pass" if fits == len(boxes) and overlaps == 0 else "review"}
    code, out, err = cli("sch", "layout-lint", *doc)
    report["layout_lint"] = (out or err)[-1000:]
    time.sleep(3)
    png = out_dir / (export_name + ".png")
    code, out, err = cli("sch", "export-image", "--format", "png", "--scope", "page",
                         "--out", str(png), *doc)
    report["export"] = code
    (out_dir / (export_name + ".report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    spec = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    rep = run(spec["project_uuid"], spec["page"], spec["plan"], spec["parts"],
              spec["out_dir"], spec["export_name"], spec.get("window"))
    print(json.dumps(rep["metrics"], ensure_ascii=False))
    for b in rep["blocks"]:
        print(b.get("id"), "apply=", b.get("apply"), "actual=", b.get("actual"))
