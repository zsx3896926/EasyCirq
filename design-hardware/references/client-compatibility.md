# 客户端兼容与首次接通

本文件只记录**当前能核实的事实**。客户端版本、目录和菜单会变化，安装前以本机实际界面/官方文档为准。标记：

- **L**：本机实测（LOCALLY VERIFIED）
- **D**：官方文档/版本源码（DOCUMENTED）
- **I**：推断，尚未实测（INFERRED）
- **U**：未知（UNKNOWN）

## 1. 先诊断，不先安装

在 Skill 目录运行：

```bash
python scripts/doctor_env.py --summary
python scripts/doctor_env.py --summary --project /path/to/authorized-copy.eprj2
python scripts/doctor_env.py            # JSON，便于 Agent 读取
```

它检查：当前工作目录、已安装客户端、各客户端技能目录、`design-hardware` 是否已安装、`lceda-pro`/`easyeda` 是否存在、EDA 是否连通、授权副本是否可读。

它**不测试可写性**。工程能打开不等于能写；写入必须在授权副本上用 `eda_exec.py apply --dry-run` 和一次可回滚 `apply` 验证。

## 2. 能力矩阵（2026-10-22 本机）

| 客户端 | 版本 | 用户技能目录 | 项目技能目录 | 安装格式 | 本机状态 |
|---|---|---|---|---|---|
| Claude Code | 2.1.303 (D/L) | `~/.claude/skills/` | `<repo>/.claude/skills/` | `<name>/SKILL.md` + 相对引用目录 | 已安装客户端；**未安装** design-hardware；目录/格式已核实，实际调用未跑 |
| Codex CLI/Desktop | 0.163.0-alpha.10.2 (L) | `~/.agents/skills/`（首选）<br>`~/.codex/skills/`（旧版兼容） | `<repo>/.agents/skills/`<br>`<repo>/.codex/skills/` | `<name>/SKILL.md` + YAML frontmatter | 已安装客户端；**未安装** design-hardware；路径来自同版本源码，实际注入未跑 |
| WorkBuddy | 5.8.3.0 (L) | `~/.workbuddy/skills/` | `<repo>/.workbuddy/skills/` | `<name>/SKILL.md`；也可在技能页导入本地包 | 已安装客户端；**未安装** design-hardware；路径/扫描逻辑已核实，GUI 导入刷新未跑 |

### 客户端能力

| 能力 | Claude Code | Codex | WorkBuddy |
|---|---|---|---|
| 本机命令 | 是（Bash/PowerShell 工具）L/D | 是（exec/shell，受沙箱与审批）L | 具备终端基础设施；本会话未实跑 L/I |
| 本机文件读写 | 是 L/D | 是（工作区读，写入受沙箱）L | 是（本地文件/办公技能）L |
| 图片输入 | 是（拖拽/粘贴/路径）D | 是（`-i/--image`）L | 有图像/多模态技能；实际视觉注入未验证 L/U |
| PDF | 文本可读；>10 页需按页渲染，本机未装 `pdftoppm` L | 可读文本；PDF 渲染依赖技能/Poppler，本机缺 L | 办公技能可查看 `.pdf/.ofd`；是否可直接视觉理解未验证 L/U |
| 网络 | 是（WebFetch/WebSearch，受权限）D | 受模型后端与沙箱网络策略约束 L/I | 有应用/模块/连接器，shell 出网未验证 L/I |
| 中断恢复 | `--resume/--continue` D/L | `codex resume` / `exec resume` L | 会话持久化存在；恢复入口未验证 L/I |

> 普通 ChatGPT 聊天、Codex 云端任务不等于本机客户端：它们即使能读 Skill，也不必然能连接你电脑上的 EDA、读本地工程或执行 `lceda-pro`。本文件只讨论**能访问本机文件和命令**的客户端。

## 3. 安装（只装一个客户端，不要三套全装）

### Claude Code

```powershell
# Windows
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".\design-hardware" "$HOME\.claude\skills\design-hardware"
```

```bash
# macOS / Linux
mkdir -p ~/.claude/skills
cp -R ./design-hardware ~/.claude/skills/design-hardware
```

新开一个会话，在对话中明确说“使用 design-hardware”。项目级安装放在 `<repo>/.claude/skills/design-hardware`，只对该仓库生效。

