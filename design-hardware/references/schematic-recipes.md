# 原理图画法配方：从引脚关系生成局部候选

本页教 Agent 怎样把已经确认的电路拓扑画成可跟读的局部结构。配方保存的是**角色、实际引脚间的相对关系、支路意图与检查方法**，不是某个库符号的一组固定坐标。

配方表：[schematic-recipes.json](../assets/schematic-recipes.json)；离线实例化器：[sch_recipe.py](../scripts/sch_recipe.py)。五种配方均标记为 `experimental_unverified_in_eda`：当前测试使用合成测量，尚未完成两个真实符号变体的 EDA 写入、导图与回读验证。可用于规划和候选比较，不能据此宣布真实图面已经通过。

## 先做一个模块，再组成页面

1. 从 [排版引擎](schematic-layout-engine.md) 的现场快照、连接 IR、文字几何、页面几何构造 `layout-source.json`；先解决 model-report 的 blockers。
2. 选择与真实拓扑相同的配方。根据已核对的器件身份、符号单元与物理脚号建立角色绑定；不按封装常识猜脚号，不把所有“反馈”都归入同一配方。
3. 查看实测姿态：例如分压两只电阻竖直、输入电阻横向、NPN 的 B 向左而 C 向上。若姿态不合适，在执行器支持的离线规划中选择姿态，或者在授权工程副本中旋转后重新测量。实例化器只平移，保留现有 rotation/mirror，不旋转旧测量点来冒充回读。
4. 用脚本计算候选。它沿连接轴按本体、引脚和已有文字边界留白，在垂直于连接轴的方向对齐被绑定的真实引脚。图面单位采用现有模型的 raw、y-up、5-raw 网格；gap 是可调规划参数，不是行业制造规则。
5. 看 SVG 的角色关系和引脚位置，按下表组织真实短线。SVG 中灰虚线仅为连接意图，允许斜线；它不是路由结果，也不是可以写入的导线。
6. 选择候选后回到现有排版引擎进行路径规划、合页、独立几何检查。实例化器输出不是 `compose` 或 `apply` 输入，也不是现有求解器已经支持的强制位置约束。尚无自动配方→官方布局/写入适配器时，由 Agent 在受支持的规划接口表达这些相对安排，或使用当前执行器的受控移动并重布受影响线；每次均从最新真实状态复核。
7. 实际写入后完成网表成员/NC/作用域比对、保存重开、官方导图整页与局部检视。局部碰撞先改姿态、间距或反馈通道，重新生成候选，不靠改网络或到处加标签解决。

## 五种可执行画法

| 配方 ID / 适用拓扑 | 先绑定的角色与引脚 | 相对摆法与连线次序 | 读图时应看到什么 |
|---|---|---|---|
| `divider` / 两电阻分压 | upper.supply/tap、lower.tap/ground | upper 为核心；lower 的 tap 对齐 upper.tap 的 x，放在其完整边界下方；先连 tap，再向上电源、向下地，在中点向负载引出 | 一个可直接跟读的上下串联链和中点支路；不是三个散开的网标签 |
| `npn-led-driver` / NPN 低边 LED | switch.base/collector/emitter、base_resistor.input/base、led.anode/cathode、limit_resistor.supply/led | B 电阻位于 B 脚左方且连接脚同 y；LED 阴极在 C 脚上方且同 x；限流电阻继续放在 LED 阳极上方；先画 B 短线，再画集电极串联链，E 就近回地 | 控制从左入，供电支路自上而下到 C/E；实际 B/C/E、LED 极性可辨 |
| `opamp-inverting-feedback` / 反相运放 | amplifier.minus/plus/out、input_resistor.input/sum、feedback_resistor.sum/out | 输入电阻在负输入左侧；反馈电阻在运放上方且 sum 脚与负输入同 x；先连求和节点，再从输出沿上方预留通道回反馈电阻；正输入参考独立表达 | 负反馈环路绕运放上方回到求和点，输入与反馈相交处明确；不会误画成正反馈 |
| `555-astable` / 标准无稳态 555 | timer.discharge/threshold/trigger/control/vcc/ground、ra.supply/discharge、rb.discharge/timing、timing_cap.timing/ground、control_cap.control/ground | RB 放 discharge 左方；RA 在 RB 上方；定时电容在 RB 下方；控制电容在 control 下方；先连 RA/RB/放电节点，再连 RB/电容/threshold/trigger 定时节点；控制电容与定时电容分别就近回地 | 两个不同节点：上面的放电结点和下面的定时结点；threshold/trigger 的同网支路清楚 |
| `regulator-decoupling` / 线性稳压器 | regulator.input/output/ground、input_cap.supply/ground、output_cap.supply/ground | 输入电容在输入脚左侧，输出电容在输出脚右侧，两电容供电脚分别与对应 IC 脚同 y；先画输入/输出水平短线，再向下画电容/地支路 | 左入右出、两个局部去耦支路；电容归属于输入还是输出一眼可辨 |

