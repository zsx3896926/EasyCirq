"""Report assembly (J6) and deterministic human-readable ECO handover.

This module is the only place that decides the overall status, merges the
unknown boundaries reported by every stage, and renders the human-readable
handover.  It performs no analysis of its own: propagation, evidence and
verification selection stay in their own modules so they can be tested alone.

Status is deliberately narrow (see ``change_impact.STATUSES``):

* ``no_change``           - identical snapshots, declared complete, no changes;
* ``planned_with_scope``  - an analysis and a plan exist, with stated limits;
* ``incomplete``          - truncated traversal, missing graph data, partial
                            snapshot, unresolvable difference or unresolved
                            unknown that affects selection;
* ``input_invalid``       - raised, never returned by ``analyze_input``.

There is no ``design_pass``: a completed analysis is not a passed board.
"""
from __future__ import annotations

from . import (
    NOT_RUN_ACTIONS,
    SCHEMA_ANALYSIS,
    SCHEMA_EXPLAIN,
    SCHEMA_PLAN,
    STATUS_INCOMPLETE,
    STATUS_NO_CHANGE,
    STATUS_PLANNED_WITH_SCOPE,
    TOOL_VERSION,
)
from . import canonical as canon
from . import evidence as evidence_mod
from . import propagate as propagate_mod
from . import verify_plan
from .classify import compare_declared_to_observed
from .errors import InputInvalid
from .graph import Graph
from .model import validate_model

EXECUTED_ACTIONS = ('offline_change_impact_analysis',)
NOT_RUN = list(NOT_RUN_ACTIONS)

_IMPACT_SEVERITY_GAP = 'gap'
_IMPACT_SEVERITY_LIMITATION = 'limitation'


# ---------------------------------------------------------------------------
# unknown entries
# ---------------------------------------------------------------------------

def unknown_entry(code, where, reason, *, change_ids=None, consequence=None,
                  severity=None, object_id=None):
    """One explicit unknown.  Nothing here is ever silently dropped."""
    entry = {
        'code': str(code),
        'where': str(where),
        'reason': str(reason),
        'change_ids': sorted(str(item) for item in (change_ids or [])),
        'consequence': consequence,
        'severity': severity,
    }
    if object_id is not None:
        entry['object'] = str(object_id)
    return entry


def _dedupe_unknown(entries):
    seen = set()
    result = []
    for entry in entries:
        key = canon.canonical_json(entry)
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return sorted(result, key=lambda item: (item.get('where', ''),
                                            item.get('code', ''),
                                            item.get('object', ''),
                                            item.get('reason', ''),
                                            canon.canonical_json(item)))


