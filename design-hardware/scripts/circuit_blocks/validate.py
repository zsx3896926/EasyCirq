"""Independent validation of generated module results and composed designs.

``generate`` runs this check on its own output before printing it, and
``python -m circuit_blocks validate`` runs exactly the same checks on a file it
did not produce.  Validation is deliberately redundant with the draft builder:
it recomputes the content hash, re-derives referential integrity from the JSON
alone, and (in ``--recompute`` mode) re-runs the module from its echoed input.

A hash mismatch means the file was edited after generation.  A structural
problem with a *matching* hash means the generator itself is wrong.  Both are
reported, never silently repaired.
"""
from __future__ import annotations

from fractions import Fraction

from . import DESIGN_SCHEMA, RESULT_SCHEMA
from .canonical import content_hash, payload_of, payload_of_design
from .errors import InputInvalid
from .eseries import is_standard_value, supported_series
from .numeric import parse_number

_REQUIRED_RESULT_KEYS = (
    'schema', 'module_type', 'template_version', 'instance_id', 'display_name',
    'status', 'status_reasons', 'inputs', 'units', 'components', 'ports',
    'connectivity', 'calculations', 'constraints', 'evidence', 'unknowns',
    'assumptions', 'binding', 'content_hash',
)


def validate_module_result(result, *, check_hash=True, check_standard_values=True,
                           check_binding_levels=True):
    """Return ``{'status': 'valid'|'invalid', 'problems': [...], 'warnings': [...]}``."""
    problems, warnings = [], []
    if not isinstance(result, dict):
        raise InputInvalid('module result must be a JSON object')
    for key in _REQUIRED_RESULT_KEYS:
        if key not in result:
            problems.append({'code': 'missing_key', 'detail': 'required key %r is missing' % key})
    if problems:
        return _report(problems, warnings)
    if result['schema'] != RESULT_SCHEMA:
        problems.append({'code': 'schema_mismatch',
                         'detail': 'schema must be %r' % RESULT_SCHEMA})
    if not isinstance(result['status_reasons'], list):
        problems.append({'code': 'invalid_status_reasons',
                         'detail': 'status_reasons must be a list'})
        return _report(problems, warnings)
    status = result['status']
    if status not in ('ready_abstract', 'needs_device_facts', 'unsupported', 'input_invalid'):
        problems.append({'code': 'invalid_status', 'detail': 'unknown status %r' % status})
    elif status != 'ready_abstract' and not result['status_reasons']:
        problems.append({'code': 'missing_status_reason',
                         'detail': '%s needs a status reason' % status})
    elif status == 'ready_abstract' and result['status_reasons']:
        problems.append({'code': 'ready_with_reasons',
                         'detail': 'ready_abstract must not carry blocking reasons'})

    components = result['components']
    ports = result['ports']
    connectivity = result['connectivity']
    if not isinstance(components, list):
        problems.append({'code': 'invalid_components', 'detail': 'components must be a list'})
        return _report(problems, warnings)
    if not isinstance(ports, list):
        problems.append({'code': 'invalid_ports', 'detail': 'ports must be a list'})
        return _report(problems, warnings)
    if not isinstance(connectivity, dict):
        problems.append({'code': 'invalid_connectivity', 'detail': 'connectivity must be an object'})
        return _report(problems, warnings)
    nets = connectivity.get('nets')
    connections = connectivity.get('connections')
    if not isinstance(nets, list) or not isinstance(connections, list):
        problems.append({'code': 'invalid_connectivity',
                         'detail': 'connectivity.nets and connectivity.connections must be lists'})
        return _report(problems, warnings)

    _check_components(components, problems, warnings, check_standard_values)
    net_ids = _check_nets(nets, result['instance_id'], problems)
    _check_connections(components, connections, net_ids, problems, warnings)
    _check_ports(ports, net_ids, connections, problems, warnings)

    if status == 'ready_abstract':
        if not components:
            problems.append({'code': 'empty_components',
                             'detail': 'ready_abstract result has no components'})
        if not nets:
            problems.append({'code': 'empty_nets',
                             'detail': 'ready_abstract result has no nets'})
        if not ports:
            problems.append({'code': 'empty_ports',
                             'detail': 'ready_abstract result has no ports'})
        if not result['calculations']:
            problems.append({'code': 'empty_calculations',
                             'detail': 'ready_abstract result has no calculations'})
        if not result['evidence']:
            problems.append({'code': 'empty_evidence',
                             'detail': 'ready_abstract result must at least record input/derivation evidence'})

    if check_binding_levels:
        binding = result['binding']
        if not isinstance(binding, dict):
            problems.append({'code': 'invalid_binding', 'detail': 'binding must be an object'})
        else:
            for level in ('library_binding', 'host_validation', 'physical_validation', 'real_eda'):
                if binding.get(level) not in ('NOT RUN', 'partial', 'pass', 'fail'):
                    problems.append({'code': 'invalid_binding_level',
                                     'detail': 'binding.%s must be explicit (NOT RUN/partial/pass/fail)' % level})

    if check_hash:
        expected = content_hash(payload_of(result))
        if result['content_hash'] != expected:
            problems.append({'code': 'content_hash_mismatch',
                             'detail': 'content_hash does not match the result body; '
                                       'the file was edited after generation or generated inconsistently'})
    return _report(problems, warnings)


