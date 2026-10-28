"""Dependency graphs for power domains and generated steps.

The graphs are deterministic: ids are visited in sorted order and the
topological order uses a stable tie-break, so re-ordering objects in the input
JSON does not re-order the plan.
"""
from __future__ import annotations

import heapq


def build_domain_graph(domains):
    """Return nodes/edges/order plus cycle and missing-dependency findings."""
    nodes = {domain['id']: domain for domain in domains if domain.get('id')}
    missing = []
    self_dependencies = []
    for domain_id in sorted(nodes):
        for dep in nodes[domain_id].get('depends_on') or []:
            target = dep.get('domain')
            if target == domain_id:
                self_dependencies.append({'domain': domain_id,
                                          'wrong_position': domain_id})
            elif target not in nodes:
                missing.append({'domain': domain_id, 'missing': target})

    edges = []
    dependents = {domain_id: [] for domain_id in nodes}
    for domain_id in sorted(nodes):
        for dep in nodes[domain_id].get('depends_on') or []:
            target = dep.get('domain')
            if target not in nodes or target == domain_id:
                continue
            edges.append({'from': target, 'to': domain_id,
                          'reason': dep.get('reason')})
            dependents[target].append(domain_id)
    for domain_id in dependents:
        dependents[domain_id].sort()

    cycles = find_cycles(nodes, edges)
    order = topological_order(nodes, edges)
    depth = _depths(nodes, edges, order, cycles)
    graph_nodes = []
    for domain_id in sorted(nodes):
        graph_nodes.append({
            'id': domain_id,
            'net': nodes[domain_id].get('net'),
            'depends_on': sorted({dep['domain'] for dep in
                                  (nodes[domain_id].get('depends_on') or [])
                                  if dep.get('domain')}),
            'dependents': dependents[domain_id],
            'depth': depth.get(domain_id),
            'executable': not missing and not cycles
            and nodes[domain_id].get('operating_min_v') is not None,
        })
    return {'nodes': graph_nodes, 'edges': edges, 'order': order,
            'cycles': cycles, 'missing_dependencies': missing,
            'self_dependencies': self_dependencies,
            'acyclic': not cycles and not missing and not self_dependencies}


def find_cycles(nodes, edges):
    adjacency = {node_id: [] for node_id in nodes}
    for edge in edges:
        adjacency.setdefault(edge['from'], []).append(edge['to'])
    for node_id in adjacency:
        adjacency[node_id].sort()
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {node_id: WHITE for node_id in nodes}
    cycles = []
    seen = set()

    def visit(node_id, stack):
        colour[node_id] = GREY
        stack.append(node_id)
        for target in adjacency.get(node_id, []):
            if target not in colour:
                continue
            if colour[target] == GREY:
                index = stack.index(target)
                cycle = stack[index:] + [target]
                key = tuple(sorted(set(cycle)))
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif colour[target] == WHITE:
                visit(target, stack)
        stack.pop()
        colour[node_id] = BLACK

    for node_id in sorted(nodes):
        if colour[node_id] == WHITE:
            visit(node_id, [])
    return cycles


def topological_order(nodes, edges):
    indegree = {node_id: 0 for node_id in nodes}
    adjacency = {node_id: [] for node_id in nodes}
    for edge in edges:
        indegree[edge['to']] = indegree.get(edge['to'], 0) + 1
        adjacency.setdefault(edge['from'], []).append(edge['to'])
    ready = [(node_id, node_id) for node_id, count in indegree.items()
             if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        _key, node_id = heapq.heappop(ready)
        order.append(node_id)
        for target in sorted(adjacency.get(node_id, [])):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, (target, target))
    return order


def _depths(nodes, edges, order, cycles):
    parents = {node_id: [] for node_id in nodes}
    for edge in edges:
        parents.setdefault(edge['to'], []).append(edge['from'])
    depth = {}
    in_cycle = set()
    for cycle in cycles:
        in_cycle.update(cycle)
    for node_id in order:
        if node_id in in_cycle:
            depth[node_id] = None
            continue
        parent_depths = [depth.get(parent) for parent in
                         sorted(parents.get(node_id, []))]
        if any(item is None for item in parent_depths):
            depth[node_id] = None
        else:
            depth[node_id] = 1 + max(parent_depths) if parent_depths else 0
    for node_id in nodes:
        depth.setdefault(node_id, None)
    return depth


def build_step_graph(steps):
    """Graph of generated steps keyed by ``prerequisites`` of kind step."""
    ids = [step['step_id'] for step in steps]
    nodes = {step['step_id']: step for step in steps}
    edges = []
    missing = []
    for step in steps:
        for prereq in step.get('prerequisites') or []:
            if prereq.get('kind') != 'step':
                continue
            target = prereq.get('step_id')
            if target in nodes:
                edges.append({'from': target, 'to': step['step_id']})
            elif target is not None:
                missing.append({'step': step['step_id'], 'missing': target})
    cycles = find_cycles(nodes, edges)
    order = topological_order(nodes, edges)
    return {'order': order, 'edges': edges, 'cycles': cycles,
            'missing_prerequisites': missing, 'acyclic': not cycles and
            not missing, 'step_ids': ids}


def supply_conflicts(domains, assemblies, interfaces):
    """Detect declared external supplies that can feed an active rail."""
    conflicts = []
    for path in assemblies.get('external_supply_paths') or []:
        for domain in domains:
            if path.get('net') != domain.get('net'):
                continue
            protection = domain.get('protection') or {}
            scheme = protection.get('reverse_blocking')
            conflicts.append({
                'code': 'EXTERNAL_SUPPLY_PATH',
                'path_id': path.get('id'),
                'net': path.get('net'),
                'domain': domain.get('id'),
                'can_backfeed': bool(path.get('can_backfeed')),
                'disconnect_required': bool(
                    path.get('disconnect_required_for_deenergized_tests')),
                'reverse_blocking': scheme,
                'blocking': bool(path.get('can_backfeed')) and
                scheme not in ('series_diode', 'ideal_diode', 'power_mux'),
                'resolution': (
                    'disconnect the external supply before energising this '
                    'domain or before de-energised measurements'),
            })
    for interface in interfaces:
        if not interface.get('backfeed_risk'):
            continue
        power_nets = {pin.get('net') for pin in interface.get('pins') or []
                      if pin.get('role') == 'power' and pin.get('net')}
        for domain in domains:
            if domain.get('net') not in power_nets:
                continue
            protection = domain.get('protection') or {}
            scheme = protection.get('reverse_blocking')
            conflicts.append({
                'code': 'INTERFACE_BACKFEED',
                'path_id': interface.get('id'),
                'net': domain.get('net'),
                'domain': domain.get('id'),
                'can_backfeed': True,
                'disconnect_required': True,
                'reverse_blocking': scheme,
                'blocking': scheme not in ('series_diode', 'ideal_diode',
                                           'power_mux'),
                'resolution': (
                    'declare the reverse-blocking/power-mux scheme or treat '
                    'the interface as a conflicting supply that must be '
                    'disconnected'),
            })
    return conflicts
