# 离线回归、证据绑定与冻结基准

本页说明本轮离线工具链的可执行入口、边界和判据。所有命令只读本地 JSON/SVG/CSV，**不启动或连接 EDA、不调用真实 `easyeda`、不写工程**。通过只代表离线检查通过，不证明真实 EDA、布线、制造或硬件功能。

路径约定：本页第 1/9 节的 `tools/...` 与 `benchmarks/...` 只在仓库开发环境存在（安装到客户端的 Skill 包不含 `tests/`/`benchmarks/`），须在**仓库根目录**运行；Skill 目录内的脚本用 `python scripts/<name>.py`。第 8 节按仓库根目录写全路径。

## 1. 一条命令跑离线套件

```bash
python tools/offline_suite.py
python tools/offline_suite.py --out docs/round11/offline-suite.json
python tools/offline_suite.py --inventory docs/round11/offline-inventory.json
```

`offline_suite.py`：

- 设置 `HDS_OFFLINE=1`，安装 `offline_guard`：真实 `easyeda`/`easyeda.exe` 或进程内网络连接立即 `OfflineViolation`；
- 只允许路径中含 `fake` 或文件带 `HDS_FAKE_CLI`/`FAKE_EASYEDA` 标记的假 CLI；
- 在全新临时 `TMP/TEMP` 下导入所有脚本并运行 `tests/`，从任意工作目录可运行；
- 输出 `simulated:true`、测试计数、被拦截事件和静态清单；不把模拟日志当真实证据。

`offline_guard` 不是 EDA 适配器，只是测试安全缝。允许假 CLI 的规则是显式的；不要为了“跑通”把真实 CLI 路径改名成 fake。

负例在 `tests/test_offline_guard.py`：裸 `easyeda`、`subprocess.run(['easyeda',...])`、`socket.connect` 均被拦截；带标记的假 CLI 通过。

## 2. 证据解析：absent / empty / invalid / measured

`pcb_evidence.py` 是所有 PCB 门禁/案例工具的共享解析层。它区分：

| 状态 | 含义 | 结果 |
|---|---|---|
| `absent` | 文件或字段不存在 | `blocked`/`not_comparable`，不是 pass |
| `empty` | 字段存在但为空列表/零对象 | 不当作 match；两侧都空仍 `not_comparable` |
| `invalid` | 类型/数值非法（bool 当数字、字符串数字、负数、NaN、Infinity） | 结构化 `diagnostics`，不静默归零 |
| `measured` | 有完整字段且一致 | 才允许进入 pass 判定 |

`parse_pcb_check` 把 `level` 与 `severity` 统一归一为 ERROR/WARN/INFO；summary 与逐条 findings 交叉核对，`summary.errors=0` 但存在 ERROR finding 或 `total` 小于计数时判 `contradictions`，`passed=false`。外层 `{"ok":false,"result":{...}}` 保留为 `trusted=false`，不因内层字段齐全而变成成功。

`parse_drc` 只有 `passed=true`、`total=0`、`violations=[]`、`counts.connection=0` 且计数一致时 `ok=true`；裸 `{"passed":true}` 不是测量。

`evaluate_netpath([])` 是 `not_applicable`，不是 pass；`path_kind` 缺失记 `unmeasured`。

`validate_warn_disposition(..., levels=('ERROR','WARN','INFO'))` 用同一稳定 key 检查三个级别；`fixed` 仍出现即 stale。

## 3. SCH↔PCB 比较

`compare_sch_pcb` 分开报告：

- 器件存在性：`missing_component` / `extra_component` / 重复位号；
- 引脚存在性：`missing_pad` / `extra_pad` / 重复脚号；
- 未连接：两侧都为空网是 `unconnected`（**不是 NC 证明**）；一侧为空是 mismatch；
- 组合焊盘：`pin_aliases` 逐目标 pad 检查存在性；目标缺失是 `alias_target_missing`，目标 pad 多网是 `ambiguous_alias_target_net`；
- 网络分区：引脚集合分组变化是 `mismatch`；分组不变仅网名变化是 `match_with_renames` + `name_changes`；
- 身份：两侧都有的 `uniqueId`、component/device/symbol uuid、footprint、BOM 字段逐项比较；缺字段列入 `not_checked`，不猜测；
- `ignore_designators` 明确列入 `excluded_designators`；全部排除是 `not_comparable`，不是完整验证。

