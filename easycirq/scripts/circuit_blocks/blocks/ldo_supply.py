"""F6 — low-dropout (LDO) linear supply with exact device facts.

A fixed-output LDO is only as trustworthy as the part data behind it, so this
module refuses to invent a generic regulator.  It consumes either a bundled
verified fact file (``device_fact_id``, category ``ldo``) or caller-declared
facts (``device_facts``) and makes every hard decision from those numbers:

* input-voltage envelope against the device recommended range;
* fixed-output variant match (no feedback-divider synthesis for an adjustable
  variant, and a mismatch is ``unsupported``, not "we will design the divider");
* worst-case headroom ``VIN_min - VOUT_max >= Vdropout(IOUT_max)`` using the
  documented dropout row at or above the actual load current (with the
  temperature condition that covers the declared ambient range preferred);
* dissipation ``P = (VIN_max - VOUT_min) * IOUT_max + VIN_max * Iq`` and a
  junction-temperature *estimate* ``Tj = Ta_max + P * Rtheta_JA`` that is only
  produced under the board condition stated by the datasheet fact.  It is
  labelled an estimate, never a board-temperature guarantee;
* capacitor requirements (minimum input/output capacitance, declared ESR
  window, voltage rating with a caller-declared derating), quoting the
  datasheet's own condition text instead of inventing a dielectric;
* minimum-load / bleed-path handling: a bleed resistor is only added when the
  caller explicitly declares one, otherwise the unmet minimum load becomes a
  hard constraint and an ``unsupported`` result;
* enable-pin and reverse-current conditions as explicit constraints.

Out-of-range operation (below dropout, over-current, over-temperature) is
always an explicit constraint, never silently treated as covered.
"""
from __future__ import annotations

import re
from fractions import Fraction

from ..devices import (evidence_for, fact_condition, fact_number,
                       fact_value, load_fact, missing_keys, user_declared_facts)
from ..errors import InputInvalid, NeedsDeviceFacts, NoFeasibleSolution, Unsupported
from ..eseries import values as series_values
from ..numeric import format_number, parse_number, to_json_number
from ..ranges import Interval
from ..units import canonical_unit, quantity_json
from .base import Block

#: Facts without which the electrical maths cannot run at all.
_REQUIRED_FACTS = (
    'vin_min_v', 'vin_max_v', 'vout_nom_v', 'vout_tol_pct', 'iout_max_a',
    'iq_a', 'dropout_v', 'cin_min_f', 'cout_min_f', 'min_load_a', 'tj_max_c',
)

#: Name used when dropout facts exist but their load condition cannot be found.
_DROPOUT_LOAD_KEY = 'dropout_v.load_a'

#: User-declared facts without a real condition keep this placeholder.
_DECLARED_PLACEHOLDER = 'declared by the caller'

_TEMP_RANGE_RE = re.compile(
    r'(-?\d+(?:\.\d+)?)\s*(?:°\s*C|\bC\b)\s*(?:to|through|\.\.\.)\s*'
    r'\+?(-?\d+(?:\.\d+)?)\s*(?:°\s*C|\bC\b)', re.IGNORECASE)
_LOAD_RE = re.compile(
    r'(?:(?:I\s*OUT|IOUT|I_OUT|output\s+current|load(?:\s+current)?)\s*'
    r'(?:=|:)?\s*)?(-?\d+(?:\.\d+)?)\s*([numµμp])?\s*A(?![A-Za-z])',
    re.IGNORECASE)
_PREFIX = {'n': Fraction(1, 10 ** 9), 'u': Fraction(1, 10 ** 6),
           'µ': Fraction(1, 10 ** 6), 'μ': Fraction(1, 10 ** 6),
           'm': Fraction(1, 1000), 'p': Fraction(1, 10 ** 12)}


def _quantity_record(family, extra=None):
    """One caller-declared fact record: ``{value, condition?, source?, ...}``."""
    fields = {
        'value': {'kind': 'quantity', 'family': family, 'required': True},
        'condition': {'kind': 'string'},
        'source': {'kind': 'string'},
        'applies_to': {'kind': 'string'},
    }
    if extra:
        fields.update(extra)
    return {'kind': 'object', 'fields': fields}


def _number_record(doc):
    return {'kind': 'object', 'fields': {
        'value': {'kind': 'number', 'required': True, 'doc': doc},
        'condition': {'kind': 'string'},
        'source': {'kind': 'string'},
        'applies_to': {'kind': 'string'},
    }}


def _bool_record(doc):
    return {'kind': 'object', 'fields': {
        'value': {'kind': 'bool', 'required': True, 'doc': doc},
        'condition': {'kind': 'string'},
        'source': {'kind': 'string'},
        'applies_to': {'kind': 'string'},
    }}


_DROPOUT_EXTRA = {'load_a': {'kind': 'quantity', 'family': 'current',
                             'doc': 'Load current at which this maximum dropout applies (A).'}}

#: Known caller-declared fact keys; the extra keys are documented optional
#: facts consumed only when present.
_DEVICE_FACT_SCHEMA = {
    'vin_min_v': _quantity_record('voltage'),
    'vin_max_v': _quantity_record('voltage'),
    'vin_abs_max_v': _quantity_record('voltage'),
    'vout_nom_v': _quantity_record('voltage'),
    'vout_tol_pct': _quantity_record('percent'),
    'iout_max_a': _quantity_record('current'),
    'iq_a': _quantity_record('current'),
    'dropout_v': _quantity_record('voltage', extra=dict(_DROPOUT_EXTRA)),
    'dropout_max_over_temp_v': _quantity_record('voltage', extra=dict(_DROPOUT_EXTRA)),
    'cin_min_f': _quantity_record('capacitance'),
    'cout_min_f': _quantity_record('capacitance'),
    'cout_max_f': _quantity_record('capacitance'),
    'cout_stability_min_f': _quantity_record('capacitance'),
    'esr_min_ohm': _quantity_record('resistance'),
    'esr_max_ohm': _quantity_record('resistance'),
    'min_load_a': _quantity_record('current'),
    'theta_ja_c_per_w': _number_record('Junction-to-ambient thermal resistance (C/W).'),
    'tj_max_c': _quantity_record('temperature'),
    'enable_pin': _bool_record('True when the device has an enable pin.'),
    'enable_vih_min_v': _quantity_record('voltage'),
    'enable_vil_max_v': _quantity_record('voltage'),
    'reverse_current_allowed': _bool_record('True when reverse current is permitted.'),
    'vout_abs_max_offset_v': _quantity_record('voltage'),
    'current_limit_min_a': _quantity_record('current'),
}


