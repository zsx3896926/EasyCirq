# Current handoff — 2026-10-27 — round12 排版工具链 + 真机集成

- 目标：round12 排版工具链（PR #32）基于最新 main 集成、复核、测试；随后只在恢复工程的独立副本中做真机 compose/apply 验收。原工程 P2 保持不动。
- worktree：`C:/Users/jlc/work/hds-compose-r12`；分支 `feat/compose-tooling-r12`；已并入 `origin/main`（含 PR #31 power preflight）。
- 本轮文件：
  - 新增 `design-hardware/scripts/sch_compose_input.py`、`sch_sheet_fit.py`、`sch_bind_component_ids.py`
  - 新增 `tests/test_sch_compose_input.py`、`test_sch_sheet_fit.py`、`test_sch_bind_component_ids.py`
  - 修改 `design-hardware/references/schematic-layout-engine.md`、`CHANGELOG.md`、`.version`（0.9.4）、`scripts/skill_selftest.py`
- 离线验证：全量测试与 `skill_selftest` 以合并后实际运行结果为准（见 PR #32 评论/检查）。
- 真实只读证据：P1 compose-input `ready`（8 区/24 件/93 线/33 标记）；P1 sheet-fit `fits`；P2 sheet-fit `no-fit` 并定位剩余空间不足；P1 绑定 `verified 24/24`。数据在 `C:/Users/jlc/work/usb-audio-reflow-20261027/`。
- 真机计划：唯一写入窗口确认 → 恢复工程独立副本 → 新鲜测量 → 绑定/预检/compose → dry-run → apply → save/reopen → 身份与逐脚网络 diff → 官方导图审查。失败先回读再重算，禁止整批盲重放。
- 真机状态：以本轮实际执行与 PR #32 更新为准；未执行项标 `NOT RUN`/`BLOCKED`，不用离线 ready/fits/verified 代替。
- origin/main 同时合入 PR #31（power preflight）；其验证与未执行项见 `docs/power-preflight/review-report.md`，本任务未改变其结论。
- 下一动作：合并 main 后跑全量测试并推送；确认 EDA 窗口归属与唯一写权后开始真机步骤。
