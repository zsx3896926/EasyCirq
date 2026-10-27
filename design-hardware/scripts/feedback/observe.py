"""Capability probe, observation contract, semantic hash and read cache.

The observation layer is deliberately conservative:

* every read command is sent with an explicit window and document UUID; a
  response that echoes a different ``projectUuid``/``documentUuid`` is refused
  with :class:`schemas.FeedbackError` ``target_mismatch`` instead of being
  merged into the current project;
* a response that does not echo its context is kept, but recorded as a
  degradation -- the read itself is not promoted to identity-verified evidence;
* a timed-out or failed command becomes a ``degradations`` entry and makes the
  affected section ``None`` plus an ``unknown`` entry.  It is never silently
  turned into an empty list;
* a capability is ``available`` only after the corresponding command actually
  ran and the expected data was measured.  Help text only proves that an
  interface is listed; mutating probes are therefore ``unknown``, never
  ``available``.

Normalized sections use snake_case; the source spellings that consumers rely
on (``copperLayers``/``capturedAt``/``semanticSha256``/``uniqueId``) are kept as
aliases next to them.  Nothing here calls a real ``zhigou`` binary by itself:
the caller injects ``runner`` (same signature as :func:`pcb_cli.run`) and
``zhigou`` is passed through unchanged.
"""
from __future__ import annotations

import copy
import os
import re

import pcb_cli
import pcb_evidence

try:  # package import (feedback.observe)
    from . import schemas
except ImportError:  # pragma: no cover - flat import by offline tools
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import schemas

CAPABILITY_IDS = (
    'project_doc_identity', 'sch_object_read', 'sch_net_read',
    'pcb_object_read', 'pcb_geometry_read', 'pcb_copper_read',
    'move_component', 'move_text', 'route_track', 'place_via', 'lock',
    'sch_erc', 'pcb_drc', 'pcb_check', 'save', 'reopen', 'screenshot',
    'export_archive', 'undo',
)

WRITE_CAPABILITIES = (
    'move_component', 'move_text', 'route_track', 'place_via', 'lock',
    'save', 'reopen', 'screenshot', 'export_archive', 'undo',
)

STATUS_AVAILABLE = 'available'
STATUS_UNAVAILABLE = 'unavailable'
STATUS_UNKNOWN = 'unknown'

CACHE_SCHEMA = 'hds-observation-cache/v1'
EVIDENCE_SCHEMA = 'hds-command-evidence/v1'

_VOLATILE_KEYS = {
    'generated_at', 'captured_at', 'capturedAt', 'stored_at', 'started_at',
    'startedAt', 'ended_at', 'completedAt', 'probed_at', 'observed_at',
    'observedAt', 'argv', 'stdout', 'stderr', 'stdout_sha256',
    'stderr_sha256',
}

_UUID_RE = re.compile(r'^[0-9a-fA-F]{16,64}$')


def _text(value):
    if value is None:
        return ''
    return str(value).strip()


