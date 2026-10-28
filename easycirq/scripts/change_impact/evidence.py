"""J3: prior-evidence invalidation and reuse assessment.

The module answers a narrow, auditable question: *may a previously captured
verification result still be relied on for the candidate revision, and if so
under which limits?*  It never turns absence of evidence into validity and it
never manufactures a fresh capture:

* reuse requires a **proven content binding** — the evidence revision and
  content hash match the candidate, or the candidate values of the covered
  attributes hash to the recorded ``dependency_fingerprint``;
* an original capture (``captured_at``, ``revision``, ``content_hash``,
  ``tool_version``, ``host``) is copied verbatim and never rewritten, so
  touching a file, copying an evidence directory or rewriting a manifest
  cannot restore validity;
* missing binding fields, an empty coverage declaration, an unparseable
  expiry or an unverifiable fingerprint produce ``unknown`` — not "probably
  fine" and not an invented invalidation;
* ``simulated`` evidence can only ever be an ``offline`` reference.  It never
  serves as a host DRC, save-and-reopen, official plot or physical-test pass.

The rules are expressed as explicit branches (see ``README``-style document
``docs/parallel-change-impact/evidence-reuse-policy.md``) and every list is
deterministically ordered, so identical input yields identical output.  Only
the standard library is used; nothing here reads the environment, network or
an EDA tool, and nothing mutates the model.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import (
    CHECK_KINDS,
    EVIDENCE_INVALIDATED,
    EVIDENCE_NOT_APPLICABLE,
    EVIDENCE_REUSABLE_ASSESSED,
    EVIDENCE_REUSABLE_BOUND,
    EVIDENCE_STATES,
    EVIDENCE_UNKNOWN,
)
from . import canonical as canon
from .model import MISSING

DOCUMENTATION_ONLY = 'documentation_only'

#: Fields whose absence makes a reuse claim unprovable (contract §2.4).
BINDING_FIELDS = ('revision', 'content_hash', 'tool_version')

SIMULATED_LIMIT = '模拟证据，仅离线参考，不得作为宿主/实物通过依据'
PRESERVED_LIMIT = ('原始捕获原样保留（captured_at/revision/content_hash/host 未改写），'
                   '本评估不生成新的捕获时间或宿主回执')
NO_FILTER_LIMIT = ('未声明覆盖对象/覆盖属性：不能把该证据扩大解释为整板或未列出对象。')


# ---------------------------------------------------------------------------
# deterministic copies and small helpers
# ---------------------------------------------------------------------------

def _copy(value):
    """Deep JSON copy so no caller can mutate the model through the report."""
    return canon.canonical_value(value, where='evidence')


def _reason(code, detail, change_ids=None):
    return {
        'code': code,
        'detail': detail,
        'change_ids': sorted({str(item) for item in (change_ids or []) if item}),
    }


def _parse_time(value):
    """Parse an ISO 8601 timestamp, accepting a trailing ``Z`` on Python 3.10.

    Naive timestamps are interpreted as UTC so a comparison is always
    well-defined; anything unparseable returns ``None`` (never "not expired").
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coverage_empty(coverage):
    if not isinstance(coverage, dict):
        return True
    return not any(coverage.get(key) for key in ('objects', 'attributes', 'impacts'))


def covered_attribute_fingerprint(model, coverage):
    """Recompute the candidate-side fingerprint of an evidence coverage.

    Convention (documents in ``evidence-reuse-policy.md``):

    * for every covered object and every listed covered attribute path, take
      the candidate value and pair it as ``(object_id + ':' + path, value)``;
      absent values (``MISSING``) are skipped;
    * every covered impact is added as ``('impact:' + impact, impact)``;
    * the pairs are sorted and hashed with :func:`canonical.fingerprint`.

    Returns ``None`` when the coverage does not name enough information to
    recompute a comparable fingerprint.  A stored fingerprint that cannot be
    recomputed is ``unknown``, never assumed equal.
    """
    if not isinstance(coverage, dict):
        return None
    identities = [item for item in coverage.get('objects') or []
                  if isinstance(item, str)]
    attributes = [item for item in coverage.get('attributes') or []
                  if isinstance(item, str)]
    impacts = [item for item in coverage.get('impacts') or []
               if isinstance(item, str)]
    if not attributes and not impacts:
        # Object-level coverage without attribute paths cannot be recomputed
        # without inventing a convention the capture did not declare.
        return None
    if not identities and attributes:
        # Attribute paths without objects cannot be resolved to values.
        if not impacts:
            return None
    pairs = []
    for identity in identities:
        if model.object(identity) is None:
            return None
        for path in attributes:
            value = model.candidate_value(identity, path)
            if value is MISSING:
                continue
            pairs.append((identity + ':' + path, value))
    for impact in impacts:
        pairs.append(('impact:' + impact, impact))
    return canon.fingerprint(pairs)


