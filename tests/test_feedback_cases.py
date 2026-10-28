import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from feedback import cases as case_lib  # noqa: E402
from feedback import schemas  # noqa: E402


def pass_level(*evidence):
    return {'status': schemas.STATUS_PASS, 'evidence': list(evidence)}


def not_run():
    return {'status': schemas.STATUS_NOT_RUN, 'evidence': []}


def evidence_file(path):
    return {'kind': 'file', 'path': path}


def photo_case():
    """Case built from the real 5V photo-LED PCB report (2026-10-26)."""
    case = case_lib.case_template()
    case.update({
        'id': 'photo-led-5v-pcb',
        'version': 1,
        'goal': '5V photoresistor controlled LED board PCB layout and routing',
        'applies_when': {
            'power_w': {'min': 0.1, 'max': 1.0},
            'interfaces': ['power-2pin', 'analog'],
            'topologies': ['comparator', 'led-driver'],
            'footprints': ['DIP-8', '0805', 'LED-5mm'],
            'layers': 2,
            'process': 'jlcpcb-2layer-1.6mm',
            'tags': ['led', 'photoresistor', 'analog', '5v',
                     'through-hole'],
            'device': {'name': 'LM393', 'version': 'DIP-8'},
        },
        'does_not_apply_when': ['mains voltage', 'high current LED string'],
        'inputs': ['90x60mm outline', 'J1 power input'],
        'provenance': {
            'source_project': 'photo-led-pcb-20261026',
            'source_case': 'easycirq/cases/photo-led-pcb-2026-10-26',
            'artifacts': ['photo-led-pcb-final.epro2'],
            'verified_at': '2026-10-26T00:00:00Z',
            'stale': False,
        },
        'tool_versions': {'easyeda': '4.1.78', 'easyeda-agent': '1.15.0'},
        'original_problem': 'Place and route 19 parts on a 90x60mm board '
                            'without collisions or DRC errors.',
        'method': 'Offline placement candidate, then typed apply, router, '
                  'GND pour and native DRC.',
        'before_after': {
            'before': 'Parts imported in one row outside the outline.',
            'after': '19/19 placed, 8/8 signal nets routed, DRC 0.',
            'changes': ['moved J1 rotation 90 to 270'],
        },
        'check_method': ['pcb check', 'native DRC', 'save/reload diff'],
        'evidence': [evidence_file('evidence/pcb-drc-final.json')],
        'verification_levels': {
            'structural': pass_level(evidence_file(
                'evidence/placement-check-final.json')),
            'host_readback': pass_level(evidence_file(
                'evidence/save-reload-diff.json')),
            'erc_drc': pass_level(evidence_file(
                'evidence/pcb-drc-final.json')),
            'simulation': not_run(),
            'manufacturing': not_run(),
            'physical': not_run(),
        },
        'limits': ['gerber/drill/CPL export blocked by CLI',
                   'no physical, thermal or EMC test'],
        'failed_attempts': ['empty +5V pour produced 0 copper'],
        'invalidation_conditions': ['power above 1W', 'different DIP-8 '
                                    'footprint'],
        'source_tier': 'reusable',
    })
    return case


