# PR #36 split path sets (generated)

Do not edit the `*-paths.txt` / `*-delete.txt` files by hand - regenerate with:

```powershell
python spike/a2-coverage/plan_pr36_split.py generate
```

The exact push / `gh pr create` commands are in
[`../pr36-split-runbook.md`](../pr36-split-runbook.md). PR bodies are in
[`bodies/`](bodies/).

## State this was generated against

See `manifest.json` (`refs` + `warnings`). At generation time:

- `origin/main` already contained PR #36 (`Merge pull request #36 ...`), i.e. the
  1,700+ file toolchain fork is merged.
- `origin/feat/integrated-eda-toolchain` had moved on by two commits; its delta
  against `main` was **25 files** (`now/residual-paths.txt`).
- The historical PR #36 split (task-book baseline -> A tip `dfa8f10`) is therefore
  **replay-only**: `history/*` exists for audit, not for pushing.

## Sets

| set | content | count |
| --- | --- | --- |
| `history/history-pr1-*` | docs + benchmarks + root README (historical PR-1) | 530 |
| `history/history-pr2-*` | `distribution/**` + installer/updater tests/tools (historical PR-2) | 10 |
| `history/history-pr3-*` | runtime/connector/protocol/third_party + Skill migration (historical PR-3) | 1,270 + 4 deletes |
| `now/residual-*` | the two A-branch commits still ahead of `main` (manufacture exports) | 25 |
| `now/thin-layer-*` | the A2 thin layer / spike branch (`spike/a2-coverage/`, tests, docs, evidence) | 210 |
| `now/retire-paths.txt` | deletion scope for the A2 retire PR (gated) | 1,145 |

Counts and sha256 of every list are in `manifest.json.sets`.

## Rules

- `history`: **never push** to the shared remote; replay only in a scratch clone.
- `now/residual`: base the branch on the A branch tip (it already contains the
  commits); compare against `main`.
- `now/thin-layer`: base on `origin/main` and apply the set (adds only).
- `now/retire`: gated by the authorized W04/W05/W09 write probe; apply stages the
  deletions, text/code follow-ups are manual.
