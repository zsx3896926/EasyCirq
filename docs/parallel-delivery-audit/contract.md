# 交付审计（delivery audit）内部契约 v0.1

> 状态：冻结接口，供并行实现与审查使用。规则依据见 `format-support.md`、`source-register.md`。
> 基线：`9a951edc21481dc3ae91460acc11aa3e08a7be8a`（main），分支 `feat/parallel-delivery-audit`。
> 本文件只描述本模块内部契约；不修改任何共享入口、版本号或主交接。

## 1. 范围与非目标

本模块对**已经导出的交付目录或 ZIP**做独立、只读审计：文件安全与完整性、版本/来源自洽、有限
Gerber/钻孔结构、BOM/CPL 一致性与可追溯报告。输入是现成文件和来源声明；输出是有边界报告。

明确不做：

- 不导出、不重写、不修复任何制造文件；不生成 Gerber/CPL/BOM。
- 不调用 EDA/Connector/daemon，不联网读取输入引用的外部路径，不执行输入内任何内容。
- 不宣称板厂 DFM、阻抗、电气、可制造性、贴装、实物或备份恢复通过；`real_eda` 恒为 `NOT RUN`。
- 不把"清单由本工具生成"当成"文件来自同一 EDA revision"的证明。
- 不评估电路功能（任务 B 的电气意图审查是独立模块）。

## 2. 状态、严重级别、退出码

每条 finding：

| 字段 | 必填 | 说明 |
|---|---|---|
| `rule_id` | 是 | 稳定规则号，命名空间见 §9 |
| `status` | 是 | `pass` / `fail` / `unknown` / `not_applicable` |
| `severity` | 是 | `blocking` / `major` / `minor` / `info` |
| `message` | 是 | 面向用户，说明实际看到了什么 |
| `object` | 否 | 检查对象：层、位号、角色、路径 |
| `file` | 否 | 包内逻辑路径（POSIX 分隔，原始大小写） |
| `line` | 否 | 文本行号或 1 基记录号 |
| `actual` / `expected` / `unit` | 否 | 实际值、期望值、单位（只在有值且可比较时给） |
| `evidence` | 否 | JSON 可序列化证据（原始值、哈希、范围） |
| `suggestion` | 否 | 建议动作；**不会被执行** |

整体状态（`report.status`）：

| 状态 | 判定 | 退出码 |
|---|---|---|
| `fail` | 存在 `status=fail` 且 `severity∈{blocking,major}` 的 finding | 1 |
| `incomplete` | 无上述 fail，但存在 `status=unknown` 的 finding/检查项/必需覆盖缺口 | 3 |
| `pass_with_scope` | 所有适用检查 pass；仅剩 `not_applicable`/信息项 | 0 |
| `input_invalid` | 输入不能安全/无歧义读取（运行前异常或读取竞态） | 2 |

`inspect`：可读且安全 → 0；输入无效 → 2。`manifest`：成功 → 0；输入无效 → 2。
未知永不判绿；`pass_with_scope` 不表示制造通过，只表示报告列明的适用检查通过。

允许的 profile：`pcb-fabrication`、`smt-assembly`、`archive`。必需角色：

- `pcb-fabrication`：`copper_top`、`copper_bottom`、`board_profile`、`drill`；声明层数 >2 时，内层
  `copper_inner` 数量与索引必须齐全。
- `smt-assembly`：`bom`、`cpl`；不因缺 Gerber 判失败。
- `archive`：无制造必需项；缺 Gerber/BOM 只能是 `not_applicable` 或覆盖说明，不能判失败。

角色可选：`soldermask_*`、`silkscreen_*`、`paste_*`、`assembly_drawing`、`schematic_pdf`、
`native_project`、`layer_stack_doc`、`test_plan`、`readme`、`other`。可选角色缺失只进入覆盖清单。

## 3. 声明文件 `delivery-declarations/v1`

严格 JSON（重复键、NaN/Infinity、非对象根、未知顶层字段拒绝），UTF-8（允许 BOM）。路径必须是包内
POSIX 相对路径，禁止绝对路径、`..`、盘符、反斜杠；不允许引用包外文件。示例：

