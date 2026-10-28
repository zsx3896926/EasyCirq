# 客户端兼容与首次接通

本文件只记录**当前能核实的事实**。客户端版本、目录和菜单会变化，安装前以本机实际界面/官方文档为准。标记：

- **L**：本机实测（LOCALLY VERIFIED）
- **D**：官方文档/版本源码（DOCUMENTED）
- **I**：推断，尚未实测（INFERRED）
- **U**：未知（UNKNOWN）

## 1. 先诊断，不先安装

在 Skill 目录运行（只读，不启动 daemon、不写工程）：

```bash
python scripts/doctor_env.py --summary
python scripts/doctor_env.py --summary --project /path/to/authorized-copy.eprj2
python scripts/doctor_env.py            # JSON，便于 Agent 读取
zhigou doctor                            # 执行层：runtime/daemon/connector/protocol/checks/next steps
zhigou capabilities                      # 执行层：逐能力 supported/unsupported/unknown + 原因
```

`doctor_env.py` 检查：当前工作目录、已安装客户端、各客户端技能目录、`easycirq` 是否已安装，并汇总 `zhigou doctor`/`capabilities` 的结果。它按当前客户端判定，不把“任意客户端存在 + 任意目录装了 Skill”当成就绪。

它**不测试可写性**。工程能打开不等于能写；写入必须在授权副本上用 `zhigou apply --dry-run` 和一次可回滚的 apply 验证。`zhigou doctor` 的 `connector` 不是 `connected` 时，先按 `zhigou connector install-steps` 完成人工导入，再重跑。

## 2. 历史客户端能力矩阵（2026-10-22 本机）

以下是当日记录，不代表当前安装状态。v1.0.0 的包级隔离安装/升级/回滚验证与客户端实际装载、EDA 真机执行分开记录；不要把旧表中的“未安装”用于判断本机现状。

| 客户端 | 版本 | 用户技能目录 | 项目技能目录 | 安装格式 | 本机状态 |
|---|---|---|---|---|---|
| Claude Code | 2.1.303 (D/L) | `~/.claude/skills/` | `<repo>/.claude/skills/` | `<name>/SKILL.md` + 相对引用目录 | 已安装客户端；**未安装** easycirq；目录/格式已核实，实际调用未跑 |
| Codex CLI/Desktop | 0.163.0-alpha.10.2 (L) | `~/.agents/skills/`（首选）<br>`~/.codex/skills/`（旧版兼容） | `<repo>/.agents/skills/`<br>`<repo>/.codex/skills/` | `<name>/SKILL.md` + YAML frontmatter | 已安装客户端；**未安装** easycirq；路径来自同版本源码，实际注入未跑 |
| WorkBuddy | 5.8.3.0 (L) | `~/.workbuddy/skills/` | `<repo>/.workbuddy/skills/` | `<name>/SKILL.md`；也可在技能页导入本地包 | 已安装客户端；**未安装** easycirq；路径/扫描逻辑已核实，GUI 导入刷新未跑 |

### 客户端能力

| 能力 | Claude Code | Codex | WorkBuddy |
|---|---|---|---|
| 本机命令 | 是（Bash/PowerShell 工具）L/D | 是（exec/shell，受沙箱与审批）L | 具备终端基础设施；本会话未实跑 L/I |
| 本机文件读写 | 是 L/D | 是（工作区读，写入受沙箱）L | 是（本地文件/办公技能）L |
| 图片输入 | 是（拖拽/粘贴/路径）D | 是（`-i/--image`）L | 有图像/多模态技能；实际视觉注入未验证 L/U |
| PDF | 文本可读；>10 页需按页渲染，本机未装 `pdftoppm` L | 可读文本；PDF 渲染依赖技能/Poppler，本机缺 L | 办公技能可查看 `.pdf/.ofd`；是否可直接视觉理解未验证 L/U |
| 网络 | 是（WebFetch/WebSearch，受权限）D | 受模型后端与沙箱网络策略约束 L/I | 有应用/模块/连接器，shell 出网未验证 L/I |
| 中断恢复 | `--resume/--continue` D/L | `codex resume` / `exec resume` L | 会话持久化存在；恢复入口未验证 L/I |

> 普通 ChatGPT 聊天、Codex 云端任务不等于本机客户端：它们即使能读 Skill，也不必然能连接你电脑上的 EDA、读本地工程或执行 `zhigou`。本文件只讨论**能访问本机文件和命令**的客户端。

## 3. 安装（只装一个客户端，不要三套全装）

### Claude Code

```powershell
# Windows
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".\easycirq" "$HOME\.claude\skills\easycirq"
```

```bash
# macOS / Linux
mkdir -p ~/.claude/skills
cp -R ./easycirq ~/.claude/skills/easycirq
```

新开一个会话，在对话中明确说“使用 easycirq”。项目级安装放在 `<repo>/.claude/skills/easycirq`，只对该仓库生效。

