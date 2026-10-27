"""Input contract validation and normalisation.

The contract intentionally keeps the schema small: design identity, components
with their physical pin/pad mapping, one connectivity block, and optional
intent / device-fact / operating-condition evidence.  Validation is strict and
never guesses: a malformed or contradictory field is invalid input, not a
finding that could still produce a PASS.
"""
import copy
import re

from . import SCHEMA_INPUT
from .units import (capacitance, display, finite_number, length, resistance,
                    voltage)

SOURCE_TYPES = ("host_export", "manual_declaration", "synthetic_fixture",
                "derived")
EVIDENCE_KINDS = ("host_export", "manual_declaration", "synthetic_fixture",
                  "derived", "vendor_datasheet", "project_policy",
                  "measurement")
COMPONENT_KINDS = ("capacitor", "resistor", "inductor", "diode", "switch",
                   "ic", "connector", "other")
PIN_STATES = ("connected", "nc", "unknown")
GROUP_BEHAVIOURS = ("always_closed", "pressed_closed", "normally_open",
                    "normally_closed")
NET_ROLES = ("power", "ground", "signal", "switching", "unknown")
PIN_ROLES = ("input", "output", "bidirectional", "open_drain", "push_pull",
             "power", "ground", "passive")
CAP_ROLES = ("bulk", "local_decoupling", "filter", "flying", "unknown")
ROLE_SOURCES = ("datasheet", "user_declaration", "project_constraint",
                "derived")
FACT_SOURCE_KINDS = ("datasheet", "erratum", "package_drawing",
                     "project_policy", "synthetic_fixture")
FACT_TYPES = ("capacitor_rated_voltage", "switch_internal_groups",
              "pin_functions", "pad_map", "flying_capacitor")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class InputError(ValueError):
    """Invalid input with a stable location and code for diagnostics."""

    def __init__(self, path, code, message):
        super().__init__("%s: %s" % (path or "$", message))
        self.path = path or "$"
        self.code = code

    def as_dict(self):
        return {"status": "invalid_input", "code": self.code,
                "path": self.path, "error": str(self)}


def _bad(path, code, message):
    raise InputError(path, code, message)


def _object(value, path):
    if not isinstance(value, dict):
        _bad(path, "type", "require object")
    return value


def _list(value, path):
    if not isinstance(value, list):
        _bad(path, "type", "require array")
    return value


def _text(value, path, *, allow_empty=False):
    if not isinstance(value, str):
        _bad(path, "type", "require string")
    if not allow_empty and not value.strip():
        _bad(path, "value", "require nonblank string")
    if value != value.strip():
        _bad(path, "value", "string must not have edge whitespace")
    return value


def _optional_text(value, path):
    if value is None:
        return None
    return _text(value, path)


def _bool(value, path):
    if type(value) is not bool:
        _bad(path, "type", "require boolean")
    return value


def _int(value, path, minimum=None):
    if type(value) is not int:
        _bad(path, "type", "require integer")
    if minimum is not None and value < minimum:
        _bad(path, "value", "must be >= " + str(minimum))
    return value


def _strings(value, path, *, unique=True):
    rows = _list(value, path)
    result = []
    for index, item in enumerate(rows):
        result.append(_text(item, "%s[%d]" % (path, index)))
    if unique and len(set(result)) != len(result):
        _bad(path, "duplicate", "duplicate string values")
    return result


def _evidence_ids(value, path):
    if value is None:
        return []
    return _strings(value, path)


def _hash(value, path):
    text = _text(value, path).lower()
    if not HEX64.match(text):
        _bad(path, "hash", "require 64 lowercase hex characters")
    return text


def _date(value, path):
    text = _text(value, path)
    if not re.match(r"^\d{4}-\d{2}-\d{2}", text):
        _bad(path, "date", "require YYYY-MM-DD...")
    return text


def _net(value, path):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _bad(path, "net", "net must be a nonblank string or null")
    if value != value.strip():
        _bad(path, "net", "net must not have edge whitespace")
    return value


# ---------------------------------------------------------------------------
# design / evidence


def _design(data):
    design = _object(data.get("design"), "design")
    for key in ("project_id", "document_id"):
        _text(design.get(key), "design." + key)
    _optional_text(design.get("title"), "design.title")
    units_raw = _object(design.get("units"), "design.units")
    units = {}
    if "length" not in units_raw or "voltage" not in units_raw:
        _bad("design.units", "missing", "length and voltage units are required")
    for key, table, parser in (
            ("length", ("mm", "mil", "in"), length),
            ("voltage", ("V", "mV"), voltage),
            ("capacitance", None, capacitance),
            ("resistance", None, resistance)):
        if key not in units_raw:
            continue
        unit = _text(units_raw[key], "design.units." + key)
        # A unit parser probe with 1.0 rejects unsupported spellings here.
        try:
            parser(1.0, unit, "design.units." + key)
        except ValueError as error:
            _bad("design.units." + key, "unit", str(error))
        units[key] = unit
    design["units"] = units
    source_type = _text(design.get("source_type"), "design.source_type")
    if source_type not in SOURCE_TYPES:
        _bad("design.source_type", "enum", "unsupported source_type")
    source = design.get("source")
    if source is not None:
        _object(source, "design.source")
        _optional_text(source.get("producer"), "design.source.producer")
        _optional_text(source.get("captured_at"), "design.source.captured_at")
        if source.get("snapshot_sha256") is not None:
            _hash(source["snapshot_sha256"], "design.source.snapshot_sha256")
        _optional_text(source.get("description"), "design.source.description")
    _strings(design.get("notes", []), "design.notes")
    return design


