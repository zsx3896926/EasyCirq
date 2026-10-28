# Zhigou · EasyCirq Connector (EasyEDA Pro extension)

> In one sentence: **it is a local "network cable"** — it turns the EDA operations that the AI
> requests on your machine into official EasyEDA Pro API calls. Everything happens locally;
> nothing goes through the cloud.

For everyone: first-time installers, daily users, troubleshooters and developers.

> 中文版：[README.md](README.md)

---

## 1. What it is (and is not)

| Is | Is not |
|---|---|
| An extension (`.eext`) installed inside EasyEDA Pro | Not standalone software, no desktop icon |
| Translates requests from the local `zhigou` runtime into official `eda.*` API calls | Contains no AI and generates no designs |
| Connects only to the local loopback `127.0.0.1:23111-23120` | No internet, no project upload, no telemetry, no account |
| Requires you to explicitly grant **"Allow external interaction"** | Never modifies a project silently: every step needs a request from zhigou |

Three layers (easy to confuse):

```
AI client (Claude / Codex, etc.)
   └─ design-hardware Skill (design method, rules, gates)
        └─ zhigou runtime (local CLI + daemon; actually dispatches actions)
             └─ this connector (executes eda.* API calls inside EasyEDA)
                  └─ EasyEDA Pro (the canvas you see)
```

The connector only translates between the **bottom two layers**.

---

## 2. Prerequisites

- Windows 10/11 (tested), EasyEDA Pro **V4** (tested 4.1.78);
- The zhigou toolchain installed with the unified installer (default `%LOCALAPPDATA%\Zhigou`);
- Know where the `.eext` is: run `zhigou connector path`, or look at
  `%LOCALAPPDATA%\Zhigou\connector\zhigou-connector_v<version>.eext`.

---

## 3. Import (the only manual step)

> The extension **is loaded only when EasyEDA starts**; importing while it runs has no effect.

1. **Fully exit** EasyEDA Pro (not minimize; confirm the process is gone);
2. Start it again → **Settings → Extensions → Installed → Import extension**;
3. Choose `zhigou-connector_v<version>.eext`;
4. In the extension manager find **"Zhigou · EasyCirq Connector"** → open its settings/permissions →
   enable **"Allow external interaction"** (without it the connector cannot connect and reports no error);
5. **Fully exit and restart** EasyEDA Pro;
6. Open any project and run `zhigou doctor` from the command line:
   - `connector.status = connected` → success;
   - `degraded` with "connector not connected" → re-check step 4/5 (permission and restart).

> Why "external interaction": the connector talks to the local daemon through
> `eda.sys_WebSocket`, which the host blocks by default. You must allow it explicitly in the
> extension settings.

---

## 4. Daily use (you barely touch it)

- After EasyEDA Pro starts, the connector connects to the local daemon automatically; it disconnects when EDA closes;
- You just describe requirements to the AI; the AI drives `zhigou`; the connector executes invisibly;
- You do **not** need to start the connector manually every time, but the daemon must be online
  (`zhigou daemon start`, or the background service from the installer; `zhigou doctor` reports daemon status);
- With multiple EasyEDA windows open, `zhigou` will ask for `--window` or `--project` to pick the target —
  that is a guard against writing to the wrong window, not a fault.

---

## 5. Upgrade / uninstall (the upgrade flow differs from normal software)

EasyEDA identifies extensions by **UUID**: re-importing the same UUID may update the version number in
the manager while still loading old code. Therefore this connector **uses a new UUID for every release**.
The correct flow:

1. Close EasyEDA Pro;
2. Start it again → extension manager → **uninstall the old version** "Zhigou · EasyCirq Connector";
3. Import the new `.eext`;
4. Enable "Allow external interaction" again;
5. **Fully exit and restart** EDA;
6. `zhigou doctor` must show the connector version = expected version and status `connected`.

