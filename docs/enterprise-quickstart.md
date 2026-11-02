# EasyCirq 企业知识库：一页纸上手

> 这份是**最短可跑路径**。每一步都有实测输出，照着做能跑通。
> 完整说明见 [enterprise-onboarding.md](enterprise-onboarding.md)。

---

## 这是什么

让 EasyCirq 用**你自己公司的**规范、实测参数和标准电路来查板子，
而不用每次重讲。你加的文件放在自己电脑上，**不改程序、不重装**。

---

## 第 1 步：建目录，放一条规则

```bash
mkdir -p ~/.easycirq/knowledge          # Windows: New-Item -ItemType Directory $env:USERPROFILE\.easycirq\knowledge
```

新建 `~/.easycirq/knowledge/rules.json`：

```json
{
  "schema": "easycirq-enterprise-rules/v1",
  "rules": [{
    "id": "no-0402",
    "kind": "hard",
    "title": "禁用 0402 封装",
    "predicate": { "type": "footprint_forbidden", "patterns": ["0402"] },
    "evidence": "产线贴片下限 0603",
    "verified_on": "在一块 R0402 的板子上跑过，报 fail"
  }]
}
```

**两个字段别省**：

- `kind`：`hard` = 违反就拦住交付；`advisory` = 只提示
- `verified_on`：**写清这条规则曾经抓到过什么**。不写会被拒绝——
  工具能确认规则被加载，没法证明它真的会触发

---

## 第 2 步：确认工具读到了

```bash
python easycirq/scripts/enterprise_selfcheck.py
```

期望：

```
  规则：1 条
      [enterprise(默认)] /home/you/.easycirq/knowledge  1 个文件

✓ 全部可加载、无死规则、无死知识。
  注意：这只能证明「能用」；它到底抓不抓得到问题，要拿一块真板跑一次。
```

**看到 `✗` 就是有问题**，它会指出是哪个文件、哪个字段。

---

## 第 3 步：导出网表

```bash
easycirq sch list --include-bbox --include-pins > board.json
```

**大概率会报错，三种原因**：

| 报错 | 怎么办 |
|---|---|
| `AMBIGUOUS_WINDOW` | 加了多个 EDA 窗口 → 加 `--window <id>` |
| `AMBIGUOUS_PROJECT` | 同一项目多窗口，**只能**用 `--window` |
| `PRECONDITION_REFUSED` | 前台是 PCB → `easycirq doc ls` 查原理图名，加 `--doc <名字>` |

一次成功的写法：

```bash
easycirq sch list --include-bbox --include-pins --window <id> --doc <原理图名> > board.json
```

---

## 第 4 步：查板子

```bash
python easycirq/scripts/enterprise_rules.py --netlist board.json
```

两块板，两种结果：

```
# 干净板
企业规则判定：pass
  ✓ no-0402                      禁用 0402 封装
exit=0

# 有 0402 的板
企业规则判定：fail
  ✗ no-0402                      禁用 0402 封装  [hard] R1 的封装是 R0402
exit=1
```

---

## 第 5 步：把审核意见存下来

人审完指出问题时，记成条目（`ledger.json`）：

```json
{
  "schema": "easycirq-review-ledger/v1",
  "entries": [{
    "id": "R-001", "reviewer": "张工", "found": "这颗料停产了",
    "disposition": "rule",
    "rule": {
      "id": "banned-part", "kind": "hard", "title": "禁用停产器件",
      "predicate": { "type": "part_forbidden", "parts": ["S8050"] },
      "evidence": "供应商 2026-03 停产通知",
      "verified_on": "在一块用 S8050 的板子上跑过，报 fail"
    }
  }]
}
```

**`disposition` 必须你自己选，工具不替你判断**：

| 选 | 什么时候 | 后果 |
|---|---|---|
| `rule` | 能写成「对网表做一次确定性判定」 | **能拦住交付** |
| `knowledge` | 靠经验判断，算不出来 | 只做参考，**不拦** |

选错的两种后果都糟：知识当规则会天天误报被关掉；规则当知识就永远没人执行。

推进：

```bash
python easycirq/scripts/review_ledger.py --ledger ledger.json --promote
```

```
已写入 ~/.easycirq/knowledge/rules.from-review.json（1 条规则）
回读确认：加载到 1 条规则 id
写入目录：/home/you/.easycirq/knowledge
下次读取：/home/you/.easycirq/knowledge      ← 两行必须一样
```

**两行不一样就是写错地方了**，规则永远不会生效。

---

## 四个坑，提前知道

| 坑 | 表现 | 解法 |
|---|---|---|
| **库放进安装目录** | 升级后全丢 | 放 `~/.easycirq/knowledge/` 或配 `EASYCIRQ_KNOWLEDGE_DIR` |
| **器件实测值没生效** | 用了默认值，没提示 | 意图里也要写 `"part_key"`（两处都要） |
| **块写错字段** | `blocks ls` 看不到你的块 | 必填 8 个字段，报错会点出缺哪个 |
| **知识召回 0 条** | 以为坏了 | 不代表板子有问题，是库里没相关条目 |

---

## 出问题时先跑这三条

```bash
python easycirq/scripts/enterprise_selfcheck.py          # 库健康检查
python easycirq/scripts/enterprise_rules.py --describe   # 到底读了哪些文件
easycirq connector verify                                # 连接器版本对不对
```

**「我加了规则没生效」九成是这三个原因之一**：放错目录、文件名不是 `.json`、
`--promote` 写到了别处（看那两行路径是否一致）。

---

## 能承诺什么，不能承诺什么

| 能 | 不能 |
|---|---|
| 企业规则会加载并阻断 | 规则**没有**接进 19 项 KPI 门禁，要单独跑 |
| 知识会被检索出来 | AI **不能**自动从对话里提取规则，必须人写并选边 |
| 器件实测值进了判据 | 块里的 `pcb_layout` 约束**没有代码读**，写了等于装饰 |
| 块能被 `blocks ls` 看到 | 多台电脑之间**不会**自动同步库 |

---

## 一句话验收

> **故意造一块违规的板，看它报不报。**

报 = 生效了。不报 = 没生效，别信「加载了 N 条」。
