---
id: R4-ASSET-INDEX-R4P6
layer: decision-assets
last_reviewed: 2026-10-22
scope: J/L 切片；完整索引见 decisions/README
---

# 决策资产索引示例（R4-P6）

> 本示例只覆盖本轮 J/L 工作流负责的决策资产与既有决策记录模板，用来演示固定列、依赖与冲突字段；不声称其他工作流的资产已提交或已验证。完整索引见 `easycirq/references/decisions/README.md`（跨工作流文件，本分支未创建）。
> 路径只做指针；不复制设计卡、故障库或项目文件内容。

| id | kind | path | domain | stage | applies_to | source_ids | evidence | status | last_reviewed | depends_on | use_when | contract_ref | conflict_id | conflict_summary | affected_assets | resolution | recheck_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R4-J | reference | easycirq/references/decisions/j01-module-reuse.md | power | design | P01;R4-P2 | PWR-S07;PWR-S09;MCU-S09;PWR-S06 | E3 | active | 2026-10-22 | - | 跨产品复用充电器/power path 或其他电路块前，判断合同、条件与拒绝条款 | - | - | - | - | - | 电芯、充电电流、外壳散热、输入源或产量变化 |
| R4-L | reference | easycirq/references/decisions/l01-asset-validity.md | system | design | P02;R4-P6 | PWR-S01;PWR-S11;PWR-S05;IF-S03;IF-S04;IF-S12;PWR-S15;PWR-S16 | E3 | active | 2026-10-22 | - | 旧资产被新项目/新板版引用，或需要区分来源冲突与版本/范围差异时 | - | - | - | - | - | 来源换版、PCN/EOL、标准换版 |
| R4-CASE-J01 | case | easycirq/references/decisions/cases/r4-case-j01-charger-power-path-reuse.md | power | design | R4-P2 | PWR-S07;PWR-S09;MCU-S09;PWR-S06 | E3 | active | 2026-10-22 | R4-J | 需要看充电器+power path 复用被拒绝或有条件接受的完整判定 | R4-J | - | - | - | - | BQ24074 后缀的 min/typ/max、θJA、C 号或电芯上限变化 |
| R4-CASE-L01 | case | easycirq/references/decisions/cases/r4-case-l01-asset-validity-conflict.md | system | design | R4-P6 | PWR-S01;PWR-S11;PWR-S05;PWR-S06 | E3 | active | 2026-10-22 | R4-L | 同一文档两个修订日期、或只读标题的范围差异需要裁决时 | R4-L | PWR-S01;PWR-S11 | SLVA477C 封面 2026-09 与修订历史 2026-10 不同值；SLVA673A 封面与文档历史不同值 | R4-L;R4-CASE-L01 | 引用只写文档号/Revision C，不写月份；PWR-S05 只作方法索引 | 原厂更新 PDF 或页面；取得正文裁决 |
| R4-TPL-MODULE-REUSE | template | easycirq/assets/decisions/module-reuse-record.template.md | power | design | P01;P02;P03 | - | E3 | active | 2026-10-22 | - | 填写某个电路块/模块的复用合同 | - | - | - | - | - | 合同字段或枚举变更 |
| R4-TPL-ASSET-INDEX | template | easycirq/assets/decisions/asset-index.template.md | system | design | P01;P02;P03 | - | E3 | active | 2026-10-22 | - | 新建或维护决策资产索引 | - | - | - | - | - | 固定列或状态枚举变更 |
| R4-TPL-DECISION-RECORD | template | easycirq/assets/decisions/decision-record.template.md | system | design | P01;P02;P03 | - | E3 | active | 2026-10-22 | - | 写决策头与 typed block | - | - | - | - | - | 模板 schema 由集成人统一修改 |
| R4-SCRIPT-ASSET-CHECK | script | easycirq/scripts/decision_asset_check.py | system | design | P01;P02;P03 | - | E3 | active | 2026-10-22 | R4-TPL-ASSET-INDEX | 对索引做固定列、重复 ID、悬空依赖、冲突字段与状态枚举检查 | - | - | - | - | - | 索引格式或检查规则变更 |

**覆盖说明：** 本切片为 2 参考 + 2 案例 + 3 模板 + 1 脚本；合并目标为 12 参考 + 13 案例 + 14 模板 + 6 脚本。其余资产不在本切片范围内，完整索引见 `easycirq/references/decisions/README.md`；本示例不声称其已提交或已验证。

**有效性门禁：** 许可不明、EOL/PCN 未核、旧项目未验证或来源未登记的资产不得写成 `active`；`待查` 只允许出现在 `path` 且 `status=planned`/`blocked`。
