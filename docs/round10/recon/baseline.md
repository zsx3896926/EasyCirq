# baseline

## summary

T-0 基线已用原始审计 JSONL 逐条复核；两个给定 audit JSON 的 totals 均可完全复现（13:10-13:52: 2775 calls/9 fail；13:40:06-13:48:56: 439 calls/2 fail）。关键结论：`_audit-edit-only.json` 的 8.8368 min 窗口不是纯 C99 改板，可精确拆为 127 calls/1.7805 min 板 B 收尾（13:40:06-13:41:52Z）+ 2.9726 min 空闲（13:41:53-13:44:51Z）+ 260 calls/3.6780 min 严格验收完成的 C99 任务（13:44:51.304-13:48:31.984Z，到最终 .epro2 导出）+ 52 calls/0.4057 min 的 sch connectivity 与最终 `pcb check` 尾巴。因此：若按任务定义从 project.import 到 DRC 0/scoped diff/save-reload 全部满足，T-0 为 260 calls、30 mutations、160 probes、3.6780 min、2 failures（均为 2 ms document.current 探测，写入失败 0），另有 10 个 pcb.save action（5 显式 + 5 reload 前保存）、3 次原生 DRC（前两次失败：3 条和 1 条 clearance，第三次 0）、2 次 autoroute（只布 +3V3/GND，共 42.196 s）、1 次 project.import、1 次 pcb.import_changes、1 次 schematic.component.place、2 次 pcb.component.modify（C99 初次落位 + 避让移动）。若把最终 check 也算入，则 312 calls/177 probes/4.0837 min。质量验收：DRC passed=true total=0；scoped diff identity=1(C99)/geometry=0/copper=135/unrelated=0，135 条铜变化独立映射为 +3V3 59 / GND 76 / 其他 0；save/reload diff match；pcb check 0 ERROR/15 WARN/1 INFO（C99 去耦 272 mil 新增 WARN）。tokens=0 仅表示未记录，不是零消耗。若直接用给定 439 calls/8.8368 min 当 T-0，会把成本相对严格任务口径高估约 2.40 倍（8.8368/3.6780）。

## gaps

