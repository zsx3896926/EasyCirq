# DS18B20 8 点 1-Wire 总线：12 位读一轮温度的最短时间复核

- **固定快照：** `4c9db61628e4a83f01acad1c53ea5c0665182325`（`4c9db61`）
- **任务：** 一条 1-Wire 总线挂 8 个 DS18B20，12 位分辨率，读一轮温度最少需要多长时间；广播转换（Skip ROM/Convert T）与逐个寻址转换的区别；750 ms 是否要乘以 8。
- **结论级别：** 原厂手册复核 + 独立算例，**不是硬件实测**。S1 仍保持“连接级证据”，本复核不把它升级为功能验证。
- **仓库文件未修改。** 本文件与计算脚本都写在仓库外的 `C:\Users\jlc\work\hds-common-scratch\rerun\`。
- **并发变更说明：** 复核开始时 HEAD=`4c9db61`；复核期间另一并发会话先后提交 `d97b6f3`、`662a7ab`，工作树 HEAD 已推进。DS18B20 的 `a-environment.md:262` 和 `:310` 在 `4c9db61` 与 `662a7ab` 完全相同；本报告的仓库行号/原文以 `git show 4c9db61:...` 为准。`d97b6f3` 还给 `a-environment.md:203/354` 和 `source-register.md:149` 增加了 “SKIP ROM/CONVERT T 多点广播” / “Command Set” 字样，这些**不属于**固定快照 4c9db61；本报告在 §1/§5.3 分别标注。工作树里的 relay/decisions 改动来自其他会话，与本任务无关。

---

## 0. 结论摘要

| 调度 | 转换时间 | 读回时间 | 完整一轮 | 说明 |
|---|---:|---:|---:|---|
| **广播转换 + 逐器件读 9 字节（含 CRC）**，外部供电，标准速，最小合法时隙 | **750 ms 一次** | **81.856 ms** | **833.792 ms ≈ 0.834 s** | 推荐；8 个探头同时转换，不是 8×750 ms |
| 广播转换 + 逐器件只读 2 字节温度（无 CRC） | 750 ms 一次 | 54.528 ms | 806.464 ms ≈ 0.806 s | 协议允许读完 2 字节后发 reset 终止；但失去 CRC |
| 逐个寻址转换，且每个都等 750 ms 再下一个 | 8 × 750 ms = 6,000 ms | 81.856 ms | 6,128.576 ms ≈ 6.13 s | 这就是“750 ms × 8”真正适用的场景 |
| 广播转换 + 下一次转换与本次读回流水线（工程推断） | 750 ms/轮 | 隐藏 | ≈751.936 ms/轮（稳态） | 手册只说外部供电时总线在转换期间可承载其他通信；“转换期间读上一轮 scratchpad”未明确保证，标 `待核实` |

**直接回答：**

- 按最稳妥的 9 字节读回（含 CRC），**完整一轮约 833.792 ms（0.834 s）**；其中**转换本身是 750 ms 一次**，读回约 81.9 ms。
- 若只读 2 字节温度、不读 CRC，**约 806.464 ms（0.806 s）**。
- **750 ms 不需要乘 8。** 广播转换让 8 个 DS18B20 同时转换，转换阶段按最慢的一个算，仍是 750 ms（max）一次。
- 只有“逐个寻址、且每个都等 750 ms 转换完成再下一个”的**串行**调度，才是 8×750 ms；完整一轮约 6.13 s。
- **750 ms 是手册保证的最大值（MAX），不是典型值。** 手册没有给 tCONV 的 TYP/MIN；不能把“实际可能更早完成”当作保证值。

**仓库当前文本需要修正的两点：**

1. `design-hardware/references/common-hardware/a-environment.md:262` 和 `:310` 把 9 位写成 `187.5 ms`。手册 Table 2 的对应关系是 **9 位 93.75 ms、10 位 187.5 ms、11 位 375 ms、12 位 750 ms**。187.5 ms 是 10 位的值，不是 9 位。
2. 同两行的“只有逐个 `Match ROM (0x55)` + `Convert T` 才是 N×750 ms”表述过宽。准确说法是：**逐个寻址且串行等待每个转换完成**，才是 N×750 ms；广播转换是 750 ms 一次。逐个寻址如果背靠背发命令、让转换重叠，理论上可能不是 N×750 ms，但手册没有明确给出这种调度的保证，标 `待核实`，不建议依赖。

---

## 1. 实际读过的文件/小节

### 1.1 仓库文件

| 文件 | 实际读过的内容 |
|---|---|
| `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\a-environment.md` | §A2（第 199–357 行）：结论、证据行、路线表、必查参数、电路组成、参数与算例、逐脚、程序、验证、常见误判、采购、来源与证据；重点第 201–203、219、243、262、280、294–310、332、339–357 行；文件末尾来源表第 1150 行（CHW-S004）。**本报告按 `git show 4c9db61:...` 的版本引用；262/310 与 662a7ab 相同，203/354 在 4c9db61 中没有 d97b6f3 后加的“SKIP ROM/CONVERT T 多点广播”字样。** |
| `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\source-register.md` | 第 149 行 CHW-S004（**4c9db61 版本**）：DS18B20 `19-7487；Rev 6；7/19`，查阅范围“第 1–4 页：Features、引脚、精度、分辨率、转换时间”，支持“750 ms（12 位）”；**没有** 662a7ab 后加的“Command Set / 多点广播转换”字样 |
| `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\applications\01-temperature-alarm.md` | 第 22、30 行：DS18B20 作为数字备选、`750 ms 转换` |
| `C:\Users\jlc\work\hardware-design-skill\docs\common-hardware-report.md` | 第 54、96 行：A 组器件清单、A2 补 DS18B20 温区的记录 |
| `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\audit\a-environment.md` | A2 缺口分析（约第 73–98 行）：DS18B20 定位为远距离/多点 1-Wire 路线；当时判定 A2 为 missing |
| `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\blind\B1.md` | §3.1–3.2、§4、§5.1、§6：DS18B20 路线、`12 位 750 ms`、1 Hz 采样、未核对项 |
| `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\blind\eval.md` | B1 评分（5/5/5/5/5/5）、P1-5（DS18B20 ±0.5 °C 温区未写在 A2 正文）、第 135 行 routing 结论 |
| `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\README.md` | 第 50 行：A2 补 DS18B20 ±0.5 °C 仅 −10…85 °C 的记录 |
| `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\rerun\calc.py` | 现有未跟踪的复算脚本；其 `ds18b20_read_time()` 函数与输出（见 §4.8 对账） |
| Git 提交 `4c9db61` | `git show --stat 4c9db61` 与 `git show 4c9db61 -- design-hardware/references/common-hardware/a-environment.md`；父提交 `e5094e4` 的第 262 行原文 |

### 1.2 原厂手册

**Maxim Integrated DS18B20 Programmable Resolution 1-Wire Digital Thermometer，文档号 `19-7487；Rev 6；7/19`。**
下载地址：`https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf`
本地文件：`C:\Users\jlc\work\hds-common-scratch\rerun\src\DS18B20_19-7487_Rev6.pdf`
SHA-256：`066c8a3c7e9222c49e84488840d5cfe9dd109cf0da6ab4a55480cebac8f97f76`

实际读过的页/小节（页码为手册页脚印刷页码）：

| 页 | 小节/表 | 读到的内容 |
|---|---|---|
| p.1 | General Description / Benefits and Features | 9–12 位；±0.5 °C（−10…85 °C）；每个器件有唯一 64-bit ROM；多点能力 |
| p.2 | DC Electrical Characteristics | VDD 3.0–5.5 V；Active Current IDD typ 1 mA / max 1.5 mA（VDD=5 V，Note 9）；Standby Current、VIH/VIL 等 |
| p.3 | AC Electrical Characteristics | **tCONV：9 位 93.75 ms、10 位 187.5 ms、11 位 375 ms、12 位 750 ms（MAX 列）**；tSLOT min 60 µs；tREC min 1 µs；tRSTH/tRSTL min 480 µs；tSPON max 10 µs；CIN/OUT max 25 pF |
| p.5 | Overview / Operation—Measuring Temperature | 上电默认 12 位；总线上可寻址的器件数“virtually unlimited”；外部供电时转换期间可发 read time slot 查状态 |
| p.6 | Temperature Register / Table 1 | 16 位符号扩展二进制补码；12 位 1 LSB = 0.0625 °C；**上电复位值 +85 °C** |
| p.7 | Powering the DS18B20 | 寄生供电需在 Convert T 后 10 µs 内使能强上拉，转换期间**不得有其他总线活动**；外部供电时**总线可承载其他通信**；转换电流可高至 1.5 mA；4.7 kΩ 上拉图；Skip ROM + Read Power Supply (0xB4) 判断供电模式 |
| p.9 | Configuration Register / Table 2 | 上电默认 R1=R0=1（12 位）；**Table 2：9 位 93.75 ms、10 位 187.5 ms、11 位 375 ms、12 位 750 ms（MAX CONVERSION TIME）**；CRC 多项式 X^8+X^5+X^4+1 |
| p.10 | 1-Wire Bus System / Transaction Sequence | 每次访问必须 Step 1 Initialization → Step 2 ROM Command（8 bits）→ Step 3 Function Command；64-bit ROM；全部 LSB first；总线低电平超过 480 µs 会复位所有器件 |
| p.11 | ROM Commands / Function Commands | Match ROM [55h] + 64-bit ROM；**Skip ROM [CCh] + Convert T [44h] 可使所有 DS18B20 同时转换**；**Skip ROM + Read Scratchpad 多器件会数据冲突**；Read Scratchpad 读到第 9 字节（byte 8 = CRC），可随时 reset 终止 |
| p.12 | Table 3 / Note 1 | Convert T 44h；Read Scratchpad BEh（up to 9 data bytes）；**寄生供电时强上拉期间“No other bus activity may take place”** |
| p.15 | Initialization Procedure / Write Time Slots | reset 低电平 min 480 µs；DS18B20 等 15–60 µs 后发 presence 60–240 µs；reset 高电平 min 480 µs；写时隙 min 60 µs + 1 µs recovery |
| p.16 | Read Time Slots | 读时隙 min 60 µs + 1 µs recovery；数据在下降沿后 15 µs 内有效，主机须在 15 µs 内采样 |
| p.20 | Revision History / 免责声明 | `19-7487; Rev 6; 7/19`；**Electrical Characteristics 表的 min/max 是保证值，其他参数是指导值** |

### 1.3 未采用的资料

- 没有使用训练记忆里的“DS18B20 大约 750 ms”之类数值；所有时间值都来自上表页码或仓库文件。
- 没有使用二手模块资料、卖家页面或非原厂时序图。
- 没有把 DS18B20 与其他 1-Wire 器件（如 DS18S20、MAX31820）的时序混用；本答案只针对 DS18B20 `19-7487 Rev 6`。

---

## 2. 关键事实：保证值 / 典型值 / 假设值

| 项 | 数值 | 类型 | 来源 |
|---|---:|---|---|
| 12 位 tCONV | **750 ms max** | **保证值（MAX）** | DS18B20 p.3 AC 表；p.9 Table 2 “MAX CONVERSION TIME” |
| 11 位 tCONV | 375 ms max | 保证值 | 同上 |
| 10 位 tCONV | 187.5 ms max | 保证值 | 同上 |
| 9 位 tCONV | **93.75 ms max** | 保证值 | 同上；**不是 187.5 ms** |
| tCONV 的 TYP/MIN | 手册未给 | `待核实` | p.3 只有 MAX 列；p.20 只保证 min/max |
| 1-Wire 写/读时隙 | min 60 µs | 保证值（min） | p.3 AC 表；p.15/p.16 |
| 时隙间 recovery | min 1 µs | 保证值（min） | p.3；p.15/p.16 |
| reset 低电平 | min 480 µs | 保证值（min） | p.3；p.15 |
| reset 高电平 | min 480 µs | 保证值（min） | p.3；p.15 |
| presence 等待/脉宽 | 15–60 µs / 60–240 µs | 保证范围 | p.15 |
| 强上拉使能 | Convert T 后 max 10 µs | 保证值（max） | p.7；p.12 Table 3 Note 1 |
| 8 个器件同时转换 | 支持 | 保证功能 | p.11 Skip ROM + Convert T 示例；p.5 “virtually unlimited” |
| Skip ROM + Read Scratchpad（>1 器件） | **禁止，会冲突** | 保证限制 | p.11 |
| 外部供电转换期间总线 | 可承载其他通信 | 保证功能 | p.7 |
| 寄生供电转换期间总线 | 不得有其他活动 | 保证限制 | p.7；p.12 Note 1 |
| 转换电流 | max 1.5 mA/器件（VDD=5 V） | 保证值（max） | p.2 DC 表；p.7 文字“as high as 1.5mA” |
| 上电默认温度寄存器 | +85 °C | 保证值 | p.6 Table 1 脚注 |
| 上电默认分辨率 | 12 位 | 保证值 | p.5；p.9 |
| 4.7 kΩ 上拉 | 手册图值 | 典型/建议 | p.7 Figure 6/7；p.10 “approximately 5kΩ” |
| 8 器件 + 长线的总线电容/上升沿 | 未给 | `待核实` | p.3 只给 CIN/OUT max 25 pF；电缆参数未给 |

**保证值与典型值的边界：**

- 手册 p.20 明确：Electrical Characteristics 表里的 min/max 是保证值，其他参数是 guidance。750 ms 在 AC 表的 MAX 列，所以它是**保证的最大转换时间**，不是“典型 750 ms”。
- 手册没有给 tCONV 的 TYP 或 MIN。若主机在 750 ms 之前就去读，**可能**读到上一次转换结果或上电默认 +85 °C（p.6 上电默认 +85 °C；p.11 说 Convert T 后转换完成才把结果写入温度寄存器；手册没有明确“转换期间 Read Scratchpad 返回什么”，标 `待核实`）。因此不能把提前读到的值当本轮新数据。
- 若主机轮询 Convert T 后的状态位（外部供电时，转换中读 0、完成读 1），实际完成可能早于 750 ms；但手册只保证“不超过 750 ms”，没有给出提前量。因此**保证设计按 750 ms 上限排时间**；想利用提前完成，必须实测并承担批次/温度/电压差异，标 `待核实`。

---

## 3. 完整调度顺序

### 3.1 推荐：广播转换 + 逐器件读回

**前提/假设：**

- 8 个 DS18B20 都外部供电（VDD 接 3.0–5.5 V），不是寄生供电。
- 12 位分辨率（上电默认，或配置寄存器 R1=R0=1 已写入并保存在 EEPROM）。
- 8 个 64-bit ROM 码已知（上电时用 Search ROM [F0h] 枚举一次并保存；本轮的 750 ms 预算不含枚举）。
- 1-Wire 主机满足标准速时序：时隙 ≥60 µs、recovery ≥1 µs、reset 低/高各 ≥480 µs；总线电容/上拉能在采样窗口内达到 VIH。
- 总线上只有这 8 个 DS18B20（或至少没有会在同一时刻响应的其他从机）。

**调度：**

```text
上电/初始化（一次性，不计入本轮）：
  Reset + Presence
  Search ROM [F0h] × 若干轮 → 得到 8 个 64-bit ROM 码并保存
  可选：Reset + Skip ROM [CCh] + Read Power Supply [B4h] + read slot
        → 若总线被拉低，说明有寄生供电器件；本轮必须用强上拉

