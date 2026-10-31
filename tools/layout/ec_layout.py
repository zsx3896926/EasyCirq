#!/usr/bin/env python3
"""ec_layout — offline layout + routing toolchain for EasyCirq.

Contract for agents
-------------------
    ec_layout.py place  dump.json  --out placed.json      # layout for routing (HPWL + legalize)
    ec_layout.py route  dump.json  --place placed.json --out plan.json
    ec_layout.py report dump.json  --plan plan.json --place placed.json --out report.json
    ec_layout.py check  dump.json  --plan plan.json        # offline DRC-equivalent gate

Everything runs offline against a `pcb dump --include-copper` snapshot: no daemon,
no editor writes. Only when `check` passes does an agent apply the plan to EDA.

KPI gate (see KPI_KEYS below): unrouted legs, congestion cells, clearance
violations must be 0; vias and total length are reported for comparison, not
gated.
"""
import argparse
import json
import math
import random
import sys
from collections import defaultdict
from heapq import heappop, heappush

GRID = 10.0
CLEARANCE = 6.0
TRACE = 7.0
POWER_TRACE = 12.0
BUS_TRACE = 6.0
VIA_COST = 14.0
EDGE = 40.0
BUS_PREFIX = ("CAM_", "LCD_", "SD_")
POWER = {"+3V3", "VBUS", "BB_VIN", "VBAT_P", "BATT_M", "VDD_DW", "GND"}
HALO = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
KPI_KEYS = ("unrouted_legs", "congestion_cells", "clearance_violations", "nets_unconnected",
            "pad_layer_gaps", "pour_islands")
PLANE_VIA_KEY = "__plane_vias__"   # routed[PLANE_VIA_KEY] carries plane access vias
VIA_RADIUS = 10.0                  # mil, 0.5 mm via pad -> 10 mil radius
VIA_DIRTY_COST = 400.0             # cost of changing layers where the disc is not clear
VIA_BLOCK_MARGIN = 1.0             # mil of extra room a reserved via disc keeps
POUR_CLEARANCE = 8.0               # mil a pour keeps from other nets' copper
VIA_HISTORY_BUMP = 6.0             # negotiator pressure on a bad via site
VIA_SCORE_W = 3.0                  # weight of a bad via site in the pass score


