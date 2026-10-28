"""Guard: the GameForge-X1 field lessons must stay on the default execution path.

These lessons are only useful if they are woven into the files the agent actually
reads on a normal task.  This test uses loose keyword matching (synonyms and
section wording allowed) so it protects the rule without freezing exact prose.

Covered here: the 8 numbered requirements given by the user (1, 2, 3, 5, 6, 7,
8, 9; item 4 was not supplied and is recorded as missing in
``docs/toolchain-integration/field-lessons.md``) plus the honesty requirement
for unavailable field evidence.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'
FIELD_LESSONS = ROOT / 'docs' / 'toolchain-integration' / 'field-lessons.md'


def text(rel):
    path = SKILL / rel
    if not path.is_file():
        raise AssertionError('missing file: %s' % path)
    return path.read_text(encoding='utf-8')


def contains_any(body, alternatives):
    lowered = body.lower()
    return any(alternative.lower() in lowered for alternative in alternatives)


# rule id -> files that must carry the rule on the default path + keyword groups
RULES = {
    '1-default-drawing': {
        'files': ['SKILL.md', 'references/schematic-authoring.md',
                  'references/schematic-layout.md'],
        'groups': [['功能分区'], ['短引线', '短线'], ['直连', '直接连线'],
                   ['网络标签', '标签'], ['作用域']],
    },
    '2-representative-module': {
        'files': ['SKILL.md', 'references/schematic-authoring.md',
                  'references/workflow.md', 'references/design-gates.md'],
        'groups': [['代表模块', '最有代表性的模块', '样板'],
                   ['保存', 'save'],
                   ['重开', '重新打开'],
                   ['逐脚', 'pin-net'],
                   ['官方导图', '官方导出', '导图'],
                   ['批量']],
    },
    '3-delivery-capability-preflight': {
        'files': ['SKILL.md', 'references/workflow.md',
                  'references/schematic-authoring.md'],
        'groups': [['zhigou capabilities'], ['交付能力'],
                   ['已实测'], ['API存在', 'API 存在'],
                   ['GUI'], ['不支持'],
                   ['接口存在不等于', '接口存在 ≠', '不等于已验证']],
    },
    '5-failure-budget': {
        'files': ['SKILL.md', 'references/feedback-loop.md',
                  'references/tool-gotchas.md', 'references/design-gates.md'],
        'groups': [['连续 2 次', '连续2次', '连续 **2 次**'],
                   ['重新诊断', '重新诊断'], ['原样重试', '原样'],
                   ['阶段预算', '预算'], ['替代路径'], ['质量检查']],
    },
    '6-autonomous-execution': {
        'files': ['SKILL.md', 'references/interaction.md'],
        'groups': [['整板自主', '自主完成'], ['继续布线'],
                   ['自检'], ['新增任务范围', '新增范围'], ['关键约束']],
    },
    '7-protect-electrical-design': {
        'files': ['SKILL.md', 'references/design-gates.md',
                  'references/review.md'],
        'groups': [['浮空'], ['改网络', '改网'], ['删器件'], ['降约束', '降低约束'],
                   ['影响分析'], ['变更记录'], ['检查器']],
    },
    '8-verify-part-facts-first': {
        'files': ['references/design-experience.md',
                  'references/failures/README.md'],
        'groups': [['按键'], ['合并焊盘'], ['裸露', '裸焊盘', 'exposed'],
                   ['摇杆'], ['多单元符号'], ['原厂'],
                   ['真实库件', '库件'], ['先验证再沉淀'], ['不适用']],
    },
}


class FieldLessonsOnDefaultPath(unittest.TestCase):
    def test_each_rule_is_present_in_its_default_path_files(self):
        for rule_id, spec in RULES.items():
            with self.subTest(rule=rule_id):
                for rel in spec['files']:
                    body = text(rel)
                    missing = [group for group in spec['groups']
                               if not contains_any(body, group)]
                    self.assertFalse(
                        missing,
                        '%s missing from %s: %s' % (rule_id, rel, missing))

    def test_skill_entry_carries_the_cross_cutting_rules(self):
        # These must not live only in a reference file the agent might skip.
        entry = text('SKILL.md')
        for needle in ('功能分区', '短引线', '代表模块', 'zhigou capabilities',
                       '交付能力', '连续 2 次', '整板自主', '浮空', '降低约束'):
            with self.subTest(needle=needle):
                self.assertIn(needle, entry)


class FieldLessonsDocument(unittest.TestCase):
    def test_document_exists_and_maps_every_supplied_item(self):
        self.assertTrue(FIELD_LESSONS.is_file(), FIELD_LESSONS)
        body = FIELD_LESSONS.read_text(encoding='utf-8')
        for item in ('1', '2', '3', '5', '6', '7', '8', '9'):
            with self.subTest(item=item):
                self.assertRegex(body, r'(?m)^\| %s \|' % item,
                                 'missing lesson row %s' % item)
        for column in ('决定', '落点', '验收', '证据级别'):
            with self.subTest(column=column):
                self.assertIn(column, body)

    def test_unavailable_field_evidence_is_recorded_honestly(self):
        body = FIELD_LESSONS.read_text(encoding='utf-8')
        for needle in ('D:/Users/27675', '不可访问', '未取得', '未复现',
                       '仅按用户描述', '证据级别 D'):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)
        # Must not claim the field patch/snapshot was absorbed.
        for forbidden in ('已复现该现场', '已吸收现场补丁', '已取得现场快照'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)

    def test_each_mapped_location_exists(self):
        body = FIELD_LESSONS.read_text(encoding='utf-8')
        for rel in sorted(set(re.findall(
                r'`(easycirq/[^`:#\s]+)', body))):
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).is_file(), rel)


class NoLegacyPreflightWording(unittest.TestCase):
    def test_old_health_preflight_is_gone_from_policy_files(self):
        for rel in ('SKILL.md', 'references/interaction.md',
                    'references/client-compatibility.md'):
            with self.subTest(file=rel):
                body = text(rel)
                self.assertNotIn('zhigou health', body)


if __name__ == '__main__':
    unittest.main()
