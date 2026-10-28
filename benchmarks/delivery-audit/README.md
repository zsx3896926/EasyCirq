# 交付审计冻结基准（delivery-audit）

用途：对 `design-hardware/scripts/delivery_audit` 的真实 CLI 做可重放回归。每个场景都是
一个冻结的输入目录/文件 + 声明 + 预期退出码/状态/规则，驱动会实际执行
`python -m delivery_audit ...`，不调用单元函数替代 CLI。

## 目录

```
benchmarks/delivery-audit/
├── cases.py           # 场景定义（合成夹具构建器 + 预期）
├── make_fixtures.py   # 生成/冻结 fixtures/（内容摘要写入 case.json）
├── digest.py          # 独立实现的内容摘要（不调用被测工具）
├── run_benchmarks.py  # 真实 CLI 驱动，写 results/latest.json
├── fixtures/          # 冻结输入（提交到仓库）
│   └── <case-id>/
│       ├── case.json          # 输入 SHA/内容摘要/预期/simulated 标记
│       ├── input/             # 包目录，或单个 ZIP 文件
│       ├── declarations.json  # 可选
│       └── reference.json     # 可选（坐标参考）
├── real-sample/       # 真实只读样例 + SOURCE.md（来源/许可/哈希）
├── results/latest.json
└── README.md
```

## 运行

```bash
# 仓库根目录
python benchmarks/delivery-audit/run_benchmarks.py
# 只跑某几个场景
python benchmarks/delivery-audit/run_benchmarks.py --case 01-legal-2l-fabrication
```

驱动会对每个 case：

1. 复制输入到临时目录并校验冻结内容摘要（以及单文件输入的 sha256）；
2. 执行真实 CLI（固定 `--generated-at 2026-10-27T00:00:00+00:00`）；
3. 校验退出码、`status`、必需规则、无 `fail`/`unknown`、错误码、旧输出替换、输入不变；
4. 写出 `results/latest.json`，任一 case 失败则退出非零。

## 场景

| # | 场景 | 预期 |
|---|---|---|
| 01 | 合法双层制造包 | exit 0 / pass_with_scope |
| 02 | 合法四层制造包 | exit 0 / pass_with_scope |
| 03 | 四层缺内层 | exit 1 / stackup.missing_copper_layer |
| 04 | 同层两个冲突候选 | exit 1 / layer.duplicate_role |
| 05 | 空 Gerber | exit 1 / package.empty_file |
| 06 | 截断 Gerber（无 M02） | exit 1 / gerber.end_missing |
| 07 | 未支持弧线几何 | exit 3 / gerber.unsupported.arc |
| 08 | 未支持 AM 宏 | exit 3 / gerber.unsupported.macro |
| 09 | 钻孔缺单位 | exit 1 / drill.units_missing |
| 10 | 钻孔引用未定义工具 | exit 1 / drill.tool_undefined |
| 11 | 钻孔槽（slot） | exit 3 / drill.unsupported.slot |
| 12 | BOM 数量/位号矛盾 | exit 1 / bom.quantity_mismatch |
| 13 | CPL 重复位号 | exit 1 / cpl.designator_duplicate |
| 14 | DNP 件出现在 CPL | exit 1 / assembly.dnp_in_cpl |
| 15 | THT 无 CPL（允许） | exit 0 / pass_with_scope |
| 16 | 无坐标约定 | exit 3 / coordinates.convention_missing |
| 17 | 独立坐标参考正例（含底面镜像） | exit 0 / pass_with_scope |
| 18 | 底面坐标负例 | exit 1 / coordinates.offset_mismatch |
| 19 | 声明内容摘要冲突 | exit 1 / manifest.content_digest_mismatch |
| 20 | touch 旧文件 | exit 1 / provenance.file_hash_mismatch |
| 21 | 合法 ZIP 交付包 | exit 0 / pass_with_scope |
| 22 | archive profile + 原生容器 | exit 0 / pass_with_scope |
| 23 | ZIP 路径穿越 | exit 2 / zip_unsafe_member |
| 24 | ZIP 压缩炸弹 | exit 2 / input_limits_exceeded |
| 25 | ZIP 大小写重复成员 | exit 2 / zip_duplicate_member |
| 26 | 输出写进输入 | exit 2 / output_invalid |
| 27 | 旧 PASS 输出被 invalid 覆盖 | exit 2 / input_not_found |
| 28 | 真实只读样例重放 | 观察值冻结（exit/status/rules），非制造结论 |

## 冻结与更新

- `fixtures/<case>/case.json` 记录输入内容摘要、各文件 sha256、预期状态/规则和
  `simulated` 标记；驱动每次先校验摘要，fixture 被改而未更新元数据会立即失败。
- 有意修改夹具时：运行 `python benchmarks/delivery-audit/make_fixtures.py` 重新冻结，
  人工审查 `git diff`（尤其是 `case.json` 与声明），再运行驱动。
- 真实样例不提供源工程/BOM/CPL，也不绑定 EDA revision；case 28 的预期仅表示
  "同一输入在当前实现下的只读重放结果"，不是格式/制造验收。
- 本基准不产生/不修改任何制造文件，不调用 EDA，不上传工程。