def _valid_for(kind, simulated, status):
    """Check kinds this assessment allows the evidence to support.

    Reuse limits the answer to the captured check kind; simulated evidence is
    reduced to ``offline`` even when the recorded check claimed to be a host or
    manual run (that case is invalidated separately).  Non-reusable states
    support nothing in this change scope.
    """
    if status not in (EVIDENCE_REUSABLE_BOUND, EVIDENCE_REUSABLE_ASSESSED):
        return []
    if simulated:
        return ['offline']
    return [kind] if kind in CHECK_KINDS else []


def _limits(record, coverage, simulated, kind, *, fingerprint=False):
    limits = []
    covered_objects = list((coverage or {}).get('objects') or [])
    covered_attributes = list((coverage or {}).get('attributes') or [])
    covered_impacts = list((coverage or {}).get('impacts') or [])
    if covered_objects:
        limits.append('覆盖对象仅限：' + ', '.join(sorted(covered_objects)))
    if covered_attributes:
        limits.append('覆盖属性仅限：' + ', '.join(sorted(covered_attributes)))
    if covered_impacts:
        limits.append('覆盖影响类别仅限：' + ', '.join(sorted(covered_impacts)))
    if not covered_objects and not covered_attributes:
        limits.append(NO_FILTER_LIMIT)
    if record.get('conditions'):
        limits.append('适用条件：' + '; '.join(sorted(record['conditions'])))
    if record.get('valid_until'):
        limits.append('有效期至：' + str(record['valid_until']))
    if record.get('result') != 'pass':
        limits.append('原始捕获结果为 %r；复用该捕获不会把失败/未知结果变成通过。'
                      % (record.get('result'),))
    if simulated:
        limits.append(SIMULATED_LIMIT)
    elif kind == 'offline':
        limits.append('该证据来自离线检查，不能替代宿主 DRC/保存重开/官方导图/实物测试。')
    # Every reuse payload states that the original capture is preserved: a
    # copied/touched/manifest-rewritten record does not become a new capture.
    limits.append(PRESERVED_LIMIT)
    return limits


def _preserved_capture(record):
    return {
        'captured_at': _copy(record.get('captured_at')),
        'revision': _copy(record.get('revision')),
        'content_hash': _copy(record.get('content_hash')),
        'tool_version': _copy(record.get('tool_version')),
        'simulated': bool(record.get('simulated')),
        'host': _copy(record.get('host')),
    }


def _reuse_payload(record, coverage, simulated, kind, basis, computed=None):
    reuse = {
        'basis': basis,
        'covered_objects': sorted((coverage or {}).get('objects') or []),
        'covered_attributes': sorted((coverage or {}).get('attributes') or []),
        'covered_impacts': sorted((coverage or {}).get('impacts') or []),
        'preserved_capture': _preserved_capture(record),
        'limits': _limits(record, coverage, simulated, kind,
                          fingerprint=computed is not None),
    }
    if computed is not None:
        reuse['computed_fingerprint'] = computed
    return reuse


# ---------------------------------------------------------------------------
# impact index (from propagate's return value)
# ---------------------------------------------------------------------------

