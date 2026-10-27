"""Composition of module instances into one abstract design.

Only **explicit** declarations can merge nets: a pairwise ``connections`` edge,
a design-port ``members`` list or an ``nets`` member list.  Matching net *names*
never merge anything; two blocks keep their own namespaced nets until the caller
says otherwise.

The composed design re-checks the contracts that only exist at the design level:

* voltage domains: pairwise voltage ranges must intersect, otherwise the merge
  is a proven conflict and the design is ``unsupported``;
* electrical classes: a ground net can never merge with a power/digital/analog
  node; analog and digital nodes cannot be proven compatible -> ``incomplete``;
* source contention: two power sources or two push-pull outputs on one net are a
  proven conflict; an open-drain node without a pull-up is ``incomplete``;
* current: when a net declares both a demand and a capability, the demand must
  fit; when the necessary numbers are absent the contract is reported
  ``incomplete`` rather than assumed;
* unbound ports: every block port must be bound explicitly or listed in
  ``optional_unbound``.

``ready_abstract`` therefore means "every local module is ready AND every
declared design-level merge is proven compatible".  It still does not mean the
board is ready: part/library/host/physical levels stay ``NOT RUN``.
"""
from __future__ import annotations

from fractions import Fraction

from . import DESIGN_SCHEMA, TOOL_NAME, __version__
from .blocks import REGISTRY
from .canonical import content_hash, payload_of_design
from .errors import InputInvalid
from .numeric import to_json_number
from .result import VALIDATION_LEVELS
from .units import canonical_unit

_INPUT_KEYS = {'design_name', 'blocks', 'connections', 'design_ports',
               'optional_unbound', 'notes'}
_BLOCK_KEYS = {'instance', 'module_type', 'display_name', 'inputs'}
_DESIGN_PORT_KEYS = {'id', 'direction', 'role', 'voltage', 'current', 'isolation',
                     'members', 'description'}
_DIRECTIONS = ('input', 'output', 'bidirectional', 'passive')
_ROLES = ('power', 'ground', 'analog', 'digital', 'open_drain', 'switch', 'reference')
_ISOLATION = ('primary', 'isolated')


def validate_compose_input(payload):
    """Structural validation of a compose document (raises InputInvalid)."""
    if not isinstance(payload, dict):
        raise InputInvalid('compose input must be a JSON object')
    unknown = sorted(set(payload) - _INPUT_KEYS)
    if unknown:
        raise InputInvalid('unknown compose field(s): %s' % ', '.join(unknown))
    name = payload.get('design_name')
    if not isinstance(name, str) or not name.strip():
        raise InputInvalid('design_name must be a non-empty string')
    blocks = payload.get('blocks')
    if not isinstance(blocks, list) or not blocks:
        raise InputInvalid('blocks must be a non-empty list')
    seen = set()
    for index, block in enumerate(blocks):
        where = 'blocks[%d]' % index
        if not isinstance(block, dict):
            raise InputInvalid(where + ' must be an object')
        unknown = sorted(set(block) - _BLOCK_KEYS)
        if unknown:
            raise InputInvalid('%s has unknown field(s): %s' % (where, ', '.join(unknown)))
        instance = block.get('instance')
        if not isinstance(instance, str) or not instance.strip():
            raise InputInvalid(where + '.instance must be a non-empty string')
        if not all(character.isalnum() or character == '_' for character in instance):
            raise InputInvalid('%s.instance must match [A-Za-z0-9_]+: %r' % (where, instance))
        if instance in seen:
            raise InputInvalid('duplicate instance id %r' % instance)
        seen.add(instance)
        module_type = block.get('module_type')
        if module_type not in REGISTRY:
            raise InputInvalid('%s.module_type %r is not a known module (available: %s)'
                               % (where, module_type, ', '.join(sorted(REGISTRY))))
        inputs = block.get('inputs', {})
        if not isinstance(inputs, dict):
            raise InputInvalid(where + '.inputs must be an object')
        display = block.get('display_name')
        if display is not None and (not isinstance(display, str) or not display.strip()):
            raise InputInvalid(where + '.display_name must be a non-empty string')
    _validate_connections(payload.get('connections'))
    _validate_design_ports(payload.get('design_ports'))
    optional = payload.get('optional_unbound', [])
    if not isinstance(optional, list) or not all(isinstance(item, str) for item in optional):
        raise InputInvalid('optional_unbound must be a list of "instance.PORT" strings')
    for endpoint in optional:
        _split_endpoint(endpoint)


