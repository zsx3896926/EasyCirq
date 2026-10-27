# G0–G6 门禁复核：`zhigou-integrated-dual-button-led-20261027`

> 按 `design-hardware` 1.0.2 的 [阶段门禁](../references/design-gates.md) 执行，离线复核工具
> `scripts/gate_check.py`（只读证据，不连 daemon、不写工程）。
> 复核时间：2026-10-28；工程：两路按键点亮两路 LED 的 5V 小板（9 器件 / 7 网 / 两层板）。
> 状态文件：`evidence/gates/design-state.json`；完整报告：`evidence/gates/gate-report.json`。

## 1. 结论

| 门禁 | 结论 | 阻塞/豁免项 |
|---|---|---|
| G0 需求 | **PASS** | warn: req_size_limit, req_environment_accuracy |
| G1 功能冻结 | **PASS** | — |
| G2 原理图 | **PASS** | — |
| G3 布局 | **PASS** | — |
| G4 电源地 | **PASS_WITH_WAIVER** | waived: pcb_check_power |
| G5 布线 | **PASS** | — |
| G6 制造 | **BLOCKED** | fail: gerber_files, drill_files, cpl_files, manufacturing_profile, sourcing_check, test_plan |

**总结：5 PASS / 1 PASS_WITH_WAIVER /
1 BLOCKED / 0 UNSUPPORTED（gate_check 退出码 1）。**

因此本板的交付级别是 **PCB 候选（PCB DRC 0）**：原理图/布局/电源地/布线四个阶段门禁有证据通过，
**G6 制造交付未通过**，不得宣称"可打样/可下单"。

## 2. 复核时为达标所做的真实改动

复核不是"把已有证据念一遍"，过程中发现并修掉了两个真实的图面问题：

| 问题 | 处理 | 结果 |
|---|---|---|
| `sch check` 报 2 条 `out-of-sheet`：图签 Name/Description 可见但渲染到纸外 | `sch titleblock --data` 把两者可见性关掉（值保留） | out-of-sheet 0 |
| `sch check` 报 `missing-partition`：9 器件页没有功能分区框 | `sch zones set --module POWER/CH1/CH2` → `sch zone-draw`，画出 3 个分区框并保存 | missing-partition 0 |

复核后 `sch check` **0 finding**、`sch drc` **0 违规**；随后 save → `doc reload` → `sch read` 回读：
20 图元 / 7 网 / 0 浮空引脚，网络成员与改动前一致（分区框是注记图形，不产生连接）。

## 3. 各门禁证据

| 门禁 | 关键证据 | 说明 |
|---|---|---|
| G0 需求边界 | `design-state.requirements`（12 字段） | 2 条为显式假设（尺寸上限/环境精度），其余 confirmed 或 not_applicable+理由；无 blocking open item |
| G1 功能冻结 | `function_freeze`：9 件 required，frozen | 冻结后无增删（本地改板只移动器件，未改 BOM） |
| G2 原理图 | `sch-drc.json`(0)、`sch-check.json`(0)、`schematic-page.png`(472 KB)、逐脚回读 | 无原生前/后网表 diff：本版本 `sch netlist --type protel` 返回 `no file`，网表一致性由活体逐脚回读 + PCB DRC 0 证明（已在 state 中写明该限制） |
| G3 布局 | `pcb-layout-lint.json`（score 96，crossings 1，0 overlap）、`pcb-dump.json`(9 件)、`outline` | layout-lint 晚于最终 dump、组件数一致（evidence_freshness 通过） |
| G4 电源地 | `pcb-pours.json`（GND 双层，count=2）、`pcb-vias.json`（0 via）、`pcb-check.json` | **PASS_WITH_WAIVER**：`power-not-poured` 2 条（+5V/VIN 用走线未铺铜）；理由：9–14 mA 级电流由 10 mil 走线承载，DFM 宽度为推荐值；剩余风险已入 `risks` |
| G5 布线 | `pcb-drc-final.json`（passed，0 违规）、6 条 `net-path-*.json`（connected=true）、`pcb-reopen-readback.json` | 7 个关键网均有证明；GND 用双层铺铜（net-path 不覆盖 pours）+ DRC 0；DRC 收敛 4 轮记录在 `drc_rounds` |
| G6 制造 | `BOM.csv`、`zhigou-board.epro2`（sha256 校验 + 恢复演练已验证） | **BLOCKED**，缺口见下 |

## 4. G6 缺口与下一步命令

| 缺项 | 现状 | 解除条件 |
|---|---|---|
| Gerber / 钻孔 / CPL | 本版本 typed 能力 `unsupported`（action catalog 无 gerber/drill/cpl） | 在 EasyEDA GUI 导出 Gerber、钻孔、贴装坐标并落证据；或后续版本提供 typed 导出 |
| 嘉立创工艺档案 | 未建（`manufacturing.profile: pending`） | 按 `assets/manufacturing-profile.md` 记录层数/铜厚/阻焊/表面处理/板厂能力 |
| BOM 厂家字段 | 5 行缺厂家（系统库器件 Manufacturer 为空） | 换为有明确 MPN/厂家的器件，或补全 BOM 字段 |
| 库存/价格 | 未核（`sourcing.stock_checked_at` 空） | 按立创商城实时核对 C 号、库存、价格、MOQ，并记录查询时间 |
| 实物测试计划 | 未写（`manufacturing.test_plan: pending`） | 编写上电/按键通断/LED 电流/边界与失效测试计划；实物功能仍 `NOT RUN` |

## 5. 复跑方式

```powershell
python "$env:USERPROFILE\.agents\skills\design-hardware\scripts\gate_check.py" `
  --project zhigou-integrated-dual-button-led-20261027 `
  --evidence-dir docs/toolchain-integration/evidence/gates `
  --design-state docs/toolchain-integration/evidence/gates/design-state.json `
  --waiver "G4:pcb_check_power:+5V/VIN 各 2-4 pad，9-14 mA 级电流由 10 mil 走线承载，DFM width 提示为推荐值；剩余风险已记录在 risks" `
  --json --out docs/toolchain-integration/evidence/gates/gate-report.json
```

证据采集命令、哈希与时间戳记录在 `design-state.evidence.manifest`。

## 6. 边界（如实）

- 门禁 `PASS` 只证明列出的检查在给定对象/版本/范围内通过；**不证明实物功能**。实物功能 `NOT RUN`。
- G6 `BLOCKED` 是真实结论，不是遗漏：制造资料确实尚未导出，交付级别不升格。
- 本复核顺带修正了图签显隐与功能分区框两处图面问题；这是设计改进，不是"为了过门禁改证据"。
