#!/usr/bin/env python3
"""Offline advisory scan and access-block log summary. Does not enforce network isolation."""
import argparse
import ast
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

DOMAINS = ('lceda.cn', 'jlcpcb.com', 'szlcsc.com')
EXTENSIONS = {'.py', '.ps1', '.psm1', '.sh', '.bash', '.bat', '.cmd', '.js', '.mjs', '.cjs', '.ts'}
SKIP = {'.git', 'node_modules', '__pycache__', '.venv', 'venv'}
HOST_RE = re.compile(r'(?i)(?:https?://)?(?:[a-z0-9_-]+\.)*(?:lceda\.cn|jlcpcb\.com|szlcsc\.com)(?:[^\s\"\'<>`)]*)')
CLIENT_RE = re.compile(r'Invoke-WebRequest|Invoke-RestMethod|requests\.|urllib|httpx|http\.client|HTTPS?Connection|axios|fetch\s*\(|curl\b|wget\b|WebClient|HttpClient', re.I)
LOG_RE = re.compile(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\].*?(?:代理响应失败|HTTP(?:/\S+)?|status(?:Code)?[\s:=]+|response[\s:=]+)\s*418\s+(\S+)', re.I)

def restricted(value):
    try:
        host = urlsplit(value if '://' in value else 'https://' + value).hostname
        host = host.lower().rstrip('.') if host else None
        return bool(host and any(host.lower() == d or host.lower().endswith('.' + d) for d in DOMAINS))
    except ValueError:
        return False

def fullname(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute): return fullname(node.value) + '.' + node.attr
    if isinstance(node, ast.Call): return fullname(node.func) + '()'
    return ''

def python_findings(text):
    tree = ast.parse(text)
    names, aliases = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names: aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom):
            for item in node.names: aliases[item.asname or item.name] = (node.module or '') + '.' + item.name
    def resolve(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
        if isinstance(node, ast.Name): return names.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = resolve(node.left), resolve(node.right)
            if left is not None and right is not None: return left + right
        return None
    for _ in range(3):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value = resolve(node.value)
                if value is not None:
                    for dest in node.targets:
                        if isinstance(dest, ast.Name): names[dest.id] = value
    findings, covered = [], set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call): continue
        name = fullname(node.func)
        for alias, original in aliases.items():
            if name == alias or name.startswith(alias + '.'):
                name = original + name[len(alias):]; break
        if not CLIENT_RE.search(name): continue
        for arg in [*node.args, *(x.value for x in node.keywords)]:
            value = resolve(arg)
            if value and restricted(value):
                findings.append({'line':node.lineno, 'severity':'ERROR', 'reason':'static request target', 'target':value})
                covered.add(value)
    # Unresolved references are advisory, never a proof that execution is safe.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value not in covered:
            for match in HOST_RE.findall(node.value):
                if restricted(match): findings.append({'line':node.lineno, 'severity':'REVIEW', 'reason':'domain reference; execution unresolved', 'target':match})
    return findings

def scan(root, excludes=()):
    findings, errors, count = [], [], 0
    if not root.is_dir():
        return {'status':'unknown', 'scripts_scanned':0, 'findings':[], 'inspection_errors':[{'error':'scan root is not a directory'}], 'network_enforced':False}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and not (Path(base)/d).is_symlink() and not (hasattr(Path(base)/d, 'is_junction') and (Path(base)/d).is_junction())]
        for name in files:
            path = Path(base)/name
            if path.suffix.lower() not in EXTENSIONS or path.resolve() == Path(__file__).resolve(): continue
            if any(path.match(x) for x in excludes): continue
            count += 1
            try:
                if path.is_symlink(): raise ValueError('linked file not inspected')
                text = path.read_text(encoding='utf-8-sig')
                if path.suffix.lower() == '.py': refs = python_findings(text)
                else:
                    # Conservative heuristic for shell/JS: not a dataflow or runtime analysis.
                    lines = [re.sub(r'^\s*(?:#|//|REM\b).*$', '', line, flags=re.I) for line in text.splitlines()]
                    client = any(CLIENT_RE.search(line) for line in lines)
                    refs = [{'line':i, 'severity':'ERROR' if client else 'REVIEW', 'reason':'script heuristic', 'target':host}
                            for i,line in enumerate(lines,1) for host in HOST_RE.findall(line) if restricted(host)]
                for ref in refs: findings.append(dict(ref, file=str(path.relative_to(root))))
            except (OSError, UnicodeError, ValueError, SyntaxError) as exc: errors.append({'file':str(path.relative_to(root)), 'error':str(exc)})
    status = 'unknown' if errors else 'violations' if any(x['severity']=='ERROR' for x in findings) else 'review' if findings else 'no_findings'
    return {'status':status, 'scripts_scanned':count, 'findings':findings, 'inspection_errors':errors,
            'network_enforced':False, 'note':'Static advisory only; dynamic URLs and runtime behavior may be missed.'}

def default_log():
    base = Path.home()/'Documents/LCEDA-Pro/logs/warn'
    return base/(dt.date.today().strftime('%Y%m%d')+'.log')

def eda_log(path, cooldown_min=10):
    try: text = path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc: return {'status':'unknown', 'error':str(exc), 'hits':None, 'service_recovered':None}
    hits, invalid = [], 0
    for line in text.splitlines():
        m = LOG_RE.search(line)
        if m:
            try: stamp = dt.datetime.strptime(m[1], '%Y-%m-%d %H:%M:%S')
            except ValueError: invalid += 1; continue
            hits.append(stamp)
        elif re.search(r'\b418\b',line): invalid += 1
    if invalid: return {'status':'unknown','hits':len(hits), 'unparsed_418_lines':invalid, 'service_recovered':None}
    if not hits: return {'status':'no_observed_block', 'hits':0, 'service_recovered':None}
    last = max(hits); until = last + dt.timedelta(minutes=cooldown_min)
    return {'status':'cooling' if dt.datetime.now() < until else 'eligible_for_client_verification',
            'hits':len(hits), 'first':str(min(hits)), 'last':str(last), 'estimated_cooldown_until':str(until),
            'policy_minutes':cooldown_min, 'service_recovered':None,
            'note':'Local-log estimate only; other clients and shared-egress requests are not observed.'}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='mode', required=True)
    sp = sub.add_parser('scan');sp.add_argument('root',type=Path);sp.add_argument('--exclude',action='append',default=[]);sp.add_argument('--json',action='store_true')
    lp = sub.add_parser('eda-log');lp.add_argument('--log',type=Path);lp.add_argument('--cooldown-min',type=int,default=10);lp.add_argument('--json',action='store_true')
    args = ap.parse_args()
    if args.mode == 'scan':
        if not args.root.is_dir(): ap.error('scan root is not a directory')
        report = scan(args.root,args.exclude)
    else:
        if args.cooldown_min < 10: ap.error('conservative cooldown must be >=10 minutes')
        report = eda_log(args.log or default_log(),args.cooldown_min)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']=='unknown': return 2
    return 1 if report['status'] in ('review','violations','cooling') else 0

if __name__ == '__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'): stream.reconfigure(encoding='utf8',errors='replace')
    sys.exit(main())
