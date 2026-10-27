# 交付审计格式支持与边界（format-support）v0.1

> 性质：能力/边界说明，不是规范译文，也不是“已通过”声明。与 `contract.md` §7 对齐；
> `contract.md` 冻结接口，本文件只描述**当前实现**实际做了什么、没做什么、证据在哪。
> 核对日期：2026-10-27。路径均相对本仓库根目录：
> 实现 `design-hardware/scripts/delivery_audit/`；夹具 `benchmarks/delivery-audit/fixtures/`；
> 真实样本 `benchmarks/delivery-audit/real-sample/`（来源与哈希见其 `SOURCE.md`）；
> 来源与许可见 `docs/parallel-delivery-audit/source-register.md`（`FMT-Sxx`/`MFG-Sxx`）。
> 本 worker 只写本文件、`source-register.md` 与 `real-sample/**`；**未修改任何代码/测试/夹具**。

## 1. 状态词表

| 状态 | 含义（本文件用法） |
|---|---|
| `supported` | 实现对这类输入有明确分支/状态机，并按契约给出 `pass` 或“可解释的 pass 路径”。**不等于**任意厂商文件都能通过，也不等于语义完整。 |
| `unknown-incomplete`（显式 unknown） | 实现**识别**到该特性但明确不支持：产生 `status=unknown` 的 finding，整体报告 `incomplete`（退出码 3）；几何/边界明确不声明。 |
| `fail` | 实现对该输入产生 `status=fail` 的 finding（阻断/重大时整体 `fail`，退出码 1）。可能是内容确实有问题，也可能是实现边界（§11 逐条标注）。 |
| `not checked` | 契约/实现**没有**做这项检查；报告不因它判 fail，但也**不得**当成通过。 |
| `NOT RUN` | 本模块没有该能力的实际执行证据（环境/样本/入口未跑），不写成已验证。 |

说明：解析器返回的 `status` 是“有 fail → fail；否则有 unknown → unknown；否则 pass”，见 `model.py`/
`gerber.py::_result`/`bom.py::aggregate_status`。`capability` 字段是**静态能力清单**，不是本次执行的
结果；判断一次解析的边界要看 `findings`/`facts.unsupported`。

## 2. 运行环境与 Python 版本（如实）

| 项 | 事实 | 状态 |
|---|---|---|
| 本地解释器 | `python --version` = **Python 3.13.15**（CPython，Windows x64） | 已实测 |
| 依赖 | 仅标准库（`re/csv/io/codecs/math/hashlib/zipfile/os/pathlib` 等）；无第三方依赖 | 源码可核对 |
| CI 矩阵 | `.github/workflows/validate.yml`：`matrix.python = ['3.10','3.13']`，步骤 `python3 -m unittest discover -s tests -v`；另 `release-v1-hotfix.yml`/`skill-updater.yml` 也固定 3.10 | 仓库文件可核对 |
| Python 3.10 本地执行 | **NOT RUN**：本机 `py -0p` 只列出 3.13，未安装 3.10；未使用容器/远程 3.10 | `NOT RUN` |
| 3.10 兼容结论 | 只由“源码审查 + CI 矩阵声明”支撑（契约 §11 要求 3.10 兼容）；**不是**本地实测结论 | 部分证据 |
| 测试套件 | `tests/delivery_audit/` 存在 `test_core/test_scan/test_gerber_drill/test_bom_cpl/test_reproducibility/test_scenarios`；并行开发中，本文件**不**把“测试通过数”当格式能力证据 | 不作为证据 |
| delivery-audit CLI | 本 worker **未运行** CLI；§10 只记录 parser 级只读调用 | `NOT RUN`（CLI） |

> 复核：2026-10-27 并行实现修复后，本 worker 重跑
> `python -m unittest discover -s tests -p test_gerber_drill.py` → **63 tests OK**（只证明该子集可发现/执行；
> 全量套件与通过数不写入本文件）。修复前的真实样本回放结果与修复后复核见 §10。

## 3. 模块与上限总览

| 模块/入口 | 契约 | 输入 | 默认资源上限 | 备注 |
|---|---|---|---|---|
| `formats.detect_kind/infer_role` | §6 | 字节 + 文件名 | — | 内容优先；扩展名只作线索；不解析、不判 pass |
| `gerber.parse_gerber` | §7.1 | `bytes` | `max_objects=2_000_000`（`max_tokens` 别名，取最小） | 超限 → `gerber.limit_objects` unknown，不静默截断 |
| `drill.parse_drill` | §7.2 | `bytes` | `max_objects=2_000_000` | 超限 → `drill.limit_objects` unknown |
| `bom.parse_bom` | §7.3 | `bytes` | `max_rows=100_000` | 超限 → `bom.limit_rows` unknown，后续行不审计 |
| `cpl.parse_cpl` | §7.4 | `bytes` | `max_rows=100_000` | 超限 → `cpl.limit_rows` unknown |
| `assembly.audit_assembly` | §7.5 | 两个 parse 结果 + 声明 + profile | — | 任一解析 fail/超限则跳过交叉检查 |
| `layers.audit_outline` | 契约 §3/§7 配套 | 角色表 + parse 结果 | 容差 `0.01 mm` | 只用线性闭合轮廓 |
| `scan.scan_input` | §5 | 目录/ZIP/文件 | §4 的 limits | 不跟随符号链接；不写文件；不联网 |

