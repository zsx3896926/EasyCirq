#!/usr/bin/env python3
"""Read-only EasyEDA containers, pinned schema checks and viewer integration."""
from __future__ import annotations
import argparse
import hashlib
import html
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/easyeda-format'
VIEWER = ROOT / 'assets/ecosystem-viewer'
FORMAT_COMMIT = '4fcab1747d47b2ae01d7f93a485859970c5cf933'
VIEWER_COMMIT = 'a60b22d098d25850d1f28427e51dd2619b008ed9'
DOCS = {'PCB', 'FOOTPRINT', 'SCH_PAGE', 'SYMBOL', 'SIMULATION'}
SCHEMAS = {'DOCHEAD': 't-doc-head', 'PCB_LINE': 't-pcb-line',
           'FOOTPRINT_LINE': 't-pcb-line', 'PCB_VIA': 't-pcb-via',
           'FOOTPRINT_VIA': 't-pcb-via', 'SCH_PAGE_TEXT': 't-sch-text',
           'SYMBOL_TEXT': 't-sch-text', 'SCH_PAGE_WIRE': 't-wire',
           'SCH_PAGE_LINE': 't-sch-line', 'SYMBOL_LINE': 't-sch-line'}
ANNOTATIONS = {'$schema', 'title', 'description', 'default', 'examples', 'enumDescriptions'}
KEYWORDS = ANNOTATIONS | {'type', 'properties', 'required', 'enum', 'minimum',
                         'maximum', 'pattern', 'items'}
MAX_BYTES = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024


def strict_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def bad(value):
        raise ValueError('non-finite JSON number: ' + value)
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('non-finite JSON number')
        return parsed
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad, parse_float=finite_float)


def _type(value, name):
    return {'object': isinstance(value, dict), 'array': isinstance(value, list),
            'string': isinstance(value, str), 'boolean': type(value) is bool,
            'null': value is None,
            'number': (type(value) is int or (type(value) is float and math.isfinite(value))),
            'integer': type(value) is int}[name]


def _schema_unknown(schema, path):
    found = [path + ':' + key for key in schema.keys() - KEYWORDS]
    for name, child in schema.get('properties', {}).items():
        found += _schema_unknown(child, path + '.' + name)
    if isinstance(schema.get('items'), dict):
        found += _schema_unknown(schema['items'], path + '[]')
    return found


def _schema_check(value, schema, path='$'):
    errors, unsupported = [], _schema_unknown(schema, path)
    for key in schema.keys() - KEYWORDS:
        unsupported.append(path + ':' + key)
    types = schema.get('type')
    if types and not any(_type(value, t) for t in ([types] if isinstance(types, str) else types)):
        errors.append(path + ':type')
        return errors, unsupported
    if 'enum' in schema and not any(type(value) is type(v) and value == v for v in schema['enum']):
        errors.append(path + ':enum')
    if type(value) in (int, float):
        if type(value) is float and not math.isfinite(value):
            errors.append(path + ':finite')
        if 'minimum' in schema and value < schema['minimum']:
            errors.append(path + ':minimum')
        if 'maximum' in schema and value > schema['maximum']:
            errors.append(path + ':maximum')
    if isinstance(value, str) and 'pattern' in schema and re.search(schema['pattern'], value) is None:
        errors.append(path + ':pattern')
    if isinstance(value, dict):
        errors.extend(path + '.' + key + ':required' for key in schema.get('required', []) if key not in value)
        for key, child in schema.get('properties', {}).items():
            if key in value:
                a, b = _schema_check(value[key], child, path + '.' + key)
                errors += a; unsupported += b
    if isinstance(value, list) and 'items' in schema:
        for i, child in enumerate(value):
            a, b = _schema_check(child, schema['items'], path + '[' + str(i) + ']')
            errors += a; unsupported += b
    # Preflight unvisited child schemas too: unsupported constraints never disappear.
    for key, child in schema.get('properties', {}).items():
        if not isinstance(value, dict) or key not in value:
            _, b = _schema_check(None, child, path + '.' + key)
            unsupported += b
    return errors, sorted(set(unsupported))


