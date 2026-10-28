"""I1: de-energised inspection and preconditions.

Implemented by the I1 capability owner.  Calls ``ctx.add_step(...)`` /
``ctx.add_gap(...)`` and returns nothing.

Required semantics (see docs/parallel-bringup-planner/acceptance-matrix.md):

* visual/assembly checks: polarity, wrong part, DNP, connector orientation,
  solder bridges -- derived from assemblies/interfaces/evidence, not a fixed
  template;
* supply-path checks: every declared external supply path is identified and
  its disconnect precondition generated when backfeed is possible;
* insulation/short investigation between each power rail and ground:
  - the prerequisites are explicit: external supply disconnected, board
    de-energised, bulk capacitance discharged (discharge itself is a step
    that depends on the de-energised condition);
  - resistance/diode-mode readings are affected by capacitor charging and
    parallel semiconductors, so the step records the meter mode, settling
    requirement and that a low reading is not automatically a short;
  - a numeric short criterion is only used when
    ``assemblies.short_check_criterion`` is declared; otherwise the criterion
    is ``undefined`` / ``needs_interpretation`` and the step is not a
    numeric PASS gate;
* never place a resistance measurement on a powered board, never call a low
  current limit "safe" and never invent ohm thresholds.
"""
from __future__ import annotations

from .dag import supply_conflicts as compute_supply_conflicts
from .steps import (STATUS_BLOCKED, STATUS_READY, equipment_item,
                    evidence_item, make_step, prerequisite_step,
                    stop_condition)


def build(ctx):
    """Generate I1 steps into ``ctx``."""
    if not ctx.multimeters():
        ctx.add_equipment_gap(
            'I1_MULTIMETER_MISSING', 'multimeter',
            'DC voltage, resistance and diode-mode measurement',
            'no multimeter is declared, so de-energised voltage, discharge '
            'and rail-to-ground checks cannot be measured or verified')
    _visual_step(ctx)
    _jumper_step(ctx)
    _disconnect_step(ctx)
    _discharge_step(ctx)
    for domain in ctx.domains:
        _short_check_step(ctx, domain)
    _short_check_unknown(ctx)
    return None


# ---------------------------------------------------------------------------
# small helpers


def _fmt(value):
    if value is None:
        return '未声明'
    if isinstance(value, float):
        return '%.6g' % value
    return str(value)


def _status_of(ctx, step_id):
    for step in ctx.steps:
        if step['step_id'] == step_id:
            return step['status']
    return None


def _blocked_prerequisites(ctx, step_ids):
    return [step_id for step_id in step_ids
            if _status_of(ctx, step_id) == STATUS_BLOCKED]


def _conflicts(ctx):
    conflicts = getattr(ctx, 'supply_conflicts', None)
    if conflicts is None:
        conflicts = compute_supply_conflicts(
            ctx.domains, ctx.assemblies, ctx.interfaces)
    return list(conflicts or [])


def _evidence_ids(ctx):
    return sorted(source['id'] for source in ctx.evidence if source.get('id'))


def _first_multimeter(ctx):
    meters = ctx.multimeters()
    return meters[0] if meters else None


def _blocked_state(prereq_ids, missing, reasons):
    if prereq_ids:
        missing.append('prerequisite step(s) %s are blocked; complete them first'
                       % ', '.join(prereq_ids))
        reasons.append('de-energised preconditions are not satisfied: %s'
                       % ', '.join(prereq_ids))


# ---------------------------------------------------------------------------
# visual / assembly inspection