# ── model ────────────────────────────────────────────────────────────────────
class Board:
    def __init__(self, dump):
        r = dump.get("result") or dump
        self.comps = {}
        for c in r.get("components") or []:
            pads = [{"net": p["net"], "pad": str(p.get("padNumber")),
                     "x": float(p["x"]), "y": float(p["y"]),
                     "dx": float(p["x"]) - float(c["x"]), "dy": float(p["y"]) - float(c["y"]),
                     "w": float(p.get("width") or 20), "h": float(p.get("height") or 20),
                     "layer": int(p.get("layer") or 1)}
                    for p in (c.get("pads") or []) if p.get("net")]
            b = c.get("bbox") or {}
            self.comps[c["designator"]] = {
                "x": float(c["x"]), "y": float(c["y"]), "rotation": float(c.get("rotation") or 0),
                "w": float(b.get("maxX", 0)) - float(b.get("minX", 0)) or 40.0,
                "h": float(b.get("maxY", 0)) - float(b.get("minY", 0)) or 40.0,
                "pads": pads,
            }
        bb = (r.get("outline") or {}).get("bbox") or {}
        self.x0, self.y0 = EDGE, EDGE
        self.x1 = float(bb.get("maxX", 2756)) - EDGE
        self.y1 = float(bb.get("maxY", 1968)) - EDGE
        self.w = int((self.x1 - self.x0) // GRID)
        self.h = int((self.y1 - self.y0) // GRID)
        self.nets = defaultdict(list)
        for des, c in self.comps.items():
            for p in c["pads"]:
                self.nets[p["net"]].append({**p, "des": des})

    def cell(self, x, y):
        return int((x - self.x0) // GRID), int((y - self.y0) // GRID)

    def center(self, cx, cy):
        return self.x0 + (cx + 0.5) * GRID, self.y0 + (cy + 0.5) * GRID

    def pad_blocked(self):
        blocked, own, padcells = {}, defaultdict(set), defaultdict(set)
        for des, c in self.comps.items():
            for p in c["pads"]:
                # NOTE: inflating by CLEARANCE + trace/2 was tried and measured
                # WORSE (clearance 26 -> 32, unconnected 5 -> 8): the larger keep-out
                # squeezes the fan-outs and the negotiator finds uglier detours. The
                # remaining violations need escape vias, not a bigger blanket keep-out.
                hw, hh = p["w"] / 2 + CLEARANCE, p["h"] / 2 + CLEARANCE
                ax0, ay0 = self.cell(p["x"] - hw, p["y"] - hh)
                ax1, ay1 = self.cell(p["x"] + hw, p["y"] + hh)
                ox0, oy0 = self.cell(p["x"] - p["w"] / 2, p["y"] - p["h"] / 2)
                ox1, oy1 = self.cell(p["x"] + p["w"] / 2, p["y"] + p["h"] / 2)
                for gx in range(max(0, ax0), min(self.w, ax1 + 1)):
                    for gy in range(max(0, ay0), min(self.h, ay1 + 1)):
                        if ox0 <= gx <= ox1 and oy0 <= gy <= oy1:
                            own[p["net"]].add((gx, gy))
                            padcells[(gx, gy)].add(p["net"])
                        else:
                            blocked[(gx, gy)] = p["net"]
        self.pad_cells = padcells
        return blocked, own


# Per-net width overrides, e.g. thin traces for the legs that cannot fit the
# default width in a dense fan-out (set by the caller, never by the router).
WIDTH_OVERRIDE = {}


def route_width(net):
    if net in WIDTH_OVERRIDE:
        return WIDTH_OVERRIDE[net]
    if net in POWER:
        return POWER_TRACE
    if net.startswith(BUS_PREFIX):
        return BUS_TRACE
    return TRACE


# ── placement ────────────────────────────────────────────────────────────────
def pad_xy(c, p, rot=None):
    """Pad absolute position for a component at c['x'],c['y'].

    Offsets come from the load-time dx/dy (NOT from `p['x'] - c['x']`): once the
    component moves, that subtraction silently recomputes a wrong offset and the
    optimiser then scores a placement that does not match the geometry.
    """
    a = math.radians(c["rotation"] if rot is None else rot)
    dx, dy = p.get("dx", p["x"] - c["x"]), p.get("dy", p["y"] - c["y"])
    return c["x"] + dx * math.cos(a) - dy * math.sin(a), c["y"] + dx * math.sin(a) + dy * math.cos(a)


def hpwl(comps):
    boxes = defaultdict(lambda: [1e18, 1e18, -1e18, -1e18])
    for c in comps.values():
        for p in c["pads"]:
            x, y = pad_xy(c, p)
            b = boxes[p["net"]]
            b[0] = min(b[0], x); b[1] = min(b[1], y); b[2] = max(b[2], x); b[3] = max(b[3], y)
    return sum((b[2] - b[0]) + (b[3] - b[1]) for b in boxes.values())


def n_overlaps(comps):
    items = list(comps.values())
    n = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if (abs(a["x"] - b["x"]) * 2 < a["w"] + b["w"] + 2 * CLEARANCE and
                    abs(a["y"] - b["y"]) * 2 < a["h"] + b["h"] + 2 * CLEARANCE):
                n += 1
    return n


def n_outside(comps, board):
    n = 0
    for c in comps.values():
        if (c["x"] - c["w"] / 2 < board.x0 or c["y"] - c["h"] / 2 < board.y0 or
                c["x"] + c["w"] / 2 > board.x1 or c["y"] + c["h"] / 2 > board.y1):
            n += 1
    return n


def _collides(c, others, pad=CLEARANCE):
    for o in others:
        if c is o:
            continue
        if (abs(c["x"] - o["x"]) * 2 < c["w"] + o["w"] + 2 * pad and
                abs(c["y"] - o["y"]) * 2 < c["h"] + o["h"] + 2 * pad):
            return o
    return None


def legalize(comps, board, rounds=25):
    """Spread parts until no courtyard collision remains.

    Bigger parts are placed first (they have the least freedom), each one then
    searches outward in rings of RING mil for a free slot.  A pure "push the
    smaller one away" loop oscillated forever against the board edge (8 overlaps
    survived); placing in decreasing area order converges because the hard parts
    claim space before the small ones fill the gaps.
    """
    order = sorted(comps.values(), key=lambda c: -(c["w"] * c["h"]))
    RING = 25.0
    for c in order:
        c["x"] = min(max(c["x"], board.x0 + c["w"] / 2), board.x1 - c["w"] / 2)
        c["y"] = min(max(c["y"], board.y0 + c["h"] / 2), board.y1 - c["h"] / 2)
        if not _collides(c, order):
            continue
        placed_tries = 0
        radius = 0.0
        while placed_tries < 4000:
            radius += RING
            for dx in range(-int(radius / RING), int(radius / RING) + 1):
                for dy in range(-int(radius / RING), int(radius / RING) + 1):
                    if abs(dx) * RING + abs(dy) * RING != radius:
                        continue
                    cand = dict(c)
                    cand["x"] = min(max(c["x"] + dx * RING, board.x0 + c["w"] / 2),
                                    board.x1 - c["w"] / 2)
                    cand["y"] = min(max(c["y"] + dy * RING, board.y0 + c["h"] / 2),
                                    board.y1 - c["h"] / 2)
                    placed_tries += 1
                    if not _collides(cand, order):
                        c.update(cand)
                        break
                else:
                    continue
                break
            if not _collides(c, order):
                break
            if radius > 1200:
                break
    return comps


def _ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0] * len(vals)
    for rank, i in enumerate(order):
        out[i] = rank
    return out


def _spearman(a, b):
    if len(a) < 2:
        return 0.0
    ra, rb = _ranks(a), _ranks(b)
    m = (len(a) - 1) / 2.0
    num = sum((ra[i] - m) * (rb[i] - m) for i in range(len(a)))
    den = math.sqrt(sum((x - m) ** 2 for x in ra) * sum((x - m) ** 2 for x in rb))
    return num / den if den else 0.0


ROUTABLE_W = 600.0   # mil-equivalent cost of one unit of pin-order disorder

# Placement terms for the legs the router actually fails on.  They are reported
# in mil-equivalents so they trade against HPWL on the same scale instead of
# being an invisible tie-breaker.
FACE_W = 1500.0      # per unit of (1 - cos) pad-field misalignment, range 0..2
# Opt-in, NOT default: btn_w=800 buys unrouted 9 -> 6 on RetroCam-02 but costs
# 19% HPWL (42,202 -> 50,103) and one congestion cell, so it fails the gate it
# is supposed to improve. Enabled per run until the GND/pour work lands.
BTN_W = 0.0          # per 1000 mil of button-leg length
BTN_SCALE = 1000.0


def bus_order_penalty(comps, mcu="U5"):
    """How far each bus group is from a PLANAR bundle, measured on live geometry.

    When a group's source-side order and destination-side order disagree (|rho| < 1)
    it cannot be routed as a parallel bundle without crossings, and its legs are
    exactly the ones that die in the dense fan-out. HPWL alone never sees this, so
    placement used to be optimised into a corner where routing could not finish
    (the five dead legs at the U5 pad column).
    """
    penalty = 0.0
    for prefix in ("CAM_D", "LCD_", "SD_"):
        per_net = defaultdict(list)
        for des, c in comps.items():
            for p in c.get("pads") or []:
                if not p["net"].startswith(prefix):
                    continue
                x, y = pad_xy(c, p)
                per_net[p["net"]].append((des, x, y))
        src, dst = [], []
        for net, pts in per_net.items():
            if len(pts) < 2:
                continue
            pts = sorted(pts, key=lambda t: 0 if t[0] != mcu else 1)
            src.append(pts[0][1])
            dst.append(pts[1][2])          # destination side orders along y
        if len(src) >= 2:
            penalty += 1.0 - abs(_spearman(src, dst))
    return penalty


def _unit(vx, vy):
    """Unit vector, or (0, 0) when the input has no direction."""
    length = math.hypot(vx, vy)
    return (vx / length, vy / length) if length > 1e-9 else (0.0, 0.0)


def pad_centroid(c):
    """Absolute centroid of a component's connected pads (NOT its body centre).

    U5 is a three-sided module: the pad field's centroid sits ~100 mil off the
    body centre, and that offset is the only thing that says which way the part
    "opens".  Using the body centre would score every rotation as identical.
    """
    pads = c["pads"]
    if not pads:
        return c["x"], c["y"]
    sx = sy = 0.0
    for p in pads:
        x, y = pad_xy(c, p)
        sx += x
        sy += y
    return sx / len(pads), sy / len(pads)


def escape_face_penalty(comps, mcu="U5", peripherals=("J3", "J4", "J5")):
    """How badly the MCU's pad field points away from the parts it must reach.

    The dead legs on RetroCam-02 are +3V3/GND/BTN_* — they leave the U5 pad
    column, and none of them is a bus.  The bus-order term cannot see that, so
    placement happily accepted rotations that faced the pad field into the
    corner of the board.  This measures the angle between

      * the direction from the MCU body centre to its pad centroid, and
      * the direction from the MCU to the centroid of the peripheral pads.

    Returns 1 - cos(theta) in [0, 2]; direction-free inputs score 0.
    """
    m = comps.get(mcu)
    if not m:
        return 0.0
    pcx, pcy = pad_centroid(m)
    ux, uy = _unit(pcx - m["x"], pcy - m["y"])
    if ux == 0.0 and uy == 0.0:
        return 0.0
    sx = sy = n = 0.0
    for des in peripherals:
        c = comps.get(des)
        if not c:
            continue
        for p in c["pads"]:
            x, y = pad_xy(c, p)
            sx += x
            sy += y
            n += 1
    if not n:
        return 0.0
    vx, vy = _unit(sx / n - m["x"], sy / n - m["y"])
    if vx == 0.0 and vy == 0.0:
        return 0.0
    return 1.0 - max(-1.0, min(1.0, ux * vx + uy * vy))


def button_leg_penalty(comps, mcu="U5", prefixes=("BTN",), scale=BTN_SCALE):
    """Straight-line length of every button leg, in units of `scale` mil.

    HPWL prices a leg by its bounding box, so a 1,200 mil BTN_UP that runs the
    length of the board costs the same as a tidy 400 mil one whenever the other
    nets dominate the box.  These are exactly the legs that die, so they get
    their own term instead of hiding inside a net-averaged number.
    """
    per_net = defaultdict(list)
    for des, c in comps.items():
        for p in c["pads"]:
            if p["net"].startswith(prefixes):
                x, y = pad_xy(c, p)
                per_net[p["net"]].append((des, x, y))
    total = 0.0
    for pts in per_net.values():
        if len(pts) < 2:
            continue
        mcu_pts = [t for t in pts if t[0] == mcu]
        if len(mcu_pts) != 1:
            continue
        _, mx, my = mcu_pts[0]
        others = [math.hypot(x - mx, y - my) for des, x, y in pts if des != mcu]
        if others:
            total += min(others)
    return total / scale


def placement_cost(comps, board, face_w=None, btn_w=None, bus_w=None):
    """The placement objective, exposed as a function so it can be tested.

    HPWL alone optimises placement into corners where the router cannot finish.
    Three measured terms steer it, and each is a separate knob because they do
    NOT all help:

      * bus_w  — pin-order disorder. Worth 600 on its own, but on RetroCam-02 it
                 cost 13,600 mil of HPWL (43,301 -> 56,934) for zero routing gain:
                 the five dead legs are +3V3/GND/BTN_*, so keep it optional.
      * face_w — pad-field facing, see `escape_face_penalty`.
      * btn_w  — button leg length, see `button_leg_penalty`.
    """
    face_w = FACE_W if face_w is None else face_w
    btn_w = BTN_W if btn_w is None else btn_w
    bus_w = ROUTABLE_W if bus_w is None else bus_w
    return (hpwl(comps) + 1e6 * n_overlaps(comps) + 1e6 * n_outside(comps, board)
            + bus_w * bus_order_penalty(comps)
            + face_w * escape_face_penalty(comps)
            + btn_w * button_leg_penalty(comps))


def optimize_placement(board, iters=40000, seed=7, face_w=None, btn_w=None, bus_w=None):
    comps = {d: {**c, "pads": list(c["pads"])} for d, c in board.comps.items()}
    cur = {d: dict(c) for d, c in comps.items()}

    def cost(c):
        return placement_cost(c, board, face_w, btn_w, bus_w)

    cur_cost = cost(cur)
    best, best_cost = {d: dict(c) for d, c in cur.items()}, cur_cost
    rnd = random.Random(seed)
    names = list(cur)
    for it in range(iters):
        T = 400.0 * (1.0 / 400.0) ** (it / max(1, iters - 1))
        d = rnd.choice(names)
        cand = dict(cur[d])
        m = rnd.random()
        if m < 0.75:
            step = rnd.choice((25, 50, 100, 200, 400))
            cand["x"] = min(max(cand["x"] + rnd.choice((-step, step)), board.x0), board.x1)
            cand["y"] = min(max(cand["y"] + rnd.choice((-step, step)), board.y0), board.y1)
        elif m < 0.93:
            cand["rotation"] = (cand["rotation"] + 90.0) % 360.0
        else:
            cand["x"] = rnd.uniform(board.x0, board.x1)
            cand["y"] = rnd.uniform(board.y0, board.y1)
        old, cur[d] = cur[d], cand
        nc = cost(cur)
        if nc <= cur_cost or rnd.random() < math.exp((cur_cost - nc) / max(T, 1e-6)):
            cur_cost = nc
            if nc < best_cost:
                best_cost, best = nc, {k: dict(v) for k, v in cur.items()}
        else:
            cur[d] = old
    legalize(best, board)
    return {d: {"x": c["x"], "y": c["y"], "rotation": c["rotation"]} for d, c in best.items()}


def apply_placement(board, placed):
    """Move components (and their pads) to the planned positions in place."""
    for des, pos in placed.items():
        c = board.comps.get(des)
        if not c:
            continue
        dx, dy = pos["x"] - c["x"], pos["y"] - c["y"]
        drot = pos["rotation"] - c["rotation"]
        for p in c["pads"]:
            if drot:
                a = math.radians(drot)
                px, py = p["x"] - c["x"], p["y"] - c["y"]
                p["x"] = pos["x"] + px * math.cos(a) - py * math.sin(a)
                p["y"] = pos["y"] + px * math.sin(a) + py * math.cos(a)
            else:
                p["x"] += dx
                p["y"] += dy
        c["x"], c["y"], c["rotation"] = pos["x"], pos["y"], pos["rotation"]
    # Rebuild the net index from the moved pads. `Board.nets` is built once at load
    # time and holds COPIES, so without this the router (and every diagnostic that
    # reads nets) kept using PRE-placement pad coordinates while `comps` moved —
    # which is exactly why the bus-order tool contradicted itself (-0.90 direct vs
    # +1.00 through the identity transform).
    board.nets = defaultdict(list)
    for des, c in board.comps.items():
        for p in c["pads"]:
            board.nets[p["net"]].append({**p, "des": des})


# ── routing ──────────────────────────────────────────────────────────────────
def _via_reach(radius=VIA_RADIUS, width=TRACE):
    return int(math.ceil((radius + width / 2 + CLEARANCE) / GRID))


def build_pad_via_block(board, radius=VIA_RADIUS, margin=VIA_BLOCK_MARGIN):
    """Cells where a via would sit too close to a PAD of some net.

    Maps cell -> set of nets that already own copper there.  A net may still
    put a via on its OWN pad ring, so the check is "owner != me", not "occupied".
    `margin` follows the same rule as `stamp_via_block`: routing only enforces
    overlap, the KPI reports the rest.
    """
    block = defaultdict(set)
    for net, pads in board.nets.items():
        for p in pads:
            pc = board.cell(p["x"], p["y"])
            need = radius + max(p["w"], p["h"]) / 2 + margin
            r = int(math.ceil(need / GRID))
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if math.hypot(dx, dy) * GRID > need:
                        continue
                    block[(pc[0] + dx, pc[1] + dy)].add(net)
    return block


def stamp_via_block(block, path, net, width, margin=VIA_BLOCK_MARGIN):
    """Reserve the disc a via would need around every cell this path occupies.

    `margin` decides how much of the clearance is enforced during routing.
    Reserving the FULL clearance (VIA_RADIUS + w/2 + CLEARANCE) around every
    track made the board unroutable (measured: unrouted 7 -> 15, because a via
    then needs a 26 mil clear disc on four layers).  Reserving only the overlap
    keeps true shorts out of the plan and leaves the remaining spacing to the
    KPI, which reports it honestly.
    """
    need = VIA_RADIUS + width / 2 + margin
    reach = int(math.ceil(need / GRID))
    for cell in path:
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if math.hypot(dx, dy) * GRID > need:
                    continue
                block.setdefault((cell[0] + dx, cell[1] + dy), set()).add(net)


def _pad_layers(pad, layer_ok):
    """Which layers a leg may start/end on at this pad.

    SMD pads anchor a leg to their own layer — starting on `preferred_layer`
    instead produced plans where 72 of 188 pads had their nearest copper on a
    different layer with no via anywhere near it: "connected" on paper, open
    circuit in copper.  Through-hole pads come out of the dump as layer 12,
    which is not a routing layer, so they may leave from any layer.
    """
    lay = int(pad.get("layer") or 1)
    return {lay} if lay in layer_ok else None


def astar(board, start, goal, forbidden, cost, pref, allowed, layers=2, layer_ok=None,
          via_block=None, net=None, via_cost=None, start_layer=None, goal_layers=None):
    def h(c):
        return abs(c[0] - goal[0]) + abs(c[1] - goal[1])

    if layer_ok is None:
        layer_ok = set(range(1, layers + 1))
    if pref not in layer_ok:
        pref = min(layer_ok)
    if start_layer in layer_ok:
        pref = start_layer
    vcost = VIA_COST if via_cost is None else via_cost
    s = (start[0], start[1], pref)
    heap, came, best = [(h(s), 0.0, s)], {}, {s: 0.0}
    while heap:
        _, g, cur = heappop(heap)
        if cur[:2] == goal and (goal_layers is None or cur[2] in goal_layers):
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return list(reversed(path))
        if g > best.get(cur, 1e18) + 1e-9:
            continue
        x, y, l = cur
        for dx, dy, cost_mul in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                                 (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < board.w and 0 <= ny < board.h):
                continue
            if (nx, ny) in forbidden and (nx, ny) != goal and (nx, ny) not in allowed:
                continue
            nxt = (nx, ny, l)
            ng = g + cost_mul + cost.get(nxt, 0.0)
            if ng < best.get(nxt, 1e18) - 1e-9:
                best[nxt] = ng
                came[nxt] = cur
                heappush(heap, (ng + h(nxt), ng, nxt))
        # via to an adjacent layer (generalised so a 4-layer stackup can be
        # modelled: crossing nets then legally share an (x,y) cell)
        for other in (l - 1, l + 1):
            if other not in layer_ok:
                continue
            dirty = 0.0
            if via_block:
                # A via needs a clear disc on every layer.  Price it: refusing the
                # transition outright was measured at unrouted 7 -> 15, because a
                # leg that simply must change layers then has nowhere to go.
                owners = via_block.get((x, y))
                if owners and any(o != net for o in owners):
                    dirty = VIA_DIRTY_COST
            if (x, y) not in forbidden or (x, y) in allowed or (x, y) == goal:
                nxt = (x, y, other)
                ng = g + vcost + dirty + cost.get(nxt, 0.0)
                if ng < best.get(nxt, 1e18) - 1e-9:
                    best[nxt] = ng
                    came[nxt] = cur
                    heappush(heap, (ng + h(nxt), ng, nxt))
    return None


def mst_edges(pads):
    n = len(pads)
    if n < 2:
        return []
    inside, edges = {0}, []
    while len(inside) < n:
        best = None
        for i in inside:
            for j in range(n):
                if j in inside:
                    continue
                d = (pads[i]["x"] - pads[j]["x"]) ** 2 + (pads[i]["y"] - pads[j]["y"]) ** 2
                if best is None or d < best[0]:
                    best = (d, i, j)
        edges.append((best[1], best[2]))
        inside.add(best[2])
    return edges


def preferred_layer(net, layers=4):
    """Dedicate inner layers to the camera/LCD/SD buses. Giving buses their own
    layer is the only way length matching gets room: with everything crammed into
    L1/L2 the board filled up and zero meanders could be placed (measured twice)."""
    if layers >= 4:
        if net.startswith("CAM_"):
            return 3
        if net.startswith(("LCD_", "SD_")):
            return 4
    if net.startswith(BUS_PREFIX) or net.startswith("USB_"):
        return 2
    return 1


def via_conflicts(board, path, used, pad_forbid, net, width, radius=VIA_RADIUS, margin=1.0):
    """Is a layer change in this path actually SHORTING another net?

    A via is an annular ring on EVERY layer.  The router used to drop one
    wherever a path changed layers and never checked it at all: with via checks
    added, the plan the old gate called "clearance 0" actually had 103 via-track
    and 72 via-pad violations.

    Only a true overlap is rejected here.  Rejecting at the full spacing
    distance instead was measured worse by a wide margin (unrouted 7 -> 33): a
    dense board has almost no 26 mil clear disc on four layers, so every long
    path died.  Spacing remains a reported KPI, not a per-path veto.
    """
    need = radius + width / 2 + margin
    reach = int(math.ceil(need / GRID))
    for a, b in zip(path, path[1:]):
        if a[2] == b[2]:
            continue
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if math.hypot(dx, dy) * GRID > need:
                    continue
                cell = (a[0] + dx, a[1] + dy)
                owners = board.pad_cells.get(cell)
                if owners and any(o != net for o in owners):
                    return True
                for layer in range(1, 5):
                    nets = used.get((cell[0], cell[1], layer))
                    if nets and any(o != net for o in nets):
                        return True
    return False


def path_conflicts(board, path, routed, net, width):
    """Line-segment-level spacing test for a candidate path against everything routed
    so far. This is the structural constraint the cost model lacks: a run closer than
    CLEARANCE is rejected outright instead of being merely expensive."""
    new = []
    for a, b in zip(path, path[1:]):
        if a[2] != b[2] or a[:2] == b[:2]:
            continue
        ax, ay = board.center(a[0], a[1])
        bx, by = board.center(b[0], b[1])
        new.append((a[2], min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), ax, ay, bx, by))
    for other, paths in routed.items():
        # GND is carried by a POUR on the real board, and a pour is checked with the
        # pour clearance rule, not the track rule. Treating its temporary routing as
        # a track obstacle ate the corridors that the last legs needed.
        if other == net or other == "GND":
            continue
        need = (width + route_width(other)) / 2 + CLEARANCE - 0.5
        for p in paths:
            for a, b in zip(p, p[1:]):
                if a[2] != b[2] or a[:2] == b[:2]:
                    continue
                ax2, ay2 = board.center(a[0], a[1])
                bx2, by2 = board.center(b[0], b[1])
                xmin, xmax = min(ax2, bx2), max(ax2, bx2)
                ymin, ymax = min(ay2, by2), max(ay2, by2)
                for (layer, nx0, ny0, nx1, ny1, x1, y1, x2, y2) in new:
                    if layer != a[2]:
                        continue
                    if (nx1 + need < xmin or xmax + need < nx0
                            or ny1 + need < ymin or ymax + need < ny0):
                        continue
                    if _seg_seg(x1, y1, x2, y2, ax2, ay2, bx2, by2) < need:
                        return True
    return False


def free_via_site(board, cell, net, pad_forbid, used, width, rings=(1, 2, 3, 4),
                  radius=VIA_RADIUS):
    """Nearest cell to `cell` where a via keeps full clearance from other copper.

    The whole point of via-directed routing: decide the layer change FIRST, at a
    spot that is legal on all layers, instead of letting the A* drop a via
    wherever it happens to switch and discovering 196 violations afterwards.
    """
    need = radius + width / 2 + CLEARANCE
    reach = int(math.ceil(need / GRID))
    for r in rings:
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                cx, cy = cell[0] + dx, cell[1] + dy
                if not (0 <= cx < board.w and 0 <= cy < board.h):
                    continue
                owner = pad_forbid.get((cx, cy))
                if owner is not None and owner != net:
                    continue
                ok = True
                for ex in range(-reach, reach + 1):
                    for ey in range(-reach, reach + 1):
                        if math.hypot(ex, ey) * GRID > need:
                            continue
                        # The whole DISC must clear other nets' pads, not just
                        # the centre cell.  Checking only the centre chose sites
                        # that sat on a neighbour's keep-out ring (via-pad
                        # violations went 85 -> 104 with the "legal" sites).
                        owner = pad_forbid.get((cx + ex, cy + ey))
                        if owner is not None and owner != net:
                            ok = False
                            break
                        for layer in range(1, 5):
                            s = used.get((cx + ex, cy + ey, layer))
                            if s and any(o != net for o in s):
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        break
                if ok:
                    return cx, cy
    return None


def flat_route(board, start, goal, layer, forbidden, cost, allowed):
    """A route confined to ONE layer: it can never place a via."""
    return astar(board, start, goal, forbidden, cost, 1, allowed, max(layer, 1),
                 layer_ok={layer}, start_layer=layer, goal_layers={layer})


def _join(*parts):
    """Concatenate path pieces, dropping the repeated joint cells."""
    out = []
    for part in parts:
        if not part:
            continue
        if out and out[-1][:2] == part[0][:2] and out[-1][2] == part[0][2]:
            out.extend(part[1:])
        else:
            out.extend(part)
    return out


def plan_pad_via_sites(board, pad_forbid, max_ring=3, radius=VIA_RADIUS):
    """One legal via site per SMD pad, chosen BEFORE anything is routed.

    Measured on RetroCam-02: 174 of 176 SMD pads have a site within 3 cells when
    sites are chosen against the pads alone.  The router never found them because
    it decides the layer change *during* the A* search, by cost — so 177 vias
    ended up spread over 196 violations.  Deciding the sites up front makes the
    legal choice the only choice.
    """
    sites, taken = {}, set()
    need = radius + CLEARANCE
    for net, pads in sorted(board.nets.items()):
        for p in pads:
            lay = int(p.get("layer") or 1)
            if lay not in (1, 2, 3, 4):
                continue                      # through-hole: no via needed
            cell = board.cell(p["x"], p["y"])
            site = free_via_site(board, cell, net, pad_forbid, {}, TRACE,
                                 rings=tuple(range(1, max_ring + 1)), radius=radius)
            if site is None or site in taken:
                continue
            taken.add(site)
            sites[(p["des"], p["pad"])] = site
    return sites


def reserve_via_discs(board, sites, width=TRACE, radius=VIA_RADIUS):
    """Cells a via disc occupies; other nets may not run tracks through them."""
    need = radius + width / 2 + CLEARANCE
    reach = int(math.ceil(need / GRID))
    cells = set()
    for (cx, cy) in sites.values():
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if math.hypot(dx, dy) * GRID > need:
                    continue
                cells.add((cx + dx, cy + dy))
    return cells


def plan_via_first_leg(board, a, b, net, sites, layer_ok, pad_forbid, cost, allowed,
                       layers, mid_hint=None, blocked=None):
    """Route a leg through the PRE-PLANNED via sites instead of hunting for one.

    Endpoint that has a via site: stub from the pad to the site on the pad's own
    layer, then the site is the layer-change point.  Endpoint that has none
    (through-hole pad): the pad cell itself may be used on any layer.
    """
    sc, gc = board.cell(a["x"], a["y"]), board.cell(b["x"], b["y"])
    la = int(a.get("layer") or 1)
    lb = int(b.get("layer") or 1)
    sa = sites.get((a["des"], a["pad"]))
    sb = sites.get((b["des"], b["pad"]))
    forbidden = {c for c, o in pad_forbid.items() if o != net} | set(blocked or ())
    # llowed (pad escape bands) must not override another net's reserved via
    # disc: in astar llowed beats orbidden, so subtracting is required.
    safe_allowed = set(allowed) - set(blocked or ())
    if la not in layer_ok:
        sa = None
        la = None
    if lb not in layer_ok:
        sb = None
        lb = None
    if (sa is None and sb is None) or (la is not None and la == lb and sb is None):
        # both ends already sit on the same routable layer, or both are holes
        lay = lb if lb in layer_ok else (la if la in layer_ok else min(layer_ok))
        p = flat_route(board, sc, gc, lay, forbidden, cost, safe_allowed)
        if p:
            return p

    pa = sa if sa is not None else sc
    pb = sb if sb is not None else gc
    starts = [mid_hint] if mid_hint in layer_ok else []
    starts += [preferred_layer(net, layers)] + sorted(layer_ok)
    for mid in starts:
        if mid not in layer_ok:
            continue
        middle = flat_route(board, pa, pb, mid, forbidden, cost, safe_allowed)
        if not middle:
            continue
        parts = []
        if sa is not None:
            parts.append([(sc[0], sc[1], la), (sa[0], sa[1], la)])
        parts.append(middle)
        if sb is not None:
            parts.append([(sb[0], sb[1], lb), (gc[0], gc[1], lb)])
        path = _join(*parts)
        if path:
            return path
    return None


def plan_via_leg(board, a, b, sc, gc, net, layer_ok, pad_forbid, used, history, layers,
                 cost=None, allowed=None):
    """pad -> legal via site -> (other layer) -> legal via site -> pad.

    Returns the concatenated path, or None to let the caller fall back to the
    free-form 3D A*.  Two legal vias instead of however many the search felt like.
    """
    cost = cost or {}
    allowed = allowed or set()
    pref = preferred_layer(net, layers)
    if pref not in layer_ok:
        pref = min(layer_ok)
    # Try the preferred layer first, then the others.  Forcing the preferred one
    # (GND -> L1) put 41 legs on a single layer and unrouted exploded to 48.
    mids = [pref] + [l for l in sorted(layer_ok) if l != pref]
    for mid in mids:
        path = _plan_via_leg_on(board, a, b, sc, gc, net, layer_ok, pad_forbid, used,
                                mid, cost, allowed)
        if path is not None:
            return path
    return None


def _plan_via_leg_on(board, a, b, sc, gc, net, layer_ok, pad_forbid, used, mid, cost, allowed):
    la_set = _pad_layers(a, layer_ok)
    lb_set = _pad_layers(b, layer_ok)
    la = min(la_set) if la_set else mid
    lb = min(lb_set) if lb_set else mid
    width = route_width(net)
    forbidden = {c for c, o in pad_forbid.items() if o != net}

    if la == mid and lb == mid:
        return flat_route(board, sc, gc, mid, forbidden, cost, allowed)

    sites = []
    for cell, lay in ((sc, la), (gc, lb)):
        if lay == mid:
            sites.append(cell)
            continue
        s = free_via_site(board, cell, net, pad_forbid, used, width)
        if s is None:
            return None
        sites.append(s)
    site_a, site_b = sites

    parts = []
    if la != mid:
        p1 = flat_route(board, sc, site_a, la, forbidden, cost, allowed)
        if not p1:
            return None
        parts.append(p1)
    p2 = flat_route(board, site_a, site_b, mid, forbidden, cost, allowed)
    if not p2:
        return None
    parts.append(p2)
    if lb != mid:
        p3 = flat_route(board, site_b, gc, lb, forbidden, cost, allowed)
        if not p3:
            return None
        parts.append(p3)

    path = []
    for part in parts:
        if path and path[-1][:2] == part[0][:2]:
            path.extend(part[1:])
        else:
            path.extend(part)
    return path


def route(board, iters=10, layers=2, spacing_hard=False, hard_nets=None, segment_check=False, priority_nets=None, escape_nets=None, plane_nets=frozenset(), plane_layer=None, via_check=False, via_sites=False, via_cost=None, via_negotiate=False, via_plan=False, via_first=False, net_order="small", pour_nets=frozenset(), pour_layer=None, pour_step=5):
    pad_forbid, own = board.pad_blocked()
    layer_ok = set(range(1, layers + 1))
    if plane_layer:
        # A plane owns its whole layer: nobody else may run a track there.
        layer_ok.discard(int(plane_layer))
    # A POUR shares its layer with tracks: it only has to keep pour clearance
    # from them, so the layer stays available.  Taking a whole layer for GND was
    # measured worse than routing it (round 2), a pour is the realistic model.
    pour_sets = set(pour_nets)
    def net_priority(n):
        """Route buses FIRST so their length-matching channels exist before the
        general signals fill every free cell (measured: with the old order, zero
        meanders could be placed and the SD bus was 895 mil out of skew).

        Nets that failed on an earlier pass can be pushed to the very front: that is
        how the last unroutable legs get a corridor before everyone else takes it.
        """
        if priority_nets and n in priority_nets:
            return -1
        if n.startswith(BUS_PREFIX):
            return 0
        if n in POWER:
            return 1
        return 2

    skip_nets = set(plane_nets) | pour_sets
    nets = sorted([n for n in board.nets if len(board.nets[n]) >= 2 and n not in skip_nets],
                  key=lambda n: (net_priority(n),
                                 -len(board.nets[n]) if net_order == "big" else len(board.nets[n]),
                                 n))
    history = defaultdict(float)
    # Via sites are reserved, not vetoed.  The base map is the pads' keep-out
    # discs; it is rebuilt every pass and stamped with every accepted track, so
    # an early net's corridor also reserves the places a later net may not put a
    # via.  Refusing only the TRANSITION keeps long legs routable.
    via_base = build_pad_via_block(board) if via_sites else None
    # Via-first: every SMD pad gets its legal via site before a single track is
    # drawn, and other nets are kept off those discs.  This is the global plan
    # the per-leg version (--via-plan) failed to be.
    pad_sites, site_disc_owner, blocked_by_net = {}, {}, {}
    if via_first:
        pad_sites = plan_pad_via_sites(board, pad_forbid)
        for (des, pad), cell in pad_sites.items():
            owner = next((n for n, ps in board.nets.items()
                          for p in ps if p["des"] == des and p["pad"] == pad), None)
            for c in reserve_via_discs(board, {0: cell}):
                site_disc_owner.setdefault(c, owner)
        for net in board.nets:
            blocked_by_net[net] = {c for c, o in site_disc_owner.items() if o != net}
    best = None
    for it in range(iters):
        via_block = {k: set(v) for k, v in via_base.items()} if via_base else None
        used = defaultdict(set)
        halo = defaultdict(set)
        routed, failures = {}, []
        for net in nets:
            pads = board.nets[net]
            pref = preferred_layer(net, layers)
            if layers < 2:
                pref = 1
            forbidden = {c for c, o in pad_forbid.items() if o != net}
            if spacing_hard or (hard_nets and net in hard_nets):
                # Spacing as a HARD constraint: cells (and their 8-neighbour halo)
                # claimed by another net in this pass are off limits, not merely
                # expensive. Cost-only spacing left 227 clearance violations.
                for (cx, cy, _l), nset in halo.items():
                    if net not in nset:
                        forbidden.add((cx, cy))
            for i, j in mst_edges(pads):
                a, b = pads[i], pads[j]
                sc, gc = board.cell(a["x"], a["y"]), board.cell(b["x"], b["y"])
                cost = {}
                for cell, netset in used.items():
                    pen = 0.0 if net in netset else 10.0 + 10.0 * history[cell]
                    cost[(cell[0], cell[1], cell[2])] = pen
                for cell, netset in halo.items():
                    if net in netset:
                        continue
                    # Halo cost: a neighbouring net's track cell. Raised from 2 to
                    # 8 (+ history) because cost-only spacing at 2 left 227
                    # clearance violations; hard blocking instead killed 78 legs.
                    cost[(cell[0], cell[1], cell[2])] = cost.get((cell[0], cell[1], cell[2]), 0.0) + 8.0 + 4.0 * history.get((cell[0], cell[1]), 0.0)
                allowed = set()
                if escape_nets and net in escape_nets:
                    # Fan-out via band: a dense pad row (U5, 100 mil) leaves no room
                    # to leave on the top layer, so open a 3-cell band on each side of
                    # the pad's own keep-out. The router can then drop to an inner
                    # layer right at the module edge, which is what a real engineer
                    # does on a dense QFN/module row.
                    for pad in (a, b):
                        for ex, ey in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            for step in (1, 2, 3):
                                cx, cy = board.cell(pad["x"] + ex * step * GRID,
                                                    pad["y"] + ey * step * GRID)
                                if 0 <= cx < board.w and 0 <= cy < board.h:
                                    allowed.add((cx, cy))
                for pad in (a, b):
                    hw, hh = pad["w"] / 2 + CLEARANCE, pad["h"] / 2 + CLEARANCE
                    ax0, ay0 = board.cell(pad["x"] - hw, pad["y"] - hh)
                    ax1, ay1 = board.cell(pad["x"] + hw, pad["y"] + hh)
                    for gx in range(max(0, ax0), min(board.w, ax1 + 1)):
                        for gy in range(max(0, ay0), min(board.h, ay1 + 1)):
                            # Only cells that belong to THIS net's pad may be
                            # entered. Allowing the whole corridor let tracks run
                            # over a neighbour's pad, which showed up as clearance
                            # violations (122) while the router's own accounting
                            # saw nothing.
                            # Owners of a keep-out ring cell are the pad's net, so
                            # this also opens the pad's own clearance ring: that ring
                            # is where an ESCAPE VIA has to go when the pad sits in a
                            # 0.5 mm pitch row and the direct exit is crowded.
                            owners = board.pad_cells.get((gx, gy))
                            ring_owner = pad_forbid.get((gx, gy))
                            if (owners and net in owners) or ring_owner == net:
                                allowed.add((gx, gy))
                def _accept(cand):
                    if not cand:
                        return None
                    if segment_check and (
                            path_conflicts(board, cand, routed, net, route_width(net))
                            or (via_check and via_conflicts(board, cand, used, pad_forbid,
                                                            net, route_width(net)))):
                        # Spacing as a real geometric constraint: reject the too-close
                        # run and make its cells expensive so the next pass routes
                        # elsewhere.
                        for (x, y, _l) in cand:
                            history[(x, y)] += 2.0
                        return None
                    return cand

                path = None
                if via_first:
                    path = _accept(plan_via_first_leg(
                        board, a, b, net, pad_sites, layer_ok, pad_forbid, cost, allowed,
                        layers, mid_hint=pref, blocked=blocked_by_net.get(net, set())))
                if path is None and via_plan:
                    path = _accept(plan_via_leg(board, a, b, sc, gc, net, layer_ok,
                                                pad_forbid, used, history, layers,
                                                cost, allowed))
                if path is None:
                    # A planned-via leg that breaks spacing falls back to the free
                    # 3D search instead of dying: without this the planned legs
                    # were rejected outright and unrouted went 10 -> 48.
                    path = _accept(astar(board, sc, gc, forbidden | {c for c in own.get(net, set()) if c not in (sc, gc)} | blocked_by_net.get(net, set()),
                                         cost, pref, allowed, layers, layer_ok=layer_ok,
                                         via_block=via_block, net=net, via_cost=via_cost,
                                         start_layer=(min(_pad_layers(a, layer_ok)) if _pad_layers(a, layer_ok) else None),
                                         goal_layers=_pad_layers(b, layer_ok)))
                if not path:
                    failures.append({"net": net, "a": f"{a['des']}.{a['pad']}", "b": f"{b['des']}.{b['pad']}"})
                    continue
                routed.setdefault(net, []).append(path)
                if via_block is not None:
                    # Reserve the via discs this path has consumed so the next
                    # nets change layers somewhere else instead of on top of it.
                    stamp_via_block(via_block, path, net, route_width(net))
                for (x, y, ll) in path:
                    used[(x, y, ll)].add(net)
                    for dx, dy in HALO:
                        halo[(x + dx, y + dy, ll)].add(net)
        # ONE definition of congestion: recount it from the plan that would be
        # applied to the board. The router's own `used` bookkeeping is kept only
        # to steer A* (cost/history) — as a KPI it disagreed with the recount
        # (40 vs 281) and a KPI may not have two answers.
        contended = [c for c, ns in used.items() if len(ns) > 1]
        plan_pass = plan_from(board, routed) if routed else {"tracks": [], "vias": []}
        pass_congestion = congestion_from_plan(board, plan_pass) if routed else 0
        # Conflict-aware history: spacing conflicts feed the SAME negotiator that
        # handles congestion, instead of a single-shot rip-up reroute (which hit
        # clearance 0 but left 33 nets unrouted). The victim's cells get history so
        # the next pass spreads everything away from the hot spot.
        pairs = clearance_pairs(board, plan_pass) if routed else set()
        spacing_bumps = 0
        if pairs:
            lens = defaultdict(float)
            for t in plan_pass.get("tracks") or []:
                lens[t["net"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
            for a, b in pairs:
                victim = a if lens[a] <= lens[b] else b
                for path in routed.get(victim, []):
                    for (x, y, _l) in path:
                        history[(x, y)] += 1.0
                        spacing_bumps += 1
        score = (len(failures), pass_congestion + len(pairs))
        if via_negotiate:
            # Via spacing joins the SAME negotiator the router already uses for
            # congestion and track spacing: the cells that ended up with a bad via
            # become expensive, so the next pass changes layers somewhere else.
            # This is the only one of the four via strategies that does not cost
            # dead legs (reservation 7->15, path veto 7->33, dirty penalty 7->15).
            bad_via = via_violation_cells(board, plan_pass) if routed else set()
            for (bx, by) in bad_via:
                history[(bx, by)] += VIA_HISTORY_BUMP
                for layer in range(1, 5):
                    history[(bx, by, layer)] += VIA_HISTORY_BUMP
            score = (len(failures), pass_congestion + len(pairs) + len(bad_via) * VIA_SCORE_W)
        if best is None or score < best[0]:
            # keep the CONGESTION itself (not the composite score) so the reported
            # router_congestion is comparable with the plan recount
            best = (score, routed, failures, pass_congestion)
        if not failures and pass_congestion == 0 and not pairs:
            break
        for c in contended:
            history[c] += 1.0
    score, best_routed, best_failures, best_congestion = best
    groups = []
    if plane_nets and plane_layer:
        groups.append((set(plane_nets), int(plane_layer)))
    if pour_sets and pour_layer:
        groups.append((pour_sets, int(pour_layer)))
    for group_nets, group_layer in groups:
        vias, stubs = plane_access(board, best_routed, group_nets, group_layer,
                                     max_step=pour_step)
        # The pad->via stub is the ONLY copper a plane net may spend: the test
        # contract allows stubs up to 3*GRID and nothing longer. Dropping the stubs
        # entirely disconnects the pad from its via (measured: GND reported dead).
        for net, paths in stubs.items():
            best_routed.setdefault(net, []).extend(paths)
        if vias:
            best_routed[PLANE_VIA_KEY] = vias
    return (len(best_failures), best_congestion), best_routed, best_failures


def _seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    def pt(px, py, x1, y1, x2, y2):
        vx, vy = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
        return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))
    return min(pt(ax, ay, cx, cy, dx, dy), pt(bx, by, cx, cy, dx, dy),
               pt(cx, cy, ax, ay, bx, by), pt(dx, dy, ax, ay, bx, by))


def clearance_pairs(board, plan):
    segs = [(t["net"], t["width"], t["layer"], t["x1"], t["y1"], t["x2"], t["y2"])
            for t in plan.get("tracks") or []]
    pairs = set()
    for i in range(len(segs)):
        n1, w1, l1, ax, ay, bx, by = segs[i]
        for j in range(i + 1, len(segs)):
            n2, w2, l2, cx, cy, dx, dy = segs[j]
            if n1 == n2 or l1 != l2:
                continue
            if _seg_seg(ax, ay, bx, by, cx, cy, dx, dy) < (w1 + w2) / 2 + CLEARANCE - 0.5:
                pairs.add((n1, n2))
    return pairs


def reroute_net(board, net, extra_forbidden, layers, pad_forbid, own):
    """Route one net's MST edges with `extra_forbidden` (another net's cells) as
    hard obstacles. Used by the repair pass."""
    pads = board.nets[net]
    pref = preferred_layer(net, layers)
    forbidden = {c for c, o in pad_forbid.items() if o != net} | set(extra_forbidden)
    paths = []
    for i, j in mst_edges(pads):
        a, b = pads[i], pads[j]
        sc, gc = board.cell(a["x"], a["y"]), board.cell(b["x"], b["y"])
        allowed = set()
        for pad in (a, b):
            hw, hh = pad["w"] / 2 + CLEARANCE, pad["h"] / 2 + CLEARANCE
            ax0, ay0 = board.cell(pad["x"] - hw, pad["y"] - hh)
            ax1, ay1 = board.cell(pad["x"] + hw, pad["y"] + hh)
            for gx in range(max(0, ax0), min(board.w, ax1 + 1)):
                for gy in range(max(0, ay0), min(board.h, ay1 + 1)):
                    owners = board.pad_cells.get((gx, gy))
                    if owners and net in owners:
                        allowed.add((gx, gy))
        path = astar(board, sc, gc, forbidden | {c for c in own.get(net, set()) if c not in (sc, gc)},
                     {}, pref, allowed, layers)
        if not path:
            return None
        paths.append(path)
    return paths


def repair(board, routed, rounds=3, layers=4):
    """Soft-route, then fix clearance pair-by-pair: rip the shorter track of each
    conflicting pair and re-route it against its opponent's cells only."""
    pad_forbid, own = board.pad_blocked()
    for r in range(rounds):
        plan = plan_from(board, routed)
        pairs = clearance_pairs(board, plan)
        if not pairs:
            return routed, r, 0
        lens = defaultdict(float)
        for t in plan["tracks"]:
            lens[t["net"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        rip = set()
        opponents = defaultdict(set)
        for a, b in pairs:
            victim = a if lens[a] <= lens[b] else b
            other = b if victim == a else a
            rip.add(victim)
            opponents[victim].add(other)
        cells = {n: {(x + dx, y + dy) for p in ps for (x, y, _l) in p for dx, dy in HALO}
                 for n, ps in routed.items()}
        for net in rip:
            routed.pop(net, None)
        for net in sorted(rip):
            # Block ONLY the nets this one actually conflicts with; blocking every
            # other net's halo made 33 nets unroutable.
            blocked = set()
            for opp in opponents.get(net, ()):
                blocked |= cells.get(opp, set())
            paths = reroute_net(board, net, blocked, layers, pad_forbid, own)
            if paths:
                routed[net] = paths
    plan = plan_from(board, routed)
    return routed, rounds, len(clearance_pairs(board, plan))


def merge(path):
    """Collapse contiguous runs sharing a direction: horizontal, vertical AND
    diagonal. Only axis-aligned runs used to merge, so enabling 45-degree moves
    blew the segment count from 211 to 2174."""
    out = []
    for a, b in zip(path, path[1:]):
        if a[2] != b[2]:
            out.append(("via", a, None, None))
            continue
        d = (b[0] - a[0], b[1] - a[1])
        if out and out[-1][0] == "seg":
            pb, pd = out[-1][2], out[-1][3]
            if pd == d and pb[:2] == a[:2] and pb[2] == a[2]:
                out[-1] = ("seg", out[-1][1], b, d)
                continue
        out.append(("seg", a, b, d))
    return out


# ── metrics / verification ───────────────────────────────────────────────────
def seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    def pt(px, py, x1, y1, x2, y2):
        vx, vy = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
        return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))
    return min(pt(ax, ay, cx, cy, dx, dy), pt(bx, by, cx, cy, dx, dy),
               pt(cx, cy, ax, ay, bx, by), pt(dx, dy, ax, ay, bx, by))


def _stub_clear(board, pc, vc, busy, pad_forbid, net, margin=CLEARANCE):
    """Is the short pad -> site stub free of other nets' copper?

    With ring search a site can be off the eight compass directions, so the stub
    is a real diagonal run and every cell on it has to be checked.  `margin`
    decides how strict: at full clearance the keep-out RING is off limits, on the
    fallback tier only the solid pad is (a stub across a ring is a spacing
    violation, a stub across a pad is a short).
    """
    strict = margin > VIA_BLOCK_MARGIN
    for (cx, cy) in _bresenham(pc[0], pc[1], vc[0], vc[1]):
        if (cx, cy) in busy:
            return False
        if strict:
            owner = pad_forbid.get((cx, cy))
            if owner is not None and owner != net:
                return False
        else:
            owners = board.pad_cells.get((cx, cy))
            if owners and any(o != net for o in owners):
                return False
    return True


def _disc_clear(board, cell, net, pad_forbid, busy, width, radius=VIA_RADIUS, margin=CLEARANCE):
    """Would a via at `cell` keep clearance from other pads and tracks?

    `margin` is the spacing required on top of the via and trace radii.  Pass a
    small margin for the "accept rather than disconnect" fallback: a pad with no
    legal disc at all still has to reach the pour somehow.
    """
    need = radius + width / 2 + margin
    reach = int(math.ceil(need / GRID))
    for ex in range(-reach, reach + 1):
        for ey in range(-reach, reach + 1):
            if math.hypot(ex, ey) * GRID > need:
                continue
            c = (cell[0] + ex, cell[1] + ey)
            owner = pad_forbid.get(c)
            if owner is not None and owner != net:
                return False
            if c in busy:
                return False
    return True


def plane_access(board, routed, plane_nets, plane_layer, max_step=3):
    """Give every pad of a plane net a via beside it, plus a one-cell stub.

    A plane is how a four-layer board really connects GND: the pads drop to the
    inner layer through vias and the plane does the rest.  Modelling it as 41
    more MST legs instead — the previous behaviour — spent 22% of the routing
    budget on the one net that never needs a track.

    Vias go BESIDE the pad, not in it: via-in-pad needs resin filling (POFV), a
    different process that must not be assumed silently.  The stub keeps
    pad -> via -> plane a real copper path, so connectivity still has to find it
    and a missing via still shows up as unconnected.
    """
    pad_forbid, _own = board.pad_blocked()
    busy = set()
    for net, paths in routed.items():
        if net in plane_nets or net == PLANE_VIA_KEY:
            continue
        for path in paths:
            for (x, y, _l) in path:
                busy.add((x, y))

    vias, stubs = [], defaultdict(list)
    for net in sorted(plane_nets):
        for pad in board.nets.get(net, []):
            pc = board.cell(pad["x"], pad["y"])
            comp = board.comps.get(pad["des"]) or {"x": pad["x"], "y": pad["y"]}
            out = _unit(pad["x"] - comp["x"], pad["y"] - comp["y"])
            # Two tiers: a site whose disc keeps full clearance, else (rather than
            # leaving the pad disconnected) one that at least does not overlap.
            # Strict-only left 18 GND pads without an access via, i.e. a broken
            # net, which is worse than a spacing violation.
            #
            # The search walks WHOLE rings, not eight directions: a legal cell at,
            # say, (2, 1) is invisible to an 8-direction sweep, which is why
            # widening max_step alone only moved via-in-pad from 5 to 4.
            target = None
            for margin in (CLEARANCE, VIA_BLOCK_MARGIN):
                for r in range(1, max_step + 1):
                    cands = [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                             if max(abs(dx), abs(dy)) == r]
                    cands.sort(key=lambda d: -((d[0] * out[0] + d[1] * out[1]) /
                                               (math.hypot(d[0], d[1]) or 1.0)))
                    for dx, dy in cands:
                        vc = (pc[0] + dx, pc[1] + dy)
                        if not (0 <= vc[0] < board.w and 0 <= vc[1] < board.h):
                            continue
                        if vc in busy:
                            continue
                        # The whole DISC must clear other pads and tracks, not just
                        # the centre cell: checking only the centre put GND access
                        # vias on neighbours' keep-out rings (GND was the top
                        # offender at 62 of 426 violation involvements).
                        if not _disc_clear(board, vc, net, pad_forbid, busy,
                                           route_width(net), margin=margin):
                            continue
                        if not _stub_clear(board, pc, vc, busy, pad_forbid, net, margin):
                            continue
                        target = vc
                        break
                    if target:
                        break
                if target:
                    break
            if target is None:
                target = pc          # via-in-pad fallback, flagged below
            in_pad = target == pc
            x, y = board.center(*target)
            via = {"net": net, "x": x, "y": y, "plane_layer": int(plane_layer)}
            if in_pad:
                # Last resort: no legal site anywhere near the pad.  Via-in-pad
                # keeps the net connected but needs resin filling (POFV), so the
                # via says so out loud and the count is a KPI.
                via["in_pad"] = True
            vias.append(via)
            busy.add(target)
            if not in_pad:
                stubs[net].append([(pc[0], pc[1], 1), (target[0], target[1], 1)])
    return vias, stubs


def plan_from(board, routed):
    plan = {"grid": GRID, "tracks": [], "vias": []}
    for net, paths in routed.items():
        if net == PLANE_VIA_KEY:
            # Plane access vias travel with the routing but are not a net.
            plan["vias"].extend(paths)
            continue
        w = route_width(net)
        for path in paths:
            for item in merge(path):
                if item[0] == "via":
                    x, y = board.center(*item[1][:2])
                    plan["vias"].append({"net": net, "x": x, "y": y})
                else:
                    a, b = item[1], item[2]
                    ax, ay = board.center(*a[:2])
                    bx, by = board.center(*b[:2])
                    plan["tracks"].append({"net": net, "layer": a[2], "width": w,
                                           "x1": ax, "y1": ay, "x2": bx, "y2": by})
    return plan


def connectivity(board, routed):
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for net, paths in routed.items():
        for path in paths:
            for cell in path:
                union((net, path[0][:2]), (net, cell[:2]))
    bad = []
    for net, pads in board.nets.items():
        if len(pads) < 2:
            continue
        roots = {find((net, board.cell(p["x"], p["y"]))) for p in pads}
        if len(roots) > 1:
            bad.append(net)
    return bad


def via_violation_cells(board, plan, radius=VIA_RADIUS):
    """Cells of vias that are too close to another net's copper.

    Returned as cells (not a count) because the negotiator needs to know WHERE
    to raise the cost; a count alone was how this stayed invisible.
    """
    cells = set()
    for v in plan.get("vias") or []:
        vx, vy, vn = v["x"], v["y"], v["net"]
        need_t = radius + CLEARANCE
        for t in plan.get("tracks") or []:
            if t["net"] != vn and seg_seg(vx, vy, vx, vy, t["x1"], t["y1"],
                                          t["x2"], t["y2"]) < need_t + t["width"] / 2 - 0.5:
                cells.add((vx, vy))
                break
        else:
            for pads in board.nets.values():
                if any(p["net"] != vn and math.hypot(p["x"] - vx, p["y"] - vy) <
                       radius + max(p["w"], p["h"]) / 2 + CLEARANCE - 0.5 for p in pads):
                    cells.add((vx, vy))
                    break
    return cells


def pad_layer_gaps(board, plan, tol=GRID * 1.5):
    """Pads whose nearest copper is on another layer with no via nearby.

    This is an open circuit that `connectivity_from_plan` CANNOT see: that check
    matches pads to nodes in 2D.  Measured on the pre-fix plan: 72 of 188 pads
    had copper on the wrong layer and no via within 15 mil — the plan was
    "connected" on paper only.  Through-hole pads (layer 12 in the dump) are
    legitimately reachable from any layer and are skipped.
    """
    gaps = 0
    for net, pads in board.nets.items():
        ends = []
        for t in plan.get("tracks") or []:
            if t["net"] == net:
                ends.append((t["x1"], t["y1"], t["layer"]))
                ends.append((t["x2"], t["y2"], t["layer"]))
        if not ends:
            continue
        vias = [(v["x"], v["y"]) for v in plan.get("vias") or [] if v["net"] == net]
        for p in pads:
            lay = int(p.get("layer") or 1)
            if lay not in (1, 2, 3, 4):
                continue
            near = min(ends, key=lambda e: math.hypot(e[0] - p["x"], e[1] - p["y"]))
            if math.hypot(near[0] - p["x"], near[1] - p["y"]) > tol:
                continue                      # pad simply unrouted; counted elsewhere
            if near[2] == lay:
                continue
            if any(math.hypot(v[0] - p["x"], v[1] - p["y"]) <= tol for v in vias):
                continue
            gaps += 1
    return gaps


def pour_islands(board, plan, clearance=POUR_CLEARANCE):
    """Is the pour still ONE piece of copper after the tracks punched through it?

    A pour shares its layer with every other net, so the tracks (plus pour
    clearance) cut it into islands.  If two GND access vias land in different
    islands, the net is broken — and the flat 2D connectivity check would never
    see it, because it only knows "these vias are all pour vias".
    """
    pour_vias = [v for v in plan.get("vias") or [] if v.get("plane_layer")]
    if not pour_vias:
        return 0
    layer = int(pour_vias[0]["plane_layer"])
    pour_nets = {v["net"] for v in pour_vias}
    target = {board.cell(v["x"], v["y"]) for v in pour_vias}
    halo = int(math.ceil(clearance / GRID))
    blocked = set()
    for t in plan.get("tracks") or []:
        if int(t["layer"]) != layer or t["net"] in pour_nets:
            continue
        blocked |= _segment_cells(board, t, halo=halo)

    seen, regions = set(), 0
    for start in sorted(target):
        if start in seen or start in blocked:
            continue
        regions += 1
        stack = [start]
        seen.add(start)
        while stack:
            x, y = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < board.w and 0 <= ny < board.h):
                    continue
                if (nx, ny) in seen or (nx, ny) in blocked:
                    continue
                seen.add((nx, ny))
                stack.append((nx, ny))
    return max(0, regions - 1)


