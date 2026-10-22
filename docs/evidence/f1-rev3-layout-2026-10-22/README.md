# F1 rev3 重排证据（2026-10-22）

## 结论先行

- 以 rev3（21 器件电气基线）为对象，完成了一次**纯排版变更**：21 个器件的位号、库身份、封装、Unique ID、BOM/PCB 标志、12 个网络、60 个物理引脚全部不变。
- 重排前后 Protel 网表用 `netlist_diff.py` 比较：**`match: true`、`differences: []`**，不是只看 `pin_net_changed=0`；导出的 `netlist-after.net` 与 golden `netlist-before.net` SHA256 完全相同。
- `apply` 两阶段逐项回读通过，`save:true`；关闭重开后 `status: match`，比较域含 project/page 身份、器件属性/绑定、电源标记类型、端口方向、导线与不可解析导线。
- DRC：rev3 原 5 warn（4× `OBJECTOUTSIDESHEET` + 1× `CHECKFLOATPIN`）→ 重排后 **3 warn**（2× `ONENETNAME` + 1× `CHECKFLOATPIN`），0 error；越页告警消除。
- 图面仍**未达到工程师级排版**：J101 左侧内部标注仍拥挤，页面中部/右侧留白大；状态 `PARTIAL`。它不是重新设计的原理图，只是电气等价的块级平移。

## 基线关系（重要）

| 版本 | 器件数 | 说明 |
|---|---:|---|
| rev1 `docs/evidence/f1-2026-10-22/` | 16 | 旧版；PR #4 的重排对象 |
| **rev3 `docs/evidence/f1-rev3-2026-10-22/`** | **21** | 本轮基线；新增 C104/C105/C106/C107/D102/R107，C103→C107 钽电容，IO2 上拉、EN/RST RC、TVS、壳脚 GND |

本证据**不覆盖** rev3 的电气修订；rev3 的 golden 网表 `f1-rev3b.net` 作为不可变基线。

## 方法

rev3 页面由 21 个物理自包含块组成：块内器件、短导线、电源标记、网络端口互相接触；跨块连接只通过同名标记/端口。因此对每个块做**整体平移**即可保持电气图不变。

1. 读取 rev3 副本快照，按坐标相接求 21 个物理块。
2. 为每块指定目标 bbox；脚本检查跨块点/线段相碰、页边界（y 轴在 EDA 中向上，标题栏在低 y）。
3. 阶段 1：删除 37 个电源标记、20 个端口、57 个导线图元；移动 21 个器件到目标位置。
4. 阶段 2：在平移后的坐标重建同名标记/端口；导线按**单段**重建（51 段），避免 4.1.78 对多段线的扁平化/合并。
5. 导出网表 → `netlist_diff.py` 对 golden；导出 PNG 人工看图；`drc`；保存后关闭重开比较。

## 实际执行中的问题

1. **rev3 删除原语的 `direction` 前置条件自比对 bug**：`target.expected.direction` 在快照里可读到，但执行时 `delete_primitive` 的 drift 检查从组件 state 读不到 direction，导致 20 个端口删除全部 `stale_target`。本轮计划先不把 direction 放进删除前置条件；随后在 `eda_exec.py` 的 delete 处理器里补了 `portDirectionOf/flagTypeOf` 派生，后续可恢复该前置条件。
2. **零长度导线**：rev3 经验是零长度线可能是引脚-端口连接图元。本轮删除全部导线/端口后**重建了全部端口**，编辑器重新生成了 10 条零长度桩；网表逐脚一致，说明在“端口也重建”的前提下删除是安全的。若只删零长线不重建端口，仍会断网。
3. **y 轴方向**：第一次目标布局把电源行放到了页面底部、并与标题栏重叠；改为 y 向上后，电源链在顶部、MCU 在中部，标题栏不再被压。

## 结果

### 网表（关键门禁）

```json
{
  "match": true,
  "before": {"components": 21, "nets": 12, "pins": 60},
  "after":  {"components": 21, "nets": 12, "pins": 60},
  "differences": []
}
```