def _check_components(components, problems, warnings, check_standard_values):
    refs = set()
    for index, component in enumerate(components):
        where = 'components[%d]' % index
        if not isinstance(component, dict):
            problems.append({'code': 'invalid_component', 'detail': where + ' is not an object'})
            continue
        for key in ('ref', 'role', 'kind', 'pins', 'binding'):
            if key not in component:
                problems.append({'code': 'missing_component_key',
                                 'detail': '%s.%s is missing' % (where, key)})
        ref = component.get('ref')
        if not isinstance(ref, str) or not ref:
            problems.append({'code': 'invalid_ref', 'detail': where + '.ref must be a non-empty string'})
        elif ref in refs:
            problems.append({'code': 'duplicate_ref', 'detail': 'duplicate ref %r' % ref})
        else:
            refs.add(ref)
        pins = component.get('pins')
        pin_names = []
        if isinstance(pins, list):
            pin_names = [str(pin.get('name')) for pin in pins if isinstance(pin, dict)]
            if len(pin_names) != len(set(pin_names)):
                problems.append({'code': 'duplicate_pin_name',
                                 'detail': '%s has duplicate pin names' % where})
            for pin in pins:
                if not isinstance(pin, dict) or not pin.get('semantic'):
                    problems.append({'code': 'missing_pin_semantic',
                                     'detail': '%s pin without a semantic meaning' % where})
        else:
            problems.append({'code': 'invalid_pins', 'detail': where + '.pins must be a list'})
        if check_standard_values and component.get('series') and component.get('value'):
            value = component['value']
            if isinstance(value, dict) and value.get('unit') and component['kind'] in ('resistor', 'capacitor'):
                family = 'ohm' if component['kind'] == 'resistor' else 'F'
                if value.get('unit') == family:
                    series = component['series']
                    if series not in supported_series():
                        problems.append({'code': 'unknown_series',
                                         'detail': '%s declares unknown series %r' % (where, series)})
                    else:
                        try:
                            numeric = parse_number(value.get('value'))
                        except InputInvalid:
                            numeric = None
                        if numeric is not None and not is_standard_value(numeric, series):
                            problems.append({'code': 'non_standard_value',
                                             'detail': '%s value %s is not in %s'
                                                       % (where, value.get('value'), series)})
        if component.get('mpn') and component.get('binding') == 'unbound':
            warnings.append({'code': 'mpn_without_binding',
                             'detail': '%s names MPN %r but is still unbound'
                                       % (where, component.get('mpn'))})


