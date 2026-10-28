#!/usr/bin/env python3
"""Offline thermal screening calculator for board-level design.

This script is a deliberately small, transparent model. It does not replace a
datasheet, a vendor thermal model, FEM, or a measurement. Every result carries
an explicit assumptions string and the inputs that produced it.

Usage:
    python thermal_calc.py <mode> '<json>'

Modes and required fields (SI units: V, A, W, K or degC, m, W/m-K):
  ldo:        vin_V, vout_V, iout_A, iq_A, theta_ja_K_per_W, ta_C, tj_max_C
  mosfet:     vin_V, iout_A, duty, rds_on_25_ohm, rds_tempco_per_C,
              theta_ja_K_per_W, ta_C, tj_max_C, fsw_Hz, tr_s, tf_s,
              qg_C, vgs_V
              (vin_V = switch blocking voltage; iout_A = switch on-time
              current; for boost/flyback pass the actual switch stress)
  led:        n_series, vf_V, if_A, optical_efficiency, rth_js_K_per_W,
              rth_sa_K_per_W, ta_C, tj_max_C,
              optional rth_js_basis = "real" (default) or "electrical"
  via:        drill_m, plating_m, length_m, count, k_cu_W_per_mK
  enclosure:  power_W, area_m2, h_W_per_m2K, ta_C, limit_C
              (limit_C is the surface-temperature limit for this check; the
              older alias tj_max_C is accepted but is not a junction limit)
  heatsink:   power_W, rth_jc_K_per_W, rth_cs_K_per_W, rth_sa_K_per_W,
              ta_C, tj_max_C

Optional for ldo/mosfet/led/enclosure/heatsink: min_margin_K. With it,
status is "tight" when 0 <= margin <= min_margin_K; without it, min_margin_K
defaults to 0 and a zero margin is still "tight". "calculated" only means the
margin is above the requested minimum; it is not an engineering pass.

Temperatures are Celsius in the interface; thermal resistances are K/W.
The script rejects non-finite values and never emits NaN/Infinity.
"""

import json
import math
import sys


def _num(data, key, *, positive=False, nonnegative=False):
    if key not in data:
        raise ValueError(f"{key}: required")
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key}: finite number required")
    try:
        value = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{key}: finite number required")
    if not math.isfinite(value):
        raise ValueError(f"{key}: finite number required")
    if positive and value <= 0:
        raise ValueError(f"{key}: must be > 0")
    if nonnegative and value < 0:
        raise ValueError(f"{key}: must be >= 0")
    return value


def _fraction(data, key):
    value = _num(data, key, nonnegative=True)
    if value > 1:
        raise ValueError(f"{key}: must be between 0 and 1")
    return value


def _min_margin(data):
    if "min_margin_K" not in data:
        return 0.0
    return _num(data, "min_margin_K", nonnegative=True)


def _status(margin, min_margin, fail_label):
    if margin < 0:
        return fail_label
    if margin <= min_margin:
        return "tight"
    return "calculated"


def ldo(data):
    vin = _num(data, "vin_V", positive=True)
    vout = _num(data, "vout_V", positive=True)
    iout = _num(data, "iout_A", nonnegative=True)
    iq = _num(data, "iq_A", nonnegative=True)
    theta_ja = _num(data, "theta_ja_K_per_W", positive=True)
    ta = _num(data, "ta_C")
    tj_max = _num(data, "tj_max_C")
    min_margin = _min_margin(data)
    if vout >= vin:
        raise ValueError("vout_V: require vout < vin for an LDO (zero/negative dropout is invalid)")
    power = (vin - vout) * iout + vin * iq
    tj = ta + power * theta_ja
    margin = tj_max - tj
    required_theta = (tj_max - ta) / power if power > 0 else None
    max_power = (tj_max - ta) / theta_ja
    return {
        "mode": "ldo",
        "status": _status(margin, min_margin, "exceeds_tj_max"),
        "power_W": power,
        "tj_C": tj,
        "margin_K": margin,
        "min_margin_K": min_margin,
        "required_theta_ja_K_per_W": required_theta,
        "max_power_at_theta_ja_W": max_power,
        "assumptions": (
            "DC steady state; P=(Vin-Vout)*Iout+Vin*Iq. Iq is the datasheet "
            "quiescent current at the worst relevant operating point. theta_ja "
            "is the value for the actual package, copper area, layer count and "
            "airflow; a JEDEC-board value is a comparison metric, not a "
            "board-independent constant. Excludes transient, current-limit, "
            "thermal-shutdown behavior and self-heating of Iq. status=calculated "
            "only means margin > min_margin; it is not an engineering pass. A "
            "result above Tj,max is a failure signal, not a physically valid "
            "temperature."
        ),
    }