内容摘要（冻结算法）见 §9；所有解析器**对内容问题不抛异常**，只对参数/选项编程错误抛 `ValueError`。

## 4. Gerber（RS-274X/X2）能力矩阵

依据：`design-hardware/scripts/delivery_audit/gerber.py`（单遍状态机 + `%...%` 块/`*` 词命令切分）、
契约 §7.1、Ucamco *Gerber Layer Format Specification* Rev 2026.05（`FMT-S01`；分节引用为其 PDF 页码）。
“证据”列的 `§` 是规范节号，`gerber.py::函数` 是实现位置。

| 特性 | 状态 | 解析器行为（实际） | 证据/依据 |
|---|---|---|---|
| 空文件 | fail | `gerber.file_empty`（blocking）；返回空 facts | 契约 §7.1；`parse_gerber` |
| 编码 | supported / fail | 严格 UTF-8 解码（允许 UTF-8 BOM，fact `encoding=utf-8-sig`）；失败 → `gerber.encoding_invalid`（blocking），不做替换解码。**注意**：现行规范 §3.1 允许 UTF-8（用户属性可含非 ASCII），旧工具链的 Latin-1 字节会 fail | §3.1；`parse_gerber` |
| BOM/空白/大小写 | supported（宽容） | 命令间任意空白（含 CR/LF）忽略；命令按大写比较（小写也接受，规范要求大写） | §3.1；`_iter_blocks`/`_handle_word` |
| `G04` 注释 | supported | 整条词命令跳过（内容不解释） | §4.1；`_COMMENT_WORD` |
| `%MOMM` / `%MOIN` | supported | 设置 `units=mm/inch`；重复相同无害；不同 → `gerber.units_mixed` fail；值非法（非 MM/IN）→ `gerber.units_missing` fail blocking；完全缺失 → `gerber.units_missing` fail | §4.2.1；`_parse_units` |
| 旧式 `G70`/`G71` 单位 | supported | 等价于 MOIN/MOMM | §8（弃用章节）；`_handle_gcode` |
| `%FS` 格式声明 | supported（含旧格式） | 接受 `L`/`T` + 仅 `A`；X/Y 各自整数/小数位（实现为 1 位数字、>0）；缺失 → `gerber.format_missing` fail；非法/冲突 → `gerber.format_invalid` fail | §4.2.2；`_parse_format` |
| `%FS` 现行规范严格度 | `not checked`（宽容读取） | 现行 2026.05 要求 `LA` 且小数位必须 =6；实现接受 2.4 等旧格式（真实 Eagle 样本即为 2.4）且接受 `T`。**这是有意兼容旧文件，不是规范符合声明** | §4.2.2（“Previous format versions allowed other values”） |
| 增量坐标（`%FSI`/`G91`） | unknown-incomplete | `gerber.unsupported.incremental`；坐标按增量解释（`pos+delta`），`contours_exact/extent.exact=false` | §8；`_parse_format`/`_handle_gcode` |
| 坐标带小数点 | supported（宽容） | 有 `.` 时按声明单位直接取浮点值（现行规范坐标为整数；实现接受历史方言） | §4.8 操作参数；`_scale_value` |
| 整数坐标零省略 | supported | `L`：不填充；`T`：右侧补 0 到“整数位+小数位”；超过声明宽度 → `gerber.coordinate_invalid` fail | §4.2.2；`_scale_value` |
| `%ADD` 光圈定义 | supported | 解析 `ADD<code><template>[,<params>]`；`R/O/P` 参数用 `X` 分隔；参数非法 → `gerber.aperture_undefined` fail | §4.3；`_define_aperture` |
| C/R/O/P 模板 | supported | `C`：直径[，孔径]；`R/O`：宽×高[，孔径]；`P`：外径、顶点数[，旋转[，孔径]]；均记录 mm 尺寸与 `supported` | §4.4；`_resolve_standard_aperture` |
| 零尺寸 C 光圈 | supported（2026-10-27 修复） | `C` 直径 ≥0；`0` 作为零宽光圈接受（不扩边），负值/缺失仍 `gerber.aperture_undefined` fail。规范 §4.3.1（PDF p.51）允许零直径 C 光圈用于板框/定位信息 | §4.3.1；`_resolve_standard_aperture` |
| P 顶点数上限 | `not checked`（宽容） | 只要求整数且 ≥3；未强制规范上限 12 | §4.4.5 |
| 光圈孔径是否“严格位于光圈内” | `not checked` | 只校验孔径有限且 ≥0，不校验是否严格适配 | §4.4.6 |
| 重复定义同一 D 码 | fail | `gerber.aperture_redefined` fail（规范：一经分配不可重定义） | §4.3；`_define_aperture` |
| 引用未定义 D 码 | fail | 使用后未定义 → `gerber.aperture_undefined` fail；定义非法 → fail | §4.6；`_finalize` |
| 画/闪时无当前光圈 | fail | `gerber.aperture_missing`（全文件无光圈）或 `gerber.draw_without_aperture`（未选刀） | §4.8 |
| `G01` 线性绘线 | supported | `D01` 生成线段，更新当前点与轮廓点列 | §4.7.1；`_handle_gcode`/`_apply_operation` |
| `D02` 移动 / `D03` 闪光 | supported | `D02` 不产生图元；`D03` 以光圈半尺寸扩边；均更新当前点 | §4.8；同上 |
| 模态 D 码、省略轴 | supported | 省略 X/Y 取当前点；无操作码但有坐标 → `gerber.coordinate_invalid` fail（仍跟踪点，不伪造图元） | §4.8 |
| `G54`/`G55` | supported | 忽略（旧式选刀前缀） | §8 |
| `G02`/`G03` 弧、`I/J/K` | unknown-incomplete | `gerber.unsupported.arc`；计数 `arcs`；`contours_exact/extent.exact=false` | §4.7.2；`_unsupported` |
| `G36/G37` region | unknown-incomplete | `gerber.unsupported.region`；计数 `regions`（G36 次数）；几何不声明 | §4.10 |
| `AM`/`AB` 宏 | unknown-incomplete | 任何 `%AM`/`%AB` 出现即 `gerber.unsupported.macro`（**即使宏未被引用**）；宏名记录、`macros` 计数；引用宏模板的 `%ADD` 记 `unsupported.macro` | §4.5/§4.11；`_handle_extended` |
| `%SR` step&repeat | unknown-incomplete | `gerber.unsupported.step_repeat` | §4.12 |
| `%LPC` 非默认极性 | unknown-incomplete | `gerber.unsupported.polarity`；`%LPD` 视为默认、无 finding | §4.9.2 |
| `%TF.FilePolarity,Negative` | unknown-incomplete | 记 `file_polarity` 并 `unsupported.polarity` | §5.6.4；`_parse_file_attribute` |
| `%LM/%LR/%LS` 图像变换 | unknown-incomplete | `gerber.unsupported.transform` | §4.9.3–4.9.5 |
| `%IPNEG` | unknown-incomplete | `gerber.unsupported.image_negative`；`%IPPOS` 记为普通元数据 | §8 |
| `%MI/%OF/%SF/%AS` | unknown-incomplete | `gerber.unsupported.image_parameter`（真实 Eagle 文件普遍含 `%OF`，所以真实文件通常至少是 unknown） | §8 |
| `%IN/%LN/%PF` 等名称元数据 | supported（忽略） | 不产生 finding，不影响几何 | §5 |
| 未知扩展命令 / 未知 D/G/M 码 / 不可识别词命令 | unknown-incomplete | `gerber.unsupported.extended_command` / `.dcode` / `.gcode` / `.mcode` / `.command`，并加入 `capability.unknown` | §3.3；`_handle_word` 等 |
| X2 `%TF.FileFunction` / `.FilePolarity` / `.Part` | supported（仅元数据） | 只保存字符串到 facts；**不校验取值合法性/层号自洽**（如 `Copper,L1,Top` 与声明层数的一致性由上层） | §5.6.2–5.6.4 |
| X2 `%TA/%TO/%TD` 及其他 `%TF` | supported（忽略） | 仅当元数据，不改变几何；无 finding | §5.3–5.5 |
| `M00/M01` 程序停 | supported（继续解析） | 不结束文件 | §4.13（M02 才是结束） |
| `M02` 结束 | supported | 必须最后一条；缺失 → `gerber.end_missing` fail blocking；`M02` 后仍有非空白 → `gerber.unsupported.trailing_data` unknown | §4.13；`run`/`_finalize` |
| 截断（块未闭合） | fail | `gerber.truncated`（blocking）；不再按“缺 M02/FS/MO”重复判 | §4.13 |
| 无任何图元 | fail | `gerber.no_graphical_objects` | 实现策略（契约 §7.1） |
| 对象预算 | unknown-incomplete | 超过 `max_objects` → `gerber.limit_objects`（actual/evidence 带限制值），**不继续声称完整** | 契约 §11；`_limit_reached` |
| `facts.apertures` | supported | 按 D 码排序；`width_mm/height_mm/hole_mm`（受单位换算）；`supported` + `unsupported_reason` | `_aperture_fact` |
| `facts.graphical_objects/draws/flashes/regions/arcs/macros` | supported | 计数；`graphical_objects` 是画/闪操作总数（**含**弧线 draw），`draws` 只计线性 `D01`，`arcs` 单独计数；`regions` 计 G36 次数 | `_apply_operation` |
| `facts.contours` / `contours_exact` | supported（有限） | 仅线性 `D01` 链；闭合判定 `abs(Δ) ≤ 1e-6`（**原始文件单位**，不是 mm）；只有无弧线/region/宏/变换且 units/format 可用时 `contours_exact=true` | `_finish_contour`/`_build_facts` |
| `facts.path_extent` | supported | 所有坐标（含 move/flash/画线端点）的原始 bbox，换算 mm；无单位/不可缩放时 `None` | `_include_path` |
| `facts.extent` | supported | 路径 bbox 再按光圈扩边：flash 用 `half_x/half_y`；draw/move 用 `max(half_x,half_y)`；`exact` + `basis` 明示是否保守 | `_expand`/`_build_facts` |
| `facts.end_of_file/encoding/errors/unsupported` | supported | `errors` 最多 200 条；`unsupported` 排序去重 | `_build_facts` |

