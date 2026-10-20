#!/usr/bin/env python3
"""Small SI-unit engineering calculations; no network/EDA/file writes.

Usage: python calculate.py MODE 'JSON'
Modes and required JSON fields:
 led: vs_min_V, vs_max_V, vf_min_V, vf_max_V, r_ohm, r_tol
 divider: vin_min_V, vin_max_V, r_top_ohm, r_bottom_ohm, r_top_tol, r_bottom_tol
 i2c: v_pullup_max_V, vol_max_V, iol_A, c_bus_max_F, tr_max_s, r_tol
 ldo: vin_min_V, vin_max_V, vout_min_V, vout_max_V, iout_max_A,
      iq_max_A, dropout_max_V
Tolerance is a fraction: 0.01=1%. Use A, F, s, ohm, V (not mA/pF/ns).
Results are simplified-model calculations, never board verification.
"""
import argparse
import itertools
import json
import math
import sys

FIELDS={
 'led': 'vs_min_V vs_max_V vf_min_V vf_max_V r_ohm r_tol'.split(),
 'divider': 'vin_min_V vin_max_V r_top_ohm r_bottom_ohm r_top_tol r_bottom_tol'.split(),
 'i2c': 'v_pullup_max_V vol_max_V iol_A c_bus_max_F tr_max_s r_tol'.split(),
 'ldo': 'vin_min_V vin_max_V vout_min_V vout_max_V iout_max_A iq_max_A dropout_max_V'.split(),
}

def calculate(mode, data):
    if mode not in FIELDS or not isinstance(data,dict):
        raise ValueError('known mode and JSON object required')
    missing=set(FIELDS[mode])-data.keys(); extra=data.keys()-set(FIELDS[mode])
    if missing or extra: raise ValueError(f'missing={sorted(missing)}, unknown={sorted(extra)}')
    for k,v in data.items():
        if type(v) not in (float,int) or not math.isfinite(v):
            raise ValueError(f'{k}: finite number required')
        if v<0: raise ValueError(f'{k}: must be nonnegative')
        if k.endswith('_tol') and v>=1: raise ValueError(f'{k}: require 0 <= tolerance < 1')
    for k in data:
        if '_min_' in k:
            upper=k.replace('_min_','_max_')
            if upper in data and data[k]>data[upper]:raise ValueError(f'{k} exceeds {upper}')
    d=data
    def positive(*keys):
        for k in keys:
            if d[k]<=0:raise ValueError(f'{k}: must be positive')
    out={'status':'calculated','board_verified':False,'input_SI':d}
    if mode=='led':
        positive('r_ohm')
        rmin=d['r_ohm']*(1-d['r_tol']);rmax=d['r_ohm']*(1+d['r_tol'])
        dvmax=max(0,d['vs_max_V']-d['vf_min_V']);dvmin=max(0,d['vs_min_V']-d['vf_max_V'])
        out.update(i_min_A=dvmin/rmax,i_max_A=dvmax/rmin,resistor_power_max_W=dvmax**2/rmin,
          assumptions='Ideal DC supply and independent Vf bounds; excludes driver drop, temperature correlation, pulses, reverse voltage and LED/driver limits.')
    elif mode=='divider':
        positive('r_top_ohm','r_bottom_ohm')
        rt=[d['r_top_ohm']*(1+t*d['r_top_tol']) for t in (-1,1)]
        rb=[d['r_bottom_ohm']*(1+t*d['r_bottom_tol']) for t in (-1,1)]
        values=[v*b/(a+b) for v,a,b in itertools.product([d['vin_min_V'],d['vin_max_V']],rt,rb)]
        out.update(vout_min_V=min(values),vout_max_V=max(values),
          r_thevenin_max_ohm=max(a*b/(a+b) for a,b in itertools.product(rt,rb)),
          assumptions='Unloaded resistive divider with independent bounds; excludes leakage, ADC charge draw, temperature drift and transients.')
    elif mode=='i2c':
        positive('iol_A','c_bus_max_F','tr_max_s')
        if d['v_pullup_max_V']<=d['vol_max_V']:raise ValueError('pullup voltage must exceed VOL')
        rmin=(d['v_pullup_max_V']-d['vol_max_V'])/d['iol_A']
        rmax=d['tr_max_s']/(0.8473*d['c_bus_max_F'])
        nommin=rmin/(1-d['r_tol']);nommax=rmax/(1+d['r_tol'])
        feasible=nommin<=nommax
        out.update(status='calculated' if feasible else 'infeasible',feasible_interval=feasible,
          equivalent_R_min_ohm=rmin,equivalent_R_max_ohm=rmax,
          nominal_interval_ohm=[nommin,nommax] if feasible else None,
          assumptions='Passive pullup single-pole RC, 30%-70% rise; IOL/VOL must be guaranteed for every sink and supply condition. Account for parallel pullups in equivalent R. Excludes active accelerators and level-shifter dynamics.')
    else:
        positive('vin_min_V','vout_min_V')
        head=d['vin_min_V']-d['vout_max_V']-d['dropout_max_V']
        regulated_possible=head>=0
        out.update(status='calculated' if regulated_possible else 'infeasible',
          dropout_margin_min_V=head,
          dissipation_estimate_max_W=(d['vin_max_V']-d['vout_min_V'])*d['iout_max_A']+d['vin_max_V']*d['iq_max_A'] if regulated_possible else None,
          assumptions='Bounded DC regulated model; no dynamic/current-limit/stability/reverse-current/thermal validation. Dissipation withheld if regulation fails the supplied dropout bound.')
    # Reject arithmetic overflow rather than emit non-JSON Infinity/NaN.
    json.dumps(out,allow_nan=False)
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode',choices=FIELDS);ap.add_argument('data',help='JSON object; SI units')
    a=ap.parse_args()
    try:
        result=calculate(a.mode,json.loads(a.data,parse_constant=lambda s: (_ for _ in ()).throw(ValueError('non-finite JSON'))))
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 1 if result['status']=='infeasible' else 0
    except (ValueError,TypeError,OverflowError) as exc:
        print(json.dumps({'status':'invalid_input','error':str(exc)},ensure_ascii=False));return 2
if __name__=='__main__':sys.exit(main())