def mosfet(data):
    vin = _num(data, "vin_V", positive=True)
    iout = _num(data, "iout_A", nonnegative=True)
    duty = _fraction(data, "duty")
    rds25 = _num(data, "rds_on_25_ohm", positive=True)
    tempco = _num(data, "rds_tempco_per_C")
    theta_ja = _num(data, "theta_ja_K_per_W", positive=True)
    ta = _num(data, "ta_C")
    tj_max = _num(data, "tj_max_C")
    fsw = _num(data, "fsw_Hz", positive=True)
    tr = _num(data, "tr_s", nonnegative=True)
    tf = _num(data, "tf_s", nonnegative=True)
    qg = _num(data, "qg_C", nonnegative=True)
    vgs = _num(data, "vgs_V", positive=True)
    min_margin = _min_margin(data)

    # No switching transition occurs at duty=0 or duty=1.
    switching = 0.5 * vin * iout * (tr + tf) * fsw if 0.0 < duty < 1.0 else 0.0
    gate = qg * vgs * fsw if 0.0 < duty < 1.0 else 0.0
    tj = ta
    conduction = 0.0
    for _ in range(100):
        rds = rds25 * (1.0 + tempco * (tj - 25.0))
        if rds <= 0:
            raise ValueError("rds_on_25_ohm/tempco produce nonpositive Rds(on)")
        conduction = iout * iout * rds * duty
        new_tj = ta + (conduction + switching + gate) * theta_ja
        if abs(new_tj - tj) < 1e-6:
            tj = new_tj
            break
        tj = new_tj
    else:
        raise ValueError("iteration did not converge")
    power = conduction + switching + gate
    margin = tj_max - tj
    return {
        "mode": "mosfet",
        "status": _status(margin, min_margin, "exceeds_tj_max"),
        "conduction_loss_W": conduction,
        "switching_loss_W": switching,
        "gate_loss_W": gate,
        "power_W": power,
        "tj_C": tj,
        "margin_K": margin,
        "min_margin_K": min_margin,
        "rds_on_at_tj_ohm": rds25 * (1.0 + tempco * (tj - 25.0)),
        "assumptions": (
            "Hard-switched switch with linear V-I overlap during tr/tf; "
            "P_sw=0.5*Vds_block*I_switch*(tr+tf)*fsw is a first-order "
            "linear-overlap estimate, NOT a guaranteed upper bound (Coss, "
            "reverse recovery, ringing and different tr/tf definitions can "
            "make the real loss larger). For an inductive load, turn-on may be "
            "near zero and turn-off is 0.5*Vds*Id*tf/T; the reliable method is "
            "to use datasheet Eon/Eoff times fsw. vin_V is the switch blocking "
            "voltage and iout_A is the switch current during on-time: for a "
            "buck high/low side these are approximately Vin and Iout, but for "
            "boost/flyback pass the actual switch stress, not the converter "
            "output. Conduction uses Rds(on)(Tj)=Rds(on,25)*(1+tempco*"
            "(Tj-25)) and a user-supplied duty; the linear tempco is only a "
            "local approximation, so results above Tj,max are a failure "
            "signal, not a valid temperature. Gate loss uses Qg*Vgs*fsw. "
            "Excludes Coss/output-charge loss, dead-time/body-diode loss, "
            "inductor ripple, current waveshape, driver loss, avalanche and "
            "thermal coupling. theta_ja must match the actual board/heatsink "
            "condition; for a heatsink use the junction-to-ambient chain. "
            "status=calculated only means margin > min_margin."
        ),
    }


