# 从历史工程里长出规则（harvest）

> `easycirq enterprise harvest --drc <报告或目录> [--dump dump.json] [--out cand.json]`
>
> 聚合一堆历史 DRC 报告，回答三个问题：哪几类问题反复出现、**哪一类能变成可执行规则**、
> 能变的那些产出**候选**。候选不是规则——必须人审。

---

## 一、它解决的问题

竞品的切入口是「把你的历史工程给我，我训出你的模型」。
我们过去的切入口是「你把规范写清楚」。

**但多数企业的历史工程比成文规范多得多。**

harvest 把这条软肋变成资产：**从你已经有的 DRC 报告里，长出可以执行的东西。**

---

## 二、必须先知道的一条事实

**DRC 的两类违规都不直接对应现有谓词。** 现有 4 个谓词全是网表级：

```
footprint_forbidden  part_forbidden  net_name_required  net_name_forbidden
```

| DRC rule | 实际含义 | 能不能变规则 |
|---|---|---|
| `Connection Error` | `(+3V3): U1_4 is disconnected from other objects of the same network` —— **开路/未布通** | **不能**。这是「这块板没做完」，不是设计规范。写成规则会拦住所有未完成的板，等于没有规则 |
| `Clearance Error` | `(+3V3): e949 to (GND): e87 distance is 0mil, should be >= 6mil` —— **几何间距** | **不能直接**。没有几何谓词；要变规则得先有「按网络对限距」这类新谓词，且需要几何数据 |

**所以真正能变成规则的只有一条间接路径**：

> 某个**器件**在违规里反复出现 ⇒ 说明它的节距/焊盘尺寸与规则不兼容
> ⇒ 提一个 `part_forbidden` 候选（「禁用这个型号」）。

这条路径**必须有 `--dump`** 才能补上型号（`device` 字段）。没有 dump 就只报位号、不出候选。

---

## 三、输出长什么样

```
一、按违规类型      每类多少次、涉及哪些网络与位号、样例报文、
                    以及「为什么不能直接变规则」
二、位号总榜        每个位号出现多少次、占已归属违规的百分比、型号
三、候选            够阈值且补得上型号的，产出 review-ledger 形状的候选
四、没被提为候选的   逐条给原因（低于阈值 / 够阈值但缺型号）
```

阈值默认 **≥50 次且 ≥10%**（`--min-hits` / `--min-share` 可调）。
**低于阈值不是"不重要"，是"证据不足以提候选"——所以逐条写明。**

---

## 四、候选为什么必须人审

候选里**故意不写 `disposition`**：

```
$ easycirq enterprise harvest ... --out cand.json
$ easycirq enterprise promote --ledger cand.json
没有写入：
  ! entries[0]: disposition 必须是 rule 或 knowledge（实际 None）。
    **必须显式选边**——工具不替你判断，因为判错两边都致命
```

**判错两边都致命**：
- 判成规则 → 会拿"历史上常见"去拦正常的板，误报把检查关掉
- 判成知识 → 永远拦不住东西

所以每条候选都带 `needs_human`，列出人必须回答的问题：
这算不算公司规范？禁用这个型号还是改它的封装？`verified_on` 打算在哪块板上验？

---

## 五、CLI 噪声：为什么能容忍、又为什么要报出来

EasyEDA 的 DRC 导出是 **CLI 输出**，不是纯 JSON：

```
⚠ staleRisk: PCB was mutated by pcb.line.create since the last reload —
  pcb.drc.check (and DRC) may read stale engine state

{"passed": false, "total": 294, "violations": [...]}

pcb drc: native verdict failed; inspect the returned violations
```

- 开头的警告行被**收集并打印**——`staleRisk` 尤其重要：**它意味着这份 DRC 可能读的是旧数据**
- 尾部日志被容忍，不当错误
- 用严格 `json.loads` 会把这类文件整个丢掉。实测 25 份里有 **10 份**带尾部内容，
  严格解析会漏掉 **1,598 条违规（3,500 → 1,902）**

给目录时只认真正含 DRC 字段（`passed`/`counts`/`total`/`violations`）的文件。
**干净的 DRC 报告是 `violations: []`，不是"非 DRC"**——判定不能只看有没有违规。

---

## 六、实测（RetroCam-02，25 份报告）

```
违规总数 3500，分成 16 类；带位号 2730 条（78%）
```

位号总榜：

| 位号 | 次数 | 占比 | 型号 |
|---|---|---|---|
| **U5** | 554 | 20.3% | ESP32-S3-WROOM-1 |
| **J3** | 514 | 18.8% | FPC0.52H-WS-24P |
| U1 | 269 | 9.9% | TPS63020DSJT |
| J5 | 178 | 6.5% | TF-01A |
| J4 | 163 | 6.0% | **（dump 里没有 device，不出候选）** |

产出 2 条候选：`HARVEST-U5`、`HARVEST-J3`。

**这两个位号与几何分析的结论独立吻合**：那套分析算出的等长下界 53–67 mil，
根因正是 J3（19.7 mil 节距）与 U5（50 mil 焊盘）。
**两条互不相干的路径指向同一对器件**，这比任何一条单独的证据都硬。

---

## 七、它明确不做

- **不做 ML、不做训练**。这是聚类与提取，不是预测。
- **不从 PDF/图片 OCR**。只吃结构化 DRC。
- **不自动采纳**。工具只产出候选。
- **不替你判断"这算不算规范"**。那是人的事。
