"""Frozen fixture builders shared by unit tests and the benchmark generator.

Synthetic inputs are explicitly marked ``synthetic_fixture``.  Device facts are
real first-party datasheet excerpts with source URL, revision, page/table and
the SHA-256 of the PDF examined on 2026-10-27; every fact carries the exact MPN
and package it applies to.  Switching examples use the verified four-terminal
tactile-switch structure documented in docs/parallel-electrical-review/sources.md.
"""
import copy

INCH = 0.0254


def evidence(ident="E1", kind="synthetic_fixture", source="task-B synthetic fixture"):
    return {"id": ident, "kind": kind, "source": source}


def pin(number, net=None, **extra):
    row = {"number": str(number)}
    if net is not None:
        row["net"] = net
    row.update(extra)
    return row


def component(ident, ref, kind, mpn=None, pins=None, **extra):
    row = {"instance_id": ident, "ref": ref, "kind": kind, "pins": pins or []}
    if mpn is not None:
        row["mpn"] = mpn
    row.update(extra)
    return row


def design(project="bench", document="P1"):
    return {
        "project_id": project,
        "document_id": document,
        "units": {"length": "mil", "voltage": "V", "capacitance": "uF"},
        "source_type": "synthetic_fixture",
        "title": "electrical-review benchmark fixture",
    }


TI_MAX3232 = {
    "fact_id": "F-MAX3232",
    "mpn": "MAX3232IDR",
    "manufacturer": "Texas Instruments",
    "package": "SOIC-16 (D)",
    "revision": "SLLS410O",
    "source": {
        "kind": "datasheet",
        "url": "https://www.ti.com/lit/ds/symlink/max3232.pdf",
        "revision": "SLLS410O (JANUARY 2000 - REVISED JUNE 2021)",
        "retrieved_at": "2026-10-27",
        "pages": "3, 4",
        "table": "Table 5-1 Pin Functions; section 6.3 Recommended Operating Conditions",
        "sha256": "f8497fd138dd31accec7a08d77d79218dd982325eb2d985fd04b3f6573818849",
    },
    "applies_to": {"mpn": ["MAX3232IDR"], "packages": ["SOIC-16"],
                   "revisions": []},
    "facts": [
        {
            "type": "flying_capacitor",
            "value": {
                "pins": {"positive": "1", "negative": "3"},
                "note": "C1+ / C1- are the charge-pump flying capacitor leads",
            },
        },
        {
            "type": "pin_functions",
            "value": {
                "pins": {
                    "1": {"name": "C1+", "type": "passive"},
                    "2": {"name": "V+", "type": "power"},
                    "3": {"name": "C1-", "type": "passive"},
                    "11": {"name": "DIN1", "type": "input", "max_v": 5.5},
                    "12": {"name": "ROUT1", "type": "output"},
                    "15": {"name": "GND", "type": "ground"},
                    "16": {"name": "VCC", "type": "power"},
                },
                "supply": {"min_v": 3.0, "max_v": 5.5, "unit": "V",
                           "conditions": "VCC = 3.3 V or 5 V recommended range"},
            },
        },
    ],
}

TI_TPS62130_PIN = {
    "fact_id": "F-TPS62130-PINS",
    "mpn": "TPS62130RGTR",
    "manufacturer": "Texas Instruments",
    "package": "VQFN-16 (RGT)",
    "revision": "SLVSAG7F",
    "source": {
        "kind": "datasheet",
        "url": "https://www.ti.com/lit/ds/symlink/tps62130.pdf",
        "revision": "SLVSAG7F (NOVEMBER 2011 - REVISED NOVEMBER 2021)",
        "retrieved_at": "2026-10-27",
        "pages": "3, 4",
        "table": "Table 6-1 Pin Functions; section 7.3 Recommended Operating Conditions",
        "sha256": "f9b1af285622c0cf1a5991f9641a6e64c5e6d899e52cc0b1632808742019579f",
    },
    "applies_to": {"mpn": ["TPS62130RGTR"], "packages": ["VQFN-16", "RGT"],
                   "revisions": []},
    "facts": [
        {
            "type": "pin_functions",
            "value": {
                "pins": {
                    "4": {"name": "PG", "type": "open_drain"},
                    "6": {"name": "AGND", "type": "ground"},
                    "10": {"name": "AVIN", "type": "power"},
                    "11": {"name": "PVIN", "type": "power"},
                    "12": {"name": "PVIN", "type": "power"},
                    "13": {"name": "EN", "type": "input", "max_v": 17.3},
                    "15": {"name": "PGND", "type": "ground"},
                    "16": {"name": "PGND", "type": "ground"},
                },
                "supply": {"min_v": 3.0, "max_v": 17.0, "unit": "V",
                           "conditions": "VIN at AVIN and PVIN"},
            },
        }
    ],
}

