"""R4: special pin capability and supply/input voltage domain.

Only exact-MPN facts with a compatible package/revision are applied.  A net
whose name contains "IN" is irrelevant unless the input declares a pin role or a
voltage range.  Output pins on custom "input" nets are therefore not flagged.
"""
from ..contract import component, connected_pins, pin
from ..facts import applicable_facts, evidence_refs, fact_evidence
from ..units import display
from .common import (find_pin, pin_ref, power_partitions, single_voltage_range,
                     subject, voltage_constraint)


def _merge_pin_functions(fact_rows):
    merged = {}
    conflict = []
    supply = None
    for fact, applicability in fact_rows:
        for item in fact["facts"]:
            if item["type"] != "pin_functions":
                continue
            value = item["value"]
            for number, entry in value["pins"].items():
                if number in merged and merged[number]["type"] != entry["type"]:
                    conflict.append(number)
                merged.setdefault(number, entry)
            if value.get("supply"):
                if supply is not None and (
                        abs(supply["min_v"] - value["supply"]["min_v"]) > 1e-12 or
                        abs(supply["max_v"] - value["supply"]["max_v"]) > 1e-12):
                    conflict.append("supply")
                supply = value["supply"]
    return merged, supply, sorted(set(conflict))


def _has_pullup(data, net, component_instance):
    power = power_partitions(data)
    for other in data["components"]:
        if other["instance_id"] == component_instance:
            continue
        if other["kind"] != "resistor":
            continue
        nets = [item["net"] for item in connected_pins(other)]
        if len(nets) != 2 or net not in nets:
            continue
        other_net = nets[0] if nets[1] == net else nets[1]
        from ..contract import canonical_net
        if canonical_net(data, other_net) in power:
            return other
    return None


def _compatibility(role, fact_type):
    """Return ('ok'|'violation'|'insufficient', explanation)."""
    if fact_type == "input":
        if role == "input":
            return "ok", "引脚能力为输入，与 intent 输入角色一致。"
        return "violation", "器件事实表明该脚仅输入，intent 却声明为 %s。" % role
    if fact_type == "output":
        if role in ("output", "push_pull"):
            return "ok", "引脚能力为输出。"
        return "violation", "器件事实表明该脚输出，intent 却声明为 %s。" % role
    if fact_type == "bidirectional":
        if role in ("input", "output", "bidirectional", "open_drain"):
            return "ok", "引脚能力为双向，兼容所声明角色。"
        return "violation", "双向引脚与所声明角色 %s 不兼容。" % role
    if fact_type == "open_drain":
        if role == "open_drain":
            return "ok", "开漏输出角色与器件事实一致。"
        if role == "output":
            return "pullup", "器件事实为开漏输出；外部上拉需要另行证明。"
        return "violation", "开漏输出引脚不支持 intent 声明的 %s 角色（不能被当作推挽源）。" % role
    if fact_type == "power":
        if role == "power":
            return "ok", "电源脚与电源角色一致。"
        return "violation", "电源脚被声明为 %s 角色。" % role
    if fact_type == "ground":
        if role == "ground":
            return "ok", "地脚与地角色一致。"
        return "violation", "地脚被声明为 %s 角色。" % role
    if fact_type == "passive":
        if role == "passive":
            return "ok", "无源脚与 passive 角色一致。"
        return "insufficient", "资料仅声明该脚为无源，无法证明 %s 角色。" % role
    return "insufficient", "未知引脚能力。"


