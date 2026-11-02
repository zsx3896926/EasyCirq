# 企业接入指南：把自己的知识接进 EasyCirq

> 当前进度：**可执行规则**已能跑通（加载 → 执行 → 阻断）。
> **可检索知识**、**人审记录结构化**、**企业器件/块库**还没做，见文末「还没做的」。

## 目录

- 一、先分清两种「经验」
- 二、放哪里
- 三、规则怎么写
- 四、怎么跑
- 五、怎么确认「真的生效了」
- 六、人审记录：把「人指出的问题」变成下次的资产
- 七、知识类条目：存了还要能被检索到
- 八、企业器件库：实测参数要真的被判据用上
- 九、一条命令验证整个闭环
- 十、企业自建块库：加自己的标准电路
- 十一、升级会不会丢库
- 十二、还没做的（别当成能用）

## 零、先把网表拿出来（第一个坑）

下面所有命令都要 `--netlist <list.json>`。**这个文件不会自己出现**，得从 EasyEDA 导出。
我第一次按自己写的文档走，就在这里卡住了三次。

### 正确命令

```bash
easycirq sch list --include-bbox --include-pins > list.json
```

### 但它大概率直接报错，原因有三

**① 开了多个 EasyEDA 窗口 → `AMBIGUOUS_WINDOW`**

```
message: 2 connector windows are connected; the target is ambiguous
detail : pass --project <name> (preferred) or --window <id>. Connected now:
         6caac012-... [project=Fan-Controller-12V doc=pcb], bac2292b-... [...]
```

加上 `--window <id>` 就行。

**② 同一个项目开了多个窗口 → `AMBIGUOUS_PROJECT`，这时 `--project` 也不够**

```
message: multiple connected windows match project "Fan-Controller-12V"
detail : pass --window to pick one: 6caac012-... [doc=pcb], bac2292b-... [doc=pcb]
```

**只能靠 `--window`**。`--doc` 帮不上忙——两个窗口的前台文档都是 `pcb`。

**③ 前台是 PCB 不是原理图 → `PRECONDITION_REFUSED`**

```
message: schematic.components.list needs a schematic document, but the foreground
         document is pcb "696988895f5e0343". Retry with --doc set to the target
         schematic name or uuid (list them with `easycirq doc ls`)
```

先查有哪些文档：

```bash
easycirq doc ls --project <项目名>
```

```
    TYPE       NAME    UUID
★   pcb        PCB1    696988895f5e0343      ← ★ 是前台
    schematic  P1      664436e68d969739
```

然后指定**原理图**的名字或 uuid。

### 一次成功的完整写法

```bash
easycirq sch list --include-bbox --include-pins \
  --window 6caac012-8d84-4cab-8bc7-c61aa8aaa463 --doc P1 > board.json
```

实测输出：`ok: true`，28 颗器件。

> `--include-bbox --include-pins` 要带上：没有引脚和坐标，后面的企业规则查不了封装，
> 知识检索也抽不出上下文。

### 报错看不懂时

上面三类错误的 `message` / `detail` **都说清了下一步该做什么**。照着做就行。
如果你看到的是 `[object Object]` 之类的空话，那是连接器版本太旧——先跑
`easycirq connector verify`（应显示连接器 1.0.21）。

## 一、先分清两种「经验」


企业想让 EasyCirq 学会自己的经验，但经验分两类，**性质完全不同**：

| 类型 | 例子 | 处置 | 能否阻断交付 |
|---|---|---|---|
| **可执行规则** | 「禁用 0402 封装」「S8050 已停产不许用」 | 变成判据，进检查链 | **能** |
| **可检索知识** | 「上次这拓扑振荡，原因是…」「客户 A 要求先出方案」 | 检索库，AI 审阅时参考 | **不能** |

**两条铁律**：

1. **知识不许伪装成规则。** 执行不了的条目不许进出门禁——它天天误报，
   最后被人关掉，等于没写。
2. **规则不许降级成知识。** 能自动查的必须自动查。写进知识库＝下次没人看。

判断标准很简单：**能不能写成"对网表做一次确定性判定"？** 能，就是规则；不能，就是知识。

## 二、放哪里


企业规则放在下面任一位置（**越靠后优先级越高**）：

| 层 | 位置 | 用途 |
|---|---|---|
| 企业 | `$EASYCIRQ_KNOWLEDGE_DIR`，未设置时用 `~/.easycirq/knowledge/` | 公司级规范，所有项目共用 |
| 项目 | `<项目>/.easycirq/knowledge/` | 本项目特有要求，覆盖企业层 |

