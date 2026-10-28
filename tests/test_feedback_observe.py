"""Tests for the observation work package (capability probe + contract + cache).

Every test injects a fake runner with the same signature as ``pcb_cli.run``.
No test resolves ``zhigou`` through PATH, opens a socket or writes outside a
temporary directory.
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
SCRIPTS = ROOT / 'easycirq' / 'scripts'
FIXTURES = ROOT / 'tests' / 'fixtures'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / 'tests'))

from feedback import observe  # noqa: E402
from feedback import schemas  # noqa: E402

PROJECT = 'e56848aaf64d49d7a465352291670aef'
SCH_DOC = '5ff4d6e7c85dd153'
PCB_DOC = '99b8366b0bdc971f'
PROJECT_NAME = 'photo-led-pcb-20261026'
WINDOW = '5175351c-a00b-4788-a922-2f6e0bd80756'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


BOARD = load(FIXTURES / 'photo-led-pcb-board.json')

SCH_PAYLOAD = {
    'componentCount': 3,
    'netCount': 2,
    'floatingPinCount': 1,
    'netlistAvailable': True,
    'components': [
        {
            'componentType': 'sheet',
            'designator': '',
            'name': '5V LED board',
            'pins': [],
            'primitiveId': 'sheet-1',
            'x': 0,
            'y': 0,
        },
        {
            'componentType': 'part',
            'designator': 'U1',
            'name': '={Manufacturer Part}',
            'primitiveId': 'u1-primitive',
            'uniqueId': 'gge1',
            'x': 330,
            'y': 180,
            'footprint': {'name': 'DIP-8', 'uuid': 'fp-u1'},
            'pins': [
                {'number': '4', 'name': 'GND', 'net': 'GND'},
                {'number': '8', 'name': 'VCC', 'net': '+5V'},
                {'number': '5', 'name': '2IN+', 'net': None},
            ],
        },
        {
            'componentType': 'part',
            'designator': 'J1',
            'name': '={Manufacturer Part}',
            'primitiveId': 'j1-primitive',
            'uniqueId': 'gge2',
            'x': 560,
            'y': 710,
            'footprint': {'name': 'CONN-2P', 'uuid': 'fp-j1'},
            'pins': [{'number': '2', 'name': '2', 'net': 'GND'}],
        },
    ],
    'nets': [
        {'net': 'GND', 'pins': ['U1.4', 'J1.2'], 'degree': 2,
         'isGlobal': True},
        {'net': '+5V', 'pins': ['U1.8'], 'degree': 1, 'isGlobal': True},
    ],
    'floatingPins': [{'designator': 'U1', 'number': '5'}],
    'check': {'passed': True, 'findings': [],
              'summary': {'floatingPins': 1, 'total': 1}},
}

PCB_DRC = {'passed': True, 'total': 0, 'counts': {}, 'violations': [],
           'nativeResult': {'passed': True, 'violations': []}}
PCB_CHECK = {
    'passed': False,
    'summary': {'errors': 1, 'warnings': 0, 'total': 1},
    'findings': [{'type': 'dangling-end', 'level': 'ERROR',
                  'designator': 'C1'}],
    'incomplete': False,
    'coverage': {'complete': True},
}
SCH_DRC = {'passed': True, 'nativePassed': True, 'strict': False, 'fatal': 0,
           'summary': {'fatal': 0, 'error': 0, 'warn': 1, 'info': 0,
                       'unknown': 0, 'total': 1},
           'violations': [{'level': 'warn', 'type': 'warn'}],
           'countsAvailable': True, 'detailsAvailable': True}


def record(argv, *, exit=0, payload=None, stdout='', stderr='', error=None):
    return {
        'argv': ['zhigou'] + list(argv),
        'exit': exit,
        'ok': bool(exit == 0 and isinstance(payload, dict) and
                   payload.get('ok') is not False),
        'error': error,
        'stdout': stdout,
        'stderr': stderr,
        'payload': payload,
        'started_at': '2026-01-01T00:00:00Z',
        'ended_at': '2026-01-01T00:00:01Z',
    }


def envelope(result, *, doc_uuid=SCH_DOC, project=PROJECT,
             name=PROJECT_NAME, ok=True):
    context = {
        'projectUuid': project,
        'projectName': name,
        'documentUuid': doc_uuid,
        'documentType': 'schematic' if doc_uuid == SCH_DOC else 'pcb',
        'tabId': '%s@%s' % (doc_uuid, project),
        'pageVisibility': 'hidden',
    }
    payload = {
        'id': 'req-test', 'type': 'response', 'version': 'v1',
        'windowId': WINDOW, 'createdAt': '2026-01-01T00:00:00Z',
        'ok': ok, 'result': result, 'context': context,
        'mutationContext': context,
    }
    if not ok:
        payload['error'] = {'code': 'FAILED', 'message': 'fake failure'}
    return payload


class FakeHost:
    """Controlled fake for ``pcb_cli.run``; records every call."""

    def __init__(self, *, project=PROJECT, name=PROJECT_NAME,
                 sch_doc=SCH_DOC, pcb_doc=PCB_DOC, dump=None,
                 sch_payload=None, sch_drc=None, pcb_drc=None,
                 pcb_check=None, timeout_labels=(), fail_labels=(),
                 garbage_labels=(), unknown_commands=(),
                 end_project=None, end_documents=None,
                 wrap_reports=False, help_fails=()):
        self.project = project
        self.name = name
        self.sch_doc = sch_doc
        self.pcb_doc = pcb_doc
        self.dump = copy.deepcopy(dump if dump is not None else BOARD)
        self.dump.setdefault('capture', {})
        self.dump['capture'].update({
            'windowId': WINDOW, 'projectUuid': project,
            'projectName': name, 'documentUuid': pcb_doc,
            'documentType': 'pcb', 'identityVerified': True,
        })
        self.sch_payload = copy.deepcopy(sch_payload or SCH_PAYLOAD)
        self.sch_drc = copy.deepcopy(sch_drc or SCH_DRC)
        self.pcb_drc = copy.deepcopy(pcb_drc or PCB_DRC)
        self.pcb_check = copy.deepcopy(pcb_check or PCB_CHECK)
        self.timeout_labels = set(timeout_labels)
        self.fail_labels = set(fail_labels)
        self.garbage_labels = set(garbage_labels)
        self.unknown_commands = set(unknown_commands)
        self.end_project = end_project
        self.end_documents = end_documents
        self.wrap_reports = wrap_reports
        self.help_fails = set(help_fails)
        self.calls = []
        self.info_calls = 0
        self.doc_calls = 0

    @staticmethod
    def _flag(args, name):
        if name in args:
            index = args.index(name)
            if index + 1 < len(args):
                return args[index + 1]
        return None

    @staticmethod
    def _label(args):
        if not args:
            return 'empty'
        if args[0] == 'version':
            return 'version'
        if args[0] == 'project' and len(args) > 1:
            return 'project-' + args[1]
        if args[0] == 'doc' and len(args) > 1:
            return 'doc-' + args[1]
        if len(args) > 1:
            return args[0] + '-' + args[1]
        return args[0]

    def _documents(self):
        return [
            {'uuid': self.sch_doc, 'type': 'schematic', 'name': 'P1'},
            {'uuid': self.pcb_doc, 'type': 'pcb', 'name': 'PCB1'},
        ]

    def __call__(self, args, *, zhigou=None, timeout=120, cwd=None, env=None):
        args = [str(item) for item in args]
        self.calls.append(args)
        label = self._label(args)
        if '--help' in args:
            command = ' '.join(args[:-1])
            if command in self.unknown_commands:
                return record(args, exit=1, payload={
                    'ok': False, 'error': {
                        'code': 'UNKNOWN_COMMAND', 'message': command}})
            if command in self.help_fails:
                return record(args, exit=1, payload={
                    'ok': False, 'error': {'code': 'FAILED',
                                           'message': 'help failed'}})
            return record(args, stdout='Usage: %s [flags]' % command)
        if label in self.timeout_labels:
            return record(args, exit=124, error='timeout after %ss' % timeout)
        if label in self.fail_labels:
            return record(args, exit=1, payload={
                'ok': False, 'error': {'code': 'FAILED',
                                       'message': 'injected failure'}})
        if label in self.garbage_labels:
            return record(args, stdout='not json at all')

        if label == 'version':
            return record(args, stdout='zhigou-agent v1.15.0-fake')
        if label == 'project-info':
            self.info_calls += 1
            project = self.project
            if self.end_project and self.info_calls > 1:
                project = self.end_project
            return record(args, payload=envelope({
                'uuid': project, 'friendlyName': self.name,
                'name': 'workspace/' + self.name}, project=project))
        if label == 'doc-ls':
            self.doc_calls += 1
            documents = self._documents()
            if self.end_documents is not None and self.doc_calls > 1:
                documents = self.end_documents
            return record(args, payload=envelope({'documents': documents},
                                                 doc_uuid=self.sch_doc))
        if label == 'sch-read':
            return record(args, payload=envelope(
                copy.deepcopy(self.sch_payload), doc_uuid=self.sch_doc))
        if label == 'pcb-list':
            components = copy.deepcopy(self.dump.get('components') or [])
            return record(args, payload=envelope(
                {'components': components, 'count': len(components)},
                doc_uuid=self.pcb_doc))
        if label == 'pcb-dump':
            return record(args, payload=copy.deepcopy(self.dump))
        if label == 'sch-drc':
            return record(args, payload=envelope(
                copy.deepcopy(self.sch_drc), doc_uuid=self.sch_doc))
        if label == 'pcb-drc':
            if self.wrap_reports:
                return record(args, payload=envelope(
                    copy.deepcopy(self.pcb_drc), doc_uuid=self.pcb_doc))
            return record(args, payload=copy.deepcopy(self.pcb_drc))
        if label == 'pcb-check':
            if self.wrap_reports:
                return record(args, payload=envelope(
                    copy.deepcopy(self.pcb_check), doc_uuid=self.pcb_doc))
            return record(args, payload=copy.deepcopy(self.pcb_check))
        return record(args, exit=1, payload={
            'ok': False, 'error': {'code': 'UNKNOWN_COMMAND',
                                   'message': ' '.join(args)}})


def collect(host, **kwargs):
    kwargs.setdefault('window', WINDOW)
    kwargs.setdefault('project', PROJECT)
    kwargs.setdefault('sch_doc', SCH_DOC)
    kwargs.setdefault('pcb_doc', PCB_DOC)
    return observe.collect_observation(runner=host, **kwargs)


class ProbeTests(unittest.TestCase):
    def test_all_required_capabilities_are_reported(self):
        host = FakeHost()
        result = observe.probe_capabilities(
            runner=host, window=WINDOW, project=PROJECT,
            sch_doc=SCH_DOC, pcb_doc=PCB_DOC)
        schemas.validate_capabilities(result)
        ids = [item['id'] for item in result['items']]
        self.assertEqual(sorted(ids), sorted(observe.CAPABILITY_IDS))
        self.assertEqual(len(ids), len(set(ids)))
        by_id = {item['id']: item for item in result['items']}
        for cap_id in ('project_doc_identity', 'sch_object_read',
                       'sch_net_read', 'pcb_object_read',
                       'pcb_geometry_read', 'pcb_copper_read', 'sch_erc',
                       'pcb_drc', 'pcb_check'):
            self.assertEqual(by_id[cap_id]['status'], 'available', cap_id)
            self.assertTrue(by_id[cap_id]['evidence'])
        for cap_id in observe.WRITE_CAPABILITIES:
            self.assertEqual(by_id[cap_id]['status'], 'unknown', cap_id)
            self.assertTrue(by_id[cap_id]['reason'])
        self.assertIn('write_probe_not_executed', by_id['save']['reason'])

    def test_help_only_and_missing_undo(self):
        host = FakeHost(unknown_commands={'undo'})
        result = observe.probe_capabilities(
            runner=host, window=WINDOW, project=PROJECT,
            sch_doc=SCH_DOC, pcb_doc=PCB_DOC)
        by_id = {item['id']: item for item in result['items']}
        self.assertEqual(by_id['undo']['status'], 'unavailable')
        self.assertEqual(by_id['undo']['reason'], 'command_not_found')
        self.assertEqual(by_id['export_archive']['status'], 'unknown')

    def test_timeout_is_unknown_never_available(self):
        host = FakeHost(timeout_labels={'sch-read'})
        result = observe.probe_capabilities(
            runner=host, window=WINDOW, project=PROJECT,
            sch_doc=SCH_DOC, pcb_doc=PCB_DOC)
        by_id = {item['id']: item for item in result['items']}
        for cap_id in ('sch_object_read', 'sch_net_read'):
            self.assertEqual(by_id[cap_id]['status'], 'unknown')
            self.assertIn('timeout', by_id[cap_id]['reason'])
        self.assertEqual(by_id['pcb_object_read']['status'], 'available')

    def test_identity_mismatch_is_unknown_never_available(self):
        host = FakeHost(project='a' * 32)
        result = observe.probe_capabilities(
            runner=host, window=WINDOW, project=PROJECT,
            sch_doc=SCH_DOC, pcb_doc=PCB_DOC)
        by_id = {item['id']: item for item in result['items']}
        self.assertEqual(by_id['project_doc_identity']['status'], 'unknown')
        self.assertIn('target_mismatch', by_id['project_doc_identity']['reason'])
        for cap_id in ('sch_object_read', 'pcb_geometry_read', 'pcb_check'):
            self.assertEqual(by_id[cap_id]['status'], 'unknown')
            self.assertIn('target_mismatch', by_id[cap_id]['reason'])

    def test_name_routing_probe(self):
        host = FakeHost()
        result = observe.probe_capabilities(
            runner=host, window=WINDOW, project=PROJECT_NAME,
            sch_doc='P1', pcb_doc='PCB1')
        by_id = {item['id']: item for item in result['items']}
        for cap_id in ('project_doc_identity', 'sch_object_read',
                       'pcb_geometry_read', 'pcb_copper_read', 'pcb_check'):
            self.assertEqual(by_id[cap_id]['status'], 'available', cap_id)

    def test_failed_read_is_not_available(self):
        host = FakeHost(fail_labels={'pcb-check'})
        result = observe.probe_capabilities(
            runner=host, window=WINDOW, project=PROJECT,
            sch_doc=SCH_DOC, pcb_doc=PCB_DOC)
        by_id = {item['id']: item for item in result['items']}
        self.assertEqual(by_id['pcb_check']['status'], 'unknown')
        self.assertIn('command_failed', by_id['pcb_check']['reason'])


class CollectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = copy.deepcopy(BOARD)

    def test_name_routing_matches_project_and_document_names(self):
        result = collect(FakeHost(), window=WINDOW,
                         project=PROJECT_NAME, sch_doc='P1', pcb_doc='PCB1')
        schemas.validate_observation(result)
        self.assertEqual(result['project']['uuid'], PROJECT)
        self.assertEqual(result['project']['name'], PROJECT_NAME)
        self.assertEqual([document['uuid'] for document in result['documents']],
                         [SCH_DOC, PCB_DOC])
        self.assertIsNotNone(result['schematic'])
        self.assertIsNotNone(result['pcb'])

    def test_name_routing_rejects_a_different_project_name(self):
        with self.assertRaises(schemas.FeedbackError) as raised:
            collect(FakeHost(), project='another-project-name')
        self.assertEqual(raised.exception.failure_class,
                         schemas.FAILURE_TARGET_MISMATCH)

    def test_name_routing_rejects_an_unknown_document_name(self):
        with self.assertRaises(schemas.FeedbackError) as raised:
            collect(FakeHost(), sch_doc='missing-page')
        self.assertEqual(raised.exception.failure_class,
                         schemas.FAILURE_TARGET_MISMATCH)

    def test_shared_sim_shapes_with_name_routing(self):
        import feedback_sim

        state = feedback_sim.make_state(active='sch-sim-0001')
        result = observe.collect_observation(
            runner=feedback_sim.FakeRunner(state), window='win-sim',
            project='sim-photo-led', sch_doc='sch-sim-0001',
            pcb_doc='pcb-sim-0001')
        schemas.validate_observation(result)
        self.assertEqual(result['project'],
                         {'uuid': 'proj-sim-0001',
                          'name': 'sim-photo-led'})
        self.assertEqual([(document['uuid'], document['name'])
                          for document in result['documents']],
                         [('sch-sim-0001', 'P1'),
                          ('pcb-sim-0001', 'PCB1')])
        self.assertEqual(result['schematic']['component_count'], 19)
        self.assertEqual(result['pcb']['component_count'], 19)
        self.assertEqual(result['degradations'], [])

    def test_full_observation_validates(self):
        host = FakeHost()
        result = collect(host)
        schemas.validate_observation(result)
        self.assertEqual(result['schema'], schemas.SCHEMA_OBSERVATION)
        self.assertEqual(result['project']['uuid'], PROJECT)
        self.assertEqual(len(result['documents']), 2)
        self.assertEqual(result['host']['window_id'], WINDOW)
        self.assertEqual(result['schematic']['component_count'], 2)
        self.assertEqual(result['schematic']['net_count'], 2)
        self.assertEqual(result['schematic']['drc']['passed'], True)
        self.assertEqual(result['pcb']['component_count'], 19)
        self.assertEqual(result['pcb']['tracks'], [])
        self.assertIsNotNone(result['pcb']['drc'])
        self.assertIsNotNone(result['pcb']['check'])
        self.assertEqual(result['pcb']['check']['passed'], False)
        revision = result['revision']
        self.assertEqual(len(revision['semantic_sha256']), 64)
        self.assertEqual(set(revision['per_document']), {SCH_DOC, PCB_DOC})
        # Bare DRC/check payloads do not echo context: they stay usable but
        # are recorded as identity-not-echoed degradations.
        sources = {item['source'] for item in result['degradations']
                   if item['reason'] == 'identity_context_not_echoed'}
        self.assertIn('pcb-drc', sources)
        self.assertIn('pcb-check', sources)
        self.assertFalse(result['pcb']['drc']['identity_verified'])

    def test_full_observation_with_wrapped_reports(self):
        result = collect(FakeHost(wrap_reports=True))
        self.assertTrue(result['pcb']['drc']['identity_verified'])
        self.assertTrue(result['pcb']['check']['identity_verified'])
        self.assertTrue(result['schematic']['drc']['identity_verified'])

    def test_dump_identity_mismatch_is_refused(self):
        host = FakeHost()
        host.dump['capture']['documentUuid'] = 'ffffffffffffffff'
        with self.assertRaises(schemas.FeedbackError) as raised:
            collect(host)
        self.assertEqual(raised.exception.failure_class,
                         schemas.FAILURE_TARGET_MISMATCH)

    def test_project_identity_mismatch_is_refused(self):
        host = FakeHost(project='b' * 32)
        with self.assertRaises(schemas.FeedbackError) as raised:
            collect(host)
        self.assertEqual(raised.exception.failure_class,
                         schemas.FAILURE_TARGET_MISMATCH)

    def test_missing_requested_document_is_refused(self):
        host = FakeHost(end_documents=[
            {'uuid': SCH_DOC, 'type': 'schematic', 'name': 'P1'}])
        with self.assertRaises(schemas.FeedbackError) as raised:
            collect(host)
        self.assertEqual(raised.exception.failure_class,
                         schemas.FAILURE_TARGET_MISMATCH)

    def test_live_identity_drift_is_refused(self):
        host = FakeHost(end_project='c' * 32)
        with self.assertRaises(schemas.FeedbackError) as raised:
            collect(host)
        self.assertEqual(raised.exception.failure_class,
                         schemas.FAILURE_TARGET_MISMATCH)

    def test_timeout_is_a_degradation_not_an_empty_list(self):
        host = FakeHost(timeout_labels={'sch-read', 'pcb-dump', 'sch-drc',
                                        'pcb-drc', 'pcb-check'})
        result = collect(host)
        schemas.validate_observation(result)
        self.assertIsNone(result['schematic'])
        self.assertIsNone(result['pcb'])
        self.assertIsNone(result['revision']['semantic_sha256'])
        reasons = {item['reason'] for item in result['degradations']}
        self.assertTrue(any(reason.startswith('timeout') for reason in reasons))
        fields = {item['field'] for item in result['unknown']}
        self.assertIn('schematic', fields)
        self.assertIn('pcb', fields)
        self.assertIn('revision.semantic_sha256', fields)

    def test_missing_section_is_unknown_not_empty(self):
        host = FakeHost(garbage_labels={'sch-read', 'pcb-dump'})
        result = collect(host)
        self.assertIsNone(result['schematic'])
        self.assertIsNone(result['pcb'])
        self.assertTrue(any(item['reason'] == 'no_json_payload'
                            for item in result['degradations']))

    def test_evidence_files_are_atomic_and_hashed(self):
        with tempfile.TemporaryDirectory(prefix='observe-evidence-') as tmp:
            host = FakeHost(fail_labels={'sch-drc'})
            result = collect(host, evidence_dir=tmp)
            self.assertEqual(len(result['evidence']), len(host.calls))
            for entry in result['evidence']:
                path = entry['path']
                self.assertTrue(os.path.isfile(path), path)
                data = Path(path).read_bytes()
                self.assertEqual(entry['bytes'], len(data))
                self.assertEqual(entry['sha256'],
                                 hashlib.sha256(data).hexdigest())
                self.assertTrue(path.startswith(os.path.abspath(tmp)))
            failed = [entry for entry in result['evidence']
                      if not entry['ok']]
            self.assertTrue(failed, 'a failed command must have evidence')
            self.assertTrue(any(item['source'] == 'sch-drc'
                                for item in result['degradations']))

    def test_semantic_hash_ignores_timestamps_and_commands(self):
        first = collect(FakeHost())
        second = collect(FakeHost())
        self.assertNotEqual(first['generated_at'], second['generated_at'])
        self.assertEqual(first['revision']['semantic_sha256'],
                         second['revision']['semantic_sha256'])
        self.assertEqual(observe.observation_semantic_hash(first),
                         observe.observation_semantic_hash(second))

    def test_semantic_hash_changes_when_the_board_changes(self):
        first = collect(FakeHost())
        changed = FakeHost()
        changed.dump['components'][0]['x'] += 10
        second = collect(changed)
        self.assertNotEqual(first['revision']['semantic_sha256'],
                            second['revision']['semantic_sha256'])
        comparison = observe.compare_baseline(second, first)
        self.assertEqual(comparison['status'], 'stale')
        self.assertIn(PCB_DOC, comparison['changed_documents'])


class CompareBaselineTests(unittest.TestCase):
    def setUp(self):
        self.current = collect(FakeHost())

    def baseline(self):
        return copy.deepcopy(self.current)

    def test_match(self):
        result = observe.compare_baseline(self.current, self.baseline())
        self.assertEqual(result['status'], 'match')
        self.assertEqual(result['changed_documents'], [])
        self.assertEqual(result['semantic_sha256']['current'],
                         result['semantic_sha256']['baseline'])

    def test_stale_reports_changed_documents(self):
        baseline = self.baseline()
        baseline['revision']['semantic_sha256'] = '0' * 64
        baseline['revision']['per_document'][PCB_DOC] = '1' * 64
        result = observe.compare_baseline(self.current, baseline)
        self.assertEqual(result['status'], 'stale')
        self.assertIn(PCB_DOC, result['changed_documents'])
        self.assertIn('semantic_hash_changed', result['reasons'])

    def test_target_mismatch_on_project_or_documents(self):
        baseline = self.baseline()
        baseline['project']['uuid'] = 'd' * 32
        result = observe.compare_baseline(self.current, baseline)
        self.assertEqual(result['status'], 'target_mismatch')
        self.assertTrue(result['reasons'])

        baseline = self.baseline()
        baseline['documents'] = [baseline['documents'][0]]
        result = observe.compare_baseline(self.current, baseline)
        self.assertEqual(result['status'], 'target_mismatch')
        self.assertIn(PCB_DOC, result['changed_documents'])

    def test_unknown_when_baseline_has_no_hash(self):
        baseline = self.baseline()
        baseline['revision']['semantic_sha256'] = None
        baseline['unknown'].append(
            {'field': 'revision.semantic_sha256',
             'reason': 'not measured in this fixture'})
        result = observe.compare_baseline(self.current, baseline)
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('baseline_not_measured', result['reasons'])

    def test_invalid_observation_is_unknown(self):
        result = observe.compare_baseline({'schema': 'wrong'}, self.baseline())
        self.assertEqual(result['status'], 'unknown')
        self.assertTrue(result['reasons'])


class SchematicNormalizationTests(unittest.TestCase):
    def test_real_shaped_payload(self):
        normalized = observe.normalize_sch_read(
            envelope(copy.deepcopy(SCH_PAYLOAD)))
        self.assertEqual(normalized['document_uuid'], SCH_DOC)
        self.assertEqual(normalized['component_count'], 2)
        self.assertEqual(normalized['excluded_objects'], {'sheet': 1})
        self.assertEqual(normalized['components'][0]['designator'], 'U1')
        self.assertEqual(normalized['components'][0]['pins'][0]['number'], '4')
        self.assertEqual(normalized['components'][0]['pins'][0]['net'], 'GND')
        self.assertEqual(normalized['nets'][0]['name'], 'GND')
        self.assertEqual(normalized['nets'][0]['members'], ['U1.4', 'J1.2'])
        self.assertEqual(len(normalized['floating_pins']), 1)
        self.assertTrue(normalized['check']['passed'])
        fields = {item['field'] for item in normalized['unknown']}
        self.assertIn('schematic.components[].rotation', fields)
        self.assertIn('schematic.components[].mirror', fields)
        self.assertIn('schematic.components[].device', fields)
        self.assertIn('schematic.components[].pins[].primitive_id', fields)

    def test_enriched_component_keeps_identity_fields(self):
        payload = copy.deepcopy(SCH_PAYLOAD)
        payload['components'][1].update({
            'rotation': 90, 'mirror': True,
            'device': {'name': 'LM358P', 'uuid': 'dev-1'},
            'symbol': {'name': 'LM358P', 'uuid': 'sym-1'},
        })
        normalized = observe.normalize_sch_read(payload)
        component = normalized['components'][0]
        self.assertEqual(component['rotation'], 90)
        self.assertTrue(component['mirror'])
        self.assertEqual(component['device']['uuid'], 'dev-1')
        self.assertEqual(component['symbol']['uuid'], 'sym-1')
        fields = {item['field'] for item in normalized['unknown']}
        self.assertNotIn('schematic.components[].rotation', fields)

    def test_empty_is_measured_and_missing_is_unknown(self):
        empty = observe.normalize_sch_read(
            {'components': [], 'nets': [], 'netlistAvailable': True,
             'floatingPins': [], 'check': {'passed': True}})
        self.assertEqual(empty['components'], [])
        self.assertEqual(empty['nets'], [])
        self.assertEqual(empty['availability']['components'], 'available')
        missing = observe.normalize_sch_read({'netlistAvailable': False})
        self.assertIsNone(missing['components'])
        self.assertIsNone(missing['nets'])
        self.assertEqual(missing['availability']['nets'], 'unknown')


class PcbNormalizationTests(unittest.TestCase):
    def test_real_shaped_fixture(self):
        dump = copy.deepcopy(BOARD)
        normalized = observe.normalize_pcb_dump(dump)
        self.assertEqual(normalized['component_count'], 19)
        pads = sum(len(component['pads'] or [])
                   for component in normalized['components'])
        self.assertEqual(pads, 47)
        self.assertEqual(len(normalized['holes']), 47)
        self.assertEqual(normalized['tracks'], [])
        self.assertEqual(normalized['vias'], [])
        self.assertEqual(normalized['pours'], [])
        self.assertEqual(len(normalized['fills']), 4)
        self.assertGreater(normalized['outline']['point_count'], 100)
        self.assertEqual(normalized['copper_layers'], 2)
        self.assertEqual(normalized['copperLayers'], 2)
        self.assertEqual(normalized['captured_at'], dump['capturedAt'])
        self.assertEqual(normalized['semantic_sha256'],
                         dump['semanticSha256'])
        self.assertEqual(normalized['components'][0]['uniqueId'],
                         dump['components'][0]['uniqueId'])
        self.assertEqual(normalized['components'][0]['pads'][0]['number'],
                         dump['components'][0]['pads'][0]['padNumber'])
        self.assertIsInstance(normalized['rules'], dict)
        self.assertIsNotNone(normalized['nets'])
        fields = {item['field'] for item in normalized['unknown']}
        self.assertIn('pcb.unrouted', fields)
        self.assertIn('pcb.drc', fields)

    def test_missing_copper_is_unknown_not_empty(self):
        dump = copy.deepcopy(BOARD)
        dump.pop('copper')
        normalized = observe.normalize_pcb_dump(dump)
        self.assertEqual(normalized['component_count'], 19)
        self.assertIsNone(normalized['tracks'])
        self.assertIsNone(normalized['vias'])
        self.assertIsNone(normalized['pours'])
        self.assertIsNone(normalized['regions'])
        fields = {item['field'] for item in normalized['unknown']}
        self.assertIn('pcb.tracks', fields)
        self.assertIn('pcb.vias', fields)
        self.assertIn('pcb.pours', fields)

    def test_empty_board_is_measured(self):
        empty = {
            'components': [],
            'componentsAvailability': 'available',
            'outline': {'points': [], 'bbox': None},
            'copper': {
                'availability': {key: 'available' for key in
                                 ('fills', 'poured', 'pours', 'regions',
                                  'routing', 'vias')},
                'lines': [], 'arcs': [], 'vias': [], 'pours': [],
                'poured': [], 'regions': [], 'fills': [],
            },
            'rules': {}, 'copperLayers': 2,
            'capturedAt': '2026-01-01T00:00:00Z',
            'semanticSha256': '0' * 64,
        }
        normalized = observe.normalize_pcb_dump(empty)
        self.assertEqual(normalized['components'], [])
        self.assertEqual(normalized['tracks'], [])
        self.assertEqual(normalized['vias'], [])
        self.assertEqual(normalized['pours'], [])
        self.assertEqual(normalized['holes'], [])
        self.assertEqual(normalized['nets'], [])

    def test_missing_outline_is_unknown(self):
        dump = copy.deepcopy(BOARD)
        dump.pop('outline')
        normalized = observe.normalize_pcb_dump(dump)
        self.assertIsNone(normalized['outline'])
        self.assertIn('pcb.outline',
                      {item['field'] for item in normalized['unknown']})


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='observe-cache-')
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'cache.json')
        self.observation = collect(FakeHost())
        self.key = observe.cache_key(WINDOW, PROJECT, SCH_DOC, PCB_DOC)

    def test_cache_key_dimensions(self):
        key = observe.cache_key(WINDOW, PROJECT, SCH_DOC, PCB_DOC)
        for field in ('window', 'project', 'document', 'type', 'command',
                      'args'):
            self.assertIn(field, key)
        self.assertEqual(key['documents'],
                         {'schematic': SCH_DOC, 'pcb': PCB_DOC})

    def test_put_get_roundtrip_and_save_load(self):
        cache = observe.ObservationCache(self.path)
        cache.put(self.key, self.observation)
        cache.save()
        self.assertEqual(cache.get(self.key), self.observation)
        reloaded = observe.ObservationCache(self.path)
        self.assertEqual(reloaded.get(self.key), self.observation)
        self.assertEqual(len(reloaded.entries), 1)

    def test_changed_revision_misses(self):
        cache = observe.ObservationCache(self.path)
        first = dict(self.key, revision='rev-1')
        second = dict(self.key, revision='rev-2')
        cache.put(first, self.observation)
        self.assertEqual(cache.get(first), self.observation)
        self.assertIsNone(cache.get(second))

    def test_identity_mismatch_is_never_returned(self):
        cache = observe.ObservationCache(self.path)
        cache.put(self.key, self.observation)
        digest = cache._digest(observe._normalized_key(self.key))
        cache.entries[digest]['identity'] = {'project': 'other-project',
                                             'document': PCB_DOC}
        self.assertIsNone(cache.get(self.key))
        self.assertNotIn(digest, cache.entries)

    def test_put_refuses_mismatched_value_identity(self):
        cache = observe.ObservationCache(self.path)
        wrong = copy.deepcopy(self.observation)
        wrong['project']['uuid'] = 'e' * 32
        with self.assertRaises(ValueError):
            cache.put(self.key, wrong)

    def test_invalidate_prefix(self):
        cache = observe.ObservationCache(self.path)
        cache.put(self.key, self.observation)
        other_window = dict(self.key, window='another-window')
        cache.put(other_window, self.observation)
        self.assertEqual(cache.invalidate({'window': WINDOW}), 1)
        self.assertIsNotNone(cache.get(other_window))
        self.assertEqual(cache.invalidate(), 1)
        self.assertIsNone(cache.get(other_window))

    def test_invalidate_string_prefix(self):
        cache = observe.ObservationCache(self.path)
        cache.put(self.key, self.observation)
        self.assertEqual(cache.invalidate(PROJECT[:10]), 1)
        self.assertIsNone(cache.get(self.key))

    def test_corrupt_cache_is_reported_not_raised(self):
        Path(self.path).write_text('{not json', encoding='utf-8')
        cache = observe.ObservationCache(self.path)
        self.assertTrue(cache.problems)
        self.assertEqual(cache.entries, {})


if __name__ == '__main__':
    unittest.main()
