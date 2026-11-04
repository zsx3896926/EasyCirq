# 本地交付说明

> **现行接入方式。** 2026-11 用户决定：**不按 B/S 架构设计，全部做成本地版本。**
> 不部署服务端、不做账号体系、不做多租户。
> 讲服务端/网关/账号的那几份文档已标「未采用」，只是历史记录。

---

## 一、一句话

> **每台工程师机器装一份 EasyCirq，连本机的 EDA 客户端；企业规范放在一个共享盘里。**

没有服务端，没有登录，没有密钥托管。

---

## 二、客户要做的三件事

### 1. 装（每台机器一次）

```powershell
# 管理员把 easycirq-toolchain-<ver>.zip 拷到机器上（U 盘/内网共享都行）
.\Install-EasyCirq.cmd
```

装完包含 `easycirq.exe`、连接器 `.eext`、技能包，以及**内置的 Python**
—— **客户机器上不需要预装 Python**（受控电脑通常没有，装它要走 IT 审批）。

自检：

```powershell
easycirq --version
easycirq doctor
```

`doctor` 的 `verdict` 是 `degraded` 不一定是坏事：**daemon 没起、或连接器没连**都会是
degraded，按下面第 2 步做完再跑一次。

### 2. 导入连接器（每台机器一次，**必须重启 EDA**）

```
打开 嘉立创EDA专业版 → 设置 → 扩展 → 已安装 → 导入扩展
选 <安装目录>\connector\easycirq-connector_v<版本>.eext
**完全退出并重新启动** EDA（连接器在启动时加载，不支持热加载）
```

**版本必须对得上**：`easycirq doctor` 里那一行

```
connector connected (N window(s), expected easycirq-connector v1.0.22)
```

括号里如果是旧版本（v1.0.20 / v1.0.21），说明导入的是旧 `.eext`。
**它不会报错，只会行为不符** —— 所以每次升级都要重新导入并重启。

### 3. 指规范库（每台机器一次）

```powershell
setx EASYCIRQ_KNOWLEDGE_DIR "\\fileserver\dept\rules\easycirq-kb"
```

**这是共享文件夹，不是服务端。** 10 个工程师读同一份，谁改谁提交，
`promote` 时按 id 合并并加锁，冲突会显式报出来。

> **另一种选法**：不想用共享盘，就把库放在每台机器本地。
> 代价是 10 台机器 10 份，会分叉——**规范本来就该全公司一份**，
> 所以默认推荐共享盘。两种都能跑，切换只改这一个环境变量。

---

## 三、装完能做什么

| 能力 | 命令 | 说明 |
|---|---|---|
| 按企业规范查网表 | `easycirq enterprise check --netlist <文件>` | **只要客户能导出结构化网表就能用**，与 EDA 是哪家无关 |
| 查知识库 | `easycirq enterprise ls / show / audit` | 有哪些规则、每条拦过什么、哪些从未生效 |
| 生成自包含报告 | `easycirq enterprise report --out kb.html` | 单个 HTML，双击能开，能放内网共享 |
| 从历史 DRC 挖候选 | `easycirq enterprise harvest --drc <报告或目录> --dump <dump>` | 出**候选**，必须人审 disposition 才能 promote |
| 证明候选真会拦 | `easycirq enterprise harvest --replay <候选文件> --dump <dump>` | 回放不命中标 `unknown`，**永不标 pass** |
| 人审并生效 | `easycirq enterprise review / promote` | 没有 disposition 的条目**一律拒绝** |
| 离线 PCB 检查/测量 | `easycirq layout ...` | 出**测量数字**，不出「可投产」结论 |

---

## 四、这一版**不**做什么（必须对客户说清）

| 不做 | 为什么 |
|---|---|
| **不替你自动画完一块板** | 我们自己的样板板 `clearance 146`（目标 0）。几何下界算过：**不换连接器做不到**。销售话术里不要写 |
| **不做账号体系 / 登录** | 本地交付，没有中心 |
| **不做多租户 / 远程连接器** | 连接器只连 `ws://127.0.0.1:23111`；远程 `wss://` 是留着的可选能力，用不到 |
| **不做 LLM 密钥托管** | 没有服务端可托。**AI 用哪家、key 放哪，由客户自己配在客户端一侧** |
| **不替代人审** | 工具出候选/出数字，**"这算不算公司规范""这块板能不能投产"必须人定** |

