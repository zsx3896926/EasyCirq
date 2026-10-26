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
                           make_dump, sha256, stage_map, touch,  # noqa: E402
                           write_json)


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


if __name__ == '__main__':
    unittest.main()
