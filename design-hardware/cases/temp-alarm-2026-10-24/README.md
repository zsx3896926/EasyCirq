# 回归案例：室内温度报警小板（2026-10-24）

> 这是 `gate_check.py` 的离线回归夹具，不是一次新的 EDA 操作，也不是可制造板。
> 证据是 2026-10-24 实战项目的快照；本轮只读，不打开嘉立创 EDA、不修改工程、不下单。

## 1. 为什么有这个案例

这个项目把“先画后想”的典型错误都踩了一遍：需求边界没记、可选件在 PCB 阶段才删、布局分数不达标仍开始布线、电源/地策略没在布线前声明、DRC 多轮打地鼠、制造包和恢复演练缺失。把它的证据固定下来，用来验证 G0–G6 门禁不会把这种项目判成通过。

项目源代码与原始证据仍在上游工作目录 `C:\Users\jlc\work\temp-alarm-20261024`；本目录只保存复现门禁所需的证据副本。

## 2. 怎么跑

```text
python scripts/gate_check.py --project temp-alarm ^
  --evidence-dir cases/temp-alarm-2026-10-24/evidence ^
  --project-dir cases/temp-alarm-2026-10-24 ^
  --design-state cases/temp-alarm-2026-10-24/design-state.json ^
  --waiver-file cases/temp-alarm-2026-10-24/waivers.json --json
```

在仓库根目录执行。只用 Python 标准库，不连 daemon。

## 3. 预期结果

| 门禁 | 预期 | 主要依据 |
|---|---|---|
| G0 需求 | `BLOCKED` | 尺寸上限、外壳/安装孔、装配方式、数量/预算、环境/精度仍是 `pending`；另有 blocking open item |
| G1 功能冻结 | `BLOCKED` | `function_freeze.status=not-frozen`；J2/D2 在 PCB 阶段才删且无 `change_impact` |
| G2 原理图 | `PASS_WITH_WAIVER` | `sch drc` 0 fatal/0 error；`sch check` 电气类 0、风格类 10；10 条风格警告有落盘豁免 |
| G3 布局 | `BLOCKED` | `layout-lint` 48/100、13 crossings；无目标板框、无安装孔记录、布局未冻结；lint 早于最终 board dump |
| G4 电源地 | `BLOCKED` | 2 层/铺铜策略未预先声明；DRC 规则未记录；过孔回执带 `staleRisk` |
| G5 布线 | `BLOCKED` | `pcb drc` 18（16 Clearance + 2 Connection）；关键网无 `net-path` 证明；无保存重载；丝印压焊盘；连续 3 轮改善 <30% |
| G6 制造 | `BLOCKED` | 无 Gerber/钻孔/CPL；工艺档案缺失；`.epro2` 未做恢复演练；库存/SMT 未核对 |

`expected.json` 是机器可读版本；`actual.json` 是本次实际运行的报告（可重新生成，不建议提交运行时间会变的报告时覆盖预期）。

**如果七门全 PASS，说明门禁没有覆盖这次错误；如果 G2 不是 `PASS_WITH_WAIVER`，说明风格警告/豁免链路没接上。**

## 4. 证据清单

| 文件 | 来源（上游 evidence/） | 用途 | SHA-256 |
|---|---|---|---|
| `evidence/sch-drc.json` | `sch-drc.json` | sch DRC 0（human 摘要） | `b4fef88a…92c38c` |
| `evidence/sch-check-final2.json` | `sch-check-final2.json` | 10 条风格警告；电气类 0 | `a2f5ba59…522207` |
| `evidence/schematic-final.png` | `schematic-final.png` | 实际看图证据 | `0f853c1b…622f75` |
| `evidence/pcb-layout-lint-2.log` | `pcb-layout-lint-2.log` | score 48/100、13 crossings | `36f51e07…a714c4` |
| `evidence/pcb-board-final.json` | `pcb-board-final.json` | 板框、组件、铜、规则 dump | `692522e2…9a090f` |
| `evidence/pcb-drc.json` | `pcb-drc-11.json` | 18 条 DRC（16/2） | `c6ef18eb…55164b` |
| `evidence/pcb-pour-list.json` | `pcb-pour-list.json` | GND L1/L2、+5V、VREF 四个铺铜 | `9a5823e3…19dcc3` |
| `evidence/pcb-vias.json` | `pcb-vias-4.json` | 39 过孔，带 `staleRisk` | `ae58be0c…395c1b` |
| `evidence/BOM.csv` | `BOM-export.csv` | 21 行/26 件，全部有 C 号（未核对库存） | `b306e3bb…25ff7c` |
| `evidence/project-export.json` | `project-export-2.log` | zip 完整、`restoreVerified:false` | `46475fa5…041a0f` |
| `evidence/temp-alarm-test.epro2` | `temp-alarm-test.epro2` | 工程备份（364,810 bytes） | `6dcf4d87…800d9e` |
| `docs/test-plan.md` | `docs/test-plan.md` | 实物测试计划 | `42400b65…c73691` |

完整哈希前缀见上表；重新核对时用 `Get-FileHash <file> -Algorithm SHA256`（PowerShell）或 `sha256sum`。

## 5. 这个案例能证明什么、不能证明什么

能证明：

- `gate_check.py` 能解析 human 文本证据、JSON 证据、CSV BOM 和 `.epro2` zip；
- 缺目标、缺安装孔、缺关键网证明、DRC 未过、制造包缺失会分别落在对应门禁；
- 风格警告只影响 G2，且必须靠落盘豁免才能得到 `PASS_WITH_WAIVER`；
- 同一份证据在 `--strict-advisory` 下会更严格。

不能证明：

- 该项目已经修好或可以打板；
- 该板的电气/热/机械设计正确；
- 库存、价格、SMT 可贴状态是当前值；
- 任何 EDA 命令在本次运行中被执行过（本案例只读证据）。

## 6. 文件

- [design-state.json](design-state.json)：项目状态与门禁输入
- [waivers.json](waivers.json)：G2 风格警告豁免
- [expected.json](expected.json)：机器可读预期
- [change-log.md](change-log.md)：实战错误清单与修复过程
- [docs/test-plan.md](docs/test-plan.md)：实物测试计划副本