- 窗口口径：`_audit-edit-only.json` 的 13:40:06-13:48:56Z 不是纯 C99 改板。精确分解：439 calls = 127（板 B 收尾，13:40:06.118-13:41:52.951Z）+ 260（C99 严格验收完成，13:44:51.304-13:48:31.984Z）+ 52（最终 sch connectivity + pcb check，13:48:32-13:48:56Z）；wall 8.8368 min = 1.7805 + 2.9726（空闲）+ 3.6780 + 0.4057。引用 439/8.8368 时必须标注它不是纯改板成本。
- 严格验收完成点：scoped diff 13:48:05.988Z、save/reload match 13:48:31.926Z、最终 .epro2 导出 13:48:31.984Z；之后 52 calls/24.34 s 是三页 sch connectivity 与最终 `pcb check`，不在任务定义的 DRC 0 + scoped diff + save/reload 三项验收内。若把最终 check 计入，C99 窗口为 312 calls/177 probes/4.0837 min。
- tokens：两个 audit JSON 的 `tokens:0` 表示未记录，不是 0 消耗；LLM/context 成本 NOT RECORDED。`thinkMinutes` 同样是 wall − Σduration，无法拆分 agent 推理、人工 EDA GUI 操作和空闲，且不处理并发。
- 失败性质：2 次 audit failures 都是 2 ms 的 `document.current`（`easyeda doc ls`、`easyeda doc open`），不是写入失败；project.import、pcb.import_changes、pcb.component.modify、pcb.route.auto、pcb.pour.rebuild、pcb.save、pcb.drc.check 均为 0 failure。
- 质量失败与返工：DRC 第 1 次 3 条 clearance（2 条 +3V3/GND track-track + 1 条 C99 pad–U2 pad），第 2 次 1 条 C99 pad–U2 pad，第 3 次 0；期间 C99 从 (1320,560) 移到 (1380,600)，执行 2 轮 rip-up+autoroute+pour。首轮 track-track clearance 的根因未记录（只有 object ID +3V3 e382/e383 与 GND e401）。
- saves 口径：10 个 `pcb.save` action = 5 个显式 `easyeda pcb save` + 5 个 `easyeda doc reload` 前保存；另有 1 个 `schematic.save`。不要把 10 当作 10 次独立人工保存。
- calls 口径：audit 的 `calls` 是 action record，不是 CLI 进程数；严格窗口 260 records 来自 39 个 clientId（CLI 进程），每条命令固定发 2-4 个 probe/action。mutations 取自 `_actions-catalog.json` 的 `mutates` 标志，包含 pcb.save、project.import、project.open 等，30 是 action 计数，不是 30 个不同设计变更。
- board A 成本：两个给定窗口都从 13:10Z 开始，而板 A 证据文件时间为 12:17-12:52Z；板 A 的 calls/mutations/wall 在这两个 JSON 中 NOT RECORDED。board A/B 的最终 DRC/check/BOM/图片是冻结证据文件，本轮未重跑 EDA；图像只核对哈希/字节，未重新做视觉检查。
- board A DRC-0 checkpoint：design-state 引用 `photo-led-pcb-drc0.epro2`（224,778 B，SHA-256 6542f416c08ed4c88982ce1ac9d6d05fa3a3f52f0fe924ac939731c26a420400），但文件不在 evidence/ 也不在 git 历史；审计 `project.export` 12:46:53.294Z 的 payload 哈希匹配，可从审计日志恢复，但当前不是冻结文件。
- design-state 元数据：A/B 的最终 `.epro2` 只在 `recovery.sha256`/`checkpoint_epro2`，不在 `evidence` 数组；两个 `design-state.json` 的 `updated` 均为 null。A/B 的 final .epro2、dump、DRC、check、BOM、PNG/SVG 哈希均已逐一重算并与 design-state/文件一致。
- `project.import` 结果 `contentVerified:false` 而 `verified:true`；提供的文件没有定义 contentVerified 语义。审计 payload base64 解码后 132,270 B、SHA-256 与冻结 boardB-final.epro2 完全一致，输入身份可证。最终 edit .epro2 的 project.export payload 也精确匹配冻结文件。
- scoped diff 的 `copper_changes` 只有 `primitive_id`/`kind`，没有 net 字段；本报告的 +3V3 59/GND 76/其他 0 是从 before/after dump 的 primitiveId→net 独立映射得到，135/135 全部匹配，0 unmatched。`unrelated_changes` 原文件为空数组。
- 审计原始 JSONL 是活文件：分析期间 22:27（14:27:50Z）出现另一会话的 `pcb.save` 失败记录；不影响 13:10-13:52 窗口，但 raw log 本身不是冻结输入。两个 `_audit-*.json` 快照文件未被修改（SHA 已列在 frozen_artifacts）。
- 用户/agent turn 数、人工 GUI 时间、首轮 DRC 根因、`contentVerified:false` 语义均 NOT RECORDED；这些不能从 action-record 审计日志恢复。

## recommendations


## facts


## metrics

