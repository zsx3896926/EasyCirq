# PCB 命令族真机验收证据（E 包，2026-10-22）

## 环境

- 客户端：嘉立创EDA专业版 4.1.78（bridge 4.1.78.34f5b8d9）
- 会话：CLI 半离线（`online: false / half_offline: true`），headless
- 工程：`C:/Users/jlc/work/hds-round5-scratch/pcb-e2-verify.eprj2`
  （从 round-3 审计 `probe2-copy.eprj2` 复制，33 器件 / 98 线 / 1 铜区边框）
- 执行器：`design-hardware/scripts/eda_exec.py` @ 本轮分支（含 `pcb` 命令族）

## 执行序列与结果

| 步骤 | 命令 | 结果 | 证据 |
|---|---|---|---|
| 能力探针 | `pcb doctor` | `status: complete`，33/98/0/1/1/83 计数全读，0 read_errors | 见下（未单独存档，首跑即 complete） |
| 读快照 | `pcb read --output pcb-read-before.json` | `ok`，integrity complete，16 网络，线端点/器件坐标可读 | pcb-read-before.json |
| 最小写入 | `pcb apply --plan plan-minimal.json --save` | `verified`：line d995f855 / via e6f48254 / pour 边框全部创建+回读匹配；保存确认 saved:true；计数 98→99 线、0→1 孔、1→2 铜区边框 | pcb-apply.json |
| 铺铜事实 | apply 内 poured 计数 | 1→1，delta 0，`fill_recomputed: false` —— 边框创建不重算填充 | pcb-apply.json |
| 关闭重开 | `pcb reopen-check` | `match`：pcb 身份、6 类计数、primitive id 集合、网络名集合全部一致，diffs 为空 | pcb-reopen-check.json |
| 器件放置 | `pcb apply --plan plan-components.json --save` | `verified`：component_flat（footprint ref）→ DC2、component_search（DC005-T20）→ DC3，均 layer 1；33→35 器件；保存确认；再次重开 `match` | pcb-apply-components.json、pcb-reopen-check-2.json |
| DRC | `pcb drc` | `ran`，但 `pcb_Drc.check(false,false,false)` 返回 **boolean**，无错误明细 | pcb-drc.json |
| 制造导出 | `pcb export` × 5 种 | gerber/pickandplace/bom/pdf/pcb_info **全部返回空对象** `{}`，仅存 raw 捕获 | exports/*-raw.json |

## 能力结论（E1 矩阵更新）

- 已验证可用（半离线 CLI，2026-10-22 本轮真机复测）：pcb 枚举、激活、六类计数读、
  器件（含 footprint_ref/component_ref）/线/过孔/铜区边框行级读、网络名/长度/图元数读、
  线创建、过孔创建、铜区**边框**创建、器件创建（flat ref 与 search 两条路径都真机通过）、
  保存、关闭重开比较。**E 包验收序列（读→最小修改→回读→保存→关闭→重开→比较）对
  器件/线/过孔/铜区边框四类原语全部成立。**
- 明确不可用：
  - 铺铜填充重算（边框创建后 poured 计数不变；需 GUI 动作）。
  - DRC 错误明细（check 返回 boolean）。
  - 制造资料导出（全部 getter 返回空对象；需 GUI 全在线会话）。
- 未探测：板框专用原语、器件移动/旋转、删除、规则配置写入。

## 过程记录

- 首跑 `pcb drc`/`pcb export` 因 `pcb_not_activated` 失败：根因是 `pcb reopen-check` 泄漏第二个 CLI 会话
  （finally 只关了 first_session），泄漏会话占住同一工程副本导致新会话激活 PCB 文档失败。
  修复：finally 同时关闭两个会话；单发命令对 `pcb_not_activated` 增加 3 次专用重试（该错误发生在任何写入之前，重试不会重复写）。
  泄漏会话 `0be3fc5c-…` 已用 `close --force` 清理。