TI_TPS62130_PAD = {
    "fact_id": "F-TPS62130-PADS",
    "mpn": "TPS62130RGTR",
    "manufacturer": "Texas Instruments",
    "package": "VQFN-16 (RGT)",
    "revision": "SLVSAG7F",
    "source": {
        "kind": "datasheet",
        "url": "https://www.ti.com/lit/ds/symlink/tps62130.pdf",
        "revision": "SLVSAG7F (NOVEMBER 2011 - REVISED NOVEMBER 2021)",
        "retrieved_at": "2026-10-27",
        "pages": "3, 28",
        "table": "Table 6-1 Pin Functions; section 11.1 Layout Guidelines",
        "sha256": "f9b1af285622c0cf1a5991f9641a6e64c5e6d899e52cc0b1632808742019579f",
    },
    "applies_to": {"mpn": ["TPS62130RGTR"], "packages": ["VQFN-16", "RGT"],
                   "revisions": []},
    "facts": [
        {
            "type": "pad_map",
            "value": {
                "package": "VQFN-16 (RGT)",
                "pins": [
                    {"pin": "6", "name": "AGND", "pads": ["6"],
                     "required_net_role": "ground"},
                    {"pin": "15", "name": "PGND", "pads": ["15"],
                     "required_net_role": "ground"},
                    {"pin": "16", "name": "PGND", "pads": ["16"],
                     "required_net_role": "ground"},
                    {"pin": "EP", "name": "Exposed Thermal Pad",
                     "pads": ["17"], "required_net_role": "ground",
                     "note": "must be connected to AGND/PGND and soldered"},
                ],
            },
        }
    ],
}

AMS1117_PAD = {
    "fact_id": "F-AMS1117-PADS",
    "mpn": "AMS1117-3.3",
    "manufacturer": "Advanced Monolithic Systems",
    "package": "SOT-223",
    "revision": "AMS1117 datasheet (undated revision on vendor page)",
    "source": {
        "kind": "datasheet",
        "url": "http://www.advanced-monolithic.com/pdf/ds1117.pdf",
        "revision": "AMS1117 datasheet as retrieved 2026-10-27",
        "retrieved_at": "2026-10-27",
        "pages": "1",
        "table": "PIN CONNECTIONS / SOT-223 Top View (TAB IS OUTPUT)",
        "sha256": "189a2651878a87d590b768eaa9b44217a3fdf460352ce6ecaff127221282a3f0",
    },
    "applies_to": {"mpn": ["AMS1117-3.3"], "packages": ["SOT-223"],
                   "revisions": []},
    "facts": [
        {
            "type": "pad_map",
            "value": {
                "package": "SOT-223",
                "pins": [
                    {"pin": "1", "name": "GND/ADJ", "pads": ["1"],
                     "required_net_role": "ground"},
                    {"pin": "2", "name": "VOUT", "pads": ["2", "TAB"],
                     "note": "TAB IS OUTPUT: the tab is electrically VOUT"},
                    {"pin": "3", "name": "VIN", "pads": ["3"]},
                ],
                "notes": ["TAB IS OUTPUT (SOT-223 pin 2)"],
            },
        }
    ],
}

