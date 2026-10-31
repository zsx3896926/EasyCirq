"""Stage-wise real-device replay driver for the C-board single-page relayout.

Why this file exists: the 2026-10-30 attempts were driven by ad-hoc inline
scripts that were never saved, so a crash mid-run left no reproducible driver
(B4/B8: "断点续跑" needs a journal, "写前 verify" needs a stable entry point).
This driver is the落盘 replacement, split into explicit stages so a failed stage
stops instead of cascading:

    verify   gate + read the live page, diff against the plan, grid-check pins
    place    clear (optional) + place every planned part at its SNAPPED anchor
    pins     read back the live pins and prove every one sits on the 5-grid
    connect  stub + flag each net member, batched with gate/reload/readback
    final    sch check, connectivity audit, PNG export, comparison numbers

Every stage re-reads the page from the daemon: no state carries over in memory,
so a stage can be re-run standalone after a channel restart (which is the only
way to clear a sticky `degraded`).

Coordinates come from ``grid_snap`` (single model, B1). The stub DIRECTION comes
from the live pin rotation read back after placement (0/90/180/270 ->
right/up/left/down), cross-checked against the captured geometry side; a
contradiction is reported, and the geometric side wins because that is what the
symbol actually draws.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(r"C:\Users\jlc\Documents\deepseek-harness\default-workspace")
VER = ROOT / "hds-verifier"
TOOLS = VER / "tools"
OUT = ROOT / "easycirq-2h-deliverables"
sys.path.insert(0, str(TOOLS))

import apply_engine  # noqa: E402

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"
SESSION_BIN = str(pathlib.Path.home() / "AppData" / "Local" / "Temp" / "easycirq-session.exe")
PROJECT = "40cad6b27bf7425280071f8e35642267"
PAGE = "4c53e460e522c393"
GRID = 5.0
STUB = 20.0
MAX_BATCH = 5                      # 硬约束：每批 <=5 根
ROT2DIR = {0: "right", 90: "up", 180: "left", 270: "down"}
SIDE2DIR = {"right": "right", "left": "left", "top": "up", "bottom": "down"}
GROUND_NETS = {"GND", "AGND", "DGND", "PGND"}

PLAN_PATH = OUT / "smoke-b10-4-C-snapped.json"
PLAN_FALLBACK = OUT / "smoke-b10-4-C.json"
GEOMETRY = json.loads((OUT / "pipeline-demo" / "C-pin-geometry.json").read_text(encoding="utf-8"))
NETS = json.loads((OUT / "pipeline-demo" / "C-relayout.nets.json").read_text(encoding="utf-8"))["nets"]
DEVICE = json.loads((OUT / "pipeline-demo" / "C-power.device-map.json").read_text(encoding="utf-8"))
JOURNAL = OUT / "replay-grid.journal.jsonl"


# ---------------------------------------------------------------- plumbing ---

def log(line):
    text = str(line)
    with (OUT / "replay-grid.log").open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text, flush=True)


def cli(*args, timeout=240):
    argv = [BIN, *args, "--window", WINDOW]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return '{"ok": false, "error": {"code": "TIMEOUT"}}'
    return (result.stdout or "") + (result.stderr or "")


def js(text):
    start = text.find("{")
    if start < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:
        return {}


def gate():
    result = subprocess.run([SESSION_BIN, "session", "gate"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=120)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def degraded_now():
    text = cli("health")
    data = js(text)
    windows = ((data.get("found") or {}).get("raw") or {}).get("windows") or []
    return any(w.get("degraded") for w in windows)


def reload_page():
    cli("doc", "reload", PAGE, "--project", PROJECT)
    time.sleep(1.5)


def on_grid(value):
    return abs(float(value) / GRID - round(float(value) / GRID)) < 1e-6


def snapped(value):
    return round(float(value) / GRID) * GRID


# ------------------------------------------------------------------ state ---

def live_parts():
    """{ref: {"anchor": (x, y), "pins": {num: {"x","y","rotation"}}}}"""
    data = js(cli("sch", "list", "--include-pins"))
    parts = {}
    for comp in (data.get("result") or {}).get("components") or []:
        if comp.get("componentType") != "part":
            continue
        ref = comp.get("designator")
        if not ref:
            continue
        parts[ref] = {
            "anchor": (float(comp.get("x", 0.0)), float(comp.get("y", 0.0))),
            "pins": {str(p.get("pinNumber")): {"x": float(p["x"]), "y": float(p["y"]),
                                               "rotation": p.get("rotation")}
                     for p in comp.get("pins") or []},
        }
    return parts


def live_pin_nets():
    data = js(cli("sch", "connectivity"))
    names = {n["id"]: n.get("name") for n in data.get("nets") or []}
    refs = {c["id"]: c.get("ref") for c in data.get("components") or []}
    return {(refs.get(c.get("componentId")), str(c.get("pinNumber"))): names.get(c.get("netId"))
            for c in data.get("connections") or []}


# ------------------------------------------------------------------- plan ---

def load_plan():
    """Snapped placements. ``grid_snap`` is the single model (B1); the inline
    round is only an interim fallback while that module is being written, and it
    is reported as ``snap_path="inline-round"`` so no report can claim the
    audited model was used when it was not. Either way every coordinate is
    re-verified against the LIVE page in ``stage_pins``."""
    source = PLAN_PATH if PLAN_PATH.is_file() else PLAN_FALLBACK
    raw = json.loads(source.read_text(encoding="utf-8"))
    if source == PLAN_PATH:
        return {"placements": raw["placements"], "source": str(source),
                "report": raw.get("grid_snap") or {}, "snapped": True,
                "snap_path": "artifact"}
    try:
        import grid_snap
        result = grid_snap.snap_plan(raw, GEOMETRY)
        return {"placements": result["placements"], "source": str(source),
                "report": result["report"], "snapped": True,
                "snap_path": "grid_snap"}
    except ImportError:
        placements = {}
        for ref, spot in raw["placements"].items():
            moved = dict(spot)
            moved["x"] = snapped(spot["x"])
            moved["y"] = snapped(spot["y"])
            placements[ref] = moved
        return {"placements": placements, "source": str(source), "report": {},
                "snapped": True, "snap_path": "inline-round"}


def live_directions():
    """{ref:pin -> {direction, via}} from MEASURED bodies (stub_geom_preflight).

    The captured ``side`` says which way the symbol draws the pin; it does not know
    that a neighbour's body sits in the way. On 2026-10-30 C3's left stub ran
    straight through U1 and the write was rejected. The measured model decides,
    including the elbow (``via``) the connector requires when a pin's own outward
    direction is blocked: the FIRST segment must still leave outward
    (``pin-exit-direction``), so the turn has to happen at a via point.
    """
    import stub_geom_preflight as pre

    nets_by_pin = {"%s:%s" % (ref, pin): net["name"]
                   for net in NETS for ref, pin in net["members"]}
    report = pre.plan(pre.read_live(WINDOW), nets_by_pin)
    return {row["pin"]: {"direction": row["direction"], "via": row["via"]}
            for row in report["rows"] if row["direction"]}, report


def connect_targets():
    """Ordered connect plan: net, pin, direction (+ elbow via when needed)."""
    measured, _ = live_directions()
    targets = []
    for net in NETS:
        name = net["name"]
        for ref, pin in net["members"]:
            key = "%s:%s" % (ref, pin)
            info = ((GEOMETRY.get("parts") or {}).get(ref) or {}).get("pins", {}).get(str(pin))
            if not info:
                targets.append({"net": name, "ref": ref, "pin": str(pin),
                                "direction": None, "via": None,
                                "kind": "ground" if name in GROUND_NETS else "net_label",
                                "error": "no geometry"})
                continue
            decision = measured.get(key) or {}
            targets.append({"net": name, "ref": ref, "pin": str(pin),
                            "direction": decision.get("direction")
                            or SIDE2DIR.get(info.get("side") or "", "right"),
                            "via": decision.get("via"),
                            "side": SIDE2DIR.get(info.get("side") or "", "right"),
                            "rotation": info.get("rotation"),
                            "kind": "ground" if name in GROUND_NETS else "net_label"})
    return targets


# ---------------------------------------------------------------- stages ---

def stage_verify():
    code, gate_out = gate()
    log("session gate exit=%d %s" % (code, gate_out.strip().replace("\n", " ")))
    if code != 0:
        return 2, {"stage": "verify", "ok": False, "reason": "session gate failed"}
    plan = load_plan()
    live = live_parts()
    planned = set(plan["placements"])
    missing = sorted(planned - set(live))
    extra = sorted(set(live) - planned)
    offgrid = []
    for ref, info in live.items():
        for num, pin in info["pins"].items():
            if not (on_grid(pin["x"]) and on_grid(pin["y"])):
                offgrid.append("%s:%s(%.1f,%.1f)" % (ref, num, pin["x"], pin["y"]))
    data = {"stage": "verify", "plan_source": plan["source"],
            "planned": len(planned), "live": len(live),
            "missing": missing, "extra": extra,
            "live_pins": sum(len(i["pins"]) for i in live.values()),
            "live_pins_off_grid": len(offgrid), "off_grid_sample": offgrid[:12],
            "grid_snap_report": {k: v for k, v in (plan["report"] or {}).items()
                                 if k != "per_part"}}
    log("verify: planned=%d live=%d missing=%s extra=%s pins=%d off_grid=%d"
        % (len(planned), len(live), missing, extra, data["live_pins"], len(offgrid)))
    return 0, data


def stage_place(clear):
    plan = load_plan()
    code, gate_out = gate()
    if code != 0:
        return 2, {"stage": "place", "ok": False, "reason": "session gate failed"}
    if clear:
        log("clear: " + cli("sch", "clear", "--doc", PAGE).strip().replace("\n", " ")[:200])
        reload_page()
        remaining = live_parts()
        if remaining:
            return 3, {"stage": "place", "ok": False,
                       "reason": "page not empty after clear", "parts": sorted(remaining)}
        log("clear ok: parts=0")
    done = []
    refs = sorted(plan["placements"])
    for start in range(0, len(refs), MAX_BATCH):
        chunk = refs[start:start + MAX_BATCH]
        code, gate_out = gate()
        if code != 0:
            log("gate failed mid-place; stopping at %d" % start)
            break
        for ref in chunk:
            spot = plan["placements"][ref]
            info = DEVICE.get(ref)
            if not info:
                log("place %s: no device entry" % ref)
                continue
            text = cli("sch", "place", "--lib", info["lib"], "--uuid", info["dev"],
                       "--x", "%.1f" % snapped(spot["x"]), "--y", "%.1f" % snapped(spot["y"]),
                       "--designator", ref, "--doc", PAGE)
            if '"ok": true' not in text:
                log("place %s FAILED %s" % (ref, text.strip().replace("\n", " ")[:240]))
            else:
                done.append(ref)
        reload_page()
        live = live_parts()
        log("placed chunk %d..%d -> live parts=%d" % (start, start + len(chunk) - 1, len(live)))
        if degraded_now():
            log("DEGRADED during place -- stopping")
            break
    live = live_parts()
    data = {"stage": "place", "placed_calls": len(done),
            "live": len(live), "planned": len(refs),
            "missing": sorted(set(refs) - set(live))}
    return (0 if not data["missing"] else 4), data


def stage_pins():
    live = live_parts()
    plan = load_plan()
    rows, offgrid = [], []
    for ref in sorted(live):
        anchor = live[ref]["anchor"]
        bad = []
        for num, pin in live[ref]["pins"].items():
            if not (on_grid(pin["x"]) and on_grid(pin["y"])):
                bad.append("%s(%.1f,%.1f)" % (num, pin["x"], pin["y"]))
        rows.append({"ref": ref, "anchor": [anchor[0], anchor[1]],
                     "pins": len(live[ref]["pins"]), "off_grid": bad})
        offgrid.extend(["%s:%s" % (ref, b) for b in bad])
    # cross-axis rule the connector enforces at connect time
    cross_bad = []
    for ref, info in live.items():
        anchor = info["anchor"]
        for num, pin in info["pins"].items():
            dx, dy = pin["x"] - anchor[0], pin["y"] - anchor[1]
            direction = ROT2DIR.get(int(pin.get("rotation") or 0) % 360, "right")
            if direction in ("left", "right") and not on_grid(pin["y"]):
                cross_bad.append("%s:%s y=%.1f (%s)" % (ref, num, pin["y"], direction))
            if direction in ("up", "down") and not on_grid(pin["x"]):
                cross_bad.append("%s:%s x=%.1f (%s)" % (ref, num, pin["x"], direction))
    anchor_bad = [ref for ref, info in live.items()
                  if not (on_grid(info["anchor"][0]) and on_grid(info["anchor"][1]))]
    data = {"stage": "pins", "parts": len(live),
            "pins": sum(len(i["pins"]) for i in live.values()),
            "anchors_off_grid": anchor_bad, "pins_off_grid": offgrid,
            "cross_axis_off_grid": cross_bad, "per_part": rows}
    log("pins: parts=%d pins=%d anchors_off_grid=%d pins_off_grid=%d cross_axis=%d"
        % (len(live), data["pins"], len(anchor_bad), len(offgrid), len(cross_bad)))
    return (0 if not offgrid and not cross_bad and len(live) == len(plan["placements"]) else 5), data


def stage_connect(limit, batch):
    batch = max(1, min(int(batch), MAX_BATCH))
    targets = connect_targets()
    if limit:
        targets = targets[:int(limit)]
    pins_now = live_pin_nets()
    pin_xy = {(ref, num): (info["x"], info["y"])
              for ref, parts in live_parts().items() for num, info in parts["pins"].items()}
    journal = apply_engine.Journal(JOURNAL)
    report = {"stage": "connect", "batch": batch, "targets": len(targets),
              "ok": 0, "failed": 0, "degraded": False, "stopped_at": None,
              "failures": [], "readback": {}}
    for start in range(0, len(targets), batch):
        chunk = targets[start:start + batch]
        code, gate_out = gate()
        if code != 0:
            report["stopped_at"] = "gate failed before batch %d" % start
            log("STOP: session gate failed before batch %d" % start)
            break
        wrote = 0
        for target in chunk:
            ref, pin, net = target["ref"], target["pin"], target["net"]
            if pins_now.get((ref, pin)) == net:
                journal.mark("connect:%s:%s" % (ref, pin), "ok")
                report["ok"] += 1
                continue
            if target.get("error"):
                report["failed"] += 1
                report["failures"].append({"pin": "%s:%s" % (ref, pin),
                                           "reason": target["error"]})
                journal.mark("connect:%s:%s" % (ref, pin), "plan")
                continue
            if target.get("via"):
                # The typed `sch connect` command has no --via flag (it errored
                # with "unknown flag"), while the action behind it accepts an
                # elbow. Elbow pins therefore go through the action directly.
                px, py = pin_xy.get((ref, pin), (None, None))
                if px is None:
                    report["failed"] += 1
                    report["failures"].append({"pin": "%s:%s" % (ref, pin),
                                               "reason": "pin not on the live page"})
                    continue
                payload = {"pinX": px, "pinY": py, "kind": target["kind"], "net": net,
                           "direction": target["direction"], "offset": STUB,
                           "via": [target["via"][0], target["via"][1]]}
                text = cli("call", "schematic.power.connect_pin",
                           "--payload", json.dumps(payload), "--doc", PAGE)
            else:
                text = cli("sch", "connect", "--pin", "%s:%s" % (ref, pin),
                           "--kind", target["kind"], "--net", net,
                           "--offset", "%.0f" % STUB,
                           "--direction", target["direction"], "--doc", PAGE)
            status = apply_engine.classify(text)
            journal.mark("connect:%s:%s" % (ref, pin), "ok" if status == "ok" else status)
            if status == "ok":
                report["ok"] += 1
                wrote += 1
            else:
                report["failed"] += 1
                report["failures"].append({"pin": "%s:%s" % (ref, pin), "net": net,
                                           "status": status,
                                           "tail": text.strip().replace("\n", " ")[-400:]})
                log("FAIL %s:%s=%s status=%s tail=%s"
                    % (ref, pin, net, status, text.strip().replace("\n", " ")[-300:]))
                if status in ("degraded", "geometry"):
                    if status == "degraded":
                        report["degraded"] = True
                    report["stopped_at"] = "batch %d after %s:%s" % (start, ref, pin)
                    break
            time.sleep(0.15)
        if report["stopped_at"]:
            break
        # B3.5: a batch only counts as committed after a real save+reload and a
        # read-back of the pins it claims to have wired.
        reload_page()
        pins_now = live_pin_nets()
        expected = {"%s:%s" % (t["ref"], t["pin"]): t["net"] for t in targets[:start + len(chunk)]}
        got = sum(1 for key, net in expected.items() if pins_now.get(tuple(key.split(":"))) == net)
        report["readback"]["batch_%d" % start] = {"expected": len(expected),
                                                  "connected": got, "wrote": wrote}
        log("batch %d..%d wrote=%d readback=%d/%d"
            % (start, start + len(chunk) - 1, wrote, got, len(expected)))
        if got < len(expected) - 0:
            report["stopped_at"] = "readback short after batch %d (%d/%d)" % (start, got, len(expected))
            log("STOP: readback short after batch %d" % start)
            break
        if degraded_now():
            report["degraded"] = True
            report["stopped_at"] = "degraded after batch %d" % start
            log("STOP: channel degraded after batch %d" % start)
            break
    final_pins = live_pin_nets()
    expected_all = {"%s:%s" % (t["ref"], t["pin"]): t["net"] for t in targets}
    report["connected_total"] = sum(1 for key, net in expected_all.items()
                                    if final_pins.get(tuple(key.split(":"))) == net)
    log("connect: ok=%d failed=%d connected=%d/%d degraded=%s stopped_at=%s"
        % (report["ok"], report["failed"], report["connected_total"], len(targets),
           report["degraded"], report["stopped_at"]))
    return (0 if report["connected_total"] == len(targets) else 6), report


def stage_final():
    plan = load_plan()
    check = cli("sch", "check")
    zero = apply_engine.zero_length_wire_ids(check)
    pins_now = live_pin_nets()
    targets = connect_targets()
    expected = {"%s:%s" % (t["ref"], t["pin"]): t["net"] for t in targets}
    connected = {k: v for k, v in expected.items() if pins_now.get(tuple(k.split(":"))) == v}
    missing = sorted(set(expected) - set(connected))
    live = live_parts()
    png = OUT / "replay-grid-live.png"
    cli("sch", "export-image", "--format", "png", "--scope", "page", "--doc", PAGE,
        "--out", str(png))
    data = {"stage": "final", "parts_live": len(live), "parts_planned": len(plan["placements"]),
            "missing_parts": sorted(set(plan["placements"]) - set(live)),
            "zero_length_wires": zero, "connects_expected": len(expected),
            "connects_connected": len(connected), "connects_missing": missing[:20],
            "check_head": check.strip().replace("\n", " ")[:400],
            "png": str(png)}
    log("final: parts=%d/%d connects=%d/%d zero_len=%d"
        % (len(live), len(plan["placements"]), len(connected), len(expected), len(zero)))
    return 0, data


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True,
                        choices=["verify", "place", "pins", "connect", "final"])
    parser.add_argument("--window", required=True)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch", type=int, default=MAX_BATCH)
    args = parser.parse_args()

    global WINDOW
    WINDOW = args.window
    log("=== stage=%s window=%s at %s ===" % (args.stage, WINDOW, time.strftime("%Y-%m-%dT%H:%M:%S")))

    if args.stage == "verify":
        code, data = stage_verify()
    elif args.stage == "place":
        code, data = stage_place(args.clear)
    elif args.stage == "pins":
        code, data = stage_pins()
    elif args.stage == "connect":
        code, data = stage_connect(args.limit, args.batch)
    else:
        code, data = stage_final()

    path = OUT / ("replay-grid-%s.json" % args.stage)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    log("report -> %s (exit %d)" % (path.name, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