规则文件是 `*.json`，放进目录即可，**不用改 EasyCirq 源码，不用重装**。

## 三、规则怎么写


```json
{
  "schema": "easycirq-enterprise-rules/v1",
  "layer": "enterprise",
  "rules": [
    {
      "id": "no-0402-packaging",
      "kind": "hard",
      "title": "禁用 0402 封装",
      "predicate": { "type": "footprint_forbidden", "patterns": ["0402"] },
      "evidence": "企业设计规范 DS-2024-07 §3.2",
      "owner": "硬件部 张工"
    }
  ]
}
```

### `kind` 只有两个值，语义必须分明

| 值 | 含义 | 对返回码 |
|---|---|---|
| `hard` | 违反即失败 | **影响**（exit 1） |
| `advisory` | 只提示 | 不影响（exit 0） |

**默认 `hard`**，要降级必须显式写 `advisory`。
反过来（默认 advisory）会让企业以为规则生效了、其实没有。

`evidence` 和 `owner` 不是装饰：人被拦下来时要能知道**依据哪条规范、找谁商量**。

### 现在支持的谓词

| `predicate.type` | 参数 | 判什么 |
|---|---|---|
| `footprint_forbidden` | `patterns: ["0402"]` | 封装名命中禁用模式（子串匹配，不分大小写） |
| `part_forbidden` | `parts: ["S8050"]` / `lcsc: ["<你的立创C号>"]` | 器件型号或立创 C 号在禁用列表 |
| `net_name_forbidden` | `patterns: ["test*", "tmp*"]` | 网络名命中禁用模式（通配符） |
| `net_name_required` | `required_for: ["VCC_"]` | 必须有以此开头的网络 |

**写错谓词名不会被静默跳过**——会作为 problem 报出来、判定 `not_run`。
（这条是刻意的：静默跳过等于"存了但没生效"。）

## 四、怎么跑


```bash
# 只看加载了什么（先确认读到了哪些文件）
python easycirq/scripts/enterprise_rules.py --describe

# 对一块板跑规则
python easycirq/scripts/enterprise_rules.py \
  --netlist deliverables/fan-controller/snapshot/list.json

# 临时指定某份规则文件（优先级最高）
python easycirq/scripts/enterprise_rules.py --netlist <list.json> \
  --rule examples/enterprise-knowledge/rules.company.json
```

返回码：`0` 全过 / `1` 有 hard 违规 / `2` 有规则判不了。

## 五、怎么确认「真的生效了」


**别只看"加载了 3 条"。** 三条都写上，但谓词写错了，一样是 0 条生效。所以按这个顺序验：

1. `--describe` 确认**文件被读到**（会列出每个层的目录与文件名）
2. **故意造一块违规的板**，确认它报 `fail`（这是唯一能证明规则在执行的证据）
3. 拿真实项目跑一遍，确认该过的过

第 2 步的样例：

```bash
python easycirq/scripts/enterprise_rules.py \
  --netlist reports/fan-controller/evidence/21-enterprise-violations.json \
  --rule examples/enterprise-knowledge/rules.company.json
# 期望 exit=1，且三条规则各报一条违规
```

## 六、人审记录：把「人指出的问题」变成下次的资产


人核查时指出的问题，不要留在聊天记录里。记成结构化条目：

```bash
python easycirq/scripts/review_ledger.py --ledger .easycirq/review-ledger.json --list
```

### 每条必须显式选边

```json
{
  "id": "R-2026-11-02-004",
  "reviewer": "张工",
  "found": "产线贴不了 0402",
  "disposition": "rule",
  "rule": {
    "id": "no-0402-packaging",
    "kind": "hard",
    "predicate": { "type": "footprint_forbidden", "patterns": ["0402"] },
    "evidence": "规范 DS-2024-07 §3.2",
    "verified_on": "用一块 R0402 的板跑过，报 fail"
  }
}
```

| `disposition` | 必须有 | 处置 |
|---|---|---|
| `rule` | 可执行 `predicate` + `evidence` + **`verified_on`** | 进企业规则，**能阻断** |
| `knowledge` | `title` + `body` | 进检索库，**不阻断** |

**工具不替你判断是规则还是知识。** 判错两边都致命：知识当规则会误报被关掉，
规则当知识会漏执行。判断标准只有一条：**能不能写成「对网表做一次确定性判定」**。

### `verified_on` 是干什么的

**工具只能确认规则能被加载，无法证明它会触发。** 谓词名写对、参数是胡说，
照样通过语法校验，而它永远不会命中——那是最坏的情况（存了但没生效）。

