# Zhigou 工具链安装器（安装 / 升级 / 回退 / 卸载）

本文覆盖 `distribution/` 下的统一安装体系：它把 **Skill（easycirq）+ 运行时（`zhigou.exe` 与构建标识）+ 连接器（`.eext`）** 当作一个整体来安装、升级、回退和卸载。

- 入口（人工）：`distribution/Install-Zhigou.cmd`（双击）或 `Install-Zhigou.ps1`
- 事务实现：`distribution/zhigou_install.py`（Python 3.10+，仅标准库）
- 发行构建：`distribution/build_release.py`
- 生命周期测试：`tests/test_install_lifecycle.py`
- 运行证据：`docs/toolchain-integration/evidence/installer/`

> 与旧体系的关系：`Manage-Skill.ps1` / `skill_update.py` **继续保留**，只负责"单独更新 Skill"这一条老路径，CI 的发布物契约未变。新安装器不重写它，而是复用同一套事务范式（锁 + journal + 备份 + 清单校验）。两条路径可以共存，但**不要对同一个 Skill 目录同时操作**。

---

## 1. 安全边界（硬约束，代码里逐条实现）

| 约束 | 实现方式 |
|---|---|
| 不写入用户既有 `easyeda-agent` 目录 | `guard_install_dir()` 命中 `easyeda-agent` / `easyedas_agent` / `zhoushoujianwork` 字样直接拒绝；安装器全程只**读**这些目录（`legacy` 探针） |
| 不删除旧 easyeda-agent / 旧 Skill | 安装器只删自己 `installation.json` 里记录的文件；客户端 Skill 目录只在"由本工具链创建"（存在 `.zhigou-install.json`）时才更新/删除 |
| 不覆盖 PATH 中同名命令 | 从不调用 `setx`/注册表/`PATH` 写入；`status` 只**报告** `shadowed`，不修复 |
| 不自动导入 EDA 扩展 | `.eext` 只复制到安装目录并打印导入步骤；不改 EasyEDA 的扩展状态/IndexedDB |
| 不启动/停止用户 EDA 或旧 daemon | 安装器不执行 `daemon start/stop`、不杀进程；自检只跑只读的 `zhigou doctor` |
| 不覆盖本地修改 | 升级/卸载前逐文件比对 SHA-256；有改动则拒绝并提示 `--force`（`--force` 会先备份） |

---

## 2. 安装包布局

### 2.1 构建产物（`dist/`，由 `build_release.py` 生成）

| 文件 | 说明 |
|---|---|
| `zhigou-toolchain-installer-<版本>.zip` | **给用户的一个包**：内含 bundle + 入口脚本 + 说明 + 内层 `SHA256SUMS` |
| `zhigou-toolchain-<版本>.zip` | 工具链 bundle 本体（`bundle.json` + `payload/`） |
| `toolchain-release.json` | 分离式发布清单（版本、兼容矩阵、bundle SHA-256、源提交） |
| `toolchain-provenance.json` | 构建溯源（源提交、Go 版本、node/npm 版本、每个产物 SHA-256） |
| `SHA256SUMS` | 上述全部产物的 SHA-256（与旧 Skill 产物共用一份） |
| `easycirq-*.zip`、`release.json`、`Manage-Skill.ps1/.cmd`、`skill_update.py`、`companion_update.py`、`LICENSE`、`NOTICE`、`INSTALL.md` | **旧 Skill 安装器契约，保持原样**（CI 发布物） |

### 2.2 bundle zip 内部

```
bundle.json                          # 清单：文件 SHA-256、兼容矩阵、组件、provenance
payload/bin/zhigou.exe               # 运行时
payload/bin/zhigou-version.json      # 运行时构建标识（版本/SHA/goVersion/vcsRevision）
payload/connector/<name>_<版本>.eext # 连接器扩展（不自动导入）
payload/connector/zhigou-connector.manifest.json
payload/connector/IMPORT-STEPS.md    # 人工导入步骤
payload/skill/easycirq/…      # Skill 全量文件
payload/licenses/{LICENSE,NOTICE,THIRD-PARTY-NOTICES.md,connector__LICENSE,…}
```

### 2.3 安装后目录（默认 `%LOCALAPPDATA%\Zhigou`）

