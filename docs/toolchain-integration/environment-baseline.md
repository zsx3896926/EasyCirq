# EasyEDA Pro + easyeda-agent 环境基线（只读勘察）

- 勘察时间：2026-10-27 21:13 – 21:30 (+08:00)
- 勘察方式：纯只读。未写入/保存/移动/删除任何 EDA 工程、文档、库；未启停 daemon 与 EasyEDA；未执行任何 place/move/apply/save/export-to-project/import 类命令。
- 原始证据目录：`evidence/env/`（47 个文件，见文末清单）
- 目的：为新建的自有工具链（zhigou toolchain）提供"必须对齐的真实基线"，并指出与之隔离时的风险点。

> **两个必须先知道的结论（与任务书假设不同）：**
> 1. `easyeda doctor` **不存在**（exit 1，stderr：`unknown command "doctor" for "easyeda"`）。v1.15.0 的健康检查命令是 `easyeda health`（JSON 到 stdout，人读摘要到 **stderr**）。新 CLI 若要做 doctor，需自行定义契约，可对齐 `health` 的 JSON 字段（见 §3.3）。
> 2. **已安装 connector 是 v1.15.0，而参考克隆 `easyeda-agent-src` 是 v1.14.0**（git tag `v1.14.0`）。参考源码**落后一个 minor**，不能作为 connector 的逐字复刻基准。

### 追加问题速查（Lead Q1/Q2/Q3）
| 问题 | 一句话答案 | 详见 |
|---|---|---|
| Q1 扩展装在哪、目录结构、启动扫描还是热加载 | 本机 ONLINE 模式下**没有磁盘目录**；本体+状态存在在线编辑器 IndexedDB（库名 `User_<teamUuid>_v6`），逻辑结构 `extension.json + dist/{index.js,gateway.mjs} + iframe/ + images/`；`onStartupFinished` ⇒ **启动加载，不支持热加载** | §2.2 / §2.3 |
| Q2 「允许外部交互」状态存在哪、字段名与值 | 同一 IndexedDB 扩展记录内，字段 **`isAllowExternalInteractions = true`**（另有 `isEnable=true`、`isInExtensionStore=false`、`isAutoUpdate=false`、`isOnlineSync=false`、`isShowAtHeaderMenu=true`）；`config.json` 与 `web.db users.preference` 中**均无**该字段 | §2.4 |
| Q3 是否存在非 GUI 安装/触发途径 | **不存在**。CLI 无 extension/ext/install 类命令；`app.js` 无 `--load-extension`/`extensionDir`/`devExtension`/`.eext` 任何字样；磁盘无扩展目录；扩展管理器仅 GUI（热键 `showExtensionsManager`）。必须人工「已安装 → 导入 `.eext`」并**完全退出重启 EasyEDA** | §8 |

---

---

## 1. EDA 宿主（lceda-pro.exe）

### 1.1 可执行文件与版本
| 项 | 值 |
|---|---|
| 路径 | `C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe` |
| 大小 / 时间 | 222,989,936 bytes / 2026-10-14 13:51:22 |
| SHA256 | `B85458B4AE2F9FEF4179772942C90EA67CE4CEBF577BB38338D418FF958BD481` |
| `FileVersion` | **4.1.78** |
| `ProductVersion` | **4.1.78** |
| `ProductName` | 嘉立创EDA(专业版) |
| `CompanyName` | 深圳嘉立创科技集团股份有限公司 |
| `OriginalFilename` | lceda-pro.exe |
| 运行时完整版本（Electron 注解） | `4.1.78.34f5b8d9`，`Electron 41.2.1-jlc-sa-win-x64.6`，`Chrome/146.0.7680.188` |
| 窗口标题 | `SkyPilot-X1 | 嘉立创EDA(专业版) - V4.1.78` |

证据：`01-lceda-pro-fileversioninfo.txt`

### 1.2 安装目录关注点
- `resources\app\app.js`（3,242,628 bytes）为 Electron 主进程包；`resources\app\package.json` / `version.txt` / `editor.ini` 同在。
- `resources\app\assets\`、`resources\app\node_modules\`。
- 顶层 `docs\`、`locales\`、`resources\`，以及 `unins000.*`（Inno Setup 卸载器）。
- 顶层 `version` 文件 24 bytes；`debug.log` 1,721 bytes（2026-10-24）。
- **重要**：对 `app.js` 全文检索 `load-extension`、`--extension`、`extensionDir`、`devExtension`、`.eext`、`sideload`、`installExtension`、`isAllowExternalInteractions` —— **全部 0 匹配**（`extension` 仅 17 次，均为 lodash/ajv/multer 等第三方库里的无关键字样）。说明 **Electron 外壳不承载任何扩展加载/安装逻辑**，扩展体系完全在渲染进程加载的在线编辑器页面（origin=`https://pro.lceda.cn`）里。

### 1.3 进程清单（2026-10-27 21:13 采样）
| PID | 进程 | 启动时间 | 角色 / 命令行要点 |
|---|---|---|---|
| 38172 | lceda-pro | 15:59:21 | **主进程**，`"C:\...\lceda-pro.exe"`，唯一有窗口标题的进程 |
| 45344 | lceda-pro | 15:59:22 | `--type=crashpad-handler`，`_version=4.1.78.34f5b8d9` |
| 47004 | lceda-pro | 15:59:22 | `--type=gpu-process --no-sandbox` |
| 35044 | lceda-pro | 15:59:22 | `--type=utility --utility-sub-type=network.mojom.NetworkService --lang=zh-CN` |
| 32676 | lceda-pro | 15:59:24 | `--type=renderer --app-path=...\resources\app --lang=zh-CN` |
| 32064 | easyeda | 2026-10-26 16:52:23 | **daemon**（见 §4） |