def clearance_violations(board, plan):
    segs = [(t["net"], t["width"], t["layer"], t["x1"], t["y1"], t["x2"], t["y2"]) for t in plan["tracks"]]
    bad = 0
    for i in range(len(segs)):
        n1, w1, l1, ax, ay, bx, by = segs[i]
        for j in range(i + 1, len(segs)):
            n2, w2, l2, cx, cy, dx, dy = segs[j]
            if n1 == n2 or l1 != l2:
                continue
            if seg_seg(ax, ay, bx, by, cx, cy, dx, dy) < (w1 + w2) / 2 + CLEARANCE - 0.5:
                bad += 1
    # Vias are through-holes: their annular ring is copper on EVERY layer, so a
    # via must clear other nets' tracks on all four layers and their pads too.
    # Without this the plane model could add 40 vias for free.
    for v in plan.get("vias") or []:
        vx, vy, vn = v["x"], v["y"], v["net"]
        for t in plan.get("tracks") or []:
            if t["net"] == vn:
                continue
            if seg_seg(vx, vy, vx, vy, t["x1"], t["y1"], t["x2"], t["y2"]) < \
                    VIA_RADIUS + t["width"] / 2 + CLEARANCE - 0.5:
                bad += 1
        for pads in board.nets.values():
            for p in pads:
                if p["net"] == vn:
                    continue
                if math.hypot(p["x"] - vx, p["y"] - vy) < \
                        VIA_RADIUS + max(p["w"], p["h"]) / 2 + CLEARANCE - 0.5:
                    bad += 1
    return bad


