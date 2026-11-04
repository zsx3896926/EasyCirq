"""Offline two-layer grid maze router: the P2 "routability oracle".

The board is rasterised into square cells of ``grid_mm`` (cells fully inside the
board; anything outside the board simply does not exist, i.e. it is blocked).
Each (layer, cell) position is either

* blocked -- a component body or a keepout covers the cell (all layers),
* free,
* occupied by a committed net trace, or
* reserved as a pin-access terminal for one net.

Placement pins are snapped to the nearest free grid cell (deterministically: by
Euclidean distance, ties by lower y then lower x).  Multi-pin nets are
decomposed into a deterministic Manhattan minimum spanning tree and every tree
edge is routed with an A* maze search; changing layer costs a via.  Nets are
routed one at a time in a deterministic order (critical nets first when
``critical_nets`` is given, then scenario net order).

When a net cannot be routed because another net's copper is in the way, a
bounded rip-up-and-reroute pass is attempted: the blocking nets are identified
with a relaxed A* (crossing foreign copper is expensive but allowed), ripped
up, the stuck net is routed first and the ripped nets are rerouted afterwards.
A rip-up is accepted only if *every* affected net can be rerouted, so one
hard-to-route net never damages the statistics of the others.

Everything is pure standard library and fully deterministic for a given
(scenario, grid, placement, critical_nets) input: no RNG, no time-dependent
decisions.  ``RouteResult.runtime_s`` is the only non-deterministic field.

Metric definitions
------------------
``completion``
    fraction of *scored* nets that got routed.  The scored set is
    ``critical_nets`` (unknown names ignored) when a non-empty list is given,
    otherwise every net in the scenario.  A net with fewer than two pins is
    complete by construction.
``failed_nets``
    every net that was not routed, in routing order (not just the scored ones).
``wirelength_mm``
    total routed copper length in mm: one ``grid_mm`` per grid step plus the
    pad-to-terminal escape distance of every pin of every routed net.
``vias``
    number of layer changes used by routed nets.
``overflow``
    residual capacity overflow: number of foreign-occupied (layer, cell)
    positions a relaxed route of a still-failed net would need.  It is 0 when
    every net routed, and it stays 0 for nets that are geometrically trapped
    (no rip-up could ever help those).
"""

from __future__ import annotations

import heapq
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .model import Placement, Scenario, bbox, pad_position

_MOVE_COST = 1
_VIA_COST = 4
# Cost of crossing another net's copper while *planning* a rip-up (soft mode).
_FOREIGN_PENALTY = 40
# Cost of crossing another net's reserved pin-access terminal.  Terminals can
# never be freed by a rip-up, so the planner detours around them whenever any
# pad-free route exists (the large weight makes that the primary objective).
_PAD_PENALTY = 10 ** 6
_MAX_RIPUP_NETS = 4
_RIPUP_ROUNDS = 2
_INF = 10 ** 18

_NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass
class RouteResult:
    """Summary of one routing run produced by :class:`GridRouter`."""

    completion: float  # 0..1 fraction of scored nets completed
    failed_nets: List[str] = field(default_factory=list)
    wirelength_mm: float = 0.0
    vias: int = 0
    overflow: int = 0
    runtime_s: float = 0.0