def _visual_step(ctx):
    assemblies = ctx.assemblies
    project = ctx.project
    evidence_ids = _evidence_ids(ctx)
    has_assembly = bool(assemblies['dnp'] or assemblies['jumpers']
                        or assemblies['variants']
                        or assemblies['removable_loads']
                        or assemblies['protection_and_polarity'])
    procedure = [
        '核对实物与声明：工程 revision=%r，BOM 版本=%r，装配版本=%r；'
        '本步骤是人工目视/装配检查，不是自动判据。'
        % (project['revision'], project['bom_version'],
           project['assembly_version']),
    ]
    if evidence_ids:
        procedure.append(
            '对照证据来源 %s 复核装配与来料状态；证据 revision 与工程 '
            'revision 不一致时先更新证据，不得用过期证据下结论。'
            % ', '.join(evidence_ids))
        stale = [source['id'] for source in ctx.evidence
                 if source.get('revision') and project['revision']
                 and source['revision'] != project['revision']]
        if stale:
            procedure.append('注意：证据 %s 的 revision 与工程不一致（stale）；'
                             '按未知处理并重新采集。' % ', '.join(stale))
    else:
        procedure.append('输入未声明任何证据来源：目视结论只能记为 unknown；'
                         '先补充 BOM/装配/照片证据。')
    if assemblies['variants']:
        procedure.append('确认实物对应的装配变体：%s；不得把不同变体的器件、'
                         '跳线或 DNP 状态混用。'
                         % ', '.join(assemblies['variants']))
    procedure.append('错件核对：逐位比对已贴装器件与 BOM 版本 %r 的料号/封装，'
                     '记录任何不一致。' % project['bom_version'])
    if assemblies['protection_and_polarity']:
        procedure.append('极性与保护核对：%s；按声明确认二极管/稳压器/连接器'
                         '方向与极性标记，反接可能直接损坏器件。'
                         % assemblies['protection_and_polarity'])
    else:
        procedure.append('极性核对：输入未声明保护与极性方案；仍须按丝印/器件'
                         '标记确认电解电容、二极管与电源连接器方向，并记录未知项。')
    for item in assemblies['dnp']:
        procedure.append(
            'DNP 核对：确认 %s（%s，%s）未贴装；若已贴装，先停止并核对装配版本。'
            % (item['designator'], item['part'] or '未声明料号',
               item['reason'] or '未说明原因'))
    if not assemblies['jumpers']:
        procedure.append('跳线配置：输入未声明跳线；若实物存在跳线/焊盘选项，'
                         '先记录其状态并补充到输入。')
    for item in assemblies['removable_loads']:
        state = '默认已连接' if item['default_connected'] else '默认未连接'
        procedure.append('可分离负载核对：确认 %s（%s，%s）的实际连接状态；'
                         '首次上电前按 I2-LOAD-* 步骤保持断开。'
                         % (item['designator'],
                            item['description'] or '未描述', state))
    for interface in ctx.interfaces:
        pins = ', '.join('%s:%s' % (pin['pin'], pin['net'])
                         for pin in interface['pins'])
        text = ('接口核对：%s（%s）实际引脚/网络与声明一致（%s）'
                % (interface['id'], interface['type'],
                   pins or '未声明引脚'))
        if interface['type'] in ('connector', 'usb', 'uart', 'debug') \
                or interface['backfeed_risk']:
            text += '；确认连接器方向/防呆与 pin1 标记'
        procedure.append(text + '。')
    if ctx.domains:
        procedure.append(
            '焊接检查：在可见范围内检查 %s 与 %r 附近是否有锡桥、连锡、虚焊或'
            '异物；不得带电触碰。'
            % (', '.join(domain['net'] for domain in ctx.domains),
               ctx.domains[0]['ground_net']))
    procedure.append('记录：拍摄正/反面照片并标注日期、revision 与执行人；'
                     '任何不确定项记为 unknown，不得默认正常。')

    missing, reasons = [], []
    if not ctx.supports_operation('visual_inspection'):
        missing.append('user_policy.allowed_operations: visual_inspection '
                       '（目视检查未授权）')
        reasons.append('visual_inspection is not authorised by the user policy')
    if not (has_assembly or ctx.interfaces or ctx.evidence):
        missing.append('declared assembly/BOM reference, interfaces or '
                       'evidence source for a meaningful visual inspection')
        reasons.append('no assembly, interface or evidence declaration exists; '
                       'a fixed generic visual checklist would not be derived '
                       'from the input')
    status = STATUS_BLOCKED if missing else STATUS_READY
    ctx.add_step(make_step(
        step_id='I1-VIS-001',
        group='I1',
        title='目视与装配检查（极性/错件/DNP/跳线/连接器方向）',
        purpose='在断电状态下按声明的装配、接口与证据核对实物，发现极性、'
                '错件、DNP、跳线与连接器方向问题，避免带着装配缺陷上电。',
        procedure=list(procedure),
        wiring={'measure_at': None, 'reference': None, 'probe': None,
                'notes': '纯目视/装配检查；不施加电源，不测电阻。'},
        expected_behavior='实物与声明一致：无未解释的极性反转、错件、误贴 DNP、'
                          '跳线错位、连接器反插或锡桥。',
        required_evidence=[
            evidence_item('photo', '已装配板卡正面/反面照片，可追溯到计划与 '
                                   'revision'),
            evidence_item('visual_check', '逐项目视结论（含 unknown 项与原因）'),
        ],
        status=status,
        blocked_reason='; '.join(reasons) if reasons else None,
        missing_information=missing,
        required=True,
        source_refs=evidence_ids,
        notes='内容由 assemblies/interfaces/evidence 的声明生成，不是固定模板；'
              '目视结论不能替代测量证据。'))
    if ctx.evidence and not (has_assembly or ctx.interfaces):
        ctx.add_gap('I1_VISUAL_REFERENCE_WEAK', 'I1 visual inspection',
                    'only evidence sources are declared; no assembly or '
                    'interface data exists to derive concrete visual checks',
                    needed=['assemblies/BOM details', 'interface pin tables'],
                    severity='warning')