多个 `lceda-pro` 进程共享 user-data-dir `C:\Users\jlc\AppData\Local\LCEDA-Pro\cache.x64.3`。仅 PID 38172 有 `MainWindowTitle`，其余为空属正常（子进程）。

证据：`02-processes.txt`

### 1.4 EDA 用户数据目录（`config.json` 权威定义）
`C:\Users\jlc\Documents\LCEDA-Pro\config.json`（980 bytes，2026-10-27 10:09:23，SHA256 `58D65EE6F8AC2737B8B59FE34BF8C27D0667FC554700B862933BDF082BDC0FF7`）关键字段：

```json
{ "type": "ONLINE",
  "onlineService": "https://pro.lceda.cn",
  "logLevel": "warn", "logEnable": true,
  "APP_PROJECT_DIR": ["C:\\Users\\jlc\\Documents\\LCEDA-Pro\\projects",
                      "C:\\Users\\jlc\\Documents\\LCEDA-Pro\\example-projects"],
  "LIB_DIR": ["C:\\Users\\jlc\\Documents\\LCEDA-Pro\\libraries"],
  "ONLINE_BACKUP_DIR": "C:\\Users\\jlc\\Documents\\LCEDA-Pro\\online-projects-backup",
  "TMP_BACKUP_DIR": "C:\\Users\\jlc\\Documents\\LCEDA-Pro\\projects-recovery" }
```

- `"type": "ONLINE"` 是理解后续"扩展在哪儿"的关键：工程与扩展都以账号为中心，**本地不落扩展目录**。
- 其它：`database\web.db`（SQLite，2,146,304 bytes，工程/文档/用户元数据）、`logs\warn\YYYYMMDD.log`（日切文本日志）、`logs\editor\editor_*.db`。
- 候选目录核对：`C:\Users\jlc\AppData\Roaming\lceda-pro` **不存在**；实际存在 `C:\Users\jlc\AppData\Local\lceda-pro`（含 `cache.model.2`、`cache.x64.3`、`rc-acceptance`、`updater`）。

证据：`31-lceda-config.json.txt`

---

## 2. Connector 扩展（EDA 应用内）

### 2.1 身份（manifest 逐字）
| 字段 | 值 |
|---|---|
| `name` | **easyeda-agent-connector** |
| `uuid` | **4dae27407c1d43be98e8e210d45fe587** |
| `displayName` | **EDA Agent Connector** |
| `version`（已安装，当前） | **1.15.0** |
| `version`（参考克隆源码） | **1.14.0** |
| `publisher` | zhoushoujian |
| `engines.eda` | `~3.2.0` |
| `entry` | 已安装记录为 `../dist/index`；源码 `extension.json` 为 `./dist/index` |
| `activationEvents` | `{ "onStartupFinished": true }` |
| `license` / `homepage` | MIT / `https://github.com/zhoushoujianwork/easyeda-agent` |
| `images.logo` | `../images/logo.jpg` |
| `headerMenus` | `home` / `blank` / `sch` / `symbol` / `pcb` / `footprint` 六个上下文各有一组菜单：`EDA Agent` → `Reconnect`(`reconnect`)、`Stop`(`stopConnection`)、`Toggle Auto-Connect`(`toggleAutoConnect`)、`About...`(`about`) |

### 2.2 安装位置（**不是磁盘目录**）— 这是本次勘察最反直觉的一点
在 ONLINE 模式下，connector 的代码与安装状态**只存在于在线编辑器的 IndexedDB 存储中**，没有 `<uuid>/extension.json + dist/` 这样的落盘目录。

- 存储文件：`C:\Users\jlc\AppData\Local\LCEDA-Pro\cache.x64.3\IndexedDB\https_pro.lceda.cn_0.indexeddb.leveldb\000004.log`（613,203 bytes 采样时）
- IndexedDB 库名（含账号/团队维度）：`User_0d20f286253d4bae9d18fcc726fdf389_v6`
  - `0d20f286253d4bae9d18fcc726fdf389` 即 `project info` 返回的 `teamUuid`，说明存储按登录账号隔离。
- 扩展记录 uuid：`4dae27407c1d43be98e8e210d45fe587`；另有文档级缓存 uuid `db973d4c6587475e90efbc2f2a470a54`。

**导入 `.eext` 后的逻辑结构（记录内 `fileIndex` 原样）**：
```
extension.json
dist/            dist/index.js       dist/gateway.mjs
iframe/          iframe/index.html
images/          images/logo.png
LICENSE          README.md
```
注意：这是**记录内的逻辑路径**，不是文件系统路径；本体作为 blob 存在 IndexedDB 中。也就是说"是否存在 `dist/` 目录"的答案是——**存在 `dist/` 这一逻辑条目（含 `index.js` 与 `gateway.mjs`），但磁盘上没有对应目录可达**。

**磁盘搜索反证（全部为空）**：
- `Documents\LCEDA-Pro`、`AppData\Local\LCEDA-Pro`、`AppData\Local\lceda-pro`、`Programs\lceda-pro`、`.easyeda` —— 无 `extension`/`extensions` 目录，无 `extension.json`
- `Downloads` / `Desktop` / `Documents` / `.easyeda` —— 无任何 `*.eext`

