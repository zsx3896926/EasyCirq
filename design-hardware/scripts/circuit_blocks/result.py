"""Result envelope construction for one module instance.

Modules describe components, ports, abstract nets, endpoint connections,
calculations, constraints, evidence and unknowns through :class:`Draft`.  The
draft enforces the cross-references (an endpoint must name a declared net, a
net id must be namespaced by the instance, a ref must be unique) and computes
the content hash, so a module cannot emit a result whose connection list and
net table disagree.

Everything here is abstract: a component is a *role with requirements*, never a
bound library part.  ``binding`` is a fixed NOT RUN block until a later layer
binds a real library footprint and host-verifies it.
"""
from __future__ import annotations

from fractions import Fraction

from . import RESULT_SCHEMA, TOOL_NAME, __version__
from .canonical import content_hash, payload_of
from .errors import InputInvalid
from .numeric import to_json_number
from .units import canonical_unit, quantity_json

STATUSES = ('ready_abstract', 'needs_device_facts', 'unsupported', 'input_invalid')

VALIDATION_LEVELS = {
    'math_and_connection_contract': 'pass',
    'device_fact_verification': 'partial',
    'part_binding': 'NOT RUN',
    'library_binding': 'NOT RUN',
    'host_validation': 'NOT RUN',
    'physical_validation': 'NOT RUN',
    'real_eda': 'NOT RUN',
}

_PREFIX_BY_KIND = {
    'resistor': 'R', 'capacitor': 'C', 'inductor': 'L', 'diode': 'D',
    'led': 'D', 'transistor': 'Q', 'mosfet': 'Q', 'ic': 'U', 'connector': 'J',
    'switch': 'SW', 'test_point': 'TP', 'ferrite': 'FB', 'crystal': 'Y',
    'fuse': 'F', 'varistor': 'RV', 'header': 'J',
}


def _nonempty_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise InputInvalid('non-empty string required', field=field)
    return value.strip()


