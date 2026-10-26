# Skill 更新机制交付（2026-10-26）

## 实现

版本 0.8.0，基于 main eef9a1b 的 0.7.0（保留并行诊断修复）。

- `design-hardware/scripts/skill_update.py`：托管安装、稳定版检查/升级、修复、回退、恢复、包构建、交互菜单。
- `distribution/Manage-Skill.cmd`：Windows 双击入口，验证 Python 运行时后启动；不依赖 PowerShell 脚本策略。
- `distribution/Manage-Skill.ps1`：允许 PowerShell 脚本时的参数化入口。
- `distribution/build_release.py`：生成 391 文件 Skill ZIP、逐文件清单与独立安装器 ZIP。
- `.github/workflows/skill-updater.yml`：Windows/Linux + Python 3.10 更新器测试与构建；正式 Release 事件附加资产。
- Skill 路由、安装教程、README、CHANGELOG 与版本同步。

## 已实际验证

- 更新器专项 35 tests OK；包括真实 Windows CMD 启动，带空格路径与中文菜单校验。
- 全量回归：785 tests OK（Windows / Python 3.13）；更新器专项 35 tests OK。CI 另验 Windows/Linux / Python 3.10。
- 完整 0.7.0 旧目录分别放入隔离 Claude / Codex 旧目录 / WorkBuddy 根目录：
  备份迁移到 0.8.0、逐文件校验、安装版 selftest、回退到 0.7.0 均通过。
- 客户工程哨兵文件逐字节保留；未修改用户实际客户端安装或 EDA 工程。
- 完整接受记录：`docs/evidence/skill-updater/acceptance.json`。
- 损坏 ZIP、哈希不匹配、额外文件、路径穿越、Windows 保留名、符号链接、同版本换内容、
  降级、本地修改、并发锁、切换失败、中断恢复、缓存到期、网络失败均有回归。
- 备份与暂存位于客户端 skills 扫描根目录之外，避免产生重复技能。

## 实测修复的问题

- Windows 的进程存在性检查改用只读系统接口，不使用 POSIX 的 signal-0 方式。
- 本机 PowerShell 策略阻止未签名脚本，主入口改为直接调用 Python，未修改执行策略。
- 本机存在无有效运行时的 py 启动器，入口改为验证后依次选择 py / python3 / python。
- 修复检查缓存命中会无限延长 TTL 的问题；更新动作不信任缓存下载 URL。
- CMD 路径包含空格的真实启动纳入回归。

## 尚未验证/发布边界

- 当前仓库尚无正式 Release；未打标签、未创建 Release。线上检查会保留安装并明确报错，
  需要维护者正式发布带资产的稳定版本后才对客户启用。
- 本机直接 Python 网络请求受到 DNS 限制；真实联网下载全链路 BLOCKED，
  已测试真实离线 ZIP 生命周期与网络响应协议 fixture，不能将 fixture 当线上下载实测。
- Claude/Codex/WorkBuddy GUI 发现新版 NOT RUN；本轮验证的是实际文件和 CLI，不冒充 GUI 加载。
- 不后台通知、不自动安装；需要 Python 3.10+。客户首次迁移一次后，才能使用 Skill 内更新入口。
- SHA256 是完整性校验，不是发布者数字签名；信任边界是仓库发布账户与 HTTPS。

## 发布者接续

合并并验证本轮 PR 后，创建与 `.version` 一致的稳定 Release（v0.8.0）。
等待资产工作流通过并核对 release.json / Skill ZIP / installer ZIP 后，再发给客户。
已经有的手动安装先从独立安装器选择备份迁移；后续通过 Agent 在空闲时检查和升级。
