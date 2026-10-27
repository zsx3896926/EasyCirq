"""Deterministic finding/report construction and overall status semantics."""
from . import SCHEMA_REPORT, TOOL_NAME, TOOL_VERSION

RULES = (
    ("R1", "Flying/coupling capacitor endpoints",
     "capacitors with an evidenced flying/coupling role"),
    ("R2", "Capacitor voltage rating vs stress",
     "capacitors with an evidenced rated voltage"),
    ("R3", "Tactile-switch internal groups and switching",
     "switches with a declared switching requirement and internal-structure fact"),
    ("R4", "Special pin capability and supply domain",
     "components with declared pin roles or supplies and a matching device fact"),
    ("R5", "Exposed/merged pads and one-to-many pin mapping",
     "components with a pad-map device fact"),
    ("R6", "Capacitor role and local placement",
     "capacitors with a declared role and an explicit project distance constraint"),
)
RULE_TITLES = {rule_id: title for rule_id, title, _scope in RULES}
RULE_SCOPES = {rule_id: scope for rule_id, _title, scope in RULES}

OUTCOMES = ("satisfied", "violated", "insufficient", "not_applicable",
            "invalid_input")
GLOBAL_NOT_CHECKED = [
    "live EDA / native DRC / simulation / saved-reopen acceptance",
    "analogue waveforms, transients, switching-node AC stress and negative rails "
    "(R2 only uses declared stress or a provable DC interval)",
    "high-frequency return path, loop inductance, ESL and EMI (R6 only measures "
    "a Euclidean distance proxy, not the real loop)",
    "copper/track/pour connectivity and current density",
    "full-project page completeness, cross-sheet aliasing not supplied as evidence",
    "thermal, safety, EMC, firmware, manufacturing and powered functional test",
    "device datasheets not supplied in device_facts; no fact is guessed from a "
    "part number or symbol",
]


class RuleResult:
    def __init__(self, rule_id):
        self.rule_id = rule_id
        self.title = RULE_TITLES[rule_id]
        self.scope = RULE_SCOPES[rule_id]
        self.counts = {"checked": 0, "satisfied": 0, "violations": 0,
                       "unknown": 0, "not_applicable": 0, "invalid_input": 0}
        self.findings = []
        self.satisfied = []
        self.notes = []
        self.incomplete = False
        self._ids = set()

    def note(self, message):
        self.notes.append(message)

    def mark_incomplete(self, message):
        self.incomplete = True
        self.note(message)

    def _identifier(self, code, subjects):
        parts = [self.rule_id, code or "check"]
        for key in ("components", "pins", "nets"):
            parts.extend(str(item) for item in subjects.get(key, []))
        base = ":".join(parts)
        candidate = base
        index = 2
        while candidate in self._ids:
            candidate = "%s:%d" % (base, index)
            index += 1
        self._ids.add(candidate)
        return candidate

    def _subject_block(self, subjects):
        return {
            "components": sorted(subjects.get("components", [])),
            "pins": sorted(subjects.get("pins", [])),
            "nets": sorted(subjects.get("nets", [])),
        }

    def _finding(self, code, outcome, severity, certainty, subjects, actual,
                 constraint, unit, evidence, explanation, recommendation,
                 unverified):
        return {
            "finding_id": self._identifier(code, subjects),
            "rule_id": self.rule_id,
            "code": code,
            "state": outcome,
            "severity": severity,
            "certainty": certainty,
            "subjects": self._subject_block(subjects),
            "actual": actual,
            "constraint": constraint,
            "unit": unit,
            "evidence": evidence or [],
            "explanation": explanation,
            "recommendation": recommendation,
            "unverified": list(unverified or []),
        }

    def satisfied_check(self, subjects, constraint=None, evidence=None,
                        explanation="", certainty="proven"):
        """Record a proven-satisfied check without emitting a finding."""
        self.counts["checked"] += 1
        self.counts["satisfied"] += 1
        self.satisfied.append({
            "rule_id": self.rule_id,
            "subjects": self._subject_block(subjects),
            "constraint": constraint,
            "certainty": certainty,
            "evidence": evidence or [],
            "explanation": explanation,
        })

    def not_applicable(self, subjects, reason):
        self.counts["not_applicable"] += 1
        self.findings.append(self._finding(
            "not_applicable", "not_applicable", "info", "proven",
            subjects, None, None, None, [], reason,
            "若该对象确应受本规则约束，请补充角色/资料证据。", []))

    def insufficient(self, code, subjects, actual=None, constraint=None,
                     unit=None, evidence=None, explanation="",
                     recommendation="", unverified=None):
        self.counts["checked"] += 1
        self.counts["unknown"] += 1
        self.findings.append(self._finding(
            code, "insufficient", "review", "unverified", subjects, actual,
            constraint, unit, evidence, explanation, recommendation,
            unverified or ["insufficient evidence to prove or disprove the rule"]))

    def violated(self, code, subjects, actual, constraint, unit, evidence,
                 explanation, recommendation, severity="hard",
                 certainty="proven", unverified=None):
        self.counts["checked"] += 1
        self.counts["violations"] += 1
        self.findings.append(self._finding(
            code, "violated", severity, certainty, subjects, actual, constraint,
            unit, evidence, explanation, recommendation, unverified or []))

    def invalid(self, code, subjects, explanation):
        self.counts["invalid_input"] += 1
        self.findings.append(self._finding(
            "invalid_input:" + code, "invalid_input", "hard", "proven", subjects,
            None, None, None, [], explanation,
            "修正输入数据后重新运行；不得沿用旧 PASS 报告。", []))


