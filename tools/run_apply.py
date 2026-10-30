"""Run a relayout plan against the live page with the bulk-apply engine."""

from __future__ import annotations

import json
import pathlib
import shlex
import subprocess
import sys
import time

ROOT = pathlib.Path(r"C:\Users\jlc\Documents\deepseek-harness\default-workspace")
VER = ROOT / "hds-verifier"
TOOLS = VER / "tools"
sys.path.insert(0, str(TOOLS))
import apply_engine  # noqa: E402

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"
OUT = ROOT / "easycirq-2h-deliverables"
WINDOW = sys.argv[1]
PROJECT = "40cad6b27bf7425280071f8e35642267"
PAGE = "4c53e460e522c393"
PLAN = json.loads((OUT / "relayout-C-v9.json").read_text(encoding="utf-8"))["plan"]
NETS = json.loads((OUT / "pipeline-demo/C-relayout.nets.json").read_text(encoding="utf-8"))["nets"]
DEV = json.loads((OUT / "pipeline-demo/C-power.device-map.json").read_text(encoding="utf-8"))
GEOMETRY = json.loads((OUT / "pipeline-demo/C-pin-geometry.json").read_text(encoding="utf-8"))
JOURNAL = OUT / "apply-C.journal.jsonl"
LOG = OUT / "run-apply-C.log"


def log(line):
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def cli(*args, timeout=240):
    result = subprocess.run([BIN, *args, "--window", WINDOW], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return (result.stdout or "") + (result.stderr or "")


def js(text):
    start = text.find("{")
    if start < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:
        return {}


def page_state():
    data = js(cli("call", "schematic.components.list", "--payload",
                  '{"includeBBox":true}'))
    parts = {c.get("designator"): c
             for c in (data.get("result") or {}).get("components") or []
             if c.get("componentType") == "part" and c.get("designator")}
    data = js(cli("sch", "connectivity"))
    names = {n["id"]: n.get("name") for n in data.get("nets") or []}
    refs = {c["id"]: c.get("ref") for c in data.get("components") or []}
    pins = {(refs.get(c.get("componentId")), str(c.get("pinNumber"))):
            names.get(c.get("netId")) for c in data.get("connections") or []}
    return parts, pins


def main():
    LOG.write_text("", encoding="utf-8")
    cli("project", "open", "--project-uuid", PROJECT, "--allow-discard-unsaved")
    time.sleep(6)
    cli("doc", "open", PAGE, "--project", PROJECT)
    time.sleep(4)
    parts, pins = page_state()
    # connect every net member that exists on the page, including parts the
    # older plan did not cover (C1/R7/R8): use their live centre for preflight.
    live_xy = {}
    for ref, comp in parts.items():
        bbox = comp.get("bbox") or {}
        try:
            live_xy[ref] = ((float(bbox["minX"]) + float(bbox["maxX"])) / 2.0,
                            (float(bbox["minY"]) + float(bbox["maxY"])) / 2.0)
        except (KeyError, TypeError, ValueError):
            continue
    planned = set(PLAN["placements"])
    missing_parts = sorted(planned - set(parts))
    log("parts on page=%d planned=%d missing=%s" % (len(parts), len(planned), missing_parts))
    ops = apply_engine.plan_ops(PLAN, NETS, DEV)
    for op in ops:
        if op["kind"] == "connect" and (op["x"] == 0.0 or op["y"] == 0.0):
            xy = live_xy.get(op["ref"])
            if xy:
                op["x"], op["y"] = xy
    ops = [op for op in ops if op["kind"] != "place" or op["ref"] not in parts]
    expected_connects = {(op["ref"], op["pin"]): op["net"]
                         for op in ops if op["kind"] == "connect"}
    missing_pins = [("%s:%s" % key) for key, net in expected_connects.items()
                    if pins.get(key) != net]
    log("planned ops=%d connects=%d missing pins=%d" % (len(ops), len(expected_connects),
                                                       len(missing_pins)))
    problems = apply_engine.preflight(ops, GEOMETRY)
    log("preflight problems=%d %s" % (len(problems), problems[:3]))

    def repair_zero_length():
        text = cli("sch", "check")
        ids = apply_engine.zero_length_wire_ids(text)
        if not ids:
            return False
        log("deleting zero-length wires: %s" % ",".join(ids))
        cli("sch", "prim-delete", "--ids", ",".join(ids), "--doc", PAGE)
        time.sleep(2)
        return True

    repair_zero_length()

    def execute(op):
        if op["kind"] == "place":
            text = cli("sch", "place", "--lib", op["lib"], "--uuid", op["dev"],
                       "--x", str(op["x"]), "--y", str(op["y"]),
                       "--designator", op["ref"], "--doc", PAGE)
            return 0, text
        command = ["sch", "connect", "--pin", "%s:%s" % (op["ref"], op["pin"]),
                   "--kind", op["kind_flag"], "--net", op["net"],
                   "--offset", "20", "--doc", PAGE]
        if op.get("direction"):
            command += ["--direction", op["direction"]]
        return 0, cli(*command)

    def reload():
        cli("doc", "reload", PAGE, "--project", PROJECT)
        time.sleep(1.5)

    def health():
        return cli("health")

    def verify():
        current_parts, current_pins = page_state()
        miss_parts = sorted(planned - set(current_parts))
        miss_pins = ["%s:%s" % key for key, net in expected_connects.items()
                     if current_pins.get(key) != net]
        return miss_parts, miss_pins

    report = apply_engine.apply_ops(
        ops, execute=execute, reload=reload, health=health,
        journal=apply_engine.Journal(JOURNAL), batch=10, pause=0.15,
        max_rounds=10, log=log, verify=verify,
        repair_geometry=repair_zero_length)
    log("REPORT " + json.dumps({k: v for k, v in report.items()
                                if k not in ("skipped_plan",)}, ensure_ascii=False))
    img = OUT / "relayout-C-live.png"
    cli("sch", "export-image", "--format", "png", "--scope", "page",
        "--doc", PAGE, "--out", str(img))
    snap_path = OUT / "ace-review" / "C-relayout-live.snapshot.json"
    subprocess.run([sys.executable, str(TOOLS / "ace_snapshot.py"), PAGE,
                    str(snap_path)], capture_output=True, text=True)
    import ace_review
    import net_integrity
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    review = ace_review.review(snap)
    audit = net_integrity.audit(snap)
    log("LIVE review %s errors=%d warnings=%d dead=%d parts=%d" %
        (review["verdict"], review["metrics"]["errors"], review["metrics"]["warnings"],
         audit["counts"]["errors"], len(snap["components"])))


if __name__ == "__main__":
    main()
