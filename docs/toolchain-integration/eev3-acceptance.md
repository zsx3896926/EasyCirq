# eev3 最终验收证据（DRC + BOM）

> 工程：`zhigou-dual-button-led-eev3-20261028`（uuid `b45c9648853446a08f2bf374fa85ee0d`）
> 基线：从 `zhigou-board.epro2` 重导（原工程与 eev2 副本已损坏，不再使用）
> 采集时间：2026-10-28 13:12（只读收集，未修改工程）

## 1. PCB DRC

- 命令：`zhigou pcb drc`（`pcb.drc.check`）
- 结果：**passed = true，0 violations**（原始回执 `evidence/eev3/pcb-drc.json`）
- 前提：全部 47 条旧走线删除后由官方路由器 `pcb.route.auto` 全板重布，`pcb.pour.rebuild` 重建两层 GND 铺铜，
  `pcb save → doc reload` 后读取。

## 2. BOM（可下单）

来源 `evidence/eev3/BOM-v3.csv`（`bom export --type csv --enrich=false`）：

| 位号 | C 号 | 型号 | 厂家 | 封装 |
|---|---|---|---|---|
| C1 | C125205 | CT41G-0603-2X1-50V-0.1uF-K(N) | TORCH(火炬) | C0603 |
| D1,D2 | C51933311 | GL0805YG01 | Guiguang light(桂光光电) | LED0805-RD |
| F1 | C845159 | S1206-SD-1.5A | SART(萨特) | F1206 |
| J1 | C124375 | B-2100S02P-A110 | Ckmtw(灿科盟) | HDR-TH_2P-P2.54-V-M-1 |
| R1,R2 | C112291 | RC0402FR-07220RL | YAGEO(国巨) | R0402 |
| SW1,SW2 | C49296724 | TS-1101-C-R | XKB Connection(中国星坤) | SW-SMD_L6.0-W3.6-LS8.0 |

## 3. 视觉证据

- PCB 顶面图：`evidence/eev3/pcb-top.png`（快照时间 2026-10-28 13:12）
- 原理图：`evidence/eev3/schematic.png`（2026-10-28 13:11 导出）

## 4. 能作为投产基线吗？

**结论：可以作为"工程/PCB 候选基线"，但不能直接作为"投产基线"。**

已具备：
- PCB 原生 DRC 0 违规；
- 6 行 BOM 全部有可订货 C 号/型号/厂家（库存已核）；
- J1 已按确认方案换为 TH 封装，网络与封装一致。

还缺（投产前必须补）：
1. **制造文件**：eec3 工程尚未导出 Gerber/钻孔/CPL（工具侧已有 `pcb.manufacture.*` 能力，
   可只读导出、不改工程）；
2. **DFM/工艺复核**：layout-lint、DFM 规则、板厂工艺档案核对；
3. **人工走线复核**：全板重布由官方路由器生成，电气正确，但需人工确认走线走向/电源路径/丝印观感；
4. **实物验证**：打样后的上电、通断、限流、边界测试（V2–V11，全部 NOT RUN）。

一句话：**"电气/工程上可以当基线，投产还差制造文件 + DFM + 人工复核 + 实物验证"。**
