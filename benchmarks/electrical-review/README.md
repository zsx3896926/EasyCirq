# electrical-review 冻结 CLI 基准

本目录是任务 B“离线电气意图审查”的可重复基准。每个场景的输入是冻结 JSON；
驱动器通过**真实 CLI 子进程**运行 `python -m electrical_review review`，不调用内部
Python API 来下结论。**0 次 EDA 调用，不联网。**

## 运行

```bash
cd <repo root>
python benchmarks/electrical-review/run_benchmark.py --runs 3
```

输出写入 `benchmarks/electrical-review/result.json`，包含：

- `correctness`：逐场景 exit code、status、summary totals、规则计数、必需 finding 是否命中、
  输入 SHA-256 是否仍等于冻结值；
- `coverage`：31 个场景、六组规则、正/反/unknown/incomplete/invalid 分布、来源类别；
- `timing`：真实 CLI 子进程 wall clock 的 min/median/max；**只证明审查执行成本，
  不代表画板提速**；
- `simulated: true`、`real_eda: "NOT RUN"`、`eda_calls: 0`；
- `not_covered`：真实 EDA/DRC/保存重开/仿真/铜/热/EMC/制造/上电等。

## 场景（31 个，冻结于 2026-10-27）

| 类别 | 场景 |
|---|---|
| R1 飞跨/耦合电容 | `r1-flying-ok`（正确）、`r1-flying-short`（两端同网）、`r1-flying-wrong-net`（错接）、`r1-flying-unknown-net`（信息不足） |
| R2 耐压/应力 | `r2-overvoltage-hard`（16 V vs 24 V）、`r2-derating-shortfall`（项目 0.8 降额）、`r2-switching-unknown`（开关节点 unknown）、`r2-dc-derived-ok`（DC 区间推导） |
| R3 四脚按键 | `r3-switch-ok`、`r3-always-closed`（1–2 常通）、`r3-pressed-power-short`、`r3-internal-unknown` |
| R4 特殊引脚/电源域 | `r4-pin-role-conflict`（TPS62130 PG 开漏 vs push-pull）、`r4-supply-overvoltage`（24 V vs 3–17 V）、`r4-open-drain-pullup-ok` |
| R5 裸焊盘/合并焊盘 | `r5-exposed-pad-ok`、`r5-exposed-pad-missing`（EP 缺失）、`r5-exposed-pad-wrong-net`、`r5-ams-tab-ok`、`r5-ams-tab-missing`（SOT-223 TAB）、`r5-no-pad-fact`（不默认要求中心焊盘） |
| R6 角色/局部布置 | `r6-local-ok`、`r6-local-too-far`（200 mil > 项目 150 mil）、`r6-bulk-exempt`、`r6-geometry-missing` |
| 真实工程只读重放 | `real-mcu-i2c-ams-tab`（由仓库冻结 mcu-i2c 证据离线派生）、`real-mcu-i2c-ams-tab-split`（反例变异，明确标注） |
| 非法输入 | `invalid-nan`、`invalid-duplicate-ref`、`invalid-unit`、`invalid-contradiction` |

`expected.json` 冻结每个场景的：输入原始字节 SHA-256、预期退出码/status/summary、
规则计数、必需 finding code、来源类别与推导依据（`basis`）。修改输入即哈希失配，
基准会失败而不是“通过”。

## 证据类型

- `synthetic_fixture` / `synthetic_fixture_verified_fact`：合成工程，引用原厂事实；
- `real_engineering_read_only_replay_derived`：仓库内真实工程证据的离线派生重放；
- `derived_counterexample_mutation`：在重放上做反例变异；
- `synthetic_invalid_input`：非法输入负例。

原厂事实（ALPS SKHH 四脚按键、TI TPS62130 EP/PG、TI MAX3232 C1、AMS1117 TAB）的来源、
版本、页码与 PDF SHA-256 见 `docs/parallel-electrical-review/sources.md`。

## 结果口径

- `correctness` 只说明“审查工具在冻结输入上的判断与人工核对预期一致”；
- `pass_with_scope` 只证明所列规则和输入范围，不表示整板/制造/上电正确；
- timing 不宣称比旧版本或画板流程快，也不把审查耗时当 PCB 布局提速；
- 本基准不替代任务 A 的真实小板验收。

## 未覆盖

真实 EDA CLI/daemon/connector、原生 DRC/check、保存重开、仿真、Gerber/CPL/钻孔/DFM、
实际布线、铺铜连通、热/EMC/安规/固件、实物功能、制造与上电验收。
