"""Input contract, validation and normalisation for procurement-input/v1.

Every price is a Decimal parsed from a JSON string/integer; every timestamp is
an aware RFC3339 instant compared in UTC against one declared evaluation
moment.  Structural or semantic violations become ``blocking`` findings and the
command reports ``status=input_invalid`` (exit 2) instead of guessing a value.
"""

from __future__ import annotations

import re
from decimal import Decimal

from . import INPUT_SCHEMA
from .errors import Findings, InputError
from .money import (CURRENCIES, TAX_BASES, parse_amount, parse_currency,
                    parse_fx_rate, parse_tax_basis)
from .util import (MAX_JSON_BYTES, ago_hours, format_utc, is_sha256, load_json,
                   normalize_identity, normalize_supply_id, parse_bool,
                   parse_decimal, parse_enum, parse_int, parse_rfc3339,
                   parse_text, safe_relative_name, utc_now)

CHANNELS = ("lcsc_mall", "jlc_smt", "other_supplier")
ASSEMBLY = ("smt", "tht", "hand", "dnp")
SNAPSHOT_SOURCES = ("synthetic_fixture", "user_provided",
                    "official_api_export", "manual_table")
DECLARED_TRUTH = ("synthetic_not_live", "user_provided_unverified",
                  "manual_table_unverified", "official_export")
STOCK_STATUSES = ("in_stock", "low", "out_of_stock", "unknown",
                  "not_applicable")
SMT_ATTACHABILITY = ("basic", "extended", "consigned", "unknown",
                     "not_applicable")
LEAD_TIME_KINDS = ("in_stock", "estimated", "committed", "unknown",
                   "not_applicable")
PRICE_MODES = ("total_tier", "progressive")
PRICE_UNITS = ("per_each", "per_pack")
FEE_BASES = ("per_order", "per_line", "per_part", "per_board",
             "percent_of_subtotal")
FEE_KINDS = ("shipping", "tax", "smt_extended_part_fee", "smt_board_fee",
             "stencil", "handling", "other")
ASSEMBLY_STRATEGIES = ("smt", "hand_solder", "mixed")
DESIGNATOR_RE = re.compile(r"^[A-Z]{1,5}\d{1,5}$")
LCSC_RE = re.compile(r"^C\d+$")
PLACEHOLDERS = {"tbd", "todo", "待核", "待查", "待定", "unknown", "n/a", "-",
                "?", "xx", "xxx"}
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

TOP_LEVEL_KEYS = {
    "schema", "project", "evaluation", "policies", "bom", "demand", "offers",
    "supply_snapshots", "fees", "fx_rates", "alternates", "notes",
}


def safe_text(value, where, required=True, max_len=300):
    text = parse_text(value, where, required=required, max_len=max_len)
    if text is None:
        return None
    if CONTROL_RE.search(text):
        raise InputError("control_character_in_text",
                         "文本包含控制字符，拒绝执行/导出", where)
    return text


def identity_text(value, where, required=True):
    text = safe_text(value, where, required=required, max_len=200)
    if text is None:
        return None
    if text.strip().lower() in PLACEHOLDERS:
        raise InputError("placeholder_identity",
                         "标识仍是占位符 %r，不能作为可采购身份" % text, where)
    return text


def _require_object(value, where):
    if not isinstance(value, dict):
        raise InputError("invalid_object", "必须是 JSON 对象", where)
    return value


def _require_array(value, where, allow_empty=False):
    if not isinstance(value, list):
        raise InputError("invalid_array", "必须是 JSON 数组", where)
    if not value and not allow_empty:
        raise InputError("empty_array", "数组不能为空", where)
    return value


def _check_keys(obj, allowed, where, findings, label="key"):
    unknown = sorted(set(obj) - set(allowed))
    for key in unknown:
        findings.warning("unknown_%s" % label, "%s.%s" % (where, key),
                         "未知字段被保留但不参与计算：%s" % key)


class Prepared:
    """Normalised input plus validation findings."""

    def __init__(self):
        self.findings = Findings()
        self.raw = None
        self.input_sha256 = None
        self.evaluation = {}
        self.project = {}
        self.policies = {}
        self.demand = {}
        self.rows = []
        self.snapshots = {}
        self.offers = []
        self.fees = []
        self.fx_rates = []
        self.alternates = []
        self.csv = None
        self.notes = []

    @property
    def ok(self):
        return self.findings.blocking_count == 0


def parse_sha256(value, where, required=False):
    if value is None:
        if required:
            raise InputError("missing_sha256", "缺少 sha256", where)
        return None
    text = parse_text(value, where)
    if text.lower().startswith("sha256:"):
        text = text[7:]
    if not is_sha256(text):
        raise InputError("invalid_sha256", "必须是 64 位十六进制 sha256", where)
    return text.lower()


def _parse_evaluation(doc, prepared, as_of_override):
    evaluation = doc.get("evaluation", {})
    evaluation = _require_object(evaluation, "evaluation")
    declared = evaluation.get("as_of")
    if as_of_override is not None:
        as_of = as_of_override
        source = "cli"
        if declared is not None:
            prepared.findings.warning(
                "as_of_overridden", "evaluation.as_of",
                "CLI --as-of 覆盖输入的评估时刻；报告以 CLI 时刻重放")
    elif declared is not None:
        as_of = parse_rfc3339(declared, "evaluation.as_of")
        source = "input"
    else:
        as_of = utc_now()
        source = "system"
    freshness = evaluation.get("freshness", {})
    freshness = _require_object(freshness, "evaluation.freshness")
    max_age = None
    if freshness.get("max_age_hours") is not None:
        max_age = parse_decimal(freshness.get("max_age_hours"),
                                "evaluation.freshness.max_age_hours",
                                minimum=Decimal("0"))
    prepared.evaluation = {
        "as_of": as_of,
        "as_of_source": source,
        "max_age_hours": max_age,
    }


def _parse_project(doc, prepared):
    project = _require_object(doc.get("project"), "project")
    _check_keys(project, {"name", "bom_revision", "bom_source_sha256",
                          "board_quantity", "allow_zero_boards"}, "project",
                prepared.findings)
    name = safe_text(project.get("name"), "project.name", max_len=120)
    revision = safe_text(project.get("bom_revision"), "project.bom_revision",
                         max_len=120)
    boards = parse_int(project.get("board_quantity"),
                       "project.board_quantity", minimum=0,
                       maximum=1000000)
    allow_zero = parse_bool(project.get("allow_zero_boards", False),
                            "project.allow_zero_boards", required=False,
                            default=False)
    if boards == 0 and not allow_zero:
        raise InputError(
            "zero_board_quantity",
            "board_quantity=0 需显式 allow_zero_boards=true；零板不采购，"
            "不能当作正常批量", "project.board_quantity")
    if boards == 0:
        prepared.findings.warning("zero_demand", "project.board_quantity",
                                  "板数量为 0：本批无装配需求，仅验证数据")
    source_hash = parse_sha256(project.get("bom_source_sha256"),
                               "project.bom_source_sha256")
    if source_hash is None:
        prepared.findings.warning(
            "missing_bom_source_hash", "project.bom_source_sha256",
            "未声明 BOM 源哈希；报告会给出计算哈希，但无法核对来源版本")
    prepared.project = {
        "name": name,
        "bom_revision": revision,
        "bom_source_sha256": source_hash,
        "board_quantity": boards,
        "allow_zero_boards": allow_zero,
    }


