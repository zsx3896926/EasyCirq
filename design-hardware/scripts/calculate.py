#!/usr/bin/env python3
"""Small SI-unit engineering calculations; no network/EDA/file writes.

Usage: python calculate.py MODE 'JSON'
Modes and required JSON fields:
 led: vs_min_V, vs_max_V, vf_min_V, vf_max_V, r_ohm, r_tol
 divider: vin_min_V, vin_max_V, r_top_ohm, r_bottom_ohm, r_top_tol, r_bottom_tol
 i2c: v_pullup_max_V, vol_max_V, iol_A, c_bus_max_F, tr_max_s, r_tol
 ldo: vin_min_V, vin_max_V, vout_min_V, vout_max_V, iout_max_A,
      iq_max_A, dropout_max_V
 buck: vin_min_V, vin_max_V, vout_V, iout_max_A, fsw_min_Hz,
       efficiency, ripple_ratio, vout_ripple_max_V
 boost: vin_min_V, vin_max_V, vout_V, iout_max_A, fsw_min_Hz,
        efficiency, ripple_ratio, vout_ripple_max_V
 adc_settle: r_source_ohm, r_switch_ohm, c_ext_F, c_sample_F,
             t_sample_s, bits, vref_V
 current_sense: shunt_ohm, shunt_tol, i_max_A, gain, gain_tol,
                offset_max_V, adc_vref_V, adc_bits
 wire: length_m, current_A, width_m, copper_thickness_um, temp_c,
       max_current_density_A_per_mm2
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
 'buck': 'vin_min_V vin_max_V vout_V iout_max_A fsw_min_Hz efficiency ripple_ratio vout_ripple_max_V'.split(),
 'boost': 'vin_min_V vin_max_V vout_V iout_max_A fsw_min_Hz efficiency ripple_ratio vout_ripple_max_V'.split(),
 'adc_settle': 'r_source_ohm r_switch_ohm c_ext_F c_sample_F t_sample_s bits vref_V'.split(),
 'current_sense': 'shunt_ohm shunt_tol i_max_A gain gain_tol offset_max_V adc_vref_V adc_bits'.split(),
 'wire': 'length_m current_A width_m copper_thickness_um temp_c max_current_density_A_per_mm2'.split(),
}

def calculate(mode, data):
    if mode not in FIELDS or not isinstance(data,dict):
        raise ValueError('known mode and JSON object required')
    missing=set(FIELDS[mode])-data.keys(); extra=data.keys()-set(FIELDS[mode])
    if missing or extra: raise ValueError(f'missing={sorted(missing)}, unknown={sorted(extra)}')
    for k,v in data.items():
        if type(v) not in (float,int) or not math.isfinite(v):
            raise ValueError(f'{k}: finite number required')
        if v<0 and k!='temp_c': raise ValueError(f'{k}: must be nonnegative')
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
    elif mode=='ldo':
        positive('vin_min_V','vout_min_V')
        head=d['vin_min_V']-d['vout_max_V']-d['dropout_max_V']
        regulated_possible=head>=0
        out.update(status='calculated' if regulated_possible else 'infeasible',
          dropout_margin_min_V=head,
          dissipation_estimate_max_W=(d['vin_max_V']-d['vout_min_V'])*d['iout_max_A']+d['vin_max_V']*d['iq_max_A'] if regulated_possible else None,
          assumptions='Bounded DC regulated model; no dynamic/current-limit/stability/reverse-current/thermal validation. Dissipation withheld if regulation fails the supplied dropout bound.')
    elif mode=='buck':
        positive('vin_min_V','vin_max_V','vout_V','iout_max_A','fsw_min_Hz','vout_ripple_max_V')
        if not 0<d['efficiency']<=1:raise ValueError('efficiency: require 0 < efficiency <= 1')
        if not 0<d['ripple_ratio']<1:raise ValueError('ripple_ratio: require 0 < ripple_ratio < 1')
        feasible=d['vin_min_V']*d['efficiency']>d['vout_V'] and d['vin_max_V']>d['vout_V']
        if feasible:
            duty_max=d['vout_V']/(d['vin_min_V']*d['efficiency'])
            duty_min=d['vout_V']/(d['vin_max_V']*d['efficiency'])
            ripple=d['ripple_ratio']*d['iout_max_A']
            l_min=d['vout_V']*(d['vin_max_V']-d['vout_V'])/(ripple*d['fsw_min_Hz']*d['vin_max_V'])
            i_peak=d['iout_max_A']+ripple/2
            i_rms=math.sqrt(d['iout_max_A']**2+ripple**2/12)
            c_out_min=ripple/(8*d['fsw_min_Hz']*d['vout_ripple_max_V'])
            out.update(status='calculated',duty_max=duty_max,duty_min=duty_min,
              inductor_ripple_A=ripple,inductor_min_H=l_min,inductor_peak_A=i_peak,
              inductor_rms_A=i_rms,output_cap_min_F=c_out_min,
              output_cap_rms_A=ripple/math.sqrt(12),
              input_cap_rms_A=d['iout_max_A']*math.sqrt(duty_max*(1-duty_max)),
              switch_voltage_max_V=d['vin_max_V'],switch_current_peak_A=i_peak,
              assumptions='Ideal CCM buck power stage with lumped efficiency in D=Vout/(Vin*eta); no DCR, diode drop, dead time, compensation, transient, thermal or EMI validation. Inductor ripple is taken as ripple_ratio*Iout(max); L_min uses Vin(max). Verify against the selected controller datasheet.')
        else:
            out.update(status='infeasible',reason='Buck cannot regulate when Vin(min)*efficiency <= Vout or Vin(max) <= Vout',
              duty_max=None,duty_min=None,inductor_ripple_A=None,inductor_min_H=None,
              inductor_peak_A=None,inductor_rms_A=None,output_cap_min_F=None,
              output_cap_rms_A=None,input_cap_rms_A=None,switch_voltage_max_V=None,
              switch_current_peak_A=None,
              assumptions='Topology feasibility only; no component selection performed.')
    elif mode=='boost':
        positive('vin_min_V','vin_max_V','vout_V','iout_max_A','fsw_min_Hz','vout_ripple_max_V')
        if not 0<d['efficiency']<=1:raise ValueError('efficiency: require 0 < efficiency <= 1')
        if not 0<d['ripple_ratio']<1:raise ValueError('ripple_ratio: require 0 < ripple_ratio < 1')
        feasible=d['vin_min_V']*d['efficiency']<d['vout_V'] and d['vin_max_V']*d['efficiency']<d['vout_V']
        if feasible:
            duty_max=1-d['vin_min_V']*d['efficiency']/d['vout_V']
            duty_min=1-d['vin_max_V']*d['efficiency']/d['vout_V']
            v_peak=2*d['vout_V']/(3*d['efficiency'])
            candidates=[d['vin_min_V'],d['vin_max_V']]
            if d['vin_min_V']<v_peak<d['vin_max_V']:candidates.append(v_peak)
            l_required=[]
            for vin in candidates:
                i_in=d['vout_V']*d['iout_max_A']/(vin*d['efficiency'])
                l_required.append(vin*(1-vin*d['efficiency']/d['vout_V'])/(d['fsw_min_Hz']*d['ripple_ratio']*i_in))
            l_min=max(l_required)
            peaks=[];rms=[];deltas=[]
            for vin in candidates:
                i_in=d['vout_V']*d['iout_max_A']/(vin*d['efficiency'])
                delta=vin*(1-vin*d['efficiency']/d['vout_V'])/(d['fsw_min_Hz']*l_min)
                deltas.append(delta);peaks.append(i_in+delta/2);rms.append(math.sqrt(i_in**2+delta**2/12))
            i_in_max=d['vout_V']*d['iout_max_A']/(d['vin_min_V']*d['efficiency'])
            c_out_min=d['iout_max_A']*duty_max/(d['fsw_min_Hz']*d['vout_ripple_max_V'])
            out.update(status='calculated',duty_max=duty_max,duty_min=duty_min,
              input_current_max_A=i_in_max,inductor_ripple_max_A=max(deltas),
              inductor_min_H=l_min,inductor_peak_A=max(peaks),inductor_rms_A=max(rms),
              output_cap_min_F=c_out_min,input_cap_rms_A=max(deltas)/math.sqrt(12),
              switch_voltage_max_V=d['vout_V'],switch_current_peak_A=max(peaks),
              diode_current_avg_A=d['iout_max_A'],
              assumptions='Ideal CCM boost with lumped efficiency in D=1-Vin*eta/Vout; no DCR, diode drop, leakage inductance, compensation, transient, thermal or EMI validation. L_min and peak current are evaluated at Vin endpoints and at Vin=2*Vout*eta/3 where ripple is worst. Verify against the selected controller datasheet.')
        else:
            out.update(status='infeasible',reason='Boost cannot regulate when Vin*efficiency >= Vout at either input extreme',
              duty_max=None,duty_min=None,input_current_max_A=None,inductor_ripple_max_A=None,
              inductor_min_H=None,inductor_peak_A=None,inductor_rms_A=None,
              output_cap_min_F=None,input_cap_rms_A=None,switch_voltage_max_V=None,
              switch_current_peak_A=None,diode_current_avg_A=None,
              assumptions='Topology feasibility only; no component selection performed.')
    elif mode=='adc_settle':
        positive('c_ext_F','c_sample_F','t_sample_s','vref_V')
        if d['r_source_ohm']+d['r_switch_ohm']<=0:raise ValueError('r_source_ohm + r_switch_ohm must be positive')
        if not (isinstance(d['bits'],int) or (isinstance(d['bits'],float) and d['bits'].is_integer())):raise ValueError('bits: integer required')
        bits=int(d['bits'])
        if not 1<=bits<=32:raise ValueError('bits: require 1..32')
        tau=(d['r_source_ohm']+d['r_switch_ohm'])*(d['c_ext_F']+d['c_sample_F'])
        error_fraction=math.exp(-d['t_sample_s']/tau)
        lsb=d['vref_V']/(2**bits)
        error_lsb=error_fraction*(2**bits)
        required_tau=d['t_sample_s']/((bits+1)*math.log(2))
        settled=error_lsb<=0.5
        out.update(status='calculated' if settled else 'insufficient_settling',
          tau_upper_s=tau,settling_error_fraction=error_fraction,
          settling_error_LSB_full_scale=error_lsb,lsb_V=lsb,
          required_tau_for_0p5LSB_s=required_tau,
          max_total_resistance_for_0p5LSB_ohm=required_tau/(d['c_ext_F']+d['c_sample_F']),
          assumptions='Conservative first-order bound tau=(Rsource+Rswitch)*(Cext+Csample); full-scale step, constant switch resistance, no charge injection, leakage, noise, dielectric absorption or signal change during sampling. 0.5 LSB is a settling criterion, not total ADC accuracy.')
    elif mode=='current_sense':
        positive('shunt_ohm','i_max_A','gain','adc_vref_V')
        if not (isinstance(d['adc_bits'],int) or (isinstance(d['adc_bits'],float) and d['adc_bits'].is_integer())):raise ValueError('adc_bits: integer required')
        adc_bits=int(d['adc_bits'])
        if not 1<=adc_bits<=32:raise ValueError('adc_bits: require 1..32')
        v_shunt=d['shunt_ohm']*d['i_max_A']
        v_out=v_shunt*d['gain']
        lsb=d['adc_vref_V']/(2**adc_bits)
        lsb_current=lsb/(d['shunt_ohm']*d['gain'])
        components={
          'shunt_tolerance_A':d['i_max_A']*d['shunt_tol'],
          'gain_tolerance_A':d['i_max_A']*d['gain_tol'],
          'offset_A':d['offset_max_V']/(d['shunt_ohm']*d['gain']),
          'quantization_A':lsb_current/2,
        }
        rss=math.sqrt(sum(x*x for x in components.values()))
        worst=sum(components.values())
        headroom=d['adc_vref_V']-v_out
        out.update(status='calculated' if headroom>=0 else 'infeasible',
          shunt_voltage_max_V=v_shunt,output_voltage_max_V=v_out,adc_headroom_V=headroom,
          shunt_power_max_W=d['i_max_A']**2*d['shunt_ohm'],lsb_V=lsb,lsb_A=lsb_current,
          error_components_A=components,full_scale_error_A_rss=rss,
          full_scale_error_A_worst=worst,
          full_scale_error_percent_rss=100*rss/d['i_max_A'],
          assumptions='DC full-scale error budget. Shunt tolerance and gain tolerance are relative; offset_max_V is referred to the amplifier/ADC output. RSS assumes independent errors; worst-case is a linear sum. Excludes temp drift, CMRR, nonlinearity, noise, reference error, self-heating and layout parasitics. Headroom<0 is a blocking scaling error.')
    elif mode=='wire':
        positive('length_m','current_A','width_m','copper_thickness_um','max_current_density_A_per_mm2')
        if not -50<=d['temp_c']<=200:raise ValueError('temp_c: require -50..200 C')
        area_mm2=d['width_m']*d['copper_thickness_um']
        area_m2=area_mm2*1e-6
        rho=1.72e-8*(1+0.00393*(d['temp_c']-20))
        resistance=rho*d['length_m']/area_m2
        drop=d['current_A']*resistance
        power=d['current_A']**2*resistance
        density=d['current_A']/area_mm2
        out.update(status='calculated' if density<=d['max_current_density_A_per_mm2'] else 'infeasible',
          resistivity_ohm_m=rho,resistance_ohm=resistance,voltage_drop_V=drop,
          power_loss_W=power,cross_section_mm2=area_mm2,
          current_density_A_per_mm2=density,
          assumptions='Uniform DC current in a rectangular copper bar at the stated temperature; excludes pads, via/barrel resistance, connectors, skin/proximity effect, thermal coupling and fusing. The current-density limit is a user-supplied screening criterion, not a universal design rule.')
    else:
        raise ValueError('known mode required')
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
        return 1 if result['status'] in ('infeasible','insufficient_settling') else 0
    except (ValueError,TypeError,OverflowError) as exc:
        print(json.dumps({'status':'invalid_input','error':str(exc)},ensure_ascii=False));return 2
if __name__=='__main__':sys.exit(main())
