# 上游 Skill 副本比对：源码克隆 vs 已安装（只读）

目的：确认"正在被客户端加载的上游 Skill"与"审计所依据的源码克隆"是否同一版本，避免用旧条文做冲突判定。

## 1. 三个目录

| 角色 | 路径 | 判定依据 |
|---|---|---|
| 源码克隆（审计基线） | `C:\Users\jlc\work\_round6-scratch\easyeda-agent-src\.agents\skills\easyeda-agent` | 无 `.version`；`SKILL.md` frontmatter `version: "1.14.0"` |
| 已安装（Codex） | `C:\Users\jlc\.codex\skills\easyeda-agent` | `.version`=`1.15.0`；frontmatter `version: "1.15.0"` |
| 已安装（Claude） | `C:\Users\jlc\.claude\skills\easyeda-agent` | `.version`=`1.15.0`；与 Codex 副本逐文件一致 |

## 2. 版本与哈希

| 项 | 源码克隆 | .codex / .claude |
|---|---|---|
| `SKILL.md` 行 / 字节 | 74 / 6357 | 74 / 6583 |
| `SKILL.md` SHA256 | `70510AE0D89CB562A90CB775C7BB9C1A0B0BE5D0C684139F7D1A36237D519764` | `39894D33755666952AB67E8A0F95F62F8D6914C789082BA2F07E40CBDB713D42` |
| 文件数 | 189 | 193 |
| 两个安装副本是否一致 | — | **是**：全文件 (sha256+相对路径) 聚合 SHA256 均为 `15AE1F60AF68D76E85F9813A4655540173B33FCC71232ED0084600301B213C75` |

## 3. 差异统计（源码 vs .codex）

- **仅源码有**：无。
- **仅已安装有**（4 项）：`.version`、`references\exam-pcb-workflow.md`、`references\examples\esp32s3r8-crystal\README.md`、`references\examples\teardrop-maintenance\README.md`。
- **逐字节相同**：0（源码为 LF，安装副本多数文件换行不同）。
- **仅换行不同、文本内容相同**：158 个文件。
- **文本内容确有差异**：12 个文件——
  `SKILL.md`、`references\actions.md`、`design-flow.md`、`environment-setup.md`、`pcb-config.md`、`pcb-layout.md`、`pcb-layout-conventions.md`、`pcb-routing.md`、`pcb.md`、`schematic.md`、`library-authoring.md`、`examples\index.md`。
  其中体量变化最大：`pcb.md` 36621→43749（+7128）、`pcb-layout.md` 73719→76509（+2790）、`design-flow.md` 14094→16685（+2591）、`actions.md` 32964→35445（+2481）。

## 4. 结论

1. **已安装副本 ≠ 源码克隆**：安装的是 v1.15.0 发布内容，源码克隆是 v1.14.0 开发快照；不能把源码克隆的条文当成"客户端此刻加载的条文"。
2. `SKILL.md` 层面差异只有 3 处（version 字符串 + 2 行任务索引），**规则条文本身未变**；真正的内容差异集中在 `references/pcb*.md`、`design-flow.md`、`actions.md` 等执行细节——因此本审计中**凡是"上游规则"都按已安装 v1.15.0 引用，并同时标注源码克隆行号**（两者行号在 SKILL.md 上一致，74 行）。
3. 用户当前环境里**两份上游 Skill 内容重复**（`~/.codex` 与 `~/.claude` 各一份 v1.15.0），加上我方 `design-hardware`（`~/.agents/skills/design-hardware` v1.0.1，与 worktree 逐行一致），本会话的可用技能清单里 **`design-hardware` 与 `easyeda-agent` 同时出现**——这正是"两套技能同时加载"的现场证据（见主报告 C01）。
4. 未运行任何 EDA 命令、未修改任何安装目录；本比对全部为 `Get-FileHash` / `Compare-Object` / 字节读取。
