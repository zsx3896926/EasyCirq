#!/usr/bin/env python3
"""Battery-side duty-cycle estimate, not a power-converter or lifetime validator.

Usage: python power_budget.py budget.json
Required JSON: capacity_Ah, usable_fraction, current_basis="battery_input",
sleep_current_A, states=[{name,current_A,duration_s,events_per_day}].
Optional: target_days. States must be disjoint TOTAL battery-input currents;
sleep occupies the rest of a 24-hour representative day. No device defaults.
Exit 0: model calculated; 1: supplied target missed; 2: invalid input.
"""
import argparse
import json
import math
import sys


def unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f'duplicate JSON key: {key}')
        data[key] = value
    return data


def read_json(path):
    with open(path, 'rb') as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('input exceeds 2 MB')
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def number(value, name, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name}: finite number required')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name}: {"positive" if positive else "nonnegative"} required')
    return float(value)


def fields(data, required, optional=()):
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    missing = set(required) - data.keys()
    extra = data.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f'missing={sorted(missing)}, unknown={sorted(extra)}')


def analyze(data):
    fields(data, ['capacity_Ah', 'usable_fraction', 'current_basis', 'sleep_current_A', 'states'], ['target_days'])
    if data['current_basis'] != 'battery_input':
        raise ValueError('convert every state to TOTAL battery-input current first')
    capacity = number(data['capacity_Ah'], 'capacity_Ah', True)
    usable = number(data['usable_fraction'], 'usable_fraction', True)
    if usable > 1:
        raise ValueError('usable_fraction must be <= 1')
    sleep = number(data['sleep_current_A'], 'sleep_current_A')
    if not isinstance(data['states'], list) or len(data['states']) > 1000:
        raise ValueError('states must be a list of at most 1000 entries')
    rows, names, durations, charges = [], set(), [], []
    for index, state in enumerate(data['states']):
        fields(state, ['name', 'current_A', 'duration_s', 'events_per_day'])
        name = state['name']
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError(f'states[{index}]: unique nonempty name required')
        names.add(name)
        current = number(state['current_A'], f'{name}.current_A')
        duration = number(state['duration_s'], f'{name}.duration_s', True)
        count = number(state['events_per_day'], f'{name}.events_per_day')
        seconds = duration * count
        charge = current * seconds / 3600
        if not math.isfinite(seconds) or not math.isfinite(charge):
            raise ValueError('arithmetic overflow')
        durations.append(seconds)
        charges.append(charge)
        rows.append({'name': name, 'seconds_per_day': seconds, 'Ah_per_day': charge})
    active = math.fsum(durations)
    if active > 86400:
        raise ValueError('disjoint active states exceed 24 hours per day')
    sleep_seconds = 86400 - active
    rows.append({'name': '(remaining sleep)', 'seconds_per_day': sleep_seconds,
                 'Ah_per_day': sleep * sleep_seconds / 3600})
    daily = math.fsum(charges + [rows[-1]['Ah_per_day']])
    days = capacity * usable / daily if daily > 0 else None
    target = number(data['target_days'], 'target_days', True) if 'target_days' in data else None
    meets = days >= target if target is not None and days is not None else None
    result = {'status': 'target_missed' if meets is False else ('calculated' if days is not None else 'insufficient_model'),
              'average_current_A': daily / 24, 'Ah_per_day': daily, 'estimated_days': days,
              'target_days': target, 'model_meets_target': meets, 'states': rows,
              'board_verified': False, 'lifetime_verified': False,
              'assumptions': 'Disjoint representative daily states; total battery-input current; explicit usable capacity fraction.',
              'not_checked': ['input voltage and converter dropout/startup', 'peak current and battery impedance',
                              'time-varying efficiency and temperature', 'self-discharge/aging curves',
                              'abnormal connection retries and real lifetime']}
    if daily == 0:
        result['warning'] = 'Zero modeled consumption cannot establish infinite lifetime or a passed target.'
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('budget')
    args = parser.parse_args()
    try:
        result = analyze(read_json(args.budget))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if result['status'] == 'target_missed' else 0
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
