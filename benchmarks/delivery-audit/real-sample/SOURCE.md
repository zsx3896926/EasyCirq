# 真实样本（real sample）来源、许可与只读回放记录

> 样本目录：`benchmarks/delivery-audit/real-sample/`。本文件是**该目录唯一的说明文件**，目录内的
> `gerber/*` 与 `LICENSE-APACHE-2.0.txt` 是上游文件的**逐字节副本**：没有做任何内容修改、没有添加
> 头部注释、没有改换行、没有重命名上游文件（仅按上游原名放入 `gerber/` 扁平目录）。
> 检索日期：2026-10-27。基线：`docs/parallel-delivery-audit/contract.md`。

## 1. 结论

- **真实样本：FOUND（已找到并收录）**——一套 2 层板的 Gerber + Excellon 钻孔导出，来自 Apache-2.0 的
  `curtacircuitos/pcb-tools` 仓库测试资源，按 commit 固定下载。
- **BOM/CPL：NOT RUN（未找到可合法再分发的真实 BOM+CPL 导出）**。原因见 §7；BOM/CPL 的能力证据仍只来自
  本仓库的合成夹具与单元测试，**不能**把本样本当作 BOM/CPL 的真实证据。
- **样本本身不是制造证据**：它只用于“只读回放/回归”验证解析边界；**不**证明设计正确、可制造、可贴装，
  也**不**绑定导出它的 EDA 工程或 revision。

## 2. 上游仓库与固定版本

| 项目 | 值 |
|---|---|
| 仓库 | `curtacircuitos/pcb-tools`（Python 的 Gerber/Excellon 工具库；维护者已声明停止维护） |
| 仓库页面 | https://github.com/curtacircuitos/pcb-tools |
| 固定 commit | `ea7cf0018788f9712379007358600922f188bfb5`（master HEAD；提交时间 2024-06-19T21:21:12Z；GitHub 显示 PGP 签名已验证） |
| 提交页 | https://github.com/curtacircuitos/pcb-tools/commit/ea7cf0018788f9712379007358600922f188bfb5 |
| 样本在上游的路径 | `gerber/tests/resources/` |
| 本次获取方式 | `Invoke-WebRequest` 直接取 `raw.githubusercontent.com` 的**commit 固定** URL；未 clone 仓库、未执行仓库内任何脚本、未调用 EDA |
| 检索日期 | 2026-10-27 |

## 3. 许可（已核对 LICENSE 正文，不是只看徽章）

- 上游许可证：**Apache License, Version 2.0**。
- 许可证文件（上游，commit 固定）：
  https://raw.githubusercontent.com/curtacircuitos/pcb-tools/ea7cf0018788f9712379007358600922f188bfb5/LICENSE
- 许可证文件（本仓库副本，逐字节）：
  [`LICENSE-APACHE-2.0.txt`](LICENSE-APACHE-2.0.txt)
  - sha256：`cb5e8e7e5f4a3988e1063c142c60dc2df75605f4c46515e776e3aca6df976e14`
  - 大小：11,325 bytes
  - 正文开头：`Apache License / Version 2.0, January 2004 / http://www.apache.org/licenses/`
  - 与上游 `master` 的 `LICENSE`（2026-10-27 打开）逐字节一致。
- 上游仓库**没有** `NOTICE` 文件（commit 树中不存在），因此没有额外 NOTICE 需要随附。
- 上游文件**没有**逐文件版权头；仓库级 `LICENSE` 是唯一的许可声明。源代码文件头中的版权行为
  “Copyright 2016 Hamilton Kibbe” 及贡献者，样本数据文件本身没有单独版权行。
- 本仓库的合规处理：**Apache-2.0 §4(a)**——已随样本附上许可证副本；**§4(b)**——未修改文件，故无需变更声明；
  **§4(c)**——未删除任何版权/许可声明（上游数据文件本身没有）；**§4(d)**——无 NOTICE。
- **许可范围的重要限制**：我们只核对到“仓库以 Apache-2.0 发布这些仓库内容”。样本的**板级设计本身**
  （谁画的、EDA 工程、原始 revision、是否另有第三方权利）上游**没有文档说明**。因此本仓库**不声称**
  “该板设计是 Apache-2.0 作品”，只声称“按上游仓库的 Apache-2.0 许可、在未修改的前提下再分发这些文件”。
  若下游需要板设计本身的授权，须向 GitHub 仓库维护者/原作者确认。
- 本样本**不是** Ucamco 测试文件：Ucamco 规范与测试文件的版权为 all rights reserved（见
  `../../docs/parallel-delivery-audit/source-register.md` 的 FMT-S01/S02），本次**未**使用。

## 4. 样本是什么（可证实与不可证实）