```
<安装目录>/
  installation.json            # 本工具链的所有权清单：version/files{rel→sha256}/components/compat/
                               # provenance/history/backups/clientSkill/selfCheck
  bin/zhigou.exe
  bin/zhigou-version.json
  connector/zhigou-connector_v0.1.0.eext
  connector/IMPORT-STEPS.md
  connector/zhigou-connector.manifest.json
  skill/easycirq/…      # 由本工具链拥有的 Skill 副本
  licenses/…
  config/                      # 可选，用户自建；升级保留、卸载默认保留
<安装目录同级>/.zhigou-install-state/<hash>/
  update.lock  transaction.json
  backups/backup-<版本>-<时间戳>/   # 升级前的完整快照（含 _backup.json 标记）
```

> **备份为什么放在安装目录之外**：安装目录需要被整体原子替换（`os.replace`）才能做到"升级失败不留半成品"，所以状态目录必须是它的**同级目录**，不能在里面。

---

## 3. 干净机器上的最短安装流程

前置：Windows 10/11 + Python 3.10+（`py -3 --version` 能跑通）。

```powershell
# 1. 解压整个安装包目录（不要只解压里面的 zip）
Expand-Archive .\zhigou-toolchain-installer-0.2.0.zip -DestinationPath .\zhigou-setup

# 2. 双击 zhigou-setup\Install-Zhigou.cmd，选 1（安装或升级）
#    或者命令行：
.\zhigou-setup\Install-Zhigou.ps1 install

# 3. 人工把连接器装进 EasyEDA（安装器不会自动做）
#    打开安装目录下 connector\IMPORT-STEPS.md 按步骤：
#    EasyEDA Pro → 设置 → 扩展 → 已安装 → 导入扩展 → 选 .eext
#    → 完全退出 EasyEDA 并重新启动（启动时加载，无热加载）

# 4. 自检
& "$env:LOCALAPPDATA\Zhigou\bin\zhigou.exe" doctor
#    verdict=ok 表示宿主可达；degraded 表示 daemon 未起或连接器未连（不是安装失败）
```

想把 CLI 加进 PATH（可选，安装器不会改）：

```powershell
$env:PATH = "$env:LOCALAPPDATA\Zhigou\bin;$env:PATH"   # 仅当前会话
```

---

## 4. 命令参考

### 4.1 PowerShell 入口

```powershell
Install-Zhigou.ps1 <action> [参数]
```

| action | 作用 | 常用参数 |
|---|---|---|
| `menu`（默认） | 交互菜单 | — |
| `install` / `upgrade` | 安装或升级（同一条幂等路径） | `-Bundle <zip>` `-Release <json>` `-SkillClient claude\|codex\|agents` `-Force` `-Adopt` `-DryRun` `-NoSelfCheck` |
| `status` | 安装状态 + 文件自检 + PATH 影子检测 + 遗留目录观测 + 备份列表 | — |
| `verify` | 只做文件级 SHA-256 校验 | — |
| `rollback` | 回退到最近（或指定）备份 | `-To <版本>` `-Backup <目录>` |
| `uninstall` | 卸载本工具链文件 | `-Force` `-PurgeState` |
| `inspect-bundle` | 只读检查一个 bundle 的清单与哈希 | `-Bundle <zip>` |
| `recover` | 恢复中断的事务（锁/半迁移） | — |

`-InstallDir`、`-StateDir`、`-HomeDirectory` 可覆盖默认位置。

### 4.2 Python CLI（等价，便于自动化/CI）

```powershell
py -3 distribution\zhigou_install.py install  --bundle <zip> [--release <json>] [--install-dir <dir>]
py -3 distribution\zhigou_install.py status   [--install-dir <dir>]
py -3 distribution\zhigou_install.py verify   [--install-dir <dir>]
py -3 distribution\zhigou_install.py rollback [--to <版本>] [--backup <目录>]
py -3 distribution\zhigou_install.py uninstall [--force] [--purge-state]
py -3 distribution\zhigou_install.py inspect-bundle --bundle <zip>
py -3 distribution\zhigou_install.py recover
```

