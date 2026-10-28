# 变更影响基准（benchmarks/change-impact）

本目录是 J（ECO 变更影响分析与增量验证计划）的**冻结 CLI 基准**：50 个用例
真实以子进程运行 `python -m change_impact`，输入与期望断言都提交到仓库并记录
SHA-256，任何改动都会被检测。

**这些输入全部是合成的（`simulated: true` / `source_type: simulated_synthetic`），
不是真实工程数据。** 基准只证明工具在该声明模型上的推断与计划行为一致，不证明任何
实际板子正确，也不代表真实 EDA 运行时间。

## 目录

| 路径 | 内容 | 数量 |
|---|---|---|
| `scenarios/` | 单点变更分析场景 | 25 |
| `scenarios/invalid/` | 非法输入（期望退出码 2 + `input_invalid`） | 11 |
| `composite/` | 完整组合案例（低压 MCU 传感板、接口/壳体控制板） | 2 |
| `holdout/` | 与训练场景不同组合的 holdout | 4 |
| `variants/` | 变形（排序、同义显示名、单位换算、无关子图、成本膨胀、移除覆盖边） | 6 |
| `compare/` | 多候选 ECO 比较输入 | 2 |
| `expected/` | 每个用例**独立推导**的断言（含 `derivation`） | 50 |
| `manifest.json` | 冻结 SHA-256、分组计数、NOT RUN 声明 | 1 |
| `build_scenarios.py` | 确定性生成器（`--check` 可校验可重建） | — |
| `run_benchmark.py` | 真实 CLI 子进程 runner | — |

## 运行

```bash
# 校验并运行全部用例（需要 Python 3.10+，仅标准库）
python benchmarks/change-impact/run_benchmark.py

# 只跑某类
python benchmarks/change-impact/run_benchmark.py --only power_

# 重新冻结（重写输入/断言/manifest，仅在刻意修改语料时使用）
python benchmarks/change-impact/run_benchmark.py --freeze
```

runner 行为：

1. 先校验每个输入与 expected 文件的 SHA-256 与 `manifest.json` 一致（防篡改/
   防漂移）。SHA 基于 **LF 归一化**后的内容计算，因此 Windows（`core.autocrlf`）
   与 Linux 检出结果一致，不会因换行风格误报；
2. 以 `PYTHONPATH=<repo>/easycirq/scripts`、`cwd=<repo>` 运行
   `python -m change_impact analyze|compare <input>`；
3. 断言：退出码、总体状态、`impacted_objects` 的对象/影响/置信度/来源变更、
   `must_not_impact`（不得无依据传播）、`required`/`blocked` 检查、证据状态、
   `unknown` 代码、覆盖缺口数、循环报告、预算截断；
4. stdout 输出机器 JSON 汇总（含 `timing_ms`），stderr 输出人类摘要；全部通过
   退出码 0，否则 1。

## 断言是独立推导的，不是倒填输出

`expected/*.json` 的每个用例都带 `derivation` 字段，说明期望影响链来自哪条传播
规则（R1–R17 见 `docs/parallel-change-impact/propagation-rules.md`）与依赖语义，
例如：

- 5V→3.3V 只沿 `power_supply` 到 MCU，不因 `firmware_consumer` 边把固件判为
  certain；
- 显示文字移动只到 `documentation_only`，不使固件/采购失效；
- 测试判据变化只到需求追踪与测试本身，不扩散到无关电气对象；
- 接口 pose/板框变化即使网络不变，也影响壳体锚点与贴装/制造产物；
- 证据在候选 revision+hash 上 → `reusable_bound`；覆盖对象实际受影响且无可验证
  绑定 → `invalidated`；模拟证据永远不能充当宿主/实物通过。

`variant_remove_coverage_*` 额外断言 `gaps + unknown` 数量不得下降：**信息减少
不能把 unknown 变成已证明安全**。

## Timing 口径

`timing_ms` 只测量本地离线 CLI（含进程启动）耗时，用于检测性能回归。
**它不是 EDA 运行时间，也不能用来宣称缩短真实 EDA/DRC/制造时间。**

## 明确 NOT RUN

`eda_read`、`eda_write`、`host_drc`、`save_and_reopen`、`official_plot`、
`physical_test`、`manufacturing_order` 均 **NOT RUN**。基准不连接 EDA、不调用
执行器/Connector/仪器、不烧录、不上电、不下单。

## 覆盖能力对照

| 用例 | 能力 | 关键断言 |
|---|---|---|
| `display_text_move` | J2 显示边界 | 只 documentation_only；不波及固件 |
| `net_rename` | J1/J2 重命名 vs 分区 | 重命名不短路；partition 证据存在 |
| `led_resistor_value` | J2 参数传播 | 电阻→LED 网络+电流测试 |
| `power_5v_to_3v3` | J2 电源范围 | 电源语义边界；固件不 certain |
| `ldo_replacement` | J2 实例替换 | 封装/CPL 影响；同封装不证明电气等价 |
| `mcu_instance_change` | J2 实例替换 | 固件契约+CPL+布局 |
| `mcu_pin_remap` | J2 引脚重映射 | 引脚网络+固件 |
| `mcu_footprint` | J2 封装 | 布局/机械/制造 |
| `usb_position` | J2 接口 pose | 壳体/CPL 影响；固件与测试不无依据传播 |
| `board_outline` | J2 板框 | 机械配合+制造 |
| `differential_layer` | J2 叠层 | 信号完整性+制造；测试边界 |
| `dnp_config` / `bom_substitute` | J2 交付配置 | BOM 变体+CPL |
| `firmware_contract` / `test_threshold` / `requirement_change` | J2 契约/测试/需求 | 各自消费者；不跨域扩散 |
| `evidence_reuse_positive/negative` | J3 | reusable_bound / invalidated |
| `partial_snapshot` / `unauthorized_observed` / `unknown_attribute` | J1/J6 未知边界 | incomplete + 明确 unknown |
| `cyclic_dependency` | J2 循环 | 报告 cycles 且收敛 |
| `missing_coverage` | J4 | 报 gap，不用无关检查凑 |
| `budget_exhaustion` | J2/J4 预算 | truncated/incomplete/frontier |
| `compare_*` | J5 | 硬约束优先、未知更多更便宜者不得胜出 |
| `invalid_*` | J7 严格性 | 退出 2 + `input_invalid` + issue code |
| `composite_*` | 组合 | 多变更叠加、宿主/人工只计划 |
| `holdout_*` | 泛化 | 不同命名/结构，无场景 ID 特判 |
