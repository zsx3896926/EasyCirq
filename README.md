<img src="assets/brand/logo-horizontal-1200.png" alt="智构 · EasyCirq" width="520">

# 智构 · EasyCirq

**AI 画板搭档 · Hardware Design Skill + 自有 EDA 执行层**

说出你想做什么，让 AI 帮你选零件、画原理图、布 PCB、检查并交付。本项目由两部分组成：

| 层 | 是什么 | 位置 |
|---|---|---|
| **设计方法层** | `easycirq` Skill：需求澄清、选型与供应链、工程计算、设计规则、G0–G6 阶段门禁、证据口径、交付话术 | `easycirq/` |
| **执行层** | 自有 `easycirq` 工具链：CLI + daemon + 连接器，从本仓库源码构建，在真实嘉立创 EDA 里读写工程 | `runtime/`、`connector/`、`protocol/`、`distribution/` |

不依赖上游 `easyeda-agent` 的 Skill 或 CLI（它只作为 MIT 来源保留在 `third_party/`，用于来源追溯）。
以前"装两个 Skill + 一个插件"的步骤已经不需要了。

> **2026-10 重命名**：仓库、Skill、CLI 与协议统一更名为 **EasyCirq**（中文名「智构」）。旧安装目录请先迁移；步骤见 [迁移说明](docs/migration-easycirq.md)。

> 首次使用请先读 [安装说明](distribution/INSTALL.md)；本文的"快速开始"是最短路径。

## 快速开始（Windows，约 10 分钟）

环境：Windows 10/11 + Python 3.10+ + 嘉立创 EDA **专业版** V4（实测 4.1.78）+ 一个能执行本机命令的 AI 客户端（Claude Code / Codex 已实测）。

### 1. 安装工具链（CLI + daemon + 连接器）

