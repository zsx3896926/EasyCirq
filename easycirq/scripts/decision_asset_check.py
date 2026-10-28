#!/usr/bin/env python3
"""Read-only checker for decision asset indexes.

The index is a Markdown table with the fixed 18 columns defined below. The
checker verifies structure only: column set, duplicate IDs, dangling
depends_on/contract_ref, conflict field completeness, status enums, path
existence and registered source IDs. It never proves that an asset is
correct, current or hardware-verified, and it does not read the asset bodies.

No network access and no file writes. Standard output is exactly one JSON
object. Exit codes: 0 = no findings, 1 = findings need review, 2 = invalid
input (unreadable file, no index table, no registered source IDs, bad CLI).
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

BOARD_VERIFIED = False
EXECUTION = 'OFFLINE_PLANNING'
HARDWARE_EXECUTION = 'NOT RUN'
SEVERITIES = ('blocking', 'warning', 'unknown')
KINDS = ('reference', 'case', 'template', 'script')
STATUSES = ('active', 'conditional', 'deprecated', 'retired', 'planned', 'blocked')
EVIDENCE_LEVELS = ('E1', 'E2', 'E3')
COLUMNS = (
    'id', 'kind', 'path', 'domain', 'stage', 'applies_to', 'source_ids',
    'evidence', 'status', 'last_reviewed', 'depends_on', 'use_when',
    'contract_ref', 'conflict_id', 'conflict_summary', 'affected_assets',
    'resolution', 'recheck_trigger',
)
CONFLICT_FIELDS = ('conflict_summary', 'affected_assets', 'resolution',
                   'recheck_trigger')
ID_RE = re.compile(r'^[A-Z][A-Z0-9]*-[A-Z0-9]+$')
ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
SEPARATOR_RE = re.compile(r'^:?-{3,}:?$')
PLACEHOLDER = '待查'
NOT_CHECKED = [
    '字段语义与数值正确性（脚本只查结构）',
    '来源登记正文与资产摘要是否一致',
    '资产内容是否可执行、可复现',
    '真实硬件、EDA 回读与实测',
]


class InputError(ValueError):
    """The supplied index or register cannot be parsed as input."""


def add(findings, code, severity, message, where):
    if severity not in SEVERITIES:
        raise AssertionError(severity)
    findings.append({'code': code, 'severity': severity,
                     'message': message, 'where': where})


def split_cells(line):
    text = line.strip()
    if text.startswith('|'):
        text = text[1:]
    if text.endswith('|'):
        text = text[:-1]
    return [cell.strip() for cell in text.split('|')]


def is_separator(cells):
    return bool(cells) and all(SEPARATOR_RE.match(cell) for cell in cells)


def table_blocks(lines):
    """Yield (header_cells, [(line_number, cells), ...]) for pipe tables."""
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith('|'):
            index += 1
            continue
        start = index
        rows = []
        while index < len(lines) and lines[index].lstrip().startswith('|'):
            rows.append((index + 1, split_cells(lines[index])))
            index += 1
        header = rows[0][1]
        data = [item for item in rows[1:] if not is_separator(item[1])]
        yield header, data, start + 1


def parse_index(text):
    blocks = list(table_blocks(text.splitlines()))
    candidate = None
    for header, data, line_number in blocks:
        overlap = sum(1 for name in COLUMNS if name in header)
        if overlap >= 5 or ('id' in header and 'path' in header):
            candidate = (header, data, line_number)
            break
    if candidate is None:
        raise InputError('未找到资产索引表：需要含固定 18 列的表头')
    return candidate


def parse_register(text):
    registered = set()
    for line in text.splitlines():
        if not line.lstrip().startswith('|'):
            continue
        cells = split_cells(line)
        if not cells:
            continue
        token = cells[0]
        if ID_RE.match(token):
            registered.add(token)
    if not registered:
        raise InputError('来源登记表中没有可识别的来源 ID')
    return registered


def resolve_ids(value):
    if value == '-':
        return []
    parts = [part.strip() for part in value.split(';')]
    return parts


def check_conflict(row, findings, where):
    conflict_id = row['conflict_id']
    if conflict_id != '-':
        missing = [name for name in CONFLICT_FIELDS if row[name] == '-']
        if missing:
            add(findings, 'conflict_fields_incomplete', 'blocking',
                '冲突 %s 缺少字段：%s' % (conflict_id, ', '.join(missing)),
                where)
    else:
        stray = [name for name in CONFLICT_FIELDS[:-1] if row[name] != '-']
        if stray:
            add(findings, 'conflict_without_id', 'blocking',
                '没有 conflict_id 却填写了：%s' % ', '.join(stray), where)


def check_rows(header, data, registered, root):
    findings = []
    ids = {}
    row_dicts = []
    for line_number, cells in data:
        where = 'line %d' % line_number
        if len(cells) != len(COLUMNS):
            asset = cells[0] if cells else '?'
            add(findings, 'row_column_count', 'blocking',
                '行应有 %d 列，实际 %d 列' % (len(COLUMNS), len(cells)),
                '%s (%s)' % (where, asset))
            continue
        row = dict(zip(COLUMNS, cells))
        row_dicts.append((line_number, row))
        asset_id = row['id']
        where = '%s (id=%s)' % (where, asset_id or '空')
        if not asset_id or asset_id == '-':
            add(findings, 'empty_field', 'blocking', 'id 不得为空', where)
            continue
        if asset_id in ids:
            add(findings, 'duplicate_id', 'blocking',
                '重复 ID：%s（首次见 line %d）' % (asset_id, ids[asset_id]),
                where)
            continue
        ids[asset_id] = line_number
    for line_number, row in row_dicts:
        asset_id = row['id']
        where = 'line %d (id=%s)' % (line_number, asset_id or '空')
        if not asset_id or asset_id == '-':
            continue
        if row['kind'] not in KINDS:
            add(findings, 'invalid_kind', 'blocking',
                'kind 应为 %s，实际 %s' % ('/'.join(KINDS), row['kind']), where)
        if row['status'] not in STATUSES:
            add(findings, 'invalid_status', 'blocking',
                'status 应为 %s，实际 %s' % ('/'.join(STATUSES), row['status']),
                where)
        if row['evidence'] not in EVIDENCE_LEVELS:
            add(findings, 'invalid_evidence', 'blocking',
                'evidence 应为 E1/E2/E3，实际 %s' % row['evidence'], where)
        stamp = row['last_reviewed']
        if not ISO_DATE_RE.match(stamp):
            add(findings, 'invalid_last_reviewed', 'blocking',
                'last_reviewed 应为 YYYY-MM-DD，实际 %s' % stamp, where)
        else:
            try:
                date.fromisoformat(stamp)
            except ValueError:
                add(findings, 'invalid_last_reviewed', 'blocking',
                    'last_reviewed 不是合法日期：%s' % stamp, where)
        for name in ('domain', 'stage', 'applies_to', 'use_when'):
            if not row[name] or row[name] == '-':
                add(findings, 'empty_field', 'blocking',
                    '%s 不得为空或 -' % name, where)
        path_text = row['path']
        if path_text == PLACEHOLDER:
            if row['status'] not in ('planned', 'blocked'):
                add(findings, 'path_placeholder_status', 'blocking',
                    'path 为待查时 status 只能是 planned/blocked，实际 %s'
                    % row['status'], where)
        else:
            candidate = Path(path_text)
            if candidate.is_absolute():
                add(findings, 'path_not_relative', 'blocking',
                    'path 必须是仓库相对路径：%s' % path_text, where)
            elif not (Path(root) / candidate).is_file():
                add(findings, 'missing_path', 'blocking',
                    'path 指向的文件不存在：%s' % path_text, where)
        sources = resolve_ids(row['source_ids'])
        if row['source_ids'] != '-' and not sources:
            add(findings, 'empty_field', 'blocking', 'source_ids 不得为空', where)
        for source in sources:
            if source not in registered:
                add(findings, 'unregistered_source', 'blocking',
                    'source_ids 含未登记来源：%s' % source, where)
        for dependency in resolve_ids(row['depends_on']):
            if dependency not in ids:
                add(findings, 'dangling_depends_on', 'blocking',
                    'depends_on 指向不存在的资产：%s' % dependency, where)
        contract = row['contract_ref']
        if contract != '-':
            if contract not in ids:
                add(findings, 'dangling_contract_ref', 'blocking',
                    'contract_ref 指向不存在的资产：%s' % contract, where)
            else:
                target = row_dicts[[item[1]['id'] for item in row_dicts].index(contract)][1]
                if target['kind'] != 'reference':
                    add(findings, 'contract_ref_not_reference', 'blocking',
                        'contract_ref 必须指向 reference，%s 是 %s'
                        % (contract, target['kind']), where)
        for affected in resolve_ids(row['affected_assets']):
            if affected not in ids:
                add(findings, 'dangling_affected_asset', 'blocking',
                    'affected_assets 含不存在的资产：%s' % affected, where)
        check_conflict(row, findings, where)
    return findings


def check_index(index_path, register_path, root):
    index_text = Path(index_path).read_text(encoding='utf-8-sig')
    register_text = Path(register_path).read_text(encoding='utf-8-sig')
    registered = parse_register(register_text)
    header, data, header_line = parse_index(index_text)
    findings = []
    if tuple(header) != COLUMNS:
        missing = [name for name in COLUMNS if name not in header]
        extra = [name for name in header if name not in COLUMNS]
        detail = []
        if missing:
            detail.append('缺少：' + ', '.join(missing))
        if extra:
            detail.append('多出：' + ', '.join(extra))
        if not missing and not extra:
            detail.append('列顺序与固定列不一致')
        add(findings, 'header_columns_mismatch', 'blocking',
            '表头不是固定 18 列（%s）' % '；'.join(detail),
            'header line %d' % header_line)
    else:
        findings.extend(check_rows(header, data, registered, root))
    counts = {'rows': len(data)}
    return findings, counts


def invalid_result(message):
    return {
        'kind': 'asset-index',
        'status': 'invalid_input',
        'error': message,
        'board_verified': BOARD_VERIFIED,
        'execution': EXECUTION,
        'hardware_execution': HARDWARE_EXECUTION,
        'findings': [],
        'not_checked': list(NOT_CHECKED),
    }


def final_result(findings, counts):
    return {
        'kind': 'asset-index',
        'status': 'needs_review' if findings else 'pass',
        'board_verified': BOARD_VERIFIED,
        'execution': EXECUTION,
        'hardware_execution': HARDWARE_EXECUTION,
        'counts': counts,
        'findings': findings,
        'not_checked': list(NOT_CHECKED),
    }


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps(invalid_result(message), ensure_ascii=False))
        raise SystemExit(2)


def infer_root(index_path):
    current = Path(index_path).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / 'easycirq').is_dir():
            return candidate
    return Path.cwd()


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument('index', help='path to the Markdown asset index')
    parser.add_argument('--source-register', required=True,
                        help='path to references/source-register.md')
    parser.add_argument('--root', default=None,
                        help='repository root for index paths (default: infer)')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else infer_root(args.index)
    try:
        findings, counts = check_index(args.index, args.source_register, root)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps(invalid_result(str(exc)), ensure_ascii=False))
        return 2
    result = final_result(findings, counts)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
