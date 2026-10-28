# C 运动、位置、转速与角度 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq` 的硬件设计知识库（工作树 HEAD `0fe5cf8`）。
> 方法：只读检索 SKILL 按需表、设计卡索引、选型/组合/领域/放置/故障/深潜/案例库，按关键词定位后只读相关段落；未修改任何仓库文件。
> 判定口径：`adequate` 可直接引用；`partial` 有基础但缺本主题具体内容；`missing` 没有本主题内容。
> 总体结论：现有 60 张设计卡中没有运动/位置/转速类卡片；7 个主题都需新增组文件内容，其中 C2、C4、C6、C7 可复用少量现有基础，C1、C3、C5 基本从零写。

## C1 加速度计

### 现有内容

- `design-hardware/references/pcb-placement-details.md:37`（PL25）：MEMS/晶体等机械敏感件避开弯板、分板、按键和紧固应力区。只有一句，没有加速度计轴向、安装基准或旋转中心。
- `design-hardware/references/domain-design-details.md:45`（DM24）：温湿度/气压/气体/光学/惯性传感器按物理测量条件布置。只有一句，且与气路/窗口等环境传感器条件混在一起。
- `design-hardware/references/design-cards/analog/a04-adc-driver.md:39-323`：SAR ADC 驱动（源阻抗、采样窗、RC、建立），可用于模拟输出加速度计，但不是加速度计专用。
- `design-hardware/references/design-cards/analog/a02-opamp-buffer.md:39-342`、`a05-vref.md:39-342`、`a01-divider.md:39-270`：缓冲/基准/分压，仅在模拟输出路线复用。
- `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:24-641`：传感器到 ADC 的误差分类、合成与校准边界，可用于模拟输出加速度计的误差预算。
- `design-hardware/references/selection/modules-connectors.md:153-168`：通用传感器选型（精度是区间、位置是设计的一部分、校准要写进交付），没有加速度计参数。
- `design-hardware/references/manufacturing-details.md:27`（MF16）、`jlc-smt-rules.md:35`：MSL、回流次数、MEMS/传感器禁清洗，可复用于 LGA 封装。

### 判定

`missing`

### 已覆盖

只有“MEMS 要避开板弯/螺钉应力”的放置提示（PL25）、惯性传感器物理条件一句（DM24），以及模拟输出路线可复用的 ADC/误差链；没有加速度计的量程、噪声、ODR、校准、倾角算法和验证内容。

### 缺口

1. 用户话术：没有把“测倾斜/跌倒/振动/冲击/机器是否在动/水平”映射到加速度计，也没区分静态倾角、动态振动、冲击记录和简单倾倒开关。
2. 路线选择：没有数字 MEMS（I²C/SPI）、模拟输出 MEMS + ADC、高 g/电荷式振动传感器、机械倾倒/滚珠开关、成品模块 vs 裸片的路线与淘汰条件。
3. 必查参数：没有量程（±2/4/8/16 g）、噪声密度、ODR、带宽、零偏及温漂、横轴灵敏度、自检、封装/MSL 的核对表；未区分分辨率与精度、保证值与典型值。
4. 电路组成：没有 VDD/VDDIO 去耦、CS/地址 strap、INT1/INT2 上拉与极性、模拟输出的 RC/ADC 驱动拓扑。
5. 参数确定：没有由噪声密度推倾角分辨率（`Δθ≈a_noise/g`）、ODR 与振动带宽/抗混叠、冲击测量带宽、FIFO 水位与采样窗的算例。
6. 原理图：没有具体型号逐脚表（电源/地/SCL/SDA/SDO/CS/INT）与默认态；没有 CS 悬空、地址 strap 错误的检查项。
7. PCB：没有敏感轴与安装基准、旋转/振动中心、板弯与螺钉应力隔离、远离热源/连接器/分板边的放置规则；PL25 仅一句。
8. 程序：没有上电 ID 校验、量程/ODR/FIFO/中断配置、六面校准、倾角计算、阈值/唤醒、复位后重初始化的流程。
9. 验证：没有静态 1 g 六面翻转、已知角度/转台、振动台/冲击锤、静止噪声标准差、温度漂移、跌落与轴向符号检查。
10. 常见误判：没有“分辨率=精度”“量程=抗冲击”“模块跑通=自研板通过”“忽略安装应力造成的零偏”“ODR 低于信号带宽导致混叠”等反例。
11. 采购落地：没有立创商城检索字段（轴向/量程/接口/封装/MSL）、模块与裸片区分、编带/托盘与 SMT 可贴性核对；也没有禁止编造 C 号的提醒。

### 动作

`new`

### 候选型号