## 5. 钻孔（Excellon 风味）能力矩阵

依据：`drill.py`、契约 §7.2、`FMT-S03`（XNC，唯一公开的 CAD→CAM NC 规范，但**不是** Excellon）、
`FMT-S04`（Excellon 原厂机床手册存档）、`FMT-S05`（历史脉络；CC BY-SA，仅链接）。
**重要**：Excellon 历史上是机床厂商私有格式，Excellon 公司已停止发布规范；本模块只支持一个**显式子集**，
不声称符合 Excellon 或 IPC-NC-349（详见 `FMT-S06`：IPC-NC-349 付费未读）。

| 特性 | 状态 | 解析器行为（实际） | 证据/依据 |
|---|---|---|---|
| 空文件 | fail | `drill.file_empty`（blocking） | 契约 §7.2 |
| 编码 | supported / fail | 严格 UTF-8（BOM 允许）；失败 → `drill.header_missing`（blocking，消息说明“header 读不了”），规则号复用 | `parse_drill` |
| `M48` 头位置 | supported（2026-10-27 修复） | `M48` 前的空行、`;` 注释、单独的 `%` rewind 行被容忍；`M48` 仍是必需项，缺失 → `drill.header_missing` fail。已实测 Eagle `%\nM48\n...` 可正常读入 | `_DrillState.run` |
| 头终止符 `%` / `M95` | supported | 记录 `header.terminated_by`；缺失 → `drill.truncated` fail blocking（读取提前返回） | `run` |
| `METRIC` / `INCH` | supported | 可带 `,TZ` / `,LZ` 后缀；`M71`/`M72` 也接受（头/体）；同值重复无害；冲突/非法后缀 → `drill.units_invalid` fail；缺失 → `drill.units_missing` fail | `_set_units` |
| 头内其他参数（VER/DETECT/ICI/FMAT/R,S,/TCST/ATC/FILE_FORMAT/TYPE/UNITS 等） | supported（部分忽略） | 识别前缀后当注释解析（可提供 FORMAT/单位线索）；其余行记入 `header.unknown` + `capability.unknown`，**不产生 finding** | `_header_line` |
| 工具表 `TnCd` | supported | 头/体均可定义；直径 >0 有限；非正/非数 → `drill.tool_invalid` fail；同码同径视为重复但容忍，同码异径 → fail | `_define_tool` |
| 选刀 `T`、`T0` | supported | `T0` 取消当前刀；引用未定义刀 → `drill.tool_undefined` fail；未选刀出孔 → fail | `_body_line`/`_add_hole` |
| 显式小数坐标 | supported | 有 `.` 时按文件单位取浮点；非数/非有限 → `drill.coordinate_invalid` fail | `_scale_coordinate` |
| 整数坐标（定点） | supported（条件）| 必须同时从头拿到 **digit format**（如 `;FORMAT={2:4/...}`）与 **零抑制**（`,TZ`/`,LZ`）才解释；缺任一 → `drill.coordinate_unknown_format` unknown（**不猜**）；超声明宽度 → fail | 契约 §7.2；`_scale_coordinate` |
| 模态轴 | supported | 一行只给 X 或只给 Y 时沿用上一孔坐标；无模态可沿用 → `drill.coordinate_invalid` fail | `_add_hole` |
| `G90` 绝对 / `G05` 钻孔模式 | supported | 记录状态；`G91` → `drill.unsupported.incremental` unknown，`geometry_exact=false` | `_handle_gcode` |
| `M30/M00/M02` 结束 | supported | 结束解析；缺失 → `drill.end_missing` fail blocking | `_finalize` |
| `G85` 槽 | unknown-incomplete | `drill.unsupported.slot`，`slots` 计数；不计算槽几何 | 契约 §7.2 |
| `M15/M16/M17`、`G00/G01` 铣 | unknown-incomplete | `drill.unsupported.routing`，`routing` 计数 | 契约 §7.2 |
| 重复孔 `Rnn` | unknown-incomplete | `drill.unsupported.repeat` | 契约 §7.2 |
| 未知 body 命令/字母/头参数 | unknown-incomplete | `drill.unsupported.command` + `capability.unknown` | `_body_line` |
| 机床参数（如 `T1C.04F200S65` 的 F/S 后缀） | not checked（不识别） | 头工具正则要求 `TnC<number>` 行结束，带 F/S 的工具栏不建立 → 可能进一步触发 `tool_table_missing`/`tool_undefined` fail；不解析进给/转速 | `_TOOL_DEF` |
| `facts.extent` | supported | 孔中心 ± 刀半径，mm；`exact` 需无 unknown 几何、单位有效、非增量；单位缺失 → `None` | `_add_hole`/`_build_facts` |
| `facts.tools/undefined_tools/duplicate_tools/holes_without_tool` | supported | 直径 mm、`defined/used/duplicate` | `_build_facts` |
| XNC 正式支持 | `NOT RUN`（不支持） | XNC 的十进制坐标可被“小数坐标”路径读入，但 `G00` 铣、`M15/M16`、`G02/G03+A`、属性段均不在子集；**不得**声称支持 XNC | `FMT-S03` §2.7/§3；`drill.py` `_UNSUPPORTED` |
| 对象预算 | unknown-incomplete | `drill.limit_objects` | `_limit_reached` |