def _evidence(data):
    rows = _list(data.get("evidence", []), "evidence")
    index = {}
    for position, row in enumerate(rows):
        path = "evidence[%d]" % position
        _object(row, path)
        ident = _text(row.get("id"), path + ".id")
        if ident in index:
            _bad(path + ".id", "duplicate", "duplicate evidence id")
        kind = _text(row.get("kind"), path + ".kind")
        if kind not in EVIDENCE_KINDS:
            _bad(path + ".kind", "enum", "unsupported evidence kind")
        _text(row.get("source"), path + ".source")
        _optional_text(row.get("url"), path + ".url")
        _optional_text(row.get("captured_at"), path + ".captured_at")
        if row.get("sha256") is not None:
            _hash(row["sha256"], path + ".sha256")
        _optional_text(row.get("note"), path + ".note")
        index[ident] = row
    data["evidence"] = rows
    return index


# ---------------------------------------------------------------------------
# components / connectivity


def _attributes(raw, path, design):
    attributes = {}
    raw = _object(raw, path) if raw is not None else {}
    if "capacitance" in raw:
        item = _object(raw["capacitance"], path + ".capacitance")
        value = capacitance(item.get("value"), item.get("unit"),
                            path + ".capacitance.value")
        if value <= 0:
            _bad(path + ".capacitance.value", "value", "must be positive")
        attributes["capacitance"] = {
            "value": value, "unit": "F",
            "display": display(item.get("value"), item.get("unit")),
            "evidence": _evidence_ids(item.get("evidence"),
                                      path + ".capacitance.evidence"),
        }
    if "rated_voltage" in raw:
        item = _object(raw["rated_voltage"], path + ".rated_voltage")
        value = voltage(item.get("value"), item.get("unit"),
                        path + ".rated_voltage.value")
        if value <= 0:
            _bad(path + ".rated_voltage.value", "value",
                 "rated voltage must be positive")
        attributes["rated_voltage"] = {
            "value": value, "unit": "V",
            "display": display(item.get("value"), item.get("unit")),
            "conditions": _optional_text(item.get("conditions"),
                                         path + ".rated_voltage.conditions"),
            "evidence": _evidence_ids(item.get("evidence"),
                                      path + ".rated_voltage.evidence"),
        }
    if "resistance" in raw:
        item = _object(raw["resistance"], path + ".resistance")
        value = resistance(item.get("value"), item.get("unit"),
                           path + ".resistance.value")
        if value <= 0:
            _bad(path + ".resistance.value", "value", "must be positive")
        attributes["resistance"] = {
            "value": value, "unit": "ohm",
            "display": display(item.get("value"), item.get("unit")),
            "evidence": _evidence_ids(item.get("evidence"),
                                      path + ".resistance.evidence"),
        }
    if "max_differential_stress" in raw:
        item = _object(raw["max_differential_stress"],
                       path + ".max_differential_stress")
        value = voltage(item.get("value"), item.get("unit"),
                        path + ".max_differential_stress.value")
        if value < 0:
            _bad(path + ".max_differential_stress.value", "value",
                 "stress must be nonnegative")
        attributes["max_differential_stress"] = {
            "value": value, "unit": "V",
            "display": display(item.get("value"), item.get("unit")),
            "basis": _optional_text(item.get("basis"),
                                    path + ".max_differential_stress.basis"),
            "evidence": _evidence_ids(item.get("evidence"),
                                      path + ".max_differential_stress.evidence"),
        }
    unknown = set(raw) - {"capacitance", "rated_voltage", "resistance",
                          "max_differential_stress"}
    if unknown:
        _bad(path, "unknown_field", "unsupported attributes: " +
             ", ".join(sorted(unknown)))
    return attributes


def _position(raw, path, design):
    item = _object(raw, path)
    x = length(item.get("x"), item.get("units") or design["units"]["length"],
               path + ".x")
    y = length(item.get("y"), item.get("units") or design["units"]["length"],
               path + ".y")
    return {"x": x, "y": y, "unit": "mm"}


def _pins(raw, path, design):
    rows = _list(raw, path)
    if not rows:
        _bad(path, "empty", "component must declare at least one pin")
    result = []
    numbers = set()
    for index, row in enumerate(rows):
        sub = "%s[%d]" % (path, index)
        _object(row, sub)
        number = _text(row.get("number"), sub + ".number")
        if number in numbers:
            _bad(sub + ".number", "duplicate", "duplicate pin number")
        numbers.add(number)
        pin = {"number": number,
               "name": _optional_text(row.get("name"), sub + ".name"),
               "net": _net(row.get("net"), sub + ".net"),
               "no_connect": _bool(row.get("no_connect", False),
                                   sub + ".no_connect"),
               "state": _optional_text(row.get("state"), sub + ".state"),
               "pads": _strings(row.get("pads", []), sub + ".pads"),
               "pad_nets": {},
               "position": None}
        if pin["state"] and pin["state"] not in PIN_STATES:
            _bad(sub + ".state", "enum", "unsupported pin state")
        if pin["no_connect"] and pin["net"] is not None:
            _bad(sub, "contradiction",
                 "pin cannot be both NC and connected to a net")
        if row.get("pad_nets") is not None:
            pad_nets = _object(row["pad_nets"], sub + ".pad_nets")
            for pad, net in pad_nets.items():
                _text(pad, sub + ".pad_nets key")
                if pad not in pin["pads"]:
                    _bad(sub + ".pad_nets", "unknown_pad",
                         "pad is not listed in pads: " + pad)
                pin["pad_nets"][pad] = _net(net, sub + ".pad_nets." + pad)
        if row.get("position") is not None:
            pin["position"] = _position(row["position"], sub + ".position",
                                        design)
        result.append(pin)
    for index, pin in enumerate(result):
        for pad in pin["pads"]:
            for other in result[index + 1:]:
                if pad in other["pads"]:
                    _bad(path, "duplicate_pad",
                         "pad %s mapped to pins %s and %s"
                         % (pad, pin["number"], other["number"]))
    return result