- supplied_window.span_utc = 13:40:06-13:48:56 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.wall_minutes = 8.836774416666668 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.daemon_minutes = 1.6821833333333334 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.think_minutes = 7.154591083333334 | source: audit-direct (CLI-derived wall-daemon): _audit-edit-only.json | measured: True
- supplied_window.calls = 439 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.mutations = 39 | source: audit-direct: _audit-edit-only.json; reproduced from raw JSONL with _actions-catalog.json mutates flags | measured: True
- supplied_window.probes = 241 | source: audit-direct: _audit-edit-only.json (document.current + schematic.pages.list + pcb.documents.list) | measured: True
- supplied_window.probe_seconds = 4.175 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.probe_share = 0.5489749430523918 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.failures = 2 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.fail_rate = 0.004555808656036446 | source: audit-direct: _audit-edit-only.json | measured: True
- supplied_window.pcb_save_calls = 15 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.schematic_save_calls = 1 | source: derived: raw JSONL 13:40:06-13:48:56Z | measured: True
- supplied_window.pcb_drc_check_calls = 5 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.pcb_route_auto_calls = 2 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.project_import_calls = 1 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.pcb_import_changes_calls = 1 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.schematic_component_place_calls = 1 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.schematic_power_connect_pin_calls = 2 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.pcb_pour_rebuild_calls = 3 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.document_open_calls = 15 | source: audit-direct: _audit-edit-only.json topActions; exact in raw JSONL | measured: True
- supplied_window.tokens = NOT RECORDED (0 in JSON means unrecorded, not zero consumption) | source: audit CLI help: tokens are caller-reported and never inferred | measured: False
- boardB_tail.span_utc = 13:40:06.1188784-13:41:52.9508038 | source: derived: raw JSONL filtered by projectName=mcu-i2c-s3-20261026 | measured: True
- boardB_tail.calls = 127 | source: derived: raw JSONL project split | measured: True
- boardB_tail.wall_minutes = 1.7805320833333333 | source: derived: raw JSONL first/last ts | measured: True
- boardB_tail.mutations = 9 | source: derived: raw JSONL + catalog mutates flags | measured: True
- boardB_tail.probes = 64 | source: derived: raw JSONL | measured: True
- boardB_tail.failures = 0 | source: derived: raw JSONL | measured: True
- boardB_tail.pcb_save_calls = 5 | source: derived: raw JSONL | measured: True
- boardB_tail.pcb_drc_check_calls = 2 | source: derived: raw JSONL | measured: True
- boardB_to_c99_idle_gap_minutes = 2.97256645 | source: derived: 13:41:52.9508038 -> 13:44:51.3047907Z | measured: True
- c99_acceptance.span_utc = 13:44:51.3047907-13:48:31.9844613 | source: derived: raw JSONL, project mcu-i2c-s3-edit-20261026 + 2 unattributed document.current probes | measured: True
- c99_acceptance.calls = 260 | source: derived: raw JSONL 13:44:51-13:48:32Z | measured: True
- c99_acceptance.mutations = 30 | source: derived: raw JSONL + _actions-catalog.json mutates flags | measured: True
- c99_acceptance.probes = 160 | source: derived: raw JSONL (document.current+schematic.pages.list+pcb.documents.list) | measured: True
- c99_acceptance.probe_seconds = 3.139 | source: derived: raw JSONL | measured: True
- c99_acceptance.probe_share = 0.6153846153846154 | source: derived: 160/260 | measured: True
- c99_acceptance.wall_minutes = 3.6779945166666668 | source: derived: raw JSONL first/last ts through final .epro2 export | measured: True
- c99_acceptance.daemon_minutes = 1.2736666666666667 | source: derived: raw JSONL durationMs sum 76420 | measured: True
- c99_acceptance.think_minutes = 2.40432785 | source: derived: wall - daemon; includes agent reasoning, manual GUI and idle (not separable) | measured: True
- c99_acceptance.failures = 2 | source: derived: raw JSONL; both 2 ms document.current probes (easyeda doc ls, easyeda doc open) | measured: True
- c99_acceptance.write_failures = 0 | source: derived: raw JSONL; no failed import/modify/autoroute/pour/save/DRC action | measured: True
- c99_acceptance.fail_rate = 0.007692307692307693 | source: derived: 2/260 | measured: True
- c99_acceptance.pcb_save_calls = 10 | source: derived: raw JSONL | measured: True
- c99_acceptance.schematic_save_calls = 1 | source: derived: raw JSONL (after C99 placement/autoconnect) | measured: True
- c99_acceptance.explicit_pcb_save_commands = 5 | source: derived: raw JSONL command=easyeda pcb save | measured: True
- c99_acceptance.reload_save_actions = 5 | source: derived: raw JSONL command=easyeda doc reload | measured: True
- c99_acceptance.pcb_drc_check_calls = 3 | source: derived: raw JSONL | measured: True
- c99_acceptance.drc_failed_runs = 2 | source: derived: raw JSONL results (3 then 1 clearance violations; third passed) | measured: True
- c99_acceptance.pcb_route_auto_calls = 2 | source: derived: raw JSONL | measured: True
- c99_acceptance.autoroute_seconds = 42.196 | source: derived: raw JSONL (21458+20738 ms) | measured: True
- c99_acceptance.project_import_calls = 1 | source: derived: raw JSONL | measured: True
- c99_acceptance.pcb_import_changes_calls = 1 | source: derived: raw JSONL | measured: True
- c99_acceptance.schematic_component_place_calls = 1 | source: derived: raw JSONL (C99) | measured: True
- c99_acceptance.pcb_component_modify_calls = 2 | source: derived: raw JSONL (initial PCB placement 1320,560; fix move 1380,600) | measured: True
- c99_acceptance.pcb_pour_rebuild_calls = 3 | source: derived: raw JSONL | measured: True
- c99_acceptance.pcb_route_rip_up_calls = 4 | source: derived: raw JSONL (2 x +3V3, 2 x GND) | measured: True
- c99_acceptance.document_open_calls = 7 | source: derived: raw JSONL | measured: True
- c99_acceptance.distinct_cli_processes = 39 | source: derived: distinct clientId in raw JSONL | measured: True
- c99_through_final_check.calls = 312 | source: derived: raw JSONL 13:44:51-13:48:57Z | measured: True
- c99_through_final_check.wall_minutes = 4.083675883333333 | source: derived: raw JSONL first/last ts | measured: True
- c99_through_final_check.probes = 177 | source: derived: raw JSONL | measured: True
- c99_through_final_check.daemon_minutes = 1.4865833333333334 | source: derived: raw JSONL durationMs sum 89195 | measured: True
- c99_through_final_check.mutations = 30 | source: derived: raw JSONL + catalog mutates flags | measured: True
- final_check_tail.calls = 52 | source: derived: raw JSONL 13:48:32-13:48:57Z | measured: True
- final_check_tail.wall_seconds = 24.340882 | source: derived: final archive export -> last pcb check action | measured: True
- full_window.span_utc = 13:10:00-13:52:32 | source: audit-direct: _audit-edit-window.json | measured: True
- full_window.calls = 2775 | source: audit-direct: _audit-edit-window.json | measured: True
- full_window.mutations = 263 | source: audit-direct: _audit-edit-window.json; reproduced from raw JSONL | measured: True
- full_window.probes = 1453 | source: audit-direct: _audit-edit-window.json | measured: True
- full_window.wall_minutes = 42.535373928333335 | source: audit-direct: _audit-edit-window.json | measured: True
- full_window.daemon_minutes = 12.832600000000001 | source: audit-direct: _audit-edit-window.json | measured: True
- full_window.think_minutes = 29.702773928333336 | source: audit-direct (CLI-derived wall-daemon): _audit-edit-window.json | measured: True
- full_window.failures = 9 | source: audit-direct: _audit-edit-window.json | measured: True
- full_window.pcb_save_calls = 69 | source: audit-direct: _audit-edit-window.json topActions; exact in raw JSONL | measured: True
- full_window.schematic_save_calls = 14 | source: derived: raw JSONL | measured: True
- full_window.pcb_drc_check_calls = 15 | source: audit-direct: _audit-edit-window.json topActions; exact in raw JSONL | measured: True
- full_window.pcb_route_auto_calls = 6 | source: audit-direct: _audit-edit-window.json topActions; exact in raw JSONL | measured: True
- full_window.project_import_calls = 1 | source: derived: raw JSONL | measured: True
- full_window.pcb_import_changes_calls = 2 | source: derived: raw JSONL | measured: True
- full_window.schematic_component_place_calls = 1 | source: derived: raw JSONL | measured: True
- quality.drc_run1 = passed=false; 3 clearance violations (2 track-track +3V3 vs GND, 1 C99 pad vs U2 pad) | source: derived: raw JSONL pcb.drc.check 13:46:07.755Z | measured: True
- quality.drc_run2 = passed=false; 1 clearance violation (C99 pad vs U2 pad) | source: derived: raw JSONL pcb.drc.check 13:47:02.165Z | measured: True
- quality.drc_run3 = passed=true; 0 violations | source: derived: raw JSONL pcb.drc.check 13:47:51.998Z | measured: True
- quality.rework_rounds = 2 rip-up+autoroute+pour cycles; C99 moved once (1320,560 -> 1380,600) | source: derived: raw JSONL 13:46:32-33 and 13:47:23 | measured: True
- quality.c99_scoped_diff = identity=1 (C99 added), geometry=0, copper=135, unrelated=0 | source: evidence: edit-add-decap-scoped-diff.json | measured: True
- quality.c99_copper_net_split = +3V3=59, GND=76, other=0, unmatched=0 | source: derived: edit-add-decap-scoped-diff.json + before/after dump primitiveId->net mapping | measured: True
- quality.c99_save_reload_diff = match; identity=0, geometry=0, copper=0, unrelated=0 | source: evidence: edit-add-decap-save-reload-diff.json | measured: True
- quality.c99_pcb_check = 0 ERROR, 15 WARN, 1 INFO, total=16 | source: evidence: edit-add-decap-check.json | measured: True
- quality.c99_decap_distance = C99 sits 272 mil (6.9 mm) from nearest +3V3 (new WARN) | source: evidence: edit-add-decap-check.json finding | measured: True
- quality.boardA_final_drc = passed=true, total=0 | source: evidence: photo-led-pcb-2026-10-26/evidence/pcb-drc-final.json | measured: True
- quality.boardB_final_drc = passed=true, total=0 | source: evidence: mcu-i2c-s3-2026-10-26/evidence/pcb-drc-final.json | measured: True
- quality.boardA_pcb_check = 0 ERROR, 6 WARN, total=6 | source: evidence: photo-led-pcb-2026-10-26/evidence/pcb-check-final.json | measured: True
- quality.boardB_pcb_check = 0 ERROR, 13 WARN, 1 INFO, total=14 | source: evidence: mcu-i2c-s3-2026-10-26/evidence/pcb-check-final.json | measured: True
- provenance.import_payload = 132270 B; sha256=312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1; equals frozen boardB-final.epro2 | source: derived: raw JSONL project.import 13:44:51.304Z payload base64 decoded + SHA-256 | measured: True
- provenance.edit_export_payload = 135173 B; sha256=f65654cb7144c184137002c2efe5a8af7ed8ff7f5c79997d554f71251776e025; equals frozen edit-add-decap-final.epro2 | source: derived: raw JSONL project.export 13:48:31.984Z payload base64 decoded + SHA-256 | measured: True
- provenance.boardA_export_payload = project.export 12:51:38.024Z; 230203 B; sha256=d9ef9201e574c7ba944c7c77c77aa3364802464790e4e7daca1969884a826491; equals frozen photo-led-pcb-final.epro2 | source: derived: raw JSONL project.export payload base64 decoded + SHA-256 | measured: True
- provenance.boardB_export_payload = project.export 13:41:52.951Z; 132270 B; sha256=312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1; equals frozen boardB-final.epro2 | source: derived: raw JSONL project.export payload base64 decoded + SHA-256 | measured: True
- provenance.boardA_drc0_export_payload = project.export 12:46:53.294Z; 224778 B; sha256=6542f416c08ed4c88982ce1ac9d6d05fa3a3f52f0fe924ac939731c26a420400; file NOT present in repo | source: derived: raw JSONL project.export payload base64 decoded + SHA-256; design-state.drc0_sha256 | measured: True
- provenance.boardA_save_reload_semantic_sha = 6f9dae9a307ad81b4d8171d61768884b068aa9da0fe8d3f96a8bb2b04b1649c6 equal before/after reload | source: derived: photo-led-pcb-2026-10-26 pcb-dump-final.json and pcb-dump-after-reload.json | measured: True
- provenance.boardB_save_reload_semantic_sha = a83459175183547da179a8763086305e10f535a8a766ef0a827b73f60b5c3c1a equal before/after reload | source: derived: mcu-i2c-s3-2026-10-26 pcb-dump-final.json and pcb-dump-after-reload.json | measured: True
- unknown.tokens_llm_cost = NOT RECORDED | source: audit logs have no token accounting; tokens=0 is unrecorded | measured: False
- unknown.manual_gui_vs_agent_think = NOT RECORDED / not separable | source: audit think = wall - sum(duration); includes agent reasoning, manual EDA GUI work and idle | measured: False
- unknown.boardA_audit_cost_in_supplied_windows = NOT RECORDED (A evidence files 12:17-12:52Z; both supplied windows start 13:10Z) | source: not in either supplied audit JSON | measured: False
- unknown.user_agent_turn_count = NOT RECORDED | source: audit is per action record, not per conversation/tool turn | measured: False

