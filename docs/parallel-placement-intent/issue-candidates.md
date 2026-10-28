# 越界问题候选（只记录，不修改）

本文件记录任务 L 在只读审阅仓库既有放置相关实现时发现的、**超出本任务允许路径**但
建议主分支后续处理的事项。本任务没有修改任何公共模块/共享文件；以下均基于静态阅读与
只读运行（0 次 EDA 调用），未做代码补丁。是否修复、何时修复由主维护者决定。

检查范围：

- `design-hardware/scripts/design_engine/pcb_workflow.py`（`plan_candidates`、
  `template_placements`、`bind_template` 等，只读）
- `design-hardware/scripts/pcb_apply_plan.py`（`merge_module_plans`、`--module-plan`）
- `design-hardware/scripts/sch_layout_model.py`（`--module-plan`）
- `design-hardware/assets/pcb-placement-templates.json`
- `design-hardware/assets/layout-modules/*.module-plan.json`
- `design-hardware/references/design-engine.md`、`pcb-execution.md`、
  `offline-regression.md`

## IC-1 两个同名 “module plan” 格式并存，语义完全不同

- 现象：仓库里有两个都叫 module plan、但结构不兼容的东西：
  1. `assets/layout-modules/*.module-plan.json`：给 `sch_layout_model.py --module-plan`
     用，字段是 `schemaVersion`/`zones[]`（`id/title/core/members/netPolicies`）/
     `readingOrder`，**没有坐标**，表达原理图功能分区；
  2. `pcb_apply_plan.py --module-plan`：接受的是“placement module batch”，字段是
     `placements[]`（含绝对 `x/y/rotation/layer`）+ `base_semantic_sha256` +
     `partial:true`，表达 PCB 绝对位姿批次。
- 证据：
  - `design-hardware/scripts/sch_layout_model.py:163-249`（读取 zones/members、校验
    `member_in_two_zones`/缺失/多余位号）；`:462-470`（`--module-plan` 必填）。
  - `design-hardware/scripts/pcb_apply_plan.py:184-239`（`merge_module_plans` 只接受
    `placements`/`base_semantic_sha256`/`partial` 等字段并校验批次一致性）；
    `:1348-1349`（`--module-plan` 可重复一次传入多个 module batch）。
- 影响：人类/LLM 看到 “module plan” 容易把一种格式传给另一种命令；两者的“模块”
  含义（原理图分区 vs 放置批次）也不同。
- 建议（不在本任务范围）：文档与字段命名上明确区分（如 schematic module plan /
  placement module batch），或在 CLI 帮助与 `references/*.md` 中互相引用；
  本任务的 `integration-proposal.md` §1.2 给出两种来源到放置意图输入的映射思路。

## IC-2 `--module-plan` 批次只校验绝对位姿硬合法，没有“相对意图”一致性层

- 现象：`merge_module_plans` 校验的是 base 哈希、项目/文档、designator 唯一、scope
  不扩大；随后 `validate_placement` 检查板内/重叠/固定/edge/keepout/spacing 等绝对
  硬约束。它能发现“两个模块的位姿互相碰撞”（测试
  `tests/test_pcb_module_batch.py::test_cross_module_collision_refuses`），但**无法
  发现**“两个模块的绝对位姿各自合法、却与上游模板/人工意图的相对关系矛盾”（例如
  模板要求去耦电容在核心下方 300 mil，实际批次放在上方，两者都满足硬几何）。
- 证据：`design-hardware/scripts/pcb_apply_plan.py:184-239`（只做批次字段一致性，
  无相对约束）；`tests/test_pcb_module_batch.py`（覆盖哈希/重叠/scope/project 冲突，
  无相对意图用例）。
- 影响：模块批次的“意图”只存在于生成它的工具/人脑里，交接后不可复核；出错时只能靠
  最终几何偶然发现。
- 建议（不在本任务范围）：集成时在生成 module batch 前用
  `placement_intent validate/plan` 做意图一致性前置校验（见
  `integration-proposal.md` §1）；或让 module batch 可选携带 CCG 声明。

## IC-3 模板 `frame: board` 的相对偏移不能直接映射成“节点相对”约束

- 现象：`assets/pcb-placement-templates.json` 的模板级 `frame` 有 `core`（默认）与
  `board` 两种。`frame: board` 的 `relative[].dx/dy/rotation` 是**板坐标流向**下的
  相对量（不随核心旋转），而放置意图 CCG 的边是“`to` 相对 `from`、随 `from` 旋转”
  的节点相对量。把 `frame: board` 模板直接映射成 CCG 边（`from=core`）会丢失语义，
  除非集成层先知道核心的绝对朝向并做换算。
