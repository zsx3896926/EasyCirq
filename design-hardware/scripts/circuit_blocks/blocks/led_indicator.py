"""F1 — LED current-limit resistor and indicator interface.

Topology variants (``control`` × ``resistor_position``):

* ``always_on``        VCC -> [R] -> LED -> GND (or VCC -> LED -> [R] -> GND)
* ``low_side_switch``  VCC -> [R] -> LED -> SW   (external switch sinks to GND)
* ``high_side_switch`` VSW -> [R] -> LED -> GND  (external switch feeds VSW)

The resistor is chosen from a declared standard series and tolerance.  All
worst-case currents are computed from the *declared ranges* of supply, LED Vf
and switch drop, with the resistor at both tolerance endpoints.  A point
(nominal-only) Vf is rejected: LED Vf varies over temperature and batch, so the
module reports ``needs_device_facts`` instead of treating a nominal value as a
bound.

The module never claims that a GPIO can drive the LED directly unless the
caller declares the switch's sink/source capability and voltage drop, and it
never picks or names an LED part (MPN/library id stay unbound).
"""
from __future__ import annotations

from fractions import Fraction

from ..errors import InputInvalid, NeedsDeviceFacts, NoFeasibleSolution, Unsupported
from ..eseries import values as series_values
from ..numeric import format_number, to_json_number
from ..ranges import Interval
from ..units import quantity_json
from .base import Block


