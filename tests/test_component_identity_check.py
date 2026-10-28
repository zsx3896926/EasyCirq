import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'easycirq/scripts'))
import component_identity_check as identity


def part(primitive='p1', designator='R1', device_uuid='dev-1',
         footprint='RES-0603', value='10k', pin_net='N1', add_to_pcb=True,
         unique_id='uid-1', component_uuid='comp-1'):
    return {
        'componentType': 'part', 'primitiveId': primitive,
        'uniqueId': unique_id,
        'component': {'libraryUuid': 'comp-lib', 'uuid': component_uuid},
        'device': {'libraryUuid': 'lib-1', 'uuid': device_uuid, 'name': 'Resistor'},
        'symbol': {'libraryUuid': 'sym-lib', 'uuid': 'sym-1', 'name': 'R'},
        'otherProperty': {
            'Footprint': footprint, 'Manufacturer Part': 'MPN-1',
            'Supplier Part': 'C1', 'LCSC Part Name': value,
            'Value': value, 'Description': 'resistor',
        },
        'pins': [{'pinNumber': '1', 'pinName': 'A', 'net': pin_net}],
        'addIntoBom': True, 'addIntoPcb': add_to_pcb,
    }


def doc(*pairs):
    components, attributes = [], []
    for item, designator in pairs:
        item = json.loads(json.dumps(item))
        item.pop('designator', None)
        components.append(item)
        attributes.append({'Key': 'Designator', 'Value': designator,
                           'ParentPrimitiveId': item['primitiveId']})
    return {'components': components,
            'pagePrimitives': {'attributes': attributes}}


def pcb(*items):
    return {'components': list(items)}


def pcb_part(designator='R1', footprint='RES-0603'):
    return {'designator': designator, 'footprint': footprint}