def connectivity_from_plan(board, plan, tol=GRID * 1.5):
    """Independent connectivity check rebuilt from the PLAN (pads -> track
    endpoints -> vias). Without this the gate could not judge "unrouted" on its
    own: it used to report every net unconnected because it had no router state."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def q(x, y, layer):
        return (round(x / 2.0), round(y / 2.0), int(layer))

    for t in plan.get("tracks") or []:
        union((t["net"],) + q(t["x1"], t["y1"], t["layer"]),
              (t["net"],) + q(t["x2"], t["y2"], t["layer"]))
    for v in plan.get("vias") or []:
        base = (v["net"],) + q(v["x"], v["y"], 1)
        for layer in (2, 3, 4):
            union(base, (v["net"],) + q(v["x"], v["y"], layer))

    # Plane nets: every pad is joined through the plane, so all of that net's plane
    # access vias form a single node. Without this the pads look disconnected once
    # the tracks are (correctly) not emitted.
    plane_nodes = defaultdict(list)
    for v in plan.get("vias") or []:
        if v.get("plane_layer"):
            plane_nodes[v["net"]].append((v["net"],) + q(v["x"], v["y"], 1))
    for net, nodes in plane_nodes.items():
        for n in nodes[1:]:
            union(nodes[0], n)

    # All plane access vias land on the SAME copper: one connection through the
    # plane, not 42 separate islands.  A pad whose via is missing keeps its own
    # ("unrouted", ...) root, so a failed access via still fails the gate.
    plane_members = defaultdict(set)
    for v in plan.get("vias") or []:
        pl = v.get("plane_layer")
        if pl:
            plane_members[int(pl)].add((v["net"],) + q(v["x"], v["y"], 1))
    for members in plane_members.values():
        members = sorted(members)
        for m in members[1:]:
            union(members[0], m)

    nodes = defaultdict(list)
    for t in plan.get("tracks") or []:
        nodes[t["net"]].append((t["x1"], t["y1"], t["layer"]))
        nodes[t["net"]].append((t["x2"], t["y2"], t["layer"]))
    for v in plan.get("vias") or []:
        nodes[v["net"]].append((v["x"], v["y"], 1))

    unconnected = []
    for net, pads in board.nets.items():
        if len(pads) < 2:
            continue
        roots = set()
        for p in pads:
            best, bd = None, 1e18
            for (nx, ny, nl) in nodes.get(net, []):
                d = math.hypot(p["x"] - nx, p["y"] - ny)
                if d < bd:
                    bd, best = d, (nx, ny, nl)
            if best is None or bd > tol:
                roots.add(("unrouted", net, p["des"], p["pad"]))
            else:
                roots.add(find((net,) + q(*best)))
        if len(roots) > 1:
            unconnected.append(net)
    return unconnected


def _bresenham(x0, y0, x1, y1):
    """Cells a segment actually crosses (integer grid walk). Float sampling at a
    fixed step made long segments jitter into neighbouring cells, which is why
    the plan recount read 350 while the router's own accounting read 40."""
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return pts


