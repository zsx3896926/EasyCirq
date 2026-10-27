# round11 评审报告 — 离线能力强化与真实样例回放

## 1. 基线与分支

- 评审基线：`origin/main` `066a74b`（PR #22 后，0.9.2）。
- 分支：`feat/offline-toolchain-round11`；worktree `C:/Users/jlc/work/hds-offline-r11`。
- 代码提交：`6bbc761`；最终候选：`8c7f318`（合并 576bc0e）（含 PR #23 check-role 修复与 PR #25 强校验/负例资产）；PR #24 https://github.com/zsx3896926/hardware-design-skill/pull/24
- **真实 EDA 调用：0 次**。未启动/连接 EasyEDA，未调用 `easyeda`（含 health/help/read/export），未访问本机服务/WebSocket/连接器，未修改工程或已安装执行器。

## 2. 已复现并修复的缺陷

| 缺陷 | 复现 | 修复 | 回归 |
|---|---|---|---|
| 两侧空组件返回 `match` | `compare_sch_pcb({}, {})` | 空侧/无可比对象 → `not_comparable` | `test_two_empty_sides_are_not_a_match` 等 |
| `absent/empty/invalid/measured` 混淆 | 缺 pad 与空网、bool/字符串/NaN 计数 | 四态分离 + `diagnostics` | `test_missing_pad_is_distinct_from_unconnected` 等 |
| `summary.errors=0` 但 findings 有 ERROR 仍 clean | 构造 summary 0 + ERROR finding | `contradictions`、`passed=false`、门禁 `pcb_check_inconsistent` | `test_summary_zero_with_error_finding_is_not_clean` |
| 外层 `ok=false` + 内层 result | 构造 envelope | `trusted=false`，不因内层齐全变成功 | `test_outer_failure_envelope_is_preserved` |
| alias 目标 `None` 网络异常/缺失目标被忽略 | `pin_aliases` + 无网 pad | 不再抛异常；`alias_target_missing`/`ambiguous_alias_target_net` | `AliasTests` |
| 重复位号/脚号被字典覆盖 | 重复 R1、重复 pin 1 | 保留首个 + `duplicate_*` 失败，不静默 | `DuplicateTests` |
| 网名变化与分区变化混在一起 | 一致改名 / 部分改名 | `match_with_renames` + `name_changes`；`partition_match` 单独 | `NetPartitionTests` |
| 全部 ignore 仍算完整验证 | 排除 R1/R2 | `not_comparable` + `excluded_designators` | `test_all_objects_excluded_is_not_a_pass` |
| DRC `passed=true` + total/violations 矛盾 | 构造矛盾回执 | `drc_inconsistent`、`ok=false` | `DrcParserTests` |
| lint bool/负数被当数字 | score=true / overlap=-1 | `measured=false` + diagnostics | `LintParserTests` |
| net-path 空要求返回 pass | `evaluate_netpath([], [])` | `not_applicable` | `test_empty_requirements_are_not_a_pass` |
| 证据被复制后 `touch` 恢复新鲜 | manifest `produced_at` 旧 + mtime 新 | manifest 时间/哈希优先 → `STALE_EVIDENCE`/`EVIDENCE_BINDING` | `test_manifest_timestamp_beats_touched_mtime` |
| 两个工程文件混放静默择一 | 两个不同 `projectUuid` 的 DRC | `EVIDENCE_IDENTITY_CONFLICT`；manifest 缺件不回退 | `test_two_projects_in_one_directory...` |
| 计划缺 rotation/layer 默认 0/顶层 | 缺字段 board/plan | 拒绝或继承并声明 `pose_defaults` | `test_pcb_apply_plan` 相关 |
| 重复移动/no-op 写入 | 目标 pose=实测 | `no_op`，不写 playbook、不调 CLI | `test_all_noop_legacy_plan_writes_nothing` |
| journal 把已发出当已确认 | skip journal / save fail | `unknown/failed/confirmed/not_sent` + `recovery.safe_to_retry=false` | `test_missing_journal_after_send_is_unknown...` |
| 线宽越界、keepout 被忽略 | 中心线在内但宽度越界/keepout 相交 | `outside_outline_width`/`copper_intersects_keepout` | `test_geometry_primitives` |
| 0/360 角度误报 | J1 270 vs -90 | 角度归一，不报无关变化 | `test_apply_verifies_a_real_placement_move` |
| 模块复用缺 footprint 仍算兼容 | footprint 缺失/尺寸变化 | `footprint_unmeasured`/`footprint_size_mismatch`/网络分区 | `ReuseTests` |

