"""Strict loading, hashing, time and atomic-write helpers.

The planner must be replayable from a declared evaluation moment, so every
timestamp is parsed explicitly and compared in UTC.  Input files are read
read-only with a hard size limit; nothing here executes user content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import InputError

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_CSV_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})"
    r"[Tt ](?P<time>\d{2}:\d{2}:\d{2})(?P<fraction>\.\d{1,9})?"
    r"(?P<offset>[Zz]|[+-]\d{2}:\d{2})$"
)


def read_limited_bytes(path, limit, field):
    """Read at most ``limit`` bytes from a regular file, no symlink following."""

    candidate = Path(path)
    try:
        if candidate.is_symlink():
            raise InputError("symlink_input_rejected",
                             "输入路径是符号链接，拒绝读取", str(path))
        if not candidate.is_file():
            raise InputError("input_not_file", "输入路径不是普通文件", str(path))
        size = candidate.stat().st_size
        if size > limit:
            raise InputError(
                "input_too_large",
                "输入文件 %.1f MiB 超过限制 %.1f MiB"
                % (size / 1048576.0, limit / 1048576.0),
                str(path))
        return candidate.read_bytes()
    except InputError:
        raise
    except OSError as exc:
        raise InputError("input_unreadable", "无法读取输入文件：%s" % exc,
                         str(path))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("重复 JSON key: %s" % key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("JSON 不允许 NaN/Infinity: %s" % value)


def load_json(path, limit=MAX_JSON_BYTES):
    raw = read_limited_bytes(path, limit, "json")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("input_encoding", "JSON 必须是 UTF-8：%s" % exc,
                         str(path))
    try:
        data = json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (ValueError, json.JSONDecodeError) as exc:
        raise InputError("invalid_json", "JSON 解析失败：%s" % exc, str(path))
    if not isinstance(data, dict):
        raise InputError("invalid_json_root", "JSON 顶层必须是对象", str(path))
    return data


def canonical_bytes(value):
    """Stable canonical JSON bytes used for every reported input hash."""

    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value):
    return sha256_hex(canonical_bytes(value))


def is_sha256(value):
    return isinstance(value, str) and SHA256_RE.match(value.strip()) is not None


def parse_int(value, where, minimum=None, maximum=None, required=True,
              allow_none=False):
    if value is None and allow_none:
        return None
    if not required and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError("invalid_integer",
                         "必须是整数，不接受布尔/小数/字符串", where)
    if minimum is not None and value < minimum:
        raise InputError("integer_out_of_range",
                         "必须 >= %d，实际 %d" % (minimum, value), where)
    if maximum is not None and value > maximum:
        raise InputError("integer_out_of_range",
                         "必须 <= %d，实际 %d" % (maximum, value), where)
    return value


def parse_bool(value, where, required=True, default=None):
    if value is None:
        if required:
            raise InputError("missing_boolean", "缺少布尔字段", where)
        return default
    if not isinstance(value, bool):
        raise InputError("invalid_boolean", "必须是 JSON true/false", where)
    return value


def parse_text(value, where, required=True, allow_empty=False, max_len=500):
    if value is None:
        if required:
            raise InputError("missing_text", "缺少文本字段", where)
        return None
    if not isinstance(value, str):
        raise InputError("invalid_text", "必须是字符串", where)
    text = value.strip()
    if not text and not allow_empty:
        if required:
            raise InputError("empty_text", "不能为空字符串", where)
        return None
    if len(text) > max_len:
        raise InputError("text_too_long",
                         "文本长度 %d 超过 %d" % (len(text), max_len), where)
    return text


def parse_enum(value, allowed, where, required=True):
    text = parse_text(value, where, required=required)
    if text is None:
        return None
    if text not in allowed:
        raise InputError(
            "invalid_enum",
            "必须是 %s 之一，实际 %r" % ("|".join(allowed), text), where)
    return text


def parse_decimal(value, where, minimum=None, maximum=None, required=True):
    """Parse a decimal quantity.

    Money and ratios must be strings or integers in JSON; binary floats are
    rejected so a value such as 0.1 never enters settlement as a float.
    """

    if value is None:
        if required:
            raise InputError("missing_decimal", "缺少十进制数值", where)
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InputError(
            "float_decimal_rejected",
            "价格/比率字段必须是字符串或整数；不接受二进制 float", where)
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise InputError("invalid_decimal", "必须是字符串或整数", where)
    if not text:
        raise InputError("invalid_decimal", "不能为空", where)
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise InputError("invalid_decimal", "不是合法十进制数：%r" % text,
                         where)
    if not number.is_finite():
        raise InputError("non_finite_decimal", "不允许 NaN/Infinity", where)
    if minimum is not None and number < minimum:
        raise InputError("decimal_out_of_range",
                         "必须 >= %s，实际 %s" % (minimum, number), where)
    if maximum is not None and number > maximum:
        raise InputError("decimal_out_of_range",
                         "必须 <= %s，实际 %s" % (maximum, number), where)
    return number


def parse_rfc3339(value, where, required=True, allow_date_only=False):
    if value is None:
        if required:
            raise InputError("missing_timestamp", "缺少时间戳", where)
        return None
    text = parse_text(value, where)
    match = RFC3339_RE.match(text)
    if not match:
        if allow_date_only and re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            try:
                day = date.fromisoformat(text)
            except ValueError:
                raise InputError("invalid_timestamp", "非法日期：%r" % text,
                                 where)
            # A date-only deadline means end of that UTC day on purpose.
            return datetime(day.year, day.month, day.day, 23, 59, 59,
                            tzinfo=timezone.utc)
        raise InputError(
            "invalid_timestamp",
            "必须是带时区的 RFC3339 时间（如 2026-10-27T08:00:00+08:00）", where)
    fraction = match.group("fraction") or ""
    stamp = "%sT%s%s" % (match.group("date"), match.group("time"), fraction)
    offset = match.group("offset")
    if offset in ("Z", "z"):
        suffix = "+00:00"
    else:
        suffix = offset
    try:
        parsed = datetime.fromisoformat(stamp + suffix)
    except ValueError:
        raise InputError("invalid_timestamp", "非法时间：%r" % text, where)
    if parsed.tzinfo is None:
        raise InputError("naive_timestamp", "时间必须带时区", where)
    return parsed.astimezone(timezone.utc)


def format_utc(moment):
    if moment is None:
        return None
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def format_local(moment):
    if moment is None:
        return None
    return moment.isoformat()


def utc_now():
    return datetime.now(timezone.utc)


def ago_hours(moment, reference):
    delta = reference - moment
    return delta.total_seconds() / 3600.0


def add_days(moment, days):
    return moment + timedelta(days=days)


def normalize_identity(text):
    """Normalise MPN/footprint for identity comparison, never for display."""

    if not isinstance(text, str):
        return ""
    return " ".join(text.strip().upper().split())


def normalize_supply_id(text):
    if not isinstance(text, str):
        return ""
    return "".join(text.strip().upper().split())


def safe_relative_name(value, where, max_len=120):
    """Validate a caller-supplied identifier used in report paths/messages."""

    text = parse_text(value, where, max_len=max_len)
    if any(ch in text for ch in ("/", "\\", "..")) or "\x00" in text:
        raise InputError("unsafe_identifier",
                         "标识符不能包含路径分隔符或 ..", where)
    return text


def atomic_write_text(path, text, forbidden_paths=()):
    """Write UTF-8 text atomically; refuse to overwrite any input path."""

    target = Path(path).expanduser()
    try:
        resolved = target.resolve()
    except OSError as exc:
        raise InputError("output_path_invalid", "输出路径无效：%s" % exc,
                         str(path))
    for forbidden in forbidden_paths:
        if forbidden is None:
            continue
        try:
            if resolved == Path(forbidden).expanduser().resolve():
                raise InputError(
                    "output_overwrites_input",
                    "输出路径与输入路径相同；规划器不得改写输入", str(path))
        except OSError:
            continue
    parent = resolved.parent
    if not parent.exists():
        raise InputError("output_parent_missing", "输出目录不存在", str(path))
    fd, tmp = tempfile.mkstemp(prefix=".procure-", suffix=".tmp",
                               dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, str(resolved))
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise InputError("output_write_failed", "写输出失败：%s" % exc,
                         str(path))
    return str(resolved)


def csv_safe_cell(value):
    """Spreadsheet formula-injection guard for exported CSV only.

    The internal report JSON keeps exact MPNs.  In CSV cells a leading
    ``= + - @`` (or tab/CR) is prefixed with an apostrophe so a spreadsheet
    treats the value as text and never evaluates it.
    """

    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
