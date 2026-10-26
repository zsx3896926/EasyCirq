"""R4-WS5 (H calibration and I change impact) document, asset and CLI tests.

Fixtures are handwritten. Expected byte counts, CRCs and finding codes come
from the documented contract, not from importing the checker to generate
them. CLI tests run the real entry point and assert exit codes 0/1/2.
"""

import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zlib

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

ROOT = Path(__file__).resolve().parents[1]
DH = ROOT / 'design-hardware'
REF = DH / 'references' / 'decisions'
CASES = REF / 'cases'
ASSETS = DH / 'assets' / 'decisions'
SCRIPTS = DH / 'scripts'
SOURCE_REGISTER = DH / 'references' / 'source-register.md'

H01_REF = REF / 'h01-calibration-and-identity.md'
I01_REF = REF / 'i01-change-impact.md'
H01_CASE = CASES / 'r4-case-h01-measurement-node-calibration.md'
I01_CASE = CASES / 'r4-case-i01-legacy-product-revision.md'
CAL_TEMPLATE = ASSETS / 'calibration-record.template.json'
CAL_EXAMPLE = ASSETS / 'calibration-record.r4p3.example.json'
CHANGE_TEMPLATE = ASSETS / 'change-record.template.json'
CHANGE_EXAMPLE = ASSETS / 'change-record.r4p6.example.json'
GRAPH_TEMPLATE = ASSETS / 'change-impact-graph.template.json'
GRAPH_EXAMPLE = ASSETS / 'change-impact-graph.r4p6.example.json'

OWNED = [H01_REF, I01_REF, H01_CASE, I01_CASE, CAL_TEMPLATE, CAL_EXAMPLE,
         CHANGE_TEMPLATE, CHANGE_EXAMPLE, GRAPH_TEMPLATE, GRAPH_EXAMPLE,
         SCRIPTS / 'decision_record_check.py', Path(__file__)]

sys.path.insert(0, str(SCRIPTS))
import decision_record_check as check

UNKNOWN = '待查'

REFERENCE_HEADINGS = [
    '## 目录',
    '## 1. 触发条件',
    '## 2. 输入',
    '## 3. Agent 可独立完成的判断',
    '## 4. 必须停下的条件',
    '## 5. 决策规则与表',
    '## 6. 改变哪个工程决定',
    '## 7. 完整案例',
    '## 8. 证据与验证方式',
    '## 9. 与现有资产的分工',
    '## 10. 来源、未知与重评触发',
]
CORE_HEADINGS = REFERENCE_HEADINGS[1:7]
CASE_HEADINGS = [
    '## 1. 触发与用户任务',
    '## 2. 产品与真实材料',
    '## 3. 初始决定（错在哪）',
    '## 4. 判定依据（path:start-end）',
    '## 5. 修正后的决定、代价与三行用户可见摘要',
    '## 6. 记录类型与 typed block',
    '## 7. 验证与证据状态',
    '## 8. 未知、停止与重评',
    '## 9. 与现有资产分工',
]

ANCHOR_RE = re.compile(r'([A-Za-z0-9_./-]+\.(?:md|json)):(\d+)-(\d+)')
LINK_RE = re.compile(r'\[[^\]]+\]\(([^)]+)\)')

# Each path:start-end must resolve to a real range that still holds the
# keyword the sentence relies on. Values were checked by reading the current
# worktree files, not carried over from another checkout.
ANCHOR_KEYWORDS = {
    'design-hardware/references/calculations/analog-adc.md:383-395': ('校准',),
    'design-hardware/references/design-cards/analog/a05-vref.md:168-177': ('校准',),
    'design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:179-191': ('校准',),
    'design-hardware/references/projects/p02-industrial-rs485-analog.md:169-190': ('校准',),
    'design-hardware/references/projects/p02-industrial-rs485-analog.md:190-207': ('3905',),
    'design-hardware/references/projects/p02-industrial-rs485-analog.md:405-416': ('GPIO_ISO_EN',),
    'design-hardware/references/projects/p02-industrial-rs485-analog.md:424-434': ('B6', 'B9'),
    'design-hardware/references/projects/p02-industrial-rs485-analog.md:360-368': ('iso=0',),
    'design-hardware/references/projects/p02-industrial-rs485-analog.md:364-365': ('iso=0', 'iso=1'),
    'design-hardware/references/projects/p02-industrial-rs485-analog.md:370-374': ('25 块',),
    'design-hardware/references/manufacturing-routes.md:539-562': ('ECO',),
    'design-hardware/references/project-coherence.md:18-27': ('变更传播',),
    'docs/evidence/f1-2026-10-22/README.md:1-10': ('F1',),
    'docs/evidence/f1-2026-10-22/README.md:1-20': ('F1',),
}


def read_text(path):
    return path.read_text(encoding='utf-8')


def frontmatter(text):
    if not text.startswith('---\n'):
        return {}
    end = text.find('\n---', 4)
    if end < 0:
        return {}
    data = {}
    for line in text[4:end].splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
    return data


def section(text, heading):
    start = text.index(heading)
    nxt = text.find('\n## ', start + len(heading))
    return text[start:] if nxt < 0 else text[start:nxt]


def subsection(text, heading):
    start = text.index(heading)
    nxt = text.find('\n### ', start + len(heading))
    return text[start:] if nxt < 0 else text[start:nxt]


def line_count(text):
    return len(text.splitlines())


