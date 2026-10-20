import json
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'design-hardware'
sys.path.insert(0, str(SKILL / 'scripts'))
import netlist_check as netcheck
import sch_layout_check as layout


class ProjectAssets(unittest.TestCase):
    def test_p01_connection_table_is_valid_and_not_board_verified(self):
        path = SKILL / 'assets/projects/p01-connectivity.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        result = netcheck.check(data)
        self.assertIn(result['status'],
                      {'no_structural_issues', 'needs_review', 'blocked', 'incomplete'})
        self.assertFalse(result['board_verified'])
        self.assertFalse(result['coverage']['full_project_verified'])

    def test_p01_layout_draft_is_valid_and_not_electrically_verified(self):
        path = SKILL / 'assets/projects/p01-layout.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        result = layout.analyze(data)
        self.assertIn(result['status'],
                      {'no_candidates', 'candidates', 'incomplete'})
        self.assertFalse(result['electrical_verified'])
        self.assertFalse(result['visual_verified'])

    def test_p01_project_text_records_the_tool_status(self):
        text = (SKILL / 'references/projects/p01-low-power-wireless-sensor.md').read_text(
            encoding='utf-8')
        self.assertIn('netlist_check', text)
        self.assertIn('sch_layout_check', text)
        self.assertIn('离线规划', text)


if __name__ == '__main__':
    unittest.main()