# ---------------------------------------------------------------------------
# jumper configuration


def _jumper_step(ctx):
    jumpers = ctx.assemblies['jumpers']
    if not jumpers:
        return
    procedure, missing, reasons = [], [], []
    for jumper in jumpers:
        line = '跳线配置 %s：默认状态 %r；' % (jumper['id'],
                                              jumper['default_state'])
        required = jumper['required_state_for_test']
        if required:
            line += '测试要求状态 %r；' % required
            states = [config['state'] for config in jumper['configurations']]
            if states and required not in states:
                missing.append(
                    'assemblies.jumpers[%s].required_state_for_test %r is not '
                    'among the declared configurations %s'
                    % (jumper['id'], required, states))
        else:
            line += '未声明测试所需状态，保持默认/当前状态并记录，不得擅自更改；'
        if jumper['configurations']:
            line += '已声明配置：%s。' % '; '.join(
                '%s=%s' % (config['state'], config['purpose'] or '未说明')
                for config in jumper['configurations'])
        if jumper['notes']:
            line += '说明：%s' % jumper['notes']
        procedure.append(line)
    blocked = _blocked_prerequisites(ctx, ['I1-VIS-001'])
    _blocked_state(blocked, missing, reasons)
    if not ctx.supports_operation('visual_inspection'):
        missing.append('user_policy.allowed_operations: visual_inspection '
                       '（跳线检查未授权）')
        reasons.append('jumper configuration is an assembly inspection and is '
                       'not authorised by the user policy')
    status = STATUS_BLOCKED if missing else STATUS_READY
    ctx.add_step(make_step(
        step_id='I1-JMP-001',
        group='I1',
        title='跳线/配置状态确认',
        purpose='在断电状态下确认每个声明跳线的测试配置，避免按错误配置上电。',
        prerequisites=[prerequisite_step(
            'I1-VIS-001', 'assembly identity verified before changing jumpers')],
        procedure=list(procedure),
        expected_behavior='每个跳线处于声明的测试要求状态（未声明时保持默认/'
                          '当前状态并记录）。',
        required_evidence=[
            evidence_item('photo', '跳线实际位置照片（每个跳线可见）'),
            evidence_item('inspection_note', '跳线状态与声明配置的逐项对照'),
        ],
        status=status,
        blocked_reason='; '.join(reasons) if reasons else None,
        missing_information=missing,
        required=True,
        notes='跳线状态来自 assemblies.jumpers 的 required_state_for_test/'
              'configurations 声明；未声明时不得自行选择“常用配置”。'))


# ---------------------------------------------------------------------------
# de-energise and disconnect external supply paths


