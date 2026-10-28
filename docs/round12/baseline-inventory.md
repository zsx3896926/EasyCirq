# Round 12 基线盘点（2026-10-27）

> 本文件记录开工时仓库与真实宿主的事实，不用旧交接的版本/PR 代替现场。
> 真实 EDA 只做了只读探测与被中断前的一次工程副本导入；随后按用户要求停止
> 真机操作，改做离线验收。所有未执行的写/DRC/保存重开都标 `NOT RUN`。

## 1. 仓库与工作树

| 项 | 现场值 |
|---|---|
| 仓库 | `C:/Users/jlc/work/EasyCirq`（主工作树） |
| 本轮 worktree | `C:/Users/jlc/work/hds-feedback-r12` |
| 分支 | `feat/feedback-loop-round12` |
| 基线 HEAD | `82474b0`（PR #24 `feat/offline-toolchain-round11` 头部） |
| 远端 | `https://github.com/zsx3896926/EasyCirq` |
| 其他未合并 PR | #24（离线证据/门禁）、#23（gate check 角色） |
| Skill 版本 | `0.9.3`（`design-hardware/.version`） |
| 已安装客户端 | 仍 0.9.2（本轮不替换用户安装版、不发 Release） |

主工作树有另一个会话的未跟踪文件（`design-hardware/assets/decisions/` 等），
本轮未触碰；本轮全部改动在隔离 worktree 内。

## 2. 真实宿主探测（只读 / 被中断）

| 项 | 实测 |
|---|---|
| easyeda CLI | `v1.15.0` |
| daemon | `v1.15.0`，端口 `60832` |
| Connector | `1.15.0` |
| EasyEDA Pro | `4.1.78` |
| 窗口 | `5175351c-a00b-4788-a922-2f6e0bd80756`（用户 GUI 会话，连接器只挂在该窗口） |
| 能力声明 | `schematic.v1`、`pcb.v1` |
| typed action catalog | 181 个动作，111 个可变更；pcb 85 / schematic 41 / library 22 / board 10 / document 9 / project 7 / system 3 |
| 观察到的真实故障 | `--project` 路由在切换工程后返回旧工程文档（`doc ls --project` 给出旧 PCB1/P1）；`sch save` 未带 `--doc` 时警告上下文不匹配且实际保存了 PCB；daemon autosave 历史有多条 `PRECONDITION_REFUSED: active project/document context ... differs from expectedContext` |

结论：真实宿主可用，但**工程/文档身份必须用 `--window` + 明确文档 UUID 并在
响应里核对 `context`**；`--project` 名称路由不能作为写入目标依据。这条已写入
观察契约与离线测试。

## 3. A1 能力清单（实际探测）

| 能力 | 状态 | 接口 / 实测 | 限制 |
|---|---|---|---|
| 工程/文档识别 | available | `project info`、`doc ls`、`project find` | `project find` 当前会话返回 `enumeration.complete=false`（`empty_uuid_list`），缺席只能记 unknown |
| 原理图对象/网络读取 | available | `sch read`（实测 37 器件/12 网；副本工程返回 52 器件/13 网） | 非活动页返回浅数据；需 `--page`/`--doc` |
| PCB 对象/焊盘读取 | available | `pcb list`、`pcb dump` | 空板与读失败需由 `coverage/availability` 区分 |
| PCB 几何/铜读取 | available | `pcb dump --include-copper`（实测 19 器件/67 线/0 过孔/2 铺铜；副本 104 器件） | 板框需要 PCB 前台；否则 `partial[]` |
| 移动/旋转 | available（未实写） | `pcb modify`、`sch modify`、`sch group-move` | 本轮真机写 `NOT RUN` |
| 布线/过孔 | available（未实写） | `pcb track`、`pcb via`、`pcb autoroute`、`pcb rip-up` | 本轮真机写 `NOT RUN` |
| 锁定 | available（未实写） | `pcb lock`（读取回读验证） | 本轮真机写 `NOT RUN` |
| ERC/DRC | available | `sch drc --json`、`pcb drc --json`（旧工程实测 passed=true total=0） | 必须前台；超时不要循环重试 |
| 保存 | available | `sch save`/`pcb save`（实测 saved=true） | 文档身份错位时会拒绝（autosave 历史有实例） |
| 重新打开 | available（未实测） | `doc reload` | 本轮 `NOT RUN` |
| 截图/导出 | available（未实测） | `pcb snapshot`、`sch export-image`、`project export(-source)` | 本轮 `NOT RUN`；导图不是对象级几何证明 |
| 撤销/恢复 | unknown | CLI 无公开 undo；`easyeda apply --resume` + journal 可用 | 宿主不保证原子事务；恢复只能靠检查点/幂等 |

## 4. 现有工具盘点（复用 / 需修 / 缺失）

| 领域 | 可复用 | 需修 / 缺口 |
|---|---|---|
| 观察 | `pcb_cli.run`（统一 runner/JSON/超时）、`eda_cache.py`、`design_inventory.py`、`pcb dump`、`sch read` | 无统一观察契约；无响应 context 强制核对；缓存键未含文档修订；空/未知未统一 |
| 闭环状态 | `design_engine/state.py`（S0–S5）、`pcb_apply_plan` journal | 状态机没有 apply/readback/verify/repair/blocked；无预算、连续无改善、停止条件执行 |
| 局部修改 | `pcb_apply_plan.py`（一次 apply、dry-run、journal、no-op）、`diff_boards` scope | 写前不校验目标文档；scope 不限制写入（写后才归因）；无原理图写入执行器；无写后逐期望变化校验 |
| 差异/不变量 | `pcb_workflow.diff_boards`、`design_engine/compare.py` | 不比 holes/keepout/locked/未布状态/rules 值；无容差；原理图前后连接未接入 |
| 质量评价 | `gate_check.py` G0–G6、`pcb_gate.py` PG1–PG8、`pcb check`、`sch_layout_check/quality` | 无统一三层仲裁；DRC 0 不吸收工程质量；readability 未入门禁；无候选“更整齐但更差”拒绝 |
| 案例 | `design-hardware/cases/` 三个项目案例、`pcb_case.py` | 无案例索引/检索/适用性检查；验证层级不结构化；无复用复核 |
| 路由 | `SKILL.md` 意图表、references | 无“画板”入口；无“这里改一下”/“参考以前方案”路由；无反馈闭环命令入口 |
| 回归 | `tools/offline_suite.py`、`offline_benchmark.py`、`offline_guard.py`、1237 tests | 无本轮闭环/越界/并发/恢复/案例检索的离线基准 |

## 5. 本轮交付策略

- 新增 `design-hardware/scripts/feedback/` 契约层与 `feedback_loop.py` 单一入口，
  复用 `pcb_cli.run`、`pcb_apply_plan.py`、`design_engine` 几何/差异、`pcb check`；
- 不修改 `pcb_apply_plan.py` 的既有契约，闭环在其外层做写前目标/范围/基线拒绝；
- 真机只保留已完成的只读探测；所有写入、保存重开、DRC 复验标 `BLOCKED/NOT RUN`；
- 离线验收用注入 fake runner/假 CLI，全部输出标 `simulated`，不冒充宿主保存；
- 至少 3 个案例（原理图可读性、电源/去耦局部、接口锁定局部），验证层级只写
  实际做过的 `structural`，其余 `not_run`。
