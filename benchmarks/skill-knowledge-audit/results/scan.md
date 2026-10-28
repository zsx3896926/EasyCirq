# Skill 知识结构扫描索引

- 根目录：`C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-ska-worktree\easycirq`
- 基线：`c9836eb29869040aeac245d0d3959021134b7f3e`
- 工具/目录版本：`0.1.0` / `2026-10-27.1`
- 文件 309，链接 2480，必读链接 67，错误 0，警告 16

> 本结果只证明静态文档结构与引用关系，不证明 Skill 被客户端加载、模型遵守规则、阅读行为改变或硬件设计正确。 本命令不验证外链，也不执行任何脚本。

## 必读闭包（从 SKILL.md 出发）

- `SKILL.md`
- `assets/beginner-summary.md`
- `assets/pcb-delivery-checklist.md`
- `references/agent-collaboration.md`
- `references/beginner-journey.md`
- `references/connectivity.md`
- `references/design-gates.md`
- `references/eda-execution.md`
- `references/evidence.md`
- `references/jlc-handoff.md`
- `references/jlc-production.md`
- `references/network-discipline.md`
- `references/offline-tools.md`
- `references/pcb-execution.md`
- `references/pcb.md`
- `references/schematic-layout-engine.md`
- `references/workflow.md`

## 结构提示

- 必读链最大深度：2
- 孤立资料：7
  - `CHANGELOG.md`
  - `assets/decisions/asset-index.r4p6.example.md`
  - `cases/dual-button-led-night-20261027/negative-direct-move/README.md`
  - `cases/mcu-i2c-s3-2026-10-26/README.md`
  - `cases/photo-led-pcb-2026-10-26/README.md`
  - `references/engineering-deepdives/action-map.md`
  - `references/engineering-deepdives/casebook/index.md`
- 引用环：15
  - `SKILL.md` ↔ `assets/design-brief.md` ↔ `assets/design-calc.md` ↔ `assets/docs/manufacturing-package.md` ↔ `assets/docs/mechanical.md` ↔ `assets/docs/silk-assembly.md` ↔ `assets/docs/thermal-sensor.md` ↔ `assets/docs/verification.md` ↔ `assets/routing-plan.md` ↔ `references/agent-collaboration.md` ↔ `references/analog-rf-highspeed.md` ↔ `references/calculations/README.md` ↔ `references/calculations/analog-adc.md` ↔ `references/calculations/energy-battery.md` ↔ `references/calculations/interconnect.md` ↔ `references/calculations/power-thermal.md` ↔ `references/common-hardware/README.md` ↔ `references/common-hardware/a-environment.md` ↔ `references/common-hardware/applications/01-temperature-alarm.md` ↔ `references/common-hardware/applications/02-fan-control.md` ↔ `references/common-hardware/applications/03-humidity-display.md` ↔ `references/common-hardware/applications/04-door-window-reminder.md` ↔ `references/common-hardware/applications/05-electronic-scale.md` ↔ `references/common-hardware/applications/06-water-level-alarm.md` ↔ `references/common-hardware/applications/07-current-monitor.md` ↔ `references/common-hardware/applications/08-rs485-node.md` ↔ `references/common-hardware/applications/09-timer-control.md` ↔ `references/common-hardware/applications/10-soil-monitor.md` ↔ `references/common-hardware/applications/11-data-logger.md` ↔ `references/common-hardware/applications/12-solenoid-controller.md` ↔ `references/common-hardware/b-optics.md` ↔ `references/common-hardware/c-motion.md` ↔ `references/common-hardware/d-force.md` ↔ `references/common-hardware/e-measurement.md` ↔ `references/common-hardware/h-battery.md` ↔ `references/common-hardware/j-buses.md` ↔ `references/common-hardware/k-drive.md` ↔ `references/common-hardware/l-hmi.md` ↔ `references/common-hardware/m-wireless-time.md` ↔ `references/decisions/README.md` ↔ `references/decisions/cases/README.md` ↔ `references/design-cards/README.md` ↔ `references/design-cards/analog/a01-divider.md` ↔ `references/design-cards/analog/a02-opamp-buffer.md` ↔ `references/design-cards/analog/a03-diff-amp.md` ↔ `references/design-cards/analog/a04-adc-driver.md` ↔ `references/design-cards/analog/a05-vref.md` ↔ `references/design-cards/drive/d01-low-side.md` ↔ `references/design-cards/drive/d02-high-side.md` ↔ `references/design-cards/drive/d03-relay.md` ↔ `references/design-cards/drive/d04-half-bridge.md` ↔ `references/design-cards/drive/d05-h-bridge.md` ↔ `references/design-cards/drive/d06-stepper.md` ↔ `references/design-cards/drive/d07-led-cc.md` ↔ `references/design-cards/drive/d08-heater.md` ↔ `references/design-cards/interfaces/i05-uart.md` ↔ `references/design-cards/interfaces/i06-rs232.md` ↔ `references/design-cards/wireless/w01-wifi-ble.md` ↔ `references/design-cards/wireless/w02-antenna.md` ↔ `references/design-cards/wireless/w03-cellular.md` ↔ `references/design-cards/wireless/w04-gnss.md` ↔ `references/design-cards/wireless/w05-display.md` ↔ `references/design-cards/wireless/w06-classd.md` ↔ `references/design-cards/wireless/w07-spi-flash.md` ↔ `references/design-cards/wireless/w08-microsd.md` ↔ `references/design-experience.md` ↔ `references/design-gates.md` ↔ `references/digital.md` ↔ `references/domain-design-details.md` ↔ `references/domains.md` ↔ `references/eda-execution.md` ↔ `references/engineering-deepdives/README.md` ↔ `references/engineering-deepdives/casebook/audio-analog-precision.md` ↔ `references/engineering-deepdives/casebook/high-speed-rf-fpga.md` ↔ `references/engineering-deepdives/casebook/hmi-connectors-thermal.md` ↔ `references/engineering-deepdives/casebook/motor-power-industrial.md` ↔ `references/engineering-deepdives/exercises/README.md` ↔ `references/engineering-deepdives/sources.md` ↔ `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` ↔ `references/engineering-deepdives/topics/b2-sleep-current-budget.md` ↔ `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` ↔ `references/engineering-deepdives/topics/b4-power-dynamics.md` ↔ `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` ↔ `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` ↔ `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` ↔ `references/engineering-deepdives/topics/c4-measurement-artifacts.md` ↔ `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` ↔ `references/engineering-deepdives/topics/d2-clock-system-checklist.md` ↔ `references/engineering-deepdives/topics/d3-off-board-interfaces.md` ↔ `references/engineering-deepdives/topics/d4-wireless-integration.md` ↔ `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` ↔ `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` ↔ `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` ↔ `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` ↔ `references/examples/README.md` ↔ `references/examples/x01-buck-loop.md` ↔ `references/examples/x02-ldo-thermal.md` ↔ `references/examples/x05-i2c.md` ↔ `references/examples/x09-current-sense.md` ↔ `references/examples/x10-4-20ma.md` ↔ `references/examples/x11-h-bridge.md` ↔ `references/examples/x12-antenna.md` ↔ `references/failures/README.md` ↔ `references/failures/f01-odrive-sense-parasitic.md` ↔ `references/failures/f02-two-aa-ldo.md` ↔ `references/failures/f03-esp32-strap.md` ↔ `references/failures/f04-stm32-vcap.md` ↔ `references/failures/f05-crystal-load-esr.md` ↔ `references/failures/f06-i2c-pullup.md` ↔ `references/failures/f07-rs485-termination.md` ↔ `references/failures/f08-can-termination.md` ↔ `references/failures/f09-usbc-cc.md` ↔ `references/failures/f10-buck-loop-layout.md` ↔ `references/failures/f11-mlcc-bias.md` ↔ `references/failures/f12-inductor-saturation.md` ↔ `references/failures/f13-mosfet-soa.md` ↔ `references/failures/f14-relay-flyback.md` ↔ `references/failures/f15-fpc-pin1.md` ↔ `references/failures/f16-copper-pour-reference.md` ↔ `references/failures/f17-diff-split-reference.md` ↔ `references/failures/f18-antenna-enclosure.md` ↔ `references/failures/f19-bom-cpl-dnp.md` ↔ `references/failures/f20-lcsc-stock-vs-smt.md` ↔ `references/failures/f21-soldered-not-tested.md` ↔ `references/failures/f22-adc-settling.md` ↔ `references/failures/f23-debugger-backpower.md` ↔ `references/failures/f24-nrst-pulled-by-peripheral.md` ↔ `references/failures/f25-radio-tx-resets-system.md` ↔ `references/failures/f26-motor-start-corrupts-adc.md` ↔ `references/failures/f27-usb-ground-loop-source-conflict.md` ↔ `references/failures/f28-i2c-unpowered-device-lockup.md` ↔ `references/failures/f29-spi-write-ok-read-unstable.md` ↔ `references/failures/f30-gpio-power-on-glitch.md` ↔ `references/failures/f31-replacement-passes-typical-fails-corner.md` ↔ `references/failures/f32-enclosure-degrades-rf-and-thermal.md` ↔ `references/failures/f33-measurement-caused-wrong-rework.md` ↔ `references/idea-to-product.md` ↔ `references/jlc-handoff.md` ↔ `references/jlc-pcb-rules.md` ↔ `references/jlc-production.md` ↔ `references/jlc-smt-rules.md` ↔ `references/lcsc-sourcing.md` ↔ `references/manufacturing-details.md` ↔ `references/manufacturing-routes.md` ↔ `references/module-cards.md` ↔ `references/module-integration.md` ↔ `references/offline-regression.md` ↔ `references/offline-tools.md` ↔ `references/part-selection.md` ↔ `references/pcb-execution.md` ↔ `references/pcb-lessons.md` ↔ `references/pcb-placement-details.md` ↔ `references/pcb-routing-details.md` ↔ `references/pcb-routing-strategy.md` ↔ `references/pcb.md` ↔ `references/power.md` ↔ `references/product-example.md` ↔ `references/projects/README.md` ↔ `references/projects/p01-low-power-wireless-sensor.md` ↔ `references/projects/p02-industrial-rs485-analog.md` ↔ `references/projects/p03-low-voltage-power-drive.md` ↔ `references/projects/p04-usb-mcu-board.md` ↔ `references/review.md` ↔ `references/schematic-authoring.md` ↔ `references/schematic-benchmarks.md` ↔ `references/schematic-details.md` ↔ `references/schematic-layout-engine.md` ↔ `references/schematic-layout.md` ↔ `references/schematic-lessons.md` ↔ `references/schematic-recipes.md` ↔ `references/schematic.md` ↔ `references/selection/README.md` ↔ `references/selection/lcsc-verification.md` ↔ `references/selection/modules-connectors.md` ↔ `references/selection/passives.md` ↔ `references/selection/power-ics.md` ↔ `references/selection/replacement-classes.md` ↔ `references/selection/semiconductors.md` ↔ `references/simulation-measurement.md` ↔ `references/source-register.md` ↔ `references/sources.md` ↔ `references/starter-patterns.md` ↔ `references/thermal/topic.md` ↔ `references/tool-gotchas.md`
  - `references/decisions/c01-state-transition-contract.md` ↔ `references/decisions/cases/r4-case-c01-battery-plus-external-supply-states.md` ↔ `references/decisions/cases/r4-case-e01-multiboard-interface-contract.md` ↔ `references/decisions/e01-interface-contract.md`
  - `references/decisions/cases/r4-case-h01-measurement-node-calibration.md` ↔ `references/decisions/h01-calibration-and-identity.md`
  - `references/decisions/cases/r4-case-i01-legacy-product-revision.md` ↔ `references/decisions/i01-change-impact.md`
  - `references/design-cards/interfaces/i01-i2c.md` ↔ `references/design-cards/interfaces/i02-i2c-buffer.md`
  - `references/design-cards/interfaces/i10-usbc-data.md` ↔ `references/examples/x08-usbc.md`
  - `references/design-cards/mcu/m01-bare-mcu.md` ↔ `references/design-cards/mcu/m02-module-mcu.md`
  - `references/design-cards/mcu/m05-crystal.md` ↔ `references/design-cards/mcu/m06-external-clock.md`
  - `references/design-cards/power/p03-boost.md` ↔ `references/design-cards/power/p04-buck-boost.md`
  - `references/design-cards/power/p06-linear-charger.md` ↔ `references/design-cards/power/p07-switching-charger.md`
  - `references/engineering-deepdives/casebook/low-power-wireless-battery.md`
  - `references/engineering-deepdives/casebook/mcu-dev-boards.md`
  - `references/engineering-deepdives/exercises/answers.md`
  - `references/engineering-deepdives/exercises/blind-prompts.md`
  - `references/engineering-deepdives/exercises/exercises.md`
- 重复主题：1
  - duplicate_basename `sources.md`: `references/engineering-deepdives/sources.md`, `references/sources.md`, `references/thermal/sources.md`

## 发现

| id | severity | check | location | target | detail | ignored |
|---|---|---|---|---|---|---|
| F0001 | warning | anchor_prefix_match | `references/common-hardware/README.md:29` | g-power-conversion.md#g1-ldo | anchor matches a heading only by prefix: #g1-ldo |  |
| F0002 | warning | anchor_prefix_match | `references/common-hardware/README.md:29` | g-power-conversion.md#g2-buck | anchor matches a heading only by prefix: #g2-buck |  |
| F0003 | warning | anchor_prefix_match | `references/common-hardware/README.md:29` | g-power-conversion.md#g3-boost | anchor matches a heading only by prefix: #g3-boost |  |
| F0004 | warning | anchor_prefix_match | `references/common-hardware/README.md:29` | g-power-conversion.md#g5-反相电源 | anchor matches a heading only by prefix: #g5-反相电源 |  |
| F0005 | warning | anchor_prefix_match | `references/common-hardware/README.md:29` | g-power-conversion.md#g6-隔离-dcdc | anchor matches a heading only by prefix: #g6-隔离-dcdc |  |
| F0006 | warning | anchor_prefix_match | `references/common-hardware/README.md:35` | g-power-conversion.md#g2-buck | anchor matches a heading only by prefix: #g2-buck |  |
| F0007 | warning | anchor_prefix_match | `references/common-hardware/applications/02-fan-control.md:33` | ../g-power-conversion.md#g2-buck | anchor matches a heading only by prefix: #g2-buck |  |
| F0008 | warning | anchor_compat_match | `references/common-hardware/applications/03-humidity-display.md:27` | ../j-buses.md#j1-i2c-外设 | anchor matches only after NFKC folding: #j1-i2c-外设 |  |
| F0009 | warning | anchor_prefix_match | `references/common-hardware/applications/03-humidity-display.md:27` | ../g-power-conversion.md#g1-ldo | anchor matches a heading only by prefix: #g1-ldo |  |
| F0010 | warning | anchor_prefix_match | `references/common-hardware/applications/03-humidity-display.md:40` | ../g-power-conversion.md#g2-buck | anchor matches a heading only by prefix: #g2-buck |  |
| F0011 | warning | anchor_prefix_match | `references/common-hardware/applications/05-electronic-scale.md:29` | ../g-power-conversion.md#g1-ldo | anchor matches a heading only by prefix: #g1-ldo |  |
| F0012 | warning | anchor_prefix_match | `references/common-hardware/applications/07-current-monitor.md:114` | ../g-power-conversion.md#g2-buck | anchor matches a heading only by prefix: #g2-buck |  |
| F0013 | warning | anchor_prefix_match | `references/common-hardware/applications/07-current-monitor.md:160` | ../g-power-conversion.md#g2-buck | anchor matches a heading only by prefix: #g2-buck |  |
| F0014 | warning | anchor_prefix_match | `references/common-hardware/applications/11-data-logger.md:99` | ../g-power-conversion.md#g1-ldo | anchor matches a heading only by prefix: #g1-ldo |  |
| F0016 | warning | anchor_prefix_match | `references/common-hardware/applications/12-solenoid-controller.md:108` | ../g-power-conversion.md#g1-ldo | anchor matches a heading only by prefix: #g1-ldo |  |
| F0015 | warning | anchor_prefix_match | `references/common-hardware/applications/12-solenoid-controller.md:108` | ../g-power-conversion.md#g2-buck | anchor matches a heading only by prefix: #g2-buck |  |

## 文件与引用索引

### `CHANGELOG.md`

- 标题：变更记录
- 行/字符/字节：267 / 15299 / 24067
- SHA-256：`b82e831af72301b181e2141ba2d99051e34b22b01356efe7396f4c9b27a0f14e`

- L250 [unknown] [缺口，落成可离线复核的规则、模板与回归案例。

### 新增

- **G0–G6 阶段门禁**：[references/design-gates.md](references/design-gates.md) → `references/design-gates.md` (ok)
- L252 [unknown] [KED / UNSUPPORTED`，退出码 0/1/2。
- **布线与工具约束**：[references/pcb-routing-strategy.md](references/pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L252 [unknown] [b-routing-strategy.md)（2 层 vs 4 层、电源/地策略、布线计划、连接器逃逸）、[references/tool-gotchas.md](references/tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L255 [unknown] [、`scripts/skill_selftest.py`。
- **回归案例**：[cases/temp-alarm-2026-10-24/README.md](cases/temp-alarm-2026-10-24/README.md) → `cases/temp-alarm-2026-10-24/README.md` (ok)

### `SKILL.md`

- 标题：AI画板搭档：从想法到可用实物
- 行/字符/字节：324 / 24988 / 50163
- SHA-256：`2fe4feb283f0904f25f44ce2425c6c3766a0f8b6db45fcbd9d4e2542ff9e486d`

- L14 [conditional_read] [时沿用工程师表达。不要求用户先选择水平，也不降低内部工程核查标准。

## 安装与更新

用户要求安装、检查更新、升级、修复或回退时，读取 [安装与更新](references/installation-updates.md) → `references/installation-updates.md` (ok)
- L22 [conditional_read] [子回退。

## EasyEDA 生态工具接入

涉及差分/等长、批量工程取证、模块复用、原生文件格式、离线预览或 API 查询时，先读 [生态工具集成](references/easyeda-ecosystem.md) → `references/easyeda-ecosystem.md` (ok)
- L27 [conditional_read] [工程能力，补上产品落地层

保留本Skill已有的原理图/PCB、选型核算、工程审查、商城配单、制造交付与新手带做能力。完整idea任务再加载 [想法到实物](references/idea-to-product.md) → `references/idea-to-product.md` (ok)
- L27 [conditional_read] [idea任务再加载 [想法到实物](references/idea-to-product.md)；涉及程序、烧录、手机/网页端或样机启动时加载 [程序与样机联调](references/firmware-bringup.md) → `references/firmware-bringup.md` (ok)
- L27 [conditional_read] [uct.md)；涉及程序、烧录、手机/网页端或样机启动时加载 [程序与样机联调](references/firmware-bringup.md)；按 [功能验收](references/product-acceptance.md) → `references/product-acceptance.md` (ok)
- L36 [required_read] [DK、外部通知或云服务可能仍需要，不能为了宣称“全内部”省掉必要功能或杜撰内部服务。

## 1. 从用户想实现的效果开始

先读 [Agent协作契约](references/agent-collaboration.md) → `references/agent-collaboration.md` (ok)
- L36 [required_read] [效果开始

先读 [Agent协作契约](references/agent-collaboration.md)。新手或水平不明时，在首次答复前读 [新手带做](references/beginner-journey.md) → `references/beginner-journey.md` (ok)
- L90 [unknown] [封装 ↔ 商城C号 ↔ EDA器件/封装身份 ↔ 图纸BOM ↔ 当前装配/采购清单”的映射，不能画完再随便匹配便宜料。每个采购相关任务读 [立创商城选型与配单](references/lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L90 [unknown] [完再随便匹配便宜料。每个采购相关任务读 [立创商城选型与配单](references/lcsc-sourcing.md)；需要打样/组装再读 [嘉立创设计到实物](references/jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L90 [unknown] [nces/lcsc-sourcing.md)；需要打样/组装再读 [嘉立创设计到实物](references/jlc-handoff.md) 和 [生产规则接入](references/jlc-production.md) → `references/jlc-production.md` (ok)
- L100 [conditional_read] [只有工程副本、执行会话和输出目录都隔离时才允许候选并行写入。工具不支持子 Agent 时按相同角色串行完成，不阻塞交付。分工、交接与验收按 [Agent协作契约](references/agent-collaboration.md) → `references/agent-collaboration.md` (ok)
- L108 [conditional_read] [CLI时，先运行 `python scripts/eda_exec.py doctor`，需要工程时加 `--project <已授权副本>`；按 [EDA执行](references/eda-execution.md) → `references/eda-execution.md` (ok)
- L110 [unknown] [装了 Skill”当成就绪，也不把 `versionMatch:false` 或工程不可读当成可执行。完整路径、能力矩阵与五步首次接通见 [客户端兼容与首次接通](references/client-compatibility.md) → `references/client-compatibility.md` (ok)
- L118 [conditional_read] [固定受控动作，不执行用户JS、不下单、不访问网络。

### 原理图：先生成可复用布局，再执行与验收

新画、增加模块或整理图纸时，先读 [绘图执行方法](references/schematic-authoring.md) → `references/schematic-authoring.md` (ok)
- L118 [conditional_read] [d)，按“拓扑与角色 → 实测符号 → 模块候选 → 整页候选 → 写入 → 官方导图复核”执行。常用分压、驱动、反馈、定时和稳压模块优先使用 [参数化绘图模板](references/schematic-recipes.md) → `references/schematic-recipes.md` (ok)
- L122 [unknown] [器件身份与连接，按受影响模块修正；一次候选失败先读取具体冲突，同一失败机制重复两次就换布局方法或记录能力缺口，不继续盲改坐标。

验收仍使用 [图面验收标准](references/schematic-layout.md) → `references/schematic-layout.md` (ok)
- L122 [unknown] [ion_outlier`、`zone_reading_order`、`title_block_duplicate_text` 等图面问题，流程见 [绘图执行方法](references/schematic-authoring.md) → `references/schematic-authoring.md` (ok)
- L126 [conditional_read] [验收分别报告，任何一个 PASS 都不能代替另一个。

### 电源主干、加宽与走廊

电源主干过细、加宽受限或规划宽走廊时，读取 [电源路径与走廊预检](references/power-routing-preflight.md) → `references/power-routing-preflight.md` (ok)
- L130 [unknown] [把项目固定线宽、距离、温升值写成通用常量。

### 提速：先离线准备，再合批写入

多个独立 PCB 放置模块来自同一实测快照时，按 [批量执行与提速](references/execution-efficiency.md) → `references/execution-efficiency.md` (ok)
- L134 [required_read] [ compose/现有模板路径，不用 PCB 放置批处理冒充原理图或布线完成。

## 3. 按需读取，不加载规则百科

内部设计始终遵循 [工程工作流](references/workflow.md) → `references/workflow.md` (ok)
- L134 [required_read] [完成。

## 3. 按需读取，不加载规则百科

内部设计始终遵循 [工程工作流](references/workflow.md) 和 [证据与工程记录](references/evidence.md) → `references/evidence.md` (ok)
- L138 [conditional_read] [t消化，不要求用户读完。按任务加载：

| 当前任务 | 读取 |
|---|---|
| 完整idea、做成能用设备、需要跨业务推进 | [想法到实物](references/idea-to-product.md) → `references/idea-to-product.md` (ok)
- L139 [conditional_read] [ | [想法到实物](references/idea-to-product.md) |
| 程序开发、下载烧录、上电联调、手机/网页连接 | [程序与样机联调](references/firmware-bringup.md) → `references/firmware-bringup.md` (ok)
- L140 [conditional_read] [网页连接 | [程序与样机联调](references/firmware-bringup.md) |
| 判断原始用途是否实现、记录实测和复验 | [功能验收](references/product-acceptance.md) → `references/product-acceptance.md` (ok)
- L141 [conditional_read] [能验收](references/product-acceptance.md) |
| Agent要组织多步设计、衔接执行器与恢复失败 | [Agent协作契约](references/agent-collaboration.md) → `references/agent-collaboration.md` (ok)
- L142 [conditional_read] [ [Agent协作契约](references/agent-collaboration.md) |
| 新手、生活化需求、不会安装/选型/看图 | [新手带做](references/beginner-journey.md) → `references/beginner-journey.md` (ok)
- L143 [conditional_read] [会安装/选型/看图 | [新手带做](references/beginner-journey.md) |
| 初次使用、判断任务范围和评审节奏 | [首次协作](references/interaction.md) → `references/interaction.md` (ok)
- L144 [conditional_read] [ 初次使用、判断任务范围和评审节奏 | [首次协作](references/interaction.md) |
| 组合新模块、避免漏掉外围 | [模块设计卡](references/module-cards.md) → `references/module-cards.md` (ok)
- L145 [conditional_read] [组合新模块、避免漏掉外围 | [模块设计卡](references/module-cards.md) |
| 用户要求选型、换料或BOM | [选型与装配变体](references/part-selection.md) → `references/part-selection.md` (ok)
- L146 [conditional_read] [选型与装配变体](references/part-selection.md) |
| 立创商城选料、查货、估价、BOM配单、缺料替代 | [立创商城选型与配单](references/lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L147 [conditional_read] [ [立创商城选型与配单](references/lcsc-sourcing.md) |
| 嘉立创打板/贴片、选择工艺、设置厂规或工厂驳回 | [生产规则接入](references/jlc-production.md) → `references/jlc-production.md` (ok)
- L148 [conditional_read] [roduction.md)，Agent维护实际订单工艺与证据，不要求新手填表 |
| PCB层叠/铜厚/线孔/阻焊/成型与特殊工艺 | [嘉立创PCB生产规则](references/jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L149 [conditional_read] [es/jlc-pcb-rules.md)，数值为需重查的条件快照 |
| SMT工艺边/Mark/拼板/可焊性/BOM坐标/DFM | [嘉立创SMT生产规则](references/jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)
- L150 [conditional_read] [eferences/jlc-smt-rules.md)，区分服务类型与当前实际订单 |
| 嘉立创PCB/SMT/手焊与按需结构件交付 | [嘉立创设计到实物](references/jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L151 [conditional_read] [/SMT/手焊与按需结构件交付 | [嘉立创设计到实物](references/jlc-handoff.md) |
| 准备离线连接表或自检 | [连接表契约](references/connectivity.md) → `references/connectivity.md` (ok)
- L152 [conditional_read] [|
| 准备离线连接表或自检 | [连接表契约](references/connectivity.md) |
| 选择技术路线、判断覆盖范围 | [领域路由](references/domains.md) → `references/domains.md` (ok)
- L153 [conditional_read] [|
| 选择技术路线、判断覆盖范围 | [领域路由](references/domains.md) |
| 电源树、电池、驱动、保护或发热 | [电源与功率](references/power.md) → `references/power.md` (ok)
- L154 [conditional_read] [电池、驱动、保护或发热 | [电源与功率](references/power.md) |
| MCU/SoC/FPGA、时钟、复位、数字接口 | [数字与接口](references/digital.md) → `references/digital.md` (ok)
- L155 [conditional_read] [/FPGA、时钟、复位、数字接口 | [数字与接口](references/digital.md) |
| 模拟采集、音视频、射频或高速链路 | [模拟与高速](references/analog-rf-highspeed.md) → `references/analog-rf-highspeed.md` (ok)
- L156 [conditional_read] [射频或高速链路 | [模拟与高速](references/analog-rf-highspeed.md) |
| 绘制/整理/换料/建库 | [原理图工程习惯](references/schematic.md) → `references/schematic.md` (ok)
- L157 [conditional_read] [/建库 | [原理图工程习惯](references/schematic.md) |
| 新建原理图、增功能块、图面混乱或排版整理 | [原理图排版与看图验收](references/schematic-layout.md) → `references/schematic-layout.md` (ok)
- L158 [required_read] [补齐 `order`/`purpose`，缺 purpose 文本默认 blocked |
| 已有原理图重排、自动布局、提高整页可读性 | [原理图排版引擎](references/schematic-layout-engine.md) → `references/schematic-layout-engine.md` (ok)
- L159 [conditional_read] [plan` → 合页 → 受保护写入 → 网表/导图复核；先读该文件的并发与工具限制 |
| 用8类典型任务校准排版检查、准备前后对比 | [原理图排版基准集](references/schematic-benchmarks.md) → `references/schematic-benchmarks.md` (ok)
- L160 [conditional_read] [ic_benchmark.py`；基准是离线示意，不是真机验收 |
| 已有真实回读，需要确定性几何/身份审计、纯排版前后对比或标签规划 | [确定性设计引擎](references/design-engine.md) → `references/design-engine.md` (ok)
- L161 [required_read] [bels/compare/pcb-audit`；离线结论不等于 EDA 应用 |
| 真实读写嘉立创EDA工程、恢复超时/重复执行、保存重开 | [EDA执行](references/eda-execution.md) → `references/eda-execution.md` (ok)
- L162 [conditional_read] [，`netlist_diff.py` 做纯排版网表门禁 |
| 批量写入、超时恢复、版本化缓存、通道模板复用、执行耗时与多Agent分工 | [EDA执行效率](references/eda-efficiency.md) → `references/eda-efficiency.md` (ok)
- L163 [conditional_read] [/`eda_cache.py`，同一工程单写入者，save/reload 后回读才算验收 |
| 不知道客户端、安装目录或首次接通 | [客户端兼容与首次接通](references/client-compatibility.md) → `references/client-compatibility.md` (ok)
- L164 [conditional_read] [ scripts/doctor_env.py --summary`，按当前客户端逐条判定 |
| 导入PCB、布局、布线、铜皮、制造输出 | [PCB工程习惯](references/pcb.md) → `references/pcb.md` (ok)
- L165 [required_read] [出 | [PCB工程习惯](references/pcb.md) |
| 真实PCB布局布线、约束/局部模板/候选、逃线迭代、保存重开 | [PCB执行工作流](references/pcb-execution.md) → `references/pcb-execution.md` (ok)
- L165 [required_read] [约束/局部模板/候选、逃线迭代、保存重开 | [PCB执行工作流](references/pcb-execution.md)，命令与证据角色见 [PCB命令映射](references/pcb-command-map.json) → `references/pcb-command-map.json` (ok)
- L165 [required_read] [cripts/pcb_gate.py`，整案证据 `scripts/pcb_case.py`；先读实测dump与sch引脚。交付逐项核对 [PCB 交付检查清单](assets/pcb-delivery-checklist.md) → `assets/pcb-delivery-checklist.md` (ok)
- L166 [conditional_read] [sets/pcb-delivery-checklist.md)。 |
| 观察→局部修改→回读→复验、越界/并发/部分失败恢复、案例检索与复用 | [反馈闭环](references/feedback-loop.md) → `references/feedback-loop.md` (ok)
- L167 [conditional_read] [eadback/verify/recover/case-search`；只读命令不写入，未回读不写通过 |
| 设计审查、故障排查、样机上电 | [审查与验证](references/review.md) → `references/review.md` (ok)
- L168 [background] [回读不写通过 |
| 设计审查、故障排查、样机上电 | [审查与验证](references/review.md) |
| 查询官方资料入口 | [来源导航](references/sources.md) → `references/sources.md` (ok)
- L169 [conditional_read] [询官方资料入口 | [来源导航](references/sources.md) |
| 新建/实质修改SCH或PCB，需要选取适用经验 | [工程经验库与来源](references/design-experience.md) → `references/design-experience.md` (ok)
- L170 [conditional_read] [erences/design-experience.md)，按当前对象选择，避免全量加载 |
| 需要理解易错机制、把经验变成模块前后检查 | [原理图机制卡](references/schematic-lessons.md) → `references/schematic-lessons.md` (ok)
- L170 [conditional_read] [加载 |
| 需要理解易错机制、把经验变成模块前后检查 | [原理图机制卡](references/schematic-lessons.md)、[PCB机制卡](references/pcb-lessons.md) → `references/pcb-lessons.md` (ok)
- L171 [conditional_read] [、[PCB机制卡](references/pcb-lessons.md)，按对象选择，不重复计数 |
| 原理图逐脚、电源状态、接口和库细节 | [原理图细节](references/schematic-details.md) → `references/schematic-details.md` (ok)
- L172 [conditional_read] [节 | [原理图细节](references/schematic-details.md) |
| PCB机械约束、关键回路、敏感区和放件 | [PCB布局细节](references/pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L173 [conditional_read] [局细节](references/pcb-placement-details.md) |
| PCB电源/地、高速、模拟、RF、铜区和回流 | [布线与回流细节](references/pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L174 [conditional_read] [线与回流细节](references/pcb-routing-details.md) |
| 封装、孔/阻焊/钢网、制造输出、装配和首板 | [制造与首板细节](references/manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L175 [conditional_read] [ [制造与首板细节](references/manufacturing-details.md) |
| 具体硬件类型的跨SCH/PCB易漏项 | [领域易漏项](references/domain-design-details.md) → `references/domain-design-details.md` (ok)
- L176 [conditional_read] [易漏项 | [领域易漏项](references/domain-design-details.md) |
| 原型路线、常见小产品起步方案 | [起步方案骨架](references/starter-patterns.md) → `references/starter-patterns.md` (ok)
- L177 [conditional_read] [骨架](references/starter-patterns.md)，不是已验证可直接生产的电路 |
| 外壳、安装、线束、模型与PCB联动 | [结构协同](references/enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L178 [conditional_read] [[结构协同](references/enclosure-integration.md) |
| 跨图纸/BOM/程序/结构的版本与引脚联动 | [项目关联记录](references/project-coherence.md) → `references/project-coherence.md` (ok)
- L179 [conditional_read] [与引脚联动 | [项目关联记录](references/project-coherence.md) |
| 连接、检查、制造、烧录或实物出问题 | [分层排障](references/troubleshooting.md) → `references/troubleshooting.md` (ok)
- L180 [conditional_read] [或实物出问题 | [分层排障](references/troubleshooting.md) |
| 续航核算、已有实际回读几何需辅助检查 | [离线工具契约](references/offline-tools.md) → `references/offline-tools.md` (ok)
- L181 [example] [几何需辅助检查 | [离线工具契约](references/offline-tools.md) |
| 需要学习完整idea任务如何接续 | [花盆提醒器演练](references/product-example.md) → `references/product-example.md` (ok)
- L182 [conditional_read] [nces/product-example.md)，不可当成已验证设计 |
| 具体电源/主控/接口/模拟/驱动/无线电路的设计方法、算例与选型 | [设计卡库](references/design-cards/README.md) → `references/design-cards/README.md` (ok)
- L183 [conditional_read] [ards/README.md) |
| 用户说“测温/称重/测压力/控制风扇/做电池设备/加个屏幕”等日常需求，需要选路线、查型号、画具体电路 | [常用硬件](references/common-hardware/README.md) → `references/common-hardware/README.md` (ok)
- L184 [example] [ware/README.md)，按 A–M 组和 12 个组合应用读取 |
| 局部原理图/PCB 范例、局部短线与标签、常见错误 | [原理图/PCB 范例](references/examples/README.md) → `references/examples/README.md` (ok)
- L185 [conditional_read] [| [原理图/PCB 范例](references/examples/README.md) |
| 两个模块单独正常但组合失败、接口契约 | [组合与接口契约](references/module-integration.md) → `references/module-integration.md` (ok)
- L186 [conditional_read] [| [组合与接口契约](references/module-integration.md) |
| 器件选型、替代分级、立创商城检索顺序 | [器件选型与替代](references/selection/README.md) → `references/selection/README.md` (ok)
- L187 [conditional_read] [城检索顺序 | [器件选型与替代](references/selection/README.md) |
| 故障现象、根因证据、修复与复验 | [故障与反例库](references/failures/README.md) → `references/failures/README.md` (ok)
- L188 [conditional_read] [ [故障与反例库](references/failures/README.md) |
| 真实设计为什么这样、为什么失败、跨模块失效与审图训练 | [工程深潜](references/engineering-deepdives/README.md) → `references/engineering-deepdives/README.md` (ok)
- L188 [conditional_read] [什么这样、为什么失败、跨模块失效与审图训练 | [工程深潜](references/engineering-deepdives/README.md)、[审图练习](references/engineering-deepdives/exercises/README.md) → `references/engineering-deepdives/exercises/README.md` (ok)
- L189 [conditional_read] [engineering-deepdives/exercises/README.md) |
| 热预算、结温/瞬态、PCB散热/外壳、温度测量 | [板级热设计](references/thermal/topic.md) → `references/thermal/topic.md` (ok)
- L189 [conditional_read] [DME.md) |
| 热预算、结温/瞬态、PCB散热/外壳、温度测量 | [板级热设计](references/thermal/topic.md)、[热算例](references/thermal/cases.md) → `references/thermal/cases.md` (ok)
- L189 [conditional_read] [量 | [板级热设计](references/thermal/topic.md)、[热算例](references/thermal/cases.md)、[热来源](references/thermal/sources.md) → `references/thermal/sources.md` (ok)
- L190 [conditional_read] [d)、[热来源](references/thermal/sources.md)，S编号仅本专题有效 |
| 带条件的计算、可执行仿真与测量方法 | [计算手册](references/calculations/README.md) → `references/calculations/README.md` (ok)
- L190 [conditional_read] [仅本专题有效 |
| 带条件的计算、可执行仿真与测量方法 | [计算手册](references/calculations/README.md)、[仿真与测量](references/simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L191 [conditional_read] [量](references/simulation-measurement.md) |
| 商城购料自焊、嘉立创 PCB+SMT、整机交付 | [制造与交付路线](references/manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L192 [conditional_read] [MT、整机交付 | [制造与交付路线](references/manufacturing-routes.md) |
| 完整项目样本与完成级别 | [项目样本](references/projects/README.md) → `references/projects/README.md` (ok)
- L193 [conditional_read] [| 完整项目样本与完成级别 | [项目样本](references/projects/README.md) |
| 任务场景、反例与确定性验收 | [任务场景](references/task-scenarios.md) → `references/task-scenarios.md` (ok)
- L194 [conditional_read] [ [任务场景](references/task-scenarios.md) |
| 架构方案比较、决策记录、过度设计与需求变化后重评 | [设计决策库 A–L](references/decisions/README.md) → `references/decisions/README.md` (ok)
- L195 [conditional_read] [README.md)，按 D0/D1/D2 深度加载，不要求简单项目全流程 |
| 主控引脚/外设资源、启动/调试脚、工作状态与接口契约 | [引脚与资源规划](references/decisions/b01-pin-resource-planning.md) → `references/decisions/b01-pin-resource-planning.md` (ok)
- L195 [conditional_read] [脚、工作状态与接口契约 | [引脚与资源规划](references/decisions/b01-pin-resource-planning.md)、[工作状态](references/decisions/c01-state-transition-contract.md) → `references/decisions/c01-state-transition-contract.md` (ok)
- L195 [conditional_read] [planning.md)、[工作状态](references/decisions/c01-state-transition-contract.md)、[接口契约](references/decisions/e01-interface-contract.md) → `references/decisions/e01-interface-contract.md` (ok)
- L196 [conditional_read] [eferences/decisions/e01-interface-contract.md) |
| 容差/最坏情况、受控实验与采用决定 | [容差与最坏情况](references/decisions/d01-tolerance-and-worst-case.md) → `references/decisions/d01-tolerance-and-worst-case.md` (ok)
- L196 [conditional_read] [控实验与采用决定 | [容差与最坏情况](references/decisions/d01-tolerance-and-worst-case.md)、[受控实验](references/decisions/k01-controlled-experiment.md) → `references/decisions/k01-controlled-experiment.md` (ok)
- L197 [conditional_read] [ferences/decisions/k01-controlled-experiment.md) |
| 线束/连接器、产品变体与差异 BOM | [整机线束](references/decisions/f01-harness-and-board-external.md) → `references/decisions/f01-harness-and-board-external.md` (ok)
- L197 [conditional_read] [变体与差异 BOM | [整机线束](references/decisions/f01-harness-and-board-external.md)、[产品变体](references/decisions/g01-product-variants.md) → `references/decisions/g01-product-variants.md` (ok)
- L198 [conditional_read] [erences/decisions/g01-product-variants.md) |
| 校准/设备身份、工程变更、模块复用、资产有效性 | [校准与身份](references/decisions/h01-calibration-and-identity.md) → `references/decisions/h01-calibration-and-identity.md` (ok)
- L198 [conditional_read] [模块复用、资产有效性 | [校准与身份](references/decisions/h01-calibration-and-identity.md)、[变更影响](references/decisions/i01-change-impact.md) → `references/decisions/i01-change-impact.md` (ok)
- L198 [conditional_read] [bration-and-identity.md)、[变更影响](references/decisions/i01-change-impact.md)、[模块复用](references/decisions/j01-module-reuse.md) → `references/decisions/j01-module-reuse.md` (ok)
- L198 [conditional_read] [ns/i01-change-impact.md)、[模块复用](references/decisions/j01-module-reuse.md)、[资产有效性](references/decisions/l01-asset-validity.md) → `references/decisions/l01-asset-validity.md` (ok)
- L199 [example] [性](references/decisions/l01-asset-validity.md) |
| 阶段门禁、设计状态、G0–G6 退出证据 | [阶段门禁](references/design-gates.md) → `references/design-gates.md` (ok)
- L199 [example] [alidity.md) |
| 阶段门禁、设计状态、G0–G6 退出证据 | [阶段门禁](references/design-gates.md)、[状态示例](assets/design-state.example.json) → `assets/design-state.example.json` (ok)
- L200 [conditional_read] [e.json)，运行 `python scripts/gate_check.py` |
| 层数选择、电源/地策略、布线计划、连接器逃逸 | [PCB布线策略](references/pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L200 [conditional_read] [| 层数选择、电源/地策略、布线计划、连接器逃逸 | [PCB布线策略](references/pcb-routing-strategy.md)、[布线计划模板](assets/routing-plan.md) → `assets/routing-plan.md` (ok)
- L201 [conditional_read] [-strategy.md)、[布线计划模板](assets/routing-plan.md) |
| 工具报错、命令行为、前台/超时/部分写入 | [工具陷阱](references/tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L202 [conditional_read] [ [工具陷阱](references/tool-gotchas.md) |
| 设计前核算：阈值/回差、NTC、LED/蜂鸣器、压降、载流 | [设计计算模板](assets/design-calc.md) → `assets/design-calc.md` (ok)
- L203 [conditional_read] [s/design-calc.md)，需要可执行核算时用 `scripts/calculate.py` |
| 机械/热/丝印装配/制造包/验证记录 | [机械](assets/docs/mechanical.md) → `assets/docs/mechanical.md` (ok)
- L203 [conditional_read] [s/calculate.py` |
| 机械/热/丝印装配/制造包/验证记录 | [机械](assets/docs/mechanical.md)、[温度传感器](assets/docs/thermal-sensor.md) → `assets/docs/thermal-sensor.md` (ok)
- L203 [conditional_read] [录 | [机械](assets/docs/mechanical.md)、[温度传感器](assets/docs/thermal-sensor.md)、[丝印装配](assets/docs/silk-assembly.md) → `assets/docs/silk-assembly.md` (ok)
- L203 [conditional_read] [[温度传感器](assets/docs/thermal-sensor.md)、[丝印装配](assets/docs/silk-assembly.md)、[制造包](assets/docs/manufacturing-package.md) → `assets/docs/manufacturing-package.md` (ok)
- L203 [conditional_read] [配](assets/docs/silk-assembly.md)、[制造包](assets/docs/manufacturing-package.md)、[验证](assets/docs/verification.md) → `assets/docs/verification.md` (ok)
- L204 [example] [age.md)、[验证](assets/docs/verification.md) |
| BOM/引脚结构化检查、Skill 自检与回归案例 | [零件示例](assets/parts.example.json) → `assets/parts.example.json` (ok)
- L204 [example] [on.md) |
| BOM/引脚结构化检查、Skill 自检与回归案例 | [零件示例](assets/parts.example.json)、[引脚图示例](assets/pinmap.example.json) → `assets/pinmap.example.json` (ok)
- L204 [example] [xample.json)、`scripts/bom_check.py`、`scripts/skill_selftest.py`、[temp-alarm 回归案例](cases/temp-alarm-2026-10-24/README.md) → `cases/temp-alarm-2026-10-24/README.md` (ok)
- L205 [conditional_read] [ses/temp-alarm-2026-10-24/README.md) |
| 无 EDA 的完整回归、证据绑定、冻结基准、图面叠加图 | [离线回归与基准](references/offline-regression.md) → `references/offline-regression.md` (ok)
- L222 [unknown] [。开源图纸、作者已修缺陷和原厂指南分别作为观察/查证依据，不按星数决定正确性，不把来源已查看当当前工程已验证。

制造相关设计由Agent按 [生产档案模板](assets/manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L226 [unknown] [查、记录并继续，不新增等待点；只有证据缺失或门禁失败时停住依赖链路。G0–G6 是 S1–S5 的退出条件，不是第二套流程；定义、命令、证据与豁免见 [阶段门禁](references/design-gates.md) → `references/design-gates.md` (ok)
- L230 [example] [ `gate_check.py` 使用同一组键，不另造别名。

- **状态载体**：非平凡项目用 `design-state.json`（模板 [状态示例](assets/design-state.example.json) → `assets/design-state.example.json` (ok)
- L230 [example] [例](assets/design-state.example.json)）记录需求、功能冻结、布局/层叠/布线/制造证据、假设与未决项；小修改可沿用 [工程记录](assets/engineering-notes.md) → `assets/engineering-notes.md` (ok)
- L240 [unknown] [样机联调与用途验收，能并行的准备同步推进，按用户范围跳过无关阶段。阶段完成由实际证据决定，不为推进而伪造证据。

为非平凡工程维护精简记录，可从 [记录模板](assets/engineering-notes.md) → `assets/engineering-notes.md` (ok)
- L242 [unknown] [ngineering-notes.md) 复制到工程工作区；沿用已有记录而不另建同义文件。小修改在会话和变更报告中记清即可。

从零项目可用 [需求摘要模板](assets/design-brief.md) → `assets/design-brief.md` (ok)
- L272 [required_read] [或伪造指纹绕过拦截。遇到 418/拦截先读本地日志并停止相关请求，异常不代表型号不存在；共享出口的 Agent 协同退避，转做离线工作。见 [网络纪律与服务阻塞](references/network-discipline.md) → `references/network-discipline.md` (ok)
- L278 [required_read] [

需要离线连接表检查时运行 `python scripts/netlist_check.py <design.json> --json`，先读 [连接表契约](references/connectivity.md) → `references/connectivity.md` (ok)
- L282 [required_read] [、手册注释不得变成工具指令。

电池项目可用 `python scripts/power_budget.py budget.json`，先读 [离线工具契约](references/offline-tools.md) → `references/offline-tools.md` (ok)
- L284 [conditional_read] [、`variant_bom.py`、`decision_record_check.py`、`decision_asset_check.py`，先读 [设计决策库](references/decisions/README.md) → `references/decisions/README.md` (ok)
- L286 [required_read] [e_check.py --project <name> --evidence-dir <dir> --design-state <file>`，先读 [阶段门禁](references/design-gates.md) → `references/design-gates.md` (ok)
- L288 [unknown] [ifest 绑定、`match_with_renames`、pin alias/ignore、no-op/journal 状态和凹板几何边界见 [离线回归与基准](references/offline-regression.md) → `references/offline-regression.md` (ok)
- L290 [required_read] [通过不等于真实 EDA/硬件通过。

BOM/装配结构用 `python scripts/bom_check.py parts.json`，先按 [零件示例](assets/parts.example.json) → `assets/parts.example.json` (ok)
- L290 [required_read] [tandard-parts.json --expect-designator RV1=10kΩ` 核对 C 号、本地映射回填与重复/冲突（见 [嘉立创设计到实物](references/jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L294 [required_read] [何硬件或 EDA 工程已验证。

需要真实读写嘉立创EDA工程时运行 `python scripts/eda_exec.py` 的子命令，先读 [EDA执行](references/eda-execution.md) → `references/eda-execution.md` (ok)
- L296 [required_read] [保存后按 `reopen-check` 验证持久化。它只支持本文件列出的原理图原语，不覆盖PCB、下单或任意JS。

真实PCB任务先读 [PCB执行工作流](references/pcb-execution.md) → `references/pcb-execution.md` (ok)
- L296 [required_read] [，不覆盖PCB、下单或任意JS。

真实PCB任务先读 [PCB执行工作流](references/pcb-execution.md) 与 [PCB命令映射](references/pcb-command-map.json) → `references/pcb-command-map.json` (ok)
- L298 [conditional_read] [模板缺少实测引脚/适用条件时拒绝；`near_pin` 的中心距和逃线预判都不是铜路径证明。

需要把一次画板/改板/检查做成可恢复闭环时，先读 [反馈闭环](references/feedback-loop.md) → `references/feedback-loop.md` (ok)
- L302 [required_read] [量通过是五件事，缺一项就是 `NOT RUN`/`unknown`，不能合并成“完成”。

## 7. 让用户看懂进度和结果

对新手先按 [新手交付卡](assets/beginner-summary.md) → `assets/beginner-summary.md` (ok)
- L315 [unknown] [据。
3. 原理图连接、PCB未布线/DRC、保存与同步的实际结果。
4. 尚未解决的阻断项、待测项目及下一步。
5. 涉及采购/打样时，按 [购料交付卡](assets/sourcing-summary.md) → `assets/sourcing-summary.md` (ok)
- L317 [conditional_read] [

问题用“阻断 / 建议 / 提示”表示处置优先级，另列“已证实 / 条件风险 / 待核实”表示证据状态；不能把猜测直接升成已证实阻断。采用 [交付摘要模板](assets/review-summary.md) → `assets/review-summary.md` (ok)
- L319 [unknown] [采用 [交付摘要模板](assets/review-summary.md)，按任务裁剪，保留检查范围与缺测，不为凑格式输出空表。

完整产品以 [产品进度卡](assets/product-progress.md) → `assets/product-progress.md` (ok)

### `assets/beginner-summary.md`

- 标题：这次做到哪里了
- 行/字符/字节：16 / 478 / 1244
- SHA-256：`180bc5eb3e971c221a56f70b50d6fc7521baccbb0fd2d97ad26d10f646dea93d`

### `assets/decisions/asset-index.r4p6.example.md`

- 标题：决策资产索引示例（R4-P6）
- 行/字符/字节：27 / 3001 / 4078
- SHA-256：`b79fb759c7abf04e8e08e0016b4ddfa98f550c01d6e7cdbfa6f03cabadeab810`

### `assets/decisions/asset-index.template.md`

- 标题：决策资产索引（Agent 填写，用户不填）
- 行/字符/字节：49 / 2218 / 3618
- SHA-256：`e5bc850979081eb894ba6ebf6c58c147dc858b06566c48b33b3b42f55ef6a52d`

### `assets/decisions/decision-record.template.md`

- 标题：工程决策记录（Agent 填写，用户不填）
- 行/字符/字节：70 / 1600 / 2836
- SHA-256：`cf2f09323e710b9962cdbf56f419928327b8ae31f28cffa2bbbd2ab70496a1f9`

### `assets/decisions/experiment-record.template.md`

- 标题：受控实验预注册与记录（Agent 填写，用户不填）
- 行/字符/字节：60 / 2136 / 4201
- SHA-256：`2e4994bd4975498e796eed7383675d2ad2e2e8236a59c810ba92e02754309220`

### `assets/decisions/harness-package.template.md`

- 标题：整机线束包模板（Agent 填写，用户不填）
- 行/字符/字节：43 / 1501 / 2445
- SHA-256：`de53a3507ea7bc5c56b1cc49f345652387da9e0254f0b6595064d5bcb3422fa5`

### `assets/decisions/module-reuse-record.template.md`

- 标题：模块复用合同（Agent 填写，用户不填）
- 行/字符/字节：61 / 1624 / 2758
- SHA-256：`4752b9e9814680d73fd17c61f5c4f16f38cb9c797ab023c55a80d047bde52c65`

### `assets/decisions/tolerance-budget.template.md`

- 标题：容差预算与角点决策（Agent 填写，用户不填）
- 行/字符/字节：61 / 2712 / 4743
- SHA-256：`b00868b901963206dad69fc4246500ed0b42a821b23e08aba946802699b1cede`

### `assets/decisions/variant-matrix.template.md`

- 标题：产品变体矩阵模板（Agent 填写，用户不填）
- 行/字符/字节：49 / 1522 / 2427
- SHA-256：`763db7c826cfd9e69082753b1b26d87e8fc4318c7c74943d5ca196646d643827`

### `assets/design-brief.md`

- 标题：需求摘要（G0 输入）
- 行/字符/字节：97 / 3323 / 6355
- SHA-256：`5700b4e0d7c9d129658dea27ad31a7893b6b1043a40f9230e131e19b803c618f`

- L3 [background] [确认后的值要转录到项目 `design-state.json` 的 `requirements.<key>`，G0 门禁读取那里；字段名与门禁定义见 [门禁定义](../references/design-gates.md) → `references/design-gates.md` (ok)
- L56 [unknown] [。
- 接口朝向、板边位置、最高器件、外壳内净空、锁定件/卡扣：
- 机械细节（板框、安装孔、插头空间、声孔、LED、NTC、应力释放）：转 [机械约束模板](docs/mechanical.md) → `assets/docs/mechanical.md` (ok)
- L57 [unknown] [约束模板](docs/mechanical.md)，本摘要只留结论。
- 丝印/装配标识（极性、1 脚、板名/版本、DNP、测试点标签）：转 [丝印与装配模板](docs/silk-assembly.md) → `assets/docs/silk-assembly.md` (ok)

### `assets/design-calc.md`

- 标题：设计核算表：阈值、回差、电流与压降
- 行/字符/字节：384 / 12676 / 21382
- SHA-256：`461da18510964ea662c99b3b300427de6a8a8fbe9187d43fe1ce013f18860958`

- L5 [unknown] [/应用笔记；`E2` = 通用工程方法或有来源入口，具体型号参数待核；`E3` = 离线估算/推断。`E2/E3` 不得写成保证值。证据分层见 [证据与轻量记录](../references/evidence.md) → `references/evidence.md` (ok)
- L12 [background] [-state.json` 或 `review-summary.md`；完整计算落项目 `docs/`，聊天里只给摘要。
4. 通用公式与更多算例见 [计算手册](../references/calculations/README.md) → `references/calculations/README.md` (ok)
- L12 [background] [
4. 通用公式与更多算例见 [计算手册](../references/calculations/README.md)；可执行脚本见 [calculate.py](../scripts/calculate.py) → `scripts/calculate.py` (ok)
- L13 [unknown] [t_sense`；所有结果都带 `board_verified:false`。NTC/Beta 与比较器回差没有专门模式，用本文公式或 [RTD/热敏电阻设计卡](../references/design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L191 [unknown] [）。
- **不能证明：** 实际安装介质与气流下的 `D`、与蜂鸣器/电源的热耦合、长期漂移、NTC 批次公差、失效检测是否可靠。布置要求见 [热敏电阻模板](docs/thermal-sensor.md) → `assets/docs/thermal-sensor.md` (ok)
- L344 [unknown] [_contact` 用最大接触电阻；回流路径与电源路径同样计入。
- PCB 走线压降/温升用 `calculate.py wire` 复核（见 [互连与载流](../references/calculations/interconnect.md) → `references/calculations/interconnect.md` (ok)
- L383 [unknown] [ 接触老化、线缆、热插拔、ESD | 同上 |

记录结论时同时写“算过”和“测过”两种状态：本表通过只说明纸面模型成立，门禁所需的实板证据仍按 [门禁定义](../references/design-gates.md) → `references/design-gates.md` (ok)

### `assets/docs/manufacturing-package.md`

- 标题：制造包清单（G6）
- 行/字符/字节：191 / 8377 / 13440
- SHA-256：`7ed02e3b0a97075beb7c327f93c17bc715bf356798835684274813dec183c5fa`

- L3 [example] [turing/`）后按实际导出结果填写。未核项写 `待核`，不默认放行；未知值不填 0、不编造。工艺参数另按 [manufacturing-profile.md](../manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L3 [example] [manufacturing-profile.md](../manufacturing-profile.md) 记录，实物测试按 [verification.md](verification.md) → `assets/docs/verification.md` (ok)
- L3 [example] [.md) 记录，实物测试按 [verification.md](verification.md) 执行，结构化选料台账见 [parts.example.json](../parts.example.json) → `assets/parts.example.json` (ok)
- L3 [example] [料台账见 [parts.example.json](../parts.example.json) 与本文第 5 节。门禁定义见 [design-gates.md](../../references/design-gates.md) → `references/design-gates.md` (ok)
- L64 [unknown] [塞孔 | PTH/NPTH、槽宽、是否树脂塞孔/盖帽 | 槽被当成钻孔导出 |

层数决策与电源/地策略见 [pcb-routing-strategy.md](../../references/pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L64 [unknown] [ategy.md](../../references/pcb-routing-strategy.md)；渠道与动态费用边界见 [lcsc-sourcing.md](../../references/lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L64 [unknown] [与动态费用边界见 [lcsc-sourcing.md](../../references/lcsc-sourcing.md) 和 [jlc-handoff.md](../../references/jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L81 [example] [_check.py`

`parts/v1` 是选料/库存/DNP 的计划台账，不是 EDA 导出的 BOM。示例见 [parts.example.json](../parts.example.json) → `assets/parts.example.json` (ok)
- L159 [unknown] [ath": "docs/test-plan.md", "status": "pass"}
}
```

测试计划可基于 [verification.md](verification.md) → `assets/docs/verification.md` (ok)
- L165 [unknown] [ON 回执用 `restoreVerified`。二者不能混写。

## 7. 测试计划与“未证明”清单

实物测试按 [verification.md](verification.md) → `assets/docs/verification.md` (ok)

### `assets/docs/mechanical.md`

- 标题：机械约束与接口（模板）
- 行/字符/字节：67 / 3259 / 6597
- SHA-256：`f3ace4985b1003aca8c4ef9a34d91af069546ee6cbba05d4ba2dafc7cdc8d2c6`

- L6 [unknown] [，括号注明来源单位（EDA 命令多用 mil）；不在同一行混用 mm/mil。
- 只记录影响布局、装配或整机使用的机械约束；纯电气与工艺规则留在 [生产档案](../manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L7 [unknown] [或整机使用的机械约束；纯电气与工艺规则留在 [生产档案](../manufacturing-profile.md)。
- 外壳协同方法与材料边界见 [结构协同](../../references/enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L7 [unknown] [
- 外壳协同方法与材料边界见 [结构协同](../../references/enclosure-integration.md)；丝印标识见 [丝印与装配模板](silk-assembly.md) → `assets/docs/silk-assembly.md` (ok)
- L8 [unknown] [on.md)；丝印标识见 [丝印与装配模板](silk-assembly.md)。
- NTC/温度传感器的自热、响应时间与热路径另见 [温度传感器热设计模板](thermal-sensor.md) → `assets/docs/thermal-sensor.md` (ok)

### `assets/docs/silk-assembly.md`

- 标题：丝印与装配标识（模板）
- 行/字符/字节：73 / 3331 / 6737
- SHA-256：`0d1ab19c6ac22e4481b1649b7187f2740da7fc5f9f4dd1a969dd9fd1a462e031`

- L5 [unknown] [件的情况下可读。底层丝印按底面视角正确可读（EDA 中镜像），装配图分别出 Top/Bottom 视图。最小线宽/字高、到焊盘和板边距离以当次板厂与 [生产档案](../manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L5 [unknown] [、到焊盘和板边距离以当次板厂与 [生产档案](../manufacturing-profile.md) 为准，未知写 `待确认`。极性与方向规则另见 [制造细节](../../references/manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L5 [unknown] [ `待确认`。极性与方向规则另见 [制造细节](../../references/manufacturing-details.md) 与 [嘉立创 SMT 规则](../../references/jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)
- L34 [unknown] [成极性、1 脚或功能标记；运行后必须复核这些标记是否被移动、遮挡或覆盖。
- 自动避让后检查文字是否落入外壳遮挡区、插头空间或声孔；这些区域以 [机械约束模板](mechanical.md) → `assets/docs/mechanical.md` (ok)
- L71 [unknown] [`待确认`，不得默认可接受。
- G6 前：装配图、DNP 表、BOM、CPL 一致；缺一项或相互矛盾按 `BLOCKED` 处理。制造包清单见 [制造包清单](manufacturing-package.md) → `assets/docs/manufacturing-package.md` (ok)
- L71 [unknown] [项或相互矛盾按 `BLOCKED` 处理。制造包清单见 [制造包清单](manufacturing-package.md)，首件装配与功能验证按 [实物验证记录](verification.md) → `assets/docs/verification.md` (ok)

### `assets/docs/thermal-sensor.md`

- 标题：温度传感器热设计记录（模板）
- 行/字符/字节：91 / 3433 / 5696
- SHA-256：`c2442cd3f1ebc50584491ad7e9dac68448f6fb1c772e83d607543feddcdf7e5b`

- L3 [unknown] [1000）和数字温度传感器（I2C/SPI/1-Wire）。在 G0 需求（环境、精度、响应时间）确认后开始填，G3 布局冻结前完成结论；与 [PCB 布线策略](../../references/pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L3 [unknown] [结前完成结论；与 [PCB 布线策略](../../references/pcb-routing-strategy.md) 的 NTC 小节、[PCB 布局细节](../../references/pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L90 [unknown] [RUN`。

对应门禁：G0 环境/精度、G3 布局、G6 测试计划；最终精度结论只能在实物标定后给出。状态词与证据要求见 [design-gates.md](../../references/design-gates.md) → `references/design-gates.md` (ok)

### `assets/docs/verification.md`

- 标题：实物验证记录（交付前 / G6）
- 行/字符/字节：95 / 4070 / 8075
- SHA-256：`6eaf54c932b4afe63a111ebc825891e7e497ccc6608ed04a9f44576c06cbfd3f`

- L3 [unknown] [`PASS / PASS_WITH_WAIVER / BLOCKED / UNSUPPORTED`。制造包见 [manufacturing-package.md](manufacturing-package.md) → `assets/docs/manufacturing-package.md` (ok)
- L3 [unknown] [ufacturing-package.md](manufacturing-package.md)，工艺档案见 [manufacturing-profile.md](../manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L3 [unknown] [见 [manufacturing-profile.md](../manufacturing-profile.md)，门禁定义见 [design-gates.md](../../references/design-gates.md) → `references/design-gates.md` (ok)

### `assets/engineering-notes.md`

- 标题：工程记录
- 行/字符/字节：56 / 1241 / 2507
- SHA-256：`bba1ae11660c99974de3175fc25733328a0fac5cf316122182ce9a7f42ba2388`

- L19 [unknown] [册/参考/计算 | 受影响器件/网/PCB |
|---|---|---|---|

决策记录、五类 typed block 与复用合同见 [决策记录模板](decisions/decision-record.template.md) → `assets/decisions/decision-record.template.md` (ok)
- L19 [unknown] [记录、五类 typed block 与复用合同见 [决策记录模板](decisions/decision-record.template.md)、[模块复用合同](decisions/module-reuse-record.template.md) → `assets/decisions/module-reuse-record.template.md` (ok)
- L45 [unknown] [要沉淀的新经验还记录问题后果、原始观察与授权/脱敏状态，不自动把项目记录公开到Skill。

## 适用生产工艺

嘉立创打板/SMT任务按 [生产档案](manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)

### `assets/manufacturing-profile.md`

- 标题：本项目生产档案
- 行/字符/字节：42 / 1043 / 2265
- SHA-256：`515d0e3922663ec94508912afb344da19498327a125f150c6bc13627635b664b`

### `assets/pcb-delivery-checklist.md`

- 标题：PCB 交付检查清单（可复用）
- 行/字符/字节：59 / 2557 / 4749
- SHA-256：`94ac13b4b2fe9f08b90d9a4c9006ff4759273ac143aeb70905ef1f232ded0993`

### `assets/product-progress.md`

- 标题：从想法到实物：当前进度
- 行/字符/字节：28 / 539 / 1121
- SHA-256：`f4af0f66b1e277d35a8d2ced146851a2b3cbd9faa5f1bf407c2696dd2a0109b2`

### `assets/review-summary.md`

- 标题：阶段结论：<项目与版本>
- 行/字符/字节：25 / 435 / 933
- SHA-256：`ede1629ca23c2078a6de7d3d800b5df3684f6d33855d951b2de8434ca2fda5b8`

### `assets/routing-plan.md`

- 标题：布线计划（项目模板）
- 行/字符/字节：123 / 4017 / 6373
- SHA-256：`a080a63f69159f94f9449b79116112fc60a269975b34088abded902e555a4b7e`

- L5 [unknown] [位，不要填示例值或留空后当已完成。本模板是计划与证据清单，不是审批单：门禁是证据门，只有用户明确要求评审时才停下来等确认。

依据与判定见 [PCB布线策略](../references/pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L5 [unknown] [

依据与判定见 [PCB布线策略](../references/pcb-routing-strategy.md)；RT/PL 逐项方法见 [布线与回流细节](../references/pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L5 [unknown] [ategy.md)；RT/PL 逐项方法见 [布线与回流细节](../references/pcb-routing-details.md) 与 [PCB布局细节](../references/pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L5 [unknown] [CB布局细节](../references/pcb-placement-details.md)，本模板只引用编号。层数/铜厚/工艺能力按 [嘉立创PCB生产规则](../references/jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L5 [unknown] [数/铜厚/工艺能力按 [嘉立创PCB生产规则](../references/jlc-pcb-rules.md) 的当期订单条件核对；证据记录见 [证据与轻量记录](../references/evidence.md) → `references/evidence.md` (ok)
- L5 [unknown] [-pcb-rules.md) 的当期订单条件核对；证据记录见 [证据与轻量记录](../references/evidence.md)；工艺参数并入 [生产档案](manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)

### `assets/sourcing-summary.md`

- 标题：购料与制造交付卡
- 行/字符/字节：22 / 652 / 1482
- SHA-256：`eb9bc682cffe8e13d8bae6571fab77f3a70247da7f86c44213cd0fc96417c66d`

### `cases/dual-button-led-night-20261027/negative-direct-move/README.md`

- 标题：Negative case: direct LED2 +2 mm move from the first baseline
- 行/字符/字节：35 / 1632 / 1632
- SHA-256：`770ac56768dbce1596d147ee81d09c081a413c20dfc84b2af0edb22e40bb2d1e`

### `cases/mcu-i2c-s3-2026-10-26/README.md`

- 标题：真实案例：MCU + I²C 传感器小板（2026-10-26）
- 行/字符/字节：111 / 6873 / 9806
- SHA-256：`676cbb51ba342325eda5d3ee8e9072f6d9b48e0464074e76c231209b31f41899`

### `cases/photo-led-pcb-2026-10-26/README.md`

- 标题：真实案例：5V 光控 LED 板 PCB（2026-10-26）
- 行/字符/字节：106 / 6424 / 8784
- SHA-256：`b0485c307bd4f00e0004ed7462eebf03fea31df8a584ba354b011831e5056f7e`

### `cases/temp-alarm-2026-10-24/README.md`

- 标题：回归案例：室内温度报警小板（2026-10-24）
- 行/字符/字节：82 / 3464 / 5172
- SHA-256：`9eda65310c465994bd44e68d7de13beed0c9818cda4e07ca9d5f0c76c7cbe226`

- L77 [unknown] [T 可贴状态是当前值；
- 任何 EDA 命令在本次运行中被执行过（本案例只读证据）。

## 6. 文件

- [design-state.json](design-state.json) → `cases/temp-alarm-2026-10-24/design-state.json` (ok)
- L78 [unknown] [
## 6. 文件

- [design-state.json](design-state.json)：项目状态与门禁输入
- [waivers.json](waivers.json) → `cases/temp-alarm-2026-10-24/waivers.json` (ok)
- L79 [unknown] [tate.json)：项目状态与门禁输入
- [waivers.json](waivers.json)：G2 风格警告豁免
- [expected.json](expected.json) → `cases/temp-alarm-2026-10-24/expected.json` (ok)
- L80 [unknown] [ivers.json)：G2 风格警告豁免
- [expected.json](expected.json)：机器可读预期
- [change-log.md](change-log.md) → `cases/temp-alarm-2026-10-24/change-log.md` (ok)
- L81 [unknown] [json)：机器可读预期
- [change-log.md](change-log.md)：实战错误清单与修复过程
- [docs/test-plan.md](docs/test-plan.md) → `cases/temp-alarm-2026-10-24/docs/test-plan.md` (ok)

### `cases/temp-alarm-2026-10-24/change-log.md`

- 标题：实战错误清单与修复过程（temp-alarm，2026-10-24）
- 行/字符/字节：61 / 5237 / 7818
- SHA-256：`d9f3125acda81b00586e92c12db2c710e15c2a18c1a55f895bc0033d9b8da123`

### `cases/temp-alarm-2026-10-24/docs/test-plan.md`

- 标题：测试与使用步骤（无程序）
- 行/字符/字节：49 / 1373 / 2877
- SHA-256：`22d4b5c40a50acbfd90e91794d1fa4bfb2238de05a5c76557053c181260ab7df`

### `references/agent-collaboration.md`

- 标题：Agent协作契约
- 行/字符/字节：141 / 6257 / 14176
- SHA-256：`2c33f972019ecb89a58ffefeaed8ad6c5daa3665cf8f5bd0ce9b663c340178c8`

- L59 [unknown] [删除的对象确认不存在后再继续。
5. **禁止整批盲重试。** 整批重放会制造重复器件、重复导线，或把一次局部失败扩大成多处修改。工具层细节见 [EDA 执行](eda-execution.md) → `references/eda-execution.md` (ok)
- L59 [unknown] [ 整批重放会制造重复器件、重复导线，或把一次局部失败扩大成多处修改。工具层细节见 [EDA 执行](eda-execution.md) §4 与 [工具动作陷阱](tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L73 [unknown] [消关键网证明：DRC 数字下降不等于连接正确，仍需 G5 的 `net-path` 与保存重载证据。

方法细节与 2 层/4 层取舍见 [PCB 布线策略](pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L89 [unknown] [h` | 证据文件路径（相对项目根） |
| `sha256` | 文件哈希；大文件至少记录一次 |
| `role` | 对应门禁证据角色（见 [门禁定义](design-gates.md) → `references/design-gates.md` (ok)
- L95 [unknown] [当本次结论。
- 证据与最终板框/器件数/版本不一致时标 `STALE_EVIDENCE`，重跑受影响检查。
- 证据分层与计算记录要求见 [证据与轻量记录](evidence.md) → `references/evidence.md` (ok)
- L95 [unknown] [STALE_EVIDENCE`，重跑受影响检查。
- 证据分层与计算记录要求见 [证据与轻量记录](evidence.md)；落盘与解析陷阱见 [工具动作陷阱](tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L123 [unknown] [增删都有存在的文件；`pcb import-changes` 不会自动删除原理图已移除的器件，必须回读确认。
- 变更方法、等级、批次与回滚按 [变更影响决策](decisions/i01-change-impact.md) → `references/decisions/i01-change-impact.md` (ok)
- L140 [unknown] [独立准备、记录已知状态并给可恢复接续条件；不因为“生态优先”虚构内部云服务或工厂代开发能力。

## 门禁与工具陷阱入口

阶段退出证据门见 [门禁定义](design-gates.md) → `references/design-gates.md` (ok)
- L140 [unknown] [es.md)：G2 未过不导入 PCB、不布局；G3 与 G4 未过不布线；G5 未过不进入制造；G6 未过不声称可下单。动作级陷阱与正确命令见 [工具动作陷阱](tool-gotchas.md) → `references/tool-gotchas.md` (ok)

### `references/analog-rf-highspeed.md`

- 标题：模拟、射频与高速
- 行/字符/字节：32 / 1258 / 3218
- SHA-256：`f97e0a095818453ac6c59aea8021589b30837cd0736f42e99f1b5d2b7b5229c9`

- L3 [unknown] [、射频与高速

> 本文保留模拟/射频/高速的通用判断。分压、运放、ADC 驱动、基准、电流采样、4-20mA、桥式/RTD、天线等具体设计卡见 [设计卡库](design-cards/README.md) → `references/design-cards/README.md` (ok)

### `references/beginner-journey.md`

- 标题：没用过EDA的人也能开始
- 行/字符/字节：106 / 3851 / 9965
- SHA-256：`f289af686e1c1be3db391b24cdc54a09c9c836e88bc6a6b398756d31b63f95ff`

### `references/calculations/README.md`

- 标题：带条件的计算手册
- 行/字符/字节：11 / 348 / 576
- SHA-256：`a5ffa6d308cf718ef2cd3e61e3ebd7e1121831e62513968dccd38669dedeba07`

- L7 [unknown] [lculate.py`。

| 文档 | 文件 |
|---|---|
| 模拟采集、基准与 ADC：带条件的计算手册 | [analog-adc.md](analog-adc.md) → `references/calculations/analog-adc.md` (ok)
- L8 [unknown] [算手册 | [analog-adc.md](analog-adc.md) |
| 电池、续航与储能：带条件的计算手册 | [energy-battery.md](energy-battery.md) → `references/calculations/energy-battery.md` (ok)
- L9 [unknown] [energy-battery.md](energy-battery.md) |
| 互连、载流与传输线：带条件的计算手册 | [interconnect.md](interconnect.md) → `references/calculations/interconnect.md` (ok)
- L10 [unknown] [册 | [interconnect.md](interconnect.md) |
| 电源、瞬态与热：带条件的计算手册 | [power-thermal.md](power-thermal.md) → `references/calculations/power-thermal.md` (ok)

### `references/calculations/analog-adc.md`

- 标题：模拟采集、基准与 ADC：带条件的计算手册
- 行/字符/字节：591 / 29120 / 50992
- SHA-256：`a00360686cd4d54ea30025dd6374f7a9e7cfed45d47155176c4936aaefe4c98d`

- L9 [unknown] [ EDA、没有 PCB、没有实测波形；脚本输出 `board_verified:false`。
>
> **可执行脚本：** [`calculate.py`](../../scripts/calculate.py) → `scripts/calculate.py` (ok)
- L9 [unknown] [ts/calculate.py) 的 `divider`、`adc_settle`、`current_sense` 模式；[`rc_settle_sim.py`](../../scripts/rc_settle_sim.py) → `scripts/rc_settle_sim.py` (ok)
- L9 [unknown] [ipts/rc_settle_sim.py)（自研二阶 RC 数值模型，不是 SPICE）；[`assets/simulation/rc_sample.cir`](../../assets/simulation/rc_sample.cir) → `assets/simulation/rc_sample.cir` (ok)
- L414 [unknown] [点、标准器、温度、固件常数 | 改校准方案需改固件/测试 | 类 2 |

**替代分级（只用这四类，定义见 [replacement-classes.md](../selection/replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L423 [unknown] [回 404/系统异常**，未取得实时字段（记录见 `README.md`（仓库根，未随 Skill 安装） 与 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L440 [unknown] [，不猜测。商城有货 ≠ SMT 可贴 ≠ 已备料/已下单。

## 7. 制造与装配接口

完整路线见 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L465 [unknown] [/测试夹具、测试点、屏蔽罩是否包含，逐项写清。

**不一致处理：** 缺料/短装/多装/替代/ECO 按 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L588 [example] [C 号/价格/库存/MOQ/包装/交期/生命周期/SMT 状态为 `待查`。
- **需要其他文档补：** 分压/运放/ADC/基准的设计卡见 [ANA-01](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L588 [example] [文档补：** 分压/运放/ADC/基准的设计卡见 [ANA-01](../design-cards/analog/a01-divider.md)、[ANA-02](../design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L588 [example] [log/a01-divider.md)、[ANA-02](../design-cards/analog/a02-opamp-buffer.md)、[ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L588 [example] [/a02-opamp-buffer.md)、[ANA-04](../design-cards/analog/a04-adc-driver.md)、[ANA-05](../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L588 [example] [og/a04-adc-driver.md)、[ANA-05](../design-cards/analog/a05-vref.md)；电流采样见 [ANA-06](../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L588 [example] [05-vref.md)；电流采样见 [ANA-06](../design-cards/analog/a06-low-side-sense.md)/[ANA-07](../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L588 [example] [/[ANA-07](../design-cards/analog/a07-high-side-sense.md)；4–20 mA/桥/RTD 见 [ANA-08](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L588 [example] [sense.md)；4–20 mA/桥/RTD 见 [ANA-08](../design-cards/analog/a08-4-20ma.md)/[ANA-09](../design-cards/analog/a09-bridge.md) → `references/design-cards/analog/a09-bridge.md` (ok)
- L588 [example] [rds/analog/a08-4-20ma.md)/[ANA-09](../design-cards/analog/a09-bridge.md)/[ANA-10](../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L588 [example] [a09-bridge.md)/[ANA-10](../design-cards/analog/a10-rtd-thermistor.md)；局部布局见 [x09](../examples/x09-current-sense.md) → `references/examples/x09-current-sense.md` (ok)
- L588 [example] [analog/a10-rtd-thermistor.md)；局部布局见 [x09](../examples/x09-current-sense.md)/[x10](../examples/x10-4-20ma.md) → `references/examples/x10-4-20ma.md` (ok)

### `references/calculations/energy-battery.md`

- 标题：电池、续航与储能：带条件的计算手册
- 行/字符/字节：533 / 24772 / 42977
- SHA-256：`9fcf3e7fb96c33a8a0c21e4c509f6f6191cde9ab1d6768c0ccbb9ad6e741638d`

- L9 [unknown] [d_verified:false`、`lifetime_verified:false`。
>
> **可执行脚本：** [`power_budget.py`](../../scripts/power_budget.py) → `scripts/power_budget.py` (ok)
- L9 [unknown] [** [`power_budget.py`](../../scripts/power_budget.py)（电池输入侧状态预算）；[`calculate.py`](../../scripts/calculate.py) → `scripts/calculate.py` (ok)
- L304 [unknown] [必须在 4.2 V×25 A≈105 W、250 µs 的脉冲下不超 SOA；要按 FET 的 SOA/`Zth` 核对（见 [power-thermal.md](power-thermal.md) → `references/calculations/power-thermal.md` (ok)
- L362 [unknown] [ 电量计 | 型号、采样电阻、固件算法 | 换算法/校准 | 类 2 |

**替代分级（只用这四类，定义见 [replacement-classes.md](../selection/replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L371 [unknown] [回 404/系统异常**，未取得实时字段（记录见 `README.md`（仓库根，未随 Skill 安装） 与 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L388 [unknown] [的运输/仓储限制按当前承运商/法规核对，本文不写具体条款。

## 7. 制造与装配接口

完整路线见 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L413 [unknown] [清；不能把“PCB+SMT”当“整机含电池”。

**不一致处理：** 缺料/短装/多装/替代/ECO 按 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L532 [unknown] [页访问失败；所有 C 号/价格/库存/MOQ/包装/交期/生命周期/SMT 状态为 `待查`。
- **需要其他文档补：** 线性/开关充电见 [PWR-06](../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L532 [unknown] [要其他文档补：** 线性/开关充电见 [PWR-06](../design-cards/power/p06-linear-charger.md)/[PWR-07](../design-cards/power/p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L532 [unknown] [rger.md)/[PWR-07](../design-cards/power/p07-switching-charger.md)；1S 保护见 [PWR-08](../design-cards/power/p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L532 [unknown] [)；1S 保护见 [PWR-08](../design-cards/power/p08-battery-protection.md)；超级电容见 [PWR-14](../design-cards/power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L532 [unknown] [；超级电容见 [PWR-14](../design-cards/power/p14-supercap-backup.md)；多源/ORing 见 [PWR-05](../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L532 [unknown] [g 见 [PWR-05](../design-cards/power/p05-power-mux.md)；USB-C sink/source 见 [PWR-12](../design-cards/power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L532 [unknown] [md)；USB-C sink/source 见 [PWR-12](../design-cards/power/p12-usbc-sink.md)/[PWR-13](../design-cards/power/p13-usbc-source.md) → `references/design-cards/power/p13-usbc-source.md` (ok)

### `references/calculations/interconnect.md`

- 标题：互连、载流与传输线：带条件的计算手册
- 行/字符/字节：541 / 24635 / 44618
- SHA-256：`d250265714ad0a670183ff0be50a494f2b5035b4262881f54a0a46a10b256765`

- L9 [unknown] [/钻孔、没有 TDR/VNA/热成像；脚本输出 `board_verified:false`。
>
> **可执行脚本：** [`calculate.py`](../../scripts/calculate.py) → `scripts/calculate.py` (ok)
- L318 [unknown] [
| 时序/等长 | 网络类、公差、层 | 改规则/拓扑 | 类 3 |

**替代分级（只用这四类，定义见 [replacement-classes.md](../selection/replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L327 [unknown] [回 404/系统异常**，未取得实时字段（记录见 `README.md`（仓库根，未随 Skill 安装） 与 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L343 [unknown] [≠ 已备料/已下单。

## 7. 制造与装配接口（三条路线与对账）

完整流程、字段模板和异常矩阵见 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L540 [example] [库存/MOQ/包装/交期/生命周期/SMT 状态为 `待查`。
- **需要其他文档补：** 载流/回流布局见 [pcb-routing-details.md](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L540 [example] [他文档补：** 载流/回流布局见 [pcb-routing-details.md](../pcb-routing-details.md)；接口设计卡见 [I²C](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L540 [example] [-routing-details.md)；接口设计卡见 [I²C](../design-cards/interfaces/i01-i2c.md)、[RS-485](../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L540 [example] [ds/interfaces/i01-i2c.md)、[RS-485](../design-cards/interfaces/i07-rs485.md)、[CAN](../design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L540 [example] [s/interfaces/i07-rs485.md)、[CAN](../design-cards/interfaces/i08-can.md)、[USB 2.0](../design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L540 [example] [faces/i08-can.md)、[USB 2.0](../design-cards/interfaces/i09-usb-device.md)、[USB-C](../design-cards/interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)
- L540 [example] [09-usb-device.md)、[USB-C](../design-cards/interfaces/i10-usbc-data.md)、[Ethernet](../design-cards/interfaces/i11-ethernet.md) → `references/design-cards/interfaces/i11-ethernet.md` (ok)
- L540 [example] [-usbc-data.md)、[Ethernet](../design-cards/interfaces/i11-ethernet.md)；局部范例见 [x05](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L540 [example] [esign-cards/interfaces/i11-ethernet.md)；局部范例见 [x05](../examples/x05-i2c.md)、[x06](../examples/x06-rs485.md) → `references/examples/x06-rs485.md` (ok)
- L540 [example] [net.md)；局部范例见 [x05](../examples/x05-i2c.md)、[x06](../examples/x06-rs485.md)、[x07](../examples/x07-can.md) → `references/examples/x07-can.md` (ok)
- L540 [example] [s/x05-i2c.md)、[x06](../examples/x06-rs485.md)、[x07](../examples/x07-can.md)、[x08](../examples/x08-usbc.md) → `references/examples/x08-usbc.md` (ok)
- L540 [example] [amples/x07-can.md)、[x08](../examples/x08-usbc.md)；制造路线见 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)

### `references/calculations/power-thermal.md`

- 标题：电源、瞬态与热：带条件的计算手册
- 行/字符/字节：549 / 28326 / 49667
- SHA-256：`7232c183d1a03c15937161646e86e9cfa1def67f40f106196637719e1741cc0f`

- L9 [unknown] [板、没有热像仪/示波器实测**。脚本输出一律带 `board_verified:false`。
>
> **可执行脚本：** [`calculate.py`](../../scripts/calculate.py) → `scripts/calculate.py` (ok)
- L9 [unknown] [(../../scripts/calculate.py) 的 `buck`、`boost`、`ldo`、`wire` 模式；[`power_budget.py`](../../scripts/power_budget.py) → `scripts/power_budget.py` (ok)
- L74 [unknown] [电容储能 `E = ½CV²`。
- 线缆/走线：`Vdrop = I·R`，`Ploss = I²R`；R 随温度上升（见 [interconnect.md](interconnect.md) → `references/calculations/interconnect.md` (ok)
- L110 [unknown] [：PWR-S09 §10.2.2.2 对 TPS63802 建议“饱和电流比计算峰值高 20%”；这是**该器件的建议**，不是所有电感的通用规则（见 [F12](../failures/f12-inductor-saturation.md) → `references/failures/f12-inductor-saturation.md` (ok)
- L305 [unknown] [的 SOA 是否足够、线缆电感导致的振铃、并联均流、重复插拔累积、`VGS` 瞬态；没有具体型号的 SOA 曲线，不能给出“能承受多少安”的保证值（见 [F13](../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L379 [unknown] [ `PLIM` | 同封装同引脚：类 2；不同封装/改拓扑：类 3 |

**替代分级只用这四类**（定义见 [replacement-classes.md](../selection/replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L388 [unknown] [回 404/系统异常**，未取得实时字段（记录见 `README.md`（仓库根，未随 Skill 安装） 与 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L405 [unknown] [7. 制造与装配接口

本文的计算结果会直接改变制造文件和装配方式。完整的三条路线、字段、对账和异常处理见 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L430 [unknown] [项写清；不能把“PCB 价格”当“整机成本”。

**不一致处理：** 缺料/短装/多装/替代/ECO 按 [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L546 [unknown] [格/库存/MOQ/包装/交期/生命周期/SMT 状态均为 `待查`。
- **需要其他文档补：** 环路补偿/稳定性见具体控制器手册与 [PWR-02 设计卡](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L546 [unknown] [环路补偿/稳定性见具体控制器手册与 [PWR-02 设计卡](../design-cards/power/p02-buck.md)；热插拔拓扑见 [PWR-10](../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L546 [unknown] [ck.md)；热插拔拓扑见 [PWR-10](../design-cards/power/p10-hot-swap.md)；保险/eFuse 见 [PWR-11](../design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L546 [unknown] [ot-swap.md)；保险/eFuse 见 [PWR-11](../design-cards/power/p11-efuse.md)；电感饱和失效见 [F12](../failures/f12-inductor-saturation.md) → `references/failures/f12-inductor-saturation.md` (ok)
- L546 [unknown] [se.md)；电感饱和失效见 [F12](../failures/f12-inductor-saturation.md)；MOSFET SOA 失效见 [F13](../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L548 [unknown] [ion.md)；MOSFET SOA 失效见 [F13](../failures/f13-mosfet-soa.md)。

完整热指标与测量纪律见 [热专题](../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/client-compatibility.md`

- 标题：客户端兼容与首次接通
- 行/字符/字节：126 / 5384 / 8596
- SHA-256：`29334756026d6ac002588dec5d0ac37d927afcd331a0d7a1f6294c13cf829a74`

### `references/common-hardware/README.md`

- 标题：常用硬件：从用户话术到具体电路
- 行/字符/字节：109 / 8675 / 14487
- SHA-256：`d99c0347a1138162da80a4c3e3a316d616c5d00a47f92d49dae0f8141db8d773`

- L5 [unknown] [液位/流量、测电压电流、供电入口、LDO/Buck/Boost、电池、主控、总线、驱动、显示、声音、按键、无线、RTC、隔离。
>
> 它不替代 [设计卡库](../design-cards/README.md) → `references/design-cards/README.md` (ok)
- L5 [unknown] [声音、按键、无线、RTC、隔离。
>
> 它不替代 [设计卡库](../design-cards/README.md) 的通用电气理论，也不替代 [工程深潜](../engineering-deepdives/README.md) → `references/engineering-deepdives/README.md` (ok)
- L19 [unknown] [断 | 读 |
|---|---|---|
| “测水温/室温/电池温度，±1 °C 够不够” | 介质、温区、响应、探头安装、是否校准 | [A1 NTC](a-environment.md#a1-ntc-温度测量) → `references/common-hardware/a-environment.md` (ok) #a1-ntc-温度测量 ok
- L19 [unknown] [1 °C 够不够” | 介质、温区、响应、探头安装、是否校准 | [A1 NTC](a-environment.md#a1-ntc-温度测量)、[A2 数字温度](a-environment.md#a2-数字温度传感器) → `references/common-hardware/a-environment.md` (ok) #a2-数字温度传感器 ok
- L19 [unknown] [TC](a-environment.md#a1-ntc-温度测量)、[A2 数字温度](a-environment.md#a2-数字温度传感器)、[A3 RTD](a-environment.md#a3-铂电阻测温) → `references/common-hardware/a-environment.md` (ok) #a3-铂电阻测温 ok
- L20 [unknown] [ RTD](a-environment.md#a3-铂电阻测温) |
| “测炉温/火焰/高温表面” | 热电偶类型、冷端、补偿导线、接地 | [A4 热电偶](a-environment.md#a4-热电偶测温) → `references/common-hardware/a-environment.md` (ok) #a4-热电偶测温 ok
- L21 [unknown] [电偶](a-environment.md#a4-热电偶测温) |
| “测室内温湿度/做气象站” | RH 精度定义、气路、结露、长期漂移 | [A5 温湿度](a-environment.md#a5-温湿度传感器) → `references/common-hardware/a-environment.md` (ok) #a5-温湿度传感器 ok
- L22 [unknown] [ 温湿度](a-environment.md#a5-温湿度传感器) |
| “测气压/高度/楼层” | 绝压/差压、`P0`、噪声、天气漂移 | [A6 气压](a-environment.md#a6-气压与高度估算) → `references/common-hardware/a-environment.md` (ok) #a6-气压与高度估算 ok
- L23 [unknown] [-environment.md#a6-气压与高度估算) |
| “测空气质量/CO2/VOC/甲醛” | 目标气体、舒适度还是安全报警、认证 | [A7 气体](a-environment.md#a7-空气质量与气体检测) → `references/common-hardware/a-environment.md` (ok) #a7-空气质量与气体检测 ok
- L24 [unknown] [environment.md#a7-空气质量与气体检测) |
| “感应有人/手势/接近/测距” | 目标、距离、环境光、静止/运动、安装 | [B5 PIR](b-optics.md#b5-pir-人体检测) → `references/common-hardware/b-optics.md` (ok) #b5-pir-人体检测 ok
- L24 [unknown] [“感应有人/手势/接近/测距” | 目标、距离、环境光、静止/运动、安装 | [B5 PIR](b-optics.md#b5-pir-人体检测)、[B6 ToF](b-optics.md#b6-tof-测距) → `references/common-hardware/b-optics.md` (ok) #b6-tof-测距 ok
- L24 [unknown] [运动、安装 | [B5 PIR](b-optics.md#b5-pir-人体检测)、[B6 ToF](b-optics.md#b6-tof-测距)、[B7 超声](b-optics.md#b7-超声测距) → `references/common-hardware/b-optics.md` (ok) #b7-超声测距 ok
- L24 [unknown] [5-pir-人体检测)、[B6 ToF](b-optics.md#b6-tof-测距)、[B7 超声](b-optics.md#b7-超声测距)、[B8 毫米波](b-optics.md#b8-毫米波存在感知) → `references/common-hardware/b-optics.md` (ok) #b8-毫米波存在感知 ok
- L25 [unknown] [毫米波](b-optics.md#b8-毫米波存在感知) |
| “测倾斜/振动/转动/角度/转速” | 单轴/多轴、量程、带宽、安装基准 | [C1 加速度](c-motion.md#c1-加速度计) → `references/common-hardware/c-motion.md` (ok) #c1-加速度计 ok
- L25 [unknown] [
| “测倾斜/振动/转动/角度/转速” | 单轴/多轴、量程、带宽、安装基准 | [C1 加速度](c-motion.md#c1-加速度计)、[C2 IMU](c-motion.md#c2-陀螺仪与-imu) → `references/common-hardware/c-motion.md` (ok) #c2-陀螺仪与-imu ok
- L25 [unknown] [宽、安装基准 | [C1 加速度](c-motion.md#c1-加速度计)、[C2 IMU](c-motion.md#c2-陀螺仪与-imu)、[C5 编码器](c-motion.md#c5-旋转编码器) → `references/common-hardware/c-motion.md` (ok) #c5-旋转编码器 ok
- L25 [unknown] [c1-加速度计)、[C2 IMU](c-motion.md#c2-陀螺仪与-imu)、[C5 编码器](c-motion.md#c5-旋转编码器)、[C6 转速](c-motion.md#c6-转速检测) → `references/common-hardware/c-motion.md` (ok) #c6-转速检测 ok
- L26 [unknown] [、[C6 转速](c-motion.md#c6-转速检测) |
| “称重/测压力/液位/流量/土壤湿度” | 量程、介质、安装、校准、过载 | [D1 称重](d-force.md#d1-称重与应变桥) → `references/common-hardware/d-force.md` (ok) #d1-称重与应变桥 ok
- L26 [unknown] [|
| “称重/测压力/液位/流量/土壤湿度” | 量程、介质、安装、校准、过载 | [D1 称重](d-force.md#d1-称重与应变桥)、[D2 压力](d-force.md#d2-模拟压力传感器) → `references/common-hardware/d-force.md` (ok) #d2-模拟压力传感器 ok
- L26 [unknown] [质、安装、校准、过载 | [D1 称重](d-force.md#d1-称重与应变桥)、[D2 压力](d-force.md#d2-模拟压力传感器)、[D4 液位](d-force.md#d4-液位检测) → `references/common-hardware/d-force.md` (ok) #d4-液位检测 ok
- L26 [unknown] [.md#d1-称重与应变桥)、[D2 压力](d-force.md#d2-模拟压力传感器)、[D4 液位](d-force.md#d4-液位检测)、[D5 土壤](d-force.md#d5-土壤与介质湿度) → `references/common-hardware/d-force.md` (ok) #d5-土壤与介质湿度 ok
- L26 [unknown] [md#d2-模拟压力传感器)、[D4 液位](d-force.md#d4-液位检测)、[D5 土壤](d-force.md#d5-土壤与介质湿度)、[D6 流量](d-force.md#d6-脉冲流量计) → `references/common-hardware/d-force.md` (ok) #d6-脉冲流量计 ok
- L27 [unknown] [介质湿度)、[D6 流量](d-force.md#d6-脉冲流量计) |
| “测电压/电流/功率/电量” | 共模、方向、隔离、量程、校准 | [E1 电压](e-measurement.md#e1-电压采样) → `references/common-hardware/e-measurement.md` (ok) #e1-电压采样 ok
- L27 [unknown] [ |
| “测电压/电流/功率/电量” | 共模、方向、隔离、量程、校准 | [E1 电压](e-measurement.md#e1-电压采样)、[E3 高侧](e-measurement.md#e3-高侧电流采样) → `references/common-hardware/e-measurement.md` (ok) #e3-高侧电流采样 ok
- L27 [unknown] [准 | [E1 电压](e-measurement.md#e1-电压采样)、[E3 高侧](e-measurement.md#e3-高侧电流采样)、[E4 双向](e-measurement.md#e4-双向电流测量) → `references/common-hardware/e-measurement.md` (ok) #e4-双向电流测量 ok
- L27 [unknown] [)、[E3 高侧](e-measurement.md#e3-高侧电流采样)、[E4 双向](e-measurement.md#e4-双向电流测量)、[E5 隔离](e-measurement.md#e5-隔离电流检测) → `references/common-hardware/e-measurement.md` (ok) #e5-隔离电流检测 ok
- L27 [unknown] [)、[E4 双向](e-measurement.md#e4-双向电流测量)、[E5 隔离](e-measurement.md#e5-隔离电流检测)、[E6 电量](e-measurement.md#e6-电池电量估算) → `references/common-hardware/e-measurement.md` (ok) #e6-电池电量估算 ok
- L28 [unknown] [surement.md#e6-电池电量估算) |
| “USB 供电/Type-C/PD/直流插座/防反接” | 角色、线缆、功率、保护链 | [F1 USB](f-input-protection.md#f1-usb-供电) → `references/common-hardware/f-input-protection.md` (ok) #f1-usb-供电 ok
- L28 [unknown] [流插座/防反接” | 角色、线缆、功率、保护链 | [F1 USB](f-input-protection.md#f1-usb-供电)、[F2 USB-C 5V](f-input-protection.md#f2-usb-c-固定低压取电) → `references/common-hardware/f-input-protection.md` (ok) #f2-usb-c-固定低压取电 ok
- L28 [unknown] [ection.md#f1-usb-供电)、[F2 USB-C 5V](f-input-protection.md#f2-usb-c-固定低压取电)、[F3 PD](f-input-protection.md#f3-usb-pd-电源输入) → `references/common-hardware/f-input-protection.md` (ok) #f3-usb-pd-电源输入 ok
- L28 [unknown] [tection.md#f2-usb-c-固定低压取电)、[F3 PD](f-input-protection.md#f3-usb-pd-电源输入)、[F5 反接](f-input-protection.md#f5-反接保护) → `references/common-hardware/f-input-protection.md` (ok) #f5-反接保护 ok
- L29 [unknown] [rotection.md#f5-反接保护) |
| “3.3 V/5 V 电源、升压、负压、隔离电源” | 输入/输出范围、负载、纹波、热 | [G1 LDO](g-power-conversion.md#g1-ldo) → `references/common-hardware/g-power-conversion.md` (ok) #g1-ldo ok
- L29 [unknown] [、升压、负压、隔离电源” | 输入/输出范围、负载、纹波、热 | [G1 LDO](g-power-conversion.md#g1-ldo)、[G2 Buck](g-power-conversion.md#g2-buck) → `references/common-hardware/g-power-conversion.md` (ok) #g2-buck ok
- L29 [unknown] [g-power-conversion.md#g1-ldo)、[G2 Buck](g-power-conversion.md#g2-buck)、[G3 Boost](g-power-conversion.md#g3-boost) → `references/common-hardware/g-power-conversion.md` (ok) #g3-boost ok
- L29 [unknown] [g-power-conversion.md#g2-buck)、[G3 Boost](g-power-conversion.md#g3-boost)、[G5 负压](g-power-conversion.md#g5-反相电源) → `references/common-hardware/g-power-conversion.md` (ok) #g5-反相电源 ok
- L29 [unknown] [t](g-power-conversion.md#g3-boost)、[G5 负压](g-power-conversion.md#g5-反相电源)、[G6 隔离](g-power-conversion.md#g6-隔离-dcdc) → `references/common-hardware/g-power-conversion.md` (ok) #g6-隔离-dcdc ok
- L30 [unknown] [ersion.md#g6-隔离-dcdc) |
| “电池供电/充电/续航/低功耗” | 化学体系、串数、充电、保护、电源路径、睡眠预算 | [H1 一次电池](h-battery.md#h1-一次电池) → `references/common-hardware/h-battery.md` (ok) #h1-一次电池 ok
- L30 [unknown] [供电/充电/续航/低功耗” | 化学体系、串数、充电、保护、电源路径、睡眠预算 | [H1 一次电池](h-battery.md#h1-一次电池)、[H2 充电](h-battery.md#h2-单节锂电池充电) → `references/common-hardware/h-battery.md` (ok) #h2-单节锂电池充电 ok
- L30 [unknown] [睡眠预算 | [H1 一次电池](h-battery.md#h1-一次电池)、[H2 充电](h-battery.md#h2-单节锂电池充电)、[H3 电源路径](h-battery.md#h3-带电源路径管理的充电) → `references/common-hardware/h-battery.md` (ok) #h3-带电源路径管理的充电 ok
- L30 [unknown] [)、[H2 充电](h-battery.md#h2-单节锂电池充电)、[H3 电源路径](h-battery.md#h3-带电源路径管理的充电)、[H8 低电量](h-battery.md#h8-低电量与维护) → `references/common-hardware/h-battery.md` (ok) #h8-低电量与维护 ok
- L31 [unknown] [](h-battery.md#h8-低电量与维护) |
| “选个单片机/最小系统/下载/看门狗” | 资源、供电、时钟、启动、调试、存储 | [I1 低成本](i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L31 [unknown] [个单片机/最小系统/下载/看门狗” | 资源、供电、时钟、启动、调试、存储 | [I1 低成本](i-mcu.md#i1-低成本基础控制)、[I2 通用 MCU](i-mcu.md#i2-通用-mcu) → `references/common-hardware/i-mcu.md` (ok) #i2-通用-mcu ok
- L31 [unknown] [调试、存储 | [I1 低成本](i-mcu.md#i1-低成本基础控制)、[I2 通用 MCU](i-mcu.md#i2-通用-mcu)、[I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组) → `references/common-hardware/i-mcu.md` (ok) #i3-无线-mcu-与模组 ok
- L31 [unknown] [控制)、[I2 通用 MCU](i-mcu.md#i2-通用-mcu)、[I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组)、[I4 模拟主控](i-mcu.md#i4-模拟能力较强的主控) → `references/common-hardware/i-mcu.md` (ok) #i4-模拟能力较强的主控 ok
- L31 [unknown] [mcu)、[I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组)、[I4 模拟主控](i-mcu.md#i4-模拟能力较强的主控)、[I7 下载](i-mcu.md#i7-下载与自动进入启动模式) → `references/common-hardware/i-mcu.md` (ok) #i7-下载与自动进入启动模式 ok
- L32 [unknown] [进入启动模式) |
| “I2C/SPI/UART/RS232/RS485/CAN/USB/网口” | 距离、速率、共模、端接、隔离、协议 | [J1 I²C](j-buses.md#j1-i²c-外设) → `references/common-hardware/j-buses.md` (ok) #j1-i²c-外设 ok
- L32 [unknown] [S485/CAN/USB/网口” | 距离、速率、共模、端接、隔离、协议 | [J1 I²C](j-buses.md#j1-i²c-外设)、[J5 RS-485](j-buses.md#j5-rs-485) → `references/common-hardware/j-buses.md` (ok) #j5-rs-485 ok
- L32 [unknown] [隔离、协议 | [J1 I²C](j-buses.md#j1-i²c-外设)、[J5 RS-485](j-buses.md#j5-rs-485)、[J6 CAN](j-buses.md#j6-can) → `references/common-hardware/j-buses.md` (ok) #j6-can ok
- L32 [unknown] [j1-i²c-外设)、[J5 RS-485](j-buses.md#j5-rs-485)、[J6 CAN](j-buses.md#j6-can)、[J7 USB](j-buses.md#j7-usb-数据接口) → `references/common-hardware/j-buses.md` (ok) #j7-usb-数据接口 ok
- L32 [unknown] [#j5-rs-485)、[J6 CAN](j-buses.md#j6-can)、[J7 USB](j-buses.md#j7-usb-数据接口)、[J8 以太网](j-buses.md#j8-以太网) → `references/common-hardware/j-buses.md` (ok) #j8-以太网 ok
- L33 [unknown] [j8-以太网) |
| “控制继电器/电磁阀/电机/风扇/舵机/加热器” | 负载类型、启动/堵转、续流、默认态、热；风扇测速还要看 C6 | [K3 继电器](k-drive.md#k3-继电器) → `references/common-hardware/k-drive.md` (ok) #k3-继电器 ok
- L33 [unknown] [扇/舵机/加热器” | 负载类型、启动/堵转、续流、默认态、热；风扇测速还要看 C6 | [K3 继电器](k-drive.md#k3-继电器)、[K4 电磁阀](k-drive.md#k4-电磁阀与电磁铁) → `references/common-hardware/k-drive.md` (ok) #k4-电磁阀与电磁铁 ok
- L33 [unknown] [扇测速还要看 C6 | [K3 继电器](k-drive.md#k3-继电器)、[K4 电磁阀](k-drive.md#k4-电磁阀与电磁铁)、[K5 直流电机](k-drive.md#k5-直流电机) → `references/common-hardware/k-drive.md` (ok) #k5-直流电机 ok
- L33 [unknown] [.md#k3-继电器)、[K4 电磁阀](k-drive.md#k4-电磁阀与电磁铁)、[K5 直流电机](k-drive.md#k5-直流电机)、[K7 风扇](k-drive.md#k7-风扇) → `references/common-hardware/k-drive.md` (ok) #k7-风扇 ok
- L33 [unknown] [ve.md#k4-电磁阀与电磁铁)、[K5 直流电机](k-drive.md#k5-直流电机)、[K7 风扇](k-drive.md#k7-风扇)、[K8 舵机](k-drive.md#k8-舵机) → `references/common-hardware/k-drive.md` (ok) #k8-舵机 ok
- L33 [unknown] [](k-drive.md#k5-直流电机)、[K7 风扇](k-drive.md#k7-风扇)、[K8 舵机](k-drive.md#k8-舵机)、[C6 转速](c-motion.md#c6-转速检测) → `references/common-hardware/c-motion.md` (ok) #c6-转速检测 ok
- L34 [unknown] [ion.md#c6-转速检测) |
| “门窗开合/干簧/霍尔/纽扣电池提醒” | 磁体-气隙、安装偏差、CR2032 脉冲、BLE 占空比 | [C4 霍尔](c-motion.md#c4-霍尔开关与线性霍尔) → `references/common-hardware/c-motion.md` (ok) #c4-霍尔开关与线性霍尔 ok
- L34 [unknown] [提醒” | 磁体-气隙、安装偏差、CR2032 脉冲、BLE 占空比 | [C4 霍尔](c-motion.md#c4-霍尔开关与线性霍尔)、[C7 限位/接近](c-motion.md#c7-限位与接近开关) → `references/common-hardware/c-motion.md` (ok) #c7-限位与接近开关 ok
- L34 [unknown] [ | [C4 霍尔](c-motion.md#c4-霍尔开关与线性霍尔)、[C7 限位/接近](c-motion.md#c7-限位与接近开关)、[H1 一次电池](h-battery.md#h1-一次电池) → `references/common-hardware/h-battery.md` (ok) #h1-一次电池 ok
- L34 [unknown] [线性霍尔)、[C7 限位/接近](c-motion.md#c7-限位与接近开关)、[H1 一次电池](h-battery.md#h1-一次电池)、[H7 低功耗](h-battery.md#h7-低功耗外围) → `references/common-hardware/h-battery.md` (ok) #h7-低功耗外围 ok
- L34 [unknown] [限位与接近开关)、[H1 一次电池](h-battery.md#h1-一次电池)、[H7 低功耗](h-battery.md#h7-低功耗外围)、[M2 BLE](m-wireless-time.md#m2-ble) → `references/common-hardware/m-wireless-time.md` (ok) #m2-ble ok
- L34 [unknown] [[H7 低功耗](h-battery.md#h7-低功耗外围)、[M2 BLE](m-wireless-time.md#m2-ble)，组合见 [04 门窗提醒](applications/04-door-window-reminder.md) → `references/common-hardware/applications/04-door-window-reminder.md` (ok)
- L35 [unknown] [2/无线主控 + 2.4 寸彩屏 + 蜂鸣器” | 屏带宽/帧缓冲、ESP32 峰值电流、供电要 Buck 不是 200 mA LDO | [I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组) → `references/common-hardware/i-mcu.md` (ok) #i3-无线-mcu-与模组 ok
- L35 [unknown] [、ESP32 峰值电流、供电要 Buck 不是 200 mA LDO | [I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组)、[L4 TFT](l-hmi.md#l4-tft-显示) → `references/common-hardware/l-hmi.md` (ok) #l4-tft-显示 ok
- L35 [unknown] [A LDO | [I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组)、[L4 TFT](l-hmi.md#l4-tft-显示)、[L8 蜂鸣器](l-hmi.md#l8-蜂鸣器) → `references/common-hardware/l-hmi.md` (ok) #l8-蜂鸣器 ok
- L35 [unknown] [md#i3-无线-mcu-与模组)、[L4 TFT](l-hmi.md#l4-tft-显示)、[L8 蜂鸣器](l-hmi.md#l8-蜂鸣器)、[A5 温湿度](a-environment.md#a5-温湿度传感器) → `references/common-hardware/a-environment.md` (ok) #a5-温湿度传感器 ok
- L35 [unknown] [tft-显示)、[L8 蜂鸣器](l-hmi.md#l8-蜂鸣器)、[A5 温湿度](a-environment.md#a5-温湿度传感器)、[F2 USB-C](f-input-protection.md#f2-usb-c-固定低压取电) → `references/common-hardware/f-input-protection.md` (ok) #f2-usb-c-固定低压取电 ok
- L35 [unknown] [ronment.md#a5-温湿度传感器)、[F2 USB-C](f-input-protection.md#f2-usb-c-固定低压取电)、[G2 Buck](g-power-conversion.md#g2-buck) → `references/common-hardware/g-power-conversion.md` (ok) #g2-buck ok
- L35 [unknown] [ction.md#f2-usb-c-固定低压取电)、[G2 Buck](g-power-conversion.md#g2-buck)，变体见 [03 温湿度显示](applications/03-humidity-display.md) → `references/common-hardware/applications/03-humidity-display.md` (ok)
- L36 [unknown] [isplay.md) |
| “加个屏幕/数码管/OLED/触摸/按键/旋钮/蜂鸣器/喇叭” | 接口、供电、亮度/声压、面板/开窗、资源 | [L2 数码管](l-hmi.md#l2-数码管与矩阵显示) → `references/common-hardware/l-hmi.md` (ok) #l2-数码管与矩阵显示 ok
- L36 [unknown] [摸/按键/旋钮/蜂鸣器/喇叭” | 接口、供电、亮度/声压、面板/开窗、资源 | [L2 数码管](l-hmi.md#l2-数码管与矩阵显示)、[L3 OLED](l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok
- L36 [unknown] [开窗、资源 | [L2 数码管](l-hmi.md#l2-数码管与矩阵显示)、[L3 OLED](l-hmi.md#l3-oled-与液晶模块)、[L4 TFT](l-hmi.md#l4-tft-显示) → `references/common-hardware/l-hmi.md` (ok) #l4-tft-显示 ok
- L36 [unknown] [-数码管与矩阵显示)、[L3 OLED](l-hmi.md#l3-oled-与液晶模块)、[L4 TFT](l-hmi.md#l4-tft-显示)、[L5 触摸](l-hmi.md#l5-触摸屏与电容触摸) → `references/common-hardware/l-hmi.md` (ok) #l5-触摸屏与电容触摸 ok
- L36 [unknown] [3-oled-与液晶模块)、[L4 TFT](l-hmi.md#l4-tft-显示)、[L5 触摸](l-hmi.md#l5-触摸屏与电容触摸)、[L8 蜂鸣器](l-hmi.md#l8-蜂鸣器) → `references/common-hardware/l-hmi.md` (ok) #l8-蜂鸣器 ok
- L37 [unknown] [ |
| “Wi-Fi/BLE/Sub-GHz/4G/GNSS/RTC/NFC/隔离” | 频段/地区、天线、峰值电流、认证、时间保持 | [M1 Wi-Fi](m-wireless-time.md#m1-wi-fi) → `references/common-hardware/m-wireless-time.md` (ok) #m1-wi-fi ok
- L37 [unknown] [FC/隔离” | 频段/地区、天线、峰值电流、认证、时间保持 | [M1 Wi-Fi](m-wireless-time.md#m1-wi-fi)、[M2 BLE](m-wireless-time.md#m2-ble) → `references/common-hardware/m-wireless-time.md` (ok) #m2-ble ok
- L37 [unknown] [Fi](m-wireless-time.md#m1-wi-fi)、[M2 BLE](m-wireless-time.md#m2-ble)、[M3 Sub-GHz](m-wireless-time.md#m3-sub-ghz-无线) → `references/common-hardware/m-wireless-time.md` (ok) #m3-sub-ghz-无线 ok
- L37 [unknown] [-wireless-time.md#m2-ble)、[M3 Sub-GHz](m-wireless-time.md#m3-sub-ghz-无线)、[M6 RTC](m-wireless-time.md#m6-rtc) → `references/common-hardware/m-wireless-time.md` (ok) #m6-rtc ok
- L37 [unknown] [wireless-time.md#m3-sub-ghz-无线)、[M6 RTC](m-wireless-time.md#m6-rtc)、[M7 NFC/RFID](m-wireless-time.md#m7-身份与标签读取) → `references/common-hardware/m-wireless-time.md` (ok) #m7-身份与标签读取 ok
- L37 [unknown] [](m-wireless-time.md#m6-rtc)、[M7 NFC/RFID](m-wireless-time.md#m7-身份与标签读取)、[M8 隔离](m-wireless-time.md#m8-隔离与数字隔离器) → `references/common-hardware/m-wireless-time.md` (ok) #m8-隔离与数字隔离器 ok
- L43 [unknown] [# 2. 13 个组

| 组 | 文件 | 主题 |
|---|---|---|
| A 温度、湿度与环境传感 | [a-environment.md](a-environment.md) → `references/common-hardware/a-environment.md` (ok)
- L44 [unknown] [ NTC、A2 数字温度、A3 RTD、A4 热电偶、A5 温湿度、A6 气压、A7 气体 |
| B 光、接近、距离与人体检测 | [b-optics.md](b-optics.md) → `references/common-hardware/b-optics.md` (ok)
- L45 [unknown] [电二极管、B3 反射、B4 对射/槽型、B5 PIR、B6 ToF、B7 超声、B8 毫米波 |
| C 运动、位置、转速与角度 | [c-motion.md](c-motion.md) → `references/common-hardware/c-motion.md` (ok)
- L46 [unknown] [加速度、C2 IMU、C3 磁力计、C4 霍尔、C5 编码器、C6 转速、C7 限位/接近 |
| D 力、重量、压力、液位与流量 | [d-force.md](d-force.md) → `references/common-hardware/d-force.md` (ok)
- L47 [unknown] [ 模拟压力、D3 数字压力、D4 液位、D5 土壤、D6 脉冲流量、D7 模拟量接口 |
| E 电压、电流与电能测量 | [e-measurement.md](e-measurement.md) → `references/common-hardware/e-measurement.md` (ok)
- L48 [unknown] [E2 低侧、E3 高侧、E4 双向、E5 隔离、E6 电量、E7 多通道 |
| F 常用低压供电入口与保护 | [f-input-protection.md](f-input-protection.md) → `references/common-hardware/f-input-protection.md` (ok)
- L49 [unknown] [D、F4 直流端子、F5 反接、F6 过流、F7 过压、F8 浪涌 |
| G LDO、降压、升压与反相电源 | [g-power-conversion.md](g-power-conversion.md) → `references/common-hardware/g-power-conversion.md` (ok)
- L50 [unknown] [Boost、G4 Buck-Boost、G5 负压、G6 隔离、G7 负载开关、G8 多路 |
| H 电池、充电与低功耗设备 | [h-battery.md](h-battery.md) → `references/common-hardware/h-battery.md` (ok)
- L51 [unknown] [ 一次电池、H2 充电、H3 电源路径、H4 保护、H5 多节、H6 共存、H7 低功耗、H8 低电量 |
| I 常见主控与最小系统 | [i-mcu.md](i-mcu.md) → `references/common-hardware/i-mcu.md` (ok)
- L52 [unknown] [本、I2 通用、I3 无线、I4 模拟、I5 时钟、I6 复位/看门狗、I7 下载、I8 存储 |
| J 数字总线与常见有线通信 | [j-buses.md](j-buses.md) → `references/common-hardware/j-buses.md` (ok)
- L53 [unknown] [3 UART、J4 RS-232、J5 RS-485、J6 CAN、J7 USB、J8 以太网 |
| K 开关、继电器与电机负载 | [k-drive.md](k-drive.md) → `references/common-hardware/k-drive.md` (ok)
- L54 [unknown] [高侧、K3 继电器、K4 电磁阀、K5 直流电机、K6 步进、K7 风扇、K8 舵机、K9 加热器 |
| L 显示、声音、按键与交互 | [l-hmi.md](l-hmi.md) → `references/common-hardware/l-hmi.md` (ok)
- L55 [unknown] [L4 TFT、L5 触摸、L6 按键、L7 旋钮、L8 蜂鸣器、L9 扬声器 |
| M 无线、时间与常用功能模块 | [m-wireless-time.md](m-wireless-time.md) → `references/common-hardware/m-wireless-time.md` (ok)
- L63 [unknown] [成等级。

| 用户需求 | 文件 | 主要组合 |
|---|---|---|
| 温度过高报警 | [01-temperature-alarm.md](applications/01-temperature-alarm.md) → `references/common-hardware/applications/01-temperature-alarm.md` (ok)
- L64 [unknown] [mperature-alarm.md) | A1/A2 + I1 + L8 + K1 + F1 |
| 自动调速风扇 | [02-fan-control.md](applications/02-fan-control.md) → `references/common-hardware/applications/02-fan-control.md` (ok)
- L65 [unknown] [02-fan-control.md) | A1/A2 + K7 + C6 + G2 |
| 桌面温湿度显示 | [03-humidity-display.md](applications/03-humidity-display.md) → `references/common-hardware/applications/03-humidity-display.md` (ok)
- L66 [unknown] [ity-display.md) | A5 + L3 + I1/I3 + J1 |
| 电池门窗提醒 | [04-door-window-reminder.md](applications/04-door-window-reminder.md) → `references/common-hardware/applications/04-door-window-reminder.md` (ok)
- L67 [background] [window-reminder.md) | C4/C7 + H1/H2/H7 + M2 |
| 简易电子秤 | [05-electronic-scale.md](applications/05-electronic-scale.md) → `references/common-hardware/applications/05-electronic-scale.md` (ok)
- L68 [unknown] [NA-09 + I1 + L3 + F2/G1（E1/E7 仅电池/NTC 可选） |
| 水箱液位提醒 | [06-water-level-alarm.md](applications/06-water-level-alarm.md) → `references/common-hardware/applications/06-water-level-alarm.md` (ok)
- L69 [unknown] [ater-level-alarm.md) | D4 + D7 + K3/K7 + L8 |
| 设备电流监测 | [07-current-monitor.md](applications/07-current-monitor.md) → `references/common-hardware/applications/07-current-monitor.md` (ok)
- L70 [unknown] [.md) | E3/E4 + ANA-07 + I4 + J5 |
| RS-485 温湿度节点（无 4–20 mA） | [08-rs485-node.md](applications/08-rs485-node.md) → `references/common-hardware/applications/08-rs485-node.md` (ok)
- L71 [unknown] [5/F7 + M8（默认隔离；非隔离仅在共模/地差实测满足时） |
| 带 4–20 mA 的 RS-485 采集节点 | [08-rs485-node.md](applications/08-rs485-node.md) → `references/common-hardware/applications/08-rs485-node.md` (ok)
- L72 [unknown] [](applications/08-rs485-node.md) | 再加 D7 + E5 |
| 定时控制装置 | [09-timer-control.md](applications/09-timer-control.md) → `references/common-hardware/applications/09-timer-control.md` (ok)
- L73 [unknown] [09-timer-control.md) | M6 + K3 + L6/L3 + H2/H8 |
| 土壤监测装置 | [10-soil-monitor.md](applications/10-soil-monitor.md) → `references/common-hardware/applications/10-soil-monitor.md` (ok)
- L74 [unknown] [/10-soil-monitor.md) | D5 + A1/A5 + H1/H7 + M3 |
| 小型数据记录器 | [11-data-logger.md](applications/11-data-logger.md) → `references/common-hardware/applications/11-data-logger.md` (ok)
- L75 [unknown] [ta-logger.md) | M6 + I8 + A1/E1 + H2/H7 |
| 电磁阀控制器 | [12-solenoid-controller.md](applications/12-solenoid-controller.md) → `references/common-hardware/applications/12-solenoid-controller.md` (ok)
- L90 [unknown] [造/样机/实测”如实标注。

## 5. 与现有内容的分工

| 已有内容 | 负责 | 本组补什么 |
|---|---|---|
| [设计卡库](../design-cards/README.md) → `references/design-cards/README.md` (ok)
- L91 [unknown] [rds/README.md) | 通用拓扑、公式、算例、逐脚/PCB 要求 | 用户话术、路线选择、具体型号、跨主题组合与采购/验证操作化 |
| [工程深潜](../engineering-deepdives/README.md) → `references/engineering-deepdives/README.md` (ok)
- L92 [unknown] [ing-deepdives/README.md) | 真实设计、跨模块失效、审图训练 | 把机制落到具体传感器/电源/接口的选型与检查 |
| [故障与反例库](../failures/README.md) → `references/failures/README.md` (ok)
- L93 [unknown] [[故障与反例库](../failures/README.md) | 单点故障现象→根因→复验 | 常见误判条目指向对应故障卡，不重复整篇 |
| [板级热设计](../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L94 [unknown] [| [板级热设计](../thermal/topic.md) | Rθ、结温、PCB/外壳热路径 | 具体器件功耗、热放置、降额与测温 |
| [立创商城选型](../lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L94 [unknown] [d) | Rθ、结温、PCB/外壳热路径 | 具体器件功耗、热放置、降额与测温 |
| [立创商城选型](../lcsc-sourcing.md)、[生产规则](../jlc-production.md) → `references/jlc-production.md` (ok)
- L99 [unknown] [护

- 每个组文件末尾有 `## 本组来源`，登记 `CHW-S###` 的实际查阅范围、版本、支持内容与“不能推广”。
- 来源总表见 [原始来源登记](../source-register.md) → `references/source-register.md` (ok)

### `references/common-hardware/a-environment.md`

- 标题：A 温度、湿度与环境传感
- 行/字符/字节：1199 / 54700 / 94672
- SHA-256：`dabd0cef97e101981e88f400040c8cc95955c1eafd52fca7b3e2e3d10ad37b2f`

- L3 [unknown] [度与环境传感

本组解决“测温度、测湿度、测气压/高度、测空气质量”从选路线到画图、写程序、验证和采购的落地问题。A1/A3 的电气基础已在 [ANA-10](../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L23 [unknown] [Steinhart-Hart、`R_TOP`、ADC 码值换算，以及 A3 的 IEC 60751/CVD、Pt1000、MAX31865。引用：[ANA-10](../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L24 [example] [-thermistor.md) §3–§5。
- **A2/A5 → I²C 总线层**：上拉区间、总线电容、TVS 位置、地址 strap 见 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L24 [example] [拉区间、总线电容、TVS 位置、地址 strap 见 [IF-01](../design-cards/interfaces/i01-i2c.md) 与 [x05](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L25 [unknown] [5](../examples/x05-i2c.md)；不要在传感器卡里重算一遍 I²C。
- **A2/A4/A6/A7 → 地址/片选与睡眠预算**：[D1](../engineering-deepdives/topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L25 [unknown] [s/topics/d1-interface-combination-constraints.md) 的 `ADDR`/`CSB`/`SDO` strap，[B2](../engineering-deepdives/topics/b2-sleep-current-budget.md) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok)
- L26 [unknown] [topics/b2-sleep-current-budget.md) 的 standby 电流预算。
- **A5/A6/A7 → 气路与布置**：[DM24](../domain-design-details.md) → `references/domain-design-details.md` (ok)
- L26 [unknown] [ standby 电流预算。
- **A5/A6/A7 → 气路与布置**：[DM24](../domain-design-details.md)、[PL24](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L26 [unknown] [置**：[DM24](../domain-design-details.md)、[PL24](../pcb-placement-details.md)、[G08](../design-experience.md) → `references/design-experience.md` (ok)
- L26 [unknown] [/pcb-placement-details.md)、[G08](../design-experience.md)、[enclosure-integration](../enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L26 [unknown] [perience.md)、[enclosure-integration](../enclosure-integration.md)、[thermal/topic](../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L27 [unknown] [d) §7.4。三张卡共用“留气孔、远离热源、防凝露/涂覆堵孔”判据，但滤膜、导压管、加热器要求分别写。
- **A1 → 充电器 NTC**：[PWR-06](../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L28 [unknown] [r-charger.md) 的 TS 脚是电压门限检测，不是精密测温；曲线不同不能直接换料。
- **A1/A2/A4 → 加热器过温保护**：[DRV-08](../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L29 [unknown] [感器类型、位置、断线与独立切断路径。
- **采购**：完整 MPN、封装、气孔/滤膜、生命周期按 [selection/modules-connectors](../selection/modules-connectors.md) → `references/selection/modules-connectors.md` (ok)
- L29 [unknown] [dules-connectors](../selection/modules-connectors.md) §5/§7 与 [lcsc-verification](../selection/lcsc-verification.md) → `references/selection/lcsc-verification.md` (ok)
- L41 [unknown] [装，CHW-S001）；E2（Beta/Steinhart-Hart 为通用方法，具体系数须按型号/校准取得）。分压、自热与 ADC 误差链复用 [ANA-10](../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L203 [example] [ 6`，引脚、±0.5 °C、12 位/750 ms、SKIP ROM/CONVERT T 多点广播，CHW-S004）；E2（I²C 上拉/电容复用 [x05](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L203 [example] [M/CONVERT T 多点广播，CHW-S004）；E2（I²C 上拉/电容复用 [x05](../examples/x05-i2c.md) 与 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L240 [example] [

### 电路组成

- **去耦**：`V+` 到 GND 就近 100 nF；长线再加 1 µF。
- **上拉**：SDA/SCL 按 [x05](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L361 [unknown] [拓扑的电容与上拉。

## A3 铂电阻测温

结论先行：RTD 的线制、双 IDAC、比率测量、`R_REF`/PGA 与自热预算已在 [ANA-10](../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L400 [unknown] [` 串阻+差分电容（100 nF/100 Ω 或 10 nF/1 kΩ，按手册）；TVS 漏电会破坏三线匹配。
- **分立方案**：完全复用 [ANA-10](../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L482 [unknown] [位，CHW-S007）；E2（NIST ITS-90 数据库入口已确认，表值未取得，CHW-S012）。用热电偶“测壳温”的方法见 [thermal/topic](../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L647 [example] [`，引脚、RH/T 精度、命令、CRC、加热器、时序，CHW-S008）；E2（DM24/PL24/G08/P01 的布置与验收要求，已在仓库）；E1（[x05](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L686 [example] [3.6 V，**不能接 5 V**；100 nF 就近去耦，长线再加 1 µF。
- **I²C**：SDA/SCL 上拉 2.2–4.7 kΩ（按 [x05](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)

### `references/common-hardware/applications/01-temperature-alarm.md`

- 标题：温度过高报警：A1/A2 + I1 + L8 + K1 + F1/F5
- 行/字符/字节：180 / 10194 / 18179
- SHA-256：`c3b3decb0042849a2bebd1589176a6601f297f09b6ae276282ec1893cd263d74`

- L24 [unknown] [满量程/零判为开路/短路，能用厂商 R-T 表代替单 Beta，能在产线写 45 °C 校准点，并用软件做 2 °C 回差。NTC 选 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量) → `references/common-hardware/a-environment.md` (ok) #a1-ntc-温度测量 ok
- L24 [unknown] [C 选 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量) 的分压路线；若现场不接受校准，改用 [A2 数字温度传感器](../a-environment.md#a2-数字温度传感器) → `references/common-hardware/a-environment.md` (ok) #a2-数字温度传感器 ok
- L24 [unknown] [器响、没有固件”，它更便宜且已有 EDA 回读。本文把它保留为 B 方案，并复用其 NTC 分压、低侧 MOS 和蜂鸣器连接；主控边界按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L24 [unknown] [压、低侧 MOS 和蜂鸣器连接；主控边界按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) 核算，功率级按 [K1 低侧 MOS 开关](../k-drive.md#k1-低侧-mos-开关) → `references/common-hardware/k-drive.md` (ok) #k1-低侧-mos-开关 ok
- L24 [unknown] [-mcu.md#i1-低成本基础控制) 核算，功率级按 [K1 低侧 MOS 开关](../k-drive.md#k1-低侧-mos-开关) 与 [DRV-01](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L32 [background] [203(42)` 仅作族参考 | 有源/无源、电磁式/压电式、额定电压、电流、声压@10 cm、谐振频率 | EDA 库 E2；手册待核；路线见 [L8 蜂鸣器](../l-hmi.md#l8-蜂鸣器) → `references/common-hardware/l-hmi.md` (ok) #l8-蜂鸣器 ok
- L36 [unknown] [3 V + 9×5.5 mm + 声压 + 电流；`2N7002` + SOT-23 + `Rds(on)@3.3V`。输入链与反接分别读 [F1 USB 供电](../f-input-protection.md#f1-usb-供电) → `references/common-hardware/f-input-protection.md` (ok) #f1-usb-供电 ok
- L36 [unknown] [Rds(on)@3.3V`。输入链与反接分别读 [F1 USB 供电](../f-input-protection.md#f1-usb-供电)、[F5 反接保护](../f-input-protection.md#f5-反接保护) → `references/common-hardware/f-input-protection.md` (ok) #f5-反接保护 ok
- L57 [unknown] [；若同时保留 USB-C 与 2 针端子，两路 5 V 不能直接并在一起，必须 ORing 或只装一路，否则会反灌。ORing 与反灌路径见 [P05 电源切换](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L68 [unknown] [留 4.7 kΩ，就要在固件/校准里承认 +1.3 °C 的系统偏移。这不是网表错误，是 E24 取值与目标阈值没有对齐；分压、自热与误差链复用 [ANA-10](../../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)

### `references/common-hardware/applications/02-fan-control.md`

- 标题：自动调速风扇（组合应用 02）
- 行/字符/字节：127 / 10111 / 18569
- SHA-256：`04841375aee8564e0cad581b7eeb7d7924f9c84984133d155e2f61764dcb1cc4`

- L25 [unknown] [*。4 线把功率与调速分开，风扇内部电路始终有电，低速稳定性、噪声和寿命都优于切电源；TACH 还能独立验证“命令是否真的变成转速”。接口与时序按 [K7 风扇](../k-drive.md#k7-风扇) → `references/common-hardware/k-drive.md` (ok) #k7-风扇 ok
- L25 [unknown] [命都优于切电源；TACH 还能独立验证“命令是否真的变成转速”。接口与时序按 [K7 风扇](../k-drive.md#k7-风扇)，测速路线按 [C6 转速](../c-motion.md#c6-转速检测) → `references/common-hardware/c-motion.md` (ok) #c6-转速检测 ok
- L33 [unknown] [MCU 开漏/低边 FET 拉 PWM | PWM 脚不得外加 pull-up/pull-down；不得切 12 V 调速 |

测温默认用 [A1 NTC](../a-environment.md#a1-ntc-温度测量) → `references/common-hardware/a-environment.md` (ok) #a1-ntc-温度测量 ok
- L33 [unknown] [(../a-environment.md#a1-ntc-温度测量) 做控制量：便宜、可把探头放到风道或散热器上。需要板温监测或更高精度时加 [A2 TMP117](../a-environment.md#a2-数字温度传感器) → `references/common-hardware/a-environment.md` (ok) #a2-数字温度传感器 ok
- L33 [unknown] [a-environment.md#a2-数字温度传感器) 作第二点；TMP117 测的是芯片/焊盘温度，不能直接当成远处空气温度。主控用 [I1 低成本 MCU](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L33 [unknown] [03F4P6：24 MHz、16 KB Flash、10 位 ADC、两个定时器，够做 25 kHz PWM 与输入捕获。逻辑 3.3 V 由 [G2 Buck](../g-power-conversion.md#g2-buck) → `references/common-hardware/g-power-conversion.md` (ok) #g2-buck ok
- L33 [unknown] [k](../g-power-conversion.md#g2-buck) 从 12 V 降下来；风扇 12 V 不经过 Buck 开关。状态灯按 [L1 LED](../l-hmi.md#l1-led-指示) → `references/common-hardware/l-hmi.md` (ok) #l1-led-指示 ok
- L62 [unknown] [或只做通断。2 线风扇没有 TACH，只能通断；需要调速时用调压，不要用 25 kHz 斩波，且要接受低速可能不启动。2/3 线的低侧开关见 [D01 低侧开关](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L78 [unknown] [40 Ω，电流 4.6–6.25 mA，电阻最坏 9.4 mW。指示 LED 默认电阻限流，恒流方案只用于大电流/多串/背光，见 [DRV-07 LED 恒流卡](../../design-cards/drive/d07-led-cc.md) → `references/design-cards/drive/d07-led-cc.md` (ok)
- L90 [unknown] [电压、NTC 的 R25/B/R_TOP/温区、Buck 的 L/C/反馈值、LED 的 Vf 分档与限流电阻。NTC 分压的细节和误差预算复用 [ANA-10](../../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L90 [unknown] [算复用 [ANA-10](../../design-cards/analog/a10-rtd-thermistor.md)，Buck 功率级复用 [PWR-02](../../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L126 [unknown] [。

安全与证据边界：本文只适用于 12 V SELV；市电风扇、隔离、爬电距离、接地与认证需专业签核，本文不声称通过任何安规/EMC 认证。[L1 LED](../l-hmi.md#l1-led-指示) → `references/common-hardware/l-hmi.md` (ok) #l1-led-指示 ok

### `references/common-hardware/applications/03-humidity-display.md`

- 标题：桌面温湿度显示（组合应用 03）
- 行/字符/字节：133 / 10767 / 19581
- SHA-256：`08ca3eaabaea66678801b44f1c0903f3609e3005fdf883d7884fc848c2f84fe3`

- L27 [unknown] [06 0.96 英寸 128×64 I²C 模块 + CH32V003F4P6 + USB 5 V 经 LDO 到 3.3 V**。传感器路线按 [A5 温湿度](../a-environment.md#a5-温湿度传感器) → `references/common-hardware/a-environment.md` (ok) #a5-温湿度传感器 ok
- L27 [unknown] [ LDO 到 3.3 V**。传感器路线按 [A5 温湿度](../a-environment.md#a5-温湿度传感器)，显示按 [L3 OLED 与液晶模块](../l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok
- L27 [unknown] [3-oled-与液晶模块)（已按该节核对 128×64/1024 B、模块 LDO/上拉与 SSD1306/SH1106 差异），主控按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L27 [unknown] [O/上拉与 SSD1306/SH1106 差异），主控按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制)，总线按 [J1 I²C 外设](../j-buses.md#j1-i2c-外设) → `references/common-hardware/j-buses.md` (ok) #j1-i2c-外设 ok
- L27 [unknown] [(../i-mcu.md#i1-低成本基础控制)，总线按 [J1 I²C 外设](../j-buses.md#j1-i2c-外设)，入口按 [F1 USB 供电](../f-input-protection.md#f1-usb-供电) → `references/common-hardware/f-input-protection.md` (ok) #f1-usb-供电 ok
- L27 [unknown] [d#j1-i2c-外设)，入口按 [F1 USB 供电](../f-input-protection.md#f1-usb-供电)，3.3 V 按 [G1 LDO](../g-power-conversion.md#g1-ldo) → `references/common-hardware/g-power-conversion.md` (ok) #g1-ldo ok
- L38 [unknown] [模块只接受 5 V VCC，必须确认其逻辑侧是 3.3 V，或加电平转换/改用 3.3 V 模组，不能把 SHT40 直接挂上去。

显示路线可复用 [L3](../l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok
- L40 [unknown] [ESP32 + 2.4 寸彩屏 + 蜂鸣器，不要照抄本应用的 0.96 寸 OLED / CH32V003 / TPS7A02 路线；改走 [I3 无线 MCU](../i-mcu.md#i3-无线-mcu-与模组) → `references/common-hardware/i-mcu.md` (ok) #i3-无线-mcu-与模组 ok
- L40 [unknown] [OLED / CH32V003 / TPS7A02 路线；改走 [I3 无线 MCU](../i-mcu.md#i3-无线-mcu-与模组) + [L4 TFT](../l-hmi.md#l4-tft-显示) → `references/common-hardware/l-hmi.md` (ok) #l4-tft-显示 ok
- L40 [unknown] [3 无线 MCU](../i-mcu.md#i3-无线-mcu-与模组) + [L4 TFT](../l-hmi.md#l4-tft-显示) + [L8 蜂鸣器](../l-hmi.md#l8-蜂鸣器) → `references/common-hardware/l-hmi.md` (ok) #l8-蜂鸣器 ok
- L40 [unknown] [-与模组) + [L4 TFT](../l-hmi.md#l4-tft-显示) + [L8 蜂鸣器](../l-hmi.md#l8-蜂鸣器) + [A5 温湿度](../a-environment.md#a5-温湿度传感器) → `references/common-hardware/a-environment.md` (ok) #a5-温湿度传感器 ok
- L40 [unknown] [8 蜂鸣器](../l-hmi.md#l8-蜂鸣器) + [A5 温湿度](../a-environment.md#a5-温湿度传感器) + [F2 USB-C](../f-input-protection.md#f2-usb-c-固定低压取电) → `references/common-hardware/f-input-protection.md` (ok) #f2-usb-c-固定低压取电 ok
- L40 [unknown] [.md#a5-温湿度传感器) + [F2 USB-C](../f-input-protection.md#f2-usb-c-固定低压取电) + [G2 Buck](../g-power-conversion.md#g2-buck) → `references/common-hardware/g-power-conversion.md` (ok) #g2-buck ok
- L50 [unknown] [I `TPD3S014`（0.5 A 级限流+数据 ESD）；USB-C 受电则 CC1/CC2 各 5.1 kΩ Rd（另按 [F2 USB-C 固定低压取电](../f-input-protection.md#f2-usb-c-固定低压取电) → `references/common-hardware/f-input-protection.md` (ok) #f2-usb-c-固定低压取电 ok
- L77 [unknown] [片还是带滤膜/保护盖，决定装配顺序与开窗方式，不能按“温湿度模块”笼统处理。

## 5. 关键计算与未确定项

**显示带宽与刷新率。** 按 [L3](../l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok
- L81 [unknown] [ax)=1000 ns`，5 kΩ 下约 313 ns 仍通过）。4.7 kΩ 单侧时 `tr=295 ns`，只剩 5 ns 余量，不建议。详见 [IF-01](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L81 [unknown] [ 5 ns 余量，不建议。详见 [IF-01](../../design-cards/interfaces/i01-i2c.md) §5 与 [F06 上拉失效](../../failures/f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L97 [required_read] [/BS 脚要单独处理，不能按 4-pin 模组画。上拉若画在模组框内，主板侧留 0 Ω/DNP 位置，方便调试时切换。功率级与 LDO 细节复用 [PWR-01](../../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L97 [required_read] [试时切换。功率级与 LDO 细节复用 [PWR-01](../../design-cards/power/p01-ldo.md)，I²C 电气复用 [IF-01](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L132 [unknown] [DA/PCB 与 DRC；⑤ 样机、装壳响应与两点湿度比对；⑥ 再做 ESD/EMC 与长期运行。每一步未通过就停在该步。

证据边界：显示部分已与 [L3](../l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok

### `references/common-hardware/applications/04-door-window-reminder.md`

- 标题：电池门窗提醒：C4 霍尔/干簧 + C7 限位 + H1 一次电池 + H7 低功耗 + M2 BLE + I1 主控
- 行/字符/字节：181 / 11733 / 20648
- SHA-256：`c2984ba6eb410e004409d73a4c4ea53083b7172a5fe0a398b5d9106e486902df`

- L27 [background] [MCP73831/BQ24074 + 保护板 | 高频事件、要边充边用 | 多 USB-C/充电/保护，体积与成本上升 |

推荐 A。按 [H1 一次电池](../h-battery.md#h1-一次电池) → `references/common-hardware/h-battery.md` (ok) #h1-一次电池 ok
- L27 [background] [
推荐 A。按 [H1 一次电池](../h-battery.md#h1-一次电池)，CR2032 只适合 µA 级背景 + 几 mA 短脉冲；[M2 BLE](../m-wireless-time.md#m2-ble) → `references/common-hardware/m-wireless-time.md` (ok) #m2-ble ok
- L27 [background] [眠 1.5 µA，可直供而不用升压。升压 TPS63802 的 Iq 11 µA 单这一项就把 150 mAh 可用容量压到 1.5 年以内（[H7 低功耗外围](../h-battery.md#h7-低功耗外围) → `references/common-hardware/h-battery.md` (ok) #h7-低功耗外围 ok
- L27 [background] [一项就把 150 mAh 可用容量压到 1.5 年以内（[H7 低功耗外围](../h-battery.md#h7-低功耗外围)）。B 路线按 [C4 霍尔开关](../c-motion.md#c4-霍尔开关与线性霍尔) → `references/common-hardware/c-motion.md` (ok) #c4-霍尔开关与线性霍尔 ok
- L27 [background] [霍尔开关](../c-motion.md#c4-霍尔开关与线性霍尔) 的 BOP/BRP 与气隙算例，适合干簧不可靠的场合；C 路线保留 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L41 [unknown] [位/防拆 | Omron `D2F-01`（SPDT，0.1 A/30 VDC） | COM/NO/NC、操作力/行程、寿命、小电流接触可靠性 | E1（[C7](../c-motion.md#c7-限位与接近开关) → `references/common-hardware/c-motion.md` (ok) #c7-限位与接近开关 ok
- L84 [unknown] [26 V，安全；100 µF 与 ESR 压降叠加约 0.24 V，100 nF 负责高频。
### 5.3 磁体–气隙与安装偏差

按 [C4 霍尔开关](../c-motion.md#c4-霍尔开关与线性霍尔) → `references/common-hardware/c-motion.md` (ok) #c4-霍尔开关与线性霍尔 ok
- L111 [unknown] [未确定项

CR2032 不可充电，任何“给纽扣电池充电”的方案都不成立。要充电改用 1S 锂电（如 50 mAh 软包）+ 保护板 + [MCP73831](../h-battery.md#h2-单节锂电池充电) → `references/common-hardware/h-battery.md` (ok) #h2-单节锂电池充电 ok
- L111 [unknown] [20 V 已超 32 mV，必须选更低 CV 档或换电芯；它无 power path，边充边用要改 BQ24074；USB-C 入口按 [F2 USB-C 5V](../f-input-protection.md#f2-usb-c-固定低压取电) → `references/common-hardware/f-input-protection.md` (ok) #f2-usb-c-固定低压取电 ok
- L115 [background] [。

## 6. 原理图组织
按四块画：1) 电源入口：CR2032 座 → P-MOS 防反（AO3401A 或 LM66100，按 [P09 反接保护](../../design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L115 [background] [1 MΩ。3) 主控/射频：nRF52840 模组 VDD 去耦、32.768 kHz 晶振（模组未含时）、SWD、复位、天线；最小系统按 [M01 裸 MCU](../../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L115 [background] [小系统按 [M01 裸 MCU](../../design-cards/mcu/m01-bare-mcu.md)，模组边界按 [W01 Wi-Fi/BLE 模组](../../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L129 [unknown] [ | 现场气隙公差需要微调 |
本板最高 3.0 V，不涉及爬电/隔离；改成 12/24 V 或市电联动要重新按实际电压核算。天线按 [W02 天线接口与匹配](../../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L178 [required_read] [、−20/25/60 °C；3) 定路线后画原理图并跑 ERC，重点检查“无充电网络、上拉门控、ADC 基准”；4) 画 PCB，先按 [W02 天线接口与匹配](../../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)

### `references/common-hardware/applications/05-electronic-scale.md`

- 标题：简易电子秤（组合应用 05）
- 行/字符/字节：160 / 12099 / 22082
- SHA-256：`313ff074e1c42e7038f06e81f88e709e637201f368426f1d527c8f55b0a1e954`

- L10 [unknown] [是 24 bit 二进制补码，不是 g；显示 0.1 g 只代表分辨率；传感器重复性、迟滞、蠕变、安装应力才是准确度的主项。** 本推演按 [D1 称重与应变桥](../d-force.md#d1-称重与应变桥) → `references/common-hardware/d-force.md` (ok) #d1-称重与应变桥 ok
- L10 [unknown] [主项。** 本推演按 [D1 称重与应变桥](../d-force.md#d1-称重与应变桥) 的产品化流程，桥式电气理论只引用 [ANA-09 桥式传感器前端](../../design-cards/analog/a09-bridge.md) → `references/design-cards/analog/a09-bridge.md` (ok)
- L23 [unknown] [B-C 5 V SELV，备选 3×AAA 一次电池与 3.3 V SELV，不涉及市电、充电、隔离或气体。若改用 1S 锂电/可充电方案，必须补 [H2 充电](../h-battery.md#h2-单节锂电池充电) → `references/common-hardware/h-battery.md` (ok) #h2-单节锂电池充电 ok
- L23 [unknown] [，不涉及市电、充电、隔离或气体。若改用 1S 锂电/可充电方案，必须补 [H2 充电](../h-battery.md#h2-单节锂电池充电) 与 [H4 保护](../h-battery.md#h4-电池保护) → `references/common-hardware/h-battery.md` (ok) #h4-电池保护 ok
- L27 [unknown] [DO；HX711 `VSUP=5 V`、`AVDD=DVDD=3.3 V`，桥激励 3.3 V，与本文 6.6 mV 满量程算例一致。USB-C 入口按 [F2](../f-input-protection.md#f2-usb-c-固定低压取电) → `references/common-hardware/f-input-protection.md` (ok) #f2-usb-c-固定低压取电 ok
- L29 [unknown] [需两根 GPIO，成本、面积和固件复杂度都低于 ADS1232 的 SPI/外部基准/多脚方案。显示、主控与 3.3 V 轨分别按 [L3 OLED 与液晶模块](../l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok
- L29 [unknown] [基准/多脚方案。显示、主控与 3.3 V 轨分别按 [L3 OLED 与液晶模块](../l-hmi.md#l3-oled-与液晶模块)、[I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L29 [unknown] [D 与液晶模块](../l-hmi.md#l3-oled-与液晶模块)、[I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制)、[G1 LDO](../g-power-conversion.md#g1-ldo) → `references/common-hardware/g-power-conversion.md` (ok) #g1-ldo ok
- L99 [background] [残差 ≤1 g；去皮只消空载失调，不能修灵敏度。自动回零只在“稳定且空载 3 s”时执行，不能开机带载回零。
10. **E1 电池采样**（[E1 电压采样](../e-measurement.md#e1-电压采样) → `references/common-hardware/e-measurement.md` (ok) #e1-电压采样 ok
- L100 [background] [则会吃掉睡眠预算。VDD 参考的 LDO 公差（±2% 级）直接进电池读数，低电阈值要留余量，不能当电量计。
11. **E7 多通道**（[E7 多通道采样](../e-measurement.md#e7-多通道采样) → `references/common-hardware/e-measurement.md` (ok) #e7-多通道采样 ok
- L159 [example] [ESD/EMC、长期运行与（如适用）计量检定。每一步未通过就停在该步。

证据边界：本文的 HX711 引脚/时序/噪声与 ADS1232 约束来自 [D1](../d-force.md#d1-称重与应变桥) → `references/common-hardware/d-force.md` (ok) #d1-称重与应变桥 ok
- L159 [example] [声与 ADS1232 约束来自 [D1](../d-force.md#d1-称重与应变桥) 已登记的 E1 资料；桥式公式/四六线/比率测量来自 [ANA-09](../../design-cards/analog/a09-bridge.md) → `references/design-cards/analog/a09-bridge.md` (ok)

### `references/common-hardware/applications/06-water-level-alarm.md`

- 标题：水箱液位提醒：D4 液位 + D7 模拟量接口 + K3 继电器/K7 泵 + L8 蜂鸣器 + F4 直流端子
- 行/字符/字节：180 / 11346 / 20984
- SHA-256：`3b83703f850881fd0a5124b86f2530093dbae7ede993d4fa3823fe084f8d580d`

- L30 [unknown] [、雷击、结垢 |

推荐 B：浮球做独立的高/低安全点，连续量做泵控与显示，二者互相校验。只报警选 A，成本最低且失效模式清楚。浮球路线按 [D4 液位检测](../d-force.md#d4-液位检测) → `references/common-hardware/d-force.md` (ok) #d4-液位检测 ok
- L30 [unknown] [成本最低且失效模式清楚。浮球路线按 [D4 液位检测](../d-force.md#d4-液位检测) 的干接点/消抖要求；连续量按 [D7 模拟量流量与液位接口](../d-force.md#d7-模拟量流量与液位接口) → `references/common-hardware/d-force.md` (ok) #d7-模拟量流量与液位接口 ok
- L30 [unknown] [的干接点/消抖要求；连续量按 [D7 模拟量流量与液位接口](../d-force.md#d7-模拟量流量与液位接口) 与 [ANA-08 4–20 mA 输入](../../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L30 [unknown] [非金属壁且壁厚在 0–13 mm；静压式测的是液柱压力，不是体积。K7 的正文锚点是风扇，泵不能直接套用其 2.2 A/1 s 启动上限；泵按 [K5 直流电机](../k-drive.md#k5-直流电机) → `references/common-hardware/k-drive.md` (ok) #k5-直流电机 ok
- L30 [unknown] [正文锚点是风扇，泵不能直接套用其 2.2 A/1 s 启动上限；泵按 [K5 直流电机](../k-drive.md#k5-直流电机) 与铭牌核对，[K7 风扇](../k-drive.md#k7-风扇) → `references/common-hardware/k-drive.md` (ok) #k7-风扇 ok
- L76 [unknown] [。330 µA 对部分干接点低于可靠湿润电流，长期可能氧化；要么改用 4.7 kΩ（约 0.70 mA），要么选金触点/厂家指定低电平负载，按 [D4 液位检测](../d-force.md#d4-液位检测) → `references/common-hardware/d-force.md` (ok) #d4-液位检测 ok
- L88 [unknown] [=0.515 mA` 的注入电流；戴维南电阻 `40.2k∥10k=8.0 kΩ`，SAR ADC 前要缓冲或延长采样，按 [ANA-04 SAR ADC 驱动](../../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L106 [unknown] [水材料合规；现场 EMC/浪涌与批量一致性。以上均未实测。

## 6. 原理图组织

按五块画：1) 输入：F4 DC 座（[F4 直流端子与圆孔输入](../f-input-protection.md#f4-直流端子与圆孔输入) → `references/common-hardware/f-input-protection.md` (ok) #f4-直流端子与圆孔输入 ok
- L106 [unknown] [4 直流端子与圆孔输入](../f-input-protection.md#f4-直流端子与圆孔输入)）→ 保险/TVS → 反接 MOS（按 [F5 反接保护](../f-input-protection.md#f5-反接保护) → `references/common-hardware/f-input-protection.md` (ok) #f5-反接保护 ok
- L106 [unknown] [与圆孔输入)）→ 保险/TVS → 反接 MOS（按 [F5 反接保护](../f-input-protection.md#f5-反接保护)、[P09 反接保护](../../design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L106 [unknown] [09-reverse-polarity.md)）→ `VIN`，标注中心极性、适配器电压、保险额定。2) 电源：24 V→3.3 V LDO，按 [G1 LDO](../g-power-conversion.md#g1-ldo低压差线性稳压) → `references/common-hardware/g-power-conversion.md` (ok) #g1-ldo低压差线性稳压 ok
- L106 [unknown] [TVS；0–10 V 分压+钳位；隔离边界用虚线框标出。4) 输出：继电器线圈驱动+续流，触点侧单独画；泵端子、RC/压敏；蜂鸣器低侧驱动+续流（[L8 蜂鸣器](../l-hmi.md#l8-蜂鸣器) → `references/common-hardware/l-hmi.md` (ok) #l8-蜂鸣器 ok
- L108 [unknown] [载类型。网络名固定 `VIN`、`3V3`、`LEVEL_L`、`LEVEL_H`、`I_SENSE`、`PUMP_ON`、`BUZ`。继电器按 [K3 继电器](../k-drive.md#k3-继电器) → `references/common-hardware/k-drive.md` (ok) #k3-继电器 ok
- L108 [unknown] [`PUMP_ON`、`BUZ`。继电器按 [K3 继电器](../k-drive.md#k3-继电器) 的线圈/触点分开画，驱动级按 [DRV-03 继电器驱动](../../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)

### `references/common-hardware/applications/07-current-monitor.md`

- 标题：设备电流监测（组合应用 07）
- 行/字符/字节：161 / 13412 / 23743
- SHA-256：`dc6e686bc35e0fec350d4425ba4d26bb44ff3730c62c6f4fef1b66d75e2d0e5e`

- L22 [required_read] [ V 由市电电源派生，SELV 与绝缘由该电源负责，本板不提供市电隔离。若母线 >60 V DC、或分流所在回路的地与本地地必须分开，改用 [E5 隔离电流检测](../e-measurement.md#e5-隔离电流检测) → `references/common-hardware/e-measurement.md` (ok) #e5-隔离电流检测 ok
- L22 [required_read] [离电流检测](../e-measurement.md#e5-隔离电流检测) 并做隔离电源/爬电/间隙与专业签核。若 24 V 是电池组，必须按 [H4 电池保护](../h-battery.md#h4-电池保护) → `references/common-hardware/h-battery.md` (ok) #h4-电池保护 ok
- L34 [unknown] [ µV、增益误差 ±0.2%、400 kHz；REF1/REF2 可接同一中点，天然支持双向。选 **STM32G431CBU6**（[I4 模拟能力较强的主控](../i-mcu.md#i4-模拟能力较强的主控) → `references/common-hardware/i-mcu.md` (ok) #i4-模拟能力较强的主控 ok
- L34 [unknown] [器件；代价是 12 位 ENOB 只有 10.4–10.6 位、INL 3.4 LSB，必须过采样和校准。通信选 **THVD1450**（[J5 RS-485](../j-buses.md#j5-rs-485) → `references/common-hardware/j-buses.md` (ok) #j5-rs-485 ok
- L34 [unknown] [5-rs-485)）：3.3 V、1/8 U.L.、±18 kV IEC ESD、SOIC-8；若主机只支持 CAN，改 **TCAN334**（[J6 CAN](../j-buses.md#j6-can) → `references/common-hardware/j-buses.md` (ok) #j6-can ok
- L110 [required_read] [n 或 off 的中间；若把分流改到电机相线（在线采样），必须在导通中点采样并 blanking，且不能把 off 期电流当相电流——那是另一套 [ANA-07](../../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L114 [unknown] [24 V 下 15 mA；整机 <1 W。**TPS54202H 推荐上限 28 V，30 V 母线不成立**：改用 60 V Buck 并按 [G2 Buck](../g-power-conversion.md#g2-buck) → `references/common-hardware/g-power-conversion.md` (ok) #g2-buck ok
- L160 [required_read] [试。每一步未通过就停在该步。

证据边界：INA240/INA228 的共模、CMRR、`V_os`、增益与 INA181 的 REF 传递函数来自 [E3](../e-measurement.md#e3-高侧电流采样) → `references/common-hardware/e-measurement.md` (ok) #e3-高侧电流采样 ok
- L160 [required_read] [ 的共模、CMRR、`V_os`、增益与 INA181 的 REF 传递函数来自 [E3](../e-measurement.md#e3-高侧电流采样)/[E4](../e-measurement.md#e4-双向电流测量) → `references/common-hardware/e-measurement.md` (ok) #e4-双向电流测量 ok
- L160 [required_read] [电流采样)/[E4](../e-measurement.md#e4-双向电流测量) 已登记的 E1 资料；高侧拓扑、CMRR 与误差合成方法来自 [ANA-07](../../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L160 [required_read] [E2，且其 §5 的 `100 µV/1 mΩ` 必须按 100 mA 修正，本文用修正后的口径）；G431 的 ENOB/INL/OPAMP 数值来自 [I4](../i-mcu.md#i4-模拟能力较强的主控) → `references/common-hardware/i-mcu.md` (ok) #i4-模拟能力较强的主控 ok
- L160 [required_read] [NOB/INL/OPAMP 数值来自 [I4](../i-mcu.md#i4-模拟能力较强的主控) 的 DS12589 核对；RS-485/CAN 来自 [J5](../j-buses.md#j5-rs-485) → `references/common-hardware/j-buses.md` (ok) #j5-rs-485 ok
- L160 [required_read] [cu.md#i4-模拟能力较强的主控) 的 DS12589 核对；RS-485/CAN 来自 [J5](../j-buses.md#j5-rs-485)/[J6](../j-buses.md#j6-can) → `references/common-hardware/j-buses.md` (ok) #j6-can ok
- L160 [required_read] [85/CAN 来自 [J5](../j-buses.md#j5-rs-485)/[J6](../j-buses.md#j6-can)；Buck 边界来自 [G2](../g-power-conversion.md#g2-buck) → `references/common-hardware/g-power-conversion.md` (ok) #g2-buck ok

### `references/common-hardware/applications/08-rs485-node.md`

- 标题：RS-485 采集节点：A5 温湿度 + J5 RS-485 + D7 4–20 mA + E5 隔离 + F5/F7 保护 + I2 MCU
- 行/字符/字节：179 / 11089 / 18967
- SHA-256：`a626e719dd7210a9765b43efb45ec30b07f7e5e48fd421ae0fb1f0fb0099c737`

- L29 [unknown] [85 收发器、4–20 mA 分流与 24 V 入口放在同一“现场地”，MCU、SHT40、调试口放在本地地，只做一道屏障。SHT40 按 [A5 温湿度传感器](../a-environment.md#a5-温湿度传感器) → `references/common-hardware/a-environment.md` (ok) #a5-温湿度传感器 ok
- L29 [unknown] [地，只做一道屏障。SHT40 按 [A5 温湿度传感器](../a-environment.md#a5-温湿度传感器) 选型与布置；总线按 [J5 RS-485](../j-buses.md#j5-rs-485) → `references/common-hardware/j-buses.md` (ok) #j5-rs-485 ok
- L29 [unknown] [ THVD1450（3–5.5 V、1/8 U.L.、±18 kV IEC ESD、CM −15…+15 V）；4–20 mA 按 [D7 模拟量流量与液位接口](../d-force.md#d7-模拟量流量与液位接口) → `references/common-hardware/d-force.md` (ok) #d7-模拟量流量与液位接口 ok
- L29 [unknown] [15 V）；4–20 mA 按 [D7 模拟量流量与液位接口](../d-force.md#d7-模拟量流量与液位接口) 定量程/回路，按 [E5 隔离电流检测](../e-measurement.md#e5-隔离电流检测) → `references/common-hardware/e-measurement.md` (ok) #e5-隔离电流检测 ok
- L29 [unknown] [位接口) 定量程/回路，按 [E5 隔离电流检测](../e-measurement.md#e5-隔离电流检测) 选 AMC1300B；入口按 [F5 反接保护](../f-input-protection.md#f5-反接保护) → `references/common-hardware/f-input-protection.md` (ok) #f5-反接保护 ok
- L29 [unknown] [隔离电流检测) 选 AMC1300B；入口按 [F5 反接保护](../f-input-protection.md#f5-反接保护) 与 [F7 过压与瞬态保护](../f-input-protection.md#f7-过压与瞬态保护) → `references/common-hardware/f-input-protection.md` (ok) #f7-过压与瞬态保护 ok
- L88 [unknown] [间时，两端 120 Ω 是并联，每只承受约 24 V：`P=24²/120=4.8 W`，两只合计 9.6 W；1/4 W 电阻不满足。按 [J5 RS-485](../j-buses.md#j5-rs-485) → `references/common-hardware/j-buses.md` (ok) #j5-rs-485 ok
- L113 [background] [GND1 明确；RS-485 的 A/B 经 PTC→TVS/GDT→端子，端接/偏置用文字框标“仅两端/仅一个节点”。参考 [IF-07 RS-485 设计卡](../../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L113 [background] [-07 RS-485 设计卡](../../design-cards/interfaces/i07-rs485.md) 与 [ANA-08 4–20 mA 输入](../../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L115 [unknown] [禁止任何网络跨框；调试口只在本地侧。
4. **本地**：3.3 V LDO、MCU、8 MHz 晶体、SHT40、SWD、IWDG；按 [I2 通用 MCU](../i-mcu.md#i2-通用-mcu) → `references/common-hardware/i-mcu.md` (ok) #i2-通用-mcu ok
- L115 [unknown] [体、SHT40、SWD、IWDG；按 [I2 通用 MCU](../i-mcu.md#i2-通用-mcu) 核对 BOOT0/电源脚，按 [I5 外部晶体与时钟](../i-mcu.md#i5-外部晶体与时钟) → `references/common-hardware/i-mcu.md` (ok) #i5-外部晶体与时钟 ok

### `references/common-hardware/applications/09-timer-control.md`

- 标题：定时控制装置：M6 RTC + K3 继电器 + L6 按键 + L3 显示 + H2/H8 电池 + I1 主控
- 行/字符/字节：175 / 13852 / 24164
- SHA-256：`988e776a090d9b2f0ac57def40dc7bd482b8217304b7c37eebd390b03d2b3c52`

- L28 [conditional_read] [压/锁存时序复杂，锁存默认态是“上次状态”，安全要评审 |

推荐 A：把“负载开关”和“逻辑保持”分开。市电正常时，适配器经 [H3 带电源路径管理的充电](../h-battery.md#h3-带电源路径管理的充电) → `references/common-hardware/h-battery.md` (ok) #h3-带电源路径管理的充电 ok
- L28 [conditional_read] [供电并给 1S 电池充电；市电掉电时，电池只给 MCU、RTC、OLED（按需）供电，继电器线圈立即断电、负载回到 NO 的“关”态。RTC 选 [M6 RTC](../m-wireless-time.md#m6-rtc) → `references/common-hardware/m-wireless-time.md` (ok) #m6-rtc ok
- L30 [required_read] [标要另核；PCF8563 只有外部晶体、无温度补偿，用普通 ±20 ppm 晶体一年差约 10.5 min，只能靠定期手动校时。

继电器按 [K3 继电器](../k-drive.md#k3-继电器) → `references/common-hardware/k-drive.md` (ok) #k3-继电器 ok
- L30 [required_read] [，230 VAC 的电流与寿命必须按原厂 250 VAC 曲线复核，不能按“10 A”外推；频繁动作或大幅感性负载应改 SSR/接触器。按键按 [L6 机械按键](../l-hmi.md#l6-机械按键) → `references/common-hardware/l-hmi.md` (ok) #l6-机械按键 ok
- L30 [required_read] [或大幅感性负载应改 SSR/接触器。按键按 [L6 机械按键](../l-hmi.md#l6-机械按键) 用 4 个独立键，显示按 [L3 OLED 与液晶模块](../l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok
- L30 [required_read] [个独立键，显示按 [L3 OLED 与液晶模块](../l-hmi.md#l3-oled-与液晶模块) 用 SSD1306 模块；主控按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L77 [unknown] [33 h ≈ 6.3 年`；typ 0.84 µA 时理论 22 年以上，实际由自放电（约 1%/年）和温度决定。若用超级电容，按 [PWR-14 超级电容备份](../../design-cards/power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L81 [unknown] [4/2.6=27.5`，饱和足够；VCE(sat) 约 0.2–0.3 V，线圈实际 4.1 V 左右。若线圈是 24 V/30 mA 档，则按 [K3 继电器](../k-drive.md#k3-继电器) → `references/common-hardware/k-drive.md` (ok) #k3-继电器 ok
- L87 [unknown] [7/200k=18.5 µA`，总电流约 68 µA，寿命降到 `1600/0.068=23,529 h≈2.7 年`；所以分压必须门控，按 [H7 低功耗外围](../h-battery.md#h7-低功耗外围) → `references/common-hardware/h-battery.md` (ok) #h7-低功耗外围 ok
- L87 [unknown] [。若继电器线圈 71 mA 由备电供，`1600/0.0714=22.4 h`，所以市电掉电必须断线圈，这是本设计的硬约束。低电四方协调按 [H8 低电量与维护](../h-battery.md#h8-低电量与维护) → `references/common-hardware/h-battery.md` (ok) #h8-低电量与维护 ok
- L93 [unknown] [50 pF（280 ns），否则老实跑 100 kHz。模块自带 4.7–10 k 时不要再并一组；两组并联会把上升沿拉快、灌电流增大，按 [IF-01 I²C](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L97 [unknown] [S3823，超时 min 0.9 s，固件最坏循环应 <450 ms（2 倍裕量），且 WDI 不得悬空（悬空会自脉冲、永不复位），按 [I6 外部复位与看门狗](../i-mcu.md#i6-外部复位与看门狗) → `references/common-hardware/i-mcu.md` (ok) #i6-外部复位与看门狗 ok
- L103 [unknown] [险/PTC→TVS→BQ24074（IN/OUT/BAT、ILIM、ISET、TS）→`SYS`；电池座、NTC、保护板接口单独画。按 [PWR-06 线性充电](../../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L103 [unknown] [独画。按 [PWR-06 线性充电](../../design-cards/power/p06-linear-charger.md) 与 [H2 单节锂电池充电](../h-battery.md#h2-单节锂电池充电) → `references/common-hardware/h-battery.md` (ok) #h2-单节锂电池充电 ok
- L104 [unknown] [*：`SYS`→TPS7A02→`3V3`；`VBUS`/`SYS` 好坏信号→继电器负载开关；备电域与负载域用虚线框分开。电源切换按 [PWR-05 电源切换](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L105 [unknown] [BAT/ I²C/ INT 单画一区，pin5–12 接地、pin14 0.1–1 µF、pin4 不外加推挽；CR2032 座标极性/防反。按 [M6 RTC](../m-wireless-time.md#m6-rtc) → `references/common-hardware/m-wireless-time.md` (ok) #m6-rtc ok
- L106 [background] [ED 4-pin（VCC/GND/SCL/SDA）与 4 键；键串 100 Ω、10 kΩ 上拉，BOOT/NRST 键不加电容；蜂鸣器可选，按 [L8 蜂鸣器](../l-hmi.md#l8-蜂鸣器) → `references/common-hardware/l-hmi.md` (ok) #l8-蜂鸣器 ok
- L107 [unknown] [BT3904 基极 1 kΩ + 10 kΩ 下拉、线圈 1N4148W 续流、COM/NO 端子、触点 RC/TVS、负载保险；按 [DRV-03 继电器驱动](../../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)
- L107 [unknown] [触点 RC/TVS、负载保险；按 [DRV-03 继电器驱动](../../design-cards/drive/d03-relay.md) 与 [K3 继电器](../k-drive.md#k3-继电器) → `references/common-hardware/k-drive.md` (ok) #k3-继电器 ok

### `references/common-hardware/applications/10-soil-monitor.md`

- 标题：土壤监测装置：D5 土壤湿度 + A1/A5 温湿度 + H1/H7 电池与低功耗 + M3 Sub-GHz + L3 显示
- 行/字符/字节：204 / 14127 / 24123
- SHA-256：`8184ec80f85e10ec98902edcc8c095a2299e92651349c04d9e325b9cc054610d`

- L31 [unknown] [RF 匹配。B 只在实测 ER14250 脉冲能力、且 60 min 上报可接受时选用；C 的末端/低温余量不足，不作为推荐。土壤探头按 [D5 土壤与介质湿度](../d-force.md#d5-土壤与介质湿度) → `references/common-hardware/d-force.md` (ok) #d5-土壤与介质湿度 ok
- L31 [unknown] [按 [D5 土壤与介质湿度](../d-force.md#d5-土壤与介质湿度) 选电容式 SEN0308，不用直流电阻式；土壤温度按 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量) → `references/common-hardware/a-environment.md` (ok) #a1-ntc-温度测量 ok
- L31 [unknown] [08，不用直流电阻式；土壤温度按 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量) 用 NTC；[A5 温湿度传感器](../a-environment.md#a5-温湿度传感器) → `references/common-hardware/a-environment.md` (ok) #a5-温湿度传感器 ok
- L31 [unknown] [ NTC；[A5 温湿度传感器](../a-environment.md#a5-温湿度传感器) 只测机壳内空气，不埋进土里；无线按 [M3 Sub-GHz 无线](../m-wireless-time.md#m3-sub-ghz-无线) → `references/common-hardware/m-wireless-time.md` (ok) #m3-sub-ghz-无线 ok
- L31 [unknown] [埋进土里；无线按 [M3 Sub-GHz 无线](../m-wireless-time.md#m3-sub-ghz-无线)；显示按 [L3 OLED 与液晶模块](../l-hmi.md#l3-oled-与液晶模块) → `references/common-hardware/l-hmi.md` (ok) #l3-oled-与液晶模块 ok
- L33 [unknown] [埋地部分只用 NTC 与电容探头；L3 默认断电，按键唤醒 30 s；M3 的发射功率按目标市场法规设置，不直接跑 +22 dBm。低功耗按 [H7 低功耗外围](../h-battery.md#h7-低功耗外围) → `references/common-hardware/h-battery.md` (ok) #h7-低功耗外围 ok
- L33 [unknown] [市场法规设置，不直接跑 +22 dBm。低功耗按 [H7 低功耗外围](../h-battery.md#h7-低功耗外围) 先做整板预算，再选 [H1 一次电池](../h-battery.md#h1-一次电池) → `references/common-hardware/h-battery.md` (ok) #h1-一次电池 ok
- L86 [unknown] [/LSB`；12 位为 0.0235% VWC/LSB。探头本身的土质/盐分/温度误差远大于 LSB，不能拿分辨率当准确度。[ANA-04 SAR ADC 驱动](../../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L92 [unknown] [kΩ=0.106 mW`，按 `E=1 mW/°C` 约 0.11 °C（土壤散热更好，实际更小）；仍建议只在测量窗口供电。误差预算按 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量) → `references/common-hardware/a-environment.md` (ok) #a1-ntc-温度测量 ok
- L129 [unknown] [涌与当地 RF 法规。以上均未实测。

## 6. 原理图组织

按六块画：1) 电池入口：电池座 → PTC（[PWR-11 保险丝/eFuse/限流](../../design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L129 [unknown] [-11 保险丝/eFuse/限流](../../design-cards/power/p11-efuse.md)）→ 反接 P-MOS（[PWR-09 反接保护](../../design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L129 [unknown] [接 P-MOS（[PWR-09 反接保护](../../design-cards/power/p09-reverse-polarity.md)、[F5 反接保护](../f-input-protection.md#f5-反接保护) → `references/common-hardware/f-input-protection.md` (ok) #f5-反接保护 ok
- L129 [unknown] [)、[F5 反接保护](../f-input-protection.md#f5-反接保护)）→ `VBAT` → TPS63802（[G4 Buck-Boost](../g-power-conversion.md#g4-buck-boost四开关升降压) → `references/common-hardware/g-power-conversion.md` (ok) #g4-buck-boost四开关升降压 ok
- L129 [unknown] [→ TPS63802（[G4 Buck-Boost](../g-power-conversion.md#g4-buck-boost四开关升降压)、[PWR-04](../../design-cards/power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L129 [unknown] [）→ `3V3`；标注电池化学、不可充电、PTC 动作电流、UVLO。2) MCU：CH32V003 最小系统、SWIO、NRST、去耦；[I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L129 [unknown] [CH32V003 最小系统、SWIO、NRST、去耦；[I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制)、[MCU-07 SWD/JTAG](../../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L129 [unknown] [D/JTAG](../../design-cards/mcu/m07-swd-jtag.md)。3) 传感：`SENSOR_3V3` 负载开关（[G7 负载开关](../g-power-conversion.md#g7-负载开关load-switch) → `references/common-hardware/g-power-conversion.md` (ok) #g7-负载开关load-switch ok
- L131 [unknown] [OUT`、`NTC1`、`NTC2`、`I2C_SDA`、`I2C_SCL`、`RF_CS`、`BUSY`、`DIO1`。I²C 按 [IF-01 I²C 总线](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L131 [unknown] [1 I²C 总线](../../design-cards/interfaces/i01-i2c.md) 核对上拉/电容；SPI 按 [IF-03 SPI 点对点](../../design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)

### `references/common-hardware/applications/11-data-logger.md`

- 标题：小型数据记录器：M6 RTC + I8 NOR/EEPROM + A1/E1 采样 + H2/H7 电池与低功耗 + J7 USB 数据
- 行/字符/字节：175 / 16212 / 26704
- SHA-256：`c81b4d3b45ab16a7d0355b011dfc0756190d180e2954038ed9b78b9874f7e79b`

- L29 [unknown] [60 s 一条 16 B 仅约 1.4 天（34 h）；不适合长期 |

推荐 A：把“时间保持”“批量存储”“USB 桥”分域。RTC 用 [M6 RTC](../m-wireless-time.md#m6-rtc) → `references/common-hardware/m-wireless-time.md` (ok) #m6-rtc ok
- L29 [unknown] [c) 的 RV-3028-C7：45 nA、内置晶体、UNIX 时间、43 B RAM，常开不心疼；NOR 用 [I8 外扩 Flash、EEPROM 与存储卡](../i-mcu.md#i8-外扩-flasheeprom-与存储卡) → `references/common-hardware/i-mcu.md` (ok) #i8-外扩-flasheeprom-与存储卡 ok
- L29 [unknown] [-flasheeprom-与存储卡) 的 W25Q128JV 做只追加环形日志；参数/校准/提交指针放 AT24C256C；USB 走 [J7 USB 数据接口](../j-buses.md#j7-usb-数据接口) → `references/common-hardware/j-buses.md` (ok) #j7-usb-数据接口 ok
- L29 [unknown] [据接口](../j-buses.md#j7-usb-数据接口) 的 USB-UART 桥，因为 CH32V003 无原生 USB。电池按 [H2 单节锂电池充电](../h-battery.md#h2-单节锂电池充电) → `references/common-hardware/h-battery.md` (ok) #h2-单节锂电池充电 ok
- L29 [unknown] [为 CH32V003 无原生 USB。电池按 [H2 单节锂电池充电](../h-battery.md#h2-单节锂电池充电) 与 [H3 带电源路径管理的充电](../h-battery.md#h3-带电源路径管理的充电) → `references/common-hardware/h-battery.md` (ok) #h3-带电源路径管理的充电 ok
- L29 [unknown] [锂电池充电) 与 [H3 带电源路径管理的充电](../h-battery.md#h3-带电源路径管理的充电) 选 BQ24074，低功耗按 [H7 低功耗外围](../h-battery.md#h7-低功耗外围) → `references/common-hardware/h-battery.md` (ok) #h7-低功耗外围 ok
- L98 [unknown] [测。
## 6. 原理图组织

1. **USB 输入与充电**：USB-C 的 CC1/CC2 各 5.1 kΩ Rd（[F2 USB-C 固定低压取电](../f-input-protection.md#f2-usb-c-固定低压取电) → `references/common-hardware/f-input-protection.md` (ok) #f2-usb-c-固定低压取电 ok
- L98 [unknown] [ BQ24074（IN/OUT/BAT/ILIM/ISET/TS/CE/CHG/PG）→ `SYS`；电池座、保护板、NTC 单独画。按 [H2 单节锂电池充电](../h-battery.md#h2-单节锂电池充电) → `references/common-hardware/h-battery.md` (ok) #h2-单节锂电池充电 ok
- L98 [unknown] [ `SYS`；电池座、保护板、NTC 单独画。按 [H2 单节锂电池充电](../h-battery.md#h2-单节锂电池充电)、[H3 带电源路径管理的充电](../h-battery.md#h3-带电源路径管理的充电) → `references/common-hardware/h-battery.md` (ok) #h3-带电源路径管理的充电 ok
- L98 [unknown] [ery.md#h2-单节锂电池充电)、[H3 带电源路径管理的充电](../h-battery.md#h3-带电源路径管理的充电) 与 [PWR-06 线性充电](../../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L99 [unknown] [S22916→`3V3_SW`（NOR/NTC 激励/CH340G）；CH340G 的 EN 由“VBUS 有效”与 MCU GPIO 相与。按 [G1 LDO](../g-power-conversion.md#g1-ldo) → `references/common-hardware/g-power-conversion.md` (ok) #g1-ldo ok
- L99 [unknown] [ EN 由“VBUS 有效”与 MCU GPIO 相与。按 [G1 LDO](../g-power-conversion.md#g1-ldo)、[G7 负载开关](../g-power-conversion.md#g7-负载开关load-switch) → `references/common-hardware/g-power-conversion.md` (ok) #g7-负载开关load-switch ok
- L99 [unknown] [sion.md#g1-ldo)、[G7 负载开关](../g-power-conversion.md#g7-负载开关load-switch)、[H7 低功耗外围](../h-battery.md#h7-低功耗外围) → `references/common-hardware/h-battery.md` (ok) #h7-低功耗外围 ok
- L100 [unknown] [。
3. **MCU 最小系统**：CH32V003 的 VDD/VDDA 去耦、NRST、SWIO 调试口；不接晶体，用 HSI。按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok
- L100 [unknown] [ST、SWIO 调试口；不接晶体，用 HSI。按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) 与 [MCU-07 SWD/JTAG](../../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L101 [unknown] [.7 kΩ 到 `3V3_A`。若改 DS3231，pin5–12 必须接地、pin14 放 0.1–1 µF 低漏电、pin4 不外加推挽；按 [M6 RTC](../m-wireless-time.md#m6-rtc) → `references/common-hardware/m-wireless-time.md` (ok) #m6-rtc ok
- L102 [unknown] [D` 10 kΩ 上拉、0.1 µF；AT24C256C 的 A0–A2 接 GND、WP 接 GPIO、0.1 µF。SPI 按 [IF-03 SPI 点对点](../../design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L102 [unknown] [ 按 [IF-03 SPI 点对点](../../design-cards/interfaces/i03-spi.md)，I²C 按 [IF-01 I²C 总线](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L102 [unknown] [ [IF-01 I²C 总线](../../design-cards/interfaces/i01-i2c.md)，NOR 细节按 [W07 SPI Flash](../../design-cards/wireless/w07-spi-flash.md) → `references/design-cards/wireless/w07-spi-flash.md` (ok)
- L102 [unknown] [W07 SPI Flash](../../design-cards/wireless/w07-spi-flash.md)，SD 备选按 [W08 microSD](../../design-cards/wireless/w08-microsd.md) → `references/design-cards/wireless/w08-microsd.md` (ok)
- L103 [unknown] [点 1 kΩ+100 nF 到 ADC；电池 100 k/100 k + P-MOS 门控；VBUS 100 k/100 k 分压。按 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量) → `references/common-hardware/a-environment.md` (ok) #a1-ntc-温度测量 ok
- L103 [unknown] [门控；VBUS 100 k/100 k 分压。按 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量)、[E1 电压采样](../e-measurement.md#e1-电压采样) → `references/common-hardware/e-measurement.md` (ok) #e1-电压采样 ok
- L103 [unknown] [/a-environment.md#a1-ntc-温度测量)、[E1 电压采样](../e-measurement.md#e1-电压采样)、[ANA-01 分压](../../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L103 [unknown] [电压采样)、[ANA-01 分压](../../design-cards/analog/a01-divider.md) 与 [ANA-04 SAR ADC 驱动](../../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L104 [unknown] [的 12 MHz 晶体、V3 0.1 µF、UD± 串阻/ESD、TXD/RXD 1 kΩ 到 MCU、DTR#/RTS# 测试点；按 [J7 USB 数据接口](../j-buses.md#j7-usb-数据接口) → `references/common-hardware/j-buses.md` (ok) #j7-usb-数据接口 ok
- L104 [unknown] [ kΩ 到 MCU、DTR#/RTS# 测试点；按 [J7 USB 数据接口](../j-buses.md#j7-usb-数据接口)、[IF-09 USB 设备](../../design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L104 [unknown] [、[IF-09 USB 设备](../../design-cards/interfaces/i09-usb-device.md)、[IF-10 USB-C 数据](../../design-cards/interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)

### `references/common-hardware/applications/12-solenoid-controller.md`

- 标题：电磁阀控制器：K4 电磁阀 + K2 高侧/K3 继电器 + F6/F7 保护 + I1 主控 + L1 指示
- 行/字符/字节：179 / 11584 / 20461
- SHA-256：`040baab4f2c707b5869007f74449fa56104e7554409a4079e06b1c4e0c191275`

- L29 [unknown] [ AC 阀 | 220 VAC 阀、要物理隔离、不能 PWM | 无峰值-保持；触点按 AC 感性负载降额；安规签核 |

推荐 A：先用 [K2 高侧开关](../k-drive.md#k2-高侧开关) → `references/common-hardware/k-drive.md` (ok) #k2-高侧开关 ok
- L29 [unknown] [2 高侧开关](../k-drive.md#k2-高侧开关) 的 TPS1H100-Q1 做总开关，提供默认关、限流和 ST 诊断；再用 [K4 电磁阀与电磁铁](../k-drive.md#k4-电磁阀与电磁铁) → `references/common-hardware/k-drive.md` (ok) #k4-电磁阀与电磁铁 ok
- L29 [unknown] [RV110 的 EN 被内部上拉误开，高侧仍可断开；高侧关断后线圈不长期带 24 V，金属阀体不因低侧开关而带电。高侧不是反接保护，反接仍要按 [F5 反接保护](../f-input-protection.md#f5-反接保护) → `references/common-hardware/f-input-protection.md` (ok) #f5-反接保护 ok
- L33 [unknown] [ A 保持电流还大，阀会抖；DRV110 用 25 kHz，纹波约 25.6 mA，才可控。

若阀是 220 VAC 或要求触点隔离，改走 [K3 继电器](../k-drive.md#k3-继电器) → `references/common-hardware/k-drive.md` (ok) #k3-继电器 ok
- L63 [unknown] [|
|---|---|---|
| `24V_IN` | 端子→2 A 延时保险→TVS→高侧 VS、Buck 输入 | 中心极性/线规按 [F4 直流端子](../f-input-protection.md#f4-直流端子与圆孔输入) → `references/common-hardware/f-input-protection.md` (ok) #f4-直流端子与圆孔输入 ok
- L88 [unknown] [没有电容性大浪涌，但 24 V 入口 bulk 的充电仍要按 I²t 核对。没有时间-电流曲线时只做量级校验，不能声称“保险丝一定先断”。[F6 过流与短路保护](../f-input-protection.md#f6-过流与短路保护) → `references/common-hardware/f-input-protection.md` (ok) #f6-过流与短路保护 ok
- L99 [unknown] [置不变→机械卡滞，必须加位置开关或流量/压力传感器才能确认，单靠电流不能证明阀芯到位。

### 5.4 指示、热与未确定项
指示按 [L1 LED 指示](../l-hmi.md#l1-led-指示) → `references/common-hardware/l-hmi.md` (ok) #l1-led-指示 ok
- L107 [unknown] [度。以上均未实测。

## 6. 原理图组织

1. **输入与保护**：连接器→2 A 延时保险→SMBJ28A→bulk；按 [F6 过流与短路保护](../f-input-protection.md#f6-过流与短路保护) → `references/common-hardware/f-input-protection.md` (ok) #f6-过流与短路保护 ok
- L107 [unknown] [险→SMBJ28A→bulk；按 [F6 过流与短路保护](../f-input-protection.md#f6-过流与短路保护) 与 [F7 过压与瞬态保护](../f-input-protection.md#f7-过压与瞬态保护) → `references/common-hardware/f-input-protection.md` (ok) #f7-过压与瞬态保护 ok
- L108 [unknown] [put-protection.md#f7-过压与瞬态保护) 的顺序，TVS 靠连接器，保险在 TVS 前。
2. **电源分配**：24 V→[G2 Buck](../g-power-conversion.md#g2-buck) → `references/common-hardware/g-power-conversion.md` (ok) #g2-buck ok
- L108 [unknown] [TVS 前。
2. **电源分配**：24 V→[G2 Buck](../g-power-conversion.md#g2-buck) 5 V→[G1 LDO](../g-power-conversion.md#g1-ldo) → `references/common-hardware/g-power-conversion.md` (ok) #g1-ldo ok
- L109 [unknown] [，Buck 输入加 bulk。
3. **高侧总开关**：TPS1H100-Q1 的 VS/OUT/IN/DIAG_EN/CL/ST 按 [DRV-02 高侧](../../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L111 [unknown] [G5LE-1 线圈用 MMBT3904 + 1N4148W，基极 1 kΩ + 10 kΩ 下拉；触点 RC/MOV 与线圈续流分开；按 [DRV-03 继电器](../../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)
- L112 [unknown] [sign-cards/drive/d03-relay.md) 与 K3 分区。
6. **主控/指示**：CH32V003 最小系统按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) → `references/common-hardware/i-mcu.md` (ok) #i1-低成本基础控制 ok

### `references/common-hardware/b-optics.md`

- 标题：B 光、接近、距离与人体检测
- 行/字符/字节：1069 / 41930 / 72841
- SHA-256：`53686f18083f1f696afbed6de7ec00ade31a986065de0ae95d6b6ff7725850ad`

- L37 [unknown] [ | 模拟/比较器 | 开集/推挽 | I²C + 中断 | 脉宽/模拟/UART |

**组级复用说明：**

- 模拟采集链统一见 [ANA-01](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L37 [unknown] [

- 模拟采集链统一见 [ANA-01](../design-cards/analog/a01-divider.md) §4.2/§4.5、[ANA-02](../design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L37 [unknown] [§4.2/§4.5、[ANA-02](../design-cards/analog/a02-opamp-buffer.md) §4.2/§4.5、[ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L38 [unknown] [c-driver.md) §4.2/§4.6；误差合成见 C1 专题。光电流源不能直接套电压源分压的源阻抗判据（见 B2）。
- 发射管驱动见 [DRV-01](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L38 [unknown] [源阻抗判据（见 B2）。
- 发射管驱动见 [DRV-01](../design-cards/drive/d01-low-side.md) 与 [DRV-07](../design-cards/drive/d07-led-cc.md) → `references/design-cards/drive/d07-led-cc.md` (ok)
- L39 [unknown] [n-cards/drive/d07-led-cc.md)；DRV-07 是连续恒流，脉冲 IR 的峰值电流/占空比/结温要另算。
- I²C 见 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L39 [unknown] [占空比/结温要另算。
- I²C 见 [IF-01](../design-cards/interfaces/i01-i2c.md)，UART 见 [IF-05](../design-cards/interfaces/i05-uart.md) → `references/design-cards/interfaces/i05-uart.md` (ok)
- L39 [unknown] [/i01-i2c.md)，UART 见 [IF-05](../design-cards/interfaces/i05-uart.md)，电平转换见 [IF-12](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L40 [unknown] [md)，电平转换见 [IF-12](../design-cards/interfaces/i12-level-shift.md)。
- 供电见 [PWR-01](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L40 [unknown] [s/i12-level-shift.md)。
- 供电见 [PWR-01](../design-cards/power/p01-ldo.md)、[PWR-02](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L40 [unknown] [、[PWR-02](../design-cards/power/p02-buck.md)；上电/复位/休眠状态表见 [module-integration.md](../module-integration.md) → `references/module-integration.md` (ok)
- L41 [unknown] [.md](../module-integration.md) §5，地址/片选/复用见 §6。
- 布局见 [pcb-placement-details.md](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L41 [unknown] [etails.md) PL07/PL21/PL22/PL24/PL26/PL27；壳体窗口/声孔/天线净空见 [enclosure-integration.md](../enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L92 [unknown] [受更大噪声。LDR 分压 `V_out = V_ref × R_bottom/(R_top+R_LDR)` 只适合相对检测：亮/暗阻跨几个数量级，[ANA-01](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L178 [unknown] [V_out = V_ref + I_ph × Rf`（光电流从二极管流入 IN−，输出为正）。反偏时后级要 AC 耦合/电平搬移；输出 RC 按 [ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L374 [unknown] [9-08-17）：Product Summary、Basic Characteristics、Fig.1/6/9、封装。
- 发射驱动拓扑复用 [DRV-01](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L374 [unknown] [发射驱动拓扑复用 [DRV-01](../design-cards/drive/d01-low-side.md) §3–§5；连续 LED 对照 [DRV-07](../design-cards/drive/d07-led-cc.md) → `references/design-cards/drive/d07-led-cc.md` (ok)
- L375 [unknown] [ [DRV-07](../design-cards/drive/d07-led-cc.md)，但脉冲参数不能套。
- 接收 ADC/比较器复用 [ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L375 [unknown] [ADC/比较器复用 [ANA-04](../design-cards/analog/a04-adc-driver.md) §4.2/§4.6 与 [ANA-02](../design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L501 [unknown] [uct Summary、Absolute Maximum、Basic Characteristics、Fig.2/3、封装。
- 发射驱动复用 [DRV-01](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L501 [unknown] [射驱动复用 [DRV-01](../design-cards/drive/d01-low-side.md) §3–§5；MCU 定时器/中断复用 [MCU-01](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L502 [unknown] [./design-cards/mcu/m01-bare-mcu.md)。
- 状态表（复位/休眠时输出电平）复用 [module-integration.md](../module-integration.md) → `references/module-integration.md` (ok)
- L631 [unknown] [ea、Maximum rated values、Electrical characteristics、Timing chart。
- 供电复用 [PWR-01](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L631 [unknown] [iming chart。
- 供电复用 [PWR-01](../design-cards/power/p01-ldo.md)；MCU 唤醒复用 [MCU-02](../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L631 [unknown] [[MCU-02](../design-cards/mcu/m02-module-mcu.md)；外壳窗口复用 [enclosure-integration.md](../enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L758 [unknown] [8）：§2.3 引脚、§2.4 应用图/上拉表、§3.4 校准、§3.5 量程、§3.6 上电、§6 电特性、§7 激光安全。
- I²C 复用 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L758 [unknown] [特性、§7 激光安全。
- I²C 复用 [IF-01](../design-cards/interfaces/i01-i2c.md)，电平复用 [IF-12](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L758 [unknown] [)，电平复用 [IF-12](../design-cards/interfaces/i12-level-shift.md)，2.8 V 供电复用 [PWR-01](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L889 [unknown] [4R DM-U16-483 Rev.2, 2017-08）：40 kHz、SPL、电容、最大输入、室内限制。
- MCU 定时器/输入捕获复用 [MCU-01](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L889 [unknown] [MCU 定时器/输入捕获复用 [MCU-01](../design-cards/mcu/m01-bare-mcu.md)；5 V→3.3 V 复用 [IF-12](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)

### `references/common-hardware/c-motion.md`

- 标题：C 运动、位置、转速与角度
- 行/字符/字节：877 / 44622 / 80485
- SHA-256：`a3001b36f239fd8561566bf764333d2fd4fc4cfdf3b80666ce2b8009d5503210`

- L19 [unknown] [内分工

- **C1 只写加速度计产品化**：量程/噪声/ODR/零偏、倾角算法、六面校准、安装方向。模拟输出的 ADC 驱动与误差预算见 [ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L19 [unknown] [方向。模拟输出的 ADC 驱动与误差预算见 [ANA-04](../design-cards/analog/a04-adc-driver.md)、[ANA-05](../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L19 [unknown] [analog/a04-adc-driver.md)、[ANA-05](../design-cards/analog/a05-vref.md) 与 [C1 误差链](../engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok)
- L20 [unknown] [.md)。
- **C2 写陀螺/IMU 的增量**：6 轴/9 轴取舍、零偏与积分漂移、融合边界、双 IMU 片选/总线冲突；I²C 掉电拖总线见 [F28](../failures/f28-i2c-unpowered-device-lockup.md) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok)
- L20 [unknown] [/总线冲突；I²C 掉电拖总线见 [F28](../failures/f28-i2c-unpowered-device-lockup.md)，组合约束见 [D1](../engineering-deepdives/topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L23 [unknown] [尔电流传感器不在本组。
- **C5 写编码器**：机械增量、光学增量、磁绝对；正交解码、去抖、PPR 与档位、绝对角度延迟。闭环控制稳定性见 [DRV-05](../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L23 [unknown] [、PPR 与档位、绝对角度延迟。闭环控制稳定性见 [DRV-05](../design-cards/drive/d05-h-bridge.md)/[DRV-06](../design-cards/drive/d06-stepper.md) → `references/design-cards/drive/d06-stepper.md` (ok)
- L37 [example] [-04（多从机/片选）、IF-12（电平转换）、`examples/x05-i2c.md`；上拉所有权、反灌与地址冲突见 [module-integration](../module-integration.md) → `references/module-integration.md` (ok)
- L38 [unknown] [ion](../module-integration.md) §4/§6/§8。
- 模拟输出：ANA-01/02/04/05 与 [传感器到 ADC 误差链](../engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok)
- L39 [unknown] [（MEMS 机械应力）、DM24（传感器物理条件）、PL07（开孔与外壳一起定位）、MF16（MSL/回流/清洗）、[enclosure-integration](../enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L40 [unknown] [ion](../enclosure-integration.md)。
- 24 V 输入与保护：DM26、SC37、F30（上电默认态）；电机干扰见 [F26](../failures/f26-motor-start-corrupts-adc.md) → `references/failures/f26-motor-start-corrupts-adc.md` (ok)

### `references/common-hardware/d-force.md`

- 标题：D 力、重量、压力、液位与流量
- 行/字符/字节：990 / 50146 / 89994
- SHA-256：`cce9e48fcda15dffcbf67fca099ea68ad31f4f725c7238cc4dcad1508256a413`

- L19 [unknown] [偏载/蠕变/校准、HX711/ADS1232 的增益与激励约束、固件流程。桥式灵敏度、四/六线、比率测量、INA 共模/CMRR、误差预算一律见 [ANA-09](../design-cards/analog/a09-bridge.md) → `references/design-cards/analog/a09-bridge.md` (ok)
- L20 [unknown] [**：表压/绝压/差压、proof/burst、介质、端口、5 V 输出进 3.3 V ADC、比率接法与保护。分压/缓冲/ADC 建立/基准见 [ANA-01](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L20 [unknown] [比率接法与保护。分压/缓冲/ADC 建立/基准见 [ANA-01](../design-cards/analog/a01-divider.md)、[ANA-02](../design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L20 [unknown] [log/a01-divider.md)、[ANA-02](../design-cards/analog/a02-opamp-buffer.md)、[ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L20 [unknown] [/a02-opamp-buffer.md)、[ANA-04](../design-cards/analog/a04-adc-driver.md)、[ANA-05](../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L21 [unknown] [数字压力**：BMP388/MS5837/SDP810 的选型、地址/strap、气路/介质、过采样/转换时间、补偿与验证。I²C/SPI/电平见 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L21 [unknown] [过采样/转换时间、补偿与验证。I²C/SPI/电平见 [IF-01](../design-cards/interfaces/i01-i2c.md)、[IF-03](../design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L21 [unknown] [rds/interfaces/i01-i2c.md)、[IF-03](../design-cards/interfaces/i03-spi.md)、[IF-12](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L23 [unknown] [、接触/非接触、死区/泡沫/蒸汽、泵控状态机与故障安全。
- **D5 写土壤与介质湿度**：探头类型、真实介质标定、盐分/温度/腐蚀；产品级验收见 [S01](../task-scenarios.md) → `references/task-scenarios.md` (ok)
- L23 [unknown] [**：探头类型、真实介质标定、盐分/温度/腐蚀；产品级验收见 [S01](../task-scenarios.md) 与 [product-acceptance](../product-acceptance.md) → `references/product-acceptance.md` (ok)
- L25 [unknown] [过程量接口增量**：0–10 V 输入/保护、差压流量平方律、液位 4/20 mA 标定、NAMUR/HART 边界；4–20 mA 电气核算见 [ANA-08](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L46 [unknown] [桥

电子秤的难点通常不在 ADC 位数，而在“容量选型、安装应力、蠕变/温漂、两点校准”四件事。桥式灵敏度、四/六线、比率测量与误差预算见 [ANA-09](../design-cards/analog/a09-bridge.md) → `references/design-cards/analog/a09-bridge.md` (ok)
- L469 [unknown] [绝压型用绝对压力减当时大气压。共性：入口 ESD/TVS；泵/继电器续流与 RC（DRV-03）；液位与泵电源分地；长电缆考虑压降与地电位差。见 [ANA-08](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L558 [unknown] [DC/0.5 A、SG 0.7、M10、5–6 in-lb。
- 水深/绝压复用 D3（MS5837，CHW-S067）；4–20 mA 复用 [ANA-08](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L558 [unknown] [design-cards/analog/a08-4-20ma.md)；泵/继电器复用 DRV-03；密封/凝露复用 [enclosure-integration](../enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L689 [unknown] [ g/76 g→18.4%。
- SEN0193/VH400/EC-5 仅为候选（E2），未取得并核对原厂手册；不能把其参数写成保证值。产品级验收见 [S01](../task-scenarios.md) → `references/task-scenarios.md` (ok)
- L689 [unknown] [2），未取得并核对原厂手册；不能把其参数写成保证值。产品级验收见 [S01](../task-scenarios.md)、[product-acceptance](../product-acceptance.md) → `references/product-acceptance.md` (ok)
- L689 [unknown] [/task-scenarios.md)、[product-acceptance](../product-acceptance.md)；模拟前端见 [ANA-01](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L689 [unknown] [uct-acceptance.md)；模拟前端见 [ANA-01](../design-cards/analog/a01-divider.md)、[ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L689 [unknown] [divider.md)、[ANA-04](../design-cards/analog/a04-adc-driver.md)；4–20 mA 见 [ANA-08](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L820 [unknown] [/黄/黑三线。手册为翻译件，存在“four lead”与 3 线、5–24 V 与 5–18 V 等矛盾，按最保守值设计并实测。
- 电平转换见 [IF-12](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L820 [unknown] [rds/interfaces/i12-level-shift.md)；泵/继电器噪声见 F26、DRV-03；4–20 mA 流量变送器见 D7/[ANA-08](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L921 [unknown] [（2.25–5.5 V、1 A、420 kHz）。
- 4–20 mA 电气核算、两/三/四线、compliance、采样电阻、隔离/保护：见 [ANA-08](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L921 [unknown] [：见 [ANA-08](../design-cards/analog/a08-4-20ma.md) §3–§5、§7–§9；0–10 V 分压见 [ANA-01](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L921 [unknown] [§9；0–10 V 分压见 [ANA-01](../design-cards/analog/a01-divider.md)；ADC 驱动/基准见 [ANA-04](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L921 [unknown] [ivider.md)；ADC 驱动/基准见 [ANA-04](../design-cards/analog/a04-adc-driver.md)、[ANA-05](../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)

### `references/common-hardware/e-measurement.md`

- 标题：E 电压、电流与电能测量
- 行/字符/字节：820 / 46094 / 77707
- SHA-256：`a9d67ecc2b53ebfa720574cfc7a669bb3ed790485f0790b38d15738a8e8242d5`

- L27 [unknown] [功能安全等级。

## 组级复用说明

| 已有内容 | 本组怎么用 | 不要重复什么 |
|---|---|---|
| [ANA-01 分压采样](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L28 [unknown] [/a01-divider.md) | E1 的分压比、戴维南电阻、采集时间、误差预算主卡 | 不重写分压公式与 LSB 推导 |
| [ANA-02 运放缓冲](../design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L28 [unknown] [推导 |
| [ANA-02 运放缓冲](../design-cards/analog/a02-opamp-buffer.md)、[ANA-04 ADC 驱动](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L28 [unknown] [-buffer.md)、[ANA-04 ADC 驱动](../design-cards/analog/a04-adc-driver.md)、[ANA-05 基准](../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L29 [example] [log/a05-vref.md) | E1/E7 的高阻缓冲、SAR 建立、基准误差 | 不复制运放稳定性与基准噪声理论 |
| [ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L29 [example] [准噪声理论 |
| [ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md)、[X09 范例](../examples/x09-current-sense.md) → `references/examples/x09-current-sense.md` (ok)
- L29 [example] [analog/a06-low-side-sense.md)、[X09 范例](../examples/x09-current-sense.md)、[F01 故障](../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L30 [unknown] [sitic.md) | E2 的 R_SH/增益/Kelvin/地差主卡与真实修订案例 | 不重写低侧传递函数与误差预算 |
| [ANA-07 高侧电流采样](../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L30 [unknown] [|
| [ANA-07 高侧电流采样](../design-cards/analog/a07-high-side-sense.md)、[ANA-03 差分放大](../design-cards/analog/a03-diff-amp.md) → `references/design-cards/analog/a03-diff-amp.md` (ok)
- L31 [unknown] [ | E3 的共模/CMRR/隔离判断主卡；E3 必须用修正后的失调数值 | 不复制高侧公式；不沿用 10 mA 错误 |
| [ANA-08 4–20 mA](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L31 [unknown] [10 mA 错误 |
| [ANA-08 4–20 mA](../design-cards/analog/a08-4-20ma.md)、[P02 工业接口项目](../projects/p02-industrial-rs485-analog.md) → `references/projects/p02-industrial-rs485-analog.md` (ok)
- L32 [unknown] [md) | E2 的 4–20 mA 低侧 100 Ω 分流与 compliance | 不把 RCV420 旧例当现代直连方案 |
| [B2 睡眠电流预算](../engineering-deepdives/topics/b2-sleep-current-budget.md) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok)
- L32 [unknown] [2 睡眠电流预算](../engineering-deepdives/topics/b2-sleep-current-budget.md)、[P01 低功耗节点](../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L32 [unknown] [nt-budget.md)、[P01 低功耗节点](../projects/p01-low-power-wireless-sensor.md)、[B1 电源路径](../engineering-deepdives/topics/b1-power-path-and-source-switching.md) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok)
- L33 [unknown] [and-source-switching.md) | E1 的门控分压、电池采样、母线检测实例 | 不重算已有 µA 预算 |
| [B3 充电/负载/电量计](../engineering-deepdives/topics/b3-charger-load-and-gauge.md) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok)
- L34 [unknown] [ge.md) | E6 的电压法/库仑计/Impedance Track 误差源与 BQ27441 证据 | 不复制 B3 的充电算例 |
| [C1 误差链](../engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok)
- L34 [unknown] [1 误差链](../engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md)、[C4 测量假象](../engineering-deepdives/topics/c4-measurement-artifacts.md) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok)
- L34 [unknown] [、[C4 测量假象](../engineering-deepdives/topics/c4-measurement-artifacts.md)、[C2 接地屏蔽](../engineering-deepdives/topics/c2-grounding-shielding-common-mode.md) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok)
- L35 [unknown] [elding-common-mode.md) | 各主题的共模、探头、地弹与误差合成 | 不把探头 CMRR 当电路 CMRR |
| [F22 ADC 建立](../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L35 [unknown] [ CMRR 当电路 CMRR |
| [F22 ADC 建立](../failures/f22-adc-settling.md)、[analog-adc 计算](../calculations/analog-adc.md) → `references/calculations/analog-adc.md` (ok)
- L36 [unknown] [ions/analog-adc.md) | E7 的通道切换拖尾、扫描率与抗混叠冲突 | 不重复单通道建立公式 |
| [selection/passives](../selection/passives.md) → `references/selection/passives.md` (ok)
- L36 [unknown] [ | 不重复单通道建立公式 |
| [selection/passives](../selection/passives.md)、[lcsc-sourcing](../lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L73 [unknown] [10 mA；OPA320 20 MHz、0.9 pA max、150 µV max。
### 原理图与逐脚
- 分压/C_ext/保护画法见 [ANA-01](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L73 [unknown] [
- 分压/C_ext/保护画法见 [ANA-01](../design-cards/analog/a01-divider.md) §8；缓冲见 [ANA-02](../design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)

### `references/common-hardware/f-input-protection.md`

- 标题：常用硬件：常用低压供电入口与保护（F 组）
- 行/字符/字节：1001 / 41111 / 72702
- SHA-256：`010b6534b8297c58cddcb670781dadc1a7a6b674f92f7efa2822e363369e5e0f`

### `references/common-hardware/g-power-conversion.md`

- 标题：常用硬件：电源转换与分配（G 组）
- 行/字符/字节：1224 / 56690 / 98007
- SHA-256：`106e3967e988e841aaaa72f5c8ff11b9639ee948359699d99408948507a6463b`

- L47 [unknown] [论先行：LDO 先过三关——最低输入时压差够、最坏输入时结温够、输出电容落在器件稳定窗口内；三关都过，才谈 PSRR/噪声。功率级与算例主体仍用 [PWR-01](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L171 [unknown] [130/269.5 µVRMS 是 typ 曲线值，不是保证值。

## G2 Buck（降压变换器）

结论先行：Buck 的功率级按 [PWR-02](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L292 [required_read] [ 时 2.7 A min 约可出 1.91 A，不是 0.84 A。实际能出多少还要同时受热、输入源限流、最大占空比和最小关断时间限制。本主题以 [PWR-03](../design-cards/power/p03-boost.md) → `references/design-cards/power/p03-boost.md` (ok)
- L420 [unknown] [关非反相 Buck-Boost 用一颗电感同时覆盖 Buck/Boost；峰值出现在**最低输入**，模式和效率最差点在输入≈输出附近。本主题以 [PWR-04](../design-cards/power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L984 [unknown] [02；本主题不重复其 SOA/保险丝/理想二极管公式。

## G8 多路电源与电源切换

结论先行：多源切换（谁供谁、会不会倒灌）已有 [PWR-05](../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)

### `references/common-hardware/h-battery.md`

- 标题：H 电池、充电与低功耗设备
- 行/字符/字节：868 / 53295 / 95232
- SHA-256：`603a1f7f569fb906b47fdff42e34c61117a39bea3b35760b44c505fbe6027ce9`

- L28 [unknown] [→ H5。
4. 最后问“待机多久/要不要显示电量”。要 → H7/H8。

### 组级复用说明

- **充电主线：** [PWR-06 线性充电](../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L28 [unknown] [主线：** [PWR-06 线性充电](../design-cards/power/p06-linear-charger.md)、[PWR-07 开关/NVDC](../design-cards/power/p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L28 [unknown] [d)、[PWR-07 开关/NVDC](../design-cards/power/p07-switching-charger.md)、[B3 充电/负载/电量](../engineering-deepdives/topics/b3-charger-load-and-gauge.md) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok)
- L29 [unknown] [ent、NTC、终止/再充的公式和算例以这三份为准；H2/H3 只补型号、引脚、固件、测试矩阵和采购字段。
- **保护主线：** [PWR-08 1S 保护](../design-cards/power/p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L29 [unknown] [** [PWR-08 1S 保护](../design-cards/power/p08-battery-protection.md)、[B3 §3.1/§5.3](../engineering-deepdives/topics/b3-charger-load-and-gauge.md) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok)
- L30 [unknown] [-08 只覆盖 1S，多节必须转 H5；它的标题“1S 电池保护与 BMS”容易误导，见 99-fixes。
- **多源主线：** [PWR-05 多源供电](../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L30 [unknown] [- **多源主线：** [PWR-05 多源供电](../design-cards/power/p05-power-mux.md)、[B1 power path](../engineering-deepdives/topics/b1-power-path-and-source-switching.md) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok)
- L31 [required_read] [P vs RCB、反灌、优先级门限以 B1/PWR-05 为准；H6 只补 TPS2121 型号和固件状态机。
- **低功耗主线：** [B2 睡眠电流预算](../engineering-deepdives/topics/b2-sleep-current-budget.md) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok)
- L31 [required_read] [眠电流预算](../engineering-deepdives/topics/b2-sleep-current-budget.md)、[P01 低功耗无线传感器](../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L32 [required_read] [AA/纽扣/ER14250 时必须按 H1 重算；P01 的 25 µA 是设计上限，不是实测。
- **一次电池反例：** [F02 两节 AA 经 LDO](../failures/f02-two-aa-ldo.md) → `references/failures/f02-two-aa-ldo.md` (ok)
- L32 [required_read] [ **一次电池反例：** [F02 两节 AA 经 LDO](../failures/f02-two-aa-ldo.md) 是 H1 的必读反例；[P01 §2](../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L33 [unknown] [.md) 的“2×AA+Boost”淘汰理由只覆盖一条峰值场景，不能替代 H1 的整条曲线方法。
- **能量/串并公式：** [energy-battery](../calculations/energy-battery.md) → `references/calculations/energy-battery.md` (ok)

### `references/common-hardware/i-mcu.md`

- 标题：I 常见主控与最小系统
- 行/字符/字节：914 / 47733 / 81442
- SHA-256：`fd67b188de6553305edfad44372eb1958449618d58626107404c9749d751f901`

### `references/common-hardware/j-buses.md`

- 标题：J 数字总线与常见有线通信
- 行/字符/字节：1298 / 64550 / 111795
- SHA-256：`3e340591ab59816272a817204e5fce933a3578e68651e96f210667cc7a1a2951`

- L24 [unknown] [VS，避免重复添加或把模块的 5 V 输出直接灌进 3.3 V 器件。
3. **总线电气引用既有卡，不在这里重算。** I²C 上拉/Cb 见 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L24 [unknown] [里重算。** I²C 上拉/Cb 见 [IF-01](../design-cards/interfaces/i01-i2c.md)；I²C 分段见 [IF-02](../design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L24 [unknown] [；I²C 分段见 [IF-02](../design-cards/interfaces/i02-i2c-buffer.md)；SPI 模式/时序见 [IF-03](../design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L24 [unknown] [2c-buffer.md)；SPI 模式/时序见 [IF-03](../design-cards/interfaces/i03-spi.md) 与 [IF-04](../design-cards/interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L24 [unknown] [i.md) 与 [IF-04](../design-cards/interfaces/i04-spi-multi.md)；UART 位时间/电平见 [IF-05](../design-cards/interfaces/i05-uart.md) → `references/design-cards/interfaces/i05-uart.md` (ok)
- L24 [unknown] [；UART 位时间/电平见 [IF-05](../design-cards/interfaces/i05-uart.md)；RS-232 电荷泵见 [IF-06](../design-cards/interfaces/i06-rs232.md) → `references/design-cards/interfaces/i06-rs232.md` (ok)
- L24 [unknown] [S-232 电荷泵见 [IF-06](../design-cards/interfaces/i06-rs232.md)；RS-485 端接/偏置见 [IF-07](../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L24 [unknown] [RS-485 端接/偏置见 [IF-07](../design-cards/interfaces/i07-rs485.md)；CAN 端接/支线见 [IF-08](../design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L24 [unknown] [md)；CAN 端接/支线见 [IF-08](../design-cards/interfaces/i08-can.md)；USB 设备/CC 见 [IF-09](../design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L24 [unknown] [n.md)；USB 设备/CC 见 [IF-09](../design-cards/interfaces/i09-usb-device.md) 与 [IF-10](../design-cards/interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)
- L24 [unknown] [vice.md) 与 [IF-10](../design-cards/interfaces/i10-usbc-data.md)；以太网 PHY 见 [IF-11](../design-cards/interfaces/i11-ethernet.md) → `references/design-cards/interfaces/i11-ethernet.md` (ok)
- L24 [unknown] [a.md)；以太网 PHY 见 [IF-11](../design-cards/interfaces/i11-ethernet.md)；电平转换见 [IF-12](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L35 [unknown] [四件事：地址够不够、速率/转换时间够不够、支持脚（INT/WP/RESET/地址脚）是否接全、模块是否已经自带稳压/上拉/电平转换。总线电气全部按 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L37 [example] [5 SCPS200E §1/§6/§9.4）；E2（AT24C02C 与具体 OLED/RTC 型号未核对）；复用 IF-01/IF-02/IF-12、[x05](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L169 [unknown] [补支持脚：Flash 的 WP/HOLD/QE、SD 卡的电源/卡检测、显示的 RESET/背光、ADC 的基准/输入缓冲。总线时序与多从机争用按 [IF-03](../design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L169 [unknown] [光、ADC 的基准/输入缓冲。总线时序与多从机争用按 [IF-03](../design-cards/interfaces/i03-spi.md)/[IF-04](../design-cards/interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L171 [unknown] [5/§6、Electrical Characteristics）；E2（SD 卡、SPI TFT 模组的具体型号未核对）；复用 IF-03/IF-04、[w05](../design-cards/wireless/w05-display.md) → `references/design-cards/wireless/w05-display.md` (ok)
- L171 [unknown] [T 模组的具体型号未核对）；复用 IF-03/IF-04、[w05](../design-cards/wireless/w05-display.md)/[w07](../design-cards/wireless/w07-spi-flash.md) → `references/design-cards/wireless/w07-spi-flash.md` (ok)
- L171 [unknown] [s/wireless/w05-display.md)/[w07](../design-cards/wireless/w07-spi-flash.md)/[w08](../design-cards/wireless/w08-microsd.md) → `references/design-cards/wireless/w08-microsd.md` (ok)
- L307 [background] [232/RS-485 等外部物理层。桥片/模组选型先看驱动、VIO、DTR/RTS、峰值电流与天线/认证；UART 位时间、电平判据、RX 上拉按 [IF-05](../design-cards/interfaces/i05-uart.md) → `references/design-cards/interfaces/i05-uart.md` (ok)
- L448 [required_read] [DB9 的针序、DTE/DCE 角色和 null modem 接法必须按对端手册核对，不能套“常见 2/3/5”。MAX3232 的电荷泵与摆幅按 [IF-06](../design-cards/interfaces/i06-rs232.md) → `references/design-cards/interfaces/i06-rs232.md` (ok)
- L591 [unknown] [：** RS-485 选型先定四件事：3.3 V 还是 5 V 逻辑、半双工还是全双工、非隔离还是隔离、内部失效保护还是外部偏置。端接/偏置公式按 [IF-07](../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L593 [example] [§7.7 Electrical Characteristics）；E2（SP3485/MAX485/ADM2483 具体参数未核对）；复用 IF-07、[x06](../examples/x06-rs485.md) → `references/examples/x06-rs485.md` (ok)
- L739 [unknown] [ / 容错 CAN / 隔离 CAN”，再分“控制器在 MCU 内 / 外置 SPI 控制器 / 收发器带 VIO”。端接、支线、共模、故障功率按 [IF-08](../design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L741 [example] [7.1/§7.3）；E2（MCP2515/MCP2518FD、TJA1051、ISO1042 未核对；CAN FD 标准正文未取得）；复用 IF-08、[x07](../examples/x07-can.md) → `references/examples/x07-can.md` (ok)
- L880 [unknown] [/ host / OTG / hub），再定速度（FS / HS）与连接器（Type-C / micro-B / A）。设备侧 FS/CC 电气按 [IF-09](../design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L880 [unknown] [ / A）。设备侧 FS/CC 电气按 [IF-09](../design-cards/interfaces/i09-usb-device.md)/[IF-10](../design-cards/interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)
- L882 [example] [（USB-C 24-pin 映射、USBLC6-2SC6、host 电源开关具体型号未核对）；复用 IF-09/IF-10、PWR-12/PWR-13、[x08](../examples/x08-usbc.md) → `references/examples/x08-usbc.md` (ok)
- L1031 [unknown] [AN8720A 要 RMII 50 MHz 时钟/RBIAS/49.9 Ω 串联/75 Ω Bob Smith。MDI 阻抗、磁性挖空、中心抽头按 [IF-11](../design-cards/interfaces/i11-ethernet.md) → `references/design-cards/interfaces/i11-ethernet.md` (ok)

### `references/common-hardware/k-drive.md`

- 标题：K 开关、继电器与电机负载
- 行/字符/字节：860 / 44499 / 86563
- SHA-256：`a3e11cf65a1d3aca605a66c9cd1493d05d8adccb9748619a30e345509878a9a1`

- L28 [unknown] [没有独立过温链 | 低侧/高侧 MOS、SSR、独立硬件切断 | K9 |

### 组级复用说明

- **功率级不重复写**：低侧见 [DRV-01](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L28 [unknown] [

- **功率级不重复写**：低侧见 [DRV-01](../design-cards/drive/d01-low-side.md)，高侧见 [DRV-02](../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L28 [unknown] [1-low-side.md)，高侧见 [DRV-02](../design-cards/drive/d02-high-side.md)，继电器见 [DRV-03](../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)
- L28 [unknown] [d02-high-side.md)，继电器见 [DRV-03](../design-cards/drive/d03-relay.md)，H 桥见 [DRV-05](../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L28 [unknown] [e/d03-relay.md)，H 桥见 [DRV-05](../design-cards/drive/d05-h-bridge.md)，步进见 [DRV-06](../design-cards/drive/d06-stepper.md) → `references/design-cards/drive/d06-stepper.md` (ok)
- L28 [unknown] [d05-h-bridge.md)，步进见 [DRV-06](../design-cards/drive/d06-stepper.md)，加热器见 [DRV-08](../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L29 [unknown] [-cards/drive/d08-heater.md)。本组只写“该主题特有的选择、接口、时序与验证”。
- **能量去向统一看** [E1 感性负载能量路径](../engineering-deepdives/topics/e1-inductive-load-energy-path.md) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok)
- L61 [unknown] [` 与最高 `T_J`、`Q_g`、`V_GS(th)`、SOA、`Z_thJC`。缺 `R_DS(on)` 保证值或 SOA 时不能选型，详见 [DRV-01](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L65 [unknown] [源极`，续流二极管跨在负载两端（阴极接 V+）。体二极管方向是源极→漏极，感性关断时反偏，不能替代外部续流。完整拓扑与四种钳位见 DRV-01 §3 与 [E1](../engineering-deepdives/topics/e1-inductive-load-energy-path.md) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok)
- L838 [unknown] [证上界，也不能由 max=5 ms 推断物理上不可能达成 5 ms。具体钳位、温度、负载下的触点释放与弹跳待核，当前 5 ms 目标未验证。详见 [DRV-03](../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)

### `references/common-hardware/l-hmi.md`

- 标题：L 显示、声音、按键与交互
- 行/字符/字节：805 / 45976 / 86586
- SHA-256：`3c3e91897e006b48c3c0068aa91ea0283f10c4325dc6b63d49f8408810eac805`

- L28 [unknown] [乐；供电/负载 | PWM+RC+功放 / I2S 功放 | L9 |

### 组级复用说明

- **LED 恒流、热与多串**：见 [DRV-07](../design-cards/drive/d07-led-cc.md) → `references/design-cards/drive/d07-led-cc.md` (ok)
- L29 [unknown] [ed-cc.md) §1–§6；L1 只写“指示”这一档的限流、亮度与多路/灯带边界，不重抄恒流公式。
- **TFT 接口、复位与背光**：见 [RF-05](../design-cards/wireless/w05-display.md) → `references/design-cards/wireless/w05-display.md` (ok)
- L30 [unknown] [display.md) §3–§5、§7–§9；L4 只补“选屏、带宽、程序与采购”。
- **Class-D 输出级、LC 与 EMI**：见 [RF-06](../design-cards/wireless/w06-classd.md) → `references/design-cards/wireless/w06-classd.md` (ok)
- L31 [unknown] [w06-classd.md) §3–§5、§9；L9 只补“路线、功放/扬声器选型、声学与程序”。
- **I²C 上拉/总线电容/地址**：见 [IF-01](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L31 [unknown] [[IF-01](../design-cards/interfaces/i01-i2c.md)；OLED、触摸 IC 的“模块自带还是主板再加”统一按 [模块集成](../module-integration.md) → `references/module-integration.md` (ok)
- L32 [unknown] [是主板再加”统一按 [模块集成](../module-integration.md) §10 去重。
- **SPI 时序/片选/多从机**：见 [IF-03](../design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L33 [unknown] [9 的时钟上限按各自手册再核。
- **电平转换**：3.3 V MCU 驱动 5 V 模块（TM1637、WS2812B、1602 背板）先过 [IF-12](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L35 [unknown] [复添加或把模块行为当芯片保证值。
- **默认态与低功耗**：按键/触摸/编码器的上拉、常开分压、LED 电源灯都会进入休眠预算；统一看 [b2 休眠电流预算](../engineering-deepdives/topics/b2-sleep-current-budget.md) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok)

### `references/common-hardware/m-wireless-time.md`

- 标题：M 无线、时间与常用功能模块
- 行/字符/字节：1043 / 49047 / 83595
- SHA-256：`8da609ffd08cc24968c104d161668accd82ee0c0f3580d7a5d13077297d716ab`

- L26 [unknown] [签收。

### 组级复用（不要重复抄）

- **Wi-Fi/BLE 模组上板、EN/strap、峰值储能、2.4 GHz 天线**：见 [RF-01](../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L26 [unknown] [rap、峰值储能、2.4 GHz 天线**：见 [RF-01](../design-cards/wireless/w01-wifi-ble.md)、[RF-02](../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L27 [unknown] [cards/wireless/w02-antenna.md)；本组只补路线、BLE 专项、配网与采购。
- **蜂窝 VBAT 脉冲供电**：见 [RF-03](../design-cards/wireless/w03-cellular.md) → `references/design-cards/wireless/w03-cellular.md` (ok)
- L28 [unknown] [reless/w03-cellular.md)；本组只补制式路线、SIM/eSIM、接口与认证边界。
- **GNSS 天线/NF/屏蔽**：见 [RF-04](../design-cards/wireless/w04-gnss.md) → `references/design-cards/wireless/w04-gnss.md` (ok)
- L29 [unknown] [ign-cards/wireless/w04-gnss.md)；本组只补模组选型、PPS、备份与 TTFF。
- **RTC 备份能量**：见 [PWR-14](../design-cards/power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L29 [unknown] [4](../design-cards/power/p14-supercap-backup.md)；**32.768 kHz 晶体/ppm**：见 [MCU-05](../design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L30 [unknown] [rystal.md) 与 D2；本主题只补 RTC 芯片级设计与 ppm→秒差。
- **隔离边界检查**：见 SC38、RT10、DM45/DM46、[C2](../engineering-deepdives/topics/c2-grounding-shielding-common-mode.md) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok)
- L31 [unknown] [ing-shielding-common-mode.md)；本组只补隔离器选型、CMTI/延时/默认态与隔离电源。
- **整机集成与认证责任**：见 [D4](../engineering-deepdives/topics/d4-wireless-integration.md) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok)

### `references/connectivity.md`

- 标题：离线连接表与自检契约
- 行/字符/字节：28 / 1379 / 3059
- SHA-256：`efb8619e409dfa47bc23b4411f17937f800b9b838f51944e28fa757c795f73de`

- L6 [example] [换格式，不是任何EDA工具的原生格式。优先沿用项目/执行器已有权威数据，按字段明确映射后再检查；不要维护两份互不一致的权威网络。

## 输入
见 [示例](../assets/example-connectivity.json) → `assets/example-connectivity.json` (ok)

### `references/decisions/README.md`

- 标题：工程设计决策库（A–L）
- 行/字符/字节：133 / 8809 / 13221
- SHA-256：`c1b3c0565d8d0ca7553a55ce603cce6274de2fe790e11d556ac6c7c3523cf462`

- L7 [unknown] [are_execution: NOT RUN`。模板、脚本、索引通过只证明结构与记录自洽，不证明器件、板子、制造或样机已验证。
>
> 不替代：[组合与接口契约](../module-integration.md) → `references/module-integration.md` (ok)
- L7 [unknown] [，不证明器件、板子、制造或样机已验证。
>
> 不替代：[组合与接口契约](../module-integration.md) 的 12 条判据、[项目关联记录](../project-coherence.md) → `references/project-coherence.md` (ok)
- L7 [unknown] [module-integration.md) 的 12 条判据、[项目关联记录](../project-coherence.md) 的变更传播、[选型与装配变体](../part-selection.md) → `references/part-selection.md` (ok)
- L7 [unknown] [录](../project-coherence.md) 的变更传播、[选型与装配变体](../part-selection.md) 的 DNP 原则、[计算手册](../calculations/README.md) → `references/calculations/README.md` (ok)
- L7 [unknown] [体](../part-selection.md) 的 DNP 原则、[计算手册](../calculations/README.md) 的公式与算例、[设计卡库](../design-cards/README.md) → `references/design-cards/README.md` (ok)
- L7 [unknown] [册](../calculations/README.md) 的公式与算例、[设计卡库](../design-cards/README.md) 的拓扑、[项目样本](../projects/README.md) → `references/projects/README.md` (ok)
- L36 [unknown] [ 十二个工作包

| 包 | 参考 | 一句话 | 主要案例 | 脚本 |
|---|---|---|---|---|
| A | [R4-A01 架构决策记录](a01-architecture-decision.md) → `references/decisions/a01-architecture-decision.md` (ok)
- L37 [unknown] [chitecture-decision.md) | 备选、排除判据、代价、冻结与重评 | A01、A02 | — |
| B | [R4-B01 引脚与资源规划](b01-pin-resource-planning.md) → `references/decisions/b01-pin-resource-planning.md` (ok)
- L38 [unknown] [.md) | 分配顺序、冲突检查、换型号/封装 diff | B01 | `pin_plan_check.py` |
| C | [R4-C01 工作状态与转换](c01-state-transition-contract.md) → `references/decisions/c01-state-transition-contract.md` (ok)
- L39 [unknown] [-contract.md) | 三轴、entry/exit/completion、恢复与 POR | C01 | — |
| D | [R4-D 容差与最坏情况](d01-tolerance-and-worst-case.md) → `references/decisions/d01-tolerance-and-worst-case.md` (ok)
- L40 [unknown] [lerance-and-worst-case.md) | 逐项预算、角点同时性、主导项→动作 | D01 | — |
| E | [R4-E01 跨模块接口契约](e01-interface-contract.md) → `references/decisions/e01-interface-contract.md` (ok)
- L41 [unknown] [t.md) | 一条接口一行、阻断、stale | E01 | `interface_contract_check.py` |
| F | [R4-F 整机线束](f01-harness-and-board-external.md) → `references/decisions/f01-harness-and-board-external.md` (ok)
- L42 [unknown] [rd-external.md) | 线束包、配对件、逐线记录、防误接 | F01 | `harness_check.py` |
| G | [R4-G 产品变体](g01-product-variants.md) → `references/decisions/g01-product-variants.md` (ok)
- L43 [unknown] [requires/conflicts/forbidden 闭包、防混料 | G01 | `variant_bom.py` |
| H | [R4-H 校准与身份](h01-calibration-and-identity.md) → `references/decisions/h01-calibration-and-identity.md` (ok)
- L44 [unknown] [d) | 记录结构、A/B 槽、无效参数、工厂/现场 | H01 | `decision_record_check.py` |
| I | [R4-I 变更影响](i01-change-impact.md) → `references/decisions/i01-change-impact.md` (ok)
- L45 [unknown] [pact.md) | 四类场景、影响图、旧件失效闭包 | I01 | `decision_record_check.py` |
| J | [R4-J 模块复用](j01-module-reuse.md) → `references/decisions/j01-module-reuse.md` (ok)
- L46 [unknown] [块复用](j01-module-reuse.md) | opt-in 合同、兼容矩阵、实例化验证、退役 | J01 | — |
| K | [R4-K 受控实验](k01-controlled-experiment.md) → `references/decisions/k01-controlled-experiment.md` (ok)
- L47 [unknown] [验](k01-controlled-experiment.md) | 预注册、基线、单变量、采用决定 | K01 | — |
| L | [R4-L 资产有效性](l01-asset-validity.md) → `references/decisions/l01-asset-validity.md` (ok)
- L53 [unknown] [6）

| 案例 | 项目 | 族 | 包 | record_types |
|---|---|---|---|---|
| [R4-CASE-A01 需求变化](cases/r4-case-a01-requirement-change.md) → `references/decisions/cases/r4-case-a01-requirement-change.md` (ok)
- L54 [unknown] [irement-change.md) | R4-P2 | P01 | A | requirement-change |
| [R4-CASE-A02 过度设计门](cases/r4-case-a02-overdesign-gate.md) → `references/decisions/cases/r4-case-a02-overdesign-gate.md` (ok)
- L55 [unknown] [overdesign-gate.md) | R4-P1 | P01 | A | refuted-assumption |
| [R4-CASE-B01 引脚冲突](cases/r4-case-b01-pin-allocation-conflict.md) → `references/decisions/cases/r4-case-b01-pin-allocation-conflict.md` (ok)
- L56 [unknown] [ation-conflict.md) | R4-P1 | P01 | B | unknown-retained |
| [R4-CASE-C01 电池+外电状态](cases/r4-case-c01-battery-plus-external-supply-states.md) → `references/decisions/cases/r4-case-c01-battery-plus-external-supply-states.md` (ok)
- L57 [unknown] [md) | R4-P2 | P01 | C | state-transition, unknown-retained |
| [R4-CASE-D01 采集容差](cases/r4-case-d01-acquisition-tolerance.md) → `references/decisions/cases/r4-case-d01-acquisition-tolerance.md` (ok)
- L58 [unknown] [ition-tolerance.md) | R4-P3 | P02 | D | refuted-assumption |
| [R4-CASE-E01 多板接口](cases/r4-case-e01-multiboard-interface-contract.md) → `references/decisions/cases/r4-case-e01-multiboard-interface-contract.md` (ok)
- L59 [unknown] [) | R4-P4 | P02 | E | interface-contract, unknown-retained |
| [R4-CASE-F01 多板线束](cases/r4-case-f01-multiboard-harness.md) → `references/decisions/cases/r4-case-f01-multiboard-harness.md` (ok)
- L60 [unknown] [ | R4-P4 | P02 | F | refuted-assumption, unknown-retained |
| [R4-CASE-G01 双销售配置](cases/r4-case-g01-two-sales-configs-one-board.md) → `references/decisions/cases/r4-case-g01-two-sales-configs-one-board.md` (ok)
- L61 [unknown] [（constructed） | G | refuted-assumption, unknown-retained |
| [R4-CASE-H01 测量节点校准](cases/r4-case-h01-measurement-node-calibration.md) → `references/decisions/cases/r4-case-h01-measurement-node-calibration.md` (ok)
- L62 [unknown] [-node-calibration.md) | R4-P3 | P02 | H | unknown-retained |
| [R4-CASE-I01 旧版改型](cases/r4-case-i01-legacy-product-revision.md) → `references/decisions/cases/r4-case-i01-legacy-product-revision.md` (ok)
- L63 [unknown] [egacy-product-revision.md) | R4-P6 | P02 | I | local-only |
| [R4-CASE-J01 充电块复用](cases/r4-case-j01-charger-power-path-reuse.md) → `references/decisions/cases/r4-case-j01-charger-power-path-reuse.md` (ok)
- L64 [unknown] [.md) | R4-P2 | P01 | J | reuse-rejected, unknown-retained |
| [R4-CASE-K01 单变量实验](cases/r4-case-k01-acquisition-single-variable.md) → `references/decisions/cases/r4-case-k01-acquisition-single-variable.md` (ok)
- L65 [unknown] [n-single-variable.md) | R4-P3 | P02 | K | unknown-retained |
| [R4-CASE-L01 资产冲突](cases/r4-case-l01-asset-validity-conflict.md) → `references/decisions/cases/r4-case-l01-asset-validity-conflict.md` (ok)
- L67 [unknown] [| unknown-retained |

案例族谱、canonical facts 与五类 record 的 owner 见 [cases/README.md](cases/README.md) → `references/decisions/cases/README.md` (ok)
- L73 [unknown] [ 证据。

## 4. 十四个模板

| 模板 | 谁用 | 用途 |
|---|---|---|
| [decision-record.template.md](../../assets/decisions/decision-record.template.md) → `assets/decisions/decision-record.template.md` (ok)
- L74 [unknown] [cord.template.md) | 所有 A–L 案例 | 决策头 + 五类 typed block |
| [pin-plan.template.json](../../assets/decisions/pin-plan.template.json) → `assets/decisions/pin-plan.template.json` (ok)
- L75 [unknown] [pin-plan.template.json) | B01 | 引脚/资源/候选/未决项 |
| [state-transition.template.json](../../assets/decisions/state-transition.template.json) → `assets/decisions/state-transition.template.json` (ok)
- L76 [unknown] [on.template.json) | C01 | 三轴状态、转换、POR、部分供电 |
| [interface-contract.template.json](../../assets/decisions/interface-contract.template.json) → `assets/decisions/interface-contract.template.json` (ok)
- L77 [unknown] [terface-contract.template.json) | E01 | 一条接口一行 |
| [tolerance-budget.template.md](../../assets/decisions/tolerance-budget.template.md) → `assets/decisions/tolerance-budget.template.md` (ok)
- L78 [unknown] [tolerance-budget.template.md) | D01 | 逐项预算与角点 |
| [experiment-record.template.md](../../assets/decisions/experiment-record.template.md) → `assets/decisions/experiment-record.template.md` (ok)
- L79 [unknown] [iment-record.template.md) | K01 | 预注册、基线、单变量、采用 |
| [harness-package.template.md](../../assets/decisions/harness-package.template.md) → `assets/decisions/harness-package.template.md` (ok)
- L80 [unknown] [sions/harness-package.template.md) | F01 | 整机线束包 |
| [variant-matrix.template.md](../../assets/decisions/variant-matrix.template.md) → `assets/decisions/variant-matrix.template.md` (ok)
- L81 [unknown] [sions/variant-matrix.template.md) | G01 | 变体闭包与差异 |
| [variant-bom.template.json](../../assets/decisions/variant-bom.template.json) → `assets/decisions/variant-bom.template.json` (ok)
- L82 [unknown] [plate.json) | G01 | master BOM → 变体 needed |
| [calibration-record.template.json](../../assets/decisions/calibration-record.template.json) → `assets/decisions/calibration-record.template.json` (ok)
- L83 [unknown] [on-record.template.json) | H01 | 校准记录、槽位、CRC、身份 |
| [change-record.template.json](../../assets/decisions/change-record.template.json) → `assets/decisions/change-record.template.json` (ok)
- L84 [unknown] [template.json) | I01 | 变更单、旧件状态、BOM delta |
| [change-impact-graph.template.json](../../assets/decisions/change-impact-graph.template.json) → `assets/decisions/change-impact-graph.template.json` (ok)
- L85 [unknown] [mpact-graph.template.json) | I01 | 有向影响图与闭包 |
| [module-reuse-record.template.md](../../assets/decisions/module-reuse-record.template.md) → `assets/decisions/module-reuse-record.template.md` (ok)
- L86 [unknown] [module-reuse-record.template.md) | J01 | 10 组复用合同字段 |
| [asset-index.template.md](../../assets/decisions/asset-index.template.md) → `assets/decisions/asset-index.template.md` (ok)
- L94 [unknown] [目。

## 5. 六个检查脚本

| 脚本 | 检查 | 退出码 | 不证明 |
|---|---|---|---|
| [pin_plan_check.py](../../scripts/pin_plan_check.py) → `scripts/pin_plan_check.py` (ok)
- L95 [unknown] [输出、strap/调试脚被占、候选混入已分配 | 0/1/2 | 物理脚/pinmux 已核对 |
| [interface_contract_check.py](../../scripts/interface_contract_check.py) → `scripts/interface_contract_check.py` (ok)
- L96 [unknown] [y) | 字段完整性、多驱动仲裁、off_behavior、插合序列、stale | 0/1/2 | 接口电气已通过 |
| [harness_check.py](../../scripts/harness_check.py) → `scripts/harness_check.py` (ok)
- L97 [unknown] [harness_check.py) | 线束包版本、配对件、逐线证据、防误接矩阵 | 0/1/2 | 线束可加工/已压接 |
| [variant_bom.py](../../scripts/variant_bom.py) → `scripts/variant_bom.py` (ok)
- L98 [unknown] [/forbidden 闭包、DNP、混料、needed 数量 | 0/1/2 | 可下单/价格/库存 |
| [decision_record_check.py](../../scripts/decision_record_check.py) → `scripts/decision_record_check.py` (ok)
- L99 [unknown] [heck.py) | 校准记录、变更单、影响图的结构与状态机 | 0/1/2 | 校准有效/改型已验证 |
| [decision_asset_check.py](../../scripts/decision_asset_check.py) → `scripts/decision_asset_check.py` (ok)
- L117 [unknown] [评 |

## 7. 与现有资产的分工

| 现有资产 | 负责 | 本库只补 |
|---|---|---|
| [module-integration.md](../module-integration.md) → `references/module-integration.md` (ok)
- L118 [unknown] [tion.md) | 12 条接口判据、组合失败案例、状态快照 | 一条接口一行、状态×接口矩阵、stale |
| [project-coherence.md](../project-coherence.md) → `references/project-coherence.md` (ok)
- L119 [unknown] [d](../project-coherence.md) | 变更传播与版本对应 | 有向影响图、闭包、旧件失效状态 |
| [part-selection.md](../part-selection.md) → `references/part-selection.md` (ok)
- L120 [unknown] [](../part-selection.md) | DNP/变体的工程原则 | 双销售配置闭包、变体 BOM 生成与防混料 |
| [calculations/](../calculations/README.md) → `references/calculations/README.md` (ok)
- L121 [unknown] [/calculations/README.md) | 公式、假设、算例、不能证明 | 跨电路逐项预算、角点决策、主导项动作 |
| [design-cards/](../design-cards/README.md) → `references/design-cards/README.md` (ok)
- L122 [unknown] [](../design-cards/README.md) | 拓扑、参数步骤、逐脚 | 不做卡片；J 只给 opt-in 复用合同 |
| [projects/](../projects/README.md) → `references/projects/README.md` (ok)
- L123 [unknown] [projects/](../projects/README.md) | 项目样本与完成级别 | 在其事实上做决策对照，不改项目文件 |
| [failures/](../failures/README.md) → `references/failures/README.md` (ok)
- L124 [unknown] [/](../failures/README.md) | 单点故障与复验 | 只引用判据，不复制故障叙事 |
| [manufacturing-routes.md](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L128 [background] [、制造路线 | 线束包受控字段、变体闭包与生成规则 |

## 8. 维护与准入

- 新增参考/案例/模板/脚本必须在本页与 [cases/README.md](cases/README.md) → `references/decisions/cases/README.md` (ok)
- L129 [unknown] [ses/README.md](cases/README.md) 登记；未登记资产不得写 `active`。
- 来源只用 [source-register.md](../source-register.md) → `references/source-register.md` (ok)

### `references/decisions/a01-architecture-decision.md`

- 标题：架构决策记录：备选、代价、冻结与重评
- 行/字符/字节：101 / 4134 / 8817
- SHA-256：`1f628f94ccb6ff9bd2edc0891dd3fb9dfec0413c82eed0215d5925e3fe9d3e4c`

- L79 [unknown] [器、线束、BOM 包装、备损、SMT/手焊、测试抽样与 EMC/安规测试。

## 7. 完整案例
- [R4-CASE-A01：首发 25 块到 1000 台](cases/r4-case-a01-requirement-change.md) → `references/decisions/cases/r4-case-a01-requirement-change.md` (ok)
- L80 [unknown] [件；若硬上限 ≤4.20 V，换 `VBAT(REG)` max ≤4.20 V 的型号；保护板只作协调。
- [R4-CASE-A02：对既有最小架构门的应用](cases/r4-case-a02-overdesign-gate.md) → `references/decisions/cases/r4-case-a02-overdesign-gate.md` (ok)

### `references/decisions/b01-pin-resource-planning.md`

- 标题：引脚与资源规划：分配顺序、冲突检查与未决项
- 行/字符/字节：100 / 4504 / 8997
- SHA-256：`7140586624685962dcedcb14e7f8ffaa34fca472f1223b45b13a1533e7b64a18`

- L80 [unknown] [改变 BOM、钢网/焊盘、调试夹具与替代等级，并重跑 B4 与连接器核对。

## 7. 完整案例
- [R4-CASE-B01：第二串口与下载/调试口复用冲突](cases/r4-case-b01-pin-allocation-conflict.md) → `references/decisions/cases/r4-case-b01-pin-allocation-conflict.md` (ok)

### `references/decisions/c01-state-transition-contract.md`

- 标题：工作状态与转换契约：三轴、恢复与 POR
- 行/字符/字节：101 / 5008 / 9708
- SHA-256：`e1d9b5053161a2fc4c436fa97b4a09883006ee421919a6dc3c923abc315fa45c`

- L81 [unknown] [序与复位标志、测试计划与 BOM；可关断轨还改变变体与 DNP。
## 7. 完整案例
- [R4-CASE-C01：电池与 USB 外部供电共存节点的状态契约](cases/r4-case-c01-battery-plus-external-supply-states.md) → `references/decisions/cases/r4-case-c01-battery-plus-external-supply-states.md` (ok)

### `references/decisions/cases/README.md`

- 标题：第 4 轮决策案例（R4-CASE）
- 行/字符/字节：62 / 4016 / 5563
- SHA-256：`e1f7f87bd00fd3dd33715894dc17764d43b89f68fb3acd777113d8f6e849e5b0`

- L11 [unknown] [推事实。

## 1. 案例族谱

| 族 | 派生项目 | 案例 | 说明 |
|---|---|---|---|
| P01 | [P01 低功耗无线传感器](../../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L12 [unknown] [.md) | R4-P1、R4-P2 | P1 多外设主控板；P2 电池+USB 外电共存 |
| P02 | [P02 工业 RS485/4–20 mA 节点](../../projects/p02-industrial-rs485-analog.md) → `references/projects/p02-industrial-rs485-analog.md` (ok)
- L13 [unknown] [-analog.md) | R4-P3、R4-P4、R4-P6 | P3 测量采集；P4 三块板控制；P6 旧版改型 |
| P03 | [P03 低压电机驱动](../../projects/p03-low-voltage-power-drive.md) → `references/projects/p03-low-voltage-power-drive.md` (ok)
- L19 [unknown] [s（跨工作流只认这些）

| 项目 | 主责案例（事实源） | 不能漂移的事实 | 仍未知 |
|---|---|---|---|
| R4-P1 | [A02](r4-case-a02-overdesign-gate.md) → `references/decisions/cases/r4-case-a02-overdesign-gate.md` (ok)
- L20 [unknown] [固件配置；新增按键/LED/第二串口/I2C；物理脚未核 | ESP32-C3 物理脚、pinmux、ADC 限制、封装 NC |
| R4-P2 | [C01](r4-case-c01-battery-plus-external-supply-states.md) → `references/decisions/cases/r4-case-c01-battery-plus-external-supply-states.md` (ok)
- L21 [unknown] [ed`，仅标称 4.20 V 时 `blocked`/待核 | 电芯型号/硬上限/允许条件、NTC、θJA、许可、OTA 平台 |
| R4-P3 | [D01](r4-case-d01-acquisition-tolerance.md) → `references/decisions/cases/r4-case-d01-acquisition-tolerance.md` (ok)
- L22 [unknown] [ 的 3905/0.524 LSB 用 recompute JSON 重算 | 实际 ADC/基准/运放、校准源、恒温箱、老化 |
| R4-P4 | [E01](r4-case-e01-multiboard-interface-contract.md) → `references/decisions/cases/r4-case-e01-multiboard-interface-contract.md` (ok)
- L23 [unknown] [integration §17.2；J2/J3 与第三块板是构造假设 | 连接器 MPN/额定/配对端子/压接工具、线长/线规 |
| R4-P5 | [G01](r4-case-g01-two-sales-configs-one-board.md) → `references/decisions/cases/r4-case-g01-two-sales-configs-one-board.md` (ok)
- L24 [unknown] [9.4 的 V1 继电器/V2 MOSFET；constructed | 全部 MPN/C 号/价格/库存/MOQ/包装/认证 |
| R4-P6 | [I01](r4-case-i01-legacy-product-revision.md) → `references/decisions/cases/r4-case-i01-legacy-product-revision.md` (ok)
- L32 [unknown] [件 |
|---|---|---|---|---|
| R4-CASE-A01 | R4-P2 | A | requirement-change | [需求变化](r4-case-a01-requirement-change.md) → `references/decisions/cases/r4-case-a01-requirement-change.md` (ok)
- L33 [unknown] [requirement-change.md) |
| R4-CASE-A02 | R4-P1 | A | refuted-assumption | [过度设计门](r4-case-a02-overdesign-gate.md) → `references/decisions/cases/r4-case-a02-overdesign-gate.md` (ok)
- L34 [unknown] [e-a02-overdesign-gate.md) |
| R4-CASE-B01 | R4-P1 | B | unknown-retained | [引脚冲突](r4-case-b01-pin-allocation-conflict.md) → `references/decisions/cases/r4-case-b01-pin-allocation-conflict.md` (ok)
- L35 [unknown] [.md) |
| R4-CASE-C01 | R4-P2 | C | state-transition, unknown-retained | [电池+外电状态](r4-case-c01-battery-plus-external-supply-states.md) → `references/decisions/cases/r4-case-c01-battery-plus-external-supply-states.md` (ok)
- L36 [unknown] [ernal-supply-states.md) |
| R4-CASE-D01 | R4-P3 | D | refuted-assumption | [采集容差](r4-case-d01-acquisition-tolerance.md) → `references/decisions/cases/r4-case-d01-acquisition-tolerance.md` (ok)
- L37 [unknown] [e.md) |
| R4-CASE-E01 | R4-P4 | E | interface-contract, unknown-retained | [多板接口](r4-case-e01-multiboard-interface-contract.md) → `references/decisions/cases/r4-case-e01-multiboard-interface-contract.md` (ok)
- L38 [unknown] [t.md) |
| R4-CASE-F01 | R4-P4 | F | refuted-assumption, unknown-retained | [多板线束](r4-case-f01-multiboard-harness.md) → `references/decisions/cases/r4-case-f01-multiboard-harness.md` (ok)
- L39 [unknown] [.md) |
| R4-CASE-G01 | R4-P5 | G | refuted-assumption, unknown-retained | [双销售配置](r4-case-g01-two-sales-configs-one-board.md) → `references/decisions/cases/r4-case-g01-two-sales-configs-one-board.md` (ok)
- L40 [unknown] [les-configs-one-board.md) |
| R4-CASE-H01 | R4-P3 | H | unknown-retained | [测量校准](r4-case-h01-measurement-node-calibration.md) → `references/decisions/cases/r4-case-h01-measurement-node-calibration.md` (ok)
- L41 [unknown] [easurement-node-calibration.md) |
| R4-CASE-I01 | R4-P6 | I | local-only | [旧版改型](r4-case-i01-legacy-product-revision.md) → `references/decisions/cases/r4-case-i01-legacy-product-revision.md` (ok)
- L42 [unknown] [sion.md) |
| R4-CASE-J01 | R4-P2 | J | reuse-rejected, unknown-retained | [充电块复用](r4-case-j01-charger-power-path-reuse.md) → `references/decisions/cases/r4-case-j01-charger-power-path-reuse.md` (ok)
- L43 [unknown] [ger-power-path-reuse.md) |
| R4-CASE-K01 | R4-P3 | K | unknown-retained | [单变量实验](r4-case-k01-acquisition-single-variable.md) → `references/decisions/cases/r4-case-k01-acquisition-single-variable.md` (ok)
- L44 [unknown] [ition-single-variable.md) |
| R4-CASE-L01 | R4-P6 | L | unknown-retained | [资产冲突](r4-case-l01-asset-validity-conflict.md) → `references/decisions/cases/r4-case-l01-asset-validity-conflict.md` (ok)

### `references/decisions/cases/r4-case-a01-requirement-change.md`

- 标题：首发 25 块到 1000 台：需求变化后的重新决策
- 行/字符/字节：89 / 4671 / 8074
- SHA-256：`963112c0384e6ee8196843a8c6679195a9e349b468d091850891a72322d6e70a`

### `references/decisions/cases/r4-case-a02-overdesign-gate.md`

- 标题：对既有最小架构门的应用：四项新增外设逐项判定
- 行/字符/字节：86 / 3953 / 6949
- SHA-256：`3dfc752fbafc25511de17d9a43abbf8c7da8f79b95c70c606dcb0917da4d0e8e`

### `references/decisions/cases/r4-case-b01-pin-allocation-conflict.md`

- 标题：第二串口与下载/调试口的引脚分配冲突
- 行/字符/字节：83 / 4077 / 7186
- SHA-256：`ee7bc23dbc3803ea7b73d520859531e3409d08da8e36310c7518f0fb2746ea7b`

### `references/decisions/cases/r4-case-c01-battery-plus-external-supply-states.md`

- 标题：电池与 USB 外部供电共存节点的状态契约
- 行/字符/字节：63 / 4013 / 6778
- SHA-256：`a78785e7b28ae89eb1271adffb7eea5dda20366f90a41b88d611c934ffc32c5c`

- L59 [unknown] [拔方式、出现实测复位/反灌记录。
## 9. 与现有资产分工
- 三轴与 POR 方法见 [`c01-state-transition-contract.md`](../c01-state-transition-contract.md) → `references/decisions/c01-state-transition-contract.md` (ok)
- L62 [unknown] [.md:86-86`、`:133-133`、`:263-265`；本文不新增器件参数。
- 接口字段见 [`e01-interface-contract.md`](../e01-interface-contract.md) → `references/decisions/e01-interface-contract.md` (ok)

### `references/decisions/cases/r4-case-d01-acquisition-tolerance.md`

- 标题：两路 4–20 mA 采集的容差预算与角点决策
- 行/字符/字节：90 / 8994 / 13133
- SHA-256：`e04f69f6ec07df81df7fcf9f01d007a5007e817fd8f8e49aa7e6411f3872149b`

### `references/decisions/cases/r4-case-e01-multiboard-interface-contract.md`

- 标题：三块板控制系统的接口契约
- 行/字符/字节：62 / 3412 / 5889
- SHA-256：`271897aff140768ec3766ff9c14a8c4164bafbfbd052c056de1f47db643da4a7`

- L58 [unknown] [dule-integration.md` 行号漂移。
## 9. 与现有资产分工
- 接口方法与字段见 [`e01-interface-contract.md`](../e01-interface-contract.md) → `references/decisions/e01-interface-contract.md` (ok)
- L60 [unknown] [13-729`；本文不重写。
- 状态×接口矩阵回链 [`r4-case-c01-battery-plus-external-supply-states.md`](r4-case-c01-battery-plus-external-supply-states.md) → `references/decisions/cases/r4-case-c01-battery-plus-external-supply-states.md` (ok)

### `references/decisions/cases/r4-case-f01-multiboard-harness.md`

- 标题：三块板的整机线束包
- 行/字符/字节：91 / 4001 / 7660
- SHA-256：`a2b7530927fb508bca47a6f869706bbc1a90fd9321c98becdbc739a08359845c`

- L87 [background] [换型或换厂；板/壳版本变化；线束长度、电流或屏蔽要求变化；整机 EMC/振动/跌落出现新约束。

## 9. 与现有资产分工

- [整机线束、连接器与板外接口](../f01-harness-and-board-external.md) → `references/decisions/f01-harness-and-board-external.md` (ok)

### `references/decisions/cases/r4-case-g01-two-sales-configs-one-board.md`

- 标题：继电器版与 MOSFET 版共板的两个销售配置
- 行/字符/字节：91 / 4511 / 8200
- SHA-256：`781e3c3da25851d3f382b174d43eb6d0b6fb9c7856bdc7e2839f8ac5b58e2570`

- L87 [background] [评：变体表换版；新增销售配置或包装形式；产线防错方案变化；原厂 PCN/EOL；混料投诉。

## 9. 与现有资产分工

- [产品变体、共板销售配置与防混料](../g01-product-variants.md) → `references/decisions/g01-product-variants.md` (ok)

### `references/decisions/cases/r4-case-h01-measurement-node-calibration.md`

- 标题：两路 4–20 mA 测量节点的校准记录
- 行/字符/字节：76 / 4112 / 7340
- SHA-256：`d8599891fe41a2911e964483744b889d2d6bee3f2536adada47b5f66de16cdf2`

- L72 [background] [身份触发，必须回到服务流程，不允许现场“忽略告警继续用”。重评在器件、量程、温区、存储或工装任一变化时触发。

## 9. 与现有资产分工

- [H 方法参考](../h01-calibration-and-identity.md) → `references/decisions/h01-calibration-and-identity.md` (ok)

### `references/decisions/cases/r4-case-i01-legacy-product-revision.md`

- 标题：旧版产品 V1 到 V1.1 的四类改型
- 行/字符/字节：91 / 4473 / 8109
- SHA-256：`9edebe698ae74e4d13cb6e9a2209e63ccdd0fdcbea9d0e4538b790f48aeb4a4a`

- L88 [background] [重评：变更场景/等级变化、新增出货批次、隔离或安规要求变化、F1 重跑或出现新的 E1 基线、客户合同变化。

## 9. 与现有资产分工

- [I 方法参考](../i01-change-impact.md) → `references/decisions/i01-change-impact.md` (ok)

### `references/decisions/cases/r4-case-j01-charger-power-path-reuse.md`

- 标题：充电器与 power path 电路块的复用合同核对
- 行/字符/字节：91 / 5667 / 9769
- SHA-256：`5540d5ae72ddb9d7d3ddd66d4c6944453d6bc1722e53d23de164dbdb3975c760`

### `references/decisions/cases/r4-case-k01-acquisition-single-variable.md`

- 标题：采集时间 t_ACQ 的单变量受控实验预注册
- 行/字符/字节：89 / 4885 / 8218
- SHA-256：`75edcb5b1cbde732d5ebc9ed2060efb97dcbfd97d215eff35104c8289e963cf5`

### `references/decisions/cases/r4-case-l01-asset-validity-conflict.md`

- 标题：同一文档两个日期的冲突裁决：SLVA477C、SLVA673A 与 PWR-S05 范围差异
- 行/字符/字节：91 / 4415 / 7833
- SHA-256：`f137ab325188ae3093d23da04421cea202e1898176bd5c86c35ec85fab9ba8bb`

### `references/decisions/d01-tolerance-and-worst-case.md`

- 标题：容差预算、角点组合与最坏情况决策
- 行/字符/字节：100 / 5435 / 10567
- SHA-256：`449ab3480d4250c205a02db8a14499ef99b50f4b94d496e2ebd895819cf1d77f`

- L80 [unknown] [结原理图前完成；只改软件校准不能消掉建立、串扰、INL 与温漂。
## 7. 完整案例
[R4-CASE-D01：两路 4–20 mA 采集的容差预算与角点决策](cases/r4-case-d01-acquisition-tolerance.md) → `references/decisions/cases/r4-case-d01-acquisition-tolerance.md` (ok)

### `references/decisions/e01-interface-contract.md`

- 标题：跨模块接口契约：一接口一行、阻断与 stale
- 行/字符/字节：101 / 5620 / 10295
- SHA-256：`a29f6d65509e9358031431a2f460a099e71d024c0f0748ecfcd7a744776ab80b`

- L76 [unknown] [、负载开关/理想二极管、固件方向控制与初始化顺序、变体 DNP、测试项与 BOM。
## 7. 完整案例
- [R4-CASE-E01：三块板控制系统的接口契约](cases/r4-case-e01-multiboard-interface-contract.md) → `references/decisions/cases/r4-case-e01-multiboard-interface-contract.md` (ok)

### `references/decisions/f01-harness-and-board-external.md`

- 标题：整机线束、连接器与板外接口
- 行/字符/字节：96 / 3890 / 8297
- SHA-256：`cc6bb0f5a16ec29b455ac2d741eb24d8460d23bf5c20fe2ce2fbae2e02bc2cd6`

### `references/decisions/g01-product-variants.md`

- 标题：产品变体、共板销售配置与防混料
- 行/字符/字节：97 / 4199 / 8268
- SHA-256：`c33ceebadf11bac1b584066a772c5354a66a26d9d28fd4f7186f1fed66dc7baa`

### `references/decisions/h01-calibration-and-identity.md`

- 标题：校准、参数存储与设备身份
- 行/字符/字节：101 / 5604 / 11052
- SHA-256：`081fcd9562f4ba693af54a1399c34f320abee0561ba12c9a934504692015f321`

- L79 [unknown] [签与序列号、服务流程与备件策略。是否校准必须在选基准和分流之前回答。

## 7. 完整案例
[R4-CASE-H01：两路 4–20 mA 测量节点的校准记录](cases/r4-case-h01-measurement-node-calibration.md) → `references/decisions/cases/r4-case-h01-measurement-node-calibration.md` (ok)

### `references/decisions/i01-change-impact.md`

- 标题：变更影响：四类场景、闭包与旧件状态
- 行/字符/字节：101 / 5999 / 11558
- SHA-256：`f3b548daf1793b5caf4be0fc9279a79ebb7214b234e3a5fba348f4f5ab867755`

- L82 [unknown] [抽样与客户通知。等级 2/3 不能在旧板上“先飞线试试”后直接放行。

## 7. 完整案例
[R4-CASE-I01：旧版产品 V1 → V1.1 的四类改型](cases/r4-case-i01-legacy-product-revision.md) → `references/decisions/cases/r4-case-i01-legacy-product-revision.md` (ok)

### `references/decisions/j01-module-reuse.md`

- 标题：模块复用合同：边界、兼容与退役
- 行/字符/字节：101 / 5145 / 9968
- SHA-256：`47245b60aa4414a5bf0566eef5712d669f031a5deb04158c8bf6b5eb5d2415d1`

### `references/decisions/k01-controlled-experiment.md`

- 标题：受控实验预注册、基线与采用决定
- 行/字符/字节：100 / 4661 / 9040
- SHA-256：`38f102421b0b443b0358d324c0cc8401f7188355d04338c99931d80dcd08b192`

- L80 [unknown] [SCH/固件前完成；不能用“平均后看起来稳定”替代建立或串扰结论。
## 7. 完整案例
[R4-CASE-K01：采集时间 t_ACQ 的单变量受控实验预注册](cases/r4-case-k01-acquisition-single-variable.md) → `references/decisions/cases/r4-case-k01-acquisition-single-variable.md` (ok)

### `references/decisions/l01-asset-validity.md`

- 标题：决策资产有效性与来源冲突
- 行/字符/字节：101 / 5270 / 9442
- SHA-256：`571e3743a36c87924b37805a2eca6de04e8f5c7747297eacbcbcfabb50c5f597`

### `references/design-cards/README.md`

- 标题：可复用电路设计卡库
- 行/字符/字节：115 / 7102 / 8582
- SHA-256：`d9f1fa402e2fb572a5e95f2edf436c9cc89371a2de6d208e25a079e593c4b5aa`

- L20 [unknown] [|---|---|
| PWR-01 | LDO 线性稳压 | E1 | SC12, SC14, SC18, PL16, RT01 | [p01-ldo.md](power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L21 [unknown] [R-02 | Buck 降压变换器 | E1 | SC13, PL09, PL10, PL11, PL12, RT01, RT04 | [p02-buck.md](power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L22 [unknown] [| PWR-03 | Boost 升压变换器 | E1 | SC13, PL09, PL10, PL11, RT01, RT04 | [p03-boost.md](power/p03-boost.md) → `references/design-cards/power/p03-boost.md` (ok)
- L23 [unknown] [uck-Boost / SEPIC / 四开关 | E1 | SC09, SC13, PL09, PL10, RT01 | [p04-buck-boost.md](power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L24 [unknown] [PWR-05 | 多源供电与电源路径 | E2 | SC10, SC11, SC14, SC17, PL15, RT06 | [p05-power-mux.md](power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L25 [unknown] [d) |
| PWR-06 | 单节锂电线性充电 | E1 | SC17, SC18, PL16, MF16 | [p06-linear-charger.md](power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L26 [unknown] [-07 | 开关充电与 Power Path | E2 | SC09, SC17, PL09, PL16 | [p07-switching-charger.md](power/p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L27 [unknown] [PWR-08 | 1S 电池保护与 BMS | E2 | SC17, SC18, PL16, DM13 | [p08-battery-protection.md](power/p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L28 [unknown] [ection.md) |
| PWR-09 | 反接保护 | E1 | SC16, PL15, RT01 | [p09-reverse-polarity.md](power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L29 [unknown] [rity.md) |
| PWR-10 | 热插拔与浪涌限制 | E1 | SC16, SC15, PL15, RT01 | [p10-hot-swap.md](power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L30 [unknown] [-swap.md) |
| PWR-11 | 保险丝 / eFuse / 限流 | E2 | SC15, PL15, RT01 | [p11-efuse.md](power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L31 [unknown] [d) |
| PWR-12 | USB-C 5V Sink | E1 | SC30, SC31, PL15, DM29 | [p12-usbc-sink.md](power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L32 [unknown] [R-13 | USB-C 5V Source / OTG | E2 | SC30, SC10, PL15, DM29 | [p13-usbc-source.md](power/p13-usbc-source.md) → `references/design-cards/power/p13-usbc-source.md` (ok)
- L33 [unknown] [4 | 超级电容 / RTC 备份 / 掉电保持 | E2 | SC09, SC11, SC18, RT06 | [p14-supercap-backup.md](power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L39 [unknown] [最小系统（STM32 类） | E1 | SC19, SC22, SC23, SC24, SC25, PL17, PL18 | [m01-bare-mcu.md](mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L40 [unknown] [CU-02 | 模组最小系统（ESP32 类） | E1 | SC19, SC20, SC24, PL17, PL26 | [m02-module-mcu.md](mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L41 [unknown] [mcu.md) |
| MCU-03 | 复位与电源监控 | E1 | SC22, SC14, PL17 | [m03-reset-supervisor.md](mcu/m03-reset-supervisor.md) → `references/design-cards/mcu/m03-reset-supervisor.md` (ok)
- L42 [unknown] [supervisor.md) |
| MCU-04 | 启动与配置脚 | E1 | SC20, SC21, SC25 | [m04-boot-strap.md](mcu/m04-boot-strap.md) → `references/design-cards/mcu/m04-boot-strap.md` (ok)
- L43 [unknown] [m04-boot-strap.md) |
| MCU-05 | 晶体振荡器 | E1 | SC23, PL19, RT24 | [m05-crystal.md](mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L44 [unknown] [.md) |
| MCU-06 | 外部时钟 / 振荡器输入 | E2 | SC23, PL19, RT24 | [m06-external-clock.md](mcu/m06-external-clock.md) → `references/design-cards/mcu/m06-external-clock.md` (ok)
- L45 [unknown] [ck.md) |
| MCU-07 | SWD / JTAG 调试与救援 | E1 | SC24, SC25, SC40 | [m07-swd-jtag.md](mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L46 [unknown] [MCU-08 | UART Bootloader / ISP | E1 | SC24, SC29, SC20 | [m08-uart-bootloader.md](mcu/m08-uart-bootloader.md) → `references/design-cards/mcu/m08-uart-bootloader.md` (ok)
- L52 [unknown] [-|---|---|---|---|
| IF-01 | I²C 总线 | E1 | SC27, SC26, PL15, RT19 | [i01-i2c.md](interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L53 [unknown] [md) |
| IF-02 | I²C 缓冲 / 中继 / 电平转换 | E2 | SC27, SC26, RT19 | [i02-i2c-buffer.md](interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L54 [unknown] [-i2c-buffer.md) |
| IF-03 | SPI 点对点 | E1 | SC28, SC26, RT11, RT20 | [i03-spi.md](interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L55 [unknown] [03-spi.md) |
| IF-04 | SPI 多从机 / 片选 | E2 | SC28, SC25, PL29 | [i04-spi-multi.md](interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L56 [unknown] [s/i04-spi-multi.md) |
| IF-05 | UART TTL | E2 | SC29, SC26, SC40 | [i05-uart.md](interfaces/i05-uart.md) → `references/design-cards/interfaces/i05-uart.md` (ok)
- L57 [unknown] [s/i05-uart.md) |
| IF-06 | RS-232 | E1 | SC29, SC15, PL15, DM27 | [i06-rs232.md](interfaces/i06-rs232.md) → `references/design-cards/interfaces/i06-rs232.md` (ok)
- L58 [unknown] [s232.md) |
| IF-07 | RS-485 | E1 | SC32, SC15, SC38, PL15, RT18 | [i07-rs485.md](interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L59 [unknown] [faces/i07-rs485.md) |
| IF-08 | CAN | E1 | SC32, SC15, SC38, PL15 | [i08-can.md](interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L60 [unknown] [B 2.0 Full-Speed Device | E1 | SC31, SC30, PL15, RT11, RT12 | [i09-usb-device.md](interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L61 [unknown] [.md) |
| IF-10 | USB-C 数据与 CC | E1 | SC30, SC31, SC40, DM29 | [i10-usbc-data.md](interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)
- L62 [unknown] [-11 | 10/100 Ethernet PHY | E2 | SC32, PL28, RT11, RT12, DM28 | [i11-ethernet.md](interfaces/i11-ethernet.md) → `references/design-cards/interfaces/i11-ethernet.md` (ok)
- L63 [unknown] [1-ethernet.md) |
| IF-12 | 电平转换选型 | E1 | SC26, SC27, PL15 | [i12-level-shift.md](interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L69 [unknown] [|---|---|---|
| ANA-01 | 电阻分压采样 | E1 | SC34, SC37, PL21, RT21 | [a01-divider.md](analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L70 [unknown] [der.md) |
| ANA-02 | 运放缓冲 / 同相放大 | E1 | SC33, PL22, RT22 | [a02-opamp-buffer.md](analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L71 [unknown] [p-buffer.md) |
| ANA-03 | 差分放大 | E1 | SC33, SC36, PL21, RT21 | [a03-diff-amp.md](analog/a03-diff-amp.md) → `references/design-cards/analog/a03-diff-amp.md` (ok)
- L72 [unknown] [.md) |
| ANA-04 | SAR ADC 驱动 | E1 | SC34, SC35, PL23, RT21 | [a04-adc-driver.md](analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L73 [unknown] [log/a04-adc-driver.md) |
| ANA-05 | 电压基准 | E1 | SC35, PL23, RT23 | [a05-vref.md](analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L74 [unknown] [5-vref.md) |
| ANA-06 | 低侧电流采样 | E1 | SC36, PL14, RT07 | [a06-low-side-sense.md](analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L75 [unknown] [md) |
| ANA-07 | 高侧电流采样 | E2 | SC36, SC33, PL14, RT07 | [a07-high-side-sense.md](analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L76 [unknown] [ense.md) |
| ANA-08 | 4–20 mA 输入 | E2 | SC37, SC38, PL21, DM22 | [a08-4-20ma.md](analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L77 [unknown] [-4-20ma.md) |
| ANA-09 | 桥式传感器前端 | E2 | SC33, SC36, PL21, DM22 | [a09-bridge.md](analog/a09-bridge.md) → `references/design-cards/analog/a09-bridge.md` (ok)
- L78 [unknown] [
| ANA-10 | RTD / 热敏电阻测量 | E2 | SC33, SC36, PL24, DM22 | [a10-rtd-thermistor.md](analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L84 [unknown] [-|---|---|---|
| DRV-01 | 低侧开关 | E1 | SC21, SC39, PL13, RT09 | [d01-low-side.md](drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L85 [unknown] [ow-side.md) |
| DRV-02 | 高侧开关 | E1 | SC21, SC39, PL13, RT09 | [d02-high-side.md](drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L86 [unknown] [-high-side.md) |
| DRV-03 | 继电器驱动 | E1 | SC21, SC39, PL16, DM20 | [d03-relay.md](drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)
- L87 [unknown] [y.md) |
| DRV-04 | 半桥 | E1 | SC21, SC39, PL11, PL13, RT09 | [d04-half-bridge.md](drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L88 [unknown] [ |
| DRV-05 | H 桥 / 有刷电机 | E1 | SC21, SC39, PL13, PL14, RT09 | [d05-h-bridge.md](drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L89 [unknown] [-bridge.md) |
| DRV-06 | 步进电机驱动 | E2 | SC21, SC39, PL13, PL16 | [d06-stepper.md](drive/d06-stepper.md) → `references/design-cards/drive/d06-stepper.md` (ok)
- L90 [unknown] [tepper.md) |
| DRV-07 | LED 恒流驱动 | E1 | SC21, SC39, PL16, DM41 | [d07-led-cc.md](drive/d07-led-cc.md) → `references/design-cards/drive/d07-led-cc.md` (ok)
- L91 [unknown] [07-led-cc.md) |
| DRV-08 | 加热器控制 | E1 | SC21, SC39, PL16, DM44 | [d08-heater.md](drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L95 [unknown] [示、音频与存储（8 张）

> 显示/音频卡位于 `wireless/` 是历史归类；HMI 的用户话术、选屏/触摸/按键/蜂鸣器内容见 [常用硬件 L 组](../common-hardware/l-hmi.md) → `references/common-hardware/l-hmi.md` (ok)
- L99 [unknown] [
| RF-01 | Wi-Fi / BLE 模组 | E1 | SC09, SC20, PL26, PL27, DM33 | [w01-wifi-ble.md](wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L100 [unknown] [ifi-ble.md) |
| RF-02 | 天线接口与匹配 | E1 | PL26, PL27, RT25, RT26 | [w02-antenna.md](wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L101 [unknown] [antenna.md) |
| RF-03 | 蜂窝模组电源 | E2 | SC09, SC16, PL26, DM33 | [w03-cellular.md](wireless/w03-cellular.md) → `references/design-cards/wireless/w03-cellular.md` (ok)
- L102 [unknown] [3-cellular.md) |
| RF-04 | GNSS 模组 | E2 | SC37, PL26, PL27, DM35 | [w04-gnss.md](wireless/w04-gnss.md) → `references/design-cards/wireless/w04-gnss.md` (ok)
- L103 [unknown] [s.md) |
| RF-05 | SPI TFT 显示与背光 | E1 | SC40, PL07, PL16, DM39 | [w05-display.md](wireless/w05-display.md) → `references/design-cards/wireless/w05-display.md` (ok)
- L104 [unknown] [lay.md) |
| RF-06 | Class-D 音频功放 | E1 | SC39, PL16, RT22, DM38 | [w06-classd.md](wireless/w06-classd.md) → `references/design-cards/wireless/w06-classd.md` (ok)
- L105 [unknown] [md) |
| RF-07 | SPI NOR Flash | E1 | SC25, SC28, PL20, DM31 | [w07-spi-flash.md](wireless/w07-spi-flash.md) → `references/design-cards/wireless/w07-spi-flash.md` (ok)
- L106 [unknown] [lash.md) |
| RF-08 | microSD 接口 | E1 | SC25, SC28, SC40, DM31 | [w08-microsd.md](wireless/w08-microsd.md) → `references/design-cards/wireless/w08-microsd.md` (ok)

### `references/design-cards/analog/a01-divider.md`

- 标题：电阻分压采样
- 行/字符/字节：271 / 12025 / 24069
- SHA-256：`fff1e67276675a758f9d4f4a377aea1b386d1948b14eb0d80a562cf2102dc9d4`

- L43 [unknown] [维南电阻能否在 ADC 的采集窗口内建立到 ½ LSB**。这一步决定了同样的比例下是选 411 Ω 还是 12 kΩ，以及要不要加缓冲（缓冲本身见 [运放缓冲](a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L49 [unknown] [通常做不到 §5 的结论。
- **需要电气隔离**：分压器不能替代隔离放大器或隔离 ADC，隔离边界要单独设计（见 SC38、RT10 与 [常用硬件 E5](../../common-hardware/e-measurement.md) → `references/common-hardware/e-measurement.md` (ok)
- L61 [background] [DC 位数 | N（bit） | 选型 | 阻断 |
| ADC 参考电压 | V_REF,min / V_REF,max（V） | 基准手册（见 [电压基准](a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L155 [unknown] [作电压与脉冲耐压要单独核对。**具体额定值待按所选电阻手册核对。**
5. **迭代**：若功耗不可接受，只有三条路：提高 R_th 并加缓冲（[ANA-02](a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L166 [unknown] [电 | `V_err = I_leak,max × R_th` | 高阻分压的主要直流误差；I_leak 随温度上升 |
| 基准误差 | 见 [ANA-05](a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L196 [unknown] [
| ADC | C_SH、R_SW、I_leak、输入绝对最大额定值、输入范围 | 只按分辨率选型；不看输入结构 | 引脚与封装按手册 | 见 [ANA-04](a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)

### `references/design-cards/analog/a02-opamp-buffer.md`

- 标题：运放缓冲 / 同相放大
- 行/字符/字节：343 / 13152 / 25496
- SHA-256：`f5e3d2f3081ce1260ae668e6593039d6196df347d17229637d96b9342528aa52`

- L55 [unknown] [估算不成立，需要完整环路分析。
- **需要低于运放噪声底限的测量**：噪声预算不在本次来源内，必须另算。
- **需要电气隔离或高共模**：见 [高侧采样](a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L55 [unknown] [：噪声预算不在本次来源内，必须另算。
- **需要电气隔离或高共模**：见 [高侧采样](a07-high-side-sense.md) 与 [常用硬件 E5](../../common-hardware/e-measurement.md) → `references/common-hardware/e-measurement.md` (ok)

### `references/design-cards/analog/a03-diff-amp.md`

- 标题：差分放大
- 行/字符/字节：347 / 11292 / 21675
- SHA-256：`f11e2acca2fc9849f4fcc14256835e5487c80dbd5132fdfb9730a3a9bda9a5ed`

- L52 [unknown] [运放输入共模下限可能不允许。
- **源阻抗不可忽略**：源阻抗直接串入 R1/R3，造成增益误差，需先算。
- **需要电气隔离**：见 [常用硬件 E5](../../common-hardware/e-measurement.md) → `references/common-hardware/e-measurement.md` (ok)
- L231 [required_read] [  ```
   若参考就是 ADC 基准，误差可能与 ADC 增益误差相关，可部分抵消；若参考是独立 LDO，必须按 305 µV 核对（见 [ANA-05](a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)

### `references/design-cards/analog/a04-adc-driver.md`

- 标题：SAR ADC 驱动
- 行/字符/字节：332 / 12807 / 23933
- SHA-256：`98f8f4ce7f33db33abe6af9885cf34c38cc88c672ba95edcc8cf00888273e3b2`

- L178 [example] [的实际条件本次未核对**，f_s、V_REF、V_REF 动态电流均待查。
- 前端：源阻抗 10 kΩ（例如 24 V 分压器的高阻版本，见 [ANA-01](a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)

### `references/design-cards/analog/a05-vref.md`

- 标题：电压基准
- 行/字符/字节：343 / 11218 / 21487
- SHA-256：`20b6ca17eac2873e3790bc5ef4b7ed2c0690448ba170749b93d3d3901b342a1d`

- L166 [unknown] [形待按 ADC 手册/模型核对。
4. **缓冲稳定性**：缓冲驱动大容性负载时需要 R_ISO 或专用补偿，公式与限制见 ANA-S10 与 [ANA-02](a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L242 [background] [位：本例若不改善参考指标/校准方法则不满足，不能推广为所有16位系统都必须温度校准，应改为（a）逐温度校准，或（b）比率测量（基准与输入同源，见 [ANA-04](a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)

### `references/design-cards/analog/a06-low-side-sense.md`

- 标题：低侧电流采样
- 行/字符/字节：267 / 11791 / 22293
- SHA-256：`ffc6b0d3c7e04ef1b548edbf7603b1118677f945ebc06cf62bafd79695a30d5d`

### `references/design-cards/analog/a07-high-side-sense.md`

- 标题：高侧电流采样
- 行/字符/字节：256 / 11464 / 22356
- SHA-256：`addfc92d71dfb355fc1d577d40e5de5cdecc8fdbd2b4db93269bec40dea09ab5`

### `references/design-cards/analog/a08-4-20ma.md`

- 标题：4–20 mA 输入
- 行/字符/字节：257 / 11067 / 21427
- SHA-256：`47bc6ba7fb34f6cec3d80a0317f04703a2d10113cd0e8d141c711a9176f584bf`

### `references/design-cards/analog/a09-bridge.md`

- 标题：桥式传感器前端
- 行/字符/字节：249 / 10735 / 20921
- SHA-256：`c33786cb2c8c0030facbca200ef91b1d7940a6072f0e1780625c6767a7b8b058`

### `references/design-cards/analog/a10-rtd-thermistor.md`

- 标题：RTD / 热敏电阻测量
- 行/字符/字节：274 / 11579 / 21825
- SHA-256：`fc7418507371525e3c9a66071ac699b6bc78e7c729c157f24184d2744c168b2c`

### `references/design-cards/drive/d01-low-side.md`

- 标题：低侧开关
- 行/字符/字节：274 / 14485 / 27999
- SHA-256：`84a84546fa55923753ecd7b81fc72720e3a8a1ad6bcba935978f6fb143aa82ee`

- L43 [unknown] [`R_DS(on)` 怎么定，栅极怎么驱动和默认关断，感性负载怎么续流，功耗与结温够不够，关断/堵转时 SOA 是否成立。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)
- L47 [unknown] [
### 不能使用的条件

- 负载必须保持硬接地，或必须切断“负载对电源”的短路：低侧开关位于负载与地之间，不能替代高侧开关的故障切断方向；改 [高侧开关](d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)

### `references/design-cards/drive/d02-high-side.md`

- 标题：高侧开关
- 行/字符/字节：290 / 15354 / 29321
- SHA-256：`cd477ba7f4b3e645fb917bd254ed1d86dd2847ca50e431548c957df40222c68f`

- L46 [unknown] [决五个决定：拓扑与器件形态、栅极偏置方式、`V_DS`/`R_DS(on)`/热、短路与感性关断的 SOA、反灌与默认态。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/drive/d03-relay.md`

- 标题：继电器驱动
- 行/字符/字节：274 / 13110 / 27099
- SHA-256：`31e5ac36054fba2635bdc0eeb0bcc7377903b72070358726c7269d7d1362227e`

- L46 [unknown] [卡解决四个决定：线圈钳位方式与释放时间、驱动 MOSFET 的电压/电流应力、触点额定与负载类型的匹配、默认态与故障检测。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)
- L180 [external_reference] [）。

> 算例中的具体型号、阻容、脚号、层数、线宽只适用于本算例条件，不能推广到其他芯片或板。

计时定义依据：[OMRON Release Time](https://www.ia.omron.com/support/guide/36/explanation_of_terms.html) → `https://www.ia.omron.com/support/guide/36/explanation_of_terms.html` (external)

### `references/design-cards/drive/d04-half-bridge.md`

- 标题：半桥
- 行/字符/字节：290 / 14331 / 26342
- SHA-256：`af8915d93bd5aa1a1d383d7ce581e6adee19719471bc44afefcf98d05fe26379`

- L43 [unknown] [个决定：自举电容/二极管/电阻、死区与直通、栅极回路与米勒误导通、开关节点过冲与 SOA、默认态与 100% 占空比限制。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/drive/d05-h-bridge.md`

- 标题：H 桥 / 有刷电机
- 行/字符/字节：278 / 13456 / 26173
- SHA-256：`51c167cd0423a21583453d023a4071f8dc73b6470ec118ce8534f6693a5ddf21`

- L43 [unknown] [四管+栅极驱动。本卡解决五个决定：集成还是分立、`R_DS(on)`/热与堵转、电流调节/采样、死区与直通、回生与默认态。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/drive/d06-stepper.md`

- 标题：步进电机驱动
- 行/字符/字节：268 / 12001 / 23283
- SHA-256：`ea6cade8efc4054ce6b975cb9c964684bfcf4f1c4030132b74c6fddd70d8443c`

- L45 [unknown] [32 微步，STEP/DIR 接口。本卡解决五个决定：相电流/采样电阻、细分与衰减模式、母线储能、驱动器热、默认态与故障。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/drive/d07-led-cc.md`

- 标题：LED 恒流驱动
- 行/字符/字节：271 / 12117 / 22718
- SHA-256：`5b2a30a2fbd078d13ba32ddee50340f489e6908881c12b599f0255238a859a03`

- L47 [unknown] [解决五个决定：串/并联结构、恒流/限流方式与电流设定、压差/功耗/结温、`V_f` 温度与热折返、PWM 调光与故障诊断。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/drive/d08-heater.md`

- 标题：加热器控制
- 行/字符/字节：273 / 12144 / 24780
- SHA-256：`0445d247e423945b43ff71092cea1a5a4223ef2960412169ccf23c62068149f6`

- L43 [unknown] [审）。本卡解决五个决定：开关器件与浪涌、PWM 频率/热循环、过温保护的独立切断、传感器断线/短路检测、默认态与失效分析。

模块组合层面的入口见 [模块卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/interfaces/i01-i2c.md`

- 标题：I²C 总线
- 行/字符/字节：302 / 13360 / 25104
- SHA-256：`2e98529b7b15fadb1a3d25565f137c48c337c1d47432b9e6ccb4eb40683d521e`

- L138 [unknown] [上升；
   - 换更高驱动能力的器件（Fm+，`IOL` 20 mA）；
   - 用缓冲器/多路开关把总线分段，每段各 400 pF（见 [I²C 缓冲](i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L230 [unknown] [构 | 布线顺序见 §9 |
| 缓冲/中继 | 侧别、静态偏移、`tPD`、EN 时序 | 需要 B-B 级联；带上升沿加速器 | — | 见 [IF-02](i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)

### `references/design-cards/interfaces/i02-i2c-buffer.md`

- 标题：I²C 缓冲 / 中继 / 电平转换
- 行/字符/字节：293 / 12109 / 22567
- SHA-256：`abc916a04b4c5c182d7676db1ef11db6b1b1f243245201fa85e4b562378aabc6`

- L41 [background] [## 1. 用途与适用范围

一条 I²C 总线需要"加东西"通常只有两个原因：**电容超了**（`Rp(min) > Rp(max)`，见 [I²C 总线](i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L108 [unknown] [缓冲器自身带来的延时与偏移，因为这两项只有在电气窗口成立之后才有意义。

1. **判据：单段是否已经无解。**
   **做法：** 按 [I²C 总线](i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)

### `references/design-cards/interfaces/i03-spi.md`

- 标题：SPI 点对点
- 行/字符/字节：242 / 9715 / 18889
- SHA-256：`3c5e75a8d7f485f995bd7431843a4e448a3bba39d3803b4d900713d35966495a`

- L52 [unknown] [Hz，板内或短排线。

### 不能使用的条件

- **多从机共享 MISO**：本卡只算点对点；共享总线的争用、死区与片选默认态见 [SPI 多从机](i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L152 [unknown] [I/O 域）保持无效；否则从机会被随机选中，甚至在 `MISO` 上驱动。
   **核对：** `CS` 是否与启动 strap 复用（见 [SPI 多从机](i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)

### `references/design-cards/interfaces/i04-spi-multi.md`

- 标题：SPI 多从机 / 片选
- 行/字符/字节：280 / 10992 / 21638
- SHA-256：`abce98a21e91485fd62883f980959b3c8fd64abb5f9fdfb6803713dc96e76372`

### `references/design-cards/interfaces/i05-uart.md`

- 标题：UART TTL
- 行/字符/字节：288 / 11280 / 21612
- SHA-256：`eb976b53a00586ccaba53f2e90c8c73ffb74538d0d4928fa9ef6f7546e572d5c`

- L53 [unknown] [的条件

- **RS-232/RS-485 电平**：必须外加收发器（AN2606 §4.3 明确"RS-232 电平需外加收发器"），见 [RS-232](i06-rs232.md) → `references/design-cards/interfaces/i06-rs232.md` (ok)

### `references/design-cards/interfaces/i06-rs232.md`

- 标题：RS-232
- 行/字符/字节：285 / 10777 / 21123
- SHA-256：`d2672b56b35622cf66c849b6d6cef7f2376003b367f3f30dfa3d522f86f3fbf3`

- L284 [required_read] [一律待查。**DB9/DB25 针序与 DTE/DCE 是阻断项**：必须按对端设备手册和连接器图纸核对，不能按“常见 2/3/5”直接画；见 [常用硬件 J4](../../common-hardware/j-buses.md) → `references/common-hardware/j-buses.md` (ok)

### `references/design-cards/interfaces/i07-rs485.md`

- 标题：RS-485
- 行/字符/字节：325 / 14789 / 29812
- SHA-256：`b7e81665406f3601c18305e5713fe58aea00f5137ad75af84eca1f36ae657f43`

### `references/design-cards/interfaces/i08-can.md`

- 标题：CAN
- 行/字符/字节：317 / 14360 / 29106
- SHA-256：`854dda6a28bcee592f36c637179692a1131b6f2354a338be2560f3b3896609d6`

### `references/design-cards/interfaces/i09-usb-device.md`

- 标题：USB 2.0 Full-Speed Device
- 行/字符/字节：302 / 14550 / 27034
- SHA-256：`e2e7e67c2141cd823ab06c71633aa48d6b293272e7e42208245db8c7bafb6af0`

### `references/design-cards/interfaces/i10-usbc-data.md`

- 标题：USB-C 数据与 CC
- 行/字符/字节：294 / 13805 / 24748
- SHA-256：`83a592576261f076f38f124a23e31fd94346d355475ecc1963afd0ef2f09909d`

- L54 [required_read] [6 kΩ/22 kΩ/10 kΩ 等阻值（它们在 Figure 4-5/4-7/4-9 等图形内）。本卡**不把这些数值写成已验证**；可先参考 [PWR-12](../power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L54 [required_read] [/4-7/4-9 等图形内）。本卡**不把这些数值写成已验证**；可先参考 [PWR-12](../power/p12-usbc-sink.md) 与 [x08](../../examples/x08-usbc.md) → `references/examples/x08-usbc.md` (ok)

### `references/design-cards/interfaces/i11-ethernet.md`

- 标题：10/100 Ethernet PHY
- 行/字符/字节：304 / 13817 / 26129
- SHA-256：`b03b83966aa45d6b24c5e18c72397e9465ef31ea38fb67364411119560ce42ca`

### `references/design-cards/interfaces/i12-level-shift.md`

- 标题：电平转换选型
- 行/字符/字节：303 / 13309 / 25049
- SHA-256：`10630ab77de70cb08324efb998089396eb28b817874245ddf8292749c5ad2c02`

### `references/design-cards/mcu/m01-bare-mcu.md`

- 标题：裸 MCU 最小系统（STM32 类）
- 行/字符/字节：270 / 12600 / 23574
- SHA-256：`72c986f670fe8b18c0c6884f2422f425eaadbb01803fd6ced57a0a89c15cbe84`

- L47 [unknown] [## 不能使用的条件

- **模组形态**（ESP32 模组、核心板）：模组内部已集成 Flash、晶振、稳压、天线，最小系统是另一套（见 [MCU-02](m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L51 [unknown] [度封装**：AN4488 第 41–50 页（扇出示例）未读，本卡不覆盖其布局。
- **需要功能安全/高可靠复位**：必须叠加外部监控器，见 [MCU-03](m03-reset-supervisor.md) → `references/design-cards/mcu/m03-reset-supervisor.md` (ok)
- L94 [background] [颗电容与芯片之间流动，不能与 VDD 大电容共用一段细长走线。
- **模拟域参考**是 VDDA/VREF+，其回流应与数字开关电流分开（见 [MCU-03](m03-reset-supervisor.md) → `references/design-cards/mcu/m03-reset-supervisor.md` (ok)
- L131 [unknown] [ kΩ 网络图注明确“仅为典型示例”。
   **选择：** 量产默认走主 Flash（BOOT0 下拉）；下载口只留测试点或排针，具体网络见 [MCU-04](m04-boot-strap.md) → `references/design-cards/mcu/m04-boot-strap.md` (ok)
- L135 [unknown] [ 的谐振器，**不要用 CL = 12.5 pF**（会超过 CL1/CL2 的 15 pF 上限）。
   **选择：** 计算与负阻判据见 [MCU-05](m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L139 [background] [TCK/SWCLK 内部下拉，JTDO 浮空；**不需要再加外部电阻**。
   **选择：** 只留连接器、串联小电阻（可选）与地；引脚序见 [MCU-07](m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)

### `references/design-cards/mcu/m02-module-mcu.md`

- 标题：模组最小系统（ESP32 类）
- 行/字符/字节：265 / 11576 / 20968
- SHA-256：`ecb4ded87d0f3f79c51fccaee47f7dbaf9cbdb192fcf027d411fc9f535ce6b58`

- L48 [unknown] [SP32-C3 芯片直接上板，或如 RP2040 的裸片参考设计，MCU-S05）：需要自己画晶振、Flash、匹配网络与天线，本卡不覆盖（对照 [MCU-01](m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L48 [unknown] [参考设计，MCU-S05）：需要自己画晶振、Flash、匹配网络与天线，本卡不覆盖（对照 [MCU-01](m01-bare-mcu.md) 与 [MCU-05](m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)

### `references/design-cards/mcu/m03-reset-supervisor.md`

- 标题：复位与电源监控
- 行/字符/字节：254 / 10094 / 18649
- SHA-256：`bb7cc99963959fb0a4e26cf58d39d59a93d2527fd39e8e8ea1af6acf75282b8a`

### `references/design-cards/mcu/m04-boot-strap.md`

- 标题：启动与配置脚
- 行/字符/字节：238 / 8861 / 16201
- SHA-256：`ffaca2a80d09779d0488f8abbde41ec724e5397247e6e001a2e1ef8b07e2bc41`

### `references/design-cards/mcu/m05-crystal.md`

- 标题：晶体振荡器
- 行/字符/字节：257 / 9555 / 16198
- SHA-256：`217f39a987c63fcd762accc132482003ab50b53bbb078cabee2bc9d8ab7739d0`

- L48 [unknown] [ 外部晶体），HSE 与 LSE 均适用。

### 不能使用的条件

- **有源晶振/外部时钟输入**：不适用负载电容与负阻计算，转 [MCU-06](m06-external-clock.md) → `references/design-cards/mcu/m06-external-clock.md` (ok)

### `references/design-cards/mcu/m06-external-clock.md`

- 标题：外部时钟 / 振荡器输入
- 行/字符/字节：236 / 8599 / 15971
- SHA-256：`f1029d5e545ccb07a60e9383069ae3922eab85661a6481f3a1245119f8876b50`

- L49 [unknown] [# 不能使用的条件

- **差分时钟（LVDS/LVPECL/HCSL）**：需要转换器，本卡不覆盖。
- **晶体/陶瓷谐振器**：转 [MCU-05](m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)

### `references/design-cards/mcu/m07-swd-jtag.md`

- 标题：SWD / JTAG 调试与救援
- 行/字符/字节：240 / 8977 / 16176
- SHA-256：`5658b7153039520f199273ddcf36e3b61ff3fc0008a95acd42a608b7f2e9b1cd`

- L50 [unknown] [.65–3.3 V）：需适配板/隔离。
- **安全芯片/读保护**：SWD 可能只能识别不能读，救援策略不同（AN2606 的 ISP 另走 [MCU-08](m08-uart-bootloader.md) → `references/design-cards/mcu/m08-uart-bootloader.md` (ok)

### `references/design-cards/mcu/m08-uart-bootloader.md`

- 标题：UART Bootloader / ISP
- 行/字符/字节：245 / 9314 / 16333
- SHA-256：`c78e809547f918e88cf479c7158d70f49d3438e9b9bf72326ff55a084da833ff`

### `references/design-cards/power/p01-ldo.md`

- 标题：LDO 线性稳压
- 行/字符/字节：294 / 14309 / 27585
- SHA-256：`77963a9733afd0f53efb3e552e6bcdaa85b1483cec0a0e8bc5867d042f91644d`

- L48 [unknown] [O(max) @ Iout(max)` 时，LDO 进入 dropout，输出跟随输入，纹波与 PSRR 全部失效。此时必须改拓扑（Buck，见 [PWR-02](p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L211 [unknown] [ 开关 Buck | 效率曲线、L/C、EMI | 噪声敏感且无后级滤波 | 需电感/电容/布局 | 5 V→1.8 V 等大压差应优先评估，见 [PWR-02](p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L213 [unknown] [双电源 | 小封装 | 只做通断/保护，不调压 |
| 反向阻断器件 | 正向压降、反向漏电、耐压 | 用普通肖特基做大电流 | 散热 | 见 [PWR-09](p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)

### `references/design-cards/power/p02-buck.md`

- 标题：Buck 降压变换器
- 行/字符/字节：321 / 14120 / 25504
- SHA-256：`4f6701b690f9e2d322765d015f06bfdb4c38bc0fe6f265f882305da4e79d15cc`

### `references/design-cards/power/p03-boost.md`

- 标题：Boost 升压变换器
- 行/字符/字节：316 / 13567 / 23552
- SHA-256：`13ca78d3b9ab477d96a81949f6c74bdcb458922e7088b023cc36272bcf2416a6`

- L53 [unknown] [出仍经电感/二极管连到输入；必须外加负载开关/理想二极管。
- **输入可能高于输出**：此时 Boost 不能调压，需 Buck-Boost（[PWR-04](p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)

### `references/design-cards/power/p04-buck-boost.md`

- 标题：Buck-Boost / SEPIC / 四开关
- 行/字符/字节：294 / 12520 / 23060
- SHA-256：`c1f982ac4b30ef294436e1e294ebb5db82c55f2bed23bac0b94b2c8cce846410`

- L48 [unknown] [用笔记并重新核对；本卡只能提示要问的问题（见 §6）。
- **输入始终高于或始终低于输出**：用四开关会白白增加开关与损耗；应选纯 Buck（[PWR-02](p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L48 [unknown] [**输入始终高于或始终低于输出**：用四开关会白白增加开关与损耗；应选纯 Buck（[PWR-02](p02-buck.md)）或纯 Boost（[PWR-03](p03-boost.md) → `references/design-cards/power/p03-boost.md` (ok)
- L124 [unknown] [*，考虑直流偏压降容；该器件**输出电容无上限**。
   **对照：** LDO TPS7A02 的有效输出电容有 **22 µF 上限**（[PWR-01](p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L190 [unknown] [PG 拉低。
   - **阈值未读到**，不能给出“几伏触发”；设计上应避免 MODE 固定为强制 PWM，或在输出加理想二极管/ORing（[PWR-05](p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)

### `references/design-cards/power/p05-power-mux.md`

- 标题：多源供电与电源路径
- 行/字符/字节：303 / 13379 / 25167
- SHA-256：`a1d8d81d8c2deb1502362e974b626d124fe3bc1baacbe7282fb7290dded33e6b`

- L50 [unknown] [，但不能直接套到低压 USB）。
- **需要 USB-C PD 电压协商**：本卡只处理 5 V 档与 CC 角色之外的电源路径；PD 见 [常用硬件 F3](../../common-hardware/f-input-protection.md) → `references/common-hardware/f-input-protection.md` (ok)
- L52 [unknown] [*：多源共地不等于隔离；隔离边界另按 DM45/DM46。
- **电池保护/充电职责未分清**：保护 IC 不是充电器，充电器不是保护器（见 [PWR-08](p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)

### `references/design-cards/power/p06-linear-charger.md`

- 标题：单节锂电线性充电
- 行/字符/字节：306 / 13666 / 24084
- SHA-256：`26d2ef8b657fa3074bfd847e9215aead11b7b1f4487b984a9f82189abef91ab6`

- L52 [unknown] [续”；线性方案在大压差下热调节会大幅降流。
- **需要开关充电效率**：5 V→3.7 V 线性效率约 74%，大电流/大容量应评估开关充电（[PWR-07](p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L53 [unknown] [7-switching-charger.md)）。
- **电池无保护板或保护参数不明**：充电器不是保护器；过充/过放/过流保护职责必须分清（[PWR-08](p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L226 [unknown] [电同时存在 | 小封装 | 系统可能被充电电流拖累 |
| 开关充电器 | 效率、电感、NVDC、热 | 大压差/大电流 | 电感占板 | 见 [PWR-07](p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L227 [unknown] [er.md) |
| 保护 IC | OVP/UVP/OCC/OCD/SCP 门限与延时 | 门限与充电器不协调 | 与 FET 一起 | 见 [PWR-08](p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)

### `references/design-cards/power/p07-switching-charger.md`

- 标题：开关充电与 Power Path
- 行/字符/字节：306 / 12659 / 22003
- SHA-256：`2a87705a7c6f504aceefabe0d13a9a702ce874533c0fbd9f197227ba6bb0dcea`

- L13 [unknown] [充电电流、热调节与电池补充算清，判断 USB 500 mA 到底能给系统多少、什么时候电池在放电、以及电感/输入电容/散热怎么落地。它和线性充电（[PWR-06](p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)

### `references/design-cards/power/p08-battery-protection.md`

- 标题：1S 电池保护（保护 IC + 背靠背 FET）
- 行/字符/字节：259 / 12351 / 23835
- SHA-256：`a4ec5a1be3a00edf4e392ba01819ca95d7688f18da4f82fee2f4cbb364bb7605`

### `references/design-cards/power/p09-reverse-polarity.md`

- 标题：反接保护
- 行/字符/字节：238 / 9833 / 19637
- SHA-256：`55a7b0344da1d34c217d9b026bc274bf7f2116298168671ba7992f3bc7ab9715`

### `references/design-cards/power/p10-hot-swap.md`

- 标题：热插拔与浪涌限制
- 行/字符/字节：233 / 10574 / 19111
- SHA-256：`3877a81ecd7b807998ce0aba4afe180a800b298528cf66fbd885dab45491c7f6`

### `references/design-cards/power/p11-efuse.md`

- 标题：保险丝 / eFuse / 限流
- 行/字符/字节：235 / 9616 / 18977
- SHA-256：`024f38f7170530f66540eac1016f7cb68df85e4b451d6c0ddcbcb832f5413fde`

### `references/design-cards/power/p12-usbc-sink.md`

- 标题：USB-C 5V Sink
- 行/字符/字节：242 / 11158 / 19149
- SHA-256：`e50a0470780943c83265db9029ddc2d702f29b6454b4da42ffac5d38498dbfa5`

### `references/design-cards/power/p13-usbc-source.md`

- 标题：USB-C 5V Source / OTG
- 行/字符/字节：241 / 10036 / 17537
- SHA-256：`2b5053fae3de37f5c2e33eabda2018f2cfdcf91e7738d8917c744663e302befa`

### `references/design-cards/power/p14-supercap-backup.md`

- 标题：超级电容 / RTC 备份 / 掉电保持
- 行/字符/字节：243 / 9143 / 17446
- SHA-256：`a23d6eecf3d598769434504bb7453242be412cc24f3bc185c15c0337e18c139a`

### `references/design-cards/wireless/w01-wifi-ble.md`

- 标题：Wi-Fi / BLE 模组
- 行/字符/字节：202 / 11183 / 21138
- SHA-256：`0c38dfd79b0fb890ffac1b377882455dc87f67847f125da57193431420b0e73f`

- L41 [unknown] [型输出是 3.3 V 轨电流预算、bulk/去耦电容、EN RC、strap 电阻表、天线伸出/挖空要求和验证项。

模组组合层面的整体检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/wireless/w02-antenna.md`

- 标题：天线接口与匹配
- 行/字符/字节：195 / 8935 / 18011
- SHA-256：`c572d2b7aa00293b85fba71c7dddf7865e044f3456bfa8a8f4d30761964de07a`

- L41 [unknown] [是馈线阻抗与走向、匹配元件拓扑与初值、净空区、测试口和验证计划。

它不设计天线本身，也不替代天线厂的调谐报告或整机认证。模组组合层面的检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/wireless/w03-cellular.md`

- 标题：蜂窝模组电源
- 行/字符/字节：198 / 8907 / 17042
- SHA-256：`34c49c1b22c5411f614073049f88db17321c22c56ce1f9ba9c6fe5410ea70478`

- L41 [unknown] [热；典型输出是电源选型、电容组合、走线宽度、TVS 和验证波形要求。

蜂窝射频、SIM 协议、运营商认证不在本卡范围内。模组组合层面的检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/wireless/w04-gnss.md`

- 标题：GNSS 模组
- 行/字符/字节：195 / 8359 / 16573
- SHA-256：`e0465a8612052565e433d891446b989ff5d248e350b8b34c397de396aeddc87d`

- L41 [unknown] [天线选型、偏置网络、屏蔽/滤波方案、keep-out 和验证计划。

它不设计天线辐射体，也不替代整机定位性能/认证测试。模组组合层面的检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/wireless/w05-display.md`

- 标题：SPI TFT 显示与背光
- 行/字符/字节：209 / 9900 / 18137
- SHA-256：`9940acb02e13aa43514027d85ebea1e6848a130338341762f5e2e2f688735242`

- L41 [unknown] [、背光 LED 串并数与电流、结构视角；典型输出是接口模式、时序上限、复位序列、背光驱动与电感/电容、FPC 连接器和验证项。

选屏判据见 [L4 TFT](../../common-hardware/l-hmi.md) → `references/common-hardware/l-hmi.md` (ok)
- L41 [unknown] [电容、FPC 连接器和验证项。

选屏判据见 [L4 TFT](../../common-hardware/l-hmi.md) 与 [L3 OLED/LCD](../../common-hardware/l-hmi.md) → `references/common-hardware/l-hmi.md` (ok)
- L41 [unknown] [./common-hardware/l-hmi.md)；本卡只处理接口与背光，不做触摸/显示驱动软件，也不替代屏厂模组规格书。模组组合层面的检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)
- L133 [unknown] [| 接口模式、时序、供电、FPC | IM 组合不匹配、时序不够 | FPC 脚序/正反面 | 控制器 datasheet ≠ 屏规格书；选屏见 [L4 TFT](../../common-hardware/l-hmi.md#l4-tft-显示) → `references/common-hardware/l-hmi.md` (ok) #l4-tft-显示 ok

### `references/design-cards/wireless/w06-classd.md`

- 标题：Class-D 音频功放
- 行/字符/字节：199 / 8293 / 15759
- SHA-256：`eabc9355c1723d11cfb8f2fda05d3426b2653b0b8b54d0198e5c7d2f0454d368`

- L41 [unknown] [扑、L/C 值、器件应力、端口/静音设计和验证项。

它不选功放、不做声学调音/增益结构，也不替代 EMC/音频指标测试。模组组合层面的检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/wireless/w07-spi-flash.md`

- 标题：SPI NOR Flash
- 行/字符/字节：199 / 9677 / 17445
- SHA-256：`8ed79c7ff69beee55c37b2b70b389a276ea3f1bf66deda022883c11aea4b6ff6`

- L41 [unknown] [配置、上拉/串联电阻、启动 strap 网络、去耦和验证项。

它不处理文件系统、OTA、安全启动或 NAND/eMMC。模组组合层面的检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-cards/wireless/w08-microsd.md`

- 标题：microSD 接口
- 行/字符/字节：204 / 9415 / 17287
- SHA-256：`32b7e9a7da0475f4ee0cb3d9c1edee024dc1051b6aed9b4e891e0eeb3a26a80b`

- L41 [unknown] [测/ACMD42 方案、电源开关、ESD 器件和验证项。

它不处理文件系统、SD 协议栈、UHS-II 或卡兼容性认证。模组组合层面的检查见 [模块设计卡](../../module-cards.md) → `references/module-cards.md` (ok)

### `references/design-engine.md`

- 标题：确定性设计引擎：IR、几何审计与标签规划
- 行/字符/字节：176 / 9944 / 16754
- SHA-256：`e36b2a061800243e365b727e6afdb8a0d520755f839f62fd0a6d85df5d29c5fc`

- L90 [external_reference] [出图；计划里的模拟结果不是 EDA 验收。

本仓库已在独立导入副本上验证过 9 个 Name/Designator 移动、保存和重开（见[真实应用（仓库证据）](https://github.com/zsx3896926/EasyCirq/blob/main/docs/round7/a08-real-apply.md) → `https://github.com/zsx3896926/EasyCirq/blob/main/docs/round7/a08-real-apply.md` (external)

### `references/design-experience.md`

- 标题：工程经验库：选择、应用与继续积累
- 行/字符/字节：63 / 5502 / 10166
- SHA-256：`d9a912d0de71571237d55a918ea96e75d5e55743530fed0485fd4906b564fd8a`

- L9 [unknown] [

## 选择本次需要的部分

| 当前对象 | 加载 | 本次应留下的证据 |
|---|---|---|
| 新建/修改原理图 | [原理图细节](schematic-details.md) → `references/schematic-details.md` (ok)
- L10 [unknown] [改原理图 | [原理图细节](schematic-details.md) | 适用的引脚/电源/接口核对、实际连接回读 |
| 图面混乱 | [排版与看图验收](schematic-layout.md) → `references/schematic-layout.md` (ok)
- L11 [unknown] [图面混乱 | [排版与看图验收](schematic-layout.md) | 连接基线、实际整页与局部图 |
| PCB放件、改尺寸或换封装 | [布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L12 [background] [装 | [布局细节](pcb-placement-details.md) | 机械约束、关键回路与敏感区位置 |
| 布线/铺铜/改层叠 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L13 [unknown] [布线与回流细节](pcb-routing-details.md) | 网络规则、参考层、实际铜连接与未布线 |
| 准备打板/贴片/手焊 | [制造与首板细节](manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L14 [unknown] [/手焊 | [制造与首板细节](manufacturing-details.md) | 同版制造包、装配变体与待测清单 |
| 某类具体硬件 | [领域易漏项](domain-design-details.md) → `references/domain-design-details.md` (ok)
- L20 [conditional_read] [选优化不得伪装为阻断。具体数值服从器件手册、项目约束和实际板厂订单。

## 把经验落实到当前模块

需要解释失效原因或检查方法时，再读 [原理图机制卡](schematic-lessons.md) → `references/schematic-lessons.md` (ok)
- L20 [conditional_read] [。

## 把经验落实到当前模块

需要解释失效原因或检查方法时，再读 [原理图机制卡](schematic-lessons.md) 与 [PCB机制卡](pcb-lessons.md) → `references/pcb-lessons.md` (ok)
- L28 [external_reference] [ 本轮实际查看范围 | 可以吸收的经验 / 不能照搬的部分 |
|---|---|---|
| P01 [SparkFun ESP32 Thing Plus](https://cdn.sparkfun.com/assets/6/d/c/6/c/ESP32_Thing_Plus_Schematic.pdf) → `https://cdn.sparkfun.com/assets/6/d/c/6/c/ESP32_Thing_Plus_Schematic.pdf` (external)
- L29 [external_reference] [pdf) | 单页图纸；原作者仓库在排版参考中 | 功能分区、局部拓扑和远端网名；不照搬旧器件与外围参数 |
| P02 [SparkFun ESP32-S3](https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf) → `https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf` (external)
- L30 [external_reference] [_Plus_ESP32-S3.pdf) | 两页实际图纸 | 主控/外围分页和约束注释；叠层专属线宽不得通用化 |
| P03 [Arduino UNO R3](https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf) → `https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf` (external)
- L31 [external_reference] [tics.pdf) | 单页实际图纸 | 电源、USB和主控区域组织；AVR与其他MCU不能直接互套 |
| P04 [ODrive v3 CHANGELOG](https://github.com/odriverobotics/ODriveHardware/blob/master/v3/CHANGELOG.md) → `https://github.com/odriverobotics/ODriveHardware/blob/master/v3/CHANGELOG.md` (external)
- L32 [external_reference] [lvin净距用net-tie表达、DFU时控制脚状态、端接可配置；其分地方案只属于该设计 |
| P05 [Crazyflie Brushless Rev.G](https://www.bitcraze.io/documentation/hardware/crazyflie_2_1_brushless/cf2.1_bl_schematics_Rev.G.pdf) → `https://www.bitcraze.io/documentation/hardware/crazyflie_2_1_brushless/cf2.1_bl_schematics_Rev.G.pdf` (external)
- L33 [external_reference] [图像 | 重复电调用层次页实例组织、供电与传感器独立页、调试口与不装件标记；源图含非商业许可限制，不能当MIT附件分发 |
| P06 [RP2040硬件设计](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf) → `https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf` (external)
- L34 [external_reference] [ | 图中器件关系要落到实际PCB；板厚改变后需重新核对USB传输线；RP2040专属电路不泛化到RP2350/STM32 |
| P07 [泰山派手机扩展板](https://wiki.lckfb.com/zh-hans/tspi-rk3566/project-case/fat-little-cell-phone/mobile-phone-integrated-project.html) → `https://wiki.lckfb.com/zh-hans/tspi-rk3566/project-case/fat-little-cell-phone/mobile-phone-integrated-project.html` (external)
- L35 [external_reference] [本 | FPC线序与网络错位需独立核对；已知固件隔离硬件问题；参考载板与屏版本必须一致；未读取附件PCB，不声称已审完整布线 |
| P08 [EEZ BB3](https://github.com/eez-open/modular-psu) → `https://github.com/eez-open/modular-psu` (external)
- L36 [external_reference] [具体功率板图纸 | 背板、电源模块、MCU、结构文件分开管理；只作为模块化交付组织样本，不提炼其布线数值 |
| P09 [OLIMEX STM32-E407](https://www.olimex.com/Products/ARM/ST/STM32-E407/) → `https://www.olimex.com/Products/ARM/ST/STM32-E407/` (external)
- L37 [external_reference] [入口 | 旧/新PHY固件应匹配板版；未成功读取PDF内容，不据此声称验证其电路 |
| G01 [Espressif schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/schematic-checklist.html) → `https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/schematic-checklist.html` (external)
- L38 [external_reference] [源、启动、GPIO、存储章节 | 复位/strap与外围相互作用、输入专用脚及已占用脚；必须切到实际芯片系列 |
| G02 [Espressif PCB指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html) → `https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html` (external)
- L39 [external_reference] [线章节 | 连续参考、模组位置与壳体影响；不要把ESP32的净空距离、层数或线宽当所有无线器件标准 |
| G03 [TI Power Tips：寻找开关回路](https://www.ti.com/document-viewer/lit/html/SSZTBF4/GUID-095BD04D-6DAF-42E7-9AA0-72CB14E1F58C) → `https://www.ti.com/document-viewer/lit/html/SSZTBF4/GUID-095BD04D-6DAF-42E7-9AA0-72CB14E1F58C` (external)
- L40 [external_reference] [B14E1F58C) | 拓扑开/关状态与脉动回路说明 | 按拓扑找不连续电流回路；文章的单过孔电流经验不作为设计保证 |
| G04 [TI低侧电流采样布局](https://www.ti.com/document-viewer/lit/html/SSZT805/GUID-5F278960-BA94-4362-9099-87ABC753A4D6) → `https://www.ti.com/document-viewer/lit/html/SSZT805/GUID-5F278960-BA94-4362-9099-87ABC753A4D6` (external)
- L41 [external_reference] [87ABC753A4D6) | Kelvin与地压降误差分析 | 采样点和参考点要一起落实；不能只在网络名写SENSE |
| G05 [ADI MT-031](https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf) → `https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf` (external)
- L42 [external_reference] [rials/MT-031.pdf) | 接地与数据转换器回流说明 | 按电流路径理解AGND/DGND，不机械套用割地 |
| G06 [TI SLLA414](https://www.ti.com/lit/an/slla414/slla414.pdf) → `https://www.ti.com/lit/an/slla414/slla414.pdf` (external)
- L43 [external_reference] [lla414.pdf) | 高速差分、过孔、回流和ESD章节 | 按通道检查阻抗不连续和支路；接口速率/平台约束分别处理 |
| G07 [ST AN4488](https://www.st.com/resource/en/application_note/an4488-getting-started-with-stm32f4xxxx-mcu-hardware-development-stmicroelectronics.pdf) → `https://www.st.com/resource/en/application_note/an4488-getting-started-with-stm32f4xxxx-mcu-hardware-development-stmicroelectronics.pdf` (external)
- L44 [external_reference] [ STM32F4硬件指南章节 | 特殊供电脚、复位、启动和调试的查证入口；VCAP/电容和封装依实际型号 |
| G08 [Bosch BME280 HSMI](https://www.bosch-sensortec.com/media/boschsensortec/downloads/handling_soldering_mounting_instructions/bst-bme280-hs006.pdf) → `https://www.bosch-sensortec.com/media/boschsensortec/downloads/handling_soldering_mounting_instructions/bst-bme280-hs006.pdf` (external)
- L45 [external_reference] [气路、机械应力、涂覆与清洗章节 | 传感器的环境接触/机械条件属于设计本体；不把大铜散热和涂覆保护强套给环境传感器 |
| G09 [TI TUSB320LI](https://www.ti.com/product/TUSB320LI) → `https://www.ti.com/product/TUSB320LI` (external)
- L46 [external_reference] [ct/TUSB320LI) | 官方CC控制器说明 | Type-C需要角色/方向与供电策略；具体电阻/状态仍读手册和协议 |
| G10 [ADI AN88](https://www.analog.com/media/en/technical-documentation/application-notes/an88f.pdf) → `https://www.analog.com/media/en/technical-documentation/application-notes/an88f.pdf` (external)
- L47 [external_reference] [本次读取4页热插拔LC振铃与阻尼分析 | 陶瓷输入电容与线缆可产生过冲；文中器件/阻尼值仅适用其示例，不直接迁移 |
| T01 [KiCad 9 PCB手册](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) → `https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html` (external)
- L48 [external_reference] [ml) | 铺铜、布线、规则与输出章节 | 铜区轮廓不代表已重填充；工具描述仅说明KiCad行为，不能冒充EasyEDA命令 |
| M01 [嘉立创阻焊说明](https://www.jlc.com/portal/q6i34402.html) → `https://www.jlc.com/portal/q6i34402.html` (external)
- L49 [external_reference] [6i34402.html) | Mask/Paste与阻焊桥说明 | 阻焊与钢网不同，阻焊桥受实际工艺限制；下单再查当前能力 |
| M02 [嘉立创工艺总览](https://www.jlc.com/portal/vtechnology.html) → `https://www.jlc.com/portal/vtechnology.html` (external)
- L49 [unknown] [portal/vtechnology.html) | 本次已读取FR4/孔/阻焊/成型和SMT对比正文，替代先前读取失败的状态 | 条件快照与冲突见 [生产规则](jlc-production.md) → `references/jlc-production.md` (ok)
- L62 [example] [的 60 张设计卡、12 组范例、22 个故障案例（后续新增 F23–F33，共 33 个）、选型/计算/制造/项目内容所引用的资料，统一登记在 [原始来源登记](source-register.md) → `references/source-register.md` (ok)

### `references/design-gates.md`

- 标题：阶段门禁：G0–G6
- 行/字符/字节：411 / 30667 / 47186
- SHA-256：`60956d1ebd8fb2b941bc9141d74b55519d58b84ec3644a0a457abdf91b853c01`

- L3 [unknown] [# 阶段门禁：G0–G6

> 本文定义 G0–G6 阶段退出证据门禁。阶段本身（S0–S5）与五状态词以 [SKILL.md](../SKILL.md) → `SKILL.md` (ok)
- L3 [unknown] [定义 G0–G6 阶段退出证据门禁。阶段本身（S0–S5）与五状态词以 [SKILL.md](../SKILL.md) §4 为准；工程推进叙事见 [工程工作流](workflow.md) → `references/workflow.md` (ok)
- L3 [unknown] [状态词以 [SKILL.md](../SKILL.md) §4 为准；工程推进叙事见 [工程工作流](workflow.md)；证据记录纪律见 [证据与工程记录](evidence.md) → `references/evidence.md` (ok)
- L9 [example] [先评审 / 这步给我看 / 确认后再布线”时，才在方案、原理图、布局、交付四个可见检查点等待。

- 门禁失败只暂停依赖链路，其余工作继续（与 [工程工作流](workflow.md) → `references/workflow.md` (ok)
- L70 [background] [* 对话、参考工程、外壳/结构资料、既有 BOM 与用户约束；写入 `design-state.json` 的 `requirements`。模板见 [需求摘要](../assets/design-brief.md) → `assets/design-brief.md` (ok)
- L74 [example] [te.json` | `schema` 为 `design-state/v1` | 缺文件或 schema 不符 → `BLOCKED`；先复制 [示例状态文件](../assets/design-state.example.json) → `assets/design-state.example.json` (ok)
- L111 [unknown] [读、网表与设计意图一致，再进入 PCB。

**必需输入：** 已保存并回读的原理图；计划网表与实际网表；整页导出图；图签信息。适用检查提示见 [原理图细节](schematic-details.md) → `references/schematic-details.md` (ok)
- L111 [unknown] [原理图；计划网表与实际网表；整页导出图；图签信息。适用检查提示见 [原理图细节](schematic-details.md) 的 SC 条目与 [原理图工程习惯](schematic.md) → `references/schematic.md` (ok)
- L161 [unknown] [成大面积返工。

**必需输入：** 层叠决策（2 层 vs 4 层）、电源树、地策略、DRC 规则、铺铜/平面回执、过孔清单。方法细节见 [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L161 [unknown] [略、DRC 规则、铺铜/平面回执、过孔清单。方法细节见 [布线与回流细节](pcb-routing-details.md) 的 RT 条目与 [PCB 工程习惯](pcb.md) → `references/pcb.md` (ok)
- L185 [unknown] [ 把电源/地布成 track，是 G4 未过就布线的典型后果。

### 电源主干的条件复核

涉及载流主干设计或线宽整改时，补充 [电源路径与走廊预检](power-routing-preflight.md) → `references/power-routing-preflight.md` (ok)
- L193 [unknown] [
**必需输入：** 布线计划、关键网清单、完整 DRC、关键网 `net-path` 证明、保存重载回读、丝印检查、DRC 轮次记录。计划模板见 [布线计划](../assets/routing-plan.md) → `assets/routing-plan.md` (ok)
- L201 [unknown] [false` 表示未走线证明，不等于全板断连；缺证明 → `BLOCKED`（不可豁免） |
| `routing_plan` | 计划 | 阅读 [布线计划](../assets/routing-plan.md) → `assets/routing-plan.md` (ok)
- L218 [unknown] [持项。

**必需输入：** Gerber、钻孔、CPL/坐标、BOM、工艺档案、工程导出包、库存/SMT 核对时间、测试计划。制造细节见 [制造与首板细节](manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L218 [unknown] [OM、工艺档案、工程导出包、库存/SMT 核对时间、测试计划。制造细节见 [制造与首板细节](manufacturing-details.md)、[生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)
- L218 [unknown] [制造细节见 [制造与首板细节](manufacturing-details.md)、[生产规则接入](jlc-production.md) 与 [制造与交付路线](manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L226 [unknown] [`（不可豁免）；缺 MPN/厂家只给 advisory `warn` |
| `manufacturing_profile` | 记录 | 按 [工艺档案模板](../assets/manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L246 [example] [门禁引用既有检查体系，不替代、不复制条款正文。

### 12.1 SC / PL / RT / MF / DM 编号

- **SC**（[原理图细节](schematic-details.md) → `references/schematic-details.md` (ok)
- L247 [example] [C01 完整型号、SC02 引脚三方对照、SC04 特殊脚分类。G2 要求证据显示适用条目已落实，不在本文复述条目内容。
- **PL**（[PCB 布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L248 [example] [ 的机械外形、安装孔、接口插拔、正反面与高度分区；例如 PL01 外形先确定、PL02 孔不只是圆、PL03 接口可插拔。
- **RT**（[布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L249 [example] [换层回流、铜区与最终状态；例如 RT27 铜区真实状态、RT30 缝合有目的、RT32 移动后重验、RT33 实际连通性。
- **MF**（[制造与首板细节](manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L250 [unknown] [6 的焊盘、成品孔、阻焊/钢网、散热焊盘与 DNP；例如 MF01 实物焊接面、MF02 成品孔公差、MF08 DNP 钢网。
- **DM**（[领域易漏项](domain-design-details.md) → `references/domain-design-details.md` (ok)
- L251 [unknown] [n-design-details.md)）按具体硬件类型补充 G2/G3/G4 的适用项；领域覆盖不等于该领域已验证。
- 条目选择方法见 [工程经验库与来源](design-experience.md) → `references/design-experience.md` (ok)
- L259 [unknown] [证明 PCB 网表与原理图一致。网表不包含未连引脚，单靠网表不能证明 NC 状态。

### 12.3 connectivity 硬门禁

[连接表契约](connectivity.md) → `references/connectivity.md` (ok)
- L263 [unknown] [mplete`，不能算覆盖完整。按 SKILL.md §6，它不是每次修改的强制前置。

### 12.4 decision 有效性门禁

[设计决策库](decisions/README.md) → `references/decisions/README.md` (ok)

### `references/digital.md`

- 标题：数字系统与接口
- 行/字符/字节：27 / 1105 / 2620
- SHA-256：`b6dcd59e42211fceb7fdabe9d6a5057ba8e4d575bd97f0be5baed4a36acd01a2`

- L3 [unknown] [# 数字系统与接口

> 本文保留数字系统与接口的通用判断。逐脚最小系统、时钟、复位、下载和具体接口的设计卡见 [设计卡库](design-cards/README.md) → `references/design-cards/README.md` (ok)

### `references/domain-design-details.md`

- 标题：领域易漏项：从通用流程到具体电路
- 行/字符/字节：88 / 4086 / 9622
- SHA-256：`1740e208bd87d21f4addbbdb6fa91b3e699ffbb36d25021f2c0e93fdc47642d8`

- L3 [required_read] [M条目。这里提供查证入口与跨原理图/PCB的检查动作，不是经过验证的通用电路库。源码/原理图/固件/机械参考各自核对授权和版本；工程经验与来源的关系见 [经验库](design-experience.md) → `references/design-experience.md` (ok)

### `references/domains.md`

- 标题：主流硬件领域路由
- 行/字符/字节：28 / 1588 / 3648
- SHA-256：`a9342bca7f1d8d4c8493f81a00c9ff5d65d5b9f30a9ad31ef4808b92ca622f5f`

- L7 [unknown] [
|---|---|---|
| 日常常用硬件（测温/称重/压力/液位/风扇/电池/屏幕/按键） | 用户原话、量程、介质、安装、校准、供电 | [常用硬件](common-hardware/README.md) → `references/common-hardware/README.md` (ok)

### `references/easyeda-ecosystem.md`

- 标题：EasyEDA 生态集成（v1.0）
- 行/字符/字节：62 / 2607 / 4335
- SHA-256：`41484f627219a7e80230db95b39c9eb628f828361ef859631ffba223cd250c3b`

- L5 [unknown] [查过的生态项目转为可执行离线工具、适用性规则和可选择的宿主集成。
不安装或启动第二个 EDA 桥接，不变更现有工程。固定来源见
[registry.json](../assets/ecosystem/registry.json) → `assets/ecosystem/registry.json` (ok)
- L25 [conditional_read] [际整合 | 进一步资料 |
|---|---|---|
| 差分/等长、线宽间距建议 | 路径审核、有界补长候选、规则预览；无自动写铜 | [routing](ecosystem-routing.md) → `references/ecosystem-routing.md` (ok)
- L26 [conditional_read] [em-routing.md) |
| 导出工程取证 | 解析上游导出结构、保留可用性与身份缺口；不是 before_dump | [capture/reuse](ecosystem-capture-reuse.md) → `references/ecosystem-capture-reuse.md` (ok)
- L27 [conditional_read] [-capture-reuse.md) |
| 从已有模块提速 | 目录检索、实例/引脚/网络与选区快照兼容性计划；不直接放置 | [capture/reuse](ecosystem-capture-reuse.md) → `references/ecosystem-capture-reuse.md` (ok)
- L28 [conditional_read] [euse](ecosystem-capture-reuse.md) |
| 原生文件/图元 | 容器安全检查、固定 schema 的保守校验 | [files](ecosystem-files.md) → `references/ecosystem-files.md` (ok)
- L29 [conditional_read] [(ecosystem-files.md) |
| 不占 EDA 的审图 | 与单独部署 viewer 的只读页面、位号定位集成；渲染器未捆绑 | [files](ecosystem-files.md) → `references/ecosystem-files.md` (ok)

### `references/ecosystem-capture-reuse.md`

- 标题：EasyEDA batch capture and module reuse
- 行/字符/字节：107 / 6033 / 6033
- SHA-256：`1a0b3b074749e4ab3f58cacd82b55195c36e189d902788d4e3e1be7fa865c010`

- L95 [external_reference] [ng

Contract source reviews pinned on 2026-10-27:

- [eext-batch-data-export](https://github.com/easyeda/eext-batch-data-export/tree/16c0b33ca318abf162d21a287e5695ed1d8c1e73) → `https://github.com/easyeda/eext-batch-data-export/tree/16c0b33ca318abf162d21a287e5695ed1d8c1e73` (external)
- L98 [external_reference] [ject.ts`, `src/dataCollectors.ts` and LICENSE.
- [eext-ai-reuse-block-placement](https://github.com/easyeda/eext-ai-reuse-block-placement/tree/c24c7228b022c53e509788ef375e1bf81bd82966) → `https://github.com/easyeda/eext-ai-reuse-block-placement/tree/c24c7228b022c53e509788ef375e1bf81bd82966` (external)

### `references/ecosystem-files.md`

- 标题：EasyEDA file inspection and local preview
- 行/字符/字节：74 / 4420 / 4420
- SHA-256：`4cc828686cd6549c423a84a5028b01206c173b7b13fbf1970b4c60e396c18c99`

### `references/ecosystem-routing.md`

- 标题：EasyEDA routing and design-rule absorption
- 行/字符/字节：104 / 6233 / 6233
- SHA-256：`2530d788f8f30b8ae675ef22bbfafa73d723bbfa910226157974f125909221bd`

### `references/eda-efficiency.md`

- 标题：EDA 执行效率、批量写入与可恢复交付
- 行/字符/字节：295 / 10092 / 16794
- SHA-256：`e4b4672f1610c116d678e895398053cc9981a30ffc86f350e85d6ea056ba6ada`

### `references/eda-execution.md`

- 标题：EDA真实执行契约
- 行/字符/字节：164 / 12386 / 21854
- SHA-256：`fcf17aa5767ea3e20499608a57c15e0bfd371ad0dbcdb1ee08d173d7da81147d`

- L3 [required_read] [# EDA真实执行契约

制造规则写入遵循 [生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)
- L9 [unknown] [-agent CLI 时）

`easyeda-agent`（本机实测 v1.15.0）的页面/文档语义与前台焦点、引擎缓存强相关；遇到异常先查 [工具陷阱](tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L15 [unknown] [表内容是 JSON，解析失败按不可用处理。

批量执行、检查点/断点续跑、版本化缓存、通道模板复用、多 Agent 单写入者与耗时记录，见 [EDA执行效率](eda-efficiency.md) → `references/eda-efficiency.md` (ok)
- L94 [example] [/几何、端口方向/几何、导线（含不可解析线）、属性；任一不可比较项（如斜线）强制 `mismatch`，不能宣称持久化完成。

示例计划见 [EDA计划示例](../assets/eda/plan-example.json) → `assets/eda/plan-example.json` (ok)

### `references/enclosure-integration.md`

- 标题：PCB、外壳与安装协同
- 行/字符/字节：30 / 1174 / 3078
- SHA-256：`41f40d13bfe08a3cf4c63d53b1cb4f98011e0a90692d541e3cad06501bfa331c`

### `references/engineering-deepdives/README.md`

- 标题：工程深潜：真实设计、失效机制与审图训练
- 行/字符/字节：128 / 5195 / 8829
- SHA-256：`4f8d810fb1496c4c48d0ca280926a1b2c8b9ecab5eb3d1022759b2032d6a916c`

- L5 [unknown] [# 工程深潜：真实设计、失效机制与审图训练

## 内容导航

- [1. 和现有内容的分工](#1-和现有内容的分工) → `references/engineering-deepdives/README.md` (ok) #1-和现有内容的分工 ok
- L6 [unknown] [# 工程深潜：真实设计、失效机制与审图训练

## 内容导航

- [1. 和现有内容的分工](#1-和现有内容的分工)
- [2. 按症状找](#2-按症状找) → `references/engineering-deepdives/README.md` (ok) #2-按症状找 ok
- L7 [unknown] [练

## 内容导航

- [1. 和现有内容的分工](#1-和现有内容的分工)
- [2. 按症状找](#2-按症状找)
- [3. 按设计阶段找](#3-按设计阶段找) → `references/engineering-deepdives/README.md` (ok) #3-按设计阶段找 ok
- L8 [unknown] [的分工](#1-和现有内容的分工)
- [2. 按症状找](#2-按症状找)
- [3. 按设计阶段找](#3-按设计阶段找)
- [4. 按器件/领域找](#4-按器件领域找) → `references/engineering-deepdives/README.md` (ok) #4-按器件领域找 ok
- L9 [unknown] [按症状找](#2-按症状找)
- [3. 按设计阶段找](#3-按设计阶段找)
- [4. 按器件/领域找](#4-按器件领域找)
- [5. 证据怎么读](#5-证据怎么读) → `references/engineering-deepdives/README.md` (ok) #5-证据怎么读 ok
- L10 [unknown] [设计阶段找](#3-按设计阶段找)
- [4. 按器件/领域找](#4-按器件领域找)
- [5. 证据怎么读](#5-证据怎么读)
- [6. 文件地图](#6-文件地图) → `references/engineering-deepdives/README.md` (ok) #6-文件地图 ok
- L11 [unknown] [/领域找](#4-按器件领域找)
- [5. 证据怎么读](#5-证据怎么读)
- [6. 文件地图](#6-文件地图)
- [7. Agent 使用规则](#7-agent-使用规则) → `references/engineering-deepdives/README.md` (ok) #7-agent-使用规则 ok
- L12 [unknown] [](#5-证据怎么读)
- [6. 文件地图](#6-文件地图)
- [7. Agent 使用规则](#7-agent-使用规则)
- [8. 不覆盖什么](#8-不覆盖什么) → `references/engineering-deepdives/README.md` (ok) #8-不覆盖什么 ok
- L23 [unknown] [舍和可训练的审图题**。

## 1. 和现有内容的分工

| 已有内容 | 负责 | 本目录补什么 |
|---|---|---|
| [设计卡库](../design-cards/README.md) → `references/design-cards/README.md` (ok)
- L24 [unknown] [-cards/README.md) | 拓扑、参数步骤、算例、逐脚/PCB 要求 | 为什么选这个拓扑、真实设计怎么落地、哪里容易误判 |
| [故障与反例库](../failures/README.md) → `references/failures/README.md` (ok)
- L25 [unknown] [res/README.md) | 单点故障的现象→假设→检查→修复 | 跨模块组合失效、测量误判、版本/替代料边界（F23–F33） |
| [组合与接口契约](../module-integration.md) → `references/module-integration.md` (ok)
- L26 [unknown] [module-integration.md) | 接口契约、6 个组合案例 | 8+ 个“单模块正常、组合失败”的机制与区分检查（D1） |
| [仿真与测量](../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L27 [unknown] [simulation-measurement.md) | 仿真/测量总则 | 测量接法制造的假象、示波器/探头/分流器的具体算例（C4） |
| [板级热专题](../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L35 [unknown] [| 你看到的现象 | 先读 | 再查 |
|---|---|---|
| 插上 USB/适配器/调试器后复位、发热、反向供电 | [B1 多路供电与电源切换](topics/b1-power-path-and-source-switching.md) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok)
- L36 [unknown] [urce-switching.md) | F23、F27、PWR-05/09/10 |
| 电池设备待机远超标称、续航对不上 | [B2 低功耗整机与睡眠电流](topics/b2-sleep-current-budget.md) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok)
- L37 [unknown] [budget.md) | PWR-01、MCU-02、任务场景 S04/S34 |
| 充电慢、充电时系统掉电、电量跳变 | [B3 充电、系统负载与电量判断](topics/b3-charger-load-and-gauge.md) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok)
- L38 [unknown] [r-load-and-gauge.md) | PWR-06/07/08、F09 |
| 无线发射/电机启动时系统复位或音频爆音 | [B4 电源动态与负载瞬态](topics/b4-power-dynamics.md) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok)
- L39 [unknown] [power-dynamics.md) | F25、F26、RF-03 |
| 传感器读数有偏、跳、温漂、校准后仍不够 | [C1 从传感器到 ADC 的误差链](topics/c1-sensor-to-adc-error-chain.md) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok)
- L40 [unknown] [or-chain.md) | ANA-01/03/04/05、F01/F22 |
| 模拟量被数字/功率噪声污染，地怎么接都别扭 | [C2 接地、屏蔽与共模](topics/c2-grounding-shielding-common-mode.md) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok)
- L41 [unknown] [g-common-mode.md) | F16/F17、MT-031 |
| 运放直流增益对，但输出饱和/振铃/上电异常 | [C3 运放容易被漏查的工作条件](topics/c3-opamp-hidden-conditions.md) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok)
- L42 [unknown] [ditions.md) | ANA-02/03/04、SBOA583 |
| 示波器看到“明显振铃/纹波”，改板后却没改善 | [C4 测量方法本身造成的错误](topics/c4-measurement-artifacts.md) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok)
- L43 [unknown] [ment-artifacts.md) | F33、仿真与测量 §5 |
| 单个模块都正常，接在一起就 NACK/冲突/读错 | [D1 接口组合后的隐藏约束](topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L44 [unknown] [s.md) | F06/F28/F29、module-integration §13 |
| 晶体不起振/偶发不起振/频偏/抖动 | [D2 时钟系统完整检查](topics/d2-clock-system-checklist.md) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok)
- L45 [unknown] [clock-system-checklist.md) | MCU-05/06、F05 |
| 板内正常，接长线/外设/热插拔就坏 | [D3 连接器与板外通信](topics/d3-off-board-interfaces.md) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok)
- L46 [unknown] [rd-interfaces.md) | IF-06/07/08/11、F07/F08 |
| 模组能用，装壳后距离/灵敏度下降 | [D4 无线性能与整机环境](topics/d4-wireless-integration.md) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok)
- L47 [unknown] [on.md) | F18、RF-01/02/04、KDB 996369 D04 |
| 继电器/电磁阀/电机关断时炸管、触点烧 | [E1 感性负载与能量去向](topics/e1-inductive-load-energy-path.md) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok)
- L48 [unknown] [oad-energy-path.md) | DRV-03/05、F14 |
| MOSFET 发热/误导通/低栅压不够 | [E2 MOS 栅极驱动与异常状态](topics/e2-gate-drive-and-false-turn-on.md) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok)
- L49 [unknown] [ve-and-false-turn-on.md) | DRV-01/02/04/05、F13 |
| 板在壳里过热、降额后仍不够 | [E3 热设计与机械环境](topics/e3-thermal-mechanical-environment.md) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok)
- L50 [unknown] [ronment.md) | thermal/topic、thermal/cases |
| 连接器/端子/焊点发热、长期接触不良 | [E4 连接与长期可靠性](topics/e4-connector-long-term-reliability.md) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok)
- L60 [unknown] [、热路径、连接器 | 专题 §4 + pcb-placement/routing-details |
| 评审 | 先问“结论类型”，再给证据 | [审图练习](exercises/README.md) → `references/engineering-deepdives/exercises/README.md` (ok)
- L68 [unknown] [. 按器件/领域找

| 领域 | 专题 | 开源案例 |
|---|---|---|
| MCU/开发板 | B2、D1、D2 | [MCU 与开发板](casebook/mcu-dev-boards.md) → `references/engineering-deepdives/casebook/mcu-dev-boards.md` (ok)
- L69 [unknown] [| [MCU 与开发板](casebook/mcu-dev-boards.md) |
| 低功耗无线/电池 | B2、B3、B4、D4 | [低功耗无线/电池](casebook/low-power-wireless-battery.md) → `references/engineering-deepdives/casebook/low-power-wireless-battery.md` (ok)
- L70 [unknown] [(casebook/low-power-wireless-battery.md) |
| 电机/功率/工业 | B4、E1、E2、E3 | [电机/功率/工业](casebook/motor-power-industrial.md) → `references/engineering-deepdives/casebook/motor-power-industrial.md` (ok)
- L71 [unknown] [机/功率/工业](casebook/motor-power-industrial.md) |
| 音频/精密模拟 | C1、C2、C3 | [音频/模拟/精密](casebook/audio-analog-precision.md) → `references/engineering-deepdives/casebook/audio-analog-precision.md` (ok)
- L72 [unknown] [(casebook/audio-analog-precision.md) |
| 高速/RF/FPGA | C2、D2、D3、D4 | [高速/RF/FPGA](casebook/high-speed-rf-fpga.md) → `references/engineering-deepdives/casebook/high-speed-rf-fpga.md` (ok)
- L73 [unknown] [[高速/RF/FPGA](casebook/high-speed-rf-fpga.md) |
| HMI/连接器/热 | E3、E4 | [HMI/连接器/热](casebook/hmi-connectors-thermal.md) → `references/engineering-deepdives/casebook/hmi-connectors-thermal.md` (ok)
- L127 [external_reference] [样机/EMC/安规测试的内容，保持 `未执行`。
- 开源项目的许可未明确时，只做阅读分析，不复制图纸/文件。

历史试答原始记录单独保存在[仓库证据目录](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/README.md) → `https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/README.md` (external)

### `references/engineering-deepdives/action-map.md`

- 标题：经验到行动：24 条映射
- 行/字符/字节：39 / 3553 / 7915
- SHA-256：`fac074d2a5072dc81fcd7ee3ea0b04f9b1e06a1496be0be028f7031c89daeb7d`

### `references/engineering-deepdives/casebook/audio-analog-precision.md`

- 标题：音频、模拟与精密电源组案例集（OSHW-18 ~ OSHW-21）
- 行/字符/字节：214 / 24516 / 42837
- SHA-256：`a37ce86849b298519216f7ebd27f292ddd683f540a9b0fb3ded3ee4b06c585d8`

- L5 [unknown] [# 音频、模拟与精密电源组案例集（OSHW-18 ~ OSHW-21）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口) → `references/engineering-deepdives/casebook/audio-analog-precision.md` (ok) #本组覆盖缺口 ok
- L8 [unknown] [HW-18 ~ OSHW-21）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口)


**编号说明**：编号与 [sources.md](../../sources.md) → `references/sources.md` (ok)

### `references/engineering-deepdives/casebook/high-speed-rf-fpga.md`

- 标题：高速/RF/FPGA 开源硬件案例条目
- 行/字符/字节：275 / 22823 / 38471
- SHA-256：`3725be6643bce1f92bee7ac980a73d939d96a5823cb0426075036719e9932df6`

- L5 [unknown] [# 高速/RF/FPGA 开源硬件案例条目

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口) → `references/engineering-deepdives/casebook/high-speed-rf-fpga.md` (ok) #本组覆盖缺口 ok
- L12 [unknown] [`、`images/...` 是本地核查快照路径，不随仓库分发；复查时按项目名 + 仓库 + 提交定位。

**编号说明**：编号与 [sources.md](../../sources.md) → `references/sources.md` (ok)

### `references/engineering-deepdives/casebook/hmi-connectors-thermal.md`

- 标题：HMI、连接器与电源组案例集（OSHW-12、OSHW-25）
- 行/字符/字节：122 / 17648 / 28181
- SHA-256：`474e5c6f93df96094a019e8e2aa0f2d6f44fc2866a2b1dcde7682bf540806312`

- L5 [unknown] [# HMI、连接器与电源组案例集（OSHW-12、OSHW-25）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口) → `references/engineering-deepdives/casebook/hmi-connectors-thermal.md` (ok) #本组覆盖缺口 ok
- L8 [unknown] [OSHW-12、OSHW-25）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口)


**编号说明**：编号与 [sources.md](../../sources.md) → `references/sources.md` (ok)

### `references/engineering-deepdives/casebook/index.md`

- 标题：开源硬件案例库：25 个项目
- 行/字符/字节：70 / 4496 / 7051
- SHA-256：`c68f5308b532a878cdf7f93edcbe407673f774f2298eab2b47303f7a1718ebf8`

- L11 [unknown] [覆盖范围

| 领域 | 项目数 | 案例文件 |
|---|---:|---|
| MCU 与开发板 | 6 | [mcu-dev-boards.md](mcu-dev-boards.md) → `references/engineering-deepdives/casebook/mcu-dev-boards.md` (ok)
- L12 [unknown] [rds.md](mcu-dev-boards.md) |
| 低功耗无线、电池与便携 | 5 | [low-power-wireless-battery.md](low-power-wireless-battery.md) → `references/engineering-deepdives/casebook/low-power-wireless-battery.md` (ok)
- L13 [unknown] [(low-power-wireless-battery.md) |
| 电机、功率与工业控制 | 5 | [motor-power-industrial.md](motor-power-industrial.md) → `references/engineering-deepdives/casebook/motor-power-industrial.md` (ok)
- L14 [unknown] [.md](motor-power-industrial.md) |
| 音频、精密模拟与测量 | 4 | [audio-analog-precision.md](audio-analog-precision.md) → `references/engineering-deepdives/casebook/audio-analog-precision.md` (ok)
- L15 [unknown] [.md](audio-analog-precision.md) |
| 高速接口、RF 与 FPGA | 3 | [high-speed-rf-fpga.md](high-speed-rf-fpga.md) → `references/engineering-deepdives/casebook/high-speed-rf-fpga.md` (ok)
- L16 [unknown] [-fpga.md](high-speed-rf-fpga.md) |
| HMI、连接器与热 | 2 | [hmi-connectors-thermal.md](hmi-connectors-thermal.md) → `references/engineering-deepdives/casebook/hmi-connectors-thermal.md` (ok)

### `references/engineering-deepdives/casebook/low-power-wireless-battery.md`

- 标题：低功耗无线/电池类开源硬件案例集（OSHW-07…11）
- 行/字符/字节：273 / 28516 / 47811
- SHA-256：`028ac8bb45c9c2c4a3b783f7da59f2727d9d932e89a119c8f2ea0da825964d13`

- L5 [unknown] [# 低功耗无线/电池类开源硬件案例集（OSHW-07…11）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口) → `references/engineering-deepdives/casebook/low-power-wireless-battery.md` (ok) #本组覆盖缺口 ok

### `references/engineering-deepdives/casebook/mcu-dev-boards.md`

- 标题：MCU/开发板开源硬件案例集（OSHW-01…06）
- 行/字符/字节：291 / 21947 / 37330
- SHA-256：`cae6e8ded0c7982c2082e4a44a3d353a91347c36e6d479083655b7ad8f8f7e4c`

- L5 [unknown] [# MCU/开发板开源硬件案例集（OSHW-01…06）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口) → `references/engineering-deepdives/casebook/mcu-dev-boards.md` (ok) #本组覆盖缺口 ok

### `references/engineering-deepdives/casebook/motor-power-industrial.md`

- 标题：电机、功率与工业控制组案例集（OSHW-13 ~ OSHW-17）
- 行/字符/字节：229 / 24285 / 42177
- SHA-256：`7bdc26a6f2383654ea8a060d3932006a042061efc45f642d68dc73f74e35177b`

- L5 [unknown] [# 电机、功率与工业控制组案例集（OSHW-13 ~ OSHW-17）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口) → `references/engineering-deepdives/casebook/motor-power-industrial.md` (ok) #本组覆盖缺口 ok
- L8 [unknown] [HW-13 ~ OSHW-17）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口)


**编号说明**：编号与 [sources.md](../../sources.md) → `references/sources.md` (ok)

### `references/engineering-deepdives/exercises/README.md`

- 标题：审图练习使用说明
- 行/字符/字节：48 / 1983 / 3073
- SHA-256：`7100b31b3604d5d06b9dc6da827058d6a62b7cd571160af877e0eb683a1e21ce`

- L3 [unknown] [# 审图练习使用说明

独立试答使用[无类型提示输入](blind-prompts.md) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok)
- L3 [external_reference] [练习使用说明

独立试答使用[无类型提示输入](blind-prompts.md)；带题型的学习版不用于盲判评估。历史试验的输入泄漏与旧评分限制见[试验说明](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/README.md) → `https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/README.md` (external)
- L8 [background] [ 对成对案例。目标不是“找错越多越好”，而是学会区分：明确错误、条件风险、有意取舍、看似异常实际合理、信息不足。
>
> 题目在 [exercises.md](exercises.md) → `references/engineering-deepdives/exercises/exercises.md` (ok)
- L8 [background] [意取舍、看似异常实际合理、信息不足。
>
> 题目在 [exercises.md](exercises.md)，成对案例在 [paired-cases.md](paired-cases.md) → `references/engineering-deepdives/exercises/paired-cases.md` (ok)
- L8 [background] [ses.md](exercises.md)，成对案例在 [paired-cases.md](paired-cases.md)，参考答案在 [answers.md](answers.md) → `references/engineering-deepdives/exercises/answers.md` (ok)
- L30 [external_reference] [写，基于本轮专题与来源）。
- 独立 Agent 答案文件隔离试答：已运行（2 名 Agent、20 题）；原始回答见 [trial/responses.md](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/responses.md) → `https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/responses.md` (external)
- L30 [external_reference] [ain/docs/evidence/deepdives-2026-10-22/responses.md)，评分与歧义见 [trial/evaluation.md](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/evaluation.md) → `https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/evaluation.md` (external)
- L39 [unknown] [
每题背后的机制在对应专题展开：

| 题 | 专题 |
|---|---|
| E01/E03/E06/E07/E17/E18 | [D1 接口组合](../topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L40 [unknown] [](../topics/d1-interface-combination-constraints.md) |
| E02/E05/E10 | [E1 感性负载](../topics/e1-inductive-load-energy-path.md) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok)
- L40 [unknown] [
| E02/E05/E10 | [E1 感性负载](../topics/e1-inductive-load-energy-path.md)、[E2 栅极驱动](../topics/e2-gate-drive-and-false-turn-on.md) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok)
- L41 [unknown] [2 栅极驱动](../topics/e2-gate-drive-and-false-turn-on.md) |
| E04/E09/E20 | [C1 误差链](../topics/c1-sensor-to-adc-error-chain.md) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok)
- L41 [unknown] [d) |
| E04/E09/E20 | [C1 误差链](../topics/c1-sensor-to-adc-error-chain.md)、[B3 充电](../topics/b3-charger-load-and-gauge.md) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok)
- L42 [unknown] [c-error-chain.md)、[B3 充电](../topics/b3-charger-load-and-gauge.md) |
| E08 | [D1](../topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L43 [unknown] [08 | [D1](../topics/d1-interface-combination-constraints.md) |
| E11 | [D3 板外接口](../topics/d3-off-board-interfaces.md) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok)
- L44 [unknown] [| E11 | [D3 板外接口](../topics/d3-off-board-interfaces.md) |
| E12/E13 | [C2 接地/屏蔽](../topics/c2-grounding-shielding-common-mode.md) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok)
- L45 [unknown] [E13 | [C2 接地/屏蔽](../topics/c2-grounding-shielding-common-mode.md) |
| E14 | [D1](../topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L46 [unknown] [14 | [D1](../topics/d1-interface-combination-constraints.md) |
| E15 | [B1 电源路径](../topics/b1-power-path-and-source-switching.md) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok)
- L47 [unknown] [[B1 电源路径](../topics/b1-power-path-and-source-switching.md) |
| E16/E19 | [D2 时钟](../topics/d2-clock-system-checklist.md) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok)

### `references/engineering-deepdives/exercises/answers.md`

- 标题：工程审图练习：参考答案与判断依据
- 行/字符/字节：276 / 8922 / 18065
- SHA-256：`51e56d8d4200e5d356c9adb9c29166c498b85f0e34a8a91254645895cde6853c`

- L5 [unknown] [# 工程审图练习：参考答案与判断依据

## 内容导航

- [E01 I²C 上拉接到 5 V](#e01-i²c-上拉接到-5-v) → `references/engineering-deepdives/exercises/answers.md` (ok) #e01-i²c-上拉接到-5-v ok
- L6 [unknown] [

## 内容导航

- [E01 I²C 上拉接到 5 V](#e01-i²c-上拉接到-5-v)
- [E02 24 V 高边 P-MOS 的栅极](#e02-24-v-高边-p-mos-的栅极) → `references/engineering-deepdives/exercises/answers.md` (ok) #e02-24-v-高边-p-mos-的栅极 ok
- L7 [unknown] [v)
- [E02 24 V 高边 P-MOS 的栅极](#e02-24-v-高边-p-mos-的栅极)
- [E03 USB-C sink 的 CC 电阻](#e03-usb-c-sink-的-cc-电阻) → `references/engineering-deepdives/exercises/answers.md` (ok) #e03-usb-c-sink-的-cc-电阻 ok
- L8 [unknown] [ [E03 USB-C sink 的 CC 电阻](#e03-usb-c-sink-的-cc-电阻)
- [E04 10 V 传感器直接进 3.3 V ADC](#e04-10-v-传感器直接进-33-v-adc) → `references/engineering-deepdives/exercises/answers.md` (ok) #e04-10-v-传感器直接进-33-v-adc ok
- L9 [unknown] [阻)
- [E04 10 V 传感器直接进 3.3 V ADC](#e04-10-v-传感器直接进-33-v-adc)
- [E05 继电器线圈没有续流路径](#e05-继电器线圈没有续流路径) → `references/engineering-deepdives/exercises/answers.md` (ok) #e05-继电器线圈没有续流路径 ok
- L10 [unknown] [0-v-传感器直接进-33-v-adc)
- [E05 继电器线圈没有续流路径](#e05-继电器线圈没有续流路径)
- [E06 两个同地址 I²C 器件](#e06-两个同地址-i²c-器件) → `references/engineering-deepdives/exercises/answers.md` (ok) #e06-两个同地址-i²c-器件 ok
- L11 [unknown] [线圈没有续流路径)
- [E06 两个同地址 I²C 器件](#e06-两个同地址-i²c-器件)
- [E07 10 kΩ I²C 上拉在两种条件下的结论](#e07-10-kω-i²c-上拉在两种条件下的结论) → `references/engineering-deepdives/exercises/answers.md` (ok) #e07-10-kω-i²c-上拉在两种条件下的结论 ok
- L12 [unknown] [Ω I²C 上拉在两种条件下的结论](#e07-10-kω-i²c-上拉在两种条件下的结论)
- [E08 3.3 V GPIO 驱动 5 V CMOS 输入](#e08-33-v-gpio-驱动-5-v-cmos-输入) → `references/engineering-deepdives/exercises/answers.md` (ok) #e08-33-v-gpio-驱动-5-v-cmos-输入 ok
- L13 [unknown] [3.3 V GPIO 驱动 5 V CMOS 输入](#e08-33-v-gpio-驱动-5-v-cmos-输入)
- [E09 SOT-23 LDO 的结温](#e09-sot-23-ldo-的结温) → `references/engineering-deepdives/exercises/answers.md` (ok) #e09-sot-23-ldo-的结温 ok
- L14 [unknown] [输入)
- [E09 SOT-23 LDO 的结温](#e09-sot-23-ldo-的结温)
- [E10 30 V MOSFET 用在 24 V 电机上](#e10-30-v-mosfet-用在-24-v-电机上) → `references/engineering-deepdives/exercises/answers.md` (ok) #e10-30-v-mosfet-用在-24-v-电机上 ok
- L15 [unknown] [V MOSFET 用在 24 V 电机上](#e10-30-v-mosfet-用在-24-v-电机上)
- [E11 RS-485 上的 100 pF TVS](#e11-rs-485-上的-100-pf-tvs) → `references/engineering-deepdives/exercises/answers.md` (ok) #e11-rs-485-上的-100-pf-tvs ok
- L16 [unknown] [
- [E11 RS-485 上的 100 pF TVS](#e11-rs-485-上的-100-pf-tvs)
- [E12 分割 AGND / DGND](#e12-分割-agnd--dgnd) → `references/engineering-deepdives/exercises/answers.md` (ok) #e12-分割-agnd--dgnd ok
- L17 [unknown] [85-上的-100-pf-tvs)
- [E12 分割 AGND / DGND](#e12-分割-agnd--dgnd)
- [E13 两颗地之间的 0 Ω](#e13-两颗地之间的-0-ω) → `references/engineering-deepdives/exercises/answers.md` (ok) #e13-两颗地之间的-0-ω ok
- L18 [unknown] [](#e12-分割-agnd--dgnd)
- [E13 两颗地之间的 0 Ω](#e13-两颗地之间的-0-ω)
- [E14 SPI 时钟串联 22 Ω](#e14-spi-时钟串联-22-ω) → `references/engineering-deepdives/exercises/answers.md` (ok) #e14-spi-时钟串联-22-ω ok
- L19 [unknown] [e13-两颗地之间的-0-ω)
- [E14 SPI 时钟串联 22 Ω](#e14-spi-时钟串联-22-ω)
- [E15 USB VBUS 上的磁珠](#e15-usb-vbus-上的磁珠) → `references/engineering-deepdives/exercises/answers.md` (ok) #e15-usb-vbus-上的磁珠 ok
- L20 [unknown] [4-spi-时钟串联-22-ω)
- [E15 USB VBUS 上的磁珠](#e15-usb-vbus-上的磁珠)
- [E16 晶体旁边的 100 nF](#e16-晶体旁边的-100-nf) → `references/engineering-deepdives/exercises/answers.md` (ok) #e16-晶体旁边的-100-nf ok
- L21 [unknown] [e15-usb-vbus-上的磁珠)
- [E16 晶体旁边的 100 nF](#e16-晶体旁边的-100-nf)
- [E17 SPI 片选没有外部上拉](#e17-spi-片选没有外部上拉) → `references/engineering-deepdives/exercises/answers.md` (ok) #e17-spi-片选没有外部上拉 ok
- L22 [unknown] [e16-晶体旁边的-100-nf)
- [E17 SPI 片选没有外部上拉](#e17-spi-片选没有外部上拉)
- [E18 只有主控板装 I²C 上拉](#e18-只有主控板装-i²c-上拉) → `references/engineering-deepdives/exercises/answers.md` (ok) #e18-只有主控板装-i²c-上拉 ok
- L23 [unknown] [pi-片选没有外部上拉)
- [E18 只有主控板装 I²C 上拉](#e18-只有主控板装-i²c-上拉)
- [E19 8 MHz 晶体没有外部负载电容](#e19-8-mhz-晶体没有外部负载电容) → `references/engineering-deepdives/exercises/answers.md` (ok) #e19-8-mhz-晶体没有外部负载电容 ok
- L24 [unknown] [i²c-上拉)
- [E19 8 MHz 晶体没有外部负载电容](#e19-8-mhz-晶体没有外部负载电容)
- [E20 LDO 输出只有 100 nF](#e20-ldo-输出只有-100-nf) → `references/engineering-deepdives/exercises/answers.md` (ok) #e20-ldo-输出只有-100-nf ok
- L25 [unknown] [](#e19-8-mhz-晶体没有外部负载电容)
- [E20 LDO 输出只有 100 nF](#e20-ldo-输出只有-100-nf)
- [评分建议](#评分建议) → `references/engineering-deepdives/exercises/answers.md` (ok) #评分建议 ok
- L58 [external_reference] [这不证明设计合规。

**行动/待补：** 两个CC分别配置适用Rd，核对控制器、方向、保护及电流广告；PD与VBUS保护另核。来源：[TI SSZT842](https://www.ti.com/document-viewer/lit/html/SSZT842/GUID-9549F798-DB33-4CAC-992E-D779B5C09E31) → `https://www.ti.com/document-viewer/lit/html/SSZT842/GUID-9549F798-DB33-4CAC-992E-D779B5C09E31` (external)

### `references/engineering-deepdives/exercises/blind-prompts.md`

- 标题：工程审图独立试答输入（未运行）
- 行/字符/字节：326 / 6488 / 11065
- SHA-256：`1a082b2a748488f750cc27838cb2d1f25ff8cb1a8a8b9031a0e7582f58b8da06`

- L5 [unknown] [# 工程审图独立试答输入（未运行）

## 内容导航

- [E08 3.3 V GPIO 驱动 5 V CMOS 输入](#e08-33-v-gpio-驱动-5-v-cmos-输入) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e08-33-v-gpio-驱动-5-v-cmos-输入 ok
- L6 [unknown] [V GPIO 驱动 5 V CMOS 输入](#e08-33-v-gpio-驱动-5-v-cmos-输入)
- [E03 USB-C sink 的 CC 电阻](#e03-usb-c-sink-的-cc-电阻) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e03-usb-c-sink-的-cc-电阻 ok
- L7 [unknown] [os-输入)
- [E03 USB-C sink 的 CC 电阻](#e03-usb-c-sink-的-cc-电阻)
- [E16 晶体旁边的 100 nF](#e16-晶体旁边的-100-nf) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e16-晶体旁边的-100-nf ok
- L8 [unknown] [k-的-cc-电阻)
- [E16 晶体旁边的 100 nF](#e16-晶体旁边的-100-nf)
- [E11 RS-485 上的 100 pF TVS](#e11-rs-485-上的-100-pf-tvs) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e11-rs-485-上的-100-pf-tvs ok
- L9 [unknown] [
- [E11 RS-485 上的 100 pF TVS](#e11-rs-485-上的-100-pf-tvs)
- [E20 LDO 输出只有 100 nF](#e20-ldo-输出只有-100-nf) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e20-ldo-输出只有-100-nf ok
- L10 [unknown] [的-100-pf-tvs)
- [E20 LDO 输出只有 100 nF](#e20-ldo-输出只有-100-nf)
- [E05 继电器线圈没有续流路径](#e05-继电器线圈没有续流路径) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e05-继电器线圈没有续流路径 ok
- L11 [unknown] [20-ldo-输出只有-100-nf)
- [E05 继电器线圈没有续流路径](#e05-继电器线圈没有续流路径)
- [E14 SPI 时钟串联 22 Ω](#e14-spi-时钟串联-22-ω) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e14-spi-时钟串联-22-ω ok
- L12 [unknown] [e05-继电器线圈没有续流路径)
- [E14 SPI 时钟串联 22 Ω](#e14-spi-时钟串联-22-ω)
- [E01 I²C 上拉接到 5 V](#e01-i²c-上拉接到-5-v) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e01-i²c-上拉接到-5-v ok
- L13 [unknown] [14-spi-时钟串联-22-ω)
- [E01 I²C 上拉接到 5 V](#e01-i²c-上拉接到-5-v)
- [E18 只有主控板装 I²C 上拉](#e18-只有主控板装-i²c-上拉) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e18-只有主控板装-i²c-上拉 ok
- L14 [unknown] [01-i²c-上拉接到-5-v)
- [E18 只有主控板装 I²C 上拉](#e18-只有主控板装-i²c-上拉)
- [E06 两个同地址 I²C 器件](#e06-两个同地址-i²c-器件) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e06-两个同地址-i²c-器件 ok
- L15 [unknown] [8-只有主控板装-i²c-上拉)
- [E06 两个同地址 I²C 器件](#e06-两个同地址-i²c-器件)
- [E12 分割 AGND / DGND](#e12-分割-agnd--dgnd) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e12-分割-agnd--dgnd ok
- L16 [unknown] [两个同地址-i²c-器件)
- [E12 分割 AGND / DGND](#e12-分割-agnd--dgnd)
- [E09 SOT-23 LDO 的结温](#e09-sot-23-ldo-的结温) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e09-sot-23-ldo-的结温 ok
- L17 [unknown] [dgnd)
- [E09 SOT-23 LDO 的结温](#e09-sot-23-ldo-的结温)
- [E04 10 V 传感器直接进 3.3 V ADC](#e04-10-v-传感器直接进-33-v-adc) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e04-10-v-传感器直接进-33-v-adc ok
- L18 [unknown] [)
- [E04 10 V 传感器直接进 3.3 V ADC](#e04-10-v-传感器直接进-33-v-adc)
- [E17 SPI 片选没有外部上拉](#e17-spi-片选没有外部上拉) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e17-spi-片选没有外部上拉 ok
- L19 [unknown] [-v-adc)
- [E17 SPI 片选没有外部上拉](#e17-spi-片选没有外部上拉)
- [E10 30 V MOSFET 用在 24 V 电机上](#e10-30-v-mosfet-用在-24-v-电机上) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e10-30-v-mosfet-用在-24-v-电机上 ok
- L20 [unknown] [30 V MOSFET 用在 24 V 电机上](#e10-30-v-mosfet-用在-24-v-电机上)
- [E02 24 V 高边 P-MOS 的栅极](#e02-24-v-高边-p-mos-的栅极) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e02-24-v-高边-p-mos-的栅极 ok
- L21 [unknown] [-v-电机上)
- [E02 24 V 高边 P-MOS 的栅极](#e02-24-v-高边-p-mos-的栅极)
- [E15 USB VBUS 上的磁珠](#e15-usb-vbus-上的磁珠) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e15-usb-vbus-上的磁珠 ok
- L22 [unknown] [os-的栅极)
- [E15 USB VBUS 上的磁珠](#e15-usb-vbus-上的磁珠)
- [E07 10 kΩ I²C 上拉在两种条件下的结论](#e07-10-kω-i²c-上拉在两种条件下的结论) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e07-10-kω-i²c-上拉在两种条件下的结论 ok
- L23 [unknown] [[E07 10 kΩ I²C 上拉在两种条件下的结论](#e07-10-kω-i²c-上拉在两种条件下的结论)
- [E19 8 MHz 晶体没有外部负载电容](#e19-8-mhz-晶体没有外部负载电容) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e19-8-mhz-晶体没有外部负载电容 ok
- L24 [unknown] [上拉在两种条件下的结论)
- [E19 8 MHz 晶体没有外部负载电容](#e19-8-mhz-晶体没有外部负载电容)
- [E13 两颗地之间的 0 Ω](#e13-两颗地之间的-0-ω) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok) #e13-两颗地之间的-0-ω ok

### `references/engineering-deepdives/exercises/exercises.md`

- 标题：工程审图练习（20 题）
- 行/字符/字节：390 / 7520 / 13179
- SHA-256：`0bb52567930ebcede481c2ddf1e5cc10e34dd3d108710808216da11ad379fa19`

- L5 [unknown] [# 工程审图练习（20 题）

## 内容导航

- [题型分布](#题型分布) → `references/engineering-deepdives/exercises/exercises.md` (ok) #题型分布 ok
- L6 [unknown] [# 工程审图练习（20 题）

## 内容导航

- [题型分布](#题型分布)
- [E01 I²C 上拉接到 5 V](#e01-i²c-上拉接到-5-v) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e01-i²c-上拉接到-5-v ok
- L7 [unknown] [[题型分布](#题型分布)
- [E01 I²C 上拉接到 5 V](#e01-i²c-上拉接到-5-v)
- [E02 24 V 高边 P-MOS 的栅极](#e02-24-v-高边-p-mos-的栅极) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e02-24-v-高边-p-mos-的栅极 ok
- L8 [unknown] [v)
- [E02 24 V 高边 P-MOS 的栅极](#e02-24-v-高边-p-mos-的栅极)
- [E03 USB-C sink 的 CC 电阻](#e03-usb-c-sink-的-cc-电阻) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e03-usb-c-sink-的-cc-电阻 ok
- L9 [unknown] [ [E03 USB-C sink 的 CC 电阻](#e03-usb-c-sink-的-cc-电阻)
- [E04 10 V 传感器直接进 3.3 V ADC](#e04-10-v-传感器直接进-33-v-adc) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e04-10-v-传感器直接进-33-v-adc ok
- L10 [unknown] [阻)
- [E04 10 V 传感器直接进 3.3 V ADC](#e04-10-v-传感器直接进-33-v-adc)
- [E05 继电器线圈没有续流路径](#e05-继电器线圈没有续流路径) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e05-继电器线圈没有续流路径 ok
- L11 [unknown] [0-v-传感器直接进-33-v-adc)
- [E05 继电器线圈没有续流路径](#e05-继电器线圈没有续流路径)
- [E06 两个同地址 I²C 器件](#e06-两个同地址-i²c-器件) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e06-两个同地址-i²c-器件 ok
- L12 [unknown] [线圈没有续流路径)
- [E06 两个同地址 I²C 器件](#e06-两个同地址-i²c-器件)
- [E07 10 kΩ I²C 上拉在两种条件下的结论](#e07-10-kω-i²c-上拉在两种条件下的结论) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e07-10-kω-i²c-上拉在两种条件下的结论 ok
- L13 [unknown] [Ω I²C 上拉在两种条件下的结论](#e07-10-kω-i²c-上拉在两种条件下的结论)
- [E08 3.3 V GPIO 驱动 5 V CMOS 输入](#e08-33-v-gpio-驱动-5-v-cmos-输入) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e08-33-v-gpio-驱动-5-v-cmos-输入 ok
- L14 [unknown] [3.3 V GPIO 驱动 5 V CMOS 输入](#e08-33-v-gpio-驱动-5-v-cmos-输入)
- [E09 SOT-23 LDO 的结温](#e09-sot-23-ldo-的结温) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e09-sot-23-ldo-的结温 ok
- L15 [unknown] [输入)
- [E09 SOT-23 LDO 的结温](#e09-sot-23-ldo-的结温)
- [E10 30 V MOSFET 用在 24 V 电机上](#e10-30-v-mosfet-用在-24-v-电机上) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e10-30-v-mosfet-用在-24-v-电机上 ok
- L16 [unknown] [V MOSFET 用在 24 V 电机上](#e10-30-v-mosfet-用在-24-v-电机上)
- [E11 RS-485 上的 100 pF TVS](#e11-rs-485-上的-100-pf-tvs) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e11-rs-485-上的-100-pf-tvs ok
- L17 [unknown] [
- [E11 RS-485 上的 100 pF TVS](#e11-rs-485-上的-100-pf-tvs)
- [E12 分割 AGND / DGND](#e12-分割-agnd--dgnd) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e12-分割-agnd--dgnd ok
- L18 [unknown] [85-上的-100-pf-tvs)
- [E12 分割 AGND / DGND](#e12-分割-agnd--dgnd)
- [E13 两颗地之间的 0 Ω](#e13-两颗地之间的-0-ω) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e13-两颗地之间的-0-ω ok
- L19 [unknown] [](#e12-分割-agnd--dgnd)
- [E13 两颗地之间的 0 Ω](#e13-两颗地之间的-0-ω)
- [E14 SPI 时钟串联 22 Ω](#e14-spi-时钟串联-22-ω) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e14-spi-时钟串联-22-ω ok
- L20 [unknown] [e13-两颗地之间的-0-ω)
- [E14 SPI 时钟串联 22 Ω](#e14-spi-时钟串联-22-ω)
- [E15 USB VBUS 上的磁珠](#e15-usb-vbus-上的磁珠) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e15-usb-vbus-上的磁珠 ok
- L21 [unknown] [4-spi-时钟串联-22-ω)
- [E15 USB VBUS 上的磁珠](#e15-usb-vbus-上的磁珠)
- [E16 晶体旁边的 100 nF](#e16-晶体旁边的-100-nf) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e16-晶体旁边的-100-nf ok
- L22 [unknown] [e15-usb-vbus-上的磁珠)
- [E16 晶体旁边的 100 nF](#e16-晶体旁边的-100-nf)
- [E17 SPI 片选没有外部上拉](#e17-spi-片选没有外部上拉) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e17-spi-片选没有外部上拉 ok
- L23 [unknown] [e16-晶体旁边的-100-nf)
- [E17 SPI 片选没有外部上拉](#e17-spi-片选没有外部上拉)
- [E18 只有主控板装 I²C 上拉](#e18-只有主控板装-i²c-上拉) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e18-只有主控板装-i²c-上拉 ok
- L24 [unknown] [pi-片选没有外部上拉)
- [E18 只有主控板装 I²C 上拉](#e18-只有主控板装-i²c-上拉)
- [E19 8 MHz 晶体没有外部负载电容](#e19-8-mhz-晶体没有外部负载电容) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e19-8-mhz-晶体没有外部负载电容 ok
- L25 [unknown] [i²c-上拉)
- [E19 8 MHz 晶体没有外部负载电容](#e19-8-mhz-晶体没有外部负载电容)
- [E20 LDO 输出只有 100 nF](#e20-ldo-输出只有-100-nf) → `references/engineering-deepdives/exercises/exercises.md` (ok) #e20-ldo-输出只有-100-nf ok
- L26 [unknown] [](#e19-8-mhz-晶体没有外部负载电容)
- [E20 LDO 输出只有 100 nF](#e20-ldo-输出只有-100-nf)
- [使用建议](#使用建议) → `references/engineering-deepdives/exercises/exercises.md` (ok) #使用建议 ok
- L31 [background] [有意取舍 / 看似异常实际合理 / 信息不足”之间做区分，而不是见到不熟悉的画法就报缺陷。
>
> 本文件是带题型提示的学习版；独立试答应使用[无题型提示版](blind-prompts.md) → `references/engineering-deepdives/exercises/blind-prompts.md` (ok)
- L31 [background] [本文件是带题型提示的学习版；独立试答应使用[无题型提示版](blind-prompts.md)，不要把本文件作为题型盲判输入。参考答案在 [answers.md](answers.md) → `references/engineering-deepdives/exercises/answers.md` (ok)
- L386 [background] [需要查数据手册的哪几项？在什么条件下 100 nF 可能够用，什么条件下必须加大？

---

## 使用建议

1. 先独立作答，再读 [参考答案](answers.md) → `references/engineering-deepdives/exercises/answers.md` (ok)

### `references/engineering-deepdives/exercises/paired-cases.md`

- 标题：成对案例（8 对）
- 行/字符/字节：94 / 2644 / 5192
- SHA-256：`6456e5f02e94b59b6ca3abfe280a6faaaaf3e82cb1271fe5c7554383476c2933`

- L5 [background] [一拓扑/同一电流/同一接口”当成“同一结论”。
>
> 每对给：A 条件、B 条件、只改了什么、需要补什么、结论如何翻转。参考答案在 [answers.md](answers.md) → `references/engineering-deepdives/exercises/answers.md` (ok)

### `references/engineering-deepdives/sources.md`

- 标题：工程深潜来源与开源项目台账
- 行/字符/字节：88 / 9541 / 14703
- SHA-256：`a5b532e2e002a7451af501de7840af0b73457b24d310288ae15554e62d27d186`

- L9 [unknown] [-Sxx`、`MCU-Sxx`、`IF-Sxx`、`DRV-Sxx`、`RF-Sxx`、`MFG-Sxx`、`Gxx`、`P0x` 等编号继续在 [原始来源登记](../source-register.md) → `references/source-register.md` (ok)
- L9 [unknown] [`、`RF-Sxx`、`MFG-Sxx`、`Gxx`、`P0x` 等编号继续在 [原始来源登记](../source-register.md) 与 [工程经验库](../design-experience.md) → `references/design-experience.md` (ok)
- L81 [external_reference] [不复制图纸/文件；商用/再分发前必须单独核对许可。

## 合并复核补充来源与许可说明（2026-10-22）

- [CC BY-SA 3.0官方说明](https://creativecommons.org/licenses/by-sa/3.0/deed.en) → `https://creativecommons.org/licenses/by-sa/3.0/deed.en` (external)
- L82 [external_reference] [条件下复制/改编（包括商业用途）；本仓库选择不打包第三方图纸，不能表述为该许可禁止复制。每个实际文件仍按其自身许可与其他权利核对。
- [TI SSZT842](https://www.ti.com/document-viewer/lit/html/SSZT842/GUID-9549F798-DB33-4CAC-992E-D779B5C09E31) → `https://www.ti.com/document-viewer/lit/html/SSZT842/GUID-9549F798-DB33-4CAC-992E-D779B5C09E31` (external)
- L83 [external_reference] [798-DB33-4CAC-992E-D779B5C09E31)：A-to-C插头中的CC/Rp，支持E03修订。
- [TI SLLA337 Fig.1-2](https://www.ti.com/lit/pdf/slla337) → `https://www.ti.com/lit/pdf/slla337` (external)
- L84 [external_reference] [.ti.com/lit/pdf/slla337)：CAN总线本征共模，支持D3修订；实际包络按具体收发器保证值。
- [TI BQ25619 §7.3.5.1](https://www.ti.com/lit/ds/symlink/bq25619.pdf) → `https://www.ti.com/lit/ds/symlink/bq25619.pdf` (external)
- L85 [external_reference] [.ti.com/lit/ds/symlink/bq25619.pdf)：NVDC的SYS/BAT关系，支持B3修订。
- [TI TPS7A02 §7.3.2](https://www.ti.com/lit/ds/symlink/tps7a02.pdf) → `https://www.ti.com/lit/ds/symlink/tps7a02.pdf` (external)

### `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md`

- 标题：B1 多路供电与电源切换：2^n 组合、反灌路径与优先级
- 行/字符/字节：838 / 47347 / 81714
- SHA-256：`3a28ca6a41cb9621588f14dd97ea4bda35d056a426d38c50fba54fee5f84a711`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok) #10-来源与适用范围 ok
- L28 [unknown] [oldup、假上电和优先级抖动。**不适用：** USB PD 高压协商、>24 V 工业/汽车瞬态、隔离与安规、电池包内部保护设计；PD 见 [常用硬件 F3](../../common-hardware/f-input-protection.md) → `references/common-hardware/f-input-protection.md` (ok)
- L28 [unknown] [3](../../common-hardware/f-input-protection.md)（旧卡 PWR-12/13 只做 5 V），反接见 [PWR-09](../../design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L28 [unknown] [5 V），反接见 [PWR-09](../../design-cards/power/p09-reverse-polarity.md)，电池包见 [PWR-08](../../design-cards/power/p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L32 [unknown] [例。全文用【已核对原厂资料】【作者记录】【工程推断】【构造案例】【未执行】显式标注。
>
> **与现有内容的关系：** [PWR-05 多源供电与电源路径](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L40 [unknown] [有两个及以上电源入口（USB、DC 座、电池、调试器、备份电容） | 任一路有电时，电流可能从负载倒灌回另一路；只画“正常工作”一种方向必漏 | [PWR-05](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L40 [unknown] [另一路；只画“正常工作”一种方向必漏 | [PWR-05](../../design-cards/power/p05-power-mux.md)、[PWR-09](../../design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L41 [unknown] [
| 电池与系统同时在位，且系统负载可能大于输入限流 | 充电器进入 DPPM/supplement 后，电池可能在“充电命令”下实际放电 | [PWR-06](../../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L41 [unknown] [能在“充电命令”下实际放电 | [PWR-06](../../design-cards/power/p06-linear-charger.md)、[PWR-07](../../design-cards/power/p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L42 [background] [`T_VCC`/`VTref`，且目标可能由电池或外部电源供电 | `T_VCC` 是电平参考输入，不是电源输出；接错会把目标电压灌进调试器 | [MCU-07](../../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L43 [unknown] [-swd-jtag.md) |
| 适配器/电池热插拔，或线缆较长 | 线缆电感、输入电容和 TVS 的配合决定插拔瞬间的负压/振铃与浪涌 | [PWR-10](../../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L43 [unknown] [浪涌 | [PWR-10](../../design-cards/power/p10-hot-swap.md)、[module-integration §8.3](../../module-integration.md) → `references/module-integration.md` (ok)
- L44 [unknown] [
| 需要“拔掉主电源后系统保持 N ms” | holdup 时间由电容、负载和反向阻断共同决定；100 µF 通常只有几十到几百 µs | [PWR-14](../../design-cards/power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L151 [unknown] [压 | 5 V 轨 → VBUS 或 VBUS → 5 V 轨 | USB 2.0 设备不得向 VBUS 供电；[module-integration §8.2](../../module-integration.md) → `references/module-integration.md` (ok)
- L152 [unknown] [md) |
| 调试器 T_VCC | 目标 3.3 V 有电，调试器 T_VCC 接目标轨 | 目标 3.3 V → 调试器 T_VCC | [MCU-07](../../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L164 [unknown] [方案**，它只能撑住一次快速切换/瞬态。需要 10 ms 级 holdup 时，要么用 mF 级电容/超级电容，要么让电池/第二路源无缝接管；见 [PWR-14](../../design-cards/power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L232 [unknown] [。

### 2.9 调试器 T_VCC 是参考输入，但仍可能被反灌

【已核对原厂资料】ST UM2448 Rev 9 §11.5（经 [MCU-07](../../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L375 [unknown] [负极/USB 地不要在连接器处直接串在一起再穿过采样电阻。

### 4.3 热路径

【已核对原厂资料】[thermal/topic.md §2–§3](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L393 [unknown] [P` 的负压/振铃、TVS 电流、ORing 器件 `VDS`；不要用普通接地探头直接夹浮动/高压节点（见 [simulation-measurement §5](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L551 [unknown] [is = 3.3 × 0.06894 = 0.2275 V`。
- `VIN_fall = 4.349 V`。

**与简化式的差别：** [PWR-05](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L600 [unknown] [/300 mVpp 纹波 | 切换点、抖动、`ST` | 门限在预算内；无反复切换 |

测量按 [simulation-measurement §5–§6](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L696 [unknown] [主电源时，测 `T_VCC` 脚电流方向/大小；若目标→调试器，说明反灌。
4. 查所有上拉域；拔掉传感器/上拉，重复。

**证据：** [MCU-07](../../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L696 [unknown] [ag.md) 的 UM2448 §11.5 与 1 kΩ 反灌算例 `(3.3−0.7)/1k=2.6 mA`；[module-integration §8.2](../../module-integration.md) → `references/module-integration.md` (ok)
- L722 [unknown] [.8 mV 纹波（构造）；TPS2121 SLVSEA3F 第 7–8 页 `tSW/tFSW`、第 15–17 页 `VOUT,MIN` 公式；[PWR-05](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L749 [unknown] [-to-C、正反插、不同线缆；测 VBUS。
4. 查 BOM/装配图：`Rd` 是否 DNP；连接器 CC 是否被外壳短接。

**证据：** [F09](../../failures/f09-usbc-cc.md) → `references/failures/f09-usbc-cc.md` (ok)
- L749 [unknown] [、sink 电压窗）；TI TUSB320 SLLSEN9F（`RCC_D` 4.6/5.1/5.6 kΩ、DFP 80/180/330 µA）；[PWR-12](../../design-cards/power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L775 [unknown] [TC=25°C、`ILIM=min(ILIM, PLIM/VDS)`）；SLVAE57B §2.1（大 holdup 电容浪涌不得超过二极管最大电流）；[F14](../../failures/f14-relay-flyback.md) → `references/failures/f14-relay-flyback.md` (ok)
- L828 [unknown] [分压精度/ESR/浪涌未核对；开源设计不是正确性权威 |

### 10.2 相关现有内容（相对链接）

- 设计卡：[PWR-05 多源供电与电源路径](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L828 [unknown] [卡：[PWR-05 多源供电与电源路径](../../design-cards/power/p05-power-mux.md)、[PWR-06 单节锂电线性充电](../../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L828 [unknown] [锂电线性充电](../../design-cards/power/p06-linear-charger.md)、[PWR-07 开关充电与 Power Path](../../design-cards/power/p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L828 [unknown] [er Path](../../design-cards/power/p07-switching-charger.md)、[PWR-08 1S 电池保护与 BMS](../../design-cards/power/p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L828 [unknown] [8 1S 电池保护与 BMS](../../design-cards/power/p08-battery-protection.md)、[PWR-09 反接保护](../../design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L828 [unknown] [[PWR-09 反接保护](../../design-cards/power/p09-reverse-polarity.md)、[PWR-10 热插拔与浪涌限制](../../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L828 [unknown] [PWR-10 热插拔与浪涌限制](../../design-cards/power/p10-hot-swap.md)、[PWR-12 USB-C 5V Sink](../../design-cards/power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L828 [unknown] [B-C 5V Sink](../../design-cards/power/p12-usbc-sink.md)、[PWR-14 超级电容/RTC 备份/掉电保持](../../design-cards/power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L828 [unknown] [容/RTC 备份/掉电保持](../../design-cards/power/p14-supercap-backup.md)、[MCU-07 SWD/JTAG](../../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L829 [unknown] [7 SWD/JTAG](../../design-cards/mcu/m07-swd-jtag.md)。
- 故障：[F09 USB-C CC 电阻缺失/错误](../../failures/f09-usbc-cc.md) → `references/failures/f09-usbc-cc.md` (ok)
- L829 [unknown] [)。
- 故障：[F09 USB-C CC 电阻缺失/错误](../../failures/f09-usbc-cc.md)、[F14 继电器线圈无续流/释放慢](../../failures/f14-relay-flyback.md) → `references/failures/f14-relay-flyback.md` (ok)
- L830 [unknown] [](../../failures/f14-relay-flyback.md)。
- 组合/测量/热：[module-integration §8.2–§8.3](../../module-integration.md) → `references/module-integration.md` (ok)
- L830 [unknown] [ntegration §8.2–§8.3](../../module-integration.md)、[simulation-measurement §5–§6](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L830 [unknown] [tion-measurement §5–§6](../../simulation-measurement.md)、[thermal/topic.md §2–§3](../../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/engineering-deepdives/topics/b2-sleep-current-budget.md`

- 标题：B2 低功耗整机与睡眠电流预算
- 行/字符/字节：503 / 31927 / 56632
- SHA-256：`6a518487935642958fe0312dbac26f64f9ead805136f2d40c286dcb6e499e3bc`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok) #10-来源与适用范围 ok
- L30 [unknown] [ 为缺型号资料、不能给保证值的点。本稿没有做任何实物测量，也没有把模型输出当成实测。
>
> **与现有内容的关系：** 本文不重复 [PWR-01 LDO](../../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L30 [unknown] [* 本文不重复 [PWR-01 LDO](../../design-cards/power/p01-ldo.md) 的压差/热/电容窗口，不重复 [MCU-01](../../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L30 [unknown] [-ldo.md) 的压差/热/电容窗口，不重复 [MCU-01](../../design-cards/mcu/m01-bare-mcu.md)/[MCU-02](../../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L30 [unknown] [-mcu.md)/[MCU-02](../../design-cards/mcu/m02-module-mcu.md) 的逐脚最小系统，也不重复 [P01 项目](../../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L30 [unknown] [型。本文补的是“板级 µA 从哪里来、怎么在原理图上定位、怎么在电池端证明”。组合漏电案例见 [module-integration.md 案例 C11/C12](../../module-integration.md) → `references/module-integration.md` (ok)
- L70 [unknown] [off`。`k_temp`、`k_age`、`k_cutoff` 必须来自电池手册或实测；P01 用 0.8 是写明假设的工程值，不是保证值（[P01 §4.2](../../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L116 [unknown] [另一侧断电时，关断态漏电、`Ioff` 规格、OE 默认态都要查；电平转换器的 B 侧有电、A 侧无电时，可能经 A 侧 ESD 二极管反灌。见 [MCU-02](../../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L116 [unknown] [../../design-cards/mcu/m02-module-mcu.md) 的“反灌”异常状态和 [module-integration.md §8.2](../../module-integration.md) → `references/module-integration.md` (ok)
- L118 [unknown] [* C11 讲的是“主控板上拉给断电传感器板漏电，整机从 50 µA 变 1.05 mA”的组合案例（[module-integration.md 案例 C11](../../module-integration.md) → `references/module-integration.md` (ok)
- L123 [unknown] [），每条 **0.70 mA**（3.3 V/4.7 kΩ），两条 **1.40 mA**。这是“休眠电流突然变成 mA”的常见原因，见 [F06 I²C 上拉](../../failures/f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L131 [unknown] [SWDIO、JTDI、JNTRST 内部上拉，JTCK/SWCLK 内部下拉，不需要再加外部电阻（`[原厂 MCU-S01/AN4488]`，见 [MCU-01](../../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L148 [unknown] [02（`IQ 11 µA typ`，`[原厂 PWR-S09]`），在 25 µA 睡眠预算里给电源留 15 µA，这是明确的取舍（[P01 §3.3/§4.2](../../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L216 [unknown] [选；不要用 0402 焊盘当 2 A 测试点。
- **SC19 最小系统逐脚：** 每个 VDD 脚、EN、复位、调试脚都要有明确默认态；见 [MCU-01](../../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L216 [unknown] [D 脚、EN、复位、调试脚都要有明确默认态；见 [MCU-01](../../design-cards/mcu/m01-bare-mcu.md)/[MCU-02](../../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L218 [unknown] [低”作为删掉调试口的理由。
- **SC27 I²C 完整性：** `R7` 的 4.7 kΩ 上拉、总线电容、最弱灌电流、器件掉电钳位一起核对；见 [F06](../../failures/f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L225 [background] [= 3.3 µA`；如果是 100 kΩ，就是 **33 µA**，已经超过分压本身。`VDIV` 走线要短、远离开关节点和连接器脏区，按 [PL22 高阻节点](../../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L226 [unknown] [3`、`D1` 的电流回路要按实际路径放；`VBAT` 和 `GND` 的接触电阻、连接器额定、线束压降按峰值算，不按睡眠 µA 算。见 [PL15 保护靠边界](../../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L226 [unknown] [器额定、线束压降按峰值算，不按睡眠 µA 算。见 [PL15 保护靠边界](../../pcb-placement-details.md)、[PL16 散热路径](../../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L228 [unknown] [3`、LDO `U2` 的发热会抬高自身漏电和电池自放电；温度对 Iq/漏电的影响必须用高低温箱或热像仪确认。公式与热阻链见 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L240 [unknown] [5 µA | 戴维南 500 kΩ；SAR ADC 建立/漏电误差大；可能需要缓冲 | **2.1/1.85 µA** | 高源阻抗；见 [F22 ADC 建立](../../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L350 [unknown] [ADC 源阻抗从 50 kΩ 变成 `50 kΩ + Rds(on)`；开关关断漏电、GPIO 默认态、测量窗口内的建立时间都要重算。见 [F22 ADC 建立](../../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L373 [unknown] [波器，带宽至少覆盖脉冲边沿；DC 精度用 DMM/库仑计交叉验证。电流探头的 DC 漂移/饱和按 [simulation-measurement.md §8.3](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L383 [unknown] [- **BOM/装配：** DNP 不是 NC；调试座、LED、分压、传感器电源跳线的装/不装要形成变体，并与固件配置对应。见 [F19 BOM/CPL/DNP](../../failures/f19-bom-cpl-dnp.md) → `references/failures/f19-bom-cpl-dnp.md` (ok)
- L400 [unknown] [7 kΩ（设计文件）；分压 18.5 µA @3.7 V（计算）；C11 的 50 µA→1.05 mA 组合案例（[module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L414 [unknown] [ 平均值对比。
  4. 关掉射频/传感器/看门狗，逐项看脉冲是否消失。
- **证据：** [simulation-measurement.md §8.3](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L428 [unknown] [ 调试寄存器/低功耗调试位。
  4. 用 USB 隔离器或电池供电的调试器复测。
- **证据：** MCU-S07 的 T_VCC 定义；[MCU-01](../../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L428 [unknown] [U-01](../../design-cards/mcu/m01-bare-mcu.md) 的内部上/下拉；C12（[module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L442 [unknown] [O 定义与 `RDS(ON)` 换算；PWR-S10 的 UVP；P01 选 TPS63802 的理由（3.0 V 时纯 Buck/LDO 不够，[P01 §2](../../projects/p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L473 [unknown] [urden voltage、电流探头的 DC 精度/带宽、库仑计的分辨率都没有型号和校准记录；按 [simulation-measurement.md §8.3](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)

### `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md`

- 标题：B3 充电、系统负载与电量判断
- 行/字符/字节：639 / 45396 / 75758
- SHA-256：`ba4d9a9dd63b197248945286dfa1c43b446fb1df9c6c20fae4b85c3baddb655e`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` (ok) #10-来源与适用范围 ok
- L34 [unknown] [、不能给保证值的点。本稿没有做任何实物测量，也没有把数据手册典型值当成整板保证值。
>
> **与现有内容的关系：** 本文不重复 [PWR-06 线性充电](../../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L34 [unknown] [ 线性充电](../../design-cards/power/p06-linear-charger.md) 的 CC/CV 参数步骤、[PWR-07 开关充电](../../design-cards/power/p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L34 [unknown] [07 开关充电](../../design-cards/power/p07-switching-charger.md) 的功率级设计、[PWR-08 1S 保护](../../design-cards/power/p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L34 [unknown] [保护](../../design-cards/power/p08-battery-protection.md) 的门限表，也不重复 [B1 power path](./b1-power-path-and-source-switching.md) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok)
- L34 [unknown] [不重复 [B1 power path](./b1-power-path-and-source-switching.md) 的多源组合与反灌路径、[B2 睡眠预算](./b2-sleep-current-budget.md) → `references/engineering-deepdives/topics/b2-sleep-current-budget.md` (ok)
- L108 [external_reference] [系统电压时，SYS 跟随 BAT 并高出充电路径压降，不能设 SYS=3.8 V、BAT=4.2 V 却继续充电。参见 [TI BQ25619 §7.3.5.1](https://www.ti.com/lit/ds/symlink/bq25619.pdf) → `https://www.ti.com/lit/ds/symlink/bq25619.pdf` (external)
- L335 [unknown] [Q76952 的 300 µΩ 也在 pack 主路径。高边采样的共模/CMRR 要求比低边高，不能把低边电流采样卡直接套过来；见 [ANA-07 高侧电流采样](../../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L336 [unknown] [effective)` 核；不能把 datasheet 的 JEDEC 值当实际板。热阻链与 ΨJT/ΨJB 的用法见 [thermal/topic.md §2](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L340 [unknown] [ar 的 `D12` SMCJ70A 与 `D22` MURS360。连接器额定、线束压降、保险丝 I²t 要按峰值电流，不是按平均充电电流；见 [PWR-11](../../design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L356 [unknown] [性充电器。
- 多源 ORing、优先级 mux（TPS2121）与本文的“带充电器 power path”不是同一层；那部分取舍见 [PWR-05 多源供电](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L446 [unknown] [ 1.5 A/3 A 充电；Type-C 原生上限是 15 W（3 A@5 V），PD 不在本文来源内。CC 电阻缺失/错误的排查见 [F09 USB-C CC](../../failures/f09-usbc-cc.md) → `references/failures/f09-usbc-cc.md` (ok)
- L466 [unknown] [依据，不是喜好。
- `RθJA` 是 JEDEC 测试板值；实际板铜面积/层数/气流/外壳可让它差 2–4 倍（[thermal/topic.md §2.2](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L490 [unknown] [1 µA 就是 `1 µA × 50 kΩ = 50 mV`，是 100 mV 的一半。高阻分压的漏电/污染会把“电压法”再拉坏一截；见 [F22 ADC 建立](../../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L532 [unknown] [阻真的装、阻值正确；DNP 不是 NC；电池连接器 pin 序与 pack 一致；gauge 的 `BIN` 不被外壳短路。见 [F19 BOM/CPL/DNP](../../failures/f19-bom-cpl-dnp.md) → `references/failures/f19-bom-cpl-dnp.md` (ok)

### `references/engineering-deepdives/topics/b4-power-dynamics.md`

- 标题：B4 电源动态与负载瞬态
- 行/字符/字节：698 / 36008 / 63866
- SHA-256：`7558f960309279213d0ced09082f2ccd01738378d280c3fb6d67bebbb3e12265`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok) #10-来源与适用范围 ok
- L37 [unknown] [
> - `[未执行]` 没有做仿真、测量、EDA 回读或热测试。
>
> **与现有内容的关系：** 拓扑、参数步骤、逐脚核对见 [PWR-02 Buck](../../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L37 [unknown] [** 拓扑、参数步骤、逐脚核对见 [PWR-02 Buck](../../design-cards/power/p02-buck.md)、[PWR-10 热插拔](../../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L37 [unknown] [02-buck.md)、[PWR-10 热插拔](../../design-cards/power/p10-hot-swap.md)、[PWR-11 eFuse](../../design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L37 [unknown] [t-swap.md)、[PWR-11 eFuse](../../design-cards/power/p11-efuse.md)、[PWR-05 多源与电源路径](../../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L37 [unknown] [use.md)、[PWR-05 多源与电源路径](../../design-cards/power/p05-power-mux.md)、[PWR-06 线性充电](../../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L37 [unknown] [d)、[PWR-06 线性充电](../../design-cards/power/p06-linear-charger.md)；失效机理见 [F12 电感饱和](../../failures/f12-inductor-saturation.md) → `references/failures/f12-inductor-saturation.md` (ok)
- L37 [unknown] [.md)；失效机理见 [F12 电感饱和](../../failures/f12-inductor-saturation.md)、[F13 MOSFET SOA](../../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L37 [unknown] [r-saturation.md)、[F13 MOSFET SOA](../../failures/f13-mosfet-soa.md)；热与测量分别见 [热专题](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L37 [unknown] [](../../failures/f13-mosfet-soa.md)；热与测量分别见 [热专题](../../thermal/topic.md)、[仿真与测量](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L209 [background] [V；2 A 脉冲在 10 mΩ 共同地阻抗上产生 20 mV，约 25 LSB。`[推断]` 具体回流路径要按 PCB 叠层和连接器针序核对，参见 [跨模块组合](../../module-integration.md) → `references/module-integration.md` (ok)
- L218 [unknown] [来提高 ESR。

热专题给的是从功耗到结温的路径，本文只强调：动态算例必须用“最高环境温度 + 最坏器件参数”，不能用 25 °C 典型值。参见 [热专题](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L238 [unknown] [ 负载表有 `I_peak`、持续时间、重复率、哪些峰值会同时发生 | 只写“最大 2 A”，不写 burst/启动 | [module-integration](../../module-integration.md) → `references/module-integration.md` (ok)
- L241 [unknown] [u` 当 100 µF | PWR-S04 |
| 稳压器最大容性负载 | 手册的 `C_OUT` 范围/稳定窗口 | 无上限地并联大电容 | [PWR-01](../../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L242 [unknown] [md) |
| 限流/软启动/定时器 | `ILIM`、`T_START`、`T_TIMER`、`dv/dt` | 只查额定电流，不查启动 | [PWR-10](../../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L243 [unknown] [p.md) |
| 输入热插拔路径 | 连接器针序、precharge、TVS、保险、理想二极管 | 地针与电源针同时接触 | PWR-S11、[PWR-11](../../design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L244 [unknown] [| 100 µF 低 ESR + 100 nF/33 pF/10 pF，靠近 `VBAT_BB`/`VBAT_RF` | 只放一颗 10 µF | [RF-03](../../design-cards/wireless/w03-cellular.md) → `references/design-cards/wireless/w03-cellular.md` (ok)
- L245 [unknown] [eless/w03-cellular.md) |
| 电机续流/栅极 | 续流二极管方向、栅极电阻、下拉、默认态 | 续流二极管没有或反接 | [DRV-01](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L317 [unknown] [额定与温度 | 热专题 §3.4 |
| MOSFET | 导通/开关/雪崩/SOA | `Rds(on)` 随温度、SOA 脉冲、铜皮/散热器 | [F13](../../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L318 [unknown] [/failures/f13-mosfet-soa.md) |
| 电感 | 铜损/铁损/饱和 | `I_rms`、`ISAT`、DCR、温度降额 | [F12](../../failures/f12-inductor-saturation.md) → `references/failures/f12-inductor-saturation.md` (ok)
- L319 [unknown] [s/f12-inductor-saturation.md) |
| 连接器/保险丝 | 接触电阻/I²t | 额定降额、周围热源、插拔次数 | [PWR-11](../../design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L526 [background] [行]` 本稿没有运行 SPICE/行为模型；以上是计划。仿真必须用实际源阻抗与负载斜率，不能用理想电压源；通过标准要与第 1.3 节判据一致。参考 [仿真与测量](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L592 [unknown] [µF+0.5 Ω→30 V；47 µF 铝电解 ESR 0.44 Ω→25 V（G10 第 2–3 页）；PWR-S11 Eq.1–3 第 1–8 页；[F13](../../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L604 [unknown] [ART`；⑥ 查输入是否被拉跌 |
| 证据 | PWR-S04：输出电容有上下限；PWR-S11 Eq.3：`T_START` 随 C 增大；[PWR-01](../../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L604 [unknown] [-S11 Eq.3：`T_START` 随 C 增大；[PWR-01](../../design-cards/power/p01-ldo.md)、[PWR-10](../../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L678 [unknown] [on.md`、`failures/f13-mosfet-soa.md` | 电感饱和/SOA 排查结构 | 证据等级 B；无本次板级失效复现 |
| [热专题](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L678 [unknown] [` | 电感饱和/SOA 排查结构 | 证据等级 B；无本次板级失效复现 |
| [热专题](../../thermal/topic.md) / [仿真与测量](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L678 [unknown] [热专题](../../thermal/topic.md) / [仿真与测量](../../simulation-measurement.md) / [跨模块组合](../../module-integration.md) → `references/module-integration.md` (ok)

### `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md`

- 标题：C1 从传感器到 ADC 的误差链
- 行/字符/字节：642 / 35262 / 63214
- SHA-256：`0f2c185d830306240694ae82f9032efb24bc3798f6bc8111cad50063ea25cc27`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok) #10-来源与适用范围 ok
- L30 [unknown] [计量、音频、RF 采样、隔离放大器内部、纯比较器阈值检测。它们的判据是带宽、失真、相位、隔离耐压，不是本文的直流误差预算。ADC 建立时间的完整推导见 [F22](../../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L30 [unknown] [误差预算。ADC 建立时间的完整推导见 [F22](../../failures/f22-adc-settling.md)，基准的完整六项误差见 [ANA-05](../../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L30 [unknown] [md)，基准的完整六项误差见 [ANA-05](../../design-cards/analog/a05-vref.md)，低侧电流采样拓扑见 [ANA-06](../../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L34 [unknown] [设的假设值，不是某颗器件的保证值；`[未执行]` 本次没有做仿真、温循或实物测量。
>
> **与现有内容的关系：** 本文不重复 [ANA-01 电阻分压](../../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L34 [unknown] [关系：** 本文不重复 [ANA-01 电阻分压](../../design-cards/analog/a01-divider.md)、[ANA-03 差分放大](../../design-cards/analog/a03-diff-amp.md) → `references/design-cards/analog/a03-diff-amp.md` (ok)
- L34 [unknown] [.md)、[ANA-03 差分放大](../../design-cards/analog/a03-diff-amp.md)、[ANA-04 SAR ADC 驱动](../../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L34 [unknown] [d)、[ANA-04 SAR ADC 驱动](../../design-cards/analog/a04-adc-driver.md)、[ANA-05 电压基准](../../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L34 [unknown] [c-driver.md)、[ANA-05 电压基准](../../design-cards/analog/a05-vref.md)、[ANA-06 低侧电流采样](../../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L34 [unknown] [条可核对的误差链”，以及卡片刻意留给具体型号的那一层：漏电、建立、CMRR、比率测量、校准边界。测量总则见 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L34 [unknown] [tion-measurement.md](../../simulation-measurement.md)；热路径公式不重复 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L218 [unknown] [*；R_REF 成为主要误差源（ANA-S04 1.4 节）。**[原厂]** 三线制双 IDAC 的完整式（拓扑与选型步骤见 [ANA-10 RTD/热敏电阻](../../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L288 [unknown] [分压地、ADC AGND、基准地在 ADC 处单点汇合；功率地/数字地不能穿过这段（ANA-01 §9；[module-integration.md 第 9 节](../../module-integration.md) → `references/module-integration.md` (ok)
- L297 [unknown] [rced with net-tie”（`v3/CHANGELOG.md`）。**[作者记录]** 该案例的完整排查链见 [F01 ODrive 电流采样寄生电阻](../../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L478 [unknown] [
  "board_verified": false
}
```

**与现有仿真记录对照：** [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)

### `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md`

- 标题：C2 接地、屏蔽与共模：先画回流，再谈接地与屏蔽
- 行/字符/字节：789 / 37075 / 71715
- SHA-256：`96e15cd07cdb81d3c22b04723e9df0f520b7ba5fec83db00805c8449ff4d586e`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok) #10-来源与适用范围 ok
- L34 [unknown] [值，不是某颗器件的保证值；`[未执行]` 本次没有做仿真、EMC 或实物测量。
>
> **与现有内容的关系：** 本文不重复 [ANA-06 低侧电流采样](../../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L34 [unknown] [/../design-cards/analog/a06-low-side-sense.md) 的传递函数与 Kelvin 步骤，不重复 [ANA-03 差分放大](../../design-cards/analog/a03-diff-amp.md) → `references/design-cards/analog/a03-diff-amp.md` (ok)
- L34 [unknown] [/design-cards/analog/a03-diff-amp.md) 的增益/CMRR 推导，也不重复 [module-integration.md §9](../../module-integration.md) → `references/module-integration.md` (ok)
- L44 [unknown] [变成差模或共模误差 |
| 低侧/在线分流，或分流电阻 <10 mΩ | 需要 | Kelvin 接法、地电位差、PWM 共模瞬态都会进入误差链；见 [F01](../../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L125 [required_read] [核对（G06 p.7；`[推断]` 具体电容值待仿真/实测）。铺铜/改铜区后参考路径被切断、铜区未重填、孤岛/细颈的检查见 [F16 铺铜后参考路径/连通性变化](../../failures/f16-copper-pour-reference.md) → `references/failures/f16-copper-pour-reference.md` (ok)
- L278 [background] [把两层 GND 连起来，过孔在信号换层过孔 200 mil 内对称布置（G06 p.6–8）。这些检查在现有规则中对应 [RT04/RT06/RT15/RT23](../../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L311 [unknown] [0° 接机壳？
- 连接器附近是否有缝合过孔，把地针电流分散到平面？

### 4.4 Kelvin/分流布局

对低侧/在线分流，按 [ANA-06](../../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L340 [unknown] [要按实际壳内环境测，不能用开放环境的热阻（`[未执行]` 热实测）。热阻/温升的一阶公式、`θJA` 与铜面积/气流的关系见 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L559 [unknown] [| 差分/隔离探头，短地弹簧 | 不超器件绝对最大；无异常振铃 | 普通接地探头不能接浮动 SW（见 [simulation-measurement.md §7](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L561 [unknown] [ |

测量前先算探头负载效应；测量后记录板号/版本/仪器/探头/条件。没有这些，波形不能当证据（[simulation-measurement.md §5](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L687 [unknown] [R 看反射点；若在过孔/连接器/ESD 处 → H3/H4。
4. 查线宽/间距/参考平面边缘；不满足 5W/90 mil → H5。
5. 对照 [F17](../../failures/f17-diff-split-reference.md) → `references/failures/f17-diff-split-reference.md` (ok)
- L768 [background] [R35`/`C155` DNP；4 层板 | 未测屏蔽效能/辐射；DNP 选择是否最优未验证 |
| F16/F17 | [F16 铺铜后参考路径/连通性变化](../../failures/f16-copper-pour-reference.md) → `references/failures/f16-copper-pour-reference.md` (ok)
- L768 [background] [16 铺铜后参考路径/连通性变化](../../failures/f16-copper-pour-reference.md)、[F17 差分等长但跨参考平面分割](../../failures/f17-diff-split-reference.md) → `references/failures/f17-diff-split-reference.md` (ok)

### `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md`

- 标题：C3 运放容易被漏查的工作条件
- 行/字符/字节：585 / 37050 / 69420
- SHA-256：`51810d629a2691306293e9dd8300b6c8621846e7dd0294c649683336b93dfcf1`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok) #10-来源与适用范围 ok
- L32 [unknown] [而设的假设值，不是某颗器件的保证值；`[未执行]` 本次未做仿真或测量。
>
> **与现有内容的关系：** 本文不重复 [ANA-02 运放缓冲/同相放大](../../design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L32 [unknown] [复 [ANA-02 运放缓冲/同相放大](../../design-cards/analog/a02-opamp-buffer.md)、[ANA-03 差分放大](../../design-cards/analog/a03-diff-amp.md) → `references/design-cards/analog/a03-diff-amp.md` (ok)
- L32 [unknown] [.md)、[ANA-03 差分放大](../../design-cards/analog/a03-diff-amp.md)、[ANA-04 SAR ADC 驱动](../../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L32 [unknown] [为“待按具体运放手册核对”的那一层：共模交越、输出线性区、容性负载、输入保护、上电顺序、Ib/Ios 与低频噪声。ADC 建立时间与 F22 的分工见 [F22](../../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L32 [unknown] [ 的分工见 [F22](../../failures/f22-adc-settling.md)；测量总则见 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L32 [unknown] [lation-measurement.md](../../simulation-measurement.md)；热公式不重复 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L45 [unknown] [IA）接法 | 误套“高源阻抗电压源”判据；反相输入是虚地 | `Ib×Rf`、`Cd/Cf` 稳定性、暗电流、guard/漏电 | 见 [B2 光电二极管前端](../../common-hardware/b-optics.md) → `references/common-hardware/b-optics.md` (ok)
- L176 [unknown] [置数字标 `[计算]`；未实测的连接解释标 `[推断]`。

模块间接口契约（谁驱动谁、上电顺序、负载归属）见 [module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L399 [unknown] [−、负载、温度、C_L、探头、带宽限制），否则数字不可复用。

## 7. 常见失败现象与排查顺序

排查链沿用 [failures/README.md](../../failures/README.md) → `references/failures/README.md` (ok)

### `references/engineering-deepdives/topics/c4-measurement-artifacts.md`

- 标题：C4 测量方法本身造成的错误
- 行/字符/字节：710 / 32165 / 59837
- SHA-256：`4f33fa4978f009b1992d0006a26a7b17a53f358dd677ed83cabf69acb3a2a321`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok) #10-来源与适用范围 ok
- L32 [unknown] [录；`[未执行]` 本稿没有做的测量/仿真。
>
> **与现有内容的关系：** 设计侧的 Kelvin、分流选型、误差预算见 [ANA-06 低侧电流采样](../../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L32 [unknown] [ [ANA-06 低侧电流采样](../../design-cards/analog/a06-low-side-sense.md)、[ANA-07 高侧电流采样](../../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L32 [unknown] [-07 高侧电流采样](../../design-cards/analog/a07-high-side-sense.md)、[C1 从传感器到 ADC 的误差链](c1-sensor-to-adc-error-chain.md) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok)
- L32 [unknown] [se.md)、[C1 从传感器到 ADC 的误差链](c1-sensor-to-adc-error-chain.md)、[F01 ODrive 电流采样寄生电阻](../../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L32 [unknown] [[F01 ODrive 电流采样寄生电阻](../../failures/f01-odrive-sense-parasitic.md)；ADC 建立见 [F22](../../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L32 [unknown] [d)；ADC 建立见 [F22](../../failures/f22-adc-settling.md)；热测量清单见 [thermal/topic.md §8](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L108 [unknown] [| 只给平均值，不给纹波 | 任何“纹波”结论 |

测点、仪器、探头、带宽与负载的完整选择表见 [simulation-measurement.md §5](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L155 [unknown] [流；读数会变，探头/仪器也可能受损。这时用差分/隔离探头，不要用“把地线夹到机壳”解决。`[原厂]` [simulation-measurement.md §7](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L282 [unknown] [件]` `schematic_v3.5.pdf` 第 3 页 U5 通道的 R45/R46；第 2 页 U4 通道的 R27/R28 同构；作者记录见 [F01](../../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L569 [unknown] [波。用示波器 AC 耦合+短地复核，不用 INA260 判断纹波。
- **ADC**：读码值/`VREF`/采样时间；源阻抗/采样电容/建立时间见 [F22](../../failures/f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L598 [unknown] [良；50 Ω 负载改变电路；阻尼电阻功耗；TVS 电容。 |

如果短地/同轴下振铃仍在，且与负载/输入电压相关，按 [F10 Buck 反馈/输入电容布局](../../failures/f10-buck-loop-layout.md) → `references/failures/f10-buck-loop-layout.md` (ok)
- L607 [unknown] [文件]` `schematic_v3.5.pdf` 第 3 页 R45/R46 500 µΩ+Net Tie；`[原厂]` SSZT805 式 2/3；[F01](../../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L652 [unknown] [---|---|
| 用户说“纹波 50 mV，超标” | 原理图轨/`COUT`/`fsw`；[simulation-measurement.md §5.3](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L652 [unknown] [/`fsw`；[simulation-measurement.md §5.3](../../simulation-measurement.md)；[PWR-02](../../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L653 [unknown] [各测一次 | 预期值+两张波形+仪器设置 | 接法改变结果→判测量假象；不变→查 `COUT`/ESR/环路 |
| 用户说“电流采样比例误差” | [F01](../../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L653 [unknown] [|
| 用户说“电流采样比例误差” | [F01](../../failures/f01-odrive-sense-parasitic.md)、[ANA-06](../../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L654 [unknown] [不变→增益/固件/ `VREF` |
| 用户说“相电流尖峰/负值” | VESC `R53/R54`、`R48–R51`、`C34/C36`；[ANA-07](../../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L655 [unknown] [分/单端对比、采样点 | 0 A 仍有→共模/探头；0 A 干净→真实续流/采样时刻 |
| 用户说“温度超限” | [thermal/topic.md §8](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L656 [unknown] [与示波器不一致” | INA260 SBOS656C tCT/averaging；MNT U6/L1；[simulation-measurement.md §5](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L684 [unknown] [ V | 只属该 24 V 适配器/测试电路；不能套所有电缆/电容 |
| P04 / F01 | ODrive v3 `CHANGELOG.md`；[F01](../../failures/f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L689 [unknown] [60；不能把 1.25 mV/LSB 当精度；不能用于纹波 |
| SIM-MEAS-5-8 | 本仓库 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L690 [unknown] [ | 该文未执行板级测量；具体仪器型号未记录 |
| THERMAL-8 / thermal/topic.md | 本仓库 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/engineering-deepdives/topics/d1-interface-combination-constraints.md`

- 标题：D1 接口组合后的隐藏约束
- 行/字符/字节：749 / 37324 / 65846
- SHA-256：`b167b080d537fe0baaf991b7e9d34709ab75f52cfd67c692fff59c548bc4784a`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #5-方案与取舍 ok
- L11 [unknown] [、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok) #10-来源与适用范围 ok
- L32 [unknown] [真实板的事故记录；`[未执行]` 本次没有仿真或测量。
>
> **与现有内容的关系：** 单条总线的公式、参数步骤与完整算例见 [IF-01 I²C 总线](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L32 [unknown] [[IF-01 I²C 总线](../../design-cards/interfaces/i01-i2c.md)；缓冲/中继的静态偏移与使能时序见 [IF-02](../../design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L32 [unknown] [偏移与使能时序见 [IF-02](../../design-cards/interfaces/i02-i2c-buffer.md)；SPI 拓扑见 [IF-04](../../design-cards/interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L32 [unknown] [)；SPI 拓扑见 [IF-04](../../design-cards/interfaces/i04-spi-multi.md)；电平转换判据见 [IF-12](../../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L32 [unknown] [判据见 [IF-12](../../design-cards/interfaces/i12-level-shift.md)；上拉过强/过弱的单板故障见 [F06](../../failures/f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L94 [unknown] [issues"`，`not_checked` 明确包含“器件额定/阈值/电压域”“去耦/稳定性/热/SI/EMC”（[module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L180 [unknown] [流仅 1.30 mA，不是瓶颈 | `tr>300 ns`；`Rp(max)=1967 Ω <2350 Ω` | [module-integration C01](../../module-integration.md) → `references/module-integration.md` (ok)
- L180 [unknown] [)=1967 Ω <2350 Ω` | [module-integration C01](../../module-integration.md)；[IF-01](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L181 [unknown] [；固定地址模块无法改 | 两个 ACK/同一地址；`0x50` 与 `0xA0` 是同一器件 | Crazyflie `U1` 标注 1010000b；[C10](../../module-integration.md) → `references/module-integration.md` (ok)
- L184 [unknown] [ISO 三态、启动 strap | Feather Sense `QSPI_CS` 无外部上拉（`IC2.SSEL`↔`MDBT1.P0.20`）；[IF-04](../../design-cards/interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L185 [unknown] [定 | Feather `MS1.GPIOTX/RX`↔`MDBT1.P0.24/25`；Crazyflie `P6` 的 `E_RX1/E_TX1`；[F03](../../failures/f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L186 [unknown] [H(min)=3.2 V`，差 0.3 V；低电平却通过 | `VOH(min)>VIH(max)` 不成立 | [module-integration C02](../../module-integration.md) → `references/module-integration.md` (ok)
- L187 [unknown] [.5 V 偏移、70 mV 识别余量；EN 需 START 前 100 ns/STOP 后 100 ns | IF-S10 第 1、3、6–7 页；[IF-02](../../design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L298 [unknown] [ pF，并在 100 pF 节点上就是 10–15% 的 `Cb` 增量；测边沿时用短地弹簧，不要用长地线（[simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L318 [unknown] [ SDA/SCL，避免在总线忙时被耦合翻转。
- **连接器**：地针先接触、数量足够；热插拔时避免浪涌走信号针。FPC 还要查 Pin-1/接触面（[F15](../../failures/f15-fpc-pin1.md) → `references/failures/f15-fpc-pin1.md` (ok)
- L329 [unknown] [的 `Icc`、负载开关的 `Ron` 要按手册算；没有手册就写“待按型号”。

热的一阶方法、`θJA` 的适用条件见 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L526 [unknown] [不接”的 `tr` | 探头电容不把边沿推出规格 | 实际无探头时的 EMC |

**测量总则**见 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L530 [unknown] [上拉数量、DNP、串阻、连接器脚序、地址脚接法、CS/EN 默认态。结构检查只能证明“连通”，不能证明“电气正确”（[module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L533 [unknown] [描、9 clock 恢复、GPIO 默认态、看门狗复位后的引脚状态。硬件 strap 决定的启动模式，固件改不回来（[module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L534 [unknown] [ration.md](../../module-integration.md) §11.2）。
- **连接器/FPC**：Pin-1、视角、接触面（[F15](../../failures/f15-fpc-pin1.md) → `references/failures/f15-fpc-pin1.md` (ok)
- L621 [unknown] [AM_I。

**证据：** Crazyflie `U1` 固定 `1010000b`；Feather Sense 的 `SDO/ADDR` 接法；[C10](../../module-integration.md) → `references/module-integration.md` (ok)
- L647 [unknown] [**证据：** `3.2 V<3.5 V`，差 0.3 V；TTL 2.0 V 可通过；线降/负载进一步吃掉余量（[module-integration C02](../../module-integration.md) → `references/module-integration.md` (ok)
- L728 [unknown] [100 kΩ EN；`RESET` 共享 | 只证明设计这样连；传感器地址/`Cb` 未实测 |
| 现有库 | [module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L728 [unknown] [ 现有库 | [module-integration.md](../../module-integration.md) C01–C06、§14.4；[IF-01](../../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L728 [unknown] [ation.md) C01–C06、§14.4；[IF-01](../../design-cards/interfaces/i01-i2c.md)、[IF-02](../../design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L728 [unknown] [aces/i01-i2c.md)、[IF-02](../../design-cards/interfaces/i02-i2c-buffer.md)、[IF-04](../../design-cards/interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L728 [unknown] [02-i2c-buffer.md)、[IF-04](../../design-cards/interfaces/i04-spi-multi.md)、[IF-12](../../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L728 [unknown] [i04-spi-multi.md)、[IF-12](../../design-cards/interfaces/i12-level-shift.md)；[F06](../../failures/f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L728 [unknown] [ards/interfaces/i12-level-shift.md)；[F06](../../failures/f06-i2c-pullup.md)、[F03](../../failures/f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L728 [unknown] [(../../failures/f06-i2c-pullup.md)、[F03](../../failures/f03-esp32-strap.md)、[F15](../../failures/f15-fpc-pin1.md) → `references/failures/f15-fpc-pin1.md` (ok)

### `references/engineering-deepdives/topics/d2-clock-system-checklist.md`

- 标题：D2 时钟系统完整检查
- 行/字符/字节：719 / 37088 / 68629
- SHA-256：`fbd69e351685776ae9f7eb2eaa241f971a9bd330feaf63b1c2364d1bd972c0b3`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #5-方案与取舍 ok
- L11 [unknown] [、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/d2-clock-system-checklist.md` (ok) #10-来源与适用范围 ok
- L30 [unknown] [缺型号资料、待按型号核对的点。本稿没有做任何实物测量，也没有把公式结果当成实测。
>
> **与现有内容的关系：** 本文不重复 [MCU-05 晶体振荡器](../../design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L30 [unknown] [ [MCU-05 晶体振荡器](../../design-cards/mcu/m05-crystal.md) 的逐项参数步骤，也不重复 [MCU-06 外部时钟](../../design-cards/mcu/m06-external-clock.md) → `references/design-cards/mcu/m06-external-clock.md` (ok)
- L30 [unknown] [有源晶振选型；本文补的是**跨方案判据、真实设计读图证据、测量扰动、模组时钟所有权**，以及“公式用错会把好设计判死”的边界。晶体失效排查的通用结构见 [F05](../../failures/f05-crystal-load-esr.md) → `references/failures/f05-crystal-load-esr.md` (ok)
- L30 [unknown] [](../../failures/f05-crystal-load-esr.md)；探头与接地假象见 [simulation-measurement.md §5](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L30 [unknown] [d §5](../../simulation-measurement.md)；模组“已集成外围”的去重表见 [module-integration.md §10](../../module-integration.md) → `references/module-integration.md` (ok)
- L185 [unknown] [ 探头。
- 探头地线夹的引线电感会引入振铃/假象；地线越长，这个假象越明显。具体机理与算例见 [simulation-measurement.md §5.3](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L193 [required_read] [省略所有时钟检查；也不能因为“参考电路画了晶体”就给一个内部已含晶体的模组外加晶体（驱动冲突）。所有权表见 [module-integration.md §10](../../module-integration.md) → `references/module-integration.md` (ok)
- L208 [conditional_read] [时 ≤10 kΩ 上拉或选 NC | 悬空；把 OE 低当断电 | 数据手册 + 原理图 |
| 输出串阻 | 需要时 22–33 Ω（DNP，[MCU-06](../../design-cards/mcu/m06-external-clock.md) → `references/design-cards/mcu/m06-external-clock.md` (ok)
- L283 [unknown] [，走线短；ESP32-S3 指南给的是“距时钟脚至少 2.0 mm、下方不走线”，条件是该芯片/该指南（经 [module-integration.md §12](../../module-integration.md) → `references/module-integration.md` (ok)
- L290 [conditional_read] [境建议三防漆；漏电会延长启动甚至不起振 | AN2867 §7.1 | 工艺文件 |
| 探测 | 不长期加测试支路；需要时缓冲 | RT24；[MCU-05](../../design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L321 [unknown] [敏感；避免把晶体放在板边、螺钉孔、连接器插拔受力区；按器件手册的焊盘/回流要求，不要用外力压晶体。
- 热设计的一般方法见 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/engineering-deepdives/topics/d3-off-board-interfaces.md`

- 标题：D3 连接器与板外通信：地电位、端接、保护与连接器契约
- 行/字符/字节：1032 / 48985 / 87933
- SHA-256：`01de96008a6537cfed37a2ee04d012c3adb0c02c85af41cd3c416825064fc6e6`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok) #10-来源与适用范围 ok
- L34 [unknown] [执行` 表示没有仿真/测量/台架结果。开源设计只证明“有人这样设计”，不证明它正确。
>
> **与现有内容的关系：** 不重复 [IF-07 RS-485](../../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L34 [unknown] [07 RS-485](../../design-cards/interfaces/i07-rs485.md) 的端接/偏置参数步骤，不重复 [IF-08 CAN](../../design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L34 [unknown] [(../../design-cards/interfaces/i08-can.md) 的分裂端接公式，不重复 [module-integration.md §7](../../module-integration.md) → `references/module-integration.md` (ok)
- L136 [unknown] [：5 ns/m 与终端

SLLA270 第 9 页 §4.8 给典型双绞线传播延时 5 ns/m（去回 10 ns/m）；现有 [IF-07 RS-485](../../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L469 [unknown] [阻、隔离 DC/DC 的效率都要进热预算；具体 `θJA` 按封装/铜面积/气流查手册，不能用一个数字套所有板。热计算方法见 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L592 [external_reference] [/CANL保证范围、接收共模、瞬态和故障电压检查。不能仅凭2 V地差断言必须隔离，也不能据这一算例断言不需要隔离。原厂机制参考：[TI SLLA337，图1-2](https://www.ti.com/lit/pdf/slla337) → `https://www.ti.com/lit/pdf/slla337` (external)
- L1006 [unknown] [N8710A/LPJ0011BBNL 手册未读；第 9 页未见分立 TVS |
| D3-S11 | 现有 [module-integration.md §7](../../module-integration.md) → `references/module-integration.md` (ok)
- L1007 [conditional_read] [面、反灌路径、去重规则 | 通用方法；具体连接器/线缆仍需原厂图纸/手册 |
| D3-S12 | 现有 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L1024 [unknown] [/医疗安规不在本文范围。`[原厂 + 版本边界]`

### 10.3 与现有内容的关系

- 端接/偏置的完整参数步骤：看 [IF-07 RS-485](../../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L1024 [unknown] [置的完整参数步骤：看 [IF-07 RS-485](../../design-cards/interfaces/i07-rs485.md)、[IF-08 CAN](../../design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L1025 [unknown] [CAN](../../design-cards/interfaces/i08-can.md)。
- RS-232 电荷泵/逐脚：看 [IF-06 RS-232](../../design-cards/interfaces/i06-rs232.md) → `references/design-cards/interfaces/i06-rs232.md` (ok)
- L1026 [unknown] [-232](../../design-cards/interfaces/i06-rs232.md)。
- USB 全速：看 [IF-09 USB 2.0 FS](../../design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L1027 [unknown] [sign-cards/interfaces/i09-usb-device.md)。
- 以太网 PHY/磁性：看 [IF-11 10/100 Ethernet](../../design-cards/interfaces/i11-ethernet.md) → `references/design-cards/interfaces/i11-ethernet.md` (ok)
- L1028 [unknown] [../design-cards/interfaces/i11-ethernet.md)。
- 端接/共模失败的排查模板：看 [F07 RS-485 端接/偏置](../../failures/f07-rs485-termination.md) → `references/failures/f07-rs485-termination.md` (ok)
- L1028 [unknown] [查模板：看 [F07 RS-485 端接/偏置](../../failures/f07-rs485-termination.md)、[F08 CAN 端接/共模](../../failures/f08-can-termination.md) → `references/failures/f08-can-termination.md` (ok)
- L1029 [unknown] [./failures/f08-can-termination.md)。
- 连接器/线缆/FPC 契约：看 [module-integration.md §7](../../module-integration.md) → `references/module-integration.md` (ok)
- L1030 [unknown] [.md §7](../../module-integration.md)。
- 测量假象/示波器接地：看 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L1031 [unknown] [easurement.md](../../simulation-measurement.md)。
- 热预算/封装热阻：看 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/engineering-deepdives/topics/d4-wireless-integration.md`

- 标题：D4 无线性能与整机环境：从模组上板到整机射频
- 行/字符/字节：717 / 37441 / 69861
- SHA-256：`00f16576138394c0deee2beba37afbdc779ef8e0dc2aff0fea137a0216f0e0e4`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #5-方案与取舍 ok
- L11 [unknown] [、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok) #10-来源与适用范围 ok
- L30 [unknown] [做的仿真/测量/认证；`[待核]` 为缺型号资料、不能给保证值的点。
>
> **与现有内容的关系：** 本文不重复 [RF-01 Wi-Fi/BLE 模组](../../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L30 [unknown] [./../design-cards/wireless/w01-wifi-ble.md) 的供电/EN/strap 逐脚步骤，不重复 [RF-02 天线接口与匹配](../../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L30 [unknown] [./../design-cards/wireless/w02-antenna.md) 的 50 Ω/CLC 参数步骤，也不重复 [F18 天线净空/外壳导致失谐](../../failures/f18-antenna-enclosure.md) → `references/failures/f18-antenna-enclosure.md` (ok)
- L30 [unknown] [st 电流与电源阻抗、以及把“模组可用”误当成“整机射频已验证”的具体失败路径。组合层面的机械/天线检查见 [module-integration.md §12](../../module-integration.md) → `references/module-integration.md` (ok)
- L30 [unknown] [ntegration.md §12](../../module-integration.md)；测量方法见 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L172 [unknown] [整机效率/方向图仍然差，因为损耗体还在天线近场里。

RF-02 已经给出了 CLC 初值、0201 封装和电抗灵敏度的算法（[w02-antenna.md](../../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L214 [unknown] [时，是否有官方测试模式/耦合方式？不要为了测 S11 在模组天线上割线。

RF-02 的测试口规则和 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L225 [unknown] [/45/46 默认态、采样窗 | 启动/下载模式不被射频/外设驱动；strap 脚无大电容 | 模组进不了启动/下载；射频一开就复位 | RF-S01；[F03](../../failures/f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L228 [unknown] [ | 测试口 50 Ω、短 stub、可断开；校准到口 | 长支路导致陷波；探头直接挂天线 | RF-02；[simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L309 [unknown] [：`P = (VIN − VOUT) × I`；burst 时 I 更大，热是脉冲/平均的组合。LDO 热算方法见 [thermal/topic.md §3.1](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L464 [unknown] [/阻焊）、天线模型、匹配件寄生、外壳 3D、电池/金属件位置；缺一项就标 `[待核]`。
- 现有总则见 [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L493 [unknown] [换天线+改匹配+换外壳。

### 7.1 链路 1：裸板正常，装壳/装电池后距离下降

更完整的现象/假设/检查表见 [F18 天线净空/外壳导致失谐](../../failures/f18-antenna-enclosure.md) → `references/failures/f18-antenna-enclosure.md` (ok)
- L625 [unknown] [近芯片、优先 CLC；参考值只是起点，不能证明已匹配（调谐目标是芯片共轭点 35+j0 Ω，不是 S11 的 dB 门限）。
- `[设计卡]` [RF-02](../../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L642 [unknown] [测试矩阵/C2PC 条件 | KDB 页码、grant 条款 | grant 未读→不能给结论；标 `[待核]` |
| 用户报“装壳后距离短” | [F18](../../failures/f18-antenna-enclosure.md) → `references/failures/f18-antenna-enclosure.md` (ok)
- L700 [unknown] [15 U20、PCIE1_PWR_EN、LED_WLAN1 | 只有主板，无 Wi-Fi 卡/天线装配；不能核对整机 RF |
| 现有文档 | [RF-01](../../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L700 [unknown] [能核对整机 RF |
| 现有文档 | [RF-01](../../design-cards/wireless/w01-wifi-ble.md)、[RF-02](../../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L700 [unknown] [less/w01-wifi-ble.md)、[RF-02](../../design-cards/wireless/w02-antenna.md)、[RF-04](../../design-cards/wireless/w04-gnss.md) → `references/design-cards/wireless/w04-gnss.md` (ok)
- L700 [unknown] [s/wireless/w02-antenna.md)、[RF-04](../../design-cards/wireless/w04-gnss.md)、[F18](../../failures/f18-antenna-enclosure.md) → `references/failures/f18-antenna-enclosure.md` (ok)
- L700 [unknown] [4-gnss.md)、[F18](../../failures/f18-antenna-enclosure.md)、[module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L700 [unknown] [、[module-integration.md](../../module-integration.md)、[simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L700 [unknown] [)、[simulation-measurement.md](../../simulation-measurement.md)、[thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md`

- 标题：E1 感性负载与能量去向：继电器、电磁阀、风扇与电机的关断路径
- 行/字符/字节：526 / 36600 / 69023
- SHA-256：`27137d8ad25e05bb2b3544c880e54ad6fdc4787c705aeb36f687f7e59302f7e0`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/e1-inductive-load-energy-path.md` (ok) #10-来源与适用范围 ok
- L31 [unknown] [条件，不对应具体板；`【未执行】`=未执行（本次没有仿真或实测）。
> **与现有内容的关系：** 拓扑、参数步骤、逐脚表和算例在 [DRV-03 继电器驱动](../../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)
- L31 [unknown] [扑、参数步骤、逐脚表和算例在 [DRV-03 继电器驱动](../../design-cards/drive/d03-relay.md)、[DRV-05 H 桥](../../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L31 [unknown] [3-relay.md)、[DRV-05 H 桥](../../design-cards/drive/d05-h-bridge.md)、[DRV-08 加热器控制](../../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L31 [unknown] [h-bridge.md)、[DRV-08 加热器控制](../../design-cards/drive/d08-heater.md)、[DRV-01 低侧开关](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L31 [unknown] [)、[DRV-01 低侧开关](../../design-cards/drive/d01-low-side.md)；故障链在 [F14 继电器线圈无续流/释放慢](../../failures/f14-relay-flyback.md) → `references/failures/f14-relay-flyback.md` (ok)
- L129 [unknown] [电容负责开关频率级的纹波和极短瞬态；持续回生必须由电池、制动斩波或受控减速接走。** 这条与 [module-integration.md §8.2 反灌路径表](../../module-integration.md) → `references/module-integration.md` (ok)
- L438 [unknown] [V 稳压管）；(c) 线圈 `L` 远大于假设，能量/尖峰超 `E_AS`；(d) 续流回路布局电感大，振铃叠加；(e) 栅极误导通/直通（见 [E2 栅极驱动](e2-gate-drive-and-false-turn-on.md) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok)
- L440 [unknown] [ 的 `V=L·di/dt`、续流/钳位公式；DRV-S05 §6 的 SOA/雪崩区分；DRV-S11 §3.1 的“钳位能量有限”。`【故障库】` [F14](../../failures/f14-relay-flyback.md) → `references/failures/f14-relay-flyback.md` (ok)
- L523 [unknown] [区分检查/修复/复验/边界；B 级，无本次实物复现 | 不能当已证实根因；没有具体型号释放时间/寿命数字 |

**其他引用：** [DRV-01 低侧开关](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L523 [unknown] [
**其他引用：** [DRV-01 低侧开关](../../design-cards/drive/d01-low-side.md)、[DRV-03 继电器驱动](../../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)
- L523 [unknown] [1-low-side.md)、[DRV-03 继电器驱动](../../design-cards/drive/d03-relay.md)、[DRV-05 H 桥](../../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L523 [unknown] [3-relay.md)、[DRV-05 H 桥](../../design-cards/drive/d05-h-bridge.md)、[DRV-08 加热器控制](../../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L523 [unknown] [dge.md)、[DRV-08 加热器控制](../../design-cards/drive/d08-heater.md)、[F14 继电器线圈无续流/释放慢](../../failures/f14-relay-flyback.md) → `references/failures/f14-relay-flyback.md` (ok)
- L523 [unknown] [圈无续流/释放慢](../../failures/f14-relay-flyback.md)、[module-integration.md §8.2 反灌路径表](../../module-integration.md) → `references/module-integration.md` (ok)
- L523 [unknown] [md §8.2 反灌路径表](../../module-integration.md)、[simulation-measurement.md §5.3 探头接地](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L523 [unknown] [rement.md §5.3 探头接地](../../simulation-measurement.md)、[thermal/topic.md §5 瞬态与脉冲](../../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md`

- 标题：E2 MOS 栅极驱动与异常状态：从 Qg/Qgd 到默认关断
- 行/字符/字节：496 / 33604 / 59498
- SHA-256：`30e837146e534e9bb0d2032fabc51cb79d2e481f3cbc7fdf26082284ee5d4628`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok) #10-来源与适用范围 ok
- L29 [unknown] [** 隔离栅驱、高压安规/爬电、栅极驱动器芯片内部设计、纯集成智能开关的内部 FET 设计。集成高侧开关的 EN/FAULT/限流仍按 [DRV-02 高侧开关](../../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L31 [unknown] [ 是为说明方法编造的条件，不对应具体板；`【未执行】` 表示本次没有仿真或实测。
> **与现有内容的关系：** 参数步骤、逐脚表和完整算例在 [DRV-01](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L31 [unknown] [的关系：** 参数步骤、逐脚表和完整算例在 [DRV-01](../../design-cards/drive/d01-low-side.md)、[DRV-02](../../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L31 [unknown] [ive/d01-low-side.md)、[DRV-02](../../design-cards/drive/d02-high-side.md)、[DRV-04](../../design-cards/drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L31 [unknown] [/d02-high-side.md)、[DRV-04](../../design-cards/drive/d04-half-bridge.md)、[DRV-05](../../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L45 [unknown] [成智能高侧开关，内部已含电荷泵、限流、热关断和诊断，且 datasheet 已覆盖实际负载；此时重点转为 EN/FAULT/默认态和外部钳位，按 [DRV-02](../../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L48 [unknown] [结论；这些项在本文标“待按型号核对”。
- 需要隔离、安规、爬电/间隙、功能安全（STO 等）：不在本文范围；按 [module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L298 [unknown] [不变），`P_sw=2.4 W`。这是线性重叠的一阶估算，不含 `C_oss`、`Q_rr`、振铃和二极管恢复；`【文件】` [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L337 [unknown] [ 兜底；太小直通，太大体二极管损耗/反向恢复增加。具体 ns 值按驱动器和 FET 延迟核对。`【原厂】` DRV-S05 §7；`【设计卡】` [DRV-04](../../design-cards/drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L381 [unknown] [驱动器 | 实际 PWM/温度；避免气流 | 平均功率/布局热点；不能证明脉冲额定 |

`【文件】` [simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L419 [unknown] [.2 Ω、DRV8301 的 `DTC` 脚；VESC 用 4.7 Ω、DRV8302；两者都把死区/栅极网络当设计变量。`【推断】` `【故障库】` [F13](../../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L428 [unknown] [9/R70 为 22 Ω 串联（网络 `GPIO_FET1`/`PWM1_FET`/`GPIO_FET`）；这是默认态的正面样本。`【设计卡】` [DRV-04](../../design-cards/drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L428 [unknown] [esign-cards/drive/d04-half-bridge.md) §10 的启动/复位行要求上下管下拉、驱动器 UVLO、EN 默认态；[DRV-02](../../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L437 [unknown] [；查驱动器 UVLO。
- **证据：** `【原厂】` DRV-S01 §2–§3.1 的自举公式和“自举只适合有限占空比”；`【设计卡】` [DRV-04](../../design-cards/drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L446 [unknown] [位置和钳位电压；查短路时限流/定时器。
- **证据：** `【原厂】` DRV-S05 §6 的 SOA 五条限制线和热不稳定判据；`【故障库】` [F13](../../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L446 [unknown] [故障库】` [F13](../../failures/f13-mosfet-soa.md) 的 H1–H4（B 级，未实物复现）；`【设计卡】` [DRV-01](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L493 [unknown] [；`OSHW-13/14/15` 为研究台账中的 ODrive/VESC/Smoothieboard 编号。

**其他引用：** [DRV-01 低侧开关](../../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L493 [unknown] [
**其他引用：** [DRV-01 低侧开关](../../design-cards/drive/d01-low-side.md)、[DRV-02 高侧开关](../../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L493 [unknown] [low-side.md)、[DRV-02 高侧开关](../../design-cards/drive/d02-high-side.md)、[DRV-04 半桥](../../design-cards/drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L493 [unknown] [gh-side.md)、[DRV-04 半桥](../../design-cards/drive/d04-half-bridge.md)、[DRV-05 H 桥](../../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L493 [unknown] [dge.md)、[DRV-05 H 桥](../../design-cards/drive/d05-h-bridge.md)、[thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L493 [unknown] [5-h-bridge.md)、[thermal/topic.md](../../thermal/topic.md)、[module-integration.md](../../module-integration.md) → `references/module-integration.md` (ok)
- L493 [unknown] [、[module-integration.md](../../module-integration.md)、[simulation-measurement.md](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)

### `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md`

- 标题：E3 热设计与机械环境：外壳、气流、安装与邻近热源如何改变热路径
- 行/字符/字节：628 / 38386 / 75244
- SHA-256：`63522e9ffbd2fdd072d2e56b6a57aa5274cabd66ebdc5bcf7178061fd6b65ed1`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #5-方案与取舍至少-3-种 ok
- L11 [unknown] [pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍（至少 3 种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [种）](#5-方案与取舍至少-3-种)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok) #10-来源与适用范围 ok
- L32 [unknown] [要求，不替代这些专门工作。
>
> **证据：** `【原厂】` 指原厂数据手册/应用笔记/官方文档（页码/章节来自 [thermal/sources.md](../../thermal/sources.md) → `references/thermal/sources.md` (ok)
- L34 [unknown] [；`【推断】` 是工程推断，需实测；`【未执行】` 表示本次没有仿真或实测。
>
> **与现有内容的关系：** 不重复 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L34 [unknown] [pic.md](../../thermal/topic.md) 的 Rθ 指标定义、JEDEC 测试板讨论和公式推导；不重复 [thermal/cases.md](../../thermal/cases.md) → `references/thermal/cases.md` (ok)
- L34 [unknown] [/cases.md) 的 C01–C11 算例。本文只补“机械/环境如何改变热路径”，并把每条结论落到位号、网络、页码或参数。器件级参数步骤仍看 [PWR-01](../../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L34 [unknown] [条结论落到位号、网络、页码或参数。器件级参数步骤仍看 [PWR-01](../../design-cards/power/p01-ldo.md)、[PWR-02](../../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L34 [unknown] [n-cards/power/p01-ldo.md)、[PWR-02](../../design-cards/power/p02-buck.md)、[DRV-05](../../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L34 [unknown] [ds/power/p02-buck.md)、[DRV-05](../../design-cards/drive/d05-h-bridge.md)、[DRV-08](../../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L34 [unknown] [DRV-08](../../design-cards/drive/d08-heater.md)；组合接口看 [module-integration.md §12](../../module-integration.md) → `references/module-integration.md` (ok)
- L34 [unknown] [tion.md §12](../../module-integration.md)；测量方法看 [simulation-measurement.md §5/§8](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L58 [unknown] [功耗 < 0.1 W，且没有电池/触摸/传感器/连接器热耦合。
- 只做封装比较或早期选型，不声称“实际板通过”；此时可按 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L101 [unknown] [面预算只约束**外壳表面**，不含内部空气到壳壁的热阻、热点、通风、太阳负载和海拔。

一阶算例（`【构造算例】`，沿用 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L126 [unknown] [寸”更常决定现场是否过热。

### 2.3 安装与界面：导热垫的 3.3 K/W 只是起点

`【构造算例】` 用 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L140 [unknown] [PCB 事后补铜。

### 2.4 邻近热源：0.5 W 在 20 mm 处可以是几十 K

`【构造算例】` 用 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L155 [unknown] [失去对流；灌封还会增加热质量、改变 CTE 失配、妨碍返修，并在热循环中把应力传到焊点/器件本体。

`【原厂/边界】` [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L165 [unknown] [tterypack.kicad_pcb:4、:8–9、:1151/1206/1261/1316、:1451）；电池包本身没有温度传感器网络。`【文件】` [E4](e4-connector-long-term-reliability.md) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok)
- L179 [unknown] [件。

**传感器：** 温度传感器测的是自身温度，受安装位置、导热胶、气流、邻热源、自热影响；NTC/RTD 的激励、分压、自热和线性化见 [ANA-10](../../design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L202 [unknown] [I S02 第 3 页“必须焊到 PCB 热焊盘” |
| 加热器/热电制冷 | 开关器件、默认关断、保险丝/热熔断、看门狗、温度反馈 | 见 [DRV-08](../../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L203 [unknown] [cards/drive/d08-heater.md)；本文不重复拓扑 |
| 连接器/端子 | 触点电流、电源/地针数量、相邻热源、线规、降额 | 见 [E4](e4-connector-long-term-reliability.md) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok)
- L258 [unknown] [导；有外露焊盘 + 散热器通常壳/散热器主导；密封小盒且没有 TIM 时，壳内空气可能主导。选错路径，后面算得再细也没用（见 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L291 [unknown] [。
- 热过孔的数量/孔径/镀层/塞孔方式按具体 datasheet 和板厂；1D 孔壁热阻、扩散热阻、界面热阻的算法已在 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L291 [unknown] [热阻、界面热阻的算法已在 [thermal/topic.md](../../thermal/topic.md) §6.2 和 [thermal/cases.md](../../thermal/cases.md) → `references/thermal/cases.md` (ok)
- L387 [unknown] [0 mm 宽 | 构造假设 |
| 海拔 | 2000 m | 定性修正 |

**步骤 1：外壳表面温升。** 沿用 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L396 [unknown] [.0`、`board_verified=false`；脚本只验证算式，不代表实测。

**步骤 2：导热垫热阻。** 用 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L402 [background] [xt
RθCS = 1×10⁻³/(3×1×10⁻⁴) = 3.33 K/W
```

**步骤 3：结温。** 按 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L419 [unknown] [.33 + 11.6 = 56.9 °C
```

**步骤 5：0.5 W 邻热源在 20 mm 处的量级。** 用 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L459 [unknown] [烫 ≠ Tj 不超限；红外图漂亮 ≠ 发射率/测点正确；仿真通过 ≠ 边界条件正确（见 [simulation-measurement.md §8.3–§8.4](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L573 [unknown] [；2000 m 只用 TI 表做量级，不是精确修正。
9. **连接器降额**：具体端子/连接器系列的额定电流-环境温度-线规-多针降额曲线未取得；见 [E4](e4-connector-long-term-reliability.md) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok)
- L602 [unknown] [nfineon D2PAK 铜面积，第 12、19–21 页）、S24（FLIR 红外不确定度）；版本/页码/适用条件见 [thermal/sources.md](../../thermal/sources.md) → `references/thermal/sources.md` (ok)
- L612 [unknown] [on-irfs7530-7p-datasheet-en.pdf>

S01–S27 的 URL/版本/实际阅读范围见 [thermal/sources.md](../../thermal/sources.md) → `references/thermal/sources.md` (ok)
- L616 [unknown] [2 与现有内容的关系

- 指标定义、RθJA/RθJC/Ψ/Zθ 的选择、JEDEC 测试板、C01–C11 算例：看 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L616 [unknown] [ 测试板、C01–C11 算例：看 [thermal/topic.md](../../thermal/topic.md) 和 [thermal/cases.md](../../thermal/cases.md) → `references/thermal/cases.md` (ok)
- L617 [unknown] [../../thermal/cases.md)；本文不重复。
- 机械/热/天线/测试空间的组合检查：看 [module-integration.md §12](../../module-integration.md) → `references/module-integration.md` (ok)
- L618 [unknown] [../module-integration.md)。
- 测量总则、探头/带宽/不确定度：看 [simulation-measurement.md §5/§8](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L619 [unknown] [urement.md §5/§8](../../simulation-measurement.md)。
- 连接器/端子/压接/铜箔窄颈的完整链路：看 [E4](e4-connector-long-term-reliability.md) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok)
- L620 [unknown] [E4](e4-connector-long-term-reliability.md)。
- LDO/Buck/H 桥/加热器的器件级热算例：看 [PWR-01](../../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L620 [unknown] [ LDO/Buck/H 桥/加热器的器件级热算例：看 [PWR-01](../../design-cards/power/p01-ldo.md)、[PWR-02](../../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L620 [unknown] [n-cards/power/p01-ldo.md)、[PWR-02](../../design-cards/power/p02-buck.md)、[DRV-05](../../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L620 [unknown] [ds/power/p02-buck.md)、[DRV-05](../../design-cards/drive/d05-h-bridge.md)、[DRV-08](../../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L620 [unknown] [bridge.md)、[DRV-08](../../design-cards/drive/d08-heater.md)；MOSFET SOA/热失效看 [F13](../../failures/f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)

### `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md`

- 标题：E4 连接与长期可靠性：端子、压接、焊点与铜箔窄颈的整条链路
- 行/字符/字节：695 / 30799 / 58869
- SHA-256：`62afc9912dbff8f0d45e87d9bb8883807cd6a2743965330570cd96140250fa49`

- L5 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #0-什么时候需要什么时候不需要 ok
- L6 [unknown] [---

## 内容导航

- [0. 什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #1-必须先知道的条件 ok
- L7 [unknown] [什么时候需要，什么时候不需要](#0-什么时候需要什么时候不需要)
- [1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #2-最容易被忽略的机制 ok
- L8 [unknown] [[1. 必须先知道的条件](#1-必须先知道的条件)
- [2. 最容易被忽略的机制](#2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #3-原理图检查引脚网络状态 ok
- L9 [background] [2-最容易被忽略的机制)
- [3. 原理图检查：引脚、网络、状态](#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #4-pcb-检查回路位置参考平面热路径 ok
- L10 [unknown] [#3-原理图检查引脚网络状态)
- [4. PCB 检查：回路、位置、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #5-方案与取舍 ok
- L11 [unknown] [、参考平面、热路径](#4-pcb-检查回路位置参考平面热路径)
- [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #6-怎么判断计算仿真测量回读 ok
- L12 [unknown] [5. 方案与取舍](#5-方案与取舍)
- [6. 怎么判断：计算、仿真、测量、回读](#6-怎么判断计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #7-常见失败现象与排查顺序 ok
- L13 [unknown] [计算仿真测量回读)
- [7. 常见失败现象与排查顺序](#7-常见失败现象与排查顺序)
- [8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #8-agent-行动触发读取动作证据失败后继续 ok
- L14 [unknown] [[8. Agent 行动（触发→读取→动作→证据→失败后继续）](#8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #9-仍需型号资料专家实物确认 ok
- L15 [unknown] [8-agent-行动触发读取动作证据失败后继续)
- [9. 仍需型号资料/专家/实物确认](#9-仍需型号资料专家实物确认)
- [10. 来源与适用范围](#10-来源与适用范围) → `references/engineering-deepdives/topics/e4-connector-long-term-reliability.md` (ok) #10-来源与适用范围 ok
- L32 [unknown] [`[工程推断]`；假设数字标 `[构造案例]`；没有做过的测量/试验标 `未执行`。
>
> **与现有内容的关系：** 不重复 [DRV-08 加热器控制](../../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L32 [unknown] [../../design-cards/drive/d08-heater.md) 的加热器拓扑与安全链；不重复 [module-integration.md §7](../../module-integration.md) → `references/module-integration.md` (ok)
- L32 [unknown] [le-integration.md §7](../../module-integration.md) 的连接器契约表；不重复 [thermal/topic.md](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L247 [unknown] [个连接器至少要有：板端（正视）、线端/配对端（正视）、装配后视角、FPC 金手指面（如适用）。现有模板见 [module-integration.md §7.2](../../module-integration.md) → `references/module-integration.md` (ok)
- L247 [unknown] [module-integration.md §7.2](../../module-integration.md)；FPC 的 Pin-1/接触面反例见 [F15](../../failures/f15-fpc-pin1.md) → `references/failures/f15-fpc-pin1.md` (ok)
- L689 [unknown] [查标准与做认证试验。
- 本专题的“通过/不通过”只表示纸面链路与测量方案是否自洽，不表示整机可靠。

### 10.4 相对链接

- [设计卡总览](../../design-cards/README.md) → `references/design-cards/README.md` (ok)
- L690 [unknown] [可靠。

### 10.4 相对链接

- [设计卡总览](../../design-cards/README.md)
- [DRV-08 加热器控制](../../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L691 [unknown] [RV-08 加热器控制](../../design-cards/drive/d08-heater.md)
- [故障库 F15 FPC Pin-1/接触面反向](../../failures/f15-fpc-pin1.md) → `references/failures/f15-fpc-pin1.md` (ok)
- L692 [unknown] [/接触面反向](../../failures/f15-fpc-pin1.md)
- [module-integration.md §7 连接器、线缆与 FPC](../../module-integration.md) → `references/module-integration.md` (ok)
- L693 [unknown] [ation.md §7 连接器、线缆与 FPC](../../module-integration.md)
- [thermal/topic.md 板级热设计](../../thermal/topic.md) → `references/thermal/topic.md` (ok)
- L694 [unknown] [al/topic.md 板级热设计](../../thermal/topic.md)
- [simulation-measurement.md §5 测量总则](../../simulation-measurement.md) → `references/simulation-measurement.md` (ok)

### `references/evidence.md`

- 标题：证据与轻量记录
- 行/字符/字节：30 / 917 / 2433
- SHA-256：`a62dd20adb5548889910c7eb516e9a7e28da91aac91871978686d3019fa0c8ac`

### `references/examples/README.md`

- 标题：原理图与 PCB 局部范例
- 行/字符/字节：22 / 1143 / 1982
- SHA-256：`fd9c0c6d73db424aa6115d58b172a609dcec98aaca5d2eac95d050b838b31c0c`

- L8 [example] [件 |
|---|---|---|
| Buck 功率回路：12 V→5 V/2 A 的回路、反馈与地 | 分析范例 | [x01-buck-loop.md](x01-buck-loop.md) → `references/examples/x01-buck-loop.md` (ok)
- L9 [example] [loop.md) |
| LDO 热与反向电流：5 V→3.3 V/150 mA 的结温、压差与倒灌 | 分析范例 | [x02-ldo-thermal.md](x02-ldo-thermal.md) → `references/examples/x02-ldo-thermal.md` (ok)
- L10 [example] [02-ldo-thermal.md) |
| 裸 MCU 最小系统：去耦、复位、BOOT 与调试口的局部约束 | 分析范例 | [x03-mcu-min.md](x03-mcu-min.md) → `references/examples/x03-mcu-min.md` (ok)
- L11 [example] [md](x03-mcu-min.md) |
| 晶体振荡器：16 MHz HSE 的负载电容、负阻与驱动电平 | 分析范例 | [x04-crystal.md](x04-crystal.md) → `references/examples/x04-crystal.md` (ok)
- L12 [example] [stal.md](x04-crystal.md) |
| 范例：I²C 温湿度传感器接口（上拉、总线电容与 ESD） | 分析范例 | [x05-i2c.md](x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L13 [example] [| [x05-i2c.md](x05-i2c.md) |
| 范例：RS-485 半双工总线（端接、偏置与保护） | 分析范例 | [x06-rs485.md](x06-rs485.md) → `references/examples/x06-rs485.md` (ok)
- L14 [example] [例 | [x06-rs485.md](x06-rs485.md) |
| 范例：CAN 总线节点（端接、支线与保护） | 分析范例 | [x07-can.md](x07-can.md) → `references/examples/x07-can.md` (ok)
- L15 [example] [07-can.md](x07-can.md) |
| 范例：USB-C 受电端（CC 下拉、VBUS 与数据保护） | 分析范例 | [x08-usbc.md](x08-usbc.md) → `references/examples/x08-usbc.md` (ok)
- L16 [example] [(x08-usbc.md) |
| 低侧 Kelvin 电流采样局部范例 | 分析范例（未在 EDA 中执行） | [x09-current-sense.md](x09-current-sense.md) → `references/examples/x09-current-sense.md` (ok)
- L17 [example] [x09-current-sense.md) |
| 4–20 mA 两线制接收局部范例 | 分析范例（未在 EDA 中执行） | [x10-4-20ma.md](x10-4-20ma.md) → `references/examples/x10-4-20ma.md` (ok)
- L18 [example] [](x10-4-20ma.md) |
| H 桥功率级局部范例（离线布局草案） | 离线布局草案（未在 EDA 中执行） | [x11-h-bridge.md](x11-h-bridge.md) → `references/examples/x11-h-bridge.md` (ok)
- L19 [example] [bridge.md) |
| Wi-Fi 模组与天线接口局部范例（离线布局草案） | 离线布局草案（未在 EDA 中执行） | [x12-antenna.md](x12-antenna.md) → `references/examples/x12-antenna.md` (ok)

### `references/examples/x01-buck-loop.md`

- 标题：Buck 功率回路：12 V→5 V/2 A 的回路、反馈与地
- 行/字符/字节：284 / 12416 / 24012
- SHA-256：`a04dff5709893a9bcda5515242d6781319654d03b9abac5eb21480336a7483a3`

- L4 [unknown] [

> **类型：** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/power/p02-buck.md`](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L4 [unknown] [buck.md`](../design-cards/power/p02-buck.md)（PWR-02）；组合入口见 [`../module-cards.md`](../module-cards.md) → `references/module-cards.md` (ok)
- L7 [unknown] [WR-S01（TI SLVA477C，Revision C，§1–§7）；G03（按开关状态找脉动回路，见 [`../design-experience.md`](../design-experience.md) → `references/design-experience.md` (ok)

### `references/examples/x02-ldo-thermal.md`

- 标题：LDO 热与反向电流：5 V→3.3 V/150 mA 的结温、压差与倒灌
- 行/字符/字节：279 / 12463 / 24363
- SHA-256：`16e3989cd919de387cee12e4165d1d581971fb5571b0547159032eabfa862ca2`

- L4 [unknown] [

> **类型：** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/power/p01-ldo.md`](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L4 [unknown] [.md`](../design-cards/power/p01-ldo.md)（PWR-01）；多源/反灌组合入口见 [`../module-cards.md`](../module-cards.md) → `references/module-cards.md` (ok)

### `references/examples/x03-mcu-min.md`

- 标题：裸 MCU 最小系统：去耦、复位、BOOT 与调试口的局部约束
- 行/字符/字节：251 / 12191 / 23806
- SHA-256：`a551f7f4ac58e2eca1580ffb2f7933c45262d525b7e23cc9deb68387b43d03bb`

- L4 [unknown] [
> **类型：** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/mcu/m01-bare-mcu.md`](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L4 [unknown] [md`](../design-cards/mcu/m01-bare-mcu.md)（MCU-01）；复位见 [`m03-reset-supervisor.md`](../design-cards/mcu/m03-reset-supervisor.md) → `references/design-cards/mcu/m03-reset-supervisor.md` (ok)
- L4 [unknown] [isor.md`](../design-cards/mcu/m03-reset-supervisor.md)，启动脚见 [`m04-boot-strap.md`](../design-cards/mcu/m04-boot-strap.md) → `references/design-cards/mcu/m04-boot-strap.md` (ok)
- L68 [unknown] [部画，不用网名拉到远处再拉回。
- **时钟块**：HSE/LSE 晶体与负载电容作为一个局部块，紧邻时钟脚（计算与布局见 [`x04-crystal.md`](x04-crystal.md) → `references/examples/x04-crystal.md` (ok)

### `references/examples/x04-crystal.md`

- 标题：晶体振荡器：16 MHz HSE 的负载电容、负阻与驱动电平
- 行/字符/字节：277 / 12255 / 22675
- SHA-256：`109b326d75cecc5aef88dc4c5ec624ff681acf8f0aebf90b0a61d6a3f2603f4c`

- L4 [unknown] [
> **类型：** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/mcu/m05-crystal.md`](../design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L4 [unknown] [stal.md`](../design-cards/mcu/m05-crystal.md)（MCU-05）；最小系统入口见 [`m01-bare-mcu.md`](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)

### `references/examples/x05-i2c.md`

- 标题：范例：I²C 传感器接口（以温湿度为例；上拉、总线电容与 ESD）
- 行/字符/字节：210 / 9897 / 19397
- SHA-256：`64b5abff488e5ed4beebf8981e65e841e2804f66b53da51330d498b44d5beab2`

- L3 [example] [
> **范围：** 本范例只覆盖 I²C 总线层（上拉、总线电容、ESD、摆放），不含温湿度测量原理、寄存器、校准或传感器选型；这些见 [常用硬件 A2/A5](../common-hardware/a-environment.md) → `references/common-hardware/a-environment.md` (ok)
- L6 [unknown] [ **类型：** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/interfaces/i01-i2c.md`](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L6 [unknown] [s/interfaces/i01-i2c.md)（I²C 总线）、[`../design-cards/interfaces/i02-i2c-buffer.md`](../design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)

### `references/examples/x06-rs485.md`

- 标题：范例：RS-485 半双工总线（端接、偏置与保护）
- 行/字符/字节：206 / 8941 / 18756
- SHA-256：`bf099ecbe2a2b7e008ee72152daaf4216750b8ddd906f4bebb806ebf368299b8`

- L4 [unknown] [*类型：** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/interfaces/i07-rs485.md`](../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)

### `references/examples/x07-can.md`

- 标题：范例：CAN 总线节点（端接、支线与保护）
- 行/字符/字节：200 / 8242 / 16837
- SHA-256：`16203903633b091ee90debdd6f5c9bf963c717aa26fbf41ebc557fed9ddca876`

- L4 [unknown] [ **类型：** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/interfaces/i08-can.md`](../design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)

### `references/examples/x08-usbc.md`

- 标题：范例：USB-C 受电端（CC 下拉、VBUS 与数据保护）
- 行/字符/字节：215 / 9990 / 19170
- SHA-256：`9de50c3783267699e030ea87eca5a7aed2747b3887156d28db0c94dc22011ebd`

- L4 [unknown] [** 分析范例（未在 EDA 中执行）
> **关联设计卡：** [`../design-cards/interfaces/i10-usbc-data.md`](../design-cards/interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)
- L4 [unknown] [interfaces/i10-usbc-data.md)（USB-C 数据）、[`../design-cards/power/p12-usbc-sink.md`](../design-cards/power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)

### `references/examples/x09-current-sense.md`

- 标题：低侧 Kelvin 电流采样局部范例
- 行/字符/字节：189 / 8157 / 17224
- SHA-256：`f1c050cf0c7a3cc2e7505037525fafa51299b1af0f24f7a2fcd185cd67318a4f`

- L4 [unknown] [分析范例（未在 EDA 中执行）**
> **关联设计卡：** [`../design-cards/analog/a06-low-side-sense.md`](../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L4 [unknown] [side-sense.md)（ANA-06）；高侧/在线对照见 [`../design-cards/analog/a07-high-side-sense.md`](../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L188 [unknown] [C33、SC18、PL14、PL21、PL22、RT07、RT21、RT22、MF15、MF29；规则入口见 [`../schematic-layout.md`](../schematic-layout.md) → `references/schematic-layout.md` (ok)
- L188 [unknown] [`../schematic-layout.md`](../schematic-layout.md)、[`../pcb-placement-details.md`](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L188 [unknown] [placement-details.md`](../pcb-placement-details.md)、[`../pcb-routing-details.md`](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)

### `references/examples/x10-4-20ma.md`

- 标题：4–20 mA 两线制接收局部范例
- 行/字符/字节：219 / 9721 / 19727
- SHA-256：`3eea5228be500eb9e9d47cfbd9fc3ebebd84dce73bcf062442b76940630651ea`

- L4 [unknown] [
> **类型：分析范例（未在 EDA 中执行）**
> **关联设计卡：** [`../design-cards/analog/a08-4-20ma.md`](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L4 [unknown] [ds/analog/a08-4-20ma.md)（ANA-08）；差分前端见 [`../design-cards/analog/a03-diff-amp.md`](../design-cards/analog/a03-diff-amp.md) → `references/design-cards/analog/a03-diff-amp.md` (ok)
- L4 [unknown] [ards/analog/a03-diff-amp.md)，ADC 驱动见 [`../design-cards/analog/a04-adc-driver.md`](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L218 [unknown] [读、compliance 台架、4/20 mA 校准、隔离耐压、浪涌、HART、EMC、长期漂移。规则入口见 [`../schematic-layout.md`](../schematic-layout.md) → `references/schematic-layout.md` (ok)
- L218 [unknown] [`../schematic-layout.md`](../schematic-layout.md)、[`../pcb-placement-details.md`](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L218 [unknown] [placement-details.md`](../pcb-placement-details.md)、[`../pcb-routing-details.md`](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L218 [unknown] [b-routing-details.md`](../pcb-routing-details.md)、[`../manufacturing-details.md`](../manufacturing-details.md) → `references/manufacturing-details.md` (ok)

### `references/examples/x11-h-bridge.md`

- 标题：H 桥功率级局部范例（离线布局草案）
- 行/字符/字节：239 / 11746 / 23563
- SHA-256：`40840772c15c3734f8794a41101d9783211ffe2637732b96d6e23cb44960081e`

- L4 [unknown] [**类型：离线布局草案（未在 EDA 中执行）**
> **关联设计卡：** [`../design-cards/drive/d05-h-bridge.md`](../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L4 [unknown] [drive/d05-h-bridge.md)（DRV-05）；半桥自举见 [`../design-cards/drive/d04-half-bridge.md`](../design-cards/drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L4 [unknown] [ds/drive/d04-half-bridge.md)，低侧/高侧开关对照见 [`../design-cards/drive/d01-low-side.md`](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L4 [unknown] [/design-cards/drive/d01-low-side.md) 与 [`../design-cards/drive/d02-high-side.md`](../design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L238 [unknown] [双脉冲/栅极波形、死区实测、自举 UVLO、回生与母线过压、热与 SOA、EMC、短路/堵转保护。规则入口见 [`../schematic-layout.md`](../schematic-layout.md) → `references/schematic-layout.md` (ok)
- L238 [unknown] [`../schematic-layout.md`](../schematic-layout.md)、[`../pcb-placement-details.md`](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L238 [unknown] [placement-details.md`](../pcb-placement-details.md)、[`../pcb-routing-details.md`](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L238 [unknown] [b-routing-details.md`](../pcb-routing-details.md)、[`../manufacturing-details.md`](../manufacturing-details.md) → `references/manufacturing-details.md` (ok)

### `references/examples/x12-antenna.md`

- 标题：Wi-Fi 模组与天线接口局部范例（离线布局草案）
- 行/字符/字节：216 / 10539 / 21466
- SHA-256：`39d7f1197777aca0f4a959e47823dee45d0a3871b1c378b64b38d0e5445b0592`

- L4 [unknown] [型：离线布局草案（未在 EDA 中执行）**
> **关联设计卡：** [`../design-cards/wireless/w01-wifi-ble.md`](../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L4 [unknown] [rds/wireless/w01-wifi-ble.md)（RF-01）与 [`../design-cards/wireless/w02-antenna.md`](../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L4 [unknown] [wireless/w02-antenna.md)（RF-02）；模组最小系统见 [`../design-cards/mcu/m02-module-mcu.md`](../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L215 [unknown] [ 采样窗测试、VNA S11（`MINI-1U`）、OTA/吞吐、装壳/装电池复测、EMC/法规。规则入口见 [`../schematic-layout.md`](../schematic-layout.md) → `references/schematic-layout.md` (ok)
- L215 [unknown] [`../schematic-layout.md`](../schematic-layout.md)、[`../pcb-placement-details.md`](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L215 [unknown] [placement-details.md`](../pcb-placement-details.md)、[`../pcb-routing-details.md`](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L215 [unknown] [b-routing-details.md`](../pcb-routing-details.md)、[`../manufacturing-details.md`](../manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L215 [unknown] [../manufacturing-details.md`](../manufacturing-details.md)、[`../module-cards.md`](../module-cards.md) → `references/module-cards.md` (ok)

### `references/execution-efficiency.md`

- 标题：批量执行与提速
- 行/字符/字节：61 / 2258 / 4486
- SHA-256：`5cd424a7adcef6a175056c249428df9c88c707c7489edc16dcd241bea8d5a06b`

### `references/failures/README.md`

- 标题：故障与反例库
- 行/字符/字节：60 / 4548 / 6008
- SHA-256：`13ad0685033aa2b4935606a65c27c4c4356931a371c917eb735d6e2af52722cc`

- L8 [unknown] [01 | ODrive 电流采样寄生电阻导致比例误差 | A | [P04, ANA-S06] | [f01-odrive-sense-parasitic.md](f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L9 [unknown] [ |
| F02 | 两节 AA 经 LDO 维持 3.3V 失败 | C | [PWR-S03, PWR-S04] | [f02-two-aa-ldo.md](f02-two-aa-ldo.md) → `references/failures/f02-two-aa-ldo.md` (ok)
- L10 [unknown] [| F03 | ESP32 启动 strap 被外围拖偏 | B | [MCU-S04, MCU-S09, P04] | [f03-esp32-strap.md](f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L11 [unknown] [.md) |
| F04 | STM32 VCAP/特殊供电脚遗漏 | B | [MCU-S01, MCU-S02] | [f04-stm32-vcap.md](f04-stm32-vcap.md) → `references/failures/f04-stm32-vcap.md` (ok)
- L12 [unknown] [| 晶体负载/ESR 不适配导致不起振 | B | [MCU-S02, MCU-S01, MCU-S04] | [f05-crystal-load-esr.md](f05-crystal-load-esr.md) → `references/failures/f05-crystal-load-esr.md` (ok)
- L13 [unknown] [-load-esr.md) |
| F06 | I2C 上拉过强/过弱 | B | [IF-S01, IF-S02] | [f06-i2c-pullup.md](f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L14 [unknown] [ullup.md) |
| F07 | RS-485 端接/偏置位置错误 | B | [IF-S03] | [f07-rs485-termination.md](f07-rs485-termination.md) → `references/failures/f07-rs485-termination.md` (ok)
- L15 [unknown] [ermination.md) |
| F08 | CAN 端接过多/共模问题 | B | [IF-S04] | [f08-can-termination.md](f08-can-termination.md) → `references/failures/f08-can-termination.md` (ok)
- L16 [unknown] [ |
| F09 | USB-C CC 电阻缺失/错误 | B | [PWR-S16, PWR-S15, PWR-S17] | [f09-usbc-cc.md](f09-usbc-cc.md) → `references/failures/f09-usbc-cc.md` (ok)
- L17 [unknown] [d) |
| F10 | Buck 反馈/输入电容布局导致噪声 | B | [PWR-S01, G03] | [f10-buck-loop-layout.md](f10-buck-loop-layout.md) → `references/failures/f10-buck-loop-layout.md` (ok)
- L18 [unknown] [ut.md) |
| F11 | MLCC 直流偏压导致有效容量不足 | B | [PWR-S01, PWR-S04] | [f11-mlcc-bias.md](f11-mlcc-bias.md) → `references/failures/f11-mlcc-bias.md` (ok)
- L19 [unknown] [d) |
| F12 | 电感饱和导致过流/过热 | B | [PWR-S01, PWR-S09] | [f12-inductor-saturation.md](f12-inductor-saturation.md) → `references/failures/f12-inductor-saturation.md` (ok)
- L20 [unknown] [.md) |
| F13 | MOSFET SOA/热插拔浪涌失效 | B | [PWR-S11, DRV-S05] | [f13-mosfet-soa.md](f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L21 [unknown] [
| F14 | 继电器线圈无续流/释放慢 | B | [DRV-S04, DRV-S09, DRV-S10] | [f14-relay-flyback.md](f14-relay-flyback.md) → `references/failures/f14-relay-flyback.md` (ok)
- L22 [unknown] [(f14-relay-flyback.md) |
| F15 | FPC Pin-1/接触面反向 | C | [P07] | [f15-fpc-pin1.md](f15-fpc-pin1.md) → `references/failures/f15-fpc-pin1.md` (ok)
- L23 [background] [n1.md) |
| F16 | 铺铜后参考路径/连通性变化 | B | [T01, G05] | [f16-copper-pour-reference.md](f16-copper-pour-reference.md) → `references/failures/f16-copper-pour-reference.md` (ok)
- L24 [background] [ence.md) |
| F17 | 差分等长但跨参考平面分割 | B | [G06, G05] | [f17-diff-split-reference.md](f17-diff-split-reference.md) → `references/failures/f17-diff-split-reference.md` (ok)
- L25 [unknown] [
| F18 | 天线净空/外壳导致失谐 | B | [RF-S01, RF-S02, RF-S04] | [f18-antenna-enclosure.md](f18-antenna-enclosure.md) → `references/failures/f18-antenna-enclosure.md` (ok)
- L26 [unknown] [ 版本不一致 | B | [MFG-S03, MFG-S05, MFG-S06, MFG-S08, MFG-S16] | [f19-bom-cpl-dnp.md](f19-bom-cpl-dnp.md) → `references/failures/f19-bom-cpl-dnp.md` (ok)
- L27 [unknown] [但 SMT 不可贴 | B | [MFG-S02, MFG-S04, MFG-S10, MFG-S15] | [f20-lcsc-stock-vs-smt.md](f20-lcsc-stock-vs-smt.md) → `references/failures/f20-lcsc-stock-vs-smt.md` (ok)
- L28 [unknown] [-smt.md) |
| F21 | 焊接完成但未烧录/未功能测试 | B | [MFG-S16] | [f21-soldered-not-tested.md](f21-soldered-not-tested.md) → `references/failures/f21-soldered-not-tested.md` (ok)
- L29 [unknown] [ted.md) |
| F22 | ADC 建立时间/采样误差 | B | [ANA-S02, ANA-S03] | [f22-adc-settling.md](f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L30 [unknown] [T_VCC 反灌/LDO 被抬压） | B/C | [MCU-S07, MCU-S01, D-S07] | [f23-debugger-backpower.md](f23-debugger-backpower.md) → `references/failures/f23-debugger-backpower.md` (ok)
- L31 [unknown] [拉错（推挽复位 IC/电容/漏电） | B/C | [MCU-S01, MCU-S06] | [f24-nrst-pulled-by-peripheral.md](f24-nrst-pulled-by-peripheral.md) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok)
- L32 [unknown] [| 无线发射导致系统复位（burst/源阻抗） | B | [RF-S03, MCU-S09] | [f25-radio-tx-resets-system.md](f25-radio-tx-resets-system.md) → `references/failures/f25-radio-tx-resets-system.md` (ok)
- L33 [unknown] [电机启动干扰模拟采集（地弹/耦合/混叠） | B | [ANA-S06, ANA-S14] | [f26-motor-start-corrupts-adc.md](f26-motor-start-corrupts-adc.md) → `references/failures/f26-motor-start-corrupts-adc.md` (ok)
- L34 [unknown] [SB 接入后地环路或电源冲突 | B | [PWR-S06, IF-S11] | [f27-usb-ground-loop-source-conflict.md](f27-usb-ground-loop-source-conflict.md) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok)
- L35 [unknown] [F28 | I²C 设备掉电后拖死总线 | B | [IF-S01 §3.1.16] | [f28-i2c-unpowered-device-lockup.md](f28-i2c-unpowered-device-lockup.md) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok)
- L36 [unknown] [| F29 | SPI 写正常、读不稳定 | B | [IF-S08, IF-S03] | [f29-spi-write-ok-read-unstable.md](f29-spi-write-ok-read-unstable.md) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok)
- L37 [unknown] [
| F30 | GPIO 在上电阶段误触发负载 | B | [MCU-S01, MCU-S04] | [f30-gpio-power-on-glitch.md](f30-gpio-power-on-glitch.md) → `references/failures/f30-gpio-power-on-glitch.md` (ok)
- L38 [unknown] [selection/replacement-classes] | [f31-replacement-passes-typical-fails-corner.md](f31-replacement-passes-typical-fails-corner.md) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok)
- L39 [unknown] [性能下降 | B | [RF-S01, RF-S02, thermal] | [f32-enclosure-degrades-rf-and-thermal.md](f32-enclosure-degrades-rf-and-thermal.md) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok)
- L40 [unknown] [| [ANA-S06, simulation-measurement §5] | [f33-measurement-caused-wrong-rework.md](f33-measurement-caused-wrong-rework.md) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok)

### `references/failures/f01-odrive-sense-parasitic.md`

- 标题：F01 ODrive 电流采样寄生电阻导致比例误差
- 行/字符/字节：95 / 4440 / 9618
- SHA-256：`893f0c71e73a2e3ddc10a6dac0d113650353e487b0635b2b3a0834d67f806243`

- L15 [example] [功率电流与感测线可能共用铜皮的布局。高侧/在线采样、集成分流电阻的器件、四端分流器不直接套用。
>
> **关联：** 设计卡 [ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L15 [example] [设计卡 [ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md)、[ANA-07 高侧电流采样](../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L15 [example] [07 高侧电流采样](../design-cards/analog/a07-high-side-sense.md)；范例 [x09 低侧 Kelvin 电流采样](../examples/x09-current-sense.md) → `references/examples/x09-current-sense.md` (ok)
- L15 [example] [de-sense.md)；范例 [x09 低侧 Kelvin 电流采样](../examples/x09-current-sense.md)；检查项 [SC36](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [流采样](../examples/x09-current-sense.md)；检查项 [SC36](../schematic-details.md)、[PL14](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L15 [example] [项 [SC36](../schematic-details.md)、[PL14](../pcb-placement-details.md)、[RT07、RT21](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L15 [example] [[PL14](../pcb-placement-details.md)、[RT07、RT21](../pcb-routing-details.md)、[DM19](../domain-design-details.md) → `references/domain-design-details.md` (ok)
- L77 [unknown] [从分流器焊盘内侧的专用取样点引出，功率电流从焊盘外侧进出；两条 sense 线成对走、不穿过功率铜；放大器 `R_G` 的地单点回到分流器低端。对应 [RT07](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L77 [unknown] [e 线成对走、不穿过功率铜；放大器 `R_G` 的地单点回到分流器低端。对应 [RT07](../pcb-routing-details.md) 与 [PL14](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)

### `references/failures/f02-two-aa-ldo.md`

- 标题：F02 两节 AA 经 LDO 维持 3.3V 失败
- 行/字符/字节：97 / 4469 / 9334
- SHA-256：`a4cd71fba8bf9d84aec6bb0a08fab771e62d6255dfcccfe06c2f30a2963beb42`

- L15 [example] [输入、用线性 LDO 稳压的拓扑。三节 AA、单节锂电、升压/升降压、以及输出低于输入的场景不适用。
>
> **关联：** 设计卡 [PWR-01 LDO](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L15 [example] [
> **关联：** 设计卡 [PWR-01 LDO](../design-cards/power/p01-ldo.md)、[PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L15 [example] [o.md)、[PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md)、[PWR-03 Boost](../design-cards/power/p03-boost.md) → `references/design-cards/power/p03-boost.md` (ok)
- L15 [example] [uck-boost.md)、[PWR-03 Boost](../design-cards/power/p03-boost.md)；范例 [x02 LDO 热设计](../examples/x02-ldo-thermal.md) → `references/examples/x02-ldo-thermal.md` (ok)
- L15 [example] [3-boost.md)；范例 [x02 LDO 热设计](../examples/x02-ldo-thermal.md)；检查项 [SC09、SC12、SC13](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [mples/x02-ldo-thermal.md)；检查项 [SC09、SC12、SC13](../schematic-details.md)，以及 [DM10](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f03-esp32-strap.md`

- 标题：F03 ESP32 启动 strap 被外围拖偏
- 行/字符/字节：99 / 4459 / 8976
- SHA-256：`c7b91f68f47e9b1bc4050ccb56568e46c80663afadc4ab65fbe7475fc54f9897`

- L15 [example] [不同，必须查对应系列的检查表；本案例不能把 3 ms 或“GPIO9 上拉”直接套到其他系列。
>
> **关联：** 设计卡 [MCU-04 启动与配置脚](../design-cards/mcu/m04-boot-strap.md) → `references/design-cards/mcu/m04-boot-strap.md` (ok)
- L15 [example] [*关联：** 设计卡 [MCU-04 启动与配置脚](../design-cards/mcu/m04-boot-strap.md)、[MCU-02 模组最小系统](../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L15 [example] [trap.md)、[MCU-02 模组最小系统](../design-cards/mcu/m02-module-mcu.md)；范例 [x03 MCU 最小系统](../examples/x03-mcu-min.md) → `references/examples/x03-mcu-min.md` (ok)
- L15 [example] [e-mcu.md)；范例 [x03 MCU 最小系统](../examples/x03-mcu-min.md)；检查项 [SC20、SC19、SC25、SC21](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [ples/x03-mcu-min.md)；检查项 [SC20、SC19、SC25、SC21](../schematic-details.md)，以及 [DM01](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f04-stm32-vcap.md`

- 标题：F04 STM32 VCAP/特殊供电脚遗漏
- 行/字符/字节：95 / 4111 / 8061
- SHA-256：`b5b5619140e1502ca9c787cbfc3a64be7ed9426bce00efce236d121b5af42f2f`

- L15 [example] [、数量和电容值随型号/封装变化，必须查该型号数据手册与 AN4488 的对应封装说明。
>
> **关联：** 设计卡 [MCU-01 裸 MCU 最小系统](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L15 [example] [** 设计卡 [MCU-01 裸 MCU 最小系统](../design-cards/mcu/m01-bare-mcu.md)；范例 [x03 MCU 最小系统](../examples/x03-mcu-min.md) → `references/examples/x03-mcu-min.md` (ok)
- L15 [example] [e-mcu.md)；范例 [x03 MCU 最小系统](../examples/x03-mcu-min.md)；检查项 [SC04、SC03、SC19、PL17](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [ples/x03-mcu-min.md)；检查项 [SC04、SC03、SC19、PL17](../schematic-details.md)，以及 [DM01](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f05-crystal-load-esr.md`

- 标题：F05 晶体负载/ESR 不适配导致不起振
- 行/字符/字节：113 / 4638 / 8915
- SHA-256：`c6b66ebdcef2d8aa38b13941ebe27438c8ce4acfb35967d567c82b84b6b4a2af`

- L15 [example] [t_max、内部反馈电阻、允许的 CL/ESR 范围随 MCU 型号变化，必须查该型号数据手册。
>
> **关联：** 设计卡 [MCU-05 晶体振荡器](../design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L15 [example] [>
> **关联：** 设计卡 [MCU-05 晶体振荡器](../design-cards/mcu/m05-crystal.md)、[MCU-06 外部时钟](../design-cards/mcu/m06-external-clock.md) → `references/design-cards/mcu/m06-external-clock.md` (ok)
- L15 [example] [-crystal.md)、[MCU-06 外部时钟](../design-cards/mcu/m06-external-clock.md)；范例 [x04 晶体](../examples/x04-crystal.md) → `references/examples/x04-crystal.md` (ok)
- L15 [example] [6-external-clock.md)；范例 [x04 晶体](../examples/x04-crystal.md)；检查项 [SC23、PL19、RT24](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [/examples/x04-crystal.md)；检查项 [SC23、PL19、RT24](../schematic-details.md)，以及 [DM01](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f06-i2c-pullup.md`

- 标题：F06 I2C 上拉过强/过弱
- 行/字符/字节：97 / 4257 / 7962
- SHA-256：`f4d018e6273dcf707f36f1dbc1c9fe043e56690b83597f214d18dd57d3780551`

- L15 [example] [Bus 的阈值与时限另有规范。上拉值必须按实际总线电容、供电和从机能力重算，不能套一个固定阻值。
>
> **关联：** 设计卡 [IF-01 I²C 总线](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L15 [example] [ **关联：** 设计卡 [IF-01 I²C 总线](../design-cards/interfaces/i01-i2c.md)、[IF-02 I²C 缓冲](../design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L15 [example] [.md)、[IF-02 I²C 缓冲](../design-cards/interfaces/i02-i2c-buffer.md)；范例 [x05 I²C 接口](../examples/x05-i2c.md) → `references/examples/x05-i2c.md` (ok)
- L15 [example] [-i2c-buffer.md)；范例 [x05 I²C 接口](../examples/x05-i2c.md)；检查项 [SC27、SC26、PL15、RT19](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [examples/x05-i2c.md)；检查项 [SC27、SC26、PL15、RT19](../schematic-details.md)，以及 [DM30](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f07-rs485-termination.md`

- 标题：F07 RS-485 端接/偏置位置错误
- 行/字符/字节：99 / 3817 / 8279
- SHA-256：`9fce5e30c2ddef411185924919315685d0e51057d5aee2d8bee5bcb76af78e11`

- L15 [example] [2 只在最远端端接一个，不能照搬“两端各一个”；不同电缆 `Zo`、不同速率/共模等级需要重算。
>
> **关联：** 设计卡 [IF-07 RS-485](../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L15 [example] [关联：** 设计卡 [IF-07 RS-485](../design-cards/interfaces/i07-rs485.md)；范例 [x06 RS-485](../examples/x06-rs485.md) → `references/examples/x06-rs485.md` (ok)
- L15 [example] [s485.md)；范例 [x06 RS-485](../examples/x06-rs485.md)；检查项 [SC32、SC15、SC38、PL15、RT18](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [-rs485.md)；检查项 [SC32、SC15、SC38、PL15、RT18](../schematic-details.md)，以及 [DM25、DM27](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f08-can-termination.md`

- 标题：F08 CAN 端接过多/共模问题
- 行/字符/字节：101 / 3937 / 8241
- SHA-256：`1392a59355cc8d748ce2ed713022379d5829787c5476485df731f60a40952e46`

- L15 [example] [CAN FD）。CAN FD、SIC 收发器、更高共模/更高 ESD 等级的器件需要按新资料重新分析。
>
> **关联：** 设计卡 [IF-08 CAN](../design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L15 [example] [
>
> **关联：** 设计卡 [IF-08 CAN](../design-cards/interfaces/i08-can.md)；范例 [x07 CAN](../examples/x07-can.md) → `references/examples/x07-can.md` (ok)
- L15 [example] [s/i08-can.md)；范例 [x07 CAN](../examples/x07-can.md)；检查项 [SC32、SC15、SC38、PL15、RT18](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [07-can.md)；检查项 [SC32、SC15、SC38、PL15、RT18](../schematic-details.md)，以及 [DM25、DM27](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f09-usbc-cc.md`

- 标题：F09 USB-C CC 电阻缺失/错误
- 行/字符/字节：116 / 5332 / 9489
- SHA-256：`1b65f8c4344d5f80960103f3e9dd0471f9c2f8e319e953b2925209345ca258b7`

- L15 [example] [ 线缆的高级行为不在本案例范围；不同连接器/不同板版的 CC 网络必须分别核对。
>
> **关联：** 设计卡 [PWR-12 USB-C 5V Sink](../design-cards/power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L15 [example] [2 USB-C 5V Sink](../design-cards/power/p12-usbc-sink.md)、[PWR-13 USB-C 5V Source](../design-cards/power/p13-usbc-source.md) → `references/design-cards/power/p13-usbc-source.md` (ok)
- L15 [example] [WR-13 USB-C 5V Source](../design-cards/power/p13-usbc-source.md)、[IF-10 USB-C 数据](../design-cards/interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)
- L15 [example] [、[IF-10 USB-C 数据](../design-cards/interfaces/i10-usbc-data.md)；范例 [x08 USB-C 受电端](../examples/x08-usbc.md) → `references/examples/x08-usbc.md` (ok)
- L15 [example] [10-usbc-data.md)；范例 [x08 USB-C 受电端](../examples/x08-usbc.md)；检查项 [SC30、SC31、PL15](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [(../examples/x08-usbc.md)；检查项 [SC30、SC31、PL15](../schematic-details.md)，以及 [DM29](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f10-buck-loop-layout.md`

- 标题：F10 Buck 反馈/输入电容布局导致噪声
- 行/字符/字节：97 / 3882 / 8151
- SHA-256：`89c17e1077b5ce0443f0bad2e3e93e8b9701313224179801d0e727c55fbc1e88`

- L15 [example] [st、反相拓扑的脉动回路位置不同，不能照搬；外补偿/电流模式/多相的控制环细节要按具体控制器手册。
>
> **关联：** 设计卡 [PWR-02 Buck](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L15 [example] [> **关联：** 设计卡 [PWR-02 Buck](../design-cards/power/p02-buck.md)；范例 [x01 Buck 功率回路](../examples/x01-buck-loop.md) → `references/examples/x01-buck-loop.md` (ok)
- L15 [example] [[x01 Buck 功率回路](../examples/x01-buck-loop.md)；检查项 [SC13、PL09、PL10、PL11、PL12、RT04](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [p.md)；检查项 [SC13、PL09、PL10、PL11、PL12、RT04](../schematic-details.md)，以及 [DM09、DM10](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f11-mlcc-bias.md`

- 标题：F11 MLCC 直流偏压导致有效容量不足
- 行/字符/字节：95 / 3831 / 8133
- SHA-256：`e012e03a489b2511c0cb8982c94e7d2f8433db98fa19270b8d59164d50b69ba5`

- L15 [example] [同；不同介质（X7R/X5R/C0G/Y5V）、封装、耐压的曲线差异很大，不能用一个系数套所有料号。
>
> **关联：** 设计卡 [PWR-01 LDO](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L15 [example] [号。
>
> **关联：** 设计卡 [PWR-01 LDO](../design-cards/power/p01-ldo.md)、[PWR-02 Buck](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L15 [example] [wer/p01-ldo.md)、[PWR-02 Buck](../design-cards/power/p02-buck.md)；范例 [x02 LDO 热设计](../examples/x02-ldo-thermal.md) → `references/examples/x02-ldo-thermal.md` (ok)
- L15 [example] [wer/p02-buck.md)；范例 [x02 LDO 热设计](../examples/x02-ldo-thermal.md)、[x01 Buck 功率回路](../examples/x01-buck-loop.md) → `references/examples/x01-buck-loop.md` (ok)
- L15 [example] [ermal.md)、[x01 Buck 功率回路](../examples/x01-buck-loop.md)；检查项 [SC12、SC13、PL10、PL17](../schematic-details.md) → `references/schematic-details.md` (ok)
- L15 [example] [es/x01-buck-loop.md)；检查项 [SC12、SC13、PL10、PL17](../schematic-details.md)，以及 [DM10](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f12-inductor-saturation.md`

- 标题：F12 电感饱和导致过流/过热
- 行/字符/字节：89 / 3998 / 8767
- SHA-256：`b1b0859c81a0439def045150ae642a2d4ac51c88b4f6cde275c79cf5542cbf64`

- L13 [example] [本次作者复现的板级失效记录。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [PWR-02 Buck](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L13 [example] [成通用规则。
> **关联：** [PWR-02 Buck](../design-cards/power/p02-buck.md)、[PWR-03 Boost](../design-cards/power/p03-boost.md) → `references/design-cards/power/p03-boost.md` (ok)
- L13 [example] [2-buck.md)、[PWR-03 Boost](../design-cards/power/p03-boost.md)、[PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L13 [example] [)、[PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md)；范例 [x01-buck-loop](../examples/x01-buck-loop.md) → `references/examples/x01-buck-loop.md` (ok)

### `references/failures/f13-mosfet-soa.md`

- 标题：F13 MOSFET SOA/热插拔浪涌失效
- 行/字符/字节：85 / 4189 / 8792
- SHA-256：`8fb7afc3467d5e6c5b305b55f5a639c9146ec84569ff1dca91366b267075cb70`

- L13 [unknown] [复现的失效管与波形。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [PWR-10 热插拔与浪涌限制](../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L13 [unknown] [
> **关联：** [PWR-10 热插拔与浪涌限制](../design-cards/power/p10-hot-swap.md)、[DRV-01 低侧开关](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)

### `references/failures/f14-relay-flyback.md`

- 标题：F14 继电器线圈无续流/释放慢
- 行/字符/字节：84 / 4216 / 9750
- SHA-256：`52a892c567b20ecb3d751baf249cea2dcd1d823b9e7820cc6bb9a1c288c269a6`

- L13 [unknown] [作者复现的继电器失效记录。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [DRV-03 继电器驱动](../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)

### `references/failures/f15-fpc-pin1.md`

- 标题：F15 FPC Pin-1/接触面反向
- 行/字符/字节：84 / 3545 / 8118
- SHA-256：`b8e145537b512a33e6c1226c0f8141a2fbfc72112018170879d109ef8015fd93`

- L13 [unknown] [写成已证实根因。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [RF-05 SPI TFT 与背光](../design-cards/wireless/w05-display.md) → `references/design-cards/wireless/w05-display.md` (ok)
- L55 [background] [ntinuity。

## 根因证据

- **项目资料提示（C，P07 入口）。** P07 在本轮是通过 [design-experience.md](../design-experience.md) → `references/design-experience.md` (ok)

### `references/failures/f16-copper-pour-reference.md`

- 标题：F16 铺铜后参考路径/连通性变化
- 行/字符/字节：87 / 3623 / 8364
- SHA-256：`16c22de86c47a2bb0246337e64efa87bd290bbe8801ebaafb9eb31a438a66c93`

- L13 [example] [路径劣化属于工程推断（C）。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [PWR-02 Buck](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L13 [example] [则。
> **关联：** [PWR-02 Buck](../design-cards/power/p02-buck.md)；范例 [x01-buck-loop](../examples/x01-buck-loop.md) → `references/examples/x01-buck-loop.md` (ok)
- L56 [unknown] [ EMC 测试；只有实际板才能证明影响。

## 根因证据

- **工具行为（B，T01 入口）。** 据 [design-experience.md](../design-experience.md) → `references/design-experience.md` (ok)
- L57 [unknown] [范围，未记录页码；引用时以当前 KiCad 9 手册对应章节为准。
- **回流原则（B，G05 入口）。** 据 [design-experience.md](../design-experience.md) → `references/design-experience.md` (ok)

### `references/failures/f17-diff-split-reference.md`

- 标题：F17 差分等长但跨参考平面分割
- 行/字符/字节：86 / 3513 / 8104
- SHA-256：`49d3ce9a657922699974cf790f64a48a7cf24d37454b520ad540d63b1ed44e99`

- L13 [example] [程推断（C），本次未复现。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [IF-09 USB 器件](../design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L13 [example] [：** [IF-09 USB 器件](../design-cards/interfaces/i09-usb-device.md)、[IF-11 Ethernet](../design-cards/interfaces/i11-ethernet.md) → `references/design-cards/interfaces/i11-ethernet.md` (ok)
- L13 [example] [ce.md)、[IF-11 Ethernet](../design-cards/interfaces/i11-ethernet.md)；范例 [x08-usbc](../examples/x08-usbc.md) → `references/examples/x08-usbc.md` (ok)
- L56 [background] [。不要只改固件均衡掩盖通道问题。

## 根因证据

- **原厂高速差分资料（B，G06 入口）。** 据 [design-experience.md](../design-experience.md) → `references/design-experience.md` (ok)
- L57 [background] [差分仍需要连续参考与回流，不能把“等长”当成信号完整性通过。
- **接地/回流原则（B，G05 入口）。** 据 [design-experience.md](../design-experience.md) → `references/design-experience.md` (ok)

### `references/failures/f18-antenna-enclosure.md`

- 标题：F18 天线净空/外壳导致失谐
- 行/字符/字节：87 / 4274 / 9389
- SHA-256：`acb77e2061246f89bfa838090424cd0cb55f30fdea2bc1f0c49cd5db6d229082`

- L13 [example] [1/暗室数据。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L13 [example] [** [RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md)、[RF-02 天线接口与匹配](../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L13 [example] [-ble.md)、[RF-02 天线接口与匹配](../design-cards/wireless/w02-antenna.md)、[RF-04 GNSS 模组](../design-cards/wireless/w04-gnss.md) → `references/design-cards/wireless/w04-gnss.md` (ok)
- L13 [example] [ntenna.md)、[RF-04 GNSS 模组](../design-cards/wireless/w04-gnss.md)；范例 [x12-antenna](../examples/x12-antenna.md) → `references/examples/x12-antenna.md` (ok)

### `references/failures/f19-bom-cpl-dnp.md`

- 标题：F19 BOM/坐标/DNP 版本不一致
- 行/字符/字节：89 / 4274 / 9163
- SHA-256：`e564bdc2fb2af29604146f2c5b9d9f4ee7266fc1f8aa00fe044b9c03838854b0`

- L13 [unknown] [ 一致；本次没有具体订单的错料记录。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [制造与首板细节](../manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L13 [unknown] [扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [制造与首板细节](../manufacturing-details.md)、[嘉立创业务衔接](../jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L13 [unknown] [*关联：** [制造与首板细节](../manufacturing-details.md)、[嘉立创业务衔接](../jlc-handoff.md)、[故障定位](../troubleshooting.md) → `references/troubleshooting.md` (ok)

### `references/failures/f20-lcsc-stock-vs-smt.md`

- 标题：F20 商城有货但 SMT 不可贴
- 行/字符/字节：87 / 3782 / 9008
- SHA-256：`7086016f23a6256819faf5f941a07404dad1336ea244556a6602fa1f4a38bc1f`

- L13 [unknown] [本次没有具体订单的可贴状态数据。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [立创商城选型与采购](../lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L13 [unknown] [适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [立创商城选型与采购](../lcsc-sourcing.md)、[嘉立创业务衔接](../jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L13 [unknown] [。
> **关联：** [立创商城选型与采购](../lcsc-sourcing.md)、[嘉立创业务衔接](../jlc-handoff.md)、[故障定位](../troubleshooting.md) → `references/troubleshooting.md` (ok)

### `references/failures/f21-soldered-not-tested.md`

- 标题：F21 焊接完成但未烧录/未功能测试
- 行/字符/字节：87 / 3375 / 7929
- SHA-256：`dc0b2efbbf1a8eec350ec2bfb537f9b78b316a76a08d97031045062373737723`

- L13 [unknown] [通过”；本次没有具体订单的交付记录。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [以原始用途验收](../product-acceptance.md) → `references/product-acceptance.md` (ok)
- L13 [unknown] [所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [以原始用途验收](../product-acceptance.md)、[嘉立创业务衔接](../jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L13 [unknown] [> **关联：** [以原始用途验收](../product-acceptance.md)、[嘉立创业务衔接](../jlc-handoff.md)、[故障定位](../troubleshooting.md) → `references/troubleshooting.md` (ok)
- L57 [unknown] [贴装选项”，不能据此声称任何工厂都不烧录；具体服务范围必须按当前订单确认。
- **验收分层（B）。** 本项目 [product-acceptance.md](../product-acceptance.md) → `references/product-acceptance.md` (ok)
- L58 [unknown] [据；端到端功能实测才证明所测版本和条件下原始场景发生。工厂 AOI/飞针/电测不能代替功能测试。
- **业务衔接（B）。** [jlc-handoff.md](../jlc-handoff.md) → `references/jlc-handoff.md` (ok)

### `references/failures/f22-adc-settling.md`

- 标题：F22 ADC 建立时间/采样误差
- 行/字符/字节：86 / 4739 / 9544
- SHA-256：`6e7c0f122dc6a85e912cdc1601834fd31cc732eadb2d63d07520bb2983358e5b`

- L13 [unknown] [只作为入口，不作为证据。
> **适用边界：** 只适用于所列拓扑、器件、板版和工况；不得推广成通用规则。
> **关联：** [ANA-01 电阻分压采样](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L13 [unknown] [*关联：** [ANA-01 电阻分压采样](../design-cards/analog/a01-divider.md)、[ANA-04 SAR ADC 驱动](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L13 [unknown] [-divider.md)、[ANA-04 SAR ADC 驱动](../design-cards/analog/a04-adc-driver.md)、[故障定位](../troubleshooting.md) → `references/troubleshooting.md` (ok)

### `references/failures/f23-debugger-backpower.md`

- 标题：F23 下载器连接后异常供电（T_VCC 反灌与 LDO 被抬压）
- 行/字符/字节：218 / 19264 / 39538
- SHA-256：`8c601f70e78e25295e7dcca16ac35647b216a4dd95f4cb0528ae73830786ebb3`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f23-debugger-backpower.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f23-debugger-backpower.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f23-debugger-backpower.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f23-debugger-backpower.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f23-debugger-backpower.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f23-debugger-backpower.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f23-debugger-backpower.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f23-debugger-backpower.md` (ok) #适用边界 ok
- L27 [unknown] [适用于 STLINK-V3SET；其他调试器、其他 MCU、其他 LDO 必须查各自手册。
>
> **关联：** 设计卡 [MCU-07 SWD/JTAG](../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L27 [unknown] [> **关联：** 设计卡 [MCU-07 SWD/JTAG](../design-cards/mcu/m07-swd-jtag.md)、[PWR-01 LDO](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L27 [unknown] [07-swd-jtag.md)、[PWR-01 LDO](../design-cards/power/p01-ldo.md)、[PWR-05 多源供电与电源路径](../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L27 [unknown] [.md)、[PWR-05 多源供电与电源路径](../design-cards/power/p05-power-mux.md)；专题 [B1 多路供电与电源切换](../engineering-deepdives/topics/b1-power-path-and-source-switching.md) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok)
- L27 [unknown] [power-path-and-source-switching.md) §2.3/§2.9/§7.3；组合问题 [module-integration §8.2](../module-integration.md) → `references/module-integration.md` (ok)
- L27 [unknown] [7.3；组合问题 [module-integration §8.2](../module-integration.md)；检查项 [SC11、SC24、SC40](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [e-integration.md)；检查项 [SC11、SC24、SC40](../schematic-details.md)；故障 [F09 USB-C CC](f09-usbc-cc.md) → `references/failures/f09-usbc-cc.md` (ok)
- L27 [unknown] [C40](../schematic-details.md)；故障 [F09 USB-C CC](f09-usbc-cc.md)、[F03 ESP32 strap](f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L86 [external_reference] [案例，不是真实用户故障；没有一块具体板、没有位号、没有波形。下面所有检查都是“应该怎么测”，不是“已经测到”。

> 配置边界：[ST UM2448官方手册](https://www.st.com.cn/resource/en/user_manual/um2448-stlinkv3set-debuggerprogrammer-for-stm8-and-stm32-stmicroelectronics.pdf) → `https://www.st.com.cn/resource/en/user_manual/um2448-stlinkv3set-debuggerprogrammer-for-stm8-and-stm32-stmicroelectronics.pdf` (external)

### `references/failures/f24-nrst-pulled-by-peripheral.md`

- 标题：F24 NRST 被外围推挽复位输出拖错
- 行/字符/字节：189 / 14520 / 28788
- SHA-256：`96f764a779c2d3da150c185c1a719323234c20f9a25b8bb8b69438d98f2a1c0e`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f24-nrst-pulled-by-peripheral.md` (ok) #适用边界 ok
- L27 [unknown] [ 复位网络本身被另一个有源驱动器拖住，修复对象是复位驱动拓扑，不是 strap 电平。
>
> **关联：** 设计卡 [MCU-01 裸 MCU 最小系统](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L27 [unknown] [：** 设计卡 [MCU-01 裸 MCU 最小系统](../design-cards/mcu/m01-bare-mcu.md)、[MCU-03 复位与电源监控](../design-cards/mcu/m03-reset-supervisor.md) → `references/design-cards/mcu/m03-reset-supervisor.md` (ok)
- L27 [unknown] [)、[MCU-03 复位与电源监控](../design-cards/mcu/m03-reset-supervisor.md)、[MCU-07 SWD/JTAG](../design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L27 [unknown] [sor.md)、[MCU-07 SWD/JTAG](../design-cards/mcu/m07-swd-jtag.md)；专题 [D1 接口组合后的隐藏约束](../engineering-deepdives/topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L27 [unknown] [gineering-deepdives/topics/d1-interface-combination-constraints.md)、[D3 连接器与板外通信](../engineering-deepdives/topics/d3-off-board-interfaces.md) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok)
- L27 [unknown] [ring-deepdives/topics/d3-off-board-interfaces.md)；故障对照 [F03 ESP32 启动 strap 被外围拖偏](f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L27 [unknown] [md)；故障对照 [F03 ESP32 启动 strap 被外围拖偏](f03-esp32-strap.md)；检查项 [SC22、SC19、SC24、SC25](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [SC22、SC19、SC24、SC25](../schematic-details.md)；组合案例 [module-integration.md §5/§13](../module-integration.md) → `references/module-integration.md` (ok)

### `references/failures/f25-radio-tx-resets-system.md`

- 标题：F25 Wi-Fi 发射瞬间复位（1S 锂电 + 3.3 V LDO）
- 行/字符/字节：195 / 15019 / 28716
- SHA-256：`5ae9f0632c0d4407c2dc309428cb9470c8f8af16411d59ed7eb794b771f13821`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f25-radio-tx-resets-system.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f25-radio-tx-resets-system.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f25-radio-tx-resets-system.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f25-radio-tx-resets-system.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f25-radio-tx-resets-system.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f25-radio-tx-resets-system.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f25-radio-tx-resets-system.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f25-radio-tx-resets-system.md` (ok) #适用边界 ok
- L27 [unknown] [V 跌落直接套到本案例；也不能把 350 mA 当成所有固件、速率和发射功率下的保证最大值。
>
> **关联：** [RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L27 [unknown] [** [RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md)、[RF-02 天线接口与匹配](../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L27 [unknown] [i-ble.md)、[RF-02 天线接口与匹配](../design-cards/wireless/w02-antenna.md)、[RF-03 蜂窝模组电源](../design-cards/wireless/w03-cellular.md) → `references/design-cards/wireless/w03-cellular.md` (ok)
- L27 [unknown] [a.md)、[RF-03 蜂窝模组电源](../design-cards/wireless/w03-cellular.md)（只借方法）、[PWR-01 LDO](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L27 [unknown] [ular.md)（只借方法）、[PWR-01 LDO](../design-cards/power/p01-ldo.md)、[PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L27 [unknown] [md)、[PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md)、[PWR-05 多源与电源路径](../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L27 [unknown] [-boost.md)、[PWR-05 多源与电源路径](../design-cards/power/p05-power-mux.md)、[PWR-06 线性充电](../design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L27 [unknown] [r-mux.md)、[PWR-06 线性充电](../design-cards/power/p06-linear-charger.md)、[PWR-10 热插拔](../design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L27 [unknown] [-charger.md)、[PWR-10 热插拔](../design-cards/power/p10-hot-swap.md)、[MCU-03 复位与电源监控](../design-cards/mcu/m03-reset-supervisor.md) → `references/design-cards/mcu/m03-reset-supervisor.md` (ok)
- L27 [unknown] [.md)、[MCU-03 复位与电源监控](../design-cards/mcu/m03-reset-supervisor.md)、[B4 电源动态与负载瞬态](../engineering-deepdives/topics/b4-power-dynamics.md) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok)
- L27 [unknown] [g-deepdives/topics/b4-power-dynamics.md)；检查项 [SC09、SC19、SC22、SC18、PL17、PL26、PL27](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [s.md)；检查项 [SC09、SC19、SC22、SC18、PL17、PL26、PL27](../schematic-details.md)，以及 [DM33](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f26-motor-start-corrupts-adc.md`

- 标题：F26 电机启动干扰模拟采集：地回流、磁场、电源跌落与采样混叠
- 行/字符/字节：175 / 15674 / 31479
- SHA-256：`0a5bd561220a9d7f8c6303789ca13a8c751e8b480b6d336df64488d9629bbd15`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f26-motor-start-corrupts-adc.md` (ok) #适用边界 ok
- L27 [unknown] [ EMC 不适用；BLDC 在线采样或高侧采样必须按 ANA-07/ANA-S14 重新分析。
>
> **关联：** 设计卡 [ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L27 [unknown] [计卡 [ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md)、[ANA-07 高侧/在线采样](../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L27 [unknown] [NA-07 高侧/在线采样](../design-cards/analog/a07-high-side-sense.md)、[ANA-04 SAR ADC 驱动](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L27 [unknown] [e.md)、[ANA-04 SAR ADC 驱动](../design-cards/analog/a04-adc-driver.md)、[ANA-05 电压基准](../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L27 [unknown] [adc-driver.md)、[ANA-05 电压基准](../design-cards/analog/a05-vref.md)；专题 [C2 接地、屏蔽与共模](../engineering-deepdives/topics/c2-grounding-shielding-common-mode.md) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok)
- L27 [unknown] [ineering-deepdives/topics/c2-grounding-shielding-common-mode.md)、[C4 测量方法本身造成的错误](../engineering-deepdives/topics/c4-measurement-artifacts.md) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok)
- L27 [unknown] [成的错误](../engineering-deepdives/topics/c4-measurement-artifacts.md)、[B4 电源动态与负载瞬态](../engineering-deepdives/topics/b4-power-dynamics.md) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok)
- L27 [unknown] [态与负载瞬态](../engineering-deepdives/topics/b4-power-dynamics.md)、[C1 从传感器到 ADC 的误差链](../engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md) → `references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` (ok)
- L27 [unknown] [eering-deepdives/topics/c1-sensor-to-adc-error-chain.md)；故障 [F01 ODrive 电流采样寄生电阻](f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L27 [unknown] [-chain.md)；故障 [F01 ODrive 电流采样寄生电阻](f01-odrive-sense-parasitic.md)、[F22 ADC 建立时间](f22-adc-settling.md) → `references/failures/f22-adc-settling.md` (ok)
- L27 [unknown] [rive-sense-parasitic.md)、[F22 ADC 建立时间](f22-adc-settling.md)；检查项 [SC34、SC35、SC36](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [-settling.md)；检查项 [SC34、SC35、SC36](../schematic-details.md)、[PL14、PL21、PL22、PL23](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L27 [unknown] [c-details.md)、[PL14、PL21、PL22、PL23](../pcb-placement-details.md)、[RT07、RT21、RT23](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L27 [unknown] [](../pcb-placement-details.md)、[RT07、RT21、RT23](../pcb-routing-details.md)、[DM19](../domain-design-details.md) → `references/domain-design-details.md` (ok)
- L125 [unknown] [把电机回流做成一条独立、宽、短的铜路，明确不从传感器/ADC 下方穿过；模拟回流从 `SP1` 单独分支，不与功率回流共段。对应 [RT07、RT21、RT23](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L125 [unknown] [` 单独分支，不与功率回流共段。对应 [RT07、RT21、RT23](../pcb-routing-details.md) 与 [PL14、PL21、PL23](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)

### `references/failures/f27-usb-ground-loop-source-conflict.md`

- 标题：F27 USB 与外部 5 V 同时接入：地环路、ORing 反灌与屏蔽环流
- 行/字符/字节：213 / 19276 / 37628
- SHA-256：`b272bb37fd5483b567bbc3e80c7b84a98f6f7bf17d1d4e6d957e4b4d15892483`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f27-usb-ground-loop-source-conflict.md` (ok) #适用边界 ok
- L27 [unknown] [Type-C 的 CC/Rd 问题先按 F09 排除，连接器外壳/屏蔽结构不同的板必须重新分析。
>
> **关联：** [PWR-05 多源供电与电源路径](../design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L27 [unknown] [ **关联：** [PWR-05 多源供电与电源路径](../design-cards/power/p05-power-mux.md)、[PWR-09 反接保护](../design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L27 [unknown] [WR-09 反接保护](../design-cards/power/p09-reverse-polarity.md)、[PWR-12 USB-C 5V Sink](../design-cards/power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L27 [unknown] [V Sink](../design-cards/power/p12-usbc-sink.md)、[IF-09 USB 2.0 Full-Speed Device](../design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L27 [unknown] [ull-Speed Device](../design-cards/interfaces/i09-usb-device.md)；专题 [B1 多路供电与电源切换](../engineering-deepdives/topics/b1-power-path-and-source-switching.md) → `references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` (ok)
- L27 [unknown] [engineering-deepdives/topics/b1-power-path-and-source-switching.md)、[C2 接地、屏蔽与共模](../engineering-deepdives/topics/c2-grounding-shielding-common-mode.md) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok)
- L27 [unknown] [deepdives/topics/c2-grounding-shielding-common-mode.md)；故障 [F09 USB-C CC 电阻缺失/错误](f09-usbc-cc.md) → `references/failures/f09-usbc-cc.md` (ok)
- L27 [unknown] [障 [F09 USB-C CC 电阻缺失/错误](f09-usbc-cc.md)；检查项 [SC10、SC11、SC16、SC30、SC31、PL15、RT06](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [查项 [SC10、SC11、SC16、SC30、SC31、PL15、RT06](../schematic-details.md)、[DM29、DM32、DM45](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f28-i2c-unpowered-device-lockup.md`

- 标题：F28 I²C 设备掉电后拖死总线
- 行/字符/字节：259 / 26959 / 51822
- SHA-256：`fe7ba1551e5ccee3d2031a373ce94b2a75d57e545e23045e3638a6be102e88d4`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f28-i2c-unpowered-device-lockup.md` (ok) #适用边界 ok
- L27 [unknown] [1（UM10204 §3.1.16 Bus clear）、IF-S02、IF-S05、IF-S10（TCA9517），见 [source-register.md](../source-register.md) → `references/source-register.md` (ok)
- L27 [unknown] [、IF-S10（TCA9517），见 [source-register.md](../source-register.md)；设计卡 [IF-01 I²C 总线](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L27 [unknown] [ster.md)；设计卡 [IF-01 I²C 总线](../design-cards/interfaces/i01-i2c.md)、[IF-02 I²C 缓冲](../design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L27 [unknown] [i2c.md)、[IF-02 I²C 缓冲](../design-cards/interfaces/i02-i2c-buffer.md)、[IF-12 电平转换](../design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L27 [unknown] [IF-12 电平转换](../design-cards/interfaces/i12-level-shift.md)；故障对照 [F06 I²C 上拉过强/过弱](f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L27 [unknown] [/i12-level-shift.md)；故障对照 [F06 I²C 上拉过强/过弱](f06-i2c-pullup.md)；专题 [D1 接口组合后的隐藏约束](../engineering-deepdives/topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L27 [unknown] [e-combination-constraints.md) §2.4/§2.8/§6.3；组合案例 [module-integration.md C03/C09](../module-integration.md) → `references/module-integration.md` (ok)
- L27 [unknown] [odule-integration.md C03/C09](../module-integration.md)；检查项 [SC27、SC26、PL15、RT19](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [SC27、SC26、PL15、RT19](../schematic-details.md)；测量总则 [simulation-measurement.md §5](../simulation-measurement.md) → `references/simulation-measurement.md` (ok)

### `references/failures/f29-spi-write-ok-read-unstable.md`

- 标题：F29 SPI NOR Flash 写正常读不稳定：MISO 采样窗、CS 释放与 20 MHz 排线
- 行/字符/字节：248 / 19989 / 39570
- SHA-256：`36ff8f64a0347d55615670660d58ea41e459778d8f29e2e4bf1e2de341383daa`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #适用边界 ok
- L13 [unknown] [分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界)
- [可能引入的新问题](#可能引入的新问题) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #可能引入的新问题 ok
- L14 [unknown] [[修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界)
- [可能引入的新问题](#可能引入的新问题)
- [适用范围/不能证明什么](#适用范围不能证明什么) → `references/failures/f29-spi-write-ok-read-unstable.md` (ok) #适用范围不能证明什么 ok
- L29 [unknown] [、多主、长背板、热插拔、安全相关不适用；换主控、换 Flash 型号/后缀、换线缆后必须重算。
>
> **关联：** 设计卡 [IF-03 SPI 点对点](../design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L29 [unknown] [：** 设计卡 [IF-03 SPI 点对点](../design-cards/interfaces/i03-spi.md)、[IF-04 SPI 多从机/片选](../design-cards/interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L29 [unknown] [04 SPI 多从机/片选](../design-cards/interfaces/i04-spi-multi.md)、[RF-07 SPI NOR Flash](../design-cards/wireless/w07-spi-flash.md) → `references/design-cards/wireless/w07-spi-flash.md` (ok)
- L29 [unknown] [F-07 SPI NOR Flash](../design-cards/wireless/w07-spi-flash.md)；专题 [D1 接口组合后的隐藏约束](../engineering-deepdives/topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L29 [unknown] [gineering-deepdives/topics/d1-interface-combination-constraints.md)、[D3 连接器与板外通信](../engineering-deepdives/topics/d3-off-board-interfaces.md) → `references/engineering-deepdives/topics/d3-off-board-interfaces.md` (ok)
- L29 [unknown] [eering-deepdives/topics/d3-off-board-interfaces.md)；故障 [F03 ESP32 启动 strap 被外围拖偏](f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L29 [unknown] [nterfaces.md)；故障 [F03 ESP32 启动 strap 被外围拖偏](f03-esp32-strap.md)、[F06 I2C 上拉过强/过弱](f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L29 [unknown] [](f03-esp32-strap.md)、[F06 I2C 上拉过强/过弱](f06-i2c-pullup.md)、[F07 RS-485 端接/偏置位置错误](f07-rs485-termination.md) → `references/failures/f07-rs485-termination.md` (ok)
- L29 [unknown] [up.md)、[F07 RS-485 端接/偏置位置错误](f07-rs485-termination.md)；检查项 [SC28、SC25、SC26、SC11](../schematic-details.md) → `references/schematic-details.md` (ok)
- L29 [unknown] [7-rs485-termination.md)；检查项 [SC28、SC25、SC26、SC11](../schematic-details.md)、[PL20](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L29 [unknown] [11](../schematic-details.md)、[PL20](../pcb-placement-details.md)、[RT11、RT19、RT20](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L29 [unknown] [](../pcb-placement-details.md)、[RT11、RT19、RT20](../pcb-routing-details.md)、[DM31](../domain-design-details.md) → `references/domain-design-details.md` (ok)

### `references/failures/f30-gpio-power-on-glitch.md`

- 标题：F30 GPIO 在上电阶段误触发电磁阀
- 行/字符/字节：178 / 14388 / 26898
- SHA-256：`b26ae2f0e5a2224dab7a76d389e7d8c66a4a32499be1fea6669cd80eeff8f560`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f30-gpio-power-on-glitch.md` (ok) #适用边界 ok
- L27 [unknown] [ V 逻辑、高边开关、集成驱动器、隔离栅驱、安全相关/汽车负载必须按对应手册重新分析。
>
> **关联：** 设计卡 [MCU-01 裸 MCU 最小系统](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L27 [unknown] [*关联：** 设计卡 [MCU-01 裸 MCU 最小系统](../design-cards/mcu/m01-bare-mcu.md)、[DRV-01 低侧开关](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L27 [unknown] [e-mcu.md)、[DRV-01 低侧开关](../design-cards/drive/d01-low-side.md)；专题 [D1 接口组合后的隐藏约束](../engineering-deepdives/topics/d1-interface-combination-constraints.md) → `references/engineering-deepdives/topics/d1-interface-combination-constraints.md` (ok)
- L27 [unknown] [ring-deepdives/topics/d1-interface-combination-constraints.md)、[E2 MOS 栅极驱动与异常状态](../engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok)
- L27 [unknown] [./engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md)、[B4 电源动态与负载瞬态](../engineering-deepdives/topics/b4-power-dynamics.md) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok)
- L27 [unknown] [ngineering-deepdives/topics/b4-power-dynamics.md)；故障对照 [F03 ESP32 启动 strap 被外围拖偏](f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)
- L27 [unknown] [md)；故障对照 [F03 ESP32 启动 strap 被外围拖偏](f03-esp32-strap.md)；检查项 [SC21、SC39、SC14、SC22](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [p32-strap.md)；检查项 [SC21、SC39、SC14、SC22](../schematic-details.md)、[DM18、DM01、DM04](../domain-design-details.md) → `references/domain-design-details.md` (ok)
- L27 [unknown] [22](../schematic-details.md)、[DM18、DM01、DM04](../domain-design-details.md)、[PL13](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L27 [unknown] [M01、DM04](../domain-design-details.md)、[PL13](../pcb-placement-details.md)、[RT09](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)

### `references/failures/f31-replacement-passes-typical-fails-corner.md`

- 标题：F31 换料后典型工况正常、边界工况失败（同封装 MOSFET）
- 行/字符/字节：249 / 17983 / 30856
- SHA-256：`b48b92b3f49e585289d64362ddbeabbb5da384e2d202a26602e2309e82c1f32c`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f31-replacement-passes-typical-fails-corner.md` (ok) #适用边界 ok
- L27 [unknown] [/GaN、48 V 以上母线；这些条件的 `R_DS(on)`、`Q_g`、SOA、热阻判据不同。
>
> **关联：** 设计卡 [DRV-01 低侧开关](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L27 [unknown] [
> **关联：** 设计卡 [DRV-01 低侧开关](../design-cards/drive/d01-low-side.md)、[DRV-05 H 桥](../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L27 [unknown] [d01-low-side.md)、[DRV-05 H 桥](../design-cards/drive/d05-h-bridge.md)、[DRV-08 加热器](../design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L27 [unknown] [-bridge.md)、[DRV-08 加热器](../design-cards/drive/d08-heater.md)（只借热/驱动方法）；选型 [替代分类](../selection/replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L27 [unknown] [d08-heater.md)（只借热/驱动方法）；选型 [替代分类](../selection/replacement-classes.md)、[半导体分立器件](../selection/semiconductors.md) → `references/selection/semiconductors.md` (ok)
- L27 [unknown] [t-classes.md)、[半导体分立器件](../selection/semiconductors.md)；故障对照 [F13 MOSFET SOA/热插拔](f13-mosfet-soa.md) → `references/failures/f13-mosfet-soa.md` (ok)
- L27 [unknown] [tion/semiconductors.md)；故障对照 [F13 MOSFET SOA/热插拔](f13-mosfet-soa.md)；专题 [E2 栅极驱动](../engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md) → `references/engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md` (ok)
- L27 [unknown] [](../engineering-deepdives/topics/e2-gate-drive-and-false-turn-on.md)、[E3 热与机械环境](../engineering-deepdives/topics/e3-thermal-mechanical-environment.md) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok)
- L27 [unknown] [](../engineering-deepdives/topics/e3-thermal-mechanical-environment.md)、[B4 电源动态](../engineering-deepdives/topics/b4-power-dynamics.md) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok)
- L27 [unknown] [ 电源动态](../engineering-deepdives/topics/b4-power-dynamics.md)；检查项 [SC21、SC39、SC03](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [s/b4-power-dynamics.md)；检查项 [SC21、SC39、SC03](../schematic-details.md)、[PL13、PL16](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L27 [unknown] [39、SC03](../schematic-details.md)、[PL13、PL16](../pcb-placement-details.md)、[RT09](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L153 [unknown] [ 4.5 V 的值去证明 3.1 V 够”。这些是 B/E2 级判据，不是本案例的实测。
- **方法对照（C3 专题，B/E2）。** [C3 运放隐藏条件](../engineering-deepdives/topics/c3-opamp-hidden-conditions.md) → `references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` (ok)

### `references/failures/f32-enclosure-degrades-rf-and-thermal.md`

- 标题：F32 外壳安装后无线或热性能下降
- 行/字符/字节：266 / 19313 / 38241
- SHA-256：`7b20325152e243a75d247d9a5e1cca20e4485cb7726ea2d8ce45f34760d5916d`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f32-enclosure-degrades-rf-and-thermal.md` (ok) #适用边界 ok
- L27 [unknown] [须重新分析；15 mm、5 mm、λ/10 都是特定参考条件或尺度，不是通用验收线。
>
> **关联：** 设计卡 [RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L27 [unknown] [计卡 [RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md)、[RF-02 天线接口与匹配](../design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L27 [unknown] [-ble.md)、[RF-02 天线接口与匹配](../design-cards/wireless/w02-antenna.md)、[RF-04 GNSS 模组](../design-cards/wireless/w04-gnss.md) → `references/design-cards/wireless/w04-gnss.md` (ok)
- L27 [unknown] [02-antenna.md)、[RF-04 GNSS 模组](../design-cards/wireless/w04-gnss.md)、[PWR-01 LDO](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L27 [unknown] [eless/w04-gnss.md)、[PWR-01 LDO](../design-cards/power/p01-ldo.md)、[MCU-02 模组最小系统](../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L27 [unknown] [-ldo.md)、[MCU-02 模组最小系统](../design-cards/mcu/m02-module-mcu.md)；专题 [D4 无线性能与整机环境](../engineering-deepdives/topics/d4-wireless-integration.md) → `references/engineering-deepdives/topics/d4-wireless-integration.md` (ok)
- L27 [unknown] [能与整机环境](../engineering-deepdives/topics/d4-wireless-integration.md)、[E3 热设计与机械环境](../engineering-deepdives/topics/e3-thermal-mechanical-environment.md) → `references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md` (ok)
- L27 [unknown] [ing-deepdives/topics/e3-thermal-mechanical-environment.md)；故障对照 [F18 天线净空/外壳导致失谐](f18-antenna-enclosure.md) → `references/failures/f18-antenna-enclosure.md` (ok)
- L27 [unknown] [vironment.md)；故障对照 [F18 天线净空/外壳导致失谐](f18-antenna-enclosure.md)、[F25 Wi-Fi 发射瞬间复位](f25-radio-tx-resets-system.md) → `references/failures/f25-radio-tx-resets-system.md` (ok)
- L27 [unknown] [e.md)、[F25 Wi-Fi 发射瞬间复位](f25-radio-tx-resets-system.md)；检查项 [SC09、SC18、SC19、SC22](../schematic-details.md) → `references/schematic-details.md` (ok)
- L27 [unknown] [-resets-system.md)；检查项 [SC09、SC18、SC19、SC22](../schematic-details.md)、[PL26、PL27](../pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L27 [unknown] [22](../schematic-details.md)、[PL26、PL27](../pcb-placement-details.md)、[RT25、RT26](../pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L27 [unknown] [](../pcb-placement-details.md)、[RT25、RT26](../pcb-routing-details.md)、[DM33、DM35](../domain-design-details.md) → `references/domain-design-details.md` (ok)
- L27 [unknown] [uting-details.md)、[DM33、DM35](../domain-design-details.md)；热专题 [thermal/topic.md](../thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/failures/f33-measurement-caused-wrong-rework.md`

- 标题：F33 测量接法错误导致错误修板
- 行/字符/字节：176 / 14782 / 29665
- SHA-256：`5a4a281b19fd11c66cf0140781025a0a4ccbeba931881b0626cdee961bfa531d`

- L5 [unknown] [---

## 内容导航

- [现象](#现象) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #现象 ok
- L6 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #工况 ok
- L7 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #原因假设 ok
- L8 [unknown] [---

## 内容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #区分假设的检查 ok
- L9 [unknown] [容导航

- [现象](#现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #根因证据 ok
- L10 [unknown] [现象)
- [工况](#工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #修复 ok
- L11 [unknown] [工况)
- [原因假设](#原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #复验 ok
- L12 [unknown] [原因假设)
- [区分假设的检查](#区分假设的检查)
- [根因证据](#根因证据)
- [修复](#修复)
- [复验](#复验)
- [适用边界](#适用边界) → `references/failures/f33-measurement-caused-wrong-rework.md` (ok) #适用边界 ok
- L27 [unknown] [须按实际探头型号和手册核对，不能把本文的 150 nH、10 pF、130 MHz 当保证值。
>
> **关联：** 设计卡 [ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L27 [unknown] [[ANA-06 低侧电流采样](../design-cards/analog/a06-low-side-sense.md)；专题 [C4 测量方法本身造成的错误](../engineering-deepdives/topics/c4-measurement-artifacts.md) → `references/engineering-deepdives/topics/c4-measurement-artifacts.md` (ok)
- L27 [unknown] [造成的错误](../engineering-deepdives/topics/c4-measurement-artifacts.md)、[C2 接地/屏蔽/共模](../engineering-deepdives/topics/c2-grounding-shielding-common-mode.md) → `references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` (ok)
- L27 [unknown] [ngineering-deepdives/topics/c2-grounding-shielding-common-mode.md)、[B4 电源动态与负载瞬态](../engineering-deepdives/topics/b4-power-dynamics.md) → `references/engineering-deepdives/topics/b4-power-dynamics.md` (ok)
- L27 [unknown] [eering-deepdives/topics/b4-power-dynamics.md)；测量总则 [simulation-measurement.md §5](../simulation-measurement.md) → `references/simulation-measurement.md` (ok)
- L27 [unknown] [ation-measurement.md §5](../simulation-measurement.md)；故障对照 [F01 ODrive 电流采样寄生电阻](f01-odrive-sense-parasitic.md) → `references/failures/f01-odrive-sense-parasitic.md` (ok)
- L27 [unknown] [d)；故障对照 [F01 ODrive 电流采样寄生电阻](f01-odrive-sense-parasitic.md)、[F10 Buck 反馈/输入电容布局](f10-buck-loop-layout.md) → `references/failures/f10-buck-loop-layout.md` (ok)
- L27 [unknown] [ense-parasitic.md)、[F10 Buck 反馈/输入电容布局](f10-buck-loop-layout.md)、[F26 电机启动干扰模拟采集](f26-motor-start-corrupts-adc.md) → `references/failures/f26-motor-start-corrupts-adc.md` (ok)
- L27 [unknown] [op-layout.md)、[F26 电机启动干扰模拟采集](f26-motor-start-corrupts-adc.md)；检查项 [MF29 测量方法记录](../manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L27 [unknown] [-start-corrupts-adc.md)；检查项 [MF29 测量方法记录](../manufacturing-details.md)、[P02 Buck](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L117 [unknown] [真实，怎么修”，不证明本板 500 mV 是真实。
  - 本仓库方法判据（非原厂，单独标注）：[simulation-measurement.md §5.3](../simulation-measurement.md) → `references/simulation-measurement.md` (ok)

### `references/feedback-loop.md`

- 标题：反馈闭环：观察 → 计划 → 局部修改 → 回读 → 复验 → 沉淀
- 行/字符/字节：184 / 7238 / 11954
- SHA-256：`63be9f46b8e4689330953d3dc728f18cd6b88f6cb06b9ccf1f50d06a54566cf7`

### `references/firmware-bringup.md`

- 标题：程序、烧录与样机联调
- 行/字符/字节：36 / 1950 / 5288
- SHA-256：`dc63e598b214068ed4259ac9d5a3456fb93fd7ddfd5f0d1f8717c17f1341db6f`

- L8 [unknown] [用的代码开发、文件、命令和设备工具推进已授权工作；本Skill不内置SDK、编译器、云服务或设备访问权限。

## 与硬件同步确定接口
按 [项目关联记录](project-coherence.md) → `references/project-coherence.md` (ok)
- L32 [unknown] [滚/救援路径；不把“双分区”或版本单调增长当所有平台都支持的强制模板。先保留可用下载与调试，再按需求加OTA。
出现烧录/重启/读数/通知问题时按 [分层排障](troubleshooting.md) → `references/troubleshooting.md` (ok)

### `references/idea-to-product.md`

- 标题：从自然语言idea到可用实物
- 行/字符/字节：42 / 1980 / 5074
- SHA-256：`d6357310c0e3f13a8a2ba71d7d6852405d1bf16a25b0a696382085dc3baca916`

- L27 [conditional_read] [云服务若体系内没有适用能力，说明选择，不将商家短信或其他业务通道杜撰成设备通知接口。

## 4. 一份目标，多条任务链
涉及多种工件时按 [项目关联记录](project-coherence.md) → `references/project-coherence.md` (ok)
- L27 [conditional_read] [. 一份目标，多条任务链
涉及多种工件时按 [项目关联记录](project-coherence.md) 维护接口/版本和变更传播；需要结构时加载 [外壳协同](enclosure-integration.md) → `references/enclosure-integration.md` (ok)
- L27 [conditional_read] [herence.md) 维护接口/版本和变更传播；需要结构时加载 [外壳协同](enclosure-integration.md)。常见路线可用 [起步方案骨架](starter-patterns.md) → `references/starter-patterns.md` (ok)
- L27 [conditional_read] [(enclosure-integration.md)。常见路线可用 [起步方案骨架](starter-patterns.md)，需要理解接续过程时读 [演练案例](product-example.md) → `references/product-example.md` (ok)

### `references/installation-updates.md`

- 标题：安装、检查更新与回退
- 行/字符/字节：135 / 5264 / 9836
- SHA-256：`96d43ab16b4471d50adf55722e9cf3ac59c4190db78edd9f2ed62a645865e341`

### `references/interaction.md`

- 标题：新手与工程师的协作
- 行/字符/字节：40 / 1151 / 2866
- SHA-256：`4f9ebb8e3ab27e9607dcd63132f45b8fcdb4d14efba3dba00c3c49772685af61`

### `references/jlc-handoff.md`

- 标题：嘉立创业务：从图纸到实物的正确衔接
- 行/字符/字节：63 / 2676 / 5902
- SHA-256：`326fd1e5a6fe58479866f84854e8f292bc16612acf49f5005c7fad94b7d16000`

- L3 [unknown] [# 嘉立创业务：从图纸到实物的正确衔接

打板/贴片任务同时执行 [生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)
- L3 [unknown] [业务：从图纸到实物的正确衔接

打板/贴片任务同时执行 [生产规则接入](jlc-production.md)，由Agent按当前工艺/渠道建立 [生产档案](../assets/manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L3 [unknown] [建立 [生产档案](../assets/manufacturing-profile.md)。PCB能力、SMT装配和EDA实际规则分别核对；依 [PCB生产规则](jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L3 [unknown] [ing-profile.md)。PCB能力、SMT装配和EDA实际规则分别核对；依 [PCB生产规则](jlc-pcb-rules.md) 与 [SMT生产规则](jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)
- L62 [unknown] [三条具体交付路线（商城购料自己焊、嘉立创 PCB+SMT、电子板+固件/配置+外壳/线束+整机验收）的必需文件、真实字段、装配变体和对账步骤见 [制造与交付路线](manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)

### `references/jlc-pcb-rules.md`

- 标题：嘉立创PCB生产规则与条件快照
- 行/字符/字节：50 / 2561 / 5645
- SHA-256：`aded240dab8bef7769bc5613b9e3c11866850601097d322325276005b4617600`

- L3 [unknown] [# 嘉立创PCB生产规则与条件快照

用途：设计准备、设置DRC、制造复核。按 [生产规则流程](jlc-production.md) → `references/jlc-production.md` (ok)
- L9 [external_reference] [。

## 官方定位与查阅范围

| 编号 | 官方页面 | 本次实际读取/用途 |
|---|---|---|
| PCB-A | [工艺能力总表](https://www.jlc.com/portal/vtechnology.html) → `https://www.jlc.com/portal/vtechnology.html` (external)
- L10 [external_reference] [chnology.html) | FR4线路、孔、阻焊、成型、层叠与SMT服务对比；FPC段落只用于识别独立条件与冲突 |
| PCB-B | [制造工艺指引](https://www.jlc.com/portal/1/serviceGuide) → `https://www.jlc.com/portal/1/serviceGuide` (external)
- L11 [external_reference] [jlc.com/portal/1/serviceGuide) | 当前可访问的旧条件，和A存在差异；不视为统一最新覆盖规则 |
| PCB-C | [阻焊说明](https://www.jlc.com/portal/server_guide_34402.html) → `https://www.jlc.com/portal/server_guide_34402.html` (external)
- L12 [external_reference] [l/server_guide_34402.html) | 正文及图示入口可读；具体图中尺寸未全部提取，不据此补数字 |
| PCB-D | [过孔五种加工方式](https://www.jlc.com/portal/server_guide_15544.html) → `https://www.jlc.com/portal/server_guide_15544.html` (external)
- L13 [external_reference] [de_15544.html) | 盖油/开窗/塞油/树脂/铜浆的差别与下单备注，页面标注更新2026-09-30 |
| PCB-E | [叠层/阻抗工具入口](https://tools.jlc.com/jlcTools/) → `https://tools.jlc.com/jlcTools/` (external)
- L49 [unknown] [的线宽不保证载流/温升/阻抗/安全间距，尺寸公差也要回到外壳、连接器与实际装配验证。工艺上更保守但破坏RF/电源回路的修改不自动合理。

最终按 [制造细节](manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L49 [unknown] [保守但破坏RF/电源回路的修改不自动合理。

最终按 [制造细节](manufacturing-details.md) 做同版文件复核，按 [SMT生产规则](jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)

### `references/jlc-production.md`

- 标题：嘉立创生产规则：按订单连接设计与制造
- 行/字符/字节：51 / 2556 / 6696
- SHA-256：`8ea271dc6abf75f1b951ee1b428f1c673c85aa3c6d45b858279f873b52572ba6`

- L7 [unknown] [l不代表已改用户PCB、上传文件或收到工厂结论。

## 先建立本项目的生产档案

Agent从工程、既有订单和用户已知目标提取信息，用 [生产档案模板](../assets/manufacturing-profile.md) → `assets/manufacturing-profile.md` (ok)
- L18 [unknown] [不能把离线候选或EDA内置默认标成生产已满足。纯审查/先方案不因此要求连EDA或登录工厂。

## 把官方要求变成项目规则

1. 按 [PCB生产规则](jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L18 [unknown] [方案不因此要求连EDA或登录工厂。

## 把官方要求变成项目规则

1. 按 [PCB生产规则](jlc-pcb-rules.md)、[SMT生产规则](jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)

### `references/jlc-smt-rules.md`

- 标题：嘉立创SMT生产规则：服务、装配和数据一起核对
- 行/字符/字节：52 / 3655 / 8144
- SHA-256：`f4054800a019560074e4e4e09c677cb32f558f91ac01d533e95a0f31fb69fa14`

- L3 [unknown] [# 嘉立创SMT生产规则：服务、装配和数据一起核对

用于工厂焊好板、混合贴片/插件、来料、拼板、制造准备。核对日期2026-10-20。按 [生产流程](jlc-production.md) → `references/jlc-production.md` (ok)
- L7 [external_reference] [档案；不能把国内SMT规则套用海外JLCPCB，不能以立创商城C号现货替代工厂供料/工艺确认。

## 官方来源与服务条件

当日读取 [SMT规范目录](https://www.jlc.com/portal/q7i64042.html) → `https://www.jlc.com/portal/q7i64042.html` (external)
- L9 [external_reference] [2分别组织准入、良率和成本问题，但正文声明须结合正式文本、器件和工程审核。以下是适用检查的独立归纳，不把目录中的每个数字提升成全行业强制规则。

[工艺总表](https://www.jlc.com/portal/vtechnology.html) → `https://www.jlc.com/portal/vtechnology.html` (external)
- L17 [external_reference] [# 工艺边、Mark与拼板

| 项目 | 官方快照与范围 | 实际设计/核查动作 |
|---|---|---|
| 标准型硬板工艺边 | [专项规范](https://www.jlc.com/portal/q7i62681.html) → `https://www.jlc.com/portal/q7i62681.html` (external)
- L18 [external_reference] [方向、夹持面、高度、薄板/小板支撑做候选；器件本体/伸出脚不得侵占夹持区。生产边与成品外形分开，不能擅改用户安装尺寸 |
| 光学定位 | [Mark专项规范](https://www.jlc.com/portal/q7i62691.html) → `https://www.jlc.com/portal/q7i62691.html` (external)
- L19 [external_reference] [部及单双面需要，Mark不当作需采购贴装的元件；“周围3mm”的具体几何有歧义时保留范围并查图/厂方，不能猜成硬DRC |
| V割 | [V-cut专项规范](https://www.jlc.com/portal/q7i62703.html) → `https://www.jlc.com/portal/q7i62703.html` (external)
- L21 [external_reference] [条件 | 核对连接强度、毛刺/断口落在何处、连接筋与敏感件、单元间隙、分板工具和治具支撑；不因空间紧自动删除加强筋 |
| FPC及特殊材料 | [FPC目录](https://www.jlc.com/portal/q7i64084.html) → `https://www.jlc.com/portal/q7i64084.html` (external)
- L21 [external_reference] [动删除加强筋 |
| FPC及特殊材料 | [FPC目录](https://www.jlc.com/portal/q7i64084.html)、[FPC工艺边](https://www.jlc.com/portal/q7i64063.html) → `https://www.jlc.com/portal/q7i64063.html` (external)
- L23 [external_reference] [补强、四边夹持、材料/耐温/治具和拼板；FPC当日总表存在尺寸描述差异，未取得订单条件前不自动给最终尺寸，也不套FR4拼板模板 |

旧 [可接受工艺边设计](https://www.jlc.com/portal/server_guide_22406.html) → `https://www.jlc.com/portal/server_guide_22406.html` (external)
- L29 [external_reference] [---|---|
| 本体间隔与返修 | 查实际本体/高度/吸嘴通道，而非中心距或单看焊盘。小阻容/二三极管、IC、发热与热敏器件分别处理 | [器件间隔专项](https://www.jlc.com/portal/q7i62744.html) → `https://www.jlc.com/portal/q7i62744.html` (external)
- L30 [external_reference] [判全板不能生产 |
| 引脚/焊盘几何 | 对齐完整型号、原厂推荐焊盘、脚距、Mask/Paste及实际服务；密脚/特殊封装单独检查 | [相邻引脚/焊盘专项](https://www.jlc.com/portal/q7i62694.html) → `https://www.jlc.com/portal/q7i62694.html` (external)
- L31 [external_reference] [是同一个参数，不能把参考间距强行改进原厂焊盘 |
| 焊盘内孔 | 检查焊膏吸入、孔填实/盖帽与平整、EPAD锡量/分窗；与PCB订单联动 | [焊盘上的过孔](https://www.jlc.com/portal/q7i62741.html) → `https://www.jlc.com/portal/q7i62741.html` (external)
- L34 [external_reference] [长、装配面、板厚及厂方工艺确认；不要自行决定胶水或削脚 |
| 极性与Pin-1 | 对照原厂标识、实际焊盘、丝印和装配图；底面角度约定单独查 | [极性专项](https://www.jlc.com/portal/q7i62705.html) → `https://www.jlc.com/portal/q7i62705.html` (external)
- L40 [external_reference] [具体物料；不把目录备损百分比当每种料必须统一购买数，更不能把高价料“0损耗”当厂方保证 |

## BOM与坐标要能进入真实生产

读取 [坐标格式说明](https://www.jlc.com/portal/server_guide_53182.html) → `https://www.jlc.com/portal/server_guide_53182.html` (external)
- L40 [external_reference] [能进入真实生产

读取 [坐标格式说明](https://www.jlc.com/portal/server_guide_53182.html)、[文件标准](https://www.jlc.com/portal/server_guide_4071.html) → `https://www.jlc.com/portal/server_guide_4071.html` (external)
- L45 [external_reference] [例外。
4. 保留工程物理身份，建立导出映射，检查重复/缺失/多余位号和BOM、坐标、PCB集合；Mark/孔、DNP、后焊等排除项有明确理由。[官方问题说明](https://www.jlc.com/portal/server_guide_17103.html) → `https://www.jlc.com/portal/server_guide_17103.html` (external)

### `references/lcsc-sourcing.md`

- 标题：立创商城：从设计选型到可核对购料表
- 行/字符/字节：75 / 4078 / 9789
- SHA-256：`25f4b306a9e53a197936cb93520d9961cc1aa3dd8c57e13cc818271dfc3714c4`

- L46 [unknown] [件清单”；后台保留完整映射和证据，不把采购表当作用户必须填写的作业。

按器件类型的必看参数、立创商城检索关键词/筛选顺序和替代分级见 [器件选型与替代资料](selection/README.md) → `references/selection/README.md` (ok)
- L54 [unknown] [ut` 写结果；它不是设计前置条件，失败就停在原始 BOM，不反复重跑。`bom-enrich` 在 `value=null` 时有已知异常，见 [工具动作陷阱](tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L72 [example] [页核对可贴状态与费用。两者都未核时写 `待查`，不写“有货”。

### 8.3 字段与脚本

- 零件表模板见 [parts.example.json](../assets/parts.example.json) → `assets/parts.example.json` (ok)
- L74 [unknown] [`not_checked` 列出的库存、价格、SMT 可贴、封装几何与替代等价性仍须人工核对。
- 选型、封装与手焊/SMT 分界见 [选型、BOM与装配变体](part-selection.md) → `references/part-selection.md` (ok)

### `references/manufacturing-details.md`

- 标题：制造、装配与首板细节
- 行/字符/字节：50 / 2618 / 6436
- SHA-256：`1125d0f916017d05b552a6d6a0866e397433971606db9422a8cf07de46117aef`

- L3 [required_read] [# 制造、装配与首板细节

嘉立创制造任务先执行 [生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)
- L3 [required_read] [# 制造、装配与首板细节

嘉立创制造任务先执行 [生产规则接入](jlc-production.md)，结合 [PCB条件快照](jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L3 [required_read] [嘉立创制造任务先执行 [生产规则接入](jlc-production.md)，结合 [PCB条件快照](jlc-pcb-rules.md) 与 [SMT装配条件](jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)
- L5 [unknown] [建议、能力极限、项目值及实际测值分开保存，不能把本地检查结果写成厂方生产放行。

按实际嘉立创PCB/SMT或用户指定渠道核对当前订单条件，来源见 [经验库](design-experience.md) → `references/design-experience.md` (ok)
- L49 [conditional_read] [录工厂电测、烧录和用户用途实测，不把首板亮灯升级为长期可靠性或认证通过。

需要完整功耗/结温、热阻指标、瞬态及PCB/外壳测量方法时，按需读 [板级热专题](thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/manufacturing-routes.md`

- 标题：三条制造与交付路线
- 行/字符/字节：816 / 37943 / 74741
- SHA-256：`c4bc9f7469ae4fa323415528b2e5c4e1cdd853977522e921d035f4ee3754c879`

- L3 [unknown] [交付版本，或用户明确要“买零件自己焊”“收到焊好的板”“收到能用的整机”。本文负责把设计包拆成可下单、可对账、可验收的制造包；具体逐项检查仍读 [制造与首板细节](manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L3 [unknown] [机”。本文负责把设计包拆成可下单、可对账、可验收的制造包；具体逐项检查仍读 [制造与首板细节](manufacturing-details.md)、[原理图细节](schematic-details.md) → `references/schematic-details.md` (ok)
- L3 [unknown] [项检查仍读 [制造与首板细节](manufacturing-details.md)、[原理图细节](schematic-details.md)、[PCB布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L3 [unknown] [md)、[原理图细节](schematic-details.md)、[PCB布局细节](pcb-placement-details.md) 与 [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L185 [unknown] [先做连接表和通断测试 |
| 整机测试 | 用户/Agent/第三方 | 测试计划、样本、判据、记录 | 工厂 AOI/电测不等于整机功能 | 按 [功能验收](product-acceptance.md) → `references/product-acceptance.md` (ok)
- L337 [unknown] [ 推荐工作范围（如 3.0–3.6 V） | 绝对最大（如 −0.3–3.6 V） | 典型电流不是峰值保证 | 电源树按最大峰值+同轨负载；见 [MCU-01](design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L337 [unknown] [| 典型电流不是峰值保证 | 电源树按最大峰值+同轨负载；见 [MCU-01](design-cards/mcu/m01-bare-mcu.md)、[RF-01](design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L461 [unknown] [行 |

工厂 AOI/SPI/电测只能证明其覆盖的制造/焊接项；不能代替 A4–A9。板亮、串口打印、发包成功都不等于目标场景完成。完成级别按 [功能验收](product-acceptance.md) → `references/product-acceptance.md` (ok)
- L681 [unknown] [把“待查”字段补齐。

## 9. 项目样本：24 V RS485 控制器（离线规划）

> 更深入的 4–20 mA/RS485 采集项目见 [P02](projects/p02-industrial-rs485-analog.md) → `references/projects/p02-industrial-rs485-analog.md` (ok)
- L800 [unknown] [审核/付款、文件打包/Gerber 建议 | 是否只收 Gerber/按 Paste 层未取得明文；价格/交期 |

补充：本文引用的设计卡 [MCU-01](design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L800 [unknown] [ 层未取得明文；价格/交期 |

补充：本文引用的设计卡 [MCU-01](design-cards/mcu/m01-bare-mcu.md)、[RF-01](design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L800 [unknown] [ards/mcu/m01-bare-mcu.md)、[RF-01](design-cards/wireless/w01-wifi-ble.md)、[ANA-06](design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L800 [unknown] [e-sense.md) 只用于“推荐工作条件 vs 绝对最大额定值”和采样/Kelvin 的边界，不把其中的器件数值搬到制造路线。完整来源登记见 [原始来源登记](source-register.md) → `references/source-register.md` (ok)
- L811 [unknown] [笔记范围**：本文制造结论主要来自 `manufacturing.md`；电源/接口/模拟/无线/驱动条件见对应的 `power.md` 等来源笔记、[来源登记](source-register.md) → `references/source-register.md` (ok)
- L815 [example] [**：不检查转换器启动/压差、峰值/内阻、温度/老化/重试；不能当整机寿命或验收通过。

本文件涉及Mark、工艺边、孔处理及制造参数时，以 [生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)

### `references/module-cards.md`

- 标题：按功能组合的模块设计卡
- 行/字符/字节：78 / 6723 / 11114
- SHA-256：`da8ef870bb711dc4cd32b05705d3eb501e98069c060b9d634b495475f4aca395`

- L3 [conditional_read] [扑或可直接套用的器件库。每类保留三条组合检查；具体的用途边界、必要输入、计算顺序、完整算例、选型、逐脚核对、原理图/PCB 要求和验证办法，按需读取 [设计卡库](design-cards/README.md) → `references/design-cards/README.md` (ok)
- L5 [unknown] [
> 组合两个各自正常的模块仍可能失败：上拉并联、电压域、启动脚、供电状态、引脚复用、连接器视角和返回路径都要在组合后重新核对。跨模块检查见 [组合与接口契约](module-integration.md) → `references/module-integration.md` (ok)
- L11 [unknown] [RAM 占脚、EPAD 连接、配置失败、去耦高频回路。不要把某个 STM32/ESP32 型号的 RC 与脚号推广到全家族。
- **深入：** [裸 MCU](design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)
- L11 [unknown] [2 型号的 RC 与脚号推广到全家族。
- **深入：** [裸 MCU](design-cards/mcu/m01-bare-mcu.md)、[模组 MCU](design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L11 [unknown] [sign-cards/mcu/m01-bare-mcu.md)、[模组 MCU](design-cards/mcu/m02-module-mcu.md)、[复位](design-cards/mcu/m03-reset-supervisor.md) → `references/design-cards/mcu/m03-reset-supervisor.md` (ok)
- L11 [unknown] [cards/mcu/m02-module-mcu.md)、[复位](design-cards/mcu/m03-reset-supervisor.md)、[启动脚](design-cards/mcu/m04-boot-strap.md) → `references/design-cards/mcu/m04-boot-strap.md` (ok)
- L11 [unknown] [cards/mcu/m03-reset-supervisor.md)、[启动脚](design-cards/mcu/m04-boot-strap.md)、[晶体](design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L11 [unknown] [(design-cards/mcu/m04-boot-strap.md)、[晶体](design-cards/mcu/m05-crystal.md)、[外部时钟](design-cards/mcu/m06-external-clock.md) → `references/design-cards/mcu/m06-external-clock.md` (ok)
- L11 [unknown] [rds/mcu/m05-crystal.md)、[外部时钟](design-cards/mcu/m06-external-clock.md)、[SWD/JTAG](design-cards/mcu/m07-swd-jtag.md) → `references/design-cards/mcu/m07-swd-jtag.md` (ok)
- L11 [unknown] [external-clock.md)、[SWD/JTAG](design-cards/mcu/m07-swd-jtag.md)、[UART Bootloader](design-cards/mcu/m08-uart-bootloader.md) → `references/design-cards/mcu/m08-uart-bootloader.md` (ok)
- L12 [unknown] [RT Bootloader](design-cards/mcu/m08-uart-bootloader.md)。
- **常用硬件：** [I 主控与最小系统](common-hardware/i-mcu.md) → `references/common-hardware/i-mcu.md` (ok)
- L18 [unknown] [掉电、短路、输出过冲；控制器真正高 di/dt 回路、反馈/Kelvin 路径和散热。不要用线性器件封装名称推断固定可耗散瓦数。
- **深入：** [LDO](design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L18 [unknown] [径和散热。不要用线性器件封装名称推断固定可耗散瓦数。
- **深入：** [LDO](design-cards/power/p01-ldo.md)、[Buck](design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L18 [unknown] [DO](design-cards/power/p01-ldo.md)、[Buck](design-cards/power/p02-buck.md)、[Boost](design-cards/power/p03-boost.md) → `references/design-cards/power/p03-boost.md` (ok)
- L18 [unknown] [gn-cards/power/p02-buck.md)、[Boost](design-cards/power/p03-boost.md)、[Buck-Boost](design-cards/power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L18 [unknown] [rds/power/p03-boost.md)、[Buck-Boost](design-cards/power/p04-buck-boost.md)、[多源供电](design-cards/power/p05-power-mux.md) → `references/design-cards/power/p05-power-mux.md` (ok)
- L18 [unknown] [cards/power/p04-buck-boost.md)、[多源供电](design-cards/power/p05-power-mux.md)、[线性充电](design-cards/power/p06-linear-charger.md) → `references/design-cards/power/p06-linear-charger.md` (ok)
- L18 [unknown] [s/power/p05-power-mux.md)、[线性充电](design-cards/power/p06-linear-charger.md)、[开关充电](design-cards/power/p07-switching-charger.md) → `references/design-cards/power/p07-switching-charger.md` (ok)
- L18 [unknown] [p06-linear-charger.md)、[开关充电](design-cards/power/p07-switching-charger.md)、[电池保护](design-cards/power/p08-battery-protection.md) → `references/design-cards/power/p08-battery-protection.md` (ok)
- L18 [unknown] [switching-charger.md)、[电池保护](design-cards/power/p08-battery-protection.md)、[反接保护](design-cards/power/p09-reverse-polarity.md) → `references/design-cards/power/p09-reverse-polarity.md` (ok)
- L18 [unknown] [8-battery-protection.md)、[反接保护](design-cards/power/p09-reverse-polarity.md)、[热插拔](design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L18 [unknown] [/power/p09-reverse-polarity.md)、[热插拔](design-cards/power/p10-hot-swap.md)、[eFuse](design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L18 [unknown] [ards/power/p10-hot-swap.md)、[eFuse](design-cards/power/p11-efuse.md)、[USB-C Sink](design-cards/power/p12-usbc-sink.md) → `references/design-cards/power/p12-usbc-sink.md` (ok)
- L18 [unknown] [er/p11-efuse.md)、[USB-C Sink](design-cards/power/p12-usbc-sink.md)、[USB-C Source](design-cards/power/p13-usbc-source.md) → `references/design-cards/power/p13-usbc-source.md` (ok)
- L18 [unknown] [er/p12-usbc-sink.md)、[USB-C Source](design-cards/power/p13-usbc-source.md)、[掉电保持](design-cards/power/p14-supercap-backup.md) → `references/design-cards/power/p14-supercap-backup.md` (ok)
- L19 [unknown] [e.md)、[掉电保持](design-cards/power/p14-supercap-backup.md)。
- **常用硬件：** [F 供电入口/保护](common-hardware/f-input-protection.md) → `references/common-hardware/f-input-protection.md` (ok)
- L19 [unknown] [硬件：** [F 供电入口/保护](common-hardware/f-input-protection.md)、[G LDO/Buck/Boost/负压/隔离](common-hardware/g-power-conversion.md) → `references/common-hardware/g-power-conversion.md` (ok)
- L19 [unknown] [md)、[G LDO/Buck/Boost/负压/隔离](common-hardware/g-power-conversion.md)、[H 电池/充电/低功耗](common-hardware/h-battery.md) → `references/common-hardware/h-battery.md` (ok)
- L31 [unknown] [/共模、时序和线缆。
- **失效与 PCB：** 同名不同物理层、重复端接、上拉并联、跨参考分割、连接器镜像、保护泄放绕远。
- **深入：** [I²C](design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L31 [unknown] [跨参考分割、连接器镜像、保护泄放绕远。
- **深入：** [I²C](design-cards/interfaces/i01-i2c.md)、[I²C 缓冲](design-cards/interfaces/i02-i2c-buffer.md) → `references/design-cards/interfaces/i02-i2c-buffer.md` (ok)
- L31 [unknown] [/interfaces/i01-i2c.md)、[I²C 缓冲](design-cards/interfaces/i02-i2c-buffer.md)、[SPI](design-cards/interfaces/i03-spi.md) → `references/design-cards/interfaces/i03-spi.md` (ok)
- L31 [unknown] [interfaces/i02-i2c-buffer.md)、[SPI](design-cards/interfaces/i03-spi.md)、[SPI 多从机](design-cards/interfaces/i04-spi-multi.md) → `references/design-cards/interfaces/i04-spi-multi.md` (ok)
- L31 [unknown] [interfaces/i03-spi.md)、[SPI 多从机](design-cards/interfaces/i04-spi-multi.md)、[UART](design-cards/interfaces/i05-uart.md) → `references/design-cards/interfaces/i05-uart.md` (ok)
- L31 [unknown] [interfaces/i04-spi-multi.md)、[UART](design-cards/interfaces/i05-uart.md)、[RS-232](design-cards/interfaces/i06-rs232.md) → `references/design-cards/interfaces/i06-rs232.md` (ok)
- L31 [unknown] [s/interfaces/i05-uart.md)、[RS-232](design-cards/interfaces/i06-rs232.md)、[RS-485](design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L31 [unknown] [rds/interfaces/i06-rs232.md)、[RS-485](design-cards/interfaces/i07-rs485.md)、[CAN](design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L31 [unknown] [s/interfaces/i07-rs485.md)、[CAN](design-cards/interfaces/i08-can.md)、[USB Device](design-cards/interfaces/i09-usb-device.md) → `references/design-cards/interfaces/i09-usb-device.md` (ok)
- L31 [unknown] [es/i08-can.md)、[USB Device](design-cards/interfaces/i09-usb-device.md)、[USB-C 数据](design-cards/interfaces/i10-usbc-data.md) → `references/design-cards/interfaces/i10-usbc-data.md` (ok)
- L31 [unknown] [09-usb-device.md)、[USB-C 数据](design-cards/interfaces/i10-usbc-data.md)、[Ethernet](design-cards/interfaces/i11-ethernet.md) → `references/design-cards/interfaces/i11-ethernet.md` (ok)
- L31 [unknown] [aces/i10-usbc-data.md)、[Ethernet](design-cards/interfaces/i11-ethernet.md)、[电平转换](design-cards/interfaces/i12-level-shift.md) → `references/design-cards/interfaces/i12-level-shift.md` (ok)
- L32 [unknown] [et.md)、[电平转换](design-cards/interfaces/i12-level-shift.md)。
- **常用硬件：** [J 总线与外设](common-hardware/j-buses.md) → `references/common-hardware/j-buses.md` (ok)
- L38 [unknown] [B：** 天线净空按实际天线/模组逐层落实，考虑壳体/电池/紧固件；匹配网络值是调谐起点，认证不能自动代替整机认证。
- **深入：** [Wi-Fi/BLE](design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L38 [unknown] [，认证不能自动代替整机认证。
- **深入：** [Wi-Fi/BLE](design-cards/wireless/w01-wifi-ble.md)、[天线](design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L38 [unknown] [n-cards/wireless/w01-wifi-ble.md)、[天线](design-cards/wireless/w02-antenna.md)、[蜂窝](design-cards/wireless/w03-cellular.md) → `references/design-cards/wireless/w03-cellular.md` (ok)
- L38 [unknown] [cards/wireless/w02-antenna.md)、[蜂窝](design-cards/wireless/w03-cellular.md)、[GNSS](design-cards/wireless/w04-gnss.md) → `references/design-cards/wireless/w04-gnss.md` (ok)
- L39 [unknown] [cellular.md)、[GNSS](design-cards/wireless/w04-gnss.md)。
- **常用硬件：** [M 无线/时间/隔离](common-hardware/m-wireless-time.md) → `references/common-hardware/m-wireless-time.md` (ok)
- L45 [unknown] [出摆幅。
- **失效与 PCB：** 开路/误接/浪涌、保护漏电、参考动态负载、Kelvin 与敏感回流；温度传感器避开热源。
- **深入：** [分压](design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L45 [unknown] [elvin 与敏感回流；温度传感器避开热源。
- **深入：** [分压](design-cards/analog/a01-divider.md)、[运放缓冲](design-cards/analog/a02-opamp-buffer.md) → `references/design-cards/analog/a02-opamp-buffer.md` (ok)
- L45 [unknown] [rds/analog/a01-divider.md)、[运放缓冲](design-cards/analog/a02-opamp-buffer.md)、[差分放大](design-cards/analog/a03-diff-amp.md) → `references/design-cards/analog/a03-diff-amp.md` (ok)
- L45 [unknown] [/analog/a02-opamp-buffer.md)、[差分放大](design-cards/analog/a03-diff-amp.md)、[ADC 驱动](design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L45 [unknown] [ards/analog/a03-diff-amp.md)、[ADC 驱动](design-cards/analog/a04-adc-driver.md)、[基准](design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L45 [unknown] [sign-cards/analog/a04-adc-driver.md)、[基准](design-cards/analog/a05-vref.md)、[低侧采样](design-cards/analog/a06-low-side-sense.md) → `references/design-cards/analog/a06-low-side-sense.md` (ok)
- L45 [unknown] [ards/analog/a05-vref.md)、[低侧采样](design-cards/analog/a06-low-side-sense.md)、[高侧采样](design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L45 [unknown] [06-low-side-sense.md)、[高侧采样](design-cards/analog/a07-high-side-sense.md)、[4-20mA](design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L45 [unknown] [analog/a07-high-side-sense.md)、[4-20mA](design-cards/analog/a08-4-20ma.md)、[桥式传感](design-cards/analog/a09-bridge.md) → `references/design-cards/analog/a09-bridge.md` (ok)
- L45 [unknown] [gn-cards/analog/a08-4-20ma.md)、[桥式传感](design-cards/analog/a09-bridge.md)、[RTD/热敏](design-cards/analog/a10-rtd-thermistor.md) → `references/design-cards/analog/a10-rtd-thermistor.md` (ok)
- L46 [unknown] [ge.md)、[RTD/热敏](design-cards/analog/a10-rtd-thermistor.md)。
- **常用硬件：** [A 环境传感](common-hardware/a-environment.md) → `references/common-hardware/a-environment.md` (ok)
- L46 [unknown] [thermistor.md)。
- **常用硬件：** [A 环境传感](common-hardware/a-environment.md)、[B 光学/测距](common-hardware/b-optics.md) → `references/common-hardware/b-optics.md` (ok)
- L46 [unknown] [ommon-hardware/a-environment.md)、[B 光学/测距](common-hardware/b-optics.md)、[C 运动/位置](common-hardware/c-motion.md) → `references/common-hardware/c-motion.md` (ok)
- L46 [unknown] [ommon-hardware/b-optics.md)、[C 运动/位置](common-hardware/c-motion.md)、[D 力/压力/液位/流量](common-hardware/d-force.md) → `references/common-hardware/d-force.md` (ok)
- L46 [unknown] [置](common-hardware/c-motion.md)、[D 力/压力/液位/流量](common-hardware/d-force.md)、[E 电测](common-hardware/e-measurement.md) → `references/common-hardware/e-measurement.md` (ok)
- L52 [unknown] [释放时间。
- **失效与 PCB：** 控制器复位时误动作、直通、缺相/短路、感性回灌；功率回路、栅极环路、散热、采样地。
- **深入：** [低侧开关](design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L52 [unknown] [回灌；功率回路、栅极环路、散热、采样地。
- **深入：** [低侧开关](design-cards/drive/d01-low-side.md)、[高侧开关](design-cards/drive/d02-high-side.md) → `references/design-cards/drive/d02-high-side.md` (ok)
- L52 [unknown] [gn-cards/drive/d01-low-side.md)、[高侧开关](design-cards/drive/d02-high-side.md)、[继电器](design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)
- L52 [unknown] [(design-cards/drive/d02-high-side.md)、[继电器](design-cards/drive/d03-relay.md)、[半桥](design-cards/drive/d04-half-bridge.md) → `references/design-cards/drive/d04-half-bridge.md` (ok)
- L52 [unknown] [esign-cards/drive/d03-relay.md)、[半桥](design-cards/drive/d04-half-bridge.md)、[H 桥](design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L52 [unknown] [gn-cards/drive/d04-half-bridge.md)、[H 桥](design-cards/drive/d05-h-bridge.md)、[步进](design-cards/drive/d06-stepper.md) → `references/design-cards/drive/d06-stepper.md` (ok)
- L52 [unknown] [ign-cards/drive/d05-h-bridge.md)、[步进](design-cards/drive/d06-stepper.md)、[LED 恒流](design-cards/drive/d07-led-cc.md) → `references/design-cards/drive/d07-led-cc.md` (ok)
- L52 [unknown] [esign-cards/drive/d06-stepper.md)、[LED 恒流](design-cards/drive/d07-led-cc.md)、[加热](design-cards/drive/d08-heater.md) → `references/design-cards/drive/d08-heater.md` (ok)
- L53 [unknown] [7-led-cc.md)、[加热](design-cards/drive/d08-heater.md)。
- **常用硬件：** [K 开关/继电器/电机负载](common-hardware/k-drive.md) → `references/common-hardware/k-drive.md` (ok)
- L59 [unknown] [漏、数字模拟耦合、对外线缆保护与装配可见标识。蜂鸣器须辨压电/电磁和有源/无源；有源只需电平/开关，无源需方波频率与占空比。
- **深入：** [显示与背光](design-cards/wireless/w05-display.md) → `references/design-cards/wireless/w05-display.md` (ok)
- L59 [unknown] [关，无源需方波频率与占空比。
- **深入：** [显示与背光](design-cards/wireless/w05-display.md)、[Class-D](design-cards/wireless/w06-classd.md) → `references/design-cards/wireless/w06-classd.md` (ok)
- L60 [unknown] [lay.md)、[Class-D](design-cards/wireless/w06-classd.md)。
- **常用硬件：** [L 显示/声音/按键](common-hardware/l-hmi.md) → `references/common-hardware/l-hmi.md` (ok)
- L66 [unknown] [SPI 模式的上下拉照搬到 QSPI，不把所有 SDIO/DDR 网机械等长；依据时序分组和叠层/过孔延迟设置约束。
- **深入：** [SPI Flash](design-cards/wireless/w07-spi-flash.md) → `references/design-cards/wireless/w07-spi-flash.md` (ok)
- L66 [unknown] [孔延迟设置约束。
- **深入：** [SPI Flash](design-cards/wireless/w07-spi-flash.md)、[microSD](design-cards/wireless/w08-microsd.md) → `references/design-cards/wireless/w08-microsd.md` (ok)
- L72 [unknown] [护协调。
- **失效与 PCB：** 跨屏障铜/孔/测试夹具/紧固件破坏隔离、采样/调试误短接；预留可测点但不因此跨接隔离。
- **深入：** [热插拔](design-cards/power/p10-hot-swap.md) → `references/design-cards/power/p10-hot-swap.md` (ok)
- L72 [unknown] [调试误短接；预留可测点但不因此跨接隔离。
- **深入：** [热插拔](design-cards/power/p10-hot-swap.md)、[eFuse](design-cards/power/p11-efuse.md) → `references/design-cards/power/p11-efuse.md` (ok)
- L72 [unknown] [gn-cards/power/p10-hot-swap.md)、[eFuse](design-cards/power/p11-efuse.md)、[RS-485](design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L72 [unknown] [gn-cards/power/p11-efuse.md)、[RS-485](design-cards/interfaces/i07-rs485.md)、[CAN](design-cards/interfaces/i08-can.md) → `references/design-cards/interfaces/i08-can.md` (ok)
- L73 [unknown] [s/i07-rs485.md)、[CAN](design-cards/interfaces/i08-can.md)。
- **常用硬件：** [E5 隔离电流](common-hardware/e-measurement.md) → `references/common-hardware/e-measurement.md` (ok)
- L73 [unknown] [8-can.md)。
- **常用硬件：** [E5 隔离电流](common-hardware/e-measurement.md)、[G6 隔离 DC/DC](common-hardware/g-power-conversion.md) → `references/common-hardware/g-power-conversion.md` (ok)
- L73 [unknown] [e-measurement.md)、[G6 隔离 DC/DC](common-hardware/g-power-conversion.md)、[M8 数字隔离器](common-hardware/m-wireless-time.md) → `references/common-hardware/m-wireless-time.md` (ok)
- L77 [background] [与反灌、参考地/隔离/屏蔽、模块内部已集成的外围、固件初始化与硬件版本、机械/热/天线/测试空间。至少 8 个“单模块正常、组合失败”的案例见 [组合与接口契约](module-integration.md) → `references/module-integration.md` (ok)

### `references/module-integration.md`

- 标题：跨模块组合与接口契约
- 行/字符/字节：847 / 39156 / 74891
- SHA-256：`c3211488740f5eba3d5d447d973d098d4638b8cf08c6d279225c06921157b576`

- L404 [unknown] [冲，为 3 级。
- **边界与来源：** 70/150/180 pF 是算例假设，不是实测；其他总线电容必须重算。IF-S01、IF-S02；相关 [F06](failures/f06-i2c-pullup.md) → `references/failures/f06-i2c-pullup.md` (ok)
- L422 [unknown] [改装配为 2 级。
- **边界与来源：** 只适用于 ESP32-C3 的 GPIO2/8/9；其他系列 strap 脚不同。MCU-S04；相关 [F03](failures/f03-esp32-strap.md) → `references/failures/f03-esp32-strap.md` (ok)

### `references/network-discipline.md`

- 标题：网络纪律与服务阻塞
- 行/字符/字节：31 / 1283 / 2935
- SHA-256：`fff41df31f4fc95d38d3d05680fe576f8f613bee662b82fbcaee320c6255cbd0`

### `references/offline-regression.md`

- 标题：离线回归、证据绑定与冻结基准
- 行/字符/字节：152 / 7500 / 11686
- SHA-256：`a4ffcc8063b15e334520c1027c7b77ffecab52bc0015df291d08dd20409cab1c`

- L102 [required_read] [带 `rotation/layer`；失败明确 rejected，不静默改成任意摆放。

## 8. 原理图离线图面回归

先按 [原理图排版与看图验收](schematic-layout.md) → `references/schematic-layout.md` (ok)

### `references/offline-tools.md`

- 标题：可选离线辅助：续航与原理图几何
- 行/字符/字节：174 / 13261 / 22919
- SHA-256：`2f6af80e756f3aac8a93e9a97f6819b56a69bdc1ffb8fbd77bc896f5eaf77b01`

- L5 [conditional_read] [补充可审查的计算与候选问题，不重复造一个独立EDA验证器。

需要完整离线回归、证据 manifest 绑定、冻结基准或图面叠加图时，先读 [离线回归与基准](offline-regression.md) → `references/offline-regression.md` (ok)
- L9 [example] [
## 续航：先换算到电池输入侧

运行 `python scripts/power_budget.py budget.json`。输入见 [虚构续航算例](../assets/example-power-budget.json) → `assets/example-power-budget.json` (ok)
- L30 [example] [`python scripts/sch_layout_check.py layout.json`。从当前EDA读入每页的几何，必要时拆页。输入见 [虚构几何算例](../assets/example-layout.json) → `assets/example-layout.json` (ok)
- L138 [unknown] [ates` / `pcb-escapes` / `pcb-power` / `pcb-diff` 做离线约束、局部模板、候选与回读比较，详见 [PCB执行工作流](pcb-execution.md) → `references/pcb-execution.md` (ok)
- L142 [unknown] [ 新增 `buck`、`boost`、`adc_settle`、`current_sense`、`wire` 模式；字段、公式前提和不能证明的内容见 [计算手册](calculations/README.md) → `references/calculations/README.md` (ok)
- L144 [unknown] [ts/simulation/rc_sample.cir` 是同一网络的 SPICE 计划文件，当前标注 `NOT RUN`，不能声称已运行。
- [仿真与测量](simulation-measurement.md) → `references/simulation-measurement.md` (ok)

### `references/part-selection.md`

- 标题：选型、BOM与装配变体
- 行/字符/字节：72 / 3350 / 6696
- SHA-256：`443596e8298fded75f1c59e08f7c65cd60410506e3943ac7283ffb027eaba13f`

- L14 [unknown] [不强制每个稀有/指定器件都凑一个未经验证备选。

## 先定装配方式，再选封装

封装的第一约束是“谁来装”，不是库里有什么。开工时按 [G0 需求门禁](design-gates.md) → `references/design-gates.md` (ok)
- L24 [unknown] [` / `tht` / `dnp`），两者不要混用。

- 手焊默认 0603，0402/1005 只用于 SMT（本轮任务书口径）。这与 [制造与交付路线](manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L24 [unknown] [焊默认 0603，0402/1005 只用于 SMT（本轮任务书口径）。这与 [制造与交付路线](manufacturing-routes.md)、[无源件选型](selection/passives.md) → `references/selection/passives.md` (ok)
- L27 [unknown] [是 EDA land pattern 名；两者不能互相替代。
- 机械/热条件在选封装时一起核对：蜂鸣器声孔、电位器螺丝刀空间、NTC 热隔离，见 [机械约束](../assets/docs/mechanical.md) → `assets/docs/mechanical.md` (ok)
- L27 [unknown] [选封装时一起核对：蜂鸣器声孔、电位器螺丝刀空间、NTC 热隔离，见 [机械约束](../assets/docs/mechanical.md) 与 [热敏电阻布置](../assets/docs/thermal-sensor.md) → `assets/docs/thermal-sensor.md` (ok)
- L49 [unknown] [ BOM 看起来齐全过关。
- C 号是身份，不是可得性：有 C 号不代表有库存、能贴、价格合适。库存、MOQ/包装、SMT 可贴状态分别核对，见 [立创商城](lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L50 [unknown] [ BOM 先导出并保留：`easyeda bom export --type csv --enrich=false`；富化失败不阻断设计，处理流程见 [立创商城](lcsc-sourcing.md) → `references/lcsc-sourcing.md` (ok)
- L51 [example] [=false`；富化失败不阻断设计，处理流程见 [立创商城](lcsc-sourcing.md)。
- 字段模板与检查：[parts.example.json](../assets/parts.example.json) → `assets/parts.example.json` (ok)
- L62 [unknown] [连接器核对接触额定与升温。
指定器件不合适时给出“保留它需要改变什么”和“替代方案改变什么”，不要偷偷换型号。

需要可直接填写的核算表时用 [设计核算表](../assets/design-calc.md) → `assets/design-calc.md` (ok)
- L62 [unknown] [变什么”，不要偷偷换型号。

需要可直接填写的核算表时用 [设计核算表](../assets/design-calc.md)；通用公式与算例库见 [计算手册](calculations/README.md) → `references/calculations/README.md` (ok)
- L69 [unknown] [关控制；不要把0Ω当作总线终端本体。

替代料分级（直接替换 / 需改阻容或固件 / 需改原理图封装PCB / 资料不足）、逐项核对和检索顺序见 [替代分类](selection/replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L69 [unknown] [需改原理图封装PCB / 资料不足）、逐项核对和检索顺序见 [替代分类](selection/replacement-classes.md) 与 [器件选型资料](selection/README.md) → `references/selection/README.md` (ok)
- L71 [conditional_read] [md) 与 [器件选型资料](selection/README.md)。

需要完整功耗/结温、热阻指标、瞬态及PCB/外壳测量方法时，按需读 [板级热专题](thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/pcb-execution.md`

- 标题：PCB 执行工作流：实测几何、约束、局部模板与回读
- 行/字符/字节：402 / 22888 / 33459
- SHA-256：`ebfc7e630fdb728fb75124c38edc406524aea8d1b2b6744bd578f62c82c07862`

- L5 [required_read] [可执行的约束、局部模板、候选与回读检查上；不承诺高速 DDR、复杂 FPGA、RF、离线市电、安规隔离或大功率变换器的自动设计。

先读 [PCB 工程习惯](pcb.md) → `references/pcb.md` (ok)
- L5 [required_read] [上；不承诺高速 DDR、复杂 FPGA、RF、离线市电、安规隔离或大功率变换器的自动设计。

先读 [PCB 工程习惯](pcb.md) 与 [EDA 执行](eda-execution.md) → `references/eda-execution.md` (ok)
- L5 [required_read] [令、参数与返回字段以当前 `easyeda pcb <cmd> --help` 为准；逐命令的 argv、必需/可选参数、输出角色与校验点见 [PCB 命令映射](pcb-command-map.json) → `references/pcb-command-map.json` (ok)
- L102 [unknown] [e-copper --out board.json
```

导入后仍必须回读：`import-changes` 不删除原理图已移除的器件（见 [工具陷阱](tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L346 [unknown] [`pcb-final-top.png` 等），优先 `*-final*`，`--file ROLE=PATH` 可覆盖任一角色。角色与命令见 [PCB 命令映射](pcb-command-map.json) → `references/pcb-command-map.json` (ok)
- L365 [unknown] [`/`not_run`，不能写 pass；报告必须列 `not_checked`。

## 11. 丝印与交付

交付前逐项核对 [PCB 交付检查清单](../assets/pcb-delivery-checklist.md) → `assets/pcb-delivery-checklist.md` (ok)

### `references/pcb-lessons.md`

- 标题：PCB经验：解释原因，并落到真实铜与装配
- 行/字符/字节：74 / 3082 / 7114
- SHA-256：`892574ef1da4565c0af92a4e262483d95a3714abf61e1087e913a2f95221941a`

- L3 [unknown] [# PCB经验：解释原因，并落到真实铜与装配

吸收hw-eda-engineer 0.6.0的经验表达，补充已有 [布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L3 [unknown] [铜与装配

吸收hw-eda-engineer 0.6.0的经验表达，补充已有 [布局细节](pcb-placement-details.md)、[布线细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L3 [unknown] [验表达，补充已有 [布局细节](pcb-placement-details.md)、[布线细节](pcb-routing-details.md) 和 [制造细节](manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L17 [example] [一个孔。
- **怎么查**：查看实际层叠、铜连接和焊盘到参考路径；有瞬态目标时进行匹配的PI分析/测量。关联PL17/18，查 [RP2040原厂布局资料等](design-experience.md) → `references/design-experience.md` (ok)
- L23 [external_reference] [、屏蔽与禁布依实际结构和原厂布局。
- **怎么查**：从真实铜逐段标出关键电流及返回、SW区和反馈取样点；检查热源对电池/温感影响。参考 [TI寻找开关回路](https://www.ti.com/document-viewer/lit/html/SSZTBF4/GUID-095BD04D-6DAF-42E7-9AA0-72CB14E1F58C) → `https://www.ti.com/document-viewer/lit/html/SSZTBF4/GUID-095BD04D-6DAF-42E7-9AA0-72CB14E1F58C` (external)
- L37 [external_reference] [**：回读插座脚序、正反插连接和实际铜；按适用速率复核通道预算/测试，不能因为USB 2.0布线经验就放行高速SuperSpeed。参考 [TI SLLA414](https://www.ti.com/lit/an/slla414/slla414.pdf) → `https://www.ti.com/lit/an/slla414/slla414.pdf` (external)
- L43 [unknown] [*：逐层看实际铜、过孔、壳体/电池/金属固定件，记录对应原厂图；射频效果与起振可靠性仍需相应实测。关联PL19/24、RT24–26与 [Espressif指南](design-experience.md) → `references/design-experience.md` (ok)
- L69 [unknown] [脚本文件清点、固定字段`saved:true`或`passed:true`都不能证明保存/放行；不存在的检查器不得写成已执行。关联RT27/32–35与 [交付](jlc-handoff.md) → `references/jlc-handoff.md` (ok)
- L73 [conditional_read] [指定原厂链接支持其相应机制；仍按任务读取实际型号/板厂订单。制造边距、丝印/阻焊、孔径与SMT单双面能力查询当前渠道，不能沿用来稿的固定值。项目经验按 [经验库](design-experience.md) → `references/design-experience.md` (ok)

### `references/pcb-placement-details.md`

- 标题：PCB布局细节
- 行/字符/字节：52 / 2778 / 6812
- SHA-256：`6eebb14455f121a609c6a508445575bb42224769783c54ea128a6dde6198e8d9`

- L3 [required_read] [# PCB布局细节

先读 [PCB工程习惯](pcb.md) → `references/pcb.md` (ok)
- L3 [required_read] [务选择PL条目，并将实际位置、禁止区域与关键回路保存到当前执行器支持的规划/约束中。只读任务不移动器件，优化任务不擅自解锁已有机械固定件。依据与出处见 [经验库](design-experience.md) → `references/design-experience.md` (ok)
- L51 [conditional_read] [3D/机械文件；3D看不到的铜回路仍需2D检查，未拿到的模型不算无碰撞。

需要完整功耗/结温、热阻指标、瞬态及PCB/外壳测量方法时，按需读 [板级热专题](thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/pcb-routing-details.md`

- 标题：PCB布线、回流与铺铜细节
- 行/字符/字节：55 / 2850 / 7074
- SHA-256：`c515997a7377f434e7b69485ff03ffd639466083c0b2d264eb69bfbbe079cabe`

- L3 [unknown] [PCB布线、回流与铺铜细节

先确认层叠、铜厚、材料、实际厂规和网络类，执行当前工具能够表达的约束；未知不猜。RT条目按网络类别应用，依据与来源见 [经验库](design-experience.md) → `references/design-experience.md` (ok)
- L54 [unknown] [报告剩余网络与原因；外部路由回导后仍检查网络、规则、层与机械约束，不能把DSN导出当PCB完成。

## 电源主干与加宽受限

按 [电源路径与走廊预检](power-routing-preflight.md) → `references/power-routing-preflight.md` (ok)

### `references/pcb-routing-strategy.md`

- 标题：PCB布线策略：层数、电源地与布线计划
- 行/字符/字节：317 / 14586 / 28042
- SHA-256：`00061e3e5f29a051d362623f223380a322c336729b90d7c079caab2dbb902c81`

- L5 [required_read] [什么以及怎样证明布通。它接在 G3 布局冻结之后使用；G4 电源地策略与 G3 并列，必须在真正布线前声明；G5 是布线退出条件。

先读 [PCB工程习惯](pcb.md) → `references/pcb.md` (ok)
- L5 [required_read] [布局冻结之后使用；G4 电源地策略与 G3 并列，必须在真正布线前声明；G5 是布线退出条件。

先读 [PCB工程习惯](pcb.md) 与 [工程工作流](workflow.md) → `references/workflow.md` (ok)
- L5 [required_read] [

先读 [PCB工程习惯](pcb.md) 与 [工程工作流](workflow.md)。阶段门禁名称、状态词与证据细节见 [design-gates.md](design-gates.md) → `references/design-gates.md` (ok)
- L5 [required_read] [orkflow.md)。阶段门禁名称、状态词与证据细节见 [design-gates.md](design-gates.md)。逐项电气细节在 [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L5 [required_read] [.md](design-gates.md)。逐项电气细节在 [布线与回流细节](pcb-routing-details.md)（RT 编号）与 [PCB布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L5 [required_read] [细节](pcb-placement-details.md)（PL 编号）；本页只引用编号，不复制条款正文。层数、铜厚、孔/槽与工艺能力按 [嘉立创PCB生产规则](jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L5 [required_read] [厚、孔/槽与工艺能力按 [嘉立创PCB生产规则](jlc-pcb-rules.md) 的当期订单条件核对，本页不复述能力数值。计划落到可填写表格：[布线计划模板](../assets/routing-plan.md) → `assets/routing-plan.md` (ok)
- L24 [unknown] [好；无内层对位问题 | 压合与对位步骤多，内层不可见，返修与改板成本高 | 按实际装配方式（SMT/手焊）与当期订单工艺核对 [jlc-pcb-rules.md](jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L92 [unknown] [度并说明为什么铺铜不能覆盖，改完重新铺铜、重新 DRC。
- GND 走线宽度与是否存在要在计划中给出依据；是否有自动检查以 [design-gates.md](design-gates.md) → `references/design-gates.md` (ok)
- L186 [unknown] [，响应更真实但增加连接器、线束固定与抗干扰成本；在布局前决定并记录取舍。
- 距离用实际焊盘/封装几何测量，不填估算值；记录模板与证据要求见 [温度传感器记录](../assets/docs/thermal-sensor.md) → `assets/docs/thermal-sensor.md` (ok)
- L230 [unknown] [开对应文档：

| 主题 | 引用编号 | 文档 |
|---|---|---|
| 载流、线宽、电源分配 | RT01–RT03 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L231 [background] [T03 | [布线与回流细节](pcb-routing-details.md) |
| 参考层、换层回流、地路径 | RT04–RT06 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L232 [unknown] [ [布线与回流细节](pcb-routing-details.md) |
| Kelvin、保护泄放、栅驱、隔离 | RT07–RT10 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L233 [unknown] [ [布线与回流细节](pcb-routing-details.md) |
| 阻抗、差分、时序、串扰、过孔与支路 | RT11–RT20 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L234 [unknown] [11–RT20 | [布线与回流细节](pcb-routing-details.md) |
| 模拟、时钟、RF | RT21–RT26 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L235 [unknown] [| [布线与回流细节](pcb-routing-details.md) |
| 铜区、孤岛、热连接、缝合、铜到边 | RT27–RT31 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L236 [unknown] [线与回流细节](pcb-routing-details.md) |
| 移动后重验、实际连通、视觉复核、诚实记录 | RT32–RT35 | [布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L237 [unknown] [ [布线与回流细节](pcb-routing-details.md) |
| 电源回路放件、输入电容、保护靠边界 | PL09–PL15 | [PCB布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L238 [background] [节](pcb-placement-details.md) |
| 去耦、敏感节点、参考与采样 | PL17–PL18、PL21–PL23 | [PCB布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L239 [unknown] [布局细节](pcb-placement-details.md) |
| 通道预留、移动后重验、布局验收 | PL29、PL31–PL32 | [PCB布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L243 [unknown] [定义；本页不新增、不改写、不扩写编号含义。
- 若本页与编号原文冲突，以编号原文和当前器件/板厂资料为准，并回改本页。
- 证据记录方式见 [证据与轻量记录](evidence.md) → `references/evidence.md` (ok)
- L243 [unknown] [编号原文和当前器件/板厂资料为准，并回改本页。
- 证据记录方式见 [证据与轻量记录](evidence.md)；EDA 前台/重载/保存边界见 [EDA执行](eda-execution.md) → `references/eda-execution.md` (ok)
- L296 [unknown] [3 | score/crossings 达标，0 overlap/off-board，逃逸 ≤5 mm 且避开 slot |
| 布线计划 | [布线计划模板](../assets/routing-plan.md) → `assets/routing-plan.md` (ok)

### `references/pcb.md`

- 标题：PCB工程习惯
- 行/字符/字节：52 / 2817 / 6487
- SHA-256：`deaf094fddc7f4f5f55bc0b860d0928710c59ee432ffffd3ac4b00bc57484e87`

- L3 [unknown] [# PCB工程习惯

目标为嘉立创制造时，在布局前读 [生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)
- L3 [unknown] [# PCB工程习惯

目标为嘉立创制造时，在布局前读 [生产规则接入](jlc-production.md)、[PCB生产规则](jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L3 [unknown] [创制造时，在布局前读 [生产规则接入](jlc-production.md)、[PCB生产规则](jlc-pcb-rules.md) 与适用的 [SMT生产规则](jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)
- L5 [conditional_read] [边、Mark、装配间隔等工具未覆盖项单独检查。改层叠/铜厚/孔工艺/贴装服务后重查，不沿用旧DRC结论。

需要解释布局/布线问题时，按需读 [PCB机制卡](pcb-lessons.md) → `references/pcb-lessons.md` (ok)
- L7 [conditional_read] [

需要解释布局/布线问题时，按需读 [PCB机制卡](pcb-lessons.md)，将动作落实到实际焊盘、铜层、装配与复验。

按阶段加载 [布局细节](pcb-placement-details.md) → `references/pcb-placement-details.md` (ok)
- L7 [conditional_read] [lessons.md)，将动作落实到实际焊盘、铜层、装配与复验。

按阶段加载 [布局细节](pcb-placement-details.md)、[布线策略](pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L7 [conditional_read] [
按阶段加载 [布局细节](pcb-placement-details.md)、[布线策略](pcb-routing-strategy.md)、[布线与回流细节](pcb-routing-details.md) → `references/pcb-routing-details.md` (ok)
- L7 [conditional_read] [s.md)、[布线策略](pcb-routing-strategy.md)、[布线与回流细节](pcb-routing-details.md)、[制造与首板细节](manufacturing-details.md) → `references/manufacturing-details.md` (ok)
- L7 [conditional_read] [[布线与回流细节](pcb-routing-details.md)、[制造与首板细节](manufacturing-details.md)，再选择 [领域易漏项](domain-design-details.md) → `references/domain-design-details.md` (ok)
- L7 [conditional_read] [facturing-details.md)，再选择 [领域易漏项](domain-design-details.md) 的适用小节；来源和经验适用性见 [经验库](design-experience.md) → `references/design-experience.md` (ok)
- L24 [unknown] [。距离按实际焊盘/走线几何测量，不用封装中心距离。

## 布线前
先完成层数与电源/地决策并落盘，再动第一根线；决策矩阵、命令与反例见 [PCB布线策略](pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L26 [unknown] [GND 电源归属写入 `design-state.json`；中途改层数或改策略回到 G3/G4 重新声明，旧 DRC/铺铜结论作废。
- 用 [布线计划模板](../assets/routing-plan.md) → `assets/routing-plan.md` (ok)
- L42 [unknown] [
明确板内电源层与地层的实际类型和连接，不能把命名为GND的层当作已正确铺铜。
温度传感器（NTC/RTD/数字）的热布局、自热与校准记录用 [温度传感器模板](../assets/docs/thermal-sensor.md) → `assets/docs/thermal-sensor.md` (ok)

### `references/power-routing-preflight.md`

- 标题：电源路径审计与宽走廊规划
- 行/字符/字节：49 / 2268 / 4635
- SHA-256：`4538257442dee4f05803f449de6fa41aeb2265484b645b0a7127844bf5454a31`

### `references/power.md`

- 标题：电源、功率与保护
- 行/字符/字节：32 / 1386 / 3380
- SHA-256：`6cc2c2bb33caeadb0c527abd70695af2fa99db2b033c77955da1a8615c41c0b8`

- L3 [unknown] [# 电源、功率与保护

> 本文保留电源树与通用判断。具体拓扑的设计方法、算例、选型和 PCB 要求见 [设计卡库](design-cards/README.md) → `references/design-cards/README.md` (ok)
- L17 [unknown] [用 ΔV≈ΔI·Δt/C+ΔI·ESR 作粗估，必须注明控制环响应、ESL、布线寄生与有效电容限制。

## 电池与多源供电
在方案阶段按 [续航工具契约](offline-tools.md) → `references/offline-tools.md` (ok)
- L31 [conditional_read] [elvin线、散热焊盘/过孔和保护泄放路径；原理图正确仍可能因布局失败。

需要完整功耗/结温、热阻指标、瞬态及PCB/外壳测量方法时，按需读 [板级热专题](thermal/topic.md) → `references/thermal/topic.md` (ok)

### `references/product-acceptance.md`

- 标题：以原始用途验收，而不是以文件数量验收
- 行/字符/字节：33 / 1172 / 3096
- SHA-256：`ea9008a6fccb91e668403714ae854675478d898c2bc1d8866037c64e0747220e`

### `references/product-example.md`

- 标题：演练案例：花盆缺水时手机提醒
- 行/字符/字节：51 / 1818 / 4760
- SHA-256：`4d2669856ac445d59023ce0a28f8743b21e26b1423f107f0f193e055a0c3c227`

- L50 [unknown] [明与证据。没有实物时只能交付准备成果和接续条件。

更深入的项目样本（低功耗无线传感、工业 RS485/4-20mA 采集、低压电机驱动）见 [完整项目样本](projects/README.md) → `references/projects/README.md` (ok)

### `references/project-coherence.md`

- 标题：一份项目记录，关联所有交付
- 行/字符/字节：36 / 1229 / 3009
- SHA-256：`38b5fab7aba0ba6153fb6ea3b0dc498158abfba925eeb46f47c054d1ac7b1585`

### `references/projects/README.md`

- 标题：完整项目样本
- 行/字符/字节：11 / 610 / 964
- SHA-256：`e4f7c1f392ccc1a8d9923a509c9bfbfa7227c4c7902854eb333b62c38b3e704a`

- L7 [unknown] [---|---|---|
| P01：低功耗无线传感器（1S 锂电 + BLE 模组） | [p01-low-power-wireless-sensor.md](p01-low-power-wireless-sensor.md) → `references/projects/p01-low-power-wireless-sensor.md` (ok)
- L8 [unknown] [资料分析 |
| P02：工业 RS485 / 4–20 mA 采集节点（24 V 供电） | [p02-industrial-rs485-analog.md](p02-industrial-rs485-analog.md) → `references/projects/p02-industrial-rs485-analog.md` (ok)
- L9 [unknown] [| 离线规划/资料分析 |
| P03：低压有刷电机驱动（12 V / 1.5 A 连续） | [p03-low-voltage-power-drive.md](p03-low-voltage-power-drive.md) → `references/projects/p03-low-voltage-power-drive.md` (ok)
- L10 [unknown] [wer-drive.md) | 离线规划/资料分析 |
| P04：USB 供电 ESP8266 小板（F1） | [p04-usb-mcu-board.md](p04-usb-mcu-board.md) → `references/projects/p04-usb-mcu-board.md` (ok)

### `references/projects/p01-low-power-wireless-sensor.md`

- 标题：P01：低功耗无线传感器（1S 锂电 + BLE 模组）
- 行/字符/字节：496 / 24397 / 41994
- SHA-256：`9402d1ee2cfb60e28dc481ca3fd39d5d54f0c757ea736be991484a30d7dfd786`

- L19 [unknown] [、热/射频/功耗实测、EMC 与安规签核、立创商城/嘉立创当天下单页面的实时字段。
>
> **关联设计卡/工具：** [PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md) → `references/design-cards/power/p04-buck-boost.md` (ok)
- L19 [unknown] [具：** [PWR-04 Buck-Boost](../design-cards/power/p04-buck-boost.md)、[MCU-02 模组最小系统](../design-cards/mcu/m02-module-mcu.md) → `references/design-cards/mcu/m02-module-mcu.md` (ok)
- L19 [unknown] [t.md)、[MCU-02 模组最小系统](../design-cards/mcu/m02-module-mcu.md)、[RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md) → `references/design-cards/wireless/w01-wifi-ble.md` (ok)
- L19 [unknown] [cu.md)、[RF-01 Wi-Fi/BLE 模组](../design-cards/wireless/w01-wifi-ble.md)、[IF-01 I²C](../design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L19 [unknown] [w01-wifi-ble.md)、[IF-01 I²C](../design-cards/interfaces/i01-i2c.md)、[ANA-01 分压采样](../design-cards/analog/a01-divider.md) → `references/design-cards/analog/a01-divider.md` (ok)
- L19 [unknown] [erfaces/i01-i2c.md)、[ANA-01 分压采样](../design-cards/analog/a01-divider.md)、[离线工具契约](../offline-tools.md) → `references/offline-tools.md` (ok)
- L19 [unknown] [压采样](../design-cards/analog/a01-divider.md)、[离线工具契约](../offline-tools.md)、[连接表契约](../connectivity.md) → `references/connectivity.md` (ok)
- L246 [unknown] [压接、线缆额定温度、短路/保险协调。

## 5. 原理图连接基线

**状态：** 逻辑连接表已写入 [`p01-connectivity.json`](../../assets/projects/p01-connectivity.json) → `assets/projects/p01-connectivity.json` (ok)
- L359 [unknown] [/Rotation/mm/T/B | 未导出 |
| 钢网 | 单面；模组焊盘与 0402 开孔；厚度待定 | 未下单 |

**对账顺序（与 [制造路线](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)

### `references/projects/p02-industrial-rs485-analog.md`

- 标题：P02：工业 RS485 / 4–20 mA 采集节点（24 V 供电）
- 行/字符/字节：504 / 23030 / 37626
- SHA-256：`bf2296109ff5cdbabc7fa831485b620d8ba5c8f65d68c52c2a35540b57db4d48`

- L19 [example] [的完整手册、隔离耐压与安规认证、环路合规电压实测、EMC/浪涌测试、当天的商城/SMT 字段。
>
> **关联设计卡/工具：** [PWR-02 Buck](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L19 [example] [
>
> **关联设计卡/工具：** [PWR-02 Buck](../design-cards/power/p02-buck.md)、[PWR-01 LDO](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)
- L19 [example] [R-01 LDO](../design-cards/power/p01-ldo.md)；制造包组织示例见 [manufacturing-routes.md §9](../manufacturing-routes.md#9-项目样本24-v-rs485-控制器离线规划) → `references/manufacturing-routes.md` (ok) #9-项目样本24-v-rs485-控制器离线规划 ok
- L19 [example] [routes.md §9](../manufacturing-routes.md#9-项目样本24-v-rs485-控制器离线规划)、[IF-07 RS-485](../design-cards/interfaces/i07-rs485.md) → `references/design-cards/interfaces/i07-rs485.md` (ok)
- L19 [example] [控制器离线规划)、[IF-07 RS-485](../design-cards/interfaces/i07-rs485.md)、[ANA-08 4–20 mA](../design-cards/analog/a08-4-20ma.md) → `references/design-cards/analog/a08-4-20ma.md` (ok)
- L19 [example] [/i07-rs485.md)、[ANA-08 4–20 mA](../design-cards/analog/a08-4-20ma.md)、[ANA-05 基准](../design-cards/analog/a05-vref.md) → `references/design-cards/analog/a05-vref.md` (ok)
- L19 [example] [og/a08-4-20ma.md)、[ANA-05 基准](../design-cards/analog/a05-vref.md)、[ANA-04 SAR 驱动](../design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L19 [example] [vref.md)、[ANA-04 SAR 驱动](../design-cards/analog/a04-adc-driver.md)、[MCU-01 裸 MCU](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)

### `references/projects/p03-low-voltage-power-drive.md`

- 标题：P03：低压有刷电机驱动（12 V / 1.5 A 连续）
- 行/字符/字节：421 / 18542 / 30619
- SHA-256：`158d0f709c3e9b6180c8ef48a7294485247ac3efa36af14677e097225a5c479e`

- L19 [unknown] [、DRV8871 的 max Rds(on) 与热阻曲线、实测温升/电流波形/EMC。
>
> **关联设计卡/工具：** [DRV-05 H 桥/有刷电机](../design-cards/drive/d05-h-bridge.md) → `references/design-cards/drive/d05-h-bridge.md` (ok)
- L19 [unknown] [联设计卡/工具：** [DRV-05 H 桥/有刷电机](../design-cards/drive/d05-h-bridge.md)、[DRV-01 低侧开关](../design-cards/drive/d01-low-side.md) → `references/design-cards/drive/d01-low-side.md` (ok)
- L19 [unknown] [h-bridge.md)、[DRV-01 低侧开关](../design-cards/drive/d01-low-side.md)、[ANA-07 高侧电流采样](../design-cards/analog/a07-high-side-sense.md) → `references/design-cards/analog/a07-high-side-sense.md` (ok)
- L19 [unknown] [.md)、[ANA-07 高侧电流采样](../design-cards/analog/a07-high-side-sense.md)、[PWR-02 Buck](../design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L19 [unknown] [high-side-sense.md)、[PWR-02 Buck](../design-cards/power/p02-buck.md)、[PWR-01 LDO](../design-cards/power/p01-ldo.md) → `references/design-cards/power/p01-ldo.md` (ok)

### `references/projects/p04-usb-mcu-board.md`

- 标题：P04：USB 供电 MCU 小板（F1）
- 行/字符/字节：188 / 6868 / 12099
- SHA-256：`1e7a709553db1276bd6b1f0ad0563574dc33de58798a2f935a5edadbbbcad493`

- L184 [unknown] [：`docs/evidence/f1-2026-10-22/README.md`（仓库内证据，未随 Skill 安装）。
- 执行契约与版本边界：[EDA执行](../eda-execution.md) → `references/eda-execution.md` (ok)

### `references/review.md`

- 标题：设计审查、故障与验证
- 行/字符/字节：37 / 1367 / 3471
- SHA-256：`54a3c29949d8941d92b89e2ab0add7605c09f9aa9ef028408acd4254321541b5`

- L3 [unknown] [# 设计审查、故障与验证

嘉立创制造任务按 [生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)
- L5 [conditional_read] [工艺优化。厂方报告未取得时保持未执行，不把所有目录建议当全板硬错误。

对关键缺陷用“条件/原因 → 设计动作 → 检查证据”说明，可按需用 [原理图机制卡](schematic-lessons.md) → `references/schematic-lessons.md` (ok)
- L5 [conditional_read] [。

对关键缺陷用“条件/原因 → 设计动作 → 检查证据”说明，可按需用 [原理图机制卡](schematic-lessons.md) 与 [PCB机制卡](pcb-lessons.md) → `references/pcb-lessons.md` (ok)
- L5 [conditional_read] [说明，可按需用 [原理图机制卡](schematic-lessons.md) 与 [PCB机制卡](pcb-lessons.md)。几何脚本仅按 [离线工具契约](offline-tools.md) → `references/offline-tools.md` (ok)

### `references/schematic-authoring.md`

- 标题：原理图绘图执行方法（0.9）
- 行/字符/字节：148 / 6643 / 12479
- SHA-256：`7283016368fb7beb7c3e704e640fd6bc08e56dff594b3cf6c7781998ca610309`

- L22 [unknown] [
## 2. 用拓扑决定空间

1. 列出主信号链、辅助供电/参考、反馈回路、外部接口。器件仅归属一个功能模块，模块之间列出实际网络。
2. 用 [模板](schematic-recipes.md) → `references/schematic-recipes.md` (ok)
- L28 [unknown] [、所有文字、导线/标记，再加标题、用途和边距生成框。整页留白为阅读服务；不为了填满纸张拉长导线，也不把主链挤在上方狭窄条带。

已有布局管线使用 [布局引擎](schematic-layout-engine.md) → `references/schematic-layout-engine.md` (ok)

### `references/schematic-benchmarks.md`

- 标题：原理图排版基准集（8类）
- 行/字符/字节：64 / 3164 / 6496
- SHA-256：`bea6403fa6d211bfaa4a3c86e715dd9bf5d07a6b204f8b9a07a7d57ea2bc766d`

- L30 [example] [RST/SWDIO`、`C1`、`R1`、`J1` 的网络关系，不证明U1真实脚号、复用功能或电气兼容。真实任务必须从适用手册/库回读物理脚，再按 [连接表契约](connectivity.md) → `references/connectivity.md` (ok)
- L32 [unknown] [ts”，只用于离线几何检查，不是毫米、mil或像素。不要把案例中的 `(300,400)` 之类坐标直接写进真实工程；真实页面宽高/引脚端点必须从 [EDA执行](eda-execution.md) → `references/eda-execution.md` (ok)
- L62 [unknown] [py case.json` 看候选。
3. 对候选逐项判断：是真实碰撞/悬空/错网，还是快照不完整造成的误报。
4. 在真实工程中按 [原理图排版与看图验收](schematic-layout.md) → `references/schematic-layout.md` (ok)

### `references/schematic-details.md`

- 标题：原理图细节检查
- 行/字符/字节：61 / 3630 / 8606
- SHA-256：`4c17564e7f4595af25bf73dc3021fd7d6974993ad08b3a0edbf69126a2421c30`

- L3 [unknown] [，不全量询问用户。SC编号用于内部定位。每条是查证问题，具体值以实际器件和工作条件为准；工程核对、实际网络回读、样机测试分别记录。来源定位与经验性质见 [经验库](design-experience.md) → `references/design-experience.md` (ok)
- L3 [unknown] [件和工作条件为准；工程核对、实际网络回读、样机测试分别记录。来源定位与经验性质见 [经验库](design-experience.md)，排版仍执行 [图面验收](schematic-layout.md) → `references/schematic-layout.md` (ok)

### `references/schematic-layout-engine.md`

- 标题：原理图排版引擎：测量 → 模块布局 → 合页 → 写入 → 复核
- 行/字符/字节：362 / 14816 / 24559
- SHA-256：`c8ff4f5bedba3f560988e4741ab86ec8975989144cf1e9cf392b3bf5e6b10fa7`

- L7 [unknown] [高”的图，而是让同一个人能顺着主信号链读完、能定位每个连接、能继续修改。分数、截图和 DRC 都只是其中一项证据。

**执行前强制读取** [图面强制验收](schematic-layout.md#强制验收先规划缺证据不放行) → `references/schematic-layout.md` (ok) #强制验收先规划缺证据不放行 ok
- L64 [unknown] [即停写，不要用 `--resume` 跳过守卫。

## 4. 功能模块计划

模块计划只描述相对关系和画法，不写绝对坐标。示例见
[温度报警模块计划](../assets/layout-modules/temperature-alarm.module-plan.json) → `assets/layout-modules/temperature-alarm.module-plan.json` (ok)

### `references/schematic-layout.md`

- 标题：原理图排版与看图验收
- 行/字符/字节：139 / 8760 / 20689
- SHA-256：`03875d059855789dcbcc9c65deb59830cbb95b6c9aa00c131d247685b81f683c`

- L5 [conditional_read] [设计，也不声称修改了执行器的自动布局算法。

需要程序化重排已有工程（读真实几何、功能分区、区内求解、合页、受保护写入、前后复核）时，先读 [原理图排版引擎](schematic-layout-engine.md) → `references/schematic-layout-engine.md` (ok)
- L18 [unknown] [几何辅助检查：`python scripts/sch_layout_check.py <snapshot.json> --strict`。输入见 [离线工具契约](offline-tools.md) → `references/offline-tools.md` (ok)
- L67 [unknown] [，不能把“同名”当成“已连通”。网络端口用于跨模块/跨页时，方向、名称和域要成对；不要把电源地也塞进每个信号端口。总线、差分和反馈链路的表达边界见 [原理图细节](schematic-details.md) → `references/schematic-details.md` (ok)
- L67 [unknown] [、名称和域要成对；不要把电源地也塞进每个信号端口。总线、差分和反馈链路的表达边界见 [原理图细节](schematic-details.md) 与 [连接表契约](connectivity.md) → `references/connectivity.md` (ok)
- L107 [unknown] [名/页名追踪？
- 新增/改动部分与保留部分衔接是否一致？分区框有没有切线、压标题或漏包内容？

已有实际回读的符号本体与文字边界时，可按 [离线工具契约](offline-tools.md) → `references/offline-tools.md` (ok)
- L111 [unknown] [ectrical_verified/visual_verified` 始终为false，修复后仍要回读网表并实际导图。

官方CLI可用时，按 [EDA执行](eda-execution.md) → `references/eda-execution.md` (ok)
- L132 [external_reference] [或整页图纸复制进Skill；这些观察是本Skill的归纳，不是原作者颁布的强制规范。

- [SparkFun ESP32 Thing Plus：单页原理图](https://cdn.sparkfun.com/assets/6/d/c/6/c/ESP32_Thing_Plus_Schematic.pdf) → `https://cdn.sparkfun.com/assets/6/d/c/6/c/ESP32_Thing_Plus_Schematic.pdf` (external)
- L132 [external_reference] [hematic.pdf)，第1页：供电、USB串口、启动控制等按功能分开；以网名连接远端模块，保留局部支路。适用于学习如何避免把主控连成一团。其[原作者硬件仓库](https://github.com/sparkfun/ESP32_Thing_Plus) → `https://github.com/sparkfun/ESP32_Thing_Plus` (external)
- L133 [external_reference] [b.com/sparkfun/ESP32_Thing_Plus)另有许可，复用硬件须单独遵守。
- [SparkFun Thing Plus ESP32-S3](https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf) → `https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf` (external)
- L134 [external_reference] [与外围分页，保留局部连线和接口网名，说明性文字关联相应模块。可学习分页与注释组织；不要照抄其某一叠层的走线参数。
- [Arduino UNO R3官方原理图](https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf) → `https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf` (external)
- L138 [unknown] [、成品照或“开源”标签认定电路与图面都优秀；无需因追求排版而换掉已经验证的电气方案。

8类典型任务的离线几何基准、预期候选与检查方法见 [原理图排版基准集](schematic-benchmarks.md) → `references/schematic-benchmarks.md` (ok)

### `references/schematic-lessons.md`

- 标题：原理图经验：从注意事项到可执行检查
- 行/字符/字节：66 / 2984 / 7064
- SHA-256：`aaef00255922fe80e8a8994138767ba51b4110b39eae57e87d3e33cc24060e91`

- L3 [unknown] [经验：从注意事项到可执行检查

吸收用户提供的hw-eda-engineer 0.6.0经验库，按本Skill的证据边界改写。已有逐项检查仍以 [原理图细节](schematic-details.md) → `references/schematic-details.md` (ok)
- L7 [unknown] [把决定落到元件值、物理脚、网络、装配选项和PCB约束。模块写入后回读这些对象，交付前再查受影响链路。资料缺失记待确认，不按口诀补值。图面仍执行 [排版与看图验收](schematic-layout.md) → `references/schematic-layout.md` (ok)
- L15 [external_reference] [适配器额定电压

- **条件与原因**：线缆电感、低ESR输入陶瓷电容及突加电源可能形成欠阻尼网络，芯片输入承受的尖峰可能高于源电压；见[ADI AN88](https://www.analog.com/media/en/technical-documentation/application-notes/an88f.pdf) → `https://www.analog.com/media/en/technical-documentation/application-notes/an88f.pdf` (external)
- L23 [unknown] [最坏条件数据；设计分区测流办法，实测包含编程器拔除、外设状态和无线重试。不能因加了“低功耗模式”网名就关闭问题。关联SC09/11/18，工具边界见 [离线工具](offline-tools.md) → `references/offline-tools.md` (ok)
- L43 [background] [逐脚回读、资源表与固件配置对账；需要无线同时采样时查实际型号/SDK的资源共享限制，不把某一ESP32的ADC2行为推广全系列。参考 [G01/G07及原厂入口](design-experience.md) → `references/design-experience.md` (ok)
- L49 [external_reference] [电策略；仅支持固定5V的产品不得假定存在PD升压授权。
- **怎么查**：核对正反插、源端公告与允许负载、VBUS失电/反灌；查 [TI TUSB320LI](https://www.ti.com/product/TUSB320LI) → `https://www.ti.com/product/TUSB320LI` (external)
- L55 [external_reference] [合适的上拉，不强制物理上只留一组。
- **怎么查**：先看实际BOM、原理图和模块内置电阻，再测规定速率/线缆/装配状态。计算方法查 [TI SLVA689](https://www.ti.com/lit/pdf/slva689) → `https://www.ti.com/lit/pdf/slva689` (external)
- L61 [unknown] [：比较修改前后物理脚成员、NC和装配变体，结合实际导图；不自动合并近似网名、不自动给孤脚补NC、不靠网名集合相等证明连接没变。关联SC03/04及 [连接表契约](connectivity.md) → `references/connectivity.md` (ok)
- L65 [unknown] [等证明连接没变。关联SC03/04及 [连接表契约](connectivity.md)。

## 经验如何继续沉淀

来源表及授权写回规则沿用 [经验库](design-experience.md) → `references/design-experience.md` (ok)

### `references/schematic-recipes.md`

- 标题：原理图画法配方：从引脚关系生成局部候选
- 行/字符/字节：67 / 4483 / 8901
- SHA-256：`777b9a4ff36a194dc0a6739f531ba5dfadb4390358cc1a112b11b09a3b9a4975`

- L5 [unknown] [配方保存的是**角色、实际引脚间的相对关系、支路意图与检查方法**，不是某个库符号的一组固定坐标。

配方表：[schematic-recipes.json](../assets/schematic-recipes.json) → `assets/schematic-recipes.json` (ok)
- L5 [unknown] [[schematic-recipes.json](../assets/schematic-recipes.json)；离线实例化器：[sch_recipe.py](../scripts/sch_recipe.py) → `scripts/sch_recipe.py` (ok)
- L8 [unknown] [
2026-10-26 的真实 555 与 AMS1117 工程已用执行器 typed 流程写入/保存重开（见
[schematic-authoring.md](schematic-authoring.md) → `references/schematic-authoring.md` (ok)
- L14 [unknown] [。要升级某个
配方，必须用它生成几何并完成该工程的身份、pin-net、导图、保存重开证据。

## 先做一个模块，再组成页面

1. 从 [排版引擎](schematic-layout-engine.md) → `references/schematic-layout-engine.md` (ok)

### `references/schematic.md`

- 标题：原理图工程习惯
- 行/字符/字节：49 / 2359 / 5356
- SHA-256：`e6fe0b4147868e37efc15fdd153f84b38680090e5f04aa8828fadba1e4ec0337`

- L3 [conditional_read] [# 原理图工程习惯

需要解释常见问题的原因与复验方法时，按需读 [原理图机制卡](schematic-lessons.md) → `references/schematic-lessons.md` (ok)
- L5 [unknown] [因与复验方法时，按需读 [原理图机制卡](schematic-lessons.md)；它展开现有检查，不另立无条件参数。

新建或实质修改时按 [原理图细节](schematic-details.md) → `references/schematic-details.md` (ok)
- L5 [unknown] [d)；它展开现有检查，不另立无条件参数。

新建或实质修改时按 [原理图细节](schematic-details.md) 选取相关对象，再读 [领域易漏项](domain-design-details.md) → `references/domain-design-details.md` (ok)
- L5 [unknown] [ic-details.md) 选取相关对象，再读 [领域易漏项](domain-design-details.md) 的适用小节；来源与持续积累方法见 [经验库](design-experience.md) → `references/design-experience.md` (ok)
- L9 [unknown] [not-direct`，注明范围、理由和复验证据（`sch drc` 与网表逐针核对）；不要画到一半在两种风格间切换。门禁定义、证据角色与豁免规则见 [设计门禁](design-gates.md) → `references/design-gates.md` (ok)
- L9 [unknown] [切换。门禁定义、证据角色与豁免规则见 [设计门禁](design-gates.md)；前台、`--page`、JSON/human 混排等工具限制见 [工具陷阱](tool-gotchas.md) → `references/tool-gotchas.md` (ok)
- L33 [unknown] [置与PCB绑定。针脚/封装/电气差异必须明示，不能只按“同为SOT-23”替换。

## 读图习惯
创建、增加功能块或整理原理图时，执行 [排版与看图验收](schematic-layout.md) → `references/schematic-layout.md` (ok)

### `references/selection/README.md`

- 标题：器件选型与替代资料
- 行/字符/字节：13 / 555 / 913
- SHA-256：`0228f7f685d464a73eecd8a636bf7cc07b68b05dfdfd2ac8ee705b9711d42086`

- L7 [unknown] [`待查`。

| 文档 | 文件 |
|---|---|
| 立创商城核对：检索、字段、留证与下单前对账 | [lcsc-verification.md](lcsc-verification.md) → `references/selection/lcsc-verification.md` (ok)
- L8 [unknown] [ication.md](lcsc-verification.md) |
| 模组、收发器、连接器与传感器选型 | [modules-connectors.md](modules-connectors.md) → `references/selection/modules-connectors.md` (ok)
- L9 [unknown] [es-connectors.md](modules-connectors.md) |
| 无源器件选型：电阻、电容、电感与保护件 | [passives.md](passives.md) → `references/selection/passives.md` (ok)
- L10 [unknown] [ssives.md](passives.md) |
| 电源与信号链 IC 选型：稳压器、充电器、驱动器、运放、ADC 与基准 | [power-ics.md](power-ics.md) → `references/selection/power-ics.md` (ok)
- L11 [unknown] [md) |
| 替代分类：1 直接替换、2 改 RC/配置/固件、3 改原理图/封装/PCB、4 资料不足 | [replacement-classes.md](replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L12 [unknown] [acement-classes.md) |
| 半导体分立器件选型：二极管、TVS、MOSFET、BJT 与 LED | [semiconductors.md](semiconductors.md) → `references/selection/semiconductors.md` (ok)

### `references/selection/lcsc-verification.md`

- 标题：立创商城核对：检索、字段、留证与下单前对账
- 行/字符/字节：373 / 14954 / 28598
- SHA-256：`4cd795e21c4826b2fad103c2cb2496cdf156666b71b1ecf304c7126af4024b12`

- L117 [unknown] [重查。
- 证据文件保存原始页面/导出/截图；不要只留结论。
- 商城字段与 SMT 字段分行记录，不能合并成“有货/可贴”。
- 替代等级按 [替代分类](replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L141 [unknown] [BOM；把红字/黄字行直接确认。

## 7. 三条制造路线：选哪条、要什么文件

路线按“用户想收到什么”选，不按单价选。完整细节见 [制造与交付路线](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L281 [unknown] [ | 先贴再说，事后补 |
| 多装/错料 | 隔离、标识、查批次 | 返修/换料/报废；评估已焊板 | 把错料板混入良品 |
| 替代 | 按 [替代分类](replacement-classes.md) → `references/selection/replacement-classes.md` (ok)

### `references/selection/modules-connectors.md`

- 标题：模组、收发器、连接器与传感器选型
- 行/字符/字节：294 / 13337 / 24372
- SHA-256：`4df78a16726caba07c20cbcecf3a16068e60c0c65ec2fd19f51751c95221f663`

- L199 [unknown] [0 而不核对新旧与供货 |

筛选顺序：**类别 → 形态/封装 → 关键电气/机械 → 温度/认证 → 装配方式 → 供货**。完整核验见 [立创商城核对](lcsc-verification.md) → `references/selection/lcsc-verification.md` (ok)
- L212 [unknown] [| 双绞屏蔽 |
| 传感器 | 1 路 4–20 mA 或 0–3.3 V（待定） | 接口待定 |
| 输出 | 1 路 24 V 电磁阀（见 [半导体](semiconductors.md) → `references/selection/semiconductors.md` (ok)
- L213 [unknown] [V 电磁阀（见 [半导体](semiconductors.md) §8） | 0.5 A |
| 电源 | 24 V→5 V→3.3 V | 见 [电源 IC](power-ics.md) → `references/selection/power-ics.md` (ok)
- L272 [unknown] [能推广 |
|---|---|---|---|
| MCU-S01 | `VCAP` 是内部稳压输出、BOOT 锁存、SWJ 内部上下拉（经 [MCU-01](../design-cards/mcu/m01-bare-mcu.md) → `references/design-cards/mcu/m01-bare-mcu.md` (ok)

### `references/selection/passives.md`

- 标题：无源器件选型：电阻、电容、电感与保护件
- 行/字符/字节：304 / 14419 / 26267
- SHA-256：`dd45ace01030d2e6479c1aed9d99a77a7fc2c26053b13f05cda49eb562bddbaf`

- L5 [unknown] [ `E2` 为主：方法来自来源笔记记录的章节，器件实例数值只属于该型号。`E1` 仅限 2026-10-20 本轮实际访问的立创商城页面（结果见 [立创商城核对](lcsc-verification.md) → `references/selection/lcsc-verification.md` (ok)
- L203 [unknown] [压降 |
| 晶振 | 负载电容 `CL`、ESR、驱动电平、温度频差 | 用固定 18 pF 通吃 | 按 MCU/晶振手册算 `CL`，见 [MCU-05](../design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L206 [unknown] [elvin 布局；按温漂算误差（ANA-S11） |
| 保险丝 | 动作类别、70% 安全系数、温度降额、`I²t` | 只比额定电流 | 见 [电源 IC](power-ics.md) → `references/selection/power-ics.md` (ok)
- L207 [unknown] [) 的保护段；`I²t` 只用于浪涌（PWR-S13） |
| 压敏/放电管 | 工作电压、钳位/残压、能量、老化 | 与 TVS 混用判据 | 见 [半导体](semiconductors.md) → `references/selection/semiconductors.md` (ok)
- L211 [unknown] [ 立创商城检索：无源件的关键词顺序

检索的目标不是“搜到相似名字”，而是**用参数把候选缩到可核对的一小撮**。完整核验流程、字段与留证见 [立创商城核对](lcsc-verification.md) → `references/selection/lcsc-verification.md` (ok)
- L226 [unknown] [/电流 → 供货字段**。把价格/库存放在最后，因为前面的条件不满足时，价格没有比较意义。

## 7. 替代与装配边界

- 替代分级只用 [替代分类](replacement-classes.md) → `references/selection/replacement-classes.md` (ok)
- L230 [unknown] [805；0402 可手焊但需要镊子/放大镜；0201 与细间距不建议手焊。SMT 经济型最小封装 0402、标准型 01005（MFG-S01），见 [制造路线](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L253 [unknown] [与布局面积。
4. 缓冲运放选择：若信号带宽 10 kHz、增益 1，按 GBW ≥5× 原则至少 50 kHz；实际按建立/容性负载选，见 [运放与 ADC](power-ics.md) → `references/selection/power-ics.md` (ok)

### `references/selection/power-ics.md`

- 标题：电源与信号链 IC 选型：稳压器、充电器、驱动器、运放、ADC 与基准
- 行/字符/字节：355 / 17017 / 28891
- SHA-256：`574030535f76308a63d7142cb4b6e1eb917a349c07fb2bee2af7af9af811a4e8`

- L57 [unknown] [用 max `IQ` 算续航 |
| 输出电容 | 落在手册稳定窗口（有效容量） | 电容耐压 | 标称 22 µF ≠ 有效 22 µF | 见 [无源器件](passives.md) → `references/selection/passives.md` (ok)
- L225 [unknown] [=20×C_SH`；`R_source≤τ/C_EXT`；`f_U≥4f_Z` | 只看输入阻抗 | 10 kΩ 分压直接接 SAR 会建立失败（见 [无源器件](passives.md) → `references/selection/passives.md` (ok)
- L270 [unknown] [典型精度当保证 |

筛选顺序：**功能/拓扑 → 输入输出范围 → 限流/频率/精度 → 封装/热 → 温度等级 → 供货**。核验流程见 [立创商城核对](lcsc-verification.md) → `references/selection/lcsc-verification.md` (ok)

### `references/selection/replacement-classes.md`

- 标题：替代分类：1 直接替换、2 改 RC/配置/固件、3 改原理图/封装/PCB、4 资料不足
- 行/字符/字节：229 / 9274 / 18723
- SHA-256：`27ae7f2dc574d2007c80a19619bdda862b6f791266dbf043df595d3ec9030b9f`

- L114 [unknown] [PCB、结构 | 耐压/隔离 |

**3 类的硬规则：**

- 任一 PCB 改动 → 重新导出 Gerber/钻孔/BOM/CPL，按 [制造路线](../manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)

### `references/selection/semiconductors.md`

- 标题：半导体分立器件选型：二极管、TVS、MOSFET、BJT 与 LED
- 行/字符/字节：252 / 11804 / 21727
- SHA-256：`06940e880c0dd04d00580919335d7e157312b4d9aa4c15fa5d3e4f84057ea8ac`

- L150 [example] [对 `Vf` 分档敏感 | 多颗并联需均流或独立电阻 |

电阻限流的实算（5 V ±5%、`Vf` 1.8–2.2 V、180 Ω ±5%）见 [无源器件](passives.md) → `references/selection/passives.md` (ok)
- L176 [unknown] [ `0805 LED 红色 20mA` | 颜色/`Vf` bin、亮度、视角、封装 | 不同 bin 混用导致亮度差 |

完整核验流程见 [立创商城核对](lcsc-verification.md) → `references/selection/lcsc-verification.md` (ok)
- L251 [unknown] [交期/生命周期/SMT 可贴均 `待查`。
- **未覆盖**：SiC/GaN 器件、雪崩额定/EAS、TVS 阵列的通道间耦合、继电器触点灭弧（见 [驱动卡](../design-cards/drive/d03-relay.md) → `references/design-cards/drive/d03-relay.md` (ok)

### `references/simulation-measurement.md`

- 标题：仿真与测量方法：电源、模拟、数字与 RF
- 行/字符/字节：726 / 43330 / 77923
- SHA-256：`2928c8feea7467507ed161253353d83ca0fa034679d9780aecb0539c27af207c`

- L9 [unknown] [没有样机、没有实测波形。** 本文中的“预期范围”是设计预算或来源条件，不是测量结果。
>
> **可执行脚本：** [`rc_settle_sim.py`](../scripts/rc_settle_sim.py) → `scripts/rc_settle_sim.py` (ok)
- L9 [unknown] [tle_sim.py`](../scripts/rc_settle_sim.py)（自研二阶 RC 数值模型，不是 SPICE）；[`calculate.py`](../scripts/calculate.py) → `scripts/calculate.py` (ok)
- L9 [unknown] [ck`、`ldo`、`i2c`、`current_sense` 模式。SPICE 计划文件 [`assets/simulation/rc_sample.cir`](../assets/simulation/rc_sample.cir) → `assets/simulation/rc_sample.cir` (ok)
- L224 [unknown] [d_verified:false`。

### 4.4 SPICE 计划文件状态

[`assets/simulation/rc_sample.cir`](../assets/simulation/rc_sample.cir) → `assets/simulation/rc_sample.cir` (ok)
- L441 [unknown] [
仿真和测量不是制造之后的独立环节：测试点、装配变体、DNP、钢网、坐标和固件配置都会改变“能不能测/测到的是不是这个变体”。完整路线细节见 [制造与交付路线](manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)
- L551 [unknown] [先做连接表和通断测试 |
| 整机测试 | 用户/Agent/第三方 | 测试计划、样本、判据、记录 | 工厂 AOI/电测不等于整机功能 | 按 [功能验收](product-acceptance.md) → `references/product-acceptance.md` (ok)
- L725 [unknown] [in-pad/额定/温度/时序/固件重新核对，不能凭“同封装/有库存”放行。
- **需要其他文档补：** 电源/热计算见 [power-thermal.md](calculations/power-thermal.md) → `references/calculations/power-thermal.md` (ok)
- L725 [unknown] [算见 [power-thermal.md](calculations/power-thermal.md)，ADC/运放/基准计算见 [analog-adc.md](calculations/analog-adc.md) → `references/calculations/analog-adc.md` (ok)
- L725 [unknown] [ermal.md)，ADC/运放/基准计算见 [analog-adc.md](calculations/analog-adc.md)；设计方法见 [PWR-02](design-cards/power/p02-buck.md) → `references/design-cards/power/p02-buck.md` (ok)
- L725 [unknown] [lculations/analog-adc.md)；设计方法见 [PWR-02](design-cards/power/p02-buck.md)、[ANA-04](design-cards/analog/a04-adc-driver.md) → `references/design-cards/analog/a04-adc-driver.md` (ok)
- L725 [unknown] [cards/power/p02-buck.md)、[ANA-04](design-cards/analog/a04-adc-driver.md)、[MCU-05](design-cards/mcu/m05-crystal.md) → `references/design-cards/mcu/m05-crystal.md` (ok)
- L725 [unknown] [cards/analog/a04-adc-driver.md)、[MCU-05](design-cards/mcu/m05-crystal.md)、[IF-01](design-cards/interfaces/i01-i2c.md) → `references/design-cards/interfaces/i01-i2c.md` (ok)
- L725 [unknown] [ign-cards/mcu/m05-crystal.md)、[IF-01](design-cards/interfaces/i01-i2c.md)、[RF-02](design-cards/wireless/w02-antenna.md) → `references/design-cards/wireless/w02-antenna.md` (ok)
- L725 [unknown] [md)、[RF-02](design-cards/wireless/w02-antenna.md)；制造对账见 [manufacturing-routes.md](manufacturing-routes.md) → `references/manufacturing-routes.md` (ok)

### `references/source-register.md`

- 标题：原始来源登记与查阅范围
- 行/字符/字节：346 / 111919 / 164939
- SHA-256：`818bf0598772c3e1dac17986dd7e153559c118251a75307c58c042588dfb2458`

- L121 [unknown] [wireless | 10 |

## 2026-10-22 工程深潜新增来源（D-S）

本组来源的完整查阅范围、页码和“不能推广”见 [工程深潜来源](engineering-deepdives/sources.md) → `references/engineering-deepdives/sources.md` (ok)

### `references/sources.md`

- 标题：官方来源导航
- 行/字符/字节：63 / 3674 / 6764
- SHA-256：`b078dbe9a87b7019b13e699d35a61e324057c317b1c98b137801a7cb3550480f`

- L3 [unknown] [# 官方来源导航

开源硬件图纸、作者修订与专项原厂/制造资料的实际查阅范围、经验归属和未读取项见 [工程经验库](design-experience.md) → `references/design-experience.md` (ok)
- L56 [example] [接受任意程序或完整产品验证。

## 本轮扩充来源（2026-10-20）

新增设计卡、范例、故障、选型和制造内容引用的资料统一登记在 [原始来源登记](source-register.md) → `references/source-register.md` (ok)
- L62 [unknown] [时供货。

## 嘉立创PCB与SMT生产规则（核对日期：2026-10-20）

已读范围、条件数值、冲突及当前未覆盖项集中维护于 [PCB规则来源表](jlc-pcb-rules.md) → `references/jlc-pcb-rules.md` (ok)
- L62 [unknown] [日期：2026-10-20）

已读范围、条件数值、冲突及当前未覆盖项集中维护于 [PCB规则来源表](jlc-pcb-rules.md) 与 [SMT规则](jlc-smt-rules.md) → `references/jlc-smt-rules.md` (ok)
- L62 [unknown] [未覆盖项集中维护于 [PCB规则来源表](jlc-pcb-rules.md) 与 [SMT规则](jlc-smt-rules.md)，执行顺序见 [生产规则接入](jlc-production.md) → `references/jlc-production.md` (ok)
- L62 [external_reference] [es.md) 与 [SMT规则](jlc-smt-rules.md)，执行顺序见 [生产规则接入](jlc-production.md)。主要入口为 [工艺总表](https://www.jlc.com/portal/vtechnology.html) → `https://www.jlc.com/portal/vtechnology.html` (external)
- L62 [external_reference] [duction.md)。主要入口为 [工艺总表](https://www.jlc.com/portal/vtechnology.html) 和 [SMT规范目录](https://www.jlc.com/portal/q7i64042.html) → `https://www.jlc.com/portal/q7i64042.html` (external)

### `references/starter-patterns.md`

- 标题：起步方案：可查证的骨架，不是可直接生产的模板
- 行/字符/字节：25 / 1373 / 3431
- SHA-256：`a3745c8497aa41c8c99083566016dab87f4ed1cea29d2574110a1cabc46b305d`

- L12 [unknown] [SB小键盘/控制器 | 数据接口/供电→USB能力与匹配固件→按键/编码器 | 裸芯片还是模组、时钟/存储、矩阵鬼键（无二极管矩阵三键同按会出幽灵键，见 [L6](common-hardware/l-hmi.md#l6-机械按键) → `references/common-hardware/l-hmi.md` (ok) #l6-机械按键 ok
- L24 [unknown] [明；改动后按项目关联记录复验。上面任一例子都不授予实际下单、烧录、账户或硬件访问能力，沿用用户授权和当前执行通道。

需要更完整的项目包时见 [完整项目样本](projects/README.md) → `references/projects/README.md` (ok)

### `references/task-scenarios.md`

- 标题：任务场景与反例验收
- 行/字符/字节：57 / 7605 / 15485
- SHA-256：`bbdce2ae87fce879a9a5843d8668c5ef26fdbe0ee96ca6b05bb47b5d15c3bc78`

### `references/thermal/cases.md`

- 标题：算例、反例与判定
- 行/字符/字节：399 / 12976 / 20719
- SHA-256：`866b804c87655cd6bc7efd1357be0f202e1a4034898553257757b767221fab96`

### `references/thermal/sources.md`

- 标题：来源与核对记录
- 行/字符/字节：520 / 28082 / 46669
- SHA-256：`a94488bc235e2568f5645003919fc0f00178573f38d6431d05eb272636889c22`

### `references/thermal/topic.md`

- 标题：板级热设计：从功耗到结温、PCB 散热路径与验证
- 行/字符/字节：590 / 26291 / 54175
- SHA-256：`a31cb763ef4629ea2c498a3cee9441072c02b89bb3c38a7666015529318d4b90`

- L7 [unknown] [态结温 → PCB 与外壳路径 → 测量验证**。每一节都说明适用条件、为什么、怎么做、怎么判定和例外。
>
> 证据标记：`[S01]` 等指向 [热来源](sources.md) → `references/thermal/sources.md` (ok)
- L9 [unknown] [推导”的公式是本专题的一阶模型；标“假设”的数值不是器件保证值。没有实际做过的 EDA、仿真或测量，在本专题及交付记录中保持未验证。

![板级热路径与指标](figures/thermal-path.svg) → `references/thermal/figures/thermal-path.svg` (ok)
- L460 [unknown] [

> 本节是“用热电偶测量温度”的实验方法，不是热电偶前端电路设计。补偿导线/连接器必须与热电偶同合金，冷端补偿、断线检测、µV 级前端见 [常用硬件 A4](../common-hardware/a-environment.md) → `references/common-hardware/a-environment.md` (ok)
- L487 [unknown] [附近、板面、外壳/环境；有邻热源时测其影响。
- 重复：至少一个最坏工况单元；有条件时测多个样本/批次。
- JEDEC 标准的正文本轮未取得（见 [热来源](sources.md) → `references/thermal/sources.md` (ok)
- L569 [unknown] [偶线径未记录 → 测量结果只能当参考。
- 器件批次/装配变体/外壳差异未覆盖 → 不能宣称全批次通过。

## 11. 工具与算例

- [热计算器](../../scripts/thermal_calc.py) → `scripts/thermal_calc.py` (ok)
- L571 [unknown] [头；所有结果带 `assumptions`，不访问 EDA/网络。
- `cases.md`：C01–C11，包含算例、反例、测量反例和判定。
- [热来源](sources.md) → `references/thermal/sources.md` (ok)

### `references/tool-gotchas.md`

- 标题：EDA 工具动作陷阱
- 行/字符/字节：335 / 27350 / 46649
- SHA-256：`a9517b80420f442e63bbcb9e1dd42860fae943b8220a7bca0bfbe62357797b22`

- L3 [unknown] [只因前台/活动页状态不同就失败。这里只写“现象、原因、正确动作、证据/边界与本案例”；工程方法、能力矩阵和保存/重开流程仍看 [eda-execution.md](eda-execution.md) → `references/eda-execution.md` (ok)
- L3 [unknown] [和保存/重开流程仍看 [eda-execution.md](eda-execution.md)，门禁定义、证据角色与豁免规则看 [design-gates.md](design-gates.md) → `references/design-gates.md` (ok)
- L3 [unknown] [豁免规则看 [design-gates.md](design-gates.md)，2 层/4 层与电源地取舍看 [pcb-routing-strategy.md](pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L5 [example] [ `pcb-drc.json` 位于其 `round7/baseline/` 子目录。技能内回归案例是 [cases/temp-alarm-2026-10-24](../cases/temp-alarm-2026-10-24/README.md) → `cases/temp-alarm-2026-10-24/README.md` (ok)
- L40 [unknown] [ 分层判：DRC 看 fatal/error=0；`sch check --json` 的电气类必须 0，风格/结构类修复或按 [design-gates.md](design-gates.md) → `references/design-gates.md` (ok)
- L112 [unknown] [而非完成，落图后逐项看 DRC 与 GND 项，必要时撤销这些 track 后重布。2 层/4 层的完整取舍见 [pcb-routing-strategy.md](pcb-routing-strategy.md) → `references/pcb-routing-strategy.md` (ok)
- L322 [required_read] [不支持项。能力矩阵、工程可写探针、先读后写的对账、`apply`/verify/reopen、保存与重开、会话来源控制，仍按 [eda-execution.md](eda-execution.md) → `references/eda-execution.md` (ok)
- L324 [unknown] [open、保存与重开、会话来源控制，仍按 [eda-execution.md](eda-execution.md) 执行。

工程习惯分别看 [pcb.md](pcb.md) → `references/pcb.md` (ok)
- L324 [unknown] [-execution.md](eda-execution.md) 执行。

工程习惯分别看 [pcb.md](pcb.md) 与 [schematic.md](schematic.md) → `references/schematic.md` (ok)
- L324 [unknown] [cb.md](pcb.md) 与 [schematic.md](schematic.md)；用户可见的定位与下一步表达看 [troubleshooting.md](troubleshooting.md) → `references/troubleshooting.md` (ok)
- L324 [unknown] [；用户可见的定位与下一步表达看 [troubleshooting.md](troubleshooting.md)；证据分层与最小记录看 [evidence.md](evidence.md) → `references/evidence.md` (ok)

### `references/troubleshooting.md`

- 标题：Agent先定位，再给用户一个具体下一步
- 行/字符/字节：41 / 1833 / 4421
- SHA-256：`fb9cf987dbf4080e55c5632226b6ccd8916bb303b51d59deed725a4f606a548f`

### `references/workflow.md`

- 标题：从工程任务到图纸
- 行/字符/字节：51 / 1986 / 5240
- SHA-256：`184dd2773ca82908dcc37f9ad89e66d49d1006dad2d7e31bfda8d26ae94140ac`