`netlist-after.net` SHA256 = `709b505f...6fd6`，与 golden `f1-rev3b.net` 完全一致。

### 对象计数

| 对象 | 重排后 |
|---|---:|
| 器件 | 21 |
| 电源标记 | 37 |
| 网络端口 | 20 |
| 导线图元 | 57（含 10 条零长度桩） |
| 归一化导线段 | 47 |

### DRC

| 规则 | rev3 原 | 重排后 | 说明 |
|---|---:|---:|---|
| `OBJECTOUTSIDESHEET` | 4 | 0 | 左侧 GND 标记已移入图框 |
| `ONENETNAME` | 0 | 2 | 合并后的 GND 网络存在多个同名记录；网表只有一个 GND，未发现短路 |
| `CHECKFLOATPIN` | 1（6 引脚） | 1（6 引脚） | J101 B8/B7/B6/A8/A7/A6 未用 USB 数据脚；桥不支持 NC，保留 |

### 保存 / 重开

`reopen-check.json`：`status: match`；21 器件、37 标记、20 端口、47 归一化线段；比较域含 parts(属性/绑定/BOM/PCB)、netflags(type)、netports(direction)、wires、unparsed_wires。无差异。

## 证据文件

| 文件 | 内容 | SHA256 |
|---|---|---|
| `layout.png` | 重排后整页（1800 宽） | `fecd460c...60be3` |
| `netlist-before.net` | rev3 golden | `709b505f...6fd6` |
| `netlist-after.net` | 重排后导出 | `709b505f...6fd6` |
| `netlist-diff.json` | 确定性 diff | `87102367...20cb0` |
| `drc.json` | DRC 原始返回 | `85b18496...991a` |
| `reopen-check.json` | 重开比较 | `2808d661...6714` |
| `snapshot-after.json` | 保存后快照 | `9facf176...cdd5` |
| `plans/01-delete-move.json` | 阶段 1 | — |
| `plans/02-recreate.json` | 阶段 2 | — |
| `apply-stage1.json` / `apply-stage2.json` | 逐项回读结果 | — |

## 复现

```bash
cp <rev3-copy>.eprj2 f1-rev3-layout.eprj2
python design-hardware/scripts/eda_exec.py doctor --project f1-rev3-layout.eprj2
python design-hardware/scripts/eda_exec.py open --project f1-rev3-layout.eprj2
python design-hardware/scripts/eda_exec.py apply --session <id> --plan plans/01-delete-move.json --allow-delete
python design-hardware/scripts/eda_exec.py apply --session <id> --plan plans/02-recreate.json --save
python design-hardware/scripts/eda_exec.py export --session <id> --schematic F1-USB-MCU-C --page-name P1 --kind netlist --output after.net
python design-hardware/scripts/netlist_diff.py netlist-before.net after.net --output diff.json
python design-hardware/scripts/eda_exec.py export --session <id> --schematic F1-USB-MCU-C --page-name P1 --kind png --output layout.png --width 1800
python design-hardware/scripts/eda_exec.py drc --session <id> --schematic F1-USB-MCU-C --page-name P1
python design-hardware/scripts/eda_exec.py read --session <id> --schematic F1-USB-MCU-C --page-name P1 --output after.json
python design-hardware/scripts/eda_exec.py close --session <id>
python design-hardware/scripts/eda_exec.py reopen-check --project f1-rev3-layout.eprj2 --snapshot after.json --schematic F1-USB-MCU-C --page-name P1
```

## 未完成 / 边界

- 图面：J101 内部（SBU/DP/DN 与 GND/5V/CC 标注）仍拥挤；页面中部/右侧留白大；标题栏仍 `V1.0`，未改 `DRAFT`。
- 未做 ERC 豁免表、人工独立审图、全在线 GUI 复验、PCB、制造资料、固件/首板。
- `ONENETNAME` 是编辑器对合并后 GND 的多条同名记录告警；本轮未逐条豁免，也未改电气。
- 本证据只证明 rev3 的**排版等价**，不证明 rev3 电气设计可生产。