def _groups(raw, path, pins):
    rows = _list(raw, path)
    numbers = {pin["number"] for pin in pins}
    result = []
    for index, row in enumerate(rows):
        sub = "%s[%d]" % (path, index)
        _object(row, sub)
        members = _strings(row.get("pins"), sub + ".pins")
        if len(members) < 2:
            _bad(sub + ".pins", "value", "internal group needs >= 2 pins")
        missing = [member for member in members if member not in numbers]
        if missing:
            _bad(sub + ".pins", "unknown_pin",
                 "pins not declared on component: " + ", ".join(missing))
        behaviour = _text(row.get("behavior"), sub + ".behavior")
        if behaviour not in GROUP_BEHAVIOURS:
            _bad(sub + ".behavior", "enum", "unsupported group behaviour")
        result.append({"pins": members, "behavior": behaviour,
                       "evidence": _evidence_ids(row.get("evidence"),
                                                 sub + ".evidence")})
    return result


def _components(data, design):
    rows = _list(data.get("components"), "components")
    if not rows:
        _bad("components", "empty", "at least one component is required")
    result = []
    instance_ids = set()
    refs = set()
    for index, row in enumerate(rows):
        path = "components[%d]" % index
        _object(row, path)
        instance_id = _text(row.get("instance_id"), path + ".instance_id")
        ref = _text(row.get("ref"), path + ".ref")
        if instance_id in instance_ids:
            _bad(path + ".instance_id", "duplicate",
                 "duplicate instance_id (same id for different objects)")
        if ref in refs:
            _bad(path + ".ref", "duplicate", "duplicate designator")
        instance_ids.add(instance_id)
        refs.add(ref)
        kind = _text(row.get("kind", "other"), path + ".kind")
        if kind not in COMPONENT_KINDS:
            _bad(path + ".kind", "enum", "unsupported component kind")
        mpn = row.get("mpn")
        if mpn is not None:
            mpn = _text(mpn, path + ".mpn")
        status = row.get("mpn_status")
        if status is None:
            status = "exact" if mpn else "unknown"
        if status not in ("exact", "unknown"):
            _bad(path + ".mpn_status", "enum", "unsupported mpn_status")
        if status == "exact" and not mpn:
            _bad(path, "contradiction", "exact mpn requires mpn")
        component = {
            "instance_id": instance_id,
            "ref": ref,
            "kind": kind,
            "mpn": mpn,
            "mpn_status": status,
            "manufacturer": _optional_text(row.get("manufacturer"),
                                           path + ".manufacturer"),
            "revision": _optional_text(row.get("revision"), path + ".revision"),
            "value": _optional_text(row.get("value"), path + ".value"),
            "attributes": _attributes(row.get("attributes"), path + ".attributes",
                                      design),
            "pins": _pins(row.get("pins"), path + ".pins", design),
            "mapping_complete": _bool(row.get("mapping_complete", False),
                                      path + ".mapping_complete"),
            "footprint": None,
            "placement": None,
            "internal_groups": [],
            "evidence": _evidence_ids(row.get("evidence"),
                                      path + ".evidence"),
        }
        footprint = row.get("footprint")
        if footprint is not None:
            _object(footprint, path + ".footprint")
            component["footprint"] = {
                "name": _text(footprint.get("name"),
                              path + ".footprint.name"),
                "evidence": _evidence_ids(footprint.get("evidence"),
                                          path + ".footprint.evidence"),
            }
        if row.get("placement") is not None:
            placement = _object(row["placement"], path + ".placement")
            component["placement"] = _position(placement, path + ".placement",
                                               design)
            if placement.get("rotation") is not None:
                component["placement"]["rotation"] = finite_number(
                    placement["rotation"], path + ".placement.rotation")
        result.append(component)
    # Second pass: re-run internal groups against the stored pins so the
    # normalised component (not a throwaway copy) is used.
    for index, row in enumerate(rows):
        if row.get("internal_groups"):
            result[index]["internal_groups"] = _groups(
                row["internal_groups"], "components[%d].internal_groups" % index,
                result[index]["pins"])
    data["components"] = result
    return result


def _pins_normalized(raw, path, design):
    return _pins(raw, path + ".pins", design)


def _find_component(components, key, path):
    for component in components:
        if component["instance_id"] == key or component["ref"] == key:
            return component
    _bad(path, "unknown_component", "unknown component: " + str(key))


