# 真实案例：5V 光控 LED 板 PCB（2026-10-26）

> 状态：**进行中**。已完成独立 PCB 副本、器件导入、板框/安装孔、19 器件布局、VREF 关键网官方布线与回读；其余网络/铺铜/丝印/DRC/保存重开/导图仍待完成。不得把当前状态写成可制造或已验收。

## 1. 工程身份

| 项 | 值 |
|---|---|
| 原理图源工程 | `photo-led-5v-20261026`，UUID `e4a2b5aced774684bdd455c9f7a9059d`（**未修改**） |
| PCB 测试副本 | `photo-led-pcb-20261026`，UUID `e56848aaf64d49d7a465352291670aef` |
| 原理图 | `5V 光控 LED 板`，`5ff4d6e7c85dd153`，页 `P1` / `cd008f919db36eba` |
| PCB | `PCB1`，UUID `99b8366b0bdc971f` |
| 源归档 | `photo-led-source-20261026.epro2`，202,482 B，SHA-256 `7180c63e22d011506a74d33f0d14f0850b940cf3b3cb91f3f2ce39fcfad09258` |
| 布局检查点 | `photo-led-placed-checkpoint.epro2`，212,883 B，SHA-256 `dbe3fdd982afce1b22a5dfa217a0fe5d17e6fa087a1cb211d834c637ccb3c018` |
| EDA / 执行器 | EasyEDA Pro 4.1.78；easyeda-agent 1.15.0；Connector 1.15.0 |
| 窗口 | `5175351c-a00b-4788-a922-2f6e0bd80756`（用户 GUI 全在线会话） |

## 2. 本轮做了什么

1. 从已核实的原理图导出 `.epro2`，导入为独立副本；原工程未改。
2. `pcb import-changes` 导入 19 器件 / 47 焊盘；save → reload 后回读。
3. 板框：90×60 mm 圆角矩形（3543.3×2362.2 mil，r=100 mil）。
4. 4 个 M3 安装孔：`pcb mount-holes --inset 200 --dia 126`，垫圈禁布半径 118 mil。
5. 布局：先把实测 dump 传到离线工具，生成/校验 placements；再逐件 `pcb modify`（x/y/rotation/layer）写入并回读。
6. 布局检查：`layout-lint` 80/moderate，19 件、47 焊盘、0 overlap/0 off-board/0 short、5 crossings。
7. 连接器：J1 初始 rotation 90 被 `pcb check` 判 `connector-opening-inward` 且 D1 落在插拔走廊；改为 270 后两项清零。
8. 关键网 VREF_2V5：官方路由器 `autoroute --layers 1,2 --net VREF_2V5`，created 12 tracks / 0 vias；save → reload；`net-path U2.3→R1.1` 等已 connected（底层、10 mil、0 via）。

## 3. 已记录的真实问题

| 问题 | 证据 | 处置 |
|---|---|---|
| U1.8 去耦 C2 实测 150 mil，CLI 规则 WARN 阈值 100 mil | `pcb check` `decap-too-far` | C2 本体 482×207 mil，U1 DIP-8 本体 402×372 mil；在不相撞前提下 150 mil 是当前最近位置。保留 WARN 并记录，不用改封装/移 U1 来“清警告”。 |
| J1 rotation 90 开口朝内 | `pcb check` `connector-opening-inward`、`connector-mating-blocked` | 改 270，两项清零。 |
| VREF 参考网底层 10 mil、12 段 | `track-list`、`net-path` | 关键网先布、0 过孔；<1 mA，10 mil 有计算依据；布后逐段验证。 |
| 其他信号/电源尚未布 | `energy`/`track-list` | 待续；不得宣称布通。 |
| 铺铜/丝印/DRC/保存重开/制造图未完成 | — | 待续；不得宣称可制造。 |

## 4. 离线证据

