# 当前交接（智构 · EasyCirq / 自有 EDA 工具链）

> 最后更新：2026-10-28 01:40（安装目录升级到 0.2.2，bundle 已带 connector 0.1.2 + 封装 outline 经验）
> 状态真源：本文件 + `docs/toolchain-integration/task-status.md`；详细证据见
> `docs/toolchain-integration/evidence/`。历史（v1.0.1 发布恢复等）见 git 历史与
> `docs/releases/`。

## 目标与结果

把 EDA 执行层纳入本仓库：自有 CLI/daemon/Connector 可从本仓库构建、隔离安装、真实握手；
设计规则只由 `design-hardware` 一个 Skill 管理；安装/诊断/升级/回退统一入口。
**M0–M4 核心链已在 EasyEDA Pro 4.1.78 真机验收通过**（详见 task-status 与 acceptance-matrix）；
PR #36 已创建（草稿，未合并、未打标签、未发布）。

## 当前运行实例（真机）

| 组件 | 版本/位置 | 说明 |
| --- | --- | --- |
| 运行时（项目内） | `runtime/dist/zhigou.exe` 0.2.1-dev | 开发/构建用 |
| 运行时（已安装） | `%LOCALAPPDATA%\Zhigou\bin\zhigou.exe` 0.2.1 | 统一安装器安装，`zhigou doctor` = **ok** |
| daemon | pid 19464，`127.0.0.1:23111`，service `zhigou-agent` | 与旧 easyeda-agent（60832）并存、互不干扰 |
| Connector | `zhigou-connector 0.1.0`，uuid `a6e6b788…` | 已在 EasyEDA Pro 4.1.78 内导入并握手 |
| Skill | `design-hardware` **1.0.2** | 已装到 `.claude / .codex / .agents` 三处客户端目录 |
| 旧上游 Skill | 已停用（移出客户端，未删除） | 备份：`C:\Users\jlc\work\_skill-backups\zhigou-cutover-20261028\` |

客户端 skill 目录现状（已验证）：`design-hardware=1.0.2`、`easyeda-agent=absent`（三处一致）；
客户端 skill 目录中已只列出 `design-hardware`（描述指向 `zhigou` 执行层）。

## 分支与提交

- 工作树：`C:\Users\jlc\work\zhigou-toolchain`，分支 `feat/integrated-eda-toolchain`
- PR：<https://github.com/zsx3896926/hardware-design-skill/pull/36>（草稿）
- 构建产物 `dist-v2/` 已 gitignore；仓库内不留 15 MB 二进制

## 常用入口

```powershell
# 已安装版（推荐）
& "$env:LOCALAPPDATA\Zhigou\bin\zhigou.exe" doctor
& "$env:LOCALAPPDATA\Zhigou\bin\zhigou.exe" capabilities

# 开发版
& C:\Users\jlc\work\zhigou-toolchain\runtime\dist\zhigou.exe doctor

