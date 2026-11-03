# 企业部署：共享知识库与 LLM 网关

> 这份讲**多家企业共用的部署方案**，不假设任何一家的具体环境。
> 需要客户提供什么，见 [企业接入信息清单](enterprise-discovery.md)。

---

## 第一部分：共享知识库

### 一句话

**把 `EASYCIRQ_KNOWLEDGE_DIR` 指向一个网络共享目录，全公司共用同一份库。**

不需要服务器、不需要服务、不需要数据库。企业自己的文件权限就是权限系统。

### 目录长什么样

```
\\company-file\easycirq\knowledge\          ← 共享目录（Windows UNC）
  或 /mnt/share/easycirq/knowledge/         ← Linux/macOS 挂载点
├── rules.company.json                      企业规范（能拦住交付）
├── parts.company.json                      器件实测参数
├── kb.supply-chain.json                    可检索知识
├── review-ledger.json                      人审记录
└── rules.from-review.json                  由 promote 生成
```

### 配置方式

**Windows（推荐用组策略下发，不要每人手设）**

```powershell
[Environment]::SetEnvironmentVariable(
  "EASYCIRQ_KNOWLEDGE_DIR",
  "\\company-file\easycirq\knowledge",
  "User")
```

**Linux / macOS**

```bash
echo 'export EASYCIRQ_KNOWLEDGE_DIR=/mnt/share/easycirq/knowledge' >> ~/.bashrc
```

> 环境变量读一次就生效在**新开的终端**里，正在跑的进程要重启。
> `easycirq enterprise audit` 会打出它实际读的是哪个目录——**目录不对，第一批就看出来**。

### 权限怎么分

| 角色 | 目录权限 | 能做什么 |
|---|---|---|
| 硬件工程师 | 读取 | 跑检查、检索知识 —— **只能读** |
| 规范维护人（1~2 人） | 读写 | 加规则、改器件参数、`promote` 人审记录 |
| 全员 | **不写** | 见上 |

**为什么默认只读**：一条 `hard` 规则改错，**所有工程师的检查结果一起变**。
让人人可写，等于让一条笔误变全公司的误报。

### 验证它真的生效了

```powershell
easycirq enterprise audit      # 会打出每个层读了哪个目录、几个文件
easycirq enterprise ls         # 看条目
```

**看到 `[enterprise(env)] \\company-file\easycirq\knowledge`** 就对了。
如果显示的是 `~/.easycirq/knowledge`，说明环境变量没生效——**这就是最常见的问题**。

### 已知限制（不装）

| 限制 | 后果 | 现在的应对 |
|---|---|---|
| **工具写入已加锁**（`promote`） | 两人各自 promote 不同规则 → 两条都在；同 id 内容不同 → 报冲突、保留原有的 | 自动处理，见下 |
| **人工编辑仍未加锁** | 两个人用编辑器同时改同一个文件，后保存的覆盖前者 | 把共享目录设成 git 仓库，用 commit 串行化 |
| **没有版本历史** | 改错了说不清谁改的、改了什么 | 把共享目录本身纳入文件系统快照，或用一个 git 仓库托管 |
| **没有审核流** | 谁有写权限谁就能立刻改 | 靠目录权限，把写权限收给 1~2 人 |
| 不支持数据库 | 客户的库只在数据库里 | 先导出成目录；要直连数据库得另做适配层 |

**前两条是真的会咬人的。** 三个人同时维护时，建议直接把共享目录设成 git 仓库，
用 commit 代替"同时改"，历史也就有了。

---

## 第二部分：LLM 网关（B 方案）

> **已验证**：转发链路、密钥不外泄、鉴权拒绝（用假上游实测）。
> **未验证**：真实模型调用——需要客户的 C1/C2/C4 答复和内网 key。
> 详见本节末尾「已验证 / 未验证」。

### 要解决什么

现状：每个工程师自己填 LLM API key。问题是——

- key 散在每台机器上，离职就带走了
- 谁用了多少、问了什么，公司看不到
- 图纸内容发给哪家模型，没人管

### 方案：真 key 不出服务器

