import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'design-hardware' / 'scripts' / 'netlist_diff.py'
spec = importlib.util.spec_from_file_location('netlist_diff', SCRIPT)
netlist_diff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(netlist_diff)

FIXTURE = '''PROTEL NETLIST 2.0
[
DESIGNATOR
R1
FOOTPRINT
R0603
PARTTYPE
10k
Add into BOM
yes
Convert to PCB
yes
Supplier Part
C25804
Manufacturer Part
0603WAF1002T5E
Unique ID
u1
*
]
[
DESIGNATOR
C1
FOOTPRINT
C0603
PARTTYPE
100nF
Add into BOM
yes
Convert to PCB
yes
Supplier Part
C1591
Manufacturer Part
CL10B104KB8NNNC
Unique ID
u2
*
]
(
5V
R1-1 10k-1 Passive
C1-1 100nF-1 Passive
)
(
GND
R1-2 10k-2 Passive
C1-2 100nF-2 Passive
)
'''


class Parsing(unittest.TestCase):
    def test_parses_components_and_nets(self):
        parsed = netlist_diff.parse_protel(FIXTURE)
        self.assertEqual(set(parsed['components']), {'R1', 'C1'})
        self.assertEqual(parsed['nets']['5V'], {('R1', '1'), ('C1', '1')})
        self.assertEqual(parsed['nets']['GND'], {('R1', '2'), ('C1', '2')})

    def test_duplicate_designator_is_invalid(self):
        text = FIXTURE.replace('DESIGNATOR\nC1', 'DESIGNATOR\nR1')
        with self.assertRaises(netlist_diff.NetlistError):
            netlist_diff.parse_protel(text)

    def test_pin_on_two_nets_is_invalid(self):
        text = FIXTURE.replace('C1-1 100nF-1 Passive\n',
                               'C1-1 100nF-1 Passive\nC1-2 100nF-2 Passive\n')
        with self.assertRaises(netlist_diff.NetlistError):
            netlist_diff.parse_protel(text)

    def test_empty_and_plain_text_are_invalid(self):
        for text in ('', '   \n\n', 'not a netlist\n'):
            with self.subTest(text=text), self.assertRaises(netlist_diff.NetlistError):
                netlist_diff.parse_protel(text)

    def test_truncated_blocks_are_invalid(self):
        cases = [
            FIXTURE.split('\n*\n', 1)[0] + '\n',  # component: no closing *
            FIXTURE.rsplit('\n)\n', 1)[0] + '\n',  # net: no closing )
        ]
        for text in cases:
            with self.subTest(text=text[-40:]), self.assertRaises(netlist_diff.NetlistError):
                netlist_diff.parse_protel(text)

    def test_missing_required_component_fields_are_invalid(self):
        values = {'PARTTYPE': '10k', 'FOOTPRINT': 'R0603'}
        for field, value in values.items():
            text = FIXTURE.replace(f'{field}\n{value}\n', f'{field}\n\n', 1)
            with self.subTest(field=field), self.assertRaises(netlist_diff.NetlistError):
                netlist_diff.parse_protel(text)

    def test_unknown_component_in_net_is_invalid(self):
        text = FIXTURE.replace('C1-1 100nF-1 Passive\n', 'C9-1 100nF-1 Passive\n')
        with self.assertRaises(netlist_diff.NetlistError):
            netlist_diff.parse_protel(text)

    def test_duplicate_net_name_is_invalid(self):
        text = FIXTURE.replace('(\nGND\n', '(\n5V\n', 1)
        with self.assertRaises(netlist_diff.NetlistError):
            netlist_diff.parse_protel(text)


class Comparison(unittest.TestCase):
    def compare(self, before, after, **kwargs):
        return netlist_diff.compare(netlist_diff.parse_protel(before),
                                    netlist_diff.parse_protel(after), **kwargs)

    def test_identical_netlists_match(self):
        result = self.compare(FIXTURE, FIXTURE)
        self.assertTrue(result['match'])
        self.assertEqual(result['differences'], [])

    def test_pin_moved_to_another_net_is_a_difference(self):
        after = FIXTURE.replace('(\nGND\nR1-2 10k-2 Passive\nC1-2 100nF-2 Passive\n)',
                                '(\nGND\nR1-2 10k-2 Passive\n)')
        result = self.compare(FIXTURE, after)
        self.assertFalse(result['match'])
        self.assertIn('pin_removed', {d['kind'] for d in result['differences']})

    def test_net_rename_is_blocking_by_default(self):
        after = FIXTURE.replace('5V\n', 'VCC\n')
        result = self.compare(FIXTURE, after)
        self.assertFalse(result['match'])
        self.assertIn('net_renamed', {d['kind'] for d in result['differences']})
        allowed = self.compare(FIXTURE, after, allow_net_renames=True)
        self.assertTrue(allowed['match'])

    def test_component_field_change_is_a_difference(self):
        after = FIXTURE.replace('PARTTYPE\n10k', 'PARTTYPE\n22k')
        result = self.compare(FIXTURE, after)
        self.assertFalse(result['match'])
        self.assertTrue(any(d['kind'] == 'component_field' and d['field'] == 'PARTTYPE'
                            for d in result['differences']))

    def test_component_added_is_a_difference(self):
        extra = ('[\nDESIGNATOR\nR2\nFOOTPRINT\nR0603\nPARTTYPE\n10k\n'
                 'Add into BOM\nyes\nConvert to PCB\nyes\nSupplier Part\nC25804\n'
                 'Manufacturer Part\n0603WAF1002T5E\nUnique ID\nu3\n*\n]\n')
        result = self.compare(FIXTURE, FIXTURE + extra)
        self.assertFalse(result['match'])
        self.assertIn('component_added', {d['kind'] for d in result['differences']})


class RealFixture(unittest.TestCase):
    def test_f1_netlist_parses(self):
        path = ROOT / 'docs' / 'evidence' / 'f1-2026-10-22' / 'schematic.net'
        if not path.exists():
            self.skipTest('F1 evidence netlist not present')
        parsed = netlist_diff.parse_protel(path.read_text(encoding='utf-8', errors='replace'))
        self.assertEqual(len(parsed['components']), 16)
        self.assertEqual(len(parsed['nets']), 11)
        self.assertEqual(len(netlist_diff._pin_map(parsed)), 45)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            before = Path(temp) / 'before.net'
            after = Path(temp) / 'after.net'
            before.write_text(FIXTURE, encoding='utf-8')
            after.write_text(FIXTURE, encoding='utf-8')
            self.assertEqual(netlist_diff.main([str(before), str(after)]), 0)
            after.write_text(FIXTURE.replace('PARTTYPE\n10k', 'PARTTYPE\n22k'), encoding='utf-8')
            self.assertEqual(netlist_diff.main([str(before), str(after)]), 1)
            missing = Path(temp) / 'missing.net'
            self.assertEqual(netlist_diff.main([str(missing), str(after)]), 2)


if __name__ == '__main__':
    unittest.main()
