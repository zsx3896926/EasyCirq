"""Tests for J3 prior-evidence invalidation and reuse assessment.

The implementation package is loaded through the ``tests/change_impact``
bootstrap alias (``from . import load``) so ``python -m unittest discover``
works without a name clash.  Most cases build a small but schema-valid model and
run the real J2 propagation (``classify`` -> ``propagate``) so the evidence
assessment consumes the documented ``impacts`` shape; a few cases hand-build the
documented ``impacted_objects``/``unknown`` shape to exercise boundary rules
that are hard to produce through the rule table.
"""
from __future__ import annotations

import unittest

from . import load

model_module = load('model')
classify_module = load('classify')
graph_module = load('graph')
propagate_module = load('propagate')
canonical_module = load('canonical')
evidence_module = load('evidence')

HASH_A = 'sha256:' + 'a' * 64   # baseline snapshot
HASH_B = 'sha256:' + 'b' * 64   # candidate snapshot
OLD_REVISION = 'r1'
NEW_REVISION = 'r2'
ZERO_HASH = 'sha256:' + '0' * 64
CAPTURED_AT = '2026-01-01T00:00:00Z'
LATER = '2026-02-01T00:00:00Z'
EARLIER = '2025-12-01T00:00:00Z'


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def snapshot(revision, content_hash, *, complete=False):
    return {
        'project': 'probe',
        'document': 'main',
        'revision': revision,
        'content_hash': content_hash,
        'source_type': 'normalized_model',
        'snapshot_scope': ['component_instance', 'net', 'document'],
        'complete': complete,
    }


def obj(identity, kind, attributes=None, baseline_attributes=None):
    record = {'id': identity, 'kind': kind,
              'attributes': dict(attributes or {})}
    if baseline_attributes is not None:
        record['baseline_attributes'] = baseline_attributes
    return record


def dep(identity, source, target, semantic, *, direction='forward',
        certainty='declared'):
    return {
        'id': identity,
        'from': source,
        'to': target,
        'semantic': semantic,
        'direction': direction,
        'certainty': certainty,
        'conditions': [],
    }


def chg(identity, target, attribute, before, after, *, kind=None,
        change_type='modify'):
    record = {
        'id': identity,
        'change_type': change_type,
        'object': target,
        'attribute': attribute,
        'before': before,
        'after': after,
        'authorized': True,
    }
    if kind is not None:
        record['kind'] = kind
    return record


def check(identity='chk:voltage', kind='offline', covers=None, *,
          title=None, cost=0.5, mandatory=False, approval=False):
    return {
        'id': identity,
        'title': title or identity,
        'kind': kind,
        'cost': cost,
        'mandatory': mandatory,
        'approval': approval,
        'module': 'electrical-review',
        'covers': list(covers or [{'object': 'net:+5V',
                                   'impact': 'power_integrity'}]),
    }


def ev(identity='ev:1', check_id='chk:voltage', *,
       revision=OLD_REVISION, content_hash=HASH_A, coverage=None,
       scope_complete=True, simulated=False, captured_at=CAPTURED_AT,
       valid_until=None, dependency_fingerprint=None, host=None,
       result='pass', tool_version='0.9.0', conditions=None):
    return {
        'id': identity,
        'check': check_id,
        'result': result,
        'tool_version': tool_version,
        'revision': revision,
        'content_hash': content_hash,
        'coverage': dict(coverage) if coverage is not None else None,
        'conditions': list(conditions or []),
        'simulated': simulated,
        'captured_at': captured_at,
        'valid_until': valid_until,
        'host': host,
        'dependency_fingerprint': dependency_fingerprint,
        'scope_complete': scope_complete,
    }


def scope_for(objects, *, complete=False):
    return {
        'declared_kinds': sorted({item['kind'] for item in objects}),
        'unknown_objects': [],
        'dependencies_complete': complete,
        'notes': 'test model',
    }


def build_model(objects, dependencies=None, changes=None, *, checks=None,
                evidence=None, analysis_time=None, constraints=None):
    data = {
        'schema': 'hds-change-impact-input/v1',
        'project': {'name': 'probe'},
        'baseline': snapshot(OLD_REVISION, HASH_A),
        'candidate': snapshot(NEW_REVISION, HASH_B),
        'objects': list(objects),
        'dependencies': list(dependencies or []),
        'changes': list(changes or []),
        'constraints': list(constraints or []),
        'verification_catalog': list(checks or []),
        'model_scope': scope_for(objects),
    }
    if evidence is not None:
        data['prior_evidence'] = list(evidence)
    if analysis_time is not None:
        data['analysis_time'] = analysis_time
    return model_module.validate_model(data)