```
工程师电脑                                    公司服务器              公网
┌──────────────────────────┐              ┌──────────────┐      ┌────────┐
│ Agent（Claude Code 等）   │              │              │      │        │
│    │ base_url              │              │  鉴权        │      │  LLM   │
│    ▼                      │   HTTPS      │  审计        │      │  厂商  │
│ 本机网关 127.0.0.1:23190  │──带 token──▶ │  计量        │─key─▶│        │
│ （easycirq 起的小进程）    │              │  转发        │      │        │
└──────────────────────────┘              └──────────────┘      └────────┘
```

**关键点**：工程师机器上**只有 token，没有 key**。token 是短期的、可吊销的。

### 三段各自的责任

| 段 | 谁负责 | 做什么 |
|---|---|---|
| 本机网关 | EasyCirq | 监听 `127.0.0.1:23190`，把请求加上 token 转发出去 |
| 公司服务端 | 企业 IT | 验 token、记审计、按人计量、用公司 key 转发 |
| LLM | 客户选 | 公网或内网模型 |

### 需要客户提供什么才能开始做

| 项 | 来自清单 | 决定什么 |
|---|---|---|
| 网关形态 | C1 | 有没有现成的可复用一个 |
| 是否 OpenAI 兼容 | C2 | 兼容则纯转发，不兼容要写协议转换 |
| 图纸能否出公司 | C4 | 能 → 公网模型；不能 → 只能内网模型 |
| 要不要按人计量 | C5 | 决定审计字段 |
| 服务器出网权限 | B4 | 决定转发路径 |

**这五条一条不清楚，写出来的网关就要返工。**

### 客户端怎么指向公司服务器（连接器 1.0.22+）

在 EDA 的插件用户配置里设两项即可，**不用改连接器代码**：

| 配置键 | 值 | 说明 |
|---|---|---|
| `easycirqDaemonUrl` | `wss://easycirq.company.com/eda` | 必须是 `ws://` 或 `wss://`；设了就**不再扫端口** |
| `easycirqAuthToken` | 一次性 token | 作为 `?token=` 附在连接上 |

```js
// 在 EDA 的脚本控制台里执行一次
eda.sys_Storage.setExtensionUserConfig(
  'easycirqDaemonUrl', 'wss://easycirq.company.com/eda');
eda.sys_Storage.setExtensionUserConfig('easycirqAuthToken', '<token>');
```

**不设这两项 = 完全等于以前的行为**（连 `ws://127.0.0.1:23111/eda`）。
这一条有单元测试钉住：`connector/src/transport-remote.test.ts` 里
「unset override keeps the localhost default exactly as before」。

#### token 放在 query 里的代价（必须知道）

`eda.sys_WebSocket.register` 只接受一个 URL 字符串，**没有设置请求头的地方**，
所以 token 只能走 query 参数。这带来两个后果：

1. **token 会出现在代理/网关的访问日志里**
2. 浏览器历史、抓包工具都可能留下它

因此：

- token 必须是**短期的、可吊销的**，不能是长期密钥
- 服务端要按 token 记审计，出事能对应到人
- 不要把 token 写进工单、聊天记录

这也是为什么方案 B 里"真 key 在服务器"很重要：**泄露的 token 只影响一次会话，
泄露的 LLM key 影响整家公司。**

#### 目前**还没有**的

**服务端那一侧还没实现。** 连接器现在**能**连远程地址，但公司服务器上还没有
一个能接受它、并把命令路由到对应工程师窗口的进程。见下方「L2 进度」。

### 服务端怎么起（L2）

```bash
easycirq gateway --tokens tokens.json --listen :8443
```

```
easycirq gateway 已在 [::]:8443 上监听
  token 数：2
  客户端配置：easycirqDaemonUrl = wss://<此地址前置代理>/eda
  注意：本进程只讲明文 HTTP/WS，TLS 由前置代理终止。
```

token 表：

```json
{"tokens": [
  {"token": "…", "engineer": "张工", "expires": "2026-12-31T00:00:00Z"}
]}
```

**每条 token 必须有 `engineer`**——没有名字的 token 无法审计，会被拒绝加载。

#### 它做了什么、没做什么

