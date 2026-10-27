# 当前交接（Round 12 反馈闭环）

> 写入时间：2026-10-27 13:05 (+08)。本文件只保留当前有效状态；历史细节见
> `docs/round12/report.md`、`docs/round12/acceptance-matrix.md`、
> `docs/round12/evidence/live-vertical/README.md`。

## 1. 目标与任务表

- 目标：把“观察—计划—执行—回读—评价—修复—复验”做成 Skill 的正常工作流程，
  留下可执行工具、数据契约、真实/离线证据与失败恢复证据。
- 任务表：`docs/round12/task-ledger.md`；基线盘点：`docs/round12/baseline-inventory.md`。

## 2. 分支 / HEAD / 未提交

| 项 | 值 |
|---|---|
| 分支 | `feat/feedback-loop-round12`（已推送） |
| HEAD | `96c3ae9`（merge `origin/main` `4fd4007`）；代码/测试/证据提交 `e734e85` |
| 基线 | `origin/main` `4fd4007`（PR #32 compose 工具链已合并）；PR #30 目标分支 `main` |
| PR | #30，state OPEN，目标 `main`；待文档提交推送后确认 CI 并合并 |
| 工作树 | `C:/Users/jlc/work/hds-feedback-r12`（隔离 worktree） |
| 源码版本 | `design-hardware/.version` = `0.9.4`（由 main 带入；本分支反馈改动未额外 bump） |
| 已安装客户端 | 本轮未核对、未安装、未替换、未发 Release |

提交文档前的未提交项只有 `benchmarks/offline-round12/result.json`（合并后重跑
基准仅时间戳变化）和本批文档；提交后工作树应为干净。不要清理其他会话的
`.tmp-*`/`None.tmp`。

## 3. 已完成 / 进行中

已完成：

- 代码收紧（`e734e85`，接续 `427a07c`/`8b7706b`）：
  - `feedback/scope.py`：PCB 写入强制**完整**原始 `before_dump`——铜的
    `lines/vias/pours/poured/regions/fills/arcs`、`copper.availability`、
    `copper.arcsAvailable`、`capturedAt`、`componentsAvailability`、整数
    `routedLines`、顶层 availability 缺一即写前拒绝；真实 dump 无顶层
    `project` 也可，工程身份以 `capture.projectUuid/documentUuid/windowId` 绑定；
    project/document/window 不符、dump 与新鲜观察哈希/内容不符均拒绝；
    normalized observation 重建的 dump 被拒绝。
  - `apply` 写前二次绑定；写入后 dump 必须带 `capture` 与 `semanticSha256`，
    缺哈希 -> `verification_failed/after_hash_missing`，缺 capture 或
    project/document/window 不符 -> `target_mismatch` 且 `write_confirmed=false`。
  - 孔归属（按 primitive id 再按位号/焊盘配对，D1→D2 两边都记录、
    after-only/无身份孔不掩盖范围外变化）、铺铜属性/几何比较
    （priority/pour_name/locked/line_width/geometry_sha256）、raw/normalized
    copper availability 兼容；diff 为 unknown 时 acceptance 计数不当 0。
  - `feedback/observe.py`：规范化 pours 增加上述属性与 `geometry_available/
    geometry_sha256/raw_sha256`；`feedback/evaluate.py` 电容角色三档；
    `feedback/loop.py`/CLI 显式 `simulated`；`verify` 事实来源与 acceptance 收紧。
- 真实宿主独立副本 round 2（**收紧前代码**）：
  - 移动 D4 +1.26 mil：apply verified、writes_sent=1、四执行事实 true；
    范围外 0；原生 DRC 4 条 clearance error -> evaluate fail、verify fail；
  - 恢复 D4：apply verified、四事实 true；PCB/整体哈希回到原始值；
    原生 DRC 0；evaluate `pass_with_warnings` 且
    `drc_zero_but_quality_issues=true`；verify `unknown`（锁定状态 unknown）。
  - 源 `.epro2` SHA256 `3c3d9853...` 未变；原工程、用户 GUI 窗口、
    其他会话工程均未写入。证据：`docs/round12/evidence/live-vertical/`。
- 最终代码只读复核真实证据（不调用 EDA）：`validate_plan` ok、真实 before/after
  dump 完整性通过、after `capture` 绑定一致、差异复现 2 inside / 0 outside /
  12 unknown、pours 规范化字段齐全。
- 最终离线实跑（合并后）：反馈 308 tests OK、全量 1653 tests OK、
  基准 16/16 PASS、`skill_selftest.py` 5 PASS / 0 FAIL / 0 NOT RUN。
- 文档已按最终事实更新：`docs/round12/report.md`、
  `docs/round12/acceptance-matrix.md`、本交接、`design-hardware/CHANGELOG.md`、
  `design-hardware/references/feedback-loop.md`、`docs/round12/offline-vertical-case.md`、
  `docs/round12/evidence/live-vertical/README.md`。

进行中 / 未完成：

- 文档批次提交、推送、CI 确认、PR #30 描述更新与合并。
- 最终代码真机写入未执行（见第 7 节）。

## 4. 最新测试快照（2026-10-27 合并后实跑）