def default_coverage(objects=('net:+5V',), attributes=('power.voltage',),
                     impacts=()):
    return {
        'objects': list(objects),
        'attributes': list(attributes),
        'impacts': list(impacts),
    }


def run_assessment(model, *, analysis_time=None, impacts=None):
    graph = graph_module.Graph(model)
    if impacts is None:
        classification = classify_module.compare_declared_to_observed(model)
        impacts = propagate_module.propagate(model, graph, classification)
    return evidence_module.assess(model, graph, impacts,
                                  analysis_time=analysis_time)


def electrical_model(evidence, *, checks=None, extra_objects=None,
                     changes=None, analysis_time=None):
    """A net voltage change that propagates ``power_integrity`` to ``cmp:U2``."""
    objects = [
        obj('net:+5V', 'net',
            {'power': {'voltage': 3.3}},
            {'power': {'voltage': 5.0}}),
        obj('cmp:U2', 'component_instance', {'mpn': 'LDO1'}),
    ] + list(extra_objects or [])
    return build_model(
        objects,
        dependencies=[dep('dep:1', 'net:+5V', 'cmp:U2', 'power_supply')],
        changes=changes or [chg('chg:1', 'net:+5V', 'power.voltage', 5.0, 3.3)],
        checks=checks or [check()],
        evidence=evidence,
        analysis_time=analysis_time,
    )


def assessment_for(result, evidence_id):
    for entry in result['assessments']:
        if entry['evidence_id'] == evidence_id:
            return entry
    raise AssertionError('no assessment for %r' % (evidence_id,))


def status_of(result, evidence_id):
    return assessment_for(result, evidence_id)['status']


def reason_codes(assessment):
    return [item['code'] for item in assessment['reasons']]


def empty_impacts(*, unknown=None, impacted=None, truncated=False):
    return {
        'impact_paths': [],
        'impacted_objects': list(impacted or []),
        'unknown': list(unknown or []),
        'truncated': truncated,
    }


# ---------------------------------------------------------------------------
# 1. immutable binding: same candidate revision + content hash
# ---------------------------------------------------------------------------

class ImmutableBindingTest(unittest.TestCase):
    def test_binding_match_is_reusable_bound(self):
        evidence = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                      coverage=default_coverage(),
                      scope_complete=True,
                      captured_at=CAPTURED_AT,
                      host={'id': 'pc-1', 'receipt': 'old-receipt'})
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_REUSABLE_BOUND)
        self.assertIn('same_revision_and_content_hash', reason_codes(entry))
        self.assertEqual(entry['valid_for'], ['offline'])
        self.assertEqual(entry['reuse']['basis'],
                         'same_revision_and_content_hash')
        self.assertNotIn('computed_fingerprint', entry['reuse'])
        self.assertTrue(entry['reuse']['limits'])
        self.assertEqual(entry['original']['captured_at'], CAPTURED_AT)
        self.assertEqual(entry['reuse']['preserved_capture']['host'],
                         {'id': 'pc-1', 'receipt': 'old-receipt'})

    def test_binding_match_requires_scope_complete(self):
        evidence = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                      coverage=default_coverage(), scope_complete=False)
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('evidence_incomplete_scope', reason_codes(entry))
        self.assertIsNone(entry['reuse'])

    def test_host_evidence_binding_match_is_valid_for_host(self):
        checks = [check('chk:drc', 'host',
                        [{'object': 'cmp:U2', 'impact': 'power_integrity'}])]
        evidence = ev('ev:1', 'chk:drc', revision=NEW_REVISION,
                      content_hash=HASH_B, coverage=default_coverage())
        model = electrical_model([evidence], checks=checks)
        result = run_assessment(model)
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_REUSABLE_BOUND)
        self.assertEqual(entry['valid_for'], ['host'])


# ---------------------------------------------------------------------------
# 2. missing binding fields never default to valid
# ---------------------------------------------------------------------------

