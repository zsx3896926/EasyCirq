# 板1 相位与证据（上机实测）

> 工程 `d3e50b4c213d409d8f641a6f484213e9`，页面 P1 `aaaa1a7b39b0d18a`。
> 板子指纹：`ef6bb794aca6d344`（这是"上机"的证据——离线推演没有指纹）

---

## 2026-11-05 第一次上机

### 环境

| 项 | 值 |
|---|---|
| daemon | 1.4.0 → 修卡点#1 后升到 1.4.2（触发一次自动重启）|
| connector | v1.0.22，1 窗口 |
| 页面可见性 | `hidden`（标签页在后台；写入与读取照常）|

### 落器件

批量放置 49 个位号（脚本报"成功 22、失败 27"，但**读回是 50 个**——见 `friction.md` #2）：

```
页面上器件数（componentType=part，排除图框）: 50
重复位号: 无
空位号:   无
```

位号清单：

```
C1 C2 C3 C4 C5 C6 C7 C8 C9 CAD1 CAD2 CB1 CD1 CD2 CRST CSEQ1 CSEQ2
D1 D2 D3 D4 D_TVS1 F1 J1 L1 L2 Q_REV
RAD1 RAD2 RAD3 RAD4 RCC1 RCC2 RFB1 RFB2 RFB3 RFB4 RL1 RL2 RL3 RL4
RRST RSEQ1 RSEQ2 R_IN1
U1 U2 U3 U4 U5
```

**难度门槛①：器件数 ≥40 → 达标（50）**

### 门（S5）第一次真跑

第一次跑的时候 daemon 正在因版本升级重启，连接器掉线，于是：

```
sch gate: BLOCKED
sch gate: BLOCKED — 检查器没能跑完，原理图未被完整判定（不是板子的问题）:
  no connected window for project "…"
```

**这条是设计在起作用**：它明确说"不是板子的问题"，而不是把"没能检查"报成"板子有问题"。

连接器重连（约 8 秒）后再跑，得到**真实判定**：

```
sch gate: FAIL
  FAIL  layout-lint   26 overlap, 27 pin-coincidence, 11 tight,
                      0 off-grid, 0 out-of-sheet, 0 no-bbox,
                      0 unchecked-pin, 0 unproven-pin, 0 nets-unproven,
                      0 invalid-geometry
  FAIL  clusters      50 个虚拟组: 26 重叠 / 0 出图纸 / 0 过近
  FAIL  check         120 finding(s): 27 error/fatal, 93 warn/info
                      （27 个 zero-length-wire）
  PASS  bridge-check  0 bridge(short), 0 orphan-stub, 0 orphan-flag,
                      0 orphan-tree (0 wire tree(s))
  PASS  drc           0 fatal, 0 error, 5 warn, 0 info; native verdict PASS
```

### 这些失败说明了什么

- **26 overlap / 27 pin-coincidence**：器件按网格批量摆放，间距不够，引脚撞在一起
- **27 zero-length-wire**：引脚重合导致生成了零长度导线
- 这些是**真实的几何问题**，不是工具误报——门在做它该做的事

### 难度门槛现状

| 维度 | 门槛 | 现状 | 达标 |
|---|---|---|---|
| 电源轨 | ≥4 路 | 电路规划 4 路，器件已落 | 器件层面 ✅ / 网络未连 ❌ |
| 器件数 | ≥40 | **50** | ✅ |
| 网络数 | ≥80 | **0**（还没连线）| ❌ |
| 混合信号 | 模拟前端 + 数字 | 采样分压 + MCU 已落 | 器件层面 ✅ |
| 保护 | 反接/过流/TVS | TVS + 保险丝 + 反接 MOSFET 已落 | 器件 ✅ / 网络未连 |

### 下一步

1. 拉开器件间距（解决 26 overlap / 27 pin-coincidence）
2. 连线：电源树 + 采样 + MCU 最小系统（目标 ≥80 网络）
3. 再跑门，直到 `PASS` 或给出**有归因的 FAIL**
4. 跑 `card` 拿交付判词

**当前判词：还不能下单**（S5 FAIL，且无交付卡）。这是合格的过程状态。


---

## 2026-11-05 第二次上机（同日推进到 S6）

### 做了什么

| 步骤 | 结果 |
|---|---|
| 用 `--verify` 修好放置的假失败 | ✅ 1.4.3 |
| 重排器件：8×7 → 9×6 网格 | 26 overlap → **1 overlap** |
| 挪开 RRST（与 MCU 重叠） | **0 overlap** |
| `--include-wires` 读回 27 条零长度导线 → `prim-delete` | 28 error → **0 error** |

### 最终判定

```
sch gate: PASS
  PASS  layout-lint   0 overlap, 0 pin-coincidence, 0 tight, 0 off-grid,
                      0 out-of-sheet, 0 no-bbox, 0 unchecked-pin,
                      0 unproven-pin, 0 nets-unproven, 0 invalid-geometry
  PASS  clusters      51 个虚拟组: 0 重叠 / 0 出图纸 / 0 过近
  PASS  check         65 finding(s): 0 error/fatal, 65 warn/info
  PASS  bridge-check  0 bridge(short), 0 orphan-stub, 0 orphan-flag, 0 orphan-tree
  PASS  drc           0 fatal, 0 error, 7 warn; native verdict PASS
```

相位机：`S5: pass` → 一路推进到 **S6**。

### 关键发现：`sch gate` PASS ≠ 可交付

这块板**一条线都没连**（0 网络），但门五道全 PASS —— 因为
layout-lint / check / bridge-check / drc 检查的是**排版与图面质量**，不是电气连接。

