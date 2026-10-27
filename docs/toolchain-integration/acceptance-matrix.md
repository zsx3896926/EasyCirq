# 验收矩阵（Acceptance matrix）— M2 / M3 / M4

> 本文件逐项列出任务书要求的能力：**实现状态 / 离线测试 / 真实宿主测试 / 客户端测试 / 证据路径 / 限制**。
> 状态只用 `PASS` / `FAIL` / `NOT RUN` / `BLOCKED`。
>
> **核心事实（2026-10-27）**：自有 `zhigou 0.2.0-dev` 运行时与隔离 daemon 已就绪；
> 自有连接器 `.eext` 尚未在 EasyEDA Pro 内人工导入，`connector.status=disconnected`。
> 因此**所有依赖宿主的真机项一律 `BLOCKED`，不是 `PASS`**；未执行的步骤写 `NOT RUN`，不写"通过"。
>
> - 生成依据：`zhigou doctor` / `zhigou capabilities` / `zhigou connector verify|path` / `zhigou health`（真实执行，只读）
> - 机器可读证据：`evidence/acceptance/summary-blocked-dryrun.json`（`schema=zhigou-acceptance/v1`，退出码 2）
> - 状态语义：`PASS`=该列所述范围已证；`FAIL`=已观察到违反/未实现；`NOT RUN`=尚未执行（含无通道）；`BLOCKED`=环境前置未满足（此处唯一原因：连接器未导入）
> - 缺连接器时能力协商为 `0 supported / 19 unknown / 5 unsupported`（`evidence/acceptance/preflight/capabilities.json`）

## A. 构建、运行时与诊断

| 编号 | 能力项 | 实现状态 | 离线测试 | 真实宿主测试 | 客户端测试 | 证据路径 | 限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | 自有 runtime 构建（`zhigou.exe` 0.2.0-dev） | PASS — 二进制与版本可读 | PASS — 本机构建，`zhigou version` 实跑 | NOT RUN — 构建不涉及宿主 | NOT RUN — 未做客户端注入 | `evidence/m1/doctor.json`、`evidence/m1/version.txt`、`evidence/acceptance/preflight/*.json` | 工作区 `vcsModified=true`，是 dev 构建，不是发布签名产物 |
| A2 | 运行时全量 `go test` | FAIL — 3 个包失败 | FAIL — `app`/`daemon`/`selfupdate` 三包失败，≥20 个用例 | NOT RUN | NOT RUN | `evidence/runtime-go-test.log`（2026-10-27 21:36 记录） | 失败含重命名/资产路径/update 命令断言；**不得当作 M1 通过**，需 owner 重跑与修复 |
| A3 | daemon 隔离启动（23111–23120、`~/.zhigou`） | PASS | PASS — 端口/进程/pid 文件可核对 | PASS — 本机实测监听，与旧 daemon 并存互不影响 | NOT RUN | `evidence/m1/listening-ports.json`、`daemon-processes.json`、`doctor.json` | 仅 loopback；旧 daemon 仍监听 60832（`legacy.used=false`） |
| A4 | `zhigou doctor` 统一诊断 | PASS | PASS — 单测存在，无连接器路径实跑 | PASS — `verdict=degraded`、四段检查输出 | NOT RUN | `evidence/m1/doctor.json`、`evidence/m1/doctor.stderr.txt`、`evidence/acceptance/preflight/doctor.json` | 连接器已连分支未真机验证 |
| A5 | `zhigou capabilities` 能力协商 | PASS | PASS — 实跑，逐项 reason | PASS — 无连接器时 19 unknown / 5 unsupported | NOT RUN | `evidence/m1/capabilities.json`、`evidence/acceptance/preflight/capabilities.json` | 仅在 connected 后才可能变 supported；不按 EDA 版本推断 |
| A6 | `zhigou connector path/verify` 与 `.eext` 构建 | PASS | PASS — 包结构/大小/sha256 可核对 | NOT RUN — 导入是 EDA 内人工动作，CLI 无法代做 | NOT RUN | `evidence/m1/connector-path.json`、`evidence/m1/connector-verify.json`、`evidence/acceptance/preflight/connector-path.json` | `.eext` 仅在 EDA 启动时从 IndexedDB 加载，无 CLI 安装通道 |
| A7 | 连接器 ↔ daemon 握手（protocol v1） | PASS — 协议常量/schema 已落盘 | NOT RUN — 无宿主可握手 | BLOCKED — 连接器未导入 | NOT RUN | `evidence/m1/connector-verify.json`、`evidence/acceptance/preflight/connector-verify.json`、`protocol/` | 解锁需：导入 `.eext` + 允许外部交互 + 重启 EDA（见 `task-status.md` §4） |
| A8 | 技能迁移为 zhigou 单入口（`design-hardware`） | PASS — doctor 报 design-hardware 1.0.1 | PASS — doctor skill 段 | NOT RUN — 未在客户端会话中加载验证 | NOT RUN | `evidence/m1/doctor.json`（`skill.installed`）、`evidence/skill-migration/` | `zhigou-agent` 技能目录不存在；SKILL.md 仍有旧称谓（见 §F） |