def _impact_index(impacts):
    """Index the J2 output by target object and impact kind.

    ``impacted_objects`` is authoritative; ``impact_paths`` fills any target a
    caller-supplied subset might otherwise hide.  Objects named by an
    ``unknown`` propagation entry are recorded separately: their impact could
    not be bounded, so evidence covering them can only become ``unknown``.
    """
    objects = {}
    paths = []
    if isinstance(impacts, dict):
        paths = [item for item in impacts.get('impact_paths') or []
                 if isinstance(item, dict)]
        direct_objects = [item for item in impacts.get('impacted_objects') or []
                          if isinstance(item, dict)]
    else:
        direct_objects = []

    def add(identity, kind_impacts, change_ids, direct):
        if not isinstance(identity, str) or not identity:
            return
        entry = objects.setdefault(identity, {
            'impacts': set(), 'change_ids': set(), 'direct': False})
        entry['impacts'].update(str(item) for item in kind_impacts if item)
        entry['change_ids'].update(str(item) for item in change_ids if item)
        entry['direct'] = entry['direct'] or bool(direct)

    for path in paths:
        add(path.get('target'), path.get('impacts') or [path.get('impact')],
            path.get('change_ids') or [], not path.get('steps'))
    for item in direct_objects:
        add(item.get('object'), item.get('impacts') or [],
            item.get('change_ids') or [], item.get('direct'))

    unknown_objects = set()
    if isinstance(impacts, dict):
        for item in impacts.get('unknown') or []:
            if not isinstance(item, dict):
                continue
            identity = item.get('object')
            if isinstance(identity, str) and identity:
                unknown_objects.add(identity)

    all_impacts = set()
    change_ids_by_impact = {}
    for identity, entry in objects.items():
        all_impacts.update(entry['impacts'])
        for impact in entry['impacts']:
            change_ids_by_impact.setdefault(impact, set()).update(
                entry['change_ids'])

    return {
        'objects': objects,
        'unknown_objects': unknown_objects,
        'all_impacts': all_impacts,
        'change_ids_by_impact': change_ids_by_impact,
        'truncated': bool(isinstance(impacts, dict) and impacts.get('truncated')),
        'unknown_count': len(unknown_objects),
        'unknown_entry_count': len((impacts or {}).get('unknown') or [])
        if isinstance(impacts, dict) else 0,
    }


# ---------------------------------------------------------------------------
# coverage overlap
# ---------------------------------------------------------------------------

def _changed_attributes(model):
    """Index declared changes and observed differences by object."""
    index = {}
    for change in getattr(model, 'changes', []) or []:
        index.setdefault(change['object'], []).append({
            'change_id': change.get('id'),
            'attribute': change.get('attribute'),
            'kind': change.get('kind'),
            'observed': False,
        })
    for diff in getattr(model, 'observed_diff', []) or []:
        index.setdefault(diff['object'], []).append({
            'change_id': None,
            'attribute': diff.get('attribute'),
            'kind': None,
            'observed': True,
        })
    for identity in index:
        index[identity].sort(key=lambda item: (
            item['change_id'] or '~observed',
            item['attribute'] or '',
            item['observed'],
        ))
    return index


def _attribute_matches(attribute, covered_attributes):
    """True when a changed attribute path is within a covered attribute path.

    Covered attribute names are often shorter than a changed path
    (``voltage`` covers ``power.voltage``) or longer
    (``voltage.nominal`` inside ``voltage``); both forms match.  A whole-object
    change (``attribute is None``) touches every covered attribute.
    """
    if not covered_attributes:
        return False
    if attribute is None:
        return True
    changed = str(attribute)
    for covered in covered_attributes:
        covered = str(covered)
        if changed == covered:
            return True
        if changed.startswith(covered + '.') or covered.startswith(changed + '.'):
            return True
        if changed.split('.')[-1] == covered.split('.')[-1]:
            return True
    return False


def _change_label(entry):
    attribute = entry['attribute'] if entry['attribute'] is not None else '*'
    if entry['observed']:
        return 'observed:' + attribute
    return '%s:%s' % (entry['change_id'], attribute)