约定与 `easyeda` CLI 一致：**成功 JSON 走 stdout，错误 JSON 走 stderr 且退出码 2**；`status/verify` 退出码 0 不代表宿主可达，只代表文件一致。

### 4.3 环境变量（隔离与自动化）

| 变量 | 作用 |
|---|---|
| `ZHIGOU_INSTALL_DIR` | 默认安装目录 |
| `ZHIGOU_STATE_DIR` | 默认状态/备份目录（锁、journal、backups） |
| `ZHIGOU_HOME` | 客户端 home（Skill 目标与自检 HOME 覆盖） |
| `ZHIGOU_CLIENT_ROOT` | 显式 Skill 目标目录（保留给测试/高级用法） |
| `ZHIGOU_INSTALL_SKIP_SELF_CHECK=1` | 跳过安装后的 `zhigou doctor`（仅诊断，跳过不影响正确性） |

显式命令行参数 > 环境变量 > 默认值。

---

## 5. 升级与回退

### 5.1 升级时序（`install` 即 `upgrade`，一条路径）

1. 加独占锁（`update.lock`；死进程遗留的锁会被回收，活锁则报错）。
2. 解压新 bundle 到状态目录下的 `stage-*`，**逐文件核对 SHA-256**（任一处不符即中止，旧安装不受影响）。
3. 读取旧 `installation.json` 并整体校验旧目录：
   - `config/**` 视为用户配置，**升级后原样保留**（若新包不含同名文件则搬过去）；
   - 其它文件若与清单不符 → 拒绝升级并提示 `--force`（`--force` 先备份再覆盖）。
4. 版本规则：同版本同内容 → `already_current`（不产生备份）；同版本不同内容 → 报错要求升版本号；**降级 → 拒绝**，提示用 `rollback`。
5. 把旧安装整体快照到 `backups/backup-<旧版本>-pre-<新版本>/`，写 `transaction.json`。
6. 原子替换：旧目录 → `displaced-*`，`stage` → 安装目录，再整体校验新目录。
7. 任何一步异常 → 自动把 `displaced` 换回，旧版本继续可用。
8. 跑 `zhigou doctor`（可用 `--no-self-check` 跳过）：`ok` / `degraded` 都算安装成功，`unavailable`（无法执行）单独如实记录。
9. 追加 `history`（action/at/from/to/backup），清 journal。

### 5.2 回退

```powershell
.\Install-Zhigou.ps1 rollback                # 最近一次备份
.\Install-Zhigou.ps1 rollback -To 0.1.0      # 指定版本
```

- 回退是"再换一次目录"，同样走 journal；**被替换下来的版本不删除**（保留在 `rolledback-*`），便于再回退或取证。
- 没有备份时明确报错（首次安装后立刻回退会看到 `No backup available to roll back to`）。
- 回退恢复的目录也会做整体校验；`_backup.json` 标记会在恢复后移除，不计入文件清单。

### 5.3 自动回退的边界

安装器保证"**升级失败不留半成品**"（第 7 步）。它**不**保证"新版本运行一定正常"——那是 `doctor` 与后续验收的职责。`doctor` 的 `degraded` 不触发回退，因为它通常与安装无关（daemon 没起、EDA 未重启、连接器未连）。

---

## 6. 卸载

```powershell
.\Install-Zhigou.ps1 uninstall                 # 保留 config/ 与备份
.\Install-Zhigou.ps1 uninstall -PurgeState     # 连 config/ 与备份一起删
```

- 只删 `installation.json.files` 里列出的文件；**无法识别的用户文件会保留**，并让目录无法被自动删除（避免静默丢数据）。
- 默认保留 `config/`（用户设置）与状态目录里的备份；`--purge-state` 才清。
- 如果安装时用 `--skill-client` 往客户端目录复制过 Skill，卸载会删掉**它自己创建的那份**（依据 `.zhigou-install.json`）。
- 文件被改过时拒绝删除，除非 `--force`。

---

## 7. 安装后自检（doctor）语义

`zhigou doctor` 输出 JSON（stdout）+ 人读摘要（stderr），安装器把结果分四类：

