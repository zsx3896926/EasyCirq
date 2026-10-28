"""J2: change-class aware impact propagation.

A change is propagated only along dependency semantics that its *change class*
declares as compatible.  There is no blanket graph walk: an edge is followed
only when a rule pairs the change kind with the edge semantic, and every rule
declares which impact kind it produces, how confident that base inference is,
and where propagation is allowed to stop.

The output is deliberately explainable:

* every impacted object has one or more path records;
* a path carries the full ordered step list (``from``/``to``/``edge``/
  ``semantic``/``conditions``), its complete change-origin set, its weakest
  confidence and an explicit stop reason;
* direct impacts (the changed object itself) are recorded with zero steps;
* an object that is only a waypoint of a longer explanation is still recorded
  (it *is* affected) but its record is marked ``deduplicated`` so it is never
  mistaken for the end of a chain;
* missing edges, unknown attribute classes, missing rename-partition evidence
  and exhausted budgets produce ``unknown`` entries instead of a silent "safe".

Only the standard library is used and nothing here mutates the model or calls
out to an EDA/executor.  Ordering is explicit everywhere (no reliance on dict
insertion order, no time, no randomness), so identical input yields identical
output.
"""
from __future__ import annotations

from collections import deque

from . import (
    CHANGE_KINDS,
    CONFIDENCES,
    DEPENDENCY_SEMANTICS,
    IMPACT_KINDS,
    STOP_REASONS,
)
from .graph import weakest
from .model import MISSING, json_equal

# Object kinds at which a rule's chain has reached a natural consumer/end.
# Nothing is inferred further from them: the rule's semantic chain is over.
# ``net`` and ``pin`` are deliberately pass-through carriers, so an absent edge
# there is reported as missing data rather than silently treated as a leaf.
TERMINAL_KINDS = frozenset({
    'component_instance',
    'power_domain',
    'interface',
    'layout_region',
    'mechanical_anchor',
    'bom_line',
    'firmware_contract',
    'test',
    'artifact',
    'requirement',
    'document',
})

# Impacts that deserve a hard-constraint annotation (a constraint is a
# declared requirement the change must be re-checked against).
ELECTRICAL_IMPACTS = frozenset({
    'electrical_state',
    'power_integrity',
    'signal_integrity',
    'pin_compatibility',
    'firmware_compatibility',
})

# Rename: an identity change only speaks about the *partition* through
# electrical semantics; documentation references are a plain documentation
# consequence.
RENAME_ELECTRICAL_SEMANTICS = frozenset({
    'power_supply',
    'signal_path',
    'pin_mapping',
    'firmware_consumer',
})

# ``artifact_source`` reaches different artifact classes; the target kind, not
# the edge, decides the exact impact kind.
ARTIFACT_IMPACT_BY_KIND = {
    'bom_line': 'bom_variant',
    'artifact': 'manufacturing_output',
    'document': 'documentation_only',
}

# Stop reasons, kept as named constants so a typo cannot leak past the enum
# check performed at import time.
STOP_LEAF_OBJECT = 'leaf_object'
STOP_SEMANTIC_MISMATCH = 'semantic_mismatch'
STOP_DISPLAY_ONLY_BOUNDARY = 'display_only_boundary'
STOP_DECLARED_BOUNDARY = 'declared_boundary'
STOP_ALREADY_VISITED = 'already_visited'
STOP_CYCLE_DETECTED = 'cycle_detected'
STOP_DEPTH_BUDGET = 'depth_budget'
STOP_PATH_BUDGET = 'path_budget'
STOP_DEDUPLICATED = 'deduplicated'
STOP_MISSING_EDGE_DATA = 'missing_edge_data'

STOP_REASONS_USED = frozenset({
    STOP_LEAF_OBJECT,
    STOP_SEMANTIC_MISMATCH,
    STOP_DISPLAY_ONLY_BOUNDARY,
    STOP_DECLARED_BOUNDARY,
    STOP_ALREADY_VISITED,
    STOP_CYCLE_DETECTED,
    STOP_DEPTH_BUDGET,
    STOP_PATH_BUDGET,
    STOP_DEDUPLICATED,
    STOP_MISSING_EDGE_DATA,
})

# ``observed`` and ``declared`` are equally strong for confidence purposes but
# are kept distinct in evidence records; only the weaker of the two survives a
# merge and it keeps its original name when possible.
_CERTAINTY_STRENGTH = {'declared': 3, 'observed': 3, 'inferred': 2, 'unknown': 1}


# ---------------------------------------------------------------------------
# rule table
# ---------------------------------------------------------------------------

