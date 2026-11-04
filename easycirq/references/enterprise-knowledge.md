# 企业知识库：用客户自己的规范、实测值和标准块

> Agent 读这份来决定「什么时候该用企业知识、怎么用、什么不能承诺」。

## 什么时候读这份

用户（或客户）说了下面任何一句，就说明有企业知识要接：

- 「我们公司规定不能用 X」「按我们规范检查」「我们有内部设计规范」
- 「这颗料我们实测过，参数和手册不一样」
- 「用我们自己的标准电路」「上次这个模块我们是怎么画的」
- 「上次评审说的那个问题，别再犯」
- 「客户要求先出方案再画图」

**没有这些信号就别主动提**——企业没建库时一切都是空的，硬提会让用户以为功能不可用。

## 先分清两种「经验」，这是全部设计的核心

| 类型 | 例子 | 处置 | 能否阻断交付 |
|---|---|---|---|
| **可执行规则** | 禁用 0402；某型号停产；网络命名规范 | 变成判据 | **能** |
| **可检索知识** | 上次某拓扑振荡的原因；客户偏好先出方案 | 检索后参考 | **不能** |

**两条铁律，不许违反**：

1. **知识不许伪装成规则**。执行不了的条目放进门禁，会天天误报，最后被人关掉。
2. **规则不许降级成知识**。能自动查的必须自动查；写进知识库等于下次没人看。

判断标准只有一条：**这条意见能不能写成「对网表做一次确定性判定」？**
能 → 规则；不能 → 知识。**判错两边都致命，所以必须问用户，不许自己猜。**

## 网表从哪来（别踩这个坑）

所有脚本都要 `--netlist`。先导出：

```bash
easycirq sch list --include-bbox --include-pins > list.json
```

**大概率会失败**，三种原因逐个排：

| 报错 | 原因 | 解法 |
|---|---|---|
| `AMBIGUOUS_WINDOW` | 开了多个 EasyEDA 窗口 | 加 `--window <id>` |
| `AMBIGUOUS_PROJECT` | 同一项目开了多窗口，`--project` 也不够 | **只能** `--window` |
| `PRECONDITION_REFUSED` | 前台是 PCB 不是原理图 | `easycirq doc ls` 查名字，再加 `--doc <原理图名>` |

一次成功的写法：

```bash
easycirq sch list --include-bbox --include-pins \
  --window <id> --doc <原理图名> > board.json
```

**别忘了 `--include-bbox --include-pins`**：没有引脚和坐标，封装规则和知识检索都用不了。

## 三条命令，先看有什么再动手

```bash
# 规则：加载了什么、能不能判
python easycirq/scripts/enterprise_rules.py --describe
python easycirq/scripts/enterprise_rules.py --netlist <list.json>

# 知识：库里有什么、哪些永远检索不到
python easycirq/scripts/knowledge_search.py --audit
python easycirq/scripts/knowledge_search.py --netlist <list.json> --intent <intent.json>

# 器件实测值：某个键的有效参数 + 每个字段来自哪一层
python easycirq/scripts/enterprise_parts.py --resolve <part_key>
```

`--describe` 会打出**每个层读了哪个目录、哪些文件**。用户说「我加了规则但没生效」时，
先跑这个——最常见的原因是放错目录或文件名不是 `.json`。

## 企业库放在哪

| 层 | 位置 | 谁维护 |
|---|---|---|
| 企业 | `$EASYCIRQ_KNOWLEDGE_DIR`，未设时 `~/.easycirq/knowledge/` | 公司所有项目共用 |
| 项目 | `<项目>/.easycirq/knowledge/` | 本项目特有，覆盖企业层 |

块库单独一个变量：`EASYCIRQ_BLOCKS_DIR`。

**不需要改 EasyCirq 源码，不需要重装。**

## 沉淀人审意见：必须让用户选边

人工核查指出问题时，用 `review_ledger.py` 记成结构化条目。

**关键：你要主动问用户「这条是规则还是知识」，不能替他判断。**