```json
{
  "schema": "delivery-declarations/v1",
  "project_id": "photo-led",
  "revision": "A",
  "source_snapshot": {
    "hash_algorithm": "sha256",
    "value": "…64 hex…",
    "source": "exporter_attested",
    "reference": "export session note"
  },
  "export_session": {
    "id": "session-1",
    "tool": "EasyEDA Pro",
    "tool_version": "2.x",
    "captured_at": "2026-10-27T12:00:00+08:00"
  },
  "content_manifest": {"sha256": "…content digest…", "source": "observed"},
  "files": [
    {"path": "gerber/GTL.gbr", "role": "copper_top", "sha256": "…", "source": "observed"},
    {"path": "gerber/GBL.gbr", "role": "copper_bottom"},
    {"path": "gerber/Profile.gbr", "role": "board_profile"},
    {"path": "gerber/drill.drl", "role": "drill"},
    {"path": "bom.csv", "role": "bom"},
    {"path": "cpl.csv", "role": "cpl"}
  ],
  "stackup": {"layers": 4, "copper_order": ["top", "inner1", "inner2", "bottom"], "source": "user_declared"},
  "coordinates": {
    "origin": "board_lower_left", "x_axis": "right", "y_axis": "up",
    "rotation": "ccw_positive", "unit": "mm", "source": "user_declared",
    "bottom_side": {"mirror": "none", "rotation_offset_deg": 0, "source": "user_declared"}
  },
  "policies": {
    "dnp_in_cpl": "forbidden",
    "tht_requires_cpl": false,
    "mechanical_requires_cpl": false,
    "strict_file_set": true
  },
  "encodings": {"bom": "utf-8-sig", "cpl": "utf-8-sig"},
  "csv": {"bom_delimiter": ",", "cpl_delimiter": ","},
  "bom": {"required_fields": ["designator", "quantity"], "multiple_designator_separator": ","},
  "board": {"exterior_allow_objects": false},
  "provenance": {"source": "user_declared", "statement": "由本项目导出会话产生"}
}
```

规则：

- `source_snapshot.source` / `provenance.source` 必须属于
  `exporter_attested|user_declared|observed|inferred`；未知算法（非 `sha256/sha384/sha512`）→
  `input_invalid`，不静默择一。
- 同一路径重复声明、同一路径/角色冲突、同一角色多个文件 → `input_invalid`。
- `files[]` 的 `sha256` 是可选的**声明哈希**；实际哈希由工具计算。声明哈希不符 → fail。
- `content_manifest.sha256` 必须等于按 §5 算法计算的当前内容摘要；不符 → fail。
- `files[]` 声明集合与包内文件集合的比对：`strict_file_set=true` 时缺件 fail、多件 unknown；
  未声明包内文件默认按 unknown 报告（不静默忽略）。系统噪声文件（`.DS_Store`、`Thumbs.db`、
  `desktop.ini`、`__MACOSX/` 下文件）单独分类为 `system_artifact`，不使必需覆盖失败。
- 文件时间、文件名只做线索，不参与 provenance 判定；`touch` 不改善任何状态。
- `stackup.layers` 与 `copper_order` 是声明值；实际铜层以内容/内容声明的角色为准，缺内层可检出。
- 没有 `coordinates` 声明时，报告必须给 `coordinates.*` unknown，不能判"坐标正确"。

## 4. 清单命令与内容摘要

`manifest` 输出 `delivery-manifest/v1`，只描述**当前文件集合的内容快照**：

```json
{
  "schema": "delivery-manifest/v1",
  "tool": {"name": "delivery-audit", "version": "0.1.0"},
  "generated_at": "2026-10-27T04:00:00+00:00",
  "input": {"kind": "directory|zip|file", "path": "…", "input_sha256": "…|null", "file_count": 6},
  "content_digest": {"algorithm": "sha256", "value": "…"},
  "files": [
    {"path": "gerber/GTL.gbr", "size": 123, "sha256": "…", "detected_kind": "gerber",
     "role_hint": "copper_top", "role_hint_source": "content"}
  ],
  "provenance": {
    "source": "observed",
    "source_binding": "none",
    "statement": "content snapshot of the current file set; it does not prove a common EDA revision"
  },
  "limits": {"max_files": 5000, "max_total_bytes": 268435456, "max_member_bytes": 67108864, "max_compression_ratio": 200}
}
```

内容摘要算法（冻结）：

```
sha256( b"delivery-content/v1\n" +
        for each file sorted by (path.casefold(), path):
        sha256_hex + b"\t" + decimal_size + b"\t" + path_utf8 + b"\n" )
```

