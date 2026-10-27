"""R3: tactile-switch internal groups and effective switching.

Only an explicit device fact for the exact MPN defines internal groups.  Pin
numbers are used; symbol left/right position is never consulted.  Unknown
internal structure produces REVIEW, not a guessed four-pin grouping.
"""
from ..contract import (canonical_net, component, connected_pins,
                        role_of_net)
from ..facts import applicable_facts, evidence_refs, fact_evidence
from .common import pin_ref, subject


def _group_index(groups, pin_number):
    for index, group in enumerate(groups):
        if pin_number in group:
            return index
    return None


def _safe_net_role(data, net):
    role = role_of_net(data, net)
    if role is not None:
        return role
    if any(item["net"] == net for item in
           data.get("intent", {}).get("supplies", [])):
        return "power"
    return None


def run(data, result):
    requirements = data.get("intent", {}).get("switch_requirements", [])
    if not requirements:
        result.note("没有 switch_requirements；未对按键内部结构做猜测")
        return
    for requirement in requirements:
        component_row = component(data, requirement["component"])
        used = requirement["used_pins"] or [
            item["number"] for item in connected_pins(component_row)]
        pins = [component_row_item for component_row_item in
                component_row["pins"] if component_row_item["number"] in used]
        nets = [item["net"] for item in pins]
        subjects = subject(component_row,
                           [pin_ref(component_row, number) for number in used],
                           nets)
        if component_row["kind"] not in ("switch", "other"):
            result.invalid("requirement_on_non_switch", subjects,
                           "switch_requirement 指向非开关实例: " +
                           component_row["ref"])
            continue
        fact_rows = applicable_facts(data, component_row,
                                     "switch_internal_groups")
        fact_rows = [(fact, applicability) for fact, applicability in fact_rows
                     if applicability.get("package") is not False and
                     applicability.get("revision") is not False]
        if not fact_rows:
            if component_row["mpn_status"] != "exact" or not component_row["mpn"]:
                reason = "MPN 未知，无法匹配内部结构资料"
            else:
                reason = "没有匹配型号/封装/修订的原厂内部结构事实"
            result.insufficient(
                "internal_structure_unknown", subjects,
                explanation=reason + "；四脚按键的常通组不能由符号左右位置猜。",
                recommendation="补充该精确型号的原厂内部连接图/表（device_facts）；"
                               "未知时保持 REVIEW。",
                unverified=["内部常通组", "按下闭合关系", "端子编号"])
            continue
        fact, applicability = fact_rows[0]
        value = next(item["value"] for item in fact["facts"]
                     if item["type"] == "switch_internal_groups")
        evidence = [fact_evidence(fact)]
        if len(used) != 2:
            result.insufficient(
                "used_pin_count", subjects,
                actual={"display": str(len(used)) + " used pins"},
                constraint={"display": "2 used pins for a two-terminal switch function"},
                explanation="本期只分析两脚使用的按键功能；多脚使用需明确组合。",
                recommendation="在 switch_requirements.used_pins 中声明实际使用的两个端子。",
                unverified=["多脚组合"])
            continue
        groups = [set(group) for group in value["always_closed_groups"]]
        left_group = _group_index(groups, used[0])
        right_group = _group_index(groups, used[1])
        if left_group is None or right_group is None:
            result.insufficient(
                "fact_missing_used_pin", subjects,
                actual={"display": "used pins %s not both mapped by the fact groups"
                        % used},
                constraint={"display": "fact internal groups cover both used pins"},
                evidence=evidence,
                explanation="原厂内部组事实没有覆盖实际使用的脚号；脚号/符号映射可能不一致，"
                            "不能据此判错。",
                recommendation="核对原厂端子编号与符号/封装脚号映射。",
                unverified=["端子编号映射", "内部常通组"])
            continue
        if left_group == right_group:
            result.violated(
                "always_closed_pair", subjects,
                actual={"display": "%s and %s are in always-closed group %s"
                        % (used[0], used[1], sorted(groups[left_group]))},
                constraint={"display": "used pins must be in different groups "
                                       "or close on press"},
                unit=None, evidence=evidence,
                explanation="实际使用的两个端子始终常通，按键不能产生切换；"
                            "这与符号左右位置无关，只看原厂内部组。",
                recommendation="改用不同常通组的两个端子，或在符号/封装上核对实际脚号。",
                severity="hard")
            continue
        pressed_connects = value.get("pressed_connects_groups")
        connects = False
        if pressed_connects is True and left_group is not None and \
                right_group is not None and left_group != right_group:
            connects = True
        if not connects:
            connects = any(set(used) == set(pair)
                           for pair in value.get("pressed_closes", []))
        if not connects:
            if pressed_connects is None and not value.get("pressed_closes"):
                result.insufficient(
                    "pressed_relation_unknown", subjects,
                    explanation="原厂事实给出常通组，但未给出按下闭合关系；"
                                "不能证明按键能接通。",
                    recommendation="补充按下时连接哪两组/哪两脚的原厂资料。",
                    unverified=["按下闭合关系"])
            else:
                result.violated(
                    "used_pins_never_connect", subjects,
                    actual={"display": "pressed relation does not connect %s and %s"
                            % (used[0], used[1])},
                    constraint={"display": "pressed state connects the used pins"},
                    unit=None, evidence=evidence,
                    explanation="按下时实际使用的两个端子也不连通，按键无法接通电路。",
                    recommendation="核对原厂内部连接图与原理图脚号。",
                    severity="hard")
            continue
        # Effective switching is proven; now check the pressed rail-short risk.
        forbidden = requirement.get("forbidden_pressed_nets", [])
        actual_partitions = {canonical_net(data, net) for net in nets
                             if net is not None}
        for pair in forbidden:
            if {canonical_net(data, pair[0]), canonical_net(data, pair[1])} == \
                    actual_partitions:
                result.violated(
                    "forbidden_pressed_short", subjects,
                    actual={"display": "pressed connects %s" %
                            ", ".join(sorted(str(net) for net in nets if net))},
                    constraint={"display": "forbidden pressed net pair %s" % pair},
                    unit=None, evidence=evidence,
                    explanation="按下后把 intent 明确禁止直连的网络短接。",
                    recommendation="核对按键功能与串限流/上拉/负载路径。",
                    severity="hard")
                break
        else:
            roles = [_safe_net_role(data, net) for net in nets]
            if any(net is None for net in nets):
                result.insufficient(
                    "pressed_net_unknown", subjects,
                    actual={"display": "at least one used pin has unknown net"},
                    explanation="切换关系已证明，但无法排除按下时短接电源/地。",
                    recommendation="补齐两个端子的网络或 net_roles。",
                    unverified=["按下短接风险"])
                continue
            if any(role is None for role in roles):
                result.insufficient(
                    "pressed_net_role_unknown", subjects,
                    actual={"display": "net roles: " + repr(roles)},
                    explanation="切换关系已证明，但网络角色未声明，不能判断按下是否直连电源端。",
                    recommendation="在 intent.net_roles 中声明相关网络角色。",
                    unverified=["按下短接风险"])
                continue
            powerish = [role == "power" for role in roles]
            groundish = [role == "ground" for role in roles]
            if sum(powerish) == 2 or (any(powerish) and any(groundish)):
                result.violated(
                    "pressed_shorts_power_rails", subjects,
                    actual={"display": "pressed connects roles " + repr(roles)},
                    constraint={"display": "pressed state must not short two power "
                                           "rails or a power rail to ground"},
                    unit=None, evidence=evidence,
                    explanation="按下后把两个电源端（或电源与地）直接短接，属于不允许的电源端短接。",
                    recommendation="核对按键用途与是否存在限流/负载路径；本工具不生成自动改线。",
                    severity="hard")
            else:
                result.satisfied_check(
                    subjects,
                    constraint={"display": "different always-closed groups; pressed "
                                           "relation connects used pins; no power-rail short"},
                    evidence=evidence,
                    explanation="按原厂内部组，两个使用端子不同组且按下闭合；网络角色不构成电源端短接。",
                    certainty="proven")