def run(data, result):
    roles_by_component = {}
    for entry in data.get("intent", {}).get("pin_roles", []):
        roles_by_component.setdefault(entry["component"], []).append(entry)
    supplies_declared = bool(data.get("intent", {}).get("supplies")) or bool(
        data.get("operating_conditions", {}).get("net_voltages"))
    if not roles_by_component and not supplies_declared:
        result.note("没有 pin_roles 或已声明电压范围；R4 不按网名猜角色")
        return
    for component_row in data["components"]:
        declared_roles = roles_by_component.get(component_row["instance_id"], [])
        fact_rows = applicable_facts(data, component_row, "pin_functions")
        # Supply-domain check also applies to a power pin even without pin_roles.
        supply_pins = []
        all_pin_functions = []
        for fact, applicability in fact_rows:
            for item in fact["facts"]:
                if item["type"] == "pin_functions":
                    all_pin_functions.append((fact, applicability, item["value"]))
        if fact_rows and not all_pin_functions:
            continue
        applicable = [(fact, app, value) for fact, app, value in all_pin_functions
                      if app.get("package") is not False and
                      app.get("revision") is not False]
        mismatch = [(fact, app, value) for fact, app, value in all_pin_functions
                    if app.get("package") is False or app.get("revision") is False]
        if not fact_rows:
            if declared_roles:
                for role_entry in declared_roles:
                    pin_row = find_pin(component_row, role_entry["pin"])
                    result.insufficient(
                        "device_fact_missing",
                        subject(component_row,
                                [pin_ref(component_row, pin_row["number"])]
                                if pin_row else [],
                                [pin_row["net"]] if pin_row else []),
                        constraint={"display": "exact-MPN pin_functions fact"},
                        evidence=evidence_refs(data, role_entry["evidence"]),
                        explanation="没有匹配该精确型号的引脚能力资料，不能验证声明角色。",
                        recommendation="补充精确 MPN 的原厂 pin functions 资料。",
                        unverified=["引脚能力", "资料适用性"])
            continue
        if mismatch and not applicable:
            if declared_roles:
                for role_entry in declared_roles:
                    pin_row = find_pin(component_row, role_entry["pin"])
                    result.insufficient(
                        "fact_not_applicable",
                        subject(component_row,
                                [pin_ref(component_row, pin_row["number"])]
                                if pin_row else [],
                                [pin_row["net"]] if pin_row else []),
                        explanation="找到型号资料，但封装/修订与输入不匹配；不得套用。",
                        recommendation="核对型号后缀、封装和手册修订，补充适用资料。",
                        unverified=["资料适用性"])
            if supplies_declared and any(value.get("supply")
                                         for _fact, _app, value in mismatch):
                result.insufficient(
                    "supply_fact_not_applicable", subject(component_row),
                    constraint={"display": "applicable exact-MPN supply range"},
                    explanation="找到供电范围资料，但封装/修订与输入不匹配；不得套用。",
                    recommendation="核对型号后缀、封装和手册修订，补充适用资料。",
                    unverified=["供电范围", "资料适用性"])
            continue
        pin_functions, supply, conflicts = _merge_pin_functions(
            [(fact, app) for fact, app, _value in applicable])
        if conflicts:
            for role_entry in declared_roles:
                pin_row = find_pin(component_row, role_entry["pin"])
                result.insufficient(
                    "conflicting_device_facts",
                    subject(component_row,
                            [pin_ref(component_row, pin_row["number"])]
                            if pin_row else [], []),
                    explanation="多个适用资料对同一引脚能力/供电范围给出冲突结论。",
                    recommendation="确认唯一适用的手册修订。",
                    unverified=["资料冲突"])
            continue
        for role_entry in declared_roles:
            pin_row = find_pin(component_row, role_entry["pin"])
            if pin_row is None:
                result.invalid("unknown_pin_role", subject(component_row),
                               "pin_roles 指向不存在的引脚")
                continue
            fact_pin = pin_functions.get(pin_row["number"])
            if fact_pin is None and pin_row["name"]:
                fact_pin = pin_functions.get(pin_row["name"])
            subjects = subject(component_row,
                               [pin_ref(component_row, pin_row["number"])],
                               [pin_row["net"]])
            evidence = evidence_refs(data, role_entry["evidence"]) + \
                [fact_evidence(fact) for fact, _app, _value in applicable[:1]]
            if fact_pin is None:
                result.insufficient(
                    "fact_pin_missing", subjects,
                    constraint={"display": "fact pin " + pin_row["number"]},
                    evidence=evidence,
                    explanation="适用资料没有该脚能力条目。",
                    recommendation="核对脚号/符号映射与手册引脚表。",
                    unverified=["该脚能力"])
                continue
            outcome, explanation = _compatibility(role_entry["role"],
                                                  fact_pin["type"])
            constraint = {"display": "fact pin type " + fact_pin["type"],
                          "source": "device fact"}
            if outcome == "ok":
                result.satisfied_check(subjects, constraint=constraint,
                                       evidence=evidence,
                                       explanation=explanation,
                                       certainty="proven")
            elif outcome == "violation":
                result.violated(
                    "pin_capability_conflict", subjects,
                    actual={"display": "intent role " + role_entry["role"]},
                    constraint=constraint, unit=None, evidence=evidence,
                    explanation=explanation,
                    recommendation="核对原厂引脚定义与设计意图；不要把自定义网名当作能力证明。",
                    severity="hard")
            elif outcome == "pullup":
                pullup = _has_pullup(data, pin_row["net"],
                                     component_row["instance_id"])
                if pullup is not None:
                    result.satisfied_check(
                        subjects, constraint=constraint, evidence=evidence,
                        explanation=explanation + " 已检测到上拉电阻 " +
                                    pullup["ref"] + "。", certainty="proven")
                else:
                    result.insufficient(
                        "open_drain_pullup_missing", subjects,
                        actual={"display": "no pull-up resistor found on " +
                                str(pin_row["net"])},
                        constraint=constraint, evidence=evidence,
                        explanation="开漏输出需要上拉；当前连接数据未证明存在上拉路径。",
                        recommendation="核对上拉电阻/外部上拉或改用推挽能力。",
                        unverified=["上拉路径"])
            else:
                result.insufficient(
                    "pin_capability_unverified", subjects,
                    constraint=constraint, evidence=evidence,
                    explanation=explanation,
                    recommendation="补充能证明该角色的资料。",
                    unverified=["引脚能力"])
        # Supply domain, grouped by (net, power-pin set).
        if supply is not None:
            checked_nets = set()
            for number, fact_pin in sorted(pin_functions.items()):
                if fact_pin.get("type") != "power":
                    continue
                pin_row = find_pin(component_row, number)
                if pin_row is None or pin_row["net"] is None:
                    continue
                key = (pin_row["net"], fact_pin.get("name"))
                if key in checked_nets:
                    continue
                checked_nets.add(key)
                range_entry, conflict = single_voltage_range(data,
                                                               pin_row["net"])
                subjects = subject(component_row,
                                   [pin_ref(component_row, pin_row["number"])],
                                   [pin_row["net"]])
                evidence = [fact_evidence(fact) for fact, _app, _value
                            in applicable[:1]]
                if conflict:
                    result.insufficient(
                        "supply_range_conflict", subjects,
                        constraint={"display": "one declared supply range"},
                        evidence=evidence,
                        explanation="同一网络存在互相冲突的供电范围声明。",
                        recommendation="核对 intent.operating_conditions 与 supplies。",
                        unverified=["供电范围"])
                    continue
                if range_entry is None:
                    if supplies_declared:
                        result.insufficient(
                            "supply_range_missing", subjects,
                            constraint=voltage_constraint(
                                supply["min_v"], "device fact supply min") ,
                            evidence=evidence,
                            explanation="电源脚所在网络没有声明电压范围，无法核对越限。",
                            recommendation="补充该电源网的运行范围。",
                            unverified=["供电范围"])
                    continue
                if range_entry.get("kind") != "dc":
                    result.insufficient(
                        "supply_kind_unknown", subjects,
                        actual={"display": str(range_entry.get("kind"))},
                        constraint=voltage_constraint(supply["min_v"],
                                                      "device fact supply min"),
                        evidence=evidence,
                        explanation="供电范围不是 DC 声明，无法按器件推荐范围核对。",
                        recommendation="给该电源网标明知情 DC 范围或单独分析。",
                        unverified=["供电范围"])
                    continue
                if range_entry["min_v"] < supply["min_v"] - 1e-12 or \
                        range_entry["max_v"] > supply["max_v"] + 1e-12:
                    supply_constraint = voltage_constraint(
                        supply["min_v"], "device fact supply range")
                    supply_constraint["max"] = supply["max_v"]
                    supply_constraint["display"] = "%s..%s V" % (
                        display(supply["min_v"], "V"),
                        display(supply["max_v"], "V"))
                    result.violated(
                        "supply_out_of_range", subjects,
                        actual={"display": "%s..%s V" %
                                (display(range_entry["min_v"], "V"),
                                 display(range_entry["max_v"], "V"))},
                        constraint=supply_constraint,
                        unit="V", evidence=evidence,
                        explanation="已声明供电范围超出该精确型号资料的推荐供电范围。",
                        recommendation="按原厂推荐范围调整供电或选型；核对型号后缀/封装。",
                        severity="hard", unverified=[])
                else:
                    constraint = voltage_constraint(supply["min_v"],
                                                    "device fact supply range")
                    constraint["max"] = supply["max_v"]
                    constraint["display"] = "%s..%s V" % (
                        display(supply["min_v"], "V"),
                        display(supply["max_v"], "V"))
                    result.satisfied_check(
                        subjects, constraint=constraint, evidence=evidence,
                        explanation="电源电压范围在器件推荐范围内。",
                        certainty="proven")
        # Input-pin voltage limits from the fact, only when input radius exists.
        for number, fact_pin in sorted(pin_functions.items()):
            if fact_pin.get("type") != "input" or fact_pin.get("max_v") is None:
                continue
            pin_row = find_pin(component_row, number)
            if pin_row is None or pin_row["net"] is None:
                continue
            range_entry, conflict = single_voltage_range(data, pin_row["net"])
            if conflict or range_entry is None:
                continue
            if range_entry["max_v"] > fact_pin["max_v"] + 1e-12:
                result.violated(
                    "input_voltage_out_of_range",
                    subject(component_row,
                            [pin_ref(component_row, pin_row["number"])],
                            [pin_row["net"]]),
                    actual={"display": "%s..%s V" % (
                        display(range_entry["min_v"], "V"),
                        display(range_entry["max_v"], "V"))},
                    constraint=voltage_constraint(
                        fact_pin["max_v"], "device fact input pin max"),
                    unit="V",
                    evidence=[fact_evidence(fact) for fact, _app, _value
                              in applicable[:1]],
                    explanation="输入脚所在网络的声明电压上限超过器件事实允许值。",
                    recommendation="核对电平转换/分压或器件输入额定。",
                    severity="hard")
