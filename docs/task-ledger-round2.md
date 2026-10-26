# 第二轮任务台账（2026-10-21/22）

分支：`feat/eda-schematic-quality`，基线 `origin/main` = `68331c4`。
状态标记：`DONE` 已交付并有证据 / `PARTIAL` 部分完成 / `NOT RUN` 未执行 / `BLOCKED` 环境阻断。

## 开工基线

- 新建分支前工作区干净；未把其他人的分支修改带入。
- 基线测试：108 tests，`OK`。
- 最终测试：138 tests，`OK`（新增 EDA 桥、8 类基准、几何检查扩展等回归）。
- 真实 EDA：嘉立创EDA专业版 `4.1.78.34f5b8d9`，`lceda-pro doctor` = `connected:true`、`versionMatch:true`；CLI 自建 headless 会话；**半离线**（`online:false, half_offline:true`）。
- 会话安全：未操作用户的 `test` 会话；所有写入在独立副本 `<scratch>/base-copy.eprj2`。副本不提交。

## 任务状态

| 任务 | 状态 | 实际交付/证据 | 未完成/边界 |
|---|---|---|---|
| A1 执行能力发现与诊断 | DONE | `scripts/eda_exec.py doctor`；区分 CLI存在/连通/工程可读/可写；`docs/evidence/eda-2026-10-21/doctor.json` | 可写性默认 `not_tested`，需在副本上 `apply` 验证 |
| A2 意图到动作映射 | DONE | [eda-execution.md](../design-hardware/references/eda-execution.md) 能力矩阵；官方 `doc api` 实测；器件/属性/导线/端口/保存/导出/DRC/PCB边界 | PCB未实现；网络标签未做幂等写入；不覆盖其他执行Skill |
| A3 中断恢复与重复执行 | DONE | 先读快照→对账→只补差异；超时先回读；线按“网名+线段覆盖”对账；跨网重叠冲突；回归 `tests/test_eda_exec.py` | 没有真实故障注入矩阵；用户手改图的中断场景只做方法约定 |
| A4 对象身份与局部修改 | DONE | `primitive_id/unique_id/designator/component/supplier/footprint` 回读；局部只改计划对象；跨页位号冲突实测并改用100系列 | 换封装/换料自动核查未实现；锁定/机械约束未纳入桥 |
| A5 保存、重开与交付核验 | DONE | `EvidenceDemo`：save true→close→reopen `match`；F1：16器件/93动作 verified→save true→reopen `match` | 半离线；未做全在线GUI复验；未做PCB保存/重开 |
| B1 原理图排版基准集 | DONE | `assets/schematic-benchmarks/benchmarks.json`（8类）；`scripts/schematic_benchmark.py` 8/8；测试 `tests/test_schematic_benchmarks.py` | 离线故意有缺陷快照，不是8张真机图 |
| B2 模块内部几何设计 | DONE（方法+真机案例） | [schematic-layout.md](../design-hardware/references/schematic-layout.md) 增“按引脚不按外框”；真实E2E从3000,3000越框改为页面内；F1按真实引脚放置 | 多单元/隐藏电源脚只写方法，未用真实多单元器件验证 |
| B3 页面组合与阅读顺序 | PARTIAL | 分块/阅读顺序/图幅/图签/跨页规则；多模块基准B8 | 没有真实多页工程；没有实际分页/图框尺寸切换验收 |
| B4 连线与标签边界 | DONE | 正反例表；真机验证网络端口按名合并；实测多段线被编辑器合并/重排的坑并改为单段+端口 | 总线/差分作用域只写规则，未真机验证 |
| B5 图面检查与修复循环 | DONE | `sch_layout_check.py` 新增标题栏/模块框/悬空端点/一脚多网/标签落点；`offline-tools.md` 更新；回归通过 | F1图面仍拥挤；几何检查不判电气/可读性 |
| C1–C5 PCB | NOT RUN | 未进入PCB；F1只给候选约束 | 无板框/布局/布线/铜区/DRC/制造复验 |
| D1–D5 嘉立创业务 | NOT RUN | 保留原有生产规则与来源快照，本轮未改 | 未重查实时库存/价格/工艺；未下单 |
| E1–E5 新手/工程师行为 | NOT RUN | 保留原有12+场景与路由；本轮未做真实Agent对话试验 | 不能用目录/关键词检查冒充行为试验 |
| F1 USB 供电 MCU 小板 | PARTIAL | 真实EDA原理图 `F1-USB-MCU-C`：16器件/27电源标记/16端口/44导线；网表核对；证据 [f1-2026-10-22](../docs/evidence/f1-2026-10-22/README.md) | 图面拥挤；DRC/ERC、PCB、制造、样机、固件 NOT RUN；电气边界未验证 |
| F2–F5 | NOT RUN | 未开始 | 需按F1经验逐步扩展 |
| G1–G5 | NOT RUN | 未新增跨模块反例、公差审计、测试点/结构/固件一致性 | 不冒充完成 |
| H1–H5 | PARTIAL | H4证据约定落实（版本/输入/输出/SHA256/日期）；H2新增实质回归；H3按需路由更新 | H1关键资料抽样审计、H5独立集成复核未做完整 |

## 真实 EDA 证据

1. **执行闭环证据**：[eda-2026-10-21](../docs/evidence/eda-2026-10-21/README.md)
   - `EvidenceDemo` 两器件串联页；读→对账→写→回读→保存→关闭重开→导图/网表。
   - 关键发现：`openDocument` 不等于激活；导出跟随活动文档；错误激活会导出旧页/工程级网表；跨页位号 R1/LED1 冲突。
2. **F1 原理图证据**：[f1-2026-10-22](../docs/evidence/f1-2026-10-22/README.md)
   - 16 个真实库器件、5V/3V3/GND、CC、EN/RST/IO0、TXD/RXD、LED。
   - Protel 网表核对物理脚；`save:true`；`reopen-check:match`。
   - 图面拥挤、未做DRC/PCB/制造/样机，已在项目文档中标明。

## 仍阻断/需实物验证

- **全在线模式**：CLI 会话恒半离线；全在线结论只能由用户 GUI 会话复验，本轮未做。
- **PCB**：本机未进入 PCB 读写/布局/布线；所有 PCB 约束仅为候选。
- **制造/供应链**：无实时库存/价格/工艺核对，无 Gerber/BOM/坐标/DFM/打样/SMT。
- **样机/固件**：无实物、无烧录、无 Wi-Fi/UART/热/EMC/安规实测。
- **图面**：F1 连接正确但排版未达工程师级；下一轮先重排 J101/J102/U101 三处并保持网表不变。

## 下一步（少量、按优先级）

1. F1 图面重排 + 原理图DRC/ERC；重排前后网表比对。
2. 核对 AMS1117/ESP-01S/Type-C/按键原厂关键参数；把 LDO 热/峰值电流/ESD 从 `待确认` 变成有条件计算或实测计划。
3. 用一个真实多页工程验证 B3 的跨页/图框/阅读顺序，而不是只靠基准。
4. 进入 PCB：板框/接口/安装孔/天线净空→电源回路/去耦→DRC/制造输出；单独报告 PCB 证据。
5. 做一批真实新手/工程师 Agent 对话试验（E5），保存输入、输出、判据与结果。
