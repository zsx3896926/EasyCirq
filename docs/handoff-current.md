# Current handoff — 2026-10-26 — v0.9 PR #20

## 仓库与分支

- 仓库：`hardware-design-skill`；工作树：`C:/Users/jlc/work/hds-pr20-verify`
- 分支：`feat/skill-v0.9-eda-verify`，基于 `origin/feat/skill-v0.9-reviewed` `108403c`
- 当前 HEAD：`107ec27`（含 `d1c5deb` + `366f6f8` 与 v16 绑定证据文档）
- PR #20 head 仍是 `feat/skill-v0.9-reviewed`；本分支尚未推送
- 另一个工作树 `C:/Users/jlc/work/hds-merge-20261026` 有他人未提交 WIP
  （`layout_move_plan.py`、`readback_verify.py` 及测试），未触碰、未采用

## 本轮工具链改动

- `scripts/svg_text_bbox.py`：无头 Chromium/Edge 实测官方 SVG 全部渲染 `<text>`；
  photo-led 同页 134 条、v14 136 条，与既有实测逐项一致。
- `scripts/layout_from_easyeda.py`：`sch list --include-page-primitives` +
  `visible_text` + `sheet-geometry` + 渲染文字 → `sch_layout_check` 输入；
  分类 pin_name/pin_number/netflag/net_label/wire_name/title_block/border/unowned；
  `wire_endpoint_check=false`（连通性交给 `sch check`）。
- `sch_layout_check.py`：新增 `unowned_visible_text`、`duplicate_net_text`、
  `unanchored_net_text`、`netflag_rotation_outlier`、`netflag_text_vertical`、
  `zone_reading_order`、`title_block_duplicate_text`、`text_wire_clearance`；
  符号自有脚名/脚号不再当普通碰撞；info-only 不阻塞（`--fail-on-info` 可升级）；
  `--out` UTF-8 落盘。
- `scripts/pin_net_intent_check.py`：设计意图 vs `sch read` 的物理引脚连通组比较；
  网名拼写可不同，支持 `sch read` 的 `number` 字段；功能脚名需 `pinMap`。
- `scripts/component_identity_check.py`（jlc-61）：device/symbol/footprint/BOM 身份；
  可选 PCB 绑定（无 PCB 输入时 `pcb_binding=not_run`）。
- `tests/test_sch_acceptance.py`、`tests/test_pin_net_intent.py`、
  `tests/test_sch_acceptance_v14.py`、`tests/test_component_identity_check.py`；
  真实 fixture `tests/fixtures/photo-led-acceptance.json`、`photo-led-v14/`。
- 验证：`python -m unittest discover -s tests` → **960 tests OK**；
  `skill_selftest.py` → **5 PASS / 0 FAIL**。
- `d1c5deb` 追加：自身导线边缘级豁免、无结点交叉必须有宿主 junction 证据、
  实例 uniqueId/component.uuid 与 `--expected-changes` 声明门禁。
- `366f6f8` 追加：junction 证据绑定 pageId + snapshotSha256 + 两段导线 ID；
  页/哈希/导线不匹配按 stale evidence 拒绝，不再降 hint。

## 真实 EDA（本机 EasyEDA Pro 4.1.78 / easyeda-agent 1.15.0）

### 1) photo-led-5v-20261026（协作完成）

- P1 `cd008f919db36eba`；12 网 / 47 脚 / 0 floating / 37 组件。
- 编号按阅读顺序 1 光敏 / 2 供电 / 3 阈值 / 4 LED；标题在框左上；purpose 持久修复。
- 图签两处 Claude Code 已消除（绘制/审阅留空，避免平台双渲染重复）。
- v16 追加：R3 Name 上移 10 raw；VREF 短桩绕开 zone2 purpose（先下移、再绕左/上，
  避开文字与线名）。`strict_missing: []`、`status: info_only`；3 条无结点交叉 hint
  已绑定页 `cd008f919db36eba`、快照 SHA-256 `0392d03c…` 和两段导线 ID（`25209c69…#3`
  等），另有 3 条 5 raw 内贴线 hint。
- 身份核验（v14→v16）：`pass_sch_only`，19/19 位号/uniqueId/component.uuid/
  device/symbol/封装/脚名不变；1 条 expected_change_unused info；BOM 导出与
  SCH↔PCB 仍 NOT RUN。
- 残留：`sch check` **7 条 reversed-net-flag**（GND/+5V 旗 rot=0 而桩水平），
  未逐一重连；图签 Drawed 留空。
- 最终证据：`evidence/final-v16.png/.svg`、`v16-check.json`、`v16-list.json`、
  `v16-identity-check.json`；v14 原生 `.epro2` SHA-256 `502D6FD2…`（v16 未重导）。

### 2) ne555-blinker-1hz-20261026（新建，已保存重开）

- 工程 `856ec8994a544ad999a5adf69be04dd9`；P1 `2beb0746a6a6c75a`；
  10 器件 / 7 网 / 0 floating；`sch gate` PASS；pin-net intent `match`。
- 1k/68k/10µF → f≈1.05Hz、D≈50.4%；OUT→330Ω→LED。
- 证据：`C:/Users/jlc/work/ne555-blinker-1hz-20261026/evidence/`（final-v2、
  final-after-reload、check9、gate、pin-net-diff）。
- 残留：多个电源/地标记竖排文字（管脚水平导致），方向不统一；无 purpose 文字；
  Drawed 留空；原生归档 `evidence/final.epro2`（44,712 B，SHA-256 `0b7ad4a3…`，
  restoreVerified=false）；PCB/仿真/实物 NOT RUN。

### 3) ams1117-3v3-20261026（新建，已保存重开）

- 工程 `7686883008644dea9fd9317d949a5f92`；P1 `86faeee12e6b50e6`；
  6 器件 / 3 网 / 0 floating；`sch gate` PASS；pin-net intent `match`。
- J1→10µF→AMS1117-3.3→22µF+100nF→J2；三功能区框。
- 证据：`C:/Users/jlc/work/ams1117-3v3-20261026/evidence/`（final-v2、
  final-after-reload、check-final、gate、pin-net-diff）。
- 残留：输出电容为 22µF 0805 陶瓷，**不是**数据表保证的 22µF 固体钽，稳定性未验证；
  多个电源/地标记竖排文字；无 purpose 文字；未做负载/纹波/热/PCB；原生归档
  `evidence/final.epro2`（35,416 B，SHA-256 `793169d7…`，restoreVerified=false）。

## 明确未做 / 边界

- 未把任何配方标成 `eda-verified`：三张图仍有可见文字方向/注释缺口，且新工程主要用
  CLI typed 流程而非 `sch_recipe` 直接落地。
- 未发布 Release、未替换用户已安装 Skill、未合并 PR。
- 未推送本轮 commit；PR #20 描述待重写。
- 未做 PCB 全流程（jlc-29 在用窗口做独立 PCB 测试，21:30 前需归还）。
- 半离线 CLI 会话未用于本验收；全部为全在线 GUI 会话。

## 下一条具体动作

1. 跑通 `git status`，提交项目文档/证据索引并推送本分支到 PR #20 head。
2. 重写 PR #20 描述：工具链、三工程真实结果、残留与 NOT RUN。
3. 若继续：为 555/稳压器补 purpose 文字（等待 typed 文本创建）、统一竖排电源/地标记、
   稳压器换 22µF 固体钽并做负载/热测试；导出原生 `.epro2`。
