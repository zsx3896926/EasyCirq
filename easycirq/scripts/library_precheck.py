#!/usr/bin/env python3
"""Batch-check design-source part identities before drawing or PCB import.

This is an offline completeness/identity check, not a library query. It answers
"does every planned part have a stable device identity and a plausible shared
identity table?" It cannot prove that the symbol, footprint or pin mapping is
correct; that still needs a library read-back and a placed-instance check.

Design input: ``parts[]`` with ref/page/value/package/mpn/lcsc/lib/dev
(design.json style). Device table input (optional) accepts:
  * {role: {deviceUuid, libraryUuid, lcsc, value, package, mpn, footprint, pins}}
  * {ref: {...}} or a list of such objects.

Usage:
  python library_precheck.py --design design.json --devices devices.json [--strict]
Exit: 0 pass, 1 blocking finding, 2 invalid input.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPORT_SCHEMA = 'library-precheck/v1'
MAX_BYTES = 8_000_000
NON_LCSC = {'non_lcsc', 'pending', 'not_lcsc'}


def _read(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f'{path}: exceeds {MAX_BYTES} bytes')
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, (dict, list)):
        raise ValueError(f'{path}: JSON object or list required')
    return data


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _identity(entry, where):
    if not isinstance(entry, dict):
        raise ValueError(f'{where}: object required')
    device = entry.get('deviceUuid') or entry.get('dev')
    library = entry.get('libraryUuid') or entry.get('lib')
    return {
        'deviceUuid': device.strip() if _text(device) else None,
        'libraryUuid': library.strip() if _text(library) else None,
        'lcsc': entry.get('lcsc'),
        'value': entry.get('value'),
        'package': entry.get('package'),
        'mpn': entry.get('mpn'),
        'footprint': entry.get('footprint'),
        'pins': entry.get('pins'),
    }


def load_devices(path):
    data = _read(path)
    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        if isinstance(data.get('parts'), list):
            entries = data['parts']
        elif isinstance(data.get('devices'), list):
            entries = data['devices']
        else:
            entries = list(data.values())
    out = []
    for index, entry in enumerate(entries):
        identity = _identity(entry, f'{path}[{index}]')
        if identity['deviceUuid'] or identity['lcsc']:
            out.append(identity)
    if not out:
        raise ValueError(f'{path}: no entries with deviceUuid or lcsc')
    return out


def load_design(path):
    data = _read(path)
    parts = data.get('parts') if isinstance(data, dict) else None
    if not isinstance(parts, list):
        raise ValueError(f'{path}: parts[] required')
    out = []
    seen = set()
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f'{path}: parts[{index}] must be an object')
        ref = part.get('ref')
        if not _text(ref):
            raise ValueError(f'{path}: parts[{index}].ref required')
        if ref in seen:
            raise ValueError(f'{path}: duplicate ref {ref}')
        seen.add(ref)
        out.append({
            'ref': ref,
            'page': part.get('page'),
            'value': part.get('value'),
            'package': part.get('package'),
            'mpn': part.get('mpn'),
            'lcsc': part.get('lcsc'),
            'libraryUuid': part.get('lib') or part.get('libraryUuid'),
            'deviceUuid': part.get('dev') or part.get('deviceUuid'),
        })
    return out


def _lcsc_state(value):
    if _text(value):
        return 'number'
    if isinstance(value, dict) and value.get('status') in NON_LCSC:
        return 'declared_non_lcsc'
    return 'missing'


def analyze(parts, devices):
    findings = []
    blocking = 0
    warnings = 0

    def add(level, code, where, message):
        nonlocal blocking, warnings
        findings.append({'level': level, 'code': code, 'where': where, 'message': message})
        if level == 'blocking':
            blocking += 1
        else:
            warnings += 1

    for part in parts:
        where = part['ref']
        if not _text(part.get('value')) and not _text(part.get('mpn')):
            add('blocking', 'missing_value', where, 'value 与 mpn 都为空；无法确认器件')
        if not _text(part.get('package')):
            add('blocking', 'missing_package', where, '缺少 package；PCB/封装无法核对')
        if not _text(part.get('libraryUuid')):
            add('blocking', 'missing_library_uuid', where, '缺少库 UUID；放置身份不稳定')
        if not _text(part.get('deviceUuid')):
            add('blocking', 'missing_device_uuid', where, '缺少器件 UUID；无法批量解析库身份')
        state = _lcsc_state(part.get('lcsc'))
        if state == 'missing':
            add('blocking', 'missing_lcsc', where,
                '缺少 C 号；非立创料请用 {"status":"non_lcsc","note":"..."} 显式声明')
        elif state == 'declared_non_lcsc':
            add('warning', 'non_lcsc_declared', where, '已声明非立创料；采购与 SMT 需另核')

    by_device = defaultdict(list)
    by_lcsc = defaultdict(list)
    for part in parts:
        if _text(part.get('deviceUuid')):
            by_device[part['deviceUuid'].strip()].append(part)
        if _text(part.get('lcsc')):
            by_lcsc[part['lcsc'].strip()].append(part)

    for device, group in by_device.items():
        signatures = {(p.get('package'), p.get('mpn'), p.get('value')) for p in group}
        if len(signatures) > 1:
            refs = sorted(p['ref'] for p in group)
            add('blocking', 'device_identity_conflict', device,
                f'同一 deviceUuid 被用于不同 package/mpn/value: {refs}')
    for lcsc, group in by_lcsc.items():
        signatures = {(p.get('package'), p.get('mpn')) for p in group}
        if len(signatures) > 1:
            refs = sorted(p['ref'] for p in group)
            add('warning', 'same_lcsc_different_package_mpn', lcsc,
                f'同一 C 号出现在不同 package/mpn: {refs}')

    table_devices = set()
    table_lcsc = set()
    table_pins = {}
    for item in devices or []:
        if item['deviceUuid']:
            table_devices.add(item['deviceUuid'])
            table_pins[item['deviceUuid']] = item.get('pins')
        if _text(item['lcsc']):
            table_lcsc.add(item['lcsc'].strip())

    not_in_table = 0
    if devices is not None:
        for part in parts:
            device = (part.get('deviceUuid') or '').strip()
            lcsc = part['lcsc'].strip() if _text(part.get('lcsc')) else None
            if device:
                if device not in table_devices:
                    not_in_table += 1
                    add('blocking', 'identity_not_in_table', part['ref'],
                        f'device {device!r} 不在提供的身份表中（lcsc {lcsc!r}）')
            elif lcsc and lcsc not in table_lcsc:
                not_in_table += 1
                add('blocking', 'identity_not_in_table', part['ref'],
                    f'lcsc {lcsc!r} 不在提供的身份表中')
            if device in table_pins and table_pins[device] is not None:
                pins = table_pins[device]
                if not isinstance(pins, (int, list)) or (isinstance(pins, list) and not pins):
                    add('warning', 'device_without_pins', part['ref'],
                        f'身份表中的 device {device!r} 没有可用引脚数')
                elif isinstance(pins, int) and pins <= 0:
                    add('warning', 'device_without_pins', part['ref'],
                        f'身份表中的 device {device!r} 引脚数为 {pins}')

    status = 'blocking' if blocking else ('warning' if warnings else 'pass')
    return {
        'schema': REPORT_SCHEMA,
        'status': status,
        'summary': {
            'parts': len(parts),
            'device_identities': len(by_device),
            'lcsc_numbers': len(by_lcsc),
            'table_entries': len(devices or []),
            'blocking_findings': blocking,
            'warnings': warnings,
            'identity_not_in_table': not_in_table,
        },
        'findings': findings,
        'not_checked': [
            '器件库中 symbol/footprint 的真实存在性与几何',
            '引脚号与符号引脚、PCB 焊盘的映射',
            '库存、价格、MOQ、SMT 可贴状态（需实时查询）',
            '替代料的电气/时序等价性',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design', required=True)
    parser.add_argument('--devices')
    parser.add_argument('--strict', action='store_true',
                        help='treat warnings as blocking (exit 1)')
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    try:
        parts = load_design(args.design)
        devices = load_devices(args.devices) if args.devices else None
        report = analyze(parts, devices)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({'schema': REPORT_SCHEMA, 'status': 'invalid_input',
                          'error': str(error)}, ensure_ascii=False))
        return 2
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
        print(json.dumps({'schema': REPORT_SCHEMA, 'status': report['status'],
                          'out': args.out, 'findings': len(report['findings'])},
                         ensure_ascii=False))
    else:
        print(text)
    failed = report['summary']['blocking_findings'] > 0 or (
        args.strict and report['summary']['warnings'] > 0)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
