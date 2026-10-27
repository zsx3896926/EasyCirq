# 当前交接（Round 12 反馈闭环）

> 写入时间：2026-10-27 12:24 (+08)。本文件只保留当前有效状态；历史细节见
> `docs/round12/report.md`、`docs/round12/acceptance-matrix.md`、
> `docs/round12/offline-vertical-case.md`。本轮已完成五项源码收紧（PCB 写前
> `before_dump` 门禁、acceptance 契约、电容角色、显式 `simulated`、PCB apply
> 窗口/文档 UUID 路由），代码/测试/基准提交 `8b7706b`；本文件与文档批次随后提交。

## 1. 目标与任务表

- 目标：把“观察—计划—执行—回读—评价—修复—复验”做成 Skill 的正常工作流程，
  留下可执行工具、数据契约、真实/离线证据与失败恢复证据。
- 任务表：`docs/round12/task-ledger.md`；基线盘点：`docs/round12/baseline-inventory.md`。

## 2. 分支 / HEAD / 未提交

| 项 | 值 |
|---|---|
| 分支 | `feat/feedback-loop-round12`（已推送） |
| HEAD（代码/测试/基准） | `8b7706b`（窗口路由 `427a07c`，文档 `0c5eb71`） |
| 基线 | `origin/main` `1954e15`；PR #30 目标分支已改为 `main` |
| PR | #30，state OPEN，mergeable MERGEABLE；CI 于本次推送后确认 |
| 工作树 | `C:/Users/jlc/work/hds-feedback-r12`（隔离 worktree） |
| 已安装客户端 | 仍 0.9.2；源码 0.9.3 未 bump、未安装、未发 Release |

当前文档批次（本文件、`docs/round12/acceptance-matrix.md`、
`docs/round12/report.md`、`docs/round12/offline-vertical-case.md`、
`design-hardware/CHANGELOG.md`）与 `427a07c` 一起构成最终分支；文档提交后工作树
应为干净。不要清理其他会话的 `.tmp-*`/`None.tmp`。

## 3. 已完成 / 进行中

已完成（离线部分，本轮实跑确认）：

- 代码收紧（`427a07c`/`8b7706b`，接续 `e0c8e5a`）：
  - `feedback/scope.py`：PCB 写入强制原始 `before_dump`；缺失/非对象/缺铜或器件
    数据/项目·文档·版本绑定不符/与新鲜观察不一致/过期 → 写前拒绝；`apply` 写前
    二次核对绑定；负例基准 `before_dump_gate` 证明 `writes_sent=0`、runner 0 次。
  - `feedback/scope.py` + `pcb_apply_plan.py`：PCB apply 以 `--window` + 项目 UUID
    + 文档 UUID 路由；`pcb_apply_plan.py` 新增 `--window`，转发给 `easyeda apply`
    并写入 playbook `meta.window`；`before_dump.capture.windowId` 参与写前绑定，
    错窗口/缺窗口均拒绝。
  - `feedback/scope.py` acceptance 契约：缺计数判 unknown，不按 0 通过；
    `count >= 2` 等谓词可求值，未达成不标完成。
  - `feedback/evaluate.py`：电容角色 `bulk`/`local-decoupling`/`unknown`；
    bulk 仅 conditional、不驱动自动移动、不触发 `drc_zero_but_quality_issues`；
    unknown `auto_action_allowed=false`。
  - `observe/evaluate/scope/cli`：机器可读输出显式 `simulated`；`verify` 的
    call/write/save/reopen 只从 `--apply` receipt 读取，`quality_passed` 只从显式
    `--evaluation` 取得；`--after` 仅哈希交叉核对。
  - `feedback/cases.py`：覆盖计数 3 cases / 1 project / 3 scenarios，保留
    `provenance.source_project/source_case`。
- 12 行验收矩阵：`docs/round12/acceptance-matrix.md`（已更新到 16/16）；
- photo-led 冻结夹具的模拟纵向案例：`docs/round12/offline-vertical-case.md`；
- 最终报告：`docs/round12/report.md`（已更新）；
- 离线基准 `tools/feedback_benchmark.py` -> **16/16 PASS**，产物
  `benchmarks/offline-round12/result.json`（simulated host，`real_eda=NOT RUN`）；
- 三个案例 JSON 的证据路径指向现存基准，证据链闭合。

进行中 / 未开始：

- **真实 EDA 纵向验证未开始**：另一个会话 jlc-b9 正在独立副本
  `usb-audio-verify-r12`（P1 `660075c31db6f396`，窗口
  `c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7`）做保存/重开收尾；12:24 我们已回复
  确认接下来 10 分钟不写 EasyEDA、不切换窗口/文档。窗口释放并确认归属前不抢窗口。
- **C2 专项 apply 未单独执行**：photo-led C2 分支停在 preview；C2 候选约
  103.16mil，未达到 ≤100mil。
- 文档批次提交后工作树应为干净（见第 2 节）。

## 4. 最新测试快照（2026-10-27 12:00 左右实测）

| 项 | 结果 |
|---|---|
| `tests/test_feedback_loop.py` | 53 tests OK |
| `tests/test_feedback_cases.py` | 44 tests OK |
| `tests/test_feedback_evaluate.py` | 65 tests OK |
| `tests/test_feedback_observe.py` | 41 tests OK |
| `tests/test_feedback_scope.py` | 71 tests OK |
| `tests/test_feedback_cli.py` | 9 tests OK（subprocess 调真实 `feedback_loop.py` 入口） |
| 反馈测试合计 | **283 tests OK** |
| `python -m unittest discover -s tests` | **1593 tests OK** |
| `python tools/feedback_benchmark.py` | **16/16 PASS** -> `benchmarks/offline-round12/result.json` |
| `python design-hardware/scripts/skill_selftest.py` | 5 PASS / 0 FAIL / 0 NOT RUN |