class GridRouter:
    """Two-layer grid maze router used as an offline routability oracle."""

    def __init__(self, scenario: Scenario, grid_mm: float = 1.0, layers: int = 2):
        if grid_mm <= 0.0:
            raise ValueError("grid_mm must be positive")
        if layers < 1:
            raise ValueError("layers must be >= 1")
        self.scenario = scenario
        self.grid_mm = float(grid_mm)
        self.layers = int(layers)
        # Only cells fully inside the board are routable (board outside == blocked).
        self.nx = max(1, int(math.floor(scenario.board_w / self.grid_mm + 1e-9)))
        self.ny = max(1, int(math.floor(scenario.board_h / self.grid_mm + 1e-9)))
        self.n_cells = self.nx * self.ny
        self._net_names = [net.name for net in scenario.nets]
        self._net_by_name: Dict[str, int] = {name: i for i, name in enumerate(self._net_names)}
        self._name_by_net: Dict[int, str] = {i: name for i, name in enumerate(self._net_names)}
        # Per-run state (initialised by _prepare).
        self._blocked: List[bool] = []
        self._occ: List[int] = []
        self._term_owner: List[int] = []
        self._terminals: Dict[str, List[Optional[int]]] = {}
        self._pin_escapes: Dict[str, List[float]] = {}
        self._routes: Dict[str, Dict[str, object]] = {}
        self._states_by_net: Dict[int, Set[int]] = {}
        self._reach_cache: Dict[int, Set[int]] = {}
        self._overflow = 0

    # ------------------------------------------------------------------ API

    def route(
        self,
        placement: Placement,
        critical_nets: Optional[Sequence[str]] = None,
    ) -> RouteResult:
        """Route ``placement`` and return a deterministic :class:`RouteResult`."""
        t_start = time.perf_counter()
        self._prepare(placement)
        order = self._routing_order(critical_nets)

        # ---- first pass: sequential maze routing -------------------------
        for name in order:
            cells = self._terminals.get(name)
            if cells is None or any(cell is None for cell in cells):
                continue  # missing placement / pin: cannot be routed
            if len(cells) <= 1:
                self._routes[name] = {"wirelength": 0.0, "vias": 0, "states": frozenset()}
                continue
            self._route_net(name)

        # ---- bounded rip-up and reroute ----------------------------------
        for _round in range(_RIPUP_ROUNDS):
            failed = [n for n in order if n not in self._routes and self._ripup_candidate(n)]
            if not failed:
                break
            changed = False
            for name in failed:
                if self._try_ripup(name):
                    changed = True
            if not changed:
                break

        # ---- statistics ---------------------------------------------------
        scored = self._scored_names(critical_nets)
        routed_scored = sum(1 for n in scored if n in self._routes)
        completion = (routed_scored / len(scored)) if scored else 1.0
        failed_nets = [n for n in order if n not in self._routes]
        wirelength = 0.0
        vias = 0
        for name in order:
            info = self._routes.get(name)
            if info is None:
                continue
            wirelength += float(info["wirelength"])
            vias += int(info["vias"])
        overflow = self._residual_overflow(failed_nets)
        runtime = time.perf_counter() - t_start
        return RouteResult(
            completion=completion,
            failed_nets=failed_nets,
            wirelength_mm=wirelength,
            vias=vias,
            overflow=overflow,
            runtime_s=runtime,
        )

    # -------------------------------------------------------------- helpers

    def _routing_order(self, critical_nets: Optional[Sequence[str]]) -> List[str]:
        if not critical_nets:
            return list(self._net_names)
        crit: List[str] = []
        seen: Set[str] = set()
        for name in critical_nets:
            if name in self._net_by_name and name not in seen:
                crit.append(name)
                seen.add(name)
        return crit + [name for name in self._net_names if name not in seen]

    def _scored_names(self, critical_nets: Optional[Sequence[str]]) -> List[str]:
        if critical_nets:
            wanted = set(critical_nets)
            scored = [n for n in self._net_names if n in wanted]
            if scored:
                return scored
        return list(self._net_names)

    def _prepare(self, placement: Placement) -> None:
        self._blocked = self._build_blocked(placement)
        self._occ = [-1] * (self.layers * self.n_cells)
        self._term_owner = [-1] * self.n_cells
        self._terminals = {}
        self._pin_escapes = {}
        self._routes = {}
        self._states_by_net = {}
        self._reach_cache = {}
        self._overflow = 0
        g = self.grid_mm
        nx = self.nx
        for net_id, net in enumerate(self.scenario.nets):
            cells: List[Optional[int]] = []
            escapes: List[float] = []
            for ref, pin in net.pins:
                comp = self.scenario.components.get(ref)
                if comp is None or ref not in placement:
                    cells.append(None)
                    escapes.append(0.0)
                    continue
                x, y, rot = placement[ref]
                px, py = pad_position(comp, x, y, rot, pin)
                cell = self._nearest_free_cell(px, py, net_id)
                cells.append(cell)
                if cell is None:
                    escapes.append(0.0)
                else:
                    cx = ((cell % nx) + 0.5) * g
                    cy = ((cell // nx) + 0.5) * g
                    escapes.append(math.hypot(cx - px, cy - py))
            self._terminals[net.name] = cells
            self._pin_escapes[net.name] = escapes

    def _build_blocked(self, placement: Placement) -> List[bool]:
        blocked = [False] * self.n_cells
        for ref, comp in self.scenario.components.items():
            if ref not in placement:
                continue
            x, y, rot = placement[ref]
            self._mark_rect(blocked, bbox(comp, x, y, rot))
        for rect in self.scenario.keepouts:
            self._mark_rect(blocked, rect)
        return blocked

    def _mark_rect(self, blocked: List[bool], rect: Tuple[float, float, float, float]) -> None:
        g = self.grid_mm
        x0, y0, x1, y1 = rect
        i0 = max(0, int(math.ceil(x0 / g - 0.5 - 1e-9)))
        i1 = min(self.nx - 1, int(math.floor(x1 / g - 0.5 + 1e-9)))
        j0 = max(0, int(math.ceil(y0 / g - 0.5 - 1e-9)))
        j1 = min(self.ny - 1, int(math.floor(y1 / g - 0.5 + 1e-9)))
        if i0 > i1 or j0 > j1:
            return
        for j in range(j0, j1 + 1):
            base = j * self.nx
            for i in range(i0, i1 + 1):
                blocked[base + i] = True

    def _nearest_free_cell(self, px: float, py: float, net_id: int) -> Optional[int]:
        """Nearest unblocked cell not reserved by another net (ties: low y, then low x)."""
        g = self.grid_mm
        nx, ny = self.nx, self.ny
        bi = min(nx - 1, max(0, int(px / g)))
        bj = min(ny - 1, max(0, int(py / g)))
        best_key: Optional[Tuple[float, int, int]] = None
        best_cell = -1
        r_max = max(nx, ny)
        for r in range(r_max + 1):
            # Any cell on ring r or farther is at least (r - 1) * g away from
            # the pin, so once that exceeds the best candidate we can stop.
            if best_key is not None and (r - 1.0) * g > best_key[0] + 1e-12:
                break
            ring: List[Tuple[float, int, int]] = []
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    i = bi + di
                    j = bj + dj
                    if 0 <= i < nx and 0 <= j < ny:
                        cx = (i + 0.5) * g
                        cy = (j + 0.5) * g
                        ring.append((math.hypot(cx - px, cy - py), i, j))
            ring.sort(key=lambda item: (item[0], item[2], item[1]))
            for dist, i, j in ring:
                key = (dist, j, i)
                if best_key is not None and key >= best_key:
                    break  # the ring is sorted by exactly this key
                cell = j * nx + i
                if self._blocked[cell]:
                    continue
                owner = self._term_owner[cell]
                if owner != -1 and owner != net_id:
                    continue
                best_key = key
                best_cell = cell
                break
        if best_key is None:
            return None
        self._term_owner[best_cell] = net_id
        return best_cell

    # ------------------------------------------------------------ net router

    def _terminal_mst(self, cells: Sequence[int]) -> List[Tuple[int, int]]:
        """Deterministic O(n^2) Prim MST over terminal cells (Manhattan metric)."""
        n = len(cells)
        if n <= 1:
            return []
        nx = self.nx

        def manhattan(a: int, b: int) -> int:
            return abs(a % nx - b % nx) + abs(a // nx - b // nx)

        used = [False] * n
        used[0] = True
        dist = [manhattan(cells[0], cells[k]) for k in range(n)]
        parent = [0] * n
        dist[0] = _INF
        edges: List[Tuple[int, int]] = []
        for _ in range(n - 1):
            best = -1
            for k in range(n):
                if not used[k] and (best == -1 or dist[k] < dist[best]):
                    best = k
            used[best] = True
            edges.append((parent[best], best))
            for k in range(n):
                if used[k]:
                    continue
                d = manhattan(cells[best], cells[k])
                if d < dist[k]:
                    dist[k] = d
                    parent[k] = best
        return edges

    def _route_net(self, name: str) -> bool:
        if name in self._routes:
            return True
        net_id = self._net_by_name[name]
        cells = self._terminals.get(name)
        if cells is None or any(cell is None for cell in cells):
            return False
        if len(cells) <= 1:
            self._routes[name] = {"wirelength": 0.0, "vias": 0, "states": frozenset()}
            return True
        wirelength = 0.0
        vias = 0
        for a, b in self._terminal_mst(cells):
            if cells[a] == cells[b]:
                continue
            # A branch of the tree must start on a layer where the net already
            # has copper at the junction terminal; otherwise it would be a
            # physically disconnected branch (a via would be needed instead).
            start_layers = self._copper_layers(net_id, cells[a])  # type: ignore[arg-type]
            path = self._astar(  # type: ignore[arg-type]
                net_id, cells[a], cells[b], soft=False, start_layers=start_layers
            )
            if path is None:
                # A failed net must not keep any copper / statistics.
                self._release_net(net_id)
                return False
            edge_wl, edge_vias = self._path_metrics(path)
            wirelength += edge_wl
            vias += edge_vias
            self._commit(net_id, path)
        wirelength += sum(self._pin_escapes[name])
        states = frozenset(self._states_by_net.get(net_id, set()))
        self._routes[name] = {"wirelength": wirelength, "vias": vias, "states": states}
        return True

    def _copper_layers(self, net_id: int, cell: int) -> Optional[Set[int]]:
        """Layers on which the net already has committed copper at ``cell``."""
        states = self._states_by_net.get(net_id)
        if not states:
            return None
        n = self.n_cells
        layers = {state // n for state in states if state % n == cell}
        return layers or None

    def _commit(self, net_id: int, path: Sequence[int]) -> None:
        states = self._states_by_net.setdefault(net_id, set())
        occ = self._occ
        for state in path:
            occ[state] = net_id
            states.add(state)

    def _path_metrics(self, path: Sequence[int]) -> Tuple[float, int]:
        wirelength = 0.0
        vias = 0
        n = self.n_cells
        for prev, cur in zip(path, path[1:]):
            if prev // n == cur // n:
                wirelength += self.grid_mm
            else:
                vias += 1
        return wirelength, vias

    def _release_net(self, net_id: int) -> None:
        states = self._states_by_net.pop(net_id, None)
        if not states:
            return
        occ = self._occ
        for state in states:
            if occ[state] == net_id:
                occ[state] = -1

    def _release_route(self, name: str) -> None:
        if self._routes.pop(name, None) is None:
            return
        self._release_net(self._net_by_name[name])

    def _restore_route(self, name: str, info: Dict[str, object]) -> None:
        net_id = self._net_by_name[name]
        states = set(info["states"])  # type: ignore[arg-type]
        self._routes[name] = info
        self._states_by_net[net_id] = states
        occ = self._occ
        for state in states:
            occ[state] = net_id

    # ------------------------------------------------------------------- A*

    def _astar(
        self,
        net_id: int,
        start_cell: int,
        goal_cell: int,
        soft: bool = False,
        start_layers: Optional[Set[int]] = None,
    ) -> Optional[List[int]]:
        """Shortest path between two terminal cells.

        Hard mode treats other nets' copper and terminals as impassable.  Soft
        mode (used only for rip-up planning and overflow accounting) lets the
        search cross other nets' copper/terminals at a high penalty.
        ``start_layers`` restricts the layers the path may start on (used to
        keep the branches of a multi-pin net physically connected).
        """
        if start_cell == goal_cell:
            return [start_cell]
        n = self.n_cells
        layers = self.layers
        total = layers * n
        nx, ny = self.nx, self.ny
        blocked = self._blocked
        occ = self._occ
        owner = self._term_owner
        gi = goal_cell % nx
        gj = goal_cell // nx
        gscore = [_INF] * total
        parent = [-2] * total
        heap: List[Tuple[int, int, int]] = []
        if start_layers is None:
            candidate_layers = range(layers)
        else:
            candidate_layers = [layer for layer in sorted(start_layers) if 0 <= layer < layers]
        for layer in candidate_layers:
            state = layer * n + start_cell
            other = occ[state]
            if other != -1 and other != net_id and not soft:
                continue
            gscore[state] = 0
            parent[state] = -1
            heap.append((abs(start_cell % nx - gi) + abs(start_cell // nx - gj), 0, state))
        if not heap:
            return None
        heapq.heapify(heap)
        push = heapq.heappush
        pop = heapq.heappop
        while heap:
            f, g, state = pop(heap)
            if g != gscore[state]:
                continue
            cell = state % n
            if cell == goal_cell:
                path: List[int] = []
                cur = state
                while cur != -1:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                return path
            layer = state // n
            base = layer * n
            i = cell % nx
            j = cell // nx
            for di, dj in _NEIGHBOURS:
                ni = i + di
                nj = j + dj
                if ni < 0 or ni >= nx or nj < 0 or nj >= ny:
                    continue
                ncell = nj * nx + ni
                if blocked[ncell]:
                    continue
                if not soft:
                    ow = owner[ncell]
                    if ow != -1 and ow != net_id:
                        continue
                nstate = base + ncell
                if soft:
                    step = _MOVE_COST
                    ow = owner[ncell]
                    if ow != -1 and ow != net_id:
                        step += _PAD_PENALTY
                else:
                    step = _MOVE_COST
                other = occ[nstate]
                if other != -1 and other != net_id:
                    if not soft:
                        continue
                    step += _FOREIGN_PENALTY
                ng = g + step
                if ng < gscore[nstate]:
                    gscore[nstate] = ng
                    parent[nstate] = state
                    h = abs(ni - gi) + abs(nj - gj)
                    push(heap, (ng + h, ng, nstate))
            if layers > 1:
                for layer2 in (layer - 1, layer + 1):
                    if layer2 < 0 or layer2 >= layers:
                        continue
                    nstate = layer2 * n + cell
                    other = occ[nstate]
                    if other != -1 and other != net_id:
                        if not soft:
                            continue
                        step = _VIA_COST + _FOREIGN_PENALTY
                    else:
                        step = _VIA_COST
                    ng = g + step
                    if ng < gscore[nstate]:
                        gscore[nstate] = ng
                        parent[nstate] = state
                        h = abs(i - gi) + abs(j - gj)
                        push(heap, (ng + h, ng, nstate))
        return None

    # -------------------------------------------------------------- rip-up

    def _reachable_cells(self, net_id: int) -> Set[int]:
        cached = self._reach_cache.get(net_id)
        if cached is not None:
            return cached
        name = self._name_by_net[net_id]
        cells = self._terminals[name]
        start = cells[0]
        blocked = self._blocked
        nx, ny = self.nx, self.ny
        seen: Set[int] = {start}  # type: ignore[arg-type]
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            i = cell % nx
            j = cell // nx
            for di, dj in _NEIGHBOURS:
                ni = i + di
                nj = j + dj
                if ni < 0 or ni >= nx or nj < 0 or nj >= ny:
                    continue
                ncell = nj * nx + ni
                if ncell in seen or blocked[ncell]:
                    continue
                seen.add(ncell)
                queue.append(ncell)
        self._reach_cache[net_id] = seen
        return seen

    def _geometric_connected(self, name: str) -> bool:
        cells = self._terminals.get(name)
        if cells is None or any(cell is None for cell in cells) or len(cells) < 2:
            return False
        reach = self._reachable_cells(self._net_by_name[name])
        return all(cell in reach for cell in cells)  # type: ignore[arg-type]

    def _ripup_candidate(self, name: str) -> bool:
        cells = self._terminals.get(name)
        if cells is None or any(cell is None for cell in cells) or len(cells) < 2:
            return False
        # No rip-up can help a net whose terminals are in different free components.
        return self._geometric_connected(name)

    def _soft_plan(
        self, name: str
    ) -> Optional[Tuple[List[List[int]], Set[int], bool]]:
        """Relaxed route for a stuck net: paths, blocker net ids, pad crossings."""
        net_id = self._net_by_name[name]
        cells = self._terminals[name]
        if cells is None or any(cell is None for cell in cells):
            return None
        if len(cells) <= 1:
            return ([], set(), False)
        paths: List[List[int]] = []
        blockers: Set[int] = set()
        crosses_pad = False
        for a, b in self._terminal_mst(cells):
            if cells[a] == cells[b]:
                continue
            path = self._astar(net_id, cells[a], cells[b], soft=True)  # type: ignore[arg-type]
            if path is None:
                return None
            paths.append(path)
            for state in path:
                other = self._occ[state]
                if other != -1 and other != net_id:
                    blockers.add(other)
                owner = self._term_owner[state % self.n_cells]
                if owner != -1 and owner != net_id:
                    crosses_pad = True
        return paths, blockers, crosses_pad

    def _try_ripup(self, name: str) -> bool:
        plan = self._soft_plan(name)
        if plan is None:
            return False
        _paths, blockers, crosses_pad = plan
        if crosses_pad or not blockers or len(blockers) > _MAX_RIPUP_NETS:
            return False
        blocker_names = [self._name_by_net[b] for b in blockers]
        blocker_names.sort(key=lambda n: self._net_by_name[n])
        saved: Dict[str, Dict[str, object]] = {}
        for blocker in blocker_names:
            info = self._routes.get(blocker)
            if info is None:
                return False
            saved[blocker] = info
        for blocker in blocker_names:
            self._release_route(blocker)
        ok = self._route_net(name)
        if ok:
            for blocker in blocker_names:
                if not self._route_net(blocker):
                    ok = False
                    break
        if not ok:
            self._release_route(name)
            for blocker in blocker_names:
                self._release_route(blocker)
            for blocker, info in saved.items():
                self._restore_route(blocker, info)
            return False
        self._overflow += len(blocker_names)
        return True

    # ------------------------------------------------------------ overflow

    def _residual_overflow(self, failed_nets: Sequence[str]) -> int:
        """Copper cells a relaxed route of a stuck net still has to cross."""
        total = 0
        for name in failed_nets:
            if not self._ripup_candidate(name):
                continue
            net_id = self._net_by_name[name]
            cells = self._terminals[name]
            edges = self._terminal_mst(cells)  # type: ignore[arg-type]
            for a, b in edges:
                if cells[a] == cells[b]:  # type: ignore[index]
                    continue
                path = self._astar(net_id, cells[a], cells[b], soft=True)  # type: ignore[arg-type]
                if path is None:
                    continue
                for state in path:
                    other = self._occ[state]
                    if other != -1 and other != net_id:
                        total += 1
        return total
