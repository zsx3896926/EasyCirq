#!/usr/bin/env python3
"""Regression checks for thermal_calc.py.

Run from this directory:
    python -I test_thermal_calc.py

These tests check the arithmetic and the input guards, not any physical
validity beyond the stated model. They are not a substitute for a datasheet,
FEM, or measurement.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CALC = os.path.join(HERE, "thermal_calc.py")


def run(mode, data):
    proc = subprocess.run(
        [sys.executable, "-I", CALC, mode, json.dumps(data)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        return proc.returncode, {"status": "unexpected_exit", "stderr": proc.stderr[-200:]}
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.returncode, {"status": "invalid_json", "stdout": proc.stdout[-200:]}


def close(actual, expected, tol=1e-3):
    return abs(actual - expected) <= tol


def main():
    checks = []

    code, out = run("ldo", {
        "vin_V": 12, "vout_V": 3.3, "iout_A": 0.15, "iq_A": 0.005,
        "theta_ja_K_per_W": 250, "ta_C": 40, "tj_max_C": 125,
    })
    checks.append(("ldo fail status", code == 0 and out["status"] == "exceeds_tj_max"))
    checks.append(("ldo power", close(out["power_W"], 1.365)))
    checks.append(("ldo required theta", close(out["required_theta_ja_K_per_W"], 62.271062)))

    code, out = run("ldo", {
        "vin_V": 12, "vout_V": 3.3, "iout_A": 0.15, "iq_A": 0.005,
        "theta_ja_K_per_W": 60, "ta_C": 40, "tj_max_C": 125,
    })
    checks.append(("ldo 60C tj", close(out["tj_C"], 121.9)))

    code, out = run("mosfet", {
        "vin_V": 24, "iout_A": 5, "duty": 0.4, "rds_on_25_ohm": 0.01,
        "rds_tempco_per_C": 0.004, "theta_ja_K_per_W": 50, "ta_C": 40,
        "tj_max_C": 125, "fsw_Hz": 100000, "tr_s": 20e-9, "tf_s": 20e-9,
        "qg_C": 20e-9, "vgs_V": 10,
    })
    checks.append(("mosfet good tj", close(out["tj_C"], 58.673469)))
    checks.append(("mosfet good power", close(out["power_W"], 0.373469)))

    code, out = run("mosfet", {
        "vin_V": 48, "iout_A": 10, "duty": 0.5, "rds_on_25_ohm": 0.02,
        "rds_tempco_per_C": 0.005, "theta_ja_K_per_W": 40, "ta_C": 40,
        "tj_max_C": 125, "fsw_Hz": 200000, "tr_s": 50e-9, "tf_s": 50e-9,
        "qg_C": 50e-9, "vgs_V": 10,
    })
    checks.append(("mosfet bad status", out["status"] == "exceeds_tj_max"))
    checks.append(("mosfet bad power", close(out["power_W"], 7.46875)))
    checks.append(("mosfet bad tj", close(out["tj_C"], 338.75)))

    code, out = run("led", {
        "n_series": 6, "vf_V": 3.0, "if_A": 0.35, "optical_efficiency": 0.3,
        "rth_js_K_per_W": 5, "rth_sa_K_per_W": 15, "ta_C": 40,
        "tj_max_C": 125,
    })
    checks.append(("led heat", close(out["heat_power_W"], 4.41)))
    checks.append(("led required rth_sa", close(out["required_rth_sa_K_per_W"], 14.274376)))
    checks.append(("led bad status", out["status"] == "exceeds_tj_max"))

    code, out = run("led", {
        "n_series": 6, "vf_V": 3.0, "if_A": 0.35, "optical_efficiency": 0.3,
        "rth_js_K_per_W": 5, "rth_sa_K_per_W": 10, "ta_C": 40,
        "tj_max_C": 125,
    })
    checks.append(("led good tj", close(out["tj_C"], 106.15)))

    code, out = run("via", {
        "drill_m": 0.0003, "plating_m": 25e-6, "length_m": 0.0016,
        "count": 9, "k_cu_W_per_mK": 385,
    })
    checks.append(("via 9", close(out["resistance_K_per_W"], 21.379334)))

    code, out = run("enclosure", {
        "power_W": 4, "area_m2": 0.02, "h_W_per_m2K": 8,
        "ta_C": 30, "limit_C": 70,
    })
    checks.append(("enclosure surface", close(out["surface_C"], 55.0)))

    code, out = run("heatsink", {
        "power_W": 10, "rth_jc_K_per_W": 2, "rth_cs_K_per_W": 0.5,
        "rth_sa_K_per_W": 3, "ta_C": 40, "tj_max_C": 125,
    })
    checks.append(("heatsink tj", close(out["tj_C"], 95.0)))
    checks.append(("heatsink required sa", close(out["required_rth_sa_K_per_W"], 6.0)))

    # Input guards: these must fail with a JSON error, not emit a number.
    code, out = run("ldo", {
        "vin_V": 3.3, "vout_V": 12, "iout_A": 0.1, "iq_A": 0,
        "theta_ja_K_per_W": 50, "ta_C": 40, "tj_max_C": 125,
    })
    checks.append(("ldo rejects vout>vin", code == 1 and out["status"] == "error"))

    code, out = run("via", {
        "drill_m": 0.0003, "plating_m": 0.0002, "length_m": 0.0016,
        "count": 9, "k_cu_W_per_mK": 385,
    })
    checks.append(("via rejects over-plating", code == 1 and out["status"] == "error"))

    code, out = run("via", {
        "drill_m": 0.0003, "plating_m": 25e-6, "length_m": 0.0016,
        "count": 9.5, "k_cu_W_per_mK": 385,
    })
    checks.append(("via rejects fractional count", code == 1 and out["status"] == "error"))

    code, out = run("ldo", {
        "vin_V": 12, "vout_V": 3.3, "iout_A": 0.15, "iq_A": 0.005,
        "theta_ja_K_per_W": 60, "ta_C": 40, "tj_max_C": 125,
        "min_margin_K": 20,
    })
    checks.append(("ldo project margin tight", out["status"] == "tight"))

    code, out = run("enclosure", {
        "power_W": 4, "area_m2": 0.02, "h_W_per_m2K": 5,
        "ta_C": 30, "limit_C": 70,
    })
    checks.append(("enclosure zero margin tight", out["status"] == "tight"))

    code, out = run("led", {
        "n_series": 6, "vf_V": 3.0, "if_A": 0.35, "optical_efficiency": 0.3,
        "rth_js_K_per_W": 5, "rth_sa_K_per_W": 12.5, "ta_C": 40,
        "tj_max_C": 125, "rth_js_basis": "electrical",
    })
    checks.append(("led electrical basis tj", close(out["tj_C"], 126.625)))
    checks.append(("led electrical basis fails", out["status"] == "exceeds_tj_max"))

    code, out = run("ldo", {
        "vin_V": 10 ** 400, "vout_V": 3.3, "iout_A": 0.1, "iq_A": 0,
        "theta_ja_K_per_W": 50, "ta_C": 40, "tj_max_C": 125,
    })
    checks.append(("huge integer rejected", code == 1 and out["status"] == "error"))

    code, out = run("led", {
        "n_series": 2.5, "vf_V": 3.0, "if_A": 0.35, "optical_efficiency": 0.3,
        "rth_js_K_per_W": 5, "rth_sa_K_per_W": 10, "ta_C": 40,
        "tj_max_C": 125,
    })
    checks.append(("led rejects fractional series", code == 1 and out["status"] == "error"))

    code, out = run("led", {
        "n_series": 6, "vf_V": 3.0, "if_A": 0.35, "optical_efficiency": 1.0,
        "rth_js_K_per_W": 5, "rth_sa_K_per_W": 10, "ta_C": 40,
        "tj_max_C": 125,
    })
    checks.append(("led rejects optical=1", code == 1 and out["status"] == "error"))

    code, out = run("ldo", {
        "vin_V": 3.3, "vout_V": 3.3, "iout_A": 0.1, "iq_A": 0,
        "theta_ja_K_per_W": 50, "ta_C": 40, "tj_max_C": 125,
    })
    checks.append(("ldo rejects zero dropout", code == 1 and out["status"] == "error"))

    code, out = run("mosfet", {
        "vin_V": 24, "iout_A": 5, "duty": 0, "rds_on_25_ohm": 0.01,
        "rds_tempco_per_C": 0.004, "theta_ja_K_per_W": 50, "ta_C": 40,
        "tj_max_C": 125, "fsw_Hz": 100000, "tr_s": 20e-9, "tf_s": 20e-9,
        "qg_C": 20e-9, "vgs_V": 10,
    })
    checks.append(("mosfet duty=0 no switching", close(out["switching_loss_W"], 0.0)))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
