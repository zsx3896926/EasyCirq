"""R1: flying/coupling capacitor endpoints.

A capacitor is in scope only when the input supplies an evidenced flying or
coupling role.  The rule never guesses a role from its reference designator or
value.  Endpoint sets are compared by real connectivity partitions (net aliases
are honoured), so renaming a net does not change the conclusion.
"""
from ..contract import canonical_net, component, connected_pins
from ..facts import applicable_facts, evidence_refs, fact_evidence
from ..units import display
from .common import pin_ref, subject


def _role_caps(data):
    return [entry for entry in data.get("intent", {}).get("capacitor_roles", [])
            if entry["role"] == "flying"]


def _flying_fact_rows(data, component_row, role):
    rows = []
    known = {fact["fact_id"]: fact for fact in data.get("device_facts", [])}
    for fact_id in role.get("fact_ids", []):
        if fact_id not in known:
            return None
        fact = known[fact_id]
        if not any(item["type"] == "flying_capacitor"
                   for item in fact["facts"]):
            return None
        rows.append(fact)
    if rows:
        return [(fact, None, {"mpn": True, "package": None,
                              "revision": None}) for fact in rows]
    return applicable_facts(data, component_row, "flying_capacitor")


def run(data, result):
    roles = _role_caps(data)
    if not roles:
        result.note("没有带证据的 flying/coupling 电容角色；未对普通电容猜角色")
        return
    for role in roles:
        component_row = component(data, role["component"])
        nets = [item["net"] for item in connected_pins(component_row)]
        pin_numbers = [item["number"] for item in connected_pins(component_row)]
        subjects = subject(component_row,
                           [pin_ref(component_row, number)
                            for number in pin_numbers], nets)
        if component_row["kind"] != "capacitor":
            result.invalid("role_on_non_capacitor", subjects,
                           "intent 将非电容实例声明为 flying 电容: " +
                           component_row["ref"])
            continue
        if not role["evidence"] and not role["fact_ids"]:
            result.insufficient(
                "role_without_source", subjects,
                explanation="flying 角色没有声明来源；不能凭位号或名称判断。",
                recommendation="补充用户/原厂角色证据（evidence 或 fact_ids）。",
                unverified=["角色来源", "端点期望"])
            continue
        fact_rows = _flying_fact_rows(data, component_row, role)
        if fact_rows is None:
            result.invalid("unknown_fact_reference", subjects,
                           "fact_ids 指向不存在的 device_fact 或不含 flying_capacitor 事实")
            continue
        evidence = evidence_refs(data, role["evidence"]) + \
            [fact_evidence(fact) for fact, _value, _app in fact_rows]
        if len(connected_pins(component_row)) != 2:
            result.insufficient(
                "terminal_count", subjects,
                actual={"display": str(len(connected_pins(component_row))) +
                        " connected terminals"},
                constraint={"display": "2 connected terminals"},
                explanation="飞跨电容必须恰好有两个可判定端子；当前无法确定。",
                recommendation="核对符号/封装的引脚-网络映射，补齐两端网络。",
                unverified=["完整端子数", "未连接端子的真实状态"])
            continue
        terminals = role.get("expected_terminals") or []
        if terminals:
            actual = {}
            for pin_row in connected_pins(component_row):
                actual[pin_row["number"]] = pin_row["net"]
            expected = {item["pin"]: item["net"] for item in terminals}
            if set(expected) != set(actual):
                result.violated(
                    "endpoint_pin_set_mismatch", subjects,
                    actual={"display": ", ".join(
                        "%s=%s" % (key, actual[key]) for key in sorted(actual)),
                        "pins": sorted(actual)},
                    constraint={"display": ", ".join(
                        "%s=%s" % (key, expected[key]) for key in sorted(expected)),
                        "pins": sorted(expected)},
                    unit=None, evidence=evidence,
                    explanation="飞跨电容实际连接的端子集合与 intent 期望不一致。",
                    recommendation="核对原厂引脚定义与原理图实际连接；不要只改网名。",
                    severity="hard")
                continue
            actual_set = {canonical_net(data, net) for net in actual.values()}
            expected_set = {canonical_net(data, net)
                            for net in expected.values()}
            if actual_set != expected_set:
                result.violated(
                    "endpoint_net_set_mismatch", subjects,
                    actual={"display": ", ".join(sorted(
                        _names(actual.values())))},
                    constraint={"display": ", ".join(sorted(
                        _names(expected.values())))},
                    unit=None, evidence=evidence,
                    explanation="飞跨电容两端网络与期望网络集合不一致（按真实连通分区比较，含别名）。",
                    recommendation="核对电容两端实际网络；不要因网名相近而合并。",
                    severity="hard")
                continue
            if len(actual_set) == 1:
                result.violated(
                    "flying_capacitor_shorted", subjects,
                    actual={"display": "both terminals on " +
                            ", ".join(sorted(_names(actual.values()))),
                            "value": 1, "unit": "net partition"},
                    constraint={"display": "two distinct net partitions"},
                    unit=None, evidence=evidence,
                    explanation="飞跨电容两端落在同一真实网络分区，电容被旁路，不会产生预期泵电/耦合作用。",
                    recommendation="检查两端是否被同名网络/别名/连线短接；以实际连通分区为准确认。",
                    severity="hard")
                continue
            result.satisfied_check(
                subjects, constraint={"display": "two distinct expected net partitions"},
                evidence=evidence,
                explanation="两端引脚与期望网络集合一致，且真实网络分区不同。",
                certainty="proven")
            continue
        # No pin/net expectation: only the short condition is decidable.
        if len(nets) != 2 or any(net is None for net in nets):
            result.insufficient(
                "unknown_endpoint_net", subjects,
                actual={"display": "net unknown for at least one terminal"},
                constraint={"display": "two known distinct net partitions"},
                explanation="缺少完整端点网络，无法证明飞跨电容未被旁路。",
                recommendation="补齐两端网络或原厂连接约束。",
                unverified=["端点网络", "真实连通分区"])
            continue
        if canonical_net(data, nets[0]) == canonical_net(data, nets[1]):
            result.violated(
                "flying_capacitor_shorted", subjects,
                actual={"display": "both terminals on " + str(nets[0]),
                        "value": 1, "unit": "net partition"},
                constraint={"display": "two distinct net partitions"},
                unit=None, evidence=evidence,
                explanation="飞跨电容两端同网，电路上被短路旁路。",
                recommendation="核对电容两端实际连通关系；这是可定位的端点错误。",
                severity="hard")
        else:
            result.satisfied_check(
                subjects, constraint={"display": "two distinct net partitions"},
                evidence=evidence,
                explanation="角色有来源且两端网络分区不同；未声明具体期望网络。",
                certainty="proven")


def _names(values):
    return [str(value) for value in values if value is not None]
