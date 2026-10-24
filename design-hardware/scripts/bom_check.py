#!/usr/bin/env python3
"""Read-only BOM/parts planner check (parts/v1). No network, no EDA, no writes.

Stdout is exactly one JSON object. Exit codes: 0 = no blocking finding,
1 = blocking finding, 2 = invalid input (unreadable file, bad JSON, wrong
schema). --strict promotes every warning to blocking.

The checker validates planning fields only. A pass never proves stock, price,
SMT attachability, footprint geometry, alternates' electrical equivalence or
schematic connectivity; see the not_checked list in the report.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

REPORT_SCHEMA = "bom-check/v1"
PARTS_SCHEMA = "parts/v1"
ASSEMBLY_VALUES = ("smt", "hand", "tht", "dnp")
SMT_CLASSES = ("basic", "extended", "consigned", "pending")
STOCK_STATUSES = ("in_stock", "low", "out_of_stock", "unchecked")
NON_LCSC_STATUSES = ("non_lcsc", "pending")
LCSC_RE = re.compile(r"^C\d+$")
DESIGNATOR_RE = re.compile(r"^[A-Z]{1,4}\d{1,4}$")
# Imperial 0402 / metric 1005 are the same body; imperial 0201 is not a
# hand-solderable package. Matching tolerates EDA names such as R0402.
TINY_PACKAGE_RE = re.compile(r"(?:^|[^0-9])(0201|0402|1005)(?:[^0-9]|$)")
PLACEHOLDERS = {"待核", "待查", "待定", "tbd", "todo", "unknown", "n/a", "-", "?"}
NOT_CHECKED = [
    "实际库存、价格、MOQ 与交期（脚本不联网，不读商城或订单页）",
    "嘉立创 SMT 可贴状态、换料费与服务类型（须按当日订单页核对）",
    "封装/land pattern 与原厂 drawing 的几何一致性",
    "替代料的 pin-to-pin、电气、时序与固件等价性（只检查字段完整性）",
    "DNP 与 CPL、装配图、装配变体的一致性",
    "原理图网表、引脚映射与 PCB 焊盘的一致性",
]


def add(findings, level, code, where, message):
    if level not in ("blocking", "warning"):
        raise AssertionError(level)
    findings.append({
        "level": level,
        "code": code,
        "where": where,
        "message": message,
    })


def is_text(value):
    return isinstance(value, str) and bool(value.strip())


def valid_date(value):
    if not is_text(value):
        return False
    try:
        date.fromisoformat(value.strip())
    except ValueError:
        return False
    return True


def is_placeholder(value):
    return is_text(value) and value.strip().lower() in PLACEHOLDERS


def check_stock(part, label, findings):
    stock = part.get("stock")
    if not isinstance(stock, dict):
        add(findings, "blocking", "missing_stock", label + ".stock",
            "缺少 stock 对象；库存状态必须显式记录，未核对写 unchecked")
        return
    status = stock.get("status")
    if status not in STOCK_STATUSES:
        add(findings, "blocking", "invalid_stock_status", label + ".stock.status",
            "stock.status 必须是 in_stock|low|out_of_stock|unchecked 之一")
        return
    qty = stock.get("qty")
    if qty is not None and (type(qty) is not int or qty < 0):
        add(findings, "blocking", "invalid_stock_qty", label + ".stock.qty",
            "stock.qty 必须是 >=0 的整数或 null")
    if status == "unchecked":
        add(findings, "warning", "stock_unchecked", label + ".stock",
            "库存未核对；G6 前必须补 checked_at 与 status，不能默认有货")
        return
    if not valid_date(stock.get("checked_at")):
        add(findings, "blocking", "missing_stock_check_date",
            label + ".stock.checked_at",
            "声称有库/缺货却缺少有效查询日期（YYYY-MM-DD）；旧 BOM 或搜索摘要不算核对")
    if status == "out_of_stock":
        add(findings, "blocking", "out_of_stock", label + ".stock",
            "status=out_of_stock；改用合格替代料或调整方案后重新核价核货")
    elif status == "low":
        add(findings, "warning", "stock_low", label + ".stock",
            "库存偏低；按实际用量/备损核对是否够本批")


def check_lcsc(value, label, findings, required=True):
    if value is None:
        if required:
            add(findings, "blocking", "missing_lcsc", label + ".lcsc",
                "缺少 LCSC C 号；非立创料用 {\"status\":\"non_lcsc\",\"note\":\"...\"} 显式声明")
        return
    if isinstance(value, str):
        if LCSC_RE.match(value.strip()):
            return
        add(findings, "blocking", "invalid_lcsc", label + ".lcsc",
            "LCSC 字段必须是 C 加数字（如 C80839）；非立创料用显式状态对象")
        return
    if isinstance(value, dict):
        status = value.get("status")
        if status not in NON_LCSC_STATUSES:
            add(findings, "blocking", "invalid_lcsc_status", label + ".lcsc.status",
                "lcsc.status 必须是 non_lcsc 或 pending")
        elif status == "pending":
            add(findings, "warning", "lcsc_pending", label + ".lcsc",
                "C 号待核；采购前必须补实际商品编号或非立创渠道")
        note = value.get("note")
        if note is not None and not is_text(note):
            add(findings, "warning", "invalid_lcsc_note", label + ".lcsc.note",
                "note 必须是非空字符串")
        return
    add(findings, "blocking", "invalid_lcsc", label + ".lcsc",
        "LCSC 字段必须是字符串或状态对象")


def check_alternates(value, label, findings, primary_mpn):
    if value is None:
        return
    if not isinstance(value, list):
        add(findings, "blocking", "invalid_alternates", label + ".alternates",
            "alternates 必须是数组")
        return
    for index, alt in enumerate(value):
        alabel = "%s.alternates[%d]" % (label, index)
        if not isinstance(alt, dict):
            add(findings, "blocking", "invalid_alternate", alabel,
                "替代料必须是对象")
            continue
        mpn = alt.get("mpn")
        if not is_text(mpn):
            add(findings, "blocking", "alternate_missing_mpn", alabel + ".mpn",
                "替代料缺少 MPN")
        elif is_text(primary_mpn) and mpn.strip().upper() == primary_mpn.strip().upper():
            add(findings, "warning", "alternate_same_as_primary", alabel + ".mpn",
                "替代料与主料 MPN 相同，不构成替代")
        check_lcsc(alt.get("lcsc"), alabel, findings, required=False)
        for key in ("difference", "note"):
            if key in alt and not is_text(alt[key]):
                add(findings, "warning", "invalid_alternate_text",
                    alabel + "." + key, "字段必须是非空字符串")


def check_designators(part, label, findings, seen):
    designators = part.get("designators")
    accepted = []
    if not isinstance(designators, list) or not designators:
        add(findings, "blocking", "missing_designators", label + ".designators",
            "designators 必须是非空数组")
        return accepted
    for index, raw in enumerate(designators):
        dlabel = "%s.designators[%d]" % (label, index)
        if not is_text(raw):
            add(findings, "blocking", "invalid_designator", dlabel,
                "位号必须是非空字符串")
            continue
        designator = raw.strip().upper()
        if not DESIGNATOR_RE.match(designator):
            add(findings, "blocking", "invalid_designator", dlabel,
                "位号格式应为字母+数字（如 R1、U12、LED1）")
            continue
        if designator in accepted:
            add(findings, "blocking", "duplicate_designator", dlabel,
                "同一行内位号重复：%s" % designator)
            continue
        accepted.append(designator)
        if designator in seen:
            add(findings, "blocking", "duplicate_designator", dlabel,
                "位号 %s 已在 %s 出现；一个位号只能属于一个料行"
                % (designator, seen[designator]))
        else:
            seen[designator] = label
    return accepted


def check_part(index, part, findings, seen):
    label = "parts[%d]" % index
    if not isinstance(part, dict):
        add(findings, "blocking", "part_not_object", label,
            "每个 part 必须是对象")
        return None

    if "role" not in part:
        add(findings, "warning", "missing_role", label + ".role",
            "建议记录 role（功能角色），便于装配/测试追溯")
    elif not is_text(part.get("role")):
        add(findings, "warning", "invalid_role", label + ".role",
            "role 必须是非空字符串")

    for field in ("mpn", "manufacturer", "footprint", "package"):
        value = part.get(field)
        if not is_text(value):
            add(findings, "blocking", "missing_" + field, label + "." + field,
                "缺少 %s；空白或占位符必须在采购前补实" % field)
        elif is_placeholder(value):
            add(findings, "blocking", "placeholder_" + field,
                label + "." + field,
                "%s 仍是占位符（%s），不是可采购/可制造的确定值"
                % (field, value.strip()))

    if not is_text(part.get("datasheet")) or is_placeholder(part.get("datasheet")):
        add(findings, "warning", "missing_datasheet", label + ".datasheet",
            "缺少 datasheet 链接/文件名；关键参数无出处时不能判已核")

    info = {
        "assembly": None,
        "designators": check_designators(part, label, findings, seen),
        "mpn": part.get("mpn") if is_text(part.get("mpn")) else None,
    }

    assembly = part.get("assembly")
    if assembly not in ASSEMBLY_VALUES:
        add(findings, "blocking", "invalid_assembly", label + ".assembly",
            "assembly 必须是 smt|hand|tht|dnp 之一")
        assembly = None
    info["assembly"] = assembly

    if assembly == "smt":
        smt_class = part.get("smt_class")
        if smt_class is None:
            add(findings, "blocking", "missing_smt_class", label + ".smt_class",
                "SMT 料必须记录 smt_class（basic|extended|consigned|pending）")
        elif smt_class not in SMT_CLASSES:
            add(findings, "blocking", "invalid_smt_class", label + ".smt_class",
                "smt_class 必须是 basic|extended|consigned|pending 之一")
        elif smt_class == "pending":
            add(findings, "warning", "smt_class_pending", label + ".smt_class",
                "SMT 可贴分类待核，不能当作可贴证据")

    if assembly != "dnp":
        check_stock(part, label, findings)

    check_lcsc(part.get("lcsc"), label, findings, required=(assembly != "dnp"))

    check_alternates(part.get("alternates"), label, findings, info["mpn"])

    if assembly in ("hand", "tht"):
        package_text = " ".join((str(part.get("package") or ""),
                                 str(part.get("footprint") or ""))).upper()
        match = TINY_PACKAGE_RE.search(package_text)
        if match:
            code = match.group(1)
            if code == "0201":
                add(findings, "blocking", "unsuitable_hand_solder",
                    label + ".package",
                    "0201 封装无法可靠手焊；改用 SMT 或换 0402/0603")
            else:
                add(findings, "warning", "hand_solder_0402", label + ".package",
                    "0402/1005 手焊难度高；优先交 SMT 或换 0603/1608，"
                    "坚持手焊须记录返修能力与验收标准")

    return info


def analyze(data):
    findings = []
    seen = {}
    buckets = {key: [] for key in ASSEMBLY_VALUES}
    total_designators = 0
    for index, part in enumerate(data["parts"]):
        info = check_part(index, part, findings, seen)
        if info is None:
            continue
        total_designators += len(info["designators"])
        if info["assembly"] in buckets:
            buckets[info["assembly"]].extend(info["designators"])
    return findings, buckets, total_designators


def apply_strict(findings):
    promoted = 0
    for finding in findings:
        if finding["level"] == "warning":
            finding["level"] = "blocking"
            finding["promoted"] = True
            promoted += 1
    return promoted


def counts_of(findings, buckets, parts, total_designators, promoted):
    blocking = sum(1 for item in findings if item["level"] == "blocking")
    warning = sum(1 for item in findings if item["level"] == "warning")
    return {
        "parts": parts,
        "designators": total_designators,
        "assembly_designators": sum(
            len(buckets[key]) for key in ("smt", "hand", "tht")),
        "dnp_designators": len(buckets["dnp"]),
        "smt_designators": len(buckets["smt"]),
        "hand_designators": len(buckets["hand"]),
        "tht_designators": len(buckets["tht"]),
        "blocking": blocking,
        "warning": warning,
        "promoted": promoted,
    }


def build_result(data, findings, buckets, total_designators, promoted,
                 strict, path):
    findings.sort(key=lambda item: 0 if item["level"] == "blocking" else 1)
    counts = counts_of(findings, buckets, len(data["parts"]),
                       total_designators, promoted)
    return {
        "schema": REPORT_SCHEMA,
        "input": str(path),
        "parts_schema": PARTS_SCHEMA,
        "project": data.get("project"),
        "status": "pass" if counts["blocking"] == 0 else "needs_review",
        "strict": strict,
        "counts": counts,
        "assembly": buckets,
        "findings": findings,
        "not_checked": list(NOT_CHECKED),
    }


def invalid_result(message, path=None):
    return {
        "schema": REPORT_SCHEMA,
        "input": str(path) if path is not None else None,
        "parts_schema": None,
        "project": None,
        "status": "invalid_input",
        "strict": False,
        "counts": {
            "parts": 0,
            "designators": 0,
            "assembly_designators": 0,
            "dnp_designators": 0,
            "smt_designators": 0,
            "hand_designators": 0,
            "tht_designators": 0,
            "blocking": 0,
            "warning": 0,
            "promoted": 0,
        },
        "assembly": {key: [] for key in ASSEMBLY_VALUES},
        "findings": [],
        "not_checked": list(NOT_CHECKED),
        "error": message,
    }


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON number: %s" % value)


def load_input(path):
    raw = Path(path).read_text(encoding="utf-8-sig")
    data = json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=reject_constant)
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    if data.get("schema") != PARTS_SCHEMA:
        raise ValueError("schema must be %r" % PARTS_SCHEMA)
    parts = data.get("parts")
    if not isinstance(parts, list):
        raise ValueError("parts must be an array")
    if not parts:
        raise ValueError("parts must contain at least one part")
    project = data.get("project")
    if project is not None and not is_text(project):
        raise ValueError("project must be a nonblank string")
    return data


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps(invalid_result(message), ensure_ascii=False))
        raise SystemExit(2)


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("parts", help="path to a parts/v1 JSON file")
    parser.add_argument("--strict", action="store_true",
                        help="promote warnings to blocking")
    parser.add_argument("--json", action="store_true",
                        help="emit one JSON report (default)")
    args = parser.parse_args(argv)
    try:
        data = load_input(args.parts)
        findings, buckets, total_designators = analyze(data)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps(invalid_result(str(exc), args.parts),
                         ensure_ascii=False))
        return 2
    promoted = apply_strict(findings) if args.strict else 0
    report = build_result(data, findings, buckets, total_designators,
                          promoted, args.strict, args.parts)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["counts"]["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
