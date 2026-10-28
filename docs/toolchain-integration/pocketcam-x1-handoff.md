# PocketCam X1 PR 包 → EasyCirq 落地 handoff

> 输入：`hardware-design-skill-PR-pocketcam-x1.zip`（2026-10-28 导出，含一份 patch/bundle + 两份复盘报告 26 条建议 / 27 条缺点）
> 目标仓库：`zsx3896926/EasyCirq`（原 `hardware-design-skill`，已改名 + 品牌统一 智构/EasyCirq）
> 状态：**11 个落地项全部完成并合并（11/11）**；本文件记录改动、PR、NOT RUN 边界与剩余项。
> 收尾时间：2026-10-28（+08），`origin/main` tip = `a08f6c1`（fix release #141）

---

## 1. 总览

| # | 主题 | Issue | PR | 合并提交 | 类型 |
|---|---|---|---|---|---|
| 0 | PocketCam X1 教训进默认路径（原始 PR 包移植） | — | #105 | `c777709` | 文档 + guard |
| 1 | DRC 轻量入口 | #108 | #116 | `afaab6d` | 脚本 + 文档 + 测试 |
| 2 | apply 去重/续传/几何比对 | #109 | #119 | `02a1e02` | 脚本 + 文档 + 测试 |
| 3 | 4 层闭环配方 + 停止规则 | #111 | #122 | `aaa88fe` | 文档 + guard |
| 4 | 接口引脚定义确认进交付门禁 | #114 | #123 | `e189117` | 门禁 + 文档 + 测试 |
| 5 | design-state 恢复字段 | #112 | #126 | `5f9e684` | 门禁 + 文档 + 测试 |
| 6 | 门禁识别 DRC 规则放宽与铺铜新鲜度 | #113 | #130 | `b25829d` | 门禁 + 文档 + 测试 |
| 7 | 离线补线规划器与铜岛诊断（同层） | #110 | #133 | `d369d48` | 脚本 + 文档 + 测试 |
| 8 | 离线补线跨层过孔缝合（#110 补全） | #110 | #137 | `01d6d48` | 脚本 + 测试（并行会话） |
| 9 | PCB 能力矩阵 + command-map 编辑/删除动词 | #115 | #129 | `1bd1af7` | 文档 + 测试（并行会话） |
| 10 | S18 SY8089 电感额定值 fail-closed | #134 | #139 | `c7175c3` | 块数据 + 测试 |
| 11 | S23 netpath_fallback + S27 G6 MANUAL_HANDOFF/STEP | #135 · #136 | #139 | `c7175c3` | 门禁 + 文档 + 测试 |

> 说明：
> - #105 是 zip 里原始 patch 的移植（品牌/路径归一 + 3 处 runtime 复核改写）。
> - #108–#114、#134–#136 由分析会话实现并推送/合并；#115/#129、#137（跨层连岛）由并行会话完成。
> - S18/S23/S27（#134/#135/#136）合在 1 个 PR #139；`skill_knowledge_audit` 的行号基线修正在 #133（`a99671e`）与 #139（`adf60cf`）上随行补齐。

---

## 2. 逐项改动与验证

### 0. PocketCam X1 教训进默认路径（PR #105，`c777709`）
- **改动**：`pcb-routing-strategy.md` §3.3/§4.2、`routing-plan.md`、`pcb-execution.md` §9.1/§9.4、`SKILL.md` 硬规则、`manufacturing-package.md`、`pcb-delivery-checklist.md`，新增 `docs/toolchain-integration/pocketcam-x1-lessons.md` 与 guard。
- **复核改写 3 处**：mismatch 不再一律归因 primitiveId；`escape-plan` 只规划不锁定；Gerber/CPL 注明 `pcb.manufacture.*` typed action。

### 1. DRC 轻量入口（PR #116，`afaab6d`）
- `pcb_evidence.py drc-summary`，复用 `parse_drc`；布线期唯一读法。

### 2. apply 去重/续传/几何比对（PR #119，`02a1e02`）
- `--skip-existing`、`--auto-timeout`、`verified_geometry` 状态；`feedback/scope.py` 识别。

### 3. 4 层闭环配方 + 停止规则（PR #122，`aaa88fe`）
- `pcb-4layer-closure.md`（12 步）；停止规则合并为单一定义 + 3 条补丁。

### 4. 接口引脚定义确认进交付门禁（PR #123，`e189117`）
- `requirements.interface_pinout`；`assumed` → G6 BLOCKED；DVP FPC 设计卡。

### 5. design-state 恢复字段（PR #126，`5f9e684`）
- `recovery` 字段；SKILL §4 恢复规则；G0 校验。

### 6. 门禁识别 DRC 规则放宽与铺铜新鲜度（PR #130，`b25829d`）
- G5 规则放宽比对 + `pour_rebuilt` 检查。

### 7. 离线补线规划器与铜岛诊断（同层，PR #133，`d369d48`）
- `power_preflight/islands.py`（铜岛诊断）+ `island_join.py`（同层连岛）。

### 8. 离线补线跨层过孔缝合（PR #137，`01d6d48`，并行会话）
- `island_join.py` 补跨层 A* + 过孔插入 + 过孔去重（完成 #110 的跨层部分）。

### 9. PCB 能力矩阵 + command-map（PR #129，`1bd1af7`，并行会话）
- `SKILL.md` §2 PCB 编辑能力矩阵、`pcb-command-map.json` 编辑/删除动词。

