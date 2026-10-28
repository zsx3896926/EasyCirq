"""I5: bounded fault-localisation trees for observable step failures.

Consumes ``ctx.steps`` after I1-I4 have generated them and appends trees to
``ctx.trees``; the tree id is also recorded in the failing step's
``failure_branches``.  Placeholder ``FT-<step_id>`` entries for steps that get
no tree (blocked steps, steps without an observable failure) are removed so the
branch references stay consistent with the generated trees.  Each tree is a
hypothesis/next-step aid, **not** a claim that a component is damaged: it never
lists dozens of possible causes, never invents an ohmic threshold, and leaves a
branch ``unknown`` when the project declares no measurement or no known limit
instead of defaulting to normal.

Node order for every tree (per the task contract):

1. power/connection and prerequisite state;
2. mode / strapping / firmware precondition;
3. local measurement against the thresholds declared by the project
   (step ``measurement`` range, step ``stop_conditions`` thresholds and the
   rail ``absolute_max_v``).

Every STOP node is derived from a project-known threshold (or a conservative
qualitative hazard: smoke/odour/heat) that the generator itself already wrote
into the step; nothing here is a new universal criterion.
"""
from __future__ import annotations

from .steps import GROUP_ORDER, STATUS_READY

#: Hard bound on the size of one fault tree (contract: at most 12 nodes).
MAX_NODES_PER_TREE = 12

#: Hard bound on how many trees are generated for one plan (keeps output finite
#: and readable; only key observable steps get a tree).
MAX_TREES = 16

_FAULT_GROUPS = ('I2', 'I3', 'I4')
_NODE_KINDS = ('check', 'measure', 'stop', 'unknown', 'resolution')

_BOUNDARY = ('本树只是基于项目已声明阈值与可观测现象的假设与下一步检查：它不证明'
             '任何器件已损坏，也不替代器件级诊断；每个分支都必须记录证据，'
             '缺少测量或项目阈值时保持 unknown，不得默认 normal。')


def build(ctx):
    """Generate bounded fault trees into ``ctx.trees`` for key ready steps."""
    steps = getattr(ctx, 'steps', None) or []
    if not steps:
        return None
    eligible = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if step.get('status') != STATUS_READY:
            # A blocked step is never executed, so there is no observed failure
            # phenomenon to localise.
            continue
        if step.get('group') not in _FAULT_GROUPS:
            continue
        if not _observable(step):
            continue
        eligible.append((GROUP_ORDER.get(step.get('group'), 9), index, step))
    eligible.sort(key=lambda item: (item[0], item[1]))
    generated = 0
    for _order, _index, step in eligible:
        if generated >= MAX_TREES:
            break
        tree = _build_tree(ctx, step)
        if tree is None:
            continue
        if _append_tree(ctx, tree):
            _link_step(step, tree['id'])
            generated += 1
    _drop_dangling_branches(ctx, steps)
    return generated


# ---------------------------------------------------------------------------
# tree assembly


def _observable(step):
    """Only steps with an expected phenomenon or a measurement get a tree."""
    return bool(step.get('measurement') or step.get('expected_behavior')
                or step.get('stop_conditions'))


