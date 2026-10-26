#!/usr/bin/env python3
"""A versioned, fail-closed cache for EDA reads.

The cache is deliberately dumb: it stores an already-validated JSON value under
a key and refuses to return it unless every freshness condition still holds.

Key:      project UUID + document UUID + action + SHA-256(canonical params).
Entry:    value + storedAt + caller versionTag + CLI/connector version.
Invalidation conditions (any one is a MISS, never a stale HIT):
  1. project or document differs;
  2. the caller's versionTag differs (bump it after save/reload/any mutation,
     e.g. from a save sequence or a content hash of the page snapshot);
  3. the requested CLI/connector version differs (when supplied);
  4. the entry is older than --ttl-seconds (when supplied);
  5. the entry is corrupt, has an unknown schema, or cannot be read;
  6. `invalidate` removed it explicitly.
A cache is never proof that a write landed. Reads used for write decisions must
be re-read after a mutation; this module only avoids repeated identical reads.

CLI:
  python eda_cache.py put --cache DIR --project P --document D --action A \
      --params '{"page":"P1"}' --version-tag SAVE_SEQ --cli-version 1.14.0 \
      --value page.json
  python eda_cache.py get ... --version-tag SAVE_SEQ [--ttl-seconds 300]
  python eda_cache.py invalidate --cache DIR [--project P] [--document D]
  python eda_cache.py stats --cache DIR
Exit: 0 hit/success, 1 miss, 2 invalid input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

CACHE_SCHEMA = 'eda-cache/v1'
MAX_BYTES = 16_000_000


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _key(project, document, action, params, tool_version=None):
    payload = {'project': project, 'document': document, 'action': action,
               'params': params, 'toolVersion': tool_version}
    digest = hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()
    return digest


def _entry_path(cache_dir, digest):
    return Path(cache_dir) / f'{digest}.json'


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1) + '\n'
    fd, temp = tempfile.mkstemp(prefix='.eda-cache-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _load_entry(path):
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError('entry exceeds size limit')
    data = json.loads(raw.decode('utf-8'))
    if not isinstance(data, dict) or data.get('schema') != CACHE_SCHEMA:
        raise ValueError('unknown cache schema')
    return data


def put(cache_dir, project, document, action, params, version_tag, cli_version,
        value, tool_version=None):
    digest = _key(project, document, action, params, tool_version)
    entry = {
        'schema': CACHE_SCHEMA,
        'key': {'project': project, 'document': document, 'action': action,
                'params': params, 'toolVersion': tool_version},
        'versionTag': version_tag,
        'cliVersion': cli_version,
        'toolVersion': tool_version,
        'storedAt': time.time(),
        'value': value,
    }
    path = _entry_path(cache_dir, digest)
    _atomic_write(path, entry)
    return {'status': 'stored', 'path': str(path), 'digest': digest}


def get(cache_dir, project, document, action, params, version_tag, cli_version=None,
        ttl_seconds=None, tool_version=None):
    digest = _key(project, document, action, params, tool_version)
    path = _entry_path(cache_dir, digest)
    if not path.exists():
        # A version-less lookup may still find an older key; do not do that
        # silently.  A missing key is a miss.
        return {'status': 'miss', 'reason': 'not_found'}
    try:
        entry = _load_entry(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {'status': 'miss', 'reason': 'corrupt_entry', 'detail': str(error)}
    key = entry.get('key') or {}
    if key.get('project') != project or key.get('document') != document \
            or key.get('action') != action or key.get('params') != params:
        return {'status': 'miss', 'reason': 'key_mismatch'}
    if key.get('toolVersion') != tool_version:
        return {'status': 'miss', 'reason': 'tool_version_mismatch',
                'expected': tool_version, 'stored': key.get('toolVersion')}
    if entry.get('versionTag') != version_tag:
        return {'status': 'miss', 'reason': 'version_tag_mismatch',
                'expected': version_tag, 'stored': entry.get('versionTag')}
    if cli_version is not None and entry.get('cliVersion') != cli_version:
        return {'status': 'miss', 'reason': 'cli_version_mismatch',
                'expected': cli_version, 'stored': entry.get('cliVersion')}
    if ttl_seconds is not None:
        stored = entry.get('storedAt')
        if type(stored) not in (int, float):
            return {'status': 'miss', 'reason': 'invalid_stored_at'}
        age = time.time() - stored
        if age < -60:
            return {'status': 'miss', 'reason': 'clock_skew'}
        if age > ttl_seconds:
            return {'status': 'miss', 'reason': 'ttl_expired', 'age_seconds': round(age, 3)}
    return {'status': 'hit', 'value': entry.get('value'), 'storedAt': entry.get('storedAt'),
            'versionTag': entry.get('versionTag'), 'cliVersion': entry.get('cliVersion'),
            'digest': digest}


def invalidate(cache_dir, project=None, document=None):
    root = Path(cache_dir)
    removed = 0
    if not root.exists():
        return {'status': 'invalidated', 'removed': 0}
    for path in root.glob('*.json'):
        try:
            entry = _load_entry(path)
        except (OSError, ValueError, json.JSONDecodeError):
            # A corrupt entry cannot be attributed; leave it for stats/cleanup.
            continue
        key = entry.get('key') or {}
        if project is not None and key.get('project') != project:
            continue
        if document is not None and key.get('document') != document:
            continue
        path.unlink()
        removed += 1
    return {'status': 'invalidated', 'removed': removed}


def stats(cache_dir):
    root = Path(cache_dir)
    entries = projects = 0
    documents = set()
    total_bytes = 0
    reasons = {}
    if root.exists():
        for path in root.glob('*.json'):
            total_bytes += path.stat().st_size
            try:
                entry = _load_entry(path)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                reasons['corrupt'] = reasons.get('corrupt', 0) + 1
                continue
            key = entry.get('key') or {}
            entries += 1
            if key.get('project'):
                projects = 1 if projects == 0 else projects
            documents.add((key.get('project'), key.get('document')))
    return {'status': 'stats', 'entries': entries, 'projects': len({p for p, _ in documents}),
            'documents': len(documents), 'bytes': total_bytes, 'corrupt': reasons.get('corrupt', 0)}


def _parse_params(value):
    if value is None:
        return {}
    if os.path.exists(value):
        return json.loads(Path(value).read_text(encoding='utf-8'))
    return json.loads(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    def add_key_args(target):
        target.add_argument('--cache', required=True)
        target.add_argument('--project', required=True)
        target.add_argument('--document', required=True)
        target.add_argument('--action', required=True)
        target.add_argument('--params', default='{}')
        target.add_argument('--version-tag', required=True)
        target.add_argument('--tool-version',
                            help='caller/tool version that affects the result; '
                                 'part of the cache key')

    put_parser = sub.add_parser('put')
    add_key_args(put_parser)
    put_parser.add_argument('--cli-version')
    put_parser.add_argument('--value', required=True)

    get_parser = sub.add_parser('get')
    add_key_args(get_parser)
    get_parser.add_argument('--cli-version')
    get_parser.add_argument('--ttl-seconds', type=float)

    invalidate_parser = sub.add_parser('invalidate')
    invalidate_parser.add_argument('--cache', required=True)
    invalidate_parser.add_argument('--project')
    invalidate_parser.add_argument('--document')

    stats_parser = sub.add_parser('stats')
    stats_parser.add_argument('--cache', required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == 'put':
            params = _parse_params(args.params)
            value = json.loads(Path(args.value).read_text(encoding='utf-8-sig'))
            result = put(args.cache, args.project, args.document, args.action,
                         params, args.version_tag, args.cli_version, value,
                         tool_version=args.tool_version)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == 'get':
            params = _parse_params(args.params)
            result = get(args.cache, args.project, args.document, args.action,
                         params, args.version_tag, args.cli_version,
                         args.ttl_seconds, tool_version=args.tool_version)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result['status'] == 'hit' else 1
        if args.command == 'invalidate':
            print(json.dumps(invalidate(args.cache, args.project, args.document),
                             ensure_ascii=False))
            return 0
        if args.command == 'stats':
            print(json.dumps(stats(args.cache), ensure_ascii=False))
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)},
                         ensure_ascii=False))
        return 2
    return 2


if __name__ == '__main__':
    sys.exit(main())
