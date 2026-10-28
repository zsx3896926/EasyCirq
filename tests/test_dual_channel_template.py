"""Regression for the reusable dual-channel switch/LED placement template."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
CASE = ROOT / 'easycirq' / 'cases' / 'dual-button-led-night-20261027' / 'negative-direct-move'
TEMPLATES = ROOT / 'easycirq' / 'assets' / 'pcb-placement-templates.json'


class DualChannelTemplateTests(unittest.TestCase):
    def test_template_binds_to_measured_accepted_baseline(self):
        data = json.loads(TEMPLATES.read_text(encoding='utf-8'))
        template = next(t for t in data['templates']
                        if t['id'] == 'dual-channel-switch-led')
        self.assertEqual(template['status'], 'offline-tested')
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / 'design_engine_cli.py'),
             'pcb-template-plan', '--dump', str(CASE / 'board-accepted-baseline.json'),
             '--template', 'dual-channel-switch-led',
             '--binding', str(CASE / 'binding.json'),
             '--anchor', '1200,350,0', '--json'],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        payload, _ = json.JSONDecoder().raw_decode(result.stdout)
        self.assertEqual(payload['status'], 'planned', payload.get('reasons'))
        poses = {item['designator']: (item['x'], item['y'], item['rotation'])
                 for item in payload['placements']}
        self.assertEqual(poses, {
            'SW1': (1200.0, 350.0, 0.0),
            'D3': (1195.09, 730.0, 180.0),
            'R2': (1200.0, 1000.0, 0.0),
            'SW2': (1600.0, 350.0, 0.0),
            'D4': (1595.09, 730.0, 180.0),
            'R3': (1600.0, 1000.0, 0.0),
        })


if __name__ == '__main__':
    unittest.main()