def validate_primitive(doc_type, primitive, data):
    key = primitive.upper()
    if key != 'DOCHEAD' and not any(key.startswith(d + '_') for d in DOCS):
        if not doc_type:
            raise ValueError('explicit --doc required for bare primitive names')
        key = doc_type.upper() + '_' + key
    if doc_type and key != 'DOCHEAD' and not key.startswith(doc_type.upper() + '_'):
        raise ValueError('document/primitive prefix mismatch')
    name = SCHEMAS.get(key)
    if not name:
        return {'status': 'incomplete', 'valid': None, 'reason': 'schema_not_bundled', 'type': key}
    raw = (VENDOR / 'schemas' / (name + '.json')).read_bytes()
    schema = strict_json(raw.decode('utf-8-sig'))
    errors, unknown = _schema_check(data, schema)
    return {'schema': 'hds-format-conformance/v1', 'status': 'incomplete' if unknown else ('invalid' if errors else 'valid'),
            'valid': None if unknown else not errors, 'type': key, 'errors': errors,
            'unsupported_constraints': unknown, 'source_commit': FORMAT_COMMIT,
            'source_schema_sha256': hashlib.sha256(raw).hexdigest(),
            'host_validation': 'NOT RUN', 'semantic_validation': 'NOT RUN',
            'scope': 'payload conformity to pinned upstream schema only',
            'upstream_caveats': ['Schema required/type fields can disagree with documented real-client data; do not rewrite imported data to silence schema errors.']}


def inspect_records(raw):
    text = raw.decode('utf-8-sig')
    docs, errors, records, tombstones = [], [], 0, 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            outer_text, inner_text = line.split('||', 1)
            outer = strict_json(outer_text)
            payload = inner_text[:-1] if inner_text.endswith('|') else inner_text
            inner = strict_json(payload) if payload else None
            if not isinstance(outer, dict) or (inner is not None and not isinstance(inner, dict)):
                raise ValueError('record halves must be objects')
            kind = outer.get('type')
            if not isinstance(kind, str) or not kind:
                raise ValueError('missing record type')
            if inner is None:
                if kind in ('DOCHEAD', 'META', 'DELETE_DOC'):
                    raise ValueError('empty payload is forbidden for this record type')
                tombstones += 1
            if kind == 'DOCHEAD':
                if not all(isinstance(inner.get(k), str) and inner[k].strip() for k in ('docType', 'uuid')):
                    raise ValueError('missing document identity')
                docs.append({'type': inner['docType'], 'uuid': inner['uuid']})
            elif not docs:
                raise ValueError('body precedes DOCHEAD')
            elif (kind != 'DELETE_DOC' and 'id' not in outer) or type(outer.get('ticket')) is not int or outer['ticket'] < 0:
                raise ValueError('body record needs id and nonnegative integer ticket')
            elif kind == 'DELETE_DOC' and type(inner.get('isDelete')) is not bool:
                raise ValueError('DELETE_DOC requires boolean isDelete')
            records += 1
        except (ValueError, TypeError, RecursionError) as exc:
            errors.append({'line': number, 'reason': str(exc)})
    if not docs:
        errors.append({'line': None, 'reason': 'no DOCHEAD'})
    return {'records': records, 'tombstone_records': tombstones, 'documents': docs, 'errors': errors,
            'status': 'invalid' if errors else 'pass',
            'scope': 'line structure only; logical clocks, deletes, references and geometry NOT validated'}


