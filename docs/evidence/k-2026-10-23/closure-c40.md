# K-1 / C40 关闭记录：ESP32-S3 “35+j0” S11 目标的定义

> **任务：** K-1（知识库审校旧账 C40）。
> **仓库：** `C:/Users/jlc/work/hds-round5`（git worktree），分支 `feat/round5-release-acceptance`，基线 HEAD `a8ef214`。执行日期 2026-10-23。
> **范围：** 只处理 C40；不改代码、不做 EDA、不下单、不写凭据、不 commit/push。工作区中其他并行 agent 的改动不属于本记录。
> **最终状态：** **CLOSED（DONE）**——原厂页面已实际取得，`35+j0` 是芯片共轭**阻抗点**（Smith 圆图，单位 Ω），不是 S11 的 dB 门限；C40 中“疑似应为 S11 ≤ −35 dB”的推断被否定。5 个知识文件（修改前 16 行）+ 1 个来源登记文件的相关表述已统一；相关测试通过。

---

## 1. 历史问题（C40 原始记录）

来源：`docs/common-hardware-gap-analysis.md:497`（§15.2 过时结论/单型号外推/边界收窄）：

> | C40 | `W02`/`D4`/`simulation-measurement` | “35+j0”S11 目标重复传播，来源笔记定义不完整，疑似应为 S11≤−35 dB | 回读 Espressif RF Tuning 原页；未确认前统一写“按模组/芯片要求” | M |

同一文件的临时同步口径（`docs/common-hardware-gap-analysis.md:414`）：

> `35+j0` 全部改为“按模组/芯片要求，疑似 S11≤−35 dB，待回读原页”

审计来源：`docs/evidence/common-hardware-2026-10-22/audit/m-wireless-time.md:71` 与 `:446`（M 组审计，审计对象 `C:\Users\jlc\work\hardware-design-skill`，HEAD `0fe5cf8`，2026-10-22）。审计原话（`:446`）：

> `w02-antenna.md:90` 已注明来源笔记对“35+j0”的单位/定义记录不完整；`d4-wireless-integration.md:470`、`simulation-measurement.md:80,294,359,668` 仍把它当 ESP32-S3 的 S11 目标。疑似应为“S11 ≤ −35 dB”，必须回读 Espressif RF Tuning 原页后统一；在未确认前，所有文档都应写成“按模组/芯片要求，不能用 35+j0 当门限”。

**问题本质：** 原记录把“35+j0”当成一个来路不明的 S11 数值门限，并猜测应改成“S11 ≤ −35 dB”。这两步都需要用原页核实。

---

## 2. 当前文件 / 位置（修改前核对）

修改前在 `design-hardware/references/` 下实际 `grep -rn "35+j0"`，共有 **16 行、5 个知识文件**命中（`source-register.md` 的补登见 §4）：

| 文件 | 修改前行号 | 修改前表述（摘要） | 是否仍有问题 |
|---|---|---|---|
| `design-cards/wireless/w02-antenna.md` | 90 | “调谐目标写作 S11 约‘35+j0’、S21 低于 −35 dB…”；只加“来源定义不完整，使用前回读” | **是**：未给出定义，仍把 35+j0 放在“S11 约…”的写法里 |
| 同上 | 183 | 通过标准：“S11 满足芯片要求（不能直接用本卡记录的‘35+j0’）” | **是**：只回避，没有正确判据 |
| 同上 | 190 | 来源表：“‘35+j0’定义需回读原页” | **是**：待查状态 |
| `engineering-deepdives/topics/d4-wireless-integration.md` | 470 | “ESP32-S3 参考给 `35+j0` 目标，但来源笔记对其定义记录不完整，使用前回读原页” | **是**：仍称其为“目标”，未定义 |
| `simulation-measurement.md` | 80、131、294、359、668、701、718 | 在仿真/预期范围/测点/计划/来源/缺口表中重复“ESP32-S3 给 `35+j0` 目标” | **是**：7 处均未定义，部分只加“不能通用” |
| `failures/f18-antenna-enclosure.md` | 47 | “Espressif 参考调谐目标为 S11 约 `35+j0`、S21 低于 −35 dB…” | **是**：把阻抗点写成“S11 约…” |
| 同上 | 57 | 根因证据：“调谐目标与匹配范围是参考起点” | 部分：未提 35+j0，但未定义正确判据 |
| `common-hardware/m-wireless-time.md` | 351 | “VNA 测 S11（按天线厂要求，不写‘35+j0’）” | 部分：回避写法；未解释 |
| 同上 | 1010–1013 | “需要同步修正”第 2 条：“疑似应为 S11 ≤ −35 dB…本组 M1/M3/M5 已按此口径写” | **是（最严重）**：把错误推断写成建议口径 |