- **首选：LIS2DH12TR（ST）**。LGA-12、I²C/SPI、低功耗、资料完整、常见；适合做通用倾角/运动检测。
- LIS3DH（ST）：同族、FIFO 更大，适合需要缓冲采样的场合。
- ADXL345（ADI）：经典三轴数字加速度计，资料完整，适合作为第二来源。
- BMA400（Bosch）：超低功耗，适合电池设备；需核对 ODR/唤醒与 FIFO 条件。
- 模拟输出路线可另核 ADXL335（ADI）；高 g 振动路线另核 ADXL1002 类器件，不混入通用倾角设计。

### 备注

DM24 把惯性传感器与环境传感器并列，容易让人以为 IMU/加速度计需要气路或窗口；PL25 只写 MEMS 机械应力，没有轴向和安装基准。ANA-04 是 SAR ADC 驱动卡，模拟输出加速度计的源阻抗、输出 RC 和内部缓冲需按具体型号重算，不能直接套卡片的算例。现有 `assets/scenarios.json` 的 35 个场景中没有“倾斜/振动/跌倒”类用户话术，写新组时需自建话术表。

## C2 陀螺仪与 IMU

### 现有内容

- `design-hardware/references/engineering-deepdives/topics/d1-interface-combination-constraints.md:122-147`：未上电从机的 ESD 二极管是直流路径；`:219-235` I²C 逐网络检查；`:461-486` Crazyflie 未上电 IMU 的 ESD 注入算例（含 2.2 kΩ 上拉、14.31 µF、9.59 ms 量级）。
- `design-hardware/references/failures/f28-i2c-unpowered-device-lockup.md:21-254`：I²C 设备掉电后拖死总线的现象、假设、修复与复验。
- `design-hardware/references/module-integration.md:111-155`：先判输出结构再判电平、上拉/下拉所有权；`:263-274` 反灌路径；`:478-486` 两个 I²C 从机地址相同的案例。
- `design-hardware/references/pcb-placement-details.md:37`（PL25）：MEMS 机械应力放置。
- `design-hardware/references/domain-design-details.md:45`（DM24）：惯性传感器物理测量条件一句。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md:55,135,153-158`：BMI088/MPU9250、LSM6DS3/LIS3MDL 的位号、I²C 地址 strap 和换型记录；`motor-power-industrial.md:174`：双 IMU 共用 `!GYRO_CS` 等信号，只能互斥装配。
- `design-hardware/references/design-experience.md:32`：Crazyflie Brushless IMU 页的阅读证据（P05）。
- `design-hardware/references/manufacturing-details.md:27`、`jlc-smt-rules.md:35`：MSL/回流/清洗限制。

### 判定

`partial`

### 已覆盖

有 IMU 作为 I²C 从机的上拉所有权、未上电反灌/ESD 注入（D1 §6.3、F28）、MEMS 机械应力放置（PL25），以及 Crazyflie/Feather 的 IMU 器件阅读证据；没有陀螺/IMU 的选型、量程、零偏、融合与验证内容。

### 缺口

1. 用户话术：没有把“姿态/航向/转向/平衡/云台/抖动/翻车”映射到陀螺、6 轴 IMU、9 轴 IMU 或编码器。
2. 路线选择：没有 6 轴 vs 9 轴 vs 分离加速度计+陀螺、裸片 vs 模组、MPU-6050 等旧器件的淘汰条件、原始数据 vs 内置融合的选择。
3. 必查参数：没有陀螺量程（±125–2000 dps）、灵敏度、零速率偏移及温漂、噪声密度、bias instability、ODR/带宽、加速度计量程、自检、时钟输入、封装/MSL。
4. 电路组成：没有 VDD/VDDIO 去耦、SPI/I²C 模式 strap、CS 默认态、INT/DRDY 上拉、CLKIN、地址 strap、掉电/反灌路径。
5. 参数确定：没有角度随机游走/积分漂移、互补或 Kalman 滤波的频段划分、静止零偏校准、温度补偿、采样率与振动带宽的算例。
6. 原理图：没有具体 IMU 的逐脚表；没有 CS 悬空、双 IMU 共用片选/总线的互斥装配检查（现有 casebook 只是观察）。
7. PCB：没有旋转中心/刚性安装、轴向丝印、振动隔离与刚性固定的取舍、热梯度隔离、SPI 走线长度、9 轴远离磁源/大电流回路的规定。
8. 程序：没有 WHO_AM_I、复位、ODR/FS/FIFO/DRDY、静止零偏、融合、温度读取、异常重初始化、I²C 时钟拉伸/高速 ODR 的流程。
9. 验证：没有静止零偏标准差、转台/速率源、温度扫、振动、长时间漂移、轴向符号与顺序检查。
10. 常见误判：没有“6 轴能给出绝对航向”“模块能用=自研板能用”“量程=分辨率”“忽略零偏温漂”“采样太慢”“把 DMP 当保证”等反例。
11. 采购落地：没有检索字段（轴数/量程/接口/封装/MSL）、模组 vs 裸片、旧型号/克隆料识别与替代分级。

### 动作

`supplement`

### 候选型号

- **首选：LSM6DS3TR-C（ST）**。LGA-14、I²C/SPI、资料完整、常见、成本低；适合通用 6 轴。
- ICM-42688-P（TDK InvenSense）：低噪声、高 ODR，适合机器人/云台；需核对具体封装与时钟选项。
- BMI270（Bosch）：低功耗 6 轴，适合可穿戴/电池设备。
- BMI088（Bosch）：加速度计与陀螺分离，抗振更好，适合无人机/运动平台。
- 不把 MPU-6050 列为新设计首选：模块生态大但克隆/停产风险高，只作为“旧设计维护”说明。

### 备注

D1 §6.3 的 ESD 注入算例只证明路径存在，未核对 LP2985 的反向电流与具体 IMU 手册，不能外推到所有 IMU。casebook 的 Crazyflie“双 IMU”是互斥装配，不是冗余，可作为“共用片选/总线”的反例。现有资料没有 MPU-6050 克隆/停产提醒，新写时应补，但不要把它写成现有卡片的错误。

## C3 磁力计

### 现有内容

- `design-hardware/references/selection/modules-connectors.md:162`：“磁/光/proximity：感应距离、目标材料、污染、环境光；只看检测距离 → 现场条件留裕量”。这是接近检测判据，不是航向/磁力计判据。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md:135`：Feather Sense 的 LIS3MDL 挂在 I²C 上的位号与地址记录，没有磁校准内容。
- `design-hardware/references/pcb-placement-details.md:37`（PL25）：若选 MEMS 磁力计，可复用机械应力放置一句。
- `design-hardware/references/design-experience.md:44`（G08）：BME280 的安装/清洗指南，只适用于环境传感器，不能外推到磁力计。

