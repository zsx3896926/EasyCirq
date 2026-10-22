# 工作包 B（P0）：执行器可靠性与故障恢复修复报告

日期：2026-10-22
分支：`feat/round3-engineering`
代码基线：`origin/main` `0fe5cf8`（审计基线 `dc62f20` + 3 个 docs-only 提交）
真实客户端：嘉立创EDA专业版 `4.1.78.34f5b8d9`，半离线 CLI headless

## 1. 解决了什么问题

本轮只处理审计中已确认、会影响数据正确性或工程安全的问题，不重写执行桥，不删除既有能力。

| 审计 ID | 新状态 | 处理结果 | 证据 |
|---|---|---|---|
| B1-01 读取失败折叠为空 | PARTIAL | 快照增加 `integrity.read_errors`；字段/引脚/属性/分类计数失败都记录；Python 在 `apply` 前拒绝不完整快照，`reopen-check` 不返回 match | 单测 `SnapshotIntegrity`；真机 `round3-fix-snapshot.json` |
| B2-01 位号不参与验证、丢弃 execution id | DONE（真实 create 已验） | 验证优先用 execution/计划 `primitive_id`，逐字段比较 designator/unique_id/component/supplier/footprint/坐标/旋转/镜像/属性/BOM-PCB；`R?` 报 `designator_not_applied` | 真机 `apply-r999.json`；单测 `VerificationCoverage` |
| B2-02 / B3-02 计划内/页内/改位号撞车 | DONE（真实工程级阻断） | `validate_plan` 拒绝同计划重复位号；reconcile 检查当前页占用、identity mismatch、改位号撞车；`designators` + `--project-designators` 做工程级查重 | 真机 `dry-r1.json`（7 个跨页占用者）；单测 `DesignatorUniqueness` |
| B2-03 标记类型/端口方向未回读 | DONE | 从 `symbol.name` 派生 `flag_type` 与 `direction`；验证并比较 rotation/mirror | 真机 F1 dry-run 93/93 skip；单测 `NetMarkerVerification` |
| B2-04 属性/BOM 标志不比对 | PARTIAL | `manufacturer/manufacturer_id/supplier/name/other_property` 逐项比较；已有器件的 BOM/PCB 成员变更不支持时返回 `unsupported_property_change`，不再静默 skip | 单测 `VerificationCoverage` |
| B3-01 位号唯一性只查当前页 | DONE | 新增 `designators` 命令遍历全部页；`apply --project-designators` 使用该清单；未提供时结果明确 `designator_scope=page` | 真机 10 页/78 器件/13 组重复；`f1-designators.json` |
| B4-01 无写前条件 | PARTIAL | `modify_part` 携带 `expected`；目标漂移返回 `stale_target` 且不写该动作；`create_part` 写前再次检查位号占用 | 单测；完整快照哈希/时间条件仍未实现 |
| B4-02 页身份未冻结 | DONE | 读取后把 `page.current`/`schematic_name` 冻结为 `page_uuid`；before/apply/after 同一 UUID；写后核对页/工程 UUID；多页同名 schematic 拒绝猜测 | 真机 apply 全程使用固定页 UUID |
| B6-01 重试留 R? 孤儿 | PARTIAL | 创建前认领同位置/同料号/自动号孤儿；创建后轮询位号生效 | 代码+单测；真实超时注入未执行 |
| B6-03 超时后不回读 | PARTIAL | invoke 超时后做一次短回读，返回 `partial_unknown` + counts/integrity，不自动重放 | 代码；真实超时注入未执行 |
| B7-01 重开比较域缺端口/镜像/属性 | DONE | 比较工程/页 UUID、器件全字段、重复位号、标记类型/几何、端口方向/几何、属性 | 真机 reopen `match`（17/27/16/34）；创建前快照 `mismatch` |
| B7-02 斜线被静默丢弃 | DONE | 不可解析线进入 `unparsed_wires` 并强制 mismatch；零长度线归为编辑器规范化 | 单测；真机 F1 零长度线不再误报 |
| B7-03 坐标口径不一致 | DONE | apply 与 compare 统一 0.01 容差 | 单测 `position_tolerance` |
| B8-01 无版本门禁 | DONE | 非 `4.1.78.*` 默认拒绝写入；`--allow-unverified-version` 显式覆盖；doctor 检查 versionMatch/resultChannel | 真机 4.1.78 通过；单测 |
| B8-02 可写用户会话/关闭未知来源 | DONE（单测） | `origin:"user"` 默认拒绝；未知来源拒绝；`close` 只自动关 `cli` | 单测 `SessionSafetyExtended` |
| B8-03 reopen 关闭无关工程 | PARTIAL | 关闭前核对会话工程 UUID/路径；比较工程/页身份 | 真机 reopen；错误会话关闭未真机注入 |
| B1-02 异常破坏 JSON 契约 | PARTIAL | 只接受含 `ok/value` 的 CLI 响应；`value` 缺失报错；快照/重开输入包装为 `EdaInputError` | 单测 `OutputParsing` |
| B1-03 current/settle_ms/重试分类 | PARTIAL | current 固化；`settle_ms` 真实传入并生效；page_not_found 不重试，超时保留超时语义 | 代码；真机 current 路径未单独注入 |
| T-01 测试只覆盖理想路径 | PARTIAL | `tests/test_eda_exec.py` 从 23 增至 50 项；全仓 168 项通过；新增完整性/位号/验证/比较/会话/解析用例 | `python -m unittest discover -s tests` |

## 2. 修改了哪些文件和行为

