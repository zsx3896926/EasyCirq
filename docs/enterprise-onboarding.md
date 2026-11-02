# 企业接入指南：把自己的知识接进 EasyCirq

> 当前进度：**可执行规则**已能跑通（加载 → 执行 → 阻断）。
> **可检索知识**、**人审记录结构化**、**企业器件/块库**还没做，见文末「还没做的」。

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
| `part_forbidden` | `parts: ["S8050"]` / `lcsc: ["C1234"]` | 器件型号或立创 C 号在禁用列表 |
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

## 六、还没做的（别当成能用）

| 能力 | 状态 |
|---|---|
| 企业**可检索知识**（历史工程教训、客户偏好） | ❌ 未实现。现在只支持可执行规则 |
| **人审意见结构化沉淀**（人工核查指出问题 → 记录 → 下次生效） | ❌ 未实现。这是整个闭环的入口，最该做 |
| 企业**器件库补充**（器件手册里的实测参数覆盖） | ❌ 未实现 |
| 企业**块库**扩充 | ❌ 未实现 |
| 规则接进 19 项 KPI 门禁 | ❌ 未接。现在要单独跑一条命令 |

**当前能做到的闭环是**：企业写规则 → 放到知识目录 → 下次跑检查时自动加载并阻断。
**还不能做到的是**：人工审完之后，把"这次指出的问题"自动变成下一条规则。

后者的难点不在存储，在于**判断这条意见是规则还是知识**——那个判断目前需要人来做，
所以接口设计上必须让人显式选边，不能让工具猜。
