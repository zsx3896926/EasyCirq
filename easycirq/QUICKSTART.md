# 快速上手 · 智构 · EasyCirq

> **10 分钟，从「装好了」到「AI 按工程纪律开始画板」。**
> 本页只讲 Skill 怎么用起来；执行层（`easycirq` CLI）的安装、升级、卸载见仓库 [README](../README.md) 与 [安装说明](../distribution/INSTALL.md)。（`../` 是仓库内路径；Skill 装进客户端后这些链接指不到，回仓库看。）
>
> 本文的命令与输出在 **Windows + easycirq 1.3.83 + EasyEDA Pro 4.1.78** 上实跑（2026-11-04）。标「实测」的是照抄的真实输出；没标的表示本次未跑，别当成已验证。

## 0. 两句话看懂它是什么

| 层 | 是什么 | 你要做什么 |
|---|---|---|
| **Skill（本目录）** | 工程方法与纪律：澄清需求、选型、计算、G0–G6 门禁、证据口径、交付话术 | 让 AI 读它 |
| **执行层（`easycirq`）** | CLI + daemon + 连接器，真正读写嘉立创 EDA 里的工程 | 装一次 |

- **只有 Skill、没有执行层**：能出方案、算式、检查清单，碰不到你的工程文件（它会明确标 `NOT RUN`，不会假装画完）。
- **只有执行层、没有 Skill**：能改工程，但没有工程纪律——那不是本项目的用法。

Skill 有两套模式，开工第一句就定：

| 模式 | 触发 | 预算与流程 |
|---|---|---|
| **咨询模式** | 问答、选型、快速检查、只要结论或计划 | 输出优先契约 R0–R12（≤4 次工具调用），见 [SKILL.md](SKILL.md) |
| **施工模式** | 「做出来 / 改完 / 跑通 / 落地」，或需要真机写入、多轮迭代、交付图纸 | 施工模式契约 B0–B10，见 [施工模式契约](references/build-mode.md) |

## 1. 三步到位（约 3 分钟）

```powershell
# 1) 装执行层（一次）—— 细节见 README「快速开始」
powershell -ExecutionPolicy Bypass -File .\Install-EasyCirq.ps1 install `
  -Bundle .\easycirq-toolchain-<版本>.zip -InstallDir "$env:LOCALAPPDATA\EasyCirq"

# 2) 把 Skill 装进你的 AI 客户端（claude / codex，可重复执行）
powershell -ExecutionPolicy Bypass -File .\Install-EasyCirq.ps1 install `
  -Bundle .\easycirq-toolchain-<版本>.zip -SkillClient codex

# 3) 自检：五行情表，退出码 0=就绪，2=未就绪
easycirq setup
```

第 3 步实测输出：

```text
EasyCirq 安装检查

  ✓ 软件             easycirq 1.3.83
  ✓ 后台运行           运行中
  ✓ EasyEDA        已连接（EasyEDA Pro 4.1.78）
  ✓ 技能             已装入
  - 企业知识库          未配置（可选；运行 easycirq enterprise ls 了解怎么开始）

一切就绪。下一步：说清你要做什么板子，或者运行 easycirq status 看当前状态。
```

装完 **重载或新开一个会话**，让客户端重新读 Skill 目录；同一会话里改文件不一定立刻生效。

## 2. 第一句话怎么说（决定后面 90% 的体验）

模板：

> **做一块什么板 + 给谁用 / 什么场景 + 硬约束（输入电源、接口、尺寸、成本、批量）+ 要的产物（原理图 / PCB / BOM / 打样文件）**

三种能直接开工的开场：

| 场景 | 可以这么说 |
|---|---|
| 新手（不会 EDA） | 「我要一个 5V 供电的温度报警器，超 40℃ 蜂鸣器响，插 USB 供电就行。我不会用 EDA，你带我做完，最后给我原理图和 PCB。」 |
| 工程师（带约束） | 「12–24V 输入、5V/2A 输出的降压板，带反接保护和 TVS，尺寸压到 40×30mm，用嘉立创 SMT 贴片。先出方案再画。」 |
| 改板 / 检查 | 「这个工程 DRC 报 3 处网络未连接，我不想重画，先告诉我哪几处、优先级怎么排，再改。」 |

不会被接受的问法：**「帮我画个板子」**。这不是刁难——缺上下文时任何方案都是猜的。Skill 会先反问 3–5 个关键问题（供电源、接口、尺寸、成本、要不要贴片），答完才动手。

## 3. 不接 EDA 也能先跑通（3 分钟）

哪怕是纯计算，也走同一套口径：算完的东西不是板子。实测一个 LDO 的压差与耗散：

```powershell
python easycirq/scripts/calculate.py ldo '{"vin_min_V":4.5,"vin_max_V":5.5,"vout_min_V":3.23,"vout_max_V":3.37,"iout_max_A":0.2,"iq_max_A":0.00001,"dropout_max_V":0.3}'
```

实测输出（截取关键字段）：

```json
{
  "status": "calculated",
  "board_verified": false,
  "dropout_margin_min_V": 0.83,
  "dissipation_estimate_max_W": 0.454,
  "assumptions": "Bounded DC regulated model; no dynamic/current-limit/stability/reverse-current/thermal validation."
}
```

**看 `board_verified: false`。** 算式通过 ≠ 板子通过；同一个工具也覆盖 `led` / `divider` / `i2c` / `buck` / `boost` / `adc_settle` / `current_sense` / `wire`。功耗与续航另走 `python easycirq/scripts/power_budget.py budget.json`。

## 4. 接上 EDA 的最小闭环

预检 → 绑定目标 → 先读后写 → 写 → 保存重开 → 回读。少任何一步，"成功"都只是命令没报错：