所以要求人写一条「这条规则曾经抓到过什么」。这是人对「它真的有用」的背书，
不是工具能替你做的。**做不到的检查，工具就该明说做不到，而不是假装过了。**

### 推进去，并回读确认

```bash
python easycirq/scripts/review_ledger.py --ledger .easycirq/review-ledger.json --promote
```

它会写进企业规则目录，然后**立刻对着那个目录回读**，确认规则 id 真的出现在加载列表里。
只写不验等于没数。

**默认目录跟着 `EASYCIRQ_KNOWLEDGE_DIR` 走**，和读取规则时一致。输出会把两个路径都打出来：

```
已写入 .../company-lib/rules.from-review.json（1 条规则）
回读确认：加载到 1 条规则 id
写入目录：.../company-lib
下次读取：.../company-lib     ← 两个不一致就是有问题
```

> 这一条是真踩过的：早先默认写死 `~/.easycirq/knowledge`，设了环境变量的客户
> 规则被写到别处，而回读把环境变量临时改成写入目标，于是报「加载成功」——
> **下一次真实运行一条都读不到**。工具主动把「存了」说成「生效了」。

实测闭环：

```
已写入 ~/.easycirq/knowledge/rules.from-review.json（1 条规则）
回读确认：加载到 1 条规则 id
```

然后**不加任何参数**，那块违规板就被拦住了：

```
企业规则判定：fail
  ✗ no-0402-packaging  禁用 0402 封装  [hard] R1 的封装是 R0402
exit=1
```

干净板：

```
企业规则判定：pass
exit=0
```

## 七、知识类条目：存了还要能被检索到


规则类已经能阻断。知识类如果只是「存起来了」，它就和没人读的字段一样。
用检索把它们接进审阅：

```bash
python easycirq/scripts/knowledge_search.py   --netlist deliverables/fan-controller/snapshot/list.json   --intent  deliverables/fan-controller/design/intent.json
```

实测输出：

```
这块板检索到 1 条企业知识（共 3 条）
  上下文：负载 200mA；负载类型 inductive；PWR5V=5.0V；PWR12V=12.0V；回差 3°C；传感器 ntc；有容差声明
  · [10] R-2026-11-02-002  这类分压电阻不必上 1% 精度
         命中：tag:容差
```

### 三条设计约束

1. **可解释**：每条召回都给 `matched_on`（命中了什么词）。说不出为什么召回的检索，
   人没法判断该不该信。
2. **不阻断**：知识不是门禁。召回多少都不改交付判定，返回码永远是 0
   （除非输入错误或知识失效）。知识伪装成门禁会被误报拖垮。
3. **没被召回的知识是死的**：

```bash
python easycirq/scripts/knowledge_search.py --audit
```

审计查两件事：

| 检查 | 说明 |
|---|---|
| 没有任何可检索文本 | 标题/标签/正文全是空或停用词 → 永远不会召回 |
| **用自己的标签查不回自己** | 标签和内容对不上，分拣作用失效 |

### 检索用关键词不用向量，是因为要可测

向量相似度不可解释、LLM 检索不可复现，两者都写不成
「故意构造一个上下文 → 必须召回某条」的测试。关键词匹配牺牲召回率换可验证。

**已知局限（不装）**：同义词不匹配（写「去耦」不会命中只写 decoupling 的条目）、
中文按 2-gram 朴素切分。所以 `--audit` 会提示补 tags。

**纯数字不当检索词**：实测发现正文里的 `XH2.54` 会切出 `54`，导致连接器那条知识
被任何含 54 的板误召回。带单位的数字（`200ma`、`12v`）保留，它们有意义。

## 八、企业器件库：实测参数要真的被判据用上


器件手册给的是**保证范围**，不是实际值。企业自己测过更准的数，就该被设计判据用上。

```json
{
  "schema": "easycirq-enterprise-parts/v1",
  "parts": {
    "mosfet.ao3400a_sot23": {
      "value": "AO3400A", "mpn": "AO3400A",   // lcsc 填你自己核过的编号
      "deviceUuid": "84f69a83e2c34d168d19d16f0d252938",
      "footprint": "SOT-23-3_L2.9-W1.3-P1.90-LS2.4",
      "measured": {
        "vgs_th": 1.3,
        "note": "2026-09 批次 30 颗抽测均值；手册保证 0.65–1.45V"
      }
    }
  }
}
```

### 每个字段都能说出它来自哪一层

```bash
python easycirq/scripts/enterprise_parts.py \
  --parts parts.company.json --resolve mosfet.ao3400a_sot23
```

