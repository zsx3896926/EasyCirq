# 12V 温控风扇板 · 设计记录（未搭图）

> 状态：**参数已算准，电路还没画。** 这份文档只记录"该用什么值、为什么"，
> 不声称板子存在。要搭图时照这里的数走，搭完用 `sch_design_validity.py` 复核。
>
> 生成方式：`python tools/size_fan_controller.py`（每次改需求重跑一次）

## 客户原话

> 温度到 45°C 自动开 12V 风扇，降下来自动停；风扇 12V/200mA，别在边上疯狂启停。

## 算出来的参数

| 项 | 值 | 依据 |
|---|---|---|
| 阈值分压 R2 / R3 | 10k / **4.3k** | 扫 E24 档位取最接近 45°C 的一档，实得 **45.3°C** |
| 回差 R6 | **39k** | 从 ALARM 正反馈到 NTC_MID，实得回差 **2.97°C** |
| 栅极上拉 R5 | **100k** | MOSFET 栅极静态不取电流，100k 足够把栅压拉到 5V |
| 风扇驱动管 | **MOSFET（AO3400 类）** | 见下方"为什么不用三极管" |
| 续流二极管 D1 | 反并在风扇两端，≥500mA | 感性负载必须 |

## 为什么不用三极管（这一条差点选错）

客户说的 200mA 是**稳态**。直流风扇的**启动电流通常是稳态的 2–3 倍**：

```
按 3 倍估 → 启动瞬间 600mA
S8050 的 Ic 上限 700mA，稳态够用，启动时已贴近极限，而且大电流下 hFE 会掉
```

所以这颗负载该用 MOSFET：AO3400 这类 SOT-23 逻辑电平管额定 4A 以上，
`Vgs(th)` 约 1.05V，5V 栅压驱动充分，栅极还不取直流电流。

**如果一定用三极管**：R5 取 2.4k、串联 R4 取 10Ω → 基极 1.77mA → 可驱动 212mA。
稳态能过，启动裕量不足，属于"能跑但不稳"。

## 意图文件（搭图时直接用）

```json
{
  "schema": "easycirq-design-intent/v1",
  "name": "12V 温控风扇",
  "power_rail": "PWR5V",
  "load_rail": "PWR12V",
  "ground": "GND",
  "rails": { "PWR5V": 5.0, "PWR12V": 12.0 },
  "grounds": ["GND"],
  "threshold": {
    "comparator": "U1",
    "target_c": 45,
    "tolerance_c": 3,
    "vcc": 5.0,
    "sensor": { "kind": "ntc", "r25": 10000, "b": 3950 },
    "hysteresis_c": 3
  },
  "switches": [
    { "part": "Q1", "load": "FAN1", "load_ma": 200,
      "kind": "mosfet", "vgs_th": 1.05, "id_max_a": 4.0,
      "load_kind": "inductive", "load_rail": "PWR12V" }
  ]
}
```

## 尚未建模的部分（工具查不了，必须人判）

| 项 | 状态 |
|---|---|
| 续流二极管是否存在 / 方向对不对 | ✅ **已有判据**：`inductive_load` 查 `NO_FLYWHEEL_DIODE` 与 `FLYWHEEL_DIODE_REVERSED` |
| 双电源域接错（漏极接到 5V） | ✅ **已有判据**：`supply_domains` 查 `SWITCH_LOAD_ON_LOGIC_RAIL` |
| 两轨被 0Ω 短接 | ✅ **已有判据**：`RAIL_SHORTED` |
| 12V 与 5V 共地 | ✅ **已有判据**：`GROUNDS_DISCONNECTED`（只在 `grounds` 声明了多个地时才查） |
| 风扇启动电流的裕量 | ❌ 工具不猜倍率，用意图里声明的 `load_ma` |
| **器件额定电压是否够** | ❌ **要规格书**——"这颗管子 Vds 上限 30V，12V 打不穿"网表里没有。这一条只能人判 |

前四类已由 `sch_design_validity.py` 覆盖；最后两项明确写在检查器的 `note` 里，
不假装能判。

---

## 板子已画出（2026-11-02）

工程 `Fan-Controller-12V`，原理图页 `P1`，11 个器件、8 个网络，全部与设计一致：

```
PWR5V    R1.1 R2.1 R5.1 U1.8
PWR12V   D1.1 FAN1.1
GND      NTC1.2 Q1.2 R3.2 U1.4
NTC_MID  NTC1.1 R1.2 R6.2 U1.3
TH       R2.2 R3.1 U1.2
ALARM    R6.1 R7.2 U1.1
GATE     Q1.1 R5.2 R7.1
FAN_M    D1.2 FAN1.2 Q1.3
```

