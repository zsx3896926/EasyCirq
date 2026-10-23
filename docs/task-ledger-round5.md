# 第五轮任务台账（发布验收轮，2026-10-22）

> 本轮目标：把真实项目向「能够制造、装配、烧录和实际使用」推进，并让没用过 EDA 的新手
> 也能通过 Agent 完成关键步骤。任务书分 A–N 包，里程碑 R0–R5。
> 本文件是第五轮状态真源；历史台账（round2/3/4）只作历史引用。
> 盘点原始数据：`docs/round5/a-inventory-raw.json`；汇总：`docs/round5/a-summary.txt`。

## 0. 基线与环境快照（2026-10-22）

| 项 | 值 | 证据 |
|---|---|---|
| 主线 | `origin/main` = `7a6edb7b5a44e8e87a578f18402a85410642cc1f`，与 GitHub main 一致 | GIT-01（核验 CONFIRMED） |
| 本轮 worktree | `C:/Users/jlc/work/hds-round5`，分支 `feat/round5-release-acceptance`，HEAD `0e254dc`（截至本轮第 2 个提交） | git |
| PR | #1–#3、#5–#9 共 8 个 MERGED；#4 CLOSED（被 #8 接替，不得再合）；0 OPEN | GIT-02 |
| CI | validate 全绿；历史 5 次失败均为 PR #5 中间 run，已被取代；CI 只跑 unittest | GIT-04 |
| 测试 | 干净基线 495 OK；本轮 +51 → **546 OK**（含 51 项 PCB 测试） | 本地实跑 |
| Python / Node / npm | 3.13.15 / v24.20.0 / 11.19.0 | ENV-02 |
| Claude Code / Codex | 2.1.303 / CLI 存在（pwsh 267 报错另查） | ENV-02/09 |
| EDA | 嘉立创EDA专业版 4.1.78（bridge 4.1.78.34f5b8d9）；CLI 会话恒半离线；4 个用户 GUI 会话 alive（勿动） | ENV-03/07 |
| 未合入远端分支 | cross-client-round3（3 ahead）、engineering-decisions-round4（5 ahead）、rev3-relayout（1 ahead，docs 提交） | GIT-03 |
| main 分支保护 | **无**；7a6edb7 等 6 个提交为直接 push | GIT-05 |

## 1. A 包盘点结论（核验后）

9 个方向 147 条发现，62 条声明经独立复核：**59 CONFIRMED、3 REFUTED（全部修正为 PARTIAL，
无虚假 DONE）**。修正的三条：

- `r3-pkg-i`：声称「接口卡 i12-level-shift 已修」不成立——文件与审计基线 blob 相同（零改动）。
- `r3-backlog-p2p3`：声称 NOT RUN 与现状不符——P2-11 部分已由 F1 rev3 完成、P3 有部分文档修正。
- `E-16`：声称「PCB 适配器没有就绪探测」已被本轮新代码推翻（PCB_SELECT_JS 有 12×600ms 重试）；
  且存在真实竞态证据：open 后立即读 `getAllPcbsInfo` 可返回空列表（`%TEMP%/hds5-pcb-read/result.json`）。

### 关键事实（防重复劳动）

1. F1 基线 = **21 器件 rev3**（golden `f1-rev3b.net`），重排前后网表 SHA256 相同、
   保存重开 match、DRC 3 条（2×ONENETNAME + 1×CHECKFLOATPIN）。旧 16 器件 F1 不得当基线。
2. DRC「3 条 vs 5 条」：3 条对应重排后 rev3，5 条对应 rev1 修订过程——不是回归。
3. 图面仍拥挤、标题栏仍 V1.0（非 DRAFT）、J101 未用脚无 NC（桥不支持 NC 原语）、ERC 豁免表未做。
4. 执行器 P0 门禁已实现（快照完整性、回读、重开比较、受控删除、超时部分结果）；但「真实故障注入」
   验证缺口仍在（I 包）。
5. `eda-execution.md` 与当前执行器存在不一致；tests 数量、connections/ 目录说明等多处 STALE 文档。
6. `docs/evidence/client-env-2026-10-22/README` 指向只在 PR #4 分支存在的
   `f1-relayout-2026-10-22/`——断链。
7. 供应链：21 位号 C 号 21/21（其中 2 个为 10 位系统号，非真实 C 号）、MPN 17/21、
   实时库存 0/21（2026-10-20 查询失败）、无当前 BOM/CPL/Gerber；README/P04 仍描述 16 器件 rev1。