### 判定

`missing`

### 已覆盖

只有一条通用“磁/光/proximity”选型判据和某开源板把 LIS3MDL 挂在 I²C 上的位号记录；没有磁力计的量程、航向校准、硬/软铁与磁干扰内容。

### 缺口

1. 用户话术：没有把“指南针/航向/方向/指北/车位/门磁”分流到磁力计、霍尔开关或接近开关；没有说明磁力计不能做金属探测。
2. 路线选择：没有 AMR/GMR/TMR/Hall/磁通门、3 轴磁力计 vs 9 轴 IMU、裸片 vs 模组、是否配合加速度计做倾斜补偿的路线。
3. 必查参数：没有量程（±2–16 Gauss）、分辨率（nT/LSB）、噪声、ODR、航向精度、线性度、横轴误差、置位/复位、温漂、封装。
4. 电路组成：没有供电/去耦、I²C 地址、DRDY、SET/RESET 脉冲电路、电平转换。
5. 参数确定：没有地磁 25–65 µT、1° 航向约需 0.57 µT（中纬度量级）、硬铁/软铁、倾斜补偿、360° 校准、干扰源距离衰减的算例。
6. 原理图：没有具体型号逐脚表；没有 SET/RESET 脚的处理与默认态。
7. PCB：没有远离电流回路/电感/扬声器/磁铁/电池/铁磁外壳与螺钉、传感器朝向基准、装配后复校准的规则。
8. 程序：没有原始三轴读取、硬铁/软铁系数、椭球拟合、倾斜补偿、磁偏角、低通、单次/连续模式。
9. 验证：没有 360° 旋转、参考罗盘对比、电机/电流开启干扰、装配前后重复性、温度漂移验证。
10. 常见误判：没有“原始航向直接可用”“HMC5883L 与 QMC5883L 寄存器兼容”“忽略电机电流/扬声器磁铁”“室内也能保证航向精度”“量程=分辨率”等反例。
11. 采购落地：没有检索字段（轴数/量程/接口/封装）、停产料识别（HMC5883L）、模块 vs 裸片、替代分级。

### 动作

`new`

### 候选型号

- **首选：LIS3MDL（ST）**。LGA-12、I²C/SPI、资料完整、常见；适合通用电子罗盘。
- MMC5983MA（MEMSIC）：20 位、低噪声、带 SET/RESET，适合高分辨率航向；需核对封装与校准。
- BMM150（Bosch）：低功耗三轴磁力计，适合可穿戴/电池设备。
- QMC5883L（QST）：低成本、模块多，但资料完整性与批次一致性需谨慎；HMC5883L 已属旧料，不应作为新设计首选。

### 备注