从 [Releases](https://github.com/zsx3896926/EasyCirq/releases) 下载 `easycirq-toolchain-0.2.3.zip`，解压后执行：

```powershell
# 安装到默认目录 %LOCALAPPDATA%\EasyCirq
powershell -ExecutionPolicy Bypass -File .\Install-EasyCirq.ps1 install `
  -Bundle .\easycirq-toolchain-0.2.3.zip -InstallDir "$env:LOCALAPPDATA\EasyCirq"

# 把 easycirq 装进客户端（claude / codex 二选一，可重复执行）
powershell -ExecutionPolicy Bypass -File .\Install-EasyCirq.ps1 install `
  -Bundle .\easycirq-toolchain-0.2.3.zip -SkillClient codex

# 安装后自检：应显示 runtime 0.2.3；连接器未导入时 connector 会是 degraded（正常）
& "$env:LOCALAPPDATA\EasyCirq\bin\easycirq.exe" doctor
```

安装器**不会改 PATH**。要直接敲 `easycirq`，自行把 `%LOCALAPPDATA%\EasyCirq\bin` 加入用户 PATH；否则用绝对路径。

### 2. 在 EDA 里导入连接器（只需一次）

1. 完全关闭 EasyEDA Pro；
2. 重新打开 → **设置 → 扩展 → 导入扩展**，选择
   `%LOCALAPPDATA%\EasyCirq\connector\easycirq-connector_v0.1.3.eext`（`easycirq connector path` 可打印路径）；
3. 扩展管理器里找到 **「智构 · EasyCirq 连接器」**，打开并勾选 **「允许外部交互」**；
4. **完全退出并重启** EDA（扩展只在启动时加载）；
5. 验证：`easycirq doctor` 应显示 `verdict: ok`、`connector 0.1.3 connected`。

> 升级连接器时旧版本要卸载、导入新版本、重新授权并重启——新 uuid 的扩展不会继承旧权限。

### 3. 说需求

装好后直接对 AI 说"帮我画个 XX 板"，或复制下面这段（示例，不是已验证成品）：

```text
我完全不会 EDA，想做一个室内温度报警小板：
用 USB 供电，温度超过设定值时亮灯并发出声音，先做一块。
芯片、零件和实现方法请你推荐，优先考虑立创商城与嘉立创制造。

先运行 easycirq doctor 检查执行层，确认当前测试工程，然后在其中完成设计。
一般技术细节你查资料后决定，非关键细节采用容易实现的方案并简单说明。
只在缺少会影响功能、供电或尺寸的关键信息时问我，集中一次问清。

请实际绘制原理图并推进 PCB，检查、保存，告诉我工程和导出文件在哪里。
原理图按功能分区，文字不要遮挡，PCB 考虑实际装配与调试。
常规步骤检查后继续，不必反复问是否继续；购买、支付或生产下单前再让我确认。
```

### 过程中你会看到什么

| 阶段 | AI 应给你的真实结果 |
|---|---|
| 接通检查 | `easycirq doctor` / `capabilities` 的实际状态，读到哪个真实工程 |
| 方案与选型 | 简短方案、关键取舍、为什么这样选 |
| 画原理图 | 工程里出现真实器件与连线；保存、重开、回读核对 |
| 做 PCB | 真实板框/器件/走线/铺铜；原生 DRC 结果 |
| 检查与交付 | 六态证据（命令完成/回读/保存/重开/电气/质量）与导出文件 |
| 制作与实物 | 制造资料、BOM/坐标、测试计划；实物结果（未测会写 NOT RUN） |

这些是**可见进度点，不是每步都要你批准**。AI 能继续就继续，遇到真实卡点再说明。

## 换成你自己的想法

```text
做个打开抽屉就亮的灯，用电池，尽量省电。
我想测房间温湿度，显示在小屏幕上，放桌面用。
把当前原理图整理清楚，连接保持不变。
现有板子加一个接口，其他位置尽量别动。
本次只做原理图，先不画 PCB。
```

有现成设备、负载或电源时，把型号、铭牌照片或商品链接一起给 AI。不懂芯片、封装、层数没关系，这些由 AI 查资料决定。

## 卡住了，直接这样说

**AI 只给文字、没真的画进 EDA：**

```text
请先运行 easycirq doctor 确认连接器和工程，再读取目标工程；
需要真实回执；暂时不能写入时说明具体卡点，不要只在文字里画。
```

**AI 一直问芯片/封装/板层：**

```text
这些技术选择请你查资料并推荐，先用合理、容易实现的方案继续，
只问会影响实际使用、成本或尺寸的关键问题。
```

**报错或中断：**

```text
请先回读工程，判断哪些操作已完成，再修复并接着做；
不要重复创建器件或整页重画；需要我点界面时一次只给一步。
```

## 现在实际验证到了哪里

截至 2026-10-28，证据来自 Windows 11、嘉立创 EDA 专业版 4.1.78、自有 `easycirq` 0.2.3 + 连接器 0.1.3：

| 范围 | 结果 | 证据 |
|---|---|---|
| 真实握手与隔离 | doctor `ok`、1 窗口、旧 daemon 并存未使用 | `docs/toolchain-integration/evidence/m2/` |
| 读→移→存→重开→回读 | 六态 PASS，位移持久化、身份/pin-net 不变 | `evidence/m2/` |
| 小板原理图 | 9 器件、7 网一致、0 浮空、原生 DRC 0、`sch check` 0 finding | `evidence/gates/` |
| SCH→PCB→布线→铺铜→DRC | 布局 96–100 分、官方布线 6/6 网、PCB DRC **0** | `evidence/m4/pcb/` |
| 局部改板 | 仅目标器件变化，断线重布后 DRC 0 | `evidence/m4/pcb/local-edit-summary.json` |
| 导出与归档恢复 | BOM、原理图 SVG/PNG、PCB PNG、3D OBJ；`.epro2` 独立工程恢复后网表/板框一致、DRC 0 | `evidence/m4/` |
| G0–G6 门禁 | G0–G3、G5 PASS；G4 PASS_WITH_WAIVER；**G6 BLOCKED** | `docs/toolchain-integration/gate-review.md` |

**边界（如实，不随合并改变）**

- **Gerber / 钻孔 / CPL 仍需在 EDA GUI 手动导出**（本版本 typed 能力为 `gui_only`），所以 G6 未过、交付级别止于 **PCB 候选（DRC 0）**，不说"可打样"。
- **实物功能 NOT RUN**：PCB DRC 通过 ≠ 硬件上电通过；测试计划已写，实测项未执行。
- 高复杂度板卡、阻抗/等长、射频与高速数字未做通用能力保证。

## 项目结构

```text
easycirq/    设计方法 Skill（规则、门禁、参考、脚本）
runtime/            自有 Go 运行时（easycirq CLI + daemon；上游 easyeda-agent v1.15.0 维护分支）
connector/          自有 EDA 扩展（TypeScript，构建为 .eext）
protocol/           wire v1 协议与 JSON Schema
distribution/       统一安装器、发布构建、来源校验
tools/              验收、诊断、板级构建脚本
tests/              迁移守卫、CLI 与安装器用例
docs/               架构、能力矩阵、验收/门禁记录与全部证据
assets/brand/       logo（横版/方形，含原图）
```

## 开发者入口

```powershell
# 构建运行时与发布包
cd runtime; go build -o dist\easycirq.exe ./cmd/easycirq
cd ..; python distribution\build_release.py --output dist-v5

# 来源可复现（上游 v1.15.0 解包目录）
python distribution\verify_vendor.py --upstream <upstream-dir>

# 离线回归 / 安装器用例
# （生命周期测试默认把 JSONL 记账写临时目录，不修改工作树；刷新仓库证据见
#   docs/toolchain-integration/evidence/installer/README.md）
python tools\offline_suite.py
python -m pytest tests\test_install_lifecycle.py -q

# 门禁复核（需设计证据目录）
python "$env:USERPROFILE\.agents\skills\easycirq\scripts\gate_check.py" --help
```

- 交接与状态：[docs/handoff-current.md](docs/handoff-current.md)、[任务状态](docs/toolchain-integration/task-status.md)
- 架构/能力/验收/门禁：[docs/toolchain-integration/](docs/toolchain-integration/)
- 设计方法：[SKILL.md](easycirq/SKILL.md)、[references/eda-execution.md](easycirq/references/eda-execution.md)
- 欢迎 [Issue](https://github.com/zsx3896926/EasyCirq/issues) / PR，优先提供脱敏的实际任务与复现材料。

## 致谢与许可

EDA 执行层衍生自 [easyeda-agent](https://github.com/zhoushoujianwork/easyeda-agent)（MIT，作者 zhoushoujianwork 及贡献者），
来源锚点与逐文件哈希见 `third_party/easyeda-agent/UPSTREAM.json` 与 `runtime/PROVENANCE.md`。

本项目由作者独立维护，非嘉立创官方产品。自有内容采用 [Apache License 2.0](LICENSE)，
允许使用、修改与商业使用；外部工具、资料与商标遵循各自许可。`hw-eda-engineer` 等历史 Skill 已统一维护，不另作第三方致谢。