def _first(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != '':
            return value
    return None


def _looks_like_uuid(value):
    return bool(_UUID_RE.match(_text(value)))


def _invoke(run, args, *, zhigou=None, timeout=120):
    return run([str(item) for item in args], zhigou=zhigou,
               timeout=timeout)


def _body(record):
    """Return ``(body, envelope)`` for an envelope, a bare result or None."""
    payload = record.get('payload') if isinstance(record, dict) else None
    if isinstance(payload, dict):
        result = payload.get('result')
        if isinstance(result, dict):
            return result, payload
        return payload, payload
    text = _text((record or {}).get('stdout'))
    if text:
        try:
            import json
            value = json.loads(text)
        except ValueError:
            return None, None
        if isinstance(value, dict):
            result = value.get('result')
            if isinstance(result, dict):
                return result, value
            return value, value
    return None, None


def _input_body(value):
    """Accept a pcb_cli record, an envelope or a bare payload."""
    if not isinstance(value, dict):
        return None, None
    if 'payload' in value or 'exit' in value or 'stdout' in value:
        return _body(value)
    return _body({'payload': value})


def _record_ok(record):
    if not isinstance(record, dict) or record.get('exit') != 0:
        return False
    payload = record.get('payload')
    return not (isinstance(payload, dict) and payload.get('ok') is False)


def _record_state(record):
    record = record if isinstance(record, dict) else {}
    error = _text(record.get('error')).lower()
    exit_code = record.get('exit')
    if exit_code == 124 or 'timeout' in error:
        return 'timeout'
    if exit_code in (126, 127) or 'not found' in error or \
            'could not execute' in error:
        return 'host_unavailable'
    if exit_code != 0:
        return 'failed'
    return 'ok'


def _error_code(record):
    payload = (record or {}).get('payload')
    if isinstance(payload, dict):
        error = payload.get('error')
        if isinstance(error, dict):
            return _text(error.get('code')).upper()
        if isinstance(error, str):
            return error.upper()
    return ''


def _unknown_command(record):
    code = _error_code(record)
    if code in ('UNKNOWN_COMMAND', 'UNKNOWN_FLAG', 'UNKNOWN_SUBCOMMAND'):
        return True
    text = (_text((record or {}).get('stderr')) + ' ' +
            _text((record or {}).get('stdout'))).lower()
    return 'unknown command' in text or 'unknown flag' in text


def _contexts(record, body):
    found = []
    sources = []
    if isinstance(record, dict):
        sources.append(record)
        sources.append(record.get('payload'))
    sources.append(body)
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ('context', 'mutationContext'):
            value = source.get(key)
            if isinstance(value, dict):
                found.append(value)
        if isinstance(source.get('capture'), dict):
            found.append(source['capture'])
        for key in ('projectUuid', 'project_uuid'):
            if source.get(key):
                found.append({key: source[key]})
    return found


def _norm(value):
    return re.sub(r'\s+', ' ', _text(value)).strip().casefold()


def _context_identity(record, body):
    observed = {}
    aliases = (
        ('projectUuid', 'project_uuid'), ('project_uuid', 'project_uuid'),
        ('projectName', 'project_name'), ('project_name', 'project_name'),
        ('documentUuid', 'document_uuid'), ('document_uuid', 'document_uuid'),
        ('documentName', 'document_name'),
        ('document_name', 'document_name'),
        ('documentType', 'document_type'),
    )
    for context in _contexts(record, body):
        for key, target in aliases:
            value = _text(context.get(key))
            if value:
                observed.setdefault(target, value)
    return observed


def _field_any(observed_values, expected_values):
    """Return True/False/None; any echoed identifier may prove the target.

    ``--project`` and ``--doc`` accept a UUID or a name, so a matching UUID
    *or* a matching name is proof.  ``None`` means nothing was comparable.
    """
    acceptable = {_norm(value) for value in expected_values if _text(value)}
    observed = [value for value in observed_values if _text(value)]
    if not acceptable or not observed:
        return None
    return any(_norm(value) in acceptable for value in observed)


def _verify_identity(record, body, *, project=None, project_name=None,
                     document=None, document_name=None, where='command'):
    """Refuse a response whose echoed context names another target.

    ``--project`` and ``--doc`` accept either a UUID or a name, so the echoed
    UUID or the echoed name may both prove the target.  A field that was not
    echoed is not comparable; if nothing was comparable the result is
    ``verified=None`` (unknown), never a pass.
    """
    observed = _context_identity(record, body)
    project_result = _field_any(
        (observed.get('project_uuid'), observed.get('project_name')),
        (project, project_name))
    if project_result is False:
        raise schemas.FeedbackError(
            schemas.FAILURE_TARGET_MISMATCH,
            '%s: response project %r/%r does not match expected %r/%r'
            % (where, observed.get('project_uuid'),
               observed.get('project_name'), project, project_name),
            where=where, expected_project=project or project_name,
            observed_project=observed.get('project_uuid'),
            observed_project_name=observed.get('project_name'),
            argv=(record or {}).get('argv'))
    document_result = _field_any(
        (observed.get('document_uuid'), observed.get('document_name')),
        (document, document_name))
    if document_result is False:
        raise schemas.FeedbackError(
            schemas.FAILURE_TARGET_MISMATCH,
            '%s: response document %r/%r does not match expected %r/%r'
            % (where, observed.get('document_uuid'),
               observed.get('document_name'), document, document_name),
            where=where, expected_document=document or document_name,
            observed_document=observed.get('document_uuid'),
            observed_document_name=observed.get('document_name'),
            argv=(record or {}).get('argv'))
    comparable = [result for result in (project_result, document_result)
                  if result is not None]
    return {'context_echoed': bool(observed),
            'verified': all(comparable) if comparable else None,
            'project_uuid': observed.get('project_uuid'),
            'project_name': observed.get('project_name'),
            'document_uuid': observed.get('document_uuid'),
            'document_name': observed.get('document_name'),
            'document_type': observed.get('document_type')}


def _target_args(*, window=None, project=None):
    if _text(window):
        return ['--window', _text(window)]
    if _text(project):
        return ['--project', _text(project)]
    return []


def _document_args(document):
    return ['--doc', _text(document)] if _text(document) else []


def _canonical_sha(value):
    if value is None:
        return None
    try:
        return schemas.stable_hash(value)
    except (TypeError, ValueError):
        return schemas.sha256_text(str(value))


def _compact_evidence(record, body):
    return {
        'argv': (record or {}).get('argv') or [],
        'exit': (record or {}).get('exit'),
        'ok': _record_ok(record),
        'response_keys': sorted(body) if isinstance(body, dict) else [],
        'response_sha256': _canonical_sha(body) if body is not None
        else schemas.sha256_text(_text((record or {}).get('stdout'))),
    }


def _capability_item(cap_id, status, interface, *, version=None, evidence=None,
                     limits=None, reason=None):
    return {
        'id': cap_id,
        'status': status,
        'interface': interface,
        'version': version,
        'evidence': evidence or {},
        'limits': limits or [],
        'reason': reason,
    }


def _probe_version(run, *, zhigou, timeout):
    record = _invoke(run, ['version'], zhigou=zhigou, timeout=timeout)
    body, _ = _body(record)
    if isinstance(body, dict):
        value = _first(body, 'version', 'cliVersion')
        if value:
            return _text(value)
    text = _text(record.get('stdout')).splitlines()
    if record.get('exit') == 0 and text:
        return text[0][:120]
    return None


def _read_gate(call, measured):
    """Return ``(status, reason)`` for one read capability."""
    if call['state'] == 'timeout':
        return STATUS_UNKNOWN, 'timeout: %s' % _text(
            call['record'].get('error')) or 'timeout'
    if call['state'] == 'host_unavailable':
        return STATUS_UNKNOWN, 'host_unavailable: %s' % _text(
            call['record'].get('error'))
    if call['state'] == 'failed':
        if _unknown_command(call['record']):
            return STATUS_UNAVAILABLE, 'command_not_found'
        return STATUS_UNKNOWN, 'command_failed: exit=%s' % (
            call['record'].get('exit'),)
    if call['identity_mismatch']:
        return STATUS_UNKNOWN, 'target_mismatch: %s' % (
            call['identity_mismatch'],)
    if call['body'] is None:
        return STATUS_UNKNOWN, 'no_json_response'
    if not measured:
        return STATUS_UNKNOWN, 'expected_data_missing'
    return STATUS_AVAILABLE, None


def _combine_gates(gates):
    order = (STATUS_UNAVAILABLE, STATUS_UNKNOWN, STATUS_AVAILABLE)
    reasons = [reason for _, reason in gates if reason]
    for status in order:
        for candidate, _ in gates:
            if candidate == status:
                return status, '; '.join(reasons) or None
    return STATUS_UNKNOWN, 'no_probe_result'


def _help_probe(run, cap_id, interface, args, *, zhigou, version, timeout,
                limits):
    record = _invoke(run, args, zhigou=zhigou, timeout=timeout)
    state = _record_state(record)
    evidence = _compact_evidence(record, None)
    if state == 'timeout':
        return _capability_item(
            cap_id, STATUS_UNKNOWN, interface, version=version,
            evidence=evidence, limits=limits,
            reason='timeout: %s' % _text(record.get('error')))
    if state == 'host_unavailable':
        return _capability_item(
            cap_id, STATUS_UNKNOWN, interface, version=version,
            evidence=evidence, limits=limits,
            reason='host_unavailable: %s' % _text(record.get('error')))
    if state == 'ok':
        return _capability_item(
            cap_id, STATUS_UNKNOWN, interface, version=version,
            evidence=evidence, limits=limits,
            reason='write_probe_not_executed: the CLI lists this interface, '
                   'but executing it would mutate the open document')
    if _unknown_command(record):
        return _capability_item(
            cap_id, STATUS_UNAVAILABLE, interface, version=version,
            evidence=evidence, limits=limits, reason='command_not_found')
    return _capability_item(
        cap_id, STATUS_UNKNOWN, interface, version=version,
        evidence=evidence, limits=limits,
        reason='interface_probe_failed: exit=%s' % (record.get('exit'),))


def probe_capabilities(*, runner=None, zhigou=None, window=None, project=None,
                       sch_doc=None, pcb_doc=None, timeout=120):
    """Probe read commands and CLI interfaces without mutating the project.

    ``project``/``sch_doc``/``pcb_doc`` may be UUIDs or names; a matching
    echoed ``projectUuid``/``projectName``/``documentUuid``/``documentName``
    proves the target.  A capability is ``available`` only when its own command
    returned the expected measured data.  Mutating commands are probed through
    ``--help`` and reported as ``unknown`` -- the probe never writes.
    """
    run = runner or pcb_cli.run
    version = _probe_version(run, zhigou=zhigou, timeout=timeout)
    base = _target_args(window=window, project=project)
    raw_project_uuid = _text(project) if _looks_like_uuid(project) else None
    raw_project_name = None if _looks_like_uuid(project) else _text(project)
    calls = {}

    def call(label, args, *, project_uuid=None, project_name=None,
             document=None, document_name=None):
        record = _invoke(run, args, zhigou=zhigou, timeout=timeout)
        body, _envelope = _body(record)
        mismatch = None
        if _record_state(record) in ('ok', 'failed') and body is not None:
            try:
                _verify_identity(record, body, project=project_uuid,
                                 project_name=project_name,
                                 document=document,
                                 document_name=document_name, where=label)
            except schemas.FeedbackError as exc:
                mismatch = exc.message
        calls[label] = {
            'record': record, 'body': body,
            'state': _record_state(record), 'identity_mismatch': mismatch,
        }
        return calls[label]

    info = call('project-info', ['project', 'info'] + base,
                project_uuid=raw_project_uuid,
                project_name=raw_project_name)
    docs = call('doc-list', ['doc', 'ls', '--json'] + base,
                project_uuid=raw_project_uuid,
                project_name=raw_project_name)
    measured_project = _project_identity(info['body']) if info['body'] else {}
    project_uuid, project_name = raw_project_uuid, raw_project_name
    if measured_project and not info['identity_mismatch']:
        project_uuid = measured_project['uuid'] or raw_project_uuid
        project_name = measured_project['name'] or raw_project_name
    listed = _document_list(docs['body']) if docs['body'] and \
        not docs['identity_mismatch'] else None

    def resolve_document(value):
        value = _text(value)
        if not value:
            return None, None
        for item in listed or []:
            if item.get('uuid') == value:
                return value, item.get('name') or None
        if _looks_like_uuid(value):
            return value, None
        matches = [item for item in listed or []
                   if _norm(item.get('name')) == _norm(value)]
        if len(matches) == 1:
            return matches[0]['uuid'], matches[0]['name'] or value
        return value, value

    sch_uuid, sch_name = resolve_document(sch_doc)
    pcb_uuid, pcb_name = resolve_document(pcb_doc)
    target = {'project_uuid': project_uuid,
              'project_name': project_name}

    sch = call('sch-read', ['sch', 'read'] + base +
               _document_args(sch_doc), document=sch_uuid,
               document_name=sch_name, **target)
    pcb_list = call('pcb-list', ['pcb', 'list', '--include-pads'] + base +
                    _document_args(pcb_doc), document=pcb_uuid,
                    document_name=pcb_name, **target)
    dump = call('pcb-dump', ['pcb', 'dump', '--include-copper'] + base +
                _document_args(pcb_doc), document=pcb_uuid,
                document_name=pcb_name, **target)
    sch_drc = call('sch-drc', ['sch', 'drc', '--json'] + base +
                   _document_args(sch_doc), document=sch_uuid,
                   document_name=sch_name, **target)
    pcb_drc = call('pcb-drc', ['pcb', 'drc', '--json'] + base +
                   _document_args(pcb_doc), document=pcb_uuid,
                   document_name=pcb_name, **target)
    pcb_check = call('pcb-check', ['pcb', 'check', '--json'] + base +
                     _document_args(pcb_doc), document=pcb_uuid,
                     document_name=pcb_name, **target)

    items = []

    def read_item(cap_id, interface, labels, measured, limits=()):
        gates = [_read_gate(calls[label], measured(calls[label]['body']))
                 for label in labels]
        status, reason = _combine_gates(gates)
        evidence = _compact_evidence(calls[labels[0]]['record'],
                                     calls[labels[0]]['body'])
        evidence['commands'] = [_compact_evidence(
            calls[label]['record'], calls[label]['body']) for label in labels]
        items.append(_capability_item(cap_id, status, interface,
                                      version=version, evidence=evidence,
                                      limits=list(limits), reason=reason))

    def has_components(body):
        return isinstance(body, dict) and isinstance(
            body.get('components'), list)

    def sch_net_measured(body):
        if not isinstance(body, dict):
            return False
        nets = body.get('nets')
        return (isinstance(nets, (list, dict)) and
                body.get('netlistAvailable') is not False)

    def geometry_measured(body):
        if not has_components(body):
            return False
        outline = body.get('outline')
        return isinstance(outline, dict) and isinstance(
            outline.get('points'), list)

    def copper_measured(body):
        if not isinstance(body, dict) or not isinstance(
                body.get('copper'), dict):
            return False
        copper = body['copper']
        availability = copper.get('availability')
        if not isinstance(availability, dict):
            return False
        required = ('fills', 'poured', 'pours', 'regions', 'routing', 'vias')
        if any(availability.get(key) != 'available' for key in required):
            return False
        return all(isinstance(copper.get(key), list)
                   for key in ('lines', 'arcs', 'vias', 'pours'))

    def sch_drc_measured(body):
        if not isinstance(body, dict):
            return False
        return (isinstance(body.get('passed'), bool) and
                (isinstance(body.get('summary'), dict) or
                 isinstance(body.get('violations'), list) or
                 isinstance(body.get('fatal'), int)))

    def pcb_drc_measured(body):
        try:
            return pcb_evidence.parse_drc(body).get('measured') is True
        except (TypeError, ValueError):
            return False

    def pcb_check_measured(body):
        try:
            return pcb_evidence.parse_pcb_check(body).get('measured') is True
        except (TypeError, ValueError):
            return False

    def identity_measured(body):
        if isinstance(body, dict) and _first(
                body, 'uuid', 'projectUuid', 'friendlyName', 'name'):
            return True
        return False

    def documents_measured(body):
        return isinstance(body, dict) and isinstance(
            _first(body, 'documents', 'docs', 'items'), list)

    read_item('project_doc_identity',
              'zhigou project info + doc ls',
              ('project-info', 'doc-list'),
              lambda body: identity_measured(body) if
              calls['project-info']['body'] is body
              else documents_measured(body),
              limits=['a --project name route is not target proof; use '
                      '--window plus explicit document UUIDs'])
    # Evaluate the two identity calls separately so an empty document list is
    # distinguishable from a failed read.
    identity_gate = _read_gate(calls['project-info'],
                               identity_measured(calls['project-info']['body']))
    docs_gate = _read_gate(calls['doc-list'],
                           documents_measured(calls['doc-list']['body']))
    identity_status, identity_reason = _combine_gates([identity_gate,
                                                       docs_gate])
    items[-1]['status'] = identity_status
    items[-1]['reason'] = identity_reason
    items[-1]['evidence'] = {
        'commands': [_compact_evidence(calls['project-info']['record'],
                                       calls['project-info']['body']),
                     _compact_evidence(calls['doc-list']['record'],
                                       calls['doc-list']['body'])],
        **_compact_evidence(calls['project-info']['record'],
                            calls['project-info']['body']),
    }

    read_item('sch_object_read', 'zhigou sch read', ('sch-read',),
              has_components,
              limits=['inactive pages may return shallow data'])
    read_item('sch_net_read', 'zhigou sch read (nets)', ('sch-read',),
              sch_net_measured,
              limits=['netlistAvailable=false means the net table was not '
                      'measured'])
    read_item('pcb_object_read', 'zhigou pcb list --include-pads',
              ('pcb-list',), has_components,
              limits=['an empty list is measured only when the host reports '
                      'no components, not when a read failed'])
    read_item('pcb_geometry_read', 'zhigou pcb dump (components + outline)',
              ('pcb-dump',), geometry_measured,
              limits=['the board outline requires the PCB foreground document; '
                      'a missing outline is unknown, not an empty board'])
    read_item('pcb_copper_read', 'zhigou pcb dump --include-copper',
              ('pcb-dump',), copper_measured,
              limits=['each copper category must report availability=available'])
    read_item('sch_erc', 'zhigou sch drc --json', ('sch-drc',),
              sch_drc_measured)
    read_item('pcb_drc', 'zhigou pcb drc --json', ('pcb-drc',),
              pcb_drc_measured)
    read_item('pcb_check', 'zhigou pcb check --json', ('pcb-check',),
              pcb_check_measured)

    help_specs = (
        ('move_component', 'zhigou pcb modify', ['pcb', 'modify', '--help']),
        ('move_text', 'zhigou sch attribute-move',
         ['sch', 'attribute-move', '--help']),
        ('route_track', 'zhigou pcb track', ['pcb', 'track', '--help']),
        ('place_via', 'zhigou pcb via', ['pcb', 'via', '--help']),
        ('lock', 'zhigou pcb lock', ['pcb', 'lock', '--help']),
        ('save', 'zhigou pcb save + sch save', ['pcb', 'save', '--help']),
        ('reopen', 'zhigou doc reload', ['doc', 'reload', '--help']),
        ('screenshot', 'zhigou pcb snapshot', ['pcb', 'snapshot', '--help']),
        ('export_archive', 'zhigou project export',
         ['project', 'export', '--help']),
        ('undo', 'zhigou undo', ['undo', '--help']),
    )
    for cap_id, interface, args in help_specs:
        limits = ['write/side-effect capability: only the CLI interface was '
                  'checked; no mutation was executed']
        if cap_id == 'undo':
            limits.append('the host exposes no public undo; recovery relies on '
                          'checkpoints and idempotent journal replay')
        items.append(_help_probe(run, cap_id, interface, args,
                                 zhigou=zhigou, version=version,
                                 timeout=timeout, limits=limits))

    order = {cap_id: index for index, cap_id in enumerate(CAPABILITY_IDS)}
    items.sort(key=lambda item: order.get(item['id'], 999))
    # If the host already disagreed with the requested project, no read result
    # may be attributed to that target -- including a bare result that did not
    # echo a context of its own.
    host_mismatch = bool(calls['project-info']['identity_mismatch'] or
                         calls['doc-list']['identity_mismatch'])
    if host_mismatch:
        for item in items:
            if item['status'] == STATUS_AVAILABLE:
                item['status'] = STATUS_UNKNOWN
                item['reason'] = ('target_mismatch: the probe target did not '
                                  'match the host identity')
    payload = schemas.new_capabilities(
        host={'window_id': _text(window) or None,
              'project': _text(project) or None,
              'zhigou': zhigou,
              'probed_at': pcb_cli.utc_now()},
        adapter={'name': 'zhigou-cli', 'interface': 'cli',
                 'version': version},
        items=items,
    )
    return schemas.validate_capabilities(payload)


# ---------------------------------------------------------------------------
# project / document identity
# ---------------------------------------------------------------------------

def _project_identity(body):
    project = body if isinstance(body, dict) else {}
    nested = project.get('project') if isinstance(project.get('project'),
                                                  dict) else {}
    return {
        'uuid': _text(_first(project, 'uuid', 'projectUuid', 'id') or
                      _first(nested, 'uuid', 'projectUuid')),
        'name': _text(_first(project, 'friendlyName', 'name', 'projectName')
                      or _first(nested, 'friendlyName', 'name')),
    }


def _document_type(value):
    text = _text(value).lower()
    if text in ('schematic', 'sch', 'schematic page', 'page'):
        return 'schematic'
    if text in ('pcb', 'board', 'pcb document'):
        return 'pcb'
    return _text(value)


def _document_list(body):
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        items = _first(body, 'documents', 'docs', 'items')
    else:
        items = None
    if not isinstance(items, list):
        return None
    documents = []
    for item in items:
        if not isinstance(item, dict):
            continue
        uuid = _text(_first(item, 'uuid', 'documentUuid', 'id'))
        if not uuid:
            continue
        documents.append({
            'uuid': uuid,
            'type': _document_type(_first(item, 'type', 'documentType',
                                          'docType')),
            'name': _text(_first(item, 'name', 'documentName', 'title')),
        })
    return documents


# ---------------------------------------------------------------------------
# schematic normalizer
# ---------------------------------------------------------------------------

def _identity(value):
    if isinstance(value, dict):
        identity = {}
        for key in ('name', 'uuid', 'libraryUuid', 'deviceUuid'):
            if _text(value.get(key)):
                identity[key] = _text(value[key])
        return identity or None
    if isinstance(value, str) and value.strip():
        return {'name': value.strip()}
    return None


def _unknown_entry(field, reason):
    return {'field': field, 'reason': reason}


def _normalize_nets(raw):
    if isinstance(raw, list):
        nets = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            members = item.get('pins') or item.get('members') or []
            nets.append({
                'name': _text(_first(item, 'net', 'name')),
                'members': [_text(member) for member in members
                            if _text(member)],
                'degree': item.get('degree'),
                'global': item.get('isGlobal'),
            })
        return nets
    if isinstance(raw, dict):
        return [{'name': _text(name),
                 'members': [_text(member) for member in members or []
                             if _text(member)]}
                for name, members in raw.items()]
    return None


def normalize_sch_read(payload):
    """Normalize ``sch read`` (envelope or bare result) for observation use.

    Only ``componentType == 'part'`` objects become components; sheets and
    netflags are counted under ``excluded_objects`` instead of being silently
    dropped.  Missing measurements are ``None``/``unknown`` -- an empty
    schematic is an empty list only when the read actually succeeded.
    """
    body, envelope = _input_body(payload)
    unknown = []
    if not isinstance(body, dict):
        return {
            'document_uuid': None, 'components': None, 'component_count': None,
            'excluded_objects': {}, 'nets': None, 'net_count': None,
            'floating_pins': None, 'check': None,
            'availability': {'components': STATUS_UNKNOWN,
                             'nets': STATUS_UNKNOWN,
                             'check': STATUS_UNKNOWN},
            'unknown': [_unknown_entry(
                'schematic', 'sch read returned no JSON object')],
        }

    context = _contexts(envelope or {}, body)
    document_uuid = None
    for item in context:
        if isinstance(item, dict):
            document_uuid = document_uuid or _text(
                _first(item, 'documentUuid', 'document_uuid'))
    raw_components = body.get('components')
    components_available = body.get('componentsAvailability')
    excluded = {}
    components = []
    if isinstance(raw_components, list):
        rotation_seen = mirror_seen = device_seen = symbol_seen = False
        pin_id_seen = False
        for raw in raw_components:
            if not isinstance(raw, dict):
                continue
            kind = _text(raw.get('componentType')) or 'part'
            if kind != 'part':
                excluded[kind] = excluded.get(kind, 0) + 1
                continue
            raw_pins = raw.get('pins') if isinstance(raw.get('pins'), list) \
                else []
            pins = []
            for pin in raw_pins:
                if not isinstance(pin, dict):
                    continue
                pin_id_seen = pin_id_seen or bool(
                    _text(_first(pin, 'primitiveId', 'primitive_id')))
                pins.append({
                    'number': _text(_first(pin, 'number', 'pinNumber',
                                           'name')),
                    'name': _text(_first(pin, 'pinName', 'name')),
                    'net': _text(_first(pin, 'net', 'netName')) or None,
                    'primitive_id': _text(_first(pin, 'primitiveId',
                                                 'primitive_id')) or None,
                })
            rotation_seen = rotation_seen or 'rotation' in raw
            mirror_seen = mirror_seen or (
                'mirror' in raw or 'mirrored' in raw)
            device = _identity(raw.get('device') or raw.get('component'))
            symbol = _identity(raw.get('symbol'))
            device_seen = device_seen or device is not None
            symbol_seen = symbol_seen or symbol is not None
            components.append({
                'designator': _text(raw.get('designator')),
                'component_type': kind,
                'primitive_id': _text(_first(raw, 'primitiveId',
                                             'primitive_id')) or None,
                'unique_id': _text(_first(raw, 'uniqueId', 'unique_id'))
                or None,
                'uniqueId': _text(_first(raw, 'uniqueId', 'unique_id'))
                or None,
                'x': raw.get('x'),
                'y': raw.get('y'),
                'rotation': raw.get('rotation'),
                'mirror': raw.get('mirror', raw.get('mirrored')),
                'device': device,
                'symbol': symbol,
                'footprint': _identity(raw.get('footprint')),
                'name': _text(raw.get('name')) or None,
                'supplier_id': _text(_first(raw, 'supplierId',
                                            'supplier_id')) or None,
                'pins': pins,
            })
        if components:
            for field, measured, reason in (
                    ('schematic.components[].rotation', rotation_seen,
                     'sch read does not report component rotation'),
                    ('schematic.components[].mirror', mirror_seen,
                     'sch read does not report mirroring'),
                    ('schematic.components[].device', device_seen,
                     'sch read does not report library device identity'),
                    ('schematic.components[].symbol', symbol_seen,
                     'sch read does not report symbol identity'),
                    ('schematic.components[].pins[].primitive_id',
                     pin_id_seen,
                     'sch read does not report pin primitive ids')):
                if not measured:
                    unknown.append(_unknown_entry(field, reason))
    else:
        components = None
        components_available = STATUS_UNAVAILABLE

    raw_nets = body.get('nets')
    nets = _normalize_nets(raw_nets)
    netlist_available = body.get('netlistAvailable')
    if nets is None or netlist_available is False:
        nets_unknown = True
        nets = None if netlist_available is False or raw_nets is None else nets
    else:
        nets_unknown = False
    floating = body.get('floatingPins', body.get('floating_pins'))
    if not isinstance(floating, list):
        floating = None if 'floatingPins' in body or \
            'floating_pins' in body else []
    check = body.get('check') if isinstance(body.get('check'), dict) else None

    availability = {
        'components': (STATUS_AVAILABLE if isinstance(raw_components, list)
                       and components_available != STATUS_UNAVAILABLE
                       else STATUS_UNKNOWN),
        'nets': STATUS_UNKNOWN if nets_unknown else STATUS_AVAILABLE,
        'check': STATUS_AVAILABLE if check is not None else STATUS_UNKNOWN,
    }
    if nets_unknown:
        unknown.append(_unknown_entry(
            'schematic.nets', 'net list was not measured (netlistAvailable='
                              '%r)' % (netlist_available,)))
    if check is None:
        unknown.append(_unknown_entry('schematic.check',
                                      'sch read returned no check object'))
    if floating is None:
        unknown.append(_unknown_entry('schematic.floating_pins',
                                      'floating pin list was not measured'))

    return {
        'document_uuid': document_uuid,
        'components': components,
        'component_count': len(components) if components is not None else None,
        'excluded_objects': excluded,
        'nets': nets,
        'net_count': len(nets) if nets is not None else None,
        'floating_pins': floating,
        'check': check,
        'availability': availability,
        'unknown': unknown,
    }


# ---------------------------------------------------------------------------
# PCB dump normalizer
# ---------------------------------------------------------------------------

def normalize_text_list(payload):
    """Normalize ``sch text-list`` for readability evidence.

    Free text is not part of ``sch read``; without this call a text overlap can
    never be checked or moved.  A missing payload is ``None``, not an empty
    list.
    """
    body, envelope = _input_body(payload)
    if not isinstance(body, dict):
        return {'texts': None, 'count': None,
                'unknown': [_unknown_entry(
                    'schematic.texts', 'sch text-list returned no JSON object')]}
    raw = body.get('texts')
    if raw is None:
        raw = body.get('items')
    texts = []
    unknown = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            texts.append({
                'primitiveId': _text(_first(item, 'primitiveId', 'id',
                                            'primitive_id')),
                'content': _text(_first(item, 'content', 'Content', 'text')),
                'x': item.get('x', item.get('X')),
                'y': item.get('y', item.get('Y')),
                'rotation': item.get('rotation', item.get('Rotation')),
                'fontSize': item.get('fontSize', item.get('FontSize')),
                'color': item.get('color', item.get('TextColor')),
            })
    else:
        texts = None
        unknown.append(_unknown_entry(
            'schematic.texts', 'text-list payload carries no texts array'))
    return {'texts': texts, 'count': len(texts) if texts is not None else None,
            'unknown': unknown}


def _availability(value, key):
    if isinstance(value, dict):
        item = value.get(key)
        if isinstance(item, str):
            return item
    return None


def _normalize_pad(pad):
    if not isinstance(pad, dict):
        return None
    return {
        'primitive_id': _text(_first(pad, 'primitiveId', 'primitive_id'))
        or None,
        'number': _text(_first(pad, 'padNumber', 'number')),
        'net': _text(_first(pad, 'net', 'netName')) or None,
        'x': pad.get('x'),
        'y': pad.get('y'),
        'layer': pad.get('layer'),
        'shape': copy.deepcopy(pad.get('shape')),
        'width': pad.get('width'),
        'height': pad.get('height'),
        'rotation': pad.get('rotation'),
        'hole': copy.deepcopy(pad.get('hole')),
    }


def _normalize_component(raw):
    raw_pads = raw.get('pads') if isinstance(raw.get('pads'), list) else None
    pad_availability = _availability(raw.get('availability'), 'pads')
    pads_measured = raw_pads is not None and \
        pad_availability != STATUS_UNAVAILABLE
    pads = []
    if pads_measured:
        for pad in raw_pads:
            normalized = _normalize_pad(pad)
            if normalized is not None:
                pads.append(normalized)
    return {
        'designator': _text(raw.get('designator')) or None,
        'primitive_id': _text(_first(raw, 'primitiveId', 'primitive_id'))
        or None,
        'unique_id': _text(_first(raw, 'uniqueId', 'unique_id')) or None,
        'uniqueId': _text(_first(raw, 'uniqueId', 'unique_id')) or None,
        'device': raw.get('device') if not isinstance(raw.get('device'), dict)
        else _identity(raw.get('device')),
        'name': _text(raw.get('name')) or None,
        'x': raw.get('x'),
        'y': raw.get('y'),
        'rotation': raw.get('rotation'),
        'layer': raw.get('layer'),
        'locked': raw.get('locked') if isinstance(raw.get('locked'), bool)
        else None,
        'bbox': copy.deepcopy(raw.get('bbox')),
        'pads': pads if pads_measured else None,
        'pad_count': len(pads) if pads_measured else None,
    }


def _holes_from_components(components):
    if components is None:
        return None
    holes = []
    for component in components:
        for pad in component.get('pads') or []:
            raw = pad.get('hole')
            if not isinstance(raw, list) or not raw:
                continue
            holes.append({
                'designator': component.get('designator'),
                'pad': pad.get('number'),
                'primitive_id': pad.get('primitive_id'),
                'shape': _text(raw[0]).upper() or None,
                'width': raw[1] if len(raw) > 1 else None,
                'height': raw[2] if len(raw) > 2 else None,
                'x': pad.get('x'),
                'y': pad.get('y'),
            })
    return holes


def _normalize_lines(lines, kind):
    result = []
    if not isinstance(lines, list):
        return None
    for raw in lines:
        if not isinstance(raw, dict):
            continue
        result.append({
            'primitive_id': _text(_first(raw, 'primitiveId', 'primitive_id'))
            or None,
            'kind': kind,
            'net': _text(_first(raw, 'net', 'netName')) or None,
            'layer': raw.get('layer'),
            'width': raw.get('lineWidth', raw.get('width')),
            'locked': raw.get('locked') if isinstance(raw.get('locked'),
                                                      bool) else None,
            'start': {'x': raw.get('startX'), 'y': raw.get('startY')}
            if 'startX' in raw or 'startY' in raw else None,
            'end': {'x': raw.get('endX'), 'y': raw.get('endY')}
            if 'endX' in raw or 'endY' in raw else None,
            'raw_sha256': _canonical_sha(raw),
        })
    return result


def _normalize_vias(vias):
    if not isinstance(vias, list):
        return None
    result = []
    for raw in vias:
        if not isinstance(raw, dict):
            continue
        result.append({
            'primitive_id': _text(_first(raw, 'primitiveId', 'primitive_id'))
            or None,
            'net': _text(_first(raw, 'net', 'netName')) or None,
            'x': raw.get('x'),
            'y': raw.get('y'),
            'diameter': raw.get('diameter'),
            'hole_diameter': raw.get('holeDiameter'),
            'locked': raw.get('locked') if isinstance(raw.get('locked'),
                                                      bool) else None,
            'raw_sha256': _canonical_sha(raw),
        })
    return result


def _normalize_pours(pours):
    if not isinstance(pours, list):
        return None
    result = []
    for raw in pours:
        if not isinstance(raw, dict):
            continue
        source = raw.get('source') if raw.get('source') is not None else \
            raw.get('points')
        result.append({
            'primitive_id': _text(_first(raw, 'primitiveId', 'primitive_id'))
            or None,
            'net': _text(_first(raw, 'net', 'netName')) or None,
            'layer': raw.get('layer'),
            'pour_name': _text(_first(raw, 'pourName', 'name')) or None,
            'priority': raw.get('priority'),
            'locked': raw.get('locked') if isinstance(raw.get('locked'),
                                                      bool) else None,
            'fill_method': raw.get('fillMethod'),
            'line_width': raw.get('lineWidth', raw.get('line_width')),
            'geometry_available': raw.get('geometryAvailable'),
            # Keep a geometry fingerprint instead of the full polygon: the
            # raw dump's ``source`` can be huge, but dropping it entirely made
            # every normalized pour geometry comparison a no-op.
            'geometry_sha256': (_canonical_sha(source)
                                if source is not None else None),
            'raw_sha256': _canonical_sha(raw),
        })
    return result


def _normalize_poured(poured):
    if not isinstance(poured, list):
        return None
    result = []
    for raw in poured:
        if not isinstance(raw, dict):
            continue
        fills = raw.get('fills')
        result.append({
            'id': _text(_first(raw, 'id', 'primitiveId')) or None,
            'layer': raw.get('layer'),
            'net': _text(_first(raw, 'net', 'netName')) or None,
            'fill_count': len(fills) if isinstance(fills, list) else None,
            'raw_sha256': _canonical_sha(raw),
        })
    return result


def _normalize_regions(regions):
    if not isinstance(regions, list):
        return None
    result = []
    for raw in regions:
        if not isinstance(raw, dict):
            continue
        result.append({
            'primitive_id': _text(_first(raw, 'primitiveId', 'primitive_id'))
            or None,
            'layer': raw.get('layer'),
            'locked': raw.get('locked') if isinstance(raw.get('locked'),
                                                      bool) else None,
            'bbox': copy.deepcopy(raw.get('bbox')),
            'region_name': _text(_first(raw, 'regionName', 'name')) or None,
            'rule_types': copy.deepcopy(raw.get('ruleTypeNames')),
            'geometry_available': raw.get('geometryAvailable'),
            'raw_sha256': _canonical_sha(raw),
        })
    return result


def _derive_nets(components, tracks, vias, pours):
    if components is None and tracks is None and vias is None and \
            pours is None:
        return None
    nets = {}

    def entry(name):
        return nets.setdefault(name, {'name': name, 'members': [],
                                      'tracks': 0, 'vias': 0, 'pours': 0})

    for component in components or []:
        for pad in component.get('pads') or []:
            name = pad.get('net')
            if not name:
                continue
            item = entry(name)
            item['members'].append('%s.%s' % (
                component.get('designator') or '?', pad.get('number') or '?'))
    for track in tracks or []:
        if track.get('net'):
            entry(track['net'])['tracks'] += 1
    for via in vias or []:
        if via.get('net'):
            entry(via['net'])['vias'] += 1
    for pour in pours or []:
        if pour.get('net'):
            entry(pour['net'])['pours'] += 1
    for item in nets.values():
        item['members'] = sorted(set(item['members']))
    return [nets[name] for name in sorted(nets)]


def normalize_pcb_dump(payload):
    """Normalize a measured ``pcb dump`` (envelope or bare snapshot).

    Measured-empty and unreadable are different: an empty category is ``[]``
    only when the host reports it available; otherwise it is ``None`` and an
    ``unknown`` entry names the missing evidence.
    """
    body, envelope = _input_body(payload)
    unknown = []
    if not isinstance(body, dict):
        return {
            'document_uuid': None, 'project_uuid': None, 'project_name': None,
            'components': None, 'component_count': None,
            'outline': None, 'holes': None, 'keepouts': None, 'regions': None,
            'nets': None, 'tracks': None, 'vias': None, 'pours': None,
            'poured': None, 'fills': None, 'rules': None,
            'copper_layers': None, 'copperLayers': None,
            'routed_lines': None, 'unrouted': None, 'drc': None, 'check': None,
            'captured_at': None, 'capturedAt': None,
            'semantic_sha256': None, 'semanticSha256': None,
            'availability': {}, 'coverage': {}, 'partial': [],
            'unknown': [_unknown_entry('pcb',
                                       'pcb dump returned no JSON object')],
        }

    capture = body.get('capture') if isinstance(body.get('capture'),
                                                dict) else {}
    availability = body.get('availability') if isinstance(
        body.get('availability'), dict) else {}
    copper = body.get('copper') if isinstance(body.get('copper'), dict) else {}
    copper_availability = copper.get('availability') if isinstance(
        copper.get('availability'), dict) else {}

    raw_components = body.get('components')
    components_availability = _text(body.get('componentsAvailability')) or \
        _availability(availability, 'components')
    components_measured = isinstance(raw_components, list) and \
        components_availability != STATUS_UNAVAILABLE
    components = None
    if isinstance(raw_components, list):
        normalized = [_normalize_component(raw) for raw in raw_components
                      if isinstance(raw, dict)]
        if components_measured:
            components = normalized
            if any(component.get('locked') is None for component in components):
                unknown.append(_unknown_entry(
                    'pcb.components[].locked',
                    'pcb dump does not report a locked flag for every '
                    'component'))
            if any(component.get('pads') is None for component in components):
                unknown.append(_unknown_entry(
                    'pcb.components[].pads',
                    'at least one component has no measured pad list'))
        else:
            unknown.append(_unknown_entry(
                'pcb.components', 'components read reported unavailable'))
    else:
        unknown.append(_unknown_entry(
            'pcb.components', 'pcb dump has no components list'))

    outline_raw = body.get('outline')
    outline = None
    if isinstance(outline_raw, dict) and isinstance(
            outline_raw.get('points'), list):
        outline = {
            'points': copy.deepcopy(outline_raw.get('points')),
            'bbox': copy.deepcopy(outline_raw.get('bbox')),
            'source': outline_raw.get('source'),
            'format': outline_raw.get('format'),
            'point_count': len(outline_raw.get('points') or []),
        }
    else:
        unknown.append(_unknown_entry(
            'pcb.outline',
            'board outline was not measured (the PCB may not be the '
            'foreground document)'))

    holes = _holes_from_components(components)
    if holes is None:
        unknown.append(_unknown_entry(
            'pcb.holes', 'pad hole geometry was not measured'))
    elif components:
        unavailable_holes = any(
            _availability(raw.get('availability'), 'hole') ==
            STATUS_UNAVAILABLE
            for raw in raw_components if isinstance(raw, dict))
        if unavailable_holes:
            holes = None
            unknown.append(_unknown_entry(
                'pcb.holes', 'at least one pad reported hole geometry '
                             'unavailable'))

    regions_raw = body.get('regions')
    if not isinstance(regions_raw, list):
        regions_raw = copper.get('regions')
    regions_availability = _availability(copper_availability, 'regions')
    if isinstance(regions_raw, list) and regions_availability != \
            STATUS_UNAVAILABLE:
        regions = _normalize_regions(regions_raw)
    else:
        regions = None
        unknown.append(_unknown_entry(
            'pcb.regions', 'keep-out/rule regions were not measured'))
    keepouts = regions

    def category(key, source_key, normalizer, availability=None):
        raw = copper.get(source_key, body.get(source_key))
        value = normalizer(raw) if isinstance(raw, list) else None
        if value is None:
            unknown.append(_unknown_entry(
                'pcb.%s' % key, '%s was not measured' % source_key))
        elif availability is not None and availability != STATUS_AVAILABLE:
            unknown.append(_unknown_entry(
                'pcb.%s' % key, '%s availability=%r'
                % (source_key, availability)))
        return value

    tracks = None
    lines = category('tracks', 'lines',
                     lambda raw: _normalize_lines(raw, 'line'),
                     _availability(copper_availability, 'routing'))
    arcs = category('arcs', 'arcs',
                    lambda raw: _normalize_lines(raw, 'arc'),
                    _availability(copper_availability, 'routing'))
    if lines is not None or arcs is not None:
        tracks = (lines or []) + (arcs or [])
    vias = category('vias', 'vias', _normalize_vias,
                    _availability(copper_availability, 'vias'))
    pours = category('pours', 'pours', _normalize_pours,
                     _availability(copper_availability, 'pours'))
    poured = category('poured', 'poured', _normalize_poured,
                      _availability(copper_availability, 'poured'))
    fills = category('fills', 'fills',
                     lambda raw: [
                         {'primitive_id': _text(_first(item, 'primitiveId')),
                          'net': _text(item.get('net')) or None,
                          'layer': item.get('layer'),
                          'locked': item.get('locked'),
                          'fill_mode': item.get('fillMode'),
                          'bbox': copy.deepcopy(item.get('bbox')),
                          'geometry_available': item.get('geometryAvailable'),
                          'raw_sha256': _canonical_sha(item)}
                         for item in raw if isinstance(item, dict)],
                     _availability(copper_availability, 'fills'))

    nets = _derive_nets(components, tracks, vias, pours)
    if nets is None:
        unknown.append(_unknown_entry(
            'pcb.nets', 'no measured component/copper category carried nets'))
    elif any(value is None for value in (components, tracks, vias, pours)):
        unknown.append(_unknown_entry(
            'pcb.nets',
            'at least one net-bearing category was not measured; the net '
            'list is a measured subset, not a complete netlist'))

    rules = body.get('rules') if isinstance(body.get('rules'), dict) else None
    if rules is None:
        unknown.append(_unknown_entry('pcb.rules', 'live DRC rules missing'))
    copper_layers = body.get('copperLayers')
    if not isinstance(copper_layers, int) or isinstance(copper_layers, bool):
        copper_layers = None
        unknown.append(_unknown_entry('pcb.copperLayers',
                                      'copper layer count missing'))
    routed_lines = body.get('routedLines')
    unrouted = body.get('unrouted')
    if unrouted is None:
        unknown.append(_unknown_entry(
            'pcb.unrouted',
            'the dump reports a routed line count but no unrouted state'))

    drc = body.get('drc') if isinstance(body.get('drc'), dict) else None
    check = body.get('check') if isinstance(body.get('check'), dict) else None
    if drc is None:
        unknown.append(_unknown_entry('pcb.drc',
                                      'no DRC receipt on the dump'))
    if check is None:
        unknown.append(_unknown_entry('pcb.check',
                                      'no pcb check receipt on the dump'))

    copper_complete = all(
        copper_availability.get(key) == STATUS_AVAILABLE
        for key in ('fills', 'poured', 'pours', 'regions', 'routing', 'vias'))
    coverage = {
        'components': 'complete' if components is not None else 'unknown',
        'outline': 'complete' if outline is not None else 'unknown',
        'holes': 'complete' if holes is not None else 'unknown',
        'regions': 'complete' if regions is not None else 'unknown',
        'copper': 'complete' if copper_complete else (
            'partial' if copper else 'unknown'),
        'rules': 'complete' if rules is not None else 'unknown',
        'layers': 'complete' if copper_layers is not None else 'unknown',
    }
    captured_at = body.get('capturedAt', body.get('captured_at'))
    semantic = body.get('semanticSha256', body.get('semantic_sha256'))
    return {
        'document_uuid': _text(_first(capture, 'documentUuid',
                                      'document_uuid')) or None,
        'project_uuid': _text(_first(capture, 'projectUuid', 'project_uuid'))
        or None,
        'project_name': _text(_first(capture, 'projectName', 'project_name'))
        or None,
        'components': components,
        'component_count': len(components) if components is not None else None,
        'outline': outline,
        'holes': holes,
        'keepouts': keepouts,
        'regions': regions,
        'nets': nets,
        'tracks': tracks,
        'track_count': len(tracks) if tracks is not None else None,
        'vias': vias,
        'via_count': len(vias) if vias is not None else None,
        'pours': pours,
        'pour_count': len(pours) if pours is not None else None,
        'poured': poured,
        'fills': fills,
        'rules': copy.deepcopy(rules),
        'copper_layers': copper_layers,
        'copperLayers': copper_layers,
        'routed_lines': routed_lines,
        'unrouted': unrouted,
        'drc': drc,
        'check': check,
        'captured_at': captured_at,
        'capturedAt': captured_at,
        'semantic_sha256': semantic,
        'semanticSha256': semantic,
        'availability': {
            'components': components_availability or None,
            'copper': _availability(availability, 'copper'),
            'categories': copy.deepcopy(copper_availability),
        },
        'coverage': coverage,
        'partial': copy.deepcopy(body.get('partial') or []),
        'unknown': unknown,
    }


def _normalize_sch_drc(body):
    if not isinstance(body, dict):
        return None
    summary = body.get('summary') if isinstance(body.get('summary'), dict) \
        else {}
    violations = body.get('violations') if isinstance(
        body.get('violations'), list) else []
    fatal = body.get('fatal')
    return {
        'passed': body.get('passed') if isinstance(body.get('passed'), bool)
        else None,
        'fatal': fatal if isinstance(fatal, int) and not isinstance(fatal,
                                                                   bool)
        else None,
        'summary': copy.deepcopy(summary),
        'violations': copy.deepcopy(violations),
        'counts_available': body.get('countsAvailable'),
        'details_available': body.get('detailsAvailable'),
        'measured': isinstance(body.get('passed'), bool) and (
            bool(summary) or isinstance(body.get('fatal'), int) or
            isinstance(body.get('violations'), list)),
    }


# ---------------------------------------------------------------------------
# observation collection
# ---------------------------------------------------------------------------

def _drop_unknown(section, fields):
    if not isinstance(section, dict):
        return
    wanted = set(fields)
    section['unknown'] = [entry for entry in section.get('unknown') or []
                          if entry.get('field') not in wanted]


def _evidence_write(directory, index, label, record, body):
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '-', label).strip('-') or 'command'
    path = os.path.join(directory, '%02d-%s.json' % (index, safe))
    payload = record.get('payload')
    if payload is None and body is None:
        payload = None
    value = {
        'schema': EVIDENCE_SCHEMA,
        'label': label,
        'argv': record.get('argv') or [],
        'exit': record.get('exit'),
        'ok': _record_ok(record),
        'error': record.get('error'),
        'payload': payload,
        'body': body if payload is None else None,
        'stdout_sha256': schemas.sha256_text(_text(record.get('stdout'))),
        'stderr_sha256': schemas.sha256_text(_text(record.get('stderr'))),
    }
    pcb_cli.write_json(path, value)
    return {
        'role': label,
        'path': os.path.abspath(path),
        'sha256': pcb_cli.sha256_file(path),
        'bytes': os.path.getsize(path),
        'command': record.get('argv') or [],
        'exit': record.get('exit'),
        'ok': _record_ok(record),
    }


