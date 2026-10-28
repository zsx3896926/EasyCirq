"""Guard: the PocketCam X1 routing/closure lessons must stay on the default path.

Loose keyword matching (synonyms allowed) so the rule is protected without
freezing exact prose.  See docs/toolchain-integration/pocketcam-x1-lessons.md.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'
LESSONS = ROOT / 'docs' / 'toolchain-integration' / 'pocketcam-x1-lessons.md'


def text(rel):
    path = SKILL / rel
    if not path.is_file():
        raise AssertionError('missing file: %s' % path)
    return path.read_text(encoding='utf-8')


def contains_any(body, alternatives):
    lowered = body.lower()
    return any(alternative.lower() in lowered for alternative in alternatives)


RULES = {
    'stitch-after-signals': {
        'files': ['assets/routing-plan.md', 'references/pcb-routing-strategy.md',
                  'SKILL.md'],
        'groups': [['缝合'], ['Connection 0']],
    },
    'autoroute-official-and-timeout': {
        'files': ['references/pcb-routing-strategy.md'],
        'groups': [['官方路由器'], ['--router'], ['超时'],
                   ['不保证无残留', '可能留下'], ['每批']],
    },
    'apply-copper-not-deduplicated': {
        'files': ['references/pcb-execution.md'],
        'groups': [['no-op 检测', '不去重'], ['几何比对', '按几何'],
                   ['--timeout'], ['mismatch'], ['primitiveId']],
    },
    'delete-granularity': {
        'files': ['references/pcb-execution.md'],
        'groups': [['track-delete'], ['via-delete'], ['只认器件']],
    },
    'pour-rebuild-before-drc': {
        'files': ['references/pcb-execution.md'],
        'groups': [['pour-rebuild'], ['假错误'], ['via-bond']],
    },
    'escape-and-diff-pair': {
        'files': ['references/pcb-routing-strategy.md'],
        'groups': [['escape-plan'], ['锁定'], ['全速'], ['决策记录']],
    },
    'dfm-closeout': {
        'files': ['assets/pcb-delivery-checklist.md'],
        'groups': [['antenna-keepout'], ['dangling-end'], ['track-delete']],
    },
    'export-fallback': {
        'files': ['assets/docs/manufacturing-package.md'],
        'groups': [['20 MiB'], ['OBJ'], ['GUI']],
    },
}


class ClosureLessonsOnDefaultPath(unittest.TestCase):
    def test_each_rule_is_present(self):
        for rule_id, spec in RULES.items():
            with self.subTest(rule=rule_id):
                for rel in spec['files']:
                    body = text(rel)
                    missing = [g for g in spec['groups'] if not contains_any(body, g)]
                    self.assertFalse(missing, '%s missing from %s: %s'
                                     % (rule_id, rel, missing))

    def test_old_power_first_order_is_gone(self):
        for rel in ('assets/routing-plan.md', 'references/pcb-routing-strategy.md'):
            with self.subTest(file=rel):
                self.assertNotIn('缝合孔、必要的电源走线 | G4', text(rel))
                self.assertNotIn('缝合、必要电源走线） | G4', text(rel))

    def test_autoroute_not_described_as_freerouting_only(self):
        body = text('references/pcb-routing-strategy.md')
        self.assertNotIn('`easycirq pcb autoroute` 走外部 Freerouting 流程', body)


class ClosureLessonsDocument(unittest.TestCase):
    def test_document_maps_lessons_and_states_evidence_honestly(self):
        self.assertTrue(LESSONS.is_file(), LESSONS)
        body = LESSONS.read_text(encoding='utf-8')
        for column in ('决定', '落点', '证据级别'):
            self.assertIn(column, body)
        self.assertIn('根因未定', body)
        self.assertIn('不外推', body)

    def test_each_mapped_location_exists(self):
        body = LESSONS.read_text(encoding='utf-8')
        for rel in sorted(set(re.findall(r'`(easycirq/[^`:#\s]+)', body))):
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == '__main__':
    unittest.main()