def _collect_unknown(model, classification, impacts, evidence_report, plan):
    entries = []
    for side in ('baseline', 'candidate'):
        snapshot = model.__dict__.get(side) or {}
        if not snapshot.get('complete'):
            entries.append(unknown_entry(
                'snapshot_incomplete', f'snapshot.{side}',
                'the snapshot does not declare complete coverage'
                + (f'; missing fields: {snapshot["missing_fields"]}'
                   if snapshot.get('missing_fields') else ''),
                consequence=('impact analysis is limited to the declared object '
                             'graph and snapshot scope; objects outside it are '
                             'not proven unaffected'),
                severity=_IMPACT_SEVERITY_GAP))
    for identity in model.model_scope.get('unknown_objects') or []:
        entries.append(unknown_entry(
            'unknown_object', 'model_scope', 'object is declared as unknown',
            object_id=identity,
            consequence='its state and impact are unknown, by declaration',
            severity=_IMPACT_SEVERITY_GAP))
    for item in classification.get('observed_not_declared') or []:
        entries.append(unknown_entry(
            'observed_not_declared', 'changes',
            'observed difference was not declared: '
            f'{item.get("object")}.{item.get("attribute")} '
            f'({item.get("before")!r} -> {item.get("after")!r})',
            consequence=('the declared change set does not cover the observed '
                         'difference; it is treated as an unauthorised, '
                         'unexpected change and is not silently allowed'),
            severity=_IMPACT_SEVERITY_GAP))
    for item in classification.get('declared_not_observed') or []:
        entries.append(unknown_entry(
            'declared_not_observed', 'changes',
            f'declared change {item.get("change_id")} for '
            f'{item.get("object")}.{item.get("attribute")} was not present in '
            f'the observed diff',
            change_ids=[item.get('change_id')],
            consequence='the declaration and the observation disagree',
            severity=_IMPACT_SEVERITY_GAP))
    for item in impacts.get('unknown') or []:
        entries.append(unknown_entry(
            item.get('code', 'propagation_unknown'), 'propagation',
            item.get('reason', 'impact could not be determined'),
            change_ids=item.get('change_ids'),
            object_id=item.get('object'),
            consequence=('not traversed or not declared is not the same as '
                         'unaffected'),
            severity=_IMPACT_SEVERITY_GAP))
    for item in evidence_report.get('unknown') or []:
        entries.append(unknown_entry(
            item.get('code', 'evidence_unknown'), 'evidence',
            item.get('reason', 'evidence could not be assessed'),
            consequence=('this prior evidence can be neither relied on nor '
                         'discarded automatically'),
            severity=_IMPACT_SEVERITY_LIMITATION))
    for item in plan.get('unknown') or []:
        entries.append(unknown_entry(
            item.get('code', 'verification_unknown'), 'verification_plan',
            item.get('reason', 'verification could not be fully selected'),
            change_ids=item.get('change_ids'),
            consequence='the verification plan is not complete',
            severity=_IMPACT_SEVERITY_GAP))
    if not model.check_order:
        entries.append(unknown_entry(
            'empty_verification_catalog', 'verification_catalog',
            'no verification check is declared',
            consequence=('every impacted object is a coverage gap; the tool will '
                         'not invent a check'),
            severity=_IMPACT_SEVERITY_GAP))
    if not model.observed_diff:
        entries.append(unknown_entry(
            'no_independent_observation', 'changes',
            'no independently observed diff was supplied',
            consequence=('the declared change list was not cross-checked against '
                         'measured differences'),
            severity=_IMPACT_SEVERITY_LIMITATION))
    if getattr(model, 'undeclared_difference', False):
        entries.append(unknown_entry(
            'undeclared_difference', 'changes',
            'the snapshots differ but no change is declared and no observed diff '
            'is supplied',
            consequence=('no impact can be attributed to a declared change; the '
                         'analysis is incomplete by construction'),
            severity=_IMPACT_SEVERITY_GAP))
    return _dedupe_unknown(entries)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def _snapshot_complete(model):
    return bool((model.baseline or {}).get('complete') and
                (model.candidate or {}).get('complete'))


def _status(model, classification, impacts, plan):
    if not model.changes and not model.observed_diff and \
            model.baseline['content_hash'] == model.candidate['content_hash']:
        return STATUS_NO_CHANGE
    if getattr(model, 'undeclared_difference', False):
        return STATUS_INCOMPLETE
    if impacts.get('truncated'):
        return STATUS_INCOMPLETE
    if impacts.get('unknown'):
        return STATUS_INCOMPLETE
    if classification.get('observed_not_declared'):
        return STATUS_INCOMPLETE
    if classification.get('declared_not_observed'):
        return STATUS_INCOMPLETE
    if not _snapshot_complete(model):
        return STATUS_INCOMPLETE
    if model.model_scope.get('unknown_objects'):
        return STATUS_INCOMPLETE
    if not model.check_order:
        return STATUS_INCOMPLETE
    return STATUS_PLANNED_WITH_SCOPE


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

def _sort_paths(paths):
    return sorted(paths or [], key=lambda item: (
        item.get('target', ''), item.get('impact', ''),
        item.get('path_id', ''), canon.canonical_json(item)))


def _sort_impacts(records):
    order = {'certain': 0, 'possible': 1, 'unknown': 2}
    return sorted(records or [], key=lambda item: (
        item.get('kind', ''), item.get('object', ''),
        order.get(item.get('confidence'), 9), canon.canonical_json(item)))


def _counts(impacts, evidence_report, plan):
    direct = [item for item in impacts.get('impacted_objects') or []
              if item.get('direct')]
    evidence_counts = evidence_report.get('counts') or {}
    return {
        'declared_changes': len(impacts.get('impact_paths') or []),
        'affected_objects': len(impacts.get('impacted_objects') or []),
        'directly_affected': len(direct),
        'required_checks': len(plan.get('required') or []),
        'conditional_checks': len(plan.get('conditional') or []),
        'optional_checks': len(plan.get('optional') or []),
        'blocked_checks': len(plan.get('blocked') or []),
        'approvals': len(plan.get('approvals') or []),
        'coverage_gaps': len(plan.get('coverage_gaps') or []),
        'evidence_invalidated': evidence_counts.get('invalidated', 0),
        'evidence_reusable': (evidence_counts.get('reusable_bound', 0) +
                              evidence_counts.get('reusable_with_assessment', 0)),
        'evidence_unknown': evidence_counts.get('unknown', 0),
        'unknown': None,  # filled by caller
    }