`selection/modules-connectors.md:162` 的“磁/光/proximity”行是本组最容易误用的现有条目：它把磁力计和接近开关混在“检测距离”一个判据下，不能拿来做航向设计。G08 只适用于 BME280 类环境传感器，不能外推到磁力计安装。现有库没有地磁/校准类来源，需新增。

## C4 霍尔开关与线性霍尔

### 现有内容

- `design-hardware/references/selection/modules-connectors.md:160,162`：“电流 | 分流/霍尔……”与“磁/光/proximity……”。霍尔在两个不同器件类别里出现，但没有霍尔位置/开关的具体参数。
- `design-hardware/references/design-cards/analog/a04-adc-driver.md:39-323`、`a02-opamp-buffer.md:39-342`、`a05-vref.md:39-342`、`a01-divider.md:39-270`：线性霍尔的模拟前端、基准、分压与 ADC 建立。
- `design-hardware/references/schematic-details.md:52`（SC37）：外部传感器开路、短到地/供电、负压、过量程和热插拔保护。
- `design-hardware/references/pcb-placement-details.md:13,34`（PL07、PL22）：传感器孔与外壳开口一起定位；高阻节点缩小、远离污染。
- `design-hardware/references/module-integration.md:111-155,263-274`：开漏/推挽输出结构、上拉所有权、反灌路径。
- `design-hardware/references/failures/f26-motor-start-corrupts-adc.md:67`：磁场/电场耦合机理（H2），可用于解释霍尔信号受电机线束干扰。
- `design-hardware/references/manufacturing-details.md:27`、`jlc-smt-rules.md:35`：MSL/清洗/传感器涂覆限制。

### 判定

`partial`

### 已覆盖

有通用磁/光/接近传感器选型一行、模拟前端卡（ANA-01/02/04/05）和开漏/上拉/反灌组合规则；没有霍尔的 BOP/BRP、锁存/单极、磁体与气隙、开漏上拉计算等具体内容。

### 缺口

1. 用户话术：没有把“门磁/到位/计数/换向/水表/电流检测”分流到霍尔开关、线性霍尔、霍尔角度传感器、霍尔电流传感器或干簧管。
2. 路线选择：没有单极/全极/双极锁存/线性/角度/电流的路线表；没有开漏 vs 推挽、3.3 V vs 24 V 工业、裸片 vs 模块的选择与淘汰条件。
3. 必查参数：没有 BOP/BRP/迟滞、灵敏度（mV/G）、线性范围、输出类型、灌/拉电流、温度漂移、斩波稳定、封装。
4. 电路组成：没有开漏上拉、串阻/ESD、去耦、反接保护、长线滤波/施密特整形的拓扑。
5. 参数确定：没有磁体牌号/尺寸/气隙与 B 的关系、BOP 在全温区的取值、上拉电阻 `R=(V_PULL−V_OL)/I_OL` 与上升时间 `t_r≈0.8473·R·C` 的算例。
6. 原理图：没有 TO-92/SOT-23 不同引脚顺序的逐脚表；没有开漏上拉到 MCU 3.3 V 而不是 5 V 的规则。
7. PCB：没有感应面/气隙/磁体极性方向、远离杂散磁场与磁性紧固件、连接器应力与线束固定的规则。
8. 程序：没有去抖、边沿/脉冲计数、锁存状态、轮询 vs 中断、双霍尔判方向的流程。
9. 验证：没有用实际磁体扫 BOP/BRP、全温区、气隙公差、振动、长线上升时间、EMC 的验证。
10. 常见误判：没有“只看 BOP 典型值”“忽略 BRP/迟滞”“高温磁体变弱”“上拉过大+长线导致慢边沿”“开漏上拉到 5 V 打进 3.3 V”“锁存当单极”“开关霍尔当线性”等反例。
11. 采购落地：没有检索字段（开关/线性/锁存、极性、封装、灵敏度）、模块 vs 裸片、克隆料与替代分级。

### 动作

`supplement`

### 候选型号

- **首选（开关）：DRV5032（TI）**。超低功耗、SOT-23/X2SON、资料完整；适合电池设备的门磁/到位检测。
- **首选（线性）：DRV5055（TI）**。比率输出、量程可选、资料完整；适合位置/角度模拟检测。
- A3144（Allegro 类单极开关）：低价、模块常见，但克隆料多，BOP/BRP 与温度条件需按实际来料核对。
- SS49E（Honeywell 线性）：低价线性霍尔，灵敏度/线性度按手册条件核对。

### 备注

同一份 `modules-connectors.md` 第 160 行“分流/霍尔”指霍尔电流传感器，第 162 行“磁”指位置/接近；两个“霍尔”不是一类器件。新写时必须先分流，否则用户会把 ACS712 类电流传感器当位置传感器。霍尔电流传感器的隔离、共模、dV/dt 与位置霍尔完全不同，不能共用一套参数表。

