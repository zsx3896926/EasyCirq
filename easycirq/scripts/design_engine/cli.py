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
from .assembly import audit_cpl, generic_components, write_cpl
from .benchmarks import run as run_benchmarks
from .compare import compare_ir
from .constraints import compile_intent
from .gerber import audit_layers
from .critical import audit_critical
from .ir import read_ir, summary, validate_ir, write_ir
from .labels import plan_label_moves, to_easycirq_moves, verify_plan
from .manufacturing import audit_package
from .pack import pack_modules
from .pcb import audit_pcb, build_pcb_ir
from .pcb_workflow import (audit_fabrication, audit_power,
                           compile_constraints as compile_pcb_constraints,
                           diff_boards, extract_pcb_module,
                           load_templates as load_pcb_templates,
                           normalize_board, plan_candidates, plan_pcb_reuse,
                           predict_escapes, template_placements, validate_placement)
from .placement import plan_placement
from .reuse import plan_reuse
from .router import route, validate_route
from .routability import analyze_congestion
from .silk import audit_silk
from .sourcing import audit_bom, match_candidates, read_bom
from .state import (add_evidence, new_state, read_state, resume_summary,
                    verify_evidence, write_state)
from .variants import apply_variant, variant_closure
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
    plan = plan_label_moves(ir, include_advisory=getattr(args, 'include_advisory', False))
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
        documents = to_easycirq_moves(plan, ir)
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


def command_constraints(args):
    with open(args.intent, encoding='utf-8-sig') as handle:
        intent = json.load(handle)
    result = compile_intent(intent)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"约束: {result['counts']}; 状态 {result['status']}; 冲突 {len(result['conflicts'])}")
        for item in result['constraints']:
            print(f"  [{item['kind']}] {item['subject']} {item['predicate']} "
                  f"{item.get('op', '')} {item.get('value')} {item.get('unit')} "
                  f"({item.get('source')})")
    return 0 if result['status'] == 'compiled' else 1


def command_critical(args):
    pcb = build_pcb_ir(args.bundle)
    constraints = None
    if args.constraints:
        with open(args.constraints, encoding='utf-8-sig') as handle:
            constraints = json.load(handle)
    result = audit_critical(pcb, constraints)
    result['source'] = {'kind': 'pcb-bundle', 'path': args.bundle}
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"关键回路: {result['status']}; hard={result['hard_count']} "
              f"advisory={result['advisory_count']}")
        for finding in result['findings']:
            print(f"  [{finding['scope']}] {finding['code']}: {finding['message']}")
        print('电气已验证: 否')
    return 0 if result['status'] == 'pass' else 1


def command_placement(args):
    pcb = build_pcb_ir(args.bundle)
    constraints = None
    if args.constraints:
        with open(args.constraints, encoding='utf-8-sig') as handle:
            constraints = json.load(handle)
    result = plan_placement(pcb, constraints)
    result['source'] = {'kind': 'pcb-bundle', 'path': args.bundle}
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"布局候选: {result['status']}; 选中 {result['selected']}; "
              f"移动 {len(result['plan'])} 个器件")
        for candidate in result['candidates']:
            print(f"  {candidate['id']}: hard={candidate['hard_ok']} "
                  f"critical={candidate['critical_findings']} "
                  f"congestion={candidate['congestion']['overflow']} "
                  f"hpwl={candidate['hpwl']:.1f} neatness={candidate['neatness']:.3f}")
        print('eda_apply: NOT RUN')
    return 0 if result['status'] == 'selected' else 1


def command_routability(args):
    pcb = build_pcb_ir(args.bundle)
    result = analyze_congestion(pcb)
    result['source'] = {'kind': 'pcb-bundle', 'path': args.bundle}
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"拥塞: max={result['congestion']['max']} "
              f"overflow={result['congestion']['overflow']} cells={result['congestion']['cells']}")
        print(f"最近异网焊盘间距: {result['min_pad_spacing_mil']} mil; "
              f"<10 mil 的焊盘对: {len(result['tight_pad_pairs'])}; "
              f"不同网包围盒重叠: {len(result['network_separation_overlaps'])}")
        print('实际布通率: NOT RUN')
    return 0