def analyze_model(model, *, input_sha256=None, budget=None):
    """Run the full J pipeline over an already validated model."""
    graph = Graph(model)
    classification = compare_declared_to_observed(model)
    effective_budget = dict(model.budget)
    if budget:
        for key in ('max_depth', 'max_paths', 'max_cost', 'max_checks'):
            if key in budget and budget[key] is not None:
                effective_budget[key] = budget[key]
    impacts = propagate_mod.propagate(model, graph, classification,
                                      budget=effective_budget)
    evidence_report = evidence_mod.assess(model, graph, impacts,
                                          analysis_time=model.analysis_time)
    plan = verify_plan.build_plan(model, graph, impacts, evidence_report,
                                  budget=effective_budget)
    status = _status(model, classification, impacts, plan)
    unknown = _collect_unknown(model, classification, impacts,
                               evidence_report, plan)
    counts = _counts(impacts, evidence_report, plan)
    counts['unknown'] = len(unknown)
    simulated = bool(model.simulated or
                     any(item.get('simulated') for item in evidence_report.get(
                         'assessments') or []) or
                     any(evidence.get('simulated') for evidence in model.evidence))
    report = {
        'schema': SCHEMA_ANALYSIS,
        'tool_version': TOOL_VERSION,
        'status': status,
        'target': {
            'project': model.project,
            'baseline': model.baseline,
            'candidate': model.candidate,
            'input_sha256': input_sha256,
            'model_fingerprint': model.fingerprint(),
        },
        'model_scope': model.model_scope,
        'changes': {
            'declared': classification['declared'],
            'declared_not_observed': classification['declared_not_observed'],
            'observed_not_declared': classification['observed_not_declared'],
            'unauthorized_declared': classification['unauthorized_declared'],
            'observation_available': classification['observation_available'],
            'comparison_complete': classification['comparison_complete'],
            'note': classification['note'],
        },
        'impact_paths': _sort_paths(impacts.get('impact_paths')),
        'impacted_objects': _sort_impacts(impacts.get('impacted_objects')),
        'evidence_assessments': {
            'assessments': sorted(evidence_report.get('assessments') or [],
                                  key=lambda item: item.get('evidence_id', '')),
            'unknown': _dedupe_unknown([
                unknown_entry(item.get('code', 'evidence_unknown'), 'evidence',
                              item.get('reason', ''),
                              consequence='prior evidence cannot be relied on')
                for item in evidence_report.get('unknown') or []]),
            'counts': evidence_report.get('counts') or {},
            'simulated_only': bool(evidence_report.get('simulated_only')),
            'notes': evidence_report.get('notes') or [],
        },
        'verification_plan': {
            'required': plan.get('required') or [],
            'conditional': plan.get('conditional') or [],
            'optional': plan.get('optional') or [],
            'blocked': plan.get('blocked') or [],
            'approvals': plan.get('approvals') or [],
            'selection': plan.get('selection') or {},
        },
        'coverage_gaps': plan.get('coverage_gaps') or [],
        'unknown': unknown,
        'cycles': impacts.get('cycles') or [],
        'budget': {
            'requested': effective_budget,
            'used': impacts.get('budget') or {},
        },
        'not_run': NOT_RUN,
        'executed': list(EXECUTED_ACTIONS),
        'simulated': simulated,
        'notes': _notes(model, classification, evidence_report, plan),
        'human_summary': {
            'status': status,
            'counts': counts,
            'must_read': _must_read(model, evidence_report, plan),
        },
    }
    return report


def _must_read(model, evidence_report, plan):
    lines = []
    for gap in (plan.get('coverage_gaps') or [])[:20]:
        lines.append(f"coverage gap: {gap.get('object')} / {gap.get('impact')}")
    blocked = [item for item in plan.get('blocked') or []]
    if blocked:
        lines.append(f'{len(blocked)} check(s) are blocked (host/manual or '
                     f'missing input) and were not run')
    if plan.get('approvals'):
        lines.append(f'{len(plan["approvals"])} declared approval point(s) need '
                     f'human sign-off')
    if evidence_report.get('simulated_only'):
        lines.append('all reusable evidence is simulated; it cannot stand in '
                     'for host or physical verification')
    if model.model_scope.get('unknown_objects'):
        lines.append('the model declares unknown objects; their impact is not '
                     'proven to be absent')
    return lines