| status | 含义 | 是否算安装失败 |
|---|---|---|
| `ok` | `verdict=ok`，宿主可达 | 否 |
| `degraded` | daemon 未运行 / 连接器未连接 / EDA 未重启（`verdict=degraded`，退出码可能非 0） | **否**，如实打印 |
| `unparsed` | 进程能跑但输出不是预期 JSON（例如版本不匹配） | 否，需人工看 stdout |
| `unavailable` | 无法执行（二进制缺失/被杀软锁/架构不符） | 否（但会显著提示） |

安装结果里的 `selfCheck` 字段保留 `exitCode`、`summary`（runtimeVersion/daemonPort/connectorStatus）、`stderr` 片段与 `stdoutHead`，便于排障与取证。

---

## 8. 兼容矩阵与版本规则

`bundle.json.compat` 与 `installation.json.compat` 同时记录：

```json
{"cli":"0.2.0","runtime":"0.2.0","daemon":"0.2.0","connector":"0.1.0",
 "protocol":"zhigou-agent/v1","eda":">=3.2.0","validatedEda":"4.1.78","minPython":"3.10"}
```

构建期强制校验（`build_release.py`）：
- `compat.runtime` 必须等于 bundle 版本；`compat.connector` 必须等于 `.eext` manifest 的 `version`；
- 运行时自报版本必须等于 bundle 版本（除非显式 `--toolchain-version` 且一致）；
- 连接器 UUID 必须是 32 位 hex；`.eext` 的 `extension.json` 必须含 `name/uuid/version`。

安装期强制校验（`zhigou_install.py`）：同一套规则再验一遍，并对 `components.*.path` 是否在文件清单内、清单是否越界（必须 `payload/` 前缀）做检查。

升级时 `compat` 有变化会写进 `compat.changes`（例如 `connector: 0.1.0 -> 0.2.0`），`status=changed` 但不阻断。

---

## 9. 构建与可追溯

```powershell
# 完整发行物（旧 Skill 安装器 + 工具链 bundle + installer zip）
py -3 distribution\build_release.py --output dist

# 只构建工具链；本机没有 Go 工具链时复用已构建二进制
py -3 distribution\build_release.py --output dist --toolchain-only --skip-runtime-build

# 强制从源码构建运行时（需要 Go）
py -3 distribution\build_release.py --output dist --toolchain-only

# 只构建旧 Skill 安装器（CI 契约）
py -3 distribution\build_release.py --output dist --skill-only --require-clean
```

关键开关：`--toolchain-version`、`--runtime-exe`、`--go`、`--connector-build auto|always|never`、`--connector-eext`、`--skill-dir`、`--require-clean`、`--require-toolchain`。

**连接器构建**走仓库自带 npm 流水线：

```
cd connector
npx ts-node ./config/esbuild.prod.ts     # 产出 dist/
npx ts-node ./build/packaged.ts          # 打包 build/dist/<name>_<ver>.eext
```

**记录的溯源信息**（`toolchain-provenance.json` 与 bundle 内 `provenance`）：`sourceCommit`、`sourceDirty`、`goVersion`（优先取二进制自报，其次取 `go version`）、`nodeVersion`/`npmVersion`、`runtimeVcsRevision/vcsTime/vcsModified`、`builder`、`host`、`pythonVersion`，以及 `artifacts.{bundle,runtime,connector,skill}.sha256`。

> 本机没有 `go` 时：`--skip-runtime-build`（复用 `runtime/dist/zhigou.exe`）或 `--runtime-exe`。此时 `goVersion` 仍从二进制 `doctor` 的 `runtime.goVersion` 读取，来源字段记为 `reused:<路径>`，不会伪造成"本次编译"。

---

## 10. 故障速查