```json
{
  "id": "R-2026-11-02-004", "reviewer": "张工",
  "found": "产线贴不了 0402",
  "disposition": "rule",
  "rule": {
    "id": "no-0402-packaging", "kind": "hard",
    "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
    "evidence": "规范 DS-2024-07 §3.2",
    "verified_on": "用一块 R0402 的板跑过，报 fail"
  }
}
```

`rule` 类必须给 `predicate` + `evidence` + **`verified_on`**。

**`verified_on` 是什么**：写清「这条规则曾经抓到过什么」。
工具能确认规则被加载，**无法证明它会触发**——谓词名写对、参数胡说，照样过语法校验，
然后永远不命中。这一栏是人对「它真的有用」的背书。**缺了会被拒绝，别绕过。**

推进：`python easycirq/scripts/review_ledger.py --promote`。它会写进企业目录并**回读确认**加载到。

**默认目录跟随 `EASYCIRQ_KNOWLEDGE_DIR`**，输出会打印「写入目录」和「下次读取」两行。
两行不一致就是写错了地方——这种时候规则存进去了但永远不会生效。

如果客户报「我加了规则没生效」，第一件事是让他把这两行贴出来。

## 支持的谓词（现在只有这四个）

| `predicate.type` | 参数 | 判什么 |
|---|---|---|
| `footprint_forbidden` | `patterns` | 封装名命中禁用模式（子串，不分大小写） |
| `part_forbidden` | `parts` / `lcsc` | 型号或立创 C 号在禁用列表 |
| `net_name_forbidden` | `patterns` | 网络名命中禁用模式（通配符） |
| `net_name_required` | `required_for` | 必须有以此开头的网络 |

**写不成的就标 `knowledge`，不要硬塞。** 不认识的谓词会作为 problem 报出并判 `not_run`。

## 器件实测值：优先级是「意图 > 企业库 > 内置默认」

**两处都要写，缺一处就不生效**（这是最容易踩的坑）：

1. 企业器件库里用 `--list-builtin --filter <关键词>` 查到的那个键
2. 意图里给对应开关加 `"part_key": "<同一个键>"`

只写第 1 步，实测值一条都用不上，而判据输出上看不出来——所以加了两个告警：
`ENTERPRISE_PARTS_UNUSED`（库非空但没人声明 part_key）、
`ENTERPRISE_PART_KEY_NOT_FOUND`（键对不上，会列出库里有哪些键）。

两个都是 advisory，不改判定。客户说"我把实测参数加进去了但没效果"时，先看这两条。


`design_validity` 加 `--enterprise-parts <path>` 就会用企业实测值，输出里带
`vgs_th_from` 说明用的是哪个来源。

意图显式声明与企业实测差超过 20% 时给 `VGS_TH_DISAGREES_WITH_MEASURED`（advisory）：
**不静默替换**，因为意图是针对这块板的选择，批次均值不该盖掉它。

## 你能承诺什么、不能承诺什么

**能说**：企业规则会加载并阻断；知识会被检索出来；实测值进了判据；块能被 `blocks ls` 看到。

**不能说**：

| 不能承诺 | 理由 |
|---|---|
| 「规则接入 19 项 KPI 门禁」 | **没接**。要单独跑 `enterprise_rules.py` |
| 「AI 能自动从对话里提取规则」 | **不能**。必须人写进 ledger 并选边 |
| 「块里的 `pcb_layout` 约束生效了」 | **没有任何代码读它**，写了等于装饰 |
| 「会自动同步到所有项目」 | 企业库在 `~/.easycirq`，项目库各自独立 |

**验证生效的唯一方法是故意造一块违规的板看它报不报。**
「加载了 3 条」不证明任何事——3 条参数全写错也是加载了 3 条。

## 交付前自检

```bash
python tools/verify_enterprise.py      # 12/12 才算闭环成立
```

每项都是正反例：违规板必须拦、干净板必须放行、相关知识必须召回、
无关上下文不许误召回、实测值必须真的出现在判据输出里。
