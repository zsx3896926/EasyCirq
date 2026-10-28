## What

Take the two commits that are still only on `feat/integrated-eda-toolchain`
(after PR #36 was merged) as their own PR:

- `feat: manufacture exports verified on the real host (gerber/cpl/netlist/3d)`
- `feat(connector): spike the host @beta manufacture exports`

Delta vs `main`: 25 files (`connector/src/pcb-manufacture.ts` new,
`connector/src/actions.ts` + `extension.json` + lockfile updates, a measured
capabilities action, manufacture-spike evidence under
`docs/toolchain-integration/evidence/`, and `tools/zhigou_manufacture_spike.py`).

## Why separate

PR #36 mixed docs, distribution, the runtime/connector fork and this manufacturing
work in one 1,700+ file PR. The fork part is now merged, so the remaining work is
small, reviewable and independent.

## Evidence

- `docs/toolchain-integration/evidence/manufacture-spike/99-summary.json`
- `docs/toolchain-integration/evidence/gates/manufacturing/` (Gerber zip, CPL csv,
  netlist)
- `docs/toolchain-integration/capability-matrix.md` (measured capabilities)

## Acceptance

- [ ] `git diff --name-status origin/main...HEAD` equals the 25 paths recorded in
      `docs/parallel-a2-coverage/pr-split/manifest.json` (`sets.residual`)
- [ ] connector builds (`npx ts-node ./config/esbuild.prod.ts`) - CI job decides
- [ ] no change to `design-hardware/**` behaviour outside the capability record
- [ ] draft PR (do not merge without the A2 decision)

Do not merge this PR by itself; it is one of the three split steps.