def _validate_connections(connections):
    if connections is None:
        return
    if not isinstance(connections, list):
        raise InputInvalid('connections must be a list')
    for index, connection in enumerate(connections):
        where = 'connections[%d]' % index
        if not isinstance(connection, dict):
            raise InputInvalid(where + ' must be an object')
        unknown = sorted(set(connection) - {'a', 'b', 'reason'})
        if unknown:
            raise InputInvalid('%s has unknown field(s): %s' % (where, ', '.join(unknown)))
        for endpoint in ('a', 'b'):
            value = connection.get(endpoint)
            if not isinstance(value, str) or not value.strip():
                raise InputInvalid('%s.%s must be an "instance.PORT" string' % (where, endpoint))
            _split_endpoint(value)


def _validate_design_ports(ports):
    if ports is None:
        return
    if not isinstance(ports, list) or not ports:
        raise InputInvalid('design_ports must be a non-empty list when supplied')
    seen = set()
    for index, port in enumerate(ports):
        where = 'design_ports[%d]' % index
        if not isinstance(port, dict):
            raise InputInvalid(where + ' must be an object')
        unknown = sorted(set(port) - _DESIGN_PORT_KEYS)
        if unknown:
            raise InputInvalid('%s has unknown field(s): %s' % (where, ', '.join(unknown)))
        port_id = port.get('id')
        if not isinstance(port_id, str) or not port_id.strip():
            raise InputInvalid(where + '.id must be a non-empty string')
        if any(character in port_id for character in ':/ .'):
            raise InputInvalid('%s.id must be a simple identifier: %r' % (where, port_id))
        if port_id in seen:
            raise InputInvalid('duplicate design port id %r' % port_id)
        seen.add(port_id)
        if port.get('direction') not in _DIRECTIONS:
            raise InputInvalid('%s.direction must be one of %s' % (where, '|'.join(_DIRECTIONS)))
        if port.get('role') not in _ROLES:
            raise InputInvalid('%s.role must be one of %s' % (where, '|'.join(_ROLES)))
        members = port.get('members')
        if not isinstance(members, list) or not members:
            raise InputInvalid(where + '.members must be a non-empty list of "instance.PORT"')
        for endpoint in members:
            if not isinstance(endpoint, str):
                raise InputInvalid(where + '.members must contain strings')
            _split_endpoint(endpoint)
        if port.get('isolation') is not None and port['isolation'] not in _ISOLATION:
            raise InputInvalid('%s.isolation must be primary or isolated' % where)


def _split_endpoint(text):
    if not isinstance(text, str) or '.' not in text:
        raise InputInvalid('endpoint %r must look like "instance.PORT"' % (text,))
    instance, port = text.rsplit('.', 1)
    if not instance or not port:
        raise InputInvalid('endpoint %r must look like "instance.PORT"' % (text,))
    return instance, port


def _range_obj(payload, field, family):
    """Parse an optional range dict from compose input."""
    from .schema import _parse_field
    from .errors import InputInvalid as _Invalid
    try:
        return _parse_field({'kind': 'range', 'family': family,
                             'nonnegative': True, 'positive': family in ('voltage',)},
                            payload, field)
    except _Invalid:
        raise


