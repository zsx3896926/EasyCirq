# Frozen mechanical-layout benchmark

Offline subprocess benchmark for
[`mechanical_layout`](../../easycirq/scripts/mechanical_layout). It runs
the real CLI (`python -m mechanical_layout`) against static JSON documents and
checks exit code, status and required/forbidden rule IDs.

```text
python benchmarks/mechanical-layout/run_benchmarks.py
python benchmarks/mechanical-layout/run_benchmarks.py --holdout
python benchmarks/mechanical-layout/run_benchmarks.py --case pass_panel
```

Run from the repository root. The runner sets
`PYTHONPATH=easycirq/scripts` itself. No EDA, network or client is
contacted.

## Layout

```
cases/           34 frozen input documents (+ snapshot source + invalid NaN JSON)
expected/        hand-derived expected status/exit/rules, one file per case
holdout/         4 combinations not referenced by implementation tests
sources/         short vendor mechanical facts (GCT USB4105, OMRON B3F, ISO 4762 M3)
manifest.json    input + expected SHA-256, command, args, holdout flag
results.json     last frozen-run coverage/correctness/timings (real_eda NOT RUN)
results_holdout.json  last holdout run
```

## What is frozen

Every input and expected file is frozen by SHA-256 in `manifest.json`. Editing a
case without updating the manifest makes the runner fail. `--update-hashes` is
the only way to accept changed bytes, and it must be a reviewed action. Expected
statuses/rules were written from the geometry and contract before running the
CLI; do not copy actual output into an expected file to make a failure disappear.

## Adding a case

1. add a static JSON document under `cases/` or `holdout/` (never generate it at
   run time);
2. add a hand-derived expected JSON under `expected/` (status, exit, rules);
3. add a manifest entry with the input/expected hashes, command, args and
   `holdout` flag;
4. run the suite and fix the implementation or the case geometry — do not weaken
   the expected result.

## What it proves / does not prove

It proves the CLI's contract behaviour on the frozen synthetic documents:
correct exit/status pairing, no empty-candidate-plus-pass, rule presence and
absence for the named regressions. It does **not** prove physical assembly,
electrical correctness, EDA import, manufacturing or that the synthetic
dimensions match a real product. Timings are wall-clock only and are not part of
any report identity.
