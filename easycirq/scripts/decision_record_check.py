#!/usr/bin/env python3
"""Read-only checker for calibration records, change records and impact graphs.

No network access and no file writes. Standard output is exactly one JSON object.
Exit codes: 0 = no findings, 1 = findings need review, 2 = invalid input.

See references/decisions/h01-calibration-and-identity.md and
references/decisions/i01-change-impact.md. A pass only proves the supplied
record is internally consistent; it never proves hardware, calibration or a
change has been executed.
"""
import argparse
import json
import re
import sys
import zlib
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

BOARD_VERIFIED = False
EXECUTION = 'OFFLINE_PLANNING'
HARDWARE_EXECUTION = 'NOT RUN'
SEVERITIES = ('blocking', 'warning', 'unknown')
STATES = ('unchanged', 'updated', 'invalidated', 'reverified', 'not_applicable')
CAL_STATUS = ('valid', 'uncalibrated', 'expired', 'invalid')
CHANGE_STATUS = ('draft', 'frozen', 'superseded', 'withdrawn')
CHANGE_RESULTS = ('pass', 'fail', 'NOT RUN', 'unknown')
EVIDENCE_LEVELS = ('E1', 'E2', 'E3')
SCENARIO_LEVEL = {
    'shunt-change': 2,
    'mcu-package-change': 3,
    'isolation-add': 3,
    'layout-only': 'local-only',
}
CRC_RE = re.compile(r'^0[xX][0-9A-Fa-f]{8}$')
ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
PATH_RANGE_RE = re.compile(r'[A-Za-z0-9_./\\-]+:\d+-\d+')
SOURCE_ID_RE = re.compile(r'(?<![A-Za-z0-9])[A-Z]{2,5}-S\d{2,3}(?![A-Za-z0-9])')
BOM_DELTA_STATUS = ('planned', 'unchanged', 'unknown')
DNP_VALUES = ('yes', 'no', '待查')
CAL_FIELDS = ('record_id', 'magic', 'schema_version', 'length', 'identity',
              'cal_date', 'cal_temp_c', 'source_id', 'channels', 'slots',
              'status', 'valid', 'valid_until', 'invalid_reason')
CAL_PAYLOAD_FIELDS = ('magic', 'schema_version', 'identity', 'cal_date',
                      'cal_temp_c', 'source_id', 'channels')
COMMON_NOT_CHECKED = [
    '真实硬件/EDA 回读',
    '实测、校准源不确定度与温循数据',
    '出货批次/序列号追溯',
    '记录内容真实性（脚本只查结构与自洽）',
    '证据引用目标文件/行号内容（脚本只解析 path:start-end 与来源 ID 语法）',
]


class InputError(ValueError):
    """The supplied record is not structurally valid input."""


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


def boolean(value, label):
    if type(value) is not bool:
        raise InputError('%s: require boolean' % label)
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


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError('%s: require finite number' % label)
    if value != value or value in (float('inf'), float('-inf')):
        raise InputError('%s: require finite number' % label)
    return value


def number_or_unknown(value, label):
    if value == '待查':
        return value
    return finite_number(value, label)


def iso_date(value, label):
    text(value, label)
    if not ISO_DATE_RE.match(value):
        raise InputError('%s: require YYYY-MM-DD' % label)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InputError('%s: invalid date: %s' % (label, exc)) from exc
    return value


def date_or_unknown(value, label):
    if value == '待查':
        return value
    return iso_date(value, label)


def add(findings, code, severity, message, where):
    if severity not in SEVERITIES:
        raise AssertionError(severity)
    findings.append({'code': code, 'severity': severity,
                     'message': message, 'where': where})