**核对结论：问题仍存在。** 其中 `w02`、`d4`、`simulation-measurement` 只是加了“待回读/不能直接用”的限定，没有解决定义；`m-wireless-time.md` 的“需要同步修正”甚至把“S11 ≤ −35 dB”写成了建议改法。仅靠限定词不能关闭 C40。

---

## 3. 依据：Espressif 原页实际复核（2026-10-23）

### 3.1 访问记录

| 项 | 内容 |
|---|---|
| URL | https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html |
| 页面标题 | `Schematic Checklist - ESP32-S3 - — ESP Hardware Design Guidelines latest documentation` |
| 页面版本标识 | 页面为 “latest documentation”，页脚 `© Copyright 2023 - 2026, Espressif Systems (Shanghai) Co., Ltd`；**未显示独立修订号或发布日期** |
| 访问日期 | 2026-10-23（本地时间约 08:46；UTC 2026-10-23T00:53:19Z 复核哈希） |
| 实际读取章节 | `RF` → `RF Circuit`、`RF Tuning`（整页 HTML 另存于本机临时目录，未入库） |
| 本地快照 | 78,910 bytes，SHA-256 `42d32ee82c4ab44249c155962bbc13cf952258dbea566f5fee755fb8529589d2`（仅用于说明本次读取的是同一份页面，不作为长期证据文件） |

### 3.2 原文（逐字）

`RF Tuning` 节：

> “In the matching circuit, define the port near the chip as Port 1 and the port near the antenna as Port 2. S11 describes the ratio of the signal power reflected back from Port 1 to the input signal power, the transmission performance is best if the matching impedance is conjugate to the chip impedance. S21 is used to describe the transmission loss of signal from Port 1 to Port 2. **If S11 is close to the chip conjugate point 35+j0 and S21 is less than -35 dB at 4.8 GHz and 7.2 GHz, the matching circuit can satisfy transmission requirements.**”

同页 `RF Circuit` 节（用于确认 −35 dB 的性质）：

> “For the chip matching circuit, it must be placed close to the chip. A CLC structure is preferred. The CLC structure is mainly used to adjust the impedance point and suppress harmonics.”

同页 `RF Tuning` 的参考值表（旁证，不是 C40 的核心）：

> C11 `1.2 ~ 1.8 pF`；L2 `2.0 ~ 3.0 nH`；C12 `1.8 ~ 1.2 pF`；并注明 “Please use 0201 packages for RF matching components…”。

### 3.3 正确解释

| 项 | 结论 | 依据 |
|---|---|---|
| `35+j0` 是什么 | **芯片共轭阻抗点**，Smith 圆图上的复数阻抗点；按 RF/S 参数惯例单位为 Ω。原页该句未显式写出 “Ω”，但上下文明确在讲 “matching impedance is conjugate to the chip impedance”，且 Port 1/Port 2、VNA 测 S11/S21 均为阻抗/S 参数语境 | RF Tuning 原文；RF Circuit “adjust the impedance point” |
| 它是不是 S11 的 dB 门限 | **不是。** 原页说的是 “S11 is close to the chip conjugate point 35+j0”，即 S11 轨迹/输入阻抗点接近 35+j0 Ω；不是 “S11 ≤ 35 dB” 或 “S11 ≤ −35 dB” | RF Tuning 原文 |
| `−35 dB` 属于谁 | **S21**，在 **4.8 GHz 与 7.2 GHz** 的传输损耗要求；结合 RF Circuit “suppress harmonics”，这是 2.4 GHz 频段 2 次/3 次谐波抑制，不是 S11 门限 | RF Tuning + RF Circuit 原文 |
| C40 的“疑似 S11 ≤ −35 dB” | **不成立。** 它把 S21 的谐波指标误当成了 S11 指标 | 同上 |
| 适用范围 | 仅 ESP32-S3 参考条件；页面明确 “The RF matching parameters vary with the board, so the ones used in Espressif modules could not be applied directly.” 其他芯片/模组必须按各自原厂要求 | RF Tuning 原文 |

