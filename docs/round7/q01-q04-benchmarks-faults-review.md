# Q01–Q04：基准、A/B、故障与人工审图状态

日期：2026-10-24。所有结论区分合成/真实、离线/真机。

## Q01：真实质量基准与坏图夹具

### 已建立

1. **12 个合成几何基准**：`design_engine/benchmarks.py`，对应 12 类常用画法（电源入口、LDO、Buck、MCU、晶振、复位、USB-C、I2C、分压、运放/比较器、MOS、RS485/CAN）。每个用例包含一个故意错误、预期候选码和证据级别。
   - 运行：`python scripts/design_engine_cli.py benchmarks --json`
   - 结果：**12/12 复现声明候选**；全部标记 `synthetic_offline_geometry_not_real_eda`。
2. **一个真实几何基准**：温度报警板冻结 bundle（26 器件/65 导线/14 网/34 净标签），见 [a01](a01-baseline-freeze.md)。
3. **一个真实网表基准**：F1 rev3b 的 `eda_exec` 快照（21 器件/57 导线，无 bbox），可用于身份/网表对比，不能做几何审计。

### 未达到

- 验收要求“至少两个来自独立真实设计的几何金样”；本轮只有温度报警板一个真实几何样本。F1 有真实快照但缺 bbox/文字，不能冒充几何金样。
- 没有 12 个真实 EDA 金样；12 个是合成几何夹具，只能证明检查器可复现，不证明真机图面质量。
- 没有许可证/来源问题：合成数据由本仓库生成；真实样本是本项目工程。

## Q02：公平 A/B、消融与预算

同一冻结输入、同一预算（离线、无随机种子、确定性排序）下：

| 方法 | 输入 | 输出 | 结果 |
|---|---|---|---|
| 原生 `sch check` | 温度报警板冻结文本 | 5 条警告 | 1 marker-overlap、1 out-of-sheet、2 designator-wire、1 missing-partition |
| 本引擎 audit | 同一 bundle | 10 hard + 7 advisory | 3 文字重叠、2 文字压器件、4 导线穿文字、1 越页等 |
| 本引擎 label plan | 同一 IR | 4 个 Name/Designator 移动 | 模拟 10 → 4 hard；`verify_plan` match |
| 原生 PCB DRC | 同一 PCB dump | 18 条 | 16 Clearance + 2 Connection |
| 本引擎 PCB connectivity | 同一 PCB dump | +5V 2 个断开组 | 与原生 2 条 Connection Error 一致 |
| 本引擎 placement | 同一 PCB dump | 5 候选 | force-2：25,078.7 → 20,779.6 mil HPWL；拥塞 overflow 2186 → 1756；关键回路仍 5 条 |
| 本引擎 label plan（真实导入副本） | 同一页的 live 回读 | 9 个 Name/Designator 移动 | audit 11→1 hard；原生 check 5→3；DRC 0；layout-score 84.2→86.7；identity/重开 match |
| 本引擎 router | 51 对同网引脚 | 47 routed / 4 no_solution | 独立验证仅 22 条 valid，29 条被拒绝 |

消融：

- **去掉净标签识别**：30+ 个正常导线端被误报为悬空；加入导线自有 `Name` 属性识别后降为 0。
- **去掉覆盖门**：空 `components/texts` 会被报成 `no_candidates`；加入 `coverage` 后返回 `incomplete`。
- **只看 HPWL**：force-2 最短，但关键回路仍 5 条；所以选择顺序是硬合法 → 关键回路 → 拥塞 → HPWL，不是单一分数。
- **只看总 DRC 数**：原生 18 条中 2 条 Connection、16 条 Clearance；本引擎按规则/对象/坐标逐条保留，未用数量代替身份。

失败公开：

- 路由 29/51 被独立验证拒绝；这是当前 S05 的失败集。
- placement 的 critical-snap 候选没有把去耦距离降到 100 mil 以内；没有把“候选”说成“已改善”。

## Q03：持久化与故障注入

已覆盖的离线故障：

| 故障 | 测试/行为 |
|---|---|
| JSON 中夹 CLI 文本 | `load_json_tolerant` 删除深度>0 的非 JSON 行，记录 removed；`pcb-drc.json` 18 条成功解析 |
| 截断/非法 JSON | 返回 `invalid_json`，不崩溃 |
| 快照缺 `parts[].bbox` | `layout_from_snapshot` 输出 `coverage.absent`；`sch_layout_check` 返回 `incomplete` |
| 重复位号 | `validate_ir` 明确失败 |
| 计划前置位置过期 | `verify_plan` 返回 `stale_from_position` |
| 网表身份变化 | `compare` 报 `changed_pin_nets`，`identity.match=false` |
| 证据文件变化 | `state --verify` 报 `changed` |
| 页/板 UUID 漂移 | IR `source` 保留 UUID；比较/计划带 `projectUuid`/`documentUuid`；没有 live apply 时不能验证漂移拒绝 |
| 保存重开 | **真实通过**：隔离副本 save → doc reload → 回读，与 after3 一致（moved attrs 0） |
| 超时、页切换、人工并发修改 | **NOT RUN** |

## Q04：工程师盲审与视觉差分

- 没有人工硬件工程师参与；没有隐藏算法身份的盲审；没有人工视觉差分。
- Agent 已检视真实 after3 导出 PNG：文字重叠/导线穿文字已消失，底部仍可见越页的 `Name`；这不是人工验收。
- 本轮只有 Agent 的几何/身份审计、合成基准和一次真实 PNG 检视；这些不能替代人工审图。
- 建议的人工审图问题：
  1. 温度报警板整页是否能按电源→比较器→输出跟读？
  2. 4 个被计划移动的位号/值是否移到更易读的位置？
  3. PCB 的 +5V 2 个断开组是否符合预期（R16_1、e244）？
  4. J1 本体外伸、丝印 R1/R2 侧向是否可以接受？
- 状态：`pending`，不阻止已完成离线部分。
