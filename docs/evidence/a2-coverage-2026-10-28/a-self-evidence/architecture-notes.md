# A reference notes (read-only, not our measurement)

Source: `origin/feat/integrated-eda-toolchain` @ `dfa8f10d7149df435ab0c0be91edcdcb91990ce1`.
These files are **A's own claims** copied here for citation. They are not receipts
produced by this spike; no A command was executed against the host (see the
isolation notes in `docs/parallel-a-coverage/environment.md`).

## Copied files and why

`SHA256SUMS.txt` records sha256 over **LF-normalised** bytes, so a Windows CRLF
checkout and Linux CI produce the same digests (`hash_self_evidence.py`
regenerates it).

| file | taken from | what it supports |
| --- | --- | --- |
| `actions.json` | `docs/toolchain-integration/evidence/m1/actions.json` | 181 typed actions, 9 domains, `mutates`/`needsWindow` flags |
| `capabilities.json` | `docs/toolchain-integration/evidence/m1/capabilities.json` | 0 supported / 19 unknown / 5 unsupported when the connector is absent |
| `doctor.json` | `docs/toolchain-integration/evidence/m1/doctor.json` | A's M1 doctor output (degraded, connector disconnected) |
| `acceptance-README.md` | `docs/toolchain-integration/evidence/acceptance/README.md` | how A records PASS/FAIL/NOT RUN/BLOCKED |
| `task-status.md` | `docs/toolchain-integration/task-status.md` | M0-M5 status, connector import step, later self-claimed M2-M4 PASS |
| `cli-help/INDEX.txt` | `docs/toolchain-integration/evidence/acceptance/cli-help/INDEX.txt` | A's captured `zhigou <cmd> --help` index |

## Facts extracted from the A branch (static reading)

- `runtime/` = 1008 tracked files, `connector/` = 122, `protocol/` = 13; the PR adds
  about 1,700 files in total (task book background).
- Runtime is a Go fork of `easyeda-agent v1.15.0` (MIT) rebranded to `zhigou`; the
  connector is a TypeScript `.eext` fork loaded at EDA startup only.
- 181 typed actions: `pcb` 85, `schematic` 41, `library` 22, `board` 10,
  `document` 9, `project` 7, `system` 3, `artifact` 3, `debug` 1.
- 192 CLI command entries; daemon on `127.0.0.1:23111-23120`; state dir `~/.zhigou`.
- Export surface is only 3 actions (`schematic.export.netlist|bom|image`); the
  capability matrix itself reports `gerber.export`, `drill.export`, `cpl.export`,
  `archive.backup`, `length.tuning` as **unsupported**.
- A has no MCP server. Its contract is a WebSocket protocol with stable error codes.
- A's own M1 acceptance matrix marks 19/124 status units `BLOCKED` (connector not
  imported) and 61 `NOT RUN`; `runtime-go-test.log` has 40 failing cases (upstream
  Windows environment failures, 0 new regressions per A's own diff).
- The task-status file later records that the operator imported the connector by
  hand (2026-10-27 22:25) and that M2-M4 were re-run; those are A's self-evidence.

## Why this spike did not run A

1. No Go toolchain on this host (task book section 12 forbids installing one), so
   the A branch cannot be built here.
2. The A connector lives inside the user's GUI session. Every editor session this
   spike opened is `origin:"cli"` and reports **0 installed extensions**
   (`extensions-headless.json`), so A cannot even see a window this spike owns.
   Running A would necessarily drive the user's window, which task book section 4.2
   forbids.
3. Design-content writes were not authorized, so the A-side cells stay `static`.