def _rule(rule_id, change_kinds, semantics, semantic_impacts, direct_impact,
          base_confidence, stop_condition, evidence):
    """Build one rule record.

    ``semantic_impacts`` maps an allowed dependency semantic to
    ``(impact_kind, base_confidence)``.  ``direct_impact`` is the impact of the
    changed object itself (an explanation path with zero steps).
    """
    produced = {impact for impact, _confidence in semantic_impacts.values()}
    produced.add(direct_impact[0])
    if 'artifact_source' in semantics:
        produced.update(ARTIFACT_IMPACT_BY_KIND.values())
    return {
        'rule_id': rule_id,
        'change_kinds': tuple(change_kinds),
        'semantics': tuple(semantics),
        'semantic_impacts': dict(semantic_impacts),
        'direct_impact': tuple(direct_impact),
        'base_confidence': base_confidence,
        'terminal_kinds': TERMINAL_KINDS,
        'stop_condition': stop_condition,
        'evidence': evidence,
        'impacts': tuple(sorted(produced)),
    }


RULES = (
    _rule(
        'R1_power_requirement', ('power_requirement',), ('power_supply',),
        {'power_supply': ('power_integrity', 'certain')},
        ('electrical_state', 'certain'), 'certain',
        'no further declared power_supply edge, or a natural consumer reached',
        'contract §2.2 power_requirement / §2.3 power_supply'),
    _rule(
        'R2_component_identity', ('component_identity',),
        ('footprint_binding', 'power_supply', 'signal_path', 'artifact_source',
         'firmware_consumer'),
        {'footprint_binding': ('footprint_compatibility', 'certain'),
         'power_supply': ('electrical_state', 'possible'),
         'signal_path': ('signal_integrity', 'possible'),
         'artifact_source': ('manufacturing_output', 'certain'),
         'firmware_consumer': ('firmware_compatibility', 'possible')},
        ('electrical_state', 'possible'), 'possible',
        'natural delivery/consumer endpoint; electrical consequence stays unproven',
        'contract §2.2 component_identity; same footprint never proves electrical equivalence'),
    _rule(
        'R3_footprint', ('footprint',),
        ('footprint_binding', 'mechanical_constraint', 'enclosure_constraint',
         'artifact_source'),
        {'footprint_binding': ('footprint_compatibility', 'certain'),
         'mechanical_constraint': ('mechanical_fit', 'certain'),
         'enclosure_constraint': ('enclosure_interface', 'possible'),
         'artifact_source': ('assembly_fit', 'certain')},
        ('footprint_compatibility', 'certain'), 'certain',
        'no further footprint_binding/mechanical/enclosure edge',
        'contract §2.2 footprint; contract §6 C/G'),
    _rule(
        'R4_pin_mapping', ('pin_mapping',),
        ('pin_mapping', 'signal_path', 'power_supply', 'firmware_consumer'),
        {'pin_mapping': ('pin_compatibility', 'certain'),
         'signal_path': ('signal_integrity', 'certain'),
         'power_supply': ('electrical_state', 'certain'),
         'firmware_consumer': ('firmware_compatibility', 'possible')},
        ('pin_compatibility', 'certain'), 'certain',
        'no further pin/electrical/firmware consumer edge',
        'contract §2.2 pin_mapping'),
    _rule(
        'R5_mechanical_pose', ('mechanical_pose',),
        ('mechanical_constraint', 'enclosure_constraint', 'artifact_source',
         'signal_path'),
        {'mechanical_constraint': ('mechanical_fit', 'certain'),
         'enclosure_constraint': ('enclosure_interface', 'possible'),
         'artifact_source': ('assembly_fit', 'possible'),
         'signal_path': ('signal_integrity', 'possible')},
        ('mechanical_fit', 'certain'), 'certain',
        'no further mechanical/enclosure/assembly edge',
        'contract §2.2 mechanical_pose; contract §6 G interface pose'),
    _rule(
        'R6_identity_rename', ('identity_rename',),
        ('document_reference', 'signal_path', 'power_supply', 'pin_mapping',
         'firmware_consumer', 'artifact_source'),
        {'document_reference': ('documentation_only', 'certain'),
         'signal_path': ('signal_integrity', 'possible'),
         'power_supply': ('electrical_state', 'possible'),
         'pin_mapping': ('pin_compatibility', 'possible'),
         'firmware_consumer': ('firmware_compatibility', 'possible'),
         'artifact_source': ('manufacturing_output', 'possible')},
        ('electrical_state', 'possible'), 'possible',
        'document reference reached, or electrical partition evidence exhausted',
        'contract §2.1 rename vs partition; classify.py conservative rename handling'),
    _rule(
        'R7_display_only', ('display_only',), ('document_reference',),
        {'document_reference': ('documentation_only', 'certain')},
        ('documentation_only', 'certain'), 'certain',
        'display text can only reach documentation/drawing outputs; every '
        'electrical or delivery edge is an explicit display-only boundary',
        'contract §2.2 display_only; §4 no BOM/firmware invalidation'),
    _rule(
        'R8_board_outline', ('board_outline',),
        ('mechanical_constraint', 'enclosure_constraint', 'artifact_source'),
        {'mechanical_constraint': ('mechanical_fit', 'certain'),
         'enclosure_constraint': ('enclosure_interface', 'possible'),
         'artifact_source': ('manufacturing_output', 'certain')},
        ('mechanical_fit', 'certain'), 'certain',
        'no further mechanical/enclosure/manufacturing edge',
        'contract §2.2 board_outline; contract §6 C/G'),
    _rule(
        'R9_layer_stack', ('layer_stack', 'mechanical_pose'),
        ('signal_path', 'power_supply', 'artifact_source'),
        {'signal_path': ('signal_integrity', 'certain'),
         'power_supply': ('power_integrity', 'possible'),
         'artifact_source': ('manufacturing_output', 'certain')},
        ('signal_integrity', 'certain'), 'certain',
        'no further signal/power/manufacturing edge',
        'contract §2.2 layer/layers/stackup; stackup drives impedance and outputs'),
    _rule(
        'R10_delivery_config', ('delivery_config',),
        ('artifact_source', 'footprint_binding', 'test_reference',
         'verification_coverage'),
        {'artifact_source': ('bom_variant', 'certain'),
         'footprint_binding': ('assembly_fit', 'possible'),
         'test_reference': ('test_criterion_change', 'possible'),
         'verification_coverage': ('test_criterion_change', 'possible')},
        ('bom_variant', 'certain'), 'certain',
        'no further delivery/assembly/test edge',
        'contract §2.2 delivery_config; contract §6 C/H DNP and alternates'),
    _rule(
        'R11_firmware_contract', ('firmware_contract',),
        ('firmware_consumer', 'signal_path', 'pin_mapping', 'requirement_ref'),
        {'firmware_consumer': ('firmware_compatibility', 'certain'),
         'signal_path': ('signal_integrity', 'possible'),
         'pin_mapping': ('pin_compatibility', 'possible'),
         'requirement_ref': ('requirement_trace', 'possible')},
        ('firmware_compatibility', 'certain'), 'certain',
        'no further firmware/electrical/requirement edge',
        'contract §2.2 firmware_contract'),
    _rule(
        'R12_test_criterion', ('test_criterion',),
        ('test_reference', 'verification_coverage', 'requirement_ref'),
        {'test_reference': ('test_criterion_change', 'certain'),
         'verification_coverage': ('test_criterion_change', 'certain'),
         'requirement_ref': ('requirement_trace', 'possible')},
        ('test_criterion_change', 'certain'), 'certain',
        'only the referencing test/evidence and traced requirement; unrelated '
        'electrical evidence is never invalidated',
        'contract §2.2 test_criterion; contract §6 I'),
    _rule(
        'R13_parameter', ('parameter',),
        ('power_supply', 'signal_path', 'pin_mapping', 'test_reference',
         'verification_coverage'),
        {'power_supply': ('electrical_state', 'certain'),
         'signal_path': ('signal_integrity', 'certain'),
         'pin_mapping': ('pin_compatibility', 'possible'),
         'test_reference': ('test_criterion_change', 'possible'),
         'verification_coverage': ('test_criterion_change', 'possible')},
        ('electrical_state', 'certain'), 'certain',
        'no further electrical/test edge',
        'contract §2.2 parameter; contract §6 F'),
    _rule(
        'R14_requirement', ('requirement',),
        ('requirement_ref', 'verification_coverage', 'document_reference'),
        {'requirement_ref': ('requirement_trace', 'certain'),
         'verification_coverage': ('test_criterion_change', 'possible'),
         'document_reference': ('documentation_only', 'certain')},
        ('requirement_trace', 'certain'), 'certain',
        'no further trace/coverage/document edge',
        'contract §2.2 requirement'),
    _rule(
        'R15_connectivity', ('connectivity',),
        ('signal_path', 'power_supply', 'pin_mapping', 'firmware_consumer',
         'test_reference'),
        {'signal_path': ('signal_integrity', 'certain'),
         'power_supply': ('power_integrity', 'certain'),
         'pin_mapping': ('pin_compatibility', 'certain'),
         'firmware_consumer': ('firmware_compatibility', 'possible'),
         'test_reference': ('test_criterion_change', 'possible')},
        ('electrical_state', 'certain'), 'certain',
        'no further electrical/firmware/test edge',
        'contract §2.2 connectivity (net partition)'),
    _rule(
        'R16_document_metadata', ('document_metadata',),
        ('document_reference', 'artifact_source', 'requirement_ref'),
        {'document_reference': ('documentation_only', 'certain'),
         'artifact_source': ('manufacturing_output', 'possible'),
         'requirement_ref': ('requirement_trace', 'possible')},
        ('documentation_only', 'certain'), 'certain',
        'no further document/artifact/trace edge',
        'contract §2.2 document_metadata'),
    _rule(
        'R17_unknown_attribute', ('unknown_attribute',), (),
        {},
        ('unknown', 'unknown'), 'unknown',
        'attribute class is not mapped; nothing is inferred and the impact is '
        'reported as unknown, never as cosmetic',
        'contract §2.2 unknown_attribute'),
)

