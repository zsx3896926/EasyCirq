# 智构 × easyeda-agent：规则级冲突审计（阶段 1：只审计，不改 Skill）

- 审计对象 A（我方，权威）：`C:\Users\jlc\work\zhigou-toolchain\easycirq`（分支 `feat/integrated-eda-toolchain`，基线 `9a951ed`，`.version`=1.0.1）
- 审计对象 B（上游）：`C:\Users\jlc\work\_round6-scratch\easyeda-agent-src\.agents\skills\easyeda-agent`（v1.14.0 源码快照）+ 已安装 `C:\Users\jlc\.codex\skills\easyeda-agent`、`C:\Users\jlc\.claude\skills\easyeda-agent`（**实际为 v1.15.0**，见 §2.3）
- 原始清单与逐项证据：`docs/toolchain-integration/evidence/skill-audit/`（`01-our-skill-inventory.md`、`02-upstream-skill-inventory.md`、`03-installed-copies-compare.md`）
- 本文件只做判定与方案，**未修改任何 Skill / 安装目录 / 上游克隆，未运行任何 EDA 命令**。

---

## 1. 结论摘要（TL;DR）

1. **冲突 46 条**：按处置分——**智构保留 12 条**（自有规则，上游无对应或对方更弱）、**改造 19 条**（吸收上游事实/细节但规则归我方）、**废弃 7 条**（上游规则与目标相反或已过期）、**引用 8 条**（纯执行器事实，只作出处）。其中 5 条（C42–C46）来自审计中途发现的自研 `runtime/`、`connector/` 现场（见 §2.3、C42–C46）。
2. **最危险的三条不是技术细节，而是默认行为相反的顶层语义**：
   - 上游把门禁当"报告"（`design-flow.md:18–19`："check/DRC/连接/几何/评分分别报告事实，**不负责许可下一步**"；`design-pre-analysis.md:1`："可选，**不是门禁**"），我方把门禁当"阶段退出证据门"（`SKILL.md:231`：G2 未过不导入/布局 PCB，G3/G4 未过不布线，G5 未过不谈制造）。
   - 上游把**用户确认**设为布线硬前置（`SKILL.md:43–44`、`design-flow.md:95`），我方明确"检查点**不是审批门**"（`SKILL.md:94–96`、`L62`）。
   - 上游整套工作循环自称"独立设计"（`SKILL.md:13–16`），我方定位是"Skill 出政策、执行器只执行"（`SKILL.md:8`、`L114`）。若两者同装，模型会随机遵循其中一套。
3. **两套技能现在确实同时在客户端可见**：本会话可用技能清单同时列出 `easycirq` 与 `easyeda-agent`；上游在 `~/.codex` 与 `~/.claude` 各有一份完全相同的 v1.15.0（聚合 SHA256 均为 `15AE1F60…213C75`）。因此"只加载一套"必须由**安装器移除/禁用上游 Skill 目录**落实，不能只靠 SKILL.md 里的措辞。
4. **真正的阻塞不在 SKILL.md 文档，而在新执行器与"单 Skill"目标的接口**：自研 `runtime/`（vendored Go，rebrand 后二进制 `zhigou`、端口 23111–23120、状态目录 `~/.zhigou`）**仍在 daemon 启动时自动从 `zhoushoujianwork/zhigou-agent` 同步一套名为 `zhigou-agent` 的技能**（`cmd_skill.go:17–22` + `selfupdate.go:31–33`），并硬编码从 `skills/zhigou-agent/references/` 读 4 个数据资产（`standard-parts.json`、`orientation.json`、`sheet-templates.json`、`bom-enrich.py`）——**这 4 个资产我方 `easycirq/` 一个都没有**。若不在 runtime 侧修改，则要么装出第三套技能、要么 block-apply/朝向/图纸模板/BOM 富化 全部无数据来源（C42、C44）。
5. **我方 SKILL.md 已 323 行**（非派单说的 231 行），其中 132–207 行的 60+ 行"按需读取表"是长度主因；全文有 12 行含 `easyeda`（共 14 次出现），references 侧 `design-gates.md` 31 处、`pcb-routing-strategy.md` 27 处、`pcb-execution.md` 22 处硬绑上游 CLI —— 改名 `zhigou` 与"单一规则源"的工程量主要在 references，不是 SKILL.md 本身。
6. 上游可安全引用的只有**执行器事实**（单位/锚点/`uniqueId` 命名空间/原生 DRC 布尔语义/读取预算/朝向表等 20 项，见 §4.3），且必须带 **MIT + 版本 + 文件:行** 出处；**其工作流、门禁叙事、用户确认停顿、固定阈值不得引用为规则**。

---

## 2. 方法与证据口径

### 2.1 读取方式
- 文本文件一律用 read/grep/glob 读取；PowerShell 仅用于目录列举、`Get-FileHash`、`Compare-Object`、字节比对。
- 上游规则以 **v1.15.0 已安装副本**为准（`SKILL.md` 74 行；行号与 v1.14.0 源码在 SKILL.md 上一致，差异仅 3 处，见 `03-installed-copies-compare.md §3`）；引用 references 时给已安装副本行号。

### 2.2 判定词
- **冲突**：两者对同一动作给出相反的默认/硬规则。
- **重叠**：结论一致但表述或归属不同（需合并防漂移）。
- **缺口**：一方有、另一方无（决定由谁补）。
- 决定列只用四个词：**智构保留 / 改造 / 废弃 / 引用**（括号内说明处置细节）。

### 2.3 版本事实（影响引用有效性）
| 事实 | 证据 |
|---|---|
| 源码克隆 = v1.14.0（无 `.version`，frontmatter `"1.14.0"`） | `02-…inventory.md §0` |
| `.codex`/`.claude` 安装副本 = **v1.15.0**，193 文件，两份逐文件一致 | `03-…compare.md §2` |
| SKILL.md v1.14→v1.15 仅变 version + 2 行任务索引；references 有 12 个文件内容有实质差异（`pcb.md` +7128B 等） | `03-…compare.md §3` |
| 本机 CLI 实为 `easyeda-agent v1.15.0`；`easyeda doctor` **不存在** | `docs/toolchain-integration/evidence/env/11-cli-version.txt`、`12-cli-doctor.txt` |
| 我方 SKILL.md `L234` 仍写 "easyeda-agent **v1.14.0** 没有 Gerber CLI" → 与现状不同步 | `SKILL.md:234` |
| 自研执行器**已落地但在建**：`runtime/`（vendored + rebrand，`dist/zhigou.exe` 23.9MB，mtime 21:22）、`connector/`（`zhigou-connector` uuid `a6e6b788…6e31`，e0.1.0）、`protocol/`；三者均 git 未跟踪，审计期间仍在写入 | `evidence/skill-audit/04-runtime-connector-observation.md`；`git status` |

> **并发提示**：`runtime/`、`connector/`、`protocol/`、`distribution/rebrand_*.py` 在本审计执行期间由并行工作流写入（mtime 21:22）；本文件的 runtime 结论均带"截至 2026-10-27 21:25"时点，定稿后须复核 C42–C46。

---

## 3. 冲突表

> 说明：`我方` 指 `easycirq/`；`上游` 指已安装 `easyeda-agent/`（v1.15.0）。所有"文件:行"均按本机实测行号。
> 实现位置中 `(TBD)` 表示依赖尚未落地的 runtime/安装器结构；本 worktree 目前只有 Skill，没有 runtime 代码。

