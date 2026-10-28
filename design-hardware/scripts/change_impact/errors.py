"""Machine-readable failures for the change-impact tool.

A failure carries a ``failure_class`` from :mod:`change_impact` and one or more
``issues`` with a stable ``code``.  Callers branch on the class/code, never on
the English message.  ``to_payload()`` is the only thing the CLI prints on an
invalid input, so a stale report can never be mistaken for a new one.
"""
from __future__ import annotations

from . import FAILURE_INVALID_INPUT

MAX_ISSUES = 200


class ChangeImpactError(Exception):
    """Base error with a machine-readable class and structured issues."""

    failure_class = FAILURE_INVALID_INPUT

    def __init__(self, message, *, code='invalid', where=None, issues=None):
        super().__init__(message)
        self.message = str(message)
        self.code = str(code)
        self.where = where
        self.issues = list(issues or [])
        if not self.issues:
            self.issues.append(issue(self.code, self.message, where=self.where))

    def to_payload(self, *, schema, tool_version):
        return {
            'schema': schema,
            'tool_version': tool_version,
            'status': 'input_invalid',
            'failure_class': self.failure_class,
            'message': self.message,
            'issues': _bounded(self.issues),
            'executed': [],
            'not_run': ['eda_read', 'eda_write', 'host_drc', 'save_and_reopen',
                        'official_plot', 'physical_test'],
            'note': ('the input was rejected; no analysis report was produced '
                     'and any previous output file must be treated as stale'),
        }


class InputInvalid(ChangeImpactError):
    failure_class = FAILURE_INVALID_INPUT


class PathConflict(ChangeImpactError):
    failure_class = 'path_conflict'


class BudgetExhausted(ChangeImpactError):
    failure_class = 'budget_exhausted'


def issue(code, message, *, where=None, **extra):
    payload = {'code': str(code), 'message': str(message)}
    if where is not None:
        payload['where'] = str(where)
    for key in sorted(extra):
        if extra[key] is not None:
            payload[key] = extra[key]
    return payload


def _bounded(issues):
    return issues[:MAX_ISSUES]


def require(condition, code, message, *, where=None):
    """Raise :class:`InputInvalid` unless ``condition`` holds."""
    if not condition:
        raise InputInvalid(message, code=code, where=where)
