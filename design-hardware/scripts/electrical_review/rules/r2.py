"""R2: capacitor rated voltage vs evidenced differential stress.

Hard overstress requires a proven maximum differential stress.  The rule either
uses an explicitly declared stress with provenance or a provable DC interval for
both terminals; switching nodes, negative rails and waveforms stay unknown.  It
never substitutes a single-ended voltage for a differential voltage.
"""
from ..contract import component, connected_pins
from ..facts import applicable_facts, evidence_refs, fact_evidence
from ..units import display
from .common import (pin_ref, single_voltage_range, subject, voltage_actual,
                     voltage_constraint)


def _rating(data, component_row):
    """Return (voltage, source_label, evidence, unverified, applicable)."""
    attribute = component_row["attributes"].get("rated_voltage")
    if attribute:
        if not attribute["evidence"]:
            return (attribute["value"], "rated_voltage attribute",
                    [], ["耐压来源未给出"], True)
        return (attribute["value"], "rated_voltage attribute",
                evidence_refs(data, attribute["evidence"]), [], True)
    fact_rows = applicable_facts(data, component_row,
                                 "capacitor_rated_voltage")
    usable = []
    for fact, applicability in fact_rows:
        if applicability.get("package") is False or \
                applicability.get("revision") is False:
            continue
        for item in fact["facts"]:
            if item["type"] == "capacitor_rated_voltage":
                usable.append((fact, item["value"]))
    if not usable:
        if fact_rows:
            return (None, None, [], ["型号资料存在但封装/修订不适用"], False)
        return None, None, [], [], False
    fact, value = usable[0]
    return (value["voltage"], "device fact " + fact["fact_id"],
            [fact_evidence(fact)], [], True)


def _declared_stress(data, component_row):
    attribute = component_row["attributes"].get("max_differential_stress")
    if not attribute:
        return None
    return {
        "value": attribute["value"],
        "display": attribute["display"] +
                   " (declared max differential)",
        "unit": "V",
        "basis": attribute.get("basis") or "declared",
        "evidence": evidence_refs(data, attribute["evidence"]),
        "source_ok": bool(attribute["evidence"]),
    }


def _derived_dc_stress(data, terminals):
    ranges = []
    for net in terminals:
        entry, conflict = single_voltage_range(data, net)
        if conflict:
            return {"unknown": "conflicting_ranges", "reason":
                    "同一网络存在互相冲突的电压范围声明"}
        if entry is None:
            return {"unknown": "missing_range",
                    "reason": "缺少网络 %s 的电压范围" % net}
        if entry.get("kind") != "dc":
            return {"unknown": "non_dc",
                    "reason": ("网络 %s 不是可证明的 DC 区间（kind=%s），"
                               "不把单端电压代替差分应力"
                               % (net, entry.get("kind")))}
        if entry["min_v"] < 0:
            return {"unknown": "negative_rail",
                    "reason": ("网络 %s 含负电压；本期不建模负电源/瞬态" % net)}
        ranges.append(entry)
    low, high = ranges
    stress = max(abs(high["max_v"] - low["min_v"]),
                 abs(low["max_v"] - high["min_v"]))
    return {
        "value": stress,
        "display": display(stress, "V") + " (derived DC interval)",
        "unit": "V",
        "basis": "derived_dc_interval",
        "evidence": evidence_refs(data, high.get("evidence", []) +
                                  low.get("evidence", [])),
        "source_ok": True,
        "ranges": ranges,
    }


def _stress(data, component_row):
    declared = _declared_stress(data, component_row)
    if declared is not None:
        return declared
    connected = connected_pins(component_row)
    if len(connected) != 2 or any(item["net"] is None for item in connected):
        return {"unknown": "terminal_nets", "reason":
                "需要恰好两个已知端网络才能推导差分应力"}
    return _derived_dc_stress(data, [item["net"] for item in connected])


