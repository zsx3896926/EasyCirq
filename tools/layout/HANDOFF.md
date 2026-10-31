# 交接文档：RetroCam-02 离线布局布线（王牌 layout 方向）

更新：本会话结束时的真实状态。**只写本会话实测过的数字，未验证的标注"未验证"。**

---

## 1. 一句话状态

离线工具链已能完成"布局优化 → 协商布线 → 质量度量 → 离线门禁"的闭环，
**走线间距与拥塞已压到 0**；剩余缺口是 **5 条未布通腿 / 8 张未连通网 / 总线等长未达标**。
门禁 **FAIL**，未上真机板（机制：离线全绿才允许上机）。

```
路线: pcb dump → tools/layout/ec_layout.py place → route → check
```

---

## 2. 代码与命令

```
hds-verifier/tools/layout/
  ec_layout.py          主流程 place / route / report / check
  run_best.py           用 segment_check 复现"最佳布线"配置（CLI 没暴露该开关）
  sweep_placement.py    place→route→5 指标 的权重扫描（一次跑多组，可复现）
  check_bus_order.py    引脚序相关性 ρ + MCU 朝向建议
  BUNDLE-DESIGN.md      等长 bundle 的 7 次尝试与几何证据
  README.md             KPI 定义 / 实测权衡表 / 已否决方案
  HANDOFF.md            本文件
  gradient.py           硬/软间距梯度升级实验
  debug_*.py            冲突单元级诊断

hds-verifier/tests/
  test_ec_layout.py     11 条（指标语义、合法化、门禁、新增的 face/btn 项）
  test_bus_order.py     3 条（ρ 一致性、镜像、秩相关）
```

```bash
python tools/layout/ec_layout.py place  dump.json --iters 40000 --out placed.json
python tools/layout/ec_layout.py route  dump.json --place placed.json --iters 20 --layers 4 --out plan.json
python tools/layout/ec_layout.py check  dump.json --place placed.json --plan plan.json   # exit 1 = 禁止上机
python tools/layout/run_best.py dump.json --place placed.json --out plan.json --kpi kpi.json   # 带 segment_check
python tools/layout/sweep_placement.py dump2.json --configs baseline,face,btn --out sweep.json
```

`place` 的三个可调开关（默认值见文件头常量）：
`--bus-w`（引脚序 ρ 项，默认 600 **在本板实测有害**）、`--face-w`（焊盘场朝向，默认 1500）、
`--btn-w`（按键腿长，**默认 0 = opt-in**；实测 800 才有收益，但见 §10.4 的代价）。

`route()` 的可选开关：
`segment_check=True`（线段级间距硬约束，**关键**）、`priority_nets`、`escape_nets`、`hard_nets`、`spacing_hard`。
`ec_layout.WIDTH_OVERRIDE = {net: mil}` 可做单网线宽覆盖。

---

## 3. 当前实测前沿（RetroCam-02，4 层，GND 按铺铜建模）

**基线可复现性（已纠正）**：旧文档的"未布通 5 / 未连通 8"来自磁盘上的
`ec-placed.json`，**该文件用任何已知参数都复现不出来**（历史纯 HPWL 代码 + dump2 得
42202，而文件对应 43301）。那份基线**作废**。以下为 `dump2 + 当前代码` 的可复现基线，
同参数重跑得同一组数字。

| 配置（权重 bus/face/btn） | HPWL | 走线间距 | 拥塞 | 未布通 | 未连通 | vias |
|---|---|---|---|---|---|---|
| **baseline 0/0/0（可复现基线）** | 42202 | **0** | **0** | **9** | 11 | 66 |
| btn400 (0/0/400) | 46626 | 2 | 0 | 10 | 11 | 54 |
| **btn (0/0/800)** | 50103 | 0 | 1 | **6** | 11 | 69 |
| btn1200 (0/0/1200) | 48747 | 2 | 2 | 8 | 12 | 65 |
| btn2000 (0/0/2000) | 46447 | 0 | 0 | 9 | 7 | 58 |
| both (0/1500/800) | 50103 | 0 | 1 | 6 | 11 | 69 |