拦住它的是 DELIVER 的**前置**：

```
board_facts → parts = 51, floatingPinCount = 196
```

**196 个悬空引脚**会被 PINS 拦下（即使交付卡已就绪）。实测 `phase advance`：

```
refused: the delivery card is pending — a board that has not been measured
         cannot be delivered    阻塞：DELIVER 前置 CARD = pending
```

**这条设计是对的，值得记下来**：门管图面，前置管电气，两层各管一件事。

### 难度门槛

| 维度 | 门槛 | 现状 | 达标 |
|---|---|---|---|
| 器件数 | ≥40 | **51** | ✅ |
| 电源轨 | ≥4 路 | 器件齐 | 器件层 ✅ |
| 保护 | 反接/过流/TVS | 器件齐 | 器件层 ✅ |
| **网络数** | ≥80 | **0** | ❌ **下一步** |

### 下一步

连线：电源树 + 采样分压 + MCU 最小系统 → ≥80 网络，
并把 `floatingPinCount` 降到 0（或对刻意不接的引脚标 no-connect）。


---

## 2026-11-05 第三次上机：换料 + 第一次连线

### 换掉 3 个错料（卡点 #6 的后续）

| 位号 | 换前 | 换后 | 引脚 |
|---|---|---|---|
| D_TVS1 | 8 位 I2C 扩展器 | **SMBJ18CA**（TVS） | 2（A/K）|
| U3 | 16 脚无关器件 | **1117-1.8**（LDO 1.8V） | 3（GND/VOUT/VIN）|
| U4 | 150V MOSFET | **A1117-3.3**（LDO 3.3V） | 3（ADJ/GND/VOUT/VIN）|

器件数仍是 **51**，总引脚 196 → **167**（错料少了 19 脚）。

### 第一次连线（用错了工具）

用 `sch connect` 逐个引脚连，115 条成功、8 条失败。

读回真实电气状态：

```
器件数 51   已连引脚 110   悬空 57   导线 111   有名网络 35
+5V 一个网络 37 个引脚   ← 我只挂了 9 个
```

**原因**：相邻引脚的引线与网络标号在物理上重叠，不同网络被并成了一个。
`sch connect` 用的是它自己的默认偏移，不看周围几何。

### 门的判定（它抓住了）

```
sch gate: FAIL
  FAIL  layout-lint   1 overlap
  FAIL  clusters      51 个虚拟组: 37 重叠 / 2 出图纸
  FAIL  check         124 finding(s): 2 error/fatal (out-of-sheet×2)
  FAIL  bridge-check  6 bridge(真短路), 109 wire tree(s)
  PASS  drc           0 fatal, 0 error, 20 warn
```

**`bridge-check` 报 6 处真短路** —— 这正是门存在的意义：脚本可以把网络并错，
门不会替它遮掩。

### 正确工具

`sch autoconnect`：按几何给「方向 × 偏移」候选打分、幂等、支持 `--spec` 批量、
`--strict` 拒绝有碰撞的候选。板1 的连线要用它重做。

### 门槛现状

| 维度 | 门槛 | 实测 | 达标 |
|---|---|---|---|
| 器件数 | ≥40 | 51 | ✅ |
| 电源轨 | ≥4 路 | 网络里可见 VBUS/VIN_12V/+5V/+3V3/+1V8/+4V0 | ✅ |
| 保护 | 反接/过流/TVS | TVS + 保险丝 + 反接 MOS 已连 | ✅ |
| **网络数** | ≥80 | **35**（且含短路，不可用） | ❌ 且门槛偏高（见 friction #8）|
| 电气正确 | — | **6 处短路** | ❌ |

**判词：还不能下单。** 这是合格的过程状态——门把问题指得很清楚。


---

## 2026-11-05 第四次上机：改用 autoconnect，短路 6 → 2

### 做了什么

| 步骤 | 结果 |
|---|---|
| 写 `connect-spec.json`（40 个网络 / 118 条连接） | ✅ |
| `sch autoconnect --spec --replace --strict` 一次跑 | ❌ 连接器 DEGRADED（卡点 #9）|
| 改分块（12 条/块，块间停 6 秒，跑 6 轮） | 部分成功，但**震荡**（卡点 #10）|
| 停手，让门判 | 见下 |

### 门的判定

```
sch gate: FAIL
  FAIL  layout-lint   1 overlap
  FAIL  clusters      51 个虚拟组: 21 重叠 / 0 出图纸
  PASS  check         88 finding(s): 0 error/fatal, 88 warn/info
  FAIL  bridge-check  2 bridge(short), 90 wire tree(s)
  PASS  drc           0 fatal, 0 error, 20 warn
```

**对比上一轮**：短路 6 → 2，`check` 的 2 个 error 清零。方向是对的。

### 本轮最重要的一条经验

**降级状态下不要反复 `--replace`。** 它是"删旧+重连"，在假失败环境里每一轮都在
拆上一轮的成果 —— 已连引脚数在 76 和 100 之间来回跳。**修复动作本身在破坏。**

正确姿势：要么先一次性清干净再从零连（不带 `--replace`），要么停下等连接器恢复。

### 现状

| 维度 | 门槛 | 实测 | |
|---|---|---|---|
| 器件数 | ≥40 | 51 | ✅ |
| 已连引脚 | — | 91 / 167 | 进行中 |
| 网络数 | ≥80 | 37 | ❌（且门槛偏高，见 #8）|
| 短路 | 0 | **2** | ❌ |

**判词：还不能下单。**


---

## 2026-11-05 第五次上机：拆-重连路径把引脚数拉回 99

