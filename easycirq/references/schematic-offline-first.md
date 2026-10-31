# 原理图离线先行（Offline-First Schematic）

> 一句话：**离线跑通并连续达标 → 才允许一次性上真机**。每轮用 15 项 KPI 量化，
> 缺证据一律 `BLOCKED`，不把离线 PASS 说成真机可用。

## 何时用

新建、重排、改板、换料、多页合并等任何会改变原理图拓扑/连接/图面的任务；尤其当
agent 需要在真机 EDA 里落图时。纯问答、纯选型、只读检查可跳过本流程，直接按
[输出优先契约](../SKILL.md) 处理。

## 六阶段

| 阶段 | 做什么 | 产出 | 是否碰 EDA |
|---|---|---|---|
| S1 离线规格化 | 功能模块清单、电源树、引脚/复用表、接口契约、BOM↔封装↔C 号映射、机械约束、NC 声明 | `spec.json` / 表格 | 否 |
| S2 离线布局与连接优化 | 版式规划 → 模块候选 → 标签/端口规划 → 打分选优 | `style-plan.json`、候选 JSON、被拒原因 | 否 |
| S3 离线质量度量 | 跑各 checker 得原始报告 | `reports/*.json` | 否 |
| S4 KPI 门禁 | 15 项 KPI 聚合裁决 + 稳定性判定 | `kpi-report.json`、`kpi-history.jsonl` | 否 |
| S5 一次性上机 | dry-run 对账 → 单次批量写入 → save → reload → 回读 → 官方导图复核 | 回读 JSON、PNG/SVG | **是** |
| S6 沉淀落库 | KPI 回执、门禁证据、失败模式 | `reports/`、`docs/` | 否 |

S2 的规则不变：局部拓扑电路（分压、反馈、滤波、去耦、晶振、保护、复位）**100% 直连**；
跨功能块/跨页/密集数字信号用语义标签，两端留短引线扇出。先跑
`scripts/sch_style_plan_check.py`，未过不得进器件。

## 15 项 KPI

定义与阈值以 [`metrics/schematic-kpi.v1.json`](../../metrics/schematic-kpi.v1.json) 为准，
`scripts/sch_kpi.py` 内置一份一致的默认值（`tests/test_sch_kpi.py` 校验两者不漂移）。

| # | KPI | 类别 | 来源 checker | 默认门限 |
|---|---|---|---|---|
| 1 | 未连接/悬空 | 硬 | `netlist_check.py` | 0 |
| 2 | 跨区穿越 | 硬 | `sch_wire_metrics.py` | 0 |
| 3 | 图面重叠 | 硬 | `sch_layout_check.py`（含文字压本体/越界） | 0 |
| 4 | 连接转换 | 硬 | `sch_layout_check.py`（当前仅无主可见文字） | 0 |
| 5 | 总线完整性 | 硬 | `netlist_check.py` | 0 |
| 6 | 线长 | 软 | `sch_wire_metrics.py` | ≤120 mm（profile 可调） |
| 7 | 可跟读率 | advisory | `sch_readability_metrics.py`（标签网占比的补数） | 不阻断，只记录 |
| 8 | 分区均衡 | 软 | `sch_wire_metrics.py` | ≤0.3 |
| 9 | ERC | 硬 | `sch_drc_metrics.py`（DRC fatal+error） | 0 |
| 10 | 引脚复用 | 硬 | `pin_plan_check.py`（需引脚规划输入，未自动） | 0 |
| 11 | 去耦覆盖 | 硬 | `sch_decoupling_metrics.py`（IC 电源脚 × 电容） | 0 缺失 |
| 12 | 命名规范 | 硬 | `sch_connectivity_metrics.py`（重名/默认名） | 0 |
| 13 | 料号映射 | 硬 | `sch_bom_metrics.py`（BOM 封装/型号/C 号） | 0 |
| 14 | 网表 diff | 硬 | `sch_connectivity_diff.py`（前后两份 IR） | 0 |
| 15 | 回读一致 | 硬 | `sch_connectivity_diff.py --metric readback_diff`（重开后 IR） | 0 |