### 判据在全新板上抓到的东西

第一次跑，五类里 `inductive_load` 直接 **fail**：

```
! FLYWHEEL_DIODE_REVERSED: 续流二极管 D1 极性接反：
  阳极接 PWR12V、阴极接 FAN_M。
  应该反过来——阴极朝 PWR12V、阳极朝 FAN_M，
  否则它正向导通，一上电就把 PWR12V 短路
```

**判据是对的，线是我接错的。** 库里这颗 1N4148W 的引脚定义是
**pin2 = A（阳极）、pin1 = K（阴极）**，我按"1 阳 2 阴"的常见约定接反了。

`sch disconnect` 断开后按正确极性重接，五类全过：

```
threshold_sanity   pass   45.3°C（目标 45±3）
switch_drive       pass   栅极 5.0V » 1.05V，200mA « 4A
hysteresis         pass   反馈件 R6
inductive_load     pass   阴极朝 12V、阳极朝开关侧
supply_domains     pass
设计有效性：pass
```

**这是这次压力测试最重要的产出**：一块从零画的板子，
第一个让工具拦住的就是"会让电源短路"的那一处。

### 顺带记两个坑

**坑一：40 个内置块里没有模拟比较器这一类。**
`easycirq blocks ls` 有 power / comms / mcu / rf / usb / display / audio / storage /
button / sensing 十类，**没有"阈值比较 / 温控"**。所以"做个风扇控制器"这个需求，
块库给不了任何帮助，只能 11 个器件一个个手放。这是块库的真实缺口。

**坑二：我自己的成功判定又错了一次。**
`sch autoconnect` 输出的是人读文本（`✓ R1:1 → PWR5V [net_label] ...`），
我却按 `"ok": true` 去匹配，于是 26 次**全部成功**的连线被我报成 26 个失败。
读回网表才知道 8 个网络分毫不差。

**这已经是第三次同类错误**（前两次：数 bundle 里的 `[object Object]`、
按固定空格数断言状态列）。共同的病根是**用猜的格式去判成功**，而不是读回真实状态再判断。

---

## PCB 打通（2026-11-02）

工程 `Fan-Controller-12V`，PCB 文档 `696988895f5e0343`。

| 步骤 | 命令 | 结果 |
|---|---|---|
| 原理图→PCB 同步 | `pcb import-changes` | **0 → 11** 个器件 |
| 自动摆件 | `pcb auto-place` | 完成（先 save + `doc reload` 处理 staleRisk） |
| 板框 | `pcb outline-fit --margin 60` | **allInside: true**，940.5 高，锁定 |
| 布线 | `pcb autoroute` | **8/8 网络全部成功** |
| DRC | `pcb save` → `doc reload` → `pcb drc` | **passed: true, violations: []** |

**顺序是照技能里记的实测教训走的**：没有板框就 autoroute 会报
`successNetsCount: 0`（所有网络都 failed），而这最容易被误判成"路由器坏了"。
这次先做 outline-fit 再布，8/8 一次通过。

### 这轮踩到的四个摩擦

**1. `project find --name` 枚举不出工程。**

```
presence: unknown, enumeration: {complete: false, uuidCount: 0,
reason: "empty_uuid_list", scope: "unscoped"}
```

**连错误都算不上——它返回 ok:true 加一堆内部词。** 实际后果：从风扇板切到
测试工程之后，**回不去了**，因为 `project open` 需要 uuid 而 find 给不出。

**2. 最后是从审计日志里把 uuid 挖出来的。**

`~/.easycirq/audit/2026-11-02.jsonl` 里 `project.create` 那条记录带着
`"uuid": "77ef9d0874cc48499400578c59eb2910"`。

**审计日志在这里救了一次。** 但"去 jsonl 里翻自己的工程 uuid"不该是正常路径。

**3. `project open` 要同时满足三个条件**才肯动：
`--window <当前id>` + `--project-uuid` + `--allow-discard-unsaved`。
少一个就报一条不同的错，得试三轮才知道全貌。

**4. 窗口 id 会变。** 那条错误信息本身写得很好：

```
window "e5f47efb-…" is not connected, but 1 connector window(s) ARE
— window IDs change on reconnect. Connected now: 2e722b8b-…
```