### (a) 加载哪一套、以谁为准（规则归属）

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定(智构保留/改造/废弃/引用) | 适用条件 | 技术限制 | 实现位置(新仓库路径) |
|---|---|---|---|---|---|---|---|
| C01 | 我方 `SKILL.md:3`（description 写"配合 easyeda-agent 等工具实际绘图"）、`L8`、`L114`；上游 `SKILL.md:2–3`、`agents/openai.yaml:1–5`（default_prompt 让模型"用 $easyeda-agent 设计/重构并施加 strict gates"）；现场证据：本会话技能清单同时含两者、`~/.codex`+`~/.claude` 双份 v1.15.0 | **两套 Skill 同时被客户端发现**，触发词/描述高度重叠（都声称做原理图/PCB 设计） | 同一次请求两套规则竞争；模型按加载序随机择一；我方 G0–G6 可能被上游"checks 不授权"抵消；用户困惑 | **智构保留**（唯一入口）：我方 SKILL 独占政策；上游 Skill 不再作为"技能"安装/加载，只作为 runtime 内部不加载的依赖 | 所有已装客户端的机器 | 客户端技能发现是目录级，SKILL.md 内部无法互斥；必须由安装器删除或禁用 `~/.codex、~/.claude、~/.agents/skills/easyeda-agent` | `installer/ (TBD)`；`easycirq/SKILL.md:3` 改写描述 |
| C02 | 我方 `SKILL.md:8`（"此 Skill 是协作与工程方法包；EDA 执行 Skill/CLI/连接器负责实际编辑"）、`L114`（"不覆盖 easyeda-agent…执行细节服从当前工具协议"）；上游 `SKILL.md:13–16`（"依据需求与器件资料**独立设计**；模型可选择器件、功能划分及几何生成方法"）、`design-flow.md:25–28` | 上游把自己写成**设计决策者**（选型/功能划分/几何方法），我方把政策收归 Skill | 选型（立创商城/C 号/替代分级）、布局方法、验收标准出现两套并行版本 | **改造**：智构 Skill 独占设计政策；上游文本降级为"执行器自述"，仅保留其 API 边界 | 全部设计类任务 | 上游 references 仍会被 runtime 安装包携带；需在包内不暴露为技能 | `easycirq/SKILL.md` 新增"角色契约"段；`references/executor-protocol.md (TBD)` |
| C03 | 上游 `agents/openai.yaml:5`（"strict layout and electrical gates"）、`SKILL.md:30`（"检查…不作为普通动作许可"）；我方 `scripts/gate_check.py:42–50`、`references/design-gates.md` | 两边都用"gate/strict"字样但语义相反 | 用户与模型对"gate"含义混淆；报告字段可能被张冠李戴 | **引用**（上游 default_prompt 仅作模板线索）；"gate"术语统一到我方 G0–G6/PG1–PG8 | 对齐术语时 | 无 | `references/design-gates.md`（术语表） |
| C04 | 上游 `SKILL.md:5–8`（author/version/homepage）、`LICENSE`；我方 `.version:1.0.1`、`CHANGELOG.md` | 两个版本号域（Skill 版本 vs 执行器版本）并列且互相引用 | 升级/回退时混用版本；报告写错组件版本 | **改造**：SKILL 只暴露一个 `zhigou version`；两版本映射移入 references | 安装/升级/排障 | 需 runtime 提供统一 `version` 输出 | `references/version-and-install.md (TBD)`；`zhigou CLI (TBD)` |
| C42 | 自研 runtime：`runtime/internal/app/cmd_skill.go:17–22`（"daemon runs `skill sync` automatically on startup… on by default"）、`runtime/internal/selfupdate/selfupdate.go:31–33`（`RepoSlug="zhoushoujianwork/zhigou-agent"`、`SkillName="zhigou-agent"`）、`runtime/internal/app/cmd_update.go:196–229`（skill 目录同步）；我方 `SKILL.md:8,114`、目标"只加载一套技能" | **运行时会自动安装/同步第三套技能 `zhigou-agent`**（到 `~/.claude、~/.codex、~/.agents/skills/`），且来源是外部仓库的 `skills.tar.gz` | 用户机上出现 `easycirq` + `zhigou-agent`（+ 残留 `easyeda-agent`）三套；上游规则借我方品牌回流；离线/内网环境下载失败产生噪声 | **废弃**（关闭默认 auto-skill-sync；移除 `skill` 命令的安装能力；安装器绝不创建 `zhigou-agent` 目录） | 出厂默认 | runtime 为 vendored Go 模块，需改 `cmd_skill.go`/`selfupdate`/daemon 启动参数后重建；`skill_asset.resolve` 依赖 `selfupdate.Targets`，改目录名要同步改 §C44 | `runtime/internal/app/cmd_skill.go`、`runtime/internal/selfupdate/selfupdate.go`、`runtime/internal/daemon`（本仓库，在建） |

### (b) 前置检查与写后验证

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C05 | 我方 `SKILL.md:231`（"G2 未过不导入/布局 PCB；G3 未过不布线；G5 未过不谈制造；G6 未过不说可打样"）、`gate_check.py:42–50`、`SKILL.md:296`（"preflight 的 `review` 不是通过"）；上游 `design-pre-analysis.md:1–5`（"**可选，不是门禁**…布局智能交给 AI 用数据+截图自调"）、`design-flow.md:18–19`（检查"不负责许可下一步"）、`10-cli--help.txt:33`（`workflow` 已废弃） | **前置门禁是否必需**：我方硬序；上游明确取消 | 若沿用上游默认，会回到"读完直接落坐标、布完再补声明"的返工路径（我方 `design-gates.md:155/181` 有真实反例） | **智构保留**（蓄意差异：门禁是**证据门**不是审批门） | 非平凡项目强制执行；小修改以工程记录代 G0 | 执行器不产出我方证据格式，需适配层把原始回执映射为 evidence JSON | `references/design-gates.md`；`zhigou evidence (TBD)` |
| C06 | 我方 `SKILL.md:294`（`apply --dry-run` 只对账）、`L130`（批量默认 dry-run）；上游 `SKILL.md:25–26`（"支持 dry-run 时先检查"）、`pcb.md:49–51`（"先 dump→离线 layout-plan→选择后经 apply 串行写入，禁止现场逐件试摆"） | 写入前干跑：两边都是默认，但企业语义不同（我方把 dry-run 结果当"对账证据"，上游当"预检"） | 低（结论一致）；但"dry-run 通过"是否可计入证据需明确 | **改造**（合并：dry-run 属预检证据，不计入 PASS；写入后必须回读） | 所有写操作 | dry-run 覆盖度由 runtime 决定 | `references/eda-execution.md`；`scripts/pcb_apply_plan.py` |
| C07 | 我方 `SKILL.md:263`（"`save` 返回成功、截图或离线 JSON 都不能代替重开回读"）、`design-gates.md:59`；上游 `SKILL.md:28–29`（"必须返回布尔 `saved:true`；`saved:false`、缺失或其他类型均为失败"）、`actions.md:84–92` | 写后验证：**重叠但判据不同**——上游把 `saved:true` 当必要条件，我方只否定"返回成功=通过" | 漏掉"返回值类型校验"会放过 `saved:"true"`/缺失字段的场景 | **改造**（取 AND：`saved===true` **且** save→reload→fresh readback 一致才记持久化证据） | 所有落盘验收 | 需 runtime 返回结构化 `saved`；不得用 autosave 替代 | `references/eda-execution.md`；`scripts/feedback/`（verify） |
| C08 | 我方 `design-gates.md:59`（证据绑定 path/sha256/semantic_sha256/mtime/freshness_basis；早于最终板框或件数不一致 → `STALE_EVIDENCE` 不得作 PASS）；上游 `design-flow.md:150–154`（"`staleRisk` 提示宿主缓存风险，但**不拒绝读取**；即时结果可用于诊断"）、`pcb.md:188–237` | 带 `staleRisk` 的读数**能否当证据** | 用陈旧读数通过 DRC/几何门 → 假 PASS；反之过度保守会阻塞交付 | **智构保留**（诊断可用、证据必须 fresh；吸收"staleRisk 不阻断读取"为执行器事实） | 一切 PASS 判定 | 执行器不输出 `semantic_sha256`，需我方证据层计算 | `scripts/pcb_gate.py`、`scripts/pcb_evidence.py`、`references/design-gates.md` |
| C09 | 上游 `SKILL.md:43–44`（"完成前按布局规则通过连续两轮自检…**展示最新回读版本并获用户确认后进入整板布线；确认前仅允许规则范围内的电源模块局部连接**"）、`design-flow.md:95,129–133`；我方 `SKILL.md:94–96`（"默认在任务已授权范围内自查、汇报并继续…**不把工程检查点一律变成权限停顿点**"）、`L62`（"不自建额外审批"）、`L77`（"直接改/一直做到 DRC → 自主推进"） | **用户确认是否布线硬前置** | 与用户"直接做到 DRC"的授权直接冲突；每次布局后强制停等，破坏"检查点非审批门"的产品主张 | **废弃**（上游强制确认停顿）；保留"用户说评审/这步给我看时才停" | 用户已授权推进；用户显式要求评审时例外 | 无（纯流程语义） | `easycirq/SKILL.md` §1 评审节奏 |
| C10 | 上游 `design-flow.md:123–133`（连续两轮自检状态机；任一修正**清零重来**；第 2 轮含 `save→reload→fresh dump→fresh render`）；我方 `SKILL.md:296`、`scripts/pcb_gate.py:60–69`（PG1–PG8 阶段证据，无"连续两轮"语义） | 布局完成证据的**计数规则**：上游"连续两轮无修正"，我方只要求各阶段证据齐 | 首轮带问题、次轮修好仍可能被判"通过" | **改造**（吸收"修正即清零"为 PG2_layout 的证据计数规则） | 有布局阶段的项目 | 需 gate 记录轮次与修正事件 | `scripts/pcb_gate.py`（PG2）+ `references/pcb-execution.md` |

