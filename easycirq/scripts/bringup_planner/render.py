"""Render plan artifacts: Markdown checklist, blank result JSON/CSV, explain.

Rendering is deterministic and offline.  The blank result template deliberately
marks every step ``not_run`` with ``source=unset``: a fresh template can never be
mistaken for real measurements.
"""
from __future__ import annotations

from . import RESULT_SCHEMA, TOOL_NAME, TOOL_VERSION
from .units import CANONICAL_UNITS
from .util import iso_now

STATUS_LABELS = {
    'ready': '可执行',
    'blocked': 'BLOCKED',
    'unsupported': 'UNSUPPORTED',
    'advisory': 'ADVISORY',
}


def _fmt_range(measurement):
    if not measurement:
        return ''
    span = measurement.get('range') or {}
    lower = span.get('min')
    upper = span.get('max')
    unit = span.get('unit') or ''
    if lower is None and upper is None:
        return '无自动判据（%s）' % (measurement.get('criterion_status')
                                    or 'undefined')
    if lower is None:
        return '≤ %s %s' % (_num(upper), unit)
    if upper is None:
        return '≥ %s %s' % (_num(lower), unit)
    return '%s–%s %s' % (_num(lower), _num(upper), unit)


def _num(value):
    if isinstance(value, float):
        return '%.6g' % value
    return str(value)


def _cell(value):
    text = '' if value is None else str(value)
    return text.replace('|', '\\|').replace('\n', ' ')