def congestion_from_plan(board, plan):
    """Congestion recounted from the PLAN with the same integer cell walk the
    router uses, so the two independent counters must agree."""
    owner, dup = {}, set()
    for t in plan.get("tracks") or []:
        c0 = board.cell(t["x1"], t["y1"])
        c1 = board.cell(t["x2"], t["y2"])
        layer = int(t["layer"])
        for (cx, cy) in _bresenham(c0[0], c0[1], c1[0], c1[1]):
            cell = (cx, cy, layer)
            prev = owner.get(cell)
            if prev and prev != t["net"]:
                dup.add(cell)
            owner[cell] = t["net"]
    for v in plan.get("vias") or []:
        cx, cy = board.cell(v["x"], v["y"])
        cell = (cx, cy, 0)  # layer 0 = via, spans all layers
        prev = owner.get(cell)
        if prev and prev != v["net"]:
            dup.add(cell)
        owner[cell] = v["net"]
    return len(dup)


def _segment_cells(board, t, halo=0):
    c0 = board.cell(t["x1"], t["y1"])
    c1 = board.cell(t["x2"], t["y2"])
    cells = set()
    for (cx, cy) in _bresenham(c0[0], c0[1], c1[0], c1[1]):
        for dx in range(-halo, halo + 1):
            for dy in range(-halo, halo + 1):
                cells.add((cx + dx, cy + dy))
    return cells