### 3.4 复算（本记录的推导，不是原页数值）

把阻抗点换算成 50 Ω 测试系统的反射系数，仅用于交叉核对：

```text
Γ = (Z_L − Z_0) / (Z_L + Z_0) = (35 − 50) / (35 + 50) = −15/85 = −0.17647
|Γ| = 0.17647
S11(dB) = 20·log10(0.17647) = −15.07 dB
VSWR = (1 + |Γ|) / (1 − |Γ|) = 1.17647 / 0.82353 = 1.4286
```

即：在 50 Ω 归一化下，`35+j0 Ω` 这个点对应 **S11 ≈ −15.1 dB、VSWR ≈ 1.43**。这是“同一个阻抗点的另一种表示”，**不是**原页给出的验收门限，也不能反过来要求“S11 越小越好”。

反证“S11 ≤ −35 dB”为什么错：

```text
若 |Γ| ≤ 10^(−35/20) = 0.01778
则 50 Ω 系统的输入阻抗约在 48.3 … 51.8 Ω（实部）
而 35+j0 Ω 的共轭匹配点对应 |Γ| = 0.176（−15.1 dB）
```

把门限收紧到 −35 dB，实际是把阻抗拉回 50 Ω 附近，**偏离**芯片要求的 35 Ω 共轭点。因此不能把 C40 的猜测当作修正。

### 3.5 未能确证/待查项（如实标注）

- 原页是 “latest documentation”，**没有修订号/发布日期**；若 Espressif 后续改页，需重新核对。本记录只对 2026-10-23 的页面快照负责。
- 本次只核对了 **ESP32-S3** 的 Schematic Checklist；ESP32-C3/C6/S31 或其他模组的共轭点/门限未逐页核对，知识库中不得把 35+j0 外推到它们。
- 没有做任何 VNA/S11/S21 实测；本记录是文档定义核对，不是硬件验收。
- “35+j0 的单位为 Ω”是按 Smith 圆图/S 参数惯例与上下文解释；原页该句没有印出 “Ω” 字样（已在 3.3 标注）。

---

## 4. 修改内容（逐文件）

修改原则：保留 35+j0，但把它写成“芯片共轭阻抗点（Ω）”；把 −35 dB 明确归到 S21；把“疑似 S11 ≤ −35 dB”明确否定；保留“其他模组按各自原厂要求”的边界。