def mcu_case():
    """Case built from the real MCU + I2C sensor board report."""
    case = case_lib.case_template()
    case.update({
        'id': 'mcu-i2c-s3-pcb',
        'version': 1,
        'goal': 'ESP32-S3 MCU with I2C sensor, USB-C and LDO regulator',
        'applies_when': {
            'power_w': {'min': 0.5, 'max': 2.5},
            'interfaces': ['usb', 'i2c'],
            'topologies': ['ldo', 'usb-serial-jtag'],
            'footprints': ['SMD-module', '0402', '0805'],
            'layers': 2,
            'process': 'jlcpcb-2layer-1.6mm',
            'tags': ['mcu', 'i2c', 'sensor', 'usb', 'esp32-s3'],
            'device': {'name': 'ESP32-S3-WROOM-1', 'version': 'WROOM-1'},
        },
        'does_not_apply_when': ['no antenna keepout', 'mains voltage'],
        'inputs': ['65.79x45mm outline', 'USB-C input'],
        'provenance': {
            'source_project': 'mcu-i2c-s3-20261026',
            'source_case': 'easycirq/cases/mcu-i2c-s3-2026-10-26',
            'artifacts': ['boardB-final.epro2'],
            'verified_at': '2026-10-26T00:00:00Z',
            'stale': False,
        },
        'tool_versions': {'easyeda': '4.1.78', 'easyeda-agent': '1.15.0'},
        'original_problem': 'Fit MCU, LDO, USB and sensor on a two-layer '
                            'board with an antenna keepout.',
        'method': 'Relational block preflight, placement plan, router, '
                  'GND pour, DRC and save/reload.',
        'before_after': {
            'before': '23 parts in one row outside the outline.',
            'after': '23/23 placed, DRC 45 to 0 after keepout and pour fix.',
            'changes': ['J1 moved 2.1 mil from the board edge'],
        },
        'check_method': ['pcb check', 'native DRC', 'save/reload diff'],
        'evidence': [evidence_file('evidence/pcb-drc-final.json')],
        'verification_levels': {
            'structural': pass_level(evidence_file(
                'evidence/placement-apply-report.json')),
            'host_readback': pass_level(evidence_file(
                'evidence/save-reload-diff.json')),
            'erc_drc': pass_level(evidence_file(
                'evidence/pcb-drc-final.json')),
            'simulation': not_run(),
            'manufacturing': not_run(),
            'physical': not_run(),
        },
        'limits': ['LDO stability NOT VERIFIED',
                   'USB full-speed not SI signed off'],
        'failed_attempts': ['hand-routed +3V3 stubs made 20 clearance errors'],
        'invalidation_conditions': ['different MCU module',
                                    'four-layer stackup'],
        'source_tier': 'reusable',
    })
    return case


def candidate_case():
    case = case_lib.case_template()
    case.update({
        'id': 'candidate-buck-rule',
        'version': 1,
        'goal': 'Candidate rule: buck converter placement near input',
        'applies_when': {
            'power_w': {'min': 1.0, 'max': 10.0},
            'interfaces': ['power-2pin'],
            'topologies': ['buck'],
            'footprints': ['SOT-23-6', '0805'],
            'layers': 4,
            'process': 'jlcpcb-4layer-1.6mm',
            'tags': ['buck', 'power'],
            'device': {'name': 'TPS563201'},
        },
        'does_not_apply_when': ['linear-only designs'],
        'inputs': ['rule extracted from two boards'],
        'provenance': {
            'source_project': 'internal',
            'source_case': '',
            'artifacts': [],
            'verified_at': '',
            'stale': False,
        },
        'tool_versions': {},
        'original_problem': 'Reuse a reviewed buck placement rule.',
        'method': 'Compare two boards with the same buck converter.',
        'before_after': {'before': '', 'after': '', 'changes': []},
        'check_method': [],
        'evidence': [],
        'verification_levels': {
            'structural': not_run(),
            'host_readback': not_run(),
            'erc_drc': not_run(),
            'simulation': not_run(),
            'manufacturing': not_run(),
            'physical': not_run(),
        },
        'limits': ['candidate only'],
        'failed_attempts': [],
        'invalidation_conditions': ['different buck family'],
        'source_tier': 'candidate-rule',
        'validated_by': ['photo-led-5v-pcb@1', 'mcu-i2c-s3-pcb@1'],
    })
    return case


def matching_target():
    return {
        'power_w': {'min': 0.1, 'max': 1.0},
        'interfaces': ['power-2pin', 'analog'],
        'topologies': ['comparator', 'led-driver'],
        'footprints': ['DIP-8', '0805', 'LED-5mm'],
        'layers': 2,
        'process': 'jlcpcb-2layer-1.6mm',
        'device': {'name': 'LM393', 'version': 'DIP-8'},
        'version': 1,
    }


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False),
                          encoding='utf-8')