def _merge_pin_nets(data, components):
    by_owner = {}
    for component in components:
        by_owner[component["instance_id"]] = component
        by_owner[component["ref"]] = component
    connectivity = _object(data.get("connectivity", {}), "connectivity")
    pin_nets = connectivity.get("pin_nets", {})
    if pin_nets is not None:
        _object(pin_nets, "connectivity.pin_nets")
        for key, net in pin_nets.items():
            _text(key, "connectivity.pin_nets key")
            if "." not in key:
                _bad("connectivity.pin_nets." + key, "syntax",
                     "require <ref>.<pin>")
            owner, number = key.rsplit(".", 1)
            component = by_owner.get(owner)
            if component is None:
                _bad("connectivity.pin_nets." + key, "unknown_component",
                     "unknown component: " + owner)
            pin = None
            for candidate in component["pins"]:
                if candidate["number"] == number:
                    pin = candidate
                    break
            if pin is None:
                _bad("connectivity.pin_nets." + key, "unknown_pin",
                     "unknown pin on component: " + number)
            declared = _net(net, "connectivity.pin_nets." + key)
            if pin["net"] is not None and declared is not None and \
                    pin["net"] != declared:
                _bad("connectivity.pin_nets." + key, "contradiction",
                     "inline pin net contradicts connectivity.pin_nets")
            if declared is not None:
                pin["net"] = declared
    connectivity["pin_nets"] = pin_nets or {}
    # Internal groups may also be supplied in the connectivity block.
    groups = connectivity.get("internal_groups", [])
    for index, row in enumerate(_list(groups, "connectivity.internal_groups")):
        path = "connectivity.internal_groups[%d]" % index
        _object(row, path)
        component = _find_component(components, row.get("component"),
                                    path + ".component")
        members = _strings(row.get("pins"), path + ".pins")
        numbers = {pin["number"] for pin in component["pins"]}
        missing = [member for member in members if member not in numbers]
        if missing:
            _bad(path + ".pins", "unknown_pin",
                 "pins not declared on component: " + ", ".join(missing))
        behaviour = _text(row.get("behavior"), path + ".behavior")
        if behaviour not in GROUP_BEHAVIOURS:
            _bad(path + ".behavior", "enum", "unsupported group behaviour")
        existing = [group for group in component["internal_groups"]
                    if set(group["pins"]) == set(members)]
        if existing and existing[0]["behavior"] != behaviour:
            _bad(path, "contradiction",
                 "internal group behaviour contradicts component block")
        if not existing:
            component["internal_groups"].append({
                "pins": members, "behavior": behaviour,
                "evidence": _evidence_ids(row.get("evidence"),
                                          path + ".evidence")})
    aliases = connectivity.get("net_aliases", [])
    for index, pair in enumerate(_list(aliases, "connectivity.net_aliases")):
        path = "connectivity.net_aliases[%d]" % index
        if not isinstance(pair, list) or len(pair) != 2:
            _bad(path, "shape", "require [net_a, net_b]")
        left = _net(pair[0], path + "[0]")
        right = _net(pair[1], path + "[1]")
        if left is None or right is None:
            _bad(path, "net", "alias pair requires two non-null nets")
        if left == right:
            _bad(path, "value", "alias pair must name two different nets")
    measurement = connectivity.get("measurement")
    if measurement is not None:
        _object(measurement, "connectivity.measurement")
        if "available" in measurement:
            _bool(measurement["available"],
                  "connectivity.measurement.available")
        _optional_text(measurement.get("source"),
                       "connectivity.measurement.source")
        _strings(measurement.get("gaps", []),
                 "connectivity.measurement.gaps")
    coverage = connectivity.get("coverage")
    if coverage is not None:
        _object(coverage, "connectivity.coverage")
        if "complete" in coverage:
            _bool(coverage["complete"], "connectivity.coverage.complete")
        _strings(coverage.get("notes", []), "connectivity.coverage.notes")
    connectivity["net_aliases"] = aliases
    data["connectivity"] = connectivity
    data["_meta"] = {
        "measurement": measurement or {"available": False},
        "net_alias_groups": _alias_groups(aliases),
    }


def _alias_groups(aliases):
    parent = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            if left_root < right_root:
                parent[right_root] = left_root
            else:
                parent[left_root] = right_root

    for left, right in aliases:
        union(left, right)
    return {name: find(name) for name in list(parent)}


# ---------------------------------------------------------------------------
# intent


def _resolve_component(components, value, path):
    if not isinstance(value, str) or not value.strip():
        _bad(path, "component", "component instance_id/ref required")
    return _find_component(components, value, path)


def _evidence_or_fact(value, path):
    return _evidence_ids(value, path)


