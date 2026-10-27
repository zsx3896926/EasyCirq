#!/usr/bin/env python3
"""Offline API/SDK documentation lookup and help plans; no EDA execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

SCHEMA = 'hds-ecosystem-docs/v1'
MAX_FILES = 4000
MAX_FILE_BYTES = 2_000_000

def digest(data):
    return hashlib.sha256(data).hexdigest()

def scan(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Documentation root must be a directory')
    files = {}
    total_bytes = 0
    for count, path in enumerate(root.rglob('*'), 1):
        if count > 20000:
            raise ValueError('Documentation entry budget exceeded')
        if path.is_symlink():
            raise ValueError('Symlink in documentation source: ' + str(path))
        if not path.is_file() or path.suffix.lower() not in ('.md', '.ts', '.json'):
            continue
        if any(part in ('node_modules', '.git', 'dist') for part in path.relative_to(root).parts):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError('Documentation input too large: ' + str(path))
        total_bytes += path.stat().st_size
        if total_bytes > 64 * 1024 * 1024:
            raise ValueError('Documentation byte budget exceeded')
        raw = path.read_bytes()
        raw.decode('utf-8-sig')
        files[path.relative_to(root).as_posix()] = digest(raw)
        if len(files) > MAX_FILES:
            raise ValueError('Documentation file budget exceeded')
    if not files:
        raise ValueError('No measured documentation files')
    return root, files

def index(root, provider, product_version='unknown'):
    if provider not in ('official-cli', 'api-skill', 'sdk'):
        raise ValueError('Unknown provider')
    _, files = scan(root)
    fingerprint = digest(json.dumps(files, sort_keys=True).encode())
    return {'schema': SCHEMA, 'status': 'indexed', 'provider': provider,
            'product_version': product_version, 'version_basis': 'caller_declared',
            'files': files, 'snapshot_sha256': fingerprint,
            'runtime_help_required': True, 'live_eda': 'NOT RUN'}

def query(root, evidence, text, limit=12):
    if not isinstance(evidence, dict) or evidence.get('schema') != SCHEMA or not isinstance(evidence.get('files'), dict):
        raise ValueError('Invalid documentation index')
    root, files = scan(root)
    if (files != evidence['files'] or
        digest(json.dumps(files, sort_keys=True).encode()) != evidence.get('snapshot_sha256')):
        raise ValueError('Stale documentation index; rebuild from current files')
    terms = [t.lower() for t in re.findall(r'[\w]+', text, re.UNICODE)]
    if not terms or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Nonempty query and limit 1..100 required')
    hits = []
    for name in files:
        raw = (root / name).read_bytes()
        if digest(raw) != files[name]:
            raise ValueError('Source changed during query; rebuild index')
        lines = raw.decode('utf-8-sig').splitlines()
        for line_number, line in enumerate(lines, 1):
            score = sum(t in line.lower() for t in terms)
            if score == len(terms):
                hits.append({'path': name, 'line': line_number,
                             'text': line[:900], 'source_sha256': files[name],
                             'score': score})
    hits.sort(key=lambda h: (-h['score'], h['path'], h['line']))
    return {'schema': SCHEMA, 'status': 'found' if hits else 'not_found',
            'matches': hits[:limit], 'total_matches': len(hits),
            'snapshot_sha256': evidence['snapshot_sha256'],
            'runtime_help_required': True, 'live_eda': 'NOT RUN'}

def help_plan(keyword, executable=None):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', keyword):
        raise ValueError('Use one English capability keyword')
    exe = executable or shutil.which('lceda-pro') or shutil.which('easyeda-pro')
    return {'schema': SCHEMA, 'status': 'planned' if exe else 'blocked',
            'executable': exe, 'commands': [] if not exe else
            [[str(exe), '--help'], [str(exe), '--search', keyword]],
            'executed': False, 'live_eda': 'NOT RUN',
            'next': 'Inspect installed help and doc command signatures; bind one owned session before any operation. Do not infer manufacturing export success from command discovery.'}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('index'); a.add_argument('--root', required=True)
    a.add_argument('--provider', choices=['official-cli', 'api-skill', 'sdk'], required=True)
    a.add_argument('--product-version', default='unknown'); a.add_argument('--out', required=True)
    a = sub.add_parser('query'); a.add_argument('--root', required=True)
    a.add_argument('--index', required=True); a.add_argument('--query', required=True)
    a.add_argument('--limit', type=int, default=12); a.add_argument('--out')
    a = sub.add_parser('help-plan'); a.add_argument('--keyword', required=True)
    a.add_argument('--executable'); a.add_argument('--out')
    args = p.parse_args(argv)
    output_allowed = False
    try:
        if args.action in ('index', 'query') and args.out:
            try:
                Path(args.out).resolve().relative_to(Path(args.root).resolve())
            except ValueError:
                pass
            else:
                raise ValueError('Write index/query output outside the documentation source root')
        output_allowed = True
        if args.action == 'index': result = index(args.root, args.provider, args.product_version)
        elif args.action == 'query': result = query(args.root, json.loads(Path(args.index).read_text(encoding='utf-8-sig')), args.query, args.limit)
        else: result = help_plan(args.keyword, args.executable)
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(encoded, encoding='utf-8')
        print(encoded)
        return 1 if result['status'] in ('blocked', 'not_found') else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        error = json.dumps({'schema': SCHEMA, 'status': 'invalid_input', 'error': str(exc)})
        if output_allowed and args.out:
            try:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(error + '\n', encoding='utf-8')
            except OSError:
                pass
        print(error)
        return 2

# Keep JSON output parseable on Windows legacy console codepages.
import sys as _cli_sys
for _stream in (_cli_sys.stdout, _cli_sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors="backslashreplace")

if __name__ == '__main__':
    raise SystemExit(main())
