"""F4 — resistive divider feeding an ADC input.

Two explicit topologies are supported and never silently invented:

* ``divider_to_ground`` ``VIN -[R_top]- VOUT -[R_bottom]- GND``
* ``divider_to_vref``   ``VIN -[R_top]- VOUT -[R_bottom]- VREF``

The standard ``R_top``/``R_bottom`` pair is chosen from a declared IEC 60063
series so that the whole declared input range maps inside the ADC legal input
range (minus the declared design margin), the worst-case Thevenin source
impedance stays below a declared ADC limit, and — when the ADC sampling facts
are declared — the sample-and-hold settles within the declared sample time.

Worst-case output uses exact rational interval arithmetic over:

* the input voltage range,
* both resistor tolerances (independent extremes),
* the declared ADC input leakage current acting through the Thevenin source
  impedance in the worst direction,
* the declared ADC reference tolerance (for ``divider_to_vref`` it shifts the
  tap; for ``divider_to_ground`` it is reported as a conversion gain error).

The module never claims ADC accuracy: a tap that lands inside the legal range
is a range check, not an accuracy proof.  Sample settling is reported as
*unverified* whenever the sample time / sample-hold capacitance / error target
facts are absent, and an external buffer is emitted as an explicit gap (with a
required specification) instead of picking an op-amp.  Negative input,
overvoltage, reverse feed and an added series protection resistor are emitted
as separate protection constraints that are **not** covered by this math.
"""
from __future__ import annotations

import bisect
from decimal import Decimal, localcontext
from fractions import Fraction

from ..errors import InputInvalid, NeedsDeviceFacts, NoFeasibleSolution
from ..eseries import values as series_values
from ..numeric import format_number, to_json_number
from ..ranges import Interval
from ..units import quantity_json
from .base import Block

#: Significant digits for logarithms / pi.  Decimal is correctly rounded, so the
#: same exact rational input yields the same decision on every platform.
_LOG_PRECISION = 40

#: Resistor candidates span 1 ohm .. 9.1 Mohm; anything outside is not a
#: plausible ADC divider and is a caller error, not a design choice.
_RESISTOR_DECADES = range(0, 7)

#: Capacitors need decades well below 1 uF.
_CAPACITOR_DECADES = range(-12, 7)

_PI = Decimal('3.14159265358979323846264338327950288419716939937510')


def _ln(value):
    """Natural logarithm of an exact positive Fraction, evaluated with Decimal."""
    value = value if isinstance(value, Fraction) else Fraction(value)
    if value <= 0:
        raise InputInvalid('logarithm argument must be positive')
    with localcontext() as context:
        context.prec = _LOG_PRECISION
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
        return Fraction(decimal_value.ln())


def _bandwidth(resistance, capacitance):
    """First-order -3 dB bandwidth ``f = 1 / (2*pi*R*C)`` as an exact Fraction."""
    tau = resistance * capacitance
    if tau <= 0:
        raise InputInvalid('bandwidth requires a positive time constant')
    with localcontext() as context:
        context.prec = _LOG_PRECISION
        value = (Decimal(tau.denominator) /
                 (Decimal(2) * _PI * Decimal(tau.numerator)))
        return Fraction(value)


