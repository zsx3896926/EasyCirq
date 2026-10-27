# 制造包清单（G6）

> 模板：复制到项目工作区（建议 `manufacturing/`）后按实际导出结果填写。未核项写 `待核`，不默认放行；未知值不填 0、不编造。工艺参数另按 [manufacturing-profile.md](../manufacturing-profile.md) 记录，实物测试按 [verification.md](verification.md) 执行，结构化选料台账见 [parts.example.json](../parts.example.json) 与本文第 5 节。门禁定义见 [design-gates.md](../../references/design-gates.md)。

## 1. 使用边界与真实命令

`design-hardware` 负责清单、证据与工程判断；实际导出由 `zhigou` / EDA 完成。前代执行器 v1.14.0 中与本门禁直接相关的命令只有：

```powershell
zhigou bom export --type csv --enrich=false --project <name> > manufacturing/BOM.csv
zhigou project export --out manufacturing/<project>-<rev>.epro2 --project-uuid <uuid>
```

v1.14.0 的 `--help` 中没有 Gerber、钻孔、坐标/CPL、装配图的 CLI 子命令，这三类制造文件在能力上属 `UNSUPPORTED`：必须由用户在嘉立创EDA专业版的制造资料导出入口人工导出，并在 manifest 中记录 `GUI 手工导出`、EDA 版本、导出人、时间与 sha256；缺人工证据时 G6 为 `BLOCKED`。不得写成不存在的 `zhigou pcb export-gerber` 之类命令。一次只认一个板版本，换版必须全部重导并更新哈希，不能沿用旧文件。

## 2. Manifest 模板

清单头（每个板版本一份）：

```text
板名/版本:       <project> / <rev>
EDA 版本:        嘉立创EDA专业版 <版本>
CLI 版本:        前代执行器 v1.14.0
工程 UUID:       <uuid>
导出时间:        <YYYY-MM-DD HH:MM +08:00>
导出人/复核人:   <姓名或接手记录>
```

文件清单（`role` 与 `design-state.json` 的 `manufacturing.artifacts[].role` 一致）：

| role | 必须覆盖 | 生成方式 | 必须记录 |
|---|---|---|---|
| `gerber` | 顶层/底层铜、顶层/底层阻焊、顶层/底层丝印、板框、顶层/底层钢网；单文件或 zip 注明 | GUI 手工导出 | 文件名、层清单、导出时间、EDA 版本、sha256 |
| `drill` | PTH/NPTH 或合并文件，孔径表与板厚 | GUI 手工导出 | 文件名、孔数、最小孔径、sha256 |
| `bom` | 可订购 BOM（位号、数量、MPN、厂家、C 号、封装、DNP 标记） | `zhigou bom export --type csv --enrich=false` | 文件名、行数/件数、sha256 |
| `cpl` | 贴片坐标（designator、x、y、层、旋转）；与当前装配变体一致 | GUI 手工导出 | 文件名、贴装面、件数、sha256 |
| `assembly_drawing` | 顶/底装配图：极性、1 脚、DNP、连接器方向 | GUI 打印/导出或 EDA 截图 | 文件名、覆盖面、sha256 |
| `stackup_process` | 层叠、板厚、铜厚、表面处理、阻焊/丝印、阻抗 | 按 manufacturing-profile 填写 | 文件、与订单页核对日期 |
| `project_export` | 可重开的 `.epro2` 工程备份 | `zhigou project export` | 路径、sha256、zip 完整性、恢复演练结果 |
| `manifest` | 本清单的最终版 | 人工汇总 | 版本、生成时间、上表全部哈希 |

`gate_check.py` 只自动核对 `gerber / drill / cpl / bom` 四类核心件；`assembly_drawing`、`stackup_process` 等作为人工证据登记，不能因为脚本没查就省略。

## 3. 嘉立创工艺检查表

工艺值必须来自当日订单页或对应规则文档，并写明核对日期；旧报价、旧活动、别人的订单截图都不算。

| 检查项 | 必须记录 | 常见返工/退单点 |
|---|---|---|
| 层数/层叠 | 2 层或 4 层；各层用途（信号/平面）；与设计一致 | EDA 层数、Gerber 层数与订单不一致 |
| 板厚 | 成品厚度、公差；阻抗要求的板厚 | 1.6 mm 默认值被忽略 |
| 铜厚 | 外层/内层铜厚（oz 或 µm）；大电流路径是否加铜 | 细线按 1 oz 算，实际 0.5 oz |
| 表面处理 | 有铅/无铅喷锡、沉金、OSP 等；与焊接工艺匹配 | 沉金厚度/面积附加费未计 |
| 阻焊 | 颜色、单双面、开窗规则、过孔盖油/开窗 | 测试点被阻焊覆盖 |
| 丝印 | 颜色、最小线宽/字高、是否允许压焊盘 | 位号太小不可读、压盘被删 |
| 阻抗 | 有无阻抗网络；层别、目标值、公差、是否要报告 | 写了“阻抗 50Ω”但未给层别 |
| 拼板 | 单元数、工艺边、V-CUT/邮票孔、拼板尺寸 | 单板坐标被当成拼板坐标 |
| SMT 面别/类型 | 单面/双面；经济型/标准型；可贴范围 | 双面贴装与坐标文件不一致 |
| 定位孔/工具孔 | 数量、孔径、位置；是否非金属化 | 与安装孔混用 |
| Mark 点 | 数量、直径、位置、阻焊开窗、周围无铜 | Mark 被丝印或铜覆盖 |
| 板框/外形 | 尺寸、圆角、公差、板边禁布 | 外形层与钻孔/槽冲突 |
| 孔/槽/塞孔 | PTH/NPTH、槽宽、是否树脂塞孔/盖帽 | 槽被当成钻孔导出 |