## C5 旋转编码器

### 现有内容

- `design-hardware/references/starter-patterns.md:12`：“USB小键盘/控制器……按键/编码器”一行，没有链接和电气细节。
- `design-hardware/references/design-cards/drive/d05-h-bridge.md:48`、`d06-stepper.md:50`：明确把编码器闭环排除在卡片范围外。
- `design-hardware/references/projects/p03-low-voltage-power-drive.md:50`：R10 明确不做编码器闭环。
- `design-hardware/references/pcb-placement-details.md:13`（PL07）：按钮/传感器孔与外壳开口一起定位。
- `design-hardware/references/schematic-details.md:52`（SC37）：输入异常保护，可复用于编码器线。

### 判定

`missing`

### 已覆盖

只有“按键/编码器”的起步骨架提及、驱动卡明确把编码器闭环排除在外，以及旋钮与外壳定位检查；没有编码器的电气接口、解码、去抖、测速与验证内容。

### 缺口

1. 用户话术：没有把“旋钮/档位/菜单/电机定位/手轮/车速/流量”分流到机械增量、光学增量、磁绝对、电位器或霍尔脉冲。
2. 路线选择：没有机械 EC11 vs 光学 vs 磁 AS5600/AS5047 vs 电位器的寿命/分辨率/成本/环境取舍；没有 PPR 与“档位”不是同一概念的说明。
3. 必查参数：没有 PPR、档位数、A/B/Z 通道、输出类型、最高频率、抖动时间、机械寿命、轴径/轴长、按压开关额定、绝对分辨率/精度/延迟。
4. 电路组成：没有上拉/RC/施密特整形/ESD/长线差分接收；磁编码器没有旁路、I²C 上拉、磁铁对准。
5. 参数确定：没有计数率 `f=PPR×RPM/60`、4 倍频解码、滤波时间常数与抖动/最高转速的冲突、低速周期法测速的算例。
6. 原理图：没有 A/B/Z 上拉与滤波、索引脉冲、按压开关、屏蔽/接地的逐项连接。
7. PCB：没有轴与面板开孔同轴、编码器本体固定、线缆应力释放、远离电机相线/开关节点的规则。
8. 程序：没有正交状态机、去抖、方向、位置计数、M/T 测速、索引回零、溢出处理的流程。
9. 验证：没有整圈计数、正反转、低速抖动、最高转速丢步、长线、机械寿命的验证。
10. 常见误判：没有“2 倍频/4 倍频搞错”“滤波太慢高速丢计数”“上拉太弱”“机械编码器用于伺服反馈”“PPR 当档位数”“A/B 接反”“索引脉冲受扰”等反例。
11. 采购落地：没有检索字段（PPR/档位/轴型/输出）、EC11 变体与磁编码器模块、替代分级。

### 动作

`new`

### 候选型号

- **首选（非接触）：AS5600（ams）**。I²C/PWM/模拟输出、磁角度、资料完整、模块常见；适合旋钮/电机角度。
- **首选（旋钮）：EC11（ALPS 类机械增量）**。带按压、档位清晰、成本低；需核对抖动、寿命与轴型。
- AS5047P（ams）：高分辨率、A/B/SPI/UVW，适合电机换向/高精度位置；需核对磁铁与安装公差。
- PEC11R（Bourns）：机械增量编码器，资料完整，可作为 EC11 的第二来源。

### 备注

现有三处（`d05-h-bridge.md:48`、`d06-stepper.md:50`、`p03-low-voltage-power-drive.md:50`）明确把编码器闭环排除在范围外；新组只能声明覆盖传感/解码/测速，不能声称覆盖闭环控制稳定性。`starter-patterns.md:12` 的“编码器”只是骨架词，没有链接。PL07 只管外壳开孔，不管轴同轴度和面板公差。

## C6 转速检测

### 现有内容

- `design-hardware/references/engineering-deepdives/topics/e3-thermal-mechanical-environment.md:113-123`：风扇工作点、堵转/转速回读、滤网堵塞 TACH 测不到；`:85` PQ 曲线/转速/堵转；`:215-222` 风扇 PWM/TACH 默认态、上拉电源、堵转失效；`:229-241` 正常/过热/风扇堵转状态表；`:464,478-479,514,540` 测量与排查。
- `design-hardware/references/failures/f26-motor-start-corrupts-adc.md:67`：电机线束磁场/电场耦合机理，可用于解释测速信号受扰，但不是测速方法。
- `design-hardware/references/projects/p03-low-voltage-power-drive.md:345,357`：用“命令与转速/电流不一致”间接判断故障；转速随占空比单调的验收项。
- `design-hardware/references/design-cards/drive/d05-h-bridge.md:48`、`d06-stepper.md:157`：电机转速/转矩背景，不是检测电路。

