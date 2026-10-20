# Hardware Design Skill · AI画板搭档

配合 AI Agent，把“我想做个小装置”持续推进为经过实际效果验证的可用实物；尽量在嘉立创生态完成适用环节。已有电路连接图、PCB布局走线、工程审查和商城配单能力全部保留。没用过 EDA 也能描述用途开始；工程师可以直接给型号、约束或现有工程。

用户负责说想实现什么，Agent 负责推荐方案、查资料、选型核算、连接已配置的 EDA 工具、实际绘图和检查。本 Skill 是 Agent 的方法包，本身不是独立应用，也不会自动获得你电脑、设备或商家账户的控制权限。

**Skill 名称：** `design-hardware` · **许可：** MIT · **主要语言：** 中文

> 这是一套 Agent Skill，不是 EDA 软件或自动布线器。操作真实编辑器还需要已配置的 EDA 执行工具，例如 [easyeda-agent](https://github.com/zhoushoujianwork/easyeda-agent)。本项目独立维护，不代表嘉立创或其他工具厂商。程序与实物任务仍需匹配工具链、设备、制造与测试条件。

## 目标：idea落地，不止画完板

```text
我想做一个花盆土干了手机提醒的小装置，不懂EDA，也不会写程序。
请带我做到能用，优先用嘉立创体系里合适的方案、零件和制造服务。
```

对完整设备目标，Agent会组织：用途与验收场景 → 参考/原型路线 → 电子与结构设计 → 程序/连接与用户交互 → 购料制造装配 → 烧录配置 → 实际场景验证。

- 优先寻找适用的立创开发板、技术资料和许可允许的开源参考，再衔接EDA、商城、PCB/SMT及所需结构服务。
- 图纸、BOM、装配变体、程序/配置、结构与制造文件保持对应，不把剩余程序和调试默认为用户自己研究。
- 各项状态分别报告：画完图、编译、工厂装配、烧录和用户功能验收不是同一件事。
- 缺样机/账号/执行通道时，继续能做的准备，保留真实卡点与下一步；不会声称已运行、已购买或已实测。
- 体系内能力有缺口时说明原因与最小补充，不杜撰通知云服务或任意工厂代开发能力，也不强推不需要的业务。

**局部任务照常：** 只review、只画图、先方案或改PCB时不强行扩展为完整产品开发。现成模块能更快验证用途时可提出路线，但用户明确要定制板时保留定制交付。

详见 [想法到实物](design-hardware/references/idea-to-product.md)、[程序与联调](design-hardware/references/firmware-bringup.md) 和 [功能验收](design-hardware/references/product-acceptance.md)。

## 可以做什么

| 任务 | 工作方式 |
|---|---|
| 从需求画原理图 | 明确关键约束、选型、查手册、核算、绘制、回读连接 |
| 整理混乱原理图 | 保全引脚和网络，按功能排版，局部短线、跨区网名连接，导出实际图面复核 |
| 修改现有设计 | 读取实际工程，保留正确部分，跟踪修改影响 |
| 选型、换料与建库 | 核对完整型号、封装、引脚和焊盘映射 |
| PCB 布局布线 | 同步原理图、落实机械约束、分区布局、关键布线、铜皮和丝印 |
| 审查与调试 | 给出有位置、有依据、有复验方法的问题 |
| 检查与交付 | 分开报告连接、未布线、DRC、制造输出与样机实测状态 |

领域入口涵盖 MCU / SoC / FPGA、电源与电池、工业控制、电机驱动、模拟采集、有线通信、无线射频、显示音视频、高速数字、照明和音频等主流任务。“覆盖”指工作流与资料路由，**不代表所有器件、协议或行业都已验证**。

## 按任务调用的绘图经验库

经验留给Agent在后台使用，新手仍从一句用途开始。现有原理图排版流程保留，另外加入190条带条件的工程检查提示：

| 内容 | 条目 | 典型细节 |
|---|---:|---|
| [原理图](design-hardware/references/schematic-details.md) | 45 | 库脚映射、上电/掉电反灌、启动默认态、接口角色、NC与装配变体 |
| [PCB布局](design-hardware/references/pcb-placement-details.md) | 32 | 插拔/壳体、去耦回路、采样位置、开关节点、传感器与天线 |
| [布线与铺铜](design-hardware/references/pcb-routing-details.md) | 35 | 完整载流路径、Kelvin、参考层/回流、差分/过孔、铜区重算 |
| [制造与首板](design-hardware/references/manufacturing-details.md) | 30 | 封装/孔/阻焊/钢网、坐标旋转、同版制造包、首板供电与测试 |
| [12类领域易漏项](design-hardware/references/domain-design-details.md) | 48 | 主控/高速、电源/电池、驱动/采集、工业/USB、无线/音视频、照明与特殊工艺 |

[经验与来源记录](design-hardware/references/design-experience.md)区分实际看过的图纸、作者修订记录、官方指南与仅入口资料，注明适用条件和未读取范围。结合SparkFun、Arduino、ODrive、Crazyflie、Raspberry Pi、立创开发板等资料，按具体器件与工艺重新核对；不是照抄整板，也没有遍历所有开源作品。

条目不是190条固定参数或认证规则：Agent按任务选择，落实设计与工具约束并回读/复验。经验继续积累到工程记录；经授权、脱敏和核对后再沉淀到共享Skill，不自动公开客户工程。不用经验数量代替真实工程和实物验收。

## 最新增量：融合0.6.0工程经验

保留以前全部能力与190条检查，新增按需读取的 [原理图机制卡](design-hardware/references/schematic-lessons.md) 和 [PCB机制卡](design-hardware/references/pcb-lessons.md)：按“适用条件与原因、设计动作、怎么查”解释热插拔过冲、整板低功耗、ADC分压、Type-C取电、I2C等效上拉、去耦回路、USB触点汇合、散热焊盘、载流和同版制造包等问题。

Agent在模块写入前选择适用项，写入后回读，交付前复核；新手无须理解或逐项批准内部检查。机制卡展开已有检查并补充易漏原因，不重复累计条数。固定阻值/间距、全系列统一启动电路、所有散热片接地等建议改为依据具体器件与工况；未合入的旧脚本不因新文档引用而成为可用能力。

## 从新版本协作包吸收的改进

在保留上述能力的基础上，融合用户提供的`hw-eda-engineer 0.5.0`的方法，按当前Skill的工程边界改写：

- [8种起步方案](design-hardware/references/starter-patterns.md)：灯/指示器、温湿度、开发板、电池电源、低压开关、USB键盘、RS485采集和电机小车；提供功能骨架，不照抄固定芯片/阻容值。
- [外壳协同](design-hardware/references/enclosure-integration.md)：板框、孔、接口、插拔空间、天线/传感器、材料与加工文件一起核对。
- [项目关联记录](design-hardware/references/project-coherence.md)：图纸、BOM、实际物理脚/GPIO、固件、外壳、制造和测试对应；沿用现有格式，不强制新手维护JSON。
- [分层排障](design-hardware/references/troubleshooting.md)：从实际日志定位连接、图面、电气、制造、烧录与实物问题，不见到相似网名就自动合并。
- [完整案例演练](design-hardware/references/product-example.md)：从花盆缺水提醒目标推进至实物验收，修正了两节AA经LDO维持3.3V、拔出探头代替真实土壤校准等不可靠做法。
- 两个重新实现的可选离线辅助：电池侧状态续航估算，以及带文本边界/覆盖范围的原理图几何检查。Agent准备输入，不是每次画板的强制步骤。

## 没用过 EDA？这样开始

首次需要在支持本机工具的 Agent 中安装本 Skill，并接通 EDA 执行工具。你可以先对 Agent 说：

```text
我没用过EDA，请使用 design-hardware 带我做。
先检查我电脑还缺什么；你能做的自己做，需要我操作时一次告诉我一步。
我想做一个花盆土干了能给手机发提醒的小东西。
```

Agent 会先讲清楚推荐路线，只问影响方案的关键问题，比如“放室内还是室外”“方便插电还是必须用电池”。不需要你先选芯片、封装、板层或填写专业需求表。

- **能自动做的：** 真实工具允许范围内的资料读取、选型、计算、绘图、检查与已授权配置。
- **需要你做的：** 只有无法代做的登录、界面设置或用途/预算等重要选择；每次给具体动作和成功标志。
- **要看清的结果：** 图纸在哪、实际做到哪、检查发现什么、还差什么、下一步是什么。

没有本机通道或 EDA 连接时，Agent 会明确说明，继续可独立完成的方案，不会把文字方案说成已经画好图。手机提醒等功能还涉及固件和手机/服务端部分，图纸、程序、实物与实测分别交付。

已有经验的工程师可以直接说：

```text
请使用 design-hardware，读取当前工程，将这一路传感器改为4-20mA输入。
保留接口和板框，完成原理图与PCB修改，检查后保存并列出待测项，不用讲入门。
```

## 结合立创商城与嘉立创做出实物

中国大陆项目优先检索立创商城合适候选，尊重指定供应链/自有库存。先保证电气、机械和可靠性，再比较供应与总成本；设计阶段就核对完整型号、封装、C号（商城商品编号）与EDA库身份。

```text
想做5块温湿度小板，我不会焊。优先选立创商城合适的零件，
帮我准备嘉立创工厂焊好的路线。你负责查料、核对数量和文件，列清费用与待确认项。
```

Agent会按实际任务处理：

- **选准料：** 完整型号/规格/封装、C号、真实商品链接和EDA引脚/焊盘映射。
- **算清数量：** 单板用量、装配板数、备件/备损、已核实自有料、起订及实际购买规则。
- **看清花费：** 按购买数量匹配阶梯价；区分用料成本、实际购料支出、剩余料和PCB/SMT等未计费用。
- **处理缺料：** 复核替代兼容性；需改图时同步工程与清单，不只是替换BOM里的C号。
- **准备配单：** 从已保存工程和明确变体生成零件清单，核对平台匹配结果；上传、订单与支付仅依真实工具能力和相应用户授权进行。

**立创商城购料与嘉立创SMT的选料、库存和价格独立核对。** 商城有货不等于SMT可贴，EDA有库不等于已经购买。需要工厂组装时，另查SMT物料与BOM/坐标、包装/备料和报价，不假设个人散料能直接抵扣工厂用量。

不把旧库存/搜索缓存当实时保证，不编造C号或商品链接，不承诺固定优惠或交期。缺报价不填0；尚未登录、上传或下单会如实报告。需要面板/外壳等其他服务时再按真实需求衔接。

业务依据与边界见 [立创商城配单](design-hardware/references/lcsc-sourcing.md)、[嘉立创实物交付](design-hardware/references/jlc-handoff.md) 和 [官方来源](design-hardware/references/sources.md)。本仓库提供Agent流程，不内置商城/SMT账户连接或未公开采购API。

## 协作方式

方案、原理图、布局和交付设四个可见检查点。默认在已授权范围内检查后继续；说“确认后再布线”时才在该边界等待。新增模块用设计卡核对构成、核算、失效和PCB影响，不机械套用某个芯片的阻容值。

选型同时考虑指定型号、真实规格、供应与装配变体。DNP不等于NC，连接表与BOM区分当前装配状态；无C号不自动阻断非立创供应链工程。

## 首次安装（只需配置一次）

以下供 Agent 或需要自行配置的用户参考。Agent 应先检查已有什么，不要让用户重复安装。具体客户端版本和包格式以当前界面为准。


点击本页面 **Code → Download ZIP**，解压后找到 `design-hardware` 目录。复制时保留整个目录，不要只复制 `SKILL.md`。

也可以使用 Git：

```bash
git clone https://github.com/zsx3896926/hardware-design-skill.git
```

### Claude Code

将 `design-hardware` 整个目录复制到用户技能目录：

- Windows：`%USERPROFILE%\.claude\skills\design-hardware`
- macOS / Linux：`~/.claude/skills/design-hardware`

重新加载客户端，在对话中明确要求使用 `design-hardware`。配置了自定义用户目录时，以客户端实际配置为准。

### Codex

将 `design-hardware` 复制到 `~/.codex/skills/`。使用其他技能发现目录或自定义配置时，以客户端实际文档为准。重新加载客户端，使用 `$design-hardware` 调用。

### WorkBuddy

在技能页面使用“添加技能 / 上传技能”导入本地技能包并启用。用本仓库的 `design-hardware` 目录制作当前客户端要求的本地包，保留 `SKILL.md` 和相对引用目录；包格式与入口层级以当前导入界面要求为准。

```text
请使用 design-hardware，先检查能否读取当前工程、执行本机命令，
以及通过 easyeda-agent 连接嘉立创 EDA。先报告连接状态，再执行设计任务。
```

WorkBuddy 是支持 Skill 与本机执行能力的候选宿主；**尚未完成本项目与 WorkBuddy 的端到端兼容实测**。easyeda-agent 的安装器不保证自动把技能装入 WorkBuddy。

## 配合嘉立创 EDA 实际绘图

需要同时具备嘉立创 EDA 专业版、EDA Agent Connector、本机 easyeda CLI/daemon，以及对应的 easyeda-agent Skill。按 [easyeda-agent 安装说明](https://github.com/zhoushoujianwork/easyeda-agent) 完成配置，开启“允许外部交互”，打开目标工程后检查：

```bash
easyeda health
```

两套 Skill 配合：`design-hardware` 负责工程方法、设计意图和验收；`easyeda-agent` 负责按当前协议执行 EDA 动作。不要用本技能覆盖其原有 Skill。

## 常用需求

**用生活语言开始**

```text
我想做个天热了自动转的小风扇，完全不懂电路，你帮我推荐，先给方案。
```

```text
我只有一句想法，没有工程文件。请带我从零开始，别让我先选芯片或学命令。
```

Agent 应读取可用信息，必要时索取产品型号/链接/铭牌等可观察资料，不凭空猜负载额定。


**从零画原理图**

```text
使用 design-hardware 和 easyeda-agent，画一块 ESP32 控制板的原理图。
USB 5V供电，需要一路I2C传感器、下载调试接口和LED。
核对供电、启动与引脚，再实际绘制并检查保存。本次只做原理图。
```

**沿用既有 PCB**

```text
使用 design-hardware，优化当前PCB布局布线。
保留板框、安装孔、连接器位置和锁定器件，优先解决电源回路、回流和丝印问题。
完成后报告实际未布线、DRC与未覆盖项，不要无目的整体重排。
```

**整理画得太乱的原理图**

```text
使用 design-hardware 和 easyeda-agent，整理当前原理图，让电路连接图容易读。
保持所有器件、脚号、数值、网络、NC和PCB绑定不变。
按功能分区，减少跨区长线，保留局部电路，整理文字和标题。
整理前后核对连接，导出实际整页和局部图检查，修复遮挡、歧义和越界后保存。
```

排版方法参考实际查看的SparkFun ESP32系列与Arduino UNO原理图，详见 [排版与看图验收](design-hardware/references/schematic-layout.md)。这些是Agent的执行与验收要求，不能替代绘图工具能力，也不代表已修改easyeda-agent的自动布局算法。

**只检查**

```text
使用 design-hardware 检查当前原理图与PCB。
按已证实缺陷、条件性风险、待实测和优化建议分别报告，附位置、证据和处理建议。
先不要修改工程。
```

## 内容结构

```text
design-hardware/
  SKILL.md                    主入口与工程师交互方式
  agents/openai.yaml          客户端展示信息
  references/                 按任务读取的工程工作流与专业参考
  assets/engineering-notes.md  可裁剪的工程记录模板
  scripts/calculate.py        无第三方依赖的基础计算工具
  scripts/netlist_check.py    显式连接表的只读结构自检
  scripts/power_budget.py     显式电池侧状态续航估算
  scripts/sch_layout_check.py 实际回读几何的候选问题提示
```

计算工具支持 LED 限流、无负载分压、I2C 上拉范围和 LDO 压差/功耗初算。输入全部用 SI 单位，不访问网络、不写工程、不调用 EDA。运行以下命令查看输入字段：

```bash
python design-hardware/scripts/calculate.py --help
```

计算工具是可选辅助，不是绘图的强制前置。其简化模型不能代替稳定性、热、EMC、信号完整性或板级验证。

离线连接表工具按完整物理引脚ID集合核对连接与NC、重复位号、显式上拉要求和装配状态；单脚网络/相似名称只提示核查，不自动合并或改线。输入格式及边界见 [连接表契约](design-hardware/references/connectivity.md)。

```bash
python design-hardware/scripts/netlist_check.py design-hardware/assets/example-connectivity.json --json
```

示例使用虚构器件，不能拿来画真实电路。退出0仅表示输入中未发现结构阻断，缺失引脚表会单列覆盖不足；该工具不证明电源地无短路、去耦充分、额定满足或真实EDA连通。

续航与图面辅助的字段、单位和覆盖范围见 [离线工具契约](design-hardware/references/offline-tools.md)。以下是虚构算例，不表示硬件参数或电路已经验证：

```bash
python design-hardware/scripts/power_budget.py design-hardware/assets/example-power-budget.json
python design-hardware/scripts/sch_layout_check.py design-hardware/assets/example-layout.json
```

续航不默认可用容量折扣，不能混用负载端电流与电池容量；零耗电不报告无限寿命。几何检查的0退出不表示电气/图面通过，缺文字边界和实际对象时保持未覆盖；仍需要EDA回读、官方检查和实际导图复核。输入契约与来稿同名脚本不同，不能直接混用旧JSON。

## 验证状态

- 已检查技能结构、内部引用及计算工具的典型值、边界和无效输入。
- 已进行缺少工程/连接、未知参数、新手首次使用、工程师改板、采购数量/阶梯价、商城与SMT分流、缺货替代、完整产品目标及功能验收等场景试跑。
- 原理图排版与工程细节经验库已加入结构检查；条目本身不是可执行的硬件自动验证器，场景试跑不等于真实EDA或首板验收。
- 离线辅助脚本已覆盖状态积分、错误电流基准、目标未满足、零耗电、非有限/重复键输入，以及文字范围、线穿本体、相切、越页和覆盖缺失等实际反例；本地共48项测试。
- **尚未完成这套 Skill 驱动真实原理图与 PCB 的端到端验收，也未完成商城/SMT账户操作、真实烧录或完整实物功能链的端到端实测。**
- 不保证特定客户端、模型、EDA 版本或执行器支持全部操作。
- DRC 通过、动作响应、连接回读与样机实测分别报告；未验证项不会默认通过。
- 高速、射频、安规隔离及汽车/医疗等项目仍需要适用资料、专业工具与相应工程签核。

## 本地验证

需要 Python 3.10 或更新版本，无第三方依赖：

```bash
python -m unittest discover -s tests -v
```

CI 运行相同检查。通过仅证明这些自动化检查通过，不证明硬件设计已验证。

## 参与改进

欢迎提交 Issue / Pull Request。优先提供脱敏的具体任务、预期行为、实际表现和复现材料；型号相关问题注明封装、资料版本及条件。不要提交密钥、客户工程或其他无权公开的内容。

优先改进工程工作流、可执行交付和减少无效追问；专业规则按需引用可靠资料，避免堆砌无条件通用口诀。

## 致谢与许可

合并参考了用户提供的 MIT 声明技能 `hw-eda-engineer` 中的口语协作、模块卡、需求摘要、分级评审和离线连接表思路；对默认值、阶段等待、数据覆盖和检查边界做了重写。原包未提供作者/版权主体，详见 [NOTICE](NOTICE)。

感谢 [easyeda-agent](https://github.com/zhoushoujianwork/easyeda-agent) 和嘉立创 EDA 的官方扩展能力。其代码、文档和商标遵循各自许可，本仓库不包含其实现。

本仓库采用 [MIT License](LICENSE)，允许使用、修改与分发，包括商业使用，需保留版权和许可声明。