## controlled_task

受控任务定义：将冻结的 `boardB-final.epro2`（132,270 B，SHA-256 312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1）导入新工程（实际工程 `mcu-i2c-s3-edit-20261026`，UUID 283b0ccaaa9c404d87056886a29c2562；同一 PCB document 40b81985cfb4a5ed），增加 C99 100nF（CC0603KRX7R9BB104 / C0603）接在 +3V3 与 GND 之间，PCB import-changes 后放置/调整 C99，仅对 +3V3/GND 执行 rip-up + autoroute，pour-rebuild，要求原生 DRC passed=true total=0、scoped diff unrelated_changes=0、save→reload→fresh dump pcb-diff match。实际执行窗口 13:44:51.3047907–13:48:56.3253434Z；两次 autoroute payload 均为 nets=['+3V3','GND']、layers=[1,2]、optimization='completion'；两次 rip-up 循环各含 +3V3 与 GND。严格三项验收在 13:48:31.9844613Z（最终 .epro2 导出）已全部满足，之后的 sch connectivity + pcb check 是额外质量检查。验收证据：`edit-add-decap-drc.json`、`edit-add-decap-scoped-diff.json`、`edit-add-decap-save-reload-diff.json`、`edit-add-decap-check.json`、`edit-add-decap-final.epro2`。

