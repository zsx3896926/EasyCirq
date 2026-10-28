import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'
REFS = SKILL / 'references'

CARD_COUNTS = {'power': 14, 'mcu': 8, 'interfaces': 12,
               'analog': 10, 'drive': 8, 'wireless': 8}
CARD_HEADINGS = [
    '## 1. 用途与适用范围', '## 2. 必要输入', '## 3. 拓扑及工作原理',
    '## 4. 参数确定步骤', '## 5. 完整算例', '## 6. 器件选择依据',
    '## 7. 逐脚与外围核对', '## 8. 原理图表达', '## 9. PCB 要求',
    '## 10. 异常状态', '## 11. 验证办法', '## 12. 原始来源与版本',
]
EXAMPLE_HEADINGS = [
    '## 1. 设计意图与连接基线', '## 2. 原理图模块内部摆放',
    '## 3. 局部短线与标签连接', '## 4. PCB 关键器件相对关系',
    '## 5. 电流路径、信号路径与返回路径', '## 6. 常见错误及其后果',
    '## 7. 改善后的方案与检查方法',
    '## 8. 必须保留的身份、连接和接口约束',
]
FAILURE_HEADINGS = ['## 现象', '## 工况', '## 原因假设',
                    '## 区分假设的检查', '## 根因证据', '## 修复',
                    '## 复验', '## 适用边界']
PROJECT_HEADINGS = [
    '## 1. 自然语言需求与验收标准', '## 2. 方案与架构', '## 3. 选型与依据',
    '## 4. 计算', '## 5. 原理图连接基线', '## 6. PCB 布局草案',
    '## 7. BOM、制造文件与装配说明', '## 8. 固件、引脚配置与构建说明',
    '## 9. 首板测试计划', '## 10. 实际结果、已知限制与下一步',
    '## 11. 来源与证据',
]


def frontmatter(text):
    if not text.startswith('---\n'):
        return {}
    end = text.find('\n---', 4)
    if end < 0:
        return {}
    data = {}
    for line in text[4:end].splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
    return data


def md_files(directory):
    return sorted(p for p in directory.glob('*.md') if p.name.lower() != 'readme.md')


class DesignCards(unittest.TestCase):
    def test_category_counts_and_total(self):
        total = 0
        for category, expected in CARD_COUNTS.items():
            cards = md_files(REFS / 'design-cards' / category)
            self.assertEqual(len(cards), expected, category)
            total += len(cards)
        self.assertEqual(total, 60)

    def test_each_card_has_frontmatter_and_twelve_sections(self):
        for category, expected in CARD_COUNTS.items():
            prefix = {'power': 'PWR', 'mcu': 'MCU', 'interfaces': 'IF',
                      'analog': 'ANA', 'drive': 'DRV', 'wireless': 'RF'}[category]
            for card in md_files(REFS / 'design-cards' / category):
                text = card.read_text(encoding='utf-8')
                meta = frontmatter(text)
                with self.subTest(card=str(card.relative_to(SKILL))):
                    self.assertTrue(meta.get('id', '').startswith(prefix + '-'))
                    self.assertEqual(meta.get('category'), category)
                    self.assertTrue(meta.get('title'))
                    self.assertIn(meta.get('evidence'), {'E1', 'E2', 'E3'})
                    self.assertEqual(meta.get('last_reviewed'), '2026-10-20')
                    self.assertTrue(meta.get('sources'))
                    self.assertTrue(meta.get('related_checks'))
                    for heading in CARD_HEADINGS:
                        self.assertIn(heading, text)
                    self.assertIn('### 不能使用的条件', text)
                    self.assertIn('给定条件', text)
                    self.assertIn('结论与限制', text)
                    self.assertIn('不能证明', text)
                    self.assertNotIn('[TODO', text)

    def test_related_checks_are_known_ids(self):
        for category in CARD_COUNTS:
            for card in md_files(REFS / 'design-cards' / category):
                meta = frontmatter(card.read_text(encoding='utf-8'))
                checks = re.findall(r'(SC|PL|RT|MF|DM)\d+', meta.get('related_checks', ''))
                self.assertTrue(checks, card)


class Examples(unittest.TestCase):
    def test_twelve_examples_with_required_sections(self):
        examples = md_files(REFS / 'examples')
        self.assertGreaterEqual(len(examples), 12)
        for example in examples:
            text = example.read_text(encoding='utf-8')
            with self.subTest(example=str(example.relative_to(SKILL))):
                self.assertIn('类型：', text)
                for heading in EXAMPLE_HEADINGS:
                    self.assertIn(heading, text)
                self.assertNotIn('[TODO', text)