# Verified four-terminal tactile switch structure.  ALPSALPINE SKHH Top push
# type: pins 1-2 are internally common, pins 3-4 are internally common, and the
# press closes the normally-open contact between the two groups.  See
# docs/parallel-electrical-review/sources.md and fact-research.md.
SWITCH_MPN = "SKHHAKA010"
SWITCH_FACT = {
    "fact_id": "F-SWITCH-4PIN",
    "mpn": SWITCH_MPN,
    "manufacturer": "ALPSALPINE",
    "package": "SKHH Top push 4-terminal THT",
    "revision": "ALPS SKHH product page printed 2018-01-17; catalog p.200",
    "source": {
        "kind": "datasheet",
        "url": "http://www.alps.com/prod/info/C/HTML/Tact/SnapIn/SKHH/SKHHAKA010.html",
        "revision": "ALPS SKHH product page print 2018-01-17; catalog printed p.200",
        "retrieved_at": "2026-10-27",
        "pages": "product page print p.3 circuit diagram; catalog p.199-200",
        "table": "Circuit diagram: 1-2 common, 3-4 common, NO contact between groups",
        "sha256": "ca5bd4e5d68018b9835dbd40b0ce177d321b95ed6caf560b70db3cb4176e736c",
        "note": "first-party ALPS PDF mirrored by LCSC (C139754); original URL is the "
                "official ALPS product page printed in the footer",
    },
    "applies_to": {"mpn": [SWITCH_MPN, "SKHHARA010", "SKHHAJA010",
                           "SKHHALA010", "SKHHAQA010", "SKHHAMA010"],
                   "packages": [], "revisions": []},
    "facts": [
        {
            "type": "switch_internal_groups",
            "value": {
                "always_closed_groups": [["1", "2"], ["3", "4"]],
                "pressed_connects_groups": True,
                "pressed_closes": [],
                "terminal_numbering": "原厂电路图明确标注 1/2/3/4；不依赖符号左右位置",
                "note": "Top push type: 1-2 common, 3-4 common, press closes the "
                        "NO contact between the two groups. Side push type is "
                        "2-terminal and must not use this fact.",
            },
        }
    ],
}


def five_volt_cap(ref="C1", ident="iC1", net_a="VIN", net_b="GND",
                  rated=25.0, role="bulk", stress=None):
    attributes = {"rated_voltage": {"value": rated, "unit": "V",
                                   "conditions": "DC rated",
                                   "evidence": ["E1"]}}
    if stress is not None:
        attributes["max_differential_stress"] = {
            "value": stress, "unit": "V", "basis": "declared worst case",
            "evidence": ["E1"]}
    return component(ident, ref, "capacitor", mpn="GRM188R71C104KA01",
                     value="100nF", attributes=attributes,
                     pins=[pin(1, net_a), pin(2, net_b)])


def case_r1_ok():
    return {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r1-ok"),
        "evidence": [evidence()],
        "components": [
            component("iU1", "U1", "ic", mpn="MAX3232IDR",
                      pins=[pin(1, "CP"), pin(3, "CN"), pin(16, "3V3"),
                            pin(15, "GND")]),
            component("iC1", "C1", "capacitor", mpn="GRM188R71C104KA01",
                      value="100nF",
                      pins=[pin(1, "CP"), pin(2, "CN")]),
        ],
        "connectivity": {"pin_nets": {}},
        "device_facts": [copy.deepcopy(TI_MAX3232)],
        "intent": {
            "source": "user_declaration",
            "capacitor_roles": [{
                "component": "C1", "role": "flying",
                "role_source": "datasheet",
                "expected_terminals": [{"pin": "1", "net": "CP"},
                                       {"pin": "2", "net": "CN"}],
                "evidence": ["E1"], "fact_ids": ["F-MAX3232"]}],
        },
    }


def _r1_variant(nets, expected=True):
    data = case_r1_ok()
    data["design"]["project_id"] = "r1-variant"
    data["components"][1]["pins"] = [pin(1, nets[0], ), pin(2, nets[1])]
    role = data["intent"]["capacitor_roles"][0]
    if not expected:
        role.pop("expected_terminals")
    else:
        role["expected_terminals"] = [
            {"pin": "1", "net": nets[0] if nets[0] else "CP"},
            {"pin": "2", "net": nets[1] if nets[1] else "CN"},
        ]
    if nets[0] is None:
        data["components"][1]["pins"][0].pop("net")
    return data