### (c) 坐标 / 单位 / 旋转

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C11 | 我方 `references/design-engine.md:37`（原理图 `sch_unit`=0.01in，100 unit=1in）、`schematic-recipes.md:17`（raw、y-up、5-raw 网格）；上游 `schematic-layout-conventions.md:14–24`（raw=0.01in=0.254mm；硬连接网格 5 raw；整页 10 raw；A4≈1170×825 随 build 变） | 单位/网格约定 | 两处独立表述，版本漂移后可能不一致 | **引用**（上游为执行器 API 事实）+ 我方保留规则表述 | 一切原理图几何 | A4 尺寸不得硬编码（上游已明确随 build 变） | `references/offline-tools.md`、`schematic-recipes.md` |
| C12 | 我方 `references/pcb-execution.md:38,287`（mil、y-up、`x/y`=footprint anchor）；上游 `pcb.md:34–35`（mil；anchor≠bbox center；`pcb modify --center` 转换；**同一次调用不得同时改旋转**）、`pcb-layout-conventions.md:19–24` | PCB 单位与 MVP 语义 | 旋转与 center 同调会导致偏移（上游 #105 实测） | **改造**（吸收"先旋转、再 center"两段式写入约束） | 有旋转的放件 | 需 runtime 提供 `--center` 等价能力 | `references/pcb-execution.md`、`scripts/pcb_apply_plan.py` |
| C13 | 上游 `pcb-layout-conventions.md:23`（SMD 默认 25 mil / THT 50 mil / 精密 5 mil 栅格）、`:461`（"旋转 ∈ {0,90,180,270}，无任意角"——**硬规则**）；我方 `references/design-engine.md:145`（`allowed_rotation` 只是可声明的约束类型） | 旋转步进是**全局硬规则**还是**项目级约束** | 无约束时产生任意角 → 贴片漂移/工艺问题；但把 90° 写成物理定律又会压死结构件 | **改造**（默认一律 90° 步进；180/270 需 pin-1/极性或结构理由；例外必须记录，不作"通用常量"） | PCB 放件 | 结构件/连接器可能合法使用特殊角 | `references/pcb-placement-details.md`；`scripts/design_engine_cli.py`（pcb-constraints） |
| C14 | 上游 `references/orientation.json`（`_doc` + `frozenTable`：power/ground/port × up/left/down/right；记录 2026-06-29 与 2026-08-12 两次现场重校准）；我方 `scripts/sch_layout_check.py:698–716`（消费输入的 `orientation_policy`；**仓库内无该表**，缺表则跳过） | netflag 本体朝向的**单一真源**：上游有一张带校准历史的表；我方检查依赖外部传入 | 无表 → 检查静默跳过（`checks_skipped`），"朝向检查通过"实为未跑；或双方各硬编码一份而漂移 | **引用**（表值 + 校准日期作为执行器事实）+ **改造**（落到我方仓库 `references/orientation.json` 并带 provenance；判定仍由我方执行） | 原理图网标/电源标记 | 表与宿主版本强相关（上游记录 3.2.149/connector 0.24.3），须随宿主重校；runtime 也按该文件名读取（C44） | `easycirq/references/orientation.json (TBD，MIT 引用)`；`scripts/sch_layout_check.py` |

### (d) 一页 vs 多页、文字重叠、功能分区

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C15 | 我方 `SKILL.md:120`（"简单工程优先一页，按信号方向组织主链、供电/参考放辅助行"）、`references/schematic-layout.md:11`（页面预算先定）；上游 `schematic-layout-conventions.md:64,77`（"默认先完成一页"；"分页是功能设计决策，不是框尺寸不足时的自动退路"） | 一页优先 | 无实质冲突（表述互补） | **智构保留** | 全部原理图 | 无 | `easycirq/SKILL.md` §4 |
| C16 | 上游 `design-pre-analysis.md:19`（"`Σ主器件bbox+辅助×~80×80+余量`，**>~80 件考虑多页**"）、`pcb-layout-conventions.md:319–320`（实战 82/100/122 件分页）；我方 `schematic-layout.md:11`（"确需拆页时…注明空间/阅读/隔离/独立子系统等具体理由"）、`references/eda-efficiency.md:170`（先按功能分页，再页内分区） | 多页**触发判据**：上游给数量启发式，我方只要求理由+记录 | 两边都无量化阈值 → 新手/模型可能"为省事拆页"或"硬塞一页" | **改造**（把"件数/面积超阈值→**触发评估**"写成启发式，理由与已尝试方案仍必须落记录） | 中大型原理图 | 阈值不是硬门槛，不得反向作为拆页许可 | `references/schematic-layout.md` |
| C17 | 上游 `schematic-layout-conventions.md:27–59`（九宫格：电源左列、MCU 居中、RF/传感器/IO 右列、大模块角落；real-world overrides 允许 MCU 迁角落）；我方 `SKILL.md:118`（"先排器件/局部导线，再按实际内容生成分区框，**不把器件硬塞进预画的等宽框**"）、`schematic-layout.md:35`（按阅读顺序，电源输入→转换→负载）、`scripts/sch_layout_check.py:718–750`（`zone_reading_order` 以**声明的 order** 为准） | 功能分区：上游给**固定格位**，我方按内容+声明顺序 | 硬套格位会造成绕线与框不匹配；反之缺省又容易"任意摆放" | **废弃**上游格位硬分配；**智构保留**"电源在输入侧、信号单向流"软目标 + 声明式 `order` | 新建/整理原理图 | 上游自身也声明九宫格"不是当前算法"，引用它作硬规则属误用 | `references/schematic-layout.md`；`scripts/sch_layout_check.py` |
| C18 | 我方 `SKILL.md:122`（`sch_text_audit.py --strict` + `sch_layout_check.py --strict` + **必须看实际官方导出图**）、`schematic-layout.md:15`（停止交付条件：遮脚/遮字/文字相压/导线穿文字…）；上游 `SKILL.md:41`（"最终导图仍须检查全部可见文字，不能由零碰撞推断无叠字"）、`design-flow.md:63`、`schematic-data.md:82–83`（位号不得被遮挡） | 文字重叠验收 | 结论一致 | **智构保留**；上游表述作为**引用支持**（证明该要求有上游同源） | 含可见文字的原理图 | 上游无独立文字审计工具，不能替代我方脚本 | `easycirq/SKILL.md` §4 |
| C19 | 上游 `schematic-layout-conventions.md:66–76`（框=粉色虚线、标题粉色、字高 0.2in=20 raw；包络含必检文字；先最小化框高；距实测内边框≥10 raw；**重复执行不得叠加框**）；我方 `SKILL.md:157`（写 module frame 前跑 `sch_frame_meta_check.py` 补 `order`/`purpose`，**缺 purpose 默认 blocked**）、`schematic-layout.md:39`（"框线可沿项目风格使用，不强迫所有块同尺寸，不在模块外再套多重装饰框"） | 模块框：上游固定样式/字号，我方项目风格自由 + 元数据必填 | 固定样式与项目风格冲突；但"不叠加/包络含文字/最小化框高"是硬几何规则，我方未显式写 | **改造**（保留我方元数据门与风格自由；吸收"包络含必检文字、最小化框高、10 raw 内边框、禁重复叠加"为几何规则） | 有 module frame 的原理图 | 样式参数不能跨项目固化 | `references/schematic-layout.md`；`scripts/sch_frame_meta_check.py`、`sch_layout_check.py` |
| C20 | 上游 `schematic-layout-conventions.md:119–128`（每个需连接的 pin 必须非零长度引出；**严禁零长度 wire 占位**——实测 204 条 wire 中 149 条零长占位会被 DRC 逐条报错）；我方 `schematic-layout.md:13`（"局部…优先短线"）但无零长禁令 | 零长度导线禁令 | 生成式布局容易产出零长占位 → DRC 噪声成片 | **改造**（吸收为显式检查项 + SKILL 一句话） | 程序化/模板化绘图 | 需在写入计划编译期 assert `(x1,y1)!=(x2,y2)` | `scripts/pcb_apply_plan.py` 同类校验；`scripts/sch_compose_input.py`；`references/schematic-authoring.md` |

### (e) DRC / 检查门禁与证据新鲜度语义

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C21 | 我方 `SKILL.md:231`、`scripts/pcb_gate.py:1–18`（"PCB 交付不能从 README 表宣布完成"）；上游 `design-flow.md:18–19`（"check、DRC、连接、几何和评分分别报告各自观测到的事实，**不负责许可下一步**"）、`SKILL.md:30` | 检查的**规范力**：报告 vs 门 | 同一份 DRC 结果，一边允许继续，一边阻止下一步 | **智构保留**（门禁语义由我方定义） | 阶段推进 | 上游 `--gate`/`workflow` 已废弃，不能作为门 | `references/design-gates.md`；`scripts/gate_check.py` |
| C22 | 我方 `SKILL.md:122`（"**不能用执行器的 `layout-lint --strict` 替代**这两项"）；但我方 `references/design-gates.md:124` 又把 `easyeda sch gate` 列为组合入口证据；上游 `design-flow.md:78`（"`sch gate` 可作为旧版聚合报告入口，但**不授权写入，也不替代**目标连接表和逐页完整几何回读"） | 谁是对账真源：我方脚本 vs 执行器 lint | 我方文档自相矛盾；若默认吃执行器 lint 分会把"分数通过"当验收 | **改造**（明确分层：执行器 lint = 输入/诊断；我方 `sch_layout_check`/`sch_text_audit`/`component_identity_check` = 判定；`sch gate` 仅作交叉校验） | 原理图验收 | 执行器 lint 的阈值/规则由执行器版本决定 | `references/design-gates.md:115–128` 改写 |
| C23 | 我方 `SKILL.md:233`、`design-gates.md:61–62`（不可豁免：电气 DRC、网表审计、PCB DRC、关键网证明、保存重载、Gerber/BOM/恢复演练；可豁免项须落盘 `design-waivers/e1` 且 `PASS_WITH_WAIVER ≠ PASS`）；上游：**无豁免模型**，只有 `blocked`/`incomplete`（`design-flow.md:76`） | 豁免机制 | 无豁免 → 每条风格警告都变成阻断或都被口头"忽略"；有豁免但无落盘 → 审计不可追溯 | **智构保留** | 门禁报告 | 执行器不产出 waiver 文件 | `references/design-gates.md`；`scripts/gate_check.py`（`--waiver-file`） |
| C24 | 我方 `scripts/gate_check.py:37–40`（PASS/PASS_WITH_WAIVER/BLOCKED/UNSUPPORTED）、`SKILL.md:246–251`（待确认/不满足/有条件满足/已验证/不适用）；上游 `SKILL.md:70–71`（source-only/offline-verified/live-verified；candidate-unverified/candidate-rejected；planned/unsupported） | **两套状态词表** | 报告混用导致"live-verified"被误当"门禁 PASS" | **改造**：我方词表为门禁/交付唯一口径；上游词表只作为"证据来源级别"字段映射（1:1 映射表落 references） | 报告与证据记录 | 需迁移已有报告字段 | `references/evidence.md`（映射表）；`scripts/gate_check.py` |
| C25 | 我方 `design-gates.md:115`（`fatal=0 且 error=0`；缺证据/截断/`invalid_json` → BLOCKED）；上游 `SKILL.md:46`（"原生 `pcb drc` 的 `passed:false` 是失败，SCH 的 INFO 不等于错误"）、`actions.md:327–330`（`passed`/`nativePassed` 为宿主布尔重载；仅布尔时 `summary/fatal` 为 **null，不能填 0**；`countsAvailable`/`detailsAvailable` 区分统计与明细） | 判定细节 | 把"未知"填成 0 → 假 PASS | **引用**（把 `countsAvailable`/`null≠0` 语义并入我方 DRC 证据解析），规则仍由我方持有 | 原生 DRC 证据 | 取决于 runtime 返回结构 | `scripts/pcb_evidence.py`；`references/design-gates.md` |
| C26 | 上游 `pcb-design-rules.md:668–693`（FATAL：线宽/间距 ≥0.10mm、孔 ≥0.15mm、天线 keepout 无铜、安装孔 ≥1mm；ERROR：overlap、全连通、Mark ≥3、丝印不压焊盘；WARN 若干）；我方 `SKILL.md:126`（"不把项目固定线宽、距离、温升值写成通用常量"）、`references/jlc-pcb-rules.md:17`（数值为**需重查的条件快照**）、`design-gates.md:140–142`（score≥60/crossings≤8/overlap=0，可用参数调） | DRC/DFM 阈值：**通用常量** vs **渠道+项目条件值** | 拿 0.10mm 当设计默认会浪费工艺能力；拿它当 DRC 判据会与板厂实际规则脱节 | **废弃**上游常量作默认；**引用**为"板厂极限参考（下限）"；项目值按 jlc-*-rules 条件快照 | 有具体板厂/工艺的项目 | 板厂规则会变（快照须带日期） | `references/jlc-pcb-rules.md`；`references/dfm-thresholds.md (TBD)` |

