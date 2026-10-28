import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import pcb_cli
import pcb_preflight

_SENTINEL = object()


# ---------------------------------------------------------------------------
# Synthetic measured evidence
#
# The real photo-led fixture is deliberately used in no test here because it
# has no copper, preferred silk findings and a power audit that is genuinely
# review.  The synthetic board below is small, fully measured and internally
# consistent so "ready" is provable; each negative test then changes one fact.

def pad(primitive_id, number, net, x, y, layer=1):
    return {'primitiveId': primitive_id, 'padNumber': number, 'net': net,
            'layer': layer, 'x': x, 'y': y, 'width': 20, 'height': 20,
            'rotation': 0, 'shape': ['RECT', 20, 20]}


def ready_dump():
    return {
        'project': 'demo-project',
        'semanticSha256': 'hash-ready',
        'capturedAt': '2026-10-26T00:00:00Z',
        'availability': {
            'components': 'available', 'copper': 'available',
            'layers': 'available', 'outline': 'available',
            'routedLines': 'available', 'rules': 'available',
            'silk': 'available',
        },
        'capture': {
            'projectUuid': 'project-uuid-demo',
            'projectName': 'demo-project',
            'documentUuid': 'doc-uuid-demo',
            'documentType': 'pcb',
            'tabId': 'doc-uuid-demo@project-uuid-demo',
            'identityVerified': True,
        },
        'copperLayers': 2,
        'rules': {},
        'outline': {
            'bbox': {'minX': 0, 'minY': 0, 'maxX': 1000, 'maxY': 1000},
            'points': [[0, 0], [1000, 0], [1000, 1000], [0, 1000]],
            'source': 'polygon', 'format': 'polyline',
        },
        'components': [
            {
                'designator': 'U1', 'primitiveId': 'pid-u1',
                'uniqueId': 'uid-u1', 'name': 'IC', 'device': {'name': 'IC'},
                'layer': 1, 'x': 500, 'y': 500, 'rotation': 0,
                'bbox': {'minX': 450, 'minY': 450, 'maxX': 550, 'maxY': 550},
                'pads': [
                    pad('pid-u1-1', '1', '+5V', 460, 460),
                    pad('pid-u1-2', '2', 'GND', 540, 460),
                    pad('pid-u1-3', '3', 'SIG', 460, 540),
                    pad('pid-u1-4', '4', 'GND', 540, 540),
                    pad('pid-u1-9', '9', 'GND', 500, 500),
                ],
            },
            {
                'designator': 'C1', 'primitiveId': 'pid-c1',
                'uniqueId': 'uid-c1', 'name': 'CAP', 'device': {'name': 'CAP'},
                'layer': 1, 'x': 400, 'y': 460, 'rotation': 0,
                'bbox': {'minX': 380, 'minY': 440, 'maxX': 420, 'maxY': 480},
                'pads': [
                    pad('pid-c1-1', '1', '+5V', 390, 460),
                    pad('pid-c1-2', '2', 'GND', 410, 460),
                ],
            },
            {
                'designator': 'J1', 'primitiveId': 'pid-j1',
                'uniqueId': 'uid-j1', 'name': 'CONN', 'device': {'name': 'CONN'},
                'layer': 1, 'x': 50, 'y': 500, 'rotation': 0,
                'bbox': {'minX': 20, 'minY': 480, 'maxX': 80, 'maxY': 520},
                'pads': [
                    pad('pid-j1-1', '1', '+5V', 40, 490),
                    pad('pid-j1-2', '2', 'GND', 60, 490),
                ],
            },
            {
                'designator': 'U2', 'primitiveId': 'pid-u2',
                'uniqueId': 'uid-u2', 'name': 'SENSOR', 'device': {'name': 'SENSOR'},
                'layer': 1, 'x': 800, 'y': 500, 'rotation': 0,
                'bbox': {'minX': 760, 'minY': 470, 'maxX': 840, 'maxY': 530},
                'pads': [pad('pid-u2-1', '1', 'GND', 800, 490)],
            },
        ],
        'silk': [],
        'copper': {
            'lines': [{
                'primitiveId': 'line-5v', 'net': '+5V', 'layer': 1,
                'lineWidth': 10, 'startX': 350, 'startY': 460,
                'endX': 380, 'endY': 460,
            }],
            'vias': [], 'pours': [], 'poured': [],
            'arcs': [], 'regions': [], 'fills': [],
        },
    }


