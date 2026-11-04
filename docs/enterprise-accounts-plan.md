# 独立账号体系 · 实施方案

> ⚠️ **本方案未采用（2026-11 用户决定）**
>
> 当前交付为**纯本地版本**：不做 B/S 架构、不部署服务端、不做账号体系。
> 本文保留作为**历史记录与备选方案**，**不是现行的接入方式**。
> 现行接入请读 [本地交付说明](enterprise-local.md)。


> 决定：**做一套自包含的账号体系**，不对接客户的目录服务（AD/LDAP/SSO）。
> 本文是规划，未开始实现。每条都写了验收方式。

---

## 一、结论先行

| 做什么 | 不做什么 |
|---|---|
| 账号（用户名 + 密码登录） | 不对接 AD/LDAP/OAuth/SSO |
| 会话（登录后拿长期 token） | 不做第三方登录 |
| 邀请码（管理员发码，工程师自己设密码） | 不做多因素认证（MFA） |
| 角色（`admin` / `engineer`） | 不做细粒度项目级权限 |
| 会话吊销、账号停用 | 不做密码找回（管理员重置） |

**分三期**，每期都能独立验收，任何一期停下来系统都是可用的。

| 期 | 内容 | 预估 |
|---|---|---|
| **P1** | `internal/auth` 包：账号、密码哈希、会话、目录文件 + 锁 | 1 轮 |
| **P2** | 接进 gateway 鉴权接缝、`/auth/login`、CLI（登录/建号/停用/改密/引导管理员） | 1 轮 |
| **P3** | 邀请码、失败锁定、文档、迁移说明、全量回归 + 发版 | 1 轮 |

---

## 二、关键设计决定（含推荐与备选）

### 2.1 只改一个接缝，不碰路由

现在**三个鉴权入口**全部经过同一个函数：

```
gateway/route.go:28   /eda    连接器
gateway/route.go:67   /action 命令
gateway/llm.go:94     /llm/*  LLM 转发
```

三处都是 `s.opts.Tokens.lookup(presented)`。所以账号体系**只替换这个 lookup 的背后**，
路由、租户隔离、审计全部不动。

```go
// 新接缝：会话优先，老 token 表兜底
type Authenticator interface {
    Lookup(presented string) (Token, bool)
}
```

**好处**：22 条现有 gateway 测试不用改一条。这既是省事，也是「不破坏现有通过项」的保证。

### 2.2 密码哈希用标准库 pbkdf2，不引新依赖

Go 1.26 的标准库已有 `crypto/pbkdf2`（1.24 起）。全项目现在只有 4 个直接依赖，
**为密码哈希引 bcrypt 不值得**。

| 方案 | 依赖 | 评价 |
|---|---|---|
| **PBKDF2-HMAC-SHA256，600k 次迭代** ✅ | 0（标准库） | OWASP 推荐值；盐 16 字节随机 |
| bcrypt | `golang.org/x/crypto` | 更抗 GPU，但多一个依赖 |
| argon2id | `golang.org/x/crypto` | 最好，同上 |

**说明**：PBKDF2 的抗 GPU 能力弱于 argon2。这里的补偿是**失败锁定**（见 2.6）——
攻击者拿不到无限次尝试机会，暴力破解的成本就不只看单次哈希。

### 2.3 会话 token 在服务端**存哈希**

存明文会话 token 的文件一旦被拷走，等于所有人立刻被接管。
所以落盘的是 `sha256(token)`，明文只在签发那一刻返回给客户端。

- 查找：把请求带的 token 哈希后比对 → 仍然是常数时间
- 文件泄露 → 攻击者拿不到可用的 token

### 2.4 管理操作用 CLI，不开 HTTP 管理端点

目标写的是「管理员**在服务器上**建账号」。所以管理走命令行，在服务器上跑：

```
easycirq gateway account add --username zhang --role engineer
```

**开阔的 HTTP 面只有两个**：`/auth/login`、`/auth/change-password`。
不开 `/admin/*` 是刻意的——管理端点是攻击者最想找的东西，没必要为了远程方便把它挂出来。

### 2.5 首次引导（bootstrap）问题

第一个管理员账号不存在时，谁也不能登录。用一条**只在一个账号都没有时生效**的命令：

```
easycirq gateway account init --username admin
```

- 已有账号 → 直接拒绝（否则任何人跑一次就能给自己建管理员）
- 这条命令必须有测试：**账号已存在时再跑一次必须失败**

### 2.6 失败锁定（本地密码体系必须有的东西）

token 是随机 32 字节，猜不到；**密码是人选的，猜得到**。所以：

- 每个账号记 `failedAttempts` 和 `lockedUntil`
- 连续 5 次失败 → 锁 15 分钟
- 锁定期间一律拒绝，**但错误信息与密码错误完全相同**（见 2.7）

