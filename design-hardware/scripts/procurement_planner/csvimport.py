"""Explicit-column-mapping BOM CSV import.

There is no column-name guessing, no locale guessing and no formula
evaluation.  The mapping file names every source header; a decode failure is
reported as an input error instead of being silently repaired.  UTF-16 (with
BOM) EasyEDA exports and UTF-8 are supported explicitly.
"""

from __future__ import annotations

import csv
import io

from .errors import Findings, InputError
from .util import (MAX_CSV_BYTES, parse_int, parse_text, read_limited_bytes,
                   sha256_hex)

MAX_CSV_ROWS = 5000

CANONICAL_COLUMNS = (
    "line_id",
    "designators",
    "quantity_per_board",
    "mpn",
    "manufacturer",
    "footprint",
    "package",
    "description",
    "value",
    "supply_part",
    "assembly",
    "dnp",
    "consigned_qty",
)

ASSEMBLY_VALUES = ("smt", "tht", "hand", "dnp")
DEFAULT_DNP_VALUES = ("DNP", "DNF", "NOFIT", "DO_NOT_POPULATE", "不贴")


def _delimiter(value, where):
    text = parse_text(value, where)
    named = {"tab": "\t", "comma": ",", "semicolon": ";", "pipe": "|"}
    if text in named:
        return named[text]
    if len(text) == 1 and text not in ("\n", "\r"):
        return text
    raise InputError("invalid_delimiter",
                     "delimiter 必须是 tab/comma/semicolon/pipe 或单字符", where)


def _encoding(value, where):
    text = parse_text(value, where).lower()
    allowed = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be",
               "auto")
    if text not in allowed:
        raise InputError(
            "unsupported_encoding",
            "encoding 必须是 %s 之一；不做编码猜测" % "/".join(allowed), where)
    return text


def _decode(raw, encoding, path):
    if encoding == "auto":
        if raw.startswith(b"\xff\xfe"):
            encoding = "utf-16"
        elif raw.startswith(b"\xfe\xff"):
            encoding = "utf-16"
        elif raw.startswith(b"\xef\xbb\xbf"):
            encoding = "utf-8-sig"
        else:
            encoding = "utf-8"
    try:
        return raw.decode(encoding), encoding
    except UnicodeDecodeError as exc:
        raise InputError(
            "csv_encoding_error",
            "按声明的 %s 解码失败（%s）；请在 mapping 中显式声明正确编码，"
            "工具不猜乱码" % (encoding, exc), path)


def _parse_designators(text, separator, where):
    if text is None:
        return []
    if not isinstance(text, str):
        raise InputError("invalid_designators", "位号列必须是字符串", where)
    items = []
    for part in text.split(separator):
        item = part.strip()
        if item:
            items.append(item.upper())
    return items


def _parse_supply(text, where):
    value = parse_text(text, where, required=False)
    if value is None:
        return {}
    upper = value.upper()
    if upper.startswith("C") and upper[1:].isdigit():
        return {"lcsc": upper}
    return {"other": value}