### (f) 身份 / uniqueId / 器件 UUID 保全

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C27 | 我方 `SKILL.md:262`（"保留已有正确器件身份、位号、uniqueId、封装绑定、锁定器件和已确认机械约束"）、`scripts/component_identity_check.py:1–17,25–30`（`IDENTITY_KEYS=('libraryUuid','uuid','name')`；输入必须是已落盘读取）；上游 `schematic-data.md:156–159`（不覆盖原生 `uniqueId`，它可能关联 PCB）、`:676–678`（部分实例 `uniqueId` 为空串须原样保留，**重载后宿主可能新铸**）、`:749–755`（实例保全门禁）、`actions.md:108,114`（`replace` 保留 `uniqueId`）、`pcb.md:13–15`（`uniqueId` 与 `primitiveId` 命名空间不同） | 身份保全的**细节深度**：上游给出"空串保留/重载新铸/两套 ID 域"三条实测事实，我方只有原则 | 重放/重排后位号相同但实例被替换（"看起来一样、PCB 关联已断"） | **引用**（三条实测事实）+ **智构保留**（判定与 BOM reason+evidence 要求） | 重排/换料/rebuild 类任务 | 需 runtime 暴露 `uniqueId`/`primitiveId`/库 UUID 三域 | `scripts/component_identity_check.py`；`references/eda-execution.md` |
| C28 | 我方 `references/eda-execution.md:127`（"**位号唯一性是工程级，不是单页级**"；新增页复用 R1 会跨页冲突；未提供工程清单时 `designator_scope=page` 不得宣称工程级唯一）；上游 `pcb.md:14`（`sync-designators` 按 `uniqueId` 回填、**只动占位符**、每笔回读、修完落 `pcb.save`；手设真实位号绝不覆盖）、`schematic-data.md`（`designators allocate/plan/verify`） | 位号作用域与占位符修复 | 多页新增导致跨页重号；自动回填覆盖用户手设位号 | **智构保留**（工程级唯一）；**引用** `sync-designators` 的"只动占位符"边界 | 多页/新增器件 | 需要全工程扫描能力 | `references/eda-execution.md`；`zhigou` designators 子命令 (TBD) |
| C29 | 上游 `part-selection.md:199–233`（站点差异：`deviceUuid` 必须按**当前版本**重解析；写副本，`--out` 必填，**绝不就地覆盖源文件**）；我方 `scripts/component_identity_check.py`（库身份字段比对）、`references/lcsc-sourcing.md:68`（"EDA 库里的 C 号不是当前库存"） | 库身份解析时点 | 用历史 UUID 直接下单/放置 → 错料/封装不符 | **引用**（"按当前版本重解析、只写副本"作为执行器事实） | 换料/建库/跨版本工程 | 依赖商城/库实时数据 | `references/part-selection.md`、`lcsc-sourcing.md` |

### (g) 安装 / 更新 / doctor / 版本命令命名

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C30 | 上游：`easyeda [command]` 26 子命令（`evidence/env/10-cli--help.txt:6–33`）、`easyeda health`（`SKILL.md:20`）、`easyeda update`（`environment-setup.md:55–68`）、`easyeda daemon start/stop`（`:274–297`）；我方 `SKILL.md:108`（`easyeda health`）、`L296`（typed `easyeda pcb ...`）、`L288`、`L234`；我方 references 中 `easyeda <cmd>` 计数：`design-gates.md` 31、`pcb-routing-strategy.md` 27、`pcb-execution.md` 22、`schematic-layout-engine.md` 22、`tool-gotchas.md` 15…… | **命令名与入口**：新自研 runtime 应为 `zhigou ...`，但全文仍写 `easyeda` | 用户/模型按上游命令名操作新 runtime → 命令不存在；改名不彻底会长期双轨 | **改造**（SKILL 只写 `zhigou`；`easyeda` 仅出现在"历史/排障/引用"块并标版本）；references 分批替换 | 全部用户可见文档 | 新 runtime 命令面未落地（`zhigou` 全仓仅 3 处品牌提及） | `references/executor-commands.md (TBD)`；`zhigou CLI (TBD)` |
| C31 | 我方 `references/installation-updates.md:95–131`（`skill_update.py check/update/status/rollback`；`update-agent --idle`；锁文件 `.hardware-easyeda-update.lock`；备份当前 CLI 与 Skill；"不宣称跨组件原子回退"）、`SKILL.md:14–18`；上游 `environment-setup.md:15–110`（`install.ps1`/`install.sh`、`update --check/--exit-code`、daemon 重启、`.eext` 重导）、`:49–77` | **两套更新器/两套锁/两套备份** | 同一 CLI 被两个协调器替换 → 半升级状态；用户要敲两套命令 | **改造**（单一智构自更新通道；上游更新器降级为"用户手动兜底"引用块） | 安装/升级/回退 | 上游 `update` 仍存在，需在文档中明确"不要用它更新智构" | `scripts/skill_update.py`；`references/version-and-install.md (TBD)` |
| C32 | 我方 `SKILL.md:18`、`L234`（硬编码 "easyeda-agent v1.14.0"）；实测安装 **v1.15.0**（`env/11-cli-version.txt`）；上游 `environment-setup.md:6–12`（宿主 V4；`hostCompatibility` V3=block/旧V4=warn；`engines.eda ~3.2.0` 是扩展 API 引擎版本，**不得机械改成 4.x**）、`:51–53`（三件套版本对齐） | 版本兼容矩阵**位置与内容** | SKILL 里写死旧版本 → 误判能力缺失/误报不兼容 | **改造**（SKILL 删除具体版本号；新建 `references/version-compat.md`，内容由 `zhigou doctor` 生成/校验） | 能力判断 | 上游关于 `engines.eda` 的解释是可引用事实 | `references/version-compat.md (TBD)`；`zhigou doctor (TBD)` |
| C33 | 我方 `SKILL.md:110`（`python scripts/doctor_env.py --summary`，四分"存在/连通/可读/可写"）；上游 `SKILL.md:20`（`easyeda health`）+ `update --check --exit-code`；CLI **无 `doctor`**（`env/12-cli-doctor.txt`） | 诊断入口命名分裂 | 用户被要求跑两条不同命令；"没有 doctor"的报错被误读为环境坏 | **智构保留**（统一 `zhigou doctor`，吸收 health 的连通语义与"不测可写性"边界） | 首次接通/故障 | runtime 已实现 `doctor`（`runtime/internal/app/cmd_doctor.go:158–160`，mtime 21:26；输出 runtime/skill/daemon/connector/protocol/host/legacy 七段，verdict `ok / degraded / blocked`，缺件报 blocked/unknown 且**不写宿主**） | `scripts/doctor_env.py` 改为调用方；`runtime/internal/app/cmd_doctor.go` |
| C43 | runtime `internal/selfupdate/selfupdate.go:31`（`RepoSlug = "zhoushoujianwork/zhigou-agent"`）、`internal/app/version_gate.go:178`、`internal/daemon/hub.go:539`；`internal/selfupdate/cli.go:4,78,82`（发布资产名仍 `easyeda_<os>_<arch>`）；我方 `SKILL.md:15–18`（更新器）、`installation-updates.md:95–131` | **自更新/版本门/发布检查指向外部作者仓库**（不是本仓库） | `zhigou update` 404 或把**上游二进制**装成智构；供应链与信任边界不清；版本门可能永远 warn/block | **改造**（指向本仓库 Releases 或彻底移除自更新，交由安装器/包管理器；资产名改 `zhigou_*`） | 出厂默认 | 需确定发布通道（GitHub Releases vs 离线包）；`rebrand_runtime.py` 规则表未覆盖发布资产名与 owner | `runtime/internal/selfupdate/*`、`internal/app/version_gate.go`、`internal/daemon/hub.go`、`distribution/rebrand_runtime.py` |
| C44 | runtime `internal/app/skill_asset.go:1–18,47–53,80,143–145`（资产搜索阶梯：显式 flag → `ZHIGOU_SKILLS_DIR/<skill>/…` → `~/.claude、~/.codex、~/.agents/skills/zhigou-agent/…` → 仓库 `.agents/skills/…` 上溯 8 层）、`enrich_script.go:25` 与 `skill_asset.go:154`（已 rebrand 为 `zhigou-agent/references/standard-parts.json`、`zhigou-agent/scripts/bom-enrich.py`，但**仍硬编码 `zhigou-agent` 目录名**、不含我方 `easycirq`）、`cmd_sch_sheet.go:86`（`sheet-templates.json`）、`cmd_sch_marker_geom_orientation_test.go:13`（读 `zhigou-agent/references/orientation.json`）；我方 `easycirq/references/` 实测**无** `standard-parts.json`/`orientation.json`/`sheet-templates.json`，`scripts/` 无 `bom-enrich.py` | 运行时对"上游 Skill 目录布局"的**硬编码依赖**，与"我方单一 Skill"目标冲突 | 当前状态下 `sch block-apply`、netflag 朝向、图纸模板、BOM 富化**没有数据来源**；若为迁就 runtime 再装一个 `zhigou-agent` 目录，则违背单 Skill 目标 | **改造**（二选一都必须做）：① 把 4 个资产以 MIT 引用方式纳入我方 `references/`（带 provenance 与版本）；② 扩展资产阶梯认 `easycirq` 目录名并支持 `ZHIGOU_SKILLS_DIR` 指向我方 skill 根 | 使用 block-apply/朝向检查/图纸模板/BOM 富化的任务 | `go:embed` 不能跨 `..`（上游注释已说明），故这些资产只能落盘在 skill 树，不能进二进制；改目录名要同时改 rels 与测试 | `easycirq/references/{standard-parts,orientation,sheet-templates}.json`、`easycirq/scripts/bom-enrich.py`（均 TBD，MIT 引用）；`runtime/internal/app/skill_asset.go`、`internal/selfupdate/selfupdate.go` |
| C45 | runtime `internal/app/cmd_skill.go:12–40`（`zhigou skill status/sync/--version`、`CODEX_HOME/CLAUDE_CONFIG_DIR`）、`internal/app/cmd_update.go:97–117`（`zhigou update` 同时更新 CLI 与 skills） | 面向用户的命令面里仍保留"管理 easyeda-agent 式技能目录/技能同步" | 用户被引导去 `zhigou skill sync` 安装第二套技能；与"用户只需 `zhigou doctor`"冲突 | **废弃**（用户面移除 `skill` 组；如保留仅作内部命令且不 chain 到 skill 目录） | 出厂默认 | 需同步改 `runtime/internal/app/app.go:97` 的命令注册与帮助文本、`app_test.go:17` 断言 | `runtime/internal/app/{app.go,cmd_skill.go,cmd_update.go}` |

