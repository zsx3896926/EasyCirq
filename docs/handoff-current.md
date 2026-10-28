# 当前交接（智构 · EasyCirq / 自有 EDA 工具链）

> 最后更新：2026-10-28 01:40（安装目录升级到 0.2.2，bundle 已带 connector 0.1.2 + 封装 outline 经验）
> 状态真源：本文件 + `docs/toolchain-integration/task-status.md`；详细证据见
> `docs/toolchain-integration/evidence/`。历史（v1.0.1 发布恢复等）见 git 历史与
> `docs/releases/`。

## 目标与结果

把 EDA 执行层纳入本仓库：自有 CLI/daemon/Connector 可从本仓库构建、隔离安装、真实握手；
设计规则只由 `easycirq` 一个 Skill 管理；安装/诊断/升级/回退统一入口。
**M0–M4 核心链已在 EasyEDA Pro 4.1.78 真机验收通过**（详见 task-status 与 acceptance-matrix）；
PR #36 已创建（草稿，未合并、未打标签、未发布）。

## 当前运行实例（真机）

| 组件 | 版本/位置 | 说明 |
| --- | --- | --- |
| 运行时（项目内） | `runtime/dist/easycirq.exe` 0.2.1-dev | 开发/构建用 |
| 运行时（已安装） | `%LOCALAPPDATA%\EasyCirq\bin\easycirq.exe` 0.2.1 | 统一安装器安装，`easycirq doctor` = **ok** |
| daemon | pid 19464，`127.0.0.1:23111`，service `easycirq-agent` | 与旧 easyeda-agent（60832）并存、互不干扰 |
| Connector | `easycirq-connector 0.1.0`，uuid `a6e6b788…` | 已在 EasyEDA Pro 4.1.78 内导入并握手 |
| Skill | `easycirq` **1.0.2** | 已装到 `.claude / .codex / .agents` 三处客户端目录 |
| 旧上游 Skill | 已停用（移出客户端，未删除） | 备份：`C:\Users\jlc\work\_skill-backups\easycirq-cutover-20261028\` |

客户端 skill 目录现状（已验证）：`easycirq=1.0.2`、`easyeda-agent=absent`（三处一致）；
客户端 skill 目录中已只列出 `easycirq`（描述指向 `easycirq` 执行层）。

## 分支与提交

- 工作树：`C:\Users\jlc\work\easycirq-toolchain`，分支 `feat/integrated-eda-toolchain`
- PR：<https://github.com/zsx3896926/EasyCirq/pull/36>（草稿）
- 构建产物 `dist-v2/` 已 gitignore；仓库内不留 15 MB 二进制

## 常用入口

```powershell
# 已安装版（推荐）
& "$env:LOCALAPPDATA\EasyCirq\bin\easycirq.exe" doctor
& "$env:LOCALAPPDATA\EasyCirq\bin\easycirq.exe" capabilities

# 开发版
& C:\Users\jlc\work\easycirq-toolchain\runtime\dist\easycirq.exe doctor

