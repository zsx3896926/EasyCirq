#!/usr/bin/env python3
"""Mechanical part of the easyeda -> zhigou skill migration.

Run from the repository root:

    python docs/toolchain-integration/evidence/skill-migration/migrate_toolchain_refs.py --apply

The script only rewrites the text of files that are *live policy or tooling*
(design-hardware/, tests/, tools/, benchmarks/, .github/).  Historical records
(CHANGELOG, NOTICE, cases/ evidence, vendor formats) are intentionally left
alone: they document what was actually run and must not be rewritten as if the
old toolchain had never existed.

The manual parts of the migration (SKILL.md structure, the doctor_env /
companion_update rewrites, new guard tests) are NOT done here.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
SCOPES = ['design-hardware', 'tests', 'tools', 'benchmarks', '.github']
SKIP_PARTS = {'node_modules', '__pycache__', '.git'}
SKIP_REL_PREFIXES = (
    'design-hardware/CHANGELOG.md',
    'design-hardware/NOTICE',
    'design-hardware/LICENSE',
    'design-hardware/vendor/',
    'design-hardware/cases/',
    # Frozen real-measurement fixtures: rewriting provenance invalidates the
    # recorded SHA-256 bindings.
    'tests/fixtures/photo-led-v14/',
    'tests/fixtures/photo-led-acceptance.json',
    # Faithful captures of zhigou doctor/capabilities output; the doctor's
    # ``legacy`` field legitimately names the old daemon it detects.
    'tests/fixtures/zhigou/',
    # The scanner spells the legacy tokens in its pattern definitions.
    'tools/toolchain_refs.py',
    'tests/test_no_legacy_toolchain_refs.py',
    # Defensive/compatibility files that must keep a legacy token on purpose:
    # the offline guard refuses old binaries, the release packager accepts the
    # old wrapper flag, and the layout adapter binds a frozen schema string.
    'design-hardware/scripts/offline_guard.py',
    'design-hardware/scripts/skill_update.py',
    'design-hardware/scripts/layout_from_zhigou.py',
)
BINARY_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.epro2', '.eext',
    '.exe', '.woff', '.woff2', '.ttf', '.otf', '.ico', '.pyc', '.bin',
}

# Ordered replacements.  Specific identifiers first, then the generic command
# token.  ``easyeda-format`` / ``easyeda-ecosystem`` / prodocs.easyeda.com are
# deliberately not matched: they name the EasyEDA product/format, not the CLI.
REPLACEMENTS = [
    (re.compile(r'EASYEDA_NO_AUTOSTART'), 'ZHIGOU_NO_AUTOSTART'),
    (re.compile(r'EASYEDA_CLI'), 'ZHIGOU_BIN'),
    (re.compile(r'EASYEDA_HEALTH_TIMEOUT_S'), 'ZHIGOU_DOCTOR_TIMEOUT_S'),
    (re.compile(r'EASYEDA_NAMES'), 'EDA_NAMES'),
    (re.compile(r'FAKE_EASYEDA_'), 'FAKE_ZHIGOU_'),
    (re.compile(r'EASYEDA_'), 'ZHIGOU_'),
    (re.compile(r'easyeda-agent'), 'zhigou-agent'),
    (re.compile(r'easyeda_agent'), 'zhigou_agent'),
    (re.compile(r'easyeda-connector'), 'zhigou-connector'),
    (re.compile(r'easyeda_executable'), 'zhigou_executable'),
    (re.compile(r'easyeda_command'), 'zhigou_command'),
    (re.compile(r'easyeda_probe'), 'zhigou_probe'),
    (re.compile(r'easyeda_ready'), 'zhigou_ready'),
    (re.compile(r'easyeda_name'), 'zhigou_name'),
    (re.compile(r'easyeda-health'), 'zhigou-health'),
    (re.compile(r'easyeda-version'), 'zhigou-version'),
    (re.compile(r'layout_from_easyeda'), 'layout_from_zhigou'),
    (re.compile(r'to_easyeda_moves'), 'to_zhigou_moves'),
    (re.compile(r'easyeda-list-bundle'), 'zhigou-list-bundle'),
    (re.compile(r'easyeda_sch_clusters'), 'zhigou_sch_clusters'),
    (re.compile(r'easyeda_version_unknown'), 'zhigou_version_unknown'),
    (re.compile(r'easyeda-actual-readback'), 'zhigou-actual-readback'),
    (re.compile(r'easyeda-cli'), 'zhigou-cli'),
    (re.compile(r'easyeda_list'), 'zhigou_list'),
    (re.compile(r'references_easyeda'), 'references_zhigou'),
    (re.compile(r'_mentions_easyeda'), '_mentions_legacy_eda'),
    (re.compile(r'mock-easyeda'), 'mock-zhigou'),
    (re.compile(r'fake-easyeda'), 'fake-zhigou'),
    (re.compile(r'fake_easyeda'), 'fake_zhigou'),
    (re.compile(r'easyeda-fake'), 'zhigou-fake'),
    (re.compile(r'--easyeda'), '--zhigou'),
    (re.compile(r'\beasyeda='), 'zhigou='),
    # Attribute form (args.easyeda / self.easyeda); URLs such as
    # prodocs.easyeda.com are protected by the ``(?!\.)``.
    (re.compile(r'\.easyeda(?!\.)(?![A-Za-z0-9_-])'), '.zhigou'),
    # Attribute / path form: args.easyeda, .easyeda/artifacts, .easyeda-agent
    (re.compile(r'(?<![A-Za-z0-9_-])\.easyeda(?![A-Za-z0-9_-])'), '.zhigou'),
    # Standalone CLI token in prose, code fences, arrays and file names.
    (re.compile(r'(?<![A-Za-z0-9_./-])easyeda(?![A-Za-z0-9_/-])'), 'zhigou'),
]

RENAMES = {
    'design-hardware/scripts/layout_from_easyeda.py':
        'design-hardware/scripts/layout_from_zhigou.py',
    'tests/fixtures/feedback/fake_easyeda.py':
        'tests/fixtures/feedback/fake_zhigou.py',
    'tests/fixtures/feedback/easyeda-fake.cmd':
        'tests/fixtures/feedback/zhigou-fake.cmd',
    'tests/fixtures/feedback/easyeda-fake.sh':
        'tests/fixtures/feedback/zhigou-fake.sh',
}


def skipped(rel: str) -> bool:
    return any(rel == prefix or rel.startswith(prefix)
               for prefix in SKIP_REL_PREFIXES)


def iter_files():
    for scope in SCOPES:
        base = ROOT / scope
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*')):
            if not path.is_file():
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if skipped(rel):
                continue
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            yield path, rel


def migrate_text(text: str) -> tuple[str, list[str]]:
    hits: list[str] = []
    for pattern, replacement in REPLACEMENTS:
        new, count = pattern.subn(replacement, text)
        if count:
            hits.append('%s -> %s (%d)' % (pattern.pattern, replacement, count))
            text = new
    return text, hits


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='write changes (default: report only)')
    args = parser.parse_args(argv)
    changed = 0
    total_hits = 0
    for path, rel in iter_files():
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            print('skip (not utf-8): %s' % rel, file=sys.stderr)
            continue
        new, hits = migrate_text(text)
        if new == text:
            continue
        changed += 1
        total_hits += len(hits)
        print('%s: %s' % (rel, '; '.join(hits)))
        if args.apply:
            path.write_text(new, encoding='utf-8', newline='')
    for old, new in RENAMES.items():
        source, target = ROOT / old, ROOT / new
        if not source.is_file():
            continue
        print('rename %s -> %s' % (old, new))
        if args.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
    print('files changed: %d, rule applications: %d' % (changed, total_hits))
    return 0


if __name__ == '__main__':
    sys.exit(main())
