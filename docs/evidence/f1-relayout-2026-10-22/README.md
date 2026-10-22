# F1 原理图重排与 DRC 证据（2026-10-22）

## 结论先行

- 在嘉立创EDA专业版 4.1.78 的真实工程副本上，对 F1（`F1-USB-MCU-C / P1`）完成了一轮**电气等价的重排**：16 个器件身份、11 个网络、45 个已连接物理引脚全部保持；重排前后 Protel 网表逐引脚一致。
- `apply` 逐项回读通过，`save:true`；关闭会话重开后，16 器件 / 41 个导线对象（44 个归一化线段）/ 27 电源标记 / 14 网络端口全部 `match`。
- 原理图 DRC：重排前 5 条告警（4 条 `OBJECTOUTSIDESHEET` + 1 条 `CHECKFLOATPIN`）；重排后 4 条告警（3 条 `ONENETNAME` + 1 条 `CHECKFLOATPIN`），**0 条 error**。`OBJECTOUTSIDESHEET` 已消除。
- 图面仍**未达到工程师级排版验收**：J101 的 SBU/DP/DN 引脚名、U101 周边上拉/端口、J102 排针标注仍有文字拥挤。状态为 `PARTIAL`，不冒充完成。
- 未做：全在线 GUI 会话复验、PCB、ERC 电气规则人工审查、制造输出。F1 仍不是可生产板。

## 环境与对象

| 项 | 值 |
|---|---|
| 客户端 | 嘉立创EDA专业版 `4.1.78.34f5b8d9` |
| 模式 | 半离线（`online:false`、`half_offline:true`、`offline:false`） |
| 工程副本 | `C:\Users\jlc\work\hw-eda-round3\f1-layout.eprj2`（不提交，源自上一轮 `base-copy.eprj2`） |
| 原理图 / 图页 | `F1-USB-MCU-C / P1`，page UUID `f6d41a58df3fa849` |
| 通道 | `lceda-pro invoke --ext-uuid eda` + `design-hardware/scripts/eda_exec.py` |
| 用户会话 | 用户自有 `test` 会话全程未操作；本轮只用 CLI 自建 headless 会话 |

## 重排方法

上一轮 F1 的物理连通块是 15 个（器件 + 自己的短导线/电源标记/网络端口），跨块连接全部通过**同名电源标记/网络端口**完成。因此可以刚性平移每个连通块，而不改变任何引脚-网络关系。

1. 读取当前页快照，按“坐标相接”求 15 个物理连通块。
2. 为每块指定平移量；先用脚本检查**跨块点/线段是否相碰**，再生成计划。
3. 删除全部导线/电源标记/端口 → 移动器件 → 在平移后的坐标重建同名图元。
4. 第二次重排针对三处最拥挤的局部（J101、U101、J102、U102）改成**短水平支线 + 不同 x 车道**的标注，减少符号堆叠；移动 R101/R102/SW102 对齐各自的引脚行。
5. 每一步都先 `--dry-run`，再真实写入；任何回读失败都不保存。

## 关键失败与修复（真实回读发现）

1. **平移碰撞导致 CC1 被并入 5V**：第一次平移把 R101 的 CC1 端点放到 J101 的 5V 标记同一坐标，导线被编辑器归到 5V。逐项回读立即报 `wire ... missing_segments`，未保存；回滚副本并加入跨组坐标碰撞检查后重做。
2. **L 形多段导线被编辑器重排**：`[690,260]→[690,240]→[650,240]` 写入后回读为扁平折线，`_segments_from_line` 无法归一化，验证失败。改为拆成两条**单段导线**后通过。这与上一轮“同网多段线会被合并/重排”的真机结论一致。
3. **SW102 引脚映射写反**：重排计划误把 SW102 pin1 当 GND、pin2 当 IO0；重排后网表显示 `SW102-1` 落入 GND、IO0 少了 `SW102-1`。按真实快照（pin1=IO0、pin2=GND）修正标注后，网表恢复一致。
4. **删除/新建同网段需要分批**：同一计划里“删旧线 + 建新线”会让对账把旧线当作已覆盖而只补差段；拆成删除、创建两个计划后验证通过。

这些失败都保留在 `apply-stage4.json`（partial）与修复后的 `apply-stage5/6/7*.json` 中，没有用“最终成功”覆盖失败现场。

## 结果

### 网表

`netlist-before.net` 与 `netlist-after.net` 解析后，11 个网络的物理引脚集合完全一致：

```text
5V, 3V3, GND, CC1, CC2, EN, RST, IO0, TXD, RXD, LED_A
```

### 图面对象计数