def case_r1_short():
    data = _r1_variant(("CP", "CP"), expected=False)
    data["design"]["project_id"] = "r1-short"
    return data


def case_r1_wrong():
    data = _r1_variant(("CP", "SW"), expected=False)
    data["design"]["project_id"] = "r1-wrong"
    data["intent"]["capacitor_roles"][0]["expected_terminals"] = [
        {"pin": "1", "net": "CP"}, {"pin": "2", "net": "CN"}]
    return data


def case_r1_unknown():
    data = _r1_variant(("CP", None), expected=False)
    data["design"]["project_id"] = "r1-unknown"
    return data


def case_r2_overvoltage():
    return {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r2-overvoltage"),
        "evidence": [evidence()],
        "components": [five_volt_cap("C1", "iC1", "VIN", "GND", rated=16.0,
                                     role="bulk", stress=24.0)],
        "connectivity": {"pin_nets": {}},
        "intent": {"capacitor_roles": [{
            "component": "C1", "role": "bulk", "role_source": "user_declaration",
            "evidence": ["E1"]}]},
    }


def case_r2_derating():
    data = case_r2_overvoltage()
    data["design"]["project_id"] = "r2-derating"
    data["components"][0] = five_volt_cap("C1", "iC1", "VIN", "GND",
                                          rated=25.0, role="bulk", stress=21.0)
    data["intent"]["derating"] = {"max_voltage_fraction": 0.8,
                                  "source": "project policy",
                                  "evidence": ["E1"]}
    return data


def case_r2_unknown_switching():
    data = {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r2-switching"),
        "evidence": [evidence()],
        "components": [five_volt_cap("C1", "iC1", "SW", "GND", rated=16.0,
                                     role="bulk")],
        "connectivity": {"pin_nets": {}},
        "intent": {"capacitor_roles": [{
            "component": "C1", "role": "bulk", "role_source": "user_declaration",
            "evidence": ["E1"]}]},
        "operating_conditions": {"net_voltages": [
            {"net": "SW", "min_v": 0, "max_v": 24, "kind": "switching",
             "evidence": ["E1"]},
            {"net": "GND", "min_v": 0, "max_v": 0, "kind": "dc",
             "evidence": ["E1"]},
        ]},
    }
    return data


def case_r2_dc_ok():
    data = case_r2_unknown_switching()
    data["design"]["project_id"] = "r2-dc-ok"
    data["components"][0] = five_volt_cap("C1", "iC1", "VIN", "GND",
                                          rated=25.0, role="bulk")
    data["operating_conditions"] = {"net_voltages": [
        {"net": "VIN", "min_v": 4.5, "max_v": 5.5, "kind": "dc",
         "evidence": ["E1"]},
        {"net": "GND", "min_v": 0, "max_v": 0, "kind": "dc",
         "evidence": ["E1"]},
    ]}
    return data


def switch_case(used, nets, project, fact=True, roles=None):
    data = {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design(project),
        "evidence": [evidence()],
        "components": [component(
            "iSW1", "SW1", "switch", mpn=SWITCH_MPN if fact else None,
            pins=[pin(1, nets[0]), pin(2, nets[1]), pin(3, nets[2]),
                  pin(4, nets[3])])],
        "connectivity": {"pin_nets": {}},
        "device_facts": [copy.deepcopy(SWITCH_FACT)] if fact else [],
        "intent": {
            "switch_requirements": [{
                "component": "SW1", "function": "user button",
                "used_pins": used, "evidence": ["E1"]}],
            "net_roles": roles or {},
        },
    }
    return data


def case_r3_ok():
    return switch_case(["1", "3"], ["EN", "EN", "GND", "GND"],
                       "r3-ok", roles={"EN": "signal", "GND": "ground"})


def case_r3_wrong():
    return switch_case(["1", "2"], ["BOOT", "BOOT", "GND", "GND"],
                       "r3-wrong", roles={"BOOT": "signal", "GND": "ground"})


def case_r3_short():
    return switch_case(["1", "3"], ["VIN", "VIN", "GND", "GND"],
                       "r3-short", roles={"VIN": "power", "GND": "ground"})