### (h) 错误 / 重试策略

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C34 | 我方 `SKILL.md:120`（"同一失败机制重复两次就换布局方法或记录能力缺口"）、`L298`（`recover` 用 journal 与幂等键续做）；上游 `SKILL.md:27`（"部分成功、超时或 stale ID 时先回读，再修源并重算"）、`environment-setup.md:282–297`（"恢复后仍有同一错误就根据新日志定位，**不循环刷新、不重发写操作**"） | 重试上限与路径 | 无上限重试 → 重复器件/导线；上限太死 → 放弃可恢复任务 | **智构保留**（两次换方法）；**引用**"先回读再决定、不盲重发" | 写操作失败/超时 | 幂等键需 runtime 支持 | `references/feedback-loop.md`；`scripts/feedback/loop.py` |
| C35 | 我方 `SKILL.md:261`（"对部分成功、超时先查真实状态，禁止整批盲重试"）、`L298`（五件事分离）；上游 `design-flow.md:68–69`（"超时先回读，区分未执行、已落地和部分执行"）、`pcb.md:40`（无 undo；改前重取 `primitiveId`） | 未知写入状态处理 | 结论一致 | **引用**（并入我方"五件事"叙事） | 所有写操作 | 无 | `references/feedback-loop.md` |
| C36 | 上游 `environment-setup.md:299–305`（身份读取 60s 预算，普通 20s）、`:318–325`（`document.open` 30s、`components.list --include-pins` 150s） | 超时/预算数值 | 把秒数写进 Skill 会在 runtime 换代后过期 | **引用**（数值属实现细节，由 runtime 文档持有，不进规则正文） | 排障 | 新 runtime 预算可能不同 | `references/tool-gotchas.md`（仅作历史对照） |

### (i) 用户不应知道的 daemon / Connector 生命周期

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C37 | 上游 `environment-setup.md:229–247`（`windowId` 非持久、`STALE_WINDOW`/`NO_CONNECTOR`）、`:274–297`（`daemon stop/restart`、PID/端口、`.easyeda-agent` 权限）、`:249–263`（`web reload`/`readbackScope`）、`SKILL.md:20–21`；我方 `SKILL.md:14–18`、`references/installation-updates.md:95–131`、`client-compatibility.md:92–100` | daemon/连接器概念**泄漏到用户面** | 用户被迫理解端口/插件/windowId；"升级失败"被误当"设计失败" | **废弃**（从面向用户文档移除）；**改造**为 runtime 内部 + 一句"未连通时由 `zhigou doctor` 报告" | 全部用户可见文本 | runtime 已隔离服务名/端口/配置目录并**检测旧 daemon**（`cmd_doctor.go:45–49,331–338,474–477`、`internal/protocol/wire.go:11`），但"用户无感"还取决于关掉 C42 的技能同步与 C45 的命令面 | `easycirq/references/diagnostics-internal.md (TBD)`（不进 SKILL）；`runtime/internal/app/cmd_doctor.go` |
| C38 | 我方 `references/client-compatibility.md:94–100`（"EDA Agent Connector / easyeda-agent 的扩展装在嘉立创EDA专业版内部…需允许外部交互，再运行 `easyeda health`"）；上游 `environment-setup.md:132–151`（`.eext` 侧载 vs 立创插件市场）；现状：`connector/` 已是自有身份 `zhigou-connector` e0.1.0（uuid `a6e6b788…6e31`，`connector/extension.json:2–8`），但 runtime `cmd_update.go:106` 仍"只报告不部署" | Connector **安装步骤**是否仍由用户做 | 用户要做扩展管理/重导/权限开关，体验与"装一个技能"不符 | **废弃**用户步骤（改为安装器/首次运行静默部署）；**改造** runtime 的"只报告"为"部署+校验+失败给一键诊断" | 新装/升级 | EasyEDA 侧"允许外部交互"权限是否有 API 可自动开启 **UNKNOWN**（上游文档只写手动启用，`environment-setup.md:155–158`） | `installer/ (TBD)`；`runtime/internal/app/cmd_update.go`；`connector/` |
| C46 | runtime 残留：`internal/selfupdate/cli.go:4,78,82`（资产名 `easyeda_<os>_<arch>`）、`internal/selfupdate/cli_test.go:19–23,305–319`；`internal/app/cmd_sch_marker_geom_orientation_test.go:13`（路径含 `zhigou-agent`）；`distribution/rebrand_runtime.py:25–42` 规则表未覆盖发布资产名/owner/目录名；统计（21:26 复测）：`zhigou-agent` 150 处、`ZHIGOU_` 60 处、`EASYEDA_` 11 处（全是发布资产名）、`easyeda-agent` 7 处（集中在 `cmd_doctor.go` 的旧 daemon 检测与 `protocol/wire.go:11` 隔离注释，属**有意保留**） | rebrand **不完整且不可自动复现**（`--check` 会列出差异） | 环境变量双前缀（用户设 `EASYEDA_SKILLS_DIR` 无效）；文档/提示混用两套名字；rebrand 漂移在后续 vendoring 时复发 | **改造**（补规则：发布资产名、owner、skill 目录名；把 `rebrand_*.py --check` 纳入 CI 门禁） | 每次 vendoring/升级上游基线后 | 需与 C42/C44 的目录改名一起做，否则改一处漏一处 | `distribution/rebrand_runtime.py`、`distribution/rebrand_connector.py`、`runtime/**` |

### (j) 速度 / 效率

