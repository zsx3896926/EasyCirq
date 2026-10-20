#!/usr/bin/env python3
"""Executable two-node RC sampling-network simulation (no third-party deps).

Circuit (all values SI):
  Vs -- R_source -- node A -- R_switch -- node B
                    |                       |
                  C_ext                  C_sample
                    |                       |
                   GND                     GND

The switch closes at t_close. The source steps from 0 to Vin at t=0.
Backward-Euler is used with a fixed step. This is a transparent numerical
model, not a SPICE simulator and not a device-level validation.

Example:
  python rc_settle_sim.py --vin 3.3 --r-source 1000 --r-switch 100 \
    --c-ext 1e-9 --c-sample 4e-12 --t-close 0 --t-end 20e-6 --dt 1e-9 \
    --bits 12 --vref 3.3 --out rc.csv
"""
import argparse
import csv
import json
import math
import sys


def simulate(vin, r_source, r_switch, c_ext, c_sample, t_close, t_end, dt,
             bits, vref):
    if not all(math.isfinite(x) for x in
               (vin, r_source, r_switch, c_ext, c_sample, t_close, t_end, dt, vref)):
        raise ValueError('all inputs must be finite')
    if r_source <= 0 or r_switch <= 0 or c_ext <= 0 or c_sample <= 0:
        raise ValueError('resistances and capacitances must be positive')
    if t_end <= 0 or dt <= 0 or t_close < 0 or t_close >= t_end:
        raise ValueError('require 0 <= t_close < t_end and dt > 0')
    if not isinstance(bits, int) or not 1 <= bits <= 32:
        raise ValueError('bits must be an integer in 1..32')
    steps = int(math.ceil(t_end / dt))
    if steps > 5_000_000:
        raise ValueError('too many steps; increase dt or reduce t_end')

    g_s = 1.0 / r_source
    g_sw = 1.0 / r_switch
    va = 0.0
    vb = 0.0
    vs = vin
    rows = []
    peak_va = 0.0
    monotonic = True
    last_vb = vb
    for n in range(steps + 1):
        t = n * dt
        if n > 0:
            if t >= t_close:
                # Coupled nodes after switch closure.
                a11 = g_s + c_ext / dt + g_sw
                a12 = -g_sw
                a21 = -g_sw
                a22 = g_sw + c_sample / dt
                b1 = g_s * vs + c_ext / dt * va
                b2 = c_sample / dt * vb
                det = a11 * a22 - a12 * a21
                va_new = (b1 * a22 - a12 * b2) / det
                vb_new = (a11 * b2 - b1 * a21) / det
            else:
                # Sample capacitor disconnected; hold its state.
                va_new = (g_s * vs + c_ext / dt * va) / (g_s + c_ext / dt)
                vb_new = vb
            va, vb = va_new, vb_new
        if vb + 1e-15 < last_vb:
            monotonic = False
        last_vb = vb
        peak_va = max(peak_va, va)
        rows.append((t, va, vb, vin - vb,
                     abs(vin - vb) / (vref / (2 ** bits))))
    lsb = vref / (2 ** bits)
    final_error_lsb = abs(vin - vb) / lsb
    return {
        'status': 'simulated',
        'simulation_executed': True,
        'board_verified': False,
        'model': 'backward-Euler two-node RC network; ideal step source, constant resistances, no charge injection/leakage/noise',
        'steps': steps,
        'dt_s': dt,
        't_end_s': t_end,
        'final_v_b_V': vb,
        'final_error_V': vin - vb,
        'final_error_LSB': final_error_lsb,
        'settled_0p5LSB': final_error_lsb <= 0.5,
        'peak_v_a_V': peak_va,
        'v_b_monotonic': monotonic,
        'limitations': 'Transparent numerical model only. It does not validate switch charge injection, ADC input capacitance nonlinearity, source settling, dielectric absorption, noise, reference error or total ADC accuracy.',
    }, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vin', type=float, default=3.3)
    ap.add_argument('--r-source', type=float, default=1000.0)
    ap.add_argument('--r-switch', type=float, default=100.0)
    ap.add_argument('--c-ext', type=float, default=1e-9)
    ap.add_argument('--c-sample', type=float, default=4e-12)
    ap.add_argument('--t-close', type=float, default=0.0)
    ap.add_argument('--t-end', type=float, default=20e-6)
    ap.add_argument('--dt', type=float, default=1e-9)
    ap.add_argument('--bits', type=int, default=12)
    ap.add_argument('--vref', type=float, default=3.3)
    ap.add_argument('--out', default='rc_settle.csv')
    a = ap.parse_args()
    try:
        summary, rows = simulate(a.vin, a.r_source, a.r_switch, a.c_ext,
                                 a.c_sample, a.t_close, a.t_end, a.dt,
                                 a.bits, a.vref)
        with open(a.out, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['time_s', 'v_a_V', 'v_b_V', 'error_V', 'error_LSB'])
            w.writerows(rows)
        summary['csv'] = a.out
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, TypeError, OverflowError) as exc:
        print(json.dumps({'status': 'invalid_input', 'error': str(exc)},
                         ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