RULE_IDS = tuple(rule['rule_id'] for rule in RULES)

_RULE_BY_ID = {rule['rule_id']: rule for rule in RULES}
_RULE_BY_CHANGE_KIND = {}
for _entry in RULES:
    for _kind in _entry['change_kinds']:
        _RULE_BY_CHANGE_KIND.setdefault(_kind, _entry)

LAYER_PREFIXES = ('layer', 'layers.', 'stackup', 'stackup.')


def _validate_rule_table():
    """Fail fast at import time when a rule contradicts the package enums."""
    seen = set()
    for rule in RULES:
        rule_id = rule['rule_id']
        if rule_id in seen:
            raise RuntimeError('duplicate propagation rule %r' % (rule_id,))
        seen.add(rule_id)
        if rule['base_confidence'] not in CONFIDENCES:
            raise RuntimeError('rule %s: bad base confidence' % (rule_id,))
        for semantic in rule['semantics']:
            if semantic not in DEPENDENCY_SEMANTICS:
                raise RuntimeError('rule %s: unknown semantic %r'
                                   % (rule_id, semantic))
        for semantic, pair in rule['semantic_impacts'].items():
            if semantic not in rule['semantics']:
                raise RuntimeError('rule %s: semantic %r is not allowed'
                                   % (rule_id, semantic))
            impact, confidence = pair
            if impact not in IMPACT_KINDS:
                raise RuntimeError('rule %s: unknown impact %r'
                                   % (rule_id, impact))
            if confidence not in CONFIDENCES:
                raise RuntimeError('rule %s: bad confidence %r'
                                   % (rule_id, confidence))
        direct_impact, direct_confidence = rule['direct_impact']
        if direct_impact not in IMPACT_KINDS:
            raise RuntimeError('rule %s: unknown direct impact' % (rule_id,))
        if direct_confidence not in CONFIDENCES:
            raise RuntimeError('rule %s: bad direct confidence' % (rule_id,))
    for kind in CHANGE_KINDS:
        if kind not in _RULE_BY_CHANGE_KIND:
            raise RuntimeError('no propagation rule covers change kind %r'
                               % (kind,))
    if not STOP_REASONS_USED.issubset(set(STOP_REASONS)):
        raise RuntimeError('propagation uses a stop reason outside the contract')