## B. 原理图（SCH）

| 编号 | 能力项 | 实现状态 | 离线测试 | 真实宿主测试 | 客户端测试 | 证据路径 | 限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 原理图读取（`sch read/list/connectivity/nets`） | PASS — 15 个 typed action | NOT RUN — 需宿主；仅 action 目录可离线枚举 | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`evidence/m1/capabilities.json` | 后台页返回浅数据；pin→net 以官方网表为准 |
| B2 | 原理图写入（`sch place/modify/connect/netflag/no-connect`） | PASS — 26 个写 action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json` | 写后必须新鲜回读；部分属性 patch 可能部分成功并非零退出 |
| B3 | 原理图检查（`sch drc/check/layout-lint/gate`） | PASS — 2 个 check action + 4 个 CLI 检查 | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`evidence/acceptance/cli-help/sch-*.txt` | 官方 DRC 可能只返回布尔/聚合；`sch check` 是重建式明细，不等于 UI DRC 全表 |
| B4 | 保存 → 真实重开 → 回读（`sch save` + `doc reload` + `doc ready`） | PASS — 命令面齐备 | NOT RUN | BLOCKED | NOT RUN | `evidence/acceptance/m2-blocked-dryrun.stderr.log`、`cli-help/sch-save.txt`、`cli-help/doc-reload.txt` | `saved:true` 只证明保存调用成功，持久化必须重开回读；`doc ready` 不证明 reload 成功 |
| B5 | 原理图批量/compose/block-apply（离线几何 → 守卫写入） | PASS — 181 action 中 41 个 schematic | NOT RUN — 需 skill 资产与宿主 | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`evidence/m1/capabilities.json` | 依赖 `references/standard-parts.json` 等资产；资产缺失则 block-apply 不可用 |
| B6 | 原理图导出（netlist / BOM / image） | PASS — 3 个 export action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`evidence/acceptance/cli-help/bom-export.txt` | BOM 富化依赖标准件表；图像导出对后台标签页仍以官方渲染为准 |

## C. PCB

| 编号 | 能力项 | 实现状态 | 离线测试 | 真实宿主测试 | 客户端测试 | 证据路径 | 限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | PCB 读取（`pcb dump/list/layers/nets/outline`） | PASS — 27 个读 action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`evidence/acceptance/cli-help/pcb-dump.txt` | 单位 mil、y-up；`x/y` 是 anchor，规划用 bbox `center` |
| C2 | PCB 写入（`pcb modify/place/track/via/delete`） | PASS — 58 个写 action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json` | 无编程 undo；改前重取 primitiveId；`delete` 布尔不代表已删 |
| C3 | PCB 布线（受控原语 + 求解器入口） | PASS — 5 个 route action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`evidence/m1/capabilities.json` | **官方自动布线器是否存在需真机探测**（`pcb.route` unknown）；不得把受控原语当自动布线 |
| C4 | PCB 铺铜（pour-fit / power-pour / pour-rebuild） | PASS — 5 个 pour action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json` | 重建铺铜改全板铜；铺铜后必须 `pour-rebuild` + 回读 + DRC |
| C5 | PCB DRC（`pcb drc`） | PASS — 3 个 drc action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`cli-help/pcb-drc.txt` | DRC 必须绑定当前快照；`--timeout` 默认 60s；旧 DRC 不能证明新修改 |
| C6 | PCB DFM 检查（`pcb check`） | PASS — 重建式 DFM 审计 | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/actions.json`、`cli-help/pcb-check.txt` | 只对已放铜/器件成立；`--strict` 才作为门禁 |

