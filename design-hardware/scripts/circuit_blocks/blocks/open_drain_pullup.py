"""F3 — open-drain bus pull-up resistor (I2C-style, interface-mode aware).

An open-drain/open-collector line can only pull LOW; the HIGH level exists only
because of the pull-up resistor.  The legal pull-up interval therefore comes
from four independent hard bounds, all evaluated with exact Fractions:

* rise time (upper bound on R): ``R_max = t_rise / (k * C_bus_max)`` where the
  coefficient ``k`` belongs to the *declared rise-time definition*:
  ``ln(9)`` for 10 %..90 %, ``ln(7/3)`` for 30 %..70 % and
  ``ln((V_pu - V_IL)/(V_pu - V_IH))`` for a VIL->VIH measurement (evaluated at
  the worst-case (lowest) rail);
* sink current / low level (lower bound on R): the device can only guarantee
  ``V_OL <= V_OL_max`` while sinking at most ``I_OL``, so
  ``R_min = (V_pu_max - V_OL_min)/I_OL`` with ``V_OL_min = 0`` when only
  ``V_OL_max`` is declared.  The naive form ``(V_pu_min - V_OL_max)/I_OL``
  under-bounds the sink current and is deliberately not used;
* device sink-current capability (optional): ``R_min = V_pu_max / I_sink_max``;
* static-current budget: ``R_min = V_pu_max / I_budget`` (worst case is the
  maximum rail and the minimum resistor value).

Instead of one universal coefficient, an interface mode (``bus_spec``) selects
the rise-time limit, the bus-capacitance limit and the rise-time definition from
a data table.  The bundled *verified* fact file ``bus_i2c_um10204`` (NXP
UM10204, Rev. 7.0, Tables 10/11, Figure 38, Section 7.1) backs the I2C modes and
its source is copied into the result evidence; a module-level fallback table
keeps the generator usable when that fact file is absent.  Caller-declared
numbers still work: ``bus_spec='custom'`` takes an application-specific rise
time and definition, and the device ``V_OL``/``I_OL`` are always caller facts.

Passing the maths never proves the bus runs at a frequency: the module records
that explicitly (tLOW/tHIGH of the slowest device are separate datasheet facts)
and never claims "I2C 400 kHz guaranteed" from an RC number alone.  It also
cannot prove that the pull-up rail is safe for every device pin; that stays a
verification constraint.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction

from ..devices import evidence_for, fact_number, fact_source, load_fact, missing_keys
from ..errors import CircuitBlockError, InputInvalid, NeedsDeviceFacts, NoFeasibleSolution, Unsupported
from ..eseries import choose, values as series_values
from ..numeric import format_number, to_json_number
from ..ranges import Interval
from ..units import quantity_json
from .base import Block

#: Significant digits for the natural logarithm (Decimal.ln is correctly
#: rounded, so the coefficients are deterministic and no binary float decides
#: anything).
_LOG_PRECISION = 40

#: Verified fact file used for the I2C per-mode limits.  Loaded at runtime so the
#: numbers (and their primary source) are not duplicated in code.
_STANDARDS_FACT_ID = 'bus_i2c_um10204'

#: Human-readable interface names used in messages/evidence.
_MODE_LABELS = {
    'standard': 'I2C Standard-mode',
    'fast': 'I2C Fast-mode',
    'fast_plus': 'I2C Fast-mode Plus',
}

#: Data-driven fallback copy of the per-interface limits, used only when the
#: bundled verified fact file is unavailable.  Primary source: NXP UM10204,
#: "I2C-bus specification and user manual", Rev. 7.0 (1 October 2021),
#: Table 10 (I/O stages), Table 11 (bus lines) and Figure 38; rise/fall times
#: are measured 30 %..70 % of VDD, hence the ``30_70`` definition and the
#: 0.8473 = ln(7/3) coefficient of Section 7.1 equation 1.
FALLBACK_INTERFACE_TABLE = {
    'standard': {
        'interface': 'I2C Standard-mode (100 kbit/s)',
        'rise_time_max': Fraction(1000, 10 ** 9),
        'bus_cap_max': Fraction(400, 10 ** 12),
        'f_scl_max': Fraction(100000),
        'iol_min': Fraction(3, 1000),
        'vol_max': Fraction(4, 10),
        'rise_time_definition': '30_70',
        'source': {'document': 'NXP UM10204 I2C-bus specification and user manual',
                   'revision': 'Rev. 7.0 (1 October 2021)',
                   'section': 'Table 11 (bus lines) and Figure 38'},
    },
    'fast': {
        'interface': 'I2C Fast-mode (400 kbit/s)',
        'rise_time_max': Fraction(300, 10 ** 9),
        'bus_cap_max': Fraction(400, 10 ** 12),
        'f_scl_max': Fraction(400000),
        'iol_min': Fraction(3, 1000),
        'vol_max': Fraction(4, 10),
        'rise_time_definition': '30_70',
        'source': {'document': 'NXP UM10204 I2C-bus specification and user manual',
                   'revision': 'Rev. 7.0 (1 October 2021)',
                   'section': 'Table 11 (bus lines) and Figure 38'},
    },
    'fast_plus': {
        'interface': 'I2C Fast-mode Plus (1 Mbit/s)',
        'rise_time_max': Fraction(120, 10 ** 9),
        'bus_cap_max': Fraction(550, 10 ** 12),
        'f_scl_max': Fraction(1000000),
        'iol_min': Fraction(20, 1000),
        'vol_max': Fraction(4, 10),
        'rise_time_definition': '30_70',
        'source': {'document': 'NXP UM10204 I2C-bus specification and user manual',
                   'revision': 'Rev. 7.0 (1 October 2021)',
                   'section': 'Table 11 (bus lines) and Figure 38'},
    },
}


def _ln(value):
    """Natural logarithm of an exact positive Fraction, evaluated with Decimal."""
    value = value if isinstance(value, Fraction) else Fraction(value)
    if value <= 0:
        raise InputInvalid('logarithm argument must be positive')
    with localcontext() as context:
        context.prec = _LOG_PRECISION
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
        return Fraction(decimal_value.ln())


class OpenDrainPullup(Block):
    MODULE_TYPE = 'open_drain_pullup'
    TEMPLATE_VERSION = '1.0.0'
    TITLE = 'Open-drain bus pull-up resistor'
    SUMMARY = ('Selects a standard pull-up resistor for an open-drain/open-collector bus from '
               'declared rise-time, sink-current, static-budget, bus-capacitance and tolerance '
               'facts, using a data-driven per-interface limit table (I2C modes backed by the '
               'verified UM10204 fact file), and recomputes the worst-case rise time, static '
               'current and low-level voltage with margins.')
    TOPOLOGY = 'VCC -[pull-up resistor]- BUS (open-drain, bidirectional); GND return'
    APPLICABILITY = (
        'single-ended open-drain/open-collector bus segment with one pull-up resistor per line',
        'first-order RC rise from the low level towards the pull-up rail',
        'interface modes standard / fast / fast_plus from the UM10204 I2C-bus limits, or a '
        'custom rise-time limit with an explicit measurement definition',
    )
    NON_APPLICABILITY = (
        'push-pull buses, differential buses or active pull-up/accelerator circuits',
        'multi-drop segments whose capacitance changes with hot-plug events',
        'claiming a guaranteed bus frequency: clock/hold/setup times are per-device facts',
        'level shifting or a pull-up rail that exceeds a device input absolute maximum',
    )
    REQUIRED_DEVICE_FACTS = (
        'bus device VOL max at the declared IOL sink current (and the IOL test condition)',
        'bus capacitance range (Cb) of the segment',
        'allowed maximum rise time and its measurement definition (custom mode)',
        'static-current budget of the bus',
    )
    SOURCES = (
        {'document': 'NXP UM10204 I2C-bus specification and user manual, Rev. 7.0 '
                     '(1 October 2021), Tables 10/11, Figure 38, Section 7.1',
         'why': 'per-mode tr/Cb/fscl limits, VIL/VIH levels and the pull-up sizing equations'},
        {'document': 'IEC 60063 preferred number series (E6/E12/E24/E48/E96)',
         'why': 'standard resistor values'},
        {'document': 'bus device datasheet or declared VOL/IOL facts',
         'why': 'guaranteed low-level output voltage at its sink current'},
    )

    #: Capability declaration: the three I2C interface modes plus a caller-defined mode.
    BUS_SPEC_MODES = ('standard', 'fast', 'fast_plus', 'custom')

    INPUT_SCHEMA = {
        'supply_voltage': {
            'kind': 'range', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'Pull-up rail range (V); the BUS high level is established by this rail.'},
        'bus_spec': {
            'kind': 'enum', 'values': ['standard', 'fast', 'fast_plus', 'custom'],
            'default': 'custom',
            'doc': 'Interface mode. The three I2C modes select tr max, Cb max and the rise-time '
                   'definition from the UM10204 table; "custom" requires max_rise_time and '
                   'rise_time_definition.'},
        'bus_capacitance': {
            'kind': 'range', 'family': 'capacitance', 'positive': True,
            'doc': 'Total bus capacitance range Cb (F). Required for a ready result: without it '
                   'no rise-time bound exists and no bus frequency is guaranteed.'},
        'max_rise_time': {
            'kind': 'quantity', 'family': 'time', 'positive': True,
            'doc': 'Allowed maximum rise time (s); required when bus_spec is "custom" and must '
                   'not be supplied for an interface mode (the standard fixes it).'},
        'rise_time_definition': {
            'kind': 'enum', 'values': ['10_90', '30_70', 'vil_vih'],
            'doc': 'Rise-time measurement definition; required when bus_spec is "custom". It '
                   'changes the coefficient k: ln(9), ln(7/3) or a rail/threshold-dependent ln.'},
        'bus_v_il': {
            'kind': 'quantity', 'family': 'voltage', 'nonnegative': True,
            'doc': 'Bus input LOW threshold (V); required for the vil_vih definition and used for '
                   'the low-level margin when declared.'},
        'bus_v_ih': {
            'kind': 'quantity', 'family': 'voltage', 'positive': True,
            'doc': 'Bus input HIGH threshold (V); required for the vil_vih definition.'},
        'device': {
            'kind': 'object',
            'fields': {
                'vol_max': {
                    'kind': 'quantity', 'family': 'voltage', 'nonnegative': True,
                    'doc': 'Device maximum LOW-level output voltage VOL at IOL (V); required.'},
                'iol': {
                    'kind': 'quantity', 'family': 'current', 'positive': True,
                    'doc': 'Sink current IOL at which VOL_max is guaranteed (A); required.'},
                'sink_current_max': {
                    'kind': 'quantity', 'family': 'current', 'positive': True,
                    'doc': 'Optional device maximum sink current (A); adds a lower bound on R.'},
                'declared_by': {
                    'kind': 'enum', 'values': ['datasheet', 'user_declared'],
                    'default': 'user_declared',
                    'doc': 'Provenance of the VOL/IOL facts.'},
            },
            'doc': 'Open-drain bus device low-level facts. Required: the sink capability must '
                   'never be assumed.'},
        'static_current_budget': {
            'kind': 'quantity', 'family': 'current', 'positive': True,
            'doc': 'Maximum static current allowed through the pull-up while the bus is LOW (A); '
                   'required for the current budget bound.'},
        'series': {
            'kind': 'enum', 'values': ['E6', 'E12', 'E24', 'E48', 'E96', 'explicit'],
            'default': 'E24', 'doc': 'Resistor series, or "explicit" with allowed_values.'},
        'allowed_values': {
            'kind': 'array', 'items': {'kind': 'quantity', 'family': 'resistance'},
            'doc': 'Explicit allowed resistor values (ohm); required when series is "explicit".'},
        'value_range': {
            'kind': 'range', 'family': 'resistance', 'positive': True,
            'doc': 'Optional allowed resistance window from BOM/package reality (ohm).'},
        'resistor_tolerance_pct': {
            'kind': 'quantity', 'family': 'percent', 'required': True, 'nonnegative': True,
            'doc': 'Resistor tolerance (±%) used for the worst-case bounds.'},
        'objective': {
            'kind': 'enum', 'values': ['max_resistance', 'min_resistance'],
            'default': 'max_resistance',
            'doc': 'Deterministic selection objective; max_resistance minimises the static current.'},
        'notes': {'kind': 'string', 'doc': 'Free-form note copied into the result.'},
    }
    EXAMPLE_INPUT = {
        'supply_voltage': {'min': 3.0, 'max': 3.6},
        'bus_spec': 'fast',
        'bus_capacitance': {'min': '100pF', 'max': '200pF'},
        'bus_v_il': 0.9,
        'device': {
            'vol_max': 0.4,
            'iol': '3mA',
            'declared_by': 'datasheet',
        },
        'static_current_budget': '4mA',
        'series': 'E24',
        'resistor_tolerance_pct': 1,
    }

    # ------------------------------------------------------------------
    def compute(self, draft, inputs):
        notes = inputs.get('notes')
        supply = inputs.interval('supply_voltage')
        tolerance_pct = inputs.quantity('resistor_tolerance_pct')
        if tolerance_pct >= 100:
            raise InputInvalid('resistor tolerance must stay below 100%',
                               field='resistor_tolerance_pct')
        tolerance = tolerance_pct / 100

        specification = self._resolve_bus_spec(inputs, draft)
        bus_capacitance = self._require_bus_capacitance(inputs)
        device = self._require_device(inputs)
        vol_max = device.quantity('vol_max')
        iol = device.quantity('iol')
        sink_current_max = device.get('sink_current_max')
        budget = self._require_static_budget(inputs)

        definition = specification['rise_time_definition']
        coefficient = self._coefficient(inputs, definition, supply, draft)

        self._check_mode_limits(draft, specification, bus_capacitance, iol)

        # ---- legal interval -----------------------------------------
        rise_limit = specification['rise_time_max']
        r_upper = rise_limit / (coefficient['k_worst'] * bus_capacitance.hi * (1 + tolerance))

        lower_details = [
            ('device low level at IOL: R_min = (V_pu_max - VOL_min)/IOL',
             supply.hi / iol),
            ('static-current budget: R_min = V_pu_max/I_budget',
             supply.hi / budget),
        ]
        if sink_current_max is not None:
            lower_details.append(
                ('device sink-current capability: R_min = V_pu_max/I_sink_max',
                 supply.hi / sink_current_max))
        r_lower = max(bound for _, bound in lower_details) / (1 - tolerance)

        draft.calculation(
            'rise_time_bound',
            'Maximum pull-up resistance from the allowed rise time',
            'R_max = t_rise_max / (k * C_bus_max * (1 + tol));  k = ln(9) for 10%-90%, '
            'ln(7/3) for 30%-70%, ln((V_pu-V_IL)/(V_pu-V_IH)) for VIL->VIH',
            inputs={'max_rise_time': quantity_json(rise_limit, 'time'),
                    'bus_capacitance_max': quantity_json(bus_capacitance.hi, 'capacitance'),
                    'rise_time_definition': definition,
                    'coefficient_k': to_json_number(coefficient['k_worst']),
                    'resistor_tolerance_pct': quantity_json(tolerance_pct, 'percent')},
            result={'r_max_ohm': to_json_number(r_upper)},
            unit='ohm',
            limit={'max_rise_time': quantity_json(rise_limit, 'time')},
            margin=None,
            method='exact rational arithmetic with a Decimal-evaluated logarithm',
            assumptions=['first-order RC with one lumped bus capacitance',
                         'the rise time is measured with the declared definition'],
            not_modelled=['driver output capacitance and distributed bus capacitance',
                          'series resistors or bus switches in the segment'])
        draft.calculation(
            'current_bounds',
            'Minimum pull-up resistance from the sink-current and static-current bounds',
            'R_min = max(V_pu_max/IOL, V_pu_max/I_budget, V_pu_max/I_sink_max) / (1 - tol); '
            'V_OL_min is taken as 0 V when only V_OL_max is declared',
            inputs={'supply_voltage': supply.as_json('voltage'),
                    'iol': quantity_json(iol, 'current'),
                    'static_current_budget': quantity_json(budget, 'current'),
                    'sink_current_max': (quantity_json(sink_current_max, 'current')
                                         if sink_current_max is not None else None),
                    'resistor_tolerance_pct': quantity_json(tolerance_pct, 'percent')},
            result={'r_min_ohm': to_json_number(r_lower),
                    'bounds': [{'statement': statement, 'raw_ohm': to_json_number(bound)}
                               for statement, bound in lower_details]},
            unit='ohm',
            limit={'iol': quantity_json(iol, 'current'),
                   'static_current_budget': quantity_json(budget, 'current')},
            margin=None,
            assumptions=['the device guarantees V_OL <= V_OL_max only while the sink current is '
                         'at or below I_OL',
                         'a declared V_OL_min of 0 V bounds the worst-case sink current'],
            not_modelled=['I_OL dependence on temperature and V_OL', 'rail droop during the LOW '
                          'phase'])
        draft.calculation(
            'legal_interval',
            'Legal pull-up interval (empty means the interface cannot be met)',
            'R_min <= R <= R_max; the interval is empty when R_min > R_max',
            inputs={'r_min_ohm': to_json_number(r_lower),
                    'r_max_ohm': to_json_number(r_upper)},
            result={'r_min_ohm': to_json_number(r_lower),
                    'r_max_ohm': to_json_number(r_upper),
                    'feasible': r_lower <= r_upper},
            unit='ohm',
            limit=None,
            margin={'width_ohm': to_json_number(r_upper - r_lower)},
            assumptions=[],
            not_modelled=['resistor self-heating changing the value'])

        if r_lower > r_upper:
            raise NoFeasibleSolution(
                'the pull-up interval is empty: the rise-time bound needs R <= %s ohm while the '
                'sink-current/budget bounds need R >= %s ohm'
                % (format_number(r_upper), format_number(r_lower)),
                bounds={'r_max_rise_time': to_json_number(r_upper),
                        'r_min_current': to_json_number(r_lower)})

        candidates = self._candidates(inputs, r_lower, r_upper)
        if not candidates:
            raise NoFeasibleSolution(
                'no standard resistor from the declared series lies in the legal interval '
                '[%s, %s] ohm' % (format_number(r_lower), format_number(r_upper)),
                bounds={'r_min_current': to_json_number(r_lower),
                        'r_max_rise_time': to_json_number(r_upper)})
        objective = inputs.get('objective')
        score = (lambda value: -value) if objective == 'max_resistance' else (lambda value: value)
        selected = choose(candidates, score)
        if selected is None:
            raise NoFeasibleSolution('no candidate satisfies the declared objective')

        r_nom = selected
        r_min_sel = r_nom * (1 - tolerance)
        r_max_sel = r_nom * (1 + tolerance)
        rise_time_max = coefficient['k_worst'] * r_max_sel * bus_capacitance.hi
        rise_time_min = coefficient['k_best'] * r_min_sel * bus_capacitance.lo
        static_current = supply.hi / r_min_sel
        power = supply.hi ** 2 / r_min_sel
        sink_current = supply.hi / r_min_sel

        if rise_time_max > rise_limit:
            raise NoFeasibleSolution(
                'the selected resistor violates the rise-time bound after tolerance: %s s > %s s'
                % (format_number(rise_time_max), format_number(rise_limit)))
        if sink_current > iol or static_current > budget:
            raise NoFeasibleSolution(
                'the selected resistor violates a current bound after tolerance: sink %s A '
                '(IOL %s A), static %s A (budget %s A)'
                % (format_number(sink_current), format_number(iol),
                   format_number(static_current), format_number(budget)))

        bus_v_il = inputs.get('bus_v_il')
        low_level_margin = (bus_v_il - vol_max) if bus_v_il is not None else None
        if low_level_margin is not None and low_level_margin < 0:
            raise NoFeasibleSolution(
                'the device VOL_max=%s V is not below the bus V_IL=%s V; no pull-up value can '
                'make the bus read LOW'
                % (format_number(vol_max), format_number(bus_v_il)),
                bounds={'vol_max': to_json_number(vol_max),
                        'bus_v_il': to_json_number(bus_v_il)})

        # ---- components --------------------------------------------
        resistor = draft.component(
            'pull_up', 'resistor',
            value=r_nom, tolerance_pct=tolerance_pct,
            series=inputs.get('series') if inputs.get('series') != 'explicit' else None,
            power_rating_w=power,
            voltage_rating_v=supply.hi,
            pins=[{'name': '1', 'semantic': 'rail_side'},
                  {'name': '2', 'semantic': 'bus_side'}],
            requirements={
                'rise_time_max': quantity_json(rise_limit, 'time'),
                'static_current_max': quantity_json(budget, 'current'),
                'bus_capacitance_max': quantity_json(bus_capacitance.hi, 'capacitance'),
            },
            candidates=[{'nominal': value} for value in
                        (sorted(candidates, key=lambda value: -value)
                         if objective == 'max_resistance' else sorted(candidates))[:5]],
            notes='Standard value selected deterministically; the package power rating is a '
                  'requirement, not a bound part.')

        # ---- nets, ports, endpoints --------------------------------
        vcc = draft.net('VCC', role='power', scope='external', voltage_domain='supply')
        gnd = draft.net('GND', role='ground', scope='external')
        bus = draft.net('BUS', role='signal', scope='external', voltage_domain='open_drain',
                        notes='Open-drain bus line; HIGH exists only through the pull-up')
        draft.connect(resistor['ref'], '1', vcc, 'rail_side')
        draft.connect(resistor['ref'], '2', bus, 'bus_side')

        draft.port('VCC', 'input', 'power', net=vcc, voltage=supply,
                   description='Pull-up rail; also the bus HIGH level once the line is released')
        draft.port('GND', 'passive', 'ground', net=gnd, description='Ground return')
        draft.port('BUS', 'bidirectional', 'open_drain', net=bus,
                   voltage=Interval(Fraction(0), supply.hi),
                   current=Interval(Fraction(0), iol),
                   logic={
                       'vol_max': quantity_json(vol_max, 'voltage'),
                       'vol_at_iol': quantity_json(iol, 'current'),
                       'voh': 'pull-up rail (the bus is only pulled up, never driven high)',
                       'rise_time_max': quantity_json(rise_limit, 'time'),
                       'rise_time_definition': definition,
                       'max_sink_current': quantity_json(iol, 'current'),
                   },
                   description='Bidirectional open-drain bus: the bus only sources current '
                               'through the pull-up and can be pulled LOW only by a device')

        # ---- recomputed worst cases --------------------------------
        draft.calculation(
            'worst_case_rise_time',
            'Worst-case rise time with the selected resistor',
            't_rise = k * R_max * C_bus_max;  R_max = R_selected*(1+tol)',
            inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                    'r_max': quantity_json(r_max_sel, 'resistance'),
                    'bus_capacitance_max': quantity_json(bus_capacitance.hi, 'capacitance'),
                    'rise_time_definition': definition,
                    'coefficient_k': to_json_number(coefficient['k_worst'])},
            result={'rise_time_max_s': to_json_number(rise_time_max),
                    'rise_time_min_s': to_json_number(rise_time_min)},
            unit='s',
            limit={'max_rise_time': quantity_json(rise_limit, 'time')},
            margin={'margin_s': quantity_json(rise_limit - rise_time_max, 'time')},
            assumptions=['first-order RC with the declared bus capacitance'],
            not_modelled=['rise-time degradation from connectors, series resistors or crosstalk'])
        draft.calculation(
            'static_current_and_power',
            'Worst-case static current and resistor dissipation while the bus is LOW',
            'I_low = V_pu_max/R_min;  I_high = 0 A;  P = V_pu_max^2/R_min',
            inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                    'r_min': quantity_json(r_min_sel, 'resistance'),
                    'supply_voltage': supply.as_json('voltage')},
            result={'static_current_max_a': to_json_number(static_current),
                    'power_w': to_json_number(power)},
            unit='A',
            limit={'static_current_budget': quantity_json(budget, 'current')},
            margin={'margin_a': quantity_json(budget - static_current, 'current')},
            assumptions=['the bus is LOW for the static-current worst case and HIGH draws no '
                         'current through the pull-up'],
            not_modelled=['dynamic average current at the actual bus duty cycle',
                          'resistor self-heating'])
        draft.calculation(
            'low_level_voltage',
            'Recomputed sink current and guaranteed low-level voltage',
            'I_sink = V_pu_max/R_min <= IOL  =>  V_OL <= V_OL_max (datasheet guarantee)',
            inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                    'r_min': quantity_json(r_min_sel, 'resistance'),
                    'supply_voltage': supply.as_json('voltage'),
                    'vol_max': quantity_json(vol_max, 'voltage'),
                    'iol': quantity_json(iol, 'current'),
                    'bus_v_il': (quantity_json(bus_v_il, 'voltage')
                                 if bus_v_il is not None else None)},
            result={'sink_current_max_a': to_json_number(sink_current),
                    'vol_max_guaranteed_v': to_json_number(vol_max)},
            unit='V',
            limit={'iol': quantity_json(iol, 'current'),
                   'bus_v_il': (quantity_json(bus_v_il, 'voltage')
                                if bus_v_il is not None else None)},
            margin={'sink_current_margin_a': quantity_json(iol - sink_current, 'current'),
                    'low_level_margin_v': (quantity_json(low_level_margin, 'voltage')
                                           if low_level_margin is not None else None)},
            assumptions=['the datasheet guarantee is VOL <= VOL_max for any sink current at or '
                         'below IOL',
                         'VOL_min is 0 V'],
            not_modelled=['VOL nonlinearity above IOL', 'sink current during the falling edge'])
        if bus_v_il is None:
            draft.unknown('bus_v_il_not_declared',
                          'the bus input LOW threshold was not declared',
                          impact='the low-level voltage margin against the bus threshold is not '
                                 'verified; only the current margin against IOL is claimed',
                          how_to_resolve='declare bus_v_il (for I2C: 0.3 x VDD)')

        # ---- preconditions ----------------------------------------
        draft.constraint(
            'rise_time_is_a_bound',
            'Worst-case rise time %s s must stay at or below the allowed %s s at the declared '
            'bus capacitance and resistor tolerance.'
            % (format_number(rise_time_max), format_number(rise_limit)),
            kind='hard', applies_to=resistor['ref'])
        draft.constraint(
            'static_current_budget',
            'Worst-case static current %s A must stay at or below the declared %s A budget.'
            % (format_number(static_current), format_number(budget)),
            kind='hard', applies_to=resistor['ref'])
        draft.constraint(
            'pull_up_voltage_safety',
            'Mathematical feasibility does not prove the pull-up voltage is safe for every device '
            'pin: the rail must not exceed the absolute maximum input voltage of any device on '
            'the bus, and every device must accept the rail as a valid HIGH level.',
            kind='verification', applies_to='VCC')
        draft.constraint(
            'bus_frequency_not_proven',
            'The rise-time/bus-capacitance limits are necessary but not sufficient for a bus '
            'frequency: tLOW/tHIGH, setup/hold and spike suppression of the slowest device are '
            'per-part datasheet facts and are not modelled here.',
            kind='verification', applies_to='BUS')
        if specification['mode'] == 'custom':
            draft.constraint(
                'custom_rise_time_definition',
                'The rise-time limit (%s s) and its measurement definition (%s) are '
                'caller-declared, not a verified interface-standard entry.'
                % (format_number(rise_limit), definition),
                kind='verification', applies_to='BUS')
        else:
            draft.constraint(
                'interface_mode_checked',
                'The limits for %s were taken from the verified UM10204 fact '
                'file/table: tr max %s s, Cb max %s F.'
                % (specification['interface'], format_number(specification['rise_time_max']),
                   format_number(specification['bus_cap_max'])),
                kind='hard', applies_to='BUS')

        # ---- evidence ---------------------------------------------
        draft.evidence('input_supply', 'user_declared',
                       'Pull-up rail range declared by the caller: %s..%s V.'
                       % (format_number(supply.lo), format_number(supply.hi)),
                       applies_to='VCC')
        draft.evidence('input_bus_device', 'user_declared',
                       'Bus device facts declared by the caller (source=%s): VOL_max %s V at '
                       'IOL %s A%s.'
                       % (device.get('declared_by'), format_number(vol_max),
                          format_number(iol),
                          (', max sink current %s A' % format_number(sink_current_max))
                          if sink_current_max is not None else ''),
                       source={'document': 'caller declaration',
                               'provenance': device.get('declared_by')},
                       applies_to='BUS', verified=False)
        draft.evidence('input_bus_capacitance', 'user_declared',
                       'Bus capacitance declared by the caller: %s..%s F.'
                       % (format_number(bus_capacitance.lo), format_number(bus_capacitance.hi)),
                       source={'document': 'caller declaration'}, applies_to='BUS',
                       verified=False)
        if specification['facts'] is not None:
            evidence_for(draft, specification['facts'], specification['keys'])
            draft.evidence('i2c_rise_time_definition', 'standard',
                           'The rise time of the selected I2C modes is measured between 30 %% and '
                           '70 %% of VDD (Figure 38), so the coefficient k = ln(7/3) = 0.8473 of '
                           'Section 7.1 equation 1 is used.',
                           source={'document': 'NXP UM10204 I2C-bus specification and user manual',
                                   'revision': 'Rev. 7.0 (1 October 2021)',
                                   'section': 'Figure 38 and Section 7.1 equation 1'},
                           applies_to='BUS', verified=True)
        elif specification['mode'] == 'custom':
            draft.evidence('rise_time_definition_declared', 'user_declared',
                           'Caller-declared rise-time definition %s and limit %s s.'
                           % (definition, format_number(rise_limit)),
                           source={'document': 'caller declaration'}, applies_to='BUS',
                           verified=False)
        else:
            draft.evidence('i2c_bus_limits_fallback', 'standard',
                           'Fallback module-level copy of the UM10204 limits was used because the '
                           'bundled fact file was unavailable: tr max %s s, Cb max %s F.'
                           % (format_number(specification['rise_time_max']),
                              format_number(specification['bus_cap_max'])),
                           source=specification['source'], applies_to='BUS', verified=False)
        draft.evidence('standard_series', 'standard',
                       'Resistor values from IEC 60063 series %s.'
                       % inputs.get('series'),
                       source={'document': 'IEC 60063', 'section': 'preferred number series',
                               'url': 'https://webstore.iec.ch/publication/593'})
        draft.evidence('derivation_math', 'derivation',
                       'The legal interval, the worst-case rise time and the current/level checks '
                       'are derived here with exact rational arithmetic (logarithm via Decimal, no '
                       'binary floats).')
        draft.assumption('Bus capacitance is a single lumped value and does not change with the '
                         'bus state or temperature inside the declared range.',
                         impact='the computed rise time is first-order; a distributed bus needs a '
                                'measured/guarded Cb')
        draft.assumption('Resistor tolerance is independent of the bus capacitance and rail '
                         'extremes (independent worst case).',
                         impact='conservative interval; a correlated worst case would be narrower')
        draft.unknown('bus_frequency_not_guaranteed',
                      'No bus frequency is guaranteed by this RC calculation: the interface mode '
                      'only bounds the rise time and bus capacitance.',
                      impact='the bus may still fail timing because of tLOW/tHIGH, setup/hold or '
                             'spike-suppression limits of the actual devices',
                      how_to_resolve='verify the timing table of every device on the bus against '
                                     'the intended clock frequency')
        draft.unknown('device_pin_absolute_max',
                      'The absolute maximum input voltage of each device on the bus was not '
                      'declared.',
                      impact='the pull-up rail could exceed a device pin rating even though the '
                             'maths is feasible',
                      how_to_resolve='declare and check each device absolute maximum input '
                                     'voltage against the pull-up rail')
        return 'ready_abstract', [], notes

    # ------------------------------------------------------------------
    def _resolve_bus_spec(self, inputs, draft):
        mode = inputs.get('bus_spec')
        if mode == 'custom':
            if not inputs.provided('max_rise_time'):
                raise NeedsDeviceFacts(
                    ['max_rise_time'],
                    'bus_spec="custom" needs the allowed maximum rise time; without it no '
                    'rise-time bound exists and no bus frequency is guaranteed')
            if not inputs.provided('rise_time_definition'):
                raise NeedsDeviceFacts(
                    ['rise_time_definition'],
                    'bus_spec="custom" needs the rise-time measurement definition (10_90, 30_70 '
                    'or vil_vih); the coefficient changes with it')
            return {'mode': 'custom', 'interface': 'custom',
                    'rise_time_max': inputs.quantity('max_rise_time'),
                    'rise_time_definition': inputs.enum('rise_time_definition'),
                    'bus_cap_max': None, 'f_scl_max': None, 'iol_min': None,
                    'vol_max': None, 'facts': None, 'keys': [], 'source': None}
        if inputs.provided('max_rise_time'):
            raise InputInvalid(
                'max_rise_time must not be supplied when bus_spec=%r: the interface standard '
                'fixes the rise-time limit (use bus_spec="custom" for an application-specific '
                'limit)' % mode, field='max_rise_time')
        if inputs.provided('rise_time_definition'):
            raise InputInvalid(
                'rise_time_definition must not be supplied when bus_spec=%r: the interface '
                'standard fixes the measurement definition (use bus_spec="custom" to declare '
                'it)' % mode, field='rise_time_definition')
        entry = self._standards_entry(mode)
        return entry

    @staticmethod
    def _standards_entry(mode):
        try:
            facts = load_fact(_STANDARDS_FACT_ID)
        except CircuitBlockError:
            facts = None
        if facts is not None:
            keys = ['rise_time_max_s_' + mode, 'bus_cap_max_f_' + mode, 'f_scl_max_hz_' + mode,
                    'iol_min_a_fast_plus' if mode == 'fast_plus' else 'iol_min_a', 'vol_max_v']
            if not missing_keys(facts, keys):
                label = _MODE_LABELS[mode]
                return {
                    'mode': mode,
                    'interface': '%s (max %s bit/s)' % (
                        label, format_number(fact_number(facts, keys[2]))),
                    'rise_time_max': fact_number(facts, keys[0]),
                    'bus_cap_max': fact_number(facts, keys[1]),
                    'f_scl_max': fact_number(facts, keys[2]),
                    'iol_min': fact_number(facts, keys[3]),
                    'vol_max': fact_number(facts, keys[4]),
                    'rise_time_definition': '30_70',
                    'facts': facts,
                    'keys': keys,
                    'source': fact_source(facts, keys[0]),
                }
        fallback = FALLBACK_INTERFACE_TABLE[mode]
        return {
            'mode': mode,
            'interface': fallback['interface'],
            'rise_time_max': fallback['rise_time_max'],
            'bus_cap_max': fallback['bus_cap_max'],
            'f_scl_max': fallback['f_scl_max'],
            'iol_min': fallback['iol_min'],
            'vol_max': fallback['vol_max'],
            'rise_time_definition': fallback['rise_time_definition'],
            'facts': None,
            'keys': [],
            'source': fallback['source'],
        }

    @staticmethod
    def _require_bus_capacitance(inputs):
        if inputs.get('bus_capacitance') is None:
            raise NeedsDeviceFacts(
                ['bus_capacitance'],
                'the bus capacitance is required: without Cb no rise-time bound exists and no '
                'bus frequency is guaranteed from an RC number alone')
        return inputs.interval('bus_capacitance')

    @staticmethod
    def _require_device(inputs):
        device = inputs.get('device')
        if device is None:
            raise NeedsDeviceFacts(
                ['device'],
                'device V_OL/I_OL facts are required: the sink capability must never be assumed '
                'and no bus frequency is guaranteed without it')
        missing = ['device.' + name for name in ('vol_max', 'iol')
                   if device.get(name) is None]
        if missing:
            raise NeedsDeviceFacts(
                missing,
                'the device low-level facts (V_OL_max at the declared I_OL test current) are '
                'required; without them the low-level guarantee cannot be checked')
        return device

    @staticmethod
    def _require_static_budget(inputs):
        if inputs.get('static_current_budget') is None:
            raise NeedsDeviceFacts(
                ['static_current_budget'],
                'the static-current budget is required: the pull-up lower bound needs the allowed '
                'static current')
        return inputs.quantity('static_current_budget')

    def _coefficient(self, inputs, definition, supply, draft):
        if definition == '10_90':
            k_worst = k_best = _ln(Fraction(9))
            description = 'k = ln(9) = 2.1972 for a 10%-90% rise-time measurement'
        elif definition == '30_70':
            k_worst = k_best = _ln(Fraction(7, 3))
            description = 'k = ln(7/3) = 0.8473 for a 30%-70% rise-time measurement'
        else:
            if inputs.get('bus_v_il') is None or inputs.get('bus_v_ih') is None:
                raise NeedsDeviceFacts(
                    ['bus_v_il', 'bus_v_ih'],
                    'the vil_vih rise-time definition needs the bus input thresholds V_IL and '
                    'V_IH to build the coefficient')
            v_il = inputs.quantity('bus_v_il')
            v_ih = inputs.quantity('bus_v_ih')
            if v_il >= v_ih:
                raise InputInvalid('bus_v_il must stay below bus_v_ih', field='bus_v_il')
            draft.calculation(
                'rail_threshold_check',
                'Rail can exceed the bus HIGH threshold',
                'V_pu_min > V_IH (otherwise the open-drain bus can never read HIGH)',
                inputs={'supply_voltage': supply.as_json('voltage'),
                        'bus_v_ih': quantity_json(v_ih, 'voltage')},
                result={'v_rail_min_v': to_json_number(supply.lo),
                        'v_ih_v': to_json_number(v_ih),
                        'margin_v': to_json_number(supply.lo - v_ih)},
                unit='V',
                limit={'bus_v_ih': quantity_json(v_ih, 'voltage')},
                margin={'margin_v': quantity_json(supply.lo - v_ih, 'voltage')},
                assumptions=['the pull-up rail is the bus HIGH level'],
                not_modelled=['rail droop and device input leakage'])
            if supply.lo <= v_ih:
                raise NoFeasibleSolution(
                    'the pull-up rail cannot exceed the bus HIGH threshold: V_pu_min=%s V <= '
                    'V_IH=%s V' % (format_number(supply.lo), format_number(v_ih)),
                    bounds={'v_rail_min': to_json_number(supply.lo),
                            'bus_v_ih': to_json_number(v_ih)})
            # k(V) = ln((V-VIL)/(V-VIH)) decreases with V, so the largest (worst)
            # coefficient is at the minimum rail.
            k_worst = _ln((supply.lo - v_il) / (supply.lo - v_ih))
            k_best = _ln((supply.hi - v_il) / (supply.hi - v_ih))
            description = ('k = ln((V_pu-V_IL)/(V_pu-V_IH)) evaluated at the worst-case rail '
                           '(V_pu_min for the bound, V_pu_max for the minimum time)')
        draft.calculation(
            'rise_time_coefficient',
            'Rise-time coefficient for the declared measurement definition',
            description,
            inputs={'rise_time_definition': definition,
                    'bus_v_il': (quantity_json(inputs.quantity('bus_v_il'), 'voltage')
                                 if inputs.get('bus_v_il') is not None else None),
                    'bus_v_ih': (quantity_json(inputs.quantity('bus_v_ih'), 'voltage')
                                 if inputs.get('bus_v_ih') is not None else None),
                    'supply_voltage': supply.as_json('voltage')},
            result={'k_worst': to_json_number(k_worst),
                    'k_best': to_json_number(k_best)},
            unit='1',
            limit=None,
            margin=None,
            assumptions=['the definition describes how the external rise time is measured'],
            not_modelled=['measurement tolerances of the rise-time definition'])
        return {'k_worst': k_worst, 'k_best': k_best, 'definition': definition}

    @staticmethod
    def _check_mode_limits(draft, specification, bus_capacitance, iol):
        bus_cap_max = specification['bus_cap_max']
        if bus_cap_max is not None and bus_capacitance.hi > bus_cap_max:
            draft.calculation(
                'bus_capacitance_limit',
                'Declared bus capacitance against the interface-mode limit',
                'C_bus_max <= Cb_max(mode)',
                inputs={'bus_capacitance_max': quantity_json(bus_capacitance.hi, 'capacitance'),
                        'mode_bus_capacitance_max': quantity_json(bus_cap_max, 'capacitance'),
                        'bus_spec': specification['mode']},
                result={'declared_f': to_json_number(bus_capacitance.hi),
                        'limit_f': to_json_number(bus_cap_max)},
                unit='F',
                limit={'mode_bus_capacitance_max': quantity_json(bus_cap_max, 'capacitance')},
                margin={'margin_f': to_json_number(bus_cap_max - bus_capacitance.hi)},
                assumptions=[],
                not_modelled=['special-purpose devices that exceed the standard pin capacitance'])
            raise Unsupported(
                'the declared bus capacitance %s F exceeds the %s limit %s F for bus_spec=%r'
                % (format_number(bus_capacitance.hi), specification['interface'],
                   format_number(bus_cap_max), specification['mode']),
                reasons=['bus capacitance %s F exceeds the %s limit %s F'
                         % (format_number(bus_capacitance.hi), specification['interface'],
                            format_number(bus_cap_max))])
        iol_min = specification['iol_min']
        if iol_min is not None and iol < iol_min:
            draft.calculation(
                'device_sink_capability',
                'Declared device sink current against the interface-mode requirement',
                'I_OL(device) >= I_OL_min(mode)',
                inputs={'device_iol': quantity_json(iol, 'current'),
                        'mode_iol_min': quantity_json(iol_min, 'current'),
                        'bus_spec': specification['mode']},
                result={'device_a': to_json_number(iol),
                        'required_a': to_json_number(iol_min)},
                unit='A',
                limit={'mode_iol_min': quantity_json(iol_min, 'current')},
                margin={'margin_a': to_json_number(iol - iol_min)},
                assumptions=[],
                not_modelled=['full-load sink current requirements beyond the mode minimum'])
            raise Unsupported(
                'the declared device sink current %s A is below the %s requirement %s A'
                % (format_number(iol), specification['interface'], format_number(iol_min)),
                reasons=['device sink current IOL %s A < %s minimum %s A'
                         % (format_number(iol), specification['interface'],
                            format_number(iol_min))])

    @staticmethod
    def _candidates(inputs, low, high):
        series = inputs.get('series')
        window = inputs.get('value_range')
        lower = max(low, window.lo) if window is not None else low
        upper = min(high, window.hi) if window is not None else high
        if series == 'explicit':
            explicit = inputs.get('allowed_values')
            if not explicit:
                raise InputInvalid('series="explicit" requires allowed_values',
                                   field='allowed_values')
            candidates = {value for value in explicit
                          if lower <= value <= upper}
        else:
            candidates = set(series_values(series, lower, upper))
        return sorted(candidates)