门禁读取 `sch_pcb` 证据时接受 `match`/`match_with_renames`；`not_comparable` 失败。计算路径可加 `--pin-aliases` 和 `--ignore-designators`。

## 4. 证据来源与失效

`pcb_gate.py` 的 discovery 仍按角色匹配，但：

- 优先 `*-final*` 文件，scratch/edit/copy 降级；多个兼容候选内容不同会记录 `EVIDENCE_AMBIGUOUS`，项目/页身份不同直接 `EVIDENCE_IDENTITY_CONFLICT`；
- case 目录有 `manifest.json` 时，manifest 的 `sha256`、`source_dump_sha256`、`produced_at` 优先于文件名和 mtime；manifest 指定文件缺失时**不**回退到旁边文件；
- 证据文件哈希与 manifest 不一致、源 dump 变化、项目身份不一致 → `EVIDENCE_BINDING` 失败；
- `produced_at`/payload capture 优先于 mtime；只有 mtime 时在 `not_checked` 写明 `freshness_basis`，复制旧文件再 `touch` 不能获得内容绑定；
- 原始 `sha256` 与去时间/路径的 `semantic_sha256` 同时写入证据 meta。

生成 manifest 用 `pcb_case.py`；没有 manifest 时仍可运行，但新鲜度只能按 mtime/捕获时间辅助判断，不能声称内容绑定。

## 5. 离线执行计划

`pcb_apply_plan.py`：

- `--apply` 之外只编译 playbook，不调用 CLI；相同输入产生确定的命令序列；
- 实测 pose 缺 `x/y/rotation/layer` 时拒绝，不默认成原点/顶层；目标缺 rotation/layer 时继承实测值并在 `pose_defaults` 声明；
- 目标 pose 与实测相同 → `no_op`，不写 playbook、不发 CLI；混合计划只跳过 no-op 写入；
- journal 每步区分 `planned`/`sent`/`confirmed`/`failed`/`unknown`；`confirmed` 的 status 以 ok 开头，`unknown` 表示已发出但无确认；
- `recovery.safe_to_retry=false`；已发出但未确认时必须先取 fresh dump，不得把“已发出”当“已生效”；
- 报告原子写入（临时文件 + `os.replace`），不会把半份 JSON 留给后续工具；
- 不实现、也不宣称事务回滚。

## 6. 几何精确/近似

`design_engine/geometry.py` 提供角度归一、凹多边形内点、矩形/圆/带宽度折线包含、线段相交和距离。`pcb_apply_plan` 的铜几何检查：

- 矩形/凹形板按实测 polygon 检查；`arc-polyline` 明确标为 `arc-polyline-approx`，无 polygon 的 arc 板拒绝；
- track 中心线在内但线宽越界 → `outside_outline_width`；via 直径越界 → `outside_outline_diameter`；pour 边越界 → `pour_edge_outside`；
- keepout/hole 与铜相交 → `copper_intersects_keepout`；
- 只提供 bbox 时不能证明精确包含，铜写入拒绝或明确 `bbox-approx`。

`validate_placement` 同样用 polygon 检查器件 bbox/pad；凹板缺口内的器件不会被 bbox 误判为在板内。

## 7. 布局候选与模块复用

`plan_candidates` / `plan_placement` 先硬过滤（板内、同层重叠、固定/锁定、edge、keepout、spacing），再按 critical findings、escape proxy、HPWL、面积排序；输出 `score_components`/`selection`。`no_feasible_candidate` 表示固定种子与预算内未找到，不是“证明无解”。`routing_verified=false` 始终保留；HPWL/escape 是代理，不是布通证明。

`plan_reuse` 在 footprint/pin 集合之外还检查：footprint id 缺失（`footprint_unmeasured`）、body 尺寸不一致、声明 rotation 不允许、引脚角色网络分区变化；操作带 `rotation/layer`；失败明确 rejected，不静默改成任意摆放。

## 8. 原理图离线图面回归

先按 [原理图排版与看图验收](schematic-layout.md) 生成 `layout.json`，再运行：

```bash
python design-hardware/scripts/sch_visual_audit.py layout.json \
  --out-svg review/photo-led-v14-overlay.svg \
  --out review/photo-led-v14-visual.json
```

