# 会话交接（截至 2026-11-01，第 155 轮）

> 目的：这个会话跨了上百轮，上下文随时可能被压缩。这一页是**给下一个接手的人（或压缩后的自己）**看的：
> 现在到哪了、哪些已验证、哪些还是空白、下一步做什么。

## 一句话现状

**一块"测温度、超温就响"的板，从一句话做到了可下单的 12 层 Gerber，全程有证据；
但它没打样，所以"会不会响"仍然未知。**

## 已验证（附证据位置）

| 结论 | 怎么验的 | 证据 |
|---|---|---|
| 从零建板 → 卡片 | 报警器 9 器件 / 15 连接全 ok | `docs/traceability-alarm.md` |
| 离线门禁 17 项 | 两轮 PASS 才签发写入许可 | `reports/alarm-r132/` |
| PCB 走通 | autoroute 7/7、DRC 0 | 同上 + `reports/pcb-drc-r132.json` |
| Gerber | 12 层含两套钻孔 | `deliverables/alarm/board-gerber.zip` |
| 客户零术语 | 六文件静态扫描 | `tests/test_customer_language.py` |
| 四向一致性 | 仓库 ↔ 包 ↔ 副本 | `tools/check_release_consistency.py` |
| 可复现 | 同机重跑 17 项数值一致 | `docs/traceability-alarm.md` |
| 能力边界 | MCU 引脚实测九字段 | `easycirq/references/scope-limits.md` |
| 全量回归 | 4820 passed / 16 Go 包 | 最近一次 commit |

## 五个真实缺陷（都是这块板暴露的）

| # | 缺陷 | 怎么发现的 | 现在的防线 |
|---|---|---|---|
| 1 | 建板写入门禁死锁 | 从零画板卡住 | 分阶段门禁（1.3.0） |
| 2 | 电源网名 `VCC` 被静默改写成 `GND` | 人工读网络表 | 连接守则 + KPI 16 |
| 3 | 蜂鸣器开集输出驱动方向错 | 人工读电路 | （无自动检查，见下方空白） |
| 4 | 图改了 PCB 没同步无检查 | 人工比对 | KPI 17 |
| 5 | 我移器件把引脚与导线撕开 | DRC warn 增加 | 顺序：断开→移动→连接 |

## 明确的空白（不要以为已覆盖）

| 空白 | 为什么还在 |
|---|---|
| **电路功能是否正确** | 17 项全是结构/连接/供电/一致性；没有任何一项验证电气行为 |
| **实物是否可用** | 没打样 |
| **跨机器复现** | 只有同机 + 隔离目录 |
| `VCC` 映射的根因 | connector 是打包的 `.eext`，无可读源码 |
| 原理图 6 项 warn | 5 个网络标签在框外 + 1 个孤立网名；排版问题，不阻断 |

## 下一步（按优先级）

1. **打样**：`deliverables/alarm/board-gerber.zip` 下单（约 ¥8–15/板，¥50–80/5 片）。
2. 板回来后按 `deliverables/alarm/electrical-checklist.md` 测六个值，特别注意
   **`NTC_MID` 必须随温度下降**（接反时它上升，只测"响不响"发现不了）。
3. 填 `acceptance.example.json` 的格式，跑 `easycirq acceptance`。
4. 有条件时做跨机器复现（第二台机器装 bundle）。

## 关键文件在哪

| 要找什么 | 位置 |
|---|---|
| 客户交付包（9 文件） | `deliverables/alarm/` |
| 报警器的完整经过 | `docs/alarm-functional-defect.md` |
| 逐条命令的可追溯台账 | `docs/traceability-alarm.md` |
| 能做什么/不能做什么 | `easycirq/references/scope-limits.md` |
| 发版检查单 | `docs/release-checklist.md` |
| 已知 flaky 测试 | `docs/known-failures.md` |

## 环境快照

```
easycirq 1.3.30      daemon 端口 23111     connector 已连接（EasyEDA Pro 4.1.78）
KPI 定义 17 项（metrics/schematic-kpi.v1.json，版本 1.2.0）
测试：4820 passed / 5 skipped；go test 16 包 ok
临时工程：KPI-S5-Verify（含报警器 P2 页 + PCB1）
```