def _intent(data, components):
    raw = data.get("intent")
    data["_meta"]["intent_supplied"] = raw is not None
    if raw is None:
        return {}
    raw = _object(raw, "intent")
    intent = {"source": _optional_text(raw.get("source"), "intent.source")}
    supplies = []
    for index, row in enumerate(_list(raw.get("supplies", []),
                                      "intent.supplies")):
        path = "intent.supplies[%d]" % index
        _object(row, path)
        net = _net(row.get("net"), path + ".net")
        if net is None:
            _bad(path + ".net", "net", "supply net required")
        low = voltage(row.get("min_v"), row.get("unit") or
                      data["design"]["units"]["voltage"], path + ".min_v")
        high = voltage(row.get("max_v"), row.get("unit") or
                       data["design"]["units"]["voltage"], path + ".max_v")
        if low > high:
            _bad(path, "range", "min_v must be <= max_v")
        entry = {"net": net, "min_v": low, "max_v": high, "unit": "V",
                 "kind": _optional_text(row.get("kind"), path + ".kind")
                 or "unknown",
                 "evidence": _evidence_ids(row.get("evidence"),
                                           path + ".evidence")}
        if entry["kind"] not in ("dc", "ac", "switching", "unknown"):
            _bad(path + ".kind", "enum", "unsupported voltage kind")
        if row.get("nominal_v") is not None:
            entry["nominal_v"] = voltage(row["nominal_v"],
                                          row.get("unit") or
                                          data["design"]["units"]["voltage"],
                                          path + ".nominal_v")
        supplies.append(entry)
    intent["supplies"] = supplies
    roles = {}
    for net, role in _object(raw.get("net_roles", {}),
                             "intent.net_roles").items():
        _net(net, "intent.net_roles net")
        role = _text(role, "intent.net_roles." + net)
        if role not in NET_ROLES:
            _bad("intent.net_roles." + net, "enum", "unsupported net role")
        roles[net] = role
    intent["net_roles"] = roles
    caps = []
    for index, row in enumerate(_list(raw.get("capacitor_roles", []),
                                      "intent.capacitor_roles")):
        path = "intent.capacitor_roles[%d]" % index
        _object(row, path)
        component = _resolve_component(components, row.get("component"),
                                       path + ".component")
        role = _text(row.get("role"), path + ".role")
        if role not in CAP_ROLES:
            _bad(path + ".role", "enum", "unsupported capacitor role")
        role_source = _text(row.get("role_source"), path + ".role_source")
        if role_source not in ROLE_SOURCES:
            _bad(path + ".role_source", "enum", "unsupported role source")
        terminals = []
        for terminal_index, terminal in enumerate(_list(
                row.get("expected_terminals", []),
                path + ".expected_terminals")):
            sub = "%s.expected_terminals[%d]" % (path, terminal_index)
            _object(terminal, sub)
            pin = _text(terminal.get("pin"), sub + ".pin")
            if not any(item["number"] == pin for item in component["pins"]):
                _bad(sub + ".pin", "unknown_pin", "unknown pin: " + pin)
            net = _net(terminal.get("net"), sub + ".net")
            if net is None:
                _bad(sub + ".net", "net", "expected terminal net required")
            terminals.append({"pin": pin, "net": net})
        entry = {"component": component["instance_id"], "role": role,
                 "role_source": role_source, "expected_terminals": terminals,
                 "evidence": _evidence_ids(row.get("evidence"),
                                           path + ".evidence"),
                 "fact_ids": _strings(row.get("fact_ids", []),
                                      path + ".fact_ids")}
        target = row.get("target")
        if target is not None:
            _object(target, path + ".target")
            entry["target"] = {
                "component": _resolve_component(components,
                                                target.get("component"),
                                                path + ".target.component")["instance_id"],
                "pins": _strings(target.get("pins", []),
                                 path + ".target.pins"),
                "basis": _optional_text(target.get("basis"),
                                        path + ".target.basis"),
            }
        caps.append(entry)
    intent["capacitor_roles"] = caps
    switches = []
    for index, row in enumerate(_list(raw.get("switch_requirements", []),
                                      "intent.switch_requirements")):
        path = "intent.switch_requirements[%d]" % index
        _object(row, path)
        component = _resolve_component(components, row.get("component"),
                                       path + ".component")
        used = _strings(row.get("used_pins", []), path + ".used_pins")
        numbers = {pin["number"] for pin in component["pins"]}
        missing = [pin for pin in used if pin not in numbers]
        if missing:
            _bad(path + ".used_pins", "unknown_pin",
                 "unknown pins: " + ", ".join(missing))
        entry = {"component": component["instance_id"],
                 "function": _optional_text(row.get("function"),
                                            path + ".function"),
                 "used_pins": used,
                 "pressed_connection": None,
                 "forbidden_pressed_nets": [],
                 "evidence": _evidence_ids(row.get("evidence"),
                                           path + ".evidence"),
                 "fact_ids": _strings(row.get("fact_ids", []),
                                      path + ".fact_ids")}
        if row.get("pressed_connection") is not None:
            pair = _strings(row["pressed_connection"],
                            path + ".pressed_connection")
            if len(pair) != 2:
                _bad(path + ".pressed_connection", "shape",
                     "pressed_connection requires two pins")
            missing = [pin for pin in pair if pin not in numbers]
            if missing:
                _bad(path + ".pressed_connection", "unknown_pin",
                     "unknown pins: " + ", ".join(missing))
            entry["pressed_connection"] = pair
        for pair_index, pair in enumerate(_list(
                row.get("forbidden_pressed_nets", []),
                path + ".forbidden_pressed_nets")):
            sub = "%s.forbidden_pressed_nets[%d]" % (path, pair_index)
            pair = _strings(pair, sub)
            if len(pair) != 2:
                _bad(sub, "shape", "require two nets")
            entry["forbidden_pressed_nets"].append(pair)
        switches.append(entry)
    intent["switch_requirements"] = switches
    pin_roles = []
    for index, row in enumerate(_list(raw.get("pin_roles", []),
                                      "intent.pin_roles")):
        path = "intent.pin_roles[%d]" % index
        _object(row, path)
        component = _resolve_component(components, row.get("component"),
                                       path + ".component")
        pin = _text(row.get("pin"), path + ".pin")
        if not any(item["number"] == pin for item in component["pins"]):
            _bad(path + ".pin", "unknown_pin", "unknown pin: " + pin)
        role = _text(row.get("role"), path + ".role")
        if role not in PIN_ROLES:
            _bad(path + ".role", "enum", "unsupported pin role")
        pin_roles.append({"component": component["instance_id"], "pin": pin,
                          "role": role,
                          "evidence": _evidence_ids(row.get("evidence"),
                                                    path + ".evidence")})
    intent["pin_roles"] = pin_roles
    constraints = []
    for index, row in enumerate(_list(raw.get("decoupling_targets", []),
                                      "intent.decoupling_targets")):
        path = "intent.decoupling_targets[%d]" % index
        _object(row, path)
        cap = _resolve_component(components, row.get("capacitor"),
                                 path + ".capacitor")
        target = _resolve_component(components, row.get("target_component"),
                                    path + ".target_component")
        maximum = _object(row.get("max_distance"), path + ".max_distance")
        value = length(maximum.get("value"), maximum.get("unit"),
                       path + ".max_distance.value")
        if value <= 0:
            _bad(path + ".max_distance.value", "value",
                 "distance must be positive")
        basis = _optional_text(row.get("basis"), path + ".basis") or \
            "euclidean_proxy"
        constraints.append({
            "capacitor": cap["instance_id"],
            "target_component": target["instance_id"],
            "target_pins": _strings(row.get("target_pins", []),
                                    path + ".target_pins"),
            "max_distance": {"value": value, "unit": "mm",
                             "display": display(maximum.get("value"),
                                                maximum.get("unit")),
                             "original_value": finite_number(
                                 maximum.get("value"),
                                 path + ".max_distance.value"),
                             "original_unit": _text(maximum.get("unit"),
                                                    path + ".max_distance.unit")},
            "basis": basis,
            "source": _optional_text(row.get("source"), path + ".source"),
            "evidence": _evidence_ids(row.get("evidence"),
                                      path + ".evidence")})
    intent["decoupling_targets"] = constraints
    derating = raw.get("derating")
    if derating is not None:
        derating = _object(derating, "intent.derating")
        fraction = finite_number(derating.get("max_voltage_fraction"),
                                 "intent.derating.max_voltage_fraction")
        if not 0 < fraction <= 1:
            _bad("intent.derating.max_voltage_fraction", "range",
                 "must be in (0, 1]")
        intent["derating"] = {
            "max_voltage_fraction": fraction,
            "source": _optional_text(derating.get("source"),
                                     "intent.derating.source"),
            "evidence": _evidence_ids(derating.get("evidence"),
                                      "intent.derating.evidence"),
        }
    intent["assumptions"] = _strings(raw.get("assumptions", []),
                                     "intent.assumptions")
    intent["evidence"] = _evidence_ids(raw.get("evidence"),
                                       "intent.evidence")
    data["intent"] = intent
    return intent