def led(data):
    n = _num(data, "n_series", positive=True)
    if n != int(n):
        raise ValueError("n_series: integer required")
    vf = _num(data, "vf_V", positive=True)
    current = _num(data, "if_A", positive=True)
    optical = _fraction(data, "optical_efficiency")
    if optical >= 1.0:
        raise ValueError("optical_efficiency: require 0 <= value < 1 for a thermal calculation")
    rth_js = _num(data, "rth_js_K_per_W", positive=True)
    rth_sa = _num(data, "rth_sa_K_per_W", nonnegative=True)
    ta = _num(data, "ta_C")
    tj_max = _num(data, "tj_max_C")
    min_margin = _min_margin(data)
    basis = data.get("rth_js_basis", "real")
    if basis not in ("real", "electrical"):
        raise ValueError("rth_js_basis: require 'real' or 'electrical'")
    electrical = n * vf * current
    heat = electrical * (1.0 - optical)
    junction_heat = (heat if basis == "real" else electrical) / n
    tsolder = ta + heat * rth_sa
    tj = tsolder + junction_heat * rth_js
    margin = tj_max - tj
    required_rth_sa = (tj_max - ta - junction_heat * rth_js) / heat if heat > 0 else None
    return {
        "mode": "led",
        "status": _status(margin, min_margin, "exceeds_tj_max"),
        "rth_js_basis": basis,
        "electrical_power_W": electrical,
        "heat_power_W": heat,
        "junction_heat_W": junction_heat,
        "junction_heat_per_led_W": junction_heat,
        "solder_point_C": tsolder,
        "tj_C": tj,
        "margin_K": margin,
        "min_margin_K": min_margin,
        "required_rth_sa_K_per_W": required_rth_sa,
        "assumptions": (
            "P_heat=P_electrical*(1-optical_efficiency). optical_efficiency "
            "must come from the LED datasheet or measurement; if unknown, use "
            "0 for a conservative all-heat estimate. rth_js_basis selects how "
            "Rth_JS is paired: 'real' (default) multiplies P_heat/n by the real "
            "Rth_JS per LED; 'electrical' multiplies P_electrical/n by the electrical "
            "Rth_JS. In both cases rth_sa is multiplied by P_heat, because the "
            "board/TIM/heatsink carries the heat, not the optical power. Do not "
            "mix the definitions. Identical LEDs share an approximately isothermal solder node; local spreading/coupling is not solved. rth_sa lumps PCB, TIM, heatsink and ambient "
            "path and must be derived for the actual stack. Excludes thermal "
            "droop, binning, aging and transient effects. status=calculated "
            "only means margin > min_margin."
        ),
    }


def via(data):
    drill = _num(data, "drill_m", positive=True)
    plating = _num(data, "plating_m", positive=True)
    length = _num(data, "length_m", positive=True)
    count = _num(data, "count", positive=True)
    if count != int(count):
        raise ValueError("count: integer required")
    k_cu = _num(data, "k_cu_W_per_mK", positive=True)
    if 2.0 * plating >= drill:
        raise ValueError("plating_m: 2*plating must be less than drill")
    outer = drill
    inner = drill - 2.0 * plating
    area_one = math.pi * (outer * outer - inner * inner) / 4.0
    area_total = area_one * count
    resistance = length / (k_cu * area_total)
    return {
        "mode": "via",
        "status": "calculated",
        "barrel_area_one_m2": area_one,
        "barrel_area_total_m2": area_total,
        "resistance_K_per_W": resistance,
        "assumptions": (
            "One-dimensional copper-barrel conduction, R=L/(k*A), with a "
            "hollow annulus of outer diameter=drill and inner "
            "diameter=drill-2*plating. Vias are thermally in parallel. This "
            "is an OPEN/PLATED barrel model; a solder-filled via needs the "
            "solid area and the fill conductivity instead. k_Cu is a "
            "user-supplied bulk value (about 385 W/m-K at 20 C for pure "
            "copper, but the actual plating/voids/temperature differ). "
            "Excludes spreading resistance from the pad into the barrels, "
            "interface resistance, solder fill, and the resistance of the "
            "destination copper. A small via resistance does not prove the "
            "whole heat path is adequate."
        ),
    }