class TemplateAndValidationTests(unittest.TestCase):
    def test_template_has_every_required_field(self):
        case = case_lib.case_template()
        self.assertEqual(case['schema'], schemas.SCHEMA_CASE)
        for field in schemas.CASE_REQUIRED_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, case)
        self.assertEqual(set(case['verification_levels']),
                         set(schemas.VERIFICATION_LEVELS))
        for level, entry in case['verification_levels'].items():
            with self.subTest(level=level):
                self.assertEqual(entry['status'], schemas.STATUS_NOT_RUN)
                self.assertEqual(entry['evidence'], [])
        self.assertIs(case_lib.validate_case(case), case)

    def test_real_cases_validate(self):
        for case in (photo_case(), mcu_case(), candidate_case()):
            with self.subTest(case=case['id']):
                self.assertIs(case_lib.validate_case(case), case)

    def test_pass_without_evidence_is_rejected(self):
        case = photo_case()
        case['verification_levels']['structural'] = {
            'status': schemas.STATUS_PASS, 'evidence': []}
        with self.assertRaises(schemas.ContractError):
            case_lib.validate_case(case)

    def test_physical_pass_needs_a_real_measurement_note(self):
        case = photo_case()
        levels = case['verification_levels']
        levels['physical'] = pass_level(evidence_file(
            'evidence/pcb-final-top.png'))
        with self.assertRaises(schemas.ContractError) as caught:
            case_lib.validate_case(case)
        self.assertIn('measurement', str(caught.exception))

        levels['physical'] = pass_level(
            {'note': 'DMM read 5.01 V at J1 under LED load'})
        case_lib.validate_case(case)

    def test_unknown_verification_level_is_rejected(self):
        case = photo_case()
        case['verification_levels']['vibes'] = not_run()
        with self.assertRaises(schemas.ContractError):
            case_lib.validate_case(case)

    def test_level_entry_needs_an_evidence_list(self):
        case = photo_case()
        case['verification_levels']['simulation'] = {
            'status': schemas.STATUS_NOT_RUN}
        with self.assertRaises(schemas.ContractError):
            case_lib.validate_case(case)

    def test_candidate_rule_needs_validated_by(self):
        case = photo_case()
        case['source_tier'] = 'candidate-rule'
        case.pop('validated_by', None)
        with self.assertRaises(schemas.ContractError):
            case_lib.validate_case(case)

        case['validated_by'] = []
        with self.assertRaises(schemas.ContractError):
            case_lib.validate_case(case)

        case['validated_by'] = ['photo-led-5v-pcb@1']
        case_lib.validate_case(case)

    def test_unknown_source_tier_is_rejected(self):
        case = photo_case()
        case['source_tier'] = 'maybe-reusable'
        with self.assertRaises(schemas.ContractError):
            case_lib.validate_case(case)


class IndexTests(unittest.TestCase):
    def test_create_index_without_input_is_empty(self):
        index = case_lib.create_index()
        self.assertEqual(index, {'schema': schemas.SCHEMA_CASE_INDEX,
                                 'cases': []})

    def test_create_index_entries_have_the_index_fields(self):
        index = case_lib.create_index(cases=[photo_case(), mcu_case()])
        self.assertEqual(index['schema'], schemas.SCHEMA_CASE_INDEX)
        self.assertEqual(len(index['cases']), 2)
        for entry in index['cases']:
            with self.subTest(entry=entry['id']):
                for key in ('id', 'version', 'path', 'source_tier', 'tags',
                            'summary'):
                    self.assertIn(key, entry)
                self.assertEqual(entry['path'], '')
                self.assertIn('interfaces', entry['summary'])
                self.assertTrue(entry['tags'])

    def test_create_index_scans_library_and_uses_relative_paths(self):
        with tempfile.TemporaryDirectory(prefix='case-library-') as tmp:
            tmp = Path(tmp)
            nested = tmp / 'sub'
            nested.mkdir()
            write_json(nested / 'photo.case.json', photo_case())
            write_json(tmp / 'notes.json', {'schema': 'other/v1'})
            index = case_lib.create_index(library=tmp)
        self.assertEqual(len(index['cases']), 1)
        self.assertEqual(index['cases'][0]['path'],
                         'sub/photo.case.json')
        self.assertEqual(index['cases'][0]['id'], 'photo-led-5v-pcb')

    def test_load_index_from_file_roundtrips_and_searches(self):
        with tempfile.TemporaryDirectory(prefix='case-index-') as tmp:
            tmp = Path(tmp)
            write_json(tmp / 'photo.case.json', photo_case())
            index = case_lib.create_index(library=tmp)
            write_json(tmp / 'index.json', index)
            loaded = case_lib.load_index(tmp / 'index.json')
            result = case_lib.search(loaded, {'interfaces': ['analog']})
        self.assertEqual(loaded['base_dir'], str(tmp.resolve()))
        self.assertEqual([match['id'] for match in result['matches']],
                         ['photo-led-5v-pcb'])

    def test_register_refuses_duplicate_and_replaces(self):
        index = case_lib.create_index(cases=[photo_case()])
        with self.assertRaises(schemas.FeedbackError) as caught:
            case_lib.register(index, photo_case())
        self.assertEqual(caught.exception.failure_class,
                         schemas.FAILURE_PRECONDITION_REFUSED)

        changed = copy.deepcopy(photo_case())
        changed['goal'] = 'Updated goal after a second review'
        returned = case_lib.register(index, changed, replace=True)
        self.assertIs(returned, index)
        self.assertEqual(len(index['cases']), 1)
        self.assertEqual(index['cases'][0]['summary']['goal'],
                         'Updated goal after a second review')

    def test_register_accepts_a_new_version_of_the_same_id(self):
        index = case_lib.create_index(cases=[photo_case()])
        second = copy.deepcopy(photo_case())
        second['version'] = 2
        case_lib.register(index, second)
        self.assertEqual(len(index['cases']), 2)

    def test_load_index_rejects_wrong_schema(self):
        with self.assertRaises(schemas.ContractError):
            case_lib.load_index({'schema': 'not-an-index/v1', 'cases': []})