每一轮：
  1. Reset + Presence                                  960 µs
  2. Skip ROM [CCh]                                    488 µs
  3. Convert T [44h]                                   488 µs
     → 8 个 DS18B20 同时开始转换
  4. 等待 750 ms（12 位 max）
     外部供电：等待期间总线可做其他通信；本轮简单调度就是等满 750 ms
     寄生供电：Convert T 后 10 µs 内使能强上拉，保持 750 ms；
               强上拉期间总线上不得有其他活动
  5. for i = 1..8:
       Reset + Presence                                960 µs
       Match ROM [55h]                                 488 µs
       发送 ROM_i 的 64 bit                             3,904 µs
       Read Scratchpad [BEh]                            488 µs
       读 9 字节（byte 0..8，含 CRC）                    4,392 µs
       校验 CRC；温度 = signed16(byte1:byte0) × 0.0625 °C
  6. 本轮结束；下一轮从步骤 1 重新开始
```

**关键点：**

- `Skip ROM (0xCC)` 让总线上所有 DS18B20 同时接收后面的 `Convert T (0x44)`；8 个器件各自内部同时转换，转换阶段取最慢的一个，仍是 750 ms 一次（p.11 明确给出这个用法）。
- 读回**不能**用 `Skip ROM + Read Scratchpad`：多于一个从机时多个器件会同时发送，数据冲突（p.11 明确）。所以读回必须逐器件 `Match ROM (0x55)` + 64-bit ROM + `Read Scratchpad (0xBE)`。
- 每个器件的读回都要一次新的 Reset + Presence + Match ROM；这是 p.10 的事务顺序要求（Step 1 → Step 2 → Step 3，每次访问都要走）。
- 9 字节中的 byte 8 是 scratchpad CRC（覆盖 byte 0–7），多项式 `X^8 + X^5 + X^4 + 1`（p.9/p.11）。若只读 2 字节温度，必须在读完 byte 1 后发 reset 终止；这样省时间但没有 CRC（p.11 允许“issue a reset to terminate reading at any time if only part of the scratchpad data is needed”）。
- 读回顺序可以任意；总时间与顺序无关。若某个器件 CRC 失败，按每器件 10.232 ms 追加重读时间。

### 3.2 不推荐：逐个寻址转换（串行等待）

```text
for i = 1..8:
  Reset + Presence                                      960 µs
  Match ROM [55h]                                       488 µs
  发送 ROM_i 的 64 bit                                   3,904 µs
  Convert T [44h]                                        488 µs
  等待 750 ms（只等这一个器件）
  Reset + Presence                                      960 µs
  Match ROM [55h]                                       488 µs
  发送 ROM_i 的 64 bit                                   3,904 µs
  Read Scratchpad [BEh]                                  488 µs
  读 9 字节                                              4,392 µs
