#!/usr/bin/env python3
"""Read-only generator/checker for variant BOM closures and needed quantities.

No network access and no file writes. Standard output is exactly one JSON object.
Exit codes: 0 = no findings, 1 = findings need review, 2 = invalid input.

The script expands each variant's requires/conflicts/forbidden closure against a
master BOM, rejects mix-ups between mutually exclusive assembly groups, and
reports only the needed quantity per reference. Packaging steps, MOQ, price and
stock are never invented: when a package step is unknown the order quantity is
omitted and order_qty_status is 待查.
"""
import argparse
from decimal import Decimal, ROUND_CEILING
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

SCHEMA = 'variant-bom/v1'
BOARD_VERIFIED = False
EXECUTION = 'OFFLINE_PLANNING'
HARDWARE_EXECUTION = 'NOT RUN'
UNKNOWN = '待查'
SEVERITIES = ('blocking', 'warning', 'unknown')
MASTER_FIELDS = ('ref', 'per_board')
MASTER_OPTIONAL = ('mpn', 'exclusive_group', 'requires', 'package_step', 'note')
VARIANT_FIELDS = ('id', 'boards', 'attrition_rate', 'min_spare', 'requires',
                  'conflicts', 'forbidden', 'dnp', 'firmware_config',
                  'test_delta')
VARIANT_OPTIONAL = ('note',)
NOT_CHECKED = [
    '包装步进、MOQ、价格、库存与交期（未核）',
    '替代料、批次/序列号与实物一致性',
    'DNP/CPL、丝印与固件配置的一致性',
    '混料风险只按声明闭包检查，未核实物与产线',
    'needed 只是数量推算，不含自有料抵扣与损耗实测',
]


class InputError(ValueError):
    """The supplied variant package is not structurally valid input."""


def text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise InputError('%s: require nonblank string without edge whitespace' % label)
    return value


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise InputError('%s: require integer >= %d' % (label, minimum))
    return value


def obj(value, label):
    if not isinstance(value, dict):
        raise InputError('%s: require object' % label)
    return value


def array(value, label):
    if not isinstance(value, list):
        raise InputError('%s: require array' % label)
    return value


def require_keys(value, required, label, optional=()):
    obj(value, label)
    missing = [key for key in required if key not in value]
    if missing:
        raise InputError('%s: missing %s' % (label, ', '.join(missing)))
    unknown = sorted(set(value) - set(required) - set(optional))
    if unknown:
        raise InputError('%s: unknown fields %s' % (label, ', '.join(unknown)))
    return value


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError('%s: require finite number' % label)
    if value != value or value in (float('inf'), float('-inf')):
        raise InputError('%s: require finite number' % label)
    return value


def ref_list(value, label, known):
    array(value, label)
    result = []
    for index, item in enumerate(value):
        ref = text(item, '%s[%d]' % (label, index))
        if ref not in known:
            raise InputError('%s[%d]: unknown master BOM ref %s'
                             % (label, index, ref))
        if ref in result:
            raise InputError('%s[%d]: duplicate ref %s' % (label, index, ref))
        result.append(ref)
    return result


def add(findings, code, severity, message, where):
    if severity not in SEVERITIES:
        raise AssertionError(severity)
    findings.append({'code': code, 'severity': severity,
                     'message': message, 'where': where})


def parse_master(items):
    if not items:
        raise InputError('master_bom: require at least one item')
    master = {}
    order = []
    for index, item in enumerate(items):
        label = 'master_bom[%d]' % index
        require_keys(item, MASTER_FIELDS, label, MASTER_OPTIONAL)
        ref = text(item['ref'], label + '.ref')
        if ref in master:
            raise InputError('%s.ref: duplicate ref %s' % (label, ref))
        integer(item['per_board'], label + '.per_board')
        if 'mpn' in item:
            text(item['mpn'], label + '.mpn')
        if 'exclusive_group' in item:
            text(item['exclusive_group'], label + '.exclusive_group')
        if 'note' in item:
            text(item['note'], label + '.note')
        if 'requires' in item:
            array(item['requires'], label + '.requires')
        if 'package_step' in item:
            step = item['package_step']
            if step != UNKNOWN:
                integer(step, label + '.package_step', 1)
        master[ref] = item
        order.append(ref)
    for index, item in enumerate(items):
        label = 'master_bom[%d]' % index
        ref = item['ref']
        if 'requires' in item:
            item['requires'] = ref_list(item['requires'], label + '.requires',
                                        master)
        else:
            item['requires'] = []
        master[ref] = item
    return master, order