# 安装/升级/回退（统一入口；-Adopt 用于接管已有客户端 Skill）
distribution\Install-EasyCirq.ps1 status
distribution\Install-EasyCirq.ps1 install  -Bundle dist-v2\easycirq-toolchain-0.2.1.zip -Adopt
distribution\Install-EasyCirq.ps1 upgrade  -Bundle <new>.zip
distribution\Install-EasyCirq.ps1 rollback
```


## 2026-10-28 01:40 更新：bundle 0.2.2 与回归工程

* 已构建 `dist-v4/easycirq-toolchain-0.2.2.zip`（installer sha256 `c70f07aa…`）：
  runtime 0.2.2-dev、connector **0.1.2**（新 uuid `cfc96215…`）、skill **1.0.2**
  （含 `references/pcb-lessons.md` 的"封装内嵌 Board Outline"经验）。
* 已用统一安装器升级 `%LOCALAPPDATA%\EasyCirq`：0.2.1 → **0.2.2**，selfCheck **ok**；
  安装目录 connector 为 `easycirq-connector_v0.1.2.eext`。
* 客户端三处 skill 已更新到 1.0.2（含新经验条目）。
* **回归工程保留**：`outline-foreign-repro-20261028-013032`（SW1 已换成
  `TS-1187A-B-E-B`/C2885182 同类器件，PCB DRC 0 违规），作为该缺陷的现场案例；
  不要删除，后续回归/文档引用它。
* 该缺陷的结论：封装内嵌 Board Outline **不能靠删图元修复**（引擎会重建），
  正确路径是 诊断（`tools/easycirq_footprint_outline_diagnose.py`）→ `sch replace`
  换器件/换封装/改库 → save+reload+DRC 复验。详见 `docs/toolchain-integration/outline-foreign.md`。

## 门禁复核状态（2026-10-28，skill 流程）

- 验收板 `easycirq-integrated-dual-button-led-20261027` 已按 `easycirq` 1.0.2 做 G0–G6 复核：
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
- `PATH` 未修改（安装器设计）：需要直接敲 `easycirq` 时自行把 `%LOCALAPPDATA%\EasyCirq\bin` 加入用户 PATH。
- 旧 `easyeda.exe` 与旧 daemon 保留未删（端口/服务名/扩展 uuid 均隔离）。

## 下一条具体操作

1. 若想命令行直接用 `easycirq`：把 `%LOCALAPPDATA%\EasyCirq\bin` 加入用户 PATH（或继续用绝对路径）。
   （本机已追加，回退基线在 `_skill-backups/easycirq-cutover-20261028/user-path-before.txt`。）
2. 需要正式合并/发版：审阅 PR #36 后由用户决定（不自动合并/发布）。
3. 新硬件任务：新开 AI 客户端会话，加载 `easycirq`（1.0.2）；它会用
   `easycirq doctor` + `easycirq capabilities` 做开工预检，再按 M/S 流程推进。

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
- **显示名**：统一为「智构 · EasyCirq」——README 标题、`easycirq/SKILL.md`
  （description 前缀 + H1）、根 `NOTICE`、`connector/extension.json` 的 `displayName`、
  连接器 README/NOTICE、`distribution/INSTALL.md`、`Install-EasyCirq.ps1` 文案、
  handoff/task-status/architecture/protocol/gate-review 标题。
- **技术标识未改**：`easycirq` CLI、服务名 `easycirq-agent`、端口 23111–23120、`~/.easycirq`、
  包名 `easycirq-connector`、`easycirq` 目录名、`EASYCIRQ_` env、uuid 之外的路径均保持。
- **连接器 0.1.3**：新 uuid `7b3c1e5a9d2f4c6b8e0a1f2d3c4b5a69`；`displayName` 与 logo 更新；
  **同时移除此前下架的两个 `pcb.outline.foreign.scan/delete` handlers**（兑现"下次连接器
  改动一起清"的约定）。
- **产物**：`dist-v5/easycirq-toolchain-0.2.3.zip`（runtime 0.2.3-dev + connector 0.1.3 +
  skill 1.0.2 品牌版）；安装目录已升级 **0.2.3**（selfCheck degraded，原因见下）；客户端
  三处 skill 已更新（description 含品牌）。
- **已完成（2026-10-28T02:22Z）**：EDA 已卸载 0.1.2、导入 0.1.3（新 uuid）并授予「外部交互」；
  `easycirq doctor` **verdict: ok**，connector **0.1.3 connected**（EDA 4.1.78，caps
  `schematic.v1`/`pcb.v1`），daemon **0.2.3**；调用 `pcb.outline.foreign.scan` 返回
  `UNKNOWN_ACTION`，证明旧 handlers 已不在新包中。证据：
  `docs/toolchain-integration/evidence/installer/rebrand-{doctor,health,action-absence}.json`。
- **README 已按当前架构重写（2026-10-28）**：单入口（`easycirq` + 自有 `easycirq`
  执行层）、统一安装器步骤、连接器导入/授权/重启、`easycirq doctor` 验证、真机验收范围与
  边界（Gerber gui_only、G6 BLOCKED、实物 NOT RUN）、项目结构与开发者入口；不再指导安装
  上游 `easyeda-agent` Skill/CLI（仅保留为 MIT 来源致谢）。

## 已合并的 main 侧交接：Round 13（SkyPilot X1 反馈）

## 2026-10-28 制造导出 spike：Gerber/CPL/网表/3D 真机通过

- 连接器 **0.1.4**（uuid `9511dbc464364e48b6c9047872a82e12`）新增三个 typed action：
  `pcb.manufacture.gerber`、`pcb.manufacture.cpl`、`pcb.manufacture.netlist`，
  均封装官方 `@beta pcb_ManufactureData` API，产物作为 artifact 回读校验。
- 真机结果（验收板 `easycirq-integrated-dual-button-led-20261027`，连接器 0.1.4）：
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

## 2026-10-28 drill 验证 + G6 只剩库存核对

- 在独立工程 `manufacture-drill-repro-20261028-120350`（板框 2000×1200 mil + 1 个 12/24 mil 无网络 via）
  上复跑 `pcb.manufacture.gerber`（drill=true, drillTable=true）：zip 11 个条目，含
  `Gerber_DrillDrawingLayer.GDD`、`Drill_PTH_Through.DRL`、`Drill_PTH_Through_Via.DRL`。
  → 钻孔文件能力在含孔板上**已验证**；0 孔板不产生 drill 文件属于不适用。
- 能力模型：`drill.export` unsupported → **supported**；deliverables `export.drill` → **measured**
  （capabilities 汇总 supported 20 / unknown 2 / unsupported 2）。
- `gate_check.py` 新增"0 孔板不适用"判定：`design-state.pcb.drilled_holes=0` 时 `drill_files` 判 pass
  并注明不适用（不是掩盖缺失）。已同步到安装目录与三处客户端 skill。
- **G6 阻塞只剩 `sourcing_check`**（库存/价格未核，不伪造时间）；**G6 结论仍 BLOCKED**，
  交付级别不变（PCB 候选 DRC 0）。
- 注意：验收板板框曾被误设为 2000×1200，已按 dump 原始坐标恢复并 save+reload+DRC 0 复核。

## 2026-10-28 12:40 G6 闭环（sourcing 核对完成）

- 修好 DSH 的 web-search 后端：profile patch 里把 `web-search-deepseek` 的 baseURL 指到
  `https://claude.jlcops.com/api/v1`、model 改为 `deepseek-v4.1-flash`（备份
  `cordis.patch.yml.bak-20261028-123651`）；此前它默认打 `api.deepseek.com`，用代理 key 必然 401。