没有这一条，一个本地账号体系就是可以被在线爆破的。

### 2.7 防用户名枚举

未知用户和密码错误必须**返回同一个错误、耗时接近**：

- 未知用户时也跑一次哈希比对（对着一个固定的假哈希），不让响应时间暴露差异
- 错误一律是「用户名或密码不正确」

---

## 三、数据模型

一个文件：`--directory <path>`，默认 `~/.easycirq/directory.json`。

```json
{
  "version": 1,
  "accounts": [
    {
      "username": "zhang",
      "displayName": "张工",
      "role": "engineer",
      "passwordHash": "pbkdf2-sha256$600000$<salt-b64>$<hash-b64>",
      "mustChangePassword": true,
      "disabled": false,
      "failedAttempts": 0,
      "lockedUntil": "",
      "createdAt": "2026-11-03T14:00:00+08:00",
      "createdBy": "admin"
    }
  ],
  "invites": [
    {
      "codeHash": "<sha256>",
      "role": "engineer",
      "createdBy": "admin",
      "createdAt": "...",
      "expiresAt": "...",
      "usedBy": null
    }
  ],
  "sessions": [
    {
      "tokenHash": "<sha256>",
      "username": "zhang",
      "createdAt": "...",
      "expiresAt": "...",
      "lastSeenAt": "..."
    }
  ]
}
```

**为什么哈希里带参数**：`pbkdf2-sha256$600000$...` 自带算法和迭代数，
以后提高迭代数时老密码仍能验证，不用强迫所有人改密。

**为什么会话有 `lastSeenAt`**：管理员能看到「这个人最后一次用是什么时候」，
停用前判断是否影响在用的工程。同时给「长期不用的会话自动过期」留位置。

---

## 四、接口面

### HTTP（只这两个）

```
POST /auth/login
  {"username":"zhang","password":"..."}
  → {"token":"...","expiresAt":"...","mustChangePassword":true,"role":"engineer"}

POST /auth/change-password        (Bearer <token>)
  {"oldPassword":"...","newPassword":"..."}
  → {"ok":true}
```

`mustChangePassword=true` 的会话**只能调 `/auth/change-password`**，其它一律拒绝。
否则管理员印出来的临时密码会一直有效。

### CLI（管理员，在服务器上跑）

```
easycirq gateway account init   --username admin          首次引导
easycirq gateway account add    --username zhang --role engineer
easycirq gateway account list   [--json]                  含最后登录、是否停用
easycirq gateway account disable --username zhang         立即踢掉其全部会话
easycirq gateway account enable  --username zhang
easycirq gateway account passwd  --username zhang         重置密码（临时密码）
easycirq gateway invite new      [--role engineer] [--ttl 7d]
easycirq gateway invite list
easycirq gateway invite revoke   --code <c>
```

### CLI（工程师）

```
easycirq login --server https://... --username zhang     提示输密码
easycirq login --server https://... --invite <码>         凭邀请码自助开通
easycirq login --status / --logout                       已有
```

`easycirq login` 的旧用法（`--token <token>`）**保留不动**——现有部署不会坏。

---

## 五、安全要点与对应测试

判据要求「每加一处能力，配一个故意制造该问题 → 必须报错或被看见的测试」。
下面是逐条对应：

| # | 安全要求 | 故意破坏 → 必须发生什么 | 测试名 |
|---|---|---|---|
| 1 | 密码不落盘明文 | 建号后 grep 目录文件里的密码 → **找不到** | `TestPasswordNeverAppearsInDirectoryFile` |
| 2 | 会话不明文落盘 | 登录后 grep 会话 token 原文 → **找不到** | `TestSessionTokenStoredHashed` |
| 3 | 错误密码拒绝 | 错密码登录 → 401 | `TestLoginRejectsWrongPassword` |
| 4 | 不暴露用户是否存在 | 未知用户 vs 错密码 → **同一个错误** | `TestLoginDoesNotRevealWhetherUserExists` |
| 5 | 停用账号立刻失效 | 登录后停用 → 旧会话再请求 → 401 | `TestDisableKillsExistingSessions` |
| 6 | 会话过期 | 手工把 expiresAt 改到过去 → 401 | `TestExpiredSessionRejected` |
| 7 | 临时密码必须改 | `mustChangePassword` 会话调 `/action` → 403 | `TestTempPasswordCannotBeUsedUntilChanged` |
| 8 | 角色隔离 | engineer 会话调管理命令 → 拒绝 | `TestEngineerCannotRunAdminCommands` |
| 9 | 邀请码一次性 | 同一个码用两次 → 第二次拒绝 | `TestInviteIsSingleUse` |
| 10 | 邀请码过期 | 过期的码 → 拒绝 | `TestExpiredInviteRejected` |
| 11 | 失败锁定 | 连错 5 次 → 第 6 次即使密码对也拒绝 | `TestLockoutAfterRepeatedFailures` |
| 12 | 引导不可重复 | 已有账号时再 `init` → 失败 | `TestBootstrapRefusedWhenAccountsExist` |
| 13 | 老 token 仍可用 | 现有 token 表的 token 照常鉴权 | `TestLegacyTokensStillWork` |
| 14 | 目录文件损坏要报错 | 写坏 JSON → 启动失败并说清路径 | `TestCorruptDirectoryFailsLoudly` |
| 15 | 并发写不丢账号 | 两个进程同时 add → 两个都在 | `TestConcurrentAccountAddKeepsBoth` |