def _notes(model, classification, evidence_report, plan):
    notes = [
        'suggestions are not applied automatically; this report is not an EDA '
        'write authorisation',
        'a completed analysis is not a passed board and not a manufacturing '
        'release',
        'unchanged dependencies only help where they are declared and verified; '
        'an absent edge is not proof of no impact',
    ]
    if not classification.get('observation_available'):
        notes.append('no independent diff was supplied; the declared change list '
                     'was not cross-checked against measured differences')
    if evidence_report.get('notes'):
        notes.extend(str(item) for item in evidence_report['notes'])
    selection = plan.get('selection') or {}
    if selection:
        notes.append('verification selection: '
                     f"{selection.get('algorithm', 'unknown')} within "
                     f"{canon.canonical_json(selection.get('budget', {}))}; "
                     f"not proven globally optimal")
    if model.baseline.get('source_type') == 'simulated_synthetic' or model.simulated:
        notes.append('this model is simulated/synthetic; it demonstrates the '
                     'analysis, not a real project')
    return notes


def analyze_input(data, *, input_sha256=None, where='input', budget=None):
    model = validate_model(data, where=where)
    return analyze_model(model, input_sha256=input_sha256, budget=budget)


def plan_payload(report):
    """``plan`` command payload: the verification plan with its binding."""
    return {
        'schema': SCHEMA_PLAN,
        'tool_version': TOOL_VERSION,
        'status': report['status'],
        'target': report['target'],
        'model_scope': report['model_scope'],
        'changes': report['changes'],
        'verification_plan': report['verification_plan'],
        'coverage_gaps': report['coverage_gaps'],
        'evidence_assessments': report['evidence_assessments'],
        'impacted_objects': report['impacted_objects'],
        'unknown': report['unknown'],
        'budget': report['budget'],
        'not_run': report['not_run'],
        'executed': report['executed'],
        'simulated': report['simulated'],
        'notes': report['notes'],
        'human_summary': report['human_summary'],
    }


# ---------------------------------------------------------------------------
# explain (J6)
# ---------------------------------------------------------------------------

def explain(report, *, object_id=None, change_id=None):
    """Filter a completed report down to one object or one change.

    The result keeps the full provenance of every retained path; it never
    re-derives analysis from a different model.
    """
    changes = report['changes']['declared']
    if change_id is not None:
        matches = [item for item in changes if item['change_id'] == change_id]
        if not matches:
            raise InputInvalid(f'change {change_id!r} is not a declared change '
                               f'in this report', code='unknown_change',
                               where='--change')
    object_ids = {item['object'] for item in changes}
    object_ids.update(item['object'] for item in report['impacted_objects'])
    for path in report['impact_paths']:
        object_ids.add(path.get('target'))
        for step in path.get('steps') or []:
            object_ids.add(step.get('from'))
            object_ids.add(step.get('to'))
    object_ids.discard(None)
    object_ids.discard('')
    if object_id is not None and object_id not in object_ids:
        raise InputInvalid(f'object {object_id!r} does not appear in this report',
                           code='unknown_object_for_explain', where='--object')
    paths = report['impact_paths']
    if change_id is not None:
        paths = [path for path in paths
                 if change_id in (path.get('change_ids') or [])]
    if object_id is not None:
        paths = [path for path in paths
                 if path.get('target') == object_id or
                 any(step.get('from') == object_id or step.get('to') == object_id
                     for step in path.get('steps') or [])]
    impacted = report['impacted_objects']
    if change_id is not None:
        impacted = [item for item in impacted
                    if change_id in (item.get('change_ids') or [])]
    if object_id is not None:
        impacted = [item for item in impacted if item['object'] == object_id]
    assessments = report['evidence_assessments']['assessments']
    if object_id is not None:
        assessments = [item for item in assessments
                       if object_id in ((item.get('coverage') or {})
                                        .get('objects') or [])]
    selected_changes = changes
    if change_id is not None:
        selected_changes = matches
    if object_id is not None:
        selected_changes = [item for item in selected_changes
                            if item['object'] == object_id]
    human_lines = _explain_lines(selected_changes, paths, impacted, assessments)
    return {
        'schema': SCHEMA_EXPLAIN,
        'tool_version': TOOL_VERSION,
        'status': report['status'],
        'target': report['target'],
        'selection': {'object': object_id, 'change': change_id},
        'changes': selected_changes,
        'impact_paths': _sort_paths(paths),
        'impacted_objects': _sort_impacts(impacted),
        'evidence_assessments': sorted(assessments,
                                       key=lambda item: item.get('evidence_id', '')),
        'unknown': report['unknown'],
        'not_run': report['not_run'],
        'human_lines': human_lines,
        'note': ('explanation of declared analysis; it does not authorise an '
                 'edit and is not a verification result'),
    }