```

- 每个器件都要“发转换命令 → 等 750 ms → 再读”，8 个串行就是 **8 × 750 ms = 6,000 ms 的转换等待**，加上命令和读回约 **6.13 s**。
- 这就是“750 ms × 8”真正成立的场景；它不是广播转换的必要代价，而是**串行调度**的代价。
- 若外部供电且把 8 个 `Match ROM + Convert T` 背靠背发出、让转换重叠，理论上不是 8×750 ms；但手册没有明确说明“转换进行中收到 reset/ROM 命令不会干扰该次转换”，因此这种调度标 `待核实`，不建议作为保证方案。广播转换没有这个不确定性。

### 3.3 可选：读回与下一次转换流水线（工程推断，`待核实`）

外部供电时，手册明确“the 1-Wire bus is free to carry other traffic during the temperature conversion time”（p.7）。因此可以尝试：

```text
t=0：第 N 轮转换完成
  发第 N+1 轮广播命令（Reset + Skip ROM + Convert T）   1.936 ms
  在第 N+1 轮转换的 750 ms 内，读第 N 轮的 8 个 scratchpad  81.856 ms
  第 N+1 轮转换完成后，重复
```

- 稳态周期约 **751.936 ms/轮**（广播命令 + 750 ms），读回被隐藏在转换期间。
- 但这依赖“转换进行中读同一器件的 scratchpad 仍返回上一轮结果”这一行为；手册只说转换结束后结果写入温度寄存器，没有明确保证转换期间 scratchpad 的旧值可读。标 `待核实`。
- 若不能保证，就按 §3.1 的简单串行调度：每轮 833.792 ms。**不要为了省 82 ms 而冒读到半更新数据的风险。**

---

## 4. 计算过程

### 4.1 广播转换命令

单位统一用 µs；1 ms = 1,000 µs。

- Reset + Presence：`tRSTL + tRSTH = 480 µs + 480 µs = 960 µs`（p.3/p.15；presence 在 480 µs 高电平窗口内）。
- Skip ROM [CCh]：8 bit × (60 µs + 1 µs) = `8 × 61 = 488 µs`。
- Convert T [44h]：8 bit × 61 µs = `488 µs`。

```text
T_broadcast = 960 + 488 + 488 = 1,936 µs = 1.936 ms
```

### 4.2 转换

- 12 位 tCONV = **750 ms max**（p.3 AC 表；p.9 Table 2）。
- 从广播命令开始到所有器件转换完成：

```text
T_to_all_done = 1.936 ms + 750 ms = 751.936 ms
```

### 4.3 逐器件读回（9 字节，含 CRC）

每个器件的事务：

- Reset + Presence：`960 µs`
- Match ROM [55h]：`8 × 61 = 488 µs`
- 64-bit ROM 码：`64 × 61 = 3,904 µs`
- Read Scratchpad [BEh]：`8 × 61 = 488 µs`
- 9 字节数据：`9 × 8 × 61 = 72 × 61 = 4,392 µs`

```text
T_read9 = 960 + 488 + 3,904 + 488 + 4,392
        = 10,232 µs
        = 10.232 ms/器件
