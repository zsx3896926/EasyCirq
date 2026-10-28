# 上游 Skill 原始清单（easyeda-agent）

> 说明：本文件为审计证据（只读观察结果）。2026-10-27 21:30 曾修复过一次自动改写造成的反引号损坏，内容以本版为准。

审计对象：
- 源码克隆：`C:\Users\jlc\work\_round6-scratch\easyeda-agent-src\.agents\skills\easyeda-agent`
- 已安装副本：`C:\Users\jlc\.codex\skills\easyeda-agent`、`C:\Users\jlc\.claude\skills\easyeda-agent`
- 补充证据：`docs/toolchain-integration/evidence/env/`（本仓库已捕获的 CLI 版本/help/doctor，非本次运行）

## 0. 版本与身份

| 项 | 源码克隆 | 已安装（.codex / .claude） |
|---|---|---|
| `.version` 文件 | 不存在 | `1.15.0`（两份相同） |
| `SKILL.md` frontmatter version | `"1.14.0"`（L5–8） | `"1.15.0"` |
| `SKILL.md` 字节 / 行 | 6357 / 74 | 6583 / 74 |
| `SKILL.md` SHA256 | `70510AE0D89CB562A90CB775C7BB9C1A0B0BE5D0C684139F7D1A36237D519764` | `39894D33755666952AB67E8A0F95F62F8D6914C789082BA2F07E40CBDB713D42`（两份一致） |
| 文件数 | 189 | 193 |
| License | MIT（`LICENSE:1–3`，Copyright (c) 2026 zhoushoujianwork and contributors） | 同 |

`SKILL.md` 内容差异（v1.14.0 → v1.15.0）仅三处：`version` 字符串；「按任务读取」表新增 `exam-pcb-workflow.md` 一行；同表新增「由已有 PCB 生成 3D 打印外壳」一行。即**已安装副本比源码克隆新一个小版本**；本审计引用具体条文一律以已安装 v1.15.0 为准，行号与源码在 SKILL.md 上一致（74 行）。

## 1. 命令面（上游 CLI）

来自已捕获证据 `evidence/env/10-cli--help.txt`（`easyeda-agent v1.15.0`，`11-cli-version.txt`）：`easyeda [command]`，26 个子命令：
`actions, api, apply, audit, blocks, board, bom, call, completion, daemon, debug, doc, editor, health, help, lib, notify, pcb, project, sch, skill, spec, update, version, view, web, workflow（已废弃）`。
全局 flag：`--doc`（把写操作钉在指定页/PCB）、`--project`、`--window`、`--ports 60832-60841`、`--host`、`--force-stale-read`（deprecated）、`--skip-version-check`（deprecated）。
`evidence/env/12-cli-doctor.txt`：`unknown command "doctor" for "easyeda"` —— 上游**没有** `doctor` 子命令（诊断入口是 `health` 与 `update --check`）。

## 2. 工作循环（`SKILL.md:17–31`，8 步）

1. 明确供电/接口/机械/装配约束；授权内自主取舍（L19）。
2. 现场读写前 `easyeda health` 确认已打开的 Web EDA/工程/文档；**宿主要求 V4**（L20–21）。
3. 保留原始快照，核实库身份/引脚/网络/NC/几何/规则；未知不当空或 NC（L22）。
4. 在源副本中明确连接、外围归属、单位与约束，生成候选并检查预览（L23–24）。
5. 用当前 `--help`/`easyeda actions` 核对接口；**仅经 Cobra 子命令、typed action 或 `easyeda apply` 写入；同一窗口的调用串行执行**（L25–26）。
6. 回读身份/逐脚连接/实际几何；部分成功、超时或 stale ID 先回读再修源重算（L27）。
7. 稳定检查点显式保存；最终 `save → doc reload → fresh readback/render`，**必须布尔 `saved:true`**；`saved:false`/缺失/其他类型均为失败，外层 `ok:true` 与 autosave 不替代（L28–29）。
8. 交付结果/证据/未覆盖项；**检查、评分、版本或旧 `workflow/stage` 状态不作为普通动作许可**（L30）。

## 3. 硬规则与边界（`SKILL.md:32–47`）

