# 审查报告（并行任务 E）

任务：四层板高速信号参考平面与回流风险审查（离线几何/拓扑）
分支：`feat/parallel-return-path-audit`，基于 main `9a951edc21481dc3ae91460acc11aa3e08a7be8a`
性质：离线审查工具开发 + 冻结回归基准。**未调用 EDA、未画板/改板、未做 SI 仿真。**

## 1. 结论摘要

- 交付一个可独立运行的审查器：`python -m return_path_audit validate|audit|explain`。
- 五组检查 E1–E5 全部实现，含严格输入校验、证据绑定/陈旧拒绝、覆盖与未知传播。
- 45 个冻结 CLI 场景 45/45 通过；本包 106 个测试、全仓 1889 个测试全绿。
- 结论语义保守：`pass_with_scope` 只表示“声明范围内未发现参考路径几何/拓扑缺陷”，
  **不**代表阻抗、SI/EMI、DRC、制造或硬件功能通过；候选回流只到 `potential_candidate`。

## 2. 交付物

| 路径 | 内容 |
|---|---|
| `design-hardware/scripts/return_path_audit/` | CLI、严格校验模型、几何内核、E1–E5 检查、报告/原子写、SVG 叠加、来源注册 |
| `tests/return_path_audit/` | 106 个测试：几何、校验、五组行为、CLI 契约、变形、对抗、4 个 holdout |
| `benchmarks/return-path-audit/` | 45 个冻结场景（含 8 个非法输入）+ 生成器 + runner + result.json |
| `docs/parallel-return-path-audit/` | 契约、几何支持、来源登记、验收矩阵、本报告、集成建议、交接、issue 候选 |

未修改任何公共文件（SKILL.md、references、README/CHANGELOG/版本、runtime/connector/protocol、
distribution、CI、顶层依赖、feedback、compose、design_engine、ecosystem_routing）。

## 3. 五组检查实现要点

| 组 | 关键行为 |
|---|---|
| E1 | 显式物理层序校验（不按 ID 排序）；参考角色/网络一致性；参考冲突不自动选赢家；层厚缺失无法判断最近参考时 unknown；非相邻参考告警；候选参考不当作已声明参考 |
| E2 | 直线投影 vs 多边形铜（含孔洞）的**精确区间划分**（非采样）；区分跨网分割/孔洞/同网微缝/铜边结束/无铜/走廊不足；内部接缝不算铜边界；计入线宽/走廊/容差；给出区间坐标、长度、相关铜与多边形 ID |
| E3 | 换层 via 存在性/网络/物理跨度；参考变化检测；候选回流过孔必须同网+跨度覆盖参考层+连接证据（`connected_copper_ids`/连通岛/pad/thermal/fill）+距离阈值+快照绑定；只输出 `potential_candidate`，**永不** `recovered_return_path=true`；GND→电源变化不自动推荐 GND via，电容只作有条件候选；附近同网 via 只作 unknown 提示 |
| E4 | 只用声明的差分对；比较两腿的参考网络/层、跨缝风险、换层结构；单边跨缝/不同参考/非对称换层分别报告；不重算长度/阻抗 |
| E5 | 每网/每段 `checked/unknown/not_applicable` 长度与原因；空路径、全 unknown、未指派参考、弧线/不支持对象、pour boundary 均不得返回 PASS；未支持几何保留部分已检查长度，整体 incomplete |

## 4. 开发期发现并修复的缺陷（反例驱动）

1. **窄缝会被区间跳过**：区间合并时把“参数 t 差”与“长度容差”比较，导致 0.05 mm 缝
   区间被整段丢弃（曾出现“跨 0.2 mm 分割却 PASS”）。改为只跳过重复断点，并由基准
   `28-sparse-sampling-narrow-slit` 与单测锁定。
2. **跨网分割被误判为铜边**：覆盖判定只使用声明网络铜，看不到另一网络铜。增加
   `context_regions` 与 `wrong_reference_net` 状态，精确区分“真缺口”与“跑到别的参考网”。
3. **同网相接/重叠误报走廊不足**：内部接缝被当成铜边界。改为“并集铜边界”语义。
4. **非直线段崩溃**：语义哈希对 `start/end=None` 的弧线段抛异常。已修复，并把
   CLI 未捕获异常映射为退出码 5，避免与 `fail=1` 混淆。
