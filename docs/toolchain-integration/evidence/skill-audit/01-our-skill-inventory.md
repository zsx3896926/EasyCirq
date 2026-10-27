# 我方 Skill 原始清单（design-hardware / 智构）

审计对象：`C:\Users\jlc\work\zhigou-toolchain\design-hardware`（本 worktree，权威）
分支 `feat/integrated-eda-toolchain`，基线 commit `9a951ed`（from origin/main）。
本文件只做摘录与定位，不改变任何规则语义。

## 0. 版本与一致性事实

| 项 | 值 | 证据 |
|---|---|---|
| `.version` | `1.0.1` | `design-hardware/.version` |
| `SKILL.md` 行数/字节 | **323 行 / 50163 字节** | `Get-Content`/文件长度实测（派单说明写作 231 行，与实际不符，见主报告 §7 UNKNOWN-1） |
| `SKILL.md` SHA256 | `2FE4FEB283F0904F25F44CE2425C6C3766A0F8B6DB45FCBD9D4E2542FF9E486D` | `Get-FileHash -Algorithm SHA256` |
| 已安装副本 | `C:\Users\jlc\.agents\skills\design-hardware`，323 行、`.version`=1.0.1、`SKILL.md` 逐行内容相同（仅 CRLF→LF；多出 `.install.json`） | 逐行 `Compare-Object` + 首字节比对（repo `2D,2D,2D,0D,0A`；inst `2D,2D,2D,0A`） |
| 文件总数 | 545（repo） / 546（inst，多 `.install.json`） | 递归计数 |
| references | 顶层 66 个 `.md`/`.json`，含子目录合计 **280 个文件** | 目录统计 |
| assets | 顶层 22 项，子目录 9 组（`docs`5/`decisions`25/…） | 目录统计 |
| scripts | 66 个 `.py` + 分包 `design_engine/`(22)、`feedback/`(7)、`power_preflight/`(7) | 目录统计 |
| cases | 4 组（`temp-alarm-2026-10-24`、`photo-led-pcb-2026-10-26`、`mcu-i2c-s3-2026-10-26`、`dual-button-led-night-20261027`）+ `index.json` | 目录统计 |
| agents | 仅 `agents/openai.yaml`（394 字节） | 目录统计 |
| vendor | `vendor/easyeda-format/`（LICENSE + source.json + 6 个 schema） | 目录统计 |

## 1. `SKILL.md` 规则承载段（323 行逐段）