class LdoSupply(Block):
    MODULE_TYPE = 'ldo_supply'
    TEMPLATE_VERSION = '1.0.0'
    TITLE = 'LDO linear supply with exact device facts'
    SUMMARY = ('Checks a fixed-output LDO against exact device facts: input envelope, '
               'dropout headroom at the actual load, dissipation and a board-condition '
               'junction-temperature estimate, capacitor/ESR requirements, minimum-load '
               'and bleed handling, enable and reverse-current conditions.')
    TOPOLOGY = 'fixed-output linear regulator: VIN -> LDO -> VOUT with input/output decoupling'
    APPLICABILITY = (
        'single fixed-output LDO with the requested output equal to the device nominal output',
        'DC / steady-state operating point; dissipation is averaged over the load range',
        'ambient range and load range fully declared by the caller',
        'exact device facts from a verified fact file or declared by the caller',
    )
    NON_APPLICABILITY = (
        'adjustable-output LDO variants (feedback-divider synthesis is not modelled)',
        'switching regulators, charge pumps, multi-phase or parallel regulators',
        'load-step / transient response, PSRR, noise or start-up sequencing analysis',
        'board-level thermal simulation; Rtheta_JA estimate is not a board temperature guarantee',
        'operation outside the device recommended range (reported, not designed around)',
    )
    REQUIRED_DEVICE_FACTS = (
        'input voltage range (vin_min_v, vin_max_v)',
        'fixed nominal output and its accuracy (vout_nom_v, vout_tol_pct)',
        'rated output current (iout_max_a) and quiescent current (iq_a)',
        'maximum dropout at a stated load current (dropout_v + load condition)',
        'minimum input/output capacitance (cin_min_f, cout_min_f) and ESR window when stated',
        'minimum load when the part requires one (min_load_a)',
        'thermal model: theta_ja_c_per_w with its board condition and tj_max_c',
        'enable pin and reverse-current permission when the part defines them',
    )
    SOURCES = (
        {'document': 'TI TLV755P datasheet, SBVS320D (TLV75533PDBVR example facts)',
         'why': 'vin/vout/iout limits, dropout rows, Iq, capacitor recommendations, Rtheta_JA, EN and reverse current'},
        {'document': 'easycirq/scripts/circuit_blocks/devices/SCHEMA.md',
         'why': 'verified device-fact file format and required ldo keys'},
        {'document': 'IEC 60063 preferred number series',
         'why': 'standard values for an optional minimum-load bleed resistor'},
    )
    INPUT_SCHEMA = {
        'input_voltage': {
            'kind': 'range', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'VIN operating range at the regulator input (V).'},
        'output_voltage': {
            'kind': 'quantity', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'Requested output voltage (V); must equal the device fixed output exactly.'},
        'load_current': {
            'kind': 'range', 'family': 'current', 'required': True, 'nonnegative': True,
            'doc': 'Output load current range (A); both bounds must be declared.'},
        'ambient_temperature': {
            'kind': 'range', 'family': 'temperature', 'required': True,
            'doc': 'Ambient/operating temperature range around the package (degC).'},
        'device_fact_id': {
            'kind': 'string',
            'doc': 'Bundled verified LDO fact file id (for example "ldo_tlv75533p").'},
        'device_facts': {
            'kind': 'object', 'fields': dict(_DEVICE_FACT_SCHEMA),
            'doc': 'Caller-declared LDO facts; every entry is a fact record '
                   '{value, condition?, source?, applies_to?} mirroring the verified-file schema.'},
        'device_mpn': {
            'kind': 'string',
            'doc': 'MPN that caller-declared facts describe (declared facts are never "verified").'},
        'device_source_note': {
            'kind': 'string', 'doc': 'Source note attached to caller-declared facts.'},
        'bleed_resistor': {
            'kind': 'bool', 'default': False,
            'doc': 'Declare a minimum-load bleed resistor when the load range goes below min_load_a.'},
        'bleed_series': {
            'kind': 'enum', 'values': ['E6', 'E12', 'E24', 'E48', 'E96'],
            'default': 'E24', 'doc': 'Standard series for the bleed resistor (ohm).'},
        'bleed_tolerance_pct': {
            'kind': 'quantity', 'family': 'percent', 'default': 1, 'nonnegative': True,
            'doc': 'Bleed resistor tolerance used for the minimum-load guarantee (%).'},
        'bleed_power_derating_pct': {
            'kind': 'quantity', 'family': 'percent', 'default': 50, 'nonnegative': True,
            'doc': 'Required derating of the bleed resistor rating at worst case (%).'},
        'bleed_resistance_range': {
            'kind': 'range', 'family': 'resistance', 'positive': True,
            'doc': 'Optional allowed bleed-resistance window from BOM/package reality (ohm).'},
        'capacitor_derating_pct': {
            'kind': 'quantity', 'family': 'percent', 'default': 50, 'nonnegative': True,
            'doc': 'Maximum applied voltage as a percentage of the capacitor voltage rating (%).'},
        'notes': {'kind': 'string', 'doc': 'Free-form note copied into the result.'},
    }
    EXAMPLE_INPUT = {
        'input_voltage': {'min': 4.5, 'max': 5.5},
        'output_voltage': '3.3V',
        'load_current': {'min': '10mA', 'max': '50mA'},
        'ambient_temperature': {'min': -40, 'max': 85},
        'device_fact_id': 'ldo_tlv75533p',
    }

    # ------------------------------------------------------------------
    def compute(self, draft, inputs):
        facts, origin = _resolve_facts(inputs)
        missing = missing_keys(facts, _REQUIRED_FACTS)
        if missing:
            raise NeedsDeviceFacts(
                missing,
                'the LDO circuit maths needs these device facts; none is guessed: %s'
                % ', '.join(missing))

        vin = inputs.interval('input_voltage')
        vout_requested = inputs.quantity('output_voltage')
        load = inputs.interval('load_current')
        ambient = inputs.interval('ambient_temperature')
        notes = inputs.get('notes')

        vin_min_v = fact_number(facts, 'vin_min_v')
        vin_max_v = fact_number(facts, 'vin_max_v')
        vout_nom_v = fact_number(facts, 'vout_nom_v')
        vout_tol_pct = fact_number(facts, 'vout_tol_pct')
        iout_max_a = fact_number(facts, 'iout_max_a')
        iq_a = fact_number(facts, 'iq_a')
        cin_min_f = fact_number(facts, 'cin_min_f')
        cout_min_f = fact_number(facts, 'cout_min_f')
        min_load_a = fact_number(facts, 'min_load_a')
        tj_max_c = fact_number(facts, 'tj_max_c')
        _sanity(facts, vin_min_v, vin_max_v, vout_nom_v, vout_tol_pct,
                iout_max_a, iq_a, cin_min_f, cout_min_f, min_load_a, tj_max_c)

        verified = bool(facts.get('verified'))
        mpn = facts.get('mpn')
        manufacturer = facts.get('manufacturer')
        fact_id = facts.get('fact_id') or 'user_declared'

        tolerance = vout_tol_pct / 100
        vout_min = vout_nom_v * (1 - tolerance)
        vout_max = vout_nom_v * (1 + tolerance)
        derating_pct = inputs.quantity('capacitor_derating_pct')
        if derating_pct <= 0 or derating_pct > 100:
            raise InputInvalid('capacitor_derating_pct must be in (0, 100]',
                               field='capacitor_derating_pct')
        derating = derating_pct / 100

        # ---- optional minimum-load bleed (decided before the current budget) --
        bleed = self._resolve_bleed(draft, inputs, vout_min, vout_max, load, min_load_a)
        total_iout_max = load.hi + (bleed['i_max'] if bleed is not None else Fraction(0))

        # ---- device envelope ---------------------------------------------------
        self._check_envelope(draft, facts, vin, vout_requested, vout_nom_v, vin_min_v,
                             vin_max_v, iout_max_a, total_iout_max, load, min_load_a)

        # ---- components, nets, ports, endpoints --------------------------------
        has_enable, has_enable_known = _enable_state(facts)
        reverse_allowed, reverse_known = _reverse_state(facts)
        components = self._write_topology(
            draft, inputs, facts, vin, load, total_iout_max, iq_a, vout_min,
            vout_max, cin_min_f, cout_min_f, bleed, has_enable,
            tolerance, vin_min_v, vin_max_v, mpn, manufacturer, fact_id, verified)
        regulator = components['regulator']

        # ---- electrical calculations and constraints ---------------------------
        self._headroom(draft, facts, ambient, vin, vout_max, total_iout_max,
                       regulator['ref'])
        iq = iq_a
        power = (vin.hi - vout_min) * total_iout_max + vin.hi * iq
        draft.calculation(
            'dissipation',
            'Worst-case regulator dissipation',
            'P = (VIN_max - VOUT_min) * IOUT_max + VIN_max * Iq',
            inputs={
                'vin_max': quantity_json(vin.hi, 'voltage'),
                'vout_min': quantity_json(vout_min, 'voltage'),
                'iout_max_total': quantity_json(total_iout_max, 'current'),
                'iq_a': quantity_json(iq, 'current'),
                'bleed_current_max': (quantity_json(bleed['i_max'], 'current')
                                      if bleed is not None else None),
            },
            result={'power_w': to_json_number(power)},
            unit='W',
            method='exact rational arithmetic on the declared worst-case extremes',
            assumptions=['worst-case extremes of input voltage, output tolerance and load are '
                         'independent and may coincide',
                         'Iq is taken as the declared iq_a fact'],
            not_modelled=['quiescent current variation over temperature (a documented maximum '
                          'ground current, if any, should be supplied as iq_a for a hotter estimate)',
                          'switching or transient dissipation; this is a DC operating point'])
        draft.constraint(
            'dissipation_limit',
            'The regulator must dissipate at most %s W in this application; the declared '
            'thermal limits are checked from this number.' % format_number(power),
            kind='hard', applies_to=regulator['ref'])

        self._capacitors(draft, facts, vin.hi, vout_max, vout_min, cin_min_f,
                         cout_min_f, derating_pct, derating)
        self._enable(draft, facts, has_enable, has_enable_known, vin_max_v,
                     regulator['ref'])
        self._reverse_current(draft, facts, reverse_allowed, reverse_known,
                              regulator['ref'])

        # ---- thermal estimate (electrical checks above stay reported when it is
        #      impossible to make the thermal claim) -----------------------------
        theta_ja = _optional_number(facts, 'theta_ja_c_per_w')
        board_condition = _board_condition(facts)
        thermal = self._thermal(draft, theta_ja, board_condition, ambient, power,
                                tj_max_c, regulator['ref'])

        # ---- evidence, assumptions, unknowns -----------------------------------
        self._evidence(draft, facts, origin, verified, mpn, manufacturer, fact_id,
                       inputs, vin, load, ambient, vout_min, vout_max, total_iout_max)
        self._records(draft, facts, bleed)

        if thermal is None:
            missing_keys_list = []
            if theta_ja is None:
                missing_keys_list.append('theta_ja_c_per_w')
            if board_condition is None:
                missing_keys_list.append('theta_ja_c_per_w board condition')
            draft.constraint(
                'thermal_estimate_unavailable',
                'The junction-temperature estimate cannot be made: the thermal fact or its '
                'board condition is missing. The electrical checks above are still reported, '
                'but no thermal claim is made.',
                kind='verification', applies_to=regulator['ref'])
            raise NeedsDeviceFacts(
                missing_keys_list,
                'the thermal claim needs %s; the electrical checks are reported without it'
                % ', '.join(missing_keys_list))

        tj_est, tj_margin, thermal_limit = thermal
        if tj_est > thermal_limit:
            raise Unsupported(
                'estimated junction temperature %s degC exceeds the device maximum %s degC '
                'at Ta_max=%s degC under the datasheet board condition %r'
                % (format_number(tj_est), format_number(thermal_limit),
                   format_number(ambient.hi), board_condition),
                reasons=['over-temperature: Tj_est %s degC > tj_max_c %s degC (Ta_max %s degC, '
                         'board condition: %s)'
                         % (format_number(tj_est), format_number(thermal_limit),
                            format_number(ambient.hi), board_condition)])

        if tj_margin < tj_max_c / 10:
            draft.constraint(
                'thin_thermal_margin',
                'Estimated junction temperature is within %s degC of tj_max_c; re-check '
                'the real board thermal path (Rtheta_JA is a JEDEC board characterisation, '
                'not the user board).' % format_number(tj_margin),
                kind='advisory', applies_to=regulator['ref'])

        return 'ready_abstract', [], notes

    # ------------------------------------------------------------------
    # device envelope
    # ------------------------------------------------------------------
    def _check_envelope(self, draft, facts, vin, vout_requested, vout_nom_v, vin_min_v,
                        vin_max_v, iout_max_a, total_iout_max, load, min_load_a):
        envelope_margin = min(vin.lo - vin_min_v, vin_max_v - vin.hi)
        vin_abs_max = _optional_number(facts, 'vin_abs_max_v')
        draft.calculation(
            'input_voltage_envelope',
            'Input voltage range inside the device recommended range',
            'VIN_min >= vin_min_v AND VIN_max <= vin_max_v',
            inputs={'input_voltage': vin.as_json('voltage'),
                    'vin_min_v': quantity_json(vin_min_v, 'voltage'),
                    'vin_max_v': quantity_json(vin_max_v, 'voltage'),
                    'vin_abs_max_v': (quantity_json(vin_abs_max, 'voltage')
                                      if vin_abs_max is not None else None)},
            result={'pass': envelope_margin >= 0,
                    'margin_v': to_json_number(envelope_margin)},
            unit='V',
            limit={'vin_min_v': quantity_json(vin_min_v, 'voltage'),
                   'vin_max_v': quantity_json(vin_max_v, 'voltage')},
            margin={'min_side_v': to_json_number(vin.lo - vin_min_v),
                    'max_side_v': to_json_number(vin_max_v - vin.hi)},
            assumptions=['the declared input range covers every operating point, including '
                         'start-up and load steps within the declared load range'],
            not_modelled=['absolute-maximum transient excursions above vin_max_v%s'
                          % ('' if vin_abs_max is None else
                             ' (vin_abs_max_v = %s V is an absolute rating, not an operating '
                             'point)' % format_number(vin_abs_max))])
        draft.constraint(
            'input_voltage_envelope',
            'VIN must stay within the device recommended range %s..%s V at the declared '
            'ambient range.%s'
            % (format_number(vin_min_v), format_number(vin_max_v),
               '' if vin_abs_max is None else
               ' Absolute maximum input is %s V; exceeding it is not covered.'
               % format_number(vin_abs_max)),
            kind='hard', applies_to='VIN')
        if envelope_margin < 0:
            raise Unsupported(
                'declared input range %s..%s V is outside the device recommended range '
                '%s..%s V'
                % (format_number(vin.lo), format_number(vin.hi),
                   format_number(vin_min_v), format_number(vin_max_v)),
                reasons=['input voltage envelope violated: VIN %s..%s V vs device %s..%s V'
                         % (format_number(vin.lo), format_number(vin.hi),
                            format_number(vin_min_v), format_number(vin_max_v))])

        variant_margin = 0 if vout_requested == vout_nom_v else -1
        draft.calculation(
            'output_variant_match',
            'Requested output equals the fixed device output',
            'VOUT_requested == vout_nom_v (fixed-output variant; no feedback divider is synthesised)',
            inputs={'output_voltage': quantity_json(vout_requested, 'voltage'),
                    'vout_nom_v': quantity_json(vout_nom_v, 'voltage')},
            result={'pass': vout_requested == vout_nom_v,
                    'difference_v': to_json_number(vout_requested - vout_nom_v)},
            unit='V',
            limit={'vout_nom_v': quantity_json(vout_nom_v, 'voltage')},
            margin={'difference_v': to_json_number(vout_requested - vout_nom_v)},
            assumptions=['the supplied facts describe a fixed-output variant; the fact file '
                         'names the exact fixed output'],
            not_modelled=['adjustable-output variants and external feedback networks'])
        draft.constraint(
            'output_fixed_variant',
            'The load must be supplied by the fixed %s V output variant; do not add an '
            'external feedback divider to set another voltage.'
            % format_number(vout_nom_v),
            kind='hard', applies_to='VOUT')
        if vout_requested != vout_nom_v:
            raise Unsupported(
                'requested output %s V does not match the fixed device output %s V; an '
                'adjustable-output variant is not described by the supplied facts'
                % (format_number(vout_requested), format_number(vout_nom_v)),
                reasons=['fixed-variant mismatch: requested %s V, device nominal %s V'
                         % (format_number(vout_requested), format_number(vout_nom_v))])

        current_margin = iout_max_a - total_iout_max
        current_limit = _optional_number(facts, 'current_limit_min_a')
        draft.calculation(
            'load_current_envelope',
            'Load current range inside the device rated output current',
            'IOUT_max_total = load_current.max (+ bleed current when declared); '
            'IOUT_max_total <= iout_max_a',
            inputs={'load_current': load.as_json('current'),
                    'iout_max_total': quantity_json(total_iout_max, 'current'),
                    'iout_max_a': quantity_json(iout_max_a, 'current'),
                    'current_limit_min_a': (quantity_json(current_limit, 'current')
                                            if current_limit is not None else None)},
            result={'pass': current_margin >= 0,
                    'margin_a': to_json_number(current_margin)},
            unit='A',
            limit={'iout_max_a': quantity_json(iout_max_a, 'current')},
            margin={'margin_a': to_json_number(current_margin)},
            assumptions=['the load current is the regulator output current; a declared bleed '
                         'resistor current is added to the output budget'],
            not_modelled=['inrush/start-up current into the output capacitance'])
        draft.constraint(
            'load_current_envelope',
            'Total output current (load plus any bleed path) must not exceed the device '
            'rated output current %s A.%s'
            % (format_number(iout_max_a),
               '' if current_limit is None else
               ' Above the rated current the device enters current limit (documented minimum '
               'current limit %s A); that is out-of-regulation operation, not a design point.'
               % format_number(current_limit)),
            kind='hard', applies_to='VOUT')
        if current_margin < 0:
            raise Unsupported(
                'load current range needs up to %s A (including bleed) but the device is '
                'rated for %s A'
                % (format_number(total_iout_max), format_number(iout_max_a)),
                reasons=['over-current: IOUT_max_total %s A > iout_max_a %s A'
                         % (format_number(total_iout_max), format_number(iout_max_a))])

        if min_load_a > 0:
            self._minimum_load_constraint(draft, load, min_load_a)

    def _minimum_load_constraint(self, draft, load, min_load_a):
        if load.lo >= min_load_a:
            draft.constraint(
                'minimum_load_path',
                'The declared minimum load %s A is already at or above the device '
                'minimum load %s A; the application must keep the load connected.'
                % (format_number(load.lo), format_number(min_load_a)),
                kind='hard', applies_to='VOUT')

    # ------------------------------------------------------------------
    # headroom and dropout rows
    # ------------------------------------------------------------------
    def _headroom(self, draft, facts, ambient, vin, vout_max, total_iout_max,
                  regulator_ref):
        rows = _dropout_rows(facts)
        if not rows:
            if 'dropout_v' in (facts.get('facts') or {}):
                raise NeedsDeviceFacts(
                    [_DROPOUT_LOAD_KEY],
                    'the dropout fact does not state the load current at which it applies; '
                    'declare device_facts.dropout_v.load_a (or state it in the condition text)')
            raise NeedsDeviceFacts(
                ['dropout_v'],
                'no numeric dropout fact was found; a dropout row at or above the actual '
                'load current is required for the headroom check')
        selected, info = _choose_dropout(rows, total_iout_max, ambient)
        if selected is None:
            raise NeedsDeviceFacts(
                [_DROPOUT_LOAD_KEY],
                'the dropout fact does not state the load current at which it applies; '
                'declare device_facts.dropout_v.load_a (or state it in the condition text)')
        headroom = vin.lo - vout_max
        margin = headroom - selected['value']
        not_modelled = [
            'dropout is a maximum at one documented load current; the actual dropout at '
            'lower currents is smaller but not separately documented here',
            'dropout temperature dependence is only represented by choosing the documented '
            'condition that covers the declared ambient range',
        ]
        if info['single_load_condition']:
            not_modelled.append(
                'only one dropout load condition (%s A) is documented; it is applied '
                'unchanged across the requested load range (conservative extrapolation)'
                % format_number(selected['load_a']))
        if info['extrapolated']:
            not_modelled.append(
                'the requested load current %s A exceeds every documented dropout load '
                'condition; the row at the highest documented load was used (conservative '
                'extrapolation)' % format_number(total_iout_max))
        assumptions = [
            'the selected dropout row is a maximum value at the stated load and temperature '
            'condition, not a typical value',
        ]
        if info['mode'] == 'documented':
            assumptions.append('the selected row documents a temperature condition that '
                               'covers the declared ambient range')
        elif info['mode'] == 'undeclared':
            assumptions.append('the supplied dropout fact does not state a temperature '
                               'condition; its declared maximum is applied as-is')
        else:
            assumptions.append('no documented dropout condition covers the declared ambient '
                               'range; the largest documented maximum was used')
        draft.calculation(
            'headroom',
            'Worst-case dropout headroom at the actual load current',
            'headroom = VIN_min - VOUT_max;  margin = headroom - Vdropout(IOUT_max_total)',
            inputs={
                'vin_min': quantity_json(vin.lo, 'voltage'),
                'vout_max': quantity_json(vout_max, 'voltage'),
                'iout_max_total': quantity_json(total_iout_max, 'current'),
                'dropout_fact': selected['key'],
                'dropout_v': quantity_json(selected['value'], 'voltage'),
                'dropout_load_a': quantity_json(selected['load_a'], 'current'),
                'dropout_condition': selected['condition'],
                'ambient_temperature': ambient.as_json('temperature'),
                'selection': info['mode'],
            },
            result={'headroom_v': to_json_number(headroom),
                    'dropout_v': to_json_number(selected['value']),
                    'margin_v': to_json_number(margin)},
            unit='V',
            limit={'required_headroom_v': to_json_number(selected['value'])},
            margin={'margin_v': to_json_number(margin)},
            method='exact rational arithmetic; dropout row chosen from documented conditions',
            assumptions=assumptions,
            not_modelled=not_modelled)
        draft.constraint(
            'dropout_margin',
            'VIN - VOUT must stay at or above the documented maximum dropout %s V (at %s A, '
            'condition: %s). Below dropout the regulator is out of regulation.'
            % (format_number(selected['value']), format_number(selected['load_a']),
               selected['condition'] or 'not stated'),
            kind='hard', applies_to=regulator_ref)
        if margin < 0:
            raise Unsupported(
                'worst-case headroom %s V (VIN_min %s V - VOUT_max %s V) is below the '
                'documented dropout %s V at %s A'
                % (format_number(headroom), format_number(vin.lo),
                   format_number(vout_max), format_number(selected['value']),
                   format_number(selected['load_a'])),
                reasons=['below dropout: headroom %s V < dropout %s V (VIN_min %s V, '
                         'VOUT_max %s V)'
                         % (format_number(headroom), format_number(selected['value']),
                            format_number(vin.lo), format_number(vout_max))])

    # ------------------------------------------------------------------
    # capacitor requirements
    # ------------------------------------------------------------------
    def _capacitors(self, draft, facts, vin_max, vout_max, vout_min, cin_min_f,
                    cout_min_f, derating_pct, derating):
        cin_rating = vin_max / derating
        cout_rating = vout_max / derating
        esr_min = _optional_number(facts, 'esr_min_ohm')
        esr_max = _optional_number(facts, 'esr_max_ohm')
        if (esr_min is None) != (esr_max is None):
            missing_esr = 'esr_min_ohm' if esr_min is None else 'esr_max_ohm'
            raise NeedsDeviceFacts(
                [missing_esr],
                'an ESR stability window needs both bounds; %s is missing' % missing_esr)
        if esr_min is not None and esr_min > esr_max:
            raise InputInvalid('device facts: esr_min_ohm must not exceed esr_max_ohm')
        cout_max = _optional_number(facts, 'cout_max_f')
        cout_effective_min = _optional_number(facts, 'cout_stability_min_f')
        cin_condition = _condition_text(facts, 'cin_min_f')
        cout_condition = _condition_text(facts, 'cout_min_f')

        result = {
            'cin_min_f': to_json_number(cin_min_f),
            'cout_min_f': to_json_number(cout_min_f),
            'cin_voltage_rating_v': to_json_number(cin_rating),
            'cout_voltage_rating_v': to_json_number(cout_rating),
            'esr_window_declared': esr_min is not None,
            'cout_max_f': to_json_number(cout_max) if cout_max is not None else None,
            'cout_effective_min_f': (to_json_number(cout_effective_min)
                                     if cout_effective_min is not None else None),
        }
        draft.calculation(
            'capacitor_requirements',
            'Input/output capacitor requirements derived from the device facts',
            'CIN >= cin_min_f;  COUT >= cout_min_f;  '
            'V_rating >= V_rail_worst_case * 100 / capacitor_derating_pct;  '
            'ESR within [esr_min_ohm, esr_max_ohm] when declared',
            inputs={
                'vin_max': quantity_json(vin_max, 'voltage'),
                'vout_max': quantity_json(vout_max, 'voltage'),
                'cin_min_f': quantity_json(cin_min_f, 'capacitance'),
                'cout_min_f': quantity_json(cout_min_f, 'capacitance'),
                'capacitor_derating_pct': quantity_json(derating_pct, 'percent'),
                'esr_min_ohm': (quantity_json(esr_min, 'resistance')
                                if esr_min is not None else None),
                'esr_max_ohm': (quantity_json(esr_max, 'resistance')
                                if esr_max is not None else None),
                'cin_condition': cin_condition,
                'cout_condition': cout_condition,
            },
            result=result,
            unit='F',
            limit={'cin_min_f': quantity_json(cin_min_f, 'capacitance'),
                   'cout_min_f': quantity_json(cout_min_f, 'capacitance')},
            assumptions=['the caller-declared capacitor voltage derating policy is applied to '
                         'the worst-case rail voltage',
                         'dielectric/type requirements are quoted from the device facts and '
                         'not invented here'],
            not_modelled=['capacitance loss at DC bias and temperature unless the facts state '
                          'an effective minimum',
                          'capacitor ESR variation over temperature and frequency'])

        draft.constraint(
            'input_capacitor',
            'Place at least %s F of input capacitance from VIN to GND, with a voltage '
            'rating >= %s V (worst-case rail %s V at %s%% of rating).%s'
            % (format_number(cin_min_f), format_number(cin_rating),
               format_number(vin_max), format_number(derating_pct),
               (' Condition: %s.' % cin_condition) if cin_condition else ''),
            kind='hard', applies_to='VIN')
        draft.constraint(
            'output_capacitor',
            'Place at least %s F of output capacitance from VOUT to GND, with a voltage '
            'rating >= %s V (worst-case output %s V at %s%% of rating).%s'
            % (format_number(cout_min_f), format_number(cout_rating),
               format_number(vout_max), format_number(derating_pct),
               (' Condition: %s.' % cout_condition) if cout_condition else ''),
            kind='hard', applies_to='VOUT')
        if cout_max is not None:
            draft.constraint(
                'output_capacitor_max',
                'Output capacitance must not exceed %s F; larger values are outside the '
                'recommended range the facts describe.' % format_number(cout_max),
                kind='hard', applies_to='VOUT')
        if cout_effective_min is not None:
            draft.constraint(
                'output_capacitance_effective',
                'The effective output capacitance must be at least %s F after DC-bias and '
                'temperature derating; the nominal value may need to be larger.'
                % format_number(cout_effective_min),
                kind='hard', applies_to='VOUT')
        if esr_min is not None and esr_max is not None:
            draft.constraint(
                'esr_stability_window',
                'Capacitor ESR must stay within the declared stability window %s..%s ohm.'
                % (format_number(esr_min), format_number(esr_max)),
                kind='hard', applies_to='VIN/VOUT')
        else:
            draft.constraint(
                'esr_stability_window_unverified',
                'The device facts state no numeric ESR stability window; the capacitor ESR '
                'must be checked against the datasheet capacitor recommendation before release.',
                kind='verification', applies_to='VIN/VOUT')
            draft.unknown(
                'esr_stability_window',
                'the supplied device facts describe no ESR stability window for CIN/COUT',
                impact='an ESR outside an unstated stability window could make the regulator '
                       'unstable even though the capacitance value passes',
                how_to_resolve='check the datasheet capacitor-selection section for this exact '
                               'part, or declare esr_min_ohm/esr_max_ohm facts')

    # ------------------------------------------------------------------
    # enable pin
    # ------------------------------------------------------------------
    def _enable(self, draft, facts, has_enable, has_enable_known, vin_max_v,
                regulator_ref):
        if has_enable_known and not has_enable:
            draft.constraint(
                'enable_pin_not_applicable',
                'The supplied device facts describe a part without an enable pin; the EN port '
                'is not declared.',
                kind='advisory', applies_to=regulator_ref)
            return
        if not has_enable_known:
            draft.constraint(
                'enable_pin_unknown',
                'The supplied device facts do not state whether the part has an enable pin; '
                'no EN port is declared and the enable condition is unverified.',
                kind='verification', applies_to=regulator_ref)
            draft.unknown(
                'enable_pin',
                'the device facts do not state whether an enable pin exists',
                impact='the connectivity contract may be missing an enable input',
                how_to_resolve='declare enable_pin (and enable_vih_min_v/enable_vil_max_v) '
                               'from the exact datasheet')
            return
        vih = _optional_number(facts, 'enable_vih_min_v')
        vil = _optional_number(facts, 'enable_vil_max_v')
        thresholds_known = vih is not None and vil is not None
        draft.calculation(
            'enable_interface',
            'Enable-pin drive requirement',
            'EN is active high: V_EN >= VIH(min) enables, V_EN <= VIL(max) disables; EN must '
            'stay within its absolute maximum',
            inputs={'enable_vih_min_v': (quantity_json(vih, 'voltage')
                                         if vih is not None else None),
                    'enable_vil_max_v': (quantity_json(vil, 'voltage')
                                         if vil is not None else None),
                    'enable_condition': _condition_text(facts, 'enable_pin')},
            result={'has_enable_pin': True, 'thresholds_known': thresholds_known},
            unit='V',
            limit={'enable_vih_min_v': (quantity_json(vih, 'voltage')
                                        if vih is not None else None)},
            assumptions=['the enable input is driven by a digital source within the module '
                         'boundary'],
            not_modelled=['EN-pin current when driven above VIN', 'EN input capacitance '
                          'and any maximum EN switching frequency'])
        if thresholds_known:
            draft.constraint(
                'enable_drive',
                'Drive EN to at least %s V to enable and at most %s V to disable; keep EN '
                'within its absolute maximum (do not drive it above VIN without checking the '
                'datasheet note).'
                % (format_number(vih), format_number(vil)),
                kind='hard', applies_to='EN')
        else:
            draft.constraint(
                'enable_thresholds_unverified',
                'The device facts do not state the EN threshold levels; the EN drive levels '
                'are unverified.',
                kind='verification', applies_to='EN')
            draft.unknown(
                'enable_thresholds',
                'enable_vih_min_v / enable_vil_max_v are not declared for the supplied facts',
                impact='the EN port declares a voltage range but the logic levels are not '
                       'proven compatible with the driving source',
                how_to_resolve='declare enable_vih_min_v and enable_vil_max_v from the '
                               'exact datasheet')

    # ------------------------------------------------------------------
    # reverse current
    # ------------------------------------------------------------------
    def _reverse_current(self, draft, facts, reverse_allowed, reverse_known,
                         regulator_ref):
        offset = _optional_number(facts, 'vout_abs_max_offset_v')
        offset_text = (format_number(offset) if offset is not None
                       else 'the datasheet absolute maximum (not supplied)')
        if reverse_known and reverse_allowed:
            draft.constraint(
                'reverse_current_allowed',
                'The device facts permit reverse current; still keep VOUT within the '
                'absolute-maximum relation VOUT <= VIN + %s V.' % offset_text,
                kind='advisory', applies_to=regulator_ref)
            return
        if reverse_known and not reverse_allowed:
            draft.calculation(
                'reverse_current_exposure',
                'Reverse-current exposure when the input collapses',
                'Reverse current is not permitted; VOUT must stay <= VIN + V_abs_offset. '
                'With COUT charged and VIN collapsing (power-down, UVLO, input dropout) '
                'VOUT > VIN is possible, so an external reverse-current path must be '
                'provided unless the sequence proves otherwise.',
                inputs={'reverse_current_allowed': False,
                        'vout_abs_max_offset_v': (quantity_json(offset, 'voltage')
                                                  if offset is not None else None),
                        'cout_min_f': quantity_json(fact_number(facts, 'cout_min_f'),
                                                    'capacitance')},
                result={'reverse_current_exposure': True,
                        'protection_required': True},
                unit='V',
                assumptions=['the output capacitance stores charge while the input can '
                             'collapse during power-down or a fault'],
                not_modelled=['the magnitude of the reverse current (no numeric limit is '
                              'declared by the facts)',
                              'power-down sequencing and discharge timing'])
            draft.constraint(
                'reverse_current_protection',
                'Reverse current is not permitted: keep VOUT <= VIN + %s V. Add an external '
                'reverse-current protection/sequencing measure (for example a series switch '
                'or a Schottky path as the datasheet requires) whenever the input can fall '
                'below the output while COUT is charged.' % offset_text,
                kind='hard', applies_to=regulator_ref)
            draft.unknown(
                'reverse_current_magnitude',
                'the device facts declare no numeric reverse-current magnitude limit; only '
                'the VOUT <= VIN + offset absolute maximum and the external-protection '
                'requirement are stated',
                impact='the protection device cannot be sized from the supplied facts',
                how_to_resolve='obtain the reverse-current magnitude/energy from the '
                               'manufacturer application note or validate it on the bench')
        else:
            draft.constraint(
                'reverse_current_allowed_unknown',
                'The supplied device facts do not state whether reverse current is '
                'permitted; a reverse-current path is unverified.',
                kind='verification', applies_to=regulator_ref)
            draft.unknown(
                'reverse_current_allowed',
                'the device facts do not state whether reverse current is permitted',
                impact='driving VOUT above VIN (power-down, pre-biased output) may damage '
                       'the device',
                how_to_resolve='declare reverse_current_allowed from the exact datasheet')

    # ------------------------------------------------------------------
    # thermal estimate
    # ------------------------------------------------------------------
    def _thermal(self, draft, theta_ja, board_condition, ambient, power, tj_max_c,
                 regulator_ref):
        if theta_ja is not None and theta_ja <= 0:
            raise InputInvalid('device facts: theta_ja_c_per_w must be positive')
        if theta_ja is None or board_condition is None:
            return None
        tj_est = ambient.hi + power * theta_ja
        margin = tj_max_c - tj_est
        draft.calculation(
            'thermal_estimate',
            'Junction-temperature estimate under the datasheet board condition '
            '(an estimate, not a board-temperature guarantee)',
            'Tj_est = Ta_max + P * theta_JA',
            inputs={'ambient_temperature': ambient.as_json('temperature'),
                    'power_w': quantity_json(power, 'power'),
                    'theta_ja_c_per_w': {'value': to_json_number(theta_ja),
                                         'unit': 'C/W'},
                    'board_condition': board_condition,
                    'tj_max_c': quantity_json(tj_max_c, 'temperature')},
            result={'tj_est_c': to_json_number(tj_est)},
            unit='degC',
            limit={'tj_max_c': quantity_json(tj_max_c, 'temperature')},
            margin={'margin_c': to_json_number(margin)},
            method='first-order steady-state estimate: Tj = Ta_max + P * theta_JA',
            assumptions=['theta_JA applies to the exact datasheet board condition quoted '
                         'here, in the datasheet environment',
                         'the declared ambient maximum coincides with the worst-case '
                         'dissipation (one operating point)',
                         'theta_JA is a JEDEC/board characterisation parameter of the exact '
                         'package variant'],
            not_modelled=['the real user board copper area, airflow, enclosure and adjacent '
                          'heat sources (a board temperature is not guaranteed by this estimate)',
                          'duty cycling, transient thermal impedance and thermal capacitance',
                          'junction-temperature dependence of Iq and theta_JA'])
        draft.constraint(
            'thermal_junction_limit',
            'Under the datasheet board condition (%s) the estimated junction temperature is '
            '%s degC at Ta_max=%s degC; it must stay <= tj_max_c %s degC. This is an '
            'estimate for that condition, not a board-temperature guarantee.'
            % (board_condition, format_number(tj_est), format_number(ambient.hi),
               format_number(tj_max_c)),
            kind='hard', applies_to=regulator_ref)
        draft.constraint(
            'thermal_board_condition',
            'Rtheta_JA is only valid for the quoted board condition; the actual PCB thermal '
            'path, enclosure and airflow must be verified by measurement before release.',
            kind='verification', applies_to=regulator_ref)
        draft.constraint(
            'layout_thermal',
            'Provide the copper/thermal path assumed by the datasheet board condition; keep '
            'the regulator away from heat sources and allow the capacitor temperature rise.',
            kind='layout', applies_to=regulator_ref)
        return tj_est, margin, tj_max_c

    # ------------------------------------------------------------------
    # bleed resistor
    # ------------------------------------------------------------------
    def _resolve_bleed(self, draft, inputs, vout_min, vout_max, load, min_load_a):
        if not inputs.get('bleed_resistor'):
            deficit = min_load_a - load.lo
            if min_load_a > 0 and deficit > 0:
                draft.calculation(
                    'minimum_load',
                    'Requested minimum load against the device minimum-load requirement',
                    'I_load_min >= min_load_a',
                    inputs={'load_min_a': quantity_json(load.lo, 'current'),
                            'min_load_a': quantity_json(min_load_a, 'current')},
                    result={'pass': False,
                            'deficit_a': to_json_number(deficit)},
                    unit='A',
                    limit={'min_load_a': quantity_json(min_load_a, 'current')},
                    margin={'margin_a': to_json_number(load.lo - min_load_a)},
                    assumptions=['the device minimum-load requirement is a hard operating '
                                 'condition, not an advisory'],
                    not_modelled=['leakage currents and the minimum load provided by the '
                                  'load itself'])
                draft.constraint(
                    'minimum_load_path',
                    'The requested load range goes down to %s A, below the device minimum '
                    'load %s A. Provide an external minimum-load/bleed path (or declare '
                    'bleed_resistor) so the regulator always sees at least %s A; no bleed '
                    'component was added silently.'
                    % (format_number(load.lo), format_number(min_load_a),
                       format_number(min_load_a)),
                    kind='hard', applies_to='VOUT')
                raise NoFeasibleSolution(
                    'minimum load not guaranteed: load can fall to %s A while the device '
                    'requires at least %s A, and no bleed resistor was declared'
                    % (format_number(load.lo), format_number(min_load_a)),
                    bounds={'load_min_a': to_json_number(load.lo),
                            'min_load_a': to_json_number(min_load_a)})
            return None

        deficit = min_load_a - load.lo
        if deficit <= 0:
            draft.constraint(
                'bleed_not_required',
                'A bleed resistor was declared but the load minimum %s A already satisfies '
                'the device minimum load %s A; no bleed resistor was selected because no '
                'bleed current target exists.'
                % (format_number(load.lo), format_number(min_load_a)),
                kind='advisory', applies_to='VOUT')
            return None

        series = inputs.get('bleed_series')
        tolerance = inputs.quantity('bleed_tolerance_pct') / 100
        derating = inputs.quantity('bleed_power_derating_pct') / 100
        if derating >= 1:
            raise InputInvalid('bleed_power_derating_pct must be below 100',
                               field='bleed_power_derating_pct')
        window = inputs.get('bleed_resistance_range')
        candidates = series_values(series, window.lo if window is not None else None,
                                   window.hi if window is not None else None)
        if not candidates:
            raise InputInvalid('no bleed resistor candidates: the declared series/range is empty',
                               field='bleed_series')
        # Guarantee I_bleed_min = VOUT_min / (R*(1+tol)) >= deficit
        r_upper = vout_min / (deficit * (1 + tolerance))
        feasible = [value for value in candidates if value <= r_upper]
        if not feasible:
            draft.calculation(
                'minimum_load',
                'Bleed resistor for the device minimum-load requirement',
                'R_bleed <= VOUT_min / (deficit * (1 + tolerance));  '
                'I_bleed_min = VOUT_min / (R*(1+tolerance)) >= deficit',
                inputs={'deficit_a': quantity_json(deficit, 'current'),
                        'vout_min': quantity_json(vout_min, 'voltage'),
                        'bleed_tolerance_pct': quantity_json(tolerance * 100, 'percent'),
                        'bleed_series': series},
                result={'pass': False, 'max_ohm': to_json_number(r_upper)},
                unit='ohm',
                limit={'max_ohm': to_json_number(r_upper)},
                margin=None,
                assumptions=['the bleed resistor tolerance is applied to the minimum-load '
                             'guarantee'],
                not_modelled=['bleed resistor self-heating'])
            draft.constraint(
                'minimum_load_path',
                'No standard bleed resistor in %s is small enough to guarantee the device '
                'minimum load; provide an active minimum-load sink instead.'
                % series,
                kind='hard', applies_to='VOUT')
            raise NoFeasibleSolution(
                'no standard %s bleed resistor is <= %s ohm, which is the largest value that '
                'still guarantees the device minimum load %s A'
                % (series, format_number(r_upper), format_number(min_load_a)),
                bounds={'r_max_ohm': to_json_number(r_upper)})

        resistance = max(feasible)
        i_min = vout_min / (resistance * (1 + tolerance))
        i_max = vout_max / (resistance * (1 - tolerance))
        power = vout_max ** 2 / (resistance * (1 - tolerance))
        required_rating = power / (1 - derating)
        draft.calculation(
            'minimum_load',
            'Bleed resistor selected to satisfy the device minimum-load requirement',
            'R_bleed <= VOUT_min / (deficit * (1 + tolerance));  '
            'I_bleed_min = VOUT_min / (R*(1+tolerance));  '
            'I_bleed_max = VOUT_max / (R*(1-tolerance));  P_bleed = VOUT_max^2 / R_min',
            inputs={'deficit_a': quantity_json(deficit, 'current'),
                    'vout_min': quantity_json(vout_min, 'voltage'),
                    'vout_max': quantity_json(vout_max, 'voltage'),
                    'bleed_tolerance_pct': quantity_json(tolerance * 100, 'percent'),
                    'bleed_series': series,
                    'bleed_resistance': quantity_json(resistance, 'resistance')},
            result={'selected_ohm': to_json_number(resistance),
                    'bleed_current_min_a': to_json_number(i_min),
                    'bleed_current_max_a': to_json_number(i_max),
                    'bleed_power_w': to_json_number(power),
                    'required_rating_w': to_json_number(required_rating)},
            unit='ohm',
            limit={'max_ohm': to_json_number(r_upper)},
            margin={'min_load_margin_a': to_json_number(load.lo + i_min - min_load_a)},
            assumptions=['the bleed resistor tolerance is applied to the minimum-load '
                         'guarantee and to the worst-case power'],
            not_modelled=['bleed resistor self-heating changing its value',
                          'bleed current being switched off in low-power modes'])
        return {'r': resistance, 'i_min': i_min, 'i_max': i_max,
                'power': power, 'rating': required_rating, 'series': series,
                'tolerance_pct': tolerance * 100}

    # ------------------------------------------------------------------
    # topology
    # ------------------------------------------------------------------
    def _write_topology(self, draft, inputs, facts, vin, load, total_iout_max, iq,
                        vout_min, vout_max, cin_min_f, cout_min_f, bleed,
                        has_enable, tolerance, vin_min_v, vin_max_v, mpn,
                        manufacturer, fact_id, verified):
        regulator_pins = [
            {'name': 'VIN', 'semantic': 'power_input'},
            {'name': 'VOUT', 'semantic': 'power_output'},
            {'name': 'GND', 'semantic': 'ground'},
        ]
        if has_enable:
            regulator_pins.append({'name': 'EN', 'semantic': 'enable'})
        regulator = draft.component(
            'ldo_regulator', 'ic',
            pins=regulator_pins,
            requirements={
                'mpn_reference': mpn,
                'manufacturer': manufacturer,
                'device_fact_id': fact_id,
                'device_facts_verified': verified,
                'function': 'fixed-output LDO regulator',
                'output_voltage': quantity_json(
                    fact_number(facts, 'vout_nom_v'), 'voltage'),
                'output_tolerance_pct': quantity_json(
                    fact_number(facts, 'vout_tol_pct'), 'percent'),
                'output_current_max': quantity_json(
                    fact_number(facts, 'iout_max_a'), 'current'),
                'input_voltage_range': {
                    'min': to_json_number(vin_min_v),
                    'max': to_json_number(vin_max_v),
                    'unit': canonical_unit('voltage'),
                },
                'package_condition': _condition_text(facts, 'theta_ja_c_per_w'),
            },
            notes='Abstract fixed-output LDO; the MPN is a reference requirement for later '
                  'part binding, not a bound library/stock/physical part.')

        cin_condition = _condition_text(facts, 'cin_min_f')
        cout_condition = _condition_text(facts, 'cout_min_f')
        cin_rating = vin.hi / (inputs.quantity('capacitor_derating_pct') / 100)
        cout_rating = vout_max / (inputs.quantity('capacitor_derating_pct') / 100)
        cin = draft.component(
            'input_decoupling', 'capacitor', value=cin_min_f,
            voltage_rating_v=cin_rating,
            requirements={
                'min_capacitance': quantity_json(cin_min_f, 'capacitance'),
                'voltage_rating_required': quantity_json(cin_rating, 'voltage'),
                'device_condition': cin_condition,
            },
            notes='Input decoupling capacitor; the value is the device minimum requirement '
                  'from the facts, not an invented generic value.')
        cout = draft.component(
            'output_capacitor', 'capacitor', value=cout_min_f,
            voltage_rating_v=cout_rating,
            requirements={
                'min_capacitance': quantity_json(cout_min_f, 'capacitance'),
                'voltage_rating_required': quantity_json(cout_rating, 'voltage'),
                'device_condition': cout_condition,
            },
            notes='Output capacitor; the value is the device minimum requirement from the '
                  'facts, not an invented generic value.')

        vin_net = draft.net('VIN', role='power', scope='external',
                            voltage_domain='input supply')
        vout_net = draft.net('VOUT', role='power', scope='external',
                             voltage_domain='regulated output')
        gnd_net = draft.net('GND', role='ground', scope='external')
        en_net = draft.net('EN', role='signal', scope='external',
                           voltage_domain='logic') if has_enable else None

        draft.connect(regulator['ref'], 'VIN', vin_net, 'power_input')
        draft.connect(regulator['ref'], 'VOUT', vout_net, 'power_output')
        draft.connect(regulator['ref'], 'GND', gnd_net, 'ground')
        if has_enable:
            draft.connect(regulator['ref'], 'EN', en_net, 'enable')
        draft.connect(cin['ref'], '1', vin_net, 'input_capacitor')
        draft.connect(cin['ref'], '2', gnd_net, 'return_side')
        draft.connect(cout['ref'], '1', vout_net, 'output_capacitor')
        draft.connect(cout['ref'], '2', gnd_net, 'return_side')

        if bleed is not None:
            bleed_component = draft.component(
                'minimum_load_bleed', 'resistor',
                value=bleed['r'], tolerance_pct=bleed['tolerance_pct'],
                series=bleed['series'],
                power_rating_w=bleed['rating'],
                voltage_rating_v=vout_max,
                requirements={
                    'min_load_a': quantity_json(fact_number(facts, 'min_load_a'),
                                                'current'),
                    'bleed_current_min': quantity_json(bleed['i_min'], 'current'),
                    'bleed_current_max': quantity_json(bleed['i_max'], 'current'),
                    'required_power_rating': quantity_json(bleed['rating'], 'power'),
                },
                notes='Optional minimum-load bleed resistor declared by the caller; the '
                      'value is a standard series value.')
            draft.connect(bleed_component['ref'], '1', vout_net, 'output_side')
            draft.connect(bleed_component['ref'], '2', gnd_net, 'return_side')

        vih = _optional_number(facts, 'enable_vih_min_v')
        vil = _optional_number(facts, 'enable_vil_max_v')
        logic = None
        if has_enable:
            logic = {
                'active_level': 'high',
                'vih_min': quantity_json(vih, 'voltage') if vih is not None else None,
                'vil_max': quantity_json(vil, 'voltage') if vil is not None else None,
                'thresholds_verified': vih is not None and vil is not None,
                'condition': _condition_text(facts, 'enable_pin'),
            }

        draft.port('VIN', 'input', 'power', net=vin_net, voltage=vin,
                   current=Interval(load.lo, total_iout_max + iq),
                   description='Regulator input supply (declared operating range)')
        draft.port('VOUT', 'output', 'power', net=vout_net,
                   voltage=Interval(vout_min, vout_max), current=load,
                   description='Regulated output over the device tolerance, with the '
                               'declared load current range')
        draft.port('GND', 'passive', 'ground', net=gnd_net,
                   description='Ground return')
        if has_enable:
            draft.port('EN', 'input', 'digital', net=en_net,
                       voltage=Interval(Fraction(0), vin_max_v), logic=logic,
                       description='Enable input (active high per the supplied facts)',
                       notes='Keep EN within its absolute maximum; driving EN above VIN has '
                             'its own datasheet conditions.')
        return {'regulator': regulator, 'cin': cin, 'cout': cout}

    # ------------------------------------------------------------------
    # evidence and records
    # ------------------------------------------------------------------
    def _evidence(self, draft, facts, origin, verified, mpn, manufacturer, fact_id,
                  inputs, vin, load, ambient, vout_min, vout_max, total_iout_max):
        if origin == 'bundled':
            keys = _consumed_fact_keys(facts)
            evidence_for(draft, facts, keys)
            draft.evidence(
                'device_document_facts', 'manufacturer_datasheet',
                'Device facts for %s (%s) were verified against the primary manufacturer '
                'document %s. This is a documentary check only: library, stock, host and '
                'physical binding remain NOT RUN.'
                % (mpn, fact_id,
                   (facts.get('sources') or [{}])[0].get('document', '')),
                source={'document': (facts.get('sources') or [{}])[0].get('document'),
                        'doc_id': (facts.get('sources') or [{}])[0].get('doc_id'),
                        'revision': (facts.get('sources') or [{}])[0].get('revision'),
                        'url': (facts.get('sources') or [{}])[0].get('url')},
                verified=True)
        else:
            source_note = inputs.get('device_source_note') or 'caller declaration'
            draft.evidence(
                'device_consumer_declared_facts', 'user_declared',
                'Device facts were declared by the caller (%s); they are not verified '
                'against a manufacturer document. MPN reference: %s.'
                % (source_note, mpn or 'not declared'),
                source={'document': source_note},
                verified=False)
        draft.evidence(
            'input_declaration', 'user_declared',
            'Application ranges declared by the caller: VIN %s..%s V, VOUT %s V, IOUT %s..%s A, '
            'ambient %s..%s degC.'
            % (format_number(vin.lo), format_number(vin.hi),
               format_number((vout_min + vout_max) / 2),
               format_number(load.lo), format_number(load.hi),
               format_number(ambient.lo), format_number(ambient.hi)),
            verified=False)
        draft.evidence(
            'derivation', 'derivation',
            'Envelope, headroom, dissipation, thermal estimate and capacitor requirements are '
            'derived here with exact rational arithmetic from the declared ranges and the '
            'supplied device facts; worst-case extremes are treated as independent.')
        if origin == 'bundled':
            draft.evidence(
                'fact_scope', 'application_note',
                'Verified device facts prove document facts only. They do not prove the part '
                'is in stock, that a PCB library footprint exists, that the pin map matches a '
                'physical package, or that the circuit was built and measured.',
                source={'document': 'circuit_blocks/devices/SCHEMA.md'}, verified=False)

    def _records(self, draft, facts, bleed):
        draft.assumption(
            'Input voltage, output tolerance and load current extremes may occur '
            'simultaneously (independent worst case).',
            impact='conservative electrical margins; correlated extremes would be narrower')
        draft.assumption(
            'The quiescent current used in the dissipation estimate is the declared iq_a '
            'fact.',
            impact='a hotter or maximum ground current would increase the estimate')
        draft.assumption(
            'Rtheta_JA is applied as a first-order steady-state estimate under the exact '
            'datasheet board condition; it is not a board temperature guarantee.',
            impact='the real junction temperature must be verified on the actual PCB')
        if _condition_text(facts, 'cin_min_f') is None or \
                _condition_text(facts, 'cout_min_f') is None:
            draft.unknown(
                'capacitor_type_unverified',
                'the supplied device facts do not state the required capacitor dielectric/'
                'type condition for CIN and/or COUT',
                impact='a capacitor that meets the capacitance value may not meet the '
                       'stability requirement',
                how_to_resolve='read the datasheet capacitor-selection section for this exact '
                               'part and declare the condition text')
        if bleed is not None:
            draft.evidence(
                'standard_series', 'standard',
                'The bleed resistor value was selected from IEC 60063 series %s.'
                % bleed['series'],
                source={'document': 'IEC 60063', 'section': 'preferred number series',
                        'url': 'https://webstore.iec.ch/publication/593'})
        draft.constraint(
            'verify_extremes',
            'Measure the output at both input-voltage extremes and at the ambient extremes '
            'after assembly; verify the output stays inside the device accuracy window.',
            kind='verification', applies_to='VOUT')
        draft.constraint(
            'out_of_range_operation',
            'Operation below dropout, above the rated output current, or above tj_max_c is '
            'outside the device recommended range: it is reported as a constraint here and '
            'must not be relied on by the load.',
            kind='hard', applies_to='VIN/VOUT')
        if bleed is not None:
            draft.constraint(
                'bleed_resistor_rating',
                'Use a %s ohm %s resistor rated at least %s W at the declared derating, and '
                'keep the bleed current (%s..%s A) inside the output-current budget.'
                % (format_number(bleed['r']), bleed['series'],
                   format_number(bleed['rating']),
                   format_number(bleed['i_min']), format_number(bleed['i_max'])),
                kind='hard', applies_to='minimum_load_bleed')