5. **非法输入退出码错**：不可解析 JSON 曾返回 5；现统一为 `input_invalid` 退出码 4 并输出
   validation 文档。
6. **覆盖记账把理想化铜算成 checked**：`declared_ideal` 曾计入 `checked_length`；现只认
   实际填充 + 完整校验证，其余计入 unknown。
7. **同一 copper 对象内的多 polygon 未做相接/重叠检查**；已覆盖（含 `same_object` 标记）。
8. **E5-502 重复计数**：一个 unsupported 条目同时声明 signal+segment 时产生两条 unknown；
   已改为每对象一条，并让 `kind != straight` 也产生 `RP-E5-502`。

## 5. 基准与测试结果（本机实测）

| 项目 | 结果 |
|---|---|
| 基准场景 | **45/45 通过**，总耗时 **5.15 s**（单进程逐场景） |
| 本包测试 | **106 tests OK**（`-s tests/return_path_audit`，12.2 s） |
| 全仓测试 | **1889 tests OK**（`-s tests`，128.1 s） |
| 运行环境 | Python 3.13.15 / Windows 11（`result.json` 记录完整环境） |
| 标志 | `simulated=true`、`real_eda=NOT RUN`、`network=NOT USED` |
| 冻结 | 每场景记录输入字节 SHA256、语义 SHA256、期望/观察状态、规则集、覆盖、逐场景耗时 |

基准覆盖：完整平面、窄缝、跨网分割、孔洞、凹多边形、边缘走廊、同网相接/微缝/重叠、
mm/mil、非标准四层、正确回流候选、跨度不足、错网、未连接、陈旧证据、参考网变化（含电容）、
差分单边跨缝、不同参考、非对称换层、pour boundary、弧线/unsupported、空路径、
missing via、8 类非法输入，以及“固定稀疏采样会漏掉窄缝”的专门反例。

## 6. 证据与未知语义（本任务的核心价值）

- 几何只能证明几何：同网相接、微缝、via 与铜的连接、真实电连接均保持 unknown，
  除非输入提供实际填充铜/连通岛/连接证据。
- 只有 `actual_fill` 计入 checked；`pour_boundary`/`ideal_plane`/`unknown` 只能是
  potential/unknown。
- 陈旧快照（对象/证据 `source_snapshot` 与项目快照不一致）拒绝复用。
- 未支持几何/对象不得被忽略：计入 unknown，整网 incomplete。

## 7. 限制与 NOT RUN（如实声明）

| 项目 | 状态 |
|---|---|
| 真实 EDA / Connector / 宿主窗口 | `NOT RUN`（任务禁止） |
| 真实工程快照重放 | `NOT RUN`（未取得合法真实四层板快照；不使用原厂示意图转写的合成 JSON 冒充真实板） |
| SI/EMI/阻抗/眼图/串扰仿真 | `NOT RUN`（非目标） |
| DRC/DFM/Gerber/制造/功能验收 | `NOT RUN`（非目标；不宣称） |
| 独立第三方盲测 | 无；holdout 由独立测试作者基于几何/契约编写，不宣称外部盲测 |
| 一手资料页码/节核验 | 部分 `V2/V3`（环境不能解析 PDF；搜索端点 401），见 `source-register.md` |

## 8. 来源说明

规则方向性依据 5 条一手文档（TI SLLA414、ADI MT-031、AMD UG583、IPC-2221、USB-IF USB 2.0），
本轮核验等级与缺口逐条记录在 `source-register.md`；**没有任何数值阈值**来自这些来源，
全部保持 `project_configured`，报告不把它们写成通用高速标准。

## 9. 复现命令

```bash
cd hds-rpa-worktree
python benchmarks/return-path-audit/run_benchmark.py
python -m unittest discover -s tests/return_path_audit -v
python -m unittest discover -s tests -v
```

## 10. 结论边界

本报告证明：审查器在给定契约与 45 个冻结几何/规则场景上行为一致、可回归，
并能在输入允许的范围内定位参考平面/回流路径的几何与拓扑风险。
它**不**证明任何真实 PCB 的 DRC、SI、阻抗、EMI、制造或硬件功能通过。