### 2.3 加载时机：启动时扫描，**不支持运行时热加载**
证据链：
1. manifest `activationEvents.onStartupFinished = true`；
2. daemon 对"connector 落后"给出的修复指引明确要求重启宿主：`re-import the connector .eext (uninstall old in 已安装 → import new → FULLY quit & relaunch EasyEDA)`；
3. `easyeda skill --help` 原文：`The connector .eext is NOT covered here (no sideload auto-update) — the daemon logs a re-import notice when it detects a stale connector.`

⇒ 新 connector 更新必然伴随 **EasyEDA 完全退出再启动**，不存在免重启生效路径。

### 2.4 「允许外部交互 / Allow external interaction」状态在哪（Lead Q2）
- **不在**任何 JSON 配置文件里；`Documents\LCEDA-Pro\config.json` 与 `web.db` 的 `users.preference`（4,885 个扁平化键）中**都没有**该字段（仅命中无关的 `allowRename`、`allowFootprintFlipping`、热键 `showExtensionsManager`）。
- 它与扩展安装记录**同处 IndexedDB**，字段名精确为：

| 字段名 | 当前值 | 含义 |
|---|---|---|
| `isAllowExternalInteractions` | **true** | 允许外部交互（新 connector 免 GUI 安装的关键开关） |
| `isEnable` | true | 扩展启用 |
| `isShowAtHeaderMenu` | true | 顶部菜单显示 |
| `isInExtensionStore` | **false** | 旁加载（sideload），非商店安装 |
| `isAutoUpdate` | false | 不自动更新 |
| `isOnlineSync` | false | 不参与在线同步 |

同一记录还带 `fileSize`、`installationTime`。历史上该字段曾为 `false` 后改为 `true`（日志中 26 处 `isAllowExternalInteractions`，最新记录为 `true`）。

⇒ 新工具链若想"免 GUI 安装"，必须**写入/受控修改该 IndexedDB 记录**，而这是 EDA 私有存储、无公开写接口；且需 EasyEDA 未运行（LevelDB 独占锁）才能安全改写。**不建议依赖**。

证据：`34-connector-record-indexeddb.txt`

### 2.5 与参考克隆 v1.14.0 的一致性判定
| 对象 | 版本 | 判定 |
|---|---|---|
| 已安装 connector（运行时注册值 `connectorVersion`） | **1.15.0** | 现行 |
| 已安装 connector（IndexedDB manifest 记录） | 1.15.0（3 处）；残留 1.14.0（5 处旧记录） | 现行=1.15.0 |
| 参考克隆 `easyeda-agent-src` | `package.json` version **1.13.1**（仓库壳）、`extension/package.json` **1.14.0**、`git describe` = **v1.14.0**（HEAD `7cde1ae`，2026-10-17） | **落后一版** |

**结论：已安装 connector（1.15.0）≠ 参考克隆（1.14.0）。克隆只可作为"结构/协议参考"，不可作为"版本对齐基准"；其 `extension/` 目录（含 `extension.json`、`config/`、`src/`、`build/`、`scripts/`、`.edaignore`、`ws-file-server.mjs`）可用于推导构建流程（`npm run build` → `build/packaged.ts` 打 `.eext`）。**

---

## 3. CLI（`easyeda.exe`）

### 3.1 二进制
| 项 | 值 |
|---|---|
| 路径 | `C:\Users\jlc\.local\bin\easyeda.exe` |
| 大小 / 时间 | 23,393,280 bytes / 2026-10-26 16:51:19 |
| SHA256 | `35EA413C976BACB6EF44E8A2312596F4B8AF89EB9DE4F3BC03C56581C35BE40C` |
| 旧版 | `easyeda.exe.old` 22,865,920 bytes / 2026-10-24 15:03:22，SHA256 `93079A2CFC2939FF0304D7F6836C0373BB809F504B06BBE58F570AA9973E640B` |

### 3.2 版本与诊断命令的 I/O 契约（实测）
| 命令 | exit | stdout | stderr | 格式 |
|---|---|---|---|---|
| `easyeda version` | **0** | `easyeda-agent v1.15.0\n`（22 chars） | 空 | 纯文本，非 JSON |
| `easyeda --version` | **0** | 同上 | 空 | 同上 |
| `easyeda --help` | **0** | 45 行帮助 | 空 | 纯文本 |
| `easyeda doctor` | **1** | 空 | `unknown command "doctor" for "easyeda"`（39 chars） | 错误文本 |
| `easyeda daemon status` | **1** | 空 | `unknown command "status" for "easyeda daemon"` | 错误文本 |
| `easyeda health` | **0** | **JSON**（`status/found/versionGate/hostCompatibility/checks/checked`） | **人读中文摘要**（`✓ daemon …` `就绪：…`） | 双通道 |

⇒ **约定：JSON 结果走 stdout；人读诊断/就绪摘要走 stderr；错误也是 stderr + 非零退出。** 新 CLI 应对齐"stdout 可管道解析、stderr 放人类提示"。
证据：`11-cli-version.txt`、`12-cli-doctor.txt`、`13-cli-io-split-*.txt`、`40-health.txt`、`45-daemon-status.txt`

### 3.3 若新 CLI 要做 doctor：可对齐的 JSON 字段契约（来自 `easyeda health`）
顶层：`status`(str) `host`(str) `ports`(str) `found`(obj) `versionGate`(obj) `hostCompatibility`(obj) `checks`(list) `checked`(list)

