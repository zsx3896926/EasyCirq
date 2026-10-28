"""Grep-style guard: the skill must not reference the retired easyeda toolchain.

The repository now ships its own execution layer (``easycirq``).  Any live file in
``easycirq/`` that still names the old CLI, daemon service, state
directory, environment variables or connector is a migration bug, not a
historical document.  ``tools/toolchain_refs.py`` owns the patterns and the
allowlist; this test only enforces the policy:

* no *actionable* reference may remain (exempt files are listed with a reason);
* the allowlist must stay narrow (only history/attribution/defensive files);
* the skill entry point must name the single preflight (``easycirq doctor`` +
  ``easycirq capabilities``).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import toolchain_refs  # noqa: E402


class LegacyReferenceGuard(unittest.TestCase):
    def test_skill_has_no_actionable_legacy_references(self):
        rows = toolchain_refs.scan(toolchain_refs.GUARD_SCOPES)
        actionable = [row for row in rows if not row['allowlist_reason']]
        self.assertFalse(
            actionable,
            'legacy easyeda references still live in the skill: '
            + '; '.join('%s:%s %r' % (row['path'], row['line'], row['match'])
                        for row in actionable[:20]))
        # The scan itself must really be looking for the old tokens.
        self.assertTrue(toolchain_refs.CATEGORIES)

    def test_repository_tooling_has_no_actionable_legacy_references(self):
        scopes = tuple(scope for scope in toolchain_refs.INVENTORY_SCOPES
                       if scope != 'easycirq')
        rows = toolchain_refs.scan(scopes)
        actionable = [row for row in rows if not row['allowlist_reason']]
        self.assertFalse(
            actionable,
            'legacy easyeda references still live in repository tooling: '
            + '; '.join('%s:%s %r' % (row['path'], row['line'], row['match'])
                        for row in actionable[:20]))

    def test_allowlist_entries_exist_and_state_a_reason(self):
        self.assertTrue(toolchain_refs.ALLOWLIST)
        for prefix, reason in toolchain_refs.ALLOWLIST.items():
            self.assertTrue(reason.strip(), prefix)
            path = ROOT / prefix.rstrip('/')
            self.assertTrue(path.exists(), 'allowlist path missing: %s' % prefix)
        # Never allowlist the policy entry point or live tooling by accident.
        for forbidden in ('easycirq/SKILL.md',
                          'easycirq/references/',
                          'easycirq/scripts/easycirq_cli.py'):
            self.assertNotIn(forbidden, toolchain_refs.ALLOWLIST)

    def test_skill_entry_names_the_single_preflight(self):
        entry = (ROOT / 'easycirq' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('easycirq doctor', entry)
        self.assertIn('easycirq capabilities', entry)
        found = [category for category, pattern in
                 toolchain_refs.CATEGORIES.items() if pattern.search(entry)]
        self.assertEqual(found, [], 'SKILL.md carries legacy tokens: %s' % found)
        # health is a daemon detail, not the agent's preflight entry.
        self.assertNotIn('easycirq health', entry)


class GuardDetectsRegressions(unittest.TestCase):
    """The scanner must actually catch the strings it claims to catch."""

    def test_scanner_catches_each_category(self):
        samples = {
            'cli': 'easyeda sch list --json',
            'service': 'easyeda-agent v1.15.0',
            'state_dir': 'artifacts under <proj>/.easyeda/artifacts',
            'env': 'EASYEDA_NO_AUTOSTART=1',
            'connector': 'easyeda-connector extension',
            'bare': "['easyeda', 'version']",
        }
        for category, sample in samples.items():
            with self.subTest(category=category):
                self.assertTrue(toolchain_refs.CATEGORIES[category].search(sample),
                                '%s pattern missed %r' % (category, sample))

    def test_scanner_ignores_product_names_and_product_docs(self):
        for benign in ('EasyEDA Pro 4.1.78', 'prodocs.easyeda.com/cn/pcb/',
                       'vendor/easyeda-format/schemas', 'easyeda-ecosystem.md'):
            with self.subTest(text=benign):
                for category, pattern in toolchain_refs.CATEGORIES.items():
                    self.assertIsNone(
                        pattern.search(benign),
                        '%s pattern falsely flagged %r' % (category, benign))


if __name__ == '__main__':
    unittest.main()