### Codex

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
Copy-Item -Recurse -Force ".\easycirq" "$HOME\.agents\skills\easycirq"
```

旧版 Codex 仍可能读取 `~/.codex/skills/`；两处都放会形成重复技能，优先只放 `~/.agents/skills/`。新开会话后用 `$easycirq` 或直接描述任务调用。项目级安装放在 `<repo>/.agents/skills/easycirq`。

### WorkBuddy

把 `easycirq` 整个目录复制到 `~/.workbuddy/skills/easycirq`，或在技能页使用“添加技能/上传技能”导入本地包。**保留 `SKILL.md` 和 `references/`、`scripts/`、`assets/` 的相对结构**，不要只上传 `SKILL.md`。刷新/重开技能页后确认列表中出现 `easycirq`。

> 以上安装命令只复制 Skill。它不会安装嘉立创EDA、`zhigou` 运行时或 `zhigou-connector`，也不会让云端会话获得本机访问。运行时从本仓库 `distribution/` 的发布包安装，安装后用 `zhigou doctor` 验证，而不是靠文件存在推断。

## 4. 首次接通（五步，分开报告）

在**授权副本**上做，不要在用户正在编辑的原工程上做。

1. **读工作目录**：Agent 能列出当前目录并读到 `easycirq/SKILL.md`。
2. **无害文件往返**：在临时目录创建 `connect-test.txt`，写入一行，读回并核对内容；删除。
3. **预检执行层**：`zhigou doctor` 的 `verdict` 为 `ok` 且 `daemon.status=running`、`connector.status=connected`、`protocol.service=zhigou-agent`；`zhigou capabilities` 的逐项状态带原因。两者在未连接时如实判 `blocked`/`unknown`，不猜。
4. **读工程 + 最小写入**：`zhigou project info`/`doc ls` 绑定工程与文档身份，只读回读用 `zhigou sch read`/`pcb dump`；在副本上用 `zhigou apply --dry-run` 对账后再执行一个最小计划（例如改一个已有器件的位号或加一个电源标记），逐项回读；不要用“命令返回 0”代替回读。
5. **保存/重开**：`zhigou pcb save`/`sch save` 成功后 `zhigou doc reload`，确认工程/页身份和对象都仍在；再实际打开图页看一眼。保存成功不等于重开后仍在。

任一步失败时按层定位：客户端命令 → Skill 发现 → 文件读写 → zhigou 运行时 → daemon → connector/protocol → 工程可读 → 工程可写 → 保存/重开。不要把上层失败写成下层通过。

## 5. 连接器装在 EDA 里面

`zhigou-connector` 扩展装在**嘉立创EDA专业版内部**，不是在 Claude Code、Codex 或 WorkBuddy 的“连接器”菜单里。它是本仓库自有 uuid 的扩展，与旧工具链的连接器隔离、可并存。导入是 EDA 内的显式人工动作：

```bash
zhigou connector path          # 本构建携带的 .eext 路径
zhigou connector install-steps # 逐步说明（导入/允许外部交互/重启/验证）
zhigou connector verify        # 校验磁盘上的 .eext 内容
zhigou doctor                  # 导入并重启后，connector 应为 connected
```

Agent 给一次动作和可观察的成功标志即可，不要求用户理解 daemon、端口或双 Skill；导入后必须靠 `zhigou doctor` 的真实握手判断，不以磁盘文件存在或截图冒充已连接。

## 6. 已知差异与坑

- **前台/离线状态**：`zhigou doctor` 的 `host` 会报告窗口、连接器与页面可见性；半离线/后台读取能拿到真实数据，但“全在线结论”仍只能来自用户的在线 GUI 会话。不要把半离线回读写成全在线验收。
- **PATH 刷新**：安装客户端/CLI 后，已打开的终端和 Agent 进程不会自动刷新 PATH；新开进程或重启客户端。
- **工作目录**：客户端的工作目录不一定等于工程目录；Skill 用绝对路径或先 `cd` 到仓库。Agent 不应假定“当前目录就是工程”。
- **空格/中文路径**：Windows 下用引号包裹；脚本内部用 `Path`，不要手拼字符串。
- **云端会话**：无法访问本机 EDA 时，继续做方案/计算/离线检查，明确写“未写入”，不要用文本或 JSON 冒充工程已改。
- **技能重复**：同一客户端同时存在用户级和项目级同名 Skill 时，加载优先级可能不同；先只保留一处，确认生效后再调整。本Skill不再需要第二套执行Skill；`~/.claude/skills` 等目录里的旧执行器副本不参与本Skill策略，也不要让Agent加载它。
- **未实测**：WorkBuddy GUI 导入/刷新、Codex 实际 Skill 注入、Claude Code 实际 `/easycirq` 调用，本机尚未完成；相关结论标 `I/U`，不冒充通过。

## 7. 相关命令

```bash
python scripts/doctor_env.py --summary
zhigou doctor
zhigou capabilities
zhigou project info --project <name>
zhigou doc ls --project <name>
zhigou sch read --project /path/to/copy.eprj2 --doc <page>
zhigou apply --dry-run --file plan.json --project /path/to/copy.eprj2
zhigou pcb dump --include-copper --project /path/to/copy.eprj2
zhigou doc reload --project /path/to/copy.eprj2
zhigou connector path
zhigou connector install-steps
```

所有 JSON 命令的字段以当前 `--help`/`zhigou capabilities` 为准；`status` 不是成功态时不要报告成功。
