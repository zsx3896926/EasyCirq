# AI 画板搭档 · Hardware Design Skill

**说出你想做什么，让 AI 帮你选零件、画原理图和 PCB，一步步做出能用的小装置。**

没用过 EDA、不会选芯片，也可以从一句话开始：

> “我想做一个温度太高就响的小东西，用 USB 供电，我不会画电路，你帮我做。”

本项目的推荐用法是：**把 `design-hardware` 和 `easyeda-agent` 两个 Skill 装进同一个 AI 客户端，再通过 EDA Agent Connector 插件连接嘉立创 EDA 专业版。** 然后直接描述需求，由 AI 在真实工程里推进设计。

[开始安装](#第一次使用先装好这几样) · [复制第一句话](#装好后复制这句话就能开始) · [遇到问题](#卡住了直接这样说) · [工程资料](#工程师与开发者入口)

## 你说想法，AI 负责推进

你只需要说明用途。有预算、尺寸、现成零件或参考图片，一起发给 AI；没有也可以先开始。

AI 应该负责：

- 推荐容易做成的方案，查器件资料，选零件并核对连接。
- 在嘉立创 EDA 中画原理图、整理图面、推进 PCB 布局布线。
- 检查实际工程，修复能确定的问题，保存并告诉你工程在哪里。
- 按需要核对立创商城物料，准备嘉立创 PCB / SMT 所需资料。
- 如果目标是完整设备，继续处理适用的程序、烧录和功能测试步骤。

**你不需要先学命令、填需求表，或者替 AI 判断芯片和封装对不对。** 普通选型、资料查询、绘图和检查由 AI 处理；确实缺少影响功能的关键信息时，才用日常语言集中问你。

这些是工作目标，能执行到哪一步取决于当前工具、工程和设备条件。[当前实测范围](#现在实际验证到了哪里)会单独说明。

## 第一次使用，先装好这几样

### 1. 准备电脑上的 AI 客户端和嘉立创 EDA

需要一个**能在你电脑上运行命令、读取文件和使用 Skill 的 AI 客户端**，例如 Claude Code 或 Codex，以及[嘉立创 EDA 专业版](https://pro.lceda.cn/)。按 easyeda-agent 当前说明使用专业版 V4。

WorkBuddy 也可以作为候选客户端，但要确认当前版本支持本地 Skill 和本机命令；本项目尚未完成 WorkBuddy 全流程实测。只在网页聊天窗口上传 Skill，通常还不能操作你电脑上的 EDA。

**不确定是否装齐？把下面整段发给你电脑上的 AI，让它先检查：**

```text
我想用下面两个项目，让你直接在嘉立创 EDA 里帮我画板：
https://github.com/zsx3896926/hardware-design-skill
https://github.com/zhoushoujianwork/easyeda-agent

请先读取它们的安装说明，检查当前电脑已有的软件、Skill 和连接状态。
帮我配置 design-hardware、easyeda-agent 及其 CLI，并检查 EDA Agent Connector。
已安装的不要重复安装；你能执行的检查和配置直接做。
需要我登录或点击界面时，一次只告诉我一个动作，并说明做到什么样算成功。
最后确认两个 Skill 都能被你读取，并通过 easyeda health 检查目标工程连接。
```

如果当前客户端不能执行本机命令，先换到具备该能力的客户端，再使用这段话。

### 2. 把本 Skill 装到 AI 客户端

在本仓库点击 **Code → Download ZIP**，解压，找到里面的 **`design-hardware` 文件夹**。

把这个文件夹完整放进客户端的技能目录，**不要只复制 `SKILL.md`，也不要把整个仓库当成这个 Skill。** 可以让 AI 帮你完成复制。

| 客户端 | 放置位置 |
|---|---|
| Claude Code（Windows） | `%USERPROFILE%\.claude\skills\design-hardware` |
| Claude Code（macOS / Linux） | `~/.claude/skills/design-hardware` |
| Codex（0.163 实测路径） | 首选 `~/.agents/skills/design-hardware`；旧版兼容 `~/.codex/skills/design-hardware`，两处只放一处 |
| WorkBuddy（5.8.3 实测路径） | `~/.workbuddy/skills/design-hardware`，或在技能页导入本地包；保留 `references/`、`scripts/`、`assets/` |

**当前正式补丁版本为 v1.0.1**，修复 v1.0.0 的 Python 3.10 兼容性与发布失败。首次可从正式 [Releases](https://github.com/zsx3896926/hardware-design-skill/releases) 下载 `design-hardware-installer-版本号.zip`，完整解压后双击 `Manage-Skill.cmd`，选择客户端安装。需要 Python 3.10+；不要求 Git。尚未发布正式包时，可从仓库运行 `python distribution/build_release.py --output dist` 构建本地安装器。

以后直接对 Agent 说：**“检查硬件设计 Skill 有没有更新，有的话告诉我变化。”** 更新检查会分别查看本 Skill 与 easyeda-agent 执行链（CLI、Skill、daemon、Connector），不会自动替换文件；明确要求升级后，在任务空闲时更新，再重新加载客户端。旧手动安装首次需选择“备份后迁移”，客户定制不会被静默覆盖。完整步骤见 [安装与更新说明](design-hardware/references/installation-updates.md)。

新版源码合并和正式稳定包发布是两件事：在线更新只跟随带完整资产的稳定 Release，不自动跟随 main。

安装后重新加载客户端，让 AI 确认能读取 `design-hardware`。自定义了技能目录时，以实际配置为准。

不确定装在哪、是否已装、当前客户端能否连 EDA 时，让 AI 先运行：

```bash
python design-hardware/scripts/doctor_env.py --summary
```

它按**当前客户端**判定状态（未检测到就要求 `--client`），并把 `versionMatch:false`、工程不可读计入 `incomplete`；同时分别报告 `lceda-pro` 与 `easyeda-agent` 两条 EDA 路线，**不能用一个绿色代表另一条路线就绪**。只诊断，不安装、不写工程。完整路径、能力矩阵和五步首次接通见 [客户端兼容与首次接通](design-hardware/references/client-compatibility.md)。

### 3. 安装 easyeda-agent 和 EDA 连接器

这一步把 AI 和真实编辑器接起来。**只装本 Skill 或只装 EDA 插件都不够。**

先让 AI 按 [easyeda-agent 官方安装说明](https://github.com/zhoushoujianwork/easyeda-agent#安装与开始使用)安装本机工具和它的 Skill。愿意自行安装时，打开对应终端执行：

**Windows PowerShell：**

```powershell
irm https://raw.githubusercontent.com/zhoushoujianwork/easyeda-agent/main/install.ps1 | iex
```

**macOS / Linux 终端：**

```bash
curl -fsSL https://raw.githubusercontent.com/zhoushoujianwork/easyeda-agent/main/install.sh | bash
```

安装器会识别支持的客户端；**本仓库的 `design-hardware` 仍需单独安装**。WorkBuddy 的 Skill 安装也需要按客户端要求核对。安装提示路径未加入 PATH 时，把提示交给 AI 处理即可。

然后在嘉立创 EDA 专业版中：

1. 从[插件市场](https://jlc-ext.com/item/zhoushoujian/easyeda-agent-connector)安装 **EDA Agent Connector**；也可以从 [Release](https://github.com/zhoushoujianwork/easyeda-agent/releases/latest) 下载 `.eext`，在扩展管理器中导入。
2. 开启 **允许外部交互**。菜单位置随版本可能变化，让 AI 根据当前界面带你找。
3. 打开或新建一个测试工程。第一次先用测试工程，保留原工程。
4. 告诉 AI：“检查连接，连上后继续。”由 AI 运行 `easyeda health` 并读取目标工程。

**成功标志：AI 能报告实际工程名称，并读取里面的页面或对象。** 只看到插件已安装，还不算接通。连接器安装、升级和版本问题交给 AI 按[官方快速开始](https://github.com/zhoushoujianwork/easyeda-agent/blob/main/docs/quick-start.md)排查。

<details>
<summary>为什么有两个 Skill，还有一个插件？</summary>

| 名称 | 你可以把它理解成 |
|---|---|
| AI 客户端 | 接收你的需求、查资料并调用工具的工作台 |
| `design-hardware`（本项目） | 告诉 AI 怎样按工程习惯设计、检查和交付 |
| `easyeda-agent` Skill 与本机工具 | 告诉 AI 怎样执行具体 EDA 操作 |
| EDA Agent Connector | 装在 EDA 里面，把操作送到真实编辑器 |
| 嘉立创 EDA 专业版 | 保存和编辑原理图、PCB 的软件 |

两个 Skill 保留各自目录，一起使用，不要互相覆盖。你日常只需对 AI 说需求。

</details>

## 装好后，复制这句话就能开始

第一次推荐从一个功能简单、USB 供电的小板开始。下面是一段**启动需求示例，不是已验证的成品项目**：

```text
请同时使用 design-hardware 和 easyeda-agent。

我完全不会 EDA，想做一个室内温度报警小板：
用 USB 供电，温度超过设定值时亮灯并发出声音，先做一块。
芯片、零件和实现方法请你推荐，优先考虑立创商城与嘉立创制造。

先检查连接并确认当前测试工程，然后在其中完成设计。
一般技术细节你查资料后决定，非关键细节采用容易实现的方案并简单说明。
只在缺少会影响功能、供电或尺寸的关键信息时问我，集中一次问清。

请实际绘制原理图并推进 PCB，检查、保存，告诉我工程和导出文件在哪里。
原理图按功能分区，文字不要遮挡，PCB 考虑实际装配与调试。
如果需要程序，也请准备最小可用程序和后续测试步骤。
常规步骤检查后继续，不必反复问是否继续；购买、支付或生产下单前再让我确认。
```

以后不用每次复制这么长。直接说“帮我做一个……”，或者“把刚才那个改成……”就可以。

### 过程中，你应该看到什么？

| 阶段 | AI 应该给你的结果 |
|---|---|
| 接通工具 | 读到了哪个真实工程，还缺什么配置 |
| 确定做法 | 简短说明推荐怎么做，有关键取舍时再问你 |
| 画原理图 | 工程里出现真实器件和连线，并核对实际连接 |
| 做 PCB | 实际板框、器件和走线，以及已执行的检查结果 |
| 准备制作 | 对应版本的文件、零件清单、已核实费用与待查项 |
| 做到能用 | 程序、烧录、上电和功能测试的适用步骤与实际结果 |

这些是可见进度点，**不是每到一步都要你批准一次**。AI 能继续就继续，遇到真实卡点再说明。

## 换成你自己的想法

只需描述想看到的效果，不必先想好电路：

> “做个打开抽屉就亮的灯，用电池，尽量省电。”
>
> “我想测房间温湿度，显示在小屏幕上，放桌面用。”
>
> “把当前原理图整理清楚，连接保持不变。”
>
> “现有板子加一个接口，其他位置尽量别动。”

有现成设备、负载或电源时，把型号、铭牌照片或商品链接一起给 AI，让它核对参数。只想画原理图，也直接说“本次只做原理图”。

## 不会焊，也可以继续

告诉 AI：

```text
我不会焊，想收到焊好的板。
请按实际可用的嘉立创 SMT 服务核对零件和文件，准备报价需要的资料。
查不到的价格和库存标出来，下单付款前给我看清单。
```

AI 应优先衔接合适的立创商城选型、嘉立创 PCB 与 SMT 服务。**商城有货与 SMT 能贴片需要分别核对**，费用和交期按实际渠道查询。

收到板子后，AI 继续带你做适用的烧录和测试；工厂焊接完成，不代表程序已经烧好或整机功能已经实测。

## 卡住了，直接这样说

**AI 只给文字，没有画到 EDA 里：**

```text
请检查 easyeda-agent 的实际连接和写入能力，读取目标工程后再执行。
我需要真实工程中的图纸。暂时不能写入时，说明具体卡点并帮我解决。
```

**AI 一直问芯片、封装和板层：**

```text
这些技术选择请你根据用途查资料并推荐。
先采用合理、容易实现的方案继续，只问我会影响实际使用的关键问题。
```

**报错了或中途断开：**

```text
请先回读工程，判断哪些操作已经完成，再修复并接着做。
不要重复创建器件或整页重画；需要我操作界面时，一次只给一步。
```

**原理图太乱：**

```text
请保持器件、物理引脚、网络和 PCB 绑定不变，按功能重新排版。
核对整理前后的连接，导出整页和局部图，检查文字、连线和标签遮挡后保存。
```

## 现在实际验证到了哪里？

截至 2026-10-27，证据来自 Windows 11、嘉立创 EDA 专业版 4.1.78、easyeda-agent 1.15.0 下的独立工程副本。不同轮次的结果分别归档，不能拼接成任意工程全自动成功的保证。

| 范围 | 已验证 | 保留边界 |
|---|---|---|
| 简单 PCB 工程 | 双按键 LED 的原理图、布局布线、铺铜、原生 DRC、保存重开与逐脚核对；导入副本和局部移动有真实记录 | 没有实物功能、制造文件或高复杂度通用能力保证 |
| 原理图重排 | 24 器件 / 8 分区副本写入，局部修正后保存重开，24 器件身份、59 引脚与 13 网一致 | compose 批次在 strict gate 停止；非 strict PASS，strict FAIL；最终保存由独立恢复步骤完成 |
| 离线工具 | 原理图几何、电源路径/走廊、实例身份、PCB 证据门禁与模块合批均有回归 | 候选路线、启发式评分和模拟宿主不等于真实布线/DRC/硬件通过 |
| 实验反馈闭环 | 观察、计划、范围控制、差异、评价、案例；真机旧代码能报告移动后 DRC 失败并恢复 | 最终收紧代码的真机写入 BLOCKED；部分状态 unknown，不能当作 pass |
| 安装兼容 | Python 3.10+；Claude / Codex / WorkBuddy 安装路径与升级/恢复由发布包冒烟检查 | 文件安装成功不等于客户端已经装载；WorkBuddy 全流程仍未验证 |

**v1.0.0 发布准备不包含新的 EDA 真机验收。** 首次使用请在副本中确认客户端能读取 Skill、工具连接正确，并检查每项任务的实际回执。

[发布说明与限制](docs/releases/v1.0.0.md) · [原理图真机记录](docs/round12-real-machine.md) · [反馈闭环记录](docs/round12/report.md) · [导入/局部移动记录](docs/round11/live-regression/README.md)

## EasyEDA 生态能力

v1.0 候选整合了差分等长审核、工程日志取证、模块复用计划、格式校验与只读预览适配，以及 API/SDK 本地检索。详见[生态工具集成](design-hardware/references/easyeda-ecosystem.md)。新增入口默认离线；插件部署、实际渲染和真实工程写入按各项边界单独验收，不因上游支持就宣称本机可用。

## 工程师与开发者入口

入门不需要先读这些资料，AI 会按任务使用。

- [工程资料、工具与验证记录](docs/readme-technical.md)
- [原理图排版与看图验收](design-hardware/references/schematic-layout.md)
- [设计卡库](design-hardware/references/design-cards/README.md)与[工程深潜](design-hardware/references/engineering-deepdives/README.md)
- [工程设计决策库](design-hardware/references/decisions/README.md)：架构取舍、引脚/状态/接口、容差与实验、线束/变体、校准/变更/复用与资产有效性
- [立创商城选型与配单](design-hardware/references/lcsc-sourcing.md)
- [嘉立创 PCB / SMT 生产规则](design-hardware/references/jlc-production.md)
- [想法到实物](design-hardware/references/idea-to-product.md)与[程序联调](design-hardware/references/firmware-bringup.md)
- [官方 CLI 适配器](design-hardware/references/eda-execution.md)：已有能力保留，推荐入门路线仍为本 Skill + easyeda-agent。

欢迎提交 [Issue](https://github.com/zsx3896926/hardware-design-skill/issues) 或 Pull Request，优先提供脱敏的实际任务、遇到的问题和复现材料。

## 致谢与许可

感谢 [easyeda-agent](https://github.com/zhoushoujianwork/easyeda-agent) 提供 EDA 执行工具与连接器。

本仓库及此前提供的 `hw-eda-engineer` 等 Skill 均由项目作者编写，相关内容已统一维护，不另作第三方致谢。外部工程资料仍保留来源与许可记录。

本项目独立维护，非嘉立创官方产品。采用 [Apache License 2.0](LICENSE)，允许使用、修改与商业使用，按许可保留声明；外部工具、资料与商标遵循各自许可。