### 这一轮的关键判断

上一轮用 `--replace` 批量修冲突，结果**删了 24 个旧标号却只重连上一部分**，
已连引脚从 99 掉到 76 —— #10 的守卫只挡"一开始就降级"，挡不住"跑到一半降级"（#12）。

改用 **disconnect → 全新 autoconnect**：

| 步骤 | 结果 |
|---|---|
| 只补缺失（不带 `--replace`） | 62 已正确 → 99 已连 |
| `--replace` 修 16 个冲突 | **失败**，掉到 76（卡点 #12）|
| disconnect + 全新连 | 拆完待补 42 → 重新连上，**回到 99** |

### 最终判定

```
sch gate: FAIL
  FAIL  layout-lint   1 overlap
  FAIL  clusters      51 个虚拟组: 27 重叠
  PASS  check         87 finding(s): 0 error/fatal   ← 保持干净
  FAIL  bridge-check  2 bridge(short), 98 wire tree(s)
  PASS  drc           0 fatal, 0 error, 20 warn
已连引脚 99 / 167      网络 37
```

### 顺带再次验证了 #4

本轮又撞上 daemon 升级重启，门打出：

```
连接器刚掉线（多半是 daemon 因版本升级重启），已等待重连后重跑。
```

然后给出真实判定而不是 BLOCKED。**#4 在自然场景下第二次验证。**

### 现状

| 维度 | 门槛 | 实测 | |
|---|---|---|---|
| 器件数 | ≥40 | 51 | ✅ |
| 电源轨 | ≥4 | 6 个电源网 | ✅ |
| 保护 | 反接/过流/TVS | 已连 | ✅ |
| 已连引脚 | — | 99 / 167 | 进行中 |
| 网络数 | ≥80 | 37 | ❌ |
| 短路 | 0 | **2** | ❌ |

**判词：还不能下单。**


---

## 2026-11-05 第六次上机：#12 修掉

### 修了什么

`--replace` 的降级守卫原来只在**开跑前**探一次。现在批量循环里每次写入后都看一次
响应，发现降级且正在 `--replace` 就**中止整批**，并把原因写进报告：

```json
{ "ok": false, "aborted": true, "abortReason": "连接器已降级…反复跑会来回震荡…" }
```

为什么必须中止而不是放慢：`--replace` 是「删旧标号 + 重连」，中途降级时
删除可能落上而重连没落上 —— 继续跑就是**在拆自己的成果**（实测 99 → 76）。

### 测试

5 条（降级识别 / 放慢 / 健康放行 / 降级时拒绝 `--replace` / **中止必须带理由**）。

### 板1 状态（本轮未再动板子）

```
已连引脚 99 / 167     网络 37
sch gate: FAIL
  FAIL  layout-lint   1 overlap
  FAIL  clusters      27 重叠
  PASS  check         0 error/fatal
  FAIL  bridge-check  2 bridge(short)
  PASS  drc           0 fatal, 0 error
```

**判词：还不能下单。** 门把问题指得很具体：2 处短路 + 27 处重叠。


---

## 2026-11-05 第七次上机：重排把重叠从 27 压到 3

### 做了什么

| 步骤 | 结果 |
|---|---|
| 全拆（disconnect 逐脚） | 97 / 99 |
| 重排到 7×8 网格（间距 145×95） | **51 / 51 成功** |
| 重连（autoconnect spec） | 92 / 167，34 网络 |
| 门判 | **重叠 27 → 3，短路 2 → 1** |

### 一次没跑完的补救

发现 `y=735` 探出图纸可用区，尝试第二轮重排（8×7，145×85），
但连接器中途降级，**只移动了 25/51**（卡点 #13）。

按纪律**停止改动**，读取真值并记录——没有假装重排成功。

### 最终真值

```
器件 51   已连引脚 85 / 167   网络 34   导线 88
layout-lint    fail   1 overlap, 1 out-of-sheet
clusters       fail   3 重叠 / 1 出图纸
check          fail   1 error/fatal (out-of-sheet)
bridge-check   fail   1 bridge(short)
drc            PASS
verdict        fail
```

### 进步曲线（同一块板，七次上机）

| 指标 | 第 1 次 | 现在 |
|---|---|---|
| 器件 | 0 → 50 | 51 |
| `check` error | 27 | **1** |
| 短路（bridge） | 6 | **1** |
| 组间重叠 | 37 | **3** |
| 已连引脚 | 0 | 85 / 167 |

**判词：还不能下单。** 差 3 处重叠、1 处出图纸、1 处短路 —— 都是**有具体对象的**问题，
不是"整体感觉不行"。


---

## 2026-11-05 第八次上机：被 `sch modify` 的阻断性故障挡住

### 本轮的正面收获：找到了正确的批量工具

`easycirq apply`（playbook + journal + `--resume`）本来就是为这种场景设计的：

```
第 1 次 apply：playbook stopped at step move-01-C2 (1 ok, 0 skipped)
第 2 次 --resume：(0 ok, 1 skipped)   ← 跳过已完成、重试失败项
```

提示还说：`⚠ 变更类步骤失败/超时:变更可能已生效——先读回校验,再决定恢复步骤`

**所以 #13 要更正**：不是产品缺事务语义，是我手搓了无日志的循环。

### 阻断：#14

跑 playbook 时第 2 步失败，手动重试 5 个不同器件**全部失败**：

```
EDA_CALL_FAILED: Failed to modify component.
detail: Cannot destructure property 'cmdKey' of 'i' as it is undefined.
```

对照：同一时刻 `sch list` 正常（读到 51 个器件），`sch gate` 正常给判定。
**只有 `sch modify` 挂。**