## 6. BOM（CSV）能力矩阵

依据：`bom.py`、契约 §7.3、`MFG-S05`（嘉立创 BOM 规则，仅用于**限定字段范围**）。

| 特性 | 状态 | 解析器行为（实际） | 证据/依据 |
|---|---|---|---|
| 空/纯空白 | fail | `bom.empty`（blocking） | 契约 §7.3 |
| 编码 | supported / fail | 默认 `utf-8-sig`；`options['encoding']` 经 `codecs.lookup` 校验（未知 codec 是调用方错误 → `ValueError`）；解码失败 → `bom.encoding_unspecified` fail（**不使用** `errors='replace'`） | `resolve_encoding`/`decode_bytes` |
| xls/xlsx | not checked（且会 fail） | 二进制 xlsx 按文本解码失败 → `bom.encoding_unspecified` fail；**不解析表格**。嘉立创支持 xlsx，但本审计契约只做 CSV | 契约 §7.3；`MFG-S05` §1 |
| 分隔符 | supported | `options['delimiter']` 优先；否则按首个非空行在 `, ; TAB` 中确定性嗅探（引号内不计数）；平局 → 用逗号 + `bom.delimiter_ambiguous` unknown | `resolve_delimiter`/`sniff_delimiter` |
| 引号/嵌入换行 | supported | 标准 `csv` 模块；`csv.Error` → `bom.row_invalid` fail（读取中断，后续行不可靠） | `parse_bom` |
| 表头列别名 | supported | 大小写/空格/下划线/连字符/括号不敏感；位号 `designator(s)/ref(s)/reference/位号`；数量 `quantity/qty/数量`；值 `value/comment/值`；封装 `footprint/package/封装`；`mpn/manufacturer part number/型号`；`manufacturer/厂商`；`lcsc/supplier part/C号`；`dnp/do not populate/不贴`；装配 `assembly/装配`；面别 `side/layer/面`。同字段多列：第一个生效，其余记 `ignored_columns`；不识别列记 `unrecognized_columns` | 契约 §7.3；`_BOM_ALIASES` |
| 位号列缺失 | fail | `bom.no_designator_column`（blocking） | 同上 |
| 位号单元格 | supported / fail | 逗号/分号/空白分隔；token 须匹配 `[A-Za-z][A-Za-z0-9_]*`；空 → `bom.designator_missing_invalid` fail；跨行重复 → `bom.designator_duplicate` fail | `parse_designator_cell` |
| 范围位号 | supported（同前缀、升序） | `R1-R3` / `R1-3` 展开，保留前导零宽度；降序/跨前缀/其他写法 → `bom.designator_range_invalid` fail；单次展开上限 10,000；厂商复杂语法不猜 | 契约 §7.3 |
| 数量 | supported / fail | 必须是正整数；非法 → `bom.quantity_invalid` fail；与展开后的位号数不一致 → `bom.quantity_mismatch` fail | `parse_bom` |
| 数量列缺失 | fail（默认必需） | 默认 `required_fields=("designator","quantity")`；声明可用 `bom.required_fields` 覆盖；缺列/必填值为空 → `bom.required_field_missing` fail | 契约 §3/§7.3 |
| DNP | supported / fail | 只接受 `1/0/true/false/yes/no/y/n`（大小写不敏感）；空=非 DNP；其他 → `bom.dnp_invalid` fail | `DNP_TRUE/DNP_FALSE` |
| 装配类型 | supported / partial | `smt/tht/hand/mechanical/dnp`（大小写不敏感）；其他值 → `bom.assembly_unknown` unknown（minor）；缺省计入 `counts.assembly.missing` | `ASSEMBLY_TYPES` |
| 面别列 | supported（仅记录） | `side/layer/面` 仅保存文本，不在 BOM 内校验；面别矛盾在 `assembly.py` 处理 | `facts.rows[].side` |
| 行数上限 | unknown-incomplete | 超 `max_rows` → `bom.limit_rows` unknown，后续行未审计 | `resolve_limit` |
| `facts` | supported | `encoding/delimiter/header/header_mapping/required_fields/rows/counts`；`counts` 含 `assembly` 分类与 `dnp_designators` | `_build_result` |

