# Derived 案例（D1–D3）派生说明

> 归属：任务 D「从真实回读证据派生案例」。
> 案例数据：`easycirq/assets/pcb-placement-benchmarks/benchmarks.json`（原 12 条不改，追加 3 条 `derived`）。
> 派生脚本：`benchmarks/pcb-placement-benchmark/derive_cases.py`（唯一派生源；SHA-256 由脚本计算，不是手填）。
> 契约：`docs/pcb-placement-training/contract.md` §2 schema、§3 判分语义、§6 证据与边界。
>
> **边界（固定成立）**：只做离线几何/网表代理判分。不是 DRC、不证明可布通、不证明阻抗/热/EMC/制造；所有判分输出固定
> `placement_applied:false`、`routing_verified:false`、`drc:"NOT RUN"`、`eda_calls:0`。本文件不把「案例 verdict」写成「这块板能打样」。

---

## 1. 数据源与 SHA-256

只用 **git 已跟踪** 的回读证据。`provenance.source_sha256` 由
`derive_cases.py` 用 `hashlib.sha256(file.read_bytes())` 现算；其它辅助证据的
SHA-256 也由脚本算出并打印（见 §6），同样不是手填。

| 案例 | 角色 | 文件（相对 worktree 根） | SHA-256 |
|---|---|---|---|
| D1 | 主源：最终 dump | `easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json` | `db7521f2883346f0d70126047927f2cf6a61343374c2e0cb71869649aa3a57fe` |
| D1 | 辅助：tracked 去耦 WARN 实测 | `easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-check-final.json` | `7c5449402562369e075214d4e50c38075f64284fbf65f854c2b2b29ce564c835` |
| D2 | 主源：最终 dump | `easycirq/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json` | `86822978045ce69b84ae39f84fae85bab3862acedfbad543eab93ff7c7e4c1f2` |
| D2 | 辅助：near-pin `max_mil` | `easycirq/cases/photo-led-pcb-2026-10-26/evidence/constraints.json` | `92c06f7718bc769a5e9633983df0b46c43610579d989a9d2c4c6909c9090ecf6` |
| D2 | 辅助：tracked 实测距离 | `easycirq/cases/photo-led-pcb-2026-10-26/evidence/placement-check-final.json` | `1d5ca86e2e68291cd69c8f62d096417e3ec686f9bd0d560fec00a81cfec347e5` |
| D3 | 主源：首版基线 dump | `easycirq/cases/dual-button-led-night-20261027/negative-direct-move/board-baseline.json` | `ef995715dee1030044592f18ba1cf0442d15fd489947a83bed905ca6fa747d00` |
| D3 | 辅助：被拒绝的直接移动 | `easycirq/cases/dual-button-led-night-20261027/negative-direct-move/placement-direct-move.json` | `5d61d459f5024a7032fc739ed72fe595a9bd2d23a3d4477ebba98dd88e389b5b` |
| D3 | 辅助：tracked 拒绝事实 | `easycirq/cases/dual-button-led-night-20261027/negative-direct-move/expected.json` | `ac03f3f1667649d6c94de47393c5f05419802c3eb14d07fb7df6655def52fbf9` |

源文件的工程身份见各 case 的 `README.md`（mcu-i2c-s3、photo-led、dual-button-led）。
脚本只读这些文件；不联网、不调 EDA。

## 2. 单位与坐标换算规则（3 条案例同一套）

### 2.1 长度单位 = mil，`mm = mil × 0.0254`

判定依据（三重交叉验证）：

1. dump 的 `rules` 块字段名自带单位（`clearanceMil`、`viaDrillMil`、`copperToEdgeMil`），说明该回读坐标系以 mil 计。
2. 板框尺寸与 tracked README 对得上：
   - mcu-i2c-s3：dump 多边形包络 `2590 × 1771.7` mil = **65.786 × 45.00118 mm**（README：65.79×45 mm）；
   - photo-led：`3543.3 × 2362.2` mil = **89.99982 × 59.99988 mm**（README：90×60 mm）；
   - dual-button：`1968 × 1378` mil = **49.9872 × 35.0012 mm**（README：约 50×35 mm 的小板）。
3. 器件尺寸常识相符（如 0805 焊盘包络约 4.08×1.96 mm、DIP-8 包络约 402×372 mil）。