只含路径/字节数/字节哈希；不含 mtime、容器元数据、生成时间。按原始字节算哈希，不因 CSV 换行、
编码或 Unicode 归一改变。

## 5. 输入扫描（`scan.py`，S 负责）

```python
class Limits:
    max_files: int = 5000
    max_total_bytes: int = 256 * 1024 * 1024
    max_member_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: int = 200
    ratio_min_bytes: int = 1024 * 1024

class PackageSource:
    input_path: Path          # resolved
    kind: str                 # "directory" | "zip" | "file"
    files: list[dict]         # 每项: path,size,sha256,origin,zip_member?,compression_ratio?,mtime_ns?
    limits: dict
    input_sha256: str | None  # zip/file 容器哈希
    zip_facts: dict | None
    def read_bytes(self, logical_path: str) -> bytes   # 重新读取并校验 size+sha256
    def content_digest(self) -> str                    # 冻结算法
    def verify_unchanged(self) -> None                  # 变化时 raise AuditInputError
    def metadata(self) -> dict

def scan_input(path, limits=None) -> PackageSource      # 失败 raise AuditInputError
```

必需行为：

- 目录：递归、只用 `os.scandir`、不跟随符号链接/junction/reparse point；遇到即
  `AuditInputError('input_symlink')`。读取前后 stat 一致，否则
  `AuditInputError('input_changed_during_scan')`。权限/IO 错误转 `input_unreadable`。
- 单文件非 ZIP：作为 `file` 包（一个逻辑文件），仍做字节哈希与上限检查。
- ZIP：拒绝路径穿越、绝对路径、盘符、反斜杠、控制字符、段尾 `.`/空格、Windows 保留设备名、
  空段；拒绝符号链接成员、加密成员、CRC 错误、重复路径（含 casefold+NFC 冲突）；限制成员数、
  单成员/总展开字节、压缩比（单成员且 `file_size>=ratio_min_bytes`，以及总展开/总压缩）；
  目录成员计入成员数但不入 files。
- 不写任何文件、不执行任何内容、不访问网络、不解析外部引用。
- `read_bytes` 只接受 `source.files` 中的逻辑路径；不匹配/读取失败/哈希变化 →
  `AuditInputError('input_changed_during_read')`（含 file 证据）。
- 所有错误信息必须可操作（说明限制值/成员名/原因）。

扫描规则号（作为 input_invalid 的 `code`）：`input_not_found`、`input_not_supported`、
`input_unreadable`、`input_symlink`、`input_changed_during_scan`、`input_changed_during_read`、
`input_limits_exceeded`、`zip_unsafe_member`、`zip_duplicate_member`、`zip_encrypted_member`、
`zip_crc_error`、`zip_bad_archive`。`AuditInputError.evidence` 带 `where`/限制值。

## 6. 格式探测（`formats.py`，Lead 负责）

```python
def detect_kind(data: bytes, name: str) -> dict
# {"kind": "gerber|drill|csv|json|pdf|svg|png|zip|text|binary|empty|unknown",
#  "confidence": "content|extension|none", "evidence": str, "extension": ".gbr"}
def infer_role(name: str) -> dict | None
# {"role": "copper_top|...|None", "layer_index": int|None, "source": "inferred"}
```

内容优先，扩展名只作线索；扩展名与内容不符必须可被后续判定发现（不因扩展名正确而放行）。

## 7. 有限解析器接口

所有解析函数签名为 `parse_<format>(data: bytes, file: str, options: dict | None = None) -> dict`，
**对内容问题不抛异常**（返回 findings），只对编程错误抛 `ValueError`。返回：

```python
{
  "kind": "gerber|drill|bom|cpl",
  "file": "<逻辑路径>",
  "status": "pass|fail|unknown",
  "facts": {...},                       # 见下
  "capability": {"supported": [...], "unsupported": [...], "unknown": [...]},
  "findings": [model.finding(...), ...]
}
```

`status`：有 fail finding → fail；否则有 unknown finding → unknown；否则 pass。

### 7.1 Gerber（`gerber.py`，G 负责）`gerber.parse_gerber`