**范围说明**：嘉立创 `MFG-S05` 的**必需**列是 Comment/Designator/Footprint（Quantity 是推荐），
本审计默认必需列是 Designator/Quantity（契约 §3 默认）——这不是“JLC 合规检查”，而是可配置的交付
一致性检查。要做 JLC 字段合规，应在声明里显式设置 `bom.required_fields`（见 §11-8）。

## 7. CPL（pick-and-place CSV）能力矩阵

依据：`cpl.py`、契约 §7.4、`MFG-S05`/`MFG-S06`（嘉立创坐标文件规则，仅限定字段范围）。

| 特性 | 状态 | 解析器行为（实际） | 证据/依据 |
|---|---|---|---|
| 空/纯空白 | fail | `cpl.empty`（blocking） | 契约 §7.4 |
| 编码/分隔符/CSV 结构 | supported / fail | 与 BOM 同一套严格解码与分隔符逻辑（默认 utf-8-sig；平局→逗号+unknown）；CSV 结构错误 → `cpl.required_field_missing` fail（契约 §7.4 无专用规则，实现用该规则并在 evidence 记录 `csv_error`） | `parse_cpl` |
| 位号列/值 | supported / fail | 别名同 BOM（含 `位号`）；缺列 → `cpl.no_designator_column` fail blocking；空/非法 token → `cpl.designator_missing_invalid` fail；重复 → `cpl.designator_duplicate` fail | `_CPL_ALIASES` |
| X/Y 列 | supported / fail | 默认必需；缺列 → `cpl.required_field_missing` fail；值严格解析：空/`NaN`/`Infinity`/`true`/`false`/畸形 → `cpl.position_not_numeric` fail；允许指数形式；必须有限 | `parse_number` |
| 单位来源与优先级 | supported / fail | 行内 `unit` 列词 > 表头文字（`X(mm)`/`Mid X (mil)` 等） > `options['unit']`（声明，`unit_source='declared'`）；支持 `mm/mil/inch`；**无单位 → `cpl.unit_missing` fail**（全行缺失为 blocking，部分为 major），绝不猜 | `_resolve_row_unit`/`_resolve_header_unit` |
| 已知但不支持的单位 | fail | `um/µm/cm` 被识别为“已知不支持”：表头 → `cpl.unit_missing` blocking；行内 → `cpl.position_unit_unknown` fail | `_UNIT_WORDS` |
| 面别 | supported / fail | 缺列 → `cpl.side_missing` fail；值只接受 `top/bottom/T/B/back/front`（大小写不敏感），空/未知 → `cpl.side_unknown` fail | `_SIDE_MAP` |
| 旋转 | supported / fail | 缺列 → `cpl.rotation_not_numeric` fail；非有限/非数 → fail；保留原值 `rotation`，另给 `rotation_norm = rotation % 360`；**不做**“顶/底旋转方向/偏移”解释 | 契约 §7.4 |
| 底面镜像/旋转偏移/坐标变换 | `NOT RUN`（不应用） | capability 明确 `bottom_side_mirror_transform`/`rotation_offset_application`/`coordinate_transform` 不支持；坐标按导出原值比较，不转换 | `CPL_CAPABILITY` |
| 行数上限 | unknown-incomplete | `cpl.limit_rows` unknown | `resolve_limit` |
| `facts` | supported | `rows[]` 含 `line/designator/x/y/unit/x_mm/y_mm/side/rotation/rotation_norm/rotation_raw`；`units/unit_source/counts` | `_build_result` |

