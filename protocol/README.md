# 智构 · EasyCirq 工具链契约（protocol）

本目录是 Skill ↔ 运行时 ↔ 连接器之间**线上契约的唯一真源**。JSON Schema 用于校验，
`README.md` 用于人读；`reference/` 是从上游 easyeda-agent（MIT, v1.15.0）引用的原始契约
文档，仅作溯源与对照，**不再生效**——生效的是本目录下的文件。

## 版本与服务身份

| 项 | 值 | 说明 |
| --- | --- | --- |
| `wireVersion` | `v1` | 每个 request/response envelope 的 `version` 字段 |
| `service` | `easycirq-agent` | daemon 在 `handshake` 帧里声明；连接器校验后才注册 |
| 传输 | WebSocket，`ws://127.0.0.1:<port>/eda` | 端口段 23111–23120，仅本机 |
| 心跳 | 连接器 `ping` / daemon `pong` | 3s 间隔，连续缺失触发重连 |
| 大小/超时 | 单帧上限由 daemon 读取边界控制；请求带 `timeoutMs` | 超时不得盲重试 |

`handshake` 校验是隔离的关键：旧 daemon 说 `easyeda-agent`，本工具链说 `easycirq-agent`，
连接器只认后者，因此两套工具链同机运行不会互相接管。

## 帧

| 文件 | 方向 | 内容 |
| --- | --- | --- |
| [`schemas/handshake.schema.json`](schemas/handshake.schema.json) | daemon→connector | 服务身份与版本 |
| [`schemas/register.schema.json`](schemas/register.schema.json) | connector→daemon | windowId、连接器/EDA 版本、能力、UA |
| [`schemas/context.schema.json`](schemas/context.schema.json) | connector→daemon | 工程/文档/类型/单位/可见性 |
| [`schemas/request.schema.json`](schemas/request.schema.json) | daemon→connector | 动作调用 |
| [`schemas/response.schema.json`](schemas/response.schema.json) | connector→daemon | 结果 + 身份证据 + 顺序证据 |
| [`schemas/error.schema.json`](schemas/error.schema.json) | 内含于 response | 稳定错误码 |
| [`schemas/artifact.schema.json`](schemas/artifact.schema.json) | 双向 | 二进制产物（base64 内联 → daemon 落盘） |

## 语义要点（不是可选建议）

1. `response.context` 是**诊断**，不能当作写入/保存目标；只有 `mutationContextAvailable:true`
   的 `mutationContext` 才能作为同一 handler 边界的身份证据。
2. `seq`/`seqAbandoned`/`unordered` 是顺序证据，不是持久化证据；`unordered:true` 的响应
   不构成任何顺序结论。
3. `ACTION_ABANDONED` 表示 handler 超时被放弃，**其效果可能稍后落地**：关于这次写的任何
   结论都不成立，必须回读判定。
4. `PRECONDITION_REFUSED` 表示调用方输入讲不通且**零变异**；收到它不得当作"连接器不健康"。
5. 产物由连接器内联 base64 返回，daemon 落盘后填 `path/size/sha256` 并剥离 `inlineBase64`，
   因此调用方看到的产物路径一定是 daemon 写出的、可哈希核对的真实文件。
