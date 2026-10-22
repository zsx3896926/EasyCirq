#!/usr/bin/env python3
"""Paper-only interface contract check. No EDA, network or project writes.

Input: interface-contract/v1 JSON. Output: one JSON object on stdout.
Exit 0 = no findings, 1 = findings need review, 2 = invalid input.
A passing report never verifies connector ratings, device thresholds or a real board.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

RESULT_SCHEMA = "interface-contract-check/v1"
CONTRACT_SCHEMA = "interface-contract/v1"
DIRECTIONS = {"A->B", "B->A", "bidirectional", "power", "ground", "none"}
DRIVES = {"push-pull", "open-drain", "power", "none", "unknown"}
UNKNOWN_VALUES = {"", "待查", "unknown", "待确认", "tbd", "TBD"}
SIGNAL_DIRECTIONS = {"A->B", "B->A", "bidirectional"}
THRESHOLD_KEYS = ("voh_min", "vih_max", "vol_max", "vil_min", "absolute_max")
STATE_KEYS = ("A_reset", "B_reset", "A_off", "B_off")
CONNECTOR_FIELDS = ("mpn", "pin_count", "mating_part", "crimp_tool", "view")
PATH_RE = re.compile(r"[A-Za-z0-9_.\-/\\]+:\d+(?:-\d+)?")
SOURCE_RE = re.compile(r"\b(?:[A-Z]{2,4}-S\d+|D-S\d+)\b")
NOT_CHECKED = [
    "连接器 MPN、每针额定、配对端子、压接工具与机械保持力",
    "两端器件的 VOH/VOL/VIH/VIL 与绝对最大额定值",
    "可关断轨的 off_behavior、漏电与反向电流实测",
    "用户可插拔接口的插合序列、热插拔瞬态与地弹",
    "多驱动仲裁的固件实现与总线释放时刻",
    "原理图/PCB 网表与固件配置一致性",
]


def text(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}: require string")
    value = value.strip()
    if not value:
        raise ValueError(f"{label}: require nonblank string")
    return value


def is_unknown(value):
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    value = value.strip()
    return value in UNKNOWN_VALUES or "待查" in value


def string_list(value, label):
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{label}: require array")
    result = []
    for item in value:
        result.append(text(item, f"{label}[]"))
    return result


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def analyze(data):
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    if data.get("schema") != CONTRACT_SCHEMA:
        raise ValueError(f"schema must be {CONTRACT_SCHEMA!r}")
    interfaces = data.get("interfaces")
    if not isinstance(interfaces, list):
        raise ValueError("require interfaces array")
    unresolved = data.get("unresolved")
    if not isinstance(unresolved, list):
        raise ValueError("require unresolved array")
    connectors = data.get("connectors")
    if not isinstance(connectors, list):
        raise ValueError("require connectors array")

    findings = []

    def add(code, severity, message, where):
        findings.append(
            {"code": code, "severity": severity, "message": message, "where": where}
        )

    connector_refs = set()
    if not connectors:
        add("NO_CONNECTORS", "warning", "connectors 为空，无法核对连接器字段", "connectors")
    for index, connector in enumerate(connectors):
        label = f"connectors[{index}]"
        if not isinstance(connector, dict):
            raise ValueError(f"{label}: require object")
        ref = connector.get("ref")
        if is_unknown(ref):
            add("CONNECTOR_REF_UNKNOWN", "unknown", "连接器缺少 ref", f"{label}.ref")
        else:
            ref = text(ref, f"{label}.ref")
            if ref in connector_refs:
                add("DUP_CONNECTOR", "blocking", f"连接器 {ref} 重复声明", f"{label}.ref")
            connector_refs.add(ref)
        for field in CONNECTOR_FIELDS:
            value = connector.get(field)
            if is_unknown(value):
                add(
                    "CONNECTOR_FIELD_UNKNOWN",
                    "unknown",
                    f"连接器 {ref or '#'} 未核实 {field}",
                    f"{label}.{field}",
                )
            elif not isinstance(value, str):
                raise ValueError(f"{label}.{field}: require string")

    if not interfaces:
        add("NO_INTERFACES", "warning", "interfaces 为空，没有可检查的接口", "interfaces")
    interface_ids = set()
    for index, item in enumerate(interfaces):
        label = f"interfaces[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label}: require object")
        raw_id = item.get("id")
        if is_unknown(raw_id):
            iface_id = f"#{index}"
            add("MISSING_FIELD", "unknown", f"接口 {iface_id} 缺字段 id", f"{label}.id")
        else:
            iface_id = text(raw_id, f"{label}.id")
            if iface_id in interface_ids:
                add("DUP_INTERFACE_ID", "blocking", f"接口 ID {iface_id} 重复", f"{label}.id")
            interface_ids.add(iface_id)

        connector_ref = item.get("connector")
        if is_unknown(connector_ref):
            add(
                "MISSING_FIELD",
                "unknown",
                f"接口 {iface_id} 缺字段 connector",
                f"{label}.connector",
            )
        elif not isinstance(connector_ref, str):
            raise ValueError(f"{label}.connector: require string")
        elif connector_ref.strip() not in connector_refs:
            add(
                "UNKNOWN_CONNECTOR",
                "unknown",
                f"接口 {iface_id} 引用了未声明的连接器 {connector_ref}",
                f"{label}.connector",
            )

        for field in (
            "connector_pin",
            "net",
            "domain",
            "leakage",
            "load",
            "supply_state",
            "verification",
            "firmware",
            "basis",
        ):
            value = item.get(field)
            if is_unknown(value):
                add(
                    "MISSING_FIELD",
                    "unknown",
                    f"接口 {iface_id} 缺字段 {field}",
                    f"{label}.{field}",
                )
            elif not isinstance(value, str):
                raise ValueError(f"{label}.{field}: require string")

        direction_raw = item.get("direction")
        direction = None
        if is_unknown(direction_raw):
            add(
                "MISSING_FIELD",
                "unknown",
                f"接口 {iface_id} 缺字段 direction",
                f"{label}.direction",
            )
        else:
            direction = text(direction_raw, f"{label}.direction")
            if direction not in DIRECTIONS:
                raise ValueError(f"{label}.direction: invalid value {direction!r}")

        drive_raw = item.get("drive")
        drive = None
        if is_unknown(drive_raw):
            add(
                "MISSING_FIELD",
                "unknown",
                f"接口 {iface_id} 缺字段 drive",
                f"{label}.drive",
            )
        else:
            drive = text(drive_raw, f"{label}.drive")
            if drive not in DRIVES:
                raise ValueError(f"{label}.drive: invalid value {drive!r}")

        drivers = string_list(item.get("drivers"), f"{label}.drivers")
        receivers = string_list(item.get("receivers"), f"{label}.receivers")
        owners = string_list(item.get("owners"), f"{label}.owners")
        peer_obligations = string_list(
            item.get("peer_obligations"), f"{label}.peer_obligations"
        )
        change_triggers = string_list(
            item.get("change_triggers"), f"{label}.change_triggers"
        )
        for field, values in (
            ("drivers", drivers),
            ("receivers", receivers),
            ("owners", owners),
            ("peer_obligations", peer_obligations),
            ("change_triggers", change_triggers),
        ):
            if values is None:
                add(
                    "MISSING_FIELD",
                    "unknown",
                    f"接口 {iface_id} 缺字段 {field}",
                    f"{label}.{field}",
                )
        if drivers is not None and not drivers and direction not in {"ground", "none"}:
            add(
                "NO_DRIVER",
                "unknown",
                f"接口 {iface_id} 没有声明驱动器",
                f"{label}.drivers",
            )
        if drive == "open-drain" and owners is not None and not owners:
            add(
                "OPEN_DRAIN_NO_OWNER",
                "unknown",
                f"接口 {iface_id} 为开漏但未声明上拉所有者",
                f"{label}.owners",
            )
        if (
            peer_obligations is not None
            and not peer_obligations
            and direction in SIGNAL_DIRECTIONS
        ):
            add(
                "PEER_OBLIGATIONS_EMPTY",
                "unknown",
                f"接口 {iface_id} 没有声明对端义务",
                f"{label}.peer_obligations",
            )
        if change_triggers is not None and not change_triggers:
            add(
                "CHANGE_TRIGGERS_EMPTY",
                "unknown",
                f"接口 {iface_id} 没有声明重评触发",
                f"{label}.change_triggers",
            )

        thresholds = item.get("thresholds")
        if not isinstance(thresholds, dict):
            add(
                "MISSING_THRESHOLD",
                "unknown",
                f"接口 {iface_id} 缺 thresholds 对象",
                f"{label}.thresholds",
            )
        else:
            signal = drive in {"push-pull", "open-drain"} or (
                direction in SIGNAL_DIRECTIONS and drive != "power"
            )
            missing_thresholds = []
            threshold_not_applicable = False
            for key in THRESHOLD_KEYS:
                value = thresholds.get(key)
                if is_unknown(value):
                    missing_thresholds.append(key)
                elif not isinstance(value, str):
                    raise ValueError(f"{label}.thresholds.{key}: require string")
                elif value.strip() == "not_applicable" and signal:
                    threshold_not_applicable = True
            if missing_thresholds:
                add(
                    "MISSING_THRESHOLD",
                    "unknown",
                    f"接口 {iface_id} 的门限未核：{'、'.join(missing_thresholds)}",
                    f"{label}.thresholds",
                )
            if threshold_not_applicable:
                add(
                    "THRESHOLD_NOT_APPLICABLE",
                    "unknown",
                    f"接口 {iface_id} 是信号网络，却把门限写成 not_applicable",
                    f"{label}.thresholds",
                )

        state_behavior = item.get("state_behavior")
        if not isinstance(state_behavior, dict):
            add(
                "STATE_BEHAVIOR_UNKNOWN",
                "unknown",
                f"接口 {iface_id} 缺 state_behavior 对象",
                f"{label}.state_behavior",
            )
        else:
            missing_states = [
                key for key in STATE_KEYS if is_unknown(state_behavior.get(key))
            ]
            for key in STATE_KEYS:
                value = state_behavior.get(key)
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"{label}.state_behavior.{key}: require string")
            if missing_states:
                add(
                    "STATE_BEHAVIOR_UNKNOWN",
                    "unknown",
                    f"接口 {iface_id} 未声明状态行为：{'、'.join(missing_states)}",
                    f"{label}.state_behavior",
                )

        multi_driver = item.get("multi_driver")
        if multi_driver is not None and not isinstance(multi_driver, bool):
            if not is_unknown(multi_driver):
                raise ValueError(f"{label}.multi_driver: require boolean or 待查")
        driver_count = len(drivers) if drivers is not None else 0
        effective_multi = multi_driver is True or driver_count > 1
        arbitration = item.get("arbitration")
        if effective_multi:
            if is_unknown(arbitration) or (
                isinstance(arbitration, str) and arbitration.strip() == "not_applicable"
            ):
                add(
                    "MULTI_DRIVER_NO_ARBITRATION",
                    "blocking",
                    f"接口 {iface_id} 有多个驱动器但未声明仲裁",
                    f"{label}.arbitration",
                )
            elif not isinstance(arbitration, str):
                raise ValueError(f"{label}.arbitration: require string")
        else:
            if is_unknown(arbitration):
                add(
                    "MISSING_FIELD",
                    "unknown",
                    f"接口 {iface_id} 缺字段 arbitration",
                    f"{label}.arbitration",
                )
            elif not isinstance(arbitration, str):
                raise ValueError(f"{label}.arbitration: require string")
            elif arbitration.strip() == "待查":
                add(
                    "ARBITRATION_UNKNOWN",
                    "unknown",
                    f"接口 {iface_id} 的仲裁状态待查",
                    f"{label}.arbitration",
                )
        if multi_driver is True and driver_count <= 1:
            add(
                "MULTI_DRIVER_FLAG_MISMATCH",
                "unknown",
                f"接口 {iface_id} 声明多驱动但驱动器少于两个",
                f"{label}.multi_driver",
            )
        if multi_driver is None:
            add(
                "MISSING_FIELD",
                "unknown",
                f"接口 {iface_id} 缺字段 multi_driver",
                f"{label}.multi_driver",
            )

        switchable = item.get("switchable")
        switchable_known = None
        if switchable is None or (isinstance(switchable, str) and switchable.strip() in UNKNOWN_VALUES):
            add(
                "SWITCHABLE_UNKNOWN" if switchable is not None else "MISSING_FIELD",
                "unknown",
                f"接口 {iface_id} 的 switchable 未声明",
                f"{label}.switchable",
            )
        elif not isinstance(switchable, bool):
            raise ValueError(f"{label}.switchable: require boolean or 待查")
        else:
            switchable_known = switchable
        off_behavior = item.get("off_behavior")
        if switchable_known is True:
            if is_unknown(off_behavior) or (
                isinstance(off_behavior, str) and off_behavior.strip() == "not_applicable"
            ):
                add(
                    "SWITCHABLE_RAIL_NO_OFF_BEHAVIOR",
                    "blocking",
                    f"接口 {iface_id} 是可关断轨，但缺 off_behavior",
                    f"{label}.off_behavior",
                )
            elif not isinstance(off_behavior, str):
                raise ValueError(f"{label}.off_behavior: require string")
        else:
            if is_unknown(off_behavior):
                add(
                    "MISSING_FIELD",
                    "unknown",
                    f"接口 {iface_id} 缺字段 off_behavior",
                    f"{label}.off_behavior",
                )
            elif not isinstance(off_behavior, str):
                raise ValueError(f"{label}.off_behavior: require string")

        hotplug = item.get("hotplug")
        if not isinstance(hotplug, dict):
            add(
                "HOTPLUG_UNKNOWN",
                "unknown",
                f"接口 {iface_id} 缺 hotplug 对象",
                f"{label}.hotplug",
            )
        else:
            user_accessible = hotplug.get("user_accessible")
            if user_accessible is None or (
                isinstance(user_accessible, str) and user_accessible.strip() in UNKNOWN_VALUES
            ):
                add(
                    "HOTPLUG_ACCESS_UNKNOWN",
                    "unknown",
                    f"接口 {iface_id} 未声明是否用户可插拔",
                    f"{label}.hotplug.user_accessible",
                )
                user_accessible = None
            elif not isinstance(user_accessible, bool):
                raise ValueError(f"{label}.hotplug.user_accessible: require boolean or 待查")
            mating_sequence = hotplug.get("mating_sequence")
            if mating_sequence is not None and not isinstance(mating_sequence, str):
                raise ValueError(f"{label}.hotplug.mating_sequence: require string")
            if user_accessible is True:
                if is_unknown(mating_sequence) or (
                    isinstance(mating_sequence, str)
                    and mating_sequence.strip() in {"not_applicable", "none"}
                ):
                    add(
                        "HOTPLUG_NO_MATING_SEQUENCE",
                        "blocking",
                        f"接口 {iface_id} 用户可插拔，但缺插合序列",
                        f"{label}.hotplug.mating_sequence",
                    )
            elif mating_sequence is None:
                add(
                    "MISSING_FIELD",
                    "unknown",
                    f"接口 {iface_id} 缺字段 hotplug.mating_sequence",
                    f"{label}.hotplug.mating_sequence",
                )

        verification = item.get("verification")
        if not is_unknown(verification) and isinstance(verification, str):
            if verification.strip() not in {"NOT RUN", "not_run"}:
                add(
                    "VERIFICATION_UNSUPPORTED",
                    "unknown",
                    f"接口 {iface_id} 的 verification 不是 NOT RUN，离线检查不能放行",
                    f"{label}.verification",
                )

        basis = item.get("basis")
        if not is_unknown(basis) and isinstance(basis, str):
            if not PATH_RE.search(basis) and not SOURCE_RE.search(basis):
                add(
                    "BASIS_NOT_TRACEABLE",
                    "unknown",
                    f"接口 {iface_id} 的 basis 不能回到 path:start-end 或来源 ID",
                    f"{label}.basis",
                )

        stale = item.get("stale")
        if isinstance(stale, bool):
            if stale:
                add(
                    "STALE_INTERFACE",
                    "unknown",
                    f"接口 {iface_id} 标记为 stale，必须重核",
                    f"{label}.stale",
                )
        elif stale is None or (isinstance(stale, str) and stale.strip() in UNKNOWN_VALUES):
            add(
                "STALE_UNKNOWN",
                "unknown",
                f"接口 {iface_id} 未声明 stale 状态",
                f"{label}.stale",
            )
        else:
            raise ValueError(f"{label}.stale: require boolean or 待查")

    for index, item in enumerate(unresolved):
        label = f"unresolved[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label}: require object")
        name = item.get("item")
        if is_unknown(name):
            add("UNRESOLVED_INCOMPLETE", "unknown", f"未决项 {label} 缺 item", f"{label}.item")
            continue
        name = text(name, f"{label}.item")
        incomplete = [
            key
            for key in ("why", "owner", "stop_before")
            if not isinstance(item.get(key), str) or not item[key].strip()
        ]
        if incomplete:
            add(
                "UNRESOLVED_INCOMPLETE",
                "unknown",
                f"未决项 {name} 缺少字段：{'、'.join(incomplete)}",
                label,
            )
        else:
            add("UNRESOLVED_ITEM", "unknown", f"未决项：{name}", label)

    order = {"blocking": 0, "warning": 1, "unknown": 2}
    findings.sort(key=lambda finding: order[finding["severity"]])
    counts = {severity: 0 for severity in order}
    for finding in findings:
        counts[finding["severity"]] += 1
    if counts["blocking"]:
        status = "blocked"
    elif findings:
        status = "needs_review"
    else:
        status = "passed"
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "board_verified": False,
        "execution": "OFFLINE_PLANNING",
        "hardware_execution": "NOT RUN",
        "summary": {
            "interfaces": len(interfaces),
            "connectors": len(connectors),
            "blocking": counts["blocking"],
            "warning": counts["warning"],
            "unknown": counts["unknown"],
        },
        "findings": findings,
        "not_checked": NOT_CHECKED,
    }


def error_result(message):
    return {
        "schema": RESULT_SCHEMA,
        "status": "invalid_input",
        "board_verified": False,
        "execution": "OFFLINE_PLANNING",
        "hardware_execution": "NOT RUN",
        "error": {"code": "invalid_input", "message": message},
        "findings": [],
        "not_checked": NOT_CHECKED,
    }


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("contract", help="interface-contract/v1 JSON file")
    try:
        args = parser.parse_args(argv)
        raw = Path(args.contract).read_text(encoding="utf-8")
        data = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {value}")
            ),
        )
        result = analyze(data)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps(error_result(str(exc)), ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
