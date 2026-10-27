"""I6: separate result evaluator (plan generation is never test execution).

Public API used by the CLI and tests::

    evaluate(plan, results, evidence_root=None) -> report dict
    evaluate_files(plan_path, results_path, evidence_root=None) -> report dict
    exit_code_for(report) -> 0/1/2/3

Invariants implemented here (contract ``bringup-result/v1``):

* the result document is strictly typed; malformed JSON *values* (a boolean or
  a string where a number is required, NaN/Infinity, unknown status/source,
  duplicate or unknown step ids) make the evaluation ``INVALID``;
* a result is bound to ``plan_sha256`` + ``input_sha256`` +
  ``input_semantic_sha256`` + design ``revision`` + ``tool_version``.  Any
  mismatch invalidates the whole evaluation (``STALE_REVISION`` /
  ``BINDING_MISMATCH``) instead of silently reusing old results;
* a ``pass`` on a quantitative step needs real source, instrument, a measured
  value whose quantity/unit matches the step and whose value lies inside the
  declared range, the step's required evidence kinds, verified evidence files
  (only under the supplied evidence root, SHA-256 checked) and execution
  metadata.  A pass with an out-of-range measurement is an inconsistency, not
  a pass;
* evidence *availability* is a warning, not a document contradiction: a
  missing evidence root/file (or a missing declared digest) only makes the
  affected step unable to pass (``unknown``) and caps the verdict at
  ``INCOMPLETE``; an escaping path or a digest that contradicts the file is a
  structural inconsistency and makes the verdict ``INVALID``;
* ``synthetic`` records never enter a hardware pass; all-synthetic passes yield
  ``SYNTHETIC_ONLY``; ``manual_declaration`` alone never becomes a pass;
* undefined/needs-interpretation criteria are never auto-passed (an accepted
  manual interpretation is at most ``needs_review``);
* a triggered STOP or a failed step blocks every transitive dependent; a
  recorded pass in such a dependent is reported as invalidated
  (``INVALIDATED_BY_STOP``); independent branches continue;
* verdict precedence: ``INVALID`` (binding/schema/unit contradiction), then
  ``FAIL`` (required failure or STOP), then ``PASS`` (all required, ready
  steps pass with verified real evidence), then ``SYNTHETIC_ONLY``, otherwise
  ``INCOMPLETE``.  The completion ratio and per-group/domain statistics are
  reported but can never promote the verdict.

The report contains ``verdict``, ``hardware_pass`` (true only for ``PASS``),
``counts``, ``steps`` (per-step evaluation), ``groups``, ``domains``,
``binding``, ``design``, ``evidence``, ``findings`` and a Chinese
``markdown`` summary.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from . import (EVALUATION_SCHEMA, EXIT_FINDINGS, EXIT_INCOMPLETE,
               EXIT_INVALID_INPUT, EXIT_OK, PLAN_SCHEMA, RESULT_SCHEMA,
               TOOL_NAME, TOOL_VERSION)
from .steps import (CRITERION_STATUSES, GROUP_ORDER, MEASURE_QUANTITIES,
                    STATUSES as PLAN_STATUSES, STATUS_READY)
from .units import UnitError, to_canonical
from .util import (PlannerError, check_attachment_path, iso_now,
                   parse_timestamp, read_json, resolve_within, sha256_file)

STEP_STATUSES = ('pass', 'fail', 'unknown', 'blocked', 'not_run')
SOURCES = ('real_measurement', 'synthetic', 'manual_declaration', 'unset')
VERDICTS = ('PASS', 'FAIL', 'INVALID', 'INCOMPLETE', 'SYNTHETIC_ONLY')

_HEX64 = re.compile(r'^[0-9a-fA-F]{64}$')
_GROUP_KEYS = ('I1', 'I2', 'I3', 'I4')

_OUTCOME_TO_VERDICT = {
    'pass_real': 'pass',
    'fail': 'fail',
    'unknown': 'unknown',
    'blocked': 'blocked',
    'not_run': 'not_run',
    'invalid': 'invalid',
    'invalidated': 'invalidated',
    'synthetic_pass': 'unknown',
    'synthetic_other': 'unknown',
    'manual': 'unknown',
    'needs_review': 'unknown',
    'unverified': 'unknown',
}

_BINDING_KEYS = ('plan_sha256', 'input_sha256', 'input_semantic_sha256',
                 'revision', 'tool_version')


class _Findings:
    """Ordered finding collector (error findings make the verdict INVALID)."""

    def __init__(self):
        self.items = []

    def add(self, code, detail, *, step_id=None, severity='warning'):
        item = {'code': code, 'severity': severity, 'step_id': step_id,
                'detail': detail}
        self.items.append(item)
        return item

    def error(self, code, detail, *, step_id=None):
        return self.add(code, detail, step_id=step_id, severity='error')

    def warning(self, code, detail, *, step_id=None):
        return self.add(code, detail, step_id=step_id, severity='warning')

    @property
    def has_errors(self):
        return any(item['severity'] == 'error' for item in self.items)


def _error_count(findings):
    return sum(1 for item in findings.items if item['severity'] == 'error')


# ---------------------------------------------------------------------------
# public API


def evaluate(plan, results, evidence_root=None):
    """Evaluate recorded ``results`` against ``plan`` and return a report."""
    findings = _Findings()
    plan_meta = _plan_meta(plan, findings)
    result_meta = _result_meta(results, plan_meta, findings)
    binding = _check_binding(plan_meta, result_meta, findings)
    evidence_report = _evidence_report(evidence_root, result_meta, findings)

    evaluations = []
    for step in plan_meta['steps']:
        entry = result_meta['by_id'].get(step['step_id'])
        ev = _evaluate_step(step, entry, findings)
        evaluations.append(ev)
    _propagate(plan_meta, evaluations, findings)
    _annotate_domains(plan_meta, evaluations)

    counts = _counts(evaluations)
    groups = _group_report(evaluations)
    domains = _domain_report(plan_meta, evaluations)
    verdict = _verdict(findings, evaluations, evidence_report)

    report = {
        'schema': EVALUATION_SCHEMA,
        'generator': TOOL_NAME + '-eval',
        'tool_version': TOOL_VERSION,
        'generated_at': iso_now(),
        'verdict': verdict,
        'hardware_pass': verdict == 'PASS',
        'counts': counts,
        'binding': binding,
        'design': dict(plan_meta.get('design') or {}),
        'scope_status': _scope_status(plan),
        'executed_by': result_meta.get('executed_by'),
        'source_kind': result_meta.get('source_kind'),
        'steps': evaluations,
        'groups': groups,
        'domains': domains,
        'evidence': evidence_report,
        'findings': list(findings.items),
        'markdown': '',
    }
    report['markdown'] = _render_markdown(report)
    return report


def evaluate_files(plan_path, results_path, evidence_root=None):
    """Load both JSON documents from disk and evaluate them."""
    plan = read_json(plan_path)
    results = read_json(results_path)
    return evaluate(plan, results, evidence_root=evidence_root)


def exit_code_for(report):
    """Map the report verdict to the documented CLI exit code."""
    verdict = report.get('verdict') if isinstance(report, dict) else None
    if verdict == 'PASS':
        return EXIT_OK
    if verdict == 'FAIL':
        return EXIT_FINDINGS
    if verdict == 'INVALID':
        return EXIT_INVALID_INPUT
    if verdict in ('INCOMPLETE', 'BLOCKED', 'SYNTHETIC_ONLY'):
        return EXIT_INCOMPLETE
    return EXIT_INCOMPLETE


# ---------------------------------------------------------------------------
# plan document


def _plan_meta(plan, findings):
    meta = {'ok': False, 'schema': None, 'tool_version': None,
            'hashes': {}, 'input': {}, 'design': {}, 'steps': [],
            'step_by_id': {}, 'edges': [], 'order': [], 'domains': []}
    if not isinstance(plan, dict):
        findings.error('SCHEMA_INVALID', 'plan must be a JSON object')
        return meta
    before = _error_count(findings)
    schema = plan.get('schema')
    if schema == PLAN_SCHEMA:
        meta['schema'] = schema
    else:
        findings.error('SCHEMA_INVALID',
                       'plan.schema must be %r, got %r'
                       % (PLAN_SCHEMA, schema))
    tool_version = plan.get('tool_version')
    if isinstance(tool_version, str) and tool_version.strip():
        meta['tool_version'] = tool_version.strip()
    else:
        findings.error('SCHEMA_INVALID',
                       'plan.tool_version must be a non-empty string')

    hashes = plan.get('hashes')
    if isinstance(hashes, dict):
        plan_sha = hashes.get('plan_sha256')
        if isinstance(plan_sha, str) and _HEX64.match(plan_sha.strip()):
            meta['hashes']['plan_sha256'] = plan_sha.strip().lower()
        else:
            findings.error('SCHEMA_INVALID',
                           'plan.hashes.plan_sha256 must be a 64-hex SHA-256')
    else:
        findings.error('SCHEMA_INVALID', 'plan.hashes object is required')

    input_block = plan.get('input')
    if isinstance(input_block, dict):
        for key in ('sha256', 'semantic_sha256'):
            value = input_block.get(key)
            if isinstance(value, str) and _HEX64.match(value.strip()):
                meta['input'][key] = value.strip().lower()
            else:
                findings.error('SCHEMA_INVALID',
                               'plan.input.%s must be a 64-hex SHA-256' % key)
    else:
        findings.error('SCHEMA_INVALID', 'plan.input object is required')

    design = plan.get('design')
    if isinstance(design, dict):
        for key in ('project', 'revision', 'source_snapshot_hash',
                    'bom_version', 'assembly_version'):
            value = design.get(key)
            if value is None or isinstance(value, str):
                meta['design'][key] = value
            else:
                findings.error('SCHEMA_INVALID',
                               'plan.design.%s must be a string' % key)
        revision = design.get('revision')
        if not isinstance(revision, str) or not revision.strip():
            findings.error('SCHEMA_INVALID',
                           'plan.design.revision must be a non-empty string')
    else:
        findings.error('SCHEMA_INVALID', 'plan.design object is required')

    meta['steps'] = _plan_steps(plan, findings)
    meta['step_by_id'] = {step['step_id']: step for step in meta['steps']}
    meta['domains'] = _plan_domains(plan)
    meta['edges'], meta['order'] = _plan_step_graph(plan, meta['steps'])
    meta['ok'] = _error_count(findings) == before
    return meta


def _plan_steps(plan, findings):
    raw = plan.get('steps')
    if not isinstance(raw, list) or not raw:
        findings.error('SCHEMA_INVALID',
                       'plan.steps must be a non-empty array')
        return []
    steps = []
    seen = set()
    for index, item in enumerate(raw):
        path = 'plan.steps[%d]' % index
        if not isinstance(item, dict):
            findings.error('SCHEMA_INVALID', '%s must be an object' % path)
            continue
        step_id = item.get('step_id')
        if not isinstance(step_id, str) or not step_id.strip():
            findings.error('SCHEMA_INVALID',
                           '%s.step_id must be a non-empty string' % path)
            continue
        step_id = step_id.strip()
        if step_id in seen:
            findings.error('SCHEMA_INVALID',
                           'duplicate plan step_id %r' % step_id)
            continue
        seen.add(step_id)
        status = item.get('status')
        if status not in PLAN_STATUSES:
            findings.error('SCHEMA_INVALID',
                           '%s.status must be one of %s, got %r'
                           % (path, ', '.join(PLAN_STATUSES), status))
            status = 'blocked'
        group = item.get('group')
        if not isinstance(group, str) or not group.strip():
            findings.error('SCHEMA_INVALID',
                           '%s.group must be a non-empty string' % path)
            group = 'unknown'
        required = item.get('required', True)
        if not isinstance(required, bool):
            findings.error('SCHEMA_INVALID',
                           '%s.required must be a boolean' % path)
            required = True
        measurement = _plan_measurement(item.get('measurement'),
                                       path, findings)
        steps.append({
            'step_id': step_id,
            'group': group.strip(),
            'title': item.get('title') if isinstance(item.get('title'), str)
            else '',
            'status': status,
            'required': required,
            'measurement': measurement,
            'required_kinds': _required_kinds(item.get('required_evidence')),
            'stop_conditions': [entry for entry in
                                (item.get('stop_conditions') or [])
                                if isinstance(entry, dict)]
            if isinstance(item.get('stop_conditions'), list) else [],
            'prerequisite_ids': _prerequisite_ids(item.get('prerequisites')),
            'sequence': index + 1,
        })
    return steps


def _plan_measurement(value, path, findings):
    if value is None:
        return None
    if not isinstance(value, dict):
        findings.error('SCHEMA_INVALID', '%s.measurement must be null or an '
                                         'object' % path)
        return None
    quantity = value.get('quantity')
    if quantity not in MEASURE_QUANTITIES:
        findings.error('SCHEMA_INVALID',
                       '%s.measurement.quantity must be one of %s, got %r'
                       % (path, ', '.join(MEASURE_QUANTITIES), quantity))
        quantity = None
    criterion = value.get('criterion_status')
    if criterion not in CRITERION_STATUSES:
        findings.error('SCHEMA_INVALID',
                       '%s.measurement.criterion_status must be one of %s, '
                       'got %r' % (path, ', '.join(CRITERION_STATUSES),
                                   criterion))
        criterion = 'undefined'
    span = value.get('range')
    normalised_span = None
    if span is not None:
        if not isinstance(span, dict):
            findings.error('SCHEMA_INVALID',
                           '%s.measurement.range must be null or an object'
                           % path)
        else:
            lower = span.get('min')
            upper = span.get('max')
            unit = span.get('unit')
            if lower is not None and not _is_number(lower):
                findings.error('SCHEMA_INVALID',
                               '%s.measurement.range.min must be a finite '
                               'number' % path)
            if upper is not None and not _is_number(upper):
                findings.error('SCHEMA_INVALID',
                               '%s.measurement.range.max must be a finite '
                               'number' % path)
            if unit is not None and not isinstance(unit, str):
                findings.error('SCHEMA_INVALID',
                               '%s.measurement.range.unit must be a string'
                               % path)
            normalised_span = {
                'min': float(lower) if _is_number(lower) else None,
                'max': float(upper) if _is_number(upper) else None,
                'unit': unit if isinstance(unit, str) else None,
            }
    return {
        'quantity': quantity,
        'criterion_status': criterion,
        'range': normalised_span,
        'point': value.get('point') if isinstance(value.get('point'), str)
        else None,
        'reference': value.get('reference')
        if isinstance(value.get('reference'), str) else None,
        'basis': value.get('basis') if isinstance(value.get('basis'), str)
        else None,
        'source_refs': [item for item in (value.get('source_refs') or [])
                        if isinstance(item, str)]
        if isinstance(value.get('source_refs'), list) else [],
    }


def _required_kinds(value):
    if not isinstance(value, list):
        return []
    kinds = []
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get('verifiable') is False:
            continue
        kind = item.get('kind')
        if isinstance(kind, str) and kind.strip():
            kinds.append(kind.strip())
    return kinds


def _prerequisite_ids(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict) or item.get('kind') != 'step':
            continue
        step_id = item.get('step_id')
        if isinstance(step_id, str) and step_id.strip():
            result.append(step_id.strip())
    return result


def _plan_domains(plan):
    domains = []
    seen = set()
    raw = plan.get('power_domains')
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            domain_id = item.get('id')
            if not isinstance(domain_id, str) or not domain_id.strip():
                continue
            domain_id = domain_id.strip()
            if domain_id in seen:
                continue
            seen.add(domain_id)
            domains.append({'id': domain_id,
                            'net': item.get('net')
                            if isinstance(item.get('net'), str) else None})
    if domains:
        return domains
    dag = plan.get('dag')
    if isinstance(dag, dict):
        domain_dag = dag.get('domains')
        nodes = domain_dag.get('nodes') if isinstance(domain_dag, dict) \
            else None
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                domain_id = node.get('id')
                if not isinstance(domain_id, str) or domain_id in seen:
                    continue
                seen.add(domain_id)
                domains.append({'id': domain_id,
                                'net': node.get('net')
                                if isinstance(node.get('net'), str) else None})
    return domains


def _plan_step_graph(plan, steps):
    known = {step['step_id'] for step in steps}
    # Dependency edges are taken both from the machine-readable DAG and from
    # the step ``prerequisites`` list: a hand-written/minimal plan may only
    # carry one of them, and a missing edge would silently drop STOP blocking.
    edges = []
    for step in steps:
        for prereq in step['prerequisite_ids']:
            if prereq in known and prereq != step['step_id']:
                edges.append({'from': prereq, 'to': step['step_id']})
    raw_edges = None
    dag = plan.get('dag')
    if isinstance(dag, dict):
        step_dag = dag.get('steps')
        if isinstance(step_dag, dict):
            raw_edges = step_dag.get('edges')
    if isinstance(raw_edges, list):
        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            source = item.get('from')
            target = item.get('to')
            if source in known and target in known and source != target:
                edges.append({'from': source, 'to': target})
    unique = []
    seen = set()
    for edge in edges:
        key = (edge['from'], edge['to'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    preferred = []
    raw_order = None
    if isinstance(dag, dict):
        step_dag = dag.get('steps')
        if isinstance(step_dag, dict):
            raw_order = step_dag.get('order')
    if isinstance(raw_order, list):
        for step_id in raw_order:
            if step_id in known and step_id not in preferred:
                preferred.append(step_id)
    for step in steps:
        if step['step_id'] not in preferred:
            preferred.append(step['step_id'])
    return unique, _topological([step['step_id'] for step in steps],
                                unique, preferred)


def _topological(step_ids, edges, preferred):
    rank = {step_id: index for index, step_id in enumerate(preferred)}
    for index, step_id in enumerate(step_ids):
        rank.setdefault(step_id, len(preferred) + index)
    indegree = {step_id: 0 for step_id in step_ids}
    adjacency = {step_id: [] for step_id in step_ids}
    for edge in edges:
        if edge['to'] not in indegree or edge['from'] not in indegree:
            continue
        indegree[edge['to']] += 1
        adjacency[edge['from']].append(edge['to'])
    ready = sorted((step_id for step_id in step_ids
                    if indegree[step_id] == 0),
                   key=lambda item: rank.get(item, 0))
    order = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
        ready.sort(key=lambda item: rank.get(item, 0))
    for step_id in step_ids:
        if step_id not in order:
            order.append(step_id)
    return order


# ---------------------------------------------------------------------------
# result document


def _result_meta(results, plan_meta, findings):
    meta = {'ok': False, 'schema': None, 'steps': [], 'by_id': {},
            'source_kind': 'unset', 'executed_by': None, 'binding': {}}
    if not isinstance(results, dict):
        findings.error('SCHEMA_INVALID', 'results must be a JSON object')
        return meta
    before = _error_count(findings)
    schema = results.get('schema')
    if schema == RESULT_SCHEMA:
        meta['schema'] = schema
    else:
        findings.error('SCHEMA_INVALID',
                       'results.schema must be %r, got %r'
                       % (RESULT_SCHEMA, schema))
    binding = results.get('plan_binding')
    if isinstance(binding, dict):
        meta['binding'] = binding
    else:
        findings.error('BINDING_MISMATCH',
                       'results.plan_binding object is required')
    executed_by = results.get('executed_by')
    if executed_by is None:
        meta['executed_by'] = None
    elif isinstance(executed_by, str):
        meta['executed_by'] = executed_by
    else:
        findings.error('SCHEMA_INVALID',
                       'results.executed_by must be a string')
    source_kind = results.get('source_kind', 'unset')
    if source_kind in SOURCES:
        meta['source_kind'] = source_kind
    else:
        findings.error('STATUS_INVALID',
                       'results.source_kind must be one of %s, got %r'
                       % (', '.join(SOURCES), source_kind))
    raw = results.get('results')
    if not isinstance(raw, list):
        findings.error('SCHEMA_INVALID',
                       'results.results must be an array')
        return meta
    if not raw:
        findings.error('SCHEMA_INVALID',
                       'results.results must contain at least one record')
    known_steps = set(plan_meta.get('step_by_id') or {})
    seen = set()
    for index, item in enumerate(raw):
        entry = _entry_meta(item, index, findings)
        if entry is None:
            continue
        if entry['step_id'] in seen:
            findings.error('SCHEMA_INVALID',
                           'duplicate result entry for step %r'
                           % entry['step_id'], step_id=entry['step_id'])
            continue
        seen.add(entry['step_id'])
        if known_steps and entry['step_id'] not in known_steps:
            findings.error('UNKNOWN_STEP_ID',
                           'result step %r is not part of this plan'
                           % entry['step_id'], step_id=entry['step_id'])
        meta['steps'].append(entry)
        meta['by_id'][entry['step_id']] = entry
    meta['ok'] = _error_count(findings) == before
    return meta


def _entry_meta(item, index, findings):
    path = 'results[%d]' % index
    if not isinstance(item, dict):
        findings.error('SCHEMA_INVALID', '%s must be an object' % path)
        return None
    step_id = item.get('step_id')
    if not isinstance(step_id, str) or not step_id.strip():
        findings.error('SCHEMA_INVALID',
                       '%s.step_id must be a non-empty string' % path)
        return None
    step_id = step_id.strip()
    before = _error_count(findings)
    status = item.get('status')
    if status not in STEP_STATUSES:
        findings.error('STATUS_INVALID',
                       '%s.status must be one of %s, got %r'
                       % (path, ', '.join(STEP_STATUSES), status),
                       step_id=step_id)
        status = 'unknown'
    source = item.get('source', 'unset')
    if source not in SOURCES:
        findings.error('STATUS_INVALID',
                       '%s.source must be one of %s, got %r'
                       % (path, ', '.join(SOURCES), source),
                       step_id=step_id)
        source = 'unset'
    stop_triggered = item.get('stop_triggered', False)
    if not isinstance(stop_triggered, bool):
        findings.error('SCHEMA_INVALID',
                       '%s.stop_triggered must be a boolean' % path,
                       step_id=step_id)
        stop_triggered = False
    instrument = _instrument_meta(item.get('instrument'), path, step_id,
                                  findings)
    measured = _measured_meta(item.get('measured'), path, step_id, findings)
    evidence = _evidence_meta(item.get('evidence'), path, step_id, findings)
    executed_by = item.get('executed_by', '')
    if executed_by is None:
        executed_by = ''
    if not isinstance(executed_by, str):
        findings.error('SCHEMA_INVALID',
                       '%s.executed_by must be a string' % path,
                       step_id=step_id)
        executed_by = ''
    executed_at = item.get('executed_at')
    if executed_at is not None:
        if not isinstance(executed_at, str) or not _timestamp_ok(executed_at):
            findings.error('SCHEMA_INVALID',
                           '%s.executed_at must be an ISO-8601 timestamp '
                           'with a timezone' % path, step_id=step_id)
            executed_at = None
    notes = item.get('notes', '')
    if notes is None:
        notes = ''
    if not isinstance(notes, str):
        findings.error('SCHEMA_INVALID',
                       '%s.notes must be a string' % path, step_id=step_id)
        notes = ''
    exceptions = item.get('exceptions', [])
    if not isinstance(exceptions, list):
        findings.error('SCHEMA_INVALID',
                       '%s.exceptions must be an array' % path,
                       step_id=step_id)
        exceptions = []
    else:
        cleaned = []
        for value in exceptions:
            if isinstance(value, str):
                cleaned.append(value)
            else:
                findings.error('SCHEMA_INVALID',
                               '%s.exceptions entries must be strings' % path,
                               step_id=step_id)
        exceptions = cleaned
    return {
        'step_id': step_id,
        'status': status,
        'source': source,
        'instrument': instrument,
        'measured': measured,
        'evidence': evidence,
        'executed_by': executed_by,
        'executed_at': executed_at,
        'stop_triggered': stop_triggered,
        'notes': notes,
        'exceptions': exceptions,
        'valid': _error_count(findings) == before,
    }


def _instrument_meta(value, path, step_id, findings):
    if value is None:
        return None
    if not isinstance(value, dict):
        findings.error('SCHEMA_INVALID',
                       '%s.instrument must be null or an object' % path,
                       step_id=step_id)
        return None
    model = value.get('model')
    equipment_id = value.get('equipment_id')
    settings = value.get('settings')
    if model is not None and not isinstance(model, str):
        findings.error('SCHEMA_INVALID',
                       '%s.instrument.model must be a string' % path,
                       step_id=step_id)
        model = None
    if equipment_id is not None and not isinstance(equipment_id, str):
        findings.error('SCHEMA_INVALID',
                       '%s.instrument.equipment_id must be a string' % path,
                       step_id=step_id)
        equipment_id = None
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        findings.error('SCHEMA_INVALID',
                       '%s.instrument.settings must be an object' % path,
                       step_id=step_id)
        settings = {}
    return {'model': model, 'equipment_id': equipment_id,
            'settings': settings}


def _measured_meta(value, path, step_id, findings):
    if value is None:
        return None
    if not isinstance(value, dict):
        findings.error('SCHEMA_INVALID',
                       '%s.measured must be null or an object' % path,
                       step_id=step_id)
        return None
    quantity = value.get('quantity')
    raw_value = value.get('value')
    unit = value.get('unit')
    at = value.get('at')
    valid = True
    if quantity not in MEASURE_QUANTITIES:
        findings.error('SCHEMA_INVALID',
                       '%s.measured.quantity must be one of %s, got %r'
                       % (path, ', '.join(MEASURE_QUANTITIES), quantity),
                       step_id=step_id)
        quantity = None
        valid = False
    if not _is_number(raw_value):
        findings.error('SCHEMA_INVALID',
                       '%s.measured.value must be a finite JSON number, '
                       'got %r' % (path, raw_value), step_id=step_id)
        valid = False
    if not isinstance(unit, str) or not unit.strip():
        findings.error('SCHEMA_INVALID',
                       '%s.measured.unit must be a non-empty string' % path,
                       step_id=step_id)
        unit = None
        valid = False
    if at is not None:
        if not isinstance(at, str) or not _timestamp_ok(at):
            findings.error('SCHEMA_INVALID',
                           '%s.measured.at must be an ISO-8601 timestamp '
                           'with a timezone' % path, step_id=step_id)
            at = None
    return {'quantity': quantity,
            'value': float(raw_value) if _is_number(raw_value) else None,
            'unit': unit, 'at': at, 'valid': valid}


def _evidence_meta(value, path, step_id, findings):
    if value is None:
        return []
    if not isinstance(value, list):
        findings.error('SCHEMA_INVALID',
                       '%s.evidence must be an array' % path,
                       step_id=step_id)
        return []
    records = []
    for index, item in enumerate(value):
        item_path = '%s.evidence[%d]' % (path, index)
        if not isinstance(item, dict):
            findings.error('SCHEMA_INVALID',
                           '%s must be an object' % item_path,
                           step_id=step_id)
            continue
        kind = item.get('kind')
        relative = item.get('path')
        digest = item.get('sha256')
        description = item.get('description', '')
        if not isinstance(kind, str) or not kind.strip():
            findings.error('SCHEMA_INVALID',
                           '%s.kind must be a non-empty string' % item_path,
                           step_id=step_id)
            kind = None
        if not isinstance(relative, str) or not relative.strip():
            findings.error('SCHEMA_INVALID',
                           '%s.path must be a non-empty string' % item_path,
                           step_id=step_id)
            continue
        if description is not None and not isinstance(description, str):
            findings.error('SCHEMA_INVALID',
                           '%s.description must be a string' % item_path,
                           step_id=step_id)
            description = ''
        if digest is not None:
            if not isinstance(digest, str) or not _HEX64.match(digest.strip()):
                findings.error('SCHEMA_INVALID',
                               '%s.sha256 must be a 64-hex SHA-256'
                               % item_path, step_id=step_id)
                digest = None
            else:
                digest = digest.strip().lower()
        records.append({
            'kind': kind.strip() if isinstance(kind, str) else None,
            'path': relative.strip(),
            'sha256': digest,
            'description': description or '',
            'verified': False,
            'problem': None,
            'rel_path': None,
        })
    return records


# ---------------------------------------------------------------------------
# binding


def _check_binding(plan_meta, result_meta, findings):
    expected = {
        'plan_sha256': plan_meta['hashes'].get('plan_sha256'),
        'input_sha256': plan_meta['input'].get('sha256'),
        'input_semantic_sha256': plan_meta['input'].get('semantic_sha256'),
        'revision': plan_meta['design'].get('revision'),
        'tool_version': plan_meta.get('tool_version'),
    }
    recorded = result_meta.get('binding') if isinstance(
        result_meta.get('binding'), dict) else {}
    checks = {}
    valid = True
    for key in _BINDING_KEYS:
        expected_value = expected.get(key)
        recorded_value = recorded.get(key)
        if not isinstance(recorded_value, str) or not recorded_value.strip():
            findings.error('BINDING_MISMATCH',
                           'results.plan_binding.%s is missing or not a '
                           'string' % key)
            checks[key] = {'expected': expected_value,
                           'recorded': recorded_value, 'match': False}
            valid = False
            continue
        recorded_value = recorded_value.strip()
        if expected_value is None:
            match = False
        elif key.endswith('sha256'):
            match = recorded_value.lower() == expected_value.lower()
        else:
            match = recorded_value == expected_value
        checks[key] = {'expected': expected_value,
                       'recorded': recorded_value, 'match': bool(match)}
        if match:
            continue
        valid = False
        if key == 'revision':
            findings.error('STALE_REVISION',
                           'result revision %r does not match plan revision '
                           '%r; results from an older board revision must not '
                           'be reused' % (recorded_value, expected_value))
        else:
            findings.error('BINDING_MISMATCH',
                           'results.plan_binding.%s %r does not match the '
                           'plan value %r'
                           % (key, recorded_value, expected_value))
    binding = {key: expected.get(key) for key in _BINDING_KEYS}
    binding['valid'] = valid
    binding['checks'] = checks
    return binding


# ---------------------------------------------------------------------------
# evidence


def _evidence_report(evidence_root, result_meta, findings):
    report = {
        'root': None,
        'root_state': None,
        'available': False,
        'declared': 0,
        'verified': 0,
        'unverified': 0,
        'missing': [],
        'mismatched': [],
        'escaped': [],
        'records': [],
    }
    root_path = None
    if evidence_root is not None:
        try:
            candidate = Path(evidence_root)
            exists = candidate.exists()
        except (OSError, RuntimeError, ValueError):
            candidate = None
            exists = False
        if not exists:
            # An absent evidence root only means "the evidence cannot be
            # checked"; it is not a contradiction inside the recorded result.
            findings.warning('EVIDENCE_ROOT_INVALID',
                             'evidence root %r does not exist; evidence '
                             'files are not verified' % str(evidence_root))
            report['root_state'] = 'missing'
        else:
            try:
                root_path = candidate.resolve()
            except (OSError, RuntimeError):
                root_path = None
            if root_path is None or not root_path.is_dir():
                findings.error('EVIDENCE_ROOT_INVALID',
                               'evidence root %r exists but is not a usable '
                               'directory' % str(evidence_root))
                report['root_state'] = 'not_a_directory'
                root_path = None
            else:
                report['root'] = str(root_path)
                report['available'] = True
                report['root_state'] = 'available'
    else:
        findings.warning('EVIDENCE_ROOT_REQUIRED',
                         'no --evidence-root supplied: evidence files cannot '
                         'be verified, so a hardware PASS is not possible')
        report['root_state'] = 'not_provided'

    for entry in result_meta.get('steps') or []:
        step_id = entry['step_id']
        for record in entry.get('evidence') or []:
            report['declared'] += 1
            item = {'step_id': step_id, 'kind': record.get('kind'),
                    'path': record.get('path'), 'sha256': record.get('sha256'),
                    'verified': False, 'problem': None}
            try:
                relative = check_attachment_path(record['path'],
                                                 'evidence path')
            except PlannerError as exc:
                findings.error('EVIDENCE_PATH_ESCAPE',
                               'evidence path %r: %s'
                               % (record['path'], exc.message),
                               step_id=step_id)
                record['problem'] = 'escape'
                item['problem'] = 'escape'
                report['escaped'].append({'step_id': step_id,
                                          'path': record['path']})
                report['unverified'] += 1
                report['records'].append(item)
                continue
            record['rel_path'] = relative
            if root_path is None:
                problem = {'not_provided': 'no_root',
                           'missing': 'root_missing',
                           'not_a_directory': 'root_invalid'}.get(
                               report.get('root_state'), 'root_invalid')
                record['problem'] = problem
                item['problem'] = problem
                report['unverified'] += 1
                report['records'].append(item)
                continue
            try:
                target = resolve_within(root_path, relative)
            except PlannerError as exc:
                findings.error('EVIDENCE_PATH_ESCAPE',
                               'evidence path %r resolves outside the '
                               'evidence root: %s'
                               % (record['path'], exc.message),
                               step_id=step_id)
                record['problem'] = 'escape'
                item['problem'] = 'escape'
                report['escaped'].append({'step_id': step_id,
                                          'path': record['path']})
                report['unverified'] += 1
                report['records'].append(item)
                continue
            if not target.is_file():
                # Evidence that cannot be found does not prove that the
                # document is contradictory: the step simply cannot pass.
                findings.warning('EVIDENCE_FILE_MISSING',
                                 'declared evidence %r does not exist under '
                                 'the evidence root; the step cannot pass'
                                 % relative, step_id=step_id)
                record['problem'] = 'missing_file'
                item['problem'] = 'missing_file'
                report['missing'].append({'step_id': step_id,
                                          'path': relative})
                report['unverified'] += 1
                report['records'].append(item)
                continue
            declared_sha = record.get('sha256')
            if declared_sha is None:
                findings.warning('EVIDENCE_HASH_MISSING',
                                 'evidence %r has no declared sha256; it '
                                 'cannot be verified' % relative,
                                 step_id=step_id)
                record['problem'] = 'missing_hash'
                item['problem'] = 'missing_hash'
                report['unverified'] += 1
                report['records'].append(item)
                continue
            actual = sha256_file(target)
            if actual.lower() != declared_sha.lower():
                findings.error('EVIDENCE_HASH_MISMATCH',
                               'evidence %r sha256 %s does not match the '
                               'declared %s'
                               % (relative, actual, declared_sha),
                               step_id=step_id)
                record['problem'] = 'hash'
                item['problem'] = 'hash'
                item['actual_sha256'] = actual
                report['mismatched'].append({'step_id': step_id,
                                              'path': relative,
                                              'recorded': declared_sha,
                                              'actual': actual})
                report['unverified'] += 1
                report['records'].append(item)
                continue
            record['verified'] = True
            record['problem'] = None
            item['verified'] = True
            report['verified'] += 1
            report['records'].append(item)
    return report


# ---------------------------------------------------------------------------
# per-step evaluation


def _evaluate_step(step, entry, findings):
    ev = {
        'step_id': step['step_id'],
        'group': step['group'],
        'title': step['title'],
        'sequence': step['sequence'],
        'required': step['required'],
        'plan_status': step['status'],
        'status': None,
        'source': None,
        'verdict': 'unknown',
        'outcome': 'unknown',
        'findings': [],
        'messages': [],
        'measurement': None,
        'evidence': {'required_kinds': list(step['required_kinds']),
                     'present_kinds': [], 'missing_kinds': [],
                     'count': 0, 'verified': False},
        'instrument_present': False,
        'stop': False,
        'blocked': False,
        'invalidated': False,
        'synthetic': False,
        'domains': [],
        'notes': '',
    }

    if step['status'] != STATUS_READY:
        if step['required']:
            ev['outcome'] = 'blocked'
            _flag(ev, findings, 'PLAN_STEP_BLOCKED',
                  '计划本身把该必需步骤标记为 %r，未执行前不能视为通过'
                  % step['status'])
            if entry is not None and entry.get('status') == 'pass':
                _flag(ev, findings, 'PLAN_STEP_NOT_EXECUTABLE',
                      '结果为 pass，但计划把该步骤标记为 %r，二者矛盾'
                      % step['status'], severity='error')
                ev['outcome'] = 'invalid'
        else:
            ev['outcome'] = 'not_run'
        return _finish(ev)

    if entry is None:
        if step['required']:
            ev['outcome'] = 'unknown'
            _flag(ev, findings, 'RESULT_MISSING',
                  '必需步骤没有结果条目；缺失记录按 unknown 处理，不得默认正常')
        else:
            ev['outcome'] = 'not_run'
        return _finish(ev)

    ev['status'] = entry['status']
    ev['source'] = entry['source']
    ev['stop'] = bool(entry.get('stop_triggered'))
    ev['notes'] = entry.get('notes') or ''

    if not entry['valid']:
        ev['outcome'] = 'invalid'
        return _finish(ev)

    source = entry['source']
    status = entry['status']

    if source == 'synthetic':
        ev['synthetic'] = True
        ev['stop'] = False
        _flag(ev, findings, 'SYNTHETIC_RECORD',
              'synthetic 记录不是真实测量，不能作为硬件通过证据',
              severity='warning')
        ev['outcome'] = 'synthetic_pass' if status == 'pass' else 'unknown'
        return _finish(ev)

    if source == 'unset' and status in ('pass', 'fail'):
        _flag(ev, findings, 'STATUS_INVALID',
              'status=%r 但 source=unset：没有记录来源的结果不能成立' % status,
              severity='error')
        ev['outcome'] = 'invalid'
        return _finish(ev)

    if source == 'manual_declaration':
        _flag(ev, findings, 'SOURCE_NOT_REAL',
              'manual_declaration 只是人工声明，不是原始测量数据，不能作为通过'
              '证据（最多 needs_review）', severity='warning')
        if status == 'pass':
            ev['outcome'] = 'manual'
        elif status == 'fail':
            ev['outcome'] = 'fail' if ev['stop'] else 'manual'
        elif status == 'not_run':
            ev['outcome'] = 'not_run'
        elif status == 'blocked':
            ev['outcome'] = 'blocked'
        else:
            ev['outcome'] = 'unknown'
        return _finish(ev)

    # real_measurement (or unset/not_run style records)
    if ev['stop'] and status == 'pass':
        _flag(ev, findings, 'STATUS_INVALID',
              'stop_triggered=true 的结果不能同时是 pass（STOP 即终止本步）',
              severity='error')
        ev['outcome'] = 'invalid'
        return _finish(ev)
    if status != 'pass':
        ev['outcome'] = status
        if ev['stop']:
            _flag(ev, findings, 'STOP_TRIGGERED',
                  '结果声明已触发 STOP：依赖步骤必须被阻断')
        return _finish(ev)

    # -- a real pass claim: verify every machine-checkable requirement ----
    problems = []

    def problem(severity, code, detail):
        problems.append((severity, code, detail))

    instrument = entry.get('instrument')
    measurement = step['measurement']
    if isinstance(instrument, dict):
        ev['instrument_present'] = bool(
            (instrument.get('model') or '').strip()
            or (instrument.get('equipment_id') or '').strip())
    if measurement is not None and not ev['instrument_present']:
        problem('warning', 'INSTRUMENT_REQUIRED',
                'real_measurement 的定量步骤缺少 instrument.model/'
                'equipment_id')

    if measurement is not None:
        _check_measurement(step, entry, ev, problem)
    else:
        measured = entry.get('measured')
        if measured is not None:
            quantity = measured.get('quantity')
            unit = measured.get('unit')
            if quantity in MEASURE_QUANTITIES and unit:
                try:
                    to_canonical(measured['value'], unit, quantity)
                except UnitError as exc:
                    problem('error', 'UNIT_MISMATCH', str(exc))

    _check_evidence(step, entry, ev, problem)

    if not (entry.get('executed_by') or '').strip():
        problem('warning', 'MISSING_EXECUTION_METADATA',
                'real_measurement 的 pass 缺少 executed_by（执行人）')
    if not entry.get('executed_at'):
        problem('warning', 'MISSING_EXECUTION_METADATA',
                'real_measurement 的 pass 缺少 executed_at（带时区的执行时间）')

    for severity, code, detail in problems:
        _flag(ev, findings, code, detail, severity=severity)
    severities = {severity for severity, _code, _detail in problems}
    if 'error' in severities:
        ev['outcome'] = 'invalid'
    elif problems:
        ev['outcome'] = 'unknown'
    else:
        ev['outcome'] = 'pass_real'
    return _finish(ev)


def _check_measurement(step, entry, ev, problem):
    measurement = step['measurement']
    quantity = measurement['quantity']
    measured = entry.get('measured')
    ev['measurement'] = {
        'quantity': quantity,
        'expected_min': (measurement['range'] or {}).get('min'),
        'expected_max': (measurement['range'] or {}).get('max'),
        'unit': (measurement['range'] or {}).get('unit'),
        'measured_value': None,
        'measured_unit': None,
        'value_canonical': None,
        'in_range': None,
        'criterion_status': measurement['criterion_status'],
    }
    if not isinstance(measured, dict):
        problem('warning', 'MISSING_MEASUREMENT',
                '定量步骤 status=pass 但 measured 为空；没有读数不能判通过')
        return
    ev['measurement']['measured_value'] = measured.get('value')
    ev['measurement']['measured_unit'] = measured.get('unit')
    if measured.get('quantity') != quantity:
        problem('error', 'UNIT_MISMATCH',
                'measured.quantity=%r 与步骤测量量 %r 不一致'
                % (measured.get('quantity'), quantity))
        return
    try:
        value = to_canonical(measured['value'], measured['unit'], quantity)
    except UnitError as exc:
        problem('error', 'UNIT_MISMATCH', str(exc))
        return
    ev['measurement']['value_canonical'] = value

    span = measurement.get('range') or {}
    lower = _span_bound(span, 'min', quantity, problem)
    upper = _span_bound(span, 'max', quantity, problem)
    if lower is not None or upper is not None:
        in_range = True
        if lower is not None and value < lower:
            in_range = False
        if upper is not None and value > upper:
            in_range = False
        ev['measurement']['in_range'] = in_range
        if not in_range:
            problem('error', 'RANGE_VIOLATION',
                    '实测 %s %s（= %.6g %s）超出计划声明范围 %s–%s；'
                    'status=pass 与读数矛盾，不能判通过'
                    % (_fmt(measured.get('value')), measured.get('unit'),
                       value, _canonical_unit(quantity),
                       _fmt(lower), _fmt(upper)))

    criterion = measurement['criterion_status']
    if criterion in ('undefined', 'needs_interpretation'):
        interpretation = _accepted_interpretation(entry)
        if interpretation is not None:
            problem('warning', 'CRITERION_UNDEFINED',
                    '判据状态为 %r：存在已接受的人工解释，最多算 needs_review，'
                    '不判 PASS' % criterion)
        else:
            problem('warning', 'CRITERION_UNDEFINED',
                    '判据状态为 %r：不能自动判通过；需要人工解释并单独记录'
                    % criterion)
    elif criterion == 'defined' and lower is None and upper is None:
        problem('warning', 'CRITERION_UNDEFINED',
                'criterion_status=defined 但计划没有给出数值范围，不能自动判通过')

    stop_hit = _stop_threshold_hit(step, quantity, value)
    if stop_hit is not None:
        problem('error', 'STOP_TRIGGERED',
                '实测值满足计划声明的 STOP 条件 %r，但 status=pass；'
                'STOP 必须终止本步，不能判通过'
                % (stop_hit.get('code') or 'STOP'))


def _check_evidence(step, entry, ev, problem):
    records = entry.get('evidence') or []
    present = {record.get('kind') for record in records
               if isinstance(record.get('kind'), str)}
    missing = [kind for kind in step['required_kinds'] if kind not in present]
    ev['evidence'].update({
        'present_kinds': sorted(kind for kind in present if kind),
        'missing_kinds': missing,
        'count': len(records),
        'verified': bool(records) and all(record.get('verified')
                                          for record in records),
    })
    if not records:
        problem('warning', 'MISSING_EVIDENCE',
                'real_measurement 的 pass 没有任何证据记录')
        return
    if missing:
        problem('warning', 'MISSING_EVIDENCE',
                '缺少步骤要求的证据类型：%s' % ', '.join(missing))
    unverified = [record for record in records
                  if not record.get('verified')]
    if not unverified:
        return
    problems = {record.get('problem') for record in unverified}
    if problems & {'escape', 'hash'}:
        # A path that escapes the root or a digest that contradicts the file
        # is a structural inconsistency: the recorded document cannot be
        # trusted, so the verdict is INVALID.
        problem('error', 'EVIDENCE_UNVERIFIED',
                '证据无法校验（路径越界/哈希不符），pass 不能成立')
    elif 'missing_file' in problems:
        missing_paths = [record.get('rel_path') or record.get('path')
                         for record in unverified
                         if record.get('problem') == 'missing_file']
        problem('warning', 'EVIDENCE_FILE_MISSING',
                '证据文件在 evidence root 下不存在：%s；该步不能判 pass'
                % ', '.join(path for path in missing_paths if path))
    elif 'no_root' in problems:
        problem('warning', 'EVIDENCE_UNVERIFIED',
                '未提供 --evidence-root，证据文件未校验，不能判 PASS')
    elif 'root_missing' in problems:
        problem('warning', 'EVIDENCE_UNVERIFIED',
                'evidence root 不存在，证据文件未校验，不能判 PASS')
    elif 'root_invalid' in problems:
        problem('warning', 'EVIDENCE_UNVERIFIED',
                'evidence root 不是可用目录，证据文件未校验，不能判 PASS')
    else:
        problem('warning', 'EVIDENCE_UNVERIFIED',
                '证据未声明 sha256，无法核对文件内容')


def _span_bound(span, key, quantity, problem):
    value = span.get(key)
    if not _is_number(value):
        return None
    unit = span.get('unit')
    if not unit:
        return float(value)
    try:
        return to_canonical(value, unit, quantity)
    except UnitError as exc:
        problem('error', 'UNIT_MISMATCH',
                'plan measurement.range.%s 单位无法换算：%s' % (key, exc))
        return None


def _stop_threshold_hit(step, quantity, value):
    for item in step.get('stop_conditions') or []:
        code = (item.get('code') or '').upper()
        threshold = item.get('threshold')
        if not isinstance(threshold, dict):
            continue
        if threshold.get('quantity') != quantity:
            continue
        if not any(tag in code for tag in ('ABSOLUTE', 'LIMIT', 'POLICY')):
            continue
        try:
            limit = to_canonical(threshold.get('value'),
                                 threshold.get('unit'), quantity)
        except (UnitError, TypeError, ValueError):
            continue
        if value >= limit:
            return item
    return None


def _accepted_interpretation(entry):
    interpretation = entry.get('interpretation')
    if isinstance(interpretation, dict) \
            and interpretation.get('accepted') is True:
        text = interpretation.get('text')
        if isinstance(text, str) and text.strip():
            return interpretation
    notes = entry.get('notes') or ''
    for exception in entry.get('exceptions') or []:
        if exception.strip().lower().startswith(
                'accepted_manual_interpretation') and notes.strip():
            return {'accepted': True, 'text': notes}
    return None


def _finish(ev):
    outcome = ev.get('outcome')
    ev['verdict'] = _OUTCOME_TO_VERDICT.get(outcome, 'unknown')
    ev['blocked'] = ev['verdict'] == 'blocked'
    ev['invalidated'] = ev['verdict'] == 'invalidated'
    return ev


def _flag(ev, findings, code, detail, *, severity='warning'):
    if code not in ev['findings']:
        ev['findings'].append(code)
    ev['messages'].append(detail)
    findings.add(code, detail, step_id=ev['step_id'], severity=severity)


# ---------------------------------------------------------------------------
# dependency propagation


def _propagate(plan_meta, evaluations, findings):
    by_id = {ev['step_id']: ev for ev in evaluations}
    predecessors = {}
    for edge in plan_meta.get('edges') or []:
        predecessors.setdefault(edge['to'], []).append(edge['from'])
    for step_id in plan_meta.get('order') or []:
        ev = by_id.get(step_id)
        if ev is None:
            continue
        bad = [by_id[parent] for parent in predecessors.get(step_id, [])
               if parent in by_id and by_id[parent]['verdict'] != 'pass']
        if not bad:
            continue
        if ev['outcome'] in ('synthetic_pass', 'synthetic_other'):
            # Synthetic records are not real pass/fail evidence; they neither
            # invalidate a real dependent nor get invalidated themselves.
            continue
        if ev['outcome'] == 'pass_real':
            stopped = any(parent.get('stop') or parent['outcome'] == 'fail'
                          for parent in bad)
            ev['outcome'] = 'invalidated'
            ev['findings'].append('INVALIDATED_BY_STOP' if stopped
                                  else 'DEPENDENCY_BLOCKED')
            _flag(
                ev, findings,
                'INVALIDATED_BY_STOP' if stopped else 'DEPENDENCY_BLOCKED',
                ('前置步骤 %s 未通过或已触发 STOP，本步记录的通过结果作废'
                 if stopped else
                 '前置步骤 %s 未通过，本步记录不能视为通过')
                % ', '.join(parent['step_id'] for parent in bad),
                severity='warning')
            _finish(ev)
        elif ev['outcome'] in ('fail', 'invalid', 'blocked', 'invalidated'):
            continue
        else:
            ev['outcome'] = 'blocked'
            _flag(ev, findings, 'DEPENDENCY_BLOCKED',
                  '前置步骤 %s 未 pass，本步不得执行/不得判定为通过'
                  % ', '.join(parent['step_id'] for parent in bad),
                  severity='warning')
            _finish(ev)


def _annotate_domains(plan_meta, evaluations):
    domains = plan_meta.get('domains') or []
    for ev in evaluations:
        text = '%s %s' % (ev['step_id'], ev['title'] or '')
        measurement = ev.get('measurement') or {}
        if measurement.get('unit'):
            text += ' %s' % measurement.get('unit')
        matched = []
        for domain in domains:
            domain_id = domain.get('id')
            net = domain.get('net')
            if domain_id and domain_id in _tokens(text):
                matched.append(domain_id)
            elif net and net in text:
                matched.append(domain_id)
        ev['domains'] = matched


def _tokens(text):
    for separator in ('-', ':', '/', ' ', '(', ')', ','):
        text = text.replace(separator, ' ')
    return set(text.split())


# ---------------------------------------------------------------------------
# verdict, counts and range reports


def _verdict(findings, evaluations, evidence_report):
    if findings.has_errors:
        return 'INVALID'
    required = [ev for ev in evaluations if ev['required']]
    required_ready = [ev for ev in required
                      if ev['plan_status'] == STATUS_READY]
    required_not_ready = [ev for ev in required
                          if ev['plan_status'] != STATUS_READY]
    stopped = any(ev.get('stop') for ev in evaluations)
    failed = [ev for ev in evaluations if ev['outcome'] == 'fail']
    if stopped or failed:
        return 'FAIL'
    invalidated = any(ev['outcome'] == 'invalidated' for ev in evaluations)
    # ``pass_real`` already implies a verified evidence file, a matching
    # measurement and execution metadata for every required ready step, so the
    # PASS guard only needs the structural conditions here.
    all_real = bool(required_ready) and all(
        ev['outcome'] == 'pass_real' for ev in required_ready)
    evidence_ok = (evidence_report.get('available')
                   and evidence_report.get('declared', 0) > 0)
    if (all_real and evidence_ok and not required_not_ready
            and not invalidated):
        return 'PASS'
    all_synthetic = bool(required_ready) and all(
        ev['outcome'] == 'synthetic_pass' for ev in required_ready)
    if (all_synthetic and not required_not_ready and not invalidated
            and not stopped):
        return 'SYNTHETIC_ONLY'
    return 'INCOMPLETE'


def _counts(evaluations):
    counts = {key: 0 for key in ('total', 'pass', 'fail', 'unknown',
                                 'blocked', 'not_run', 'invalid',
                                 'invalidated', 'synthetic')}
    counts['total'] = len(evaluations)
    for ev in evaluations:
        if ev['verdict'] in counts:
            counts[ev['verdict']] += 1
        if ev['outcome'] == 'synthetic_pass':
            counts['synthetic'] += 1
    required = [ev for ev in evaluations if ev['required']]
    required_ready = [ev for ev in required
                      if ev['plan_status'] == STATUS_READY]
    counts['required_total'] = len(required)
    counts['required_ready'] = len(required_ready)
    counts['required_pass'] = sum(1 for ev in required
                                  if ev['verdict'] == 'pass')
    counts['completion_ratio'] = (
        round(counts['pass'] / counts['total'], 4) if counts['total'] else 0.0)
    counts['required_completion_ratio'] = (
        round(counts['required_pass'] / len(required), 4)
        if required else 0.0)
    # Backwards-compatible alias used by some frozen fixtures/report readers.
    counts['failed'] = counts['fail']
    return counts


def _empty_bucket():
    return {'total': 0, 'pass': 0, 'fail': 0, 'unknown': 0, 'blocked': 0,
            'not_run': 0, 'invalid': 0, 'invalidated': 0,
            'required_total': 0, 'required_pass': 0,
            'completion_ratio': 0.0}


def _accumulate(bucket, ev):
    bucket['total'] += 1
    if ev['verdict'] in bucket:
        bucket[ev['verdict']] += 1
    if ev['required']:
        bucket['required_total'] += 1
        if ev['verdict'] == 'pass':
            bucket['required_pass'] += 1


def _finish_bucket(bucket):
    bucket['completion_ratio'] = (
        round(bucket['pass'] / bucket['total'], 4) if bucket['total'] else 0.0)
    return bucket


def _group_report(evaluations):
    buckets = {key: _empty_bucket() for key in _GROUP_KEYS}
    for ev in evaluations:
        group = ev['group'] or 'unknown'
        bucket = buckets.setdefault(group, _empty_bucket())
        _accumulate(bucket, ev)
    result = []
    for key in sorted(buckets, key=lambda item: (GROUP_ORDER.get(item, 99),
                                                 item)):
        bucket = _finish_bucket(buckets[key])
        entry = {'group': key}
        entry.update(bucket)
        result.append(entry)
    return result


def _domain_report(plan_meta, evaluations):
    buckets = {}
    nets = {}
    for domain in plan_meta.get('domains') or []:
        buckets[domain['id']] = _empty_bucket()
        nets[domain['id']] = domain.get('net')
    for ev in evaluations:
        for domain_id in ev.get('domains') or []:
            bucket = buckets.setdefault(domain_id, _empty_bucket())
            nets.setdefault(domain_id, None)
            _accumulate(bucket, ev)
    result = []
    for domain_id in sorted(buckets):
        bucket = _finish_bucket(buckets[domain_id])
        entry = {'domain': domain_id, 'net': nets.get(domain_id)}
        entry.update(bucket)
        result.append(entry)
    return result


def _scope_status(plan):
    if isinstance(plan, dict) and isinstance(plan.get('scope'), dict):
        status = plan['scope'].get('status')
        if isinstance(status, str):
            return status
    return None


# ---------------------------------------------------------------------------
# markdown


def _render_markdown(report):
    lines = []

    def add(text=''):
        lines.append(text)

    binding = report.get('binding') or {}
    design = report.get('design') or {}
    counts = report.get('counts') or {}
    verdict = report.get('verdict')
    add('# 首板结果评估（离线一致性核查，不执行任何步骤）')
    add('')
    add('- 结论：**%s**（hardware_pass=%s）'
        % (verdict, 'true' if report.get('hardware_pass') else 'false'))
    add('- 计划 SHA-256：`%s`' % (binding.get('plan_sha256') or '—'))
    add('- 输入 SHA-256：`%s` / 语义 `%s`'
        % (binding.get('input_sha256') or '—',
           binding.get('input_semantic_sha256') or '—'))
    add('- 设计 revision：`%s`' % (design.get('revision') or '—'))
    add('- 绑定校验：%s'
        % ('通过' if binding.get('valid') else '**失败**'))
    add('- 结果执行人：%s；结果来源：`%s`'
        % (report.get('executed_by') or '—',
           report.get('source_kind') or '—'))
    add('- 评估时间：%s' % (report.get('generated_at') or '—'))
    add('- 完成率（仅报告，不替代结论）：%s/%s = %.1f%%'
        % (counts.get('pass', 0), counts.get('total', 0),
           float(counts.get('completion_ratio') or 0.0) * 100))
    add('')

    add('## 1. 统计（counts）')
    add('')
    add('| 项 | 数量 |')
    add('|---|---|')
    for key in ('total', 'pass', 'fail', 'unknown', 'blocked', 'not_run',
                'invalid', 'invalidated', 'synthetic', 'required_total',
                'required_ready', 'required_pass'):
        add('| %s | %s |' % (key, counts.get(key, 0)))
    add('')

    add('## 2. 按组统计（I1–I4）')
    add('')
    add('| 组 | 总数 | pass | fail | unknown | blocked | not_run | invalid '
        '| invalidated | 必需通过 |')
    add('|---|---|---|---|---|---|---|---|---|---|')
    for group in report.get('groups') or []:
        add('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s/%s |'
            % (group['group'], group['total'], group['pass'], group['fail'],
               group['unknown'], group['blocked'], group['not_run'],
               group['invalid'], group['invalidated'], group['required_pass'],
               group['required_total']))
    add('')

    add('## 3. 电源域统计')
    add('')
    domains = report.get('domains') or []
    if domains:
        add('| 电源域 | 网络 | 总数 | pass | fail | unknown | blocked | '
            'not_run | invalid |')
        add('|---|---|---|---|---|---|---|---|---|')
        for domain in domains:
            add('| %s | %s | %s | %s | %s | %s | %s | %s | %s |'
                % (domain['domain'], domain.get('net') or '—',
                   domain['total'], domain['pass'], domain['fail'],
                   domain['unknown'], domain['blocked'], domain['not_run'],
                   domain['invalid']))
    else:
        add('（计划未声明电源域）')
    add('')

    add('## 4. 证据校验结果')
    add('')
    evidence = report.get('evidence') or {}
    add('- 证据根：%s' % (evidence.get('root') or '未提供/不可用'))
    root_state = evidence.get('root_state')
    if root_state and root_state != 'available':
        labels = {'not_provided': '未提供 --evidence-root',
                  'missing': 'evidence root 不存在',
                  'not_a_directory': 'evidence root 不是目录'}
        add('- 证据根状态：%s（证据不可校验，相关步骤不能判 pass）'
            % labels.get(root_state, root_state))
    add('- 声明证据数：%s；校验通过：%s；未通过/未校验：%s'
        % (evidence.get('declared', 0), evidence.get('verified', 0),
           evidence.get('unverified', 0)))
    if evidence.get('missing'):
        add('- 文件缺失：%s' % '；'.join(
            '%s:%s' % (item['step_id'], item['path'])
            for item in evidence['missing']))
    if evidence.get('mismatched'):
        add('- SHA-256 不符：%s' % '；'.join(
            '%s:%s' % (item['step_id'], item['path'])
            for item in evidence['mismatched']))
    if evidence.get('escaped'):
        add('- 路径越界：%s' % '；'.join(
            '%s:%s' % (item['step_id'], item['path'])
            for item in evidence['escaped']))
    add('')

    add('## 5. 被阻断/失效步骤')
    add('')
    blocked = [ev for ev in report.get('steps') or []
               if ev['verdict'] in ('blocked', 'invalidated', 'invalid')]
    if blocked:
        for ev in blocked:
            reason = ev['messages'][-1] if ev['messages'] else ''
            add('- `%s` %s：%s' % (ev['step_id'], ev['verdict'], reason))
    else:
        add('（无）')
    add('')

    add('## 6. NOT RUN 声明')
    add('')
    not_run = [ev for ev in report.get('steps') or []
               if ev['verdict'] == 'not_run']
    if not_run:
        add('以下步骤被记录为 not_run，一律不视为通过：')
        for ev in not_run:
            add('- `%s` %s' % (ev['step_id'], ev['title'] or ''))
    else:
        add('（没有记录为 not_run 的步骤；但 unknown/blocked 步骤同样不视为通过。）')
    add('')
    add('本评估不执行任何步骤：工具没有连接仪器、没有上电、没有烧录、没有运行'
        '任何命令；PASS 只表示所记录的结果在文档层面一致且证据可校验。')
    add('')

    add('## 7. 关键发现（findings）')
    add('')
    findings = report.get('findings') or []
    if findings:
        add('| 级别 | 代码 | 步骤 | 说明 |')
        add('|---|---|---|---|')
        for item in findings:
            add('| %s | `%s` | %s | %s |'
                % (item['severity'], item['code'],
                   item.get('step_id') or '—', _cell(item.get('detail'))))
    else:
        add('（无）')
    add('')

    add('## 8. 本评估不证明的内容')
    add('')
    add('- 不是硬件、安规、EMC、温升、可靠性或量产一致性的合格结论。')
    add('- synthetic / manual_declaration / not_run / unknown 记录永远不构成'
        '真机通过证据。')
    add('- 单点、单温、单样品的结果不得外推；未覆盖项必须单独列出。')
    add('- 完成率、分组统计只用于定位，不得用来替代 verdict。')
    add('')
    return '\n'.join(lines) + '\n'


def _cell(value):
    text = '' if value is None else str(value)
    return text.replace('|', '\\|').replace('\n', ' ')


# ---------------------------------------------------------------------------
# helpers


def _is_number(value):
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value))


def _timestamp_ok(value):
    try:
        parse_timestamp(value, 'timestamp')
        return True
    except PlannerError:
        return False


def _canonical_unit(quantity):
    from .units import CANONICAL_UNITS
    return CANONICAL_UNITS.get(quantity, '')


def _fmt(value):
    if value is None:
        return '—'
    if isinstance(value, float):
        return '%.6g' % value
    return str(value)