| 项 | 结果 |
|---|---|
| `tests/test_feedback_loop.py` | 53 tests OK |
| `tests/test_feedback_cases.py` | 44 tests OK |
| `tests/test_feedback_evaluate.py` | 65 tests OK |
| `tests/test_feedback_observe.py` | 41 tests OK |
| `tests/test_feedback_scope.py` | 96 tests OK |
| `tests/test_feedback_cli.py` | 9 tests OK（subprocess 调真实 `feedback_loop.py` 入口） |
| 反馈测试合计 | **308 tests OK** |
| `python -m unittest discover -s tests` | **1653 tests OK** |
| `python tools/feedback_benchmark.py` | **16/16 PASS** -> `benchmarks/offline-round12/result.json` |
| `python design-hardware/scripts/skill_selftest.py` | 5 PASS / 0 FAIL / 0 NOT RUN |

- 基准 16 个用例：`observe_contract`、`drc_zero_but_poor`、`cap_roles`、
  `text_move_vertical`、`pcb_local_apply`、`before_dump_gate`、`acceptance`、
  `out_of_scope_refused`、`locked_refused`、`stale_baseline`、
  `partial_recovery`、`wrong_target`、`unknown_drc`、`prettier_but_worse`、
  `case_library`、`loop_budget`。全部 simulated；`real_eda=NOT RUN`。

## 5. 证据路径

- 真实 round 2：`docs/round12/evidence/live-vertical/`
  （`observation-round2-*`、`plan-round2-*`、`preview-round2-*`、
  `apply-round2-*`、`diff-round2-*`、`drc-round2-*`、`evaluate-round2-*`、
  `verify-round2-*`、`journal-round2-*`、`round2-after/04-pcb-dump.json`）
- 真实只读基线：`docs/round12/evidence/live-baseline/`
- 离线基准：`benchmarks/offline-round12/result.json`、`tools/feedback_benchmark.py`
- 冻结夹具：`tests/fixtures/feedback/board-before.json`、
  `schematic-before.json`、`fake_easyeda.py`
- 案例：`design-hardware/cases/feedback-r12/*.json` +
  `design-hardware/cases/index.json`
- 契约说明：`design-hardware/references/feedback-loop.md`
- 报告/矩阵/纵向案例：`docs/round12/report.md`、`acceptance-matrix.md`、
  `offline-vertical-case.md`

## 6. 运行进程 / 会话 / 跨会话协调

- 本会话没有启动或持有 EasyEDA/easyeda daemon/Connector 进程；最终代码只读
  复核在临时 Python 进程中完成，已结束。
- 用户 GUI 窗口 `5175351c-a00b-4788-a922-2f6e0bd80756`：**不要关闭、不要抢占、
  不要在其上写入**。
- round 2 使用的窗口 `c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7` 与独立副本工程
  `f37160f4acb64e13a80f1eb9c0a67fa3`：jlc-b9 已明确释放窗口并声明不再写入；
  round 2 完成后没有继续写入。不要写 jlc-b9 的
  `usb-audio-amplifier-test-01-restored` / `usb-audio-verify-r12`。
- 可能存在用户/其他会话的 easyeda daemon（端口 `60832`）；不是本轮所有，
  不要重启或清理。
- 当前 `easyeda doc ready --json` 返回 `no EasyEDA connector is available`
  （exit 1），Connector 不可用；不要通过开窗/切窗规避。

## 7. 阻塞

1. **最终代码真机写入 BLOCKED**：Connector 不可用，最终代码未在真实宿主重跑
   apply/保存/重开/DRC；round 2 的真机证据来自收紧前代码，不能冒充最终代码通过。
2. **C2 专项未执行**：C2 候选约 103.16mil，未达 ≤100mil；真实 DRC/铜连接未测。
3. **电容容值解析为启发式**：角色三档已分开，但阈值仍需规则/人工复核。
4. **原理图重开未实现**：文本分支 `reopen_confirmed=null`。
5. **案例层级**：最高 `structural`；三例共享源工程，按 3 cases / 1 project /
   3 scenarios 计数。
6. **未安装/未发版**：源码 0.9.4（main 带入），本分支反馈改动未安装到任何客户端、
   未发布 Release。
7. **PR #30 未合并**：等待文档提交/CI 后合并。

## 8. 下一条具体操作

1. 提交本批文档与最终基准产物（只暂存本轮相关文件），push
   `feat/feedback-loop-round12`。
2. 确认 PR #30 的 CI 通过；更新 PR 描述（最终 SHA、308/1653、16/16、
   round 2 真机结果、最终代码只读复核、最终代码真机 BLOCKED）。
3. 无未解决阻断后合并 PR #30（任务书授权）；不发布 Release、不替换其他客户端
   安装版。
4. 若 Connector 恢复且窗口归属确认，再按验收矩阵第 12 行用最终代码重跑
   apply/readback/verify/保存/重开/原生 DRC；未确认归属时不抢窗口。
5. 恢复会话时先读本交接、`docs/round12/task-ledger.md` 与相关规则，再核实
   `git status`/HEAD、测试计数与基准产物，最后执行写入或提交。
