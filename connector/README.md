# 智构 · EasyCirq EDA Connector（连接器扩展）

EasyEDA Pro（嘉立创EDA专业版）内运行的连接器扩展：把本机 Zhigou 运行时 daemon 的
typed action 请求翻译成官方 `eda.*` API 调用，并把结果、身份证据与产物回传给 daemon。

- 服务标识：`zhigou-agent`（只连本工具链 daemon，不连旧 `easyeda-agent`）
- 端口：`127.0.0.1:23111-23120`（仅本机；可用扩展用户配置 `zhigouDaemonPorts` 覆盖）
- 扩展 UUID：`a6e6b788551945b399e150d80efa6e31`
- 权限：需在扩展管理器中允许「外部交互 / Allow external interaction」，否则
  `eda.sys_WebSocket` 调用会被宿主拒绝

## 安装

导入是 EasyEDA 内的显式人工动作（扩展在启动时加载，运行中导入不生效）：

1. 关闭所有 EasyEDA Pro 窗口；
2. 「设置 → 扩展 → 导入扩展」，选择随运行时发布的 `zhigou-connector_v<ver>.eext`
   （`zhigou connector path` 可打印本机路径）；
3. 扩展管理器 → Zhigou EDA Connector → 允许「外部交互」；
4. 重启 EasyEDA Pro 并打开工程；
5. 命令行运行 `zhigou doctor`，`connector.status` 应为 `connected`。

## 构建

```bash
npm install            # 首次
npx ts-node ./config/esbuild.prod.ts   # -> dist/index.js
npx ts-node ./build/packaged.ts        # -> build/dist/zhigou-connector_v<ver>.eext
```

## 许可

MIT（上游 easyeda-agent）+ Apache-2.0（本项目修改）。见 `LICENSE` 与 `NOTICE`。