- `found`：`port`(int) `service`(str) `raw{ pid, service, version, status, port, windows[], writeHealth{}, autosave[] }`
- `found.raw.windows[]`：`windowId` `connectorVersion` `easyedaVersion` `capabilities[]` `host{kind,userAgent}` `context{projectUuid,projectName,documentUuid,documentType,tabId,pageVisibility}` `connectedAt` `lastSeen` `connectorVersionOk`
- `found.raw.writeHealth.<windowId>`：`samples` `failures` `failureRate` `consecutiveFailures` `degraded` `verified`
- `found.raw.autosave[]`：`windowId` `action` `context{...}` `state` `saved` `updatedAt`
- `versionGate`：`cli` `daemon` `connectors[]` `verdict` `findings[{component,version,severity,reason}]`
- `hostCompatibility`：`baseline`(=4.0.0) `recommended`(=4.1.60) `verdict` `findings[{windowId,version,severity,reason}]`
- `checks[]`：`name` `status` `detail`；`checked[]`：`port` `status`

完整字段树：`43-health-json-contract.txt`

### 3.4 完整顶层命令面（`easyeda --help` 原文 26 条）
`actions` `api` `apply` `audit` `blocks` `board` `bom` `call` `completion` `daemon` `debug` `doc` `editor` `health` `help` `lib` `notify` `pcb` `project` `sch` `skill` `spec` `update` `version` `view` `web` `workflow`

全局 flag（所有子命令继承）：
- `--doc string`（把变更动作钉到某原理图页/PCB，切换后以 `document.current` 复核）
- `--force-stale-read string`（**deprecated**）
- `--host string`（默认 `127.0.0.1`）
- `--ports string`（默认 **`60832-60841`**）
- `--project string`（按工程名/uuid 路由，替代 `--window`）
- `--skip-version-check`（**deprecated**）
- `-v, --version`

分支级 flag：`sch` / `pcb` / `doc` / `project` 等带 `--window string`（EasyEDA window ID）。

### 3.5 任务要求的命令面（仅 help 文本，未执行写操作）
| 能力 | 命令 | 关键 flag / 备注 |
|---|---|---|
| 版本 | `easyeda version` | 无 flag |
| 健康 | `easyeda health`（= `daemon health`） | 扫描端口段 |
| 窗口/工程/文档枚举 | `easyeda project info`、`project doc`、`project find --name <> [--team <>]`、`doc ls [--project <>]`、`doc ready [uuid] [--json]`、`sch pages`、`pcb docs` | `doc ls` 输出 `TYPE/NAME/UUID`，`★`=当前；`doc ready` 明确"never saves/closes/opens/switches" |
| 保存 | `easyeda sch save`、`easyeda pcb save` | 无参；保存"active document" |
| 工程导出 | `easyeda project export --out <.epro2> --project-uuid <>`；`project export-source` | 不覆盖已存在文件 |
| 图片导出 | `easyeda sch export-image --format svg\|png\|pdf -o <out> [--ids ...] [--page ...] [--scope selection\|page\|project] [--theme ...] [--line-width ...] [--stay]`；`easyeda pcb snapshot --fit-mode board\|all\|none [--previous-sha256 <>]` | sch 侧是**真渲染**（非视口截图）；pcb 侧是画布捕获 |
| 检查/DRC | `easyeda sch drc [--json --strict --verbose]`、`sch check [--json --strict --page <> --all-pages --overlap-eps]`、`sch bridge-check`、`sch gate`；`easyeda pcb drc [--json ...]`、`pcb check`（DFM 只读）、`pcb drc-rules`、`pcb layout-lint` | `sch drc` 退出码：仅 fatal>0 才非零；`sch check` 默认 0，`--strict` 有 findings 即非零 |
| BOM | `easyeda bom export --type csv\|xlsx [--columns <json> --enrich=false --template <> --parts <> --script <>]`；`bom enrich` | 默认给 csv 就地补 LCSC C-number |
| 制造/Gerber | **UNKNOWN / 无专用命令** | 全 help 语料检索 `gerber` = 0 命中。现有最接近：`pcb export-dsn`（Specctra DSN，供外部 autorouter）、`pcb export-3d --format obj\|step --out <新目录> [--elements ... --model-mode Outfit\|Parts --auto-generate-models]`、`project export`（原生 `.epro2`）。**结论：本 baseline 上不存在 Gerber/钻孔/贴片坐标导出命令，需另行核实（可能只能走 GUI 制造输出）。** |
| 只读几何快照 | `easyeda pcb dump [--out <> --include-copper --no-silk --no-rules --no-layers --label <>]` | 一文件含器件/板框/丝印/DRC 规则/层数；`--out` 另出 `<out>.capture.json`（含 SHA256） |
| 技能维护 | `easyeda skill status` / `skill sync [--version <>]` | `skill list` 不存在（exit 1） |
| 自更新 | `easyeda update [--check] [--exit-code] [--local-dir <>]` | `--check` 只报不改；`--exit-code` 不一致退出 10 |

其它分支规模：`sch` 约 80 条子命令、`pcb` 约 110 条子命令（含 offline 规划类，`--dry-run` 默认），`lib`、`board`、`blocks`、`api`（离线 API 发现）、`actions`（typed action catalog JSON）、`call/apply`（通用逃生口/剧本回放）、`audit`（动作审计）、`view`（缩放/适配）、`web`（控制 EasyEDA Web 编辑器页）、`notify`（窗口内 toast）。

证据：`10-cli--help.txt`、`21-help-all-topcommands.txt`、`22-help-leaf-commands.txt`、`20-help-*.txt`