def _disconnect_step(ctx):
    procedure = []
    supplies = ctx.supplies()
    if supplies:
        for supply in supplies:
            procedure.append(
                '关闭并断开限流电源 %s（%s）输出，随后移除其与板卡的供电与接地'
                '连线；保持断开直到后续步骤明确要求上电。'
                % (supply['id'], supply['model']))
    else:
        procedure.append('输入未声明限流电源：先断开现场使用的一切外部供电并'
                         '记录电源身份/型号；无声明电源时不得上电。')
    declared_paths = set()
    for path in ctx.assemblies['external_supply_paths']:
        declared_paths.add(path['id'])
        line = '外部供电路径 %s（网络 %r）：' % (path['id'], path['net'])
        if path['can_backfeed']:
            line += ('声明可回灌（can_backfeed=true），必须物理断开/移除该路径；'
                     '断开前不得做对地电阻/短路测量。')
            if not path['disconnect_required_for_deenergized_tests']:
                line += ('输入未声明“断电测试断开要求”，本计划仍要求断开并需'
                         '人工确认，不能默认其已经断开。')
        else:
            line += '未声明回灌能力；保持断开并记录实际状态，不假设其隔离。'
        if path['notes']:
            line += '说明：%s。' % path['notes']
        procedure.append(line)
    for conflict in _conflicts(ctx):
        if not conflict.get('can_backfeed'):
            continue
        if conflict.get('code') == 'EXTERNAL_SUPPLY_PATH' \
                and conflict.get('path_id') in declared_paths:
            continue
        procedure.append(
            '冲突 %s：%s 可能向 %s 的 %r 回灌（反向阻断=%s），必须先物理断开'
            '该外部供电路径/接口，再做断电测量。'
            % (conflict['code'], conflict['path_id'], conflict['domain'],
               conflict['net'], conflict.get('reverse_blocking')))
    for interface in ctx.interfaces:
        if interface['backfeed_risk']:
            procedure.append(
                '拔除接口 %s（%s）上的外部线缆；该接口声明 backfeed_risk=true，'
                '在拔除前不得测量对地电阻。'
                % (interface['id'], interface['type']))
    for item in ctx.assemblies['removable_loads']:
        procedure.append('断开可分离负载 %s（%s）；首次上电前保持断开。'
                         % (item['designator'],
                            item['description'] or '未描述'))
    meter = _first_multimeter(ctx)
    if meter:
        for domain in ctx.domains:
            usable = [point for point in ctx.testpoints_for(domain['net'])
                      if point['reachability_verified']]
            if usable:
                procedure.append(
                    '用万用表 %s 的 DC 电压档在 %s（%r）对 %r 测量，确认无持续'
                    '电压并记录读数；读到稳定无电压才继续。'
                    % (meter['id'], usable[0]['id'], domain['net'],
                       domain['ground_net']))
            else:
                procedure.append(
                    '电源域 %s（%r）没有已验证测试点：断电状态无法直接测量，'
                    '记为 unknown，不得用“应该没电”代替读数。'
                    % (domain['id'], domain['net']))
    else:
        procedure.append('没有声明的万用表：断电状态无法验证；补齐设备前不得继续。')

    missing, reasons = [], []
    if not ctx.supports_operation('deenergized_continuity'):
        missing.append('user_policy.allowed_operations: deenergized_continuity '
                       '（断电量测未授权）')
        reasons.append('deenergized_continuity is not authorised by the user '
                       'policy')
    if not meter:
        missing.append('declared multimeter (equipment.multimeters) for '
                       'de-energised verification（断电验证用万用表未声明）')
        reasons.append('no multimeter is declared; the de-energised state '
                       'cannot be measured or verified')
    _blocked_state(_blocked_prerequisites(ctx, ['I1-VIS-001', 'I1-JMP-001']),
                   missing, reasons)
    status = STATUS_BLOCKED if missing else STATUS_READY
    equipment = []
    if meter:
        equipment.append(equipment_item(
            meter['id'], 'DC voltage measurement',
            settings={'mode': 'dc_voltage'}, verified=True,
            detail='declared instrument; used only for manual readings'))
    ctx.add_step(make_step(
        step_id='I1-OFF-001',
        group='I1',
        title='断电、断开外部供电与可回灌路径',
        purpose='建立并验证板卡完全断电的状态：关闭电源、断开所有可能回灌的'
                '外部供电/接口/负载，使后续对地电阻测量与首次上电是安全的。',
        prerequisites=([prerequisite_step(
                            'I1-VIS-001',
                            'assembly/interface state confirmed before '
                            'disconnecting and probing')]
                       + ([prerequisite_step(
                               'I1-JMP-001',
                               'jumper/configuration state confirmed')]
                          if ctx.assemblies['jumpers'] else [])),
        equipment=equipment,
        wiring={'measure_at': '每个已声明电源域测试点（逐轨）',
                'reference': '声明的 ground_net',
                'probe': 'standard DMM probes',
                'notes': '仅在断开所有供电后进行；测量的是“无电压”，不是'
                         '上电电压。'},
        procedure=procedure,
        measurement={
            'quantity': 'voltage',
            'point': 'one reading per declared rail testpoint',
            'reference': 'declared ground_net for each domain',
            'range': None,
            'criterion_status': 'qualitative',
            'basis': 'de-energised confirmation only: no sustained voltage may '
                     'remain; no numeric tolerance is declared, so no automatic '
                     'PASS/FAIL range is applied',
            'source_refs': [],
        },
        expected_behavior='所有已声明电源轨对地均无持续电压；外部供电、可回灌'
                          '路径、调试器与可分离负载全部断开。',
        stop_conditions=[stop_condition(
            'I1_RESIDUAL_VOLTAGE',
            '断开全部外部供电后仍测到稳定电压或电压上升',
            action='stop; keep the board de-energised and locate the remaining '
                   'supply, stored energy or backfeed path; do not perform '
                   'resistance checks')],
        required_evidence=[
            evidence_item('photo', '外部供电/回灌线缆与可分离负载已断开的照片'),
            evidence_item('meter_reading',
                          '每轨 DC 电压读数（含测试点、量程、时间）'),
            evidence_item('inspection_note', '断开项清单与人工确认记录'),
        ],
        status=status,
        blocked_reason='; '.join(reasons) if reasons else None,
        missing_information=missing,
        required=True,
        notes='本步骤必须先于任何对地电阻/短路测量；声明可回灌的外部供电路径'
              '必须在此处物理断开。'))


