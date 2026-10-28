# 给任务 A 的集成建议：导出完成后调用交付审计

> 本文件只是集成建议，不修改任务 A 的入口、导出器或任何真实代码路径。
> 本模块不改写制造文件；审计通过不等于板厂接单、DFM/阻抗/电气/贴装/实物通过。

## 1. 集成点

在任务 A 的导出流程中，"文件已全部写出且不再变化"之后、打包/上传/下单之前执行一次：

```
导出完成 (Gerber/钻孔/BOM/CPL/工程文件已落盘)
        │
        ├─ 1. manifest  记录当前文件集合的内容摘要
        ├─ 2. declarations  把导出会话身份、层叠、坐标约定、角色/哈希写入声明
        ├─ 3. audit     依据 profile 审计
        └─ 4. gate      按退出码/状态阻止或放行本 revision
```

建议每个 revision 只审计一次冻结快照；审计后任何文件（包括重跑导出、文本编辑器保存、
换行转换、`touch`）发生变化都必须重做 manifest + audit。审计报告写到导出目录**之外**。

## 2. 最小调用示例（A 侧可直接用）

在本仓库 `easycirq/scripts` 目录（或已安装 Skill 的 scripts 目录）执行：

```bash
# 0) 输入：A 的导出目录（只读），例如 evidence/photo-led-vA/export/
EXPORT="evidence/photo-led-vA/export"
OUT="evidence/photo-led-vA/delivery-audit"   # 必须在 EXPORT 之外

# 1) 内容清单（observed；只证明当前字节，不证明 EDA revision）
python -m delivery_audit manifest --input "$EXPORT" --out "$OUT/manifest.json"

# 2) 写 declarations.json（示例见 §3；content_manifest.sha256 取 manifest 的 content_digest.value）
#    角色、层叠、坐标约定、导出会话由 A 的导出上下文填写

# 3) 审计（JSON + Markdown）
python -m delivery_audit audit \
  --input "$EXPORT" \
  --profile pcb-fabrication \
  --declarations "$OUT/declarations.json" \
  --out "$OUT/report"

# 4) 运行退出码：0 = pass_with_scope；1 = fail；2 = input_invalid；3 = incomplete
```

纯贴装交付包用 `--profile smt-assembly`（必需 BOM+CPL，不因缺 Gerber 失败）；纯归档用
`--profile archive`（不要求制造文件）。若 A 已知 BOM/CPL 的精确路径，可加
`--bom bom.csv --cpl cpl.csv` 覆盖按角色推断；有独立可信的坐标参考导出时加
`--coordinate-reference ref.json` 才会做逐件坐标比对。

## 3. declarations.json 示例（A 的导出会话填写）

```json
{
  "schema": "delivery-declarations/v1",
  "project_id": "photo-led",
  "revision": "A",
  "source_snapshot": {
    "hash_algorithm": "sha256",
    "value": "<A 导出的源快照哈希或项目版本标识，按实际填写>",
    "source": "exporter_attested",
    "reference": "export session id / EDA save version"
  },
  "export_session": {
    "id": "export-20261027-01",
    "tool": "EasyEDA Pro",
    "tool_version": "<实际版本>",
    "captured_at": "2026-10-27T22:00:00+08:00"
  },
  "content_manifest": {
    "sha256": "<manifest.json 的 content_digest.value>",
    "source": "observed"
  },
  "files": [
    {"path": "gerber/GTL.gbr", "role": "copper_top", "sha256": "<manifest 中该文件 sha256>"},
    {"path": "gerber/GBL.gbr", "role": "copper_bottom", "sha256": "<…>"},
    {"path": "gerber/GP1.gbr", "role": "copper_inner", "layer_index": 2, "sha256": "<…>"},
    {"path": "gerber/GP2.gbr", "role": "copper_inner", "layer_index": 3, "sha256": "<…>"},
    {"path": "gerber/GKO.gbr", "role": "board_profile", "sha256": "<…>"},
    {"path": "gerber/drill.drl", "role": "drill", "sha256": "<…>"},
    {"path": "bom.csv", "role": "bom", "sha256": "<…>"},
    {"path": "cpl.csv", "role": "cpl", "sha256": "<…>"}
  ],
  "stackup": {"layers": 4, "copper_order": ["top", "inner1", "inner2", "bottom"],
              "source": "user_declared"},
  "coordinates": {
    "origin": "board_lower_left", "x_axis": "right", "y_axis": "up",
    "rotation": "ccw_positive", "unit": "mm", "source": "user_declared",
    "bottom_side": {"mirror": "none", "rotation_offset_deg": 0,
                    "source": "user_declared"}
  },
  "policies": {"dnp_in_cpl": "forbidden", "tht_requires_cpl": false,
               "mechanical_requires_cpl": false, "strict_file_set": true},
  "encodings": {"bom": "utf-8-sig", "cpl": "utf-8-sig"},
  "csv": {"bom_delimiter": ",", "cpl_delimiter": ","},
  "bom": {"required_fields": ["designator", "quantity", "mpn", "footprint"]},
  "board": {"exterior_allow_objects": false},
  "provenance": {"source": "exporter_attested",
                 "statement": "A 的导出步骤写出；未上传板厂"}
}
```