**证据边界（实现事实，不是设计理想）**：

- KPI 9 用 `sch drc --json` 的 fatal+error；warn 记录但不计入。
- KPI 11 是启发式：IC（`U*`/`IC*`）电源脚所在网至少有一个电容（`C*`），不做 AC 或布局验证。
- KPI 10（引脚复用）需要 `pin-plan/v1` 规划输入，没有规划表就不判；页面**完全没有 IC**
  时由管线写 `verdict: n/a`（`status: na`，既不阻断也不算通过）；有 IC 但没规划表仍判缺失。
  不要用现成连线反推。
- KPI 15（回读）只在真实 S5 之后有 `connectivity-reopen.json` 时才判；离线阶段标 `NOT RUN`。
- KPI 14/15 共用 diff 工具，但语义不同：14 是改板前后，15 是写入前后 + 保存重开。
  缺证据时按 `BLOCKED` 处理，不要用「看起来没问题」放行。


- 连接度量必须同时给 `--list`，否则显式 NC 引脚会被算成悬空（IR 不带 NC 标记）。
- `single_node_nets` 只统计 `scope=local` 的单成员网；global 网在单页只有一端是正常的跨页连接。
- KPI 7（可跟读率）当前是**页级代理指标**：直连率 = 1 − 标签网占比。实测 P1/P2 都是 0%，因为电源/地
  和跨区信号都靠 flag/标签连接——这正是它只能 advisory 的原因。IR 不含模块归属，
  「拓扑电路 100% 直连」仍需人工/导图复核，不能报通过。

**硬约束恒为 0，profile 不能放宽**；profile 只覆盖软指标（`dense-digital` 线长 80 mm、
`power` 可跟读率 0.7 等），见 KPI 定义文件的 `profiles`。

## 用法

```bash
# 1. 生成输入骨架
python scripts/sch_kpi.py --template > reports/kpi-input.json

# 2. 把各 checker 报告挂上去（也可直接写进 input.checks[*].metrics）
python scripts/sch_kpi.py --input reports/kpi-input.json \
  --check connectivity=reports/netlist.json \
  --check layout=reports/layout.json \
  --check text=reports/text.json \
  --history reports/kpi-history.jsonl --record-history \
  --out reports/kpi-report.json --md reports/kpi-report.md
# 退出码 0=PASS 1=REVIEW 2=BLOCKED
```

- 每个 check 只需 `verdict` + `metrics`（或 `findings[*].code`）；缺指标即 `missing`。
- `verdict: fail` 表示检查跑完了、有违规，指标照常计入；`error/blocked/unknown`
  表示检查没跑成，判 `BLOCKED`。
- 带 `codes` 的指标按 finding code 计数，且**只计已确认项**：
  `review_candidate`、`severity: info` 的条目单独记录、不进硬指标。
- 同一 `project` + `page` 的轮次写进 `--history`，脚本自动比较「新增违规」与
  「连续 PASS 轮数」。
- `apply_allowed=true` 才允许 S5 上机；单轮 PASS 不够（默认要求连续 2 轮，
  `--min-rounds` 可覆盖但需在回执里写明理由）。

### 实测桥接（真机快照 → 离线 KPI）

**一键（推荐）**：快照目录放 connectivity.json（必需）、list.json（必需，排除显式 NC）、svg-text.json / layout.json（无 layout.json 时用前者生成）、drc.json（KPI 9）、bom.tsv（KPI 13）、connectivity-before.json（KPI 14）、connectivity-reopen.json（KPI 15），然后

```bash
python scripts/sch_offline_pipeline.py --snapshot-dir reports/p1-snapshot \
  --project <P> --page P1 --out-dir reports/p1
# 退出码 0=PASS 1=REVIEW 2=BLOCKED；产物含 kpi-report.json/.md 与 history
```

**多页汇总**（读各页 `kpi-report.json`，按 (project,page) 去重取最新）：

