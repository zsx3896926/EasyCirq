## What

Add the A2 coverage spike as reviewable, offline-verifiable material:

- `spike/a2-coverage/` - thin official-CLI adapter (`official_cli.py`,
  `probe_official.py`, `mcp_stdio.py`), workflow definitions, matrix generator,
  PR-split planner;
- `tests/a2_coverage_spike_tests/` - 65 offline tests (no EDA/network);
- `docs/parallel-a2-coverage/` - environment, methodology, 11-workflow coverage
  matrix, rubric and provisional decision;
- `docs/evidence/a2-coverage-2026-10-28/` - receipts (raw CLI JSON, API catalog,
  MCP transcript, export artifacts, hashes).

## Why

PR #36 delivered the execution layer as a ~1,700-file fork. This PR is the
evidence-backed alternative: measure what the **official** `lceda-pro` CLI/MCP
already covers, and keep only a thin typed layer. It is deliberately small and
does not modify `design-hardware/**`, `runtime/**`, `connector/**` or `protocol/**`.

## Status of the conclusion

`decision-provisional`: W04/W05/W09-save were not measured because
design-content write probes were not authorized in that session. The matrix
records `blocked (authorization)`; a final A1/A2/A3 needs one authorized write
probe on a disposable project.

## Acceptance

- [ ] `python spike/a2-coverage/run_spike.py --offline` regenerates the matrix
- [ ] `python -m unittest discover -s tests` green (3.10 / 3.13 CI)
- [ ] no EDA, daemon or network call in the offline path (tested)
- [ ] draft PR; merging it does not decide A1/A2/A3 by itself