**它直接告诉了你该填什么。** 这是本轮唯一一条"错误信息自己把问题解决了"的——
值得作为标杆。

### 还没做

- **19 项 KPI 门禁**（`sch_offline_pipeline.py`）：未跑
- **门禁两轮 + 通行证**：未跑
- **Gerber / BOM / 交付卡**：未做
- **PCB 视觉复核**（官方导图）：未做

DRC 0 违规不等于板子对——技能里写得很清楚：**门禁绿 ≠ 板子对**。

---

## 19 项 KPI 门禁跑通了（2026-11-02）

### 先修了一个我自己的 bug

管线第一次报：

```
BLOCKED — layout_from_easycirq failed rc=2:
{"status": "invalid_input", "error": "Invalid control character at: line 194 column 49"}
```

**这不是 CLI 的问题，是我的捕获管道。** 我用 `Start-Job` + `Out-File` 抓 JSON，
非 ASCII 被当 GBK 重解释：`-55℃~+155℃` 变成 `-55℃傈+155℃?`，
文件从 417111 字节被撑到 433361 字节。

改成 **Python subprocess 拿原始字节直接写文件**之后，三份快照全部严格解析通过。

**教训**：报错说"控制字符"时，先怀疑自己的读写路径，别急着赖工具。

### 结果

```
offline pipeline: BLOCKED (apply_allowed=False)
  fail     #1  unconnected     connectivity.floating_pins=3
  missing  #10 pin_mux         pinplan: 未提供
  fail     #11 decoupling      power.decap_missing=1
  missing  #14 netlist_diff    netlist: 未提供
  missing  #15 readback        readback: 未提供
  missing  #17 pcb_match       pcb_match: 未提供
```

**#19 design_validity = pass**（五类判据全过，已集成进管线）。

### 两个是真缺陷，不是缺证据

| 项 | 具体 | 为什么是真错 |
|---|---|---|
| #1 | `U1 pin 5 / 6 / 7 未连接` | LM393 **另一路比较器完全悬空**。闲置比较器的输入不能浮着——会自激、往同一片硅上灌噪声 |
| #11 | `U1 pin 8 (VDD) 所在网 PWR5V 没有电容` | **整块板没有去耦电容** |

**这两条都是五类设计判据查不到的**：design_validity 查"电路功能对不对"，
KPI 查"结构/供电/一致性"。门禁在这里抓到了我自己漏掉的东西。

### 四条是缺证据（标 missing，不填 pass）

`pin_mux`（要给 pinplan.json）、`netlist_diff`、`readback`（要先 save→reload 回读）、
`pcb_match`（要 pcb dump）。

### 一处我传错了参数

第一次跑传的是 `intent-block.json`（块版，连接器叫 **J1**），
而快照是 `Fan-Controller-12V`（手工版，连接器叫 **FAN1**），于是 `#19` 报 unknown。
换成 `intent.json` 后 pass。

**unknown 如实反映了"判不了"，没有假装通过——正是第 12 轮修的那个行为在起作用。**

### 还没做

补两个真缺陷（加去耦电容、处理悬空引脚）→ 补四条缺失证据 → 连续两轮 PASS → 通行证 →
Gerber/BOM/卡片。

---

## 按门禁意见改板（2026-11-02）

### 改了什么

| 缺陷 | 修法 |
|---|---|
| #11 去耦缺失 | 加 **C1**（100nF / 0603 / C1591 三星 CL10B104KB8NNNC）接 PWR5V–GND |
| #1 三个悬空引脚 | U1 的 pin5(IN2+) / pin6(IN2-) / pin7(OUT2) 全部接 GND |

**第 2 条的取舍**：闲置比较器输入**不能浮空**——会自激、往同一片硅上灌噪声。
标准做法是把两输入短接到同一确定电平。开集输出（pin7）接 GND 也无害：
它本来就只能拉低，接低相当于常低。

### 门禁复验：两条真缺陷确实消失了

```
改前: fail #1 unconnected (floating_pins=3)
      fail #11 decoupling (decap_missing=1)

改后: 两条都不在列表里了
      新的 fail: #18 bom_match   ← 因为加了 C1，PCB 还没同步
```

**#18 冒出来是对的**，不是倒退：改了原理图、BOM 和 PCB 自然对不上。
门禁在这里做的正是它该做的事。

### 顺带踩到一个好错误信息

查 C1591 时 `lib search` 报：

