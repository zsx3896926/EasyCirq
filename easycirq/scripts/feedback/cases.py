"""Case library, retrieval and reuse guards.

A case records one real design episode: what it applies to, what was tried,
what was actually executed and which limits remain.  This module keeps three
promises:

* a case is only accepted when every required field is present and every
  ``pass`` has evidence behind it;
* retrieval applies hard filters first (a case that does not cover the target
  is *rejected with a reason*, never silently returned);
* old ``pass`` conclusions are never inherited.  ``reuse_check`` lists the
  differences and the rechecks they force.

Searchable attributes live under ``case['applies_when']``::

    applies_when = {
        'power_w': {'min': 0.1, 'max': 1.0},
        'interfaces': ['i2c', 'usb'],
        'topologies': ['ldo'],
        'footprints': ['SOT-23', '0805'],
        'layers': 2,
        'process': 'jlcpcb-2layer-1.6mm',
        'tags': ['led', '5v'],
        'device': {'name': 'LM393', 'version': 'DIP-8'},
    }

Interfaces, topologies, footprints, layers and tags are hard *coverage*
filters: the case must declare every requested value.  Power is a hard range
filter: the query range must intersect the case range.  A filter whose value
cannot be parsed is ``invalid_input``, not an empty match.

The index is deliberately small::

    {'schema': 'hds-case-index/v1',
     'cases': [{'id', 'version', 'path', 'source_tier', 'tags', 'summary'}]}

``summary`` keeps the filterable attributes only (plus verification statuses,
never evidence).  Case files are read only when the summary cannot answer a
requested filter; such reads must stay inside the index/library directory or
the repository.

Paths in an index are relative to the index file (or the library directory)
when possible.  ``load_index(path)`` records that directory as ``base_dir`` so
case files can be resolved later without guessing.
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

try:  # package import (feedback_loop.py) and flat import (tests) both work
    from . import schemas
except ImportError:  # pragma: no cover - flat import by offline tools
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import schemas

SOURCE_TIERS = ('project-local', 'reusable', 'candidate-rule')

ALLOWED_FILTERS = (
    'power_min_w', 'power_max_w', 'interfaces', 'topologies', 'footprints',
    'layers', 'process', 'verification_level_min', 'tags', 'source_tier',
    'text',
)
TEXT_ALIASES = ('q', 'query', 'keywords')

REUSE_DIMENSIONS = (
    'power', 'interfaces', 'topology', 'footprint', 'layers', 'process',
    'device', 'version',
)

_SEARCH_TEXT_KEYS = ('text', 'goal', 'original_problem', 'method')
_SEARCH_LIST_KEYS = ('interfaces', 'topologies', 'footprints', 'tags')
_VIEW_KEYS = (
    'power_w', 'interfaces', 'topologies', 'footprints', 'layers',
    'process', 'device', 'verification_levels', 'tags', 'text', 'goal',
    'original_problem', 'method', 'source_tier',
)
_VIEW_ALIASES = {
    'power': 'power_w',
    'interface': 'interfaces',
    'topology': 'topologies',
    'footprint': 'footprints',
    'layer': 'layers',
}

_TOKEN_RE = re.compile(r'[a-z0-9]+|[一-鿿]')
_MEASUREMENT_WORDS = re.compile(
    r'(measur|read|dmm|multimeter|meter|scope|probe|实测|测量|读数)',
    re.IGNORECASE)
_DIGIT_RE = re.compile(r'\d')

_MEASUREMENT_KEYS = (
    'measurement', 'measured', 'reading', 'measured_value', 'value',
)


# ---------------------------------------------------------------------------
# case template and validation
# ---------------------------------------------------------------------------

def case_template():
    """Return a complete ``hds-case/v1`` skeleton.

    Every required field is present with a structurally valid placeholder, so
    a caller fills values instead of inventing the contract.  All six
    verification levels start as ``not_run`` with empty evidence; a case that
    claims ``pass`` must add evidence explicitly.
    """
    levels = {
        level: {'status': schemas.STATUS_NOT_RUN, 'evidence': []}
        for level in schemas.VERIFICATION_LEVELS
    }
    return schemas.new_case(
        id='case-id',
        version=1,
        goal='',
        applies_when={
            'power_w': {'min': None, 'max': None},
            'interfaces': [],
            'topologies': [],
            'footprints': [],
            'layers': [],
            'process': '',
            'tags': [],
            'device': {},
        },
        does_not_apply_when=[],
        inputs=[],
        provenance={
            'source_project': '',
            'source_case': '',
            'artifacts': [],
            'verified_at': '',
            'stale': False,
        },
        tool_versions={},
        original_problem='',
        method='',
        before_after={'before': '', 'after': '', 'changes': []},
        check_method=[],
        evidence=[],
        verification_levels=levels,
        limits=[],
        failed_attempts=[],
        invalidation_conditions=[],
        source_tier='project-local',
    )


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _string_value(value):
    """Return the stripped string, or ``''`` when the value is not one."""
    return value.strip() if isinstance(value, str) and value.strip() else ''


def _measurement_note(evidence):
    """True when a physical pass carries a real measurement, not a file name.

    A measurement is a dict with a non-empty measurement/reading/value field,
    or a note/string that contains a number *and* a measurement word.  A bare
    path such as ``evidence/pcb-final-top.png`` does not qualify.
    """
    for item in evidence or []:
        if isinstance(item, dict):
            for key in _MEASUREMENT_KEYS:
                value = item.get(key)
                if _is_number(value):
                    return True
                if _text(value):
                    return True
            note = item.get('note')
            if _text(note) and _DIGIT_RE.search(note) and \
                    _MEASUREMENT_WORDS.search(note):
                return True
            if item.get('kind') == 'measurement' and (
                    _text(item.get('note')) or _is_number(item.get('value'))):
                return True
        elif _text(item) and _DIGIT_RE.search(item) and \
                _MEASUREMENT_WORDS.search(item):
            return True
    return False


def _validated_names(value):
    names = []
    for entry in value:
        if isinstance(entry, dict):
            entry = entry.get('id')
        if not _text(entry):
            return []
        names.append(entry.strip())
    return names


def validate_case(case):
    """Validate a case against the frozen schema plus the reuse guards.

    Delegates to :func:`schemas.validate_case` and then tightens the rules a
    case must satisfy before it may enter a library:

    * ``verification_levels`` may only use the six contract level names;
    * every level entry must carry a list ``evidence`` field;
    * a ``physical`` pass needs a real measurement note;
    * a ``candidate-rule`` must name the cases that validated it.
    """
    schemas.validate_case(case)

    if not _text(case.get('id')):
        raise schemas.ContractError('case.id must be a non-empty string')
    version = case.get('version')
    if isinstance(version, bool):
        raise schemas.ContractError('case.version must be an integer or text')
    if isinstance(version, int):
        if version < 1:
            raise schemas.ContractError('case.version must be >= 1')
    elif isinstance(version, float) and version.is_integer():
        if version < 1:
            raise schemas.ContractError('case.version must be >= 1')
    elif not _text(version):
        raise schemas.ContractError('case.version must be an integer or text')
    if not isinstance(case.get('evidence'), list):
        raise schemas.ContractError('case.evidence must be a list')

    levels = case['verification_levels']
    for level, entry in levels.items():
        if level not in schemas.VERIFICATION_LEVELS:
            raise schemas.ContractError(
                'case.verification_levels.%s is not a contract level' % level)
        if not isinstance(entry.get('evidence'), list):
            raise schemas.ContractError(
                'case.verification_levels.%s.evidence must be a list' % level)
        if level == schemas.VERIFICATION_PHYSICAL and \
                entry.get('status') == schemas.STATUS_PASS:
            if not _measurement_note(entry['evidence']) and \
                    not _measurement_note(case.get('evidence')):
                raise schemas.ContractError(
                    'case.verification_levels.physical: a pass needs a real '
                    'measurement note')

    if case['source_tier'] == 'candidate-rule':
        validated_by = case.get('validated_by')
        if not isinstance(validated_by, list) or not _validated_names(
                validated_by):
            raise schemas.ContractError(
                'case.validated_by must name the cases that validated a '
                'candidate-rule')
    return case


# ---------------------------------------------------------------------------
# small normalisers shared by search and reuse
# ---------------------------------------------------------------------------

def _invalid(message, **detail):
    raise schemas.FeedbackError(schemas.FAILURE_INVALID_INPUT, message,
                                **detail)


def _refuse(message, **detail):
    raise schemas.FeedbackError(schemas.FAILURE_PRECONDITION_REFUSED, message,
                                **detail)


def _repo_root():
    # <repo>/easycirq/scripts/feedback/cases.py
    return Path(__file__).resolve().parents[3]


def _norm_name(value):
    text = str(value).strip().lower()
    for old, new in (('²', '2'), ('µ', 'u'), ('μ', 'u'),
                     ('_', '-'), (' ', '-')):
        text = text.replace(old, new)
    while '--' in text:
        text = text.replace('--', '-')
    return text


def _names(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return set()
    return {_norm_name(item) for item in value
            if isinstance(item, str) and item.strip()}


def _parse_number(value, name):
    if isinstance(value, bool) or value is None:
        _invalid('%s must be a number' % name)
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            _invalid('%s is not a number: %r' % (name, value))
    else:
        _invalid('%s must be a number' % name)
    if not math.isfinite(number) or number < 0:
        _invalid('%s must be a finite non-negative number' % name)
    return number


def _parse_int(value, name):
    if isinstance(value, bool):
        _invalid('%s must be an integer' % name)
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str):
        try:
            number = int(value.strip(), 10)
        except ValueError:
            _invalid('%s is not an integer: %r' % (name, value))
    else:
        _invalid('%s must be an integer' % name)
    if number < 1:
        _invalid('%s must be >= 1' % name)
    return number


def _parse_name_list(value, name):
    if isinstance(value, str):
        items = value.split(',')
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        _invalid('%s must be a list or a comma-separated string' % name)
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, str) or not item.strip():
            _invalid('%s must contain non-empty strings' % name)
        token = item.strip()
        key = _norm_name(token)
        if key not in seen:
            seen.add(key)
            result.append(token)
    return result


def _parse_layers(value, name):
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    result = []
    for item in items:
        number = _parse_int(item, name)
        if number not in result:
            result.append(number)
    return result


def _parse_level(value):
    if isinstance(value, bool):
        _invalid('verification_level_min must be a level name or index')
    if isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value < len(schemas.VERIFICATION_LEVELS):
            return schemas.VERIFICATION_LEVELS[value]
        _invalid('verification_level_min index out of range: %r' % (value,))
    if isinstance(value, float) and value.is_integer():
        return _parse_level(int(value))
    if isinstance(value, str):
        token = value.strip().lower().replace('-', '_').replace(' ', '_')
        if token in schemas.VERIFICATION_LEVELS:
            return token
    _invalid('verification_level_min is not a known level: %r' % (value,))


def _normalize_filters(query):
    if not isinstance(query, dict):
        _invalid('query must be an object')
    if 'filters' in query:
        raw = query['filters']
        if not isinstance(raw, dict):
            _invalid('query.filters must be an object')
        raw = dict(raw)
    else:
        raw = {key: value for key, value in query.items()
               if key != 'schema'}
    unknown = sorted(set(raw) - set(ALLOWED_FILTERS) - set(TEXT_ALIASES))
    if unknown:
        _invalid('unknown filter(s): %s' % ', '.join(unknown),
                 filters=unknown)

    filters = {}
    if 'power_min_w' in raw:
        filters['power_min_w'] = _parse_number(raw['power_min_w'],
                                               'power_min_w')
    if 'power_max_w' in raw:
        filters['power_max_w'] = _parse_number(raw['power_max_w'],
                                               'power_max_w')
    if 'power_min_w' in filters and 'power_max_w' in filters and \
            filters['power_min_w'] > filters['power_max_w']:
        _invalid('power_min_w must not exceed power_max_w')
    for key in ('interfaces', 'topologies', 'footprints'):
        if key in raw:
            parsed = _parse_name_list(raw[key], key)
            if parsed:
                filters[key] = parsed
    if 'layers' in raw:
        parsed = _parse_layers(raw['layers'], 'layers')
        if parsed:
            filters['layers'] = parsed
    if 'tags' in raw:
        parsed = _parse_name_list(raw['tags'], 'tags')
        if parsed:
            filters['tags'] = parsed
    if 'process' in raw:
        if not _text(raw['process']):
            _invalid('process must be a non-empty string')
        filters['process'] = raw['process'].strip()
    if 'verification_level_min' in raw:
        filters['verification_level_min'] = _parse_level(
            raw['verification_level_min'])
    if 'source_tier' in raw:
        tier = raw['source_tier']
        if not _text(tier) or tier.strip().lower() not in SOURCE_TIERS:
            _invalid('source_tier must be one of %s' % (SOURCE_TIERS,))
        filters['source_tier'] = tier.strip().lower()

    texts = []
    for key in ('text',) + TEXT_ALIASES:
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            _invalid('%s must be a string' % key)
        if value.strip():
            texts.append(value.strip())
    if texts:
        filters['text'] = ' '.join(texts)
    return filters


# ---------------------------------------------------------------------------
# index helpers
# ---------------------------------------------------------------------------

def _string_list(value):
    if isinstance(value, str):
        return [part.strip() for part in value.split(',') if part.strip()]
    if isinstance(value, (list, tuple)):
        return [item.strip() for item in value
                if isinstance(item, str) and item.strip()]
    return []


def _applies(case):
    applies = case.get('applies_when')
    return applies if isinstance(applies, dict) else {}


def _case_tags(case):
    applies = _applies(case)
    tags = applies.get('tags')
    if not isinstance(tags, (list, str)):
        tags = case.get('tags')
    return _string_list(tags)


def _first(mapping, source, *keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, '', [], {}):
            return value
    for key in keys:
        value = source.get(key)
        if value not in (None, '', [], {}):
            return value
    return None


def _case_summary(case):
    applies = _applies(case)
    levels = {}
    for level, entry in (case.get('verification_levels') or {}).items():
        if isinstance(entry, dict):
            levels[level] = entry.get('status')
    text_parts = [case.get('goal'), case.get('original_problem'),
                  case.get('method')]
    for key in ('interfaces', 'topologies', 'footprints', 'tags'):
        text_parts.extend(_string_list(_first(applies, case, key)))
    process = _first(applies, case, 'process')
    if isinstance(process, str):
        text_parts.append(process)
    device = _first(applies, case, 'device')
    if isinstance(device, dict):
        text_parts.extend(str(device.get(key) or '')
                          for key in ('name', 'version'))
    elif isinstance(device, str):
        text_parts.append(device)
    provenance = case.get('provenance')
    provenance = provenance if isinstance(provenance, dict) else {}
    return {
        'goal': case.get('goal') or '',
        'power_w': _first(applies, case, 'power_w', 'power'),
        'interfaces': _string_list(_first(applies, case, 'interfaces',
                                          'interface')),
        'topologies': _string_list(_first(applies, case, 'topologies',
                                          'topology')),
        'footprints': _string_list(_first(applies, case, 'footprints',
                                          'footprint')),
        'layers': _first(applies, case, 'layers', 'layer'),
        'process': process,
        'device': device,
        'verification_levels': levels,
        # Provenance without evidence: the summary must be able to say which
        # project a case came from so several scenarios of one project are not
        # mistaken for independent evidence.
        'provenance': {
            'source_project': _string_value(provenance.get('source_project')),
            'source_case': _string_value(provenance.get('source_case')),
        },
        'text': ' '.join(part for part in text_parts
                         if isinstance(part, str) and part.strip()),
    }


def _relative_posix(value, base):
    if value is None or (isinstance(value, str) and not value.strip()):
        return ''
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path(base).resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _entry_from_case(case, base_dir, source_path=None):
    validate_case(case)
    if source_path is not None:
        path = Path(source_path)
    elif _text(case.get('path')):
        path = Path(case['path'])
    else:
        path = None
    return {
        'id': case['id'],
        'version': case['version'],
        'path': _relative_posix(path, base_dir) if path else '',
        'source_tier': case['source_tier'],
        'tags': _case_tags(case),
        'summary': _case_summary(case),
    }


def _entry_key(entry):
    return (str(entry.get('id')), str(entry.get('version')))


def _check_index(index):
    if not isinstance(index, dict):
        raise schemas.ContractError('index must be an object')
    if index.get('schema') != schemas.SCHEMA_CASE_INDEX:
        raise schemas.ContractError(
            'index.schema must be %s' % schemas.SCHEMA_CASE_INDEX)
    cases = index.get('cases')
    if not isinstance(cases, list):
        raise schemas.ContractError('index.cases must be a list')
    seen = set()
    for position, entry in enumerate(cases):
        where = 'index.cases[%d]' % position
        if not isinstance(entry, dict):
            raise schemas.ContractError('%s must be an object' % where)
        if not _text(entry.get('id')):
            raise schemas.ContractError('%s.id must be a non-empty string'
                                        % where)
        if 'version' not in entry:
            raise schemas.ContractError('%s.version is required' % where)
        key = _entry_key(entry)
        if key in seen:
            raise schemas.ContractError('%s duplicates case %s@%s'
                                        % ((where,) + key))
        seen.add(key)
        if entry.get('source_tier') not in ('', None) and \
                entry['source_tier'] not in SOURCE_TIERS:
            raise schemas.ContractError('%s.source_tier invalid' % where)
        if 'tags' in entry and not isinstance(entry['tags'], list):
            raise schemas.ContractError('%s.tags must be a list' % where)
        if 'summary' in entry and not isinstance(entry['summary'], dict):
            raise schemas.ContractError('%s.summary must be an object'
                                        % where)
        if 'path' in entry and not isinstance(entry['path'], str):
            raise schemas.ContractError('%s.path must be a string' % where)
    return index


def _index_base(index):
    base = index.get('base_dir')
    if _text(base):
        return Path(base)
    return _repo_root()


def _insert_entry(index, entry, replace):
    key = _entry_key(entry)
    for position, existing in enumerate(index['cases']):
        if _entry_key(existing) != key:
            continue
        if not replace:
            _refuse('case %s@%s is already registered' % key,
                    id=entry['id'], version=entry['version'])
        index['cases'][position] = entry
        return index
    index['cases'].append(entry)
    return index


# ---------------------------------------------------------------------------
# index creation / loading / registration
# ---------------------------------------------------------------------------

def create_index(*, library='', cases=None):
    """Create a case index from a library directory and/or explicit cases.

    ``library`` is the base directory for relative paths.  When ``cases`` is
    omitted the library is scanned for ``*.json`` files whose top-level
    ``schema`` is ``hds-case/v1``; other JSON files are ignored.  ``cases``
    may contain case objects, JSON paths, or a single one of either.  An
    invalid case fails the build instead of being skipped.  With neither
    argument an empty index is returned.
    """
    if library:
        base = Path(library)
        if not base.exists():
            _invalid('library does not exist: %s' % library)
        if not base.is_dir():
            _invalid('library is not a directory: %s' % library)
        base = base.resolve()
    else:
        base = _repo_root()

    index = {'schema': schemas.SCHEMA_CASE_INDEX, 'cases': []}
    loaded = []

    if cases is None:
        if not library:
            return index
        for path in sorted(base.rglob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and \
                    data.get('schema') == schemas.SCHEMA_CASE:
                loaded.append((data, path))
    else:
        if isinstance(cases, dict) or isinstance(cases, (str, Path)):
            cases = [cases]
        if not isinstance(cases, (list, tuple)):
            _invalid('cases must be a list')
        for item in cases:
            if isinstance(item, dict):
                loaded.append((item, None))
            elif isinstance(item, (str, Path)):
                path = Path(item)
                if not path.is_absolute():
                    path = base / path
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                except OSError as exc:
                    _invalid('cannot read case %s: %s' % (item, exc))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    _invalid('case %s is not valid JSON: %s' % (item, exc))
                loaded.append((data, path))
            else:
                _invalid('cases items must be objects or paths')

    for case, path in loaded:
        if not isinstance(case, dict):
            _invalid('a case must be an object')
        entry = _entry_from_case(case, base, path)
        _insert_entry(index, entry, replace=False)
    return index


def load_index(path_or_dict):
    """Load an index from a JSON file or a dictionary.

    A file index records its parent directory as ``base_dir`` so relative case
    paths stay resolvable.  The input dictionary is not mutated.
    """
    if isinstance(path_or_dict, dict):
        index = copy.deepcopy(path_or_dict)
        _check_index(index)
        return index
    if not isinstance(path_or_dict, (str, Path)):
        _invalid('index must be a path or an object')
    path = Path(path_or_dict)
    if not path.is_file():
        _invalid('index file does not exist: %s' % path)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _invalid('cannot read index %s: %s' % (path, exc))
    if not isinstance(data, dict):
        _invalid('index file must contain an object')
    _check_index(data)
    data['base_dir'] = str(path.resolve().parent)
    return data


def register(index, case, *, replace=False):
    """Register one case in an index.

    A duplicate ``id``+``version`` is refused unless ``replace=True``.  The
    index is updated in place and returned for convenience.
    """
    _check_index(index)
    base = _index_base(index)
    entry = _entry_from_case(case, base)
    return _insert_entry(index, entry, replace=replace)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def _merge_view(out, mapping):
    if not isinstance(mapping, dict):
        return
    for alias, canonical in _VIEW_ALIASES.items():
        if canonical in out:
            continue
        value = mapping.get(alias)
        if value not in (None, '', [], {}):
            out[canonical] = value
    for key in _VIEW_KEYS:
        if key in out:
            continue
        value = mapping.get(key)
        if value not in (None, '', [], {}):
            out[key] = value


def _view_from_case(out, case):
    _merge_view(out, case.get('applies_when') or {})
    _merge_view(out, case)


def _needed_keys(filters):
    needed = set()
    if 'power_min_w' in filters or 'power_max_w' in filters:
        needed.add('power_w')
    for key in ('interfaces', 'topologies', 'footprints', 'layers', 'process',
                'tags'):
        if key in filters:
            needed.add(key)
    if 'verification_level_min' in filters:
        needed.add('verification_levels')
    return needed


def _missing(value):
    return value in (None, '', [], {})


def _load_case_file(index, entry):
    path = entry.get('path')
    if not _text(path):
        return None, 'case has no path'
    base = _index_base(index)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None, 'case path cannot be resolved: %s' % path
    roots = [base.resolve(), _repo_root().resolve()]
    if not any(resolved == root or root in resolved.parents
               for root in roots):
        return None, 'case path escapes the library/repo: %s' % path
    try:
        data = json.loads(resolved.read_text(encoding='utf-8'))
    except OSError:
        return None, 'case file is unreadable: %s' % path
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, 'case file is not valid JSON: %s' % path
    if not isinstance(data, dict) or \
            data.get('schema') != schemas.SCHEMA_CASE:
        return None, 'file is not a case: %s' % path
    try:
        validate_case(data)
    except schemas.ContractError as exc:
        return None, 'case file is invalid: %s' % exc
    return data, None


def _entry_view(index, entry, filters):
    out = {}
    summary = entry.get('summary')
    if isinstance(summary, dict):
        _merge_view(out, summary)
    _merge_view(out, entry)
    embedded = entry.get('case')
    if isinstance(embedded, dict):
        _view_from_case(out, embedded)

    tags = entry.get('tags')
    if not isinstance(tags, list) or not tags:
        tags = out.get('tags')
    out['tags'] = [tag.strip() for tag in (tags or [])
                   if isinstance(tag, str) and tag.strip()]
    out['source_tier'] = (entry.get('source_tier') or
                          out.get('source_tier') or '')

    needed = _needed_keys(filters)
    if any(_missing(out.get(key)) for key in needed) and \
            _text(entry.get('path')):
        loaded, error = _load_case_file(index, entry)
        if loaded is not None:
            _view_from_case(out, loaded)
            if not out['tags']:
                out['tags'] = _case_tags(loaded)
            out['source_tier'] = (out['source_tier'] or
                                  loaded.get('source_tier') or '')
        else:
            out['_read_error'] = error

    out['_text'] = ' '.join(
        out[key].strip() for key in _SEARCH_TEXT_KEYS
        if _text(out.get(key)))
    return out


def _power_range(value):
    """Return ``(low, high)`` in watts; ``high=None`` means unbounded."""
    low = high = None
    if _is_number(value):
        low = high = float(value)
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        low = _optional_number(value[0])
        high = _optional_number(value[1])
    elif isinstance(value, str):
        try:
            low = high = float(value.strip())
        except ValueError:
            return None
    elif isinstance(value, dict):
        low = _optional_number(value.get('min', value.get('min_w')))
        high = _optional_number(value.get('max', value.get('max_w')))
        if value.get('value') is not None:
            low = high = _optional_number(value.get('value'))
    else:
        return None
    if low is None and high is None:
        return None
    if low is None:
        low = 0.0
    if low < 0 or (high is not None and high < low):
        return None
    return (low, high)


def _optional_number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _fmt_number(number):
    if number is None:
        return 'unbounded'
    if float(number).is_integer():
        return str(int(number))
    return str(round(number, 6))


def _fmt_range(power_range):
    low, high = power_range
    return '%s-%s W' % (_fmt_number(low), _fmt_number(high))


def _overlaps(power_range, low, high):
    case_low, case_high = power_range
    if high is not None and high < case_low:
        return False
    if case_high is not None and low > case_high:
        return False
    return True


def _contains(outer, inner):
    outer_low, outer_high = outer
    inner_low, inner_high = inner
    if inner_low < outer_low:
        return False
    if outer_high is not None:
        if inner_high is None or inner_high > outer_high:
            return False
    return True


def _int_values(value):
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, float) and value.is_integer():
        return [int(value)]
    if isinstance(value, str):
        try:
            return [int(value.strip(), 10)]
        except ValueError:
            return []
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            parsed = _int_values(item)
            if not parsed:
                return []
            result.extend(parsed)
        return result
    return []


def _verification_statuses(view):
    raw = view.get('verification_levels')
    if not isinstance(raw, dict):
        return {}
    statuses = {}
    valid = (schemas.STATUS_PASS, schemas.STATUS_FAIL,
             schemas.STATUS_NOT_RUN, schemas.STATUS_UNKNOWN)
    for level in schemas.VERIFICATION_LEVELS:
        entry = raw.get(level)
        status = entry.get('status') if isinstance(entry, dict) else entry
        if status in valid:
            statuses[level] = status
    return statuses


def _fmt_values(values):
    return ', '.join(str(value) for value in values)


def _check_covered(view, filters, key, label):
    """Check that the case declares every requested value for one dimension."""
    requested = filters.get(key)
    if not requested:
        return None
    have = _names(view.get(key))
    if not have:
        return False, '%s: case declares none (unknown)' % label
    missing = [value for value in requested
               if _norm_name(value) not in have]
    if missing:
        return False, '%s: case does not cover %s' % (
            label, _fmt_values(missing))
    return True, '%s: covers %s' % (
        label, _fmt_values(requested))


def _match_case(view, filters):
    results = []

    if 'power_min_w' in filters or 'power_max_w' in filters:
        case_range = _power_range(view.get('power_w'))
        query_low = filters.get('power_min_w', 0.0)
        query_high = filters.get('power_max_w')
        query_range = (query_low, query_high)
        if case_range is None:
            results.append((False, 'power: case declares no power range'))
        elif not _overlaps(case_range, query_low, query_high):
            results.append((False, 'power: case %s does not overlap query %s'
                            % (_fmt_range(case_range),
                               _fmt_range(query_range))))
        else:
            results.append((True, 'power: case %s overlaps query %s'
                            % (_fmt_range(case_range),
                               _fmt_range(query_range))))

    for key, label in (('interfaces', 'interfaces'),
                       ('topologies', 'topologies'),
                       ('footprints', 'footprints')):
        result = _check_covered(view, filters, key, label)
        if result is not None:
            results.append(result)

    if 'layers' in filters:
        have = _int_values(view.get('layers'))
        if not have:
            results.append((False, 'layers: case declares none (unknown)'))
        else:
            missing = [layer for layer in filters['layers']
                       if layer not in have]
            if missing:
                results.append((False, 'layers: case does not cover %s'
                                % _fmt_values(missing)))
            else:
                results.append((True, 'layers: covers %s'
                                % _fmt_values(filters['layers'])))

    if 'process' in filters:
        value = view.get('process')
        have = _names(value)
        if not have:
            results.append((False, 'process: case declares none (unknown)'))
        elif _norm_name(filters['process']) not in have:
            results.append((False, 'process: case %r != %r'
                            % (value, filters['process'])))
        else:
            results.append((True, 'process: %s' % filters['process']))

    if 'verification_level_min' in filters:
        statuses = _verification_statuses(view)
        if not statuses:
            results.append((False, 'verification: case records no status'))
        else:
            minimum = schemas.VERIFICATION_LEVELS.index(
                filters['verification_level_min'])
            passed = [position for position, level in
                      enumerate(schemas.VERIFICATION_LEVELS)
                      if statuses.get(level) == schemas.STATUS_PASS]
            highest = max(passed) if passed else -1
            if highest < minimum:
                reached = (schemas.VERIFICATION_LEVELS[highest]
                           if highest >= 0 else 'none')
                results.append((
                    False, 'verification: highest pass %s < %s'
                    % (reached, filters['verification_level_min'])))
            else:
                results.append((
                    True, 'verification: highest pass %s >= %s'
                    % (schemas.VERIFICATION_LEVELS[highest],
                       filters['verification_level_min'])))

    if 'tags' in filters:
        result = _check_covered(view, filters, 'tags', 'tags')
        if result is not None:
            results.append(result)

    if 'source_tier' in filters:
        tier = view.get('source_tier') or ''
        if not tier:
            results.append((False, 'source_tier: case declares none'))
        elif tier != filters['source_tier']:
            results.append((False, 'source_tier: %s != %s'
                            % (tier, filters['source_tier'])))
        else:
            results.append((True, 'source_tier: %s' % tier))

    ok = all(result[0] for result in results)
    return ok, [reason for _, reason in results]


def _tokens(text):
    return _TOKEN_RE.findall((text or '').lower())


def _case_tokens(view):
    parts = [view.get('_text') or '']
    for key in _SEARCH_LIST_KEYS:
        parts.extend(_string_list(view.get(key)))
    if isinstance(view.get('process'), str):
        parts.append(view['process'])
    device = view.get('device')
    if isinstance(device, dict):
        parts.extend(str(device.get(key) or '')
                     for key in ('name', 'version'))
    elif isinstance(device, str):
        parts.append(device)
    layers = _int_values(view.get('layers'))
    parts.extend(str(layer) for layer in layers)
    return set(_tokens(' '.join(parts)))


def _query_tokens(filters):
    parts = [filters.get('text') or '']
    for key in _SEARCH_LIST_KEYS:
        parts.extend(filters.get(key) or [])
    if 'process' in filters:
        parts.append(filters['process'])
    if 'verification_level_min' in filters:
        parts.append(filters['verification_level_min'])
    if 'source_tier' in filters:
        parts.append(filters['source_tier'])
    parts.extend(str(layer) for layer in filters.get('layers') or [])
    return set(_tokens(' '.join(parts)))


def _score(view, filters):
    query = _query_tokens(filters)
    if not query:
        return 0.0, 'tokens: no query text'
    hits = sorted(query & _case_tokens(view))
    score = round(len(hits) / float(len(query)), 4)
    if hits:
        reason = 'tokens: %d/%d matched (%s)' % (
            len(hits), len(query), ', '.join(hits))
    else:
        reason = 'tokens: 0/%d matched' % len(query)
    return score, reason


def _case_provenance(index, entry):
    embedded = entry.get('case')
    loaded = embedded if isinstance(embedded, dict) else None
    if loaded is None and _text(entry.get('path')):
        loaded, _error = _load_case_file(index, entry)
    if isinstance(loaded, dict) and isinstance(loaded.get('provenance'),
                                                dict):
        return loaded['provenance']
    summary = entry.get('summary')
    if isinstance(summary, dict) and isinstance(summary.get('provenance'),
                                                dict):
        return summary['provenance']
    return {}


def _library_coverage(index, entries):
    """Count matched cases, distinct source projects and scenarios.

    Several cases derived from one measured project are scenarios of that
    project, not independent evidence.  Reporting the three numbers keeps that
    distinction machine-readable.
    """
    projects, scenarios, per_project = set(), set(), {}
    for entry in entries:
        provenance = _case_provenance(index, entry)
        project = _string_value(provenance.get('source_project')) or 'unknown'
        # One case id is one scenario even when several cases cite the same
        # source case label; two versions of the same id are one scenario.
        scenarios.add((project, str(entry.get('id'))))
        projects.add(project)
        per_project.setdefault(project, []).append({
            'id': entry.get('id'),
            'scenario': _string_value(provenance.get('source_case')) or
                        str(entry.get('id')),
        })
    return {
        'cases': len(entries),
        'source_projects': len(projects),
        'scenarios': len(scenarios),
        'per_project': [
            {'source_project': project, 'cases': items}
            for project, items in sorted(per_project.items())
        ],
        'note': 'cases sharing a provenance.source_project are scenarios of '
                'that project, not independent projects',
    }


def search(index, query):
    """Return matching cases and explicit rejections for one query.

    Hard filters run first.  Surviving cases receive a deterministic token
    overlap score; ties break on id and version.  A filter value that cannot
    be parsed raises ``FeedbackError(invalid_input)`` instead of returning an
    empty result.  ``unknowns`` is always present and empty: every requested
    filter ends up either matched or rejected with a reason.
    """
    if isinstance(index, (str, Path)):
        index = load_index(index)
    else:
        _check_index(index)

    filters = _normalize_filters(query)
    matches = []
    matched_entries = []
    rejected = []
    for entry in index['cases']:
        view = _entry_view(index, entry, filters)
        ok, reasons = _match_case(view, filters)
        if view.get('_read_error') and not ok:
            reasons.insert(0, 'case: %s' % view['_read_error'])
        identity = {'id': entry.get('id'), 'version': entry.get('version')}
        if ok:
            score, score_reason = _score(view, filters)
            match = dict(identity)
            match['score'] = score
            match['reasons'] = reasons + [score_reason]
            matches.append(match)
            matched_entries.append(entry)
        else:
            rejection = dict(identity)
            rejection['reasons'] = reasons
            rejected.append(rejection)

    matches.sort(key=lambda item: (-item['score'], str(item['id']),
                                   str(item['version'])))
    rejected.sort(key=lambda item: (str(item['id']), str(item['version'])))
    for item in matches:
        item.pop('version', None)
    for item in rejected:
        item.pop('version', None)
    return {
        'schema': schemas.SCHEMA_CASE_QUERY,
        'filters': filters,
        'matches': matches,
        'rejected': rejected,
        'unknowns': [],
        'library': _library_coverage(index, matched_entries),
    }


# ---------------------------------------------------------------------------
# reuse guard
# ---------------------------------------------------------------------------

def _device_name(value):
    if isinstance(value, dict):
        value = value.get('name')
    if _text(value):
        return value.strip()
    return None


def _device_version(value):
    if isinstance(value, dict):
        candidate = value.get('version')
        if _text(candidate):
            return candidate.strip()
        if _is_number(candidate):
            return candidate
        return None
    if _is_number(value):
        return value
    return None


def _reuse_case_values(case):
    applies = _applies(case)
    device = _first(applies, case, 'device')
    device_version = (applies.get('device_version') or
                      _device_version(device) or
                      case.get('device_version'))
    return {
        'power': _first(applies, case, 'power_w', 'power'),
        'interfaces': _first(applies, case, 'interfaces', 'interface'),
        'topology': _first(applies, case, 'topologies', 'topology'),
        'footprint': _first(applies, case, 'footprints', 'footprint'),
        'layers': _first(applies, case, 'layers', 'layer'),
        'process': _first(applies, case, 'process'),
        'device': device,
        'device_version': device_version,
        'version': case.get('version'),
    }


def _reuse_target_values(target):
    applies = target.get('applies_when')
    if not isinstance(applies, dict):
        applies = {}

    def pick(*keys):
        for source in (target, applies):
            for key in keys:
                value = source.get(key)
                if value not in (None, '', [], {}):
                    return value
        return None

    device = pick('device')
    power = pick('power_w', 'power')
    if power is None and ('power_min_w' in target or
                          'power_max_w' in target):
        power = {'min': target.get('power_min_w'),
                 'max': target.get('power_max_w')}
    version = pick('version', 'case_version')
    device_version = _device_version(device)
    if device_version is None:
        device_version = pick('device_version')
    return {
        'power': power,
        'interfaces': pick('interfaces', 'interface'),
        'topology': pick('topologies', 'topology'),
        'footprint': pick('footprints', 'footprint'),
        'layers': pick('layers', 'layer'),
        'process': pick('process'),
        'device': device,
        'device_version': device_version,
        'version': version,
    }


def _verification_is_current(case):
    levels = case.get('verification_levels') or {}
    passed = [level for level, entry in levels.items()
              if isinstance(entry, dict) and
              entry.get('status') == schemas.STATUS_PASS and
              entry.get('evidence')]
    if not passed:
        return False
    provenance = case.get('provenance') or {}
    if not isinstance(provenance, dict):
        provenance = {}
    if case.get('stale') is True or provenance.get('stale') is True:
        return False
    if provenance.get('invalidated') is True or \
            provenance.get('invalidated_at'):
        return False
    return True


def _reuse_names(value, where):
    if value is None:
        return None
    if isinstance(value, str):
        names = [part.strip() for part in value.split(',') if part.strip()]
        return names or None
    if isinstance(value, (list, tuple)):
        names = [item.strip() for item in value
                 if isinstance(item, str) and item.strip()]
        return names or None
    _invalid('%s must be a string or a list of strings' % where)


def _target_layers(value, where):
    if value is None:
        return None
    layers = _int_values(value)
    if not layers:
        _invalid('%s must be an integer or a list of integers' % where)
    return layers


def _target_process(value, where):
    if value is None:
        return None
    if not _text(value):
        _invalid('%s must be a non-empty string' % where)
    return value.strip()


def reuse_check(case, target):
    """Compare a case with a target design and list forced rechecks.

    ``differences`` holds mismatches in the eight compared dimensions; any
    difference means the case is not directly applicable to the target.
    ``required_rechecks`` names every dimension that was not proven equal,
    including target values that were not stated.  A version, device,
    footprint, layer or process change always forces the matching recheck.
    ``can_inherit_verification`` is true only when every dimension matches and
    the case has current pass evidence; an old pass conclusion is never
    inherited.
    """
    validate_case(case)
    if not isinstance(target, dict):
        _invalid('target must be an object')

    source = _reuse_case_values(case)
    wanted = _reuse_target_values(target)
    differences = []
    rechecks = []
    applicable = True

    def difference(dimension, reason, case_value, target_value):
        nonlocal applicable
        differences.append({
            'dimension': dimension,
            'reason': reason,
            'case': case_value,
            'target': target_value,
        })
        applicable = False
        if dimension not in rechecks:
            rechecks.append(dimension)

    def need(dimension, case_value=None):
        """An unstated target value blocks inheritance if the case has one."""
        if case_value in (None, '', [], {}):
            return
        if dimension not in rechecks:
            rechecks.append(dimension)

    # power: the target range must sit inside what the case actually covers.
    target_power = wanted['power']
    case_range = _power_range(source['power'])
    if target_power is None:
        need('power', case_range)
    else:
        target_range = _power_range(target_power)
        if target_range is None:
            _invalid('target.power_w is not a usable power value')
        if case_range is None:
            difference('power', 'case states no power range', None,
                       target_power)
        elif not _contains(case_range, target_range):
            difference('power', 'target power is outside the case range',
                       _fmt_range(case_range), _fmt_range(target_range))

    # interfaces: every requested interface must be declared by the case.
    target_interfaces = _reuse_names(wanted['interfaces'],
                                     'target.interfaces')
    case_interfaces = _names(source['interfaces'])
    if target_interfaces is None:
        need('interfaces', case_interfaces)
    elif not case_interfaces:
        difference('interfaces', 'case declares no interfaces', None,
                   target_interfaces)
    else:
        missing = [name for name in target_interfaces
                   if _norm_name(name) not in case_interfaces]
        if missing:
            difference('interfaces', 'interface(s) not covered by case',
                       sorted(case_interfaces), missing)

    # topology: at least one requested topology must be declared.
    target_topology = _reuse_names(wanted['topology'], 'target.topology')
    case_topologies = _names(source['topology'])
    if target_topology is None:
        need('topology', case_topologies)
    elif not case_topologies:
        difference('topology', 'case declares no topology', None,
                   target_topology)
    elif not ({_norm_name(name) for name in target_topology} &
              case_topologies):
        difference('topology', 'topology differs',
                   sorted(case_topologies), target_topology)

    # footprint: a change does not block reuse of the method, but the case is
    # not directly applicable and every changed dimension forces rechecks.
    target_footprints = _reuse_names(wanted['footprint'],
                                     'target.footprints')
    case_footprints = _names(source['footprint'])
    if target_footprints is None:
        need('footprint', case_footprints)
    elif not case_footprints:
        difference('footprint', 'case declares no footprint', None,
                   target_footprints)
    elif {_norm_name(name) for name in target_footprints} != \
            case_footprints:
        difference('footprint', 'footprint set differs',
                   sorted(case_footprints), target_footprints)

    # layers
    target_layers = _target_layers(wanted['layers'], 'target.layers')
    case_layers = _int_values(source['layers'])
    if target_layers is None:
        need('layers', case_layers)
    elif not case_layers:
        difference('layers', 'case declares no layer count', None,
                   target_layers)
    elif set(target_layers) != set(case_layers):
        difference('layers', 'layer count differs', case_layers,
                   target_layers)

    # process
    target_process = _target_process(wanted['process'], 'target.process')
    case_process = source['process']
    if isinstance(case_process, (list, tuple)):
        case_processes = {_norm_name(item) for item in case_process
                          if _text(item)}
    elif _text(case_process):
        case_processes = {_norm_name(case_process)}
    else:
        case_processes = set()
    if target_process is None:
        need('process', case_processes)
    elif not case_processes:
        difference('process', 'case declares no process', None,
                   target_process)
    elif _norm_name(target_process) not in case_processes:
        difference('process', 'process differs', case_process,
                   target_process)

    # device name and the device's own version (when both state one)
    target_device = _device_name(wanted['device'])
    case_device = _device_name(source['device'])
    if target_device is None:
        need('device', case_device)
    elif case_device is None:
        difference('device', 'case declares no device', None, target_device)
    elif _norm_name(target_device) != _norm_name(case_device):
        difference('device', 'device differs', case_device, target_device)

    target_device_version = wanted['device_version']
    case_device_version = source['device_version']
    if target_device_version is not None and case_device_version is not None \
            and not _same_version(case_device_version,
                                  target_device_version):
        difference('version', 'device version differs', case_device_version,
                   target_device_version)

    # version: the case revision, plus a device version when both state one.
    target_version = wanted['version']
    if target_version is None:
        need('version', source['version'])
    else:
        case_version = source['version']
        if not _same_version(case_version, target_version):
            difference('version', 'version differs', case_version,
                       target_version)

    ordered = [dimension for dimension in REUSE_DIMENSIONS
               if dimension in rechecks]
    can_inherit = (applicable and not differences and not ordered and
                   _verification_is_current(case))
    return {
        'applicable': applicable,
        'differences': differences,
        'required_rechecks': ordered,
        'can_inherit_verification': bool(can_inherit),
    }


def _same_version(left, right):
    if left is None or right is None:
        return False
    return str(left).strip().lower() == str(right).strip().lower()
