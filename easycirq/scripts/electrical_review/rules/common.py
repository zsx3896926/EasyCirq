"""Shared rule helpers.  Everything here is evidence-driven; names never decide."""
from ..contract import (canonical_net, component, connected_pins, pin,
                        role_of_net, same_net)
from ..facts import applicable_facts, fact_evidence
from ..units import display


def component_nets(component_row):
    return [item["net"] for item in connected_pins(component_row)]


def subject(component_row=None, pins=None, nets=None):
    return {
        "components": [component_row["ref"]] if component_row else [],
        "pins": list(pins or []),
        "nets": sorted({net for net in (nets or []) if net is not None}),
    }


def pin_ref(component_row, number):
    return component_row["ref"] + "." + str(number)


def net_voltage_entries(data, net):
    """All declared voltage ranges for one net, from operating conditions first."""
    if net is None:
        return []
    rows = []
    for item in data.get("operating_conditions", {}).get("net_voltages", []):
        if item["net"] == net:
            rows.append(item)
    for item in data.get("intent", {}).get("supplies", []):
        if item["net"] == net:
            rows.append(item)
    return rows


def single_voltage_range(data, net):
    """Return (entry, conflict).  Multiple disagreeing ranges are a conflict."""
    rows = net_voltage_entries(data, net)
    if not rows:
        return None, False
    first = rows[0]
    conflict = any(abs(item["min_v"] - first["min_v"]) > 1e-12 or
                   abs(item["max_v"] - first["max_v"]) > 1e-12 or
                   item.get("kind") != first.get("kind")
                   for item in rows[1:])
    return first, conflict


def ground_partitions(data, component_row):
    """Net alias partitions proven ground by intent or by a device fact."""
    declared = set()
    for net, role in data.get("intent", {}).get("net_roles", {}).items():
        if role == "ground":
            declared.add(canonical_net(data, net))
    for fact, applicability in applicable_facts(data, component_row,
                                                "pin_functions"):
        if applicability.get("package") is False or \
                applicability.get("revision") is False:
            continue
        for pin_number, entry in next(
                item["value"]["pins"] for item in fact["facts"]
                if item["type"] == "pin_functions").items():
            if entry.get("type") != "ground":
                continue
            component_pin = find_pin(component_row, pin_number)
            if component_pin is not None and component_pin["net"] is not None:
                declared.add(canonical_net(data, component_pin["net"]))
    return declared


def power_partitions(data):
    declared = {canonical_net(data, item["net"])
                for item in data.get("intent", {}).get("supplies", [])}
    for net, role in data.get("intent", {}).get("net_roles", {}).items():
        if role == "power":
            declared.add(canonical_net(data, net))
    return declared


def find_pin(component_row, number_or_name):
    """Match a fact pin by number first, then by symbolic pin name."""
    direct = pin(component_row, str(number_or_name))
    if direct is not None:
        return direct
    for item in component_row["pins"]:
        if item["name"] and item["name"].casefold() == \
                str(number_or_name).casefold():
            return item
    return None


def fact_evidence_rows(fact_rows):
    return [fact_evidence(fact) for fact, _value, _applicability in fact_rows]


def voltage_actual(value, basis, unit="V"):
    return {"value": round(float(value), 6),
            "display": display(value, unit),
            "unit": unit, "basis": basis}


def voltage_constraint(value, source, extra=None):
    result = {"value": round(float(value), 6),
              "display": display(value, "V"), "unit": "V",
              "source": source}
    if extra:
        result.update(extra)
    return result


def net_set(data, nets):
    return {canonical_net(data, net) for net in nets if net is not None}


def role_net_entries(data, component_row):
    return data.get("intent", {}).get("capacitor_roles", [])