def _parse_policies(doc, prepared):
    raw = doc.get("policies", {})
    raw = _require_object(raw, "policies")
    _check_keys(raw, {"attrition", "overbuy", "order_policy", "substitution",
                      "channel_preference", "search"}, "policies",
                prepared.findings)
    attrition_raw = raw.get("attrition", {})
    attrition_raw = _require_object(attrition_raw, "policies.attrition")
    _check_keys(attrition_raw, {"ratio", "fixed", "minimum", "order"},
                "policies.attrition", prepared.findings)
    ratio = parse_decimal(attrition_raw.get("ratio", "0"),
                          "policies.attrition.ratio", minimum=Decimal("0"),
                          maximum=Decimal("1"))
    fixed = parse_int(attrition_raw.get("fixed", 0),
                      "policies.attrition.fixed", minimum=0, maximum=100000)
    minimum = parse_int(attrition_raw.get("minimum", 0),
                        "policies.attrition.minimum", minimum=0,
                        maximum=100000)
    order = attrition_raw.get("order", ["ratio", "fixed", "minimum"])
    _require_array(order, "policies.attrition.order")
    if order != ["ratio", "fixed", "minimum"]:
        raise InputError(
            "unsupported_attrition_order",
            "首期只支持明确的顺序 ratio -> fixed -> minimum；"
            "不得静默改序", "policies.attrition.order")
    overbuy_raw = raw.get("overbuy", {})
    overbuy_raw = _require_object(overbuy_raw, "policies.overbuy")
    _check_keys(overbuy_raw, {"max_extra_qty", "max_extra_ratio",
                              "allow_price_break_extra"},
                "policies.overbuy", prepared.findings)
    max_extra_qty = parse_int(overbuy_raw.get("max_extra_qty", 50),
                              "policies.overbuy.max_extra_qty", minimum=0,
                              maximum=1000000)
    max_extra_ratio = parse_decimal(overbuy_raw.get("max_extra_ratio", "0.20"),
                                    "policies.overbuy.max_extra_ratio",
                                    minimum=Decimal("0"),
                                    maximum=Decimal("1"))
    allow_break = parse_bool(
        overbuy_raw.get("allow_price_break_extra", True),
        "policies.overbuy.allow_price_break_extra", required=False,
        default=True)
    order_policy = parse_enum(raw.get("order_policy", "moq_mpq"),
                              ("moq_mpq",), "policies.order_policy")
    substitution_raw = raw.get("substitution", {})
    substitution_raw = _require_object(substitution_raw,
                                       "policies.substitution")
    _check_keys(substitution_raw, {"enabled", "allowed_grades"},
                "policies.substitution", prepared.findings)
    substitution_enabled = parse_bool(
        substitution_raw.get("enabled", False),
        "policies.substitution.enabled", required=False, default=False)
    allowed_grades = substitution_raw.get(
        "allowed_grades", ["exact_identity", "evidence_supported_candidate"])
    _require_array(allowed_grades, "policies.substitution.allowed_grades")
    for grade in allowed_grades:
        parse_enum(grade, ("exact_identity", "evidence_supported_candidate",
                           "requires_design_review", "incompatible",
                           "insufficient_evidence"),
                   "policies.substitution.allowed_grades[]")
    search_raw = raw.get("search", {})
    search_raw = _require_object(search_raw, "policies.search")
    _check_keys(search_raw, {"max_search_steps"}, "policies.search",
                prepared.findings)
    max_search_steps = parse_int(
        search_raw.get("max_search_steps", 10000),
        "policies.search.max_search_steps", minimum=1, maximum=10000000)
    channel_pref = raw.get("channel_preference",
                           ["lcsc_mall", "jlc_smt"])
    _require_array(channel_pref, "policies.channel_preference")
    for channel in channel_pref:
        parse_enum(channel, CHANNELS, "policies.channel_preference[]")
    prepared.policies = {
        "attrition": {
            "ratio": ratio,
            "fixed": fixed,
            "minimum": minimum,
            "order": ["ratio", "fixed", "minimum"],
        },
        "overbuy": {
            "max_extra_qty": max_extra_qty,
            "max_extra_ratio": max_extra_ratio,
            "allow_price_break_extra": allow_break,
        },
        "order_policy": order_policy,
        "substitution": {
            "enabled": substitution_enabled,
            "allowed_grades": list(allowed_grades),
        },
        "search": {"max_search_steps": max_search_steps},
        "channel_preference": list(channel_pref),
    }