---

## 4. Daemon

| 项 | 值 |
|---|---|
| PID | **32064**（已确认就是 daemon，非误认） |
| 命令行 | `C:\Users\jlc\.local\bin\easyeda.exe daemon start --host 127.0.0.1 --ports 60832-60841 --autosave-debounce 3s --auto-update-skill=true` |
| 父进程 | 34804 |
| 启动时间 | 2026-10-26 16:52:23 |
| 监听 | **`127.0.0.1:60832` LISTEN**（端口段 `60832-60841` 中仅 60832 被占） |
| 活动连接 | `127.0.0.1:60832` ← `127.0.0.1:50259`（ESTABLISHED）。**50259 是 connector 一侧的临时源端口，不是服务端口**——任务书"connector 在 50259"应理解为该连接的客户端端口 |
| PID 文件 | `C:\Users\jlc\.easyeda-agent\daemon.pid` = `32064`（6 bytes，2026-10-26 16:52:23） |
| 状态目录 | `C:\Users\jlc\.easyeda-agent\` → `audit\`、`workflow\`、`daemon.log`、`daemon.pid` |
| 日志 | `daemon.log` 18,688,511 bytes（勘察时，持续增长；任务书称 ~13 MB 已过时） |
| HTTP 端点 | `listening on http://127.0.0.1:60832 (health: /health, connector: /eda, action: /action)` |

**鉴权 / token：无。** 对 `daemon.log` 全文检索 `token|auth|secret|bearer` = **0 命中**；状态目录内无 token/credential 文件；`.easyeda-agent` 仅有上述 4 项。⇒ 该 daemon 是"仅绑定 127.0.0.1、无鉴权"的本地 socket 服务，安全性依赖本地回环 + 端口段。**新工具链若同机并行，会与它争用同一端口段与同一 connector 连接——这是首要隔离风险。**

**日志格式**：每行 `easyeda-agent daemon: <事件>`，前缀行首为 ISO8601 本地时间戳的启动横幅（`=== 2026-10-24T15:05:02+08:00 background start: ... ===`）。连接生命周期事件：
```
connector connected from 127.0.0.1:<port>
connector 127.0.0.1:<port> upgraded (origin="https://pro.lceda.cn" ua="Mozilla/5.0 ... JLCEDAPro/4.1.78.34f5b8d9 ...")
handshake sent to 127.0.0.1:<port>
connector 127.0.0.1:<port> frame (<n> bytes): {"type":"register","windowId":"<uuid>","connectorV...
connector registered windowId=<uuid> version=<x.y.z>
connector LOG: lifecycle registered moduleBootstrapObserved=true activateObserved=true
```
随后主要是 `{"type":"ping","id":"hb-<n>"}` 心跳（29 bytes/条约 1s）。**帧日志含 URL 与 UA，可用于溯源，但也会无限增长（已 18.7 MB）。**

**"connector 落后"诊断样例（历史上出现过）**：
`stale connector: v1.14.0 < daemon v1.15.0 — re-import the connector .eext (uninstall old in 已安装 → import new → FULLY quit & relaunch EasyEDA). Latest .eext: https://github.com/zhoushoujianwork/easyeda-agent/releases/latest`

证据：`30-daemon-pidfile.txt`、`32-daemon-log-tail40.txt`、`33-daemon-ports.txt`

---

## 5. 版本 / 身份对照表

| 组件 | 版本 / Build | 路径 | 如何验证 | 在磁盘？ | 在运行？ |
|---|---|---|---|---|---|
| EasyEDA Pro 宿主 | **4.1.78**（build `4.1.78.34f5b8d9`，Electron `41.2.1-jlc-sa-win-x64.6`） | `...\Programs\lceda-pro\lceda-pro.exe` | `FileVersionInfo` + 进程 cmdline 注解 + 窗口标题 | ✅ | ✅ PID 38172 等 5 个 |
| CLI | **v1.15.0** | `C:\Users\jlc\.local\bin\easyeda.exe` | `easyeda version` / `--version` | ✅ 23,393,280 B | ✅ 仅以 daemon 形态 PID 32064 |
| daemon | **v1.15.0** | 同上二进制 | `/health` → `version":"v1.15.0"`；`connectorVersionOk` | ✅ | ✅ PID 32064:60832 |
| Connector 扩展 | **1.15.0** | **IndexedDB `User_0d20f286253d4bae9d18fcc726fdf389_v6`**（`...\IndexedDB\https_pro.lceda.cn_0.indexeddb.leveldb\`） | 运行时 `register` 帧 + `health.windows[0].connectorVersion=1.15.0` | ❌ 无磁盘目录 | ✅ 已注册（origin `https://pro.lceda.cn`） |
| Connector manifest 记录 | uuid `4dae27407c1d43be98e8e210d45fe587`，name `easyeda-agent-connector`，entry `../dist/index` | 同上 | 字节扫描 manifest 字段 | ❌ | — |
| 参考克隆 | **v1.14.0**（`extension/package.json` 1.14.0；仓库壳 1.13.1） | `C:\Users\jlc\work\_round6-scratch\easyeda-agent-src` | `git describe`=`v1.14.0`，HEAD `7cde1ae` 2026-10-17 | ✅ | ❌ |
| Skill（codex） | **1.15.0** | `C:\Users\jlc\.codex\skills\easyeda-agent` | `.version`=1.15.0；SKILL.md `metadata.version`=1.15.0 | ✅ | — |
| Skill（claude） | **1.15.0** | `C:\Users\jlc\.claude\skills\easyeda-agent` | 同上 | ✅ | — |
| Skill（agents） | **1.15.0** | `C:\Users\jlc\.agents\skills\easyeda-agent` | 同上 | ✅ | — |