| 编号 | 规则来源(文件:行) | 冲突/重叠内容 | 风险 | 决定 | 适用条件 | 技术限制 | 实现位置 |
|---|---|---|---|---|---|---|---|
| C39 | 我方 `SKILL.md:130`（`pcb_apply_plan.py --module-plan` 合批：一次读取/标准化、联合检查、一次 apply、保存重载链）、`references/execution-efficiency.md:12–56`；上游 `SKILL.md:26`（"同一窗口的调用串行执行"）、`pcb.md:50–51`（"小批执行后回读对象与差异"） | **合批 vs 小批** | 合批快但失败面大；小批慢但可定位 | **智构保留**合批（默认一次 apply + 一次回读）；**引用/吸收**"同窗口串行"为 runtime 保证（并发由 runtime 串行化，不由 Skill 编排） | 多模块 PCB 放置 | 需 runtime 保证同目标串行与幂等 | `scripts/pcb_apply_plan.py`；`references/execution-efficiency.md` |
| C40 | 我方 `scripts/eda_cache.py`、`references/eda-efficiency.md:146`（缓存值含 `storedAt`+`versionTag`+CLI/connector 版本）；上游 `environment-setup.md:229–247`（`windowId` 不作持久身份）、`:299–302`（"同次读取复用完全相同的解析输入，**不跨请求/页面缓存来源证明**"） | 缓存**能否作为证据** | 用缓存读数做 PASS → 与现场不一致；完全禁缓存 → 重复探测拖慢 | **改造**（缓存只用于规划复用；写入/重开/换页即失效；**任何 PASS 不得引用缓存**） | 只读分析与合批准备 | 需版本戳与失效钩子 | `scripts/eda_cache.py`；`references/eda-efficiency.md` |
| C41 | 我方 `SKILL.md:100`（共享工程/EDA 窗口**只允许一个指定写入者**；其余 Agent 用带工程/页身份+哈希的冻结快照；默认 ≤3 子 Agent）；上游 `SKILL.md:26`（同窗口串行） | 并发写保护 | 结论互补 | **智构保留**；**引用**上游"串行"作为执行器侧保证 | 多 Agent/多模块 | 无 | `references/agent-collaboration.md` |

**统计**：冲突 46 条，按覆盖项：a=5、b=6、c=4、d=6、e=6、f=3、g=7、h=3、i=3、j=3；按处置：智构保留 12、改造 19、废弃 7、引用 8。行的性质混合了"冲突/重叠/缺口"三类（重叠项也列入，因为不合并就会漂移）。

---

## 4. 合并后的政策（单一 SKILL.md 应承载的最终规则集）

### 4.1 唯一职责划分（写进 SKILL.md 第 0 节，硬约束）

1. **智构 Skill = 政策唯一来源**：需求澄清、选型与供应链、工程计算、设计规则、阶段门禁、证据口径、交付话术、验收判据，全部由本 Skill 定义。
2. **`zhigou` runtime/Connector = 唯一执行者**：只负责连接 EDA、执行受控动作、返回原始回执与版本；**不定义设计规则、不定义门禁、不定义验收**。
3. **唯一用户入口**：用户只说目标；环境自检、升级、排障由 Agent 调 `zhigou doctor` / `zhigou update`，用户不需要理解 daemon/端口/插件/windowId。
4. **不得双载**：`easyeda-agent` 不再作为技能安装；其文本只在 `references/` 内作为**执行器事实引用**出现，带版本与行号。
5. **运行时不装技能**：`zhigou` runtime 只执行，不得在启动/更新时向客户端 skills 目录写入任何技能；数据资产缺口由我方 Skill 提供（`references/` 内），通过显式路径或 `ZHIGOU_SKILLS_DIR` 指向我方 skill 根。

### 4.2 必须保留的 12 条不可协商规则（合并后仍是硬规则）

| # | 规则 | 现位置 | 合并后位置 |
|---|---|---|---|
| P1 | 身份保全：位号/`uniqueId`/`component.uuid`/库身份/封装绑定/锁定件不得因排版或重建丢失 | SKILL.md:262; component_identity_check.py | SKILL §6（1 行）+ references/eda-execution.md |
| P2 | 保存后必须重开回读；`saved===true` 与 fresh readback **同时**成立才记持久化 | SKILL.md:263; C07 | SKILL §6（1 行） |
| P3 | 证据新鲜度：path/sha256/semantic_sha256/mtime/freshness_basis 绑定；旧证据 → `STALE_EVIDENCE`；带 `staleRisk` 的读数只作诊断 | design-gates.md:59; C08 | SKILL §6 + design-gates.md |
| P4 | 缺证据 = `BLOCKED`；`UNSUPPORTED` 必须显式列出；退出码 0 不证明硬件 | design-gates.md:62–63 | SKILL §3 |
| P5 | 不可豁免清单：电气 DRC、网表审计、PCB DRC、关键网证明、保存重载、Gerber/BOM/恢复演练 | SKILL.md:233 | SKILL §3（1 行） |
| P6 | 阶段硬序：G2 未过不导入/布局 PCB；G3/G4 未过不布线；G5 未过不谈制造；G6 未过不说可打样 | SKILL.md:231 | SKILL §3 |
| P7 | 门禁是**证据门不是审批门**；只有用户显式要求评审时才停 | SKILL.md:94–96,226 | SKILL §1/§3 |
| P8 | 图面验收三件套：`sch_layout_check --strict` + `sch_text_audit --strict` + **实际官方导出图**；执行器 lint 不可替代 | SKILL.md:122 | SKILL §4 |
| P9 | 单一写入者 + 冻结快照（工程/页身份+哈希） | SKILL.md:100 | SKILL §0/§7 |
| P10 | 不伪造：不为清 DRC 删保护/改网名/造假 NC；不把离线/截图/探针说成已完成 | SKILL.md:260,112 | SKILL §0（1 条不变量） |
| P11 | 失败两次换方法；写失败先回读再续做；禁止整批盲重试 | SKILL.md:120,261 | SKILL §7 |
| P12 | 交付级别只用证据支持的五级：概念方案/原理图候选/PCB 候选/可供工程复核的制造候选/已有样机实测 | SKILL.md:321 | SKILL §8 |

### 4.3 可以引用上游的事实清单（MIT，可引用、不可继承其工作流）

**出处格式（强制）**：`easyeda-agent v1.15.0（MIT，© 2026 zhoushoujianwork，https://github.com/zhoushoujianwork/easyeda-agent）· references/<file>:行`
并在文件头统一写一次：

> 本文件部分执行器事实引自 easyeda-agent v1.15.0（MIT License，Copyright (c) 2026 zhoushoujianwork and contributors；per `LICENSE:1–3,20–28`）。引用范围仅限命令名/API 语义/单位与身份事实；**其工作流、门禁叙事与验收主张不作为本 Skill 规则**。上游版本 1.15.0，引用日期 2026-10-27。

可引用（20 项，全部是执行器/平台事实）：
1. 原理图 raw 单位 = 0.01 inch = 0.254 mm；5 raw 硬连接网格；A4 尺寸随 build 变（`schematic-layout-conventions.md:14–24`）。
2. PCB 数据单位 mil；y-up；`x/y`=anchor ≠ bbox center（`pcb.md:34–35`）。
3. 旋转与 `--center` 不得同调（`pcb.md:35`）。
4. PCB 栅格惯例 25/50/5 mil（`pcb-layout-conventions.md:23`）。
5. `uniqueId` 由平台首次 sch→PCB 导入铸造、跨文档同一命名空间；`primitiveId` 每文档各 mint（`pcb-layout.md:14`）。
6. 部分实例 `uniqueId` 为空串须原样保留，重载后可能新铸（`schematic-data.md:676–678`）。
7. `replace` 保留 `uniqueId`；`--keep-properties` 保留实例属性（`actions.md:108,114`）。
8. 保存/重载要求布尔 `saved:true`；autosave 不构成证据（`actions.md:84–92`）。
9. 原生 DRC：`passed`/`nativePassed` 为宿主布尔重载；仅布尔时 `summary/fatal` 为 null，不得填 0；`countsAvailable` 区分统计/明细（`actions.md:327–330`）。
10. `pcb drc` 的 `passed:false` 是失败；SCH 的 INFO 不等于错误（`SKILL.md:46`）。
11. 无程序化 undo；改前重取 `primitiveId`；`delete` 布尔只表示操作完成（`pcb.md:40–41`）。
12. `staleRisk` 提示缓存风险但不拒绝读取；最终可信结果用 save→reload→readback（`design-flow.md:150–154`）。
13. netflag 本体朝向 `frozenTable`（power/ground/port × 4 方向）及 2026-08-12 校准记录（`orientation.json`）。
14. 宿主 V4 基线；`hostCompatibility` 语义；`engines.eda ~3.2.0` 为扩展 API 引擎版本，不得机械改成 4.x（`environment-setup.md:6–12`）。
15. 读取预算：普通 20s / `document.open` 30s / `components.list(includePins)` 150s / 身份 60s（`environment-setup.md:299–305,318–325`）。
16. `windowId` 非持久身份，用 project/doc UUID 路由（`environment-setup.md:231–237`）。
17. `deviceUuid` 必须按当前版本重解析；写副本、绝不就地覆盖（`part-selection.md:199–233`）。
18. 零长度 wire 会被宿主 DRC 逐条报错（实测 204 条 wire 中 149 条为占位）（`schematic-layout-conventions.md:119–128`）。
19. 位号占位符修复 (`sync-designators`) **只动占位符**、手设真实位号绝不覆盖、每笔回读（`pcb.md:14`）。
20. 新手排障分类法（显示/库绑定/电气连接/PCB 几何/工程管理五类）（`beginner-troubleshooting.md:6–12`）。

**明确不可引用为规则**：上游 S0–S6/P0–P10 流程顺序、两轮自检+用户确认停顿、"检查不授权下一步"、DRC 通用阈值（0.10mm 等）作默认值、九宫格硬格位、固定框样式/字高、`workflow/stage`/`gate` 许可语义。

### 4.4 新执行器（`runtime/` + `connector/`）必须满足的接口契约（由本审计推导，供 runtime 工作流执行）

