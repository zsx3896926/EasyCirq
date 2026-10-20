# 任务场景与反例验收

> 这些场景用于检查 Agent 是否沿真实用户路径推进，不是让新手阅读的规则。
> `assets/scenarios.json` 是机器可检查的同一份数据；测试会核对数量、路由文件、反例覆盖和可确定性计算。

| ID | 用户 | 任务 | 场景 | 必须做到 | 禁止宣称 | 反例 |
|---|---|---|---|---|---|---|
| S01 | beginner | from_zero | 花盆缺水手机提醒 | 先复述目标并只问1-2个影响路线的生活化问题；区分硬件、固件、手机端和实物验收；先建立土壤传感与供电方案，再谈外壳 | 把图纸完成说成设备能用；把拔出探头测试说成真实土壤校准 | — |
| S02 | beginner | from_zero | USB 小灯/指示器 | 先确认USB-C sink角色和C-to-C供电；按LED Vf/电流选限流或恒流方案；解释是否真的需要MCU | 把Type-C外形当成PD能力；直接套5.1k到所有Type-C角色 | — |
| S03 | beginner | from_zero | 手机看温湿度 | 确认室内/室外、电池/插电、查看距离；核对模组峰值电流与传感器气路；把壳体影响纳入验收 | 用模组典型电流代替峰值；把开发板跑通说成定制板已验证 | — |
| S04 | beginner | from_zero | 电池供电无线按钮 | 把“一年”转成可测的每日事件/睡眠预算；核对唤醒、发射、确认、重试状态；说明电池化学体系与截止电压 | 用典型待机电流直接乘算一年；把模型寿命说成已验证 | — |
| S05 | beginner | from_zero | 12V 小水泵定时开关 | 取得水泵铭牌/启动/堵转电流；按感性负载处理续流与浪涌；设计复位/掉电默认关闭 | 把水泵当电阻负载；只按平均电流选开关 | — |
| S06 | beginner | from_zero | 两节 AA 经 LDO 维持 3.3V（反例） | 用2.0-3.2V输入范围跑LDO压差计算；明确指出LDO无法维持3.3V；提出升压/升降压或改变电池组合 | 说LDO“加个大电容就行”；说电池标称3V所以能输出3.3V | two_aa_ldo |
| S07 | beginner | from_zero | 只有一句想法，没有工程 | 用一句话复述目标；只问1-2个真正影响路线的问题；给出推荐起点和理由 | 把选型作业推给用户；要求用户填写完整需求表 | — |
| S08 | beginner | troubleshoot | 收到焊好的板但不会烧录 | 先核对板版、装配变体、供电和下载口；区分未烧录、BOOT状态、驱动/工具和硬件故障；一次只让用户做一个可观察动作 | 从一次失败直接判板子坏；让用户随便短接/乱按BOOT | — |
| S09 | engineer | design_change | 改现有工程的 4-20mA 输入 | 先读实际工程、接口和板框；确认两线/三线/四线、回路供电和共模；核对采样电阻、compliance、保护和ADC | 把4-20mA当普通电压输入；擅自改接口/板框 | — |
| S10 | engineer | tidy | 整理混乱原理图但保持连接 | 先建立pin-net基线；按功能做模块几何再组合页面；局部短线与跨区标签分别处理 | 交换脚号或合并相似网名；把所有局部连接都改成标签 | — |
| S11 | engineer | design_change | 优化现有 PCB 布局，保留机械约束 | 先锁定机械约束和锁定器件；按开关状态找关键电流回路；检查参考层/回流和载流瓶颈 | 无目的整体重排；移动锁定器件 | — |
| S12 | engineer | part_change | 同封装但不同脚位的替代（反例） | 核对完整MPN、引脚定义、焊盘映射和电气条件；把替代判为需要改原理图/封装/PCB的类别；更新源工程、BOM、固件和装配变体 | 只换BOM里的C号/型号；凭封装相同判pin-to-pin | same_package_different_pinout |
| S13 | engineer | review | 同一网名出现在错误物理脚（反例） | 按完整物理引脚ID核对pin-net；区分逻辑脚名、物理脚号和焊盘号；发现缺脚/多脚/错脚后修源数据 | 因为网名相同就判为同一网络；把相似网名自动合并 | same_net_wrong_physical_pin |
| S14 | engineer | review | 模块上拉并联后超出灌电流（反例） | 把所有并联上拉折算成等效电阻；用最弱器件的IOL/VOL保证值算灌电流；核对总线电容和上升时间 | 重复套4.7k；只看单个模块的上拉 | parallel_pullup_over_sink |
| S15 | engineer | review | 复位/下载状态导致负载误动作（反例） | 列出高阻、复位、bootloader、崩溃四种状态；检查控制脚外部默认态；加硬件下拉/关断路径 | 只靠固件初始化保持关闭；把复位抖动当正常 | reset_download_load_actuation |
| S16 | engineer | review | 差分等长却跨参考平面分割（反例） | 逐段追踪参考平面；检查换层回流过孔；确认差分对共模回流 | 把等长当信号完整性通过；只看差分间距 | diff_pair_cross_split |
| S17 | engineer | from_zero | 低功耗无线温湿度节点 | 先写需求和验收标准；建立电池输入侧状态预算；核对模组峰值/睡眠/传感器稳定时间 | 把6个月估算说成已验证；忽略弱网重试和低温 | — |
| S18 | engineer | from_zero | 工业 RS485/4-20mA 采集节点 | 确认24V范围、隔离/非隔离、节点数和线缆；核对RS485端接/偏置/共模/保护；核对4-20mA compliance和采样 | 把RS485当TTL；每个节点都装终端 | — |
| S19 | engineer | from_zero | 低压有刷电机驱动板 | 核对启动/堵转/回生；算MOSFET导通/开关/SOA；设计死区、栅驱、自举和默认态 | 只按额定3A选器件；忽略堵转和回生 | — |
| S20 | engineer | from_zero | USB-C 5V 供电小板 | 确认sink/source角色和C-to-C场景；核对CC/Rd和VBUS路径；加ESD/限流/保护 | 把所有Type-C都加5.1k；把USB-C外形当PD | — |
| S21 | engineer | design_change | 把 LDO 换成 Buck | 比较输入/输出范围、效率、纹波和面积；算电感/电容/峰值电流；核对反馈、补偿和轻载 | 把LDO脚对脚换Buck；只看效率不看纹波/EMI | — |
| S22 | engineer | design_change | 增加一路 CAN | 确认CAN版本、速率、节点/线缆；核对收发器电源、端接、共模和隔离；检查MCU引脚复用和默认态 | 每个节点都加120Ω；把CANH/CANL当UART | — |
| S23 | engineer | design_change | 增加电池充电与电源路径 | 区分充电、保护、电量计和power path；核对充电电流/热/终止；检查USB与电池同时供电/反灌 | 把保护板当充电器；充电时带载不核对终止 | — |
| S24 | engineer | design_change | 改板：FPC 方向/Pin-1（反例） | 核对完整料号、FPC接触面、Pin-1和脚序；区分上接/下接、同面/异面；核对连接器视角和装配方向 | 同针数判兼容；只看3D外形 | fpc_pin1_reversed |
| S25 | engineer | part_change | 替代料需要改阻容/固件 | 把替代判为需要改阻容/配置/固件的类别；重算反馈分压和补偿；核对启动/时序/引脚 | 只换C号；按典型反馈电压算 | — |
| S26 | engineer | part_change | 商城有货但不满足 SMT 供料（反例） | 区分商城库存与SMT可贴/备料状态；核对包装、编带、MOQ、 feeder和订单选项；确认是否需要客供料/换料 | 把商城有货等同SMT可贴；把个人散料当工厂库存 | lcsc_stock_not_smt |
| S27 | engineer | part_change | 替代料资料不足 | 把替代判为资料不足/暂不能判定；列出缺失的手册/引脚/额定/PCN；要求样品/完整资料/测试 | 凭一页简介批准替代；把“可替代”推荐当原厂保证 | — |
| S28 | engineer | tidy | 原理图有电容但 PCB 回路不合理（反例） | 按电源脚-电容-参考的完整回路检查；看电容端子到开关/负载的实际路径；核对过孔/参考层/回路面积 | 数电容数量当去耦完成；只看电容离芯片中心的距离 | schematic_cap_bad_pcb_loop |
| S29 | engineer | tidy | 几何脚本返回0但缺文字边界（反例） | 检查输入是否有完整文字边界/对象计数；缺expected_counts或文字bbox时判incomplete；仍要做实际导图整页/局部复核 | 把退出0当排版通过；用锚点冒充文字边界 | geometry_zero_missing_text_bounds |
| S30 | engineer | tidy | DRC 通过但器件/功率条件不满足（反例） | 区分DRC几何规则与电气/热/功率条件；复算电压/电流/SOA/热；核对器件实际Vgs/温度/封装 | 把DRC通过当电气通过；只降额不计算 | drc_pass_power_condition_unmet |
| S31 | engineer | troubleshoot | 上电反复复位 | 先测输入/电源轨/电流和复位脚；核对brownout、负载瞬态和启动顺序；区分复位、 bootloop、看门狗和供电跌落 | 先怪固件；盲目加大限流 | — |
| S32 | engineer | troubleshoot | 电流采样偏差/ADC异常 | 核对shunt/Kelvin/增益/偏置；检查ADC建立时间和采样时刻；区分功率回路噪声与基准/地压降 | 直接改阈值让读数好看；把跳变都归因于软件滤波 | — |
| S33 | engineer | troubleshoot | 焊接完成但未烧录/未功能测试（反例） | 区分工厂电测/AOI、烧录、功能测试和用户验收；核对板版/固件/装配变体；制定首板测试和停止条件 | 把贴片完成当交付完成；把AOI当功能测试 | soldered_not_flashed_tested |
| S34 | engineer | troubleshoot | 仅估算却宣称半年续航已验证（反例） | 区分模型估算与实测；检查输入电流是否在电池侧；列出未测的睡眠/发射/低温/老化 | 把脚本输出当实测；把典型电流乘算当保证 | estimate_claimed_verified |
| S35 | engineer | troubleshoot | BOM/坐标/DNP 版本不一致 | 冻结同一工程版本再导出BOM/坐标/Gerber；核对位号/面/旋转/原点/单位/DNP；区分装配变体与替代料 | 直接删BOM行掩盖差异；拿旧坐标配新BOM | bom_cpl_version_mismatch |

共 35 个场景；必需反例 12 个。
