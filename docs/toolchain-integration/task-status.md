# 工具链整合任务状态（M0–M5）

> 本文件是"智构自有 EDA 工具链整合开发"的**当前真源**：基线、实施清单、阶段状态、
> 关键路径与依赖、阻塞。每阶段结束更新；历史细节留在 `docs/toolchain-integration/evidence/`。
>
> 最后更新：2026-10-27 22:45（**M1 完成、M2 真机通过**：自有连接器已在 EasyEDA Pro 4.1.78 内握手，读写—保存—重开—回读链实测通过；M3/M4 继续）

## 0. 基线（现场核对结果，非任务书推测）

| 项 | 实测值 | 证据 |
| --- | --- | --- |
| 仓库 | `C:\Users\jlc\work\hardware-design-skill`（origin: github.com/zsx3896926/hardware-design-skill） | `git remote -v` |
| 基线提交 | `origin/main` = `9a951ed`（2026-10-27 15:03） | `git worktree add ... origin/main` |
| 开发分支/工作树 | `feat/integrated-eda-toolchain` @ `C:\Users\jlc\work\zhigou-toolchain` | 本文件同级 |
| 用户级规则 | `C:\Users\jlc\.codex\AGENTS.md`（139 行，含"实现→构建→真实路径→证据→修复→重跑"要求） | 已读 |
| EasyEDA Pro | **4.1.78**（build 4.1.78.34f5b8d9，Electron 41.2.1-jlc-sa） | `environment-baseline.md` |
| 已装连接器 | 上游 `easyeda-agent-connector` **1.15.0**（uuid `4dae27407c1d43be98e8e210d45fe587`） | `environment-baseline.md` |
| 连接器加载方式 | `onStartupFinished` → **启动加载，不能热加载**；安装在 EDA 的 IndexedDB（无磁盘扩展目录） | `environment-baseline.md` §3/§5 |
| 旧 daemon | pid 32064，`127.0.0.1:60832`，无 token | `evidence/m1/listening-ports.json` |
| 上游源码 | github.com/zhoushoujianwork/easyeda-agent，**tag v1.15.0 / commit d93d3dd**（2026-10-24） | `third_party/easyeda-agent/UPSTREAM.json` |
| 工具链 | Go 1.27.3（新装 `C:\Users\jlc\.local\go\bin`）、Node 24.20 / npm 11.19、Python 3.13.15 | 本机实测 |

**与任务书历史背景的差异（必须按实测走）**：任务书示例端口 `64832` 与早期草稿作废；
本实现统一为 **23111–23120（0x5A47–0x5A50）**。上游只有一个发布标签 `v1.14.0` 在旧克隆里，
远端实际最新为 `v1.15.0`，且本机已装连接器就是 1.15.0，因此 vendoring 基线固定为 v1.15.0。

## 1. 阶段状态

| 阶段 | 状态 | 产物 | 证据 |
| --- | --- | --- | --- |
| **M0** 环境/源码/许可/冲突/能力调查 | **完成**（除真机 API 探测） | `environment-baseline.md`、`upstream-analysis.md`、`rule-conflicts.md`、`architecture.md`、`capability-matrix.md`、`third_party/`、`runtime/PROVENANCE.md`、`protocol/` | `evidence/env/`（47 文件）、`evidence/upstream/`（9 文件）、`evidence/skill-audit/`（4 文件）、`evidence/m1/vendor-verify.txt` |
| **M1** 自有 CLI/daemon/Connector 构建 + 隔离安装 | **完成**（构建、隔离启动、诊断、安装/升级/回退、Skill 单入口迁移均实测）；**连接器真实握手 BLOCKED**（需 EDA 内人工导入） | `runtime/`（构建成功，`zhigou.exe` 0.2.0-dev）、`connector/`（`.eext` 231 KB）、`protocol/schemas/`、`distribution/`（统一安装器）、`design-hardware/`（已迁移到 `zhigou`） | `evidence/m1/*`、`evidence/installer/*`、`evidence/skill-migration/*`、`evidence/runtime-go-test.log`、`evidence/test-failure-diff.txt` |
| **M2** 独立工程 读取→移动一件→保存→重开→回读 | **PASS（真机）** | 独立新工程 `zhigou-integrated-dual-button-led-20261027`（P1），R1/D1 放置 → D1 +40 raw 移动 → save(saved:true) → close/reopen → 新鲜回读 D1 x=640、R1 不变、primitiveId/device 身份不变、pin-net 不变 | `evidence/m2/summary.json` 及同目录原始 JSON/日志 |
| **M3** SCH/PCB 读写、批量、检查导出 | **PASS（原理图/PCB 同步/检查/导出真机）** | 9 器件双通道 LED 小板原理图：7 网全部逐脚一致、0 浮空脚、原生 DRC 0 违规、BOM/SVG/PNG 导出；PCB 同步 9 footprint 并经保存+重开+新鲜回读；PCB DRC 因未布局布线而失败（如实记录） | `evidence/m4/summary.json` 及同目录原始响应 |
| **M4** 完整小板 + 局部修改 + 备份恢复 + 统一安装升级回退 | **核心链 PASS**：安装/升级/回退 PASS；原理图+PCB 同步、布局 100/100、官方布线 6/6、双层 GND 铺铜、新鲜 PCB DRC **0 违规**、**局部改板 2mm PASS（范围外变化 0）**；**原生归档恢复演练、制造文件导出、DFM 剩余 5 警告 = NOT RUN/未清** | `distribution/`、`tools/zhigou_board_*.py`、`tools/zhigou_pcb_layout.py`、`tools/zhigou_pcb_edit_2mm.py` | `evidence/installer/`、`evidence/m4/`、`evidence/m4/pcb/` |
| **M5** 独立审查/反例/最终候选重跑/提交 PR | **进行中** | 本文件 + PR | 见 §5 |