def _parse_demand(doc, prepared, cli_snapshot=None):
    demand = _require_object(doc.get("demand"), "demand")
    _check_keys(demand, {"channels", "assembly_strategy", "hand_solder_allowed",
                         "self_supply_allowed", "allowed_channels",
                         "due_date", "budget", "substitution_policy",
                         "overbuy", "split_policy", "channel_preference"},
                "demand", prepared.findings)
    channels_raw = demand.get("allowed_channels", demand.get("channels"))
    _require_array(channels_raw, "demand.channels")
    channels = []
    for index, channel in enumerate(channels_raw):
        value = parse_enum(channel, CHANNELS, "demand.channels[%d]" % index)
        if value in channels:
            raise InputError("duplicate_channel", "渠道重复", "demand.channels")
        channels.append(value)
    strategy = parse_enum(demand.get("assembly_strategy", "smt"),
                          ASSEMBLY_STRATEGIES, "demand.assembly_strategy")
    hand_allowed = parse_bool(demand.get("hand_solder_allowed", False),
                              "demand.hand_solder_allowed", required=False,
                              default=False)
    self_allowed = parse_bool(demand.get("self_supply_allowed", False),
                              "demand.self_supply_allowed", required=False,
                              default=False)
    due_date = parse_rfc3339(demand.get("due_date"), "demand.due_date",
                             required=False, allow_date_only=True)
    budget = None
    budget_raw = demand.get("budget")
    if budget_raw is not None:
        budget_raw = _require_object(budget_raw, "demand.budget")
        _check_keys(budget_raw, {"amount", "currency"}, "demand.budget",
                    prepared.findings)
        budget = {
            "amount": parse_amount(budget_raw.get("amount"),
                                   "demand.budget.amount"),
            "currency": parse_currency(budget_raw.get("currency"),
                                       "demand.budget.currency"),
        }
    split_raw = demand.get("split_policy", {})
    split_raw = _require_object(split_raw, "demand.split_policy")
    _check_keys(split_raw, {"allow_multi_offer", "max_orders_per_line",
                            "max_orders_total"}, "demand.split_policy",
                prepared.findings)
    split = {
        "allow_multi_offer": parse_bool(
            split_raw.get("allow_multi_offer", True),
            "demand.split_policy.allow_multi_offer", required=False,
            default=True),
        "max_orders_per_line": parse_int(
            split_raw.get("max_orders_per_line", 3),
            "demand.split_policy.max_orders_per_line", minimum=1,
            maximum=50, allow_none=True),
        "max_orders_total": parse_int(
            split_raw.get("max_orders_total"),
            "demand.split_policy.max_orders_total", minimum=1,
            maximum=500, allow_none=True),
    }
    substitution_raw = demand.get("substitution_policy")
    substitution = dict(prepared.policies["substitution"])
    if substitution_raw is not None:
        substitution_raw = _require_object(substitution_raw,
                                           "demand.substitution_policy")
        _check_keys(substitution_raw, {"enabled", "allowed_grades"},
                    "demand.substitution_policy", prepared.findings)
        substitution["enabled"] = parse_bool(
            substitution_raw.get("enabled", False),
            "demand.substitution_policy.enabled", required=False,
            default=False)
        allowed = substitution_raw.get("allowed_grades",
                                       substitution["allowed_grades"])
        _require_array(allowed, "demand.substitution_policy.allowed_grades")
        for grade in allowed:
            parse_enum(grade, ("exact_identity",
                               "evidence_supported_candidate",
                               "requires_design_review", "incompatible",
                               "insufficient_evidence"),
                       "demand.substitution_policy.allowed_grades[]")
        substitution["allowed_grades"] = list(allowed)
    overbuy = dict(prepared.policies["overbuy"])
    overbuy_raw = demand.get("overbuy")
    if overbuy_raw is not None:
        overbuy_raw = _require_object(overbuy_raw, "demand.overbuy")
        _check_keys(overbuy_raw, {"max_extra_qty", "max_extra_ratio",
                                  "allow_price_break_extra"},
                    "demand.overbuy", prepared.findings)
        overbuy["max_extra_qty"] = parse_int(
            overbuy_raw.get("max_extra_qty", overbuy["max_extra_qty"]),
            "demand.overbuy.max_extra_qty", minimum=0, maximum=1000000)
        overbuy["max_extra_ratio"] = parse_decimal(
            overbuy_raw.get("max_extra_ratio",
                            str(overbuy["max_extra_ratio"])),
            "demand.overbuy.max_extra_ratio", minimum=Decimal("0"),
            maximum=Decimal("1"))
        overbuy["allow_price_break_extra"] = parse_bool(
            overbuy_raw.get("allow_price_break_extra",
                            overbuy["allow_price_break_extra"]),
            "demand.overbuy.allow_price_break_extra", required=False,
            default=True)
    channel_pref = demand.get("channel_preference",
                              prepared.policies["channel_preference"])
    _require_array(channel_pref, "demand.channel_preference")
    pref = []
    for channel in channel_pref:
        value = parse_enum(channel, CHANNELS, "demand.channel_preference[]")
        if value not in pref:
            pref.append(value)
    if not pref:
        raise InputError("empty_channel_preference",
                         "channel_preference 不能为空",
                         "demand.channel_preference")
    prepared.demand = {
        "channels": list(channels),
        "assembly_strategy": strategy,
        "hand_solder_allowed": hand_allowed,
        "self_supply_allowed": self_allowed,
        "due_date": due_date,
        "budget": budget,
        "split_policy": split,
        "substitution": substitution,
        "overbuy": overbuy,
        "channel_preference": pref,
    }
    if cli_snapshot:
        prepared.demand["snapshot_override"] = cli_snapshot


def _parse_supply_ids(raw, where):
    obj = _require_object(raw, where)
    unknown = sorted(set(obj) - {"lcsc", "other"})
    if unknown:
        raise InputError("unknown_supply_id_scheme",
                         "供应 ID 只支持 lcsc/other：%s" % ", ".join(unknown),
                         where)
    result = {}
    if obj.get("lcsc") is not None:
        lcsc = normalize_supply_id(safe_text(obj.get("lcsc"),
                                             where + ".lcsc", max_len=40))
        if not LCSC_RE.match(lcsc):
            raise InputError("invalid_lcsc", "C 号格式应为 C<数字>", where)
        result["lcsc"] = lcsc
    if obj.get("other") is not None:
        result["other"] = safe_text(obj.get("other"), where + ".other",
                                    max_len=100)
    return result