def compose_design(payload):
    """Generate and compose every block, then verify design-level contracts."""
    validate_compose_input(payload)
    design_name = payload['design_name'].strip()
    blocks_spec = payload['blocks']
    instances, module_results = [], []
    for block in blocks_spec:
        instance = block['instance']
        module = REGISTRY[block['module_type']]
        result = module.generate(block.get('inputs', {}), instance_id=instance,
                                 display_name=block.get('display_name'))
        module_results.append(result)
        instances.append({
            'instance_id': instance,
            'module_type': result['module_type'],
            'template_version': result['template_version'],
            'display_name': result['display_name'],
            'status': result['status'],
            'content_hash': result['content_hash'],
        })

    ports_by_instance = {result['instance_id']: {port['id']: port for port in result['ports']}
                         for result in module_results}
    nets_by_instance = {result['instance_id']: {net['id']: net for net in result['connectivity']['nets']}
                        for result in module_results}

    # endpoint -> design port owners (pairwise connections may legitimately reuse
    # an endpoint: that is how a net with more than two members is written).
    declared = {}
    for connection in payload.get('connections') or []:
        for side in ('a', 'b'):
            instance, port = _split_endpoint(connection[side])
            _require_endpoint(ports_by_instance, instance, port, 'connections')
    design_ports = payload.get('design_ports') or []
    for design_port in design_ports:
        for endpoint in design_port['members']:
            instance, port = _split_endpoint(endpoint)
            _require_endpoint(ports_by_instance, instance, port, 'design_ports')
            declared.setdefault(endpoint, []).append(design_port['id'])
    for endpoint, owners in declared.items():
        if len(owners) > 1:
            raise InputInvalid('endpoint %r is declared by more than one design port (%s); '
                               'a boundary port cannot belong to two nets'
                               % (endpoint, ', '.join(owners)))

    # union-find over endpoints and design ports
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(first, second):
        root_a, root_b = find(first), find(second)
        if root_a != root_b:
            parent[root_b] = root_a

    for connection in payload.get('connections') or []:
        union(('endpoint', connection['a']), ('endpoint', connection['b']))
    for design_port in design_ports:
        anchor = ('port', design_port['id'])
        for endpoint in design_port['members']:
            union(anchor, ('endpoint', endpoint))
    for result in module_results:
        for port in result['ports']:
            find(('endpoint', '%s.%s' % (result['instance_id'], port['id'])))
    for design_port in design_ports:
        find(('port', design_port['id']))

    groups = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)

    optional_unbound = set(payload.get('optional_unbound') or [])
    conflicts, incomplete, unbound = [], [], []
    nets = []
    bound_endpoints = set()
    for members in groups.values():
        endpoints = sorted(node[1] for node in members if node[0] == 'endpoint')
        design_port_ids = sorted(node[1] for node in members if node[0] == 'port')
        if not endpoints:
            conflicts.append({'code': 'empty_design_port',
                              'detail': 'design port(s) %s have no member endpoint'
                                        % ', '.join(design_port_ids)})
            continue
        if len(endpoints) == 1 and not design_port_ids:
            # A port that no explicit declaration mentions stays unbound; it is
            # reported below, never silently turned into a net.
            continue
        bound_endpoints.update(endpoints)
        net = _build_net(design_name, endpoints, design_port_ids, design_ports,
                         ports_by_instance, nets_by_instance, conflicts, incomplete)
        if net is not None:
            nets.append(net)

    for result in module_results:
        for port in result['ports']:
            endpoint = '%s.%s' % (result['instance_id'], port['id'])
            if endpoint not in bound_endpoints and endpoint not in optional_unbound:
                unbound.append({'instance': result['instance_id'], 'port': port['id'],
                                'module_type': result['module_type'],
                                'reason': 'block port is neither connected nor listed in optional_unbound'})
    missing_optional = sorted(endpoint for endpoint in optional_unbound
                              if _endpoint_exists(ports_by_instance, endpoint) is False)
    if missing_optional:
        incomplete.append({'code': 'optional_unbound_unknown',
                           'detail': 'optional_unbound names unknown endpoint(s): %s'
                                     % ', '.join(missing_optional)})

    components = _design_components(module_results)

    reasons = []
    if conflicts:
        reasons.extend(item['detail'] for item in conflicts)
        status = 'unsupported'
    elif unbound or incomplete:
        reasons.extend(item.get('detail') or item.get('reason') or ''
                       for item in unbound)
        reasons.extend(item['detail'] for item in incomplete)
        status = 'incomplete'
    else:
        not_ready = [instance['instance_id'] for instance in instances
                     if instance['status'] != 'ready_abstract']
        if not_ready:
            status = 'incomplete'
            reasons.append('instance(s) not ready_abstract: %s' % ', '.join(not_ready))
        else:
            status = 'ready_abstract'
    if status != 'ready_abstract' and not reasons:
        reasons = ['composition cannot be proven complete']

    design = {
        'schema': DESIGN_SCHEMA,
        'design_name': design_name,
        'status': status,
        'status_reasons': reasons,
        'instances': instances,
        'blocks': module_results,
        'components': components,
        'nets': sorted(nets, key=lambda net: net['id']),
        'connections': [{'a': connection['a'], 'b': connection['b']}
                        for connection in payload.get('connections') or []],
        'ports': [{'id': port['id'], 'direction': port['direction'], 'role': port['role'],
                   'net': 'design:' + port['id'],
                   'voltage': _port_range_json(port.get('voltage'), 'voltage'),
                   'current': _port_range_json(port.get('current'), 'current'),
                   'isolation': port.get('isolation', 'primary'),
                   'description': port.get('description'),
                   'members': list(port['members'])}
                  for port in design_ports],
        'unbound_ports': unbound,
        'conflicts': conflicts,
        'incomplete': incomplete,
        'partition': _partition(design_ports, payload),
        'binding': dict(VALIDATION_LEVELS),
        'tool': {'name': TOOL_NAME, 'version': __version__},
        'notes': payload.get('notes'),
    }
    design['content_hash'] = content_hash(payload_of_design(design))
    return design