_validate_rule_table()


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _rule_for(change):
    """Select the rule for one classified change."""
    kind = change.get('kind') or 'unknown_attribute'
    if kind == 'mechanical_pose':
        return _RULE_BY_ID['R9_layer_stack'] if _is_layer_change(change) \
            else _RULE_BY_ID['R5_mechanical_pose']
    return _RULE_BY_CHANGE_KIND.get(kind, _RULE_BY_ID['R17_unknown_attribute'])


def _is_layer_change(change):
    path = (change.get('attribute') or '').lower()
    if not path:
        return False
    if path in ('layer', 'layers', 'stackup'):
        return True
    return any(path.startswith(prefix) for prefix in LAYER_PREFIXES)


def _declared_changes(classification):
    """Accept the classify() report or a bare declared-change list."""
    if isinstance(classification, dict):
        declared = classification.get('declared') or []
    elif isinstance(classification, (list, tuple)):
        declared = list(classification)
    else:
        declared = []
    entries = [item for item in declared if isinstance(item, dict)]
    entries.sort(key=lambda item: (
        str(item.get('change_id') or ''),
        str(item.get('object') or ''),
        str(item.get('attribute') or ''),
    ))
    return entries


def _budget_limits(model, budget):
    """Resolve max_depth/max_paths, favouring an explicit override."""
    limits = {'max_depth': 8, 'max_paths': 500}
    source = getattr(model, 'budget', None)
    if isinstance(source, dict):
        for key in limits:
            limits[key] = _int_or(source.get(key), limits[key])
    if isinstance(budget, dict):
        for key in limits:
            if key in budget:
                limits[key] = _int_or(budget.get(key), limits[key])
    for key in limits:
        if limits[key] < 0:
            limits[key] = 0
    return limits