def _explain_lines(changes, paths, impacted, assessments):
    lines = []
    for change in changes:
        lines.append(
            f"change {change.get('change_id')}: {change.get('kind')}"
            f"/{change.get('subtype')} on {change.get('object')}"
            f".{change.get('attribute')} {change.get('before')!r} -> "
            f"{change.get('after')!r}")
    for path in paths:
        chain = ' -> '.join(
            f"{step.get('from')} --{step.get('semantic')}--> {step.get('to')}"
            for step in path.get('steps') or [])
        lines.append(
            f"impact {path.get('target')}: {path.get('impact')} "
            f"[{path.get('confidence')}] rule={path.get('trigger_rule')} "
            f"stop={path.get('stop_reason')} changes="
            f"{','.join(path.get('change_ids') or [])}"
            + (f" via {chain}" if chain else ' (direct)'))
    for item in assessments:
        reuse = item.get('reuse') or {}
        lines.append(
            f"evidence {item.get('evidence_id')}: {item.get('status')}"
            + (f" reuse_basis={reuse.get('basis')}" if reuse else ''))
    return lines


# ---------------------------------------------------------------------------
# human-readable handover
# ---------------------------------------------------------------------------

_STATUS_TEXT = {
    STATUS_PLANNED_WITH_SCOPE: '已规划（附作用域与限制）',
    STATUS_INCOMPLETE: '分析不完整（存在未知/截断/缺覆盖）',
    STATUS_NO_CHANGE: '未发现声明范围内的变化',
}