def _parse_rows(doc, prepared, cli_rows=None):
    bom = _require_object(doc.get("bom"), "bom")
    _check_keys(bom, {"rows", "revision", "notes", "source"}, "bom",
                prepared.findings)
    raw_rows = bom.get("rows")
    if cli_rows is not None:
        if raw_rows not in (None, []):
            raise InputError(
                "bom_rows_and_csv",
                "输入 JSON 已含 bom.rows，同时又传 --bom-csv；二者只能选一",
                "bom.rows")
        raw_rows = cli_rows
    _require_array(raw_rows, "bom.rows")
    seen_designators = {}
    seen_lines = {}
    seen_identities = {}
    rows = []
    for index, raw in enumerate(raw_rows):
        where = "bom.rows[%d]" % index
        raw = _require_object(raw, where)
        _check_keys(raw, {"line_id", "designators", "qty_per_board", "mpn",
                          "manufacturer", "supply_ids", "footprint",
                          "package", "description", "assembly", "dnp",
                          "consigned_qty", "consigned_qualified", "params",
                          "unknown_fields", "identity_source", "role",
                          "notes"}, where, prepared.findings)
        line_id = safe_relative_name(raw.get("line_id"), where + ".line_id")
        if line_id in seen_lines:
            raise InputError("duplicate_line_id", "line_id 重复：%s" % line_id,
                             where + ".line_id")
        seen_lines[line_id] = index
        designators = []
        raw_designators = raw.get("designators", [])
        if raw_designators is None:
            raw_designators = []
        _require_array(raw_designators, where + ".designators",
                       allow_empty=True)
        for pos, designator in enumerate(raw_designators):
            text = parse_text(designator,
                              "%s.designators[%d]" % (where, pos),
                              max_len=20).upper()
            if not DESIGNATOR_RE.match(text):
                raise InputError("invalid_designator",
                                 "位号格式应为字母+数字（如 R1、U12）",
                                 "%s.designators[%d]" % (where, pos))
            if text in designators:
                raise InputError("duplicate_designator_same_row",
                                 "同一行位号重复：%s" % text,
                                 where + ".designators")
            if text in seen_designators:
                raise InputError(
                    "duplicate_designator",
                    "位号 %s 已出现在 %s；一个位号只能属于一个料行"
                    % (text, seen_designators[text]), where + ".designators")
            seen_designators[text] = line_id
            designators.append(text)
        qty_raw = raw.get("qty_per_board")
        qty = None
        if qty_raw is not None:
            qty = parse_int(qty_raw, where + ".qty_per_board", minimum=0,
                            maximum=100000)
        if designators and qty is not None and len(designators) != qty:
            raise InputError(
                "quantity_designator_mismatch",
                "位号数 %d 与 qty_per_board %d 不一致；请核对 BOM 而不是"
                "猜测" % (len(designators), qty), where)
        if not designators and qty is None:
            raise InputError("missing_quantity",
                             "缺少 designators 或 qty_per_board", where)
        if not designators:
            prepared.findings.warning(
                "missing_designators", where + ".designators",
                "该行没有位号，仅按数量规划；位号追溯缺失")
        if qty is None:
            qty = len(designators)
        mpn = identity_text(raw.get("mpn"), where + ".mpn")
        manufacturer = identity_text(raw.get("manufacturer"),
                                     where + ".manufacturer")
        footprint = identity_text(raw.get("footprint"), where + ".footprint")
        package = safe_text(raw.get("package"), where + ".package",
                            required=False, max_len=120)
        description = safe_text(raw.get("description"),
                                where + ".description", required=False,
                                max_len=300)
        assembly = parse_enum(raw.get("assembly"), ASSEMBLY,
                              where + ".assembly")
        dnp = parse_bool(raw.get("dnp", assembly == "dnp"),
                         where + ".dnp", required=False,
                         default=(assembly == "dnp"))
        if dnp and assembly != "dnp":
            prepared.findings.warning(
                "dnp_assembly_conflict", where,
                "dnp=true 但 assembly=%s；按 DNP 处理且不采购" % assembly)
            assembly = "dnp"
        if assembly == "dnp":
            dnp = True
        consigned = parse_int(raw.get("consigned_qty", 0),
                              where + ".consigned_qty", minimum=0,
                              maximum=10000000)
        consigned_qualified = parse_bool(
            raw.get("consigned_qualified", True),
            where + ".consigned_qualified", required=False, default=True)
        supply_ids = _parse_supply_ids(raw.get("supply_ids", {}),
                                       where + ".supply_ids")
        if not supply_ids:
            prepared.findings.warning(
                "missing_supply_id", where + ".supply_ids",
                "没有 C 号或其它供应 ID；只能按 MPN/封装匹配 offer")
        identity_source_raw = raw.get("identity_source")
        identity_source = None
        if identity_source_raw is not None:
            identity_source_raw = _require_object(identity_source_raw,
                                                  where + ".identity_source")
            identity_source = {
                "kind": parse_enum(
                    identity_source_raw.get("kind"),
                    ("user_bom", "csv_import", "manual", "official_export",
                     "synthetic_fixture"),
                    where + ".identity_source.kind"),
                "source": safe_text(identity_source_raw.get("source"),
                                    where + ".identity_source.source",
                                    max_len=300),
            }
            if identity_source_raw.get("captured_at") is not None:
                identity_source["captured_at"] = parse_rfc3339(
                    identity_source_raw.get("captured_at"),
                    where + ".identity_source.captured_at")
            else:
                identity_source["captured_at"] = None
        else:
            prepared.findings.warning(
                "missing_identity_source", where + ".identity_source",
                "器件身份没有来源；采购前须补充 BOM/商城/EDA 身份来源")
        params = raw.get("params", {})
        params = _require_object(params, where + ".params")
        clean_params = {}
        for key, value in params.items():
            if not isinstance(key, str) or not key:
                raise InputError("invalid_param_key", "参数名必须是非空字符串",
                                 where + ".params")
            if isinstance(value, bool) or isinstance(value, (dict, list)):
                raise InputError("invalid_param_value",
                                 "参数值必须是字符串/整数/有限小数", where +
                                 ".params." + key)
            if isinstance(value, float):
                raise InputError("float_param_rejected",
                                 "参数值不接受 float；请写字符串", where +
                                 ".params." + key)
            clean_params[key] = value
        unknown_fields = raw.get("unknown_fields", [])
        _require_array(unknown_fields, where + ".unknown_fields",
                       allow_empty=True)
        for pos, value in enumerate(unknown_fields):
            parse_text(value, "%s.unknown_fields[%d]" % (where, pos),
                       max_len=100)
        identity_key = (normalize_identity(mpn),
                        normalize_identity(footprint))
        if identity_key in seen_identities:
            prepared.findings.warning(
                "duplicate_identity_rows", where,
                "同一 MPN+封装出现在多行（%s）；各行可独立规划，但库存会"
                "在同池内共享" % seen_identities[identity_key])
        else:
            seen_identities[identity_key] = line_id
        row = {
            "line_id": line_id,
            "designators": designators,
            "qty_per_board": qty,
            "mpn": mpn,
            "manufacturer": manufacturer,
            "supply_ids": supply_ids,
            "footprint": footprint,
            "package": package,
            "description": description,
            "assembly": assembly,
            "dnp": dnp,
            "consigned_qty": consigned,
            "consigned_qualified": consigned_qualified,
            "params": clean_params,
            "unknown_fields": list(unknown_fields),
            "identity_source": identity_source,
        }
        rows.append(row)
    if not rows:
        raise InputError("empty_bom", "BOM 没有料行", "bom.rows")
    same_mpn = {}
    for row in rows:
        key = normalize_identity(row["mpn"])
        other = same_mpn.get(key)
        if other is not None and (normalize_identity(other["footprint"])
                                  != normalize_identity(row["footprint"])):
            prepared.findings.warning(
                "same_mpn_different_footprint", "bom.rows[%s]"
                % row["line_id"],
                "同 MPN 在不同行使用不同封装（%s vs %s）；身份不能互相代替"
                % (other["footprint"], row["footprint"]))
        same_mpn.setdefault(key, row)
    prepared.rows = rows
    prepared.bom_meta = {
        "revision": safe_text(bom.get("revision"),
                              "bom.revision", required=False, max_len=120),
        "source": safe_text(bom.get("source"), "bom.source", required=False,
                            max_len=300),
        "notes": safe_text(bom.get("notes"), "bom.notes", required=False,
                           max_len=500),
    }


def _parse_snapshots(doc, prepared):
    raw = doc.get("supply_snapshots", [])
    _require_array(raw, "supply_snapshots", allow_empty=True)
    snapshots = {}
    for index, item in enumerate(raw):
        where = "supply_snapshots[%d]" % index
        item = _require_object(item, where)
        _check_keys(item, {"snapshot_id", "source", "declared_truth",
                           "captured_at", "valid_until", "channel",
                           "sha256", "notes", "live_supply_query"},
                    where, prepared.findings)
        snapshot_id = safe_relative_name(item.get("snapshot_id"),
                                         where + ".snapshot_id")
        if snapshot_id in snapshots:
            raise InputError("duplicate_snapshot_id",
                             "snapshot_id 重复：%s" % snapshot_id, where)
        source = parse_enum(item.get("source"), SNAPSHOT_SOURCES,
                            where + ".source")
        truth = parse_enum(item.get("declared_truth"), DECLARED_TRUTH,
                           where + ".declared_truth")
        if truth == "official_export" and source != "official_api_export":
            prepared.findings.warning(
                "truth_source_mismatch", where + ".declared_truth",
                "declared_truth=official_export 但 source=%s；按声明保留，"
                "不提升为实时" % source)
        if source == "synthetic_fixture" and truth != "synthetic_not_live":
            raise InputError(
                "synthetic_truth_conflict", "合成数据必须声明 "
                "declared_truth=synthetic_not_live", where + ".declared_truth")
        captured = parse_rfc3339(item.get("captured_at"),
                                 where + ".captured_at")
        as_of = prepared.evaluation["as_of"]
        if captured > as_of:
            raise InputError("future_timestamp",
                             "captured_at 晚于评估时刻 %s；未来时间不可用于"
                             "规划" % format_utc(as_of), where + ".captured_at")
        valid_until = parse_rfc3339(item.get("valid_until"),
                                    where + ".valid_until", required=False)
        if valid_until is not None and valid_until < captured:
            raise InputError("invalid_validity_window",
                             "valid_until 早于 captured_at", where)
        channel = parse_enum(item.get("channel"), CHANNELS,
                             where + ".channel", required=True)
        age = ago_hours(captured, as_of)
        max_age = prepared.evaluation["max_age_hours"]
        stale_reasons = []
        if valid_until is not None and as_of > valid_until:
            stale_reasons.append("valid_until_expired")
        if max_age is not None and Decimal(str(age)) > max_age:
            stale_reasons.append("max_age_exceeded")
        live_query = item.get("live_supply_query")
        if live_query is not None:
            live_query = parse_bool(live_query, where + ".live_supply_query",
                                    required=False, default=False)
        else:
            live_query = False
        if live_query and source != "official_api_export":
            prepared.findings.warning(
                "live_query_source_mismatch", where + ".live_supply_query",
                "只有 official_api_export 快照才可声明 live_supply_query；"
                "本工具不执行查询")
            live_query = False
        snapshots[snapshot_id] = {
            "snapshot_id": snapshot_id,
            "source": source,
            "declared_truth": truth,
            "captured_at": captured,
            "valid_until": valid_until,
            "channel": channel,
            "sha256": parse_sha256(item.get("sha256"), where + ".sha256"),
            "notes": safe_text(item.get("notes"), where + ".notes",
                               required=False, max_len=500),
            "age_hours": Decimal(str(age)),
            "stale": bool(stale_reasons),
            "stale_reasons": stale_reasons,
            "live_supply_query": bool(live_query),
            "synthetic": truth == "synthetic_not_live",
        }
        if stale_reasons:
            prepared.findings.warning(
                "stale_snapshot", where,
                "快照已过期（%s）；其价格/库存不参与满足性判断"
                % ",".join(stale_reasons))
    prepared.snapshots = snapshots


