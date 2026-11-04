# 离线布局与布线

> 对**已捕获**的板子离线布通、给出 11 项 KPI、在门禁红时拒绝上机。
> 不碰在线编辑器；吃 dump + 放置文件。
>
> 入口：`easycirq layout <子命令>`。工具链在 `scripts/layout/`，纪律见该目录 `WORKING-RULES.md`。

---

## 一、什么时候用它

| 场景 | 用它 |
|---|---|
| 想知道"这块板离能交付还差多远、为什么" | `feasibility` → `gaps_check` |
| 想在一个方案上真的布一遍并量化 | `pipeline` |
| 改了几个参数，想比较 | `sweep --jobs N` |
| 改了工具链本身 | `verify` |

**不适用**：在线改板、DRC 豁免、替人决定换不换器件。

---

## 二、八条纪律（R1–R8）

这八条不是流程装饰，每一条都是**用浪费的轮次换来的**。按顺序遵守：

| # | 规则 | 具体动作 |
|---|---|---|
| **R1** | **先算边界，再搜索** | 任何新板/新目标，先跑 `feasibility`。如果几何下界已经超过目标，**停下来指认必须改什么**，不要开始搜 |
| **R2** | **合法性与可制造性是门禁，不是 KPI** | 重叠器件、焊盘 ≥ 节距、焊盘小于自己的孔、板子规则低于布线器自己的过孔、DFM 发现——**全部必须让流水线失败**，而且从第一天就要失败 |
| **R3** | **并行求值、全部缓存** | 多于一个配置就 `sweep --jobs N`；缓存键是内容哈希，文档改一下不会让重跑变慢 |
| **R4** | **没有校准过的廉价筛选，绝不用来排序** | 用快筛挑赢家前先 `sweep --calibrate <交付轮次>`，Spearman ≥ 0.8 才准 |
| **R5** | **只留极端点，每个确认一次** | 保留 3–4 个非支配点（间距最优、等长最优、折中），不要十五个中间值；每个对外结论在交付档位确认一次 |
| **R6** | **候选是数据，文档由运行生成** | 加一个候选（改板 + 配方 + 常量 + 实测记录），**不要手改数字**；表格从运行生成 |
| **R7** | **连续三轮没改善 → 换问题** | 不是调参，是改问法：转向根因/边界分析，或者换器件 |
| **R8** | **计划不是结果** | 未跑标 `NOT RUN`；数字必须附产生它的命令；"完成"= 命令退出 0 且断言值成立 |

**这八条适用于任何"搜索 + 指标"的工作**，不只是布局。

---

## 三、一条命令的诚实结论

`easycirq layout gaps_check --candidate all` 给四个合法点：

| 候选 | CAM 窗口 | SoC 焊盘 | 间距 | CAM 等长 | LCD | SD |
|---|---|---|---|---|---|---|
| **frontier-i** | 17..24 | 26×26 | **146** | 837.8 | 41.4 | 31.9 |
| frontier-g | 13..20 | 36×36 | 180 | 398.6 | 41.4 | 31.9 |
| frontier-j | 11..18 | 26×26 | 217 | **121.8** | 41.4 | 31.9 |
| frontier-h | 13..20 | 26×26 | 232 | 144.9 | 41.4 | 31.9 |

**没有任何一点同时满足「间距归零 + CAM < 50」。**

原因是硬事实，不是算法没调好：

> **J3 是 19.7 mil 节距，U5 焊盘 50 mil，8 针跨度差 212 mil
> ⇒ 等长几何下界 √(D²+Δ²) − D = 53–67 mil。**
> **不换连接器做不到 < 50 mil。**

按间距优先（D8）主候选是 `frontier-i`；把等长提前则是 `frontier-j`。**这条排序要工程师确认。**

---

## 四、它做不到的事（不要替它宣称）

| 做不到 | 原因 |
|---|---|
| 让 RetroCam-02 `deliverable: YES` | 上面那条几何下界。需要不同连接器封装 / SoC 扇出 |
| 出可上机的 Gerber 包 | 输出语法有效、回读通过，但**没过 CAM 验证**；槽孔刻意不发；没有带 LCSC 料号的 BOM |
| 担保阻抗/电流/热正确 | 全部跑在**标注假设**上，直到真实的叠层/负载/功耗进来 |
| 判装配间隙、拼板、Mark、钢网 | 需要工艺卡与装配数据 |

**它能做的是：** 证明 self-test 板**可以**变绿（间距 0、等长 0.0、`deliverable: YES`、契约 PASS）——
所以链路本身是通的，只是这块板的物理做不到。

---

## 五、门禁与安全

- **门禁红时 `emit_apply` 退出 2 且什么都不写**（有断言）
- **从未写入真实板**
- **PCB DRC 不可豁免**
- 已撤回的候选（`frontier-d/e/f`、`recipe-only`）被 `regress` **拒跑**，不是"跑得慢"

---

## 六、常用命令

```bash
easycirq layout verify                      # 14 项健康检查（约 6 s）
easycirq layout feasibility                 # 先算边界（R1）
easycirq layout pipeline --candidate frontier-i --out-dir out/fi
easycirq layout gaps_check --candidate all
easycirq layout equivalence --iters 3 --write     # 改内循环前：记录产物指纹
easycirq layout equivalence --iters 3 --compare   # 改完后：plan 必须逐字节相同
easycirq layout bench --iters 3 --compare         # 再确认 KPI 指纹一致并看时间
easycirq layout sweep --jobs 4 --calibrate 70
easycirq layout regress --candidate frontier-i
```

板子数据默认用**随包夹具**；要指别处：
```
EASYCIRQ_LAYOUT_BOARD=/path/to/board-dir easycirq layout gaps_check
```

---

## 七、给 AI 的一句话

**先跑 `feasibility`，再决定要不要搜。** 在这条纪律之前，这个项目花了约 20 轮调参，
才在 §127 意识到问题不在参数——是连接器的物理决定了不可能。