| 文件 | 修改 |
|---|---|
| `design-hardware/scripts/eda_exec.py` | 快照 `integrity/read_errors`；字段级回读；工程级位号扫描 `designators`；计划/页/工程三级位号查重；`expected` 漂移检查；冻结页 UUID；孤儿认领；完整验证域；重开比较域；会话来源与版本门禁；超时部分结果；零长度导线规范化；CLI 响应解析加固 |
| `design-hardware/references/eda-execution.md` | 同步执行契约：完整性门槛、工程级位号命令、冻结页身份、逐字段验证、重开比较域、零长度线/不可解析线、版本与会话门禁 |
| `tests/test_eda_exec.py` | 新增 27 个回归用例，覆盖本轮全部修复面 |
| `docs/evidence/round3-2026-10-22/` | 9 份真机结果与哈希 |
| `docs/task-ledger-round3.md` / `docs/round3/backlog.md` | 顶部增加本轮修复状态覆盖，避免旧 DEFECT 状态过期 |
| `docs/round3/capability-matrix.md` | 顶部增加修复后口径说明 |

## 3. 实际运行了什么

### 3.1 自动化

```bash
python -m unittest tests.test_eda_exec -v   # 50 tests, OK
python -m unittest discover -s tests        # 168 tests, OK
```

### 3.2 真实 EDA（全部在独立副本、CLI 自有 headless 会话）

| 动作 | 结果 |
|---|---|
| `read` F1 页 | `integrity=complete`；60 元件分类一致（16/27/16/1） |
| `apply --dry-run` F1 既有 93 项计划 | 93 项 `skip`、0 冲突；新增的端口方向/标记类型比较未破坏既有证据 |
| `designators` 全工程 | 10 页、78 器件、0 错误；13 组跨页重复位号 |
| `apply --dry-run` 新建 `R1` + 工程清单 | `designator_already_exists_project`，列出 7 个占用页，无写入 |
| `apply --dry-run` 新建 `R999` + 工程清单 | 无冲突，`create` 动作生成 |
| `apply --save` 新建 `R999` | `verified`；expected/observed 全字段一致；`save.saved=true`；61 元件/17 器件 |
| `reopen-check` 对保存后快照 | `match`；17 器件/27 标记/16 端口/34 归一化线；`actual_integrity=complete` |
| `reopen-check` 对创建前快照 | `mismatch`；`R999` presence 差异被报告 |

## 4. 结果与证据位置

- 摘要与哈希：`docs/evidence/round3-2026-10-22/README.md`
- 关键文件：`round3-fix-snapshot.json`、`f1-dryrun.json`、`f1-designators.json`、`dry-r1.json`、`dry-r999.json`、`apply-r999.json`、`reopen-post2.json`、`reopen-pre.json`
- 原始运行目录：`C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/`（含工程副本，不提交）

## 5. 未执行项、限制和阻断条件

| 项 | 状态 | 说明 |
|---|---|---|
| 真实 getter 抛错/截断注入 | NOT RUN | 由单测和 Fake 覆盖；未在客户端制造故障 |
| 真实 invoke 超时、断连、保存失败注入 | NOT RUN | `partial_unknown` 路径未真机触发 |
| 用户 GUI 全在线会话 | BLOCKED | 未操作 `origin:"user"`；半离线结论不能写成全在线 |
| PCB/DRC/制造/样机/固件 | NOT RUN | `eda_exec.py` 的 PCB 仍未实现；E 工作包另开 |
| 已有器件 BOM/PCB 成员修改 | NOT SUPPORTED | 现在明确报 `unsupported_property_change`，不再静默跳过 |
| 斜线/非正交线的几何比较 | PARTIAL | 强制 mismatch；尚未实现通用线段几何模型 |
| 快照哈希/读时间条件写 | PARTIAL | 已按页 UUID + 单对象 expected 防漂移；未做全快照 hash 比对 |
| 函数级覆盖率 | NOT RUN | 只统计测试数，未重新生成行/函数覆盖报告 |

## 6. 对新手和工程师的实际影响

- **新手**：`apply` 不再可能因为一次读取失败把已有器件当成不存在而重复创建；遇到不完整读取会得到 `snapshot_incomplete`，可以按提示重新读取，而不是拿到一个“成功”的结果。
- **工程师**：位号冲突现在在计划内、当前页和工程级三层被拦截；`designators` 能直接给出全工程重复位号清单；`reopen-check` 的 `match` 现在覆盖端口方向、标记类型、镜像和 BOM/PCB 标志，不再只比器件名和坐标。
- **交付语言**：`verified` 现在要求 `integrity=complete` 且逐字段 expected/observed 一致；只读文档、只有网表或只有截图都不能替代。

## 7. 后续接手命令与环境

```bash
# 只读诊断
python design-hardware/scripts/eda_exec.py doctor
python design-hardware/scripts/eda_exec.py sessions

# 读页并检查完整性
python design-hardware/scripts/eda_exec.py read --project <copy> --page <page_uuid> --output snapshot.json

# 工程级位号清单（会切换自有 CLI 会话活动页）
python design-hardware/scripts/eda_exec.py designators --project <copy> --output designators.json

# 对账/写入（先 dry-run）
python design-hardware/scripts/eda_exec.py apply --project <copy> --plan plan.json \
  --project-designators designators.json --dry-run
python design-hardware/scripts/eda_exec.py apply --project <copy> --plan plan.json \
  --project-designators designators.json --save --output apply.json

# 重开比较
python design-hardware/scripts/eda_exec.py reopen-check --project <copy> \
  --snapshot snapshot.json --page <page_uuid> --output reopen.json
```

环境：Windows 11、Python 3.13.15、嘉立创EDA专业版 4.1.78.34f5b8d9、CLI 半离线。所有写入必须使用授权副本；默认不驱动用户 GUI 会话。
