import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'easycirq/scripts/rc_settle_sim.py'
spec = importlib.util.spec_from_file_location('rcsim', SCRIPT)
rcsim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rcsim)


def run(**patch):
    data = dict(vin=3.3, r_source=1000, r_switch=100, c_ext=1e-9,
                c_sample=4e-12, t_close=0, t_end=20e-6, dt=1e-9,
                bits=12, vref=3.3)
    data.update(patch)
    return rcsim.simulate(**data)


class RcSimulation(unittest.TestCase):
    def test_default_settles_and_records_every_step(self):
        summary, rows = run()
        self.assertTrue(summary['simulation_executed'])
        self.assertFalse(summary['board_verified'])
        self.assertEqual(summary['steps'], 20000)
        self.assertEqual(len(rows), 20001)
        self.assertTrue(summary['settled_0p5LSB'])
        self.assertLess(summary['final_error_LSB'], .5)
        self.assertAlmostEqual(summary['final_v_b_V'], 3.3, places=6)
        self.assertTrue(summary['v_b_monotonic'])
        self.assertAlmostEqual(rows[0][1], 0.0)
        self.assertAlmostEqual(rows[0][2], 0.0)
        self.assertAlmostEqual(rows[0][3], 3.3)

    def test_slow_source_does_not_settle(self):
        summary, rows = run(r_source=10000, t_end=1.5e-6)
        self.assertFalse(summary['settled_0p5LSB'])
        self.assertGreater(summary['final_error_LSB'], .5)
        self.assertLess(summary['final_v_b_V'], 3.3)

    def test_sample_capacitor_holds_before_switch_closes(self):
        summary, rows = run(t_close=5e-6, t_end=10e-6)
        before = [r for r in rows if r[0] < 5e-6]
        self.assertTrue(before)
        self.assertTrue(all(r[2] == 0.0 for r in before))
        self.assertGreater(rows[-1][2], 0.0)
        self.assertTrue(summary['v_b_monotonic'])

    def test_invalid_inputs(self):
        cases = [dict(dt=0), dict(t_end=0), dict(t_close=-1),
                 dict(t_close=20e-6), dict(r_source=0), dict(c_ext=0),
                 dict(bits=0), dict(bits=13.5), dict(vin=float('nan'))]
        for patch in cases:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                run(**patch)

    def test_cli_writes_csv_and_reports_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'rc.csv'
            result = subprocess.run(
                [sys.executable, str(SCRIPT), '--t-end', '2e-6', '--dt', '1e-9',
                 '--out', str(out)],
                capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + (result.stderr or ''))
            payload = json.loads(result.stdout)
            self.assertTrue(payload['simulation_executed'])
            self.assertFalse(payload['board_verified'])
            self.assertTrue(out.is_file())
            self.assertEqual(out.read_text(encoding='utf-8').splitlines()[0],
                             'time_s,v_a_V,v_b_V,error_V,error_LSB')

    def test_cli_invalid_input_exit_2(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--dt', '0'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'invalid_input')


if __name__ == '__main__':
    unittest.main()