def payload_bytes(record):
    body = {key: record[key] for key in
            ('magic', 'schema_version', 'identity', 'cal_date',
             'cal_temp_c', 'source_id', 'channels')}
    return json.dumps(body, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('utf-8')


def seal(record):
    record = copy.deepcopy(record)
    raw = payload_bytes(record)
    record['length'] = len(raw)
    crc = '0x%08X' % (zlib.crc32(raw) & 0xFFFFFFFF)
    record['slots']['A']['crc32'] = crc
    record['slots']['B']['crc32'] = crc
    return record


def channel(number):
    return {'channel': number, 'offset': UNKNOWN, 'gain': UNKNOWN,
            'range': UNKNOWN, 'unit': UNKNOWN}


def calibration():
    return seal({
        'record_id': 'CAL-TEST-001',
        'magic': 'CALREC',
        'schema_version': 1,
        'length': 0,
        'identity': {'model': UNKNOWN, 'hw_rev': UNKNOWN,
                     'variant': 'V1', 'serial': UNKNOWN},
        'cal_date': UNKNOWN,
        'cal_temp_c': UNKNOWN,
        'source_id': UNKNOWN,
        'channels': [channel(1), channel(2)],
        'slots': {
            'A': {'sequence': 0, 'crc32': '0x00000000', 'status': 'uncalibrated'},
            'B': {'sequence': 0, 'crc32': '0x00000000', 'status': 'uncalibrated'},
        },
        'status': 'uncalibrated',
        'valid': False,
        'valid_until': UNKNOWN,
        'invalid_reason': '',
    })


def valid_calibration():
    record = calibration()
    record['cal_date'] = '2026-10-22'
    record['cal_temp_c'] = 25.0
    record['source_id'] = 'CAL-SRC-001'
    for item in record['channels']:
        item.update(offset=0.0, gain=1.0, range='4-20 mA', unit='mA')
    record['slots']['A'].update(sequence=1, status='valid')
    record['slots']['B'].update(sequence=1, status='valid')
    record['status'] = 'valid'
    record['valid'] = True
    record['valid_until'] = '2027-10-22'
    return seal(record)


def bom_item(**overrides):
    item = {'ref': 'R1', 'old': '100 Ω（MPN 待查）', 'new': '50 Ω（MPN 待查）',
            'qty': 1, 'dnp': 'no', 'reason': '测试原因'}
    item.update(overrides)
    return item


def bom_delta(**overrides):
    delta = {'status': 'planned', 'note': '测试 BOM 变化',
             'items': [bom_item()]}
    delta.update(overrides)
    return delta


def change():
    return {
        'change_id': 'ECO-TEST-01',
        'title': 'test change',
        'date': '2026-10-22',
        'status': 'draft',
        'baseline': {
            'product_baseline': '测试基线 V1',
            'eda_baseline': 'F1',
            'eda_baseline_level': 'E1',
            'eda_rerun_this_round': False,
            'role': 'baseline_only',
        },
        'changes': [{
            'change_id': 'CHG-01', 'scenario': 'shunt-change', 'level': 2,
            'from': '100 Ω', 'to': '50 Ω', 'reason': 'test',
            'status': 'planned', 'bom_delta': bom_delta(),
        }],
        'affected_artifacts': [{
            'artifact': 'schematic', 'ref': 'V1', 'state': 'invalidated',
            'reason': 'test',
        }],
        'netlist_diff': {'status': 'NOT RUN', 'evidence': '无'},
        'batch_scope': {'mode': 'not_applicable', 'detail': '无出货批次',
                        'effective_from': UNKNOWN, 'effective_to': UNKNOWN},
        'verification': [{'check': 'test', 'scope': 'CHG-01',
                          'result': 'NOT RUN', 'evidence_level': 'E3',
                          'evidence': ''}],
        'rollback': {'plan': '保留旧快照', 'disposition': 'not_applicable',
                     'reason': '未投产'},
        'approvals': {'engineering': UNKNOWN, 'manufacturing': UNKNOWN,
                      'quality': UNKNOWN},
        'revision_verified': False,
    }


def passing_verification(**overrides):
    item = {'check': '重验原理图', 'scope': 'schematic', 'result': 'pass',
            'evidence_level': 'E1',
            'evidence': 'design-hardware/references/projects/p02-industrial-rs485-analog.md:169-190'}
    item.update(overrides)
    return item


def graph():
    return {
        'graph_id': 'IMP-TEST-01',
        'change_id': 'ECO-TEST-01',
        'nodes': [
            {'id': 'schematic', 'kind': 'artifact', 'state': 'invalidated',
             'role': 'changed', 'evidence': 'test', 'evidence_level': 'E3'},
            {'id': 'netlist', 'kind': 'artifact', 'state': 'invalidated',
             'role': 'downstream', 'evidence': 'test', 'evidence_level': 'E3'},
            {'id': 'f1', 'kind': 'baseline', 'state': 'unchanged',
             'role': 'baseline_only', 'evidence': 'F1 baseline',
             'evidence_level': 'E1'},
        ],
        'edges': [
            {'from': 'schematic', 'to': 'netlist', 'relation': 'invalidates'},
        ],
        'old_parts': [
            {'ref': 'R1', 'state': 'invalidated', 'note': 'test'},
            {'ref': 'R2', 'state': 'unchanged', 'note': 'test'},
        ],
        'batch_scope': {'mode': 'not_applicable', 'detail': '无出货批次',
                        'effective_from': UNKNOWN, 'effective_to': UNKNOWN},
        'evidence': {'eda_baseline': 'F1', 'eda_baseline_level': 'E1',
                     'eda_rerun_this_round': False,
                     'role': 'baseline_only', 'revision_verified': False},
        'canonical_facts': [
            {'id': 'CF-01', 'statement': '测试事实', 'source': 'test'},
        ],
        'rollback': {'plan': '保留旧快照', 'disposition': 'not_applicable',
                     'reason': '未投产'},
    }


def codes(findings):
    return {item['code'] for item in findings}


class CalibrationRecord(unittest.TestCase):
    def test_uncalibrated_fixture_is_sealed_and_passes(self):
        record = calibration()
        self.assertEqual(record['length'], 440)
        self.assertEqual(record['slots']['A']['crc32'], '0xBDA6BB38')
        findings, not_checked = check.check_calibration(record)
        self.assertEqual(findings, [])
        self.assertIn('校准值 offset/gain/range 均为待查', not_checked)

    def test_record_id_is_not_part_of_payload(self):
        record = calibration()
        before = (record['length'], record['slots']['A']['crc32'])
        record['record_id'] = 'CAL-OTHER-002'
        record = seal(record)
        self.assertEqual((record['length'], record['slots']['A']['crc32']), before)
        findings, _ = check.check_calibration(record)
        self.assertEqual(findings, [])

    def test_valid_fixture_passes_with_real_valid_until(self):
        record = valid_calibration()
        self.assertEqual(record['valid_until'], '2027-10-22')
        findings, _ = check.check_calibration(record)
        self.assertEqual(findings, [])

    def test_valid_without_valid_until_is_blocking(self):
        record = valid_calibration()
        record['valid_until'] = UNKNOWN
        findings, _ = check.check_calibration(record)
        self.assertIn('valid_without_valid_until', codes(findings))

    def test_valid_with_malformed_valid_until_is_blocking(self):
        record = valid_calibration()
        record['valid_until'] = '2026-13-40'
        findings, _ = check.check_calibration(record)
        self.assertIn('invalid_valid_until', codes(findings))

    def test_valid_with_impossible_calendar_date_is_blocking(self):
        record = valid_calibration()
        record['valid_until'] = '2026-02-30'
        findings, _ = check.check_calibration(record)
        self.assertIn('invalid_valid_until', codes(findings))

    def test_expired_with_malformed_valid_until_is_blocking(self):
        record = valid_calibration()
        record['status'] = 'expired'
        record['valid'] = False
        record['valid_until'] = '2026-02-30'
        findings, _ = check.check_calibration(record)
        self.assertIn('invalid_valid_until', codes(findings))
        self.assertNotIn('expired_without_valid_until', codes(findings))

    def test_uncalibrated_with_unparseable_valid_until_still_passes(self):
        record = calibration()
        record['valid_until'] = '以后再说'
        findings, _ = check.check_calibration(record)
        self.assertEqual(findings, [])

    def test_record_id_must_use_cal_prefix(self):
        record = calibration()
        record['record_id'] = 'REC-001'
        with self.assertRaises(ValueError):
            check.check_calibration(record)

    def test_missing_record_id_is_input_error(self):
        record = calibration()
        del record['record_id']
        with self.assertRaises(ValueError):
            check.check_calibration(record)

    def test_uncalibrated_with_values_is_blocking(self):
        record = calibration()
        record['channels'][0]['offset'] = 0.0
        record = seal(record)
        findings, _ = check.check_calibration(record)
        self.assertIn('uncalibrated_has_values', codes(findings))

    def test_valid_flag_false_is_blocking(self):
        record = valid_calibration()
        record['valid'] = False
        findings, _ = check.check_calibration(record)
        self.assertIn('valid_flag_false', codes(findings))

    def test_crc_and_length_mismatch_are_blocking(self):
        record = calibration()
        record['slots']['A']['crc32'] = '0x00000000'
        record['length'] = record['length'] + 1
        findings, _ = check.check_calibration(record)
        self.assertTrue({'crc_mismatch', 'length_mismatch'} <= codes(findings))

    def test_slot_sequence_conflict(self):
        record = valid_calibration()
        record['slots']['B']['sequence'] = 2
        findings, _ = check.check_calibration(record)
        self.assertIn('slot_sequence_conflict', codes(findings))

    def test_invalid_status_requires_reason_and_slot(self):
        record = calibration()
        record['status'] = 'invalid'
        record['slots']['A']['status'] = 'valid'
        record['slots']['B']['status'] = 'valid'
        record = seal(record)
        findings, _ = check.check_calibration(record)
        self.assertTrue({'invalid_without_reason', 'invalid_without_invalid_slot'}
                        <= codes(findings))

    def test_expired_requires_valid_until(self):
        record = valid_calibration()
        record['status'] = 'expired'
        record['valid'] = False
        record['valid_until'] = UNKNOWN
        findings, _ = check.check_calibration(record)
        self.assertIn('expired_without_valid_until', codes(findings))

    def test_missing_required_field_is_input_error(self):
        record = calibration()
        del record['identity']
        with self.assertRaises(ValueError):
            check.check_calibration(record)

    def test_duplicate_channel_is_input_error(self):
        record = calibration()
        record['channels'][1]['channel'] = 1
        record = seal(record)
        with self.assertRaises(ValueError):
            check.check_calibration(record)


class ChangeRecord(unittest.TestCase):
    def test_minimal_fixture_passes(self):
        findings, not_checked = check.check_change(change())
        self.assertEqual(findings, [])
        self.assertIn('复验项：test', not_checked)

    def test_scenario_level_mapping(self):
        record = change()
        record['changes'][0]['level'] = 3
        findings, _ = check.check_change(record)
        self.assertIn('scenario_level_mismatch', codes(findings))

    def test_layout_only_level_is_local_only(self):
        record = change()
        record['changes'][0].update(scenario='layout-only', level=2)
        record['changes'][0]['bom_delta'] = {
            'status': 'unchanged', 'note': 'BOM 不变，CPL/坐标变化，NOT RUN',
            'items': []}
        findings, _ = check.check_change(record)
        self.assertIn('scenario_level_mismatch', codes(findings))

    def test_f1_cannot_be_revision_evidence(self):
        record = change()
        record['baseline']['role'] = 'revision_evidence'
        findings, _ = check.check_change(record)
        self.assertIn('f1_baseline_role_invalid', codes(findings))

    def test_f1_revision_verified_is_blocking(self):
        record = change()
        record['revision_verified'] = True
        findings, _ = check.check_change(record)
        self.assertIn('f1_baseline_cannot_verify_revision', codes(findings))

    def test_pass_requires_e1(self):
        record = change()
        record['verification'][0].update(
            result='pass', evidence_level='E3',
            evidence='design-hardware/references/projects/p02-industrial-rs485-analog.md:169-190')
        findings, _ = check.check_change(record)
        self.assertIn('pass_without_e1', codes(findings))
        self.assertNotIn('pass_without_evidence', codes(findings))

    def test_pass_with_empty_evidence_is_blocking(self):
        record = change()
        record['verification'][0].update(result='pass', evidence_level='E1',
                                          evidence='')
        findings, _ = check.check_change(record)
        self.assertIn('pass_without_evidence', codes(findings))

    def test_pass_with_unparseable_evidence_is_blocking(self):
        record = change()
        record['verification'][0].update(result='pass', evidence_level='E1',
                                          evidence='脚本说没问题')
        findings, _ = check.check_change(record)
        self.assertIn('pass_without_evidence', codes(findings))

    def test_pass_with_source_id_evidence_passes(self):
        record = change()
        record['verification'][0].update(result='pass', evidence_level='E1',
                                          evidence='MFG-S05 §2 BOM 字段与 DNP')
        findings, _ = check.check_change(record)
        self.assertEqual(findings, [])

    def test_pass_with_path_range_evidence_passes(self):
        record = change()
        record['verification'][0].update(passing_verification())
        findings, _ = check.check_change(record)
        self.assertEqual(findings, [])

    def test_f1_pass_is_blocking_even_with_e1(self):
        record = change()
        record['verification'][0].update(result='pass', evidence_level='E1',
                                          evidence='F1 baseline')
        findings, _ = check.check_change(record)
        self.assertIn('f1_cannot_verify_revision', codes(findings))
        self.assertIn('pass_without_evidence', codes(findings))

    def test_reverified_artifact_with_matching_scope_passes(self):
        record = change()
        record['affected_artifacts'][0]['state'] = 'reverified'
        record['verification'][0] = passing_verification()
        findings, _ = check.check_change(record)
        self.assertEqual(findings, [])

    def test_reverified_artifact_scope_must_match(self):
        record = change()
        record['affected_artifacts'][0]['state'] = 'reverified'
        record['verification'][0] = passing_verification(scope='pcb')
        findings, _ = check.check_change(record)
        self.assertIn('reverified_scope_mismatch', codes(findings))
        self.assertNotIn('reverified_without_e1', codes(findings))

    def test_reverified_by_change_id_in_artifact_reason_passes(self):
        record = change()
        record['affected_artifacts'][0].update(state='reverified',
                                               reason='CHG-01/02')
        record['verification'][0] = passing_verification(scope='CHG-01')
        findings, _ = check.check_change(record)
        self.assertEqual(findings, [])

    def test_frozen_with_not_run_is_blocking(self):
        record = change()
        record['status'] = 'frozen'
        findings, _ = check.check_change(record)
        self.assertIn('frozen_with_unverified_items', codes(findings))

    def test_layout_unchanged_without_diff_is_blocking(self):
        record = change()
        record['changes'][0].update(scenario='layout-only', level='local-only')
        record['changes'][0]['bom_delta'] = {
            'status': 'unchanged', 'note': 'BOM 不变，CPL/坐标变化，NOT RUN',
            'items': []}
        record['netlist_diff'] = {'status': 'unchanged', 'evidence': ''}
        findings, _ = check.check_change(record)
        self.assertIn('netlist_unchanged_without_diff', codes(findings))

    def test_unknown_batch_scope_is_unknown_finding(self):
        record = change()
        record['batch_scope']['mode'] = 'unknown'
        findings, not_checked = check.check_change(record)
        self.assertIn('batch_scope_unknown', codes(findings))
        self.assertTrue(any(item['severity'] == 'unknown' for item in findings))
        self.assertIn('出货批次/序列号生效范围', not_checked)

    def test_reverified_artifact_requires_e1(self):
        record = change()
        record['affected_artifacts'][0]['state'] = 'reverified'
        findings, _ = check.check_change(record)
        self.assertIn('reverified_without_e1', codes(findings))

    def test_bom_delta_is_required(self):
        record = change()
        del record['changes'][0]['bom_delta']
        with self.assertRaises(ValueError):
            check.check_change(record)

    def test_non_layout_scenario_without_items_is_blocking(self):
        record = change()
        record['changes'][0]['bom_delta'] = {
            'status': 'planned', 'note': '忘了写', 'items': []}
        findings, _ = check.check_change(record)
        self.assertIn('bom_delta_missing', codes(findings))

    def test_unknown_bom_delta_is_not_checked(self):
        record = change()
        record['changes'][0]['bom_delta'] = {
            'status': 'unknown', 'note': 'schema 未定', 'items': []}
        findings, not_checked = check.check_change(record)
        self.assertNotIn('bom_delta_missing', codes(findings))
        self.assertIn('BOM delta：shunt-change', not_checked)

    def test_layout_only_bom_must_be_unchanged(self):
        record = change()
        record['changes'][0].update(scenario='layout-only', level='local-only')
        record['changes'][0]['bom_delta'] = {
            'status': 'planned', 'note': '换了一颗电阻', 'items': [bom_item()]}
        findings, _ = check.check_change(record)
        self.assertIn('layout_only_bom_delta', codes(findings))

    def test_layout_only_note_must_state_cpl_and_not_run(self):
        record = change()
        record['changes'][0].update(scenario='layout-only', level='local-only')
        record['changes'][0]['bom_delta'] = {
            'status': 'unchanged', 'note': 'BOM 不变', 'items': []}
        findings, _ = check.check_change(record)
        self.assertIn('layout_only_bom_delta', codes(findings))

    def test_layout_only_with_full_note_passes(self):
        record = change()
        record['changes'][0].update(scenario='layout-only', level='local-only')
        record['changes'][0]['bom_delta'] = {
            'status': 'unchanged', 'note': 'BOM 不变，CPL/坐标变化，NOT RUN',
            'items': []}
        findings, _ = check.check_change(record)
        self.assertEqual(findings, [])

    def test_bom_item_rejects_zero_quantity(self):
        record = change()
        record['changes'][0]['bom_delta']['items'][0]['qty'] = 0
        with self.assertRaises(ValueError):
            check.check_change(record)

    def test_bom_item_rejects_unknown_dnp_value(self):
        record = change()
        record['changes'][0]['bom_delta']['items'][0]['dnp'] = 'maybe'
        with self.assertRaises(ValueError):
            check.check_change(record)

    def test_bom_item_allows_unknown_quantity(self):
        record = change()
        record['changes'][0]['bom_delta']['items'][0]['qty'] = UNKNOWN
        findings, _ = check.check_change(record)
        self.assertEqual(findings, [])

    def test_missing_required_field_is_input_error(self):
        record = change()
        del record['baseline']
        with self.assertRaises(ValueError):
            check.check_change(record)

    def test_superseded_requires_reference(self):
        record = change()
        record['status'] = 'superseded'
        with self.assertRaises(ValueError):
            check.check_change(record)


class ImpactGraph(unittest.TestCase):
    def test_minimal_fixture_passes(self):
        findings, _ = check.check_graph(graph())
        self.assertEqual(findings, [])

    def test_stale_downstream_is_blocking(self):
        record = graph()
        record['nodes'][1]['state'] = 'unchanged'
        findings, _ = check.check_graph(record)
        self.assertIn('stale_downstream_artifact', codes(findings))

    def test_baseline_node_must_not_change(self):
        record = graph()
        record['nodes'][2]['state'] = 'updated'
        findings, _ = check.check_graph(record)
        self.assertIn('baseline_node_modified', codes(findings))

    def test_f1_role_must_be_baseline_only(self):
        record = graph()
        record['evidence']['role'] = 'revision_evidence'
        findings, _ = check.check_graph(record)
        self.assertIn('f1_baseline_role_invalid', codes(findings))

    def test_unknown_edge_node_is_input_error(self):
        record = graph()
        record['edges'][0]['to'] = 'missing'
        with self.assertRaises(ValueError):
            check.check_graph(record)

    def test_duplicate_node_is_input_error(self):
        record = graph()
        record['nodes'][1]['id'] = 'schematic'
        with self.assertRaises(ValueError):
            check.check_graph(record)

    def test_reverified_node_requires_e1(self):
        record = graph()
        record['nodes'][0].update(state='reverified', evidence_level='E3')
        findings, _ = check.check_graph(record)
        self.assertIn('reverified_without_e1', codes(findings))

    def test_revision_verified_requires_reverified_node(self):
        record = graph()
        record['evidence']['revision_verified'] = True
        findings, _ = check.check_graph(record)
        self.assertIn('revision_verified_without_evidence', codes(findings))


class ReferenceDocuments(unittest.TestCase):
    def test_frontmatter_and_headings(self):
        expected = {
            H01_REF: ('R4-H', '[H]'),
            I01_REF: ('R4-I', '[I]'),
        }
        for path, (doc_id, package) in expected.items():
            with self.subTest(path=path.name):
                text = read_text(path)
                meta = frontmatter(text)
                self.assertEqual(meta.get('id'), doc_id)
                self.assertEqual(meta.get('packages'), package)
                self.assertEqual(meta.get('evidence'), 'E3')
                self.assertEqual(meta.get('last_reviewed'), '2026-10-22')
                self.assertTrue(meta.get('sources'))
                last = -1
                for heading in REFERENCE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, last, heading)
                    last = pos

    def test_six_core_sections_are_present(self):
        for path in (H01_REF, I01_REF):
            with self.subTest(path=path.name):
                text = read_text(path)
                previous = -1
                for heading in CORE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, previous, heading)
                    previous = pos

    def test_line_budget(self):
        for path in (H01_REF, I01_REF):
            with self.subTest(path=path.name):
                count = line_count(read_text(path))
                self.assertGreaterEqual(count, 60)
                self.assertLessEqual(count, 100)

    def test_source_table_documents_range_and_reopen_status(self):
        for path in (H01_REF, I01_REF):
            with self.subTest(path=path.name):
                text = read_text(path)
                ids = re.findall(r'[A-Z]+-S\d+',
                                 frontmatter(text).get('sources', ''))
                segment = section(text, '## 10. 来源、未知与重评触发')
                for source in ids:
                    self.assertIn('| %s |' % source, segment)
                self.assertIn('未重开', segment)

    def test_section9_budget_and_anchors(self):
        for path in (H01_REF, I01_REF):
            with self.subTest(path=path.name):
                text = read_text(path)
                segment = section(text, '## 9. 与现有资产的分工')
                self.assertLessEqual(line_count(segment), 8)
                matches = ANCHOR_RE.findall(segment)
                self.assertGreaterEqual(len(matches), 2)
                for relative, start, end in matches:
                    target = ROOT / relative
                    self.assertTrue(target.is_file(), relative)
                    self.assertLessEqual(int(end),
                                         line_count(read_text(target)), relative)
                    self.assertLessEqual(int(start), int(end), relative)