| 现象 / 消息 | 原因 | 处理 |
|---|---|---|
| `Python 3.10+ required` | 没装 Python 或太旧 | 装 Python 3.10+ 后重开窗口 |
| `An install needs --bundle <zip>` | 没给安装包且目录里没有 | 把 `zhigou-toolchain-<版本>.zip` 放到脚本同目录，或 `-Bundle` 指定 |
| `Bundle archive SHA256 does not match release.json` | 包被改过/下错版本 | 重新获取安装包，别手工改 release.json |
| `Corrupt bundle payload (SHA256 mismatch)` | 包损坏 | 重新构建/重新下载 |
| `Duplicate, directory or symlink entry in bundle` | 包被恶意或错误打包 | 拒绝使用，重新构建 |
| `Unsafe package path` | 包内路径越界（`..`、盘符、Windows 保留名） | 包不可信，重新构建 |
| `Unmanaged content at <dir>; pass --adopt` | 目录非空且不是本工具链装的 | 确认后 `-Adopt`（会先备份），或换 `-InstallDir` |
| `Another install/upgrade is running (lock: …)` | 并发安装，或上次崩溃留锁 | 确认没有安装进程后 `recover` |
| `An interrupted transaction exists; run the recover action first` | 上次中途断电/被杀 | `recover` |
| `Local modifications detected; nothing was changed` | 安装目录里的文件被人改过 | 先备份改动，再 `-Force` |
| `Refusing to downgrade …; use the rollback action` | 用旧包覆盖新版本 | 要回去请 `rollback -To <版本>` |
| `No backup available to roll back to` | 只有一次安装，没产生备份 | 正常；重新安装目标版本 |
| `Cannot move … ([WinError 5]/[WinError 32])` | 文件被杀软/索引器占用 | 安装器已自动重试多次；仍失败则等几秒再试，或把安装目录加入杀软排除 |
| `Install path contains a symlink/junction` | 安装路径含 junction | 换真实目录 |
| `Refusing to install into a path that belongs to easyeda-agent` | 目标路径命中 `easyeda-agent` | 换 `-InstallDir`（默认 `%LOCALAPPDATA%\Zhigou`） |
| `uninstall … modified …` | 卸载前发现文件被改 | 备份后 `-Force` |
| doctor `degraded` | daemon 未起 / EDA 未重启 / 连接器未连 | 不是安装失败；按 `IMPORT-STEPS.md` 导入并重启 EDA，或 `zhigou daemon start` |
| `status.path.verdict = shadowed` | PATH 里有另一个 `zhigou.exe` | 安装器不改 PATH；自己调整 PATH 顺序 |

---

## 11. 中文 / 空格 / 长路径与权限

- **中文与空格路径**：全流程用 `Path`/`os.replace`，不拼命令行字符串；`install`、`upgrade`、`rollback`、`uninstall`、`status` 均在 `C:\…\安装 目录\智构 工具链` 这类路径上测过（见 §12）。
- **长路径**：Python 3.10+ 在 Windows 上使用 Unicode API；测试覆盖 ~200 字符深路径。若企业策略关闭长路径支持，建议把安装目录放在较浅层级。
- **权限**：默认装在 `%LOCALAPPDATA%`，无需管理员。装到 `C:\Program Files` 之类目录需要管理员权限，且 `os.replace` 可能被 UAC/虚拟化拦截——**不推荐**。
- **杀软/索引器**：刚写入的 20+ MB 二进制常被短暂持有，导致目录改名 `ACCESS_DENIED`；安装器对目录替换有**指数退避重试**，并把最终失败写成可操作错误。
- **junction/symlink**：安装目录、状态目录及其父链上出现链接一律拒绝（避免"以为装到 A 其实写进 B"）。
- **文件占用**（二进制正在运行）：升级会先替换目录，被占用的旧二进制会阻止改名；请先退出使用该二进制的进程（daemon 由用户决定是否停止，安装器不会代劳）。

---

## 12. 测试与证据

```powershell
# pytest（推荐）
py -3 -m pytest tests\test_install_lifecycle.py -v

# 仓库既有风格（CI 用这个）
py -3 -m unittest tests.test_install_lifecycle -v
```

当前结果：**39 passed**（本机 Windows，Python 3.13.15；`unittest` 与 `pytest` 两种入口都跑过）。

覆盖矩阵：

