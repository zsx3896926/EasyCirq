# 任务 B 交接：离线电气意图审查（handoff-current）

- 任务 B 分支 / PR：`feat/parallel-electrical-review` / **#38（CLOSED，内容由 #48 合入 main）**
- 后续修复：**#52**（独立审查 P1/P2，已合入 main）
- 固定基线：`main` @ `9a951edc21481dc3ae91460acc11aa3e08a7be8a`（开工时核实；未反复合入任务 A 分支）
- 本文件验收复验基于：`main` @ `acbcc18c821e08ddff2401015eb7a16eaee733c8`（含 #48 LF 修复与 #52 P1/P2 修复）
- 本文件由 **docs-only PR** 更新：只补验收记录与 3.10 CI 状态，不改产品代码
- 本任务真实 EDA 调用：**0**
- 共享文件修改：**无**（SKILL.md/references/feedback/design_engine/pcb_gate/runtime/connector/
  protocol/distribution/更新器/CI/顶层依赖/版本号/LICENSE/NOTICE/README/CHANGELOG/
  docs/handoff-current.md 均未改）
- 允许范围内新增：
  - `easycirq/scripts/electrical_review/`（模块 + CLI）
  - `tests/electrical_review/`（测试与夹具）
  - `benchmarks/electrical-review/`（31 场景冻结基准 + 驱动 + result）
  - `docs/parallel-electrical-review/`（本目录）
- 交付形式：独立 PR；主维护者已通过 #48/#52 合入 main。本文件不合并、不发 Release、不改版本、
  不安装到用户客户端。

## 1. 模块与命令

```bash
cd easycirq/scripts
python -m electrical_review validate ../../benchmarks/electrical-review/cases/r1-flying-ok/input.json
python -m electrical_review review   ../../benchmarks/electrical-review/cases/r2-overvoltage-hard/input.json --out /tmp/report.json
python -m electrical_review explain  /tmp/report.json --rule R2
```

退出码 / 整体状态：

| exit | status | 含义 |
|---|---|---|
| 0 | `pass_with_scope` | 所列规则 + 给定输入范围均证明满足，无 unknown |
| 1 | `fail` | 至少一条已证明硬性电气违反 |
| 2 | `invalid_input` | 输入/用法非法；不复用旧 PASS |
| 3 | `review_required` | 无硬违反，但有 unknown/证据不足/策略项 |
| 4 | `incomplete` | 无 intent、无可审查对象或规则因整段输入缺失未评估 |

输入/报告 schema：`zhigou.electrical-review.input/v1` / `.report/v1`。
报告含 `input.sha256`、`input.semantic_sha256`、逐规则 checked/violations/unknown/
not_applicable/invalid_input、finding 对象/实际值/约束/单位/证据/解释/建议/未验证项，
并强制列出 `not_checked`；`pass_with_scope` 不等于整板电气/DRC/制造/上电通过。

## 2. 六组规则（首期范围）

- **R1** 飞跨/耦合电容：只处理有证据的 flying 角色；按真实连通分区（含网名别名）比较端点；
  两端同网/错接 → hard；角色或网络缺失 → unknown。
- **R2** 电容耐压：有来源的额定耐压 vs 已声明差分应力或**可证明的 DC 区间**；
  硬超额 hard，项目降额不足 review；开关节点/负压/波形/单端替代 → unknown。
- **R3** 四脚按键：精确 MPN 原厂内部常通组 + 按下闭合关系；同组使用 → hard；
  按下电源端直连 → hard；内部结构未知 → review；只看脚号，不看符号左右。
- **R4** 特殊引脚/电源域：精确 MPN 的 pin_functions；角色冲突/供电或输入越限 → hard；
  开漏上拉需证据；封装/修订不匹配不套用；自定义网名不构成证据。
- **R5** 裸/合并焊盘：精确 MPN pad_map；必要焊盘遗漏/错网、合并焊盘分离 → hard；
  中心焊盘不默认 GND；缺封装/映射完整性 → unknown。
- **R6** 电容角色/局部布置：角色必须可追溯；bulk 不套局部阈值；local_decoupling 仅按
  项目显式阈值做 Euclidean 焊盘距离代理；缺几何/来源 → unknown，不证明高频/ESL/EMI。

完整语义见 `contract.md`、`design.md`。

