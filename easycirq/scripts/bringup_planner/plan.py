"""Plan assembly.

Generation order: normalised input -> scope gate -> domain DAG -> capability
generators (I1..I5) -> deterministic step order -> gap/unknown summary -> plan
hashes.  Generation is pure: no instrument, network, shell or EDA access.
"""
from __future__ import annotations

from . import (PLAN_SCHEMA, TOOL_NAME, TOOL_VERSION)
from . import dag as dag_module
from . import evaluate as evaluate_module
from . import faults, interface_tests, measurements, poweroff, powerup
from .model import PlanContext
from .scope import assess_scope
from .steps import STATUS_BLOCKED, STATUS_READY, STATUS_UNSUPPORTED, \
    finalize_steps
from .util import iso_now, semantic_sha256


def generate_plan(model):
    """Return the full plan document (without rendering)."""
    ctx = PlanContext(model)
    scope = assess_scope(model)
    ctx.scope = scope
    ctx.dag = dag_module.build_domain_graph(model['power_domains'])
    ctx.supply_conflicts = dag_module.supply_conflicts(
        model['power_domains'], model['assemblies'], model['interfaces'])

    if scope['status'] in ('supported', 'needs_information'):
        poweroff.build(ctx)
        powerup.build(ctx, ctx.dag)
        measurements.build(ctx)
        interface_tests.build(ctx)
        faults.build(ctx)
    else:
        ctx.add_gap('SCOPE_BLOCKED',
                    'Plan generation',
                    'No powered steps were generated because the declared '
                    'design is outside the first-release scope or needs a '
                    'specialist: %s'
                    % '; '.join(scope['excluded']),
                    needed=['specialist review of the safe operating envelope'],
                    severity='blocking')

    steps = finalize_steps(ctx.steps)
    step_graph = dag_module.build_step_graph(steps)
    if step_graph['missing_prerequisites']:
        for item in step_graph['missing_prerequisites']:
            ctx.add_gap('STEP_PREREQUISITE_MISSING', item['step'],
                        'step %r references unknown prerequisite %r'
                        % (item['step'], item['missing']), severity='blocking')
    for cycle in step_graph['cycles']:
        ctx.add_gap('STEP_DAG_CYCLE', 'step prerequisites',
                    'step prerequisite cycle: %s' % ' -> '.join(cycle),
                    severity='blocking')

    design = {
        'project': model['project']['name'],
        'revision': model['project']['revision'],
        'source_snapshot_hash': model['project']['source_snapshot_hash'],
        'bom_version': model['project']['bom_version'],
        'assembly_version': model['project']['assembly_version'],
    }
    summary = summarize(steps, ctx)
    plan = {
        'schema': PLAN_SCHEMA,
        'generator': TOOL_NAME,
        'tool_version': TOOL_VERSION,
        'generated_at': iso_now(),
        'input': {
            'path': model.get('source_path'),
            'sha256': model['raw_sha256'],
            'semantic_sha256': model['semantic_sha256'],
            'completeness': model['completeness'],
            'declared_completeness': model['input_completeness_declared'],
        },
        'design': design,
        'scope': scope,
        'power_domains': model['power_domains'],
        'dag': {
            'domains': ctx.dag,
            'steps': {
                'order': step_graph['order'],
                'edges': step_graph['edges'],
                'cycles': step_graph['cycles'],
                'missing_prerequisites':
                    step_graph['missing_prerequisites'],
                'acyclic': step_graph['acyclic'],
            },
        },
        'supply_conflicts': ctx.supply_conflicts,
        'steps': steps,
        'fault_trees': ctx.trees,
        'gaps': ctx.gaps,
        'unknowns': ctx.unknowns,
        'equipment_gaps': ctx.equipment_gaps,
        'summary': summary,
        'hashes': {},
        'notes': {
            'execution': 'manual_only',
            'not_proven': [
                'no instrument was connected and no board was powered',
                'a generated plan is not a hardware, safety, EMC or thermal '
                'qualification',
                'synthetic result records can never become a real-hardware '
                'PASS',
            ],
        },
    }
    plan['hashes']['plan_sha256'] = plan_semantic_hash(plan)
    plan['hashes']['output_sha256'] = None
    return plan


def plan_semantic_hash(plan):
    """Hash the plan content without volatile fields or raw-file noise.

    Re-ordering input objects and equivalent unit conversions do not change
    this hash (the normalised semantic input hash is stable); a revision
    change does.
    """
    clone = dict(plan)
    clone.pop('generated_at', None)
    clone.pop('hashes', None)
    clone['input'] = {key: value for key, value in
                      (clone.get('input') or {}).items()
                      if key not in ('path', 'sha256')}
    clone['notes'] = {'execution': 'manual_only'}
    return semantic_sha256(clone)


def summarize(steps, ctx):
    by_status = {}
    by_group = {}
    for step in steps:
        by_status[step['status']] = by_status.get(step['status'], 0) + 1
        group = step['group']
        bucket = by_group.setdefault(group, {'total': 0, 'ready': 0,
                                             'blocked': 0, 'required': 0})
        bucket['total'] += 1
        if step['status'] == STATUS_READY:
            bucket['ready'] += 1
        elif step['status'] == STATUS_BLOCKED:
            bucket['blocked'] += 1
        if step['required']:
            bucket['required'] += 1
    return {
        'steps_total': len(steps),
        'steps_ready': by_status.get(STATUS_READY, 0),
        'steps_blocked': by_status.get(STATUS_BLOCKED, 0),
        'steps_unsupported': by_status.get(STATUS_UNSUPPORTED, 0),
        'steps_advisory': by_status.get('advisory', 0),
        'required_steps': sum(1 for step in steps if step['required']),
        'by_status': by_status,
        'by_group': by_group,
        'gaps': len(ctx.gaps),
        'blocking_gaps': sum(1 for gap in ctx.gaps
                             if gap.get('severity') == 'blocking'),
        'unknowns': len(ctx.unknowns),
        'equipment_gaps': len(ctx.equipment_gaps),
        'fault_trees': len(ctx.trees),
        'scope_status': ctx.scope.get('status'),
        'energize_allowed': ctx.scope.get('energize_allowed', False),
    }


def evaluate(plan, results, evidence_root=None):
    """Facade for ``evaluate`` used by the CLI and tests."""
    return evaluate_module.evaluate(plan, results,
                                    evidence_root=evidence_root)
