"""相位层：把方法论做成代码，而不是提示词。

> 2026-11 用户明确：harness 形态的目的是**把方法论做成代码**。
> 所以这一层不是"让 AI 更会画板"，是**让 AI 跳不过步骤**。

---

## 一、它解决什么

`sch status` 能**检测** S1–S6 到哪一步了，但它不**阻止**你从 S1 直接跑 `sch place`。

**检测不是强制。** 这一层补的是强制那一半。

`sch gate` 的说明里记着动机，是真实故障：

> 四个检查器本来是分开的命令，于是每次运行都从一个无法回答的问题开始——
> 跑哪几个、什么顺序、谁的退出码算数。
> **审计日志显示 agent 对同一个失败的四种不同回答。**

把顺序和阻塞规则放进代码，就是消灭这种自由。

---

## 二、语义（与 `sch gate` 三态判词对齐）

```
NOT RUN ──跑一次──→ pass / fail / blocked
                      │
blocked ──修好环境再跑──→ pass / fail
fail    ──修板──→ pass
```

**只有 `pass` 放行。**

| 状态 | 含义 | 阻塞？ |
|---|---|---|
| `pass` | 门通过了 | 否 |
| `fail` | 板子有问题 | **是** |
| `blocked` | **检查器没跑成**（连接器掉线、页面没开） | **是** |
| `pending` | **有门但没跑**（NOT RUN） | **是** |
| `stale` | 跑过了，但**板子改了** | **是** |
| `unenforced` | **这个相位还没接门** | 否，但必须显式标出 |

**`blocked` 不是通过。** 这与 `sch gate` 的立场一致：
"the checker could not run" 不是 "the board is broken"，但也不是通过。

---

## 三、命令

```powershell
easycirq phase show     --project <uuid>    # 当前相位 + 各相位证据状态
easycirq phase run S5   --project <uuid>    # 跑该相位的门并记证据
easycirq phase advance  --project <uuid>    # 推进（前置不是 pass 就拒）
easycirq phase set S6   --project <uuid>    # 强制设置（记为 override，留痕）
```

---

## 四、当前接了什么

| 相位 | 门 | 状态 |
|---|---|---|
| S5 | `sch gate --json`（layout-lint → check → bridge-check → drc） | **已接** |
| 其余 | — | **未接门**（`unenforced`，不阻塞但标明） |

**只接一个门是刻意的。** 目标文档第九节写着：

> 给 184 个动作分相位会分错。分错的后果不是"漏了一个门"，是**正常做板被卡住**
> ——那比没有强制更糟，因为用户会去找绕过办法，然后永远绕过去。

所以先只强制一个转换，跑过真实任务再铺开。

---

## 五、DELIVER 多一道：空板子不行

**实测发现**：新建的空工程跑 `sch gate` 返回 `pass`（没有可检查的问题）。
如果 DELIVER 只认 S5，那空板子也能"可交付"——强制了个寂寞。

所以 DELIVER 额外要求：**板上至少一个真实器件**（不含 sheet 图框）。

```
$ easycirq phase advance DELIVER --project <空工程>
refused: the board has no parts yet — an empty schematic passes the S5 gate
trivially, so it cannot be delivered
  阻塞：PARTS 的证据是 empty（需要 pass）
```

---

## 六、证据会过期

每条证据带**文档哈希**（对工程的图纸 uuid 列表取 SHA256 前 16 位）。

板子改了 → 哈希变了 → 旧证据自动变 `stale` → 阻塞。

**为什么**：换机器、过一夜，都不能假装跑过了。

存放位置：`~/.easycirq/phase/<projectUuid>.json`（本机，不进工程）。
可选 `EASYCIRQ_PHASE_DIR` 覆盖。

---

## 七、实测（2026-11-04）

```
1) 空板子跑 S5 门               → pass（trivially，因为没什么可查）
2) S5 → S6 推进                 → 允许（S5 是 pass）
3) S6 → DELIVER（空板子）        → **拒绝**：the board has no parts yet
4) daemon 重启导致连接器掉线，
   再跑 S5                      → **blocked**（不是 fail）→ 记为阻塞
```

第 4 条正是三态判词的价值：**"检查器没能跑完"不等于"板子坏了"，但也不等于通过。**

---

## 八、这一层刻意没做的

| 没做 | 为什么 |
|---|---|
| **184 个动作按相位白名单（daemon 强制）** | 分错会卡住正常工作流。先搭证据链，跑过真实任务再铺 |
| 循环 / 模型调用 | 第 1 层做完，循环退化成"顺序调用器的薄壳" |
| 改现有门的判定逻辑 | `sch gate` 三态、`card` exit 码、`equivalence` 都已验过，不动 |
| R1–R8 全部落码 | 先落能量化的（有命令、有退出码的） |

---

## 九、为什么这算"方法论做成代码"

对照一下：

| 做法 | 模型能不能绕过 |
|---|---|
| 在 SKILL.md 里写"必须先跑 gate" | **能**（它可能不跑，或跑别的顺序） |
| 在 `phase advance` 里检查证据 | **不能**（exit≠0，脚本和 agent 都会停） |

现在的强度是第二种。**第三种**（daemon 拒绝派发越界动作）更强，但要先把 184 个动作分类，
那是下一层的事。


---

## 十、真实任务验证（阶段 3，2026-11-04 实测）

新建工程 → 逐级推进 → 落一个器件 → 试图交付。全部动作与拒绝记录在
`reports/phase-stage3.json`。

```
总动作数 15 · 门运行 2 次 · 推进尝试 9 次 · 被拒 3 次
```

| # | 拒绝 | 是不是误报 |
|---|---|---|
| 1 | S0 直接跳 DELIVER | **不是** —— 前置全没跑 |
| 2 | S5 没跑门就推进 S6 | **不是** —— 有门没跑 |
| 3 | 空板子进 DELIVER | **不是** —— 没有器件 |

**三次拒绝都是真的拦住了问题，零误报。** 这是决定"要不要铺开 184 动作白名单"
的关键数据——至少目前这条路不吵。

### 但验证同时挖出两个真漏洞

**① 空板子让 S5 trivially pass。**
空原理图没有可检查的问题，`sch gate` 判 `pass`。只认 S5 的话，空板子也能"可交付"。
→ DELIVER 加前置：**至少一个真实器件**（sheet 图框不算）。

**② 悬空引脚只是 warn，判词仍是 pass。**
落一个电阻（两个引脚都没接）后，`sch gate` 只报 `CHECKFLOATPIN` 的 `warn`，
**判词还是 pass**，于是 DELIVER 被放行。
→ DELIVER 加前置：**`floatingPinCount == 0`**。

这两个都不是设计时想到的，是跑出来的。**这正是"先量再铺"的理由。**

### 顺带修的两个小问题

- `advance` 在"目标 == 当前相位"时报 `advanced X → X`，是假进展 → 现在明确拒绝
- `PARTS` / `PINS` 是 DELIVER 的前置条件、不是相位，原来也打印
  "该相位还没有门"，会让人以为要去接一个叫 PINS 的门 → 改成"DELIVER 前置"

### 还有一个坑（值得记下来）

改完 `easycirq/scripts/phase.py` 后**忘了同步到技能目录**
（`~/.agents/skills/easycirq/scripts/`），于是 `easycirq phase` 跑的还是旧拷贝，
新加的检查"没生效"。**改完脚本必须同步，否则你会以为是逻辑没写对。**


---

## 十一、`card` 已接进 DELIVER

`card` 是"这块板能不能下单"的交付卡。它的退出码语义是它自己定的：

```
Exit codes: 0 ready, 1 not ready, 2 not measured or invalid
```

接法：DELIVER 额外要求 `card` 是 `ready`。

| card 判词 | 映射 | 放行？ |
|---|---|---|
| `ready`（exit 0） | `pass` | ✅ |
| `not_ready`（exit 1） | `fail` | ❌ 板子有问题 |
| `not_measured`（exit 2） | **`pending`（= NOT RUN）** | ❌ **没测量不等于通过** |

实测：

```
$ easycirq phase advance DELIVER --project <未跑 KPI 的工程>
refused: the delivery card is pending (⏳ 这块板还没检查过) — a board that has
not been measured cannot be delivered
  阻塞：DELIVER 前置 CARD = pending
```

**`not_measured` 映射成 `pending` 是这条的关键。** 它没有报错、退出码也不是 1，
但它**什么也没证明**——正好是本目标要消灭的那种"看起来没事"。

代价：所有还没跑离线 KPI 的工程，现在都到不了 DELIVER。**这不是副作用，这是正确行为。**

### DELIVER 现在的四道前置

| 前置 | 判据 |
|---|---|
| `S5` | 原理图校验门 pass |
| `PARTS` | 板上至少一个真实器件（sheet 图框不算） |
| `PINS` | `floatingPinCount == 0` |
| `CARD` | 交付卡 `ready`（不是 not_measured） |

## 十二、证据默认落在哪（实测）

不设 `EASYCIRQ_PHASE_DIR` 时：

```
$ easycirq phase run S5 --project a0b27326…
S5: pass

$ ls ~/.easycirq/phase/
a0b27326352d4d45a2b1c85eaf384e1e.json     1343 字节
```

- **不在工程目录里**（`~/.easycirq/phase`，不在仓库内）
- `.gitignore` 第 25 行已有 `.easycirq/`，git 看不见它
- 内容是 `{schema, project, phase, evidence{S5:{verdict, detail, fingerprint, at}}}`

**为什么放本机而不是工程里**：相位是"我们对这块板的判断进度"，不是板子的一部分；
换机器应该能重建。但**不能因为换机器就假装跑过了**——所以每条证据带文档指纹，
板子变了证据自动作废（`stale`）。

### 还有三个技能目录要一起同步

`doctor` 会看到三份技能目录：

```
~/.agents/skills/easycirq
~/.claude/skills/easycirq
~/.codex/skills/easycirq
```

改完 `scripts/*.py` 后**只同步 `~/.agents` 是不够的**——CLI 可能解析到 `.claude`/`.codex`
那一份旧拷贝，于是你改的逻辑"不生效"，症状和逻辑写错一模一样。三份都要同步。