def rule_status(rule):
    if rule.counts["invalid_input"]:
        return "invalid_input"
    if rule.counts["violations"]:
        return "violated"
    if rule.counts["unknown"]:
        return "review_required"
    if rule.incomplete:
        return "incomplete"
    if rule.counts["checked"]:
        return "satisfied"
    return "not_applicable"


def overall_status(results, meta):
    all_findings = [finding for rule in results for finding in rule.findings]
    if any(finding["state"] == "invalid_input" for finding in all_findings):
        return "invalid_input", "输入不合法；未执行或未完成审查，不能产生 PASS。"
    if any(finding["state"] == "violated" and finding["severity"] == "hard"
           for finding in all_findings):
        return "fail", "存在已证明的硬性电气意图违反。"
    if any(finding["state"] == "insufficient" for finding in all_findings) or \
            any(finding["state"] == "violated" for finding in all_findings):
        return "review_required", "无硬性违反，但存在证据不足或项目策略项需要审查。"
    if not meta.get("intent_supplied"):
        return "incomplete", "未提供 intent（用户/原厂声明）输入，无法形成有范围的通过结论。"
    total_checked = sum(rule.counts["checked"] for rule in results)
    if total_checked == 0:
        return "incomplete", "输入中没有可被本模块审查的对象或声明。"
    if any(rule.incomplete for rule in results):
        return "incomplete", "部分规则因缺少整段输入而未评估。"
    return "pass_with_scope", "所列规则在给定输入范围内均被证明满足，且无未验证项。"


def build_report(data, results, input_meta, *, coverage_extra=None,
                 assumptions=None):
    status, reason = overall_status(results, input_meta)
    totals = {key: 0 for key in ("checked", "satisfied", "violations",
                                 "unknown", "not_applicable",
                                 "invalid_input")}
    rule_summary = {}
    for rule in results:
        for key in totals:
            totals[key] += rule.counts[key]
        rule_summary[rule.rule_id] = {
            "status": rule_status(rule),
            "title": rule.title,
            "scope": rule.scope,
            **rule.counts,
            "notes": rule.notes,
        }
    findings = [finding for rule in results for finding in rule.findings]
    findings.sort(key=lambda item: (item["rule_id"], item["finding_id"]))
    satisfied = [item for rule in results for item in rule.satisfied]
    satisfied.sort(key=lambda item: (item["rule_id"],
                                     item["subjects"]["components"],
                                     item["subjects"]["pins"]))
    coverage = {
        "input_sections": {
            "design": True,
            "components": len(data["components"]),
            "pins": sum(len(item["pins"]) for item in data["components"]),
            "intent": bool(input_meta.get("intent_supplied")),
            "device_facts": len(data.get("device_facts", [])),
            "operating_conditions": bool(data.get("operating_conditions")),
            "evidence": len(data.get("evidence", [])),
            "measurement_available": bool(
                data["_meta"].get("measurement", {}).get("available")),
        },
        "rules_evaluated": [rule.rule_id for rule in results
                            if rule.counts["checked"]],
        "rules_not_applicable": [rule.rule_id for rule in results
                                 if not rule.counts["checked"]],
        "geometry": "euclidean_proxy_only",
        "datasheet_facts": sorted({
            item["id"] for item in
            [evidence for finding in findings for evidence in
             finding.get("evidence", [])] +
            [evidence for check in satisfied for evidence in
             check.get("evidence", [])]
            if item.get("kind") == "vendor_datasheet" and item.get("id")
        }),
        "not_checked": list(GLOBAL_NOT_CHECKED),
    }
    if coverage_extra:
        coverage.update(coverage_extra)
    report = {
        "schema": SCHEMA_REPORT,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION,
                 "min_python": "3.10", "deterministic": True},
        "status": status,
        "status_reason": reason,
        "input": input_meta,
        "summary": {"rules": rule_summary, "totals": totals,
                    "finding_count": len(findings)},
        "rule_results": [
            {"rule_id": rule.rule_id, "title": rule.title, "scope": rule.scope,
             "status": rule_status(rule), "counts": dict(rule.counts),
             "notes": list(rule.notes), "incomplete": rule.incomplete}
            for rule in results
        ],
        "findings": findings,
        "satisfied": satisfied,
        "coverage": coverage,
        "assumptions": list(assumptions or []),
        "not_checked": list(GLOBAL_NOT_CHECKED),
        "scope_note": "pass_with_scope 只证明所列规则和给定输入覆盖范围；"
                      "不表示整机电气、PCB、制造或上电正确。",
    }
    return report


def make_results():
    return [RuleResult(rule_id) for rule_id, _title, _scope in RULES]
