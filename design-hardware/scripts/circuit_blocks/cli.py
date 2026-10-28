"""Command line interface for the parameterized circuit blocks.

Run from ``design-hardware/scripts`` (or with it on ``PYTHONPATH``)::

    python -m circuit_blocks list
    python -m circuit_blocks describe led_indicator
    python -m circuit_blocks generate led_indicator --example --out led.json
    python -m circuit_blocks generate adc_divider --input divider.json
    python -m circuit_blocks validate led.json --recompute
    python -m circuit_blocks compose --input design.json --out design.out.json
    python -m circuit_blocks facts list

Machine output is JSON on stdout; human summaries go to stderr so a pipe stays
clean.  Exit codes: 0 ready/valid, 2 invalid input, 3 needs device facts,
4 unsupported/no feasible solution, 5 incomplete composition, 6 validation
failed, 1 internal error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import TOOL_NAME, __version__
from .canonical import canonical_text
from .blocks import REGISTRY, module_types
from .devices import available_facts, load_fact
from .errors import CircuitBlockError, InputInvalid, NeedsDeviceFacts, Unsupported
from .validate import recompute_module, validate_design, validate_module_result

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INPUT_INVALID = 2
EXIT_NEEDS_FACTS = 3
EXIT_UNSUPPORTED = 4
EXIT_INCOMPLETE = 5
EXIT_VALIDATION_FAILED = 6


def build_parser():
    parser = argparse.ArgumentParser(
        prog='python -m circuit_blocks',
        description='Parameterized standard circuit blocks: math + connectivity contracts, '
                    'no EDA binding.')
    parser.add_argument('--version', action='version', version='%(prog)s ' + __version__)
    sub = parser.add_subparsers(dest='command', metavar='COMMAND')

    listing = sub.add_parser('list', help='list available modules')
    listing.add_argument('--json', action='store_true', help='machine-readable output')

    describe = sub.add_parser('describe', help='describe one module and its inputs')
    describe.add_argument('module_type')
    describe.add_argument('--json', action='store_true')

    generate = sub.add_parser('generate', help='generate one module instance')
    generate.add_argument('module_type')
    source = generate.add_mutually_exclusive_group(required=True)
    source.add_argument('--input', metavar='FILE', help='input JSON file, or - for stdin')
    source.add_argument('--example', action='store_true', help='use the documented example input')
    generate.add_argument('--instance', dest='instance_id', metavar='ID',
                          help='instance id (namespace); default is the module type')
    generate.add_argument('--name', dest='display_name', metavar='TEXT', help='display name')
    generate.add_argument('--out', metavar='FILE', help='write the result JSON here')
    generate.add_argument('--svg', metavar='FILE', help='write an analysis SVG (not an EDA schematic)')
    generate.add_argument('--allow-nonready', action='store_true',
                          help='exit 0 even when the status is not ready_abstract')
    generate.add_argument('--summary', action='store_true', help='human summary on stderr')

    validate = sub.add_parser('validate', help='validate a result file (and optionally recompute it)')
    validate.add_argument('file', metavar='FILE')
    validate.add_argument('--recompute', action='store_true',
                          help='re-run the module from its echoed inputs and compare content hashes')
    validate.add_argument('--design', action='store_true', help='the file is a composed design')

    compose = sub.add_parser('compose', help='compose modules into an abstract design')
    compose.add_argument('--input', metavar='FILE', required=True, help='design JSON file, or - for stdin')
    compose.add_argument('--out', metavar='FILE')
    compose.add_argument('--svg', metavar='FILE')
    compose.add_argument('--allow-nonready', action='store_true')

    facts = sub.add_parser('facts', help='inspect bundled verified device facts')
    facts.add_argument('action', choices=['list', 'show'])
    facts.add_argument('fact_id', nargs='?')
    facts.add_argument('--json', action='store_true')

    return parser


def main(argv=None):
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(parser, args)
    except (InputInvalid, NeedsDeviceFacts, Unsupported) as error:
        document = _error_document(error, getattr(args, 'module_type', None))
        _emit_json(document, None)
        print('error: %s' % error, file=sys.stderr)
        return _exit_code_for(error)
    except CircuitBlockError as error:
        print('internal error: %s' % error, file=sys.stderr)
        return EXIT_INTERNAL
    except (OSError, ValueError) as error:
        print('error: %s' % error, file=sys.stderr)
        return EXIT_INTERNAL


def _dispatch(parser, args):
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_INPUT_INVALID
    if args.command == 'list':
        return _cmd_list(args)
    if args.command == 'describe':
        return _cmd_describe(args)
    if args.command == 'generate':
        return _cmd_generate(args)
    if args.command == 'validate':
        return _cmd_validate(args)
    if args.command == 'compose':
        return _cmd_compose(args)
    if args.command == 'facts':
        return _cmd_facts(args)
    parser.error('unknown command %r' % args.command)
    return EXIT_INPUT_INVALID


def _cmd_list(args):
    rows = []
    for module_type in module_types():
        block = REGISTRY[module_type]
        rows.append({'module_type': module_type, 'template_version': block.TEMPLATE_VERSION,
                     'title': block.TITLE, 'summary': block.SUMMARY})
    if args.json:
        _emit_json({'schema': 'circuit-blocks/module-list/1', 'tool': TOOL_NAME,
                    'version': __version__, 'modules': rows}, None)
    else:
        for row in rows:
            print('%-22s %s' % (row['module_type'], row['title']))
        print('\n%d modules. Use `describe <module_type>` for the input contract.' % len(rows))
    return EXIT_OK


def _cmd_describe(args):
    if args.module_type not in REGISTRY:
        raise InputInvalid('unknown module_type %r (available: %s)'
                           % (args.module_type, ', '.join(module_types())))
    description = REGISTRY[args.module_type].describe()
    if args.json:
        _emit_json(description, None)
    else:
        _print_description(description)
    return EXIT_OK


def _print_description(description):
    print('%s  (template %s)' % (description['module_type'], description['template_version']))
    print(description['title'])
    print()
    print(description['summary'])
    print('\ntopology: %s' % description['topology'])
    if description['applicability']:
        print('\napplicable:')
        for item in description['applicability']:
            print('  - %s' % item)
    if description['not_applicable']:
        print('\nnot applicable:')
        for item in description['not_applicable']:
            print('  - %s' % item)
    print('\ninputs:')
    for field in description['inputs']:
        unit = field.get('unit')
        requirement = 'required' if field['required'] else 'optional'
        detail = field['kind'] + (' (%s)' % unit if unit else '')
        if 'values' in field:
            detail += ' one of: ' + '|'.join(field['values'])
        if 'default' in field:
            detail += '; default=%r' % (field['default'],)
        print('  %-24s %-10s %-28s %s' % (field['name'], requirement, detail, field['doc']))
    if description['required_device_facts']:
        print('\nrequires device facts:')
        for item in description['required_device_facts']:
            print('  - %s' % item)
    print('\nexample input:')
    print(json.dumps(description['example_input'], indent=2, ensure_ascii=False))


def _cmd_generate(args):
    if args.module_type not in REGISTRY:
        raise InputInvalid('unknown module_type %r (available: %s)'
                           % (args.module_type, ', '.join(module_types())))
    block = REGISTRY[args.module_type]
    raw = dict(block.EXAMPLE_INPUT) if args.example else _read_json(args.input)
    result = block.generate(raw, instance_id=args.instance_id, display_name=args.display_name)
    if args.svg:
        from .svg import result_svg
        _write_text(Path(args.svg), result_svg(result))
    _emit_json(result, args.out)
    if args.summary or not args.out:
        _print_summary(result)
    if result['status'] == 'ready_abstract':
        return EXIT_OK
    if args.allow_nonready:
        return EXIT_OK
    return {'needs_device_facts': EXIT_NEEDS_FACTS,
            'unsupported': EXIT_UNSUPPORTED,
            'input_invalid': EXIT_INPUT_INVALID}.get(result['status'], EXIT_INTERNAL)


def _cmd_validate(args):
    payload = _read_json(args.file)
    errors = []
    if args.design:
        report = validate_design(payload)
    else:
        report = validate_module_result(payload)
        if report['status'] == 'valid' and args.recompute:
            recomputed = recompute_module(payload, REGISTRY)
            report['recompute'] = recomputed
            if recomputed['status'] != 'match':
                errors.append({'code': 'recompute_' + recomputed['status'],
                               'detail': recomputed.get('detail', '')})
        elif args.recompute:
            report['recompute'] = {'status': 'skipped', 'detail': 'hash/structure validation failed first'}
    if errors:
        report['status'] = 'invalid'
        report['problems'].extend(errors)
    report['file'] = str(args.file)
    _emit_json(report, None)
    if report['status'] == 'valid':
        print('valid: %s' % args.file, file=sys.stderr)
        return EXIT_OK
    print('invalid: %s' % args.file, file=sys.stderr)
    for problem in report['problems']:
        print('  - %s: %s' % (problem['code'], problem['detail']), file=sys.stderr)
    return EXIT_VALIDATION_FAILED


def _cmd_compose(args):
    from .compose import compose_design, validate_compose_input
    payload = _read_json(args.input)
    validate_compose_input(payload)
    design = compose_design(payload)
    if args.svg:
        from .svg import design_svg
        _write_text(Path(args.svg), design_svg(design))
    _emit_json(design, args.out)
    if args.out or not args.allow_nonready:
        print('design status: %s' % design['status'], file=sys.stderr)
    if design['status'] == 'ready_abstract':
        return EXIT_OK
    if args.allow_nonready:
        return EXIT_OK
    return EXIT_INCOMPLETE if design['status'] == 'incomplete' else EXIT_UNSUPPORTED


def _cmd_facts(args):
    available = available_facts()
    if args.action == 'list':
        rows = []
        for fact_id in sorted(available):
            try:
                data = load_fact(fact_id)
                rows.append({'fact_id': fact_id, 'category': data['category'],
                             'mpn': data['mpn'], 'manufacturer': data.get('manufacturer'),
                             'file': str(available[fact_id].relative_to(Path.cwd()))
                             if available[fact_id].is_relative_to(Path.cwd())
                             else available[fact_id].name})
            except InputInvalid as error:
                rows.append({'fact_id': fact_id, 'error': str(error)})
        if args.json:
            _emit_json({'schema': 'circuit-blocks/fact-list/1', 'facts': rows}, None)
        else:
            for row in rows:
                if 'error' in row:
                    print('%-28s INVALID: %s' % (row['fact_id'], row['error']))
                else:
                    print('%-28s %-14s %s (%s)' % (row['fact_id'], row['category'],
                                                   row['mpn'], row['manufacturer']))
            print('\n%d fact file(s).' % len(rows))
        return EXIT_OK
    if not args.fact_id:
        raise InputInvalid('facts show needs a fact_id')
    data = load_fact(args.fact_id)
    _emit_json(data, None)
    return EXIT_OK


# -- helpers ---------------------------------------------------------
def _configure_stdio():
    """Force UTF-8 I/O so JSON containing symbols such as ± is never mangled."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (ValueError, OSError):
                pass