def inspect_file(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('input exceeds 64 MiB limit')
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError('input grew beyond size limit')
    result = {'schema': 'hds-eda-file-inspection/v1', 'source_sha256': hashlib.sha256(raw).hexdigest(),
              'write_operations': 0, 'host_validation': 'NOT RUN', 'entries': []}
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            if len(infos) > 8000 or sum(i.file_size for i in infos) > MAX_TOTAL:
                raise ValueError('archive expanded size/count limit exceeded')
            seen = set()
            for i in infos:
                name = i.orig_filename
                p = PurePosixPath(name)
                if (not name or any(ord(c) < 32 for c in name) or chr(92) in name or p.is_absolute() or '..' in p.parts or
                        any(':' in part or part.endswith((' ', '.')) for part in p.parts) or
                        name.casefold() in seen or stat.S_ISLNK(i.external_attr >> 16) or i.flag_bits & 1):
                    raise ValueError('unsafe archive member: ' + name)
                seen.add(name.casefold())
                if i.is_dir():
                    continue
                if i.file_size > MAX_BYTES:
                    raise ValueError('member size limit exceeded')
                payload = z.read(i)  # CRC checked; no extraction.
                item = {'name': name, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
                if p.name == 'project2.json' or p.suffix.lower() == '.eprj3':
                    try:
                        meta = strict_json(payload.decode('utf-8-sig'))
                        if not isinstance(meta, dict):
                            raise ValueError('project metadata must be an object')
                        item['metadata_structure'] = 'pass'
                    except (ValueError, UnicodeError, RecursionError) as exc:
                        item['metadata_structure'] = 'invalid'
                        item['metadata_error'] = str(exc)
                if p.suffix.lower() in ('.epru', '.esch2', '.epcb2', '.esym2', '.epan2'):
                    item['records'] = inspect_records(payload)
                result['entries'].append(item)
            if not result['entries']:
                raise ValueError('empty archive is not an EDA project')
            known = any(PurePosixPath(i['name']).suffix.lower() in ('.eprj3', '.epru', '.esch2', '.epcb2', '.esym2', '.epan2') or PurePosixPath(i['name']).name == 'project2.json' for i in result['entries'])
            invalid = any(i.get('records', {}).get('errors') or i.get('metadata_structure') == 'invalid' for i in result['entries'])
            checked_records = any('records' in i for i in result['entries'])
            result['status'] = 'invalid' if invalid else ('pass' if known and checked_records else 'incomplete')
    else:
        result['records'] = inspect_records(raw)
        result['status'] = result['records']['status']
    result['scope'] = 'container integrity and record structure; not schema/electrical/host acceptance'
    return result


def preview_page(viewer_url, out):
    url = urlsplit(viewer_url)
    if url.scheme not in ('http', 'https') or url.hostname not in ('localhost', '127.0.0.1', '[::1]', '::1') or url.username or url.password:
        raise ValueError('viewer must be an explicitly supplied loopback HTTP(S) build')
    if url.fragment:
        raise ValueError('viewer URL fragment not allowed')
    target = Path(out)
    if target.suffix.lower() not in ('.html', '.htm') or target.name.casefold() == 'hds-viewer-adapter.js':
        raise ValueError('preview output must be an HTML file, not the reserved adapter path')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_name('hds-viewer-adapter.js').write_bytes((VIEWER / 'adapter.js').read_bytes())
    config = json.dumps({'url': viewer_url}, ensure_ascii=True).replace('<', '\\u003c')
    target.write_text('''<!doctype html><meta charset="utf-8"><title>HDS read-only review</title>
<p>Read-only project preview. Choose a file to send only to the configured local viewer. No DRC/host acceptance is provided. Serve this folder over localhost; file:// is unsupported.</p>
<input id="project" type="file"><input id="refs" placeholder="R1,C2"><button id="select">Locate</button>
<iframe id="viewer" title="Local EasyEDA viewer" style="width:100%;height:75vh"></iframe>
<pre id="status"></pre><script src="hds-viewer-adapter.js"></script><script>
const config = ''' + config + ''';
const frame = document.getElementById('viewer');
const adapter = HdsViewer.create(frame, config.url, window);
document.getElementById('project').onchange = async e => {
 try { const f=e.target.files[0]; if(!f)return; if(f.size>64*1024*1024)throw Error('File too large');
 const b=new Uint8Array(await f.arrayBuffer());let s='';for(let i=0;i<b.length;i++)s+=String.fromCharCode(b[i]);
 adapter.send('load',{files:[{name:f.name,dataBase64:btoa(s)}]}); }catch(e){document.getElementById('status').textContent=e.message;}
};
document.getElementById('select').onclick=()=>adapter.send('select',{designators:document.getElementById('refs').value.split(',').map(s=>s.trim()).filter(Boolean)});
adapter.onEvent=m=>document.getElementById('status').textContent=JSON.stringify(m,null,2);
</script>''', encoding='utf-8')
    return {'schema': 'hds-viewer-preview/v1', 'status': 'prepared', 'output': str(target),
            'viewer_url': viewer_url, 'viewer_commit_reviewed': VIEWER_COMMIT,
            'renderer_bundled': False, 'render_verified': 'NOT RUN', 'write_operations': 0,
            'notes': 'Use separately built/pinned easyeda-viewer; generated page is an integration adapter, not an official export.'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('inspect'); a.add_argument('--input', required=True)
    a = sub.add_parser('validate'); a.add_argument('--doc'); a.add_argument('--type', required=True); a.add_argument('--input', required=True)
    a = sub.add_parser('preview'); a.add_argument('--viewer-url', required=True); a.add_argument('--out', required=True)
    a = p.parse_args(argv)
    try:
        if a.command == 'inspect': result = inspect_file(a.input)
        elif a.command == 'validate': result = validate_primitive(a.doc, a.type, strict_json(Path(a.input).read_text(encoding='utf-8-sig')))
        else: result = preview_page(a.viewer_url, a.out)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0 if result['status'] in ('valid', 'pass', 'prepared') else 1
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, UnicodeError, RecursionError) as exc:
        print(json.dumps({'status': 'invalid_input', 'error': str(exc)})); return 2


# Keep JSON output parseable on Windows legacy console codepages.
import sys as _cli_sys
for _stream in (_cli_sys.stdout, _cli_sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors="backslashreplace")

if __name__ == '__main__':
    raise SystemExit(main())