## frozen_artifacts

- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/photo-led-pcb-final.epro2 | d9ef9201e574c7ba944c7c77c77aa3364802464790e4e7daca1969884a826491 | 230203
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json | 3a07ade567e725d918410b21b3846fd6bfa414486a63db58a6c0dbfdb69199e2 | 261386
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-after-reload.json | 510c52ce9140e3abe2e80b4e0d88a0a3ec5d222907a9599260c2acf1db3da9b1 | 261384
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/save-reload-diff.json | 6abb4c65476c1b7e965e2d032935ff9c7d461e8317b6f2c27b36652a2805ae41 | 384
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-drc-final.json | bcecab466975deec1fec102618a846f3efc015aad81f67c0a99374eb016ad6ad | 147
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-check-final.json | 2587eb236057e30a2ddb99872856621305dbf940c9712a9ed795fd852d72d9f7 | 3788
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/BOM.csv | c88181adb026e7bdf09ecc72a7488e38c067576a6fcf91db6b266ad5d91973cc | 1471
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-final-top.png | d942aaecc33d7f75d947ccc4d9f0e4e472780fff00ecb3669536f09e776afe9e | 164801
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-final-bottom.png | 34e69a46ce398fd21dc7a9861c7dc43d35ecc316081712ef6e42e935a12b41a5 | 144024
- A | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-final-actual.svg | fbbd06a91dfd327b773ebc9280f4199c2954ebac883c4d3f5624efe3ad8e114f | 65936
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/boardB-final.epro2 | 312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1 | 132270
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json | 42acfe23ba0b7cb499653b218033b91ca67562b7d88d7fa99d4ee994b0a0c1c4 | 355879
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-after-reload.json | 2702c7bdeb6d08629a3c69e488fc40b911228136618c361749eca788dcf24c00 | 355881
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/save-reload-diff.json | 6abb4c65476c1b7e965e2d032935ff9c7d461e8317b6f2c27b36652a2805ae41 | 384
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-drc-final.json | bcecab466975deec1fec102618a846f3efc015aad81f67c0a99374eb016ad6ad | 147
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-check-final.json | 7c5449402562369e075214d4e50c38075f64284fbf65f854c2b2b29ce564c835 | 6827
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/BOM.csv | f2628a128b853b0ffcdbf91e0ad38220ffb49114ac951fbe35a046cf62bede46 | 1401
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-final-top.png | 7c880ebcf2b7e136cac1c9a39e15449d919e761b03579dec9003feabfc670fef | 192823
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-final-bottom.png | e50e4bc0966543960f7d6b89a16be995686ad6446840d17f7519965ef61a890c | 102986
- B | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-final-actual.svg | c6f67e6eca329e7634142a2a84267c53a311839634211e69b9910b78b7c77ad4 | 76782
- C99 | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/edit-add-decap-final.epro2 | f65654cb7144c184137002c2efe5a8af7ed8ff7f5c79997d554f71251776e025 | 135173
- C99 | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/edit-add-decap-dump.json | a32ea2a5494059c8798f9c5cdd8db8f6b88bbf5dcf6965a5b813a3d74dd61fd7 | 360359
- C99 | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/edit-add-decap-drc.json | bcecab466975deec1fec102618a846f3efc015aad81f67c0a99374eb016ad6ad | 147
- C99 | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/edit-add-decap-check.json | bb3d34b3c397d55dc2bc63f5fad6937a8790afdac537f13cd197824af3397a1e | 7508
- C99 | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/edit-add-decap-save-reload-diff.json | 6abb4c65476c1b7e965e2d032935ff9c7d461e8317b6f2c27b36652a2805ae41 | 384
- C99 | C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/edit-add-decap-scoped-diff.json | 5de326c50d4d51a4e16b2ac9fc09aba5e8c6ac51a1feeb101827495a9dde4fe3 | 11848
- AUDIT-INPUT | C:/Users/jlc/work/hds-pcb-round9/_audit-edit-window.json | 61edf9bd695eb4629d1e6434644ae7d47cd13a16192537697aa3bd0e38953791 | 2226
- AUDIT-INPUT | C:/Users/jlc/work/hds-pcb-round9/_audit-edit-only.json | 4488b39d85928a497f2a55918c18e0a85ee9b41435a9f535fac81666738c40fc | 1862
- AUDIT-INPUT | C:/Users/jlc/work/hds-pcb-round9/_actions-catalog.json | bdede60fba6148ad93f68002499a7b0fa0c7a5b622253cabf36dc5df7628414f | 152410