def _coverage_overlap(model, impact_index, coverage):
    """Decide whether the coverage is *hit* or merely *related*.

    ``hit``   — a covered object/attribute/impact is demonstrably affected by
                this change set; the capture cannot cover the candidate.
    ``related`` — the coverage touches something in the impact set, but the
                covered attributes were not directly changed and the declared
                impact filter did not match; only a fingerprint comparison can
                decide.  No fingerprint makes it ``unknown``.
    neither   — the check is unrelated to this change set (``not_applicable``).
    """
    covered_objects = list((coverage or {}).get('objects') or [])
    covered_attributes = list((coverage or {}).get('attributes') or [])
    covered_impacts = set((coverage or {}).get('impacts') or [])
    changed = _changed_attributes(model)

    hit = False
    related = False
    hit_changes = set()
    details = []

    if covered_objects:
        for identity in covered_objects:
            object_changes = changed.get(identity, [])
            matched_changes = [
                entry for entry in object_changes
                if _attribute_matches(entry['attribute'], covered_attributes)]
            if matched_changes:
                hit = True
                hit_changes.update(entry['change_id']
                                   for entry in matched_changes
                                   if entry['change_id'])
                details.append(
                    '%s: covered attribute changed (%s)' % (
                        identity,
                        ', '.join(sorted(_change_label(entry)
                                         for entry in matched_changes))))
                continue
            impacted = impact_index['objects'].get(identity)
            if impacted is not None:
                impacted_impacts = set(impacted['impacts'])
                meaningful = impacted_impacts - {DOCUMENTATION_ONLY}
                if covered_impacts:
                    matched = sorted(impacted_impacts & covered_impacts)
                    if matched:
                        hit = True
                        hit_changes.update(impacted['change_ids'])
                        details.append(
                            '%s: covered impact(s) %s are hit' % (
                                identity, ', '.join(matched)))
                    elif meaningful:
                        # The object is genuinely affected, but only by impact
                        # kinds outside the declared filter: a potential
                        # relation resolved by the fingerprint, not a hit.
                        related = True
                    # A documentation-only consequence that the filter does not
                    # cover cannot invalidate independent physical evidence.
                elif covered_attributes:
                    # Attribute-specific coverage: an indirect impact may or
                    # may not have changed the covered values, so the
                    # fingerprint decides.  A documentation-only consequence
                    # cannot touch electrical/mechanical values.
                    if meaningful:
                        related = True
                else:
                    if meaningful:
                        hit = True
                        hit_changes.update(impacted['change_ids'])
                        details.append(
                            '%s: object is impacted (%s) and the evidence '
                            'declares no attribute/impact filter' % (
                                identity, ', '.join(sorted(meaningful))))
            elif identity in impact_index['unknown_objects']:
                related = True
            elif object_changes:
                meaningful_changes = [entry for entry in object_changes
                                      if entry['kind'] != 'display_only']
                if meaningful_changes:
                    related = True
    elif covered_impacts:
        matched = sorted(impact_index['all_impacts'] & covered_impacts)
        if matched:
            hit = True
            for impact in matched:
                hit_changes.update(
                    impact_index['change_ids_by_impact'].get(impact, set()))
            details.append('covered impact(s) %s are hit' % ', '.join(matched))
        elif impact_index['all_impacts'] - {DOCUMENTATION_ONLY}:
            related = True

    return {
        'hit': hit,
        'related': related,
        'change_ids': sorted(hit_changes),
        'details': details,
    }


# ---------------------------------------------------------------------------
# one evidence record
# ---------------------------------------------------------------------------

def _assessment(record, status, reasons, reuse, coverage, kind, simulated,
                notes):
    return {
        'evidence_id': record['id'],
        'check': record.get('check'),
        'status': status,
        'reasons': reasons,
        'reuse': reuse,
        'original': {key: _copy(record[key]) for key in sorted(record)},
        'coverage': _copy(coverage),
        'valid_for': _valid_for(kind, simulated, status),
        'notes': notes,
    }