def render_markdown(plan):
    lines = []
    add = lines.append
    design = plan['design']
    scope = plan['scope']
    summary = plan['summary']
    add('# 首板上电与功能测试计划（人工执行，工具不执行）')
    add('')
    add('> 工程：**%s / %s**　BOM：%s　装配：%s'
        % (design['project'], design['revision'], design['bom_version'],
           design['assembly_version']))
    add('>')
    add('> 输入 SHA-256：`%s`　计划 SHA-256：`%s`'
        % (plan['input']['sha256'], plan['hashes']['plan_sha256']))
    add('>')
    add('> 工具：%s %s　生成时间：%s'
        % (TOOL_NAME, TOOL_VERSION, plan['generated_at']))
    add('>')
    add('> **本文件不是测试执行证据。** 计划生成器不连接仪器、不烧录、不上电、'
        '不执行任何命令；所有步骤必须由有资质的人员按现场条件人工执行，'
        '结果另行记录并与计划哈希绑定。')
    add('')

    add('## 1. 适用范围与安全边界')
    add('')
    add('| 项 | 值 |')
    add('|---|---|')
    add('| 范围判定 | `%s` |' % scope['status'])
    add('| 是否允许上电步骤 | %s |'
        % ('是（仍需人工确认点）' if scope['energize_allowed'] else '否'))
    add('| 声明供电类别 | `%s` |' % scope.get('supply_class'))
    add('| 最高工作电压 | %s V |'
        % _num(scope['voltage_envelope']['max_operating_v']))
    add('| 本工具支持上限 | %s V（工作）/ %s V（绝对） |'
        % (_num(scope['voltage_envelope']['supported_max_operating_v']),
           _num(scope['voltage_envelope']['supported_max_absolute_v'])))
    add('')
    if scope['reasons']:
        add('范围判定依据：')
        for reason in scope['reasons']:
            add('- `%s`（%s）：%s' % (reason['code'], reason['severity'],
                                     reason['detail']))
        add('')
    if not scope['energize_allowed']:
        add('> **未生成可执行上电步骤。** 缺少安全边界、授权或超出首期范围时，'
            '工具只输出缺口与待确认项，不提供通用上电动作。')
        add('')

    add('## 2. 输入完整度与未决信息')
    add('')
    completeness = plan['input']['completeness']
    add('输入完整度（仅信息覆盖，不是通过判据）：%d/%d = %.1f%%'
        % (completeness['known'], completeness['total'],
           completeness['ratio'] * 100))
    add('')
    if completeness['missing']:
        add('缺失项编码：%s' % ', '.join('`%s`' % item
                                          for item in completeness['missing']))
        add('')
    if plan['unknowns']:
        add('### 未决信息（unknown）')
        add('')
        add('| 编码 | 主题 | 影响 | 需要补充 |')
        add('|---|---|---|---|')
        for item in plan['unknowns']:
            add('| `%s` | %s | %s | %s |'
                % (item['code'], _cell(item['topic']), _cell(item['detail']),
                   _cell('；'.join(item.get('needed') or []))))
        add('')
    if plan['equipment_gaps']:
        add('### 设备能力缺口')
        add('')
        for item in plan['equipment_gaps']:
            add('- `%s`（%s / %s）：%s'
                % (item['code'], item['equipment'], item['capability'],
                   item['detail']))
        add('')
    if plan['supply_conflicts']:
        add('### 外部供电路径冲突')
        add('')
        for item in plan['supply_conflicts']:
            add('- `%s` %s ↔ %s（%s）：%s'
                % (item['code'], item['path_id'], item['domain'],
                   'blocking' if item['blocking'] else 'declared',
                   item['resolution']))
        add('')

    add('## 3. 电源域依赖与执行顺序')
    add('')
    add('| 顺序 | 电源域 | 网络 | 工作范围 | 绝对最大 | 依赖 |')
    add('|---|---|---|---|---|---|')
    dag = plan['dag']['domains']
    domains = {item['id']: item for item in plan['power_domains']}
    nodes = {item['id']: item for item in dag['nodes']}
    for index, domain_id in enumerate(dag['order'], 1):
        domain = domains.get(domain_id, {})
        add('| %d | `%s` | `%s` | %s–%s V | %s V | %s |'
            % (index, domain_id, domain.get('net', ''),
               _num(domain.get('operating_min_v')),
               _num(domain.get('operating_max_v')),
               _num(domain.get('absolute_max_v')),
               ', '.join(nodes.get(domain_id, {}).get('depends_on') or [])))
    add('')
    if dag['cycles']:
        add('> **依赖环路：** %s。相关步骤不会被执行。'
            % '；'.join(' → '.join(cycle) for cycle in dag['cycles']))
        add('')
    if dag['missing_dependencies']:
        add('> **缺依赖：** %s'
            % '；'.join('%s 缺 %s' % (item['domain'], item['missing'])
                       for item in dag['missing_dependencies']))
        add('')

    add('## 4. 执行清单（人工逐步执行）')
    add('')
    add('| # | 步骤 ID | 组 | 内容 | 状态 | 必需 |')
    add('|---|---|---|---|---|---|')
    for step in plan['steps']:
        add('| %d | `%s` | %s | %s | %s | %s |'
            % (step['sequence'], step['step_id'], step['group'],
               _cell(step['title']), STATUS_LABELS.get(step['status'],
                                                       step['status']),
               '是' if step['required'] else '否'))
    add('')

    add('## 5. 步骤详情')
    add('')
    for step in plan['steps']:
        add('### %d. `%s` %s' % (step['sequence'], step['step_id'],
                                 step['title']))
        add('')
        add('- 状态：`%s`　分组：`%s`　必需：%s'
            % (step['status'], step['group'],
               '是' if step['required'] else '否'))
        if step['blocked_reason']:
            add('- 阻塞原因：%s' % step['blocked_reason'])
        if step['missing_information']:
            add('- 缺失信息：%s'
                % '；'.join('`%s`' % item for item in
                            step['missing_information']))
        add('- 目的：%s' % step['purpose'])
        if step['prerequisites']:
            add('- 前提：')
            for prereq in step['prerequisites']:
                if prereq['kind'] == 'step':
                    add('  - 步骤 `%s`%s'
                        % (prereq['step_id'],
                           '（%s）' % prereq['reason'] if prereq.get('reason')
                           else ''))
                else:
                    add('  - 条件：%s%s'
                        % (prereq['text'],
                           '（来源 `%s`）' % prereq['source_ref']
                           if prereq.get('source_ref') else ''))
        if step['equipment']:
            add('- 设备与设置：')
            for item in step['equipment']:
                state = '' if item.get('verified') else '，**能力未验证**'
                add('  - `%s`：%s%s%s'
                    % (item['equipment_id'], item['capability'],
                       ('，设置：%s' % item['settings'])
                       if item.get('settings') else '',
                       state))
        wiring = step['wiring']
        if wiring:
            add('- 接线/参考：测点 %s，参考 %s%s%s'
                % (wiring.get('measure_at') or '—',
                   wiring.get('reference') or '—',
                   '，探头/地夹：%s' % wiring['probe'] if wiring.get('probe')
                   else '',
                   '，注意：%s' % wiring['notes'] if wiring.get('notes')
                   else ''))
        if step['procedure']:
            add('- 操作：')
            for index, action in enumerate(step['procedure'], 1):
                add('  %d. %s' % (index, action))
        measurement = step['measurement']
        if measurement:
            add('- 测量：%s @ %s（参考 %s），允许范围：%s，判据状态：`%s`'
                % (measurement.get('quantity'), measurement.get('point'),
                   measurement.get('reference'), _fmt_range(measurement),
                   measurement.get('criterion_status')))
            if measurement.get('basis'):
                add('- 判据依据：%s%s'
                    % (measurement['basis'],
                       '，来源 %s' % ', '.join(measurement['source_refs'])
                       if measurement.get('source_refs') else ''))
        if step['expected_behavior']:
            add('- 预期现象：%s' % step['expected_behavior'])
        if step['stop_conditions']:
            add('- 停止条件：')
            for item in step['stop_conditions']:
                threshold = item.get('threshold') or {}
                text = ''
                if threshold:
                    text = '（阈值 %s %s）' % (_num(threshold.get('value')),
                                               threshold.get('unit') or '')
                add('  - `%s`：%s%s；动作：%s'
                    % (item['code'], item['description'], text,
                       item['action']))
        if step['failure_branches']:
            add('- 失败分支：%s'
                % ', '.join('`%s`' % item for item in
                            step['failure_branches']))
        if step['required_evidence']:
            add('- 必需证据：')
            for item in step['required_evidence']:
                add('  - `%s`：%s' % (item['kind'], item['description']))
        if step['source_refs']:
            add('- 资料引用：%s' % ', '.join(step['source_refs']))
        if step['notes']:
            add('- 备注：%s' % step['notes'])
        add('')

    add('## 6. 故障定位树（假设与下一步，不是已确定结论）')
    add('')
    if not plan['fault_trees']:
        add('（无：故障树仅在存在可判定测量与已知阈值时生成；缺信息时保留 '
            'unknown，不列猜测清单。）')
        add('')
    for tree in plan['fault_trees']:
        add('### 故障树 `%s`：%s' % (tree['id'], tree['symptom']))
        add('')
        if tree.get('entry_steps'):
            add('- 入口步骤：%s'
                % ', '.join('`%s`' % item for item in tree['entry_steps']))
        if tree.get('boundary'):
            add('- 边界：%s' % tree['boundary'])
        add('')
        for node in tree.get('nodes') or []:
            indent = '  ' * int(node.get('depth', 0))
            suffix = ''
            if node.get('terminal'):
                suffix = ' → **%s**' % node['terminal'].upper()
            add('%s- `%s` [%s] %s%s'
                % (indent, node['node_id'], node['kind'],
                   node.get('text') or node.get('hypothesis') or '', suffix))
            if node.get('evidence'):
                add('%s  证据：%s' % (indent, node['evidence']))
            if node.get('decidable'):
                add('%s  可判定条件：%s' % (indent, node['decidable']))
        add('')

    add('## 7. 结果记录与评估')
    add('')
    add('- 使用 `results-template.json` / `results-template.csv` 记录；'
        '每个步骤绑定本计划哈希与设计 revision。')
    add('- 状态只允许 `pass / fail / unknown / blocked / not_run`；'
        '未执行必须写 `not_run`，不得默认通过。')
    add('- 证据必须写相对路径、文件 SHA-256、采集时间与执行人；'
        '`source` 必须区分 `real_measurement / synthetic / manual_declaration`。')
    add('- 评估命令：`python -m bringup_planner evaluate --plan plan.json '
        '--results results.json --evidence-root evidence/`。')
    add('- 评估器只做离线一致性判定；它不能证明安规、EMC、温升、可靠性或'
        '量产一致性。')
    add('')
    add('## 8. 本计划不证明的内容')
    add('')
    for item in plan['notes']['not_proven']:
        add('- %s' % item)
    add('')
    return '\n'.join(lines) + '\n'


