# Changelog — EasyCirq EDA Connector

## 0.1.0 (2026-10-27)

- 从 easyeda-agent v1.15.0 连接器扩展分支：自有扩展标识（uuid/name/displayName/publisher）。
- 服务标识改为 `easycirq-agent`，daemon 端口改为 23111-23120，与上游工具链完全隔离。
- 扩展用户配置键改为 `easycirqDaemonPorts`；菜单与日志前缀改为 EasyCirq。
- 发布包剔除上游演示媒体与上游 CHANGELOG，附 `NOTICE`（含内嵌 Apache-2.0 组件说明）。