class MissingBindingTest(unittest.TestCase):
    def _status(self, **overrides):
        evidence = ev('ev:1', coverage=default_coverage(), **overrides)
        return run_assessment(electrical_model([evidence]))

    def test_missing_revision_is_unknown(self):
        result = self._status(revision=None)
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('evidence_missing_binding', reason_codes(entry))
        self.assertIn('revision', entry['reasons'][0]['detail'])
        self.assertEqual(result['unknown'][0]['evidence_id'], 'ev:1')

    def test_missing_content_hash_is_unknown(self):
        entry = assessment_for(self._status(content_hash=None), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('content_hash', entry['reasons'][0]['detail'])

    def test_missing_tool_version_is_unknown(self):
        entry = assessment_for(self._status(tool_version=None), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('tool_version', entry['reasons'][0]['detail'])

    def test_missing_result_is_unknown(self):
        evidence = ev('ev:1', coverage=default_coverage())
        model = electrical_model([evidence])
        model.evidence[0].pop('result')
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('result', entry['reasons'][0]['detail'])

    def test_missing_coverage_is_unknown(self):
        evidence = ev('ev:1', coverage=None)
        entry = assessment_for(
            run_assessment(electrical_model([evidence])), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('evidence_missing_coverage', reason_codes(entry))
        self.assertIsNone(entry['coverage'])

    def test_empty_coverage_without_fingerprint_is_unknown(self):
        evidence = ev('ev:1',
                      coverage={'objects': [], 'attributes': [], 'impacts': []})
        entry = assessment_for(
            run_assessment(electrical_model([evidence])), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('evidence_missing_coverage', reason_codes(entry))


# ---------------------------------------------------------------------------
# 3. expiry
# ---------------------------------------------------------------------------

class ExpiryTest(unittest.TestCase):
    def test_expired_evidence_is_invalidated(self):
        evidence = ev('ev:1', coverage=default_coverage(),
                      valid_until=EARLIER)
        model = electrical_model([evidence], analysis_time=LATER)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_INVALIDATED)
        self.assertIn('expired', reason_codes(entry))
        self.assertIsNone(entry['reuse'])

    def test_valid_until_in_future_does_not_expire(self):
        evidence = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                      coverage=default_coverage(), valid_until=LATER)
        model = electrical_model([evidence], analysis_time=CAPTURED_AT)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_REUSABLE_BOUND)

    def test_unparseable_valid_until_is_unknown(self):
        evidence = ev('ev:1', coverage=default_coverage(),
                      valid_until='not-a-timestamp')
        model = electrical_model([evidence], analysis_time=LATER)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('unparseable_expiry', reason_codes(entry))

    def test_expiry_uses_declared_analysis_time(self):
        evidence = ev('ev:1', coverage=default_coverage(),
                      valid_until=EARLIER)
        model = electrical_model([evidence], analysis_time=LATER)
        result = run_assessment(model)
        self.assertEqual(status_of(result, 'ev:1'),
                         evidence_module.EVIDENCE_INVALIDATED)

    def test_explicit_analysis_time_overrides_model(self):
        evidence = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                      coverage=default_coverage(),
                      valid_until='2026-01-15T00:00:00Z')
        model = electrical_model([evidence], analysis_time=LATER)
        # The declared time would expire the evidence; the explicit argument
        # predates valid_until, so it must not be expired.
        result = run_assessment(model, analysis_time=CAPTURED_AT)
        self.assertEqual(status_of(result, 'ev:1'),
                         evidence_module.EVIDENCE_REUSABLE_BOUND)
        self.assertEqual(
            status_of(run_assessment(model), 'ev:1'),
            evidence_module.EVIDENCE_INVALIDATED)


# ---------------------------------------------------------------------------
# 4. simulated evidence boundary
# ---------------------------------------------------------------------------