| 文件 | 修改后位置 | 修改内容 |
|---|---|---|
| `design-hardware/references/design-cards/wireless/w02-antenna.md` | 90 | 改为“调谐目标不是 S11 的 dB 门限，而是芯片共轭点 35+j0（Ω）……Port 1 输入阻抗应接近 35+j0 Ω；S21 在 4.8/7.2 GHz 低于 −35 dB 为 2/3 次谐波抑制”，并加入 `Γ=(35−50)/(35+50)=−0.176`、S11 幅值≈0.176（−15.1 dB）、`VSWR≈1.43` 的换算说明 |
| 同上 | 183 | 通过标准改为“S11 接近芯片共轭点 35+j0（Ω），Port 1 输入阻抗约 35 Ω”，明确“不能写成 S11 ≤ −35 dB” |
| 同上 | 190 | 来源表补“RF Tuning 节 2026-10-23 复核”，不能推广列改为“35+j0 是芯片共轭阻抗点（Ω），−35 dB 属 S21 谐波抑制” |
| `engineering-deepdives/topics/d4-wireless-integration.md` | 470 | S11 测量行改为“接近芯片共轭点 35+j0（Ω），Port 1 输入阻抗≈35 Ω；S11≈−15.1 dB、VSWR≈1.43 仅换算；−35 dB 是 S21 谐波抑制”，并注明 2026-10-23 复核 |
| 同上 | 624 | §7.4 原厂证据补“调谐目标是芯片共轭点 35+j0 Ω，不是 S11 的 dB 门限” |
| 同上 | 690 | 来源表补复核日期与 35+j0 定义/边界 |
| `simulation-measurement.md` | 80、131、294、359、670、703、720 | 7 处统一改为“芯片共轭点 35+j0（Ω）/Port 1 输入阻抗≈35 Ω；−35 dB 属 S21 谐波抑制”；S11 行不再写成“给 35+j0 目标” |
| 同上 | 366 | 在 §6.4 RF 表后新增一段“ESP32-S3 的 35+j0 怎么读”，引用原页英文原文并给出换算/反证 |
| `failures/f18-antenna-enclosure.md` | 47 | 改为“参考调谐目标不是 S11 的 dB 值，而是芯片侧共轭阻抗点 35+j0（Ω，Smith 圆图；对应 S11≈−15.1 dB、VSWR≈1.43 仅为换算）；S21<−35 dB 指谐波抑制” |
| 同上 | 57 | 根因证据补“35+j0 是共轭阻抗点，单位 Ω，不是 S11 dB 门限；2026-10-23 复核” |
| `common-hardware/m-wireless-time.md` | 351 | 改为“ESP32-S3 的‘35+j0’是芯片共轭阻抗点 Ω，不是 dB 门限，见 M1/RF-02” |
| 同上 | 1010–1013 | 把“需要同步修正”第 2 条从“仍在传播/疑似 S11≤−35 dB”改为“已按原页定义统一（2026-10-23 关闭）”，保留历史问题、原页原文、修改摘要与证据路径 |
| `source-register.md` | 91（RF-S01 行） | 查阅日期补“RF Tuning 节 2026-10-23 复核原文”；支持内容补“35+j0 为芯片共轭阻抗点（Ω，Port 1 看进去的输入阻抗），−35 dB 属 S21@4.8/7.2 GHz 谐波抑制”；不能推广列补“35+j0 不是 S11 dB 门限，不能改写成 S11 ≤ −35 dB” |

**未改动（有意保留历史）：**

- `docs/common-hardware-gap-analysis.md`：C40 原始问题记录（:497）与临时同步口径（:414）保持原样，作为“历史问题”证据；关闭状态以本文件为准。
- `docs/evidence/common-hardware-2026-10-22/audit/m-wireless-time.md`：审计原文保持原样（历史审计记录）。
- `docs/round5/a-inventory-raw.json`：原始盘点 JSON，属于其他流程的数据，不改。
- `docs/task-ledger-round5.md`：由主流程维护；其中 :48/:68 仍写“C40/C76 两条未关闭”，建议主流程在汇总时更新（本任务不越权修改）。

**测试约束说明：** `w02-antenna.md` 的 `last_reviewed` 保持 `2026-10-20`，因为 `tests/test_design_content.py` 对全部设计卡断言该值；复核日期记录在卡片 §12 来源表。`f18`、`d4` 的 `last_reviewed` 已更新为 `2026-10-23`（无对应测试断言）。

---

## 5. 受影响引用（`design-hardware/references/` 内）

