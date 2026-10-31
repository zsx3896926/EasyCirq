# 从零建板实验（2026-10-31，1.3.0）

> 目标：验证「AI 能不能独立画一块板」。在临时工程 `KPI_S5_Verify` 里搭一个
> 最小电路：`VCC → R11 → LED(D1) → GND`。

## 做成的部分

| 步骤 | 命令 | 结果 |
|---|---|---|
| 放 LED | `sch place --lib ... --uuid <0805-LED>` | `ok: true`，D1 |
| 放限流电阻 | `sch place ...` | `ok: true`，R11 |
| 接电源 | `sch connect --pin R11:1 --kind power --net VCC` | `ok: true` |
| 电阻→LED | `sch connect --pin R11:2 --kind net_label --net NLED` | `ok: true` |
| LED 阳极 | `sch connect --pin D1:1 --kind net_label --net NLED` | `ok: true` |
| LED 阴极→地 | `sch connect --pin D1:2 --kind gnd --net GND` | `ok: true` |
| 保存 | `sch save` | `ok: true` |

连接结果（`sch connectivity` 的 connections）：

```
D1.1  ↔ R11.2  → net NLED
D1.2  ↔ R1.1, R3.1 → net GND
R11.1 → net VCC
```

**最小电路在电气上成立了**。而且这一步不需要任何门禁令牌（建板动作已放行）。

## 卡住的部分

跑离线管线时：

```
offline pipeline: BLOCKED — layout_from_easycirq failed rc=2:
{"status": "invalid_input", "error": "sheet bbox or sheet-geometry bbox required for page bounds"}
```

原因：管线的 `layout_from_easycirq` 需要 `geometry_data['sheet']['bbox']`，格式是
`{"minX","minY","maxX","maxY"}` 的 JSON；而 `sch sheet-geometry` 命令只打印**文本**：

```
sheet-geometry: template "a-series-landscape", bbox [0.00,0.00 → 1170.00,825.00]
  titleBlock (visible, source=known-template-ratio): bbox [468.00,0.00 → 1170.00,198.00]
```

我按两种猜测的 JSON 结构手工补了 `sheet.json`，管线仍然报同一个错——说明
**管线传给适配器的参数名或内容并不是我猜的那样**，需要读管线的调用处才能确定。

## 这是真实的客户断点

客户（或 agent）从零画完板之后，想跑离线检查，会在这里停住：

1. `sch sheet-geometry` 的输出**不能直接喂给管线**
2. 管线报的错是 `layout_from_easycirq failed`，属于内部实现名，不是客户能行动的话
3. 我试了两次 JSON 形状都没成功，说明文档里也没有这个对接格式

## 待修

| 问题 | 建议 |
|---|---|
| `sch sheet-geometry` 只有文本输出 | 加 `--json`，输出 `{sheet:{bbox:{minX..}}, titleBlock:{bbox:{...}}}` |
| 管线对 sheet 的要求没写进文档 | 在 `schematic-offline-first.md` 的快照清单里写清格式 |
| 管线的错误信息暴露内部实现名 | 改成「这页缺图纸边界，先用 sch sheet-geometry --json 生成 sheet.json」 |

## 结论

**建板这一段通了**（放置 + 连线 + 保存，全部门禁放行）。
**检查这一段断了**（缺 sheet 边界的对接格式）。
所以「AI 独立完成一块板」目前走不到「拿到卡片」那一步。