## D. 导出、归档、局部修改与保护

| 编号 | 能力项 | 实现状态 | 离线测试 | 真实宿主测试 | 客户端测试 | 证据路径 | 限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | BOM 导出（`bom export --type csv / xlsx`） | PASS | NOT RUN | BLOCKED | NOT RUN | `evidence/acceptance/cli-help/bom-export.txt` | 无 `--out`：产物路径以回执为准；富化 best-effort |
| D2 | 图像导出（`sch export-image` / PCB 快照渲染） | PASS | NOT RUN | BLOCKED | NOT RUN | `cli-help/sch-export-image.txt` | 后台标签页可能不重绘；以官方渲染而非截图证据 |
| D3 | Gerber 导出 | FAIL — 运行时无 typed action | NOT RUN — 无实现可测 | NOT RUN — 不是环境阻塞，是能力缺失 | NOT RUN | `evidence/m1/capabilities.json`（`gerber.export=unsupported`） | 只能 EDA GUI 人工导出 + 人工证据；G6 缺人工证据时仍 BLOCKED |
| D4 | 钻孔导出 | FAIL — 无 typed action | NOT RUN | NOT RUN | NOT RUN | 同上（`drill.export=unsupported`） | 同上 |
| D5 | CPL（贴装坐标）导出 | FAIL — 无 typed action | NOT RUN | NOT RUN | NOT RUN | 同上（`cpl.export=unsupported`） | 同上；SMT 坐标必须与 BOM 同版人工核对 |
| D6 | 原生归档（`project export --out`） | PASS — 2 个 export action | NOT RUN | BLOCKED | NOT RUN | `evidence/m1/capabilities.json`、`cli-help/project-export.txt` | 拒绝覆盖已有文件；导出前先保存文档 |
| D7 | 恢复演练（`project import` @beta，导入为**新**工程） | PASS — 代码路径在 | NOT RUN | BLOCKED | NOT RUN | `cli-help/project.txt`、`evidence/m1/actions.json` | 只能新建工程，不能在原工程上"还原"；不得宣称已恢复 |
| D8 | 局部修改 + 范围外差异（M4：2 mm 上移 → 保存 → 重开 → fresh dump → scope diff） | PASS — `tools/zhigou_acceptance.py` 已实现 before/after 差分 | PASS — `--self-test` 覆盖 target-only/他件移动/铜变化三类判定，12/12 | BLOCKED | NOT RUN | `evidence/acceptance/self-test.json`、`evidence/acceptance/summary-blocked-dryrun.json` | 差分依赖真实 dump 字段；dump schema 未在真机验证前只作候选证据 |
| D9 | 错目标 / 过期 / 超时保护（`--doc` 钉页、`staleRisk`、有界 timeout） | PASS — CLI 提供 `--doc`/`--force-stale-read`/`--timeout` | NOT RUN — 需真机触发 | BLOCKED | NOT RUN | `cli-help/top.txt`、`cli-help/doc-ready.txt`、`cli-help/pcb-drc.txt`、`evidence/acceptance/m2-blocked-dryrun.stderr.log` | `staleRisk` 只诊断；`--doc` 拒绝错页但需宿主才可验证 |
| D10 | 安装 / 升级 / 回退 | PASS — `distribution/` 生命周期测试 | PASS — `pytest` 39 passed；生命周期日志含 install/upgrade | NOT RUN — 仅在临时目录演练，`real_bundle_install` verdict=`degraded` | NOT RUN | `evidence/installer/pytest-install-lifecycle.log`、`evidence/installer/install-lifecycle.log` | `degraded` 的含义与可接受性由安装器 owner 说明；本矩阵不判通过 |
| D11 | 验收脚本自身（`--self-test` / `--dry-run` / BLOCKED 退出码） | PASS | PASS — self-test 12/12；dry-run 真实执行 preflight 后退出 2 | NOT RUN — 脚本不直接连 daemon | NOT RUN | `evidence/acceptance/self-test.json`、`summary-blocked-dryrun.json`、`blocked-dryrun.stderr.log` | 依赖 CLI `--json`/退出码契约；CLI 改名或字段漂移需同步 |

## E. 状态计数