## 3. 增强的可执行能力

- `tools/offline_suite.py`：`HDS_OFFLINE=1` + `offline_guard`，从任意 cwd/干净临时目录跑全量；真实 CLI/网络立即失败，假 CLI 需显式标记。
- `tools/offline_benchmark.py`：一条命令生成 9 个冻结用例的 correctness/coverage/timing，含真实证据哈希、修改前后候选、变形与 holdout。
- `sch_visual_audit.py`：对象/位置/原因/未执行建议、字体不确定性、netflag policy 状态、结点证据分组、分析叠加 SVG（水印 + `official_export:false`）。
- `pcb_gate.py`：manifest 绑定、项目/页冲突、`freshness_basis`、`semantic_sha256`、`match_with_renames`、pin alias/ignore。
- `pcb_apply_plan.py`：no-op、journal 状态、恢复语义、宽度/直径/keepout 几何、原子报告。
- `design_engine`：凹板 polygon、`locked`/`spacing`、候选评分组成、`routing_verified=false`、复用 rotation/尺寸/网络分区。

## 4. 样例证据

- **photo-led v14 图面**：`sch_visual_photo` 保留 1 个 `bbox_overlap` + 2 个 `wire_enters_bbox` 阻塞残差；3 个有宿主无结点证据的交叉、2 个近距文字仍是 info，没有被阈值放宽统一降级。离线叠加图与报告：`docs/round11/photo-led-v14-overlay.svg`、`docs/round11/photo-led-v14-visual.json`（均为 `analysis_overlay`，非官方导出）。
- **真实 photo PCB 门禁**：`gate_photo_regression` 在真实证据目录（只读，46 个输入文件已冻结 SHA-256）上 `pass_with_gaps`；PG1/PG3/PG6/PG7/PG8 pass，PG2/4/5 not_run。
- **PR #25 资产**：check 强校验（summary/findings/source counters 一致）、多候选歧义硬失败；`check_move_clearance.py`、`sch_frame_meta_check.py`、`dual-channel-switch-led` 模板、负例 `negative-direct-move/`、交付清单已并入并跑通。
- **真实 controlledB manifest**：`docs/round10/controlledB` 在 `--profile regression` 下 `pass_with_gaps`（PG1/PG2/PG3/PG6/PG7/PG8 pass）；manifest 的 CRLF 归一哈希、源 dump 绑定、真实 lint 的 `null` 明细数组均被正确接受。`--profile full` 仅因缺 `--key-nets` 在 PG5 blocked，不是证据绑定失败。
- **候选修改前后**：photo 全量 intent 仍选 `signal-chain`；`signal-chain/mechanical` hard_ok、`density` hard false；HPWL 18664.6/22218.68/18664.6、面积 3945153.68 与冻结 `candidates.json` 在 0.02 容差内一致（无硬约束退化）。
- **三种结构**：`power-input`（接口—保护—核心）、`driver`（晶体管—负载—回流）、`ldo-power`（LDO—输入输出电容）均 selected；LDO 合成板 HPWL 820 mil。
- **硬约束增益**：同一 keepout 边界，旧 bbox-only 检查 `legacy_hard_ok=true`，新过滤器 `new_hard_ok=false` 且 `keepout_collision`。
- **holdout**：凹板 L 缺口 track 被拒绝、下臂 track 接受；该样例实现后新增，未参与调参。
- **变形**：组件/引脚/焊盘倒序 + 坐标平移仍 `match`；PCB 短接必须 `mismatch`。

