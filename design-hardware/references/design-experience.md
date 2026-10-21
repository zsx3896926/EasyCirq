# 工程经验库：选择、应用与继续积累

这是Agent按任务读取的检查提示库，不是让用户填的问卷，也不是无条件规则集。先保留用户范围与既有正确设计；不因条目多而给小修改强加全流程。原理图和PCB以真实工程与适用资料验收，不能靠读完清单、总分或勾选数量放行。

## 选择本次需要的部分

| 当前对象 | 加载 | 本次应留下的证据 |
|---|---|---|
| 新建/修改原理图 | [原理图细节](schematic-details.md) | 适用的引脚/电源/接口核对、实际连接回读 |
| 图面混乱 | [排版与看图验收](schematic-layout.md) | 连接基线、实际整页与局部图 |
| PCB放件、改尺寸或换封装 | [布局细节](pcb-placement-details.md) | 机械约束、关键回路与敏感区位置 |
| 布线/铺铜/改层叠 | [布线与回流细节](pcb-routing-details.md) | 网络规则、参考层、实际铜连接与未布线 |
| 准备打板/贴片/手焊 | [制造与首板细节](manufacturing-details.md) | 同版制造包、装配变体与待测清单 |
| 某类具体硬件 | [领域易漏项](domain-design-details.md) | 对应型号手册、接口条件和专项复验 |

对适用条目执行“识别对象/条件 → 查具体型号与版本 → 落实设计/约束 → 回读/测量/检查”。只在工程记录中列重要的通过证据、缺陷和未覆盖项；不把内部编号流水账发给新手。已知事实违反约束才判缺陷；没有资料/工具时标待确认；可选优化不得伪装为阻断。具体数值服从器件手册、项目约束和实际板厂订单。

## 把经验落实到当前模块

需要解释失效原因或检查方法时，再读 [原理图机制卡](schematic-lessons.md) 与 [PCB机制卡](pcb-lessons.md)。两者吸收用户提供的0.6.0新增经验并与现有190条去重，属于展开说明，不是额外数量指标。每模块只留适用条件、实际设计决定、回读/测量证据及剩余缺口；检查前后使用同一工程版本。

## 已查看的样本与资料

核对日期：2026-10-20。下面区分实际图纸、作者修改记录、官方技术指导和仅入口资料；“看过”不代表复刻、测过或证明整个项目无缺陷。各细节文件是结合这些资料与通用工程知识的独立归纳，表中只归属明确支持的观察，不把所有条目都归给某一项目。