def _int_or(value, fallback):
    if value is None or isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _kind_of(model, graph, identity):
    record = model.object(identity) if model is not None else None
    if record is not None:
        return record['kind']
    return graph.nodes.get(identity, 'unknown')


def _partition_of(model, change):
    """Rename partition evidence: ``proven_same`` / ``changed`` / ``unknown``.

    ``classify`` already computes this; the fallback keeps the rule honest when
    a caller supplies a bare change record.
    """
    value = change.get('partition_evidence')
    if value in ('proven_same', 'changed', 'unknown'):
        return value
    identity = change.get('object')
    if model is None or identity is None:
        return 'unknown'
    for path in ('members', 'pins', 'membership', 'partition'):
        before = model.baseline_value(identity, path)
        after = model.candidate_value(identity, path)
        if before is MISSING and after is MISSING:
            continue
        if before is MISSING or after is MISSING:
            return 'unknown'
        return 'proven_same' if json_equal(before, after) else 'changed'
    return 'unknown'


def _special_conditions(model, rule, change):
    """Conditions that explain a conservative or unresolved inference."""
    rule_id = rule['rule_id']
    notes = []
    if rule_id == 'R6_identity_rename':
        partition = _partition_of(model, change)
        if partition == 'proven_same':
            notes.append('partition_evidence=proven_same: the partition did not '
                         'change, but a rename is not proof of no impact')
        elif partition == 'changed':
            notes.append('partition_evidence=changed: the connectivity partition '
                         'changed together with the rename')
        else:
            notes.append('partition_evidence=unknown: no partition evidence; a '
                         'rename is not proof of no impact and the electrical '
                         'consequence is undetermined')
    elif rule_id == 'R2_component_identity':
        for note in change.get('similarity_notes') or []:
            if not isinstance(note, dict):
                continue
            trap = note.get('trap')
            detail = note.get('detail')
            if trap and detail:
                notes.append('similarity_trap:%s: %s' % (trap, detail))
            elif detail:
                notes.append('similarity_note: %s' % detail)
    elif rule_id == 'R17_unknown_attribute':
        notes.append('unknown_attribute_change: the attribute class is not '
                     'mapped; its impact is unknown, not cosmetic')
    return notes


def _direct_impact(model, rule, change):
    """Return ``(impact_kind, confidence, undetermined)`` for the object itself."""
    rule_id = rule['rule_id']
    if rule_id == 'R17_unknown_attribute':
        return 'unknown', 'unknown', True
    if rule_id == 'R6_identity_rename':
        partition = _partition_of(model, change)
        if partition == 'changed':
            return 'electrical_state', 'certain', False
        if partition == 'proven_same':
            return 'electrical_state', 'possible', False
        return 'electrical_state', 'unknown', True
    impact, confidence = rule['direct_impact']
    return impact, confidence, False


def _impact_for(model, rule, change, semantic, target_kind):
    """Return ``(impact_kind, base_confidence, undetermined)`` for one step."""
    table = rule['semantic_impacts']
    if semantic not in table:
        return 'unknown', 'unknown', True
    impact, base = table[semantic]
    if semantic == 'artifact_source':
        impact = ARTIFACT_IMPACT_BY_KIND.get(target_kind, impact)
    undetermined = False
    if rule['rule_id'] == 'R6_identity_rename' and \
            semantic in RENAME_ELECTRICAL_SEMANTICS:
        partition = _partition_of(model, change)
        if partition == 'changed':
            base = 'certain'
        elif partition == 'proven_same':
            base = weakest([base, 'possible'])
        else:
            base = 'unknown'
            undetermined = True
    return impact, base, undetermined


def _successors(graph, node, rule):
    """Rule-compatible ``(edge, next_node)`` pairs leaving ``node``.

    Forward edges are followed.  ``bidirectional`` edges may also be walked
    against their declared direction; a declared forward edge is never reversed
    here (see ``graph.successor_edges``).
    """
    semantics = rule['semantics']
    if not semantics:
        return []
    result = []
    seen = set()
    for edge in graph.successor_edges(node, semantics):
        if edge.id in seen:
            continue
        seen.add(edge.id)
        if edge.source == node:
            target = edge.target
        elif edge.target == node:
            target = edge.source
        else:
            continue
        result.append((edge, target))
    return result