---

## 五、每台机器要确认的四条

装完在一台机器上跑一遍，四条都过才算装好：

```
1. easycirq --version                      → 显示版本
2. easycirq doctor                         → skill installed / daemon running
3. <安装目录>\python\python.exe 存在        → 自带解释器在
4. easycirq enterprise check --netlist <网表> → 出结论（exit 0 或 1 都正常）
```

**第 3 条是重点**：它不存在时 `enterprise` 命令会明确报「安装不完整」，
而不是静默变成「命令不存在」。

---

## 六、升级

```powershell
# 新版本覆盖安装
.\Install-EasyCirq.cmd
# 重新导入新连接器 .eext，并重启 EDA ← 这一步最容易忘
easycirq doctor     # 确认 connector 版本已跟上
```

旧版本的文件有清单记录，卸载只删自己装的东西，不碰用户配置。

---

## 七、常见问题

**Q：`doctor` 显示 degraded 要紧吗？**
先看是哪一项。`daemon down` / `connector disconnected` 都是 degraded 但可修；
如果 `skill` 不是 `installed`，那是真没装好。

**Q：能不能不装 Python？**
本来就不需要——包里有。如果 `<安装目录>\python\` 被删了，
`enterprise` 命令会指名说「安装不完整」。

**Q：知识库能不能各管各的？**
能。不设 `EASYCIRQ_KNOWLEDGE_DIR` 就用本机默认目录，但会分叉。

**Q：客户 EDA 不是嘉立创 EDA 怎么办？**
**当前版本不支持**，产品边界就是嘉立创 EDA（用户 2026-11 明确）。
但 `enterprise check` 这一条只吃网表文件，只要客户能导出结构化网表就与 EDA 无关。


---

## 八、已知交付边界（交付时必须对客户说）

这一节列的**不是待办**，是**这一版客观上没做到的事**。写在这里是为了让它
出现在交付清单上，而不是埋在某个文档的脚注里。

| 边界 | 现状 | 客户会感知到什么 |
|---|---|---|
| **真实模型没有端到端跑过** | 编排层与**协议层**都验过（本地 OpenAI 兼容服务端，4 次 POST、`tools:5`、工具结果回灌）；**真模型行为未验**——本机没有任何 API key | 第一次接真模型时，可能遇到提示词、工具描述、模型选型导致的效果差异。**这不是 bug，是没验过** |
| **自动布线不能交付** | 我们自己的样板 `clearance 146`（目标 0）；几何下界算过，不换连接器做不到 | 不要承诺"自动布线出可投产的板" |
| **不做账号体系 / 多租户** | 本地交付，无中心 | 没有登录，没有集中管理 |
| **动作白名单在循环层，不在 daemon** | 模型走 `easycirq run` 时受约束；绕过 `run` 直接调 CLI 不受相位白名单限制 | 客户若不用 `run`，相位约束只剩 `phase advance` 那一层 |
| **只支持嘉立创 EDA** | 产品边界（2026-11 用户明确） | 其他 EDA 不支持；但 `enterprise check` 只吃网表，与 EDA 无关 |

### 关于「真实模型未验」的具体说明

已经验的：

```
$ easycirq run --goal … --endpoint http://127.0.0.1:<port>/v1 --model mock-model
服务端收到 4 次 POST /v1/chat/completions
  tools: 5   messages: 2 → 4 → 6 → 8   Authorization: Bearer sk-…
  [cli] REFUSED 'sch place --x 1'（相位 S0 不许）
  [advance] OK advanced S0 → S1
```

`messages` 递增说明**工具结果确实回灌进了对话**；`REFUSED` 说明越界动作在
HTTP 路径上也被拦住。

**没验的是**：一个真模型拿到这份系统提示和这 5 个工具之后，会不会按预期推进。

补齐只需要一件事：在有 key 的机器上

```powershell
easycirq run --goal "给这块板加一个 3.3V LDO" --project <uuid> `
    --endpoint <OpenAI 兼容端点> --model <模型名>
```

把输出补进 `references/harness-run.md` 第十节即可。
