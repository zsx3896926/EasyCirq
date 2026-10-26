# v0.9：原理图验收工具链升级（含三个真实工程）

## 定位（合并评审请以此为准）

**这是工具链能力升级，不是“绘图效果已理想”的交付。** 三个工程证明的是：真实写入 → 回读 →
原生检查 → 渲染文字/几何检查 → 官方导图 → 保存重开这条链路可用，以及检查器会如实暴露
残留；它们不作为参考设计或已验收电路推荐。

已知图面不理想之处（photo-led v16）：阈值区纵向拉得很长、反馈回路绕行较大、R3/R4/R5/R7
位号离本体偏远、LED 区下方留白明显；另有 7 个反向电源/地旗按 BLOCKED 保留。AMS1117
案例的输出电容仍是 22µF 0805 陶瓷，不是数据表保证的 22µF 固体钽，**稳定性未验证**，
只能证明绘图/回读流程。

## 这次解决什么

把 v0.9 从“有规则、有离线候选”推进到“能在真实嘉立创 EDA 中写入、回读、导图、保存重开”：

1. **渲染文字全覆盖**：`svg_text_bbox.py` 用无头 Chromium/Edge 实测官方 SVG 的全部 `<text>`。photo-led 同页 API 只给 72 条，实际渲染 134 条；v14 为 136 条——图框行列号、图签字段、符号内脚名/脚号、netflag 网名不再被当成“已覆盖”。
2. **真实回读适配器**：`layout_from_easyeda.py` 把 `sch list --include-page-primitives`、`visible_text.bboxes`、`sch sheet-geometry --from-svg` 与渲染文字拼成 `sch_layout_check` 输入；无法归属的可见文字标 `unowned`，不再静默漏掉。
3. **图面语义检查**：新增 `unowned_visible_text`、`duplicate_net_text`、`unanchored_net_text`、`netflag_rotation_outlier`、`netflag_text_vertical`、`zone_reading_order`、`title_block_duplicate_text`、`text_wire_clearance`。自身导线豁免改为**边缘级**：`anchor_id` 只证明归属；导线进入文字 bbox 但在 1 raw 内只记 info，进入主体仍 blocking。无结点交叉的宿主证据必须绑定**页 ID、快照 SHA-256 和两段导线 ID**，页/哈希不匹配或导线不在当前快照时按 stale evidence 拒绝并保持 blocking；只有点+导线全匹配才降为 readability hint，共线重叠始终 blocking。符号自有脚名/脚号不再当普通碰撞；info-only 不阻塞（`--fail-on-info` 可升级）；`--out` 以 UTF-8 落盘。
4. **设计意图对账**：`pin_net_intent_check.py` 按物理引脚连通组比较设计意图与 `sch read`，网名拼写可不同（`DISCH` vs `$1N117`），多/少脚、拆网、并网、未声明连接逐条列出；支持 `sch read` 的 `number` 字段。
5. **器件身份核验**：`component_identity_check.py` 比较位号/device/symbol/footprint/脚名与 BOM 属性，并加入实例 `uniqueId`/`component.uuid`（缺失或变化 blocking，仅 primitiveId 变化 info）；`--expected-changes` 只接受带 reason+evidence 且 before/after 精确匹配的 BOM 变更，否则 blocking。无 PCB 输入时明确 `pcb_binding=not_run`，实际 BOM 导出未提供时 `NOT RUN`。
6. **BOM C 号审计**：`bom_cnumber_check.py` 检查 EasyEDA BOM 的数量/位号/MPN/`C<数字>`、空 Supplier Part 的项目本地映射回填、映射冲突、重复位号、同 MPN 不同 C 号和指定位号值；photo-led 本地映射 **15/15** 回填，RV1=`10kΩ`。不检查库存/价格/MOQ/SMT。
7. **真实失败回归**：`tests/fixtures/photo-led-acceptance.json` 与 `photo-led-v14/` 保留 134/136 条渲染文字、真实阅读顺序 2,1,3,4、孤立 `LED_CTRL`、图签重复等样例；v14 还保留宿主 `sch read` 的 4 个无结点交叉证据。全部测试 **966 OK**，`skill_selftest.py` **5 PASS**。

## 三个真实工程的验收结果

全部为 EasyEDA Pro 4.1.78 / easyeda-agent 1.15.0 全在线 GUI 会话；未使用半离线 CLI 会话。

### 1）photo-led-5v-20261026（修复）