| 代号/原始资料 | 本轮实际查看范围 | 可以吸收的经验 / 不能照搬的部分 |
|---|---|---|
| P01 [SparkFun ESP32 Thing Plus](https://cdn.sparkfun.com/assets/6/d/c/6/c/ESP32_Thing_Plus_Schematic.pdf) | 单页图纸；原作者仓库在排版参考中 | 功能分区、局部拓扑和远端网名；不照搬旧器件与外围参数 |
| P02 [SparkFun ESP32-S3](https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf) | 两页实际图纸 | 主控/外围分页和约束注释；叠层专属线宽不得通用化 |
| P03 [Arduino UNO R3](https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf) | 单页实际图纸 | 电源、USB和主控区域组织；AVR与其他MCU不能直接互套 |
| P04 [ODrive v3 CHANGELOG](https://github.com/odriverobotics/ODriveHardware/blob/master/v3/CHANGELOG.md) | 作者3.2–3.5修改记录 | 采样寄生电阻引发比例误差、Kelvin净距用net-tie表达、DFU时控制脚状态、端接可配置；其分地方案只属于该设计 |
| P05 [Crazyflie Brushless Rev.G](https://www.bitcraze.io/documentation/hardware/crazyflie_2_1_brushless/cf2.1_bl_schematics_Rev.G.pdf) | 7页文本及主控/IMU页实际图像 | 重复电调用层次页实例组织、供电与传感器独立页、调试口与不装件标记；源图含非商业许可限制，不能当MIT附件分发 |
| P06 [RP2040硬件设计](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf) | 最小系统、电源/USB章节与去耦布局图 | 图中器件关系要落到实际PCB；板厚改变后需重新核对USB传输线；RP2040专属电路不泛化到RP2350/STM32 |
| P07 [泰山派手机扩展板](https://wiki.lckfb.com/zh-hans/tspi-rk3566/project-case/fat-little-cell-phone/mobile-phone-integrated-project.html) | 原理图/PCB流程与焊接、首次测试章节文本 | FPC线序与网络错位需独立核对；已知固件隔离硬件问题；参考载板与屏版本必须一致；未读取附件PCB，不声称已审完整布线 |
| P08 [EEZ BB3](https://github.com/eez-open/modular-psu) | 作者仓库结构与说明；未读取具体功率板图纸 | 背板、电源模块、MCU、结构文件分开管理；只作为模块化交付组织样本，不提炼其布线数值 |
| P09 [OLIMEX STM32-E407](https://www.olimex.com/Products/ARM/ST/STM32-E407/) | 作者产品、版本/原理图与源码入口 | 旧/新PHY固件应匹配板版；未成功读取PDF内容，不据此声称验证其电路 |
| G01 [Espressif schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/schematic-checklist.html) | 电源、启动、GPIO、存储章节 | 复位/strap与外围相互作用、输入专用脚及已占用脚；必须切到实际芯片系列 |
| G02 [Espressif PCB指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html) | 电源、晶体、RF、模组/天线章节 | 连续参考、模组位置与壳体影响；不要把ESP32的净空距离、层数或线宽当所有无线器件标准 |
| G03 [TI Power Tips：寻找开关回路](https://www.ti.com/document-viewer/lit/html/SSZTBF4/GUID-095BD04D-6DAF-42E7-9AA0-72CB14E1F58C) | 拓扑开/关状态与脉动回路说明 | 按拓扑找不连续电流回路；文章的单过孔电流经验不作为设计保证 |
| G04 [TI低侧电流采样布局](https://www.ti.com/document-viewer/lit/html/SSZT805/GUID-5F278960-BA94-4362-9099-87ABC753A4D6) | Kelvin与地压降误差分析 | 采样点和参考点要一起落实；不能只在网络名写SENSE |
| G05 [ADI MT-031](https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf) | 接地与数据转换器回流说明 | 按电流路径理解AGND/DGND，不机械套用割地 |
| G06 [TI SLLA414](https://www.ti.com/lit/an/slla414/slla414.pdf) | 高速差分、过孔、回流和ESD章节 | 按通道检查阻抗不连续和支路；接口速率/平台约束分别处理 |
| G07 [ST AN4488](https://www.st.com/resource/en/application_note/an4488-getting-started-with-stm32f4xxxx-mcu-hardware-development-stmicroelectronics.pdf) | STM32F4硬件指南章节 | 特殊供电脚、复位、启动和调试的查证入口；VCAP/电容和封装依实际型号 |
| G08 [Bosch BME280 HSMI](https://www.bosch-sensortec.com/media/boschsensortec/downloads/handling_soldering_mounting_instructions/bst-bme280-hs006.pdf) | 热源、气路、机械应力、涂覆与清洗章节 | 传感器的环境接触/机械条件属于设计本体；不把大铜散热和涂覆保护强套给环境传感器 |
| G09 [TI TUSB320LI](https://www.ti.com/product/TUSB320LI) | 官方CC控制器说明 | Type-C需要角色/方向与供电策略；具体电阻/状态仍读手册和协议 |
| G10 [ADI AN88](https://www.analog.com/media/en/technical-documentation/application-notes/an88f.pdf) | 本次读取4页热插拔LC振铃与阻尼分析 | 陶瓷输入电容与线缆可产生过冲；文中器件/阻尼值仅适用其示例，不直接迁移 |
| T01 [KiCad 9 PCB手册](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) | 铺铜、布线、规则与输出章节 | 铜区轮廓不代表已重填充；工具描述仅说明KiCad行为，不能冒充EasyEDA命令 |
| M01 [嘉立创阻焊说明](https://www.jlc.com/portal/q6i34402.html) | Mask/Paste与阻焊桥说明 | 阻焊与钢网不同，阻焊桥受实际工艺限制；下单再查当前能力 |
| M02 [嘉立创工艺总览](https://www.jlc.com/portal/vtechnology.html) | 本次已读取FR4/孔/阻焊/成型和SMT对比正文，替代先前读取失败的状态 | 条件快照与冲突见 [生产规则](jlc-production.md)；实际订单组合、费用与厂方审核仍需独立核对 |

## 每次任务继续积累的方法

1. 选与当前目标最接近的原作者项目，优先立创开源/开发板资料；再用其他开源方案与具体器件原厂资料交叉核对。反例和已修复缺陷优于只看成品照；不为凑数量下载无关仓库。
2. 读实际原理图/PCB、板版、BOM、作者问题记录与修订；链接/封面仅记为入口。能定位提交或发布版时记录不可变版本，主分支只记查询日期，不能杜撰SHA。
3. 写精简经验记录：问题与后果、适用拓扑/器件/工艺、原始出处与位置、观察还是作者结论、建议动作、复验办法、例外和验证状态。没有原始证据的传闻保留待证，不提升成规则。
4. 新经验先进入当前工程记录，合并同义条目；只有用户授权更新Skill/仓库时才持久化到共享经验库。未脱敏客户工程、账号、采购信息不能自动成为公开案例。
5. 升级已有经验时保留适用边界；资料冲突查型号、工作条件与版本，必要时记录并存的条件结论。失效经验移出默认执行路径，不无限附加互相矛盾的口诀。
6. 学习表达与原理不等于获得源文件许可；不打包第三方图纸/源码。复用实际硬件、库、固件或图片时分别核对版权/商用/署名/衍生条件。

经验库可持续扩展，但不能声称遍历了所有开源作品，也不能把“来源已查看”升级为“当前用户设计已实测”。目前未对这些项目做整板复刻或本Skill驱动的真实EDA验收。

本轮扩充的 60 张设计卡、12 组范例、22 个故障案例、选型/计算/制造/项目内容所引用的资料，统一登记在 [原始来源登记](source-register.md)。本文件早期样本的 P/G/T/M 编号保留，不与新来源 ID 混用；新内容的查阅范围、版本和“不能推广的部分”以登记表为准。