```
value        = 'AO3400A'      ← explicit
deviceUuid   = '84f69a83...'  ← explicit
basic        = True           ← builtin
desc         = '...Vgs(th) 1.05V, Id 4A'  ← builtin
measured     = {'vgs_th': 1.3, ...}       ← explicit
条目来源: examples/enterprise-knowledge/parts.company.json
```

**合并是字段级的**，不是整条替换——企业只想补一个实测值，不该被迫把
`deviceUuid` 也抄一遍（抄漏一个就是一条坏料）。歧义靠**逐字段标注来源**消解：
看见 `vgs_th ← explicit` 和 `basic ← builtin`，人立刻知道哪些是企业改的。

### 判据真的会用上（这是关键）

```bash
python easycirq/scripts/sch_design_validity.py \
  --netlist .../list.json --intent .../intent.json \
  --enterprise-parts parts.company.json
```

意图里不写 `vgs_th`、只给 `part_key` 时，判据输出：

```json
{"vgs_th": 1.3, "vgs_th_from": "企业实测（parts.company.json）", "vgs": 5.0}
```

**优先级**：意图显式声明 > 企业实测 > 内置默认。三者都会在 `vgs_th_from` 里标出来。

意图与企业实测差超过 20% 时给 `VGS_TH_DISAGREES_WITH_MEASURED`（advisory）：
判据仍用意图值（那是**这块板的选择**），但提醒你两边对不上。

### 为什么优先级是「意图 > 企业库」

企业库说的是"这颗料的实际参数"，意图说的是"这块板怎么用"。
后者是针对具体项目做的决定，不能被人测的平均值悄悄盖掉。所以冲突时
**保意图、提示差异**，而不是静默替换。

## 九、一条命令验证整个闭环

前面九节各讲一块。真要用起来，跑这个：

```
python tools/verify_enterprise.py
```

它不是"列加载了几条"，而是**每条资产都跑一次正反例**：

```
── S1/S3 企业规则 ─────────────────────────────────────
  ✓ 加载：3 条
  ✓ 故意违规板 → 必须拦住（实际 exit=1）
  ✓ 干净板 → 必须放行（实际 exit=0）

── S4 企业知识检索 ────────────────────────────────────
  ✓ 相关的被召回：['R-2026-11-02-002']
  ✓ 每条召回都说得出命中什么
  ✓ 无关上下文不误召回（数字噪声）

── S5 企业器件库 ──────────────────────────────────────
  ✓ 实测 vgs_th=1.3 在有效参数里
  ✓ 意图不写该参数时，判据用企业实测值并标出来源

── S2 人审记录闭环 ────────────────────────────────────
  ✓ 记录校验（选边 + verified_on）
  ✓ 推进并回读确认加载
  ✓ **不加任何参数**，下一块违规板被拦住（实际 exit=1）

生效验证：12/12 项通过
企业知识系统闭环成立：规则能拦、知识能检索、实测值能用、人审能沉淀。
```

**为什么必须跑正反例**：一条规则"加载成功"不代表它活着。
谓词写错、参数胡说，照样能通过语法校验，然后永远不触发——
那是本目标反复要防的「存了但没生效」。

同样的道理适用于知识和器件实测值：一条谁都检索不到的知识、
一个判据根本没用上的实测参数，和没写一样。

`tests/test_verify_enterprise.py` 把这个演练钉成回归测试：
任何一条链断了，它必须返回非零。

## 十、企业自建块库：加自己的标准电路

块库原本是编译进二进制的（`go:embed`），企业加块就得重编 EasyCirq——
这不对，企业自己的标准电路恰恰最该能自己加。

现在有一个外部目录：

```
export EASYCIRQ_BLOCKS_DIR=/path/to/company-blocks      # Linux/macOS
$env:EASYCIRQ_BLOCKS_DIR = "D:\company-blocks"          # Windows
```

目录里的 `*.json` 会被加载，**同 id 覆盖内置块**。

### 一个企业块长什么样

和内置块格式一致，改 `id` 和内容即可：

```json
{
  "id": "block.company_threshold_switch",
  "desc": "企业改版：NTC 阈值 + 回差 + 12V 感性负载开关（栅极上拉 47k，配合实测 Vgs(th)=1.3V）",
  "category": "sensing",
  "author": "@company-hardware",
  "parts": { "…": "…" },
  "internal_nets": [ ["R.1", "PORT:PWR5V"], "…" ],
  "ports": { "…": "…" }
}
```

### 验证它真的被看到

```bash
easycirq blocks ls | grep company      # 设了环境变量后应出现
easycirq blocks show block.company_threshold_switch
```

实测：

```
block.company_threshold_switch   ready  sensing  @company-hardware  企业改版：…
```

