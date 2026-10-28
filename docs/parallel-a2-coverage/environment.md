# Environment and authorization (A2-COVERAGE)

- Date: 2026-10-28 (Asia/Shanghai)
- Operator: AI coding session (DeepSeek Harness), branch `spike/a2-eda-coverage`
- Baseline: `main @ fd4499cd3c98dc66c96bb38a703ce562e1c3dbe5` (worktree HEAD at start)
- A reference (read-only): `origin/feat/integrated-eda-toolchain @ dfa8f10d7149df435ab0c0be91edcdcb91990ce1`
- Repository: `https://github.com/zsx3896926/hardware-design-skill`

## 1. Host

| item | value |
| --- | --- |
| OS | Windows (Win32), user `jlc` |
| Python | 3.13.15 |
| Node.js | v24.20.0 |
| Git | 2.55.0.windows.5 |
| Go | **not installed** (`go version` -> command not found) |
| EDA client | EasyEDA Pro (JLCEDA Pro) **4.1.78.34f5b8d9** |

## 2. Official CLI

| item | value |
| --- | --- |
| primary path | `C:\Users\jlc\AppData\Local\Programs\LCEDA-Pro\lceda-pro.exe` |
| duplicate path | `C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe` |
| sha256 (both) | `b85458b4ae2f9fef4179772942c90ea67ce4cebf577bb38338d418ff958bd481` |
| `--help` first line | `JLCEDA Pro 4.1.78.34f5b8d9` |
| on PATH | no (`LCEDA_PRO_EXE` / `--exe` supported by the repo adapter) |

Commands exposed (verbatim, condensed from `--help`): `activate`, `open`,
`stop`, `doctor`, `session list/close/abort`, `invoke`, `functions`,
`doc api/external/format`, `--mcp stdio|http`.

Known CLI capture quirk (documented by the CLI itself): PowerShell cannot
capture this program's stdout with `$x = & lceda-pro ...` or `> file`; use a
pipe or `Start-Process -RedirectStandardOutput`. This spike used Python
`subprocess.run(capture_output=True)` instead.

## 3. `doc api` works offline

`lceda-pro doc api` needs **no** editor session and no network: it returned
388 types, 20 classes and 31 method details (receipts in
`docs/evidence/a2-coverage-2026-10-28/api/`). This is the authoritative
capability surface used by the matrix (create/save/importChanges/DRC/getGerberFile/
getPickAndPlaceFile/...).

## 4. `doctor` and session inventory

```json
{"ok":true,"value":{"endpoint":"JLCEDAProa0c9c6ce","connected":true,
 "bridgeVersion":"4.1.78.34f5b8d9","versionMatch":true,"resultChannel":true},
 "logs":[],"durationMs":58}
```

Sessions before the probe (one user window, never touched):

```json
{"sessionId":"eb818679-ca93-40ff-b816-9853a328a517","status":"alive","headless":false,
 "origin":"user","path":null,"title":"嘉立创EDA(专业版) - V4.1.78"}
```

Sessions after the probe: the same user session is still `alive`; every
`origin:"cli"` session opened by this spike is `closed`
(`sessions-before.json` / `sessions-after.json`).

## 5. Authorization and isolation

| item | decision |
| --- | --- |
| design-content write probes (W04/W05/W09-save) | **NOT AUTHORIZED** -> cells `blocked (authorization)`, no write was attempted |
| project creation | not used against the user's project tree; a **vendor sample copy** under `%TEMP%` was opened |
| user window (activate/refresh/close) | never touched; only `origin:"cli"` headless sessions were driven |
| extension install/uninstall | none performed |
| network | none (only local CLI/MCP) |
| A branch | read-only static reading; not checked out, not modified, not used as base |
| repo / PR | no merge, no release, no changes outside the allowed paths |

Write authorization was never granted in this session, so the task book's
fallback applies: deliver **offline/provisional** conclusions and mark the
write cells `BLOCKED`. No receipt in this directory was fabricated: every
JSON under `raw/` is the unedited stdout/stderr of a real CLI call.

## 6. Fixture project (disposable, in the system temp dir)

- Source: `C:\Users\jlc\Documents\LCEDA-Pro\example-projects\示例工程_快速入门.eprj2`
  (EasyEDA-shipped sample project; the source is only read, never opened or written).
- Copy opened by this spike:
  `%TEMP%\a2-spike-20261028-1050\fixture\a2spike-quickstart.eprj2`
  sha256 `824f6dcc41f6eb4918024a4d86e2b35248436b11bdad60aaa4d1693cb4d90fe0`.
- Project hash before/after the whole probe: unchanged (`project-before.json`,
  `project-after.json`), i.e. the read/check/export probes did not mutate it.
- Content used for the read probes: 1 board, 1 schematic page (`P1`),
  58 schematic components, 34 wires, 1 PCB, 2 copper layers, 17 PCB nets,
  33 PCB components.
- Cleanup: temp project stays under `%TEMP%\a2-spike-20261028-1050\`
  (not in the repo); delete that directory to clean up. Only receipts/hashes
  were copied into `docs/evidence/`.

The earlier attempt also created a throw-away project through
`eda.dmt_Project.createProject` inside the client's `APP_PROJECT_DIR`
(`C:\Users\jlc\Documents\LCEDA-Pro\projects\a2spike 20261028`). The directory
was removed immediately afterwards and is not present now; the receipt of that
attempt is kept in `attempt1/` so the evidence trail is complete.

## 7. A runtime (observed, not run)

`C:\Users\jlc\AppData\Local\Zhigou\bin\zhigou.exe` (pid file
`~\.zhigou\daemon.pid`) was running on this host during the spike, and
`~\.zhigou\daemon.log` shows a connected `zhigou` connector. This is the
operator's environment, **not our measurement**: this spike ran no `zhigou`
command. Go is absent, so the A branch cannot be rebuilt here, and the
connector only loads into GUI sessions (see below), which excludes the CLI
sessions this spike is allowed to use.

## 8. Reproduce

```powershell
# offline part (no EDA): regenerate matrix + rubric
python spike/a2-coverage/run_spike.py --offline

# official CLI static catalog refresh (no session, no network)
python spike/a2-coverage/capture_api_catalog.py --evidence-date 2026-10-28

# read-only live probe (operator-driven; needs the CLI + a temp fixture copy)
python spike/a2-coverage/probe_official.py --evidence-date 2026-10-28 --fixture <temp copy>.eprj2
```
