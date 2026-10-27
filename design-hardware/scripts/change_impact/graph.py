"""Dependency index, deterministic ordering, cycles and traversal budget.

The graph is built only from edges the model declares.  That has a deliberate
consequence the reporter must keep visible: **no edge is not proof of no
impact**.  ``Graph.boundary()`` therefore distinguishes "the declared model ends
here" (a declared boundary) from "the model does not know" (missing edge data).

Traversal is breadth-first with a strict order (edge semantic, then target id),
so identical input yields identical paths regardless of input list order.
Cycles are detected up front (Tarjan SCC) and reported, then terminated by the
visited set during traversal.
"""
from __future__ import annotations

from . import CONFIDENCE_RANK

FORWARD = 'forward'
BIDIRECTIONAL = 'bidirectional'


class Edge:
    __slots__ = ('id', 'source', 'target', 'semantic', 'direction',
                 'conditions', 'certainty', 'evidence', 'note')

    def __init__(self, record):
        self.id = record['id']
        self.source = record['from']
        self.target = record['to']
        self.semantic = record['semantic']
        self.direction = record['direction']
        self.conditions = tuple(record['conditions'])
        self.certainty = record['certainty']
        self.evidence = record['evidence']
        self.note = record['note']

    def as_dict(self):
        return {
            'id': self.id,
            'from': self.source,
            'to': self.target,
            'semantic': self.semantic,
            'direction': self.direction,
            'conditions': list(self.conditions),
            'certainty': self.certainty,
            'evidence': self.evidence,
        }

    def confidence(self, base='certain'):
        """Edge certainty translated to path confidence.

        An ``inferred`` edge makes an otherwise certain rule *possible*; an
        ``unknown`` edge keeps it unknown.  ``observed`` and ``declared`` are
        both strong enough to stay certain, but the evidence is carried along.
        """
        if self.certainty == 'unknown':
            return 'unknown'
        if self.certainty == 'inferred':
            return 'possible' if base == 'certain' else base
        return base


class Graph:
    def __init__(self, model):
        self.model = model
        self.nodes = {}          # id -> object kind
        self._out = {}
        self._in = {}
        for identity in model.object_order:
            self.nodes[identity] = model.objects[identity]['kind']
            self._out.setdefault(identity, [])
            self._in.setdefault(identity, [])
        for record in model.dependencies:
            edge = Edge(record)
            self._out.setdefault(edge.source, []).append(edge)
            self._in.setdefault(edge.target, []).append(edge)
        for identity in self._out:
            self._out[identity].sort(key=lambda item: (item.semantic, item.id))
        for identity in self._in:
            self._in[identity].sort(key=lambda item: (item.semantic, item.id))
        self.cycles = self._find_cycles()

    # -- adjacency ---------------------------------------------------------
    def out_edges(self, identity, semantics=None):
        edges = self._out.get(identity, [])
        if semantics is None:
            return list(edges)
        allowed = frozenset(semantics)
        return [edge for edge in edges
                if edge.semantic in allowed or edge.direction == BIDIRECTIONAL]

    def in_edges(self, identity, semantics=None):
        edges = self._in.get(identity, [])
        if semantics is None:
            return list(edges)
        allowed = frozenset(semantics)
        return [edge for edge in edges
                if edge.semantic in allowed or edge.direction == BIDIRECTIONAL]

    def successor_edges(self, identity, semantics, *, allow_reverse=False):
        """Edges usable to propagate away from ``identity``.

        Forward edges are followed source→target.  A ``bidirectional`` edge is
        usable in both directions.  ``allow_reverse`` additionally permits
        walking declared forward edges backwards, which is only used for
        artifact→layout provenance queries, never for electrical propagation.
        """
        allowed = frozenset(semantics)
        result = []
        for edge in self._out.get(identity, []):
            if edge.semantic in allowed:
                result.append(edge)
        for edge in self._in.get(identity, []):
            if edge.semantic not in allowed:
                continue
            if allow_reverse or edge.direction == BIDIRECTIONAL:
                result.append(edge)
        result.sort(key=lambda item: (item.semantic, item.id))
        return result

    def incoming_semantics(self, identity):
        return sorted({edge.semantic for edge in self._in.get(identity, [])})

    def outgoing_semantics(self, identity):
        return sorted({edge.semantic for edge in self._out.get(identity, [])})

    # -- coverage ----------------------------------------------------------
    def boundary(self, identity):
        """Why propagation stops at ``identity`` and how strong that is."""
        model_scope = self.model.model_scope
        kind = self.nodes.get(identity)
        targets = [edge.target for edge in self._out.get(identity, [])]
        if not targets:
            if model_scope['dependencies_complete'] and \
                    kind in model_scope['declared_kinds']:
                return 'declared_boundary', 'certain'
            return 'missing_edge_data', 'unknown'
        if model_scope['dependencies_complete'] and \
                kind in model_scope['declared_kinds']:
            return 'declared_boundary', 'unknown'
        return 'missing_edge_data', 'unknown'

    # -- cycles ------------------------------------------------------------
    def _find_cycles(self):
        """Tarjan SCCs; a component is a cycle when it has >1 node or a self edge."""
        index = {}
        low = {}
        stack = []
        on_stack = set()
        counter = [0]
        components = []
        adjacency = {identity: [] for identity in self.nodes}
        for identity in self.nodes:
            for edge in self._out.get(identity, []):
                adjacency[identity].append(edge.target)
        for identity in sorted(adjacency):
            adjacency[identity].sort()

        def strongconnect(node):
            index[node] = low[node] = counter[0]
            counter[0] += 1
            stack.append(node)
            on_stack.add(node)
            for target in adjacency[node]:
                if target not in index:
                    strongconnect(target)
                    low[node] = min(low[node], low[target])
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
            if low[node] == index[node]:
                component = []
                while True:
                    item = stack.pop()
                    on_stack.discard(item)
                    component.append(item)
                    if item == node:
                        break
                components.append(sorted(component))

        for identity in sorted(adjacency):
            if identity not in index:
                strongconnect(identity)
        cycles = []
        for component in components:
            if len(component) > 1:
                cycles.append(component)
            elif component:
                node = component[0]
                if any(edge.target == node for edge in self._out.get(node, [])):
                    cycles.append(component)
        cycles.sort()
        return cycles

    # -- determinism helpers ----------------------------------------------
    def confidence_of(self, identities):
        """Weakest edge certainty over the given nodes."""
        levels = []
        for identity in identities:
            for edge in self._out.get(identity, []):
                levels.append(edge.certainty)
        if not levels:
            return 'certain'
        worst = min((_CERTAINTY_RANK[level] for level in levels))
        return _CERTAINTY_NAMES[worst]

    def sort_key(self, identity):
        return (self.nodes.get(identity, 'zzz'), identity)


_CERTAINTY_RANK = {'declared': 3, 'observed': 3, 'inferred': 2, 'unknown': 1}
_CERTAINTY_NAMES = {3: 'declared', 2: 'inferred', 1: 'unknown'}


def weakest(confidences):
    """Weakest confidence among a collection (empty means certain)."""
    worst = 'certain'
    for item in confidences:
        if CONFIDENCE_RANK[item] < CONFIDENCE_RANK[worst]:
            worst = item
    return worst