- **禁止 GUI 自动化**编辑/保存/重载/验证，禁止 `debug.exec_js` 绕过缺失接口；接口缺失时停写并标 `unsupported/incomplete`（L34–35）。
- 原始观测不可改写；改源数据后重新生成受保护队列，不手改队列/SVG/回读掩盖差异（L36）。
- 相近型号须核对引脚/封装；多变体未支持选择时拒绝，不默认取第一项（L37）。
- **原理图用 raw、y 向上、5 raw 网格；PCB 命令通常用 mil**；明确原点/anchor/bbox 语义（L38）。
- 保留全部物理脚与明确 NC；`netAmbiguous:true` 不得转成未连接；同名网络/同框/高分不能代替实际直连（L39–40）。
- 位号参与碰撞与入框检查；其余属性保留原值；**最终导图仍须检查全部可见文字，不能由零碰撞推断无叠字**（L41）。
- PCB 按真实机械/回流/器件要求布局；缺测不等于空；**完成前连续两轮自检，第二轮含保存重载与新回读，修复后重来**；**展示最新回读版本并获用户确认后才进入整板布线；确认前仅允许规则范围内的电源模块局部连接**（L42–44）。
- 临时隐藏属性只能走可恢复 typed 视图接口，保存旧值/恢复/回读（L45）。
- DRC/连接/几何/图面分别说明覆盖；**原生 `pcb drc` 的 `passed:false` 是失败，SCH 的 INFO 不等于错误**；离线通过/导出成功/截图不能代替现场持久化、制造或硬件验证（L46–47）。
- 状态词：`source-only`/`offline-verified`/`live-verified`，候选 `candidate-unverified`/`candidate-rejected`，未实现 `planned`/`unsupported`（L70–71）。
- 修改 Skill 后运行 `python3 scripts/pack-skill.py --check`（L73–74）。

## 4. 安装 / 配置 / 运行时假设

| 主题 | 上游条文 |
|---|---|
| 宿主版本 | EasyEDA Pro V4 主线；最低识别 4.0.0，推荐已验证 4.1.60+；`health.hostCompatibility` 的 V3 `block` / 老 V4 `warn`（`environment-setup.md:6–12`） |
| 版本对齐 | CLI/daemon、Skill、EDA Agent Connector **三件套**；CLI/daemon/Skill 精确同版，Connector 按 major.minor 兼容线（`:51–53`） |
| 正式安装 | `curl … install.sh \| bash` 或 Windows `irm … install.ps1 \| iex`；`easyeda update --check` / `easyeda update`（`:55–68`） |
| 更新语义 | `update --check` 是显式只读对账、"不是每次 EDA 操作的前置许可"；`--check --exit-code`：满足=0/差异=10/查询失败=1（`:70–73`） |
| 升级顺序 | `easyeda update` → 停旧 daemon → `easyeda daemon start` → 纯 patch 保留 Connector；跨 minor/major 才取 `.eext` 卸载重导并完全退出重开 EDA（`:84–93`） |
| Windows 默认目录 | `%USERPROFILE%\.local\bin`；`EASYEDA_INSTALL_DIR`/`CODEX_HOME`/`CLAUDE_CONFIG_DIR`；`-AddToPath` 才写 PATH（`:100–110`） |
| Connector 渠道 | GitHub Release `.eext` 侧载 或 立创插件市场；同一 profile 只保留一种；需在扩展设置启用"允许外部交互"（`:132–151`、`:153–158`） |
| daemon 生命周期 | `easyeda daemon stop` / `daemon restart --auto-update-skill=false`；PID/端口、`.easyeda-agent` 权限；不盲杀进程（`:274–297`） |
| 读取预算 | 普通动作 20s；`document.open` 30s；`components.list --include-pins` 150s；身份读取 60s（`:299–305`、`:318–325`） |
| 缓存纪律 | `windowId` 非持久身份，用 project/doc UUID 路由；同次读取复用解析输入，**不跨请求/页面缓存来源证明**（`:229–247`、`:299–302`） |
| 源码安装 | 源码规范源即 `.agents/skills/easyeda-agent/`；`scripts/install-agent-skills.py --scope design --dry-run`（`:17–24`） |

## 5. references / scripts 清单（源码克隆）

