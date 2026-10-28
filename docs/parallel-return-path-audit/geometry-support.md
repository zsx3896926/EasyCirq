# 几何支持范围与算法说明（v1）

工具：`design-hardware/scripts/return_path_audit/`（`python -m return_path_audit`）
性质：离线、纯标准库、几何/拓扑审查。无 EDA、无场求解、无浮点“近似求交冒充可靠结果”。

## 1. 支持的几何

| 类别 | v1 支持 | 说明 |
|---|---|---|
| 信号路径 | 直线段 `kind=straight` | 端点、层、宽度、声明长度 |
| 过孔/焊盘 | 圆形 | 只用于跨度/网络/连接证据与距离，不当作参考铜面 |
| 参考铜 | 简单多边形（外环 + 孔洞环） | 可多块、可同网/异网、可凹多边形 |
| 板框 | 闭合多边形（可带孔） | 仅用于范围与合理性，不参与回流判定 |
| 层叠 | 任意层数、显式物理顺序 | 支持标准四层与非标准四层，不写死角色 |
| 单位 | `mm` / `mil` | 全输入统一单位；阈值同单位；不自动猜单位 |
| 容差 | 单一 `board.geometry_tolerance` | 退化判定与“容差附近”分类的唯一来源 |

## 2. 明确不支持（必须计入 unknown，不得忽略后判 PASS）

- 圆弧/贝塞尔/样条走线（`kind ∈ {arc, polyline, unsupported}`）；
- 非多边形铜：原生铺铜填充算法内部结构、热焊盘辐条、复杂热隔离、网格铺铜；
- 任意 Gerber/ODB++ 解析、盲埋孔的多层堆叠细节（只按声明的 from/to 物理跨度）；
- 铜厚/介质材料对阻抗、损耗、场分布的影响；
- 任何电磁场、串扰、眼图、阻抗、EMI 求解；
- 真实 EDA 或宿主渲染（本工具不调用 EDA，SVG 只是本地分析叠加图）。

未支持对象必须通过 `unsupported[]` 或非直线 `kind` 显式声明；其长度计入
`unknown_length`，整网状态为 `incomplete`，**绝不**因为“能检查的部分没问题”就把整网标 PASS。

## 3. 覆盖判定算法（为什么不会漏掉窄缝）

设信号段中心线 `p(t)=p0+t·d`，要求半宽
`h = width/2 + corridor`（`corridor` 来自声明阈值，缺失按 0 并记录假设）。

1. 收集**所有分类可能改变**的参数 `t`：
   - 中心线与每条铜边界边相交的点（进入/离开铜）；
   - 中心线到边界**直线**距离 `= h` 的根（条带边界，线性函数 ⇒ 闭式解）；
   - 中心线到边界**顶点**距离 `= h` 的根（端帽圆，二次方程闭式解）；
   - 端点 `t=0,1`；
   - 上下文铜（其他网络）的边界交点（用于区分“真缺口”与“跑到别的参考网上”）。
2. 在相邻断点之间取中点分类：`safe / corridor_insufficient / void /
   wrong_reference_net / borderline`，并用中点判断“是否在铜内、离边界多远”。
3. 分区间长度 = `(t1−t0)·段长`，风险区间按相邻合并为 risk run，保留
   `void_length / corridor_length / wrong_net_length` 三个分量。

**关键性质**：断点是“所有可能变化点”的超集，区间内部状态恒定，因此**不依赖采样**。
基准场景 `28-sparse-sampling-narrow-slit` 与单测
`test_sparse_sampling_would_miss_the_slit` 专门证明：0.05 mm 缝可落在 0.3/1.0 mm
采样网格之间，但本实现仍精确检出 0.05 mm。

**风险区间的上下文取样**：缺口/走廊 run 的“前/后是什么铜”取自最近的**可用铜区间中点**，
而不是 run 边界 ±ε（大孔洞内部 ±ε 仍是空洞，会把孔误标成“无铜/铜边”）。