def enclosure(data):
    power = _num(data, "power_W", nonnegative=True)
    area = _num(data, "area_m2", positive=True)
    h = _num(data, "h_W_per_m2K", positive=True)
    ta = _num(data, "ta_C")
    if "limit_C" in data:
        limit = _num(data, "limit_C")
    elif "tj_max_C" in data:
        # Backward-compatible alias; semantically this is a SURFACE limit.
        limit = _num(data, "tj_max_C")
    else:
        raise ValueError("limit_C: required (surface-temperature limit)")
    min_margin = _min_margin(data)
    rise = power / (h * area) if power > 0 else 0.0
    surface = ta + rise
    margin = limit - surface
    required_area = power / (h * (limit - ta)) if power > 0 and limit > ta else None
    return {
        "mode": "enclosure",
        "status": _status(margin, min_margin, "surface_exceeds_limit"),
        "surface_rise_K": rise,
        "surface_C": surface,
        "margin_to_limit_K": margin,
        "min_margin_K": min_margin,
        "required_area_m2": required_area,
        "assumptions": (
            "Lumped external-surface model Q=h_eff*A*(T_surface-T_ambient). "
            "h_eff must be supplied for the actual enclosure, orientation, "
            "finish and airflow; Cree's LED note quotes roughly 5-20 W/m2K "
            "for natural convection in air and up to 100 W/m2K for forced "
            "air, but these are order-of-magnitude values, not a guarantee "
            "for your box. The model does not include internal air-to-wall "
            "resistance, hot spots, ventilation, solar load, altitude, or the "
            "component's own junction-to-case path. It bounds the enclosure "
            "surface, not Tj; limit_C is a surface-temperature limit, not a "
            "junction limit. Subtract surfaces that cannot transfer heat "
            "(for example, a wall-mounted face). status=calculated only means "
            "margin > min_margin."
        ),
    }


def heatsink(data):
    power = _num(data, "power_W", nonnegative=True)
    rth_jc = _num(data, "rth_jc_K_per_W", positive=True)
    rth_cs = _num(data, "rth_cs_K_per_W", nonnegative=True)
    rth_sa = _num(data, "rth_sa_K_per_W", nonnegative=True)
    ta = _num(data, "ta_C")
    tj_max = _num(data, "tj_max_C")
    min_margin = _min_margin(data)
    total = rth_jc + rth_cs + rth_sa
    tj = ta + power * total
    margin = tj_max - tj
    required_total = (tj_max - ta) / power if power > 0 else None
    required_sa = required_total - rth_jc - rth_cs if required_total is not None else None
    return {
        "mode": "heatsink",
        "status": _status(margin, min_margin, "exceeds_tj_max"),
        "total_rth_K_per_W": total,
        "tj_C": tj,
        "margin_K": margin,
        "min_margin_K": min_margin,
        "required_total_rth_K_per_W": required_total,
        "required_rth_sa_K_per_W": required_sa,
        "assumptions": (
            "Series steady-state chain Tj=Ta+P*(Rth_jc+Rth_cs+Rth_sa). "
            "Rth_jc is junction-to-case from the exact package datasheet; "
            "Rth_cs depends on TIM, thickness, contact area and mounting "
            "pressure; Rth_sa depends on heatsink, airflow, orientation and "
            "altitude. Excludes spreading resistance and transient Zth. The "
            "series chain is most defensible when the heatsink dominates and "
            "Rth_jc is small compared with Rth_ja; otherwise use the "
            "combined network or a measurement. status=calculated only means "
            "margin > min_margin."
        ),
    }


MODES = {
    "ldo": ldo,
    "mosfet": mosfet,
    "led": led,
    "via": via,
    "enclosure": enclosure,
    "heatsink": heatsink,
}


def main(argv):
    if len(argv) != 3 or argv[1] not in MODES:
        print(__doc__.strip())
        return 2
    try:
        data = json.loads(argv[2])
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        result = MODES[argv[1]](data)
        result["board_verified"] = False
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