# ----------------------------------------------------------------------
# fact-source helpers
# ----------------------------------------------------------------------
def _resolve_facts(inputs):
    fact_id = inputs.get('device_fact_id')
    declared = inputs.get('device_facts')
    if fact_id is not None and declared is not None:
        raise InputInvalid(
            'device_fact_id and device_facts are mutually exclusive; choose one fact source',
            field='device_fact_id')
    if fact_id is not None:
        return load_fact(fact_id), 'bundled'
    if declared is not None:
        return _declared_facts(inputs), 'user'
    raise NeedsDeviceFacts(
        ['device_fact_id or device_facts'],
        'no device facts were supplied: give a verified fact-file id or caller-declared '
        'facts; a generic LDO is never invented')


def _declared_facts(inputs):
    declared = inputs.get('device_facts')
    payload = {}
    for name in _DEVICE_FACT_SCHEMA:
        if name not in declared:
            continue
        record = declared.obj(name)
        item = {'value': record.get('value')}
        for optional in ('condition', 'source', 'applies_to', 'load_a'):
            if optional in record:
                item[optional] = record.get(optional)
        if item['value'] is None:
            raise InputInvalid('device_facts.%s.value must not be null' % name,
                               field='device_facts.%s.value' % name)
        payload[name] = item
    facts = user_declared_facts(payload, 'ldo', mpn=inputs.get('device_mpn'),
                                source_note=inputs.get('device_source_note'))
    for name, item in payload.items():
        if 'load_a' in item:
            facts['facts'][name]['load_a'] = item['load_a']
    return facts


