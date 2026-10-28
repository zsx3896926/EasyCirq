"""R6: capacitor role traceability and local placement.

Roles come only from intent evidence.  A local-decoupling distance is checked
only against an explicit project constraint; 100 mil / 150 mil are never global
defaults and bulk capacitors are not forced through the same threshold.  Only a
Euclidean pad-to-pad proxy is measured; high-frequency loop/ESL/EMI is not
proven.
"""
from ..contract import canonical_net, component, connected_pins
from ..facts import evidence_refs
from ..units import display
from .common import pin_ref, subject


def _role_for(data, component_row):
    for entry in data.get("intent", {}).get("capacitor_roles", []):
        if entry["component"] == component_row["instance_id"]:
            return entry
    return None


def _constraints_for(data, component_row):
    return [item for item in data.get("intent", {}).get("decoupling_targets", [])
            if item["capacitor"] == component_row["instance_id"]]


def _coords(component_row, pin_numbers=None):
    points = []
    missing = []
    for pin_row in component_row["pins"]:
        if pin_numbers is not None and pin_row["number"] not in pin_numbers:
            continue
        if pin_row["position"] is None:
            missing.append(pin_ref(component_row, pin_row["number"]))
            continue
        points.append((pin_row["position"]["x"], pin_row["position"]["y"]))
    return points, missing


def _distance(left, right):
    best = None
    for x1, y1 in left:
        for x2, y2 in right:
            value = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
            if best is None or value < best:
                best = value
    return best


def run(data, result):
    capacitors = [item for item in data["components"]
                  if item["kind"] == "capacitor"]
    if not capacitors:
        result.note("输入没有电容；R6 不适用")
        return
    for component_row in capacitors:
        role_entry = _role_for(data, component_row)
        connected = connected_pins(component_row)
        subjects = subject(component_row,
                           [pin_ref(component_row, item["number"])
                            for item in connected],
                           [item["net"] for item in connected])
        if role_entry is None:
            result.insufficient(
                "role_missing", subjects,
                actual={"display": component_row.get("value") or "unknown value"},
                constraint={"display": "traceable role: bulk/local_decoupling/"
                                       "filter/flying/unknown"},
                explanation="没有声明电容角色。仅凭 100nF/10uF 数值不能确定 bulk、"
                            "局部去耦、滤波或飞跨角色。",
                recommendation="在 intent.capacitor_roles 中给出角色与来源。",
                unverified=["角色", "局部布置约束"])
            continue
        role = role_entry["role"]
        evidence = evidence_refs(data, role_entry["evidence"])
        if role == "unknown":
            result.insufficient(
                "role_unknown", subjects,
                actual={"display": "unknown"},
                constraint={"display": "traceable role"},
                evidence=evidence,
                explanation="角色被明确标为 unknown；不能套用任何布置规则。",
                recommendation="补充角色来源或原厂连接约束。",
                unverified=["角色"])
            continue
        if not role_entry["evidence"] and not role_entry.get("fact_ids"):
            result.insufficient(
                "role_without_source", subjects,
                actual={"display": role},
                constraint={"display": "role source and evidence"},
                explanation="角色没有可追溯来源；不能据此套用局部布置规则。",
                recommendation="补充 role_source 的 evidence 或 fact_ids。",
                unverified=["角色来源"])
            continue
        if role == "bulk":
            result.satisfied_check(
                subjects,
                constraint={"display": "bulk capacitor; local decoupling distance "
                                       "threshold intentionally not applied"},
                evidence=evidence,
                explanation="角色为 bulk，不套用局部去耦距离阈值；bulk 仍需按"
                            "回路/容量另行审查。",
                certainty="declared")
            continue
        constraints = _constraints_for(data, component_row)
        if role == "local_decoupling" and not constraints:
            result.insufficient(
                "distance_constraint_missing", subjects,
                actual={"display": "no project distance constraint"},
                constraint={"display": "explicit project constraint (not a global "
                                       "100/150 mil default)"},
                evidence=evidence,
                explanation="局部去耦电容没有项目距离约束；不把经验阈值写成全电路硬标准。",
                recommendation="在 intent.decoupling_targets 提供项目阈值、目标脚和来源。",
                unverified=["距离阈值", "回路/回流路径"])
            continue
        if not constraints:
            result.satisfied_check(
                subjects,
                constraint={"display": "role %s; no local-distance constraint "
                                       "declared" % role},
                evidence=evidence,
                explanation="角色可追溯且不是局部去耦距离规则对象；未套用距离阈值。",
                certainty="declared")
            continue
        for constraint in constraints:
            _check_constraint(data, result, component_row, constraint,
                              subjects, evidence)


