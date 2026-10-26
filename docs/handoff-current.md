# Current handoff — 2026-10-26 — v0.9

## 仓库与分支

- 仓库：`hardware-design-skill`；工作树：`C:/Users/jlc/work/hds-merge-20261026`
- 分支：`feat/skill-v0.9`
- 基线：`origin/main` `66a1d22`（v0.8.1 内容；本地历史以 `ce9a0d9` 等价树重建）
- 本文件记录的起点提交：`ce9a0d9`；后续提交以 `git log --oneline -5` 为准

## v0.9 目标

在 0.8.1 的真实 EDA 能力上，继续提升原理图/PCB 自动设计质量，顺序为：

1. 确定性布局：角色/相对约束 → 可复算候选 → 受保护写入 → 几何一致性。
2. 工程设计规则：只做可由实测网表/几何确定性判定的规则，不伪造器件模型。
3. EDA 原生编辑：候选必须能转成执行器 typed 计划，不靠原始 JS。
4. 读回验证：写入/保存/重开后的身份、引脚—网络、几何、文字覆盖分别报告。
5. PCB：布局/布线/DRC/制造前的确定性质量检查。

## 已完成并验证（本会话接手时未提交）

- `references/schematic-authoring.md`：绘图执行顺序、能力盘点、局部闭环、文字实测与失败处理；
  明确 0.9 固定真实任务为 555 闪灯、光控 LED、稳压电源。
- `references/schematic-recipes.md` + `assets/schematic-recipes.json` + `scripts/sch_recipe.py`：
  5 个参数化局部配方（divider、npn-led-driver、opamp-inverting-feedback、555-astable、
  regulator-decoupling），只做平移、保持 rotation/mirror 与 pin-net，输出
  `experimental_unverified_in_eda` 候选和离线 SVG。
- `scripts/sch_text_audit.py`：实测可见文字 bbox 的 text-text 重叠/过近审计；覆盖七类文字，
  缺类/零面积/无 bbox 一律不能 strict 通过；明确 `visual_verified=false`。
- `scripts/sch_layout_pipeline.py`：单页质量证据 fail-closed；模型 blocker、分页、quality
  退出码与报告矛盾、非法 JSON 都使 `status != planned`；记录 before 哈希与
  `placement_consistency`，不执行 compose。
- `design-hardware/.version` 升至 `0.9.0`；`SKILL.md` 入口改为“先生成可复用布局，再执行与验收”。
- 测试合并：新 8 个 pipeline 测试并入 `tests/test_sch_layout_pipeline.py`，删除误放在
  `design-hardware/scripts/` 下的重复文件（原位置会导致 `unittest discover` 全量失败）。
- 证据：`python -m unittest discover -s tests` → **896 tests OK（33.657 s）**；
  `python design-hardware/scripts/skill_selftest.py` → **5 PASS / 0 FAIL**。
  新增定向测试 19 个（recipe 4、text audit 7、pipeline 8）。
- 边界：以上全部是离线合成/离线几何测试，**不是真机 EDA 写入或视觉验收**。
  `tests/fixtures/photo-led-visible-text.json` 是历史实测载荷，不含引脚名/自动线名。

### WP2 图面检查三分类（2026-10-26 本会话）

- `sch_layout_check.py` 新增可选 `texts[].owner`、`title_block_owned`、
  `policy.self_text_contact_tolerance`：
  - 已声明 owner 的文字浅贴自身符号边缘（默认阈值 0，项目可设 0.5 raw）→
    `symbol_text_edge_contact`（info），不再混同普通 `bbox_overlap`；深入本体仍报重叠。
  - 图签自身字段文字只豁免 `overlaps_title_block`，仍参与其他碰撞检查；未知 ID 视为输入无效。
  - 所有 `bbox_overlap`/`overlaps_title_block` 输出实际重叠宽高，便于人工分诊。
- `references/offline-tools.md` 已同步契约与边界：分类不等于通过，coverage 仍须完整。
- 测试：`tests/test_schematic_readability.py` 新增 5 个分类/拒绝用例；全量 **900 tests OK**；
  skill_selftest **5 PASS**。

## 真实 EDA 现状（外部工程，非本仓库工作树）

`C:/Users/jlc/work/photo-led-5v-20261026`：5V 光控 LED 板，已实际绘制、保存重开、官方导图；
`sch gate` PASS，`sch check` 0，19 器件/12 网回读 MATCH。本会话重跑了修正后的
`docs/build_layout_snapshot.py`（标题改为从 `frame-apply-v3.log` 取最终ID、`contains`
剔除netflag、补owner/title_block_owned），strict 结果从 80+ 条误报降到 7 条：
- 4 条 `symbol_text_edge_contact`（U1/J1 属性文字与本体 0.5 raw 贴边，info）；
- 1 条真实文字叠印：U2 的 Name 与网名标签文字（重叠约 39×10 raw）；
- 1 条导线穿 R4 的 Name 文字；
- 1 条 C2 的 Name 文字跨越 zone1-power 分区框下边。
strict 仍为 `incomplete`，唯一 `strict_missing` 是 `coverage.texts`：符号内部脚名/自动线名
无 bbox API，属于真实能力缺口，**不得改成 complete**。图面已实际查看官方 PNG，
U2 叠字与 C2 跨框肉眼可见。下一步用原生属性移动修复这 3 处，再 save/reload/导图复核。

## 后续工作包（按序，完成后更新本文件）

- **WP3 配方→原生编辑**：把 `sch_recipe`/`layout-source` 候选转成 `eda_exec` 的
  `part.match+place` 计划（执行器没有 move op），写入后做 pin-net、刚体平移和
  netlist 不变核验；未完成真机验证前保持 `NOT RUN`。
- **WP4 工程规则门禁**：只实现实测网表可判定的规则（去耦、上拉、限流、稳压器输入/输出电容、
  NC/悬空、电源网冲突等），每条规则带证据等级和误报边界。
- **WP5 PCB 质量**：基于 PCB 回读的 courtyard/丝印/板框/安装孔/电源回路/DRC 可判定项，
  与既有 `gate_check` 分工，不重复已有 gate。
- **WP6 固定真实任务**：555 闪灯、光控 LED、稳压电源；每个记录首个候选、返工次数、
  重复失败机制和官方导图结果；未做就如实写 `NOT RUN`。

## 下一条具体动作

1. 提交本工作包（authoring/recipes/text audit/pipeline/version/tests）。
2. 运行修正后的 photo-led 快照构造与两项检查，把真实图面问题与快照问题分开。
3. 按能力盘点结果落 WP2，先写失败测试再改代码。