def _optional_number(facts, key):
    if key not in (facts.get('facts') or {}):
        return None
    return fact_number(facts, key)


def _condition_text(facts, key):
    if key not in (facts.get('facts') or {}):
        return None
    try:
        text = fact_condition(facts, key)
    except NeedsDeviceFacts:
        return None
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text or text.lower() == _DECLARED_PLACEHOLDER:
        return None
    return text


def _board_condition(facts):
    return _condition_text(facts, 'theta_ja_c_per_w')


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return False
        return not text.startswith(('no', 'false', 'not', 'disabled', 'none', 'n/a'))
    if isinstance(value, (int, Fraction)):
        return value != 0
    return bool(value)


def _enable_state(facts):
    facts_map = facts.get('facts') or {}
    if 'enable_pin' not in facts_map:
        return None, None
    return _truthy(fact_value(facts, 'enable_pin')), True


def _reverse_state(facts):
    facts_map = facts.get('facts') or {}
    if 'reverse_current_allowed' not in facts_map:
        return None, None
    return _truthy(fact_value(facts, 'reverse_current_allowed')), True


def _consumed_fact_keys(facts):
    keys = []
    for name in ('vin_min_v', 'vin_max_v', 'vin_abs_max_v', 'vout_nom_v',
                 'vout_tol_pct', 'iout_max_a', 'iq_a', 'cin_min_f', 'cout_min_f',
                 'cout_max_f', 'cout_stability_min_f', 'esr_min_ohm', 'esr_max_ohm',
                 'min_load_a', 'theta_ja_c_per_w', 'tj_max_c', 'enable_pin',
                 'enable_vih_min_v', 'enable_vil_max_v', 'reverse_current_allowed',
                 'vout_abs_max_offset_v', 'current_limit_min_a'):
        if name in (facts.get('facts') or {}):
            keys.append(name)
    for name in sorted(facts.get('facts') or {}):
        if name.startswith('dropout') and name.endswith('_v') and 'typ' not in name \
                and name not in keys:
            keys.append(name)
    return keys


