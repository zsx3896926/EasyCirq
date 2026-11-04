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