| 状态 | 次数 | 占全部状态单元 |
| --- | ---: | ---: |
| `PASS` | 39 | 31.5% |
| `FAIL` | 5 | 4.0% |
| `NOT RUN` | 61 | 49.2% |
| `BLOCKED` | 19 | 15.3% |
| **合计** | **124** | 100% |

统计范围：A–D 共 **31** 个能力项 × 4 列（实现/离线/真机/客户端）= **124** 个状态单元；`UNPARSED=0`。

| 分组 | PASS | FAIL | NOT RUN | BLOCKED |
| --- | ---: | ---: | ---: | ---: |
| A | 16 | 2 | 13 | 1 |
| B | 6 | 0 | 12 | 6 |
| C | 6 | 0 | 12 | 6 |
| D | 11 | 3 | 24 | 6 |

## F. 与 `design-hardware/SKILL.md` 的映射与缺口（本矩阵视角）

| 项 | 现状 | 缺口/冲突 |
| --- | --- | --- |
| 阶段映射 | SKILL 用 G0–G6 + S0–S5；本矩阵用 M2/M3/M4 | 缺一张显式映射：M2 ≈ G2/S3（原理图证据门）、M3 ≈ G5/G6 的导出与检查面、M4 ≈ G3/G5 的局部改板与重开证据。**建议**：`SKILL.md` 阶段门禁引用本矩阵的 M 阶段证据文件名，或反之；当前两套编号并行 |
| Gerber/钻孔/CPL | SKILL.md L234 写"在 `zhigou-agent v1.14.0` 没有 CLI/typed action" | **版本身份错误**：现实是 `zhigou 0.2.0-dev`，不存在 `zhigou-agent v1.14.0`；应改为"`zhigou capabilities` 报 `gerber/drill/cpl.export=unsupported`，只能 GUI 人工导出" |
| 执行器称谓 | SKILL.md L15/L108/L114 仍称"`zhigou-agent` 的 Skill / 使用 zhigou-agent 时读取其 Skill" | 架构是**单一技能**（`design-hardware`），`~/.codex、~/.claude、~/.agents/skills/zhigou-agent` 均不存在；"读取其 Skill"已无对象，且 runtime 不自我更新技能 |
| 升级语义 | SKILL.md L15 把"本 Skill 与 `zhigou-agent` 的 CLI/Skill/daemon/Connector"一起检查 | 与 runtime 现状不符：runtime 的 `skill sync`/`update` 已不再安装技能（`--auto-update-skill` 默认关）；升级由 `distribution/` 负责。`scripts/skill_update.py` 仍保留 `update-agent` 与 `--easyeda` 隐藏别名 |
| 验收口径 | SKILL 要求"未回读不写通过"，本矩阵 M2 six-state 正是其落地 | 缺"六态"命名与 SKILL 用语映射；建议 SKILL 引用 `tools/zhigou_acceptance.py` 的六态字段名 |
| 真机阻塞传播 | SKILL G6 要求制造证据 | 连接器未导入时，G2–G6 的宿主依赖项应显示 `BLOCKED` 而非"待确认"，否则用户会误以为可以直接开画 |

## G. 证据索引

| 证据 | 路径 |
| --- | --- |
| M1 运行与诊断 | `evidence/m1/doctor.json`、`capabilities.json`、`connector-path.json`、`connector-verify.json`、`health.json`、`listening-ports.json`、`daemon-processes.json`、`version.txt` |
| 运行时回归（**FAIL**） | `evidence/runtime-go-test.log` |
| vendoring 一致性（PASS） | `evidence/m1/vendor-verify.txt` |
| 安装/升级/回退 | `evidence/installer/install-lifecycle.log`、`evidence/installer/pytest-install-lifecycle.log` |
| 验收脚本与阻塞证据 | `evidence/acceptance/README.md`、`self-test.json`、`summary-blocked-dryrun.json`、`summary-m2-blocked-dryrun.json`、`blocked-dryrun.stderr.log`、`preflight/`、`cli-help/` |
| 环境基线 | `evidence/env/`、`environment-baseline.md` |

## H. 解锁与刷新

1. 用户在 EasyEDA Pro 内导入 `zhigou connector path` 输出的 `.eext`，允许外部交互，重启 EDA（一次性人工动作）。
2. `zhigou doctor` 应显示 `connector.status=connected`、`connectorVersion=0.1.0`；否则脚本继续退出 2。
3. 按顺序执行并回填本矩阵：