**结论一：btn 权重不单调。** 未布通随权重 0→400→800→1200→2000 为
**9 → 10 → 6 → 8 → 9**，噪声型曲线，不是趋势。btn=800 的 6 条腿可能是局部幸运点，
不能当作"找到规律"。它同时把 HPWL 抬高 19%（42202 → 50103）并引入 1 个拥塞单元，
**不值得作为默认配置**。

**结论二：`face_w` 项目前无效。** `both (0/1500/800)` 与 `btn (0/0/800)` 的 HPWL、
未布通、死腿清单完全一致（50103 / 6 / 同样 6 条腿）。说明 `escape_face_penalty`
在 cost 里要么是常数、要么梯度为零 —— 需要单独验证后才有意义。

其它已测指标：

```
45° 占比 ≈ 0.40；总线等长误差 CAM 741–1011 / LCD 130–305 / SD 73–308 mil（未达标）
测试 11/11 通过
```

死腿（baseline 9 条）集中在 GND（5 条）、CAM_D4 / CAM_PWDN、CC1 ——
GND 在真实板上是铺铜，因此 GND 相关死腿应视为"建模缺口"，而不是布线失败。

## 4. 三个必须避免回归的 bug

1. **`Board.nets` 是加载时快照**（存的是 pad 拷贝）。`apply_placement` 必须重建它，
   否则布线器用**布局前坐标**路由——这个 bug 曾污染全部指标约 10 轮，修好后拥塞从 9 掉到 1。
2. **占用表必须按层记键** `(x, y, layer)`。按 `(x, y)` 会把不同层的交叉误判为冲突，
   bundle 类函数都踩过（已修 9 处）。
3. **`check` 不得覆写它没测的 KPI**。曾把 `congestion_cells` 强制写 0 后放行。

---

## 5. 已否决的方案（都有实测数字，不要重试）

| 方案 | 结果 |
|---|---|
| 线宽降到 7/6 mil | 间距违规不变（26）→ 与线宽无关 |
| 焊盘禁布区 +trace/2 | 26→32，未连通 5→8 |
| GND 独占一层 | 26→32，只省 9 个过孔 |
| 外部 rip-up + 单发重布 | **919** 条间距（破坏协商解） |
| 间距光环 2 格 | 39 条，vias 105 |
| 失败网优先布线 | 未布通仍 7，vias 76→64 |
| 失败网 5 mil 窄线 | 未布通 5→**6**（窄线让邻网更难通过） |
| 焊盘扇出过孔带 | 5→6 |
| **布局目标函数加总线序 ρ 项** | 严格间距下未布通 5→**10**（失败网不是总线网，打错靶） |
| **btn 权重 400 / 1200 / 2000**（本轮） | 未布通 10 / 8 / 9，只有 800 是 6 → 权重非单调，别线性外推 |
| **face 项单独上线**（本轮） | 未布通 9→9，只把 HPWL 降到 40217：朝向对布线无用 |
| 等长 bundle 7 种几何 | 落地 0–3/8，见 `BUNDLE-DESIGN.md` |

---

## 6. 下一步（按优先级，理由已写清）

### 6.1 布局：把"引脚侧朝向 + 就近"写进目标函数（最优先）

失败网是 `+3V3/GND/BTN_*`，全部卡在 U5 焊盘列 → 这是**布局问题**。

1. **引脚侧朝向惩罚**：算 U5 的焊盘重心相对器件中心的方向向量，与"外设方向"
   （J3/J4/J5 的重心）做夹角，夹角大则惩罚。`pad_escape_dirs()` 已有方向基础。
2. **按键就近惩罚**：BTN_* 对应的 SW2–SW5 到 U5 相应引脚的直线距离。
3. 验收：`place` 后 HPWL 不明显回退（≤ 46000），且 `check_bus_order` 的 ρ 不恶化；
   再用 `segment_check` 布线，目标 **unrouted 0**。

