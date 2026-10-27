"""D2: rule extraction, evidence verification, candidate tensions and fixtures.

Only reviewed catalog relations may be called conflicts; deterministic text
features produce candidates, never confirmed conflicts.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import CATALOG_VERSION, NOT_PROOF, SCHEMA
from .common import (
    AuditError, base_result, git_sha_for, stable_digest, utc_now,
)
from .scan import scan_root

RULES_SCHEMA = "ska-rules/v1"
FIXTURE_SCHEMA = "ska-rule-fixtures/v1"
CLASSIFICATIONS = {
    "true_conflict", "default_with_exception", "different_stage",
    "different_scope", "stale_reference", "ambiguity", "user_authorized",
    "technical_limit", "negation", "code_example", "coexist",
}
STRENGTH_RE = re.compile(
    r"(必须|不得|禁止|务必|严禁|一律|始终|只有|仅当|必须|应|应当|建议|优先|"
    r"可以|可|默认|不要|无需|不得|不能|must|should|never|always|only|may)")
CONDITION_RE = re.compile(
    r"(?:当|如果|若|除非|只有|仅当|在)([^，。；;\n]{2,60}?)(?:时|情况下|条件下|才)")
EN_CONDITION_RE = re.compile(
    r"\b(?:when|if|unless|only when)\b([^.;\n]{2,80})", re.IGNORECASE)
SCOPE_TERMS = {
    "schematic": ("原理图", "schematic", "图面", "symbol", "符号"),
    "pcb": ("pcb", "布局", "布线", "走线", "板框", "铜", "layer", "层叠"),
    "manufacturing": ("制造", "交付", "贴片", "smt", "打样", "gerber", "bom"),
    "sourcing": ("商城", "配单", "采购", "选型", "lcsc", "库存", "价格"),
    "review": ("评审", "review", "检查", "审查"),
    "gate": ("门禁", "gate", "g0", "g1", "g2", "g3", "g4", "g5", "g6",
             "阶段退出", "退出证据"),
    "installation": ("安装", "升级", "更新", "update", "install", "版本"),
    "execution": ("执行", "写入", "回读", "保存", "重开", "drc", "dump"),
    "product": ("完整产品", "整机", "产品", "idea", "设备"),
    "offline": ("离线", "无eda", "无 eda", "not run", "offline"),
    "analysis": ("分析", "资料", "方案评估", "离线"),
}
ACTION_FAMILIES = {
    "approval": ("签批", "等待用户", "等确认", "等批准", "用户确认", "逐项确认",
                 "等待用户确认", "check in", "sign off", "approve"),
    "autonomy": ("自主", "直接执行", "继续推进", "无需确认", "不逐阶段",
                 "不新增等待", "proceed", "without asking", "autonomous"),
    "full_load": ("全部", "一次性加载", "完整读取", "全量", "read all"),
    "on_demand": ("按需", "按任务", "仅读", "只读", "when needed", "on demand"),
    "direct_wire": ("直接画线", "直接连线", "可追踪导线", "实体直连", "直连"),
    "label": ("标签", "端口", "net label", "网络名"),
    "strict": ("blocked", "不得", "禁止", "必须", "fail closed", "block"),
    "lenient": ("可以", "允许", "放行", "通过", "optional", "allow"),
    "user": ("用户明确", "用户说", "用户要求", "已授权", "用户只需说",
             "客户已要求", "user asked", "per user"),
    "technical": ("没有 cli", "无 cli", "不支持", "只能由用户", "beta",
                  "未包装", "not supported", "gui 导出", "没有 typed action"),
    "stale": ("已废弃", "废弃", "历史阈值", "旧版", "deprecated", "legacy",
              "outdated", "旧命令"),
    "code": ("python ", "python3 ", " --", "`--"),
    "evidence": ("证据", "blocked", "pass", "not run", "warn", "advisory",
                 "缺证据"),
    "local": ("局部", "就近", "local"),
    "cross": ("跨区", "跨页", "长距离", "cross"),
}


def _normalise(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _hits(text, family):
    lower = _normalise(text).lower()
    return [term for term in ACTION_FAMILIES[family] if term in lower]


def _scope_set(text):
    lower = _normalise(text).lower()
    found = set()
    for scope, terms in SCOPE_TERMS.items():
        for term in terms:
            start = 0
            while True:
                index = lower.find(term, start)
                if index < 0:
                    break
                prefix = lower[max(0, index - 15):index]
                negated = any(marker in prefix for marker in (
                    "无需", "不用", "不必", "不得", "禁止", "不再", "未"))
                if not negated:
                    found.add(scope)
                    break
                start = index + len(term)
    if "完整产品" in lower or "整机" in lower:
        found.add("whole_product")
    if "只要求" in lower or "局部任务" in lower or "仍按该范围" in lower:
        found.add("local_scope")
    return found


def _stage_set(text):
    lower = _normalise(text).lower()
    stages = set()
    if any(word in lower for word in ("布局冻结后", "冻结后", "重开 g3")):
        stages.add("layout_frozen")
    if any(word in lower for word in ("检查点", "评审", "复核", "汇报", "确认")):
        stages.add("review")
    if any(word in lower for word in ("方案", "concept")):
        stages.add("concept")
    if any(word in lower for word in ("原理图", "schematic")):
        stages.add("schematic")
    if any(word in lower for word in ("布局", "放件", "placement")):
        stages.add("layout")
    if any(word in lower for word in ("布线", "走线", "route")):
        stages.add("route")
    if any(word in lower for word in ("交付", "制造", "打样")):
        stages.add("delivery")
    if any(word in lower for word in ("开工", "开始前", "启动")):
        stages.add("startup")
    return stages


def _has_strong_exception(text):
    lower = _normalise(text).lower()
    return any(marker in lower for marker in (
        "仅当", "除非", "例外", "only when", "unless",
        "难以直连时", "只有用户明确", "只有用户要求",
    ))


def _has_negation(text):
    return bool(re.search(r"(不要|不得|禁止|无需|不必|不需要|不是)", _normalise(text)))


def _classification(a_text, b_text):
    a = _normalise(a_text)
    b = _normalise(b_text)
    al, bl = a.lower(), b.lower()

    # 1. code example: a command block is not a rule statement
    if (_hits(a, "code") and a.startswith(("python", "`python"))) or \
            (_hits(b, "code") and b.startswith(("python", "`python"))):
        return "code_example"

    # 2. negation over a shared review-checkpoint noun
    negative_checkpoint = re.search(
        r"不要[^。；\n]{0,30}(检查点|权限停顿)", b) or re.search(
        r"不要[^。；\n]{0,30}(检查点|权限停顿)", a)
    if negative_checkpoint and "检查点" in a and "检查点" in b:
        return "negation"

    # 3. stale/deprecated reference used as authority
    if (_hits(a, "stale") or _hits(b, "stale")) and any(
            word in (a + b).lower() for word in ("依据", "授权", "放行", "通过")):
        return "stale_reference"

    # 4. external tool capability limit vs method preference
    if _hits(a, "technical") or _hits(b, "technical"):
        return "technical_limit"

    # 5. disjoint task scope (before stage: disjoint scope is stronger)
    a_scope, b_scope = _scope_set(a), _scope_set(b)
    if ("whole_product" in a_scope and "local_scope" in b_scope) or \
            ("whole_product" in b_scope and "local_scope" in a_scope):
        return "different_scope"
    if a_scope and b_scope and not (a_scope & b_scope):
        return "different_scope"

    # 6. stage differs, including the freeze/change-order case
    a_stage, b_stage = _stage_set(a), _stage_set(b)
    if ("layout_frozen" in a_stage) != ("layout_frozen" in b_stage):
        return "different_stage"
    if a_stage and b_stage and not (a_stage & b_stage):
        return "different_stage"

    # 7. same rule expressed twice (direct wire + cross-zone label) -> coexist
    if _hits(a, "direct_wire") and _hits(b, "direct_wire") and \
            _hits(a, "cross") and _hits(b, "cross"):
        return "coexist"

    # 8. direct negation of a shared multi-character requirement -> conflict
    for phrase in ("逐项签批", "每道门禁", "全量预载"):
        if phrase in a and phrase in b and _has_negation(b):
            return "true_conflict"

    # 9. exception covering the other side's default
    if _has_strong_exception(b) and not _has_strong_exception(a):
        return "default_with_exception"
    if _has_strong_exception(a) and not _has_strong_exception(b):
        return "default_with_exception"

    # 10. both sides are user-authorised variants
    if _hits(a, "user") and _hits(b, "user"):
        return "user_authorized"

    # 11. undefined mapping between a default route and an exception route
    if "不是所有" in b and "用户明确" in b and "默认" in a:
        return "ambiguity"
    if "不是所有" in a and "用户明确" in a and "默认" in b:
        return "ambiguity"

    # 12. everything else is a coexistence candidate, not a conflict
    return "coexist"


def load_rules_catalog(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"cannot read rules catalog {path}: {exc}")
    if not isinstance(data, dict) or data.get("schema") != RULES_SCHEMA:
        raise AuditError(f"rules catalog must have schema {RULES_SCHEMA}")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise AuditError("rules catalog must contain a non-empty rules list")
    seen = set()
    for rule in rules:
        rule_id = rule.get("rule_id")
        if not rule_id or rule_id in seen:
            raise AuditError(f"duplicate or empty rule_id: {rule_id}")
        seen.add(rule_id)
        for key in ("text", "source", "condition", "task_scope", "action",
                    "strength", "exception", "evidence_required",
                    "priority_declared", "version_applicability", "provenance"):
            if key not in rule:
                raise AuditError(f"rule {rule_id}: missing {key}")
        if rule["provenance"] not in (
                "machine_extracted", "maintainer_declared", "inferred"):
            raise AuditError(f"rule {rule_id}: invalid provenance")
    for relation in data.get("relations", []):
        if relation.get("classification") not in CLASSIFICATIONS:
            raise AuditError(
                f"relation {relation.get('pair_id')}: invalid classification")
        if not relation.get("evidence"):
            raise AuditError(
                f"relation {relation.get('pair_id')}: evidence is required")
    return data


def verify_catalog_evidence(catalog, root):
    """Check every reviewed quote exists at its declared line range."""
    root = Path(root)
    mismatches = []
    cache = {}
    for rule in catalog["rules"]:
        source = rule.get("source") or {}
        path = source.get("path", "")
        rel = path.replace("design-hardware/", "", 1)
        target = root / rel
        if not target.is_file():
            mismatches.append({
                "rule_id": rule["rule_id"], "path": path, "kind": "missing_file"})
            continue
        if rel not in cache:
            cache[rel] = target.read_text(encoding="utf-8").splitlines()
        lines = cache[rel]
        start = int(source.get("line_start") or 0)
        end = int(source.get("line_end") or start)
        quote = _normalise(rule["text"])
        window = ""
        if 1 <= start <= len(lines):
            window = "\n".join(lines[start - 1:max(start, min(end, len(lines)))])
        if quote and quote not in _normalise(window):
            mismatches.append({
                "rule_id": rule["rule_id"], "path": path,
                "line_start": start, "line_end": end,
                "kind": "quote_not_in_line_window",
            })
    for relation in catalog.get("relations", []):
        for evidence in relation.get("evidence", []):
            path = evidence.get("path", "")
            rel = path.replace("design-hardware/", "", 1)
            target = root / rel
            if not target.is_file():
                mismatches.append({
                    "relation_id": relation.get("pair_id"),
                    "path": path, "kind": "missing_file"})
                continue
            if rel not in cache:
                cache[rel] = target.read_text(encoding="utf-8").splitlines()
            line = int(evidence.get("line") or 0)
            quote = _normalise(evidence.get("quote"))
            if line < 1 or line > len(cache[rel]) or quote not in _normalise(
                    cache[rel][line - 1]):
                mismatches.append({
                    "relation_id": relation.get("pair_id"),
                    "path": path, "line": line,
                    "kind": "quote_not_on_declared_line",
                })
    return mismatches


def load_fixtures(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"cannot read fixtures {path}: {exc}")
    if not isinstance(data, dict) or data.get("schema") != FIXTURE_SCHEMA:
        raise AuditError(f"fixtures must have schema {FIXTURE_SCHEMA}")
    pairs = data.get("pairs")
    if not isinstance(pairs, list) or len(pairs) < 12:
        raise AuditError("fixtures must contain at least 12 pairs")
    for pair in pairs:
        if pair.get("expected") not in CLASSIFICATIONS:
            raise AuditError(
                f"fixture {pair.get('pair_id')}: invalid expected classification")
        if not (pair.get("a") or {}).get("text") or not (pair.get("b") or {}).get("text"):
            raise AuditError(f"fixture {pair.get('pair_id')}: missing a/b text")
    return data


def _verify_fixture_quotes(pairs, root):
    root = Path(root)
    cache = {}
    mismatches = []
    for pair in pairs:
        if pair.get("synthetic"):
            continue
        for side in ("a", "b"):
            item = pair.get(side) or {}
            source = item.get("source")
            line = item.get("line")
            if not source or not isinstance(line, int) or line < 1:
                continue
            if source.startswith("constructed:"):
                continue
            rel = source.replace("design-hardware/", "", 1)
            target = root / rel
            if not target.is_file():
                mismatches.append({"pair_id": pair["pair_id"], "side": side,
                                   "kind": "missing_file", "path": source})
                continue
            if rel not in cache:
                cache[rel] = target.read_text(encoding="utf-8").splitlines()
            lines = cache[rel]
            if line > len(lines) or _normalise(item["text"]) not in \
                    _normalise(lines[line - 1]):
                mismatches.append({"pair_id": pair["pair_id"], "side": side,
                                   "kind": "quote_not_on_declared_line",
                                   "path": source, "line": line})
    return mismatches


def extract_machine_rules(index, limit=400):
    rules = []
    seen = set()
    for path in sorted(index["records"]):
        record = index["records"][path]
        try:
            lines = record.abspath.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        in_fence = False
        for number, raw in enumerate(lines, 1):
            stripped = raw.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence or not stripped or stripped.startswith(("#", "|", ">", "<")):
                continue
            if len(stripped) > 500:
                continue
            match = STRENGTH_RE.search(stripped)
            if not match:
                continue
            condition = "unknown"
            condition_match = CONDITION_RE.search(stripped) or \
                EN_CONDITION_RE.search(stripped)
            if condition_match:
                condition = _normalise(condition_match.group(0))
            scope = sorted({
                name for name, terms in SCOPE_TERMS.items()
                if any(term in stripped.lower() for term in terms)})
            exception = "unknown"
            if _has_strong_exception(stripped):
                exception = "has_explicit_exception_marker"
            strength = "unknown"
            if match.group(1) in ("必须", "不得", "禁止", "务必", "严禁",
                                  "一律", "始终", "must", "never", "always"):
                strength = "must"
            elif match.group(1) in ("应", "应当", "建议", "优先", "should"):
                strength = "should"
            elif match.group(1) in ("可以", "可", "may"):
                strength = "may"
            key = _normalise(stripped).casefold()
            if key in seen:
                continue
            seen.add(key)
            digest = hashlib.sha256(
                f"{path}:{number}:{stripped}".encode("utf-8")).hexdigest()[:10]
            rules.append({
                "rule_id": "M-" + digest,
                "text": _normalise(stripped)[:500],
                "source": {"path": path, "line_start": number,
                           "line_end": number},
                "condition": condition,
                "task_scope": scope or ["unknown"],
                "action": _normalise(stripped)[:200],
                "strength": strength,
                "exception": exception,
                "evidence_required": [],
                "priority_declared": "unknown",
                "version_applicability": "v1.0.1",
                "provenance": "machine_extracted",
                "extraction": {"method": "pattern", "confidence": "low",
                               "notes": "deterministic imperative-line pattern; "
                                        "not reviewed"},
            })
            if len(rules) >= limit:
                return rules
    return rules


def _candidate_tensions(rules, reviewed_relation_pairs, limit=200):
    rules = [rule for rule in rules if rule["provenance"] == "machine_extracted"]
    families = ["approval", "autonomy", "full_load", "on_demand",
                "direct_wire", "label", "strict", "lenient"]
    opposite = [("approval", "autonomy"), ("full_load", "on_demand"),
                ("direct_wire", "label"), ("strict", "lenient")]
    by_family = {family: [] for family in families}
    for rule in rules:
        for family in families:
            if _hits(rule["text"], family):
                by_family[family].append(rule)
    candidates = []
    seen = set()
    for left, right in opposite:
        for a in by_family[left]:
            for b in by_family[right]:
                if a["rule_id"] == b["rule_id"]:
                    continue
                key = tuple(sorted((a["rule_id"], b["rule_id"])))
                if key in seen:
                    continue
                seen.add(key)
                if key in reviewed_relation_pairs:
                    continue
                a_scope = set(a["task_scope"])
                b_scope = set(b["task_scope"])
                if "unknown" not in a_scope | b_scope and not (a_scope & b_scope):
                    continue
                candidates.append({
                    "candidate_id": "C-%04d" % (len(candidates) + 1),
                    "relation": "%s_vs_%s" % (left, right),
                    "rule_a": a["rule_id"], "rule_b": b["rule_id"],
                    "evidence": [a["source"], b["source"]],
                    "overlap": {"scope": sorted(a_scope & b_scope) or ["unknown"],
                                "condition": "unknown"},
                    "classification": "candidate",
                    "note": "deterministic keyword families only; not a "
                            "confirmed conflict",
                })
                if len(candidates) >= limit:
                    return candidates
    return candidates


def run_rules(root, *, catalog_path=None, fixtures_path=None, strict=False,
              exclude_paths=()):
    begin = time.perf_counter()
    started = utc_now()
    root = Path(root)
    scan_result, index = scan_root(root, exclude_abs=exclude_paths)
    rules_data = load_rules_catalog(catalog_path) if catalog_path else None
    if rules_data is None:
        from .common import AuditError as _AE
        raise _AE("rules catalog path is required (--catalog)")
    curated_rules = rules_data["rules"]
    mismatches = verify_catalog_evidence(rules_data, root)
    if mismatches:
        raise AuditError(
            "reviewed catalog evidence does not match the fixed baseline: "
            + json.dumps(mismatches[:5], ensure_ascii=False))
    machine_rules = extract_machine_rules(index)
    all_rules = curated_rules + machine_rules
    relations = rules_data.get("relations", [])
    reviewed_pairs = set()
    for relation in relations:
        ids = relation.get("rule_ids") or []
        for first in ids:
            for second in ids:
                if first < second:
                    reviewed_pairs.add((first, second))
    candidates = _candidate_tensions(all_rules, reviewed_pairs)
    fixtures_result = {
        "total": 0, "correct": 0, "accuracy": None, "results": [],
        "mismatches": [],
    }
    if fixtures_path:
        fixtures = load_fixtures(fixtures_path)
        quote_mismatches = _verify_fixture_quotes(fixtures["pairs"], root)
        if quote_mismatches:
            raise AuditError(
                "fixture quotes do not match the fixed baseline: "
                + json.dumps(quote_mismatches[:5], ensure_ascii=False))
        for pair in fixtures["pairs"]:
            actual = _classification(pair["a"]["text"], pair["b"]["text"])
            ok = actual == pair["expected"]
            fixtures_result["results"].append({
                "pair_id": pair["pair_id"], "expected": pair["expected"],
                "actual": actual, "ok": ok,
                "category": pair.get("category"),
                "synthetic": bool(pair.get("synthetic")),
            })
            if not ok:
                fixtures_result["mismatches"].append(pair["pair_id"])
        fixtures_result["total"] = len(fixtures_result["results"])
        fixtures_result["correct"] = sum(
            1 for item in fixtures_result["results"] if item["ok"])
        fixtures_result["accuracy"] = round(
            fixtures_result["correct"] / fixtures_result["total"], 4)

    confirmed = [relation for relation in relations
                 if relation["classification"] == "true_conflict"]
    duration_ms = round((time.perf_counter() - begin) * 1000, 3)
    result = base_result("rules", root, git_sha_for(root), started,
                         duration_ms, True)
    result.update({
        "catalog_version": CATALOG_VERSION,
        "catalog": {"rules": len(curated_rules),
                    "relations": len(relations),
                    "sha256": stable_digest(rules_data)},
        "counts": {
            "rules": len(curated_rules),
            "machine_candidates": len(machine_rules),
            "candidate_tensions": len(candidates),
            "reviewed_relations": len(relations),
            "confirmed_conflicts": len(confirmed),
        },
        "rules": curated_rules,
        "machine_rules_sample": machine_rules[:20],
        "candidates": candidates,
        "reviewed_relations": relations,
        "confirmed_conflicts": confirmed,
        "fixtures": fixtures_result,
        "verification": {
            "catalog_evidence_mismatches": [],
            "fixture_quote_mismatches": [],
            "note": "reviewed catalog and non-synthetic fixture quotes were "
                    "verified against the declared file/line window; machine "
                    "candidates are not reviewed",
        },
        "not_proof": NOT_PROOF + " 规则分类是启发式/人工审查，不是运行时行为证明；"
                                 "未运行模型会话，未测量实际审批次数或阅读 token。",
    })
    result["ok"] = not (strict and fixtures_result.get("mismatches"))
    if strict and fixtures_result.get("mismatches"):
        result["strict_failure"] = fixtures_result["mismatches"]
    return result