注意：

- 文件路径必须是包内 POSIX 相对路径；声明拒绝包外路径、重复路径、同层多候选和未知哈希算法。
- `coordinates` 必须来自导出器/工程设置，不能猜。没有它，报告会明确 `unknown`，不能宣称坐标正确。
- `content_manifest.sha256` 必须等于 manifest 命令输出；A 不要自行拼一个哈希。
- 真实源绑定只能到"声明 + 内容摘要"级别；报告始终写 `same_eda_revision=declared_unverified`。

## 4. Gate 规则建议

| 退出码 / 状态 | 建议动作 |
|---|---|
| 0 / `pass_with_scope` | 允许进入打包/上传步骤；把报告的 `restrictions` 一并写入交付记录，禁止改写成"制造通过" |
| 1 / `fail` | 阻止本 revision 交付；按 `findings[].rule_id` 修复导出或声明后重跑（不要改报告/改哈希） |
| 3 / `incomplete` | 默认阻止；只有明确知道缺哪类证据（如无坐标参考、格式超子集）并记录 scoped waiver 才可人工放行 |
| 2 / `input_invalid` | 阻止；先修输入/参数（ZIP 不安全、声明非法、输出路径在输入内等），不得复用旧 PASS 报告 |

A 的 gate 应只读取报告 JSON 的 `status`、`exit` 和 `findings`，不要解析 Markdown 或从总分推断。
`pass_with_scope` 的定义是"报告列出的适用检查通过"，不是"可以下单"。

## 5. A 侧调用代码示例（CLI 边界，不需要导入本包）

```python
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path("easycirq/scripts")  # 或安装后的 Skill scripts

def audit_export(export_dir: Path, declarations: Path, out_dir: Path,
                 profile: str = "pcb-fabrication") -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "delivery_audit", "audit",
         "--input", str(export_dir),
         "--profile", profile,
         "--declarations", str(declarations),
         "--out", str(out_dir)],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=300,
    )
    report = json.loads(proc.stdout) if proc.stdout.strip() else {}
    # gate: only status/exit/findings are contractual; do not parse Markdown.
    return {"exit": proc.returncode, "report": report,
            "stderr": proc.stderr}
```

A 可以把 `content_manifest.sha256` 与 manifest 输出做自动对齐；其余字段（角色、层叠、坐标、
导出会话）必须来自 A 的真实导出上下文，不能用"全填 pass"的模板。

## 6. 兼容性与边界

- CLI/schema 版本：`delivery-audit 0.1.0`、`delivery-audit/v1`、
  `delivery-declarations/v1`、`delivery-manifest/v1`；破坏性变更需升 schema 版本。
- 本模块只读输入，不调用 EDA/Connector/daemon/网络，不写导出目录，不自动修复。
- 报告 JSON 提供 `real_eda: "NOT RUN"`、`restrictions[]` 和 `provenance.same_eda_revision`；
  A 的交付记录必须原样保留这些限制。
- A 与 C 不需要互相等待未稳定提交：A 只需在自身导出完成后调用上述 CLI；本模块不可用时
  应显式记录 `delivery audit NOT RUN`，不能默认通过。