| 做了 | 没做（有意） |
|---|---|
| 按 token 分辨人，命令只送到本人的窗口 | 账号管理、邀请码、密码 |
| 跨租户严格隔离（甲拿乙的 windowId 打不进去，有测试） | LLM 网关 |
| 复用 daemon 的门禁、审计、产物落盘 | 跨机器数据同步 |
| `/health` 免鉴权，可做负载均衡探活 | TLS 终止（交给前置代理） |

**为什么复用 daemon 而不是重写**：daemon 里已经有变更门禁、审计日志、产物落盘、
多窗口路由、陈旧读检测，且全部有测试。重写一遍会造出**第二套更弱的规则**——
工程师会以为自己受同一套门禁保护，其实没有。

#### 部署时必须知道的三件事

1. **token 走 query 参数**（连接器只能给一个 URL，没法设请求头），
   所以它会进代理日志。**必须短期、可吊销。**
2. **本进程只讲明文 HTTP/WS**。前置必须挂 TLS 代理，否则 token 在网络上是明文。
3. **Windows 上 Ctrl+C 能优雅退出，SIGTERM 不能**——Windows 的 `TerminateProcess`
   是硬杀，进程会被直接终止。生产用服务管理器时要配**优雅停止**（发送 Ctrl+C 等价信号），
   否则在途请求会被切断。这一条**在本机实测过**（`proc.terminate()` 后退出码 1）。

### Agent 直接调 HTTP：工程师机器可以不装 CLI

`easycirq` 命令行只是 `/action` 的一个 HTTP 客户端。**gateway 的接口本身就是
全部能力**——任何能发 HTTP 的 Agent 都能驱动它，不需要在工程师机器上装 CLI。

```bash
curl -sS https://easycirq.company.com/action \
  -H "Authorization: Bearer $EASYCIRQ_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"request","version":"v1","action":"schematic.pages.list"}'
```

服务器会把这个请求路由到**你名下**的连接器，由 EDA 客户端执行并回读。
`windowId` 可选；同一人有多个窗口时用 `--project` 或 `windowId` 消歧。

#### 已验证到什么程度

| 断言 | 验证 |
|---|---|
| 裸 HTTP 能让连接器执行动作并回读 | ✅ `TestRawHTTPDrivesConnectorWithoutCLI`（不经 CLI） |
| 没有 token 的裸 HTTP 被拒、且不打扰连接器 | ✅ `TestRawHTTPWithoutTokenIsRefused` |
| 跨租户隔离在裸 HTTP 下同样成立 | ✅ 沿用 `/action`，与 CLI 同一条路径 |

#### 没验证到的

**具体某个 Agent 怎么发这个请求**（工具调用格式、是否支持自定义 header）
取决于那家 Agent 的形态——这是 B1/B3 之外的新变量，**没拿到答复就不猜**。
上面那条 curl 是通用形态；把它变成某家 Agent 的工具定义是最后一公里。

### 工程师怎么接入（一条命令）

```bash
easycirq login --server https://easycirq.company.com --token <管理员发的>
```

之后**所有命令都发往公司服务器**，不再找本机 daemon。

```bash
easycirq login --status     # 看登录状态，顺手探一次服务器可达性
easycirq login --logout     # 回到本机模式
```

#### 登录会做两次检查，缺一不可

| 检查 | 为什么 |
|---|---|
| `GET /health` 可达 | 地址写错当场发现 |
| **用你的 token 发一次 `system.health`** | `/health` 是免鉴权的 |

第二项是 2026-11-03 实测出来的缺陷：**只探 `/health` 会放行错误 token**——
登录报成功，之后每条命令 401，而工程师以为已经配置好了。现在错误 token
会被当场拒绝，且凭据不会被覆盖。

#### 存了什么、没存什么

存：服务器地址 + 你的 token（`~/.easycirq/credentials.json`，权限 0600）。

**不存：LLM 密钥。** 方案 B 的关键就是真 key 只在服务器，
工程师机器上任何文件都找不到它。这个文件以后也不该加 key。

#### 凭据文件坏了会怎样

**报错，不静默回落到本机。** 否则工程师会以为在操作公司服务器，
实际在本机窗口——那是更难查的错。

### 已经实现了什么