| 行 | 段落 | 承载的规则 |
|---|---|---|
| 1–4 | frontmatter | `name: design-hardware`；description 定义触发面（含"配合 easyeda-agent 等工具"——与上游绑定，见 C27/C31） |
| 6–10 | 定位 | Skill=协作/工程方法包；执行器负责实际编辑；安装 Skill ≠ 获得 EDA 能力；默认中文 |
| 12–18 | 安装与更新 | `skill_update.py check`"统一检查本 Skill **与 easyeda-agent** 的 CLI/Skill/daemon/Connector"；24h 缓存；不静默覆盖；升级须 idle；`update-agent --idle`；不宣称跨组件原子回退 |
| 20–23 | EasyEDA 生态工具接入 | `ecosystem.py registry/run`；唯一写入者；离线导入/审核不另开桥接器；差分几何通过 ≠ 阻抗/DRC 通过 |
| 25–32 | §0 产品落地层 | 完整 idea 任务链不在 DRC/BOM 后自行结束；按用户范围交付；生态复用需核对授权与执行能力 |
| 34–42 | §1 从效果开始 | 先读 Agent 协作契约；新手不问芯片/层数/封装；区分图纸/板子/固件 |
| 44–64 | 模式表 + 追问纪律 | 12 类意图→默认交付/边界（含"未回读不写验证通过"）；只集中问会改拓扑/接口/电源/机械的缺口；不自建额外审批 |
| 66–78 | 工程师口语表 | "先出方案/照参考/参考以前方案/加一路/走线粗一点/地分开/过一下/直接改/能打板"的落地任务 |
| 80–84 | 生态完整路线 | 优先立创开发板/开源参考，先核对型号/板版/许可；不把定制板偷换成买模块 |
| 86–92 | 商城与制造 | 中国大陆默认检索立创商城；建立"型号↔C号↔EDA身份↔BOM↔采购清单"映射 |
| 94–96 | 评审节奏 | 方案/原理图/布局/交付=四个**可见检查点**；默认自查汇报继续；**不把检查点变成权限停顿点** |
| 98–100 | 多 Agent | 默认单 Agent，最多 3 个；共享工程**唯一写入者**；冻结快照带工程/页身份+哈希 |
| 102–114 | §2 执行能力检查 | 纯方案不连 EDA；`easyeda health`（L108）；`python scripts/doctor_env.py --summary`（L110）；四分"工具存在/连通/工程可读/工程可写"；不静默安装；"不覆盖 easyeda-agent"（L114）；官方 CLI 适配器不发用户 JS/不下单/不联网 |
| 116–122 | 原理图执行与验收 | "拓扑与角色→实测符号→模块候选→整页候选→写入→官方导图复核"；**简单工程优先一页**；同失败机制两次即换方法；`sch_layout_check.py --strict`+`sch_text_audit.py --strict` 为验收口径，**不得用执行器 `layout-lint --strict` 替代**；`component_identity_check.py` 项；原生 gate/pin-net/身份/save→reopen/图面**分别报告** |
| 124–126 | 电源主干 | `power_routing.py audit/widen/corridor`；先定电流/铜厚/源负载/层；不把项目线宽/温升写成通用常量 |
| 128–130 | 提速 | `pcb_apply_plan.py --module-plan` 合批；一次读取→联合检查→一次 apply→保存重载；不为提速跳过身份/连接/DRC/最终保存重开 |
| 132–207 | §3 按需读取表 | 60+ 行"任务→reference"映射（本表是 SKILL.md 长度主因） |
| 209–222 | §3.1 内容库边界 | 设计卡 60 张 E1/E2/E3；常用硬件 A–M；具体值只在其条件内成立；数量不等于验证；D0/D1/D2 深度 |
| 224–234 | §3.2 G0–G6 | 门禁是**阶段退出证据门，不是审批门**；键名 `G0_requirements`…`G6_manufacturing`；**硬规则 G2未过不导入/布局 PCB、G3未过不布线、G5未过不谈制造、G6未过不说可打样**；`gate_check.py` 输出 PASS/PASS_WITH_WAIVER/BLOCKED/UNSUPPORTED；不可豁免项清单（L233）；**Gerber/钻孔/CPL 在 easyeda-agent v1.14.0 无 CLI/typed action，只能人工 GUI 导出**（L234） |
| 236–253 | §4 工程状态 | S0读取→S1需求→S2方案→S3原理图→S4 PCB→S5检查/交付；五状态词 `待确认/不满足/有条件满足/已验证/不适用`；分别报告核算/回读/几何DRC/仿真/实测 |
| 255–272 | §5 底线 1–13 | 型号精确（1）；逻辑脚/物理脚/焊盘区分（2）；范围+容差+温度（3）;**图面跟随电气意图、不为清 DRC 删保护/改网名/造假 NC**（4）；先源数据后执行、禁止整批盲重试（5）；**保留 identity/位号/uniqueId/封装绑定/锁定件**（6）；显式保存+重开确认（7）；项目手册优先于通用经验（8）；安规/市电/汽车医疗需专业签核（9）；商城/库身份/SMT 分验（10）；价格库存引用时间（11）；板版/BOM/固件/结构匹配（12）；平台正常路径、418/拦截先读日志（13） |
| 274–298 | §6 后台计算与自动化 | 各离线脚本的**边界声明**（不证明选型/稳定性/EMC；缺证据=BLOCKED；退出 0 ≠ 通过）；`eda_exec.py` doctor/read/apply/save/reopen-check；PCB 工具链（`pcb_preflight/pcb_apply_plan/pcb_gate/pcb_case`）+ `easyeda pcb dump --include-copper`（L296）；反馈闭环九子命令 + **五件事分离**（调用/写入/保存/重开/质量，L298） |
| 300–323 | §7 交付 | 新手交付卡；不要求小白确认技术正确；工程师 5 条交付格式；阻断/建议/提示 + 已证实/条件风险/待核实；"能打样吗"的五级交付级别 |

## 2. references 分组清单（治理面）

顶层 66 个文件（行数为字节数级摘录，不作版本比对依据）：

