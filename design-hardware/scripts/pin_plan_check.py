#!/usr/bin/env python3
"""Paper-only pin/resource plan check. No EDA, network or project writes.

Input: pin-plan/v1 JSON. Output: one JSON object on stdout.
Exit 0 = no findings, 1 = findings need review, 2 = invalid input.
A passing report never verifies a physical pin table or a real board.
Optional candidates (status deferred/rejected) must stay out of resources.
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

RESULT_SCHEMA = "pin-plan-check/v1"
DIRECTIONS = {"input", "output", "bidirectional", "power", "ground"}
STRAP_ALLOWED = re.compile(r"^(BOOT|STRAP|RESERVED|NC|N/?A|待查)", re.IGNORECASE)
DEBUG_ALLOWED = re.compile(
    r"(SWD|SWCLK|SWDIO|JTAG|TMS|TCK|TDI|TDO|UART0|U0TXD|U0RXD|DEBUG|RESERVED|NC)",
    re.IGNORECASE,
)
NOT_CHECKED = [
    "完整物理脚表与 pinmux 真实性",
    "封装 NC/EPAD 与未引出脚清单",
    "ADC 通道、参考与衰减档限制",
    "电气时序、驱动能力与实测",
    "原理图/PCB 与固件配置一致性",
]
RESOURCE_KINDS = {
    "gpio",
    "adc",
    "dac",
    "timer",
    "pwm",
    "dma",
    "uart",
    "spi",
    "i2c",
    "interrupt",
    "clock",
    "debug",
}
PLAN_SCHEMA = "pin-plan/v1"


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: require nonblank string")
    return value.strip()


def is_unknown(value):
    return value is None or (isinstance(value, str) and value.strip() in {"", "待查", "unknown"})


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
    if data.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"schema must be {PLAN_SCHEMA!r}")
    pins = data.get("pins")
    if not isinstance(pins, list):
        raise ValueError("require pins array")
    if "resources" not in data:
        raise ValueError("require resources array")
    resources = data["resources"]
    if not isinstance(resources, list):
        raise ValueError("resources must be an array")
    if "unresolved" not in data:
        raise ValueError("require unresolved array")
    unresolved = data["unresolved"]
    if not isinstance(unresolved, list):
        raise ValueError("unresolved must be an array")
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("candidates must be an array")
    mcu = data.get("mcu", {})
    if not isinstance(mcu, dict):
        raise ValueError("mcu must be an object")
    package_pins = mcu.get("package_pins", [])
    if not isinstance(package_pins, list):
        raise ValueError("mcu.package_pins must be an array")
    package_pins = [text(pin, "mcu.package_pins[]") for pin in package_pins]
    bank_voltages = mcu.get("bank_voltages", {})
    if not isinstance(bank_voltages, dict):
        raise ValueError("mcu.bank_voltages must be an object")
    for bank, voltage in bank_voltages.items():
        text(bank, "mcu.bank_voltages key")
        text(voltage, f"mcu.bank_voltages[{bank}]")

    findings = []

    def add(code, severity, message, where):
        findings.append(
            {"code": code, "severity": severity, "message": message, "where": where}
        )

    missing = defaultdict(list)
    logical_seen = {}
    physical_seen = {}
    pin_roles = {}
    flagged = set()
    if not pins:
        add("NO_PINS", "warning", "pins 为空，没有可检查的引脚", "pins")

    for index, pin in enumerate(pins):
        label = f"pins[{index}]"
        if not isinstance(pin, dict):
            raise ValueError(f"{label}: require object")
        logical = text(pin.get("logical"), f"{label}.logical")
        if logical in logical_seen:
            add(
                "DUP_LOGICAL",
                "blocking",
                f"逻辑资源 {logical} 重复分配，另见 pins[{logical_seen[logical]}]",
                f"{label}.logical",
            )
        else:
            logical_seen[logical] = index
        usage = pin.get("usage")
        if is_unknown(usage):
            missing["usage"].append(logical)
            usage = ""
        else:
            usage = text(usage, f"{label}.usage")

        direction = pin.get("direction")
        if is_unknown(direction):
            missing["direction"].append(logical)
            direction = None
        elif direction not in DIRECTIONS:
            raise ValueError(f"{label}.direction: invalid value {direction!r}")

        physical = pin.get("physical_pin")
        if is_unknown(physical):
            missing["physical_pin"].append(logical)
        else:
            physical = text(physical, f"{label}.physical_pin")
            if physical in physical_seen:
                add(
                    "DUP_PHYSICAL_PIN",
                    "blocking",
                    f"物理脚 {physical} 重复出现：{physical_seen[physical]} 与 {logical}",
                    f"{label}.physical_pin",
                )
            else:
                physical_seen[physical] = logical
            if package_pins and physical not in package_pins:
                add(
                    "UNKNOWN_PHYSICAL_PIN",
                    "blocking",
                    f"物理脚 {physical} 不在已声明的封装脚表中",
                    f"{label}.physical_pin",
                )

        voltage = pin.get("voltage_domain")
        if is_unknown(voltage):
            missing["voltage_domain"].append(logical)
        else:
            voltage = text(voltage, f"{label}.voltage_domain")
        bank = pin.get("bank")
        if is_unknown(bank):
            missing["bank"].append(logical)
        else:
            bank = text(bank, f"{label}.bank")

        if is_unknown(pin.get("reset_state")):
            missing["reset_state"].append(logical)

        boot_sample = pin.get("boot_sample")
        if is_unknown(boot_sample):
            missing["boot_sample"].append(logical)
        elif not isinstance(boot_sample, bool):
            raise ValueError(f"{label}.boot_sample: require boolean or 待查")

        strap = pin.get("strap")
        if is_unknown(strap):
            missing["strap"].append(logical)
            strap_known = None
        elif not isinstance(strap, bool):
            raise ValueError(f"{label}.strap: require boolean or 待查")
        else:
            strap_known = strap
            if strap and not STRAP_ALLOWED.search(usage):
                add(
                    "STRAP_OCCUPIED",
                    "blocking",
                    f"启动 strap 脚 {logical} 被 {usage or '未命名外设'} 占用",
                    f"{label}.strap",
                )
                flagged.add(("STRAP_OCCUPIED", logical))

        debug = pin.get("debug")
        if is_unknown(debug):
            missing["debug"].append(logical)
            debug_known = None
        elif not isinstance(debug, bool):
            raise ValueError(f"{label}.debug: require boolean or 待查")
        else:
            debug_known = debug
            if debug and not DEBUG_ALLOWED.search(usage):
                add(
                    "DEBUG_OCCUPIED",
                    "blocking",
                    f"调试/下载脚 {logical} 被 {usage or '未命名外设'} 占用",
                    f"{label}.debug",
                )
                flagged.add(("DEBUG_OCCUPIED", logical))

        analog_used = pin.get("analog_used")
        if is_unknown(analog_used):
            missing["analog_used"].append(logical)
            analog_known = None
        elif not isinstance(analog_used, bool):
            raise ValueError(f"{label}.analog_used: require boolean or 待查")
        else:
            analog_known = analog_used
            if analog_used and direction == "output":
                add(
                    "ADC_AS_OUTPUT",
                    "blocking",
                    f"{logical} 被同时声明为模拟输入与输出",
                    f"{label}.analog_used",
                )
                flagged.add(("ADC_AS_OUTPUT", logical))

        pin_roles.setdefault(
            logical,
            {
                "direction": direction,
                "strap": strap_known,
                "debug": debug_known,
                "analog_used": analog_known,
            },
        )

        bonded = pin.get("package_bonded")
        if is_unknown(bonded):
            missing["package_bonded"].append(logical)
        elif bonded is False:
            add(
                "PACKAGE_NOT_BONDED",
                "blocking",
                f"{logical} 在封装上未引出",
                f"{label}.package_bonded",
            )
        elif bonded is not True:
            raise ValueError(f"{label}.package_bonded: require boolean or 待查")

        if bank and voltage and bank in bank_voltages and bank_voltages[bank] != voltage:
            add(
                "BANK_VOLTAGE_MISMATCH",
                "blocking",
                f"{logical} 电压域 {voltage} 与 {bank} 的 {bank_voltages[bank]} 不一致",
                f"{label}.voltage_domain",
            )

    for field, labels in missing.items():
        preview = "、".join(labels[:5])
        if len(labels) > 5:
            preview += f" 等 {len(labels)} 个"
        add(
            "MISSING_FIELD",
            "unknown",
            f"{len(labels)} 个引脚未声明 {field}（{preview}）",
            f"pins[].{field}",
        )

    if not package_pins:
        add(
            "UNKNOWN_PACKAGE_PINS",
            "unknown",
            "mcu.package_pins 为空，无法核对物理脚是否存在或已引出",
            "mcu.package_pins",
        )
    if not bank_voltages:
        add(
            "UNKNOWN_BANK_VOLTAGES",
            "unknown",
            "mcu.bank_voltages 为空，无法核对 bank 电压一致性",
            "mcu.bank_voltages",
        )

    resource_ids = set()
    resource_pairs = set()
    resource_missing = defaultdict(list)
    logical_resources = defaultdict(list)
    for index, resource in enumerate(resources):
        label = f"resources[{index}]"
        if not isinstance(resource, dict):
            raise ValueError(f"{label}: require object")
        rid = text(resource.get("id"), f"{label}.id")
        if rid in resource_ids:
            add("DUP_RESOURCE", "blocking", f"资源 ID {rid} 重复", f"{label}.id")
        resource_ids.add(rid)
        kind = resource.get("kind")
        if is_unknown(kind):
            resource_missing["kind"].append(rid)
            kind_value = None
        else:
            kind_value = text(kind, f"{label}.kind").lower()
            if kind_value not in RESOURCE_KINDS:
                raise ValueError(f"{label}.kind: invalid value {kind!r}")
        pin = resource.get("pin")
        if is_unknown(pin):
            add(
                "RESOURCE_PIN_UNKNOWN",
                "unknown",
                f"资源 {rid} 未绑定逻辑脚",
                f"{label}.pin",
            )
        else:
            pin = text(pin, f"{label}.pin")
            if pin not in logical_seen:
                add(
                    "UNKNOWN_RESOURCE_PIN",
                    "blocking",
                    f"资源 {rid} 引用了未声明的逻辑脚 {pin}",
                    f"{label}.pin",
                )
            else:
                logical_resources[pin].append(rid)
                if kind_value is not None:
                    resource_pairs.add((kind_value, pin))
                role = pin_roles.get(pin, {})
                if kind_value is not None:
                    if kind_value == "adc":
                        if role.get("direction") == "output":
                            if ("ADC_AS_OUTPUT", pin) not in flagged:
                                add(
                                    "ADC_AS_OUTPUT",
                                    "blocking",
                                    f"资源 {rid} 把模拟输入分配到输出脚 {pin}",
                                    f"{label}.pin",
                                )
                                flagged.add(("ADC_AS_OUTPUT", pin))
                        elif role.get("analog_used") is False:
                            add(
                                "ADC_NOT_ANALOG",
                                "blocking",
                                f"资源 {rid} 声明为 ADC，但 {pin} 的 analog_used 为 false",
                                f"{label}.pin",
                            )
                    if role.get("strap") is True and not STRAP_ALLOWED.search(
                        f"{rid} {kind_value}"
                    ):
                        if ("STRAP_OCCUPIED", pin) not in flagged:
                            add(
                                "STRAP_OCCUPIED",
                                "blocking",
                                f"启动 strap 脚 {pin} 被资源 {rid}（{kind_value}）占用",
                                f"{label}.pin",
                            )
                            flagged.add(("STRAP_OCCUPIED", pin))
                    if role.get("debug") is True and not DEBUG_ALLOWED.search(
                        f"{rid} {kind_value}"
                    ):
                        if ("DEBUG_OCCUPIED", pin) not in flagged:
                            add(
                                "DEBUG_OCCUPIED",
                                "blocking",
                                f"调试/下载脚 {pin} 被资源 {rid}（{kind_value}）占用",
                                f"{label}.pin",
                            )
                            flagged.add(("DEBUG_OCCUPIED", pin))
    for logical, rids in logical_resources.items():
        unique = sorted(set(rids))
        if len(unique) > 1:
            add(
                "DUPLICATE_RESOURCE_PIN",
                "blocking",
                f"逻辑脚 {logical} 被多个资源占用：{'、'.join(unique)}",
                "resources[].pin",
            )
    for field, ids in resource_missing.items():
        add(
            "MISSING_FIELD",
            "unknown",
            f"{len(ids)} 个资源未声明 {field}（{'、'.join(ids[:5])}）",
            f"resources[].{field}",
        )

    candidate_ids = set()
    for index, candidate in enumerate(candidates):
        label = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            raise ValueError(f"{label}: require object")
        cid = text(candidate.get("id"), f"{label}.id")
        if cid in candidate_ids:
            add("DUP_CANDIDATE", "blocking", f"候选 ID {cid} 重复", f"{label}.id")
        candidate_ids.add(cid)
        status = candidate.get("status")
        if status not in {"deferred", "rejected"}:
            raise ValueError(f"{label}.status: require 'deferred' or 'rejected'")
        ckind = text(candidate.get("kind"), f"{label}.kind").lower()
        if ckind not in RESOURCE_KINDS:
            raise ValueError(f"{label}.kind: invalid value {candidate.get('kind')!r}")
        cpin = candidate.get("pin")
        cpin_value = None
        if not is_unknown(cpin):
            cpin_value = text(cpin, f"{label}.pin")
            if cpin_value not in logical_seen:
                add(
                    "UNKNOWN_CANDIDATE_PIN",
                    "blocking",
                    f"候选 {cid} 引用了未声明的逻辑脚 {cpin_value}",
                    f"{label}.pin",
                )
                cpin_value = None
        if cid in resource_ids:
            add(
                "CANDIDATE_IN_RESOURCES",
                "blocking",
                f"候选 {cid}（status={status}）同时出现在 resources；"
                "resources 只保留最终分配",
                f"{label}.id",
            )
        elif cpin_value is not None and (ckind, cpin_value) in resource_pairs:
            add(
                "CANDIDATE_PIN_ALLOCATED",
                "blocking",
                f"候选 {cid}（status={status}）的 {ckind} 资源已占用逻辑脚 "
                f"{cpin_value}，与 resources 冲突",
                f"{label}.pin",
            )

    for index, item in enumerate(unresolved):
        label = f"unresolved[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label}: require object")
        name = text(item.get("item"), f"{label}.item")
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
    return {
        "schema": RESULT_SCHEMA,
        "status": "needs_review" if findings else "passed",
        "board_verified": False,
        "execution": "OFFLINE_PLANNING",
        "hardware_execution": "NOT RUN",
        "summary": {
            "pins": len(pins),
            "resources": len(resources),
            "candidates": len(candidates),
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
    parser.add_argument("plan", help="pin-plan/v1 JSON file")
    try:
        args = parser.parse_args(argv)
        raw = Path(args.plan).read_text(encoding="utf-8")
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
