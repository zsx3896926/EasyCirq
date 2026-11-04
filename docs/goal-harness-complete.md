# 目标：把 harness 形态做完且可交付

> 2026-11-04 立。用户：「把harness形态做完且可交付」
> 承接上一轮：`docs/goal-methodology-as-code.md`（门已经写进代码），
> 这一轮补的是**循环**和**打包**。

---

## 一、一句话

> **门已经会拒绝，这一轮让「谁按顺序调门」也变成代码；然后打出能装、能跑的包。**

---

## 二、做完的（每条都有实测）

### ① 循环：`easycirq run`

```
while 还没到 DELIVER:
    把「当前相位 + 各相位证据 + 本相位允许的动作」交给模型
    模型返回工具调用
    执行（**白名单在这一层，越界直接拒**）
    该推进时先跑门，再问 phase 能不能 advance
    被拒 → 拒绝理由原样喂回模型
```

实测（假模型驱动，无需 key）：

```
$ easycirq run --goal "验证 harness" --project demo2 --fake script.json
  [cli] REFUSED 'sch place --lib x --uuid y --x 100 --y 100'（相位 S0 不许）
  [advance] OK advanced S0 → S1
  [gate S5] → blocked
  [advance] OK advanced S1 → S2
```

**第一行就是全部意义**：模型在 S0 想放器件，被拒了——
不是"提示它别这么做"，是**它拿不到这个动作**。

### ② 动作白名单在循环里，不在 daemon 里

daemon 级要给 **184 个动作**逐个分类，分错会卡住正常工作流（比没有强制更糟）。
模型是从循环里调动作的，**在这里过滤效果一样，代价小得多**。

白名单刻意从窄开始，每条都是"这个阶段不做就进行不下去"的最小集合。
匹配**按词边界**（`sch placeX` 不会被当成 `sch place`）。

### ③ 打包：1.3.86（= 最终 HEAD）

```
version: 1.3.86
verdict: ok
corrupt: []
files: 970
sourceCommit: 5d38c7a5…   dirty: False     ← 与 HEAD 一致
包内连接器 sha256: 9d091629d7c1  = 本地最新那份（含无工程报错修复）
```

版本演进：
- 1.3.84 把连接器修对了
- 1.3.85 把「`--goal` 没传给模型」修进去
- **1.3.86 把「`sch kpi` 没暴露、交付卡永远没证据」修进去**

> **这一步是校验器抓出来的**：我先只重建了本地二进制、没重新打包，
> 于是发给客户的包仍停在 d62b9246，**不含 `sch kpi` 与 S5 白名单**——
> 客户拿到的包照样卡在 DELIVER。现在有测试钉住：
> `tests/test_bundle_freshness.py` 要求 `sourceCommit == HEAD` 且载荷里有 `run.py`。

**这修掉了一个真问题**：上一版 1.3.81 包里的连接器是旧的，和磁盘上的最新构建对不上。

### ④ 干净安装验收

```
装到全新目录：exit=0，版本 1.3.86，自带 Python ✅，`sch kpi` 命令存在 ✅
PATH 上剔除所有 python/python3/py
  → easycirq phase show        正常
  → easycirq run --fake …      [cli] REFUSED …（相位 S0 不许）
                               [advance] OK advanced S0 → S1
```

**装完不用装 Python，harness 循环就能跑。**

---

## 三、验证到了哪一层（分三层说清）

| 层 | 怎么验的 | 结果 |
|---|---|---|
| **编排逻辑**（白名单/门/推进/目标入对话） | `--fake` 剧本 | ✅ 12 条测试 |
| **协议层**（HTTP + tools + 结果回灌） | 本地起 OpenAI 兼容服务端 | ✅ 1 条测试 |
| **真实模型行为** | 需要真 key | **NOT RUN** |

协议层实测：4 次 POST `/v1/chat/completions`，`tools: 5`，`messages` 从 2 递增到 8
（**工具结果真的回灌进了对话**），`Authorization: Bearer sk-…` 正确。

**未验的只剩一件事**：真模型会不会按提示走。那不是流程问题，是模型能力问题；
流程保证的是**它走不动的时候会被拦住**。

---

## 三之二、真板子干跑发现的卡点（本轮最重要的产出）

前面几节的验证都停在一两步。把相位机**在真板子上从头推到交付判定**，才发现：

```
  [advance] OK advanced S5 → S6
  [gate S5] → pass
  [advance] REFUSED … —— 阻塞：CARD=pending
```

`card` 读 `.easycirq/kpi-report.json`，而产出它的 `sch_offline_pipeline.py`
**没有暴露成 easycirq 子命令**。于是模型在 harness 里**无论如何都满足不了 CARD**：
板子推到 S6、门也过了，交付卡却永远是 `not_measured`，而且**没有任何白名单项能补证据**。

修法：接成 `easycirq sch kpi`，并加进 S5 白名单（早于 S5 不放行）。

**这说明白名单的价值不是"少给模型几个动作"，而是逼出这类断链**——
设计时看不见，跑一遍就露出来。

## 四、路上抓到的 bug

| bug | 症状 | 怎么发现 |
|---|---|---|
| **`--goal` 从没传给模型** | 模型不知道要做什么，只会瞎猜 | 写 HTTP 测试时读初始消息发现的 |
| 白名单用裸 `startswith` | `sch placeX` 会被当成 `sch place` 放行 | 写测试时想到的 |
| 1.3.81 包内连接器旧 | 装了包却拿到旧连接器 | 上一轮核对哈希时发现的 |

第一个最典型：**不报错、不崩、只是模型表现得很笨**。这种只能靠"读一遍实际发出去的对话"抓到。

---

## 五、明确没做的

| 没做 | 为什么 |
|---|---|
| **真实模型端到端** | 本机没有 API key。**NOT RUN**，不外推 |
| daemon 级白名单（184 动作分类） | 分错会卡住正常工作流。循环层的白名单已经够用 |
| 上下文压缩 / 子代理 | 一轮都没在真实任务上跑通，谈不上 |
| 多轮并发 / 断点续跑 | 同上 |

---

## 六、判据

- **不许把"提示"说成"强制"**：白名单拒绝要能测出来，不是写在提示词里。✅
- 每条能力配一个「故意越界 → 必须被拒」的测试。✅ 13 条
- **NOT RUN 标 NOT RUN**：真实模型没跑过就是没跑过。✅
- 不破坏基线。✅

## 七、基线

```
pytest        5200 passed / 4 skipped / 0 failed
go test       17 包 OK
connector     1241/1241
布局单测      124 passed
layout verify 14 项全 PASS
发布          1.3.86  verdict ok  corrupt []  sourceDirty False（sourceCommit = HEAD 5d38c7a5）
```

## 八、可交付的判定

| 项 | 状态 |
|---|---|
| 装得上（含没有 Python 的机器） | ✅ 干净目录装过 |
| 跑得了（相位、循环） | ✅ 无 Python 环境下验过 |
| 拦得住（越界动作、门没过） | ✅ 测试证明 |
| 协议通（HTTP + tools） | ✅ 本地服务端验过 |
| **真模型能用** | **NOT RUN**（无 key） |

**结论：可以交付，附一句实话——真模型没跑过。**