### 10. S18 SY8089 电感额定值（PR #139，`c7175c3`）
- 块默认电感 `ind.22uh_1210`（约 0.77A auto-added）→ `ind.2u2_swpa4020`（实装件，Isat/Irms 待核）；`ind.22uh_1210` 降备选并注明电流上限；新增 `tests/test_block_parts_verified.py`（块引用 auto-added 器件报警、引用可解析）。**未在仓库内伪造"已核过"的 2A 电感（无手册访问），改为 fail-closed。**

### 11. S23 + S27（PR #139，`c7175c3`）
- **S23**：G5 关键网证明支持 `netpath_fallback`（`{connection:0, copper_ids:[...]}`），原生 DRC Connection=0 时降级 advisory；`design-gates.md` 写清格式。
- **S27**：G6 新增 `step`（3D/STEP）角色 + `manufacturing_manual_handoff` advisory（`artifacts[].status=manual_handoff`）；Gerber/钻孔/CPL 文案更新为 `pcb.manufacture.*` typed action + GUI 兜底；`manufacturing-package.md` 加 step 行与 MANUAL_HANDOFF 说明。

---

## 3. NOT RUN / 边界（按 PR）

| PR | NOT RUN / 边界 |
|---|---|
| #105 | 证据（会话记录、apply journal）未随仓库提交；单板个案，不外推；"根因未定"如实标注。 |
| #116 | 只读已导出的 DRC receipt；未真实 EDA 回读。**runtime 侧 `pcb drc --summary` 未做**（只做了 skill 侧 `pcb_evidence.py drc-summary`）。 |
| #119 | 去重匹配器读 dump 铜集合；未真实 EDA 中断续传回读。**自动分块（≤500 op）未实现**，只做了 `--auto-timeout` 缩放。 |
| #122 | 纯文档 + guard；停止规则是文本单一定义，**未在 gate 代码层强制**。 |
| #123 | 门禁在 `gate_check.py`；**`interface_contract_check` 未自动接入该键**；DVP 卡是 assumed 模板，未核实。 |
| #126 | `gate_check` G0 advisory；**`pcb_gate.py`（PG1–PG8）未动**；恢复字段缺失只 warn。 |
| #130 | **只在 `gate_check.py` G5**；`pcb_gate.py` PG3 同名检查未改。 |
| #133+#137 | 未在真实 EDA 跑 `pcb_apply_plan --apply` 回读；铺铜成员用"节点点在多边形内"近似（整段 track 穿过铺铜但无端点在内的极端情况不覆盖）。 |
| #129 | 并行会话完成；本会话未复核实现与测试覆盖。 |
| #139 | S18 未在仓库内对照数据手册核过 2A 电感（无手册访问，fail-closed）；S23/S27 落在 `gate_check.py`（`pcb_gate.py` 同名逻辑未动）。 |

**跨体系待对齐（贯穿多个 PR 的共性边界）**：分析会话的 gate 改动都在 `gate_check.py`（G0–G6 离线门禁）；`pcb_gate.py`（PG1–PG8 交付门禁）是另一套证据角色/时序模型，等价检查（netpath fallback、规则放宽、G6 handoff、interface_pinout）尚未落到该体系。

---

## 4. 复盘报告里尚未落地的项（26/27 条之外）

以下仍未 open/未跟踪（`skill-shortcomings.md` / `skill-feedback-report.md`），建议后续单独评估：

- **S19（中）**：额定值应力检查只覆盖电容耐压，电感/电阻/其他应力未覆盖。
- **S24（中）**：天线禁铜等 RF 安全警告可标 `accepted` 放行，PG4 不区分类型。
- **S25（中）**：`pcb check` 覆盖不全只算 advisory，与 `layout-lint` 不一致。
- **R09（P1）**：输出编码规范（`--json` 单 JSON、非终端不输出 emoji、`sys.stdout.reconfigure`）。
- **R15**：已否决（S06 明确不建并行 `.eda/closure.json`，恢复字段进 `design-state`）。
- **S18 的硬事实遗留**：2A 电感 Isat/Irms 尚未对照数据手册终核（实装件 SWPA4020S2R2MT 标"待核"）；需人工核对手册后回填标准件 rating 并把块默认件标记为 confirmed。

---

## 5. 分析会话产物（不在本仓库）

分析阶段的工作区产物（原始 zip 解包、分析报告、PR/issue body、测试日志、机械移植补丁）位于分析会话工作区，未随本仓库提交；如需复现请取原始 `hardware-design-skill-PR-pocketcam-x1.zip` 与 `zsx3896926/EasyCirq` 的 PR #105–#141 历史。

---

## 6. 仓库当前状态

- `origin/main` tip：`a08f6c1`（fix release #141）。
- 11 个落地项全部合并；issue #108–#115、#134–#136 全部 `CLOSED`。

---

## 7. 建议的下一步

1. 单独开 issue 跟踪 §4 未落地项（S19/S24/S25/R09）。
2. 把 `gate_check.py`（G0–G6）已实现的 gate 检查同步到 `pcb_gate.py`（PG1–PG8）：netpath fallback、规则放宽、G6 handoff、interface_pinout。
3. 人工对照数据手册终核 S18 的 2A 电感（SWPA4020S2R2MT）Isat/Irms，回填标准件 rating。
4. 若需真实验收，任选 #119/#133+#137 在一个真实工程上跑 `pcb_apply_plan --apply` + fresh DRC 回读，补 NOT RUN 证据。
