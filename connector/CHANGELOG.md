# Changelog

本文件记录「智构 · EasyCirq 连接器」的版本更新情况。

## [1.0.7] - 2026-10-28

- 演示素材重做：用 easycirq 重新新建工程绘制（原理图三组布局 + 标题栏，PCB 同电路 DRC 0）
- README 演示图/GIF 替换为新图
- 扩展标识：`uuid` 换新（每次发版换新规则）

## [1.0.6] - 2026-10-28

- 运行时配套改名：服务标识 `easycirq-agent`、用户配置键 `easycirqDaemonPorts`（与 easycirq 运行时匹配）
- README 中 CLI 命令与安装路径同步为 `easycirq` / `%LOCALAPPDATA%\EasyCirq`
- 扩展标识：`uuid` 换新（每次发版换新规则）

## [1.0.5] - 2026-10-28

- README 品牌措辞清理：正文中不再出现 easycirq 作为产品/组件名（仅保留 CLI 命令、安装路径与服务标识等技术标识）
- 扩展标识：`uuid` 换新（每次发版换新规则）

## [1.0.4] - 2026-10-28

- README 补充功能演示（原理图/PCB 真实截图 + 流程 GIF），满足扩展市场审核要求
- 演示素材来自本项目真实工程（非上游素材），图片位于 images/showcase-*.png、showcase.gif
- 扩展标识：`uuid` 换新（每次发版换新规则）

## [1.0.3] - 2026-10-28

- 品牌命名统一：中文名称「智构」、英文名称「EasyCirq」；扩展标识与显示文案不再使用 easycirq/design-hardware
- 扩展 `name` 改为 `easycirq-connector`；扩展 `uuid` 换新（每次发版换新规则）
- README/安装说明中的组件名统一为「智构 Skill / 智构运行时 / 智构工具链」（命令 `easycirq` 保留为运行时内部代号）

## [1.0.2] - 2026-10-28

- 图标改用项目品牌方形 logo（`images/logo.png`，512×512，来自品牌素材）
- README 顶部加入品牌横幅 `images/banner.png`（智构 · EasyCirq 横版 logo）
- 扩展标识：`uuid` 换新（每次发版换新规则）

## [1.0.1] - 2026-10-28

- 图标改为项目自有品牌 PNG（`images/logo.png`，512×512，1:1，非播放默认图）
- 清单 `license` 改为项目主许可 `Apache-2.0`（上游 MIT 版权/许可声明保留在 NOTICE）
- 扩展标识：`uuid` 换新（每次发版换新规则）

## [1.0.0] - 2026-10-28

首个 EDA 扩展市场版本（市场合规改造）：

- 扩展标识更新：`name` = `easycirq-easycirq-connector`，`uuid` = `e5f3a3c5193c4b4b8c319188737c0e4f`（每次发版换新 UUID，避免旧代码残留）
- 完善扩展清单：名称、唯一标识、显示名、描述、版本、许可证、仓库、类别（categories）、图标、入口（entry）
- 自定义品牌图标（512×512，1:1，PNG/JPEG 合规，非 SDK 默认 Logo）
- 新增 `CHANGELOG.md`，重写 `README.md` / `README.en.md`（功能说明、安装、授权、升级、排障、安全）
- 许可证表述与上游一致：MIT（上游 easyeda-agent）+ Apache-2.0（本项目修改）
- 功能与协议行为与 0.1.4 一致：本机 WebSocket 桥接、typed action、身份/产物回传

## [0.1.4] - 2026-10-27

- 新增 PCB 制造导出动作：Gerber/钻孔、贴装坐标（CPL）、网表
- 修复 drill 导出对"0 孔板"的误报
- 品牌重命名：显示名改为「智构 · EasyCirq 连接器」

## [0.1.3] - 2026-10-27

- 品牌重命名（显示名、UUID 更新）
- 原理图/PCB 检查动作增强

## [0.1.2] - 2026-10-27

- 修复封装内嵌 BOARD_OUTLINE 图形导致的操作阻断

## [0.1.1] - 2026-10-26

- 初始内部版本：连接器与运行时握手、基础原理图/PCB 动作

## [0.1.0] - 2026-10-26

- 首个内部构建（派生自 easyeda-agent 1.15.0，MIT）