`web reload` 尝试恢复失败（30 秒内未等到新的连接器注册）。

### 板1 现状（未再改动）

```
器件 51   已连引脚 85 / 167   网络 34
layout-lint  fail  1 overlap, 1 out-of-sheet
clusters     fail  3 重叠 / 1 出图纸
check        fail  1 error/fatal
bridge-check fail  1 bridge(short)
drc          PASS
verdict      fail
```

**判词：还不能下单。** 而且在 #14 修好之前，**这条线推不动**。


---

## 2026-11-05 第九次上机：绕道失败，整板被删后重建

### 起因

#14（`sch modify` 对所有器件报 `Cannot destructure property 'cmdKey'`）挡住了重排。
想用"删掉重放"绕开——`place` 是好的。

### 发生了什么

| 步骤 | 结果 |
|---|---|
| 删除全部 51 个器件 | ok |
| `lib by-lcsc` 批量解析身份 | **只解析出 5/15**（批量路径静默少返回）|
| 首次重放 | **只放回 6 个** ← 板子一度只剩 6 个 |
| 改用 `pin-inventory.json` 逐个解析 + place | 42/45 |
| 补 3 个（C2 重试、L1/L2 换候选电感） | 51 个位号齐全 |
| 删掉多出来的 C10 | ok |

### 重建后的判定（比重建前更差）

```
sch gate: FAIL
  FAIL  layout-lint   6 overlap, 2 pin-coincidence, 1 out-of-sheet
  FAIL  clusters      6 重叠 / 1 出图纸
  FAIL  check         4 error/fatal (zero-length-wire×3, out-of-sheet×1)
  FAIL  bridge-check  1 bridge(short)
  FAIL  drc           27 fatal  ← 重建前是 0
  verdict             fail
```

**重建让局面变差了**：重叠 3→6、check error 1→4、**drc 0→27 fatal**。
原因：重新放置的器件挤在网格上，旧的引线与标号没有对应清理。

### 我记下来的教训

1. **不要为了绕过一个阻断缺陷做整板破坏性操作** —— 代价比等待更大
2. **破坏性操作前先验证可恢复性**：先跑一遍"每个位号能否 `by-lcsc` 解析"，
   就会立刻发现只有 5/15 能，从而放弃这条路
3. 这条判断应当变成**产品能力**（删除前校验可恢复性 / 提供快照回滚）

**判词：还不能下单。**


---

## 2026-11-05 第十次上机：DRC 27 fatal → 0

### 根因

上一轮重建后 `drc` 报 **27 条 MISSFOOTPRINT**。查下去发现：

| 命令 | 同一个 C 号返回的封装 |
|---|---|
| `lib search --query C31847` | `footprintName = "C1206"` ✅ |
| `lib by-lcsc --lcsc C31847` | `footprintName = None` ❌ |

**`by-lcsc` 自称返回"可直接 place 的身份"，但那个身份缺封装绑定。**
用它 place 出来的器件没有封装 → 造不出来 → 直到 DRC 才暴露（#17）。

### 修法与验证

1. CLI 侧补齐 `footprintName`（缺的用 `search` 按同一 C 号查一次）
2. 决定性验证：同一个 C1，`by-lcsc` 身份放 → 无封装；`search` 身份放 → **有封装**
3. 26 个裸器件删掉、按 `search` 身份重放 → **51/51 全部有封装**

### 结果

```
sch gate: FAIL
  FAIL  layout-lint   6 overlap, 2 pin-coincidence, 1 tight, 1 out-of-sheet
  FAIL  clusters      6 重叠 / 1 出图纸
  FAIL  check         4 error/fatal (zero-length-wire×3, out-of-sheet×1)
  FAIL  bridge-check  1 bridge(short)
  PASS  drc           0 fatal, 0 error, 10 warn   ← 27 fatal 清到 0
```

### 顺带：产品的一个好设计

`rebind-footprint` 对这 27 个器件**在变更之前就拒绝了**，并说清原因：

```
Rebind was refused before mutation because the device association
could not be rolled back exactly.
```

对比 #14 的 `Cannot destructure property 'cmdKey'` —— **同一个产品里，一个错误信息好到可以当范本，另一个坏到毫无用处。**

**判词：还不能下单。** 剩 6 处重叠、1 处出图纸、3 条零长导线、1 处短路。


---

## 2026-11-05 第十一次上机：四道门从 FAIL 到 PASS

### 做了什么

统一重排到 **7 列 × 152×90**（X0=95, Y0=80），走"删 + 按 `search` 身份重放"：

| 步骤 | 结果 |
|---|---|
| 删全部 51 个 | ok |
| 按 search 身份重放 | **51 / 51**，全部带封装 |
| 再删 6 条零长度导线 | ok |

### 门的结果（同一块板，前后对比）

| 门 | 重排前 | 现在 |
|---|---|---|
| `layout-lint` 重叠 | 6 | **3** |
| `layout-lint` 出图纸 | 1 | **0** ✅ |
| `check` error/fatal | 4 | **0** ✅ PASS |
| `bridge-check` | 1 短路 | **0** ✅ PASS |
| `drc` fatal | 27 | **0** ✅ PASS |
| 器件有封装 | 24/51 | **51/51** ✅ |

### 剩下的 3 处重叠，成因是同一个

**U5（STM32F030C8T6）的符号高约 115 单位，而网格行距只有 90。**

试了 5 个位置（y = 620 / 530 / 440 / 350，以及 (551,260)），**每个位置都是 3 个问题**——
因为它无论放在哪一列，都会压住同列上下的邻居。

