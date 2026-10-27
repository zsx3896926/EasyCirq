# 电源路径审计与宽走廊规划

## 使用场景

电源主干过细、局部加宽受限、需要比较多档走廊宽度时，先用本工具离线筛查，再用当前执行器形成受保护计划。纯分析不连接 EDA。

三个入口共享测量模型，均不修改工程：

```text
python scripts/power_routing.py audit board.json --net PWR --current 1.0 --from 100,200 --to 700,200 --from-layer 1 --to-layer 1 --layer-class external --oz 1 --dt-limit 10 --json evidence/power-path.json
python scripts/power_routing.py widen board.json --targets PWR=30 --report evidence/width-plan.json
python scripts/power_routing.py corridor board.json --net PWR --start 100,200 --goal 700,200 --layer 1 --widths 60,50,40,30 --json evidence/corridor.json
```

坐标和宽度为 mil。示例坐标仅来自回归合成板，实际任务必须由当前工程回读提供。电流、铜厚、温升目标由项目确定；10K、30mil等不是通用门槛。

从仓库根目录可用 tests/fixtures/power-preflight/model-board.json 替换 board.json 运行示例；它是合成测试板，不是可制造电路。

## 输出与通过边界

- audit：显式源/负载端点和层，禁止自动把最远焊盘当供电方向。输出实际所选模型路径、逐段压降/温升估计、轨迹模型中的桥候选及移除后受影响焊盘。源文件SHA绑定输入，不代表文件仍是当前现场。
- 拓扑节点包含铜层；不同层坐标重合不连接。过孔/通孔跨层连接需明确跨度和镀孔事实，缺失不猜。正吸附容差、未连接负载或未覆盖铜会阻止完整模型通过。
- 温升仅为IPC-2221外层简化筛查。显式 external 不会使内层自动成为外层；分支电流、焊盘/过孔载流、邻近铜及实际温升仍需另核。所选路径赋全电流是保守情景，不是电流分配求解。
- widen：部分加宽后仍低于目标继续列为 requirements_unmet；同时检查计划之间的冲突。端点焊盘限制只作为 neck_review 线索，不能推出改道必然无效，也不自动豁免载流责任。
- corridor：feasible只描述已建模障碍下的候选，不是电气/阻抗/DRC通过。搜索未找到写 not_found_within_grid，不宣称物理无解。净距至少遵守当前dump规则；忽略障碍或不支持几何必须标缺口。
- 退出0仅是覆盖条件下的模型结果/候选；1是已观察到未满足要求；2是输入无效或覆盖不完整。所有输出都不是现场验收。

## 几何、层和覆盖

保留回读焊盘width/height，避免90°尺寸重复交换。RECT/轴向OVAL及圆形支持相应距离模型；非圆椭圆、特殊形状、未知旋转约定使用保守边界并记录approx，不假称exact。

规则缺失、非有限数字、非法尺寸等拒绝输入。铜层ID不等于层用途：2不写死成内层，层栈用途来自当前工具回读。未知via跨度作为保守障碍，不能据此证明跨层连通。

器件本体不按J/U/L前缀自动硬禁布，也不按同网整器件豁免。需要机械/器件禁布时显式提供规则中的hard_body_designators，或使用完整设计引擎约束；本工具没有覆盖的禁布区不得被宣称已检查。

铺铜、平面、弧、规则区域、特殊焊盘等未实现完整模型时，报告incomplete并保留候选。显式空数组与未测到不是同义。工具输出保留source/coverage/live_verified:false（audit的字段为input_sha256），不能把候选升级为门禁PASS。

## 写入与验证

不输出无守卫的删线/重建shell命令；旧--emit-cli明确拒绝。Agent应结合新鲜工程/文档/窗口身份和快照，经现有受保护计划分逻辑批次执行，失败先回读只补差量。多窗口显式路由，遵循唯一写入者规则，不要求无条件关闭用户窗口。

铜变更后按需要重建铺铜，保存→reload→fresh dump，再采集原生DRC与关键网连接证明。只改丝印不机械触发全板重铺；原生DRC不替代载流、温升、EMC、音质或实物验证。

## 回归与来源

运行 python -m unittest discover -s tests -p "test_power_*.py"。公开样例是最小合成反例；用户r23完整板留本机回放，未提交公开库。覆盖矩形内部穿铜、跨层误连、NaN、板规覆盖、加宽未达目标、旋转尺寸和缺测不假绿。

来源为用户提供的pcb-preflight-skill-patch.zip；保留其离线审计/多档寻路思路，修正已复现错误。原包11项通过不代表新边界测试通过。说明与验证记录见仓库docs/power-preflight/。