## 5. 测试与基准实际结果

- 基线段：`python -m unittest discover -s tests` → **1121 tests OK**（改动前）。
- 最终全量：**1257 tests OK**。
- `python tools/offline_suite.py`：**1257 tests OK**；导入扫描 72 modules，0 blocked / 0 error / 0 system_exit。
- `python design-hardware/scripts/skill_selftest.py`：**5 PASS / 0 FAIL / 0 NOT RUN**。
- 基准：**9/9 pass**（`benchmarks/offline-round11/result.json`，`--runs 3`）：

| 用例 | min (s) | median (s) | 输入字节 |
|---|---:|---:|---:|
| source_hashes | 0.023 | 0.023 | 2,123,582 |
| gate_photo_regression | 0.128 | 0.135 | 1,878,853 |
| sch_visual_photo | 0.055 | 0.059 | 72,240 |
| candidates_photo_full | 0.110 | 0.113 | 156,651 |
| candidates_structures | 0.235 | 0.236 | 159,181 |
| apply_noop | 0.041 | 0.042 | 134,779 |
| placement_constraint_gain | 0.0001 | 0.0001 | 567 |
| holdout_geometry | 0.0004 | 0.0004 | 1,497 |
| deformations | 0.009 | 0.009 | 299,831 |

性能只记录本机本次输入规模/运行次数/统计口径，没有同范围旧版基线，因此不宣称提速百分比。

## 6. 未完成与原因

- K 安装/缓存/兼容性演练、L 输入安全/批量回放：本轮按优先级未实施；无外部阻断，属于扩展包。
- 真实 EDA 读写、原生 DRC/check/lint、保存重开、布线/铺铜、Gerber/CPL、板厂 DFM、热/EMC/固件/实物：**NOT RUN**；按任务边界本轮禁止调用 EDA。
- 图片字节级回归、官方导图人工视觉签核：**NOT RUN**；`sch_visual_audit` 输出为分析叠加图。
- 未安装 0.9.3 到客户端、未发 Release、未合并 PR。

## 7. 独立复核

本轮改动经过 4 个维度的独立审查（证据解析、门禁 provenance、执行/几何、离线入口/文档），每条候选再由独立 verifier 尝试反驳；共确认 30 条缺陷并已修复/补测，包括：真实 lint 的 `null` 明细数组被误判未测量、summary.total 大于逐项 findings 仍 clean、多对一 alias 分区误判、duplicate manifest role 静默回退、`inferred_mtime` 被当内容时间、显式 override 混用 manifest、manifest 路径受 glob 限制、keepout 约束未进入铜检查、实测 rotation 被 normalize_board 补 0、凹板 pour 边/keepout 宽度/覆铜覆盖 keepout、preferred 约束被硬拒绝、journal 头校验失败仍 confirmed、复用网络未测量/旋转偏移、locked/fixed mm 坐标重复缩放、no-op 无 primitiveId 被拒绝、arc outline 被标 exact、文档批量替换损坏、guard shell 绕过、0 测试假绿、`--out` 父目录缺失、基准输入未全部哈希、变形基准 base 非 match 等。复核中也有一条“sch_visual 阈值过宽”被 verifier 判为非缺陷（真实残差对象确实保留）。

## 8. 结论边界

本轮结论仅为**离线工具链验收**。所有 `simulated:true` 日志、假 CLI、冻结 JSON 和合成边界样例都不是真实 EDA 或硬件验证；真实 EDA/硬件验收仍需下一轮在显式授权下执行（清单见 `docs/handoff-current.md` §6）。

## 9. PR

- 分支：`feat/offline-toolchain-round11`
- PR：https://github.com/zsx3896926/hardware-design-skill/pull/24（#24）
- 代码提交：`6bbc761`；PR head 随文档提交前进；未合并、未发 Release、未替换已安装 Skill