**不设环境变量时看不见**——内置行为完全不变，回归测试
`TestNoEnvKeepsBuiltinBehaviour` 钉住这条。

### 坏的块会 loudly 失败

块的 `id` 为空或 JSON 坏了，`Load()` 直接报错并**点出文件名**，不会静默跳过。
企业用 `blocks ls` 看不到自己的块时，先看报错说了哪个文件。

### 边界

- **只加块，不改内置块的行为**：同 id 覆盖是显式选择
- 块里的器件仍要能在标准件库里解析（`block-apply` 用 `standard-parts.json`
  把 role 映射到真实 deviceUuid）；企业特有的料请同时放进企业器件库
- 块里的 `pcb_layout` 约束**目前没有任何代码读**，写了等于装饰（见最后一节）

## 十一、升级会不会丢库

**不会——前提是库放在正确的位置。** 这一节说清哪些会被替换、哪些不会，以及一个容易犯的错。

### 两个目录是分开的

| 目录 | 放什么 | 升级时 |
|---|---|---|
| `%LOCALAPPDATA%\EasyCirq\`（对应安装目录） | 程序本体、内置技能、内置标准件 | **整个替换** |
| `~/.easycirq/` | 运行状态：`knowledge/`、`audit/`、`backups/`、`workflow/` | **不碰** |

依据（可自行核对）：

- 安装器的删除/替换动作只作用于 `install_dir`（`distribution/easycirq_install.py` 里的
  `_replace_dir(install_dir, displaced)` 与 `_rmtree(install_dir)`），失败时会把
  `displaced` 搬回来
- 运行时的状态目录由 `stateDir()` 算成 `~/.easycirq`（`runtime/internal/app/cmd_doctor.go`），
  与安装目录**没有包含关系**
- 安装器自己的记录放在 `install_dir.parent/.easycirq-install-state/<hash>/`，
  也不在 `~/.easycirq` 里

### 所以你的库要放在这三个位置之一

```
~/.easycirq/knowledge/                 ← 默认企业库，升级不丢
%YOUR_DIR%\company-lib\              ← 配 EASYCIRQ_KNOWLEDGE_DIR，最保险
<项目>/.easycirq/knowledge/            ← 跟着项目走，本就在版本管理里
```

### 一个容易犯的错

**别把库放进安装目录。**

```
%LOCALAPPDATA%\EasyCirq\knowledge\     ← 错的：升级时整个目录被替换，全丢
```

看起来"放在工具旁边很方便"，但那是唯一会被清空的地方。

放完用自检确认工具看到的是对的位置：

```bash
python easycirq/scripts/enterprise_selfcheck.py
```

它会打出 `[enterprise(默认)] ~/.easycirq/knowledge` 或 `[enterprise(env)] <你的目录>`
——**看到 `%LOCALAPPDATA%` 就是放错了**。

### 还没实测的部分

上面是**读代码得出的结论**，不是跑了一遍真实升级。真机升级验证需要在一台装过旧版的
机器上跑完整安装包，目前没有做。

所以：**库放对位置就不用担心**；如果要在生产环境升级，第一次升级前把
`~/.easycirq/knowledge/` 备份一份，升完跑一次自检对比条数。


## 十二、还没做的（别当成能用）

| 能力 | 状态 |
|---|---|
| 企业可检索知识（历史工程教训、客户偏好） | ✅ 已实现（第七节） |
| 人审意见结构化沉淀 | ✅ 已实现（第六节） |
| 企业器件库补充（实测参数覆盖） | ✅ 已实现（第八节） |
| 企业块库扩充 | ✅ 已实现（第九节） |
| **规则接进 19 项 KPI 门禁** | ❌ **未接**。现在要单独跑 `enterprise_rules.py`，不是门禁的一环 |
| **AI 主动从对话里提取候选条目** | ❌ 未实现。仍需人写进 ledger 并显式选边 |
| **块库的 `pcb_layout` 约束** | ❌ 未实现。块里的 `pcb_layout` 字段没有任何代码读它，写了等于装饰 |

### 剩下这三项为什么不修

- **接进 KPI 门禁**：加第 20 项要改指标定义、阈值和四处重复的表格，属于**契约变更**。
  按"不为通过而改判据"的同一条原则，也不该随手加。
- **AI 提取候选条目**：难点不在技术，在**判断一条意见是规则还是知识**。
  判错两边都致命（误报被关掉 / 漏执行），所以必须人显式选边，工具不能猜。
- **块库 `pcb_layout`**：它需要一套约束语言和一个消费它的检查器。
  只往字段里写文字，没有代码读，就是本目标第 30 轮已经栽过的那种装饰。