换算后所有 mm 值保留 6 位小数（1 nm）；案例 `units.length` 固定 `"mm"`。

### 2.2 器件中心、size、引脚偏移

- **dump 的 `x`/`y` 是 footprint 原点，不是几何中心。** 反例（同一份 tracked 数据内可查）：
  dual-button 的 `J1` 原点 `(288.1885, 687.0315)` mil 与其 bbox 中心
  `(286.220, 698.843)` mil 相差 11.8 mil；`D3` 原点 `x=1195.0898` 而 bbox 中心 `x=1200.0`。
  因此本派生**不**把 `x`/`y` 当中心。
- **中心 := dump 绝对 `bbox` 的中心**；**`size_mm` := bbox 尺寸按 `rot_deg` 反旋转**
  （90/270 时宽高互换）。判定式：`center ± size/2`（90/270 交换宽高）必须逐分量等于 dump bbox。
  脚本对此断言，最大误差 **1e-6 mm**（6 位小数舍入导致）。
- **引脚偏移 := `R(-rot) · (pad_abs − center)`**（mm，未旋转的器件局部坐标），
  正是契约 §3.1 要求的语义。判分器再施加 `R(rot)` 后必须回到 dump 的绝对焊盘坐标；
  脚本断言最大误差 **≤1.4e-14 mm**。
- 旋转：只接受四分之一转。dump 里出现 `-90.00000000000001°`（photo-led J1），
  按 `mod 360` 精确等于 270°，归一到 270；若某器件角度不在 `{0,90,180,270}±1e-6°`
  内则**丢弃、不猜**——本次 3 条案例**没有**因旋转被丢弃的器件。
- 坐标轴：dump 的板框多边形与器件/焊盘在同一坐标系，案例原样沿用（不做 y 镜像）。
  为避开轴向歧义，所有 `board.connectors` 只声明 **left/right** 边（对 y 镜像不变），
  不使用 top/bottom。
- 说明（诚实近似）：契约的 `size_mm` 语义是「器件本体，不含引脚外伸」，而 dump 只提供
  footprint bbox（含焊盘外沿；tracked README 也把同一数值称作「本体」）。
  本派生用 dump bbox 并在案例中 1:1 复现该 bbox；这属于 tracked 数据模型内的近似，
  不是新造的器件尺寸。

### 2.3 用一条案例的实测距离反验证中心/旋转/引脚规则

| 案例 | 派生距离（由绝对焊盘坐标重算） | tracked 实测 | 来源 |
|---|---|---|---|
| D1 | `C1.1 → U1.4 = 316.354 mil = 8.035404 mm` | 316 mil (8.0 mm) | `pcb-check-final.json` decap-too-far |
| D1 | `C3.1 → U1.4 = 212.735 mil = 5.403473 mm` | 213 mil (5.4 mm) | 同上 |
| D1 | `C90.1 → U90.3 = 128.464 mil = 3.262984 mm` | 128 mil (3.3 mm) | 同上 |
| D2 | `C2.1 → U1.8 = 150.000 mil = 3.81 mm` | `distance_mil: 150.0` | `placement-check-final.json` NP-C2-U1 |
| D2 | `C3.2 → U2.3 = 203.100 mil = 5.158740 mm` | `203.1` | NP-C3-U2 |
| D2 | `R4.1 → U1.3 = 254.077 mil = 6.453544 mm` | `254.077` | NP-R4-U1 |
| D2 | `R5.1 → U1.1 = 405.814 mil = 10.307672 mm` | `405.814` | NP-R5-U1 |
| D2 | `C1.1 → U1.8 = 889.737 mil = 22.599326 mm` | `889.737` | NP-C1-U1 |
| D3 | D4 上沿 966.075 mil vs R3 下沿 960.894 mil，重叠高 **5.181 mil = 0.1316 mm** | `raw_overlap_height_mil: 5.181` | `expected.json` |

D1 的 316.354 mil 与 tracked 的「316 mil」按 3 位有效数字对齐；D2 五条完全逐位对上
（说明中心、旋转、焊盘反算与 tracked 的 `pad-centre-euclidean` 口径一致）。

## 3. 保留 / 丢弃对象