这不是"位置没选对"，是**它需要一个两行高的专属槽位**：把同列邻居挪走。
而挪邻居正是 `sch modify` 该干的活 —— **#14 挂着，改不了位置**。

### 学生意：为什么这一轮才做到

前面几轮一直在"修一件、坏一件"：删了重放丢封装（#17）、改位置报 `cmdKey`（#14）。
这一轮之所以能一次到位，是因为**先把 #17 修好了**（search 身份带封装），
才敢做整板重放。

**修产品的顺序，决定了后面能动多快。**

**判词：还不能下单。** 剩 3 处重叠，全部由 U5 的符号高度导致。


---

## 2026-11-05 第十二次上机：**`sch gate: PASS`** —— 板1 第一次五门全绿

### 怎么做到的

不再挪 U5（它放哪都压邻居），改成**清空它周围**：

| 挪走 | 新位置 | 为什么 |
|---|---|---|
| U4（LDO） | (95, 80) | 顶左空格 |
| RFB3 | (399, 710) | 右下空格 |
| RSEQ1 | (703, 710) | 右下空格 |

三个都与 U5 重叠，挪走之后就没人压它了。

### 结果

```
sch gate: PASS
  PASS  layout-lint   0 overlap, 0 pin-coincidence, 0 tight, 38 off-grid,
                      0 out-of-sheet, 0 no-bbox, 0 unchecked-pin,
                      0 unproven-pin, 0 nets-unproven, 0 invalid-geometry
  PASS  clusters      51 个虚拟组: 0 重叠 / 0 出图纸 / 0 过近
  PASS  check         66 finding(s): 0 error/fatal, 66 warn/info
  PASS  bridge-check  0 bridge(short), 0 orphan-stub, 0 orphan-flag, 0 orphan-tree
  PASS  drc           0 fatal, 0 error, 45 warn; native verdict PASS
```

**这是板1 第一次五道门全部 PASS。**

### 紧接着上一行的真相

```
board_facts → parts = 53, floatingPinCount = 167
```

**167 个引脚全部悬空** —— 排版干净，但**一条线都没连**。

`sch gate: PASS` 只管图面质量（排版/桥接/DRC），**不管电气连通**。
拦住交付的是 DELIVER 的前置：

```
refused: the delivery card is pending — a board that has not been measured
         cannot be delivered    阻塞：DELIVER 前置 CARD = pending
```

**两层各管一件事，这次在同一屏里同时出现了。**

### 相位

```
S0 ✓ → S1 ✓ → S2 ✓ → S3 ✓ → S4 ✓ → S5 ✓ pass → S6 ✓
DELIVER: 被 CARD 挡住
```

### 随后连线（S4 补做）

用 `connect-spec.json` 跑 `autoconnect`：

```
成功 59 / 失败 59    已连引脚 24 / 167    网络 14
```

门的变化：

```
layout-lint   PASS（0 重叠）
clusters      FAIL（1 处重叠 ← 新加的标号）
check         PASS（0 error）
bridge-check  PASS（0 短路）  ← #9/#12 的修复在起作用
drc           PASS（0 fatal）
```

**只差 1 处重叠。** 而上一轮连完线是 6 处短路 + 37 处重叠。

**判词：还不能下单。** 差 1 处重叠 + 143 个悬空引脚。


---

## 2026-11-05 第十三次上机：门 PASS 且带线；连线卡在"引脚朝向"

### 做到的事

把与 U5 重叠的 RFB4 挪到远端 (1007,710) 后：

```
sch gate: PASS
  PASS  layout-lint   0 overlap, 0 pin-coincidence, 0 out-of-sheet
  PASS  clusters      0 重叠 / 0 出图纸
  PASS  check         0 error/fatal
  PASS  bridge-check  0 bridge(short), 59 wire tree(s)   ← 带线
  PASS  drc           0 fatal, 0 error
```

**这是第一次"门 PASS 且板上已经有线"**（26 引脚 / 16 网络 / 59 wire tree）。

### 然后连线就走不动了

补连 4 轮，88 条里只有 3 条能连上：

```
第 1 轮：成功 3 / 失败 84
第 2–4 轮：成功 0 / 失败 85
```

### 为什么 —— 产品在这里是对的

失败原因不是"工具坏了"，是**几何硬拒绝**：

```
schematic geometry guard failed (preflight) — Rejected before write:
  fix source pin exit/wire geometry and replan.
  pin-exit-direction (J1:B4A9): pin B4A9 outward rotation 180° requires …

no safe candidate: every direction/offset is unsafe
  （引出方向不沿引脚朝外方向（hard reject））
  — resolve the layout (move the part, clear the wire, or free the title-block corner) and retry
```

**`autoconnect` 不肯画一根从引脚"朝里"出来的线。** 这是对的 —— 那种线在原理图上
既难看又容易误读。

### 但这就把板1 顶到了 #14 上

要让引脚朝外，得**改器件的旋转角**。改旋转 = `sch modify --rotation` = **#14（挂了六轮）**。

所以现在的链条是：

```
想连线 → 引脚朝向不对 → 需要改旋转 → 需要 sch modify → #14 全挂 → 卡住
```

**#14 不再只是"不方便"，它是板1 连线的唯一硬阻断。**

### 现状

```
51 器件（全部有封装）   26 / 167 引脚已连   16 网络   59 wire tree
sch gate: PASS（五门全绿）
相位: S6
交付: 被 CARD=pending 挡住
判词: 还不能下单
```

**难度门槛**：器件 51 ✅ / 电源轨 6 个电源网 ✅ / 保护已连 ✅ / **网络 16（门槛 80）❌**


