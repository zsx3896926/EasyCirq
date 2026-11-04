# 温度报警器：从方案到图纸的执行清单

> 配套 `temp-alarm-proposal.md`（开工确认）。这份是**第二幕（设计）**的可执行步骤，
> 每一步都给出命令与验收判据。器件已确认真实存在于库中。

## 已核实的器件（`easycirq lib search`，2026-10-31）

| 用途 | 器件 | LCSC | 库 uuid | 器件 uuid |
|---|---|---|---|---|
| 感温 | `NTC/10K` | C9900004021 | 0819f05c4eef4c71ace90d822a990e87 | 1fb69ec7d4584c77814edf6734580bcf |
| 比较器 | `LM393` | C504553 | 0819f05c4eef4c71ace90d822a990e87 | f6c052f627d24462af0cabf98d8547bd |
| 蜂鸣器（贴片） | `5025贴片蜂鸣器` | C9900027059 | 待查 | 待查 |
| 电阻/电容 | 库内通用件 | — | — | — |

蜂鸣器与无源件的 uuid 在动手前用 `easycirq lib search --query <C号> --exact` 取。

## 电路（方案 A：纯模拟，最少器件）

```
        +5V
         │
        [R1 10K]        ← 上臂
         │
         ├──── NTC ──── GND      ← 分压中点 = 温度电压
         │
     LM393 IN-  （阈值侧）
        [R2/R3 分压]  ← 设定 60°C 对应电压
     LM393 IN+
        │
     OUT ──► [R4 1K] ──► 蜂鸣器 ──► GND
```

阈值电压按 NTC 在 60°C 的阻值算，用两个电阻分压设定；`R4` 限流保护输出。

## 执行步骤

### 1. 新建页面（不破坏已有的 LED 板）

```bash
easycirq --project 'KPI-S5-Verify' sch page-new --schematic <schematic-uuid>
```

`schematic-uuid` 从 `easycirq board list --project <P>` 里取（`Board1` 的 schematic 字段）。

### 2. 放置器件

```bash
easycirq --project 'KPI-S5-Verify' --doc <new-page-uuid> sch place \
  --lib 0819f05c4eef4c71ace90d822a990e87 --uuid <器件uuid> \
  --x <x> --y <y> --designator <R1/R2/R3/R4/NTC1/U1/BZ1>
```

建板动作**不需要令牌**（分阶段门禁）。

### 3. 连接（全部用网络标签，不手画导线）

```bash
easycirq ... sch connect --pin U1:1 --kind net_label --net NTC_MID
easycirq ... sch connect --pin NTC1:1 --kind net_label --net NTC_MID
easycirq ... sch connect --pin R1:2 --kind power --net VCC
easycirq ... sch connect --pin BZ1:1 --kind net_label --net ALARM
easycirq ... sch connect --pin R4:2 --kind net_label --net ALARM
```

每接一个引脚都看 `ok: true`；同名网络即电气相连。

### 4. 保存并快照

```bash
easycirq ... sch save
easycirq --project 'KPI-S5-Verify' sch connectivity --page <page> | jq '.result' > $S/connectivity.json
easycirq --project 'KPI-S5-Verify' sch list --page <page> --include-bbox | jq '.result' > $S/list.json
easycirq --project 'KPI-S5-Verify' sch sheet-geometry --json | jq '.result' > $S/sheet.json
easycirq --project 'KPI-S5-Verify' sch drc --json | jq '.result' > $S/drc.json
easycirq --project 'KPI-S5-Verify' bom export --type csv   # 产物复制为 $S/bom.tsv
```

`--include-bbox` **不能省**（否则布局适配器丢弃所有器件）。

### 5. 跑门禁

```bash
python easycirq/scripts/sch_offline_pipeline.py \
  --snapshot-dir $S --project 'KPI-S5-Verify' \
  --project-uuid <uuid> --page <页名> --out-dir reports/temp-alarm
```

**必须传 `--project-uuid`**，否则令牌只绑名字，名字一有差异就 `GATE_PROJECT_MISMATCH`。

### 6. 看卡片

```bash
easycirq card --kpi-report reports/temp-alarm/kpi-report.json
```

## 验收判据

| 步骤 | 通过条件 |
|---|---|
| 放置 | 每个器件 `ok: true` 且 `sch list` 能看到 designator |
| 连接 | `sch connectivity` 的 connections 里每个引脚都有 netId |
| 快照 | 三个文件都在，且 `list.json` 的器件都带 bbox |
| 门禁 | 第 1 轮 `PASS (apply_allowed=False)`，第 2 轮 `True` |
| 卡片 | `✅ 可以打样`，或「不能」但只差缺证据 |

## 已知风险

| 风险 | 现象 | 应对 |
|---|---|---|
| NTC 在 60°C 的阻值需实算 | 阈值电压定错 → 报警点偏移 | 先算再画，别拍脑袋 |
| 蜂鸣器驱动电流 | LM393 输出 <20mA，直接驱动可能不够 | 加三极管或选低电流件 |
| 页面多了布局冲突 | 新页与 LED 板共用图纸尺寸 | 新页独立布局即可 |
| 临时工程被清 | 现有 LED 板与 Gerber 证据丢失 | 新建页面，不要 `sch clear` |

## 为什么这份清单比"直接开画"更重要

从零画 LED 板那一轮，我踩了六个坑（门禁死锁、缺 sheet、缺 bbox、anchor null、
无导线、工程名不一致），每个坑都让管线停在半路。这份清单把这些坑的解法写进
步骤里——**照着做就不会重踩**。
