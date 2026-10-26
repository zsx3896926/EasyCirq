# 第五轮发布说明（2026-10-23）

> 历史记录：本文的 574 tests 与验证范围是第五轮当时快照，不代表当前 main。当前测试数、
> 能力与边界见 `README.md`、`docs/readme-technical.md` 与 `docs/handoff-current.md`。

分支：`feat/round5-release-acceptance`。状态真源：`docs/task-ledger-round5.md`。

## 本轮新增实现

- **原理图执行器**：`text` / `text_modify` 操作；文本图元持久化矩阵实测（create 持久，delete/modify 仅内存）。
- **PCB 执行器**：`pcb doctor/read/apply/save/drc/export/reopen-check` + `pcb import/layout/route/outline`；
  线/过孔/铜区边框/器件（flat ref、search）真机验证。
- **固件骨架**：`firmware/f1-esp01s/`（ESP8266 ESP-01S 引脚表、最小固件、烧录命令、12 项上电检查表）。
- **知识库**：C40（35+j0）跨文件修正；场景库 35→47。
- **Skill 安装**：三客户端用户级目录各装一份（329 文件），Claude Code 发现已验证。

## 本轮实际验证（可复核）

| 项 | 结果 | 证据 |
|---|---|---|
| 全量测试 | 574 OK | `python -m unittest discover -s tests` |
| F1 原理图（v5） | DRC 1 warn（CHECKFLOATPIN 保留），网表 SHA256 = golden `709B505F…`，重开 match | `docs/evidence/f1-b-2026-10-22/` |
| PCB 执行器（半离线 CLI） | 读→写（线/过孔/铜区边框/器件）→回读→保存→重开 match | `docs/evidence/pcb-e2-2026-10-22/` |
| PCB 布局/布线 | autoLayout 33/33；autoRouting 13–16/17（失败网络列出）；保存后重开一致 | `docs/evidence/f1-pcb-f-2026-10-23/` |
| 故障注入 | 超时→partial_unknown；复跑→no_changes；错误身份→blocked | `docs/evidence/i-2026-10-23/` |
| 选料 | 10µF：C15850（主）/C84416/C386085；USB-C：C2843967（主）/C2988369；库存/价格带 2026-10-23 时间戳 | `docs/evidence/f1-g-2026-10-23/` |
| 知识库 | C40/C76 关闭记录 | `docs/evidence/k-2026-10-23/` |

## 已确认的客户端限制（半离线 CLI，4.1.78）

- 原理图→PCB 导入：`importChanges` 返回 true 但 0 物化 → 需 GUI。
- 板框：`pcb_PrimitiveLine.create` 拒绝 layer 11 → 需 GUI。
- DRC：`pcb_Drc.check` 返回 boolean，无错误明细。
- 制造导出：`getGerberFile` 等全部返回空对象 → 需 GUI 全在线会话。
- 文本图元：delete/modify 不持久（仅 create 持久）。
- 零长度退化导线承载端口—引脚连接，删除会断网（60→50 pins）。

## 未执行 / 阻塞

- F1 实际 PCB 与制造包：BLOCKED（GUI 导入+板框）。
- 实时 SMT 可贴性、DC bias 降额：NOT RUN。
- 固件构建：BLOCKED（公司网络无法拉取 PlatformIO 平台，20 分钟 0.2MB）。
- Codex/WorkBuddy 技能发现：待 GUI；WorkBuddy 登录 BLOCKED。
- 人工审图、首板实测、Agent 行为评测结论（见下）：按证据文件状态。

## L：Agent 行为评测（首轮）

首轮（自由访问）Skill 胜 2/6、基线胜 4/6，但基线也读了 SKILL.md，方法学受污染。
校正基线（禁止读文件）下 **Skill 胜 5/6**，差异来自仓库依据（UUID/网表/料号）与提问聚焦。
唯一基线胜场 s2 暴露「未问传感器供电/比率输出」的真实缺口，已在 p01-ldo 卡片补入
必问项并复测胜出（5/5/5/5 vs 4/3/3/4）。局限：12 场景只做 6 个。
全部回答与评分见 `docs/evidence/l-2026-10-23/`。

## 升级影响

- 新增 `pcb` 命令族与 `text`/`text_modify` 操作；旧计划文件不受影响。
- `docs/evidence/` 新增本轮全部证据；历史证据未改动。
- 安装方式：将 `design-hardware/` 整目录复制到客户端技能目录（见 README）。

## 已知限制

- 本轮 PCB 演示跑在工程内旧板（非 F1）；F1 PCB 尚未生成。
- 所有半离线结论不代表全在线验收。
- C101/C106/J101 换料后须重跑 BOM/CPL/DRC 并核对工程内焊盘表。