---

## 2026-11-05 第十四次上机：连线卡死的真因找到了 —— 排版没给标号留位置

### 先更正 #14

做了 A/B 实验：新放一个器件立刻 `modify` → **ok**；改一个重放的旧器件 → **ok**。

**`sch modify` 自己好了。** 所以 #14 是 EDA 会话状态的**瞬态失效**，不是命令坏了。
真正的缺陷是那句 `Cannot destructure property 'cmdKey'` —— 六轮工作被一个"重试就过去"
的状态挡住，而错误信息既不提示重试也不提示重载。

### 然后连线仍然 85/85 失败，但理由变了

| 场景 | 拒绝理由 |
|---|---|
| 网格上（152×90 密排） | `no safe candidate: every direction/offset is unsafe（引出方向不沿引脚朝外方向，hard reject）` |
| 挪到空旷角落 | `label leaves the usable sheet area（hard reject）` |

再加上旋转时的：

```
Pin (246.99999999999994, 370) sits OFF the 5-unit schematic grid
```

**三条约束同时成立才能连一根线**：引脚朝外、标号落在图纸内、坐标在 5 单位网格上。

### 真因（#21）

**排版只算器件 bbox，不算标号 bbox。** 于是 51 个器件排得整整齐齐、门也 PASS，
但**器件之间没有给 120 个标号留位置** —— 一连线就无处放标号。

这比 #14 更根本：#14 是偶发的，#21 每次都会撞上。

### 板1 现状（本轮结束时）

```
51 器件（全部有封装）   26 / 167 引脚已连   16 网络   59 wire tree
sch gate: PASS（五门全绿）
判词: 还不能下单
网络数 16 / 门槛 80
```

**下一步不是"继续试连线"，是让排版给标号留位置。**


---

## 2026-11-05 第十五次上机：发现产品本来就有"块级复用"

### 起因

上一轮判断"排版没给标号留位置"（#21）。这一轮先算了一笔账：
51 个器件要 200×120 的间距需要约 120 万平方单位，而 A4 只有约 96 万 —— **放不下**。
所以加间距不是解。

### 然后读 `sch wire` 的帮助，看到一句话

> 常规布线请走：`easycirq sch autoconnect` — 电源/地/netport 短桩；**`easycirq sch block-apply` — 整块落地（自带 netlist 对账门）**

于是去看了 block 库：

```
39 个电路块，多数 ready / verified
块级 dry-run 实测（block.led_indicator_gpio）：
  device preflight: 2/2 device(s) resolved
  REF   ROLE  PART                AT        LAYOUT
  LED1  LED   led.yellow_0805     820,300   template r180
  R1    R     res.1k_0402         700,300   template
  NET         KIND       MEMBERS
  LED_CTRL    net_label  R1:1 (port CTRL)
  LED1_N2     net_label  R1:2 LED1:+
  GND         gnd        LED1:- (port GND)
```

**它自带布线计划，根本不会撞上 #21。**

### 这对板1 意味着什么

板1 用十几轮手搓了"块级工具本来能直接做"的东西。它不废——
它证明了零件级链路能走通，也挖出了 #16 / #17 / #21 这些真缺陷。
但要在合理轮次内走到 ≥80 网络，正确做法是**用块重建**。

### 现状（未再改动板子）

```
51 器件（全部有封装）  26 / 167 引脚  16 网络  59 wire tree
sch gate: PASS   ·   判词：还不能下单
```


---

## 2026-11-05 第十六次上机：块级重建（板1b），一轮超过手搓十五轮

### 新建工程

| 项 | 值 |
|---|---|
| 工程名 | 板1b-块级电源板 |
| projectUuid | `c5443fece5a548ba9e41b35951ee124c` |
| 页面 | P1 `c4958b937ebb4a9a` |

### 落的块（按顺序）

| 块 | `--at` | 结果 |
|---|---|---|
| `block.led_indicator_gpio` | 200,200 | `applied` |
| `block.ams1117_ldo_3v3` | 200,420 | `applied-mismatch` |
| `block.pmos_highside_softstart` | 200,650 | `applied` |
| `block.ina226_power_monitor` | 760,300 | `applied-mismatch` |
| `block.esp32s3_pico_native_usb` | 660,620 | `applied-mismatch` |

### 累计效果（5 个块，5 次调用）

```
器件 31（全部有封装 31/31）
已连引脚 62 / 131
网络 22
off-grid 0
```

前 3 块时 `sch gate: PASS`（含 `bridge-check` 23 个 wire tree、`drc` PASS）。

### 为什么掉成 FAIL

第 4、5 块放得太靠右下，块的整体包络超出图纸可用区：

```
layout-lint  FAIL  5 out-of-sheet
clusters     FAIL  3 重叠 / 5 出图纸
check        FAIL  5 error/fatal
```

**`block-apply` 尊重显式 `--at`（对），但不预检"这块落下去会不会出图纸"（缺）。** 记为 #23。

### 与手搓路线的对照

| | 板1（手搓 15 轮） | 板1b（块级 1 轮） |
|---|---|---|
| 器件 | 51 | 31 |
| 有封装 | 第 16 轮才到 51/51 | **开始就是 31/31** |
| 已连引脚 | 26 / 167 | **62 / 131** |
| 网络 | 16 | **22** |
| off-grid | 38 警告 | **0** |

**判词：还不能下单。** 差 5 处出图纸 + 3 处重叠（都是坐标选得不好，不是块的问题）。


---

## 2026-11-05 第十七次上机：块级布局一次成型；大块需要独占页但没落成

### 一次成型的那次