层数决策与电源/地策略见 [pcb-routing-strategy.md](../../references/pcb-routing-strategy.md)；渠道与动态费用边界见 [lcsc-sourcing.md](../../references/lcsc-sourcing.md) 和 [jlc-handoff.md](../../references/jlc-handoff.md)。

## 4. 选料与装配清单

逐行核对，不允许“BOM 有 C 号”就当作可下单：

- **C 号**：`C` 加数字；只在商城商品页核对后写入。非立创渠道或自备料写显式状态与渠道，不能拿相似料号顶替。
- **库存**：记录 `status`、数量与 `checked_at`（实际查询日期）。商城库存与嘉立创 SMT 库存分开核，旧 BOM、搜索摘要、缓存页面都不算。
- **SMT 可贴**：单独核对基础库/扩展库/寄料、换料费、包装与最小起订；`smt_class=pending` 不是可贴证据。
- **MOQ/包装**：按商品页的起订量、订购步进与包装形式记录；未知写 `待核`，不假设整盘或零剪规则。
- **DNP**：保留 BOM 行与原因，排除在该装配变体的装配清单与 CPL 之外；DNP 不是 NC，也不是从原理图删除。
- **替代料**：记录差异等级与需改动范围（直接替换/改外围/改封装/资料不足），不能只写“有货”。

字段级核对用第 5 节的 `bom_check.py`；可订购 BOM 仍以 EDA 导出的 `BOM.csv` 为准，两者不能互相替代。

## 5. `parts.json` 与 `bom_check.py`

`parts/v1` 是选料/库存/DNP 的计划台账，不是 EDA 导出的 BOM。示例见 [parts.example.json](../parts.example.json)（示例数据，库存全部未核）。

| 字段 | 必填 | 取值/规则 |
|---|---|---|
| `schema` | 是 | 固定 `parts/v1` |
| `project` | 否 | 项目名，便于报告归属 |
| `parts[].role` | 建议 | 功能角色；缺失只告警 |
| `parts[].designators` | 是 | 非空数组，格式为字母+数字，全局唯一；重复位号阻塞 |
| `parts[].mpn` | 是 | 完整可订购型号；空白或占位符（`待核`/`TBD`）阻塞 |
| `parts[].manufacturer` | 是 | 厂家；空白或占位符阻塞 |
| `parts[].lcsc` | 非 DNP 必填 | `C\d+`；或对象 `{"status":"non_lcsc","note":"..."}`（非立创）；`pending` 表示待核 |
| `parts[].footprint` | 是 | EDA 封装名 |
| `parts[].package` | 是 | 封装/尺寸（如 `0402`、`SOT-23-5`、`直插 Ø9.5`） |
| `parts[].assembly` | 是 | `smt` / `hand` / `tht` / `dnp` |
| `parts[].datasheet` | 建议 | 链接或项目内文件名；缺失只告警 |
| `parts[].stock` | 非 DNP 必填 | `status` ∈ `in_stock/low/out_of_stock/unchecked`；`qty` 为 >=0 整数或 null |
| `parts[].smt_class` | `assembly=smt` 必填 | `basic` / `extended` / `consigned`（寄料/自供）/ `pending` |
| `parts[].alternates` | 否 | 数组；每项 `mpn` 必填，`lcsc` 可选，`difference/note` 可选 |

装配枚举：

- `smt`：交嘉立创 SMT；必须有 `smt_class`。
- `hand`：贴片件手焊；0402/1005 告警，`--strict` 下阻塞；0201 直接阻塞。
- `tht`：直插件手焊/后焊；同样受 0402/0201 手焊策略约束（按 `package` 与 `footprint` 文本判断）。
- `dnp`：不装配；不要求 `stock`、`smt_class`、`lcsc`，也不计入装配数量。

库存状态：

- `in_stock` / `low` / `out_of_stock`：必须带有效 `checked_at`（`YYYY-MM-DD`）；`out_of_stock` 阻塞，`low` 告警。
- `unchecked`：只告警；G6 前必须补实际查询日期。
- 脚本不联网，`checked_at` 只证明“何时查过”，不证明现在仍有货。

运行方式与退出码：

```powershell
python scripts/bom_check.py parts.json
python scripts/bom_check.py parts.json --strict > bom-check.json
```

