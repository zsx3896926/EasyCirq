# 并行任务 I 报告：首板上电、功能测试与故障定位计划生成器

> 分支 `feat/parallel-bringup-planner`（独立 worktree `hds-bp-worktree`，基线 `main@9a951ed`）。
> 本报告中的"通过"均指**离线文档/CLI 一致性验收**；真实仪器、上电、烧录、串口/JTAG、EDA 操作全部 **NOT RUN**。

## 1. 交付概览

| 交付 | 位置 |
|---|---|
| 可运行 CLI（validate/plan/explain/evaluate） | `design-hardware/scripts/bringup_planner/` |
| 六组能力 I1–I6 | `poweroff.py`、`powerup.py`、`measurements.py`、`interface_tests.py`、`faults.py`、`evaluate.py` |
| 契约/范围/资料/测量纪律/验收/集成/交接文档 | `docs/parallel-bringup-planner/` |
| 专属测试 172 个 | `tests/bringup_planner/` |
| 34 个 CLI 冻结场景 + 5 holdout/变形 + 2 组合板案例 + runner | `benchmarks/bringup-planner/` |
| 一手资料 11 源 / 143 facts（78 条带页码） | `benchmarks/bringup-planner/sources/device-facts.json`、`source-register.md` |

## 2. 环境与基线

| 项 | 值 |
|---|---|
| 基线 main | `9a951edc21481dc3ae91460acc11aa3e08a7be8a`（origin/main 相同，开工时核对） |
| 分支 | `feat/parallel-bringup-planner` |
| Python（本地实测） | 3.13.15（仓库目标 3.10+；仅用标准库，未引入新依赖/锁文件） |
| 离线约束 | 无 EDA、无仪器、无串口/JTAG、无烧录、无 shell 执行计划步骤、无网络（基准与测试） |

## 3. 软件实测结果

### 3.1 专属测试

```bash
python -m unittest discover -s tests/bringup_planner -p "test_*.py"
# Ran 172 tests ... OK
```

覆盖：输入校验/单位/哈希不变性/CLI 边界（`test_contract`）、I1/I2（`test_poweroff`/`test_powerup`）、I3/I4（`test_measurements`/`test_interface_tests`）、I5/I6（`test_faults`/`test_evaluate`）、基准（`test_benchmark`，真实子进程跑 freeze 基准）。

### 3.2 冻结 CLI 基准（真实子进程）

```bash
python benchmarks/bringup-planner/run_benchmark.py --json --out /tmp/bringup-benchmark.json
```

实测结果（本机）：

| 指标 | 结果 |
|---|---|
| 场景 | **34 passed / 34** |
| holdout | **5 passed / 5** |
| 组合板案例 | **2 passed / 2** |
| 总用例 | **41 / 41 pass** |
| 必需类别覆盖 | **30 / 30**（任务书第 8 节全部类别 + 组合/变形） |
| 输入/证据/计划/结果冻结 | `baseline.json` 90 个文件 SHA-256 |
| 运行耗时 | 约 17.5 s（本机，单次） |
| 失败 | 0 |

每个场景真实启动 `python -m bringup_planner validate|plan|explain|evaluate` 子进程，比较退出码、scope、DAG order/cycles、冻结 step_id 全集与逐步骤状态、gap/unknown/equipment_gap codes、评估 verdict；holdout 变形（对象排序、mV↔V、notes 同义改写、无关模块、revision 变化）由 runner 通用执行，不按场景 ID 特判。

### 3.3 仓库既有回归

```bash
python tools/offline_suite.py
# status: pass, tests_run: 1783, failures: 0, errors: 0

python design-hardware/scripts/skill_selftest.py
# 5 PASS, 0 FAIL, 0 NOT RUN -> exit 0
```

（`tools/offline_suite.py` 不会发现 `tests/bringup_planner/`：该目录没有 `__init__.py`，避免 discovery 把测试包误当产品包 `bringup_planner`；专属测试用上面的 `unittest discover` 入口运行，见 `issue-candidates.md`。）