| 案例 | 源器件 | 保留 | 丢弃 | 丢弃网 |
|---|---|---|---|---|
| D1 | 23 | **8**：`U1,C1,C2,C3,C4,C6,C90,U90` | 15 个范围外器件；`U2` 另有数据限制（见下） | `I2C_SCL`、`I2C_SDA`（保留集内只剩 1 个脚，零 HPWL） |
| D2 | 19 | **19**（全部） | 无 | 无（12 个网在保留集内完整） |
| D3 | 12 | **12**（全部） | 无 | 无（8 个网完整） |

**丢弃规则与理由（不是为凑 verdict）**

- 只保留与所选检查相关的器件及其电源/地上下文；不开「整板复刻」是因为案例 schema 只判
  一个候选布局，保留子集是对象筛选，不改变保留器件之间的电气事实。
- `U2`（ESP32-S3-WROOM-1）有 **9 个物理 EP 焊盘共用 `padNumber` `"41"`**；案例 schema 要求
  同一器件引脚名唯一，无法在不重命名物理焊盘的前提下表示。本派生选择**丢弃 U2** 并如实记录，
  而不是重命名焊盘（重命名虽不改变 GND 事实，但会让引脚身份与 tracked dump 不再一一对应）。
  后果：`C4`/`C6` 的 139/140 mil 去耦 WARN 的最近 `+3V3` 脚是 `U2.2`，因此这两条不在 D1 判分。
- 保留器件都具备可用焊盘和 net 字段；没有因「缺 pad/net」再丢弃其他器件。
  `U90` 的 EP 焊盘 5 在 dump 里 `net` 为空（该 case README 记录 EP=NC），案例把它保留为
  未连网引脚，没有为它补造网络。
- `nets` 是保留器件上的**诱导子图**：网名、焊盘号、连接关系原样取自 dump 焊盘的 `net` 字段，
  被丢弃器件的引脚不参与 HPWL/congestion；单脚网被丢弃（对 HPWL 无贡献）。
- 电气事实未被改动：没有新增/删除连接、没改网名、没改焊盘号、没有补默认尺寸或默认 placement。

## 4. 三条案例、checks 阈值与依据

| id | domain | expected verdict | expected codes | expected soft_fail |
|---|---|---|---|---|
| `D1-MCU-LDO-DECAP` | mcu | **review** | `distance_far` | `ck-decoup-c1`, `ck-decoup-c3`, `ck-decoup-c90` |
| `D2-PHOTO-LED-SENSE` | analog | **acceptable** | 无 | 无 |
| `D3-DUAL-BTN-D4-MOVE` | multi | **blocking** | `body_overlap` | 无 |

### 4.1 D1-MCU-LDO-DECAP（真实板确有超规距离 → review）

真实板 mcu-i2c-s3 的最终布局中，去耦距离超过 `pcb check` 的 100 mil 规则（原工程把 5 条
`decap-too-far` 作为 WARN 保留并解释，见该 case README §6.4）。本案例保留其中 3 条能在
保留子集内复算的检查：

| check id | pins | `max_mm`（依据） | 派生实测 | tracked | 结果 |
|---|---|---|---|---|---|
| `ck-decoup-c1` | C1.1 ↔ U1.4 | **2.54** = 100 mil（`pcb-check-final.json`: "a decap must hug its IC (≤100mil / 2.54mm)"；PL17） | 8.035404 mm | 316 mil | fail → `distance_far` |
| `ck-decoup-c3` | C3.1 ↔ U1.4 | 2.54（同上） | 5.403473 mm | 213 mil | fail |
| `ck-decoup-c90` | C90.1 ↔ U90.3 | 2.54（同上；PL17） | 3.262984 mm | 128 mil | fail |

- 阈值**直接采用 tracked CLI 规则 100 mil = 2.54 mm**，没有为了 verdict 改阈值；真实距离就是
  实测值（316.354/212.735/128.464 mil），也没有为了凑 `review` 放大距离。
- D1 没有声明的 connector，`connector_edge_tol_mm = 2.0`（契约 §2 示例默认，本案例不使用）。

### 4.2 D2-PHOTO-LED-SENSE（真实板基线 → acceptable）