def _check_nets(nets, instance_id, problems):
    net_ids = set()
    prefix = instance_id + ':'
    for index, net in enumerate(nets):
        where = 'connectivity.nets[%d]' % index
        if not isinstance(net, dict):
            problems.append({'code': 'invalid_net', 'detail': where + ' is not an object'})
            continue
        net_id = net.get('id')
        if not isinstance(net_id, str) or not net_id:
            problems.append({'code': 'invalid_net_id', 'detail': where + '.id must be a string'})
            continue
        if net_id in net_ids:
            problems.append({'code': 'duplicate_net', 'detail': 'duplicate net id %r' % net_id})
        net_ids.add(net_id)
        if not net_id.startswith(prefix):
            problems.append({'code': 'unnamespaced_net',
                             'detail': 'net %r is not namespaced by %r' % (net_id, instance_id)})
        if not net.get('name'):
            problems.append({'code': 'missing_net_name', 'detail': where + '.name is missing'})
    return net_ids


def _check_connections(components, connections, net_ids, problems, warnings):
    refs = {component.get('ref') for component in components if isinstance(component, dict)}
    pin_map = {}
    for component in components:
        if isinstance(component, dict):
            pin_map[component.get('ref')] = {str(pin.get('name')) for pin in component.get('pins') or []
                                              if isinstance(pin, dict)}
    seen = set()
    net_endpoints = {}
    for index, connection in enumerate(connections):
        where = 'connectivity.connections[%d]' % index
        if not isinstance(connection, dict):
            problems.append({'code': 'invalid_connection', 'detail': where + ' is not an object'})
            continue
        ref, pin = connection.get('component'), str(connection.get('pin'))
        if ref not in refs:
            problems.append({'code': 'unknown_component', 'detail': where + ' names unknown component %r' % ref})
            continue
        if pin not in pin_map.get(ref, set()):
            problems.append({'code': 'unknown_pin', 'detail': where + ' names unknown pin %r on %s' % (pin, ref)})
        key = (ref, pin)
        if key in seen:
            problems.append({'code': 'duplicate_endpoint', 'detail': '%s repeated' % (key,)})
        seen.add(key)
        state = connection.get('state')
        net_id = connection.get('net')
        if state == 'connected':
            if net_id not in net_ids:
                problems.append({'code': 'unknown_net', 'detail': where + ' references undeclared net %r' % net_id})
            else:
                net_endpoints.setdefault(net_id, []).append(key)
        elif state == 'no_connect':
            if net_id is not None:
                problems.append({'code': 'nc_with_net', 'detail': where + ' is NC but carries a net'})
            if not connection.get('reason'):
                warnings.append({'code': 'nc_without_reason', 'detail': where + ' has no reason'})
        else:
            problems.append({'code': 'unknown_endpoint_state',
                             'detail': where + ' state must be connected/no_connect'})
    for net_id, endpoints in net_endpoints.items():
        if len(endpoints) == 1:
            warnings.append({'code': 'singleton_net',
                             'detail': 'net %r has only one endpoint %s; declare a port if it leaves the module'
                                       % (net_id, endpoints[0])})


def _check_ports(ports, net_ids, connections, problems, warnings):
    port_ids = set()
    port_nets = set()
    for index, port in enumerate(ports):
        where = 'ports[%d]' % index
        if not isinstance(port, dict):
            problems.append({'code': 'invalid_port', 'detail': where + ' is not an object'})
            continue
        port_id = port.get('id')
        if not isinstance(port_id, str) or not port_id:
            problems.append({'code': 'invalid_port_id', 'detail': where + '.id must be a string'})
        elif port_id in port_ids:
            problems.append({'code': 'duplicate_port', 'detail': 'duplicate port id %r' % port_id})
        else:
            port_ids.add(port_id)
        if port.get('direction') not in ('input', 'output', 'bidirectional', 'passive'):
            problems.append({'code': 'invalid_port_direction',
                             'detail': where + '.direction is invalid'})
        if port.get('role') not in ('power', 'ground', 'analog', 'digital', 'open_drain',
                                    'switch', 'reference'):
            problems.append({'code': 'invalid_port_role', 'detail': where + '.role is invalid'})
        net_id = port.get('net')
        if net_id not in net_ids:
            problems.append({'code': 'port_unknown_net',
                             'detail': where + ' references undeclared net %r' % net_id})
        else:
            port_nets.add(net_id)
    for connection in connections:
        if isinstance(connection, dict) and connection.get('state') == 'connected':
            net_id = connection.get('net')
            if net_id in net_ids and net_id not in port_nets:
                endpoint_count = sum(1 for item in connections
                                     if isinstance(item, dict) and item.get('net') == net_id)
                if endpoint_count < 2:
                    warnings.append({'code': 'dangling_net',
                                     'detail': 'net %r has one endpoint and no port' % net_id})