```

核对位数：`8 (Match ROM) + 64 (ROM) + 8 (Read Scratchpad) + 72 (data) = 152 bit`；`152 × 61 µs = 9,272 µs`；加 reset 960 µs = **10,232 µs**。一致。

### 4.4 8 个器件的读回

```text
T_read8 = 8 × 10.232 ms = 81.856 ms
```

### 4.5 完整一轮（9 字节读回）

```text
T_round9 = T_broadcast + T_conv + T_read8
         = 1.936 ms + 750 ms + 81.856 ms
         = 833.792 ms
         ≈ 0.834 s
```

### 4.6 只读 2 字节温度（无 CRC）的变体

- 每器件数据：`2 × 8 × 61 = 16 × 61 = 976 µs`
- 每器件读回：`960 + 488 + 3,904 + 488 + 976 = 6,816 µs = 6.816 ms`
- 8 个器件：`8 × 6.816 = 54.528 ms`
- 完整一轮：`1.936 + 750 + 54.528 = 806.464 ms ≈ 0.806 s`

这是协议层“最少数据”的下界；代价是没有 CRC，通信误码无法检测。仓库的推荐调度读 9 字节，所以应使用 **833.792 ms**，不是 806.464 ms。

### 4.7 逐个寻址、串行等待的完整时间

- 每器件转换命令事务：`Reset 960 + Match ROM 488 + 64-bit ROM 3,904 + Convert T 488 = 5,840 µs = 5.84 ms`
- 每器件“转换命令 + 750 ms + 读回 9 字节”：`5.84 + 750 + 10.232 = 766.072 ms`
- 8 个器件：`8 × 766.072 = 6,128.576 ms ≈ 6.13 s`
- 其中转换等待：`8 × 750 = 6,000 ms`。

### 4.8 与仓库现有 `rerun/calc.py` 的对账

仓库工作树里有一个未跟踪的 `docs/evidence/common-hardware-2026-10-22/rerun/calc.py`（不属于固定快照 4c9db61 的提交内容）。它的 DS18B20 公式是：

```python
def ds18b20_read_time(n, bit_us=60, bits_per_device=64 + 8 + 9 * 8, reset_us=960):
    return n * (reset_us + bits_per_device * bit_us) / 1e6
