"""Closed-loop feedback layer for EasyCirq.

The package turns one design task into explicit, resumable states:
observe → plan → prepare → apply → readback → verify → repair → done/failed/
blocked.  It never treats "the CLI returned ok" as "the board is correct":
call, write, save, reopen persistence and quality are separate facts.

Modules:
  schemas      versioned contracts and validators
  observe      capability probe, observation collection, evidence and cache
  loop         resumable loop state, budgets, rounds, issues and stop rules
  scope        modification contract, writable/check scope, diffs, recovery
  evaluate     layered quality evaluation and candidate comparison
  cases        case library, retrieval filters and reuse guards
  cli          one stable JSON entry point (feedback_loop.py)
"""