### 3.4 CLI 样例（组合板）

| 案例 | scope | 步骤 | ready | blocked | plan SHA-256（示例运行） |
|---|---|---|---|---|---|
| `cases/mcu-sensor-board`（USB-C 5V→AMS1117 3V3→MCU/I2C/ADC） | supported | 23 | 13 | 10 | `e22a20bc…` |
| `cases/load-control-board`（5V 低边驱动 LED/蜂鸣器 + 比较器/NTC） | supported | 15 | 9 | 6 | `2f417fda…` |

计划 SHA 只用于示例；正式绑定以各次生成的 `plan.json` 内 `hashes.plan_sha256` 为准。

### 3.5 评估器 verdict 覆盖（冻结 eval 场景）

| 场景 | 退出码 | verdict | hardware_pass |
|---|---|---|---|
| `eval-pass-real-evidence` | 0 | PASS | true |
| `eval-stop-propagation` | 1 | FAIL | false |
| `eval-stale-revision` | 2 | INVALID | false |
| `eval-unit-conflict` | 2 | INVALID | false |
| `eval-missing-evidence` | 3 | INCOMPLETE | false |
| `eval-partial-tests` | 3 | INCOMPLETE | false |
| `eval-synthetic-only` | 3 | SYNTHETIC_ONLY | false |

评估器要求：plan/input/revision/tool_version 绑定一致；`pass` 需实测值+单位兼容+范围内+required_evidence；证据路径越界/sha 不符→INVALID；证据不可得/缺测→最多 INCOMPLETE；STOP 传播阻断依赖；全 synthetic 不得升级为硬件 PASS。

## 4. 六组能力实现对照

| 能力 | 关键实现 | 验收场景 |
|---|---|---|
| **I1 断电检查与前提** | 目视/装配/DNP/跳线/连接器方向；外部供电路径断开；放电步骤；电阻/二极管档限制说明；无 `short_check_criterion` 时不输出欧姆阈值（`needs_interpretation`） | `deenergized-measurement-preconditions`、`no-short-check-criterion`、`dnp-module` |
| **I2 首次上电与分域顺序** | 域 DAG 拓扑顺序；每域上电步依赖前级验证与断电检查；限流仅来自 `current_limit_policy`/启动电流/保护；缺依据 blocked；观察窗无依据不编秒数；可拆负载/外部供电/烧录前提分步；STOP 阈值全部溯源 | `power-sequence-three-rails`、`missing-startup-current`、`inrush-current-limit`、`missing-observation-window`、`external-usb-backfeed` |
| **I3 电源/时钟/复位/通信** | 测点+参考地+工作范围；纹波/时钟需带宽/探头能力，缺则 blocked+equipment gap；电压合格≠纹波合格；ADC 读值≠精度；固件/主机前提；未烧录时不期待业务通信 | `normal-mcu-sensor-board`、`missing-probe-bandwidth`、`firmware-not-flashed`、`missing-testpoint`、`insufficient-equipment` |
| **I4 负载与接口** | 仅按声明负载/限值生成；BTL/桥式/非地参考禁止单端接地，缺差分→blocked；I2C/SPI 需总线前提；模拟输入不默认满量程；典型值不充当保证值 | `btl-wrong-grounding`、`unknown-load`、组合案例 |
| **I5 故障树与 STOP** | 有限节点树（≤12），顺序：供电/连接→模式/固件→局部测量；每分支有证据/可判定条件；缺测 unknown；STOP 仅项目已知阈值+定性立即停止；STOP 后依赖 blocked | 所有计划场景；`eval-stop-propagation` |
| **I6 结果记录与评估** | 独立结果契约；版本/哈希绑定；synthetic/real/manual 区分；单位/范围/证据一致性；STOP 传播；部分通过按组/域报告；完成率不掩盖阻断 | 7 个 eval 场景 |

## 5. 数据严格性与确定性