def case_r3_unknown():
    return switch_case(["1", "3"], ["EN", "EN", "GND", "GND"],
                       "r3-unknown", fact=False,
                       roles={"EN": "signal", "GND": "ground"})


def tps_components(ep_net="GND", ep_pads=("17",), mapping_complete=True):
    pins = [
        pin(4, "PG"), pin(6, "GND"), pin(10, "VIN"), pin(11, "VIN"),
        pin(12, "VIN"), pin(13, "EN"), pin(15, "GND"), pin(16, "GND"),
    ]
    if ep_net is not None:
        pins.append(pin(17, ep_net, pads=list(ep_pads), name="EP"))
    for row in pins:
        if row["number"] in ("6", "15", "16", "17", "10", "11", "12"):
            row.setdefault("pads", [row["number"]])
    return component("iU1", "U1", "ic", mpn="TPS62130RGTR",
                     footprint={"name": "VQFN-16_RGT", "evidence": ["E1"]},
                     mapping_complete=mapping_complete,
                     pins=pins)


def case_r4_pin_role():
    return {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r4-pin-role"),
        "evidence": [evidence()],
        "components": [tps_components()],
        "connectivity": {"pin_nets": {}},
        "device_facts": [copy.deepcopy(TI_TPS62130_PIN)],
        "intent": {"pin_roles": [{"component": "U1", "pin": "4",
                                  "role": "push_pull", "evidence": ["E1"]}],
                   "net_roles": {"GND": "ground", "VIN": "power",
                                 "PG": "signal", "EN": "signal"}},
    }


def case_r4_supply():
    data = case_r4_pin_role()
    data["design"]["project_id"] = "r4-supply"
    data["intent"].pop("pin_roles")
    data["intent"]["supplies"] = [{"net": "VIN", "min_v": 24, "max_v": 24,
                                   "kind": "dc", "evidence": ["E1"]}]
    return data


def case_r4_open_drain_pullup():
    data = case_r4_pin_role()
    data["design"]["project_id"] = "r4-pullup"
    data["components"].append(component(
        "iR1", "R1", "resistor", mpn="RC0603FR-0710KL",
        pins=[pin(1, "PG"), pin(2, "3V3")]))
    data["intent"]["pin_roles"] = [{"component": "U1", "pin": "4",
                                    "role": "output", "evidence": ["E1"]}]
    data["intent"]["net_roles"]["3V3"] = "power"
    return data


def case_r5_ep_missing():
    return {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r5-ep-missing"),
        "evidence": [evidence()],
        "components": [tps_components(ep_net=None)],
        "connectivity": {"pin_nets": {}},
        "device_facts": [copy.deepcopy(TI_TPS62130_PAD)],
        "intent": {"net_roles": {"GND": "ground", "VIN": "power"}},
    }


def case_r5_ep_wrong():
    data = case_r5_ep_missing()
    data["design"]["project_id"] = "r5-ep-wrong"
    data["components"] = [tps_components(ep_net="SW")]
    data["intent"]["net_roles"]["SW"] = "signal"
    return data


def case_r5_ep_ok():
    data = case_r5_ep_missing()
    data["design"]["project_id"] = "r5-ep-ok"
    data["components"] = [tps_components(ep_net="GND")]
    return data


def ams_component(tab=True):
    pads = ["2", "TAB"] if tab else ["2"]
    return component(
        "iU2", "U2", "ic", mpn="AMS1117-3.3",
        footprint={"name": "SOT-223", "evidence": ["E1"]},
        mapping_complete=True,
        pins=[pin(1, "GND", pads=["1"]), pin(2, "+3V3", pads=pads),
              pin(3, "VIN", pads=["3"])])


def case_r5_ams_tab_missing():
    return {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r5-ams-missing"),
        "evidence": [evidence()],
        "components": [ams_component(tab=False)],
        "connectivity": {"pin_nets": {}},
        "device_facts": [copy.deepcopy(AMS1117_PAD)],
        "intent": {"net_roles": {"GND": "ground", "+3V3": "power",
                                 "VIN": "power"}},
    }