def _require_endpoint(ports_by_instance, instance, port, where):
    if instance not in ports_by_instance:
        raise InputInvalid('%s references unknown instance %r' % (where, instance))
    if port not in ports_by_instance[instance]:
        raise InputInvalid('%s references unknown port %r on instance %r (ports: %s)'
                           % (where, port, instance,
                              ', '.join(sorted(ports_by_instance[instance]))))


def _endpoint_exists(ports_by_instance, endpoint):
    try:
        instance, port = _split_endpoint(endpoint)
    except InputInvalid:
        return False
    return instance in ports_by_instance and port in ports_by_instance[instance]


def _port_range_json(value, family):
    if value is None:
        return None
    if hasattr(value, 'as_json'):
        return value.as_json(family)
    return value


def _build_net(design_name, endpoints, design_port_ids, design_ports, ports_by_instance,
               nets_by_instance, conflicts, incomplete):
    declared_ports = {port['id']: port for port in design_ports}
    members = []
    for endpoint in endpoints:
        instance, port_id = _split_endpoint(endpoint)
        port = ports_by_instance[instance][port_id]
        members.append({'instance': instance, 'port': port_id,
                        'block_net': port['net'],
                        'direction': port['direction'],
                        'role': port['role'],
                        'voltage': port.get('voltage'),
                        'current': port.get('current')})
    role = members[0]['role']
    for member in members[1:]:
        role = _merge_role(role, member['role'])
    # voltage intersection
    voltage = None
    for member in members:
        candidate = _as_interval(member.get('voltage'))
        if candidate is None:
            continue
        voltage = candidate if voltage is None else voltage.intersect(candidate)
        if voltage is None:
            conflicts.append({'code': 'voltage_domain_conflict',
                              'detail': 'net %s merges incompatible voltage ranges'
                                        % _net_label(members),
                              'endpoints': endpoints})
            return None
    if design_port_ids:
        design_port_map = {port['id']: port for port in design_ports}
        design_port = design_port_map[design_port_ids[0]]
        declared_voltage = _as_interval(design_port.get('voltage'))
        if voltage is not None and declared_voltage is not None:
            merged = voltage.intersect(declared_voltage)
            if merged is None:
                conflicts.append({'code': 'design_port_voltage_conflict',
                                  'detail': 'design port %r declares %s which does not cover the net %s'
                                            % (design_port['id'], declared_voltage.as_json('voltage'),
                                               _net_label(members)),
                                  'endpoints': endpoints})
                return None
            if not declared_voltage.covers(voltage):
                incomplete.append({'code': 'design_port_voltage_narrower',
                                   'detail': 'design port %r voltage does not cover every member of net %s'
                                             % (design_port['id'], _net_label(members))})
            voltage = merged
        role = design_port['role']
        isolation = design_port.get('isolation', 'primary')
    else:
        isolation = 'primary'
    # electrical class and contention checks
    classes = {_role_class(member['role']) for member in members}
    if 'ground' in classes and classes - {'ground'}:
        conflicts.append({'code': 'ground_power_merge',
                          'detail': 'net %s merges a ground port with %s'
                                    % (_net_label(members), ', '.join(sorted(classes - {'ground'}))),
                          'endpoints': endpoints})
        return None
    if 'analog' in classes and ('digital' in classes or 'switch' in classes):
        incomplete.append({'code': 'analog_digital_unproven',
                           'detail': 'net %s merges analog and digital/switch ports; level '
                                     'compatibility cannot be proven from port metadata'
                                     % _net_label(members)})
    sources = [member for member in members
               if member['direction'] == 'output' and member['role'] in ('power', 'digital')]
    if len(sources) >= 2:
        conflicts.append({'code': 'output_contention',
                          'detail': 'net %s merges %d push-pull outputs (%s)'
                                    % (_net_label(members), len(sources),
                                       ', '.join('%s.%s' % (item['instance'], item['port'])
                                                 for item in sources)),
                          'endpoints': endpoints})
        return None
    if 'open_drain' in classes and 'power' not in classes and design_port_ids == []:
        incomplete.append({'code': 'missing_pull_up',
                           'detail': 'open-drain net %s has no declared pull-up rail in the design'
                                     % _net_label(members)})
    # current contract
    demand = [member['current'] for member in members
              if member['direction'] == 'input' and member.get('current')]
    capability = [member['current'] for member in members
                  if member['direction'] == 'output' and member.get('current')]
    if design_port_ids:
        port_current = design_port_map[design_port_ids[0]].get('current')
    else:
        port_current = None
    demand_interval = _current_interval(demand)
    capability_interval = _current_interval(capability)
    if port_current is not None:
        boundary = _as_interval(port_current)
        capability_interval = boundary if capability_interval is None else \
            _min_interval(capability_interval, boundary)
    if demand_interval is not None and capability_interval is not None:
        if demand_interval.hi > capability_interval.hi:
            conflicts.append({'code': 'current_contract_conflict',
                              'detail': 'net %s demands %s A but the declared capability is only %s A'
                                        % (_net_label(members),
                                           _fmt(demand_interval.hi), _fmt(capability_interval.hi)),
                              'endpoints': endpoints})
            return None
    elif demand and not capability:
        incomplete.append({'code': 'current_capability_unknown',
                           'detail': 'net %s has a declared current demand but no declared capability'
                                     % _net_label(members)})
    net_id = 'design:' + design_port_ids[0] if design_port_ids else \
        'design:internal_%s' % _internal_slug(members)
    net_name = design_port_ids[0] if design_port_ids else _internal_slug(members)
    net = {
        'id': net_id,
        'name': net_name,
        'role': role,
        'scope': 'external' if design_port_ids else 'internal',
        'voltage': voltage.as_json('voltage') if voltage is not None else None,
        'current': capability_interval.as_json('current') if capability_interval is not None else None,
        'isolation': isolation,
        'members': [{'instance': member['instance'], 'port': member['port'],
                     'block_net': member['block_net']} for member in members],
    }
    return net


