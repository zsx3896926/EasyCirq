"""R5: exposed/merged pads and one-to-many logical-pin to physical-pad mapping.

A centre pad is never assumed to be ground.  A required pad connection exists
only when a matching exact-MPN device fact says so.  Missing footprint or pad
mapping evidence yields REVIEW, not a silent footprint pass.
"""
from ..contract import canonical_net, component
from ..facts import applicable_facts, fact_evidence
from .common import (find_pin, ground_partitions, pin_ref, power_partitions,
                     subject, voltage_constraint)


def _pad_nets(pin_row, pads):
    """Resolve each physical pad's net, falling back to the logical pin net."""
    return [pin_row["pad_nets"].get(pad, pin_row["net"]) for pad in pads]


def _role_ok(data, component_row, net, role):
    if net is None:
        return None
    partition = canonical_net(data, net)
    if role == "ground":
        evidence = ground_partitions(data, component_row)
        return partition in evidence if evidence else None
    if role == "power":
        evidence = power_partitions(data)
        return partition in evidence if evidence else None
    if role == "signal":
        ground = ground_partitions(data, component_row)
        power = power_partitions(data)
        if not ground and not power:
            return None
        return not (partition in ground or partition in power)
    return None


def run(data, result):
    fact_rows = []
    for fact in data.get("device_facts", []):
        for item in fact["facts"]:
            if item["type"] == "pad_map":
                fact_rows.append((fact, item["value"]))
    if not fact_rows:
        result.note("没有 pad_map 设备事实；不要求任何中心/合并焊盘，也不判封装核验通过")
        return
    any_match = False
    for fact, value in fact_rows:
        matched = []
        for component_row in data["components"]:
            for applicable_fact, applicability in applicable_facts(
                    data, component_row, "pad_map"):
                if applicable_fact["fact_id"] != fact["fact_id"]:
                    continue
                if applicability.get("package") is False or \
                        applicability.get("revision") is False:
                    matched.append((component_row, applicability, False))
                else:
                    matched.append((component_row, applicability, True))
        if not matched:
            continue
        any_match = True
        # Original requirement conflicts (same physical pad demanded for two
        # different roles) are a fact/design conflict, reported once per fact.
        pad_requirements = {}
        for spec in value["pins"]:
            for pad in spec["pads"]:
                prior = pad_requirements.get(pad)
                requirement = (spec.get("required_net_role"),
                               spec.get("tie_to_pin"))
                if prior is not None and prior != requirement:
                    result.violated(
                        "conflicting_pad_requirement",
                        {"components": [], "pins": [], "nets": []},
                        actual={"display": "pad %s required by %r and %r"
                                % (pad, prior, requirement)},
                        constraint={"display": "one consistent requirement per pad"},
                        unit=None, evidence=[fact_evidence(fact)],
                        explanation="同一物理焊盘被要求连接不同逻辑引脚/角色。",
                        recommendation="核对原厂封装图与符号映射。",
                        severity="hard")
                else:
                    pad_requirements[pad] = requirement
        for component_row, applicability, applicable in matched:
            subjects = subject(component_row)
            evidence = [fact_evidence(fact)]
            if not applicable:
                result.insufficient(
                    "pad_fact_not_applicable", subjects,
                    constraint={"display": "applicable exact-MPN pad_map fact"},
                    evidence=evidence,
                    explanation="找到焊盘映射事实，但封装/修订与输入不匹配，不得套用。",
                    recommendation="核对型号后缀与封装，补充适用资料。",
                    unverified=["封装/焊盘映射"])
                continue
            if not component_row["footprint"]:
                result.insufficient(
                    "footprint_missing", subjects,
                    explanation="缺少封装证据，不能核验裸焊盘/合并焊盘映射。",
                    recommendation="补充封装名称与来源；没有封装证据不能判封装核验通过。",
                    unverified=["封装", "焊盘映射"])
                continue
            if not any(pin_row["pads"] for pin_row in component_row["pins"]):
                result.insufficient(
                    "pad_mapping_missing", subjects,
                    explanation="缺少引脚-物理焊盘映射，无法核验必要焊盘是否遗漏。",
                    recommendation="补充每个引脚对应的物理焊盘号/焊盘名。",
                    unverified=["焊盘映射完整性"])
                continue
            for spec in value["pins"]:
                pin_row = find_pin(component_row, spec["pin"])
                spec_subjects = subject(
                    component_row,
                    [pin_ref(component_row, pin_row["number"])]
                    if pin_row is not None else [],
                    [pin_row["net"]] if pin_row is not None else [])
                if not spec.get("required", True):
                    continue
                if pin_row is None:
                    if component_row["mapping_complete"]:
                        result.violated(
                            "required_pin_missing", spec_subjects,
                            actual={"display": "logical pin %s absent" % spec["pin"]},
                            constraint={"display": "logical pin %s with pads %s"
                                        % (spec["pin"], spec["pads"])},
                            unit=None, evidence=evidence,
                            explanation="资料要求该逻辑引脚/焊盘，但输入的引脚映射中没有它。",
                            recommendation="核对符号/封装映射是否遗漏该脚或裸焊盘。",
                            severity="hard")
                    else:
                        result.insufficient(
                            "required_pin_unmapped", spec_subjects,
                            actual={"display": "logical pin %s absent" % spec["pin"]},
                            constraint={"display": "logical pin %s with pads %s"
                                        % (spec["pin"], spec["pads"])},
                            evidence=evidence,
                            explanation="输入缺少该逻辑引脚，但未声明映射完整性，不能判定遗漏。",
                            recommendation="补充完整引脚-焊盘映射或声明 mapping_complete。",
                            unverified=["映射完整性"])
                    continue
                if not pin_row["pads"]:
                    result.insufficient(
                        "pad_list_missing", spec_subjects,
                        actual={"display": "pin %s has no pads" % pin_row["number"]},
                        constraint={"display": "pads " + repr(spec["pads"])},
                        evidence=evidence,
                        explanation="该逻辑引脚没有声明任何物理焊盘。",
                        recommendation="补充该脚的物理焊盘映射。",
                        unverified=["焊盘映射"])
                    continue
                missing = [pad for pad in spec["pads"]
                           if pad not in pin_row["pads"]]
                if missing:
                    if component_row["mapping_complete"]:
                        result.violated(
                            "required_pad_missing", spec_subjects,
                            actual={"display": "pads mapped: " + repr(pin_row["pads"])},
                            constraint={"display": "pads required: " + repr(spec["pads"])},
                            unit=None, evidence=evidence,
                            explanation="资料要求该逻辑引脚连接一个或多个物理焊盘，输入的映射遗漏了它。",
                            recommendation="核对封装焊盘名/号，特别是裸露热焊盘或合并焊盘。",
                            severity="hard")
                    else:
                        result.insufficient(
                            "required_pad_unverified", spec_subjects,
                            actual={"display": "pads mapped: " + repr(pin_row["pads"])},
                            constraint={"display": "pads required: " + repr(spec["pads"])},
                            evidence=evidence,
                            explanation="映射中缺少数个焊盘，但未声明映射完整性，不能判定遗漏。",
                            recommendation="补充完整焊盘映射或声明 mapping_complete。",
                            unverified=["映射完整性"])
                    continue
                role = spec.get("required_net_role")
                if role is not None:
                    pad_nets = _pad_nets(pin_row, spec["pads"])
                    if any(net is None for net in pad_nets):
                        result.insufficient(
                            "pad_net_unknown", spec_subjects,
                            actual={"display": "net unknown for pads " +
                                    repr([pad for pad, net in
                                          zip(spec["pads"], pad_nets)
                                          if net is None])},
                            constraint={"display": "required net role " + role},
                            evidence=evidence,
                            explanation="焊盘存在但至少一个物理焊盘的网络未知，"
                                        "不能证明所需连接。",
                            recommendation="补齐该脚/焊盘网络（pad_nets 或 pin.net）。",
                            unverified=["焊盘网络"])
                        continue
                    partitions = {canonical_net(data, net) for net in pad_nets}
                    if len(partitions) > 1:
                        result.violated(
                            "pad_net_conflict", spec_subjects,
                            actual={"display": "physical pad nets " +
                                    repr(pad_nets)},
                            constraint={"display": "one net partition per logical pin"},
                            unit=None, evidence=evidence,
                            explanation="同一逻辑引脚的物理焊盘落在不同网络分区，"
                                        "属于冲突映射，不能当作已验证连接。",
                            recommendation="核对封装/符号焊盘映射；必要时拆分逻辑引脚。",
                            severity="hard")
                        continue
                    net = pad_nets[0]
                    ok = _role_ok(data, component_row, net, role)
                    if ok is None:
                        result.insufficient(
                            "net_role_not_classified", spec_subjects,
                            actual={"display": "net " + net},
                            constraint={"display": "required net role " + role},
                            evidence=evidence,
                            explanation="无法把该网络分类为所需角色；不能用网名猜测。",
                            recommendation="在 intent.net_roles 声明网络角色，或补充器件地/电源脚连接证据。",
                            unverified=["网络角色"])
                    elif ok:
                        result.satisfied_check(
                            spec_subjects,
                            constraint={"display": "pads %s -> %s (%s)"
                                        % (spec["pads"], net, role)},
                            evidence=evidence,
                            explanation="所需焊盘存在，并连接到带证据的 %s 网络。" % role,
                            certainty="proven")
                    else:
                        result.violated(
                            "required_pad_wrong_net", spec_subjects,
                            actual={"display": "pad net " + str(net)},
                            constraint={"display": "required net role " + role},
                            unit=None, evidence=evidence,
                            explanation="所需焊盘存在，但连接的网络不是所需 %s 角色。" % role,
                            recommendation="核对原厂封装图与地/电源连接；不得把中心焊盘默认接地。",
                            severity="hard")
                    continue
                tie = spec.get("tie_to_pin")
                if tie:
                    other = find_pin(component_row, tie)
                    if other is None:
                        result.insufficient(
                            "tie_pin_missing", spec_subjects,
                            constraint={"display": "tie to pin " + tie},
                            evidence=evidence,
                            explanation="资料要求焊盘与另一逻辑引脚同网，但该脚未声明。",
                            recommendation="补齐该逻辑引脚映射。",
                            unverified=["合并焊盘关系"])
                        continue
                    pad_nets = _pad_nets(pin_row, spec["pads"])
                    if any(net is None for net in pad_nets) or \
                            other["net"] is None:
                        result.insufficient(
                            "tie_net_unknown", spec_subjects,
                            actual={"display": "net unknown"},
                            constraint={"display": "same net partition as pin " + tie},
                            evidence=evidence,
                            explanation="缺少网络，无法证明合并焊盘与目标脚同网。",
                            recommendation="补齐两端网络。",
                            unverified=["合并焊盘关系"])
                        continue
                    if any(canonical_net(data, net) !=
                           canonical_net(data, other["net"])
                           for net in pad_nets):
                        result.violated(
                            "merged_pad_split_net", spec_subjects,
                            actual={"display": "pad nets %s vs pin %s net %s"
                                    % (pad_nets, tie, other["net"])},
                            constraint={"display": "same net partition"},
                            unit=None, evidence=evidence,
                            explanation="合并/裸焊盘与目标逻辑引脚不在同一网络分区。",
                            recommendation="核对封装映射与原厂连接要求。",
                            severity="hard")
                    else:
                        result.satisfied_check(
                            spec_subjects,
                            constraint={"display": "same net partition as pin " + tie},
                            evidence=evidence,
                            explanation="合并/裸焊盘与目标引脚连接在同一真实网络分区。",
                            certainty="proven")
                    continue
                result.satisfied_check(
                    spec_subjects,
                    constraint={"display": "required pads present: " + repr(spec["pads"])},
                    evidence=evidence,
                    explanation="资料要求的焊盘均存在于映射中；该事实未要求特定网络。",
                    certainty="proven")
    if not any_match:
        result.note("没有组件精确匹配任何 pad_map 事实；R5 未对中心焊盘作默认要求")