def load_bom_csv(path, mapping_path):
    """Return (rows, findings, metadata) from a mapped BOM CSV."""

    findings = Findings()
    mapping_raw = read_limited_bytes(mapping_path, MAX_CSV_BYTES, "csv_map")
    try:
        import json
        mapping = json.loads(mapping_raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InputError("invalid_csv_map", "列映射 JSON 无效：%s" % exc,
                         str(mapping_path))
    if not isinstance(mapping, dict):
        raise InputError("invalid_csv_map", "列映射顶层必须是对象",
                         str(mapping_path))
    if mapping.get("schema") != "procurement-csv-map/v1":
        raise InputError("invalid_csv_map_schema",
                         "列映射 schema 必须是 procurement-csv-map/v1",
                         str(mapping_path))
    encoding = _encoding(mapping.get("encoding", "utf-8-sig"),
                        "csv_map.encoding")
    delimiter = _delimiter(mapping.get("delimiter", "comma"),
                           "csv_map.delimiter")
    separator = parse_text(mapping.get("designator_separator", ","),
                           "csv_map.designator_separator")
    if len(separator) > 1:
        raise InputError("invalid_designator_separator",
                         "位号分隔符必须是单字符",
                         "csv_map.designator_separator")
    columns = mapping.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise InputError("missing_csv_columns", "列映射缺少 columns 对象",
                         "csv_map.columns")
    unknown = sorted(set(columns) - set(CANONICAL_COLUMNS))
    if unknown:
        raise InputError(
            "unknown_csv_column",
            "未知的规范列：%s；可用 %s" % (", ".join(unknown),
                                          ", ".join(CANONICAL_COLUMNS)),
            "csv_map.columns")
    for required in ("designators", "quantity_per_board", "mpn"):
        if required not in columns:
            raise InputError("missing_csv_column",
                             "列映射缺少必需列 %r" % required,
                             "csv_map.columns")
    for key, header in columns.items():
        if not isinstance(header, str) or not header.strip():
            raise InputError("invalid_csv_header", "列名必须是非空字符串",
                             "csv_map.columns.%s" % key)

    defaults = mapping.get("defaults", {})
    if not isinstance(defaults, dict):
        raise InputError("invalid_csv_defaults", "defaults 必须是对象",
                         "csv_map.defaults")
    default_assembly = defaults.get("assembly")
    if "assembly" not in columns and default_assembly is None:
        raise InputError(
            "missing_assembly_policy",
            "CSV 没有 assembly 列时必须在 defaults 中显式给出装配方式，"
            "不按猜测补 smt", "csv_map.defaults.assembly")
    if default_assembly is not None and default_assembly not in ASSEMBLY_VALUES:
        raise InputError("invalid_assembly",
                         "assembly 必须是 smt|tht|hand|dnp",
                         "csv_map.defaults.assembly")
    default_dnp = defaults.get("dnp", False)
    if not isinstance(default_dnp, bool):
        raise InputError("invalid_dnp_default", "defaults.dnp 必须是布尔值",
                         "csv_map.defaults.dnp")
    dnp_values = mapping.get("dnp_values", list(DEFAULT_DNP_VALUES))
    if (not isinstance(dnp_values, list)
            or any(not isinstance(item, str) for item in dnp_values)):
        raise InputError("invalid_dnp_values", "dnp_values 必须是字符串数组",
                         "csv_map.dnp_values")
    dnp_set = {item.strip().upper() for item in dnp_values}

    raw = read_limited_bytes(path, MAX_CSV_BYTES, "bom_csv")
    text, used_encoding = _decode(raw, encoding, str(path))
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise InputError("empty_csv", "CSV 为空", str(path))
    header = [cell.strip().lstrip("\ufeff") for cell in header]
    duplicates = sorted({name for name in header if header.count(name) > 1
                         and name})
    if duplicates:
        raise InputError("duplicate_csv_header",
                         "CSV 表头重复：%s" % ", ".join(duplicates), str(path))
    header_index = {name: index for index, name in enumerate(header)}
    resolved = {}
    for key, source_header in columns.items():
        if source_header not in header_index:
            raise InputError(
                "mapped_header_missing",
                "mapping 声明的列 %r 不在 CSV 表头中；表头为 %s"
                % (source_header, ", ".join(header)), str(path))
        resolved[key] = header_index[source_header]

    def cell(row, key):
        index = resolved.get(key)
        if index is None or index >= len(row):
            return None
        return row[index]

    rows = []
    seen_line_ids = set()
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > MAX_CSV_ROWS:
            raise InputError("csv_too_many_rows",
                             "CSV 行数超过限制 %d" % MAX_CSV_ROWS, str(path))
        if not raw_row or not any(str(item).strip() for item in raw_row):
            continue
        where = "%s:%d" % (path, index)
        line_id = parse_text(cell(raw_row, "line_id"), where + ".line_id",
                             required=False, max_len=60)
        if line_id is None:
            line_id = "CSV-%d" % (index - 1)
        if line_id in seen_line_ids:
            findings.blocking("duplicate_line_id", where + ".line_id",
                              "行号/ID 重复：%s" % line_id)
        seen_line_ids.add(line_id)
        qty_text = parse_text(cell(raw_row, "quantity_per_board"),
                              where + ".quantity_per_board")
        try:
            qty = int(qty_text, 10)
        except (TypeError, ValueError):
            findings.blocking("invalid_csv_quantity",
                              where + ".quantity_per_board",
                              "每板数量必须是十进制整数，实际 %r" % qty_text)
            continue
        if qty < 0:
            findings.blocking("negative_quantity",
                              where + ".quantity_per_board",
                              "每板数量不能为负")
        designators = _parse_designators(cell(raw_row, "designators"),
                                         separator, where + ".designators")
        if not designators:
            findings.warning("csv_missing_designators", where + ".designators",
                             "该行没有位号；仅按数量规划，位号追溯缺失")
        elif len(designators) != qty:
            findings.blocking(
                "quantity_designator_mismatch", where + ".designators",
                "位号数 %d 与每板数量 %d 不一致；请核对 BOM 而不是猜测"
                % (len(designators), qty))
        mpn = parse_text(cell(raw_row, "mpn"), where + ".mpn", max_len=200)
        manufacturer = parse_text(cell(raw_row, "manufacturer"),
                                  where + ".manufacturer", required=False,
                                  max_len=200)
        footprint = parse_text(cell(raw_row, "footprint"),
                               where + ".footprint", max_len=200)
        package = parse_text(cell(raw_row, "package"), where + ".package",
                             required=False, max_len=120)
        description = parse_text(cell(raw_row, "description"),
                                 where + ".description", required=False,
                                 max_len=300)
        value = parse_text(cell(raw_row, "value"), where + ".value",
                           required=False, max_len=120)
        supply = _parse_supply(cell(raw_row, "supply_part"),
                               where + ".supply_part")
        assembly = cell(raw_row, "assembly")
        if assembly is not None and str(assembly).strip():
            assembly = str(assembly).strip().lower()
            if assembly not in ASSEMBLY_VALUES:
                findings.blocking("invalid_assembly", where + ".assembly",
                                  "assembly 必须是 smt|tht|hand|dnp")
        else:
            assembly = default_assembly
        dnp_value = cell(raw_row, "dnp")
        dnp = default_dnp
        if dnp_value is not None and str(dnp_value).strip():
            dnp = str(dnp_value).strip().upper() in dnp_set
        if dnp:
            assembly = "dnp"
        consigned_text = parse_text(cell(raw_row, "consigned_qty"),
                                    where + ".consigned_qty",
                                    required=False)
        consigned = 0
        if consigned_text is not None:
            try:
                consigned = int(consigned_text, 10)
            except ValueError:
                findings.blocking("invalid_consigned_qty",
                                  where + ".consigned_qty",
                                  "自备数量必须是整数，实际 %r" % consigned_text)
                consigned = 0
            if consigned < 0:
                findings.blocking("negative_consigned_qty",
                                  where + ".consigned_qty",
                                  "自备数量不能为负")
        rows.append({
            "line_id": line_id,
            "designators": designators,
            "qty_per_board": qty,
            "mpn": mpn,
            "manufacturer": manufacturer,
            "supply_ids": supply,
            "footprint": footprint,
            "package": package,
            "description": description or value,
            "assembly": assembly,
            "dnp": bool(dnp),
            "consigned_qty": consigned,
            "params": {},
            "unknown_fields": [],
            "identity_source": {
                "kind": "csv_import",
                "source": "%s + %s" % (path, mapping_path),
                "columns": dict(columns),
            },
        })
    if not rows:
        raise InputError("csv_no_rows", "CSV 没有数据行", str(path))
    metadata = {
        "path": str(path),
        "sha256": sha256_hex(raw),
        "mapping_path": str(mapping_path),
        "mapping_sha256": sha256_hex(mapping_raw),
        "encoding": used_encoding,
        "delimiter": {"\t": "tab", ",": "comma", ";": "semicolon"}.get(
            delimiter, "custom"),
        "row_count": len(rows),
    }
    return rows, findings, metadata