def _assess_record(model, impact_index, record, supplied_time, parsed_time):
    evidence_id = record['id']
    check = model.checks.get(record.get('check'))
    notes = []
    coverage = record.get('coverage')
    simulated = bool(record.get('simulated'))
    kind = check['kind'] if check is not None else 'offline'
    if check is None:  # defensive: model.py already rejects unknown checks
        reason = _reason(
            'evidence_unknown_check',
            'the evidence names check %r which is not in the verification '
            'catalog' % (record.get('check'),))
        return _assessment(record, EVIDENCE_UNKNOWN, [reason], None, coverage,
                           kind, simulated, notes)

    # -- (a) missing binding fields: never defaults to valid -----------------
    missing_fields = [field for field in ('result',) + BINDING_FIELDS
                      if record.get(field) is None]
    if missing_fields:
        reason = _reason(
            'evidence_missing_binding',
            'required binding field(s) missing: %s; an absent field never '
            'defaults to a valid capture' % ', '.join(missing_fields))
        return _assessment(record, EVIDENCE_UNKNOWN, [reason], None, coverage,
                           kind, simulated,
                           notes + ['missing_fields: ' + ', '.join(missing_fields)])

    # -- (b) expiry (valid_until < analysis_time) ----------------------------
    valid_until = record.get('valid_until')
    if valid_until is not None:
        if parsed_time is None:
            if supplied_time is not None:
                reason = _reason(
                    'unparseable_expiry',
                    'valid_until %r is not a parseable ISO 8601 timestamp; the '
                    'expiry cannot be evaluated, so the evidence is not treated '
                    'as valid' % (valid_until,))
                return _assessment(record, EVIDENCE_UNKNOWN, [reason], None,
                                   coverage, kind, simulated, notes)
            notes.append('valid_until is present but no analysis_time was '
                         'supplied; expiry was not evaluated')
        else:
            expiry = _parse_time(valid_until)
            if expiry is None:
                reason = _reason(
                    'unparseable_expiry',
                    'valid_until %r is not a parseable ISO 8601 timestamp; the '
                    'expiry cannot be evaluated, so the evidence is not treated '
                    'as valid' % (valid_until,))
                return _assessment(record, EVIDENCE_UNKNOWN, [reason], None,
                                   coverage, kind, simulated, notes)
            if expiry < parsed_time:
                reason = _reason(
                    'expired',
                    'valid_until %r is earlier than analysis_time %r' % (
                        valid_until, supplied_time))
                return _assessment(record, EVIDENCE_INVALIDATED, [reason], None,
                                   coverage, kind, simulated, notes)

    # -- (c) simulated evidence can never satisfy a host/manual check --------
    if simulated and kind in ('host', 'manual'):
        reason = _reason(
            'simulated_cannot_satisfy_host_check',
            'simulated=true cannot support a %s check; simulated evidence is '
            'an offline reference only and is never a host/physical pass' % kind)
        return _assessment(record, EVIDENCE_INVALIDATED, [reason], None,
                           coverage, kind, simulated,
                           notes + [SIMULATED_LIMIT])

    # -- (f) an empty coverage cannot bound a reuse claim --------------------
    if _coverage_empty(coverage):
        if record.get('dependency_fingerprint'):
            detail = ('coverage is absent or empty, so the stored '
                      'dependency_fingerprint cannot be recomputed; reuse '
                      'cannot be proven')
        else:
            detail = ('coverage is absent or empty (objects/attributes/'
                      'impacts) and no dependency_fingerprint is recorded; a '
                      'reuse claim has no bounds')
        reason = _reason('evidence_missing_coverage', detail)
        return _assessment(record, EVIDENCE_UNKNOWN, [reason], None, coverage,
                           kind, simulated, notes)

    # -- (d) content binding: same candidate revision and hash ---------------
    candidate_revision = model.candidate['revision']
    candidate_hash = model.candidate['content_hash']
    if record['revision'] == candidate_revision and \
            record['content_hash'] == candidate_hash:
        if not record.get('scope_complete'):
            reason = _reason(
                'evidence_incomplete_scope',
                'revision/content_hash match the candidate but '
                'scope_complete is false: a partial capture cannot be reused '
                'as a complete binding')
            return _assessment(record, EVIDENCE_UNKNOWN, [reason], None,
                               coverage, kind, simulated, notes)
        reason = _reason(
            'same_revision_and_content_hash',
            'evidence revision %r and content_hash %r match the candidate '
            'snapshot; the capture is preserved verbatim' % (
                record['revision'], record['content_hash']))
        reuse = _reuse_payload(record, coverage, simulated, kind,
                               'same_revision_and_content_hash')
        if simulated:
            notes.append(SIMULATED_LIMIT)
        notes.append(PRESERVED_LIMIT)
        return _assessment(record, EVIDENCE_REUSABLE_BOUND, [reason], reuse,
                           coverage, kind, simulated, notes)

    # -- (e) different revision/hash: is the coverage hit or merely related? -
    overlap = _coverage_overlap(model, impact_index, coverage)
    if overlap['hit']:
        detail = '; '.join(overlap['details']) or (
            'the check coverage is hit by the known impact set')
        reason = _reason('covered_attribute_changed', detail,
                         overlap['change_ids'])
        return _assessment(record, EVIDENCE_INVALIDATED, [reason], None,
                           coverage, kind, simulated, notes)

    if not overlap['related']:
        reason = _reason(
            'no_overlap',
            'the check coverage does not intersect the objects/impacts '
            'affected by this change set; the check is not needed here')
        return _assessment(record, EVIDENCE_NOT_APPLICABLE, [reason], None,
                           coverage, kind, simulated, notes)

    if not record.get('dependency_fingerprint'):
        reason = _reason(
            'evidence_missing_fingerprint',
            'the coverage relates to the known impacts but no '
            'dependency_fingerprint is recorded; semantic reuse cannot be '
            'proven and the evidence is not disproved either')
        return _assessment(record, EVIDENCE_UNKNOWN, [reason], None, coverage,
                           kind, simulated, notes)

    computed = covered_attribute_fingerprint(model, coverage)
    if computed is None:
        reason = _reason(
            'fingerprint_unverifiable',
            'the coverage does not name the objects/attributes needed to '
            'recompute a comparable fingerprint; the stored '
            'dependency_fingerprint cannot be verified')
        return _assessment(record, EVIDENCE_UNKNOWN, [reason], None, coverage,
                           kind, simulated, notes)

    if computed == record['dependency_fingerprint']:
        reason = _reason(
            'dependency_fingerprint_match',
            'candidate covered-attribute fingerprint %s equals the captured '
            'dependency_fingerprint; the capture metadata is preserved '
            'unchanged' % computed)
        reuse = _reuse_payload(record, coverage, simulated, kind,
                               'dependency_fingerprint_match', computed)
        if simulated:
            notes.append(SIMULATED_LIMIT)
        notes.append(PRESERVED_LIMIT)
        return _assessment(record, EVIDENCE_REUSABLE_ASSESSED, [reason], reuse,
                           coverage, kind, simulated, notes)

    reason = _reason(
        'dependency_fingerprint_mismatch',
        'candidate covered-attribute fingerprint %s does not equal the '
        'captured dependency_fingerprint %s' % (
            computed, record['dependency_fingerprint']))
    return _assessment(record, EVIDENCE_INVALIDATED, [reason], None, coverage,
                       kind, simulated, notes)


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def assess(model, graph, impacts, *, analysis_time=None):
    """Return ``{assessments, unknown, counts, simulated_only, notes}``.

    ``impacts`` is the dictionary returned by :func:`propagate.propagate`
    (``impacted_objects``, ``impact_paths`` and ``unknown`` are read).
    ``analysis_time`` defaults to the model's declared ``analysis_time``; when
    neither is a parseable ISO 8601 timestamp, expiry is reported as *not
    evaluated* rather than treated as valid.

    Reuse requires a proven binding: matching revision/content_hash with
    ``scope_complete``, or an unchanged covered-attribute fingerprint.  The
    original capture metadata is preserved verbatim; a fresh time or host
    receipt is never invented.  ``graph`` is accepted for interface symmetry
    with the other modules and is not needed here because J2 already resolved
    the impact set.
    """
    index = _impact_index(impacts)
    supplied_time = (analysis_time if analysis_time is not None
                     else getattr(model, 'analysis_time', None))
    parsed_time = _parse_time(supplied_time)

    assessments = []
    unknown_entries = []
    counts = {state: 0 for state in EVIDENCE_STATES}
    counts['total'] = 0
    simulated_count = 0

    for record in sorted(getattr(model, 'evidence', []) or [],
                         key=lambda item: item['id']):
        assessment = _assess_record(model, index, record, supplied_time,
                                    parsed_time)
        assessments.append(assessment)
        counts[assessment['status']] += 1
        counts['total'] += 1
        if record.get('simulated'):
            simulated_count += 1
        if assessment['status'] == EVIDENCE_UNKNOWN:
            first = assessment['reasons'][0]
            unknown_entries.append({
                'code': first['code'],
                'evidence_id': assessment['evidence_id'],
                'reason': first['detail'],
            })

    unknown_entries.sort(key=lambda item: (item['code'], item['evidence_id']))
    simulated_only = bool(assessments) and simulated_count == len(assessments)

    notes = []
    if not assessments:
        notes.append('no prior_evidence records were supplied; no evidence can '
                     'be reused for this change set')
    if simulated_count:
        notes.append('%d simulated evidence record(s): offline reference only, '
                     'never a host/manual/physical pass' % simulated_count)
    if supplied_time is None:
        notes.append('no analysis_time was supplied; valid_until expiry was not '
                     'evaluated (that is not the same as valid)')
    elif parsed_time is None:
        notes.append('analysis_time %r could not be parsed as ISO 8601; '
                     'valid_until expiry was not evaluated' % (supplied_time,))
    if index['truncated']:
        notes.append('the propagated impact set was truncated by budget; '
                     'not_applicable only means "no overlap with the known '
                     'impact set", not proof of no impact')
    if index['unknown_entry_count']:
        notes.append('%d propagation unknown record(s): evidence covering those '
                     'objects cannot be proven reusable'
                     % index['unknown_entry_count'])
    notes.append('captured_at/revision/content_hash/tool_version/host are '
                 'copied verbatim from prior_evidence; no new capture, time or '
                 'host receipt was produced')
    notes.sort()

    return {
        'assessments': assessments,
        'unknown': unknown_entries,
        'counts': counts,
        'simulated_only': simulated_only,
        'notes': notes,
    }