顶层 `.md`（治理面）：`design-flow.md`(172)、`actions.md`(330)、`environment-setup.md`(325)、`schematic.md`(322)、`schematic-data.md`、`schematic-placement.md`、`schematic-wiring.md`、`schematic-layout-conventions.md`(382)、`auto-layout-sop.md`(233)、`pcb.md`(264)、`pcb-layout.md`、`pcb-layout-conventions.md`(549)、`pcb-routing.md`、`pcb-config.md`(88)、`pcb-design-rules.md`(704)、`part-selection.md`(257)、`library-authoring.md`(87)、`reusable-module-library.md`、`standard-blocks-contributing.md`、`module-owned-objects.md`、`project-import.md`(148)、`document-source.md`(78)、`design-decisions.md`(111)、`design-pre-analysis.md`(28)、`design-drawings.md`(83)、`beginner-troubleshooting.md`(151)；v1.15.0 另加 `exam-pcb-workflow.md`。
JSON 资产：`orientation.json`(3071)、`standard-parts.json`(67572)、`sheet-templates.json`、`fab-rules-jlcpcb.json`、`symbol-pins.json`(42109)、`library-device-example.json`、`drawings-input.example.json`。
子目录：`examples/`（`260919-at32f415/` 大量 live JSON/SVG/manifest、`index.md`、`exam-differences.md`）、`library/modules/`（14 个 topology/layout JSON + catalog）、`scripts/`（`lint.py`、`bulk-place.py`、`bulk-connect.py`、`parts-select.py`、`parts-relocalize.py`、`parts-add.py`、`bom-enrich.py`、`orient.py`、`diff.py`、`sch.py`、`audit-baseline.py`、`blocks-pin-audit.py`、`modules-audit.py`、`calibrate.js`、`probe.js`、`validate_260919_can_plan.py` 等）。
`agents/openai.yaml`：`display_name: EasyEDA Agent`；`default_prompt: "Use $easyeda-agent to design or safely refactor an EasyEDA schematic/PCB, preserving topology and applying strict layout and electrical gates."`

## 6. 可引用的执行器事实（详见主报告 §4.3）

| 事实 | 定位 |
|---|---|
| 原理图 raw=0.01in=0.254mm；5 raw 硬网格；整页 10 raw；A4 随 build 变 | `schematic-layout-conventions.md:14–24` |
| PCB 单位 mil；y-UP；`x/y`=锚点，规划用 bbox center，写用 `--center`；旋转与 center 不得同调 | `pcb.md:34–35`；`pcb-layout-conventions.md:19–24` |
| PCB 栅格 25/50/5 mil；旋转仅 90° 步进 | `pcb-layout-conventions.md:23,461` |
| 布局冲突裁决 P0–P7；跨维度裁决 7 条 | `pcb-layout-conventions.md:72–87,514–524` |
| 九宫格分区自述"历史参考"；"默认先完成一页"，分页是功能设计决策 | `schematic-layout-conventions.md:27–59,64,77` |
| netflag 朝向 `frozenTable` + 两次校准记录 | `orientation.json` |
| `uniqueId` 命名空间/空串/重载后重铸；`replace` 保留 `uniqueId` | `pcb-layout.md:14`；`schematic-data.md:156–159,676–678,749–755`；`actions.md:108,114` |
| 保存必须布尔 `saved:true`；autosave 不构成证据 | `actions.md:84–92` |
| 原生 DRC 布尔语义；`countsAvailable`；`null` 不得填 0 | `actions.md:327–330` |
| DRC 清单 FATAL/ERROR/WARN（0.10mm/0.15mm/Mark≥3 等） | `pcb-design-rules.md:668–693` |
| 无编程 undo；改前重取 `primitiveId`；`delete` 布尔只表示操作完成 | `pcb.md:40–41` |
| `staleRisk` 只诊断；最终用 save→reload→readback | `design-flow.md:150–154` |
| 事前摸底"可选，不是门禁"；>~80 件考虑多页 | `design-pre-analysis.md:1–5,19` |
| "检查不负责许可下一步"；旧 workflow/stage 仅兼容 | `design-flow.md:18–19` |
| 两轮自检 + 用户确认后才布线 | `design-flow.md:95,123–133`；`SKILL.md:43–44` |
| 新手排障五原则 | `beginner-troubleshooting.md:6–12` |
| `deviceUuid` 按当前版本重解析、只写副本 | `part-selection.md:199–233` |
| MIT 许可 | `LICENSE:1–3,20–28` |

## 7. 上游明示、但产品化后应隐藏的运行时细节

`easyeda health`、V4 hostCompatibility、daemon start/stop/restart、端口段 60832–60841、`windowId`/`STALE_WINDOW`/`NO_CONNECTOR`、`.eext` 侧载与插件市场、扩展管理器"允许外部交互"、`.easyeda-agent` 目录权限、PID 文件、`web reload`、`readbackScope`、读取预算秒数、`--force-stale-read`/`--skip-version-check` 兼容开关。
定位：`SKILL.md:20–21`；`environment-setup.md:132–151,229–325`；`10-cli--help.txt:35–43`。