```text
easycirq doctor && easycirq capabilities          # 1 预检：非零退出就停
easycirq project create --name "温度报警器" --open  # 2 新工程（独立，不覆盖别人的）
easycirq doc ls                                  # 3 拿页面 / PCB 的 UUID
easycirq doc open <页面名或UUID>                  # 4 必须有活动文档才能写
easycirq sch list --include-pins                 # 5 先读一次，确认目标（空页也要读）
...                                              # 6 放置 / 连线 / 检查
easycirq sch save && easycirq doc reload <页面>   # 7 保存后重开，再回读验证持久化
```

两个必踩的坑，先知道能省半小时：

- **`No active document`**：新建工程后默认没有活动文档，跳过第 4 步直接写就会报这个。这不是工具坏了，是目标没绑定。
- **连接器没导入**：`doctor` 报 connector 未就绪时，跑 `easycirq connector install-steps`，在 EDA 里一次性完成导入和「允许外部交互」，重启 EDA 再跑 `doctor`。不要用截图或 JSON 冒充"已连接"。

进度与验收用两条命令看，都不要自己发明口径：

```text
easycirq sch status     # S1–S6 每一格当场从画布算出来（✓ done / ◐ partial / ○ todo / ? unknown）
easycirq sch gate       # 一次固定顺序跑完 layout-lint → check → bridge-check → drc，出一个判决
```

## 5. 为什么它不会跳步：门禁只认 `pass`

`sch status` 能**检测**到哪一步，但检不出"你还没到这一步就往下跑"。`easycirq phase` 补的是强制那一半：

```text
easycirq phase show    --project <uuid>   # 当前相位 + 每相位证据状态
easycirq phase run S5  --project <uuid>   # 跑该相位的门，记证据
easycirq phase advance --project <uuid>   # 前置不是 pass 就拒绝推进
easycirq phase set S6  --project <uuid>   # 强制设置（记为 override，留痕）
```

| 状态 | 含义 | 放行？ |
|---|---|---|
| `pass` | 门通过了 | **是**（唯一放行） |
| `fail` | 板子有问题 | 否 |
| `blocked` | **检查器没跑成**（连接器掉线、页面没开） | 否 |
| `pending` | 有门但没跑（NOT RUN） | 否 |
| `stale` | 跑过了，但板子改了（按文档哈希判失效） | 否 |
| `unenforced` | 这个相位还没接门 | 否，但必须显式标出 |

目前只强制 S5（`sch gate`）一个转换，其余相位标 `unenforced`——**刻意只接一个**，分错相位会让正常做板被卡住，那比没有强制更糟。细节见 [相位与证据](references/phase-gate.md)。

最后一道"能不能下单"，用一张卡回答，缺证据会和真缺陷分开列：

```text
easycirq card                                  # 只读最近一次离线 KPI 报告 + 写权限，不重新测量
easycirq card --pcb-drc <easycirq pcb drc --json 的输出>   # 加上板子那一半
```

## 6. 五个常见坑

| 症状 | 真实原因 | 怎么处理 |
|---|---|---|
| 让 AI 画板，它先问一堆问题 | 缺约束，方案只能猜 | 按 §2 的模板一次性给全；答完它才动手，这是纪律不是拖延 |
| `No active document` | 目标未绑定 | `doc ls` → `doc open <页面>`，写入时再带 `--doc` |
| 说"已完成"，但 EDA 里没变化 | 命令成功 ≠ 已落盘 | 只认 `save` → `reload` → 回读三件事都成立 |
| `blocked` 被当成"板子坏了" | 三态混读 | `blocked` 是检查器没跑成；修环境重跑，不是改板 |
| 板子改了一版，旧结论还在用 | 证据按文档哈希失效 | 看 `phase show` 是否已变 `stale`，`stale` 一律重跑 |

另外：Windows 控制台默认 GBK/CP936 时，`easycirq phase --help` 的中文帮助会乱码（本次实测，`chcp 65001` 不解决）。要读帮助就用 `--json`，或 `$env:PYTHONUTF8=1; python -X utf8 easycirq/scripts/phase.py --help`。

## 7. 想深入读哪

| 你想干的事 | 先读这一篇 |
|---|---|
| 选型、供电、接口、成本先拍板 | [从想法到产品](references/idea-to-product.md) |
| 真机画原理图、排版、看图像验收 | [绘图执行方法](references/schematic-authoring.md)、[原理图排版](references/schematic-layout.md) |
| PCB 顺序、布线、DRC 归零 | [PCB 执行](references/pcb.md)、[4 层板闭环](references/pcb-4layer-closure.md) |
| 让 AI 别跳步、别把没跑的说成跑过 | [施工模式契约](references/build-mode.md)、[证据与工程记录](references/evidence.md) |
| 企业：查网表、沉淀人审经验、从历史 DRC 挖规则 | [本地交付说明](references/enterprise-local.md)、[企业知识库](references/enterprise-knowledge.md) |
| 装完命令跑不了 / 客户机器没 Python | [自带 Python](references/bundled-python.md)、[故障排查](references/troubleshooting.md) |

## 8. 版本与更新

- `easycirq/.version` 是 **Skill 版本**；`easycirq version` 是**执行层版本**。两者不要求相等，各自升级、各自核对。
- 查 Skill：`easycirq skill status`；升级已装的 Skill：`easycirq skill sync`（可 `--version` 钉版本）；连 CLI 一起升级：`easycirq update`。
- 变更记录看 [CHANGELOG.md](CHANGELOG.md)。
- **升级前**：不要在画板中途替换技能；升级后重载会话，并重跑 `easycirq setup` 与 `easycirq doctor`。