**性能与精确性的折中（真实快照需要）**：真实铺铜 polygon 可有数百条边。实现只保留
“线段 bbox 向外扩 `half_width + tolerance`”范围内的边/区域参与断点与最近边界计算
（`geometry.coverage_intervals(limit=...)`）。这是**语义等价**裁剪：范围外的边到线段
任何点的距离都大于所需半宽，不可能影响 safe/corridor/void 分类，也不可能成为更近的
走廊边界。真实 2 层板回放因此从 134 s 降到 1.8 s，规则/状态/覆盖不变。
单区域（外环+孔）不可能有“内部接缝”，因此单区域时跳过接缝检测：真实四层板回放
从 68 s 降到 14 s，365 条 findings 逐条一致。

早期版本曾把“参数差”与“长度容差”混用，导致窄缝区间被整段跳过；该缺陷已在开发期修复，
并由上述基准/单测锁定（回归不得重犯）。

## 4. 铜的“并集边界”语义

参考铜由多块 polygon 组成时，**内部接缝不是铜边界**：

- 两块同网 polygon 共边相接 → 接缝两侧都是铜，不计入走廊距离；
- 同网 polygon 重叠 → 重叠边不计入；
- 孔洞边、外轮廓边、真正缺口两侧的边 → 计为铜边界。

实现：对每条候选边界边取中点、沿法向两侧各探 `ε`（`max(1e-9, min(tol·0.001, 1e-4))`），
若两侧都在并集铜内则跳过。这样避免“同网相接处误报走廊不足”，同时保留微缝/真缺口。

限制：若两块 polygon 的间隙小于 `2ε`，可能被当作相接——这类尺度已低于声明的
几何容差，输入应声明更小的 `geometry_tolerance` 或改用实际填充结果。

## 5. 缺口成因分类

| 成因 | 判据 | 默认规则/严重度 |
|---|---|---|
| `split_different_nets` | 投影覆盖到**其他网络**铜上（含跨缝） | `RP-E2-201` error |
| `void_in_copper` | 缺口两侧上下文同属一块 polygon（孔/凹口） | `RP-E2-202` error |
| `same_net_gap` | 缺口两侧是同网不同 polygon | `RP-E2-203` warning + connectivity unknown |
| `copper_edge` | 只有一侧有铜（平面/板边结束） | `RP-E2-204` error |
| `no_copper` | 两侧都没有参考铜 | `RP-E2-205` error |
| `narrow_corridor` | 铜存在但边缘距离 < h | `RP-E2-206` warning |

连续的多个非 safe 区间**合并为一个 run、一条 finding**，但保留
`measured.void_length / corridor_length / wrong_net_length` 分量；需要逐段定位时用
`interval`（t0/t1、起止坐标、长度）与 SVG 叠加图。这是刻意的降噪设计，不是漏报。

## 6. 证据不足时的语义

- 只有铺铜设计边界（`pour_boundary`）、理想无限平面（`ideal_plane`）或来源未知
  （`unknown`）时：可以给出“声明理想化下的潜在结论”（`determinism=potential`），
  但长度**不计入 checked**，整体 `incomplete`（`RP-E2-208`）。
- 同网 polygon 相接/微缝/重叠：几何不能证明填充级电连接 → `RP-E2-207` +
  `connectivity_unproven` unknown。
- 陈旧快照（`source_snapshot` 与项目快照不同）：证据拒绝复用，不计 checked。
- 层厚缺失导致无法判断“更近参考”：`RP-E1-112` unknown，不估算。

## 7. 数值与稳定性

- 全部使用 Python `float`；`bool/NaN/inf` 在输入校验阶段拒绝。
- 长度比较使用 `board.geometry_tolerance`；风险区间划分不使用长度容差做“跳过”
  （只跳过 `t` 差 ≤ 1e-12 的重复断点）。
- 变形稳定性由 `tests/return_path_audit/test_deformation.py` 覆盖：对象排序、平移、
  90° 旋转、mm↔mil、网络一致重命名、无关铜增加。
