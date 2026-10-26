"""Tests for the offline PCB gate (PG1..PG8).

No EDA binary is used.  Fixtures are either synthetic temp files or copies of
the real round-9 case evidence; mtimes are explicit so freshness is deterministic.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
REAL_MCU = ROOT / 'design-hardware' / 'cases' / 'mcu-i2c-s3-2026-10-26'
REAL_PHOTO = ROOT / 'design-hardware' / 'cases' / 'photo-led-pcb-2026-10-26'
REAL_KEY_NETS = ROOT / 'docs' / 'round10' / 'baseline' / 'key-nets-b2.json'

sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('pcb_gate', SCRIPTS / 'pcb_gate.py')
pcb_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pcb_gate)

PAST = 1700000000.0          # 2023-11-14, older than the real dump captures
PAST_AFTER = PAST + 10.0
FRESH = 1800000000.0         # 2027-01-15, newer than the real dump captures


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace('+00:00', 'Z')


def touch(path, epoch):
    os.utime(str(path), (epoch, epoch))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def png_bytes(width=800, height=600):
    return (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' +
            struct.pack('>II', width, height) + b'\x08\x06\x00\x00\x00' +
            b'\x00\x00\x00\x00')


def dump_component(designator, x, device='fixture'):
    return {
        'designator': designator,
        'x': x, 'y': 20, 'rotation': 0, 'layer': 1,
        'bbox': {'minX': x - 10, 'minY': 10, 'maxX': x + 10, 'maxY': 30},
        'primitiveId': 'pid-' + designator,
        'uniqueId': 'uid-' + designator,
        'device': device,
        'pads': [{
            'padNumber': '1', 'net': '+3V3', 'x': x, 'y': 20,
            'width': 2, 'height': 2, 'layer': 1,
            'primitiveId': 'pid-%s-1' % designator,
        }],
    }


def make_dump(captured=PAST, semantic='hash-1', c1_x=60, extra=False):
    components = [dump_component('U1', 20), dump_component('C1', c1_x)]
    if extra:
        components.append(dump_component('C2', 90))
    return {
        'components': components,
        'outline': {
            'points': [[0, 0], [200, 0], [200, 200], [0, 200]],
            'bbox': {'minX': 0, 'minY': 0, 'maxX': 200, 'maxY': 200},
            'source': 'test fixture',
        },
        'copper': {'lines': [], 'arcs': [], 'vias': [], 'pours': [],
                   'poured': [], 'regions': [], 'fills': []},
        'copperLayers': 2,
        'rules': {'clearanceMil': 6},
        'silk': [],
        'capturedAt': iso(captured),
        'semanticSha256': semantic,
        'capture': {
            'projectUuid': 'project-fixture',
            'projectName': 'fixture',
            'documentUuid': 'doc-fixture',
            'completedAt': iso(captured),
        },
        'availability': {
            'components': 'available', 'copper': 'available',
            'outline': 'available', 'silk': 'available', 'rules': 'available',
        },
    }


def constraints_payload():
    return {
        'schema': 'design-engine-pcb-constraints/v1',
        'status': 'compiled',
        'constraints': [{
            'id': 'FIX-U1', 'type': 'fixed', 'severity': 'hard',
            'source': 'test fixture', 'unit': 'mil',
            'designator': 'U1', 'x': 20, 'y': 20, 'rotation': 0, 'layer': 1,
        }],
        'conflicts': [],
        'unknown': [],
        'counts': {'constraints': 1, 'hard': 1, 'preferred': 0,
                   'conflicts': 0, 'unknown': 0},
    }


def placement_payload():
    return {
        'schema': 'design-engine-pcb-placement/v1',
        'status': 'pass', 'hard_ok': True, 'findings': [],
        'constraints': [{'constraint_id': 'FIX-U1', 'type': 'fixed',
                         'status': 'pass', 'severity': 'hard'}],
        'counts': {'findings': 0, 'hard_findings': 0, 'constraint_rows': 1,
                   'hard_failed': 0, 'hard_unmeasured': 0},
    }


def lint_payload(score=68, crossings=8, tight=0, coverage=True):
    return {
        'schema': 'design-engine-pcb-lint/v1',
        'score': score, 'crossings': crossings, 'componentCount': 2,
        'overlap': 0, 'offBoard': 0, 'short': 0, 'tight': tight,
        'silkOverPad': 0,
        'coverage': {'complete': coverage},
    }


def drc_payload():
    return {'passed': True, 'total': 0, 'counts': {}, 'violations': [],
            'nativeResult': {'passed': True, 'violations': []}}


def check_payload(warnings=0):
    findings = []
    if warnings:
        findings = [{
            'type': 'decap-too-far', 'level': 'WARN',
            'designator': 'C1', 'net': '+3V3',
            'message': 'decoupling cap is too far from the pin',
        }]
    return {
        'passed': warnings == 0,
        'summary': {'errors': 0, 'warnings': warnings, 'infos': 0,
                    'total': warnings},
        'findings': findings,
    }


def netpath_payload():
    return {
        'schema': 'design-engine-pcb-netpath/v1',
        'rows': [{
            'from': 'U1.1', 'to': 'C1.1', 'net': '+3V3',
            'status': 'connected', 'path_kind': 'exact-centerline',
            'length_mil': 40, 'vias': 0, 'layers': [1],
        }],
    }


def key_nets_payload():
    return {
        'schema': 'design-engine-pcb-key-nets/v1',
        'nets': [{'net': '+3V3', 'from': 'U1.1', 'to': 'C1.1'}],
    }


def sch_pcb_payload(status='match', mismatches=None):
    return {
        'status': status,
        'schematic_components': 2,
        'pcb_components': 2,
        'pins': 2,
        'mismatches': mismatches or [],
    }


def save_reload_payload():
    return {
        'schema': 'design-engine-pcb-diff/v1',
        'status': 'match',
        'identity_changes': [], 'geometry_changes': [],
        'copper_changes': [], 'unrelated_changes': [],
        'counts': {'identity': 0, 'geometry': 0, 'copper': 0, 'unrelated': 0},
    }


def write_artifact_set(evidence_dir, mtime=FRESH):
    top = evidence_dir / 'pcb-final-top.png'
    bottom = evidence_dir / 'pcb-final-bottom.png'
    top.write_bytes(png_bytes(800, 600))
    bottom.write_bytes(png_bytes(800, 600))
    svg = write_text(evidence_dir / 'pcb-final-actual.svg',
                     '<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    bom = write_text(evidence_dir / 'BOM.csv',
                     'Designator,Quantity,Supplier Part\nU1,1,C1\nC1,1,C2\n')
    archive = evidence_dir / 'fixture-final.epro2'
    with zipfile.ZipFile(str(archive), 'w') as handle:
        handle.writestr('project.json', '{}')
    for path in (top, bottom, svg, bom, archive):
        touch(path, mtime)
    return {'image_top': top, 'image_bottom': bottom, 'actual_svg': svg,
            'bom': bom, 'archive': archive}


class CaseBuilder:
    """A complete passing evidence set that individual tests then perturb."""

    def __init__(self, root):
        self.root = Path(root)
        self.case = self.root / 'case'
        self.ev = self.case / 'evidence'
        self.ev.mkdir(parents=True)
        self.out = self.root / 'report.json'
        self.write_base()

    def write(self, name, payload, mtime=FRESH):
        path = write_json(self.ev / name, payload)
        touch(path, mtime)
        return path

    def write_base(self):
        self.dump_before = self.ev / 'pcb-dump-final.json'
        self.dump_after = self.ev / 'pcb-dump-after-reload.json'
        write_json(self.dump_before, make_dump(captured=PAST))
        write_json(self.dump_after, make_dump(captured=PAST_AFTER))
        touch(self.dump_before, PAST)
        touch(self.dump_after, PAST_AFTER)

        self.constraints = self.write('constraints.json', constraints_payload())
        self.placement = self.write('placement-check-final.json', placement_payload())
        self.lint = self.write('pcb-layout-lint.json', lint_payload())
        self.drc = self.write('pcb-drc-final.json', drc_payload())
        self.check = self.write('pcb-check-final.json', check_payload())
        self.netpath = self.write('netpath-key-connections.json', netpath_payload())
        self.key_nets = self.write('key-nets.json', key_nets_payload())
        self.sch_pcb = self.write('sch-pcb-compare.json', sch_pcb_payload())
        self.save_reload = self.write('save-reload-diff.json', save_reload_payload())
        self.artifacts = write_artifact_set(self.ev)

    def rewrite_dump(self, which, payload, mtime):
        path = self.dump_before if which == 'before' else self.dump_after
        write_json(path, payload)
        touch(path, mtime)
        return path


def make_args(case, **overrides):
    values = dict(
        case=str(case), profile='full', baseline_manifest=None, key_nets=None,
        warn_disposition=None, dump_before=None, dump_after=None,
        constraints=None, plan=None, intent=None, check=None, drc=None,
        lint=None, netpath=None, sch_pcb=None, sch=None, images=None,
        edit_scope=None, file=[], role=[], out=None, json=True,
        strict_advisory=False,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def stage_map(report):
    return {stage['id']: stage for stage in report['stages']}


def finding_codes(stage):
    return [finding.get('code') for finding in stage['findings']]


def baseline_manifest(path, evidence_dir, archive_name='fixture-final.epro2'):
    roles = ('image_top', 'image_bottom', 'actual_svg', 'bom', 'archive')
    names = {
        'image_top': 'pcb-final-top.png',
        'image_bottom': 'pcb-final-bottom.png',
        'actual_svg': 'pcb-final-actual.svg',
        'bom': 'BOM.csv',
        'archive': archive_name,
    }
    artifacts = [{'role': role, 'sha256': sha256(evidence_dir / names[role])}
                 for role in roles]
    return write_json(path, {'schema': 'design-engine-pcb-case/v1',
                             'artifacts': artifacts})


class BaseGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.builder = CaseBuilder(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class FullPassTests(BaseGateTests):
    def test_full_profile_passes(self):
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['schema'], 'design-engine-pcb-gate/v1')
        self.assertEqual(report['status'], 'pass')
        self.assertEqual([stage['status'] for stage in report['stages']],
                         ['pass'] * 8)
        self.assertTrue(report['next_command'])
        self.assertIsInstance(report['not_checked'], list)
        self.assertEqual(report['counts']['pass'], 8)
        self.assertEqual(pcb_gate.EXIT_CODES[report['status']], 0)

    def test_pass_with_baseline_manifest_match(self):
        manifest = baseline_manifest(self.builder.root / 'baseline.json',
                                     self.builder.ev)
        report = pcb_gate.evaluate(make_args(
            self.builder.case, baseline_manifest=str(manifest)))
        self.assertEqual(report['status'], 'pass')
        stage = stage_map(report)['PG8_delivery']
        self.assertEqual(stage['metrics']['baseline']['status'], 'match')

    def test_cli_pass_exit_zero_and_writes_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = pcb_gate.main([
                '--case', str(self.builder.case),
                '--out', str(self.builder.out), '--json',
            ])
        self.assertEqual(rc, 0)
        payload = json.loads(self.builder.out.read_text(encoding='utf-8'))
        self.assertEqual(payload['status'], 'pass')

    def test_default_out_is_case_gate_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = pcb_gate.main(['--case', str(self.builder.case)])
        self.assertEqual(rc, 0)
        default = self.builder.case / 'gate-report.json'
        self.assertTrue(default.is_file())
        payload = json.loads(default.read_text(encoding='utf-8'))
        self.assertEqual(payload['schema'], 'design-engine-pcb-gate/v1')


class MissingAndStaleEvidenceTests(BaseGateTests):
    def test_missing_lint_blocks_full_profile(self):
        self.builder.lint.unlink()
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['status'], 'blocked')
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'blocked')
        self.assertTrue(stage['required'])
        self.assertIn('missing_evidence', finding_codes(stage))
        self.assertEqual(pcb_gate.EXIT_CODES[report['status']], 1)

    def test_stale_drc_fails(self):
        touch(self.builder.drc, PAST - 1000)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['status'], 'fail')
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('STALE_EVIDENCE', finding_codes(stage))

    def test_stale_lint_fails(self):
        touch(self.builder.lint, PAST - 1000)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('STALE_EVIDENCE', finding_codes(stage))

    def test_missing_dump_after_blocks_save_reload(self):
        self.builder.dump_after.unlink()
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['status'], 'blocked')
        stage = stage_map(report)['PG7_save_reload']
        self.assertEqual(stage['status'], 'blocked')
        self.assertIn('dump_after', stage['metrics']['missing_roles'])

    def test_missing_archive_blocks_delivery(self):
        self.builder.artifacts['archive'].unlink()
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['status'], 'blocked')
        stage = stage_map(report)['PG8_delivery']
        self.assertEqual(stage['status'], 'blocked')
        self.assertIn('archive', stage['metrics']['missing_roles'])


class PlacementAndLintQualityTests(BaseGateTests):
    def test_placement_without_constraint_rows_fails(self):
        payload = placement_payload()
        payload['counts']['constraint_rows'] = 0
        payload['constraints'] = []
        self.builder.write('placement-check-final.json', payload)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG1_placement']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('placement_no_constraints', finding_codes(stage))

    def test_constraints_with_unknown_objects_fail(self):
        payload = constraints_payload()
        payload['unknown'] = [{'id': 'FIX-X1', 'object': 'X1',
                               'reason': 'unknown designator'}]
        self.builder.write('constraints.json', payload)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG1_placement']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('constraint_unknown_objects', finding_codes(stage))

    def test_lint_coverage_incomplete_fails(self):
        self.builder.write('pcb-layout-lint.json',
                           lint_payload(coverage=False))
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('lint_coverage_incomplete', finding_codes(stage))

    def test_lint_score_and_crossings_thresholds(self):
        self.builder.write('pcb-layout-lint.json',
                           lint_payload(score=59, crossings=9))
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'fail')
        codes = finding_codes(stage)
        self.assertIn('lint_score', codes)
        self.assertIn('lint_crossings', codes)

    def test_real_lint_null_detail_arrays_are_a_measurement(self):
        source = (ROOT / 'docs' / 'round10' / 'regression' / 'liveA'
                  / 'evidence' / 'pcb-layout-lint.json')
        if not source.is_file():
            self.skipTest('real lint capture not present')
        target = self.builder.ev / 'pcb-layout-lint.json'
        shutil.copyfile(str(source), str(target))
        touch(target, FRESH)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'pass',
                         stage['findings'])
        self.assertEqual(stage['metrics']['overlap'], 0)
        self.assertEqual(stage['metrics']['off_board'], 0)

    def test_malformed_evidence_shape_fails_closed(self):
        # Valid JSON, wrong field type: the shared parser must not crash the
        # whole gate; the stage fails with an explicit stage_error.
        payload = lint_payload()
        payload['coverage'] = True
        self.builder.write('pcb-layout-lint.json', payload)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('lint_diagnostics', finding_codes(stage))
        self.assertIn('lint_coverage_incomplete', finding_codes(stage))
        self.assertEqual(report['status'], 'fail')


class WarnDispositionTests(BaseGateTests):
    def test_warn_without_disposition_blocks(self):
        self.builder.write('pcb-check-final.json', check_payload(warnings=1))
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG4_check']
        self.assertEqual(stage['status'], 'blocked')
        self.assertEqual(stage['metrics']['warnings'], 1)
        self.assertIn('missing_warn_disposition', finding_codes(stage))
        self.assertEqual(report['status'], 'blocked')

    def test_warn_with_valid_disposition_passes(self):
        check = self.builder.write('pcb-check-final.json', check_payload(warnings=1))
        disposition = {
            'schema': 'design-engine-pcb-warn-disposition/v1',
            'source': {'sha256': sha256(check), 'path': str(check)},
            'findings': [{
                'type': 'decap-too-far', 'designator': 'C1', 'net': '+3V3',
                'disposition': 'waived',
                'reason': 'test board accepts the decap distance',
            }],
        }
        disposition_path = self.builder.write('warn-disposition.json', disposition)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG4_check']
        self.assertEqual(stage['status'], 'pass')
        self.assertTrue(stage['metrics']['disposition_present'])
        self.assertTrue(any(item['role'] == 'warn_disposition'
                            for item in stage['evidence']))
        self.assertEqual(report['status'], 'pass')
        self.assertTrue(disposition_path.is_file())

    def test_disposition_with_wrong_source_sha_fails(self):
        check = self.builder.write('pcb-check-final.json', check_payload(warnings=1))
        disposition = {
            'schema': 'design-engine-pcb-warn-disposition/v1',
            'source': {'sha256': '0' * 64},
            'findings': [{
                'type': 'decap-too-far', 'designator': 'C1', 'net': '+3V3',
                'disposition': 'waived', 'reason': 'reason for the waiver',
            }],
        }
        self.builder.write('warn-disposition.json', disposition)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG4_check']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('invalid_warn_disposition', finding_codes(stage))

    def test_info_findings_require_disposition_too(self):
        info_check = {
            'passed': False,
            'summary': {'errors': 0, 'warnings': 0, 'infos': 1, 'total': 1},
            'findings': [{'type': 'fiducial-missing', 'level': 'INFO',
                          'message': 'add three fiducials before SMT'}],
        }
        self.builder.write('pcb-check-final.json', info_check)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG4_check']
        self.assertEqual(stage['metrics']['infos'], 1)
        self.assertEqual(stage['status'], 'blocked')
        self.assertIn('missing_warn_disposition', finding_codes(stage))

        disposition = {
            'schema': 'design-engine-pcb-warn-disposition/v1',
            'source': {'sha256': sha256(self.builder.ev / 'pcb-check-final.json')},
            'findings': [],
        }
        self.builder.write('warn-disposition.json', disposition)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG4_check']
        self.assertEqual(stage['status'], 'blocked')
        self.assertIn('missing_warn_disposition', finding_codes(stage))

    def test_real_check_warns_require_disposition(self):
        source = REAL_MCU / 'evidence' / 'pcb-check-final.json'
        target = self.builder.ev / 'pcb-check-final.json'
        shutil.copyfile(str(source), str(target))
        touch(target, FRESH)
        payload = json.loads(target.read_text(encoding='utf-8-sig'))
        expected_warnings = sum(
            1 for finding in payload.get('findings') or []
            if str(finding.get('level')).upper() == 'WARN')
        self.assertGreater(expected_warnings, 0)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG4_check']
        self.assertEqual(stage['metrics']['warnings'], expected_warnings)
        self.assertEqual(stage['status'], 'blocked')
        self.assertIn('missing_warn_disposition', finding_codes(stage))


class ReconciliationAndPersistenceTests(BaseGateTests):
    def test_sch_pcb_mismatch_fails(self):
        write_json(self.builder.sch_pcb, sch_pcb_payload(
            status='mismatch',
            mismatches=[{'designator': 'U1', 'pin': '1',
                         'schematic_net': '+3V3', 'pcb_net': 'GND',
                         'status': 'mismatch'}]))
        touch(self.builder.sch_pcb, FRESH)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG6_sch_pcb']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('sch_pcb_mismatch', finding_codes(stage))
        self.assertIn('sch_pcb_pin_mismatch', finding_codes(stage))

    def test_sch_pcb_computed_from_sch_and_final_dump(self):
        sch = self.builder.write('sch-read.json', {
            'components': [
                {'designator': 'U1',
                 'pins': [{'number': '1', 'net': '+3V3'}]},
                {'designator': 'C1',
                 'pins': [{'number': '1', 'net': '+3V3'}]},
            ],
        })
        report = pcb_gate.evaluate(make_args(
            self.builder.case, sch=str(sch)))
        stage = stage_map(report)['PG6_sch_pcb']
        self.assertEqual(stage['status'], 'pass')
        self.assertEqual(stage['metrics']['source'],
                         'computed_from_sch_and_final_dump')
        self.assertEqual(stage['metrics']['pins'], 2)

    def test_discovered_sch_does_not_override_sch_pcb_without_flag(self):
        sch = self.builder.write('sch-read.json', {
            'components': [
                {'designator': 'U1',
                 'pins': [{'number': '1', 'net': 'GND'}]},
                {'designator': 'C1',
                 'pins': [{'number': '1', 'net': '+3V3'}]},
            ],
        })
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG6_sch_pcb']
        self.assertEqual(stage['status'], 'pass')
        self.assertEqual(stage['metrics']['source'], 'sch_pcb_evidence')
        explicit = pcb_gate.evaluate(make_args(
            self.builder.case, sch=str(sch)))
        self.assertEqual(stage_map(explicit)['PG6_sch_pcb']['status'], 'fail')

    def test_save_reload_pure_change_fails(self):
        after = make_dump(captured=PAST_AFTER, semantic='hash-2', c1_x=70)
        self.builder.rewrite_dump('after', after, PAST_AFTER)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG7_save_reload']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('save_reload_changed', finding_codes(stage))

    def test_save_reload_edit_scope_unrelated_change_fails(self):
        after = make_dump(captured=PAST_AFTER, semantic='hash-2', c1_x=70)
        self.builder.rewrite_dump('after', after, PAST_AFTER)
        scope = self.builder.write('edit-scope.json', {'designators': ['U1']})
        report = pcb_gate.evaluate(make_args(
            self.builder.case, edit_scope=str(scope)))
        stage = stage_map(report)['PG7_save_reload']
        self.assertEqual(stage['status'], 'fail')
        self.assertEqual(stage['metrics']['mode'], 'edit')
        self.assertIn('save_reload_unrelated', finding_codes(stage))

    def test_save_reload_edit_scope_in_scope_change_passes(self):
        after = make_dump(captured=PAST_AFTER, semantic='hash-2', c1_x=60)
        after['components'][0]['x'] = 25  # U1 moves inside the declared scope
        self.builder.rewrite_dump('after', after, PAST_AFTER)
        scope = self.builder.write('edit-scope.json', {'designators': ['U1']})
        report = pcb_gate.evaluate(make_args(
            self.builder.case, edit_scope=str(scope)))
        stage = stage_map(report)['PG7_save_reload']
        self.assertEqual(stage['status'], 'pass')
        self.assertEqual(stage['metrics']['diff_status'], 'changed')


class DeliveryTests(BaseGateTests):
    def test_baseline_plain_role_mapping_passes(self):
        names = {
            'image_top': 'pcb-final-top.png',
            'image_bottom': 'pcb-final-bottom.png',
            'actual_svg': 'pcb-final-actual.svg',
            'bom': 'BOM.csv',
            'archive': 'fixture-final.epro2',
        }
        mapping = {role: sha256(self.builder.ev / name)
                   for role, name in names.items()}
        path = write_json(self.builder.root / 'baseline-map.json', mapping)
        report = pcb_gate.evaluate(make_args(
            self.builder.case, baseline_manifest=str(path)))
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(
            stage_map(report)['PG8_delivery']['metrics']['baseline']['status'],
            'match')

    def test_baseline_file_name_roles_match(self):
        names = ('pcb-final-top.png', 'pcb-final-bottom.png',
                 'pcb-final-actual.svg', 'BOM.csv', 'fixture-final.epro2')
        mapping = {name: sha256(self.builder.ev / name) for name in names}
        path = write_json(self.builder.root / 'baseline-names.json', mapping)
        report = pcb_gate.evaluate(make_args(
            self.builder.case, baseline_manifest=str(path)))
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(
            stage_map(report)['PG8_delivery']['metrics']['baseline']['status'],
            'match')

    def test_images_dir_override(self):
        images = self.builder.root / 'images'
        images.mkdir()
        for role in ('image_top', 'image_bottom', 'actual_svg'):
            source = self.builder.artifacts[role]
            target = images / source.name
            shutil.copyfile(str(source), str(target))
            touch(target, FRESH)
            source.unlink()
        report = pcb_gate.evaluate(make_args(
            self.builder.case, images=str(images)))
        stage = stage_map(report)['PG8_delivery']
        self.assertEqual(stage['status'], 'pass')
        self.assertGreaterEqual(
            sum(1 for item in stage['evidence'] if 'images' in item['path']), 3)

    def test_baseline_image_change_fails(self):
        manifest = baseline_manifest(self.builder.root / 'baseline.json',
                                     self.builder.ev)
        top = self.builder.artifacts['image_top']
        top.write_bytes(png_bytes(1024, 768))
        touch(top, FRESH)
        report = pcb_gate.evaluate(make_args(
            self.builder.case, baseline_manifest=str(manifest)))
        stage = stage_map(report)['PG8_delivery']
        self.assertEqual(stage['status'], 'fail')
        codes = finding_codes(stage)
        self.assertIn('baseline_changed', codes)
        changed = stage['metrics']['baseline']['changed']
        self.assertEqual([item['role'] for item in changed], ['image_top'])

    def test_invalid_png_fails(self):
        top = self.builder.artifacts['image_top']
        top.write_bytes(b'not a png at all')
        touch(top, FRESH)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG8_delivery']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('invalid_png', finding_codes(stage))

    def test_stale_image_is_advisory_until_strict(self):
        touch(self.builder.artifacts['image_top'], PAST - 500)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG8_delivery']
        self.assertEqual(stage['status'], 'pass')
        self.assertIn('stale_image', finding_codes(stage))
        strict = pcb_gate.evaluate(make_args(
            self.builder.case, strict_advisory=True))
        self.assertEqual(stage_map(strict)['PG8_delivery']['status'], 'fail')
        self.assertEqual(strict['status'], 'fail')


class ProfileAndOverrideTests(BaseGateTests):
    def test_regression_optional_stages_not_run_is_pass_with_gaps(self):
        for path in (self.builder.lint, self.builder.constraints,
                     self.builder.placement):
            path.unlink()
        report = pcb_gate.evaluate(make_args(
            self.builder.case, profile='regression'))
        stages = stage_map(report)
        for stage_id in ('PG1_placement', 'PG2_layout', 'PG4_check',
                         'PG5_netpath'):
            self.assertEqual(stages[stage_id]['status'], 'not_run')
            self.assertFalse(stages[stage_id]['required'])
        self.assertEqual(stages['PG3_drc']['status'], 'pass')
        self.assertEqual(stages['PG7_save_reload']['status'], 'pass')
        self.assertEqual(report['status'], 'pass_with_gaps')
        self.assertEqual(report['counts']['optional_not_run'], 4)
        self.assertEqual(pcb_gate.EXIT_CODES[report['status']], 0)

    def test_explicit_role_override_wins(self):
        alt = write_json(self.builder.ev / 'alt-lint.json',
                         lint_payload(score=10, crossings=20))
        touch(alt, FRESH)
        report = pcb_gate.evaluate(make_args(
            self.builder.case, file=['lint=alt-lint.json']))
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'fail')
        self.assertEqual(stage['metrics']['score'], 10)
        self.assertTrue(stage['evidence'][0]['path'].endswith('alt-lint.json'))
        self.assertIn('lint_score', finding_codes(stage))

    def test_role_alias_override(self):
        alt = write_json(self.builder.ev / 'alt-drc.json',
                         {'passed': False, 'total': 1,
                          'counts': {'connection': 1},
                          'violations': [{'rule': 'Connection Error'}]})
        touch(alt, FRESH)
        report = pcb_gate.evaluate(make_args(
            self.builder.case, role=['drc=alt-drc.json']))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('drc_failed', finding_codes(stage))

    def test_bare_path_override_infers_role(self):
        alt = write_json(self.builder.ev / 'pcb-layout-lint-alt.json',
                         lint_payload(score=10))
        touch(alt, FRESH)
        report = pcb_gate.evaluate(make_args(
            self.builder.case, file=[str(alt)]))
        stage = stage_map(report)['PG2_layout']
        self.assertEqual(stage['status'], 'fail')
        self.assertEqual(stage['metrics']['score'], 10)

    def test_strict_advisory_escalates_lint_warning(self):
        self.builder.write('pcb-layout-lint.json', lint_payload(tight=2))
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(stage_map(report)['PG2_layout']['status'], 'pass')
        strict = pcb_gate.evaluate(make_args(
            self.builder.case, strict_advisory=True))
        self.assertEqual(stage_map(strict)['PG2_layout']['status'], 'fail')
        self.assertEqual(strict['status'], 'fail')


class InputErrorTests(BaseGateTests):
    def test_malformed_explicit_json_exits_two(self):
        bad = write_text(self.builder.ev / 'bad.json', '{not valid json')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = pcb_gate.main([
                '--case', str(self.builder.case),
                '--drc', str(bad), '--out', str(self.builder.out),
            ])
        self.assertEqual(rc, 2)
        self.assertIn('error:', stderr.getvalue())

    def test_malformed_only_discovered_json_exits_two(self):
        self.builder.drc.unlink()
        broken = write_text(self.builder.ev / 'pcb-drc-broken.json',
                            '{not valid json')
        touch(broken, FRESH)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = pcb_gate.main([
                '--case', str(self.builder.case),
                '--out', str(self.builder.out),
            ])
        self.assertEqual(rc, 2)
        self.assertIn('no parseable JSON candidate', stderr.getvalue())

    def test_malformed_newest_candidate_is_skipped_for_a_valid_one(self):
        broken = write_text(self.builder.ev / 'pcb-drc-broken.json',
                            '{not valid json')
        touch(broken, FRESH + 100)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'pass')
        self.assertTrue(stage['evidence'][0]['path'].endswith('pcb-drc-final.json'))
        self.assertEqual(report['status'], 'pass')

    def test_missing_explicit_evidence_exits_two(self):
        rc = pcb_gate.main([
            '--case', str(self.builder.case),
            '--lint', str(self.builder.root / 'does-not-exist.json'),
            '--out', str(self.builder.out),
        ])
        self.assertEqual(rc, 2)

    def test_missing_case_exits_two(self):
        rc = pcb_gate.main([
            '--case', str(self.builder.root / 'no-such-case'),
            '--out', str(self.builder.out),
        ])
        self.assertEqual(rc, 2)

    def test_empty_edit_scope_exits_two(self):
        scope = self.builder.write('edit-scope.json', {'designators': []})
        rc = pcb_gate.main([
            '--case', str(self.builder.case),
            '--edit-scope', str(scope), '--out', str(self.builder.out),
        ])
        self.assertEqual(rc, 2)


class RealBoardATests(unittest.TestCase):
    """Integration test over copies of the real photo-led (board A) evidence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.case = self.root / 'case'
        self.ev = self.case / 'evidence'
        self.ev.mkdir(parents=True)
        self.copy_real_evidence()
        self.write_synthetic_checks()

    def tearDown(self):
        self.tmp.cleanup()

    def copy_real_evidence(self):
        source = REAL_PHOTO / 'evidence'
        names = [
            'constraints.json', 'placement-check-final.json',
            'pcb-dump-final.json', 'pcb-dump-after-reload.json',
            'pcb-drc-final.json', 'netpath-key-connections.json',
            'sch-pcb-compare.json', 'pcb-final-top.png',
            'pcb-final-bottom.png', 'pcb-final-actual.svg', 'BOM.csv',
            'photo-led-pcb-final.epro2',
        ]
        for name in names:
            shutil.copyfile(str(source / name), str(self.ev / name))
            if name == 'pcb-dump-final.json':
                touch(self.ev / name, PAST)
            elif name == 'pcb-dump-after-reload.json':
                touch(self.ev / name, PAST_AFTER)
            else:
                touch(self.ev / name, FRESH)
        netpath = json.loads((self.ev / 'netpath-key-connections.json').read_text(
            encoding='utf-8-sig'))
        rows = netpath.get('rows') or []
        self.assertGreater(len(rows), 0)
        nets = [{'net': row['net'], 'from': row['from'], 'to': row['to']}
                for row in rows]
        key_nets = write_json(self.ev / 'key-nets.json', {'nets': nets})
        touch(key_nets, FRESH)

    def write_synthetic_checks(self):
        dump = json.loads((self.ev / 'pcb-dump-final.json').read_text(
            encoding='utf-8-sig'))
        lint = lint_payload(score=80, crossings=5)
        lint['componentCount'] = len(dump.get('components') or [])
        lint_path = write_json(self.ev / 'pcb-layout-lint.json', lint)
        check_path = write_json(self.ev / 'pcb-check-final.json', check_payload())
        for path in (lint_path, check_path):
            touch(path, FRESH)

    def test_real_board_a_full_profile_passes(self):
        report = pcb_gate.evaluate(make_args(self.case))
        self.assertEqual(report['status'], 'pass',
                         json.dumps([(s['id'], s['status'], s['findings'])
                                     for s in report['stages']], indent=2))
        stages = stage_map(report)
        placement = json.loads(
            (self.ev / 'placement-check-final.json').read_text(
                encoding='utf-8-sig'))
        self.assertEqual(stages['PG1_placement']['metrics']['constraint_rows'],
                         placement['counts']['constraint_rows'])
        key_nets = json.loads((self.ev / 'key-nets.json').read_text(
            encoding='utf-8-sig'))
        self.assertEqual(stages['PG5_netpath']['metrics']['connected'],
                         len(key_nets['nets']))
        dump = json.loads((self.ev / 'pcb-dump-final.json').read_text(
            encoding='utf-8-sig'))
        self.assertEqual(stages['PG6_sch_pcb']['metrics']['pcb_components'],
                         len(dump.get('components') or []))
        self.assertEqual(stages['PG7_save_reload']['metrics']['diff_status'],
                         'match')
        self.assertEqual(stages['PG8_delivery']['status'], 'pass')