class FailureLibrary(unittest.TestCase):
    def test_at_least_twenty_cases_with_evidence_grades(self):
        cases = md_files(REFS / 'failures')
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            text = case.read_text(encoding='utf-8')
            meta = frontmatter(text)
            with self.subTest(case=str(case.relative_to(SKILL))):
                self.assertTrue(meta.get('id', '').startswith('F'))
                self.assertTrue(meta.get('title'))
                self.assertIn(meta.get('evidence_grade'), {'A', 'B', 'C', 'D'})
                self.assertTrue(meta.get('source_ids'))
                for heading in FAILURE_HEADINGS:
                    self.assertIn(heading, text)
                self.assertNotIn('[TODO', text)


class SelectionAndManufacturing(unittest.TestCase):
    def test_selection_files_and_replacement_classes(self):
        selection = REFS / 'selection'
        for name in ['passives.md', 'semiconductors.md', 'power-ics.md',
                     'modules-connectors.md', 'replacement-classes.md',
                     'lcsc-verification.md']:
            self.assertTrue((selection / name).is_file(), name)
        text = (selection / 'replacement-classes.md').read_text(encoding='utf-8')
        for cls in ['1', '2', '3', '4']:
            self.assertRegex(text, rf'类\s*{cls}|等级\s*{cls}|第\s*{cls}\s*类')
        combined = '\n'.join((selection / n).read_text(encoding='utf-8')
                             for n in ['passives.md', 'semiconductors.md',
                                       'power-ics.md', 'modules-connectors.md'])
        for keyword in ['绝对最大', '推荐工作条件', '典型值', '封装', '筛选']:
            self.assertIn(keyword, combined)

    def test_manufacturing_routes(self):
        text = (REFS / 'manufacturing-routes.md').read_text(encoding='utf-8')
        for keyword in ['商城', 'SMT', '整机', 'Gerber', 'BOM', '坐标', 'DNP']:
            self.assertIn(keyword, text)


class IntegrationAndSimulation(unittest.TestCase):
    def test_module_integration_contract_and_cases(self):
        text = (REFS / 'module-integration.md').read_text(encoding='utf-8')
        for keyword in ['接口契约', '输入/输出', '逻辑门限', '上电', '复位',
                        '下载', '休眠', '引脚复用', '连接器', 'FPC', 'Pin-1',
                        '参考地', '隔离', '固件', '机械', '热', '天线']:
            self.assertIn(keyword, text)
        self.assertGreaterEqual(text.count('案例'), 8)

    def test_simulation_and_measurement_doc(self):
        text = (REFS / 'simulation-measurement.md').read_text(encoding='utf-8')
        for keyword in ['rc_settle_sim', 'NOT RUN', '测点', '探头', '带宽',
                        '停止条件', '不能证明']:
            self.assertIn(keyword, text)


class CalculationsAndProjects(unittest.TestCase):
    def test_calculation_files_have_assumptions_and_limits(self):
        files = md_files(REFS / 'calculations')
        self.assertGreaterEqual(len(files), 4)
        for path in files:
            text = path.read_text(encoding='utf-8')
            with self.subTest(path=path.name):
                self.assertIn('假设', text)
                self.assertIn('算例', text)
                self.assertTrue('不能证明' in text or '限制' in text)

    def test_three_projects_with_completion_level(self):
        projects = md_files(REFS / 'projects')
        self.assertGreaterEqual(len(projects), 3)
        for project in projects:
            text = project.read_text(encoding='utf-8')
            with self.subTest(project=project.name):
                self.assertIn('完成级别', text)
                for heading in PROJECT_HEADINGS:
                    self.assertIn(heading, text)
                self.assertNotIn('[TODO', text)


class SourceAndFabricationHygiene(unittest.TestCase):
    def test_source_register_is_present(self):
        text = (REFS / 'source-register.md').read_text(encoding='utf-8')
        self.assertGreaterEqual(len(re.findall(r'\|\s*[A-Z]+-S\d+', text)), 25)

    def test_every_cited_source_id_is_registered(self):
        text = (REFS / 'source-register.md').read_text(encoding='utf-8')
        registered = set(re.findall(r'\|\s*([A-Z]+-S\d+)', text))
        cited = set()
        for path in REFS.rglob('*.md'):
            cited.update(re.findall(r'\b([A-Z]{2,4}-S\d+)\b',
                                    path.read_text(encoding='utf-8')))
        missing = sorted(cited - registered)
        self.assertEqual(missing, [], f'unregistered source IDs: {missing}')

    def test_no_obvious_fabricated_c_numbers(self):
        hits = []
        for path in list(REFS.rglob('*.md')) + list(SKILL.glob('assets/*.md')):
            for line in path.read_text(encoding='utf-8').splitlines():
                if re.search(r'\bC\d{4,}\b', line) and not any(
                        marker in line for marker in ('待查', '示例', '不编造', '未核对', 'placeholder')):
                    hits.append(f"{path.relative_to(SKILL)}: {line.strip()[:120]}")
        self.assertEqual(hits, [], '\n'.join(hits))


if __name__ == '__main__':
    unittest.main()
