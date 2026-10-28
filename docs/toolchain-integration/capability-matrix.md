# 能力矩阵（Capability matrix）

生成方式：`zhigou capabilities`（机器可读 JSON）+ `zhigou actions`（typed action 目录）。
本文件是**M1 实测快照**，不是设计目标；随代码与真机状态更新。

* 生成时间：2026-10-27（M1，自有 daemon 运行、自有连接器尚未导入 EDA）
* 运行时：`zhigou 0.2.0-dev`，源提交 `9a951ed`（工作区有未提交改动，见 `doctor.runtime.vcsModified`）
* 连接器状态：disconnected（0 窗口）→ 因此所有"动作存在"的能力只能是 `unknown`
* 原始证据：`evidence/m1/capabilities.json`、`evidence/m1/actions.json`

状态语义：

| 状态 | 含义 |
| --- | --- |
| `supported` | typed action 存在于本运行时，且连接器已连接。**不**表示该动作在当前宿主必然成功；单次调用仍以新鲜回读为准 |
| `unsupported` | 本运行时没有该能力（动作目录里不存在）。不得用 EDA 版本号推断为可用 |
| `unknown` | 动作存在但无法协商（无连接器），或需真机探测才能判定（官方自动布线/差分/调长） |

## 1. 按能力的协商结果

| 能力 | 状态 | 动作数 | 模式 | 回读动作 | 影响全板 | 原因/限制 |
| --- | --- | ---: | --- | --- | --- | --- |
| `schematic.read` | unknown | 15 | sync-long | 有 | 否 | 动作存在，当前无连接器连接，无法与宿主协商 |
| `schematic.write` | unknown | 26 | sync | 有 | 否 | 同上 |
| `schematic.check` | unknown | 2 | sync-long | 有 | 否 | 原生原理图检查/DRC；长任务，超时后禁止盲重试 |
| `schematic.export` | unknown | 3 | sync | 有 | 否 | 网表/BOM/图像导出 |
| `pcb.read` | unknown | 27 | sync-long | 有 | 否 | 含 dump/几何/铜皮读取；后台页会限制可读性 |
| `pcb.write` | unknown | 58 | sync-long | 有 | 部分 | 器件/走线/过孔/铺铜/丝印原语 |
| `pcb.route` | unknown | 5 | sync-long | 有 | 部分 | 受控原语 + 求解器入口；**官方自动布线器是否存在待真机探测** |
| `pcb.pour` | unknown | 5 | sync-long | 有 | 是 | 重建铺铜会改全板铜；写后必须重建 + 回读 |
| `pcb.drc` | unknown | 3 | sync-long | 有 | 是 | DRC 必须绑定当前快照，旧 DRC 不能证明新修改 |
| `bom.export` | unknown | 1 | sync | 有 | 否 | 导出后仍需检查非空/可解析/匹配当前板版 |
| `image.export` | unknown | 2 | sync | 有 | 否 | 官方整页/局部图；后台标签页可能截不到 |
| `project.read` | unknown | 4 | sync | 有 | 否 | 工程/文档上下文 |
| `project.export` | unknown | 2 | sync | 有 | 否 | 原生工程导出（归档基础） |
| `library.read` | unknown | 8 | sync | 有 | 否 | 库/符号/封装读取 |
| `library.write` | unknown | 14 | sync | 有 | 否 | 库写入需身份核验 |
| `board.binding` | unknown | 10 | sync | 有 | 否 | 原理图↔PCB 绑定 |
| `document.control` | unknown | 9 | sync | 有 | 否 | 打开/切换/保存/重载文档 |
| `save.reload` | unknown | 3 | sync | 有 | 否 | save 返回成功 ≠ 已持久化；必须重开回读 |
| `gerber.export` | **unsupported** | 0 | — | 否 | — | typed action 目录中不存在；只能官方 GUI 导出 + 人工证据 |
| `drill.export` | **unsupported** | 0 | — | 否 | — | 同上 |
| `cpl.export` | **unsupported** | 0 | — | 否 | — | 同上（贴装坐标） |
| `archive.backup` | **unsupported** | 0 | — | 否 | — | 没有 backup/archive 动作；原生归档走 `project.export` + 人工恢复演练 |
| `diffpair.routing` | unknown | 3 | sync | 有 | 部分 | 存在 `pcb.differential_pair.*` 管理动作，但"官方差分布线"能力需真机探测 |
| `length.tuning` | **unsupported** | 0 | — | 否 | — | 无等长/调长动作；只能做离线建议，不得宣称已布线 |

