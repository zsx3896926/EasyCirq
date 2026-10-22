# 第三轮任务台账（2026-10-22）

分支：`feat/cross-client-round3`（worktree `C:\Users\jlc\work\hardware-design-skill-r3`），基线 `origin/main` = `0fe5cf8`。
状态：`DONE` / `PARTIAL` / `BLOCKED` / `NOT RUN`。只记录本轮实际发生的事。

## 基线

- 开工时 `origin/main` = `0fe5cf8`，工作树干净；基线测试 141 项 `OK`。
- 本轮新增 EDA 桥可靠性/删除原语/DRC/属性回读/`doctor_env` 回归后，157 项 `OK`。
- 并发：另一个本地会话在同一仓库切换分支，并把本轮未提交的删除原语提交为 `2d6a3ea`（推到 `feat/engineering-decisions-round4`）。本轮改用独立 worktree，cherry-pick 该提交到本分支（`2474ad1`），未覆盖对方分支。
- 真实 EDA：嘉立创EDA专业版 `4.1.78.34f5b8d9`，半离线；用户自有 `test` 会话全程未操作；所有写入在 `C:\Users\jlc\work\hw-eda-round3\f1-layout.eprj2` 副本。

## 工作包状态

| 工作包 | 状态 | 实际交付/证据 | 未完成/边界 |
|---|---|---|---|
| A1 客户端能力矩阵 | PARTIAL | [client-compatibility.md](../design-hardware/references/client-compatibility.md)：Claude Code 2.1.303、Codex 0.163.0-alpha.10.2、WorkBuddy 5.8.3 的路径/格式/能力分层；本机路径与诊断见 [client-env-2026-10-22](evidence/client-env-2026-10-22/README.md) | 三客户端均未实际安装/调用 design-hardware；WorkBuddy GUI 导入未跑 |
| A2 统一环境诊断 | DONE | `design-hardware/scripts/doctor_env.py` + `tests/test_doctor_env.py`；本机实跑输出 Claude/Codex/WorkBuddy/EDA 状态 | 只诊断；不测可写性，不安装 |
| A3 环境差异 | PARTIAL | 文档覆盖 Windows 路径、PATH 刷新、cwd 差异、半离线、云端无本机 EDA | macOS/Linux 未实测；中文/空格路径未做专项回归 |
| A4 结果语义 | PARTIAL | `apply` 区分 verified/partial/failed/blocked/needs_save/apply_unknown/page_changed/save_failed；失败保留会话 | 未统一成跨客户端共享 schema；文本提示仍可能被误读 |
| B1 最短安装入口 | PARTIAL | README 与 client-compatibility 按“已有客户端”给路线；不再要求三套全装 | 未做安装包/一键脚本；未在全新机器实测 |
| B2 Skill 安装包 | PARTIAL | 目录格式在临时项目级目录实测：`doctor_env --cwd <temp>` 识别 `design-hardware/SKILL.md`；证据 [client-env](evidence/client-env-2026-10-22/README.md) | 未生成 zip/包校验清单；未做用户级实际安装 |
| B3 安装前后检查 | PARTIAL | `doctor_env` 可查“目录存在/已安装”，临时安装前后状态可复现 | 重复安装、损坏包、版本不匹配未做专项 |
| B4 连接器引导 | DONE（文档） | 明确 EDA Agent Connector 装在 EDA 内；`easyeda health` 边界 | 本机无 `easyeda`，未实跑 |
| B5 首次接通小任务 | PARTIAL | 五步清单写入 client-compatibility；EDA 读/写/保存/重开在 F1 副本真实通过 | 三客户端自身的五步未逐项执行 |
| C 需求与产品预期 | NOT RUN | 沿用上一轮内容 | 本轮没有真实多轮新手任务 |
| D 项目状态/接续 | PARTIAL | 本台账 + `docs/handoff-current.md`；工程记录沿用模板 | 未做跨客户端实际交接；未测过期记录 |
| E1 快照完整性 | DONE | 引脚读取失败置 `pins_complete:false` + `pins_missing`；类型读取失败计 `unclassified`；`apply` 拒绝在引脚不完整时写；回归测试 | 没有在真机上制造“读引脚失败”的故障注入 |
| E2 身份保留 | PARTIAL | 跨页位号、unique_id、footprint 回读沿用；create 预检同名多候选改为 `ambiguous_part`，要求 C 号 | 未自动核对 SCH-PCB 同步；换封装未实现 |
| E3 写入前条件 | DONE | `before` 成功后锁定 `page_uuid`，apply/after/save 不再重解析；after 页变化报 `page_changed`；回归测试 | 用户手改图的并发冲突仍靠 snapshot 对账 |
| E4 逐项验证 | DONE | 补 designator、mirror、add_into_bom/pcb、properties（other_property 按请求键子集）回读；回归测试 | net_flag.type / net_port.direction 仍不可读，未验证 |
| E5 超时/结果未知 | PARTIAL | 超时/异常返回 `apply_unknown`，会话 `destroy=false` 保留；先回读再重试 | 未做真实断连/超时注入 |
| E6 部分失败恢复 | PARTIAL | 结果记录 actions/execution/phase；失败不销毁会话 | 未做逐对象 landed/unknown 清单 |
| E7 保存重开 | DONE | `compare_snapshots` 增 netports；`reopen-check` 比较 project/schematic/page 身份；F1 `match` | net_flag.type 仍不比较；attributes 未纳入 |
| E8 故障注入 | NOT RUN | — | 断连、保存失败、导出失败、异步延迟未系统注入 |
| F1 原理图质量 | PARTIAL | 真实重排：[f1-relayout-2026-10-22](evidence/f1-relayout-2026-10-22/README.md)；11 网络逐脚一致、save true、reopen match、DRC 4 warn | 图面仍拥挤（J101/U101/J102）；未做 ERC 人工审查；未改电气 |
| G PCB 闭环 | NOT RUN | 只做了 API 能力探查：`DMT_Pcb.createPcb`、`PCB_Document.importChanges/autoRouting`、`PCB_Drc.check`、`PCB_ManufactureData.getGerberFile` 存在 | 本桥未实现 PCB 读写/布局/布线/DRC/制造导出；无真实板 |
| H 商城/SMT/成本 | PARTIAL | 从真实设计导出 BOM（11 行、16 件、C 号），证据 `bom.csv`/`bom-export.json` | 未查实时库存/价格/MOQ/SMT 可贴；未做替代料/完整成本 |
| I 程序/结构/首板 | NOT RUN | 仅文档中的启动/测试计划 | 无固件、无烧录、无样机、无结构 |
| J 工程知识审计 | PARTIAL | 独立审计确认：CC/上拉/按键/LED/UART 网表正确；公式脚本未发现公式/单位错误；确认 J102-1 3V3 反灌风险与“44 图元 vs 34 有效段”计数问题，已修文档；AMS1117 输出电容、ESP GPIO2 标为待核实 | 未取得 AMS1117/ESP-01S 原厂 PDF 正文；未逐条审计全部设计卡 |
| K 跨客户端评测 | NOT RUN | — | 未做同任务三客户端对比/有无 Skill 对照 |
| L 教程与传播 | PARTIAL | README 更新客户端路径/诊断命令/F1 新证据；新增 client-compatibility；readme-technical 测试计数更新 | 三套独立教程、快速开始一页版、发布兼容说明未完成 |