## 8. BOM/CPL 交叉检查（`assembly.py`，契约 §7.5）

| 检查 | 状态 | 行为 | 规则号 |
|---|---|---|---|
| 需要贴装的 BOM 位号必须在 CPL | supported | 默认 `assembly=smt`；装配类型缺失/未知时按 smt 处理但记 unknown；缺 → fail | `assembly.cpl_missing_designator` |
| CPL 位号必须在 BOM | supported | 多出 → fail | `assembly.cpl_extra_designator` |
| DNP 策略 | supported | `policies.dnp_in_cpl="forbidden"` 时 DNP 位号出现在 CPL → fail；`allowed` → pass/info | `assembly.dnp_in_cpl` |
| THT/机械件策略 | supported | 策略 false 时不要求 CPL；出现在 CPL 记 info | `assembly.tht_in_cpl`/`assembly.mechanical_in_cpl`（动态规则号，见 §11-9） |
| 面别一致性 | supported | 仅两侧都已知时比较；矛盾 → fail；一侧已知另一侧未知 → unknown | `assembly.side_conflict` |
| 装配字段缺失 | supported | BOM 无装配列/值 → unknown（不单独判 fail） | `assembly.assembly_field_missing` |
| 数量残差 | supported | 先排除已解释的缺/多位号与策略例外，仍有残差 → unknown | `assembly.count_mismatch` |
| 解析不可用 | supported | 任一 parse fail/超限 → 跳过交叉，报告并 `facts.comparisons.performed=false`，不判绿 | `assembly.bom_unusable`/`assembly.cpl_unusable` |
| 电气/器件等价、坐标/旋转一致性 | `NOT RUN`（capability 明确不支持） | 不比较 MPN/替代料/电气等价；不比较 CPL 坐标是否与 Gerber 焊盘一致 | — |

## 9. 板框/边界与内容哈希

### 9.1 板框（`layers.audit_outline`）

| 项 | 状态 | 行为 |
|---|---|---|
| 必需角色 `board_profile`（仅 `pcb-fabrication`） | supported | 缺 → `outline.missing` fail blocking |
| profile 解析失败 | supported（unknown） | `outline.unverified_geometry` unknown，不判“闭合/包含” |
| 仅线性闭合轮廓 | supported（有限） | 要求 `facts.contours_exact=true` 且至少一个轮廓；含弧线/region/宏/变换 → `outline.unverified_geometry` unknown |
| 未闭合轮廓 | supported | 任一轮廓未闭合 → `outline.not_closed` fail blocking（不拿 bbox 冒充） |
| 板框 bbox | supported | 对所有线性轮廓点取 bbox（轮廓**中心线**，与规范 §6.5“非零光圈时中心线代表 profile”一致） |
| 铜层越界 | supported | `extent.exact=true` 且越界 → `outline.copper_outside` fail blocking；extent 不精确 → `outline.extent_inexact` unknown |
| 钻孔越界 | supported | `outline.drill_outside` fail；钻孔 extent 不可用 → `outline.drill_extent_unknown` unknown |
| 容差 | supported | `OUTLINE_TOLERANCE_MM = 0.01`（±10 µm） |
| 声明允许外部对象 | supported | `board.exterior_allow_objects=true` → `outline.exterior_objects_declared` info/not_applicable，不判 fail |
| 铜到板边间距、环宽、最小线宽、cutout 语义 | `not checked` | bbox 包含性之外不做任何 DFM/几何间距判断 |

### 9.2 内容哈希与 provenance（契约 §4）

