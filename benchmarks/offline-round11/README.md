# offline-round11 冻结基准

本目录是 round11 离线工具链的可重复验收基准。**没有任何真实 EDA 调用**；真实样例是仓库内已保留的回读证据，派生数据另存。

## 运行

```bash
python tools/offline_benchmark.py --runs 3 \
  --out benchmarks/offline-round11/result.json
```

`result.json` 包含：

- `correctness`: 每个用例是否与 `expected.json` 一致；
- `coverage`: 用例、证据类别、变形测试；
- `timing`: 每个用例的 min/median/max、输入字节、Python/平台信息；
- `not_covered`: 真实 EDA、原生 DRC、制造、布线、热/EMC/固件、图像字节回归等；
- `simulated: true`、`eda_calls: 0`。

## 样例与来源

| 用例 | 来源 | 预期依据 |
|---|---|---|
| `source_hashes` | `expected.json.sources` | 每个真实/合成输入的实际 SHA-256 必须等于冻结值 |
| `gate_photo_regression` | `design-hardware/cases/photo-led-pcb-2026-10-26/`（只读） | round10 真实证据；regression profile 的 pass_with_gaps 与阶段状态人工核对 |
| `sch_visual_photo` | `tests/fixtures/photo-led-v14/layout.json`（真实 v14 回读派生） | fixture README 记录的 1 个 bbox_overlap + 2 个 wire_enters_bbox；3 个有结点证据交叉 + 2 个近距文字为 info |
| `candidates_photo_full` | `templates/photo-led-pcb-intent.json` + 真实板 dump；冻结 `candidates.json` | 修改前 selected/hard/HPWL/面积，容差 0.02 |
| `candidates_structures` | photo 的 interface-protection-core / transistor-load-return + `cases/ldo-caps-*` | 模板角色、实测 body 尺寸与硬过滤结果独立推导 |
| `apply_noop` | frozen placement plan | 计划就是实测 pose，必须 `no_op` 且 0 次 CLI |
| `placement_constraint_gain` | 合成 keepout 边界 | 旧 bbox-only 检查通过、新 keepout 过滤器拒绝 |
| `holdout_geometry` | `cases/holdout-concave-keepout.json` | 实现完成后新增、未参与调参的凹板缺口样例 |
| `deformations` | photo `sch-read.json` + dump | 数组倒序/坐标平移不改变 match；PCB 短接必须 mismatch |

真实证据文件以 `expected.json.sources` 的 SHA-256 为准；基准校验这些哈希，源文件被改动即失败（`NOT RUN` 而不是“通过”）。

预期值的独立性说明：图面残差来自 v14 README 的人工记录；凹板/keepout、holdout 与变形用例的预期由几何/拓扑定义人工推导；photo 候选的 selected/hard 状态按模板绑定和硬约束人工核对，HPWL/面积数值只作为冻结回归基线（来自 round10 的 `candidates.json`），不作为“绝对最优”标准。

## 性能口径

只记录本机本次运行的输入规模、运行次数与 min/median/max；没有同范围旧版基线时，不宣称提速百分比。真实门禁/图面样例的耗时受 Python 启动/文件大小影响，不代表 EDA 速度。

## 未覆盖

真实 `easyeda` CLI/daemon/连接器、原生 DRC/check/lint、Gerber/CPL/钻孔、板厂 DFM、实际布线完成、铺铜连通、热/EMC/安规、固件、实物功能、官方导图人工视觉签核、无字体环境的字形渲染。离线基准通过不等于硬件或生产可用。
