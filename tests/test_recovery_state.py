"""Guard: design-state recovery fields and the "read state first" rule.

PocketCam X1 was compressed 2-3 times and every resume relied on the summary
alone.  These checks pin the recovery fields and the SKILL rule that says a
resume must re-read design-state (and treat a missing/inconsistent state as
BLOCKED rather than inferring from the summary).
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'

EXAMPLE = SKILL / 'assets' / 'design-state.example.json'
SKILL_MD = SKILL / 'SKILL.md'

RECOVERY_KEYS = ('open_nets', 'last_journal', 'last_backup',
                 'rejected_options', 'next_action')


class RecoveryStateGuard(unittest.TestCase):
    def test_example_carries_recovery_fields(self):
        data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        recovery = data.get('recovery')
        self.assertIsInstance(recovery, dict)
        for key in RECOVERY_KEYS:
            self.assertIn(key, recovery)
        self.assertIsInstance(recovery['open_nets'], list)
        self.assertIsInstance(recovery['rejected_options'], list)
        self.assertEqual(data['project']['stage'], 'G0')

    def test_skill_documents_read_state_first_rule(self):
        body = SKILL_MD.read_text(encoding='utf-8')
        self.assertIn('上下文压缩', body)
        self.assertIn('project.stage', body)
        self.assertIn('按 `BLOCKED` 处理', body)
        self.assertIn('不凭对话摘要推断', body)

    def test_example_carries_rule_relaxation_and_pour_fields(self):
        data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        self.assertIn('drc_rules_before', data['stackup'])
        self.assertEqual(data['routing']['drc_rules'], {})
        self.assertEqual(data['routing']['rule_relaxations'], [])
        self.assertIs(data['routing']['pour_rebuilt'], False)


if __name__ == '__main__':
    unittest.main()
