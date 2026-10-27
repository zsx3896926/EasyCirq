"""Tests for the scoped modification contract (work package D).

Every write path uses a fake runner.  No test resolves a real ``easyeda``
from PATH and no test touches the network.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from feedback import schemas as S
from feedback import scope as D

BASE = 'base-hash-0001'


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def make_board(hash_value=BASE, **overrides):
    board = {
        'document_uuid': 'pcb-doc',
        'capture': {'projectUuid': 'proj', 'projectName': 'P',
                    'documentUuid': 'pcb-doc', 'documentType': 'pcb',
                    'windowId': 'win-1'},
        'semanticSha256': hash_value,
        'components': [
            {
                'primitiveId': 'pid-D1', 'uniqueId': 'uid-D1',
                'designator': 'D1', 'name': 'LED', 'device': 'LED-0603',
                'layer': 1, 'x': 100.0, 'y': 100.0, 'rotation': 0.0,
                'locked': False,
                'bbox': {'minX': 90, 'minY': 90, 'maxX': 110, 'maxY': 110},
                'pads': [
                    {'padNumber': '1', 'net': 'LED_A', 'x': 95, 'y': 100},
                    {'padNumber': '2', 'net': 'GND', 'x': 105, 'y': 100},
                ],
            },
            {
                'primitiveId': 'pid-D2', 'uniqueId': 'uid-D2',
                'designator': 'D2', 'name': 'LED', 'device': 'LED-0603',
                'layer': 1, 'x': 300.0, 'y': 300.0, 'rotation': 0.0,
                'locked': True,
                'bbox': {'minX': 290, 'minY': 290, 'maxX': 310, 'maxY': 310},
                'pads': [{'padNumber': '1', 'net': 'PWR', 'x': 295,
                          'y': 300}],
            },
        ],
        'outline': {
            'points': [[0, 0], [500, 0], [500, 400], [0, 400]],
            'bbox': {'minX': 0, 'minY': 0, 'maxX': 500, 'maxY': 400},
            'format': 'polygon',
        },
        'copper': {
            'lines': [{'primitiveId': 'tid-1', 'net': 'GND', 'layer': 1,
                       'lineWidth': 10, 'startX': 0, 'startY': 0,
                       'endX': 10, 'endY': 0}],
            'vias': [], 'pours': [], 'fills': [], 'regions': [],
            'poured': [], 'arcs': [], 'arcsAvailable': True,
            'availability': {'routing': 'available', 'vias': 'available',
                             'pours': 'available', 'poured': 'available',
                             'regions': 'available', 'fills': 'available'},
        },
        'copperLayers': 2,
        'rules': {'clearanceMil': 6, 'trackWidthMil': 10},
        'routedLines': ['GND'],
        'holes': [],
        'keepouts': [],
        'availability': {'components': 'available', 'copper': 'available',
                         'outline': 'available', 'rules': 'available'},
    }
    board.update(copy.deepcopy(overrides))
    return board


def make_schematic(**overrides):
    schematic = {
        'document_uuid': 'sch-doc',
        'components': [
            {
                'primitiveId': 'pid-U1', 'uniqueId': 'uid-U1',
                'designator': 'U1', 'device': 'DIP-8', 'name': 'U1',
                'footprint': 'DIP-8', 'supplierId': 'C5213',
                'x': 100.0, 'y': 100.0, 'rotation': 0.0,
                'pins': [{'number': '1', 'net': '+5V'},
                         {'number': '2', 'net': 'GND'}],
            },
        ],
        'nets': [
            {'net': '+5V', 'pins': ['U1.1']},
            {'net': 'GND', 'pins': ['U1.2']},
        ],
        'texts': [
            {'primitiveId': 'txt-1', 'content': 'hello', 'x': 0.0, 'y': 0.0,
             'rotation': 0.0},
        ],
    }
    schematic.update(copy.deepcopy(overrides))
    return schematic


def make_observation(board=None, schematic=None, hash_value=BASE):
    board = board if board is not None else make_board(hash_value)
    schematic = schematic if schematic is not None else make_schematic()
    return {
        'schema': S.SCHEMA_OBSERVATION,
        'generated_at': '2026-10-27T00:00:00Z',
        'tool_version': '1.0.0',
        'host': {'window_id': 'win-1'},
        'adapter': {'name': 'fake', 'version': '1'},
        'project': {'uuid': 'proj', 'name': 'P'},
        'documents': [
            {'uuid': 'pcb-doc', 'type': 'pcb', 'name': 'PCB1'},
            {'uuid': 'sch-doc', 'type': 'schematic', 'name': 'SCH1'},
        ],
        'units': {'schematic_coordinate': '0.01inch',
                  'schematic_y_axis': 'up', 'pcb_coordinate': 'mil',
                  'pcb_y_axis': 'up'},
        'schematic': schematic,
        'pcb': board,
        'revision': {'semantic_sha256': hash_value,
                     'per_document': {'pcb-doc': hash_value,
                                      'sch-doc': hash_value},
                     'captured_at': '2026-10-27T00:00:00Z'},
        'evidence': [],
        'degradations': [],
        'unknown': [],
    }


def make_contract(observation=None, scope=None, actions=None, invariants=None,
                  preview_only=False):
    observation = observation if observation is not None else make_observation()
    return D.build_contract(
        contract_id='contract-1', goal='scoped change',
        target={'project_uuid': 'proj',
                'documents': [{'uuid': 'pcb-doc', 'type': 'pcb',
                               'name': 'PCB1'},
                              {'uuid': 'sch-doc', 'type': 'schematic',
                               'name': 'SCH1'}]},
        observation=observation,
        scope=scope or {'writable': {'objects': ['D1'],
                                     'nets': ['LED_A', 'GND'],
                                     'regions': []}},
        allowed_actions=actions or ['move_component', 'track', 'via', 'pour',
                                    'save', 'reload'],
        invariants=invariants,
        preview_only=preview_only)


def make_raw_dump(observation=None):
    """A complete ``pcb dump --include-copper`` shaped payload.

    The observation board is only a convenient source of geometry here; the
    dump carries the raw provenance fields (capture, availability, timestamp,
    routed-line count and arcs) that a normalized observation cannot supply.
    """
    observation = observation if observation is not None else make_observation()
    board = (observation or {}).get('pcb')
    if not isinstance(board, dict):
        return None
    dump = copy.deepcopy(board)
    project = (observation.get('project') or {})
    host = (observation.get('host') or {})
    capture = dump.setdefault('capture', {})
    capture.update({
        'projectUuid': project.get('uuid'),
        'projectName': project.get('name'),
        'documentUuid': board.get('document_uuid'),
        'documentType': 'pcb',
        'windowId': host.get('window_id'),
    })
    dump['project'] = project.get('uuid')
    dump['capturedAt'] = observation.get('generated_at') or \
        '2026-10-27T00:00:00Z'
    dump['componentsAvailability'] = 'available'
    routed = dump.get('routedLines')
    if isinstance(routed, list):
        dump['routedLines'] = len(routed)
    elif isinstance(routed, bool) or not isinstance(routed, int):
        dump['routedLines'] = 0
    copper = dump.setdefault('copper', {})
    copper.setdefault('arcs', [])
    copper['arcsAvailable'] = True
    copper['availability'] = {
        'routing': 'available', 'vias': 'available', 'pours': 'available',
        'poured': 'available', 'regions': 'available', 'fills': 'available'}
    dump['availability'] = {
        'components': 'available', 'copper': 'available',
        'outline': 'available', 'routedLines': 'available',
        'rules': 'available', 'layers': 'available', 'silk': 'available'}
    return dump


def raw_before_dump(observation=None):
    """The raw dump a PCB plan must carry."""
    return make_raw_dump(observation)


def place_plan(designator='D1', x=120.0, y=100.0, *, base=BASE,
               observation=None, before_dump=None, **extra):
    plan = {
        'schema': D.PLAYBOOK_SCHEMA,
        'base': {'semantic_sha256': base},
        'ops': [{'op': 'place', 'designator': designator,
                 'to': {'x': x, 'y': y, 'rotation': 0.0}}],
        'before_dump': copy.deepcopy(
            before_dump if before_dump is not None
            else raw_before_dump(observation)),
    }
    if observation is not None:
        plan['observation'] = observation
    plan.update(extra)
    return plan


def track_plan(points, *, net='GND', base=BASE, observation=None,
               before_dump=None):
    plan = {
        'schema': D.PLAYBOOK_SCHEMA,
        'base': {'semantic_sha256': base},
        'ops': [{'op': 'track', 'net': net, 'layer': 1, 'width_mil': 10,
                 'points': [list(point) for point in points]}],
        'before_dump': copy.deepcopy(
            before_dump if before_dump is not None
            else raw_before_dump(observation)),
    }
    if observation is not None:
        plan['observation'] = observation
    return plan


def record(exit_code=0, payload=None, error=None):
    return {'argv': [], 'exit': exit_code, 'ok': exit_code == 0,
            'error': error, 'stdout': '', 'stderr': '',
            'payload': payload, 'started_at': 'a', 'ended_at': 'b'}


class RecordingRunner:
    """A runner that must never be called."""

    def __init__(self):
        self.calls = []

    def __call__(self, args, *, easyeda=None, timeout=120, cwd=None, env=None):
        self.calls.append(list(args))
        raise AssertionError('runner must not be called')


class PcbFakeRunner:
    """Emulate one ``easyeda apply`` for the pcb_apply_plan delegation path."""

    def __init__(self, after_board, *, statuses=None, write_dump=True):
        self.after_board = after_board
        self.statuses = statuses or {}
        self.write_dump = write_dump
        self.calls = []

    def __call__(self, args, *, easyeda=None, timeout=120, cwd=None, env=None):
        args = [str(item) for item in args]
        self.calls.append({'args': args, 'easyeda': easyeda,
                           'timeout': timeout})
        playbook_path = args[1]
        with open(playbook_path, encoding='utf-8') as handle:
            playbook = json.load(handle)
        journal_path = args[args.index('--journal') + 1]
        sha = hashlib.sha256(Path(playbook_path).read_bytes()).hexdigest()
        lines = [{'playbookSha256': sha,
                  'name': playbook['meta']['name'],
                  'project': playbook['meta']['project'],
                  'startedAt': '2026-01-01T00:00:00Z'}]
        failed = False
        for index, step in enumerate(playbook['steps'], 1):
            status = self.statuses.get(step['id'], 'ok')
            lines.append({'idx': index, 'id': step['id'], 'status': status,
                          'ms': 1})
            if not str(status).startswith('ok'):
                failed = True
                break
        with open(journal_path, 'a', encoding='utf-8', newline='\n') as handle:
            handle.write('\n'.join(json.dumps(item) for item in lines) + '\n')
        if self.write_dump and not failed:
            dump_step = next(step for step in playbook['steps']
                             if step.get('id') == 'dump')
            out_path = dump_step['flags']['out']
            with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
                json.dump(self.after_board, handle)
        return record(0)


class SchFakeRunner:
    """Return typed schematic responses and record every call."""

    def __init__(self, *, context=None, texts=None, components=None,
                 verify=True, saved=True, omit_texts=False):
        self.context = context or {'projectUuid': 'proj',
                                   'documentUuid': 'sch-doc'}
        self.texts = texts if texts is not None else [
            {'primitiveId': 'txt-1', 'content': 'hello', 'x': 10.0,
             'y': 20.0, 'rotation': 0.0}]
        self.components = components
        self.verify = verify
        self.saved = saved
        self.omit_texts = omit_texts
        self.calls = []

    def __call__(self, args, *, easyeda=None, timeout=120, cwd=None, env=None):
        args = [str(item) for item in args]
        self.calls.append({'args': args, 'easyeda': easyeda,
                           'timeout': timeout})
        action = args[1]
        if action == 'schematic.text.move':
            payload = {'ok': True, 'context': self.context,
                       'result': {'verified': self.verify, 'moved': [
                           {'primitiveId': 'txt-1', 'x': 10, 'y': 20}]}}
        elif action == 'schematic.component.modify':
            payload = {'ok': True, 'context': self.context,
                       'result': {'verified': self.verify,
                                  'component': {}}}
        elif action == 'schematic.text.list':
            payload = {'ok': True, 'context': self.context,
                       'result': {} if self.omit_texts else
                       {'texts': self.texts}}
        elif action == 'schematic.components.list':
            payload = {'ok': True, 'context': self.context,
                       'result': {'components': self.components or []}}
        elif action == 'schematic.save':
            payload = {'ok': True, 'context': self.context,
                       'result': {'saved': self.saved}}
        else:
            payload = {'ok': True, 'context': self.context, 'result': {}}
        return record(0, payload)


# ---------------------------------------------------------------------------
# contract construction
# ---------------------------------------------------------------------------

class ContractTests(unittest.TestCase):
    def test_contract_has_schema_baseline_scope_and_invariants(self):
        observation = make_observation()
        contract = make_contract(observation)
        self.assertEqual(contract['schema'], S.SCHEMA_MODIFICATION)
        self.assertEqual(contract['baseline']['semantic_sha256'], BASE)
        self.assertEqual(contract['target']['project_uuid'], 'proj')
        self.assertIn('D1', contract['scope']['writable']['objects'])
        kinds = [item['kind'] for item in contract['invariants']]
        self.assertIn(S.INVARIANT_PCB_PAD_NET, kinds)
        self.assertIn(S.INVARIANT_SCH_CONNECTIVITY, kinds)
        self.assertTrue(contract['preview_only'] is False)

    def test_scope_shorthand_and_tolerance_are_normalised(self):
        contract = make_contract(
            scope={'objects': ['D1', 'pid-D1'], 'nets': 'GND',
                   'regions': [[0, 0, 200, 200]],
                   'tolerance': {'position': 0.5, 'angle': 0.1}})
        writable = contract['scope']['writable']
        self.assertEqual(writable['objects'], ['D1', 'pid-D1'])
        self.assertEqual(writable['nets'], ['GND'])
        self.assertEqual(writable['regions'], [[0.0, 0.0, 200.0, 200.0]])
        self.assertEqual(contract['scope']['tolerance']['position'], 0.5)
        self.assertEqual(contract['scope']['tolerance']['angle'], 0.1)

    def test_unknown_baseline_contract_is_valid_data_but_plans_refuse(self):
        contract = D.build_contract(
            contract_id='c', goal='g',
            target={'project_uuid': 'proj',
                    'documents': [{'uuid': 'pcb-doc', 'type': 'pcb'}]},
            observation=None, scope={'objects': ['D1']},
            allowed_actions=['move_component', 'save', 'reload'],
            preview_only=False)
        self.assertIn('unknown_reason', contract['baseline'])
        result = D.validate_plan(contract, place_plan(observation=None))
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_class'],
                         S.FAILURE_PRECONDITION_REFUSED)
        self.assertIn('unknown_baseline',
                      [item['reason'] for item in result['refusals']])

    def test_rejects_empty_scope_unknown_action_and_bad_id(self):
        observation = make_observation()
        for kwargs in (
            {'scope': {'writable': {}}, 'actions': ['move_component']},
            {'scope': {'objects': ['D1']}, 'actions': ['explode']},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(S.ContractError):
                    make_contract(observation, **kwargs)
        with self.assertRaises(S.ContractError):
            D.build_contract(contract_id='', goal='g', target=None,
                             observation=observation, scope={'objects': ['D1']},
                             allowed_actions=['move_component'])

    def test_invariants_cannot_be_derived_without_document_types(self):
        with self.assertRaises(S.ContractError):
            D.build_contract(
                contract_id='c', goal='g',
                target={'project_uuid': 'proj',
                        'documents': [{'uuid': 'x', 'type': 'unknown'}]},
                observation=None, scope={'objects': ['D1']},
                allowed_actions=['move_component'])
        contract = D.build_contract(
            contract_id='c', goal='g',
            target={'project_uuid': 'proj',
                    'documents': [{'uuid': 'x', 'type': 'unknown'}]},
            observation=None, scope={'objects': ['D1']},
            allowed_actions=['move_component'],
            invariants=['pcb_unrelated'])
        self.assertEqual(contract['invariants'][0]['kind'],
                         'pcb_unrelated')

    def test_explicit_invariant_params_are_kept(self):
        contract = make_contract(invariants=[
            {'id': 'drc-0', 'kind': 'drc', 'params': {'max_errors': 0}}])
        self.assertEqual(contract['invariants'][0]['id'], 'drc-0')
        self.assertEqual(contract['invariants'][0]['params'],
                         {'max_errors': 0})


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observation = make_observation()
        cls.contract = make_contract(cls.observation)

    def test_valid_plan_compiles_pcb_steps(self):
        result = D.validate_plan(self.contract,
                                 place_plan(observation=self.observation))
        self.assertTrue(result['ok'], result['refusals'])
        self.assertEqual(result['plan_kind'], 'pcb')
        self.assertEqual([step['id'] for step in result['steps']],
                         ['place-D1', 'save', 'reload', 'dump'])
        self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(
            result['actions'][0]['operation_key'],
            D.operation_key({'op': 'place', 'designator': 'D1',
                             'to': {'x': 120, 'y': 100, 'rotation': 0}}))

    def test_out_of_scope_refused_before_any_call(self):
        runner = RecordingRunner()
        plan = place_plan('D2', 320, 300, observation=self.observation)
        result = D.apply_scoped(self.contract, plan, runner=runner, write=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(runner.calls, [])
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_OUT_OF_SCOPE)

    def test_locked_object_is_refused(self):
        contract = make_contract(scope={'objects': ['D2']},
                                 actions=['move_component', 'save', 'reload'])
        result = D.validate_plan(
            contract, place_plan('D2', 320, 300,
                                 observation=self.observation))
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_class'],
                         S.FAILURE_PRECONDITION_REFUSED)
        self.assertIn('locked_object',
                      [item['reason'] for item in result['refusals']])

    def test_stale_plan_baseline_is_refused(self):
        result = D.validate_plan(
            self.contract,
            place_plan(observation=self.observation, base='another-base'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_class'], S.FAILURE_STALE_BASELINE)

    def test_stale_fresh_observation_is_refused(self):
        stale = make_observation(hash_value='newer-base')
        stale['pcb']['semanticSha256'] = 'newer-base'
        result = D.apply_scoped(
            self.contract,
            place_plan(observation=stale), runner=RecordingRunner(),
            write=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_STALE_BASELINE)

    def test_missing_baseline_is_refused(self):
        plan = place_plan(observation=None)
        plan.pop('base')
        result = D.validate_plan(self.contract, plan)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_class'],
                         S.FAILURE_PRECONDITION_REFUSED)
        self.assertIn('missing_baseline',
                      [item['reason'] for item in result['refusals']])

    def test_action_not_allowed_is_refused(self):
        contract = make_contract(actions=['save', 'reload'])
        result = D.validate_plan(contract,
                                 place_plan(observation=self.observation))
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_class'], S.FAILURE_OUT_OF_SCOPE)
        self.assertIn('action_not_allowed',
                      [item['reason'] for item in result['refusals']])

    def test_document_identity_change_is_refused(self):
        contract = make_contract(
            scope={'objects': ['U1']},
            actions=['move_component', 'save'])
        plan = {
            'base': {'semantic_sha256': BASE},
            'document': {'uuid': 'sch-doc'},
            'ops': [{'op': 'move_component', 'primitive_id': 'pid-U1',
                     'patch': {'designator': 'U2'}}],
            'observation': self.observation,
            'save': True,
        }
        result = D.validate_plan(contract, plan)
        self.assertFalse(result['ok'])
        self.assertIn('identity_change',
                      [item['reason'] for item in result['refusals']])

    def test_duplicate_operations_are_refused(self):
        plan = {
            'base': {'semantic_sha256': BASE},
            'ops': [
                {'op': 'track', 'net': 'GND', 'layer': 1, 'width_mil': 10,
                 'points': [[0, 0], [10, 0]]},
                {'op': 'track', 'net': 'GND', 'layer': 1, 'width_mil': 10,
                 'points': [[0, 0], [10, 0]]},
            ],
            'observation': self.observation,
            'before_dump': raw_before_dump(self.observation),
        }
        result = D.validate_plan(self.contract, plan)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_class'], S.FAILURE_INVALID_INPUT)
        self.assertIn('duplicate_operation',
                      [item['reason'] for item in result['refusals']])

    def test_plan_document_outside_target_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['document'] = {'uuid': 'other-doc'}
        result = D.validate_plan(self.contract, plan)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_class'], S.FAILURE_TARGET_MISMATCH)

    def test_missing_lock_evidence_is_unknown_not_pass(self):
        observation = make_observation()
        del observation['pcb']['components'][0]['locked']
        contract = make_contract(observation)
        result = D.validate_plan(
            contract, place_plan(observation=observation))
        self.assertTrue(result['ok'], result['refusals'])
        self.assertTrue(any(item['field'].startswith('locked')
                            for item in result['unknown']))


class BeforeDumpGateTests(unittest.TestCase):
    """A PCB write needs a complete raw dump bound to the live board."""

    def setUp(self):
        self.observation = make_observation()
        self.contract = make_contract(self.observation)

    def refuse(self, plan, expected_reason, expected_class, contract=None):
        contract = contract or self.contract
        runner = RecordingRunner()
        result = D.apply_scoped(contract, plan, runner=runner,
                                write=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(runner.calls, [])
        self.assertEqual(result['failure']['failure_class'], expected_class)
        reasons = [item['reason'] for item in
                   (result['failure'].get('detail') or {}).get('refusals', [])]
        self.assertIn(expected_reason, reasons)
        validation = D.validate_plan(contract, plan)
        self.assertIn(expected_reason,
                      [item['reason'] for item in validation['refusals']])
        return result

    def two_pcb_contract(self):
        observation = copy.deepcopy(self.observation)
        observation['documents'] = [
            {'uuid': 'pcb-doc', 'type': 'pcb', 'name': 'PCB1'},
            {'uuid': 'pcb-doc2', 'type': 'pcb', 'name': 'PCB2'},
            {'uuid': 'sch-doc', 'type': 'schematic', 'name': 'SCH1'}]
        return D.build_contract(
            contract_id='contract-1', goal='scoped change',
            target={'project_uuid': 'proj',
                    'documents': copy.deepcopy(observation['documents'])},
            observation=observation,
            scope={'writable': {'objects': ['D1'],
                                'nets': ['LED_A', 'GND'], 'regions': []}},
            allowed_actions=['move_component', 'save', 'reload'],
            preview_only=False)

    def test_write_document_alias_must_resolve_to_the_live_document(self):
        contract = self.two_pcb_contract()
        for alias in ('document', 'doc'):
            with self.subTest(alias=alias):
                plan = place_plan(observation=self.observation)
                plan[alias] = 'pcb-doc2'
                self.refuse(plan, 'before_dump_target_mismatch',
                            S.FAILURE_TARGET_MISMATCH, contract=contract)

    def test_write_document_string_alias_is_accepted(self):
        contract = self.two_pcb_contract()
        plan = place_plan(observation=self.observation)
        plan['doc'] = 'pcb-doc'
        validation = D.validate_plan(contract, plan)
        self.assertTrue(validation['ok'], validation['refusals'])
        after_board = copy.deepcopy(self.observation['pcb'])
        after_board['components'][0]['x'] = 120
        after_board['semanticSha256'] = 'after-base'
        runner = PcbFakeRunner(after_board)
        with tempfile.TemporaryDirectory() as directory:
            result = D.apply_scoped(
                contract, plan, runner=runner, write=True,
                journal_path=os.path.join(directory, 'apply.jsonl'))
        self.assertEqual(result['status'], 'verified', result.get('failure'))
        argv = runner.calls[0]['args']
        self.assertEqual(argv[argv.index('--doc') + 1], 'pcb-doc')

    def test_runtime_window_mismatch_is_refused_before_any_write(self):
        plan = place_plan(observation=self.observation)
        runner = RecordingRunner()
        result = D.apply_scoped(self.contract, plan, runner=runner,
                                write=True, window='win-2')
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(runner.calls, [])
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_TARGET_MISMATCH)
        reasons = [item['reason'] for item in
                   (result['failure'].get('detail') or {}).get('refusals', [])]
        self.assertIn('before_dump_target_mismatch', reasons)

    def test_observation_without_a_window_is_unbound(self):
        observation = make_observation()
        contract = make_contract(observation)
        contract['target'].pop('window_id', None)
        plan_observation = copy.deepcopy(observation)
        plan_observation['host'] = {}
        plan_observation['pcb']['capture'].pop('windowId', None)
        plan = place_plan(observation=plan_observation,
                          before_dump=make_raw_dump(plan_observation))
        self.refuse(plan, 'unbound_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED, contract=contract)

    def test_missing_raw_before_dump_is_refused_before_any_write(self):
        plan = place_plan(observation=self.observation)
        plan.pop('before_dump')
        self.refuse(plan, 'missing_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_missing_copper_capture_is_refused(self):
        plan = place_plan(observation=self.observation)
        del plan['before_dump']['copper']['vias']
        self.refuse(plan, 'incomplete_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_missing_poured_capture_is_refused(self):
        plan = place_plan(observation=self.observation)
        del plan['before_dump']['copper']['poured']
        self.refuse(plan, 'incomplete_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_missing_arcs_capture_is_refused(self):
        plan = place_plan(observation=self.observation)
        del plan['before_dump']['copper']['arcs']
        self.refuse(plan, 'incomplete_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_missing_copper_availability_is_refused(self):
        plan = place_plan(observation=self.observation)
        del plan['before_dump']['copper']['availability']
        self.refuse(plan, 'incomplete_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_missing_raw_provenance_is_refused(self):
        for key in ('capturedAt', 'routedLines', 'componentsAvailability'):
            with self.subTest(key=key):
                plan = place_plan(observation=self.observation)
                plan['before_dump'].pop(key, None)
                self.refuse(plan, 'incomplete_before_dump',
                            S.FAILURE_PRECONDITION_REFUSED)

    def test_normalized_observation_reconstruction_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump'] = D._pcb_dump_from_view(self.observation)
        self.refuse(plan, 'incomplete_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_unavailable_copper_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump']['availability']['copper'] = 'unavailable'
        self.refuse(plan, 'incomplete_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_real_dump_without_a_top_level_project_is_accepted(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump'].pop('project', None)
        validation = D.validate_plan(self.contract, plan)
        self.assertTrue(validation['ok'], validation['refusals'])

    def test_dump_project_object_is_bound_by_uuid(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump']['project'] = {'uuid': 'proj', 'name': 'P'}
        validation = D.validate_plan(self.contract, plan)
        self.assertTrue(validation['ok'], validation['refusals'])
        plan['before_dump']['project'] = {'uuid': 'other-project'}
        self.refuse(plan, 'invalid_before_dump', S.FAILURE_INVALID_INPUT)

    def test_before_dump_for_another_project_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump']['capture']['projectUuid'] = 'other-project'
        self.refuse(plan, 'before_dump_target_mismatch',
                    S.FAILURE_TARGET_MISMATCH)

    def test_before_dump_for_another_document_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump']['capture']['documentUuid'] = 'other-doc'
        self.refuse(plan, 'before_dump_target_mismatch',
                    S.FAILURE_TARGET_MISMATCH)

    def test_stale_before_dump_hash_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump']['semanticSha256'] = 'older-board'
        self.refuse(plan, 'before_dump_stale', S.FAILURE_STALE_BASELINE)

    def test_before_dump_content_mismatch_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump']['components'][0]['x'] = 777.0
        self.refuse(plan, 'before_dump_stale', S.FAILURE_STALE_BASELINE)

    def test_unbound_before_dump_without_capture_is_refused(self):
        plan = place_plan(observation=self.observation)
        plan['before_dump'].pop('capture')
        self.refuse(plan, 'unbound_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)

    def test_before_dump_for_another_window_is_refused(self):
        self.contract['target']['window_id'] = 'win-1'
        plan = place_plan(observation=self.observation)
        plan['before_dump']['capture']['windowId'] = 'win-2'
        self.refuse(plan, 'before_dump_target_mismatch',
                    S.FAILURE_TARGET_MISMATCH)

    def test_before_dump_without_a_window_is_unbound_when_targeted(self):
        self.contract['target']['window_id'] = 'win-1'
        plan = place_plan(observation=self.observation)
        plan['before_dump']['capture'].pop('windowId', None)
        self.refuse(plan, 'unbound_before_dump',
                    S.FAILURE_PRECONDITION_REFUSED)


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

class PreviewTests(unittest.TestCase):
    def test_preview_reports_steps_and_zero_writes(self):
        observation = make_observation()
        contract = make_contract(observation)
        preview = D.preview(contract,
                            place_plan(observation=observation))
        self.assertTrue(preview['ok'], preview['refusals'])
        self.assertEqual(preview['schema'], S.SCHEMA_PREVIEW)
        self.assertEqual(preview['writes_sent'], 0)
        self.assertEqual(preview['steps'][0]['id'], 'place-D1')
        self.assertEqual(preview['step_scope'][0]['decision'], 'in_scope')
        self.assertEqual(preview['step_scope'][0]['basis'], 'object:D1')

    def test_apply_write_false_is_a_preview_and_never_calls(self):
        observation = make_observation()
        contract = make_contract(observation)
        runner = RecordingRunner()
        result = D.apply_scoped(contract, place_plan(observation=observation),
                                runner=runner, write=False)
        self.assertEqual(result['status'], 'preview')
        self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(runner.calls, [])
        self.assertIsNone(result['call_ok'])
        self.assertIsNone(result['write_confirmed'])

    def test_schematic_preview_compiles_typed_action(self):
        observation = make_observation()
        contract = make_contract(observation, scope={'objects': ['txt-1']},
                                 actions=['move_text', 'save'])
        plan = {
            'base': {'semantic_sha256': BASE},
            'document': {'uuid': 'sch-doc'},
            'ops': [{'op': 'move_text', 'primitive_id': 'txt-1',
                     'x': 10, 'y': 20}],
            'save': True,
            'observation': observation,
        }
        preview = D.preview(contract, plan)
        self.assertTrue(preview['ok'], preview['refusals'])
        step = preview['steps'][0]
        self.assertEqual(step['action'], 'schematic.text.move')
        self.assertEqual(step['payload'],
                         {'moves': [{'primitiveId': 'txt-1', 'x': 10.0,
                                     'y': 20.0}]})
        self.assertEqual(preview['writes_sent'], 0)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

class DiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = make_observation()

    def diff(self, board=None, schematic=None, **kwargs):
        after = make_observation(
            board=board if board is not None else copy.deepcopy(
                self.before['pcb']),
            schematic=schematic if schematic is not None else
            copy.deepcopy(self.before['schematic']))
        return D.diff_observations(self.before, after, **kwargs)

    def test_rotation_equivalence(self):
        board = copy.deepcopy(self.before['pcb'])
        board['components'][0]['rotation'] = 360
        self.assertEqual(self.diff(board=board)['status'], 'match')
        board['components'][0]['rotation'] = -90
        before = make_observation(board=board)
        board2 = copy.deepcopy(board)
        board2['components'][0]['rotation'] = 270
        self.assertEqual(D.diff_observations(
            before, make_observation(board=board2))['status'], 'match')
        board3 = copy.deepcopy(board)
        board3['components'][0]['rotation'] = 90
        result = D.diff_observations(before,
                                     make_observation(board=board3))
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(result['pcb']['components']['pose_changed'][0]
                         ['designator'], 'D1')

    def test_outline_tolerance(self):
        board = copy.deepcopy(self.before['pcb'])
        board['outline']['points'][0] = [0.005, 0.0]
        self.assertEqual(self.diff(board=board)['status'], 'match')
        board['outline']['points'][0] = [1.0, 0.0]
        result = self.diff(board=board)
        self.assertEqual(result['status'], 'changed')
        self.assertTrue(result['pcb']['outline']['changed'])

    def test_component_identity_pose_lock_and_pad_net(self):
        board = copy.deepcopy(self.before['pcb'])
        board['components'][0]['device'] = 'OTHER-LED'
        board['components'][1]['locked'] = False
        board['components'][0]['pads'][0]['net'] = 'VCC'
        result = self.diff(board=board)
        components = result['pcb']['components']
        self.assertEqual(components['identity_changed'][0]['designator'],
                         'D1')
        self.assertEqual(components['locked_changed'][0]['designator'],
                         'D2')
        self.assertEqual(components['pad_net_changed'][0]['designator'],
                         'D1')
        self.assertEqual(result['status'], 'changed')

    def test_holes_and_keepouts_geometry(self):
        board = copy.deepcopy(self.before['pcb'])
        board['holes'] = [{'center': [10, 10], 'radius': 3}]
        board['keepouts'] = [{'rect': [20, 20, 30, 30]}]
        result = self.diff(board=board)
        self.assertTrue(result['pcb']['holes']['changed'])
        self.assertTrue(result['pcb']['keepouts']['changed'])

    def scoped_hole_diff(self, before_holes, after_holes, scope_objects):
        before_board = copy.deepcopy(self.before['pcb'])
        before_board['holes'] = copy.deepcopy(before_holes)
        after_board = copy.deepcopy(before_board)
        after_board['holes'] = copy.deepcopy(after_holes)
        return D.diff_observations(
            make_observation(board=before_board),
            make_observation(board=after_board),
            scope={'objects': scope_objects})

    def hole_change(self, result):
        return [item for item in result['changes']
                if item['category'] == 'pcb.holes'][0]

    def test_moved_tht_holes_are_inside_their_component_scope(self):
        before = [
            {'designator': 'D1', 'pad': '1', 'primitive_id': 'hole-D1-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 95, 'y': 100},
            {'designator': 'D2', 'pad': '1', 'primitive_id': 'hole-D2-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 295, 'y': 300},
        ]
        after = copy.deepcopy(before)
        after[0]['y'] = 101
        result = self.scoped_hole_diff(before, after, ['D1'])
        change = self.hole_change(result)
        self.assertTrue(change['in_scope'])
        self.assertEqual(change['scope_basis'], 'hole-owner:D1')
        self.assertEqual(change['designators'], ['D1'])
        self.assertEqual(result['outside_scope'], [])
        contract = make_contract(
            scope={'writable': {'objects': ['D1'], 'nets': [],
                                'regions': []}},
            invariants=[{'id': S.INVARIANT_PCB_UNRELATED,
                         'kind': S.INVARIANT_PCB_UNRELATED, 'params': {}}])
        invariants = D.check_invariants(contract, result)
        self.assertEqual(invariants['results'][0]['status'], 'pass')

    def test_mixed_or_unowned_hole_changes_stay_outside_scope(self):
        before = [
            {'designator': 'D1', 'pad': '1', 'primitive_id': 'hole-D1-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 95, 'y': 100},
            {'designator': 'D2', 'pad': '1', 'primitive_id': 'hole-D2-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 295, 'y': 300},
            {'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 400, 'y': 300},
        ]
        mixed = copy.deepcopy(before)
        mixed[0]['y'] = 101
        mixed[1]['y'] = 301
        result = self.scoped_hole_diff(before, mixed, ['D1'])
        change = self.hole_change(result)
        self.assertFalse(change['in_scope'])
        self.assertEqual(change['designators'], ['D1', 'D2'])
        self.assertEqual(result['status'], 'mismatch')

        unowned = copy.deepcopy(before)
        unowned[2]['y'] = 301
        result = self.scoped_hole_diff(before, unowned, ['D1'])
        change = self.hole_change(result)
        self.assertFalse(change['in_scope'])
        self.assertTrue(change['unattributed'])
        self.assertEqual(result['status'], 'mismatch')

    def test_added_unowned_hole_is_unattributed(self):
        before = [
            {'designator': 'D1', 'pad': '1', 'primitive_id': 'hole-D1-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 95, 'y': 100},
            {'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 400, 'y': 300},
        ]
        after = copy.deepcopy(before)
        after.append({'shape': 'ROUND', 'width': 3, 'height': 3,
                      'x': 450, 'y': 300})
        result = self.scoped_hole_diff(before, after, ['D1'])
        change = self.hole_change(result)
        self.assertFalse(change['in_scope'])
        self.assertTrue(change['unattributed'])

    def test_unchanged_identity_less_hole_does_not_mask_a_scoped_change(self):
        before = [
            {'designator': 'D1', 'pad': '1', 'primitive_id': 'hole-D1-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 95, 'y': 100},
            {'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 400, 'y': 300},
        ]
        after = copy.deepcopy(before)
        after[0]['y'] = 101
        result = self.scoped_hole_diff(before, after, ['D1'])
        change = self.hole_change(result)
        self.assertTrue(change['in_scope'])
        self.assertFalse(change.get('unattributed'))
        self.assertEqual(change['designators'], ['D1'])

    def test_hole_owner_change_touches_both_designators(self):
        before = [
            {'designator': 'D1', 'pad': '1', 'primitive_id': 'hole-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 95, 'y': 100},
        ]
        after = [
            {'designator': 'D2', 'pad': '1', 'primitive_id': 'hole-1',
             'shape': 'ROUND', 'width': 3, 'height': 3, 'x': 295, 'y': 300},
        ]
        result = self.scoped_hole_diff(before, after, ['D1'])
        change = self.hole_change(result)
        self.assertFalse(change['in_scope'])
        self.assertEqual(change['designators'], ['D1', 'D2'])

    def normalized_board(self):
        """The board shape ``observe`` emits for real hosts."""
        board = copy.deepcopy(self.before['pcb'])
        copper = board.pop('copper')
        board['tracks'] = [
            {'primitive_id': item.get('primitiveId'),
             'kind': 'line', 'net': item.get('net'),
             'layer': item.get('layer'), 'width': item.get('lineWidth'),
             'locked': False,
             'start': {'x': item.get('startX'), 'y': item.get('startY')},
             'end': {'x': item.get('endX'), 'y': item.get('endY')}}
            for item in copper['lines']]
        board['vias'] = [
            {'primitive_id': item.get('primitiveId'), 'net': item.get('net'),
             'x': item.get('x'), 'y': item.get('y'),
             'diameter': item.get('diameter'),
             'hole_diameter': item.get('holeDiameter')}
            for item in copper['vias']]
        board['pours'] = [
            {'primitive_id': item.get('primitiveId'), 'net': item.get('net'),
             'layer': item.get('layer'),
             'fill_method': item.get('fillMethod')}
            for item in copper['pours']]
        board['poured'] = copy.deepcopy(copper['poured'])
        board['fills'] = copy.deepcopy(copper['fills'])
        board['regions'] = copy.deepcopy(copper['regions'])
        board['availability'] = {
            'components': 'available', 'copper': 'available',
            'categories': {'routing': 'available', 'vias': 'available',
                           'pours': 'available', 'poured': 'available',
                           'regions': 'available', 'fills': 'available'}}
        return board

    def test_normalized_observation_copper_is_compared_not_unknown(self):
        before_board = self.normalized_board()
        after_board = copy.deepcopy(before_board)
        after_board['tracks'][0]['width'] = 12
        result = D.diff_observations(make_observation(board=before_board),
                                     make_observation(board=after_board))
        self.assertEqual(result['status'], 'changed')
        self.assertTrue(result['pcb']['tracks']['changed'])
        fields = {item['field'] for item in result['unknown']}
        self.assertNotIn('pcb.copper.lines', fields)
        self.assertNotIn('pcb.copper.vias', fields)

        result = D.diff_observations(make_observation(board=before_board),
                                     make_observation(board=before_board))
        self.assertEqual(result['status'], 'match')
        self.assertNotIn('pcb.copper.lines',
                         {item['field'] for item in result['unknown']})

    def normalized_pour_board(self):
        board = self.normalized_board()
        board['pours'] = [{
            'primitive_id': 'pour-1', 'net': 'GND', 'layer': 1,
            'pour_name': 'GND pour', 'priority': 1, 'locked': False,
            'fill_method': 'solid', 'line_width': 8,
            'geometry_sha256': 'geo-a'}]
        return board

    def test_normalized_pour_attributes_and_geometry_are_compared(self):
        before_board = self.normalized_pour_board()
        result = D.diff_observations(make_observation(board=before_board),
                                     make_observation(board=before_board))
        self.assertEqual(result['status'], 'match')
        for field, value in (('priority', 2), ('pour_name', 'renamed'),
                             ('locked', True), ('line_width', 10),
                             ('geometry_sha256', 'geo-b')):
            after_board = copy.deepcopy(before_board)
            after_board['pours'][0][field] = value
            result = D.diff_observations(
                make_observation(board=before_board),
                make_observation(board=after_board))
            self.assertEqual(result['status'], 'changed', field)
            changes = result['pcb']['pours']['changed']
            self.assertTrue(changes, field)
            expected = 'geometry' if field == 'geometry_sha256' else field
            self.assertIn(expected, changes[0]['difference'], field)

    def test_tracks_use_semantic_tuple_and_ignore_id_churn(self):
        board = copy.deepcopy(self.before['pcb'])
        board['copper']['lines'][0]['primitiveId'] = 'tid-2'
        board['copper']['lines'][0]['startX'] = 0.005
        result = self.diff(board=board)
        self.assertEqual(result['status'], 'match')
        self.assertEqual(result['pcb']['tracks']['id_churn'], 1)
        board['copper']['lines'][0]['lineWidth'] = 12
        result = self.diff(board=board)
        self.assertEqual(result['status'], 'changed')
        self.assertTrue(result['pcb']['tracks']['changed'])
        board['copper']['lines'][0]['endX'] = 50
        result = self.diff(board=board)
        self.assertEqual(result['status'], 'changed')
        self.assertTrue(result['pcb']['tracks']['added'])
        self.assertTrue(result['pcb']['tracks']['removed'])

    def test_rules_and_copper_layers_are_compared_by_value(self):
        board = copy.deepcopy(self.before['pcb'])
        board['rules']['clearanceMil'] = 8
        board['copperLayers'] = 4
        result = self.diff(board=board)
        self.assertTrue(result['pcb']['rules']['changed'])
        self.assertTrue(result['pcb']['copper_layers']['changed'])

    def test_raw_copper_availability_routing_key_marks_lines_unknown(self):
        dump = make_raw_dump()
        dump['copper']['availability']['routing'] = 'unavailable'
        self.assertIsNone(D._pcb_copper(dump, 'lines'))
        dump = make_raw_dump()
        dump['copper']['availability'].pop('routing')
        self.assertIsNone(D._pcb_copper(dump, 'lines'))
        self.assertEqual(len(D._pcb_copper(make_raw_dump(), 'lines')), 1)

    def test_normalized_partial_copper_availability_is_unknown(self):
        board = self.normalized_board()
        board['availability']['categories']['routing'] = 'partial'
        result = D.diff_observations(make_observation(board=board),
                                     make_observation(board=board))
        self.assertIn('pcb.copper.lines',
                      {item['field'] for item in result['unknown']})

    def test_routed_state_per_net(self):
        board = copy.deepcopy(self.before['pcb'])
        board['routedLines'] = []
        board['copper']['lines'] = []
        result = self.diff(board=board)
        changes = result['pcb']['routed']['changes']
        self.assertTrue(any(item['net'] == 'GND' and
                            item['before'] == 'routed' and
                            item['after'] == 'unrouted'
                            for item in changes))

    def test_unreadable_category_is_unknown_not_empty(self):
        board = copy.deepcopy(self.before['pcb'])
        del board['copper']
        del board['holes']
        del board['keepouts']
        result = self.diff(board=board)
        self.assertEqual(result['status'], 'unknown')
        fields = {item['field'] for item in result['unknown']}
        self.assertIn('pcb.copper.lines', fields)
        self.assertIn('pcb.holes', fields)
        self.assertEqual(result['changes'], [])

    def test_scope_classifies_inside_and_outside(self):
        board = copy.deepcopy(self.before['pcb'])
        board['components'][0]['x'] = 130
        inside = self.diff(board=board,
                           scope={'objects': ['D1']})
        self.assertEqual(inside['status'], 'changed')
        self.assertTrue(inside['inside_scope'])
        self.assertFalse(inside['outside_scope'])
        board = copy.deepcopy(self.before['pcb'])
        board['components'][1]['x'] = 330
        outside = self.diff(board=board, scope={'objects': ['D1']})
        self.assertEqual(outside['status'], 'mismatch')
        self.assertEqual(outside['outside_scope'][0]['designator'], 'D2')

    def test_net_scope_classifies_copper_change(self):
        board = copy.deepcopy(self.before['pcb'])
        board['copper']['lines'].append(
            {'primitiveId': 'new', 'net': 'LED_A', 'layer': 1,
             'lineWidth': 10, 'startX': 40, 'startY': 40,
             'endX': 50, 'endY': 40})
        result = self.diff(board=board, scope={'nets': ['LED_A']})
        self.assertEqual(result['status'], 'changed')
        self.assertTrue(all(item['in_scope']
                            for item in result['changes']))

    def test_schematic_nets_and_texts(self):
        schematic = copy.deepcopy(self.before['schematic'])
        schematic['components'][0]['pins'][1]['net'] = 'VSS'
        schematic['nets'][1]['net'] = 'VSS'
        schematic['texts'][0]['x'] = 25
        result = self.diff(schematic=schematic)
        self.assertTrue(result['schematic']['nets']['changed'])
        self.assertTrue(result['schematic']['texts']['changed'])
        self.assertEqual(result['status'], 'changed')


# ---------------------------------------------------------------------------
# acceptance
# ---------------------------------------------------------------------------

class AcceptanceTests(unittest.TestCase):
    """Declared targets are met only when fully measured and passing."""

    def contract(self, *acceptance):
        return {'acceptance': list(acceptance)}

    def diff(self, outside=0, inside=2):
        return {'counts': {'total': outside + inside,
                           'inside_scope': inside,
                           'outside_scope': outside},
                'changes': [{}] * (outside + inside)}

    def test_zero_outside_scope_meets_the_declared_target(self):
        result = D.evaluate_acceptance(
            self.contract({'id': 'a1', 'metric': 'diff.outside_scope',
                           'predicate': '== 0'}), self.diff(outside=0))
        self.assertEqual(result['schema'], 'hds-acceptance/v1')
        self.assertEqual(result['status'], 'pass')
        self.assertIs(result['target_met'], True)
        self.assertEqual(result['failed'], [])

    def test_outside_scope_change_fails_the_target(self):
        result = D.evaluate_acceptance(
            self.contract({'id': 'a1', 'metric': 'diff.outside_scope',
                           'predicate': '== 0'}), self.diff(outside=2))
        self.assertEqual(result['status'], 'fail')
        self.assertIs(result['target_met'], False)
        self.assertEqual(result['failed'], ['a1'])

    def test_unmeasured_metric_is_unknown_not_met(self):
        result = D.evaluate_acceptance(
            self.contract({'id': 'a1', 'metric': 'diff.outside_scope',
                           'predicate': '== 0'}), {})
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['target_met'])
        self.assertEqual(result['unknown'], ['a1'])

    def test_unknown_diff_counts_are_not_measured_as_zero(self):
        diff = dict(self.diff(outside=0), status='unknown')
        result = D.evaluate_acceptance(
            self.contract({'id': 'a1', 'metric': 'diff.outside_scope',
                           'predicate': '== 0'}), diff)
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['target_met'])
        self.assertEqual(result['unknown'], ['a1'])
        self.assertEqual(result['failed'], [])

    def test_no_declared_acceptance_is_not_a_pass(self):
        result = D.evaluate_acceptance({}, self.diff())
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['target_met'])

    def test_count_prefix_and_numeric_thresholds(self):
        passing = D.evaluate_acceptance(
            self.contract({'id': 'a1', 'metric': 'diff.changes',
                           'predicate': 'count >= 2'}), self.diff(inside=2))
        self.assertEqual(passing['status'], 'pass')
        failing = D.evaluate_acceptance(
            self.contract({'id': 'a1', 'metric': 'diff.changes',
                           'predicate': '< 2'}), self.diff(inside=2))
        self.assertEqual(failing['status'], 'fail')

    def test_status_metrics_compare_by_equality_only(self):
        contract = self.contract(
            {'id': 'inv', 'metric': 'invariants.status', 'predicate': '== pass'},
            {'id': 'qual', 'metric': 'evaluation.verdict',
             'predicate': '== pass'})
        result = D.evaluate_acceptance(
            contract, self.diff(),
            evaluation={'verdict': 'pass'},
            invariants={'status': 'pass'})
        self.assertEqual(result['status'], 'pass')
        bad = D.evaluate_acceptance(
            contract, self.diff(),
            evaluation={'verdict': 'fail'},
            invariants={'status': 'pass'})
        self.assertEqual(bad['status'], 'fail')
        self.assertEqual(bad['failed'], ['qual'])
        ordered = D.evaluate_acceptance(
            self.contract({'id': 'inv', 'metric': 'invariants.status',
                           'predicate': '>= pass'}),
            self.diff(), invariants={'status': 'pass'})
        self.assertEqual(ordered['status'], 'unknown')

    def test_invariants_fall_back_to_the_diff_payload(self):
        result = D.evaluate_acceptance(
            self.contract({'id': 'inv', 'metric': 'invariants.status',
                           'predicate': '== pass'}),
            dict(self.diff(), invariants={'status': 'pass'}))
        self.assertEqual(result['status'], 'pass')

    def test_unreadable_predicate_is_unknown(self):
        result = D.evaluate_acceptance(
            self.contract({'id': 'a1', 'metric': 'diff.outside_scope',
                           'predicate': 'zero please'}), self.diff())
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['target_met'])


# ---------------------------------------------------------------------------
# invariants
# ---------------------------------------------------------------------------

class InvariantTests(unittest.TestCase):
    ALL_KINDS = list(S.INVARIANT_KINDS)

    def contract_with(self, kinds):
        return make_contract(
            invariants=[{'id': kind, 'kind': kind, 'params': {}}
                        for kind in kinds])

    def clean_diff(self):
        return D.diff_observations(make_observation(), make_observation())

    def test_unknown_is_not_pass_and_drc_unknown_blocks(self):
        contract = self.contract_with(self.ALL_KINDS)
        result = D.check_invariants(contract, self.clean_diff())
        by_kind = {item['kind']: item for item in result['results']}
        self.assertEqual(by_kind['drc']['status'], 'unknown')
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['ok'])
        after = make_observation()
        after['drc'] = {'passed': True, 'errors': 0}
        result = D.check_invariants(contract, self.clean_diff(), after=after)
        self.assertEqual(result['status'], 'pass', result['results'])
        self.assertTrue(result['ok'])

    def test_locked_pad_net_holes_and_outline_fail(self):
        board = copy.deepcopy(make_board())
        board['components'][1]['locked'] = False
        board['components'][0]['pads'][0]['net'] = 'VCC'
        board['holes'] = [{'center': [5, 5], 'radius': 2}]
        board['outline']['points'][0] = [10, 10]
        diff = D.diff_observations(make_observation(),
                                   make_observation(board=board))
        contract = self.contract_with([
            S.INVARIANT_PCB_LOCKED, S.INVARIANT_PCB_PAD_NET,
            S.INVARIANT_HOLES, S.INVARIANT_PCB_OUTLINE])
        result = D.check_invariants(contract, diff)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['counts']['fail'], 4)

    def test_unrelated_change_fails_and_unknown_blocks(self):
        board = copy.deepcopy(make_board())
        board['components'][1]['x'] = 330
        diff = D.diff_observations(make_observation(),
                                   make_observation(board=board),
                                   scope={'objects': ['D1']})
        contract = self.contract_with([S.INVARIANT_PCB_UNRELATED])
        self.assertEqual(D.check_invariants(contract, diff)['status'], 'fail')
        board = copy.deepcopy(make_board())
        del board['copper']
        diff = D.diff_observations(make_observation(),
                                   make_observation(board=board))
        self.assertEqual(D.check_invariants(contract, diff)['status'],
                         'unknown')

    def test_routed_regression_fails(self):
        board = copy.deepcopy(make_board())
        board['routedLines'] = []
        board['copper']['lines'] = []
        diff = D.diff_observations(make_observation(),
                                   make_observation(board=board))
        contract = self.contract_with([S.INVARIANT_PCB_ROUTED])
        result = D.check_invariants(contract, diff)
        self.assertEqual(result['status'], 'fail')
        self.assertIn('GND', result['results'][0]['reasons'][0])

    def test_schematic_connectivity_and_identity(self):
        schematic = copy.deepcopy(make_schematic())
        schematic['components'][0]['pins'][1]['net'] = 'VSS'
        schematic['nets'][1]['net'] = 'VSS'
        diff = D.diff_observations(make_observation(),
                                   make_observation(schematic=schematic))
        contract = self.contract_with([S.INVARIANT_SCH_CONNECTIVITY,
                                       S.INVARIANT_SCH_IDENTITY])
        result = D.check_invariants(contract, diff)
        by_kind = {item['kind']: item for item in result['results']}
        self.assertEqual(by_kind[S.INVARIANT_SCH_CONNECTIVITY]['status'],
                         'fail')
        self.assertEqual(by_kind[S.INVARIANT_SCH_IDENTITY]['status'], 'pass')

    def test_drc_failure_is_not_masked(self):
        diff = self.clean_diff()
        after = make_observation()
        after['drc'] = {'passed': False, 'errors': 3}
        contract = self.contract_with([S.INVARIANT_DRC])
        result = D.check_invariants(contract, diff, after=after)
        self.assertEqual(result['status'], 'fail')
        self.assertFalse(result['ok'])


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------

class BaselineTests(unittest.TestCase):
    def test_current_stale_unknown_and_target_mismatch(self):
        contract = make_contract(make_observation())
        current = D.check_baseline(contract, make_observation())
        self.assertTrue(current['ok'])
        self.assertEqual(current['status'], 'current')
        stale = D.check_baseline(contract, make_observation(
            board=make_board('other'), hash_value='other'))
        self.assertFalse(stale['ok'])
        self.assertEqual(stale['status'], 'stale')
        self.assertEqual(stale['failure_class'], S.FAILURE_STALE_BASELINE)
        unknown = make_observation()
        unknown['revision']['semantic_sha256'] = None
        unknown['pcb']['semanticSha256'] = None
        result = D.check_baseline(contract, unknown)
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['ok'])
        wrong_project = make_observation()
        wrong_project['project']['uuid'] = 'other'
        result = D.check_baseline(contract, wrong_project)
        self.assertEqual(result['status'], 'target_mismatch')
        self.assertEqual(result['failure_class'], S.FAILURE_TARGET_MISMATCH)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

class ApplyTests(unittest.TestCase):
    def test_pcb_apply_records_five_separate_facts(self):
        observation = make_observation()
        contract = make_contract(observation)
        after_board = copy.deepcopy(observation['pcb'])
        after_board['components'][0]['x'] = 120
        after_board['semanticSha256'] = 'after-base'
        runner = PcbFakeRunner(after_board)
        with tempfile.TemporaryDirectory() as directory:
            journal_path = os.path.join(directory, 'apply.jsonl')
            result = D.apply_scoped(
                contract, place_plan(observation=observation),
                runner=runner, write=True, journal_path=journal_path)
            self.assertEqual(result['status'], 'verified', result.get(
                'failure'))
            self.assertTrue(result['ok'])
            self.assertTrue(result['call_ok'])
            self.assertTrue(result['write_confirmed'])
            self.assertTrue(result['save_confirmed'])
            self.assertTrue(result['reopen_confirmed'])
            self.assertIsNone(result['quality_passed'])
            self.assertEqual(result['writes_sent'], 1)
            self.assertEqual(len(runner.calls), 1)
            self.assertTrue(os.path.isfile(journal_path))
            recovery = D.recover(contract, journal_path,
                                 current_observation=make_observation(
                                     board=after_board,
                                     hash_value='after-base'),
                                 plan=place_plan(observation=observation))
            self.assertEqual(recovery['status'], 'complete')
            self.assertEqual(recovery['pending'], [])
            self.assertTrue(recovery['safe_to_retry'])

    def test_pcb_apply_normalizes_the_raw_after_dump_before_diffing(self):
        from feedback import observe as observe_module
        observation = make_observation()
        observation['pcb'] = observe_module.normalize_pcb_dump(make_board())
        observation['pcb']['semanticSha256'] = BASE
        observation['pcb']['semantic_sha256'] = BASE
        contract = make_contract(observation)
        after_raw = make_board()
        after_raw['components'][0]['x'] = 120
        after_raw['semanticSha256'] = 'after-base'
        runner = PcbFakeRunner(after_raw)
        with tempfile.TemporaryDirectory() as directory:
            result = D.apply_scoped(
                contract,
                place_plan(observation=observation,
                           before_dump=make_raw_dump()),
                runner=runner, write=True,
                journal_path=os.path.join(directory, 'apply.jsonl'))
        self.assertEqual(result['status'], 'verified', result.get('failure'))
        self.assertEqual(result['diff']['counts']['outside_scope'], 0)
        self.assertEqual(result['diff']['pcb']['tracks']['status'], 'available')
        self.assertEqual(result['diff']['pcb']['tracks']['added'], [])
        self.assertEqual(result['diff']['pcb']['tracks']['removed'], [])
        self.assertEqual(len(result['diff']['changes']), 1)
        self.assertEqual(result['diff']['changes'][0]['category'],
                         'pcb.component')
        self.assertFalse(result['notes'])

    def test_pcb_apply_marks_an_unreadable_after_dump_unknown(self):
        from feedback import observe as observe_module
        observation = make_observation()
        contract = make_contract(observation)
        after_board = copy.deepcopy(observation['pcb'])
        after_board['components'][0]['x'] = 120
        after_board['semanticSha256'] = 'after-base'
        runner = PcbFakeRunner(after_board)
        original = observe_module.normalize_pcb_dump

        def unavailable(payload):
            raise ValueError('after dump is not a board')

        observe_module.normalize_pcb_dump = unavailable
        try:
            with tempfile.TemporaryDirectory() as directory:
                result = D.apply_scoped(
                    contract, place_plan(observation=observation),
                    runner=runner, write=True,
                    journal_path=os.path.join(directory, 'apply.jsonl'))
        finally:
            observe_module.normalize_pcb_dump = original
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['ok'])
        self.assertIsNone(result['diff'])
        self.assertIsNone(result['invariants'])
        self.assertIsNone(result['write_confirmed'])
        self.assertEqual(result['writes_sent'], 1)
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_VERIFICATION_FAILED)
        self.assertEqual(result['failure']['reason'], 'after_dump_unreadable')
        self.assertTrue(result['notes'])

    def test_pcb_apply_missing_after_hash_is_unknown_not_verified(self):
        observation = make_observation()
        contract = make_contract(observation)
        after_board = copy.deepcopy(observation['pcb'])
        after_board['components'][0]['x'] = 120
        after_board.pop('semanticSha256', None)
        runner = PcbFakeRunner(after_board)
        with tempfile.TemporaryDirectory() as directory:
            result = D.apply_scoped(
                contract, place_plan(observation=observation),
                runner=runner, write=True,
                journal_path=os.path.join(directory, 'apply.jsonl'))
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['ok'])
        self.assertIsNone(result['write_confirmed'])
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_VERIFICATION_FAILED)
        self.assertEqual(result['failure']['reason'], 'after_hash_missing')

    def test_pcb_apply_unbound_after_dump_is_a_target_mismatch(self):
        cases = (('capture', None), ('projectUuid', 'other-project'),
                 ('documentUuid', 'other-doc'), ('windowId', 'win-2'),
                 ('documentUuid', None), ('windowId', None))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                observation = make_observation()
                contract = make_contract(observation)
                after_board = copy.deepcopy(observation['pcb'])
                after_board['components'][0]['x'] = 120
                after_board['semanticSha256'] = 'after-base'
                if field == 'capture':
                    after_board.pop('capture', None)
                elif value is None:
                    after_board['capture'].pop(field, None)
                else:
                    after_board['capture'][field] = value
                runner = PcbFakeRunner(after_board)
                with tempfile.TemporaryDirectory() as directory:
                    result = D.apply_scoped(
                        contract, place_plan(observation=observation),
                        runner=runner, write=True,
                        journal_path=os.path.join(directory, 'apply.jsonl'))
                self.assertEqual(result['status'], 'target_mismatch', field)
                self.assertFalse(result['ok'])
                self.assertIs(result['write_confirmed'], False)
                self.assertEqual(result['failure']['failure_class'],
                                 S.FAILURE_TARGET_MISMATCH)

    def test_pcb_apply_pins_window_project_and_document_uuid(self):
        observation = make_observation()
        observation['pcb']['capture']['windowId'] = 'win-1'
        contract = make_contract(observation)
        self.assertEqual(contract['target']['window_id'], 'win-1')
        after_board = copy.deepcopy(observation['pcb'])
        after_board['components'][0]['x'] = 120
        after_board['semanticSha256'] = 'after-base'
        runner = PcbFakeRunner(after_board)
        with tempfile.TemporaryDirectory() as directory:
            result = D.apply_scoped(
                contract, place_plan(observation=observation),
                runner=runner, write=True,
                journal_path=os.path.join(directory, 'apply.jsonl'))
            self.assertEqual(result['status'], 'verified', result.get(
                'failure'))
            argv = runner.calls[0]['args']
            self.assertEqual(argv[argv.index('--window') + 1], 'win-1')
            self.assertEqual(argv[argv.index('--project') + 1], 'proj')
            self.assertEqual(argv[argv.index('--doc') + 1], 'pcb-doc')

    def test_apply_requires_fresh_observation(self):
        observation = make_observation()
        contract = make_contract(observation)
        result = D.apply_scoped(
            contract, place_plan(observation=None), runner=RecordingRunner(),
            write=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_STALE_BASELINE)
        self.assertIn('fresh observation',
                      result['failure']['message'])

    def test_apply_refuses_to_resolve_easyeda_from_path(self):
        observation = make_observation()
        contract = make_contract(observation)
        result = D.apply_scoped(
            contract, place_plan(observation=observation), write=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_HOST_UNAVAILABLE)
        self.assertEqual(result['writes_sent'], 0)

    def test_preview_only_contract_refuses_write(self):
        observation = make_observation()
        contract = make_contract(observation, preview_only=True)
        runner = RecordingRunner()
        result = D.apply_scoped(
            contract, place_plan(observation=observation), runner=runner,
            write=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_PRECONDITION_REFUSED)
        self.assertEqual(runner.calls, [])

    def test_rerun_skips_already_applied_track(self):
        base = make_board()
        board = copy.deepcopy(base)
        board['copper']['lines'].append(
            {'primitiveId': 'new', 'net': 'GND', 'layer': 1,
             'lineWidth': 10, 'startX': 40, 'startY': 40,
             'endX': 50, 'endY': 40})
        observation = make_observation(board=board)
        contract = make_contract(observation)
        runner = RecordingRunner()
        plan = track_plan([(40, 40), (50, 40)], observation=observation)
        result = D.apply_scoped(contract, plan, runner=runner, write=True)
        self.assertEqual(result['status'], 'no_op')
        self.assertTrue(result['ok'])
        self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(runner.calls, [])

    def test_filtered_apply_journal_maps_back_to_original_ops(self):
        base = make_board()
        first_track = {'primitiveId': 'new-1', 'net': 'GND', 'layer': 1,
                       'lineWidth': 10, 'startX': 100, 'startY': 50,
                       'endX': 110, 'endY': 50}
        board = copy.deepcopy(base)
        board['copper']['lines'].append(first_track)
        observation = make_observation(board=board)
        contract = make_contract(observation)
        after_board = copy.deepcopy(board)
        after_board['copper']['lines'].append(
            {'primitiveId': 'new-2', 'net': 'GND', 'layer': 1,
             'lineWidth': 10, 'startX': 110, 'startY': 50,
             'endX': 120, 'endY': 50})
        after_board['semanticSha256'] = 'after-base'
        plan = {
            'schema': D.PLAYBOOK_SCHEMA,
            'base': {'semantic_sha256': BASE},
            'ops': [
                {'op': 'track', 'net': 'GND', 'layer': 1, 'width_mil': 10,
                 'points': [[100, 50], [110, 50]]},
                {'op': 'track', 'net': 'GND', 'layer': 1, 'width_mil': 10,
                 'points': [[110, 50], [120, 50]]},
            ],
            'observation': observation,
            'before_dump': raw_before_dump(observation),
        }
        runner = PcbFakeRunner(after_board)
        with tempfile.TemporaryDirectory() as directory:
            journal_path = os.path.join(directory, 'apply.jsonl')
            result = D.apply_scoped(contract, plan, runner=runner, write=True,
                                    journal_path=journal_path)
            self.assertEqual(result['status'], 'verified', result.get(
                'failure'))
            self.assertEqual(result['writes_sent'], 1)
            journal_ids = [step.get('id') for step in
                           result['journal']['entries']
                           if step.get('id')]
            self.assertIn('track-0-1', journal_ids)
            self.assertNotIn('track-1-1', journal_ids)
            recovery = D.recover(
                contract, journal_path,
                current_observation=make_observation(
                    board=after_board, hash_value='after-base'),
                plan=plan)
            self.assertEqual(recovery['status'], 'complete',
                             recovery['operations'])
            self.assertEqual(len(recovery['applied']), 2)

    def test_schematic_apply_verifies_context_and_readback(self):
        observation = make_observation()
        contract = make_contract(observation, scope={'objects': ['txt-1']},
                                 actions=['move_text', 'save'])
        plan = {
            'base': {'semantic_sha256': BASE},
            'document': {'uuid': 'sch-doc'},
            'ops': [{'op': 'move_text', 'primitive_id': 'txt-1',
                     'x': 10, 'y': 20}],
            'save': True,
            'observation': observation,
        }
        runner = SchFakeRunner()
        result = D.apply_scoped(contract, plan, runner=runner, write=True)
        self.assertEqual(result['status'], 'verified', result.get('failure'))
        self.assertTrue(result['call_ok'])
        self.assertTrue(result['write_confirmed'])
        self.assertTrue(result['save_confirmed'])
        self.assertIsNone(result['reopen_confirmed'])
        self.assertIsNone(result['quality_passed'])
        self.assertEqual(result['writes_sent'], 1)
        self.assertEqual([call['args'][1] for call in runner.calls],
                         ['schematic.text.move', 'schematic.text.list',
                          'schematic.save'])

    def test_schematic_wrong_response_context_is_target_mismatch(self):
        observation = make_observation()
        contract = make_contract(observation, scope={'objects': ['txt-1']},
                                 actions=['move_text', 'save'])
        plan = {
            'base': {'semantic_sha256': BASE},
            'document': {'uuid': 'sch-doc'},
            'ops': [{'op': 'move_text', 'primitive_id': 'txt-1',
                     'x': 10, 'y': 20}],
            'save': True,
            'observation': observation,
        }
        runner = SchFakeRunner(context={'projectUuid': 'other-project',
                                        'documentUuid': 'sch-doc'})
        result = D.apply_scoped(contract, plan, runner=runner, write=True)
        self.assertEqual(result['status'], 'target_mismatch')
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure']['failure_class'],
                         S.FAILURE_TARGET_MISMATCH)
        self.assertFalse(result['write_confirmed'])

    def test_missing_readback_is_unknown_never_verified(self):
        observation = make_observation()
        contract = make_contract(observation, scope={'objects': ['txt-1']},
                                 actions=['move_text', 'save'])
        plan = {
            'base': {'semantic_sha256': BASE},
            'document': {'uuid': 'sch-doc'},
            'ops': [{'op': 'move_text', 'primitive_id': 'txt-1',
                     'x': 10, 'y': 20}],
            'save': True,
            'observation': observation,
        }
        runner = SchFakeRunner(omit_texts=True)
        result = D.apply_scoped(contract, plan, runner=runner, write=True)
        self.assertIsNone(result['write_confirmed'])
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['ok'])
        self.assertIn('write_confirmed',
                      [item['field'] for item in result['unknown']])


# ---------------------------------------------------------------------------
# recovery
# ---------------------------------------------------------------------------

class RecoveryTests(unittest.TestCase):
    def contract(self):
        return make_contract()

    def two_track_plan(self):
        return {
            'schema': D.PLAYBOOK_SCHEMA,
            'base': {'semantic_sha256': BASE},
            'ops': [
                {'op': 'track', 'net': 'GND', 'layer': 1, 'width_mil': 10,
                 'points': [[0, 0], [10, 0]]},
                {'op': 'track', 'net': 'GND', 'layer': 1, 'width_mil': 10,
                 'points': [[10, 0], [20, 0]]},
            ],
        }

    def board_with_first_track(self):
        board = make_board()
        board['copper']['lines'].append(
            {'primitiveId': 'new', 'net': 'GND', 'layer': 1,
             'lineWidth': 10, 'startX': 0, 'startY': 0,
             'endX': 10, 'endY': 0})
        return board

    def test_partial_success_is_applied_plus_pending(self):
        journal = [
            {'playbookSha256': 'sha'},
            {'idx': 1, 'id': 'track-0-1', 'status': 'ok'},
            {'idx': 2, 'id': 'track-1-1', 'status': 'failed'},
        ]
        observation = make_observation(board=self.board_with_first_track())
        result = D.recover(self.contract(), journal,
                           current_observation=observation,
                           plan=self.two_track_plan())
        self.assertEqual(result['status'], 'resumable')
        self.assertTrue(result['safe_to_retry'])
        self.assertEqual(len(result['applied']), 1)
        self.assertEqual(len(result['pending']), 1)
        self.assertEqual(result['unknown'], [])
        self.assertEqual(result['duplicate_risk'], [])

    def test_sent_but_unconfirmed_track_is_duplicate_risk(self):
        journal = [
            {'playbookSha256': 'sha'},
            {'idx': 1, 'id': 'track-0-1', 'status': 'ok'},
            {'idx': 2, 'id': 'track-1-1', 'status': 'sent'},
        ]
        observation = make_observation(board=self.board_with_first_track())
        result = D.recover(self.contract(), journal,
                           current_observation=observation,
                           plan=self.two_track_plan())
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['safe_to_retry'])
        self.assertEqual(len(result['duplicate_risk']), 1)
        operation = next(item for item in result['operations']
                         if item['state'] == 'unknown')
        self.assertFalse(operation['safe_to_retry'])
        self.assertTrue(operation['duplicate_risk'])

    def test_missing_journal_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'missing.jsonl')
            result = D.recover(self.contract(), path,
                               plan=self.two_track_plan())
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['safe_to_retry'])
        self.assertTrue(result['journal']['problems'])

    def test_operation_key_is_content_stable(self):
        first = {'op': 'track', 'net': 'GND', 'layer': 1,
                 'width_mil': 10.0, 'points': [[0, 0], [10, 0]],
                 'primitiveId': 'volatile-1'}
        second = {'op': 'track', 'net': 'GND', 'layer': 1,
                  'width_mil': 10, 'points': [[0.0, 0.0], [10.0, 0.0]],
                  'primitiveId': 'volatile-2'}
        self.assertEqual(D.operation_key(first), D.operation_key(second))
        first['net'] = 'LED_A'
        self.assertNotEqual(D.operation_key(first), D.operation_key(second))
        place_a = {'op': 'place', 'designator': 'D1',
                   'to': {'x': 100, 'y': 100, 'rotation': 0},
                   'primitive_id': 'old'}
        place_b = {'op': 'place', 'designator': 'D1',
                   'to': {'x': 100.0, 'y': 100.0, 'rotation': 360.0},
                   'primitive_id': 'new'}
        self.assertEqual(D.operation_key(place_a), D.operation_key(place_b))

    def test_recover_without_plan_uses_journal_ids(self):
        journal = [
            {'playbookSha256': 'sha'},
            {'idx': 1, 'id': 'track-0-1', 'status': 'ok'},
        ]
        result = D.recover(self.contract(), journal)
        self.assertEqual(len(result['operations']), 1)
        self.assertEqual(result['operations'][0]['state'], 'applied')
        self.assertTrue(result['safe_to_retry'])


if __name__ == '__main__':
    unittest.main()