- P1 `cd008f919db36eba`；12 网 / 47 脚 / 0 floating / 37 组件。
- 分区编号按阅读顺序 **1 光敏 → 2 供电 → 3 阈值 → 4 LED**，标题在框左上；zone2 purpose 持久修复。
- 图签两处 `Claude Code` 已消除（绘制/审阅留空，避免平台“titleblock 字段 + sheet 属性”双渲染重复）。
- 官方整页：`evidence/final-v18.png/.svg`（v18 恢复到 v16 视觉状态；12 网 / 0 floating）。
- 最终 checker：`strict_missing: []`、`status: info_only`；3 条无结点交叉 hint 的宿主证据绑定页 `cd008f919db36eba`、快照 SHA-256 `e8b9f5ed…` 和两段导线 ID，3 条 5 raw 内贴线 hint；无 text-text overlap / zone_reading_order / title_block_duplicate_text / blocking bbox contact。
- 器件身份（v14→v16 新鲜回读）：`pass_sch_only`，19/19 位号、uniqueId、component.uuid、device/symbol/封装/脚名不变；1 条 `expected_change_unused` info。
- **7 个反向旗：已实测“原地旋转”不可行并回退**。删除后在原锚点按桩方向重建（rotation 90/270）能把原生 `reversedNetFlags` 降到 0，但产生 7 个竖排电源/地文字并引入 2 处 blocking 文字接触（zone3 purpose 等），肉眼明显变差；随后删除新旗、按原位置 rot=0 重建，回到 v18。`sch check` 仍有 7 条 `reversed-net-flag`，按 **BLOCKED** 保留；正确修法是改桩线走向/数据驱动 compose，不是原地转旗。图签 Drawed 留空。
- BOM 已实际导出并完成本地映射 enrichment：`evidence/photo-led-bom-enriched.csv`（15/15 行回填，SHA-256 `493F5D75…`）；`bom_cnumber_check.py` 对 RV1=`10kΩ` 及其余 14 行检查 **pass**。`bom export` 默认 standard-parts 表 0/15，项目本地 `photo-led-standard-parts.json` 补足；库存/价格/MOQ/SMT 可贴仍 **NOT RUN**。
- SCH↔PCB：项目内 PCB1 `99b8366b0bdc971f` 已 linked，但 `pcb list` 为 **0 器件**，无法做绑定核验，按 **BLOCKED** 记录；未导入/创建 PCB 器件。

### 2）ne555-blinker-1hz-20261026（新建）

- 工程 `856ec8994a544ad999a5adf69be04dd9`；P1 `2beb0746a6a6c75a`；10 器件 / 7 网 / 0 floating。
- 1k + 68k + 10µF → `f≈1.05 Hz`、`D≈50.4%`；OUT→330Ω→5mm 红光 LED；RESET 直接接 +5V。
- `sch gate` **PASS**；`pin_net_intent_check` **match**；保存 → reload → 回读引脚-网络保持。
- 证据：`C:/Users/jlc/work/ne555-blinker-1hz-20261026/evidence/`（`final-after-reload.png/.svg`、`gate.json`、`read-after-reload.json`、`pin-net-diff.json`）。
- 残留：5 个电源/地标记因管脚水平而竖排网名；3 处文字/本体轻微接触；无 purpose 文字（typed API 无自由文本创建）；PCB/仿真/实物 NOT RUN。原生归档 `evidence/final.epro2`（44,712 B，SHA-256 `0b7ad4a3…`，restoreVerified=false）。

### 3）ams1117-3v3-20261026（新建）

- 工程 `7686883008644dea9fd9317d949a5f92`；P1 `86faeee12e6b50e6`；6 器件 / 3 网 / 0 floating。
- J1 → 10µF → AMS1117-3.3（SOT-223）→ 22µF + 100nF → J2；三功能区框。
- `sch gate` **PASS**；`pin_net_intent_check` **match**；保存 → reload → 回读保持。
- 证据：`C:/Users/jlc/work/ams1117-3v3-20261026/evidence/`（`final-after-reload.png`、`final-v2.svg`、`gate.json`、`read-after-reload.json`、`pin-net-diff.json`）。
- 残留：输出电容是 22µF 0805 陶瓷，**不是**数据表保证的 22µF 固体钽，稳定性未验证；8 个电源/地标记竖排；无 purpose 文字；未做负载/纹波/热/PCB。原生归档 `evidence/final.epro2`（35,416 B，SHA-256 `793169d7…`，restoreVerified=false）。

## 评审重点 / 明确未做

- 评审者已独立查看 v16 官方图、checker、身份检查、BOM 与 PR 状态；**尚未独立重跑 960 tests / selftest**，合并前建议在干净工作树复跑。
- “checker 通过”不等于“布局漂亮”：photo-led 仍有阈值区纵向过长、反馈回路绕行大、部分位号离本体远、LED 区留白；这些是已知视觉残留，不作为本 PR 的完成标准。
- AMS1117 案例只证明绘图与回读流程；22µF 陶瓷输出电容的稳定性未验证，**不能作为已验证电路推荐**。
- **没有**把任何配方标成 `eda-verified`：三张图仍有可见文字方向/注释缺口，且 555/稳压器主要用 typed 执行器流程而非 `sch_recipe.py` 直接落地。
- 未做 PCB 全流程、仿真、实物、采购/下单；未发布 Release；未替换用户已安装 Skill；未合并 PR。
- 半离线 CLI 会话未用于本验收；`--allow-discard-unsaved` 仅用于重新打开已保存工程。
- 平台限制记录：free text 的 `move/setState/SDK delete` 不持久，删除需 `sch prim-delete`；新建 free text 必须 `alignMode=2` 才左对齐；titleblock 的可见 `Drawed` 会与 sheet 属性各渲染一次。

## 验证命令

```bash
python -m unittest discover -s tests     # 966 tests OK
python design-hardware/scripts/skill_selftest.py  # 5 PASS
# 每个工程：
easyeda sch gate --json
python scripts/pin_net_intent_check.py docs/netlist-intent*.json evidence/read-after-reload.json
easyeda sch export-image --format png --page <page> --out evidence/final.png
easyeda doc reload <page> --project <name>
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