"在磁盘 vs 在运行"的差异点仅两处：**（a）connector 无磁盘目录、只活在 IndexedDB；（b）CLI 二进制虽新，但只有 daemon 在跑，前台 CLI 是短命进程。**

`hostCompatibility`：`baseline=4.0.0`、`recommended=4.1.60`、实际 4.1.78 ⇒ `verdict=ok`（4.1.78 满足 V4 主线基线）。
`versionGate`：`cli=v1.15.0`、`daemon=v1.15.0`、`verdict=ok`。

证据：`11-cli-version.txt`、`40-health.txt`、`60-sha256-manifest.tsv`

---

## 6. 当前打开的工程 / 文档（只读枚举）

- 唯一在线宿主窗口：`windowId = 8f406ca7-ac3b-4222-a1f8-bb86a40ac24d`
  - `easyedaVersion=4.1.78`、`connectorVersion=1.15.0`、`capabilities=["schematic.v1","pcb.v1"]`、`host.kind=electron`
  - `connectedAt=2026-10-27T12:46:09Z`、`lastSeen=2026-10-27T13:16:52Z`、`connectorVersionOk=true`
  - `pageVisibility=hidden`（标签页在后台；health 的 stderr 明确提示：操作照常，**仅 PCB 画布截图需切到前台**）
- 当前工程：`friendlyName=**SkyPilot-X1**`、`name=zsx520bb/SkyPilot-X1`、`uuid=**2f08700cd4f94e6e88de521f72db8c3e**`、`teamUuid=0d20f286253d4bae9d18fcc726fdf389`、描述 "Quadcopter flight controller + 4-in-1 ESC, 6S, STM32G474, ICM-42688-P, DPS310"
- 当前文档（active，`mutationContextAvailable=true`）：`documentUuid=**9d5b9d544e2a1c5b**`、`documentType=**schematic**`、`tabId=9d5b9d544e2a1c5b@2f08700cd4f94e6e88de521f72db8c3e`、`pageVisibility=hidden`
- 该工程全部可打开文档（`easyeda doc ls`，10 个）：

| 类型 | 名称 | UUID | 当前 |
|---|---|---|---|
| pcb | PCB1 | `46568562813744d8` | |
| schematic | P1 | `d088dc5fba4d38e2` | |
| schematic | P2 | `e09af7471397f380` | |
| schematic | **P3** | **`9d5b9d544e2a1c5b`** | ★ |
| schematic | P4 | `a3fa3a84cb1d32f4` | |
| schematic | P5 | `c66bac8645e54965` | |
| schematic | P6 | `267fab80bfb4688b` | |
| schematic | P7 | `374a3594f9a0d3f7` | |
| schematic | P8 | `c695bd9dba61d52c` | |
| schematic | P9 | `d97ff5811deff1ad` | |

- autosave 痕迹（`health.found.raw.autosave[]`）：`windowId=263d9359-…`、`action=schematic.save`、`state=saved`、`saved=true`、`documentUuid=267fab80bfb4688b`（=P6）、`updatedAt=2026-10-27T12:20:40Z`。注意该 windowId 与当前活动窗口**不同**（历史窗口），说明 autosave 记录跨窗口留存。
- `doc ls` 另有 9 个原理图页只列出 P1–P9，与 `windows[0].context` 一致；**未发现第二个工程窗口**。

**宿主可达性结论：可达。** `easyeda health` → `status=found`、`verdict=ok`、`writeHealth.degraded=false`、`failures=0`（20 samples）。新工具链必须绑定的标识符：`windowId`（会漂移，建议改用 `--project` 路由）、`projectUuid`、`documentUuid`、`documentType`（`schematic` / `pcb`）、`tabId`（`<documentUuid>@<projectUuid>`）。

证据：`40-health.txt`、`41-project-info.txt`、`42-doc-ls.txt`、`44-open-documents.tsv`、`43-health-json-contract.txt`

---

## 7. 客户端 / AI 集成点（skill 目录）

| 路径 | 存在 | `.version` | SKILL.md `metadata.version` | SKILL.md SHA256 |
|---|---|---|---|---|
| `C:\Users\jlc\.codex\skills\easyeda-agent` | ✅ | `1.15.0` | `1.15.0` | `39894D33…713D42` |
| `C:\Users\jlc\.claude\skills\easyeda-agent` | ✅ | `1.15.0` | `1.15.0` | 同上（三份完全一致） |
| `C:\Users\jlc\.agents\skills\easyeda-agent` | ✅ | `1.15.0` | `1.15.0` | 同上 |

- SKILL.md frontmatter：`name: easyeda-agent`、`license: MIT`、`metadata.author: zhoushoujianwork`、`metadata.version: "1.15.0"`、`metadata.homepage`。
- 结构：`SKILL.md`、`LICENSE`、`agents/openai.yaml`、`library/modules/*.json`、`references/*.md|json`（含 `environment-setup.md`、`design-flow.md`、`pcb-*.md`、`schematic-*.md`、`fab-rules-jlcpcb.json` 等）、`references/examples/**`、`scripts/*.py|js|sh`。
- **安装/更新方式**：由 daemon 启动时同步——`easyeda skill --help`：`The daemon syncs installed Skill dirs to its own version on startup`，daemon 命令行带 `--auto-update-skill=true`；另有 `easyeda skill status` / `skill sync [--version X]`。三目录同版 1.15.0、同哈希，印证"一次同步、多客户端分发"。
- 同级目录另见 `design-hardware`（`.claude`、`.agents` 下各有，`.codex` 下无），说明该机器还有第二个相关 skill 在分发，新工具链命名时应避让 `easyeda-agent` 与 `design-hardware`。
- `C:\Users\jlc\.codex\skills\.system` 存在（codex 内建）。