**可证实（来自文件内容）**：

- 一套 **2 层板**的制造数据：2 个铜层（`GTL/GBL`）、2 个阻焊（`GTS/GBS`）、2 个丝印（`GTO/GBO`）、
  1 个板框（`GKO`）、1 个钻孔文件（`DRD`）。没有 paste 层、没有 BOM/CPL、没有装配图。
- 导出风格：**Eagle（Autodesk Eagle / EAGLE CAM）风格**，证据是每个 Gerber 的固定头部：
  `G75*`、`%MOIN*%`（英制）、`%OFA0B0*%`（图像偏移）、`%FSLAX24Y24*%`（2 位整数 + **4 位小数**，旧式
  零省略格式）、`%IPPOS*%`、`%LPD*%`，并包含一个 `%AMOC8*` 光圈宏定义；钻孔文件为
  `%\nM48\nM72\nT01C0.0236 ...`，工具直径单位 inch。这是**内容推断**，上游没有写明 EDA 名称/版本。
- 观测几何（只读解析结果，仅作描述）：路径范围约 **x 0.761–58.092 mm，y 7.781–45.884 mm**
  （约 57.3 × 38.1 mm）；单位为 inch；钻孔 5 把刀，整数坐标（2.4 风格、无 FORMAT 声明）。
- 板名/项目名/revision：**未知**（上游只叫 `gerber/tests/resources`，没有 README 说明板子来源）。

**不可证实（不得写成已验证）**：

- 该板设计是 Apache-2.0 作品（见 §3 限制）。
- 导出该文件的 EDA 工程、导出时间、设计 revision、层叠/铜厚/工艺。
- 文件之间“属于同一次导出会话”——虽然目录内文件尺寸/坐标互相吻合，但本工具**不**声称能证明同源。

## 5. 文件清单与哈希（sha256）

所有文件均为**上游原始字节**（`raw.githubusercontent.com`，commit 固定）。`sha256` 由本机
`Get-FileHash -Algorithm SHA256` 计算。链接即**精确下载 URL**。

| 本地路径 | 上游路径 | 大小 (bytes) | sha256 | 观测角色/内容 |
|---|---|---:|---|---|
| `gerber/top_copper.GTL` | `gerber/tests/resources/top_copper.GTL` | 61,967 | `4924d18d6a11bced130af863dea1959e258ada4b43133dbe36ba304218fbe9ea` | 顶层铜（2 层板） |
| `gerber/bottom_copper.GBL` | `gerber/tests/resources/bottom_copper.GBL` | 34,186 | `e04bc50815a8e3830b396dbd7d9a968b1cdee7ccd19f61b5bf1a40c1121de4b7` | 底层铜 |
| `gerber/top_mask.GTS` | `gerber/tests/resources/top_mask.GTS` | 2,804 | `02b1ca99957791aaf3cee5865e885ce2f66968ffaf97b6b4df0cba60f287c4f8` | 顶层阻焊 |
| `gerber/bottom_mask.GBS` | `gerber/tests/resources/bottom_mask.GBS` | 1,079 | `39f918af62b7494ee088e07af5fa7c3ba409a0d6602dbc6a4e1f444ba0c7c858` | 底层阻焊 |
| `gerber/top_silk.GTO` | `gerber/tests/resources/top_silk.GTO` | 39,608 | `5ab126aef40eac6906f1a0f177de52a749941e73105577545fe73e05e902e2c7` | 顶层丝印 |
| `gerber/bottom_silk.GBO` | `gerber/tests/resources/bottom_silk.GBO` | 112,787 | `85d45eb5ef4976dbe7382a867ff561db42a7d6bdead944e0237df7aff676012c` | 底层丝印 |
| `gerber/board_outline.GKO` | `gerber/tests/resources/board_outline.GKO` | 9,430 | `01b4f8e99740decd019ee72b9a621d63f131f00fa5b5b6cb91b6d556af2d0d3b` | 板框（线性轮廓） |
| `gerber/ncdrill.DRD` | `gerber/tests/resources/ncdrill.DRD` | 532 | `f791b4e380083a9d449113c18390813e08dc90c0a678265409ae73b1fb200368` | Excellon 钻孔（M48/M72/%） |
| `LICENSE-APACHE-2.0.txt` | `LICENSE`（同一 commit） | 11,325 | `cb5e8e7e5f4a3988e1063c142c60dc2df75605f4c46515e776e3aca6df976e14` | 上游许可证副本 |