```powershell
python tools/zhigou_acceptance.py --stage m2 --project-dir <设计工作区> --evidence-dir docs/toolchain-integration/evidence/acceptance --json
python tools/zhigou_acceptance.py --stage m3 --project-dir <设计工作区> --evidence-dir docs/toolchain-integration/evidence/acceptance --json
python tools/zhigou_acceptance.py --stage m4 --m4-device R1 --project-dir <设计工作区> --evidence-dir docs/toolchain-integration/evidence/acceptance --json
```

每次运行都会覆盖 `summary.json` 并追加 `commands.jsonl`；矩阵中的 `BLOCKED` 只在对应 `summary-*.json` 出现 `PASS` 且六态齐备后才可改为 `PASS`。

## 6. 小板真机进展（Lead 补记 2026-10-27 23:20）

独立工程 `zhigou-integrated-dual-button-led-20261027`（Board1 = Schematic1 + PCB1）：

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 原理图 9 器件、2 通道（按键→限流电阻→LED→GND，5V 经 PTC + 100nF 去耦） | PASS | `evidence/m4/summary.json` |
| 7 个网络逐脚一致 / 0 浮空引脚 / 保存确认 | PASS | `evidence/m4/schematic-verify.json` |
| 原生原理图 DRC | PASS（0 违规） | `evidence/m4/sch-drc.json` |
| 图签必填项 | PASS（已写入 Name/Drawed/Description） | `evidence/m4/titleblock-set.json` |
| BOM / SVG / PNG 官方导出 | PASS（文件非空：CSV 1 KB、SVG 90.6 KB、PNG 458 KB） | `evidence/m4/bom-export.json`、`sch-image-*.json` |
| SCH→PCB 同步 | PASS（imported+verified，9 footprint），但 handler 边界身份不可认证 + staleRisk → 已 save→reload→新鲜 dump 后回读 | `evidence/m4/pcb-import-changes.json`、`pcb-dump.json` |
| PCB 布局 | **PASS**：layout-lint 100/100（0 short/0 overlap/0 tight） | `evidence/m4/pcb/pcb-layout-lint2.json` |
| 板框 | **PASS**：outline-fit margin 100 mil → 1883×802 mil | `evidence/m4/pcb/outline-after.json` |
| 布线（官方路由器） | **PASS**：6/6 网、36 track、0 via、987 ms | `evidence/m4/pcb/pcb-autoroute.json` |
| GND 铺铜（双层） | **PASS**：TOP+BOTTOM GND pour，verified | `evidence/m4/pcb/pour-*.json` |
| PCB DRC（新鲜回读） | **PASS：0 违规**（改板与 DFM 修复后复跑仍 0） | `evidence/m4/pcb/pcb-drc-poured.json`、`pcb-drc-dfm.json` |
| DFM 检查 | 0 error / **5 warning**（J1 丝印旋转、+5V/VIN 未铺、2 条电源线偏细） | `evidence/m4/pcb/pcb-check.json` |
| 局部改板 D1 +2mm | **PASS**：仅 D1 pose 变化，范围外变化 0；断线→重布线→重铺铜→DRC 0 违规 | `evidence/m4/pcb/local-edit-summary.json`、`edit-drc-3.json` |
| 原生归档导出（.epro2） | **PASS**：46,838 B，zip 3 entries，CRC OK | `evidence/m4/pcb/project-export.json` |
| PCB 截图 | **BLOCKED**：两次尝试（含窗口激活）后 EDA 标签页仍 hidden，工具拒绝截过期画布（PRECONDITION_REFUSED）；需用户手动把 PCB 标签页切前台 | `evidence/m4/pcb/pcb-snapshot.json`、`pcb-snapshot2.json` |
| 恢复演练（导入 .epro2 到新工程） | **PASS**：新工程读回 7 网一致 / 9 footprint pose 一致 / 板框一致 / DRC 0 违规 | `evidence/m4/restore/restore-summary.json` |
| PCB 3D 导出 | **NOT RUN** | — |
| Gerber/钻孔/CPL | **gui_only**（无 typed action），未尝试未宣称 | `evidence/m1/capabilities.json` |
| 功能分区框 | **未画**（`sch check` WARN missing-partition） | `evidence/m4/sch-check.json` |
| 局部改板 2mm / 原生归档恢复演练 | **NOT RUN** | — |