def _no_successor_reason(graph, rule, node):
    """Why the rule cannot continue from ``node`` (see STOP_REASONS)."""
    if rule['rule_id'] == 'R7_display_only':
        # A display-only change has no electrical consequence by definition;
        # this boundary is explicit and does not depend on edge completeness.
        return STOP_DISPLAY_ONLY_BOUNDARY
    if graph.nodes.get(node) in rule['terminal_kinds']:
        return STOP_LEAF_OBJECT
    if graph.out_edges(node):
        # Dependencies exist, but none of them carries a semantic this change
        # class may follow: semantic mismatch, not missing data.
        return STOP_SEMANTIC_MISMATCH
    boundary, _certainty = graph.boundary(node)
    if boundary == STOP_DECLARED_BOUNDARY:
        return STOP_DECLARED_BOUNDARY
    return STOP_MISSING_EDGE_DATA


def _make_path(model, *, target, target_kind, impact, change_ids, confidence,
               steps, rule_id, stop_reason, conditions, undetermined):
    out_steps = []
    evidence = []
    seen_edges = set()
    for step in steps:
        out_steps.append({
            'from': step['from'],
            'to': step['to'],
            'edge': step['edge'],
            'semantic': step['semantic'],
            'conditions': list(step['conditions']),
        })
        if step['edge'] in seen_edges:
            continue
        seen_edges.add(step['edge'])
        evidence.append({'edge_id': step['edge'],
                         'certainty': step['certainty']})
    merged_conditions = set(conditions)
    if impact in ELECTRICAL_IMPACTS and model is not None:
        for constraint in model.constraints_on(target):
            merged_conditions.add('constraint:%s' % constraint['id'])
    return {
        'path_id': None,  # assigned after deterministic sorting
        'target': target,
        'target_kind': target_kind,
        'impact': impact,
        'change_ids': sorted(set(change_ids)),
        'confidence': confidence,
        'steps': out_steps,
        'trigger_rule': rule_id,
        'stop_reason': stop_reason,
        'conditions': sorted(merged_conditions),
        'evidence': evidence,
        'undetermined': bool(undetermined),
    }


def _dedupe_key(record):
    """Identity of one explanation: target + impact + rule + exact route."""
    return (
        record['target'],
        record['impact'],
        record['trigger_rule'],
        tuple((step['from'], step['to'], step['edge'])
              for step in record['steps']),
    )