def collect_observation(*, runner=None, zhigou=None, window, project,
                        sch_doc, pcb_doc, project_name=None, evidence_dir=None,
                        timeout=120):
    """Collect one versioned observation with identity-enforced reads.

    Every command is pinned to ``window`` (preferred) or ``project`` plus an
    explicit document UUID or name.  ``project``/``sch_doc``/``pcb_doc`` may be
    names; they are resolved against the live project/document list, and a
    response whose echoed context names another project/document raises
    ``target_mismatch``.  Failed or timed-out reads are recorded as
    degradations and make their section unknown; they never become empty
    lists.
    """
    for label, value in (('window', window), ('project', project),
                         ('sch_doc', sch_doc), ('pcb_doc', pcb_doc)):
        if not _text(value):
            raise schemas.FeedbackError(
                schemas.FAILURE_INVALID_INPUT,
                'collect_observation requires %s' % label)
    run = runner or pcb_cli.run
    base = _target_args(window=window, project=project)
    commands = []
    degradations = []
    evidence = []
    unknown = []

    expected_project_uuid = _text(project) if _looks_like_uuid(project) \
        else None
    expected_project_name = None if _looks_like_uuid(project) else _text(project)
    simulation = {'simulated': False}

    def execute(index, label, args, *, document=None, document_name=None,
                project_uuid=None, project_name=None):
        record = _invoke(run, args, zhigou=zhigou, timeout=timeout)
        body, envelope = _body(record)
        if isinstance(envelope, dict) and envelope.get('simulated') is True:
            simulation['simulated'] = True
        identity = {'context_echoed': False, 'verified': None}
        if _record_state(record) in ('ok', 'failed') and body is not None:
            identity = _verify_identity(
                record, body, project=project_uuid, project_name=project_name,
                document=document, document_name=document_name, where=label)
        state = _record_state(record)
        reason = None
        if state == 'timeout':
            reason = 'timeout: %s' % _text(record.get('error'))
        elif state == 'host_unavailable':
            reason = 'host_unavailable: %s' % _text(record.get('error'))
        elif state == 'failed':
            reason = 'command_failed: exit=%s' % (record.get('exit'),)
        elif body is None:
            reason = 'no_json_payload'
        if reason is not None:
            degradations.append({
                'source': label,
                'reason': reason,
                'argv': record.get('argv') or [],
                'exit': record.get('exit'),
                'ok': _record_ok(record),
            })
        elif not identity.get('context_echoed'):
            degradations.append({
                'source': label,
                'reason': 'identity_context_not_echoed',
                'argv': record.get('argv') or [],
                'exit': record.get('exit'),
                'ok': _record_ok(record),
            })
        elif identity.get('verified') is None:
            degradations.append({
                'source': label,
                'reason': 'identity_not_comparable',
                'argv': record.get('argv') or [],
                'exit': record.get('exit'),
                'ok': _record_ok(record),
            })
        commands.append({
            'command': label,
            'argv': record.get('argv') or [],
            'exit': record.get('exit'),
            'ok': _record_ok(record),
            'state': state,
            'context_echoed': bool(identity.get('context_echoed')),
            'identity_verified': identity.get('verified'),
        })
        if evidence_dir:
            evidence.append(_evidence_write(evidence_dir, index, label,
                                            record, body))
        return {'record': record, 'body': body, 'envelope': envelope,
                'state': state, 'reason': reason, 'identity': identity}

    info_start = execute(1, 'project-info', ['project', 'info', '--json'] +
                         base, project_uuid=expected_project_uuid,
                         project_name=expected_project_name)
    docs_start = execute(2, 'doc-list', ['doc', 'ls', '--json'] + base,
                         project_uuid=expected_project_uuid,
                         project_name=expected_project_name)

    def failed(call):
        return call['state'] != 'ok' or call['body'] is None

    # ---- resolve the requested project (UUID or name) ----------------------
    measured_project = _project_identity(info_start['body']) if \
        not failed(info_start) else {}
    project_uuid = expected_project_uuid
    project_name_resolved = expected_project_name
    if measured_project:
        if expected_project_uuid:
            if measured_project['uuid'] and \
                    measured_project['uuid'] != expected_project_uuid:
                raise schemas.FeedbackError(
                    schemas.FAILURE_TARGET_MISMATCH,
                    'project info reports project %r, expected %r'
                    % (measured_project['uuid'], expected_project_uuid),
                    where='project-info',
                    expected_project=expected_project_uuid,
                    observed_project=measured_project['uuid'])
            project_uuid = measured_project['uuid'] or expected_project_uuid
            project_name_resolved = measured_project['name'] or \
                expected_project_name
        else:
            uuid_alias = bool(
                measured_project['uuid'] and
                _norm(measured_project['uuid']) ==
                _norm(expected_project_name))
            if measured_project['name'] and not uuid_alias and \
                    _norm(measured_project['name']) != \
                    _norm(expected_project_name):
                raise schemas.FeedbackError(
                    schemas.FAILURE_TARGET_MISMATCH,
                    'project info reports project %r, expected name %r'
                    % (measured_project['name'], expected_project_name),
                    where='project-info',
                    expected_project=expected_project_name,
                    observed_project_name=measured_project['name'])
            project_uuid = measured_project['uuid'] or None
            project_name_resolved = measured_project['name'] or \
                expected_project_name
    host_project = {
        'uuid': project_uuid or measured_project.get('uuid'),
        'name': project_name_resolved or measured_project.get('name'),
    }
    if not host_project['uuid']:
        host_project['uuid'] = _text(project)
        unknown.append(_unknown_entry(
            'project.uuid',
            'project UUID was not measured; the routed value is recorded'))
    if not host_project['name']:
        host_project['name'] = _text(project_name) or _text(project)
        unknown.append(_unknown_entry(
            'project.name',
            'project friendly name was not measured'))

    # ---- resolve documents (UUID or name) ----------------------------------
    listed = _document_list(docs_start['body']) if not failed(docs_start) \
        else None
    by_uuid = {item['uuid']: item for item in listed or []}

    def resolve_document(label, value, expected_type):
        value = _text(value)
        if listed is None:
            if _looks_like_uuid(value):
                return {'uuid': value, 'name': None, 'strict': True}
            return {'uuid': value, 'name': value, 'strict': False}
        if value in by_uuid:
            item = by_uuid[value]
        elif _looks_like_uuid(value):
            item = None
        else:
            matches = [item for item in listed
                       if _norm(item.get('name')) == _norm(value)]
            if len(matches) != 1:
                raise schemas.FeedbackError(
                    schemas.FAILURE_TARGET_MISMATCH,
                    'document name %r resolves to %d documents (%s)'
                    % (value, len(matches), label),
                    where='doc-list', expected_document=value,
                    matches=matches, documents=listed)
            item = matches[0]
        if item is None:
            raise schemas.FeedbackError(
                schemas.FAILURE_TARGET_MISMATCH,
                'document list does not contain %s %r' % (label, value),
                where='doc-list', expected_document=value,
                documents=listed)
        if item.get('type') and item['type'] != expected_type:
            raise schemas.FeedbackError(
                schemas.FAILURE_TARGET_MISMATCH,
                'document %r has type %r, expected %r'
                % (item['uuid'], item['type'], expected_type),
                where='doc-list', expected_document=item['uuid'],
                expected_type=expected_type, observed_type=item['type'])
        return {'uuid': item['uuid'], 'name': item.get('name') or None,
                'strict': True}

    sch_target = resolve_document('sch_doc', sch_doc, 'schematic')
    pcb_target = resolve_document('pcb_doc', pcb_doc, 'pcb')
    sch_ref = sch_target['uuid'] or _text(sch_doc)
    pcb_ref = pcb_target['uuid'] or _text(pcb_doc)
    if not sch_target['strict']:
        degradations.append({
            'source': 'sch-doc', 'reason': 'document_name_unresolved',
            'document': _text(sch_doc), 'ok': True, 'exit': None})
        unknown.append(_unknown_entry(
            'documents.schematic',
            'document name was not resolved to a UUID; identity is '
            'unverifiable'))
    if not pcb_target['strict']:
        degradations.append({
            'source': 'pcb-doc', 'reason': 'document_name_unresolved',
            'document': _text(pcb_doc), 'ok': True, 'exit': None})
        unknown.append(_unknown_entry(
            'documents.pcb',
            'document name was not resolved to a UUID; identity is '
            'unverifiable'))
    target_kwargs = {'project_uuid': project_uuid,
                     'project_name': project_name_resolved}

    sch_call = execute(3, 'sch-read', ['sch', 'read'] + base +
                       _document_args(sch_ref),
                       document=sch_target['uuid'],
                       document_name=sch_target['name'], **target_kwargs)
    dump_call = execute(4, 'pcb-dump', ['pcb', 'dump', '--include-copper'] +
                        base + _document_args(pcb_ref),
                        document=pcb_target['uuid'],
                        document_name=pcb_target['name'], **target_kwargs)
    sch_drc_call = execute(5, 'sch-drc', ['sch', 'drc', '--json'] + base +
                           _document_args(sch_ref),
                           document=sch_target['uuid'],
                           document_name=sch_target['name'], **target_kwargs)
    pcb_drc_call = execute(6, 'pcb-drc', ['pcb', 'drc', '--json'] + base +
                           _document_args(pcb_ref),
                           document=pcb_target['uuid'],
                           document_name=pcb_target['name'], **target_kwargs)
    pcb_check_call = execute(7, 'pcb-check', ['pcb', 'check', '--json'] +
                             base + _document_args(pcb_ref),
                             document=pcb_target['uuid'],
                             document_name=pcb_target['name'], **target_kwargs)
    info_end = execute(8, 'project-info-out', ['project', 'info', '--json'] +
                       base, project_uuid=project_uuid,
                       project_name=project_name_resolved)
    docs_end = execute(9, 'doc-list-out', ['doc', 'ls', '--json'] + base,
                       project_uuid=project_uuid,
                       project_name=project_name_resolved)

    if not failed(info_end):
        measured_end = _project_identity(info_end['body'])
        checks = []
        if project_uuid and measured_end['uuid']:
            checks.append(measured_end['uuid'] == project_uuid)
        if project_name_resolved and measured_end['name']:
            checks.append(_norm(measured_end['name']) ==
                          _norm(project_name_resolved))
        if checks and not all(checks):
            raise schemas.FeedbackError(
                schemas.FAILURE_TARGET_MISMATCH,
                'live identity drift: project %r/%r, expected %r/%r'
                % (measured_end['uuid'], measured_end['name'], project_uuid,
                   project_name_resolved),
                where='project-info-out', expected_project=project_uuid,
                observed_project=measured_end['uuid'],
                observed_project_name=measured_end['name'])
    listed_end = _document_list(docs_end['body']) if not failed(docs_end) \
        else None
    if listed_end is not None:
        end_by_uuid = {item['uuid']: item for item in listed_end}
        for label, target in (('sch_doc', sch_target),
                              ('pcb_doc', pcb_target)):
            if target['uuid']:
                if target['uuid'] not in end_by_uuid:
                    raise schemas.FeedbackError(
                        schemas.FAILURE_TARGET_MISMATCH,
                        'live document list no longer contains %s %r'
                        % (label, target['uuid']),
                        where='doc-list-out',
                        expected_document=target['uuid'],
                        documents=listed_end)
            elif target['name']:
                matches = [item for item in listed_end
                           if _norm(item.get('name')) ==
                           _norm(target['name'])]
                if len(matches) != 1:
                    raise schemas.FeedbackError(
                        schemas.FAILURE_TARGET_MISMATCH,
                        'live document name %r resolves to %d documents'
                        % (target['name'], len(matches)),
                        where='doc-list-out',
                        expected_document=target['name'],
                        documents=listed_end)

    documents = [
        {'uuid': sch_ref, 'type': 'schematic',
         'name': sch_target['name'] or
         _text((by_uuid.get(sch_ref) or {}).get('name')) or None},
        {'uuid': pcb_ref, 'type': 'pcb',
         'name': pcb_target['name'] or
         _text((by_uuid.get(pcb_ref) or {}).get('name')) or None},
    ]
    if listed is None:
        unknown.append(_unknown_entry(
            'documents', 'document list was not measured; UUIDs came from '
                         'the caller'))

    # ---- schematic ---------------------------------------------------------
    schematic = None
    if failed(sch_call):
        unknown.append(_unknown_entry(
            'schematic', 'sch read failed: %s' % (sch_call['reason'],)))
    else:
        schematic = normalize_sch_read(sch_call['record']['payload'])
        schematic['document_uuid'] = sch_ref
        schematic['document_type'] = 'schematic'
        unknown.extend(schematic.get('unknown') or [])
    if failed(sch_drc_call) or _normalize_sch_drc(sch_drc_call['body']) is None:
        if schematic is not None:
            schematic['drc'] = None
        unknown.append(_unknown_entry(
            'schematic.drc', sch_drc_call['reason'] or
            'sch drc returned no measured report'))
    else:
        report = _normalize_sch_drc(sch_drc_call['body'])
        if not report.get('measured'):
            if schematic is not None:
                schematic['drc'] = None
            unknown.append(_unknown_entry(
                'schematic.drc', 'sch drc report carries no measured verdict'))
        else:
            report['context_verified'] = bool(
                sch_drc_call['identity'].get('context_echoed'))
            report['identity_verified'] = (
                sch_drc_call['identity'].get('verified') is True)
            if schematic is not None:
                schematic['drc'] = report

    text_call = execute(10, 'sch-text-list', ['sch', 'text-list'] + base +
                        _document_args(sch_ref),
                        document=sch_target['uuid'],
                        document_name=sch_target['name'], **target_kwargs)
    if schematic is not None:
        if failed(text_call):
            schematic['texts'] = None
            unknown.append(_unknown_entry(
                'schematic.texts', text_call['reason'] or
                'sch text-list failed'))
        else:
            normalized_texts = normalize_text_list(
                text_call['record']['payload'])
            schematic['texts'] = normalized_texts.get('texts')
            schematic['text_count'] = normalized_texts.get('count')
            unknown.extend(normalized_texts.get('unknown') or [])

    # ---- PCB ---------------------------------------------------------------
    pcb = None
    if failed(dump_call):
        unknown.append(_unknown_entry(
            'pcb', 'pcb dump failed: %s' % (dump_call['reason'],)))
    else:
        pcb = normalize_pcb_dump(dump_call['record']['payload'])
        pcb['document_uuid'] = pcb_ref
        pcb['document_type'] = 'pcb'
        if project_uuid and pcb.get('project_uuid') and \
                pcb['project_uuid'] != project_uuid:
            raise schemas.FeedbackError(
                schemas.FAILURE_TARGET_MISMATCH,
                'pcb dump capture reports project %r, expected %r'
                % (pcb['project_uuid'], project_uuid),
                where='pcb-dump', expected_project=project_uuid,
                observed_project=pcb['project_uuid'])
        _drop_unknown(pcb, ('pcb.drc', 'pcb.check'))
        unknown.extend(pcb.get('unknown') or [])
        capture_verified = bool(
            dump_call['identity'].get('verified') is True and
            (not pcb_ref or pcb.get('document_uuid') == pcb_ref))
        pcb['capture_identity_verified'] = capture_verified
        if not capture_verified:
            unknown.append(_unknown_entry(
                'pcb.capture.identityVerified',
                'pcb dump capture identity was not verified'))
            degradations.append({
                'source': 'pcb-dump',
                'reason': 'capture_identity_not_verified',
                'argv': dump_call['record'].get('argv') or [],
                'exit': dump_call['record'].get('exit'),
                'ok': True,
            })

    drc_report = None
    if not failed(pcb_drc_call):
        try:
            drc_report = pcb_evidence.parse_drc(pcb_drc_call['body'])
        except (TypeError, ValueError) as exc:
            drc_report = None
            degradations.append({
                'source': 'pcb-drc', 'reason': 'unparsable_drc: %s' % exc,
                'argv': pcb_drc_call['record'].get('argv') or [],
                'exit': pcb_drc_call['record'].get('exit'), 'ok': True,
            })
    if drc_report is None or not drc_report.get('measured'):
        if pcb is not None:
            pcb['drc'] = None
        unknown.append(_unknown_entry(
            'pcb.drc', (pcb_drc_call['reason'] or
                        'pcb drc report carries no measurement')))
    else:
        drc_report['context_verified'] = bool(
            pcb_drc_call['identity'].get('context_echoed'))
        drc_report['identity_verified'] = (
            pcb_drc_call['identity'].get('verified') is True)
        if pcb is not None:
            pcb['drc'] = drc_report

    check_report = None
    if not failed(pcb_check_call):
        try:
            check_report = pcb_evidence.parse_pcb_check(pcb_check_call['body'])
        except (TypeError, ValueError) as exc:
            check_report = None
            degradations.append({
                'source': 'pcb-check', 'reason': 'unparsable_check: %s' % exc,
                'argv': pcb_check_call['record'].get('argv') or [],
                'exit': pcb_check_call['record'].get('exit'), 'ok': True,
            })
    if check_report is None or not check_report.get('measured'):
        if pcb is not None:
            pcb['check'] = None
        unknown.append(_unknown_entry(
            'pcb.check', (pcb_check_call['reason'] or
                          'pcb check report carries no measurement')))
    else:
        check_report['context_verified'] = bool(
            pcb_check_call['identity'].get('context_echoed'))
        check_report['identity_verified'] = (
            pcb_check_call['identity'].get('verified') is True)
        if pcb is not None:
            pcb['check'] = check_report

    # ---- observation -------------------------------------------------------
    observation = schemas.new_observation(
        host={'window_id': _text(window),
              'zhigou': zhigou,
              'project_name': host_project['name'],
              'captured_at': pcb_cli.utc_now()},
        adapter={'name': 'zhigou-cli', 'interface': 'cli',
                 'commands': commands},
        project=host_project,
        documents=documents,
        units=dict(schemas.UNIT_DEFAULTS),
        schematic=schematic,
        pcb=pcb,
        evidence=evidence,
        degradations=degradations,
        unknown=unknown,
    )
    per_document = {}
    if schematic is not None:
        per_document[sch_ref] = schemas.stable_hash(
            _semantic_clean(schematic))
    if pcb is not None:
        per_document[pcb_ref] = schemas.stable_hash(
            _semantic_clean(pcb))
    revision = {
        'semantic_sha256': None,
        'per_document': per_document,
        'captured_at': pcb_cli.utc_now(),
    }
    observation['revision'] = revision
    observation['simulated'] = bool(simulation['simulated'])
    if per_document:
        revision['semantic_sha256'] = observation_semantic_hash(observation)
    else:
        observation['unknown'].append(_unknown_entry(
            'revision.semantic_sha256',
            'no schematic or PCB section was measured'))
    return schemas.validate_observation(observation)