- 数据文件合计：**262,393 bytes**（8 个文件，< 500 KB 限制）；含许可证合计 **273,718 bytes**。
- 精确下载 URL 模式（逐文件把 `<NAME>` 替换为上表“上游路径”列的文件名）：
  `https://raw.githubusercontent.com/curtacircuitos/pcb-tools/ea7cf0018788f9712379007358600922f188bfb5/gerber/tests/resources/<NAME>`
  （本文件所有哈希与字节数均对应 §2 的这个 commit；本次未 clone 仓库。）
- 复核命令（任意 shell/PS 均可）：
  `Get-FileHash -Algorithm SHA256 benchmarks\delivery-audit\real-sample\gerber\*.GTL` 等；
  或对目录逐个比对 §5 表格。

## 6. 只读回放记录（修复后复核；不是 CLI 声明，不是制造结论）

2026-10-27，用本仓库 `easycirq/scripts/delivery_audit/` 的 `gerber.parse_gerber` 与
`drill.parse_drill` **在只读方式**下解析上述 8 个数据文件（未写任何输入文件、未修改样本、未调用 CLI，
因此本文件**不**声称运行过 `python -m delivery_audit`）。以下为**实现修复后的复核结果**——它们是
**解析器 findings**，说明“本工具在真实 Eagle 文件上会看到什么”，不能反过来当作“样本无效”或“设计有问题”：

| 文件 | 解析状态 | 主要 finding / facts | 备注 |
|---|---|---|---|
| `top_copper.GTL` / `bottom_copper.GBL` / `top_silk.GTO` / `bottom_silk.GBO` / `board_outline.GKO` | unknown | `gerber.unsupported.image_parameter:unknown`（`%OF`）、`gerber.unsupported.macro:unknown`（`%AMOC8`） | 零尺寸 C 光圈已正常接受；`contours_exact=false`；图元数分别为 2,616 / 1,407 / 1,934 / 5,612 / 481 |
| `top_mask.GTS` / `bottom_mask.GBS` | unknown | 同上两项 unknown（无零尺寸 C 光圈项） | 110 / 36 个图元 |
| `ncdrill.DRD` | unknown | `drill.coordinate_unknown_format:unknown` | 读出 **5 把刀 / 36 孔 / inch**；整数坐标无 digit format → extent 不计算（符合契约“不猜”） |

**修复前后（历史记录）**：同一天的首轮回放（修复前）曾在该样本上暴露两个**实现问题**：

1. 5 个 Gerber 因 `%ADD10C,0.0000`（零尺寸 C 光圈）被判 `gerber.aperture_undefined:fail`；
2. `ncdrill.DRD` 因首行 `%` 在 `M48` 之前被判 `drill.header_missing:fail`。

这两个问题已由实现负责人修复（Gerber 规范 §4.3.1 允许零直径 C 光圈；Eagle 导出以 `%` 行开头），
修复后复跑 fail 消失、只剩契约明确声明的 unknown；`docs/parallel-delivery-audit/report.md` §8 记录了
该修复，基准 28 的期望已重新冻结。→ 这段历史说明本样本有真实回归价值，**不是**样本内容有问题。
`source-register.md` §4 与 `format-support.md` §10/§11 也记录了同一过程。

## 7. 为什么没有 BOM/CPL（NOT RUN 的具体原因）

- 检索目标要求“可合法再分发 + 有明确许可 + 真实 BOM/CPL 导出 + 体积可控”。2026-10-27 本次核对到的
  含 BOM/CPL 的真实工程，要么没有任何许可声明，要么是 CC BY-SA/GPL 硬件工程（不符合
  “MIT/BSD/Apache/CC0/public domain” 的许可范围），要么是 JLC 平台示例（页面版权保留，不可打包）。
- 因此：**没有收录 BOM/CPL**，也不伪造一份。`bom.py`/`cpl.py`/`assembly.py` 的证据仍只来自
  `benchmarks/delivery-audit/fixtures/` 的合成夹具与单元测试；真实 BOM/CPL 回放应作为后续工作
  （需要先找到许可清晰、可再分发的真实导出，并记录同样的 SOURCE.md 字段）。
- 嘉立创的字段规则只用于**限定 CSV 范围**（`source-register.md` 的 MFG-S05/S06），不是样本来源。

## 8. 明确不声称（non-claims）

- 不声称样本来自某个 EDA 工程/revision；不声称同源；不声称是“官方样例”。
- 不声称板可制造、可贴装、DFM/阻抗/电气/装配通过；不声称 Gerber/钻孔语义完整。
- 不声称解析器在真实文件上的 `fail/unknown` 等于文件错误（见 §6；首轮的两处 fail 属解析器边界，已修复）。
- 不声称 Ucamco 或任何第三方为本样本背书；`Gerber` 是 Ucamco 的注册商标，仅作格式名使用。
- 不声称已运行 delivery-audit CLI；本文件只记录 parser 级只读解析与内存诊断。