- 校验覆盖：重复 JSON key、NaN/Infinity、bool 冒充数字、未知单位、倒置范围、负电流/电阻、工作电压高于绝对最大、未来时间、缺 revision、附件路径越界、重复 step/域/测点 ID、DAG 自依赖/缺依赖/环路、角色冲突、设备能力不足、evidence revision 不一致（警告）。
- 哈希：原始输入 SHA、归一化语义 SHA、计划 SHA（排除时间/输入路径/自由文本）；`manifest.json` 记录全部产物 SHA。
- 确定性/变形：对象排序、mV↔V/mA↔A、notes 同义改写不改变语义哈希与计划哈希；无关模块只新增自身步骤；revision 改变使旧结果绑定失效。
- 输出：JSON/Markdown/CSV/结果模板均为原子写；非法输入不写计划、清理旧生成物并写 `input-invalid.json`；stdout 纯 JSON（`--json`）/stderr 诊断；退出码 0/1/2/3 固定。
- 生成计划不执行任何操作：所有步骤 `execution=manual_only`、`auto_execute=false`。

## 6. 一手资料

11 个官方来源、143 条 facts（78 条有精确页码），抽样：

| 来源 | 类型 | 已核实内容（示例） |
|---|---|---|
| TI TPS62130 数据手册 SLVSAG7F | 器件 | §7.1 p4 绝对最大（AVIN/PVIN 20 V、TJ 150 °C）、§7.5 p5 IQ 17 typ/30 max µA、UVLO 2.7 V、热关断 160 °C |
| Espressif ESP32-C3 数据手册 v2.4 | 器件 | §5.1 p54 输入电源绝对最大 3.6 V、§5.2 p54 推荐 3.0/3.3/3.6 V、§5.4 p55 I/O DC 电平、p28/p30 复位/strapping 时序 |
| TI CSD17578Q3A、TLV700、LM393 | 器件 | VGS(th)/RDS(on) 条件、LDO 范围、比较器输入范围（部分页码级引用缺失，标 unverified） |
| Fluke 87/83/85 用户手册 PN 834192 Rev.8 | 仪器方法 | p20 断电+放电、显示值为"所有可能路径总电阻"（低阻≠短路的官方依据）；p23 二极管档 0.6 mA、最多五结 |
| Rigol DS1000Z User Guide/Datasheet | 仪器方法 | p4 探头地线必须接地、p31/p32 探头补偿、p6 1 MΩ∥15 pF、CAT I 300 Vrms、p7 上升时间/DC 增益 |

仍标 `unverified`：TPS62130 100% 占空比段落、LM393/TLV700 部分绝对最大表页码、CSD 雪崩能量/热阻、Fluke 87V 专属指标（87V 手册 403）、Rigol 修订字母/探头负载电容。未编造数值，未把手册打包进仓库。

## 7. 场景与 holdout

- 34 个标准场景覆盖任务书第 8 节全部类别（正常小板、电源顺序、环路、缺启动电流、浪涌/限流、USB 回灌、断电前提、缺测点、缺探头/带宽、DNP、未烧固件、BTL 错误接地、负载不明、STOP、部分测试、旧 revision、单位冲突、证据缺失、合成、非法输入、设备不足、范围外、未声明操作、组合正/负/缺信息、组合部分完成）。
- 5 个 holdout：对象排序、单位换算、notes 同义改写、无关模块增加、revision 变化；runner 通用变形，不按 ID 特判。
- 2 个组合板案例：低压 MCU 传感板、低压负载控制板；引用现有冻结设计只读信息，明确 synthetic design intent、无实物。
- `baseline.json` 冻结 90 个输入/证据/计划/结果文件 SHA-256；`--update-baseline` 才会更新。

## 8. 已修问题（集成/审查中发现）

