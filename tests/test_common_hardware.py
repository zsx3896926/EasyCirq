import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'
REFS = SKILL / 'references'
PACK = REFS / 'common-hardware'
APPS = PACK / 'applications'

TOPICS = {
    'a-environment': ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7'],
    'b-optics': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8'],
    'c-motion': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7'],
    'd-force': ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7'],
    'e-measurement': ['E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7'],
    'f-input-protection': ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8'],
    'g-power-conversion': ['G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8'],
    'h-battery': ['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8'],
    'i-mcu': ['I1', 'I2', 'I3', 'I4', 'I5', 'I6', 'I7', 'I8'],
    'j-buses': ['J1', 'J2', 'J3', 'J4', 'J5', 'J6', 'J7', 'J8'],
    'k-drive': ['K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K7', 'K8', 'K9'],
    'l-hmi': ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9'],
    'm-wireless-time': ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8'],
}

HEADINGS = [
    '### 用户会怎么说', '### 路线选择', '### 必查参数', '### 电路组成',
    '### 参数与算例', '### 原理图与逐脚', '### PCB', '### 程序',
    '### 验证', '### 常见误判', '### 采购与落地', '### 来源与证据',
]

APP_FILES = [
    '01-temperature-alarm.md', '02-fan-control.md', '03-humidity-display.md',
    '04-door-window-reminder.md', '05-electronic-scale.md',
    '06-water-level-alarm.md', '07-current-monitor.md', '08-rs485-node.md',
    '09-timer-control.md', '10-soil-monitor.md', '11-data-logger.md',
    '12-solenoid-controller.md',
]

APP_HEADINGS = [
    '## 1. 需求与验收', '## 2. 推荐路线及理由', '## 3. 具体器件资料需求',
    '## 4. 模块组成与连接关系', '## 5. 关键计算与未确定项',
    '## 6. 原理图组织', '## 7. PCB 重点', '## 8. 程序与测试要求',
    '## 9. 采购与制造落地', '## 10. 当前完成等级与下一步',
]


def section(text, topic):
    match = re.search(rf'^##\s+{topic}\b.*$', text, re.M)
    if not match:
        return ''
    start = match.end()
    nxt = re.search(r'^##\s+', text[start:], re.M)
    return text[start:start + nxt.start()] if nxt else text[start:]


class CommonHardwareGroups(unittest.TestCase):
    def test_all_group_files_and_topics_exist(self):
        total = 0
        for group, topics in TOPICS.items():
            path = PACK / f'{group}.md'
            with self.subTest(group=group):
                self.assertTrue(path.is_file(), path)
                text = path.read_text(encoding='utf-8')
                self.assertIn('## 0. 本组怎么用', text)
                self.assertIn('## 本组来源', text)
                self.assertNotIn('[TODO', text)
                self.assertNotIn('待填', text)
                for topic in topics:
                    body = section(text, topic)
                    self.assertTrue(body, f'{group}: missing topic {topic}')
                    for heading in HEADINGS:
                        self.assertIn(heading, body, f'{group}/{topic}: missing {heading}')
                    self.assertRegex(body, r'证据[：:]', f'{group}/{topic}: missing evidence tag')
                    self.assertRegex(body, r'E[123]', f'{group}/{topic}: missing E1/E2/E3')
                    total += 1
        self.assertEqual(total, 102)

    def test_no_unregistered_source_ids(self):
        register = (REFS / 'source-register.md').read_text(encoding='utf-8')
        registered = set(re.findall(r'\b(CHW-S\d+)\b', register))
        cited = set()
        for path in PACK.rglob('*.md'):
            cited.update(re.findall(r'\b(CHW-S\d+)\b', path.read_text(encoding='utf-8')))
        self.assertTrue(cited, 'no CHW-S sources cited')
        self.assertEqual(sorted(cited - registered), [])

    def test_no_unmarked_c_numbers(self):
        hits = []
        for path in PACK.rglob('*.md'):
            for line in path.read_text(encoding='utf-8').splitlines():
                if re.search(r'\bC\d{4,}\b', line) and not any(
                        marker in line for marker in ('待查', '示例', '不编造', '未核对', '证据', '定位')):
                    hits.append(f'{path.relative_to(SKILL)}: {line.strip()[:120]}')
        self.assertEqual(hits, [], '\n'.join(hits))


class CommonHardwareApplications(unittest.TestCase):
    def test_twelve_applications_with_required_sections(self):
        for name in APP_FILES:
            path = APPS / name
            with self.subTest(app=name):
                self.assertTrue(path.is_file(), path)
                text = path.read_text(encoding='utf-8')
                for heading in APP_HEADINGS:
                    self.assertIn(heading, text)
                self.assertRegex(text, r'完成级别[：:]')
                self.assertNotIn('[TODO', text)
                self.assertNotIn('待填', text)


class CommonHardwareIndex(unittest.TestCase):
    def test_readme_routes_all_groups_and_apps(self):
        text = (PACK / 'README.md').read_text(encoding='utf-8')
        for group in TOPICS:
            self.assertIn(f'{group}.md', text)
        for name in APP_FILES:
            self.assertIn(name, text)


if __name__ == '__main__':
    unittest.main()