| 项 | 状态 | 行为 |
|---|---|---|
| 文件条目哈希 | supported | 每文件 `sha256`（原始字节）+ 大小；ZIP 另记容器 `input_sha256` |
| 内容摘要（冻结算法） | supported | `sha256(b"delivery-content/v1\n" + 按 (path.casefold(), path) 排序的 "sha256hex\tsize\tpathutf8\n")`；**不含** mtime/容器元数据/生成时间；`scan.PackageSource.content_digest` |
| manifest provenance | supported | `source="observed"`、`source_binding="none"`，statement 明示“不证明同一 EDA revision/可制造” |
| 声明哈希比对 | supported | `declarations.files[].sha256` 与实际不符 → `provenance.file_hash_mismatch` fail；`content_manifest` 不符 → fail；`touch` 不改善任何状态 |
| `real_eda` | `NOT RUN`（恒定） | 报告 `restrictions[]` 恒含 `real_eda: NOT RUN`；本模块不调用 EDA/Connector/daemon |
| 同一 EDA revision 证明 | `NOT RUN`（明确不做） | 只能给 observed/声明级 provenance；不能证明“文件来自同一导出会话/设计版本” |

## 10. 真实样本只读回放（修复后复核；证据，不是 CLI）

样本与逐文件哈希见 `benchmarks/delivery-audit/real-sample/SOURCE.md`。2026-10-27 并行实现修复后，用
`gerber.parse_gerber` / `drill.parse_drill` 在**只读**下重跑（**未**运行 CLI，**未**修改样本）：

| 文件 | 状态 | 主要 findings / facts |
|---|---|---|
| 5 个含 `%ADD10C,0.0000` 的 Gerber（top/bottom copper、两 silk、outline） | unknown | `gerber.unsupported.image_parameter:unknown`（`%OF`）、`gerber.unsupported.macro:unknown`（`%AMOC8`）；零尺寸 C 光圈已正常接受（不再 fail）；`contours_exact=false` |
| `top_mask.GTS` / `bottom_mask.GBS` | unknown | 同上两项 unknown（无零尺寸 C 光圈项） |
| `ncdrill.DRD` | unknown | `drill.coordinate_unknown_format:unknown`；读出 **5 把刀 / 36 孔 / inch**；整数坐标无 digit format → extent 不计算（符合契约“不猜”） |

**修复前后（同一样本、只读对比）**：首次回放（修复前）在 5 个 Gerber 上得到
`gerber.aperture_undefined:fail`（零尺寸 C 光圈被拒），在钻孔上得到 `drill.header_missing:fail`
（Eagle 以 `%` 行开头，`M48` 不是第一条非注释行）。这两个问题已由实现负责人于 2026-10-27 修复
（代码注释已引用 §4.3.1 与“Eagle exports start with `%`”）；复跑后对应 fail 消失，只剩契约明确声明的
unknown。该过程与 `report.md` §8 的修复记录一致；基准 28 的期望已随之重新冻结。
`source-register.md` §4 保留该历史记录。

## 11. 已知差异与待裁决（只报告；本 worker 未改代码）

> 1、2 是由真实样本暴露并**已于 2026-10-27 修复**的问题，保留为历史/回归记录；3–13 是仍需明确的
> 文档措辞、宽容读取或范围问题（不影响“显式 unknown”的保守性）。

| # | 差异/现象 | 规范依据 | 实现现状 | 影响 |
|---|---|---|---|---|
| 1 | 零尺寸 C 光圈 | Gerber 2026.05 §4.3.1：C 光圈直径可为 0，用于板框/定位信息 | **已修复**：`C` 允许直径 ≥0，`0` 作零宽光圈（不扩边）；负值/缺失仍 fail | 历史：修复前合法板框文件被判 fail（真实 Eagle 样本复现）；回归见 §10 |
| 2 | 钻孔文件首行 `%` | XNC §3.2 要求 M48 在 header 第一行；Excellon 方言常把 `%`（rewind stop）放在前面（`FMT-S04` 手册有 `%`/M95 两种头结束） | **已修复**：M48 前允许空行/`;` 注释/单独 `%`；复跑样本读出 5 刀 36 孔 | 历史：修复前真实 Eagle/KiCad 导出被判 `drill.header_missing` fail；回归见 §10 |
| 3 | 现行 FS 严格度 vs 旧文件 | 2026.05 要求 `LA` 且小数位=6；旧版本允许 2.4 等 | 实现宽容接受旧格式，`format` 记录声明值 | 不是 bug；但报告/文档不得把“能读”写成“符合 2026.05” |
| 4 | P 顶点上限 | 规范 3 ≤ n ≤ 12 整数 | 只校验整数且 ≥3 | 宽容读取，不判 fail；不影响 bbox 保守性（用外接圆） |
| 5 | 光圈孔径适配 | 规范：孔径必须严格位于光圈内 | 只校验非负/有限 | `not checked`；不影响本次审计结论，但别声称几何精确 |
| 6 | `drill.py` 文档标题/契约措辞“Excellon / RS-274X drill parser” | Gerber 规范 §6.6 建议钻孔/铣边用 Gerber（Gerber 钻孔文件是 `%FS/%MO/D03` 闪光，不是 M48 头） | 实现只解析 Excellon 风味（M48 头）；Gerber 格式的钻孔文件会被判 `header_missing` | 措辞易误解为“支持 RS-274X 钻孔”；建议澄清契约 §7.2/文档标题（实现负责人决定） |
| 7 | 轮廓闭合容差单位 | — | `abs(Δ) ≤ 1e-6` 是**原始文件单位**（inch 文件 = 25.4 nm，mm 文件 = 1 nm），与板框 0.01 mm 容差不同层级 | 不影响当前样本（Eagle 板框未闭合项未触发），但语义上应写明单位/换算 |
| 8 | BOM 默认必需列 vs 嘉立创必需列 | `MFG-S05` §2.1：Comment/Designator/Footprint 必需；Quantity 推荐 | 契约/实现默认 `designator+quantity` | 审计通过 ≠ 嘉立创可导入；需在声明里 `bom.required_fields` 显式加列，或文档明确“非 JLC 合规检查” |
| 9 | `assembly.tht_in_cpl` / `assembly.mechanical_in_cpl` | 契约 §7.5 规则清单未列这两条；§9 要求新增规则同步 `format-support.md`/`acceptance-matrix.md` | 实现动态生成这两个 pass/info 规则号 | 规则号登记缺口（文档同步问题，不是行为错误） |
| 10 | BOM 接受 `;` 作位号分隔符 | `MFG-S05` §2.7 明确禁止分号分隔（只允许英文逗号/空格） | 实现按 `[,;\s]+` 拆分（比 JLC 宽容） | 审计可 pass 而嘉立创可能拒收；属“审计范围比平台宽”，见 §11-8 同类说明 |
| 11 | 重复 `%MO` 同值 | 规范要求 MO 只出现一次 | 实现容忍重复同值 | 宽容读取，无 finding；不声称合规 |
| 12 | 坐标带小数点 | 现行规范坐标类型为整数 | 实现接受（历史方言） | 宽容读取；不影响单位/格式校验 |
| 13 | `gerber.units_missing` 规则号复用 | 契约 §7.1 规则表 | 非法 `%MO` 值也报 `units_missing`（消息说明值非法） | 规则号语义略混；报告仍可读 |

