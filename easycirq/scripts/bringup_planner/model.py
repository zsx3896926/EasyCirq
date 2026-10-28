"""Input contract: strict validation, normalisation and the planning context.

The normalised model is the only representation the rest of the planner reads:
all electrical values are in canonical SI units, every collection is sorted by
its stable id, and no safety-relevant value ever receives an invented default.
Missing information is kept as *missing*; the planner turns it into a gap or a
blocked step instead of guessing.

Field names, required groups and status semantics are documented in
``docs/parallel-bringup-planner/contract.md``.
"""
from __future__ import annotations

import math
import re
from datetime import timezone
from pathlib import Path

from . import (SUPPORTED_MAX_ABSOLUTE_DC_V, SUPPORTED_MAX_OPERATING_DC_V,
               SUPPORTED_OPERATIONS, UNSUPPORTED_SUPPLY_CLASSES)
from .units import UnitError, to_canonical
from .util import (Diagnostics, InputInvalid, PlannerError, check_not_future,
                   check_attachment_path, read_json, sha256_bytes,
                   semantic_sha256)

_CURRENT_BASES = ('datasheet', 'calculation', 'project_requirement',
                  'measurement', 'estimate', 'unknown')
_EVIDENCE_KINDS = ('drc', 'netlist', 'bom', 'assembly', 'manufacturing',
                   'visual', 'datasheet', 'measurement', 'other')
_FACT_KINDS = ('device', 'instrument', 'measurement_method')
_INTERFACE_TYPES = ('connector', 'usb', 'uart', 'i2c', 'spi', 'gpio',
                    'analog_input', 'analog_output', 'led', 'button',
                    'load_output', 'bridge_output', 'debug', 'other')
_PIN_ROLES = ('power', 'ground', 'signal', 'nc', 'other')
_OUTPUT_TYPES = ('single_ended_ground_referenced', 'bridge_tied_load',
                 'differential', 'floating_unknown')
_CONTACTS = ('probe_pad', 'header_pin', 'wire_loop', 'test_point', 'clip',
             'unknown')
_GROUNDING = ('earth_referenced', 'differential', 'isolated', 'unknown')
_OPS_RE = re.compile(r'^[a-z][a-z0-9_]{1,39}$')