def _merge_path(existing, incoming):
    """Merge two identical explanations without dropping any origin."""
    existing['change_ids'] = sorted(set(existing['change_ids']) |
                                    set(incoming['change_ids']))
    existing['confidence'] = weakest([existing['confidence'],
                                      incoming['confidence']])
    existing['conditions'] = sorted(set(existing['conditions']) |
                                    set(incoming['conditions']))
    existing['undetermined'] = bool(existing['undetermined'] or
                                    incoming['undetermined'])
    merged = {}
    for item in existing['evidence'] + incoming['evidence']:
        edge_id = item['edge_id']
        current = merged.get(edge_id)
        if current is None or \
                _CERTAINTY_STRENGTH[item['certainty']] < \
                _CERTAINTY_STRENGTH[current]:
            merged[edge_id] = item['certainty']
    order = [step['edge'] for step in existing['steps']]
    existing['evidence'] = [
        {'edge_id': edge_id, 'certainty': merged[edge_id]}
        for edge_id in order if edge_id in merged]
    if existing['stop_reason'] == STOP_DEDUPLICATED and \
            incoming['stop_reason'] != STOP_DEDUPLICATED:
        existing['stop_reason'] = incoming['stop_reason']


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def propagate(model, graph, classification, *, budget=None):
    """Propagate classified changes through semantically compatible edges.

    ``classification`` is the report from
    :func:`change_impact.classify.compare_declared_to_observed` (its
    ``declared`` list is used) or an equivalent list of classified changes.
    """
    limits = _budget_limits(model, budget)
    max_depth = limits['max_depth']
    max_paths = limits['max_paths']

    paths = []
    path_index = {}
    unknown = {}
    frontier = {}
    state = {'truncated': False}
    rules_applied = set()

    cycles = [list(component) for component in graph.cycles]

    def add_unknown(code, object_id, reason, change_ids):
        key = (code, object_id)
        entry = unknown.get(key)
        if entry is None:
            unknown[key] = {
                'code': code,
                'object': object_id,
                'reason': reason,
                'change_ids': set(change_ids),
            }
        else:
            entry['change_ids'].update(change_ids)

    def add_frontier(identity, change_ids):
        frontier.setdefault(identity, set()).update(change_ids)

    def add_path(record):
        key = _dedupe_key(record)
        existing = path_index.get(key)
        if existing is not None:
            _merge_path(existing, record)
            return existing
        if len(paths) >= max_paths:
            state['truncated'] = True
            add_frontier(record['target'], record['change_ids'])
            return None
        path_index[key] = record
        paths.append(record)
        return record

    for change in _declared_changes(classification):
        change_id = str(change.get('change_id') or '')
        identity = change.get('object')
        rule = _rule_for(change)
        rules_applied.add(rule['rule_id'])

        if not change_id:
            add_unknown('invalid_change_record', identity or '',
                        'classified change has no change_id and cannot be cited',
                        [])
            continue
        if identity is None or identity not in graph.nodes:
            add_unknown('unknown_change_object', identity or '',
                        'the change names an object that is not in the graph; '
                        'its impact cannot be propagated', [change_id])
            continue

        direct_impact, direct_confidence, direct_undetermined = \
            _direct_impact(model, rule, change)
        base_conditions = set(change.get('conditions') or [])
        base_conditions.update(_special_conditions(model, rule, change))

        partition_unknown = rule['rule_id'] == 'R6_identity_rename' and \
            _partition_of(model, change) == 'unknown'
        if partition_unknown:
            add_unknown(
                'rename_partition_unknown', identity,
                'the rename has no declared partition evidence; the electrical '
                'impact is undetermined and a rename is not proof of no impact '
                '(not traversed does not mean unaffected)', [change_id])
            direct_undetermined = True

        if rule['rule_id'] == 'R17_unknown_attribute':
            add_unknown(
                'unknown_attribute_change', identity,
                'the changed attribute is not mapped to any change class; its '
                'impact is unknown, not cosmetic', [change_id])

        visited = {(identity, direct_impact)}
        queue = deque()
        # ``chain_confidence`` starts at certain and is weakened step by step;
        # the direct record keeps the rule's own direct confidence so a
        # conservative direct inference (e.g. component identity) does not
        # artificially weaken strictly stronger downstream rules.
        queue.append((
            identity, (), 0, 'certain', direct_impact,
            tuple(sorted(base_conditions)), direct_undetermined))

        while queue:
            if len(paths) >= max_paths:
                state['truncated'] = True
                for queued in queue:
                    add_frontier(queued[0], [change_id])
                queue.clear()
                break

            (node, steps, depth, chain_confidence, impact,
             conditions, undetermined) = queue.popleft()
            target_kind = _kind_of(model, graph, node)
            record_confidence = direct_confidence if not steps \
                else chain_confidence
            successors = _successors(graph, node, rule)

            if not successors:
                stop_reason = _no_successor_reason(graph, rule, node)
                if stop_reason == STOP_MISSING_EDGE_DATA:
                    add_unknown(
                        'missing_edge_data', node,
                        'no declared dependency lets this change class continue; '
                        'missing edge data is not proof of no impact '
                        '(not traversed does not mean unaffected)', [change_id])
                    if steps:
                        # The propagated consequence at this node cannot be
                        # bounded: mark it unknown rather than certain.
                        record_confidence = 'unknown'
                add_path(_make_path(
                    model, target=node, target_kind=target_kind,
                    impact=impact, change_ids=[change_id],
                    confidence=record_confidence, steps=steps,
                    rule_id=rule['rule_id'], stop_reason=stop_reason,
                    conditions=conditions,
                    undetermined=undetermined or
                    stop_reason == STOP_MISSING_EDGE_DATA))
                continue

            if depth >= max_depth:
                state['truncated'] = True
                add_frontier(node, [change_id])
                add_path(_make_path(
                    model, target=node, target_kind=target_kind,
                    impact=impact, change_ids=[change_id],
                    confidence=record_confidence, steps=steps,
                    rule_id=rule['rule_id'], stop_reason=STOP_DEPTH_BUDGET,
                    conditions=conditions, undetermined=undetermined))
                continue

            expanded = False
            blocked = []
            for edge, successor in successors:
                successor_kind = _kind_of(model, graph, successor)
                step_impact, step_base, step_undetermined = _impact_for(
                    model, rule, change, edge.semantic, successor_kind)
                step_confidence = weakest(
                    [chain_confidence, edge.confidence(step_base)])
                step_conditions = tuple(sorted(
                    set(conditions) | set(edge.conditions)))
                step = {
                    'from': node,
                    'to': successor,
                    'edge': edge.id,
                    'semantic': edge.semantic,
                    'conditions': tuple(sorted(edge.conditions)),
                    'certainty': edge.certainty,
                }
                next_steps = steps + (step,)
                next_undetermined = bool(
                    undetermined or step_undetermined or
                    step_confidence == 'unknown')

                if (successor, step_impact) in visited:
                    # Cycle only when the next node is already an ancestor of
                    # the current route; a parallel route to an already visited
                    # node (diamond) is remembered as already_visited.
                    route_nodes = {node}
                    route_nodes.update(item['from'] for item in steps)
                    route_nodes.update(item['to'] for item in steps)
                    if successor in route_nodes:
                        stop_reason = STOP_CYCLE_DETECTED
                    else:
                        stop_reason = STOP_ALREADY_VISITED
                    blocked.append(stop_reason)
                    add_path(_make_path(
                        model, target=successor,
                        target_kind=successor_kind,
                        impact=step_impact, change_ids=[change_id],
                        confidence=step_confidence, steps=next_steps,
                        rule_id=rule['rule_id'], stop_reason=stop_reason,
                        conditions=step_conditions,
                        undetermined=next_undetermined))
                    continue

                visited.add((successor, step_impact))
                queue.append((
                    successor, next_steps, depth + 1, step_confidence,
                    step_impact, step_conditions, next_undetermined))
                expanded = True

            if rule['rule_id'] == 'R7_display_only':
                stop_reason = STOP_DISPLAY_ONLY_BOUNDARY
            elif expanded:
                # The object is affected but only as a waypoint of a longer
                # explanation: its record is a prefix and must not be read as
                # the end of the chain.
                stop_reason = STOP_DEDUPLICATED
            elif STOP_CYCLE_DETECTED in blocked:
                stop_reason = STOP_CYCLE_DETECTED
            else:
                stop_reason = STOP_ALREADY_VISITED
            add_path(_make_path(
                model, target=node, target_kind=target_kind, impact=impact,
                change_ids=[change_id], confidence=record_confidence,
                steps=steps,
                rule_id=rule['rule_id'], stop_reason=stop_reason,
                conditions=conditions, undetermined=undetermined))

    # -- deterministic numbering and ordering ------------------------------
    ordered = sorted(
        paths,
        key=lambda item: (
            item['target'],
            item['impact'],
            item['trigger_rule'],
            tuple((step['from'], step['to'], step['edge'])
                  for step in item['steps']),
            tuple(item['change_ids']),
        ))
    for index, record in enumerate(ordered, 1):
        record['path_id'] = 'path:%04d' % index
    impact_paths = sorted(ordered, key=lambda item: (
        item['target'], item['impact'], item['path_id']))

    # -- impacted object aggregation ---------------------------------------
    grouped = {}
    for record in impact_paths:
        target = record['target']
        entry = grouped.get(target)
        if entry is None:
            entry = {
                'object': target,
                'kind': _kind_of(model, graph, target),
                'impacts': set(),
                'confidence': 'certain',
                'change_ids': set(),
                'path_ids': [],
                'direct': False,
            }
            grouped[target] = entry
        entry['impacts'].add(record['impact'])
        entry['confidence'] = weakest([entry['confidence'],
                                       record['confidence']])
        entry['change_ids'].update(record['change_ids'])
        entry['path_ids'].append(record['path_id'])
        if not record['steps']:
            entry['direct'] = True

    impacted_objects = []
    for target in grouped:
        entry = grouped[target]
        impacted_objects.append({
            'object': entry['object'],
            'kind': entry['kind'],
            'impacts': sorted(entry['impacts']),
            'confidence': entry['confidence'],
            'change_ids': sorted(entry['change_ids']),
            'path_ids': sorted(set(entry['path_ids'])),
            'direct': entry['direct'],
        })
    impacted_objects.sort(key=lambda item: (item['kind'], item['object']))

    # -- unknown entries ---------------------------------------------------
    unknown_entries = []
    for (code, object_id) in sorted(unknown,
                                    key=lambda key: (key[0], key[1] or '')):
        entry = unknown[(code, object_id)]
        unknown_entries.append({
            'code': entry['code'],
            'object': entry['object'],
            'reason': entry['reason'],
            'change_ids': sorted(entry['change_ids']),
        })
    if state['truncated']:
        existing_budget = {entry['object'] for entry in unknown_entries
                           if entry['code'] == 'budget_exhausted'}
        for object_id in sorted(frontier):
            if object_id in existing_budget:
                continue
            unknown_entries.append({
                'code': 'budget_exhausted',
                'object': object_id,
                'reason': 'the traversal budget stopped before this object was '
                          'expanded; not traversed does not mean unaffected',
                'change_ids': sorted(frontier[object_id]),
            })
    unknown_entries.sort(key=lambda item: (item['code'], item['object'] or ''))

    used_paths = len(impact_paths)
    max_depth_used = 0
    for record in impact_paths:
        if len(record['steps']) > max_depth_used:
            max_depth_used = len(record['steps'])

    return {
        'impact_paths': impact_paths,
        'impacted_objects': impacted_objects,
        'unknown': unknown_entries,
        'truncated': bool(state['truncated']),
        'budget': {
            'max_depth': max_depth,
            'max_paths': max_paths,
            'used_paths': used_paths,
            'max_depth_used': max_depth_used,
            'frontier': sorted(frontier),
        },
        'cycles': cycles,
        'rules_applied': sorted(rules_applied),
    }