- 用修好的搜索 + LCSC 商品页 JSON-LD 做真实核对（`evidence/gates/sourcing-check.json`）：
  R1/R2（C2889365）可订货但**库存 0**、最小包装 10000；其余 5 行 Page Not Found（系统库内部编号）。
- `sourcing_check` pass → **G6 PASS**：gate 汇总 **6 PASS / 1 PASS_WITH_WAIVER / 0 BLOCKED**（退出码 0）。
- 结论仍是**不能下单**：BOM 缺货/无订货号（`OI-SOURCING-2`），需换料后重核；交付级别不升格。

## 2026-10-28 12:55 BOM 换料（部分完成，PCB 待重布）

- 用户确认的 6 行替换：R1/R2→C112291、C1→C125205、D1/D2→C51933311、F1→C845159、
  SW1/SW2→C49296724、J1→C124375（TH 直插）。
- 在**干净副本** `easycirq-dual-button-led-eev2-20261028`（从 `easycirq-board.epro2` 导入）上用
  `schematic.component.modify` 只改 BOM 身份（符号/封装不动），9/9 成功；J1 因无同封装有货的
  SMD 2P 料号，改为删除+重放 TH 器件（封装 `HDR-TH_2P-P2.54-V-M-1`）。
- 新 BOM（含 C 号/厂家/MPN）：`evidence/gates/BOM-v2.csv`；记录 `bom-replacement-record.json`。
- **PCB 未闭环**：J1 换 TH 后 4 处 No Connection（GND: C1_2/J1_2；VIN: J1_1/e26）；
  `route.auto` 与 `pour.rebuild` 调用成功但未消除，需要手工补 J1/C1 的短线后重跑 DRC。
- **原验收工程 `easycirq-integrated-dual-button-led-20261027` 被改坏**（原地替换导致原理图连接/网表
  受损）。恢复方式：用 `easycirq-board.epro2` 重新导入，或在 EDA 中撤销。请勿再引用其当前状态。

## 2026-10-28 12:58 PCB 修复尝试失败（如实）

- 自动补线尝试：`pcb.route.auto`、`pcb.pour.rebuild`（rebuilt 2）都成功调用，但 J1 换 TH 后的
  No Connection 未消除；随后 `pcb.line.create` 画了 3 条线（VIN J1_1→e26、GND J1_2、GND C1_2），
  端点没有吸附到焊盘/走线端点，DRC 反而变成 2 条违规、多出悬空段 e52/e53。
- 因此 **PCB 未闭环**：需在 EDA GUI 里交互式补 J1/C1 两条线（吸附可靠），或
  `easycirq-board.epro2` 重导基线 + 保留 `BOM-v2.csv` 的料号。
- BOM 侧不退回：6 行新料号（C112291/C125205/C51933311/C845159/C49296724/C124375）已确认有货，
  BOM 导出（`evidence/gates/BOM-v2.csv`）可直接用于下单核对。

## 2026-10-28 13:05 PCB 自动补线结论（停止）

- 用真实宿主坐标（`getPrimitivesBBox`）后，J1_1/J1_2 的 No Connection **清零**；
- 但逃逸走线互相重叠，且剩 1 条 Safe-Spacing（+5V e34 与 GND/VIN 补线间距不足）；
  按 id 删除没匹配到新线段，重复补线累积 → PCB 当前不可信。