# ---------------------------------------------------------------------------
# device facts


def _fact_value(fact_type, value, path, design):
    value = _object(value, path)
    if fact_type == "capacitor_rated_voltage":
        rated = voltage(value.get("value"), value.get("unit"),
                        path + ".value")
        if rated <= 0:
            _bad(path + ".value", "value", "must be positive")
        return {"voltage": rated, "unit": "V",
                "display": display(value.get("value"), value.get("unit")),
                "conditions": _optional_text(value.get("conditions"),
                                             path + ".conditions")}
    if fact_type == "switch_internal_groups":
        groups = []
        for index, group in enumerate(_list(value.get("always_closed_groups",
                                                      []),
                                            path + ".always_closed_groups")):
            groups.append(_strings(group, "%s.always_closed_groups[%d]"
                                   % (path, index)))
        pressed = []
        for index, pair in enumerate(_list(value.get("pressed_closes", []),
                                           path + ".pressed_closes")):
            pair = _strings(pair, "%s.pressed_closes[%d]" % (path, index))
            if len(pair) != 2:
                _bad(path + ".pressed_closes", "shape",
                     "pressed pair requires two pins")
            pressed.append(pair)
        if not groups:
            _bad(path + ".always_closed_groups", "missing",
                 "at least one always-closed group is required")
        return {"always_closed_groups": groups,
                "pressed_closes": pressed,
                "pressed_connects_groups": (
                    _bool(value["pressed_connects_groups"],
                          path + ".pressed_connects_groups")
                    if value.get("pressed_connects_groups") is not None
                    else None),
                "terminal_numbering": _optional_text(
                    value.get("terminal_numbering"),
                    path + ".terminal_numbering"),
                "note": _optional_text(value.get("note"), path + ".note")}
    if fact_type == "pin_functions":
        pins = {}
        for number, item in _object(value.get("pins", {}),
                                    path + ".pins").items():
            sub = path + ".pins." + str(number)
            item = _object(item, sub)
            kind = _text(item.get("type"), sub + ".type")
            if kind not in ("input", "output", "bidirectional", "open_drain",
                            "power", "ground", "passive"):
                _bad(sub + ".type", "enum", "unsupported pin type")
            entry = {"type": kind,
                     "name": _optional_text(item.get("name"), sub + ".name")}
            if item.get("max_v") is not None:
                entry["max_v"] = voltage(item["max_v"],
                                         item.get("unit") or
                                         design["units"]["voltage"],
                                         sub + ".max_v")
            if item.get("min_v") is not None:
                entry["min_v"] = voltage(item["min_v"],
                                         item.get("unit") or
                                         design["units"]["voltage"],
                                         sub + ".min_v")
            pins[str(number)] = entry
        if not pins:
            _bad(path + ".pins", "empty", "pin functions required")
        result = {"pins": pins}
        if value.get("supply") is not None:
            supply = _object(value["supply"], path + ".supply")
            low = voltage(supply.get("min_v"), supply.get("unit") or
                          design["units"]["voltage"], path + ".supply.min_v")
            high = voltage(supply.get("max_v"), supply.get("unit") or
                           design["units"]["voltage"], path + ".supply.max_v")
            if low > high:
                _bad(path + ".supply", "range", "min_v must be <= max_v")
            result["supply"] = {"min_v": low, "max_v": high, "unit": "V",
                                "conditions": _optional_text(
                                    supply.get("conditions"),
                                    path + ".supply.conditions")}
        return result
    if fact_type == "pad_map":
        pins = []
        seen = set()
        for index, row in enumerate(_list(value.get("pins"),
                                          path + ".pins")):
            sub = "%s.pins[%d]" % (path, index)
            row = _object(row, sub)
            pin = _text(row.get("pin"), sub + ".pin")
            if pin in seen:
                _bad(sub + ".pin", "duplicate", "duplicate logical pin")
            seen.add(pin)
            entry = {"pin": pin,
                     "name": _optional_text(row.get("name"), sub + ".name"),
                     "pads": _strings(row.get("pads"), sub + ".pads"),
                     "required": _bool(row.get("required", True),
                                       sub + ".required"),
                     "required_net_role": _optional_text(
                         row.get("required_net_role"),
                         sub + ".required_net_role"),
                     "tie_to_pin": _optional_text(row.get("tie_to_pin"),
                                                  sub + ".tie_to_pin"),
                     "note": _optional_text(row.get("note"), sub + ".note")}
            if entry["required_net_role"] is not None and \
                    entry["required_net_role"] not in NET_ROLES:
                _bad(sub + ".required_net_role", "enum",
                     "unsupported required net role")
            pins.append(entry)
        if not pins:
            _bad(path + ".pins", "empty", "pad map pins required")
        return {"pins": pins,
                "package": _optional_text(value.get("package"),
                                          path + ".package"),
                "notes": _strings(value.get("notes", []), path + ".notes")}
    if fact_type == "flying_capacitor":
        pins = _object(value.get("pins"), path + ".pins")
        return {"pins": {str(key): _text(item, path + ".pins." + str(key))
                         for key, item in pins.items()},
                "expected_nets": _strings(value.get("expected_nets", []),
                                          path + ".expected_nets"),
                "note": _optional_text(value.get("note"), path + ".note")}
    return value