def match_lengths(board, plan, groups=("CAM_D", "LCD_", "SD_"), tol=50.0, amp=GRID * 3):
    """Meander compensation for bus groups: bring every net in a group up to the
    group's longest length. An ace engineer will not ship a bus with 895 mil of
    skew, and DRC cannot see skew at all.

    A meander is only inserted when its cells are free of other nets' copper, so
    length matching cannot silently create clearance violations.
    """
    net_len = defaultdict(float)
    for t in plan["tracks"]:
        net_len[t["net"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
    occupancy = {}
    for t in plan["tracks"]:
        for cell in _segment_cells(board, t, halo=1):
            occupancy[cell] = t["net"]

    added = 0
    for prefix in groups:
        nets = [n for n in net_len if n.startswith(prefix)]
        if len(nets) < 2:
            continue
        target = max(net_len[n] for n in nets)
        for net in sorted(nets):
            delta = target - net_len[net]
            if delta <= tol:
                continue
            # longest straight segment of this net is the meander host
            best = None
            for idx, t in enumerate(plan["tracks"]):
                if t["net"] != net:
                    continue
                length = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                horizontal = abs(t["y2"] - t["y1"]) < 1e-9
                if (horizontal or abs(t["x2"] - t["x1"]) < 1e-9) and length > 3 * amp:
                    if best is None or length > best[0]:
                        best = (length, idx, horizontal)
            if best is None:
                continue
            _, idx, horizontal = best
            t = plan["tracks"][idx]
            # triangular bumps: each bump of pitch p and amplitude a adds
            # 2*sqrt((p/2)^2+a^2) - p extra length
            p = 4 * amp
            extra_per_bump = 2 * math.hypot(p / 2, amp) - p
            bumps = max(1, int(math.ceil(delta / extra_per_bump)))
            span = bumps * p
            if horizontal:
                if abs(t["x2"] - t["x1"]) < span + amp:
                    continue
            else:
                if abs(t["y2"] - t["y1"]) < span + amp:
                    continue
            # free-space gate for the meander envelope
            ok = True
            for k in range(bumps + 1):
                if horizontal:
                    x = t["x1"] + (t["x2"] - t["x1"]) * k / bumps
                    y0 = t["y1"] + (0 if k % 2 == 0 else amp)
                else:
                    x = t["x1"] + (0 if k % 2 == 0 else amp)
                    y0 = t["y1"] + (t["y2"] - t["y1"]) * k / bumps
                cell = board.cell(x, y0)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        owner = occupancy.get((cell[0] + dx, cell[1] + dy))
                        if owner and owner != net:
                            ok = False
            if not ok:
                continue
            # rebuild the segment as a meander
            new = []
            x0, y0 = t["x1"], t["y1"]
            for k in range(1, bumps + 1):
                if horizontal:
                    xa = t["x1"] + (t["x2"] - t["x1"]) * (k - 0.5) / bumps
                    xb = t["x1"] + (t["x2"] - t["x1"]) * k / bumps
                    ya = t["y1"] + amp
                    new.append({"net": net, "layer": t["layer"], "width": t["width"],
                                "x1": x0, "y1": y0, "x2": xa, "y2": ya})
                    new.append({"net": net, "layer": t["layer"], "width": t["width"],
                                "x1": xa, "y1": ya, "x2": xb, "y2": t["y1"]})
                    x0, y0 = xb, t["y1"]
                else:
                    ya = t["y1"] + (t["y2"] - t["y1"]) * (k - 0.5) / bumps
                    yb = t["y1"] + (t["y2"] - t["y1"]) * k / bumps
                    xa = t["x1"] + amp
                    new.append({"net": net, "layer": t["layer"], "width": t["width"],
                                "x1": x0, "y1": y0, "x2": xa, "y2": ya})
                    new.append({"net": net, "layer": t["layer"], "width": t["width"],
                                "x1": xa, "y1": ya, "x2": t["x1"], "y2": yb})
                    x0, y0 = t["x1"], yb
            plan["tracks"][idx:idx + 1] = new
            net_len[net] += bumps * extra_per_bump
            for seg in new:
                for cell in _segment_cells(board, seg, halo=1):
                    occupancy[cell] = net
            added += 1
    return added


def bundle_route(board, plan, prefix, pitch=12.0, layer=3):
    """Route a bus group as a BUNDLE: members share one Manhattan corridor, offset
    perpendicular by `pitch`, so their lengths are equal by construction.

    This replaces "route every net alone, then try to compensate" — measured twice
    that approach could not place a single meander because the board was full.
    Returns (routed_members, blocked_members, length_spread).
    """
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    if len(nets) < 2:
        return 0, 0, None
    # order members by their source pad's position so the bundle never crosses
    pairs = []
    for net in nets:
        pads = board.nets[net]
        if len(pads) < 2:
            continue
        a, b = pads[0], pads[1]
        pairs.append((net, a, b))
    if len(pairs) < 2:
        return 0, 0, None
    pairs.sort(key=lambda t: (t[1]["y"], t[1]["x"]))
    # common corridor: horizontal at y = mean source y, then vertical at the mean
    # destination x
    y_common = round(sum(p[1]["y"] for p in pairs) / len(pairs) / GRID) * GRID
    x_dest = round(sum(p[2]["x"] for p in pairs) / len(pairs) / GRID) * GRID

    # occupancy of everything already routed (other nets only)
    occ = {}
    for t in plan["tracks"]:
        for cell in _segment_cells(board, t, halo=1):
            occ[cell] = t["net"]

    placed, blocked = 0, 0
    for i, (net, a, b) in enumerate(pairs):
        off = (i - (len(pairs) - 1) / 2.0) * pitch
        pts = [(a["x"], a["y"]), (a["x"], y_common + off),
               (x_dest + off, y_common + off), (x_dest + off, b["y"]), (b["x"], b["y"])]
        segs = []
        clash = False
        for p0, p1 in zip(pts, pts[1:]):
            seg = {"net": net, "layer": layer, "width": BUS_TRACE,
                   "x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1]}
            for cell in _segment_cells(board, seg, halo=0):
                owner = occ.get((cell[0], cell[1], layer))
                if owner and owner != net:
                    clash = True
                    break
            if clash:
                break
            segs.append(seg)
        if clash:
            blocked += 1
            continue
        plan["tracks"].extend(segs)
        for seg in segs:
            for cell in _segment_cells(board, seg, halo=0):
                occ[(cell[0], cell[1], layer)] = net
        placed += 1
    lens = []
    for net, _a, _b in pairs:
        ln = sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                 for t in plan["tracks"] if t["net"] == net)
        lens.append(ln)
    spread = round(max(lens) - min(lens), 1) if lens else None
    return placed, blocked, spread


def bundle_spine(board, routed, plan, y_src, x_dst, layer):
    """A*-searched corridor for a bus bundle (4-direction, so the perpendicular
    offsets stay axis-aligned). The old fixed-corridor version placed 1 of 8
    members because the straight line ran through other pads."""
    forbidden = set()
    for cell, net in board.pad_cells.items():
        forbidden.add(cell)
    for t in plan.get("tracks") or []:
        for cell in _segment_cells(board, t, halo=1):
            forbidden.add(cell)
    start = board.cell(y_src[0], y_src[1])
    goal = board.cell(x_dst[0], x_dst[1])
    # A* on the reserved layer; allow the pad cells of the bundle itself
    return astar(board, start, goal, forbidden, {}, layer, set(), 4)


def bundle_route_along_spine(board, plan, prefix, spine, pitch=12.0, layer=3):
    """Emit one track per group member, offset perpendicular to the searched spine.
    Members then have identical length by construction."""
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    pairs = []
    for net in nets:
        pads = board.nets[net]
        if len(pads) >= 2:
            pairs.append((net, pads[0], pads[1]))
    if len(pairs) < 2 or not spine:
        return 0, len(pairs), None
    pairs.sort(key=lambda t: (t[1]["y"], t[1]["x"]))
    occ = {}
    for t in plan.get("tracks") or []:
        for cell in _segment_cells(board, t, halo=1):
            occ[cell] = t["net"]
    placed = blocked = 0
    for i, (net, a, b) in enumerate(pairs):
        off = (i - (len(pairs) - 1) / 2.0) * pitch
        cells = []
        for (cx, cy, _l) in spine:
            ocx, ocy = cx, cy
            cells.append((ocx, ocy))
        # perpendicular offset: remember the direction of each step
        shifted = []
        for k, (cx, cy) in enumerate(cells):
            if k + 1 < len(cells):
                dx = cells[k + 1][0] - cx
                dy = cells[k + 1][1] - cy
            else:
                dx, dy = cells[k][0] - cells[k - 1][0], cells[k][1] - cells[k - 1][1]
            if dx:
                shifted.append((cx, cy + round(off / GRID)))
            else:
                shifted.append((cx + round(off / GRID), cy))
        clash = any((occ.get(c)) and occ.get(c) != net for c in shifted)
        if clash:
            blocked += 1
            continue
        pts = [board.center(c[0], c[1]) for c in shifted]
        segs = []
        for p0, p1 in zip(pts, pts[1:]):
            seg = {"net": net, "layer": layer, "width": BUS_TRACE,
                   "x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1]}
            segs.append(seg)
        plan["tracks"].extend(segs)
        for seg in segs:
            for cell in _segment_cells(board, seg, halo=0):
                occ[(cell[0], cell[1], layer)] = net
        placed += 1
    lens = [sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                for t in plan["tracks"] if t["net"] == net) for net, _a, _b in pairs]
    return placed, blocked, round(max(lens) - min(lens), 1) if lens else None


def pad_escape_dirs(board):
    """Which way may each pad leave its footprint?

    For an FPC/header column the pads are 50 mil apart vertically, so the escape
    must be sideways; the earlier version scored "nearest neighbour distance"
    without a narrow corridor and happily returned vertical for those pads, which
    is why bundle fan-out placed 1 of 8.

    Rule: score each of the four directions by the distance to the nearest
    same-footprint pad inside a NARROW corridor (perpendicular deviation <= half a
    pad), and break ties by pointing away from the footprint centroid.
    """
    dirs = {}
    for des, c in board.comps.items():
        pads = c["pads"]
        if not pads:
            continue
        cx = sum(p["x"] for p in pads) / len(pads)
        cy = sum(p["y"] for p in pads) / len(pads)
        for p in pads:
            scores = {}
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                near = 1e9
                for q in pads:
                    if q is p:
                        continue
                    vx, vy = q["x"] - p["x"], q["y"] - p["y"]
                    proj = vx * dx + vy * dy
                    if proj <= 0:
                        continue
                    perp = abs(vx * dy - vy * dx)
                    if perp <= (p["w"] + p["h"]) / 2:
                        near = min(near, proj)
                outward = (p["x"] - cx) * dx + (p["y"] - cy) * dy
                scores[(dx, dy)] = (near, outward)
            best = max(scores, key=lambda d: (scores[d][0], scores[d][1]))
            dirs[(des, p["pad"])] = best
    return dirs


def bundle_route_trunk(board, plan, prefix, pitch_h=20.0, pitch_t=25.0, layer=3):
    """Row→column bundle through a VERTICAL trunk in the free area between the two
    pad fields, instead of a horizontal lane band squeezed into the 97 mil gap.

    Capacity: the horizontal band could not host 8 lanes plus jog headroom
    (80 + 75 > 97 mil), while the empty column band (x 1100..2100) has ~1000 mil of
    room for trunks. Geometry per member:

        pad -> 45° rise to its horizontal lane -> trunk x -> drop to dest y -> pad

    Trunk x order follows destination order so drops never cross; horizontal lanes
    follow source order so rises nest.
    """
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in nets if len(board.nets[n]) >= 2]
    if len(pairs) < 2:
        return 0, 0, None
    pairs.sort(key=lambda t: t[1]["x"])
    by_dst = sorted(pairs, key=lambda t: t[2]["y"])
    x_base = min(p[2]["x"] for p in pairs) - 80.0
    trunk_x = {p[0]: x_base - j * pitch_t for j, p in enumerate(by_dst)}
    src_y = min(p[1]["y"] for p in pairs)
    occ = {}
    for t in plan.get("tracks") or []:
        for (cx, cy) in _segment_cells(board, t, halo=1):
            occ[(cx, cy, t["layer"])] = t["net"]
    placed = blocked = 0
    for i, (net, a, b) in enumerate(pairs):
        lane_y = src_y + (i + 1) * pitch_h
        d = lane_y - a["y"]
        pts = [(a["x"], a["y"]), (a["x"] + d, lane_y),
               (trunk_x[net], lane_y), (trunk_x[net], b["y"]), (b["x"], b["y"])]
        segs, clash = [], False
        for p0, pn in zip(pts, pts[1:]):
            if abs(p0[0] - pn[0]) < 1e-9 and abs(p0[1] - pn[1]) < 1e-9:
                continue
            seg = {"net": net, "layer": layer, "width": BUS_TRACE,
                   "x1": p0[0], "y1": p0[1], "x2": pn[0], "y2": pn[1]}
            for (cx, cy) in _segment_cells(board, seg, halo=0):
                owner = occ.get((cx, cy, layer))
                if owner and owner != net:
                    clash = True
                    break
            if clash:
                break
            segs.append(seg)
        if clash:
            blocked += 1
            continue
        plan["tracks"].extend(segs)
        for seg in segs:
            for (cx, cy) in _segment_cells(board, seg, halo=1):
                occ[(cx, cy, layer)] = net
        placed += 1
    lens = [sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                for t in plan["tracks"] if t["net"] == net) for net, _a, _b in pairs]
    return placed, blocked, round(max(lens) - min(lens), 1) if lens else None