报告复用 `sch_layout_check.analyze` 的 findings，并补充：对象 ID/位置、原因、最小建议（`executed=false`）、字体测量来源/不确定性、netflag 方向是否真的有 policy、以及“有结点证据的交叉”和“未验证交叉”的分组。SVG 是**分析叠加图**，带 `ANALYSIS OVERLAY — NOT AN OFFICIAL EDA EXPORT` 水印和 `official_export:false` metadata；不是官方重新导出的工程图。

真实 photo-led v14 样例保留 1 个 `bbox_overlap` + 2 个 `wire_enters_bbox` 阻塞残差；3 个有宿主无结点证据的交叉和 2 个近距文字是 info，不升级为阻塞。

## 9. 冻结基准

```bash
python tools/offline_benchmark.py --runs 3 \
  --out benchmarks/offline-round11/result.json
```

基准 `benchmarks/offline-round11/expected.json` 记录来源路径、SHA-256、预期结果与推导方式；真实证据只读，派生数据另存。当前覆盖：

- 真实 photo-led 回归门禁、v14 图面残差；
- 修改前后 photo 候选对比（冻结 `candidates.json` 的 selected/hard/HPWL/面积，容差 0.02）；三种结构（接口—保护—核心、LDO—输入输出电容、晶体管—负载—回流）；
- no-op 计划、硬约束增益（keepout 被新过滤器捕获）、数组倒序/平移语义不变、PCB 短接被检测；
- holdout 凹板/缺口样例（实现后新增，未参与调参）。

结果包含 correctness、coverage、每个用例的 min/median/max 耗时、输入字节、环境、未覆盖项；不宣称跨版本提速百分比。

## 10. 新增规则的触发/动作/证据/失败处理

| 触发 | 动作 | 通过证据 | 失败后处理 |
|---|---|---|---|
| 证据文件与 manifest 哈希/源 dump/项目身份不一致 | 拒绝作为门禁证据 | `EVIDENCE_BINDING` 无 finding，meta 有 raw/semantic hash | 重新采集/修正 manifest；不 `touch` 文件 |
| 多候选项目/页身份不同 | 停止静默择一 | 单一身份或显式 `--file ROLE=PATH` | 分离目录，重新绑定 |
| 多候选内容不同但身份相同 | advisory 记录 | `EVIDENCE_AMBIGUOUS` 在报告列出 | 用 manifest 消歧；不要直接当 pass |
| SCH 侧或 PCB 侧无可用对象/全部被排除 | `not_comparable` | `status != not_comparable` | 补证据或缩小 ignore 范围 |
| 引脚分组不变、网名变化 | `match_with_renames` + advisory | `partition_match=true` | 核对命名意图；分组变化才阻断 |
| check summary 与 findings 矛盾 / 外层 ok=false | `pcb_check_inconsistent` / `pcb_check_envelope_failed` | `consistent=true`、`trusted=true` | 重新采集完整响应 |
| DRC total/violations/connection 矛盾 | `drc_inconsistent` | `consistent=true` 且 `ok=true` | 前台重跑并保存完整 JSON |
| lint 字段非法 | `lint_diagnostics` | `measured=true` 且无 diagnostics | 修采集/导出，不用 0 补 |
| 目标 pose 等于实测 pose | `no_op`，不写 playbook | `plan.noops` 列出 | 不重跑；需要变更就改计划 |
| apply 已发出但 journal 无确认 | `unknown` + `recovery.safe_to_retry=false` | 每步 `confirmed` | fresh dump 对账后只补差异 |
| 线宽/孔径/keepout 越界 | `outside_outline_width`/`outside_outline_diameter`/`copper_intersects_keepout` | 无 refusal | 改几何；不缩小板框 |
| 锁定/间距/edge/keepout 硬失败 | 候选 `hard_ok=false` | `hard_conflicts=[]` | 修布局/约束；不能用软指标抵消 |
| 固定种子预算内无候选 | `feasibility=not_found_within_budget` | `status=selected` | 扩预算或改结构；不宣称无解 |

## 11. 边界

离线通过不等于：真实 EDA 读写/保存重开、原生 DRC/check/lint、布线完成、铺铜连接、Gerber/CPL 可制造、热/EMC/安规、固件和实物功能。没有真机证据时保持 `NOT RUN`/`BLOCKED`，不把本轮 `simulated:true` 日志写成真实执行结果。