def command_reuse(args):
    reference = read_ir(args.reference_ir)
    target = read_ir(args.target_ir)
    with open(args.reference_map, encoding='utf-8-sig') as handle:
        reference_map = json.load(handle)
    with open(args.target_map, encoding='utf-8-sig') as handle:
        target_map = json.load(handle)
    template = load_templates()[args.template]
    result = plan_reuse(template, reference, reference_map, target, target_map)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"复用: {result['status']}; 操作 {len(result['operations'])}; "
              f"锁定 {len(result.get('locked_components') or [])}")
        for issue in result.get('issues') or []:
            print(f"  {issue}")
        print('eda_apply: NOT RUN')
    return 0 if result['status'] == 'planned' else 1


def command_silk(args):
    pcb = build_pcb_ir(args.bundle)
    result = audit_silk(pcb)
    result['source'] = {'kind': 'pcb-bundle', 'path': args.bundle}
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"丝印: {result['status']}; hard={result['hard_count']} "
              f"advisory={result['advisory_count']}; 建议 {len(result['suggestions'])}")
        for finding in result['findings']:
            print(f"  [{finding['scope']}] {finding['code']}: {finding['message']}")
        print('eda_apply: NOT RUN')
    return 0 if result['status'] == 'pass' else 1


def _bom_designators(path):
    import csv as csv_module
    import io
    with open(path, 'rb') as handle:
        raw = handle.read()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = raw.decode('utf-16')
    else:
        text = raw.decode('utf-8-sig')
    stream = io.StringIO(text)
    reader = csv_module.DictReader(stream, delimiter='\t')
    if reader.fieldnames and 'Designator' not in reader.fieldnames:
        stream.seek(0)
        reader = csv_module.DictReader(stream)
    result = []
    for row in reader:
        value = row.get('Designator') or row.get('designator') or ''
        result.extend(item.strip() for item in value.split(',') if item.strip())
    return result


def command_cpl(args):
    pcb = build_pcb_ir(args.bundle)
    bom = _bom_designators(args.bom) if args.bom else None
    rules = None
    if args.rules:
        with open(args.rules, encoding='utf-8-sig') as handle:
            rules = json.load(handle).get('rules')
    result = audit_cpl(pcb, bom_designators=bom, rules=rules)
    if args.out_json:
        _dump(result, args.out_json)
    if args.out_csv:
        write_cpl(result['rows'], args.out_csv)
    if args.generic_out:
        _dump(generic_components(pcb), args.generic_out)
    if args.json:
        _dump(result)
    else:
        print(f"CPL: {result['status']}; 行 {len(result['rows'])}; "
              f"top={result['sides']['top']} bottom={result['sides']['bottom']}; "
              f"hard={result['hard_count']}")
        for finding in result['findings']:
            print(f"  [{finding['scope']}] {finding['code']}: {finding['message']}")
        print('eda_apply: NOT RUN')
    return 0 if result['status'] == 'pass' else 1


def command_package(args):
    result = audit_package(args.dir, manifest_path=args.manifest)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"制造包: {result['status']}; hard={result['hard_count']}; "
              f"文件 {len(result['files'])}")
        for finding in result['findings']:
            print(f"  [{finding.get('scope')}] {finding['code']}: {finding['message']}")
        print('制造/贴片/实测: NOT RUN')
    return 0 if result['status'] == 'pass' else 1


def command_variants(args):
    with open(args.parts, encoding='utf-8-sig') as handle:
        rows = json.load(handle)
    if isinstance(rows, dict):
        rows = rows.get('parts') or []
    applied = apply_variant(rows, args.variant)
    closure = variant_closure(rows, applied['rows'])
    result = {'variant': applied, 'closure': closure}
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"变体 {args.variant}: 行 {len(applied['rows'])}; 排除 {len(applied['excluded'])}; "
              f"状态 {applied['status']}")
        print(f"变更闭包: +{len(closure['added'])} -{len(closure['removed'])} "
              f"改 {len(closure['changed'])}; 状态 {closure['status']}")
    return 0 if applied['status'] == 'ok' and closure['status'] == 'ok' else 1