支持子集：RS-274X 单位（`%MOMM/%MOIN`）、格式声明（`%FS`，L/T 零省略、仅绝对坐标）、
必要 aperture 定义（C/R/O/P；`ADD` 引用必须存在）、基本 `G01` draw / `D02` move / `D03` flash、
模态 D 码与省略轴、`G54/G55`、`M02` 结束、X2 `%TF.FileFunction`/`%TF.FilePolarity`/
`%TF.Part` 元数据、行注释 `G04`。按状态机逐 token 解析，不用整文件正则冒充。

未支持特性必须显式记入 `facts.unsupported` 并给出 unknown finding；不得忽略后宣称边界一致：
`AM` 宏（含引用宏 aperture）、`%SR` step&repeat、`G36/G37` region、`G02/G03` 弧线、
非默认极性 `%LPC`、`%LM/%LR/%LS` 图像变换、`%IPNEG`、`%MI/%OF/%SF/%AS`、incremental（`%FSI`）、
未知 D 码/aperture 模板、无法识别的扩展命令。这些特性影响几何时 `facts.contours_exact=false`、
`facts.extent.exact=false`（extent 可给保守上界并注明 basis）。

`facts` 必含：`units`（`mm|inch|None`）、`format`、`file_function`、`file_polarity`、`part`、
`apertures`、`graphical_objects`、`draws`、`flashes`、`regions`、`arcs`、`macros`、
`contours`（线性封闭轮廓；仅无弧线/region/变换时可信）、`contours_exact`、`path_extent`
（不含线宽/孔径的路径边界）、`extent`（含线宽/孔径，mm，`exact`+`basis`）、`end_of_file`、
`encoding`、`errors`、`unsupported`。

规则号：`gerber.file_empty`、`gerber.encoding_invalid`、`gerber.truncated`、
`gerber.end_missing`、`gerber.format_missing`、`gerber.format_invalid`、`gerber.units_missing`、
`gerber.units_mixed`、`gerber.aperture_missing`、`gerber.aperture_undefined`、
`gerber.aperture_redefined`、`gerber.no_graphical_objects`、`gerber.draw_without_aperture`、
`gerber.coordinate_invalid`、`gerber.unsupported.*`（如 `.macro`、`.region`、`.arc`、
`.step_repeat`、`.polarity`、`.transform`、`.incremental`）、`gerber.limit_objects`。

### 7.2 钻孔（`drill.py`，G 负责）`drill.parse_drill`

支持子集：Excellon/NC 钻带（不是 Gerber 图像格式）：`M48` 头、`METRIC/INCH` 单位、工具表 `TnCd`、
`%`/`M95` 头结束、`T` 选刀、`X/Y` 孔位（显式小数；或可由头声明的整数格式确定）、
`M30` 结束、`G90`、`G05`。坐标范围用于板框外溢检查。

未支持：槽/铣（`G85`、`M15/M16`、routing mode）、重复/增量、无法确定整数坐标格式、
未定义工具、非正直径、单位缺失。显式记 unknown；不猜。规则号：`drill.file_empty`、
`drill.header_missing`、`drill.end_missing`、`drill.truncated`、`drill.units_missing`、
`drill.units_invalid`、`drill.tool_table_missing`、`drill.tool_invalid`、`drill.tool_undefined`、
`drill.no_holes`、`drill.coordinate_unknown_format`、`drill.coordinate_invalid`、
`drill.unsupported.slot`、`drill.unsupported.routing`、`drill.limit_objects`。

`facts` 必含：`units`、`format`、`header`、`end_of_file`、`tool_count`、`hole_count`、`slots`、
`routing`、`tools`、`undefined_tools`、`duplicate_tools`、`extent`（mm + `exact`+`basis`）、
`unsupported`。

### 7.3 BOM（`bom.py`，B 负责）`bom.parse_bom`

- 编码：默认 UTF-8（允许 BOM）；`options['encoding']` 必须经 `codecs.lookup` 校验；解码失败
  不得 `errors='replace'`，给 `bom.encoding_unspecified`（fail，提示显式声明编码）。
- CSV：标准 `csv` 模块，正确处理引号/逗号/换行；分隔符 `options['delimiter']`，否则按首行
  在 `, ; \t` 中确定性判定（无法唯一确定时用逗号并记 unknown）。