def validate_design(design, *, check_hash=True):
    """Validate a composed design object produced by ``compose``."""
    problems, warnings = [], []
    if not isinstance(design, dict):
        raise InputInvalid('design must be a JSON object')
    required = ('schema', 'design_name', 'status', 'status_reasons', 'instances',
                'blocks', 'components', 'nets', 'connections', 'ports',
                'unbound_ports', 'conflicts', 'incomplete', 'partition', 'binding',
                'content_hash')
    for key in required:
        if key not in design:
            problems.append({'code': 'missing_key', 'detail': 'required key %r is missing' % key})
    if problems:
        return _report(problems, warnings)
    if design['schema'] != DESIGN_SCHEMA:
        problems.append({'code': 'schema_mismatch', 'detail': 'schema must be %r' % DESIGN_SCHEMA})
    status = design['status']
    if status not in ('ready_abstract', 'incomplete', 'unsupported'):
        problems.append({'code': 'invalid_status', 'detail': 'unknown design status %r' % status})

    instances = design['instances']
    blocks = design['blocks']
    if not isinstance(instances, list) or not isinstance(blocks, list):
        problems.append({'code': 'invalid_blocks', 'detail': 'instances and blocks must be lists'})
        return _report(problems, warnings)
    instance_ids = [instance.get('instance_id') for instance in instances]
    if len(instance_ids) != len(set(instance_ids)):
        problems.append({'code': 'duplicate_instance', 'detail': 'two blocks share an instance id'})
    if len(blocks) != len(instances):
        problems.append({'code': 'instance_block_mismatch',
                         'detail': '%d instances but %d block results' % (len(instances), len(blocks))})
    block_by_instance = {}
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            problems.append({'code': 'invalid_block', 'detail': 'blocks[%d] is not an object' % index})
            continue
        instance_id = block.get('instance_id')
        if instance_id in block_by_instance:
            problems.append({'code': 'duplicate_instance', 'detail': 'duplicate block %r' % instance_id})
        block_by_instance[instance_id] = block
        report = validate_module_result(block, check_hash=check_hash)
        if report['status'] != 'valid':
            problems.append({'code': 'invalid_module_result',
                             'detail': 'block %r: %s'
                                       % (instance_id,
                                          ', '.join(item['code'] for item in report['problems']))})
        if status == 'ready_abstract' and block.get('status') != 'ready_abstract':
            problems.append({'code': 'nonready_block_in_ready_design',
                             'detail': 'block %r is %r' % (instance_id, block.get('status'))})
    for instance in instances:
        instance_id = instance.get('instance_id')
        block = block_by_instance.get(instance_id)
        if block is None:
            problems.append({'code': 'missing_block',
                             'detail': 'instance %r has no block result' % instance_id})
            continue
        for key in ('module_type', 'status', 'content_hash'):
            if instance.get(key) != block.get(key):
                problems.append({'code': 'instance_block_mismatch',
                                 'detail': 'instance %r %s differs from its block result'
                                           % (instance_id, key)})

    # components: unique, namespaced refs
    refs = set()
    for index, component in enumerate(design['components'] or []):
        where = 'components[%d]' % index
        if not isinstance(component, dict):
            problems.append({'code': 'invalid_component', 'detail': where + ' is not an object'})
            continue
        ref = component.get('ref')
        if not isinstance(ref, str) or not ref:
            problems.append({'code': 'invalid_ref', 'detail': where + '.ref must be a string'})
            continue
        if ref in refs:
            problems.append({'code': 'duplicate_ref',
                             'detail': 'duplicate composed ref %r' % ref})
        refs.add(ref)
        if component.get('instance') not in block_by_instance:
            problems.append({'code': 'unknown_component_instance',
                             'detail': '%s names unknown instance %r'
                                       % (where, component.get('instance'))})
        if component.get('binding') != 'unbound':
            problems.append({'code': 'component_bound_without_binding_layer',
                             'detail': '%s claims binding %r before any library binding ran'
                                       % (where, component.get('binding'))})

    # nets and their members
    net_ids = set()
    bound_ports = {}
    for index, net in enumerate(design['nets'] or []):
        where = 'nets[%d]' % index
        if not isinstance(net, dict):
            problems.append({'code': 'invalid_net', 'detail': where + ' is not an object'})
            continue
        net_id = net.get('id')
        if not isinstance(net_id, str) or not net_id.startswith('design:'):
            problems.append({'code': 'invalid_net_id',
                             'detail': where + '.id must start with "design:"'})
            continue
        if net_id in net_ids:
            problems.append({'code': 'duplicate_net', 'detail': 'duplicate net id %r' % net_id})
        net_ids.add(net_id)
        if not net.get('members'):
            problems.append({'code': 'empty_net', 'detail': where + ' has no members'})
        for member in net.get('members') or []:
            instance = member.get('instance') if isinstance(member, dict) else None
            port = member.get('port') if isinstance(member, dict) else None
            block = block_by_instance.get(instance)
            if block is None:
                problems.append({'code': 'unknown_net_instance',
                                 'detail': '%s references unknown instance %r' % (where, instance)})
                continue
            ports = {item['id']: item for item in block.get('ports') or []}
            if port not in ports:
                problems.append({'code': 'unknown_net_port',
                                 'detail': '%s references unknown port %r on %r'
                                           % (where, port, instance)})
                continue
            if member.get('block_net') != ports[port].get('net'):
                problems.append({'code': 'net_member_mismatch',
                                 'detail': '%s member %s.%s claims block_net %r but the block port '
                                           'is on %r' % (where, instance, port,
                                                         member.get('block_net'), ports[port].get('net'))})
            key = (instance, port)
            if key in bound_ports:
                problems.append({'code': 'port_in_two_nets',
                                 'detail': 'port %s.%s appears in %r and %r'
                                           % (instance, port, bound_ports[key], net_id)})
            bound_ports[key] = net_id

    # design ports
    design_port_ids = set()
    for index, port in enumerate(design['ports'] or []):
        where = 'ports[%d]' % index
        if not isinstance(port, dict):
            problems.append({'code': 'invalid_port', 'detail': where + ' is not an object'})
            continue
        port_id = port.get('id')
        if not isinstance(port_id, str) or not port_id:
            problems.append({'code': 'invalid_port_id', 'detail': where + '.id must be a string'})
        elif port_id in design_port_ids:
            problems.append({'code': 'duplicate_port', 'detail': 'duplicate design port %r' % port_id})
        else:
            design_port_ids.add(port_id)
        if port.get('net') not in net_ids:
            problems.append({'code': 'port_unknown_net',
                             'detail': '%s references undeclared net %r' % (where, port.get('net'))})
        for endpoint in port.get('members') or []:
            if not isinstance(endpoint, str) or '.' not in endpoint:
                problems.append({'code': 'invalid_port_member',
                                 'detail': '%s member %r is not "instance.PORT"' % (where, endpoint)})
                continue
            instance, port_name = endpoint.rsplit('.', 1)
            block = block_by_instance.get(instance)
            if block is None or port_name not in {item['id'] for item in block.get('ports') or []}:
                problems.append({'code': 'port_member_unknown',
                                 'detail': '%s member %r is not a block port' % (where, endpoint)})

    # connections reference known endpoints
    for index, connection in enumerate(design['connections'] or []):
        where = 'connections[%d]' % index
        if not isinstance(connection, dict):
            problems.append({'code': 'invalid_connection', 'detail': where + ' is not an object'})
            continue
        for side in ('a', 'b'):
            endpoint = connection.get(side)
            if not isinstance(endpoint, str) or '.' not in endpoint:
                problems.append({'code': 'invalid_endpoint',
                                 'detail': '%s.%s is not "instance.PORT"' % (where, side)})
                continue
            instance, port_name = endpoint.rsplit('.', 1)
            block = block_by_instance.get(instance)
            if block is None or port_name not in {item['id'] for item in block.get('ports') or []}:
                problems.append({'code': 'unknown_endpoint',
                                 'detail': '%s.%s references unknown block port %r'
                                           % (where, side, endpoint)})

    # every block port must be bound or explicitly listed
    fully_bound = True
    optional = {endpoint for endpoint in design.get('unbound_ports') or []
                if isinstance(endpoint, dict)}
    # unbound_ports is a list of dicts; a bound-port set is authoritative
    for instance_id, block in block_by_instance.items():
        for port in block.get('ports') or []:
            if (instance_id, port['id']) not in bound_ports:
                fully_bound = False
                if status == 'ready_abstract':
                    problems.append({'code': 'unbound_port_in_ready_design',
                                     'detail': 'port %s.%s is not bound to a design net'
                                               % (instance_id, port['id'])})
    if status == 'ready_abstract':
        if design['conflicts']:
            problems.append({'code': 'ready_with_conflicts',
                             'detail': 'ready_abstract design carries conflicts'})
        if design['incomplete']:
            problems.append({'code': 'ready_with_incomplete',
                             'detail': 'ready_abstract design carries incomplete items'})
        if design['unbound_ports']:
            problems.append({'code': 'ready_with_unbound',
                             'detail': 'ready_abstract design carries unbound ports'})
        if not design['status_reasons'] == []:
            problems.append({'code': 'ready_with_reasons',
                             'detail': 'ready_abstract design must not carry status reasons'})
    elif not design['status_reasons']:
        problems.append({'code': 'missing_status_reason',
                         'detail': '%s design needs a status reason' % status})
    if status == 'unsupported' and not design['conflicts']:
        problems.append({'code': 'unsupported_without_conflict',
                         'detail': 'unsupported design must list at least one proven conflict'})
    if check_hash:
        expected = content_hash(payload_of_design(design))
        if design['content_hash'] != expected:
            problems.append({'code': 'content_hash_mismatch',
                             'detail': 'design content_hash does not match its body'})
    return _report(problems, warnings)