class LedIndicator(Block):
    MODULE_TYPE = 'led_indicator'
    TEMPLATE_VERSION = '1.0.0'
    TITLE = 'LED current-limit and indicator interface'
    SUMMARY = ('Chooses a standard current-limiting resistor for an LED from declared '
               'supply/Vf/tolerance ranges, recomputes worst-case currents and resistor '
               'power, and emits the topology-specific net/port contract.')
    TOPOLOGY = 'series resistor + LED, optionally driven by an external low-side or high-side switch'
    APPLICABILITY = (
        'single LED indicator (one die, one series resistor)',
        'DC or slow PWM; switching loss is not modelled',
        'LED Vf declared as a range covering temperature and batch spread',
    )
    NON_APPLICABILITY = (
        'multi-LED strings or parallel LEDs without individual ballast',
        'constant-current / boost / buck LED drivers',
        'RGB LEDs with different forward voltages sharing one resistor',
        'high-frequency PWM where capacitance and switching loss dominate',
    )
    REQUIRED_DEVICE_FACTS = (
        'LED forward-voltage range over temperature/batch at the operating current',
        'LED absolute maximum continuous forward current',
        'switch (GPIO/transistor) sink or source current capability and voltage drop when closed',
    )
    SOURCES = (
        {'document': 'IEC 60063 preferred number series (E6/E12/E24/E48/E96)',
         'why': 'standard resistor values'},
        {'document': 'LED manufacturer datasheet (exact part)',
         'why': 'Vf range, absolute maximum current, temperature coefficient'},
        {'document': 'MCU/transistor datasheet or declared driver budget',
         'why': 'sink/source current and output-low/high voltage'},
    )
    INPUT_SCHEMA = {
        'supply_voltage': {
            'kind': 'range', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'Supply rail range at the high side of the LED path (V).'},
        'led_vf': {
            'kind': 'range', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'LED forward voltage range at the operating current over temperature/batch (V).'},
        'target_current': {
            'kind': 'quantity', 'family': 'current', 'required': True, 'positive': True,
            'doc': 'Desired nominal operating current (A).'},
        'max_current': {
            'kind': 'quantity', 'family': 'current', 'required': True, 'positive': True,
            'doc': 'Hard upper bound on forward current including tolerance worst case (A).'},
        'min_current': {
            'kind': 'quantity', 'family': 'current', 'positive': True,
            'doc': 'Optional hard lower bound so the indicator stays visible at worst case (A).'},
        'led_max_current': {
            'kind': 'quantity', 'family': 'current', 'positive': True,
            'doc': 'LED datasheet absolute maximum continuous forward current (A); required for ready_abstract.'},
        'series': {
            'kind': 'enum', 'values': ['E6', 'E12', 'E24', 'E48', 'E96', 'explicit'],
            'default': 'E24', 'doc': 'Standard resistor series, or "explicit" with allowed_values.'},
        'allowed_values': {
            'kind': 'array', 'items': {'kind': 'quantity', 'family': 'resistance'},
            'doc': 'Explicit allowed resistor values (ohm); required when series is "explicit".'},
        'value_range': {
            'kind': 'range', 'family': 'resistance', 'positive': True,
            'doc': 'Optional allowed resistance window from BOM/package reality (ohm).'},
        'resistor_tolerance_pct': {
            'kind': 'quantity', 'family': 'percent', 'required': True, 'nonnegative': True,
            'doc': 'Resistor tolerance (±%) used for the worst-case current.'},
        'resistor_power_rating': {
            'kind': 'quantity', 'family': 'power', 'positive': True,
            'doc': 'Optional package power rating (W); if given it is checked, not silently raised.'},
        'power_derating_pct': {
            'kind': 'quantity', 'family': 'percent', 'default': 50, 'nonnegative': True,
            'doc': 'Required derating of the resistor rating at worst case (%).'},
        'control': {
            'kind': 'enum', 'values': ['always_on', 'low_side_switch', 'high_side_switch'],
            'default': 'low_side_switch',
            'doc': 'How the LED path is completed.'},
        'resistor_position': {
            'kind': 'enum', 'values': ['supply_side', 'ground_side'], 'default': 'supply_side',
            'doc': 'Resistor between rail and anode (supply_side) or between cathode and return (ground_side).'},
        'switch_facts': {
            'kind': 'object',
            'fields': {
                'sink_current_max': {'kind': 'quantity', 'family': 'current', 'positive': True,
                                     'doc': 'Maximum current the switch can sink (A).'},
                'source_current_max': {'kind': 'quantity', 'family': 'current', 'positive': True,
                                       'doc': 'Maximum current the switch can source (A).'},
                'voltage_drop': {'kind': 'range', 'family': 'voltage', 'nonnegative': True,
                                 'doc': 'Voltage across the closed switch (V).'},
                'declared_by': {'kind': 'enum', 'values': ['user', 'datasheet'], 'default': 'user',
                                'doc': 'Provenance of the switch facts.'},
            },
            'doc': 'Switch/GPIO drive capability; required for switched control modes.'},
        'objective': {
            'kind': 'enum', 'values': ['current_error', 'min_power', 'max_resistance'],
            'default': 'current_error',
            'doc': 'Deterministic selection objective after hard constraints pass.'},
        'notes': {'kind': 'string', 'doc': 'Free-form note copied into the result.'},
    }
    EXAMPLE_INPUT = {
        'supply_voltage': {'min': 4.75, 'max': 5.25},
        'led_vf': {'min': 1.8, 'max': 2.2},
        'target_current': '5mA',
        'max_current': '8mA',
        'min_current': '3mA',
        'led_max_current': '25mA',
        'series': 'E24',
        'resistor_tolerance_pct': 1,
        'control': 'low_side_switch',
        'resistor_position': 'supply_side',
        'switch_facts': {
            'sink_current_max': '10mA',
            'voltage_drop': {'min': 0, 'max': 0.4},
            'declared_by': 'user',
        },
    }

    # ------------------------------------------------------------------
    def compute(self, draft, inputs):
        supply = inputs.interval('supply_voltage')
        vf = inputs.interval('led_vf')
        target = inputs.quantity('target_current')
        max_current = inputs.quantity('max_current')
        min_current = _optional_quantity(inputs, 'min_current')
        led_max_current = _optional_quantity(inputs, 'led_max_current')
        control = inputs.get('control')
        position = inputs.get('resistor_position')
        tolerance_pct = inputs.quantity('resistor_tolerance_pct')
        tolerance = tolerance_pct / 100
        derating = inputs.quantity('power_derating_pct') / 100
        objective = inputs.get('objective')
        notes = inputs.get('notes')

        if vf.width == 0:
            raise NeedsDeviceFacts(
                ['led_vf range (temperature/batch spread)'],
                'led_vf is a point value; an LED forward voltage must be declared as a '
                'range over temperature and batch before a worst-case current is meaningful')

        drop, switch = self._switch_facts(inputs, control, draft)
        v_headroom_min = supply.lo - vf.hi - drop.hi
        if v_headroom_min <= 0:
            raise NoFeasibleSolution(
                'supply cannot forward-bias the LED at the worst case: '
                'V_supply_min=%s V, Vf_max=%s V, switch drop max=%s V'
                % (format_number(supply.lo), format_number(vf.hi), format_number(drop.hi)),
                bounds={'v_headroom_min': to_json_number(v_headroom_min)})

        candidates = self._candidates(inputs)
        if not candidates:
            raise InputInvalid('no resistor candidates: the declared series/value_range is empty')

        # I_max <= max_current  =>  R >= (Vs_hi - Vf_lo - Vdrop_lo) / (Imax*(1-tol))
        # I_min >= min_current  =>  R <= (Vs_lo - Vf_hi - Vdrop_hi) / (Imin*(1+tol))
        lower = (supply.hi - vf.lo - drop.lo) / (max_current * (1 - tolerance))
        upper = None
        if min_current is not None:
            upper = (supply.lo - vf.hi - drop.hi) / (min_current * (1 + tolerance))
            if lower > upper:
                raise NoFeasibleSolution(
                    'no resistance can keep the LED current between %s A and %s A: '
                    'the upper current bound needs R >= %s ohm while the lower bound needs R <= %s ohm'
                    % (format_number(min_current), format_number(max_current),
                       format_number(lower), format_number(upper)),
                    bounds={'r_min': to_json_number(lower), 'r_max': to_json_number(upper)})

        allowed = [value for value in candidates
                   if value >= lower and (upper is None or value <= upper)]
        if not allowed:
            window = ('[%s, %s] ohm' % (format_number(lower), format_number(upper))
                      if upper is not None else '>= %s ohm' % format_number(lower))
            raise NoFeasibleSolution(
                'no standard resistor in the declared series lies in the feasible window %s'
                % window,
                bounds={'r_min': to_json_number(lower),
                        'r_max': to_json_number(upper) if upper is not None else None})

        nominal_v = supply.nominal - vf.nominal - drop.nominal
        if nominal_v <= 0:
            raise NoFeasibleSolution('nominal headroom is not positive; cannot choose a resistor')
        target_resistance = nominal_v / target
        selected, ranking = self._select(allowed, objective, target_resistance, tolerance,
                                         supply, vf, drop, max_current, min_current,
                                         led_max_current, inputs, target)
        if selected is None:
            raise NoFeasibleSolution(
                'no candidate satisfies the LED/switch current and resistor-power constraints; '
                'tighten the declared current window or change the supply/LED')

        r_nom = selected
        r_min = r_nom * (1 - tolerance)
        r_max = r_nom * (1 + tolerance)
        v_max_resistor = supply.hi - vf.lo - drop.lo
        i_max = v_max_resistor / r_min
        i_min = (supply.lo - vf.hi - drop.hi) / r_max
        i_nom = nominal_v / r_nom
        p_max = v_max_resistor ** 2 / r_min
        required_rating = p_max / (1 - derating) if derating < 1 else p_max
        declared_rating = _optional_quantity(inputs, 'resistor_power_rating')
        margin_max = max_current - i_max
        margin_min = (i_min - min_current) if min_current is not None else None

        if led_max_current is not None and i_max > led_max_current:
            raise NoFeasibleSolution(
                'worst-case current %s A exceeds the LED absolute maximum %s A'
                % (format_number(i_max), format_number(led_max_current)))
        if declared_rating is not None and required_rating > declared_rating:
            raise NoFeasibleSolution(
                'the declared %s W resistor is insufficient: worst-case dissipation is %s W '
                'and the declared derating requires a %s W rating'
                % (format_number(declared_rating), format_number(p_max),
                   format_number(required_rating)))

        # ---- components ---------------------------------------------
        if position == 'supply_side':
            pins = [{'name': '1', 'semantic': 'supply_side'},
                    {'name': '2', 'semantic': 'led_anode_side'}]
        else:
            pins = [{'name': '1', 'semantic': 'led_cathode_side'},
                    {'name': '2', 'semantic': 'return_side'}]
        resistor = draft.component(
            'led_current_limit', 'resistor',
            value=r_nom, tolerance_pct=tolerance_pct,
            series=inputs.get('series') if inputs.get('series') != 'explicit' else None,
            power_rating_w=required_rating,
            voltage_rating_v=max(supply.hi, Fraction(0)),
            pins=pins,
            requirements={
                'worst_case_power_w': quantity_json(p_max, 'power'),
                'required_power_rating_w': quantity_json(required_rating, 'power'),
                'derating_pct': quantity_json(derating * 100, 'percent'),
            },
            candidates=[{'nominal': value} for value in ranking],
            notes='Standard value selected deterministically; package power rating is a '
                  'requirement, not a bound part.')
        led = draft.component(
            'indicator', 'led', value=None, polarity='anode_cathode',
            pins=[{'name': 'A', 'semantic': 'anode'}, {'name': 'K', 'semantic': 'cathode'}],
            requirements={
                'vf_range': vf.as_json('voltage'),
                'target_current': quantity_json(target, 'current'),
                'max_current': quantity_json(max_current, 'current'),
                'min_current': (quantity_json(min_current, 'current')
                                if min_current is not None else None),
                'absolute_max_current': (quantity_json(led_max_current, 'current')
                                         if led_max_current is not None else None),
            },
            notes='Abstract LED; Vf range and current limits are requirements for later part selection.')

        # ---- nets, ports, endpoints ---------------------------------
        vcc = draft.net('VCC', role='power', scope='external', voltage_domain='supply')
        gnd = draft.net('GND', role='ground', scope='external')
        if control == 'low_side_switch':
            return_net = draft.net('SW_NODE', role='signal', scope='external',
                                   notes='Pulled to ground by the external low-side switch')
            source_net = vcc
        elif control == 'high_side_switch':
            return_net = gnd
            source_net = draft.net('VSW', role='power', scope='external',
                                   notes='Switched supply node fed by the external high-side switch')
        else:
            return_net = gnd
            source_net = vcc
        junction = draft.net('LED_A' if position == 'supply_side' else 'LED_K',
                             role='signal', scope='internal',
                             notes='Series junction between the LED and its ballast resistor')

        draft.port('VCC', 'input', 'power', net=vcc, voltage=supply,
                   description='LED supply rail'
                   if control != 'high_side_switch' else 'Continuous LED supply rail (not the switched node)')
        draft.port('GND', 'passive', 'ground', net=gnd, description='Ground return')
        if control == 'low_side_switch':
            draft.port('SW', 'output', 'switch', net=return_net,
                       voltage=Interval.point(0), current=Interval.point(i_max),
                       description='External low-side switch connects SW to GND and must sink '
                                   'up to the worst-case LED current')
        elif control == 'high_side_switch':
            draft.port('VSW', 'input', 'power', net=source_net, voltage=supply,
                       description='Switched supply driven by the external high-side switch')

        if position == 'supply_side':
            draft.connect(resistor['ref'], '1', source_net, 'supply_side')
            draft.connect(resistor['ref'], '2', junction, 'led_anode_side')
            draft.connect(led['ref'], 'A', junction, 'anode')
            draft.connect(led['ref'], 'K', return_net, 'cathode')
        else:
            draft.connect(led['ref'], 'A', source_net, 'anode')
            draft.connect(led['ref'], 'K', junction, 'cathode')
            draft.connect(resistor['ref'], '1', junction, 'led_cathode_side')
            draft.connect(resistor['ref'], '2', return_net, 'return_side')

        # ---- calculations ------------------------------------------
        draft.calculation(
            'feasible_resistance_window',
            'Resistance window that satisfies both current limits',
            'R >= (Vs_hi - Vf_lo - Vd_lo) / (Imax*(1-tol));  '
            'R <= (Vs_lo - Vf_hi - Vd_hi) / (Imin*(1+tol))',
            inputs={
                'supply_voltage': supply.as_json('voltage'),
                'led_vf': vf.as_json('voltage'),
                'switch_voltage_drop': drop.as_json('voltage'),
                'max_current': quantity_json(max_current, 'current'),
                'min_current': (quantity_json(min_current, 'current')
                                if min_current is not None else None),
                'resistor_tolerance_pct': quantity_json(tolerance_pct, 'percent'),
            },
            result={'min_ohm': to_json_number(lower),
                    'max_ohm': to_json_number(upper) if upper is not None else None},
            unit='ohm',
            method='closed-form interval bounds on the series-resistor equation',
            assumptions=['supply, Vf and switch drop are bounded exactly as declared',
                         'only the resistor tolerance is modelled as a resistance spread',
                         'Vf range is a terminal range, not an independent parameter'],
            not_modelled=['Vf temperature coefficient inside the declared range',
                          'switch drop dependence on current (a range is used)',
                          'resistor self-heating changing its value'])

        draft.calculation(
            'worst_case_current',
            'Worst-case LED current with the selected standard resistor',
            'I = (V_supply - Vf - V_drop) / R; extremes over declared ranges and R tolerance',
            inputs={
                'selected_resistance': quantity_json(r_nom, 'resistance'),
                'resistance_range': Interval(r_min, r_max).as_json('resistance'),
                'supply_voltage': supply.as_json('voltage'),
                'led_vf': vf.as_json('voltage'),
                'switch_voltage_drop': drop.as_json('voltage'),
            },
            result={'min_a': to_json_number(i_min), 'nominal_a': to_json_number(i_nom),
                    'max_a': to_json_number(i_max)},
            unit='A',
            limit={'max_current': quantity_json(max_current, 'current'),
                   'min_current': (quantity_json(min_current, 'current')
                                   if min_current is not None else None)},
            margin={'max_current_margin': quantity_json(margin_max, 'current'),
                    'min_current_margin': (quantity_json(margin_min, 'current')
                                           if margin_min is not None else None),
                    'target_current_error_pct': quantity_json((i_nom - target) / target * 100,
                                                              'percent')},
            assumptions=['worst case assumes independent extremes of supply, Vf and switch drop'],
            not_modelled=['LED dynamic resistance and thermal drift during operation',
                          'PWM average current if the switch is modulated'])

        draft.calculation(
            'resistor_power',
            'Worst-case resistor dissipation and required rating',
            'P = (Vs_hi - Vf_lo - Vd_lo)^2 / R_min;  rating >= P / (1 - derating)',
            inputs={
                'r_min': quantity_json(r_min, 'resistance'),
                'max_voltage_across_resistor': quantity_json(v_max_resistor, 'voltage'),
                'power_derating_pct': quantity_json(derating * 100, 'percent'),
            },
            result={'worst_case_power_w': to_json_number(p_max),
                    'required_power_rating_w': to_json_number(required_rating)},
            unit='W',
            limit={'declared_power_rating': (quantity_json(declared_rating, 'power')
                                             if declared_rating is not None else None)},
            margin={'rating_margin_w': (to_json_number(declared_rating - p_max)
                                        if declared_rating is not None else None)},
            method='exact rational arithmetic',
            assumptions=['resistor at its lower tolerance endpoint for maximum power'],
            not_modelled=['pulse power during PWM switching'])

        if switch is not None:
            capability = switch['sink'] if control == 'low_side_switch' else switch['source']
            direction = 'sink' if control == 'low_side_switch' else 'source'
            if capability is not None and capability < i_max:
                raise Unsupported(
                    'declared switch %s capability %s A is below the worst-case LED current %s A'
                    % (direction, format_number(capability), format_number(i_max)),
                    reasons=['switch %s capability %s A < worst-case LED current %s A'
                             % (direction, format_number(capability), format_number(i_max))])
            draft.calculation(
                'switch_current_check',
                'Switch/GPIO current capability check',
                'I_led_max <= I_switch_capability',
                inputs={'worst_case_led_current': quantity_json(i_max, 'current'),
                        'switch_capability': quantity_json(capability, 'current'),
                        'switch_direction': direction},
                result={'pass': True, 'margin_a': to_json_number(capability - i_max)},
                unit='A',
                margin={'margin_a': to_json_number(capability - i_max)},
                not_modelled=['GPIO output voltage variation above the declared current range',
                              'simultaneous switching of several LEDs on one port'])

        # ---- constraints and unknowns ------------------------------
        draft.constraint('resistor_series',
                         'Use a resistor from %s with tolerance ±%s%%.'
                         % (inputs.get('series'), format_number(tolerance_pct)),
                         kind='hard', applies_to=resistor['ref'])
        draft.constraint('max_current',
                         'Worst-case forward current must not exceed %s A.'
                         % format_number(max_current), kind='hard', applies_to=led['ref'])
        if min_current is not None:
            draft.constraint('min_current',
                             'Worst-case forward current must stay at or above %s A.'
                             % format_number(min_current), kind='hard', applies_to=led['ref'])
        if led_max_current is None:
            draft.constraint('led_abs_max_unverified',
                             'The LED absolute maximum continuous current was not supplied; the '
                             'max-current constraint is a design limit, not a datasheet check.',
                             kind='verification', applies_to=led['ref'], source='declaration')
            draft.unknown('led_absolute_max_current',
                          'LED absolute maximum continuous forward current is not declared',
                          impact='the design limit could still exceed the real LED rating',
                          how_to_resolve='declare led_max_current from the exact LED datasheet')
        else:
            draft.constraint('led_abs_max',
                             'Worst-case current must stay below the LED absolute maximum %s A.'
                             % format_number(led_max_current), kind='hard', applies_to=led['ref'])
        draft.constraint('resistor_rating',
                         'Use a resistor rated at least %s W at the declared derating.'
                         % format_number(required_rating), kind='hard', applies_to=resistor['ref'])
        draft.constraint('layout_loop',
                         'Keep the supply -> resistor -> LED -> return loop short; place the '
                         'resistor where its dissipation is acceptable.',
                         kind='layout', applies_to=resistor['ref'])
        draft.constraint('verify_extremes',
                         'Measure LED current at both supply extremes and at temperature extremes '
                         'after assembly; the Vf range must come from the exact LED datasheet.',
                         kind='verification', applies_to=led['ref'])
        if margin_max < max_current / 10:
            draft.constraint('thin_max_margin',
                             'Worst-case current margin to the maximum is only %s A; re-check '
                             'supply tolerance and Vf spread before release.'
                             % format_number(margin_max),
                             kind='advisory', applies_to=resistor['ref'])
        if min_current is not None and i_min < target / 2:
            draft.constraint('dim_worst_case',
                             'At worst case the LED sees %s A versus a %s A target; brightness may be low.'
                             % (format_number(i_min), format_number(target)),
                             kind='advisory', applies_to=led['ref'])

        # ---- evidence ----------------------------------------------
        draft.evidence('input_supply', 'user_declared',
                       'Supply range declared by the caller: %s..%s V.'
                       % (format_number(supply.lo), format_number(supply.hi)))
        draft.evidence('input_led_vf', 'user_declared',
                       'LED Vf range declared by the caller: %s..%s V.'
                       % (format_number(vf.lo), format_number(vf.hi)))
        draft.evidence('standard_series', 'standard',
                       'Resistor values taken from IEC 60063 series %s.'
                       % inputs.get('series'),
                       source={'document': 'IEC 60063', 'section': 'preferred number series',
                               'url': 'https://webstore.iec.ch/publication/593'})
        draft.evidence('derivation_current', 'derivation',
                       'Worst-case currents, resistance window and power are derived here with '
                       'exact rational interval arithmetic.')
        draft.assumption('Supply, Vf and switch drop extremes may occur simultaneously '
                         '(independent worst case).',
                         impact='conservative current bounds; a correlated worst case would be narrower')
        draft.assumption('Resistor self-heating is not modelled; the declared derating covers it.',
                         impact='at high dissipation the real resistance and temperature rise need board verification')

        if led_max_current is None:
            return 'needs_device_facts', [
                'LED absolute maximum continuous current is not declared; the design limit alone '
                'cannot prove the LED stays within its rating'], notes
        if margin_max < 0 or (margin_min is not None and margin_min < 0):
            raise NoFeasibleSolution('selected resistor violates a hard current bound after rounding')
        return 'ready_abstract', [], notes

    # ------------------------------------------------------------------
    def _switch_facts(self, inputs, control, draft):
        if control == 'always_on':
            return Interval.point(0), None
        if 'switch_facts' not in inputs:
            raise NeedsDeviceFacts(
                ['switch_facts'],
                'control=%r requires declared switch/GPIO capability (sink/source current and '
                'voltage drop); a GPIO output must not be assumed to drive the LED directly'
                % control)
        payload = inputs.obj('switch_facts')
        drop = payload.get('voltage_drop')
        if drop is None:
            raise NeedsDeviceFacts(['switch_facts.voltage_drop'],
                                   'switch voltage drop is required for a worst-case current calculation')
        declared_by = payload.get('declared_by', 'user')
        if control == 'low_side_switch' and payload.get('sink_current_max') is None:
            raise NeedsDeviceFacts(['switch_facts.sink_current_max'],
                                   'a low-side switch must declare how much current it can sink')
        if control == 'high_side_switch' and payload.get('source_current_max') is None:
            raise NeedsDeviceFacts(['switch_facts.source_current_max'],
                                   'a high-side switch must declare how much current it can source')
        draft.evidence('switch_capability_declared', 'user_declared',
                       'Switch capability supplied by the caller (%s).' % declared_by,
                       source={'document': 'caller declaration'}, verified=False)
        return drop, {'sink': payload.get('sink_current_max'),
                      'source': payload.get('source_current_max'),
                      'drop': drop, 'declared_by': declared_by}

    def _candidates(self, inputs):
        series = inputs.get('series')
        window = inputs.get('value_range')
        low = window.lo if window is not None else None
        high = window.hi if window is not None else None
        candidates = set()
        if series == 'explicit':
            explicit = inputs.get('allowed_values')
            if not explicit:
                raise InputInvalid('series="explicit" requires allowed_values',
                                   field='allowed_values')
            candidates.update(explicit)
        else:
            candidates.update(series_values(series, low, high))
        if window is not None:
            candidates = {value for value in candidates if window.contains(value)}
        return sorted(candidates)

    def _select(self, allowed, objective, target_resistance, tolerance, supply, vf, drop,
                max_current, min_current, led_max_current, inputs, target):
        declared_rating = _optional_quantity(inputs, 'resistor_power_rating')
        derating = inputs.quantity('power_derating_pct') / 100

        def score(value):
            r_min = value * (1 - tolerance)
            r_max = value * (1 + tolerance)
            i_max = (supply.hi - vf.lo - drop.lo) / r_min
            i_min = (supply.lo - vf.hi - drop.hi) / r_max
            if i_max > max_current:
                return None
            if min_current is not None and i_min < min_current:
                return None
            if led_max_current is not None and i_max > led_max_current:
                return None
            power = (supply.hi - vf.lo - drop.lo) ** 2 / r_min
            required_rating = power / (1 - derating) if derating < 1 else power
            if declared_rating is not None and required_rating > declared_rating:
                return None
            nominal = (supply.nominal - vf.nominal - drop.nominal) / value
            if objective == 'min_power':
                return (power, abs(value - target_resistance))
            if objective == 'max_resistance':
                return (-value, abs(nominal - target))
            return (abs(nominal - target) / target, power)

        ranked = []
        for value in allowed:
            key = score(value)
            if key is None:
                continue
            nominal = (supply.nominal - vf.nominal - drop.nominal) / value
            ranked.append({'key': key, 'value': value, 'nominal_current': nominal})
        ranked.sort(key=lambda item: (item['key'], item['value']))
        if not ranked:
            if declared_rating is not None:
                needs = []
                for value in allowed:
                    r_min = value * (1 - tolerance)
                    power = (supply.hi - vf.lo - drop.lo) ** 2 / r_min
                    needs.append(power / (1 - derating) if derating < 1 else power)
                raise NoFeasibleSolution(
                    'the declared %s W resistor is insufficient: the smallest available candidate '
                    'needs a %s W rating at the declared derating'
                    % (format_number(declared_rating), format_number(min(needs))),
                    bounds={'declared_rating_w': to_json_number(declared_rating),
                            'required_rating_w': to_json_number(min(needs))})
            return None, []
        return ranked[0]['value'], [item['value'] for item in ranked[:5]]


def _optional_quantity(inputs, name):
    return inputs.quantity(name) if name in inputs else None