def ready_constraints():
    return {
        'schema': 'design-engine-pcb-constraints/v1',
        'status': 'compiled',
        'constraints': [
            {'id': 'FIX-U1', 'type': 'fixed', 'severity': 'hard',
             'source': 'test fixed U1', 'unit': 'mil', 'designator': 'U1',
             'x': 500.0, 'y': 500.0, 'rotation': 0.0, 'layer': 1},
            {'id': 'NP-C1-U1', 'type': 'near_pin', 'severity': 'hard',
             'source': 'test decap C1 to U1 power', 'unit': 'mil',
             'part': 'C1', 'pad': '1', 'owner': 'U1', 'owner_pad': '1',
             'max_mil': 200.0, 'role': 'decap'},
            {'id': 'ROT-U1', 'type': 'allowed_rotation', 'severity': 'preferred',
             'source': 'test orientation', 'designator': 'U1',
             'angles': [0, 90, 180, 270]},
        ],
        'conflicts': [],
        'unknown': [],
        'counts': {'constraints': 3, 'hard': 2, 'preferred': 1,
                   'conflicts': 0, 'unknown': 0},
    }


def ready_intent():
    intent = {
        'schema': 'design-engine-pcb-intent/v1',
        'project': 'demo-project',
        'units': 'mil',
        'constraints': [
            {'id': 'FIX-U1', 'type': 'fixed', 'severity': 'hard',
             'source': 'test fixed U1', 'designator': 'U1', 'x': 500, 'y': 500,
             'rotation': 0, 'layer': 1, 'unit': 'mil'},
            {'id': 'NP-C1-U1', 'type': 'near_pin', 'severity': 'hard',
             'source': 'test decap C1 to U1 power', 'part': 'C1', 'pad': '1',
             'owner': 'U1', 'owner_pad': '1', 'max_mil': 200, 'unit': 'mil',
             'role': 'decap'},
            {'id': 'ROT-U1', 'type': 'allowed_rotation', 'severity': 'preferred',
             'source': 'test orientation', 'designator': 'U1',
             'angles': [0, 90, 180, 270]},
        ],
        'modules': [],
        'components': [
            {'designator': 'U1', 'ep': True, 'ep_pad': '9'},
            {'designator': 'C1', 'ep': False},
        ],
        'connectors': [],
        'rf': [],
        'sensors': [],
        'power_nets': [
            {'net': '+5V', 'strategy': 'track', 'current_a': 0.01,
             'copper_oz': 1.0, 'temp_rise_c': 10, 'source': 'test load'},
        ],
    }
    return intent


def placement_rows(dump=None):
    dump = dump or ready_dump()
    rows = []
    for component in dump['components']:
        rows.append({
            'designator': component['designator'],
            'x': component['x'], 'y': component['y'],
            'rotation': component.get('rotation', 0),
            'layer': component.get('layer', 1),
        })
    return rows


def ready_plan(dump=None):
    return {
        'schema': 'design-engine-pcb-placement-plan/v1',
        'base_semantic_sha256': (dump or ready_dump()).get('semanticSha256'),
        'primitive_ids': {component['designator']: component['primitiveId']
                          for component in (dump or ready_dump())['components']},
        'placements': placement_rows(dump),
    }