class CaseDocuments(unittest.TestCase):
    def test_frontmatter_and_headings(self):
        expected = {
            H01_CASE: ('R4-CASE-H01', 'R4-P3', '[H]', '[unknown-retained]'),
            I01_CASE: ('R4-CASE-I01', 'R4-P6', '[I]', '[local-only]'),
        }
        for path, (case_id, project, package, record_types) in expected.items():
            with self.subTest(path=path.name):
                text = read_text(path)
                meta = frontmatter(text)
                self.assertEqual(meta.get('id'), case_id)
                self.assertEqual(meta.get('project'), project)
                self.assertEqual(meta.get('family'), 'P02')
                self.assertEqual(meta.get('parent'), 'P02')
                self.assertEqual(meta.get('packages'), package)
                self.assertEqual(meta.get('evidence'), 'E3')
                self.assertEqual(meta.get('execution'), 'OFFLINE_PLANNING')
                self.assertEqual(meta.get('hardware_execution'), 'NOT RUN')
                self.assertEqual(meta.get('last_reviewed'), '2026-10-22')
                self.assertTrue(meta.get('facts_source'))
                self.assertEqual(meta.get('record_types'), record_types)
                last = -1
                for heading in CASE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, last, heading)
                    last = pos

    def test_line_budget(self):
        for path in (H01_CASE, I01_CASE):
            with self.subTest(path=path.name):
                count = line_count(read_text(path))
                self.assertGreaterEqual(count, 50)
                self.assertLessEqual(count, 90)

    def test_three_line_user_summary(self):
        for path in (H01_CASE, I01_CASE):
            with self.subTest(path=path.name):
                summary = section(
                    read_text(path),
                    '## 5. 修正后的决定、代价与三行用户可见摘要')
                for prefix in ('- 决定：', '- 代价：', '- 下一个检查或待查：'):
                    matching = [line for line in summary.splitlines()
                                if line.startswith(prefix)]
                    self.assertEqual(len(matching), 1, prefix)

    def test_section9_starts_with_method_backlink(self):
        expected = {
            H01_CASE: '../h01-calibration-and-identity.md',
            I01_CASE: '../i01-change-impact.md',
        }
        for path, target in expected.items():
            with self.subTest(path=path.name):
                segment = section(read_text(path), '## 9. 与现有资产分工')
                bullets = [line for line in segment.splitlines()
                           if line.startswith('- ')]
                self.assertTrue(bullets, path.name)
                self.assertIn(target, bullets[0])

    def test_section9_budget_and_anchors(self):
        for path in (H01_CASE, I01_CASE):
            with self.subTest(path=path.name):
                segment = section(read_text(path), '## 9. 与现有资产分工')
                self.assertLessEqual(line_count(segment), 8)
                matches = ANCHOR_RE.findall(segment)
                self.assertGreaterEqual(len(matches), 2)
                for relative, start, end in matches:
                    target = ROOT / relative
                    self.assertTrue(target.is_file(), relative)
                    self.assertLessEqual(int(end),
                                         line_count(read_text(target)), relative)


