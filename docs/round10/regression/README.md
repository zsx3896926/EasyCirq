# A/B 回归（冻结副本，不改设计）

目标：用新 `pcb_gate` / `pcb_case` 在**不改设计**的前提下重跑 A/B，确认
DRC 0、save/reload match、SCH-PCB 全 match、图/BOM 不变。任何一项失败先修工具，
不带着失败继续。

## 输入

- 冻结基线：`docs/round10/regression/baseline.json`
- 冻结产物哈希：`docs/round10/baseline/frozen-artifacts.json`
- 板 A：`photo-led-pcb-20261026` / `PCB1`
- 板 B：`mcu-i2c-s3-20261026` / `PCB2`

## 步骤

1. 保存当前打开的原理图文档，再打开目标工程（`project open` 会切换窗口；
   不使用 `--allow-discard-unsaved`，先 `sch save`）。
2. 对新 case 目录跑 `pcb_case.py`（不是原 case，避免覆盖冻结证据）：
   ```bash
   python scripts/pcb_case.py --case docs/round10/regression/boardA \
     --project photo-led-pcb-20261026 --doc PCB1 \
     --key-nets docs/round10/baseline/key-nets-boardA.json \
     --warn-disposition ../cases/photo-led-pcb-2026-10-26/evidence/warn-disposition.json \
     --easyeda C:/Users/jlc/.local/bin/easyeda.exe --out manifest.json
   ```
   板 B 同理，替换 project/doc/key-nets/warn-disposition。
3. `pcb_gate.py --case <dir> --profile regression`。必需阶段：PG3 DRC、PG6
   SCH-PCB、PG7 save/reload、PG8 images/BOM/archive；可选阶段未跑记 `not_run`，
   整体 `pass_with_gaps`，不写成 `pass`。
4. 设计不变性：
   - 新 dump 的 `semanticSha256` 必须等于 `baseline.json` 中的值；
   - `BOM.csv` 字节哈希必须等于基线；
   - `layout render --actual` 的 SVG 哈希应等于基线（若 viewport 无关）；
   - PNG 只要求存在、非空、非 blank，并记录与基线的字节差异（视口图可能因
     渲染时间略有差异，不能把字节差异直接判成设计变化）。
5. 任何回归失败：先修 Skill/tool，再重跑；不得直接改冻结证据。

## 允许的差异

- PNG 字节：视口/抗锯齿可能不同；要求尺寸/非 blank/manifest 哈希存在，设计变化
  由 dump semantic hash + diff 判定。
- `.epro2` 字节：重新保存会改变时间戳/primitiveId；不作为“图/BOM 不变”的判据。
- primitiveId：reload 后不稳定；diff 用 identity/geometry/copper，不用 ID 单独判。