| 需求 | 用例 |
|---|---|
| 干净安装 | `CleanInstallTests.test_clean_install_layout_and_manifest`、`…creates_nothing_outside…` |
| 重复安装 / 幂等 | `…test_install_is_idempotent` |
| 升级 | `UpgradeRollbackTests.test_upgrade_records_history_and_backs_up`、`…reports_compat_changes` |
| 回退 | `…test_rollback_restores_previous_version`、`…by_explicit_version`、`…without_backup_is_a_clear_error` |
| 卸载 | `UninstallTests.*`（只删自有文件、拒绝改过的安装、重装干净） |
| 中文 + 空格路径 | `UnicodePathTests.test_chinese_and_space_paths_for_every_action`、`…long_deep_path` |
| 损坏包拒绝 | `CorruptBundleTests.*`（篡改 payload/错误清单/缺 manifest/路径穿越/重复条目/截断/分离清单不一致） |
| PATH 不被覆盖 | `SafetyTests.test_path_is_not_modified`、`…shadowing_is_reported_not_fixed` |
| 旧 easyeda-agent 不被改 | `SafetyTests.test_existing_easyeda_agent_dirs_are_never_modified`（哈希+ mtime 双比对）、`…install_dir_inside_easyeda_agent_is_refused` |
| 本地修改保护 / 升级失败回滚 | `TransactionTests.test_local_modification_blocks_upgrade_until_forced`、`UpgradeRollbackTests.test_failed_upgrade_leaves_previous_version_intact` |
| 锁 / 中断恢复 / 环境变量 / dry-run | `TransactionTests.*` |
| 客户端 Skill 安装 | `ClientSkillTests.*`（安装、卸载移除、未托管目录不覆盖） |
| doctor 语义 | `SelfCheckTests.*`（degraded 不算失败、无法执行不算失败、真实 bundle+真实 doctor） |

证据文件：

- `docs/toolchain-integration/evidence/installer/pytest-install-lifecycle.log` —— 完整 pytest 输出
- `docs/toolchain-integration/evidence/installer/install-lifecycle.log` —— 每个用例的 JSONL 记账（安装/校验/回退/损坏包拒绝等事件）

---

## 13. 已知限制与待决问题

1. **连接器仍需人工导入并重启 EDA**：受 EasyEDA Pro 扩展机制限制（`onStartupFinished`，无 CLI/无热加载），安装器只能把 `.eext` 放到安装目录并打印步骤。若将来必须"免 GUI 安装"，只能操作 EDA 的 IndexedDB（含 `isAllowExternalInteractions`），风险高且无官方保证——**建议维持现状**。
2. **daemon 生命周期不由安装器管理**：安装器不启动/停止 daemon；`doctor` 的 `degraded` 属正常态。是否需要 `--start-daemon` 类开关，需 Lead 决定。
3. **Skill 与客户端目录的关系**：默认只装到安装目录内的 `skill/`；写进 `~/.claude` / `~/.codex` / `~/.agents` 需要显式 `-SkillClient`。这与既有 `Manage-Skill.ps1` 的职责有重叠——**长期应二选一**（见待决问题）。
4. **发布通道未定**：安装器只信任本地安装包与可选的 `toolchain-release.json`，不做网络下载（有意为之，避免供应链问题）。若要"在线更新"，需要先定发布源与签名策略。
5. **Go 工具链缺失时无法从源码重建运行时**：本机通过 `--skip-runtime-build` 复用二进制；CI/发布机应安装 Go 以生成完整 provenance。

## 隔离安装验证（2026-10-28）

`dist-v2/zhigou-toolchain-0.2.1.zip`（由 `distribution/build_release.py --skip-runtime-build`
从当前工作树构建）在独立目录 `zhigou-isolated` 安装并验证：

- 安装退出码 0；`installation.json` 记录 561 个文件、组件 `runtime + connector + skill`；
- 隔离运行时 `zhigou 0.2.1-dev` 可执行，`zhigou connector path` 读到随包 `.eext`
  （`zhigou-connector 0.1.0`，uuid `a6e6b788…`，231,299 B）；
- 包内 skill 版本 **1.0.2**（迁移后的单一 `zhigou` 入口版本），不是旧的 1.0.1；
- 证据：`evidence/installer/isolated-install.json`。

**Windows PowerShell 5.1 编码修复**：`Install-Zhigou.ps1` 含中文提示，PS 5.1 默认按
ANSI 读取无 BOM 的 UTF-8 脚本会解析失败（`Unexpected token`）。已为脚本加 UTF-8 BOM，
`powershell -File distribution\Install-Zhigou.ps1 status` 现可正常输出 JSON。
`Install-Zhigou.cmd` 的 pwsh→powershell 回退路径随之可用。