配方只覆盖表内局部拓扑。555 的 RESET、OUT 和电源去耦，运放电源单元与未用单元，稳压器 EN/ADJ 等仍在原工程中保留并单独安排；脚本不会删除未选成员。NPN 配方不替代 PNP/MOSFET 设计，反相反馈不替代比较器迟滞，标准 555 配方不覆盖单稳态或二极管占空比变体。需要变体时先写清真实拓扑，再按同样方法新增配方。

## 调用与字段契约

输入复用 `sch_layout_model.py` 输出的 `schemaVersion: 1`、`components[].id`、`measurement`（含实测 bbox/pins/textBboxes）。绑定文件是单纯的角色映射；例如某工程已经核对 R1/R2 的 1、2 脚后：

```json
{
  "upper": {"componentId": "cmp-R1", "pins": {"supply": "1", "tap": "2"}},
  "lower": {"componentId": "cmp-R2", "pins": {"tap": "1", "ground": "2"}}
}
```

以上脚号只是绑定格式示例，不是电阻/符号库的默认脚号约定。其他配方的完整角色名和语义脚名直接读取资产的 `roles`；Agent 负责填真实映射，不让新手手工准备 JSON。

```bash
python design-hardware/scripts/sch_recipe.py --source out/model/layout-source.json --bindings out/divider-bindings.json --recipe divider --gap 20 --out-dir out/divider-candidate
```

输出：

- `recipe-candidate.json`：每角色稳定组件 ID、平移量、平移后的 measurement、实际网络连接意图、警告和源文件 SHA-256。measurement 保持现有模型字段形状；外围输出采用独立 `schematic-recipe-candidate/v1`，不混入官方布局输入。
- `recipe-preview.svg`：可打开的离线方框/脚点预览，不复刻真实库符号、不代表文字排版已经验证。
- 退出 0：已生成候选；退出 1：候选含缺文字边界或包围盒相交警告，需要调整/复核；退出 2：输入或已声明连接不符，未生成本次候选。应检查退出码和哈希，不使用输出目录遗留的旧候选。

相对摆放例：下方器件先令 `dx = targetPin.x - ownPin.x`，再令 `dy = floor((targetEnvelope.minY - gap - ownEnvelope.maxY)/5)*5`。这随两个符号真实尺寸与文本范围变化，不使用固定符号宽高。左、右、上同理；所有器件点、本体与已有文字边界使用相同平移量。若两个独立支路相互挤占，脚本报告 `envelope_overlap`，Agent 为该拓扑选另一侧、增加通道或调整实测姿态后再算。

## 证据与边界

脚本校验角色覆盖、组件不重复、物理脚存在且绑定不重复、有限数值、5-raw 脚点、配方连接的非空同网关系；生成后检查已选成员完整包围盒相交。它不核算电气参数、不证明网络作用域、不证明所有非声明连接正确，也不做线路避障、图签避让、整页检查或符号朝向适用性判断。实测引脚 rotation 保留，真正扇出方向与通道由后续路径规划复核。

`tests/test_sch_recipe.py` 覆盖五配方各两种合成几何尺寸、引脚对齐与净间距、原数据不变、姿态与 pin-net 不变、错网/错脚/离网格拒绝、缺文字降级以及实际 CLI 输出与 SVG 解析。这些是**离线程序验证**，不是两个真实符号配置验证。真实库适配、官方路由、写入、保存重开和导图视觉验收均保持 `NOT RUN`，直到在具体工程完成并记录证据。

新增配方先从一个已确认拓扑提取角色和连接，再设计核心向外的有序相对摆放，加入两种不同实测几何的回归与真实执行样例；把失败姿态及替代摆法写进 checks，不把“禁止用错误姿态”当作完成了画图方法。

