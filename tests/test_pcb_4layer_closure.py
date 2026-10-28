"""Guard: the 4-layer closure recipe and the single DRC stop rule stay intact.

The PocketCam X1 session hit two fake DRC spikes (pour not rebuilt) and one
real regression (21 -> 74) that a plain "3 rounds < 30% -> stop" rule cannot
tell apart.  This guard pins the recipe and the consolidated stop rule so the
skill does not drift back to multiple hand-written convergence loops.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'

CLOSURE = SKILL / 'references' / 'pcb-4layer-closure.md'
COLLAB = SKILL / 'references' / 'agent-collaboration.md'
PCB = SKILL / 'references' / 'pcb.md'
STRATEGY = SKILL / 'references' / 'pcb-routing-strategy.md'
ROUTING_PLAN = SKILL / 'assets' / 'routing-plan.md'
GATES = SKILL / 'references' / 'design-gates.md'

STEPS = ['规则与层叠', '机械与禁区', '布局', '逃逸', '关键网', '分批信号',
         '离线补线', '信号门禁', '电源与地', 'DRC 循环', 'DFM 收尾', '交付']


def text(path):
    if not path.is_file():
        raise AssertionError('missing file: %s' % path)
    return path.read_text(encoding='utf-8')


class FourLayerClosureRecipe(unittest.TestCase):
    def test_recipe_exists_and_is_compact(self):
        body = text(CLOSURE)
        self.assertLessEqual(len(body.splitlines()), 120,
                             'pcb-4layer-closure.md must stay <= 120 lines')
        for step in STEPS:
            self.assertIn(step, body)

    def test_recipe_states_the_fake_spike_rules(self):
        body = text(CLOSURE)
        self.assertIn('不计入', body)
        self.assertIn('恢复上一轮备份', body)
        self.assertIn('重排局部区域', body)
        self.assertIn('重新规划逃逸', body)

    def test_recipe_uses_pocketcam_trajectory_as_acceptance(self):
        body = text(CLOSURE)
        self.assertIn('74', body)
        self.assertIn('1910', body)
        self.assertIn('375', body)


class ConsolidatedStopRule(unittest.TestCase):
    def test_collaboration_owns_the_stop_rule(self):
        body = text(COLLAB)
        self.assertIn('唯一的 DRC 停止规则定义', body)
        self.assertIn('不计入轮次', body)
        self.assertIn('恢复上一轮备份', body)
        self.assertIn('重排局部区域', body)
        self.assertIn('重新规划逃逸', body)
        self.assertIn('pcb-4layer-closure.md', body)

    def test_other_pages_reference_not_restate(self):
        for path in (PCB, ROUTING_PLAN, GATES):
            self.assertIn('agent-collaboration', text(path),
                          '%s must reference the single stop rule' % path)
        strategy = text(STRATEGY)
        self.assertIn('agent-collaboration', strategy)
        self.assertIn('pcb-4layer-closure.md', strategy)
        self.assertNotIn('评估 4 层、拆分功能', strategy)

    def test_gates_names_the_4layer_escape_hatches(self):
        gates = text(GATES)
        self.assertIn('重规划逃逸', gates)
        self.assertIn('拆板', gates)


if __name__ == '__main__':
    unittest.main()
