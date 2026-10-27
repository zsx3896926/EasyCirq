"""I2: first power-up, current limit and per-domain sequencing.

Implemented by the I2 capability owner.  Uses ``ctx.dag['order']`` for the
domain order and ``ctx.supply_conflicts`` for external-supply conflicts.

Required semantics:

* one step per domain, in dependency order; prerequisites are the previous
  domain's verified voltage step and the I1 de-energised checks;
* the supply starts at a declared operating voltage (never the absolute
  maximum), and the plan states the voltage range, the maximum allowed
  setting and the expected behaviour;
* current limit must be justified by declared startup/runtime current, the
  load/protection scheme and ``operating_conditions.current_limit_policy``;
  if these are missing, the step is BLOCKED with the missing information and
  no default 100 mA / 500 mA is invented.  A limit below the declared startup
  current is reported as a brown-out/restart risk, not as "safe";
* observation window must come from a declared basis (datasheet/timing/
  calculation); otherwise BLOCKED/unknown;
* removable loads / debugger / USB / programming prerequisites are separate
  steps from the first energise step;
* STOP conditions only from project-known thresholds plus qualitative
  "abnormal heat/smell/smoke" immediate-stop rules.

The planner never actually applies power; procedures are manual instructions.
"""
from __future__ import annotations

from .steps import (STATUS_BLOCKED, STATUS_READY, equipment_item,
                    evidence_item, make_step, prerequisite_condition,
                    prerequisite_step, stop_condition)


def build(ctx, dag):
    """Generate I2 steps into ``ctx``."""
    order = list((dag or {}).get('order') or [])
    cycles = list((dag or {}).get('cycles') or [])
    known_ids = [domain['id'] for domain in ctx.domains]
    ordered = set(order)
    unordered = [domain_id for domain_id in known_ids
                 if domain_id not in ordered]
    if cycles:
        ctx.add_gap(
            'I2_DOMAIN_DAG_CYCLE', 'power-up sequencing',
            'power-domain dependency cycle(s): %s; no first-power-up order '
            'exists for these domains'
            % '; '.join(' -> '.join(cycle) for cycle in cycles),
            needed=['resolve the declared depends_on cycle'], severity='blocking')
    if (dag or {}).get('missing_dependencies'):
        ctx.add_gap(
            'I2_DOMAIN_DAG_MISSING_DEPENDENCY', 'power-up sequencing',
            'declared dependency target(s) do not exist: %s'
            % '; '.join('%s -> %s' % (item['domain'], item['missing'])
                        for item in dag['missing_dependencies']),
            needed=['declare the missing domain or remove the dependency'],
            severity='blocking')
    if not ctx.supplies():
        ctx.add_equipment_gap(
            'I2_SUPPLY_MISSING', 'DC supply',
            'current-limited supply with declared voltage/current capability',
            'no supply is declared; no powered step can be bounded or executed')
    if not ctx.multimeters():
        ctx.add_equipment_gap(
            'I2_MULTIMETER_MISSING', 'multimeter',
            'DC voltage measurement',
            'no multimeter is declared; powered rail verification cannot be '
            'measured')

    statuses = {step['step_id']: step['status'] for step in ctx.steps}

    def add(step):
        ctx.add_step(step)
        statuses[step['step_id']] = step['status']
        return step

    conflicts = _conflicts(ctx)
    firmware_id = _firmware_step(ctx, add, statuses)
    external_by_domain = _external_steps(ctx, add, statuses, conflicts)
    load_info = _removable_load_steps(ctx, add, statuses)

    sequence_ids = []
    first_sequence = True
    for domain_id in order:
        sequence_id = _sequence_step(
            ctx, add, statuses, domain_id, order=order, dag=dag,
            external_by_domain=external_by_domain, load_info=load_info,
            firmware_id=firmware_id, first_sequence=first_sequence)
        if sequence_id:
            sequence_ids.append(sequence_id)
            if load_info['domain'].get(domain_id):
                _connect_domain_step(ctx, add, statuses, domain_id,
                                     sequence_id, load_info)
        first_sequence = False
    for domain_id in unordered:
        sequence_id = _sequence_step(
            ctx, add, statuses, domain_id, order=order, dag=dag,
            external_by_domain=external_by_domain, load_info=load_info,
            firmware_id=firmware_id, first_sequence=first_sequence)
        if sequence_id:
            sequence_ids.append(sequence_id)
            if load_info['domain'].get(domain_id):
                _connect_domain_step(ctx, add, statuses, domain_id,
                                     sequence_id, load_info)
        first_sequence = False

    last_sequence_id = sequence_ids[-1] if sequence_ids else None
    for item in load_info['assembly']:
        _connect_assembly_step(ctx, add, statuses, item, last_sequence_id)
    return None


# ---------------------------------------------------------------------------
# small helpers


def _fmt(value):
    if value is None:
        return '未声明'
    if isinstance(value, float):
        return '%.6g' % value
    return str(value)