def _build_tree(ctx, step):
    step_id = step.get('step_id')
    if not isinstance(step_id, str) or not step_id:
        return None
    tree_id = 'FT-%s' % step_id
    domains = _step_domains(ctx, step)
    measurement = step.get('measurement') or {}
    stops = [item for item in (step.get('stop_conditions') or [])
             if isinstance(item, dict)]
    prerequisite_ids = _prerequisite_ids(step)

    nodes = []
    _start_node = _NodeBuilder(tree_id, nodes)

    # -- 1. power / connection / prerequisite state ------------------------
    if prerequisite_ids:
        _start_node.add(
            'check',
            '先核对前置步骤状态：%s 必须已记录 pass 且证据有效；任一未 pass '
            '时不得把本步现象当作本步自身故障。'
            % '、'.join('`%s`' % item for item in prerequisite_ids),
            evidence='前置步骤的结果记录与证据路径',
            decidable='全部前置步骤的结果为 pass 且有已验证证据；否则回到'
                      '前置步骤处理')
    _start_node.add(
        'check',
        '确认供电与连接与计划声明一致：电源电压目标、限流值、观察窗口、'
        '外部供电路径断开状态，以及测点/参考地是否按本步 wiring 声明连接。',
        evidence='电源设定照片/读数、连线照片、测点与参考地位置',
        decidable='电源设定与计划声明一致且外部供电路径按声明保持断开；'
                  '不一致时先纠正再复测')
    _start_node.add(
        'check',
        '断电后确认电源极性与板级短路/回灌迹象（有外部供电路径时先物理断开）。',
        evidence='断电状态照片、极性核对记录',
        decidable='极性正确且不存在来自外部路径的残余供电；极性错误或仍有'
                  '外部供电时不得复测上电')

    # -- 2. mode / strapping / firmware precondition -----------------------
    _add_mode_node(ctx, step, _start_node)

    # -- 3. local measurement against project-known limits -----------------
    range_text = _range_text(measurement, domains)
    threshold_stops = [item for item in stops
                       if isinstance(item.get('threshold'), dict)
                       and _is_number(item['threshold'].get('value'))]
    qualitative_stops = [item for item in stops
                         if not (isinstance(item.get('threshold'), dict)
                                 and _is_number(
                                     item['threshold'].get('value')))
                         and item.get('code')]
    if measurement:
        quantity = measurement.get('quantity')
        point = measurement.get('point') or '声明测点'
        reference = measurement.get('reference') or '声明参考地'
        criterion = measurement.get('criterion_status') or 'undefined'
        if range_text is not None:
            _start_node.add(
                'measure',
                '在 %s 对 %s 复测 %s（记录仪表型号/量程、时间与原始读数）。'
                % (point, reference, quantity),
                evidence='meter_reading/scope_capture 原始读数、截图或数据文件',
                decidable='读数落在计划声明范围内（%s）' % range_text,
                next_ids=['__resolution__'])
        elif criterion == 'qualitative':
            _start_node.add(
                'measure',
                '在 %s 对 %s 复测 %s（记录仪表型号/量程、时间与原始读数）；'
                '本步只有定性判据（%s），不得引用通用欧姆/电压阈值。'
                % (point, reference, quantity,
                   _clip(measurement.get('basis'), 120) or 'qualitative'),
                evidence='meter_reading/scope_capture 原始读数、截图或数据文件',
                decidable='符合本步声明的定性现象（见步骤 expected_behavior），'
                          '并记录原始读数',
                next_ids=['__resolution__'])
        else:
            _start_node.add(
                'measure',
                '在 %s 对 %s 复测 %s（记录仪表型号/量程、时间与原始读数）。'
                % (point, reference, quantity),
                evidence='meter_reading/scope_capture 原始读数、截图或数据文件',
                decidable='本步没有项目声明的数值判据（criterion_status=%s），'
                          '只能记录读数，不能判定 normal' % criterion,
                terminal='unknown')
    else:
        _start_node.add(
            'unknown',
            '本步没有可判定的测量（无 measurement）且失败现象是定性观察；'
            '保持 unknown，不把"看起来正常"当作通过。',
            evidence='人工观察记录（现象、时间、条件）',
            decidable='本步必须在计划中补充可判定的现象/测量后才可判定',
            terminal='unknown')

    # STOP node: only project-known thresholds or the conservative qualitative
    # hazard that the step itself already declares.
    stop_parts = []
    for item in threshold_stops:
        threshold = item['threshold']
        stop_parts.append(
            '`%s`：%s（阈值 %s %s）'
            % (item.get('code') or 'STOP', item.get('description') or '',
               _fmt(threshold.get('value')), threshold.get('unit') or ''))
    for domain in domains:
        absolute = _absolute_max(ctx, domain)
        if absolute is not None and not any(
                _same_threshold(item, absolute) for item in threshold_stops):
            stop_parts.append(
                '`ABSOLUTE_MAX`：%s 达到/超过声明绝对最大值 %s V'
                % (domain.get('net') or domain.get('id'), _fmt(absolute)))
    for item in qualitative_stops:
        stop_parts.append('`%s`：%s'
                          % (item.get('code') or 'STOP',
                             item.get('description') or ''))
    if stop_parts:
        _start_node.add(
            'stop',
            'STOP：' + '；'.join(stop_parts[:4])
            + '。任一条件满足时立即断电并保持断电，本树后续判定全部停止。',
            evidence='触发瞬间的读数、照片与时间；STOP 后不再上电',
            decidable='任一已声明 STOP 阈值被满足，或出现冒烟/异味/异常发热等'
                      '定性危险现象',
            terminal='stop')

    # Resolution branch: only when a declared range or qualitative criterion
    # gives the branch a decidable condition.
    if range_text is not None or _criterion(measurement) == 'qualitative':
        if range_text is not None:
            resolution_text = ('若读数在声明范围内（%s）但失败现象仍复现：记录现象'
                               '与全部前提，交人工/设计侧复核（本树不判定器件'
                               '损坏，也不允许放宽阈值）。' % range_text)
            resolution_decidable = '读数在声明范围内且预期现象仍稳定复现'
            resolution_evidence = ('复现步骤、读数、照片与时间线；与同板/参考板'
                                   '对照时注明这是相对比较而非绝对判据')
        else:
            resolution_text = ('若符合本步声明的定性现象但失败现象仍复现：记录'
                               '现象与全部前提，交人工/设计侧复核（本树不判定'
                               '器件损坏，也不允许放宽判据）。')
            resolution_decidable = '现象符合步骤声明的定性判据且仍复现'
            resolution_evidence = '复现步骤、原始读数、照片与时间线'
        _start_node.add(
            'resolution',
            resolution_text,
            evidence=resolution_evidence,
            decidable=resolution_decidable,
            terminal='resolution')

    nodes = _fit(nodes, MAX_NODES_PER_TREE)
    if not nodes:
        return None
    _wire(nodes)
    return {
        'id': tree_id,
        'symptom': _symptom(step, measurement),
        'entry_steps': [step_id],
        'boundary': _BOUNDARY,
        'nodes': nodes,
    }


