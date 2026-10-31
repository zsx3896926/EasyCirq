# 可追溯台账：温度报警器（2026-10-31）

> 指标 7 要求「"我要什么" → "能打样" 全链路可追溯 100%」。
> 这份台账逐条列出：**结论 → 用什么命令得出 → 证据留在哪**。
> 复现方式：按顺序执行命令即可（工程 `KPI-S5-Verify`，页 `P2`）。

## 0. 一句话需求

| 结论 | 命令 | 证据 |
|---|---|---|
| 能做，约 ¥8–15，3–5 天 | 人工估算（含库内器件价格） | `docs/temp-alarm-proposal.md` |
| 三个必须先问的问题 | — | 同上 |

## 1. 选型（器件确实存在）

| 结论 | 命令 | 证据 |
|---|---|---|
| 10K 热敏电阻存在 | `easycirq lib search NTC 10K` | C9900004021 |
| LM393 存在 | `easycirq lib search LM393` | C504553 |
| 贴片蜂鸣器存在 | `easycirq lib search --query '5025贴片蜂鸣器'` | C9900027059 |
| 100nF 0603 存在 | `easycirq lib search 100nF 0603` | C9900013340 |

## 2. 画原理图（15 次写入）

| 结论 | 命令 | 证据 |
|---|---|---|
| 新页创建 | `sch page-new --schematic 2be28e1c36e37dfe` | pageUuid `9d9dd9e46f53880e` |
| 7 个器件落位 | `sch place` ×7 | 每个 `ok: true` |
| 15 条连接 | `sch connect --pin ... --kind ... --net ...` ×15 | 全部 `ok: true`；`sch connectivity` 的 `connections` 16 条（含合并） |
| 未用引脚标不接 | `call schematic.pin.set_no_connect` | U1:5/6/7、BZ1:3 |
| 建板不需令牌 | — | 每次 `sch place` 都 `ok`，无 `GATE_*` |

## 3. 原理图检查（两轮 PASS）

| 结论 | 命令 | 证据 |
|---|---|---|
| 快照齐备 | `sch connectivity` / `sch list --include-bbox --include-pins` / `sch sheet-geometry --json` | `%TEMP%\alarm-snap5\*.json` |
| ERC | `sch drc --json` | `drc.json` |
| BOM | `bom export --type csv` | `bom.tsv` |
| 回读一致 | `doc reload` 前后各读一次 | `connectivity-before/reopen.json` 一致 |
| 引脚计划 | `pin_plan_check.py .easycirq/pinplan-alarm.json` | `status: passed`，`pin_mux_conflicts: 0` |
| **门禁第 1 轮** | `sch_offline_pipeline.py --project-uuid ...` | `PASS (apply_allowed=False)` |
| **门禁第 2 轮** | 同上 | `PASS (apply_allowed=True)` → 签发令牌 |
| **卡片** | `easycirq card --kpi-report ...` | `✅ 可以打样`，必查 11/11 |

## 4. PCB（0 违规）

| 结论 | 命令 | 证据 |
|---|---|---|
| 网表同步 | `pcb import-changes` | 9 器件（含 LED 页 2 个） |
| 布局 | `pcb auto-place` | `ok` |
| 板框 | `pcb outline-fit --margin 60` | 877×869 mil |
| 布线 | `pcb autoroute` | `success=true, 5/5 nets, 15139ms` |
| **DRC** | `pcb drc --json` | `passed: true, total: 0` |
| 权威重读 | `pcb save` → `doc reload` → 再 DRC | 仍 `total: 0` |

## 5. 制造文件

| 结论 | 命令 | 证据 |
|---|---|---|
| 令牌有效 | 管线两轮 | `apply_allowed: true` |
| Gerber 导出 | `call pcb.manufacture.gerber` | `ok: true`，11 层 |
| 层清单含钻孔 | 解压 zip | `Drill_PTH_Through.DRL` |

## 6. 交付包

| 结论 | 命令 | 证据 |
|---|---|---|
| 原理图可读 | `sch export-image --format svg` | 92,410 字节，81 text，NTC/LM393/BZ1 |
| 整板卡片 | `card --kpi-report ... --pcb-drc reports/pcb-drc.json` | `✅ 可以下单（原理图与 PCB 都通过）` |
| 客户部分零术语 | 扫描 11 个禁用词 | 附录之前 0 命中 |

## 清晰的 NOT RUN

| 项目 | 为什么没做 |
|---|---|
| **实物打样** | 需要下单与收货，非 AI 可完成 |
| **打样后验收**（焊接/上电/功能） | 没有实物，`acceptance` 从未收到真实数据 |
| **第二台机器安装** | 只有隔离目录安装验证，没有另一台机器 |
| **原理图视觉效果** | 本机无确定性 SVG→PNG 工具链，"看起来对不对"未验证 |

## 这一路的工具缺陷（都由这块板暴露并修掉）

| 缺陷 | 影响 | 修复版本 |
|---|---|---|
| 建板写入被门禁死锁 | 无法从零画板 | 1.3.0 分阶段门禁 |
| 管线不传 `--sheet-geometry` | 新页布局失败 | 1.3.0 |
| 纯标签页面无导线报错 | 连线度量中断 | 1.3.0 |
| `sch list` 缺 bbox | 器件全被丢弃 | 1.3.0（文档） |
| `anchor: null` 崩溃 | 布局检查中断 | 1.3.0 |
| 快照缺 `--include-pins` | NC 全被判悬空 | 1.3.1（文档） |
| `pin_plan_check` 强求 MCU 字段 | 模拟器件无法通过 | 1.3.2 |
| `pin_plan_check` 缺 `verdict`/`metrics` | KPI 恒判 unknown | 1.3.2 |
| `card` 不读 PCB | 原理图结论冒充整板 | 1.3.2 |

## 一句话

从「一句话」到「可下单的 Gerber」，**每一步都有命令与输出可查**；
**没做的那三件事（下单、实测、第二台机器）明确标着 NOT RUN**。

## 复现验证（本轮实做）

按上面的命令，用**全新的快照目录**把整条链路重跑了一遍，与首次结果逐项对比：

| 项 | 首次 | 复现 |
|---|---|---|
| verdict | PASS | PASS |
| KPI 项数 | 15 | 15 |
| 逐项 status / value | — | **无差异** |
| apply_allowed | true | true |
| 卡片 | ✅ 可以下单 | ✅ 可以下单 |

```
verdict PASS / PASS
kpi count 15 15
differences none
apply_allowed True / True
```

**这就是"可复现"的实物证据**：不是"我跑通过"，而是"换一个快照目录按同样命令
再跑，15 项指标连数值都不变"。

（注：复现用的是同一台机器、同一个 EDA 工程。跨机器复现未做——见 NOT RUN。）
