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

## 真实 EDA 现状（外部工程，非本仓库工作树）

`C:/Users/jlc/work/photo-led-5v-20261026`：5V 光控 LED 板，已实际绘制、保存重开、官方导图；
`sch gate` PASS，`sch check` 0，19 器件/12 网回读 MATCH。上一会话最后在补
`docs/layout-snapshot.json` + `sch_layout_check.py --strict`，但快照生成脚本在最后一次
运行之后又被修改（18:22:10 > 18:21:42），**修复尚未重跑**；strict 结果为
`incomplete`（texts 覆盖不全、标题/用途 bbox 缺失、大量 frame_membership_gap）。
下一步先重跑修正后的 `docs/build_layout_snapshot.py`，再判断哪些是真实图面问题、
哪些是快照构造问题，不得直接把 `incomplete` 改写成 PASS。

## 后续工作包（按序，完成后更新本文件）

- **WP2 读回验证契约**：统一 snapshot/expected/after 对比口径，区分
  identity / pin-net / geometry / text coverage；为 `eda_exec` 写入增加后置条件验证。
- **WP3 配方→原生编辑**：把 `sch_recipe` 候选转成执行器 typed move/wire 计划，
  写入后按 WP2 契约回读；未完成真机验证前保持 `NOT RUN`。
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
