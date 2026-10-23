# PCB 门禁修复记录（2026-10-23，响应 PR #10 评审）

评审报告的三项离线反例均已复现、修复并加回归；另做了一次真实 EDA 回归。

## 1. 创建对象不在回读快照中仍判 verified

- 根因：`verify_pcb_items()` 只比较执行返回值，`after` 快照参数未被使用。
- 修复：按操作类型在 `after` 的对应类（components/lines/vias/pours）中按 **primitive id**
  查找对象；找不到 → `not_in_readback`（失败）。随后逐字段比较**快照中的实际属性**：
  - line：net/layer/x1/y1/x2/y2/width；
  - via：net/x/y/hole/diameter；
  - pour_outline：net/layer；
  - component：designator/layer/x/y/rotation。
  必需字段在快照中为 None → `unverified_fields`（不算通过）；执行返回只用于解析 id。
  另核对 `poured_after` 与快照 poured 计数，不一致记 `counter_mismatch`。
- 回归：`test_created_object_missing_from_readback_fails`、`test_unreadable_readback_fields_are_not_a_pass`、
  `test_expected_mismatch_is_a_conflict`（执行返回层=1、回读层=2 → 以回读为准判冲突）。

## 2. PCB 实质变化、重开比较仍 match

- 根因：`compare_pcb_snapshots()` 只比较计数、id 集合与网络名。
- 修复：逐对象深比较——器件（designator/layer/x/y/rotation/footprint）、走线
  （net/layer/端点/线宽）、过孔（net/x/y/hole/diameter）、铜区（net/layer）、焊盘（net）；
  另比较每个网络的 length/primitive_count。浮点字段用 0.01 容差。
  双侧均读不到的必需字段记入 `unverified`，`complete=false`；重开命令仅在
  `match=true 且 complete=true` 时返回 `match`，否则 `incomplete`/`mismatch`。
- 回归：`test_moved_component_is_a_diff`、`test_rotated_component_is_a_diff`、
  `test_line_net_and_width_changes_are_diffs`、`test_line_endpoint_change_is_a_diff`、
  `test_via_and_pour_fields_are_compared`、`test_net_length_change_is_a_diff`、
  `test_unreadable_geometry_marks_comparison_incomplete`。

## 3. 截断快照仍判完整

- 根因：`pcb_snapshot_integrity()` 只看 counts 是否为 null 与 read_errors。
- 修复：逐类检查 `truncated`、`total` 与 rows 数量、counts 与 total 一致性、section 缺失；
  网络新增 `nets_total`/`nets_truncated` 标记并参与判定。任何覆盖不足 → `incomplete`，
  并在 `coverage_issues` 中给出类别与原因；写入门禁沿用该结论。
- 回归：`test_truncated_component_list_blocks_integrity`、`test_row_budget_mismatch_blocks_integrity`、
  `test_nets_truncation_blocks_integrity`、`test_missing_section_blocks_integrity`。

## 真实 EDA 回归（半离线 CLI，副本 `f1-gate-verify.eprj2`）

| 步骤 | 结果 | 证据 |
|---|---|---|
| `pcb apply`（GND 线 3000,-600→3100,-600, w12, --save） | `verified`，100→101 线，save=true | `gate-apply.json` |
| `pcb reopen-check`（深比较） | `status=match`，`match=true complete=true diffs=0 unverified=0`，counts 35/101/1/2/1/89 | `gate-reopen.json` |

全量测试：**589 OK**（新增 13 项 PCB 门禁回归）。

## 状态

- E 包门禁缺陷已修复并有离线+真机回归，E 恢复 **DONE**（其余限制不变）。
- B/C/L 按评审意见收紧为 PARTIAL（人工审图、C2/C5、6/12 场景）。