def _parse_price_tiers(raw, where, mode):
    tiers = _require_array(raw, where)
    parsed = []
    last_min = None
    for index, tier in enumerate(tiers):
        twhere = "%s[%d]" % (where, index)
        tier = _require_object(tier, twhere)
        min_qty = parse_int(tier.get("min_qty"), twhere + ".min_qty",
                            minimum=1, maximum=10000000)
        max_qty = parse_int(tier.get("max_qty"), twhere + ".max_qty",
                            minimum=1, maximum=10000000, allow_none=True)
        unit_price = parse_amount(tier.get("unit_price"),
                                  twhere + ".unit_price")
        if last_min is not None and min_qty <= last_min:
            raise InputError(
                "price_tier_order",
                "价格阶梯必须按 min_qty 严格升序；不接受倒序/重复断点，"
                "也不静默重排", twhere + ".min_qty")
        last_min = min_qty
        if index == 0 and min_qty != 1:
            raise InputError("price_tier_start",
                             "第一档必须从 min_qty=1 开始，否则无法为任意"
                             "数量定价", twhere + ".min_qty")
        if max_qty is not None and max_qty < min_qty:
            raise InputError("price_tier_range", "max_qty 不能小于 min_qty",
                             twhere)
        if parsed and parsed[-1]["max_qty"] is not None:
            if min_qty <= parsed[-1]["max_qty"]:
                raise InputError("price_tier_overlap",
                                 "价格阶梯区间重叠", twhere)
        unit = tier.get("unit")
        if unit is not None:
            unit = parse_enum(unit, PRICE_UNITS, twhere + ".unit")
        parsed.append({
            "min_qty": min_qty,
            "max_qty": max_qty,
            "unit_price": unit_price,
            "unit": unit,
        })
    if mode == "progressive":
        for index, tier in enumerate(parsed):
            if tier["max_qty"] is None and index != len(parsed) - 1:
                raise InputError("progressive_tier_open_ended",
                                 "分段累进价只有最后一档可以无上限",
                                 where + "[%d]" % index)
    return parsed


def _parse_stock(raw, where, findings):
    raw = _require_object(raw, where)
    _check_keys(raw, {"qty", "status", "reserved", "independent",
                      "pool_id"}, where, findings)
    status = parse_enum(raw.get("status"), STOCK_STATUSES,
                        where + ".status")
    qty = parse_int(raw.get("qty"), where + ".qty", minimum=0,
                    maximum=100000000, allow_none=True)
    reserved = parse_int(raw.get("reserved", 0), where + ".reserved",
                         minimum=0, maximum=100000000)
    independent = parse_bool(raw.get("independent", True),
                             where + ".independent", required=False,
                             default=True)
    pool_id = safe_relative_name(raw.get("pool_id"), where + ".pool_id",
                                 max_len=100) if raw.get("pool_id") else None
    if status == "in_stock" and qty is None:
        findings.warning("stock_quantity_missing", where + ".qty",
                         "status=in_stock 但数量未知；未知库存不视作无限")
    if status == "out_of_stock" and qty not in (None, 0):
        raise InputError("stock_status_conflict",
                         "status=out_of_stock 但 qty>0，数据自相矛盾", where)
    if status == "not_applicable" and qty not in (None, 0):
        raise InputError("stock_status_conflict",
                         "status=not_applicable 但 qty>0", where)
    if qty is not None and reserved > qty:
        findings.warning("reserved_exceeds_stock", where + ".reserved",
                         "预留数大于库存数；可用量按 0 计，不制造虚假满足")
    available = None
    if qty is not None and status not in ("unknown", "not_applicable"):
        available = max(0, qty - reserved)
    if not independent and pool_id is None:
        findings.warning(
            "non_independent_stock_without_pool", where,
            "库存声明为不独立但未给 pool_id；无法证明共享关系，按未知库存"
            "处理，避免重复计数")
        available = None
    return {
        "qty": qty,
        "status": status,
        "reserved": reserved,
        "independent": independent,
        "pool_id": pool_id,
        "available": available,
        "unknown": available is None,
    }


def _parse_lead_time(raw, where, findings):
    if raw is None:
        findings.warning("missing_lead_time", where,
                         "没有交期字段；不能判为按时交付")
        return {"kind": "unknown", "days_min": None, "days_max": None,
                "captured_at": None}
    raw = _require_object(raw, where)
    _check_keys(raw, {"kind", "days_min", "days_max", "captured_at", "note"},
                where, findings)
    kind = parse_enum(raw.get("kind"), LEAD_TIME_KINDS, where + ".kind")
    days_min = parse_int(raw.get("days_min"), where + ".days_min", minimum=0,
                         maximum=3650, allow_none=True)
    days_max = parse_int(raw.get("days_max"), where + ".days_max", minimum=0,
                         maximum=3650, allow_none=True)
    if days_min is not None and days_max is not None and days_max < days_min:
        raise InputError("invalid_lead_time_range",
                         "days_max 不能小于 days_min", where)
    if kind == "in_stock":
        if days_min is None and days_max is None:
            days_min = days_max = 0
        elif days_max not in (0, None) or days_min not in (0, None):
            raise InputError("invalid_lead_time",
                             "in_stock 的 days 必须为 0", where)
    if kind in ("estimated", "committed") and days_min is None \
            and days_max is None:
        findings.warning("lead_time_days_missing", where,
                         "交期性质为 %s 但没有天数；不能判按时" % kind)
    captured = parse_rfc3339(raw.get("captured_at"), where + ".captured_at",
                             required=False)
    return {
        "kind": kind,
        "days_min": days_min,
        "days_max": days_max,
        "captured_at": captured,
        "note": safe_text(raw.get("note"), where + ".note", required=False,
                          max_len=300),
    }