class RealEvidenceTests(unittest.TestCase):
    """Integration tests over copies of the real mcu-i2c board-B evidence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.case = self.root / 'case'
        self.ev = self.case / 'evidence'
        self.ev.mkdir(parents=True)
        self.copy_real_evidence()
        self.write_synthetic_checks()
        self.out = self.root / 'report.json'

    def tearDown(self):
        self.tmp.cleanup()

    def copy_real_evidence(self):
        source = REAL_MCU / 'evidence'
        names = [
            'pcb-dump-final.json', 'pcb-dump-after-reload.json',
            'pcb-drc-final.json', 'netpath-key-connections.json',
            'sch-pcb-compare.json', 'pcb-final-top.png',
            'pcb-final-bottom.png', 'pcb-final-actual.svg', 'BOM.csv',
            'boardB-final.epro2', 'sch-connectivity.json',
        ]
        for name in names:
            shutil.copyfile(str(source / name), str(self.ev / name))
        shutil.copyfile(str(REAL_KEY_NETS), str(self.ev / 'key-nets.json'))
        for name in names + ['key-nets.json']:
            path = self.ev / name
            if name == 'pcb-dump-final.json':
                touch(path, PAST)
            elif name == 'pcb-dump-after-reload.json':
                touch(path, PAST_AFTER)
            else:
                touch(path, FRESH)

    def write_synthetic_checks(self):
        for name, payload in (
                ('constraints.json', constraints_payload()),
                ('placement-check-final.json', placement_payload()),
                ('pcb-layout-lint.json', lint_payload()),
                ('pcb-check-final.json', check_payload())):
            path = write_json(self.ev / name, payload)
            touch(path, FRESH)

    def test_real_evidence_full_profile_passes(self):
        manifest = baseline_manifest(self.root / 'baseline.json', self.ev,
                                     archive_name='boardB-final.epro2')
        report = pcb_gate.evaluate(make_args(
            self.case, baseline_manifest=str(manifest)))
        self.assertEqual(report['status'], 'pass',
                         json.dumps([(s['id'], s['status'], s['findings'])
                                     for s in report['stages']], indent=2))
        stages = stage_map(report)
        key_nets = json.loads((self.ev / 'key-nets.json').read_text(
            encoding='utf-8-sig'))
        expected_nets = key_nets.get('nets') or key_nets.get('key_nets') or []
        self.assertGreater(len(expected_nets), 0)
        self.assertEqual(stages['PG5_netpath']['metrics']['required'],
                         len(expected_nets))
        self.assertEqual(stages['PG5_netpath']['metrics']['connected'],
                         len(expected_nets))
        dump = json.loads((self.ev / 'pcb-dump-final.json').read_text(
            encoding='utf-8-sig'))
        expected_components = len(dump.get('components') or [])
        self.assertEqual(stages['PG6_sch_pcb']['metrics']['pcb_components'],
                         expected_components)
        self.assertGreater(stages['PG6_sch_pcb']['metrics']['pins'], 0)
        self.assertEqual(stages['PG7_save_reload']['metrics']['diff_status'],
                         'match')
        self.assertEqual(stages['PG8_delivery']['metrics']['baseline']['status'],
                         'match')

    def test_real_sch_connectivity_computes_match(self):
        dump = json.loads((self.ev / 'pcb-dump-final.json').read_text(
            encoding='utf-8-sig'))
        report = pcb_gate.evaluate(make_args(
            self.case, sch=str(self.ev / 'sch-connectivity.json')))
        stage = stage_map(report)['PG6_sch_pcb']
        self.assertEqual(stage['status'], 'pass')
        self.assertEqual(stage['metrics']['source'],
                         'computed_from_sch_and_final_dump')
        self.assertEqual(stage['metrics']['schematic_components'],
                         len(dump.get('components') or []))
        self.assertGreater(stage['metrics']['pins'], 0)

    def test_real_case_cli_writes_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = pcb_gate.main([
                '--case', str(self.case), '--out', str(self.out), '--json',
            ])
        self.assertEqual(rc, 0)
        payload = json.loads(self.out.read_text(encoding='utf-8'))
        self.assertEqual(payload['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