def _check_constraint(data, result, component_row, constraint, subjects,
                      role_evidence):
    target = component(data, constraint["target_component"])
    target_pins = constraint["target_pins"]
    if not target_pins:
        result.insufficient(
            "target_pins_missing", subjects,
            constraint={"display": "explicit target power/ground pins"},
            explanation="项目约束没有给出目标 IC 的具体引脚，无法计算引脚到焊盘距离。",
            recommendation="补充 target_pins。",
            unverified=["目标引脚"])
        return
    for number in target_pins:
        if not any(item["number"] == number for item in target["pins"]):
            result.invalid("unknown_target_pin", subjects,
                           "decoupling_targets.target_pins 指向不存在的引脚: " + number)
            return
    if constraint["basis"] != "euclidean_proxy":
        result.insufficient(
            "unsupported_placement_basis", subjects,
            actual={"display": constraint["basis"]},
            constraint={"display": "euclidean_proxy"},
            explanation="只实现了直线距离代理；铜皮/走线/回流路径数据未提供，不能声称高频回路合格。",
            recommendation="提供铜/走线数据或使用其他独立审查；本工具不把直线距离当回流证明。",
            unverified=["铜连接", "回流路径", "ESL/EMI"])
        return
    cap_points, cap_missing = _coords(component_row,
                                      {item["number"] for item in connected_pins(component_row)})
    target_points, target_missing = _coords(target, set(target_pins))
    if cap_missing or target_missing:
        result.insufficient(
            "geometry_missing", subjects,
            actual={"display": "missing positions: " + repr(cap_missing +
                                                            target_missing)},
            constraint={"display": "pad-level coordinates for capacitor and target pins"},
            explanation="缺少焊盘级坐标；不能用器件本体中心或网名代替。",
            recommendation="补充宿主回读的焊盘级几何（坐标、单位、旋转后的绝对位置）。",
            unverified=["几何", "距离"])
        return
    distance = _distance(cap_points, target_points)
    limit = constraint["max_distance"]["value"]
    evidence = role_evidence + evidence_refs(data, constraint.get("evidence", []))
    actual = {"value": round(distance, 6),
              "display": display(distance, "mm") +
                         " (Euclidean proxy, pad-to-pad)",
              "unit": "mm", "measurement": "euclidean_proxy"}
    constraint_block = {
        "value": round(limit, 6),
        "display": display(limit, "mm") + " (project constraint)",
        "unit": "mm",
        "source": constraint.get("source") or "project constraint",
        "target": target["ref"],
        "target_pins": sorted(target_pins),
    }
    if distance > limit + 1e-12:
        result.violated(
            "local_decoupling_too_far", subjects, actual, constraint_block,
            unit="mm", evidence=evidence,
            explanation="局部去耦电容到目标 IC 引脚的直线距离超过项目约束。"
                        "该值是 Euclidean proxy，不代表真实回流回路或高频性能。",
            recommendation="按项目约束调整布置或确认约束不适用于该电容；"
                           "本报告不生成自动布局命令。",
            severity="review",
            certainty="derived",
            unverified=["真实回流路径", "过孔/铜皮", "ESL/EMI"])
    else:
        result.satisfied_check(
            subjects, constraint=constraint_block, evidence=evidence,
            explanation="局部去耦电容到目标引脚的直线距离在项目约束内；"
                        "仅证明 Euclidean proxy，不证明高频回路/ESL/EMI。",
            certainty="derived")
