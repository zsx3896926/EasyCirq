# Round 8 证据索引（dual-scope-instrument-01 隔离副本）

日期：2026-10-26。本目录是 `docs/round8-report.md` 的原始证据副本；项目工作目录为
`C:\Users\jlc\work\dual-scope-20261026`，Skill 工作树为 `C:\Users\jlc\work\hds-round8`。
PR：https://github.com/zsx3896926/hardware-design-skill/pull/17

## 环境与身份

- EasyEDA Pro 4.1.78；easyeda-agent CLI/daemon 1.14.0；connector 1.14.0。
- 原工程：`dual-scope-instrument-01`，UUID `47e3126a4f3d4abd9da89d64fdfca63b`。
  本轮只做只读导出，未修改。
- 隔离副本：`dual-scope-r8-isolated`，UUID `ac26e6ad34d24573ab2d82d383b96643`；
  窗口 `6c8f658f-91b8-4e7d-a58c-137fdc280182`。
- 只读基线导出：`dual-scope-r8-base.epro2`，SHA-256
  `ed6c64c5b102de9b6927de25d24769f88e3f0ef65541386fda3cca49e5a0b110`。

## 文件与证据类型

| 文件 | 内容 | 证据类型 |
|---|---|---|
| `design-inventory-baseline.json` | 设计源 337 件 vs 隔离副本 21 页回读 | 真实 EDA 回读 + 离线比较 |
| `channel-map-input.json` | 设计源 P1↔P3 通道映射 | 离线（设计源） |
| `channel-map-level.json` | 设计源 P2↔P4 通道映射 | 离线（设计源） |
| `channel-map-eda-P1-P3.json` | EDA 回读 P1↔P3 通道映射 | 真实 EDA 回读 + 离线比较 |
| `library-precheck.json` | 337 件器件身份/LCSC/封装预检 | 离线（设计源） |
| `cache-demo.txt` | 版本化缓存 hit / 版本失配 miss / 失效 / not_found | 离线工具演示 |
| `audit-cost-20261026.json` | 上一轮双通道会话的审计成本基线 | 真实 EDA 审计日志 |
| `read-batch-probe.out.txt` | 单进程 5 步只读 playbook 输出 | 真实 EDA 只读 |
| `P1-frames.json` | P1 三功能框的显式几何与单行标题 | 真实 EDA 写入输入 |
| `before-P1.png` | P1 修正/排版前官方导图 | 真实 EDA 导出 |
| `after-P1-v3.png` | P1 修正/分区/说明/图签后官方导图 | 真实 EDA 导出 |
| `pcb-ch1-seed-crop.png` | PCB 板框内 CH1 16 件布局种子 | 离线辅助渲染（`pcb dump` + `pcb layout render`，非官方画布截图） |
| `ch1-pcb-placements.jsonl` | 16 件 `pcb modify` 检查点（id/目标/ok/耗时） | 真实 EDA 写入 |
| `architecture-verification-raw.txt` | 独立复核的 4 条结论原文（第 5 组高风险项待补） | 只读审查（原厂资料+设计源） |

## 关键数字

### 页面盘点

- 设计源 337 件；隔离副本回读 213 件；缺 126、多 2（P1 的 K2，已在副本修正）。
- P11–P16、P21 空白；P6 16/17、P10 24/28、P17 1 缺 1 多。
- P7/P8/P9 件数齐但分别 23/8/30 floating。
- “complete”只表示位号集合一致，不表示连线完成。

### P1/P3 拓扑修正

- P1 删除 K2（5 个已连接 pin + 2 旗）；K3:2 `CH1_ATT_OUT→CH1_10X_TAP`；
  网 `CH1_ATT_OUT`/`RELAY2` 消失；其余 50 pin 零变化。
- P3 K203:2 `CH2_ATT_OUT→CH2_10X_TAP`；其余 50 pin 零变化。
- EDA P1↔P3 映射：16 件、51 pin、0 缺失/0 多余/0 网名不一致。