# ---------------------------------------------------------------------------
# semantic hash / baseline comparison
# ---------------------------------------------------------------------------

def _semantic_clean(value):
    if isinstance(value, dict):
        return {key: _semantic_clean(item) for key, item in value.items()
                if key not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_semantic_clean(item) for item in value]
    return value


def _semantic_view(value):
    if not isinstance(value, dict):
        return _semantic_clean(value)
    content = {
        'schema': value.get('schema'),
        'tool_version': value.get('tool_version'),
        'project': _semantic_clean(value.get('project')),
        'documents': _semantic_clean(value.get('documents')),
        'units': _semantic_clean(value.get('units')),
        'schematic': _semantic_clean(value.get('schematic')),
        'pcb': _semantic_clean(value.get('pcb')),
        'unknown': _semantic_clean(value.get('unknown')),
    }
    degradations = []
    for entry in value.get('degradations') or []:
        if isinstance(entry, dict):
            degradations.append({
                'source': entry.get('source'),
                'reason': entry.get('reason'),
                'exit': entry.get('exit'),
            })
    content['degradations'] = degradations
    return content


def observation_semantic_hash(observation):
    """Hash the semantic design content, ignoring capture timestamps/paths.

    Evidence paths, command argv, adapter command logs and revision hashes are
    excluded so two captures of the same design compare equal across sessions
    and machines.
    """
    return schemas.stable_hash(_semantic_view(observation))


