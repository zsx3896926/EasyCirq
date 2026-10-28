#!/usr/bin/env python3
"""Read-only checker for a whole-machine harness package.

No network access and no file writes. Standard output is exactly one JSON object.
Exit codes: 0 = no findings, 1 = findings need review, 2 = invalid input.

A pass only proves the supplied harness package is structurally complete and
internally consistent. It never proves a harness was built, crimped, tested,
installed or that its connectors are rated for the application.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

SCHEMA = 'harness-package/v1'
BOARD_VERIFIED = False
EXECUTION = 'OFFLINE_PLANNING'
HARDWARE_EXECUTION = 'NOT RUN'
UNKNOWN = '待查'
SEVERITIES = ('blocking', 'warning', 'unknown')
SIDES = ('board', 'harness', 'panel')
CONNECTOR_STATUS = ('planned', 'approved', 'released', UNKNOWN)
TEST_STATES = ('pass', 'fail', 'NOT RUN', UNKNOWN)
MATRIX_RESULTS = ('blocked', 'distinct', UNKNOWN)
CONNECTOR_FIELDS = ('id', 'side', 'mate', 'mpn', 'mating_housing',
                    'mating_terminal', 'crimp_tool', 'status',
                    'rated_current_a', 'rated_voltage_v', 'wire_gauge_range',
                    'shielding', 'keying', 'lock')
WIRE_FIELDS = ('net', 'board', 'harness', 'gauge', 'length_m', 'shielding',
               'continuity', 'pull_test', 'latch_check', 'label',
               'bend_radius_mm', 'evidence')
NOT_CHECKED = [
    '连接器原厂图纸、额定与降额曲线',
    '压接工具/端子匹配、拉脱力与接触电阻实测',
    '线束弯曲半径、屏蔽接地与整机装配的实物结果',
    'EMC、振动、跌落与热插拔的整机验证',
    '线束包内容真实性（脚本只查字段、引用与矩阵覆盖）',
]


class InputError(ValueError):
    """The supplied package is not structurally valid input."""


def text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise InputError('%s: require nonblank string without edge whitespace' % label)
    return value


def one_of(value, allowed, label):
    if value not in allowed:
        raise InputError('%s: require one of %s' % (label, ', '.join(allowed)))
    return value


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise InputError('%s: require integer >= %d' % (label, minimum))
    return value


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError('%s: require finite number' % label)
    if value != value or value in (float('inf'), float('-inf')):
        raise InputError('%s: require finite number' % label)
    return value


def number_or_unknown(value, label, minimum=0):
    if value == UNKNOWN:
        return value
    number = finite_number(value, label)
    if number < minimum:
        raise InputError('%s: require number >= %s' % (label, minimum))
    return value


def obj(value, label):
    if not isinstance(value, dict):
        raise InputError('%s: require object' % label)
    return value


def array(value, label):
    if not isinstance(value, list):
        raise InputError('%s: require array' % label)
    return value


def require_keys(value, required, label, optional=()):
    obj(value, label)
    missing = [key for key in required if key not in value]
    if missing:
        raise InputError('%s: missing %s' % (label, ', '.join(missing)))
    unknown = sorted(set(value) - set(required) - set(optional))
    if unknown:
        raise InputError('%s: unknown fields %s' % (label, ', '.join(unknown)))
    return value


def add(findings, code, severity, message, where):
    if severity not in SEVERITIES:
        raise AssertionError(severity)
    findings.append({'code': code, 'severity': severity,
                     'message': message, 'where': where})


def is_unknown(value):
    return value == UNKNOWN


def connector_ref(value, label):
    text(value, label)
    if '.' not in value:
        raise InputError('%s: require connector.pin form' % label)
    head, _, pin = value.rpartition('.')
    if not head or not pin:
        raise InputError('%s: require connector.pin form' % label)
    return head, pin


def check_revisions(revisions, findings):
    require_keys(revisions, ('harness_rev', 'board_rev', 'enclosure_rev', 'binding'),
                 'revisions')
    names = ('harness_rev', 'board_rev', 'enclosure_rev')
    values = {name: text(revisions[name], 'revisions.' + name) for name in names}
    binding = array(revisions['binding'], 'revisions.binding')
    bound = set()
    for index, item in enumerate(binding):
        bound.add(text(item, 'revisions.binding[%d]' % index))
    unknown = [name for name in names if is_unknown(values[name])]
    if unknown:
        add(findings, 'revision_unknown', 'unknown',
            '线束/板/外壳版本仍待查：%s；版本未绑定前不能把它当成已配套' % ', '.join(unknown),
            'revisions')
    known = {values[name] for name in names if not is_unknown(values[name])}
    missing = sorted(known - bound)
    if missing:
        add(findings, 'revision_binding_incomplete', 'blocking',
            'binding 未包含已填版本：%s' % ', '.join(missing), 'revisions.binding')


def check_connectors(connectors, findings):
    if not connectors:
        raise InputError('connectors: require at least one connector')
    ids = {}
    for index, connector in enumerate(connectors):
        label = 'connectors[%d]' % index
        require_keys(connector, CONNECTOR_FIELDS, label)
        cid = text(connector['id'], label + '.id')
        if cid in ids:
            raise InputError('%s.id: duplicate connector %s' % (label, cid))
        ids[cid] = connector
        one_of(connector['side'], SIDES, label + '.side')
        text(connector['mate'], label + '.mate')
        status = one_of(connector['status'], CONNECTOR_STATUS, label + '.status')
        if status == UNKNOWN:
            add(findings, 'connector_status_unknown', 'unknown',
                '连接器 %s 的采购/批准状态待查' % cid, label + '.status')
        for key in ('mpn', 'mating_housing', 'mating_terminal', 'crimp_tool',
                    'wire_gauge_range', 'shielding', 'keying', 'lock'):
            text(connector[key], label + '.' + key)
        number_or_unknown(connector['rated_current_a'], label + '.rated_current_a')
        number_or_unknown(connector['rated_voltage_v'], label + '.rated_voltage_v')
        unknown = [key for key in ('mpn', 'mating_housing', 'mating_terminal',
                                   'crimp_tool', 'rated_current_a',
                                   'rated_voltage_v', 'wire_gauge_range',
                                   'shielding', 'keying', 'lock')
                   if is_unknown(connector[key])]
        if unknown:
            add(findings, 'connector_field_unknown', 'unknown',
                '连接器 %s 的受控字段待查：%s' % (cid, ', '.join(unknown)), label)
        if status in ('approved', 'released') and unknown:
            add(findings, 'connector_approval_without_data', 'blocking',
                '连接器 %s 标为 %s，但仍有受控字段待查，不能按已批准使用' % (cid, status),
                label + '.status')
    for index, connector in enumerate(connectors):
        label = 'connectors[%d]' % index
        cid = connector['id']
        mate = connector['mate']
        if mate == 'none':
            continue
        if mate not in ids:
            add(findings, 'mate_unknown', 'blocking',
                '连接器 %s 的配对端 %s 不在本包内' % (cid, mate), label + '.mate')
            continue
        back = ids[mate]['mate']
        if back != cid:
            add(findings, 'mate_not_mutual', 'blocking',
                '配对关系不互指：%s.mate=%s，但 %s.mate=%s'
                % (cid, mate, mate, back), label + '.mate')
    return ids


def check_wires(wires, connectors, findings, not_checked):
    if not wires:
        raise InputError('wires: require at least one wire record')
    seen = set()
    for index, wire in enumerate(wires):
        label = 'wires[%d]' % index
        require_keys(wire, WIRE_FIELDS, label)
        net = text(wire['net'], label + '.net')
        board_id, _ = connector_ref(wire['board'], label + '.board')
        harness_id, _ = connector_ref(wire['harness'], label + '.harness')
        if board_id not in connectors:
            add(findings, 'wire_unknown_ref', 'blocking',
                '%s 的板端连接器 %s 不在 connectors 中' % (net, board_id),
                label + '.board')
        elif connectors[board_id]['side'] != 'board':
            add(findings, 'wire_wrong_side', 'blocking',
                '%s 的板端引用 %s 不是 board 侧' % (net, board_id), label + '.board')
        if harness_id not in connectors:
            add(findings, 'wire_unknown_ref', 'blocking',
                '%s 的线束端连接器 %s 不在 connectors 中' % (net, harness_id),
                label + '.harness')
        elif connectors[harness_id]['side'] != 'harness':
            add(findings, 'wire_wrong_side', 'blocking',
                '%s 的线束端引用 %s 不是 harness 侧' % (net, harness_id),
                label + '.harness')
        key = (wire['board'], wire['harness'])
        if key in seen:
            add(findings, 'duplicate_wire', 'blocking',
                '同一板端/线束端组合被重复记录：%s / %s' % key, label)
        seen.add(key)
        text(wire['gauge'], label + '.gauge')
        number_or_unknown(wire['length_m'], label + '.length_m')
        text(wire['shielding'], label + '.shielding')
        number_or_unknown(wire['bend_radius_mm'], label + '.bend_radius_mm')
        if not isinstance(wire['evidence'], str):
            raise InputError(label + '.evidence: require string')
        pending = []
        failed = []
        unsupported = []
        for key in ('continuity', 'pull_test', 'latch_check', 'label'):
            state = one_of(wire[key], TEST_STATES, label + '.' + key)
            if state in ('NOT RUN', UNKNOWN):
                pending.append(key)
            elif state == 'fail':
                failed.append(key)
            elif state == 'pass' and wire['evidence'].strip() in ('', UNKNOWN):
                unsupported.append(key)
        if pending:
            add(findings, 'wire_test_not_run', 'unknown',
                '%s 的逐线记录未执行/待查：%s' % (net, ', '.join(pending)), label)
            not_checked.append('逐线通断/拉脱/锁扣/标签：' + net)
        if failed:
            add(findings, 'wire_test_failed', 'blocking',
                '%s 的逐线记录存在 fail：%s' % (net, ', '.join(failed)), label)
        if unsupported:
            add(findings, 'wire_claim_without_evidence', 'blocking',
                '%s 标记 pass 但无证据：%s' % (net, ', '.join(unsupported)), label)
        unknown = [key for key in ('gauge', 'length_m', 'shielding', 'bend_radius_mm')
                   if is_unknown(wire[key])]
        if unknown:
            add(findings, 'wire_field_unknown', 'unknown',
                '%s 的线材字段待查：%s' % (net, ', '.join(unknown)), label)
            not_checked.append('线规/长度/屏蔽/弯折半径：' + net)


def check_matrix(matrix, connectors, findings):
    rows = {}
    for index, row in enumerate(matrix):
        label = 'misconnection_matrix[%d]' % index
        require_keys(row, ('a', 'b', 'result', 'note'), label)
        a = text(row['a'], label + '.a')
        b = text(row['b'], label + '.b')
        text(row['note'], label + '.note')
        if a not in connectors or b not in connectors:
            add(findings, 'matrix_unknown_ref', 'blocking',
                '防误接记录引用了不存在的连接器：%s / %s' % (a, b), label)
            continue
        if a == b:
            add(findings, 'matrix_self_pair', 'blocking',
                '防误接记录不能把连接器 %s 与自身配对' % a, label)
            continue
        key = tuple(sorted((a, b)))
        if key in rows:
            add(findings, 'duplicate_matrix_row', 'warning',
                '防误接记录重复：%s / %s' % key, label)
        rows[key] = row
        result = one_of(row['result'], MATRIX_RESULTS, label + '.result')
        if result == UNKNOWN:
            add(findings, 'matrix_unknown', 'unknown',
                '%s 与 %s 的防误接结论待查' % (a, b), label + '.result')
        elif result not in ('blocked', 'distinct'):
            add(findings, 'misconnection_possible', 'blocking',
                '%s 与 %s 的防误接结论为 %s，不能放行' % (a, b, result),
                label + '.result')
        key_a = connectors[a]['keying']
        key_b = connectors[b]['keying']
        if key_a != UNKNOWN and key_a == key_b and result != 'blocked':
            add(findings, 'same_keying_not_blocked', 'blocking',
                '%s 与 %s 使用同一键位 %s，但防误接结论不是 blocked'
                % (a, b, key_a), label + '.result')
    ids = list(connectors)
    for left in range(len(ids)):
        for right in range(left + 1, len(ids)):
            a = ids[left]
            b = ids[right]
            if connectors[a]['mate'] == b and connectors[b]['mate'] == a:
                continue
            if tuple(sorted((a, b))) not in rows:
                add(findings, 'matrix_incomplete', 'blocking',
                    '缺少连接器 %s 与 %s 的防误接记录' % (a, b),
                    'misconnection_matrix')


def check_package(data):
    require_keys(data, ('schema', 'package_id', 'revisions', 'connectors',
                        'wires', 'misconnection_matrix'), 'package',
                 optional=('_note',))
    if data['schema'] != SCHEMA:
        raise InputError('schema: require %s' % SCHEMA)
    text(data['package_id'], 'package_id')
    findings = []
    not_checked = []
    check_revisions(obj(data['revisions'], 'revisions'), findings)
    connectors = check_connectors(array(data['connectors'], 'connectors'), findings)
    check_wires(array(data['wires'], 'wires'), connectors, findings, not_checked)
    check_matrix(array(data['misconnection_matrix'], 'misconnection_matrix'),
                 connectors, findings)
    return findings, not_checked


def invalid_result(message):
    return {
        'status': 'invalid_input',
        'error': message,
        'board_verified': BOARD_VERIFIED,
        'execution': EXECUTION,
        'hardware_execution': HARDWARE_EXECUTION,
        'findings': [],
        'not_checked': list(NOT_CHECKED),
    }


def final_result(findings, not_checked):
    ordered = []
    for item in NOT_CHECKED + list(not_checked):
        if item not in ordered:
            ordered.append(item)
    return {
        'kind': 'harness',
        'status': 'needs_review' if findings else 'pass',
        'board_verified': BOARD_VERIFIED,
        'execution': EXECUTION,
        'hardware_execution': HARDWARE_EXECUTION,
        'findings': findings,
        'not_checked': ordered,
    }


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps(invalid_result(message), ensure_ascii=False))
        raise SystemExit(2)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: %s' % key)
        result[key] = value
    return result


def load_package(path):
    raw = Path(path).read_text(encoding='utf-8')
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError('non-finite JSON: %s' % value)))


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument('package', help='path to a harness-package/v1 JSON file')
    args = parser.parse_args(argv)
    try:
        data = load_package(args.package)
        findings, not_checked = check_package(data)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps(invalid_result(str(exc)), ensure_ascii=False))
        return 2
    print(json.dumps(final_result(findings, not_checked), ensure_ascii=False))
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