# ----------------------------------------------------------------------
# dropout row helpers
# ----------------------------------------------------------------------
def _parse_load_a(record, condition):
    for key in ('load_a', 'iout_a', 'iout_max_a', 'current_a'):
        if key not in record:
            continue
        value = record[key]
        if isinstance(value, dict) and 'value' in value:
            value = value['value']
        return parse_number(value)
    if condition:
        match = _LOAD_RE.search(condition)
        if match:
            amount = parse_number(match.group(1))
            prefix = match.group(2)
            return amount * _PREFIX[prefix] if prefix else amount
    return None


def _parse_temperature_range(condition):
    if not condition:
        return None
    match = _TEMP_RANGE_RE.search(condition)
    if not match:
        return None
    low, high = parse_number(match.group(1)), parse_number(match.group(2))
    if low > high:
        return None
    return low, high


def _dropout_rows(facts):
    records = facts.get('facts') or {}
    rows = []
    for key in sorted(records):
        if 'typ' in key.lower():
            continue
        if key != 'dropout_v' and not (key.startswith('dropout') and key.endswith('_v')):
            continue
        record = records[key]
        if isinstance(record, list):
            for index, item in enumerate(record):
                if not isinstance(item, dict) or 'value' not in item:
                    raise InputInvalid(
                        'device facts: %s[%d] is not a value record' % (key, index))
                row = _single_dropout_row('%s[%d]' % (key, index), item)
                if row is not None:
                    rows.append(row)
        elif isinstance(record, dict) and 'value' in record:
            row = _single_dropout_row(key, record)
            if row is not None:
                rows.append(row)
        else:
            raise InputInvalid('device facts: %s is not a numeric fact record' % key)
    return rows