def _revision_hash(observation, document_uuid=None):
    revision = observation.get('revision') if isinstance(observation, dict) \
        else None
    if not isinstance(revision, dict):
        return None
    if document_uuid is None:
        return revision.get('semantic_sha256')
    per_document = revision.get('per_document')
    if not isinstance(per_document, dict):
        return None
    return per_document.get(document_uuid)


def compare_baseline(observation, baseline):
    """Compare a live observation with a stored baseline.

    ``match`` requires identical measured semantic hashes; a changed target is
    ``target_mismatch``; an unmeasured side is ``unknown``.  Everything else is
    ``stale`` with the documents whose per-document hashes changed.
    """
    result = {
        'status': 'unknown',
        'reasons': [],
        'changed_documents': [],
        'semantic_sha256': {'current': None, 'baseline': None},
    }
    try:
        schemas.validate_observation(observation)
    except (schemas.ContractError, TypeError) as exc:
        result['reasons'].append('current_observation_invalid: %s' % exc)
        return result
    try:
        schemas.validate_observation(baseline)
    except (schemas.ContractError, TypeError) as exc:
        result['reasons'].append('baseline_invalid: %s' % exc)
        return result

    current = observation
    current_sem = _revision_hash(current)
    baseline_sem = _revision_hash(baseline)
    result['semantic_sha256'] = {'current': current_sem,
                                 'baseline': baseline_sem}

    current_project = _text((current.get('project') or {}).get('uuid'))
    baseline_project = _text((baseline.get('project') or {}).get('uuid'))
    current_docs = {document.get('uuid'): document
                    for document in current.get('documents') or []}
    baseline_docs = {document.get('uuid'): document
                     for document in baseline.get('documents') or []}
    changed = []
    if current_project != baseline_project:
        result['status'] = 'target_mismatch'
        result['reasons'].append(
            'project_changed: %r -> %r' % (baseline_project, current_project))
        return result
    for uuid in sorted(set(baseline_docs) - set(current_docs)):
        changed.append(uuid)
        result['reasons'].append('document_removed: %s' % uuid)
    for uuid in sorted(set(current_docs) - set(baseline_docs)):
        changed.append(uuid)
        result['reasons'].append('document_added: %s' % uuid)
    for uuid in sorted(set(current_docs) & set(baseline_docs)):
        if current_docs[uuid].get('type') != \
                baseline_docs[uuid].get('type'):
            changed.append(uuid)
            result['reasons'].append(
                'document_type_changed: %s' % uuid)
    if changed:
        result['status'] = 'target_mismatch'
        result['changed_documents'] = sorted(set(changed))
        return result

    if current_sem is None or baseline_sem is None:
        result['status'] = 'unknown'
        if current_sem is None:
            result['reasons'].append('current_not_measured')
        if baseline_sem is None:
            result['reasons'].append('baseline_not_measured')
        return result

    if current_sem == baseline_sem:
        result['status'] = 'match'
        return result

    result['status'] = 'stale'
    result['reasons'].append('semantic_hash_changed')
    for uuid in sorted(set(current_docs) & set(baseline_docs)):
        current_doc_hash = _revision_hash(current, uuid)
        baseline_doc_hash = _revision_hash(baseline, uuid)
        if current_doc_hash != baseline_doc_hash:
            changed.append(uuid)
            result['reasons'].append('document_changed: %s' % uuid)
    result['changed_documents'] = sorted(set(changed))
    return result


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------

