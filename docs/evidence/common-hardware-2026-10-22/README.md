# 常用硬件能力扩展：证据索引（2026-10-22）

## 基线

- 仓库：`zsx3896926/hardware-design-skill`
- 分支：`feat/common-hardware-coverage`
- 基线：`origin/main` = `0fe5cf8`（2026-10-22 14:19 +0800）
- 本轮未合并、未打标签、未发布。

## 盘点

- [缺口分析](../../common-hardware-gap-analysis.md)：13 组 102 个主题，`adequate` 15、`partial` 60、`missing` 27；动作 `new` 43、`supplement` 46、`reuse` 13。
- [13 份分组审计](audit/)：每组列出现有文件/行号、已覆盖、缺口、候选型号、旧内容问题。
- 审计同时列出 78 条旧内容问题（C01–C78），其中数值/逻辑错误 30 条、边界/外推 17 条、悬空/错向引用 25 条、索引/计数 6 条。

## 本轮新增

- `design-hardware/references/common-hardware/`：13 个组文件 + README + 12 个组合应用。
- `tests/test_common_hardware.py`：13 组/102 主题/12 应用/12 个三级标题/来源登记/无 C 号占位的结构契约。
- `design-hardware/references/source-register.md`：`CHW-S001`–`CHW-S235` 段，登记实际查阅范围、支持内容与不能推广。
- 旧内容修正：ANA-10 RTD 灵敏度、ANA-07 误差表、ANA-01 阶跃、ANA-09 候选理由、IF-07/IF-08 24 V 端接功率、DRV-01/02/03 释放时间 RL 解、PWR-14 漏电、PWR-01 VDO/TJ、USB-C 0.9 A、RS-485 U.L.、MCU-07 STDC14 等；完整清单见本轮交付报告与各组 `## 需要同步修正`。

## 真实 EDA

[S1-NTC-ALARM](eda/README.md)：

- 嘉立创EDA专业版 `4.1.78.34f5b8d9`，半离线；真实工程副本。
- 12 个真实库器件、13 个电源/地标记、9 个网络端口、5 条命名导线（编辑器合并后）。
- Protel 网表逐脚核对：`3V3`、`GND`、`NTC_NODE`、`TH_NODE`、`OUT1`、`GATE`、`BUZ_D` 全部符合计划。
- `save:true`；关闭重开 `match`；DRC 2 条 `ONENETNAME` 警告、0 error。
- 未做：ERC 全项、PCB、制造、样机、固件、热/EMC/安规。

## 验证状态

| 项 | 状态 | 证据 |
|---|---|---|
| 基线回归（改动前） | 148 tests OK | 本轮开工记录 |
| 新结构契约 | 已通过 13 组/102 主题 + 12 应用 | 全量 `260 tests OK`（含 `CommonHardwareGroups`、`CommonHardwareApplications`、链接检查） |
| 来源登记 | 已通过 200 条 | `source-register.md` + `test_no_unregistered_source_ids` |
| C 号/库存纪律 | 已通过 | `test_no_obvious_fabricated_c_numbers` |
| 独立资料审校 | NOT RUN | 本轮未单独派审校员逐条复核；已做作者核对 + 集成人抽查 |
| 盲测路由 | DONE（6/6） | [blind/eval.md](blind/eval.md)：B1–B6 路线均正确；B2/B6 各一处分支/默认值问题已修；原始回答见 [blind/](blind/) |

盲测暴露并已修的 routing 缺口：

- 11/12 应用在盲测时尚未生成 → 现已生成，全量测试通过。
- “ESP32 + 2.4 寸 TFT + 蜂鸣器”没有直达行 → README 增加行，03 应用增加变体说明（≥1 A Buck、不能用 200 mA LDO）。
- 05 电子秤行写成 `E1/E7` 必读 → 改为 `D1 + ANA-09 + I1 + L3 + F2/G1`，E1/E7 标为可选。
- 08 RS-485 行把隔离/非隔离混在一行 → 拆成“无 4–20 mA（默认隔离）”和“带 4–20 mA（加 D7/E5）”两行。
- A2 未写 DS18B20 ±0.5 °C 仅 −10…85 °C → 已在正文和选型表补上。
| 真实 EDA | DONE（连接级） | [eda/](eda/) |
| PCB/制造/样机 | NOT RUN | — |
| 全在线 GUI | NOT RUN | CLI 会话恒半离线；需用户 GUI 会话复验 |

## 未完成与边界

- 未做 PCB、Gerber/BOM/坐标、DFM、打样/SMT、样机、固件、热/EMC/安规。
- 未取得部分标准的正文（IEC 60751/60584、EN 50291、UL 2034、IEC 62368-1 等）；相关处只写“需取得并核对”，不声称认证。
- 实时库存/价格/C 号/SMT 可贴状态未核对；组文件只给检索字段与核对流程。
- 半离线 EDA 结论不能写成全在线验收。

## 文件

| 路径 | 内容 |
|---|---|
| [audit/](audit/) | 13 份分组审计 |
| [eda/](eda/) | S1-NTC-ALARM 原理图、网表、DRC、重开比对、计划 |
| `design-hardware/references/common-hardware/` | 13 组 + README + 12 应用 |
| `docs/common-hardware-gap-analysis.md` | 缺口分析与内容架构 |
| `tests/test_common_hardware.py` | 结构契约 |