清空重放，块按"大块占角、小块排边"排开：

| 块 | `--at` | 结果 | 累计 |
|---|---|---|---|
| `esp32s3_pico_native_usb` | 120,430 | **拒绝**（见下） | — |
| `ina226_power_monitor` | 640,120 | applied-mismatch | 6 器件 / 7 网络 |
| `ams1117_ldo_3v3` | 640,330 | 拒绝 | 6 器件 |
| `pmos_highside_softstart` | 900,330 | applied-mismatch | 12 器件 / 11 网络 |
| `led_indicator_gpio` | 640,560 | applied | **14 器件 / 30 引脚 / 13 网络** |

**出图纸 0、重叠 0、off-grid 0。** 块级路线一次成型的干净布局。

### 大块：被正确拒绝，而且拒绝得像范本

ESP32-S3 块被拒，理由是实测 496×716，图签把可用区切成 L 形，宽和高两条都不满足
（差 40 / 差 101），并明确说"别重试同一条命令"，给出两条路：**让它独占一页**。

### 按它说的做，但没落成

- `sch page-new --schematic 82d87183fc1a7c91` → 新页 `6430d668a985dae9` ✅
- 在新页 `block-apply --doc 6430d668a985dae9 --at 150,150`
- 结果：**警告"这张页上已有的器件把空位占满了"** —— 可这是一张空页（#24）
- 而且这次把块量成 **660×660**，上一次是 **496×716** —— 同一个块两次尺寸不同

### 现状

```
13 器件 / 28 引脚已连 / 11 网络 / 1 出图纸 / 2 重叠
sch gate: FAIL
判词：还不能下单
```

**判词：还不能下单。** 但这一轮证明了块级布局能一次排出干净图面（14 器件 13 网络 0 问题）。


---

## 2026-11-05 第十八次上机：**板1b 拿到第一张真正的交付卡**

### 换掉了装不下的块

`block.esp32s3_pico_native_usb` 在 A4 上放不下（545×716 vs L 形可用区）。
换成 `block.esp32s3_wroom1_module`（ready，模组方案）→ **装得下**：

```
origin: 150,150 → 320,380
  （--at 会让这一块超出图纸可用区 — 出界是硬约束不是偏好，已移到距你指定坐标最近的合法位置）
device preflight: 5/5 device(s) resolved
```

**产品自己把坐标挪到了合法位置**，并且说清了为什么动你的坐标。

### 板1b 两页都干净

| 页 | 器件 | 已连引脚 | 网络 | 门 |
|---|---|---|---|---|
| P1 | 14 | 30 / 38 | 13 | **PASS**（0 重叠 / 0 出图纸 / 0 off-grid / 0 短路 / drc PASS）|
| P2 | 6 | 18 / 51 | 6 | **PASS** |

板级事实：**parts = 30，floatingPinCount = 8**（板1 手搓版是 167）。

### 离线全检 → KPI → 交付卡

```
python easycirq/scripts/sch_offline_pipeline.py --snapshot-dir … --out-dir …
→ kpi-report.json  verdict: BLOCKED
```

```
❌ 还不能打样

必须修的问题：
  · 有引脚或网络没有接上：INA_ALERT、LED_CTRL、SCL、SDA
    → 把它连到该连的地方，或显式标成不接（NC）
  · 电源脚没有配电容
    → 给电源脚补一颗去耦电容

还没检查的项目（补上资料即可）：
  · 引脚复用冲突 · 元件缺封装/型号/立创编号 · 改动前后连接对不上
  · 保存重开后对不上 · pcb_match · bom_match

检查结果：必查 6/14 通过 · 缺证据 6 · 不适用 4 · 提醒 1
下一步：按下面的建议逐条修，修完重新测量
```

### 这张卡为什么重要

它把三类东西**分开**说了：

| 类别 | 内容 |
|---|---|
| **真缺陷（2 条）** | 4 个网络没接上 · 电源脚没去耦电容 |
| **缺证据（6 条）** | 引脚复用 / 封装型号 / 改动前后 / 重开前后 / pcb / bom —— **未测 ≠ 坏了** |
| **不适用（4 条）** | PCB 侧指标，原理图阶段不产生 |

而且每条都给**下一步动作**。

**这就是"交付保证"这一层的实物**：不是一句"我觉得画完了"，而是一张能拿去
跟客户/主管交代的判词，连"哪几条只是没测"都写清楚了。

### 还差什么

两条真缺陷都是可以修的：
1. **4 个网络没接上**（INA_ALERT / LED_CTRL / SCL / SDA）—— 这些是块的边界端口，
   要用 `--bind` 绑到宿主网络，或显式标 NC
2. **电源脚没去耦电容** —— 需要在电源脚就近补电容

**判词：还不能下单。** 但这是第一次有完整判词链路：快照 → 离线全检 → KPI → 交付卡。


---

## 2026-11-05 第十九次上机：修掉一条真缺陷，换来一条更根本的

### 做了什么

1. **带 `--bind` 重落 P1 的四个块** —— 把块的边界端口钉到明确的全局网名
   （`VIN_5V=+5V`、`3V3=+3V3`、`I2C_SDA=SDA`、`ALERT_N=INA_ALERT` …）
2. **补 VSYS 去耦**：放 `CDEC1`（100nF），两端分别接到 VSYS / GND
3. 想顺手把 `LED_CTRL` / `PWR_EN` 钉到 +3V3

### 成果