### 6.2 等长：通道分配器（第二优先）

按 `BUNDLE-DESIGN.md`：行→列束需要"扇出 + 通道带 + 扇入"三段式，
且通道带必须完全避开两端焊盘区。关键容量不等式（已算）：
CAM 源行与目标列仅 97 mil，8 条线要 105 mil → **单层装不下，必须分两层（4+4）**。
前提：先把 6.1 做完，否则没有可用走廊。

### 6.3 剩余 3 条 GND↔FB 间距

需按**铺铜规则**（8–10 mil pour clearance）复核，而不是走线规则。

---

## 7. 环境与工程事实

* 工程 `RetroCam-02` uuid `8d467d4cd8564a1eae4f8ae8f588a4d0`；PCB `1fbba3874712dcca`。
* 布线全程**离线**，用的是 `pcb dump --include-copper` 快照：
  `retrocam-02/pcb/dump2.json`（布局后）、`dump1.json`（导入初态）。
* 布局结果：`retrocam-02/pcb/offline/ec-placed.json`（旧，对应最佳布线）
  与 `ec-placed-routable.json`（含 ρ 项，**布线更差，勿用**）。
* **安装版 CLI（EasyCirq 1.1.0）缺少多边形焊盘修复**：任何需要 `pcb route solve`
  或落线的操作必须用源码构建的二进制（本会话用的是 `%TEMP%\ec-pcb.exe`，由
  `go build -o %TEMP%\ec-pcb.exe ./cmd/easycirq` 生成）。
* PCB 板框：70×50 mm 圆角（`pcb outline-round --rect 0,0,2756,1968 --radius 140`）。
* 当前真机 PCB 是半成品（早前铺设过部分走线），**未做任何上机写入验证**，以离线结果为准。

---

## 8. 工作纪律（本会话踩过的坑）

1. **禁止用 `python -c "..."` 在 PowerShell 里改这个仓库的 Python 文件**：
   引号/反斜杠会被吞，命令失败但看起来像执行了，本会话至少 6 次静默失效，
   其中 1 次把"未生效的改动"当成实验结果。用编辑器改，再跑测试。
2. **每次必须同时记录 5 个指标**：clearance / congestion / unrouted / unconnected / vias。
   单指标结论在本会话误导过多次（例如"间距变好"其实换来"未布通翻倍"）。
3. `pytest tests/test_ec_layout.py tests/test_bus_order.py` 必须保持 11/11 绿。
4. **任何改动先跑基线复现**：同参数重跑应得到同一组数字；不同说明状态被污染。

---

## 9. 交付判定（给下一会话的验收口径）

离线门禁全绿 = 下列同时成立：

```
unrouted_legs == 0
congestion_cells == 0
nets_unconnected == 0
clearance_violations == 0     （GND 按铺铜规则复核后计）
bus_length_spread 各组 < 50 mil
```

当前差距：`unrouted 5`、`unconnected 8`、`等长未达标`、`3 条 GND↔FB 待复核`。
达成后才允许把布局与走线写入 EasyEDA 并回读 DRC 验证。

> **本轮更正（见 §10、§11）**：上述 `unrouted 5 / unconnected 8 / vias 83` 与 `clearance 0` 用任何
> 已知参数组合都复现不出来。当前**可复现**基线是 dump2 + 纯 HPWL 的
> `9 / 11 / 66`（clearance 0、congestion 0）。以 §10 的数字为准。
> 另：`clearance_violations` 自 §11.1 起**计入过孔**，同一计划的真实值是 179 而非 4。

---

## 10. 本轮接手实测（2026-10-31）

### 10.1 先纠正基线：§3 的"最佳"状态不可复现