def _single_dropout_row(key, record):
    try:
        value = parse_number(record['value'])
    except InputInvalid:
        raise NeedsDeviceFacts([key], 'device fact %r is not numeric' % key)
    condition = record.get('condition') if isinstance(record.get('condition'), str) else None
    load_a = _parse_load_a(record, condition)
    if load_a is None:
        return None
    temperature = _parse_temperature_range(condition)
    return {'key': key, 'value': value, 'load_a': load_a,
            'condition': condition, 'temp': temperature}


def _choose_dropout(rows, iout_max, ambient):
    """Pick the documented dropout row that applies to this operating point."""
    parsed = [row for row in rows if row['temp'] is not None]
    unparsed = [row for row in rows if row['temp'] is None]
    covering = [row for row in parsed
                if row['temp'][0] <= ambient.lo and ambient.hi <= row['temp'][1]]
    if covering:
        pool, mode = covering, 'documented'
    elif parsed:
        # No documented condition covers the declared ambient range: fall back to
        # every row and take the largest documented maximum (conservative).
        pool, mode = list(rows), 'uncovered'
    else:
        pool, mode = unparsed, 'undeclared'

    above = [row for row in pool if row['load_a'] >= iout_max]
    extrapolated = not above
    if above:
        pool = above
        lowest_load = min(row['load_a'] for row in pool)
        pool = [row for row in pool if row['load_a'] == lowest_load]
        if mode == 'documented':
            selected = min(pool, key=lambda row: (row['temp'][1] - row['temp'][0],
                                                  -row['value']))
        else:
            selected = max(pool, key=lambda row: row['value'])
    else:
        highest_load = max(row['load_a'] for row in pool)
        pool = [row for row in pool if row['load_a'] == highest_load]
        selected = max(pool, key=lambda row: row['value'])
    load_values = sorted({row['load_a'] for row in rows})
    info = {
        'mode': mode,
        'extrapolated': extrapolated,
        'single_load_condition': len(load_values) == 1,
        'load_conditions': load_values,
    }
    return selected, info


