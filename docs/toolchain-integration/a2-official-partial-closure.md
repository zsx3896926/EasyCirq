# 官方 lceda-pro CLI/MCP 四个 partial 工作流的关闭判定（S2）

- 生成：2026-10-28
- 依据：spike #75 的实测回执（`docs/parallel-a2-coverage/coverage-matrix.md` + `docs/evidence/a2-coverage-2026-10-28/`）与已实现的 workaround。
- 结论：W02/W06/W07 可判 **covered-with-workaround**；**W03 仍 partial**（完整几何 dump + 单位/锚点约定未实测，是唯一需要一次新探针才能关的项）。

## 判定表

| ID | 工作流 | #75 判 partial 的原因 | 关闭判定 | 依据 / 残留 caveat |
|---|---|---|---|---|
| W02 | 原理图读 | `sch_Net.getAllNets()` 在该 fixture 返回空 | **covered-with-workaround** | 网表缺口由「导出 Protel 网表 + 解析」补齐，Skill 的 `netlist_diff.py` 已在做；残留：官方无 typed net read，靠网表文本解析 |
| W06 | 批处理/计划应用 | 无 typed batch/事务；超时状态未知 | **covered-with-workaround** | 官方实测「一个 JS 程序内做 10 次读 ≈ 10× 便宜」；残留：CLI 层无事务/idempotency，调用方自行写 journal + 读回校验 |
| W07 | 检查/DRC/DFM | DRC 有返回值形状不符文档；无 DFM | **covered**（DRC）/ DFM 移出官方范围 | 官方 `sch_Drc.check`/`pcb_Drc.check` 实测返回结构化数组（含 warning/error 树）；DFM 属 A 侧 `pcb check` 能力，不计入官方对等 |
| W03 | PCB 读 | 只读到 counts/layers，未 dump outline/copper 几何；单位/锚点未实测 | **partial（仍待补）** | 需一次几何 dump（`pcb_*` copper/outline API）+ 一个单位/锚点（mil, y-up, anchor vs bbox）unit test；这是四个里唯一未关的 |

## 为什么 W03 是唯一没关的

- W02/W06/W07 的“partial”本质是**语义缺口 + 已实现的 workaround**，判定即可关闭，不需要再跑新探针。
- W03 的“partial”是**几何完整性未证**：官方侧只验证了「能读到 counts/layers」，没有 dump 出 copper 线段/弧/填充/板框的完整几何，也没测单位与锚点约定。要把它从 partial 转 covered，必须跑一次真实的几何 dump 并写一个单位约定 unit test。

## 新探针为何本轮未重跑（诚实记录）

- 官方 CLI 已确认可用：`lceda-pro.exe`（JLCEDA Pro 4.1.78.34f5b8d9，222 MB）`--help`/`doctor` 正常。
- 但官方 `invoke -> eda.*` 需要在 `open --path <disposable>.eprj2 --headless` 的一次性副本上跑；本机 EasyEDA Pro 工程存在其内部数据库（`LCEDA-Pro/database`），工作目录下没有可直接复制的 `.eprj2` 文件，本轮未能构造一次性副本，故未重跑几何 dump。
- 补 W03 的可行路径：用 A 的 `project export`/`export-source` 取一份 `.epro2/.eprj2` 工程存档 → 官方 `open --path <copy> --headless` → `invoke` dump 几何 → 写单位约定 unit test。

## 对 S2「0 空档」的净影响

- 官方侧：W02/W06/W07 已关闭判定（covered-with-workaround/covered），仅剩 **W03 几何 dump + 单位约定** 一项。
- A 侧（先前已定位）：W08 制造导出缺失、W11 无 MCP（架构事实，不计入对等）。
- 即：S2 还差 **W03（官方侧几何）+ W08（A 侧制造导出定性）** 两项，其余可视为 0 空档。

## 边界 / NOT RUN

- 本轮未重跑官方探针（无一次性工程副本）；判定基于 #75 的已测回执与已实现 workaround。
- 未做：W03 几何 dump、真实工程端到端、制造导出实跑、硬件实测。