真实板 photo-led 最终布局在 tracked 的 5 条 near-pin 约束上全部 pass。阈值取
`constraints.json` 的 `max_mil` 精确换算（不另设）：

| check id | pins | `max_mm`（tracked `max_mil`） | 派生实测 | tracked 实测 |
|---|---|---|---|---|
| `ck-c2-u1` | C2.1 ↔ U1.8 | 5.08（200，hard） | 3.81 mm（150.0 mil） | 150.0 |
| `ck-c3-u2` | C3.2 ↔ U2.3 | 6.35（250） | 5.158740 mm（203.1 mil） | 203.1 |
| `ck-r4-u1` | R4.1 ↔ U1.3 | 7.62（300，hard） | 6.453544 mm（254.077 mil） | 254.077 |
| `ck-r5-u1` | R5.1 ↔ U1.1 | 22.86（900） | 10.307672 mm（405.814 mil） | 405.814 |
| `ck-c1-u1` | C1.1 ↔ U1.8 | 30.48（1200） | 22.599326 mm（889.737 mil） | 889.737 |

- 另外声明 `connectors: J1 edge=left`，`connector_edge_tol_mm = 3.81`（tracked `EDGE-J1`
  `max_inset_mil: 150`）；派生实测内缩 87.518 mil = 2.222957 mm ≤ 3.81 mm，pass。
- 19 个器件本体 bbox 两两无相交、全部落在 tracked 圆形板框（184 点多边形）内 → 无硬检查命中；
  5 条软检查全 pass → verdict 如实写 **acceptable**。
- problem/target 明确写成「真实板基线，用于训练『看起来近但不能确认』的区分」：距离合格
  ≠ 铜路径/回路面积/铺铜/DRC 合格（tracked 证据本身标注 `copper_path_verified:false`）。

### 4.3 D3-DUAL-BTN-D4-MOVE（真实被拒绝的直接移动 → blocking）

- 场景：真实板 dual-button-led 首版基线（D3/D4 y=760 mil）上，把 LED2（D4）**直接**
  +78.74 mil（+2.00 mm）上移，其余 11 个器件不动（`placement-direct-move.json` 与
  `expected.json` 的 `delta_mil` 一致，脚本断言）。
- 几何：D4 bbox 上沿 `966.075` mil 压入 R3 bbox 下沿 `960.894` mil，重叠高 **5.181 mil**；
  案例判分算出重叠面积 **0.484 mm²** > `overlap_tol_mm2 = 0.0` →
  `body_overlap {D4,R3}` → **blocking**。
- 阈值依据：v1 本体重叠容差就是 0；tracked `expected.json` 的 `placement_check` 也给出
  `hard_ok:false / finding:bbox_overlap / objects:[D4,R3] / raw_overlap_height_mil:5.181`。
  没有为凑 blocking 改阈值或坐标。
- 该案例无 `checks`（`checks:[]`），soft_fail 为空；verdict 完全由硬检查决定。
- `connector_edge_tol_mm = 2.0` 占位（未声明 connector，不使用）。
- 局限：tracked 的 10 mil 工艺净空检查（`overlap_height_mil:15.181`、`conflict:R3`）不属于
  v1 判分范围，案例不声称通过。

### 4.4 rubric 的全局代理基线（hpwl / congestion）

tracked 证据没有给本基准集的全局 HPWL/congestion 阈值，所以这两个字段按「本布局实测基线」
取值（HPWL 向上取 0.1 mm、congestion 取实测整数），只作**基线回归界**，不参与本批 3 条案例的
verdict：

| 案例 | 实测 hpwl_mm | `hpwl_max_mm` | 实测 congestion_max | `congestion_max` |
|---|---|---|---|---|
| D1（8 器件诱导网） | 174.90694 | 175.0 | 3 | 3 |
| D2（19 器件完整网） | 474.08084 | 474.1 | 6 | 6 |
| D3（12 器件完整网） | 150.12670 | 150.2 | 3 | 3 |

`overlap_tol_mm2 = 0.0` 取契约 v1 语义；D1/D3 无 connector 声明时 `connector_edge_tol_mm=2.0`
是契约 §2 示例值（未使用）。D2 的 connector 容差见 §4.2。

## 5. 与判分器对账（实际运行结果）

在 worktree 根目录运行（命令与输出摘录）：