# 安装/升级/回退（统一入口；-Adopt 用于接管已有客户端 Skill）
distribution\Install-Zhigou.ps1 status
distribution\Install-Zhigou.ps1 install  -Bundle dist-v2\zhigou-toolchain-0.2.1.zip -Adopt
distribution\Install-Zhigou.ps1 upgrade  -Bundle <new>.zip
distribution\Install-Zhigou.ps1 rollback
```


## 2026-10-28 01:40 更新：bundle 0.2.2 与回归工程

* 已构建 `dist-v4/zhigou-toolchain-0.2.2.zip`（installer sha256 `c70f07aa…`）：
  runtime 0.2.2-dev、connector **0.1.2**（新 uuid `cfc96215…`）、skill **1.0.2**
  （含 `references/pcb-lessons.md` 的"封装内嵌 Board Outline"经验）。
* 已用统一安装器升级 `%LOCALAPPDATA%\Zhigou`：0.2.1 → **0.2.2**，selfCheck **ok**；
  安装目录 connector 为 `zhigou-connector_v0.1.2.eext`。
* 客户端三处 skill 已更新到 1.0.2（含新经验条目）。
* **回归工程保留**：`outline-foreign-repro-20261028-013032`（SW1 已换成
  `TS-1187A-B-E-B`/C2885182 同类器件，PCB DRC 0 违规），作为该缺陷的现场案例；
  不要删除，后续回归/文档引用它。
* 该缺陷的结论：封装内嵌 Board Outline **不能靠删图元修复**（引擎会重建），
  正确路径是 诊断（`tools/zhigou_footprint_outline_diagnose.py`）→ `sch replace`
  换器件/换封装/改库 → save+reload+DRC 复验。详见 `docs/toolchain-integration/outline-foreign.md`。

## 门禁复核状态（2026-10-28，skill 流程）

- 验收板 `zhigou-integrated-dual-button-led-20261027` 已按 `design-hardware` 1.0.2 做 G0–G6 复核：
  **G0–G3、G5 PASS；G4 PASS_WITH_WAIVER（+5V/VIN 未铺铜）；G6 BLOCKED**（5 PASS / 1 WAIVED / 1 BLOCKED）。
- 交付级别：**PCB 候选（PCB DRC 0）**，未升格；实物功能 NOT RUN。
- G6 仅剩 4 项阻塞：`gerber_files`、`drill_files`、`cpl_files`（本版本 gui_only）+
  `sourcing_check`（库存/价格未核，不伪造查询时间）。
- 已离线补齐：工艺档案、实物测试计划（V2–V11 NOT RUN）、BOM 身份核对（6 行：1 行可订货、
  5 行系统库内部编号待替换/确认）、制造导出清单、物料核对清单。
- 证据与复跑命令：`docs/toolchain-integration/gate-review.md`、`evidence/gates/`。
- 下一动作：GUI 导出三种制造文件并登记 → 商城核对物料并写 `stock_checked_at` → 重跑 gate。

## 已知边界（如实，不是掩盖）

- **Gerber/钻孔/CPL**：typed action 目录不存在 → `gui_only`，只能 EDA GUI 导出并落人工证据；未宣称。
- **PCB DRC 通过 ≠ 硬件上电通过**；实物功能 **NOT RUN**。
- DFM 剩 4 条 WARN（+5V/VIN 未铺铜、2 条电源线偏细）；3D 导出为 binding-only 覆盖。
- `PATH` 未修改（安装器设计）：需要直接敲 `zhigou` 时自行把 `%LOCALAPPDATA%\Zhigou\bin` 加入用户 PATH。
- 旧 `easyeda.exe` 与旧 daemon 保留未删（端口/服务名/扩展 uuid 均隔离）。

## 下一条具体操作

1. 若想命令行直接用 `zhigou`：把 `%LOCALAPPDATA%\Zhigou\bin` 加入用户 PATH（或继续用绝对路径）。
   （本机已追加，回退基线在 `_skill-backups/zhigou-cutover-20261028/user-path-before.txt`。）
2. 需要正式合并/发版：审阅 PR #36 后由用户决定（不自动合并/发布）。
3. 新硬件任务：新开 AI 客户端会话，加载 `design-hardware`（1.0.2）；它会用
   `zhigou doctor` + `zhigou capabilities` 做开工预检，再按 M/S 流程推进。

## 待清理（已与用户约定：不单独发版）

- **connector 侧移除 `pcb.outline.foreign.scan` / `pcb.outline.foreign.delete` handlers**
  （0.1.2 里仍存在，但实测对该缺陷无效：子图元枚举不到、delete 会被引擎重建；
  运行时 action catalog 已下架，不再作为能力发布）。
  处理时机：**下次有其它连接器改动时一起做**，随那次一起 bump 版本/换 uuid、重新导入；
  **不为此单独发版**。清理时同步更新 `docs/toolchain-integration/outline-foreign.md`。

## 2026-10-28 品牌切换：智构 · EasyCirq

- **Logo**：全项目换为用户提供的两张图（横版 + 方形）。原图与派生尺寸在
  `assets/brand/`（`source/` 原图、`logo-horizontal-1200.png`、`logo-square-512.png`、
  `logo-square-128.png`）；连接器图标 `connector/images/logo.jpg` 已换为方形版（512 JPG）。
  README 顶部使用横版。
- **显示名**：统一为「智构 · EasyCirq」——README 标题、`design-hardware/SKILL.md`
  （description 前缀 + H1）、根 `NOTICE`、`connector/extension.json` 的 `displayName`、
  连接器 README/NOTICE、`distribution/INSTALL.md`、`Install-Zhigou.ps1` 文案、
  handoff/task-status/architecture/protocol/gate-review 标题。
- **技术标识未改**：`zhigou` CLI、服务名 `zhigou-agent`、端口 23111–23120、`~/.zhigou`、
  包名 `zhigou-connector`、`design-hardware` 目录名、`ZHIGOU_` env、uuid 之外的路径均保持。
- **连接器 0.1.3**：新 uuid `7b3c1e5a9d2f4c6b8e0a1f2d3c4b5a69`；`displayName` 与 logo 更新；
  **同时移除此前下架的两个 `pcb.outline.foreign.scan/delete` handlers**（兑现"下次连接器
  改动一起清"的约定）。
- **产物**：`dist-v5/zhigou-toolchain-0.2.3.zip`（runtime 0.2.3-dev + connector 0.1.3 +
  skill 1.0.2 品牌版）；安装目录已升级 **0.2.3**（selfCheck degraded，原因见下）；客户端
  三处 skill 已更新（description 含品牌）。
- **已完成（2026-10-28T02:22Z）**：EDA 已卸载 0.1.2、导入 0.1.3（新 uuid）并授予「外部交互」；
  `zhigou doctor` **verdict: ok**，connector **0.1.3 connected**（EDA 4.1.78，caps
  `schematic.v1`/`pcb.v1`），daemon **0.2.3**；调用 `pcb.outline.foreign.scan` 返回
  `UNKNOWN_ACTION`，证明旧 handlers 已不在新包中。证据：
  `docs/toolchain-integration/evidence/installer/rebrand-{doctor,health,action-absence}.json`。
- **README 已按当前架构重写（2026-10-28）**：单入口（`design-hardware` + 自有 `zhigou`
  执行层）、统一安装器步骤、连接器导入/授权/重启、`zhigou doctor` 验证、真机验收范围与
  边界（Gerber gui_only、G6 BLOCKED、实物 NOT RUN）、项目结构与开发者入口；不再指导安装
  上游 `easyeda-agent` Skill/CLI（仅保留为 MIT 来源致谢）。

## 已合并的 main 侧交接：Round 13（SkyPilot X1 反馈）

## 2026-10-28 制造导出 spike：Gerber/CPL/网表/3D 真机通过

- 连接器 **0.1.4**（uuid `9511dbc464364e48b6c9047872a82e12`）新增三个 typed action：
  `pcb.manufacture.gerber`、`pcb.manufacture.cpl`、`pcb.manufacture.netlist`，
  均封装官方 `@beta pcb_ManufactureData` API，产物作为 artifact 回读校验。
- 真机结果（验收板 `zhigou-integrated-dual-button-led-20261027`，连接器 0.1.4）：
  - Gerber：12,169 B zip，**9 层**（GTL/GBL/GTO/GBO/GTS/GBS/GTP/GKO/GDL）+ 下单必读；
    **无 drill 文件**——本板 0 过孔，含孔板路径未验证
  - CPL：3,238 B，UTF-16 TSV，**9 行 = 9 器件**（表头 18 列）
  - 网表（PCB 侧）：15,749 B / 542 行（JLCEDA 格式；原理图侧 getNetlistFile 仍返回 no file）
  - 3D：OBJ 209,014 B；STEP 5,030,129 B（ISO-10303-21，真实网格）
- 能力模型：`gerber.export`/`cpl.export` 从 unsupported → **supported**；
  `export.gerber`/`export.cpl`/`export.3d` deliverables → **measured**（证据清单见
  `runtime/internal/app/capability_measured.go`）；`drill.export` 保持 unsupported。
- G6：阻塞从 4 项降到 **2 项**（`drill_files`：0 孔不适用；`sourcing_check`：未核库存）。
  gerber/cpl 产物已放 `evidence/gates/manufacturing/` 并登记 `manufacturing.artifacts`。
- 注意：EDA 里旧的 0.1.3 扩展仍在加载（两个窗口），建议卸载只留 0.1.4；
  安装包/安装目录尚未更新到 0.1.4（下次构建 bundle 时一并带上）。
