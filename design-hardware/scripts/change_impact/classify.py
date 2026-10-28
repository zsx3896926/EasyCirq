"""J1: change intake, classification and declaration-vs-reality accounting.

Two separate jobs live here:

* **classification** turns each explicit change into a semantic class.  The
  mapping is a declared table, not a heuristic: an attribute path that is not in
  the table becomes ``unknown_attribute`` and is reported, never silently
  treated as a cosmetic edit.
* **accounting** compares the declared change list with an independently
  observed diff.  A change that appears only in the observation is
  ``observed_not_declared`` (an unexpected, unauthorised difference); one that
  is declared but not observed is a declaration mismatch.  Neither is folded
  into "well, it changed already, so it must be allowed".

Rename handling is deliberately conservative.  A net rename with a *stable
identity* and a proven-identical pin partition is still not a proof of "no
electrical impact": it only means the partition did not change, which the
propagation rules must state explicitly.
"""
from __future__ import annotations

from . import CHANGE_KINDS
from . import canonical as canon
from .errors import InputInvalid
from .model import MISSING, classify_attribute, json_equal, lookup

RENAME_PATHS = ('name', 'net_name', 'designator', 'display_name', 'instance_name')
PARTITION_PATHS = ('members', 'pins', 'membership', 'partition')

# Attribute classes whose changes must keep electrical equivalence unproven even
# when a coincidental similarity (same footprint, same pin count) exists.
SIMILARITY_TRAPS = {
    'footprint_same': 'a matching footprint does not prove electrical equivalence',
    'pin_count_same': 'a matching pin count does not prove pin-function equivalence',
    'same_designator': 'a reused designator does not prove the instance is unchanged',
}


def _rename_subtype(object_kind, path):
    if path == 'designator':
        return 'designator_rename'
    if object_kind == 'net':
        return 'net_rename'
    if object_kind == 'component_instance':
        return 'instance_rename'
    return 'object_rename'


def _partition_evidence(model, change):
    """For a rename, report whether the connectivity partition is provably equal.

    ``proven_same`` requires a declared partition attribute on the object that
    is identical on both sides.  Absence of that evidence is ``unknown``; it is
    never upgraded to "unchanged".
    """
    identity = change['object']
    for path in PARTITION_PATHS:
        baseline = model.baseline_value(identity, path)
        candidate = model.candidate_value(identity, path)
        if baseline is MISSING and candidate is MISSING:
            continue
        if baseline is not MISSING and candidate is not MISSING:
            return 'proven_same' if json_equal(baseline, candidate) else 'changed', path
        return 'unknown', path
    return 'unknown', None


def _similarity_notes(model, change):
    """Record coincidental similarities so they cannot be read as equivalence."""
    notes = []
    identity = change['object']
    record = model.object(identity)
    if change['kind'] != 'component_identity':
        return notes
    footprint_before = model.baseline_value(identity, 'footprint')
    footprint_after = model.candidate_value(identity, 'footprint')
    if footprint_before is not MISSING and footprint_after is not MISSING and \
            json_equal(footprint_before, footprint_after):
        notes.append({'trap': 'footprint_same',
                      'detail': SIMILARITY_TRAPS['footprint_same']})
    uuid_before = model.baseline_value(identity, 'instance_uuid')
    uuid_after = model.candidate_value(identity, 'instance_uuid')
    if uuid_before is not MISSING and uuid_after is not MISSING and \
            not json_equal(uuid_before, uuid_after):
        notes.append({'trap': 'same_designator',
                      'detail': ('the instance UUID changed even though the '
                                 'designator may be unchanged; this is an '
                                 'identity change')})
    if record.get('display_name'):
        notes.append({'trap': 'display_name',
                      'detail': 'the display name is not an identity'})
    return notes