### 判定

`partial`

### 已覆盖

E3 专题对风扇 TACH/PWM 的默认态、上拉电源、堵转/失效状态有实质检查，p03 有“转速随占空比单调”的验收项；没有脉冲/编码器/霍尔/反电动势等通用测速路线与频率-转速换算。

### 缺口

1. 用户话术：没有把“风扇转速/电机转速/泵/传送带/车轮/流量”分流到 TACH、霍尔/编码器脉冲、光电、反电动势或电感式齿盘。
2. 路线选择：没有 3 线 vs 4 线风扇、TACH vs 编码器 vs 霍尔 vs 光电 vs 反电动势的精度/低速/成本取舍。
3. 必查参数：没有每转脉冲数、最低/最高频率、信号幅度/输出类型、上拉、线缆长度、更新率、分辨率与延迟、丢脉冲检测。
4. 电路组成：没有上拉/RC/施密特/光耦隔离/比较器/保护的拓扑。
5. 参数确定：没有 `RPM=f×60/N`、固定闸门计数 vs 周期测量 vs M/T 的误差与低速量化、滤波与最大频率的算例。
6. 原理图：没有 TACH 上拉到正确电源、串阻、默认态与断线检测的连接。
7. PCB：没有远离 PWM/电机相线、屏蔽/双绞、地回流与连接器的规则。
8. 程序：没有输入捕获、定时器、滑动平均、超时/堵转、方向、去抖的流程。
9. 验证：没有参考转速源、全速段扫描、低速/高速、堵转、丢脉冲、注入噪声的验证。
10. 常见误判：没有“TACH 每转脉冲数假设错”“上拉到 5 V”“滤波太慢”“平均掩盖堵转”“用 PWM 占空比当实际转速”“开漏 TACH 不上拉”等反例。
11. 采购落地：没有检索字段（风扇 TACH/霍尔/光电/编码器）、模块 vs 裸片、替代分级。

### 动作

`supplement`

### 候选型号

- **首选（通用脉冲）：DRV5032（TI）**。磁霍尔脉冲、超低功耗，配磁环/磁粒即可做转速。
- ITR9608（光电槽型）：码盘/遮光片测速，资料常见；需核对槽宽、输出与污染。
- AS5600（ams）：磁角度→转速，适合低速/高分辨率；需核对磁铁同轴度。
- A3144（单极霍尔）：低价脉冲测速，克隆料多，按实际来料核对 BOP/BRP。
- 风扇路线直接选带 TACH 的 4 线风扇；具体风扇型号按风量/静压/供电选，不在本文虚构型号。

### 备注

E3 的 TACH 内容只到“上拉是否到正确电源/堵转状态”，没有给出上拉阻值、上升时间、每转脉冲数与低速测量方法；新组需补，但不要复制 E3 的风扇热设计。E3 已正确指出 TACH 测不到滤网堵塞，不能把转速当风量。`p03` 的“转速随占空比单调”只是验收项，不是测速精度证明。

## C7 限位与接近开关

### 现有内容

- `design-hardware/references/selection/modules-connectors.md:162`：磁/光/proximity 的通用判据（感应距离、目标材料、污染、环境光）。
- `design-hardware/references/domain-design-details.md:50`（DM26）：24 V 工业 IO 的正常范围、误接、负压、浪涌、ESD、过流、地偏移、TVS/串阻/限流/隔离。
- `design-hardware/references/schematic-details.md:52`（SC37）：外部输入开路、短到地/供电、负压、过量程和热插拔保护。
- `design-hardware/references/pcb-placement-details.md:13`（PL07）：传感器孔/外壳开口一起定位。
- `design-hardware/references/module-integration.md:415-423`：案例 C03 按钮 1 µF 去抖电容拖住启动 strap。
- `design-hardware/references/failures/f30-gpio-power-on-glitch.md:21-177`：上电阶段 GPIO 误触发，可复用于限位输入默认态。
- `design-hardware/references/enclosure-integration.md:13,25`：传感器开孔/气路/涂覆与清洗。

### 判定

`partial`

### 已覆盖

有通用磁/光/接近选型一行、24 V 工业 IO 的误接/浪涌/隔离检查（DM26）、输入异常保护（SC37）与按钮去抖组合反例；没有限位/接近开关的 NPN/PNP、感应距离修正、漏电流、失效安全与安全边界内容。

### 缺口