class SearchFilterTests(unittest.TestCase):
    def setUp(self):
        self.photo = photo_case()
        self.mcu = mcu_case()
        self.rule = candidate_case()
        self.index = case_lib.create_index(
            cases=[self.photo, self.mcu, self.rule])

    def ids(self, query):
        result = case_lib.search(self.index, query)
        return [match['id'] for match in result['matches']]

    def test_result_shape(self):
        result = case_lib.search(self.index, {'interfaces': ['i2c']})
        self.assertEqual(result['schema'], schemas.SCHEMA_CASE_QUERY)
        self.assertEqual(result['filters'], {'interfaces': ['i2c']})
        self.assertEqual(result['unknowns'], [])
        match = result['matches'][0]
        for key in ('id', 'score', 'reasons'):
            self.assertIn(key, match)
        rejection = result['rejected'][0]
        self.assertIn('id', rejection)
        self.assertTrue(rejection['reasons'])

    def test_power_range_filter(self):
        self.assertEqual(
            self.ids({'power_min_w': 0.2, 'power_max_w': 0.4}),
            ['photo-led-5v-pcb'])
        self.assertEqual(
            self.ids({'power_min_w': 1.5, 'power_max_w': 2.4}),
            ['candidate-buck-rule', 'mcu-i2c-s3-pcb'])

    def test_interfaces_filter(self):
        self.assertEqual(self.ids({'interfaces': ['i2c']}),
                         ['mcu-i2c-s3-pcb'])

    def test_topologies_filter(self):
        self.assertEqual(self.ids({'topologies': ['ldo']}),
                         ['mcu-i2c-s3-pcb'])

    def test_footprints_filter(self):
        self.assertEqual(self.ids({'footprints': ['DIP-8']}),
                         ['photo-led-5v-pcb'])

    def test_layers_filter(self):
        self.assertEqual(self.ids({'layers': 2}),
                         ['mcu-i2c-s3-pcb', 'photo-led-5v-pcb'])
        self.assertEqual(self.ids({'layers': 4}),
                         ['candidate-buck-rule'])
        self.assertEqual(self.ids({'layers': 6}), [])

    def test_process_filter(self):
        self.assertEqual(
            self.ids({'process': 'JLCPCB-2layer-1.6mm'}),
            ['mcu-i2c-s3-pcb', 'photo-led-5v-pcb'])

    def test_verification_level_min_filter(self):
        self.assertEqual(
            self.ids({'verification_level_min': 'erc_drc'}),
            ['mcu-i2c-s3-pcb', 'photo-led-5v-pcb'])
        self.assertEqual(
            self.ids({'verification_level_min': 'physical'}), [])
        self.assertEqual(
            self.ids({'verification_level_min': 2}),
            ['mcu-i2c-s3-pcb', 'photo-led-5v-pcb'])

    def test_tags_filter(self):
        self.assertEqual(self.ids({'tags': ['led']}),
                         ['photo-led-5v-pcb'])

    def test_source_tier_filter(self):
        self.assertEqual(self.ids({'source_tier': 'candidate-rule'}),
                         ['candidate-buck-rule'])
        self.assertEqual(
            self.ids({'source_tier': 'reusable', 'interfaces': ['i2c']}),
            ['mcu-i2c-s3-pcb'])

    def test_rejected_case_is_listed_with_reasons(self):
        result = case_lib.search(self.index, {'interfaces': ['i2c']})
        rejected = {entry['id']: entry for entry in result['rejected']}
        self.assertIn('photo-led-5v-pcb', rejected)
        self.assertTrue(any(reason.startswith('interfaces')
                            for reason in rejected['photo-led-5v-pcb']
                            ['reasons']))

    def test_unparseable_filter_is_invalid_input(self):
        for query in ({'power_min_w': 'heavy'}, {'layers': 'two'},
                      {'verification_level_min': 'vibes'},
                      {'source_tier': 'sometimes'}):
            with self.subTest(query=query):
                with self.assertRaises(schemas.FeedbackError) as caught:
                    case_lib.search(self.index, query)
                self.assertEqual(caught.exception.failure_class,
                                 schemas.FAILURE_INVALID_INPUT)

    def test_unknown_filter_is_invalid_input(self):
        with self.assertRaises(schemas.FeedbackError) as caught:
            case_lib.search(self.index, {'colour': 'red'})
        self.assertEqual(caught.exception.failure_class,
                         schemas.FAILURE_INVALID_INPUT)

    def test_semantic_token_overlap_ranks_the_matching_case_first(self):
        result = case_lib.search(
            self.index,
            {'text': 'photoresistor LED analog 5V through-hole'})
        ids = [match['id'] for match in result['matches']]
        self.assertEqual(ids[0], 'photo-led-5v-pcb')
        scores = {match['id']: match['score']
                  for match in result['matches']}
        self.assertGreater(scores['photo-led-5v-pcb'],
                           scores['mcu-i2c-s3-pcb'])
        self.assertTrue(any('tokens:' in reason
                            for reason in result['matches'][0]['reasons']))

    def test_scores_are_deterministic(self):
        query = {'text': 'LED board', 'tags': ['analog']}
        first = case_lib.search(self.index, query)
        second = case_lib.search(self.index, query)
        self.assertEqual(first['matches'], second['matches'])

    def test_library_coverage_counts_cases_projects_and_scenarios(self):
        result = case_lib.search(self.index, {})
        library = result['library']
        self.assertEqual(library['cases'], 3)
        self.assertEqual(library['source_projects'], 3)
        self.assertEqual(library['scenarios'], 3)
        self.assertEqual(len(library['per_project']), 3)
        self.assertIn('not independent', library['note'])

    def test_same_project_cases_are_three_scenarios_not_three_projects(self):
        cases = []
        for scenario in ('placement', 'routing', 'readback'):
            case = copy.deepcopy(self.photo)
            case['id'] = 'photo-led-%s' % scenario
            case['provenance']['source_case'] = scenario
            cases.append(case)
        index = case_lib.create_index(cases=cases)
        library = case_lib.search(index, {})['library']
        self.assertEqual(library['cases'], 3)
        self.assertEqual(library['source_projects'], 1)
        self.assertEqual(library['scenarios'], 3)
        self.assertEqual(len(library['per_project']), 1)
        group = library['per_project'][0]
        self.assertEqual(group['source_project'], 'photo-led-pcb-20261026')
        self.assertEqual(sorted(item['scenario'] for item in group['cases']),
                         ['placement', 'readback', 'routing'])

    def test_embedded_case_provenance_is_read_from_the_index(self):
        entry = {'id': 'embedded-1', 'version': 1, 'source_tier': 'reusable',
                 'tags': [], 'case': copy.deepcopy(self.mcu)}
        index = {'schema': schemas.SCHEMA_CASE_INDEX, 'cases': [entry]}
        library = case_lib.search(index, {})['library']
        self.assertEqual(library['source_projects'], 1)
        self.assertEqual(library['per_project'][0]['source_project'],
                         'mcu-i2c-s3-20261026')