- 结论：**自动补线（无吸附/无 clearance 预检）不可靠**。建议从 `easycirq-board.epro2`
  重导 PCB 基线；若保留 TH J1，连接器逃逸布线在 EDA GUI 里做（约 1 分钟）。
- BOM 不受影响：`evidence/gates/BOM-v2.csv` 六行料号可下单。

## 2026-10-28 13:12 eev3 成功：BOM 换料 + 全板重布 + DRC 0

- 从 `easycirq-board.epro2` 重导基线 → `easycirq-dual-button-led-eev3-20261028`。
- 8 个器件改 BOM 身份（C112291/C125205/C51933311/C845159/C49296724）+ J1 删除重放为 TH 器件
  （C124375，封装 HDR-TH_2P-P2.54-V-M-1）→ PCB 同步 imported+verified。
- **放弃手工补线**：删除全部 47 条旧走线 → `pcb.route.auto` 全板重布 → `pour.rebuild` →
  `pcb save → doc reload → pcb drc` = **passed，0 违规**。
- BOM：`evidence/gates/BOM-v3.csv`（6 行含 C 号/型号/厂家，可下单）。
- 注意：全板重布替换了原手工布线，制造前仍需人工看布局/走线观感；原工程与 eev2 副本已损坏，
  以 eev3 为当前候选。

## 2026-10-28 13:18 DFM 修复尝试与回退

- 备份：`.easycirq/artifacts/eev3-before-dfm-fix.epro2`（49,207 B，导出成功）。
- 修复尝试：J1 位号丝印移回板内（成功）；删除 10 条 +5V/GND 走线后用 `route-short --route-power
  --width-power 20` 重布（DRC 仍 0），但引入 `widthMismatches` 4（R1/R2/SW1/SW2 进出线宽 10/20
  不一致）与 `viaInPad` 1（SW1.2 的 GND 过孔落在焊盘上）；minGap 仍 5.98、crossing 仍 1。
- 结论：**自动修复线宽/过孔不可靠**，已从备份恢复为 `easycirq-dual-button-led-eev3-final`。
  保留原 eev3 基线（DRC 0 + 4 条 DFM WARN）；DFM 的线宽/过孔/5.98 间距留给人工在 GUI 里处理。
- 制造文件（Gerber+钻孔/CPL）已从原 eev3 导出，与保留基线一致。

## 2026-10-28 13:20 最终基线：`easycirq-dual-button-led-eev3-final`

- DFM 修复尝试：丝印移动成功；但线宽加宽（+5V/GND 20 mil）引入 `widthMismatches` 4 与
  `viaInPad` 1，minGap 仍 5.98 → **已回退**，从 `eev3-before-dfm-fix.epro2`（49,207 B 备份）恢复为
  `easycirq-dual-button-led-eev3-final`（uuid `f178aba5…`）。
- 基线状态：PCB DRC **0 违规**；BOM 6 行可下单；制造文件（Gerber+钻孔/CPL）已导出。
- 遗留（投产前需人工/GUI）：minGap 5.98→≥6、J1 丝印移入、+5V/GND 线宽策略（勿 10/20 混接）、
  可选 +5V 铺铜、人工走线复核、实物测试 V2–V11。
- 证据：`evidence/eev3/final-baseline.json`、`dfm-fix-attempt.json`、`eev3-acceptance.md`。

## 2026-10-28 13:25 eev3 送打样（用户决定，跳过人工复核）

- 用户决定：直接送嘉立创打样，人工走线复核**明确跳过（视为未执行）**。
- 状态：DRC 0、BOM 6 行可下单、Gerber+钻孔+CPL 已导出、5.98 mil 满足 0.10 mm 工艺下限；
  DFM 3 WARN 经载流计算判为不必处理（+5V ≈27 mA，10 mil 余量充足）。
- 后续：打样回来做实物测试 V2–V11（NOT RUN）；任何制造文件变更需重跑 DRC/lint/check 并重导。
## 2026-10-28 16:05 演示板 peripheral 警告处理

- 已清除冗余的 module claim（sch zones clear，3 个），分区框改由虚拟组驱动：
  zone-plan 3 分区 clean、zone-draw 3 框保留；peripheral-not-direct 警告消除。
- 清除后 sch check 报出 2 条历史遗留导线几何 ERROR（D1 附近 wire-through-body）与 2 条
  sheet 属性 out-of-sheet（平台属性显示位置，工具链无法移动）；sch drc 仍 0。
- 随后 EDA 事务报 "Schematic has an unknown or non-sync transaction"，导出/读取间歇失败——
  需在 EDA 里重开工程或重启 EDA 后再复验与导出。
- 当前演示图仍为 1.0.11 的版本（标题栏已修、三框齐全）。
