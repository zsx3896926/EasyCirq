# 决策资产索引（Agent 填写，用户不填）

> 用途：给决策参考、案例、模板与脚本做一层可检查的指针，回答“哪个任务该读哪个资产、它依赖谁、现在是否仍有效”。
> 范围：只收决策资产，合并目标为 12 参考 + 13 案例 + 14 模板 + 6 脚本，共 45 条；不复制 60 张设计卡、33 条故障与 4 个项目文件的内容。
> 证据规则：模板存在、脚本通过或 model-consistent 都不等于硬件已验证；`待查` 不当作通过。

## 1. 固定列

| 字段 | 必填 | 含义与取值 |
|---|---|---|
| `id` | 是 | 资产唯一 ID，如 `R4-J`、`R4-CASE-J01`、`R4-TPL-MODULE-REUSE`、`R4-SCRIPT-ASSET-CHECK` |
| `kind` | 是 | `reference` / `case` / `template` / `script` |
| `path` | 是 | 仓库相对路径；未创建时写 `待查` 且 `status` 只能是 `planned`/`blocked` |
| `domain` | 是 | power / interface / mcu / manufacturing / system 等 |
| `stage` | 是 | concept / design / bring-up / production / retirement |
| `applies_to` | 是 | 适用项目/产品/板版，分号分隔 |
| `source_ids` | 是 | `source-register.md` 已登记的来源 ID，分号分隔；无来源写 `-` |
| `evidence` | 是 | `E1` / `E2` / `E3` |
| `status` | 是 | `active` / `conditional` / `deprecated` / `retired` / `planned` / `blocked` |
| `last_reviewed` | 是 | `YYYY-MM-DD`，最后一次实际核对日期 |
| `depends_on` | 是 | 上游资产 ID，分号分隔；无写 `-`；必须能在本索引解析 |
| `use_when` | 是 | 什么用户任务/触发条件该读它，不写“通用” |
| `contract_ref` | 是 | 案例引用的合同/参考 ID；无写 `-`；必须存在且 `kind=reference` |
| `conflict_id` | 是 | 未解决冲突 ID，如 `PWR-S01`；无写 `-` |
| `conflict_summary` | 是 | 一句话写对象、参数、条件、不同值 |
| `affected_assets` | 是 | 受该冲突影响的资产 ID，分号分隔 |
| `resolution` | 是 | 当前裁决或“未裁决”；不得把待查写成已解决 |
| `recheck_trigger` | 是 | 何时必须重评（来源换版、PCN/EOL、标准换版、新量产项目） |

## 2. 状态与证据

- `active`：合同完整且当前可用；`conditional`：有可测试条件或部分未知。
- `planned`：尚未创建；`blocked`：许可、EOL/PCN、来源或安全责任未清。
- `deprecated`：不用于新设计，保留给旧产品；`retired`：已退役，必须写替代 ID。
- 许可不明 → `blocked`；EOL/PCN 未核 → `conditional`/`blocked`；旧项目未验证 → `E3`；来源未登记 → 不得填 `source_ids`。

## 3. 关系与冲突

- `depends_on`、`contract_ref` 不得悬空；上游为 `retired`/`deprecated` 时下游必须复核。
- 只有同一对象、同一参数、同一条件、不同值才登记 `conflict_id`；版本/范围差异写在 `resolution` 或参考文档，不冒充冲突。
- `conflict_id` 非 `-` 时，`conflict_summary`、`affected_assets`、`resolution`、`recheck_trigger` 必须同时有值；`conflict_id` 为 `-` 时前三个冲突字段写 `-`，`recheck_trigger` 仍可单独填写。
- 每个冲突只登记未解决状态；解决后保留历史行并写裁决日期，不删除。

## 4. 维护

- 新增或修改资产时先更新本索引，再把 `last_reviewed` 改为实际核对日期。
- 合并后的索引用 `python design-hardware/scripts/decision_asset_check.py <index.md> --source-register design-hardware/references/source-register.md` 检查。
- 解析失败、缺固定列或出现重复 ID 时，脚本必须返回非零并给出 JSON findings；不得静默通过。
