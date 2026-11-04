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

> **交付边界（2026-11-04 实测）**：本机 `EASYCIRQ_LLM_KEY` /
> `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` /
> `DASHSCOPE_API_KEY` / `MOONSHOT_API_KEY` **全部为空**，
> `~/.easycirq/credentials.json` 与 `config.json` 均不存在。
> 所以真实模型端到端**在这一环境里跑不了**，不是没跑。
> 这一条已列入 [本地交付说明](enterprise-local.md) 的「已知交付边界」。

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


---

## 十一、真板子干跑发现的一个卡点（已修）

前面几节的验证都停在 S0/S5 的一两步。这一节是**把相位机在真板子上从头推到交付判定**，
结果发现了一个设计时看不见的卡点。

### 干跑输出

```
$ easycirq run --goal "把这块板推进到可交付（真板子干跑）" \
      --project <uuid> --fake script.json
  [advance] OK advanced S0 → S1
  [advance] OK advanced S1 → S2
  [advance] OK advanced S2 → S3
  [advance] OK advanced S3 → S4
  [advance] OK advanced S4 → S5
  [gate S5] → pass
  [advance] OK advanced S5 → S6
  [advance] REFUSED refused: the delivery card is pending (⏳ 这块板还没检查过)
            —— 阻塞：CARD=pending
```

### 卡在哪

`card` 读 `.easycirq/kpi-report.json`，而产出它的 `sch_offline_pipeline.py`
**当时没有暴露成 `easycirq` 子命令**——它只是个脚本。

于是模型在 harness 里**无论如何都满足不了 CARD**：相位机把板子推到 S6，
门也过了，交付卡却永远是 `not_measured`。而且**没有任何白名单项能让它补证据**。

这正是"白名单分错会卡住正常工作流"的具体样子——只不过这次不是分错，
是**漏了一个本来就不在动作目录里的步骤**。

### 修法

1. 把管线接成子命令：`easycirq sch kpi`（`runtime/internal/app/cmd_sch_kpi.go`）
2. S5 白名单加 `sch kpi`——S5 是"证明这块板没问题"的相位，验证类动作都在这
3. 早于 S5 的相位**不**放行它（还没画完就跑去验，是本末倒置）

修完实测：

```
  [advance] OK advanced S4 → S5
  [cli] easycirq sch kpi --snapshot-dir nope
```

白名单放行了——卡点消除。`sch kpi` 本身失败是因为快照目录不存在，
那是**输入问题**，不是流程问题。

### 顺带修的：拒绝时要说清为什么

原来日志只打 `REFUSED refused`，等于没说。现在：

```
[advance] REFUSED … —— 阻塞：CARD=pending
```

工具返回值里还带 `howToFix`，直接告诉模型该跑哪条命令。

---

## 十二、这条干跑证明了什么

**能证明**：一块真板子可以被相位机推着走完 S0→S6，门会真跑，达不到交付条件时
**会被拦下来并说明缺什么**。

**不能证明**：模型会不会自己找到正确的动作。干跑用的是固定剧本——
它验的是**流程的闸门**，不是模型的判断力。


---

## 十三、中断与续跑（实测）

harness 被中断是常态：模型超时、人关窗口、机器重启。所以「状态能不能活下来」
决定它到底能不能用在真项目上。

`
=== 第一次 run：推到 S2 ===
  [advance] OK advanced S0 → S1
  [advance] OK advanced S1 → S2
  第二次后相位: S2

=== 第二次 run：应当从 S2 继续 ===
  [advance] OK advanced S2 → S3
  第二次后相位: S3

=== 反复越界：相位不许前进 ===
  [cli] REFUSED 'sch place --x 1'（相位 S0 不许）  × 5
  相位: S0 （未动）
`

**续跑正确**：第二次 run 从 S2 接着走，没有回到 S0。
**越界不污染**：连续 5 次越界全被拒，相位一动不动。

三条测试钉住：	ests/test_run_robustness.py。