汇总（`capabilities.summary`）：`supported 0 / unknown 19 / unsupported 5`（无连接器时的真实值）。

## 2. typed action 目录（181 个动作 / 111 个写动作）

| domain | 动作数 |
| --- | ---: |
| `pcb` | 85 |
| `schematic` | 41 |
| `library` | 22 |
| `board` | 10 |
| `document` | 9 |
| `project` | 7 |
| `system` | 3 |
| `artifact` | 3 |
| `debug` | 1 |

关键动作（用于验收脚本与 Skill 门禁）：

* 保存/重载：`schematic.save`、`pcb.save`、`system.page_reload`
* 检查：`schematic.drc.check`、`pcb.drc.check`、`pcb.drc.rules`
* 导出：`schematic.export.netlist|bom|image`、`pcb.snapshot`、`pcb.export.3d|dsn`、`project.export|export_source`
* 局部修改原语：`pcb.*.modify/delete/create`、`schematic.component/modify/delete`、`schematic.wire.*`

## 3. 验收状态（实现 / 离线 / 真机 / 客户端 / 证据 / 限制）

| 能力 | 实现 | 离线测试 | 真机测试 | 客户端测试 | 证据 | 限制 |
| --- | --- | --- | --- | --- | --- | --- |
| 自有构建（runtime） | PASS | PASS（`go build`+新建单测） | NOT RUN | NOT RUN | `evidence/m1/doctor.json`、`evidence/runtime-go-test.log` | 全量 Go 测试见测试记录 |
| 自有 daemon 隔离启动 | PASS | PASS | PASS（本机 23111） | NOT RUN | `evidence/m1/listening-ports.json`、`doctor.json` | 仅 loopback |
| doctor / capabilities / connector 子命令 | PASS | PASS（单测） | PASS（无连接器路径） | NOT RUN | `evidence/m1/doctor.json`、`capabilities.json` | 连接器分支需真机 |
| 连接器构建（.eext） | PASS | PASS（包结构校验） | **BLOCKED**（需 EDA 内人工导入扩展） | NOT RUN | `evidence/m1/connector-path.json` | 导入是人工动作，见架构 §7 |
| 原理图→PCB→检查→保存重开 | PASS（代码在） | 部分（上游回归） | **BLOCKED** | NOT RUN | 待真机 | 依赖连接器握手 |
| BOM/图像导出 | PASS（代码在） | 无 | **BLOCKED** | NOT RUN | 待真机 | 依赖连接器握手 |
| 原生归档+恢复演练 | 部分 | 无 | **NOT RUN** | NOT RUN | 待真机 | `project.export` 可用，恢复演练需真机 |
| Gerber/钻孔/CPL | **未实现** | — | — | — | — | typed action 不存在；GUI 导出后需人工证据 |
| 安装/升级/回退 | 进行中 | 进行中 | 进行中 | — | `evidence/installer/` | 由 `distribution/` 负责 |

> 本表中 `BLOCKED` 一律代表"环境动作待用户完成（在 EasyEDA 内导入自有扩展）"，
> 不是"代码未写"；`NOT RUN` 代表尚未执行，不当作通过。

## 4. 运行时回归说明（Lead 补记）

`docs/toolchain-integration/evidence/runtime-go-test.log` 显示 `internal/app`、
`internal/daemon`、`internal/selfupdate` 三个包 `go test` 退出码为 1。与**未修改的上游
v1.15.0** 在同一台 Windows 机器上的基线（`evidence/upstream-v1.15.0-go-test.log`）对比：

* 失败用例：上游 41 个 → 本仓库 40 个；**新增失败 0 个**（逐用例差异见
  `evidence/test-failure-diff.txt`）。
* 剩余失败均为上游既有的 Windows 环境类失败（符号链接/路径别名权限、exec 位、
  原子 rename 权限等），不代表 EDA 执行链不可用，也不应被报告为"测试全绿"。
* `go build ./...`、新增 `doctor`/`capabilities`/`connector` 单测、`internal/blocks`
  等包均通过。

因此本表"离线测试"列的 PASS 指：构建成功 + 该能力对应的新增/既有单测通过；
`FAIL` 仅用于能力缺失（Gerber/钻孔/CPL/等长调长没有 typed action）。