def closure_from(roots, master, label, findings):
    visited = []
    state = {}

    def visit(ref, path):
        mark = state.get(ref)
        if mark == 'done':
            return
        if mark == 'active':
            add(findings, 'requires_cycle', 'blocking',
                'requires 闭包存在环：%s' % ' -> '.join(path + [ref]), label)
            return
        state[ref] = 'active'
        for child in master[ref]['requires']:
            visit(child, path + [ref])
        state[ref] = 'done'
        if ref not in visited:
            visited.append(ref)

    for root in roots:
        visit(root, [])
    return visited


def needed_quantity(item, boards, rate, min_spare):
    base = item['per_board'] * boards
    if base == 0:
        return 0
    exact = Decimal(str(rate)) * Decimal(base)
    spare = max(int(exact.to_integral_value(rounding=ROUND_CEILING)),
                min_spare)
    return base + spare


def build_variant(variant, master, findings, index):
    label = 'variants[%d]' % index
    require_keys(variant, VARIANT_FIELDS, label, VARIANT_OPTIONAL)
    vid = text(variant['id'], label + '.id')
    boards = variant['boards']
    if boards != UNKNOWN:
        integer(boards, label + '.boards')
    rate = variant['attrition_rate']
    if rate != UNKNOWN:
        finite_number(rate, label + '.attrition_rate')
        if rate < 0 or rate > 1:
            raise InputError(label + '.attrition_rate: require 0..1')
    min_spare = variant['min_spare']
    if min_spare != UNKNOWN:
        integer(min_spare, label + '.min_spare')
    known = set(master)
    requires = ref_list(variant['requires'], label + '.requires', known)
    forbidden = ref_list(variant['forbidden'], label + '.forbidden', known)
    dnp = ref_list(variant['dnp'], label + '.dnp', known)
    text(variant['firmware_config'], label + '.firmware_config')
    text(variant['test_delta'], label + '.test_delta')
    if 'note' in variant:
        text(variant['note'], label + '.note')
    conflicts = array(variant['conflicts'], label + '.conflicts')
    pairs = []
    for pair_index, pair in enumerate(conflicts):
        pair_label = '%s.conflicts[%d]' % (label, pair_index)
        array(pair, pair_label)
        if len(pair) != 2:
            raise InputError(pair_label + ': require exactly two refs')
        left = text(pair[0], pair_label + '[0]')
        right = text(pair[1], pair_label + '[1]')
        if left == right:
            raise InputError(pair_label + ': refs must differ')
        for ref in (left, right):
            if ref not in known:
                raise InputError(pair_label + ': unknown master BOM ref %s' % ref)
        pairs.append((left, right))
    closure = closure_from(requires, master, label + '.requires', findings)
    closure_set = set(closure)
    conflict = sorted(closure_set & set(forbidden))
    if conflict:
        add(findings, 'required_forbidden', 'blocking',
            '变体 %s 同时 requires 与 forbidden：%s'
            % (vid, ', '.join(conflict)), label)
    for left, right in pairs:
        if left in closure_set and right in closure_set:
            add(findings, 'variant_conflict', 'blocking',
                '变体 %s 的闭包同时包含互斥件 %s 与 %s' % (vid, left, right),
                label + '.conflicts')
    groups = {}
    for ref in closure:
        group = master[ref].get('exclusive_group')
        if group:
            groups.setdefault(group, []).append(ref)
    for group, refs in sorted(groups.items()):
        if len(refs) > 1:
            add(findings, 'mixup_exclusive_group', 'blocking',
                '变体 %s 的互斥组 %s 同时装了 %s，存在混料风险'
                % (vid, group, ', '.join(refs)), label)
    dnp_conflict = sorted(closure_set & set(dnp))
    if dnp_conflict:
        add(findings, 'dnp_required_conflict', 'blocking',
            '变体 %s 的 DNP 列表包含必装件：%s'
            % (vid, ', '.join(dnp_conflict)), label + '.dnp')
    excluded = [ref for ref in master_order(master) if ref not in closure_set]
    unknown_input = [name for name, value in
                     (('boards', boards), ('attrition_rate', rate),
                      ('min_spare', min_spare)) if value == UNKNOWN]
    if unknown_input:
        add(findings, 'unknown_quantity_input', 'blocking',
            '变体 %s 的数量输入待查：%s，无法生成 needed'
            % (vid, ', '.join(unknown_input)), label)
        items = [{'ref': ref, 'needed_status': UNKNOWN} for ref in closure]
        return {'variant': vid, 'needed_status': UNKNOWN, 'needed': items,
                'excluded': excluded, 'dnp': dnp,
                'order_qty_status': UNKNOWN}
    items = []
    any_unknown = False
    for ref in closure:
        needed = needed_quantity(master[ref], boards, rate, min_spare)
        entry = {'ref': ref, 'needed': needed}
        step = master[ref].get('package_step', UNKNOWN)
        if step == UNKNOWN:
            entry['order_qty_status'] = UNKNOWN
            any_unknown = True
        else:
            entry['order_qty'] = ((needed + step - 1) // step) * step
            entry['order_qty_status'] = 'computed'
        items.append(entry)
    return {'variant': vid, 'needed_status': 'computed', 'needed': items,
            'excluded': excluded, 'dnp': dnp,
            'order_qty_status': UNKNOWN if any_unknown else 'computed'}


def master_order(master):
    # Python dicts keep the insertion order from parse_master.
    return list(master)


def check_package(data):
    require_keys(data, ('schema', 'product', 'master_bom', 'variants'),
                 'package', optional=('_note',))
    if data['schema'] != SCHEMA:
        raise InputError('schema: require %s' % SCHEMA)
    text(data['product'], 'product')
    master, _ = parse_master(array(data['master_bom'], 'master_bom'))
    variants = array(data['variants'], 'variants')
    if not variants:
        raise InputError('variants: require at least one variant')
    findings = []
    seen = set()
    generated = []
    for index, variant in enumerate(variants):
        vid = text(variant['id'], 'variants[%d].id' % index) if isinstance(
            variant, dict) and 'id' in variant else None
        if vid is not None:
            if vid in seen:
                raise InputError('variants[%d].id: duplicate variant %s'
                                 % (index, vid))
            seen.add(vid)
        generated.append(build_variant(variant, master, findings, index))
    return findings, generated


def invalid_result(message):
    return {
        'status': 'invalid_input',
        'error': message,
        'board_verified': BOARD_VERIFIED,
        'execution': EXECUTION,
        'hardware_execution': HARDWARE_EXECUTION,
        'findings': [],
        'not_checked': list(NOT_CHECKED),
    }


def final_result(product, variants, findings):
    return {
        'kind': 'variant_bom',
        'product': product,
        'status': 'needs_review' if findings else 'pass',
        'board_verified': BOARD_VERIFIED,
        'execution': EXECUTION,
        'hardware_execution': HARDWARE_EXECUTION,
        'variants': variants,
        'findings': findings,
        'not_checked': list(NOT_CHECKED),
    }


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps(invalid_result(message), ensure_ascii=False))
        raise SystemExit(2)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: %s' % key)
        result[key] = value
    return result


def load_package(path):
    raw = Path(path).read_text(encoding='utf-8')
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError('non-finite JSON: %s' % value)))


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument('package', help='path to a variant-bom/v1 JSON file')
    args = parser.parse_args(argv)
    try:
        data = load_package(args.package)
        findings, variants = check_package(data)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps(invalid_result(str(exc)), ensure_ascii=False))
        return 2
    print(json.dumps(final_result(data['product'], variants, findings),
                     ensure_ascii=False))
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
