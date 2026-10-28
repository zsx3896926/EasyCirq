# 审查报告（并行任务 E）

任务：四层板高速信号参考平面与回流风险审查（离线几何/拓扑）
分支：`feat/parallel-return-path-audit`，基于 main `9a951edc21481dc3ae91460acc11aa3e08a7be8a`
性质：离线审查工具开发 + 冻结回归基准。**未调用 EDA、未画板/改板、未做 SI 仿真。**

## 1. 结论摘要

- 交付一个可独立运行的审查器：`python -m return_path_audit validate|audit|explain`。
- 五组检查 E1–E5 全部实现，含严格输入校验、证据绑定/陈旧拒绝、覆盖与未知传播。
- 45 个冻结 CLI 场景 45/45 通过；本包 116 个测试、全仓 1899 个测试全绿。
- 结论语义保守：`pass_with_scope` 只表示“声明范围内未发现参考路径几何/拓扑缺陷”，
  **不**代表阻抗、SI/EMI、DRC、制造或硬件功能通过；候选回流只到 `potential_candidate`。

## 2. 交付物

| 路径 | 内容 |
|---|---|
| `easycirq/scripts/return_path_audit/` | CLI、严格校验模型、几何内核、E1–E5 检查、报告/原子写、SVG 叠加、来源注册 |
| `tests/return_path_audit/` | 116 个测试：几何、校验、五组行为、CLI 契约、变形、对抗、4 个 holdout、真实快照回放、`.epru` 适配器 |
| `benchmarks/return-path-audit/` | 45 个冻结场景（含 8 个非法输入）+ 生成器 + runner + result.json + **真实快照回放**（2 层，见 §5.1） |
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
9. **真实大铺铜性能**：真实快照的参考铜有数百条边，原实现逐段做 O(E²) 全量扫描
   （真实 2 层板 134 s）。加入“线段半宽范围 bbox 预裁剪”（语义等价：范围外的边不可能
   进入走廊）后降到 **1.8 s**，规则/状态/覆盖不变（仅移除远处边产生的伪断点，风险区间
   端点有亚 mil 级数值差异）。

## 5. 基准与测试结果（本机实测）

| 项目 | 结果 |
|---|---|
| 基准场景 | **45/45 通过**，总耗时 **5.99 s**（单进程逐场景） |
| 本包测试 | **116 tests OK**（`-s tests/return_path_audit`，22.8 s） |
| 全仓测试 | **1899 tests OK**（`-s tests`，157.4 s） |
| 运行环境 | Python 3.13.15 / Windows 11（`result.json` 记录完整环境） |
| 标志 | `simulated=true`、`real_eda=NOT RUN`、`network=NOT USED` |
| 冻结 | 每场景记录输入字节 SHA256、语义 SHA256、期望/观察状态、规则集、覆盖、逐场景耗时 |

基准覆盖：完整平面、窄缝、跨网分割、孔洞、凹多边形、边缘走廊、同网相接/微缝/重叠、
mm/mil、非标准四层、正确回流候选、跨度不足、错网、未连接、陈旧证据、参考网变化（含电容）、
差分单边跨缝、不同参考、非对称换层、pour boundary、弧线/unsupported、空路径、
missing via、8 类非法输入，以及“固定稀疏采样会漏掉窄缝”的专门反例。

### 5.1 真实快照回放（REAL data replay，2 层）

任务原本要求“能拿到合法真实工程快照则只读重放”。本轮核实：
**仓库内所有真实 EDA 回读快照，以及本机 EasyEDA Pro 的 6 个真实工程备份，全部是 2 层板**
（`copperLayers: 2`，仅 TOP/BOTTOM 铜层；`dual-scope-*` 工程尚未布线）。
**本机没有任何真实四层板数据**，因此不能用真实四层板回放，也不会用合成/示意图数据冒充。

已完成的真实数据回放（明确标注 2 层）：