def ready_identity():
    return {
        'status': 'pass',
        'counts': {'before_parts': 4, 'after_parts': 4,
                   'blocking_findings': 0, 'informational_findings': 0},
        'findings': [],
        'blocking_findings': [],
        'informational_findings': [],
        'pcb_binding': {'status': 'checked', 'sch_parts': 4, 'pcb_parts': 4,
                        'mismatches': 0},
    }


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers --------------------------------------------------------

    def write(self, name, value):
        path = self.dir / name
        text = value if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, indent=2)
        path.write_text(text, encoding='utf-8')
        return str(path)

    def run_main(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = pcb_preflight.main(argv)
        return code, buffer.getvalue()

    def argv(self, *, dump=None, plan=None, constraints=None, intent=None,
             identity=_SENTINEL, schematic=None,
             project='demo-project', doc='pcb', partial=False, json_out=True,
             out=None):
        argv = ['--dump', self.write('board.json', dump or ready_dump())]
        if plan is not None:
            argv += ['--plan', self.write('plan.json', plan)]
        if constraints is not None:
            argv += ['--constraints', self.write('constraints.json', constraints)]
        if intent is not None:
            argv += ['--intent', self.write('intent.json', intent)]
        if identity is _SENTINEL:
            identity = ready_identity()
        if identity is not None:
            argv += ['--identity', self.write('identity.json', identity)]
        if schematic is not None:
            argv += ['--schematic', self.write('schematic.json', schematic)]
        if project:
            argv += ['--project', project]
        if doc:
            argv += ['--doc', doc]
        if partial:
            argv.append('--partial')
        if json_out:
            argv.append('--json')
        if out:
            argv += ['--out', out]
        return argv

    def report(self, code, output):
        self.assertIn('"schema"', output)
        return code, json.loads(output)

    def by_id(self, report):
        return {check['id']: check for check in report['checks']}

    # -- ready / review / blocked --------------------------------------

    def test_ready_preflight(self):
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent()))
        code, report = self.report(code, output)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'ready')
        self.assertEqual(report['schema'], 'design-engine-pcb-preflight/v1')
        self.assertEqual(report['counts']['hard_fail'], 0)
        self.assertEqual(report['counts']['hard_unmeasured'], 0)
        checks = self.by_id(report)
        for check_id in ('dump.components_coverage', 'dump.outline_coverage',
                         'constraints.compiled', 'placement.hard',
                         'plan.base_hash', 'plan.primitive_ids',
                         'plan.designators_measured', 'identity.check',
                         'intent.ep', 'near_pin.decap_feedback',
                         'fabrication.audit', 'power.audit'):
            self.assertEqual(checks[check_id]['status'], 'pass', check_id)
        for check in report['checks']:
            self.assertTrue({'id', 'status', 'severity', 'objects', 'message',
                             'source'} <= set(check))
            self.assertIn(check['status'],
                          ('pass', 'fail', 'unmeasured', 'skipped'))
            self.assertIn(check['severity'], ('hard', 'advisory'))
        self.assertEqual(report['board']['component_count'], 4)
        self.assertEqual(report['board']['plan']['supplied'], True)

    def test_review_on_preferred_constraint_failure(self):
        intent = ready_intent()
        intent['constraints'][2]['angles'] = [90]  # U1 is measured at 0 degrees
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=intent))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(code, 1)
        self.assertEqual(checks['placement.hard']['status'], 'pass')
        self.assertEqual(checks['placement.preferred']['status'], 'fail')
        self.assertEqual(checks['placement.preferred']['severity'], 'advisory')
        self.assertEqual(report['counts']['hard_fail'], 0)
        self.assertEqual(report['counts']['hard_unmeasured'], 0)

    def test_blocked_on_stale_base_hash(self):
        plan = ready_plan()
        plan['base_semantic_sha256'] = 'hash-from-an-older-capture'
        code, output = self.run_main(self.argv(
            plan=plan, intent=ready_intent()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(code, 2)
        self.assertEqual(checks['plan.base_hash']['status'], 'fail')
        self.assertEqual(checks['plan.base_hash']['severity'], 'hard')
        self.assertEqual(checks['plan.base_hash']['objects']['dump'],
                         'hash-ready')

    def test_blocked_on_stale_primitive_id(self):
        plan = ready_plan()
        plan['primitive_ids']['U1'] = 'pid-expired'
        code, output = self.run_main(self.argv(
            plan=plan, intent=ready_intent()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(code, 2)
        self.assertEqual(checks['plan.primitive_ids']['status'], 'fail')
        self.assertEqual(checks['plan.primitive_ids']['severity'], 'hard')
        stale = checks['plan.primitive_ids']['objects']['stale']
        self.assertEqual(stale[0]['designator'], 'U1')
        self.assertEqual(stale[0]['actual'], 'pid-u1')

    def test_incomplete_on_missing_outline(self):
        dump = ready_dump()
        dump['outline'] = {'points': []}
        code, output = self.run_main(self.argv(
            dump=dump, plan=ready_plan(dump), intent=ready_intent()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(code, 2)
        self.assertEqual(checks['dump.outline_coverage']['status'], 'unmeasured')
        self.assertEqual(checks['dump.outline_coverage']['severity'], 'hard')

    def test_missing_identity_is_review_not_pass(self):
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(), identity=None))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(code, 1)
        self.assertEqual(checks['identity.check']['status'], 'unmeasured')
        self.assertEqual(checks['identity.check']['severity'], 'advisory')
        self.assertIn('identity.check',
                      {item['check'] for item in report['not_checked']})

    def test_identity_status_other_than_pass_fails(self):
        identity = ready_identity()
        identity['status'] = 'pass_sch_only'
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(), identity=identity))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(checks['identity.check']['status'], 'fail')
        self.assertEqual(report['status'], 'review')

    # -- constraint / plan edge cases ----------------------------------

    def test_decap_owner_pad_missing_fails(self):
        constraints = ready_constraints()
        near = constraints['constraints'][1]
        near['severity'] = 'preferred'
        near['owner_pad'] = '99'
        constraints['counts'] = {'constraints': 3, 'hard': 1, 'preferred': 2,
                                 'conflicts': 0, 'unknown': 0}
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(),
            constraints=constraints))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(checks['near_pin.decap_feedback']['status'], 'fail')
        self.assertEqual(checks['near_pin.decap_feedback']['severity'],
                         'advisory')
        rows = checks['near_pin.decap_feedback']['objects']['rows']
        self.assertEqual(rows[0]['owner'], 'U1.99')
        self.assertIn('owner pad is absent from the dump', rows[0]['reasons'])

    def test_decap_net_mismatch_fails(self):
        dump = ready_dump()
        dump['components'][1]['pads'][0]['net'] = 'VIN'  # C1.1 no longer +5V
        plan = ready_plan(dump)
        intent = ready_intent()
        # The near_pin hard constraint now contradicts the measured nets and
        # compile_constraints reports a hard pin_net_mismatch, so use the
        # explicit compiled file but keep the row advisory to isolate the
        # decap net-equality check.
        constraints = ready_constraints()
        constraints['constraints'][1]['severity'] = 'preferred'
        constraints['counts'] = {'constraints': 3, 'hard': 1, 'preferred': 2,
                                 'conflicts': 0, 'unknown': 0}
        code, output = self.run_main(self.argv(
            dump=dump, plan=plan, intent=intent, constraints=constraints))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(checks['near_pin.decap_feedback']['status'], 'fail')
        row = checks['near_pin.decap_feedback']['objects']['rows'][0]
        self.assertEqual(row['part_net'], 'VIN')
        self.assertEqual(row['owner_net'], '+5V')
        self.assertIn('pad nets differ', row['reasons'])

    def test_template_condition_rejection(self):
        intent = ready_intent()
        intent['modules'] = [{
            'id': 'decoupling',
            'template': 'ic-decap-gnd',
            'roles': {
                'core': {'designator': 'U1', 'pads': {'power': '1', 'gnd': '2'}},
                'cap': {'designator': 'C1', 'pads': {'power': '1', 'gnd': '2'}},
            },
        }]
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=intent))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(checks['intent.modules']['status'], 'fail')
        rejected = checks['intent.modules']['objects']['rejected']
        self.assertTrue(rejected)
        self.assertTrue(any('condition' in reason
                            for reason in rejected[0]['reasons']))

    def test_schematic_pad_count_mismatch(self):
        schematic = {'components': [
            {'designator': 'U1', 'pins': [{'number': '1'}, {'number': '2'}]},
            {'designator': 'C1', 'pins': [{'number': '1'}, {'number': '2'}]},
            {'designator': 'J1', 'pins': [{'number': '1'}, {'number': '2'}]},
            {'designator': 'U2', 'pins': [{'number': '1'}]},
        ]}
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(), schematic=schematic))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(checks['schematic.pad_counts']['status'], 'fail')
        self.assertEqual(
            checks['schematic.pad_counts']['objects']['mismatches'][0]['designator'],
            'U1')

    def test_missing_intent_sections_are_unmeasured(self):
        # Explicit compiled constraints make the hard checks pass while no
        # intent exists, so only the optional intent sections are missing.
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=None,
            constraints=ready_constraints()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(code, 1)
        for check_id in ('intent.ep', 'intent.connectors', 'intent.rf',
                         'intent.sensors', 'power.audit'):
            self.assertEqual(checks[check_id]['status'], 'unmeasured', check_id)
            self.assertEqual(checks[check_id]['severity'], 'advisory', check_id)
        not_checked = {item['check'] for item in report['not_checked']}
        for check_id in ('intent.ep', 'intent.connectors', 'intent.rf',
                         'intent.sensors', 'power.audit'):
            self.assertIn(check_id, not_checked)

    def test_plan_without_primitive_ids_resolves_from_dump(self):
        plan = {'placements': placement_rows()}
        code, output = self.run_main(self.argv(
            plan=plan, intent=ready_intent()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'ready')
        self.assertEqual(checks['plan.primitive_ids']['status'], 'pass')
        self.assertEqual(
            len(checks['plan.primitive_ids']['objects']['resolved_from_dump']), 4)
        self.assertEqual(checks['plan.base_hash']['status'], 'skipped')

    def test_plan_designator_not_measured_blocks(self):
        plan = ready_plan()
        plan['placements'].append({'designator': 'U9', 'x': 100, 'y': 100,
                                   'rotation': 0, 'layer': 1})
        code, output = self.run_main(self.argv(
            plan=plan, intent=ready_intent()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(code, 2)
        self.assertEqual(checks['plan.designators_measured']['status'], 'fail')
        self.assertEqual(
            checks['plan.designators_measured']['objects']['unknown'], ['U9'])

    def test_partial_plan_validates_only_listed_parts(self):
        plan = {
            'schema': 'design-engine-pcb-placement-plan/v1',
            'base_semantic_sha256': 'hash-ready',
            'primitive_ids': {'U1': 'pid-u1'},
            'placements': [{'designator': 'U1', 'x': 500, 'y': 500,
                            'rotation': 0, 'layer': 1}],
        }
        full_code, full_output = self.run_main(self.argv(
            plan=plan, intent=ready_intent()))
        full_code, full_report = self.report(full_code, full_output)
        self.assertEqual(full_report['status'], 'blocked')
        self.assertEqual(full_code, 2)
        self.assertEqual(
            self.by_id(full_report)['placement.hard']['status'], 'fail')

        part_code, part_output = self.run_main(self.argv(
            plan=plan, intent=ready_intent(), partial=True))
        part_code, part_report = self.report(part_code, part_output)
        self.assertEqual(part_report['status'], 'ready', part_report['checks'])
        self.assertEqual(part_code, 0)
        self.assertEqual(
            self.by_id(part_report)['placement.hard']['status'], 'pass')

    def test_ep_without_explicit_pad_is_unmeasured(self):
        intent = ready_intent()
        intent['components'] = [{'designator': 'U1', 'ep': True}]
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=intent))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(checks['intent.ep']['status'], 'unmeasured')
        self.assertEqual(checks['intent.ep']['severity'], 'advisory')
        self.assertIn('explicit', checks['intent.ep']['message'])
        self.assertEqual(report['status'], 'review')

    def test_ep_declared_pad_missing_fails(self):
        intent = ready_intent()
        intent['components'] = [{'designator': 'U1', 'ep': True,
                                 'ep_pad': 'EP-9'}]
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=intent))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(checks['intent.ep']['status'], 'fail')
        self.assertEqual(checks['intent.ep']['objects']['failed'][0]
                         ['missing_pads'], ['EP-9'])

    def test_project_and_document_identity(self):
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(),
            project='demo-project', doc='doc-uuid-demo'))
        code, report = self.report(code, output)
        self.assertEqual(report['status'], 'ready')
        checks = self.by_id(report)
        self.assertEqual(checks['dump.project_identity']['status'], 'pass')
        self.assertEqual(checks['dump.document_identity']['status'], 'pass')

        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(),
            project='another-project', doc='pcb'))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(checks['dump.project_identity']['status'], 'fail')
        self.assertEqual(checks['dump.project_identity']['severity'], 'hard')

        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(),
            project='demo-project', doc='not-this-document'))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(checks['dump.document_identity']['status'], 'fail')
        self.assertEqual(checks['dump.document_identity']['severity'], 'hard')

    # -- audits ---------------------------------------------------------

    def test_fabrication_hard_finding_is_advisory_review(self):
        dump = ready_dump()
        dump['copper']['vias'] = [{
            'primitiveId': 'via-bad', 'net': '', 'x': 900, 'y': 900,
            'diameter': 24, 'holeDiameter': 12,
        }]
        code, output = self.run_main(self.argv(
            dump=dump, plan=ready_plan(dump), intent=ready_intent()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(checks['fabrication.audit']['status'], 'fail')
        self.assertEqual(checks['fabrication.audit']['severity'], 'advisory')
        codes = {item['code'] for item in
                 checks['fabrication.audit']['objects']['hard_findings']}
        self.assertIn('netless_via', codes)
        self.assertEqual(report['counts']['hard_fail'], 0)

    def test_power_unmeasured_is_review(self):
        dump = ready_dump()
        dump['copper']['lines'] = []
        code, output = self.run_main(self.argv(
            dump=dump, plan=ready_plan(dump), intent=ready_intent()))
        code, report = self.report(code, output)
        checks = self.by_id(report)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(checks['power.audit']['status'], 'fail')
        self.assertEqual(checks['power.audit']['severity'], 'advisory')
        self.assertEqual(checks['power.audit']['objects']['status'], 'review')

    # -- CLI contract ---------------------------------------------------

    def test_malformed_input_exits_2(self):
        bad_path = self.write('bad.json', '{not json')
        code, output = self.run_main(['--dump', bad_path, '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['status'], 'invalid_input')

        bad_plan = self.write('bad-plan.json', {'placements': 'nope'})
        dump_path = self.write('board.json', ready_dump())
        code, output = self.run_main(['--dump', dump_path, '--plan', bad_plan,
                                      '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['status'], 'invalid_input')

        missing_xy = self.write('bad-plan2.json', {
            'placements': [{'designator': 'U1', 'x': 500}]})
        code, output = self.run_main(['--dump', dump_path, '--plan', missing_xy,
                                      '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['status'], 'invalid_input')

        code, output = self.run_main(['--dump', str(self.dir / 'absent.json'),
                                      '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['status'], 'invalid_input')

    def test_cli_json_and_out(self):
        out_path = str(self.dir / 'preflight-report.json')
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(), out=out_path))
        self.assertEqual(code, 0)
        stdout_report = json.loads(output)
        file_report = json.loads(Path(out_path).read_text(encoding='utf-8'))
        self.assertEqual(stdout_report['schema'], file_report['schema'])
        self.assertEqual(stdout_report['status'], 'ready')
        self.assertEqual(file_report['status'], 'ready')
        self.assertEqual([item['id'] for item in stdout_report['checks']],
                         [item['id'] for item in file_report['checks']])

    def test_human_output_without_json(self):
        code, output = self.run_main(self.argv(
            plan=ready_plan(), intent=ready_intent(), json_out=False))
        self.assertEqual(code, 0)
        self.assertIn('pcb preflight: ready', output)
        self.assertNotIn('"schema"', output)

    def test_preflight_makes_no_eda_calls(self):
        with mock.patch.object(pcb_cli, 'run',
                               side_effect=AssertionError('EDA call attempted')), \
                mock.patch.object(pcb_cli.subprocess, 'run',
                                  side_effect=AssertionError('subprocess attempted')):
            code, output = self.run_main(self.argv(
                plan=ready_plan(), intent=ready_intent()))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