```bash
export COMPANY_LLM_KEY=sk-...          # 真 key 只在这里
easycirq gateway --tokens tokens.json --listen :8443 \
  --llm-base-url https://api.deepseek.com \
  --llm-key-env COMPANY_LLM_KEY
```

之后 `POST /llm/v1/chat/completions`（`/llm` 之后的路径**原样透传**）会：

1. 用工程师的 token 鉴权
2. 换成服务端的真 key
3. 转发上游，状态码与响应体原样返回

实测（假上游）：

```
有效 token  → 200，上游收到 Bearer sk-real-company-secret
             上游收到的 Authorization 里没有工程师的 token
无效 token  → 401，上游一次都没被调用
过期 token  → 401，上游一次都没被调用
```

#### 三个刻意的设计

| 决定 | 为什么 |
|---|---|
| key 从**环境变量**读，不从命令行 | 命令行参数会进 `ps` 和 shell 历史 |
| 不透传客户端的 `Authorization` | 那是我们的 token，不该出现在上游日志 |
| 上游状态码**原样返回** | 429 被改写成 200 会让调用方以为自己没问题 |

#### 审计只记元数据

日志写：谁、方法、路径、状态、耗时。**不写**请求体、响应体、真 key。

图纸和提示词可能涉密，落盘即泄露。

#### 还没做的

| 项 | 卡在哪 |
|---|---|
| 真实模型调用 | 客户的 C1/C2/C4（网关形态、是否 OpenAI 兼容、图纸能否出公司） |
| 本机代理（127.0.0.1:23190） | 未做。现在需要 Agent 手动把 base_url 指到 `<gateway>/llm` |
| 按人配额与限流 | C5 |
| 非 OpenAI 协议的转换 | C2 |

**注意第一项**：现在工程师的 Agent 要指向 `<服务器>/llm`，**不是** `127.0.0.1:23190`。
本机代理是 B 方案原设计里的一环，尚未实现——它能让 Agent 配置更简单，
但不影响"真 key 不下发"这个核心承诺，因为 key 本来就在服务器上。

### 为什么不让服务端代调 LLM（否掉 A 方案）

> 完整设计见 [LLM 网关设计](enterprise-llm-design.md)。

A 方案是：服务端自己当 Agent，工程师只提交"我要做块板"，服务端全自动跑完。

**否掉的理由**：

1. 现在「AI 在外面、EasyCirq 是手」这个架构**已经被验证过**（整条风扇板就是这么做出来的）
2. A 要在服务端重新实现一遍工具编排、上下文管理、失败恢复——等于重写
3. **出错面从一个人变成一个公司**：服务端逻辑错一次，所有工程师同时拿到坏结果

B 只是把 key 挪个地方，其余不变。

### 还有一个更重要的问题

**无论 A 还是 B，都不许把"人审"变成可选步骤。**

平台化最大的危险不是技术，是这句话：

> 「平台都检查过了，应该没问题吧」

然后人审被跳过。电气错误会烧板。

所以网关这一层不管怎么做，都必须做到：

| 要求 | 为什么 |
|---|---|
| 检查结果里能看出**哪条规则**拦住了、**依据哪条规范** | 人才能判断该不该接受 |
| 判不了的东西显示 `unknown`，不显示 `pass` | 否则等于告诉人"没事" |
| **不提供"一键全部通过"** | 那等于把签字变成点按钮 |

这三条已经在 L1 里做到了（`easycirq enterprise review` 的输出就是这个形状）。
网关改造不许把它降级。

---

## 部署检查单

上线前，逐条打勾：

```
□ EASYCIRQ_KNOWLEDGE_DIR 已通过组策略/配置文件下发
□ easycirq enterprise audit 显示的是共享目录，不是本机目录
□ 共享目录权限：工程师只读，维护人 1~2 个可写
□ 已把共享目录纳入备份（git 或文件系统快照）
□ 每个人跑通：easycirq enterprise ls 能看到公司规则
□ 有人拿一块真板跑过 easycirq enterprise check，确认能拦
□ 知道谁负责维护规则库
```

最后一条最容易被跳过：**"谁负责维护"没有答案，库三个月后就是空的。**
