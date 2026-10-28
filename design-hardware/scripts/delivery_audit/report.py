"""Deterministic JSON/Markdown rendering and atomic output paths."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .model import SEVERITIES


def dump_json(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _replace_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=str(path.parent),
        prefix="." + path.name + ".", suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    try:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(str(temporary), str(path))
    except BaseException:
        handle.close()
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    return path


def _temp_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=str(path.parent),
        prefix="." + path.name + ".", suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    try:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
    except BaseException:
        handle.close()
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    return temporary


def write_json_atomic(path, payload):
    return _replace_atomic(path, dump_json(payload))


def write_text_atomic(path, text):
    return _replace_atomic(path, text)


def write_reports_atomic(json_path, payload, markdown_path, markdown_text):
    """Write JSON+Markdown as atomically as a filesystem allows.

    Both renderings are materialised as temporary files first and target types
    are preflighted, so a directory in place of one report cannot leave the
    other report updated with a contradictory status.  The machine-readable JSON
    is replaced last.
    """
    json_target = Path(json_path) if json_path is not None else None
    markdown_target = Path(markdown_path) if markdown_path is not None else None
    for item in (json_target, markdown_target):
        if item is not None and item.exists() and item.is_dir():
            raise OSError("output target is a directory: %s" % item)
    json_temp = (_temp_text(json_target, dump_json(payload))
                 if json_target is not None else None)
    try:
        markdown_temp = (_temp_text(markdown_target, markdown_text)
                         if markdown_target is not None else None)
    except BaseException:
        if json_temp is not None:
            try:
                json_temp.unlink()
            except OSError:
                pass
        raise
    written = []
    try:
        if markdown_temp is not None:
            os.replace(str(markdown_temp), str(markdown_target))
            written.append(str(markdown_target))
        if json_temp is not None:
            os.replace(str(json_temp), str(json_target))
            written.append(str(json_target))
    except BaseException:
        for temporary in (json_temp, markdown_temp):
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass
        raise
    return written


def _resolved(path):
    return Path(path).expanduser().resolve(strict=False)


def _within(child, parent):
    try:
        return os.path.commonpath([str(child), str(parent)]) == str(parent)
    except ValueError:  # different drives on Windows
        return False


def resolve_outputs(out, input_path, *, audit, protected=()):
    """Resolve ``--out`` into JSON/Markdown paths and enforce containment.

    Returns ``{"json": Path|None, "markdown": Path|None, "directory": bool}``.
    Raises ``ValueError`` with an actionable message when an output would land
    inside the input or overwrite a protected declaration/reference file.
    """
    if out is None:
        return {"json": None, "markdown": None, "directory": False}
    target = Path(out)
    suffix = target.suffix.lower()
    directory = False
    if not suffix:
        directory = True
        json_path = target / "delivery-audit.json" if audit else target / "inspect.json"
        markdown_path = target / "delivery-audit.md" if audit else None
    elif suffix == ".json":
        json_path = target
        markdown_path = None
    elif suffix == ".md":
        if not audit:
            raise ValueError("--out for inspect/manifest must be a .json file or directory")
        json_path = None
        markdown_path = target
    else:
        raise ValueError("--out must be a directory or end with .json/.md")

    input_abs = _resolved(input_path)
    outputs = [item for item in (json_path, markdown_path) if item is not None]
    protected_abs = [_resolved(item) for item in protected if item]
    for item in outputs:
        item_abs = _resolved(item)
        if item_abs == input_abs:
            raise ValueError("output path equals the input path: %s" % item)
        if input_abs.is_dir() and _within(item_abs, input_abs):
            raise ValueError(
                "output must be outside the input package: %s is inside %s; "
                "a report inside the input would change the next scan's hashes"
                % (item, input_abs))
        for guarded in protected_abs:
            if item_abs == guarded:
                raise ValueError("refusing to overwrite declarations/reference "
                                 "file with a report: %s" % item)
    return {"json": json_path, "markdown": markdown_path, "directory": directory}


def _finding_line(item):
    parts = []
    location = item.get("file")
    if location:
        if item.get("line"):
            location += ":%s" % item["line"]
        parts.append("`%s`" % location)
    if item.get("object"):
        parts.append("对象=`%s`" % item["object"])
    parts.append("`%s`" % item["rule_id"])
    parts.append("[%s/%s]" % (item.get("status"), item.get("severity")))
    detail = item.get("message", "")
    if "actual" in item or "expected" in item:
        actual = item.get("actual")
        expected = item.get("expected")
        unit = item.get("unit") or ""
        if actual is not None:
            detail += " 实际=%s%s" % (json.dumps(actual, ensure_ascii=False), unit)
        if expected is not None:
            detail += " 期望=%s%s" % (json.dumps(expected, ensure_ascii=False), unit)
    if item.get("suggestion"):
        detail += " 建议：%s（未执行）" % item["suggestion"]
    return "- " + "；".join(parts) + "：" + detail


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("|", "\\|")
                                       for cell in row) + " |")
    return "\n".join(lines)


def render_markdown(report):
    status = report.get("status")
    lines = ["# 交付审计报告", ""]
    lines.append("- 整体状态：**%s**" % status)
    lines.append("- profile：`%s`" % report.get("profile"))
    lines.append("- 生成时间：`%s`" % report.get("generated_at"))
    tool = report.get("tool") or {}
    lines.append("- 工具：`%s %s`" % (tool.get("name"), tool.get("version")))
    input_info = report.get("input") or {}
    lines.append("- 输入：`%s`（kind=%s，文件数=%s）"
                 % (input_info.get("path"), input_info.get("kind"),
                    input_info.get("file_count")))
    lines.append("- 内容摘要（sha256）：`%s`" % input_info.get("content_digest"))
    declarations = report.get("declarations") or {}
    if declarations:
        lines.append("- 工程：`%s` revision `%s`；声明 sha256：`%s`"
                     % (declarations.get("project_id"), declarations.get("revision"),
                        declarations.get("declaration_sha256")))
    lines.append("")
    if status == "input_invalid":
        error = report.get("error") or {}
        lines.append("> 输入无效（%s）：本报告不是审计结论，也不包含任何通过判定。"
                     "请先按错误信息修复输入/参数后重跑。" % error.get("code"))
    else:
        lines.append("> 本报告只覆盖“格式结构、文件完整性、声明一致性”这一范围。"
                     "`pass_with_scope` 不代表板厂接单、DFM/阻抗/电气通过、可贴装、"
                     "实物或备份恢复通过。未知项不按通过处理。")
    lines.append("")

    findings = report.get("findings") or []
    fail = [item for item in findings if item.get("status") == "fail"]
    unknown = [item for item in findings if item.get("status") == "unknown"]
    lines.append("## 1. 阻断与缺件")
    lines.append("")
    if fail:
        fail.sort(key=lambda item: (SEVERITIES.index(item.get("severity", "info")),
                                    item.get("rule_id", "")))
        lines.extend(_finding_line(item) for item in fail)
    else:
        lines.append("未发现硬性阻断；请继续阅读未知项与限制。")
    lines.append("")
    lines.append("## 2. 未知 / 不完整")
    lines.append("")
    if unknown:
        lines.extend(_finding_line(item) for item in unknown)
    else:
        lines.append("无。")
    lines.append("")

    lines.append("## 3. 检查覆盖")
    lines.append("")
    rows = [(("`%s`" % item.get("id")), item.get("status"),
             item.get("scope") or "") for item in report.get("checks") or []]
    lines.append(_table(["检查", "状态", "范围"], rows))
    lines.append("")

    coverage = report.get("coverage") or {}
    missing_required = coverage.get("missing_required") or []
    lines.append("## 4. 交付角色覆盖")
    lines.append("")
    if missing_required:
        lines.append("缺失的必需角色：%s" % ", ".join(missing_required))
        lines.append("")
    role_rows = []
    for row in coverage.get("roles") or []:
        if row.get("status") == "present" or row.get("required"):
            role_rows.append((row.get("role"), row.get("layer_index") or "",
                              row.get("required"), row.get("status"),
                              ", ".join(row.get("files") or []) or "-"))
    lines.append(_table(["角色", "层号", "必需", "状态", "文件"], role_rows))
    lines.append("")

    lines.append("## 5. 文件与角色")
    lines.append("")
    file_rows = []
    for item in report.get("files") or []:
        file_rows.append(("`%s`" % item.get("path"), item.get("size"),
                          item.get("detected_kind") or "",
                          item.get("role") or "", item.get("role_source") or "",
                          "`%s`" % item.get("sha256")))
    lines.append(_table(["路径", "字节", "内容类型", "角色", "角色来源", "sha256"],
                        file_rows))
    lines.append("")

    provenance = report.get("provenance") or {}
    lines.append("## 6. 来源 / 版本自洽")
    lines.append("")
    lines.append("- 声明文件：%s" % ("有" if report.get("declarations") else "无"))
    lines.append("- 内容绑定：`%s`" % provenance.get("content_binding"))
    lines.append("- 来源绑定：`%s`" % provenance.get("source_binding"))
    lines.append("- 同一内容快照：`%s`" % provenance.get("same_snapshot_binding"))
    lines.append("- 同一 EDA revision：`%s`（本工具不能证明）"
                 % provenance.get("same_eda_revision"))
    lines.append("- 文件时间戳是否作为证据：%s"
                 % provenance.get("mtime_used_as_evidence"))
    lines.append("")

    lines.append("## 7. 未执行 / 限制")
    lines.append("")
    for item in report.get("restrictions") or []:
        lines.append("- " + item)
    lines.append("")
    lines.append("## 8. 复核命令")
    lines.append("")
    lines.append("```")
    lines.append("cd design-hardware/scripts")
    lines.append("python -m delivery_audit audit --input <package> --profile %s "
                 "--declarations <declarations.json> --out <report-dir>"
                 % report.get("profile"))
    lines.append("```")
    lines.append("")
    summary = report.get("summary") or {}
    lines.append("## 9. 计数（不是评分）")
    lines.append("")
    lines.append("findings=%s；by_status=%s；by_severity=%s"
                 % (summary.get("findings"), json.dumps(
                     summary.get("by_status"), ensure_ascii=False, sort_keys=True),
                    json.dumps(summary.get("by_severity"), ensure_ascii=False,
                               sort_keys=True)))
    lines.append("")
    return "\n".join(lines)