def _parse_offers(doc, prepared):
    raw = doc.get("offers", [])
    _require_array(raw, "offers", allow_empty=True)
    seen = set()
    offers = []
    for index, item in enumerate(raw):
        where = "offers[%d]" % index
        item = _require_object(item, where)
        _check_keys(item, {"offer_id", "supplier", "channel", "product_id",
                           "mpn", "manufacturer", "footprint", "package",
                           "currency", "tax_basis", "price_mode",
                           "price_tiers", "price_unit", "moq", "mpq",
                           "stock", "lead_time", "snapshot_id", "smt",
                           "packaging", "notes"}, where,
                    prepared.findings)
        offer_id = safe_relative_name(item.get("offer_id"),
                                      where + ".offer_id")
        if offer_id in seen:
            raise InputError("duplicate_offer_id", "offer_id 重复：%s"
                             % offer_id, where)
        seen.add(offer_id)
        channel = parse_enum(item.get("channel"), CHANNELS,
                             where + ".channel")
        supplier = safe_text(item.get("supplier"), where + ".supplier",
                             max_len=120)
        product_id = safe_text(item.get("product_id"), where + ".product_id",
                               max_len=120)
        mpn = identity_text(item.get("mpn"), where + ".mpn")
        manufacturer = identity_text(item.get("manufacturer"),
                                     where + ".manufacturer",
                                     required=False)
        footprint = identity_text(item.get("footprint"),
                                  where + ".footprint")
        package = safe_text(item.get("package"), where + ".package",
                            required=False, max_len=120)
        currency = parse_currency(item.get("currency"),
                                  where + ".currency")
        tax_basis = parse_tax_basis(item.get("tax_basis"),
                                    where + ".tax_basis")
        price_mode = parse_enum(item.get("price_mode", "total_tier"),
                                PRICE_MODES, where + ".price_mode")
        tiers = _parse_price_tiers(item.get("price_tiers"),
                                   where + ".price_tiers", price_mode)
        unit_raw = _require_object(item.get("price_unit", {"kind": "per_each"}),
                                   where + ".price_unit")
        _check_keys(unit_raw, {"kind", "pack_qty"}, where + ".price_unit",
                    prepared.findings)
        unit_kind = parse_enum(unit_raw.get("kind", "per_each"), PRICE_UNITS,
                               where + ".price_unit.kind")
        pack_qty = parse_int(unit_raw.get("pack_qty"),
                             where + ".price_unit.pack_qty", minimum=1,
                             maximum=1000000, allow_none=True)
        if unit_kind == "per_pack" and pack_qty is None:
            raise InputError("missing_pack_qty",
                             "price_unit=per_pack 必须给 pack_qty，否则包装"
                             "单位与个数混淆", where + ".price_unit")
        if unit_kind == "per_each" and pack_qty not in (None, 1):
            raise InputError("pack_qty_on_each_price",
                             "price_unit=per_each 不应带 pack_qty",
                             where + ".price_unit")
        moq = parse_int(item.get("moq", 0), where + ".moq", minimum=0,
                        maximum=10000000)
        mpq = parse_int(item.get("mpq", 1), where + ".mpq", minimum=1,
                        maximum=1000000)
        if moq % mpq != 0:
            prepared.findings.warning(
                "moq_not_multiple_of_mpq", where,
                "MOQ %d 不是 MPQ %d 的整数倍；可下单量按"
                "ceil(max(need,MOQ)/MPQ)*MPQ 计算" % (moq, mpq))
        stock = _parse_stock(item.get("stock"), where + ".stock",
                             prepared.findings)
        lead_time = _parse_lead_time(item.get("lead_time"),
                                     where + ".lead_time",
                                     prepared.findings)
        snapshot_id = safe_relative_name(item.get("snapshot_id"),
                                         where + ".snapshot_id")
        snapshot = prepared.snapshots.get(snapshot_id)
        if snapshot is None:
            raise InputError("unknown_snapshot",
                             "offer 引用了不存在的快照 %s" % snapshot_id,
                             where + ".snapshot_id")
        trusted = True
        if snapshot["stale"]:
            trusted = False
        if snapshot["channel"] is not None and snapshot["channel"] != channel:
            prepared.findings.warning(
                "snapshot_channel_mismatch", where,
                "offer 渠道 %s 与快照渠道 %s 不一致；该快照不能作为本渠道"
                "证据" % (channel, snapshot["channel"]))
            trusted = False
        smt = None
        smt_raw = item.get("smt")
        if channel == "jlc_smt":
            if smt_raw is None:
                prepared.findings.warning(
                    "smt_fields_missing", where + ".smt",
                    "jlc_smt offer 没有独立 SMT 可贴字段；SMT 状态未知，"
                    "不得由商城库存推断")
                smt = {"attachability": "unknown", "evidence": None,
                       "min_placement_qty": None, "fee_ref": None,
                       "feed_type": None}
            else:
                smt_raw = _require_object(smt_raw, where + ".smt")
                _check_keys(smt_raw, {"attachability", "evidence",
                                      "min_placement_qty", "fee_ref",
                                      "feed_type", "package"}, where + ".smt",
                            prepared.findings)
                attachability = parse_enum(
                    smt_raw.get("attachability"), SMT_ATTACHABILITY,
                    where + ".smt.attachability")
                evidence = smt_raw.get("evidence")
                evidence_ok = False
                if evidence is not None:
                    evidence = _require_object(evidence,
                                               where + ".smt.evidence")
                    _check_keys(evidence, {"source", "captured_at", "note"},
                                where + ".smt.evidence", prepared.findings)
                    source = safe_text(evidence.get("source"),
                                       where + ".smt.evidence.source",
                                       max_len=300)
                    captured = parse_rfc3339(
                        evidence.get("captured_at"),
                        where + ".smt.evidence.captured_at",
                        required=False)
                    if captured is not None and captured > \
                            prepared.evaluation["as_of"]:
                        raise InputError(
                            "future_timestamp",
                            "SMT 证据时间晚于评估时刻",
                            where + ".smt.evidence.captured_at")
                    evidence_ok = True
                else:
                    prepared.findings.warning(
                        "smt_evidence_missing", where + ".smt",
                        "SMT 可贴状态缺少独立来源；只能标状态未知/待核")
                if attachability in ("basic", "extended") and not evidence_ok:
                    prepared.findings.warning(
                        "smt_claim_without_evidence", where + ".smt",
                        "声明基础/扩展库可贴但无来源，不升级为有证据候选")
                smt = {
                    "attachability": attachability,
                    "evidence": evidence,
                    "evidence_ok": evidence_ok,
                    "min_placement_qty": parse_int(
                        smt_raw.get("min_placement_qty"),
                        where + ".smt.min_placement_qty", minimum=1,
                        maximum=1000000, allow_none=True),
                    "fee_ref": safe_text(smt_raw.get("fee_ref"),
                                         where + ".smt.fee_ref",
                                         required=False, max_len=100),
                    "feed_type": safe_text(smt_raw.get("feed_type"),
                                           where + ".smt.feed_type",
                                           required=False, max_len=100),
                }
        elif smt_raw is not None:
            prepared.findings.warning(
                "smt_fields_on_non_smt_offer", where + ".smt",
                "非 jlc_smt 渠道不应携带 SMT 可贴字段；已忽略，避免混用渠道")
        packaging = item.get("packaging")
        if packaging is not None:
            packaging = _require_object(packaging, where + ".packaging")
            _check_keys(packaging, {"kind", "min_qty"}, where + ".packaging",
                        prepared.findings)
            packaging = {
                "kind": safe_text(packaging.get("kind"),
                                  where + ".packaging.kind", max_len=80),
                "min_qty": parse_int(packaging.get("min_qty"),
                                     where + ".packaging.min_qty",
                                     minimum=1, allow_none=True,
                                     maximum=10000000),
            }
        offers.append({
            "offer_id": offer_id,
            "supplier": supplier,
            "channel": channel,
            "product_id": product_id,
            "mpn": mpn,
            "manufacturer": manufacturer,
            "footprint": footprint,
            "package": package,
            "currency": currency,
            "tax_basis": tax_basis,
            "price_mode": price_mode,
            "price_tiers": tiers,
            "price_unit": {"kind": unit_kind, "pack_qty": pack_qty},
            "moq": moq,
            "mpq": mpq,
            "stock": stock,
            "lead_time": lead_time,
            "snapshot_id": snapshot_id,
            "snapshot": snapshot,
            "trusted": trusted,
            "smt": smt,
            "packaging": packaging,
            "notes": safe_text(item.get("notes"), where + ".notes",
                               required=False, max_len=500),
        })
    prepared.offers = offers
    # Cross-offer diagnostics: same supply identity in multiple offers may be
    # the same physical stock; without an explicit pool we flag it but never
    # silently merge the quantities.
    by_product = {}
    by_pool = {}
    for offer in offers:
        key = normalize_supply_id(offer["product_id"])
        by_product.setdefault(key, []).append(offer)
        pool = offer["stock"]["pool_id"]
        if pool:
            by_pool.setdefault(pool, []).append(offer)
    for key, group in sorted(by_product.items()):
        if len(group) > 1:
            pools = {offer["stock"]["pool_id"] for offer in group}
            if len(pools) > 1 or None in pools:
                prepared.findings.warning(
                    "possible_inventory_overlap", "offers",
                    "同一供应 ID %s 出现在多个 offer 且未全部显式归池；"
                    "可能重复计算库存，规划按各自 pool 独立扣减并标注"
                    % key)
            identities = {(normalize_identity(offer["mpn"]),
                           normalize_identity(offer["footprint"]))
                          for offer in group}
            if len(identities) > 1:
                prepared.findings.warning(
                    "supply_id_identity_conflict", "offers",
                    "同一供应 ID %s 对应不同 MPN/封装；不能互相代替" % key)
    by_mpn = {}
    for offer in offers:
        by_mpn.setdefault(normalize_identity(offer["mpn"]), []).append(offer)
    for mpn, group in sorted(by_mpn.items()):
        footprints = {normalize_identity(offer["footprint"]) for offer in group}
        manufacturers = {normalize_identity(offer.get("manufacturer") or "")
                         for offer in group}
        if len(footprints) > 1:
            prepared.findings.warning(
                "same_mpn_different_footprint_offers", "offers",
                "同一 MPN %s 的 offer 使用不同封装 %s；身份不能互相代替"
                % (mpn, sorted(footprints)))
        if len(manufacturers) > 1 and "" not in manufacturers:
            prepared.findings.warning(
                "same_mpn_different_manufacturer_offers", "offers",
                "同一 MPN %s 的 offer 声明了不同制造商；不能直接当同一器件"
                % mpn)
    for pool, group in sorted(by_pool.items()):
        identities = {(normalize_supply_id(offer.get("product_id", "")),
                       normalize_identity(offer["mpn"]),
                       normalize_identity(offer["footprint"]))
                      for offer in group}
        if len(identities) > 1:
            prepared.findings.warning(
                "pool_identity_mismatch", "offers",
                "库存池 %s 被不同供应身份复用；规划按身份拆分库存池，"
                "不把不同器件的库存混成一个数" % pool)
            continue
        quantities = sorted({offer["stock"]["qty"] for offer in group
                             if offer["stock"]["qty"] is not None})
        statuses = {offer["stock"]["status"] for offer in group}
        if len(quantities) > 1:
            prepared.findings.warning(
                "pool_quantity_conflict", "offers",
                "库存池 %s 的 offer 报告了不同数量 %s；规划取最小值作为"
                "保守可用量" % (pool, quantities))
        if "out_of_stock" in statuses and ("in_stock" in statuses
                                           or "low" in statuses):
            prepared.findings.warning(
                "pool_status_conflict", "offers",
                "同一库存池 %s 同时有缺货与在库声明；按保守规则处理" % pool)