| 项 | 值 |
|---|---|
| 原始快照 | `easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json`（真实 `easyeda pcb dump`） |
| 工程/快照 | `mcu-i2c-s3-20261026` / `mcu-i2c-s3-20261026:40b81985cfb4a5ed:2026-10-26T13:40:13Z` |
| 原始字节 SHA256 | `db7521f2883346f0d70126047927f2cf6a61343374c2e0cb71869649aa3a57fe` |
| 投影 | 真实 BOTTOM GND 实际填充铺铜（1 外环 + 8 孔，圆弧 ≤0.05 mil 离散）→ 参考铜；顶层 12 网 142 段真实走线；16 个真实过孔 |
| 结果 | **`fail`（exit 1）**；覆盖 142 段 / 307.0 mm；55 findings（41 error / 14 warning），7 unknown |
| 规则分布 | `RP-E2-202` 7、`RP-E2-204` 17、`RP-E2-205` 17、`RP-E2-206` 14 |
| 独立核对 | 抽查区间中点确认落在真实 GND 铺铜孔洞/边界内（如 BOOT (471.3,907.3) ∈ 孔洞#0），非解析假象 |
| 工程含义 | 2 层板底层走线/焊盘在底层 GND 铺铜刻出避让通道，顶层信号跨过时参考不连续——普通 DRC/等长检查看不到 |

产物：`benchmarks/return-path-audit/real-replay/`（input / report / overlay.svg / README），
投影器 `benchmarks/return-path-audit/replay_real_dump.py`，回归
`tests/return_path_audit/test_real_replay.py`。

**这不是四层板验证**：仅顶层走线建模，底层 22 段走线未审计；过孔连接证据缺失，换层回流
（E3）未产生结论；圆弧为声明容差的离散近似。拿到真实四层板 dump 后，用同一投影器加
`--stackup-json` 指定 4 层物理顺序即可重放（见 real-replay/README.md）。

### 5.2 真实四层板 `.epru` 回放（EasyEDA Pro 原生备份，只读）

本机另有一个**真实四层工程**的 EasyEDA Pro 自动备份；用新增的
`benchmarks/return-path-audit/replay_epru.py` 只读解析（不调用 EDA、不写回工程）：

| 项 | 值 |
|---|---|
| 数据 | 本机真实四层工程备份（L2=GND、L3=3V3，内层为实际铺铜；157 过孔） |
| 层识别 | `[L1, L2, L3, L4]`，平面网络来自真实铺铜而非猜测 |
| 投影 | 外层 645 段真实走线；按相邻内层做参考（L1→L2 GND、L4→L3 3V3） |
| 填充单位 | `POURED` 填充为 1/10 尺度序列化，按 bbox 比例自动识别并 ×10；无法识别则降级 `pour_boundary` |
| 换层 | 62 处由“真实过孔中心 + 两层走线端点”推断，规则写入 `source.producer` |
| 结果 | **`fail`（exit 1）**；覆盖 **88,585 mil（≈2,250 mm）**，unknown 长度 0 |
| findings | 365 条（148 error / 217 warning）：`RP-E2-202` 12、`RP-E2-204` 83、`RP-E2-205` 53、`RP-E2-206` 155、`RP-E3-304` 62；unknowns 79 |
| 工程含义 | 62 处顶层↔底层换层时参考由 **GND(L2) 变为 3V3(L3)**（真实网络变化）；外层走线跨真实平面避让孔的几何风险可逐条定位 |
| 回归 | `tests/return_path_audit/test_epru_adapter.py`（合成结构，CI 可跑；真实工程数据不入仓库） |

**本项目数据只在本机只读解析，不提交到仓库**（用户工程 IP）。结论边界同 §7：这是参考
路径几何/拓扑审查；不替代 DRC、SI/EMI、阻抗或制造验收；换层与单位识别是显式声明的推断。


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
| 真实 **2 层** 工程快照回放 | **DONE**（§5.1，真实 `easyeda pcb dump`，非合成） |
| 真实 **4 层** 工程快照回放 | **DONE（操作型，§5.2）**：本机真实四层 `.epru` 备份只读回放；数据不入仓库。仓库内无真实四层快照 |
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
