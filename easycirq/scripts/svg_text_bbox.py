#!/usr/bin/env python3
"""Measure every rendered <text> in an official EasyEDA SVG export.

Why a browser: ``visible_text.bboxes`` enumerates only free text and shown
attributes (72 rows on the photo-led page), while the SVG renders border labels,
title-block fields, pin names/numbers and marker net names too (134 rows).  A
text that never appears in an API listing is still visible and can still be an
orphan, so strict acceptance needs the rendered set.

The SVG is sanitized (script/event/foreignObject removed), wrapped in a local
HTML page, and measured with a headless Chromium browser via ``--dump-dom``.
Output bbox is in the SVG's exported user coordinates (y down, so a model y of
10 appears as -10).  ``layout_from_easyeda.py`` flips it to EasyEDA raw y-up.

This is an offline measurement adapter.  It never calls or edits EasyEDA.

Usage:
  python svg_text_bbox.py page.svg --out svg-text-bbox.json
  python svg_text_bbox.py page.svg --browser <msedge/chrome> --timeout 60
Exit 0: measured; 2: unsupported/invalid input or browser failure.
"""
import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VIEWBOX = re.compile(r'<svg\b[^>]*\bviewBox="([^"]+)"', re.I)
SCRIPT = re.compile(r'<script\b[^>]*>.*?</script\s*>', re.I | re.S)
FOREIGN = re.compile(r'<foreignObject\b[^>]*>.*?</foreignObject\s*>', re.I | re.S)
EVENT = re.compile(r'\s+on\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.I)
RESULT = re.compile(r'<pre\b[^>]*id="hds-result"[^>]*>(.*?)</pre>', re.I | re.S)

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><style>html,body{{margin:0;padding:0}}</style></head>
<body>{svg}
<script>
(function() {{
  const svg = document.querySelector('svg');
  const vb = (svg.getAttribute('viewBox') || '0 0 0 0').trim().split(/[ ,]+/).map(Number);
  const rows = [];
  for (const el of svg.querySelectorAll('text')) {{
    if (el.closest('defs')) continue;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    if (!el.getClientRects().length) continue;
    let bb;
    try {{ bb = el.getBBox(); }} catch (error) {{ continue; }}
    const m = el.getCTM();
    if (!m || !(bb.width > 0) || !(bb.height > 0)) continue;
    const points = [
      [bb.x, bb.y], [bb.x + bb.width, bb.y],
      [bb.x, bb.y + bb.height], [bb.x + bb.width, bb.y + bb.height]
    ];
    const xs = [], ys = [];
    for (const [x, y] of points) {{
      // getCTM maps to the SVG viewport; undo the viewBox origin to keep
      // exported user coordinates (EasyEDA raw units).
      xs.push(m.a * x + m.c * y + m.e + (vb[0] || 0));
      ys.push(m.b * x + m.d * y + m.f + (vb[1] || 0));
    }}
    rows.push({{
      id: el.id || '',
      text: (el.textContent || '').trim(),
      bbox: [Math.min.apply(null, xs), Math.min.apply(null, ys),
             Math.max.apply(null, xs), Math.max.apply(null, ys)]
    }});
  }}
  const pre = document.createElement('pre');
  pre.id = 'hds-result';
  pre.textContent = btoa(unescape(encodeURIComponent(JSON.stringify(
    {{count: rows.length, rows: rows}}))));
  document.body.appendChild(pre);
}})();
</script></body></html>
"""


def browser_path(explicit=None):
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return str(path)
        raise ValueError(f'browser not found: {path}')
    if os.environ.get('HDS_SVG_BROWSER'):
        path = Path(os.environ['HDS_SVG_BROWSER'])
        if path.is_file():
            return str(path)
        raise ValueError(f'HDS_SVG_BROWSER not found: {path}')
    candidates = [
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    for name in ('msedge', 'chrome', 'chromium', 'chromium-browser'):
        found = shutil.which(name)
        if found:
            return found
    raise ValueError('no Chromium browser found; pass --browser or set HDS_SVG_BROWSER')


def sanitize(svg_text):
    cleaned = SCRIPT.sub('', svg_text)
    cleaned = FOREIGN.sub('', cleaned)
    return EVENT.sub('', cleaned)


def measure(svg_text, browser, timeout=60):
    match = VIEWBOX.search(svg_text)
    if not match:
        raise ValueError('SVG viewBox required for coordinate provenance')
    values = [float(value) for value in match.group(1).replace(',', ' ').split()]
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        raise ValueError('SVG viewBox must be four finite numbers with positive size')
    page = PAGE.format(svg=sanitize(svg_text))
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        source = folder / 'measure.html'
        source.write_text(page, encoding='utf-8')
        profile = folder / 'profile'
        command = [browser, '--headless=new', '--disable-gpu', '--no-first-run',
                   '--disable-extensions', '--disable-background-networking',
                   f'--user-data-dir={profile}', '--virtual-time-budget=5000',
                   '--dump-dom', source.as_uri()]
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise ValueError(f'browser timed out after {timeout}s') from error
    stdout = result.stdout.decode('utf-8', 'replace')
    match = RESULT.search(stdout)
    if not match:
        detail = result.stderr.decode('utf-8', 'replace')[-500:]
        raise ValueError('browser did not return a measurement payload: ' + detail)
    try:
        payload = json.loads(base64.b64decode(html.unescape(match.group(1))).decode('utf-8'))
    except (ValueError, TypeError) as error:
        raise ValueError('measurement payload is not JSON') from error
    rows = payload.get('rows')
    if not isinstance(rows, list) or payload.get('count') != len(rows):
        raise ValueError('measurement payload count mismatch')
    for index, row in enumerate(rows):
        box = row.get('bbox')
        if (not isinstance(box, list) or len(box) != 4
                or any(type(value) not in (int, float) for value in box)
                or box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError(f'rows[{index}].bbox invalid')
    return {'count': len(rows), 'viewBox': values,
            'coordinateSystem': 'schematic-raw-y-up; measured from rendered SVG',
            'rows': rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('svg', type=Path)
    parser.add_argument('--browser', help='Chromium/Edge executable')
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.timeout < 5 or args.timeout > 600:
            raise ValueError('timeout must be in 5..600 seconds')
        svg_text = args.svg.read_text(encoding='utf-8-sig')
        if '<svg' not in svg_text.lower():
            raise ValueError('input is not an SVG document')
        result = measure(svg_text, browser_path(args.browser), args.timeout)
        result['sourceSha256'] = __import__('hashlib').sha256(
            args.svg.read_bytes()).hexdigest()
        output = json.dumps(result, ensure_ascii=False, indent=1)
        if args.out:
            args.out.write_text(output + '\n', encoding='utf-8')
        print(json.dumps({'status': 'measured', 'count': result['count'],
                          'viewBox': result['viewBox'],
                          'out': str(args.out) if args.out else None},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)},
                         ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