class ReuseCheckTests(unittest.TestCase):
    def setUp(self):
        self.case = photo_case()

    def test_matching_target_can_inherit_current_evidence(self):
        result = case_lib.reuse_check(self.case, matching_target())
        self.assertTrue(result['applicable'])
        self.assertEqual(result['differences'], [])
        self.assertEqual(result['required_rechecks'], [])
        self.assertTrue(result['can_inherit_verification'])

    def test_version_change_forces_recheck_and_no_inheritance(self):
        target = matching_target()
        target['version'] = 2
        result = case_lib.reuse_check(self.case, target)
        self.assertIn('version', result['required_rechecks'])
        self.assertFalse(result['can_inherit_verification'])
        self.assertFalse(result['applicable'])
        self.assertEqual([entry['dimension']
                          for entry in result['differences']], ['version'])

    def test_device_version_change_forces_version_recheck(self):
        target = matching_target()
        target['device'] = {'name': 'LM393', 'version': 'DIP-8-r2'}
        result = case_lib.reuse_check(self.case, target)
        self.assertIn('version', result['required_rechecks'])
        self.assertFalse(result['can_inherit_verification'])

    def test_footprint_change_forces_recheck(self):
        target = matching_target()
        target['footprints'] = ['DIP-8', '0805', 'LED-3mm']
        result = case_lib.reuse_check(self.case, target)
        self.assertIn('footprint', result['required_rechecks'])
        self.assertFalse(result['can_inherit_verification'])

    def test_layer_change_forces_recheck(self):
        target = matching_target()
        target['layers'] = 4
        result = case_lib.reuse_check(self.case, target)
        self.assertIn('layers', result['required_rechecks'])
        self.assertFalse(result['can_inherit_verification'])

    def test_process_and_device_changes_force_rechecks(self):
        target = matching_target()
        target['process'] = 'jlcpcb-4layer-1.6mm'
        target['device'] = {'name': 'LM358', 'version': 'DIP-8'}
        result = case_lib.reuse_check(self.case, target)
        self.assertIn('process', result['required_rechecks'])
        self.assertIn('device', result['required_rechecks'])
        self.assertFalse(result['can_inherit_verification'])

    def test_interface_change_makes_the_case_not_applicable(self):
        target = matching_target()
        target['interfaces'] = ['power-2pin', 'analog', 'uart']
        result = case_lib.reuse_check(self.case, target)
        self.assertFalse(result['applicable'])
        self.assertIn('interfaces', result['required_rechecks'])
        self.assertFalse(result['can_inherit_verification'])

    def test_power_outside_the_case_range_is_not_applicable(self):
        target = matching_target()
        target['power_w'] = {'min': 2.0, 'max': 3.0}
        result = case_lib.reuse_check(self.case, target)
        self.assertFalse(result['applicable'])
        self.assertIn('power', result['required_rechecks'])

    def test_missing_target_dimensions_block_inheritance(self):
        result = case_lib.reuse_check(self.case, {'layers': 2})
        self.assertTrue(result['applicable'])
        self.assertIn('footprint', result['required_rechecks'])
        self.assertIn('version', result['required_rechecks'])
        self.assertFalse(result['can_inherit_verification'])

    def test_stale_case_evidence_is_never_inherited(self):
        stale = copy.deepcopy(self.case)
        stale['provenance']['stale'] = True
        result = case_lib.reuse_check(stale, matching_target())
        self.assertTrue(result['applicable'])
        self.assertEqual(result['required_rechecks'], [])
        self.assertFalse(result['can_inherit_verification'])

    def test_case_without_any_pass_cannot_inherit(self):
        case = copy.deepcopy(self.case)
        case['verification_levels'] = {
            level: not_run() for level in schemas.VERIFICATION_LEVELS}
        result = case_lib.reuse_check(case, matching_target())
        self.assertFalse(result['can_inherit_verification'])


if __name__ == '__main__':
    unittest.main()