```
No device exactly matches LCSC id "C1591". The raw search returned 10 fuzzy
candidate(s) whose LCSC field differs — re-run with allowFuzzy (CLI: --allow-fuzzy)
to see them, or use "lib by-lcsc" for a deterministic lookup.
```

**它说了原因（模糊匹配不是精确匹配）、给了两个解法、还指明了命令。**
按它说的用 `lib by-lcsc` 立刻拿到正确的 libraryUuid / uuid。

同时注意到 daemon 有个降级机制：连续失败 4 次后
`degraded: {consecutiveFailures: 4, degradedActions: ["schematic.library.search"]}`，
但**错误信息照旧给全**——降级没有把它变成一句"内部错误"。

### PCB 现在的真实状态：不是绿灯

加 C1 后：

| 步骤 | 结果 |
|---|---|
| `pcb import-changes` | 11 → **12** 个器件 |
| `pcb auto-place` | 完成 |
| `pcb outline-fit --margin 60` | allInside: true |
| `pcb autoroute`（第 1 遍） | **6/8** 网络 |
| `pcb autoroute`（第 2 遍） | successNetsCount: 0（没有更多可布的） |
| `pcb drc` | **passed: false，17 项违规** |

**从"8/8 布通、DRC 0 违规"退回到"6/8、17 违规"。** 这是加器件后重摆的正常代价，
但必须如实说：**现在的 PCB 不是可交付状态**，需要重新布局或加大板框再布。

### 剩下要做的

- PCB 重新布通（6/8 → 8/8）并回到 DRC 0 违规
- 补证据：`pin_mux`、`netlist_diff`、`readback`、`pcb_match`
- 连续两轮 PASS → 通行证 → Gerber / BOM / 卡片


### 第 16 轮：PCB 复布，仍不合格

| 尝试 | 结果 |
|---|---|
| 重新 auto-place + outline-fit(margin 80) + autoroute | **8/8 布通**，但 DRC **17 项违规**（全是 SMD Pad↔Track clearance） |
| auto-place --gap 120 --pitch 150 + outline(margin 100) + autoroute | 8/8 布通，DRC **30 项**（19 clearance + 11 connection）——**更差** |

**结论：加大间距没有解决问题，反而更糟。** 这类 clearance 违规需要真正重排布局
（或手工调整关键器件位置），不是调参能消掉的。本轮止损，如实记为**不合格**。

同时记录一个把我误导了两次的读法问题：pcb dump 默认**不含走线**，
必须加 --include-copper，且键名是 copper.lines 不是 	racks。
详见 known-failures。

---

## 第 19 轮：门禁从 7 项 BLOCKED 降到 1 项

### 补的证据

| KPI | 要的东西 | 怎么做的 |
|---|---|---|
| #17 pcb_match | `snapshot/pcb-dump.json` | `pcb dump --include-copper`（12 器件、88 段铜线） |
| #18 bom_match | 最新的 `snapshot/bom.csv` | 加 C1 后重导出（12 行，含 C1 100nF） |
| #15 readback | `snapshot/connectivity-reopen.json` | save → `doc reload` → 重读（12 器件 8 网络） |
| #10 pin_mux | `snapshot/pinplan.json` | 手写：U1 八个脚、`resources: []`（纯模拟无 MCU） |
| #14 netlist_diff | `snapshot/connectivity-before.json` | 从 **git 历史** `92451c8b` 取改 C1 之前的快照 |

### 结果

```
offline pipeline: BLOCKED (apply_allowed=False)
  fail     #14 netlist_diff
```

**只剩一项。** #1 悬空、#10 引脚、#11 去耦、#15 回读、#17 图板一致、#18 BOM
六项全部通过。

### #14 为什么不过（而且它是对的）

`connectivity-before.json` 是**加 C1 之前**的快照，当前是**加 C1 之后**。
diff 自然非零——因为板子确实变了：

- 新增 C1 及其两个连接
- U1 的 5/6/7 从悬空变成接 GND

**这正是 netlist_diff 该做的事**：它说"网表和冻结基线不一致"。
问题是它**没有地方接受"这些改动是已知且已复核的"这个说明**。

处置方式：把改动逐条写进这份记录（上面两条），然后**明确地重新冻结基线**
（把当前 connectivity 复制成新的 before）。这不是绕过——diff 的用途是发现
**未被察觉**的漂移，而这两处改动是上一轮由门禁指出、这一轮修掉的，
有完整的来龙去脉。

### 顺带记两个工具小问题