| 对象 | 重排后 |
|---|---:|
| 器件 | 16 |
| 电源标记 | 27 |
| 网络端口 | 14 |
| 导线对象 | 41 |
| 归一化线段 | 44 |

### DRC（编辑器 `sch_Drc.check(true,false,true)`）

| 规则 | 重排前 | 重排后 | 说明 |
|---|---:|---:|---|
| `OBJECTOUTSIDESHEET` | 4 | 0 | 图元越出图页边框，已消除 |
| `ONENETNAME` | 0 | 3 | 3V3/GND 合并网络存在多个同名记录；导出网表只有一个 3V3 与一个 GND，未发现短路 |
| `CHECKFLOATPIN` | 1（11 引脚） | 1（11 引脚） | J101 的 SBU1/SBU2/DP1/DP2/DN1/DN2 与 shield 1-4 未接；U101 IO2 未接。属于未使用引脚，保留并在下轮电气审查处理 |

DRC 通过与否不替代连接回读和看图；本轮以网表逐引脚一致 + 重开一致作为电气等价依据。

### 保存 / 重开

`reopen-check.json`：`status: match`；project/schematic/page 三个 UUID 全部 `match`；`parts 16→16`、归一化 `wires 44→44`、`netflags 27→27`、`netports 14→14`，无差异；保存后快照的导线对象为 41（无零长度桩）。

## 证据文件

| 文件 | 内容 | SHA256 |
|---|---|---|
| `layout.png` | 重排后整页导出（1800 宽） | `cfcfb143...ef61` |
| `netlist-after.net` | 重排后 Protel 网表 | `70a39ba8...f8ec7` |
| `snapshot-after.json` | 保存后整页回读快照 | `b158e0f3...64e5` |
| `reopen-check.json` | 关闭重开对比（含 project/schematic/page 身份） | `e73c84b2...832a` |
| `drc-after.json` | 重排后 DRC 原始返回 | `029b6af5...25fd` |
| `plans/` | 各阶段可复现计划 | — |
| `apply-stage*.json` | 各阶段逐项执行与回读结果（含失败现场） | — |
| `netlist-before.net` | 重排前网表 | — |
| `drc-before.json` | 重排前 DRC 原始返回 | — |

## 复现

```bash
# 1. 复制工程（不要在原工程上直接写）
cp base-copy.eprj2 f1-layout.eprj2
python design-hardware/scripts/eda_exec.py doctor --project f1-layout.eprj2
python design-hardware/scripts/eda_exec.py open --project f1-layout.eprj2

# 2. 按 plans/ 顺序执行；每步先 dry-run
python design-hardware/scripts/eda_exec.py apply --session <id> --plan plans/01-translate-delete-move.json --dry-run
python design-hardware/scripts/eda_exec.py apply --session <id> --plan plans/01-translate-delete-move.json
python design-hardware/scripts/eda_exec.py apply --session <id> --plan plans/02-translate-recreate.json --save
# ... 03/04/05/06a/06b/07a/07b 依次执行

# 3. 导出与核验
python design-hardware/scripts/eda_exec.py export --session <id> --schematic F1-USB-MCU-C --page-name P1 --kind netlist --output after.net
python design-hardware/scripts/eda_exec.py export --session <id> --schematic F1-USB-MCU-C --page-name P1 --kind png --output layout.png --width 1800
python design-hardware/scripts/eda_exec.py drc --session <id> --schematic F1-USB-MCU-C --page-name P1
python design-hardware/scripts/eda_exec.py read --session <id> --schematic F1-USB-MCU-C --page-name P1 --output after.json
python design-hardware/scripts/eda_exec.py reopen-check --project f1-layout.eprj2 --snapshot after.json --session <id> --schematic F1-USB-MCU-C --page-name P1
```

## 未完成与边界

- **图面**：J101 左侧未使用引脚名与 R101/R102 标注仍拥挤；U101 周边端口/上拉文字密集；J102 排针标注仍紧。下一步应按“功能块 + 更大间距 + 网络标签”重画这三处，而不是继续平移。
- **电气**：J101 shield 1-4、SBU/DP/DN 仍悬空；U101 IO2 悬空。是否接 GND/NC 需按 Type-C 与 ESP-01S 原厂资料确认，本轮未擅自改电气。
- **ERC/DRC**：只运行编辑器原理图 DRC；未逐条判定 `ONENETNAME` 是否可豁免，也未做 ERC 规则配置审查。
- **全在线**：本轮仍是半离线 CLI 会话；全在线 GUI 结论只能由用户自己的全在线会话复验。
- **PCB/制造/样机**：未开始。
- **工程文件**：`f1-layout.eprj2` 是 scratch 副本，不随仓库提交；证据中的计划依赖该副本的 primitive id，换工程需重新读快照生成。