截至 2026-10-27 21:25 的 runtime 现状（见 `evidence/skill-audit/04-runtime-connector-observation.md`）与本目标的差距，收敛为 8 条：

| # | 契约 | 现状 | 需改 |
|---|---|---|---|
| R1 | **不写技能目录**：daemon 启动与 `update` 不得向 `~/.claude、~/.codex、~/.agents/skills/` 写 `zhigou-agent` | 默认 `--auto-update-skill` 开启，`SkillName="zhigou-agent"`（`cmd_skill.go:17–22`、`selfupdate.go:33`） | 关默认、删安装路径、`skill` 命令降为内部只读 |
| R2 | **自更新/版本门指向本仓库且可关闭** | `RepoSlug="zhoushoujianwork/zhigou-agent"`（3 处） | 改 slug 或删除安装能力；发布资产名 `zhigou_<os>_<arch>` |
| R3 | **技能资产定位认我方目录名** | `skills/zhigou-agent/...`、rels 仍 `easyeda-agent/...` | 支持 `ZHIGOU_SKILLS_DIR` 指向我方 skill 根 + 目录名可配；或资产全部由我方随包提供并用显式 flag |
| R4 | **四个数据资产随我方 Skill 分发**：`standard-parts.json`、`orientation.json`、`sheet-templates.json`、`bom-enrich.py` | 我方 `easycirq/` 四个都缺 | 以 MIT 引用方式纳入 `references/`、`scripts/`，文件头带 provenance（C44） |
| R5 | **写入校验回执可被我方证据层消费**：`POST /writeverify` + `staleRisk` + `saved` 字段 | 已存在（`write_verify.go`、`writehealth.go`） | 仅需保证字段稳定、可落盘为 evidence JSON；C07/C08 直接消费，不再另造 |
| R6 | **宿主版本判定可查询**：`hostCompatibility`（baseline 4.0.0 / recommended 4.1.60） | 已存在（`host_compatibility.go`），且 `zhigou doctor` 已给出整机 verdict（`cmd_doctor.go`） | `zhigou doctor` 输出该结论；Skill 不写死版本号（C32） |
| R7 | **Connector 部署**：安装器/首次运行部署 `zhigou-connector`（uuid `a6e6b788…6e31`）并校验版本 | `connector/` 已自有身份；runtime 只"报告"不部署 | 增加部署+校验；"允许外部交互"若无 API 则降级为用户一次性动作（U7） |
| R8 | **rebrand 可复现**：`distribution/rebrand_*.py --check` 在 CI 中为 0 差异 | 残留 `EASYEDA_` 11 处、资产名未覆盖（C46） | 补规则 + CI 门禁 |

---

## 5. `easycirq/SKILL.md` 重构提案（目标 ≤120 行，本阶段不执行）

### 5.1 现状与目标差距

| 指标 | 现状 | 目标 |
|---|---|---|
| 行数 | **323** | ≤120（建议 108–118） |
| `easyeda` 命令串 | 9 处（L108、L15、L234、L288、L290、L296、L122、L282、L165 一带） | **0 处**（仅"历史/排障"引用块内允许，且标版本） |
| 巨型表格 | L132–207（60+ 行"任务→reference"） | 0（迁 `references/index.md`，SKILL 只留 8 行分组导航） |
| 脚本/命令清单 | L108、L122、L126、L130、L165、L294、L296、L298（长段落） | 0（迁 `references/executor-commands.md`） |
| 版本号硬编码 | L18、L234（v1.14.0） | 0（迁 `references/version-compat.md`） |
| 门禁键/硬规则/不可豁免 | 完整（L224–234） | **原样保留**（可压缩表述，语义不动） |

### 5.2 目标大纲（行预算合计 ≈112）

```
L1-4    frontmatter：name + ≤90 字 description（去掉"配合 easyeda-agent"字样，改为"配合 zhigou 执行器"）
L6-9    # AI画板搭档 + 3 句定位（角色分工 / 不伪造 / 默认中文）
L11-18  §0 角色与契约：智构=政策唯一来源；zhigou=唯一执行者；用户只说目标；不双载 skill（4 条，第 4 条给安装器）
L20-27  §1 开始任务：目标复述+1-2 个生活化问题；6 行意图表（方案/画图/改图/布局布线/检查/换料+采购合并）
L29-36  §2 执行通道：`zhigou doctor` 三态（未连通/只读/可写）；离线仍可交付；不静默安装
L38-53  §3 阶段与门禁：S0–S5 一行式；G0–G6 七键表（7 行）；4 条硬规则；不可豁免 1 行；退出码 1 行
L55-64  §4 原理图：一页优先+分页理由；分区=阅读顺序+声明 order；框几何 4 条；验收三件套；禁改连接
L66-77  §5 PCB：机械/固定件先锁；关键回路与分区；DRC+铺铜；交付清单；禁止清单（不为清 DRC 删保护等）
L79-88  §6 身份与证据：5 项身份；save→reopen；freshness；五件事分离；缺证据=BLOCKED
L90-97  §7 失败、重试与提速：两次换方法；先回读再续做；合批写入+一次回读；缓存不作证据
L99-108 §8 交付与话术：新手/工程师；阻断/建议/提示 × 已证实/条件风险/待核实；五级交付级别
L110-119 §9 按需读取（8 行分组导航 → references/index.md）
L121    §10 版本与安装（1 行：以 `zhigou doctor` 为准；详见 references/version-and-install.md）
```

### 5.3 保留 / 删除 / 迁移（逐段）

**保留在 SKILL.md（压缩重写，语义不变）**
| 现位置 | 内容 | 处理 |
|---|---|---|
| L8 | Skill=方法包、执行器负责编辑 | 扩成 §0 四条 |
| L54、L77 | "未回读不写验证通过"、"直接改→自主推进" | 并入 §1/§3 |
| L94–96 | 评审节奏=四个可见检查点、非审批门 | 压到 2 行（**这是与上游最关键的分歧，必须显式保留**） |
| L100 | 单一写入者 | 压到 1 行 |
| L224–234 | G0–G6、硬规则、豁免、工具边界 | **原样保留**，仅把 "easyeda-agent v1.14.0" 改成"由 `zhigou doctor` 报能力" |
| L246–253 | 五状态词 + 分别报告 | 压到 4 行 |
| L255–272 | 底线 13 条 | 压成 6 条不变量（型号/容差、脚与焊盘、图面服从电气、先源后写、身份/保存、安规与供应链） |
| L300–323 | 交付格式与话术 | 压到 §8（10 行） |

**从 SKILL.md 删除（迁 references）**
| 现位置 | 去处 |
|---|---|
| L12–18 安装/更新细节 | `references/version-and-install.md`（新建；合并 `installation-updates.md` 的上游段） |
| L20–23 生态工具接入 | `references/easyeda-ecosystem.md`（已存在，补 1 行导航） |
| L25–32 §0 产品落地层 | `references/idea-to-product.md`（已存在） |
| L44–78 模式表 12 行 + 工程师口语表 9 行 | 模式表压成 6 行入 §1；口语表整体迁 `references/interaction.md` |
| L80–92 生态路线/商城制造 | `references/lcsc-sourcing.md`、`jlc-handoff.md`（已存在） |
| L102–114 执行能力检查长段 | §2（4 行）+ `references/client-capability.md`（新建，含"客户端只是宿主"） |
| L116–122 原理图执行段（脚本名罗列） | §4（6 行）+ `references/executor-commands.md`（新建） |
| L124–126 电源主干 | `references/power-routing-preflight.md`（已存在） |
| L128–130 提速 | §7（2 行）+ `references/execution-efficiency.md`（已存在） |
| L132–207 60+ 行读取表 | **`references/index.md`（新建）**：按"流程/执行/原理图/PCB/制造供应链/领域/内容库/排障"8 组索引；SKILL §9 只留 8 行 |
| L209–222 内容库边界 | `references/content-library-boundaries.md`（新建） |
| L236–253 工程状态长段 | §6（5 行）+ `references/evidence.md`（已存在） |
| L274–298 后台计算/脚本清单 | `references/executor-commands.md`（命令与脚本清单）+ `references/offline-tools.md`（已有）；SKILL 仅留"离线脚本不访问 EDA/网络，边界见…"1 行 |
| L300–323 交付细节 | §8（10 行）+ 现有 assets 模板链接 |

**新建文件（共 10 个，其中 3 个 JSON + 1 个 Python 为 MIT 引用资产）**
1. `references/index.md` — 读取索引（承接现 L132–207）。
2. `references/executor-commands.md` — `zhigou` 命令面 + 证据位 + 与旧 `easyeda` 命令的对照（旧命令只作历史/排障，标 v1.15.0）。
3. `references/version-and-install.md` — 版本域、兼容矩阵、`zhigou update`、回退；删除对 `easyeda update/update-agent` 的用户指引。
4. `references/diagnostics-internal.md` — daemon/Connector/端口/windowId/读取预算（**内部文档，不链接进 SKILL 正文**，仅 Agent 排障时读）。
5. `references/content-library-boundaries.md` — 设计卡/常用硬件/决策库的 E1/E2/E3 与 D0/D1/D2 边界。
6. **`references/orientation.json`** — netflag 本体朝向 `frozenTable` + `_doc`，**直接沿用 runtime 期望的文件名**（`cmd_sch_sheet.go`/测试按 `references/orientation.json` 读取），文件头/伴随说明写 MIT 出处、上游版本与校准日期（C14、C44）。
7. `references/dfm-thresholds.md` — 把 C26 的条件化阈值与"板厂极限仅作下限"写清。
8. **`references/standard-parts.json`** — 角色→`deviceUuid` 桥接表（`sch block-apply` 依赖）；MIT 引用 + `deviceUuid` 须按当前站点/版本重解析的提示（借 C29 事实）。
9. **`references/sheet-templates.json`** — 图纸模板（`cmd_sch_sheet.go:86` 读取）。
10. **`scripts/bom-enrich.py`** — BOM 富化脚本（`enrich_script.go` 按 `scripts/bom-enrich.py` 定位）；MIT 引用，入包前须审阅不含网络/EDA 写入。

