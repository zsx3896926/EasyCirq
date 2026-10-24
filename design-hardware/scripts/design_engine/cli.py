"""Command line for the offline design engine.

Exit codes: 0 pass/no candidates, 1 review/blocked/mismatch, 2 invalid input.
The CLI never contacts the EDA and never writes a project.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import ENGINE_VERSION
from .adapters import build_ir
from .audit import audit
from .compare import compare_ir
from .ir import read_ir, summary, validate_ir, write_ir
from .labels import plan_label_moves, to_easyeda_moves, verify_plan
from .pack import pack_modules
from .pcb import audit_pcb, build_pcb_ir
from .router import route, validate_route
from .templates import load_templates


def _dump(value, path=None):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    if path:
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.write('\n')
    else:
        print(text)
    return text


def _load_input(args):
    if getattr(args, 'ir', None):
        return read_ir(args.ir), {'kind': 'ir', 'path': args.ir}
    if getattr(args, 'bundle', None):
        return build_ir(args.bundle), {'kind': 'bundle', 'path': args.bundle}
    raise ValueError('either --bundle or --ir is required')


def _reading_source(ir):
    source = ir.get('source') or {}
    return {
        'schema': ir.get('schema'),
        'project': source.get('project_name'),
        'project_uuid': source.get('project_uuid'),
        'page': source.get('page_name'),
        'document_uuid': source.get('document_uuid'),
        'files': source.get('files') or [],
    }


def command_ingest(args):
    ir = build_ir(args.bundle)
    validate_ir(ir)
    write_ir(ir, args.out)
    result = {'status': 'ok', 'out': args.out, 'summary': summary(ir)}
    if args.json:
        _dump(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


def command_audit(args):
    ir, source = _load_input(args)
    report = audit(ir)
    result = {
        'schema': 'design-engine-audit/v1',
        'engine_version': ENGINE_VERSION,
        'reading': _reading_source(ir),
        'summary': summary(ir),
        **report,
        'source': source,
    }
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        parts = sum(result['summary']['components'].values())
        print(f"工程: {result['reading'].get('project')} / {result['reading'].get('page')}")
        print(f"IR: {parts} 器件, {result['summary']['nets']} 网络, "
              f"{result['summary']['wires']} 导线, {result['summary']['net_labels']} 网络标签")
        print(f"结论: {result['status']} (hard={result['hard_count']}, advisory={result['advisory_count']})")
        for finding in result['findings']:
            print(f"  [{finding['scope']}] {finding['code']}: {finding['message']}")
        if result['coverage_issues']:
            print('覆盖不足: ' + ', '.join(result['coverage_issues']))
        print('电气已验证: 否；视觉已验证: 否')
    return 0 if result['status'] == 'pass' else 1


def command_plan(args):
    ir, source = _load_input(args)
    plan = plan_label_moves(ir)
    plan['source']['reading'] = source
    if args.out:
        _dump(plan, args.out)
    if args.json:
        _dump(plan)
    else:
        print(f"计划移动: {len(plan['operations'])}; 无法规划: {len(plan['unplanned'])}")
        for operation in plan['operations']:
            print(f"  {operation['designator']}.{operation['key']} "
                  f"({operation['from']['x']},{operation['from']['y']}) -> "
                  f"({operation['to']['x']},{operation['to']['y']}) [{operation['reason']}]")
        for item in plan['unplanned']:
            print(f"  未规划 {item['attribute_id']}: {item['reason']}")
        print(f"模拟后: {plan['after_simulation']['status']} "
              f"(hard={plan['after_simulation']['hard_count']})")
        print('eda_apply: NOT RUN')
    if args.moves_dir:
        os.makedirs(args.moves_dir, exist_ok=True)
        documents = to_easyeda_moves(plan, ir)
        for index, document in enumerate(documents, 1):
            path = os.path.join(args.moves_dir, f'move-{index:03d}-{document["primitiveId"]}.json')
            _dump(document, path)
        print(f'写入 {len(documents)} 个 attribute-move 参数文件: {args.moves_dir}', file=sys.stderr)
    return 0 if plan['after_simulation']['hard_count'] == 0 else 1


def command_verify(args):
    ir = read_ir(args.ir)
    with open(args.plan, encoding='utf-8-sig') as handle:
        plan = json.load(handle)
    result = verify_plan(ir, plan)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"校验: {result['status']}; 操作 {result['operations']}; "
              f"模拟后 {result['after_simulation']['status']} "
              f"(hard={result['after_simulation']['hard_count']})")
        for issue in result['issues']:
            print(f"  {issue['code']}: {issue}")
        print('eda_apply: NOT RUN')
    return 0 if result['status'] == 'match' and result['after_simulation']['hard_count'] == 0 else 1


def command_pcb_ingest(args):
    ir = build_pcb_ir(args.bundle)
    _dump(ir, args.out)
    if not args.quiet:
        print(f"PCB IR: {len(ir['components'])} 器件, "
              f"{sum(len(item['pads']) for item in ir['components'])} 焊盘, "
              f"{len(ir['tracks'])} 走线, {len(ir['vias'])} 过孔", file=sys.stderr)
    return 0


def command_pcb_audit(args):
    ir = build_pcb_ir(args.bundle)
    sch = read_ir(args.sch_ir) if args.sch_ir else None
    result = audit_pcb(ir, sch)
    result['reading'] = ir.get('source') or {}
    result['source'] = {'kind': 'pcb-bundle', 'path': args.bundle}
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"PCB: {result['metrics']['components']} 器件, {result['metrics']['pads']} 焊盘, "
              f"{result['metrics']['tracks']} 走线, {result['metrics']['vias']} 过孔")
        print(f"结论: {result['status']} (hard={result['hard_count']}, advisory={result['advisory_count']})")
        drc = result.get('drc') or {}
        print(f"DRC: total={drc.get('total')} counts={drc.get('counts')}")
        for finding in result['findings']:
            print(f"  [{finding['scope']}] {finding['code']}: {finding['message']}")
        if result['checks_skipped']:
            print('未检查: ' + '; '.join(result['checks_skipped']))
        print('电气已验证: 否；视觉已验证: 否')
    return 0 if result['status'] == 'pass' else 1


def _pair(value, label):
    parts = value.split(',')
    if len(parts) != 2:
        raise ValueError(f'{label}: x,y required')
    return (float(parts[0]), float(parts[1]))


def command_route(args):
    ir = read_ir(args.ir)
    start, end = _pair(args.start, '--start'), _pair(args.end, '--end')
    result = route(ir, start, end, args.net)
    result['validation'] = validate_route(ir, result, args.net,
                                          page=(ir.get('page') or {}).get('bbox'))
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"布线: {result['status']}; 长度 {result.get('length')}; 拐点 {result.get('turns')}")
        if result['validation']['issues']:
            for issue in result['validation']['issues']:
                print(f"  {issue['code']}: {issue}")
        print('电气已验证: 否')
    return 0 if result['status'] == 'routed' and result['validation']['valid'] else 1


def command_pack(args):
    ir = read_ir(args.ir)
    modules = ir.get('modules') or []
    if args.allow_groups:
        modules = (ir.get('groups') or []) + modules
    page = (ir.get('page') or {}).get('inner_bbox') or (ir.get('page') or {}).get('bbox')
    if not page:
        raise ValueError('IR page bbox is required')
    title = ((ir.get('page') or {}).get('title_block') or {}).get('bbox')
    result = pack_modules(modules, page, title_block=title, spacing=args.spacing,
                          allow_diagnostic_groups=args.allow_groups)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"装箱: {result['status']}; 页数 {result.get('page_count')}; "
              f"未解决 {len(result.get('unsolved') or [])}")
    return 0 if result['status'] == 'packed' else 1


def command_templates(args):
    templates = load_templates()
    if args.list:
        for identity, template in templates.items():
            print(f"{identity:20s} {template['title']} ({template['category']})")
        return 0
    result = {
        'status': 'ok',
        'schema': 'design-engine-templates/v1',
        'count': len(templates),
        'templates': [
            {'id': identity, 'title': template['title'], 'category': template['category'],
             'roles': template['required_roles'], 'blocks': len(template['blocks'])}
            for identity, template in sorted(templates.items())
        ],
        'validated': True,
        'eeada_instances': 'NOT RUN',
        'note': 'template data is design-method level; no instance was drawn in an EDA',
    }
    _dump(result, args.out)
    return 0


def command_compare(args):
    before, after = read_ir(args.before), read_ir(args.after)
    result = compare_ir(before, after)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        identity = result['identity']
        print(f"电气身份: {'match' if identity['match'] else 'review'}")
        print(f"  器件 +{len(identity['added_components'])} / -{len(identity['removed_components'])}; "
              f"引脚变化 {len(identity['changed_pin_nets'])}")
        print(f"  布局移动: {len(result['layout']['moved_components'])} 器件, "
              f"{len(result['layout']['moved_attributes'])} 属性")
    return 0 if result['identity']['match'] else 1


def command_selftest(args):
    templates = load_templates()
    result = {
        'status': 'ok',
        'engine_version': ENGINE_VERSION,
        'templates': len(templates),
        'template_roles': {identity: len(template['required_roles'])
                           for identity, template in sorted(templates.items())},
        'note': 'structure only; no EDA, electrical or visual verification',
    }
    _dump(result, args.out)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog='design_engine',
        description='Offline deterministic schematic IR/audit/label planner (stdlib only).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--version', action='version', version=f'design-engine {ENGINE_VERSION}')
    sub = parser.add_subparsers(dest='command', required=True)

    ingest = sub.add_parser('ingest', help='build canonical IR from a frozen evidence bundle')
    ingest.add_argument('--bundle', required=True)
    ingest.add_argument('--out', required=True)
    ingest.add_argument('--json', action='store_true')
    ingest.set_defaults(func=command_ingest)

    for name, func, help_text in (
            ('audit', command_audit, 'run readability/identity audit'),
            ('plan-labels', command_plan, 'plan moves for Name/Designator attributes')):
        item = sub.add_parser(name, help=help_text)
        group = item.add_mutually_exclusive_group(required=True)
        group.add_argument('--bundle')
        group.add_argument('--ir')
        item.add_argument('--out')
        item.add_argument('--json', action='store_true')
        if name == 'plan-labels':
            item.add_argument('--moves-dir', help='write easyeda sch attribute-move JSON documents')
        item.set_defaults(func=func)

    verify = sub.add_parser('verify-plan', help='check preconditions and simulate a label plan')
    verify.add_argument('--ir', required=True)
    verify.add_argument('--plan', required=True)
    verify.add_argument('--out')
    verify.add_argument('--json', action='store_true')
    verify.set_defaults(func=command_verify)

    pcb_ingest = sub.add_parser('pcb-ingest', help='build a PCB IR from pcb-dump/drc/check files')
    pcb_ingest.add_argument('--bundle', required=True)
    pcb_ingest.add_argument('--out', required=True)
    pcb_ingest.add_argument('--quiet', action='store_true')
    pcb_ingest.set_defaults(func=command_pcb_ingest)

    pcb_audit = sub.add_parser('pcb-audit', help='audit outline, pads, copper connectivity and DRC identity')
    pcb_audit.add_argument('--bundle', required=True)
    pcb_audit.add_argument('--sch-ir', help='schematic IR for pin/pad reconciliation')
    pcb_audit.add_argument('--out')
    pcb_audit.add_argument('--json', action='store_true')
    pcb_audit.set_defaults(func=command_pcb_audit)

    route_parser = sub.add_parser('route', help='route one orthogonal connection (offline candidate)')
    route_parser.add_argument('--ir', required=True)
    route_parser.add_argument('--start', required=True, help='x,y in schematic units')
    route_parser.add_argument('--end', required=True, help='x,y in schematic units')
    route_parser.add_argument('--net', required=True)
    route_parser.add_argument('--out')
    route_parser.add_argument('--json', action='store_true')
    route_parser.set_defaults(func=command_route)

    pack_parser = sub.add_parser('pack', help='rigid module packing with pagination')
    pack_parser.add_argument('--ir', required=True)
    pack_parser.add_argument('--spacing', type=float, default=20.0)
    pack_parser.add_argument('--allow-groups', action='store_true',
                             help='treat diagnostic L1 clusters as candidate modules')
    pack_parser.add_argument('--out')
    pack_parser.add_argument('--json', action='store_true')
    pack_parser.set_defaults(func=command_pack)

    templates = sub.add_parser('templates', help='list/validate the 12 common-circuit templates')
    templates.add_argument('--list', action='store_true')
    templates.add_argument('--out')
    templates.set_defaults(func=command_templates)

    compare = sub.add_parser('compare', help='compare two IRs for identity and layout changes')
    compare.add_argument('--before', required=True)
    compare.add_argument('--after', required=True)
    compare.add_argument('--out')
    compare.add_argument('--json', action='store_true')
    compare.set_defaults(func=command_compare)

    selftest = sub.add_parser('selftest', help='structural self-test (no EDA)')
    selftest.add_argument('--out')
    selftest.set_defaults(func=command_selftest)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