- 证据：`design-hardware/assets/pcb-placement-templates.json` 的 `note`
  （"Offsets are relative, in mil, in the template/core frame; they are rotated with
  the core"）与三个模板的 `"frame": "board"`：`connector-protection-core`、
  `mcu-debug`、`dual-channel-switch-led`；`design-hardware/references/pcb-execution.md`
  §4 绑定规则 4（`frame: core` 随核心旋转；`frame: board` 保持板坐标流向）。
  偏移条目本身只有 `role/dx/dy/rotation/unit`，**没有 per-entry frame 标记**。
- 影响：集成映射时若不处理 `frame`，会生成“数值对但语义错”的 CCG；本任务不能用
  模板数据直接当输入。
- 建议（不在本任务范围）：在模板 schema/文档中明确 per-template `frame` 的换算公式，
  或为 `relative[]` 增加 per-entry frame；集成层加单元测试覆盖 `frame: board`
  模板的 CCG 转换。

## IC-4 模板偏移单位是 per-entry `unit`（mil），放置意图用顶层 `units` + `_mm` 字段

- 现象：模板每条 `relative` 用 `dx/dy` + `unit:"mil"` 表达（当前 10 个模板的 29 条
  相对项全部带 `unit:"mil"`）；放置意图输入用顶层 `units.length` 声明单位、字段名
  带 `_mm` 后缀，并在读入时统一换算成 mm。两者若在适配层混用，容易出现“数值没换算/
  重复换算”的错误，而 JSON 本身不会报错。
- 证据：`design-hardware/assets/pcb-placement-templates.json` 的 `relative[]`；
  `docs/parallel-placement-intent/contract.md` §2.3、§9（单位换算只做一次）。
- 影响：集成适配层是唯一换算点，缺测试时可能把 400 mil 当 400 mm。
- 建议（不在本任务范围）：在集成层提供转换函数 + 金标准用例（`400 mil ↔ 10.16 mm`），
  并在 `integration-proposal.md` 的映射表中显式记录。本任务已在
  `integration-proposal.md` §1.2 标注该换算。

## IC-5 多锚点（top-right / bottom-left / bottom-right / center）需要先定义包络锚点语义

- 现象：v1 的 `--anchor` 只实现 `top-left`；`top-right`/`bottom-left`/`bottom-right`/
  `center` 对 `plan`/`explain` 直接 exit 4（用法错误），`validate` 接受并忽略。
  这不是遗漏实现，而是一个**语义设计问题**：模块的帧原点由约束链决定，而 bbox 是
  子项 AABB 的并集；若允许“锚点 = 包络某个角”，则“帧原点”与“包络角点”之间会出现
  循环定义——包络取决于子项位置，子项位置又依赖父帧锚点。
- 证据：`docs/parallel-placement-intent/contract.md` §1、§4.1（v1 固定 `top-left`）；
  `design-hardware/scripts/placement_intent/__init__.py` 的
  `SUPPORTED_ANCHORS = ("top-left",)`；`cli.py` 对其它 anchor 返回 exit 4。
- 影响：v1 的契约是自洽的（固定锚点、bbox 不归一），但如果下游需要 right/bottom/center
  锚点（例如对齐习惯或与宿主坐标约定一致），当前没有可用路径。
- 建议（不在本任务范围）：扩展前先明确“模块包络锚点”与“节点帧原点”的关系——例如
  规定 anchor 只影响**元件/叶节点**的局部矩形偏移，模块帧仍由约束链决定，再为
  bbox/重叠推导定义锚点偏移；同时补 contract 示例、测试与基准。当前的取舍记录在
  `design.md` §5.5 与 §8。

## 未越界声明

- 以上事项**未修改** `design_engine/`、`pcb_apply_plan.py`、`sch_layout_model.py`、
  `assets/`、`references/`、`SKILL.md`、`zhigou_mcp/` 或任何共享入口；也未提交
  任何补丁到这些路径。
- 本任务新增的 `placement_intent` 包与测试/基准/文档均在允许路径内；集成由后续 PR
  实施。
- 静态阅读 + 只读运行，0 次 EDA 调用；没有复制论文或第三方代码。

## 结论

有 5 项值得主分支后续处理，均属于“放置意图/模块计划交接”的表示、文档一致性与能力
边界问题，不是本任务可以自行修复的范围。当前交付的 CLI 在 v1 契约（固定 `top-left`）
内自洽可用；`design_engine` ↔ `placement_intent` 的集成应至少先解决 IC-3
（`frame: board` 语义）与 IC-4（单位换算），否则可能生成语义错误的 CCG。