# ---------------------------------------------------------------------------
# bulk capacitance discharge


def _discharge_step(ctx):
    meter = _first_multimeter(ctx)
    rail_checks = []
    for domain in ctx.domains:
        usable = [point for point in ctx.testpoints_for(domain['net'])
                  if point['reachability_verified']]
        rail_checks.append('%s=%s' % (
            domain['id'], usable[0]['id'] if usable else '缺测试点'))
    procedure = [
        '确认 I1-OFF-001 已完成：外部供电、可回灌的外部供电路径、调试/负载'
        '线缆均已断开。',
        '按实物与原理图定位已声明电源域（%s）的输入/储能电容；本输入未声明'
        '容值与认可的放电方法，放电等待时间必须按实际容值和放电工具计算，'
        '本计划不提供固定秒数。'
        % ', '.join(domain['net'] for domain in ctx.domains),
        '使用绝缘放电工具或适合的放电电阻对储能电容放电；禁止用表笔、导线或'
        '金属工具直接短接电源轨/电容。',
    ]
    if meter:
        procedure.append(
            '放电后用万用表 %s 的 DC 电压档逐轨测量（%s），等待读数停止上升并'
            '稳定在无电压状态后才可触碰板卡。'
            % (meter['id'], '；'.join(rail_checks)))
    else:
        procedure.append('没有声明的万用表：放电后无法验证储能已释放，不得继续。')
    procedure.append('若读数持续上升或重新出现电压，说明仍有供电路径或电容被'
                     '充电：停止，不得继续。')

    missing, reasons = [], []
    if not ctx.supports_operation('deenergized_continuity'):
        missing.append('user_policy.allowed_operations: deenergized_continuity '
                       '（放电验证未授权）')
        reasons.append('deenergized_continuity is not authorised by the user '
                       'policy')
    if not meter:
        missing.append('declared multimeter (equipment.multimeters) to verify '
                       'the discharge（放电验证用万用表未声明）')
        reasons.append('no multimeter is declared; stored energy cannot be '
                       'verified as released')
    _blocked_state(_blocked_prerequisites(ctx, ['I1-OFF-001']), missing, reasons)
    status = STATUS_BLOCKED if missing else STATUS_READY
    equipment = []
    if meter:
        equipment.append(equipment_item(
            meter['id'], 'DC voltage measurement',
            settings={'mode': 'dc_voltage'}, verified=True))
    ctx.add_step(make_step(
        step_id='I1-OFF-DISCHARGE',
        group='I1',
        title='储能电容放电与断电状态复核',
        purpose='在断电前提之后独立完成储能电容放电并复核，防止残余电压'
                '破坏对地电阻读数或伤害操作者。',
        prerequisites=[prerequisite_step(
            'I1-OFF-001',
            'discharge is only valid after external supplies are disconnected '
            'and the board is de-energised')],
        equipment=equipment,
        wiring={'measure_at': '每个已声明电源域测试点',
                'reference': '声明的 ground_net',
                'probe': 'insulated discharge tool and DMM probes',
                'notes': '放电工具与方式未声明时必须按实物计算，不能假设'
                         '固定等待秒数。'},
        procedure=procedure,
        measurement={
            'quantity': 'voltage',
            'point': 'each declared rail after discharge',
            'reference': 'declared ground_net',
            'range': None,
            'criterion_status': 'qualitative',
            'basis': 'the reading must show stored energy released and must '
                     'not rise again; no numeric tolerance is declared',
            'source_refs': [],
        },
        expected_behavior='放电后各电源轨对地无电压且读数不再上升。',
        stop_conditions=[stop_condition(
            'I1_STORED_ENERGY',
            '放电后仍有电压或读数上升',
            action='stop; keep the board de-energised and treat stored energy '
                   'as present until proven otherwise')],
        required_evidence=[
            evidence_item('meter_reading', '放电后逐轨 DC 电压读数与时间'),
            evidence_item('inspection_note', '放电方法与等待时间的记录'),
        ],
        status=status,
        blocked_reason='; '.join(reasons) if reasons else None,
        missing_information=missing,
        required=True,
        notes='放电是依赖断电前提的独立步骤，不与断开外部供电合并；未声明'
              '容值时不得假设固定放电时间。'))
    ctx.add_gap(
        'I1_DISCHARGE_PROFILE_UNDECLARED', 'I1 discharge',
        'bulk/input capacitance values and an approved discharge method are '
        'not declared; the discharge step is a manual procedure whose waiting '
        'time must be derived from the physical board, not a fixed number',
        needed=['bulk/input capacitance values', 'approved discharge method'],
        severity='warning')


