"""Exception types shared by the circuit-block generators.

The CLI maps each exception class to one exit code so callers can distinguish
"you typed something impossible" from "the maths has no solution" from "this
part's facts are missing".  ``docs/parallel-circuit-blocks/contract.md`` is the
normative description of the four non-ready statuses.
"""
from __future__ import annotations


class CircuitBlockError(Exception):
    """Base class; exit code 1 (internal/unexpected)."""


class InputInvalid(CircuitBlockError):
    """Malformed, contradictory or out-of-domain input. exit 2."""

    def __init__(self, message, *, field=None):
        self.field = field
        super().__init__(message if field is None else '%s: %s' % (field, message))


class Unsupported(CircuitBlockError):
    """Well-formed input outside the module's declared applicability. exit 4."""

    def __init__(self, message, *, reasons=None):
        self.reasons = list(reasons or [message])
        super().__init__(message)


class NeedsDeviceFacts(CircuitBlockError):
    """The circuit maths needs part facts that were not supplied. exit 3."""

    def __init__(self, missing, message=None, *, details=None):
        self.missing = list(missing)
        self.details = dict(details or {})
        text = message or ('missing device facts: ' + ', '.join(str(item) for item in self.missing))
        super().__init__(text)


class NoFeasibleSolution(CircuitBlockError):
    """Hard constraints cannot be satisfied. exit 4 (reported as unsupported)."""

    def __init__(self, message, *, bounds=None, details=None):
        self.bounds = bounds
        self.details = dict(details or {})
        super().__init__(message)


class CompositionConflict(CircuitBlockError):
    """A composed design contains a proven conflict. exit 4."""

    def __init__(self, message, *, conflicts=None):
        self.conflicts = list(conflicts or [])
        super().__init__(message)