| 组 | 文件 | 治理内容 |
|---|---|---|
| 协作与流程 | `agent-collaboration.md`(14176)、`interaction.md`、`workflow.md`、`evidence.md`、`idea-to-product.md`、`product-acceptance.md`、`firmware-bringup.md`、`beginner-journey.md`、`review.md`、`troubleshooting.md`、`task-scenarios.md`、`project-coherence.md` | 角色/节奏/证据/验收/排障 |
| 执行与证据 | `eda-execution.md`(21854)、`eda-efficiency.md`、`execution-efficiency.md`、`offline-tools.md`(22919)、`offline-regression.md`、`feedback-loop.md`、`design-engine.md`、`ea-execution`相关命令映射 `pcb-command-map.json`(18212) | 读写协议、回读、缓存、离线输入契约 |
| 门禁 | `design-gates.md`(47186) | G0–G6 逐项检查、证据绑定、豁免规则（引 `easyeda ...` 命令 31 处） |
| 原理图 | `schematic.md`、`schematic-authoring.md`、`schematic-recipes.md`、`schematic-layout.md`(20689)、`schematic-layout-engine.md`(24559)、`schematic-benchmarks.md`、`schematic-lessons.md`、`schematic-details.md` | 绘图方法、排版、图面验收、经验 |
| PCB | `pcb.md`、`pcb-execution.md`(33459)、`pcb-routing-strategy.md`(28042)、`pcb-placement-details.md`、`pcb-routing-details.md`、`pcb-lessons.md`、`power-routing-preflight.md` | 布局/布线/铺铜/交付 |
| 制造与供应链 | `jlc-pcb-rules.md`、`jlc-smt-rules.md`、`jlc-production.md`、`jlc-handoff.md`、`lcsc-sourcing.md`、`part-selection.md`、`manufacturing-details.md`、`manufacturing-routes.md`(74741) | 厂规条件快照、BOM/CPL、购料 |
| 安装/客户端 | `installation-updates.md`(9836)、`client-compatibility.md`(8596)、`network-discipline.md`、`tool-gotchas.md`(46649)、`easyeda-ecosystem.md`、`ecosystem-*.md`(3) | 安装/更新/诊断/客户端矩阵/坑 |
| 领域与内容 | `domains.md`、`power.md`、`digital.md`、`analog-rf-highspeed.md`、`module-cards.md`、`module-integration.md`(74891)、`design-experience.md`、`domain-design-details.md`、`starter-patterns.md`、`enclosure-integration.md`、`sources.md`、`source-register.md`(164939)、`simulation-measurement.md`(77923) | 领域路由与资料 |
| 内容库子目录 | `design-cards/`(61)、`common-hardware/`(26)、`decisions/`(27)、`failures/`(34)、`engineering-deepdives/`(31)、`examples/`(13)、`projects/`(5)、`selection/`(7)、`thermal/`(4)、`calculations/`(5) | 设计卡/常用硬件/决策/反例/深潜/范例 |

## 3. 门槛与检查脚本（"哪些是 gate"）

| 脚本 | 角色 | 不可协商的语义（代码/文档定位） |
|---|---|---|
| `scripts/gate_check.py`(96KB) | 离线阶段门 G0–G6 | `REPORT_SCHEMA=design-gate-report/v1`、`STATE_SCHEMA=design-state/v1`、`WAIVER_SCHEMA=design-waivers/v1`；`GATES` 七键 L42–50；退出码 0/1/2 = 无阻断/有阻断/参数错 L7–10；缺证据判 BLOCKED（docstring L4–6 "never connects to EDA"） |
| `scripts/pcb_gate.py`(120KB) | 离线 PCB 交付门 PG1–PG8 | `PROFILES=('full','regression')` L46；`STAGE_IDS`=`PG1_placement…PG8_delivery` L60–69；状态 `pass/pass_with_gaps/fail/blocked/not_run` L47–51；"不能从 README 表宣布完成" docstring L1–18 |
| `scripts/sch_layout_check.py`(50KB) | 原理图几何/文字严格检查 | 设备/文字重叠、线穿、越页、`unowned_visible_text` L674、`duplicate_net_text` L690、`netflag_rotation_outlier` L705（消费输入 `orientation_policy` L698–716）、`zone_reading_order` L718–750、`title_block_duplicate_text` L764 |
| `scripts/sch_text_audit.py` | 实测可见文字关系 | 7 类 `TEXT_CLASSES`；"零 bbox 不证明不可见；不做字号估算或视觉 PASS" docstring |
| `scripts/component_identity_check.py`(419 行) | 重放后身份/BOM/SCH-PCB 一致性 | 输入必须是**已落盘的 easyeda 读取**（L6–8）；`BOM_KEYS` L25–29、`IDENTITY_KEYS` L30；不证明电气正确/网表等价（L10–14） |
| `scripts/feedback_loop.py`(676B) | 闭环入口 | 只读命令不写；`apply` 默认 dry-run；未回读不写通过（L9–12） |
| `scripts/pcb_preflight.py` / `pcb_apply_plan.py` / `pcb_case.py` | 放件前门 / 合批写入 / 整案证据 | preflight `ready/review/blocked`；apply 默认 dry-run；case 出 manifest（SKILL.md L296/L165） |
| `scripts/doctor_env.py`(446 行) | 跨客户端环境诊断 | **不测可写性**（L11–13）；检查客户端/技能目录/lceda-pro/easyeda/连通/授权副本可读 |
| `scripts/skill_selftest.py`(667 行) | 包自检 | 必需文件、相对链接、G0–G6 与四状态词在 SKILL/design-gates/gate_check 一致（L6–13）；不验证任何板 |
| `scripts/eda_exec.py`(236KB) | 官方 CLI 适配器 | `doctor/read/apply/save/export/drc/reopen-check`；只发固定受控动作 |
| `scripts/ecosystem.py` | 生态入口 | `registry`/`run`；只离线导入/审核/预览/查询 |
| `scripts/pcb_cli.py` | PCB 工具共用外壳 | 只跑 `easyeda` CLI（`EASYEDA_CLI` 测试缝 L24–26）；不写工程 |
| `scripts/design_engine_cli.py` | 离线确定性引擎入口 | `audit/plan-labels/compare/pcb-audit` 等 |