8. 三客户端：Claude Code 有同会话 Skill 发现/读/最小写/保存/重开证据；Codex 同（pwsh 267 问题
   待定位）；WorkBuddy BLOCKED（CLI `/login`）；均无「完整项目」证据。
9. 知识库：13 组/102 主题/12 应用结构完整；原厂资料复核仅在线交叉核对；C40/C76 两条审校未关闭。
10. 固件：仓库无实际固件代码，只有文档与测试计划（firmware-bringup/product-acceptance）。
11. **勘误（C 包核实）**：U101 = **Ai-Thinker ESP-01S（ESP8266，8 脚）**，不是此前文档所写的 ESP32-C3。
    图面引脚 VCC/GND/TXD/RXD/EN/RST/IO0/IO2 与 ESP-01S 一致；M 包固件、烧录与引脚配置一律按 ESP8266
    重写，历史 ESP32-C3 叙述作废。

## 2. 本轮任务台账（A–N）

| 包 | 内容 | 状态 | 已完成/剩余要点 | 下一条具体操作 |
|---|---|---|---|---|
| A | 状态盘点与统一台账 | **DONE** | 盘点+62 核验完成；本文件即交付 | 随工作推进维护本文件 |
| B | F1 原理图排版/警告/审图 | **DONE**（人工审图待做） | 最终副本 `f1-b-v5.eprj2`：ONENETNAME 根因定位并重画消除（DRC 3→1）；孤立错误电源符删除；DRAFT 与 J101 未用脚注记真机写入；网表 golden 逐字节一致；重开 match；处置表 + AI 独立审图（非人工）。审图必须修复项：U101 身份已澄清（ESP-01S）、孤立符已修；端口挤压与值串可读性经 v4/v6 三组实验证明 CLI 无安全修法（删退化线断连、搬端口合并出 ONENETNAME、改属性触发 ATTRMATCHCODE），留 GUI | 人工审图按报告清单执行；先清 10 条零长度退化线再搬端口；标题栏 V1.0 需 GUI 改 |
| C | F1 电气依据/封装/验证计划 | **DONE**（C2/C5 子项 PARTIAL） | 21 位号身份表+证据等级（`docs/evidence/f1-c-2026-10-22/part-evidence.md`）；LCSC 核对 U101/U102/D102；电源压差/热/ESR 独立复算；CC/TVS/J102 反灌结论；启动复位 RC 核对；焊盘级映射如实 PARTIAL | C2 取 YONGYUTAI 原厂 PDF 或换料比较；C5 焊盘表随 F 包导入核对 |
| D | 真实几何与排版检查闭环 | PARTIAL | `sch_layout_check.py` 存在但未接真实 EDA 几何 | 用 F1 快照导出坐标，接入检查器 |
| E | PCB 执行器 | **DONE**（缺口明确列出） | 命令族实现+真机验收：读→最小写（线/过孔/铜区边框/器件 flat+search）→回读→保存→重开 match，四类原语全部成立；铺铜填充、DRC 明细、制造导出在 CLI 半离线不可用（记录在案）；板框专用原语、移动/旋转/删除未探测 | 未支持项已在 `pcb doctor` 与证据 README 明列；F 包使用前在 GUI 会话补板框验证 |
| F | F1 PCB 完整闭环 | **BLOCKED**（导入/板框需 GUI；其后步骤已验证） | 真机确认：`importChanges` 返回 true 但 0 物化；layer 11 板框被 API 拒绝；`autoLayout` 33/33、`autoRouting` 13–16/17、保存重开 match 均可用，已封装 `pcb import/layout/route/outline`；演示跑在工程内旧板（非 F1） | 用户在 GUI 完成 F1 导入 + 板框各一次；随后 CLI：layout → route --save → drc → reopen-check |
| G | 商城/SMT/替代料 | PARTIAL | C 号不全、实时库存 BLOCKED、SMT/替代料 NOT RUN | 出「关键料取证清单」；库存查询失败原因定位（网络/API） |
| H | 生产规则/制造资料 | **PARTIAL** | 生产规则映射+检查清单完成（`docs/evidence/h-2026-10-23/`）；制造包（Gerber/钻孔/CPL/BOM 导出）BLOCKED：CLI getter 返回空对象、F 未出 PCB | F 完成后按清单在 GUI 导出并逐项回填 |
| I | 异常恢复与故障注入 | **PARTIAL** | 真实注入 3/8：超时→partial_unknown 且不重复写、复跑→no_changes、错误身份→blocked 零写入；保存失败/断连/作业延迟等 5 项 NOT RUN（原因已记） | 作业模型（startAutoRouting + getAutoJobStatus）实测；保存失败注入需 GUI/宿主手段 |
| J | 三客户端与新手流程 | **PARTIAL** | Skill 已装三客户端（各 329 文件，无重复）；Claude Code headless 发现 **PASS**；Codex 为桌面应用、无 CLI，发现待 GUI 确认；WorkBuddy GUI 登录 BLOCKED；新手流程证据以既有 CC/Codex 最小流程为准 | Codex/WorkBuddy GUI 各确认一次技能可见并跑最小流程；WorkBuddy 需用户登录 |
| K | 知识库审校 | PARTIAL | C40/C76 两条未关闭；原厂依据不足 | 逐条按「历史问题→当前状态→依据→复算」关闭 |
| L | Agent 行为评测 | NOT RUN | 场景与评价维度已定，试验未跑 | 用决策库案例做同条件对照（无 Skill 基线） |
| M | 固件/首板 | PARTIAL | M1 完成：按 ESP8266 ESP-01S 的板级引脚表、最小固件、构建/烧录命令、串口判据、上电检查表（12 项）、结果模板；构建 **NOT RUN**（本机无 PlatformIO）；实物验证 BLOCKED | 安装 PlatformIO 后 `pio run` 产出 firmware.bin；首板按检查表执行并回填结果 |
| N | 发布/教程/交接 | NOT RUN | 依赖其余各包实际完成项 | 每包 DONE 后更新 README/教程差异与限制 |

