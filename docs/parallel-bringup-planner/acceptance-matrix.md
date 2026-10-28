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
python -m unittest discover -s tests/bringup_planner_tests -p "test_*.py"
python tools/offline_suite.py        # 仓库既有离线套件（不得因本任务回归）
```

判定：

- 本机实测（2026-10-28，逐条证据见 §7）：34 个标准场景 + 5 个 holdout + 2 个组合案例全部通过（41/41），必需类别覆盖 30/30；专属测试 172 个通过；`skill_selftest.py` 5 PASS。
- 仓库 `tools/offline_suite.py`：在 PR #39 合并 HEAD `b407d72` 上 1783 tests / 0 failures / 0 errors（PASS）；**最新 main（截至 `c54c6fc`，含其他并行任务）已 PASS：3318 tests / 0 failures / 0 errors**。§7.5 的 M4-2 是 2026-10-28 采集快照（当时 47 个跨任务 errors），已由后续集成修复；最新复跑见 M4-5 与 `issue-candidates.md` A.6。

- 每个场景真实启动 `python -m bringup_planner validate|plan|explain|evaluate` 子进程；记录实际退出码、计划哈希、DAG order/cycles、步骤 ID/状态、gap/unknown/equipment_gap codes、评估 verdict。
- `expected.json` 为手工推导后冻结的预期（输入 SHA 一并冻结）；实际不一致即失败，不允许按场景 ID 改判。
- 仪器/上电/烧录/串口/JTAG/EDA：全部 **NOT RUN**；基准中不得出现真实测量记录。
- 所有 `results.json` 示例必须标注 `source`；`synthetic` 场景只能得到 `SYNTHETIC_ONLY`。

## 6. 本矩阵不证明的内容

- 不证明任何实物板已上电、功能正常、通过安规/EMC/温升/可靠性/量产一致性。
- 不证明仪器读数真实或测点实际可达（只校验声明与记录一致性）。
- 不证明计划中的步骤在具体实验室环境下可安全执行；执行前仍需人工确认 `user_policy` 与现场条件。

## 7. M0–M4 实测证据清单（2026-10-28）

> **采集基线：** worktree HEAD `3f21897d9d1b93b4ac7e2ef523fe923685f59b08`（分支 `docs/bringup-planner-m0-m4-evidence`，基于合并后的 main）；实现源 HEAD `b407d72f11237001d7c7e1260beb8de770f46f1e`（PR #39 合并源）。
> **PR #39 状态：** 已于 **2026-10-27T16:53:24Z** 由仓库账号 `zsx3896926` 合并（merge commit `9a4622eb46a8ff3d336729726ab6ed056b5f650a`，changedFiles=175，+44762/−0）——**本任务未执行合并**。采集时 `origin/main` 已因其他并行任务前进到 `acbcc18c821e08ddff2401015eb7a16eaee733c8`。
> **证据文件：** 机器可读 [evidence-m0-m4.json](evidence-m0-m4.json)；复现脚本 `benchmarks/bringup-planner/tools/collect_m0_m4_evidence.py`。所有命令均为离线执行：无仪器、上电、烧录、串口/JTAG、EDA、网络。

### 7.1 M0 基线与隔离

| # | 命令 | 退出码 | 关键输出摘要 | 对应 HEAD | 结论 |
|---|---|---|---|---|---|
| M0-1 | `git rev-parse HEAD` / `--abbrev-ref HEAD` | 0 | 采集 worktree `3f21897…`；实现源 HEAD `b407d72…`；分支 `docs/bringup-planner-m0-m4-evidence`（原实现分支 `feat/parallel-bringup-planner`） | `3f21897` | PASS |
| M0-2 | `git rev-parse 9a951ed`；`git rev-parse origin/main` | 0 | 开工基线 `9a951ed…`；采集时 `origin/main=acbcc18…`（PR #39 合并后其他并行任务继续推进） | `3f21897` | PASS |
| M0-3 | `git status --short` | 0 | 空（采集前工作区干净） | `3f21897` | PASS |
| M0-4 | `git worktree list` | 0 | 独立 worktree（`hds-bp-evidence` / 原 `hds-bp-worktree`），未混用他人分支 | `3f21897` | PASS |
| M0-5 | `git diff --name-only 9a951ed...b407d72` | 0 | **175 files**；允许路径外 **0**；四目录：`design-hardware/scripts/bringup_planner/`、`tests/bringup_planner/`（合并前路径）、`benchmarks/bringup-planner/`、`docs/parallel-bringup-planner/` | `b407d72`（PR #39） | PASS |
| M0-6 | `git cat-file -e HEAD:docs/parallel-bringup-planner/acceptance-matrix.md`；`…:design-hardware/scripts/bringup_planner/plan.py` | 0 | 合并后 main 同时包含文档与实现脚本（18 个 bringup_planner 脚本） | `3f21897` | PASS |
| M0-7 | `gh pr view 39 --json …` | 0 | `state=MERGED`；`mergedAt=2026-10-27T16:53:24Z`；`mergedBy=zsx3896926`；`mergeCommit=9a4622e…`；`changedFiles=175`；`+44762/−0`；非 draft | PR 元数据 | PASS（外部合并） |

### 7.2 M1 核心 CLI（validate / plan / explain）

| # | 命令 | 退出码 | 关键输出摘要 | 对应 HEAD | 结论 |
|---|---|---|---|---|---|
| M1-1 | `python -m bringup_planner validate --input tests/bringup_planner_tests/fixtures/minimal-input.json --json` | 0 | `status=valid`，`revision=rev-A`，诊断 1 条（warning `E_BACKFEED_RISK`，非错误） | `3f21897` | PASS |
| M1-2 | `python -m bringup_planner plan --input …minimal-input.json --out <tmp> --json` | 0 | `scope=supported`；20 steps / 14 ready / 6 blocked；`plan_sha256=0e3dbc16…`；9 棵故障树 | `3f21897` | PASS |
| M1-3 | `python -m bringup_planner plan --input benchmarks/bringup-planner/cases/mcu-sensor-board/input.json --out <tmp> --json` | 0 | 23 steps / 13 ready / 10 blocked；`plan_sha256=e22a20bc…`；8 棵故障树 | `3f21897` | PASS |
| M1-4 | `python -m bringup_planner plan --input benchmarks/bringup-planner/cases/load-control-board/input.json --out <tmp> --json` | 0 | 15 steps / 9 ready / 6 blocked；`plan_sha256=2f417fda…`；4 棵故障树 | `3f21897` | PASS |
| M1-5 | `python -m bringup_planner explain --input …minimal-input.json --step I2-SEQ-VIN_5V --json` | 0 | `status=ok`，`scope=supported`，步骤存在且可解释 | `3f21897` | PASS |

### 7.3 M2 六组能力行为与评估器

| # | 命令（均为离线 CLI） | 退出码 | 关键输出摘要 | 对应 HEAD | 结论 |
|---|---|---|---|---|---|
| M2-1 | M1-2 plan 输出中的 `I1-OFF-RES-VIN_5V` | 0 | 判据 `criterion_status=needs_interpretation`、`range=null`；前提为 `I1-OFF-001` + `I1-OFF-DISCHARGE`（断电/放电/断开外部供电），未输出通用欧姆阈值 | `3f21897` | PASS |
| M2-2 | `plan --input …scenarios/missing-startup-current/input.json` | 0 | `I2-SEQ-VDD_3V3` 等 blocked；`missing_information` 含 `startup_current`；计划文本**无** 100mA/500mA/0.1A/0.5A 默认值 | `3f21897` | PASS |
| M2-3 | `plan --input …scenarios/btl-wrong-grounding/input.json` | 0 | `I4-BRIDGE-U5_BTL` blocked；计划含 `differential` 约束；设备缺口 `DIFFERENTIAL_PROBE_NOT_DECLARED`、`PROBE_LOADING_NOT_DECLARED` | `3f21897` | PASS |
| M2-4 | `plan --input …scenarios/unsupported-mains-ac/input.json` | 0 | `scope=needs_specialist`；`steps_total=0`、`ready_steps=[]`（不生成通用上电步骤） | `3f21897` | PASS |
| M2-5 | `validate --input …invalid-input-self-dependency/input.json --json` | 1 | `status=invalid`；错误 `E_DAG_SELF_DEPENDENCY`（自依赖被拒绝） | `3f21897` | PASS（预期拒绝） |
| M2-6 | `validate --input …invalid-input-json/input.json --json` | 2 | 畸形 JSON 被拒绝，无计划输出 | `3f21897` | PASS（预期拒绝） |
| M2-7 | `plan --input …invalid-input-json/input.json --out <tmp> --json` | 2 | 不写 `plan.json`；`input-invalid.json` 未写（仅 schema-invalid 文档写该标记，见 §7.7 备注） | `3f21897` | PASS（有备注） |
| M2-8 | `evaluate --plan …eval-pass-real-evidence/plan.json --results …/results.json --evidence-root …/evidence` | 0 | `verdict=PASS`、`hardware_pass=true`（评估器契约 fixture，证据文件明示 NO INSTRUMENT WAS CONNECTED，**非硬件 PASS**） | `3f21897` | PASS（契约） |
| M2-9 | `evaluate …eval-stop-propagation…` | 1 | `verdict=FAIL`、`hardware_pass=false`；STOP 传播阻断依赖 | `3f21897` | PASS（预期） |
| M2-10 | `evaluate …eval-stale-revision…` | 2 | `verdict=INVALID`；旧 revision/哈希绑定失效 | `3f21897` | PASS（预期） |
| M2-11 | `evaluate …eval-unit-conflict…` | 2 | `verdict=INVALID`；量纲冲突拒绝 | `3f21897` | PASS（预期） |
| M2-12 | `evaluate …eval-missing-evidence…` | 3 | `verdict=INCOMPLETE`、`hardware_pass=false`；缺证据不得 PASS | `3f21897` | PASS（预期） |
| M2-13 | `evaluate …eval-partial-tests…` | 3 | `verdict=INCOMPLETE`；按组/域报告，完成率不掩盖阻断 | `3f21897` | PASS（预期） |
| M2-14 | `evaluate …eval-synthetic-only…` | 3 | `verdict=SYNTHETIC_ONLY`、`hardware_pass=false`；全 synthetic 不升级为硬件 PASS | `3f21897` | PASS（预期） |

### 7.4 M3 专属测试与冻结基准

| # | 命令 | 退出码 | 关键输出摘要 | 对应 HEAD | 结论 |
|---|---|---|---|---|---|
| M3-1 | `python -m unittest discover -s tests/bringup_planner_tests -p "test_*.py" -q` | 0 | **Ran 172 tests，OK**（20.5 s） | `3f21897` | PASS |
| M3-2 | `python benchmarks/bringup-planner/run_benchmark.py --json --out <tmp>` | 0 | `ok=true`；34/34 场景、5/5 holdout、2/2 案例、**41/41** 总通过；类别 **30/30**；`baseline.json` 90 files checked、0 mismatch；约 18.6 s | `3f21897` | PASS |
| M3-3 | 基准内 holdout（对象排序/单位换算/notes 同义/无关模块/revision 变化） | 0 | 5/5 `pass`；变形由 runner 通用执行，不按 ID 特判 | `3f21897` | PASS |
| M3-4 | 基准内组合板案例（mcu-sensor-board / load-control-board） | 0 | 2/2 `pass`；评估 verdict 覆盖 PASS/FAIL/INCOMPLETE/INVALID/SYNTHETIC_ONLY | `3f21897` | PASS |

### 7.5 M4 仓库回归、文档与路径审计

| # | 命令 | 退出码 | 关键输出摘要 | 对应 HEAD | 结论 |
|---|---|---|---|---|---|
| M4-1 | `python tools/offline_suite.py`（PR #39 合并源） | 0 | `status=pass`；1783 tests；0 failures / 0 errors / 0 blocked events | `b407d72` | PASS |
| M4-2 | `python tools/offline_suite.py`（2026-10-28 采集快照 `3f21897`） | 1 | 历史快照：`status=fail`；2147 tests；0 failures；**47 errors**（全部来自其他任务测试包：`change_impact` 9、`circuit_blocks` 7、`delivery_audit` 7、`electrical_review` 5、`procurement_planner` 5、`return_path_audit` 8、`skill_knowledge_audit` 6；**`bringup_planner_tests` 0 error**）。**该状态已由后续集成修复，最新 main 见 M4-5** | `3f21897` | 历史 FAIL（当时外部原因，已修复） |
| M4-3 | `python design-hardware/scripts/skill_selftest.py` | 0 | `5 PASS, 0 FAIL, 0 NOT RUN -> exit 0`（python-compile 242 scripts） | `3f21897` | PASS |
| M4-4 | 检查 `docs/parallel-bringup-planner/` 产物 | 0 | 10 个 Markdown 文档 + `evidence-m0-m4.json` 均在；PR 范围审计 175 files / 允许路径外 0 | `3f21897` | PASS |
| M4-5 | `python tools/offline_suite.py`（最新 main） | 0 | `status=pass`；**3318 tests**；0 failures / 0 errors / 0 blocked events；`bringup_planner_tests` 172 tests 包含在 discovery 中且全通过 | `c54c6fc` | PASS |

### 7.6 仪器 / 上电 / 烧录 / EDA（NOT RUN）

| 项目 | 命令 | 退出码 | 关键输出摘要 | 对应 HEAD | 结论 |
|---|---|---|---|---|---|
| 电源、万用表、示波器、电子负载连接与测量 | 无（任务边界禁止） | — | 未连接、未读数、无证据 | — | **NOT RUN** |
| 首次上电、限流、放电、电压/纹波实测 | 无（任务边界禁止） | — | 未上电、未测量 | — | **NOT RUN** |
| 固件烧录、串口/JTAG、USB 枚举 | 无（任务边界禁止） | — | 未烧录、未访问串口/JTAG | — | **NOT RUN** |
| EDA 调用（含只读）、工程上传、购买设备 | 无（任务边界禁止） | — | 未调用 EDA、未上传/购买 | — | **NOT RUN** |
| 实物功能、EMC、温升、可靠性、量产一致性 | 无（任务边界禁止） | — | 无实物/环境证据 | — | **NOT RUN** |
| 执行任何生成步骤或自动测试 | 无（任务边界禁止） | — | 计划步骤全部 `manual_only`，工具不执行 | — | **NOT RUN** |

### 7.7 结论与备注

- 本任务范围内软件证据：**34 项 PASS**（含最新 main 复跑 M4-5）、**0 项当前 FAIL**；M4-2 是 2026-10-28 采集快照的外部 FAIL，已由后续集成修复。**6 类硬件/仪器动作 NOT RUN**。逐项见 7.1–7.6；机器可读证据见 `evidence-m0-m4.json`（历史采集快照，不含 M4-5 复跑）。
- `eval-pass-real-evidence` 的 PASS 是**评估器契约 fixture**（证据文件明确写有 "NO INSTRUMENT WAS CONNECTED"），只证明评估器在"真实测量声明+证据"下的一致性判定，**不是**真实上电/功能 PASS。
- **已知契约措辞差异（M2-7）：** 畸形 JSON 时 `plan` 退出 2 且不写计划，但未写 `input-invalid.json`；`input-invalid.json` 目前只在"可解析但 schema 非法"的文档路径写出。已在 `issue-candidates.md` B.4 记录，未在本任务中改实现。
- **跨任务回归（M4-2 → M4-5）：** 2026-10-28 采集快照中 `offline_suite` 的 47 个 errors 来自其他并行任务的测试包发现方式；后续集成已修复。最新 main `c54c6fc` 复跑 `offline_suite` 为 **PASS：3318 tests / 0 errors**，`bringup_planner_tests` 172 tests 全通过。`issue-candidates.md` A.6 已标记为“已修复”，无需再处理。
- 采集时 `origin/main` 持续前进（`acbcc18…`）；本清单的 HEAD 列固定为实际运行所用的 worktree HEAD `3f21897`，PR 范围审计固定为 `9a951ed...b407d72`。
