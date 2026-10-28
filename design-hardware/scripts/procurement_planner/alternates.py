"""Substitution candidate grading (passive and active families).

This module does NOT change the BOM.  It compares declared facts field by
field, requires a source per compared fact, and returns one of five statuses:

    exact_identity
    evidence_supported_candidate
    requires_design_review
    incompatible
    insufficient_evidence

Even when every known field is compatible, a candidate is never reported as a
"verified drop-in": complete pin/footprint/mode evidence only earns
``evidence_supported_candidate`` with ``drop_in_verified=false``.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

from . import ALTERNATES_SCHEMA
from .errors import Findings
from .util import normalize_identity, parse_text

STATUSES = ("exact_identity", "evidence_supported_candidate",
            "requires_design_review", "incompatible",
            "insufficient_evidence")

FAMILIES = ("passive", "active")

PASSIVE_REQUIRED_FACTS = (
    "component_kind",
    "value",
    "tolerance_percent",
    "voltage_rating_v",
    "package",
    "temperature_min_c",
    "temperature_max_c",
)

ACTIVE_REQUIRED_FACTS = (
    "component_kind",
    "function",
    "supply_min_v",
    "supply_max_v",
    "output_type",
    "pin_count",
    "package",
    "propagation_delay_ns",
    "temperature_min_c",
    "temperature_max_c",
)

SOURCE_KEYS = ("document", "revision", "page", "url")
EVIDENCE_KEYS = ("pin_map", "footprint", "mode")


def _num(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite number")
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            number = Decimal(value.strip())
        except InvalidOperation:
            raise ValueError("not a decimal: %r" % value)
        if not number.is_finite():
            raise ValueError("non-finite number")
        return number
    raise ValueError("unsupported number type")


def _require_source(source, field, source_id):
    """Validate one provenance record; return (ok, problem, normalized)."""

    if not isinstance(source, dict):
        return False, "缺少字段 %s 的来源记录" % field, None
    missing = [key for key in SOURCE_KEYS if not source.get(key)]
    if missing:
        return False, "字段 %s 来源缺少 %s" % (field, ",".join(missing)), None
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        return False, "字段 %s 来源 URL 不是 https" % field, None
    normalized = {
        "source_id": source_id,
        "field": field,
        "document": source.get("document"),
        "revision": source.get("revision"),
        "page": source.get("page"),
        "table": source.get("table"),
        "url": url,
        "condition": source.get("condition"),
        "accessed_at": source.get("accessed_at"),
        "verified": source.get("verified") is True,
    }
    return True, None, normalized


def _source_for(part, field, where, sources, alt_id, problems):
    source_map = part.get("sources")
    if not isinstance(source_map, dict):
        problems.append("%s 没有 sources 映射；字段 %s 无出处" % (where, field))
        return False, None
    raw = source_map.get(field)
    if raw is None:
        # A single default source may cover several fields only if it names
        # them explicitly; never infer provenance.
        problems.append("%s 字段 %s 缺少来源" % (where, field))
        return False, None
    ok, problem, normalized = _require_source(
        raw, field, "%s.%s.%s" % (alt_id, where, field))
    if not ok:
        problems.append(problem)
        return False, None
    sources.append(normalized)
    return True, normalized


class Grader:
    def __init__(self, alternate, findings=None):
        self.alt = alternate
        self.alt_id = alternate.get("alt_id")
        self.line_id = alternate.get("line_id")
        self.findings = findings or Findings()
        self.comparisons = []
        self.hard = []
        self.redesign = []
        self.missing = []
        self.sources = []
        self.notes = []
        self.original = alternate.get("original") or {}
        self.candidate = alternate.get("candidate") or {}
        self.application = alternate.get("application") or {}
        self.requirements = self.application.get("requirements") or {}
        self.evidence = alternate.get("evidence") or {}
        self.approval_scope = alternate.get("approval_scope")

    # -- comparison primitives -------------------------------------------
    def _compare_equal(self, field, requirement=None, hard=True,
                       label=None):
        original_value = self.original.get("facts", {}).get(field)
        candidate_value = self.candidate.get("facts", {}).get(field)
        required = requirement if requirement is not None else original_value
        if candidate_value is None:
            self.missing.append("候选缺少字段 %s" % field)
            self.comparisons.append({
                "field": field, "original": _stringify(original_value),
                "candidate": None, "requirement": _stringify(required),
                "verdict": "unknown", "note": "候选字段缺失",
            })
            return False
        original_ok, _ = _source_for(self.original, field, "original",
                                     self.sources, self.alt_id, self.missing)
        candidate_ok, _ = _source_for(self.candidate, field, "candidate",
                                      self.sources, self.alt_id, self.missing)
        same = _normalized_equal(candidate_value, required)
        verdict = "match" if same else ("mismatch" if hard else "difference")
        self.comparisons.append({
            "field": field, "original": _stringify(original_value),
            "candidate": _stringify(candidate_value),
            "requirement": _stringify(required),
            "verdict": verdict,
            "sources_complete": bool(original_ok and candidate_ok),
            "note": label or "",
        })
        if not same:
            (self.hard if hard else self.redesign).append(
                "%s 不满足：候选 %s，要求/原值 %s"
                % (label or field, _stringify(candidate_value),
                   _stringify(required)))
        return same

    def _compare_min(self, field, required_value=None, label=None):
        """Candidate numeric field must be >= required (rating-like)."""

        candidate_value = self.candidate.get("facts", {}).get(field)
        required = required_value
        if required is None:
            required = self.original.get("facts", {}).get(field)
        if candidate_value is None or required is None:
            missing = field + ("（候选）" if candidate_value is None
                               else "（要求）")
            self.missing.append("缺少字段 %s" % missing)
            self.comparisons.append({
                "field": field, "original": _stringify(
                    self.original.get("facts", {}).get(field)),
                "candidate": _stringify(candidate_value),
                "requirement": _stringify(required),
                "verdict": "unknown", "note": "字段或要求缺失",
            })
            return False
        try:
            cand = _num(candidate_value)
            req = _num(required)
        except ValueError:
            self.missing.append("字段 %s 不是可比较数值" % field)
            return False
        original_ok, _ = _source_for(self.original, field, "original",
                                     self.sources, self.alt_id, self.missing)
        candidate_ok, _ = _source_for(self.candidate, field, "candidate",
                                      self.sources, self.alt_id, self.missing)
        ok = cand >= req
        self.comparisons.append({
            "field": field,
            "original": _stringify(self.original.get("facts", {}).get(field)),
            "candidate": _stringify(candidate_value),
            "requirement": _stringify(required),
            "verdict": "match" if ok else "mismatch",
            "sources_complete": bool(original_ok and candidate_ok),
            "note": label or "候选值必须 >= 要求值",
        })
        if not ok:
            self.hard.append("%s 不足：候选 %s < 要求 %s"
                             % (label or field, cand, req))
        return ok

    def _compare_max(self, field, required_value=None, label=None):
        """Candidate numeric field must be <= limit (loss/tolerance-like)."""

        candidate_value = self.candidate.get("facts", {}).get(field)
        required = required_value
        if required is None:
            required = self.original.get("facts", {}).get(field)
        if candidate_value is None or required is None:
            self.missing.append("缺少字段 %s" % field)
            self.comparisons.append({
                "field": field, "original": _stringify(
                    self.original.get("facts", {}).get(field)),
                "candidate": _stringify(candidate_value),
                "requirement": _stringify(required),
                "verdict": "unknown", "note": "字段或要求缺失",
            })
            return False
        try:
            cand = _num(candidate_value)
            req = _num(required)
        except ValueError:
            self.missing.append("字段 %s 不是可比较数值" % field)
            return False
        original_ok, _ = _source_for(self.original, field, "original",
                                     self.sources, self.alt_id, self.missing)
        candidate_ok, _ = _source_for(self.candidate, field, "candidate",
                                      self.sources, self.alt_id, self.missing)
        ok = cand <= req
        self.comparisons.append({
            "field": field,
            "original": _stringify(self.original.get("facts", {}).get(field)),
            "candidate": _stringify(candidate_value),
            "requirement": _stringify(required),
            "verdict": "match" if ok else "mismatch",
            "sources_complete": bool(original_ok and candidate_ok),
            "note": label or "候选值必须 <= 要求值",
        })
        if not ok:
            self.hard.append("%s 超限：候选 %s > 允许 %s"
                             % (label or field, cand, req))
        return ok

    def _compare_temp(self):
        cand_min = self.candidate.get("facts", {}).get("temperature_min_c")
        cand_max = self.candidate.get("facts", {}).get("temperature_max_c")
        req_min = self.requirements.get(
            "temperature_min_c",
            self.original.get("facts", {}).get("temperature_min_c"))
        req_max = self.requirements.get(
            "temperature_max_c",
            self.original.get("facts", {}).get("temperature_max_c"))
        label = "工作温度范围"
        if None in (cand_min, cand_max, req_min, req_max):
            self.missing.append("工作温度范围字段缺失")
            self.comparisons.append({
                "field": "temperature_range", "original": [
                    _stringify(self.original.get("facts", {}).get(
                        "temperature_min_c")),
                    _stringify(self.original.get("facts", {}).get(
                        "temperature_max_c"))],
                "candidate": [_stringify(cand_min), _stringify(cand_max)],
                "requirement": [_stringify(req_min), _stringify(req_max)],
                "verdict": "unknown", "note": "温度字段缺失",
            })
            return False
        try:
            cmin, cmax = _num(cand_min), _num(cand_max)
            rmin, rmax = _num(req_min), _num(req_max)
        except ValueError:
            self.missing.append("工作温度范围不是可比较数值")
            return False
        for part, where in ((self.original, "original"),
                            (self.candidate, "candidate")):
            for field in ("temperature_min_c", "temperature_max_c"):
                _source_for(part, field, where, self.sources, self.alt_id,
                            self.missing)
        ok = cmin <= rmin and cmax >= rmax
        self.comparisons.append({
            "field": "temperature_range",
            "original": [_stringify(self.original.get("facts", {}).get(
                "temperature_min_c")),
                _stringify(self.original.get("facts", {}).get(
                    "temperature_max_c"))],
            "candidate": [_stringify(cand_min), _stringify(cand_max)],
            "requirement": [_stringify(req_min), _stringify(req_max)],
            "verdict": "match" if ok else "mismatch",
            "note": "候选温度范围必须覆盖要求范围",
        })
        if not ok:
            self.hard.append("工作温度范围不覆盖：候选 %s..%s，要求 %s..%s"
                             % (cmin, cmax, rmin, rmax))
        return ok

    def _compare_package(self):
        cand_pkg = self.candidate.get("footprint") or \
            self.candidate.get("facts", {}).get("package")
        req_pkg = self.original.get("footprint") or \
            self.original.get("facts", {}).get("package")
        if not cand_pkg or not req_pkg:
            self.missing.append("封装字段缺失")
            return False
        for part, where in ((self.original, "original"),
                            (self.candidate, "candidate")):
            _source_for(part, "footprint", where, self.sources, self.alt_id,
                        self.missing)
        same = normalize_identity(cand_pkg) == normalize_identity(req_pkg)
        self.comparisons.append({
            "field": "package",
            "original": _stringify(req_pkg),
            "candidate": _stringify(cand_pkg),
            "requirement": _stringify(req_pkg),
            "verdict": "match" if same else "difference",
            "note": "封装不同需要改 PCB/钢网，不是采购换料",
        })
        if not same:
            self.redesign.append("封装不同：%s -> %s"
                                 % (req_pkg, cand_pkg))
        return same

    def _check_evidence(self):
        missing = []
        family = self._family()
        needed = ["footprint"]
        if family == "active":
            needed = ["pin_map", "footprint", "mode"]
        for key in needed:
            item = self.evidence.get(key)
            if not isinstance(item, dict):
                missing.append("缺少 %s 证据" % key)
                continue
            source = item.get("source")
            if not isinstance(source, dict):
                missing.append("%s 证据缺少 source" % key)
        if missing:
            self.missing.extend(missing)
        return not missing

    def _compare_output_type(self, required_output):
        candidate_output = self.candidate.get("facts", {}).get("output_type")
        if not candidate_output:
            self.missing.append("候选缺少输出级类型 output_type")
            self.comparisons.append({
                "field": "output_type", "original": None, "candidate": None,
                "requirement": _stringify(required_output),
                "verdict": "unknown", "note": "输出级类型缺失",
            })
            return False
        for part, where in ((self.original, "original"),
                            (self.candidate, "candidate")):
            _source_for(part, "output_type", where, self.sources, self.alt_id,
                        self.missing)
        original_family = _output_family(required_output)
        candidate_family = _output_family(candidate_output)
        if original_family and candidate_family:
            ok = original_family == candidate_family
        else:
            ok = normalize_identity(str(required_output)) == normalize_identity(
                str(candidate_output))
        self.comparisons.append({
            "field": "output_type",
            "original": _stringify(required_output),
            "candidate": _stringify(candidate_output),
            "requirement": _stringify(required_output),
            "verdict": "match" if ok else ("mismatch" if original_family
                                           and candidate_family
                                           else "difference"),
            "note": "推挽与开漏是不同输出级，不能只按封装相同视为等价",
        })
        if not ok:
            self.hard.append("输出级类型不同：%s -> %s"
                             % (required_output, candidate_output))
        return ok

    def _family(self):
        family = (self.original.get("facts", {}).get("family")
                  or self.candidate.get("facts", {}).get("family"))
        if family in FAMILIES:
            return family
        kind = self.candidate.get("facts", {}).get("component_kind", "")
        if kind in ("capacitor", "resistor", "inductor"):
            return "passive"
        if kind:
            return "active"
        return None

    # -- family graders ---------------------------------------------------
    def _grade_passive(self):
        original = self.original.get("facts", {})
        candidate = self.candidate.get("facts", {})
        requirement = self.requirements
        ok = True
        self._compare_equal("component_kind", hard=True)
        kind = candidate.get("component_kind") or original.get(
            "component_kind")
        value_field = {"capacitor": "capacitance_f",
                       "resistor": "resistance_ohm",
                       "inductor": "inductance_h"}.get(kind)
        if value_field is None:
            self.missing.append("被动件类型无法确定（component_kind）")
            return False
        original_value = original.get(value_field)
        candidate_value = candidate.get(value_field)
        if candidate_value is None or original_value is None:
            self.missing.append("缺少标称值字段 %s" % value_field)
            ok = False
        else:
            for part, where in ((self.original, "original"),
                                (self.candidate, "candidate")):
                _source_for(part, value_field, where, self.sources,
                            self.alt_id, self.missing)
            try:
                same = _num(original_value) == _num(candidate_value)
            except ValueError:
                self.missing.append("标称值不是可比较数值")
                same = False
            self.comparisons.append({
                "field": value_field,
                "original": _stringify(original_value),
                "candidate": _stringify(candidate_value),
                "requirement": _stringify(original_value),
                "verdict": "match" if same else "mismatch",
                "note": "标称值必须相同；不同值是不同器件",
            })
            if not same:
                self.hard.append("标称值不同：%s vs %s"
                                 % (original_value, candidate_value))
                ok = False
        required_tol = requirement.get("tolerance_percent",
                                       original.get("tolerance_percent"))
        candidate_tol = candidate.get("tolerance_percent")
        if candidate_tol is None or required_tol is None:
            self.missing.append("缺少容差字段")
            ok = False
        else:
            for part, where in ((self.original, "original"),
                                (self.candidate, "candidate")):
                _source_for(part, "tolerance_percent", where, self.sources,
                            self.alt_id, self.missing)
            try:
                ok = ok and _num(candidate_tol) <= _num(required_tol)
            except ValueError:
                self.missing.append("容差不是可比较数值")
                ok = False
            self.comparisons.append({
                "field": "tolerance_percent",
                "original": _stringify(original.get("tolerance_percent")),
                "candidate": _stringify(candidate_tol),
                "requirement": _stringify(required_tol),
                "verdict": ("match" if _num(candidate_tol)
                            <= _num(required_tol) else "mismatch")
                if _isnum(candidate_tol) and _isnum(required_tol)
                else "unknown",
                "note": "候选容差必须不宽于要求",
            })
            if _isnum(candidate_tol) and _isnum(required_tol) \
                    and _num(candidate_tol) > _num(required_tol):
                self.hard.append("容差更宽：候选 %s%% > 要求 %s%%"
                                 % (candidate_tol, required_tol))
        required_voltage = requirement.get(
            "voltage_rating_v", original.get("voltage_rating_v"))
        if required_voltage is None:
            self.missing.append("缺少耐压要求")
            ok = False
        else:
            ok = self._compare_min("voltage_rating_v", required_voltage,
                                   "额定电压") and ok
        if original.get("power_rating_w") is not None:
            ok = self._compare_min("power_rating_w", None, "额定功率") and ok
        ok = self._compare_package() and ok
        ok = self._compare_temp() and ok
        dielectric_original = original.get("dielectric")
        dielectric_candidate = candidate.get("dielectric")
        if requirement.get("dielectric") is not None:
            for part, where in ((self.original, "original"),
                                (self.candidate, "candidate")):
                _source_for(part, "dielectric", where, self.sources,
                            self.alt_id, self.missing)
            if dielectric_candidate is None:
                self.missing.append("缺少介质字段 dielectric")
                ok = False
            elif normalize_identity(dielectric_candidate) != normalize_identity(
                    requirement["dielectric"]):
                self.hard.append("介质不满足：候选 %s，要求 %s"
                                 % (dielectric_candidate,
                                    requirement["dielectric"]))
                ok = False
        elif dielectric_original and dielectric_candidate:
            if normalize_identity(dielectric_original) != normalize_identity(
                    dielectric_candidate):
                self.redesign.append(
                    "介质不同（%s -> %s）；偏压/温度特性不能只凭额定值推断"
                    % (dielectric_original, dielectric_candidate))
        elif dielectric_original and dielectric_candidate is None:
            self.missing.append("候选介质字段 dielectric 缺失")
        if requirement.get("esr_max_ohm") is not None:
            ok = self._compare_max("esr_max_ohm",
                                   requirement.get("esr_max_ohm"),
                                   "ESR") and ok
        if requirement.get("frequency_hz") is not None:
            ok = self._compare_min("frequency_limit_hz",
                                   requirement.get("frequency_hz"),
                                   "适用频率") and ok
        return ok

    def _grade_active(self):
        ok = True
        self._compare_equal("component_kind", hard=True)
        self._compare_equal("function", hard=True)
        requirement = self.requirements
        candidate = self.candidate.get("facts", {})
        original = self.original.get("facts", {})
        if requirement.get("topology") is not None:
            ok = self._compare_equal("topology",
                                     requirement.get("topology"),
                                     hard=True) and ok
        required_output = requirement.get("output_type",
                                          original.get("output_type"))
        if required_output is not None:
            ok = self._compare_output_type(required_output) and ok
        supply = requirement.get("supply_voltage_v")
        if supply is None:
            self.missing.append("缺少应用供电电压 supply_voltage_v")
            ok = False
        else:
            cand_min = candidate.get("supply_min_v")
            cand_max = candidate.get("supply_max_v")
            if cand_min is None or cand_max is None:
                self.missing.append("缺少供电范围字段")
                ok = False
            else:
                for field in ("supply_min_v", "supply_max_v"):
                    _source_for(self.candidate, field, "candidate",
                                self.sources, self.alt_id, self.missing)
                try:
                    in_range = _num(cand_min) <= _num(supply) <= _num(cand_max)
                except ValueError:
                    self.missing.append("供电范围不是可比较数值")
                    in_range = False
                    ok = False
                self.comparisons.append({
                    "field": "supply_range",
                    "original": [_stringify(original.get("supply_min_v")),
                                 _stringify(original.get("supply_max_v"))],
                    "candidate": [_stringify(cand_min),
                                  _stringify(cand_max)],
                    "requirement": _stringify(supply),
                    "verdict": "match" if in_range else "mismatch",
                    "note": "应用供电电压必须落在候选工作范围内",
                })
                if not in_range:
                    self.hard.append("供电范围不覆盖应用电压 %s V" % supply)
                    ok = False
        ok = self._compare_temp() and ok
        ok = self._compare_package() and ok
        cand_pins = candidate.get("pin_count")
        orig_pins = original.get("pin_count")
        if cand_pins is None or orig_pins is None:
            self.missing.append("缺少引脚数字段 pin_count")
            ok = False
        else:
            for part, where in ((self.original, "original"),
                                (self.candidate, "candidate")):
                _source_for(part, "pin_count", where, self.sources,
                            self.alt_id, self.missing)
            if int(cand_pins) != int(orig_pins):
                self.redesign.append("引脚数不同：%s -> %s；必须改封装/PCB"
                                     % (orig_pins, cand_pins))
                self.comparisons.append({
                    "field": "pin_count",
                    "original": _stringify(orig_pins),
                    "candidate": _stringify(cand_pins),
                    "requirement": _stringify(orig_pins),
                    "verdict": "difference",
                    "note": "引脚数不同需要重新设计封装/PCB",
                })
                ok = False
            else:
                self.comparisons.append({
                    "field": "pin_count",
                    "original": _stringify(orig_pins),
                    "candidate": _stringify(cand_pins),
                    "requirement": _stringify(orig_pins),
                    "verdict": "match", "note": "引脚数相同",
                })
        pinout_candidate = candidate.get("pinout")
        pinout_original = original.get("pinout")
        if requirement.get("pinout_equivalence_required", True):
            if not pinout_candidate or not pinout_original:
                self.missing.append("缺少 pinout 逐脚定义")
                ok = False
            else:
                same = _pinout_equal(pinout_original, pinout_candidate)
                self.comparisons.append({
                    "field": "pinout",
                    "original": _compact_pinout(pinout_original),
                    "candidate": _compact_pinout(pinout_candidate),
                    "requirement": "逐脚同名同号",
                    "verdict": "match" if same else "difference",
                    "note": "pinout 不同不能按采购换料处理",
                })
                if not same:
                    self.redesign.append("pinout 定义不同；需要改原理图/PCB")
                    ok = False
                for part, where in ((self.original, "original"),
                                    (self.candidate, "candidate")):
                    _source_for(part, "pinout", where, self.sources,
                                self.alt_id, self.missing)
        for field, mode, label in (
                ("propagation_delay_ns", "max", "传播延迟"),
                ("input_offset_mv", "max", "输入失调"),
                ("supply_current_ua", "max", "静态电流"),
                ("drive_current_ma", "min", "驱动电流")):
            if requirement.get(field) is not None:
                if mode == "max":
                    ok = self._compare_max(field, requirement.get(field),
                                           label) and ok
                else:
                    ok = self._compare_min(field, requirement.get(field),
                                           label) and ok
        required_external = requirement.get("external_networks")
        if required_external is not None:
            candidate_external = candidate.get("external_networks")
            if candidate_external is None:
                self.missing.append("缺少外部网络要求 external_networks")
                ok = False
            else:
                same = set(map(str, required_external)) == set(
                    map(str, candidate_external))
                self.comparisons.append({
                    "field": "external_networks",
                    "original": original.get("external_networks"),
                    "candidate": candidate_external,
                    "requirement": required_external,
                    "verdict": "match" if same else "difference",
                    "note": "外部网络需求不同需要设计复核",
                })
                if not same:
                    self.redesign.append("外部网络需求不同；需要设计复核/改板")
                    ok = False
        return ok

    # -- entry ------------------------------------------------------------
    def grade(self):
        family = self._family()
        original_mpn = self.original.get("mpn")
        candidate_mpn = self.candidate.get("mpn")
        original_mfr = self.original.get("manufacturer")
        candidate_mfr = self.candidate.get("manufacturer")
        same_identity = (
            normalize_identity(original_mpn) == normalize_identity(
                candidate_mpn)
            and normalize_identity(original_mfr) == normalize_identity(
                candidate_mfr) if original_mfr and candidate_mfr else False)
        if family is None:
            status = "insufficient_evidence"
            self.missing.append("无法判断器件族（passive/active）")
        elif same_identity:
            status = "exact_identity"
            self.notes.append(
                "候选与原始 MPN/制造商完全相同；这是同一器件，不是替代料")
        else:
            if normalize_identity(original_mpn) == normalize_identity(
                    candidate_mpn) and original_mfr and candidate_mfr \
                    and normalize_identity(original_mfr) != normalize_identity(
                        candidate_mfr):
                self.redesign.append(
                    "MPN 相同但制造商不同；同一料号跨厂不能直接当同一器件")
            if family == "passive":
                self._grade_passive()
            else:
                self._grade_active()
            evidence_ok = self._check_evidence()
            if self.hard:
                status = "incompatible"
            elif family == "active":
                # H4: missing active-device fields/evidence must surface as a
                # design-review item, not as "looks equivalent".
                if self.missing or self.redesign or not evidence_ok:
                    status = "requires_design_review"
                elif not self.comparisons:
                    status = "insufficient_evidence"
                else:
                    status = "evidence_supported_candidate"
            elif self.missing:
                status = "insufficient_evidence"
            elif self.redesign or not evidence_ok:
                status = "requires_design_review"
            else:
                status = "evidence_supported_candidate"
        # A required-field gap always wins over a soft candidate label.
        if status in ("evidence_supported_candidate",) and self.missing:
            status = "insufficient_evidence"
        if status == "exact_identity" and self.hard:
            status = "incompatible"
        result = {
            "schema": ALTERNATES_SCHEMA,
            "alt_id": self.alt_id,
            "line_id": self.line_id,
            "family": family,
            "original_mpn": original_mpn,
            "original_manufacturer": original_mfr,
            "candidate_mpn": candidate_mpn,
            "candidate_manufacturer": candidate_mfr,
            "status": status,
            "drop_in_verified": False,
            "approval_scope": self.approval_scope,
            "comparisons": self.comparisons,
            "hard_violations": self.hard,
            "redesign_required": self.redesign,
            "missing_evidence": self.missing,
            "sources": self.sources,
            "notes": self.notes,
            "limits": [
                "候选分级只基于输入声明的字段与来源，不是实物/EDA/PCB 验证",
                "即使全部已知字段相容也不代表可直接替换；"
                "drop_in_verified 永远为 false",
                "替代不自动改写 BOM/工程；批准范围由 approval_scope 记录",
            ],
        }
        return result


def _isnum(value):
    try:
        _num(value)
        return True
    except ValueError:
        return False


def _stringify(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _normalized_equal(left, right):
    if left is None or right is None:
        return False
    if isinstance(left, (int, float, Decimal)) or isinstance(
            right, (int, float, Decimal)):
        try:
            return _num(left) == _num(right)
        except ValueError:
            return False
    return normalize_identity(str(left)) == normalize_identity(str(right))


def _output_family(value):
    """Map common output-stage wording to a comparable family.

    Only explicit push-pull / open-drain families are hard compared; an
    unrecognised phrase stays a review item rather than a hard failure.
    """

    text = normalize_identity(str(value or ""))
    text = text.replace("-", "_").replace("/", "_").replace(" ", "_")
    if not text:
        return None
    if "OPEN" in text and ("DRAIN" in text or "COLLECTOR" in text):
        return "open_drain"
    if "PUSH" in text and "PULL" in text:
        return "push_pull"
    if "CMOS" in text and "TTL" in text:
        return "push_pull"
    if "RAIL" in text and "RAIL" in text:
        return "push_pull"
    return None


def _pinout_equal(left, right):
    def normalize(pin):
        if isinstance(pin, dict):
            return (str(pin.get("number", "")).strip(),
                    str(pin.get("name", "")).strip().upper())
        if isinstance(pin, (list, tuple)) and len(pin) == 2:
            return (str(pin[0]).strip(), str(pin[1]).strip().upper())
        return (str(pin).strip().upper(), "")

    try:
        return [normalize(pin) for pin in left] == [
            normalize(pin) for pin in right]
    except (TypeError, AttributeError):
        return False


def _compact_pinout(pinout):
    if not isinstance(pinout, list):
        return pinout
    result = []
    for pin in pinout:
        if isinstance(pin, dict):
            result.append("%s:%s" % (pin.get("number"), pin.get("name")))
        elif isinstance(pin, (list, tuple)) and len(pin) == 2:
            result.append("%s:%s" % (pin[0], pin[1]))
        else:
            result.append(str(pin))
    return result


def grade_all(prepared):
    gradings = []
    findings = Findings()
    for alternate in prepared.alternates:
        try:
            grader = Grader(alternate, findings)
            gradings.append(grader.grade())
        except (KeyError, TypeError, ValueError) as exc:
            gradings.append({
                "schema": ALTERNATES_SCHEMA,
                "alt_id": alternate.get("alt_id"),
                "line_id": alternate.get("line_id"),
                "family": None,
                "original_mpn": (alternate.get("original") or {}).get("mpn"),
                "candidate_mpn": (alternate.get("candidate") or {}).get("mpn"),
                "status": "insufficient_evidence",
                "drop_in_verified": False,
                "comparisons": [],
                "hard_violations": [],
                "redesign_required": [],
                "missing_evidence": ["alternate 数据无法解析：%s" % exc],
                "sources": [],
                "notes": [],
                "limits": ["输入字段不足，未做任何等价性声明"],
            })
    return gradings, findings


def grading_by_alt(gradings):
    return {item["alt_id"]: item for item in gradings}


def alternate_offer_grades(prepared, gradings):
    """Map candidate MPN+footprint -> best allowed grade for substitution."""

    result = {}
    for alternate, grading in zip(prepared.alternates, gradings):
        candidate = alternate.get("candidate") or {}
        key = (normalize_identity(candidate.get("mpn")),
               normalize_identity(candidate.get("footprint")))
        result.setdefault(key, []).append(grading)
    return result
