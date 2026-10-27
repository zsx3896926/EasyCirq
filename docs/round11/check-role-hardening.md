# check 角色强化与局部改板资产（round11 离线收尾）

日期：2026-10-27。基线：PR #24 分支 `feat/offline-toolchain-round11`（`cd3476e`）。
本轮**不调用 EDA**；所有结论均为离线工具/夹具验证。

## 1. 失败输入（保留为负例）

2026-10-27 双路按键板首次局部改板：第一基线 D4 中心 y=760 mil，D4 顶部到 R3 底部只有
73.559 mil；直接上移 2.00mm（78.74 mil）会与 R3 本体重叠 5.181 mil。

保留在：

- `design-hardware/cases/dual-button-led-night-20261027/negative-direct-move/board-baseline.json`
- `.../placement-direct-move.json`
- `.../expected.json`、`README.md`

**接受标准：该输入必须被拒绝。** 后续先下移 D3/D4 30 mil 预留空间，再做同一 +2mm 改板；
这证明的是“预留空间后的局部修改可完成”，不是“任意既有布局都能自主解决冲突”。

## 2. 工具/算法改进

### 2.1 check 角色强校验

`pcb_gate.py::_shape_ok('check')` 不再接受“只要存在 findings/summary”：

- `summary` 必须有非负整数 `errors/warnings/total`（可选 `infos`）；
- findings 每项必须有非空 `type`，`level` 只能是 ERROR/WARN/INFO；
- `summary.total/errors/warnings/infos` 必须与逐条 findings 一致；
- 必须有 `trackCount`/`padCount`（可选 `viaCount`）来源计数；
- `passed` 若存在必须是 bool，`coverage` 若存在必须是对象。

这样 placement-check、空 summary、字符串计数、矛盾计数都不能冒充 DFM check。

### 2.2 多候选歧义

沿用 PR #24 的 alternatives/conflict 框架：

- 内容相同的多个 check 副本：只记 alternatives，不判歧义；
- 多个**合法** check 内容不同、且没有 manifest/`--check` 绑定：PG4 `EVIDENCE_AMBIGUOUS`
  **hard fail**，不静默选“最新”；
- 有 hash-bound manifest 或显式 `--check` 绑定时：按绑定选择，不把自动歧义判失败。
  manifest 路径会记录 alternatives/advisory；显式 `--check` 是人工选择，当前不扫描旁路
  候选（如需审计旁路文件，用 manifest 或人工查看 evidence 目录）。

### 2.3 局部移动前空间检查

新增 `scripts/check_move_clearance.py`（`design-engine-pcb-move-clearance/v1`）：

- 只读 pcb dump；比较目标件移动后的 bbox 与同层其他器件、板框；
- `clear|conflict|blocked|invalid_input`；不写 EDA，不证明铜/丝印/keepout/DRC；
- 负例 `conflict`，接受版 `clear`；测试覆盖板边、未知位号、较小移动。

### 2.4 可复用资产

- `assets/pcb-placement-templates.json` 新增 `dual-channel-switch-led`：两路按键—LED—限流
  电阻并列布局；在实测接受基线上 `pcb-template-plan` 复现 6 个位姿（status=planned），
  标记 `offline-tested`，不是 EDA 已验证实例。
- `assets/pcb-delivery-checklist.md`：身份、原理图、PCB、局部改板、BOM/归档/限制口径的交付清单。
- `assets/schematic-frame-plan.example.json` + `scripts/sch_frame_meta_check.py`：写 frame 前
  强制 `order`/`purpose`；缺 `purpose_text_id` 默认 blocked，避免到 strict 阶段才发现布局不完整。

## 3. 测试与重放

- 目标测试：`test_pcb_gate` 48 + `test_pcb_gate_provenance` 24 + `test_move_clearance` 6
  + `test_dual_channel_template` 1 + `test_sch_frame_meta_check` 7 = 85 tests OK。
- 全量：`python -m unittest discover -s tests` → **1263 tests OK**。
- `skill_selftest.py` → **5 PASS / 0 FAIL**。
- 冻结 case 重放（manifest 绑定）→ gate pass 8/8；PG4 check 绑定
  `source_dump_sha256=04aee270...`，PG7 project/doc 为
  `1e2020e3832949b1971e90dc59b6e280` / `49c8e7a5dc2e8f59`。
- 同一冻结 case 加一个合法但不同的 `pcb-check-alternate.json`、去掉 manifest →
  gate **fail**，PG4 `EVIDENCE_AMBIGUOUS` hard；显式 `--check pcb-check-final.json` 后
  gate pass。报告：`gate-replay-manifest.json`、`gate-replay-ambiguous.json`、
  `gate-replay-ambiguous-override.json`。

## 4. 独立复核后补强（PR #25 合入后）

- **被拒绝的 check-like 候选不能静默消失**：新增 `rejected_candidates`；无 hash-bound
  manifest/`--check` 时，新出现但 shape 非法/解析失败的 check 候选会产生
  `EVIDENCE_CANDIDATE_REJECTED` hard，旧干净报告不能因此通过。
- **path-only manifest 不再降级歧义**：只有 manifest 带 `sha256` 且 `binding.error` 为空，
  或显式 `--check`，才把 check 歧义降为 advisory；只有路径的 manifest 仍 hard。
- **placement 不能靠补计数器冒充 DFM**：`_check_shape_ok` 拒绝 placement schema/`hard_ok`/
  `constraints`，并要求至少一个真实 DFM 规则计数器（`clearance`、`powerNotPoured` 等）；
  `pcb-placement-check-*` 也不会被 `_manifest_role` 误读为 check。
- **歧义按语义比较**：同内容不同 JSON 格式/CRLF 不再误判 hard；raw sha 仅保留在
  alternatives 审计。
- **regression profile 不翻转 not_run**：PG4 未评估时不再被 check 歧义改成 fail。
- **frame meta 非整数/不可哈希 order**：现在走 `invalid_input`，不抛 traceback。
- **check 文件名仍需含 `pcb` 与 `check`**：无 `pcb` 前缀的合法 DFM 报告不会被自动发现，
  需用 manifest 显式绑定；这是 glob 的已知边界，不在本轮扩大（避免误收无关 check 文件）。
- 补测：empty/contradictory 候选改为 final 命名 + 更新 mtime，旧实现会选中它们；
  新增 path-only manifest、placement+计数器、同内容不同格式、regression profile、
  manifest placement role 等测试。

## 5. 本工程通过 ≠ 工具整体成熟

- 本工程：双路按键板在**预留空间后的基线**上完成 LED2 +2mm 改板；gate 8/8、case complete。
- 工具：check 角色强校验/歧义、move clearance、template、checklist、frame guard 已离线验证。
- 未证明：任意既有布局的冲突自主解决、真实 EDA 写入/DRC/布线/铺铜、Gerber/CPL、
  热/EMC/实物功能；未因为这个案例通过就宣称 Skill 整体能力成熟。