## 3. 实际执行结果（2026-10-28 最终复验，Windows 11，Python 3.13.15）

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests -k electrical_review` | **55 tests OK**（3.579 s，exit 0） |
| `python -m unittest discover -s tests/electrical_review -t tests` | **55 tests OK** |
| `python -m unittest discover -s tests`（全量既有 + 本任务） | **3144 tests OK（skipped=2）**（314.0 s，exit 0） |
| `python benchmarks/electrical-review/run_benchmark.py --runs 3 --out <仓库外临时文件>` | **31/31 pass**，exit 0 |

基准摘要（本次实际运行）：

- `status=pass`，`correctness=31/31`，`failed_cases=[]`；
- `simulated=true`、`real_eda="NOT RUN"`、`eda_calls=0`；
- 场景状态分布：`pass_with_scope` 9、`fail` 11、`review_required` 6、`incomplete` 1、`invalid_input` 4；
- 来源类别：`synthetic_fixture`、`synthetic_fixture_verified_fact`、
  `real_engineering_read_only_replay_derived`、`derived_counterexample_mutation`、
  `synthetic_invalid_input`；
- timing（3 runs）：31 场单场 min 合计 4.862 s，单场 max 193.0 ms；
- 本次复验把基准输出写到仓库外临时文件，**未修改已提交的 `result.json`**，避免 wall-clock
  波动污染冻结结果；worktree 保持 clean。

**Python 3.10 / 3.13 CI：已由 #48、#52 以及本 docs-only PR 的 `validate` 矩阵实际通过**
（`validate (3.10)`、`validate (3.13)` 均 pass），不再是未验证项。

基准覆盖 R1–R6 的正例、反例、unknown，另有 incomplete 与非法输入场景；每个场景冻结
输入 SHA-256、预期 exit/status/summary/规则计数/必需 finding code。timing 只记录本机
CLI 执行成本（约 0.16 s/场景级），**不宣称画板提速**。

测试重点：组件/引脚重排、网名一致重命名、位号改名但 instance_id 不变、mil/mm 与 mV
单位转换、正确飞跨电容短接必失败、重复 ID/位号/脚号、NaN/inf/bool、负耐压、未知单位、
空输入、矛盾网络、旧 PASS 覆盖、封装/修订不匹配。详见 `acceptance.md`。

## 4. 原厂事实与合成/重放分界

已核验原厂事实（来源/版本/页/表/URL/PDF SHA-256 见 `sources.md`）：

1. **四脚按键内部常通组**：ALPSALPINE **SKHHAKA010**（SKHH Top push，4 端子）：
   1–2 常通、3–4 常通，按下接通两组；C&K PTS645 S/T 独立旁证。
2. **电源类芯片裸焊盘**：TI **TPS62130**（VQFN-16 RGT，SLVSAG7F）：EP pin17 必接
   AGND/PGND/地平面并焊接；PG 开漏需上拉；推荐 VIN 3–17 V。
3. **合并焊盘**：AMS1117-3.3 SOT-223：TAB IS OUTPUT（TAB=VOUT），不是 GND。
4. **飞跨电容/特殊引脚**：TI MAX3232（SLLS410O）：C1 飞跨在 C1+(1)/C1−(3)。
5. MCP23017：实际原厂文档为 **DS20001952D**；任务书 DS20001921E 未证实，未硬编码、
   未作为规则依据（记录为更正案例）。

分界：

- 原厂事实：真实，但只适用于精确 MPN/封装/修订/条件；
- 31 个 benchmark 工程：**合成夹具**（`synthetic_fixture`），引用真实 facts；
- `real-mcu-i2c-ams-tab`：由仓库内冻结 `mcu-i2c-s3-2026-10-26` 的 PCB dump/sch
  connectivity **离线派生重放**（`derived`，源 SHA 固定），未重新调用 EDA；
- `real-mcu-i2c-ams-tab-split`：在该重放上的**反例变异**，明确标注，不冒充真实板。

## 5. 本轮发现并修复的问题

- 证据引用悬空（不存在的 evidence/fact_id）原会静默丢证据：新增 `_validate_references`，
  现为 `invalid_input`。独立反例审查在开发中发现 `walk` 把顶层 evidence 定义当 id 的
  blocker；已修复并复验 55 测试 + 31 基准全通过。
- 独立审查 P1：`pins[].pad_nets` 与逻辑引脚网络冲突曾可报 pass → `contract.py`
  现在按真实网络分区校验，冲突为 `invalid_input`；`r5.py` 逐物理焊盘检查 required
  net role / tie-to-pin，并支持 pad 级证据。回归测试见 `test_contract.py` /
  `test_rules.py`（#52）。
- 独立审查 P2：按键两个 used 端子已在同一网络分区（含别名）时曾仍报有效切换 →
  `r3.py` 现在报 hard `switch_externally_bypassed`；含别名回归测试（#52）。
- R3：原厂内部组未覆盖实际使用脚号时曾可能误报硬违反 → 改为 `unknown`
  （脚号映射不一致不能判错）。
- R5：没有地/电源网络分类证据时曾可能把“未分类”误判为错网 → 改为 `unknown`。
- R4：供电越限 finding 的约束显示只给 min → 修正为 min..max；补充封装/修订不匹配但
  有供电声明时的 unknown。
- R2/CLI：非法 JSON 报告现在仍绑定输入 raw sha256；报告原子覆盖旧 PASS。

## 6. 仍未知 / 未完成

- **Python 3.10/3.13 运行时：已由仓库 CI `validate` 矩阵实际通过**（#48、#52、本 docs
  PR 的 `validate (3.10)` / `validate (3.13)` 均 pass）；本机直接运行版本为 3.13.15。
- Omron B3F/B3FS、NKK JB、Würth 434（HTTP 403）、Panasonic 工业站（000）未取得原厂
  PDF；不作为完成依据。ALPS/C&K 使用厂商 PDF 的 LCSC 镜像（文件内保留原厂页脚证据）。
- 器件资料覆盖有限：模块不内置 datasheet 库；新增型号必须提供 device_facts，不能期望
  自动查手册。
- R2 不建模波形/瞬态/负压/开关节点 AC 应力；R6 只测直线距离代理，不证明回流/ESL/EMI；
  不做任意模拟网络求解。
- 未做真实小板/DRC/保存重开/仿真/Gerber/CPL/DFM/热/EMC/安规/固件/制造/上电验收；
  这些属于任务 A 或后续工作。
- 独立反例审查成员在运行中失败/中断，未产出独立报告；`adversarial-review.md` 是
  Lead 自审（文件内明确声明“不冒充独立审查”）。后续仓库 Codex 独立审查又发现 P1/P2，
  已由 #52 修复并补回归测试；这再次说明自审不能替代独立审查。

## 7. 给任务 A 的精确接入说明

1. **不阻塞**：本模块是独立 CLI，任务 A 不必等待；主维护者可先合入本 PR。
2. **字段映射**：`integration-proposal.md` §1 给出 `sch-connectivity`/PCB dump/BOM →
   本模块输入的最小映射与 JSON 例子；真实重放样例：
   `benchmarks/electrical-review/cases/real-mcu-i2c-ams-tab/input.json`。
3. **调用点**：代表模块完成、PCB 同步/apply 前；关键电气变更后；交付前证据补充。
   hard finding 阻断相关电气推进；unknown 要求补证据/人工 disposition，不永久锁死全局。
4. **命令/退出码**：`PYTHONPATH=easycirq/scripts python -m electrical_review review
   INPUT --out REPORT`；按 `contract.md` 的 exit 0/1/2/3/4 映射门禁。不要解析 stdout
   作为唯一证据，使用 `--out` 的原子报告。
5. **不要 cherry-pick 任务 A 未稳定提交**；本 PR 不依赖任务 A 分支。若 observation 字段
   变化，优先在适配层转换，不要把宿主协议复制进本模块。
6. **策略由主维护者最终决定**；本文件只给建议。SKILL.md/references 的补丁以 diff 片段
   放在 `integration-proposal.md` §5–§6，未直接修改真实文件。

## Integration note (2026-10-28, main integrator)

PR #38 could not be merged because the repository CI (`validate` 3.10/3.13, Linux)
failed in `tests/electrical_review/test_benchmark.py`: the frozen `input_sha256`
values in `expected.json` had been generated from a Windows checkout with CRLF line
endings, so on the LF Linux checkout the driver recomputed different digests and
reported 0/31.

Fix in this branch (no product-code change):
* `benchmarks/electrical-review/.gitattributes` pins `text eol=lf` for the frozen
  tree, so Windows and Linux checkouts produce the same bytes;
* the 31 frozen input hashes in `expected.json` were regenerated from the LF bytes
  (the committed input blobs are LF);
* `result.json` was regenerated by the real CLI driver.

Local evidence after the fix: 50 module tests OK, benchmark 31/31 with
`real_eda="NOT RUN"`, `eda_calls=0`. The module remains an independent offline CLI
with no cross-module adapter and no EDA/host/physical verification.

## Acceptance update (2026-10-28, docs-only PR)

- 任务 B 内容已经 #48 合入 main；#38 已 CLOSED（superseded）。
- 独立审查 P1/P2 修复 PR #52 已合入 main（`main` @ `acbcc18`）：
  55 module tests、full suite 3144 tests（skipped=2）、benchmark 31/31、0 EDA。
- 仓库 CI `validate (3.10)` / `validate (3.13)` 在 #48、#52 以及本 docs-only PR 均通过；
  3.10 运行时不再标“未验证”。
- 本次 docs-only 变更只更新验收记录与 3.10 状态，不改产品代码；详细数字见 §3 与
  `acceptance.md`。