### Codex

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
Copy-Item -Recurse -Force ".\design-hardware" "$HOME\.agents\skills\design-hardware"
```

旧版 Codex 仍可能读取 `~/.codex/skills/`；两处都放会形成重复技能，优先只放 `~/.agents/skills/`。新开会话后用 `$design-hardware` 或直接描述任务调用。项目级安装放在 `<repo>/.agents/skills/design-hardware`。

### WorkBuddy

把 `design-hardware` 整个目录复制到 `~/.workbuddy/skills/design-hardware`，或在技能页使用“添加技能/上传技能”导入本地包。**保留 `SKILL.md` 和 `references/`、`scripts/`、`assets/` 的相对结构**，不要只上传 `SKILL.md`。刷新/重开技能页后确认列表中出现 `design-hardware`。

> 以上安装命令只复制 Skill。它不会安装嘉立创EDA、`lceda-pro`、easyeda-agent 或 EDA Agent Connector，也不会让云端会话获得本机访问。

## 4. 首次接通（五步，分开报告）

在**授权副本**上做，不要在用户正在编辑的原工程上做。

1. **读工作目录**：Agent 能列出当前目录并读到 `design-hardware/SKILL.md`。
2. **无害文件往返**：在临时目录创建 `connect-test.txt`，写入一行，读回并核对内容；删除。
3. **读 EDA 工程**：`python scripts/eda_exec.py doctor` 显示 `tool_present/tool_connected`；`python scripts/eda_exec.py doctor --project <copy>` 显示 `project_readable:true`。这一步只读。
4. **最小写入**：在副本上 `apply --dry-run`，再执行一个最小计划（例如改一个已有器件的位号或加一个电源标记），逐项 `verified`；不要用“命令返回 0”代替回读。
5. **保存/重开**：`save` 返回 true 后 `reopen-check`，确认工程/页身份和对象都 `match`；再实际打开图页看一眼。

任一步失败时按层定位：客户端命令 → Skill 发现 → 文件读写 → EDA CLI → EDA 连接 → 工程可读 → 工程可写 → 保存/重开。不要把上层失败写成下层通过。

## 5. EDA 连接器装在哪里

EDA Agent Connector / `easyeda-agent` 的扩展装在**嘉立创EDA专业版内部**，不是在 Claude Code、Codex 或 WorkBuddy 的“连接器”菜单里。安装后需要在 EDA 中打开目标工程并允许外部交互，再运行：

```bash
easyeda health
```

`design-hardware` 自带的 `lceda-pro` 适配器是另一条路线，不依赖 easyeda-agent。两条路线都不访问网络、不下单；实际能力以当前 `--help`/`doc api` 为准。

## 6. 已知差异与坑

- **全在线 vs 半离线**：`lceda-pro open` 打开的会话在本机实测恒为半离线；半离线可以做真实读写/保存/网表/导图，但不能写成“全在线验收”。全在线结论只能来自用户自己的全在线 GUI 会话。
- **PATH 刷新**：安装客户端/CLI 后，已打开的终端和 Agent 进程不会自动刷新 PATH；新开进程或重启客户端。
- **工作目录**：客户端的工作目录不一定等于工程目录；Skill 用绝对路径或先 `cd` 到仓库。Agent 不应假定“当前目录就是工程”。
- **空格/中文路径**：Windows 下用引号包裹；脚本内部用 `Path`，不要手拼字符串。
- **云端会话**：无法访问本机 EDA 时，继续做方案/计算/离线检查，明确写“未写入”，不要用文本或 JSON 冒充工程已改。
- **技能重复**：同一客户端同时存在用户级和项目级同名 Skill 时，加载优先级可能不同；先只保留一处，确认生效后再调整。
- **未实测**：WorkBuddy GUI 导入/刷新、Codex 实际 Skill 注入、Claude Code 实际 `/design-hardware` 调用，本机尚未完成；相关结论标 `I/U`，不冒充通过。

## 7. 相关命令

```bash
python scripts/doctor_env.py --summary
python scripts/eda_exec.py doctor
python scripts/eda_exec.py doctor --project /path/to/copy.eprj2
python scripts/eda_exec.py read --project /path/to/copy.eprj2 --schematic <name> --page-name <page>
python scripts/eda_exec.py apply --project /path/to/copy.eprj2 --plan plan.json --dry-run
python scripts/eda_exec.py apply --project /path/to/copy.eprj2 --plan plan.json --save
python scripts/eda_exec.py drc --project /path/to/copy.eprj2 --schematic <name> --page-name <page>
python scripts/eda_exec.py reopen-check --project /path/to/copy.eprj2 --snapshot snapshot.json
```

所有命令输出 JSON；`status` 不是 `verified`/`match` 时不要报告成功。