class ContentChecks(unittest.TestCase):
    def test_all_path_anchors_resolve_and_keep_keywords(self):
        for path in (H01_REF, I01_REF, H01_CASE, I01_CASE,
                     CHANGE_TEMPLATE, CHANGE_EXAMPLE, GRAPH_EXAMPLE):
            text = read_text(path)
            for relative, start, end in ANCHOR_RE.findall(text):
                key = '%s:%s-%s' % (relative, start, end)
                with self.subTest(path=path.name, anchor=key):
                    target = ROOT / relative
                    self.assertTrue(target.is_file(), key)
                    lines = read_text(target).splitlines()
                    self.assertGreaterEqual(int(start), 1, key)
                    self.assertLessEqual(int(end), len(lines), key)
                    self.assertLessEqual(int(start), int(end), key)
                    segment = '\n'.join(lines[int(start) - 1:int(end)])
                    self.assertTrue(segment.strip(), key)
                    self.assertIn(key, ANCHOR_KEYWORDS)
                    for keyword in ANCHOR_KEYWORDS[key]:
                        self.assertIn(keyword, segment, key)

    def test_source_ids_are_registered(self):
        registered = set(re.findall(r'\|\s*([A-Z]+-S\d+)\s*\|',
                                    read_text(SOURCE_REGISTER)))
        for path in (H01_REF, I01_REF, H01_CASE, I01_CASE):
            with self.subTest(path=path.name):
                raw = frontmatter(read_text(path)).get('sources', '')
                ids = re.findall(r'[A-Z]+-S\d+', raw)
                self.assertTrue(ids)
                self.assertTrue(set(ids) <= registered, set(ids) - registered)

    def test_relative_links_point_to_existing_files(self):
        for path in (H01_REF, I01_REF, H01_CASE, I01_CASE):
            with self.subTest(path=path.name):
                for target in LINK_RE.findall(read_text(path)):
                    if target.startswith(('http://', 'https://')):
                        continue
                    relative = target.split('#', 1)[0]
                    self.assertTrue((path.parent / relative).is_file(), target)

    def test_i01_reference_bom_delta_covers_every_scenario(self):
        text = read_text(I01_REF)
        segment = subsection(text, '### 5.2 BOM delta')
        for column in ('位号', '旧值/MPN', '新值/MPN', '数量', 'DNP', '原因'):
            self.assertIn(column, segment)
        for scenario in ('换分流', '换 MCU 封装', '加隔离', '纯重排布局'):
            self.assertIn(scenario, segment)
        self.assertIn('BOM 不变，CPL/坐标变化，NOT RUN', segment)

    def test_i01_case_bom_delta_covers_every_scenario(self):
        segment = section(read_text(I01_CASE),
                          '## 5. 修正后的决定、代价与三行用户可见摘要')
        for column in ('位号', '旧值/MPN', '新值/MPN', '数量', 'DNP', '原因'):
            self.assertIn(column, segment)
        for scenario in ('换分流', '换 MCU 封装', '加隔离', '纯重排布局'):
            self.assertIn(scenario, segment)
        self.assertIn('BOM 不变，CPL/坐标变化，NOT RUN', segment)

    def test_change_example_has_bom_delta_for_each_scenario(self):
        data = json.loads(read_text(CHANGE_EXAMPLE))
        scenarios = {}
        for change in data['changes']:
            scenarios[change['scenario']] = change['bom_delta']
            for key in ('status', 'note', 'items'):
                self.assertIn(key, change['bom_delta'])
        self.assertEqual(set(scenarios),
                         {'shunt-change', 'mcu-package-change',
                          'isolation-add', 'layout-only'})
        layout = scenarios['layout-only']
        self.assertEqual(layout['status'], 'unchanged')
        self.assertEqual(layout['items'], [])
        self.assertIn('BOM 不变，CPL/坐标变化，NOT RUN', layout['note'])
        for scenario in ('shunt-change', 'mcu-package-change', 'isolation-add'):
            delta = scenarios[scenario]
            self.assertEqual(delta['status'], 'planned', scenario)
            self.assertTrue(delta['items'], scenario)
            for item in delta['items']:
                self.assertTrue({'ref', 'old', 'new', 'qty', 'dnp', 'reason'}
                                <= set(item))
        raw = read_text(CHANGE_EXAMPLE)
        self.assertNotIn('"price"', raw)
        self.assertNotIn('"stock"', raw)
        self.assertNotIn('"moq"', raw)

    def test_h01_record_id_is_traceable(self):
        example = json.loads(read_text(CAL_EXAMPLE))
        self.assertEqual(example['record_id'], 'CAL-P3-001')
        self.assertEqual(example['status'], 'uncalibrated')
        self.assertFalse(example['valid'])
        template = json.loads(read_text(CAL_TEMPLATE))
        self.assertIn('record_id', template)
        case_text = read_text(H01_CASE)
        self.assertIn('CAL-P3-001', case_text)
        self.assertIn('DEC-P3-CAL-01（待建）', case_text)
        self.assertIn('CAL-P3-001', read_text(H01_REF))

    def test_h01_valid_until_documented(self):
        text = read_text(H01_REF)
        self.assertIn('valid_until', text)
        self.assertIn('YYYY-MM-DD', text)
        self.assertIn('valid_without_valid_until', text)
        self.assertIn('invalid_valid_until', text)

    def test_i01_iso_reference_uses_variant_table(self):
        text = read_text(I01_CASE)
        self.assertIn('p02-industrial-rs485-analog.md:364-365', text)
        self.assertIn('p02-industrial-rs485-analog.md:405-416', text)
        self.assertNotIn('p02-industrial-rs485-analog.md:405-416`：隔离变体用 `iso=0/1`', text)