class Draft(object):
    """Mutable result under construction; call :meth:`finish` exactly once."""

    def __init__(self, module_type, template_version, instance_id, display_name,
                 normalized_inputs, input_schema):
        self.module_type = _nonempty_string(module_type, 'module_type')
        self.template_version = _nonempty_string(template_version, 'template_version')
        self.instance_id = _validate_namespace(instance_id)
        self.display_name = display_name or self.instance_id
        self.inputs = normalized_inputs
        self.input_schema = input_schema
        self._components = []
        self._ports = []
        self._nets = []
        self._connections = []
        self._calculations = []
        self._constraints = []
        self._evidence = []
        self._unknowns = []
        self._assumptions = []
        self._counters = {}
        self._finished = False

    # -- identity -------------------------------------------------------
    @property
    def instance_id(self):
        return self._instance_id

    @instance_id.setter
    def instance_id(self, value):
        value = _validate_namespace(value)
        self._instance_id = value

    # -- components -----------------------------------------------------
    def component(self, role, kind, *, value=None, value_unit=None,
                  tolerance_pct=None, series=None, power_rating_w=None,
                  voltage_rating_v=None, polarity='none', pins=None,
                  mpn=None, library_id=None, requirements=None,
                  candidates=None, notes=None, prefix=None):
        """Declare one abstract component and return its result dict.

        ``value``/``power_rating_w``/``voltage_rating_v`` are Fractions in
        ohm/W/V or ``None`` when the module only states a requirement.
        """
        kind = _nonempty_string(kind, 'component.kind')
        role = _nonempty_string(role, 'component.role')
        prefix = prefix or _PREFIX_BY_KIND.get(kind, 'X')
        prefix = _nonempty_string(prefix, 'component.prefix')
        index = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = index
        ref = '%s%d' % (prefix, index)
        pins = pins or [{'name': '1', 'semantic': 'passive'}, {'name': '2', 'semantic': 'passive'}]
        entry = {
            'ref': ref,
            'role': role,
            'kind': kind,
            'value': _value_json(value, value_unit or _value_unit_for_kind(kind)),
            'tolerance': ({'pct': to_json_number(Fraction(tolerance_pct))}
                          if tolerance_pct is not None else None),
            'series': series,
            'power_rating': (quantity_json(power_rating_w, 'power') if power_rating_w is not None else None),
            'voltage_rating': (quantity_json(voltage_rating_v, 'voltage') if voltage_rating_v is not None else None),
            'polarity': polarity,
            'pins': [{'name': str(pin['name']), 'semantic': str(pin['semantic'])} for pin in pins],
            'candidates': [_value_json(candidate, _value_unit_for_kind(kind)) for candidate in (candidates or [])],
            'mpn': mpn,
            'library_id': library_id,
            'binding': 'unbound',
            'requirements': requirements or {},
            'notes': notes,
        }
        self._components.append(entry)
        return entry

    def refs(self, role=None):
        return [component['ref'] for component in self._components
                if role is None or component['role'] == role]

    def _component(self, ref):
        for component in self._components:
            if component['ref'] == ref:
                return component
        return None

    # -- nets and ports -------------------------------------------------
    def net(self, name, *, role='signal', scope='internal', voltage_domain=None,
            notes=None):
        """Declare (or reuse) an abstract net; returns its namespaced id."""
        name = _nonempty_string(name, 'net.name')
        if any(character in name for character in ':/ '):
            raise InputInvalid('net name must be a simple identifier: %r' % name)
        net_id = '%s:%s' % (self._instance_id, name)
        existing = self._net(net_id)
        if existing is not None:
            return net_id
        entry = {
            'id': net_id,
            'name': name,
            'role': role,
            'scope': scope,
            'voltage_domain': voltage_domain,
            'notes': notes,
        }
        self._nets.append(entry)
        return net_id

    def _net(self, net_id):
        for net in self._nets:
            if net['id'] == net_id:
                return net
        return None

    def port(self, port_id, direction, role, *, net, voltage=None, current=None,
             logic=None, description=None, notes=None):
        """Declare an external port bound to a declared net."""
        port_id = _nonempty_string(port_id, 'port.id')
        if any(character in port_id for character in ':/ '):
            raise InputInvalid('port id must be a simple identifier: %r' % port_id)
        if direction not in ('input', 'output', 'bidirectional', 'passive'):
            raise InputInvalid('port direction must be input/output/bidirectional/passive')
        if role not in ('power', 'ground', 'analog', 'digital', 'open_drain',
                        'switch', 'reference'):
            raise InputInvalid('port role must be power/ground/analog/digital/open_drain/switch/reference')
        if self._net(net) is None:
            raise InputInvalid('port %s references undeclared net %r' % (port_id, net))
        if any(port['id'] == port_id for port in self._ports):
            raise InputInvalid('duplicate port id %r' % port_id)
        entry = {
            'id': port_id,
            'direction': direction,
            'role': role,
            'net': net,
            'voltage': _range_json(voltage, 'voltage'),
            'current': _range_json(current, 'current'),
            'logic': logic,
            'description': description,
            'notes': notes,
        }
        self._ports.append(entry)
        return entry

    def connect(self, ref, pin, net_id, semantic=None):
        """Bind one component pin to a declared net."""
        component = self._component(ref)
        if component is None:
            raise InputInvalid('connection references undeclared component %r' % ref)
        pin = str(pin)
        if pin not in [item['name'] for item in component['pins']]:
            raise InputInvalid('component %s has no pin %r' % (ref, pin))
        if self._net(net_id) is None:
            raise InputInvalid('connection references undeclared net %r' % net_id)
        for connection in self._connections:
            if connection['component'] == ref and connection['pin'] == pin:
                raise InputInvalid('duplicate endpoint %s.%s' % (ref, pin))
        entry = {
            'component': ref,
            'pin': pin,
            'pin_semantic': semantic or _pin_semantic(component, pin),
            'net': net_id,
            'state': 'connected',
        }
        self._connections.append(entry)
        return entry

    def no_connect(self, ref, pin, reason):
        """Declare a physical pin explicitly not connected."""
        component = self._component(ref)
        if component is None:
            raise InputInvalid('no_connect references undeclared component %r' % ref)
        pin = str(pin)
        if pin not in [item['name'] for item in component['pins']]:
            raise InputInvalid('component %s has no pin %r' % (ref, pin))
        entry = {'component': ref, 'pin': pin,
                 'pin_semantic': _pin_semantic(component, pin),
                 'net': None, 'state': 'no_connect', 'reason': _nonempty_string(reason, 'reason')}
        self._connections.append(entry)
        return entry

    # -- optional-graphic symbols --------------------------------------
    def symbol(self, kind, x, y, *, ref=None, label=None, blocks=None):
        """Record a presentation-only symbol position.

        Symbols are analysis-graphics metadata and are explicitly *not* the
        connection source of truth; ``connectivity`` remains authoritative.
        """
        entry = {'kind': kind, 'x': x, 'y': y, 'ref': ref, 'label': label,
                 'blocks': list(blocks or [])}
        if not hasattr(self, '_symbols'):
            self._symbols = []
        self._symbols.append(entry)
        return entry

    # -- analysis records ----------------------------------------------
    def calculation(self, calc_id, title, formula, *, inputs, result,
                    unit=None, limit=None, margin=None, method='exact rational arithmetic',
                    assumptions=None, not_modelled=None):
        entry = {
            'id': _nonempty_string(calc_id, 'calculation.id'),
            'title': _nonempty_string(title, 'calculation.title'),
            'method': method,
            'formula': _nonempty_string(formula, 'calculation.formula'),
            'inputs': inputs,
            'result': _jsonable(result),
            'unit': unit,
            'limit': _jsonable(limit),
            'margin': _jsonable(margin),
            'assumptions': list(assumptions or []),
            'not_modelled': list(not_modelled or []),
        }
        if entry['id'] in [item['id'] for item in self._calculations]:
            raise InputInvalid('duplicate calculation id %r' % calc_id)
        self._calculations.append(entry)
        return entry

    def constraint(self, constraint_id, statement, *, kind='hard', applies_to=None,
                   source='derivation', rationale=None):
        if kind not in ('hard', 'advisory', 'layout', 'verification', 'integration'):
            raise InputInvalid('constraint kind must be hard/advisory/layout/verification/integration')
        entry = {
            'id': _nonempty_string(constraint_id, 'constraint.id'),
            'kind': kind,
            'statement': _nonempty_string(statement, 'constraint.statement'),
            'applies_to': applies_to,
            'source': source,
            'rationale': rationale,
        }
        if entry['id'] in [item['id'] for item in self._constraints]:
            raise InputInvalid('duplicate constraint id %r' % constraint_id)
        self._constraints.append(entry)
        return entry

    def requirement(self, constraint_id, statement, **kwargs):
        return self.constraint(constraint_id, statement, **kwargs)

    def evidence(self, evidence_id, kind, statement, *, source=None, applies_to=None,
                 verified=False):
        if kind not in ('manufacturer_datasheet', 'standard', 'application_note',
                        'user_declared', 'derivation', 'assumption', 'tool_output'):
            raise InputInvalid('evidence kind %r is not recognised' % kind)
        entry = {
            'id': _nonempty_string(evidence_id, 'evidence.id'),
            'kind': kind,
            'statement': _nonempty_string(statement, 'evidence.statement'),
            'source': source,
            'applies_to': applies_to,
            'verified': bool(verified),
        }
        if entry['id'] in [item['id'] for item in self._evidence]:
            raise InputInvalid('duplicate evidence id %r' % evidence_id)
        self._evidence.append(entry)
        return entry

    def unknown(self, unknown_id, statement, *, impact=None, how_to_resolve=None):
        entry = {
            'id': _nonempty_string(unknown_id, 'unknown.id'),
            'statement': _nonempty_string(statement, 'unknown.statement'),
            'impact': impact,
            'how_to_resolve': how_to_resolve,
        }
        if entry['id'] in [item['id'] for item in self._unknowns]:
            raise InputInvalid('duplicate unknown id %r' % unknown_id)
        self._unknowns.append(entry)
        return entry

    def assumption(self, statement, *, impact=None):
        entry = {'statement': _nonempty_string(statement, 'assumption.statement'),
                 'impact': impact}
        self._assumptions.append(entry)
        return entry

    # -- finish ---------------------------------------------------------
    def finish(self, status, reasons=(), *, notes=None, calculations_note=None):
        """Build the immutable result, check cross-references and hash it."""
        if self._finished:
            raise InputInvalid('draft already finished')
        if status not in STATUSES:
            raise InputInvalid('status %r is not one of %s' % (status, ', '.join(STATUSES)))
        if not isinstance(reasons, (list, tuple)):
            reasons = [reasons]
        self._finished = True
        if status == 'ready_abstract' and reasons:
            raise InputInvalid('ready_abstract must not carry blocking reasons')
        if status != 'ready_abstract' and not reasons:
            raise InputInvalid('%s requires at least one reason' % status)

        units = {}
        for spec in self.input_schema.values():
            if 'family' in spec:
                units[spec['family']] = canonical_unit(spec['family'])
        result = {
            'schema': RESULT_SCHEMA,
            'module_type': self.module_type,
            'template_version': self.template_version,
            'instance_id': self._instance_id,
            'display_name': self.display_name,
            'status': status,
            'status_reasons': list(reasons),
            'inputs': _echo_inputs(self.inputs),
            'units': units,
            'components': list(self._components),
            'ports': list(self._ports),
            'connectivity': {
                'nets': [dict(net) for net in self._nets],
                'connections': [dict(connection) for connection in self._connections],
            },
            'calculations': list(self._calculations),
            'constraints': list(self._constraints),
            'evidence': list(self._evidence),
            'unknowns': list(self._unknowns),
            'assumptions': list(self._assumptions),
            'binding': dict(VALIDATION_LEVELS),
            'tool': {'name': TOOL_NAME, 'version': __version__},
            'notes': notes,
        }
        if hasattr(self, '_symbols') and self._symbols:
            result['symbols'] = list(self._symbols)
        result['content_hash'] = content_hash(payload_of(result))
        _check_cross_references(result)
        return result