class SimulatedEvidenceTest(unittest.TestCase):
    def test_simulated_offline_binding_stays_offline_only(self):
        evidence = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                      coverage=default_coverage(), simulated=True)
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_REUSABLE_BOUND)
        self.assertEqual(entry['valid_for'], ['offline'])
        self.assertNotIn('host', entry['valid_for'])
        self.assertNotIn('manual', entry['valid_for'])
        self.assertIn(evidence_module.SIMULATED_LIMIT,
                      entry['reuse']['limits'])
        self.assertTrue(result['simulated_only'])

    def test_simulated_cannot_satisfy_host_check(self):
        checks = [check('chk:drc', 'host',
                        [{'object': 'cmp:U2', 'impact': 'power_integrity'}])]
        evidence = ev('ev:1', 'chk:drc', revision=NEW_REVISION,
                      content_hash=HASH_B, coverage=default_coverage(),
                      simulated=True)
        result = run_assessment(electrical_model([evidence], checks=checks))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_INVALIDATED)
        self.assertIn('simulated_cannot_satisfy_host_check',
                      reason_codes(entry))
        self.assertEqual(entry['valid_for'], [])
        self.assertIsNone(entry['reuse'])

    def test_simulated_cannot_satisfy_manual_check(self):
        checks = [check('chk:probe', 'manual',
                        [{'object': 'cmp:U2', 'impact': 'power_integrity'}])]
        evidence = ev('ev:1', 'chk:probe', revision=NEW_REVISION,
                      content_hash=HASH_B, coverage=default_coverage(),
                      simulated=True)
        result = run_assessment(electrical_model([evidence], checks=checks))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_INVALIDATED)
        self.assertIn('simulated_cannot_satisfy_host_check',
                      reason_codes(entry))

    def test_simulated_fingerprint_reuse_is_offline_only(self):
        coverage = {'objects': ['cmp:U2'], 'attributes': ['mpn'],
                    'impacts': ['electrical_state']}
        evidence = ev('ev:1', coverage=coverage, simulated=True)
        model = electrical_model([evidence])
        model.evidence[0]['dependency_fingerprint'] = \
            evidence_module.covered_attribute_fingerprint(model, coverage)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_REUSABLE_ASSESSED)
        self.assertEqual(entry['valid_for'], ['offline'])
        self.assertIn(evidence_module.SIMULATED_LIMIT,
                      entry['reuse']['limits'])
        self.assertTrue(entry['reuse']['preserved_capture']['simulated'])


# ---------------------------------------------------------------------------
# 5. coverage hit -> invalidated
# ---------------------------------------------------------------------------

class CoverageHitTest(unittest.TestCase):
    def test_covered_attribute_change_invalidates(self):
        evidence = ev('ev:1', coverage=default_coverage(
            objects=['net:+5V'], attributes=['power.voltage']))
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_INVALIDATED)
        self.assertIn('covered_attribute_changed', reason_codes(entry))
        self.assertEqual(entry['reasons'][0]['change_ids'], ['chg:1'])
        self.assertIsNone(entry['reuse'])

    def test_covered_impact_filter_hit_invalidates(self):
        coverage = {'objects': ['cmp:U2'], 'attributes': [],
                    'impacts': ['power_integrity']}
        evidence = ev('ev:1', coverage=coverage)
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_INVALIDATED)
        self.assertIn('covered_attribute_changed', reason_codes(entry))
        self.assertEqual(entry['reasons'][0]['change_ids'], ['chg:1'])

    def test_object_level_coverage_without_filter_invalidates(self):
        coverage = {'objects': ['cmp:U2'], 'attributes': [], 'impacts': []}
        evidence = ev('ev:1', coverage=coverage)
        result = run_assessment(electrical_model([evidence]))
        self.assertEqual(status_of(result, 'ev:1'),
                         evidence_module.EVIDENCE_INVALIDATED)

    def test_global_impact_coverage_hit_invalidates(self):
        coverage = {'objects': [], 'attributes': [],
                    'impacts': ['power_integrity']}
        evidence = ev('ev:1', coverage=coverage)
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_INVALIDATED)
        self.assertIn('covered_attribute_changed', reason_codes(entry))


# ---------------------------------------------------------------------------
# 6. unrelated changes must not invalidate independent evidence
# ---------------------------------------------------------------------------