def _read_json(path):
    if path == '-':
        text = sys.stdin.read()
        source = '<stdin>'
    else:
        try:
            text = Path(path).read_text(encoding='utf-8-sig')
        except OSError as error:
            raise InputInvalid('cannot read %s: %s' % (path, error))
        source = path
    try:
        value = json.loads(text)
    except ValueError as error:
        raise InputInvalid('%s is not valid JSON: %s' % (source, error))
    if not isinstance(value, dict):
        raise InputInvalid('%s must contain a JSON object' % source)
    return value


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


def _emit_json(document, path):
    text = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if path:
        _write_text(Path(path), text)
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


def _print_summary(result):
    print('', file=sys.stderr)
    print('%s %s -> %s' % (result['module_type'], result['instance_id'], result['status']),
          file=sys.stderr)
    for reason in result['status_reasons']:
        print('  reason: %s' % reason, file=sys.stderr)
    for component in result['components']:
        value = component['value']
        text = ('%s %s' % (value['value'], value['unit'])) if value else component['kind']
        print('  %-4s %-26s %s' % (component['ref'], component['role'], text), file=sys.stderr)
    print('  ports: %s' % ', '.join(port['id'] for port in result['ports']), file=sys.stderr)
    print('  hash: %s' % result['content_hash'], file=sys.stderr)


def _error_document(error, module_type):
    kind = ('input_invalid' if isinstance(error, InputInvalid)
            else 'needs_device_facts' if isinstance(error, NeedsDeviceFacts)
            else 'unsupported')
    document = {
        'schema': 'circuit-blocks/error/1',
        'tool': {'name': TOOL_NAME, 'version': __version__},
        'module_type': module_type,
        'status': kind,
        'status_reasons': [str(error)],
        'errors': [{'kind': kind, 'message': str(error)}],
    }
    if isinstance(error, InputInvalid) and error.field:
        document['errors'][0]['field'] = error.field
    if isinstance(error, NeedsDeviceFacts):
        document['errors'][0]['missing'] = list(error.missing)
        document['errors'][0]['details'] = dict(error.details)
    return document


def _exit_code_for(error):
    if isinstance(error, InputInvalid):
        return EXIT_INPUT_INVALID
    if isinstance(error, NeedsDeviceFacts):
        return EXIT_NEEDS_FACTS
    if isinstance(error, Unsupported):
        return EXIT_UNSUPPORTED
    return EXIT_INTERNAL


if __name__ == '__main__':
    sys.exit(main())
