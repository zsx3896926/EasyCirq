# 验收记录（任务 B，2026-10-27）

## 1. 基线与环境

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/zsx3896926/EasyCirq |
| 固定基线 main SHA | `9a951edc21481dc3ae91460acc11aa3e08a7be8a`（开工时核实） |
| 最终验收 main SHA | `acbcc18c821e08ddff2401015eb7a16eaee733c8`（含 #48/#52） |
| 分支 / worktree | 任务 B 分支已由 #48/#52 合入 main；本文件更新于 docs-only worktree |
| 操作系统 | Windows 11 10.0.26200 SP0（AMD64） |
| Python（本机实际运行） | **3.13.15** |
| 最低 Python 声明 | 3.10（仓库 CI 矩阵包含 3.10/3.13） |
| 3.10 验证状态 | **已验证**：仓库 CI `validate (3.10)` 在 #48、#52 及本 docs-only PR 均通过 |
| 依赖 | 仅 Python 标准库；未新增任何依赖，未改顶层依赖文件 |
| EDA 调用 | **0**（未调用 easyeda CLI/daemon/connector，未切换窗口/刷新页面/安装扩展） |
| 网络 | 仅用于原厂/官方资料核验；审查模块自身不联网 |

## 2. 实际执行命令

在 worktree 根目录（`docs/` 中的命令均可在仓库根复现）：

```bash
# 1) CLI 自检（从 easycirq/scripts 运行）
cd easycirq/scripts
python -m electrical_review --version
python -m electrical_review validate ../../benchmarks/electrical-review/cases/r1-flying-ok/input.json
python -m electrical_review review   ../../benchmarks/electrical-review/cases/r2-overvoltage-hard/input.json --out /tmp/report.json
python -m electrical_review explain  /tmp/report.json --rule R2

# 2) 专属测试（被现有 discover 识别，也可独立运行）
cd ../..
python -m unittest discover -s tests -k electrical_review
python -m unittest discover -s tests/electrical_review -t tests

# 3) 全量现有测试（确认未破坏仓库既有测试）
python -m unittest discover -s tests

# 4) 冻结 CLI 基准（实际子进程；0 EDA）
python benchmarks/electrical-review/run_benchmark.py --runs 3
```

## 3. 测试结果（实际）

| 项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -k electrical_review` | **55 tests OK**（3.579 s） |
| `python -m unittest discover -s tests/electrical_review -t tests` | **55 tests OK** |
| `python -m unittest discover -s tests`（全量） | **3144 tests OK（skipped=2）**，314.0 s，exit 0 |
| 独立审查修复 | 仓库 Codex 独立审查 P1/P2 已由 #52 修复并补回归测试（pad_nets 冲突、按键外部旁路） |
| 测试语料 | 规则夹具 + 变形/契约/CLI/基准检查；覆盖 R1–R6 正例、反例、unknown、非法输入、单位/排序/重命名/短接变形、旧 PASS 覆盖 |

覆盖的具体负例：

- 重复 `instance_id`/位号/脚号/焊盘映射、空输入、遗漏网络、同一 ID 不同对象；
- `pin.net` 与 `connectivity.pin_nets` 矛盾、未知网络引用；
- NaN/Infinity/bool 冒充数字、负耐压、未知单位、非法 JSON 键重复；
- 器件封装/修订不匹配时不得套用事实；
- `--out` 覆盖旧 PASS 时写入 invalid_input 报告；
- 一次性把正确飞跨电容短接必触发 `flying_capacitor_shorted`。

## 4. 冻结 CLI 基准结果

`benchmarks/electrical-review/result.json`（`--runs 3` 最终结果）：

| 指标 | 值 |
|---|---|
| `status` | **pass** |
| correctness | **31 / 31** 场景通过 |
| 场景构成 | pass_with_scope / fail / review_required / incomplete / invalid_input 五类齐备 |
| 来源类别 | synthetic_fixture、synthetic_fixture_verified_fact、real_engineering_read_only_replay_derived、derived_counterexample_mutation、synthetic_invalid_input |
| 规则覆盖 | R1–R6 全部有正/反/unknown 场景 |
| `simulated` | true |
| `real_eda` | **"NOT RUN"** |
| `eda_calls` | **0** |
| 输入 SHA-256 | 每个场景冻结；源文件被改动则基准失败（不是“通过”） |
| timing | 31 个场景（3 runs）单场 min 合计 4.862 s；单场 max 193.0 ms；Python 3.13.15 / Windows 11 / AMD64 |
| 未覆盖 | 真实 EDA/DRC/保存重开/仿真/Gerber/CPL/钻孔/DFM/布线/铺铜/热/EMC/安规/固件/制造/上电 |

**timing 只说明本书审查工具的 CLI 执行成本，不宣称画板提速；整板验收由任务 A 的真实小板实测。**

## 5. 资料核验结果

| 类别 | 结果 |
|---|---|
| 四脚按键内部常通组 | **✓** ALPSALPINE SKHHAKA010（Top push，4 端子）：1–2 常通、3–4 常通、按下接通两组；C&K PTS645 S/T 独立旁证；官方 URL/页/PDF SHA-256 见 sources.md |
| 电源类芯片裸/合并焊盘 | **✓** TI TPS62130（VQFN-16 RGT）：EP pin17 必接 AGND/PGND/地平面并焊接；TI SLVSAG7F p.3/p.28 |
| 合并焊盘 | **✓** AMS1117-3.3 SOT-223：TAB IS OUTPUT（TAB=VOUT），不是 GND；原厂 p.1 |
| 明确飞跨电容/特殊引脚 | **✓** TI MAX3232：C1 飞跨在 C1+(1)/C1−(3)，SLLS410O Table 5-1；PG/开漏与供电域由 TPS62130 事实覆盖 |
| MCP23017 | **部分更正**：实际文档 DS20001952D 已核验；任务书 DS20001921E 未证实，不硬编码、不使用 |
| 未取得 | Omron B3F/B3FS、NKK JB、Würth 434（403）；Panasonic 工业站（000）；已在 sources.md 记录障碍，不作为完成依据 |

## 6. 零 EDA / 零副作用核查

- 模块源码不 `import` requests/urllib/socket/easyeda 等网络/EDA 调用；只读文件。
- 未执行任何 EDA 命令；未切换窗口、刷新页面、安装扩展、改全局环境、停后台进程。
- 未修改允许范围外文件；未改 SKILL.md、references、feedback、design_engine、pcb_gate、
  runtime、connector、protocol、distribution、更新器、CI、顶层依赖、版本号、LICENSE/NOTICE、
  README、CHANGELOG、docs/handoff-current.md。
- 未自行合并 PR、未发布版本、未安装到用户客户端；#48/#52 的合入由主维护者完成。

## 7. 已知未完成/未验证

- 原厂事实只覆盖上述型号/封装/修订；未内置资料库，换型号必须重新提供 facts。
- R2 不建模波形/瞬态/负压/开关节点；R6 只测 Euclidean 距离，不证明回流/ESL/EMI。
- Omron/NKK/Würth/Panasonic 候选未取得原厂 PDF（网络限制），不冒充已核验。
- 真实小板验收、原生 DRC、保存重开、制造与上电不在本任务范围。
- 独立反例审查成员运行失败；仓库 Codex 独立审查发现的 P1/P2 已修复（#52），说明自审
  不能替代独立审查。