def _report(problems, warnings):
    return {
        'status': 'valid' if not problems else 'invalid',
        'problems': problems,
        'warnings': warnings,
    }


def recompute_module(result, registry):
    """Re-run a module from its echoed inputs and compare semantic content.

    Returns ``{'status': 'match'|'mismatch'|'not_possible', ...}``.  This is
    stronger than a hash check: it catches a file that was edited *and* hashed
    again with a tool that produced an invalid result.
    """
    module_type = result.get('module_type')
    if module_type not in registry:
        return {'status': 'not_possible', 'detail': 'unknown module_type %r' % module_type}
    block = registry[module_type]
    instance_id = result.get('instance_id')
    display_name = result.get('display_name')
    try:
        regenerated = block.generate(result.get('inputs'), instance_id=instance_id,
                                     display_name=display_name)
    except Exception as exc:  # noqa: BLE001 - report, never crash the validator
        return {'status': 'not_possible',
                'detail': 'regeneration failed: %s: %s' % (type(exc).__name__, exc)}
    if regenerated.get('status') != result.get('status'):
        return {'status': 'mismatch',
                'detail': 'status %r != %r' % (result.get('status'), regenerated.get('status'))}
    if regenerated.get('content_hash') != result.get('content_hash'):
        return {'status': 'mismatch',
                'detail': 'regenerated content hash differs from the file'}
    return {'status': 'match'}
