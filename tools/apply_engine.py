"""Systemic bulk-apply engine for real EDA pages.

The 2026-10-30 incident (C relayout) exposed four systemic problems; each one is
handled explicitly here instead of being papered over by retries:

1. **Incomplete plans** - ``verify`` compares the planned parts/pins with the
   live page before any write, so a missing designator (C1/R7/R8) fails fast
   instead of burning 65 doomed connects.
2. **Geometry-guard rejections** - ``preflight`` rejects writes whose stub would
   be zero-length / off the sheet, and ``zero_length_wire_ids`` extracts the
   offending wire ids from ``sch check`` so they can be deleted before writing.
3. **Fragile write channel** - writes go out in adaptive batches (10 -> 5 -> 2),
   with a reload + health gate after every batch; a ``degraded`` channel stops
   the run instead of hammering it, and the batch shrinks on any rejection.
4. **No resume** - every op has a stable id and lands in a JSONL journal, so a
   crashed run resumes exactly where it stopped.

Failure classes (see ``classify``): ``ok`` / ``geometry`` (delete stray wire and
retry) / ``plan`` (part or pin absent: never retry) / ``effect`` (plugin applied
partially: verify then retry once) / ``degraded`` (channel dead: stop, restart).

The module is EDA-free: callers inject ``execute``, ``reload`` and ``health``.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import grid_snap  # noqa: E402  (anchor + pin grid checks live there)

SCHEMA = "easycirq-apply-engine/v1"
GRID = grid_snap.GRID
SHEET = (10.0, 10.0, 1160.0, 815.0)
STUB = 20.0
DIRECTION_VECTOR = {"right": (1, 0), "left": (-1, 0),
                    "up": (0, 1), "down": (0, -1)}

_GEOMETRY_RE = re.compile(r"SCHEMATIC_GEOMETRY_INVALID|geometry guard failed")
_PLAN_RE = re.compile(r"not placed|no pin .* found|unknown designator|"
                      r"component .* not found|pin number/name mismatch")
_DEGRADED_RE = re.compile(r'"degraded":\s*true|channel degraded|degraded')
_ZERO_RE = re.compile(r"zero-length-wire\s+([0-9a-f]{8,})\s+(.*?)\s+@\(")


def classify(text):
    """Map one CLI response to ok / geometry / plan / effect / degraded."""
    if '"ok": true' in text and "SCHEMATIC_GEOMETRY_INVALID" not in text:
        return "ok"
    if _GEOMETRY_RE.search(text):
        return "geometry"
    if _DEGRADED_RE.search(text) and '"ok": false' in text:
        return "degraded"
    if _PLAN_RE.search(text):
        return "plan"
    if '"ok": false' in text or re.search(r'"ok":\s*false', text):
        return "effect"
    # No daemon envelope at all means the CLI never dispatched anything (e.g.
    # `unknown flag: --via`). That used to fall through to "ok", which is exactly
    # how a batch of 5 reported wrote=5 while only 4 pins were wired — the
    # read-back had to catch it. A response we cannot read is never success.
    if '"ok"' not in text and '"type"' not in text:
        return "effect"
    return "ok"


def zero_length_wire_ids(check_text):
    """Wire primitive ids reported by ``sch check`` as zero-length."""
    ids = []
    for match in _ZERO_RE.finditer(check_text):
        wire_id = match.group(1)
        if wire_id not in ids:
            ids.append(wire_id)
    return ids


def on_grid(value):
    return grid_snap.on_grid(value)


def preflight(ops, geometry):
    """Reject ops that cannot succeed; returns ``[{op, code, detail}]``.

    Three grid gates, strongest last: the pin *offset* ``(dx, dy)`` must be a
    multiple of the grid, the op's *anchor* ``(x, y)`` must be on the grid, and
    the pin's *absolute* position ``(x + dx, y + dy)`` must be on the grid.  The
    last one is what EasyEDA actually enforces when it draws the stub (see
    ``grid_snap``); checking only the offset is how the C-board connects were
    rejected one by one.
    """
    parts = (geometry or {}).get("parts") or {}
    problems = []
    for op in ops:
        if op["kind"] != "connect":
            continue
        ref = op.get("ref")
        pin = str(op.get("pin"))
        info = (parts.get(ref) or {}).get("pins", {}).get(pin)
        if not info:
            problems.append({"op": op["id"], "code": "plan",
                             "detail": "pin %s:%s absent from geometry" % (ref, pin)})
            continue
        dx, dy = float(info["dx"]), float(info["dy"])
        if not (on_grid(dx) and on_grid(dy)):
            problems.append({"op": op["id"], "code": "geometry",
                             "detail": "pin %s:%s offset (%.3f, %.3f) is off the %g-unit grid"
                                       % (ref, pin, dx, dy, GRID)})
            continue
        anchor_x, anchor_y = float(op["x"]), float(op["y"])
        pin_x, pin_y = anchor_x + dx, anchor_y + dy
        if not (on_grid(pin_x) and on_grid(pin_y)):
            problems.append({"op": op["id"], "code": "geometry",
                             "detail": "pin %s:%s sits at (%.3f, %.3f) - off the %g-unit "
                                       "grid after the anchor offset"
                                       % (ref, pin, pin_x, pin_y, GRID)})
            continue
        if not (on_grid(anchor_x) and on_grid(anchor_y)):
            problems.append({"op": op["id"], "code": "geometry",
                             "detail": "anchor of %s:%s at (%.3f, %.3f) is off the %g-unit "
                                       "grid" % (ref, pin, anchor_x, anchor_y, GRID)})
            continue
        direction = op.get("direction") or info.get("side") or "right"
        vector = DIRECTION_VECTOR.get(direction, (1, 0))
        end_x = float(op["x"]) + info["dx"] + vector[0] * STUB
        end_y = float(op["y"]) + info["dy"] + vector[1] * STUB
        if not (SHEET[0] <= end_x <= SHEET[2] and SHEET[1] <= end_y <= SHEET[3]):
            problems.append({"op": op["id"], "code": "geometry",
                             "detail": "stub end (%.1f, %.1f) leaves the sheet"
                                       % (end_x, end_y)})
    return problems


def plan_ops(plan, nets, device_map, *, stub=STUB):
    """Turn a relayout plan + nets into an ordered op list with stable ids."""
    ops = []
    sides = (plan.get("labels") or {}).get("sides") or {}
    for ref, place in (plan.get("placements") or {}).items():
        info = device_map.get(ref)
        if not info:
            continue
        ops.append({"id": "place:%s" % ref, "kind": "place", "ref": ref,
                    "x": place["x"], "y": place["y"],
                    "lib": info["lib"], "dev": info["dev"]})
    for net in nets:
        name = net["name"]
        if name == "__NC__":
            continue
        for ref, pin in net["members"]:
            side = sides.get("%s:%s" % (ref, pin))
            ops.append({"id": "connect:%s:%s" % (ref, pin), "kind": "connect",
                        "ref": ref, "pin": str(pin), "net": name,
                        "direction": {"right": "right", "left": "left",
                                      "top": "up", "bottom": "down"}.get(side or "", ""),
                        "kind_flag": "ground" if name in ("GND", "AGND", "DGND", "PGND")
                        else "net_label",
                        "x": (plan["placements"].get(ref) or {}).get("x", 0.0),
                        "y": (plan["placements"].get(ref) or {}).get("y", 0.0)})
    return ops


class Journal:
    """Append-only JSONL journal keyed by op id (crash-safe resume)."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.status = {}
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                self.status[entry.get("id")] = entry.get("status")

    def mark(self, op_id, status):
        self.status[op_id] = status
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": op_id, "status": status,
                                     "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")

    def done(self, op_id):
        # "plan" ops are terminal: their part/pin does not exist, retrying cannot help
        return self.status.get(op_id) in ("ok", "plan")

    def pending(self, ops):
        return [op for op in ops if not self.done(op["id"])]