def cache_key(window, project, sch_doc, pcb_doc):
    """Build the cache key for one observation request.

    The key always names window/project/document/type/command/args so a cache
    entry can never be reused for another target.
    """
    return {
        'window': _text(window) or None,
        'project': _text(project) or None,
        'document': _text(pcb_doc) or _text(sch_doc) or None,
        'type': 'observation',
        'command': 'collect_observation',
        'args': {'sch_doc': _text(sch_doc) or None,
                 'pcb_doc': _text(pcb_doc) or None},
        'documents': {'schematic': _text(sch_doc) or None,
                      'pcb': _text(pcb_doc) or None},
    }


def _normalized_key(key):
    if not isinstance(key, dict):
        raise ValueError('cache key must be an object')
    normalized = {field: key.get(field) for field in
                  ('window', 'project', 'document', 'type', 'command', 'args')}
    if isinstance(key.get('documents'), dict):
        normalized['documents'] = dict(key['documents'])
    if key.get('revision') is not None:
        normalized['revision'] = key['revision']
    return normalized


def _value_identity(value):
    identity = {'project': None, 'document': None, 'documents': {}}
    if not isinstance(value, dict):
        return identity
    project = value.get('project')
    if isinstance(project, dict):
        identity['project'] = _text(_first(project, 'uuid', 'projectUuid')) \
            or None
    for document in value.get('documents') or []:
        if isinstance(document, dict) and _text(document.get('uuid')):
            kind = _document_type(document.get('type'))
            if kind in ('schematic', 'pcb'):
                identity['documents'][kind] = _text(document['uuid'])
    identity['document'] = _text(_first(value, 'document_uuid',
                                        'documentUuid')) or None
    capture = value.get('capture') if isinstance(value.get('capture'),
                                                  dict) else {}
    identity['project'] = identity['project'] or _text(
        _first(capture, 'projectUuid', 'project_uuid')) or None
    identity['document'] = identity['document'] or _text(
        _first(capture, 'documentUuid', 'document_uuid')) or None
    return identity