## 2. 已完成的关键实现

1. **运行时来源可复现**：`runtime/` = 上游 v1.15.0 源码 + `distribution/rebrand_runtime.py`
   （机械重命名）+ §4 列出的 8 处实质修改；`distribution/verify_vendor.py` 从上游归档
   重新推导并逐文件比对 → **PASS**（`evidence/m1/vendor-verify.txt`）。
2. **隔离**：服务名 `zhigou-agent`、端口 23111–23120、状态目录 `~/.zhigou`、产物
   `<proj>/.zhigou/artifacts`、env 前缀 `ZHIGOU_`、扩展 uuid `a6e6b788…`。实测新旧 daemon
   同时监听、互不影响。
3. **统一诊断入口**：`zhigou doctor`（磁盘 vs 运行分离、legacy 检测 `used:false`、
   pid 文件不一致报警、verdict ok/degraded/blocked、nextSteps）。
4. **能力协商**：`zhigou capabilities` 逐项 supported/unsupported/unknown + 原因 + 模式 +
   回读 + 全板影响；无连接器时 19 项 unknown、5 项 unsupported（Gerber/钻孔/CPL/归档/等长）。
5. **连接器交付**：自有 uuid/名称/端口/配置键；打包剔除上游演示媒体与上游 CHANGELOG
   （3.1 MB → 231 KB），附 `LICENSE` + `NOTICE`（含内嵌 Apache-2.0 组件说明）。
6. **关闭上游自更新路径**：`--auto-update-skill` 默认 false、不注册上游 `update` 命令；
   升级/回退归 `distribution/`。技能数据资产（standard-parts/orientation/sheet-templates/
   bom-enrich.py）改为从自有 `design-hardware/` 解析。
7. **契约落盘**：`protocol/README.md` + 7 个 JSON Schema + wire version/服务标识常量。

## 3. 关键路径与依赖

```
[已完成] 环境/上游/许可/冲突调查
   └─> [已完成] vendoring + 重命名 + 构建 + 单元测试
         └─> [已完成] 隔离 daemon + doctor/capabilities/connector 子命令
               └─> [BLOCKED] 用户在 EasyEDA 内导入自有 .eext + 允许外部交互 + 重启 EDA
                     └─> M2 读取→移动→保存→重开→回读
                           └─> M3 批量/检查/导出/compose/反馈
                                 └─> M4 小板全链 + 局部改板 + 备份恢复演练
                                       └─> M5 独立审查 → 提交推送 → PR
[并行] distribution/ 安装升级回退（不依赖真机）
[并行] design-hardware Skill 迁移到 zhigou 单入口（不依赖真机）
```

## 4. 当前唯一硬阻塞（已解除，保留记录）

**已于 2026-10-27 22:25 由用户完成导入**：`zhigou doctor` 显示 `connector connected (1 window, zhigou-connector 0.1.0)`、`verdict: ok`，
`zhigou health` 报告 EasyEDA Pro 4.1.78 与 `capabilities: schematic.v1, pcb.v1`。以下步骤保留作重装/排障参考。

最小所需动作（一次，约 1 分钟）：

1. 关闭所有 EasyEDA Pro 窗口；
2. 打开 EasyEDA Pro →「设置 / 扩展」→「导入扩展」→ 选择
   `C:\Users\jlc\work\zhigou-toolchain\connector\build\dist\zhigou-connector_v0.1.0.eext`
   （或安装后的 `zhigou connector path` 输出路径）；
3. 扩展管理器 → **Zhigou EDA Connector** → 允许「外部交互 / Allow external interaction」；
4. 重启 EasyEDA Pro，打开要操作的工程；
5. 运行 `zhigou doctor`，确认 `connector.status=connected`、`connectorVersion=0.1.0`。

完成后的自动化验证脚本已就绪（见 `docs/toolchain-integration/acceptance-matrix.md`
与 `runtime/` 的 doctor/capabilities 输出），无需再依赖任何人工步骤。
**旧 `easyeda-agent` 连接器与旧 daemon 不需要卸载**：端口/服务名/扩展 uuid 全部隔离。

## 4.1 回归基线：与"未修改上游"对比，没有新增失败

