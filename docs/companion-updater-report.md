# easyeda-agent 联动更新（0.8.1）

用户要求本 Skill 的更新机制同时覆盖负责实际执行的 easyeda-agent。本轮在 main 0.8.0
（9f237b8）基础上增加官方更新器协调层，不修改第三方仓库、EDA 工程或客户真实安装。

## 行为

- 原“检查更新”入口同时报告本 Skill 与 easyeda-agent CLI / Skill / daemon / Connector。
- 两套查询独立；本 Skill 尚无正式 Release 不会遮住执行器的状态。
- 新增 `update-agent --client ... --idle`，委托官方更新器，不重复实现第三方下载/安装器。
- 预检固定稳定目标版本，当前 CLI 与客户端 Skill 整目录先备份，保存 operation.json，升级后重查。
- 当前客户端分别路由；WorkBuddy 通过官方 CLAUDE_CONFIG_DIR 子进程配置能力映射到自己的目录。
- 不自动重启 daemon、不自动导入 Connector；未知或不匹配不能显示整套已更新。
- 两个协调器客户端共享二进制锁；运行时升级部分成功返回非零退出码并保留现场。
- 本 Skill rollback 不回退第三方执行器，不声称跨组件原子回退；没有经过硬件流程的任意新版本兼容性仍未验证。

## 核对依据

实际运行本机 easyeda-agent v1.14.0：`--version`、`update --help`、`skill --help`、
`skill sync --help`。另核对上游 README、docs/quick-start.md 和 internal/app/cmd_update.go。
上游：https://github.com/zhoushoujianwork/easyeda-agent 。

## 验证

- 本地全量 805 tests OK；新增 18 项伴随执行器测试，之前 37 项更新器测试保留。
- 覆盖：原生只读检查/不自动启动、退出 10、网络失败、未知状态、Connector 手动步骤、
  WorkBuddy 配置映射、Codex 重复安装、空闲要求、备份与固定目标、执行后检查、超时、
  部分失败、共享 CLI 锁，以及本 Skill 的查询失败不能遮住执行器。
- 发布包现在包含 392 个 Skill 文件，独立安装器也携带 companion_update.py。
- 真实统一只读检查记录：docs/evidence/companion-update/read-only-check.json。
  本机 DNS 限制导致两侧 unverified，未把它误报为已是最新版。
- 官方依赖升级应用与 WorkBuddy GUI 发现 NOT RUN；升级测试使用原生返回结构的 fixture，
  不冒充实际下载安装。未更新用户 easyeda.exe、未重启 daemon、未导入 Connector。
- Windows/Linux CI 对两组更新器测试及安装器构建进行复核；结果以本轮 PR 为准。

## 用户入口

双击管理器：菜单 2 统一检查，菜单 3 升级本 Skill，菜单 8 升级 EDA 执行器。
也可以直接让 Agent“把画板搭档和 EDA 执行器一起检查/更新”，Agent 代执行步骤。
版本 0.8.1 仍需合并并正式发布，旧用户不会因代码推送自动更新。
