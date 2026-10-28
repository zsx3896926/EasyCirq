"""Guard: interface pinout requirement and its DVP FPC design card stay present.

PocketCam X1 ran the whole schematic/routing on an assumed camera/LCD pinout and
only mentioned it in the final report.  These checks pin the requirement key,
the delivery blocking, and the assumed design-card template.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'

CARD = SKILL / 'references' / 'module-cards' / 'camera-dvp-fpc.md'
GATES = SKILL / 'references' / 'design-gates.md'
MODULE = SKILL / 'references' / 'module-integration.md'
EXAMPLE = SKILL / 'assets' / 'design-state.example.json'

MUST_CHECK = ['1 脚方向', '电源域', '差分对', '时钟', '电平', '复位']


class InterfacePinoutGuard(unittest.TestCase):
    def test_design_card_exists_and_is_assumed_template(self):
        body = CARD.read_text(encoding='utf-8')
        self.assertIn('assumed', body)
        self.assertIn('不得据此', body)
        for item in MUST_CHECK:
            self.assertIn(item, body)

    def test_gates_documents_the_key_and_delivery_blocking(self):
        body = GATES.read_text(encoding='utf-8')
        self.assertIn('req_interface_pinout', body)
        self.assertIn('G6 交付 `BLOCKED`', body)

    def test_module_integration_references_the_card(self):
        body = MODULE.read_text(encoding='utf-8')
        self.assertIn('interface_pinout', body)
        self.assertIn('camera-dvp-fpc.md', body)

    def test_example_state_carries_the_key(self):
        body = EXAMPLE.read_text(encoding='utf-8')
        self.assertIn('interface_pinout', body)


if __name__ == '__main__':
    unittest.main()