## 真实 EDA 证据

1. **F1 重排**：[f1-relayout-2026-10-22](evidence/f1-relayout-2026-10-22/README.md)
   - 16 器件、27 电源标记、14 网络端口、41 个导线对象（44 个归一化线段）。
   - 重排前后 11 网络逐引脚一致；save true；reopen project/page/对象 match。
   - DRC：重排前 5 warn（4 越页 + 1 悬空脚）→ 重排后 4 warn（3 ONENETNAME + 1 CHECKFLOATPIN），0 error。
   - 失败现场保留：平移碰撞导致 CC1 并入 5V、L 形多段线被重排、SW102 引脚映射写反；均由回读发现并修复。
2. **BOM 导出**：`bom.csv`（UTF-16，11 行/16 件）与 `bom-export.json`；只证明 EDA 能导出，不证明库存/价格。
3. **执行闭环（上一轮）**：[eda-2026-10-21](evidence/eda-2026-10-21/README.md)。

## 阻断/未执行

- **全在线 GUI**：CLI 会话恒半离线；全在线结论只能由用户自己的 GUI 会话复验，本轮未做。
- **PCB**：本桥未实现；API 存在不等于已验证。下一步需单独设计 PCB 计划（创建/导入变更/板框/布局/布线/DRC/Gerber）并在副本上逐项回读。
- **制造/供应链**：无实时库存/价格/MOQ/SMT；BOM 只是导出，不是可下单清单。
- **固件/样机**：无工具链、无实物；启动/测试计划未执行。
- **客户端实测**：三客户端均未实际安装并调用 design-hardware；WorkBuddy GUI 导入未跑。
- **图面**：F1 仍拥挤；未达到“工程师可直接接管”。

## 下一步（按优先级）

1. 在真实副本上完成 F1 的“功能块 + 网络标签 + 更大间距”重画，保持网表不变；再跑 DRC/整页看图。
2. 实现 PCB 最小闭环：`createPcb → importChanges → 板框/安装孔 → 布局 → autoRouting/手工布线 → PCB DRC → Gerber/BOM/坐标 → 保存重开`，每步回读；先在一块小板上验证。
3. 在三客户端各做一次“安装 → 发现 → 最小读文件 → 读 EDA → 副本最小写入”的五步实测；WorkBuddy GUI 需用户配合。
4. 用真实新手/工程师任务做 K 组评测，保留原始输入/输出/评分分歧。
5. 取 AMS1117/ESP-01S 原厂资料，关闭输出电容 ESR、GPIO2 启动脚两个待核实项；决定 J102-1 是否改 3 针/ORing。
6. 补故障注入：断连、保存失败、导出失败、异步延迟、页面切换。

## 证据与版本

- 分支 `feat/cross-client-round3`；删除原语提交 `2474ad1`（cherry-pick 自并发会话的 `2d6a3ea`）。
- 本台账随代码提交；证据路径均为仓库相对路径。
- 未提交：`f1-layout.eprj2` 副本、`C:\Users\jlc\work\hw-eda-round3\` 下的临时计划/导出（仅证据副本入库）。
