"""Base class shared by every circuit block.

A block declares an input schema, a title/summary, its applicability domain,
the device facts it needs, and primary sources.  ``compute`` writes the result
draft and returns a status.  The base class guarantees that:

* input normalisation and unknown-field rejection happen once, here;
* a non-ready status always carries a reason;
* the produced JSON validates against :mod:`circuit_blocks.validate` before it
  is allowed out — a generator bug becomes an exception, never a silently
  plausible result.
"""
from __future__ import annotations

from .. import TOOL_NAME, __version__
from ..errors import (CircuitBlockError, InputInvalid, NeedsDeviceFacts,
                      NoFeasibleSolution, Unsupported)
from ..result import Draft
from ..schema import describe_schema, validate_inputs
from ..validate import validate_module_result


class Block(object):
    MODULE_TYPE = ''
    TEMPLATE_VERSION = '1.0.0'
    TITLE = ''
    SUMMARY = ''
    TOPOLOGY = ''
    APPLICABILITY = ()
    NON_APPLICABILITY = ()
    REQUIRED_DEVICE_FACTS = ()
    SOURCES = ()
    INPUT_SCHEMA = {}
    EXAMPLE_INPUT = {}

    # -- public API -----------------------------------------------------
    def generate(self, raw_inputs, *, instance_id=None, display_name=None):
        """Validate inputs and return a self-validated module result."""
        normalized = self.normalize(raw_inputs)
        draft = Draft(self.MODULE_TYPE, self.TEMPLATE_VERSION,
                      instance_id or self.MODULE_TYPE, display_name,
                      normalized, self.INPUT_SCHEMA)
        try:
            outcome = self.compute(draft, normalized)
        except NeedsDeviceFacts as error:
            for name in error.missing:
                draft.unknown(_unknown_id(name), 'required device fact is missing: %s' % name,
                              how_to_resolve='supply the fact from the datasheet or a device fact file')
            outcome = ('needs_device_facts', [str(error)], None)
        except NoFeasibleSolution as error:
            draft.constraint('no_feasible_solution', str(error), kind='hard',
                             source='derivation', rationale='hard constraints conflict')
            outcome = ('unsupported', [str(error)], None)
        except Unsupported as error:
            outcome = ('unsupported', list(error.reasons), None)
        status, reasons, notes = _normalise_outcome(outcome)
        result = draft.finish(status, reasons, notes=notes)
        report = validate_module_result(result)
        if report['status'] != 'valid':
            raise CircuitBlockError(
                '%s produced an invalid result: %s'
                % (self.MODULE_TYPE, '; '.join('%s (%s)' % (item['code'], item['detail'])
                                               for item in report['problems'])))
        return result

    def normalize(self, raw_inputs):
        return validate_inputs(self.INPUT_SCHEMA, raw_inputs)

    def compute(self, draft, inputs):
        """Subclass hook: fill ``draft`` and return a status/outcome."""
        raise NotImplementedError

    # -- description ----------------------------------------------------
    def describe(self):
        return {
            'module_type': self.MODULE_TYPE,
            'template_version': self.TEMPLATE_VERSION,
            'title': self.TITLE,
            'summary': self.SUMMARY,
            'topology': self.TOPOLOGY,
            'applicability': list(self.APPLICABILITY),
            'not_applicable': list(self.NON_APPLICABILITY),
            'required_device_facts': list(self.REQUIRED_DEVICE_FACTS),
            'sources': [dict(source) for source in self.SOURCES],
            'inputs': describe_schema(self.INPUT_SCHEMA),
            'example_input': dict(self.EXAMPLE_INPUT),
            'output_schema': 'circuit-blocks/module-result/1',
            'statuses': ['ready_abstract', 'needs_device_facts', 'unsupported', 'input_invalid'],
        }


def _normalise_outcome(outcome):
    if isinstance(outcome, str):
        return outcome, [], None
    if isinstance(outcome, tuple):
        if len(outcome) == 2:
            return outcome[0], list(outcome[1] or []), None
        if len(outcome) == 3:
            return outcome[0], list(outcome[1] or []), outcome[2]
    raise CircuitBlockError('compute() must return a status string or a (status, reasons[, notes]) tuple')


def _unknown_id(name):
    clean = ''.join(character if character.isalnum() else '_' for character in str(name))
    return 'missing_' + clean.lower()