# ---------------------------------------------------------------------------
# per-rail insulation / short investigation


def _short_check_step(ctx, domain):
    step_id = 'I1-OFF-RES-%s' % domain['id']
    points = ctx.testpoints_for(domain['net'])
    usable = [point for point in points if point['reachability_verified']]
    ground_points = ctx.testpoints_for(domain['ground_net'])
    ground_usable = [point for point in ground_points
                     if point['reachability_verified']]
    tp = usable[0] if usable else None
    if tp is not None:
        measure_at = '%s (%s)' % (tp['id'], domain['net'])
    else:
        measure_at = 'network %r (no verified testpoint)' % domain['net']
    if ground_usable:
        reference = '%s (%s)' % (ground_usable[0]['id'],
                                 domain['ground_net'])
    else:
        reference = ('network %r (no dedicated ground testpoint declared; '
                     'locate the same net on the board)' % domain['ground_net'])
    meter = _first_multimeter(ctx)
    criterion = ctx.assemblies['short_check_criterion']
    missing, reasons = [], []

    if not ctx.supports_operation('deenergized_continuity'):
        missing.append('user_policy.allowed_operations: deenergized_continuity '
                       '（对地电阻/二极管测量未授权）')
        reasons.append('deenergized_continuity is not authorised by the user '
                       'policy')
    if not usable:
        missing.append('declared reachable testpoint for rail %r '
                       '(power_domains[%s].net)' % (domain['net'],
                                                    domain['id']))
        reasons.append('no reachable/verified testpoint exists for rail %r; '
                       'the rail-to-ground reading cannot be taken'
                       % domain['net'])
        ctx.add_gap(
            'I1_RAIL_TESTPOINT_MISSING', 'domain %s' % domain['id'],
            'no reachable/verified testpoint for rail %r; the de-energised '
            'short check cannot be measured' % domain['net'],
            needed=['testpoint on rail %r with reachability_verified=true'
                    % domain['net']],
            severity='blocking', path='$.testpoints')
    if meter is None:
        missing.append('declared multimeter (equipment.multimeters) with '
                       'resistance/diode mode（电阻/二极管档万用表未声明）')
        reasons.append('no multimeter is declared; the rail-to-ground reading '
                       'cannot be taken')
    _blocked_state(_blocked_prerequisites(ctx, ['I1-OFF-001',
                                                'I1-OFF-DISCHARGE']),
                   missing, reasons)

    procedure = [
        '前提：板卡已完全断电（I1-OFF-001）且储能电容已放电并复核'
        '（I1-OFF-DISCHARGE）；严禁在带电或未放电状态下用电阻档测量。',
        '表笔与量程：一支表笔接 %s，另一支接 %s；选择万用表电阻档，量程覆盖%s；'
        '记录量程。若电阻档无法区分，则改用二极管档对比正/反向压降。'
        % (measure_at, reference,
           ('声明判据 ≤ %s Ω' % _fmt(criterion['max_ohm']))
           if criterion else '（未声明判据，使用不会过载的合适量程并记录）'),
        '稳定时间要求：等待读数停止漂移，记录两次读数及稳定所需时间。电容充电'
        '会使读数持续上升或下降；未稳定前不得判读。输入未声明固定稳定时间，'
        '本步骤不假设某个秒数。',
        '读数解释：低阻可能来自并联半导体结、其他供电路径或仍在充电的电容，'
        '不必然是短路；必须先按分区隔离（断开可分离负载、拔除外部线缆）后再'
        '复测。',
        '记录表笔极性（红/黑）与接触点；同一读数在不同极性/量程下不一致时，'
        '按 unknown 处理。',
    ]
    if meter and meter.get('diode_mode'):
        procedure.append('二极管档复核：按正/反两个方向记录压降，与电阻读数'
                         '一起判读；单次低阻不得直接判为短路。')
    elif meter:
        procedure.append('该万用表未声明 diode_mode：只能使用电阻档记录，并在'
                         '证据中注明缺少二极管档的限制。')
    procedure.append('本步骤用于发现异常低阻并定位，不证明上电后一定正常。')

    if criterion:
        measurement = {
            'quantity': 'resistance',
            'point': measure_at,
            'reference': reference,
            'range': {'min': None, 'max': criterion['max_ohm'],
                      'unit': 'ohm'},
            'criterion_status': 'defined',
            'basis': 'declared assemblies.short_check_criterion.max_ohm '
                     '(basis=%s, source_ref=%s, conditions=%s)'
                     % (criterion['basis'],
                        criterion['source_ref'] or '未声明',
                        criterion['conditions'] or '未声明'),
            'source_refs': ([criterion['source_ref']]
                            if criterion['source_ref'] else []),
        }
        expected = (
            '隔离并联路径后，稳定读数应不高于声明判据 %s Ω（来源 basis=%s）；'
            '但低阻不必然等于短路，必须结合表笔极性、二极管档与分区隔离复测'
            '判读。' % (_fmt(criterion['max_ohm']), criterion['basis']))
        stops = [stop_condition(
            'I1_SUSPECTED_SHORT',
            '隔离并联路径后仍存在低于声明判据的对地低阻',
            threshold=criterion['max_ohm'], quantity='resistance', unit='ohm',
            source_ref=criterion.get('source_ref'),
            action='stop; do not power the rail; isolate the branch and locate '
                   'the low-resistance path first')]
    else:
        measurement = {
            'quantity': 'resistance',
            'point': measure_at,
            'reference': reference,
            'range': None,
            'criterion_status': 'needs_interpretation',
            'basis': 'no assemblies.short_check_criterion is declared; the '
                     'reading is recorded for manual interpretation only and '
                     'no automatic ohm threshold is applied',
            'source_refs': [],
        }
        expected = (
            '无声明判据：只记录稳定读数、量程、表笔极性与稳定时间，由工程人员'
            '解释；不得套用任何通用欧姆阈值把读数自动判为短路或正常，低阻也'
            '可能来自并联半导体/多路径。')
        stops = [stop_condition(
            'I1_SUSPECTED_SHORT',
            '读数极低且隔离并联路径后仍存在，无法用并联半导体或多路径解释',
            action='stop; do not power the rail until the reading is explained '
                   'or a declared criterion is added')]

    required_evidence = [
        evidence_item('meter_reading',
                      '对地电阻/二极管读数：%s，含量程、表笔极性、稳定时间与'
                      '至少两次读数' % measure_at),
    ]
    if criterion:
        required_evidence.append(evidence_item(
            'inspection_note',
            '按声明判据（max_ohm=%s，basis=%s）的判读记录，并说明是否已排除'
            '并联路径与电容充电影响'
            % (_fmt(criterion['max_ohm']), criterion['basis'])))
    else:
        required_evidence.append(evidence_item(
            'inspection_note',
            '人工解释记录：未声明 short_check_criterion，必须写明读数为何'
            '被接受或拒绝，不得套用通用欧姆阈值'))
    equipment = []
    if meter:
        equipment.append(equipment_item(
            meter['id'], 'resistance / diode measurement',
            settings={'mode': 'resistance',
                      'diode_mode': meter['diode_mode'],
                      'resistance_max_ohm': meter['resistance_max_ohm']},
            verified=True,
            detail='board de-energised and discharged before this step'))
    status = STATUS_BLOCKED if missing else STATUS_READY
    ctx.add_step(make_step(
        step_id=step_id,
        group='I1',
        title='对地绝缘/短路排查：%s（%s）' % (domain['id'], domain['net']),
        purpose='在断电、放电、断开外部供电之后，测量电源轨对地电阻/二极管'
                '特性，发现异常低阻或装配短路，再决定是否允许首次上电。',
        prerequisites=[
            prerequisite_step('I1-OFF-001',
                              'external supplies and backfeed paths disconnected'),
            prerequisite_step('I1-OFF-DISCHARGE',
                              'bulk capacitance discharged and verified'),
        ],
        equipment=equipment,
        wiring={'measure_at': measure_at,
                'reference': reference,
                'probe': 'standard DMM probes; record polarity',
                'notes': '板卡断电且已放电；不得带电测电阻，不得用表笔短接'
                         '电容放电。'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        stop_conditions=stops,
        failure_branches=['FT-%s' % step_id],
        required_evidence=required_evidence,
        status=status,
        blocked_reason='; '.join(reasons) if reasons else None,
        missing_information=missing,
        required=True,
        source_refs=([criterion['source_ref']]
                     if criterion and criterion['source_ref'] else []),
        notes='判据来源：%s；低阻不必然是短路，电容充电会导致读数漂移，'
              '并联半导体与多条供电路径会降低读数。'
              % ('assemblies.short_check_criterion'
                 if criterion else '未声明（needs_interpretation）')))


def _short_check_unknown(ctx):
    if ctx.assemblies['short_check_criterion']:
        return
    res_ids = ['I1-OFF-RES-%s' % domain['id'] for domain in ctx.domains]
    ctx.add_unknown(
        'I1_SHORT_CHECK_CRITERION_UNDEFINED', 'de-energised short check',
        'assemblies.short_check_criterion is not declared; every rail-to-'
        'ground reading can only be interpreted manually. No generic ohm '
        'threshold is applied and the reading can never auto-pass.',
        needed=['assemblies.short_check_criterion.max_ohm',
                'assemblies.short_check_criterion.basis',
                'assemblies.short_check_criterion.source_ref'],
        blocks=res_ids)
