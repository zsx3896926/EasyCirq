"""Block parts must resolve and must not silently reference auto-added parts.

S18: the SY8089 buck block defaulted to ``ind.22uh_1210`` (NLCV32T-2R2M-PF, an
auto-added part with no current rating), which reads like 22µH and is only
~0.77A — below the block's 2A requirement.  These checks make an unverified
part reference visible instead of silently wiring it.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKS_DIR = ROOT / 'runtime' / 'internal' / 'blocks' / 'data'
PARTS_PATH = ROOT / 'easycirq' / 'references' / 'standard-parts.json'


def load_parts():
    return json.loads(PARTS_PATH.read_text(encoding='utf-8'))['parts']


def load_blocks():
    blocks = {}
    for path in sorted(BLOCKS_DIR.glob('*.json')):
        blocks[path.stem] = json.loads(path.read_text(encoding='utf-8'))
    return blocks


def block_part_refs(block):
    refs = []
    for role, item in (block.get('parts') or {}).items():
        if isinstance(item, dict) and item.get('part'):
            refs.append((role, item['part']))
    return refs


def unverified_block_parts():
    """[(block_id, role, part)] where the referenced part is auto-added."""
    parts = load_parts()
    out = []
    for block_id, block in load_blocks().items():
        for role, part in block_part_refs(block):
            entry = parts.get(part)
            if entry is None:
                out.append((block_id, role, part, 'missing'))
            elif str(entry.get('desc') or '').startswith('auto-added'):
                out.append((block_id, role, part, 'auto-added'))
    return out


class BlockPartsTests(unittest.TestCase):
    def test_all_block_parts_resolve(self):
        missing = [r for r in unverified_block_parts() if r[3] == 'missing']
        self.assertEqual(missing, [], 'dangling part refs: %s' % missing)

    def test_sy8089_inductor_is_not_auto_added(self):
        blocks = load_blocks()
        block = blocks['sy8089_buck_3v3']
        parts = load_parts()
        roles = dict(block_part_refs(block))
        inductor = parts[roles['L']]
        self.assertFalse(str(inductor.get('desc') or '').startswith('auto-added'),
                         'SY8089 L still points at an auto-added part')
        self.assertIn('待', str(inductor.get('desc') or ''))

    def test_sy8089_inductor_not_in_unverified_scan(self):
        flagged = {(b, r) for b, r, _p, _k in unverified_block_parts()}
        self.assertNotIn(('sy8089_buck_3v3', 'L'), flagged)


if __name__ == '__main__':
    unittest.main()
