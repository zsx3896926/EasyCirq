# 当前交接（智构 / 自有 EDA 工具链）

> 最后更新：2026-10-28 00:25（客户端已切换到智构单一入口）
> 状态真源：本文件 + `docs/toolchain-integration/task-status.md`；详细证据见
> `docs/toolchain-integration/evidence/`。历史（v1.0.1 发布恢复等）见 git 历史与
> `docs/releases/`。

## 目标与结果

把 EDA 执行层纳入本仓库：自有 CLI/daemon/Connector 可从本仓库构建、隔离安装、真实握手；
设计规则只由 `design-hardware` 一个 Skill 管理；安装/诊断/升级/回退统一入口。
**M0–M4 核心链已在 EasyEDA Pro 4.1.78 真机验收通过**（详见 task-status 与 acceptance-matrix）；
PR #36 已创建（草稿，未合并、未打标签、未发布）。

## 当前运行实例（真机）

| 组件 | 版本/位置 | 说明 |
| --- | --- | --- |
| 运行时（项目内） | `runtime/dist/zhigou.exe` 0.2.1-dev | 开发/构建用 |
| 运行时（已安装） | `%LOCALAPPDATA%\Zhigou\bin\zhigou.exe` 0.2.1 | 统一安装器安装，`zhigou doctor` = **ok** |
| daemon | pid 19464，`127.0.0.1:23111`，service `zhigou-agent` | 与旧 easyeda-agent（60832）并存、互不干扰 |
| Connector | `zhigou-connector 0.1.0`，uuid `a6e6b788…` | 已在 EasyEDA Pro 4.1.78 内导入并握手 |
| Skill | `design-hardware` **1.0.2** | 已装到 `.claude / .codex / .agents` 三处客户端目录 |
| 旧上游 Skill | 已停用（移出客户端，未删除） | 备份：`C:\Users\jlc\work\_skill-backups\zhigou-cutover-20261028\` |

客户端 skill 目录现状（已验证）：`design-hardware=1.0.2`、`easyeda-agent=absent`（三处一致）；
客户端 skill 目录中已只列出 `design-hardware`（描述指向 `zhigou` 执行层）。

## 分支与提交

- 工作树：`C:\Users\jlc\work\zhigou-toolchain`，分支 `feat/integrated-eda-toolchain`
- PR：<https://github.com/zsx3896926/hardware-design-skill/pull/36>（草稿）
- 构建产物 `dist-v2/` 已 gitignore；仓库内不留 15 MB 二进制

## 常用入口

```powershell
# 已安装版（推荐）
& "$env:LOCALAPPDATA\Zhigou\bin\zhigou.exe" doctor
& "$env:LOCALAPPDATA\Zhigou\bin\zhigou.exe" capabilities

# 开发版
& C:\Users\jlc\work\zhigou-toolchain\runtime\dist\zhigou.exe doctor

# 安装/升级/回退（统一入口；-Adopt 用于接管已有客户端 Skill）
distribution\Install-Zhigou.ps1 status
distribution\Install-Zhigou.ps1 install  -Bundle dist-v2\zhigou-toolchain-0.2.1.zip -Adopt
distribution\Install-Zhigou.ps1 upgrade  -Bundle <new>.zip
distribution\Install-Zhigou.ps1 rollback
```

## 已知边界（如实，不是掩盖）

- **Gerber/钻孔/CPL**：typed action 目录不存在 → `gui_only`，只能 EDA GUI 导出并落人工证据；未宣称。
- **PCB DRC 通过 ≠ 硬件上电通过**；实物功能 **NOT RUN**。
- DFM 剩 4 条 WARN（+5V/VIN 未铺铜、2 条电源线偏细）；3D 导出为 binding-only 覆盖。
- `PATH` 未修改（安装器设计）：需要直接敲 `zhigou` 时自行把 `%LOCALAPPDATA%\Zhigou\bin` 加入用户 PATH。
- 旧 `easyeda.exe` 与旧 daemon 保留未删（端口/服务名/扩展 uuid 均隔离）。

## 下一条具体操作

1. 若想命令行直接用 `zhigou`：把 `%LOCALAPPDATA%\Zhigou\bin` 加入用户 PATH（或继续用绝对路径）。
2. 需要正式合并/发版：审阅 PR #36 后由用户决定（不自动合并/发布）。
3. 新硬件任务：新开 AI 客户端会话，加载 `design-hardware`（1.0.2）；它会用
   `zhigou doctor` + `zhigou capabilities` 做开工预检，再按 M/S 流程推进。
