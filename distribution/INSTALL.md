# 智构 · EasyCirq 工具链 —— 安装说明

> 从旧名称升级：先看 [迁移说明](../docs/migration-easycirq.md)。

本目录（构建产物 `dist/`，或解压后的安装包）同时提供两种安装入口：

| 你想装什么 | 入口 | 对应产物 |
|---|---|---|
| **完整工具链**：Skill（easycirq）+ 运行时（`easycirq.exe`）+ 连接器（`.eext`） | `Install-EasyCirq.cmd` / `Install-EasyCirq.ps1` | `easycirq-toolchain-<版本>.zip` |
| 只安装 / 只更新 Skill | `Manage-Skill.cmd` / `Manage-Skill.ps1` | `easycirq-<版本>.zip` |

两条路径可以共存，但**不要对同一个 Skill 目录同时操作**。

要求：Windows 10/11 + Python 3.10+。请**完整解压整个文件夹**后再运行（不要在压缩包预览里直接双击）。

---

## A. 安装完整工具链（推荐）

1. 双击 `Install-EasyCirq.cmd`。
2. 选 `1`（安装或升级）。安装器会自动在同目录查找 `easycirq-toolchain-<版本>.zip`，并用 `toolchain-release.json` 校验它。
3. 看到 `"status": "installed"`（首次）或 `"status": "upgraded"` 即完成。
4. **人工导入连接器**（安装器不会自动做，也不修改 EasyEDA 的任何状态）：
   - 打开安装目录（默认 `%LOCALAPPDATA%\EasyCirq`）下的 `connector\IMPORT-STEPS.md`；
   - EasyEDA Pro → 设置 → 扩展 → 已安装 → 导入扩展 → 选择 `connector\easycirq-connector_<版本>.eext`；
   - 在扩展设置中允许外部交互；
   - **完全退出 EasyEDA Pro 并重新启动**（连接器在启动时加载，不支持热加载）。
5. 自检：

   ```powershell
   & "$env:LOCALAPPDATA\EasyCirq\bin\easycirq.exe" doctor
   ```

   `verdict: ok` 表示宿主可达；`degraded` 表示 daemon 未运行或连接器未连接——**这不是安装失败**。

命令行等价用法：

```powershell
.\Install-EasyCirq.ps1 install        # 安装/升级（同一条幂等路径）
.\Install-EasyCirq.ps1 status         # 状态 + 文件校验 + PATH 影子检测 + 遗留目录观测
.\Install-EasyCirq.ps1 verify         # 只校验文件哈希
.\Install-EasyCirq.ps1 rollback       # 回退到上一次备份（-To <版本> 指定）
.\Install-EasyCirq.ps1 uninstall      # 卸载（默认保留用户 config/ 与备份）
.\Install-EasyCirq.ps1 inspect-bundle -Bundle .\easycirq-toolchain-0.2.0.zip
```

常用参数：`-InstallDir <目录>`、`-StateDir <目录>`、`-SkillClient claude|codex|agents`（额外把 Skill 复制进客户端目录；默认只装进安装目录）、`-Force`（先备份再覆盖本地修改）、`-DryRun`。

**行为承诺**：不写入既有 easyeda-agent 目录；不修改 PATH；不删除旧 Skill；不自动导入 EDA 扩展；不启动/停止 daemon 或 EasyEDA；升级先备份、失败自动回退；卸载只删自己记录的文件。

---

## B. 只安装 / 更新 Skill（旧路径，保持兼容）

1. 双击 `Manage-Skill.cmd`。
2. 选 `1`（安装）或 `3`（升级），再选客户端：`1` Claude Code / `2` Codex / `3` WorkBuddy。
3. 升级前会整目录备份；本地修改受保护；回退用菜单 `5`。

命令行：

```powershell
python skill_update.py install --client claude --package easycirq-<版本>.zip --manifest release.json
python skill_update.py status  --client claude
python skill_update.py rollback --client claude
```

对已有的手工安装（没有 `.install.json`）需要显式 `--adopt` 才会备份并接管。切换文件后需在客户端重新加载 Skill 或开新会话——文件清单健康**不能**证明客户端已加载或 EDA 已连通。

---

## C. 校验下载 / 拷贝的文件

`SHA256SUMS` 覆盖本目录所有产物；安装包内的 `toolchain-release.json` 绑定 bundle 的 SHA-256、版本与兼容矩阵（CLI / 运行时 / daemon / 连接器 / 协议 / EDA 版本）。安装器在写入前逐项校验，损坏或被改动的包会被拒绝，且不会留下半安装状态。

哈希只能发现损坏或错版，**不是发布者签名**。

---

## D. 排障（最常见的三条）

| 现象 | 处理 |
|---|---|
| `Python 3.10+ required` | 安装 Python 3.10+ 后重开窗口 |
| `未找到安装包` / `An install needs --bundle` | 把 `easycirq-toolchain-<版本>.zip` 放回本目录，或用 `-Bundle` 指定完整路径 |
| doctor 显示 `degraded` | 不是安装失败：启动 daemon，或在 EasyEDA 导入连接器后完全重启 EDA |

完整故障速查表见仓库 `docs/toolchain-integration/installer.md` 第 10 节。

---

本工具链为独立维护项目，非嘉立创官方产品。Apache License 2.0，见 `LICENSE`；第三方组件许可见 `NOTICE` 与安装目录下 `licenses/THIRD-PARTY-NOTICES.md`。EasyEDA Pro 本体不随本工具链分发。