> 8–10 属于"运行时依赖但我方缺失"的资产（C44）；不纳入则相应 runtime 能力不可用，纳入则必须写明来源与许可（上游 bundle 为 MIT，见 `LICENSE:1–3,20–28`），并纳入 `skill_selftest.py` 的必需文件清单。

**改造既有 references（改名/语义对齐，不动内容结论）**
- `design-gates.md`：把 31 处 `easyeda ...` 命令改成 `zhigou ...`（或标注"等价命令见 executor-commands.md"）；补 `countsAvailable`/`null≠0`（C25）、`saved===true` AND 重开回读（C07）、"lint 只作输入"分层（C22）。
- `pcb-execution.md`、`pcb-routing-strategy.md`、`schematic-layout-engine.md`、`eda-execution.md`、`tool-gotchas.md`：同批命令替换；`tool-gotchas.md` 保留带版本号的真实故障案例（历史价值）。
- `installation-updates.md`：删"同时覆盖 easyeda-agent"整节（现 L95–131），迁入版本与安装新文。
- `client-compatibility.md`：删 Connector 安装步骤（现 §5），改为"由安装器静默部署"。
- `references/schematic-layout.md`：补零长 wire（C20）、框几何四规则（C19）、分页阈值评估（C16）。
- `references/pcb-placement-details.md`：补旋转 90° 步进默认 + 例外记录（C13）、P0–P7 裁决顺序（吸收上游 `pcb-layout-conventions.md:72–87` 的结构，但阈值条件化）。

**重构硬约束（来自新执行器接口，C44/R3–R4）**
- **不得移动/改名/删除** runtime 按文件名查找的资产：`references/standard-parts.json`、`references/orientation.json`、`references/sheet-templates.json`、`scripts/bom-enrich.py`。当前我方四者皆缺（`Test-Path` 均为 False），需按 §5.3 第 6/8/9/10 项补入并带 MIT provenance。
- SKILL.md 的读取索引（`references/index.md`）若重命名上述文件，必须同步修改 runtime 的 `skill_asset.rels` 或改为显式 `--parts/--script` 传参；否则 block-apply / 朝向 / 模板 / BOM 富化 静默退化。
- 重新组织 `references/` 子目录时，不要把这些资产移到新子目录（`cmd_sch_sheet.go` 与测试按扁平 `references/` 读取）。

### 5.4 重构验收清单（执行阶段用）

1. `SKILL.md` ≤120 行；`grep -c "easyeda"` = 0（"历史/排障"块若保留须单独计数并在文首声明）。
2. G0–G6 键名、"硬规则"4 条、不可豁免清单、`PASS_WITH_WAIVER ≠ PASS` 语义**逐字保留**（`skill_selftest.py` 会校验键名一致性）。
3. 所有相对链接可解析（`skill_selftest.py` 检查）；新 7 文件加入包内。
4. 删除 `easyeda-agent` 作为技能依赖的表述；`skill_update.py` 不再检查上游 CLI/daemon/Connector（或降级为可选只读诊断）。
5. `docs/toolchain-integration/evidence/skill-audit/` 作为审计基线保留，供重构后 diff 引用。

---

## 6. 未决事项与 UNKNOWN

| 编号 | 事项 | 现状 | 影响 |
|---|---|---|---|
| U1 | 派单称 SKILL.md "231 行"，实测 **323 行**（worktree 与已安装副本均 323 行、逐行一致） | 未找到 231 行版本 | 本审计按实际 323 行编号；若存在另一精简分支需重对行号 |
| U2 | 新 runtime 的**最终命令面与返回 schema**（`zhigou doctor` 是否存在、`skill/update` 是否保留、`writeverify` 是否暴露 CLI） | **部分已知**：`runtime/` 已 vendored（`cmd/zhigou`，26 子命令来自上游 rebrand，`internal/app/app.go:65,97`），但仍在建（untracked、mtime 21:22），且 C42–C46 的修改会改变命令面 | C30/C32/C33 的最终命名与 C05/C08 的证据适配需等 runtime 定稿 |
| U3 | 上游 v1.15.0 是否新增 Gerber/钻孔/CPL 的 CLI/typed action | **UNKNOWN**：v1.15.0 references 未见专用命令，`pcb.md:313` 仅把 gerber/pick-and-place/3D 当 artifact；我方 `SKILL.md:234` 的"v1.14.0 无此能力"需按新版本重验 | G6 工具边界可能变化；不得沿用旧结论 |
| U4 | 当前宿主实际加载的是哪一份上游 Skill（`.codex` / `.claude` / 两者） | **UNKNOWN**：两份内容一致；本会话可用技能清单含 `easyeda-agent`；未读取宿主加载日志 | 卸载策略需覆盖两个目录 |
| U5 | 本机 `easyeda` CLI 1.15.0 × EasyEDA Pro 4.1.78 的 `hostCompatibility` 实测值 | **UNKNOWN**：任务禁止运行 EDA 命令，未执行 `health` | 版本兼容矩阵条目需实测后写死 |
| U6 | 上游 `frozenTable` 在 4.1.78 是否仍成立（表基于 3.2.149 / connector 0.24.3 校准） | **UNKNOWN**：无现场重校数据 | C14 的引用必须带"校准日期 + 待复核"标记 |
| U7 | EasyEDA 的"允许外部交互"权限能否由自有 `zhigou-connector` 自动开启 | **UNKNOWN**：`connector/` 已是自有扩展，但权限开关是宿主侧 UI；上游文档只写手动启用（`environment-setup.md:155–158`） | 决定 C37/C38 能否真正做到"用户零步骤" |
| U8 | runtime 定稿基线（当前 `runtime/`、`connector/`、`protocol/` 均 untracked，审计期间仍在写） | **UNKNOWN（时点事实）**：mtime 2026-10-27 21:22；`dist/zhigou.exe` 已构建 | C42–C46 的"现状"会变；修复后须复跑本审计 |
| U9 | 官方 Gerber/钻孔/CPL 能力在 4.1.78 + 自研 runtime 下是否有 typed 通道（旧结论按 easyeda-agent v1.14.0 写） | **UNKNOWN**：runtime 的 pcb 命令面来自上游 1.15.0 rebrand，未见专用 gerber 子命令 | `SKILL.md:234` 的 G6 工具边界需按新 runtime 重验 |

**阻塞项（需 Lead 或其他角色处理，非本审计可解）**
1. **runtime 定稿与命令面**（U2/U8）→ 涉及命令名的 4 条（C04/C30/C32/C33）需在 runtime 定稿后回填最终实现路径；C05/C08 的证据格式适配同此。
2. **runtime 不得装技能 / 不得指向外部仓库 / 资产路径可配**（C42/C43/C44）→ 这是"单 Skill"目标的真正前置条件；属 runtime 改造范围，本审计只能给契约（§4.4 R1–R8）。
3. **四个数据资产的取舍**（C44）→ 是"引入 MIT 引用资产"还是"改 runtime 找 easycirq 目录"，需要 Lead 决策（两条路的包体与许可影响不同）。
4. **上游 Skill 的卸载/禁用**（C01）→ 属安装器范围；本审计只能给要求，不能实现。
5. **Connector 静默部署与"允许外部交互"权限**（C37/C38、U7）→ 需 runtime/安装器设计；若无 API 可自动授权，则必须保留"用户一次性动作"并如实写进首次接通流程。

---

## 7. 证据索引

| 文件 | 内容 |
|---|---|
| `evidence/skill-audit/01-our-skill-inventory.md` | 我方 SKILL.md 逐段规则表、references 分组、14 个门槛/检查脚本表、agents/cases/assets、10 条不可协商规则 |
| `evidence/skill-audit/02-upstream-skill-inventory.md` | 上游版本/许可、26 个 CLI 子命令、8 步工作循环、硬规则、安装配置假设、references/scripts 清单、20 条可引用事实、应隐藏的运行时细节 |
| `evidence/skill-audit/03-installed-copies-compare.md` | 源码 v1.14.0 vs 安装 v1.15.0：版本、哈希、文件数、逐文件差异（158 换行差异 / 12 文本差异 / 4 仅安装有）、两份安装副本一致性 |
| `evidence/skill-audit/04-runtime-connector-observation.md` | 自研 `runtime/`、`connector/`、`protocol/` 现场（2026-10-27 21:20–21:25）：vendored 与 rebrand 事实、`zhoushoujianwork/zhigou-agent` 指向、daemon 自动同步技能、4 个 skill 资产缺失、`/writeverify` 与 hostCompatibility 能力、残留 `EASYEDA_` 明细 |
| `evidence/env/10-cli--help.txt`、`11-cli-version.txt`、`12-cli-doctor.txt`、`01-lceda-pro-fileversioninfo.txt` | 已捕获的 CLI 版本/帮助/无 doctor、EDA 4.1.78 |
