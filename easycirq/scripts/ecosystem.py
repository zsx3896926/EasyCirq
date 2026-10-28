#!/usr/bin/env python3
"""One offline entry point for reviewed EasyEDA ecosystem integrations."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TOOLS = {'docs': 'ecosystem_docs.py', 'routing': 'ecosystem_routing.py',
         'capture': 'ecosystem_capture.py', 'reuse': 'ecosystem_reuse.py',
         'files': 'ecosystem_files.py'}

def registry():
    data = json.loads((ROOT.parent / 'assets/ecosystem/registry.json').read_text(encoding='utf-8-sig'))
    data['entry_points'] = {key: {'script': value, 'available': (ROOT / value).is_file(),
                                 'live_write': False} for key, value in TOOLS.items()}
    return data

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('registry')
    a = sub.add_parser('run'); a.add_argument('--tool', choices=sorted(TOOLS), required=True)
    a.add_argument('arguments', nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    if args.action == 'registry':
        try:
            print(json.dumps(registry(), ensure_ascii=False, indent=2)); return 0
        except (OSError, ValueError, TypeError) as exc:
            print(json.dumps({'status': 'invalid_input', 'error': str(exc)})); return 2
    script = ROOT / TOOLS[args.tool]
    if not script.is_file():
        print(json.dumps({'status': 'blocked', 'reason': 'integration_script_missing'})); return 1
    rest = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    return subprocess.run([sys.executable, str(script), *rest], shell=False).returncode

# Keep JSON output parseable on Windows legacy console codepages.
import sys as _cli_sys
for _stream in (_cli_sys.stdout, _cli_sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors="backslashreplace")

if __name__ == '__main__':
    raise SystemExit(main())
