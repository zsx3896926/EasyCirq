#!/usr/bin/env python3
"""Inventory and guard old external-EDA-toolchain references.

The repository's own execution layer is ``zhigou`` (runtime/, connector/,
distribution/).  This module is the *scanning* side of the migration: it finds
references to the former upstream ``easyeda`` toolchain (CLI, daemon service,
state directory, environment variables, connector, skill name) in a tree, and
it is shared by:

  * ``python tools/toolchain_refs.py [--json|--strict]`` for a raw inventory;
  * ``tests/test_no_legacy_toolchain_refs.py`` as the grep-style guard.

It never executes anything.  A path listed in ``ALLOWLIST`` may keep old
references because it records what actually happened (CHANGELOG, release
attribution, frozen case evidence) or because it must defend against the old
binary; rewriting those would falsify history or remove a safety check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'design-hardware'

# Categories are reported separately so an intentional mention (a link to the
# EasyEDA product documentation, the ``easyeda-format`` vendor schemas) is not
# confused with a dead CLI call.
CATEGORIES = {
    # `easyeda <subcommand>` / `easyeda --flag` style invocations.
    'cli': re.compile(
        r'(?<![A-Za-z0-9_./-])easyeda(?=\s+(?:doctor|health|sch|pcb|project|'
        r'doc|bom|lib|actions|call|version|daemon|connector|session|open|'
        r'invoke|functions|apply|audit|blocks|board|editor|notify|skill|'
        r'spec|update|view|web|workflow|api)\b)'),
    # The upstream daemon service / skill family name.
    'service': re.compile(r'easyeda[-_]agent', re.I),
    # Daemon/artifact state directories: ~/.easyeda-agent, <proj>/.easyeda/...
    'state_dir': re.compile(
        r'\.easyeda(?:-agent)?(?:[\\/]|["\'`\s),;\]]|$)'),
    # Environment variables of the old toolchain.
    'env': re.compile(r'EASYEDA_[A-Z0-9_]+'),
    # Old connector extension name.
    'connector': re.compile(r'easyeda[-_]connector', re.I),
    # Bare lowercase executable token (e.g. ['easyeda', 'version']).
    'bare': re.compile(r'(?<![A-Za-z0-9_./-])easyeda(?![A-Za-z0-9_./-])'),
}

# Files that may keep old references, with the reason they are exempt.
ALLOWLIST = {
    'design-hardware/CHANGELOG.md': 'release history: records what the old '
                                    'toolchain did; rewriting it falsifies history',
    'design-hardware/NOTICE': 'upstream attribution required by the upstream '
                              'license',
    'design-hardware/vendor/easyeda-format/': 'vendor copy of the EasyEDA '
                                              'document format schemas, not the CLI',
    'design-hardware/cases/': 'frozen evidence captured from real old-toolchain '
                              'runs; it is not policy or an executable path',
    'design-hardware/scripts/offline_guard.py': 'defensive: the offline guard '
                                                'must still refuse to execute a '
                                                'legacy easyeda binary',
    'design-hardware/scripts/skill_update.py': 'legacy dist compatibility: the '
                                               'release packager still has to '
                                               'recognise old installed names',
    'design-hardware/scripts/layout_from_zhigou.py': 'frozen schema string: '
                                                    '"coordinate_units" text is '
                                                    'bound into recorded fixture '
                                                    'SHA-256 values; changing it '
                                                    'invalidates stored evidence',
    'tests/fixtures/photo-led-v14/': 'frozen real-measurement fixtures with '
                                     'recorded SHA-256 bindings; rewriting the '
                                     'provenance text invalidates the evidence',
    'tests/fixtures/photo-led-acceptance.json': 'frozen measurement provenance '
                                                'referenced by pcb_gate/case tests',
    'tests/fixtures/zhigou/': 'faithful capture of zhigou doctor/capabilities '
                              'output; the doctor legacy field legitimately names '
                              'the old daemon it detects (never uses it)',
    'benchmarks/': 'frozen benchmark inputs/evidence merged from main: they embed '
                   'historical easyeda snapshots; rewriting would falsify evidence',
    'tests/annotation_layout/fixtures/': 'frozen annotation-layout fixtures from '
                                         'the old-toolchain era; rewriting the '
                                         'provenance text invalidates the evidence',
}
ALLOWLIST_PREFIXES = tuple(ALLOWLIST)

BINARY_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.epro2', '.eext',
    '.exe', '.woff', '.woff2', '.ttf', '.otf', '.ico', '.pyc', '.bin',
}
SKIP_PARTS = {'node_modules', '__pycache__', '.git'}
# The scanner and its guard test necessarily spell the legacy tokens in their
# pattern definitions; they are not themselves references to the old toolchain.
EXCLUDE_FILES = {
    'tools/toolchain_refs.py',
    'tests/test_no_legacy_toolchain_refs.py',
}

# Default scan scope for the guard: the installed skill package only.  The
# inventory CLI additionally scans the repository tooling that drives it.
GUARD_SCOPES = ('design-hardware',)
INVENTORY_SCOPES = ('design-hardware', 'tests', 'tools', 'benchmarks', '.github')


def allowlisted(rel: str) -> str | None:
    """Return the allowlist reason for a repository-relative path, if any."""
    for prefix in ALLOWLIST_PREFIXES:
        if rel == prefix or rel.startswith(prefix):
            return ALLOWLIST[prefix]
    return None


def iter_files(scope: str):
    base = ROOT / scope
    if not base.is_dir():
        return
    for path in sorted(base.rglob('*')):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXCLUDE_FILES:
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        yield path


def scan(scopes=INVENTORY_SCOPES):
    """Return a list of reference rows plus per-file allowlist decisions."""
    rows = []
    for scope in scopes:
        for path in iter_files(scope):
            rel = path.relative_to(ROOT).as_posix()
            reason = allowlisted(rel)
            try:
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for category, pattern in CATEGORIES.items():
                    for match in pattern.finditer(line):
                        rows.append({
                            'path': rel,
                            'line': lineno,
                            'category': category,
                            'match': match.group(0),
                            'text': line.strip()[:240],
                            'allowlist_reason': reason,
                        })
    return rows


def summary(rows):
    by_category = {}
    by_file = {}
    for row in rows:
        by_category[row['category']] = by_category.get(row['category'], 0) + 1
        by_file[row['path']] = by_file.get(row['path'], 0) + 1
    return {
        'total': len(rows),
        'exempt': sum(1 for row in rows if row['allowlist_reason']),
        'actionable': sum(1 for row in rows if not row['allowlist_reason']),
        'by_category': dict(sorted(by_category.items())),
        'by_file': dict(sorted(by_file.items())),
    }


def render_text(rows):
    lines = [
        'legacy easyeda toolchain reference inventory',
        'scanned scopes: ' + ', '.join(INVENTORY_SCOPES),
        'categories: ' + ', '.join(sorted(CATEGORIES)),
        '',
    ]
    stats = summary(rows)
    lines.append('total=%d actionable=%d exempt=%d' % (
        stats['total'], stats['actionable'], stats['exempt']))
    lines.append('by category: ' + json.dumps(stats['by_category'],
                                              ensure_ascii=False, sort_keys=True))
    lines.append('')
    current = None
    for row in rows:
        if row['path'] != current:
            current = row['path']
            lines.append('=== %s' % current)
            if row['allowlist_reason']:
                lines.append('    ALLOWLIST: %s' % row['allowlist_reason'])
        lines.append('  %5d [%s] %s' % (row['line'], row['category'],
                                        row['text']))
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='machine-readable')
    parser.add_argument('--strict', action='store_true',
                        help='exit 1 when an actionable (non-exempt) reference remains')
    parser.add_argument('--out', help='write the inventory here')
    args = parser.parse_args(argv)
    rows = scan()
    text = (json.dumps({'simulated': True, 'summary': summary(rows),
                        'rows': rows}, ensure_ascii=False, indent=1)
            if args.json else render_text(rows))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding='utf-8')
        print(json.dumps(summary(rows), ensure_ascii=False, sort_keys=True))
    else:
        sys.stdout.write(text)
    actionable = summary(rows)['actionable']
    return 1 if (args.strict and actionable) else 0


if __name__ == '__main__':
    sys.exit(main())