## 3. 能力矩阵（用户动作 → 当前可复核状态）

| 用户动作 | 可用性 | 客户端/环境 | 产物 | 证据 |
|---|---|---|---|---|
| 描述需求形成方案 | 可用 | 任意（Skill 内容） | 决策库 A–L、102 主题 | round4/PR #6 |
| 实际生成/修改原理图 | 可用（半离线） | Claude Code/Codex + CLI | F1 rev3（21 器件） | docs/evidence/f1-rev3-*/ |
| 实际生成/修改 PCB | **本轮新增：最小原语可用（半离线）** | CLI 会话 | line/via/pour 边框创建+保存+重开 match | docs/evidence/pcb-e2-2026-10-22/ |
| 商城/SMT 选料 | 不可用（实时数据 BLOCKED） | — | 仅静态 selected-parts.json | — |
| 导出制造包 | 不可用（CLI API 返回空对象；需 GUI 全在线） | GUI 会话待用户配合 | 无 | docs/evidence/pcb-e2-2026-10-22/exports/ |
| 烧录与功能验证 | 不可用（无实物） | — | 无 | — |

## 4. 本轮已提交

| 提交 | 内容 |
|---|---|
| `eb930eb` | `eda_exec.py` PCB 命令族（doctor/read/apply/save/drc/export/reopen-check）+ 50 测试 |
| `0e254dc` | 真机验收驱动修复：field_notes 非阻塞通道、激活竞态专用重试、reopen-check 会话泄漏修复 + 真机证据目录 |

分支 `feat/round5-release-acceptance` 已推送；PR 待后续开（按仓库习惯，阶段完成后开 PR）。

## 5. 下一条具体操作（优先级）

1. **E 收尾**：器件放置（component_flat/search）在本轮 4.1.78 半离线副本上真机复测一次，
   补入 `docs/evidence/pcb-e2-2026-10-22/`；随后 E 可标 DONE（明确列出未支持项）。
2. **B 包**：复制 `f1-rev3-layout.eprj2` 到 round5 scratch，冻结 golden 网表，
   做标题栏 DRAFT + ERC 豁免表 + 独立审图（先产出审图清单）。
3. **C 包**：从 `selected-parts.json` 生成 21 位号取证表（MPN/封装/C 号/原厂手册），
   逐项核对；优先 1117 稳压器手册、TVS 钳位参数、USB-C CC 电阻。
4. **G 包**：定位 2026-10-20 实时库存查询失败原因；用立创商城公开页/API 补库存证据（注明时间）。
5. **J 包**：把「新手一句话提示词 + 五步检查清单」整理成可交付的一页（workbook 而非文档堆）；
   WorkBuddy GUI 登录需要用户动作——提出最小一步。
6. **M 包**：按 rev3 网表写最小固件骨架（GPIO/EN/RST/UART 引脚表 + 可复现构建命令），不依赖实物。

## 6. 阻塞与授权边界（本轮不变）

- CLI 会话恒半离线；全在线验收只能靠用户 GUI 会话，一次给一个动作。
- 不付费下单、不发消息给外部联系人、不碰用户 GUI 会话、不上传用户工程。
- 铺铜填充重算、制造资料导出、DRC 明细需要 GUI 会话——列为 BLOCKED，不留空、不冒充。
