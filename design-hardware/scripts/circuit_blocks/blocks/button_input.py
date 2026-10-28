"""F2 — push-button input with a pull resistor and optional RC filter.

Two explicit topologies are supported and never silently invented:

* ``pull_up``   ``VCC -[R]- node -[contact]- GND``  -> pressed pulls the node LOW
* ``pull_down`` ``VCC -[contact]- node -[R]- GND``  -> pressed pulls the node HIGH

The caller must choose the variant (``variant`` is required) and the resistor is
selected from a declared standard series.  Every hard bound is checked with
exact :class:`fractions.Fraction` arithmetic:

* closed-contact current ``I = V_rail_max / (R_min + Rc_min)`` must stay inside
  the declared contact current rating;
* the switch-open level must still beat the guaranteed logic threshold at the
  worst-case resistor tolerance and the declared input leakage
  (``V_node = V_rail - I_leak*R_max`` for pull-up, ``I_leak*R_max`` for
  pull-down);
* with a declared contact resistance, the switch-closed level is the true
  divider ``V_rail*Rc/(R+Rc)`` (or ``V_rail*R/(R+Rc)`` for pull-down).

An optional capacitor from the node to ground forms an RC low-pass.  A standard
resistor + standard capacitor pair is chosen so the nominal ``R*C`` falls inside
the declared target range, and the threshold-crossing times are derived from the
declared thresholds with the exponential charge equation
``t = -R*C*ln(1 - Vth/Vrail)``.  The RC product is deliberately *not* presented
as a debounce time: mechanical bounce survives the filter, slow edges need a
Schmitt-trigger input and firmware debounce remains a separate precondition.

The contact is an abstract two-terminal model.  No physical pin number is ever
emitted; a four-pin tact switch is only accepted with a caller-declared verified
internal-connection fact, because inventing a drop-in pin mapping is unsafe.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction

from ..errors import InputInvalid, NeedsDeviceFacts, NoFeasibleSolution
from ..eseries import choose, values as series_values
from ..numeric import format_number, to_json_number
from ..ranges import Interval
from ..units import quantity_json
from .base import Block

#: Significant digits used for the natural logarithm.  ``Decimal.ln`` is
#: correctly rounded, so the crossing times are deterministic on every platform
#: and no binary float ever participates in a decision.
_LOG_PRECISION = 40

#: Capacitors need decades below 1 uF; the default eseries window starts at 1e-6.
_CAPACITOR_DECADES = range(-12, 7)


def _ln(value):
    """Natural logarithm of an exact positive Fraction, evaluated with Decimal."""
    value = value if isinstance(value, Fraction) else Fraction(value)
    if value <= 0:
        raise InputInvalid('logarithm argument must be positive')
    with localcontext() as context:
        context.prec = _LOG_PRECISION
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
        return Fraction(decimal_value.ln())


def _charging_time(tau, threshold, rail):
    """Time for a 0 -> rail exponential charge to cross ``threshold``."""
    return -tau * _ln(1 - threshold / rail)


def _discharging_time(tau, threshold, rail):
    """Time for a rail -> 0 exponential decay to cross ``threshold``."""
    return -tau * _ln(threshold / rail)


class ButtonInput(Block):
    MODULE_TYPE = 'button_input'
    TEMPLATE_VERSION = '1.0.0'
    TITLE = 'Push-button input with pull resistor and optional RC filter'
    SUMMARY = ('Selects a standard pull-up/pull-down resistor (and an optional standard '
               'resistor+capacitor RC filter) from declared rail, logic-threshold, leakage, '
               'contact and tolerance facts, recomputes the closed-contact current and the '
               'open/closed levels, and reports threshold-crossing times separately from any '
               'debounce claim.')
    TOPOLOGY = ('rail - pull resistor - node - [abstract two-terminal contact to the opposite '
                'rail]; optional capacitor from node to ground; OUT is the node feeding a logic '
                'input')
    APPLICABILITY = (
        'pull_up_no_rc: VCC -[R]- node -[contact]- GND, pressed pulls the node LOW',
        'pull_up_with_rc: same topology plus a capacitor from node to ground (RC low-pass)',
        'pull_down_no_rc: VCC -[contact]- node -[R]- GND, pressed pulls the node HIGH',
        'pull_down_with_rc: same topology plus a capacitor from node to ground',
        'single button contact; the abstract contact is modelled as two terminals',
    )
    NON_APPLICABILITY = (
        'matrix / scanned keypads, rotary encoders and multi-key rollover',
        'contacts whose internal pin mapping is unknown (no drop-in pin numbers are invented)',
        'analog or resistive-ladder key inputs (use an ADC divider)',
        'a guaranteed debounce time: an RC filter alone does not remove mechanical bounce',
    )
    REQUIRED_DEVICE_FACTS = (
        'logic-input guaranteed HIGH threshold V_IH and guaranteed LOW threshold V_IL',
        'logic-input leakage current magnitude',
        'button contact maximum current rating',
        'optional: closed-contact resistance, bounce duration, verified internal connection of a '
        'four-pin tact switch',
    )
    SOURCES = (
        {'document': 'IEC 60063 preferred number series (E6/E12/E24/E48/E96)',
         'why': 'standard resistor and capacitor values'},
        {'document': 'MCU/SoC datasheet or declared GPIO input facts',
         'why': 'guaranteed V_IH/V_IL and input leakage current'},
        {'document': 'button/switch datasheet or declared contact facts',
         'why': 'contact current rating, contact resistance, bounce time, pin connection'},
    )

    #: Variants the module can generate (declared capability; selected by ``variant``
    #: plus the presence or absence of ``rc_filter``).
    VARIANTS = ('pull_up_no_rc', 'pull_up_with_rc', 'pull_down_no_rc', 'pull_down_with_rc')

    INPUT_SCHEMA = {
        'supply_voltage': {
            'kind': 'range', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'Rail at the pull resistor (V); it is also the open-state level.'},
        'v_ih': {
            'kind': 'range', 'family': 'voltage', 'positive': True,
            'doc': 'Guaranteed HIGH input threshold V_IH (V): at or above it the logic input is '
                   'guaranteed HIGH. A range is accepted and its highest endpoint is the worst case.'},
        'v_il': {
            'kind': 'range', 'family': 'voltage', 'nonnegative': True,
            'doc': 'Guaranteed LOW input threshold V_IL (V): at or below it the logic input is '
                   'guaranteed LOW. A range is accepted and its lowest endpoint is the worst case.'},
        'logic_source': {
            'kind': 'enum', 'values': ['datasheet', 'user_declared', 'derived'],
            'default': 'user_declared',
            'doc': 'Provenance of the V_IH/V_IL facts.'},
        'input_leakage': {
            'kind': 'quantity', 'family': 'current', 'nonnegative': True,
            'doc': 'Magnitude of the logic-input leakage current (A). Required: a GPIO input is '
                   'never assumed to have zero leakage.'},
        'variant': {
            'kind': 'enum', 'values': ['pull_up', 'pull_down'], 'required': True,
            'doc': 'pull_up: resistor to VCC, contact to GND. pull_down: resistor to GND, contact '
                   'to VCC. Must be chosen explicitly.'},
        'active_level': {
            'kind': 'enum', 'values': ['high', 'low'],
            'doc': 'Optional declared logic level of OUT while the button is pressed; must agree '
                   'with the variant (pull_up -> low, pull_down -> high).'},
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
        'contact': {
            'kind': 'object',
            'fields': {
                'current_limit_max': {
                    'kind': 'quantity', 'family': 'current', 'positive': True,
                    'doc': 'Maximum current the closed contact is rated to carry (A); required '
                           'for a ready result.'},
                'contact_resistance': {
                    'kind': 'range', 'family': 'resistance', 'nonnegative': True,
                    'doc': 'Closed-contact resistance range (ohm); optional, an ideal contact is '
                           'assumed when it is absent.'},
                'bounce_ms': {
                    'kind': 'number', 'nonnegative': True,
                    'doc': 'Mechanical bounce duration in milliseconds; reported, never removed '
                           'by the RC filter.'},
                'pin_configuration': {
                    'kind': 'enum', 'values': ['two_terminal_abstract', 'four_terminal_tact'],
                    'default': 'two_terminal_abstract',
                    'doc': 'Contact model. A four-pin tact switch needs a verified '
                           'internal-connection fact.'},
                'internal_connection_verified': {
                    'kind': 'bool', 'default': False,
                    'doc': 'Caller-declared verification of the four-pin internal connection; '
                           'recorded as unverified user evidence.'},
            },
            'doc': 'Abstract button contact facts.'},
        'rc_filter': {
            'kind': 'object',
            'fields': {
                'target_time_constant': {
                    'kind': 'range', 'family': 'time', 'positive': True, 'required': True,
                    'doc': 'Target RC product range (s). This is a time constant, not a debounce '
                           'time.'},
                'capacitance': {
                    'kind': 'range', 'family': 'capacitance', 'positive': True,
                    'doc': 'Optional allowed standard capacitor window (F).'},
                'capacitor_series': {
                    'kind': 'enum', 'values': ['E3', 'E6', 'E12'], 'default': 'E12',
                    'doc': 'Capacitor value series.'},
                'capacitor_tolerance_pct': {
                    'kind': 'quantity', 'family': 'percent', 'nonnegative': True, 'required': True,
                    'doc': 'Capacitor tolerance (±%) used for the worst-case RC spread.'},
            },
            'doc': 'Optional RC filter request; absent means no capacitor is fitted.'},
        'objective': {
            'kind': 'enum', 'values': ['auto', 'max_resistance', 'min_resistance',
                                       'time_constant_error'],
            'default': 'auto',
            'doc': 'Deterministic selection objective; "auto" means time_constant_error when '
                   'rc_filter is present, otherwise max_resistance (lowest static current).'},
        'notes': {'kind': 'string', 'doc': 'Free-form note copied into the result.'},
    }
    EXAMPLE_INPUT = {
        'supply_voltage': {'min': 3.135, 'max': 3.465},
        'v_ih': 2.31,
        'v_il': 0.99,
        'logic_source': 'datasheet',
        'input_leakage': '1uA',
        'variant': 'pull_up',
        'active_level': 'low',
        'series': 'E24',
        'value_range': {'min': '4.7k', 'max': '47k'},
        'resistor_tolerance_pct': 1,
        'contact': {
            'current_limit_max': '50mA',
            'contact_resistance': {'min': 0, 'max': 0.1},
            'bounce_ms': 5,
            'pin_configuration': 'two_terminal_abstract',
        },
        'rc_filter': {
            'target_time_constant': {'nominal': '1ms', 'tolerance_pct': 20},
            'capacitor_series': 'E12',
            'capacitor_tolerance_pct': 10,
        },
    }

    # ------------------------------------------------------------------
    def compute(self, draft, inputs):
        notes = inputs.get('notes')
        variant = inputs.enum('variant')
        active_level = inputs.get('active_level')
        self._check_active_level(variant, active_level)
        supply = inputs.interval('supply_voltage')

        self._require_thresholds(inputs)
        v_ih = inputs.interval('v_ih')
        v_il = inputs.interval('v_il')
        if v_il.hi >= v_ih.lo:
            raise InputInvalid(
                'v_il must stay below v_ih: declared V_IL up to %s V but V_IH from %s V'
                % (format_number(v_il.hi), format_number(v_ih.lo)), field='v_il')
        v_ih_worst = v_ih.hi
        v_il_worst = v_il.lo
        if inputs.get('input_leakage') is None:
            raise NeedsDeviceFacts(
                ['input_leakage'],
                'the logic-input leakage current is required: a GPIO input must never be assumed '
                'to have zero leakage, so the switch-open level cannot be proven without it')
        leakage = inputs.quantity('input_leakage')
        contact = self._require_contact(inputs)
        contact_resistance = contact.get('contact_resistance')
        resistance_declared = contact_resistance is not None
        rc_low = contact_resistance.lo if resistance_declared else Fraction(0)
        rc_high = contact_resistance.hi if resistance_declared else Fraction(0)
        current_limit = contact.quantity('current_limit_max')
        bounce_ms = contact.get('bounce_ms')
        bounce_seconds = Fraction(bounce_ms) / 1000 if bounce_ms is not None else None
        tolerance_pct = inputs.quantity('resistor_tolerance_pct')
        if tolerance_pct >= 100:
            raise InputInvalid('resistor tolerance must stay below 100%',
                               field='resistor_tolerance_pct')
        tolerance = tolerance_pct / 100

        candidates = self._candidates(inputs)
        if not candidates:
            raise InputInvalid('no resistor candidates: the declared series/value_range is empty')

        # The rail must be able to reach the guaranteed threshold even with an
        # ideal element; otherwise no resistor value can ever work.
        draft.calculation(
            'rail_threshold_check',
            'Rail can reach the guaranteed logic threshold',
            'V_rail_min >= V_IH_worst (pull_up open state) and V_rail_min >= V_IH_worst '
            '(pull_down closed state with an ideal contact)',
            inputs={'supply_voltage': supply.as_json('voltage'),
                    'v_ih': v_ih.as_json('voltage'),
                    'variant': variant},
            result={'v_rail_min_v': to_json_number(supply.lo),
                    'v_ih_worst_v': to_json_number(v_ih_worst),
                    'margin_v': to_json_number(supply.lo - v_ih_worst)},
            unit='V',
            limit={'v_ih_worst': quantity_json(v_ih_worst, 'voltage')},
            margin={'rail_margin_v': quantity_json(supply.lo - v_ih_worst, 'voltage')},
            assumptions=['the declared rail range bounds the node level in the ideal state'],
            not_modelled=['leakage and resistor tolerance (the next calculation covers them)'])
        if supply.lo < v_ih_worst:
            raise NoFeasibleSolution(
                'the rail cannot reach the guaranteed HIGH threshold: V_rail_min=%s V is below '
                'V_IH=%s V, so no pull resistor can make the node HIGH'
                % (format_number(supply.lo), format_number(v_ih_worst)),
                bounds={'v_rail_min': to_json_number(supply.lo),
                        'v_ih_worst': to_json_number(v_ih_worst)})

        if resistance_declared:
            self._check_contact_resistance_floor(draft, variant, supply, v_ih_worst, v_il_worst,
                                                 rc_high)

        lower_bounds, upper_bounds = self._hard_bounds(
            variant, supply, v_ih_worst, v_il_worst, leakage, current_limit, rc_low, rc_high)
        r_min_required = max([bound for _, bound in lower_bounds] + [Fraction(0)])
        r_max_allowed = (min(bound for _, bound in upper_bounds)
                         if upper_bounds else None)
        r_lower = r_min_required / (1 - tolerance)
        r_upper = (r_max_allowed / (1 + tolerance)
                   if r_max_allowed is not None else None)

        draft.calculation(
            'resistance_window',
            'Feasible pull-resistor window from the contact, level and leakage bounds',
            self._window_formula(variant),
            inputs={'supply_voltage': supply.as_json('voltage'),
                    'v_ih': v_ih.as_json('voltage'),
                    'v_il': v_il.as_json('voltage'),
                    'input_leakage': quantity_json(leakage, 'current'),
                    'contact_current_limit': quantity_json(current_limit, 'current'),
                    'contact_resistance': (contact_resistance.as_json('resistance')
                                           if resistance_declared else None),
                    'resistor_tolerance_pct': quantity_json(tolerance_pct, 'percent'),
                    'variant': variant},
            result={'r_min_required_ohm': to_json_number(r_lower),
                    'r_max_allowed_ohm': (to_json_number(r_upper)
                                          if r_upper is not None else None)},
            unit='ohm',
            method='closed-form interval bounds on the resistor divider/current equations',
            assumptions=['worst-case rail, leakage, threshold and resistor tolerance may occur '
                         'simultaneously (independent worst case)',
                         'input leakage flows in the direction that is worst for the checked level'],
            not_modelled=['leakage current temperature dependence',
                          'contact resistance variation with current/time',
                          'GPIO input capacitance affecting the DC level'])

        window_text = ('[%s, %s] ohm' % (format_number(r_lower), format_number(r_upper))
                       if r_upper is not None else '>= %s ohm' % format_number(r_lower))
        if r_upper is not None and r_lower > r_upper:
            raise NoFeasibleSolution(
                'the hard bounds conflict: the closed-contact/level constraints need R >= %s ohm '
                'while the open-state/leakage constraint needs R <= %s ohm'
                % (format_number(r_lower), format_number(r_upper)),
                bounds={'r_min_required': to_json_number(r_lower),
                        'r_max_allowed': to_json_number(r_upper)})
        allowed = [value for value in candidates
                   if value >= r_lower and (r_upper is None or value <= r_upper)]
        if not allowed:
            raise NoFeasibleSolution(
                'no standard resistor from the declared series lies in the feasible window %s'
                % window_text,
                bounds={'r_min_required': to_json_number(r_lower),
                        'r_max_allowed': (to_json_number(r_upper)
                                          if r_upper is not None else None)})

        rc_filter = inputs.get('rc_filter')
        objective = self._objective(inputs, rc_filter)
        capacitor_value = None
        capacitor_tolerance = None
        capacitor_series = None
        time_constant = None
        if rc_filter is not None:
            target_time_constant = rc_filter.interval('target_time_constant')
            capacitor_tolerance = rc_filter.quantity('capacitor_tolerance_pct') / 100
            if capacitor_tolerance >= 1:
                raise InputInvalid('capacitor tolerance must stay below 100%',
                                   field='rc_filter.capacitor_tolerance_pct')
            capacitor_series = rc_filter.get('capacitor_series')
            capacitor_window = rc_filter.get('capacitance')
            capacitors = series_values(
                capacitor_series,
                capacitor_window.lo if capacitor_window is not None else None,
                capacitor_window.hi if capacitor_window is not None else None,
                decades=_CAPACITOR_DECADES)
            if not capacitors:
                raise NoFeasibleSolution(
                    'no standard %s capacitor exists in the declared capacitance window'
                    % capacitor_series)
            selected, capacitor_value, time_constant = self._select_with_filter(
                allowed, capacitors, target_time_constant, objective)
        else:
            score = (lambda value: -value) if objective == 'max_resistance' else (lambda value: value)
            selected = choose(allowed, score)
            if selected is None:
                raise NoFeasibleSolution('no candidate satisfies the declared objective')

        r_nom = selected
        r_min_sel = r_nom * (1 - tolerance)
        r_max_sel = r_nom * (1 + tolerance)
        i_closed = supply.hi / (r_min_sel + rc_low)
        if variant == 'pull_up':
            level_open = supply.lo - leakage * r_max_sel
            open_margin = level_open - v_ih_worst
            level_closed = supply.hi * rc_high / (r_min_sel + rc_high)
            closed_margin = v_il_worst - level_closed
        else:
            level_open = leakage * r_max_sel
            open_margin = v_il_worst - level_open
            level_closed = supply.lo * r_min_sel / (r_min_sel + rc_high)
            closed_margin = level_closed - v_ih_worst
        power = supply.hi ** 2 * r_min_sel / ((r_min_sel + rc_low) ** 2)

        if i_closed > current_limit or open_margin < 0 or closed_margin < 0:
            raise NoFeasibleSolution(
                'the selected resistor violates a hard bound after tolerance: closed current %s A, '
                'open level %s V, closed level %s V'
                % (format_number(i_closed), format_number(level_open),
                   format_number(level_closed)))

        # ---- components ----------------------------------------------
        if variant == 'pull_up':
            resistor_pins = [{'name': '1', 'semantic': 'rail_side'},
                             {'name': '2', 'semantic': 'node_side'}]
            reserved_for_objective = (sorted(allowed, key=lambda value: -value)
                                      if objective == 'max_resistance'
                                      else sorted(allowed))
        else:
            resistor_pins = [{'name': '1', 'semantic': 'node_side'},
                             {'name': '2', 'semantic': 'ground_side'}]
            reserved_for_objective = (sorted(allowed, key=lambda value: -value)
                                      if objective == 'max_resistance'
                                      else sorted(allowed))
        resistor = draft.component(
            'pull_resistor', 'resistor',
            value=r_nom, tolerance_pct=tolerance_pct,
            series=inputs.get('series') if inputs.get('series') != 'explicit' else None,
            power_rating_w=power,
            voltage_rating_v=supply.hi,
            pins=resistor_pins,
            requirements={
                'closed_contact_current': quantity_json(i_closed, 'current'),
                'open_state_level': quantity_json(level_open, 'voltage'),
                'worst_case_power': quantity_json(power, 'power'),
            },
            candidates=[{'nominal': value} for value in reserved_for_objective[:5]],
            notes='Standard value selected deterministically by the declared objective; the '
                  'package power rating is a requirement, not a bound part.')
        switch = draft.component(
            'button_contact', 'switch', value=None,
            pins=[{'name': 'A', 'semantic': 'contact_terminal_a'},
                  {'name': 'B', 'semantic': 'contact_terminal_b'}],
            requirements={
                'current_limit_max': quantity_json(current_limit, 'current'),
                'contact_resistance': (contact_resistance.as_json('resistance')
                                       if resistance_declared else None),
                'bounce_time': (quantity_json(bounce_seconds, 'time')
                                if bounce_seconds is not None else None),
                'contact_model': 'abstract two-terminal contact',
                'pin_configuration': contact.get('pin_configuration'),
            },
            notes='Abstract two-terminal contact. No physical pin numbers are claimed; a four-pin '
                  'tact switch is only usable once its internal connection is verified.')
        capacitor = None
        if rc_filter is not None:
            capacitor = draft.component(
                'rc_filter', 'capacitor', value=capacitor_value,
                tolerance_pct=capacitor_tolerance * 100, series=capacitor_series,
                voltage_rating_v=supply.hi,
                pins=[{'name': '1', 'semantic': 'node_side'},
                      {'name': '2', 'semantic': 'ground_side'}],
                requirements={'nominal_time_constant': quantity_json(time_constant, 'time')},
                notes='Optional RC filter capacitor from the button node to ground.')

        # ---- nets, ports, endpoints ---------------------------------
        vcc = draft.net('VCC', role='power', scope='external', voltage_domain='supply')
        gnd = draft.net('GND', role='ground', scope='external')
        node = draft.net('BTN_NODE', role='signal', scope='external', voltage_domain='logic',
                         notes='Button node where the pull resistor, contact, optional filter '
                               'capacitor and OUT meet')

        if variant == 'pull_up':
            draft.connect(resistor['ref'], '1', vcc, 'rail_side')
            draft.connect(resistor['ref'], '2', node, 'node_side')
            draft.connect(switch['ref'], 'A', node, 'contact_terminal_a')
            draft.connect(switch['ref'], 'B', gnd, 'contact_terminal_b')
        else:
            draft.connect(resistor['ref'], '1', node, 'node_side')
            draft.connect(resistor['ref'], '2', gnd, 'ground_side')
            draft.connect(switch['ref'], 'A', vcc, 'contact_terminal_a')
            draft.connect(switch['ref'], 'B', node, 'contact_terminal_b')
        if capacitor is not None:
            draft.connect(capacitor['ref'], '1', node, 'node_side')
            draft.connect(capacitor['ref'], '2', gnd, 'ground_side')

        active = 'low' if variant == 'pull_up' else 'high'
        if variant == 'pull_up':
            high_level = Interval(level_open, supply.hi)
            low_level = Interval(Fraction(0), level_closed)
        else:
            high_level = Interval(level_closed, supply.hi)
            low_level = Interval(Fraction(0), level_open)
        switch_b_net = gnd if variant == 'pull_up' else node
        draft.port('VCC', 'input', 'power', net=vcc, voltage=supply,
                   description='Pull resistor rail; also the open-state level')
        draft.port('GND', 'passive', 'ground', net=gnd, description='Ground return')
        draft.port('SW_A', 'passive', 'switch', net=node if variant == 'pull_up' else vcc,
                   voltage=(Interval(Fraction(0), supply.hi) if variant == 'pull_up'
                            else supply),
                   current=Interval.point(i_closed),
                   description='Abstract contact terminal A; no physical pin number is claimed')
        draft.port('SW_B', 'passive', 'switch', net=switch_b_net,
                   voltage=(Interval.point(0) if variant == 'pull_up'
                            else Interval(Fraction(0), supply.hi)),
                   current=Interval.point(i_closed),
                   description='Abstract contact terminal B; no physical pin number is claimed')
        draft.port('OUT', 'output', 'digital', net=node,
                   voltage=Interval(Fraction(0), supply.hi),
                   current=Interval.point(leakage),
                   logic={
                       'active_level': active,
                       'v_ih_guaranteed': v_ih.as_json('voltage'),
                       'v_il_guaranteed': v_il.as_json('voltage'),
                       'high_level': high_level.as_json('voltage'),
                       'low_level': low_level.as_json('voltage'),
                   },
                   description='Digital output to the logic input; levels are derived from the '
                               'declared thresholds at worst-case resistor tolerance and leakage')

        # ---- calculations ------------------------------------------
        draft.calculation(
            'closed_contact_current',
            'Worst-case current through the closed contact',
            'I_closed = V_rail_max / (R_min + Rc_min);  R_min = R_selected*(1-tol)',
            inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                    'r_min': quantity_json(r_min_sel, 'resistance'),
                    'contact_resistance_min': quantity_json(rc_low, 'resistance'),
                    'supply_voltage': supply.as_json('voltage')},
            result={'current_max_a': to_json_number(i_closed)},
            unit='A',
            limit={'contact_current_limit': quantity_json(current_limit, 'current')},
            margin={'margin_a': quantity_json(current_limit - i_closed, 'current')},
            assumptions=['the closed contact current is bounded by the smallest resistor value'],
            not_modelled=['current sharing through the optional filter capacitor',
                          'contact resistance change during the make/break transient'])
        if variant == 'pull_up':
            draft.calculation(
                'open_state_level',
                'Switch-open HIGH level at worst-case leakage and tolerance',
                'V_open_min = V_rail_min - I_leak*R_max;  R_max = R_selected*(1+tol)',
                inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                        'r_max': quantity_json(r_max_sel, 'resistance'),
                        'supply_voltage': supply.as_json('voltage'),
                        'input_leakage': quantity_json(leakage, 'current')},
                result={'level_min_v': to_json_number(level_open)},
                unit='V',
                limit={'v_ih_worst': quantity_json(v_ih_worst, 'voltage')},
                margin={'margin_v': quantity_json(open_margin, 'voltage')},
                assumptions=['leakage flows into the node, which is the worst case for a HIGH '
                             'level'],
                not_modelled=['leakage current sign change over temperature',
                              'input capacitance holding the level'])
        else:
            draft.calculation(
                'open_state_level',
                'Switch-open LOW level at worst-case leakage and tolerance',
                'V_open_max = I_leak*R_max;  R_max = R_selected*(1+tol)',
                inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                        'r_max': quantity_json(r_max_sel, 'resistance'),
                        'supply_voltage': supply.as_json('voltage'),
                        'input_leakage': quantity_json(leakage, 'current')},
                result={'level_max_v': to_json_number(level_open)},
                unit='V',
                limit={'v_il_worst': quantity_json(v_il_worst, 'voltage')},
                margin={'margin_v': quantity_json(open_margin, 'voltage')},
                assumptions=['leakage flows out of the logic pin into the node, which is the '
                             'worst case for a LOW level'],
                not_modelled=['leakage current sign change over temperature',
                              'input capacitance holding the level'])
        if resistance_declared:
            if variant == 'pull_up':
                draft.calculation(
                    'closed_state_level',
                    'Switch-closed LOW level through the contact resistance',
                    'V_closed_max = V_rail_max*Rc_max / (R_min + Rc_max)',
                    inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                            'r_min': quantity_json(r_min_sel, 'resistance'),
                            'contact_resistance': contact_resistance.as_json('resistance'),
                            'supply_voltage': supply.as_json('voltage')},
                    result={'level_max_v': to_json_number(level_closed)},
                    unit='V',
                    limit={'v_il_worst': quantity_json(v_il_worst, 'voltage')},
                    margin={'margin_v': quantity_json(closed_margin, 'voltage')},
                    assumptions=['contact resistance at its maximum for the worst LOW level'],
                    not_modelled=['contact resistance nonlinearity at low current'])
            else:
                draft.calculation(
                    'closed_state_level',
                    'Switch-closed HIGH level through the contact resistance',
                    'V_closed_min = V_rail_min*R_min / (R_min + Rc_max)',
                    inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                            'r_min': quantity_json(r_min_sel, 'resistance'),
                            'contact_resistance': contact_resistance.as_json('resistance'),
                            'supply_voltage': supply.as_json('voltage')},
                    result={'level_min_v': to_json_number(level_closed)},
                    unit='V',
                    limit={'v_ih_worst': quantity_json(v_ih_worst, 'voltage')},
                    margin={'margin_v': quantity_json(closed_margin, 'voltage')},
                    assumptions=['contact resistance at its maximum for the worst HIGH level'],
                    not_modelled=['contact resistance nonlinearity at low current'])
        draft.calculation(
            'resistor_power',
            'Worst-case resistor dissipation',
            'P_max = V_rail_max^2 * R_min / (R_min + Rc_min)^2',
            inputs={'r_min': quantity_json(r_min_sel, 'resistance'),
                    'contact_resistance_min': quantity_json(rc_low, 'resistance'),
                    'supply_voltage': supply.as_json('voltage')},
            result={'power_w': to_json_number(power)},
            unit='W',
            limit=None,
            margin=None,
            assumptions=['the resistor is only loaded while the contact is closed'],
            not_modelled=['pulse power during contact bounce'])

        rise_window = fall_window = None
        if rc_filter is not None:
            c_low = capacitor_value * (1 - capacitor_tolerance)
            c_high = capacitor_value * (1 + capacitor_tolerance)
            tau_low = r_min_sel * c_low
            tau_high = r_max_sel * c_high
            target_time_constant = rc_filter.interval('target_time_constant')
            draft.calculation(
                'rc_time_constant',
                'Selected nominal RC product against the declared target range',
                'tau_nom = R_selected*C_selected;  tau_range = R*C over both tolerances',
                inputs={'selected_resistance': quantity_json(r_nom, 'resistance'),
                        'selected_capacitance': quantity_json(capacitor_value, 'capacitance'),
                        'resistor_tolerance_pct': quantity_json(tolerance_pct, 'percent'),
                        'capacitor_tolerance_pct': quantity_json(capacitor_tolerance * 100,
                                                                 'percent')},
                result={'nominal_s': to_json_number(time_constant),
                        'min_s': to_json_number(tau_low),
                        'max_s': to_json_number(tau_high)},
                unit='s',
                limit={'target_min': quantity_json(target_time_constant.lo, 'time'),
                       'target_max': quantity_json(target_time_constant.hi, 'time')},
                margin={'margin_below_s': to_json_number(time_constant - target_time_constant.lo),
                        'margin_above_s': to_json_number(target_time_constant.hi - time_constant)},
                assumptions=['the selected capacitor value is nominal and independent of the '
                             'resistor tolerance'],
                not_modelled=['capacitor DC bias/aging effects', 'load capacitance of the logic input'])
            rise_window = self._threshold_time_window(
                'rise', _charging_time, supply,
                (v_ih.lo, v_ih.hi), (tau_low, tau_high))
            fall_window = self._threshold_time_window(
                'fall', _discharging_time, supply,
                (v_il.lo, v_il.hi), (tau_low, tau_high))
            draft.calculation(
                'rc_threshold_times',
                'Threshold-crossing times of the RC filter',
                't_rise = -R*C*ln(1 - V_IH/V_rail) charging from 0 V;  '
                't_fall = -R*C*ln(V_IL/V_rail) decaying towards 0 V;  '
                'ln evaluated with Decimal at %d significant digits' % _LOG_PRECISION,
                inputs={'tau_range': {'min': to_json_number(tau_low),
                                      'max': to_json_number(tau_high), 'unit': 's'},
                        'supply_voltage': supply.as_json('voltage'),
                        'v_ih': v_ih.as_json('voltage'),
                        'v_il': v_il.as_json('voltage')},
                result={'rise_min_s': (to_json_number(rise_window[0])
                                       if rise_window is not None else None),
                        'rise_max_s': (to_json_number(rise_window[1])
                                       if rise_window is not None else None),
                        'fall_min_s': (to_json_number(fall_window[0])
                                       if fall_window is not None else None),
                        'fall_max_s': (to_json_number(fall_window[1])
                                       if fall_window is not None else None)},
                unit='s',
                limit=None,
                margin=None,
                assumptions=['first-order RC with one lumped capacitor',
                             'the charging transition starts at 0 V and the discharging '
                             'transition starts at the rail'],
                not_modelled=['discharge through the closed contact (faster than the pull '
                              'resistor), so the computed fall time is an upper bound',
                              'mechanical bounce waveform, contact wetting current',
                              'logic-input hysteresis and maximum edge-rate rating'])
            draft.calculation(
                'rc_is_not_debounce',
                'The RC product is not a debounce guarantee',
                't_debounce != R*C: a bouncing contact still produces several edges; the RC only '
                'shapes the node waveform',
                inputs={'nominal_time_constant': quantity_json(time_constant, 'time'),
                        'declared_bounce_time': (quantity_json(bounce_seconds, 'time')
                                                 if bounce_seconds is not None else None)},
                result={'declared_bounce_time_s': (to_json_number(bounce_seconds)
                                                   if bounce_seconds is not None else None)},
                unit='s',
                limit=None,
                margin=None,
                assumptions=[],
                not_modelled=['bounce waveform and its dependence on actuation speed',
                              'firmware sampling period and its own debounce filter'])

        # ---- preconditions -----------------------------------------
        self._write_preconditions(draft, inputs, variant, contact, bounce_seconds,
                                  resistance_declared, bounce_ms)
        if rc_filter is not None:
            self._write_filter_preconditions(draft, rise_window)

        # ---- evidence and assumptions ------------------------------
        draft.evidence('input_supply', 'user_declared',
                       'Rail range declared by the caller: %s..%s V.'
                       % (format_number(supply.lo), format_number(supply.hi)),
                       applies_to='VCC')
        draft.evidence('logic_thresholds', 'user_declared',
                       'Guaranteed logic thresholds declared by the caller (source=%s): '
                       'V_IH %s..%s V, V_IL %s..%s V.'
                       % (inputs.get('logic_source'), format_number(v_ih.lo),
                          format_number(v_ih.hi), format_number(v_il.lo),
                          format_number(v_il.hi)),
                       source={'document': 'caller declaration', 'provenance': inputs.get('logic_source')},
                       applies_to='OUT', verified=False)
        draft.evidence('input_leakage', 'user_declared',
                       'Logic-input leakage magnitude declared by the caller: %s A.'
                       % format_number(leakage),
                       source={'document': 'caller declaration'}, applies_to='OUT', verified=False)
        draft.evidence('contact_facts', 'user_declared',
                       'Contact facts declared by the caller: current limit %s A, model %s%s.'
                       % (format_number(current_limit), contact.get('pin_configuration'),
                          (', closed-contact resistance %s..%s ohm'
                           % (format_number(contact_resistance.lo),
                              format_number(contact_resistance.hi)))
                          if resistance_declared else ', contact resistance not declared'),
                       source={'document': 'caller declaration'}, applies_to='SW_A/SW_B',
                       verified=False)
        draft.evidence('standard_series', 'standard',
                       'Resistor values from IEC 60063 series %s; capacitor values from IEC 60063 '
                       'series %s.' % (inputs.get('series'), capacitor_series or 'n/a'),
                       source={'document': 'IEC 60063', 'section': 'preferred number series',
                               'url': 'https://webstore.iec.ch/publication/593'})
        draft.evidence('derivation_math', 'derivation',
                       'Contact current, open/closed levels and threshold-crossing times are '
                       'derived here with exact rational interval arithmetic (natural logarithm '
                       'via Decimal, no binary floats).')
        draft.assumption('Rail, thresholds, leakage and resistor tolerance extremes may occur '
                         'simultaneously (independent worst case).',
                         impact='conservative level and current bounds; a correlated worst case '
                                'would be narrower')
        draft.assumption('The level at OUT while the button is pressed follows the chosen variant '
                         '(pull_up -> low, pull_down -> high); polarity inversion is not modelled.',
                         impact='an inverting buffer or active-low MCU pin must be recorded by the '
                                'caller as a separate integration fact')

        return 'ready_abstract', [], notes

    # ------------------------------------------------------------------
    @staticmethod
    def _check_active_level(variant, active_level):
        if active_level is None:
            return
        expected = 'low' if variant == 'pull_up' else 'high'
        if active_level != expected:
            raise InputInvalid(
                'active_level=%r contradicts variant=%r: the %s topology presents %s at OUT while '
                'the button is pressed' % (active_level, variant, variant, expected),
                field='active_level')

    @staticmethod
    def _require_thresholds(inputs):
        missing = [name for name in ('v_ih', 'v_il') if inputs.get(name) is None]
        if missing:
            raise NeedsDeviceFacts(
                missing,
                'logic-input thresholds are required: without guaranteed V_IH/V_IL the open and '
                'closed levels cannot be proven and a GPIO input must never be assumed safe')

    @staticmethod
    def _require_contact(inputs):
        contact = inputs.get('contact')
        if contact is None:
            raise NeedsDeviceFacts(
                ['contact', 'contact.current_limit_max'],
                'button contact facts are required (at minimum the maximum current the closed '
                'contact may carry)')
        if contact.get('current_limit_max') is None:
            raise NeedsDeviceFacts(
                ['contact.current_limit_max'],
                'the closed-contact current rating is required; without it the resistor cannot be '
                'proven safe to use through the switch')
        if (contact.get('pin_configuration') == 'four_terminal_tact'
                and not contact.get('internal_connection_verified')):
            raise NeedsDeviceFacts(
                ['contact.internal_connection_verified'],
                'a four-pin tact switch is only modelled as a two-terminal contact when its '
                'internal connection is verified; no drop-in pin mapping is invented')
        return contact

    @staticmethod
    def _check_contact_resistance_floor(draft, variant, supply, v_ih_worst, v_il_worst, rc_high):
        """Reject cases where any finite contact resistance can never reach the threshold."""
        if variant == 'pull_up':
            if v_il_worst <= 0 and rc_high > 0:
                draft.calculation(
                    'closed_state_level',
                    'Switch-closed LOW level through the contact resistance',
                    'V_closed_max = V_rail_max*Rc_max / (R_min + Rc_max)',
                    inputs={'supply_voltage': supply.as_json('voltage'),
                            'v_il': quantity_json(v_il_worst, 'voltage'),
                            'contact_resistance_max': quantity_json(rc_high, 'resistance')},
                    result={'level_max_v': None},
                    unit='V',
                    limit={'v_il_worst': quantity_json(v_il_worst, 'voltage')},
                    margin={'margin_v': None},
                    assumptions=[],
                    not_modelled=['any divider with a nonzero contact resistance stays above 0 V'])
                raise NoFeasibleSolution(
                    'V_IL is 0 V: no divider with a nonzero contact resistance can pull the node '
                    'down to the guaranteed LOW threshold')
        else:
            if supply.lo <= v_ih_worst and rc_high > 0:
                draft.calculation(
                    'closed_state_level',
                    'Switch-closed HIGH level through the contact resistance',
                    'V_closed_min = V_rail_min*R_min / (R_min + Rc_max)',
                    inputs={'supply_voltage': supply.as_json('voltage'),
                            'v_ih': quantity_json(v_ih_worst, 'voltage'),
                            'contact_resistance_max': quantity_json(rc_high, 'resistance')},
                    result={'level_min_v': None},
                    unit='V',
                    limit={'v_ih_worst': quantity_json(v_ih_worst, 'voltage')},
                    margin={'margin_v': None},
                    assumptions=[],
                    not_modelled=['any divider with a nonzero contact resistance stays below the rail'])
                raise NoFeasibleSolution(
                    'V_IH equals the rail: no divider with a nonzero contact resistance can pull '
                    'the node up to the guaranteed HIGH threshold')

    def _hard_bounds(self, variant, supply, v_ih_worst, v_il_worst, leakage,
                     current_limit, rc_low, rc_high):
        """Return (lower bounds on R_min, upper bounds on R_max) with their statements."""
        lower = [('closed-contact current: V_rail_max/(R_min+Rc_min) <= I_limit',
                  supply.hi / current_limit - rc_low)]
        upper = []
        if variant == 'pull_up':
            if leakage > 0:
                upper.append(('open-state HIGH level: V_rail_min - I_leak*R_max >= V_IH',
                              (supply.lo - v_ih_worst) / leakage))
            if rc_high > 0:
                lower.append(('closed-state LOW level: V_rail_max*Rc_max/(R_min+Rc_max) <= V_IL',
                              rc_high * (supply.hi - v_il_worst) / v_il_worst))
        else:
            if rc_high > 0:
                lower.append(('closed-state HIGH level: V_rail_min*R_min/(R_min+Rc_max) >= V_IH',
                              v_ih_worst * rc_high / (supply.lo - v_ih_worst)))
            if leakage > 0:
                upper.append(('open-state LOW level: I_leak*R_max <= V_IL',
                              v_il_worst / leakage))
        return lower, upper

    @staticmethod
    def _window_formula(variant):
        if variant == 'pull_up':
            return ('R_min_required = max(0, V_rail_max/I_limit - Rc_min, '
                    'Rc_max*(V_rail_max - V_IL)/(V_IL)) / (1 - tol);  '
                    'R_max_allowed = (V_rail_min - V_IH)/(I_leak*(1 + tol))')
        return ('R_min_required = max(0, V_rail_max/I_limit - Rc_min, '
                'V_IH*Rc_max/(V_rail_min - V_IH)) / (1 - tol);  '
                'R_max_allowed = V_IL/(I_leak*(1 + tol))')

    def _candidates(self, inputs):
        series = inputs.get('series')
        window = inputs.get('value_range')
        low = window.lo if window is not None else None
        high = window.hi if window is not None else None
        if series == 'explicit':
            explicit = inputs.get('allowed_values')
            if not explicit:
                raise InputInvalid('series="explicit" requires allowed_values',
                                   field='allowed_values')
            candidates = set(explicit)
            if window is not None:
                candidates = {value for value in candidates if window.contains(value)}
        else:
            candidates = set(series_values(series, low, high))
        return sorted(candidates)

    @staticmethod
    def _objective(inputs, rc_filter):
        objective = inputs.get('objective')
        if objective == 'auto':
            return 'time_constant_error' if rc_filter is not None else 'max_resistance'
        if objective == 'time_constant_error' and rc_filter is None:
            raise InputInvalid('objective="time_constant_error" requires rc_filter',
                               field='objective')
        return objective

    @staticmethod
    def _select_with_filter(allowed, capacitors, target, objective):
        target_nominal = target.nominal
        pairs = []
        for resistor in allowed:
            for capacitor in capacitors:
                time_constant = resistor * capacitor
                if target.contains(time_constant):
                    pairs.append((resistor, capacitor, time_constant))
        if not pairs:
            raise NoFeasibleSolution(
                'no standard resistor/capacitor pair puts the RC product inside the declared '
                'target range %s..%s s'
                % (format_number(target.lo), format_number(target.hi)),
                bounds={'tau_min_required': to_json_number(target.lo),
                        'tau_max_required': to_json_number(target.hi)})

        def key(pair):
            resistor, _capacitor, time_constant = pair
            error = abs(time_constant - target_nominal) / target_nominal
            if objective == 'max_resistance':
                return (-resistor, error)
            if objective == 'min_resistance':
                return (resistor, error)
            return (error,)

        pairs.sort(key=lambda pair: (key(pair), pair[0], pair[1]))
        selected_resistor, selected_capacitor, time_constant = pairs[0]
        return selected_resistor, selected_capacitor, time_constant

    @staticmethod
    def _threshold_time_window(direction, time_function, supply, threshold_range, tau_range):
        """Evaluate a crossing time at the declared interval corners (monotone in each)."""
        thresholds = [threshold_range[0], threshold_range[1]]
        if direction == 'fall' and thresholds[0] <= 0:
            return None
        values = []
        for tau in tau_range:
            for rail in (supply.lo, supply.hi):
                for threshold in thresholds:
                    if threshold <= 0 or threshold >= rail:
                        return None
                    values.append(time_function(tau, threshold, rail))
        return (min(values), max(values))

    @staticmethod
    def _write_preconditions(draft, inputs, variant, contact, bounce_seconds,
                             resistance_declared, bounce_ms):
        draft.constraint(
            'mechanical_bounce_not_removed',
            'Mechanical bounce is not removed by an RC filter or by the resistor; the contact '
            'still chatters for its bounce duration and the logic input sees those edges.'
            + ((' Declared bounce time: %s ms.' % format_number(Fraction(bounce_ms)))
               if bounce_ms is not None else ''),
            kind='verification', applies_to='SW_A/SW_B')
        draft.constraint(
            'schmitt_trigger_for_slow_edges',
            'A button edge shaped by a pull resistor (and an RC filter) is slow; the logic input '
            'must have a Schmitt-trigger characteristic with a declared hysteresis or be replaced '
            'by one, otherwise the input can oscillate between V_IL and V_IH.',
            kind='verification', applies_to='OUT')
        draft.constraint(
            'software_debounce_separate',
            'Firmware debounce is a separate precondition: the firmware must ignore edges for at '
            'least the contact bounce duration after the first transition. The module does not '
            'size or verify it.',
            kind='integration', applies_to='OUT')
        draft.constraint(
            'logic_facts_provenance',
            'V_IH, V_IL and input leakage must be verified against the exact MCU/SoC datasheet '
            '(declared provenance: %s); they are user-declared facts, not datasheet-verified here.'
            % inputs.get('logic_source'),
            kind='verification', applies_to='OUT')
        if not resistance_declared:
            draft.constraint(
                'contact_resistance_unverified',
                'The closed-contact resistance was not declared; the switch-closed level was '
                'computed with an ideal contact (0 ohm for pull-up, rail for pull-down).',
                kind='verification', applies_to='SW_A/SW_B')
        draft.constraint(
            'abstract_contact_only',
            'The contact is an abstract two-terminal model. No physical pin number, footprint or '
            '4-pin tact-switch internal connection is claimed; the caller must verify the mapping.',
            kind='verification', applies_to='SW_A/SW_B')
        if bounce_ms is None:
            draft.unknown('bounce_duration',
                          'the contact bounce duration was not declared',
                          impact='the firmware debounce interval cannot be sized from this result',
                          how_to_resolve='declare contact.bounce_ms or measure the switch bounce')
        draft.unknown('logic_input_dynamic_behaviour',
                      'the logic input hysteresis and maximum edge-rate rating were not declared',
                      impact='a slow RC edge can violate the input edge-rate requirement or '
                             'oscillate without a Schmitt trigger',
                      how_to_resolve='declare the MCU input hysteresis/edge-rate limit or add a '
                                     'Schmitt-trigger buffer')
        if not resistance_declared:
            draft.unknown('contact_resistance',
                          'the closed-contact resistance was not declared',
                          impact='the switch-closed level is computed with an ideal contact; a '
                                 'worn or high-resistance contact could violate the threshold',
                          how_to_resolve='declare contact.contact_resistance from the datasheet '
                                         'or measure it (including end-of-life)')
        if bounce_seconds is not None and bounce_seconds > 0:
            draft.assumption('The declared bounce time is a maximum over the life of the switch.',
                             impact='a longer bounce needs a longer firmware debounce interval')

    @staticmethod
    def _write_filter_preconditions(draft, rise_window):
        if rise_window is None:
            draft.constraint(
                'rc_threshold_time_unbounded',
                'The falling threshold cannot be reached in finite time for the declared V_IL=0 V '
                'corner; no threshold-crossing time is claimed for it.',
                kind='verification', applies_to='OUT')
        draft.constraint(
            'rc_filter_bandwidth',
            'The RC filter also limits the maximum usable toggle rate: the node needs the '
            'computed threshold-crossing time for each edge, so the firmware sample period must '
            'be longer than that.',
            kind='integration', applies_to='OUT')
        draft.constraint(
            'capacitor_voltage_rating',
            'The filter capacitor must be rated for the pull-up rail voltage and its tolerance/'
            'dielectric drift must be compatible with the declared RC target.',
            kind='hard', applies_to='C1')