def _parse_fees(doc, prepared):
    raw = doc.get("fees", [])
    if raw is None:
        raw = []
    _require_array(raw, "fees", allow_empty=True)
    seen = set()
    fees = []
    for index, item in enumerate(raw):
        where = "fees[%d]" % index
        item = _require_object(item, where)
        _check_keys(item, {"fee_id", "kind", "channel", "amount", "rate",
                           "currency", "basis", "tax_basis", "waiver",
                           "source", "captured_at", "unknown", "note"},
                    where, prepared.findings)
        fee_id = safe_relative_name(item.get("fee_id"), where + ".fee_id")
        if fee_id in seen:
            raise InputError("duplicate_fee_id", "fee_id 重复：%s" % fee_id,
                             where)
        seen.add(fee_id)
        kind = parse_enum(item.get("kind"), FEE_KINDS, where + ".kind")
        channel = parse_enum(item.get("channel", "any"),
                             CHANNELS + ("any",), where + ".channel")
        currency = parse_currency(item.get("currency"), where + ".currency")
        basis = parse_enum(item.get("basis"), FEE_BASES, where + ".basis")
        unknown = parse_bool(item.get("unknown", False),
                             where + ".unknown", required=False, default=False)
        amount = parse_amount(item.get("amount"), where + ".amount",
                              required=False)
        rate = parse_decimal(item.get("rate"), where + ".rate",
                             minimum=Decimal("0"), maximum=Decimal("1"),
                             required=False)
        if unknown:
            if amount is not None or rate is not None:
                raise InputError("unknown_fee_has_amount",
                                 "unknown=true 的费用不得同时给 amount/rate",
                                 where)
        else:
            if amount is None and rate is None:
                raise InputError("fee_value_missing",
                                 "已知费用必须给 amount 或 rate；不能把未知"
                                 "费用当 0", where)
            if amount is not None and rate is not None:
                raise InputError("fee_value_conflict",
                                 "amount 与 rate 只能给一个", where)
            if basis == "percent_of_subtotal" and rate is None:
                raise InputError("fee_rate_required",
                                 "percent_of_subtotal 必须给 rate", where)
            if basis != "percent_of_subtotal" and amount is None:
                raise InputError("fee_amount_required",
                                 "该 basis 必须给 amount", where)
        tax_basis = parse_tax_basis(item.get("tax_basis"),
                                    where + ".tax_basis", required=False)
        waiver = item.get("waiver")
        if waiver is not None:
            waiver = _require_object(waiver, where + ".waiver")
            _check_keys(waiver, {"min_subtotal", "currency"},
                        where + ".waiver", prepared.findings)
            waiver = {
                "min_subtotal": parse_amount(waiver.get("min_subtotal"),
                                             where + ".waiver.min_subtotal"),
                "currency": parse_currency(waiver.get("currency"),
                                           where + ".waiver.currency"),
            }
            if waiver["currency"] != currency:
                raise InputError("fee_waiver_currency",
                                 "免运门槛币种必须与费用币种一致", where)
        captured = parse_rfc3339(item.get("captured_at"),
                                 where + ".captured_at", required=False)
        if captured is not None and captured > prepared.evaluation["as_of"]:
            raise InputError("future_timestamp", "费用来源时间晚于评估时刻",
                             where + ".captured_at")
        fees.append({
            "fee_id": fee_id,
            "kind": kind,
            "channel": channel,
            "currency": currency,
            "basis": basis,
            "tax_basis": tax_basis,
            "amount": amount,
            "rate": rate,
            "waiver": waiver,
            "source": safe_text(item.get("source"), where + ".source",
                                max_len=300),
            "captured_at": captured,
            "unknown": bool(unknown),
            "note": safe_text(item.get("note"), where + ".note",
                              required=False, max_len=300),
        })
    prepared.fees = fees


