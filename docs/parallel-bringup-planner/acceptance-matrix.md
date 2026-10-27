# 验收矩阵：六组能力 × 场景 × 判据

> 本矩阵说明每项能力如何被"输入场景 → CLI 子进程 → 计划/评估 JSON"验收。所有场景在 `benchmarks/bringup-planner/scenarios/` 与 `cases/`，由 `benchmarks/bringup-planner/run_benchmark.py` 以真实子进程运行，冻结输入 SHA 与预期 DAG/STOP/unknown/计划与评估结论。
>
> **所有真实仪器、上电、烧录、串口/JTAG、EDA 操作均为 NOT RUN。** 合成结果（`source=synthetic`）只用于评估器语义验收，绝不升级为真实硬件 PASS。

## 1. 六组能力 × 正例/负例/缺信息

| 能力 | 正例（应生成可执行步骤） | 负例（应阻断/拒绝/不生成） | 缺信息（应 blocked/unknown/gap，不填默认值） |
|---|---|---|---|
| **I1 断电检查与前提** | `normal-minimal-smoke`、`normal-mcu-sensor-board`、`deenergized-measurement-preconditions` | `no-short-check-criterion`（无判据不生成欧姆阈值，判据 `needs_interpretation`） | `deenergized-measurement-preconditions` 中外部供电/放电前提缺失时 blocked；缺万用表 → `I1_MULTIMETER_MISSING` |
| **I2 首次上电与分域顺序** | `power-sequence-three-rails`、`combined-normal-negative-missing` | `dependency-cycle`（环路不排序/不上电）、`high-voltage-envelope`/`unsupported-mains-ac`（范围外不生成通用上电） | `missing-startup-current`、`missing-current-limit-policy`、`inrush-current-limit`（限流依据不足→blocked）、`missing-observation-window`（不编秒数） |
| **I3 电源/时钟/复位/基础通信** | `normal-mcu-sensor-board`、`combined-normal-negative-missing` | `missing-probe-bandwidth`（缺带宽/探头→blocked，不宣称波形可测）、`insufficient-equipment` | `missing-testpoint`（无测点→blocked）、`firmware-not-flashed`（未烧录预期无业务通信） |
| **I4 负载与接口** | `normal-mcu-sensor-board`、`normal-minimal-smoke` | `btl-wrong-grounding`（禁止单端接地；缺差分→blocked）、`unknown-load`（负载不明不生成负载测试） | `dnp-module`（DNP 核对步骤）、`unknown-load`（补负载参数） |
| **I5 故障定位树与 STOP** | 所有生成计划的场景（有限故障树、分支有证据/可判定条件） | `eval-stop-propagation`（STOP 后传递依赖 blocked，独立分支继续） | 缺测量/证据的树分支 terminal=`unknown`；不列猜测清单、不宣称器件损坏 |
| **I6 结果记录与评估** | `eval-pass-real-evidence`（真实测量+证据→PASS，hardware_pass=true） | `eval-stale-revision`、`eval-unit-conflict`、`eval-missing-evidence`、`invalid-input-*`（INVALID/不得 PASS） | `eval-partial-tests`（部分通过按范围报告）、`eval-synthetic-only`（SYNTHETIC_ONLY，hardware_pass=false） |

## 2. 任务书第 8 节类别 → 场景映射