> Upgrade note: the installer / `zhigou doctor` shows the expected connector version. If it does not match,
> follow the flow above; do not just overwrite-import (it may keep old code).
>
> Uninstall: remove the extension in the extension manager. It does not touch your projects and does not
> delete zhigou.

---

## 6. Troubleshooting

| Symptom | Most likely cause | Fix |
|---|---|---|
| `zhigou doctor` shows connector not connected / windows 0 | daemon not running | `zhigou daemon start`, then retry |
| Cannot connect although the daemon is running | "External interaction" not enabled | enable it in extension settings → fully restart EDA |
| Still no connection after enabling | EDA did not really restart (process still alive) | confirm the process exited, then reopen |
| `zhigou doctor` reports a connector version mismatch | old version is loaded in EDA | uninstall old → import new → restart (see §5) |
| "Ambiguous window" errors | several EDA windows are open | use `zhigou ... --project <name>` or `--window <id>` |
| Errors like "page hidden / cannot capture" | the EDA tab is in the background, canvas not repainted | bring the EDA window to the front and retry |
| Data after an operation looks stale | runtime cache / not saved | the AI runs `save → doc reload → read back`; never trust a single return value |
| Two "Zhigou · EasyCirq Connector" entries in the manager | the old UUID was not uninstalled | uninstall the old one, keep only the current version |

Logs: `%USERPROFILE%\.zhigou\daemon.log` (connection/request records on the daemon side).

---

## 7. Security and privacy

- **Loopback only**: `127.0.0.1`, no public listener, no cloud relay;
- **No telemetry / no account**: the extension collects no usage data and requires no login;
- **Least privilege**: it calls an `eda.*` API only when a local zhigou request asks for it;
- **Auditable**: every action produces structured receipts and evidence (`zhigou` artifacts /
  `evidence`), and risky actions (clear page, delete, …) are confirm-gated in the runtime.

---

## 8. Version and compatibility

| Item | Current value |
|---|---|
| Extension name | `zhigou-connector` |
| Display name | Zhigou · EasyCirq Connector |
| Extension UUID | `9511dbc464364e48b6c9047872a82e12` (changes with every upgrade, see §5) |
| Version | `0.1.4` |
| Required service | `zhigou-agent` (this toolchain's daemon; **not** the old `easyeda-agent`) |
| Ports | `127.0.0.1:23111-23120` (overridable via the extension user config `zhigouDaemonPorts`) |
| Protocol | wire `v1` (handshake / register / context / request / response / ping / pong) |
| Host requirement | EasyEDA Pro `>= 3.2.0` (tested 4.1.78) |

---

## 9. Developers: build and release rules

```bash
npm install                                # first time
npx ts-node ./config/esbuild.prod.ts        # -> dist/index.js (version constant injected at compile time)
npx ts-node ./build/packaged.ts             # -> build/dist/zhigou-connector_v<ver>.eext
npx tsc --noEmit                            # type check
```

**Hard release rules** (problems already hit — do not repeat them):

1. **Changing code requires bumping `version` in `extension.json` AND recompiling** — the version
   constant is injected at compile time; changing only the manifest yields "new version, old code";
2. **Create a new `uuid` for every release** — EasyEDA deduplicates by UUID; re-importing the same UUID
   may keep the old payload;
3. `.eext` = zip (`extension.json` + `dist/index.js` + `images/` + license files);
4. The runtime's `runtime/internal/version/version.go` `ConnectorVersion` must be updated too,
   otherwise `zhigou doctor` reports a version mismatch;
5. After release, always smoke-test on a real host: import → authorize → restart → `zhigou doctor` +
   one `zhigou call`.

Sources: `docs/toolchain-integration/` (capability matrix, field lessons); upstream fork and license
are in `NOTICE`.

---

## 10. License

- Upstream `easyeda-agent` connector: MIT (Copyright (c) 2026 zhoushoujianwork and contributors);
- Changes in this project: Apache-2.0.
- This extension is an independently maintained fork and is not an official JLC product.