def _blank_step(step):
    measurement = step.get('measurement') or {}
    span = measurement.get('range') or {}
    return {
        'step_id': step['step_id'],
        'title': step['title'],
        'group': step['group'],
        'status': 'not_run',
        'source': 'unset',
        'instrument': None,
        'measured': None,
        'evidence': [],
        'executed_by': '',
        'executed_at': None,
        'stop_triggered': False,
        'notes': '',
        'exceptions': [],
        'expected': {
            'quantity': measurement.get('quantity'),
            'unit': span.get('unit') or (CANONICAL_UNITS.get(
                measurement.get('quantity') or '', None)),
            'min': span.get('min'),
            'max': span.get('max'),
            'criterion_status': measurement.get('criterion_status'),
        },
    }


def render_results_json(plan):
    return {
        'schema': RESULT_SCHEMA,
        'generator': TOOL_NAME + '-template',
        'generated_at': iso_now(),
        'plan_binding': {
            'plan_sha256': plan['hashes']['plan_sha256'],
            'input_sha256': plan['input']['sha256'],
            'input_semantic_sha256': plan['input']['semantic_sha256'],
            'revision': plan['design']['revision'],
            'tool_version': plan['tool_version'],
        },
        'executed_by': '',
        'source_kind': 'unset',
        'results': [_blank_step(step) for step in plan['steps']],
        'notes': 'Fill one entry per executed step. Never mark a step pass '
                 'without its required evidence. Synthetic records must set '
                 'source=synthetic and can never become a real-hardware PASS.',
    }