1. `tests/bringup_planner/__init__.py` 使仓库 `offline_suite` discovery 把测试包误当产品包，8 个 ImportError → 移除该 `__init__.py`，专属测试用独立入口。
2. 计划哈希原包含原始输入 SHA，导致对象重排/单位换算改变哈希 → 改为只绑定归一化语义哈希（仍绑定 revision）。
3. `notes` 自由文本参与语义哈希 → 递归剔除 `notes`，同义改写不影响判据。
4. 非法输入时先写 `input-invalid.json` 再清理生成物，会把 invalid 标记也删掉 → 调整为先清理后写。
5. CLI 缺 `import os` 导致 `manifest.json` 生成崩溃 → 修复。
6. 未来时间戳归一化返回 datetime 导致 JSON 序列化失败 → 统一存 ISO-8601 UTC 字符串。
7. `--evidence-root` 下证据文件缺失被当作整板 INVALID → 降为 warning/unknown（INCOMPLETE）；只有路径越界/sha 不符/绑定/schema/单位矛盾才 INVALID。
8. holdout 语义哈希比较取错字段（validate 公开视图无 `semantic_sha256`）→ 从计划输入语义哈希取。
9. `scope.required_operations` 漏 `analog_output` → 补 `analog_measurement` 需求。
10. `PlanContext` 未初始化 `scope/dag/supply_conflicts`，直接按 API 使用会 AttributeError → 给默认值。
11. I3/I4 原本只用条件文本依赖 I2/I1 → 要求改为真实 step 依赖，保证 STOP 传播可阻断（由能力模块修正并回归）。
12. 证据路径前缀与 `--evidence-root` 语义不一致 → bench 冻结结果统一为相对证据根的路径；README/契约写明。

## 9. 未执行与限制（NOT RUN）

- 未连接任何电源/万用表/示波器/电子负载；未上电；未烧录固件；未访问串口/JTAG；未调用 EDA（含只读）；未执行任何生成步骤；未购买/上传工程。
- 不证明：焊好的板能工作、读数真实、测点真实可达、安规/EMC/温升/可靠性/量产一致性。
- 首期范围：仅低压直流（≤30 V 工作 / ≤60 V 绝对）；市电、高压、电池充放电、复杂射频标 unsupported/needs_specialist。
- 已知 schema 缺口（不影响当前验收，记录于 `issue-candidates.md`）：纹波/瞬态限值、探头耦合/负载的结构化字段、差分探头能力、每接口结构化负载电流/器件限值、clock/reset 信号 role、固件是否已烧录的机读状态；当前以 `notes`/`measurement.basis` 文本承载并保持 blocked/unknown 纪律。
- 未做跨 Python 版本实测（本机仅 3.13；代码只用标准库且未使用 >3.10 语法，仍建议 CI 覆盖 3.10/3.13）。

## 10. 复现命令

```bash
cd design-hardware/scripts
python -m bringup_planner validate --input <input.json> --json
python -m bringup_planner plan --input <input.json> --out <out-dir> --json
python -m bringup_planner evaluate --plan <out>/plan.json --results <results.json> \
    --evidence-root <evidence-dir> --out <out2> --json

cd <repo-root>
python -m unittest discover -s tests/bringup_planner -p "test_*.py"
python benchmarks/bringup-planner/run_benchmark.py --json --out /tmp/bench.json
python tools/offline_suite.py
python design-hardware/scripts/skill_selftest.py
```

## 11. 路径与变更核对

`git status` 仅包含允许路径：

```
benchmarks/bringup-planner/
design-hardware/scripts/bringup_planner/
docs/parallel-bringup-planner/
tests/bringup_planner/
```

未修改 `SKILL.md`、现有 `references/`、README/CHANGELOG/版本/主 handoff、runtime/connector/protocol、distribution、CI、顶层依赖、feedback、compose、design_engine 或其他任务目录。

## 12. 提交与 PR

- 分支：`feat/parallel-bringup-planner`
- 基线：`main@9a951ed`（见第 2 节）
- 提交/PR 链接：见 PR 描述（本任务只推送独立 PR，不合并、不发布、不安装客户端）。