def bundle_route_split(board, plan, prefix, pitch=15.0, per_layer=4, layers=(3, 4)):
    """Split a bus group across two layers and run each half in the free gap between
    the source row and the destination column.

    Capacity proof that forced this shape: CAM_D needs 7 gaps x 15 mil = 105 mil but
    the source row and destination column are only 97 mil apart, so a single-layer
    single-channel bundle cannot exist. Four members per layer need 45 mil and fit.
    """
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in nets if len(board.nets[n]) >= 2]
    if len(pairs) < 2:
        return 0, 0, None
    pairs.sort(key=lambda t: t[2]["y"])
    occ = {}
    for t in plan.get("tracks") or []:
        for cell in _segment_cells(board, t, halo=1):
            occ[cell] = t["net"]
    placed = blocked = 0
    for half in range(0, len(pairs), per_layer):
        chunk = pairs[half:half + per_layer]
        layer = layers[min(len(layers) - 1, half // per_layer)]
        # Lane order must follow the SOURCE x inside the chunk: ordering by
        # destination y (the chunking order) leaves source x arbitrary, and then the
        # 45° rises cross each other's horizontal runs (measured: 1–2 of 8 placed).
        chunk = sorted(chunk, key=lambda t: t[1]["x"])
        base = min(p[1]["y"] for p in chunk)
        for k, (net, a, b) in enumerate(chunk):
            lane_y = base + (k + 1) * pitch
            p1 = (a["x"] + (lane_y - a["y"]), lane_y)
            p2 = (b["x"] + (lane_y - b["y"]), lane_y)
            pts = [(a["x"], a["y"]), p1, p2, (b["x"], b["y"])]
            segs, clash = [], False
            for p0, pn in zip(pts, pts[1:]):
                if abs(p0[0] - pn[0]) < 1e-9 and abs(p0[1] - pn[1]) < 1e-9:
                    continue
                seg = {"net": net, "layer": layer, "width": BUS_TRACE,
                       "x1": p0[0], "y1": p0[1], "x2": pn[0], "y2": pn[1]}
                for (cx, cy) in _segment_cells(board, seg, halo=0):
                    owner = occ.get((cx, cy, layer))   # occupancy is PER LAYER
                    if owner and owner != net:
                        clash = True
                        break
                if clash:
                    break
                segs.append(seg)
            if clash:
                blocked += 1
                continue
            plan["tracks"].extend(segs)
            for seg in segs:
                for (cx, cy) in _segment_cells(board, seg, halo=1):
                    occ[(cx, cy, layer)] = net
            placed += 1
    lens = [sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                for t in plan["tracks"] if t["net"] == net) for net, _a, _b in pairs]
    return placed, blocked, round(max(lens) - min(lens), 1) if lens else None


def bundle_route_channel(board, plan, prefix, lane=35.0, layer=3):
    """Row→column bundle with a channel band that is CLEAR of both pad regions and
    nested 45-degree staircases on both sides.

    Evidence that forced this shape: every earlier version clashed because the lane
    band overlapped a pad region, so a drop vertical had to cross other members'
    horizontal runs (cell-level clash logs in BUNDLE-DESIGN.md).
    """
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in nets if len(board.nets[n]) >= 2]
    if len(pairs) < 2:
        return 0, 0, None
    pairs.sort(key=lambda t: t[1]["x"])
    n = len(pairs)
    src_y = pairs[0][1]["y"]
    dst_ys = [p[2]["y"] for p in pairs]
    dst_x = min(p[2]["x"] for p in pairs)
    # Lane order follows the DESTINATION order and the lane pitch equals the
    # destination pad pitch: then every member's final drop is identical, which is
    # what makes the bundle length-equal by construction (attempt 6 failed because
    # the drop varied with each destination y).
    pairs_by_dst = sorted(pairs, key=lambda t: t[2]["y"])
    ordered_ys = [p[2]["y"] for p in pairs_by_dst]
    dst_pitch = lane
    if len(ordered_ys) >= 2:
        diffs = [abs(ordered_ys[i + 1] - ordered_ys[i]) for i in range(len(ordered_ys) - 1)]
        if diffs and min(d for d in diffs if d > 0) > 0 if any(d > 0 for d in diffs) else False:
            dst_pitch = min(d for d in diffs if d > 0)
    band = max(max(dst_ys), src_y) + 3 * dst_pitch
    lane_of = {p[0]: band + k * dst_pitch for k, p in enumerate(pairs_by_dst)}
    occ = {}
    for t in plan.get("tracks") or []:
        for cell in _segment_cells(board, t, halo=1):
            occ[cell] = t["net"]
    placed = blocked = 0
    for net, a, b in pairs:
        lane_y = lane_of[net]                      # lane order = destination order
        d_src = lane_y - a["y"]
        d_dst = lane_y - b["y"]
        p1 = (a["x"] + d_src, lane_y)              # 45-degree rise from the pad
        p2 = (b["x"] + d_dst, lane_y)              # 45-degree drop onto the pad column
        pts = [(a["x"], a["y"]), p1, p2, (b["x"], b["y"])]
        segs, clash = [], False
        for p0, pn in zip(pts, pts[1:]):
            if abs(p0[0] - pn[0]) < 1e-9 and abs(p0[1] - pn[1]) < 1e-9:
                continue
            seg = {"net": net, "layer": layer, "width": BUS_TRACE,
                   "x1": p0[0], "y1": p0[1], "x2": pn[0], "y2": pn[1]}
            for cell in _segment_cells(board, seg, halo=0):
                owner = occ.get((cell[0], cell[1], layer))
                if owner and owner != net:
                    clash = True
                    break
            if clash:
                break
            segs.append(seg)
        if clash:
            blocked += 1
            continue
        plan["tracks"].extend(segs)
        for seg in segs:
            for cell in _segment_cells(board, seg, halo=1):
                occ[(cell[0], cell[1], layer)] = net
        placed += 1
    lens = [sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                for t in plan["tracks"] if t["net"] == net) for net, _a, _b in pairs]
    return placed, blocked, round(max(lens) - min(lens), 1) if lens else None


def bundle_route_ordered(board, plan, prefix, pitch=25.0, layer=3):
    """Row→column bundle with ORDER-PRESERVING L geometry.

    The previous versions recomputed an L per member, so member i's vertical run
    crossed member j's horizontal run and the clearance gate rejected 7 of 8. Here
    the turn positions are monotonic in the same order as the pads, so the bundle
    never crosses itself:

        pad --(vertical stub, lane k)--> turn --(horizontal)--> corridor
             --(vertical)--> dest lane --> pad

    Length spread is NOT yet equalised (that needs reserved lane pitch for jogs);
    this step is about placing every member without clearance conflicts.
    """
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in nets if len(board.nets[n]) >= 2]
    if len(pairs) < 2:
        return 0, 0, None
    # order by source coordinate along the row/column axis
    src_dy = abs(pairs[0][1]["y"] - pairs[-1][1]["y"])
    src_dx = abs(pairs[0][1]["x"] - pairs[-1][1]["x"])
    horizontal_row = src_dx >= src_dy
    pairs.sort(key=lambda t: (t[1]["x"] if horizontal_row else t[1]["y"]))
    occ = {}
    for t in plan.get("tracks") or []:
        for cell in _segment_cells(board, t, halo=1):
            occ[cell] = t["net"]
    placed = blocked = 0
    n = len(pairs)
    src_ref = min(p[1]["y"] for p in pairs)
    dst_side = min(p[2]["x"] for p in pairs)
    # Diagnostics showed member i's horizontal run crossing member 0's corridor
    # vertical. Fix: every horizontal ends at ONE trunk x, and the vertical drops
    # happen BEHIND the trunk (left of it), so no horizontal can reach a vertical
    # that belongs to another member.
    trunk = dst_side - 40.0
    for i, (net, a, b) in enumerate(pairs):
        lane = src_ref + (i + 1) * pitch
        drop_x = trunk - (i + 1) * pitch
        if horizontal_row:
            pts = [(a["x"], a["y"]), (a["x"], lane), (trunk, lane),
                   (drop_x, lane), (drop_x, b["y"]), (b["x"], b["y"])]
        else:
            pts = [(a["x"], a["y"]), (lane, a["y"]), (lane, trunk),
                   (lane, drop_x), (b["x"], drop_x), (b["x"], b["y"])]
        segs, clash = [], False
        for p0, p1 in zip(pts, pts[1:]):
            if abs(p0[0] - p1[0]) < 1e-9 and abs(p0[1] - p1[1]) < 1e-9:
                continue
            seg = {"net": net, "layer": layer, "width": BUS_TRACE,
                   "x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1]}
            for cell in _segment_cells(board, seg, halo=0):
                owner = occ.get((cell[0], cell[1], layer))
                if owner and owner != net:
                    clash = True
                    break
            if clash:
                break
            segs.append(seg)
        if clash:
            blocked += 1
            continue
        plan["tracks"].extend(segs)
        for seg in segs:
            for cell in _segment_cells(board, seg, halo=1):
                occ[(cell[0], cell[1], layer)] = net
        placed += 1
    lens = [sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                for t in plan["tracks"] if t["net"] == net) for net, _a, _b in pairs]
    return placed, blocked, round(max(lens) - min(lens), 1) if lens else None


