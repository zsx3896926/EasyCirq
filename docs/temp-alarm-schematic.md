# 温度报警器：原理图已画出，检查发现两个真问题

## 已完成

在一个新的原理图页（`P2`，uuid `9d9dd9e46f53880e`）上，按 `temp-alarm-proposal.md`
的方案 A 画出了完整电路：

| 器件 | 型号 | LCSC |
|---|---|---|
| NTC1 | NTC/10K | C9900004021 |
| U1 | LM393 | C504553 |
| BZ1 | 5025 贴片蜂鸣器 | C9900027059 |
| R1–R4 | 库内通用电阻 | — |

**15 条连接全部成功**（`ok: true` ×15），全部用网络标签：

```
VCC ─ R1 ─ NTC_MID ─ NTC1 ─ GND        ← 温度分压
VCC ─ R2 ─ TH ─ R3 ─ GND               ← 阈值分压
U1.3 (IN1+) ← NTC_MID
U1.2 (IN1-) ← TH
U1.8 ← VCC    U1.4 ← GND
U1.1 (OUT1) → ALARM → BZ1.1
BZ1.2 → GND
```

建板动作全程**不需要门禁令牌**（分阶段门禁的用处）。

## 离线检查的结果（真实，不是我写的）

```
offline pipeline: BLOCKED (apply_allowed=False)
  fail     #1 unconnected
  missing  #9 erc
  missing  #10 pin_mux
  fail     #11 decoupling
  missing  #13 bom_map
  missing  #14 netlist_diff
  missing  #15 readback
```

## 两个 fail 是真正的设计问题

### #1 unconnected —— 未用引脚没标 NC

LM393 是**双比较器**，我只用了第一路（1/2/3）。第二路的 5/6/7 是悬空的。
按检查规则，悬空引脚必须显式标「不接（NC）」才算处理过。

**修法**：`schematic.pin.set_no_connect` 给 U1:5、U1:6、U1:7 标 NC。

### #11 decoupling —— 没有去耦电容

LM393 的 VCC 与 GND 之间必须放 100nF（最好再加 10µF）。我漏了。
这是**真实的电路缺陷**——不是形式问题，缺去耦会让比较器在阈值附近抖动误报警。

**修法**：加 C1 = 100nF，接 VCC 与 GND。

## 五条 missing 是缺证据

| 项 | 说明 |
|---|---|
| #9 erc | 没跑 `sch drc` |
| #10 pin_mux | 没提供 `pin-plan/v1`（LM393 未用引脚复用） |
| #13 bom_map | 没导出 BOM |
| #14 netlist_diff | 没做写入前后对比 |
| #15 readback | 没做保存重开回读 |

## 意义

这是**第一次**「客户说一句话 → AI 画出完整电路 → 检查自己发现设计错误」。

前面 LED 板那次只有 2 个器件、没有功能逻辑；这次是**有真实功能的电路**
（分压 + 比较 + 报警），而且检查真的指出了两点缺陷：

1. 双比较器只用了半颗，另一半没处理（工程规范问题）
2. 缺去耦电容（**电气问题**）

**这两条不是缺证据，是画错了。** 这正是「没有任何一步能靠看起来没问题蒙混过关」
的意思。

## 下一步

1. 给 U1:5/6/7 标 NC
2. 加 C1 100nF 去耦
3. 补 ERC / BOM / 回读证据
4. 两轮 PASS → 卡片 → PCB → Gerber

## 第一轮修复的结果（2026-10-31 晚）

| 修复 | 命令 | 结果 |
|---|---|---|
| U1 未用引脚标 NC | `call schematic.pin.set_no_connect --payload '{"designator":"U1","pins":["5","6","7"],"connected":false}'` 语义上的 `noConnected:true` | `ok: true` |
| 加去耦电容 | 放 C1（100nF/0603，C9900013340），接 VCC 与 GND | `ok: true`，**#11 decoupling 消失** |
| 清理多余件 | 删掉失败放置留下的 C2 与未连接的 R4 | `deleted: true` ×2 |
| 蜂鸣器第 3 脚 | `set_no_connect` BZ1:3 | `ok: true` |

**#11（去耦）已解决**——这是本轮最重要的确认：加了电容，检查就不再报。

## 仍然存在的 #1（悬空引脚 = 5）

`verdict BLOCKED`，`floating_pins=5`。

已排除的原因：