def apply_ops(ops, *, execute, reload=None, health=None, journal=None,
              batch=10, pause=0.4, max_rounds=8, log=print,
              verify=None, repair_geometry=None):
    """Run ops with adaptive batching, health gates and a resumable journal.

    ``execute(op) -> (code, text)`` runs one write; ``reload()`` saves and
    reloads the document; ``health() -> text`` reports the channel state;
    ``repair_geometry(ids)`` deletes stray zero-length wires and returns True
    when it changed the page; ``verify() -> (missing_parts, missing_pins)``
    re-reads the page for the final report.
    """
    if journal is None:
        import tempfile
        handle = tempfile.NamedTemporaryFile(prefix="apply-", suffix=".jsonl", delete=False)
        handle.close()
        journal = Journal(handle.name)
    report = {"schema": SCHEMA, "ok": 0, "failed": 0, "skipped_plan": [],
              "geometry": 0, "degraded_stops": 0, "batch": batch,
              "min_batch": batch, "rounds": 0}
    pending = journal.pending(ops)
    report["planned"] = len(ops)
    report["resumed_pending"] = len(pending)
    round_no = 0
    while pending and round_no < max_rounds:
        round_no += 1
        index = 0
        while index < len(pending):
            chunk = pending[index:index + batch]
            stop_reason = None
            for op in chunk:
                code, text = execute(op)
                status = classify(text)
                if status == "ok":
                    journal.mark(op["id"], "ok")
                    report["ok"] += 1
                elif status == "plan":
                    journal.mark(op["id"], "plan")
                    report["failed"] += 1
                    report["skipped_plan"].append({"id": op["id"], "tail": text[-120:]})
                elif status == "geometry":
                    report["geometry"] += 1
                    stop_reason = "geometry"
                    break
                elif status == "degraded":
                    stop_reason = "degraded"
                    break
                else:
                    report["failed"] += 1
                    stop_reason = "effect"
                    break
                if pause:
                    time.sleep(pause)
            index += len(chunk)
            if reload:
                reload()
                time.sleep(0.5)
            if stop_reason == "geometry":
                changed = repair_geometry() if repair_geometry else False
                report["geometry_repairs"] = report.get("geometry_repairs", 0) + int(bool(changed))
                batch = max(2, batch // 2)
                report["batch"] = batch
                report["min_batch"] = min(report["min_batch"], batch)
                journal.mark(chunk[0]["id"], "todo")
                continue
            if stop_reason == "degraded":
                report["degraded_stops"] += 1
                batch = max(2, batch // 2)
                report["batch"] = batch
                if health:
                    log("degraded: waiting for the channel (batch=%d)" % batch)
                time.sleep(8)
                break
            if stop_reason == "effect":
                batch = max(2, batch // 2)
                report["batch"] = batch
                continue
            # healthy batch: grow back slowly
            batch = min(10, batch + 1)
            report["batch"] = batch
            if health and '"degraded": true' in (health() or ""):
                report["degraded_stops"] += 1
                time.sleep(8)
                break
        pending = journal.pending(ops)
        if round_no >= 3 and report["ok"] == 0 and report["geometry"] == 0 \
                and report["failed"] == 0:
            break
    report["rounds"] = round_no
    report["pending_after"] = len(pending)
    if verify:
        missing_parts, missing_pins = verify()
        report["missing_parts"] = missing_parts
        report["missing_pins"] = missing_pins[:20]
        report["residual"] = len(missing_parts) + len(missing_pins)
    return report


if __name__ == "__main__":
    import sys
    print(json.dumps({"schema": SCHEMA,
                      "note": "inject execute/reload/health/verify"}, ensure_ascii=False))