class TemplatesAndAssets(unittest.TestCase):
    def test_template_headers_and_budgets(self):
        for path in (CAL_TEMPLATE, CHANGE_TEMPLATE, GRAPH_TEMPLATE):
            with self.subTest(path=path.name):
                text = read_text(path)
                head = '\n'.join(text.splitlines()[:2])
                self.assertIn('Agent 填写，用户不填', head)
                count = line_count(text)
                self.assertGreaterEqual(count, 25)
                self.assertLessEqual(count, 60)

    def test_json_assets_parse(self):
        for path in (CAL_TEMPLATE, CAL_EXAMPLE, CHANGE_TEMPLATE,
                     CHANGE_EXAMPLE, GRAPH_TEMPLATE, GRAPH_EXAMPLE):
            with self.subTest(path=path.name):
                json.loads(read_text(path))

    def test_owned_files_are_utf8_lf_without_todo(self):
        marker = '[' + 'TODO'
        for path in OWNED:
            with self.subTest(path=path.name):
                data = path.read_bytes()
                self.assertFalse(data.startswith(b'\xef\xbb\xbf'), 'BOM')
                self.assertNotIn(b'\r\n', data, 'CRLF')
                text = data.decode('utf-8')
                self.assertNotIn(chr(0xFFFD), text)
                self.assertNotIn(marker, text)


