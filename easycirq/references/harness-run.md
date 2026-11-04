# harness 循环：让 AI 跳不过步骤

> `easycirq run` —— 把「按顺序调门、拒绝跳步、把 NOT RUN 当阻塞」**自动执行**的循环。
> 2026-11 用户明确：harness 形态的目的是**把方法论做成代码，而不是提示词**。

---

## 一、它和"给 agent 一份 SKILL.md"有什么不同

| 做法 | 模型能不能绕过 |
|---|---|
| 在 SKILL.md 里写"必须先跑 gate" | **能**——它可能不跑，或换个顺序 |
| `phase advance` 检查证据 | 不能（exit≠0） |
| **`easycirq run` 的相位白名单** | **不能**——越界的动作直接被拒 |

三层是叠加的。`run` 是第三层：**模型根本拿不到越界的动作**。

---

## 二、怎么跑

```powershell
# 有模型端点
easycirq run --goal "给这块板加一个 3.3V LDO" --project <uuid> `
    --endpoint https://api.deepseek.com/v1 --model deepseek-chat

# 没有 key 时：用剧本验证编排（不需要任何外部服务）
easycirq run --goal x --project <uuid> --fake script.json
```

端点也可以走环境变量：`EASYCIRQ_LLM_ENDPOINT` / `EASYCIRQ_LLM_KEY` / `EASYCIRQ_LLM_MODEL`。

---

## 三、循环里发生什么

```
while 还没到 DELIVER:
    把「当前相位 + 各相位证据 + 本相位允许的动作」交给模型
    模型返回工具调用
    执行（**白名单在这一层，越界直接拒**）
    该推进时先跑门，再问 phase 能不能 advance
    被拒 → 把拒绝理由原样喂回模型
```

模型一开始就被告知：

> 你只能在当前相位允许的动作范围内操作。越界的调用会被直接拒绝。
> 门没 pass 就推进不了——`phase_advance` 会明确拒绝并告诉你缺什么。
> `blocked`（检查器没跑成）不是通过；`pending`（有门没跑）也不是通过。

---

## 四、实测（假模型驱动，可复现）

```
$ easycirq run --goal "验证 harness" --project demo2 --fake script.json
goal: 验证 harness
  [cli] REFUSED 'sch place --lib x --uuid y --x 100 --y 100'（相位 S0 不许）
  [advance] OK advanced S0 → S1
  [gate S5] → blocked
  [advance] OK advanced S1 → S2
```

**第一行就是全部意义**：模型在 S0 想放器件，被拒了。
不是"提示它别这么做"，是**它拿不到这个动作**。

---

## 五、动作白名单（当前范围）

刻意**从窄开始**——窄了会挡住正常工作流，所以每条都是"这个阶段不做就进行不下去"的最小集合。

| 相位 | 允许（摘要） |
|---|---|
| S0 | `project info`、`sch pages` |
| S1 | `sch pages/read`、`doc ls`、`project info/create` |
| S2 | 加 `sch block-apply`、`sch group`、`blocks ls` |
| S3 | 加 `sch place`、`sch modify`、`sch autoplace-free`、`lib search` |
| S4 | 加 `sch wire/connect/autoconnect/netflag/no-connect` |
| S5 | 加 `sch check/bridge-check/drc/gate` |
| S6 | 加 `sch save` |
| **任何相位** | `phase_status`、`run_gate`、`phase_advance`、`finish` |

匹配**按词边界**：`sch placeX` 不会被当成 `sch place`。

表里没有的相位 → 只放行元动作（查状态/跑门/推进），不放业务动作。

---

## 六、为什么白名单在循环里，不在 daemon 里

daemon 级白名单要给 **184 个动作**逐个分类。分错会**卡住正常工作流**——
那比没有强制更糟，因为用户会去找绕过办法，然后永远绕过去。

而模型是从循环里调动作的。**在这里过滤，效果一样，代价小得多，改错也容易。**

daemon 级强制留到有真实任务数据之后再谈。

---

## 七、`--fake` 为什么重要

没有 API key 的环境也要能验证**编排**对不对。
`--fake <script.json>` 用固定剧本替代模型，于是这些是**确定性可测**的：

- 模型想跳步 → 会不会被拒
- 门没过 → 能不能推进
- `blocked` → 算不算通过
- 剧本用完 → 会不会空转

剧本格式：

```json
[
  [{"name": "phase_status", "args": {}}],
  [{"name": "easycirq", "args": {"argv": ["sch", "place", "--x", "100"]}}],
  [{"name": "phase_advance", "args": {}}],
  [{"name": "finish", "args": {"summary": "done"}}]
]
```

---

## 八、明确没做的

| 没做 | 为什么 |
|---|---|
| **真实模型端到端跑** | 本机没有 API key。**NOT RUN**——见第十节，协议层已验，模型行为未验 |
| 上下文压缩 / 子代理 | 先量出真实任务的上下文峰值再谈 |
| daemon 级白名单 | 见第六节 |
| 多轮并发 / 断点续跑 | 一轮都没在真实任务上跑通，谈不上 |

---

## 九、它现在能证明什么、不能证明什么

**能**：流程跳过不去。模型拿不到越界动作，门没过推不动，`blocked`/`pending` 都不算通过。

**不能**：模型会不会把板子画对。那是能力问题，不是流程问题——
流程保证的是**没画对的时候不会声称画对了**。


---

## 十、验证到了哪一步（分三层说清）

| 层 | 怎么验的 | 结果 |
|---|---|---|
| **编排逻辑**（白名单/门/推进） | `--fake` 剧本 | ✅ 11 条测试 |
| **协议层**（HTTP + tools + 结果回灌） | 本地起一个 OpenAI 兼容服务端 | ✅ 见下 |
| **真实模型行为** | 需要真 key | **NOT RUN** |

协议层实测（真监听端口、真收 POST）：

```
PORT=52075
  [cli] REFUSED 'sch place --x 1'（相位 S0 不许）
  [advance] OK advanced S0 → S1

服务端收到的请求：
  {"path": "/v1/chat/completions", "model": "mock-model", "tools": 5, "messages": 2,  "auth": "Bearer sk-te…"}
  {"path": "/v1/chat/completions", "model": "mock-model", "tools": 5, "messages": 4,  "auth": "Bearer sk-te…"}
  {"path": "/v1/chat/completions", "model": "mock-model", "tools": 5, "messages": 6,  "auth": "Bearer sk-te…"}
  {"path": "/v1/chat/completions", "model": "mock-model", "tools": 5, "messages": 8,  "auth": "Bearer sk-te…"}
```

`messages` 从 2 递增到 8，说明**工具结果真的回灌进了对话**——
这是"模型看得到自己刚才做了什么"的证据。

**所以未验的只剩一件事**：真模型会不会按提示走。那不是流程问题，
是模型能力问题；流程保证的是**它走不动的时候会被拦住**。