```bash
python scripts/sch_kpi_scoreboard.py --reports reports \
  --expect-page P1 --expect-page P2
# 项目裁决 PASS 且每页 apply_allowed 才允许上机；未列出的页面按缺失处理
```

**分步（备查）**：

```bash
# 冻结快照（只读，不改工程）
easycirq --project <P> sch connectivity --page P1 > reports/p1-ir.json
easycirq --project <P> sch list --page P1 --include-bbox --include-pins \
  --include-wires --include-page-primitives > reports/p1-list.json
easycirq --project <P> sch export-image --scope page --page P1 --format svg \
  --out reports/p1.svg
python scripts/svg_text_bbox.py reports/p1.svg --out reports/p1-svg-text.json

# 离线归一 + 度量（不连 EDA）
python scripts/sch_connectivity_metrics.py --input reports/p1-ir.json \
  --list reports/p1-list.json --out reports/p1-connectivity-check.json
python scripts/layout_from_easycirq.py --list reports/p1-list.json \
  --rendered-text reports/p1-svg-text.json --out reports/p1-layout.json
python scripts/sch_layout_check.py reports/p1-layout.json --strict \
  --out reports/p1-layout-check.json
python scripts/sch_wire_metrics.py reports/p1-layout.json \
  --out reports/p1-wire-check.json

# 聚合裁决
python scripts/sch_kpi.py --input reports/p1-kpi-input.json \
  --check connectivity=reports/p1-connectivity-check.json \
  --check layout=reports/p1-layout-check.json \
  --check wire=reports/p1-wire-check.json \
  --history reports/p1-kpi-history.jsonl --out reports/p1-kpi-report.json
```

真机 `easycirq sch gate` 与离线 KPI 是两层证据：gate 查器件本体重叠、DRC、
短路/孤儿桩（不看未连接引脚）；离线 KPI 还查悬空引脚、单端网络、文字压字与
图框穿越。两层都过才上机。

## 上机纪律（S5）

1. 未过 S4 → **不上机**，只交离线候选 + KPI 表。
2. 写前 `--dry-run` 对账 + 冻结快照；写后旧快照失效，重新采集。
3. 单次批量写入；失败先查真实状态、按 journal 续做，**禁止整批盲重试**。
4. 保存成功 ≠ 写入成功 ≠ 重开仍在 ≠ 质量通过，四件事分开报告（缺一项 `NOT RUN`）。
5. 不执行任意 JS、不覆盖未声明对象、不为清告警改电气事实。

**已实测（2026-10-31，临时工程 `KPI-S5-Verify`）**：place → connect → save →
`doc reload` → 回读，`readback_diff = 0`；再放一个器件后 `readback_diff = 1`
（`component_added`），证明该 diff 双向可信。证据链见 `reports/s5-verify/`。

## 执行清单（agent 按序执行）

每步左列是动作，右列是可验收产物；**没有产物就没有这一步**。

| 阶段 | 动作 | 产物 | 通过条件 |
|---|---|---|---|
| 客户看 | `easycirq status` / `scripts/sch_status.py` | 一行状态 + 下一步 | `ready_to_write` 才是可写 |
| 客户看 | `scripts/sch_delivery_card.py --kpi-report <报告>` | 一张卡：✅/⚠️/❌ + 还差什么 | 只有 PASS + 有效通行证才说「可以打样」 |
| S1 | 写需求/模块/电源树/引脚/BOM 映射/NC 声明 | `spec.json`、`design-state.json`（`stage`+`recovery`） | 每个模块有输入/输出/供电/关键约束 |
| S2 | `sch_style_plan_check.py` | `style-plan.json` | exit 0，未过不得进器件 |
| S2 | `design_engine_cli.py plan-labels` | `labels-plan.json` | 跨区信号有语义标签 |
| S3 | 冻结快照：`sch connectivity` / `sch list --include-pins` / `sch export-image` + `svg_text_bbox.py` / `sch drc --json` / `bom export --type csv` | `snapshot/*.json`、`bom.tsv` | 同一时刻采集，记录 snapshot hash |
| S3 | `sch_offline_pipeline.py --snapshot-dir ...` | `kpi-report.json/.md`、`kpi-history.jsonl` | 见 S4 |
| S4 | 读 `verdict` 与 `stability.apply_allowed` | 同上 | 硬约束 0 违规、无回归、连续 2 轮 PASS |
| S5 | `dry-run` 对账 → 单次写入 → `sch save` → `doc reload` → 回读 → 官方导图 | `connectivity-before.json`、`connectivity-reopen.json`、PNG/SVG | `readback_diff = 0` |
| S6 | 回执与证据入库 | `reports/<page>/` | 每轮 KPI 表可追溯 |