def _device_facts(data):
    raw = data.get("device_facts", [])
    rows = _list(raw, "device_facts")
    result = []
    seen = set()
    for index, row in enumerate(rows):
        path = "device_facts[%d]" % index
        _object(row, path)
        fact_id = _text(row.get("fact_id"), path + ".fact_id")
        if fact_id in seen:
            _bad(path + ".fact_id", "duplicate", "duplicate fact_id")
        seen.add(fact_id)
        source = _object(row.get("source"), path + ".source")
        kind = _text(source.get("kind"), path + ".source.kind")
        if kind not in FACT_SOURCE_KINDS:
            _bad(path + ".source.kind", "enum", "unsupported source kind")
        url = _optional_text(source.get("url"), path + ".source.url")
        if kind in ("datasheet", "erratum", "package_drawing") and not url:
            _bad(path + ".source.url", "missing",
                 "first-party source requires a URL")
        entry = {
            "fact_id": fact_id,
            "mpn": _text(row.get("mpn"), path + ".mpn"),
            "manufacturer": _optional_text(row.get("manufacturer"),
                                           path + ".manufacturer"),
            "package": _optional_text(row.get("package"), path + ".package"),
            "revision": _optional_text(row.get("revision"),
                                       path + ".revision"),
            "source": {"kind": kind, "url": url,
                       "revision": _optional_text(source.get("revision"),
                                                  path + ".source.revision"),
                       "retrieved_at": _optional_text(
                           source.get("retrieved_at"),
                           path + ".source.retrieved_at"),
                       "pages": _optional_text(source.get("pages"),
                                               path + ".source.pages"),
                       "table": _optional_text(source.get("table"),
                                               path + ".source.table"),
                       "sha256": _hash(source["sha256"],
                                       path + ".source.sha256")
                       if source.get("sha256") else None},
            "applies_to": {"mpn": _strings(
                _object(row.get("applies_to", {}),
                        path + ".applies_to").get("mpn", []),
                path + ".applies_to.mpn")},
            "facts": [],
        }
        applies = _object(row.get("applies_to", {}), path + ".applies_to")
        entry["applies_to"] = {
            "mpn": _strings(applies.get("mpn", []),
                            path + ".applies_to.mpn"),
            "packages": _strings(applies.get("packages", []),
                                 path + ".applies_to.packages"),
            "revisions": _strings(applies.get("revisions", []),
                                  path + ".applies_to.revisions"),
        }
        for fact_index, fact in enumerate(_list(row.get("facts"),
                                                path + ".facts")):
            sub = "%s.facts[%d]" % (path, fact_index)
            fact = _object(fact, sub)
            fact_type = _text(fact.get("type"), sub + ".type")
            if fact_type not in FACT_TYPES:
                _bad(sub + ".type", "enum",
                     "unsupported device fact type (not silently ignored)")
            entry["facts"].append({
                "type": fact_type,
                "value": _fact_value(fact_type, fact.get("value"), sub + ".value",
                                     data["design"]),
            })
        if not entry["facts"]:
            _bad(path + ".facts", "empty", "at least one fact is required")
        result.append(entry)
    data["device_facts"] = result
    return result


# ---------------------------------------------------------------------------
# operating conditions