def _parse_fx(doc, prepared):
    raw = doc.get("fx_rates", [])
    if raw is None:
        raw = []
    _require_array(raw, "fx_rates", allow_empty=True)
    seen = {}
    rates = []
    for index, item in enumerate(raw):
        where = "fx_rates[%d]" % index
        item = _require_object(item, where)
        _check_keys(item, {"base", "quote", "rate", "source", "captured_at"},
                    where, prepared.findings)
        base = parse_currency(item.get("base"), where + ".base")
        quote = parse_currency(item.get("quote"), where + ".quote")
        if base == quote:
            raise InputError("invalid_fx_pair", "汇率两侧币种不能相同", where)
        rate = parse_fx_rate(item.get("rate"), where + ".rate")
        captured = parse_rfc3339(item.get("captured_at"),
                                 where + ".captured_at")
        if captured > prepared.evaluation["as_of"]:
            raise InputError("future_timestamp", "汇率时间晚于评估时刻",
                             where + ".captured_at")
        source = safe_text(item.get("source"), where + ".source",
                           max_len=300)
        key = (base, quote)
        if key in seen:
            previous = seen[key]
            if previous["captured_at"] == captured:
                raise InputError("duplicate_fx_rate",
                                 "同一币种对在同一时刻有多个汇率，无法确定"
                                 "使用哪个", where)
            if captured < previous["captured_at"]:
                prepared.findings.warning(
                    "older_fx_rate", where,
                    "较旧汇率被忽略：已有更新的 %s/%s 汇率"
                    % (base, quote))
                continue
        entry = {"base": base, "quote": quote, "rate": rate,
                 "source": source, "captured_at": captured}
        seen[key] = entry
        rates.append(entry)
    prepared.fx_rates = rates


def _parse_alternates(doc, prepared):
    raw = doc.get("alternates", [])
    if raw is None:
        raw = []
    _require_array(raw, "alternates", allow_empty=True)
    seen = set()
    for index, item in enumerate(raw):
        where = "alternates[%d]" % index
        item = _require_object(item, where)
        alt_id = safe_relative_name(item.get("alt_id"), where + ".alt_id")
        if alt_id in seen:
            raise InputError("duplicate_alternate_id",
                             "alt_id 重复：%s" % alt_id, where)
        seen.add(alt_id)
        line_id = safe_text(item.get("line_id"), where + ".line_id",
                            required=False, max_len=60)
        if line_id is not None and line_id not in {row["line_id"]
                                                   for row in prepared.rows}:
            raise InputError("unknown_alternate_line",
                             "alternate 引用了不存在的 line_id %s" % line_id,
                             where + ".line_id")
        for key in ("original", "candidate"):
            part = _require_object(item.get(key), where + "." + key)
            identity_text(part.get("mpn"), where + "." + key + ".mpn")
            identity_text(part.get("footprint"),
                          where + "." + key + ".footprint")
            identity_text(part.get("manufacturer"),
                          where + "." + key + ".manufacturer",
                          required=False)
        prepared.alternates.append(item)


def prepare(doc, as_of_override=None, csv_rows=None, csv_meta=None,
            source_label=None):
    """Validate and normalise one input document.

    Structural errors are recorded as blocking findings; a caller that cannot
    continue at all (for example unreadable JSON) raises ``InputError`` before
    this function is reached.
    """

    prepared = Prepared()
    prepared.raw = doc
    try:
        _parse_evaluation(doc, prepared, as_of_override)
        _parse_project(doc, prepared)
        _parse_policies(doc, prepared)
        _parse_demand(doc, prepared)
        _parse_snapshots(doc, prepared)
        _parse_rows(doc, prepared, cli_rows=csv_rows)
        _parse_offers(doc, prepared)
        _parse_fees(doc, prepared)
        _parse_fx(doc, prepared)
        _parse_alternates(doc, prepared)
    except InputError as exc:
        prepared.findings.extend([exc.as_finding()])
    prepared.csv = csv_meta
    prepared.source_label = source_label
    # BOM source hash: when a CSV was the source, the file hash is the source
    # identity; otherwise the canonical BOM rows are hashed.
    canonical_rows = prepared.rows if prepared.rows else []
    computed = None
    if csv_meta is not None:
        computed = csv_meta.get("sha256")
    else:
        from .util import canonical_sha256
        computed = canonical_sha256({
            "revision": prepared.project.get("bom_revision") if prepared.project
            else None,
            "rows": canonical_rows,
        })
    prepared.bom_computed_sha256 = computed
    declared = prepared.project.get("bom_source_sha256") if prepared.project \
        else None
    if declared and computed and declared != computed:
        prepared.findings.blocking(
            "bom_source_hash_mismatch", "project.bom_source_sha256",
            "声明的 BOM 源哈希 %s 与计算值 %s 不一致；来源版本对不上"
            % (declared, computed))
    for key in sorted(set(doc) - TOP_LEVEL_KEYS):
        prepared.findings.warning("unknown_input_key", key,
                                  "未知顶层字段不参与计算：%s" % key)
    from .util import canonical_sha256
    prepared.input_sha256 = canonical_sha256(doc)
    return prepared


def load_and_prepare(path, as_of_override=None):
    doc = load_json(path, MAX_JSON_BYTES)
    if doc.get("schema") != INPUT_SCHEMA:
        raise InputError(
            "invalid_schema",
            "schema 必须是 %r，实际 %r" % (INPUT_SCHEMA, doc.get("schema")))
    unknown = sorted(set(doc) - TOP_LEVEL_KEYS)
    prepared = prepare(doc, as_of_override=as_of_override,
                       source_label=str(path))
    for key in unknown:
        prepared.findings.warning("unknown_input_key", key,
                                  "未知顶层字段不参与计算：%s" % key)
    return prepared