def render_human(report):
    """Deterministic Markdown handover.  No timestamps, no guesses."""
    lines = []
    add = lines.append
    baseline = report['target']['baseline']
    candidate = report['target']['candidate']
    add('# ECO 变更影响分析与增量验证计划')
    add('')
    add(f"- 状态：`{report['status']}`（{_STATUS_TEXT.get(report['status'], '')}）")
    add(f"- 工具：change_impact {report['tool_version']}")
    add(f"- 工程：{report['target']['project'].get('name')}")
    add(f"- 基线：{baseline['revision']} / {baseline['content_hash']} "
        f"（{baseline['source_type']}，覆盖：{', '.join(baseline['snapshot_scope']) or '未声明'}）")
    add(f"- 候选：{candidate['revision']} / {candidate['content_hash']}")
    add(f"- 输入哈希：{report['target'].get('input_sha256') or '未提供'}")
    add(f"- 模型指纹：{report['target'].get('model_fingerprint')}")
    if report.get('simulated'):
        add('- 数据性质：**simulated/synthetic**，仅演示分析，不代表真实工程')
    counts = report['human_summary']['counts']
    add('')
    add('## 概览')
    add('')
    add(f"- 受影响对象 {counts['affected_objects']}（直接 {counts['directly_affected']}）")
    add(f"- 必做检查 {counts['required_checks']}，条件 {counts['conditional_checks']}，"
        f"可选 {counts['optional_checks']}，阻塞 {counts['blocked_checks']}")
    add(f"- 覆盖缺口 {counts['coverage_gaps']}，证据失效 {counts['evidence_invalidated']}，"
        f"可复用 {counts['evidence_reusable']}，未知 {counts['unknown']}")
    add('')
    add('## 源变更')
    add('')
    for change in report['changes']['declared']:
        add(f"- `{change['change_id']}` {change['kind']}/{change['subtype']}："
            f"{change['object']}.{change['attribute']} "
            f"{change['before']!r} → {change['after']!r}"
            f"（授权：{'是' if change.get('authorized') else '未声明'}）")
    if not report['changes']['declared']:
        add('- （无声明变更）')
    if report['changes']['observed_not_declared']:
        add('')
        add('### 未声明的实际差异（单列，不自动允许）')
        add('')
        for item in report['changes']['observed_not_declared']:
            add(f"- {item['object']}.{item['attribute']} "
                f"{item['before']!r} → {item['after']!r}")
    if report['changes']['declared_not_observed']:
        add('')
        add('### 声明但未观测到的差异')
        add('')
        for item in report['changes']['declared_not_observed']:
            add(f"- `{item['change_id']}` {item['object']}.{item['attribute']}")
    add('')
    add('## 受影响对象')
    add('')
    if not report['impacted_objects']:
        add('- （无）')
    for item in report['impacted_objects']:
        kinds = ', '.join(item.get('impacts') or [])
        add(f"- `{item['object']}`（{item.get('kind')}）：{kinds} "
            f"[{item.get('confidence')}]{' direct' if item.get('direct') else ''}"
            f" changes={','.join(item.get('change_ids') or [])}")
    add('')
    add('## 影响路径')
    add('')
    if not report['impact_paths']:
        add('- （无路径；这不等于无影响，见未知边界）')
    for path in report['impact_paths']:
        chain = ' → '.join(f"{step.get('from')}·{step.get('semantic')}"
                           for step in path.get('steps') or [])
        add(f"- `{path.get('target')}` {path.get('impact')} "
            f"[{path.get('confidence')}] rule={path.get('trigger_rule')} "
            f"stop={path.get('stop_reason')} changes="
            f"{','.join(path.get('change_ids') or [])}"
            + (f" via {chain}" if chain else ' (直接)'))
    add('')
    add('## 证据评估')
    add('')
    assessments = report['evidence_assessments']['assessments']
    if not assessments:
        add('- （无先前证据记录）')
    for item in assessments:
        add(f"- `{item.get('evidence_id')}` {item.get('check')}："
            f"**{item.get('status')}** valid_for={item.get('valid_for')}")
        for reason in item.get('reasons') or []:
            add(f"  - {reason.get('code')}：{reason.get('detail')}")
        reuse = item.get('reuse')
        if reuse:
            add(f"  - 复用依据：{reuse.get('basis')}；保留原捕获："
                f"{canon.canonical_json(reuse.get('preserved_capture') or {})}")
    add('')
    add('## 增量验证计划')
    add('')
    plan = report['verification_plan']
    for priority in ('required', 'conditional', 'optional', 'blocked'):
        add(f'### {priority}')
        add('')
        entries = plan.get(priority) or []
        if not entries:
            add('- （无）')
        for entry in entries:
            covered = ', '.join(
                f"{item.get('object')}/{item.get('impact')}"
                for item in entry.get('covered_impacts') or [])
            add(f"- `{entry.get('check')}` {entry.get('title')} "
                f"[{entry.get('kind')}, cost={entry.get('cost')}"
                f"{', mandatory' if entry.get('mandatory') else ''}] "
                f"覆盖：{covered or '—'}")
            for reason in entry.get('reasons') or []:
                add(f"  - {reason.get('code')}：{reason.get('detail', '')}")
            for blocked_reason in entry.get('blocked_reasons') or []:
                add(f"  - blocked：{blocked_reason}")
        add('')
    if plan.get('approvals'):
        add('### 行政审批点（独立于质量门禁）')
        add('')
        for entry in plan['approvals']:
            add(f"- `{entry.get('check')}` {entry.get('title')}")
        add('')
    add('## 覆盖缺口')
    add('')
    if not report['coverage_gaps']:
        add('- （无已识别缺口）')
    for gap in report['coverage_gaps']:
        add(f"- `{gap.get('object')}` / {gap.get('impact')}：{gap.get('reason')}")
    add('')
    add('## 未知边界')
    add('')
    if not report['unknown']:
        add('- （无显式未知；仍只代表声明模型内）')
    for item in report['unknown']:
        add(f"- [{item.get('where')}] {item.get('code')}：{item.get('reason')}"
            + (f"（后果：{item['consequence']}）" if item.get('consequence') else ''))
    if report.get('cycles'):
        add('')
        add('## 依赖环')
        add('')
        for cycle in report['cycles']:
            add(f"- {' → '.join(cycle)}")
    add('')
    add('## 计划选择')
    add('')
    selection = plan.get('selection') or {}
    add(f"- 算法：{selection.get('algorithm', 'n/a')}（不宣称全局最优）")
    add(f"- 预算：{canon.canonical_json(selection.get('budget', {}))}")
    add(f"- 已选成本：{selection.get('selected_cost')}，跳过可选："
        f"{selection.get('skipped_optional')}")
    add('')
    add('## 明确未执行')
    add('')
    for item in report['not_run']:
        add(f'- {item}')
    add('')
    add('## 说明')
    add('')
    for note in report['notes']:
        add(f'- {note}')
    add('')
    return '\n'.join(lines)