- 列别名（大小写/空格/下划线不敏感）：位号 `designator(s)/ref(s)/reference/位号`；数量
  `quantity/qty/数量`；值 `value/comment/值`；封装 `footprint/package/封装`；
  `mpn/manufacturer part number/型号`；`manufacturer/厂商`；`lcsc/supplier part/C号`；
  `dnp/do not populate/不贴`；装配 `assembly/装配`；面别 `side/layer/面`。
- 一行多位号明确规则：逗号、分号、空白分隔；范围仅支持同前缀 `R1-R3`、`R1-3`（升序展开）；
  其他厂商复杂格式不猜，给 findng。展开后数量必须与数量列一致。
- DNP 布尔只接受 `1/0/true/false/yes/no/y/n`（大小写不敏感，允许空）；装配类型
  `smt/tht/hand/mechanical/dnp`（大小写不敏感）。
- 规则号：`bom.encoding_unspecified`、`bom.delimiter_ambiguous`、`bom.no_designator_column`、
  `bom.row_invalid`、`bom.designator_missing_invalid`、`bom.designator_duplicate`、
  `bom.designator_range_invalid`、`bom.quantity_invalid`、`bom.quantity_mismatch`、
  `bom.dnp_invalid`、`bom.assembly_unknown`、`bom.required_field_missing`、
  `bom.limit_rows`、`bom.empty`。

`facts.rows[]` 含 `line`、`designator_raw`、`designators`、`quantity`、`dnp`、`assembly`、
`value`、`footprint`、`mpn`、`manufacturer`、`lcsc`、`side`。`facts.counts` 与列映射。

### 7.4 CPL（`cpl.py`，B 负责）`cpl.parse_cpl`

- 位号、X、Y、单位、面别、角度。单位来源优先级：表头单位（`X(mm)`/`X(mil)`/`unit` 列/
  `mm|mil|inch` 文本）> `options['unit']`（来自声明，须记 `unit_source='declared'`）> 未知即
  fail `cpl.unit_missing`（未知单位不能判坐标准确）。
- 数值严格解析：拒绝空、`NaN`、`Infinity`、`true/false`、非有限值；角度必须有限；角度保留
  原值，比较时才按 `mod 360` 归一。
- 面别只接受 `top/bottom/T/B/back/front`（大小写不敏感，映射表固定）；未知面别 fail。
- 规则号：`cpl.encoding_unspecified`、`cpl.delimiter_ambiguous`、`cpl.no_designator_column`、
  `cpl.unit_missing`、`cpl.position_not_numeric`、`cpl.position_unit_unknown`、
  `cpl.side_missing`、`cpl.side_unknown`、`cpl.rotation_not_numeric`、`cpl.designator_duplicate`、
  `cpl.designator_missing_invalid`、`cpl.required_field_missing`、`cpl.empty`、`cpl.limit_rows`。

`facts.rows[]` 含 `line`、`designator`、`x`/`y`（原单位）、`unit`、`x_mm`/`y_mm`、`side`、
`rotation`（原值）、`rotation_norm`。`facts.units`/`unit_source`。

### 7.5 BOM/CPL 交叉（`assembly.py`，B 负责）`assembly.audit_assembly`

输入：两个 parse 结果 + declarations + profile。只做一致性与策略检查，不重判行内字段。

- BOM 中需要贴装的位号（默认 `assembly=smt`，缺省时按 profile 视作 smt 但记 unknown）必须在
  CPL；CPL 位号必须在 BOM。`dnp_in_cpl` 策略：DNP 位号出现在 CPL → fail。
- `tht_requires_cpl`/`mechanical_requires_cpl` 为 false 时，THT/机械件无 CPL 不是错误；
  出现在 CPL 记 info/按策略。同位号面别/装配属性矛盾 → fail。
- 规则号：`assembly.bom_unusable`、`assembly.cpl_unusable`、`assembly.cpl_missing_designator`、
  `assembly.cpl_extra_designator`、`assembly.dnp_in_cpl`、`assembly.tht_in_cpl`、
  `assembly.mechanical_in_cpl`、`assembly.side_conflict`、`assembly.assembly_field_missing`、
  `assembly.count_mismatch`。

## 8. 报告与 CLI（Lead 负责）

`python -m delivery_audit <command>`，从 `design-hardware/scripts` 目录运行（包在
`design-hardware/scripts/delivery_audit/`）。