def _echo_inputs(normalized):
    return normalized.as_json() if hasattr(normalized, 'as_json') else normalized


def _value_json(value, unit):
    if value is None:
        return None
    if isinstance(value, dict) and 'nominal' in value:
        return {'value': to_json_number(Fraction(value['nominal'])), 'unit': unit}
    return {'value': to_json_number(Fraction(value)), 'unit': unit}


def _value_unit_for_kind(kind):
    return {'resistor': 'ohm', 'capacitor': 'F', 'inductor': 'H'}.get(kind)


def _range_json(value, family):
    if value is None:
        return None
    if hasattr(value, 'as_json'):
        return value.as_json(family)
    raise InputInvalid('range value must be an Interval')


def _pin_semantic(component, pin):
    for item in component['pins']:
        if item['name'] == pin:
            return item['semantic']
    return None


def _jsonable(value):
    """Convert Fractions inside calculation payloads into JSON numbers."""
    if isinstance(value, dict):
        result = {}
        for key in value:
            if key in ('min', 'max', 'value', 'nominal') and isinstance(value[key], Fraction):
                result[key] = to_json_number(value[key])
            else:
                result[key] = _jsonable(value[key])
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Fraction):
        return to_json_number(value)
    if isinstance(value, bool) or value is None or isinstance(value, (str, int, float)):
        return value
    if hasattr(value, 'as_json'):
        raise InputInvalid('pass an explicit unit dict for Interval calculation values')
    return value


