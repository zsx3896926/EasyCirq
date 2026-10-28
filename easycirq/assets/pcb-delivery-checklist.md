# PCB 交付检查清单（可复用）

用途：把一次真实 PCB 任务从“图画完了”推进到“证据可复核、边界写清楚”。本清单不替代 DRC、原厂资料、实物测试或制造审核；只规定**该收集哪些证据、哪些不能混写**。

## A. 身份与范围

- [ ] 工程名、工程 UUID、PCB UUID、原理图页 UUID 记录在同一份交接里。
- [ ] 本项目只改自己的工程；未改用户既有工程/共享窗口。
- [ ] Skill、zhigou 运行时、Connector、EDA 版本分别记录；不把“Skill 安装成功”当成 EDA 已连通。
- [ ] 板框、层数、铜厚、板厂工艺、器件数量、装配面是冻结输入；变更走显式记录。

## B. 原理图

- [ ] 器件完整型号/库身份/封装/pin-pad 已回读；四脚开关的常通脚组已核对，不是靠猜。
- [ ] 二极管/LED 极性、连接器脚序、NC/连接互斥已核对。
- [ ] `sch check` 0、原生 DRC 0、`bridge-check` 0；网表与设计意图逐脚一致。
- [ ] 官方整页 SVG/PNG + 必要局部图已实际查看；文字遮挡、竖排 flag、倒置接地、重复网名已修。
- [ ] 文字审计覆盖缺口如实记录；strict 布局若缺 `order`/`purpose` 元数据，写 **“电气检查通过、布局检查不完整”**，不写“原理图全面验收通过”。
- [ ] save→reopen→fresh read 已做；若 reload 就绪回执假失败，保留回执并用 `doc ready` + fresh read 证明持久化，明确哪一层通过。

## C. PCB

- [ ] `pcb dump --include-copper` 的组件/板框/铜 availability 逐类 available；不拿 bbox 或空数组补签。
- [ ] 约束：接口边、固定件、安装孔/螺丝头 keepout、通道顺序、near-pin 已编译；hard 失败 0、hard unmeasured 0。
- [ ] 落位前 `pcb-check-plan` / `pcb_preflight` 已跑；`review`/`blocked` 不当 PASS。
- [ ] 实际写入走 typed 操作或 `pcb_apply_plan` 批量路径；写入后 fresh dump + scoped diff，unrelated 0。
- [ ] 布线：关键网 net-path 全 connected（记录配对与是否含 via）；GND/电源铺铜另用 DRC + `poured-list` + 实际铜层图核对，不用 net-path 代替铺铜连通。
- [ ] 铺铜：真实 rebuild；检查孤岛、细颈、热焊盘、边界材料化铜；全局铺铜变化与器件移动分列。
- [ ] 丝印：位号/极性/接口方向/5V/GND/功能名清楚；不压焊盘、不越板框、不上下颠倒。
- [ ] 原生 DRC 0；`pcb check` ERROR 0，WARN 逐条处置（规则、适用性、计算或证据），不把 WARN 静默清零。
- [ ] `pcb layout-lint` coverage complete，score/crossings/overlap/off-board 达标。
- [ ] SCH↔PCB 组件/封装/pad-net 一致；保存→重开→fresh dump 的 identity/geometry/copper/unrelated 均为 0（编辑模式按 scope 解释）。
- [ ] `pcb_gate --profile full` 8/8 pass；缺证据只能 blocked/not_run，不能写 pass。
- [ ] `pcb_case` manifest `complete`，且 gate 报告绑定同一工程、同一最终 dump、同一 check 哈希。

## D. 局部改板

- [ ] 改板前用 `check_move_clearance.py` 或等价工具检查目标位姿：本体/板边/keepout 不冲突。
- [ ] 预留空间不是事后挪其他器件来“补”：若基线本身不够，先记录负例，重排基线，再重做改板测试。
- [ ] 只重布受影响网络/对象；无关器件/板框/接口/安装孔不动。
- [ ] 前后差异：`geometry_changes` 只在目标件；`unrelated_changes=[]`；铺铜重算变化单列。
- [ ] 改板后重跑 DRC、check、关键 net-path、save/reload、gate/case。
- [ ] 保留首次失败输入作为负例（应被拒绝），不把返工过程从报告里删掉。

## E. 交付物

- [ ] 原生 `.epro2`（zip 完整性验证；恢复演练未做就写未做）。
- [ ] 原理图 PNG/SVG；PCB 顶层/底层官方图 + actual SVG。
- [ ] BOM：位号、数量、值、封装、MPN、C 号；库存/价格/MOQ/SMT 未实时核对就写未核对。
- [ ] 电气核算：输入范围、压降、LED 电流/电阻功耗、总电流、铜宽假设；不把极小理论值当唯一接受依据。
- [ ] 验证摘要：原理图、PCB、SCH↔PCB、save/reload、gate、case 分开列。
- [ ] 限制：Gerber/CPL、打样/焊接/上电、热/EMC/机械、库存，逐项 `NOT RUN`/`BLOCKED`；不写“实物功能已验证”。

## F. 报告口径

- [ ] **工具/算法改进**与**本工程通过**分开写；一次案例通过不外推为整体能力成熟。
- [ ] 机械/工具修复写明：失败输入→原因→修改→原失败复测→必要回归。
- [ ] 没有受控基线时不宣称效率提升；没有实物测量时不宣称电气/热/EMC 性能。