class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / 'decision_record_check.py'),
                               *args], capture_output=True, text=True,
                              encoding='utf-8', env={**os.environ,
                                                    'PYTHONIOENCODING': 'utf-8'})

    def write(self, directory, name, data):
        path = Path(directory) / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def test_examples_exit_zero_and_emit_single_json(self):
        cases = [
            ('calibration', CAL_EXAMPLE),
            ('change', CHANGE_EXAMPLE),
            ('graph', GRAPH_EXAMPLE),
        ]
        for kind, path in cases:
            with self.subTest(kind=kind):
                result = self.run_cli(kind, str(path))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(len(result.stdout.strip().splitlines()), 1)
                data = json.loads(result.stdout)
                self.assertEqual(data['status'], 'pass')
                self.assertFalse(data['board_verified'])
                self.assertEqual(data['execution'], 'OFFLINE_PLANNING')
                self.assertEqual(data['hardware_execution'], 'NOT RUN')
                self.assertIsInstance(data['not_checked'], list)

    def test_findings_exit_one(self):
        with tempfile.TemporaryDirectory() as temp:
            record = change()
            record['baseline']['role'] = 'revision_evidence'
            path = self.write(temp, 'bad-change.json', record)
            result = self.run_cli('change', path)
            self.assertEqual(result.returncode, 1)
            data = json.loads(result.stdout)
            self.assertEqual(data['status'], 'needs_review')
            self.assertTrue(data['findings'])
            self.assertIn('f1_baseline_role_invalid',
                          {item['code'] for item in data['findings']})

    def test_invalid_valid_until_exits_one(self):
        with tempfile.TemporaryDirectory() as temp:
            record = valid_calibration()
            record['valid_until'] = '2026-13-40'
            path = self.write(temp, 'bad-date.json', record)
            result = self.run_cli('calibration', path)
            self.assertEqual(result.returncode, 1)
            data = json.loads(result.stdout)
            self.assertEqual(data['status'], 'needs_review')
            self.assertIn('invalid_valid_until',
                          {item['code'] for item in data['findings']})

    def test_pass_without_evidence_exits_one(self):
        with tempfile.TemporaryDirectory() as temp:
            record = change()
            record['verification'][0].update(result='pass', evidence_level='E1',
                                              evidence='')
            path = self.write(temp, 'empty-evidence.json', record)
            result = self.run_cli('change', path)
            self.assertEqual(result.returncode, 1)
            self.assertIn('pass_without_evidence',
                          {item['code'] for item in json.loads(result.stdout)['findings']})

    def test_stale_graph_exits_one(self):
        with tempfile.TemporaryDirectory() as temp:
            record = graph()
            record['nodes'][1]['state'] = 'unchanged'
            path = self.write(temp, 'stale-graph.json', record)
            result = self.run_cli('graph', path)
            self.assertEqual(result.returncode, 1)
            data = json.loads(result.stdout)
            self.assertIn('stale_downstream_artifact',
                          {item['code'] for item in data['findings']})

    def test_invalid_json_exits_two(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'broken.json'
            path.write_text('{not json', encoding='utf-8')
            result = self.run_cli('calibration', str(path))
            self.assertEqual(result.returncode, 2)
            data = json.loads(result.stdout)
            self.assertEqual(data['status'], 'invalid_input')
            self.assertFalse(data['board_verified'])

    def test_missing_field_exits_two(self):
        with tempfile.TemporaryDirectory() as temp:
            record = calibration()
            del record['slots']
            path = self.write(temp, 'missing.json', record)
            result = self.run_cli('calibration', path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'invalid_input')

    def test_bad_record_id_exits_two(self):
        with tempfile.TemporaryDirectory() as temp:
            record = calibration()
            record['record_id'] = 'REC-001'
            path = self.write(temp, 'bad-id.json', record)
            result = self.run_cli('calibration', path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'invalid_input')

    def test_missing_file_exits_two(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'does-not-exist.json')
            result = self.run_cli('calibration', path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'invalid_input')

    def test_bad_kind_and_missing_args_exit_two_with_json(self):
        for args in [('bogus', 'x.json'), ()]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                data = json.loads(result.stdout)
                self.assertEqual(data['status'], 'invalid_input')


if __name__ == '__main__':
    unittest.main()