class _N:
    """Small strict normaliser that accumulates diagnostics."""

    def __init__(self, now=None):
        self.diags = Diagnostics()
        self.now = now

    def fail(self, code, path, message):
        self.diags.error(code, path, message)

    def warn(self, code, path, message):
        self.diags.warning(code, path, message)

    def obj(self, value, path, *, required=(), optional=()):
        if not isinstance(value, dict):
            self.fail('E_TYPE', path, 'object required, got %s'
                      % type(value).__name__)
            return {}
        missing = [key for key in required if key not in value]
        for key in missing:
            self.fail('E_REQUIRED', path, 'missing required field %r' % key)
        allowed = set(required) | set(optional)
        for key in value:
            if key not in allowed:
                self.fail('E_UNKNOWN_FIELD', path,
                          'unknown field %r (allowed: %s)'
                          % (key, ', '.join(sorted(allowed)) or 'none'))
        return {key: value[key] for key in value if key in allowed}

    def string(self, value, path, *, allow_empty=False, max_len=300):
        if value is None:
            # Presence is enforced by the enclosing obj(required=...) call;
            # optional strings and explicit nulls are handled here.
            return None
        if not isinstance(value, str):
            self.fail('E_TYPE', path, 'string required, got %s'
                      % type(value).__name__)
            return None
        text = value.strip()
        if not text and not allow_empty:
            self.fail('E_REQUIRED', path, 'non-empty string required')
            return None
        if len(text) > max_len:
            self.fail('E_TOO_LONG', path, 'string exceeds %d characters'
                      % max_len)
            return None
        return text

    def ident(self, value, path):
        text = self.string(value, path, max_len=64)
        if text is None:
            return None
        if not re.match(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$', text):
            self.fail('E_ID_FORMAT', path,
                      'id must match [A-Za-z0-9][A-Za-z0-9_.:-]*: %r' % value)
            return None
        return text

    def number(self, value, path, *, positive=False, nonnegative=False):
        if type(value) not in (int, float) or isinstance(value, bool):
            self.fail('E_TYPE', path, 'finite number required, got %s %r'
                      % (type(value).__name__, value))
            return None
        if not math.isfinite(value):
            self.fail('E_NONFINITE', path, 'finite number required')
            return None
        if positive and value <= 0:
            self.fail('E_RANGE', path, 'value must be > 0')
            return None
        if nonnegative and value < 0:
            self.fail('E_RANGE', path, 'value must be >= 0')
            return None
        return float(value)

    def scalar(self, value, path, quantity, *, positive=False,
               nonnegative=False):
        """Accept bare canonical-unit number or {"value","unit"} object."""
        if isinstance(value, dict):
            entry = self.obj(value, path, required=('value', 'unit'))
            if 'value' not in entry or 'unit' not in entry:
                return None
            unit = self.string(entry['unit'], path + '.unit', max_len=16)
            raw = self.number(entry['value'], path + '.value')
            if unit is None or raw is None:
                return None
            try:
                converted = to_canonical(raw, unit, quantity)
            except UnitError as exc:
                self.fail('E_UNIT', path, str(exc))
                return None
            value = converted
        else:
            value = self.number(value, path)
            if value is None:
                return None
        if positive and value <= 0:
            self.fail('E_RANGE', path, 'value must be > 0')
            return None
        if nonnegative and value < 0:
            self.fail('E_RANGE', path, 'value must be >= 0')
            return None
        return value

    def boolean(self, value, path):
        if not isinstance(value, bool):
            self.fail('E_TYPE', path, 'boolean required, got %s'
                      % type(value).__name__)
            return None
        return value

    def enum(self, value, path, choices):
        text = self.string(value, path, max_len=64)
        if text is None:
            return None
        if text not in choices:
            self.fail('E_ENUM', path, 'expected one of %s, got %r'
                      % (', '.join(choices), text))
            return None
        return text

    def array(self, value, path, *, min_items=0):
        if not isinstance(value, list):
            self.fail('E_TYPE', path, 'array required, got %s'
                      % type(value).__name__)
            return []
        if len(value) < min_items:
            self.fail('E_RANGE', path, 'at least %d item(s) required'
                      % min_items)
        return value

    def timestamp(self, value, path):
        try:
            parsed = check_not_future(value, path, now=self.now)
        except PlannerError as exc:
            self.fail(exc.code, path, exc.message)
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace(
            '+00:00', 'Z')

    def hex64(self, value, path):
        text = self.string(value, path, max_len=64)
        if text is None:
            return None
        if not re.match(r'^[0-9a-fA-F]{64}$', text):
            self.fail('E_HASH', path, 'lower/upper-case SHA-256 hex required')
            return None
        return text.lower()

    def relpath(self, value, path):
        try:
            return check_attachment_path(value, path)
        except PlannerError as exc:
            self.fail(exc.code, path, exc.message)
            return None

    def unique_ids(self, rows, path):
        seen = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or 'id' not in row:
                continue
            ident = row['id']
            if ident in seen:
                self.fail('E_DUPLICATE_ID', '%s[%d].id' % (path, index),
                          'duplicate id %r' % ident)
            seen.add(ident)


def normalise(document, *, raw_sha256, source_path=None, now=None):
    """Validate ``document`` and return the normalised model.

    Raises :class:`InputInvalid` when there is at least one error diagnostic.
    Warnings are returned on the model and never silently discarded.
    """
    norm = _N(now=now)
    if not isinstance(document, dict):
        norm.fail('E_TYPE', '$', 'top-level JSON object required')
        raise InputInvalid(norm.diags.items)

    top = norm.obj(
        document, '$',
        required=('schema', 'project', 'power_domains', 'assemblies',
                  'interfaces', 'testpoints', 'equipment',
                  'operating_conditions', 'device_facts', 'user_policy',
                  'evidence_sources'),
        optional=('input_completeness', 'notes'))

    schema = norm.string(top.get('schema'), '$.schema', max_len=64)
    if schema is not None and schema != 'bringup-plan-input/v1':
        norm.fail('E_SCHEMA', '$.schema',
                  'expected bringup-plan-input/v1, got %r' % schema)

    project = _project(norm, top.get('project'))
    power_domains = _power_domains(norm, top.get('power_domains'))
    assemblies = _assemblies(norm, top.get('assemblies'))
    interfaces = _interfaces(norm, top.get('interfaces'))
    testpoints = _testpoints(norm, top.get('testpoints'))
    equipment = _equipment(norm, top.get('equipment'))
    conditions = _operating_conditions(norm, top.get('operating_conditions'))
    facts = _device_facts(norm, top.get('device_facts'))
    policy = _user_policy(norm, top.get('user_policy'))
    evidence = _evidence_sources(norm, top.get('evidence_sources'), project)
    completeness_declared = _input_completeness(norm,
                                               top.get('input_completeness'))

    _cross_checks(norm, project, power_domains, assemblies, interfaces,
                  testpoints, equipment, policy, evidence)

    notes = {}
    if 'notes' in top:
        raw_notes = top.get('notes')
        if isinstance(raw_notes, dict):
            for key, value in raw_notes.items():
                if isinstance(value, str):
                    notes[key] = value[:4000]
        else:
            norm.fail('E_TYPE', '$.notes', 'object of strings required')

    diagnostics = norm.diags.items
    norm.diags.raise_if_errors()

    model = {
        'schema': 'bringup-plan-input/v1',
        'project': project,
        'power_domains': power_domains,
        'assemblies': assemblies,
        'interfaces': interfaces,
        'testpoints': testpoints,
        'equipment': equipment,
        'operating_conditions': conditions,
        'device_facts': facts,
        'user_policy': policy,
        'evidence_sources': evidence,
        'input_completeness_declared': completeness_declared,
        'notes': notes,
        'source_path': str(source_path) if source_path else None,
        'raw_sha256': raw_sha256,
    }
    model['semantic_sha256'] = semantic_sha256(_hashable(model))
    model['completeness'] = compute_completeness(model)
    return {'document': model, 'diagnostics': diagnostics,
            'raw_sha256': raw_sha256,
            'semantic_sha256': model['semantic_sha256']}


def load_input(path, *, now=None):
    document = read_json(path)
    raw = Path(path).read_bytes()
    return normalise(document, raw_sha256=sha256_bytes(raw),
                     source_path=str(path), now=now)


def _hashable(model):
    """Drop free text/volatile values from the semantic hash."""
    clone = dict(model)
    clone.pop('notes', None)
    clone.pop('source_path', None)
    clone.pop('semantic_sha256', None)
    clone.pop('completeness', None)
    clone.pop('raw_sha256', None)
    return clone


# ---------------------------------------------------------------------------
# project


def _project(norm, value):
    entry = norm.obj(value, '$.project',
                     required=('name', 'revision', 'source_snapshot_hash',
                               'bom_version', 'assembly_version', 'scope'))
    scope = _scope(norm, entry.get('scope'))
    return {
        'name': norm.string(entry.get('name'), '$.project.name', max_len=120),
        'revision': norm.string(entry.get('revision'),
                                '$.project.revision', max_len=64),
        'source_snapshot_hash': norm.hex64(entry.get('source_snapshot_hash'),
                                            '$.project.source_snapshot_hash'),
        'bom_version': norm.string(entry.get('bom_version'),
                                   '$.project.bom_version', max_len=80),
        'assembly_version': norm.string(entry.get('assembly_version'),
                                        '$.project.assembly_version',
                                        max_len=80),
        'scope': scope,
    }


def _scope(norm, value):
    entry = norm.obj(value, '$.project.scope',
                     required=('supply_class', 'operations'),
                     optional=('notes',))
    supply_class = norm.string(entry.get('supply_class'),
                               '$.project.scope.supply_class', max_len=40)
    known_classes = ('dc_low_voltage',) + UNSUPPORTED_SUPPLY_CLASSES
    if supply_class is not None and supply_class not in known_classes:
        norm.fail('E_ENUM', '$.project.scope.supply_class',
                  'expected one of %s, got %r'
                  % (', '.join(known_classes), supply_class))
    operations = []
    raw_ops = norm.array(entry.get('operations'),
                         '$.project.scope.operations', min_items=1)
    for index, op in enumerate(raw_ops):
        text = norm.string(op, '$.project.scope.operations[%d]' % index,
                           max_len=40)
        if text is None:
            continue
        if not _OPS_RE.match(text):
            norm.fail('E_ID_FORMAT', '$.project.scope.operations[%d]' % index,
                      'operation id must be lower_snake_case: %r' % text)
            continue
        if text in operations:
            norm.fail('E_DUPLICATE_ID',
                      '$.project.scope.operations[%d]' % index,
                      'duplicate operation %r' % text)
        operations.append(text)
    notes = norm.string(entry.get('notes'), '$.project.scope.notes',
                        allow_empty=True, max_len=1000)
    return {'supply_class': supply_class,
            'operations': sorted(operations), 'notes': notes}


# ---------------------------------------------------------------------------
# power domains


def _current_spec(norm, value, path, required=False):
    if value is None:
        if required:
            norm.fail('E_REQUIRED', path, 'current object required')
        return None
    entry = norm.obj(value, path, required=('basis',),
                     optional=('value', 'unit', 'fact_id', 'source_ref',
                               'notes'))
    basis = norm.enum(entry.get('basis'), path + '.basis', _CURRENT_BASES)
    unit = norm.string(entry.get('unit'), path + '.unit', max_len=16) \
        if 'unit' in entry else 'A'
    value_norm = None
    if basis is None:
        return None
    if basis == 'unknown':
        if 'value' in entry:
            norm.warn('E_CURRENT_UNKNOWN', path,
                      'value present but basis=unknown; value is not used')
        return {'value': None, 'basis': 'unknown', 'unit': 'A',
                'fact_id': entry.get('fact_id'),
                'source_ref': entry.get('source_ref'),
                'notes': entry.get('notes')}
    if 'value' not in entry:
        norm.fail('E_REQUIRED', path,
                  'current value required when basis is %r (use basis=unknown '
                  'instead of inventing a number)' % basis)
        return None
    value_norm = norm.scalar(entry.get('value'), path + '.value', 'current',
                             positive=True)
    unit = unit or 'A'
    fact_id = norm.ident(entry['fact_id'], path + '.fact_id') \
        if 'fact_id' in entry else None
    source_ref = norm.string(entry.get('source_ref'), path + '.source_ref',
                             max_len=80)
    return {'value': value_norm, 'basis': basis, 'unit': 'A',
            'fact_id': fact_id, 'source_ref': source_ref,
            'notes': norm.string(entry.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=500)}


def _power_domains(norm, value):
    rows = norm.array(value, '$.power_domains', min_items=1)
    domains = []
    for index, raw in enumerate(rows):
        path = '$.power_domains[%d]' % index
        entry = norm.obj(
            raw, path,
            required=('id', 'net', 'ground_net', 'operating_min_v',
                      'operating_max_v', 'absolute_max_v'),
            optional=('nominal_v', 'source', 'depends_on', 'startup_current',
                      'static_current', 'runtime_current', 'load',
                      'protection', 'removable_load', 'notes'))
        domain = {
            'id': norm.ident(entry.get('id'), path + '.id'),
            'net': norm.string(entry.get('net'), path + '.net', max_len=80),
            'ground_net': norm.string(entry.get('ground_net'),
                                      path + '.ground_net', max_len=80),
            'nominal_v': norm.scalar(entry.get('nominal_v'),
                                     path + '.nominal_v', 'voltage',
                                     nonnegative=True)
            if 'nominal_v' in entry else None,
            'operating_min_v': norm.scalar(entry.get('operating_min_v'),
                                           path + '.operating_min_v',
                                           'voltage', nonnegative=True),
            'operating_max_v': norm.scalar(entry.get('operating_max_v'),
                                           path + '.operating_max_v',
                                           'voltage', positive=True),
            'absolute_max_v': norm.scalar(entry.get('absolute_max_v'),
                                          path + '.absolute_max_v', 'voltage',
                                          positive=True),
            'source': norm.string(entry.get('source'), path + '.source',
                                  allow_empty=True, max_len=200),
            'depends_on': _depends_on(norm, entry.get('depends_on'),
                                      path + '.depends_on'),
            'startup_current': _current_spec(
                norm, entry.get('startup_current'), path + '.startup_current'),
            'static_current': _current_spec(
                norm, entry.get('static_current'), path + '.static_current'),
            'runtime_current': _current_spec(
                norm, entry.get('runtime_current'), path + '.runtime_current'),
            'load': norm.string(entry.get('load'), path + '.load',
                                allow_empty=True, max_len=300),
            'protection': _protection(norm, entry.get('protection'),
                                      path + '.protection'),
            'removable_load': norm.boolean(entry.get('removable_load'),
                                           path + '.removable_load')
            if 'removable_load' in entry else False,
            'notes': norm.string(entry.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=1000),
        }
        _check_voltage_ranges(norm, domain, path)
        domains.append(domain)
    norm.unique_ids(domains, '$.power_domains')
    domains.sort(key=lambda item: item['id'] or '')
    # dependency ids are normalised before sorting; validate self-reference now
    known = {item['id'] for item in domains}
    for domain in domains:
        path = '$.power_domains[id=%s].depends_on' % domain['id']
        for dep in domain['depends_on']:
            if dep['domain'] == domain['id']:
                norm.fail('E_DAG_SELF_DEPENDENCY', path,
                          'domain %r depends on itself' % domain['id'])
            elif dep['domain'] not in known:
                norm.fail('E_DAG_MISSING_DEPENDENCY', path,
                          'domain %r depends on unknown domain %r'
                          % (domain['id'], dep['domain']))
    return domains


def _depends_on(norm, value, path):
    if value is None:
        return []
    rows = norm.array(value, path)
    result = []
    for index, raw in enumerate(rows):
        item_path = '%s[%d]' % (path, index)
        entry = norm.obj(raw, item_path, required=('domain',),
                         optional=('reason',))
        result.append({
            'domain': norm.ident(entry.get('domain'), item_path + '.domain'),
            'reason': norm.string(entry.get('reason'),
                                  item_path + '.reason', allow_empty=True,
                                  max_len=200),
        })
    return sorted(result, key=lambda item: (item['domain'] or '',
                                            item['reason'] or ''))


def _protection(norm, value, path):
    if value is None:
        return None
    entry = norm.obj(
        value, path,
        optional=('reverse_blocking', 'current_limit_a', 'notes'))
    reverse = norm.enum(entry.get('reverse_blocking'),
                        path + '.reverse_blocking',
                        ('none', 'series_diode', 'ideal_diode', 'power_mux',
                         'unknown'))
    return {
        'reverse_blocking': reverse,
        'current_limit_a': norm.scalar(entry.get('current_limit_a'),
                                       path + '.current_limit_a', 'current',
                                       positive=True)
        if 'current_limit_a' in entry else None,
        'notes': norm.string(entry.get('notes'), path + '.notes',
                             allow_empty=True, max_len=300),
    }


def _check_voltage_ranges(norm, domain, path):
    low = domain.get('operating_min_v')
    high = domain.get('operating_max_v')
    absolute = domain.get('absolute_max_v')
    nominal = domain.get('nominal_v')
    if low is not None and high is not None and low > high:
        norm.fail('E_RANGE', path + '.operating_min_v',
                  'operating_min_v > operating_max_v (inverted range)')
    if nominal is not None and low is not None and high is not None:
        if nominal < low or nominal > high:
            norm.fail('E_RANGE', path + '.nominal_v',
                      'nominal_v is outside the declared operating range')
    if high is not None and absolute is not None and high > absolute:
        norm.fail('E_RANGE', path + '.absolute_max_v',
                  'operating_max_v exceeds absolute_max_v: the working range '
                  'may never be above the absolute maximum rating')
    if low is not None and absolute is not None and low >= absolute:
        norm.fail('E_RANGE', path + '.operating_min_v',
                  'operating_min_v must be below absolute_max_v')


# ---------------------------------------------------------------------------
# assemblies


def _assemblies(norm, value):
    entry = norm.obj(
        value, '$.assemblies',
        optional=('dnp', 'jumpers', 'variants', 'removable_loads',
                  'protection_and_polarity', 'external_supply_paths',
                  'short_check_criterion', 'notes'))
    dnp = []
    for index, raw in enumerate(norm.array(entry.get('dnp', []),
                                           '$.assemblies.dnp')):
        path = '$.assemblies.dnp[%d]' % index
        item = norm.obj(raw, path, required=('designator',),
                        optional=('part', 'reason'))
        dnp.append({'designator': norm.string(item.get('designator'),
                                              path + '.designator',
                                              max_len=40),
                    'part': norm.string(item.get('part'), path + '.part',
                                        allow_empty=True, max_len=120),
                    'reason': norm.string(item.get('reason'),
                                          path + '.reason',
                                          allow_empty=True, max_len=200)})
    jumpers = []
    for index, raw in enumerate(norm.array(entry.get('jumpers', []),
                                           '$.assemblies.jumpers')):
        path = '$.assemblies.jumpers[%d]' % index
        item = norm.obj(raw, path, required=('id', 'default_state'),
                        optional=('configurations',
                                  'required_state_for_test', 'notes'))
        configs = []
        for cindex, raw_config in enumerate(norm.array(
                item.get('configurations', []), path + '.configurations')):
            cpath = '%s.configurations[%d]' % (path, cindex)
            cfg = norm.obj(raw_config, cpath, required=('state',),
                           optional=('purpose',))
            configs.append({'state': norm.string(
                cfg.get('state'), cpath + '.state', max_len=40),
                'purpose': norm.string(cfg.get('purpose'),
                                       cpath + '.purpose',
                                       allow_empty=True, max_len=200)})
        jumpers.append({
            'id': norm.ident(item.get('id'), path + '.id'),
            'default_state': norm.string(item.get('default_state'),
                                         path + '.default_state',
                                         max_len=40),
            'configurations': configs,
            'required_state_for_test': norm.string(
                item.get('required_state_for_test'),
                path + '.required_state_for_test', allow_empty=True,
                max_len=40),
            'notes': norm.string(item.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=300),
        })
    variants = []
    for index, raw in enumerate(norm.array(entry.get('variants', []),
                                           '$.assemblies.variants')):
        variants.append(norm.string(raw, '$.assemblies.variants[%d]' % index,
                                    max_len=100))
    removable = []
    for index, raw in enumerate(norm.array(entry.get('removable_loads', []),
                                           '$.assemblies.removable_loads')):
        path = '$.assemblies.removable_loads[%d]' % index
        item = norm.obj(raw, path, required=('designator',),
                        optional=('description', 'default_connected'))
        removable.append({
            'designator': norm.string(item.get('designator'),
                                      path + '.designator', max_len=40),
            'description': norm.string(item.get('description'),
                                       path + '.description',
                                       allow_empty=True, max_len=200),
            'default_connected': norm.boolean(item.get('default_connected'),
                                              path + '.default_connected')
            if 'default_connected' in item else False,
        })
    external = []
    for index, raw in enumerate(norm.array(
            entry.get('external_supply_paths', []),
            '$.assemblies.external_supply_paths')):
        path = '$.assemblies.external_supply_paths[%d]' % index
        item = norm.obj(
            raw, path, required=('id', 'net'),
            optional=('can_backfeed', 'disconnect_required_for_deenergized_tests',
                      'notes'))
        external.append({
            'id': norm.ident(item.get('id'), path + '.id'),
            'net': norm.string(item.get('net'), path + '.net', max_len=80),
            'can_backfeed': norm.boolean(item.get('can_backfeed'),
                                         path + '.can_backfeed')
            if 'can_backfeed' in item else False,
            'disconnect_required_for_deenergized_tests': norm.boolean(
                item.get('disconnect_required_for_deenergized_tests'),
                path + '.disconnect_required_for_deenergized_tests')
            if 'disconnect_required_for_deenergized_tests' in item else False,
            'notes': norm.string(item.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=300),
        })
    criterion = None
    if entry.get('short_check_criterion') is not None:
        path = '$.assemblies.short_check_criterion'
        item = norm.obj(entry['short_check_criterion'], path,
                        required=('max_ohm', 'basis'),
                        optional=('source_ref', 'conditions', 'notes'))
        criterion = {
            'max_ohm': norm.scalar(item.get('max_ohm'), path + '.max_ohm',
                                   'resistance', positive=True),
            'basis': norm.enum(item.get('basis'), path + '.basis',
                               ('project_requirement', 'calculation',
                                'measurement', 'datasheet')),
            'source_ref': norm.string(item.get('source_ref'),
                                      path + '.source_ref',
                                      allow_empty=True, max_len=80),
            'conditions': norm.string(item.get('conditions'),
                                      path + '.conditions',
                                      allow_empty=True, max_len=300),
            'notes': norm.string(item.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=300),
        }
    return {
        'dnp': sorted(dnp, key=lambda item: item['designator'] or ''),
        'jumpers': sorted(jumpers, key=lambda item: item['id'] or ''),
        'variants': sorted(variants),
        'removable_loads': sorted(removable,
                                  key=lambda item: item['designator'] or ''),
        'protection_and_polarity': norm.string(
            entry.get('protection_and_polarity'),
            '$.assemblies.protection_and_polarity', allow_empty=True,
            max_len=800),
        'external_supply_paths': sorted(
            external, key=lambda item: item['id'] or ''),
        'short_check_criterion': criterion,
        'notes': norm.string(entry.get('notes'), '$.assemblies.notes',
                             allow_empty=True, max_len=800),
    }


# ---------------------------------------------------------------------------
# interfaces


def _interfaces(norm, value):
    rows = norm.array(value, '$.interfaces')
    interfaces = []
    for index, raw in enumerate(rows):
        path = '$.interfaces[%d]' % index
        entry = norm.obj(
            raw, path, required=('id', 'type', 'pins'),
            optional=('logic_level_v', 'firmware_prerequisite',
                      'backfeed_risk', 'output_type', 'notes'))
        pins = []
        for pindex, raw_pin in enumerate(norm.array(entry.get('pins'),
                                                    path + '.pins')):
            ppath = '%s.pins[%d]' % (path, pindex)
            pin = norm.obj(raw_pin, ppath, required=('pin', 'net'),
                           optional=('role',))
            pins.append({
                'pin': norm.string(pin.get('pin'), ppath + '.pin',
                                  max_len=40),
                'net': norm.string(pin.get('net'), ppath + '.net',
                                   max_len=80),
                'role': norm.enum(pin.get('role'), ppath + '.role',
                                  _PIN_ROLES) if 'role' in pin else None,
            })
        firmware = entry.get('firmware_prerequisite')
        if isinstance(firmware, bool):
            firmware = 'firmware prerequisite declared' if firmware else None
        interfaces.append({
            'id': norm.ident(entry.get('id'), path + '.id'),
            'type': norm.enum(entry.get('type'), path + '.type',
                              _INTERFACE_TYPES),
            'pins': sorted(pins, key=lambda item: (item['pin'] or '',
                                                   item['net'] or '')),
            'logic_level_v': norm.scalar(entry.get('logic_level_v'),
                                         path + '.logic_level_v', 'voltage',
                                         positive=True)
            if 'logic_level_v' in entry else None,
            'firmware_prerequisite': norm.string(
                firmware, path + '.firmware_prerequisite',
                allow_empty=True, max_len=500),
            'backfeed_risk': norm.boolean(entry.get('backfeed_risk'),
                                          path + '.backfeed_risk')
            if 'backfeed_risk' in entry else False,
            'output_type': norm.enum(entry.get('output_type'),
                                     path + '.output_type', _OUTPUT_TYPES)
            if 'output_type' in entry else None,
            'notes': norm.string(entry.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=500),
        })
    norm.unique_ids(interfaces, '$.interfaces')
    interfaces.sort(key=lambda item: item['id'] or '')
    return interfaces


# ---------------------------------------------------------------------------
# testpoints


def _testpoints(norm, value):
    rows = norm.array(value, '$.testpoints')
    points = []
    for index, raw in enumerate(rows):
        path = '$.testpoints[%d]' % index
        entry = norm.obj(
            raw, path,
            required=('id', 'net', 'reference_net', 'contact',
                      'reachability_verified'),
            optional=('location', 'notes'))
        point = {
            'id': norm.ident(entry.get('id'), path + '.id'),
            'net': norm.string(entry.get('net'), path + '.net', max_len=80),
            'reference_net': norm.string(entry.get('reference_net'),
                                         path + '.reference_net', max_len=80),
            'contact': norm.enum(entry.get('contact'), path + '.contact',
                                 _CONTACTS),
            'reachability_verified': norm.boolean(
                entry.get('reachability_verified'),
                path + '.reachability_verified'),
            'location': norm.string(entry.get('location'), path + '.location',
                                    allow_empty=True, max_len=200),
            'notes': norm.string(entry.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=300),
        }
        if point['net'] is not None and point['net'] == point['reference_net']:
            norm.fail('E_RANGE', path,
                      'testpoint net and reference_net must differ')
        points.append(point)
    norm.unique_ids(points, '$.testpoints')
    points.sort(key=lambda item: item['id'] or '')
    return points


# ---------------------------------------------------------------------------
# equipment


def _equipment(norm, value):
    entry = norm.obj(value, '$.equipment',
                     optional=('supplies', 'multimeters', 'oscilloscopes',
                               'electronic_loads', 'notes'))
    supplies = []
    for index, raw in enumerate(norm.array(entry.get('supplies', []),
                                           '$.equipment.supplies')):
        path = '$.equipment.supplies[%d]' % index
        item = norm.obj(raw, path,
                        required=('id', 'model', 'max_voltage_v',
                                  'max_current_a'),
                        optional=('current_limit_min_a',
                                  'current_limit_resolution_a',
                                  'setpoint_resolution_v', 'source'))
        supplies.append({
            'id': norm.ident(item.get('id'), path + '.id'),
            'model': norm.string(item.get('model'), path + '.model',
                                 max_len=120),
            'max_voltage_v': norm.scalar(item.get('max_voltage_v'),
                                         path + '.max_voltage_v', 'voltage',
                                         positive=True),
            'max_current_a': norm.scalar(item.get('max_current_a'),
                                         path + '.max_current_a', 'current',
                                         positive=True),
            'current_limit_min_a': norm.scalar(
                item.get('current_limit_min_a'),
                path + '.current_limit_min_a', 'current', nonnegative=True)
            if 'current_limit_min_a' in item else None,
            'current_limit_resolution_a': norm.scalar(
                item.get('current_limit_resolution_a'),
                path + '.current_limit_resolution_a', 'current',
                positive=True)
            if 'current_limit_resolution_a' in item else None,
            'setpoint_resolution_v': norm.scalar(
                item.get('setpoint_resolution_v'),
                path + '.setpoint_resolution_v', 'voltage', positive=True)
            if 'setpoint_resolution_v' in item else None,
            'source': norm.string(item.get('source'), path + '.source',
                                  allow_empty=True, max_len=80),
        })
    multimeters = []
    for index, raw in enumerate(norm.array(entry.get('multimeters', []),
                                           '$.equipment.multimeters')):
        path = '$.equipment.multimeters[%d]' % index
        item = norm.obj(
            raw, path, required=('id', 'model', 'dc_voltage_max_v',
                                 'diode_mode'),
            optional=('dc_voltage_resolution_v', 'resistance_max_ohm',
                      'dc_current_max_a', 'accuracy_note', 'source'))
        multimeters.append({
            'id': norm.ident(item.get('id'), path + '.id'),
            'model': norm.string(item.get('model'), path + '.model',
                                 max_len=120),
            'dc_voltage_max_v': norm.scalar(
                item.get('dc_voltage_max_v'), path + '.dc_voltage_max_v',
                'voltage', positive=True),
            'dc_voltage_resolution_v': norm.scalar(
                item.get('dc_voltage_resolution_v'),
                path + '.dc_voltage_resolution_v', 'voltage', positive=True)
            if 'dc_voltage_resolution_v' in item else None,
            'resistance_max_ohm': norm.scalar(
                item.get('resistance_max_ohm'),
                path + '.resistance_max_ohm', 'resistance', positive=True)
            if 'resistance_max_ohm' in item else None,
            'diode_mode': norm.boolean(item.get('diode_mode'),
                                       path + '.diode_mode'),
            'dc_current_max_a': norm.scalar(item.get('dc_current_max_a'),
                                            path + '.dc_current_max_a',
                                            'current', positive=True)
            if 'dc_current_max_a' in item else None,
            'accuracy_note': norm.string(item.get('accuracy_note'),
                                         path + '.accuracy_note',
                                         allow_empty=True, max_len=300),
            'source': norm.string(item.get('source'), path + '.source',
                                  allow_empty=True, max_len=80),
        })
    scopes = []
    for index, raw in enumerate(norm.array(entry.get('oscilloscopes', []),
                                           '$.equipment.oscilloscopes')):
        path = '$.equipment.oscilloscopes[%d]' % index
        item = norm.obj(
            raw, path,
            required=('id', 'model', 'bandwidth_mhz', 'channels',
                      'grounding'),
            optional=('probe', 'max_input_voltage_v', 'source', 'notes'))
        probe = None
        if item.get('probe') is not None:
            ppath = path + '.probe'
            raw_probe = norm.obj(item['probe'], ppath,
                                 required=('type', 'bandwidth_mhz'),
                                 optional=('max_voltage_v', 'capacitance_pf'))
            probe = {
                'type': norm.string(raw_probe.get('type'), ppath + '.type',
                                    max_len=20),
                'bandwidth_mhz': norm.number(raw_probe.get('bandwidth_mhz'),
                                             ppath + '.bandwidth_mhz',
                                             positive=True),
                'max_voltage_v': norm.scalar(raw_probe.get('max_voltage_v'),
                                             ppath + '.max_voltage_v',
                                             'voltage', positive=True)
                if 'max_voltage_v' in raw_probe else None,
                'capacitance_pf': norm.number(
                    raw_probe.get('capacitance_pf'),
                    ppath + '.capacitance_pf', nonnegative=True)
                if 'capacitance_pf' in raw_probe else None,
            }
        scopes.append({
            'id': norm.ident(item.get('id'), path + '.id'),
            'model': norm.string(item.get('model'), path + '.model',
                                 max_len=120),
            'bandwidth_mhz': norm.number(item.get('bandwidth_mhz'),
                                         path + '.bandwidth_mhz',
                                         positive=True),
            'channels': norm.number(item.get('channels'), path + '.channels',
                                    positive=True),
            'grounding': norm.enum(item.get('grounding'),
                                   path + '.grounding', _GROUNDING),
            'probe': probe,
            'max_input_voltage_v': norm.scalar(
                item.get('max_input_voltage_v'),
                path + '.max_input_voltage_v', 'voltage', positive=True)
            if 'max_input_voltage_v' in item else None,
            'source': norm.string(item.get('source'), path + '.source',
                                  allow_empty=True, max_len=80),
            'notes': norm.string(item.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=300),
        })
    loads = []
    for index, raw in enumerate(norm.array(entry.get('electronic_loads', []),
                                           '$.equipment.electronic_loads')):
        path = '$.equipment.electronic_loads[%d]' % index
        item = norm.obj(raw, path,
                        required=('id', 'model', 'max_power_w',
                                  'max_current_a'),
                        optional=('min_voltage_v', 'modes', 'source', 'notes'))
        loads.append({
            'id': norm.ident(item.get('id'), path + '.id'),
            'model': norm.string(item.get('model'), path + '.model',
                                 max_len=120),
            'max_power_w': norm.scalar(item.get('max_power_w'),
                                       path + '.max_power_w', 'power',
                                       positive=True),
            'max_current_a': norm.scalar(item.get('max_current_a'),
                                         path + '.max_current_a', 'current',
                                         positive=True),
            'min_voltage_v': norm.scalar(item.get('min_voltage_v'),
                                         path + '.min_voltage_v', 'voltage',
                                         nonnegative=True)
            if 'min_voltage_v' in item else None,
            'modes': [norm.string(mode, path + '.modes[%d]' % mindex,
                                  max_len=40)
                      for mindex, mode in enumerate(norm.array(
                          item.get('modes', []), path + '.modes'))],
            'source': norm.string(item.get('source'), path + '.source',
                                  allow_empty=True, max_len=80),
            'notes': norm.string(item.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=300),
        })
    for collection in (supplies, multimeters, scopes, loads):
        norm.unique_ids(collection, '$.equipment')
        collection.sort(key=lambda item: item['id'] or '')
    return {'supplies': supplies, 'multimeters': multimeters,
            'oscilloscopes': scopes, 'electronic_loads': loads,
            'notes': norm.string(entry.get('notes'), '$.equipment.notes',
                                 allow_empty=True, max_len=500)}


# ---------------------------------------------------------------------------
# operating conditions


def _policy_value(norm, value, path, quantity, bases):
    """Shared {value, basis, source_ref/fact_id} policy object."""
    if value is None:
        return None
    entry = norm.obj(value, path, required=('value', 'basis'),
                     optional=('unit', 'source_ref', 'fact_id', 'conditions',
                               'notes'))
    basis = norm.enum(entry.get('basis'), path + '.basis', bases)
    number = norm.scalar(entry.get('value'), path + '.value', quantity,
                         positive=True)
    return {
        'value': number,
        'basis': basis,
        'unit': 'A' if quantity == 'current' else
                ('s' if quantity == 'time' else 'V'),
        'source_ref': norm.string(entry.get('source_ref'),
                                  path + '.source_ref', allow_empty=True,
                                  max_len=80),
        'fact_id': norm.ident(entry.get('fact_id'), path + '.fact_id')
        if 'fact_id' in entry else None,
        'conditions': norm.string(entry.get('conditions'),
                                  path + '.conditions', allow_empty=True,
                                  max_len=300),
        'notes': norm.string(entry.get('notes'), path + '.notes',
                             allow_empty=True, max_len=300),
    }


def _operating_conditions(norm, value):
    entry = norm.obj(
        value, '$.operating_conditions',
        optional=('ambient', 'load', 'current_limit_policy',
                  'observation_window_s', 'required_states',
                  'tolerances', 'notes'))
    ambient = None
    if entry.get('ambient') is not None:
        path = '$.operating_conditions.ambient'
        item = norm.obj(entry['ambient'], path, required=('min_c', 'max_c'))
        ambient = {
            'min_c': norm.scalar(item.get('min_c'), path + '.min_c',
                                 'temperature'),
            'max_c': norm.scalar(item.get('max_c'), path + '.max_c',
                                 'temperature'),
        }
        if ambient['min_c'] is not None and ambient['max_c'] is not None \
                and ambient['min_c'] > ambient['max_c']:
            norm.fail('E_RANGE', path, 'ambient min_c > max_c')
    states = [norm.string(item, '$.operating_conditions.required_states[%d]'
                          % index, max_len=100)
              for index, item in enumerate(norm.array(
                  entry.get('required_states', []),
                  '$.operating_conditions.required_states'))]
    tolerances = {}
    if entry.get('tolerances') is not None:
        path = '$.operating_conditions.tolerances'
        raw_tol = norm.obj(entry['tolerances'], path,
                           optional=('voltage', 'current', 'temperature'))
        for key in ('voltage', 'current', 'temperature'):
            if key in raw_tol:
                tolerances[key] = norm.scalar(raw_tol[key],
                                              path + '.' + key,
                                              'ratio', positive=True)
    return {
        'ambient': ambient,
        'load': norm.string(entry.get('load'), '$.operating_conditions.load',
                            allow_empty=True, max_len=300),
        'current_limit_policy': _policy_value(
            norm, entry.get('current_limit_policy'),
            '$.operating_conditions.current_limit_policy', 'current',
            ('project_requirement', 'calculation', 'datasheet', 'measurement',
             'estimate')),
        'observation_window_s': _policy_value(
            norm, entry.get('observation_window_s'),
            '$.operating_conditions.observation_window_s', 'time',
            ('datasheet', 'calculation', 'project_requirement', 'estimate')),
        'required_states': sorted({item for item in states if item}),
        'tolerances': tolerances,
        'notes': norm.string(entry.get('notes'),
                             '$.operating_conditions.notes',
                             allow_empty=True, max_len=500),
    }


# ---------------------------------------------------------------------------
# device facts


def _device_facts(norm, value):
    rows = norm.array(value, '$.device_facts')
    facts = []
    for index, raw in enumerate(rows):
        path = '$.device_facts[%d]' % index
        entry = norm.obj(
            raw, path,
            required=('id', 'kind', 'device', 'document', 'revision',
                      'section', 'url'),
            optional=('manufacturer', 'page', 'conditions', 'facts',
                      'unverified', 'notes'))
        url = norm.string(entry.get('url'), path + '.url', max_len=500)
        if url is not None and not re.match(r'^https?://', url):
            norm.fail('E_URL', path + '.url',
                      'official http(s) URL required, got %r' % url)
        entries = []
        for findex, raw_fact in enumerate(norm.array(
                entry.get('facts', []), path + '.facts')):
            fpath = '%s.facts[%d]' % (path, findex)
            fact = norm.obj(raw_fact, fpath, required=('key',),
                            optional=('value', 'unit', 'qualifier', 'typical',
                                      'conditions', 'page', 'quote'))
            key = norm.string(fact.get('key'), fpath + '.key', max_len=80)
            fact_value = fact.get('value')
            unit = norm.string(fact.get('unit'), fpath + '.unit',
                               max_len=16) if 'unit' in fact else None
            normalised_value = None
            if isinstance(fact_value, bool):
                normalised_value = fact_value
            elif type(fact_value) in (int, float):
                if unit is None:
                    norm.fail('E_UNIT', fpath + '.unit',
                              'unit is required for numeric facts')
                else:
                    try:
                        normalised_value = to_canonical(
                            fact_value, unit, _quantity_for_unit(norm, unit,
                                                                fpath))
                    except UnitError as exc:
                        norm.fail('E_UNIT', fpath, str(exc))
            elif isinstance(fact_value, str):
                normalised_value = fact_value[:500]
            elif fact_value is not None:
                norm.fail('E_TYPE', fpath + '.value',
                          'fact value must be number, string or boolean')
            entries.append({
                'key': key,
                'value': normalised_value,
                'unit': unit,
                'qualifier': norm.string(fact.get('qualifier'),
                                         fpath + '.qualifier',
                                         allow_empty=True, max_len=200),
                'typical': norm.boolean(fact.get('typical'),
                                        fpath + '.typical')
                if 'typical' in fact else False,
                'conditions': norm.string(fact.get('conditions'),
                                          fpath + '.conditions',
                                          allow_empty=True, max_len=300),
                'page': norm.number(fact.get('page'), fpath + '.page',
                                    positive=True)
                if 'page' in fact else None,
                'quote': norm.string(fact.get('quote'), fpath + '.quote',
                                     allow_empty=True, max_len=500),
            })
        facts.append({
            'id': norm.ident(entry.get('id'), path + '.id'),
            'kind': norm.enum(entry.get('kind'), path + '.kind', _FACT_KINDS),
            'device': norm.string(entry.get('device'), path + '.device',
                                  max_len=120),
            'manufacturer': norm.string(entry.get('manufacturer'),
                                        path + '.manufacturer',
                                        allow_empty=True, max_len=120),
            'document': norm.string(entry.get('document'), path + '.document',
                                    max_len=200),
            'revision': norm.string(entry.get('revision'),
                                    path + '.revision', max_len=60),
            'section': norm.string(entry.get('section'), path + '.section',
                                   max_len=120),
            'page': norm.number(entry.get('page'), path + '.page',
                                positive=True) if 'page' in entry else None,
            'url': url,
            'conditions': norm.string(entry.get('conditions'),
                                      path + '.conditions',
                                      allow_empty=True, max_len=400),
            'unverified': norm.boolean(entry.get('unverified'),
                                       path + '.unverified')
            if 'unverified' in entry else False,
            'facts': entries,
            'notes': norm.string(entry.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=400),
        })
    norm.unique_ids(facts, '$.device_facts')
    facts.sort(key=lambda item: item['id'] or '')
    return facts


def _quantity_for_unit(norm, unit, path):
    from .units import quantity_for_unit
    try:
        return quantity_for_unit(unit)
    except UnitError:
        norm.fail('E_UNIT', path + '.unit', 'unknown unit %r' % unit)
        raise


# ---------------------------------------------------------------------------
# user policy / evidence


def _user_policy(norm, value):
    entry = norm.obj(
        value, '$.user_policy',
        required=('mode', 'allowed_operations', 'max_input_voltage_v',
                  'max_current_a'),
        optional=('forbidden_operations', 'human_confirmation_points',
                  'risk_tolerance', 'notes'))
    allowed = []
    for index, item in enumerate(norm.array(entry.get('allowed_operations'),
                                            '$.user_policy.allowed_operations',
                                            min_items=1)):
        text = norm.string(item, '$.user_policy.allowed_operations[%d]'
                           % index, max_len=40)
        if text is None:
            continue
        if not _OPS_RE.match(text):
            norm.fail('E_ID_FORMAT',
                      '$.user_policy.allowed_operations[%d]' % index,
                      'operation id must be lower_snake_case: %r' % text)
            continue
        allowed.append(text)
    forbidden = []
    for index, item in enumerate(norm.array(
            entry.get('forbidden_operations', []),
            '$.user_policy.forbidden_operations')):
        text = norm.string(item, '$.user_policy.forbidden_operations[%d]'
                           % index, max_len=40)
        if text:
            forbidden.append(text)
    confirmations = [norm.string(
        item, '$.user_policy.human_confirmation_points[%d]' % index,
        max_len=120) for index, item in enumerate(norm.array(
            entry.get('human_confirmation_points', []),
            '$.user_policy.human_confirmation_points'))]
    policy = {
        'mode': norm.enum(entry.get('mode'), '$.user_policy.mode',
                          ('plan_only', 'review_only')),
        'allowed_operations': sorted(set(allowed)),
        'forbidden_operations': sorted(set(forbidden)),
        'max_input_voltage_v': norm.scalar(entry.get('max_input_voltage_v'),
                                           '$.user_policy.max_input_voltage_v',
                                           'voltage', positive=True),
        'max_current_a': norm.scalar(entry.get('max_current_a'),
                                     '$.user_policy.max_current_a', 'current',
                                     positive=True),
        'human_confirmation_points': sorted({item for item in confirmations
                                             if item}),
        'risk_tolerance': norm.enum(entry.get('risk_tolerance'),
                                    '$.user_policy.risk_tolerance',
                                    ('low', 'medium', 'high'))
        if 'risk_tolerance' in entry else 'low',
        'notes': norm.string(entry.get('notes'), '$.user_policy.notes',
                             allow_empty=True, max_len=500),
    }
    return policy


def _evidence_sources(norm, value, project):
    rows = norm.array(value, '$.evidence_sources')
    sources = []
    for index, raw in enumerate(rows):
        path = '$.evidence_sources[%d]' % index
        entry = norm.obj(
            raw, path,
            required=('id', 'kind', 'path', 'revision'),
            optional=('sha256', 'captured_at', 'produced_at', 'notes'))
        revision = norm.string(entry.get('revision'),
                               path + '.revision', max_len=64)
        if revision is not None and project.get('revision') is not None \
                and revision != project['revision']:
            norm.warn('E_EVIDENCE_REVISION', path + '.revision',
                      'evidence revision %r differs from project revision %r; '
                      'the planner will report it as stale'
                      % (revision, project['revision']))
        captured = entry.get('captured_at', entry.get('produced_at'))
        sources.append({
            'id': norm.ident(entry.get('id'), path + '.id'),
            'kind': norm.enum(entry.get('kind'), path + '.kind',
                              _EVIDENCE_KINDS),
            'path': norm.relpath(entry.get('path'), path + '.path'),
            'sha256': norm.hex64(entry.get('sha256'), path + '.sha256')
            if 'sha256' in entry else None,
            'revision': revision,
            'captured_at': norm.timestamp(captured, path + '.captured_at')
            if captured is not None else None,
            'notes': norm.string(entry.get('notes'), path + '.notes',
                                 allow_empty=True, max_len=300),
        })
    norm.unique_ids(sources, '$.evidence_sources')
    sources.sort(key=lambda item: item['id'] or '')
    return sources


def _input_completeness(norm, value):
    if value is None:
        return None
    entry = norm.obj(value, '$.input_completeness',
                     optional=('declared_complete', 'missing', 'notes'))
    missing = [norm.string(item,
                           '$.input_completeness.missing[%d]' % index,
                           max_len=120)
               for index, item in enumerate(norm.array(
                   entry.get('missing', []),
                   '$.input_completeness.missing'))]
    return {
        'declared_complete': norm.boolean(entry.get('declared_complete'),
                                          '$.input_completeness.declared_complete')
        if 'declared_complete' in entry else None,
        'missing': sorted({item for item in missing if item}),
        'notes': norm.string(entry.get('notes'),
                             '$.input_completeness.notes',
                             allow_empty=True, max_len=500),
    }


# ---------------------------------------------------------------------------
# cross checks and completeness


def _cross_checks(norm, project, domains, assemblies, interfaces, testpoints,
                  equipment, policy, evidence):
    ground_nets = {item['ground_net'] for item in domains if item['ground_net']}
    for domain in domains:
        if domain['net'] and domain['net'] in ground_nets:
            norm.fail('E_ROLE_CONFLICT',
                      '$.power_domains[id=%s]' % domain['id'],
                      'rail net %r is also used as a ground net'
                      % domain['net'])
    domains_by_id = {item['id']: item for item in domains}
    for interface in interfaces:
        roles = {}
        for pin in interface['pins']:
            if pin['role'] and pin['net']:
                roles.setdefault(pin['net'], set()).add(pin['role'])
        for net, net_roles in roles.items():
            if 'power' in net_roles and 'ground' in net_roles:
                norm.fail('E_ROLE_CONFLICT',
                          '$.interfaces[id=%s]' % interface['id'],
                          'net %r declared as both power and ground' % net)
        power_nets = {pin['net'] for pin in interface['pins']
                      if pin['role'] == 'power'}
        for net in sorted(power_nets):
            for domain in domains:
                if net == domain['net'] and interface['backfeed_risk']:
                    ok = False
                    protection = domain.get('protection') or {}
                    if protection.get('reverse_blocking') in (
                            'series_diode', 'ideal_diode', 'power_mux'):
                        ok = True
                    if not ok:
                        norm.warn('E_BACKFEED_RISK',
                                  '$.interfaces[id=%s]' % interface['id'],
                                  'interface feeds rail %r with possible '
                                  'backfeed and no reverse-blocking scheme is '
                                  'declared' % net)
    for path in assemblies['external_supply_paths']:
        if not path['can_backfeed']:
            continue
        for domain in domains:
            if path['net'] != domain['net']:
                continue
            protection = domain.get('protection') or {}
            if protection.get('reverse_blocking') in (
                    'series_diode', 'ideal_diode', 'power_mux'):
                continue
            norm.warn('E_BACKFEED_RISK',
                      '$.assemblies.external_supply_paths[id=%s]' % path['id'],
                      'external supply %r can feed rail %r without a declared '
                      'reverse-blocking scheme' % (path['id'], path['net']))
    tp_nets = {point['net'] for point in testpoints if point['net']}
    for domain in domains:
        if domain['net'] not in tp_nets:
            norm.warn('E_NO_TESTPOINT',
                      '$.power_domains[id=%s]' % domain['id'],
                      'no testpoint declared for rail %r; related steps will '
                      'be blocked' % domain['net'])
    for domain in domains:
        if domain['id'] not in domains_by_id:
            continue
    if policy['max_input_voltage_v'] is not None:
        for domain in domains:
            if domain['operating_max_v'] is None:
                continue
            if domain['operating_max_v'] > policy['max_input_voltage_v']:
                norm.warn('E_POLICY_RANGE',
                          '$.user_policy.max_input_voltage_v',
                          'rail %r operating_max_v exceeds the declared '
                          'user policy voltage ceiling' % domain['net'])
    for source in evidence:
        if source['revision'] and project.get('revision') \
                and source['revision'] != project['revision']:
            continue


def compute_completeness(model):
    """Information coverage, not a pass criterion.

    This is reported so a gap report can drive the user to supply the missing
    facts; it is never used to invent defaults.
    """
    checks = []

    def add(code, ok, detail):
        checks.append({'code': code, 'ok': bool(ok), 'detail': detail})

    domains = model['power_domains']
    add('power_domains_declared', bool(domains), '%d declared' % len(domains))
    for domain in domains:
        prefix = 'domain.%s' % domain['id']
        add(prefix + '.nominal', domain.get('nominal_v') is not None,
            'nominal voltage declared')
        add(prefix + '.startup_current',
            (domain.get('startup_current') or {}).get('value') is not None,
            'startup current known')
        add(prefix + '.runtime_current',
            (domain.get('runtime_current') or {}).get('value') is not None,
            'runtime current known')
    tp_nets = {point['net'] for point in model['testpoints']}
    add('testpoints_declared', bool(model['testpoints']),
        '%d declared' % len(model['testpoints']))
    for domain in domains:
        add('testpoint.%s' % domain['id'], domain['net'] in tp_nets,
            'rail %r has a declared testpoint' % domain['net'])
    equipment = model['equipment']
    add('equipment.supply', bool(equipment['supplies']),
        'current-limited supply declared')
    add('equipment.multimeter', bool(equipment['multimeters']),
        'multimeter declared')
    add('equipment.oscilloscope', bool(equipment['oscilloscopes']),
        'oscilloscope declared')
    add('operating_conditions.current_limit_policy',
        model['operating_conditions'].get('current_limit_policy') is not None,
        'current-limit value has a declared basis')
    add('operating_conditions.observation_window',
        model['operating_conditions'].get('observation_window_s') is not None,
        'observation window has a declared basis')
    add('device_facts', bool(model['device_facts']),
        '%d primary-source fact entries' % len(model['device_facts']))
    add('user_policy', model['user_policy'].get('mode') == 'plan_only',
        'plan-only policy declared')
    known = sum(1 for check in checks if check['ok'])
    ratio = round(known / len(checks), 4) if checks else 0.0
    return {'checks': checks, 'known': known, 'total': len(checks),
            'ratio': ratio,
            'missing': [check['code'] for check in checks if not check['ok']]}


# ---------------------------------------------------------------------------
# planning context


class PlanContext:
    """Shared state handed to each capability generator (I1..I5)."""

    def __init__(self, model):
        self.input = model
        self.project = model['project']
        self.domains = model['power_domains']
        self.assemblies = model['assemblies']
        self.interfaces = model['interfaces']
        self.testpoints = model['testpoints']
        self.equipment = model['equipment']
        self.conditions = model['operating_conditions']
        self.facts = model['device_facts']
        self.policy = model['user_policy']
        self.evidence = model['evidence_sources']
        self.gaps = []
        self.unknowns = []
        self.equipment_gaps = []
        self.steps = []
        self.trees = []
        self.scope = {}
        self.dag = {}
        self.supply_conflicts = []
        self._fact_index = {fact['id']: fact for fact in self.facts
                            if fact['id']}

    # -- bookkeeping -----------------------------------------------------
    def add_gap(self, code, topic, detail, *, needed=None, severity='warning',
                path=None):
        item = {'code': code, 'topic': topic, 'detail': detail,
                'needed': needed or [], 'severity': severity,
                'path': path}
        self.gaps.append(item)
        return item

    def add_unknown(self, code, topic, detail, *, needed=None, blocks=None):
        item = {'code': code, 'topic': topic, 'detail': detail,
                'needed': needed or [], 'blocks': blocks or []}
        self.unknowns.append(item)
        return item

    def add_equipment_gap(self, code, equipment, capability, detail):
        item = {'code': code, 'equipment': equipment,
                'capability': capability, 'detail': detail}
        self.equipment_gaps.append(item)
        return item

    def add_step(self, step):
        self.steps.append(step)
        return step

    # -- lookups ---------------------------------------------------------
    def domain(self, domain_id):
        for domain in self.domains:
            if domain['id'] == domain_id:
                return domain
        return None

    def domain_for_net(self, net):
        for domain in self.domains:
            if domain['net'] == net:
                return domain
        return None

    def testpoints_for(self, net):
        return [point for point in self.testpoints if point['net'] == net]

    def testpoint(self, point_id):
        for point in self.testpoints:
            if point['id'] == point_id:
                return point
        return None

    def interface(self, interface_id):
        for interface in self.interfaces:
            if interface['id'] == interface_id:
                return interface
        return None

    def fact(self, fact_id):
        return self._fact_index.get(fact_id)

    def fact_value(self, fact_id, key):
        fact = self.fact(fact_id)
        if not fact:
            return None
        for entry in fact.get('facts', []):
            if entry.get('key') == key:
                return entry.get('value')
        return None

    def supplies(self):
        return self.equipment['supplies']

    def multimeters(self):
        return self.equipment['multimeters']

    def oscilloscopes(self):
        return self.equipment['oscilloscopes']

    def declared_ops(self):
        return set(self.policy['allowed_operations'])

    def supports_operation(self, operation):
        return operation in self.declared_ops() and \
            operation in SUPPORTED_OPERATIONS


def load_and_normalise(path, *, now=None):
    loaded = load_input(path, now=now)
    return loaded['document']