---

## 六、迁移：不破坏现有部署

**原则：账号体系是叠加，不是替换。**

`Lookup` 的查找顺序：

```
1. 会话（哈希比对）        ← 新增
2. 老的 token 表（明文比）  ← 保留
```

所以：

- 现在用 `--tokens tokens.json` 的部署，**一行不改**继续工作
- 想用账号体系，加 `--directory directory.json` 并建号
- 两者可以同时存在（过渡期：管理员先给几个试点的人建号）

**发版前必须证明**：22 条现有 gateway 测试全过，且新增一条
`TestLegacyTokensStillWork`。

---

## 七、分期与验收

### P1 —— `internal/auth` 包（无 UI，纯逻辑）

- [ ] `pbkdf2.go`：`Hash(password) (string, error)` / `Verify(encoded, password) bool`，格式自描述
- [ ] `directory.go`：Load/Save，原子写（临时文件 + rename），`O_EXCL` 锁
- [ ] `accounts.go`：Add / Disable / Enable / SetPassword / Authenticate（含锁定计数）
- [ ] `sessions.go`：Issue / Lookup / RevokeAllFor(username) / Sweep
- [ ] 测试：上表 #1 #2 #3 #4 #11 #14 #15

**验收**：`go test ./internal/auth` 全过，无 UI 变化。

### P2 —— 接进 gateway 与 CLI

- [ ] `Authenticator` 接缝 + 组合（会话 + 老 token）
- [ ] `/auth/login`、`/auth/change-password`
- [ ] `easycirq gateway account {init,add,list,disable,enable,passwd}`
- [ ] `easycirq login --username` / `--invite`
- [ ] 测试：上表 #5 #6 #7 #8 #12 #13

**验收**：跑通一次真实流程（引导 → 建号 → 登录 → 用 `/action` 驱动连接器 → 停用 → 再请求失败），
并贴出每步输出。

### P3 —— 邀请码、锁定、文档、回归

- [ ] 邀请码（#9 #10）
- [ ] 失败锁定接进登录路径（#11 的端到端版本）
- [ ] `docs/enterprise-accounts.md`：怎么建号、怎么停用、离职流程
- [ ] `docs/known-failures.md` 更新账号体系状态
- [ ] 全量回归：pytest / go / connector / 19 项 / 发布一致性

**验收**：全部套件通过，发版，恢复目标并申请完成。

---

## 八、必须先说清的两条操作后果

这两条不是反对意见，是**部署时必须知道的事**，会写进文档：

### 8.1 离职要停两个地方

用了独立账号体系之后，员工离职需要：

- 在客户的 EDA / 目录服务里停用（他们原有的）
- **在 EasyCirq 里 `account disable`**（新的）

漏掉后者 = 离职后还能通过 token 用公司 LLM 额度。
**对策**：`easycirq gateway account list` 显示最后使用时间，
配合 E2（要不要操作审计）定期核对。

### 8.2 管理员多了一个密码要管

管理员账号的密码一旦丢失，只能靠**在服务器上直接改目录文件**恢复。

**对策**：`init` 时强制要求设置 `mustChangePassword`，并把
「目录文件在哪、丢了怎么办」写进运维文档，不留到最后才说。

---

## 九、需要你确认的三点

| # | 问题 | 我的建议 |
|---|---|---|
| 1 | 临时密码走「管理员口头/邮件转达」还是**邀请码自助**？ | **两者都做**（P2 做临时密码，P3 做邀请码）。邀请码更适合规模化 |
| 2 | 会话有效期多久？ | **默认 30 天**，可配；停用即时失效，所以长一点风险可控 |
| 3 | 要不要 MFA？ | **先不做**。内网 + 停用即时生效 + 失败锁定已经覆盖主要风险；MFA 等真有人要求再加 |

---

## 十、和其他目标的关系

这个目标当前是 **blocked**，唯一阻断项就是账号体系。
P1–P3 做完后可以恢复并完成。

**不影响**的部分：L1、L2、LLM 转发、知识库、写入锁都已完成并验证，
本方案只在鉴权层替换背后存储，不动它们。