def command_sourcing(args):
    rows = read_bom(args.bom)
    audit = audit_bom(rows)
    result = {'audit': audit}
    if args.candidates:
        with open(args.candidates, encoding='utf-8-sig') as handle:
            candidates = json.load(handle)
        result['match'] = match_candidates(rows, candidates, args.fetched_at)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"BOM: {audit['status']}; 行 {audit['rows']} 器件 {audit['parts']}; "
              f"hard={audit['hard_count']}")
        for finding in audit['findings']:
            print(f"  {finding['code']}: {finding['message']}")
        if 'match' in result:
            print(f"候选匹配: {result['match']['status']}; "
                  f"fetched_at={result['match']['fetched_at']}")
        print('实时库存/价格/SMT: NOT CHECKED')
    return 0 if audit['status'] == 'pass' else 1


def command_state(args):
    if args.init:
        state = new_state({'name': args.init, 'uuid': None, 'page': None},
                          stage=args.stage or 'S0_read', next_action=args.next or '')
        for path in args.evidence or []:
            add_evidence(state, path)
        write_state(state, args.file)
        print(f'已初始化状态: {args.file}')
        return 0
    state = read_state(args.file)
    if args.add_evidence:
        add_evidence(state, args.add_evidence)
        write_state(state, args.file)
    if args.verify:
        result = verify_evidence(state)
        _dump(result, args.out)
        return 0 if result['status'] == 'match' else 1
    _dump(resume_summary(state), args.out)
    return 0


def command_benchmarks(args):
    result = run_benchmarks()
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"基准: {result['status']}; {result['passed']}/{result['total']} "
              f"passed, {result['failed']} failed")
        for case in result['cases']:
            print(f"  {case['id']}: {case['status']} {case['missing'] or ''}")
        print('证据级别: synthetic offline geometry; 不是真机图')
    return 0 if result['status'] == 'ok' else 1


def command_gerber(args):
    result = audit_layers(args.gerber, args.drill)
    if args.out:
        _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"Gerber/钻孔: {result['status']}; hard={result['hard_count']}; "
              f"层 {len(result['layers'])}; 孔 {result['drill']['holes'] if result['drill'] else 0}")
        for finding in result['findings']:
            print(f"  {finding['code']}: {finding['message']}")
        print('渲染/重开/DFM: NOT RUN')
    return 0 if result['status'] == 'pass' else 1


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


def _read_json_file(path):
    with open(path, encoding='utf-8-sig') as handle:
        return json.load(handle)


def command_pcb_normalize(args):
    board = normalize_board(_read_json_file(args.dump))
    _dump(board, args.out)
    if args.json:
        _dump(board)
    else:
        print(f"PCB: {len(board['components'])} 器件, "
              f"{sum(len(item['pads']) for item in board['components'])} 焊盘, "
              f"outline={board['coverage']['outline']}")
    return 0


def command_pcb_constraints(args):
    board = normalize_board(_read_json_file(args.dump))
    intent = _read_json_file(args.intent)
    result = compile_pcb_constraints(intent, board)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"约束: {result['status']} "
              f"(hard={result['counts']['hard']}, conflicts={result['counts']['conflicts']}, "
              f"unknown={result['counts']['unknown']})")
        for conflict in result['conflicts']:
            print(f"  [{conflict['kind']}] {conflict['message']}")
        for item in result['unknown']:
            print(f"  unknown {item['object']}: {item['reason']}")
    return 0 if result['status'] == 'compiled' else 1