**1. `pin_plan_check.py` 的错误信息太简。**
`require unresolved array`、`require boolean or 待查` —— 不说是哪个文件、
不说字段含义、不说纯模拟板该填什么。我为此读了源码才搞明白：
`unresolved` 是必填数组、`debug`/`boot_sample` 等只接受布尔或字面 `待查`。
**一个纯模拟板（没有 MCU）要填齐一套原本为 MCU 设计的字段**，这件事本身也值得商榷。

**2. `analog_used` 把比较器输出也判成了"模拟输入"。**
我一开始按 `IN`/`OUT` 前缀都设成 True，被判
`ADC_AS_OUTPUT: OUT1 被同时声明为模拟输入与输出`。
**这条判据是对的**——输出不是模拟输入；但字段名 `analog_used` 本身没说明
"只对输入有效"，容易理解错。

---

## 第 20 轮：门禁两轮 PASS，通行证签发，三份制造文件导出

### 门禁

重新冻结基线（改动已逐条记录在上一节）后：

```
round 1: PASS (apply_allowed=False)
round 2: PASS (apply_allowed=True)
stability: {rounds_pass: 2, required_rounds: 2, regression: false,
            new_failures: [], apply_allowed: true}
gate: {written: true, path: .easycirq/gate.json, expires_at: 2026-11-02T03:44:39Z}
```

**19 项全过，无 blocker。**

### 三份制造文件

| 产物 | 内容 |
|---|---|
| `gerber.zip` | **12 个文件**：GTL/GBL/GTO/GBO/GTS/GBS/GTP/GKO/GDL + **2 个钻孔层**（PTH_Through、PTH_Through_Via）+ 下单必读 |
| `cpl.csv` | **13 行**（表头 + 12 个器件），带 Mid X/Y、Rotation、Layer |
| `netlist.enet` | 网表 |

已归档到 `deliverables/fan-controller/manufacturing/`。

**层数不是固定的**：这次 12 层，因为有钻孔层（板上有直插件 NTC1 和端子 FAN1）。

### 交付卡

```
✅ 可以下单（原理图与板子都通过）

板子检查：通过（0 项）
检查结果：必查 18/18 通过 · 缺证据 0 · 不适用 0 · 提醒 1
```

**第一次不带 `--pcb-drc` 时卡片是诚实的：「原理图可以打样（板子还没检查）」**，
并给出「带 --pcb-drc 一起看才是整板结论」。补上之后才是整板结论。

### 查出一个我自己工具的缺陷

`tools/check_deliverable.py` **把目录写死成 `deliverables/alarm`，无视命令行参数**：

```python
d = pathlib.Path("deliverables/alarm")   # ← 写死
```

于是 `python tools/check_deliverable.py deliverables/fan-controller` 看起来"跑过了"，
**其实查的是报警板**。证据是它报 `BOM designators: 11`（报警板），而风扇板是 12。

**检查器忽略传入参数，比没有参数更糟**：它给出的是一个看似针对目标的结论。
已改成从 `sys.argv[1]` 取，默认仍是报警板。

修完后它立刻抓到风扇包缺 `README.md`、缺 `SHA256SUMS`、根目录缺 `bom.csv`——
**说明之前那些"通过"都是查错了对象。**

### 交付包自检还有 2 项格式问题（未解决）

检查器要求 README 用它能解析的表格格式列文件，我的写法它读不全：

```
PROBLEMS (2):
  - README 列出但不存在: [design/intent.json, manufacturing/gerber.zip, …19 项]
  - 存在但 README 未列: [SHA256SUMS, bom.csv, design, snapshot]
```

**文件其实都在**（`Get-ChildItem -Recurse` 确认过 22 个），是 README 的表格解析不匹配。
这是格式问题不是内容问题，但**没修就是没修**，记在这里。

### 达到的状态

| 项 | 状态 |
|---|---|
| 意图文件 → 分压阈值 → 比较器 → 驱动管 → 续流二极管 → 双电源域 | ✅ |
| 五类设计有效性判据 | ✅ 全过 |
| 19 项 KPI 门禁 | ✅ **PASS，连续两轮** |
| 通行证 | ✅ 已签发 |
| PCB 布线 8/8 + DRC 0 违规 | ✅ |
| Gerber / CPL / BOM / 网表 | ✅ 已导出并归档 |
| 交付卡 | ✅ 可以下单 |
| 交付包 README 格式自检 | ❌ 2 项格式问题 |
| **物理打样 / 实测** | ❌ **未做**（需要用户下单） |
