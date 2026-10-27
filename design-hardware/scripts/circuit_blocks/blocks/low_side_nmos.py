"""F5 — low-side N-channel MOSFET switch.

Topology::

    VLOAD ---- load ---- SW (drain) --+-- freewheel diode anode (inductive only)
                                       |
                            Q1 drain --+
                            Q1 source ---- GND
    GATE --[optional R_gate]-- gate node --[optional R_pulldown]-- GND

All numeric decisions use exact :class:`fractions.Fraction` arithmetic.  The
MOSFET on-state is taken from the datasheet ``RDS(ON)`` row whose ``VGS`` is at
or below the *minimum* declared gate drive — never interpolated upward and never
substituted by ``VGS(th)``, which only proves the onset of conduction.  A
row that states only a typical value is reported as an estimate plus a hard
selection requirement, not turned into a fabricated maximum.

The module distinguishes what it can prove from what it cannot:

* conduction loss ``I^2*RDS(ON)`` at the stated current is computed exactly;
* switching loss needs Qg/capacitance/time data and is reported ``unknown``
  when those facts are absent — a static conduction number never becomes a
  thermal design;
* package/die thermal checks run only when the thermal facts exist, and are
  explicitly labelled estimates under the datasheet's reference board;
* an inductive load always emits the freewheel-diode voltage/current/pulse
  conditions as selection constraints, never an invented diode MPN;
* a gate series resistor is selected from a standard series only when a target
  is requested; the gate pulldown is emitted with its rationale.
"""
from __future__ import annotations

from fractions import Fraction

from ..errors import InputInvalid, NeedsDeviceFacts, NoFeasibleSolution
from ..eseries import nearest, values as series_values
from ..numeric import format_number, parse_number, to_json_number
from ..ranges import Interval
from ..units import quantity_json
from .base import Block
from ..devices import (evidence_for, fact, load_fact, missing_keys,
                       user_declared_facts)

#: Standard resistor values from 1 ohm to 9.1 Mohm (gate/pulldown domain).
_RESISTOR_DECADES = range(0, 7)

#: Facts the module cannot prove anything without.
_REQUIRED_FACTS = ('vds_max_v', 'vgss_max_v', 'id_max_a', 'rds_on_ohm',
                   'vgs_th_max_v')

#: Optional facts that improve the result when present.
_OPTIONAL_FACTS = ('id_pulsed_max_a', 'pd_max_w', 'qg_typ_c', 'ciss_typ_f',
                   'theta_ja_c_per_w', 'tj_max_c', 'body_diode',
                   'is_body_diode_max_a', 'vf_body_diode_max_v', 'soa')