**未修改、未删除任何 skill 文件。**

证据：`50-skill-status.txt`、`60-sha256-manifest.tsv`

---

## 8. 无 GUI 安装/触发途径评估（Lead Q3）

### 8.1 CLI 侧：**没有任何 extension/ext/install/import 命令**
- 顶层 26 条命令中不存在 `extension` / `ext` / `install` / `import`（对照 §3.4 全表）。
- 唯一带 import 语义的是 `easyeda project import`（**工程**导入，`@beta importer; never overwrites`），与扩展无关。
- `easyeda skill sync` 只同步 **skill 目录**，帮助文本显式排除 connector：`The connector .eext is NOT covered here (no sideload auto-update)`。
- `easyeda update`（CLI/技能自更新）虽会检查 connector 兼容性（`--check` 只报不改），但不负责安装 `.eext`。

### 8.2 EDA 侧：**没有开发模式扩展目录、没有 `--load-extension`**
- `lceda-pro.exe` 启动参数中与扩展相关者：无。实测主进程 cmdline 仅 `"...\lceda-pro.exe"`；子进程为 crashpad/gpu/utility/renderer（含 `--dump-mode=partial`、`--user-data-dir=...`），无任何 extension 相关开关。
- `resources\app\app.js` 全文检索 `load-extension`、`--extension`、`extensionDir`、`extensionsDir`、`devExtension`、`.eext`、`sideload`、`installExtension` = **0 匹配** ⇒ Electron 外壳不读扩展目录。
- 磁盘上不存在 `extension`/`extensions` 目录（五处候选根全部否认，见 §2.2）。
- 扩展管理器只能通过 UI 打开：快捷键配置里存在 `menuHotkeyCfg.showExtensionsManager`（`hotkeyCmd=showExtensionsManager`）—— 即"扩展管理器"是一个 GUI 动作。

### 8.3 结论（明确写出）
> **在本机当前配置（`config.json: "type": "ONLINE"`）下，connector 的安装/更新没有非 GUI 路径。必须由人工在 EasyEDA 的「已安装」/扩展管理器里"导入 `.eext`"，随后完全退出并重新启动 EasyEDA 才生效（`onStartupFinished` + daemon 的 re-import 指引双重证据）。** 唯一"类脚本"的替代是直接改写在线编辑器的 IndexedDB 记录（含 `isAllowExternalInteractions`），但那属于 EDA 私有存储、需在 EasyEDA 未运行（LevelDB 锁）时操作、且无任何官方保证——**不构成可依赖的自动化安装通道**。

---

## 9. 对"隔离的自有工具链"的 Top 风险

1. **端口段与 daemon 单例冲突（最高）**：现有 daemon 固定 `60832-60841` + `daemon.pid` + connector 单连接（`/eda`）。新工具链若沿用同段/同 pid 文件，会抢端口或误认别人 daemon；若另起 daemon，则 EasyEDA 里的**同一个 connector 只能连一个 daemon**，两者必然互踢。⇒ 新链路必须使用独立端口段、独立状态目录、独立 connector uuid/名称，并明确"同机同宿主同一时刻只允许一条 agent 链路"的互斥策略。
2. **connector 与 CLI 版本漂移 + 无法自动安装**：已安装 connector 1.15.0，参考源码 1.14.0；`.eext` 无 CLI 安装通道，且不支持热加载，每次升级都要"卸载→导入→整机重启 EasyEDA"。自研 connector 必须自带版本自检与"落后即明示"的降级策略，否则会陷入 `stale connector` 静默不可用。另注意 `engines.eda: ~3.2.0` 与实际 API 面 `schematic.v1/pcb.v1` 的兼容窗口。
3. **页面后台态 / 文档焦点竞态**：当前 `pageVisibility=hidden`，而 `pcb snapshot`（画布截图）依赖前台，`pcb dump` 的板框读取也"requires the PCB to be the FOREGROUND document（否则返回 null 并记 `partial[]`）"。`windowId` 已多次漂移（日志中有 6 个不同 windowId）、autosave 记录指向历史窗口 ⇒ 新链路必须以 `projectUuid`/`documentUuid` 为锚、以 `doc ready`（不导航）做前置校验，并把 `partial/unknown` 与"空"严格区分。

其它风险（次要）：`daemon.log` 无上限增长（已 18.7 MB）与 ping 帧刷屏；全局 `--force-stale-read`、`--skip-version-check` 已 deprecated，新 CLI 不应复制这两条语义；Gerber/制造导出在 baseline 上缺失（见 §3.5），若新链路承诺制造产物需另行验证 GUI 路径。

---

## 10. UNKNOWN / 未取到项（含尝试命令与结果）