- 基准 16 个用例：`observe_contract`、`drc_zero_but_poor`、`cap_roles`、
  `text_move_vertical`、`pcb_local_apply`、`before_dump_gate`、`acceptance`、
  `out_of_scope_refused`、`locked_refused`、`stale_baseline`、
  `partial_recovery`、`wrong_target`、`unknown_drc`、`prettier_but_worse`、
  `case_library`、`loop_budget`。全部 simulated；`real_eda=NOT RUN`。

## 5. 证据路径

- 真实只读基线：`docs/round12/evidence/live-baseline/`
  - `copy-pcb-check-before.json`（C2 150mil / C1 890mil decap-too-far）
  - `copy-sch-score.json`（text overlap 55.01×12.00 估算）
  - `copy-drc-before.json`（PCB DRC 0）、`copy-sch-drc.json`（1 warn）
  - `pcb-save-original.json`、`sch-save-original-2.json`（原工程只读保存回执）
- 离线基准：`benchmarks/offline-round12/result.json`、`tools/feedback_benchmark.py`
- 冻结夹具：`tests/fixtures/feedback/board-before.json`、
  `schematic-before.json`、`fake_easyeda.py`
- 案例：`design-hardware/cases/feedback-r12/*.json` +
  `design-hardware/cases/index.json`
- 契约说明：`design-hardware/references/feedback-loop.md`
- 报告/矩阵/纵向案例：`docs/round12/report.md`、`acceptance-matrix.md`、
  `offline-vertical-case.md`

## 6. 运行进程 / 会话 / 跨会话协调

- 本会话没有启动或持有 EasyEDA/easyeda daemon/Connector 进程；所有模拟均在
  in-process fake host 或临时 Python 进程中完成，已结束。
- 用户 GUI 窗口 `5175351c-a00b-4788-a922-2f6e0bd80756`：**不要关闭、不要抢占、
  不要在其上写入**。
- 跨会话同伴 jlc-b9 的窗口 `c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7` 与工程
  `usb-audio-amplifier-test-01-restored` / `usb-audio-verify-r12`：同样不要写、
  不要切文档。12:24 其请求 10 分钟内保持不写，我们已回复确认；收到其窗口释放
  消息并重新确认归属后才考虑真机操作。
- 可能存在用户/其他会话的 easyeda daemon（基线探测时端口 `60832`）；不是本轮所有，
  不要重启或清理。
- **工作区副作用**：早前真机探测在用户团队工作区导入过一个测试副本
  `r12-feedback-photo-20261027`（UUID `0433fb04...`），只做过只读/保存回执探测，
  没有写入任何设计变更；后续会话不要把它当客户工程。

## 7. 阻塞

1. **真机纵向验证暂不可执行**：EasyEDA 窗口被另一会话占用（见第 6 节），我们已
   承诺窗口释放前不写。真实写、保存、重开、DRC 复验全部 `BLOCKED`/`NOT RUN`；
   不要声称“已真机通过”。
2. **PCB apply 适配器边界**：写入现在强制原始 `before_dump`，只给规范化
   observation 会在写前被拒绝（`before_dump_gate` 负例）；路由已固定为
   `--window` + 项目/文档 UUID。C2 专项 apply 仍未单独执行，候选约 103.16mil，
   未达到 ≤100mil，真实 DRC/铜连接未测。
3. **电容角色**：已分三档并禁止 unknown 驱动自动移动；容值解析仍是启发式，
   工程质量阈值仍需规则/人工复核。
4. **原理图重开未实现**：适配器未实现 schematic reload，文本分支
   `reopen_confirmed=null`，真实 `text.move`/保存/重开未验证。
5. **案例证据层级**：最高只有 `structural`；`host_readback/erc_drc/simulation/
   manufacturing/physical` 全部 `not_run`；三个案例共享源工程
   `photo-led-pcb-20261026`，按“一个项目三个场景”计数。
6. **未安装**：客户端仍 0.9.2；源码 0.9.3 未安装、未发 Release。
7. **PR 未合并**：PR #30（base `main`）待本次推送后的 CI 确认；待真机纵向验证
   完成或明确记录其未执行后，再决定合并。

## 8. 下一条具体操作

1. **提交文档批次并推送**：`git add` 五份文档（本文件、验收矩阵、报告、纵向案例、
   CHANGELOG），提交并推送 `feat/feedback-loop-round12`，确认 CI；用
   `gh pr edit 30` 更新 PR 描述（16/16、283/1593、`8b7706b`、窗口/文档 UUID
   路由、verify 事实来源、真机 NOT RUN）。
2. **等 jlc-b9 释放窗口**并收到其消息后，重新确认窗口归属与无其他写入者，再新建
   独立工程副本做真机纵向验证：`probe` → `observe`（`--window` + 明确 sch/pcb
   文档 UUID）→ `preview`（`writes_sent=0`）→ dry-run `apply` → `apply --apply`
   （plan 必须携带原始 `before_dump`，路由带 `--window` + 项目/文档 UUID）→
   `readback` → `verify` → 保存/重开/原生 DRC；验证身份、范围外零变化、连接、
   保存重开；恢复测试修改后再复验；原工程不动。未确认归属时不抢窗口，继续
   离线/文档工作。
3. 真机结果写入 `docs/round12/report.md` 与验收矩阵，区分模拟/真实；未执行项保持
   `NOT RUN`。满足评审条件且无未解决阻断后合并 PR #30；不发布 Release、不替换
   其他客户端安装版。
4. 恢复会话时先读本交接、`docs/round12/task-ledger.md` 与相关规则，再核实
   `git status`/HEAD、测试计数与基准产物，最后执行写入或提交。
