import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'design-hardware/scripts'))
import pin_net_intent_check as check


def intent():
    return {
        'components': {
            'U1': {'pins': {'1': 'GND', '2': 'TIMING', '8': '+5V'}},
            'R1': {'pins': {'1': '+5V', '2': 'DISCH'}},
            'C1': {'pins': {'positive': 'TIMING', 'negative': 'GND'},
                   'pinMap': {'positive': '1', 'negative': '2'}},
        },
        'nets': {
            'GND': ['U1.1', 'C1.negative'],
            '+5V': ['U1.8', 'R1.1'],
            'TIMING': ['U1.2', 'C1.positive'],
            'DISCH': ['R1.2'],
        },
    }


def read(net_names=None):
    names = net_names or {'GND': 'GND', '+5V': '+5V', 'TIMING': 'TIMING',
                          'DISCH': 'DISCH'}
    return {'components': [
        {'componentType': 'part', 'designator': 'U1', 'pins': [
            {'pinNumber': '1', 'net': names['GND']},
            {'pinNumber': '2', 'net': names['TIMING']},
            {'pinNumber': '8', 'net': names['+5V']}]},
        {'componentType': 'part', 'designator': 'R1', 'pins': [
            {'pinNumber': '1', 'net': names['+5V']},
            {'pinNumber': '2', 'net': names['DISCH']}]},
        {'componentType': 'part', 'designator': 'C1', 'pins': [
            {'pinNumber': '1', 'net': names['TIMING']},
            {'pinNumber': '2', 'net': names['GND']}]},
    ]}


class PinNetIntent(unittest.TestCase):
    def test_match_ignores_net_spelling(self):
        result = check.compare(intent(), read({'GND': '$1N1', '+5V': '$1N2',
                                               'TIMING': '$1N3', 'DISCH': '$1N4'}))
        self.assertEqual(result['status'], 'match')

    def test_sch_read_number_field_is_accepted(self):
        live = read()
        for component in live['components']:
            for pin in component['pins']:
                pin['number'] = pin.pop('pinNumber')
        self.assertEqual(check.compare(intent(), live)['status'], 'match')

    def test_missing_pin_mismatch(self):
        live = read()
        live['components'][0]['pins'][1]['net'] = 'OTHER'
        result = check.compare(intent(), live)
        self.assertEqual(result['status'], 'mismatch')
        codes = {finding['code'] for finding in result['findings']}
        self.assertIn('intent_net_mismatch', codes)

    def test_unexpected_live_net(self):
        live = read()
        live['components'][1]['pins'][0]['net'] = 'SPLIT'
        result = check.compare(intent(), live)
        self.assertIn('unexpected_live_net',
                      {finding['code'] for finding in result['findings']})

    def test_missing_function_mapping_is_invalid(self):
        data = intent()
        del data['components']['C1']['pinMap']
        with self.assertRaises(ValueError):
            check.compare(data, read())

    def test_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            a, b = folder / 'intent.json', folder / 'read.json'
            a.write_text(json.dumps(intent()), encoding='utf-8')
            b.write_text(json.dumps(read()), encoding='utf-8')
            script = ROOT / 'design-hardware/scripts/pin_net_intent_check.py'
            self.assertEqual(subprocess.run([sys.executable, str(script), str(a), str(b)],
                                            capture_output=True).returncode, 0)
            live = read()
            live['components'][1]['pins'][0]['net'] = 'SPLIT'
            b.write_text(json.dumps(live), encoding='utf-8')
            self.assertEqual(subprocess.run([sys.executable, str(script), str(a), str(b)],
                                            capture_output=True).returncode, 1)


if __name__ == '__main__':
    unittest.main()