## 4. agents / cases / assets

- `agents/openai.yaml`(394B)：仅客户端展示元数据（interface/default_prompt 级别），无规则条文。
- `cases/`：`temp-alarm-2026-10-24`（含 `design-state.json`、`waivers.json`、`expected.json`、`actual.json`、证据 15 件）、`photo-led-pcb-2026-10-26`（完整 PCB 证据链 + `pcb-final-top/bottom.png`）、`mcu-i2c-s3-2026-10-26`（改板证据）、`dual-button-led-night-20261027/negative-direct-move`（**负例**：直接移动被拒绝的输入与基线）、`feedback-r12`（3 个反馈闭环案例）、`index.json`。功能：回归基准 + 负例，证明"拒绝"也是可交付行为。
- `assets/`：`design-state.example.json`、`pcb-delivery-checklist.md`、`manufacturing-profile.md`、`beginner-summary.md`、`sourcing-summary.md`、`review-summary.md`、`product-progress.md`、`design-calc.md`、`routing-plan.md`、`schematic-recipes.json`、`pcb-placement-templates.json` 及 `docs/`5 件、`decisions/`25 件等。

## 5. 不可协商规则汇总（我方持仓）

1. **身份保全**：位号/`uniqueId`/`component.uuid`/器件库身份/封装绑定/锁定件不得因排版或重建丢失（SKILL.md L262、L122；`component_identity_check.py`）。
2. **证据新鲜度与绑定**：证据须绑定 path/sha256/semantic_sha256/mtime/freshness_basis；早于最终板框或件数不一致→`STALE_EVIDENCE` 不得作 PASS（`design-gates.md` L59）。
3. **保存后必须重开回读**：`save` 成功、退出码 0、截图、离线 JSON 均不替代重开回读（SKILL.md L263、L298）。
4. **五件事分离**：调用/写入/保存/重开/质量，缺一即 `NOT RUN`/`unknown`（SKILL.md L298）。
5. **缺证据即 BLOCKED**：`gate_check`/`pcb_gate` 不默认通过；`UNSUPPORTED` 必须显式列出（`design-gates.md` L62–63）。
6. **不可豁免清单**：电气 DRC、网表审计、PCB DRC、关键网证明、保存重载、Gerber/BOM/恢复演练（SKILL.md L233；`design-gates.md` L61）。
7. **阶段硬序**：G2 未过不导入/布局 PCB，G3/G4 未过不布线，G5 未过不谈制造，G6 未过不说可打样（SKILL.md L231）。
8. **图面验收双轨**：`sch_layout_check --strict` + `sch_text_audit --strict` 不可被执行器 lint 替代，且必须看实际官方导出图（SKILL.md L122）。
9. **单一写入者**：共享工程/窗口只允许一个指定写入者（SKILL.md L100）。
10. **不伪造**：不为清 DRC 删保护/改网名/造假 NC；不把离线/截图/探针结果说成工程已完成（SKILL.md L260、L112）。