class _NodeBuilder:
    """Append nodes in contract order and resolve ``next`` ids at the end."""

    def __init__(self, tree_id, nodes):
        self.tree_id = tree_id
        self.nodes = nodes
        self._resolution = None

    def add(self, kind, text, *, evidence=None, decidable=None, next_ids=(),
            terminal=None, depth=0):
        index = len(self.nodes) + 1
        node = {
            'node_id': '%s-%02d' % (self.tree_id, index),
            'kind': kind,
            'text': text,
            'evidence': evidence or '',
            'decidable': decidable or '',
            'next': [],
            'terminal': terminal,
            'depth': depth,
            '_next_tokens': list(next_ids),
        }
        self.nodes.append(node)
        return node


def _fit(nodes, limit):
    """Keep the first ``limit`` nodes but never drop a terminal branch."""
    if len(nodes) <= limit:
        return nodes
    terminals = [node for node in nodes if node.get('terminal')]
    keep = []
    for node in nodes:
        if len(keep) >= limit - len(terminals):
            break
        if node.get('terminal'):
            continue
        keep.append(node)
    for node in terminals:
        if len(keep) >= limit:
            break
        keep.append(node)
    return keep


def _wire(nodes):
    """Convert ``__resolution__`` tokens into real node ids (bounded)."""
    resolution = next((node['node_id'] for node in nodes
                       if node.get('terminal') == 'resolution'), None)
    for node in nodes:
        tokens = node.pop('_next_tokens', [])
        next_ids = []
        for token in tokens:
            if token == '__resolution__':
                if resolution is not None:
                    next_ids.append(resolution)
            elif isinstance(token, str):
                next_ids.append(token)
        node['next'] = next_ids


def _symptom(step, measurement):
    title = step.get('title') or step.get('step_id')
    if measurement:
        span = _range_text(measurement, ())
        if span is not None:
            expected = '复测 %s 未落在计划声明范围 %s 内' % (
                measurement.get('quantity'), span)
        else:
            expected = ('复测 %s 的现象/读数无法按项目声明判据解释'
                        % measurement.get('quantity'))
    elif step.get('expected_behavior'):
        expected = '预期现象未出现：%s' % _clip(step['expected_behavior'], 180)
    else:
        expected = '预期现象未出现'
    return '步骤 %s（%s）失败：%s。' % (step.get('step_id'),
                                     _clip(title, 80), expected)


# ---------------------------------------------------------------------------
# helpers


def _add_mode_node(ctx, step, builder):
    interfaces = getattr(ctx, 'interfaces', None) or []
    assemblies = getattr(ctx, 'assemblies', None) or {}
    firmware = [interface for interface in interfaces
                if isinstance(interface, dict)
                and interface.get('firmware_prerequisite')]
    jumpers = [item for item in (assemblies.get('jumpers') or [])
               if isinstance(item, dict)]
    if firmware or jumpers:
        parts = []
        if firmware:
            parts.append('固件前提：%s'
                         % '；'.join('%s=%s' % (
                             item.get('id'),
                             _clip(item.get('firmware_prerequisite'), 90))
                             for item in firmware[:3]))
        if jumpers:
            parts.append('跳线/模式：%s'
                         % '；'.join('%s 默认 %s%s' % (
                             item.get('id'), item.get('default_state'),
                             ('，测试要求 %s' % item['required_state_for_test'])
                             if item.get('required_state_for_test') else '')
                             for item in jumpers[:3]))
        builder.add(
            'check',
            '核对启动模式/strapping 与固件前提：' + '；'.join(parts)
            + '。未烧录或模式不符时，本步失败不能直接归因硬件。',
            evidence='固件版本/烧录状态记录、跳线状态照片',
            decidable='声明的固件前提已满足且跳线状态与测试要求一致；未知时'
                      '进入固件/模式分支处理，不默认正常')
    else:
        builder.add(
            'unknown',
            '输入未声明启动模式/strapping/固件前提：与启动相关的现象无法判定，'
            '本分支保持 unknown；需要时先补充声明或按原厂资料核对，不得默认正常。',
            evidence='无（缺少声明，须先补充项目输入）',
            decidable='项目声明 strapping/跳线/固件前提后本条才可判定',
            terminal='unknown')