class UnrelatedChangeTest(unittest.TestCase):
    def test_no_overlap_is_not_applicable(self):
        extra = [obj('cmp:U9', 'component_instance', {'mpn': 'SPARE'})]
        checks = [check('chk:spare', 'offline',
                        [{'object': 'cmp:U9', 'impact': 'power_integrity'}])]
        coverage = {'objects': ['cmp:U9'], 'attributes': ['mpn'],
                    'impacts': []}
        evidence = ev('ev:1', 'chk:spare', coverage=coverage)
        model = electrical_model([evidence], checks=checks,
                                 extra_objects=extra)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_NOT_APPLICABLE)
        self.assertIn('no_overlap', reason_codes(entry))
        self.assertIsNone(entry['reuse'])

    def test_display_only_change_does_not_invalidate_electrical_evidence(self):
        objects = [
            obj('cmp:U1', 'component_instance',
                {'display': {'label': 'REG'}},
                {'display': {'label': 'LDO'}}),
            obj('cmp:U2', 'component_instance', {'mpn': 'LDO1'}),
        ]
        checks = [check('chk:value', 'offline',
                        [{'object': 'cmp:U1', 'impact': 'electrical_state'}])]
        coverage = {'objects': ['cmp:U1'], 'attributes': ['value'],
                    'impacts': ['electrical_state', 'power_integrity']}
        evidence = ev('ev:1', 'chk:value', coverage=coverage)
        model = build_model(
            objects,
            changes=[chg('chg:1', 'cmp:U1', 'display.label', 'LDO', 'REG')],
            checks=checks,
            evidence=[evidence],
        )
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_NOT_APPLICABLE)
        self.assertIsNone(entry['reuse'])

    def test_document_title_change_does_not_invalidate_electrical_evidence(self):
        objects = [
            obj('doc:main', 'document',
                {'document': {'title': 'new'}},
                {'document': {'title': 'old'}}),
            obj('cmp:U2', 'component_instance', {'mpn': 'LDO1'}),
        ]
        checks = [check('chk:value', 'offline',
                        [{'object': 'cmp:U2', 'impact': 'power_integrity'}])]
        coverage = {'objects': ['cmp:U2'], 'attributes': ['mpn'],
                    'impacts': ['power_integrity']}
        evidence = ev('ev:1', 'chk:value', coverage=coverage)
        model = build_model(
            objects,
            changes=[chg('chg:1', 'doc:main', 'document.title', 'old', 'new')],
            checks=checks,
            evidence=[evidence],
        )
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_NOT_APPLICABLE)

    def test_no_overlap_with_fingerprint_is_not_applicable(self):
        extra = [obj('cmp:U9', 'component_instance', {'mpn': 'SPARE'})]
        checks = [check('chk:spare', 'offline',
                        [{'object': 'cmp:U9', 'impact': 'power_integrity'}])]
        coverage = {'objects': ['cmp:U9'], 'attributes': ['mpn'],
                    'impacts': []}
        evidence = ev('ev:1', 'chk:spare', coverage=coverage,
                      dependency_fingerprint=ZERO_HASH)
        model = electrical_model([evidence], checks=checks,
                                 extra_objects=extra)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_NOT_APPLICABLE)
        self.assertIsNone(entry['reuse'])


# ---------------------------------------------------------------------------
# 7. semantic reuse via dependency fingerprint
# ---------------------------------------------------------------------------

def _fingerprint_scenario(*, simulated=False, fingerprint='auto'):
    """Covered attribute is not directly changed but the object is impacted.

    ``cmp:U2.mpn`` is untouched by the voltage change, while the propagator
    reports ``power_integrity`` on ``cmp:U2``; the covered impact filter
    (``electrical_state``) does not match, so the case is "related, not hit"
    and only the fingerprint can prove semantic reuse.
    """
    coverage = {'objects': ['cmp:U2'], 'attributes': ['mpn'],
                'impacts': ['electrical_state']}
    record = ev('ev:1', coverage=coverage, simulated=simulated,
                dependency_fingerprint=ZERO_HASH)
    if fingerprint == 'auto':
        record['dependency_fingerprint'] = None
    elif fingerprint is None:
        record['dependency_fingerprint'] = None
    model = electrical_model([record])
    if fingerprint == 'auto':
        model.evidence[0]['dependency_fingerprint'] = \
            evidence_module.covered_attribute_fingerprint(
                model, coverage)
    return model, coverage