_INTERNAL_INDEX = {}


def _internal_slug(members):
    keys = sorted('%s.%s' % (member['instance'], member['port']) for member in members)
    slug = '__'.join(key.replace('.', '_') for key in keys)
    return slug


def _net_label(members):
    return ', '.join('%s.%s' % (member['instance'], member['port']) for member in members)


def _role_class(role):
    return {'power': 'power', 'ground': 'ground', 'analog': 'analog',
            'digital': 'digital', 'open_drain': 'digital', 'switch': 'switch',
            'reference': 'analog'}[role]


def _merge_role(current_role, new_role):
    order = ['ground', 'power', 'reference', 'analog', 'open_drain', 'digital', 'switch']
    return current_role if order.index(current_role) <= order.index(new_role) else new_role


def _as_interval(payload):
    from .ranges import Interval, parse_interval
    if payload is None:
        return None
    if isinstance(payload, dict) and {'min', 'max'} <= set(payload):
        return parse_interval(payload, payload.get('unit') == 'A' and 'current' or 'voltage')
    return None


def _current_interval(values):
    from .ranges import Interval
    intervals = []
    for value in values:
        interval = _as_interval(value)
        if interval is not None:
            intervals.append(interval)
    if not intervals:
        return None
    return Interval(min(item.lo for item in intervals), max(item.hi for item in intervals))


def _min_interval(first, second):
    from .ranges import Interval
    return Interval(min(first.lo, second.lo), min(first.hi, second.hi))


def _fmt(value):
    from .numeric import format_number
    return format_number(value)


def _design_components(module_results):
    components = []
    for result in module_results:
        prefix = _ref_prefix(result['instance_id'])
        for component in result['components']:
            components.append({
                'ref': '%s_%s' % (prefix, component['ref']),
                'instance': result['instance_id'],
                'source_ref': component['ref'],
                'role': component['role'],
                'kind': component['kind'],
                'value': component.get('value'),
                'tolerance': component.get('tolerance'),
                'series': component.get('series'),
                'power_rating': component.get('power_rating'),
                'voltage_rating': component.get('voltage_rating'),
                'polarity': component.get('polarity'),
                'mpn': component.get('mpn'),
                'library_id': component.get('library_id'),
                'binding': 'unbound',
            })
    components.sort(key=lambda component: (component['instance'], component['source_ref']))
    return components


def _ref_prefix(instance_id):
    return ''.join(character.upper() if character.isalnum() else '_' for character in instance_id)


def _partition(design_ports, payload):
    """Report ground/power partitions, including intentional isolation."""
    grounds = [port['id'] for port in design_ports if port['role'] == 'ground']
    isolated = [port['id'] for port in design_ports
                if port['role'] == 'ground' and port.get('isolation') == 'isolated']
    return {
        'design_ports': len(design_ports),
        'ground_ports': grounds,
        'isolated_ground_ports': isolated,
        'note': 'ground ports are merged only through explicit design-port membership; '
                'isolated grounds stay separate nets',
    }