```text
$ python easycirq/scripts/pcb_placement_benchmark.py --all
...
D1-MCU-LDO-DECAP  review  OK
D2-PHOTO-LED-SENSE  acceptable  OK
D3-DUAL-BTN-D4-MOVE  blocking  OK
15/15 cases matched expected
=> exit 0

$ python easycirq/scripts/pcb_placement_benchmark.py --list
PCB placement benchmark cases: 15
（新增 3 条 id 见 §4）

$ python easycirq/scripts/pcb_placement_benchmark.py --case D1-MCU-LDO-DECAP   => exit 1 (review)
$ python easycirq/scripts/pcb_placement_benchmark.py --case D2-PHOTO-LED-SENSE => exit 0 (acceptable)
$ python easycirq/scripts/pcb_placement_benchmark.py --case D3-DUAL-BTN-D4-MOVE => exit 2 (blocking)
```

- **先几何、后对账**：`derive_cases.py` 内置了契约 §3 语义的独立复算（硬检查/软检查/全局代理/
  verdict），先由真实几何推出 verdict+codes+soft_fail，再与 `expected` 比对；随后用官方判分器
  复核。三方（tracked 证据实测 / 脚本独立复算 / 官方判分器）一致，才写入 `benchmarks.json`。
- 确定性：`derive_cases.py --print` 连续两次字节一致；判分器 `--all --json --out` 连续两次
  字节一致；`--write` 第二次运行输出「already up to date」。
- `expected.json`（`benchmarks/pcb-placement-benchmark/expected.json`）**本任务未改**，
  由 Lead 按最终 15 条重冻；`run_benchmark.py` 的对账在此之前仍按旧的 12 条 expected 运行。
- `benchmarks.json` 的改动是**纯追加**：`git diff --stat` 显示只有插入（原 12 条字节未变），
  12 条原有案例的 id/内容保持不变。

## 6. 复现

```bash
# 在 worktree 根目录
python benchmarks/pcb-placement-benchmark/derive_cases.py --check   # 校验 benchmarks.json 与源 SHA
python benchmarks/pcb-placement-benchmark/derive_cases.py --print   # 打印含派生案例的完整集合
python benchmarks/pcb-placement-benchmark/derive_cases.py --write    # 幂等重写派生案例（保留原 12 条）
python easycirq/scripts/pcb_placement_benchmark.py --all             # 必须 exit 0（15/15）
```

`--check` 会同时打印每个派生案例的主源 SHA-256 与辅助证据 SHA-256；脚本内所有换算规则、
断言（bbox/pin 复现、tracked delta、expected 对账）都在 §2 有对应说明。

## 7. 诚实局限（必须保留）

1. **只覆盖真实板的一个子集/一组选定检查，不是整板复刻。** D1 只保留 8/23 个器件，3 条去耦
   检查；其余器件、U2 的 EP 焊盘、C4/C6 的 139/140 mil WARN 都不在本案例判分。
2. **不是 DRC，不证明可布通/可制造。** 没有铜、过孔、铺铜、叠层、阻抗、热、EMC、装配信息；
   案例分数不能外推成「这块板能打样」。
3. **只看 pad-centre 距离与本体 bbox 几何。** 不判回路面积、回流路径、走线电感、载流/热。
   D2 的 acceptable 是「tracked 距离约束下的真实板基线」，不是「板已签核」。
4. **size_mm 用 dump footprint bbox（含焊盘外沿）近似契约的「本体」**；同时 1:1 复现 tracked
   bbox，所以硬检查口径与 tracked 的 bbox 语义一致，但与「裸本体」几何会有差异。
5. **全局代理阈值是基线回归界**（§4.4），不是独立判据；`net class` 是按网名的显示注释，
   只进 `metrics.hpwl_by_class`。
6. **固定/锁定件未编码为 `fixed:true`**（photo-led J1 在 tracked 中 `pcb lock`）：案例记录的是
   这一份已记录布局的位置，fixed 语义不影响对该布局的判分。
7. **D3 只判 body 相交**：tracked 的 10 mil 工艺净空（15.181 mil 重叠）不在 v1 范围。
8. 单案例只判一个候选布局、一层（dump 全为 layer 1）；不覆盖双面/多板/拼板。