- `0`：没有 blocking；`1`：存在 blocking；`2`：输入无效（文件不可读、JSON 坏、schema 不符、空 `parts`）。
- 输出恒为一个 JSON 对象（`--json` 为默认行为）；`status` ∈ `pass/needs_review/invalid_input`；`--strict` 把 warning 提升为 blocking 并标记 `promoted`。
- 报告字段：`counts`（`parts`/`designators`/`assembly_designators`/`dnp_designators`/`smt_designators`/`hand_designators`/`tht_designators`/`blocking`/`warning`/`promoted`）、`assembly`（`smt`/`hand`/`tht`/`dnp` 的位号清单）、`findings`、`not_checked`。
- finding 字段为 `level`（`blocking`/`warning`）、`code`、`where`、`message`。
- 与 `gate_check.py` 的分工：G6 对 `BOM.csv` 的缺 MPN/厂家只给 advisory 警告；`bom_check.py` 对 `parts.json` 的缺 MPN/厂家直接 blocking，因为这是下单前的选料台账。两者口径不同是有意的，不是互相削弱。
- 脚本只做字段级核对。实际库存/价格/MOQ、SMT 可贴、封装几何、替代料电气等价、DNP 与 CPL 一致性、原理图/PCB 一致性都列在报告的 `not_checked`，需人工证据。

## 6. 工程导出与恢复演练

```powershell
zhigou project export --out manufacturing\<project>-<rev>.epro2 --project-uuid <uuid>
Get-FileHash -Algorithm SHA256 manufacturing\<project>-<rev>.epro2
python -c "import zipfile; print(zipfile.ZipFile(r'manufacturing\<project>-<rev>.epro2').testzip())"
```

恢复演练步骤：

1. 把 `.epro2` 复制到另一个目录，保留原件不动。
2. 在 EDA 中导入/打开副本。
3. 核对：工程名与板版本、原理图页数与标题栏、PCB 层数与板框、器件数与位号、DRC 可运行、BOM 行数。
4. 记录结果与证据路径；完成且一致才写 `restore_verified: true`。
5. `restoreVerified: false` 或缺失（CLI 回执字段）对应 `design-state.json` 的 `restore_verified: false`，是 G6 的不可豁免阻塞。

状态片段（字段名与契约一致）：

```json
"manufacturing": {
  "artifacts": [
    {"role": "gerber", "path": "manufacturing/gerber.zip"},
    {"role": "drill", "path": "manufacturing/drill.zip"},
    {"role": "cpl", "path": "manufacturing/cpl.csv"},
    {"role": "bom", "path": "BOM.csv"}
  ],
  "profile": {"status": "pass", "file": "docs/manufacturing-profile.md"},
  "project_export": {"path": "manufacturing/temp-alarm-rev0.epro2", "sha256": "<sha256>", "restore_verified": true},
  "test_plan": {"path": "docs/test-plan.md", "status": "pass"}
}
```

测试计划可基于 [verification.md](verification.md) 生成本项目的 `docs/test-plan.md`；`path` 指向项目内实际文件。

注意两个名字：`design-state.json` 用 `restore_verified`；`zhigou project export` 的 JSON 回执用 `restoreVerified`。二者不能混写。

## 7. 测试计划与“未证明”清单

实物测试按 [verification.md](verification.md) 写；G6 只检查测试计划存在与状态，不证明测试已执行。交付说明必须区分：

- 未打样/未贴片：装配、极性、焊接质量、机械配合均未验证。
- Gerber/钻孔/CPL 未经板厂 DFM 确认；阻抗未实测。
- 库存/价格/MOQ 只是查询时点记录，脚本与回执都不能保证仍然有效。
- `bom_check.py` 通过不代表封装几何、替代料电气等价或原理图连接正确。
- `.epro2` 恢复演练证明工程可重开，不证明制造文件与当前板版本一致；必须靠 manifest 哈希对齐。
- DRC 0 与网表 0 不代表实物功能正常。

## 8. G6 退出对照

检查名以最终 `gate_check.py` 输出为准；本表按契约的 G6 退出项列出对应证据。

| `gate_check.py` 检查 | 通过需要 | 证据 |
|---|---|---|
| `gerber_files` | 存在 Gerber 文件或在 state 登记 | `manufacturing.artifacts` role=`gerber` |
| `drill_files` | 钻孔文件 | role=`drill` |
| `cpl_files` | 坐标/贴片文件 | role=`cpl` |
| `bom_c_numbers` | 可解析 BOM，且每行有 C 号 | `BOM.csv` |
| `manufacturing_profile` | 工艺/层叠/铜厚/阻焊/表面处理已记录 | `manufacturing.profile` |
| `epro2_integrity` | `.epro2` 存在且 zip 完整 | `manufacturing.project_export` |
| `epro2_restore` | 恢复演练完成 | `restore_verified: true` |
| `sourcing_check` | 库存与 SMT 核对日期齐全 | `sourcing.stock_checked_at` / `smt_checked_at` |
| `test_plan` | 实物测试计划存在 | `manufacturing.test_plan` |

按契约，Gerber/钻孔/CPL、BOM C 号、工艺档案、恢复演练与库存/SMT 核对日期不可豁免；缺证据就是 `BLOCKED`，不能用“先下单再说”代替，只有测试计划等明确允许的项才能带理由豁免。