def run(data, result):
    capacitors = [item for item in data["components"]
                  if item["kind"] == "capacitor"]
    if not capacitors:
        result.note("输入没有电容；R2 不适用")
        return
    for component_row in capacitors:
        pins = connected_pins(component_row)
        subjects = subject(component_row,
                           [pin_ref(component_row, item["number"])
                            for item in pins],
                           [item["net"] for item in pins])
        rating, rating_source, rating_evidence, rating_unverified, applicable = \
            _rating(data, component_row)
        if not applicable:
            if rating_unverified:
                result.insufficient(
                    "rating_not_usable", subjects,
                    constraint={"display": "rated voltage with provenance and "
                                           "applicable package/revision"},
                    explanation="耐压值存在，但来源缺失或资料封装/修订不适用；"
                                "不能据此证明耐压是否足够。",
                    recommendation="补充耐压来源/适用资料，或更正型号/封装/修订。",
                    unverified=rating_unverified)
            else:
                result.not_applicable(
                    subjects,
                    "没有带来源的耐压（rated_voltage 属性或匹配的 device fact）；"
                    "R2 不猜额定值")
            continue
        if rating_unverified:
            result.insufficient(
                "rating_without_source", subjects,
                actual={"display": rating_source or "rated voltage"},
                constraint={"display": "rated voltage with evidence"},
                evidence=rating_evidence,
                explanation="耐压值没有来源引用；不能作为已证明的额定值。",
                recommendation="给 rated_voltage 补充 evidence 来源。",
                unverified=rating_unverified)
            continue
        stress = _stress(data, component_row)
        if stress is None:
            result.insufficient(
                "stress_unavailable", subjects,
                constraint=voltage_constraint(rating, rating_source),
                unit="V", evidence=rating_evidence,
                explanation="缺少可证明的两端最大差分应力。",
                recommendation="补充两端网络运行电压范围（DC）或有来源的 declared stress；"
                               "开关节点/波形需专门建模，不能拿单端对地电压代替。",
                unverified=["两端差分应力", "瞬态/波形"])
            continue
        if stress.get("unknown"):
            result.insufficient(
                "stress_%s" % stress["unknown"], subjects,
                actual={"display": "unknown"},
                constraint=voltage_constraint(rating, rating_source),
                unit="V", evidence=rating_evidence,
                explanation=stress["reason"] + "；不能据此判断耐压是否足够。",
                recommendation="补齐可证明的差分应力证据；不要用电源电压或单端电压代替。",
                unverified=["差分应力", "开关/瞬态条件"])
            continue
        if not stress["source_ok"]:
            result.insufficient(
                "stress_without_source", subjects,
                actual={"display": stress["display"]},
                constraint=voltage_constraint(rating, rating_source),
                unit="V", evidence=rating_evidence + stress["evidence"],
                explanation="已声明最大差分应力，但没有来源引用；不能作为证明。",
                recommendation="给 max_differential_stress 补充 evidence 来源。",
                unverified=["应力来源"])
            continue
        evidence = rating_evidence + stress["evidence"]
        actual = {"value": round(stress["value"], 6),
                  "display": stress["display"], "unit": "V"}
        if stress["value"] > rating + 1e-12:
            result.violated(
                "over_rated_voltage", subjects, actual,
                voltage_constraint(rating, rating_source),
                unit="V", evidence=evidence,
                explanation="电容两端最大差分应力超过额定耐压。",
                recommendation="按实际节点应力重新选型或调整电路；本报告不生成自动改线命令。",
                severity="hard")
            continue
        derating = data.get("intent", {}).get("derating")
        if derating:
            fraction = derating["max_voltage_fraction"]
            limit = rating * fraction
            if stress["value"] > limit + 1e-12:
                result.violated(
                    "derating_shortfall", subjects, actual,
                    voltage_constraint(limit,
                                       "project derating %.3g of %s" %
                                       (fraction, rating_source)),
                    unit="V", evidence=evidence + evidence_refs(
                        data, derating.get("evidence", [])),
                    explanation="按已声明的项目降额策略，应力超过允许比例；"
                                "这是项目策略项，不是全行业统一标准。",
                    recommendation="核对项目降额策略与电容实际条件；若策略不适用需显式修改策略来源。",
                    severity="review")
                continue
        result.satisfied_check(
            subjects, constraint=voltage_constraint(rating, rating_source),
            evidence=evidence,
            explanation="有来源的额定耐压不低于可证明的最大差分应力"
                        + ("（包含项目降额）" if derating else "") + "。",
            certainty="derived" if stress["basis"] == "derived_dc_interval"
            else "declared")