```
inspect  --input PATH [--out PATH] [--generated-at ISO8601] [limits]
manifest --input PATH [--out PATH] [--generated-at ISO8601] [limits]
audit    --input PATH [--profile P] [--declarations PATH] [--out PATH]
         [--bom PATH] [--cpl PATH] [--coordinate-reference PATH] [--generated-at ISO8601] [limits]
limits: --max-files N --max-total-bytes N --max-member-bytes N --max-ratio N
```

- stdout 永远只有一个 JSON 对象，日志/诊断只到 stderr。
- `--out`：审计时为目录（写 `delivery-audit.json` + `delivery-audit.md`）或 `.json`/`.md`
  路径；inspect/manifest 为单 JSON 文件。输出必须在输入之外：resolved 路径落在输入目录/ZIP
  同一路径内则 `input_invalid`（exit 2），不写输入内任何文件。
- 原子输出：同目录临时文件 + `os.replace`；失败清理临时文件；不修改输入。
- 非法输入也向 `--out` 写 `status=input_invalid` 报告，替换旧 PASS，避免误读；写不了则 stderr
  说明且 stdout 仍给 JSON。
- `--generated-at` 固定时报告字节可重放；默认 UTC now（`timespec=seconds`）。
- 报告 JSON 顶层：`schema`、`tool{name,version}`、`generated_at`、`status`、`profile`、
  `input{kind,path,file_count,input_sha256,content_digest,limits}`、`declarations{...summary…}`、
  `files[]`、`checks[]{id,status,scope,objects,notes}`、`findings[]`、
  `coverage{required[],optional[]}`、`provenance{…}`、`capability{…}`、
  `restrictions[]`（含 `real_eda: NOT RUN`）、`summary`（计数，不是总分）、`error?`。
- Markdown：先列阻断与缺件，再列 unknown/限制，最后文件清单与可复核命令；不出现"制造通过"。
- 排序：files 按 `(path.casefold(), path)`；findings 按 §2 规则排序；checks 按 id。

## 9. 规则号命名空间

`package.*`（文件/角色/集合）、`stackup.*`、`layer.*`、`outline.*`、`gerber.*`、`drill.*`、
`bom.*`、`cpl.*`、`assembly.*`、`provenance.*`、`manifest.*`、`coordinates.*`、`report.*`、
`input.*`。新增规则必须同步 `format-support.md` 与 `acceptance-matrix.md`。

## 10. 文件所有权（并行写边界）

| 路径 | 所有者 |
|---|---|
| `design-hardware/scripts/delivery_audit/model.py`、`__init__.py`、`__main__.py`、`cli.py`、`formats.py`、`declarations.py`、`provenance.py`、`layers.py`、`audit.py`、`report.py`、`manifest.py` | Lead |
| `design-hardware/scripts/delivery_audit/scan.py` | S（scan/安全） |
| `design-hardware/scripts/delivery_audit/gerber.py`、`drill.py` | G（解析） |
| `design-hardware/scripts/delivery_audit/bom.py`、`cpl.py`、`assembly.py` | B（BOM/CPL） |
| `tests/delivery_audit/test_scan.py` | S |
| `tests/delivery_audit/test_gerber_drill.py` | G |
| `tests/delivery_audit/test_bom_cpl.py` | B |
| `tests/delivery_audit/support.py`、`test_core.py`、`test_reproducibility.py`、`test_scenarios.py` | Lead |
| `benchmarks/delivery-audit/`、`tests/delivery_audit/test_benchmarks.py` | Lead（冻结后可由审查者只读） |
| `docs/parallel-delivery-audit/` | Lead；`format-support.md`/`source-register.md` 可交给资料负责人 |

不得修改仓库其它路径；不得改 `design_engine`、`ecosystem_files.py` 等现有模块（只读参考）。
公共模块缺陷写入 `docs/parallel-delivery-audit/issue-candidates.md`。

## 11. 实现与测试约束

- Python 3.10 兼容（CI 矩阵 3.10/3.13；本机实测 3.13.15，3.10 本地 NOT RUN 需在报告注明）。
- 仅标准库；不新增顶层依赖。确定性输出；无网络；无 EDA；不执行输入。
- 单模块测试至少覆盖：正常样例、反例、缺信息（unknown）三类；CLI 场景由冻结基准覆盖。
- 每个解析器对资源上限（对象数/行数）有明确上限并给可操作错误，超限记 unknown，不静默截断。