```

即 `bits_per_device = 64 + 8 + 72 = 144 bit`，输出：

```text
8 devices standard-speed read phase ~= 0.077 s; +750 ms conversion = 0.827 s
```

这个结果**少算了三项**：

1. 每器件事务需要**两个** 8-bit 命令（Match ROM 0x55 和 Read Scratchpad 0xBE），脚本只算了 1 个。少 `8 × 8 × 60 µs = 3.840 ms`（8 器件合计）。
2. 每个 bit 之间还有 min 1 µs recovery；脚本按 60 µs/bit 算，少 `8 × 152 × 1 µs = 1.216 ms`。
3. 脚本还漏了广播命令本身（Reset + Skip ROM + Convert T = 1.936 ms）。

对账：

```text
826.800 ms（脚本）
+ 3.840 ms（补第 2 个 8-bit 命令）
+ 1.216 ms（补 1 µs/bit recovery）
+ 1.936 ms（补广播命令）
= 833.792 ms（本复核）
```

所以如果父任务直接引用 0.827 s，应改为 **0.834 s**（9 字节读回）。若只读 2 字节，则是 **0.806 s**。

### 4.9 9/10/11/12 位转换时间表（手册 Table 2）

| 分辨率 | MAX CONVERSION TIME | 与 tCONV 的关系 |
|---:|---:|---|
| 9 bit | **93.75 ms** | tCONV/8 |
| 10 bit | 187.5 ms | tCONV/4 |
| 11 bit | 375 ms | tCONV/2 |
| 12 bit | 750 ms | tCONV |

**仓库错误定位：** `a-environment.md:262` 写“9 位 187.5 ms”，`:310` 写“9 位为 187.5 ms”。按上表，9 位是 **93.75 ms**；187.5 ms 是 10 位。两处都应改为“9 位 93.75 ms（10 位 187.5 ms）”。

---

## 5. 修改前后

### 5.1 修改前（父提交 `e5094e4`，`a-environment.md:262`）

原文：

> DS18B20 12 位一次最长 750 ms，多点轮询要按“个数 × 750 ms”排时间。

**问题：** 把广播转换和逐个寻址转换混为一谈。多点用 `Skip ROM + Convert T` 广播时，所有探头同时转换，转换时间是 750 ms 一次，不是个数×750 ms。该结论对“逐个寻址、串行等待”才成立。

### 5.2 修改后（`4c9db61`，`a-environment.md:262` 与新增的 `:310`）

原文：

> DS18B20 12 位一次最长 750 ms；多点用 `Skip ROM (0xCC)` + `Convert T (0x44)` 广播时，所有探头**同时转换**，总转换时间仍是 750 ms（9 位 187.5 ms），不是“个数 × 750 ms”。只有逐个 `Match ROM (0x55)` + `Convert T` 才是 N×750 ms。

> **DS18B20 多点调度**：先 `Skip ROM (0xCC)` + `Convert T (0x44)` 广播，所有探头同时转换；等 750 ms（12 位，9 位为 187.5 ms），再逐个 `Match ROM (0x55)` + `Read Scratchpad (0xBE)` 读 9 字节。总转换时间是 750 ms，不是 N×750 ms；读回时间按总线速率另算（标准速每个约数 ms）。若逐个寻址转换，才是 N×750 ms，不要把两种调度混用。长线/多点不要用寄生供电。

**评价：**

- **正确：** 广播转换让 8 个探头同时转换；总转换时间 750 ms 一次，不是 N×750 ms。这是本次修改的核心，方向正确。
- **错误：** `9 位 187.5 ms` 应为 `9 位 93.75 ms`；`187.5 ms` 是 10 位。
- **过宽：** “只有逐个 `Match ROM + Convert T` 才是 N×750 ms”应限定为“逐个寻址**且每个都等转换完成再下一个**”。逐个寻址如果背靠背发命令、让转换重叠，理论上可能不是 N×750 ms；但手册没有明确保证，标 `待核实`，不建议依赖。
- **偏模糊：** “读回时间按总线速率另算（标准速每个约数 ms）”应给出数：9 字节读回 **10.232 ms/器件、81.856 ms/8 器件**；2 字节读回 **6.816 ms/器件、54.528 ms/8 器件**。
- **口径要分清：** “总转换时间 750 ms”是转换阶段；**完整一轮**是 833.792 ms（9 字节）或 806.464 ms（2 字节）。不要把 750 ms 当成“读一轮”的完整时间。

### 5.3 全库检索结果

在固定快照 4c9db61 上检索 `DS18B20`、`750`、`187.5`、`N×750`、`Skip ROM`、`0xCC`、`0x44`：

| 位置 | 原文/结论 | 判定 |
|---|---|---|
| `a-environment.md:262` | `9 位 187.5 ms`；`只有逐个 ... 才是 N×750 ms` | **需修正**（9 位数值错误；N×750 ms 表述过宽） |
| `a-environment.md:310` | `9 位为 187.5 ms`；`若逐个寻址转换，才是 N×750 ms` | **需修正**（同上；读回时间可补具体数） |
| `a-environment.md:203` | **4c9db61 版本**：`12 位/750 ms`；没有 `SKIP ROM/CONVERT T 多点广播` | 750 ms 数值正确，不需改；`SKIP ROM/CONVERT T 多点广播` 是 `d97b6f3` 后加的，不属于固定快照 |
| `a-environment.md:219` | `750 ms（12 位）` | 正确，不需改 |
| `a-environment.md:332` | “用 DS18B20 的 750 ms 转换时间做 10 Hz 控制”是误判 | 正确，不需改 |
| `a-environment.md:354` | **4c9db61 版本**：CHW-S004 `750 ms`，查阅范围“第 1–4 页”；没有 `Command Set`/`SKIP ROM/CONVERT T 广播` | 数值正确；查阅范围建议补 p.9、p.15–16。`Command Set`/多点广播字样是 `d97b6f3` 后加的，不属于固定快照 |
| `a-environment.md:1150` | **4c9db61 版本**：组来源表 `750 ms（12 位）`；没有 `多点广播转换`/`Command Set` | 数值正确；查阅范围同上建议补 |
| `source-register.md:149` | **4c9db61 版本**：CHW-S004 `750 ms（12 位）`；没有 `多点广播转换`/`Command Set` | 数值正确；建议把“实际查阅范围”补到 p.3 AC 表、p.7 Powering、p.9 Table 2、p.10–12 命令、p.15–16 时序（这是补全，不是纠错） |
| `applications/01-temperature-alarm.md:30` | `750 ms 转换` | 正确，不需改 |
| `blind/B1.md:18/27/47/62` | `12 位 750 ms`、`转换时间最长 750 ms` | 正确，属历史原始回答，保留 |
| `docs/common-hardware-report.md:96` | 只记 A2 补 ±0.5 °C 温区，未提多点调度 | 不涉及，不需改 |
| `docs/evidence/.../audit/a-environment.md` | A2 缺口分析，未给 DS18B20 多点时序 | 历史审计记录，保留 |
| `docs/evidence/.../rerun/calc.py` | `bits_per_device=64+8+9*8`，输出 0.827 s | 未跟踪的复算脚本；少算 1 个命令字节 + recovery + 广播开销，见 §4.8 |

**历史原始回答的处理：** `blind/B1.md`、`audit/a-environment.md`、`blind/eval.md` 是历史记录，按用户要求**保留原文**，不回写。需要同步修正的是当前知识正文 `a-environment.md:262` 和 `:310` 的两处“9 位 187.5 ms”以及“只有逐个 … 才是 N×750 ms”的限定；来源登记 `source-register.md:149` 的“实际查阅范围”建议补全（这是完整性改进，不是数值纠错）。历史文件可以在旁边加注“已在 4c9db61 复核，见 rerun/ds18b20-multipoint.md”，但不要改原始评分/原始回答。

### 5.4 建议替换文本（供父任务应用，本任务未修改仓库）

把 `a-environment.md:262` 和 `:310` 合并/替换为下面这段（保留原意，修正数值与边界）：

> **DS18B20 多点调度：** 12 位 tCONV 最大 750 ms（9 位 93.75 ms、10 位 187.5 ms、11 位 375 ms、12 位 750 ms，手册 Table 2）。多点用 `Skip ROM (0xCC)` + `Convert T (0x44)` 广播时，所有探头**同时转换**，转换时间是 **750 ms 一次**，不是“个数 × 750 ms”。转换完成后逐个 `Match ROM (0x55)` + 64-bit ROM + `Read Scratchpad (0xBE)` 读 9 字节（含 CRC）；标准速（60 µs 时隙 + 1 µs recovery）每器件约 **10.23 ms**，8 个约 **81.86 ms**；完整一轮约 **833.8 ms（0.834 s）**。若只读 2 字节温度、不读 CRC，约 **806.5 ms（0.806 s）**。只有“逐个寻址且每个都等 750 ms 转换完成再下一个”的串行调度，才是 **8 × 750 ms = 6 s** 量级（含命令/读回约 6.13 s）；不要把广播和逐个寻址混用。长线/多点不要用寄生供电；若用寄生供电，强上拉必须在 Convert T 后 10 µs 内使能，转换期间总线不得有其他活动，8 个器件按 1.5 mA/器件估算约 12 mA。750 ms 是手册保证的最大值，不是典型值；手册没有给 tCONV 的 TYP/MIN。

---

## 6. 独立计算依据

### 6.1 公式

```text
T_txn = t_RSTL + t_RSTH
      + (N_rom_cmd + N_rom_code + N_func + N_data) × (t_SLOT + t_REC)