- 管线确实传了 `--list`（NC 排除依赖它），代码里能看到：
  ```python
  conn_cmd = [HERE / "sch_connectivity_metrics.py", "--input", connectivity]
  if listing.is_file():
      conn_cmd += ["--list", listing]   # the connectivity IR carries no NC flag
  ```
- 删掉了 C2、R4 这两个未连接的器件。

还没查清的两点：

1. **C1 的两个引脚同名**：`sch connect --pin C1:2` 报
   `pin reference "C1:2" is ambiguous (2 matches: 2 2)`，用 `C1:2*` 绑定后，
   其中一个仍显示 `unconnected`。这是**符号库的数据问题**（0603 电容符号里两个
   引脚都叫 "2"），不是电路接错。
2. **NC 标记是否被 `--list` 识别**：`set_no_connect` 返回 `ok`，但 `floating_pins`
   仍计 5，说明要么 NC 没落到 `sch list` 的输出里，要么 U1:5/6/7 与 BZ1:3 之外的
   引脚也在计数内。

这两点需要下一轮用 `sch list` 的实际输出核对，不能靠猜。

## 当前进度

| 幕 | 状态 |
|---|---|
| 开工 | ✅ 方案、成本、工期 |
| 设计 | ✅ 原理图完整，**去耦已修**，悬空待查 |
| 上机前 | ⏳ BLOCKED（#1 + 五条缺证据） |
| 打样后 | ❌ 无实物 |


## 第二轮：NC 问题的根因找到了

loating_pins 从 9 降到 **1**。根因不是 NC 标记没生效，而是**快照清单漏了
\--include-pins\**：

`ash
# 之前的清单（错）
easycirq sch list --page <P> --include-bbox

# 正确
easycirq sch list --page <P> --include-bbox --include-pins
`

没有 \--include-pins\，\sch list\ 的器件里没有 \pins\ 数组，
\sch_connectivity_metrics._nc_keys()\ 就永远读不到 oConnected\，于是所有
显式 NC 引脚都被算成悬空。

加上之后，4 个 NC 标记（U1:5/6/7、BZ1:3）全部被识别，悬空从 5 降到 1。

**这是文档缺陷，不是代码缺陷**——工具本来就支持，是快照命令清单写漏了。

## 剩下的 1 个

\C1\ 的 pin 2 网络为空（pin 1 已接 GND）。补连时报
\SCHEMATIC_GEOMETRY_INVALID\——该引脚的位置与已有几何冲突。

下一轮的处理：把 C1 换一个不冲突的位置重放，或调整它所连网络的桩线方向。

## 第三轮：电容移位后电路本身没有 fail 了

把 C1 挪到空白位置（200,700）重放并接好 VCC/GND，再快照：

```
offline pipeline: BLOCKED (apply_allowed=False)
  missing  #9 erc
  missing  #10 pin_mux
  missing  #13 bom_map
  missing  #14 netlist_diff
  missing  #15 readback
```

**没有 fail** —— 电路本身是对的，只剩「还没提供证据」。

补上 ERC（`sch drc`）、BOM（`bom export`）、回读（`doc reload` 前后对比）之后：

```
offline pipeline: BLOCKED (apply_allowed=False)
  missing  #10 pin_mux
```

只剩一项。

## pin_mux 卡在示例与校验不一致

`pin_plan_check.py` 要求顶层有 `pins` 数组：

```python
pins = data.get("pins")
if not isinstance(pins, list):
    raise ValueError("require pins array")
```

但官方示例 `easycirq/assets/pinmap.example.json` 的顶层键是：

```
['_note', 'schema', 'device', 'pinmap']
```

**没有 `pins`**。照着示例写，check 直接报 `invalid_input: require pins array`。

这是**文档与实现的矛盾**：要么示例该带上 `pins`，要么 check 该把 `pinmap` 当作
资源声明的等价形式。我没有去猜 `pins` 的结构——猜错会写出一个「看起来通过」的报告，
先把矛盾记下来。

## 当前状态

| 项 | 值 |
|---|---|
| 原理图 | 完整（NTC + LM393 + 蜂鸣器 + 100nF 去耦） |
| fail 项 | **0** |
| 缺证据 | 1（pin_mux，卡在示例格式） |
| 进程 | `verdict BLOCKED` —— 缺证据不等于通过 |

## 下一轮

确认 `pins` 数组的正确结构（读 `pin_plan_check.py` 里 `pins` 的用法，或找现成的
`pin-plan/v1` 用例），补上后应能到 PASS。