# ----------------------------------------------------------------------
# facts sanity
# ----------------------------------------------------------------------
def _sanity(facts, vin_min_v, vin_max_v, vout_nom_v, vout_tol_pct, iout_max_a,
            iq_a, cin_min_f, cout_min_f, min_load_a, tj_max_c):
    if vin_min_v <= 0 or vin_max_v <= 0:
        raise InputInvalid('device facts: input voltage limits must be positive')
    if vin_min_v > vin_max_v:
        raise InputInvalid('device facts: vin_min_v must not exceed vin_max_v')
    if vout_nom_v <= 0:
        raise InputInvalid('device facts: vout_nom_v must be positive')
    if vout_tol_pct < 0:
        raise InputInvalid('device facts: vout_tol_pct must not be negative')
    if iout_max_a <= 0:
        raise InputInvalid('device facts: iout_max_a must be positive')
    if iq_a < 0:
        raise InputInvalid('device facts: iq_a must not be negative')
    if cin_min_f <= 0 or cout_min_f <= 0:
        raise InputInvalid('device facts: minimum capacitances must be positive')
    if min_load_a < 0 or min_load_a > iout_max_a:
        raise InputInvalid('device facts: min_load_a must be between 0 and iout_max_a')
    if tj_max_c <= 0:
        raise InputInvalid('device facts: tj_max_c must be a positive temperature')
