# 批量执行与提速

## 选择路径

- 小任务、现成完整计划：直接使用现有 `--plan`，不要额外拆模块。
- 同一 PCB 快照上的独立放置模块：用重复的 `--module-plan` 合批。
- 创建器件、原理图或铜修改：分别使用已有 materialize/compose、`easycirq sch compose/materialize` 或 `pcb_apply_plan.py --plan` 支持的路径；本次模块合批不支持这些操作。
- 模块存在执行依赖、必须观察中间结果或工具载荷过大：保持明确检查点分批。不是所有动作合成一个巨型队列。

## 模块输入

每个模块为 JSON 对象，坐标/尺寸单位与原适配器一致（mil），至少包含：

```json
{
  "partial": true,
  "base_semantic_sha256": "当前实测dump的semanticSha256",
  "placements": [
    {"designator": "R1", "x": 1200, "y": 900, "rotation": 0, "layer": 1}
  ]
}
```

模块必须显式声明 `partial:true`，绑定同一 dump 的语义哈希，位号互不重复。可提供 `project`、`doc`、`primitive_ids`；工具核验声明。省略旋转/层时沿用现有严格实测继承逻辑，不补零。显式 scope 只可等于该模块位号，不接受网络或 bbox 放大作用域。模块级 `board`、`keepouts`、`constraints`、铜操作等未支持字段直接拒绝，不能静默丢弃；公共约束使用已编译的 `--constraints` 输入。

哈希绑定只证明文件组合一致，不能证明文件仍是当前 EDA 状态。唯一写入者必须在当前项目/文档重新采集快照、维护写入归属；任何外部修改或不确定状态都先重读重算。

## 执行

从 Skill 根目录运行（路径由 Agent 准备）：

```text
python scripts/pcb_apply_plan.py --dump before.json --module-plan power.json --module-plan channel1.json --module-plan channel2.json --constraints constraints.json --project PROJECT --doc DOC --out-dump after.json --report batch-report.json --playbook-out batch-playbook.json
```

默认 dry-run，0 次 EDA 调用。原适配器会对合并后的全部放置同时预检，因此各自可行但合并碰撞的方案仍会拒绝。报告记录每个模块路径、原始字节 SHA-256、成员、基础快照与完整 assembled_plan；playbook 保留模块来源。

确认当前快照、权限及窗口归属后，在相同命令增加 `--apply --yes`。适配器一次调用现有 `easycirq apply`，仍保留 journal、save、reload、fresh dump 与作用域 diff。全 no-op 时不生成新队列、不调用 EDA；报告才是本次状态，不执行目录里遗留的旧 playbook。部分成功或超时先回读并重新生成差异，禁止全批盲重试。

本功能不是事务回滚或实时互斥锁。移动已有布线器件需要后续重布、连通性和 DRC，放置通过不能证明铜连接正确。

## 减少读写与返工

冻结快照供多个只读计算复用，不按器件重新 `list/read`。身份/库几何缓存可复用已核验条件；位置、网络、铜与布局决策在写入后失效。不要把缓存命中当作现场验证。

移动前检查空间，候选写入前联合校验；高风险网络先试布。每批检查受影响项、阶段结束检查相关门禁、最终完整验收。检查频率与依赖匹配，不减免最终验收。

## 可重复对照

从仓库根目录执行：

```text
python tools/benchmark_module_batch.py --out-dir work/module-batch-benchmark --runs 3
```

读取仓库双按键 LED 的冻结 12 器件快照，构造统一平移 1mil 的放置编译负载，对比逐器件编译与合批编译。验证有序修改指令完全一致，记录实际文件读取/标准化次数、生成的检查点数及 Python 准备耗时。队列中的 save/reload/dump 数量是计划统计，不是已执行的 EDA 调用。

这是离线编译对照：逐项方案均以同一冻结输入独立编译，不构成可直接顺序执行的现场计划；真实串行执行每批后要刷新快照。输入保留已有铜，本次不重布，因此也不是有效电气改板交付。已有完整 --plan 同样可一次编译，本功能收益来自自动合并分散模块，不宣称优于原生整板批量计划。

真实 A/B 需在两个隔离工程中从同一初始状态完成相同任务，保留相同连接、DRC、导图和保存重开验收，记录总墙钟、工具等待、读取/写入、重试、返工与成本。未执行前不得用离线耗时推算整板加速。