def bundle_route_fanout(board, plan, prefix, pitch=20.0, layer=3, fan=GRID * 3):
    """Bundle routing with the geometry that was missing: fan-out from each pad into
    the channel, a parallel run, then fan-in to the destination pad.

    Whole-corridor translation placed only 1 of 8 members because the pad pitches
    (100 mil on U5, 50 mil on J3) do not match the bundle pitch, so the shifted
    track ran straight into its neighbour pads.
    """
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in nets if len(board.nets[n]) >= 2]
    if len(pairs) < 2:
        return 0, 0, None
    pairs.sort(key=lambda t: (t[1]["y"], t[1]["x"]))
    # The channel must NOT sit on the pad row: with y_ch == mean(source y) the
    # parallel run and the fan-out both grazed the neighbouring pads, which is why
    # only 1 of 8 members could be placed. Offset the corridor clear of both pad
    # fields.
    src_y = sum(p[1]["y"] for p in pairs) / len(pairs)
    dst_x = sum(p[2]["x"] for p in pairs) / len(pairs)
    y_ch = round((src_y + 5 * GRID) / GRID) * GRID
    x_ch = round((dst_x + 5 * GRID) / GRID) * GRID
    occ = {}
    for t in plan.get("tracks") or []:
        for cell in _segment_cells(board, t, halo=1):
            occ[cell] = t["net"]
    placed = blocked = 0
    esc = pad_escape_dirs(board)
    for i, (net, a, b) in enumerate(pairs):
        off = (i - (len(pairs) - 1) / 2.0) * pitch
        # leave each pad along ITS escape direction first, then join the channel
        ex, ey = esc.get((a["des"], a["pad"]), (0, 1))
        e2x, e2y = esc.get((b["des"], b["pad"]), (0, -1))
        p_out = (a["x"] + ex * fan, a["y"] + ey * fan)
        q_out = (b["x"] + e2x * fan, b["y"] + e2y * fan)
        pts = [(a["x"], a["y"]), p_out,
               (p_out[0], y_ch + off), (x_ch + off, y_ch + off),
               (x_ch + off, q_out[1]), q_out, (b["x"], b["y"])]
        segs, clash = [], False
        for p0, p1 in zip(pts, pts[1:]):
            if abs(p0[0] - p1[0]) < 1e-9 and abs(p0[1] - p1[1]) < 1e-9:
                continue
            seg = {"net": net, "layer": layer, "width": BUS_TRACE,
                   "x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1]}
            for cell in _segment_cells(board, seg, halo=0):
                owner = occ.get((cell[0], cell[1], layer))
                if owner and owner != net:
                    clash = True
                    break
            if clash:
                break
            segs.append(seg)
        if clash:
            blocked += 1
            continue
        plan["tracks"].extend(segs)
        for seg in segs:
            for cell in _segment_cells(board, seg, halo=0):
                occ[(cell[0], cell[1], layer)] = net
        placed += 1
    lens = [sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
                for t in plan["tracks"] if t["net"] == net) for net, _a, _b in pairs]
    return placed, blocked, round(max(lens) - min(lens), 1) if lens else None


def quality_metrics(plan):
    """Professional numbers DRC cannot express: 45-degree share, length per layer,
    and how well bus groups are length-matched. An ace engineer optimises these,
    so the toolchain must report them."""
    per_layer = defaultdict(float)
    total = diag = 0.0
    for t in plan.get("tracks") or []:
        length = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        total += length
        per_layer[int(t["layer"])] += length
        if abs(t["x2"] - t["x1"]) > 1e-9 and abs(t["y2"] - t["y1"]) > 1e-9:
            diag += length
    net_len = defaultdict(float)
    for t in plan.get("tracks") or []:
        net_len[t["net"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
    groups = defaultdict(set)
    for net in net_len:
        for prefix in ("CAM_D", "LCD_", "SD_"):
            if net.startswith(prefix):
                groups[prefix].add(net)
                break
    spread = {}
    for prefix, nets in groups.items():
        lens = sorted(net_len[n] for n in nets)
        if len(lens) >= 2:
            spread[prefix] = round(lens[-1] - lens[0], 1)
    return {
        "diagonal_ratio": round(diag / total, 3) if total else 0.0,
        "layer_length_mil": {str(k): round(v, 1) for k, v in sorted(per_layer.items())},
        "bus_length_spread_mil": spread,
    }


def report(board, routed, failures, overflow, plan):
    per_net = defaultdict(float)
    for t in plan["tracks"]:
        per_net[t["net"]] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
    kpi = {
        # `failures is None` means "this command cannot see the router's failure
        # list" (a plan read back from disk has no `paths`). Reporting 0 there
        # would repeat bug #3 from the handoff: the gate passing a KPI it never
        # measured. `None` is a gate failure, never a pass.
        "unrouted_legs": None if failures is None else len(failures),
        "congestion_cells": congestion_from_plan(board, plan),
        "nets_unconnected": len(connectivity_from_plan(board, plan)),
        "pad_layer_gaps": pad_layer_gaps(board, plan),
        "pour_islands": pour_islands(board, plan),
        "clearance_violations": clearance_violations(board, plan),
        "vias": len(plan["vias"]),
        "plane_vias": sum(1 for v in plan["vias"] if v.get("plane_layer")),
        "vias_in_pad": sum(1 for v in plan["vias"] if v.get("in_pad")),
        "tracks": len(plan["tracks"]),
        "total_length_mil": round(sum(per_net.values()), 1),
        "hpwl_mil": round(hpwl(board.comps), 1),
        "overlaps": n_overlaps(board.comps),
        "outside": n_outside(board.comps, board),
        "longest_nets": sorted(((round(v, 1), k) for k, v in per_net.items()), reverse=True)[:5],
    }
    kpi.update(quality_metrics(plan))
    return kpi


def gate(kpi):
    failures = {k: kpi[k] for k in KPI_KEYS if kpi.get(k, 0) != 0}
    return (not failures), failures


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="offline layout+routing toolchain")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("place")
    p.add_argument("dump")
    p.add_argument("--iters", type=int, default=40000)
    p.add_argument("--face-w", dest="face_w", type=float, default=FACE_W,
                   help="weight of the pad-field facing term (mil-equivalent per (1-cos))")
    p.add_argument("--btn-w", dest="btn_w", type=float, default=BTN_W,
                   help="weight of the button-leg term (mil-equivalent per 1000 mil)")
    p.add_argument("--bus-w", dest="bus_w", type=float, default=ROUTABLE_W,
                   help="weight of the pin-order term (0 = pure HPWL plus the new terms)")
    p.add_argument("--out", required=True)

    r = sub.add_parser("route")
    r.add_argument("dump")
    r.add_argument("--place")
    r.add_argument("--iters", type=int, default=10)
    r.add_argument("--layers", type=int, default=2)
    r.add_argument("--spacing-hard", dest="spacing_hard", action="store_true",
                   help="treat other nets' tracks (+1 cell halo) as hard obstacles instead of cost")
    r.add_argument("--out", required=True)
    r.add_argument("--plane-net", dest="plane_nets", action="append", default=[],
                   help="net carried by a plane instead of tracks (e.g. GND)")
    r.add_argument("--plane-layer", dest="plane_layer", type=int,
                   help="inner layer the plane occupies; other nets are kept off it")
    r.add_argument("--via-check", dest="via_check", action="store_true",
                   help="reject paths whose vias overlap other copper (measured worse: unrouted 7 -> 25)")
    r.add_argument("--via-sites", dest="via_sites", action="store_true",
                   help="reserve via sites and price dirty layer transitions")
    r.add_argument("--via-cost", dest="via_cost", type=float,
                   help="cost of one layer change (default %g); higher = fewer vias" % VIA_COST)
    r.add_argument("--via-negotiate", dest="via_negotiate", action="store_true",
                   help="feed bad via sites into the router's history negotiator")
    r.add_argument("--via-plan", dest="via_plan", action="store_true",
                   help="route pad -> legal via site -> layer -> legal via site -> pad")
    r.add_argument("--via-first", dest="via_first", action="store_true",
                   help="plan every pad via site up front and route through them")
    r.add_argument("--pour-net", dest="pour_nets", action="append", default=[],
                   help="net carried by an area pour on --pour-layer (shares the layer)")
    r.add_argument("--pour-layer", dest="pour_layer", type=int)
    r.add_argument("--pour-step", dest="pour_step", type=int, default=5,
                   help="how far an access via may sit from its pad, in grid cells")
    r.add_argument("--net-order", dest="net_order", choices=("big", "small"), default="small",
                   help="order nets by pad count: big first (default) or small first")

    q = sub.add_parser("report")
    q.add_argument("dump")
    q.add_argument("--plan", required=True)
    q.add_argument("--place")
    q.add_argument("--out")

    c = sub.add_parser("check")
    c.add_argument("dump")
    c.add_argument("--plan", required=True)
    c.add_argument("--place")

    a = ap.parse_args()
    dump = json.loads(open(a.dump, encoding="utf-8").read())
    board = Board(dump)

    if a.cmd == "place":
        placed = optimize_placement(board, a.iters, face_w=a.face_w, btn_w=a.btn_w,
                                    bus_w=a.bus_w)
        json.dump(placed, open(a.out, "w", encoding="utf-8"), indent=1)
        apply_placement(board, placed)
        print(f"placed {len(placed)} parts; hpwl {hpwl(board.comps):.0f} "
              f"face {escape_face_penalty(board.comps):.3f} "
              f"btn {button_leg_penalty(board.comps):.3f} "
              f"bus {bus_order_penalty(board.comps):.3f} "
              f"overlaps {n_overlaps(board.comps)} outside {n_outside(board.comps, board)} -> {a.out}")
        return 0

    if a.place:
        apply_placement(board, json.loads(open(a.place, encoding="utf-8").read()))

    if a.cmd == "route":
        (unrouted, overflow), routed, failures = route(board, a.iters, a.layers,
                                                       getattr(a, "spacing_hard", False),
                                                       plane_nets=frozenset(a.plane_nets),
                                                       plane_layer=a.plane_layer,
                                                       via_check=a.via_check,
                                                       via_sites=a.via_sites,
                                                       via_cost=a.via_cost,
                                                       via_negotiate=a.via_negotiate,
                                                       via_plan=a.via_plan,
                                                       via_first=a.via_first,
                                                       net_order=a.net_order,
                                                       pour_nets=frozenset(a.pour_nets),
                                                       pour_layer=a.pour_layer,
                                                       pour_step=a.pour_step)
        plan = plan_from(board, routed)
        plan["router_congestion"] = overflow
        plan["plan_congestion"] = congestion_from_plan(board, plan)
        json.dump(plan, open(a.out, "w", encoding="utf-8"), indent=1)
        kpi = report(board, routed, failures, [], plan)
        print(json.dumps({"unrouted_legs": kpi["unrouted_legs"],
                          "router_congestion": plan["router_congestion"],
                          "plan_congestion": plan["plan_congestion"],
                          "nets_unconnected": kpi["nets_unconnected"],
                          "clearance_violations": kpi["clearance_violations"],
                          "vias": plan["vias"] if isinstance(plan["vias"], int) else len(plan["vias"]),
                          "tracks": len(plan["tracks"])}, ensure_ascii=False))
        return 0

    plan = json.loads(open(a.plan, encoding="utf-8").read())
    routed = defaultdict(list)
    for net, paths in (plan.get("paths") or {}).items():   # optional
        routed[net] = paths
    # The gate must judge exactly what report() computes: an earlier version
    # overwrote congestion with 0 here, so `check` passed a KPI it had never
    # measured.  Same trap for unrouted legs: a plan on disk carries no `paths`,
    # so the leg count is UNMEASURED, not zero.
    measured_legs = bool(plan.get("paths"))
    kpi = report(board, routed, [] if measured_legs else None, [], plan)
    ok, failures = gate(kpi)
    if a.cmd == "check":
        print(json.dumps({"kpi": kpi, "failures": failures, "pass": ok}, ensure_ascii=False, indent=1))
        return 0 if ok else 1
    if a.out:
        json.dump(kpi, open(a.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(kpi, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())










