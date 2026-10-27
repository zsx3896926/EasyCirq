"""Provenance tests for the offline PCB gate.

The gate must not accept a copy of old evidence just because its mtime was
refreshed, must refuse artifacts that name a different project, and must not
silently choose between two conflicting candidates.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
TESTS = ROOT / 'tests'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import pcb_gate  # noqa: E402
from test_pcb_gate import (CaseBuilder, FRESH, PAST, iso, make_args,
                           make_dump, placement_payload, sha256, stage_map,
                           touch, write_json)  # noqa: E402


def write_manifest(case, entries):
    artifacts = []
    for entry in entries:
        role = entry['role']
        path = entry['path']
        item = {
            'role': role,
            'path': str(Path(path).relative_to(case)).replace('\\', '/'),
            'sha256': sha256(path),
        }
        item.update({key: value for key, value in entry.items()
                     if key not in ('role', 'path')})
        artifacts.append(item)
    return write_json(case / 'manifest.json', {
        'schema': 'design-engine-pcb-case/v1',
        'artifacts': artifacts,
    })


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.builder = CaseBuilder(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def drc_entry(self, **overrides):
        entry = {
            'role': 'pcb-drc',
            'path': str(self.builder.drc),
            'source_dump_sha256': sha256(self.builder.dump_after),
            'produced_at': iso(FRESH),
            'run_after_final_reload': True,
        }
        entry.update(overrides)
        return entry

    def test_manifest_timestamp_beats_touched_mtime(self):
        # The file is touched to look fresh, but the manifest records that it
        # was produced before the final dump.
        touch(self.builder.drc, FRESH)
        write_manifest(self.builder.case, [
            self.drc_entry(produced_at=iso(PAST - 1000)),
        ])
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('STALE_EVIDENCE',
                      [finding.get('code') for finding in stage['findings']])

    def test_inferred_mtime_is_not_a_recorded_production_time(self):
        evidence = pcb_gate.Evidence(
            'drc', self.builder.drc, {'capturedAt': iso(PAST)},
            manifest_entry={'produced_at': iso(FRESH),
                            'source_binding': 'inferred_mtime'})
        moment, basis = pcb_gate._evidence_time_with_basis(evidence)
        self.assertEqual(basis, 'payload_capture')
        self.assertEqual(pcb_gate._iso(moment), iso(PAST))

    def test_crlf_normalized_manifest_hash_is_accepted(self):
        declared = __import__('hashlib').sha256(
            self.builder.drc.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        write_manifest(self.builder.case, [self.drc_entry(sha256=declared)])
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'pass')
        self.assertEqual(stage['metrics']['evidence_binding']['drc']['error'],
                         None)

    def test_manifest_sha_mismatch_fails_binding(self):
        manifest = write_manifest(self.builder.case, [self.drc_entry()])
        # Replace the bytes after the manifest was written.
        self.builder.write('pcb-drc-final.json', {
            'passed': True, 'total': 0, 'counts': {}, 'violations': [],
        }, mtime=FRESH)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('EVIDENCE_BINDING',
                      [finding.get('code') for finding in stage['findings']])
        self.assertEqual(stage['metrics']['evidence_binding']['drc']['error'],
                         'manifest_sha256_mismatch')

    def test_source_dump_change_fails_binding(self):
        write_manifest(self.builder.case, [
            self.drc_entry(source_dump_sha256='0' * 64),
        ])
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertEqual(stage['metrics']['evidence_binding']['drc']['error'],
                         'source_dump_changed')

    def test_project_identity_mix_is_refused_without_manifest(self):
        payload = json.loads(self.builder.drc.read_text(encoding='utf-8'))
        payload['capture'] = {'projectUuid': 'another-project',
                              'documentUuid': 'another-doc'}
        self.builder.write('pcb-drc-final.json', payload, mtime=FRESH)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertEqual(stage['metrics']['evidence_binding']['drc']['error'],
                         'project_identity_mismatch')

    def test_project_matches_but_pcb_document_differs_is_refused(self):
        payload = json.loads(self.builder.drc.read_text(encoding='utf-8'))
        payload['capture'] = {'projectUuid': 'project-fixture',
                              'documentUuid': 'another-pcb-document'}
        self.builder.write('pcb-drc-final.json', payload, mtime=FRESH)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertEqual(stage['metrics']['evidence_binding']['drc']['error'],
                         'document_identity_mismatch')

    def test_two_projects_in_one_directory_are_not_silently_mixed(self):
        original = json.loads(self.builder.drc.read_text(encoding='utf-8'))
        original['capture'] = {'projectUuid': 'project-fixture',
                               'documentUuid': 'doc-fixture'}
        self.builder.write('pcb-drc-final.json', original, mtime=FRESH)
        other = dict(original)
        other['capture'] = {'projectUuid': 'another-project',
                            'documentUuid': 'another-doc'}
        other_path = write_json(self.builder.ev / 'pcb-drc-other.json', other)
        touch(other_path, FRESH + 100)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        codes = [finding.get('code') for finding in stage['findings']]
        self.assertIn('EVIDENCE_IDENTITY_CONFLICT', codes)

    def test_two_identical_candidates_are_reported_but_are_not_a_conflict(self):
        copy = write_json(self.builder.ev / 'pcb-drc-copy.json',
                          json.loads(self.builder.drc.read_text(encoding='utf-8')))
        touch(copy, FRESH)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'pass')
        self.assertEqual(len(stage['evidence'][0]['alternatives']), 1)
        self.assertNotIn('EVIDENCE_AMBIGUOUS',
                         [finding.get('code') for finding in stage['findings']])

    def test_manifest_artifact_outside_role_globs_is_still_used(self):
        native = self.builder.case / 'native'
        native.mkdir()
        target = native / 'drc.json'
        target.write_bytes(self.builder.drc.read_bytes())
        write_manifest(self.builder.case, [{
            'role': 'pcb-drc', 'path': str(target),
            'source_dump_sha256': sha256(self.builder.dump_after),
            'produced_at': iso(FRESH), 'run_after_final_reload': True,
        }])
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'pass', stage['findings'])
        self.assertTrue(stage['evidence'][0]['path'].endswith('native/drc.json')
                        or 'native' in stage['evidence'][0]['path'])

    def test_ambiguous_manifest_role_does_not_fall_back_to_discovery(self):
        alt = self.builder.ev / 'pcb-drc-alt.json'
        alt.write_text(self.builder.drc.read_text(encoding='utf-8'),
                       encoding='utf-8')
        write_manifest(self.builder.case, [
            self.drc_entry(),
            {'role': 'pcb-drc', 'path': str(alt),
             'source_dump_sha256': sha256(self.builder.dump_after),
             'produced_at': iso(FRESH), 'run_after_final_reload': True},
        ])
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertEqual(stage['metrics']['evidence_binding']['drc']['error'],
                         'manifest_role_ambiguous')

    def test_manifest_missing_artifact_does_not_fall_back(self):
        manifest = write_manifest(self.builder.case, [self.drc_entry()])
        # Keep another valid DRC file as a plausible fallback.
        fallback = write_json(self.builder.ev / 'pcb-drc-final.json', {
            'passed': True, 'total': 0, 'counts': {}, 'violations': [],
        })
        touch(fallback, FRESH)
        declared = json.loads(manifest.read_text(encoding='utf-8'))
        declared['artifacts'][0]['path'] = 'evidence/does-not-exist.json'
        write_json(manifest, declared)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = stage_map(report)['PG3_drc']
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('EVIDENCE_BINDING',
                      [finding.get('code') for finding in stage['findings']])

    def _check_payload(self):
        return json.loads(self.builder.check.read_text(encoding='utf-8'))

    def _write_check_variant(self, name, **changes):
        payload = self._check_payload()
        payload.update(changes)
        path = self.builder.write(name, payload, mtime=FRESH + 10)
        return path

    def _pg4(self, report):
        return stage_map(report)['PG4_check']

    def test_placement_check_filename_cannot_shadow_dfm_check(self):
        # Regression: *pcb*check*.json also matches placement-check files.
        self.builder.write('pcb-placement-check-final.json',
                           placement_payload(), mtime=FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['status'], 'pass')
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'pass')
        selected = [e['path'] for e in stage['evidence']
                    if e.get('role') == 'check']
        self.assertTrue(selected)
        self.assertTrue(all(path.endswith('pcb-check-final.json')
                            for path in selected), selected)

    def test_empty_summary_candidate_blocks_instead_of_falling_back(self):
        # A newer, final-named but invalid check must not disappear and let the
        # older clean report pass silently.
        self.builder.write('pcb-check-final-empty.json', {
            'passed': True, 'summary': {}, 'findings': [],
            'trackCount': 2, 'padCount': 4,
        }, mtime=FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('EVIDENCE_CANDIDATE_REJECTED',
                      [finding.get('code') for finding in stage['findings']])
        self.assertEqual(
            stage['metrics']['evidence_binding']['check']['rejected_candidates'], 1)

    def test_contradictory_check_candidate_blocks_instead_of_falling_back(self):
        bad = self._check_payload()
        bad['summary'] = {'errors': 0, 'warnings': 0, 'infos': 0,
                          'total': 1, 'danglingEnds': 0}
        bad['findings'] = [{
            'type': 'power-not-poured', 'level': 'WARN',
            'net': '+5V', 'message': 'contradictory but itemized WARN',
        }]
        self.builder.write('pcb-check-final-contradictory.json', bad,
                           mtime=FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('EVIDENCE_CANDIDATE_REJECTED',
                      [finding.get('code') for finding in stage['findings']])

    def test_multiple_valid_check_candidates_without_binding_are_ambiguous(self):
        alternate = self._check_payload()
        alternate['summary'] = {'errors': 0, 'warnings': 1, 'infos': 0,
                                'total': 1, 'powerNotPoured': 1}
        alternate['findings'] = [{
            'type': 'power-not-poured', 'level': 'WARN',
            'net': '+5V', 'message': 'alternative DFM report',
        }]
        alternate['passed'] = False
        self.builder.write('pcb-check-alternate.json', alternate,
                           mtime=FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('EVIDENCE_AMBIGUOUS',
                      [finding.get('code') for finding in stage['findings']])
        self.assertEqual(stage['metrics']['evidence_binding']['check']['conflict'],
                         'multiple_candidates')

    def test_identical_check_copies_are_not_ambiguous(self):
        self.builder.write('pcb-check-copy.json', self._check_payload(),
                           mtime=FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'pass')
        self.assertNotIn('EVIDENCE_AMBIGUOUS',
                         [finding.get('code') for finding in stage['findings']])

    def test_placement_with_counters_cannot_spoof_check(self):
        payload = placement_payload()
        payload.update({
            'summary': {'errors': 0, 'warnings': 0, 'infos': 0,
                        'total': 0, 'danglingEnds': 0},
            'trackCount': 2, 'viaCount': 0, 'padCount': 4,
            'findings': [],
        })
        self.builder.write('pcb-placement-check-final.json', payload,
                           mtime=FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'pass')
        self.assertTrue(all(e['path'].endswith('pcb-check-final.json')
                            for e in stage['evidence']
                            if e.get('role') == 'check'))

    def test_path_only_manifest_cannot_downgrade_check_ambiguity(self):
        alternate = self._check_payload()
        alternate['summary'] = {'errors': 0, 'warnings': 1, 'infos': 0,
                                'total': 1, 'powerNotPoured': 1}
        alternate['findings'] = [{
            'type': 'power-not-poured', 'level': 'WARN',
            'net': '+5V', 'message': 'alternative DFM report',
        }]
        alternate['passed'] = False
        self.builder.write('pcb-check-alternate.json', alternate,
                           mtime=FRESH + 10)
        # Deliberately no sha256/produced_at: path-only is not a verified bind.
        write_json(self.builder.case / 'manifest.json', {
            'schema': 'design-engine-pcb-case/v1',
            'artifacts': [{
                'role': 'pcb-check',
                'path': 'evidence/pcb-check-final.json',
            }],
        })
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'fail')
        self.assertIn('EVIDENCE_AMBIGUOUS',
                      [finding.get('code') for finding in stage['findings']])
        self.assertFalse(
            stage['metrics']['evidence_binding']['check']['binding_verified'])

    def test_same_check_content_different_format_is_not_ambiguous(self):
        payload = self._check_payload()
        path = self.builder.ev / 'pcb-check-copy-formatted.json'
        path.write_text(json.dumps(payload, sort_keys=True,
                                   separators=(',', ':')), encoding='utf-8')
        touch(path, FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'pass')
        self.assertNotIn('EVIDENCE_AMBIGUOUS',
                         [finding.get('code') for finding in stage['findings']])

    def test_regression_profile_does_not_turn_not_run_into_ambiguity_fail(self):
        alternate = self._check_payload()
        alternate['summary'] = {'errors': 0, 'warnings': 1, 'infos': 0,
                                'total': 1, 'powerNotPoured': 1}
        alternate['findings'] = [{
            'type': 'power-not-poured', 'level': 'WARN',
            'net': '+5V', 'message': 'alternative DFM report',
        }]
        alternate['passed'] = False
        self.builder.write('pcb-check-alternate.json', alternate,
                           mtime=FRESH + 10)
        report = pcb_gate.evaluate(make_args(self.builder.case,
                                             profile='regression'))
        self.assertNotEqual(report['status'], 'fail')
        self.assertEqual(stage_map(report)['PG4_check']['status'], 'not_run')

    def test_manifest_placement_check_role_is_not_misread_as_dfm(self):
        placement = self.builder.ev / 'pcb-placement-check-final.json'
        write_json(placement, placement_payload())
        touch(placement, FRESH)
        write_manifest(self.builder.case, [{
            'role': 'pcb-placement-check', 'path': str(placement),
        }])
        report = pcb_gate.evaluate(make_args(self.builder.case))
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(stage_map(report)['PG1_placement']['status'], 'pass')
        self.assertEqual(stage_map(report)['PG4_check']['status'], 'pass')

    def test_manifest_bound_check_with_differing_alternative_reports_advisory(self):
        alternate = self._check_payload()
        alternate['summary'] = {'errors': 0, 'warnings': 1, 'infos': 0,
                                'total': 1, 'powerNotPoured': 1}
        alternate['findings'] = [{
            'type': 'power-not-poured', 'level': 'WARN',
            'net': '+5V', 'message': 'alternative DFM report',
        }]
        alternate['passed'] = False
        alt_path = self.builder.write('pcb-check-alternate.json', alternate,
                                      mtime=FRESH + 10)
        write_manifest(self.builder.case, [{
            'role': 'pcb-check', 'path': str(self.builder.check),
            'source_dump_sha256': sha256(self.builder.dump_after),
            'produced_at': iso(FRESH), 'run_after_final_reload': True,
        }])
        report = pcb_gate.evaluate(make_args(self.builder.case))
        stage = self._pg4(report)
        self.assertEqual(stage['status'], 'pass')
        ambiguous = [finding for finding in stage['findings']
                     if finding.get('code') == 'EVIDENCE_AMBIGUOUS']
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].get('severity'), 'advisory')
        self.assertEqual(stage['metrics']['evidence_binding']['check']['conflict'],
                         'multiple_candidates')
        check_evidence = next(e for e in stage['evidence']
                              if e.get('role') == 'check')
        self.assertIn(str(alt_path),
                      [item['path'] for item in check_evidence.get('alternatives', [])])


if __name__ == '__main__':
    unittest.main()