1. 用户话术：没有把“限位/行程/到位/防撞/门磁/液位/接近”分流到机械微动、干簧、霍尔、电感、电容、光电或安全限位。
2. 路线选择：没有机械 vs 磁 vs 电感 vs 电容 vs 光电的检测对象/距离/环境取舍；没有 NPN/PNP、NO/NC、安全型 vs 普通型的路线。
3. 必查参数：没有额定感应距离 Sn、材质修正系数、迟滞、重复精度、输出类型、负载电流、压降、漏电流、10–30 V 供电、保护、开关频率、IP、机械寿命、触点额定。
4. 电路组成：没有 24 V→3.3 V 的光耦/分压+钳位+施密特、NPN/PNP 接线、漏电流导致假高、反接/TVS/隔离的拓扑。
5. 参数确定：没有分压电阻功率、门限、漏电流在输入电阻上产生的假高、光耦 CTR/上升时间、去抖时间的算例。
6. 原理图：没有三线传感器的逐脚/线色、NPN/PNP 公共端、光耦 LED 限流、NO/NC 默认态。
7. PCB：没有隔离边界/爬电/间隙、连接器、TVS 位置、丝印标识的规则。
8. 程序：没有去抖、NO/NC 逻辑、失效安全默认、卡死检测、双通道不一致、回零流程。
9. 验证：没有实际目标材质/距离/温度、误接、长线、EMC、IP、机械寿命、断电失效的验证。
10. 常见误判：没有“NPN 当干接点直接进 3.3 V”“忽略漏电流”“分压电阻功率不够”“PNP/NPN 接反”“断电时 NO/NC 状态”“铝件用额定 Sn”“电感式测塑料”“普通接近开关当安全限位”等反例。
11. 采购落地：没有检索字段（检测方式/距离/输出/供电/IP）、工业传感器货期与替代、连接器与线缆配套。

### 动作

`supplement`

### 候选型号

- **首选（机械限位）：D2F-5（Omron）**。微动开关、资料完整、常见；适合行程终点/防撞。
- **首选（非接触金属）：TL-Q5MC1-Z（Omron）**。电感式、NPN、10–30 V、三线，适合工业到位检测。
- EX-13A（Panasonic）：光电接近，适合非金属/长距离；需核对检测方式与污染。
- MK23-35（Meder）：干簧管，适合门磁/低功耗；需核对磁体与安规边界。
- 安全相关限位另选安全型（双通道/强制断开），并按适用标准由专业人员签核，不在本组声称认证。

### 备注

DM26 只给 24 V 工业 IO 的通用检查，没有 NPN/PNP、漏电流和失效安全；SC37 是通用输入保护。`design-cards/analog/a09-bridge.md:219` 的“机械限位”指称重过载止挡，不是限位开关，检索时不要混用。安全限位、防爆、医疗、汽车应用必须在组文件里写清专业签核边界。

## 复用关系

- C1/C2/C3 的数字接口复用 IF-01（I²C）、IF-03（SPI）、IF-04（多从机/片选）、IF-12（电平转换）与 `examples/x05-i2c.md`（上拉、总线电容、ESD、地址 strap）。
- C1 模拟输出、C4 线性霍尔复用 ANA-01/ANA-02/ANA-04/ANA-05 与 `engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md`、`calculations/analog-adc.md`。
- C1/C2/C3 的电源/上拉/反灌/地址冲突复用 `module-integration.md` §4.1/§4.3/§5.1/§6.3/§8.2 与 D1 专题；掉电拖总线复用 F28。
- C2 IMU 复用 PL25、DM24、`casebook/low-power-wireless-battery.md`（BMI088/MPU9250/LSM6DS3/LIS3MDL）与 `casebook/motor-power-industrial.md`（双 IMU 互斥装配）。
- C4/C6 复用 F26 的磁场/地耦合机理与 E3 的风扇 TACH/堵转状态表；C6 的电机侧复用 DRV-05/DRV-06 与 p03 的转速验收项。
- C5 与 DRV-05/DRV-06 的边界：驱动卡只覆盖功率级与电流采样，编码器解码/测速由本组覆盖；p03 明确不做闭环。
- C7 复用 DM26、SC37、F30（上电默认态）、`module-integration.md` 案例 C03（去抖电容拖 strap）与 `enclosure-integration.md` 的传感器开孔/涂覆。
- 全部主题的采购落地复用 `lcsc-sourcing.md`、`selection/lcsc-verification.md`、`selection/replacement-classes.md`、F31；封装/MSL/清洗复用 MF16 与 `jlc-smt-rules.md:35`。
- 热漂移/自热复用 `thermal/topic.md`；测量方法复用 `simulation-measurement.md` §5–§6；新手话术复用 `beginner-journey.md` 的“负载类型/环境与防护”问法。

## 需要同步修正