运行方式：同一台机器、同一 Go 1.27.3、同一 Windows 环境，
`go test ./... -count=1`，分别对

* 未修改的上游 v1.15.0 归档（`_upstream/v1.15.0`）→ `evidence/upstream-v1.15.0-go-test.log`
* 本仓库 `runtime/`（重命名 + 实质修改后）→ `evidence/runtime-go-test.log`

| 指标 | 上游 v1.15.0 | 本仓库 runtime |
| --- | ---: | ---: |
| 失败用例总数 | 41 | **40** |
| 新增失败（回归） | — | **0** |
| 相对上游修好的 | — | 1（`TestResolveEnrichScriptPriority/5…`） |

**结论**：剩余 40 个失败全部是**上游在 Windows 上既有的环境类失败**（符号链接/路径别名
权限、`os.Chmod` 在 Windows 无 exec 位、原子 rename 权限、ProjectDrawings 渲染器路径别名、
`StripArtifactNesting` 根路径清理等），分布在 `internal/app`、`internal/daemon`、
`internal/selfupdate` 三个包；本仓库**没有引入新的失败**。逐用例差异见
`evidence/test-failure-diff.txt`。这些失败不代表 EDA 执行链不可用，但也不应被说成"全绿"。

> 注：`internal/app`、`internal/daemon`、`internal/selfupdate` 三个包的 `go test` 整体
> 退出码因此为 1；`go build ./...`、新增的 doctor/capabilities/connector 单测、以及
> `internal/blocks` 等其余包全部通过。


## 4.2 M1 收尾：本轮新增并验证的两块

| 能力 | 实测结果 | 证据 |
| --- | --- | --- |
| 统一安装/升级/回退/卸载 | **39 个生命周期用例全通过**（干净安装、幂等重装、升级、回退、卸载、中文+空格路径、7 类损坏包、PATH 不被改、旧 easyeda-agent 目录哈希与 mtime 不变、lock/journal 恢复、`--require-clean` 脏树拒绝、真实产物构建+安装+`zhigou doctor`） | `evidence/installer/pytest-install-lifecycle.log`、`unittest-install-lifecycle.log`、`e2e-real-artifacts.log` |
| Skill 单入口迁移 | 旧工具链引用清零（保留 1 处历史说明 allowlist）；`zhigou doctor`/`capabilities` 成为唯一前置；新增 guard 测试防止旧 CLI/状态目录/env 回流 | `docs/toolchain-integration/skill-migration.md`、`evidence/skill-migration/inventory-post-migration.txt` |
| 全仓库离线回归 | `python tools/offline_suite.py` → **1832 tests OK**（29/29 自检）；`skill_selftest.py` → **5 PASS / 0 FAIL**；新增 guard/CLI/安装器测试 **62 passed** | `evidence/skill-migration/offline-suite.exit.txt`、`skill-selftest.log` |

安装目录（默认，已用隔离目录实测）：`%LOCALAPPDATA%\Zhigou\` 下 `bin\zhigou.exe`、
`connector\zhigou-connector_v0.1.0.eext`（+IMPORT-STEPS.md）、`skill\design-hardware\`、
`licenses\`、`installation.json`（所有权清单+逐文件 sha256）。

## 4.3 版本与构建标识（最终候选）

| 项 | 值 |
| --- | --- |
| CLI/daemon | `zhigou 0.2.0-dev`（构建自本仓库，二进制内嵌 `vcs.revision`） |
| 连接器 | `zhigou-connector 0.1.0`，`.eext` sha256 `9b907bf6…`（231,299 B） |
| 上游基线 | easyeda-agent `v1.15.0` / `d93d3dd`（MIT） |
| 协议 | `zhigou-agent` / wire `v1` |
| 来源复现 | `distribution/verify_vendor.py` → **PASS**（`evidence/m1/vendor-verify.txt`；白名单外文件零差异） |

## 5. 证据索引

| 证据 | 路径 |
| --- | --- |
| 环境基线 | `docs/toolchain-integration/environment-baseline.md` + `evidence/env/` |
| 上游架构与协议分析 | `docs/toolchain-integration/upstream-analysis.md` + `evidence/upstream/` |
| Skill 规则冲突审计（46 条） | `docs/toolchain-integration/rule-conflicts.md` + `evidence/skill-audit/` |
| 架构 | `docs/toolchain-integration/architecture.md` |
| 能力矩阵 | `docs/toolchain-integration/capability-matrix.md` |
| 来源/许可 | `runtime/PROVENANCE.md`、`third_party/`、`NOTICE` |
| M1 运行证据 | `docs/toolchain-integration/evidence/m1/` |
| 运行时回归 | `docs/toolchain-integration/evidence/runtime-go-test.log` |

## 6. 下一条具体操作

1. Lead：把本分支（`feat/integrated-eda-toolchain`）提交并推送，创建 PR（不合并/不发布）。
2. 用户：执行 §4 的一次性 GUI 导入。
3. Lead（导入后自动执行）：`zhigou doctor` → 独立工程 M2 链 → M3 → M4 → 更新验收矩阵证据。