> 以上 1、2 已修复（保留为历史/回归记录）；3–7、10–13 属于“宽容读取/文档措辞”问题；8、9 属于范围/同步问题。
> 本文件只记录，**未改任何代码/测试/契约**。

## 12. 明确不声称（non-claims）

- **不做 DFM**：不做最小线宽/线距、环宽、孔到铜、铜到板边间距、阻焊桥、焊盘补偿等可制造性判断；
  板框检查只是“轮廓闭合 + bbox 包含性”。
- **不做阻抗/电气/信号完整性**：不计算阻抗、不检查网络、不做电气规则检查；`task B` 的电气意图审查是独立模块。
- **不做装配正确性**：不判断贴装方向/极性器件方向/旋转约定是否与实物一致；不应用底面镜像/旋转偏移；
  不比较 CPL 坐标与 Gerber 焊盘；不判断可贴性/物料替代/电气等价。
- **不证明真实 EDA**：不调用 EDA/Connector/daemon；不证明文件来自同一 EDA revision；`real_eda` 恒为 `NOT RUN`。
- **不证明制造/实物/备份恢复**：`pass_with_scope` 只表示“报告列明的适用检查通过”。
- **不是格式规范符合性认证**：不声称符合 Gerber 2026.05、Excellon、IPC-NC-349 或 XNC；只支持 §4–§8 列出的子集，
  其余显式 unknown/fail。Gerber 是 Ucamco 注册商标，本仓库不声称任何背书。
- **不运行未运行的东西**：本文件没有声称运行过 delivery-audit CLI；没有声称在 Python 3.10 上执行过；
  没有声称对真实 BOM/CPL 做过回放（`NOT RUN`，见 `real-sample/SOURCE.md` §7）。
- **不把 unknown 当绿**：任何 `unknown` 都使报告 `incomplete`（退出码 3），不会被压成 pass。

## 11. 集成后更新（Lead 记录，2026-10-27）

本文件 §2 的“delivery-audit CLI: NOT RUN”只描述资料负责人的取证边界：该负责人没有运行 CLI，
只做了 parser 级只读回放，这是正确的自我限制。集成完成后 Lead 已实际运行 CLI 与冻结基准：

- `python -m unittest discover -s tests/delivery_audit -p "test_*.py"` → 303 tests OK（1 skip，含 48 个对抗测试）。
- `python benchmarks/delivery-audit/run_benchmarks.py` → 28/28（27 合成 + 1 真实样例只读重放）；
  真实样例 case 28 的结果为 `incomplete`（exit 3），无 fail 规则，未声称可制造。
- 真实样例夹具现包含 `ncdrill.DRD`（8 个制造文件）；`SOURCE.md` 记录来源/许可/哈希。
- 契约措辞已同步：§7.2 钻孔明确为“Excellon/NC 钻带，不是 Gerber 图像格式”；
  §7.5 规则表补上 `assembly.tht_in_cpl` / `assembly.mechanical_in_cpl`。
- `formats.detect_kind` 已要求可信起始命令，`SOURCE.md` 等说明文档不会再被误判为 Gerber；
  文件名角色推断补齐 `top_mask`/`bottom_silk` 等词序（仍只是 `inferred`）。

因此，本文件的格式能力矩阵仍以 parser 级证据为准；CLI/集成结论以 `report.md`、`acceptance-matrix.md`
和 `benchmarks/delivery-audit/results/latest.json` 为准。两者都不改变“未知不判绿”的规则。