class FingerprintReuseTest(unittest.TestCase):
    def test_fingerprint_match_is_reusable_with_assessment(self):
        model, coverage = _fingerprint_scenario()
        expected = evidence_module.covered_attribute_fingerprint(model,
                                                                 coverage)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_REUSABLE_ASSESSED)
        self.assertIn('dependency_fingerprint_match', reason_codes(entry))
        self.assertEqual(entry['reuse']['basis'],
                         'dependency_fingerprint_match')
        self.assertEqual(entry['reuse']['computed_fingerprint'], expected)
        self.assertEqual(entry['reuse']['covered_objects'], ['cmp:U2'])
        self.assertEqual(entry['reuse']['covered_attributes'], ['mpn'])
        preserved = entry['reuse']['preserved_capture']
        self.assertEqual(preserved['captured_at'], CAPTURED_AT)
        self.assertEqual(preserved['revision'], OLD_REVISION)
        self.assertEqual(preserved['content_hash'], HASH_A)
        self.assertEqual(preserved['tool_version'], '0.9.0')
        self.assertFalse(preserved['simulated'])
        self.assertIsNone(preserved['host'])
        self.assertEqual(entry['original']['captured_at'], CAPTURED_AT)
        self.assertEqual(entry['valid_for'], ['offline'])
        self.assertTrue(entry['reuse']['limits'])

    def test_fingerprint_mismatch_invalidates(self):
        model, _coverage = _fingerprint_scenario(fingerprint=ZERO_HASH)
        entry = assessment_for(run_assessment(model), 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_INVALIDATED)
        self.assertIn('dependency_fingerprint_mismatch',
                      reason_codes(entry))
        self.assertIsNone(entry['reuse'])

    def test_related_without_fingerprint_is_unknown(self):
        model, _coverage = _fingerprint_scenario(fingerprint=None)
        result = run_assessment(model)
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('evidence_missing_fingerprint', reason_codes(entry))
        self.assertIsNone(entry['reuse'])
        self.assertEqual(result['unknown'][0]['code'],
                         'evidence_missing_fingerprint')

    def test_reuse_limits_describe_coverage_and_conditions(self):
        coverage = {'objects': ['cmp:U2'], 'attributes': ['mpn'],
                    'impacts': ['electrical_state']}
        record = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                    coverage=coverage, conditions=['ambient 25C'],
                    valid_until=LATER)
        model = electrical_model([record])
        entry = assessment_for(run_assessment(model), 'ev:1')
        limits = ' '.join(entry['reuse']['limits'])
        self.assertIn('cmp:U2', limits)
        self.assertIn('mpn', limits)
        self.assertIn('ambient 25C', limits)
        self.assertIn(LATER, limits)
        self.assertIn(evidence_module.PRESERVED_LIMIT,
                      entry['reuse']['limits'])


# ---------------------------------------------------------------------------
# 8. propagation unknown boundaries
# ---------------------------------------------------------------------------