| 尝试 | 结果 |
|---|---|
| dump1 + `ec-placed.json` + segment_check | 4 / 0 / **7** / 7 / 81 |
| 历史纯 HPWL 代码（4ba10d8）+ dump1 + 40000 iters | HPWL 56934，与 `ec-placed.json` 不同 |
| 同上 + dump2 | HPWL **42202**，仍 ≠ 43301 |
| 当前代码 `--bus-w 0 --face-w 0 --btn-w 0` | HPWL 56934（dump1）/ 42202（dump2） |

`ec-placed.json` 的 HPWL 43301 没有被任何已知参数集复现；`bus_order_penalty`
是 `2439366` 才进目标函数的，而 `ec-placed.json` 是**纯 HPWL 时代**的产物。
**结论：仓库里没有能重放"5 条腿"那次运行的命令。** 这是交接文档最大的缺口，
建议以后每次实验都把 `place`/`route` 的完整 argv 落在 `offline/` 里。

**本轮采用的基线（确定性，可重复）**：`dump2.json` + 纯 HPWL 布局（42202 mil），
`segment_check` 布线 → `clearance 0 / congestion 0 / unrouted 9 / unconnected 11 / vias 66`。

### 10.2 新增的两个目标项（§6.1 落地）

`escape_face_penalty()`：MCU 焊盘质心方向 vs 外设焊盘质心方向的夹角，返回 `1-cosθ ∈ [0,2]`。
`button_leg_penalty()`：每条 `BTN_*` 腿的直线长度（按 1000 mil 归一）。
两项与 `bus_order_penalty` 一起进 `placement_cost()`，权重分别由 `--face-w / --btn-w / --bus-w` 控制。

### 10.3 扫描结果（同一快照、同一布线参数、五项指标同表）

| 配置 | HPWL | 重叠 | 间距 | 拥塞 | **未布通** | 未连通 | vias |
|---|---|---|---|---|---|---|---|
| baseline 纯 HPWL（bus0/face0/btn0） | 42202 | 0 | 0 | 0 | **9** | 11 | 66 |
| face1500 | **40217** | 0 | 0 | 0 | **9** | 10 | 64 |
| btn400 | 46626 | 0 | 2 | 0 | 10 | 11 | 54 |
| **btn800（本轮最好）** | 50103 | 0 | 0 | **1** | **6** | 11 | 69 |
| btn1200 | 48747 | 0 | 2 | 2 | 8 | 12 | 65 |
| btn2000 | 46447 | 0 | 0 | 0 | 9 | 7 | 58 |
| face3000+btn800 | 50103 | 0 | 0 | 1 | 6 | 11 | 69 |
| rhoplus（bus600+face1500+btn800） | 50103 | 0 | 0 | 1 | 6 | 11 | 69 |

* `btn800` 起效：**unrouted 9 → 6**，但换来 **−19% HPWL**（42202→50103）和 **拥塞 1**，门禁仍 FAIL。
* 权重**非单调**：400→10、800→6、1200→8、2000→9。别指望调权重线性改善。
* `face` 项单独用**不减少未布通**（9→9），只把 HPWL 降到 40217；`face3000+btn800` 与 `btn800`
  逐位相同 → 退火收敛到同一盆地，face 项被 btn 项淹没。
* 重复运行同一配置得到逐位相同的数字（确定性已验证）。

### 10.4 本轮得到的判断

1. **"失败腿是布局问题"这一假设只部分成立**：按键就近项确实把 9 压到 6，但**到不了 0**，
   而且代价是拥塞和 HPWL。布局目标函数不是唯一的杠杆。
2. 死腿集合在不同配置间**大幅漂移**，只有 `CAM_D4(J3.12↔U5.12)`、`CAM_PWDN(J3.17↔U5.11)`
   在多组里反复出现 → 这是 **J3 走廊**的结构问题（正对应 §6.2 的通道分配器），不是按键。
3. `GND` 占死腿的一半以上（U1.2↔U1.15、SW3.3↔J3.2、J3.2↔J3.19 反复出现）→
   应走 §6.3 的**铺铜规则**把 GND 移出走线器，而不是继续在布局里找。