T_round_broadcast = T_broadcast_cmd + t_CONV + N_dev × T_read
T_round_serial    = N_dev × (T_dev_convert_cmd + t_CONV + T_read)
```

其中：

- `t_RSTL = 480 µs`，`t_RSTH = 480 µs`（p.3/p.15）。
- `t_SLOT = 60 µs`，`t_REC = 1 µs`（p.3/p.15/p.16）。
- `T_broadcast_cmd = 960 + (8 + 8) × 61 = 1,936 µs`。
- `T_read(9B) = 960 + (8 + 64 + 8 + 72) × 61 = 10,232 µs`。
- `T_read(2B) = 960 + (8 + 64 + 8 + 16) × 61 = 6,816 µs`。
- `T_dev_convert_cmd = 960 + (8 + 64 + 8) × 61 = 5,840 µs`。
- `t_CONV = 750,000 µs`（12 位 max）。

### 6.2 数值代入

```text
T_broadcast_cmd = 960 + 16 × 61 = 960 + 976 = 1,936 µs = 1.936 ms
T_read(9B)      = 960 + 152 × 61 = 960 + 9,272 = 10,232 µs = 10.232 ms
T_read(2B)      = 960 + 96 × 61 = 960 + 5,856 = 6,816 µs = 6.816 ms
T_dev_convert   = 960 + 80 × 61 = 960 + 4,880 = 5,840 µs = 5.840 ms