| # | 要求类别 | 场景 | 关键预期 |
|---|---|---|---|
| 1 | 正常低压小板 | `normal-minimal-smoke` | scope=supported，I1–I4 有 ready 步骤，DAG 无环 |
| 2 | 电源顺序 | `power-sequence-three-rails` | 三域 order 符合依赖，后级上电依赖前级验证 |
| 3 | 依赖环路 | `dependency-cycle` | 检测环路，相关步骤不生成/阻断，不静默排序 |
| 4 | 缺启动电流 | `missing-startup-current` | 该域上电 blocked，`missing_information` 含启动电流，**无 100mA/500mA 默认值** |
| 5 | 浪涌与限流前提 | `inrush-current-limit` | 限流 < 已知启动电流 → 浪涌/重启风险；缺依据 → blocked |
| 6 | 外部 USB 回灌 | `external-usb-backfeed` | I1 断开步骤 + I2 外部供电步骤 + 上电依赖；未解决则 blocked |
| 7 | 断电测量前提 | `deenergized-measurement-preconditions` | 电阻测量依赖"断电+断开外部供电+放电"，不出现带电测电阻 |
| 8 | 缺测点 | `missing-testpoint` | 相关电压/纹波步骤 blocked，unknown/gap 写明缺测点 |
| 9 | 缺探头/带宽 | `missing-probe-bandwidth` | 纹波/时钟步骤 blocked + equipment gap，不宣称波形可测 |
| 10 | 未装模块 | `dnp-module` | DNP 核对步骤，DNP 不按已装测试 |
| 11 | 未烧固件 | `firmware-not-flashed` | 通信步骤有固件前提；"无通信"不算失败 |
| 12 | BTL 错误接地 | `btl-wrong-grounding` | 步骤 blocked 或明确禁止单端接地；缺差分→blocked；有差分→ready |
| 13 | 负载不明 | `unknown-load` | 不生成负载测试，unknown 要求补负载参数 |
| 14 | STOP 传播 | `eval-stop-propagation` | 触发 STOP 的步骤 FAIL/STOP，传递依赖 blocked，依赖中的 pass 被 invalidated |
| 15 | 部分测试 | `eval-partial-tests` | verdict 非 PASS，按组/域报告 pass/unknown/blocked；完成率不掩盖阻断 |
| 16 | 旧 revision 结果 | `eval-stale-revision` | 绑定失效 → INVALID / `STALE_REVISION`，旧 PASS 不复用 |
| 17 | 单位冲突 | `eval-unit-conflict` | mV↔V 可换算通过；量纲不符/未知单位 → INVALID |
| 18 | 证据缺失 | `eval-missing-evidence` | 缺 required_evidence → 不得 PASS（unknown/INCOMPLETE） |
| 19 | 合成结果 | `eval-synthetic-only` | verdict=SYNTHETIC_ONLY，hardware_pass=false |
| 20 | 非法输入 | `invalid-input-json`、`invalid-input-self-dependency`、`invalid-input-unit-mismatch`、`invalid-input-unknown-field` | 退出码 2，不写计划，清理旧生成物 |
| 21 | 设备不足 | `insufficient-equipment` | 设备能力不足 → blocked + equipment_gap，不推定满足 |
| 22 | 范围外/需专家 | `unsupported-mains-ac`、`high-voltage-envelope` | scope=unsupported/needs_specialist，不生成通用上电步骤 |
| 23 | 未声明操作 | `required-operations-not-declared` | needs_information/unsupported，缺口可读 |
| 24 | 组合正/负/缺信息 | `combined-normal-negative-missing` | 同一场景内同时覆盖 ready/blocked/unknown，状态互不掩盖 |
| 25 | 组合部分完成 | `combined-partial-blocked` | 独立支路按声明继续，阻断支路不被完成率洗白 |

## 3. Holdout 与变形（不按场景 ID 特判）

| holdout | 变形 | 断言 |
|---|---|---|
| `holdout-object-order` | 输入数组/依赖/引脚倒序 | 计划哈希与步骤判据不变 |
| `holdout-unit-conversion` | 5000 mV ↔ 5 V、mA ↔ A 等价换算 | 计划哈希不变、评估 verdict 不变 |
| `holdout-synonym-notes` | `notes`/任务描述同义改写 | 不参与判据，计划哈希不变 |
| `holdout-unrelated-modules` | 新增无关接口/电源域 | 既有步骤 ID/状态/判据不变，仅新增自身步骤 |
| `holdout-revision-change` | revision 变化 + 旧结果 | 计划哈希改变，旧结果绑定失效 |

变形由 `run_benchmark.py` 对基础场景执行，不读取场景 ID 之外的特判分支。

## 4. 两个组合板案例

| 案例 | 内容 | 证据边界 |
|---|---|---|
| `cases/mcu-sensor-board/` | 低压 USB 5V → LDO 3V3 → MCU + I2C 传感器 + 模拟输入；引用 `design-hardware/cases/mcu-i2c-s3-2026-10-26` 的**只读设计信息** | 合成设计意图；未打样/未贴片/未上电，NOT RUN |
| `cases/load-control-board/` | 低压负载控制/低边驱动 + 按键/LED；引用 photo-led/temp-alarm 案例的**只读信息** | 同上；不声称实物功能已验证 |

组合案例用于检查多域、多接口、负载与固件前提在同一计划中的排序与阻断传播；不是实物验收。

## 5. 验收执行与判据

```bash
# worktree 根目录
python benchmarks/bringup-planner/run_benchmark.py --out /tmp/bp-bench.json
python -m unittest discover -s tests/bringup_planner -p "test_*.py"
python tools/offline_suite.py        # 仓库既有离线套件（不得因本任务回归）
```

判定：

- 本机实测：34 个标准场景 + 5 个 holdout + 2 个组合案例全部通过（41/41），必需类别覆盖 30/30；专属测试 172 个通过；仓库 `tools/offline_suite.py` 1783 tests / 0 failures，`skill_selftest.py` 5 PASS。

- 每个场景真实启动 `python -m bringup_planner validate|plan|explain|evaluate` 子进程；记录实际退出码、计划哈希、DAG order/cycles、步骤 ID/状态、gap/unknown/equipment_gap codes、评估 verdict。
- `expected.json` 为手工推导后冻结的预期（输入 SHA 一并冻结）；实际不一致即失败，不允许按场景 ID 改判。
- 仪器/上电/烧录/串口/JTAG/EDA：全部 **NOT RUN**；基准中不得出现真实测量记录。
- 所有 `results.json` 示例必须标注 `source`；`synthetic` 场景只能得到 `SYNTHETIC_ONLY`。

## 6. 本矩阵不证明的内容

- 不证明任何实物板已上电、功能正常、通过安规/EMC/温升/可靠性/量产一致性。
- 不证明仪器读数真实或测点实际可达（只校验声明与记录一致性）。
- 不证明计划中的步骤在具体实验室环境下可安全执行；执行前仍需人工确认 `user_policy` 与现场条件。
