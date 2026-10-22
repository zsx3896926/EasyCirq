# F1 rev3 B 包（排版/警告/审图）证据（2026-10-22）

## 环境与副本

- 客户端：嘉立创EDA专业版 4.1.78（bridge 4.1.78.34f5b8d9），CLI 半离线 headless 会话
- 基线副本来源：`C:/Users/jlc/work/hds-round3-int-scratch/f1-rev3-layout.eprj2`（#8 重排产物）
- **最终交付副本：`C:/Users/jlc/work/hds-round5-scratch/f1-b-v5.eprj2`**（pristine 重做 + 独立审图必须修复项）
- 过程副本：`f1-rev3-b-package.eprj2`（首次尝试，含文本 bug 污染，仅留作缺陷证据）、
  `f1-b-clean.eprj2`（探针副本）、`f1-b-final.eprj2`（v1 文本坐标，视觉碰撞，弃用）

## 冻结与序列（v3 基线；v5 为最终交付，差异见下节）

| 步骤 | 产物 | 结果 |
|---|---|---|
| 冻结读 | final-snapshot-before.json / netlist-before / layout-before（早期副本目录同名件） | 21 parts/57 wires/37 flags/20 ports，integrity complete |
| 删 2 条零长度中段折线 | v3-apply-delete.json | verified，57→55 |
| 重画 2 条线 | v3-apply-add.json | verified，55→57 |
| 写 2 条文本（DRAFT、未用脚注记） | v3-apply-texts.json | verified，save=True |
| 新会话读 | v3-snapshot-final.json | 57 wires、2 texts 于 (300,200)/(60,75) |
| DRC | v3-drc.json | warn=1（仅 CHECKFLOATPIN，设计意图保留） |
| 网表 | v3-netlist.net | SHA256 `709B505F26F34C96FA3CF76D960B0861D7F4B21289EDAA5280E4326223DD6FD6` = golden `f1-rev3b.net` |
| 导图 | v3-layout.png | 目检：DRAFT 与注记位于空白带，无遮挡 |
| 重开比较 | v3-reopen.json / v5-reopen.json | match，diffs=0（含 texts 域） |

处置表：`drc-erc-disposition.md`；独立审图：`independent-review.md`（AI 审图，非人工）。

## v5 相对 v3 的变化（独立审图必须修复项）

| 项 | 结果 |
|---|---|
| 孤立错误电源符 `027ca788bcdee892`（3V3 网名套 Power-5V 符号，600,620） | guarded delete 删除；DRC 仍 1 warn，网表 SHA 不变 |
| 端口挤压（RST/EN/TXD 与 IO2/IO0 垂直 10 单位） | **未修**：v4 实验（短导线+删端口+重建）与零长度退化线合并出 `ONENETNAME(IO2、IO2)`，已撤销 |
| C101/C106 值串可读性 | **未修**：v4 实验改 Manufacturer Part 触发 `ATTRMATCHCODE` 并改变 BOM 身份字段，已撤销 |
| v4 实验证据 | v4-apply-a1/a2/b.json、v4-drc.json、v4-netlist.net、v4-layout.png、v4-reopen.json（保留为失败记录） |

**安全修法（下一步）**：先受控清理 10 条零长度退化导线（每删一条网表 diff 验证连接不变），
再搬端口；值串显示需 GUI 改属性文本或换正确 MPN（G 包）。

## 客户端文本图元能力矩阵（4.1.78 半离线 CLI，实测）

| 操作 | 内存生效 | save 返回 | 重开后持久 | 结论 |
|---|---|---|---|---|
| `sch_PrimitiveText.create` | 是 | true | **是**（数据+PNG 渲染均证实，TEXT-PERSIST-PROBE） | 可用 |
| `sch_PrimitiveText.delete`（id 形态） | 是 | true | **否** | 客户端缺陷 |
| `sch_PrimitiveText.delete`（对象形态） | 是 | true | **否** | 客户端缺陷（probe-text-delete.js） |
| `sch_PrimitiveText.modify` | 是 | true | **否** | 客户端缺陷（apply-b2-texts-fix2.json） |

推论：CLI 通道下文本只能「一次放对」；放错无法回收。v2/v3 迭代即由此产生（v1 坐标 Y 轴假设反、
v2 DRAFT 与 R105 端口六角符相切）。坐标约定：画布 y 自页底向上，PNG y 自上向下。

## 仍开放（需 GUI 会话一次操作）

- 标题栏版本格 V1.0 → 目标值（sheet 图元字段无 CLI 编辑入口）；图面以 DRAFT 文本表达草稿状态。
- 若人工审图提出图面修改（移动器件/标签），CLI 的 part/net_flag move 能力可用于除文本外的对象。