def _classify(model):
    classified = []
    for change in model.changes:
        identity = change['object']
        record = model.object(identity)
        kind = change['kind']
        path = change['attribute']
        subtype = change.get('class_label')
        if path in RENAME_PATHS:
            # A rename is its own class: neither display-only nor connectivity.
            kind = 'identity_rename'
            subtype = _rename_subtype(record['kind'], path)
        elif kind == 'unknown_attribute':
            subtype = 'unmapped_attribute'
        elif kind == 'connectivity':
            subtype = 'net_partition_change'
        elif kind == 'mechanical_pose':
            subtype = 'layer_or_pose'
        elif kind == 'delivery_config':
            subtype = 'delivery_config'
        if kind not in CHANGE_KINDS:  # defensive: model.py already checks
            raise InputInvalid(f'change {change["id"]}: unknown class {kind!r}',
                               code='unknown_change_kind')
        entry = {
            'change_id': change['id'],
            'kind': kind,
            'subtype': subtype,
            'object': identity,
            'object_kind': record['kind'],
            'attribute': path,
            'change_type': change['change_type'],
            'before': change['before'],
            'after': change['after'],
            'authorized': change['authorized'],
            'authorized_scope': change['authorized_scope'],
            'source': change['source'],
            'conditions': list(change['conditions']),
            'note': change['note'],
            'simulated': bool(record['simulated'] or model.simulated),
        }
        if kind == 'identity_rename':
            partition, partition_path = _partition_evidence(model, change)
            entry['partition_evidence'] = partition
            entry['partition_attribute'] = partition_path
            entry['electrical_equivalence_proven'] = partition == 'proven_same'
        if change['change_type'] in ('add', 'remove'):
            entry['object_added'] = change['change_type'] == 'add'
            entry['object_removed'] = change['change_type'] == 'remove'
        similarity = _similarity_notes(model, change)
        if similarity:
            entry['similarity_notes'] = similarity
        if kind == 'unknown_attribute':
            entry['unknown_boundary'] = ('attribute class is not mapped; its '
                                         'impact is unknown, not cosmetic')
        classified.append(entry)
    classified.sort(key=lambda item: (item['object'], item['attribute'] or '',
                                      item['change_id']))
    return classified


def _observed_key(entry):
    return (entry['object'], entry['attribute'],
            canon.canonical_json(entry['before']),
            canon.canonical_json(entry['after']))


def _change_key(change):
    return (change['object'], change['attribute'],
            canon.canonical_json(change['before']),
            canon.canonical_json(change['after']))


def _match_declared(change, observed):
    """Match a declared change to an observed diff entry.

    Exact (object, attribute, before, after) is preferred.  When an observation
    reports a whole-object replacement (attribute ``None``) the declared
    per-attribute changes are matched by object and value instead, which is how
    a legitimate normalised diff can still confirm a declaration.
    """
    key = _change_key(change)
    for entry in observed:
        if _observed_key(entry) == key:
            return entry
    for entry in observed:
        if entry['object'] != change['object']:
            continue
        if entry['attribute'] is not None:
            continue
        if json_equal(entry['after'], change['after']):
            return entry
    return None


def compare_declared_to_observed(model):
    """J1 accounting: declared changes versus the independently observed diff.

    ``complete`` is only true when the caller supplied an observed diff.  A
    missing observation makes the comparison limited, never "nothing else
    changed".
    """
    observed = model.observed_diff
    declared = _classify(model)
    matched_observed = set()
    declared_not_observed = []
    if observed:
        # A missing observation is *not* evidence that nothing else changed:
        # without an observation the declaration is simply not cross-checked.
        for change in model.changes:
            match = _match_declared(change, observed)
            if match is None:
                declared_not_observed.append({
                    'change_id': change['id'],
                    'object': change['object'],
                    'attribute': change['attribute'],
                    'reason': 'declared change was not present in the observed diff',
                })
            else:
                matched_observed.add(id(match))
    observed_not_declared = []
    for entry in observed:
        if id(entry) in matched_observed:
            continue
        observed_not_declared.append({
            'object': entry['object'],
            'attribute': entry['attribute'],
            'before': entry['before'],
            'after': entry['after'],
            'reason': 'observed difference was not declared for this ECO',
            'authorized': False,
        })
    unauthorized = [item for item in declared if not item['authorized']]
    return {
        'declared': declared,
        'declared_not_observed': declared_not_observed,
        'observed_not_declared': observed_not_declared,
        'unauthorized_declared': [
            {'change_id': item['change_id'], 'object': item['object'],
             'attribute': item['attribute'],
             'reason': 'change is declared but not marked authorized'}
            for item in unauthorized],
        'observation_available': bool(observed),
        'comparison_complete': bool(observed) and
        model.baseline['complete'] and model.candidate['complete'] and
        model.model_scope['dependencies_complete'],
        'note': ('no independent observation was supplied; the declared change '
                 'list was not cross-checked against measured differences'
                 if not observed else
                 'declared and observed differences were compared'),
    }


def true_difference_present(model):
    """True when the declared model demonstrably differs between the two sides."""
    if model.changes:
        return True
    if model.observed_diff:
        return True
    return model.baseline['content_hash'] != model.candidate['content_hash']


def rename_map_detected(model):
    """List ``(old, new)`` pairs for explicitly renamed objects (id stable)."""
    pairs = []
    for entry in _classify(model):
        if entry['kind'] != 'identity_rename':
            continue
        if entry.get('subtype') != 'net_rename' or entry['object_kind'] != 'net':
            continue
        pairs.append({'object': entry['object'], 'before': entry['before'],
                      'after': entry['after'],
                      'partition_evidence': entry.get('partition_evidence')})
    return pairs