def _unique(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _sanitize(value):
    text = ''.join(character if character.isalnum()
                   or character in '_.:-' else '-'
                   for character in str(value))
    return text.strip('-') or 'X'


def _conflicts(ctx):
    conflicts = getattr(ctx, 'supply_conflicts', None)
    if conflicts is None:
        from .dag import supply_conflicts as compute_supply_conflicts
        conflicts = compute_supply_conflicts(
            ctx.domains, ctx.assemblies, ctx.interfaces)
    return list(conflicts or [])


def _blocked_state(statuses, prerequisite_ids, missing, reasons):
    blocked = [step_id for step_id in prerequisite_ids
               if statuses.get(step_id) == STATUS_BLOCKED]
    if blocked:
        missing.append('prerequisite step(s) %s are blocked; resolve them '
                       'first' % ', '.join(blocked))
        reasons.append('an upstream step is blocked: %s' % ', '.join(blocked))


def _scope_missing(ctx):
    missing, reasons = [], []
    scope = ctx.scope or {}
    if not scope.get('energize_allowed'):
        missing.append('scope gate: energize_allowed=false (status=%s)'
                       % scope.get('status'))
        reasons.append('the scope gate does not allow energising: %s'
                       % ('; '.join(scope.get('excluded') or [])
                          or 'scope reasons not resolved'))
    if not ctx.supports_operation('powered_dc_measurement'):
        missing.append('user_policy.allowed_operations: '
                       'powered_dc_measurement（上电测量未授权）')
        reasons.append('powered_dc_measurement is not authorised by the user '
                       'policy')
    return missing, reasons


# ---------------------------------------------------------------------------
# firmware / debugger precondition


def _firmware_step(ctx, add, statuses):
    firmware = [interface for interface in ctx.interfaces
                if interface.get('firmware_prerequisite')]
    debug_like = [interface for interface in ctx.interfaces
                  if interface['type'] in ('debug', 'usb')]
    if not (firmware or debug_like):
        return None
    procedure = []
    if firmware:
        procedure.append('记录下列接口声明的固件前提状态（已烧录/未烧录、'
                         '版本与证据）：')
        for interface in firmware:
            procedure.append('接口 %s（%s）：%s'
                             % (interface['id'], interface['type'],
                                interface['firmware_prerequisite'] or '未说明'))
    else:
        procedure.append('输入未声明接口固件前提：记录当前固件状态与证据；'
                         '首次上电不把“无业务通信”当作硬件故障。')
    procedure.append('确认调试器/编程器状态：若已连接，记录型号与供电方式；'
                     '存在回灌风险的调试/USB 线缆必须在首次上电前断开'
                     '（见 I2-EXT-* 步骤）。')
    if 'firmware_flashing' in (ctx.policy.get('forbidden_operations') or []):
        procedure.append('user_policy.forbidden_operations 包含 '
                         'firmware_flashing：本计划不烧录固件；固件前提只能由'
                         '有资质人员按合规流程处理，未烧录不得判定为硬件故障。')
    else:
        procedure.append('本工具不执行烧录：固件前提由人工按项目流程完成，'
                         '本步骤只记录状态。')
    missing, reasons = [], []
    _blocked_state(statuses, ['I1-OFF-001'], missing, reasons)
    status = STATUS_BLOCKED if missing else STATUS_READY
    add(make_step(
        step_id='I2-FW-001',
        group='I2',
        title='烧录/调试器前提与固件状态确认',
        purpose='首次上电前记录固件/调试器状态，并确保调试器或 USB 线缆不会'
                '向目标板回灌；本工具不烧录固件。',
        prerequisites=[prerequisite_step(
            'I1-OFF-001',
            'board de-energised when connecting/disconnecting a debugger')],
        procedure=procedure,
        expected_behavior='固件/调试器状态已记录；首次上电前调试器线缆按声明'
                          '断开，未烧录被记为未知而不是硬件故障。',
        required_evidence=[
            evidence_item('inspection_note',
                          '固件/调试器状态记录（含未烧录时的合理预期）'),
            evidence_item('photo',
                          '调试器/编程器与目标板的连接状态（若曾经连接）'),
        ],
        status=status,
        blocked_reason='; '.join(reasons) if reasons else None,
        missing_information=missing,
        required=True,
        notes='firmware_flashing 属于 user_policy 禁止操作时，本计划只提示'
              '前提，不产生烧录动作。'))
    return 'I2-FW-001'


# ---------------------------------------------------------------------------
# external supply / backfeed conflict steps


def _external_steps(ctx, add, statuses, conflicts):
    blocking = [conflict for conflict in conflicts if conflict.get('blocking')]
    grouped = {}
    for conflict in blocking:
        key = (conflict.get('code'), conflict.get('path_id'))
        entry = grouped.setdefault(key, {
            'code': conflict.get('code'),
            'path_id': conflict.get('path_id'),
            'nets': set(),
            'domains': set(),
            'can_backfeed': False,
            'disconnect_required': True,
            'reverse_blocking': set(),
            'resolution': conflict.get('resolution'),
        })
        if conflict.get('net'):
            entry['nets'].add(conflict['net'])
        if conflict.get('domain'):
            entry['domains'].add(conflict['domain'])
        entry['can_backfeed'] = entry['can_backfeed'] or bool(
            conflict.get('can_backfeed'))
        entry['disconnect_required'] = entry['disconnect_required'] and bool(
            conflict.get('disconnect_required'))
        reverse = conflict.get('reverse_blocking')
        entry['reverse_blocking'].add(reverse or '未声明')

    by_domain = {}
    for key in sorted(grouped, key=lambda item: (str(item[0]), str(item[1]))):
        entry = grouped[key]
        base_id = 'I2-EXT-%s' % _sanitize(entry['path_id'])
        step_id = base_id
        suffix = 2
        while step_id in statuses:
            step_id = '%s-%d' % (base_id, suffix)
            suffix += 1
        nets = ', '.join(sorted(entry['nets']))
        domains = ', '.join(sorted(entry['domains']))
        reverse = ', '.join(sorted(entry['reverse_blocking']))
        missing, reasons = [], []
        _blocked_state(statuses, ['I1-OFF-001'], missing, reasons)
        if not entry['disconnect_required']:
            missing.append(
                'declared disconnect requirement for external supply path %s '
                '(can_backfeed=true, reverse_blocking=%s)'
                '（该外部供电路径的断开要求未声明）'
                % (entry['path_id'], reverse))
            reasons.append(
                'the input declares backfeed for %s but does not declare that '
                'it must be disconnected; the plan cannot assume physical '
                'isolation before energising' % entry['path_id'])
        meter = ctx.multimeters()[0] if ctx.multimeters() else None
        if meter is None:
            missing.append('declared multimeter (equipment.multimeters) to '
                           'verify the external path is isolated'
                           '（验证外部路径已隔离的万用表未声明）')
            reasons.append('no multimeter is declared; backfeed isolation '
                           'cannot be verified')
        for domain_id in sorted(entry['domains']):
            domain = ctx.domain(domain_id)
            if domain is None:
                continue
            usable = [point for point in ctx.testpoints_for(domain['net'])
                      if point['reachability_verified']]
            if not usable:
                missing.append('reachable testpoint on rail %r to verify no '
                               'backfeed from %s'
                               % (domain['net'], entry['path_id']))
                reasons.append('the isolation of %s on rail %r cannot be '
                               'measured' % (entry['path_id'],
                                             domain['net']))
        status = STATUS_BLOCKED if missing else STATUS_READY
        procedure = [
            '物理断开外部供电路径/接口 %s（网络 %s）与目标板的连接；在 %s '
            '的首次上电验证完成前保持断开。'
            % (entry['path_id'], nets or '未声明', domains or '受影响电源域'),
            ('用万用表 %s 的 DC 电压档在受影响电源轨的声明测试点对地确认断开后'
             '无电压，并记录读数与照片。' % meter['id'])
            if meter else
            '没有声明的万用表：无法确认隔离，本步骤不得执行。',
            '声明 reverse_blocking=%s：即使有反向阻断方案，仍须人工确认隔离，'
            '不依赖未经验证的保护。' % reverse,
            '若该路径不能物理断开，必须停止并回到设计/接口侧解决，不得直接上电。',
        ]
        equipment = []
        if meter is not None:
            equipment.append(equipment_item(
                meter['id'], 'DC voltage measurement',
                settings={'mode': 'dc_voltage'}, verified=True))
        add(make_step(
            step_id=step_id,
            group='I2',
            title='外部供电/回灌路径断开：%s' % entry['path_id'],
            purpose='首次上电前物理隔离声明为 blocking 的外部供电路径/回灌'
                    '接口，避免双电源冲突或向外部设备回灌。',
            prerequisites=[prerequisite_step(
                'I1-OFF-001', 'board de-energised and external paths '
                              'disconnected')],
            equipment=equipment,
            procedure=procedure,
            measurement={
                'quantity': 'voltage',
                'point': 'affected rail testpoint(s): %s' % domains,
                'reference': 'declared ground_net',
                'range': None,
                'criterion_status': 'qualitative',
                'basis': 'isolation check only: no sustained voltage may '
                         'remain from the external path',
                'source_refs': [],
            },
            expected_behavior='外部供电路径断开后，受影响电源轨上没有来自该路径'
                              '的电压。',
            stop_conditions=[stop_condition(
                'I2_BACKFEED_PRESENT',
                '断开后受影响电源轨仍测到来自外部路径的电压',
                action='stop; keep the board de-energised; do not energise '
                       'while an external path can still feed the rail')],
            required_evidence=[
                evidence_item('photo', '%s 已断开的照片/连线状态'
                                       % entry['path_id']),
                evidence_item('meter_reading', '受影响电源轨的隔离验证读数'),
            ],
            status=status,
            blocked_reason='; '.join(reasons) if reasons else None,
            missing_information=_unique(missing),
            required=True,
            notes='blocking 冲突（code=%s）：%s。本步骤先于受影响电源域的上电'
                  '步骤；I2-SEQ-* 将其列为前提。'
                  % (entry['code'], entry['resolution'] or '断开外部供电路径')))
        for domain_id in sorted(entry['domains']):
            by_domain.setdefault(domain_id, []).append(step_id)
        if entry['domains']:
            for domain_id in sorted(entry['domains']):
                domain = ctx.domain(domain_id)
                if domain is None:
                    continue
                # deterministic order of prerequisite ids per domain
                by_domain[domain_id] = sorted(set(by_domain[domain_id]))
    return by_domain


# ---------------------------------------------------------------------------
# removable load isolation steps


def _removable_load_steps(ctx, add, statuses):
    info = {'domain': {}, 'assembly': []}
    for domain in ctx.domains:
        if not domain.get('removable_load'):
            continue
        step_id = 'I2-LOAD-%s' % domain['id']
        missing, reasons = [], []
        _blocked_state(statuses, ['I1-OFF-001'], missing, reasons)
        status = STATUS_BLOCKED if missing else STATUS_READY
        add(make_step(
            step_id=step_id,
            group='I2',
            title='可分离负载隔离：%s' % domain['id'],
            purpose='首次上电前确保 %r 上的可分离负载/模块断开，使空载上电'
                    '现象可解释。' % domain['net'],
            prerequisites=[prerequisite_step(
                'I1-OFF-001', 'board de-energised before changing loads')],
            procedure=[
                '确认 %s（%s）上的可分离负载/模块已拆下或从 %r 断开；'
                '不得带未知负载首次上电。'
                % (domain['id'], domain['load'] or '未描述负载', domain['net']),
                '拍摄连接状态照片；记录任何无法断开的负载及其原因。',
            ],
            expected_behavior='该电源轨首次上电时为空载/仅声明负载；连接负载'
                              '由独立的 I2-CONNECT-* 步骤在验证后进行。',
            required_evidence=[
                evidence_item('photo', '可分离负载/模块断开状态照片'),
                evidence_item('inspection_note', '断开状态与无法断开项记录'),
            ],
            status=status,
            blocked_reason='; '.join(reasons) if reasons else None,
            missing_information=missing,
            required=True,
            notes='本步骤只负责隔离；负载的连接是独立步骤，负载电流未声明前'
                  '不得连接。'))
        info['domain'][domain['id']] = step_id
    for load in ctx.assemblies['removable_loads']:
        step_id = 'I2-LOAD-ASM-%s' % _sanitize(load['designator'])
        missing, reasons = [], []
        _blocked_state(statuses, ['I1-OFF-001'], missing, reasons)
        status = STATUS_BLOCKED if missing else STATUS_READY
        state = '默认已连接' if load['default_connected'] else '默认未连接'
        add(make_step(
            step_id=step_id,
            group='I2',
            title='可分离负载隔离：%s' % load['designator'],
            purpose='首次上电前确认声明的可分离负载处于断开状态，避免未知'
                    '负载影响上电判读。',
            prerequisites=[prerequisite_step(
                'I1-OFF-001', 'board de-energised before changing loads')],
            procedure=[
                '确认可分离负载 %s（%s，%s）已断开；不得带未知负载首次上电。'
                % (load['designator'],
                   load['description'] or '未描述', state),
                '拍摄连接状态照片并记录任何无法断开的原因。',
            ],
            expected_behavior='声明的可分离负载在首次上电时保持断开。',
            required_evidence=[
                evidence_item('photo', '可分离负载 %s 断开状态照片'
                                       % load['designator']),
                evidence_item('inspection_note', '连接状态记录'),
            ],
            status=status,
            blocked_reason='; '.join(reasons) if reasons else None,
            missing_information=missing,
            required=True,
            notes='来自 assemblies.removable_loads 的声明；连接动作见独立的'
                  'I2-CONNECT-ASM-%s 步骤。' % _sanitize(load['designator'])))
        info['assembly'].append({
            'step_id': step_id,
            'designator': load['designator'],
            'description': load['description'] or '未描述',
            'default_connected': load['default_connected'],
        })
    return info


# ---------------------------------------------------------------------------
# per-domain first power-up


def _sequence_step(ctx, add, statuses, domain_id, *, order, dag,
                   external_by_domain, load_info, firmware_id,
                   first_sequence):
    domain = ctx.domain(domain_id)
    if domain is None:
        return None
    step_id = 'I2-SEQ-%s' % domain_id
    ordered = set(order)
    cycle_nodes = set()
    for cycle in (dag or {}).get('cycles') or []:
        cycle_nodes.update(cycle)
    missing, reasons = [], []

    if domain_id not in ordered:
        if domain_id in cycle_nodes:
            detail = '; '.join(' -> '.join(cycle)
                               for cycle in (dag.get('cycles') or []))
            missing.append('a resolvable power-domain dependency order: '
                           'domain %r is part of a cycle (%s)'
                           % (domain_id, detail))
            reasons.append('the declared power-domain graph contains a cycle; '
                           'there is no valid first-power-up order')
        else:
            missing.append('a resolvable power-domain dependency order for %r '
                           '(it is excluded from the topological order because '
                           'of a cycle)' % domain_id)
            reasons.append('the domain is excluded from the declared order')
    scope_missing, scope_reasons = _scope_missing(ctx)
    missing.extend(scope_missing)
    reasons.extend(scope_reasons)

    prerequisites = [
        prerequisite_step('I1-OFF-001',
                          'external supplies disconnected / board de-energised'),
        prerequisite_step('I1-OFF-DISCHARGE',
                          'bulk capacitance discharged and verified'),
        prerequisite_step('I1-OFF-RES-%s' % domain_id,
                          'rail-to-ground short check completed'),
    ]
    for dependency in domain['depends_on']:
        dependency_id = dependency['domain']
        if dependency_id in ordered:
            prerequisites.append(prerequisite_step(
                'I2-SEQ-%s' % dependency_id,
                dependency['reason'] or 'preceding rail verified'))
        else:
            missing.append('a resolvable dependency on domain %r'
                           % dependency_id)
            reasons.append('dependency %r has no valid order' % dependency_id)
    if firmware_id and firmware_id in statuses:
        prerequisites.append(prerequisite_step(
            firmware_id, 'firmware/debugger precondition recorded'))
    for external_id in external_by_domain.get(domain_id, []):
        prerequisites.append(prerequisite_step(
            external_id,
            'external supply/backfeed path physically disconnected'))
    domain_load_id = load_info['domain'].get(domain_id)
    if domain_load_id:
        prerequisites.append(prerequisite_step(
            domain_load_id, 'removable load isolated for first energise'))
    if first_sequence:
        for item in load_info['assembly']:
            prerequisites.append(prerequisite_step(
                item['step_id'],
                'declared removable load disconnected before first energise'))
        if 'before_first_energize' in (ctx.policy.get(
                'human_confirmation_points') or []):
            prerequisites.append(prerequisite_condition(
                'human confirmation is required before the first energise',
                source_ref='user_policy.human_confirmation_points'))

    seen = set()
    unique_prerequisites = []
    for prerequisite in prerequisites:
        key = (prerequisite.get('kind'),
               prerequisite.get('step_id') or prerequisite.get('text'))
        if key in seen:
            continue
        seen.add(key)
        unique_prerequisites.append(prerequisite)
    prerequisites = unique_prerequisites
    _blocked_state(
        statuses,
        [prerequisite['step_id'] for prerequisite in prerequisites
         if prerequisite.get('kind') == 'step'],
        missing, reasons)

    op_min = domain['operating_min_v']
    op_max = domain['operating_max_v']
    absolute = domain['absolute_max_v']
    nominal = domain['nominal_v']
    target = nominal if nominal is not None else op_min
    if op_min is None or op_max is None:
        missing.append('power_domains[%s].operating_min_v/operating_max_v '
                       '(declared working range)' % domain_id)
        reasons.append('the declared operating range is incomplete; no '
                       'voltage target can be derived')
    elif target is None:
        missing.append('power_domains[%s].nominal_v/operating_min_v '
                       '(declared voltage target)' % domain_id)
        reasons.append('no declared target voltage exists')
    elif target < op_min or target > op_max:
        missing.append('power_domains[%s].nominal_v inside the declared '
                       'operating range' % domain_id)
        reasons.append('the declared target voltage is outside the operating '
                       'range')

    supplies = ctx.supplies()
    supply = supplies[0] if supplies else None
    if supply is None:
        missing.append('declared current-limited supply (equipment.supplies)'
                       '（限流电源未声明）')
        reasons.append('no supply is declared; energising cannot be bounded')
    elif supply['max_voltage_v'] is not None and op_max is not None \
            and supply['max_voltage_v'] < op_max:
        missing.append('supply %s max_voltage_v >= operating_max %s V'
                       % (supply['id'], _fmt(op_max)))
        reasons.append('the declared supply cannot reach the operating maximum')

    points = ctx.testpoints_for(domain['net'])
    usable = [point for point in points if point['reachability_verified']]
    testpoint = usable[0] if usable else None
    if not usable:
        missing.append('declared reachable testpoint on rail %r '
                       '(power_domains[%s].net)' % (domain['net'], domain_id))
        reasons.append('the rail voltage cannot be measured at a declared '
                       'testpoint')

    meters = ctx.multimeters()
    meter = meters[0] if meters else None
    if meter is None:
        missing.append('declared multimeter (equipment.multimeters) for rail '
                       'voltage measurement（上电电压测量用万用表未声明）')
        reasons.append('no multimeter is declared')
    elif meter['dc_voltage_max_v'] is not None and op_max is not None \
            and meter['dc_voltage_max_v'] < op_max:
        missing.append('multimeter %s dc_voltage_max_v >= operating_max %s V'
                       % (meter['id'], _fmt(op_max)))
        reasons.append('the declared multimeter cannot measure the rail '
                       'voltage range')

    policy_object = ctx.conditions.get('current_limit_policy')
    startup = domain.get('startup_current') or {}
    runtime_spec = (domain.get('runtime_current')
                    or domain.get('static_current') or {})
    startup_value = startup.get('value')
    runtime_value = runtime_spec.get('value')
    if startup_value is None:
        missing.append('power_domains[%s].startup_current (启动电流): no '
                       'declared startup current' % domain_id)
        reasons.append('the startup current is not declared; the current '
                       'limit cannot be justified')
    if runtime_value is None:
        missing.append('power_domains[%s].runtime_current/static_current '
                       '(运行电流): no declared runtime current' % domain_id)
        reasons.append('the runtime current is not declared; the current '
                       'limit cannot be justified')
    limit = None
    if policy_object is None or policy_object.get('value') is None:
        missing.append('operating_conditions.current_limit_policy '
                       '(限流策略与依据): no declared current-limit policy')
        reasons.append('no current_limit_policy is declared; no current limit '
                       'may be invented')
    else:
        limit = policy_object['value']
        if supply is not None and supply.get('max_current_a') is not None \
                and supply['max_current_a'] < limit:
            missing.append('supply %s max_current_a >= declared current limit '
                           '%s A' % (supply['id'], _fmt(limit)))
            reasons.append('the declared supply cannot provide the declared '
                           'current limit')
        policy_ceiling = ctx.policy.get('max_current_a')
        if policy_ceiling is not None and policy_ceiling < limit:
            missing.append('user_policy.max_current_a >= '
                           'operating_conditions.current_limit_policy '
                           '(%s A > %s A); a reduced limit must be declared '
                           'and confirmed' % (_fmt(policy_ceiling),
                                              _fmt(limit)))
            reasons.append('the declared current limit exceeds the user '
                           'policy current ceiling')
        if startup_value is not None and limit < startup_value:
            missing.append('a current limit >= declared startup current: '
                           'limit %s A is below startup %s A'
                           '（启动浪涌/反复重启风险，不可视为安全）'
                           % (_fmt(limit), _fmt(startup_value)))
            reasons.append(
                'the declared current limit %s A is below the declared '
                'startup current %s A; startup inrush will brown out or '
                'restart the board, so this limit is not safe'
                % (_fmt(limit), _fmt(startup_value)))
        if runtime_value is not None and limit < runtime_value:
            missing.append('a current limit >= declared runtime current: '
                           'limit %s A is below runtime %s A'
                           % (_fmt(limit), _fmt(runtime_value)))
            reasons.append(
                'the declared current limit %s A is below the declared '
                'runtime current %s A; normal operation would current-limit'
                % (_fmt(limit), _fmt(runtime_value)))
    protection = domain.get('protection') or {}
    protection_limit = protection.get('current_limit_a')
    if protection_limit is not None and startup_value is not None \
            and protection_limit < startup_value:
        missing.append(
            'power_domains[%s].protection.current_limit_a >= startup current '
            '(board protection %s A < startup %s A)'
            % (domain_id, _fmt(protection_limit), _fmt(startup_value)))
        reasons.append('the declared on-board protection limit %s A is below '
                       'the startup current %s A'
                       % (_fmt(protection_limit), _fmt(startup_value)))

    window = ctx.conditions.get('observation_window_s')
    window_value = window.get('value') if window else None
    if window_value is None:
        missing.append('operating_conditions.observation_window_s '
                       '(观察窗口依据): no declared observation window; no '
                       'exact number of seconds is invented')
        reasons.append('the observation window has no declared basis')

    missing = _unique(missing)
    reasons = _unique(reasons)
    status = STATUS_BLOCKED if (missing or reasons) else STATUS_READY
    blocked_reason = ('; '.join(reasons) if reasons
                      else ('; '.join(missing[:4]) if missing else None))

    procedure = [
        '确认断电前提已完成：外部供电/可回灌路径断开（I1-OFF-001）、'
        '储能电容放电（I1-OFF-DISCHARGE）、%s 对地短路排查'
        '（I1-OFF-RES-%s）；并确认所有声明的前级电源域已验证。'
        % (domain['net'], domain_id),
    ]
    if target is not None and op_min is not None and op_max is not None:
        procedure.append(
            '设置限流电源 %s 电压为 %s V：工作范围 %s–%s V（来自 '
            'operating_min_v/operating_max_v），最大允许设置 %s V；绝对最大值'
            ' %s V 仅是损坏边界，禁止作为设定值或通过判据。'
            % (supply['id'] if supply else '（未声明电源）', _fmt(target),
               _fmt(op_min), _fmt(op_max), _fmt(op_max), _fmt(absolute)))
    else:
        procedure.append('电压设定：输入未声明完整工作范围，不得按任何默认值'
                         '上电。')
    if limit is not None:
        procedure.append(
            '限流设置 %s A：来源 operating_conditions.current_limit_policy'
            '（basis=%s%s%s）；不得使用任何未声明的默认限流值。'
            % (_fmt(limit), policy_object.get('basis') or '未声明',
               '，source_ref=%s' % policy_object['source_ref']
               if policy_object.get('source_ref') else '',
               '，conditions=%s' % policy_object['conditions']
               if policy_object.get('conditions') else ''))
        procedure.append(
            '限流校核：启动电流 %s（%s），运行/静态电流 %s（%s），板级保护'
            '限流 %s；限流低于已知启动电流会造成启动浪涌与反复重启，不能'
            '称为安全。'
            % (_fmt(startup_value), startup.get('basis') or '未声明',
               _fmt(runtime_value), runtime_spec.get('basis') or '未声明',
               _fmt(protection_limit)))
    else:
        procedure.append('限流设置：缺少声明依据（current_limit_policy 或'
                         '启动/运行电流），本步骤不得上电，更不得套用任何'
                         '默认限流值。')
    if window_value is not None:
        procedure.append(
            '观察窗口：上电后在声明窗口 %s s 内持续观察并记录（依据 %s%s）；'
            '窗口结束前不得判定通过。'
            % (_fmt(window_value), window.get('basis') or '未声明',
               '，source_ref=%s' % window['source_ref']
               if window.get('source_ref') else ''))
    else:
        procedure.append('观察窗口：输入未声明有依据的窗口，不编造精确秒数；'
                         '只记录实际观察过程，本步骤不能作为通过判据。')
    if testpoint is not None and meter is not None:
        procedure.append(
            '测量：用万用表 %s 的 DC 电压档在 %s（%s）对 %s 测量，记录上电'
            '瞬间、窗口内与窗口结束时的读数；工作范围 %s–%s V。'
            % (meter['id'], testpoint['id'], domain['net'],
               domain['ground_net'], _fmt(op_min), _fmt(op_max)))
    else:
        procedure.append('测量：该电源轨缺少已验证测试点或万用表，无法按'
                         '声明范围测量；先补齐测量条件。')
    procedure.append(
        '连接与上电：按声明的供电路径 %r 连接电源并确认极性；确认断开的'
        '外部路径/调试线缆仍保持断开，然后上电。'
        % (domain['source'] or '未声明'))
    procedure.append(
        '恢复前提：任何 STOP/失败之后，必须先断电并重新完成 I1-OFF-001 与 '
        'I1-OFF-DISCHARGE、排除原因并重新通过该电源域的对地检查，才允许再次'
        '上电；不得直接复电或“再试一次”。')
    procedure.append('任何 STOP 条件出现时立即断电并保持断电，转入失败分支，'
                     '不“观察一下再说”。')

    if op_min is not None and op_max is not None and limit is not None \
            and window_value is not None:
        expected = (
            '上电后 %s s 观察窗口内 %r 维持在 %s–%s V（工作范围，非绝对'
            '最大值）；电源电流不超过 %s A；无冒烟/异味/异常发热；前级电源'
            '无明显跌落。'
            % (_fmt(window_value), domain['net'], _fmt(op_min), _fmt(op_max),
               _fmt(limit)))
    elif window_value is None:
        expected = ('观察窗口缺少声明依据：无法给出有依据的预期现象，只能'
                    '记录实际行为，不得判定通过。')
    else:
        expected = ('输入不足（电压范围/限流/观察窗口任一项缺失）：不给出'
                    '通过性预期，只记录实际行为。')

    stop_conditions = []
    if absolute is not None:
        stop_conditions.append(stop_condition(
            'I2_ABSOLUTE_MAX',
            '任一电压读数达到或超过声明绝对最大值 %s V' % _fmt(absolute),
            threshold=absolute, quantity='voltage', unit='V',
            source_ref='power_domains[%s].absolute_max_v' % domain_id))
    if limit is not None:
        stop_conditions.append(stop_condition(
            'I2_CURRENT_LIMIT',
            '电源进入恒流或电流达到声明限流 %s A' % _fmt(limit),
            threshold=limit, quantity='current', unit='A',
            source_ref='operating_conditions.current_limit_policy'))
    policy_ceiling = ctx.policy.get('max_current_a')
    if policy_ceiling is not None and (limit is None
                                       or policy_ceiling < limit):
        stop_conditions.append(stop_condition(
            'I2_POLICY_CURRENT',
            '电流超过 user_policy.max_current_a %s A' % _fmt(policy_ceiling),
            threshold=policy_ceiling, quantity='current', unit='A',
            source_ref='user_policy.max_current_a'))
    if op_min is not None:
        stop_conditions.append(stop_condition(
            'I2_UNDERVOLTAGE',
            '电源轨低于声明工作下限 %s V 或前级异常跌落' % _fmt(op_min),
            threshold=op_min, quantity='voltage', unit='V',
            source_ref='power_domains[%s].operating_min_v' % domain_id))
    stop_conditions.append(stop_condition(
        'I2_SMOKE_ODOUR_HEAT',
        '冒烟、异味、异常发热、电弧或器件变色（定性，无声明温度阈值）'))
    stop_conditions = _unique_items(stop_conditions)

    refs = sorted({reference for reference in (
        startup.get('source_ref'), runtime_spec.get('source_ref'),
        (policy_object or {}).get('source_ref'),
        (window or {}).get('source_ref')) if reference})

    point_text = ('%s (%s)' % (testpoint['id'], domain['net'])
                  if testpoint is not None
                  else '%s (no verified testpoint)' % domain['net'])
    measurement = {
        'quantity': 'voltage',
        'point': point_text,
        'reference': domain['ground_net'],
        'range': ({'min': op_min, 'max': op_max, 'unit': 'V'}
                  if op_min is not None and op_max is not None else None),
        'criterion_status': ('defined'
                             if op_min is not None and op_max is not None
                             else 'needs_interpretation'),
        'basis': 'declared operating_min_v..operating_max_v; absolute_max_v '
                 'is a damage limit and is never used as the test target',
        'source_refs': refs,
    }
    wiring = {
        'measure_at': point_text,
        'reference': domain['ground_net'],
        'probe': 'standard DMM probes; do not connect an earth-referenced '
                 'scope ground clip to a non-ground node',
        'notes': '先设定限流再上电；观察窗口内不得改变设置。',
    }
    equipment = []
    if supply is not None:
        equipment.append(equipment_item(
            supply['id'], 'current-limited DC supply',
            settings={'voltage_v': target,
                      'voltage_range_v': [op_min, op_max],
                      'max_allowed_voltage_v': op_max,
                      'current_limit_a': limit},
            verified=True,
            detail='declared supply; settings are manual instructions and are '
                   'not applied by this tool'))
    if meter is not None:
        equipment.append(equipment_item(
            meter['id'], 'DC voltage measurement',
            settings={'mode': 'dc_voltage', 'range_v': op_max,
                      'resolution_v': meter['dc_voltage_resolution_v']},
            verified=True))
    required_evidence = [
        evidence_item('supply_reading',
                      '上电时记录的电压设定、电流限值与电源显示电流'),
        evidence_item('meter_reading',
                      '在声明观察窗口内对 %s 的 DC 电压读数（含时间）'
                      % (testpoint['id'] if testpoint else domain['net'])),
        evidence_item('inspection_note',
                      '窗口内有无冒烟/异味/异常发热的人工观察记录'),
    ]
    protection_note = ('板级 protection.current_limit_a=%s。'
                       % _fmt(protection_limit)
                       if protection_limit is not None
                       else '板级 protection.current_limit_a 未声明。')
    notes = ('absolute_max_v=%s 只是损坏上限，不是测试目标；限流值 %s A 来源 '
             'current_limit_policy。%s failure branch FT-%s 为故障树生成器'
             '固定命名（faults 由 I5 实现；未实现时按 STOP 人工处理）。'
             % (_fmt(absolute), _fmt(limit), protection_note, step_id))

    add(make_step(
        step_id=step_id,
        group='I2',
        title='首次上电：%s（%s）' % (domain_id, domain['net']),
        purpose='按依赖顺序对 %s 做首次上电与电压验证；电压范围、限流、'
                '观察窗口均取声明依据，本工具不执行上电。' % domain['net'],
        prerequisites=prerequisites,
        equipment=equipment,
        wiring=wiring,
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        stop_conditions=stop_conditions,
        failure_branches=['FT-%s' % step_id],
        required_evidence=required_evidence,
        status=status,
        blocked_reason=blocked_reason,
        missing_information=missing,
        required=True,
        source_refs=refs,
        notes=notes))
    return step_id


def _unique_items(items):
    """Deduplicate stop-condition dicts by their stable code."""
    seen = set()
    result = []
    for item in items:
        code = item.get('code')
        if code in seen:
            continue
        seen.add(code)
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# load connection steps (separate from isolation)


def _connect_domain_step(ctx, add, statuses, domain_id, sequence_id,
                         load_info):
    domain = ctx.domain(domain_id)
    if domain is None:
        return None
    step_id = 'I2-CONNECT-%s' % domain_id
    source_load_step = load_info['domain'].get(domain_id)
    missing = [
        'declared load current and acceptance criterion for the removable '
        'load on rail %r（可分离负载电流/验收判据未声明）' % domain['net'],
        'declared connection target/polarity of the removable load'
        '（负载连接目标与极性未声明）',
    ]
    reasons = [
        'the removable load current is not declared, so connecting it cannot '
        'be bounded by a declared current limit or acceptance criterion',
    ]
    _blocked_state(statuses, [sequence_id], missing, reasons)
    op_min = domain['operating_min_v']
    op_max = domain['operating_max_v']
    absolute = domain['absolute_max_v']
    meter = ctx.multimeters()[0] if ctx.multimeters() else None
    supply = ctx.supplies()[0] if ctx.supplies() else None
    measurement = {
        'quantity': 'voltage',
        'point': '%s (%s)' % (domain['net'], domain_id),
        'reference': domain['ground_net'],
        'range': ({'min': op_min, 'max': op_max, 'unit': 'V'}
                  if op_min is not None and op_max is not None else None),
        'criterion_status': ('defined'
                             if op_min is not None and op_max is not None
                             else 'needs_interpretation'),
        'basis': 'declared operating range after the removable load is '
                 'connected; the load current itself is not declared',
        'source_refs': [],
    }
    procedure = [
        '仅在 %s 已按声明范围验证且未触发 STOP 后执行本步骤。' % sequence_id,
        '确认可分离负载的类型、极性、供电轨与额定电流；本输入未声明该'
        '负载电流，缺少声明依据前不得连接。',
        '连接后立即测量母线电压与电源电流；若电压跌出工作范围或电流超过'
        '声明限流，立即断开并 STOP。',
        '记录连接前后的读数与照片；不得以“先接上看看”代替声明依据。',
    ]
    stops = []
    if absolute is not None:
        stops.append(stop_condition(
            'I2_ABSOLUTE_MAX',
            '任一电压读数达到或超过声明绝对最大值 %s V' % _fmt(absolute),
            threshold=absolute, quantity='voltage', unit='V',
            source_ref='power_domains[%s].absolute_max_v' % domain_id))
    policy_object = ctx.conditions.get('current_limit_policy')
    if policy_object and policy_object.get('value') is not None:
        stops.append(stop_condition(
            'I2_CURRENT_LIMIT',
            '连接负载后电流达到声明限流 %s A'
            % _fmt(policy_object['value']),
            threshold=policy_object['value'], quantity='current', unit='A',
            source_ref='operating_conditions.current_limit_policy'))
    stops.append(stop_condition(
        'I2_SMOKE_ODOUR_HEAT', '冒烟、异味、异常发热或器件变色'))
    equipment = []
    if supply is not None:
        equipment.append(equipment_item(
            supply['id'], 'current-limited DC supply',
            settings={'current_limit_a': (policy_object or {}).get('value')},
            verified=True))
    if meter is not None:
        equipment.append(equipment_item(
            meter['id'], 'DC voltage measurement',
            settings={'mode': 'dc_voltage'}, verified=True))
    add(make_step(
        step_id=step_id,
        group='I2',
        title='连接可分离负载：%s' % domain_id,
        purpose='在电源轨验证后按独立步骤连接可分离负载，避免把负载问题'
                '混入空载上电判读。',
        prerequisites=[prerequisite_step(
            sequence_id, 'rail must be verified before a load is connected')]
        + ([prerequisite_step(source_load_step,
                              'load must be isolated before it is connected')]
           if source_load_step else []),
        equipment=equipment,
        wiring={'measure_at': measurement['point'],
                'reference': domain['ground_net'],
                'probe': 'DMM probes plus the supply current display',
                'notes': '连接负载前确认限流仍为声明值。'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior='连接负载后电源轨仍处于声明工作范围，电流不超过'
                          '声明限流。',
        stop_conditions=stops,
        failure_branches=['FT-%s' % step_id],
        required_evidence=[
            evidence_item('photo', '负载连接状态照片'),
            evidence_item('meter_reading', '连接负载后的电源轨电压/电流读数'),
            evidence_item('inspection_note', '人工观察记录'),
        ],
        status=STATUS_BLOCKED,
        blocked_reason='; '.join(reasons),
        missing_information=_unique(missing),
        required=False,
        notes='与 I2-LOAD-* 分开：先隔离，后连接；负载电流未声明时保持 '
              'BLOCKED，不默认满量程或长时间加载。'))
    return step_id


def _connect_assembly_step(ctx, add, statuses, item, last_sequence_id):
    step_id = 'I2-CONNECT-ASM-%s' % _sanitize(item['designator'])
    missing = [
        'declared supply rail and load current for removable load %s'
        '（该可分离负载的供电轨与电流未声明）' % item['designator'],
        'declared acceptance criterion after connecting %s'
        '（连接后的验收判据未声明）' % item['designator'],
    ]
    reasons = [
        'the removable load supply rail and current are not declared; it '
        'cannot be connected under a bounded current limit',
    ]
    _blocked_state(statuses, [last_sequence_id] if last_sequence_id else [],
                   missing, reasons)
    procedure = [
        '确认 %s（%s）的供电轨、极性与额定电流；本输入未声明，缺少声明'
        '依据前不得连接。'
        % (item['designator'], item['description']),
        '若将来补充声明：在对应电源轨验证完成后连接，并立即测量母线电压与'
        '电流；出现电压跌落或过流立即断开并 STOP。',
        '记录连接前后的读数与照片。',
    ]
    add(make_step(
        step_id=step_id,
        group='I2',
        title='连接可分离负载：%s' % item['designator'],
        purpose='把声明的可分离负载连接作为独立步骤，避免与首次上电/'
                '隔离步骤混在一起。',
        prerequisites=([prerequisite_step(
            last_sequence_id,
            'all declared rails verified before connecting an external load')]
            if last_sequence_id else []),
        procedure=procedure,
        expected_behavior='负载由独立步骤连接；未声明负载电流前不得连接。',
        stop_conditions=[stop_condition(
            'I2_SMOKE_ODOUR_HEAT', '冒烟、异味、异常发热或器件变色')],
        failure_branches=['FT-%s' % step_id],
        required_evidence=[
            evidence_item('photo', '%s 连接状态照片' % item['designator']),
            evidence_item('inspection_note', '连接前的声明核对记录'),
        ],
        status=STATUS_BLOCKED,
        blocked_reason='; '.join(reasons),
        missing_information=_unique(missing),
        required=False,
        notes='来自 assemblies.removable_loads；与 I2-LOAD-ASM-%s 分开，'
              '未声明供电轨/电流时保持 BLOCKED。'
              % _sanitize(item['designator'])))
    return step_id