def command_pcb_check_plan(args):
    board = normalize_board(_read_json_file(args.dump))
    plan = _read_json_file(args.plan)
    constraint_set = _read_json_file(args.constraints) if args.constraints else None
    partial = bool(plan.get('partial')) if isinstance(plan, dict) else False
    result = validate_placement(board, plan, constraint_set, partial=partial)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"布局检查: {result['status']} (hard_findings={result['counts']['hard_findings']}, "
              f"hard_failed={result['counts']['hard_failed']}, "
              f"hard_unmeasured={result['counts']['hard_unmeasured']})")
        for finding in result['findings']:
            print(f"  [{finding['severity']}] {finding['code']}: {finding['message']} "
                  f"{finding['objects']}")
    return 0 if result['status'] == 'pass' else 1


def command_pcb_candidates(args):
    board = normalize_board(_read_json_file(args.dump))
    intent = _read_json_file(args.intent)
    templates = load_pcb_templates(args.templates)
    constraint_set = _read_json_file(args.constraints) if args.constraints else \
        compile_pcb_constraints(intent, board)
    result = plan_candidates(board, intent, templates, constraint_set)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"候选: {result['status']} selected={result['selected']} "
              f"({result['budget']['evaluated']} strategies)")
        for item in result['comparison']:
            print(f"  {item['id']:14s} hard_ok={item['hard_ok']} "
                  f"near_pin_fail={item['near_pin_failures']} "
                  f"escape_blocked={item['escape_blocked']} hpwl={item['hpwl_mil']}")
    return 0 if result['status'] == 'selected' else 1


def command_pcb_escapes(args):
    board = normalize_board(_read_json_file(args.dump))
    if args.constraints:
        constraint_set = _read_json_file(args.constraints)
        board['keepouts'] = [item for item in constraint_set.get('constraints') or []
                             if item.get('type') == 'keepout']
    nets = set(args.net or []) or None
    result = predict_escapes(board, length_mil=args.length, clearance_mil=args.clearance,
                             nets=nets)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"逃线预判: {result['status']} counts={result['counts']} "
              f"(proxy, routing_verified=false)")
    return 0 if result['status'] == 'complete' else 1


def command_pcb_diff(args):
    before = _read_json_file(args.before)
    after = _read_json_file(args.after)
    scope = _read_json_file(args.scope) if args.scope else None
    result = diff_boards(before, after, scope)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"前后比较: {result['status']} counts={result['counts']}")
        for item in result['unrelated_changes']:
            print(f"  unrelated {item}")
    return 0 if result['status'] == 'match' else 1


def command_pcb_power(args):
    board = normalize_board(_read_json_file(args.dump))
    intent = _read_json_file(args.intent)
    result = audit_power(board, intent)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"电源检查: {result['status']} nets={len(result['nets'])} "
              f"decaps={len(result['decaps'])}")
        for item in result['failed']:
            print(f"  fail {item}")
        for item in result['unmeasured']:
            print(f"  unmeasured {item}")
    return 0 if result['status'] == 'pass' else 1


def command_pcb_fabrication(args):
    board = normalize_board(_read_json_file(args.dump))
    result = audit_fabrication(board)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"制造预检: {result['status']} counts={result['counts']}")
        for finding in result['findings']:
            print(f"  [{finding['severity']}] {finding['code']}: {finding['message']} "
                  f"{finding['objects']}")
        print('未检查: ' + '; '.join(result['checks_skipped']))
    return 0 if result['status'] == 'pass' else 1


def command_pcb_template_plan(args):
    board = normalize_board(_read_json_file(args.dump))
    templates = load_pcb_templates(args.templates)
    template = next((item for item in templates['templates'] if item['id'] == args.template), None)
    if template is None:
        raise ValueError(f"template {args.template!r} not found")
    binding = _read_json_file(args.binding)
    parts = args.anchor.split(',')
    if len(parts) != 3:
        raise ValueError('--anchor: x,y,rotation required')
    result = template_placements(template, binding, board,
                                 x=float(parts[0]), y=float(parts[1]),
                                 rotation=float(parts[2]))
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"模板: {result['template']} {result['status']} "
              f"placements={len(result.get('placements') or [])}")
        for reason in result.get('reasons') or []:
            print(f"  {reason}")
    return 0 if result['status'] == 'planned' else 1