def _value_revision(value):
    if not isinstance(value, dict):
        return None
    revision = value.get('revision')
    if isinstance(revision, dict) and _text(revision.get('semantic_sha256')):
        return _text(revision['semantic_sha256'])
    for key in ('semantic_sha256', 'semanticSha256'):
        if _text(value.get(key)):
            return _text(value[key])
    return _text(_first(value, 'capturedAt', 'captured_at')) or None


class ObservationCache:
    """Versioned, identity-checked cache for observations and read payloads.

    A cache hit is returned only when the stored key matches exactly and the
    value's project/document identity still matches the requested target.  A
    key that carries a ``revision`` misses when the stored revision differs.
    Corrupt files are reported in ``problems`` and treated as an empty cache.
    """

    def __init__(self, path):
        self.path = os.path.abspath(os.fspath(path))
        self.entries = {}
        self.problems = []
        self.load()

    def load(self):
        self.entries = {}
        self.problems = []
        if not os.path.isfile(self.path):
            return self
        try:
            data = pcb_cli.load_json(self.path)
        except (OSError, ValueError) as exc:
            self.problems.append('unreadable_cache: %s' % exc)
            return self
        if not isinstance(data, dict) or data.get('schema') != CACHE_SCHEMA:
            self.problems.append('unknown_cache_schema')
            return self
        entries = data.get('entries')
        if not isinstance(entries, list):
            self.problems.append('entries_not_a_list')
            return self
        for entry in entries:
            if not isinstance(entry, dict) or not _text(
                    entry.get('key_hash')):
                self.problems.append('invalid_entry')
                continue
            self.entries[_text(entry['key_hash'])] = entry
        return self

    def _digest(self, key):
        return schemas.stable_hash(_normalized_key(key))

    def get(self, key):
        normalized = _normalized_key(key)
        digest = self._digest(normalized)
        entry = self.entries.get(digest)
        if not isinstance(entry, dict):
            return None
        if entry.get('key') != normalized:
            self.entries.pop(digest, None)
            return None
        requested_revision = normalized.get('revision')
        if requested_revision is not None and \
                entry.get('revision') != requested_revision:
            self.entries.pop(digest, None)
            return None
        value = entry.get('value')
        stored = entry.get('identity') if isinstance(entry.get('identity'),
                                                     dict) else {}
        live = _value_identity(value)
        expected_project = _text(normalized.get('project'))
        expected_document = _text(normalized.get('document'))
        for actual in (stored.get('project'), live.get('project')):
            if expected_project and actual and actual != expected_project:
                self.entries.pop(digest, None)
                return None
        for actual in (stored.get('document'), live.get('document')):
            if expected_document and actual and actual != expected_document:
                self.entries.pop(digest, None)
                return None
        requested_documents = normalized.get('documents') or {}
        stored_documents = stored.get('documents') if isinstance(
            stored.get('documents'), dict) else {}
        for kind, uuid in requested_documents.items():
            if not _text(uuid):
                continue
            actual = stored_documents.get(kind) or \
                live.get('documents', {}).get(kind)
            if actual and actual != _text(uuid):
                self.entries.pop(digest, None)
                return None
        return value

    def put(self, key, value):
        normalized = _normalized_key(key)
        identity = _value_identity(value)
        expected_project = _text(normalized.get('project'))
        expected_document = _text(normalized.get('document'))
        if expected_project and identity.get('project') and \
                identity['project'] != expected_project:
            raise ValueError('cache value project %r does not match key %r'
                             % (identity['project'], expected_project))
        if expected_document and identity.get('document') and \
                identity['document'] != expected_document:
            raise ValueError('cache value document %r does not match key %r'
                             % (identity['document'], expected_document))
        requested_documents = normalized.get('documents') or {}
        for kind, uuid in requested_documents.items():
            actual = (identity.get('documents') or {}).get(kind)
            if _text(uuid) and actual and actual != _text(uuid):
                raise ValueError(
                    'cache value %s document %r does not match key %r'
                    % (kind, actual, uuid))
        identity = dict(identity)
        identity['project'] = identity.get('project') or expected_project \
            or None
        identity['document'] = identity.get('document') or expected_document \
            or None
        digest = self._digest(normalized)
        self.entries[digest] = {
            'key': normalized,
            'key_hash': digest,
            'revision': normalized.get('revision')
            if normalized.get('revision') is not None
            else _value_revision(value),
            'identity': identity,
            'stored_at': pcb_cli.utc_now(),
            'value': value,
        }
        return digest

    def invalidate(self, prefix=None):
        if prefix is None:
            removed = len(self.entries)
            self.entries = {}
            return removed
        if isinstance(prefix, str):
            target = _text(prefix)
            removed = 0
            for digest, entry in list(self.entries.items()):
                normalized = entry.get('key') or {}
                fields = [normalized.get('window'), normalized.get('project'),
                          normalized.get('document'), normalized.get('type'),
                          normalized.get('command')]
                if digest.startswith(target) or any(
                        _text(field).startswith(target) for field in fields):
                    self.entries.pop(digest, None)
                    removed += 1
            return removed
        if isinstance(prefix, dict):
            removed = 0
            for digest, entry in list(self.entries.items()):
                normalized = entry.get('key') or {}
                if all(normalized.get(key) == value
                       for key, value in prefix.items()):
                    self.entries.pop(digest, None)
                    removed += 1
            return removed
        raise ValueError('cache prefix must be a dict, string or None')

    def save(self):
        data = {
            'schema': CACHE_SCHEMA,
            'saved_at': pcb_cli.utc_now(),
            'entries': [self.entries[digest]
                        for digest in sorted(self.entries)],
        }
        pcb_cli.write_json(self.path, data)
        return {'path': self.path, 'entries': len(self.entries)}

    def clear(self):
        self.entries = {}