| 引用/文件 | 关系 | 处理 |
|---|---|---|
| `design-cards/wireless/w02-antenna.md` | C40 点名的 W02 | 已修改（3 处 + 来源表） |
| `engineering-deepdives/topics/d4-wireless-integration.md` | C40 点名的 D4 | 已修改（S11 测量行、§7.4、来源表） |
| `simulation-measurement.md` | C40 点名的测量总纲 | 已修改（7 处 + §6.4 说明段） |
| `failures/f18-antenna-enclosure.md` | 同主题失效卡，审计中另被点名 | 已修改（2 处） |
| `common-hardware/m-wireless-time.md` | M 组知识文件（与审计文件同名但不同路径） | 已修改（2 处；历史问题条目改为关闭） |
| `source-register.md` | RF-S01 来源登记 | 已修改（1 行） |
| `design-cards/wireless/w01-wifi-ble.md`、`w04-gnss.md`、`examples/x12-antenna.md`、`failures/f25-radio-tx-resets-system.md`、`failures/f32-enclosure-degrades-rf-and-thermal.md`、`module-integration.md` | 只写“S11 按模组/天线要求”，未复制 35+j0 | 无需修改 |
| `docs/task-ledger-round5.md` | 汇总台账仍记 C40 未关闭 | 建议主流程更新（未改） |

---

## 6. 回归验证

执行环境：`C:/Users/jlc/work/hds-round5`，Python 3.13，2026-10-23。

| 检查 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `python -m unittest discover -s tests` | **Ran 574 tests … OK**（同日多次重跑均 OK） |
| 设计内容（含 w02 卡片结构/来源） | `python -m unittest discover -s tests -p "test_design_content.py"` | **Ran 14 tests … OK** |
| common-hardware 文档结构（含 m-wireless-time） | `python -m unittest discover -s tests -p "test_common_hardware.py"` | **Ran 5 tests … OK** |
| 残留错误口径 | `grep -rn "疑似应为 S11" design-hardware/references` | **1 命中**，且仅为 `m-wireless-time.md:1011` 对历史问题的复述（“曾推断…”），不是现行建议口径；历史 `docs/` 审计/分析文件保留原文 |
| 35+j0 现状 | `grep -rn "35+j0" design-hardware/references` | **22 行命中**，全部带“芯片共轭阻抗点（Ω）/不是 dB 门限”或“已关闭”说明；无“S11 约 35+j0”写法 |
| Markdown 表格列数 | 自检脚本检查 5 个内容文件 | 5 个文件通过；`source-register.md` 第 239–240 行有**修改前已存在**的列数不一致（CHW-S126/S127），与本任务无关，未触碰 |

**说明：** 全量测试在本任务开始时为 565 tests（OK）；执行期间其他并行 agent 修改了 `tests/test_eda_exec_pcb.py` 等文件，测试数变为 574。上述 574 是本任务完成时的实际结果；本任务没有修改任何测试或代码。

未执行：VNA/S11/S21 实测、EM 仿真、暗室/OTA。以上均为文档口径核对，不构成硬件验收。

---

## 7. 最终状态

| 项 | 状态 | 说明 |
|---|---|---|
| C40 原始问题（35+j0 定义不完整/重复传播） | **CLOSED** | 原页已取得并逐字核对；修改前 16 行、5 个知识文件的表述已统一（另补 `source-register.md`） |
| C40 的“疑似 S11 ≤ −35 dB” | **REJECTED** | −35 dB 属于 S21@4.8/7.2 GHz 谐波抑制；S11 的正确判据是 Smith 圆图上的 35+j0 Ω 共轭点 |
| 35+j0 的正确含义 | **CONFIRMED** | “chip conjugate point 35+j0”，Port 1（靠芯片端）看进去的输入阻抗≈35+j0 Ω；50 Ω 归一化换算为 S11≈−15.1 dB、VSWR≈1.43（换算值，不是门限） |
| 知识库文件 | **DONE** | 6 个文件已修改；历史审计/分析文件保留原样 |
| 回归测试 | **PASS** | 全量 574 tests OK；聚焦 14 + 5 tests OK |
| 待主流程处理 | **OPEN（不属于 K-1）** | `docs/task-ledger-round5.md` 的 C40 状态更新；其他芯片/模组的共轭点核对；页面为 “latest”、无修订号，后续改页需复核 |
| 硬件实测 | **NOT RUN** | 无 VNA/暗室/样机；本记录不声称任何实测通过 |

**证据入口：** 本文件 `docs/evidence/k-2026-10-23/closure-c40.md`；原页 URL 与访问日期见 §3.1；原文引用见 §3.2；修改前后位置见 §2/§4；测试结果见 §6。
