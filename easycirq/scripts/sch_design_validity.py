"""设计有效性检查：这块电路按设计会不会工作。

为什么需要它
------------
现有 18 项 KPI 全是结构性/一致性检查——未连接、跨区、重叠、线长、ERC、去耦、
命名、料号映射、网表 diff、回读、电源网络、图板一致、BOM 一致。
**没有一项问"这个电路按设计会不会工作"。**

报警板上因此漏过去三个纯算术就能查出来的缺陷：

  1. R2 = R3 = 10k → 阈值 2.500V 恰好等于 25°C 时的 NTC 分点
     → 板子在 25°C 就响，而设计要的是 60°C。门禁全绿。
  2. Q1 基极只连到一颗电阻，那颗电阻另一端是开集输出。
     开集只能灌电流、不能供电流 → 基极没有直流通路 → 管子永不导通 → 蜂鸣器不响。
     网表"连上了"，DRC 0 违规，门禁全绿。
  3. 比较器没有正反馈 → 没有回差 → 验收要求里写的"58℃ 响、55℃ 停"做不到。

三条都是人读电路发现的。这个脚本要把它们变成可重复运行的检查。

判据从哪来
----------
"会不会工作"必须先知道"应该做什么"，所以需要一个意图文件（--intent）：

    {
      "schema": "easycirq-design-intent/v1",
      "name": "温度报警器",
      "power_rail": "PWR5V",
      "ground": "GND",
      "threshold": {
        "comparator": "U1",
        "target_c": 60, "tolerance_c": 5,
        "sensor": {"kind": "ntc", "r25": 10000, "b": 3950, "to_net": "GND"},
        "hysteresis_c": 3
      },
      "switches": [{"part": "Q1", "load": "BZ1"}]
    }

没有意图文件时，脚本报 NOT RUN 并说明为什么——**不猜**。
器件引脚功能认不出来时（不在内置表里），同样报 unknown，不猜。

退出码：0 = 全部 pass；1 = 有 fail；2 = 判不了（NOT RUN/unknown）；3 = 输入有问题。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

SCHEMA = "easycirq-design-validity/v1"

# 逻辑侧默认电压；意图文件里的 vcc 优先，这里只是 mosfet 分支的兜底
VCC_FALLBACK = 5.0
INTENT_SCHEMA = "easycirq-design-intent/v1"

# 引脚功能：优先用网表里的 pinName；名字只是数字的器件靠这张表。
# 表里没有的器件一律 unknown——猜错引脚比查不出来更糟。
DEVICE_PINOUT = {
    "LM393": {1: "OUT", 2: "IN-", 3: "IN+", 4: "GND", 8: "VCC"},
    "LM2903": {1: "OUT", 2: "IN-", 3: "IN+", 4: "GND", 8: "VCC"},
    "LM339": {1: "OUT", 2: "IN-", 3: "IN+", 4: "VCC", 12: "GND"},
}

TRANSISTOR_PINS = {"B": "control", "G": "control", "E": "ref", "S": "ref",
                   "C": "load", "D": "load"}

# B/E/C 是双极型，G/S/D 是场效应。**两者不能套同一个模型**：
#   BJT   —— 控制脚要持续吃基极电流，集电极电流 = Ib × hFE
#   MOSFET —— 栅极静态电流几乎为零，只要求栅源电压够开、够关
# 早先只按 BJT 算，于是 MOSFET 会被拿去乘 hFE，算出一个没有意义的数
# （要么假通过、要么假失败）。2026-11-01 做 12V 风扇板时撞到这一点。
BJT_PINS = {"B", "C", "E"}
MOSFET_PINS = {"G", "D", "S"}


def transistor_kind(part: dict) -> str | None:
    """这颗管子是 'bjt' 还是 'mosfet'。引脚名认不出来返回 None。"""
    names = {pin_name(p).upper() for p in part.get("pins") or []}
    if names & BJT_PINS and not (names & {"G", "D", "S"}):
        return "bjt"
    if names & {"G", "D"} and (names & MOSFET_PINS):
        return "mosfet"
    return None


# ---------------------------------------------------------------- 网表读取
def load_netlist(path: pathlib.Path) -> dict:
    raw = path.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    return data.get("result") or data


def parts_of(netlist: dict) -> list[dict]:
    return [c for c in (netlist.get("components") or [])
            if c.get("componentType") == "part"]


def pin_name(pin: dict) -> str:
    name = pin.get("pinName") or pin.get("name") or ""
    return str(name).strip()


def role_of(part: dict, pin: dict) -> str | None:
    """这颗器件的这个引脚，功能是什么。认不出来返回 None。"""
    name = pin_name(pin).upper()
    if name in TRANSISTOR_PINS:
        return TRANSISTOR_PINS[name]
    table = DEVICE_PINOUT.get(str(part.get("manufacturerId") or "").upper())
    if table:
        try:
            return table.get(int(pin.get("pinNumber")))
        except (TypeError, ValueError):
            return None
    return None


def build_nets(netlist: dict) -> dict[str, list[tuple[str, str]]]:
    """net -> [(designator, pinNumber), ...]"""
    nets: dict[str, list[tuple[str, str]]] = {}
    for part in parts_of(netlist):
        for pin in part.get("pins") or []:
            net = pin.get("net") or ""
            if net:
                nets.setdefault(net, []).append(
                    (part.get("designator"), str(pin.get("pinNumber"))))
    return nets


def ohms(value) -> float | None:
    """'10kΩ' / '2.4kΩ' / '470R' -> 欧姆。"""
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Ω", "").replace("欧", "")
    multiplier = 1.0
    if text and text[-1] in "kK":
        multiplier, text = 1e3, text[:-1]
    elif text and text[-1] in "mM":
        multiplier, text = 1e6, text[:-1]
    elif text and text[-1] in "rR":
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def describe_missing_designator(netlist: dict, wanted: str) -> str:
    """意图里的位号在网表里不存在时，把网表实际有什么列出来。

    为什么这条重要（2026-11-02 实测）：`block-apply` 会重新分配位号
    （块的角色 LOAD 被分到 J1），而设计意图文件里写的是手工搭板时的 FAN1。
    于是 inductive_load 报 unknown —— **而 unknown 最容易被当成"没事"略过**，
    实际是"这一项根本没验"。

    只说事实：网表里有哪些位号。不猜"最接近的是哪个"——
    猜错比不说更糟，而人一眼就能对上。
    """
    parts = sorted(c.get("designator") for c in parts_of(netlist))
    if not parts:
        return f"意图写的是 {wanted}，而网表里一个器件都没有"
    return (f"意图写的是 {wanted}，网表里没有这个位号；"
            f"网表里的器件是：{', '.join(parts)}。"
            f"（`block-apply` 落块后会重新分配位号，意图文件要跟着改）")


def part_by(netlist: dict, designator: str) -> dict | None:
    for part in parts_of(netlist):
        if part.get("designator") == designator:
            return part
    return None


# ---------------------------------------------------------------- 阈值检查
def ntc_resistance(temp_c: float, r25: float, b: float) -> float:
    t = temp_c + 273.15
    t25 = 298.15
    return r25 * math.exp(b * (1.0 / t - 1.0 / t25))


def find_divider(netlist: dict, nets: dict, node: str, rail: str, ground: str):
    """在 node 上找一颗拉到 rail 的电阻和一颗拉到 ground 的电阻。"""
    to_rail = to_ground = None
    for designator, pin_number in nets.get(node, []):
        part = part_by(netlist, designator)
        if part is None:
            continue
        resistance = ohms((part.get("otherProperty") or {}).get("Value"))
        if resistance is None:
            continue
        other_nets = {p.get("net") for p in part.get("pins") or []
                      if str(p.get("pinNumber")) != pin_number}
        if rail in other_nets:
            to_rail = (designator, resistance)
        elif ground in other_nets:
            to_ground = (designator, resistance)
    return to_rail, to_ground


def threshold_specs(intent: dict) -> list:
    """意图里声明的阈值规格，可能有多组（窗口比较器、双阈值报警）。

    两种写法都接受：
      "threshold":  { ... }           单比较器（旧写法，全部既有文件都用它）
      "thresholds": [ {...}, {...} ]  多比较器（新写法）

    单数值数组也容忍：`"thresholds": [ {...} ]` 等价于单比较器。
    """
    many = intent.get("thresholds")
    if isinstance(many, list) and many:
        return [spec for spec in many if isinstance(spec, dict)]
    single = intent.get("threshold")
    if isinstance(single, dict):
        return [single]
    return []


def run_per_spec(check_fn, check_id, specs, netlist, nets, intent, findings):
    """对每一组阈值规格各跑一遍，把结果聚合成一条检查。

    聚合规则要保证"多比较器板不比单比较器板更宽松"：
      - 任何一组 fail          → fail
      - 否则任何一组 unknown   → unknown
      - 否则任何一组 not_run   → not_run
      - 全 pass                → pass

    `per_comparator` 里保留每组的完整 metrics，单比较器板不写这个字段，
    所以既有的读取方式（check["metrics"]）在单组时行为不变。
    """
    runs = []
    for spec in specs:
        local_findings = []
        sub_intent = dict(intent)
        sub_intent.pop("thresholds", None)
        sub_intent["threshold"] = spec
        result = check_fn(netlist, nets, sub_intent, local_findings)
        findings.extend(local_findings)
        runs.append(result)

    statuses = [r.get("status") for r in runs]
    if "fail" in statuses:
        worst = "fail"
    elif "unknown" in statuses:
        worst = "unknown"
    elif "not_run" in statuses:
        worst = "not_run"
    elif all(s == "pass" for s in statuses):
        worst = "pass"
    else:
        worst = "unknown"

    comparator = (specs[0] or {}).get("comparator")
    if len(runs) == 1:
        result = dict(runs[0])
        result["id"] = check_id
        return result
    return {
        "id": check_id,
        "status": worst,
        "metrics": runs[0].get("metrics") if comparator else None,
        "per_comparator": [
            {"comparator": (spec or {}).get("comparator"),
             "status": run.get("status"),
             "metrics": run.get("metrics")}
            for spec, run in zip(specs, runs)
        ],
    }


def rail_voltages(intent: dict) -> dict:
    """网络名 → 电压。判「实际加在器件上多少伏」必须先有这个。

    优先级：
      1. intent["rails"]（第 5 轮加的，最明确）
      2. intent["power_rail"] 配 threshold.vcc（旧写法）
      3. intent["ground"] → 0V
    查不到的轨**不猜**——调用方拿到 None 就该报 unknown。
    """
    volts = {}
    for name, value in (intent.get("rails") or {}).items():
        try:
            volts[name] = float(value)
        except (TypeError, ValueError):
            continue
    ground = intent.get("ground") or "GND"
    volts.setdefault(ground, 0.0)
    rail = intent.get("power_rail") or "PWR5V"
    if rail not in volts:
        vcc = (intent.get("threshold") or {}).get("vcc")
        if isinstance(vcc, (int, float)):
            volts[rail] = float(vcc)
    return volts


def net_voltage_bounds(netlist, nets, intent) -> dict:
    """每个网络的**电压范围** [下界, 上界]，供判耐压用。

    ## 为什么是范围而不是一个值

    GATE 这种节点在不同状态下电压不同：比较器输出拉低时 ≈0V，开集输出关断时
    被上拉到 5V。**给一个"工作点"数字就是撒谎。** 而判耐压要的恰恰是最坏情况，
    所以这里算的是**这个节点最坏能到多少伏**。

    ## 规则（简单、可解释、方向安全）

    从节点出发，经**任意器件**遍历连通部分，遇到已声明的电源轨就记下它的电压。
    **地只作终点，不作中继**——否则全板会通过地短成一坨，每个节点都报 12V。

    上界 = 可达轨里的最高电压；下界 = 可达轨里的最低电压。

    这样得到的是**保守上界**：GATE 经 R5 可达 PWR5V → 上界 5V（哪怕比较器
    永远拉低）；FAN_M 经 FAN1 可达 PWR12V、经 Q1 可达 GND → 范围 [0, 12]。

    保守方向只在一处有代价：可能把"实际永远到不了"的电压算成最坏值。
    对判耐压而言这是**安全的**（宁可早报，不可漏报），但输出里必须说明
    这是最坏情况而不是工作点，别让人当成实测值。

    ## 判不了的

    连通部分里一个已声明轨都够不到 → 该网络不出现在结果里，调用方报 unknown。
    """
    volts = rail_voltages(intent)
    ground = intent.get("ground") or "GND"

    bounds = {}
    for net in nets:
        if net in volts:
            bounds[net] = (volts[net], volts[net])
            continue
        reachable = set()
        seen = {net}
        queue = [net]
        while queue:
            current = queue.pop()
            # nets 里存的是 (位号, 引脚号字符串)，role_of 要的是 pin dict，
            # 所以要按引脚号找回那个 dict。
            for designator, entry_pin_number in nets.get(current, []):
                part = part_by(netlist, designator)
                if part is None:
                    continue
                entry_pin = next(
                    (pin for pin in part.get("pins") or []
                     if str(pin.get("pinNumber")) == str(entry_pin_number)), None)
                # **晶体管的控制脚与沟道是隔离的**：栅极/基极不通到漏/源/集/射。
                # 上一版没管这条，于是 GATE 经 Q1 的栅极"走到"漏极再到 12V 轨，
                # 算出 7V（|12-5|）——比真实的 5V 还高，凭空造出一个不存在的应力。
                # 从控制脚进入的连通部分到此为止。
                if (transistor_kind(part) is not None and entry_pin is not None
                        and role_of(part, entry_pin) == "control"):
                    continue
                for pin in part.get("pins") or []:
                    other = pin.get("net")
                    if not other or other in seen:
                        continue
                    if other in volts:
                        # 地只作为终点记下来，不作为中继继续扩散
                        reachable.add(volts[other])
                        continue
                    if other == ground:
                        continue
                    seen.add(other)
                    queue.append(other)
        if not reachable:
            continue
        bounds[net] = (min(reachable), max(reachable))
    return bounds


def worst_gap(bounds: dict, a: str, b: str):
    """两条网络之间的**最坏电位差**。任一端没有范围就返回 None。"""
    if a not in bounds or b not in bounds:
        return None
    a_lo, a_hi = bounds[a]
    b_lo, b_hi = bounds[b]
    return max(abs(a_hi - b_lo), abs(b_hi - a_lo))


def check_ratings(netlist, nets, intent, findings) -> dict:
    """器件额定应力：把**实际加在器件上的电压**和意图声明的额定值比。

    ## 为什么额定值要由意图声明

    数据手册不在网表里——"这颗管子 Vds 上限 30V"无法从图纸推出来。
    所以这里沿用本代码库已有的模式（hfe / vgs_th / id_max_a 都是声明式）：
    **人声明额定值，工具算应力，两者相减**。
    工具不做的事：猜额定值、按器件型号查参数、给"典型值"。

    ## 能算的应力

      开关管关断时，漏极/集电极坐在负载轨上：
          Vds / Vce（最坏情况）= 负载轨电压
      通用条目：两条已声明轨之间的电位差
          |V(a) - V(b)|
      电阻功率：已知阻值 + 两端电压 → V²/R

    ## 判不了的

    任何一端不是**已声明的电源轨**（比如中间网络）→ 该项 unknown，不猜。
    """
    volts = rail_voltages(intent)
    bounds = net_voltage_bounds(netlist, nets, intent)
    items = []
    failed = False

    def judge(part, label, actual, limit, where):
        """统一比较：超了 fail，接近上限只给 advisory（不判定失败）。"""
        nonlocal failed
        if actual is None:
            items.append({"part": part, "metric": label, "status": "unknown",
                          "reason": f"{where} 的电压算不出来（不是已声明的电源轨），不猜"})
            return
        if limit is None:
            return
        ratio = actual / limit if limit else 0
        if actual > limit:
            failed = True
            message = (f"{part} 的 {label} 实际 {actual:.2f}V 超过额定 {limit:.2f}V"
                       f"（{ratio*100:.0f}%）——{where}")
            findings.append({"code": "OVER_RATING", "status": "confirmed",
                             "part": part, "message": message})
            items.append({"part": part, "metric": label, "status": "fail",
                          "actual_v": round(actual, 3), "limit_v": limit,
                          "reason": message})
            return
        if ratio >= 0.8:
            findings.append({"code": "RATING_MARGIN_THIN", "status": "advisory",
                             "part": part,
                             "message": (f"{part} 的 {label} 实际 {actual:.2f}V 已达额定 "
                                         f"{limit:.2f}V 的 {ratio*100:.0f}%，余量不足 20%")})
        items.append({"part": part, "metric": label, "status": "pass",
                      "actual_v": round(actual, 3), "limit_v": limit,
                      "where": where})

    # ① 开关管的电压额定
    for entry in intent.get("switches") or []:
        designator = entry.get("part")
        load_rail = entry.get("load_rail") or intent.get("load_rail")
        v_off = volts.get(load_rail) if load_rail else None
        where = f"关断时 {designator} 承受 {load_rail} 的电压" if load_rail             else f"{designator} 未声明 load_rail"
        for field, label in (("vds_max", "Vds"), ("vce_max", "Vce"),
                             ("vdss_max", "Vds")):
            if entry.get(field) is not None:
                judge(designator, label, v_off, float(entry[field]), where)
        # 栅极/基极电压额定：驱动电平来自逻辑轨
        drive_rail = intent.get("power_rail") or "PWR5V"
        v_drive = volts.get(drive_rail)
        for field, label in (("vgs_max", "Vgs"), ("vbe_max", "Vbe")):
            if entry.get(field) is not None:
                judge(designator, label, v_drive, float(entry[field]),
                      f"驱动电平取自 {drive_rail}")

    # ② 通用条目：任意两轨之间的电位差
    for entry in intent.get("ratings") or []:
        designator = entry.get("part")
        between = entry.get("between") or []
        if len(between) != 2:
            items.append({"part": designator, "status": "unknown",
                          "reason": "ratings 条目必须给 between: [网名A, 网名B]"})
            continue
        a, b = between
        # 先按"两端都是已声明轨"算（精确），退一步再用最坏电位差（保守上界）。
        # 中间节点（GATE / 漏极）走第二条。
        va, vb = volts.get(a), volts.get(b)
        if va is not None and vb is not None:
            actual = abs(va - vb)
            where = f"{a} 与 {b} 之间"
        else:
            actual = worst_gap(bounds, a, b)
            where = f"{a} 与 {b} 之间（最坏情况）"
        if entry.get("max_v") is not None:
            judge(designator, "V", actual, float(entry["max_v"]), where)
        # 功率：需要阻值，从网表读
        max_p = entry.get("max_power_w")
        if max_p is not None:
            part = part_by(netlist, designator)
            resistance = ohms(((part or {}).get("otherProperty") or {}).get("Value"))
            if actual is None or not resistance:
                items.append({"part": designator, "metric": "P", "status": "unknown",
                              "reason": f"算 {designator} 的功率需要两端电压和阻值，缺一不可"})
                continue
            power = actual * actual / resistance
            if power > float(max_p):
                failed = True
                message = (f"{designator} 实际耗散 {power*1000:.1f}mW 超过额定 "
                           f"{float(max_p)*1000:.0f}mW（{where}，{resistance:g}Ω）")
                findings.append({"code": "OVER_RATING", "status": "confirmed",
                                 "part": designator, "message": message})
                items.append({"part": designator, "metric": "P", "status": "fail",
                              "actual_w": round(power, 5),
                              "limit_w": float(max_p), "reason": message})
            else:
                items.append({"part": designator, "metric": "P", "status": "pass",
                              "actual_w": round(power, 5),
                              "limit_w": float(max_p)})

    if not items:
        return {"id": "ratings", "status": "not_run",
                "reason": "意图文件没有声明任何额定值（switches[].vds_max / ratings[]），"
                          "无法判断器件应力"}
    statuses = {i.get("status") for i in items}
    if "fail" in statuses:
        status = "fail"
    elif "unknown" in statuses:
        status = "unknown"
    else:
        status = "pass"
    return {"id": "ratings", "status": status, "items": items,
            "note": "额定值由意图声明（数据手册不在网表里）；"
                    "工具只算实际应力并比较，不猜额定值"}


def trip_point(vcc: float, th: float, r_sensor_up: float,
               r25: float, beta: float) -> float | None:
    """给定分压参数，算 NTC 分压穿越 th 的温度。

    纯函数——不含网表、不含意图，所以容差分析可以直接换参数反复调用。
    """
    def v_at(temp_c: float) -> float:
        resistance = ntc_resistance(temp_c, r25, beta)
        return vcc * resistance / (r_sensor_up + resistance)

    lo, hi = -40.0, 150.0
    v_lo, v_hi = v_at(lo), v_at(hi)
    if not (v_hi < th < v_lo):
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if v_at(mid) > th:
            lo = mid
        else:
            hi = mid
    return lo


def tolerance_spread(vcc: float, r_sensor_up: float, r_top: float, r_bot: float,
                     r25: float, beta: float, pcts: dict) -> dict | None:
    """动作温度的**最坏散布**：把每个带容差的量按 ±pct 扰动，枚举全部组合。

    为什么需要这个（第 1 轮就记过、一直没算）：
    报警板的记录里写着「NTC 的 B 值容差会让 45°C 摊成 61–67°C」，但那是手算的，
    工具没算过。客户问「45±3°C 能做到吗」时，只报标称值 45.3°C 是不够的——
    要报的是**最坏情况下会偏到哪**。

    枚举而不是逐个扰动：±1% 的电阻和 ±1% 的 B 可能同向叠加，
    逐个绕动会低估最坏情况。这里参数少（≤5 个），2^5=32 组全枚举得起。
    """
    def th_of(r_top_v: float, r_bot_v: float) -> float:
        return vcc * r_bot_v / (r_top_v + r_bot_v)

    trips = []
    for d_r in (-1, 1):
        r_sensor = r_sensor_up * (1 + d_r * pcts["resistor"])
        for d_t in (-1, 1):
            r_t = r_top * (1 + d_t * pcts["resistor"])
            for d_b in (-1, 1):
                r_b = r_bot * (1 + d_b * pcts["resistor"])
                for d_25 in (-1, 1):
                    v25 = r25 * (1 + d_25 * pcts["ntc_r25"])
                    for d_beta in (-1, 1):
                        vbeta = beta * (1 + d_beta * pcts["ntc_b"])
                        trip = trip_point(vcc, th_of(r_t, r_b), r_sensor,
                                          v25, vbeta)
                        if trip is not None:
                            trips.append(trip)
    if not trips:
        return None
    return {"trip_min_c": round(min(trips), 2), "trip_max_c": round(max(trips), 2),
            "spread_c": round(max(trips) - min(trips), 2),
            "samples": len(trips)}


def check_threshold(netlist, nets, intent, findings) -> dict:
    spec = intent.get("threshold")
    if not spec:
        return {"id": "threshold_sanity", "status": "not_run",
                "reason": "意图文件没有声明 threshold，无法判断阈值该是多少"}

    rail = intent.get("power_rail") or "PWR5V"
    ground = intent.get("ground") or "GND"
    comparator = spec.get("comparator")
    part = part_by(netlist, comparator)
    if part is None:
        return {"id": "threshold_sanity", "status": "unknown",
                "reason": describe_missing_designator(netlist, comparator)}

    vcc = float(spec.get("vcc") or 5.0)
    roles = {}
    for pin in part.get("pins") or []:
        role = role_of(part, pin)
        if role:
            roles[role] = pin.get("net")
    in_plus, in_minus = roles.get("IN+"), roles.get("IN-")
    if not in_plus or not in_minus:
        return {"id": "threshold_sanity", "status": "unknown",
                "reason": f"{comparator} 的输入引脚认不出来（不在内置器件表里）"}

    # 两路分压：一路是传感器，一路是阈值
    sensor_spec = spec.get("sensor") or {}
    if sensor_spec.get("kind") != "ntc":
        return {"id": "threshold_sanity", "status": "not_run",
                "reason": f"传感器类型 {sensor_spec.get('kind')!r} 未支持"}

    r25 = float(sensor_spec.get("r25") or 10000)
    beta = float(sensor_spec.get("b") or 3950)

    def sensor_voltage(temp_c: float) -> float | None:
        """传感器分压中点电压。传感器接地、上拉接 rail。"""
        for node in (in_plus, in_minus):
            up, down = find_divider(netlist, nets, node, rail, ground)
            if up is None:
                continue
            # 传感器自己是另一支：从 node 到 ground 的非电阻器件
            for designator, _ in nets.get(node, []):
                other = part_by(netlist, designator)
                if other is None or ohms((other.get("otherProperty") or {})
                                         .get("Value")) is not None:
                    continue
                resistance = ntc_resistance(temp_c, r25, beta)
                return vcc * resistance / (up[1] + resistance)
        return None

    def threshold_voltage() -> tuple[float | None, str]:
        for node in (in_plus, in_minus):
            up, down = find_divider(netlist, nets, node, rail, ground)
            if up and down:
                return vcc * down[1] / (up[1] + down[1]), f"{up[0]}/{down[0]}"
        return None, ""

    th, divider = threshold_voltage()
    if th is None:
        return {"id": "threshold_sanity", "status": "unknown",
                "reason": "找不到阈值分压电阻"}

    # 找动作温度：传感器电压随温度上升而下降（NTC 接地），穿越 th 的那一点
    lo, hi = -40.0, 150.0
    v_lo, v_hi = sensor_voltage(lo), sensor_voltage(hi)
    if v_lo is None or v_hi is None:
        return {"id": "threshold_sanity", "status": "unknown",
                "reason": "传感器分压算不出来"}

    if not (v_hi < th < v_lo):
        findings.append({
            "code": "THRESHOLD_NEVER_CROSSES",
            "message": (f"阈值 {th:.3f}V 不落在传感器电压范围 "
                        f"({v_hi:.3f}V@{hi:.0f}°C .. {v_lo:.3f}V@{lo:.0f}°C) 内，"
                        f"这块板要么一直响要么永远不响"),
        })
        return {"id": "threshold_sanity", "status": "fail",
                "metrics": {"threshold_v": round(th, 4), "divider": divider}}

    for _ in range(80):
        mid = (lo + hi) / 2
        if sensor_voltage(mid) > th:
            lo = mid
        else:
            hi = mid
    trip = lo

    target = float(spec.get("target_c") or 60)
    tol = float(spec.get("tolerance_c") or 5)
    metrics = {"threshold_v": round(th, 4), "divider": divider,
               "trip_c": round(trip, 1), "target_c": target,
               "tolerance_c": tol, "delta_c": round(trip - target, 1)}
    detail = {"id": "threshold_sanity", "metrics": metrics}

    # ── 容差分析：只报标称值是不够的，客户问的是「45±3 能做到吗」
    spread = None
    tol_spec = spec.get("tolerances")
    if isinstance(tol_spec, dict):
        # 三个电阻值和两种 NTC 参数的容差，缺哪个都不猜（不默认成 0）
        pcts = {}
        for key, label in (("resistor_pct", "resistor"),
                           ("ntc_r25_pct", "ntc_r25"),
                           ("ntc_b_pct", "ntc_b")):
            value = tol_spec.get(key)
            if not isinstance(value, (int, float)):
                pcts = None
                break
            pcts[label] = float(value) / 100.0
        sensor_up = None
        for node in (in_plus, in_minus):
            up, _down = find_divider(netlist, nets, node, rail, ground)
            if up is not None:
                sensor_up = up[1]
                break
        th_up, th_down = None, None
        for node in (in_plus, in_minus):
            up, down = find_divider(netlist, nets, node, rail, ground)
            if up and down:
                th_up, th_down = up[1], down[1]
                break
        if pcts and sensor_up and th_up and th_down:
            spread = tolerance_spread(vcc, sensor_up, th_up, th_down,
                                      r25, beta, pcts)
            if spread is None:
                metrics["tolerance"] = None
                detail["status"] = "unknown"
                detail["reason"] = ("声明了容差，但扰动后算不出动作温度区间"
                                    "（分压在某个角落永远不穿越阈值），不猜")
                return detail
            metrics["tolerance"] = spread
            if (spread["trip_min_c"] < target - tol
                    or spread["trip_max_c"] > target + tol):
                findings.append({
                    "code": "TOLERANCE_OUT_OF_TARGET", "status": "confirmed",
                    "message": (f"标称动作温度 {trip:.1f}°C 在 {target:.0f}±{tol:.0f}°C 内，"
                                f"但器件容差会让它摊到 {spread['trip_min_c']:.1f}–"
                                f"{spread['trip_max_c']:.1f}°C（散布 "
                                f"{spread['spread_c']:.1f}°C，{spread['samples']} 组组合）"
                                f"——超出目标的批次会误动作"),
                })
                detail["status"] = "fail"
                return detail
    if abs(trip - target) > tol:
        findings.append({
            "code": "THRESHOLD_OUT_OF_TARGET", "status": "confirmed",
            "message": (f"分压 {divider} 算出阈值 {th:.3f}V，"
                        f"实际动作温度 {trip:.1f}°C，目标是 {target:.0f}±{tol:.0f}°C"
                        f"（偏 {trip - target:+.1f}°C）"),
        })
        detail["status"] = "fail"
    else:
        detail["status"] = "pass"
    return detail


# ---------------------------------------------------------------- 驱动检查
def check_drive(netlist, nets, intent, findings) -> dict:
    rail = intent.get("power_rail") or "PWR5V"
    ground = intent.get("ground") or "GND"
    switches = intent.get("switches") or []
    if not switches:
        return {"id": "switch_drive", "status": "not_run",
                "reason": "意图文件没有声明 switches，无法判断哪些管子该被驱动"}

    results = []
    failed = False
    for entry in switches:
        designator = entry.get("part")
        part = part_by(netlist, designator)
        if part is None:
            results.append({"part": designator, "status": "unknown",
                            "reason": describe_missing_designator(netlist, designator)})
            continue
        control_net = None
        for pin in part.get("pins") or []:
            if role_of(part, pin) == "control":
                control_net = pin.get("net")
                break
        if not control_net:
            results.append({"part": designator, "status": "unknown",
                            "reason": "控制引脚认不出来"})
            continue

        # 这个节点上，除管子自己以外，有没有到 rail 或 ground 的电阻通路
        sources = []
        for other, _pin in nets.get(control_net, []):
            if other == designator:
                continue
            other_part = part_by(netlist, other)
            if other_part is None:
                continue
            resistance = ohms((other_part.get("otherProperty") or {}).get("Value"))
            if resistance is None:
                # 不是电阻：可能是驱动源（推挽输出）或别的管子
                sources.append({"part": other, "kind": "non_resistive"})
                continue
            other_nets = {p.get("net") for p in other_part.get("pins") or []}
            where = []
            if rail in other_nets:
                where.append(rail)
            if ground in other_nets:
                where.append(ground)
            sources.append({"part": other, "kind": "resistor",
                            "ohms": resistance, "to": where})

        has_rail_path = any(s["kind"] == "resistor" and rail in s.get("to", [])
                            for s in sources)
        has_ground_path = any(s["kind"] == "resistor" and ground in s.get("to", [])
                              for s in sources)
        # 开集输出只能灌电流，不能给基极供电
        only_open_collector = (not has_rail_path) and any(
            s["kind"] == "non_resistive" for s in sources)

        kind = transistor_kind(part) or str(entry.get("kind") or "").lower() or "bjt"

        # ── MOSFET：栅极不消耗直流电流，判的是"栅极有没有确定的电平"和
        #    "这个电平够不够开"；绝不能拿 hFE 去乘栅极电流。
        if kind == "mosfet":
            vth = float(entry.get("vgs_th") or 1.5)      # 逻辑电平管典型 1.0~2.0V
            id_max = float(entry.get("id_max_a") or 4.0)
            need = float(entry.get("load_ma") or 30) / 1000.0
            if not has_rail_path and not has_ground_path:
                status = "fail"
                failed = True
                reason = (f"{designator} 是 MOSFET，栅极（{control_net}）没有到 {rail} 或 "
                          f"{ground} 的直流通路——栅极悬空时电平不确定，管子状态不可预测")
                findings.append({"code": "NO_GATE_PATH", "status": "confirmed",
                                 "part": designator, "net": control_net,
                                 "message": reason})
            else:
                # 有上拉时，导通时栅极≈rail（除以分压）
                v_gs = 0.0
                driver = None
                # 栅极电压取**声明的**逻辑轨电压，不能写死 5V。
                # 3.3V 逻辑板写死 5V 会把"栅极只有 3.3V"的管子误判成够开。
                v_rail = rail_voltages(intent).get(rail, VCC_FALLBACK)
                for source in sources:
                    if source["kind"] == "resistor" and rail in source.get("to", []):
                        driver = source["part"]
                        # 栅极到驱动器的串联电阻未建模，保守取 rail
                        v_gs = v_rail
                        break
                if driver is None:
                    status = "unknown"
                    reason = ("栅极只有下拉，导通电平取决于驱动源，网表判不了驱动电压")
                elif v_gs < vth:
                    status = "fail"
                    failed = True
                    reason = (f"栅极电压 ≈{v_gs:.2f}V 低于开启门槛 {vth:.2f}V，"
                              f"这颗 MOSFET 打不开")
                    findings.append({"code": "VGS_BELOW_THRESHOLD", "status": "confirmed",
                                     "part": designator,
                                     "message": reason})
                elif need > id_max:
                    status = "fail"
                    failed = True
                    reason = (f"负载需要 {need*1000:.0f}mA，超过这颗管子的 "
                              f"{id_max:.1f}A 额定")
                    findings.append({"code": "LOAD_EXCEEDS_RATING", "status": "confirmed",
                                     "part": designator, "message": reason})
                else:
                    reason = (f"栅极由 {driver} 上拉到 ≈{v_gs:.1f}V（> {vth:.1f}V），"
                              f"静态不取电流，负载 {need*1000:.0f}mA « {id_max:.1f}A")
                    results.append({"part": designator, "kind": "mosfet",
                                    "status": "pass", "reason": reason,
                                    "vgs": round(v_gs, 2), "vgs_th": vth,
                                    "gate_pullup": driver})
                    continue
            results.append({"part": designator, "kind": "mosfet",
                            "status": status, "reason": reason})
            continue

        status = "pass"
        reason = ""
        if not has_rail_path and not has_ground_path:
            status = "fail"
            failed = True
            reason = (f"{designator} 的控制脚（{control_net}）没有到 {rail} 或 {ground} 的"
                      f"直流通路：开集输出只能灌电流、不能供电流，这颗管子永远不会导通")
            findings.append({"code": "NO_DC_BIAS_PATH", "status": "confirmed",
                             "part": designator, "net": control_net,
                             "message": reason})
        else:
            # 有通路时粗算驱动电流（只用上拉电阻，保守）
            for source in sources:
                if source["kind"] == "resistor" and rail in source.get("to", []):
                    vbe = 0.75
                    v_rail = rail_voltages(intent).get(rail, VCC_FALLBACK)
                    current = max(0.0, (v_rail - vbe) / source["ohms"])
                    hfe = float(entry.get("hfe") or 120)
                    ic = current * hfe
                    need = float(entry.get("load_ma") or 30) / 1000.0
                    if ic < need:
                        status = "fail"
                        failed = True
                        findings.append({
                            "code": "DRIVE_INSUFFICIENT", "status": "confirmed",
                            "part": designator,
                            "message": (f"{source['part']} 提供的基极电流 "
                                        f"{current*1000:.2f}mA，hFE 下限 {hfe:.0f} → "
                                        f"可驱动 {ic*1000:.0f}mA，负载需要 "
                                        f"{need*1000:.0f}mA"),
                        })
                    results.append({"part": designator, "kind": kind, "status": status,
                                    "reason": reason,
                                    "base_ma": round(current * 1000, 3),
                                    "ic_ma": round(ic * 1000, 1),
                                    "pullup": source["part"],
                                    "pullup_ohms": source["ohms"]})
                    break
            else:
                results.append({"part": designator, "status": status,
                                "reason": "有直流通路但不是从电源轨上拉，未计算驱动电流",
                                "sources": sources})
                continue

        if status == "fail" and not results:
            results.append({"part": designator, "status": status, "reason": reason})
        elif status == "fail":
            results[-1].update({"status": status, "reason": reason})

    return {"id": "switch_drive",
            "status": "fail" if failed else "pass",
            "switches": results}


# ---------------------------------------------------------------- 回差检查
# ── 二极管：用来认续流二极管。引脚名 A/K 最可靠；很多库用 1/2，约定 1=阳极 2=阴极。
# 器件名里带这些词也当二极管（肖特基、TVS、整流管）。
DIODE_NAME_HINTS = ("1N4148", "1N400", "SS3", "SS5", "BAT", "B5819", "SK34",
                    "SCHOTTKY", "TVS", "DIODE")


def is_diode(part: dict) -> bool:
    names = {pin_name(p).upper() for p in part.get("pins") or []}
    if names & {"A", "K"} or names & {"ANODE", "CATHODE"}:
        return True
    model = str(part.get("manufacturerId") or "").upper()
    return any(hint in model for hint in DIODE_NAME_HINTS)


def diode_polarity(part: dict) -> tuple[str, str] | None:
    """返回 (阳极脚号, 阴极脚号)。认不出来返回 None。"""
    by_name = {}
    for pin in part.get("pins") or []:
        by_name[pin_name(pin).upper()] = str(pin.get("pinNumber"))
    if "A" in by_name and "K" in by_name:
        return by_name["A"], by_name["K"]
    if "ANODE" in by_name and "CATHODE" in by_name:
        return by_name["ANODE"], by_name["CATHODE"]
    numbers = sorted((str(p.get("pinNumber")) for p in part.get("pins") or []),
                     key=lambda x: (len(x), x))
    if len(numbers) == 2:
        # 常见约定：1 = 阳极，2 = 阴极
        return numbers[0], numbers[1]
    return None


def net_of_pin(part: dict, pin_number: str) -> str | None:
    for pin in part.get("pins") or []:
        if str(pin.get("pinNumber")) == pin_number:
            return pin.get("net")
    return None


def check_supply_domains(netlist, nets, intent, findings) -> dict:
    """双电源域：5V 逻辑 + 12V 负载这类板子，最容易看错电源符号。

    能查的三条（纯拓扑，可靠）：
      1. 两个不同电压的轨被 0Ω 电阻连在一起 → 短路
      2. 开关管的负载脚落在逻辑轨上 → 负载两端同电位，永远不工作
      3. 声明了多个地却互不相连 → 两个域没有共地，信号缺参考

    **不能查的（必须承认）**：器件额定电压。要知道"这颗管子 Vds 上限 30V，
    12V 不会击穿它"需要规格书，网表里没有。所以"接了高压会不会烧"这类问题，
    工具判不了，只能人来判。
    """
    rails = intent.get("rails") or {}
    grounds = intent.get("grounds") or []
    if not rails:
        return {"id": "supply_domains", "status": "not_run",
                "reason": "意图文件没有声明 rails（电源轨→电压）；"
                          "没有声明就无法判断哪些网络属于不同电压域"}

    rail_names = {}
    for name, value in rails.items():
        try:
            rail_names[name] = float(value)
        except (TypeError, ValueError):
            return {"id": "supply_domains", "status": "unknown",
                    "reason": f"rails 里 {name} 的电压 {value!r} 不是数字"}

    results = {"id": "supply_domains", "status": "pass", "checks": []}
    failed = False

    # 1. 不同电压的轨被短接
    for designator in {d for members in nets.values() for d, _ in members}:
        part = part_by(netlist, designator)
        if part is None:
            continue
        part_nets = {p.get("net") for p in part.get("pins") or [] if p.get("net")}
        touched = [n for n in part_nets if n in rail_names]
        if len(touched) < 2 or len({rail_names[n] for n in touched}) < 2:
            continue
        value = ohms((part.get("otherProperty") or {}).get("Value"))
        if value is not None and value <= 1.0:
            failed = True
            message = (f"{designator}（{value:g}Ω）把 {touched[0]}"
                       f"（{rail_names[touched[0]]:g}V）与 {touched[1]}"
                       f"（{rail_names[touched[1]]:g}V）直接连在一起，电源会被短路")
            findings.append({"code": "RAIL_SHORTED", "status": "confirmed",
                             "part": designator, "message": message})
            results["checks"].append({"rule": "rail_not_shorted", "status": "fail",
                                      "message": message})
    if not any(c["rule"] == "rail_not_shorted" for c in results["checks"]):
        results["checks"].append({"rule": "rail_not_shorted", "status": "pass"})

    # 2. 开关管的负载脚落在逻辑轨上
    for entry in intent.get("switches") or []:
        designator = entry.get("part")
        load_rail = entry.get("load_rail") or intent.get("load_rail")
        part = part_by(netlist, designator) if designator else None
        if part is None or not load_rail:
            continue
        load_net = None
        for pin in part.get("pins") or []:
            name = (pin.get("pinName") or pin.get("name") or "").strip().upper()
            if name in ("C", "D"):
                load_net = pin.get("net")
                break
        if not load_net:
            results["checks"].append({"rule": "switch_load_not_on_logic_rail",
                                      "status": "unknown",
                                      "note": f"{designator} 的负载脚认不出来"})
            continue
        logic_rails = [n for n in rail_names if n != load_rail]
        if load_net in logic_rails:
            failed = True
            message = (f"{designator} 的负载脚接在 {load_net}（逻辑轨）上，"
                       f"而负载电源轨是 {load_rail}——负载两端会同电位，永远不工作")
            findings.append({"code": "SWITCH_LOAD_ON_LOGIC_RAIL",
                             "status": "confirmed", "part": designator,
                             "message": message})
            results["checks"].append({"rule": "switch_load_not_on_logic_rail",
                                      "status": "fail", "message": message})
        else:
            results["checks"].append({"rule": "switch_load_not_on_logic_rail",
                                      "status": "pass",
                                      "note": f"{designator} 负载脚在 {load_net}"})

    # 3. 多个地必须连通
    if len(grounds) > 1:
        joined = set()
        for designator in {d for members in nets.values() for d, _ in members}:
            part = part_by(netlist, designator)
            if part is None:
                continue
            part_nets = {p.get("net") for p in part.get("pins") or [] if p.get("net")}
            hit = [g for g in grounds if g in part_nets]
            if len(hit) >= 2:
                value = ohms((part.get("otherProperty") or {}).get("Value"))
                if value is None or value <= 1.0:
                    joined.add(tuple(sorted(hit)))
        # 只有"同一个器件跨接两端（无阻值或 0Ω）"才算证明连通。
        # 光有两个不同的网络名不算——那正是"没共地"的样子。
        missing = [(a, b)
                   for i, a in enumerate(grounds)
                   for b in grounds[i + 1:]
                   if (a, b) not in joined]
        if missing:
            failed = True
            for a, b in missing:
                message = (f"声明了两个地 {a} 和 {b}，但网表里没有器件把两者连起来——"
                           f"两个电源域没有共地，信号失去参考点")
                findings.append({"code": "GROUNDS_DISCONNECTED",
                                 "status": "confirmed", "message": message})
                results["checks"].append({"rule": "grounds_joined", "status": "fail",
                                          "message": message})
        else:
            results["checks"].append({"rule": "grounds_joined", "status": "pass"})
    else:
        results["checks"].append({"rule": "grounds_joined", "status": "not_run",
                                  "note": "只声明了一个地，无需连通性判断"})

    results["status"] = "fail" if failed else "pass"
    results["note"] = ("只查拓扑（短路 / 接错域 / 共地）；"
                       "器件额定电压需要规格书，工具判不了")
    return results


def check_inductive_load(netlist, nets, intent, findings) -> dict:
    """感性负载必须续流。

    风扇、继电器、电磁铁断电瞬间，线圈电流不能突变，会在开关管上顶出一个尖峰。
    缺续流二极管时：管子被击穿、寿命骤降，或者干脆当场挂掉。
    **当前 18+1 项门禁一条都不会报这个**，所以要单独判。

    判据：负载的一端接负载电源轨（如 12V），另一端接开关管；二极管必须
    **反并**在负载两端——阴极朝电源轨、阳极朝开关管那侧。
    """
    rail = intent.get("load_rail") or intent.get("power_rail") or "PWR5V"
    ground = intent.get("ground") or "GND"
    switches = intent.get("switches") or []

    targets = [entry for entry in switches
               if entry.get("load_kind") in ("inductive", "motor", "fan", "relay",
                                             "solenoid")
               or entry.get("inductive") is True]
    if not targets:
        return {"id": "inductive_load", "status": "not_run",
                "reason": "意图文件没有把任何负载标成感性（load_kind/inductive），"
                          "不猜"}

    results = []
    failed = False
    for entry in targets:
        load = entry.get("load")
        part = part_by(netlist, load) if load else None
        if part is None:
            results.append({"load": load, "status": "unknown",
                            "reason": describe_missing_designator(netlist, load)})
            continue
        load_nets = [p.get("net") for p in part.get("pins") or [] if p.get("net")]
        if rail not in load_nets:
            results.append({"load": load, "status": "unknown",
                            "reason": f"负载没有一端接在 {rail} 上，判不了接线方式"
                                      f"（看到的是 {load_nets}）"})
            continue
        switched = [n for n in load_nets if n != rail]
        if not switched:
            results.append({"load": load, "status": "unknown",
                            "reason": "负载只有一端有网络，另一端悬空"})
            continue
        live_net = switched[0]

        # 找跨接在 rail 与 live_net 之间的二极管
        found = []
        for other, _pin in nets.get(live_net, []):
            if other == load:
                continue
            candidate = part_by(netlist, other)
            if candidate is None or not is_diode(candidate):
                continue
            polarity = diode_polarity(candidate)
            if polarity is None:
                results.append({"load": load, "status": "unknown",
                                "diode": other,
                                "reason": "找到一颗二极管，但引脚极性认不出来"})
                continue
            anode_net = net_of_pin(candidate, polarity[0])
            cathode_net = net_of_pin(candidate, polarity[1])
            other_nets = {anode_net, cathode_net}
            if rail in other_nets and live_net in other_nets:
                found.append((other, anode_net, cathode_net))

        if not found:
            status = "fail"
            failed = True
            message = (f"{load} 是电感负载，但 {live_net} 与 {rail} 之间没有续流二极管。"
                       f"断电瞬间线圈电流没有泄放回路，会在开关管上顶出尖峰")
            findings.append({"code": "NO_FLYWHEEL_DIODE", "status": "confirmed",
                             "load": load, "message": message})
            results.append({"load": load, "status": status, "reason": message})
            continue

        correct = [d for d in found if d[1] == live_net and d[2] == rail]
        if not correct:
            status = "fail"
            failed = True
            diode, anode_net, cathode_net = found[0]
            message = (f"续流二极管 {diode} 极性接反：阳极接 {anode_net}、阴极接 "
                       f"{cathode_net}。应该反过来——阴极朝 {rail}、阳极朝 {live_net}，"
                       f"否则它正向导通，一上电就把 {rail} 短路")
            findings.append({"code": "FLYWHEEL_DIODE_REVERSED", "status": "confirmed",
                             "load": load, "diode": diode, "message": message})
            results.append({"load": load, "status": status, "reason": message})
            continue

        diode = correct[0][0]
        results.append({"load": load, "status": "pass", "diode": diode,
                        "reason": f"{diode} 反并在 {load} 两端（阴极 {rail}、"
                                  f"阳极 {live_net}），断电尖峰有泄放回路"})

    findings_here = [r for r in results if r["status"] == "fail"]
    return {"id": "inductive_load",
            "status": "fail" if failed else (
                "unknown" if any(r["status"] == "unknown" for r in results) else "pass"),
            "loads": results,
            "failures": len(findings_here)}


def ntc_resistance(t_c: float, r25: float, b: float) -> float:
    """NTC 在温度 t_c 时的阻值（B 值模型）。"""
    return r25 * math.exp(b * (1.0 / (t_c + 273.15) - 1.0 / 298.15))


def ntc_mid_voltage(t_c: float, r_pull: float, r25: float, b: float,
                    vcc: float) -> float:
    """分压中点：上拉 r_pull，NTC 下地。"""
    r = ntc_resistance(t_c, r25, b)
    return vcc * r / (r_pull + r)


def ntc_mid_with_feedback(t_c: float, r_pull: float, r_hyst: float,
                          r25: float, b: float, vcc: float) -> float:
    """输出已拉低（≈0V）时，回差电阻把中点往下拽。"""
    r = ntc_resistance(t_c, r25, b)
    down = r * r_hyst / (r + r_hyst)
    return vcc * down / (r_pull + down)


def _crossing(th: float, fn) -> float:
    """二分找 fn(t) == th 的温度。NTC 阻值随温度单调降，所以单调可解。"""
    lo, hi = -40.0, 150.0
    for _ in range(90):
        mid = (lo + hi) / 2
        if fn(mid) > th:
            lo = mid
        else:
            hi = mid
    return lo


def hysteresis_width_c(spec: dict, r_hyst: float, th: float) -> dict | None:
    """算这条正反馈到底带来多少度的回差。

    目标里点名了这件事：「客户明确要求回差：hysteresis 只判有没有正反馈，不算宽度」。
    所以这里不只回答"有/没有"，而是把宽度算出来和意图里的 hysteresis_c 比。

    模型：
      动作点 trip  —— 温度上升、中点降到 TH 时翻转（此时输出还是高，无反馈）
      释放点 release —— 温度下降、带反馈的中点升回 TH 时翻转
      宽度 = trip - release

    返回 None 表示参数不全，判不了。
    """
    sensor = spec.get("sensor") or {}
    r25 = sensor.get("r25")
    b = sensor.get("b")
    vcc = spec.get("vcc")
    if not isinstance(r25, (int, float)) or not isinstance(b, (int, float)):
        return None
    if not isinstance(vcc, (int, float)):
        return None
    r_pull = spec.get("r_pull_ohms")
    if not isinstance(r_pull, (int, float)):
        return None

    trip = _crossing(th, lambda t: ntc_mid_voltage(t, r_pull, r25, b, vcc))
    release = _crossing(th, lambda t: ntc_mid_with_feedback(
        t, r_pull, r_hyst, r25, b, vcc))
    return {"trip_c": trip, "release_c": release, "width_c": trip - release}


def check_hysteresis(netlist, nets, intent, findings) -> dict:
    spec = intent.get("threshold") or {}
    want = spec.get("hysteresis_c")
    if not want:
        return {"id": "hysteresis", "status": "not_run",
                "reason": "意图文件没有声明 hysteresis_c"}
    comparator = spec.get("comparator")
    part = part_by(netlist, comparator)
    if part is None:
        return {"id": "hysteresis", "status": "unknown",
                "reason": describe_missing_designator(netlist, comparator)}

    out_net = None
    input_nets = set()
    for pin in part.get("pins") or []:
        role = role_of(part, pin)
        if role == "OUT":
            out_net = pin.get("net")
        elif role in ("IN+", "IN-"):
            input_nets.add(pin.get("net"))
    if not out_net or not input_nets:
        return {"id": "hysteresis", "status": "unknown",
                "reason": "输出或输入引脚认不出来"}

    feedback = []
    for designator, _pin in nets.get(out_net, []):
        if designator == comparator:
            continue
        other = part_by(netlist, designator)
        if other is None:
            continue
        other_nets = {p.get("net") for p in other.get("pins") or []}
        if other_nets & input_nets:
            feedback.append(designator)

    if feedback:
        # 有正反馈只是"具备回差"。客户要的是"回差多少度"，
        # 所以算出来和意图里的 hysteresis_c 比 —— 判不了就说判不了。
        r_hyst = ohms((part_by(netlist, feedback[0]).get("otherProperty") or {})
                      .get("Value")) if feedback else None
        th = None
        divider_metrics = check_threshold(netlist, nets, intent, [])
        if divider_metrics.get("metrics"):
            th = divider_metrics["metrics"].get("threshold_v")
        width = None
        if r_hyst and th:
            width = hysteresis_width_c(spec, r_hyst, th)

        metrics = {"feedback_parts": feedback, "r_hyst_ohms": r_hyst}
        if width is None:
            metrics["width_c"] = None
            return {"id": "hysteresis", "status": "unknown", "metrics": metrics,
                    "reason": "有正反馈，但算不出宽度——意图里缺 sensor.r25 / sensor.b / "
                              "vcc / threshold.r_pull_ohms 之一；不猜"}
        metrics.update(width)
        metrics["target_c"] = want
        delta = abs(width["width_c"] - want)
        metrics["delta_c"] = delta
        if delta > 1.0:
            findings.append({
                "code": "HYSTERESIS_WIDTH_OFF", "status": "confirmed",
                "message": (f"回差实测 {width['width_c']:.2f}°C，意图要 {want}°C，"
                            f"差 {delta:.2f}°C（超过 1°C）；"
                            f"改 R_HYST={r_hyst/1000:g}k 或用 tools/size_fan_controller.py 重算")})
            return {"id": "hysteresis", "status": "fail", "metrics": metrics}
        return {"id": "hysteresis", "status": "pass", "metrics": metrics}

    findings.append({
        "code": "NO_HYSTERESIS", "status": "confirmed",
        "message": (f"意图要求 {float(want):.0f}°C 回差，但没有任何器件把 "
                    f"{out_net} 反馈回比较器输入（{sorted(n for n in input_nets if n)}），"
                    f"阈值附近会抖动"),
    })
    return {"id": "hysteresis", "status": "fail",
            "metrics": {"required_c": float(want), "feedback_parts": []}}


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--netlist", required=True, help="sch list 导出的 list.json")
    ap.add_argument("--intent", help="设计意图 JSON；不给则全部 NOT RUN")
    ap.add_argument("--out", help="把结果写成 JSON")
    args = ap.parse_args(argv)

    netlist_path = pathlib.Path(args.netlist)
    if not netlist_path.is_file():
        print(f"sch_design_validity: 读不到网表 {netlist_path}", file=sys.stderr)
        return 3

    try:
        netlist = load_netlist(netlist_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"sch_design_validity: 网表解析失败 {exc}", file=sys.stderr)
        return 3

    findings: list[dict] = []
    checks: list[dict] = []

    if not args.intent:
        # 没有意图文件 ≠ 证据缺失。缺证据是"该跑没跑"，这里是"这块板从未声明
        # 自己要做什么"——判不了就是判不了，判为 na（不适用）并在卡片上可见，
        # 既不冒充 pass，也不假装成一次失败的检查。
        for cid in ("threshold_sanity", "switch_drive", "hysteresis",
                    "inductive_load", "supply_domains", "ratings"):
            checks.append({"id": cid, "status": "na",
                           "reason": "没有提供 --intent：这块板没有声明设计意图，"
                                     "无法判断阈值该是多少、管子该带多大负载"})
    else:
        intent_path = pathlib.Path(args.intent)
        if not intent_path.is_file():
            print(f"sch_design_validity: 读不到意图文件 {intent_path}", file=sys.stderr)
            return 3
        intent = json.loads(intent_path.read_text(encoding="utf-8-sig"))
        if intent.get("schema") != INTENT_SCHEMA:
            print(f"sch_design_validity: intent.schema 必须是 {INTENT_SCHEMA}",
                  file=sys.stderr)
            return 3
        nets = build_nets(netlist)
        specs = threshold_specs(intent)
        if not specs:
            # 意图没声明阈值：让原函数自己报 not_run，别在这里另造一个理由
            checks.append(check_threshold(netlist, nets, intent, findings))
            checks.append(check_drive(netlist, nets, intent, findings))
            checks.append(check_hysteresis(netlist, nets, intent, findings))
        else:
            checks.append(run_per_spec(check_threshold, "threshold_sanity",
                                       specs, netlist, nets, intent, findings))
            checks.append(check_drive(netlist, nets, intent, findings))
            checks.append(run_per_spec(check_hysteresis, "hysteresis",
                                       specs, netlist, nets, intent, findings))
        checks.append(check_inductive_load(netlist, nets, intent, findings))
        checks.append(check_supply_domains(netlist, nets, intent, findings))
        checks.append(check_ratings(netlist, nets, intent, findings))

    # 整体判定要区分两种"没做"：
    #   not_run —— 意图没要求这一项（例如板上没有电感负载，就没有续流二极管可查）
    #   unknown —— 该判但判不了（器件认不出来、网表缺信息）
    # 前者不适用，不该把整块板拖成 unknown；后者必须如实反映成 unknown。
    statuses = [c.get("status") for c in checks]
    neutral = ("pass", "na", "not_run")
    if "fail" in statuses:
        verdict = "fail"
    elif all(s in neutral for s in statuses) and "pass" in statuses:
        verdict = "pass"
    elif all(s in ("na", "not_run") for s in statuses):
        verdict = "na"
    else:
        verdict = "unknown"

    confirmed = [f for f in findings
                 if str(f.get("status", "")).strip().lower() in
                 ("confirmed", "error", "blocked", "violation", "fail")]
    report = {
        "schema": SCHEMA,
        # sch_kpi 读这三个字段：verdict / metrics / findings。
        # design_violations 是 kpi 表里 reads 声明的度量名。
        "status": verdict,
        "verdict": verdict,
        "metrics": {"design_violations": len(confirmed)},
        "netlist": str(netlist_path),
        "intent": args.intent,
        "checks": checks,
        "findings": findings,
    }

    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    for check in checks:
        print(f"  {check['id']:<18} {check['status']}")
        if check.get("reason"):
            print(f"    {check['reason']}")
        # loads 里每一项都有自己的 reason（尤其 unknown 时那句"意图写的是 FAN1，
        # 网表里是 J1 …"）。原来只打印 metrics/switches，这些理由全被吞掉，
        # 于是 unknown 只剩三个字母，看不出为什么判不了。
        for entry in check.get("loads") or []:
            reason = entry.get("reason")
            if reason:
                print(f"    [{entry.get('status')}] {entry.get('load')}: {reason}")
        # 多比较器板：每组各一条，不能只印第一组
        for entry in check.get("per_comparator") or []:
            metrics = json.dumps(entry.get("metrics") or {}, ensure_ascii=False)
            print(f"    [{entry.get('status')}] {entry.get('comparator')}: {metrics}")
        for entry in check.get("items") or []:
            reason = entry.get("reason")
            head = f"{entry.get('part')} {entry.get('metric') or ''}".strip()
            if reason:
                print(f"    [{entry.get('status')}] {head}: {reason}")
            elif entry.get("actual_v") is not None:
                where = entry.get("where")
                tail = f"（{where}）" if where else ""
                print(f"    [{entry.get('status')}] {head}: "
                      f"实际 {entry['actual_v']}V / 额定 {entry.get('limit_v')}V{tail}")
            elif entry.get("actual_w") is not None:
                print(f"    [{entry.get('status')}] {head}: "
                      f"实际 {entry['actual_w']*1000:.1f}mW / "
                      f"额定 {entry.get('limit_w', 0)*1000:.0f}mW")
        for key in ("metrics", "switches"):
            if check.get(key):
                print(f"    {key}: {json.dumps(check[key], ensure_ascii=False)}")
    print()
    for finding in findings:
        print(f"  ! {finding['code']}: {finding['message']}")
    print()
    print(f"设计有效性：{verdict}")

    if verdict == "fail":
        return 1
    if verdict in ("unknown", "na"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