def _validate_namespace(value):
    value = _nonempty_string(value, 'instance_id')
    if not all(character.isalnum() or character == '_' for character in value):
        raise InputInvalid('instance_id must match [A-Za-z0-9_]+: %r' % value)
    if value[0].isdigit():
        raise InputInvalid('instance_id must not start with a digit: %r' % value)
    return value


def _check_cross_references(result):
    refs = [component['ref'] for component in result['components']]
    if len(refs) != len(set(refs)):
        raise InputInvalid('duplicate component refs: %s' % ', '.join(sorted(refs)))
    net_ids = [net['id'] for net in result['connectivity']['nets']]
    if len(net_ids) != len(set(net_ids)):
        raise InputInvalid('duplicate net ids')
    instance_prefix = result['instance_id'] + ':'
    for net_id in net_ids:
        if not net_id.startswith(instance_prefix):
            raise InputInvalid('net %r is not namespaced by instance %r'
                               % (net_id, result['instance_id']))
    for connection in result['connectivity']['connections']:
        if connection['component'] not in refs:
            raise InputInvalid('endpoint references unknown component')
        if connection['state'] == 'connected' and connection.get('net') not in net_ids:
            raise InputInvalid('endpoint references unknown net %r' % connection.get('net'))
        if connection['state'] == 'no_connect' and connection.get('net') is not None:
            raise InputInvalid('NC endpoint must not carry a net')
    for port in result['ports']:
        if port['net'] not in net_ids:
            raise InputInvalid('port %r references unknown net %r' % (port['id'], port['net']))