### P1 可读性

- 三区：输入与保护（36,477.5–276.5,813）、耦合与量程
  （288.5,253.5–684.5,806）、高压缓冲（695.5,378.5–1103.5,791）。
- 3 个框 + 3 条用途说明；重开后 6 文本、3 框 unchanged。
- `sch check`：0 floating；分区/图签缺失清零；剩余 1 marker-overlap
  （3.5×2.5 raw）、1 位号擦边（0.5 raw）、3 条 peripheral-not-direct 警告。
- save→reload→回读：16 件、51 pin，相对修正前 0 差异。

### PCB

- `pcb import-changes`：`imported:true / partial:false / verified:true /
  componentsAfter:212`（等于已放置页器件数）。
- 板框：6299×4331 mil（160×110 mm），R118，4 个 native arc，locked；保存重开保持。
- CH1 16 件移入板内，保存重开 16/16 仍在板内。
- 未做：全板布局、布线、铺铜、DRC、Gerber/CPL。

### 批量读微基准

| 方式 | 墙钟 | 审计条数 | 上下文探测 | components.list |
|---|---:|---:|---:|---:|
| 单进程 playbook 5 步 | 5.75 s | 12 | 4 | 7 |
| 5 个独立进程 | 8.12 s | 30 | 15 | 15 |

限制：只读、同页、5 次、连接器健康；写路径未做对照。

### 架构独立复核（5/5）

| ID | 结论 | 要点 |
|---|---|---|
| PWR-01 | CONFIRMED | LM2663 用 +24V 产生 -24V，超 5.5V 上限；-24V 轨不可用 |
| DRV-01 | CONFIRMED | AD8138 无外部 RF/RG，差分增益无定义 |
| FPGA-POWER-01 | 新发现（原 claim 修正） | 64/67/78 接 1.8V 低于 2.375V；pin12 PSRAM 接 3.3V 高于 1.89V；两轨接反 |
| ADC-01 | REFUTED | S1=+3V3、S2=GND，AD9288 为 Normal Operation，不是 standby |

高风险组（逐项；组级 verdict=REFUTED，因为 H5 不成立且部分表述需修正）：

| ID | 结论 | 要点 |
|---|---|---|
| H1 3.3V buck | CONFIRMED | 3.095V < INT035TFT VDDIO 最小 3.135V；容差低端约 3.02V |
| H2 VOCM | CONFIRMED | AD8138 VOCM 0.9V < 1.0V 最小；ADC CM 0.99V 仍低 10mV |
| H3 抗混叠 | CONFIRMED | 实际 3L+3C；首个 -3dB≈8.9MHz，25MHz 相对 -21.5dB；15MHz/-44dB 不成立 |
| H4 端接 | CONFIRMED | 51/(44+51)=53.7%，计 ADC 10k 为 53.6%；量程表未乘 0.536 |
| H5 PSRAM 时钟 | REFUTED | 100MHz 是 memory clock、用户 50MHz，未越 166MHz；400MB/s 为峰值，持续余量乐观 |

原始复核原文见 `architecture-verification-raw.txt` 与 `verify-HIGH-GROUP.json`。

## 复现命令（摘要）

```bash
python design-hardware/scripts/channel_map_check.py \
  --reference page-P1.json --instance page-P3.json --mapping ch1_to_ch2.json

python design-hardware/scripts/design_inventory.py \
  --design design.json --eda P1=page-P1.json ... --check P1=check-P1.json ...

python design-hardware/scripts/library_precheck.py \
  --design design.json --devices devices.json

python design-hardware/scripts/eda_cache.py put/get/invalidate ...
```

真实 EDA 复现：先 `easyeda health`/`doc ready`，在隔离副本上 `doc open <pcb-uuid>`
后 `pcb import-changes`，再 `pcb outline-round`，最后 `save → doc reload → 回读`。
不要在原工程上重放这些写入；原工程由其它会话使用。