class LowSideNmos(Block):
    MODULE_TYPE = 'low_side_nmos'
    TEMPLATE_VERSION = '1.0.0'
    TITLE = 'Low-side N-channel MOSFET switch'
    SUMMARY = ('Checks a declared N-MOSFET against a load and its gate drive: RDS(ON) at the '
               'actual VGS, conduction loss, VDS/ID/VGS limits, inrush pulse rating, conditional '
               'thermal estimate, gate network and the freewheel conditions for an inductive '
               'load; switching loss and thermal rise stay explicitly unknown when the facts '
               'cannot prove them.')
    TOPOLOGY = ('load from VLOAD to SW; N-MOSFET drain at SW, source at GND, gate driven from '
                'GATE through an optional series resistor with an optional pulldown; optional '
                'freewheel diode across the load for inductive loads')
    APPLICABILITY = (
        'single N-channel MOSFET switching one low-side load',
        'gate drive declared as a voltage range; RDS(ON) read at or below its minimum',
        'DC or switched load with declared frequency; switching loss is not fabricated',
        'inductive load with a declared inductance or energy for the freewheel requirement',
    )
    NON_APPLICABILITY = (
        'high-side switches, P-channel FETs, H-bridges and synchronous rectifiers',
        'a thermal design: θJA results are datasheet-board estimates, not a board measurement',
        'SOA or repetitive-pulse verification beyond the declared facts',
        'unclamped inductive switching / avalanche design when no freewheel path is provided',
        'MOSFET part selection: the result names a requirement, never a bound MPN',
    )
    REQUIRED_DEVICE_FACTS = (
        'MOSFET category mosfet_n facts: vds_max_v, vgss_max_v, id_max_a, rds_on_ohm rows with '
        'the VGS condition, vgs_th_max_v',
        'optional but required for stronger claims: id_pulsed_max_a, qg_typ_c, ciss_typ_f, '
        'pd_max_w, theta_ja_c_per_w, tj_max_c, body_diode',
        'load voltage/current/inrush, gate drive range and switching frequency or DC flag',
    )
    SOURCES = (
        {'document': 'MOSFET manufacturer datasheet (exact part, via device fact file)',
         'why': 'RDS(ON) by VGS, VDS/VGS/ID ratings, thermal data, gate charge'},
        {'document': 'IEC 60063 preferred number series (E6/E12/E24/E48/E96)',
         'why': 'standard gate series and pulldown resistor values'},
        {'document': 'Ohm/Joule switching and gate-drive analysis',
         'why': 'conduction loss, freewheel energy and gate network sizing'},
    )

    INPUT_SCHEMA = {
        'load_supply_voltage': {
            'kind': 'range', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'Load supply voltage range at VLOAD (V).'},
        'load_current_nominal': {
            'kind': 'quantity', 'family': 'current', 'required': True, 'positive': True,
            'doc': 'Nominal load current (A).'},
        'load_current_max': {
            'kind': 'quantity', 'family': 'current', 'required': True, 'positive': True,
            'doc': 'Maximum continuous load current through the FET (A).'},
        'load_inrush_current': {
            'kind': 'quantity', 'family': 'current', 'positive': True,
            'doc': 'Optional inrush/start-up current (A); checked against the pulse rating.'},
        'gate_drive_voltage': {
            'kind': 'range', 'family': 'voltage', 'required': True, 'positive': True,
            'doc': 'Gate drive voltage range at GATE (V); the minimum drives RDS(ON) selection.'},
        'switching_frequency': {
            'kind': 'quantity', 'family': 'frequency', 'positive': True,
            'doc': 'Switching frequency (Hz). Declare this or dc_operation=true, not both.'},
        'dc_operation': {
            'kind': 'bool',
            'doc': 'True for a DC (never switched) load; mutually exclusive with '
                   'switching_frequency.'},
        'inductive_load': {
            'kind': 'bool', 'required': True,
            'doc': 'True when the load is inductive and a freewheel path is required.'},
        'load_inductance': {
            'kind': 'quantity', 'family': 'inductance', 'positive': True,
            'doc': 'Optional load inductance (H) used for the freewheel energy requirement.'},
        'load_energy_mj': {
            'kind': 'number', 'nonnegative': True,
            'doc': 'Optional declared inductive energy in millijoules (mJ); used when the '
                   'inductance is not declared.'},
        'ambient_temperature': {
            'kind': 'range', 'family': 'temperature',
            'doc': 'Optional ambient temperature range (degC) for the thermal estimate.'},
        'device_fact_id': {
            'kind': 'string',
            'doc': 'Bundled verified device fact id (category mosfet_n), e.g. "mosfet_ao3400a".'},
        'device_facts': {
            'kind': 'object',
            'fields': {
                'vds_max_v': {'kind': 'quantity', 'family': 'voltage', 'positive': True},
                'vgss_max_v': {'kind': 'quantity', 'family': 'voltage', 'positive': True},
                'id_max_a': {'kind': 'quantity', 'family': 'current', 'positive': True},
                'id_pulsed_max_a': {'kind': 'quantity', 'family': 'current', 'positive': True},
                'pd_max_w': {'kind': 'quantity', 'family': 'power', 'positive': True},
                'rds_on_ohm': {
                    'kind': 'array',
                    'items': {
                        'kind': 'object',
                        'fields': {
                            'vgs_v': {'kind': 'quantity', 'family': 'voltage', 'positive': True},
                            'id_a': {'kind': 'quantity', 'family': 'current', 'positive': True},
                            'max_ohm': {'kind': 'quantity', 'family': 'resistance',
                                        'positive': True},
                            'typ_ohm': {'kind': 'quantity', 'family': 'resistance',
                                        'positive': True},
                            'condition': {'kind': 'string'},
                        },
                    },
                },
                'vgs_th_min_v': {'kind': 'quantity', 'family': 'voltage', 'positive': True},
                'vgs_th_max_v': {'kind': 'quantity', 'family': 'voltage', 'positive': True},
                'qg_typ_c': {'kind': 'quantity', 'family': 'charge', 'positive': True},
                'ciss_typ_f': {'kind': 'quantity', 'family': 'capacitance', 'positive': True},
                'theta_ja_c_per_w': {'kind': 'number', 'positive': True},
                'tj_max_c': {'kind': 'quantity', 'family': 'temperature'},
                'is_body_diode_max_a': {'kind': 'quantity', 'family': 'current',
                                        'positive': True},
                'vf_body_diode_max_v': {'kind': 'quantity', 'family': 'voltage',
                                        'positive': True},
                'body_diode': {'kind': 'string'},
                'soa': {'kind': 'string'},
            },
            'doc': 'Caller-declared MOSFET facts (same shape as devices/SCHEMA.md category '
                   'mosfet_n); tagged user_declared, never a datasheet verification.'},
        'gate_series': {
            'kind': 'enum', 'values': ['E6', 'E12', 'E24', 'E48', 'E96'],
            'default': 'E24',
            'doc': 'Standard series used when a gate resistor target is declared.'},
        'gate_resistor_target': {
            'kind': 'range', 'family': 'resistance', 'positive': True,
            'doc': 'Optional allowed gate series resistor range (ohm); a standard value is '
                   'selected only when this is declared.'},
        'gate_pulldown_value': {
            'kind': 'quantity', 'family': 'resistance', 'positive': True,
            'doc': 'Optional gate pulldown resistor value (ohm). When absent the pulldown is '
                   'emitted as a requirement with its rationale.'},
        'max_gate_drive_current': {
            'kind': 'quantity', 'family': 'current', 'positive': True,
            'doc': 'Optional gate-driver source current limit (A); bounds the gate resistor and '
                   'enables the edge estimate.'},
        'notes': {'kind': 'string', 'doc': 'Free-form note copied into the result.'},
    }
    EXAMPLE_INPUT = {
        'device_fact_id': 'mosfet_ao3400a',
        'load_supply_voltage': {'min': 11.4, 'max': 12.6},
        'load_current_nominal': '0.5A',
        'load_current_max': '0.8A',
        'load_inrush_current': '2.5A',
        'gate_drive_voltage': {'min': 3.135, 'max': 3.465},
        'switching_frequency': '20kHz',
        'inductive_load': True,
        'load_inductance': '1mH',
        'ambient_temperature': {'min': 0, 'max': 40},
        'gate_series': 'E24',
        'gate_resistor_target': {'min': 10, 'max': 100},
        'gate_pulldown_value': '10k',
        'max_gate_drive_current': '100mA',
    }

    # ------------------------------------------------------------------
    def compute(self, draft, inputs):
        notes = inputs.get('notes')
        supply = inputs.interval('load_supply_voltage')
        current_nominal = inputs.quantity('load_current_nominal')
        current_max = inputs.quantity('load_current_max')
        inrush = _optional_quantity(inputs, 'load_inrush_current')
        gate = inputs.interval('gate_drive_voltage')
        inductive = inputs.boolean('inductive_load')
        ambient = inputs.get('ambient_temperature')

        if current_max < current_nominal:
            raise InputInvalid('load_current_max must not be below load_current_nominal',
                               field='load_current_max')
        if inrush is not None and inrush < current_max:
            raise InputInvalid('load_inrush_current must not be below load_current_max',
                               field='load_inrush_current')

        frequency = self._switching(inputs)
        switching = frequency is not None and frequency > 0
        if switching and inductive and 'load_inductance' not in inputs \
                and 'load_energy_mj' not in inputs:
            raise NeedsDeviceFacts(
                ['load_inductance or load_energy_mj'],
                'an inductive load that is switched needs a declared inductance or energy: the '
                'freewheel diode pulse/avalanche capability cannot be sized from an unquantified '
                'energy')

        facts = self._load_facts(inputs)
        missing = missing_keys(facts, _REQUIRED_FACTS)
        if missing:
            raise NeedsDeviceFacts(
                missing,
                'MOSFET facts are required before any on-state, voltage or current claim: '
                + ', '.join(missing))
        vds_max = _fact_number(facts, 'vds_max_v')
        vgss_max = _fact_number(facts, 'vgss_max_v')
        id_max = _fact_number(facts, 'id_max_a')
        vgs_th_max = _fact_number(facts, 'vgs_th_max_v')
        pulse_rating = _fact_optional_number(facts, 'id_pulsed_max_a')

        # -- absolute maximum checks ---------------------------------
        if gate.hi > vgss_max:
            raise NoFeasibleSolution(
                'gate drive worst case %s V exceeds the MOSFET absolute maximum VGS %s V'
                % (format_number(gate.hi), format_number(vgss_max)),
                bounds={'gate_drive_max': to_json_number(gate.hi),
                        'vgss_max': to_json_number(vgss_max)})
        if vgs_th_max >= gate.lo:
            raise NoFeasibleSolution(
                'the minimum gate drive %s V does not exceed the worst-case threshold %s V: the '
                'MOSFET is not guaranteed to enhance at the declared drive'
                % (format_number(gate.lo), format_number(vgs_th_max)),
                bounds={'gate_drive_min': to_json_number(gate.lo),
                        'vgs_th_max': to_json_number(vgs_th_max)})
        if supply.hi > vds_max:
            raise NoFeasibleSolution(
                'load supply maximum %s V exceeds the MOSFET VDS maximum %s V'
                % (format_number(supply.hi), format_number(vds_max)),
                bounds={'load_supply_max': to_json_number(supply.hi),
                        'vds_max': to_json_number(vds_max)})
        if current_max > id_max:
            raise NoFeasibleSolution(
                'maximum load current %s A exceeds the MOSFET continuous drain rating %s A'
                % (format_number(current_max), format_number(id_max)),
                bounds={'load_current_max': to_json_number(current_max),
                        'id_max': to_json_number(id_max)})

        # -- RDS(on) at the actual gate drive ------------------------
        row = self._select_rds_row(facts, gate.lo)
        rds_on = row['rds_on']
        typical_only = row['typical_only']
        conduction = current_max * current_max * rds_on
        conduction_nominal = current_nominal * current_nominal * rds_on

        # -- optional thermal facts ----------------------------------
        pd_max = _fact_optional_number(facts, 'pd_max_w')
        theta_ja = _fact_optional_number(facts, 'theta_ja_c_per_w')
        tj_max = _fact_optional_number(facts, 'tj_max_c')
        thermal_facts = (theta_ja is not None and tj_max is not None)
        junction_estimate = None
        if not switching and thermal_facts and ambient is not None:
            junction_estimate = ambient.hi + conduction * theta_ja
            if junction_estimate > tj_max:
                raise NoFeasibleSolution(
                    'estimated junction temperature %s degC (TA_max=%s degC + P_cond*theta_JA) '
                    'exceeds TJ(max)=%s degC under the datasheet reference-board condition; this '
                    'is an estimate, not a board measurement, but it already fails the static '
                    'check'
                    % (format_number(junction_estimate), format_number(ambient.hi),
                       format_number(tj_max)),
                    bounds={'estimated_tj_degc': to_json_number(junction_estimate),
                            'tj_max_degc': to_json_number(tj_max)})
        if pd_max is not None and not switching and thermal_facts and conduction > pd_max:
            raise NoFeasibleSolution(
                'conduction loss %s W exceeds the declared package dissipation rating %s W in DC '
                'operation' % (format_number(conduction), format_number(pd_max)),
                bounds={'conduction_loss_w': to_json_number(conduction),
                        'pd_max_w': to_json_number(pd_max)})

        # -- inrush / pulse rating -----------------------------------
        pulse_margin = None
        if inrush is not None and pulse_rating is not None:
            pulse_margin = pulse_rating - inrush
            if pulse_margin < 0:
                raise NoFeasibleSolution(
                    'inrush current %s A exceeds the MOSFET pulsed drain rating %s A'
                    % (format_number(inrush), format_number(pulse_rating)),
                    bounds={'inrush_a': to_json_number(inrush),
                            'id_pulsed_max_a': to_json_number(pulse_rating)})

        # -- gate network --------------------------------------------
        gate_resistor_value = self._select_gate_resistor(inputs, gate)
        gate_peak_current = None
        if gate_resistor_value is not None:
            gate_peak_current = gate.hi / gate_resistor_value
        max_drive_current = _optional_quantity(inputs, 'max_gate_drive_current')
        pulldown_value = _optional_quantity(inputs, 'gate_pulldown_value')

        # -- inductive clamp -----------------------------------------
        freewheel = None
        if inductive:
            freewheel = self._freewheel_requirements(inputs, supply, current_max, inrush,
                                                     switching)

        # ---- components -------------------------------------------
        mosfet = draft.component(
            'low_side_switch', 'mosfet', value=None, polarity='n_channel',
            voltage_rating_v=supply.hi,
            pins=[{'name': 'G', 'semantic': 'gate'},
                  {'name': 'D', 'semantic': 'drain'},
                  {'name': 'S', 'semantic': 'source'}],
            requirements={
                'vds_min': quantity_json(supply.hi, 'voltage'),
                'id_min': quantity_json(current_max, 'current'),
                'rds_on_max_at_or_below_vgs': quantity_json(rds_on, 'resistance'),
                'gate_drive': gate.as_json('voltage'),
                'device_fact_id': facts.get('fact_id'),
                'evaluated_mpn': facts.get('mpn'),
                'evaluated_by': 'bundled verified fact' if facts.get('verified')
                                else 'caller-declared facts',
            },
            notes='Abstract N-MOSFET requirement; the evaluated device is a candidate only, no '
                  'MPN is bound.')
        gate_resistor = None
        if gate_resistor_value is not None:
            gate_resistor = draft.component(
                'gate_series', 'resistor', value=gate_resistor_value,
                series=inputs.get('gate_series'),
                power_rating_w=gate.hi * gate.hi / gate_resistor_value,
                voltage_rating_v=gate.hi,
                pins=[{'name': '1', 'semantic': 'driver_side'},
                      {'name': '2', 'semantic': 'gate_side'}],
                requirements={
                    'peak_gate_current': quantity_json(gate_peak_current, 'current'),
                    'target_range': inputs.get('gate_resistor_target').as_json('resistance'),
                },
                notes='Standard gate series resistor; it limits the peak gate current and damps '
                      'the gate loop.')
        pulldown = draft.component(
            'gate_pulldown', 'resistor', value=pulldown_value,
            voltage_rating_v=gate.hi,
            pins=[{'name': '1', 'semantic': 'gate_side'},
                  {'name': '2', 'semantic': 'ground_side'}],
            requirements={
                'purpose': 'holds the gate at 0 V when the driver is high-impedance',
                'value': (quantity_json(pulldown_value, 'resistance')
                          if pulldown_value is not None
                          else 'to be selected so the pulldown loading is negligible relative to '
                               'the gate drive and the fail-safe turn-off is acceptable'),
            },
            notes='Gate pulldown is emitted with its rationale; the value is a requirement when '
                  'the caller did not declare one.')
        freewheel_diode = None
        if freewheel is not None:
            freewheel_diode = draft.component(
                'freewheel_diode', 'diode', value=None, polarity='anode_cathode',
                voltage_rating_v=freewheel['reverse_voltage'],
                pins=[{'name': 'A', 'semantic': 'anode'},
                      {'name': 'K', 'semantic': 'cathode'}],
                requirements=freewheel['requirements'],
                notes='Abstract freewheel diode requirement for the inductive load; no diode MPN '
                      'is chosen or invented.')

        # ---- nets, ports, endpoints --------------------------------
        vload = draft.net('VLOAD', role='power', scope='external',
                          voltage_domain='load_supply')
        sw = draft.net('SW', role='switch', scope='external', voltage_domain='switched_load',
                       notes='Switched low-side node between the load and the MOSFET drain')
        gate_net = draft.net('GATE', role='signal', scope='external', voltage_domain='logic',
                             notes='Gate control input at the module boundary')
        gnd = draft.net('GND', role='ground', scope='external')
        gate_node = gate_net
        if gate_resistor is not None:
            gate_node = draft.net('GATE_IN', role='signal', scope='internal',
                                  voltage_domain='logic',
                                  notes='MOSFET gate node after the series resistor')

        draft.connect(mosfet['ref'], 'D', sw, 'drain')
        draft.connect(mosfet['ref'], 'S', gnd, 'source')
        draft.connect(mosfet['ref'], 'G', gate_node, 'gate')
        if gate_resistor is not None:
            draft.connect(gate_resistor['ref'], '1', gate_net, 'driver_side')
            draft.connect(gate_resistor['ref'], '2', gate_node, 'gate_side')
        draft.connect(pulldown['ref'], '1', gate_node, 'gate_side')
        draft.connect(pulldown['ref'], '2', gnd, 'ground_side')
        if freewheel_diode is not None:
            draft.connect(freewheel_diode['ref'], 'A', sw, 'anode')
            draft.connect(freewheel_diode['ref'], 'K', vload, 'cathode')

        peak_switch_current = inrush if inrush is not None else current_max
        draft.port('VLOAD', 'input', 'power', net=vload, voltage=supply,
                   current=Interval(Fraction(0), current_max),
                   description='Load supply input')
        draft.port('SW', 'output', 'switch', net=sw,
                   voltage=Interval(Fraction(0), supply.hi),
                   current=Interval(Fraction(0), peak_switch_current),
                   description='Switched low-side node (load return); clamped by the freewheel '
                               'diode when the load is inductive')
        draft.port('GATE', 'input', 'digital', net=gate_net, voltage=gate,
                   current=(Interval.point(gate_peak_current)
                            if gate_peak_current is not None else None),
                   description='Gate control input')
        draft.port('GND', 'passive', 'ground', net=gnd, description='Power ground return')

        # ---- calculations -----------------------------------------
        self._write_calculations(draft, inputs, facts, gate, supply, current_nominal,
                                 current_max, inrush, switching, frequency, row, rds_on,
                                 typical_only, conduction, conduction_nominal, vds_max,
                                 vgss_max, id_max, vgs_th_max, pulse_rating, pulse_margin,
                                 pd_max, theta_ja, tj_max, thermal_facts, ambient,
                                 junction_estimate, gate_resistor_value, gate_peak_current,
                                 max_drive_current, pulldown_value, freewheel, inductive)
        return 'ready_abstract', [], notes

    # ------------------------------------------------------------------
    @staticmethod
    def _switching(inputs):
        frequency = _optional_quantity(inputs, 'switching_frequency')
        dc = inputs.get('dc_operation')
        if dc is None and frequency is None:
            raise InputInvalid(
                'declare either switching_frequency or dc_operation=true',
                field='switching_frequency')
        if dc is True and frequency is not None:
            raise InputInvalid('dc_operation=true contradicts a declared switching_frequency',
                               field='dc_operation')
        if dc is False and frequency is None:
            raise InputInvalid('dc_operation=false requires switching_frequency',
                               field='switching_frequency')
        return frequency

    @staticmethod
    def _load_facts(inputs):
        has_id = inputs.get('device_fact_id') is not None
        has_payload = inputs.get('device_facts') is not None
        if has_id and has_payload:
            raise InputInvalid('declare device_fact_id or device_facts, not both',
                               field='device_fact_id')
        if not has_id and not has_payload:
            raise NeedsDeviceFacts(
                ['device_facts or device_fact_id'],
                'MOSFET data is required: declare a bundled verified device_fact_id or '
                'caller-declared device_facts')
        if has_id:
            facts = load_fact(inputs.string('device_fact_id'))
            if facts.get('category') != 'mosfet_n':
                raise InputInvalid(
                    'device_fact_id %r is category %r, not mosfet_n'
                    % (facts.get('fact_id'), facts.get('category')),
                    field='device_fact_id')
            facts.setdefault('verified', True)
            return facts
        payload = inputs.obj('device_facts').as_json()
        return user_declared_facts(payload, 'mosfet_n',
                                   source_note='caller-declared MOSFET facts')

    @staticmethod
    def _select_rds_row(facts, gate_min):
        record = facts.get('facts', {}).get('rds_on_ohm')
        rows = None
        if isinstance(record, dict) and 'value' in record:
            rows = record['value']
        elif isinstance(record, list):
            rows = record
        if not rows:
            raise NeedsDeviceFacts(['rds_on_ohm (list of VGS rows)'],
                                   'RDS(ON) rows are required to prove the on-state at the '
                                   'actual gate drive')
        usable = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            vgs = _fact_row_number(raw.get('vgs_v'))
            if vgs is None:
                continue
            resistance = _fact_row_number(raw.get('max_ohm'))
            typical_only = False
            if resistance is None:
                resistance = _fact_row_number(raw.get('typ_ohm'))
                typical_only = resistance is not None
            if resistance is None or vgs > gate_min:
                continue
            condition = raw.get('condition') if isinstance(raw.get('condition'), str) else ''
            usable.append({'vgs_v': vgs, 'rds_on': resistance,
                           'typical_only': typical_only, 'condition': condition,
                           'room_temperature': _is_room_temperature(condition)})
        if not usable:
            raise NeedsDeviceFacts(
                ['rds_on_ohm row at VGS <= %s V' % format_number(gate_min)],
                'the datasheet does not specify an RDS(ON) row at or below the minimum gate '
                'drive; interpolation upward is not allowed, so the on-state cannot be proven')
        # Highest characterised VGS not above the drive, and the largest resistance
        # on that row (conservative), deterministically ordered.
        usable.sort(key=lambda item: (item['vgs_v'], item['rds_on'],
                                      item['typical_only']))
        return usable[-1]

    # ------------------------------------------------------------------
    @staticmethod
    def _select_gate_resistor(inputs, gate):
        target = inputs.get('gate_resistor_target')
        if target is None:
            return None
        series = inputs.get('gate_series')
        candidates = series_values(series, target.lo, target.hi,
                                   decades=_RESISTOR_DECADES)
        if not candidates:
            raise NoFeasibleSolution(
                'no standard %s resistor exists in the declared gate-resistor target range '
                '%s..%s ohm' % (series, format_number(target.lo), format_number(target.hi)))
        max_drive = _optional_quantity(inputs, 'max_gate_drive_current')
        if max_drive is not None:
            lower = gate.hi / max_drive
            candidates = [value for value in candidates if value >= lower]
            if not candidates:
                raise NoFeasibleSolution(
                    'the declared gate-driver current %s A would be exceeded by every standard '
                    'resistor in the target range: R_gate >= %s ohm is required'
                    % (format_number(max_drive), format_number(lower)),
                    bounds={'required_gate_resistance_ohm': to_json_number(lower)})
        selected = nearest(candidates, target.nominal)
        if selected is None:
            raise NoFeasibleSolution('no standard gate resistor satisfies the declared objective')
        return selected

    # ------------------------------------------------------------------
    def _freewheel_requirements(self, inputs, supply, current_max, inrush, switching):
        inductance = _optional_quantity(inputs, 'load_inductance')
        energy_mj = inputs.get('load_energy_mj')
        energy = None
        if inductance is not None:
            energy = inductance * current_max * current_max / 2
        declared = (Fraction(energy_mj) / 1000) if energy_mj is not None else None
        if declared is not None and (energy is None or declared > energy):
            energy = declared
        requirements = {
            'reverse_voltage_min': quantity_json(supply.hi, 'voltage'),
            'forward_current_min': quantity_json(current_max, 'current'),
            'forward_surge_current_min': (quantity_json(inrush, 'current')
                                          if inrush is not None else None),
            'pulse_energy_min': ({'value': to_json_number(energy), 'unit': 'J'}
                                 if energy is not None else None),
            'clamp_behaviour': 'during turn-off the load current freewheels through the diode; '
                               'the SW node is clamped at VLOAD + VF(diode), not at the '
                               'MOSFET avalanche voltage',
            'reverse_recovery': 'a fast (Schottky or ultrafast) diode is required when the '
                                'switching frequency makes reverse recovery loss significant; '
                                'this is a selection constraint, not a part choice',
        }
        if energy is not None:
            peak = current_max
            requirements['turn_off_peak_current'] = quantity_json(peak, 'current')
        return {
            'reverse_voltage': supply.hi,
            'forward_current': current_max,
            'forward_surge_current': inrush,
            'energy': energy,
            'requirements': requirements,
            'switching': switching,
        }

    # ------------------------------------------------------------------
    def _write_calculations(self, draft, inputs, facts, gate, supply, current_nominal,
                            current_max, inrush, switching, frequency, row, rds_on,
                            typical_only, conduction, conduction_nominal, vds_max,
                            vgss_max, id_max, vgs_th_max, pulse_rating, pulse_margin,
                            pd_max, theta_ja, tj_max, thermal_facts, ambient,
                            junction_estimate, gate_resistor_value, gate_peak_current,
                            max_drive_current, pulldown_value, freewheel, inductive):
        draft.calculation(
            'rds_on_at_drive',
            'Datasheet RDS(ON) row at the actual gate drive',
            'use the highest datasheet VGS row with VGS <= gate_drive_min; never interpolate '
            'upward and never use VGS(th) as the on-state proof',
            inputs={'gate_drive_min': quantity_json(gate.lo, 'voltage'),
                    'selected_row_vgs': quantity_json(row['vgs_v'], 'voltage'),
                    'selected_row_condition': row['condition']},
            result={'rds_on_ohm': to_json_number(rds_on),
                    'used_typical_instead_of_max': typical_only,
                    'room_temperature_only': row.get('room_temperature', False)},
            unit='ohm',
            limit=None,
            margin=None,
            method='tabular selection on the exact VGS condition',
            assumptions=['the datasheet maximum RDS(ON) applies at the declared junction '
                         'temperature'],
            not_modelled=['interpolation between VGS rows',
                          'RDS(ON) temperature coefficient when only a room-temperature row is '
                          'specified'])

        draft.calculation(
            'conduction_loss',
            'Conduction loss at the stated load current',
            'P_cond = I_load^2 * RDS(ON)(VGS);  P_nom and P_max reported separately',
            inputs={'load_current_nominal': quantity_json(current_nominal, 'current'),
                    'load_current_max': quantity_json(current_max, 'current'),
                    'rds_on_ohm': to_json_number(rds_on)},
            result={'power_nominal_w': to_json_number(conduction_nominal),
                    'power_max_w': to_json_number(conduction)},
            unit='W',
            limit={'pd_max_w': (quantity_json(pd_max, 'power') if pd_max is not None
                                else None)},
            margin={'pd_margin_w': (to_json_number(pd_max - conduction)
                                    if pd_max is not None else None)},
            method='exact rational arithmetic',
            assumptions=['the stated RDS(ON) is constant over the conduction interval'],
            not_modelled=['RDS(ON) rise with junction temperature',
                          'switching transition loss'])

        draft.calculation(
            'vds_check',
            'Drain-source voltage rating against the load supply',
            'V_DS_worst = V_load_max <= VDS_max',
            inputs={'load_supply_max': quantity_json(supply.hi, 'voltage'),
                    'vds_max': quantity_json(vds_max, 'voltage')},
            result={'margin_v': to_json_number(vds_max - supply.hi)},
            unit='V',
            limit={'vds_max': quantity_json(vds_max, 'voltage')},
            margin={'margin_v': quantity_json(vds_max - supply.hi, 'voltage')},
            assumptions=['the freewheel diode clamps the inductive turn-off overshoot at the '
                         'load node (when the load is inductive)'],
            not_modelled=['unclamped inductive switching / avalanche beyond the clamp path'])

        draft.calculation(
            'id_check',
            'Continuous drain current rating against the maximum load current',
            'I_load_max <= ID_max',
            inputs={'load_current_max': quantity_json(current_max, 'current'),
                    'id_max': quantity_json(id_max, 'current')},
            result={'margin_a': to_json_number(id_max - current_max)},
            unit='A',
            limit={'id_max': quantity_json(id_max, 'current')},
            margin={'margin_a': quantity_json(id_max - current_max, 'current')},
            assumptions=['the datasheet ID rating applies at the declared ambient/case '
                         'condition'],
            not_modelled=['ID derating with ambient temperature and PCB thermal resistance'])

        draft.calculation(
            'vgs_check',
            'Gate-source absolute maximum check',
            'V_GS_worst = gate_drive_max <= VGSS_max',
            inputs={'gate_drive_max': quantity_json(gate.hi, 'voltage'),
                    'vgss_max': quantity_json(vgss_max, 'voltage')},
            result={'margin_v': to_json_number(vgss_max - gate.hi)},
            unit='V',
            limit={'vgss_max': quantity_json(vgss_max, 'voltage')},
            margin={'margin_v': quantity_json(vgss_max - gate.hi, 'voltage')},
            assumptions=['gate ringing at turn-on/off stays inside the absolute maximum'],
            not_modelled=['inductive gate-loop ringing and clamp diodes'])

        draft.calculation(
            'vgs_th_check',
            'Necessary enhancement check (threshold is not an on-state proof)',
            'gate_drive_min > VGS(th)_max is necessary; the RDS(ON) row above provides the '
            'on-state proof',
            inputs={'gate_drive_min': quantity_json(gate.lo, 'voltage'),
                    'vgs_th_max': quantity_json(vgs_th_max, 'voltage')},
            result={'margin_v': to_json_number(gate.lo - vgs_th_max)},
            unit='V',
            limit={'vgs_th_max': quantity_json(vgs_th_max, 'voltage')},
            margin={'margin_v': quantity_json(gate.lo - vgs_th_max, 'voltage')},
            assumptions=['VGS(th) is used only as a necessary condition, never as proof of '
                         'enhancement or of RDS(ON)'],
            not_modelled=['VGS(th) fall with temperature'])

        if inrush is not None:
            draft.calculation(
                'inrush_check',
                'Inrush current against the pulsed drain rating',
                'I_inrush <= ID_pulsed when the datasheet states a pulse rating',
                inputs={'load_inrush_current': quantity_json(inrush, 'current'),
                        'id_pulsed_max': (quantity_json(pulse_rating, 'current')
                                          if pulse_rating is not None else None)},
                result={'verified': pulse_rating is not None},
                unit='A',
                limit={'id_pulsed_max': (quantity_json(pulse_rating, 'current')
                                         if pulse_rating is not None else None)},
                margin={'margin_a': (to_json_number(pulse_margin)
                                     if pulse_margin is not None else None)},
                assumptions=['the declared inrush event fits inside the pulse-width condition '
                             'of the datasheet pulse rating'],
                not_modelled=['SOA boundary at the inrush voltage/current point',
                              'repetitive pulse thermal impedance'])

        if switching:
            draft.calculation(
                'switching_loss',
                'Switching loss (unverified)',
                'P_sw requires switching times / Qgd / Coss and the drain current/voltage '
                'overlap; those facts are not declared, so no number is fabricated',
                inputs={'switching_frequency': quantity_json(frequency, 'frequency'),
                        'qg_typ': (quantity_json(_fact_optional_number(facts, 'qg_typ_c'),
                                                 'charge')
                                   if _fact_optional_number(facts, 'qg_typ_c') is not None
                                   else None)},
                result={'verified': False,
                        'reason': 'switching loss and the resulting thermal rise are unknown; '
                                  'the conduction-loss result is not a thermal design'},
                unit='W',
                limit=None,
                margin=None,
                assumptions=[],
                not_modelled=['gate charge, Coss/Crss, diode reverse recovery, dead time and '
                              'drain-voltage/current overlap'])
        else:
            draft.calculation(
                'switching_loss',
                'Switching loss in DC operation',
                'dc_operation=true means no repetitive switching transitions',
                inputs={'dc_operation': True},
                result={'verified': True, 'power_w': 0},
                unit='W',
                limit=None,
                margin=None,
                assumptions=['the load is never switched during normal operation'],
                not_modelled=['fault transients that interrupt the load current'])

        if not switching and thermal_facts and ambient is not None:
            draft.calculation(
                'thermal_estimate',
                'Static junction-temperature estimate under the datasheet reference board',
                'T_J = T_A_max + P_cond * theta_JA; P_D and T_J(max) checked',
                inputs={'ambient_max': quantity_json(ambient.hi, 'temperature'),
                        'theta_ja_c_per_w': to_json_number(theta_ja),
                        'conduction_power_w': to_json_number(conduction),
                        'pd_max_w': (quantity_json(pd_max, 'power')
                                     if pd_max is not None else None)},
                result={'estimated_tj_degc': to_json_number(junction_estimate),
                        'tj_margin_degc': to_json_number(tj_max - junction_estimate)},
                unit='degC',
                limit={'tj_max': quantity_json(tj_max, 'temperature')},
                margin={'margin_degc': quantity_json(tj_max - junction_estimate,
                                                     'temperature')},
                method='exact rational arithmetic on the datasheet theta_JA',
                assumptions=['theta_JA is the datasheet reference-board (1 in^2 FR-4, 2 oz '
                             'copper, still air) value',
                             'the conduction loss is the only heat source (DC operation)'],
                not_modelled=['real PCB copper area, airflow, transient thermal impedance and '
                              'solder-joint/board measurements',
                              'a 25 C RDS(ON) row makes the conduction loss a lower bound; the '
                              'real hot-junction value is not modelled'])
        else:
            reasons = []
            if switching:
                reasons.append('switching loss is unknown in switching operation')
            if not thermal_facts:
                reasons.append('theta_JA/TJ(max) are not declared')
            if thermal_facts and ambient is None:
                reasons.append('ambient temperature is not declared')
            draft.calculation(
                'thermal_estimate',
                'Junction-temperature estimate (unverified)',
                'T_J = T_A + P*theta_JA requires both the thermal facts and the ambient '
                'temperature; the result is not a thermal design',
                inputs={'conduction_power_w': to_json_number(conduction),
                        'theta_ja_c_per_w': (to_json_number(theta_ja)
                                             if theta_ja is not None else None),
                        'tj_max_degc': (to_json_number(tj_max) if tj_max is not None else None)},
                result={'verified': False, 'reason': '; '.join(reasons) or 'thermal data '
                        'incomplete'},
                unit='degC',
                limit=None,
                margin=None,
                assumptions=[],
                not_modelled=['junction temperature'])

        qg = _fact_optional_number(facts, 'qg_typ_c')
        ciss = _fact_optional_number(facts, 'ciss_typ_f')
        if gate_resistor_value is not None or pulldown_value is not None:
            draft.calculation(
                'gate_network',
                'Gate series/pulldown network',
                'I_g_peak = V_gate_max/R_gate;  I_pulldown = V_gate_max/R_pulldown;  '
                'tau_failsafe = R_pulldown*Ciss',
                inputs={'gate_drive_max': quantity_json(gate.hi, 'voltage'),
                        'gate_resistance': (quantity_json(gate_resistor_value, 'resistance')
                                            if gate_resistor_value is not None else None),
                        'gate_pulldown_resistance': (quantity_json(pulldown_value, 'resistance')
                                                     if pulldown_value is not None else None),
                        'ciss_typ_f': (quantity_json(ciss, 'capacitance')
                                       if ciss is not None else None)},
                result={'peak_gate_current_a': (to_json_number(gate_peak_current)
                                                if gate_peak_current is not None else None),
                        'pulldown_current_a': (to_json_number(gate.hi / pulldown_value)
                                              if pulldown_value is not None else None),
                        'failsafe_gate_discharge_s': (to_json_number(pulldown_value * ciss)
                                                      if (pulldown_value is not None
                                                          and ciss is not None) else None)},
                unit='A',
                limit={'max_gate_drive_current': (quantity_json(max_drive_current, 'current')
                                                  if max_drive_current is not None else None)},
                margin={'gate_current_margin_a': (to_json_number(max_drive_current -
                                                                  gate_peak_current)
                                                  if (max_drive_current is not None
                                                      and gate_peak_current is not None)
                                                  else None)},
                assumptions=['the gate is a lumped capacitance Ciss for the fail-safe estimate'],
                not_modelled=['gate-loop ringing, Miller plateau duration and driver '
                              'non-linearity'])

        if qg is not None and (gate_peak_current is not None or max_drive_current is not None):
            drive_current = gate_peak_current if gate_peak_current is not None \
                else max_drive_current
            draft.calculation(
                'gate_edge_estimate',
                'Gate edge-time estimate from gate charge and drive current',
                't_edge ~= Qg / I_drive (linear-current estimate only)',
                inputs={'qg_typ_c': quantity_json(qg, 'charge'),
                        'drive_current': quantity_json(drive_current, 'current')},
                result={'edge_time_s': to_json_number(qg / drive_current)},
                unit='s',
                limit=None,
                margin=None,
                assumptions=['constant drive current and a single lumped gate charge'],
                not_modelled=['Miller plateau, gate resistor/driver output impedance, '
                              'temperature dependence'])
            if switching:
                draft.calculation(
                    'gate_drive_power',
                    'Average gate-drive power',
                    'P_gate = Qg * V_gate * f_sw',
                    inputs={'qg_typ_c': quantity_json(qg, 'charge'),
                            'gate_drive_max': quantity_json(gate.hi, 'voltage'),
                            'switching_frequency': quantity_json(frequency, 'frequency')},
                    result={'power_w': to_json_number(qg * gate.hi * frequency)},
                    unit='W',
                    limit=None,
                    margin=None,
                    assumptions=['Qg is the total gate charge at the declared drive'],
                    not_modelled=['driver quiescent and cross-conduction losses'])

        if freewheel is not None:
            energy = freewheel['energy']
            draft.calculation(
                'freewheel_requirements',
                'Freewheel diode voltage/current/pulse conditions',
                'V_R >= V_load_max;  I_F >= I_load_max;  I_FSM >= I_inrush;  '
                'E_clamp >= 0.5*L*I_turn_off^2 (or the declared energy)',
                inputs={'load_supply_max': quantity_json(supply.hi, 'voltage'),
                        'load_current_max': quantity_json(current_max, 'current'),
                        'load_inrush_current': (quantity_json(inrush, 'current')
                                                if inrush is not None else None),
                        'load_energy_j': (to_json_number(energy) if energy is not None
                                          else None)},
                result={'reverse_voltage_min_v': to_json_number(supply.hi),
                        'forward_current_min_a': to_json_number(current_max),
                        'forward_surge_current_min_a': (to_json_number(inrush)
                                                        if inrush is not None else None),
                        'pulse_energy_min_j': (to_json_number(energy) if energy is not None
                                               else None)},
                unit='J',
                limit=None,
                margin=None,
                assumptions=['the freewheel diode carries the full load current during '
                             'turn-off and clamps the SW node at VLOAD + VF'],
                not_modelled=['diode reverse recovery loss, junction capacitance ringing and '
                              'the diode thermal design'])
            draft.constraint(
                'freewheel_diode',
                'A freewheel diode is mandatory across the inductive load: reverse voltage '
                '>= %s V, forward current >= %s A%s, and it must absorb the turn-off pulse '
                'energy; the diode clamps SW at VLOAD + VF, so the MOSFET is not used for '
                'avalanche clamping.'
                % (format_number(supply.hi), format_number(current_max),
                   (', surge current >= %s A' % format_number(inrush)
                    if inrush is not None else '')),
                kind='hard', applies_to=freewheel_diode_ref(draft), source='derivation',
                rationale='without the freewheel path the inductive energy would be forced '
                          'into the MOSFET, which is not rated for unclamped inductive '
                          'switching')
            if energy is None:
                draft.unknown(
                    'clamp_energy_unverified',
                    'The inductive energy was not declared, so the diode pulse/avalanche '
                    'energy requirement is unknown.',
                    impact='a diode with insufficient surge energy may fail on the first '
                           'interruption',
                    how_to_resolve='declare load_inductance or load_energy_mj and re-check the '
                                   'diode pulse capability')
            else:
                draft.constraint(
                    'freewheel_energy',
                    'The freewheel diode pulse/avalanche energy capability must be at least %s J '
                    'at the declared turn-off current.' % format_number(energy),
                    kind='hard', applies_to=freewheel_diode_ref(draft), source='derivation')

        # ---- constraints and unknowns ------------------------------
        draft.constraint('rds_on_selection',
                         'The selected part must specify a maximum RDS(ON) at VGS <= %s V; a '
                         'typical-only value cannot prove the on-state.' % format_number(gate.lo),
                         kind='hard', applies_to='Q1', source='derivation')
        draft.constraint('vds_rating',
                         'VDS maximum must be at least %s V.' % format_number(supply.hi),
                         kind='hard', applies_to='Q1', source='derivation')
        draft.constraint('id_rating',
                         'Continuous drain current rating must be at least %s A.'
                         % format_number(current_max),
                         kind='hard', applies_to='Q1', source='derivation')
        draft.constraint('vgs_rating',
                         'VGSS maximum must be at least the worst-case gate drive %s V.'
                         % format_number(gate.hi),
                         kind='hard', applies_to='Q1', source='derivation')
        if gate_resistor_value is not None:
            draft.constraint('gate_resistor_value',
                             'Use a %s ohm standard gate series resistor unless the gate-loop '
                             'verification shows a different value is required.'
                             % format_number(gate_resistor_value),
                             kind='hard', applies_to='R_gate', source='derivation')
        draft.constraint(
            'gate_pulldown_rationale',
            'The gate pulldown is required so the MOSFET stays off while the driver is '
            'high-impedance (power-up, reset, fault). Its current loading (V_gate_max/R_pd) must '
            'stay negligible relative to the gate drive, and its fail-safe discharge time '
            'R_pd*Ciss must fit the system requirement%s.'
            % ('' if pulldown_value is not None
               else '; the value must be selected and verified'),
            kind='advisory', applies_to='R_pulldown', source='derivation')
        draft.constraint('thermal_verify',
                         'The junction temperature is not proven: theta_JA is a datasheet '
                         'reference-board estimate, and switching loss is unknown in switching '
                         'operation. Measure the case/board temperature on the assembled design.',
                         kind='verification', applies_to='Q1', source='derivation')
        draft.constraint('switching_verify',
                         'Verify the switching waveform (VDS, ID, gate) and the resulting loss on '
                         'the bench; the static calculation is not a switching or thermal proof.',
                         kind='verification', applies_to='Q1', source='derivation')
        if switching:
            draft.constraint('soa_verify',
                             'Check the draining current/voltage trajectory against the '
                             'datasheet safe-operating-area and transient thermal impedance for '
                             'the actual pulse widths.',
                             kind='verification', applies_to='Q1', source='derivation')
        draft.constraint('gate_loop_layout',
                         'Keep the gate loop (driver -> R_gate -> gate -> source) short and '
                         'return the source directly to the driver ground; the power loop '
                         'VLOAD -> load -> FET -> GND must be compact.',
                         kind='layout', applies_to='Q1/R_gate', source='derivation')

        # ---- evidence ---------------------------------------------
        evidence_keys = [key for key in _REQUIRED_FACTS + _OPTIONAL_FACTS
                         if key in (facts.get('facts') or {})
                         and not isinstance((facts.get('facts') or {}).get(key), list)]
        evidence_for(draft, facts, evidence_keys, evidence_prefix='mosfet_fact')
        rows = (facts.get('facts') or {}).get('rds_on_ohm')
        row_count = len(rows) if isinstance(rows, list) else 0
        draft.evidence(
            'mosfet_fact_rds_on_rows', 'manufacturer_datasheet' if facts.get('verified')
            else 'user_declared',
            'RDS(ON) table: %d VGS rows; the row at VGS=%s V with RDS(ON)=%s ohm was selected '
            'for the actual gate drive.' % (row_count, format_number(row['vgs_v']),
                                            format_number(rds_on)),
            source={'document': (facts.get('sources') or [{}])[0].get('document'),
                    'condition': row['condition']},
            applies_to='Q1', verified=bool(facts.get('verified')))
        draft.evidence('load_declared', 'user_declared',
                       'Load supply %s..%s V, nominal/max current %s/%s A%s declared by the '
                       'caller.' % (format_number(supply.lo), format_number(supply.hi),
                                    format_number(current_nominal),
                                    format_number(current_max),
                                    (', inrush %s A' % format_number(inrush))
                                    if inrush is not None else ''),
                       source={'document': 'caller declaration'}, applies_to='VLOAD/SW',
                       verified=False)
        draft.evidence('gate_declared', 'user_declared',
                       'Gate drive range %s..%s V declared by the caller.'
                       % (format_number(gate.lo), format_number(gate.hi)),
                       source={'document': 'caller declaration'}, applies_to='GATE',
                       verified=False)
        draft.evidence('switching_declared', 'user_declared',
                       ('switching frequency %s Hz declared by the caller'
                        % format_number(frequency)) if switching else
                       'dc_operation=true declared by the caller (no repetitive switching)',
                       source={'document': 'caller declaration'}, applies_to='GATE',
                       verified=False)
        draft.evidence('standard_series', 'standard',
                       'Gate-series resistor values taken from IEC 60063 series %s.'
                       % inputs.get('gate_series'),
                       source={'document': 'IEC 60063', 'section': 'preferred number series',
                               'url': 'https://webstore.iec.ch/publication/593'})
        draft.evidence('derivation_math', 'derivation',
                       'Conduction loss, voltage/current/gate checks, thermal estimate, gate '
                       'network and freewheel conditions are derived here with exact rational '
                       'arithmetic.')
        draft.assumption('The declared RDS(ON) row bounds the on-state over the operating '
                         'temperature range it states; a room-temperature-only row does not '
                         'bound a hot junction.',
                         impact='conduction loss may be underestimated at high junction '
                                'temperature')
        draft.assumption('The gate drive range bounds the actual VGS at the die, ignoring '
                         'gate-loop ringing and driver output impedance.',
                         impact='a gate waveform that overshoots or droops invalidates the '
                                'selected RDS(ON) row')
        if switching:
            draft.unknown('switching_loss_unverified',
                          'Switching loss is unknown: the required switching-time/Qgd/Coss '
                          'facts or pulse waveforms were not supplied.',
                          impact='total dissipation and junction temperature are not bounded',
                          how_to_resolve='supply the switching facts or measure VDS/ID at the '
                                         'actual gate drive and frequency')
        else:
            draft.unknown('fault_transient_unverified',
                          'DC operation is assumed; fault or disable transients that interrupt '
                          'the load current are not modelled.',
                          impact='a fault-time inductive pulse may exceed the freewheel path',
                          how_to_resolve='verify the fault/disable turn-off path and the '
                                         'freewheel pulse rating')
        if not thermal_facts:
            draft.unknown('thermal_facts_missing',
                          'theta_JA / TJ(max) thermal facts are not declared, so no junction '
                          'temperature can be estimated.',
                          impact='the package thermal adequacy is unverified',
                          how_to_resolve='declare the datasheet thermal facts, or measure the '
                                         'assembled board')
        elif ambient is None:
            draft.unknown('ambient_temperature_missing',
                          'The ambient temperature range is not declared, so no junction '
                          'temperature can be estimated.',
                          impact='the thermal estimate cannot be anchored to a real ambient',
                          how_to_resolve='declare ambient_temperature for the application')
        draft.unknown('thermal_board_condition',
                      'The theta_JA value is the datasheet reference-board condition, not the '
                      'user PCB; no board temperature is guaranteed.',
                      impact='the real junction temperature depends on copper area and airflow',
                      how_to_resolve='measure the board/case temperature on the assembled design')
        if pulse_rating is None:
            draft.unknown('pulse_rating_missing',
                          'No pulsed drain-current rating was declared; inrush and short-pulse '
                          'operation are unverified.',
                          impact='an inrush transient may exceed the safe operating area',
                          how_to_resolve='declare the datasheet pulsed current and SOA facts')
        if typical_only:
            draft.unknown('rds_on_typical_only',
                          'The selected RDS(ON) row states only a typical value; it is used as an '
                          'estimate and cannot prove a worst-case on-state.',
                          impact='the real conduction loss may be higher than the estimate',
                          how_to_resolve='supply a datasheet maximum RDS(ON) at or below the '
                                         'minimum gate drive')
        if row.get('room_temperature'):
            draft.unknown(
                'rds_on_room_temperature_only',
                'The selected RDS(ON) row is stated at TJ = 25 C only; the conduction loss is a '
                'lower-bound estimate and the junction-temperature rise is unverified.',
                impact='at a hot junction the real RDS(ON) and conduction loss are higher than '
                       'the estimate',
                how_to_resolve='supply a hot-junction RDS(ON) maximum at the actual gate drive, '
                               'or measure the on-state loss on the assembled board')
        if inductive and freewheel is not None and freewheel['energy'] is None:
            draft.unknown('clamp_energy_missing',
                          'The inductive energy is unknown, so the freewheel diode pulse energy '
                          'capability cannot be sized.',
                          impact='the diode may be undersized for the interruption energy',
                          how_to_resolve='declare load_inductance or load_energy_mj')
        if not inductive:
            draft.constraint('resistive_load_assumption',
                             'The caller declared a non-inductive load; a hidden inductive '
                             'component (wiring, relay coil, motor) would require the freewheel '
                             'path and invalidate this assumption.',
                             kind='verification', applies_to='VLOAD/SW', source='declaration')


def freewheel_diode_ref(draft):
    refs = draft.refs('freewheel_diode')
    return refs[0] if refs else 'D1'


def _optional_quantity(inputs, name):
    return inputs.quantity(name) if name in inputs else None


def _is_room_temperature(condition):
    """True when a datasheet row is stated at 25 C (not at a hot junction)."""
    text = (condition or '').lower().replace('°', ' ')
    if '125' in text or '150' in text:
        return False
    return '25' in text or 'room' in text


def _fact_row_number(value):
    """Parse a fact-table cell that may be a bare number or a quantity object."""
    if value is None:
        return None
    if isinstance(value, dict):
        if 'value' not in value:
            return None
        value = value['value']
    if isinstance(value, bool):
        return None
    try:
        return parse_number(value)
    except InputInvalid:
        return None


def _fact_number(facts, key):
    record = fact(facts, key)
    if isinstance(record, dict) and 'value' in record:
        return parse_number(record['value'])
    return parse_number(record)


def _fact_optional_number(facts, key):
    record = (facts.get('facts') or {}).get(key)
    if record is None:
        return None
    if isinstance(record, dict):
        record = record.get('value')
    try:
        return parse_number(record)
    except InputInvalid:
        return None