T_round(9B)     = 1.936 + 750 + 8 × 10.232
                = 1.936 + 750 + 81.856
                = 833.792 ms
T_round(2B)     = 1.936 + 750 + 8 × 6.816
                = 1.936 + 750 + 54.528
                = 806.464 ms
T_serial(9B)    = 8 × (5.840 + 750 + 10.232)
                = 8 × 766.072
                = 6,128.576 ms
```

### 6.3 独立脚本

计算脚本：`C:\Users\jlc\work\hds-common-scratch\rerun\ds18b20_calc.py`
运行结果（节选）：

```text
broadcast convert cmd: 1936 us = 1.936 ms (16 bits)
read 9B/device:        10232 us = 10.232 ms (152 bits)
read 2B/device:        6816 us = 6.816 ms (96 bits)
convert cmd/device:    5840 us = 5.840 ms (80 bits)

broadcast + 750 ms + 8x9B: 833.792 ms
broadcast + 750 ms + 8x2B: 806.464 ms
conversion alone:          750.000 ms
8x9B readback alone:       81.856 ms
8x2B readback alone:       54.528 ms
serialized individual:     6128.576 ms
back-to-back individual (inference, unverified): 878.576 ms

existing formula: 8 * (960 + 144*60) us = 76.800 ms
existing + 750 ms = 826.800 ms
add missing 8-bit command: 3.840 ms
add 1 us recovery/bit:     1.216 ms
add broadcast cmd overhead:1.936 ms
reconciled total:          833.792 ms
```

### 6.4 与“750 ms × 8”的对照

| 说法 | 是否正确 | 说明 |
|---|---|---|
| “8 个 DS18B20 广播转换，总转换时间 8×750 ms = 6 s” | **错** | 广播让 8 个同时转换，转换阶段 750 ms 一次（p.11） |
| “8 个 DS18B20 逐个寻址转换，总转换时间 8×750 ms = 6 s” | **只在串行等待时成立** | 逐个 `Match ROM + Convert T` 且每个等 750 ms 再下一个，才是 6 s；背靠背发命令让转换重叠的可行性未明确保证 |
| “750 ms 是典型值” | **错** | 手册只给 MAX，没有 TYP；p.20 明确 min/max 才是保证值 |
| “750 ms 是转换阶段，不是完整读一轮” | **对** | 完整一轮还要加广播命令 1.936 ms 和读回 81.856 ms（9 字节）或 54.528 ms（2 字节） |
| “读回可以 Skip ROM + Read Scratchpad 一次读完 8 个” | **错** | 多于一个从机会数据冲突（p.11）；必须逐器件 Match ROM |

---

## 7. 仍未核实事项

1. **tCONV 的 TYP/MIN：** 手册只给 MAX 750 ms，没有给典型/最小转换时间；实际器件可能早于 750 ms 完成，但**不能作为保证值**。若要用轮询提前读取，需实测并覆盖温度、电压、批次。`待核实`
2. **转换期间读 scratchpad：** 外部供电时手册说总线可承载其他通信（p.7），但没有明确说“转换进行中读同一器件的 scratchpad 会返回上一轮旧值”。§3.3 的 751.936 ms/轮流水线依赖这一点，`待核实`。
3. **转换进行中收到 reset/ROM 命令：** 逐个寻址“背靠背发 Convert T 让转换重叠”依赖“reset/ROM 命令不会干扰正在进行的转换”。手册没有明确保证；`待核实`。广播转换没有这个问题。
4. **8 器件 + 长线的总线电容/上升沿：** 手册只给 CIN/OUT max 25 pF（p.3）；8 个器件本身约 200 pF，4.7 kΩ 上拉下器件-only 上升沿约 1–2 µs，但电缆电容会显著增加。具体线长/线材/上拉值需按实测波形核对；仓库 A2 也把“长线/多点拓扑的电容与上拉”标为待核实。
5. **寄生供电的强上拉设计：** 8 个器件同时转换的电流按 1.5 mA/器件估算约 12 mA（p.2/p.7，VDD=5 V 条件）；3.3 V 下的实际值、MOSFET RDS(on)、电缆压降、VDD 最低 3.0 V 的余量都需按实际电路核对。`待核实`
6. **1-Wire 主机的实际时隙：** 本计算按手册最小合法值（60 µs 时隙 + 1 µs recovery）。实际主机可能用 70 µs 或更长时隙；每多 1 µs/bit，8 器件读回增加约 1.216 ms。需按主机实现核对。
7. **ROM 枚举时间：** 本计算假设 8 个 64-bit ROM 码已在初始化时用 Search ROM 得到并保存；Search ROM 的多轮枚举时间未计入。若每轮都重新枚举，时间要另加。
8. **器件真伪/批次：** 750 ms max 是原厂 DS18B20 `19-7487 Rev 6` 的保证值；兼容替代/翻新件的时序未核对。
9. **温度/电压条件：** 750 ms max 的条件是 −55…125 °C、VDD=3.0–5.5 V（p.3）。超出该范围不保证。
10. **仓库来源登记范围：** 固定快照 4c9db61 的 `source-register.md:149` 与 `a-environment.md:354/1150` 只写“第 1–4 页”（“Command Set”字样是 `d97b6f3` 之后才加的，不属于 4c9db61），但本次复核用到 p.3、p.7、p.9、p.10–12、p.15–16。建议把“实际查阅范围”补全，避免后续再出现“9 位/10 位”混淆。`待核实/待更正`
11. **仓库现有 `rerun/calc.py`：** 输出 0.827 s，少算 1 个 8-bit 命令、1 µs/bit recovery 和广播命令；若父任务引用该数，应改为 0.834 s（9 字节）或 0.806 s（2 字节）。该脚本是未跟踪文件，不属于固定快照 4c9db61 的提交内容。

---

## 8. 证据路径

### 8.1 仓库文件（固定快照 4c9db61）

- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\a-environment.md`
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\source-register.md`
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\applications\01-temperature-alarm.md`
- `C:\Users\jlc\work\hardware-design-skill\docs\common-hardware-report.md`
- `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\audit\a-environment.md`
- `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\blind\B1.md`
- `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\blind\eval.md`
- `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\README.md`
- `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\rerun\calc.py`（未跟踪）

