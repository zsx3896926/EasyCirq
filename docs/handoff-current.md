# Current handoff — 2026-10-27 — round12 排版工具链 + 真机验收

- 目标：round12 排版工具链（PR #32）基于最新 main 集成、复核、测试；随后只在恢复工程的独立副本中做真机 compose/apply 验收。原工程 P2 保持不动。
- worktree：`C:/Users/jlc/work/hds-compose-r12`；分支 `feat/compose-tooling-r12`；已并入 `origin/main`（含 PR #31 power preflight）。
- HEAD：最后代码提交 `e467c53`；其后仅为 handoff 文档提交（以 `origin/feat/compose-tooling-r12` tip 为准）。
- 本轮文件：`sch_compose_input.py`、`sch_sheet_fit.py`、`sch_bind_component_ids.py`；对应测试；`references/schematic-layout-engine.md`、`CHANGELOG.md`（0.9.4）、`.version`；`docs/round12-real-machine.md`。
- 离线验证：`python -m unittest discover -s tests` → **1344 tests OK**（日志 `%TEMP%\r12-unittest.log`）；`skill_selftest` → **5 PASS / 0 FAIL / 0 NOT RUN**（`%TEMP%\r12-selftest-2.log`）。
- 真机对象：独立副本 `usb-audio-verify-r12`，UUID `66ad17591d5b4f6ebbcb42295f76b2b1`，P1 `660075c31db6f396`；窗口 `c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7`。原工程 P2 未触碰。
- 真机结果（详见 `docs/round12-real-machine.md`）：
  - compose-input `ready`（8 区/24 件/93 线/33 标记）；sheet-fit `fits`；59 行 connectivity edits。
  - `sch apply` 173 步：170 OK；第 171 步 strict gate FAIL；172/173 未执行。未 `--resume/--from/--to`、未整批盲重放。
  - 失败后回读：C5 位号先移到 `(690,612)` 仍压本体；再回读重算移到 `(712,612)`；`sch save` seq 2453，`doc reload`，回读通过。
  - 最终 check：8 findings = 5 info wire-crossing + 3 基线 out-of-sheet；无 designator-overlap/floating/geom/dangling/marker/partition。
  - 身份与逐脚：`work/identity-compare.json` `identical`；24/24 器件身份、59/59 引脚 net/NC/pin id、13 网/59 连接一致；仅副本 project UUID 不同（预期）。
  - gate：非 strict PASS；strict FAIL 仅基线（3 条 sheet out-of-sheet + 4 条 DRC warn：P3 2×ONENETNAME、P2 1×ONENETNAME、P1 F1 1×ATTRMATCHCODE），与原工程 `P1-gate3.txt` 一致；未改标题栏/属性。
  - 官方 SVG/PNG 已导出并目视审查；C5 区域干净，8 区框不重叠不越界。证据：`C:/Users/jlc/work/usb-audio-verify-r12/pages/after2/`、`work/evidence-index.json`；基线 `C:/Users/jlc/work/usb-audio-reflow-20261027/out/`。
- 未执行：P2/P3 重排、原工程 P2 修复（保持原样）、PCB、制造导出、strict gate 通过。离线 `ready/fits/verified` 不代表真机通过；apply playbook 本身未完成。
- 写入权：jlc-6f/jlc-7f 已确认本轮不写；P1 已完成保存/重开/回读，EDA 窗口可在本 handoff 后移交 jlc-6f（其 PCB 验证在独立导入副本，不碰原工程/P2）。
- 下一动作：PR #32 body 与 comment 已更新（2026-10-27 12:35 本地），等待评审/合并；窗口已释放给 jlc-6f。若继续真机，仅在新范围（P2/P3、PCB、制造导出）另开任务并重新确认写权；strict gate 通过仍受基线警告阻塞。
