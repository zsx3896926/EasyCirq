# Current handoff — 2026-10-27 — round11 离线能力强化

## 1. 目标与任务表

- 目标：修复 PCB 证据工具链的数据正确性，增强离线布局/图面分析，建立无 EDA 的可重复验收，反哺 Skill。
- 任务表/评审：`docs/round11/task-ledger.md`、`docs/round11/review-report.md`
- 基准：`benchmarks/offline-round11/`（`expected.json`、`result.json`、README）

## 2. 仓库/分支/版本

- worktree：`C:/Users/jlc/work/hds-offline-r11`
- 基线：`origin/main` = `066a74b`（PR #22 后）
- 分支：`feat/offline-toolchain-round11`；HEAD `6bbc761`
- PR：#24 https://github.com/zsx3896926/hardware-design-skill/pull/24（未合并）
- Skill 版本：`0.9.3`（`design-hardware/.version`）
- 本轮未安装到客户端、未合并、未发 Release

## 3. 已完成

### 3.1 离线入口与安全缝

- `design-hardware/scripts/offline_guard.py`：`HDS_OFFLINE=1` 拦截真实 `easyeda` 与进程内网络；假 CLI 需路径含 `fake` 或文件带 `HDS_FAKE_CLI`/`FAKE_EASYEDA` 标记；JSONL audit `simulated:true`。
- `tools/offline_suite.py`：任意 cwd 运行，设置全新 TMP/TEMP，导入所有脚本并跑 `tests/`；输出测试计数/拦截事件/静态清单。
- `pcb_cli.write_json` 改为原子替换；`pcb_cli.run` 增加 offline 前置拒绝。

### 3.2 证据/门禁

- `pcb_evidence.py` 重写解析层：空侧 `not_comparable`、absent/empty/invalid/measured 分离、summary/findings/DRC 计数一致性、外层 `ok=false`、bool/字符串/负数/NaN、重复位号/脚号/焊盘、alias 缺目标/None 网络、网络分区与重命名分离、identity 字段、全排除、net-path 空要求、INFO disposition。
- `pcb_gate.py`：`*-final*` 优先；manifest 绑定（sha256/source_dump/produced_at）；身份冲突/候选分歧/缺件不回退；`EVIDENCE_BINDING`；`freshness_basis`；`semantic_sha256`；`match_with_renames`；`--pin-aliases`/`--ignore-designators`。
- 新增测试：`tests/test_pcb_evidence_contract.py`（35）、`tests/test_pcb_gate_provenance.py`（7）、`tests/test_offline_guard.py`（7）。

### 3.3 执行计划/几何/布局

- `pcb_apply_plan.py`：实测 pose 缺字段拒绝；0/360 等价；no-op 识别与跳过；journal `confirmed/failed/unknown/not_sent`；`recovery.safe_to_retry=false`；track 线宽/via 直径/pour 边/keepout 边界；原子报告；`transaction.atomic_rollback=false`。
- `geometry.py`：角度归一、凹多边形、矩形/圆/带宽度折线包含、线段相交；`pcb_workflow.validate_placement` 与 `placement._hard_ok` 使用 polygon；新增 `locked`/`spacing` 约束；`diff_boards` 角度归一。
- `placement.py`：硬过滤 + `score_components` + `feasibility=not_found_within_budget` + `routing_verified=false`。
- `reuse.py`：footprint 缺失/尺寸/rotation/网络分区检查，操作带旋转/层。

### 3.4 原理图与基准

- `sch_visual_audit.py`：复用 `sch_layout_check`，输出对象/位置/原因/未执行建议、字体不确定性、netflag policy 状态、结点证据分组；分析叠加 SVG（水印 + `official_export:false`）。
- `tools/offline_benchmark.py` + `benchmarks/offline-round11/`：9 个用例全 pass；photo 真实残差保留 3 blocking/5 info；三结构候选；no-op；keepout 硬约束增益；holdout 凹板；变形测试。
- 新增测试：`tests/test_geometry_primitives.py`（14）、`tests/test_sch_visual_audit.py`（8）。

## 4. 验证结果（本轮实际运行）

- 全量 unittest：**1236 tests OK**（2026-10-27，离线）。
- `python tools/offline_suite.py`：**1236 tests OK**；导入扫描 72 modules，0 blocked/0 error/0 system_exit；模拟拦截事件 0（正常测试未触发真实路径）。
- `python tools/offline_benchmark.py --runs 3`：**9/9 pass**；`benchmarks/offline-round11/result.json` 记录 per-case min/median 耗时。
- 真实 controlledB manifest 离线复核：`pcb_gate --case docs/round10/controlledB --profile regression` → `pass_with_gaps`（PG1/PG2/PG3/PG6/PG7/PG8 pass）；full 仅缺 `--key-nets` 导致 PG5 blocked。
- `python design-hardware/scripts/skill_selftest.py`：**5 PASS / 0 FAIL / 0 NOT RUN**。
- 真实 EDA 调用：**0**。未启动/连接 EasyEDA，未调用 easyeda CLI（health/help/read/export 均未调用），未改工程或已安装执行器。

## 5. 未完成 / BLOCKED

- 真实 EDA 读写、保存重开、原生 DRC/check/lint：本轮按任务边界 **NOT RUN**。
- 布线完成、铺铜连通、Gerber/钻孔/CPL、板厂 DFM、热/EMC/安规、固件/实物：**NOT RUN / BLOCKED**。
- 图片字节级回归、官方导图人工视觉签核：**NOT RUN**；`sch_visual_audit` 只输出离线叠加图。
- 跨客户端安装/缓存/兼容性演练（K）与批量输入安全（L）：本轮未实施，保留为扩展。
- 整数安装/Release：未安装 0.9.3、未发 Release、未合并 PR。

## 6. 下一条具体动作

1. 评审 PR（见 `docs/round11/review-report.md` 的链接/分支）。
2. 真实 EDA 验证清单（下一轮、需显式授权）：
   - 在隔离副本上 `easyeda pcb dump`/`sch read` 采集真实证据，跑 `pcb_gate --profile regression` 与 `--profile full`；
   - 用 `pcb_apply_plan` 的一个真实 move+no-op 混合计划做 dry-run → apply → save/reload → diff；
   - 对 photo-led v14 重新导出 SVG，重跑 `sch_visual_audit` 并与本轮离线残差对照；
   - 采集 case manifest 后验证 `EVIDENCE_BINDING` 与 `produced_at`；
   - 记录真实 CLI/daemon/Connector 版本、工程 UUID、原始终端日志。
3. 如需发布，先由维护者决定版本/Release；本机客户端仍为 0.9.2。

## 7. 关键证据路径

- 全量测试输出：本地 `.tfull1.txt`（工作树临时文件，不提交）
- 离线套件：`docs/round11/offline-suite-baseline.json`（基线段，若保留）、`docs/round11/offline-inventory.json`
- 基准：`benchmarks/offline-round11/expected.json`、`result.json`、`README.md`
- 图面叠加：`docs/round11/photo-led-v14-overlay.svg`、`photo-led-v14-visual.json`
- 报告：`docs/round11/review-report.md`
- 契约：`design-hardware/references/offline-regression.md`
- 本轮未调用 EDA，无新真机日志。