def command_pcb_extract_module(args):
    board = normalize_board(_read_json_file(args.dump))
    members = [value.strip() for value in args.members.split(',') if value.strip()]
    result = extract_pcb_module(board, members, anchor=args.anchor)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"模块: anchor={result['anchor']} members={len(result['members'])} "
              f"copper_reuse={result['copper_reuse']['status']}")
    return 0


def command_pcb_reuse(args):
    module = _read_json_file(args.module)
    target = normalize_board(_read_json_file(args.target))
    binding = _read_json_file(args.binding)
    parts = args.anchor.split(',')
    if len(parts) != 3:
        raise ValueError('--anchor: x,y,rotation required')
    anchor_pose = {'x': float(parts[0]), 'y': float(parts[1]), 'rotation': float(parts[2])}
    net_map = _read_json_file(args.net_map) if args.net_map else None
    constraints = _read_json_file(args.constraints) if args.constraints else None
    result = plan_pcb_reuse(module, target, binding, anchor_pose,
                            constraints=constraints, net_map=net_map)
    _dump(result, args.out)
    if args.json:
        _dump(result)
    else:
        print(f"模块复用: {result['status']} placements={len(result['placements'])} "
              f"copper_reuse={result['copper_reuse'].get('status')}")
        for reason in result['reasons']:
            print(f"  {reason}")
    return 0 if result['status'] == 'planned' else 1


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
            item.add_argument('--moves-dir', help='write easycirq sch attribute-move JSON documents')
            item.add_argument('--include-advisory', action='store_true',
                              help='also move attributes that only touch a wire edge')
        item.set_defaults(func=func)

    verify = sub.add_parser('verify-plan', help='check preconditions and simulate a label plan')
    verify.add_argument('--ir', required=True)
    verify.add_argument('--plan', required=True)
    verify.add_argument('--out')
    verify.add_argument('--json', action='store_true')
    verify.set_defaults(func=command_verify)

    constraints = sub.add_parser('constraints', help='compile intent into hard/preferred/unknown constraints')
    constraints.add_argument('--intent', required=True)
    constraints.add_argument('--out')
    constraints.add_argument('--json', action='store_true')
    constraints.set_defaults(func=command_constraints)

    critical = sub.add_parser('critical', help='pin-level decoupling/protection/crystal/feedback checks')
    critical.add_argument('--bundle', required=True)
    critical.add_argument('--constraints')
    critical.add_argument('--out')
    critical.add_argument('--json', action='store_true')
    critical.set_defaults(func=command_critical)

    state_parser = sub.add_parser('state', help='create/read/verify a resumable task state')
    state_parser.add_argument('--file', required=True)
    state_parser.add_argument('--init')
    state_parser.add_argument('--stage')
    state_parser.add_argument('--next')
    state_parser.add_argument('--evidence', action='append')
    state_parser.add_argument('--add-evidence')
    state_parser.add_argument('--verify', action='store_true')
    state_parser.add_argument('--out')
    state_parser.add_argument('--json', action='store_true')
    state_parser.set_defaults(func=command_state)

    sourcing = sub.add_parser('sourcing', help='offline BOM identity and exact candidate matching')
    sourcing.add_argument('--bom', required=True)
    sourcing.add_argument('--candidates')
    sourcing.add_argument('--fetched-at')
    sourcing.add_argument('--out')
    sourcing.add_argument('--json', action='store_true')
    sourcing.set_defaults(func=command_sourcing)

    variants = sub.add_parser('variants', help='assembly variant/DNP/substitute impact closure')
    variants.add_argument('--parts', required=True)
    variants.add_argument('--variant', default='base')
    variants.add_argument('--out')
    variants.add_argument('--json', action='store_true')
    variants.set_defaults(func=command_variants)

    gerber = sub.add_parser('gerber', help='independent Gerber/drill layer-header check')
    gerber.add_argument('--gerber', action='append', required=True)
    gerber.add_argument('--drill')
    gerber.add_argument('--out')
    gerber.add_argument('--json', action='store_true')
    gerber.set_defaults(func=command_gerber)

    package = sub.add_parser('package', help='manufacturing package completeness audit')
    package.add_argument('--dir', required=True)
    package.add_argument('--manifest')
    package.add_argument('--out')
    package.add_argument('--json', action='store_true')
    package.set_defaults(func=command_package)

    cpl = sub.add_parser('cpl', help='CPL rows, center offset, BOM consistency and generic assembly view')
    cpl.add_argument('--bundle', required=True)
    cpl.add_argument('--bom')
    cpl.add_argument('--rules')
    cpl.add_argument('--out-json')
    cpl.add_argument('--out-csv')
    cpl.add_argument('--generic-out')
    cpl.add_argument('--json', action='store_true')
    cpl.set_defaults(func=command_cpl)

    silk = sub.add_parser('silk', help='silkscreen designator/mirroring/overlap audit')
    silk.add_argument('--bundle', required=True)
    silk.add_argument('--out')
    silk.add_argument('--json', action='store_true')
    silk.set_defaults(func=command_silk)

    routability = sub.add_parser('routability', help='congestion/escape/network-separation proxy')
    routability.add_argument('--bundle', required=True)
    routability.add_argument('--out')
    routability.add_argument('--json', action='store_true')
    routability.set_defaults(func=command_routability)

    placement = sub.add_parser('placement', help='multi-candidate PCB placement with layered scoring')
    placement.add_argument('--bundle', required=True)
    placement.add_argument('--constraints')
    placement.add_argument('--out')
    placement.add_argument('--json', action='store_true')
    placement.set_defaults(func=command_placement)

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

    reuse = sub.add_parser('reuse', help='plan a repeated module with identity/pin-set checks')
    reuse.add_argument('--template', required=True)
    reuse.add_argument('--reference-ir', required=True)
    reuse.add_argument('--reference-map', required=True)
    reuse.add_argument('--target-ir', required=True)
    reuse.add_argument('--target-map', required=True)
    reuse.add_argument('--out')
    reuse.add_argument('--json', action='store_true')
    reuse.set_defaults(func=command_reuse)

    benchmarks = sub.add_parser('benchmarks', help='run the 12 synthetic geometry benchmarks')
    benchmarks.add_argument('--out')
    benchmarks.add_argument('--json', action='store_true')
    benchmarks.set_defaults(func=command_benchmarks)

    templates = sub.add_parser('templates', help='list/validate the 12 common-circuit templates')
    templates.add_argument('--list', action='store_true')
    templates.add_argument('--out')
    templates.set_defaults(func=command_templates)

    pcb_normalize = sub.add_parser('pcb-normalize',
                                   help='normalize a measured pcb dump to the workflow view')
    pcb_normalize.add_argument('--dump', required=True)
    pcb_normalize.add_argument('--out')
    pcb_normalize.add_argument('--json', action='store_true')
    pcb_normalize.set_defaults(func=command_pcb_normalize)

    pcb_constraints = sub.add_parser('pcb-constraints',
                                     help='compile fixed/edge/near-pin/chain/keepout/channel constraints')
    pcb_constraints.add_argument('--dump', required=True)
    pcb_constraints.add_argument('--intent', required=True)
    pcb_constraints.add_argument('--out')
    pcb_constraints.add_argument('--json', action='store_true')
    pcb_constraints.set_defaults(func=command_pcb_constraints)

    pcb_check = sub.add_parser('pcb-check-plan',
                               help='validate a placement proposal against measured geometry')
    pcb_check.add_argument('--dump', required=True)
    pcb_check.add_argument('--plan', required=True)
    pcb_check.add_argument('--constraints')
    pcb_check.add_argument('--out')
    pcb_check.add_argument('--json', action='store_true')
    pcb_check.set_defaults(func=command_pcb_check_plan)

    pcb_candidates = sub.add_parser('pcb-candidates',
                                    help='generate signal-chain/density/mechanical module candidates')
    pcb_candidates.add_argument('--dump', required=True)
    pcb_candidates.add_argument('--intent', required=True)
    pcb_candidates.add_argument('--constraints')
    pcb_candidates.add_argument('--templates')
    pcb_candidates.add_argument('--out')
    pcb_candidates.add_argument('--json', action='store_true')
    pcb_candidates.set_defaults(func=command_pcb_candidates)

    pcb_escapes = sub.add_parser('pcb-escapes',
                                 help='predict blocked pad escapes from measured geometry (proxy)')
    pcb_escapes.add_argument('--dump', required=True)
    pcb_escapes.add_argument('--length', type=float, default=100.0)
    pcb_escapes.add_argument('--clearance', type=float)
    pcb_escapes.add_argument('--constraints')
    pcb_escapes.add_argument('--net', action='append')
    pcb_escapes.add_argument('--out')
    pcb_escapes.add_argument('--json', action='store_true')
    pcb_escapes.set_defaults(func=command_pcb_escapes)

    pcb_diff = sub.add_parser('pcb-diff',
                              help='compare two measured dumps and flag unrelated changes')
    pcb_diff.add_argument('--before', required=True)
    pcb_diff.add_argument('--after', required=True)
    pcb_diff.add_argument('--scope')
    pcb_diff.add_argument('--out')
    pcb_diff.add_argument('--json', action='store_true')
    pcb_diff.set_defaults(func=command_pcb_diff)

    pcb_power = sub.add_parser('pcb-power',
                               help='check declared power widths, pours and decap pin distances')
    pcb_power.add_argument('--dump', required=True)
    pcb_power.add_argument('--intent', required=True)
    pcb_power.add_argument('--out')
    pcb_power.add_argument('--json', action='store_true')
    pcb_power.set_defaults(func=command_pcb_power)

    pcb_fab = sub.add_parser('pcb-fabrication',
                             help='offline silk/pour/via facts from a measured dump')
    pcb_fab.add_argument('--dump', required=True)
    pcb_fab.add_argument('--out')
    pcb_fab.add_argument('--json', action='store_true')
    pcb_fab.set_defaults(func=command_pcb_fabrication)

    pcb_template = sub.add_parser('pcb-template-plan',
                                  help='bind one local PCB template and emit relative placements')
    pcb_template.add_argument('--dump', required=True)
    pcb_template.add_argument('--template', required=True)
    pcb_template.add_argument('--binding', required=True)
    pcb_template.add_argument('--anchor', required=True, help='x,y,rotation')
    pcb_template.add_argument('--templates')
    pcb_template.add_argument('--out')
    pcb_template.add_argument('--json', action='store_true')
    pcb_template.set_defaults(func=command_pcb_template_plan)

    pcb_extract = sub.add_parser('pcb-extract-module',
                                 help='extract relative layout + pin-net contract from a measured board')
    pcb_extract.add_argument('--dump', required=True)
    pcb_extract.add_argument('--members', required=True)
    pcb_extract.add_argument('--anchor')
    pcb_extract.add_argument('--out')
    pcb_extract.add_argument('--json', action='store_true')
    pcb_extract.set_defaults(func=command_pcb_extract_module)

    pcb_reuse = sub.add_parser('pcb-reuse-plan',
                               help='apply a PCB module to a target board with identity/pin-net checks')
    pcb_reuse.add_argument('--module', required=True)
    pcb_reuse.add_argument('--target', required=True)
    pcb_reuse.add_argument('--binding', required=True)
    pcb_reuse.add_argument('--anchor', required=True, help='target x,y,rotation')
    pcb_reuse.add_argument('--net-map')
    pcb_reuse.add_argument('--constraints')
    pcb_reuse.add_argument('--out')
    pcb_reuse.add_argument('--json', action='store_true')
    pcb_reuse.set_defaults(func=command_pcb_reuse)

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
