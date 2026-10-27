# round12 真机验收记录（usb-audio-verify-r12 / P1）

日期：2026-10-27
PR：`#32`（分支 `feat/compose-tooling-r12`）
Skill：`design-hardware` 0.9.4 工具链；EasyEDA Pro 4.1.78；easyeda-agent 1.15.0
窗口：`c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7`

## 范围与写入边界

- 只在导入备份形成的独立副本 `usb-audio-verify-r12`（UUID
  `66ad17591d5b4f6ebbcb42295f76b2b1`）的 P1（`660075c31db6f396`）上执行。
- 写入前由 jlc-b9 向 jlc-6f / jlc-7f 确认窗口唯一写入权；两者明确回复不写、
  不切换文档。原工程 P2 未触碰，未修复、未覆盖。
- 最终保存 `seq 2453`；`doc reload` 保存→关闭→重开后另行回读。

## 工具链与执行结果

| 阶段 | 结果 |
| --- | --- |
| `sch_compose_input.py` | `ready`：8 模块 / 24 器件 / 93 线 / 33 标记；project UUID 按副本重写 |
| `sch_sheet_fit.py` | `fits`：fillRatio 0.4766，usable `25..1145 × 25..800`，effective margin 10.5 / zone gap 11 / keepout 15 |
| `--connectivity-edits` | 59 行，全部为网络变化；0 NC 变化 |
| `sch compose` | 173 步 playbook；`sch apply --dry-run` 通过 |
| `sch apply` | **未完整完成**：170 步 OK；第 171 步 `strict-schematic-gate` FAIL；第 172 `save-composition`、173 `verify-saved-instance-preservation` 未执行 |
| 失败处置 | 回读 `sch check`，未使用 `--resume/--from/--to`，未整批重放；只重算 C5 位号属性 |
| 人工保存 / 重开 | `sch save` → `seq 2453`；`doc reload` → `doc ready` 可读 58 stable components |
| 最终 `sch check` | total 8 = 5 info wire-crossing + 3 基线 out-of-sheet；floating/geom/dangling/marker/partition 全 0；无 designator-overlap |
| `sch gate`（非 strict） | `verdict: pass`；check 8 warn/info；DRC 4 warn、native PASS |
| `sch gate --strict` | `verdict: fail`，仅基线 3 条 sheet out-of-sheet + 4 条 DRC warn（P3 2×ONENETNAME、P2 1×ONENETNAME、P1 F1 1×ATTRMATCHCODE） |

`sch apply` 的具体失败点和未执行步骤保存在 apply journal；最终状态由人工
save/reload/readback 独立确认，不把 apply 说成成功。

## C5 位号失败与重算

- 第 171 步 strict gate 报 `C5` designator-overlap。回读显示位号 bbox 与
  `VBAT_24V` 标记文字有 0.5 raw 重叠。
- 第一次 `sch attribute-move` 把位号从 `(690,615)` 移到 `(690,612)`；
  命令 `verified:true`，但回读发现它与 C5 本体 bbox（maxY 613.5）重叠 1.5 raw。
- 重新读取当前完整属性状态，第二次移到 `(712,612)`；`moved:true /
  preserved:true / verified:true`。回读 `sch check` 不再有 designator-overlap，
  官方 PNG 的 C5 区域显示位号位于本体右上侧，未压本体、`10uF` 值或
  `VBAT_24V` 文字。

## 保存重开后的身份 / 逐脚比对

对照原工程 P1 最终快照：

- `out/P1-after.json`：24 器件 / 59 引脚（含每脚 `net`、`noConnected`、
  `primitiveId`）。
- `out/P1-after-conn.json`：13 网络 / 59 连接。

副本回读结果（`work/identity-compare.json`）：

- `status: identical`；24/24 器件身份字段一致（`primitiveId`、`uniqueId`、
  component/device/footprint/symbol、manufacturer/supplier、BOM/PCB 标志、
  属性、rotation）；`EasyEDA Agent Component ID` 24/24 保留。
- 59/59 引脚一致：`pinNumber`、`pinName`、`primitiveId`、`net`、`noConnected`；
  只有坐标/bbox 随重排变化（24/24 器件布局变化属预期）。
- 13/13 网络分组、59/59 connections 一致。
- 唯一预期差异：副本工程 UUID `66ad...` 与原工程 `ce48...` 不同；页面 UUID
  `660075c31db6f396` 一致。

## 官方导图审查

- `sch export-image --format svg`：167,104 bytes，
  SHA-256 `85813c6d1d71a6f026c1ca8c0ed2706f9d38b70a81b5f285304604a8077eead3`。
- `sch export-image --format png`：632,952 bytes，2435×1711，
  SHA-256 `9a7d6b5fd273e3dedd142f2a396b2086a712d4bacffdece6720522c82f5a22ef`。
- 目视检查：8 个功能区框不重叠、不越界；标题栏完整；C5、Switch node、
  TPS core、24V input 放大图未发现新的文字遮挡或导线压脚。标题栏同时显示当前
  工程名与 sheet 内原工程名（原 P1 图相同），属基线现象，本次未改标题栏。

## 未执行 / 边界

- **NOT RUN**：P2/P3 重排；原工程 P2 修复（按要求保持原样）；PCB 布局；制造
  文件导出；strict gate 通过（被上述基线警告阻塞）。
- **NOT CLAIMED**：离线 `ready/fits/verified` 不等于真机通过；`sch apply`
  playbook 本身未完成。
- 本记录对应本地证据目录
  `C:/Users/jlc/work/usb-audio-verify-r12/pages/after2/`，索引见
  `work/evidence-index.json`；原始基线在
  `C:/Users/jlc/work/usb-audio-reflow-20261027/out/`。