class IdentityTests(unittest.TestCase):
    def test_identical_schematic_passes_sch_only(self):
        result = identity.compare(doc((part(), 'R1')), doc((part(), 'R1')))
        self.assertEqual(result['status'], 'pass_sch_only')
        self.assertEqual(result['blocking_findings'], [])
        self.assertEqual(result['pcb_binding']['status'], 'not_run')
        self.assertFalse(result['electrical_verified'])

    def test_device_uuid_change_blocks(self):
        result = identity.compare(doc((part(), 'R1')),
                                  doc((part(device_uuid='dev-2'), 'R1')))
        self.assertEqual(result['status'], 'review_required')
        self.assertIn('device_identity_changed',
                      [finding['code'] for finding in result['blocking_findings']])

    def test_duplicate_pcb_designator_is_invalid(self):
        before = doc((part(), 'R1'))
        after = doc((part(), 'R1'))
        board = pcb(pcb_part('R1'), pcb_part('R1'))
        with self.assertRaises(ValueError):
            identity.compare(before, after, board)

    def test_footprint_change_blocks(self):
        result = identity.compare(doc((part(), 'R1')),
                                  doc((part(footprint='RES-0805'), 'R1')))
        self.assertIn('footprint_changed',
                      [finding['code'] for finding in result['blocking_findings']])

    def test_bom_value_change_blocks_with_key(self):
        result = identity.compare(doc((part(), 'R1')),
                                  doc((part(value='22k'), 'R1')))
        keys = {finding.get('key') for finding in result['blocking_findings']
                if finding['code'] == 'bom_attribute_changed'}
        self.assertEqual(keys, {'LCSC Part Name', 'Value'})

    def test_pin_name_change_blocks(self):
        moved = part()
        moved['pins'][0]['pinName'] = 'B'
        result = identity.compare(doc((part(), 'R1')), doc((moved, 'R1')))
        self.assertIn('pin_map_changed',
                      [finding['code'] for finding in result['blocking_findings']])

    def test_net_partition_change_blocks(self):
        result = identity.compare(
            doc((part('p1'), 'R1'), (part('p2', pin_net='N1'), 'R2')),
            doc((part('p1'), 'R1'), (part('p2', pin_net='N2'), 'R2')))
        self.assertIn('net_partition_changed',
                      [finding['code'] for finding in result['blocking_findings']])

    def test_net_rename_is_informational(self):
        before = doc((part(pin_net='$1N1'), 'R1'))
        after = doc((part(pin_net='OUT'), 'R1'))
        result = identity.compare(before, after)
        self.assertEqual(result['status'], 'pass_sch_only')
        finding = next(item for item in result['informational_findings']
                       if item['code'] == 'net_names_changed')
        self.assertEqual(finding['renames'][0]['before'], '$1N1')
        self.assertEqual(finding['renames'][0]['after'], 'OUT')

    def test_primitive_id_change_is_informational(self):
        result = identity.compare(doc((part('p1'), 'R1')),
                                  doc((part('p2'), 'R1')))
        self.assertEqual(result['status'], 'pass_sch_only')
        self.assertIn('primitive_id_changed',
                      [finding['code'] for finding in result['informational_findings']])

    def test_instance_unique_id_change_blocks(self):
        result = identity.compare(doc((part(), 'R1')),
                                  doc((part(unique_id='uid-2'), 'R1')))
        self.assertIn('instance_unique_id_changed',
                      [item['code'] for item in result['blocking_findings']])

    def test_instance_component_uuid_change_blocks(self):
        result = identity.compare(doc((part(), 'R1')),
                                  doc((part(component_uuid='comp-2'), 'R1')))
        self.assertIn('instance_component_uuid_changed',
                      [item['code'] for item in result['blocking_findings']])

    def test_instance_identity_missing_blocks(self):
        missing = part()
        missing.pop('uniqueId')
        result = identity.compare(doc((part(), 'R1')), doc((missing, 'R1')))
        self.assertIn('instance_identity_unavailable',
                      [item['code'] for item in result['blocking_findings']])

    def test_declared_bom_change_is_informational(self):
        expected = [{'designator': 'R1', 'key': 'Value', 'before': '10k',
                     'after': '22k', 'reason': 'customer-visible value update',
                     'evidence': 'BOM note / change request'}]
        changed = part(); changed['otherProperty']['Value'] = '22k'
        result = identity.compare(doc((part(), 'R1')), doc((changed, 'R1')),
                                  expected_changes=expected)
        self.assertEqual(result['status'], 'pass_sch_only')
        finding = next(item for item in result['informational_findings']
                       if item['code'] == 'expected_change')
        self.assertEqual(finding['key'], 'Value')
        self.assertEqual(finding['reason'], 'customer-visible value update')

    def test_unexpected_change_stays_blocking(self):
        expected = [{'designator': 'R1', 'key': 'Footprint', 'before': 'A',
                     'after': 'B', 'reason': 'r', 'evidence': 'e'}]
        changed = part(); changed['otherProperty']['Value'] = '22k'
        result = identity.compare(doc((part(), 'R1')), doc((changed, 'R1')),
                                  expected_changes=expected)
        self.assertIn('bom_attribute_changed',
                      [item['code'] for item in result['blocking_findings']])
        self.assertIn('expected_change_unused',
                      [item['code'] for item in result['informational_findings']])

    def test_declared_change_must_match_observed_values(self):
        expected = [{'designator': 'R1', 'key': 'Value', 'before': '10k',
                     'after': '33k', 'reason': 'r', 'evidence': 'e'}]
        changed = part(); changed['otherProperty']['Value'] = '22k'
        result = identity.compare(doc((part(), 'R1')), doc((changed, 'R1')),
                                  expected_changes=expected)
        self.assertIn('expected_change_mismatch',
                      [item['code'] for item in result['blocking_findings']])

    def test_declared_change_needs_reason_and_evidence(self):
        for missing in ('reason', 'evidence'):
            entry = {'designator': 'R1', 'key': 'Value', 'before': '10k',
                     'after': '22k', 'reason': 'r', 'evidence': 'e'}
            entry.pop(missing)
            with self.subTest(missing=missing):
                with self.assertRaises(ValueError):
                    changed = part(); changed['otherProperty']['Value'] = '22k'
                    identity.compare(doc((part(), 'R1')),
                                     doc((changed, 'R1')),
                                     expected_changes=[entry])

    def test_added_and_removed_parts_block(self):
        result = identity.compare(doc((part(), 'R1')),
                                  doc((part(), 'R1'), (part('p2'), 'R2')))
        self.assertIn('part_added', [item['code'] for item in result['blocking_findings']])
        result = identity.compare(doc((part(), 'R1'), (part('p2'), 'R2')),
                                  doc((part(), 'R1')))
        self.assertIn('part_removed', [item['code'] for item in result['blocking_findings']])

    def test_pcb_binding_pass(self):
        result = identity.compare(doc((part(), 'R1')), doc((part(), 'R1')),
                                  pcb(pcb_part()))
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['pcb_binding']['status'], 'checked')

    def test_pcb_missing_and_footprint_mismatch_block(self):
        result = identity.compare(doc((part(), 'R1')), doc((part(), 'R1')),
                                  pcb(pcb_part('R9')))
        self.assertIn('pcb_part_missing',
                      [item['code'] for item in result['blocking_findings']])
        result = identity.compare(doc((part(), 'R1')), doc((part(), 'R1')),
                                  pcb(pcb_part(footprint='RES-0805')))
        self.assertIn('pcb_footprint_mismatch',
                      [item['code'] for item in result['blocking_findings']])

    def test_pcb_exempt_part_is_not_required(self):
        result = identity.compare(doc((part(add_to_pcb=False), 'R1')),
                                  doc((part(add_to_pcb=False), 'R1')), pcb())
        self.assertEqual(result['blocking_findings'], [])

    def test_missing_designator_refuses(self):
        broken = doc((part(), 'R1'))
        broken['pagePrimitives']['attributes'] = []
        with self.assertRaises(ValueError):
            identity.compare(broken, doc((part(), 'R1')))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            before = folder / 'before.json'
            after = folder / 'after.json'
            before.write_text(json.dumps(doc((part(), 'R1'))), encoding='utf-8')
            after.write_text(json.dumps(doc((part(), 'R1'))), encoding='utf-8')
            script = ROOT / 'easycirq/scripts/component_identity_check.py'
            passed = subprocess.run([sys.executable, str(script), '--before', str(before),
                                     '--after', str(after)], capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            after.write_text(json.dumps(doc((part(device_uuid='dev-2'), 'R1'))),
                             encoding='utf-8')
            failed = subprocess.run([sys.executable, str(script), '--before', str(before),
                                     '--after', str(after)], capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)


if __name__ == '__main__':
    unittest.main()
