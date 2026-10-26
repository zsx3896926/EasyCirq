"""Parameterized common-circuit templates (S02) and a minimal local solver (S03).

Templates bind *physical pin numbers* to roles.  A template is rejected when a
role cannot be bound to a real pin; matching a device name or a symbol string is
never accepted as pin-role evidence.  The data here is design-method level
(``E3``): it is not an instance that has been drawn and verified in an EDA.
"""
from __future__ import annotations

import copy

SCHEMA = 'design-engine-template/v1'

TEMPLATES = {
    'power-entry': {
        'title': '电源入口（保险/TVS/反接/储能）',
        'category': 'power',
        'required_roles': ['vin', 'vout', 'gnd'],
        'blocks': [
            {'role': 'F1', 'kind': 'fuse', 'pin_roles': {'1': 'vin', '2': 'vout'}},
            {'role': 'D1', 'kind': 'tvs', 'pin_roles': {'1': 'vout', '2': 'gnd'}},
            {'role': 'C1', 'kind': 'bulk_cap', 'pin_roles': {'1': 'vout', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VIN', 'members': [['F1', 'vin']]},
            {'name': 'VOUT', 'members': [['F1', 'vout'], ['D1', 'vout'], ['C1', 'vout']]},
            {'name': 'GND', 'members': [['D1', 'gnd'], ['C1', 'gnd']]},
        ],
        'placement': {'core': 'F1', 'satellites': ['D1', 'C1'], 'flow': 'left_to_right'},
        'checks': ['fuse_voltage_and_current', 'tvs_standoff_above_rail', 'bulk_cap_ripple'],
    },
    'ldo': {
        'title': 'LDO 稳压',
        'category': 'power',
        'required_roles': ['vin', 'vout', 'gnd', 'en'],
        'blocks': [
            {'role': 'U1', 'kind': 'ldo', 'pin_roles': {'1': 'vin', '2': 'gnd', '3': 'en', '4': 'vout'}},
            {'role': 'C1', 'kind': 'input_cap', 'pin_roles': {'1': 'vin', '2': 'gnd'}},
            {'role': 'C2', 'kind': 'output_cap', 'pin_roles': {'1': 'vout', '2': 'gnd'}},
            {'role': 'R1', 'kind': 'en_pullup', 'pin_roles': {'1': 'vin', '2': 'en'}},
        ],
        'nets': [
            {'name': 'VIN', 'members': [['U1', 'vin'], ['C1', 'vin'], ['R1', 'vin']]},
            {'name': 'VOUT', 'members': [['U1', 'vout'], ['C2', 'vout']]},
            {'name': 'GND', 'members': [['U1', 'gnd'], ['C1', 'gnd'], ['C2', 'gnd']]},
            {'name': 'EN', 'members': [['U1', 'en'], ['R1', 'en']]},
        ],
        'placement': {'core': 'U1', 'satellites': ['C1', 'C2', 'R1'], 'flow': 'left_to_right'},
        'checks': ['input_output_cap_near_pin', 'dropout_and_thermal', 'en_state'],
    },
    'buck': {
        'title': 'Buck 降压',
        'category': 'power',
        'required_roles': ['vin', 'vout', 'gnd', 'sw', 'fb', 'en'],
        'blocks': [
            {'role': 'U1', 'kind': 'buck', 'pin_roles': {'1': 'vin', '2': 'gnd', '3': 'sw', '4': 'fb', '5': 'en'}},
            {'role': 'L1', 'kind': 'inductor', 'pin_roles': {'1': 'sw', '2': 'vout'}},
            {'role': 'C1', 'kind': 'input_cap', 'pin_roles': {'1': 'vin', '2': 'gnd'}},
            {'role': 'C2', 'kind': 'output_cap', 'pin_roles': {'1': 'vout', '2': 'gnd'}},
            {'role': 'R1', 'kind': 'fb_top', 'pin_roles': {'1': 'vout', '2': 'fb'}},
            {'role': 'R2', 'kind': 'fb_bottom', 'pin_roles': {'1': 'fb', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VIN', 'members': [['U1', 'vin'], ['C1', 'vin']]},
            {'name': 'SW', 'members': [['U1', 'sw'], ['L1', 'sw']]},
            {'name': 'VOUT', 'members': [['L1', 'vout'], ['C2', 'vout'], ['R1', 'vout']]},
            {'name': 'FB', 'members': [['U1', 'fb'], ['R1', 'fb'], ['R2', 'fb']]},
            {'name': 'GND', 'members': [['U1', 'gnd'], ['C1', 'gnd'], ['C2', 'gnd'], ['R2', 'gnd']]},
            {'name': 'EN', 'members': [['U1', 'en']]},
        ],
        'placement': {'core': 'U1', 'satellites': ['C1', 'L1', 'C2', 'R1', 'R2'], 'flow': 'switching_loop_first'},
        'checks': ['hot_loop_area', 'inductor_saturation', 'fb_divider', 'compensation'],
    },
    'mcu-min': {
        'title': 'MCU 最小系统',
        'category': 'digital',
        'required_roles': ['vcc', 'gnd', 'reset', 'boot'],
        'blocks': [
            {'role': 'U1', 'kind': 'mcu', 'pin_roles': {'1': 'vcc', '2': 'gnd', '3': 'reset', '4': 'boot'}},
            {'role': 'C1', 'kind': 'decoupling', 'pin_roles': {'1': 'vcc', '2': 'gnd'}},
            {'role': 'R1', 'kind': 'reset_pullup', 'pin_roles': {'1': 'vcc', '2': 'reset'}},
            {'role': 'R2', 'kind': 'boot_pulldown', 'pin_roles': {'1': 'boot', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VCC', 'members': [['U1', 'vcc'], ['C1', 'vcc'], ['R1', 'vcc']]},
            {'name': 'GND', 'members': [['U1', 'gnd'], ['C1', 'gnd'], ['R2', 'gnd']]},
            {'name': 'RESET', 'members': [['U1', 'reset'], ['R1', 'reset']]},
            {'name': 'BOOT', 'members': [['U1', 'boot'], ['R2', 'boot']]},
        ],
        'placement': {'core': 'U1', 'satellites': ['C1', 'R1', 'R2'], 'flow': 'pin_side'},
        'checks': ['decoupling_at_pin', 'boot_state', 'reset_release'],
    },
    'crystal': {
        'title': '晶振与负载电容',
        'category': 'digital',
        'required_roles': ['xin', 'xout', 'gnd'],
        'blocks': [
            {'role': 'Y1', 'kind': 'crystal', 'pin_roles': {'1': 'xin', '2': 'xout'}},
            {'role': 'C1', 'kind': 'load_cap', 'pin_roles': {'1': 'xin', '2': 'gnd'}},
            {'role': 'C2', 'kind': 'load_cap', 'pin_roles': {'1': 'xout', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'XIN', 'members': [['Y1', 'xin'], ['C1', 'xin']]},
            {'name': 'XOUT', 'members': [['Y1', 'xout'], ['C2', 'xout']]},
            {'name': 'GND', 'members': [['C1', 'gnd'], ['C2', 'gnd']]},
        ],
        'placement': {'core': 'Y1', 'satellites': ['C1', 'C2'], 'flow': 'symmetrical'},
        'checks': ['load_cap_value', 'stray_capacitance', 'drive_level'],
    },
    'reset-supervisor': {
        'title': '复位监控与按键',
        'category': 'digital',
        'required_roles': ['vcc', 'gnd', 'reset', 'button'],
        'blocks': [
            {'role': 'U1', 'kind': 'supervisor', 'pin_roles': {'1': 'vcc', '2': 'gnd', '3': 'reset'}},
            {'role': 'R1', 'kind': 'pullup', 'pin_roles': {'1': 'vcc', '2': 'reset'}},
            {'role': 'C1', 'kind': 'delay_cap', 'pin_roles': {'1': 'reset', '2': 'gnd'}},
            {'role': 'SW1', 'kind': 'button', 'pin_roles': {'1': 'reset', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VCC', 'members': [['U1', 'vcc'], ['R1', 'vcc']]},
            {'name': 'GND', 'members': [['U1', 'gnd'], ['C1', 'gnd'], ['SW1', 'gnd']]},
            {'name': 'RESET', 'members': [['U1', 'reset'], ['R1', 'reset'], ['C1', 'reset'], ['SW1', 'reset']]},
        ],
        'placement': {'core': 'U1', 'satellites': ['R1', 'C1', 'SW1'], 'flow': 'left_to_right'},
        'checks': ['reset_polarity', 'delay_cap', 'button_debounce'],
    },
    'usb-c-power': {
        'title': 'USB-C 取电',
        'category': 'interface',
        'required_roles': ['vbus', 'gnd', 'cc1', 'cc2'],
        'blocks': [
            {'role': 'J1', 'kind': 'usb_c', 'pin_roles': {'A4': 'vbus', 'A1': 'gnd', 'A5': 'cc1', 'B5': 'cc2'}},
            {'role': 'R1', 'kind': 'cc_pulldown', 'pin_roles': {'1': 'cc1', '2': 'gnd'}},
            {'role': 'R2', 'kind': 'cc_pulldown', 'pin_roles': {'1': 'cc2', '2': 'gnd'}},
            {'role': 'C1', 'kind': 'vbus_cap', 'pin_roles': {'1': 'vbus', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VBUS', 'members': [['J1', 'vbus'], ['C1', 'vbus']]},
            {'name': 'GND', 'members': [['J1', 'gnd'], ['R1', 'gnd'], ['R2', 'gnd'], ['C1', 'gnd']]},
            {'name': 'CC1', 'members': [['J1', 'cc1'], ['R1', 'cc1']]},
            {'name': 'CC2', 'members': [['J1', 'cc2'], ['R2', 'cc2']]},
        ],
        'placement': {'core': 'J1', 'satellites': ['R1', 'R2', 'C1'], 'flow': 'connector_edge'},
        'checks': ['cc_resistors_5k1', 'vbus_cap', 'shell_ground'],
    },
    'i2c-sensor': {
        'title': 'I2C 传感器',
        'category': 'sensor',
        'required_roles': ['vcc', 'gnd', 'sda', 'scl'],
        'blocks': [
            {'role': 'U1', 'kind': 'sensor', 'pin_roles': {'1': 'vcc', '2': 'gnd', '3': 'sda', '4': 'scl'}},
            {'role': 'R1', 'kind': 'sda_pullup', 'pin_roles': {'1': 'vcc', '2': 'sda'}},
            {'role': 'R2', 'kind': 'scl_pullup', 'pin_roles': {'1': 'vcc', '2': 'scl'}},
            {'role': 'C1', 'kind': 'decoupling', 'pin_roles': {'1': 'vcc', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VCC', 'members': [['U1', 'vcc'], ['R1', 'vcc'], ['R2', 'vcc'], ['C1', 'vcc']]},
            {'name': 'GND', 'members': [['U1', 'gnd'], ['C1', 'gnd']]},
            {'name': 'SDA', 'members': [['U1', 'sda'], ['R1', 'sda']]},
            {'name': 'SCL', 'members': [['U1', 'scl'], ['R2', 'scl']]},
        ],
        'placement': {'core': 'U1', 'satellites': ['R1', 'R2', 'C1'], 'flow': 'pin_side'},
        'checks': ['pullup_value', 'address_strap', 'bus_capacitance'],
    },
    'divider-sense': {
        'title': '分压采样',
        'category': 'analog',
        'required_roles': ['vin', 'gnd', 'adc'],
        'blocks': [
            {'role': 'R1', 'kind': 'top', 'pin_roles': {'1': 'vin', '2': 'adc'}},
            {'role': 'R2', 'kind': 'bottom', 'pin_roles': {'1': 'adc', '2': 'gnd'}},
            {'role': 'C1', 'kind': 'filter', 'pin_roles': {'1': 'adc', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VIN', 'members': [['R1', 'vin']]},
            {'name': 'ADC', 'members': [['R1', 'adc'], ['R2', 'adc'], ['C1', 'adc']]},
            {'name': 'GND', 'members': [['R2', 'gnd'], ['C1', 'gnd']]},
        ],
        'placement': {'core': 'R1', 'satellites': ['R2', 'C1'], 'flow': 'vertical'},
        'checks': ['divider_ratio', 'input_impedance', 'adc_source_impedance'],
    },
    'opamp-comparator': {
        'title': '运放/比较器',
        'category': 'analog',
        'required_roles': ['vinp', 'vinn', 'vout', 'vcc', 'gnd'],
        'blocks': [
            {'role': 'U1', 'kind': 'comparator', 'pin_roles': {'1': 'vout', '2': 'vcc', '3': 'vinn', '4': 'vinp', '5': 'gnd'}},
            {'role': 'R1', 'kind': 'threshold_top', 'pin_roles': {'1': 'vcc', '2': 'vinn'}},
            {'role': 'R2', 'kind': 'threshold_bottom', 'pin_roles': {'1': 'vinn', '2': 'gnd'}},
            {'role': 'R3', 'kind': 'hysteresis', 'pin_roles': {'1': 'vout', '2': 'vinp'}},
            {'role': 'C1', 'kind': 'decoupling', 'pin_roles': {'1': 'vcc', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VCC', 'members': [['U1', 'vcc'], ['R1', 'vcc'], ['C1', 'vcc']]},
            {'name': 'GND', 'members': [['U1', 'gnd'], ['R2', 'gnd'], ['C1', 'gnd']]},
            {'name': 'VINP', 'members': [['U1', 'vinp'], ['R3', 'vinp']]},
            {'name': 'VINN', 'members': [['U1', 'vinn'], ['R1', 'vinn'], ['R2', 'vinn']]},
            {'name': 'VOUT', 'members': [['U1', 'vout'], ['R3', 'vout']]},
        ],
        'placement': {'core': 'U1', 'satellites': ['R1', 'R2', 'R3', 'C1'], 'flow': 'feedback_local'},
        'checks': ['input_common_mode', 'hysteresis', 'output_pullup', 'decoupling'],
    },
    'mos-load': {
        'title': 'MOS 负载开关',
        'category': 'driver',
        'required_roles': ['vcc', 'gnd', 'gate', 'load', 'drive'],
        'blocks': [
            {'role': 'Q1', 'kind': 'nmos', 'pin_roles': {'1': 'gate', '2': 'gnd', '3': 'load'}},
            {'role': 'R1', 'kind': 'gate_series', 'pin_roles': {'1': 'drive', '2': 'gate'}},
            {'role': 'R2', 'kind': 'gate_pulldown', 'pin_roles': {'1': 'gate', '2': 'gnd'}},
            {'role': 'D1', 'kind': 'flyback', 'pin_roles': {'1': 'load', '2': 'vcc'}},
        ],
        'nets': [
            {'name': 'VCC', 'members': [['D1', 'vcc']]},
            {'name': 'GND', 'members': [['Q1', 'gnd'], ['R2', 'gnd']]},
            {'name': 'GATE', 'members': [['Q1', 'gate'], ['R1', 'gate'], ['R2', 'gate']]},
            {'name': 'LOAD', 'members': [['Q1', 'load'], ['D1', 'load']]},
            {'name': 'GATE_DRIVE', 'members': [['R1', 'drive']]},
        ],
        'placement': {'core': 'Q1', 'satellites': ['R1', 'R2', 'D1'], 'flow': 'switch_loop_first'},
        'checks': ['vgs_rating', 'flyback_diode', 'gate_resistor', 'thermal'],
    },
    'rs485-can': {
        'title': 'RS485/CAN 收发器',
        'category': 'interface',
        'required_roles': ['vcc', 'gnd', 'txd', 'rxd', 'a', 'b'],
        'blocks': [
            {'role': 'U1', 'kind': 'transceiver', 'pin_roles': {'1': 'vcc', '2': 'gnd', '3': 'txd', '4': 'rxd', '5': 'a', '6': 'b'}},
            {'role': 'R1', 'kind': 'termination', 'pin_roles': {'1': 'a', '2': 'b'}},
            {'role': 'R2', 'kind': 'bias_pullup', 'pin_roles': {'1': 'vcc', '2': 'a'}},
            {'role': 'R3', 'kind': 'bias_pulldown', 'pin_roles': {'1': 'b', '2': 'gnd'}},
            {'role': 'D1', 'kind': 'tvs', 'pin_roles': {'1': 'a', '2': 'gnd'}},
            {'role': 'D2', 'kind': 'tvs', 'pin_roles': {'1': 'b', '2': 'gnd'}},
            {'role': 'C1', 'kind': 'decoupling', 'pin_roles': {'1': 'vcc', '2': 'gnd'}},
        ],
        'nets': [
            {'name': 'VCC', 'members': [['U1', 'vcc'], ['R2', 'vcc'], ['C1', 'vcc']]},
            {'name': 'GND', 'members': [['U1', 'gnd'], ['R3', 'gnd'], ['D1', 'gnd'], ['D2', 'gnd'], ['C1', 'gnd']]},
            {'name': 'TXD', 'members': [['U1', 'txd']]},
            {'name': 'RXD', 'members': [['U1', 'rxd']]},
            {'name': 'A', 'members': [['U1', 'a'], ['R1', 'a'], ['R2', 'a'], ['D1', 'a']]},
            {'name': 'B', 'members': [['U1', 'b'], ['R1', 'b'], ['R3', 'b'], ['D2', 'b']]},
        ],
        'placement': {'core': 'U1', 'satellites': ['R1', 'R2', 'R3', 'D1', 'D2', 'C1'], 'flow': 'connector_edge'},
        'checks': ['termination_value', 'bias_network', 'isolation_rating', 'tvs_standoff'],
    },
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_template(template):
    _require(isinstance(template, dict), 'template must be an object')
    _require(template.get('schema', SCHEMA) == SCHEMA, f'template schema {SCHEMA} required')
    for key in ('id', 'title', 'category', 'required_roles', 'blocks', 'nets', 'placement'):
        _require(key in template, f'{key}: required')
    roles = template['required_roles']
    _require(isinstance(roles, list) and roles and len(set(roles)) == len(roles),
             'required_roles: unique nonempty list required')
    block_roles = set()
    for block in template['blocks']:
        _require(block.get('role') and block.get('kind'), 'block role/kind required')
        _require(block['role'] not in block_roles, f"duplicate block role {block['role']!r}")
        block_roles.add(block['role'])
        pin_roles = block.get('pin_roles') or {}
        _require(pin_roles, f"{block['role']}: pin_roles required")
        for number, role in pin_roles.items():
            _require(isinstance(number, str) and number, f"{block['role']}: physical pin number required")
            _require(role in roles, f"{block['role']}.{number}: role {role!r} not in required_roles")
    used = set()
    for net in template['nets']:
        _require(net.get('name'), 'net name required')
        for role, pin_role in net.get('members') or []:
            _require(role in block_roles, f'net member block {role!r} unknown')
            block = next(item for item in template['blocks'] if item['role'] == role)
            _require(pin_role in block['pin_roles'].values(),
                     f'net member {role}.{pin_role} is not a declared pin role')
            used.add((role, pin_role))
    missing = {(block['role'], role) for block in template['blocks']
               for role in block['pin_roles'].values()} - used
    _require(not missing, f'pin roles without a net: {sorted(missing)}')
    core = template['placement'].get('core')
    _require(core in block_roles, f'placement.core {core!r} unknown')
    _require(set(template['placement'].get('satellites') or []) <= block_roles,
             'placement.satellites contains an unknown block')
    return True


def load_templates():
    result = {}
    for identity, raw in TEMPLATES.items():
        template = copy.deepcopy(raw)
        template['id'] = identity
        template['schema'] = SCHEMA
        validate_template(template)
        result[identity] = template
    return result


def bind_template(template, pins_by_block):
    """Bind role -> physical pin number using the real pin table.

    ``pins_by_block`` maps a block role to a list of ``{"number": "...",
    "name": "..."}`` records.  Every declared physical pin must exist; a
    missing pin or an extra role is an explicit failure.
    """
    validate_template(template)
    bound = {}
    for block in template['blocks']:
        role = block['role']
        pins = pins_by_block.get(role)
        if pins is None:
            raise ValueError(f'{role}: no pin table supplied')
        numbers = {str(pin.get('number')) for pin in pins}
        for number in block['pin_roles']:
            if number not in numbers:
                raise ValueError(f'{role}: declared physical pin {number} not found in {sorted(numbers)}')
        bound[role] = {pin_role: number for number, pin_role in block['pin_roles'].items()}
    return bound


def relative_layout(template, size_by_block, spacing=20.0):
    """Deterministic relative placement used by the local solver.

    The core keeps (0,0); satellites are placed in reading order to the right
    and below, never overlapping.  This is a candidate generator, not a claim
    that the resulting drawing is readable or that a real EDA accepted it.
    """
    validate_template(template)
    placement = template['placement']
    core = placement['core']
    satellites = list(placement.get('satellites') or [])
    positions = {core: (0.0, 0.0)}
    cursor_x, cursor_y, row_height = 0.0, 0.0, 0.0
    core_width, core_height = size_by_block.get(core, (0.0, 0.0))
    cursor_x = core_width + spacing
    for role in satellites:
        width, height = size_by_block.get(role, (0.0, 0.0))
        if cursor_x > core_width + spacing * 2:
            cursor_x = 0.0
            cursor_y -= row_height + spacing
            row_height = 0.0
        positions[role] = (cursor_x, cursor_y)
        cursor_x += width + spacing
        row_height = max(row_height, height)
    return positions


def instantiate_plan(template, ir, role_to_component, spacing=20.0):
    """Return a pure coordinate plan for a template instance.

    The plan is accepted only when every role has a real component, every
    declared pin exists on that component, and no candidate body overlaps.
    """
    validate_template(template)
    from .geometry import rect_overlap
    components = {component['id']: component for component in ir.get('components') or []}
    pins_by_block, sizes, resolved = {}, {}, {}
    for block in template['blocks']:
        identity = role_to_component.get(block['role'])
        if identity not in components:
            raise ValueError(f"{block['role']}: component {identity!r} not in IR")
        component = components[identity]
        resolved[block['role']] = identity
        pins_by_block[block['role']] = component.get('pins') or []
        box = component.get('body_bbox')
        sizes[block['role']] = ((box[2] - box[0], box[3] - box[1]) if box else (0.0, 0.0))
    bind_template(template, pins_by_block)
    relative = relative_layout(template, sizes, spacing)
    base_x = (components[resolved[template['placement']['core']]].get('placement') or {}).get('x', 0.0)
    base_y = (components[resolved[template['placement']['core']]].get('placement') or {}).get('y', 0.0)
    candidate_boxes = {}
    operations = []
    for role, (dx, dy) in relative.items():
        component = components[resolved[role]]
        box = component.get('body_bbox')
        width = box[2] - box[0] if box else 0.0
        height = box[3] - box[1] if box else 0.0
        x, y = base_x + dx, base_y + dy
        candidate = (x - width / 2.0, y - height / 2.0, x + width / 2.0, y + height / 2.0) \
            if box else (x, y, x, y)
        candidate_boxes[role] = candidate
        operations.append({
            'component_id': component['id'],
            'designator': component.get('designator'),
            'role': role,
            'from': {'x': (component.get('placement') or {}).get('x'),
                     'y': (component.get('placement') or {}).get('y')},
            'to': {'x': x, 'y': y},
        })
    for index, (first_role, first_box) in enumerate(candidate_boxes.items()):
        for second_role, second_box in list(candidate_boxes.items())[index + 1:]:
            if rect_overlap(first_box, second_box):
                raise ValueError(f'template candidate overlaps: {first_role} / {second_role}')
    return {
        'schema': 'design-engine-template-plan/v1',
        'template': template['id'],
        'operations': operations,
        'binding': {role: resolved[role] for role in resolved},
        'eeada_apply': 'NOT RUN',
        'note': 'relative candidate only; hard conflicts and pin bindings were checked offline',
    }