### 8.2 原厂资料

- 手册 PDF：`C:\Users\jlc\work\hds-common-scratch\rerun\src\DS18B20_19-7487_Rev6.pdf`
- 提取文本：`C:\Users\jlc\work\hds-common-scratch\rerun\src\DS18B20_19-7487_Rev6.txt`
- 文档号/版本：`19-7487; Rev 6; 7/19`
- 来源 URL：`https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf`
- SHA-256：`066c8a3c7e9222c49e84488840d5cfe9dd109cf0da6ab4a55480cebac8f97f76`

### 8.3 本次复核产物

- 本文件：`C:\Users\jlc\work\hds-common-scratch\rerun\ds18b20-multipoint.md`
- 独立计算脚本：`C:\Users\jlc\work\hds-common-scratch\rerun\ds18b20_calc.py`
- 计算脚本输出：见 §6.3（可重跑 `python ds18b20_calc.py`）

### 8.4 结论边界

- 本复核是**手册复核 + 独立算例**，不是硬件实测；没有示波器波形、没有 8 个真实探头的转换完成时间统计。
- S1 仍是**连接级证据**，本复核没有把它升级为功能验证，也没有声称做过全在线 GUI 复验。
- 仓库文件未修改；本文件与脚本都在仓库外。若父任务要把 §5.4 的替换文本写入仓库，请另行按项目规则提交，并保留历史原始回答。
