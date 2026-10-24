# A02：能力发现与上游版本对齐

日期：2026-10-24。目标：确认“读什么、写什么、哪些只是存在但不能用”，并选定主执行入口。

## 1. 已实测的版本与连接

| 项 | 实测结果 | 证据 |
|---|---|---|
| easyeda-agent CLI | `easyeda-agent v1.14.0` | `easyeda version` |
| daemon | 60832 端口，`v1.14.0`，`status: ok` | `easyeda health` |
| Connector | `1.14.0` | `easyeda health` |
| 宿主 EasyEDA Pro | `4.1.78` | `easyeda health` |
| 当前窗口工程 | `temp-alarm-r7-scratch`，schematic `6a8364999a809cb4` | `easyeda health` |
| 官方 CLI 适配器 | `eda_exec.py` 已验证客户端前缀 `4.1.78` | 源码常量与既有测试 |

注意：`easyeda health` 当时显示另一个会话正在同一页工作。本轮**没有**对同一页发起写入；所有几何来自冻结 bundle，版本探测只读。

## 2. 只读能力（本轮实际使用或冻结证据）

| 能力 | 命令 | 输出 | 本轮用法 |
|---|---|---|---|
| 器件/属性/导线 | `easyeda sch list --include-pads` | `components[].bbox/x/y/rotation/mirror/pins`、`pagePrimitives.attributes`、`wires` | 构建 IR；26 个器件本体、96 个布局属性、65 段导线 |
| 连接 | `easyeda sch connectivity` | `components/nets/connections` | 14 网、65 连接；逐脚对账 |
| 位号几何 | `easyeda sch designator-geometry` | 26 个原生 bbox | 精确位号边界 |
| 独立文字 | `easyeda sch text-list` | 本页 `count: 0` | 证明文字不是独立 primitives |
| 导图 | `easyeda sch export-image --format svg` | 203 个 `<text>` 锚点 | 字号/字体/旋转/锚点；不把轮廓当可编辑图元 |
| 图签/图幅 | `easyeda sch titleblock-get`、`sheet-geometry` | 图签字段、页框、keepout | 越界/压图签检查 |
| 原理图检查 | `sch check`、`sch drc`、`sch layout-lint`、`sch layout-score`、`sch gate` | 文本/JSON 摘要 | 与引擎独立结果对照，不当几何 |
| 诊断分组 | `sch clusters` | L1 组 bbox | 只作候选分组，不当功能区 |
| PCB 回读 | `pcb snapshot/dump`、`pcb drc`、`pcb check`、`pcb layout-lint` | 板框/器件/焊盘/铜/DRC/DFM | PCB IR 与独立审计 |

## 3. 写入能力与限制

| 能力 | 可用入口 | 限制 | 本轮状态 |
|---|---|---|---|
| 移动器件/创建导线/改文字 | `eda_exec.py apply`（官方 CLI 固定动作） | 只发固定模板，不执行用户 JS；写入前对账 | 未在本轮真机应用 |
| 移动 Name/Designator | `easyeda sch attribute-move --from move.json` | 只支持 Name/Designator；要求完整原始属性记录与 project/document UUID；x/y 为 Y-up 原始坐标；不接受额外字段 | **已验证**：隔离副本 10 次操作/9 个属性，`moved/verified/preserved=true`；保存重开 match |
| 移动净标签/旗形 | 无独立 API | 锚点属于导线/符号；改坐标会脱离所属对象 | 计划中标记 `unplanned` |
| 改 Value/其它属性 | 无受控单属性入口 | 需要改器件或重建，影响身份 | 不做 |
| PCB 写入/布线 | `eda_exec` PCB 命令族 / easyeda 路由 | 需激活 PCB、串行写入 | 本轮未做 |

## 4. 选定的主链

1. **测量**：以 `easyeda sch list` + `sch connectivity` + `sch designator-geometry` + `sch export-image --format svg` 为同一批次的只读来源；不新增第二个 daemon。
2. **审计/规划**：本仓库 `design_engine`，stdlib-only，离线运行。
3. **应用**：`eda_exec.py`（器件/导线/文字）或 easyeda-agent 的 `sch attribute-move`（Name/Designator）；每次应用前带完整 `expected`，应用后重新回读、重新 audit、重新导图。
4. **最终电气门禁**：`netlist_diff.py` 原生网表 diff；本引擎的 `compare` 只是辅助。

## 5. 本轮新增的离线能力

`design_engine_cli.py` 已实现并测试：IR/覆盖、标签计划与校验、正交路由候选、模块装箱、12 模板、PCB 板框/焊盘/连通/DRC、约束编译、关键回路、布局候选、可布性代理、丝印、CPL/装配视图、制造包、Gerber 层、选型、变体、复用、基准、状态与故障注入。它们全部不访问 EDA；`eda_apply`/`route_rate`/`IHMB compatibility` 等保持 `NOT RUN`/`NOT VERIFIED`。

## 6. 已确认的缺口

- `sch list` 不返回“净标签”图元；净标签实际是导线的 `Name` 属性（`ParentPrimitiveId` 属于导线）。不解析它会把正常导线端误报为悬空。
- 原生 bbox 只对位号提供；其它可见文字需要 SVG 锚点 + 字体度量，来源标记为 `windows_gdi_font_metrics` 或 `font_table_estimate`。
- `sch text-list` 为 0：独立文字图元不存在，不能靠它统计注释。
- `pcb-drc.json` 中间夹了一行 CLI 文本；严格 JSON 解析失败。引擎用“只删除深度>0 的非 JSON 行”的容错解析，并记录被删行。
- 铺铜填充含孤岛/热焊盘；本轮不把 filled polygon 简化成实心平面，GND 连通性标记 `not_checked`。
- `attribute-move` 不支持 Value/参数属性；S04 的“属性联合排布”只能先覆盖 Designator/Name。
- 没有真实人工审图、实物、制造或全在线 GUI 验收；这些保持 `NOT RUN`。