def canonical_payload(record):
    """Payload definition: the record fields excluding record_id/length/slots/
    status/valid, plus the optional valid_until and invalid_reason fields.

    The excluded set is documented in h01-calibration-and-identity.md;
    record_id names the record file and is not part of the calibrated payload.
    """
    payload = {key: record[key] for key in CAL_PAYLOAD_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('utf-8')


def payload_crc(record):
    return zlib.crc32(canonical_payload(record)) & 0xFFFFFFFF


def crc_text(value, label):
    text(value, label)
    if not CRC_RE.match(value):
        raise InputError('%s: require 0x + 8 hex digits' % label)
    return value


def evidence_reference_ok(value):
    """True when evidence parses as path:start-end or a registered source ID."""
    return bool(PATH_RANGE_RE.search(value) or SOURCE_ID_RE.search(value))


def valid_until_finding(value, status, findings):
    """Require a real ISO date for valid/expired records.

    A missing value gets a status-specific finding; a malformed value gets
    invalid_valid_until instead of an input error so the CLI reports findings
    (exit 1) rather than invalid input (exit 2).
    """
    if status not in ('valid', 'expired') or value == '待查':
        return
    try:
        iso_date(value, 'valid_until')
    except InputError:
        add(findings, 'invalid_valid_until', 'blocking',
            'valid_until 必须是真实的 YYYY-MM-DD 日期，实际为 %s' % value,
            'valid_until')


def check_calibration(data):
    require_keys(data, CAL_FIELDS, 'calibration')
    record_id = text(data['record_id'], 'record_id')
    if not record_id.startswith('CAL-'):
        raise InputError('record_id: require CAL-<项目>-<序号>')
    if data['magic'] != 'CALREC':
        raise InputError('magic: require CALREC')
    if data['schema_version'] != 1:
        raise InputError('schema_version: require 1')
    integer(data['length'], 'length')
    identity = obj(data['identity'], 'identity')
    require_keys(identity, ('model', 'hw_rev', 'variant', 'serial'), 'identity')
    for key in ('model', 'hw_rev', 'variant', 'serial'):
        text(identity[key], 'identity.' + key)
    date_or_unknown(data['cal_date'], 'cal_date')
    number_or_unknown(data['cal_temp_c'], 'cal_temp_c')
    text(data['source_id'], 'source_id')
    channels = array(data['channels'], 'channels')
    if not channels:
        raise InputError('channels: require at least one channel')
    seen = set()
    for index, channel in enumerate(channels):
        label = 'channels[%d]' % index
        require_keys(channel, ('channel', 'offset', 'gain', 'range', 'unit'), label)
        number = integer(channel['channel'], label + '.channel', 1)
        if number in seen:
            raise InputError('%s.channel: duplicate channel %d' % (label, number))
        seen.add(number)
        number_or_unknown(channel['offset'], label + '.offset')
        number_or_unknown(channel['gain'], label + '.gain')
        text(channel['range'], label + '.range')
        text(channel['unit'], label + '.unit')
    slots = obj(data['slots'], 'slots')
    require_keys(slots, ('A', 'B'), 'slots')
    for name in ('A', 'B'):
        slot = obj(slots[name], 'slots.' + name)
        require_keys(slot, ('sequence', 'crc32', 'status'), 'slots.' + name)
        integer(slot['sequence'], 'slots.%s.sequence' % name)
        crc_text(slot['crc32'], 'slots.%s.crc32' % name)
        one_of(slot['status'], CAL_STATUS, 'slots.%s.status' % name)
    status = one_of(data['status'], CAL_STATUS, 'status')
    boolean(data['valid'], 'valid')
    text(data['valid_until'], 'valid_until')
    if not isinstance(data['invalid_reason'], str) or data['invalid_reason'] != data['invalid_reason'].strip():
        raise InputError('invalid_reason: require string without edge whitespace')
    findings = []
    not_checked = []
    body = canonical_payload(data)
    if data['length'] != len(body):
        add(findings, 'length_mismatch', 'blocking',
            'length 应为规范化 payload 的字节数 %d，实际为 %d' % (len(body), data['length']),
            'length')
    expected_crc = payload_crc(data)
    for name in ('A', 'B'):
        supplied = int(slots[name]['crc32'], 16)
        if supplied != expected_crc:
            add(findings, 'crc_mismatch', 'blocking',
                '槽 %s 的 CRC32 与 payload 不符：期望 0x%08X' % (name, expected_crc),
                'slots.%s.crc32' % name)
    statuses = {name: slots[name]['status'] for name in ('A', 'B')}
    sequences = [slots[name]['sequence'] for name in ('A', 'B')]
    if status == 'uncalibrated':
        if data['valid']:
            add(findings, 'uncalibrated_marked_valid', 'blocking',
                'uncalibrated 记录的 valid 必须为 false', 'valid')
        unknown_fields = [('cal_date', data['cal_date']),
                          ('cal_temp_c', data['cal_temp_c']),
                          ('source_id', data['source_id'])]
        for channel_index, channel in enumerate(channels):
            for key in ('offset', 'gain', 'range', 'unit'):
                unknown_fields.append(('channels[%d].%s' % (channel_index, key),
                                       channel[key]))
        bad = [label for label, value in unknown_fields if value != '待查']
        if bad:
            add(findings, 'uncalibrated_has_values', 'blocking',
                'uncalibrated 记录不得带具体校准值：%s' % ', '.join(bad),
                'status')
        if any(value != 'uncalibrated' for value in statuses.values()):
            add(findings, 'uncalibrated_slot_state', 'blocking',
                'uncalibrated 记录的两个槽都应为 uncalibrated', 'slots')
        if any(value != 0 for value in sequences):
            add(findings, 'uncalibrated_slot_sequence', 'blocking',
                'uncalibrated 记录的槽序号应为 0', 'slots')
        not_checked.append('校准值 offset/gain/range 均为待查')
    elif status == 'valid':
        if not data['valid']:
            add(findings, 'valid_flag_false', 'blocking',
                'valid 记录的 valid 必须为 true', 'valid')
        bad = []
        if data['cal_date'] == '待查':
            bad.append('cal_date')
        if data['cal_temp_c'] == '待查':
            bad.append('cal_temp_c')
        if data['source_id'] == '待查':
            bad.append('source_id')
        for channel_index, channel in enumerate(channels):
            for key in ('offset', 'gain'):
                if channel[key] == '待查':
                    bad.append('channels[%d].%s' % (channel_index, key))
            for key in ('range', 'unit'):
                if channel[key] == '待查':
                    bad.append('channels[%d].%s' % (channel_index, key))
        if bad:
            add(findings, 'valid_with_unknown_values', 'blocking',
                'valid 记录不得含待查校准值：%s' % ', '.join(bad), 'status')
        valid_slots = [name for name, value in statuses.items() if value == 'valid']
        if not valid_slots:
            add(findings, 'valid_without_valid_slot', 'blocking',
                'valid 记录至少需要一个 valid 槽', 'slots')
        for name in valid_slots:
            if slots[name]['sequence'] < 1:
                add(findings, 'valid_slot_sequence', 'blocking',
                    'valid 槽的 sequence 必须 >= 1', 'slots.%s.sequence' % name)
        if len(valid_slots) == 2 and sequences[0] != sequences[1]:
            add(findings, 'slot_sequence_conflict', 'blocking',
                '两个 valid 槽的 sequence 不一致，无法判断活动槽', 'slots')
        if data['valid_until'] == '待查':
            add(findings, 'valid_without_valid_until', 'blocking',
                'valid 记录必须写 valid_until（YYYY-MM-DD）', 'valid_until')
        valid_until_finding(data['valid_until'], status, findings)
    elif status == 'expired':
        if data['valid']:
            add(findings, 'expired_marked_valid', 'blocking',
                'expired 记录的 valid 必须为 false', 'valid')
        if data['valid_until'] == '待查':
            add(findings, 'expired_without_valid_until', 'blocking',
                'expired 记录必须写 valid_until', 'valid_until')
        valid_until_finding(data['valid_until'], status, findings)
        if not any(value == 'valid' for value in statuses.values()):
            add(findings, 'expired_without_valid_slot', 'blocking',
                'expired 记录应保留一个 valid 槽供重校', 'slots')
    else:
        if data['valid']:
            add(findings, 'invalid_marked_valid', 'blocking',
                'invalid 记录的 valid 必须为 false', 'valid')
        if data['invalid_reason'] in ('', '待查'):
            add(findings, 'invalid_without_reason', 'blocking',
                'invalid 记录必须写 invalid_reason', 'invalid_reason')
        if not any(value == 'invalid' for value in statuses.values()):
            add(findings, 'invalid_without_invalid_slot', 'blocking',
                'invalid 记录至少需要一个 invalid 槽', 'slots')
    not_checked.extend([
        '校准源型号/不确定度/有效期',
        '存储耐久与 A/B 槽掉电原子性',
        '无效参数安全态实测',
    ])
    return findings, not_checked


def check_f1_baseline(baseline, revision_verified, findings, where):
    eda_baseline = text(baseline['eda_baseline'], where + '.eda_baseline')
    level = one_of(baseline['eda_baseline_level'], EVIDENCE_LEVELS,
                   where + '.eda_baseline_level')
    rerun = boolean(baseline['eda_rerun_this_round'], where + '.eda_rerun_this_round')
    role = one_of(baseline['role'], ('baseline_only', 'revision_evidence'),
                  where + '.role')
    if eda_baseline.upper() == 'F1':
        if level != 'E1':
            add(findings, 'f1_level_mismatch', 'blocking',
                'F1 是前轮 E1 原理图基线，不能标成其他等级', where + '.eda_baseline_level')
        if role != 'baseline_only':
            add(findings, 'f1_baseline_role_invalid', 'blocking',
                'F1 只能作 baseline_only，不能作改型证据', where + '.role')
        if rerun:
            add(findings, 'f1_rerun_claim_not_supported', 'blocking',
                'F1 本轮未重跑，不得记录 rerun_this_round=true', where + '.eda_rerun_this_round')
        if revision_verified:
            add(findings, 'f1_baseline_cannot_verify_revision', 'blocking',
                'F1 基线不能证明 V1.1 或任何改型已验证', where)


def check_batch_scope(scope, findings, not_checked, where):
    require_keys(scope, ('mode', 'detail', 'effective_from', 'effective_to'), where)
    mode = one_of(scope['mode'], ('not_applicable', 'range', 'serial-list', 'unknown'),
                  where + '.mode')
    text(scope['detail'], where + '.detail')
    text(scope['effective_from'], where + '.effective_from')
    text(scope['effective_to'], where + '.effective_to')
    if mode in ('range', 'serial-list'):
        for key in ('effective_from', 'effective_to'):
            if scope[key] == '待查':
                add(findings, 'batch_scope_incomplete', 'blocking',
                    '%s 模式必须写 %s' % (mode, key), where + '.' + key)
    if mode == 'unknown':
        add(findings, 'batch_scope_unknown', 'unknown',
            '批次/序列号范围未知，不能默认为全部或无影响', where)
        not_checked.append('出货批次/序列号生效范围')
    if mode == 'not_applicable' and not scope['detail']:
        add(findings, 'batch_scope_missing_detail', 'blocking',
            'not_applicable 必须写理由', where + '.detail')


def check_rollback(rollback, findings, where):
    require_keys(rollback, ('plan', 'disposition', 'reason'), where)
    text(rollback['plan'], where + '.plan')
    one_of(rollback['disposition'],
           ('rework', 'scrap', 'use-as-is', 'not_applicable', 'unknown'),
           where + '.disposition')
    text(rollback['reason'], where + '.reason')
    if rollback['disposition'] == 'unknown':
        add(findings, 'rollback_disposition_unknown', 'unknown',
            '回滚/报废处置未定，不能宣称变更可撤回', where + '.disposition')


def check_bom_delta(delta, scenario, findings, not_checked, where):
    """Validate the per-scenario BOM delta table.

    Unknown values are written as 待查; the checker never invents an MPN,
    quantity or DNP state. layout-only must explicitly state BOM unchanged
    with CPL/coordinate changes still NOT RUN.
    """
    require_keys(delta, ('status', 'note', 'items'), where)
    status = one_of(delta['status'], BOM_DELTA_STATUS, where + '.status')
    note = text(delta['note'], where + '.note')
    items = array(delta['items'], where + '.items')
    if scenario == 'layout-only':
        if status != 'unchanged' or items:
            add(findings, 'layout_only_bom_delta', 'blocking',
                'layout-only 必须写 BOM 不变，不得声明 BOM 项变化', where)
        if 'BOM 不变' not in note or 'NOT RUN' not in note:
            add(findings, 'layout_only_bom_delta', 'blocking',
                'layout-only 的 note 必须写明“BOM 不变 … NOT RUN”', where + '.note')
        return
    if not items:
        if status == 'unknown':
            not_checked.append('BOM delta：' + str(scenario))
        else:
            add(findings, 'bom_delta_missing', 'blocking',
                '%s 场景缺少 BOM delta；未知写 unknown 且值为待查' % scenario,
                where + '.items')
    for index, item in enumerate(items):
        label = '%s.items[%d]' % (where, index)
        require_keys(item, ('ref', 'old', 'new', 'qty', 'dnp', 'reason'), label)
        text(item['ref'], label + '.ref')
        text(item['old'], label + '.old')
        text(item['new'], label + '.new')
        if item['qty'] != '待查':
            integer(item['qty'], label + '.qty', 1)
        one_of(item['dnp'], DNP_VALUES, label + '.dnp')
        text(item['reason'], label + '.reason')


def scope_tokens(value):
    return {token.casefold() for token in re.split(r'[^A-Za-z0-9_.-]+', value)
            if token}


def reverified_scope_ok(artifact, verification):
    """A reverified artifact needs a verification whose scope names it.

    The scope may name the artifact directly, or name a change id that the
    artifact's reason lists (for example CHG-01 on a schematic revision).
    """
    scope = str(verification.get('scope', '')).casefold()
    if artifact['artifact'].casefold() in scope:
        return True
    scope_set = scope_tokens(scope)
    return any(token in scope_set for token in scope_tokens(artifact['reason']))


def passing_e1(verification):
    """A pass is usable only with E1, non-F1 evidence that parses as a ref."""
    if verification.get('result') != 'pass':
        return False
    if verification.get('evidence_level') != 'E1':
        return False
    evidence = str(verification.get('evidence', ''))
    if 'F1' in evidence.upper():
        return False
    return evidence_reference_ok(evidence)


def check_change(data):
    required = ('change_id', 'title', 'date', 'status', 'baseline', 'changes',
                'affected_artifacts', 'netlist_diff', 'batch_scope',
                'verification', 'rollback', 'approvals', 'revision_verified')
    optional = ('superseded_by', 'withdraw_reason')
    require_keys(data, required, 'change', optional)
    text(data['change_id'], 'change_id')
    text(data['title'], 'title')
    iso_date(data['date'], 'date')
    status = one_of(data['status'], CHANGE_STATUS, 'status')
    baseline = obj(data['baseline'], 'baseline')
    require_keys(baseline, ('product_baseline', 'eda_baseline',
                            'eda_baseline_level', 'eda_rerun_this_round', 'role'),
                 'baseline')
    text(baseline['product_baseline'], 'baseline.product_baseline')
    revision_verified = boolean(data['revision_verified'], 'revision_verified')
    findings = []
    not_checked = []
    check_f1_baseline(baseline, revision_verified, findings, 'baseline')
    changes = array(data['changes'], 'changes')
    if not changes:
        raise InputError('changes: require at least one change')
    for index, change in enumerate(changes):
        label = 'changes[%d]' % index
        require_keys(change, ('change_id', 'scenario', 'level', 'from', 'to',
                              'reason', 'status', 'bom_delta'), label)
        text(change['change_id'], label + '.change_id')
        scenario = one_of(change['scenario'], tuple(SCENARIO_LEVEL), label + '.scenario')
        expected = SCENARIO_LEVEL[scenario]
        if change['level'] != expected:
            add(findings, 'scenario_level_mismatch', 'blocking',
                '%s 必须映射为 %s，不能写 %s' % (scenario, expected, change['level']),
                label + '.level')
        text(change['from'], label + '.from')
        text(change['to'], label + '.to')
        text(change['reason'], label + '.reason')
        one_of(change['status'], ('planned', 'in_progress', 'done', 'withdrawn'),
               label + '.status')
        check_bom_delta(obj(change['bom_delta'], label + '.bom_delta'), scenario,
                        findings, not_checked, label + '.bom_delta')
    artifacts = array(data['affected_artifacts'], 'affected_artifacts')
    if not artifacts:
        raise InputError('affected_artifacts: require at least one artifact')
    verifications = array(data['verification'], 'verification')
    if not verifications:
        raise InputError('verification: require at least one item')
    for index, artifact in enumerate(artifacts):
        label = 'affected_artifacts[%d]' % index
        require_keys(artifact, ('artifact', 'ref', 'state', 'reason'), label)
        text(artifact['artifact'], label + '.artifact')
        text(artifact['ref'], label + '.ref')
        state = one_of(artifact['state'], STATES, label + '.state')
        text(artifact['reason'], label + '.reason')
        if state == 'reverified':
            usable = [item for item in verifications if passing_e1(item)]
            if not usable:
                add(findings, 'reverified_without_e1', 'blocking',
                    'reverified 必须有非 F1 的 E1 证据', label + '.state')
            elif not any(reverified_scope_ok(artifact, item) for item in usable):
                add(findings, 'reverified_scope_mismatch', 'blocking',
                    'reverified 工件的复验 scope 必须对应该工件或其变更号',
                    label + '.state')
    netlist = obj(data['netlist_diff'], 'netlist_diff')
    require_keys(netlist, ('status', 'evidence'), 'netlist_diff')
    netlist_status = one_of(netlist['status'],
                            ('unchanged', 'changed', 'NOT RUN', 'unknown'),
                            'netlist_diff.status')
    if not isinstance(netlist['evidence'], str) or netlist['evidence'] != netlist['evidence'].strip():
        raise InputError('netlist_diff.evidence: require string without edge whitespace')
    if netlist_status == 'unchanged' and not netlist['evidence']:
        add(findings, 'netlist_unchanged_without_diff', 'blocking',
            '没有 after 快照/网表 diff 不得写 unchanged', 'netlist_diff')
    if netlist_status == 'NOT RUN':
        not_checked.append('变更后网表 diff')
    if netlist_status == 'unknown':
        add(findings, 'netlist_diff_unknown', 'unknown',
            '网表是否变化未知，只能按方向记录', 'netlist_diff')
    check_batch_scope(data['batch_scope'], findings, not_checked, 'batch_scope')
    unverified = False
    pass_e1_other = False
    for index, verification in enumerate(verifications):
        label = 'verification[%d]' % index
        require_keys(verification, ('check', 'scope', 'result', 'evidence_level', 'evidence'),
                     label)
        text(verification['check'], label + '.check')
        text(verification['scope'], label + '.scope')
        result = one_of(verification['result'], CHANGE_RESULTS, label + '.result')
        level = one_of(verification['evidence_level'], EVIDENCE_LEVELS,
                       label + '.evidence_level')
        evidence = verification['evidence']
        if not isinstance(evidence, str):
            raise InputError(label + '.evidence: require string')
        if result == 'pass':
            if level != 'E1':
                add(findings, 'pass_without_e1', 'blocking',
                    'pass 只能由 E1 证据支持，%s 不够' % level, label + '.result')
            if 'F1' in evidence.upper():
                add(findings, 'f1_cannot_verify_revision', 'blocking',
                    'F1 是基线，不能作为改型复验的 pass 证据', label + '.evidence')
            if not evidence_reference_ok(evidence):
                add(findings, 'pass_without_evidence', 'blocking',
                    'pass 必须给出可解析的 path:start-end 或来源 ID 证据',
                    label + '.evidence')
            if passing_e1(verification):
                pass_e1_other = True
        if result == 'NOT RUN':
            unverified = True
            not_checked.append('复验项：' + verification['check'])
    if status == 'frozen' and unverified:
        add(findings, 'frozen_with_unverified_items', 'blocking',
            '存在 NOT RUN 复验项时不能冻结变更', 'status')
    if revision_verified and not pass_e1_other:
        add(findings, 'revision_verified_without_evidence', 'blocking',
            'revision_verified=true 需要至少一个非 F1 的 E1 pass', 'revision_verified')
    check_rollback(data['rollback'], findings, 'rollback')
    approvals = obj(data['approvals'], 'approvals')
    require_keys(approvals, ('engineering', 'manufacturing', 'quality'), 'approvals')
    for key in ('engineering', 'manufacturing', 'quality'):
        text(approvals[key], 'approvals.' + key)
    if status == 'superseded':
        if 'superseded_by' not in data:
            raise InputError('superseded_by: required when status=superseded')
        text(data['superseded_by'], 'superseded_by')
    if status == 'withdrawn':
        if 'withdraw_reason' not in data:
            raise InputError('withdraw_reason: required when status=withdrawn')
        text(data['withdraw_reason'], 'withdraw_reason')
    return findings, not_checked


def check_graph(data):
    required = ('graph_id', 'change_id', 'nodes', 'edges', 'old_parts',
                'batch_scope', 'evidence', 'canonical_facts', 'rollback')
    require_keys(data, required, 'graph')
    text(data['graph_id'], 'graph_id')
    text(data['change_id'], 'change_id')
    nodes = array(data['nodes'], 'nodes')
    if not nodes:
        raise InputError('nodes: require at least one node')
    node_states = {}
    for index, node in enumerate(nodes):
        label = 'nodes[%d]' % index
        require_keys(node, ('id', 'kind', 'state'), label,
                     ('role', 'evidence', 'evidence_level'))
        node_id = text(node['id'], label + '.id')
        if node_id in node_states:
            raise InputError('%s.id: duplicate node %s' % (label, node_id))
        one_of(node['kind'],
               ('artifact', 'part', 'interface', 'firmware', 'test',
                'document', 'production', 'baseline'), label + '.kind')
        node_states[node_id] = one_of(node['state'], STATES, label + '.state')
        if 'role' in node:
            text(node['role'], label + '.role')
        if 'evidence' in node and not isinstance(node['evidence'], str):
            raise InputError(label + '.evidence: require string')
        if 'evidence_level' in node:
            one_of(node['evidence_level'], EVIDENCE_LEVELS, label + '.evidence_level')
    findings = []
    not_checked = []
    for index, node in enumerate(nodes):
        if node.get('role') == 'baseline_only' and node_states[node['id']] not in ('unchanged', 'not_applicable'):
            add(findings, 'baseline_node_modified', 'blocking',
                'baseline_only 节点不得被更新或失效', 'nodes[%d].state' % index)
        if node_states[node['id']] == 'reverified' and node.get('evidence_level') != 'E1':
            add(findings, 'reverified_without_e1', 'blocking',
                'reverified 节点必须有 E1 证据', 'nodes[%d].state' % index)
    edges = array(data['edges'], 'edges')
    outgoing = {}
    seen_edges = set()
    for index, edge in enumerate(edges):
        label = 'edges[%d]' % index
        require_keys(edge, ('from', 'to', 'relation'), label)
        source = text(edge['from'], label + '.from')
        target = text(edge['to'], label + '.to')
        if source not in node_states:
            raise InputError('%s.from: unknown node %s' % (label, source))
        if target not in node_states:
            raise InputError('%s.to: unknown node %s' % (label, target))
        relation = one_of(edge['relation'],
                          ('updates', 'invalidates', 'requires-reverification'),
                          label + '.relation')
        key = (source, target, relation)
        if key in seen_edges:
            add(findings, 'duplicate_edge', 'warning',
                '重复边：%s -> %s (%s)' % (source, target, relation), label)
        seen_edges.add(key)
        outgoing.setdefault(source, []).append(target)
    visited = set()
    stack = [node_id for node_id, state in node_states.items() if state == 'invalidated']
    while stack:
        current = stack.pop()
        for target in outgoing.get(current, []):
            if target in visited:
                continue
            visited.add(target)
            if node_states[target] == 'unchanged':
                add(findings, 'stale_downstream_artifact', 'blocking',
                    '上游已失效，下游仍为 unchanged：%s -> %s' % (current, target),
                    'edges')
            stack.append(target)
    old_parts = array(data['old_parts'], 'old_parts')
    seen_parts = set()
    for index, part in enumerate(old_parts):
        label = 'old_parts[%d]' % index
        require_keys(part, ('ref', 'state', 'note'), label)
        ref = text(part['ref'], label + '.ref')
        if ref in seen_parts:
            raise InputError('%s.ref: duplicate ref %s' % (label, ref))
        seen_parts.add(ref)
        one_of(part['state'], STATES, label + '.state')
        text(part['note'], label + '.note')
    check_batch_scope(data['batch_scope'], findings, not_checked, 'batch_scope')
    evidence = obj(data['evidence'], 'evidence')
    require_keys(evidence, ('eda_baseline', 'eda_baseline_level',
                            'eda_rerun_this_round', 'role', 'revision_verified'),
                 'evidence')
    revision_verified = boolean(evidence['revision_verified'], 'evidence.revision_verified')
    check_f1_baseline(evidence, revision_verified, findings, 'evidence')
    facts = array(data['canonical_facts'], 'canonical_facts')
    if not facts:
        raise InputError('canonical_facts: require at least one fact')
    fact_ids = set()
    for index, fact in enumerate(facts):
        label = 'canonical_facts[%d]' % index
        require_keys(fact, ('id', 'statement', 'source'), label)
        fact_id = text(fact['id'], label + '.id')
        if fact_id in fact_ids:
            raise InputError('%s.id: duplicate fact %s' % (label, fact_id))
        fact_ids.add(fact_id)
        text(fact['statement'], label + '.statement')
        text(fact['source'], label + '.source')
    check_rollback(data['rollback'], findings, 'rollback')
    if revision_verified and not any(
            node_states.get(node['id']) == 'reverified' and node.get('evidence_level') == 'E1'
            for node in nodes):
        add(findings, 'revision_verified_without_evidence', 'blocking',
            'revision_verified=true 需要至少一个 E1 reverified 节点', 'evidence.revision_verified')
    return findings, not_checked


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: %s' % key)
        result[key] = value
    return result


def load_record(path):
    raw = Path(path).read_text(encoding='utf-8')
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError('non-finite JSON: %s' % value)))


def invalid_result(message):
    return {
        'status': 'invalid_input',
        'error': message,
        'board_verified': BOARD_VERIFIED,
        'execution': EXECUTION,
        'hardware_execution': HARDWARE_EXECUTION,
        'findings': [],
        'not_checked': list(COMMON_NOT_CHECKED),
    }


def final_result(kind, findings, not_checked):
    ordered = []
    for item in COMMON_NOT_CHECKED + list(not_checked):
        if item not in ordered:
            ordered.append(item)
    return {
        'kind': kind,
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


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('calibration', 'change', 'graph'))
    parser.add_argument('record', help='path to a JSON record')
    args = parser.parse_args(argv)
    try:
        data = load_record(args.record)
        if args.kind == 'calibration':
            findings, not_checked = check_calibration(data)
        elif args.kind == 'change':
            findings, not_checked = check_change(data)
        else:
            findings, not_checked = check_graph(data)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps(invalid_result(str(exc)), ensure_ascii=False))
        return 2
    result = final_result(args.kind, findings, not_checked)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
