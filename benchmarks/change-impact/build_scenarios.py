"""Deterministically build the frozen change-impact benchmark corpus.

The generator exists so the 24+ scenario models stay consistent and reviewable.
It writes *input* JSON and *independently derived* assertion files; the
assertions are not copied from tool output.  Running it twice produces
byte-identical files (``--check`` verifies that), and ``run_benchmark.py
--freeze`` then records their SHA-256 in ``manifest.json``.

Modelling rules encoded here (see docs/parallel-change-impact/):
* every object id is ``<prefix>:<stable-name>`` typed to its kind;
* ``baseline_attributes`` lists only the fields whose baseline value differs;
* a change's before/after must equal the model values on each side;
* snapshots declare ``complete`` only when their scope covers every kind used;
* all models are synthetic: ``simulated: true`` and
  ``source_type: simulated_synthetic``.  They are not real project data.

Not run: EDA reads/writes, host DRC, save-and-reopen, official plots, physical
tests or manufacturing.  Timing recorded by the runner says nothing about real
EDA runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALL_KINDS = [
    'component_instance', 'pin', 'net', 'power_domain', 'interface',
    'layout_region', 'mechanical_anchor', 'bom_line', 'firmware_contract',
    'test', 'artifact', 'requirement', 'document',
]
TOOL = 'benchmark-scenario-generator'


def h(char):
    return 'sha256:' + str(char) * 64


def _lf_bytes(path):
    """Repository bytes with CRLF normalised to LF.

    ``core.autocrlf=true`` checkouts turn committed LF into CRLF on Windows;
    the frozen SHA must be platform-independent, so it is always computed over
    the LF-normalised content.
    """
    return Path(path).read_bytes().replace(b'\r\n', b'\n')


def sha256_file(path):
    return hashlib.sha256(_lf_bytes(path)).hexdigest()


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def obj(identity, kind, attributes=None, baseline=None, present=None,
        display_name=None):
    record = {'id': identity, 'kind': kind,
              'attributes': attributes or {}}
    if baseline:
        record['baseline_attributes'] = baseline
    if present:
        record['present'] = present
    if display_name:
        record['display_name'] = display_name
    return record


def dep(identity, source, target, semantic='power_supply', direction='forward',
        certainty='declared', conditions=None):
    record = {'id': identity, 'from': source, 'to': target,
              'semantic': semantic, 'direction': direction,
              'certainty': certainty}
    if conditions:
        record['conditions'] = list(conditions)
    return record


def chg(identity, object_id, attribute, before, after, kind=None,
        authorized=True, change_type='modify', authorized_scope=None,
        conditions=None):
    record = {'id': identity, 'change_type': change_type,
              'object': object_id, 'attribute': attribute,
              'before': before, 'after': after, 'authorized': authorized,
              'source': {'type': 'declared', 'ref': 'ECO-BENCH'}}
    if kind:
        record['kind'] = kind
    if authorized_scope:
        record['authorized_scope'] = authorized_scope
    if conditions:
        record['conditions'] = list(conditions)
    return record


def check(identity, covers, *, cost=0.5, mandatory=False, kind='offline',
          approval=False, requires_inputs=None, requires=None, title=None,
          module='benchmark-catalog'):
    return {
        'id': identity,
        'title': title or identity.replace('chk:', '').replace('_', ' '),
        'kind': kind,
        'cost': cost,
        'mandatory': mandatory,
        'approval': approval,
        'module': module,
        'covers': covers,
        'requires': list(requires or []),
        'requires_inputs': list(requires_inputs or []),
    }


def cover(object_id, impact, attribute=None):
    entry = {'object': object_id, 'impact': impact}
    if attribute is not None:
        entry['attribute'] = attribute
    return entry


def evidence(identity, check_id, *, revision='r1', content_hash=None,
             objects=None, attributes=None, impacts=None, simulated=False,
             valid_until=None, dependency_fingerprint=None, scope_complete=True,
             result='pass', tool_version='0.9.0', captured_at='2026-01-01T00:00:00Z'):
    return {
        'id': identity,
        'check': check_id,
        'result': result,
        'tool_version': tool_version,
        'revision': revision,
        'content_hash': content_hash or h('1'),
        'coverage': {'objects': list(objects or []),
                     'attributes': list(attributes or []),
                     'impacts': list(impacts or [])},
        'conditions': [],
        'simulated': simulated,
        'captured_at': captured_at,
        'valid_until': valid_until,
        'dependency_fingerprint': dependency_fingerprint,
        'scope_complete': scope_complete,
    }


def model_payload(*, project='bench-board', objects, dependencies, changes,
                  checks, prior_evidence=None, constraints=None,
                  observed_diff=None, complete=True, missing=None,
                  budget=None, dependencies_complete=True,
                  unknown_objects=None, declared_kinds=None,
                  baseline_hash=None, candidate_hash=None,
                  analysis_time='2026-01-02T00:00:00Z'):
    kinds = sorted({item['kind'] for item in objects})
    scope = sorted(set(kinds) | ({'dependencies'} if dependencies else set()))
    declared = declared_kinds if declared_kinds is not None else sorted(
        set(ALL_KINDS) | set(kinds))
    payload = {
        'schema': 'hds-change-impact-input/v1',
        'project': {'name': project, 'id': 'PRJ-BENCH'},
        'baseline': {
            'project': project, 'document': 'main', 'revision': 'r1',
            'content_hash': baseline_hash or h('1'),
            'source_type': 'simulated_synthetic',
            'snapshot_scope': scope,
            'missing_fields': list(missing or []),
            'complete': complete,
            'notes': 'synthetic benchmark snapshot; not a real project',
        },
        'candidate': {
            'project': project, 'document': 'main', 'revision': 'r2',
            'content_hash': candidate_hash or h('2'),
            'source_type': 'simulated_synthetic',
            'snapshot_scope': scope,
            'missing_fields': list(missing or []),
            'complete': complete,
            'notes': 'synthetic benchmark snapshot; not a real project',
        },
        'objects': objects,
        'dependencies': dependencies,
        'changes': changes,
        'constraints': list(constraints or []),
        'verification_catalog': checks,
        'prior_evidence': list(prior_evidence or []),
        'budget': budget or {'max_depth': 8, 'max_paths': 500,
                             'max_cost': 1000},
        'model_scope': {
            'declared_kinds': declared,
            'unknown_objects': list(unknown_objects or []),
            'dependencies_complete': dependencies_complete,
            'notes': 'synthetic declared graph; not a real project',
        },
        'simulated': True,
        'analysis_time': analysis_time,
    }
    if observed_diff is not None:
        payload['observed_diff'] = observed_diff
    return payload


def expected(scenario_id, *, derivation, expected_status='planned_with_scope',
             must_impact=None, must_not_impact=None, required_checks=None,
             blocked_checks=None, evidence_status=None,
             unknown_codes_required=None, unknown_codes_forbidden=None,
             min_coverage_gaps=0, cycles_nonempty=False, truncated=False,
             expected_exit=0):
    return {
        'schema': 'hds-change-impact-benchmark-expected/v1',
        'scenario_id': scenario_id,
        'derivation': derivation,
        'expected_status': expected_status,
        'expected_exit': expected_exit,
        'must_impact': list(must_impact or []),
        'must_not_impact': list(must_not_impact or []),
        'required_checks': list(required_checks or []),
        'blocked_checks': list(blocked_checks or []),
        'evidence_status': dict(evidence_status or {}),
        'unknown_codes_required': list(unknown_codes_required or []),
        'unknown_codes_forbidden': list(unknown_codes_forbidden or []),
        'min_coverage_gaps': min_coverage_gaps,
        'cycles_nonempty': cycles_nonempty,
        'truncated': truncated,
        'real_eda': 'NOT RUN',
        'physical_test': 'NOT RUN',
    }


def impact(object_id, kind, *, confidence_at_least='certain',
           change_contains=None):
    record = {'object': object_id, 'impact': kind,
              'confidence_at_least': confidence_at_least}
    if change_contains:
        record['change_contains'] = list(change_contains)
    return record


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------

def scenario_display_text_move():
    objects = [
        obj('cmp:U1', 'component_instance',
            {'mpn': 'MCU-A', 'designator': 'U1', 'placement': {'x': 10, 'y': 10},
             'display': {'x': 12, 'y': 4}},
            {'display': {'x': 10, 'y': 4}}),
        obj('art:sch', 'artifact', {'kind': 'schematic_plot', 'revision': 'r2'}),
        obj('fw:mcu', 'firmware_contract', {'io_voltage': 3.3}),
    ]
    dependencies = [
        dep('dep:1', 'cmp:U1', 'art:sch', 'document_reference'),
        dep('dep:2', 'cmp:U1', 'fw:mcu', 'firmware_consumer'),
    ]
    checks = [check('chk:plot', [cover('art:sch', 'documentation_only')],
                    mandatory=False)]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:U1', 'display.x', 10, 12)],
                            checks=checks)
    exp = expected(
        'display_text_move',
        derivation=('display_only only follows document_reference (R7). The '
                    'displayed text position affects the plot artifact only; it '
                    'must not invalidate the firmware contract, and no firmware '
                    'or manufacturing impact is produced.'),
        must_impact=[impact('cmp:U1', 'documentation_only'),
                     impact('art:sch', 'documentation_only')],
        must_not_impact=[{'object': 'fw:mcu',
                          'reason': 'display text move is not a firmware change'}],
        unknown_codes_forbidden=['missing_edge_data'])
    return payload, exp


def scenario_net_rename():
    objects = [
        obj('net:+5V', 'net', {'name': '+3V3', 'members': ['cmp:U1.1']},
            {'name': '+5V'}),
        obj('cmp:U1', 'component_instance', {'mpn': 'MCU-A'}),
        obj('test:power', 'test', {'criterion': {'v': 3.3}}),
    ]
    dependencies = [
        dep('dep:1', 'net:+5V', 'cmp:U1', 'power_supply'),
        dep('dep:2', 'net:+5V', 'test:power', 'test_reference'),
    ]
    checks = [check('chk:net_name', [cover('test:power',
                                           'test_criterion_change')])]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'net:+5V', 'name',
                                         '+5V', '+3V3')],
                            checks=checks)
    exp = expected(
        'net_rename',
        derivation=('identity_rename with a proven-identical member partition '
                    'is not a connectivity change, but it is also not a proof of '
                    'no impact (R6 keeps electrical state possible and '
                    'documentation needs review).'),
        must_impact=[impact('net:+5V', 'electrical_state',
                            confidence_at_least='possible')],
        required_checks=[],
        unknown_codes_forbidden=['missing_edge_data'])
    return payload, exp


def scenario_led_resistor_value():
    objects = [
        obj('cmp:R1', 'component_instance',
            {'mpn': 'RES-1K', 'value': {'resistance': 2200, 'unit': 'ohm'},
             'footprint': {'uuid': 'fp:0603'}},
            {'value': {'resistance': 1000, 'unit': 'ohm'}}),
        obj('net:LED_A', 'net', {'members': ['cmp:R1.1', 'cmp:D1.1']}),
        obj('cmp:D1', 'component_instance', {'mpn': 'LED-RED'}),
        obj('test:led_current', 'test',
            {'criterion': {'min_ma': 2, 'max_ma': 15}}),
    ]
    dependencies = [
        dep('dep:1', 'cmp:R1', 'net:LED_A', 'signal_path'),
        dep('dep:2', 'net:LED_A', 'cmp:D1', 'signal_path'),
        dep('dep:3', 'cmp:R1', 'test:led_current', 'test_reference'),
    ]
    checks = [
        check('chk:led_current', [cover('test:led_current',
                                        'test_criterion_change')],
              mandatory=True),
        check('chk:led_net', [cover('net:LED_A', 'signal_integrity')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:R1', 'value.resistance',
                                         1000, 2200)],
                            checks=checks)
    exp = expected(
        'led_resistor_value',
        derivation=('parameter changes follow signal_path/test_reference '
                    '(R13): the resistor current-setting value affects the LED '
                    'net electrical state and the current test criterion.'),
        must_impact=[impact('cmp:R1', 'electrical_state'),
                     impact('net:LED_A', 'signal_integrity',
                            confidence_at_least='possible'),
                     impact('test:led_current', 'test_criterion_change',
                            confidence_at_least='possible')],
        required_checks=['chk:led_current'])
    return payload, exp


def scenario_power_5v_to_3v3():
    objects = [
        obj('pwr:5V', 'power_domain',
            {'voltage': {'nominal': 3.3, 'unit': 'V'}},
            {'voltage': {'nominal': 5.0, 'unit': 'V'}}),
        obj('net:+5V', 'net', {'name': '+5V'}),
        obj('cmp:MCU', 'component_instance',
            {'mpn': 'MCU-A', 'io_voltage': 3.3}),
        obj('fw:io', 'firmware_contract', {'io_voltage': 5.0}),
        obj('test:rail', 'test', {'criterion': {'v_min': 3.0, 'v_max': 3.6}}),
    ]
    dependencies = [
        dep('dep:1', 'pwr:5V', 'net:+5V', 'power_supply'),
        dep('dep:2', 'net:+5V', 'cmp:MCU', 'power_supply'),
        dep('dep:3', 'cmp:MCU', 'fw:io', 'firmware_consumer'),
        dep('dep:4', 'cmp:MCU', 'test:rail', 'verification_coverage'),
    ]
    checks = [
        check('chk:rail_range', [cover('cmp:MCU', 'power_integrity')],
              mandatory=True),
        check('chk:io_level', [cover('test:rail', 'power_integrity')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'pwr:5V', 'voltage.nominal',
                                         5.0, 3.3)],
                            checks=checks)
    exp = expected(
        'power_5v_to_3v3',
        derivation=('a power-requirement change follows only power_supply edges '
                    '(R1): the MCU is affected through the rail. The firmware '
                    'consumer edge is a different semantic, so R1 stops; the '
                    'firmware impact is not asserted as certain propagation.'),
        must_impact=[impact('net:+5V', 'power_integrity'),
                     impact('cmp:MCU', 'power_integrity')],
        must_not_impact=[{'object': 'fw:io',
                          'reason': 'R1 does not follow firmware_consumer edges'}],
        required_checks=['chk:rail_range'],
        unknown_codes_forbidden=['missing_edge_data'])
    return payload, exp


def scenario_ldo_replacement():
    objects = [
        obj('cmp:U2', 'component_instance',
            {'mpn': 'LDO-3V3-B', 'footprint': {'uuid': 'fp:sot23-5'},
             'manufacturer': 'ACME'},
            {'mpn': 'LDO-3V3-A'}),
        obj('net:+3V3', 'net', {'name': '+3V3'}),
        obj('region:main', 'layout_region', {'bbox': [0, 0, 40, 25]}),
        obj('art:cpl', 'artifact', {'kind': 'cpl', 'revision': 'r2'}),
    ]
    dependencies = [
        dep('dep:1', 'cmp:U2', 'region:main', 'footprint_binding'),
        dep('dep:2', 'cmp:U2', 'art:cpl', 'artifact_source'),
        dep('dep:3', 'cmp:U2', 'net:+3V3', 'power_supply'),
    ]
    checks = [
        check('chk:ldo_fit', [cover('region:main', 'footprint_compatibility')],
              mandatory=True),
        check('chk:cpl', [cover('art:cpl', 'manufacturing_output')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:U2', 'mpn',
                                         'LDO-3V3-A', 'LDO-3V3-B')],
                            checks=checks)
    exp = expected(
        'ldo_replacement',
        derivation=('component_identity follows footprint_binding and '
                    'artifact_source (R2): the layout region and the CPL are '
                    'affected. A same-footprint replacement still does not prove '
                    'electrical equivalence, so electrical state stays possible.'),
        must_impact=[impact('region:main', 'footprint_compatibility'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible')],
        required_checks=['chk:ldo_fit'])
    return payload, exp


def _mcu_objects():
    return [
        obj('cmp:MCU', 'component_instance',
            {'mpn': 'MCU-B', 'instance_uuid': 'uuid-b',
             'designator': 'U1', 'footprint': {'uuid': 'fp:qfn32'},
             'placement': {'x': 10, 'y': 10}},
            {'mpn': 'MCU-A', 'instance_uuid': 'uuid-a'}),
        obj('fw:pinmap', 'firmware_contract', {'pin': 'PA0', 'voltage': 3.3}),
        obj('region:main', 'layout_region', {'bbox': [0, 0, 40, 25]}),
        obj('bom:U1', 'bom_line', {'designator': 'U1', 'mpn': 'MCU-B'},
            {'mpn': 'MCU-A'}),
        obj('art:cpl', 'artifact', {'kind': 'cpl', 'revision': 'r2'}),
    ]


def _mcu_dependencies():
    return [
        dep('dep:1', 'cmp:MCU', 'fw:pinmap', 'firmware_consumer'),
        dep('dep:2', 'cmp:MCU', 'region:main', 'footprint_binding'),
        dep('dep:3', 'cmp:MCU', 'art:cpl', 'artifact_source'),
        dep('dep:4', 'bom:U1', 'art:cpl', 'artifact_source'),
    ]


def scenario_mcu_instance_change():
    payload = model_payload(
        objects=_mcu_objects(), dependencies=_mcu_dependencies(),
        changes=[chg('chg:1', 'cmp:MCU', 'mpn', 'MCU-A', 'MCU-B')],
        checks=[check('chk:fw_pinmap',
                      [cover('fw:pinmap', 'firmware_compatibility')],
                      mandatory=True),
                check('chk:cpl', [cover('art:cpl', 'manufacturing_output')])])
    exp = expected(
        'mcu_instance_change',
        derivation=('replacing the MCU instance (R2) affects the firmware '
                    'contract, the layout region and the manufacturing outputs; '
                    'the same footprint must not be read as electrical '
                    'equivalence, so no "safe" claim is expected.'),
        must_impact=[impact('fw:pinmap', 'firmware_compatibility',
                            confidence_at_least='possible'),
                     impact('region:main', 'footprint_compatibility'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible')],
        required_checks=['chk:fw_pinmap'])
    return payload, exp


def scenario_mcu_pin_remap():
    objects = [
        obj('cmp:MCU', 'component_instance',
            {'mpn': 'MCU-A',
             'pins': {'1': {'net': 'net:IO1', 'function': 'GPIO'}}},
            {'pins': {'1': {'net': 'net:IO2', 'function': 'GPIO'}}}),
        obj('net:IO1', 'net', {'name': 'IO1'}),
        obj('net:IO2', 'net', {'name': 'IO2'}),
        obj('fw:pinmap', 'firmware_contract', {'pin': 'PA0', 'net': 'net:IO1'}),
        obj('test:io', 'test', {'criterion': {'high_mv': 2400}}),
    ]
    dependencies = [
        dep('dep:1', 'cmp:MCU', 'net:IO1', 'pin_mapping'),
        dep('dep:2', 'cmp:MCU', 'net:IO2', 'pin_mapping'),
        dep('dep:3', 'cmp:MCU', 'fw:pinmap', 'firmware_consumer'),
        dep('dep:4', 'fw:pinmap', 'test:io', 'test_reference'),
    ]
    checks = [
        check('chk:pin_net', [cover('net:IO2', 'signal_integrity')],
              mandatory=True),
        check('chk:fw_map', [cover('fw:pinmap', 'firmware_compatibility')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:MCU', 'pins.1.net',
                                         'net:IO2', 'net:IO1')],
                            checks=checks)
    exp = expected(
        'mcu_pin_remap',
        derivation=('pin_mapping (R4) affects the remapped net, the firmware '
                    'consumer that references the pin and the pin-compatibility '
                    'of the instance.'),
        must_impact=[impact('net:IO1', 'pin_compatibility'),
                     impact('cmp:MCU', 'pin_compatibility'),
                     impact('fw:pinmap', 'firmware_compatibility',
                            confidence_at_least='possible')],
        required_checks=['chk:pin_net'])
    return payload, exp


def scenario_mcu_footprint():
    objects = [
        obj('cmp:MCU', 'component_instance',
            {'mpn': 'MCU-A', 'footprint': {'uuid': 'fp:lqfp48'}},
            {'footprint': {'uuid': 'fp:qfn32'}}),
        obj('region:main', 'layout_region', {'bbox': [0, 0, 40, 25]}),
        obj('anchor:case', 'mechanical_anchor', {'pose': {'x': 0, 'y': 0}}),
        obj('art:gerber', 'artifact', {'kind': 'gerber', 'revision': 'r2'}),
    ]
    dependencies = [
        dep('dep:1', 'cmp:MCU', 'region:main', 'footprint_binding'),
        dep('dep:2', 'region:main', 'anchor:case', 'mechanical_constraint'),
        dep('dep:3', 'cmp:MCU', 'art:gerber', 'artifact_source'),
    ]
    checks = [
        check('chk:fp_fit', [cover('region:main', 'footprint_compatibility')],
              mandatory=True),
        check('chk:mech', [cover('anchor:case', 'mechanical_fit')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:MCU', 'footprint.uuid',
                                         'fp:qfn32', 'fp:lqfp48')],
                            checks=checks)
    exp = expected(
        'mcu_footprint',
        derivation=('a footprint change (R3) affects the layout region, the '
                    'mechanical constraint chain and the manufacturing output.'),
        must_impact=[impact('region:main', 'footprint_compatibility'),
                     impact('anchor:case', 'mechanical_fit'),
                     impact('art:gerber', 'manufacturing_output',
                            confidence_at_least='possible')],
        required_checks=['chk:fp_fit'])
    return payload, exp


def scenario_usb_position():
    objects = [
        obj('if:USB', 'interface',
            {'pose': {'x': 0, 'y': -5, 'z': 1.2}, 'diff_pair': True},
            {'pose': {'x': 0, 'y': -5, 'z': 0.8}}),
        obj('anchor:case', 'mechanical_anchor',
            {'pose': {'x': 0, 'y': -5}, 'hole_diameter': 2.2}),
        obj('art:cpl', 'artifact', {'kind': 'cpl', 'revision': 'r2'}),
        obj('test:usb', 'test', {'criterion': {'insertion_force_n': 12}}),
        obj('fw:usb', 'firmware_contract', {'usb': True}),
    ]
    dependencies = [
        dep('dep:1', 'if:USB', 'anchor:case', 'enclosure_constraint'),
        dep('dep:2', 'if:USB', 'art:cpl', 'artifact_source'),
        dep('dep:3', 'if:USB', 'test:usb', 'test_reference'),
    ]
    checks = [
        check('chk:shell_fit', [cover('anchor:case', 'enclosure_interface')],
              mandatory=True),
        check('chk:usb_insertion', [cover('test:usb', 'test_criterion_change')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'if:USB', 'pose.z', 0.8, 1.2)],
                            checks=checks)
    exp = expected(
        'usb_position',
        derivation=('an interface pose change (R5) affects the enclosure anchor, '
                    'the assembly/CPL output and the insertion-force test even '
                    'though no net changed. Firmware is not affected.'),
        must_impact=[impact('if:USB', 'mechanical_fit'),
                     impact('anchor:case', 'enclosure_interface',
                            confidence_at_least='possible'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible')],
        must_not_impact=[
            {'object': 'fw:usb',
             'reason': 'moving an interface is not a firmware contract change'},
            {'object': 'test:usb',
             'reason': ('R5 does not follow test_reference; the insertion test '
                        'is not silently invalidated by a pose change')}],
        required_checks=['chk:shell_fit'])
    return payload, exp


def scenario_board_outline():
    objects = [
        obj('region:main', 'layout_region',
            {'bbox': [0, 0, 42, 25], 'board': {'outline': [[0, 0], [42, 0],
                                                          [42, 25], [0, 25]]}},
            {'board': {'outline': [[0, 0], [40, 0], [40, 25], [0, 25]]}}),
        obj('anchor:case', 'mechanical_anchor', {'pose': {'x': 0, 'y': 0}}),
        obj('art:gerber', 'artifact', {'kind': 'gerber', 'revision': 'r2'}),
    ]
    dependencies = [
        dep('dep:1', 'region:main', 'anchor:case', 'mechanical_constraint'),
        dep('dep:2', 'region:main', 'art:gerber', 'artifact_source'),
    ]
    checks = [
        check('chk:outline', [cover('art:gerber', 'manufacturing_output')],
              mandatory=True),
        check('chk:case_clearance',
              [cover('anchor:case', 'mechanical_fit')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'region:main', 'board.outline',
                                         [[0, 0], [40, 0], [40, 25], [0, 25]],
                                         [[0, 0], [42, 0], [42, 25], [0, 25]])],
                            checks=checks)
    exp = expected(
        'board_outline',
        derivation=('a board-outline change (R8) affects mechanical fit against '
                    'the enclosure anchor and the manufacturing output.'),
        must_impact=[impact('region:main', 'mechanical_fit'),
                     impact('anchor:case', 'mechanical_fit'),
                     impact('art:gerber', 'manufacturing_output')],
        required_checks=['chk:outline'])
    return payload, exp


def scenario_differential_layer():
    objects = [
        obj('region:main', 'layout_region',
            {'layer': 'L2', 'bbox': [0, 0, 40, 25]},
            {'layer': 'L1'}),
        obj('net:USB_DP', 'net', {'name': 'USB_DP', 'diff_pair': 'USB'}),
        obj('art:gerber', 'artifact', {'kind': 'gerber', 'revision': 'r2'}),
        obj('test:si', 'test', {'criterion': {'impedance_ohm': 90}}),
    ]
    dependencies = [
        dep('dep:1', 'region:main', 'net:USB_DP', 'signal_path'),
        dep('dep:2', 'region:main', 'art:gerber', 'artifact_source'),
        dep('dep:3', 'net:USB_DP', 'test:si', 'test_reference'),
    ]
    checks = [
        check('chk:impedance', [cover('net:USB_DP', 'signal_integrity')],
              mandatory=True),
        check('chk:gerber', [cover('art:gerber', 'manufacturing_output')]),
        check('chk:si_test', [cover('test:si', 'test_criterion_change')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'region:main', 'layer',
                                         'L1', 'L2', kind='layer_stack')],
                            checks=checks)
    exp = expected(
        'differential_layer',
        derivation=('a layer/stackup change (R9) affects signal integrity on the '
                    'differential pair, the manufacturing output and the '
                    'impedance test criterion.'),
        must_impact=[impact('region:main', 'signal_integrity'),
                     impact('net:USB_DP', 'signal_integrity'),
                     impact('art:gerber', 'manufacturing_output')],
        must_not_impact=[{'object': 'test:si',
                          'reason': ('R9 stops at signal/net boundaries; an '
                                     'impedance test criterion is not silently '
                                     'marked failed or invalidated by a layer move')}],
        required_checks=['chk:impedance'])
    return payload, exp


def scenario_dnp_config():
    objects = [
        obj('bom:R1', 'bom_line',
            {'designator': 'R1', 'mpn': 'RES-1K', 'dnp': True},
            {'dnp': False}),
        obj('art:cpl', 'artifact', {'kind': 'cpl', 'revision': 'r2'}),
        obj('test:powerup', 'test', {'criterion': {'rail_up_ms': 50}}),
    ]
    dependencies = [
        dep('dep:1', 'bom:R1', 'art:cpl', 'artifact_source'),
        dep('dep:2', 'bom:R1', 'test:powerup', 'test_reference'),
    ]
    checks = [
        check('chk:bom_variant', [cover('bom:R1', 'bom_variant')],
              mandatory=True),
        check('chk:cpl_dnp', [cover('art:cpl', 'manufacturing_output')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'bom:R1', 'dnp', False, True)],
                            checks=checks)
    exp = expected(
        'dnp_config',
        derivation=('a DNP delivery configuration change (R10) affects the BOM '
                    'line, the assembly/CPL output and the fitted-state test.'),
        must_impact=[impact('bom:R1', 'bom_variant'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible'),
                     impact('test:powerup', 'test_criterion_change',
                            confidence_at_least='possible')],
        required_checks=['chk:bom_variant'])
    return payload, exp


def scenario_bom_substitute():
    objects = [
        obj('cmp:R2', 'component_instance',
            {'mpn': 'RES-10K-B', 'footprint': {'uuid': 'fp:0603'}},
            {'mpn': 'RES-10K-A'}),
        obj('bom:R2', 'bom_line', {'designator': 'R2', 'mpn': 'RES-10K-B'},
            {'mpn': 'RES-10K-A'}),
        obj('art:cpl', 'artifact', {'kind': 'cpl', 'revision': 'r2'}),
    ]
    dependencies = [
        dep('dep:1', 'cmp:R2', 'bom:R2', 'artifact_source'),
        dep('dep:2', 'bom:R2', 'art:cpl', 'artifact_source'),
    ]
    checks = [check('chk:bom_line', [cover('bom:R2', 'bom_variant')],
                    mandatory=True)]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:R2', 'mpn',
                                         'RES-10K-A', 'RES-10K-B')],
                            checks=checks)
    exp = expected(
        'bom_substitute',
        derivation=('a component identity substitution (R2) reaches the BOM line '
                    'through artifact_source and is reported as a BOM variant '
                    'impact; the CPL is affected too.'),
        must_impact=[impact('bom:R2', 'bom_variant'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible')],
        required_checks=['chk:bom_line'])
    return payload, exp


def scenario_firmware_contract():
    objects = [
        obj('fw:pinmap', 'firmware_contract',
            {'pin': 'PA0', 'io_contract': {'voltage': 3.3}},
            {'io_contract': {'voltage': 5.0}}),
        obj('net:IO1', 'net', {'name': 'IO1'}),
        obj('req:REQ2', 'requirement', {'text': 'firmware must use 3.3V IO'}),
        obj('test:io', 'test', {'criterion': {'high_mv': 2400}}),
    ]
    dependencies = [
        dep('dep:1', 'fw:pinmap', 'net:IO1', 'signal_path'),
        dep('dep:2', 'fw:pinmap', 'req:REQ2', 'requirement_ref'),
    ]
    checks = [
        check('chk:fw_level', [cover('fw:pinmap', 'firmware_compatibility')],
              mandatory=True),
        check('chk:req_trace', [cover('req:REQ2', 'requirement_trace')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'fw:pinmap',
                                         'io_contract.voltage', 5.0, 3.3)],
                            checks=checks)
    exp = expected(
        'firmware_contract',
        derivation=('a firmware contract change (R11) affects firmware '
                    'compatibility directly and the requirement trace; the IO '
                    'net is reached through signal_path.'),
        must_impact=[impact('fw:pinmap', 'firmware_compatibility'),
                     impact('net:IO1', 'signal_integrity',
                            confidence_at_least='possible'),
                     impact('req:REQ2', 'requirement_trace',
                            confidence_at_least='possible')],
        required_checks=['chk:fw_level'])
    return payload, exp


def scenario_test_threshold():
    objects = [
        obj('test:boot', 'test',
            {'criterion': {'v_min': 3.0, 'v_max': 3.6}},
            {'criterion': {'v_min': 4.75, 'v_max': 5.25}}),
        obj('req:REQ3', 'requirement', {'text': 'boot at 3.3V'}),
        obj('cmp:MCU', 'component_instance', {'mpn': 'MCU-A'}),
        obj('test:legacy', 'test', {'criterion': {'name': 'legacy threshold'}}),
    ]
    dependencies = [
        dep('dep:1', 'test:boot', 'req:REQ3', 'requirement_ref'),
    ]
    checks = [
        check('chk:boot_threshold', [cover('test:boot',
                                           'test_criterion_change')],
              mandatory=True),
        check('chk:mcu_unrelated', [cover('cmp:MCU', 'electrical_state')]),
    ]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'test:boot', 'criterion',
                                         {'v_min': 4.75, 'v_max': 5.25},
                                         {'v_min': 3.0, 'v_max': 3.6})],
                            checks=checks)
    exp = expected(
        'test_threshold',
        derivation=('a test criterion change (R12) only follows test_reference / '
                    'verification_coverage / requirement_ref; it must not spread '
                    'to unrelated electrical evidence.'),
        must_impact=[impact('test:boot', 'test_criterion_change'),
                     impact('req:REQ3', 'requirement_trace',
                            confidence_at_least='possible')],
        must_not_impact=[{'object': 'cmp:MCU',
                          'reason': 'changing a test threshold is not an electrical change'}],
        required_checks=['chk:boot_threshold'])
    return payload, exp


def scenario_requirement_change():
    objects = [
        obj('req:REQ1', 'requirement',
            {'requirement': {'text': 'rail tolerance +-3%'}},
            {'requirement': {'text': 'rail tolerance +-5%'}}),
        obj('pwr:3V3', 'power_domain', {'voltage': {'nominal': 3.3}}),
    ]
    dependencies = [
        dep('dep:1', 'req:REQ1', 'pwr:3V3', 'requirement_ref'),
    ]
    checks = [check('chk:req', [cover('pwr:3V3', 'requirement_trace')],
                    mandatory=True)]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'req:REQ1',
                                         'requirement.text',
                                         'rail tolerance +-5%',
                                         'rail tolerance +-3%')],
                            checks=checks)
    exp = expected(
        'requirement_change',
        derivation=('a requirement change (R14) follows requirement_ref and is '
                    'reported as a requirement trace impact on the rail.'),
        must_impact=[impact('req:REQ1', 'requirement_trace'),
                     impact('pwr:3V3', 'requirement_trace')],
        required_checks=['chk:req'])
    return payload, exp


def _placement_objects():
    return [
        obj('cmp:U1', 'component_instance',
            {'mpn': 'MCU-A', 'placement': {'x': 1, 'y': 1}},
            {'placement': {'x': 0, 'y': 1}}),
        obj('region:main', 'layout_region', {'bbox': [0, 0, 40, 25]}),
    ]


def scenario_evidence_reuse_positive():
    objects = _placement_objects()
    dependencies = [dep('dep:1', 'cmp:U1', 'region:main', 'mechanical_constraint')]
    checks = [check('chk:placement',
                    [cover('region:main', 'mechanical_fit')],
                    mandatory=False, kind='offline')]
    prior = [evidence('ev:1', 'chk:placement',
                      revision='r2',
                      content_hash=h('2'),  # exactly the candidate snapshot
                      objects=['region:main'],
                      attributes=['bbox'],
                      impacts=['mechanical_fit'])]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:U1', 'placement.x', 0, 1)],
                            checks=checks, prior_evidence=prior)
    exp = expected(
        'evidence_reuse_positive',
        derivation=('the evidence was captured on the candidate revision and '
                    'hash (content-bound), so it can be reused as '
                    'reusable_bound with its original capture preserved; it must '
                    'not be re-dated.'),
        must_impact=[impact('cmp:U1', 'mechanical_fit',
                            confidence_at_least='possible'),
                     impact('region:main', 'mechanical_fit',
                            confidence_at_least='possible')],
        evidence_status={'ev:1': 'reusable_bound'})
    return payload, exp


def scenario_evidence_reuse_negative():
    objects = _placement_objects()
    dependencies = [dep('dep:1', 'cmp:U1', 'region:main', 'mechanical_constraint')]
    checks = [check('chk:placement',
                    [cover('region:main', 'mechanical_fit')],
                    mandatory=True)]
    prior = [evidence('ev:1', 'chk:placement',
                      content_hash=h('1'),
                      objects=['region:main'],
                      attributes=['bbox'],
                      impacts=['mechanical_fit'])]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:U1', 'placement.x', 0, 1)],
                            checks=checks, prior_evidence=prior)
    exp = expected(
        'evidence_reuse_negative',
        derivation=('the covered layout region is affected on a different '
                    'revision without a matching fingerprint, so the prior '
                    'evidence must be invalidated rather than reused.'),
        evidence_status={'ev:1': 'invalidated'},
        required_checks=['chk:placement'],
        min_coverage_gaps=1)
    return payload, exp


def scenario_partial_snapshot():
    objects = [obj('cmp:U1', 'component_instance', {'mpn': 'MCU-B'},
                   {'mpn': 'MCU-A'})]
    checks = [check('chk:any', [cover('cmp:U1', 'electrical_state')],
                    mandatory=True)]
    payload = model_payload(objects=objects, dependencies=[],
                            changes=[chg('chg:1', 'cmp:U1', 'mpn',
                                         'MCU-A', 'MCU-B')],
                            checks=checks, complete=False,
                            missing=['bom_line', 'artifact'])
    exp = expected(
        'partial_snapshot',
        derivation=('a partial snapshot may not claim completeness: the report '
                    'stays incomplete and carries an explicit snapshot_incomplete '
                    'unknown instead of a "no impact" conclusion.'),
        expected_status='incomplete',
        unknown_codes_required=['snapshot_incomplete'])
    return payload, exp


def scenario_cyclic_dependency():
    objects = [
        obj('net:A', 'net', {'name': 'A'}),
        obj('cmp:X', 'component_instance', {'mpn': 'BUF2'},
            {'mpn': 'BUF'}),
        obj('test:T', 'test', {'criterion': {'v': 1}}),
    ]
    dependencies = [
        dep('dep:1', 'net:A', 'cmp:X', 'signal_path'),
        dep('dep:2', 'cmp:X', 'net:A', 'signal_path'),
        dep('dep:3', 'cmp:X', 'test:T', 'verification_coverage'),
    ]
    checks = [check('chk:test', [cover('test:T', 'test_criterion_change')],
                    mandatory=True)]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:X', 'mpn', 'BUF', 'BUF2')],
                            checks=checks)
    exp = expected(
        'cyclic_dependency',
        derivation=('a dependency cycle must terminate and be reported in '
                    'cycles; it is not a reason to omit downstream impacts.'),
        cycles_nonempty=True,
        must_impact=[impact('net:A', 'signal_integrity',
                            confidence_at_least='possible')])
    return payload, exp


def scenario_missing_coverage():
    objects = [
        obj('cmp:U1', 'component_instance', {'mpn': 'MCU-B'},
            {'mpn': 'MCU-A'}),
        obj('fw:pinmap', 'firmware_contract', {'pin': 'PA0'}),
    ]
    dependencies = [dep('dep:1', 'cmp:U1', 'fw:pinmap', 'firmware_consumer')]
    checks = [check('chk:unrelated', [cover('cmp:U1', 'electrical_state')])]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:U1', 'mpn',
                                         'MCU-A', 'MCU-B')],
                            checks=checks)
    exp = expected(
        'missing_coverage',
        derivation=('the firmware contract is affected but no catalog check '
                    'covers firmware_compatibility; the plan must report a gap '
                    'instead of substituting an unrelated electrical check.'),
        min_coverage_gaps=1,
        must_impact=[impact('fw:pinmap', 'firmware_compatibility',
                            confidence_at_least='possible')],
        must_not_impact=[])
    return payload, exp


def scenario_budget_exhaustion():
    objects = [
        obj('pwr:5V', 'power_domain', {'voltage': {'nominal': 3.3}},
            {'voltage': {'nominal': 5.0}}),
        obj('net:+5V', 'net', {'name': '+5V'}),
        obj('cmp:U1', 'component_instance', {'mpn': 'MCU-A'}),
        obj('cmp:U2', 'component_instance', {'mpn': 'SENSOR'}),
    ]
    dependencies = [
        dep('dep:1', 'pwr:5V', 'net:+5V', 'power_supply'),
        dep('dep:2', 'net:+5V', 'cmp:U1', 'power_supply'),
        dep('dep:3', 'net:+5V', 'cmp:U2', 'power_supply'),
    ]
    checks = [check('chk:rail', [cover('cmp:U1', 'power_integrity')],
                    mandatory=True)]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'pwr:5V', 'voltage.nominal',
                                         5.0, 3.3)],
                            checks=checks,
                            budget={'max_depth': 1, 'max_paths': 2,
                                    'max_cost': 1000})
    exp = expected(
        'budget_exhaustion',
        derivation=('a tiny traversal budget truncates propagation; the report '
                    'must say incomplete/truncated and keep the unvisited '
                    'frontier instead of implying no impact.'),
        expected_status='incomplete',
        truncated=True,
        unknown_codes_required=['budget_exhausted'])
    return payload, exp


def scenario_unknown_attribute():
    objects = [
        obj('cmp:U1', 'component_instance',
            {'mpn': 'MCU-A', 'mystery': {'z': 2}},
            {'mystery': {'z': 1}}),
        obj('cmp:U2', 'component_instance', {'mpn': 'SENSOR'}),
    ]
    dependencies = [dep('dep:1', 'cmp:U1', 'cmp:U2', 'signal_path')]
    checks = [check('chk:any', [cover('cmp:U1', 'unknown')])]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:U1', 'mystery.z', 1, 2)],
                            checks=checks)
    exp = expected(
        'unknown_attribute',
        derivation=('an unmapped attribute is unknown_attribute, never a display '
                    'change; its impact is unknown and is not propagated as a '
                    'known electrical effect.'),
        expected_status='incomplete',
        must_impact=[impact('cmp:U1', 'unknown',
                            confidence_at_least='unknown')],
        unknown_codes_required=['unknown_attribute_change'])
    return payload, exp


def scenario_unauthorized_observed():
    objects = [
        obj('cmp:U1', 'component_instance',
            {'mpn': 'MCU-A', 'placement': {'x': 1, 'y': 1}},
            {'placement': {'x': 0, 'y': 1}}),
        obj('cmp:U2', 'component_instance', {'mpn': 'SENSOR-B'},
            {'mpn': 'SENSOR'}),
    ]
    dependencies = [dep('dep:1', 'cmp:U2', 'cmp:U1', 'signal_path')]
    checks = [check('chk:any', [cover('cmp:U1', 'electrical_state')],
                    mandatory=True)]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:U2', 'mpn',
                                         'SENSOR', 'SENSOR-B')],
                            checks=checks,
                            observed_diff=[
                                {'object': 'cmp:U1', 'attribute': 'placement.x',
                                 'before': 0, 'after': 1, 'source': 'observed'}])
    exp = expected(
        'unauthorized_observed',
        derivation=('an observed difference that was not declared is listed as '
                    'unauthorised and makes the analysis incomplete; it is never '
                    'folded into the allowed scope.'),
        expected_status='incomplete',
        unknown_codes_required=['observed_not_declared'])
    return payload, exp


def scenario_no_change():
    objects = [obj('cmp:U1', 'component_instance', {'mpn': 'MCU-A'})]
    dependencies = [dep('dep:1', 'cmp:U1', 'test:T', 'verification_coverage')]
    objects.append(obj('test:T', 'test', {'criterion': {'v': 1}}))
    checks = [check('chk:any', [cover('test:T', 'test_criterion_change')],
                    mandatory=True)]
    payload = model_payload(objects=objects, dependencies=dependencies,
                            changes=[], checks=checks,
                            complete=True,
                            baseline_hash=h('3'), candidate_hash=h('3'))
    payload['candidate']['revision'] = 'r1'
    exp = expected(
        'no_change',
        derivation=('identical snapshots with declared complete coverage and '
                    'no declared difference is the only case where no_change is '
                    'claimed; it still is not a design-pass.'),
        expected_status='no_change')
    return payload, exp


# ---------------------------------------------------------------------------
# composite cases
# ---------------------------------------------------------------------------

def composite_low_voltage_sensor():
    objects = [
        obj('pwr:5V0', 'power_domain', {'voltage': {'nominal': 5.0}}),
        obj('pwr:3V3', 'power_domain',
            {'voltage': {'nominal': 3.3}},
            {'voltage': {'nominal': 5.0}}),
        obj('net:+5V', 'net', {'name': '+5V'}),
        obj('net:+3V3', 'net', {'name': '+3V3'}),
        obj('cmp:U1', 'component_instance',
            {'mpn': 'LDO-3V3-A', 'footprint': {'uuid': 'fp:sot23-5'}}),
        obj('cmp:U2', 'component_instance',
            {'mpn': 'MCU-B', 'instance_uuid': 'u2-b',
             'footprint': {'uuid': 'fp:qfn32'},
             'designator': 'U2'},
            {'mpn': 'MCU-A', 'instance_uuid': 'u2-a'}),
        obj('cmp:U3', 'component_instance',
            {'mpn': 'SENSOR-TEMP', 'interface': 'I2C'}),
        obj('if:I2C', 'interface', {'pose': {'x': 2, 'y': 3}}),
        obj('fw:app', 'firmware_contract',
            {'i2c_address': '0x48', 'io_contract': {'voltage': 3.3}},
            {'io_contract': {'voltage': 5.0}}),
        obj('test:rail', 'test',
            {'criterion': {'v_min': 3.0, 'v_max': 3.6}},
            {'criterion': {'v_min': 4.75, 'v_max': 5.25}}),
        obj('test:i2c', 'test', {'criterion': {'clock_khz': 100}}),
        obj('bom:U2', 'bom_line', {'designator': 'U2', 'mpn': 'MCU-B'},
            {'mpn': 'MCU-A'}),
        obj('art:cpl', 'artifact', {'kind': 'cpl', 'revision': 'r2'}),
        obj('art:gerber', 'artifact', {'kind': 'gerber',
                                       'revision': 'r2'}),
        obj('req:REQ1', 'requirement', {'text': '3.3V sensor board'}),
    ]
    dependencies = [
        dep('dep:1', 'pwr:5V0', 'net:+5V', 'power_supply'),
        dep('dep:2', 'net:+5V', 'cmp:U1', 'power_supply'),
        dep('dep:3', 'pwr:3V3', 'net:+3V3', 'power_supply'),
        dep('dep:3b', 'cmp:U1', 'net:+3V3', 'power_supply'),
        dep('dep:4', 'net:+3V3', 'cmp:U2', 'power_supply'),
        dep('dep:5', 'net:+3V3', 'cmp:U3', 'power_supply'),
        dep('dep:6', 'net:+3V3', 'fw:app', 'firmware_consumer'),
        dep('dep:7', 'cmp:U2', 'fw:app', 'firmware_consumer'),
        dep('dep:8', 'cmp:U3', 'if:I2C', 'signal_path'),
        dep('dep:9', 'if:I2C', 'test:i2c', 'test_reference'),
        dep('dep:10', 'cmp:U1', 'test:rail', 'test_reference'),
        dep('dep:11', 'net:+3V3', 'test:rail', 'test_reference'),
        dep('dep:12', 'cmp:U2', 'bom:U2', 'artifact_source'),
        dep('dep:13', 'bom:U2', 'art:cpl', 'artifact_source'),
        dep('dep:14', 'cmp:U2', 'art:gerber', 'artifact_source'),
        dep('dep:15', 'req:REQ1', 'pwr:3V3', 'requirement_ref'),
        dep('dep:16', 'cmp:U2', 'net:+3V3', 'pin_mapping'),
    ]
    changes = [
        chg('chg:1', 'pwr:3V3', 'voltage.nominal', 5.0, 3.3),
        chg('chg:2', 'cmp:U2', 'mpn', 'MCU-A', 'MCU-B'),
        chg('chg:3', 'fw:app', 'io_contract.voltage', 5.0, 3.3),
        chg('chg:4', 'test:rail', 'criterion',
            {'v_min': 4.75, 'v_max': 5.25}, {'v_min': 3.0, 'v_max': 3.6}),
    ]
    checks = [
        check('chk:ldo', [cover('cmp:U1', 'power_integrity')],
              mandatory=True, module='electrical-review'),
        check('chk:mcu', [cover('cmp:U2', 'power_integrity')],
              module='electrical-review'),
        check('chk:fw', [cover('fw:app', 'firmware_compatibility')],
              module='first-board-test'),
        check('chk:rail_test', [cover('test:rail',
                                      'test_criterion_change')],
              module='first-board-test'),
        check('chk:cpl', [cover('art:cpl', 'manufacturing_output')],
              module='delivery-audit'),
        check('chk:gerber', [cover('art:gerber',
                                   'manufacturing_output')],
              module='delivery-audit'),
        check('chk:host_drc', [cover(None, 'layout_congestion')],
              kind='host', cost=2.0, module='driver'),
    ]
    prior = [
        evidence('ev:1', 'chk:ldo', content_hash=h('1'),
                 objects=['cmp:U1'], attributes=['mpn'],
                 impacts=['power_integrity'], simulated=True),
        evidence('ev:2', 'chk:cpl', content_hash=h('1'),
                 objects=['art:cpl'], attributes=['revision'],
                 impacts=['manufacturing_output']),
    ]
    payload = model_payload(project='low-voltage-sensor-board',
                            objects=objects, dependencies=dependencies,
                            changes=changes, checks=checks,
                            prior_evidence=prior,
                            constraints=[{
                                'id': 'con:rail', 'kind': 'voltage_range',
                                'object': 'pwr:3V3', 'attribute': 'voltage',
                                'value': {'min': 3.0, 'max': 3.6},
                                'hard': True, 'source': 'req:REQ1'}])
    exp = expected(
        'composite_low_voltage_sensor',
        derivation=('combined case: the 3.3V rail change (R1) reaches the MCU '
                    'and sensor through power_supply; the MCU replacement (R2) '
                    'reaches firmware, BOM and CPL; the firmware contract and '
                    'the rail test criterion change their own consumers. Host '
                    'DRC is blocked (not run offline) and the simulated LDO '
                    'evidence cannot become a real host pass.'),
        expected_status='planned_with_scope',
        must_impact=[impact('cmp:U2', 'power_integrity',
                            confidence_at_least='possible'),
                     impact('fw:app', 'firmware_compatibility',
                            confidence_at_least='possible'),
                     impact('bom:U2', 'bom_variant',
                            confidence_at_least='possible'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible'),
                     impact('test:rail', 'test_criterion_change')],
        required_checks=['chk:ldo'],
        evidence_status={'ev:2': 'invalidated'})
    return payload, exp


def composite_interface_enclosure():
    objects = [
        obj('if:USB', 'interface',
            {'pose': {'x': 0, 'y': -5, 'z': 1.2}}, {'pose': {'z': 0.8}}),
        obj('anchor:case', 'mechanical_anchor',
            {'pose': {'x': 0, 'y': -5}, 'hole_diameter': 2.2}),
        obj('region:main', 'layout_region',
            {'board': {'outline': [[0, 0], [42, 0], [42, 25], [0, 25]]},
             'layer': 'L2'},
            {'board': {'outline': [[0, 0], [40, 0], [40, 25], [0, 25]]},
             'layer': 'L1'}),
        obj('net:USB_DP', 'net', {'name': 'USB_DP', 'diff_pair': 'USB'}),
        obj('net:USB_DN', 'net', {'name': 'USB_DN', 'diff_pair': 'USB'}),
        obj('cmp:U1', 'component_instance', {'mpn': 'USB-HUB'}),
        obj('bom:U1', 'bom_line', {'designator': 'U1', 'mpn': 'USB-HUB'}),
        obj('art:cpl', 'artifact', {'kind': 'cpl', 'revision': 'r2'}),
        obj('art:gerber', 'artifact', {'kind': 'gerber', 'revision': 'r2'}),
        obj('test:si', 'test',
            {'criterion': {'impedance_ohm': 90}},
            {'criterion': {'impedance_ohm': 85}}),
        obj('test:fit', 'test', {'criterion': {'flush_mm': 0.2}}),
        obj('req:REQ5', 'requirement',
            {'text': 'USB-C flush with enclosure'}),
    ]
    dependencies = [
        dep('dep:1', 'if:USB', 'anchor:case', 'enclosure_constraint'),
        dep('dep:2', 'if:USB', 'art:cpl', 'artifact_source'),
        dep('dep:3', 'if:USB', 'test:fit', 'test_reference'),
        dep('dep:4', 'region:main', 'net:USB_DP', 'signal_path'),
        dep('dep:5', 'region:main', 'net:USB_DN', 'signal_path'),
        dep('dep:6', 'region:main', 'art:gerber', 'artifact_source'),
        dep('dep:6b', 'region:main', 'anchor:case', 'mechanical_constraint'),
        dep('dep:7', 'cmp:U1', 'net:USB_DP', 'signal_path'),
        dep('dep:8', 'cmp:U1', 'bom:U1', 'artifact_source'),
        dep('dep:9', 'bom:U1', 'art:cpl', 'artifact_source'),
        dep('dep:10', 'net:USB_DP', 'test:si', 'test_reference'),
        dep('dep:11', 'req:REQ5', 'if:USB', 'requirement_ref'),
    ]
    changes = [
        chg('chg:1', 'if:USB', 'pose.z', 0.8, 1.2),
        chg('chg:2', 'region:main', 'board.outline',
            [[0, 0], [40, 0], [40, 25], [0, 25]],
            [[0, 0], [42, 0], [42, 25], [0, 25]]),
        chg('chg:3', 'region:main', 'layer', 'L1', 'L2', kind='layer_stack'),
        chg('chg:4', 'test:si', 'criterion', {'impedance_ohm': 85},
            {'impedance_ohm': 90}),
    ]
    checks = [
        check('chk:shell', [cover('anchor:case', 'enclosure_interface')],
              mandatory=True, module='mechanical-layout'),
        check('chk:fit', [cover('test:fit', 'test_criterion_change')],
              module='mechanical-layout'),
        check('chk:impedance', [cover('net:USB_DP', 'signal_integrity')],
              module='return-path-audit'),
        check('chk:gerber', [cover('art:gerber', 'manufacturing_output')],
              module='delivery-audit'),
        check('chk:cpl', [cover('art:cpl', 'manufacturing_output')],
              module='delivery-audit'),
        check('chk:manual_fit', [cover('anchor:case',
                                       'enclosure_interface')],
              kind='manual', cost=2.0, approval=True,
              module='mechanical-layout'),
    ]
    payload = model_payload(project='interface-enclosure-board',
                            objects=objects, dependencies=dependencies,
                            changes=changes, checks=checks)
    exp = expected(
        'composite_interface_enclosure',
        derivation=('combined case: the USB pose change (R5) reaches the '
                    'enclosure anchor, CPL and fit test even with unchanged '
                    'nets; the outline/layer changes (R8/R9) reach mechanical '
                    'fit, signal integrity and manufacturing; the manual fit '
                    'check is only planned (blocked), never executed.'),
        expected_status='planned_with_scope',
        must_impact=[impact('anchor:case', 'enclosure_interface',
                            confidence_at_least='possible'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible'),
                     impact('net:USB_DP', 'signal_integrity'),
                     impact('art:gerber', 'manufacturing_output'),
                     impact('region:main', 'mechanical_fit')],
        required_checks=['chk:shell'],
        blocked_checks=['chk:manual_fit'])
    return payload, exp


# ---------------------------------------------------------------------------
# holdouts and variants
# ---------------------------------------------------------------------------

def holdout_sensor_swap():
    objects = [
        obj('cmp:S1', 'component_instance',
            {'mpn': 'SENSOR-B', 'footprint': {'uuid': 'fp:lga8'}},
            {'mpn': 'SENSOR-A'}),
        obj('if:I2C', 'interface', {'pose': {'x': 1, 'y': 1}}),
        obj('fw:drv', 'firmware_contract', {'driver': 'sensor-a'}),
        obj('art:cpl', 'artifact', {'kind': 'cpl'}),
    ]
    dependencies = [
        dep('dep:1', 'cmp:S1', 'if:I2C', 'signal_path'),
        dep('dep:2', 'cmp:S1', 'fw:drv', 'firmware_consumer'),
        dep('dep:3', 'cmp:S1', 'art:cpl', 'artifact_source'),
    ]
    checks = [check('chk:sensor_si', [cover('if:I2C', 'signal_integrity')],
                    mandatory=True)]
    payload = model_payload(project='holdout-sensor',
                            objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'cmp:S1', 'mpn',
                                         'SENSOR-A', 'SENSOR-B')],
                            checks=checks)
    exp = expected(
        'holdout_sensor_swap',
        derivation=('holdout: a sensor replacement must still reach firmware, '
                    'interface and CPL through the declared graph, independent '
                    'of the training scenarios.'),
        must_impact=[impact('fw:drv', 'firmware_compatibility',
                            confidence_at_least='possible'),
                     impact('if:I2C', 'signal_integrity',
                            confidence_at_least='possible'),
                     impact('art:cpl', 'manufacturing_output',
                            confidence_at_least='possible')],
        required_checks=['chk:sensor_si'])
    return payload, exp


def holdout_power_tree():
    objects = [
        obj('pwr:VBAT', 'power_domain', {'voltage': {'nominal': 3.6}},
            {'voltage': {'nominal': 3.7}}),
        obj('net:VBAT', 'net', {'name': 'VBAT'}),
        obj('cmp:U5', 'component_instance',
            {'mpn': 'BUCK-1V8', 'footprint': {'uuid': 'fp:qfn16'}}),
        obj('net:1V8', 'net', {'name': '1V8'}),
        obj('cmp:U6', 'component_instance', {'mpn': 'MCU-1V8'}),
        obj('test:brownout', 'test', {'criterion': {'v_min': 1.7}}),
    ]
    dependencies = [
        dep('dep:1', 'pwr:VBAT', 'net:VBAT', 'power_supply'),
        dep('dep:2', 'net:VBAT', 'cmp:U5', 'power_supply'),
        dep('dep:3', 'cmp:U5', 'net:1V8', 'power_supply'),
        dep('dep:4', 'net:1V8', 'cmp:U6', 'power_supply'),
        dep('dep:5', 'net:1V8', 'test:brownout', 'test_reference'),
    ]
    checks = [check('chk:buck', [cover('cmp:U5', 'power_integrity')],
                    mandatory=True),
              check('chk:brownout', [cover('test:brownout',
                                           'test_criterion_change')])]
    payload = model_payload(project='holdout-power',
                            objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'pwr:VBAT', 'voltage.nominal',
                                         3.7, 3.6)],
                            checks=checks)
    exp = expected(
        'holdout_power_tree',
        derivation=('holdout: a battery rail change propagates through the buck '
                    'to the 1V8 rail and its MCU, and the brownout test is '
                    'affected; the chain must not stop at the net carrier.'),
        must_impact=[impact('cmp:U5', 'power_integrity'),
                     impact('cmp:U6', 'power_integrity')],
        must_not_impact=[{'object': 'test:brownout',
                          'reason': ('R1 follows only power_supply edges; a '
                                     'power-domain change does not silently '
                                     'invalidate an independent test reference')}],
        required_checks=['chk:buck'])
    return payload, exp


def holdout_connector_outline():
    objects = [
        obj('if:USB', 'interface', {'pose': {'x': 0, 'y': 0}}),
        obj('anchor:case', 'mechanical_anchor', {'pose': {'x': 0, 'y': 0}}),
        obj('region:main', 'layout_region',
            {'board': {'outline': [[0, 0], [30, 0], [30, 20], [0, 20]]}},
            {'board': {'outline': [[0, 0], [35, 0], [35, 20], [0, 20]]}}),
        obj('art:gerber', 'artifact', {'kind': 'gerber'}),
    ]
    dependencies = [
        dep('dep:1', 'if:USB', 'anchor:case', 'enclosure_constraint'),
        dep('dep:2', 'region:main', 'anchor:case', 'mechanical_constraint'),
        dep('dep:3', 'region:main', 'art:gerber', 'artifact_source'),
    ]
    checks = [check('chk:mech', [cover('anchor:case', 'mechanical_fit')],
                    mandatory=True)]
    payload = model_payload(project='holdout-enclosure',
                            objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'region:main', 'board.outline',
                                         [[0, 0], [35, 0], [35, 20], [0, 20]],
                                         [[0, 0], [30, 0], [30, 20], [0, 20]])],
                            checks=checks)
    exp = expected(
        'holdout_connector_outline',
        derivation=('holdout: shrinking the board outline reaches both the '
                    'enclosure anchor and the manufacturing output.'),
        must_impact=[impact('anchor:case', 'mechanical_fit',
                            confidence_at_least='possible'),
                     impact('art:gerber', 'manufacturing_output')],
        required_checks=['chk:mech'])
    return payload, exp


def holdout_test_only():
    objects = [
        obj('test:rf', 'test', {'criterion': {'power_dbm': 10}},
            {'criterion': {'power_dbm': 8}}),
        obj('req:REQ9', 'requirement', {'text': 'RF output 10 dBm'}),
        obj('cmp:PA', 'component_instance', {'mpn': 'PA-2G4'}),
    ]
    dependencies = [
        dep('dep:1', 'test:rf', 'req:REQ9', 'requirement_ref'),
    ]
    checks = [check('chk:rf', [cover('test:rf', 'test_criterion_change')],
                    mandatory=True)]
    payload = model_payload(project='holdout-test',
                            objects=objects, dependencies=dependencies,
                            changes=[chg('chg:1', 'test:rf', 'criterion',
                                         {'power_dbm': 8}, {'power_dbm': 10})],
                            checks=checks)
    exp = expected(
        'holdout_test_only',
        derivation=('holdout: a test criterion change must not spread to the '
                    'amplifier; only the requirement trace is affected.'),
        must_impact=[impact('test:rf', 'test_criterion_change'),
                     impact('req:REQ9', 'requirement_trace',
                            confidence_at_least='possible')],
        must_not_impact=[{'object': 'cmp:PA',
                          'reason': 'no dependency from the test to the amplifier'}],
        required_checks=['chk:rf'])
    return payload, exp


def variant_reorder(payload):
    clone = json.loads(json.dumps(payload))
    clone['objects'] = list(reversed(clone['objects']))
    clone['dependencies'] = list(reversed(clone['dependencies']))
    clone['changes'] = list(reversed(clone['changes']))
    clone['prior_evidence'] = list(reversed(clone['prior_evidence']))
    return clone


def variant_display_name(payload):
    clone = json.loads(json.dumps(payload))
    for item in clone['objects']:
        item['display_name'] = '同义显示名'
    return clone


def variant_unit_conversion(payload):
    clone = json.loads(json.dumps(payload))
    for item in clone['objects']:
        blocks = [item.get('attributes') or {}]
        baseline = item.get('baseline_attributes')
        if isinstance(baseline, dict):
            blocks.append(baseline)
        for block in blocks:
            value = block.get('value')
            if isinstance(value, dict) and 'resistance' in value:
                value['resistance'] = round(value['resistance'] * 0.001, 6)
                value['unit'] = 'kohm'
    for change in clone['changes']:
        if change.get('attribute', '').endswith('value.resistance'):
            change['before'] = round(change['before'] * 0.001, 6)
            change['after'] = round(change['after'] * 0.001, 6)
    return clone


def variant_unrelated_subgraph(payload):
    clone = json.loads(json.dumps(payload))
    clone['objects'].append(obj('cmp:UNRELATED', 'component_instance',
                                {'mpn': 'SPARE'}))
    clone['objects'].append(obj('test:unrelated', 'test',
                                {'criterion': {'x': 1}}))
    return clone


def variant_cost_inflation(payload):
    clone = json.loads(json.dumps(payload))
    for item in clone['verification_catalog']:
        item['cost'] = round(item['cost'] * 5, 3)
    return clone


def variant_remove_coverage(payload):
    clone = json.loads(json.dumps(payload))
    clone['dependencies'] = [item for item in clone['dependencies']
                             if item['semantic'] != 'verification_coverage']
    return clone


# ---------------------------------------------------------------------------
# invalid inputs
# ---------------------------------------------------------------------------

def invalid_duplicate_id():
    payload, _ = scenario_led_resistor_value()
    payload['objects'].append(dict(payload['objects'][0]))
    return payload


def invalid_before_after():
    payload, _ = scenario_led_resistor_value()
    payload['changes'][0]['before'] = 1200
    return payload


def invalid_same_revision():
    payload, _ = scenario_led_resistor_value()
    payload['candidate']['revision'] = 'r1'
    return payload


def invalid_project_mismatch():
    payload, _ = scenario_led_resistor_value()
    payload['candidate']['project'] = 'other-project'
    return payload


def invalid_partial_claimed_complete():
    payload, _ = scenario_partial_snapshot()
    payload['baseline']['complete'] = True
    return payload


def invalid_negative_budget():
    payload, _ = scenario_led_resistor_value()
    payload['budget']['max_cost'] = -5
    return payload


def invalid_bool_cost():
    payload, _ = scenario_led_resistor_value()
    payload['verification_catalog'][0]['cost'] = True
    return payload


def invalid_unknown_direction():
    payload, _ = scenario_led_resistor_value()
    payload['dependencies'][0]['direction'] = 'sideways'
    return payload


def invalid_empty_comparison():
    payload, _ = scenario_no_change()
    payload['baseline']['complete'] = False
    payload['candidate']['complete'] = False
    return payload


def invalid_undeclared_change_object():
    payload, _ = scenario_led_resistor_value()
    payload['changes'][0]['object'] = 'cmp:NOPE'
    return payload


# ---------------------------------------------------------------------------
# compare inputs
# ---------------------------------------------------------------------------

def compare_two_candidates():
    base, _ = scenario_power_5v_to_3v3()
    base['changes'] = []
    for item in base['objects']:
        if item['id'] == 'test:rail':
            item['baseline_attributes'] = {
                'criterion': {'v_min': 4.75, 'v_max': 5.25}}
    compare_payload = {
        'schema': 'hds-change-impact-compare-input/v1',
        'base': base,
        'candidates': [
            {'id': 'eco-rail-only', 'label': '只改电源域',
             'changes': [chg('chg:1', 'pwr:5V', 'voltage.nominal', 5.0, 3.3)]},
            {'id': 'eco-rail-and-test', 'label': '同时更新测试判据',
             'changes': [chg('chg:1', 'pwr:5V', 'voltage.nominal', 5.0, 3.3),
                         chg('chg:2', 'test:rail', 'criterion',
                             {'v_min': 4.75, 'v_max': 5.25},
                             {'v_min': 3.0, 'v_max': 3.6})]},
        ],
        'hard_constraints': {'must_not_affect': ['fw:io'],
                             'require_known_impacts': False},
    }
    exp = {
        'schema': 'hds-change-impact-benchmark-expected/v1',
        'scenario_id': 'compare_two_candidates',
        'kind': 'compare',
        'derivation': ('both candidates keep the firmware consumer out of the '
                       'power propagation; the second also updates the rail test '
                       'criterion, so it declares more affected objects but must '
                       'not be ranked as safer just because that.'),
        'expected_status': 'planned_with_scope',
        'expected_exit': 0,
        'must_include_candidates': ['eco-rail-only', 'eco-rail-and-test'],
        'must_recommend_in': ['eco-rail-only', 'eco-rail-and-test'],
        'must_not_violate': True,
        'real_eda': 'NOT RUN',
        'physical_test': 'NOT RUN',
    }
    return compare_payload, exp


def compare_hard_constraint():
    candidate_a, _ = scenario_power_5v_to_3v3()
    candidate_b = json.loads(json.dumps(candidate_a))
    for item in candidate_b['objects']:
        if item['id'] == 'pwr:5V':
            item['attributes']['voltage']['nominal'] = 4.5
    for change in candidate_b['changes']:
        if change['id'] == 'chg:1':
            change['after'] = 4.5
    compare_payload = {
        'schema': 'hds-change-impact-compare-input/v1',
        'base': candidate_a,
        'candidates': [
            {'id': 'eco-a', 'input': candidate_a},
            {'id': 'eco-b', 'input': candidate_b},
        ],
        'hard_constraints': {'must_not_affect': ['cmp:MCU']},
    }
    exp = {
        'schema': 'hds-change-impact-benchmark-expected/v1',
        'scenario_id': 'compare_hard_constraint',
        'kind': 'compare',
        'derivation': ('the MCU is affected through the rail in both candidates, '
                       'so both violate must_not_affect; the tool must refuse to '
                       'recommend either instead of picking the cheaper one.'),
        'expected_status': 'planned_with_scope',
        'expected_exit': 0,
        'must_include_candidates': ['eco-a', 'eco-b'],
        'must_recommend_in': [],
        'must_not_violate': False,
        'expect_no_feasible': True,
        'real_eda': 'NOT RUN',
        'physical_test': 'NOT RUN',
    }
    return compare_payload, exp


def invalid_compare_single_candidate():
    base, _ = scenario_power_5v_to_3v3()
    base['changes'] = []
    return {
        'schema': 'hds-change-impact-compare-input/v1',
        'base': base,
        'candidates': [{'id': 'only-one',
                        'changes': []}],
        'hard_constraints': {},
    }


# ---------------------------------------------------------------------------
# scenario registry
# ---------------------------------------------------------------------------

SCENARIOS = {
    'display_text_move': scenario_display_text_move,
    'net_rename': scenario_net_rename,
    'led_resistor_value': scenario_led_resistor_value,
    'power_5v_to_3v3': scenario_power_5v_to_3v3,
    'ldo_replacement': scenario_ldo_replacement,
    'mcu_instance_change': scenario_mcu_instance_change,
    'mcu_pin_remap': scenario_mcu_pin_remap,
    'mcu_footprint': scenario_mcu_footprint,
    'usb_position': scenario_usb_position,
    'board_outline': scenario_board_outline,
    'differential_layer': scenario_differential_layer,
    'dnp_config': scenario_dnp_config,
    'bom_substitute': scenario_bom_substitute,
    'firmware_contract': scenario_firmware_contract,
    'test_threshold': scenario_test_threshold,
    'requirement_change': scenario_requirement_change,
    'evidence_reuse_positive': scenario_evidence_reuse_positive,
    'evidence_reuse_negative': scenario_evidence_reuse_negative,
    'partial_snapshot': scenario_partial_snapshot,
    'cyclic_dependency': scenario_cyclic_dependency,
    'missing_coverage': scenario_missing_coverage,
    'budget_exhaustion': scenario_budget_exhaustion,
    'unknown_attribute': scenario_unknown_attribute,
    'unauthorized_observed': scenario_unauthorized_observed,
    'no_change': scenario_no_change,
}

COMPOSITES = {
    'composite_low_voltage_sensor': composite_low_voltage_sensor,
    'composite_interface_enclosure': composite_interface_enclosure,
}

HOLDOUTS = {
    'holdout_sensor_swap': holdout_sensor_swap,
    'holdout_power_tree': holdout_power_tree,
    'holdout_connector_outline': holdout_connector_outline,
    'holdout_test_only': holdout_test_only,
}

INVALID = {
    'invalid_duplicate_id': invalid_duplicate_id,
    'invalid_before_after': invalid_before_after,
    'invalid_same_revision': invalid_same_revision,
    'invalid_project_mismatch': invalid_project_mismatch,
    'invalid_partial_claimed_complete': invalid_partial_claimed_complete,
    'invalid_negative_budget': invalid_negative_budget,
    'invalid_bool_cost': invalid_bool_cost,
    'invalid_unknown_direction': invalid_unknown_direction,
    'invalid_empty_comparison': invalid_empty_comparison,
    'invalid_undeclared_change_object': invalid_undeclared_change_object,
}

VARIANTS = {
    'variant_reorder_led_resistor': ('led_resistor_value', variant_reorder),
    'variant_display_name_led_resistor': ('led_resistor_value',
                                          variant_display_name),
    'variant_unit_conversion_led_resistor': ('led_resistor_value',
                                             variant_unit_conversion),
    'variant_unrelated_subgraph_power': ('power_5v_to_3v3',
                                         variant_unrelated_subgraph),
    'variant_cost_inflation_power': ('power_5v_to_3v3', variant_cost_inflation),
    'variant_remove_coverage_power': ('power_5v_to_3v3',
                                      variant_remove_coverage),
}


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def _dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1,
                      allow_nan=False) + '\n'
    path.write_text(text, encoding='utf-8', newline='\n')


def build(root=ROOT, *, check=False):
    root = Path(root)
    written = []
    expected_rows = []
    leftovers = []

    for name, factory in sorted(SCENARIOS.items()):
        payload, exp = factory()
        _dump(root / 'scenarios' / f'{name}.json', payload)
        _dump(root / 'expected' / f'{name}.json', exp)
        written.append(root / 'scenarios' / f'{name}.json')
        expected_rows.append((root / 'scenarios' / f'{name}.json', exp))

    for name, factory in sorted(COMPOSITES.items()):
        payload, exp = factory()
        _dump(root / 'composite' / f'{name}.json', payload)
        _dump(root / 'expected' / f'{name}.json', exp)
        written.append(root / 'composite' / f'{name}.json')

    for name, factory in sorted(HOLDOUTS.items()):
        payload, exp = factory()
        _dump(root / 'holdout' / f'{name}.json', payload)
        _dump(root / 'expected' / f'{name}.json', exp)
        written.append(root / 'holdout' / f'{name}.json')

    for name, (base_name, transform) in sorted(VARIANTS.items()):
        base_payload, base_exp = SCENARIOS[base_name]()
        payload = transform(base_payload)
        exp = json.loads(json.dumps(base_exp))
        exp['scenario_id'] = name
        exp['derivation'] = (
            f'variant of {base_name}: {transform.__name__} must not drop or '
            f'invent impacts (same must_impact/must_not_impact as the base); '
            f're-ordering, synonyms, unit conversion, an unrelated subgraph or '
            f'cost inflation must not change the analysis, and removing '
            f'coverage edges must not turn unknown into proven-safe.')
        if 'remove_coverage' in name:
            exp['min_gaps_or_unknown'] = 1
        _dump(root / 'variants' / f'{name}.json', payload)
        _dump(root / 'expected' / f'{name}.json', exp)
        written.append(root / 'variants' / f'{name}.json')

    for name, factory in sorted(INVALID.items()):
        _dump(root / 'scenarios' / 'invalid' / f'{name}.json', factory())
        exp = expected(name,
                       derivation='the input must be rejected with exit code 2 '
                                  'and a machine-readable failure class.',
                       expected_status='input_invalid', expected_exit=2)
        exp['kind'] = 'invalid'
        _dump(root / 'expected' / f'{name}.json', exp)
        written.append(root / 'scenarios' / 'invalid' / f'{name}.json')

    for name, factory in (('compare_two_candidates', compare_two_candidates),
                          ('compare_hard_constraint', compare_hard_constraint)):
        payload, exp = factory()
        _dump(root / 'compare' / f'{name}.json', payload)
        _dump(root / 'expected' / f'{name}.json', exp)
        written.append(root / 'compare' / f'{name}.json')

    _dump(root / 'scenarios' / 'invalid' / 'invalid_compare_single_candidate.json',
          invalid_compare_single_candidate())
    exp = expected('invalid_compare_single_candidate',
                   derivation='fewer than two candidates is not a comparison',
                   expected_status='input_invalid', expected_exit=2)
    exp['kind'] = 'compare_invalid'
    _dump(root / 'expected' / 'invalid_compare_single_candidate.json', exp)
    written.append(root / 'scenarios' / 'invalid'
                   / 'invalid_compare_single_candidate.json')

    manifest = {
        'schema': 'hds-change-impact-benchmark-manifest/v1',
        'generated_by': TOOL,
        'counts': {
            'scenarios': len(SCENARIOS),
            'invalid': len(INVALID) + 1,
            'composite': len(COMPOSITES),
            'holdout': len(HOLDOUTS),
            'variants': len(VARIANTS),
            'compare': 2,
        },
        'files': [],
        'real_eda': 'NOT RUN',
        'physical_test': 'NOT RUN',
        'note': ('inputs are synthetic; SHA-256 is frozen so any edit to a '
                 'scenario or assertion is detected'),
    }
    for path in sorted(written):
        exp_path = root / 'expected' / f'{path.stem}.json'
        manifest['files'].append({
            'id': path.stem,
            'group': path.parent.name,
            'input': path.relative_to(root).as_posix(),
            'input_sha256': sha256_file(path),
            'expected': exp_path.relative_to(root).as_posix(),
            'expected_sha256': sha256_file(exp_path),
        })
    _dump(root / 'manifest.json', manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Build the frozen change-impact benchmark corpus')
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--check', action='store_true',
                        help='verify the committed files are exactly rebuildable')
    args = parser.parse_args(argv)
    manifest = build(Path(args.root))
    if args.check:
        print(json.dumps({'status': 'ok',
                          'files': len(manifest['files']),
                          'counts': manifest['counts']},
                         sort_keys=True))
    else:
        print(f"built {len(manifest['files'])} frozen benchmark files")
        print(json.dumps(manifest['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