def case_r5_ams_tab_ok():
    data = case_r5_ams_tab_missing()
    data["design"]["project_id"] = "r5-ams-ok"
    data["components"] = [ams_component(tab=True)]
    return data


def r6_case(role, distance_mil, positions=True, bulk_constraint=False):
    cap_pins = [pin(1, "3V3"), pin(2, "GND")]
    ic_pins = [pin(1, "3V3"), pin(2, "GND")]
    if positions:
        cap_pins[0]["position"] = {"x": 0, "y": 0}
        cap_pins[1]["position"] = {"x": 0, "y": 50}
        ic_pins[0]["position"] = {"x": distance_mil, "y": 0}
        ic_pins[1]["position"] = {"x": distance_mil, "y": 50}
    data = {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r6-" + role),
        "evidence": [evidence()],
        "components": [
            component("iC1", "C1", "capacitor", mpn="GRM188R71C104KA01",
                      value="100nF",
                      placement={"x": 0, "y": 0, "units": "mil"},
                      pins=cap_pins),
            component("iU1", "U1", "ic", mpn="STM32G030F6P6",
                      footprint={"name": "TSSOP-20", "evidence": ["E1"]},
                      pins=ic_pins),
        ],
        "connectivity": {"pin_nets": {}},
        "intent": {"net_roles": {"3V3": "power", "GND": "ground"},
                   "capacitor_roles": [{
                       "component": "C1", "role": role,
                       "role_source": "project_constraint",
                       "evidence": ["E1"]}]},
    }
    if role == "local_decoupling" or bulk_constraint:
        data["intent"]["decoupling_targets"] = [{
            "capacitor": "C1", "target_component": "U1",
            "target_pins": ["1"], "max_distance": {"value": 150, "unit": "mil"},
            "basis": "euclidean_proxy", "source": "benchmark project rule",
            "evidence": ["E1"]}]
    return data


def case_r6_far():
    return r6_case("local_decoupling", 200)


def case_r6_ok():
    return r6_case("local_decoupling", 50)


def case_r6_bulk():
    return r6_case("bulk", 500, bulk_constraint=True)


def case_r6_missing_geometry():
    return r6_case("local_decoupling", 200, positions=False)


def case_r5_no_fact():
    return {
        "schema": "easycirq.electrical-review.input/v1",
        "design": design("r5-no-fact"),
        "evidence": [evidence()],
        "components": [tps_components(ep_net=None)],
        "connectivity": {"pin_nets": {}},
        "device_facts": [],
        "intent": {"net_roles": {"GND": "ground", "VIN": "power"}},
    }


CASES = {
    "r1-flying-ok": case_r1_ok,
    "r1-flying-short": case_r1_short,
    "r1-flying-wrong-net": case_r1_wrong,
    "r1-flying-unknown-net": case_r1_unknown,
    "r2-overvoltage-hard": case_r2_overvoltage,
    "r2-derating-shortfall": case_r2_derating,
    "r2-switching-unknown": case_r2_unknown_switching,
    "r2-dc-derived-ok": case_r2_dc_ok,
    "r3-always-closed": case_r3_wrong,
    "r3-switch-ok": case_r3_ok,
    "r3-pressed-power-short": case_r3_short,
    "r3-internal-unknown": case_r3_unknown,
    "r4-pin-role-conflict": case_r4_pin_role,
    "r4-supply-overvoltage": case_r4_supply,
    "r4-open-drain-pullup-ok": case_r4_open_drain_pullup,
    "r5-exposed-pad-missing": case_r5_ep_missing,
    "r5-exposed-pad-wrong-net": case_r5_ep_wrong,
    "r5-exposed-pad-ok": case_r5_ep_ok,
    "r5-ams-tab-missing": case_r5_ams_tab_missing,
    "r5-ams-tab-ok": case_r5_ams_tab_ok,
    "r5-no-pad-fact": case_r5_no_fact,
    "r6-local-too-far": case_r6_far,
    "r6-local-ok": case_r6_ok,
    "r6-bulk-exempt": case_r6_bulk,
    "r6-geometry-missing": case_r6_missing_geometry,
}