def _prerequisite_ids(step):
    result = []
    for item in step.get('prerequisites') or []:
        if isinstance(item, dict) and item.get('kind') == 'step':
            step_id = item.get('step_id')
            if isinstance(step_id, str) and step_id:
                result.append(step_id)
    return result


def _step_domains(ctx, step):
    domains = getattr(ctx, 'domains', None) or []
    text = ' '.join(str(part) for part in (
        step.get('step_id') or '', step.get('title') or '',
        (step.get('measurement') or {}).get('point') or ''))
    found = []
    for domain in domains:
        if not isinstance(domain, dict):
            continue
        domain_id = domain.get('id')
        net = domain.get('net')
        if domain_id and domain_id in _tokens(text):
            found.append(domain)
        elif net and net in text:
            found.append(domain)
    return found


def _tokens(text):
    for separator in ('-', ':', '/', ' '):
        text = text.replace(separator, ' ')
    return set(text.split())


def _absolute_max(ctx, domain):
    value = domain.get('absolute_max_v')
    return value if _is_number(value) else None


def _same_threshold(stop_item, absolute):
    threshold = stop_item.get('threshold')
    if not isinstance(threshold, dict):
        return False
    value = threshold.get('value')
    return _is_number(value) and abs(float(value) - float(absolute)) < 1e-12 \
        and threshold.get('quantity') == 'voltage'


def _criterion(measurement):
    return (measurement or {}).get('criterion_status')


def _range_text(measurement, domains):
    if not measurement:
        return None
    span = measurement.get('range')
    if not isinstance(span, dict):
        return None
    lower = span.get('min')
    upper = span.get('max')
    unit = span.get('unit') or ''
    if not (_is_number(lower) or _is_number(upper)):
        return None
    if _is_number(lower) and _is_number(upper):
        return '%s–%s %s' % (_fmt(lower), _fmt(upper), unit)
    if _is_number(lower):
        return '≥ %s %s' % (_fmt(lower), unit)
    return '≤ %s %s' % (_fmt(upper), unit)


def _append_tree(ctx, tree):
    trees = getattr(ctx, 'trees', None)
    if trees is None:
        trees = []
        setattr(ctx, 'trees', trees)
    if not isinstance(trees, list):
        return False
    existing = {item.get('id') for item in trees if isinstance(item, dict)}
    if tree['id'] in existing:
        return False
    adder = getattr(ctx, 'add_tree', None)
    if callable(adder):
        adder(tree)
    else:
        trees.append(tree)
    return True


def _link_step(step, tree_id):
    branches = [item for item in (step.get('failure_branches') or [])
                if isinstance(item, str) and not item.startswith('FT-')]
    if tree_id not in branches:
        branches.append(tree_id)
    step['failure_branches'] = branches


def _drop_dangling_branches(ctx, steps):
    """Keep ``failure_branches`` consistent with ``ctx.trees``.

    Other generators put a fixed ``FT-<step_id>`` placeholder on every step.
    Steps that get no tree (blocked steps, steps without an observable failure)
    would keep a reference to a tree that does not exist, so the placeholder is
    removed.  A branch list may legitimately become empty.
    """
    trees = getattr(ctx, 'trees', None) or []
    tree_ids = {tree.get('id') for tree in trees if isinstance(tree, dict)}
    for step in steps:
        if not isinstance(step, dict):
            continue
        branches = step.get('failure_branches')
        if not isinstance(branches, list):
            continue
        cleaned = []
        for item in branches:
            if not isinstance(item, str):
                continue
            if item.startswith('FT-') and item not in tree_ids:
                continue
            cleaned.append(item)
        step['failure_branches'] = cleaned


def _is_number(value):
    return type(value) in (int, float) and value == value \
        and value not in (float('inf'), float('-inf'))


def _fmt(value):
    if isinstance(value, float):
        return '%.6g' % value
    return str(value)


def _clip(text, limit):
    text = '' if text is None else str(text)
    return text if len(text) <= limit else text[:limit] + '…'