CSV_HEADER = [
    'step_id', 'group', 'title', 'status', 'source', 'instrument_model',
    'instrument_settings', 'quantity', 'measured_value', 'measured_unit',
    'expected_min', 'expected_max', 'expected_unit', 'probe_or_reference',
    'evidence_paths', 'evidence_sha256', 'executed_by', 'executed_at',
    'stop_triggered', 'notes', 'exceptions',
]


def render_results_csv(plan):
    rows = [CSV_HEADER]
    for step in plan['steps']:
        measurement = step.get('measurement') or {}
        span = measurement.get('range') or {}
        wiring = step.get('wiring') or {}
        rows.append([
            step['step_id'], step['group'], step['title'], 'not_run', 'unset',
            '', '', measurement.get('quantity') or '', '', '', span.get('min'),
            span.get('max'),
            span.get('unit') or '', wiring.get('measure_at') or '', '', '',
            '', '', 'false', '', '',
        ])
    return rows


def render_explain(plan, step_id=None):
    lines = []
    add = lines.append
    add('范围判定：%s（energize_allowed=%s）'
        % (plan['scope']['status'], plan['scope']['energize_allowed']))
    for reason in plan['scope']['reasons']:
        add('  - %s: %s' % (reason['code'], reason['detail']))
    add('电源域顺序：%s'
        % (' -> '.join(plan['dag']['domains']['order']) or '(none)'))
    if step_id:
        found = None
        for step in plan['steps']:
            if step['step_id'] == step_id:
                found = step
                break
        if found is None:
            return '未找到步骤 %r' % step_id
        add('步骤 %s：%s [%s]' % (step_id, found['title'], found['status']))
        add('  目的：%s' % found['purpose'])
        if found['blocked_reason']:
            add('  阻塞：%s' % found['blocked_reason'])
        for prereq in found['prerequisites']:
            add('  前提：%s' % (prereq.get('step_id') or prereq.get('text')))
        for action in found['procedure']:
            add('  - %s' % action)
        for item in found['required_evidence']:
            add('  证据：%s %s' % (item['kind'], item['description']))
        return '\n'.join(lines) + '\n'
    for step in plan['steps']:
        add('%-28s %-6s %-8s %s'
            % (step['step_id'], step['group'], step['status'],
               step['title']))
    add('')
    add('未决信息 %d 项；设备缺口 %d 项；故障树 %d 棵。'
        % (len(plan['unknowns']), len(plan['equipment_gaps']),
           len(plan['fault_trees'])))
    return '\n'.join(lines) + '\n'