**任何一步失败**：先读真实状态（`sch read`/`list`），按 journal 续做，禁止整批盲重试；
同一失败机制连续 2 次换方法；换方法仍失败就记录缺测并停在 `BLOCKED`。

## 门禁通行证（daemon 强制，不靠自觉）

`sch_kpi.py` 在 `verdict=PASS` 且 `apply_allowed=true` 时签发 `.easycirq/gate.json`
（默认相对 EDA 工作目录）；`BLOCKED/REVIEW` 时**删除**已有令牌，防止旧 PASS 被重放。

daemon 的 `handleAction` 对所有 `ActionSpec.Mutates=true` 的 typed action 校验令牌
（schema、verdict、未过期、project 匹配）。这是唯一入口——CLI、MCP、playbook 都走它，
**绕不过去**。拒绝时返回 HTTP 403 与以下之一：

| code | 含义 | 客户下一步 |
|---|---|---|
| `GATE_REQUIRED` | 还没有令牌 | 跑一轮门禁（PASS 后自动签发） |
| `GATE_NOT_PASS` | 令牌是 BLOCKED/REVIEW | 修掉阻断项后重测 |
| `GATE_EXPIRED` | 超过有效期（默认 30 分钟） | 重新测量 |
| `GATE_PROJECT_MISMATCH` | 令牌属于别的工程 | 对该工程重测 |

| 环境变量 | 作用 |
|---|---|
| `EASYCIRQ_GATE_MODE=strict`（默认） | 无有效令牌即拒绝写入 |
| `EASYCIRQ_GATE_MODE=warn` | 放行但审计记录（迁移期用） |
| `EASYCIRQ_GATE_MODE=off` | 仅排障用 |
| `EASYCIRQ_GATE=<path>` | 覆盖令牌路径 |

令牌有效期 `--gate-ttl-minutes`（默认 30）；`go test` 环境下自动 off，既有 daemon 测试不受影响。

令牌同时记录工程名与可选 `project_uuid`（`sch_kpi.py --project-uuid <uuid>`）：写入时用名字或 uuid
都能通过，换成别的工程一定被拒。**真机已验证**：无令牌 → `GATE_REQUIRED`；令牌 + 名字 → 放行；
令牌 + uuid → 放行；别的 uuid → `GATE_PROJECT_MISMATCH`。

## 与阶段门禁的关系

`scripts/gate_check.py` 管 G0–G6 阶段退出证据（需求、功能冻结、原理图、布局、电源地、
布线、制造）；`scripts/sch_kpi.py` 是 **G2_schematic 内部的细化度量**：它把同一份冻结
快照上的 15 项指标聚合成 PASS/REVIEW/BLOCKED，并给出 `apply_allowed`。
两者都通过才可上机；`sch_kpi` 的 PASS 不替代 `gate_check` 的 G2 证据，反之亦然。

## 诚实边界

- 15 项数字全部来自你传入的报告；脚本不重算几何、不连 EDA、不联网。
- 离线 PASS 只说明「声明的证据在给定快照上满足门限」，不证明电气正确、不证明
  图面美观、不证明实物可用。
- 导图复核必须用官方导出图（整页 + 拥挤局部）；叠加图带 `official_export:false`，
  不能冒充官方图。
- 缺证据即 `BLOCKED`，不因「看起来没问题」放行。