def _operating_conditions(data):
    raw = data.get("operating_conditions")
    if raw is None:
        return {}
    raw = _object(raw, "operating_conditions")
    conditions = {"net_voltages": [], "ambient": None,
                  "notes": _strings(raw.get("notes", []),
                                    "operating_conditions.notes")}
    for index, row in enumerate(_list(raw.get("net_voltages", []),
                                      "operating_conditions.net_voltages")):
        path = "operating_conditions.net_voltages[%d]" % index
        _object(row, path)
        net = _net(row.get("net"), path + ".net")
        if net is None:
            _bad(path + ".net", "net", "net required")
        low = voltage(row.get("min_v"), row.get("unit") or
                      data["design"]["units"]["voltage"], path + ".min_v")
        high = voltage(row.get("max_v"), row.get("unit") or
                       data["design"]["units"]["voltage"], path + ".max_v")
        if low > high:
            _bad(path, "range", "min_v must be <= max_v")
        kind = _optional_text(row.get("kind"), path + ".kind") or "unknown"
        if kind not in ("dc", "ac", "switching", "unknown"):
            _bad(path + ".kind", "enum", "unsupported voltage kind")
        conditions["net_voltages"].append({
            "net": net, "min_v": low, "max_v": high, "unit": "V",
            "kind": kind,
            "evidence": _evidence_ids(row.get("evidence"),
                                      path + ".evidence")})
    ambient = raw.get("ambient")
    if ambient is not None:
        ambient = _object(ambient, "operating_conditions.ambient")
        low = finite_number(ambient.get("min_c"),
                            "operating_conditions.ambient.min_c")
        high = finite_number(ambient.get("max_c"),
                             "operating_conditions.ambient.max_c")
        if low > high:
            _bad("operating_conditions.ambient", "range",
                 "min_c must be <= max_c")
        conditions["ambient"] = {"min_c": low, "max_c": high}
    data["operating_conditions"] = conditions
    return conditions


# ---------------------------------------------------------------------------
# entry point


def validate(data):
    """Validate and normalise one input document.  Raises InputError."""
    try:
        return _validate(data)
    except InputError:
        raise
    except ValueError as error:
        raise InputError("$", "invalid_value", str(error))


def _validate(data):
    data = _object(data, "$")
    schema = data.get("schema")
    if schema != SCHEMA_INPUT:
        _bad("schema", "unsupported",
             "require schema %r" % SCHEMA_INPUT)
    design = _design(data)
    _evidence(data)
    components = _components(data, design)
    if data.get("connectivity") is None:
        _bad("connectivity", "missing", "connectivity object is required")
    _merge_pin_nets(data, components)
    _intent(data, components)
    _device_facts(data)
    _operating_conditions(data)
    data["_meta"]["component_by_ref"] = {item["ref"]: item["instance_id"]
                                         for item in components}
    _validate_references(data)
    return data


def _validate_references(data):
    """Every evidence/fact_id reference must resolve; dangling proof is invalid."""
    evidence_ids = {item["id"] for item in data.get("evidence", [])}
    fact_ids = {item["fact_id"] for item in data.get("device_facts", [])}

    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                child = path + "." + str(key)
                if key == "evidence" and isinstance(item, list):
                    for index, ident in enumerate(item):
                        if isinstance(ident, dict):
                            # Top-level evidence definitions, not references.
                            continue
                        if not isinstance(ident, str):
                            _bad(child + "[%d]" % index, "unknown_evidence",
                                 "evidence reference must be a string id")
                        if ident not in evidence_ids:
                            _bad(child + "[%d]" % index, "unknown_evidence",
                                 "evidence id does not exist: " + str(ident))
                elif key == "fact_ids" and isinstance(item, list):
                    for index, ident in enumerate(item):
                        if not isinstance(ident, str):
                            _bad(child + "[%d]" % index, "unknown_fact",
                                 "fact reference must be a string id")
                        if ident not in fact_ids:
                            _bad(child + "[%d]" % index, "unknown_fact",
                                 "device fact id does not exist: " + str(ident))
                else:
                    walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + "[%d]" % index)

    walk(data, "$")


def canonical_net(data, net):
    """Return the alias-group root for a declared net (or None)."""
    if net is None:
        return None
    return data["_meta"]["net_alias_groups"].get(net, net)


def same_net(data, left, right):
    if left is None or right is None:
        return None
    return canonical_net(data, left) == canonical_net(data, right)


def component(data, key):
    for item in data["components"]:
        if item["instance_id"] == key or item["ref"] == key:
            return item
    return None


def pin(component_row, number):
    for item in component_row["pins"]:
        if item["number"] == number:
            return item
    return None


def connected_pins(component_row):
    return [item for item in component_row["pins"]
            if item["net"] is not None and not item["no_connect"]]


def evidence_by_id(data, ident):
    for item in data.get("evidence", []):
        if item["id"] == ident:
            return item
    return None


def role_of_net(data, net):
    """Declared role only; never inferred from a net name."""
    if net is None:
        return None
    return data.get("intent", {}).get("net_roles", {}).get(net)


def series_rows(data, object_id):
    """Return components whose pins all touch one of the two given nets.

    Used only to detect an explicit series element for switch-to-rail checks;
    not a general analogue solver.
    """
    if len(object_id) != 2:
        return []
    left = set()
    right = set()
    for component_row in data["components"]:
        nets = [item["net"] for item in connected_pins(component_row)]
        if object_id[0] in nets:
            left.add(component_row["instance_id"])
        if object_id[1] in nets:
            right.add(component_row["instance_id"])
    return sorted(left & right)


def clone(data):
    return copy.deepcopy(data)