| 指标 | 之前 | 现在 |
|---|---|---|
| P1 器件 | 14 | **19** |
| 已连引脚 | 30 / 38 | **42 / 50** |
| 网络 | 13 | 13（`+3V3_SW` 仍是单脚） |
| `sch gate` | PASS | **PASS**（39 wire tree） |
| **去耦缺陷** | 必修 | **已从必修清单消失** ✅ |
| 未接网络 | 4 个具名（INA_ALERT / LED_CTRL / SCL / SDA） | 8 个悬空引脚，但**引擎已不再具名** |

**`SDA` / `SCL` / `INA_ALERT` 已经接上了** —— 因为 INA226 块自带的上拉电阻让它们变成了两脚网。

### 但换来一条更根本的问题

```
power-net: review
  blocking POWER_SPLIT
  电源引脚被分到了 2 个不同网络：+5V(U1.3)、VSYS(U3.8)
```

**这是真的设计问题**：LDO 的 `+5V` 输入**没有来源**。我的块组合里缺一个
**电源入口块**（USB-C 供电），所以电源链是断的：
`? → +5V → LDO → +3V3 → PMOS → +3V3_SW`，最左边那个问号没有东西。

### 另一个事实

`block.esp32s3_wroom1_module` 只暴露 **3V3 / GND / EN / IO0 / U0TXD / U0RXD** 六个端口，
**没有 I2C/GPIO**。所以 `LED_CTRL`、`PWR_EN` 这两个 GPIO 驱动的网
**接不到 MCU** —— 不是接线没做，是这块 MCU 块根本不提供那些脚。

两处尝试都失败，错误信息清楚：

```
pin already connected to net "LED_CTRL", not "+3V3"; pass --replace to delete the old flag+wire
--replace 之后：no safe candidate: stub touches an existing (foreign-net) wire (hard reject)
```

### 当前交付卡

```
❌ 还不能打样
必须修的问题：
  · 有引脚或网络没有接上（→ 连接，或显式标 NC）
  · power_net（→ 按检查结果修正）
还没检查的项目：引脚复用 / 封装型号 / 改动前后 / 重开前后 / pcb_match / bom_match
```

**判词：还不能下单。** 但比上一轮更接近了：去耦那条已经消掉。
剩下的核心是**电源链缺入口**，那是设计层面的决定，不是接线动作。


---

## 2026-11-05 第二十次上机：电源链接上了；然后被 `group-move --ids` 剪断又接回

### 电源链（POWER_SPLIT）修好了

`U3:8` 从 `VSYS` 改挂 `+5V` —— 用**先断后连**的顺序（`--replace` 在密布线下会死锁，见 #29）：

```
ok: true   direction=right  offset=86  score=88.6
power-net: review(blocking POWER_SPLIT)  →  pass
```

**交付卡的必修项从 2 条减到 1 条。**

### 然后我想挪块给标号腾位置，踩了 #30

用 `group-move --ids` 把 INA226 块左移 230 / 下移 120。返回 `ok:false`（假失败），
但关键在这三个字段：

```
"movedFlags": [], "movedLabels": [], "movedWires": []
```

**器件走了，线没走。**

| 指标 | 移动前 | 移动后 | 移回后 |
|---|---|---|---|
| 连接数 | 42 | **31** | **44** |
| 悬空脚 | 8 | **19** | 6 |
| 网络 | 13 | 9 | 13 |

原路移回把电路接回来了，而且比移动前还好一点。

### 顺带看到防御链有效

移回时它自己报 `SCHEMATIC_GEOMETRY_INVALID · wire-through-body (U3)`；
`sch gate` 的 `check` **独立也抓到同一条**。删掉那条穿体导线后 `check` 转 PASS。

### 现状

```
19 器件 / 44 连接 / 13 网络
layout-lint PASS · check PASS · bridge-check PASS · drc PASS
clusters FAIL（1 处重叠：R7 ↔ U3）
判词：还不能下单
```

**判词：还不能下单。** 但电源链这条真缺陷已经修掉，剩下的是 1 处组间重叠。


---

## 2026-11-05 第二十一次上机：卡在"移动"这件事上

### 想做的事

上一轮结束时只剩 **1 处组间重叠（R7 ↔ U3）**。

### 排查过程

1. R7 先在 (560,320)，U3 在 (850,320) —— **相距 290，本体不可能重叠**
2. 查 `clusters` 的组框：**R7 的组框有 192 宽**，而一个 2512 电阻本体只有约 6mm
3. 组框里装的是**留在原地的标号**：`GND(610,340)` `+3V3(610,320)` `VBAT(640,320)`
4. 把 R7 挪到 (300,760) —— 本体彻底离开了，**重叠依然存在**，因为标号没动

### 所以这是 #31

`sch modify` 移器件、**不移标号**。孤立标号留在原处，仍算在 R7 的组里，
于是与 U3 重叠。而 `layout-lint`（看本体）和 `check`（看线）都 PASS，
**只有 `clusters`（按组算）会红** —— 覆盖是完整的，但**红的原因不在被报的那个器件身上**。

### 当前状态

```
19 器件 / 44 连接 / 13 网络
layout-lint PASS · check PASS · bridge-check PASS · drc PASS
clusters FAIL（1 处重叠：R7 的孤立标号 ↔ U3）
sch gate: FAIL      判词：还不能下单
```

### 三次移动、三次补救

| 动作 | 结果 |
|---|---|
| `group-move --ids` 左移 | 连接 42→31（#30） |
| 原路移回 | 31→44，但穿体导线 |
| 删穿体线 | `check` 转 PASS |
| `modify` 挪 R7（两次） | 本体分开了，标号留下（#31） |

**移动类操作是当前最薄弱的一环。** 这一条比"清掉最后一个重叠"更值得修。