class PropagationUnknownTest(unittest.TestCase):
    def test_unknown_impact_object_makes_evidence_unknown(self):
        coverage = {'objects': ['cmp:U2'], 'attributes': ['mpn'],
                    'impacts': []}
        evidence = ev('ev:1', coverage=coverage)
        model = electrical_model([evidence])
        impacts = empty_impacts(unknown=[{
            'code': 'missing_edge_data',
            'object': 'cmp:U2',
            'reason': 'no declared dependency lets this change class continue',
            'change_ids': ['chg:1'],
        }], truncated=True)
        baseline = run_assessment(model, impacts=impacts)
        entry = assessment_for(baseline, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('evidence_missing_fingerprint', reason_codes(entry))
        notes = ' '.join(baseline['notes'])
        self.assertIn('truncated', notes)
        self.assertIn('unknown', notes)

    def test_unknown_impact_object_with_matching_fingerprint_is_reusable(self):
        coverage = {'objects': ['cmp:U2'], 'attributes': ['mpn'],
                    'impacts': []}
        evidence = ev('ev:1', coverage=coverage,
                      dependency_fingerprint=ZERO_HASH)
        model = electrical_model([evidence])
        model.evidence[0]['dependency_fingerprint'] = \
            evidence_module.covered_attribute_fingerprint(model, coverage)
        impacts = empty_impacts(unknown=[{
            'code': 'missing_edge_data',
            'object': 'cmp:U2',
            'reason': 'unresolved propagation boundary',
            'change_ids': ['chg:1'],
        }])
        entry = assessment_for(
            run_assessment(model, impacts=impacts), 'ev:1')
        self.assertEqual(entry['status'],
                         evidence_module.EVIDENCE_REUSABLE_ASSESSED)


# ---------------------------------------------------------------------------
# 9. output contract, completeness and determinism
# ---------------------------------------------------------------------------

class OutputContractTest(unittest.TestCase):
    def test_assessment_fields_match_contract(self):
        evidence = ev('ev:1', coverage=default_coverage())
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(sorted(entry), [
            'check', 'coverage', 'evidence_id', 'notes', 'original',
            'reasons', 'reuse', 'status', 'valid_for'])
        self.assertEqual(entry['check'], 'chk:voltage')
        self.assertIn(entry['status'], evidence_module.EVIDENCE_STATES)
        for reason in entry['reasons']:
            self.assertEqual(sorted(reason), ['change_ids', 'code', 'detail'])
        for key, value in entry['original'].items():
            self.assertNotEqual(value, '<invented>')
        self.assertNotIn('assessed_at', entry)
        self.assertNotIn('assessed_at', entry['original'])

    def test_unknown_entries_match_contract(self):
        evidence = ev('ev:1', revision=None, coverage=default_coverage())
        result = run_assessment(electrical_model([evidence]))
        self.assertEqual(len(result['unknown']), 1)
        self.assertEqual(sorted(result['unknown'][0]),
                         ['code', 'evidence_id', 'reason'])
        self.assertEqual(result['unknown'][0]['code'],
                         'evidence_missing_binding')

    def test_all_evidence_records_retained_and_sorted(self):
        binding = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                     coverage=default_coverage())
        expired = ev('ev:2', coverage=default_coverage(),
                     valid_until=EARLIER)
        incomplete = ev('ev:3', revision=None,
                        coverage=default_coverage())
        model = electrical_model([incomplete, binding, expired],
                                 analysis_time=LATER)
        result = run_assessment(model)
        self.assertEqual([item['evidence_id'] for item in
                          result['assessments']],
                         ['ev:1', 'ev:2', 'ev:3'])
        self.assertEqual(result['counts'], {
            'invalidated': 1,
            'reusable_bound': 1,
            'reusable_with_assessment': 0,
            'not_applicable': 0,
            'unknown': 1,
            'total': 3,
        })
        self.assertFalse(result['simulated_only'])

    def test_no_evidence_returns_empty_assessment(self):
        model = electrical_model([])
        result = run_assessment(model)
        self.assertEqual(result['assessments'], [])
        self.assertEqual(result['counts']['total'], 0)
        self.assertEqual(result['counts']['invalidated'], 0)
        self.assertFalse(result['simulated_only'])
        self.assertTrue(result['notes'])

    def test_touch_or_copy_cannot_restore_validity(self):
        # A freshly captured_at and scope_complete=true cannot compensate for a
        # missing content_hash: the binding is what proves reuse, not mtime.
        evidence = ev('ev:1', content_hash=None,
                      captured_at='2026-12-31T23:59:59Z',
                      scope_complete=True, coverage=default_coverage())
        result = run_assessment(electrical_model([evidence]))
        entry = assessment_for(result, 'ev:1')
        self.assertEqual(entry['status'], evidence_module.EVIDENCE_UNKNOWN)
        self.assertIn('evidence_missing_binding', reason_codes(entry))
        self.assertIsNone(entry['reuse'])
        # The copied timestamp is preserved, never promoted into a new capture.
        self.assertEqual(entry['original']['captured_at'],
                         '2026-12-31T23:59:59Z')

    def test_determinism_same_input_identical_output(self):
        model, _coverage = _fingerprint_scenario()
        first = run_assessment(model)
        second = run_assessment(model)
        self.assertEqual(canonical_module.canonical_json(first),
                         canonical_module.canonical_json(second))

    def test_input_evidence_order_does_not_change_output(self):
        binding = ev('ev:1', revision=NEW_REVISION, content_hash=HASH_B,
                     coverage=default_coverage())
        incomplete = ev('ev:2', revision=None,
                        coverage=default_coverage())
        first = run_assessment(electrical_model([binding, incomplete]))
        second = run_assessment(electrical_model([incomplete, binding]))
        self.assertEqual(canonical_module.canonical_json(first),
                         canonical_module.canonical_json(second))


if __name__ == '__main__':
    unittest.main()