| 项 | 尝试 | 结果 |
|---|---|---|
| `easyeda doctor` | `easyeda doctor` / `--help` | **不存在**，exit 1，`unknown command "doctor" for "easyeda"` |
| `easyeda daemon status` | `easyeda daemon status` | **不存在**，exit 1（daemon 仅有 `health/start/stop/restart`） |
| `easyeda skill list` | `easyeda skill list` | **不存在**，exit 1（仅有 `status`/`sync`） |
| Gerber / 钻孔 / 贴片坐标导出命令 | 全 help 语料检索 `gerber`、`manufactur*`、`fabricat*` | **0 命中**，判定为不存在；未执行任何导出命令（写操作，按约束跳过） |
| connector 的 `dist/index.js`、`gateway.mjs` 字节内容与哈希 | 目标文件在磁盘不可达（仅 IndexedDB blob） | **UNKNOWN**；只能给出 manifest 与 fileIndex 逻辑结构 |
| connector 记录的 `fileSize` / `installationTime` 精确值 | IndexedDB 记录二进制编码未解码 | **UNKNOWN**（字段存在，值未解出） |
| `isEnable` 精确布尔值 | 字段名匹配但相邻字节解析未命中 | 记为"存在，值未逐字节确认"；`isShowAtHeaderMenu/isAllowExternalInteractions/isInExtensionStore/isAutoUpdate` 已确认 |
| EDA 侧扩展安装事件日志（证明"导入时刻"） | 检索 `Documents\LCEDA-Pro\logs\warn\20261027.log` 的 `extension|eext|easyeda-agent` | **0 命中**，EDA 自身 warn 日志不记录扩展安装 |
| `easyeda update --check` 的实际网络结果 | 未执行 | 避免外网 GitHub 查询与潜在副作用；`--check` 语义仅取自 help |
| 全盘 `*.eext` | `glob **/*.eext`（C:\Users\jlc） | 工具报错 `拒绝访问 (os error 5)` on `...\Temp\WinSAT`；改用 Downloads/Desktop/Documents/.easyeda 定向搜索，均无 |
| 第二个 EasyEDA 工程窗口 | `easyeda health`（windows[] 仅 1 条）、`doc ls` | 仅 1 窗口；若需更强证据需 GUI 侧确认 |

---

## 11. 证据清单（`evidence/env/`）

| 文件 | 内容 |
|---|---|
| `01-lceda-pro-fileversioninfo.txt` | lceda-pro.exe 完整 `FileVersionInfo` |
| `02-processes.txt` | Get-Process + CIM Win32_Process（含 cmdline、启动时间、窗口标题） |
| `10-cli--help.txt` | `easyeda --help` 全文（26 命令 + 全局 flag） |
| `11-cli-version.txt` | `easyeda version`（`easyeda-agent v1.15.0`） |
| `12-cli-doctor.txt` | `easyeda doctor` 失败证据（exit 1） |
| `13-cli-io-split-version.txt` / `13-cli-io-split-doctor.txt` | stdout/stderr 分离 + 退出码（`version`/`--version` 均已验证，输出一致故合并为一份） |
| `20-help-<cmd>.txt` ×25 | 各顶层子命令 help（含 `daemon`/`health`/`project`/`doc`/`sch`/`pcb`/`bom`/`skill`/`update`…） |
| `21-help-all-topcommands.txt` | 25 个顶层 help 合并语料 |
| `22-help-leaf-commands.txt` | 23 个叶子命令 help（save / export-image / drc / check / netlist / pages / snapshot / dump / export-3d / export-dsn / bom export / project export / find / doc ready / daemon status 等） |
| `30-daemon-pidfile.txt` | daemon.pid 内容 |
| `31-lceda-config.json.txt` | EDA `config.json` 副本（只读拷贝） |
| `32-daemon-log-tail40.txt` | daemon.log 末 40 行（ping 心跳格式） |
| `33-daemon-ports.txt` | PID 32064 的 TCP 连接 + 端口段 LISTEN 扫描 |
| `34-connector-record-indexeddb.txt` | **connector 安装记录解码**（manifest、fileIndex、`isAllowExternalInteractions` 等） |
| `40-health.txt` | `easyeda health` 原始 stdout(JSON)+stderr(中文摘要)+exit |
| `41-project-info.txt` | `easyeda project info`（SkyPilot-X1 全字段） |
| `42-doc-ls.txt` | `easyeda doc ls`（10 个文档，★=P3） |
| `43-health-json-contract.txt` | health JSON 字段树（新 CLI doctor 契约参考） |
| `44-open-documents.tsv` | 打开文档表（机器可读） |
| `45-daemon-status.txt` | `easyeda daemon status` 不存在证据 |
| `50-skill-status.txt` | `easyeda skill status` 输出 |
| `60-sha256-manifest.tsv` | 8 个关键文件的 SHA256/大小/时间（daemon.log 因被占用未取哈希） |

### 复现命令（全部只读）
```powershell
& 'C:\Users\jlc\.local\bin\easyeda.exe' --help
& 'C:\Users\jlc\.local\bin\easyeda.exe' version
& 'C:\Users\jlc\.local\bin\easyeda.exe' health          # stdout=JSON, stderr=摘要
& 'C:\Users\jlc\.local\bin\easyeda.exe' project info
& 'C:\Users\jlc\.local\bin\easyeda.exe' doc ls
Get-CimInstance Win32_Process -Filter "Name LIKE '%lceda%' OR Name LIKE '%easyeda%'" |
  Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine
Get-NetTCPConnection -OwningProcess 32064 | Select-Object LocalAddress,LocalPort,RemotePort,State
Get-Content 'C:\Users\jlc\.easyeda-agent\daemon.pid'
Get-Content 'C:\Users\jlc\.easyeda-agent\daemon.log' -Tail 40
```
