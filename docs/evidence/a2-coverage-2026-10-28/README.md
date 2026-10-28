# Evidence: A2 coverage spike (2026-10-28)

- Time: 2026-10-28 10:48-11:5x Asia/Shanghai
- Operator: AI coding session (DeepSeek Harness), branch `spike/a2-eda-coverage`
- OS: Windows (user `jlc`); Python 3.13.15; Node v24.20.0; Git 2.55.0
- EDA: JLCEDA Pro **4.1.78.34f5b8d9**, CLI
  `C:\Users\jlc\AppData\Local\Programs\LCEDA-Pro\lceda-pro.exe`
  (sha256 `b85458b4...`)
- A reference: `origin/feat/integrated-eda-toolchain @ dfa8f10d...` (read-only)
- Fixture: copy of the EDA-shipped sample project
  `示例工程_快速入门.eprj2` under `%TEMP%\a2-spike-20261028-1050\fixture\`,
  sha256 `824f6dcc41f6eb4918024a4d86e2b35248436b11bdad60aaa4d1693cb4d90fe0`
- Authorization: **no design-content write authorization**. No schematic/PCB
  write and no `save` was attempted; W04/W05/W09-save are `blocked`.
  The only mutation this run caused was a temporary `createProject` (name
  `a2spike 20261028`) in the client's APP_PROJECT_DIR, removed immediately
  (receipt in `attempt1/`; directory absent now).

## Files

| path | content |
| --- | --- |
| `raw/*.stdout.json` | unedited stdout receipts of every CLI call |
| `raw/*.stderr.txt` | stderr when non-empty |
| `raw/mcp-transcript.jsonl` | MCP stdio JSON-RPC transcript |
| `api/` | offline `doc api` receipts + `index.json` (sha256 per file) |
| `probe-run.json` | run summary: steps, argv, exit codes, durations, findings |
| `attempt1/` | first attempt (raced project loading); kept per "do not overwrite failures" |
| `W01-official.json` .. `W11-a.json` | per-workflow cells (schema `zhigou.a2-coverage.workflow-cell/v1`) |
| `mcp-tools.json` | MCP initialize/tools list/tools call result |
| `artifacts/` | real exports: netlist, BOM csv, page PNG, Gerber zip, pick-and-place csv |
| `project-before.json` / `project-after.json` | project tree + per-file sha256 (unchanged) |
| `sessions-before.json` / `sessions-after.json` | one user session before and after, untouched |
| `extensions-headless.json` | CLI-opened session sees 0 extensions |
| `a-self-evidence/` | copies of A's own claims + `SHA256SUMS.txt`; **not our measurements** |

## Reading order

1. `../../parallel-a2-coverage/coverage-matrix.md`
2. `probe-run.json` (facts)
3. `raw/` (provenance)

## NOT RUN

Write probes (W04/W05/W09-save, write batching), `--mcp http`,
`doc external`/`doc format`, library/3D/panel surfaces, PCB geometry dumps,
A build/run, any network call. See `../../parallel-a2-coverage/report.md` §4.