| 文件 | 说明 |
|---|---|
| `evidence/pcb-dump-placed.json` | 布局写入并 reload 后的真实 `pcb dump --include-copper`（19 件/47 焊盘；铜仅 VREF 前的基线） |
| `evidence/pcb-intent.json` | 约束（fixed/edge/near_pin/keepout/allowed_rotation/group）+ 4 个模板模块绑定 + 电源声明 |
| `evidence/constraints.json` | `pcb-constraints` 编译结果（compiled；1 条 edge+fixed 需姿态复核） |
| `evidence/placement-plan.json` | 19 件目标 anchor/rotation/layer 与理由 |
| `evidence/candidates.json` | `pcb-candidates` 三策略；signal-chain 与 mechanical 同分（所有模块均有显式目标），按策略序选 signal-chain |
| `evidence/placement-check.json` | `pcb-check-plan`：hard_ok=true、0 hard findings；near_pin 均 pass |
| `evidence/escapes.json` | `pcb-escapes` 代理预判（含 4 个 M3 keepout）；不是布线证明 |
| `evidence/power-check.json` | `pcb-power`：+5V/VIN/GND 声明铺铜但尚未铺 → fail；VREF_2V5 声明 track 但只有部分铜 → unmeasured；C2/C3/C1 去耦/体电容中心距 pass |
| `evidence/module-U1-C2-R4.json` + `module-binding.json` | `pcb-extract-module` 相对布局契约；`pcb-reuse-plan` 在同一板平移/旋转复用的离线验证；铜复用 `not_supported` |
| `evidence/fabrication-check.json` | `pcb-fabrication`：60 条丝印对象（19 可见），dump BBox 报 2 条侧向；**CLI `pcb check` 用实时渲染字框报 8 条 silkscreen-flipped + U1 silk-over-pad**。差异已记录，最终以实际导图/`silk-align` 后回读为准。 |
| `evidence/pcb-placed-actual.svg` | `pcb layout render --actual` 离线实际几何（顶/底辅助视图，不是官方 EDA 截图）；用于布线前空间核对 |

复现：

```bash
cd design-hardware/scripts
python -m design_engine pcb-constraints --dump ../../design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-placed.json --intent ../../design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-intent.json --json
python -m design_engine pcb-check-plan --dump ../../design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-placed.json --plan ../../design-hardware/cases/photo-led-pcb-2026-10-26/evidence/placement-plan.json --constraints ../../design-hardware/cases/photo-led-pcb-2026-10-26/evidence/constraints.json --json
python -m design_engine pcb-candidates --dump ../../design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-placed.json --intent ../../design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-intent.json --json
```

## 4.1 基线/首候选/返工记录（事实，不含宣传性百分比）

| 项 | 事实 |
|---|---|
| 导入后原始排布 | 19 件自动排成一行，x 约 234–5553 mil，y 约 −2265…−200 mil；在 90×60mm 板框外，不能直接布线 |
| 新流程首个候选 | signal-chain：19 件全部落位，离线 `hard_ok=true`，0 重叠/0 越框；layout-lint 80/moderate，5 crossings |
| 其他候选 | density 硬失败（越框/近引脚失败）；mechanical 与 signal-chain 同分（模块均有显式目标），按策略序选 signal-chain |
| 布局返工 | 离线检查先发现 C1/D1 与 R1/R5 重叠、R4 近引脚 516 mil；调整坐标后 0 发现，再写入 EDA；写入后 J1 rotation 90→270 修复接口朝向，共 2 次布局迭代 |
| 布线首轮 | VREF_2V5 官方路由器 12 段/0 过孔；尚未布其余网，不能计算“布通率” |
| 重复失败机制 | 未出现同一机制连续失败两次；没有用缩小板框/降间距/移固定接口换分数 |
| 路由器对比（仅 VREF，同板/同规则/同网络） | `route-short --dry-run`：VREF 14 段 / 3066.9 mil（全板计划 49 段/14 过孔）；官方 `autoroute --net VREF_2V5 --layers 1,2`：12 tracks / 2946 mil / 0 过孔。选择官方路由器，未执行 route-short。该比较不证明整板可布性或布通率。 |

## 5. 必须由后续证据补齐

1. 其余信号布线与电源/地铺铜；`pcb check`/`pcb drc` 清零或逐条解释。
2. 关键局部连接逐条 `net-path`（去耦、输入保护、驱动、反馈）；有铺铜的网络标明未证明范围。
3. 丝印位号/极性/接口方向；实际顶层/底层图（官方导出或 stage snapshot）。
4. save → `doc reload` → fresh dump → `pcb-diff`（scope 全板）一致。
5. 原生 DRC 全量结果、剩余 WARN、制造资料导出/离线核对（未做标 `BLOCKED`）。
6. 与本案例对应的 Skill 工具/回归测试与 handoff。