class AdcDivider(Block):
    MODULE_TYPE = 'adc_divider'
    TEMPLATE_VERSION = '1.0.0'
    TITLE = 'ADC input voltage divider'
    SUMMARY = ('Selects a standard R_top/R_bottom pair that maps a declared measured-voltage '
               'range into the ADC legal input range, checks the worst-case output over resistor '
               'tolerance, ADC leakage and reference tolerance, reports divider power and '
               'Thevenin source impedance, verifies sample-and-hold settling only when the ADC '
               'sample facts are declared, and emits protection/buffer gaps instead of guessing.')
    TOPOLOGY = ('R_top from VIN to the VOUT tap, R_bottom from VOUT to GND (divider_to_ground) '
                'or to the ADC reference VREF (divider_to_vref)')
    APPLICABILITY = (
        'single resistive divider with one tap feeding a high-impedance ADC input',
        'declared measured-input range and declared ADC legal input range',
        'declared resistor series, tolerance and ADC input leakage current',
        'worst-case range check plus declared source-impedance limit enforcement',
        'optional ADC sampling facts for a first-order sample-and-hold settling check',
    )
    NON_APPLICABILITY = (
        'protection circuits: negative input, overvoltage, reverse feed and series protection '
        'resistors are NOT modelled and are emitted as separate open constraints',
        'ADC accuracy: INL/DNL/offset/gain/noise of the converter are not modelled; a tap inside '
        'the legal range is not an accuracy proof',
        'high-impedance sources or dynamic signals that need an external buffer',
        'differential, bridge or ratiometric sensor front ends',
        'multiple dividers sharing one ADC channel or a multiplexer charge-sharing analysis',
    )
    REQUIRED_DEVICE_FACTS = (
        'ADC legal input voltage range and (recommended) input leakage current',
        'resistor series and tolerance (IEC 60063 values)',
        'optional: ADC sample time, sample-hold capacitance and maximum source impedance',
        'optional: ADC reference voltage, reference tolerance and resolution',
    )
    SOURCES = (
        {'document': 'IEC 60063 preferred number series (E6/E12/E24/E48/E96)',
         'why': 'standard resistor values'},
        {'document': 'ADC manufacturer datasheet (exact part)',
         'why': 'legal input range, input leakage, sample time, sample-hold capacitance, reference '
                'tolerance, maximum source impedance, resolution'},
        {'document': 'Ohm/Kirchhoff divider and first-order RC settling analysis',
         'why': 'ratio, worst-case tap, Thevenin impedance and sample-and-hold settling'},
    )

    INPUT_SCHEMA = {
        'topology': {
            'kind': 'enum', 'values': ['divider_to_ground', 'divider_to_vref'],
            'required': True,
            'doc': 'divider_to_ground: R_bottom returns to GND. divider_to_vref: R_bottom returns '
                   'to the ADC reference VREF (level-shifted tap).'},
        'input_voltage': {
            'kind': 'range', 'family': 'voltage', 'required': True,
            'doc': 'Measured input voltage range at VIN (V). It must be a real range, not a point; '
                   'negative values are legal input but their protection is a separate constraint.'},
        'adc_input_range': {
            'kind': 'range', 'family': 'voltage', 'required': True,
            'doc': 'ADC legal input voltage range (V); the worst-case tap must stay inside it.'},
        'adc_leakage_current': {
            'kind': 'quantity', 'family': 'current', 'nonnegative': True,
            'doc': 'ADC input leakage current magnitude at the tap (A). Required for a '
                   'ready_abstract worst-case output: it is never assumed to be zero.'},
        'adc_vref': {
            'kind': 'quantity', 'family': 'voltage', 'positive': True,
            'doc': 'ADC reference voltage (V). Required for topology=divider_to_vref.'},
        'adc_reference_tolerance_pct': {
            'kind': 'quantity', 'family': 'percent', 'nonnegative': True,
            'doc': 'ADC reference tolerance (±%) when declared; it is included in the '
                   'divider_to_vref tap worst case and reported as a conversion gain error.'},
        'adc_resolution_bits': {
            'kind': 'integer', 'min_value': 1, 'max_value': 32,
            'doc': 'Optional ADC resolution (bits) used only for LSB reporting and for the '
                   'sample-and-hold half-LSB error target.'},
        'adc_max_source_impedance': {
            'kind': 'quantity', 'family': 'resistance', 'positive': True,
            'doc': 'Declared maximum source impedance the ADC input tolerates (ohm); the '
                   'worst-case Thevenin impedance R_top||R_bottom must not exceed it.'},
        'adc_margin': {
            'kind': 'quantity', 'family': 'voltage', 'default': 0, 'nonnegative': True,
            'doc': 'Design margin kept inside each ADC limit (V); the boundary is legal when the '
                   'margin is zero.'},
        'adc_sampling': {
            'kind': 'object',
            'fields': {
                'sample_time': {
                    'kind': 'range', 'family': 'time', 'positive': True,
                    'doc': 'ADC sample (acquisition) time range (s).'},
                'sample_hold_capacitance': {
                    'kind': 'quantity', 'family': 'capacitance', 'positive': True,
                    'doc': 'ADC sample-and-hold capacitance (F).'},
                'settling_error_target_pct': {
                    'kind': 'quantity', 'family': 'percent', 'positive': True,
                    'doc': 'Optional settling error target in % of full scale; used when no ADC '
                           'resolution is declared (half LSB is used otherwise).'},
            },
            'doc': 'Optional ADC sampling facts. When absent, sample-and-hold settling is '
                   'reported as unverified and no ADC accuracy is claimed.'},
        'series': {
            'kind': 'enum', 'values': ['E6', 'E12', 'E24', 'E48', 'E96', 'explicit'],
            'default': 'E24',
            'doc': 'Resistor series for both R_top and R_bottom, or "explicit" with '
                   'allowed_values.'},
        'allowed_values': {
            'kind': 'array', 'items': {'kind': 'quantity', 'family': 'resistance'},
            'doc': 'Explicit allowed resistor values (ohm) used for both roles; required when '
                   'series is "explicit".'},
        'value_range': {
            'kind': 'range', 'family': 'resistance', 'positive': True,
            'doc': 'Optional allowed resistance window applied to both R_top and R_bottom (ohm).'},
        'resistor_tolerance_pct': {
            'kind': 'quantity', 'family': 'percent', 'required': True, 'nonnegative': True,
            'doc': 'Resistor tolerance (±%) used for the worst-case tap.'},
        'resistor_power_rating': {
            'kind': 'quantity', 'family': 'power', 'positive': True,
            'doc': 'Optional resistor package power rating (W); if given it is checked, never '
                   'silently raised.'},
        'power_derating_pct': {
            'kind': 'quantity', 'family': 'percent', 'default': 50, 'nonnegative': True,
            'doc': 'Required derating of the resistor rating at worst case (%).'},
        'objective': {
            'kind': 'enum', 'values': ['ratio_error', 'min_power', 'min_source_impedance'],
            'default': 'ratio_error',
            'doc': 'Deterministic selection objective after the hard constraints pass.'},
        'rc_filter': {
            'kind': 'object',
            'fields': {
                'capacitance': {
                    'kind': 'quantity', 'family': 'capacitance', 'positive': True,
                    'doc': 'Explicit filter capacitor value (F).'},
                'capacitance_range': {
                    'kind': 'range', 'family': 'capacitance', 'positive': True,
                    'doc': 'Allowed standard capacitor window (F) when selecting from a series.'},
                'capacitor_series': {
                    'kind': 'enum', 'values': ['E3', 'E6', 'E12'], 'default': 'E12',
                    'doc': 'Capacitor value series used when selecting from capacitance_range.'},
                'capacitor_tolerance_pct': {
                    'kind': 'quantity', 'family': 'percent', 'nonnegative': True,
                    'doc': 'Capacitor tolerance (±%); required for the worst-case bandwidth.'},
                'target_bandwidth': {
                    'kind': 'range', 'family': 'frequency', 'positive': True,
                    'doc': 'Target -3 dB bandwidth range (Hz) used to select the capacitor; '
                           'required when capacitance_range is used.'},
            },
            'doc': 'Optional RC filter at the tap. When absent no capacitor is fitted and no '
                   'bandwidth change is claimed.'},
        'notes': {'kind': 'string', 'doc': 'Free-form note copied into the result.'},
    }
    EXAMPLE_INPUT = {
        'topology': 'divider_to_ground',
        'input_voltage': {'min': 1, 'max': 5},
        'adc_input_range': {'min': 0, 'max': 3.3},
        'adc_leakage_current': '1uA',
        'adc_vref': 3.3,
        'adc_resolution_bits': 12,
        'adc_reference_tolerance_pct': 0.1,
        'adc_max_source_impedance': '10k',
        'adc_margin': 0,
        'adc_sampling': {
            'sample_time': '2us',
            'sample_hold_capacitance': '10pF',
        },
        'series': 'E24',
        'value_range': {'min': '1k', 'max': '100k'},
        'resistor_tolerance_pct': 1,
        'objective': 'ratio_error',
    }

    # ------------------------------------------------------------------
    def compute(self, draft, inputs):
        notes = inputs.get('notes')
        topology = inputs.enum('topology')
        vin = inputs.interval('input_voltage')
        adc = inputs.interval('adc_input_range')

        if vin.is_point:
            raise NeedsDeviceFacts(
                ['input_voltage range'],
                'input_voltage is a point value; a measured input voltage must be declared as a '
                'range over its real spread before a divider ratio and worst case are meaningful')
        if adc.is_point:
            raise NeedsDeviceFacts(
                ['adc_input_range range'],
                'adc_input_range is a point value; an ADC legal input range must have a finite '
                'width to define where the tap may sit')

        leakage = _optional_quantity(inputs, 'adc_leakage_current')
        if leakage is None:
            raise NeedsDeviceFacts(
                ['adc_leakage_current'],
                'the ADC input leakage current is required: an ADC input is never assumed to have '
                'zero leakage, and the worst-case tap cannot be bounded without it')

        vref = _optional_quantity(inputs, 'adc_vref')
        if topology == 'divider_to_vref' and vref is None:
            raise NeedsDeviceFacts(
                ['adc_vref'],
                'topology=divider_to_vref returns R_bottom to the ADC reference; adc_vref is '
                'required to compute the level-shifted tap')
        reftol_pct = _optional_quantity(inputs, 'adc_reference_tolerance_pct')
        reftol = (reftol_pct / 100) if reftol_pct is not None else None
        if reftol is not None and reftol >= 1:
            raise InputInvalid('reference tolerance must stay below 100%',
                               field='adc_reference_tolerance_pct')

        margin = inputs.quantity('adc_margin')
        win_lo = adc.lo + margin
        win_hi = adc.hi - margin
        if win_lo >= win_hi:
            raise NoFeasibleSolution(
                'the declared ADC margin %s V leaves no legal window inside %s..%s V'
                % (format_number(margin), format_number(adc.lo), format_number(adc.hi)),
                bounds={'adc_window_min': to_json_number(win_lo),
                        'adc_window_max': to_json_number(win_hi)})

        tolerance_pct = inputs.quantity('resistor_tolerance_pct')
        if tolerance_pct >= 100:
            raise InputInvalid('resistor tolerance must stay below 100%',
                               field='resistor_tolerance_pct')
        tolerance = tolerance_pct / 100
        derating = inputs.quantity('power_derating_pct') / 100
        if derating >= 1:
            raise InputInvalid('power derating must stay below 100%', field='power_derating_pct')

        candidates = self._candidates(inputs)
        if not candidates:
            raise InputInvalid('no resistor candidates: the declared series/value_range is empty')

        # Protection and converter accuracy are a separate, explicit domain: they
        # are recorded before any feasible/infeasible decision so every result
        # (including unsupported and needs_device_facts) carries the gap.
        self._write_protection_domain(draft)

        # -- sample-and-hold facts -----------------------------------
        sampling = inputs.get('adc_sampling')
        resolution_bits = inputs.get('adc_resolution_bits')
        settling = None
        if sampling is not None:
            settling = self._settling_requirements(inputs, sampling, resolution_bits)

        # -- legal ratio window from the ADC range --------------------
        base_nom = vref if topology == 'divider_to_vref' else Fraction(0)
        ref_span = (vref * reftol
                    if (topology == 'divider_to_vref' and vref is not None and reftol is not None)
                    else Fraction(0))
        k_lower, k_upper = self._ratio_window(topology, vin, base_nom,
                                              win_lo - ref_span, win_hi + ref_span)
        self._write_ratio_window(draft, topology, vin, base_nom, win_lo, win_hi,
                                 k_lower, k_upper)
        x_lower, x_upper = self._nominal_ratio_bounds(k_lower, k_upper, tolerance)
        if x_lower >= 1 or (x_upper is not None and x_upper <= 0):
            raise NoFeasibleSolution(
                'the ADC window %s..%s V cannot be reached from the input range %s..%s V with '
                'positive resistor values (required ratio interval is empty)'
                % (format_number(win_lo), format_number(win_hi),
                   format_number(vin.lo), format_number(vin.hi)),
                bounds={'required_ratio_min': to_json_number(x_lower),
                        'required_ratio_max': (to_json_number(x_upper)
                                               if x_upper is not None else None)})
        if x_upper is not None and x_lower > x_upper:
            raise NoFeasibleSolution(
                'the required divider-ratio window is empty: ratio >= %s but tolerance-adjusted '
                'ratio <= %s' % (format_number(x_lower), format_number(x_upper)),
                bounds={'required_ratio_min': to_json_number(x_lower),
                        'required_ratio_max': to_json_number(x_upper)})

        # -- deterministic candidate search --------------------------
        max_source = _optional_quantity(inputs, 'adc_max_source_impedance')
        power_rating = _optional_quantity(inputs, 'resistor_power_rating')
        objective = inputs.get('objective')
        k_target = (win_hi - win_lo) / (vin.hi - vin.lo)
        leakage_cap = ((win_hi - win_lo) / (2 * leakage)) if leakage > 0 else None

        ranked = []
        rejected = {'output': 0, 'source': 0, 'power': 0, 'settling': 0}
        for r_top in candidates:
            rb_lo = (r_top * x_lower / (1 - x_lower)) if x_lower > 0 else Fraction(0)
            rb_hi = (r_top * x_upper / (1 - x_upper)) if x_upper is not None else None
            if max_source is not None and r_top > max_source:
                bound = max_source * r_top / (r_top - max_source)
                rb_hi = bound if rb_hi is None else min(rb_hi, bound)
            if leakage_cap is not None and r_top > leakage_cap:
                bound = leakage_cap * r_top / (r_top - leakage_cap)
                rb_hi = bound if rb_hi is None else min(rb_hi, bound)
            low_index = bisect.bisect_left(candidates, rb_lo)
            high_index = (len(candidates) if rb_hi is None
                          else bisect.bisect_right(candidates, rb_hi))
            for r_bottom in candidates[low_index:high_index]:
                evaluated = self._evaluate_pair(
                    topology, vin, base_nom, reftol, tolerance, derating,
                    leakage, win_lo, win_hi, max_source, power_rating,
                    settling, r_top, r_bottom, objective, k_target)
                if evaluated is None:
                    rejected['_pair'] = rejected.get('_pair', 0) + 1
                    continue
                if 'reject' in evaluated:
                    rejected[evaluated['reject']] = rejected.get(evaluated['reject'], 0) + 1
                    continue
                ranked.append(evaluated)

        if not ranked:
            self._write_no_solution(draft, inputs, topology, win_lo, win_hi,
                                    max_source, power_rating, leakage, rejected,
                                    resolution_bits)
            raise NoFeasibleSolution(
                'no standard R_top/R_bottom pair satisfies the hard constraints (window %s..%s V, '
                'source impedance %s, resistor rating %s, settling %s)'
                % (format_number(win_lo), format_number(win_hi),
                   format_number(max_source) if max_source is not None else 'not declared',
                   format_number(power_rating) if power_rating is not None else 'not declared',
                   'checked' if settling is not None else 'unverified'),
                bounds={'adc_window_min': to_json_number(win_lo),
                        'adc_window_max': to_json_number(win_hi),
                        'rejected_output': rejected.get('output', 0),
                        'rejected_source': rejected.get('source', 0),
                        'rejected_power': rejected.get('power', 0),
                        'rejected_settling': rejected.get('settling', 0)})
        ranked.sort(key=lambda item: (item['key'], item['r_top'], item['r_bottom']))
        selected = ranked[0]
        r_top = selected['r_top']
        r_bottom = selected['r_bottom']
        self._write_selected(draft, inputs, topology, vin, adc, base_nom, vref, reftol,
                             win_lo, win_hi, tolerance, tolerance_pct, derating,
                             leakage, max_source, power_rating, settling, resolution_bits,
                             candidates, r_top, r_bottom)
        return 'ready_abstract', [], notes

    # ------------------------------------------------------------------
    @staticmethod
    def _candidates(inputs):
        series = inputs.get('series')
        window = inputs.get('value_range')
        low = window.lo if window is not None else None
        high = window.hi if window is not None else None
        if series == 'explicit':
            explicit = inputs.get('allowed_values')
            if not explicit:
                raise InputInvalid('series="explicit" requires allowed_values',
                                   field='allowed_values')
            values = set(explicit)
        else:
            values = set(series_values(series, low, high, decades=_RESISTOR_DECADES))
        if window is not None:
            values = {value for value in values if window.contains(value)}
        return sorted(values)

    # ------------------------------------------------------------------
    @staticmethod
    def _settling_requirements(inputs, sampling, resolution_bits):
        sample_time = sampling.get('sample_time')
        if sample_time is None:
            raise NeedsDeviceFacts(
                ['adc_sampling.sample_time'],
                'ADC sampling facts were declared but the sample time is missing; settling '
                'cannot be computed')
        capacitance = sampling.get('sample_hold_capacitance')
        if capacitance is None:
            raise NeedsDeviceFacts(
                ['adc_sampling.sample_hold_capacitance'],
                'ADC sampling facts were declared but the sample-hold capacitance is missing; '
                'settling cannot be computed')
        error_pct = sampling.get('settling_error_target_pct')
        if resolution_bits is not None:
            # Half of one LSB of full scale: eps = 1 / 2^(N+1), k = (N+1)*ln(2).
            with localcontext() as context:
                context.prec = _LOG_PRECISION
                required_k = Fraction(Decimal(resolution_bits + 1) * Decimal(2).ln())
            error_fraction = Fraction(1, 2 ** (resolution_bits + 1))
            target_text = 'half LSB at %d bits (%.6g%% of full scale)' % (
                resolution_bits, float(error_fraction) * 100)
        elif error_pct is not None:
            error_fraction = error_pct / 100
            required_k = -_ln(error_fraction)
            target_text = '%s%% of full scale' % format_number(error_pct)
        else:
            raise NeedsDeviceFacts(
                ['adc_resolution_bits or adc_sampling.settling_error_target_pct'],
                'a settling error target is needed to state the required number of time '
                'constants: declare the ADC resolution or the settling error target')
        return {
            'sample_time': sample_time,
            'capacitance': capacitance,
            'required_k': required_k,
            'error_fraction': error_fraction,
            'target_text': target_text,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _ratio_window(topology, vin, base_nom, win_lo, win_hi):
        """Return the ratio interval ``[k_min, k_max]`` required by the output window.

        ``None`` means unbounded on that side.  The output is
        ``VOUT = base + (VIN - base) * k`` with ``0 < k < 1``; the extremes are
        derived from the sign of ``VIN - base`` so no division by a possibly
        negative interval endpoint is hidden from the proof.
        """
        lower, upper = None, None

        def add_lower(value):
            nonlocal lower
            if lower is None or value > lower:
                lower = value

        def add_upper(value):
            nonlocal upper
            if upper is None or value < upper:
                upper = value

        d_lo = vin.lo - base_nom
        d_hi = vin.hi - base_nom
        if d_lo == 0:
            if win_lo - base_nom > 0:
                raise NoFeasibleSolution(
                    'at the minimum input the tap is fixed at the reference %s V, above the '
                    'required ADC window minimum %s V'
                    % (format_number(base_nom), format_number(win_lo)),
                    bounds={'tap_at_min_input': to_json_number(base_nom)})
        elif d_lo > 0:
            add_lower((win_lo - base_nom) / d_lo)
        else:
            add_upper((win_lo - base_nom) / d_lo)
        if d_hi == 0:
            if win_hi - base_nom < 0:
                raise NoFeasibleSolution(
                    'at the maximum input the tap is fixed at the reference %s V, above the ADC '
                    'window maximum %s V' % (format_number(base_nom), format_number(win_hi)),
                    bounds={'tap_at_max_input': to_json_number(base_nom)})
        elif d_hi > 0:
            add_upper((win_hi - base_nom) / d_hi)
        else:
            add_lower((win_hi - base_nom) / d_hi)

        if lower is not None and lower >= 1:
            raise NoFeasibleSolution(
                'the ADC window requires a divider ratio >= 1 (only a buffer/level shifter can '
                'do that), which a resistive divider cannot provide',
                bounds={'required_ratio_min': to_json_number(lower)})
        if upper is not None and upper <= 0:
            raise NoFeasibleSolution(
                'the ADC window requires a non-positive divider ratio, which a resistive divider '
                'cannot provide', bounds={'required_ratio_max': to_json_number(upper)})
        if lower is not None and upper is not None and lower > upper:
            raise NoFeasibleSolution(
                'the required divider ratio window is empty: k >= %s but k <= %s'
                % (format_number(lower), format_number(upper)),
                bounds={'required_ratio_min': to_json_number(lower),
                        'required_ratio_max': to_json_number(upper)})
        return lower, upper

    @staticmethod
    def _nominal_ratio_bounds(k_lower, k_upper, tolerance):
        """Convert worst-case ratio bounds into nominal (no-tolerance) bounds.

        For a nominal ratio ``x`` the tolerance extremes are
        ``k_min = x(1-t)/(1+t-2tx)`` and ``k_max = x(1+t)/(1-t+2tx)``; inverting
        those monotonic maps gives the nominal search window used for candidate
        enumeration.  The exact per-pair filter still decides every case.
        """
        x_lower = Fraction(0)
        if k_lower is not None:
            x_lower = k_lower * (1 + tolerance) / (1 - tolerance + 2 * tolerance * k_lower)
        x_upper = None
        if k_upper is not None:
            denominator = 1 + tolerance - 2 * tolerance * k_upper
            if denominator > 0:
                x_upper = k_upper * (1 - tolerance) / denominator
        return x_lower, x_upper

    # ------------------------------------------------------------------
    def _evaluate_pair(self, topology, vin, base_nom, reftol, tolerance, derating,
                       leakage, win_lo, win_hi, max_source, power_rating,
                       settling, r_top, r_bottom, objective, k_target):
        """Return a scored candidate dict, a rejection marker, or ``None``."""
        t = tolerance
        r_top_min, r_top_max = r_top * (1 - t), r_top * (1 + t)
        r_bottom_min, r_bottom_max = r_bottom * (1 - t), r_bottom * (1 + t)
        k_min = r_bottom_min / (r_top_max + r_bottom_min)
        k_max = r_bottom_max / (r_top_min + r_bottom_max)
        k_nom = r_bottom / (r_top + r_bottom)
        rth_min = r_top_min * r_bottom_min / (r_top_min + r_bottom_min)
        rth_nom = r_top * r_bottom / (r_top + r_bottom)
        rth_max = r_top_max * r_bottom_max / (r_top_max + r_bottom_max)

        if max_source is not None and rth_max > max_source:
            return {'reject': 'source'}
        if not (Fraction(0) < k_min <= k_max < Fraction(1)):
            return None

        base_low, base_high = self._base_interval(topology, base_nom, reftol)
        base_interval = Interval(base_low, base_high)
        output = base_interval + (vin - base_interval) * Interval(k_min, k_max)
        shift = leakage * rth_max
        output_lo = output.lo - shift
        output_hi = output.hi + shift
        if output_lo < win_lo or output_hi > win_hi:
            return {'reject': 'output'}

        if topology == 'divider_to_vref':
            chain = vin - base_interval
        else:
            chain = vin
        chain_max = max(abs(chain.lo), abs(chain.hi))
        current_max = chain_max / (r_top_min + r_bottom_min)
        power_top = current_max * current_max * r_top_max
        power_bottom = current_max * current_max * r_bottom_max
        power_worst = max(power_top, power_bottom)
        if power_rating is not None:
            required = power_worst / (1 - derating) if derating < 1 else power_worst
            if required > power_rating:
                return {'reject': 'power'}

        if settling is not None:
            tau_max = rth_max * settling['capacitance']
            required_time = settling['required_k'] * tau_max
            if settling['sample_time'].lo < required_time:
                return {'reject': 'settling'}

        if objective == 'min_power':
            key = (power_worst, abs(k_nom - k_target))
        elif objective == 'min_source_impedance':
            key = (rth_max, abs(k_nom - k_target))
        else:
            key = (abs(k_nom - k_target), power_worst)
        return {'r_top': r_top, 'r_bottom': r_bottom, 'key': key,
                'k_nom': k_nom, 'k_min': k_min, 'k_max': k_max,
                'rth_min': rth_min, 'rth_nom': rth_nom, 'rth_max': rth_max,
                'output_lo': output_lo, 'output_hi': output_hi, 'shift': shift,
                'power_top': power_top, 'power_bottom': power_bottom,
                'power_worst': power_worst, 'current_max': current_max,
                'base_low': base_low, 'base_high': base_high}

    @staticmethod
    def _base_interval(topology, base_nom, reftol):
        if topology == 'divider_to_vref' and reftol is not None:
            return (base_nom * (1 - reftol), base_nom * (1 + reftol))
        return (base_nom, base_nom)

    # ------------------------------------------------------------------
    @staticmethod
    def _write_ratio_window(draft, topology, vin, base_nom, win_lo, win_hi,
                            k_lower, k_upper):
        draft.calculation(
            'divider_ratio_window',
            'Divider ratio interval required by the ADC legal window',
            'VOUT = VREF + (VIN - VREF)*k for divider_to_vref, VOUT = VIN*k for '
            'divider_to_ground; the ratio interval follows from the sign of (VIN - VREF) and '
            'the chosen window endpoints',
            inputs={'topology': topology,
                    'input_voltage': vin.as_json('voltage'),
                    'reference_voltage': quantity_json(base_nom, 'voltage'),
                    'adc_window': {'min': to_json_number(win_lo),
                                   'max': to_json_number(win_hi), 'unit': 'V'},
                    'ratio_convention': 'k = R_bottom / (R_top + R_bottom)'},
            result={'required_ratio_min': (to_json_number(k_lower)
                                           if k_lower is not None else None),
                    'required_ratio_max': (to_json_number(k_upper)
                                           if k_upper is not None else None)},
            unit='1',
            limit=None,
            margin=None,
            method='closed-form interval inversion with sign-aware division',
            assumptions=['the ADC window is a hard output constraint for every declared input '
                         'and resistor-tolerance extreme'],
            not_modelled=['leakage and reference tolerance in this first window; the exact '
                          'per-pair filter applies them'])

    # ------------------------------------------------------------------
    def _write_no_solution(self, draft, inputs, topology, win_lo, win_hi,
                           max_source, power_rating, leakage, rejected,
                           resolution_bits):
        if rejected.get('settling'):
            self._write_buffer_gap(
                draft, inputs, resolution_bits,
                'no standard R_top/R_bottom pair with the declared source impedance settles the '
                'ADC sample-and-hold within the declared sample time at the required error target')
        if rejected.get('source'):
            draft.constraint('source_impedance_unmet',
                             'The declared ADC maximum source impedance cannot be met together '
                             'with the divider-ratio window by any standard pair.',
                             kind='hard', applies_to='VOUT', source='derivation',
                             rationale='the Thevenin impedance R_top||R_bottom is bounded from '
                                       'above by the declared limit')
        if rejected.get('power'):
            draft.constraint('resistor_rating_unmet',
                             'The declared resistor package rating is insufficient at the '
                             'worst-case dissipation for every standard pair in the ratio window.',
                             kind='hard', applies_to='R_top/R_bottom', source='derivation',
                             rationale='required rating includes the declared power derating')
        draft.constraint('ratio_window_endpoints',
                         'No standard pair maps the input range into %s..%s V with the declared '
                         'resistor tolerance, leakage and reference tolerance.'
                         % (format_number(win_lo), format_number(win_hi)),
                         kind='hard', applies_to='VOUT', source='derivation')

    # ------------------------------------------------------------------
    def _write_buffer_gap(self, draft, inputs, resolution_bits, reason):
        lsb_text = self._lsb_text(inputs, resolution_bits)
        draft.constraint(
            'buffer_required',
            'An external unity-gain buffer is required between the tap and the ADC: input bias '
            'current far below the assumed ADC leakage, input offset and drift below %s, '
            'input/output swing covering the ADC legal range, bandwidth above the highest signal '
            'component and stable with the ADC sample-hold capacitance. No operational '
            'amplifier is selected or named here.' % lsb_text,
            kind='integration', applies_to='VOUT', source='derivation',
            rationale=reason)
        draft.unknown(
            'buffer_gap',
            'The settling/source-impedance constraint cannot be satisfied by the passive divider '
            'alone; a buffer is needed but its part selection is explicitly out of scope.',
            impact='without the buffer the ADC sample does not settle and the conversion is '
                   'invalid',
            how_to_resolve='select an op-amp buffer that meets the emitted specification and add '
                           'it to the composed design, then re-run the sampling verification')

    @staticmethod
    def _lsb_text(inputs, resolution_bits):
        if resolution_bits is not None:
            return 'half an LSB at %d bits' % resolution_bits
        return 'the declared settling error target'

    # ------------------------------------------------------------------
    def _write_selected(self, draft, inputs, topology, vin, adc, base_nom, vref, reftol,
                        win_lo, win_hi, tolerance, tolerance_pct, derating,
                        leakage, max_source, power_rating, settling, resolution_bits,
                        candidates, r_top, r_bottom):
        series = inputs.get('series')
        t = tolerance
        r_top_min, r_top_max = r_top * (1 - t), r_top * (1 + t)
        r_bottom_min, r_bottom_max = r_bottom * (1 - t), r_bottom * (1 + t)
        k_min = r_bottom_min / (r_top_max + r_bottom_min)
        k_max = r_bottom_max / (r_top_min + r_bottom_max)
        k_nom = r_bottom / (r_top + r_bottom)
        rth_min = r_top_min * r_bottom_min / (r_top_min + r_bottom_min)
        rth_nom = r_top * r_bottom / (r_top + r_bottom)
        rth_max = r_top_max * r_bottom_max / (r_top_max + r_bottom_max)

        base_low, base_high = self._base_interval(topology, base_nom, reftol)
        base_interval = Interval(base_low, base_high)
        output = base_interval + (vin - base_interval) * Interval(k_min, k_max)
        shift = leakage * rth_max
        output_worst = Interval(output.lo - shift, output.hi + shift)
        output_nominal = base_nom + (vin.nominal - base_nom) * k_nom
        margin_lo = output_worst.lo - win_lo
        margin_hi = win_hi - output_worst.hi

        if topology == 'divider_to_vref':
            chain = vin - base_interval
        else:
            chain = vin
        chain_max = max(abs(chain.lo), abs(chain.hi))
        current_max = chain_max / (r_top_min + r_bottom_min)
        current_nominal = abs(vin.nominal - base_nom) / (r_top + r_bottom)
        power_top = current_max * current_max * r_top_max
        power_bottom = current_max * current_max * r_bottom_max
        power_worst = max(power_top, power_bottom)
        required_rating = (power_worst / (1 - derating)) if derating < 1 else power_worst
        voltage_top = chain_max * r_top_max / (r_top_min + r_bottom_min)
        voltage_bottom = chain_max * r_bottom_max / (r_top_min + r_bottom_min)

        # ---- components ---------------------------------------------
        top_pins = [{'name': '1', 'semantic': 'input_side'},
                    {'name': '2', 'semantic': 'tap_side'}]
        bottom_pins = [{'name': '1', 'semantic': 'tap_side'},
                       {'name': '2', 'semantic': 'reference_side'}]
        resistor_series = series if series != 'explicit' else None
        r_top_component = draft.component(
            'divider_top', 'resistor', value=r_top, tolerance_pct=tolerance_pct,
            series=resistor_series, power_rating_w=required_rating,
            voltage_rating_v=voltage_top, pins=top_pins,
            requirements={
                'worst_case_power_w': quantity_json(power_top, 'power'),
                'required_power_rating_w': quantity_json(required_rating, 'power'),
                'worst_case_voltage_v': quantity_json(voltage_top, 'voltage'),
                'derating_pct': quantity_json(derating * 100, 'percent'),
            },
            notes='Standard IEC 60063 value; package power/voltage ratings are requirements, not '
                  'a bound part.')
        r_bottom_component = draft.component(
            'divider_bottom', 'resistor', value=r_bottom, tolerance_pct=tolerance_pct,
            series=resistor_series, power_rating_w=required_rating,
            voltage_rating_v=voltage_bottom, pins=bottom_pins,
            requirements={
                'worst_case_power_w': quantity_json(power_bottom, 'power'),
                'required_power_rating_w': quantity_json(required_rating, 'power'),
                'worst_case_voltage_v': quantity_json(voltage_bottom, 'voltage'),
                'derating_pct': quantity_json(derating * 100, 'percent'),
            },
            notes='Standard IEC 60063 value; package power/voltage ratings are requirements, not '
                  'a bound part.')

        # ---- nets, ports, endpoints ---------------------------------
        vin_net = draft.net('VIN', role='signal', scope='external',
                            voltage_domain='measured_input',
                            notes='Measured input before the divider; protection is not modelled')
        vout_net = draft.net('VOUT', role='signal', scope='external',
                             voltage_domain='adc_input',
                             notes='Divider tap feeding the ADC input')
        gnd_net = draft.net('GND', role='ground', scope='external',
                            notes='ADC ground reference')
        reference_net = None
        if topology == 'divider_to_vref':
            reference_net = draft.net('VREF', role='reference', scope='external',
                                      voltage_domain='adc_reference',
                                      notes='ADC reference that R_bottom returns to')

        draft.connect(r_top_component['ref'], '1', vin_net, 'input_side')
        draft.connect(r_top_component['ref'], '2', vout_net, 'tap_side')
        draft.connect(r_bottom_component['ref'], '1', vout_net, 'tap_side')
        draft.connect(r_bottom_component['ref'], '2',
                      reference_net if reference_net is not None else gnd_net,
                      'reference_side')

        draft.port('VIN', 'input', 'analog', net=vin_net, voltage=vin,
                   current=Interval(Fraction(0), current_max),
                   description='Measured analog input voltage')
        draft.port('VOUT', 'output', 'analog', net=vout_net, voltage=output_worst,
                   current=Interval.point(leakage),
                   description='Divider tap to the ADC input; worst-case range over tolerance, '
                               'leakage and reference tolerance')
        draft.port('GND', 'passive', 'ground', net=gnd_net,
                   description='ADC ground return')
        if reference_net is not None:
            draft.port('VREF', 'passive', 'reference', net=reference_net,
                       voltage=Interval(base_low, base_high) if reftol is not None
                       else Interval.point(base_nom),
                       description='ADC reference voltage that R_bottom returns to')

        # ---- calculations ------------------------------------------
        draft.calculation(
            'selected_divider',
            'Selected standard divider pair and its ratio',
            'k = R_bottom/(R_top+R_bottom);  k_min = R_bottom_min/(R_top_max+R_bottom_min);  '
            'k_max = R_bottom_max/(R_top_min+R_bottom_max)',
            inputs={'selected_r_top': quantity_json(r_top, 'resistance'),
                    'selected_r_bottom': quantity_json(r_bottom, 'resistance'),
                    'resistance_range_top': Interval(r_top_min, r_top_max).as_json('resistance'),
                    'resistance_range_bottom': Interval(r_bottom_min,
                                                        r_bottom_max).as_json('resistance'),
                    'resistor_tolerance_pct': quantity_json(tolerance_pct, 'percent')},
            result={'ratio_nominal': to_json_number(k_nom),
                    'ratio_min': to_json_number(k_min),
                    'ratio_max': to_json_number(k_max)},
            unit='1',
            limit=None,
            margin=None,
            method='exact rational interval arithmetic',
            assumptions=['R_top and R_bottom tolerances move independently (independent worst '
                         'case)'],
            not_modelled=['resistor temperature coefficient and self-heating drift'])

        draft.calculation(
            'worst_case_output',
            'Worst-case tap voltage against the ADC legal range',
            'VOUT = VREF + (VIN - VREF)*k (reference tolerance included); '
            'VOUT_worst = VOUT +/- I_leak*R_th_max; compare against adc_input_range +/- margin',
            inputs={'topology': topology,
                    'input_voltage': vin.as_json('voltage'),
                    'ratio_range': {'min': to_json_number(k_min), 'max': to_json_number(k_max),
                                    'unit': '1'},
                    'reference_voltage': quantity_json(base_nom, 'voltage'),
                    'reference_tolerance_pct': (quantity_json(reftol * 100, 'percent')
                                                if reftol is not None else None),
                    'adc_leakage_current': quantity_json(leakage, 'current'),
                    'source_impedance_max': quantity_json(rth_max, 'resistance')},
            result={'min_v': to_json_number(output_worst.lo),
                    'max_v': to_json_number(output_worst.hi),
                    'nominal_v': to_json_number(output_nominal),
                    'leakage_shift_v': to_json_number(shift)},
            unit='V',
            limit={'adc_window_min': quantity_json(win_lo, 'voltage'),
                   'adc_window_max': quantity_json(win_hi, 'voltage')},
            margin={'margin_to_min_v': quantity_json(margin_lo, 'voltage'),
                    'margin_to_max_v': quantity_json(margin_hi, 'voltage')},
            method='exact rational interval arithmetic',
            assumptions=['the input range, both resistor tolerances, the leakage magnitude and '
                         'the reference tolerance can occur at their worst simultaneously',
                         'leakage is applied in the worst direction through the Thevenin source '
                         'impedance'],
            not_modelled=['leakage current polarity and temperature dependence',
                          'ADC input capacitance dynamically loading the tap',
                          'resistor temperature coefficients and PCB leakage'])

        draft.calculation(
            'divider_power',
            'Divider current and worst-case resistor dissipation',
            'I_max = max|VIN - VREF| / (R_top_min + R_bottom_min);  '
            'P_top = I_max^2*R_top_max;  P_bottom = I_max^2*R_bottom_max;  '
            'required_rating = max(P_top,P_bottom)/(1 - derating)',
            inputs={'chain_voltage_max': quantity_json(chain_max, 'voltage'),
                    'r_top_min': quantity_json(r_top_min, 'resistance'),
                    'r_bottom_min': quantity_json(r_bottom_min, 'resistance'),
                    'power_derating_pct': quantity_json(derating * 100, 'percent')},
            result={'current_max_a': to_json_number(current_max),
                    'current_nominal_a': to_json_number(current_nominal),
                    'power_top_w': to_json_number(power_top),
                    'power_bottom_w': to_json_number(power_bottom),
                    'required_power_rating_w': to_json_number(required_rating)},
            unit='W',
            limit={'declared_power_rating_w': (quantity_json(power_rating, 'power')
                                               if power_rating is not None else None)},
            margin={'rating_margin_w': (quantity_json(power_rating - required_rating, 'power')
                                        if power_rating is not None else None)},
            method='exact rational arithmetic',
            assumptions=['the largest chain voltage and the smallest total resistance occur '
                         'together, which is the conservative power case'],
            not_modelled=['pulse power during input transients', 'resistor voltage coefficient'])

        draft.calculation(
            'source_impedance',
            'Thevenin source impedance seen by the ADC input',
            'R_th = R_top*R_bottom/(R_top+R_bottom);  R_th_max = R_top_max*R_bottom_max / '
            '(R_top_max+R_bottom_max)',
            inputs={'selected_r_top': quantity_json(r_top, 'resistance'),
                    'selected_r_bottom': quantity_json(r_bottom, 'resistance')},
            result={'thevenin_nominal_ohm': to_json_number(rth_nom),
                    'thevenin_min_ohm': to_json_number(rth_min),
                    'thevenin_max_ohm': to_json_number(rth_max)},
            unit='ohm',
            limit={'declared_max_source_impedance': (quantity_json(max_source, 'resistance')
                                                     if max_source is not None else None)},
            margin={'margin_ohm': (quantity_json(max_source - rth_max, 'resistance')
                                   if max_source is not None else None)},
            method='exact rational arithmetic',
            assumptions=['the ADC sees the divider Thevenin resistance at DC'],
            not_modelled=['PCB trace resistance', 'switch/multiplexer series resistance'])

        draft.calculation(
            'leakage_tap_shift',
            'ADC input leakage shift at the tap',
            'V_shift = I_leak * R_th_max',
            inputs={'adc_leakage_current': quantity_json(leakage, 'current'),
                    'thevenin_max_ohm': quantity_json(rth_max, 'resistance')},
            result={'shift_v': to_json_number(shift)},
            unit='V',
            limit=None,
            margin=None,
            assumptions=['the leakage magnitude is bounded and its worst polarity always '
                         'increase/decreases the tap'],
            not_modelled=['leakage injection through the sample switch',
                          'leakage temperature coefficient'])

        lsb = None
        if resolution_bits is not None:
            lsb = adc.width / (2 ** resolution_bits)
            draft.calculation(
                'adc_lsb',
                'ADC LSB for reporting the tap in codes',
                'LSB = (adc_input_range_max - adc_input_range_min) / 2^N',
                inputs={'adc_input_range': adc.as_json('voltage'),
                        'adc_resolution_bits': resolution_bits},
                result={'lsb_v': to_json_number(lsb),
                        'leakage_shift_lsb': to_json_number(shift / lsb),
                        'output_span_lsb': to_json_number((output_worst.hi -
                                                           output_worst.lo) / lsb)},
                unit='V',
                limit=None,
                margin=None,
                assumptions=['the ADC full-scale span equals the declared legal input range'],
                not_modelled=['ADC INL/DNL, offset and gain errors'])

        if reftol is not None:
            gain_error = reftol / (1 + reftol)
            draft.calculation(
                'reference_tolerance_effect',
                'ADC reference tolerance effect on the conversion',
                'reading_error_fraction = t/(1+t) for a reference high by t',
                inputs={'reference_tolerance_pct': quantity_json(reftol * 100, 'percent'),
                        'reference_voltage': quantity_json(base_nom, 'voltage')},
                result={'relative_gain_error_pct': to_json_number(gain_error * 100),
                        'voltage_error_at_max_tap_v': to_json_number(output_worst.hi *
                                                                     gain_error)},
                unit='%',
                limit=None,
                margin=None,
                assumptions=['the ADC transfer is ratiometric to the declared reference'],
                not_modelled=['reference long-term drift', 'ADC gain error not related to the '
                              'reference'])

        if settling is not None:
            tau_max = rth_max * settling['capacitance']
            required_time = settling['required_k'] * tau_max
            achieved_k = settling['sample_time'].lo / tau_max
            draft.calculation(
                'sampling_settling',
                'ADC sample-and-hold settling of the Thevenin source',
                'tau = R_th_max * C_sample;  t_required = k_required * tau with '
                'k_required = -ln(error_fraction);  pass when t_sample_min >= t_required',
                inputs={'thevenin_max_ohm': quantity_json(rth_max, 'resistance'),
                        'sample_hold_capacitance': quantity_json(settling['capacitance'],
                                                                 'capacitance'),
                        'sample_time_min': quantity_json(settling['sample_time'].lo, 'time'),
                        'settling_error_target': settling['target_text']},
                result={'tau_s': to_json_number(tau_max),
                        'required_time_constants': to_json_number(settling['required_k']),
                        'required_settling_time_s': to_json_number(required_time),
                        'achieved_time_constants': to_json_number(achieved_k),
                        'error_target_fraction': to_json_number(settling['error_fraction'])},
                unit='s',
                limit={'sample_time_min': quantity_json(settling['sample_time'].lo, 'time')},
                margin={'margin_s': quantity_json(settling['sample_time'].lo - required_time,
                                                  'time')},
                method='first-order RC exponential settling, logarithm evaluated with Decimal',
                assumptions=['the source is a single Thevenin resistance charging the total '
                             'sample-hold capacitance',
                             'the sampled node starts at 0 V and must settle to within the stated '
                             'fraction of full scale'],
                not_modelled=['ADC sample-switch charge injection',
                              'dielectric absorption of the external capacitor',
                              'multiplexer channel-to-channel charge sharing'])
        else:
            draft.calculation(
                'sampling_settling',
                'ADC sample-and-hold settling (unverified)',
                'tau = R_th*C_sample and the required time constant count can only be computed '
                'when the sample time, sample-hold capacitance and an error target are declared',
                inputs={'thevenin_max_ohm': quantity_json(rth_max, 'resistance')},
                result={'verified': False,
                        'reason': 'ADC sample time / sample-hold capacitance / error target not '
                                  'declared; sample settling is explicitly unverified'},
                unit='s',
                limit=None,
                margin=None,
                assumptions=[],
                not_modelled=['the whole settling analysis'])

        # ---- optional RC filter ------------------------------------
        capacitor_component = None
        rc = inputs.get('rc_filter')
        if rc is not None:
            capacitor_component = self._write_rc(draft, rc, inputs, r_top, r_bottom,
                                                 rth_min, rth_nom, rth_max,
                                                 output_worst, adc, resolution_bits, settling)
        if capacitor_component is not None:
            draft.connect(capacitor_component['ref'], '1', vout_net, 'tap_side')
            draft.connect(capacitor_component['ref'], '2', gnd_net, 'ground_side')

        # ---- constraints -------------------------------------------
        draft.constraint('resistor_series',
                         'Use R_top and R_bottom from %s with tolerance ±%s%%.'
                         % (series, format_number(tolerance_pct)),
                         kind='hard', applies_to='R_top/R_bottom', source='derivation')
        draft.constraint('adc_range',
                         'The worst-case tap must stay inside %s..%s V at every declared input, '
                         'resistor-tolerance, leakage and reference-tolerance extreme.'
                         % (format_number(win_lo), format_number(win_hi)),
                         kind='hard', applies_to='VOUT', source='derivation')
        if max_source is not None:
            draft.constraint('source_impedance_limit',
                             'The worst-case Thevenin source impedance must not exceed %s ohm.'
                             % format_number(max_source),
                             kind='hard', applies_to='VOUT', source='derivation')
        if power_rating is not None:
            draft.constraint('resistor_rating',
                             'Each resistor must be rated at least %s W at the declared derating.'
                             % format_number(required_rating),
                             kind='hard', applies_to='R_top/R_bottom', source='derivation')
        if settling is not None:
            draft.constraint('sampling_settles',
                             'The ADC sample-and-hold must settle within %s s at the selected '
                             'Thevenin impedance, sample-hold capacitance and error target.'
                             % format_number(settling['sample_time'].lo),
                             kind='hard', applies_to='VOUT', source='derivation')
        else:
            draft.constraint('sampling_unverified',
                             'ADC sample time, sample-hold capacitance and error target were not '
                             'all declared: sample settling is unverified and this block does not '
                             'claim ADC accuracy.',
                             kind='verification', applies_to='VOUT', source='declaration')

        draft.constraint('verify_worst_case',
                         'Verify the tap voltage at the input and temperature extremes after '
                         'assembly; the numerical worst case is an interval proof, not a '
                         'measurement.',
                         kind='verification', applies_to='VOUT', source='derivation')
        if lsb is not None and shift > lsb:
            draft.constraint('leakage_error_above_one_lsb',
                             'The leakage-induced tap shift (%s LSB) exceeds one LSB; consider a '
                             'lower Thevenin impedance or an input buffer.'
                             % format_number(shift / lsb),
                             kind='advisory', applies_to='VOUT', source='derivation')
        draft.constraint('tap_layout',
                         'Keep the VOUT tap short and the optional filter capacitor close to the '
                         'ADC input pin; the tap is a high-impedance analog node.',
                         kind='layout', applies_to='VOUT', source='derivation')

        # ---- evidence, assumptions, unknowns -----------------------
        draft.evidence('input_range', 'user_declared',
                       'Measured input range declared by the caller: %s..%s V.'
                       % (format_number(vin.lo), format_number(vin.hi)),
                       source={'document': 'caller declaration'}, applies_to='VIN',
                       verified=False)
        draft.evidence('adc_legal_range', 'user_declared',
                       'ADC legal input range declared by the caller: %s..%s V.'
                       % (format_number(adc.lo), format_number(adc.hi)),
                       source={'document': 'caller declaration'}, applies_to='VOUT',
                       verified=False)
        draft.evidence('adc_leakage', 'user_declared',
                       'ADC input leakage magnitude declared by the caller: %s A.'
                       % format_number(leakage),
                       source={'document': 'caller declaration'}, applies_to='VOUT',
                       verified=False)
        if vref is not None:
            draft.evidence('adc_reference', 'user_declared',
                           'ADC reference declared by the caller: %s V, tolerance %s%%.'
                           % (format_number(vref),
                              format_number(reftol * 100) if reftol is not None else 'not '
                              'declared'),
                           source={'document': 'caller declaration'}, applies_to='VREF',
                           verified=False)
        draft.evidence('standard_series', 'standard',
                       'Resistor values taken from IEC 60063 series %s.' % series,
                       source={'document': 'IEC 60063', 'section': 'preferred number series',
                               'url': 'https://webstore.iec.ch/publication/593'})
        draft.evidence('derivation_math', 'derivation',
                       'Divider ratio, worst-case tap, power, Thevenin impedance, leakage shift '
                       'and settling are derived here with exact rational interval arithmetic '
                       '(logarithm via Decimal, no binary floats in the decision).')
        draft.assumption('The input range, both resistor tolerances, the ADC leakage magnitude '
                         'and the reference tolerance can reach their worst values '
                         'simultaneously (independent worst case).',
                         impact='conservative tap bounds; a correlated worst case would be '
                                'narrower')
        draft.assumption('ADC input leakage is the only DC load at the tap; any additional '
                         'external load must be declared and would change the ratio.',
                         impact='an undeclared load current is not covered by the worst-case tap')
        draft.assumption('The ADC sample-and-hold is modelled as a single resistance charging '
                         'one lumped capacitance when its facts are declared.',
                         impact='settling is a first-order estimate, not a converter datasheet '
                                'guarantee')
        if settling is None:
            draft.unknown('settling_unverified',
                          'ADC sample time, sample-hold capacitance and settling error target '
                          'were not all declared; sample-and-hold settling is unverified.',
                          impact='the ADC may not reach the required accuracy even though the DC '
                                 'tap is inside the legal range',
                          how_to_resolve='declare the ADC sampling facts from the exact datasheet '
                                         'and re-run the block')
        if resolution_bits is None:
            draft.unknown('adc_resolution_unknown',
                          'ADC resolution was not declared; the tap is not reported in LSB and '
                          'the quantization error of the conversion is unknown.',
                          impact='cannot compare the worst-case tap tolerance with one code',
                          how_to_resolve='declare adc_resolution_bits from the ADC datasheet')
        if reftol is None:
            draft.unknown('reference_tolerance_unknown',
                          'ADC reference tolerance was not declared; the reference contribution '
                          'to the conversion error is unknown.',
                          impact='the conversion gain error from the reference is not bounded',
                          how_to_resolve='declare adc_reference_tolerance_pct from the reference '
                                         'or ADC datasheet')
        draft.unknown('temperature_drift_not_modelled',
                      'Resistor temperature coefficients, leakage temperature dependence and '
                      'reference drift over temperature are not modelled.',
                      impact='worst-case bounds assume the declared values apply over the full '
                             'temperature range',
                      how_to_resolve='use datasheet temperature coefficients and re-derive if the '
                                     'declared ranges do not already cover temperature')

    # ------------------------------------------------------------------
    def _write_protection_domain(self, draft):
        """Record protection and converter-accuracy as explicit, open domains."""
        draft.constraint('protection_negative_input',
                         'Negative input is not protected by this divider: add and verify an '
                         'external clamp/limiting network and confirm the divider and ADC pin '
                         'absolute maximum ratings.',
                         kind='verification', applies_to='VIN', source='declaration')
        draft.constraint('protection_overvoltage',
                         'Overvoltage at VIN (above the ADC supply/reference or the ADC pin '
                         'absolute maximum) is not clamped or limited by this block; the external '
                         'protection network must be designed and verified separately.',
                         kind='verification', applies_to='VIN', source='declaration')
        draft.constraint('protection_reverse_feed',
                         'Reverse feed (VIN below ground or below VREF while the ADC is powered) '
                         'can push current through the divider into the source; no reverse-current '
                         'path is modelled or guaranteed.',
                         kind='verification', applies_to='VIN', source='declaration')
        draft.constraint('protection_series_resistor',
                         'Any series protection resistor added between VIN and R_top changes the '
                         'divider ratio; it must be included in the declared divider or the ratio '
                         'must be re-derived and re-verified. This block does not model it.',
                         kind='verification', applies_to='VIN', source='declaration')
        draft.constraint('adc_accuracy_not_proven',
                         'A tap inside the ADC legal range does not prove accuracy: converter '
                         'INL/DNL, offset, gain, noise and reference errors must be checked '
                         'against the system error budget separately.',
                         kind='verification', applies_to='VOUT', source='derivation')
        draft.unknown('accuracy_not_proven',
                      'ADC accuracy is outside this block: INL/DNL, offset, gain, noise, '
                      'reference drift and the converter transfer function are not modelled.',
                      impact='a divider inside the legal range is a range contract only',
                      how_to_resolve='check the converter error budget against the system '
                                     'requirement and measure the assembled channel')
        draft.unknown('protection_unverified',
                      'Negative input, overvoltage, reverse feed and series protection resistors '
                      'are emitted as separate constraints and are not covered by this math.',
                      impact='without the external protection network the ADC pin may be damaged',
                      how_to_resolve='design the protection network and verify the pin absolute '
                                     'maximum ratings against the declared input extremes')

    # ------------------------------------------------------------------
    def _write_rc(self, draft, rc, inputs, r_top, r_bottom, rth_min, rth_nom, rth_max,
                  output_worst, adc, resolution_bits, settling):
        tolerance_pct = rc.get('capacitor_tolerance_pct')
        if tolerance_pct is None:
            raise InputInvalid('rc_filter requires capacitor_tolerance_pct',
                               field='rc_filter.capacitor_tolerance_pct')
        if tolerance_pct >= 100:
            raise InputInvalid('capacitor tolerance must stay below 100%',
                               field='rc_filter.capacitor_tolerance_pct')
        tolerance = tolerance_pct / 100
        explicit = rc.get('capacitance')
        window = rc.get('capacitance_range')
        target = rc.get('target_bandwidth')
        if explicit is not None and window is not None:
            raise InputInvalid('rc_filter takes capacitance or capacitance_range, not both',
                               field='rc_filter')
        if explicit is not None:
            capacitance = explicit
            capacitor_series = None
        else:
            if window is None:
                raise InputInvalid('rc_filter requires capacitance or capacitance_range',
                                   field='rc_filter')
            if target is None:
                raise InputInvalid(
                    'selecting a capacitor from capacitance_range requires target_bandwidth',
                    field='rc_filter.target_bandwidth')
            capacitor_series = rc.get('capacitor_series')
            candidates = series_values(capacitor_series, window.lo, window.hi,
                                       decades=_CAPACITOR_DECADES)
            if not candidates:
                raise NoFeasibleSolution(
                    'no standard %s capacitor exists in the declared capacitance window'
                    % capacitor_series)
            matches = []
            for candidate in candidates:
                frequency = _bandwidth(rth_nom, candidate)
                if target.contains(frequency):
                    matches.append((abs(frequency - target.nominal), candidate, frequency))
            if not matches:
                raise NoFeasibleSolution(
                    'no standard %s capacitor puts the -3 dB bandwidth inside the declared '
                    'target range %s..%s Hz at the selected Thevenin impedance'
                    % (capacitor_series, format_number(target.lo), format_number(target.hi)))
            matches.sort(key=lambda item: (item[0], item[1]))
            capacitance = matches[0][1]

        c_min = capacitance * (1 - tolerance)
        c_max = capacitance * (1 + tolerance)
        tau_nom = rth_nom * capacitance
        bandwidth_nom = _bandwidth(rth_nom, capacitance)
        bandwidth_min = _bandwidth(rth_max, c_max)
        bandwidth_max = _bandwidth(rth_min, c_min) if rth_min > 0 else None
        voltage_rating = max(abs(output_worst.lo), abs(output_worst.hi), adc.hi)

        capacitor = draft.component(
            'adc_rc_filter', 'capacitor', value=capacitance, tolerance_pct=tolerance_pct,
            series=capacitor_series, voltage_rating_v=voltage_rating,
            pins=[{'name': '1', 'semantic': 'tap_side'},
                  {'name': '2', 'semantic': 'ground_side'}],
            requirements={'nominal_time_constant': quantity_json(tau_nom, 'time'),
                          'corner_frequency': quantity_json(bandwidth_nom, 'frequency')},
            notes='Optional ADC input filter capacitor; it adds a pole and must be compatible '
                  'with the signal bandwidth budget.')

        draft.calculation(
            'rc_bandwidth',
            'Optional RC filter corner and bandwidth change',
            'tau = R_th*C;  f_-3dB = 1/(2*pi*R_th*C);  pi and the division evaluated with '
            'Decimal',
            inputs={'thevenin_nominal_ohm': quantity_json(rth_nom, 'resistance'),
                    'thevenin_min_ohm': quantity_json(rth_min, 'resistance'),
                    'thevenin_max_ohm': quantity_json(rth_max, 'resistance'),
                    'capacitance': quantity_json(capacitance, 'capacitance'),
                    'capacitor_tolerance_pct': quantity_json(tolerance_pct, 'percent')},
            result={'bandwidth_without_capacitor_hz': None,
                    'bandwidth_nominal_hz': to_json_number(bandwidth_nom),
                    'bandwidth_min_hz': (to_json_number(bandwidth_min)
                                         if bandwidth_min is not None else None),
                    'bandwidth_max_hz': to_json_number(bandwidth_max),
                    'time_constant_nominal_s': to_json_number(tau_nom)},
            unit='Hz',
            limit=None,
            margin=None,
            method='first-order RC corner frequency, pi evaluated with Decimal',
            assumptions=['the tap is driven by the divider Thevenin resistance and loaded only '
                         'by the capacitor (and the ADC sample switch)'],
            not_modelled=['without a capacitor the ADC-limited bandwidth is not modelled, so no '
                          'numeric "before" bandwidth is claimed',
                          'capacitor ESR/ESL and dielectric absorption',
                          'signal distortion and multiplexer settling after the added pole'])
        if bandwidth_nom is not None:
            draft.constraint(
                'rc_bandwidth_budget',
                'The optional RC filter adds a %.6g Hz corner (nominal); the measured signal '
                'bandwidth must stay well below it and the source must still settle the sample '
                'network.' % float(to_json_number(bandwidth_nom)),
                kind='advisory', applies_to='VOUT', source='derivation')
        if settling is not None:
            total_cap_max = c_max + settling['capacitance']
            tau_total = rth_max * total_cap_max
            draft.calculation(
                'rc_settling_effect',
                'Sample settling change caused by the added filter capacitor',
                'tau_with_C = R_th_max*(C_filter_max + C_sample);  compare with tau without the '
                'filter capacitor',
                inputs={'thevenin_max_ohm': quantity_json(rth_max, 'resistance'),
                        'filter_capacitance_max': quantity_json(c_max, 'capacitance'),
                        'sample_hold_capacitance': quantity_json(settling['capacitance'],
                                                                 'capacitance')},
                result={'tau_without_filter_s': to_json_number(rth_max *
                                                               settling['capacitance']),
                        'tau_with_filter_s': to_json_number(tau_total)},
                unit='s',
                limit=None,
                margin=None,
                assumptions=['the filter capacitor and the sample-hold capacitor share the same '
                             'source resistance'],
                not_modelled=['sample-switch charge injection and the exact acquisition waveform'])
        return capacitor


def _optional_quantity(inputs, name):
    return inputs.quantity(name) if name in inputs else None