4. 新项**不要**默认开满：`--btn-w 800` 有收益但违反两项验收（HPWL、拥塞），
   建议下一步与铺铜/GND 方案一起联合评估。

---

## 11. 第二轮：平面模型 + 过孔盲区（2026-10-31）

### 11.1 最重要的发现：过孔间距从来没被检查过

`clearance_violations()` 原来只比较**走线对走线**。补上过孔（贯穿孔在四层都是铜）后，
同一份计划（`ec-placed.json` + segment_check）从"间距 4"变成：

```
track-track 4 | via-track 103 | via-pad 72 | 合计 179
```

也就是说 §3/§9 里"间距 0"的验收口径**不完整**：它只覆盖走线，过孔在四层上都贴着别人
的铜放，就是短路。修正后的 `clearance_violations()` 计入：过孔对其他网走线（任意层）、
过孔对其他网焊盘（`VIA_RADIUS = 10 mil`）。

### 11.2 GND 平面能力（已实现、已测试、本板实测为负结果）

`route(..., plane_nets={"GND"}, plane_layer=N)`，CLI：`--plane-net GND --plane-layer 4`：

* 平面网不再走 MST 腿，改为**每个焊盘一个接入过孔 + 一格短桩**（不做 via-in-pad：
  那需要树脂塞孔 POFV，是另一种工艺，不能默默假设）；
* 平面层被独占，其它网不允许在该层走线；
* `connectivity_from_plan` 把所有平面过孔并成同一块铜；**没有接入过孔的焊盘仍算未连通**；
* 42 个 GND 焊盘 → 42 vias + 42 stubs，取代 41 条 MST 腿（约 165 段走线）。

| 模式 | 间距 | 拥塞 | 未布通 | 未连通 | vias | 走线段 | 线长 |
|---|---|---|---|---|---|---|---|
| 无平面 | 179 | 0 | **7** | 7 | 81 | 680 | 51521 |
| 平面在第 4 层 | 140 | 2 | 9 | 14 | 95 | 515 | 37393 |
| 平面在第 2 层 | 76 | 1 | **27** | 24 | 60 | 367 | 25876 |

**负结果**：4 层板拿掉一整层信号容量（−72 段）比省下 41 条 GND 腿更贵。线长与间距变好，
未布通反而变差。结论："整层平面"不适合这块板；正确做法是 §6.3 的**区域铺铜**
（GND 按 pour clearance 避让，不独占整层），或改 6 层。

### 11.3 过孔硬否决（负结果，已降级为 opt-in）

`via_conflicts()` 在路径接受阶段否决"过孔压到别人铜上"的路径，实测：

| 判据 | 未布通 | 间距 |
|---|---|---|
| 不检查（现状，`via_check=False`） | **7** | 179 |
| 过孔间距否决（26 mil） | 33 | 26 |
| 过孔重叠否决（14.5 mil，只判真重叠） | 25 | 34 |

密集板上几乎没有"四层同时空出 26 mil 圆盘"的点，逐条否决会把整条长路径打死。
**结论：过孔要用"站点预留 / 代价"而不是"事后否决"**。

### 11.4 下一轮建议（按性价比排序）

1. **过孔站点预留**：布线时先占位（via site reservation），后来者绕行；或在 layer
   transition 处按代价加价，而不是否决整条路径。
2. **区域铺铜**（§6.3）：GND 用 pour + 8–10 mil pour clearance 避让，而非整层平面。
3. 等长通道分配器（§6.2）：CAM 97 mil 容量缺口，必须分两层 4+4。

### 11.5 `check` 的一个 KPI 诚实性修复

`check` 从磁盘读 plan，而 plan 里没有路由器的 `paths`，于是 `unrouted_legs` 一直是
**0**——它测不了这一项却报了通过值（正是 §4 第 3 条 bug 的同族）。现在这类"测不了"
的指标一律输出 `null` 并让门禁 FAIL：

```
"unrouted_legs": null,  "pass": false
```

`report(failures=None)` 表示未测；`gate()` 把 `null` 当失败，不当通过。