1. `design-hardware/references/selection/modules-connectors.md:160,162`：现有表把“分流/霍尔”和“磁/光/proximity”并列，且没有磁力计/航向行。建议拆成“电流（分流/霍尔电流传感器）”“磁开关/线性霍尔”“磁力计/罗盘”“光电/电感/电容接近”四类；磁力计判据应写量程、分辨率、硬/软铁校准、磁干扰，而不是“感应距离”。理由：同一“霍尔”被用于两个完全不同的器件类别，直接引用会误导选型。
2. `design-hardware/references/domain-design-details.md:45`（DM24）：把“温湿度/气压/气体/光学/惯性”放在同一条“物理测量条件”下，容易让人以为 IMU/加速度计需要气路或窗口。建议拆成环境传感器（保留 G08 气路/涂覆/清洗）与惯性/运动传感器（板弯、振动、轴向、热梯度、旋转中心），并链接新组 C1/C2 与 PL25。
3. `design-hardware/references/pcb-placement-details.md:36-37`（PL24/PL25）：PL24 只写环境传感器，PL25 只写 MEMS 机械应力。建议扩展 PL25：加速度计/IMU 的敏感轴、安装基准、旋转/振动中心、刚性固定与减振取舍；并新增一条磁传感器放置检查（远离电流回路、电感、扬声器、磁铁、铁磁外壳/螺钉）。若新增检查 ID，需同步 SKILL.md 的“190 条”计数与 design-experience 的条目说明。
4. `design-hardware/SKILL.md:99-149` 的按需读取表没有“运动/位置/转速/角度”入口；`design-hardware/references/engineering-deepdives/README.md:31-50` 的“按症状找”也没有姿态漂移、指南针不准、编码器丢步、转速跳变等行。新组交付后应各加一行路由，否则 Agent 不会按需加载。
5. `design-hardware/references/starter-patterns.md:12`、`design-cards/drive/d05-h-bridge.md:48`、`design-cards/drive/d06-stepper.md:50`、`projects/p03-low-voltage-power-drive.md:50`：编码器只被提及或被排除，没有指向新组。建议在四处加交叉链接，并明确“C5 只覆盖传感/解码/测速，不覆盖闭环控制稳定性”。
6. `design-hardware/references/design-cards/analog/a09-bridge.md:219`：“机械限位”指称重过载止挡，不是限位开关。建议改成“机械止挡/过载限位”，避免与 C7 的限位开关混淆。
7. `design-hardware/assets/scenarios.json`：35 个场景中没有运动/位置/转速类用户话术（倾斜、振动、指南针、编码器、转速、限位均无）。建议在 C 组交付时补 3–5 个场景，至少覆盖“旋钮调参”“风扇测速”“门磁/到位”“倾角/振动”。这不是现有错误，但会限制用户话术覆盖的验收。

## 文件组织建议

- 建议一个组文件，不拆成 7 个独立文件：`design-hardware/references/common-hardware/c-motion.md`。理由：7 个主题共享同一条链路（传感器→偏置/上拉→ADC/GPIO/总线→MCU），且都要复用同一批 ANA/IF/PL/DM 检查；拆文件会重复上拉、反偏、ADC 建立和放置规则。
- 建议结构（最终拼接文件，约 800–900 行）：
  - `## 0. 本组怎么用`：约 40 行；用户话术 → 先判断什么 → 推荐路线 → 读哪个主题。
  - `## C1 加速度计`：约 110 行。
  - `## C2 陀螺仪与 IMU`：约 120 行。
  - `## C3 磁力计`：约 90 行。
  - `## C4 霍尔开关与线性霍尔`：约 110 行。
  - `## C5 旋转编码器`：约 110 行。
  - `## C6 转速检测`：约 80 行。
  - `## C7 限位与接近开关`：约 110 行。
  - `## 本组来源`：约 35 行；CHW-S 表（文档号/版本、实际读到的章节、支持的结论、不能推广的部分、URL）。
- 写作时先在 scratch 拆分：`scratch/groups/c-motion/00-intro.md`、`01-accelerometer.md`、`02-gyro-imu.md`、`03-magnetometer.md`、`04-hall.md`、`05-encoder.md`、`06-speed.md`、`07-limit-proximity.md`、`99-sources.md`、`99-fixes.md`，再由集成人按顺序拼接。
- 每个主题固定 12 个三级标题（用户会怎么说/路线选择/必查参数/电路组成/参数与算例/原理图与逐脚/PCB/程序/验证/常见误判/采购与落地/来源与证据），开头 1–3 行结论先行 + 证据标签；已有卡片内容只链接，不复制。
- 集成约束：`tests/test_design_content.py:190-207` 会扫描所有 `[A-Z]{2,4}-S\d+` 引用必须在 `source-register.md` 登记，并拦截未标注的 `C\d{4,}` 商品编号；新组引用的原厂文档需分配 CHW-S 编号并登记，采购小节只写检索字段和 `待查`，不写 C 号/库存/价格。
