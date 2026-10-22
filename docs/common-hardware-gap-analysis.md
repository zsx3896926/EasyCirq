# 常用硬件能力缺口分析与内容架构

> 输入：[13 份分组审计](evidence/common-hardware-2026-10-22/audit/)（a-environment … m-wireless-time）。
> 审计对象：本仓库，基线 `origin/main` = `0fe5cf8`，2026-10-22。
> 本文件是开工盘点记录；实际写作按 `design-hardware/references/common-hardware/` 的 13 个组文件执行，不另建 28 张提升卡（避免同一电路多份近似文档）。
> 判定口径：`adequate` 已足够、可直接引用；`partial` 有基础但缺本主题具体内容；`missing` 没有本主题内容。判定与动作均按审计原文汇总，本文件不重新评级。
> “本轮”指本次 `common-hardware` 内容写作与旧内容修正轮；二轮范例/故障卡另列。

## 0. 总表

### 0.1 计数

13 组共 **102 个主题**（任务书口径“约 100 个”）。

| 组 | 领域 | 主题数 | adequate | partial | missing | new | supplement | reuse |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | 温度、湿度与环境传感 | 7 | 0 | 3 | 4 | 5 | 1 | 1 |
| B | 光、接近、距离与人体检测 | 8 | 0 | 2 | 6 | 6 | 2 | 0 |
| C | 运动、位置、转速与角度 | 7 | 0 | 4 | 3 | 3 | 4 | 0 |
| D | 力、重量、压力、液位与流量 | 7 | 0 | 5 | 2 | 5 | 2 | 0 |
| E | 电压、电流与电能测量 | 7 | 2 | 5 | 0 | 3 | 2 | 2 |
| F | 常用低压供电入口与保护 | 8 | 3 | 4 | 1 | 3 | 2 | 3 |
| G | LDO、降压、升压与反相电源 | 8 | 3 | 5 | 0 | 2 | 6 | 0 |
| H | 电池、充电与低功耗设备 | 8 | 5 | 3 | 0 | 2 | 1 | 5 |
| I | 常见主控与最小系统 | 8 | 1 | 5 | 2 | 2 | 5 | 1 |
| J | 数字总线与常见有线通信 | 8 | 0 | 8 | 0 | 0 | 8 | 0 |
| K | 开关、继电器与电机负载 | 9 | 1 | 6 | 2 | 3 | 5 | 1 |
| L | 显示、声音、按键与交互 | 9 | 0 | 4 | 5 | 5 | 4 | 0 |
| M | 无线、时间与常用功能模块 | 8 | 0 | 6 | 2 | 4 | 4 | 0 |
| **合计** |  | **102** | **15** | **60** | **27** | **43** | **46** | **13** |

判定占比：adequate **15/102 = 14.7%**，partial **60/102 = 58.8%**，missing **27/102 = 26.5%**。
动作占比：new **43/102 = 42.2%**，supplement **46/102 = 45.1%**，reuse **13/102 = 12.7%**。

### 0.2 读法

- 每个主题的“现有内容”只列主依据与关键行号，完整证据在对应审计文件。
- “首选型号”是写作时第一个打开原厂手册核对的锚点，不是推荐量产料号；不写 C 号、库存、价格。
- `adequate` 不等于“本轮不写”：15 个 adequate 主题仍要补用户话术、路线入口、采购字段（每组清单会列），但不得重写已有公式。
- 102 个主题中，**真正从零写（missing + new）27 个**；**有基础但要补（partial + supplement）60 个**；**只做引用与路由（adequate/reuse）13 个**。

---

## 1. A 温度、湿度与环境传感

审计结论：A 组是“两张有基础的卡（A1/A3 共用 `ANA-10`）+ 一张半成品（A5）+ 四个空白（A2/A4/A6/A7）”。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| A1 | NTC 温度测量 | `ANA-10` L37–270 已有分压/恒流、自热、选型行；`passives` L204 一行判据；`PWR-06` TS 门限 | partial | supplement | Murata `NCP15XH103F03RC` |
| A2 | 数字温度传感器 | 仅 `IF-01` I²C 总线、`x05` 总线范例、`D1` 地址 strap、`B2` standby | missing | new | TI `TMP117` |
| A3 | 铂电阻测温 | `ANA-10` 整卡 RTD（2/3/4 线、双 IDAC、比率、误差预算）；`C1` L211–231 | partial | reuse | Vishay `PTS0603M1B100RP100` |
| A4 | 热电偶测温 | 仅 `DM22` 一句“要冷端补偿”；`thermal/topic.md` §8.1 是用热电偶测壳温的方法 | missing | new | Maxim `MAX31855` |
| A5 | 温湿度传感器 | `x05` 总线、`DM24/PL24/G08/P01` 布置与验收门槛；无测量原理/换算/校准 | partial | new | Sensirion `SHT40` |
| A6 | 气压与高度估算 | 仅 `DM24/PL24` 通用布置、BME280 实例与检索词 | missing | new | Bosch `BMP390` |
| A7 | 空气质量与气体检测 | 仅 `DM24/PL24/enclosure` 通用气路要求；无原理/标定/安全 | missing | new | Sensirion `SGP41`；真 CO2 用 `SCD41` |

### A 组本轮必须新写/补充的内容

1. **`ANA-10` 补 NTC 专项（A1，约 +100 行）**：§3 补 `R_TOP≈sqrt(R_Tmin·R_Tmax)`、NTC 分压/恒流偏置与 compliance、线性化可选性；§4 补偏置步骤；§5 补 10 kΩ/B≈3380、−20…80°C、3.3 V/12 bit 算例（码值→电阻→Beta/Steinhart-Hart→温度）；§6/§10/§12 补选型、开路/短路、自热正反馈与来源。
2. **`ANA-10` 新增 §13（A3，约 40 行）**：IEC 60751 A/B/1/3B 公差、CVD 系数与反解、Pt1000 的 IDAC/自热重算、`MAX31865`/`ADS112C04` 两条集成/分立路线、探头/线制/校准证书。
3. **`SEN-01` 数字温度（约 210 行，12 节）**：本地 vs 远程二极管/热电偶、I²C/SPI/1-Wire、max over temperature、分辨率 vs 转换时间、自热、ALERT/THERM、寄存器/one-shot/CRC、参考温度计比对。
4. **`SEN-02` 热电偶（约 230 行）**：K/J/T/E/N 选型、Seebeck 与公差等级、冷端等温块、`MAX31855/31856` vs `AD8495`、µV 级误差预算、断线检测、NIST 查表、冰水混合物验证。
5. **`SEN-03` 温湿度（约 210 行）**：电容式 RH 原理、RH 精度定义（20–80%RH/全温区/迟滞/漂移）、结露恢复、加热器、滤膜/气孔、恒温恒湿箱校准、装壳前后对比。
6. **`SEN-04` 气压/高度（约 200 行）**：绝压/差压/表压、`h=44330×(1−(P/P0)^(1/5.255))`、`P0`/QNH 更新、噪声→高度（海平面约 8.3 m/hPa）、OSR/IIR、导压管/防水膜。
7. **`SEN-05` 气体/空气质量（约 230 行）**：NDIR/光声/MOX/电化学/PM 路线、预热/老化、交叉灵敏度、clean-air 基线、ABC 校准、CO 报警认证边界（EN 50291/UL 2034 只写“需取得并核对”，不写已满足）。
8. **`sensing/README.md`（约 110 行）**：7 主题选择矩阵、共用 11 问检查表、气路/布置/校准/采购边界；`design-cards/README.md` 与 `SKILL.md` 增加路由。
9. **同步**：`source-register.md` 新增 NTC R-T、TMP117、MAX31855/31856、SHT4x、BMP390、SGP41/SCD41 等 6–10 条来源；`P01` 的 RH/T 精度拆成量程/温度/迟滞/漂移四项。

---

## 2. B 光、接近、距离与人体检测

审计结论：60 张设计卡中没有任何光学/接近/测距/人体检测卡；B1/B2 可“复用+补”，B3–B8 需要新写。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| B1 | 环境光检测 | `ANA-01/02/04` 通用采集链；`selection` L162 一行“磁/光/proximity”；无 lux/ALS | partial | supplement | Rohm `BH1750FVI`（高精度 `OPT3001`） |
| B2 | 光电二极管前端 | `C3` §2.5 一行高源阻抗提示；`ANA-02/04/05` 运放/ADC/基准；无 TIA | partial | supplement | ams-OSRAM `BPW34` + TI `OPA320` |
| B3 | 反射式光电检测 | 仅 `selection` L162 一行；`DRV-01/07` 可作发射驱动 | missing | new | Vishay `TCRT5000` |
| B4 | 对射与槽型检测 | 仅 `selection` L162；`DRV-01`、`MCU-01/04` 可复用 | missing | new | Vishay `TCST1103` |
| B5 | PIR 人体检测 | 仅 `PL07/PL24`、`enclosure` 光窗、`MF14/16` 通用条目 | missing | new | Panasonic `EKMC1601111` |
| B6 | ToF 测距 | 无；可复用 `IF-01/IF-12`、`PWR-01/02`、`module-integration` §6 | missing | new | ST `VL53L1X` |
| B7 | 超声测距 | 无；可复用 `MCU-01`、`IF-12`、`PWR-01/02`、`enclosure` 声孔 | missing | new | MaxBotix `MB1240` |
| B8 | 毫米波存在感知 | 无；可复用 `RF-01/02`、`IF-05`、`PWR-01/02`、`D4` | missing | new | Hi-Link `LD2410C`（原厂资料路线 `BGT60LTR11AIP`） |

### B 组本轮必须新写/补充的内容

1. **组文件 `b-optics.md` 约 800–950 行**，8 节各 70–110 行；先写两张对照表：PIR vs mmWave（运动/存在/静止/误报）、反射 vs 对射 vs ToF/超声（目标/量程/环境光/成本）。
2. **B1（70–90 行）**：LDR 分压 → 光电二极管+TIA → 数字 ALS 路线；lux 标定、CIE 人眼匹配/红外抑制、光窗/遮光、PWM 频闪。
3. **B2（90–110 行）**：TIA 拓扑、`Vout=Iph×Rf`、`Cf` 与 `Cd`/GBW 相位裕度、`Ib×Rf`、guard ring/漏电/助焊剂、暗电流扣除、lock-in。
4. **B3（80–100 行）**：IR LED + 限流/调制 + 光电晶体管 + 比较器/ADC；CTR、反射率、发射-接收遮光墙、38 kHz 同步解调、LED 老化。
5. **B4（70–90 行）**：槽宽/孔径/遮光片、开集/推挽、施密特整形、边沿计数/转速、最小可检测物与最高计数频率。
6. **B5（80–100 行）**：热释电双元/三元 + 菲涅尔 + 前置放大（0.1–10 Hz）；延时/重触发、预热、气流/热源/阳光误报；明确 PIR 只测运动。
7. **B6（90–110 行）**：单点/多区 ToF、940 nm Class 1、量程随反射率/环境光、盖板折射/串扰、XSHUT 地址分配、offset/crosstalk 校准、眼安全声明。
8. **B7（80–100 行）**：40 kHz 换能器/驱动/接收、`c≈331+0.6T`、盲区/波束角、软/吸声目标、5 V ECHO 电平、多传感器轮流触发。
9. **B8（90–110 行）**：24/60 GHz 模块路线、UART/EN/复位、天线净空/壳体、安装角度、风扇/窗帘/金属误报、法规与“模块有售≠目标市场允许”；裸芯片 RF 另请评审。
10. **来源**：预留 14–20 条；模块类（HC-SR501/HC-SR04/LD2410）只作 E2/E3。

---

## 3. C 运动、位置、转速与角度

审计结论：60 张卡中没有运动/位置/转速类卡片；C1、C3、C5 基本从零写，C2、C4、C6、C7 可复用少量基础。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| C1 | 加速度计 | `PL25` 一句 MEMS 机械应力；`DM24` 一句惯性布置；`ANA-01/02/04/05` 模拟路线 | missing | new | ST `LIS2DH12TR` |
| C2 | 陀螺仪与 IMU | `D1` §6.3 未上电 ESD、`F28` 掉电拖总线、`PL25`、casebook BMI088/MPU9250 | partial | supplement | ST `LSM6DS3TR-C` |
| C3 | 磁力计 | 仅 `selection` L162 一行和 LIS3MDL 位号记录；无航向/硬软铁校准 | missing | new | ST `LIS3MDL` |
| C4 | 霍尔开关与线性霍尔 | `selection` L160/162 两个“霍尔”混用；`ANA-01/02/04/05`、`SC37` 可复用 | partial | supplement | TI `DRV5032`（开关）/ `DRV5055`（线性） |
| C5 | 旋转编码器 | 仅 `starter-patterns` L12 提及；`DRV-05/06`、`P03` 明确排除闭环 | missing | new | ams `AS5600`（非接触）/ ALPS `EC11`（旋钮） |
| C6 | 转速检测 | `E3` L113–123 风扇 TACH/堵转；`P03` 转速验收项；无通用测速 | partial | supplement | TI `DRV5032` + 磁环；4 线风扇 TACH |
| C7 | 限位与接近开关 | `DM26` 24 V 工业 IO、`SC37` 输入保护、`F30` 上电默认态 | partial | supplement | Omron `D2F-5`（机械）/ `TL-Q5MC1-Z`（电感） |

### C 组本轮必须新写/补充的内容

1. **组文件 `c-motion.md` 约 800–900 行**：`## 0` 40 行；C1 110、C2 120、C3 90、C4 110、C5 110、C6 80、C7 110；来源 35 行。
2. **C1**：量程/噪声密度/ODR/带宽/零偏温漂/横轴灵敏度；`Δθ≈a_noise/g`；六面 1 g 翻转、转台/振动台；敏感轴/安装基准/板弯应力。
3. **C2**：6 轴 vs 9 轴、陀螺量程/零速率偏移/bias instability、互补/Kalman 频段、静止零偏、双 IMU 共用片选互斥、`WHO_AM_I`/FIFO/DRDY。
4. **C3**：AMR/GMR/TMR/Hall/磁通门、量程（±2–16 Gauss）、1° 航向约需 0.57 µT（中纬度量级）、硬铁/软铁椭球拟合、360° 校准、远离电机/扬声器/铁磁件。
5. **C4**：单极/全极/双极锁存/线性/角度/电流分流；BOP/BRP/迟滞、磁体-气隙、`R=(V_PULL−V_OL)/I_OL`、`t_r≈0.8473·R·C`；开漏上拉到 3.3 V 而非 5 V。
6. **C5**：机械 EC11 vs 光学 vs 磁 AS5600/AS5047 vs 电位器；PPR vs 档位；`f=PPR×RPM/60`、4 倍频、抖动/最高转速冲突、M/T 测速、索引回零；声明不覆盖闭环稳定性。
7. **C6**：3 线 vs 4 线风扇、TACH vs 编码器 vs 霍尔 vs 光电 vs 反电动势；`RPM=f×60/N`、固定闸门 vs 周期测量、丢脉冲/堵转、上拉电源。
8. **C7**：机械/磁/电感/电容/光电路线；NPN/PNP、NO/NC、Sn 材质修正、漏电流假高、光耦/分压+钳位、失效安全、双通道；安全限位只写“专业签核”。
9. **同步**：`selection` L160/162 拆成四类；`DM24` 拆环境 vs 惯性；`PL25` 扩敏感轴/旋转中心；`SKILL.md` 加运动路由；`scenarios.json` 补 3–5 个场景。

---

## 4. D 力、重量、压力、液位与流量

审计结论：D1 有 `ANA-09` 强基础；D2/D3/D5/D7 部分；D4/D6 空白；7 个主题都缺“产品化/机械/校准/采购”这一段。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| D1 | 称重与应变桥 | `ANA-09` 整卡桥式前端、四/六线、比率、误差预算；`ANA-03/04/05`、`C1` | partial | supplement | `HX711`（低成本）/ TI `ADS1232`（原厂路线） |
| D2 | 模拟压力传感器 | 仅 `F26` 构造案例与 `ANA-01/02/04/05` 通用链；`ANA-09` 只覆盖桥式芯体 | partial | new | NXP `MPXV5010DP` |
| D3 | 数字压力传感器 | `IF-01/03/12`、`x05`、BMP280/BMP388 strap 记录、`P01` | partial | new | Bosch `BMP388` / TE `MS5837-30BA` |
| D4 | 液位检测 | 仅 `ANA-08` 4–20 mA、`enclosure` 密封/凝露；无液位路线 | missing | new | `JSN-SR04T` / `XKC-Y25-V` |
| D5 | 土壤与介质湿度 | `S01` 花盆提醒、`product-example/acceptance`、`enclosure` 涂层/腐蚀；无探头电路/标定 | partial | new | DFRobot `SEN0308` |
| D6 | 脉冲流量计 | 无；仅 `IF-12` 电平、`ANA-08` 4–20 mA、`F26` 泵噪 | missing | new | `YF-S201` |
| D7 | 模拟量流量与液位接口 | `ANA-08` 4–20 mA 完整、`ANA-01` 0–10 V 分压、`P02/x10` 工业节点 | partial | supplement | TI `INA149`（0–10 V）/ `RCV420`（旧例对照） |

### D 组本轮必须新写/补充的内容

1. **7 张卡合计约 1520 行**（按审计分项相加；审计另写合计 1580；若压成组文件则 1000–1200 行）：D1 180、D2 240、D3 220、D4 240、D5 220、D6 220、D7 200。
2. **D1**：只补“称重产品化”——HX711/ADS1232/NAU7802/CS1237 路线、额定容量 vs 安全/极限过载、偏载/重复性/蠕变、四线 vs 六线、连接器 Kelvin、去皮/两点校准、砝码等级；桥式公式全部引用 `ANA-09`。
3. **D2**：比率型 vs 4–20 mA vs 数字 vs 桥式芯体；proof/burst、TEB、介质兼容、端口/O 圈、`Vout=Vs×(0.1P+0.5)` 类传递函数、5 V 输出进 3.3 V ADC 的保护、压力源/泄漏/过压验证。
4. **D3**：BMP388/MS5837/SDP810 路线；绝压/表压/差压、通气孔/防水膜、`CSB/SDO` strap、过采样×IIR×转换时间×功耗、气压→海拔/水压→水深、凝露/涂覆禁区。
5. **D4**：点式 vs 连续量；浮球/干簧、电容、超声、静压/投入式、电导、雷达、光电；盲区/泡沫/蒸汽/凝露、罐体几何→体积、泵控滞回/干转/满溢、4–20 mA 隔离。
6. **D5**：电阻式/电容式/TDR/FDR/张力计；交流激励避免极化、盐分/EC/温度修正、干湿两点/多点标定、探头灌封/腐蚀、烘干称重法对比。
7. **D6**：涡轮/霍尔、桨轮、超声、电磁、差压；K 系数/每升脉冲数、脉冲宽度/开集/推挽、输入捕获/去抖/累计、最小流量/气泡/回流、5 V→3.3 V。
8. **D7**：0–10 V 输入阻抗/过压/24 V 误接/反接、隔离前端；差压流量平方律、液位 4/20 mA 标定、NAMUR NE43/HART、阻尼/故障电流；`ANA-08` 的 4–20 mA 主体不重写。
9. **同步**：`selection` 传感器表补压力/液位/流量/土壤行；`source-register` 补 HX711/ADS1232/MPX/MS5837/YF-S201 等；`scenarios` 补称重/压力/液位/流量场景。

---

## 5. E 电压、电流与电能测量

审计结论：E1/E2 可直接引用；E3/E6 补；E4/E5/E7 新写。E 组是 13 组中基础最好的一组，但“双向/隔离/多通道/电量计”仍是空白。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| E1 | 电压采样 | `ANA-01` 整卡分压/源阻抗/采集/误差/保护；`ANA-02/04/05`、`B2` §5.1、`P01` §4.6 | adequate | reuse | Vishay `TNPW0805` |
| E2 | 低侧电流采样 | `ANA-06` 整卡、`x09`、`F01`、`P02` 100 Ω 4–20 mA 例 | adequate | reuse | TI `INA181A2` |
| E3 | 高侧电流采样 | `ANA-07` 整卡、`ANA-03`、`P03` §4.6、`C4` §2.4/§2.5 | partial | supplement | TI `INA240A2`（模拟）/ `INA228`（数字） |
| E4 | 双向电流测量 | `ANA-06/07` 仅“反向饱和”一行；`D05` H 桥、`C4` §7.3 负值假象 | partial | new | `INA181A2 + REF=VCC/2` |
| E5 | 隔离电流检测 | `ANA-07` 隔离分支提示、`ANA-08` ISO122 旧例、`SC38/RT10`、`C2` | partial | new | TI `AMC1300B`（分流）/ `AMC1306M05`（ΔΣ） |
| E6 | 电池电量估算 | `B3` §2.7/§5.2/§6、`D-S02`、`PWR-08/DM16`、`energy-battery` | partial | supplement | TI `BQ27441-G1` |
| E7 | 多通道采样 | `ANA-01` §10 串扰、`ANA-04` MUX 建立、`analog-adc` §5.6、`F22` | partial | new | TI `ADS1115`（低速）/ `ADS131M08`（同步 8 通道） |

### E 组本轮必须新写/补充的内容

1. **组文件 `e-measurement.md` 约 695 行**：`## 0` 40；E1 70、E2 55、E3 75、E4 100、E5 110、E6 105、E7 100；来源 40。
2. **E1**：补电池/母线/0–10 V 场景路由、常接/GPIO 门控/load switch/1 MΩ+缓冲四条低功耗路线、门控时序（接通→建立→采样→关断）、母线瞬态/过压、爬电/间隙。
3. **E2**：补“保护/计量/趋势”目的分流、低侧 vs 高侧 vs 隔离路线表、专用 CSA 的 REF/滤波/保护、零点/增益校准、过流阈值/延时、脉冲/温升/热电动势。
4. **E3**：必修 §5 `V_os` 10 倍错误；补 CSA vs 数字功率监测 vs 分立差放 vs 隔离/霍尔路线、PWM 同步/blanking、AC CMRR 频率扫描、共模瞬态 dV/dt/脉宽。
5. **E4（100 行，新写）**：REF 中点偏置、正负满量程/过零失调/正反向增益匹配、`I=(code−code_zero)×k`、三点校准、H 桥正反转/回生、PWM 边沿负值先排除测量假象。
6. **E5（110 行，新写）**：隔离放大（AMC1300）vs 隔离 ΔΣ（AMC1306+SDFM）vs 霍尔（ACS724/TMCS1100）；隔离 DC-DC、CMTI、传播延迟、隔离带/爬电、hipot/漏电验证；不声称安规认证。
7. **E6（105 行）**：产品形态路线（只报警/分压+ADC/库仑计/IT/ModelGauge/多串 monitor）、电芯 OCV-SOC/内阻-温度-老化、Design Capacity/Chem ID、SRP/SRN Kelvin、SOC 平滑/低电关机、生产校准/换包重配。
8. **E7（100 行）**：外部 MUX vs 多 SAR vs 多通道 ΔΣ vs sequencer；`通道数×扫描率×建立时间≤1/fs` 预算、MUX Ron/电荷注入/漏电、同时 vs 顺序采样、通道间增益/偏置校准、丢首样本。
9. **同步**：修 `ANA-06/07/01` 的确定错误；`A02:55/A03:52` 的“隔离卡”改指 E5；新增型号登记 CHW-S 约 10–14 条。

---

## 6. F 常用低压供电入口与保护

审计结论：F2/F5/F6 可直接引用；F1/F4/F7/F8 补/新；F3（USB PD）完全空白。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| F1 | USB 供电 | `PWR-12` USB-C 5 V sink、`IF-09/10`、`x08`、`F09/F27`、`P04`（明确未做保护链） | partial | supplement | TI `TPD3S014` |
| F2 | USB-C 固定低压取电 | `PWR-12`、`IF-10`、`x08`、`F09`、`P04` | adequate | reuse | TI `TUSB320LAI` |
| F3 | USB PD 电源输入 | 仅多张卡声明“PD 不在范围”；无 PDO/控制器/高压 | missing | new | ST `STUSB4500` |
| F4 | 直流端子与圆孔输入 | `selection` §4.1/§4.2、`b1` MNT DC 座链路、`F27`、`P03` | partial | new | CUI `PJ-002A` |
| F5 | 反接保护 | `PWR-09` 整卡四种拓扑、`PWR-05`、`b1`、`F27`、`SC16` | adequate | reuse | `AO3401A` / TI `LM66100` |
| F6 | 过流与短路保护 | `PWR-11` 保险/PTC/eFuse/限流、`PWR-10`、`power-thermal` §5.4 | adequate | reuse | TI `TPS2595` |
| F7 | 过压与瞬态保护 | `selection/semiconductors` §3 TVS 钳位链、`power.md`、`SL04`、`b1` §4.1 | partial | new | Littelfuse `SMBJ5.0A`；TI `BQ24313` |
| F8 | 浪涌与热插拔 | `PWR-10` SOA/功率限制、`SL01` LC 振铃、`PWR-12` 插入浪涌、`PWR-05` 输入电容 | partial | supplement | TI `TPS2595`（低压）/ `LM5069`（12–48 V） |

### F 组本轮必须新写/补充的内容

1. **组文件 `f-low-voltage-power-input.md` 约 760–840 行**：`## 0` 45；F1 85、F2 60、F3 120、F4 75、F5 50、F6 60、F7 110、F8 85；来源 60。
2. **F1**：补 USB-A/Micro-B、BC1.2 D+/D− 检测、USB 2.0 500 mA / USB 3.x 900 mA / Type-C 1.5/3 A 的区分、端口限流开关/ESD/PTC 入口链、VBUS 检测/枚举前限流。
3. **F3（120 行，新写）**：固定 5 V / PD trigger / 自主 PD sink / MCU 协议栈 / Source 五条路线；PDO/APDO/PPS/EPR、e-marker 5 A、VCONN、VBUS 电容/放电、背靠背 MOS、20/28/48 V 爬电、PD 分析仪/各 PDO/热插拔验证。
4. **F4（75 行）**：DC 座/螺钉端子/弹簧端子/XT30/XT60 路线；内外径/针径/额定电流/接触电阻/插拔寿命/中心极性/插入检测/线规/扭矩；中心正不是通用前提。
5. **F7（110 行）**：TVS 并联 vs 串联 OVP vs eFuse 集成 OVP vs 充电器前端四条路线；`VWM/VBR(min)/VC@Ipp` 与脉冲功率/能量、IEC 61000-4-5/4-2 等级到 `Ipp/VC` 的换算、TVS 失效短路/单向双向/保险 I²t 协调。
6. **F8**：补 5–24 V/0.5–5 A 低压 eFuse/负载开关/dv/dt 限流路线、连接器插拔顺序、线缆电感/输入电容 ESR、重复插拔/不同相位验证；`PWR-10` 的 24 V/8 A 算例不直接套。
7. **F5/F6**：只补 5 V 栅压 `Rds(on)@VGS`、连接器机械防反、理想二极管；低压端口开关/PTC 复位后压降/FLT 状态机。
8. **同步**：修 `b1:28`、`p05:50` 的 PD 错向；统一 `f09` 与 `p12` 的 CC 窗口；`<10 µF` 加“BQ2407x/USB 2.0 条件”；来源表 PWR-S11/13/14 列错位。

---

## 7. G LDO、降压、升压与反相电源

审计结论：G1–G3 是高质量强卡；G4 只有 TPS63802 一条完整链；G5/G6 只有边界声明；G7/G8 有分散基础。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| G1 | LDO | `PWR-01` 整卡、`x02`、`power-thermal` §3.2/§4.3/§5.2、`F02/F25/F11` | adequate | supplement | TI `TPS7A02` |
| G2 | Buck | `PWR-02` 整卡、`x01`、`power-thermal` §3.3–§3.5、`F10/F12/F11/F31` | adequate | supplement | TI `TPS54202H` |
| G3 | Boost | `PWR-03` 整卡、`power-thermal` §5.7、`F12` | adequate | supplement | TI `TPS61023` |
| G4 | Buck-Boost | `PWR-04` 四开关 TPS63802 完整链、`P14`、`B2` | partial | supplement | TI `TPS63802` |
| G5 | 反相电源 | 仅 `PWR-04`/`power-ics` §10 的“未覆盖”声明与若干负压需求场景 | partial | new | TI `TPS63710` |
| G6 | 隔离 DC/DC | 仅 `module-cards` §10、`DM45/46`、`I07/I08` 的“隔离收发器+隔离 DC/DC”边界 | partial | new | TI `SN6501` |
| G7 | 负载开关 | `PWR-05`/`PWR-11`/`PWR-10`/`PWR-09`/`DRV-02` 中的零散选型行 | partial | supplement | TI `TPS22918` |
| G8 | 多路电源与电源切换 | `PWR-05` 整卡、`b1`、`b4`、`module-integration` §8、`P14` | partial | supplement | TI `TPS2116` |

### G 组本轮必须新写/补充的内容

1. **组文件 `g-converters.md` 约 950–1150 行**：`## 0` 50–70；G1 70–90、G2 90–110、G3 90–110、G4 90–110、G5 130–160、G6 140–180、G7 90–120、G8 90–110；来源 50–70。
2. **G1**：补用户入口/路线判据、PSRR/噪声密度/负载瞬态 `ΔI·Δt/C+ESR`、EN/PG/可调配置、采购字段；修 `5% 反向电流`、`TJ(max)`、VDO 95% 判据。
3. **G2**：补集成同步/非同步/控制器+FET/模块路线、环路补偿与相位裕度、最小 on/off、轻载 PFM/DCM、软启动/UVLO/PG、Bode/EMI 预扫。
4. **G3**：补 Boost vs 电荷泵 vs Buck-Boost vs 隔离 vs 模块、RHP 零点/带宽、输出断开、输入源限流（USB/电池）先于芯片限流、预偏置启动/残压。
5. **G4**：补四开关 vs SEPIC vs 反相 vs 两级 vs 模块、通用 L 公式、模式门限/fS/限流、模式切换点效率/纹波、SEPIC/反相边界。
6. **G5（130–160 行，新写）**：先判“是否真的需要负压”（运放/4–20 mA/RS-232/半桥负偏压）；反相 Buck-Boost vs 电荷泵两条主线；D=`|VOUT|/(|VOUT|+VIN)`、应力 `VIN+|VOUT|`、飞电容/输出电阻/纹波、负轨参考地/上电顺序/PCB/验证。
7. **G6（140–180 行，新写）**：隔离判据、成品模块 vs 分立推挽/反激、SN6501+变压器、光耦/TL431/变压器反馈、Y 电容/屏蔽、爬电/间隙/开槽、hipot/绝缘电阻/CMTI；不声称认证。
8. **G7**：负载开关 vs 高边开关 vs eFuse vs 热插拔 vs 理想二极管 vs P-MOS 职责表；`RDS(on)@VGS/温度`、斜率/浪涌、QOD、反向阻断、ON 默认态、SOA/热、关断漏电。
9. **G8**：多轨时序/跟踪/PMIC/sequencer/PG 链、逐轨负载开关/电容、上电浪涌/同时启动、单轨失效/跨轨反灌、电源树到负载引脚。
10. **同步**：`power-ics` §10 未覆盖列表补反相/电荷泵/负载开关/多路时序；`power.md`/`module-cards` 加路由；新增型号来源约 8–12 条。

---

## 8. H 电池、充电与低功耗设备

审计结论：H2/H3/H4/H6/H7 可直接复用；H1（一次电池）、H5（多节电池包）有明显缺口；H8（低电量与维护）需补。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| H1 | 一次电池 | 仅 `F02/S06` 2×AA+LDO 反例、`P01` 2×AA+Boost 淘汰理由、`P14` 纽扣 RTC 提示 | partial | new | Energizer `E91` / `CR2032` / EVE `ER14250` |
| H2 | 单节锂电池充电 | `PWR-06/PWR-07` 整卡、`B3`、`energy-battery`、`P01`、Feather/ESP32 Thing 案例 | adequate | reuse | Microchip `MCP73831` / TI `BQ24074` |
| H3 | 带电源路径管理的充电 | `PWR-07` NVDC、`PWR-06` DPPM/supplement、`PWR-05`、`b1`、`B3` | adequate | reuse | TI `BQ25619` |
| H4 | 电池保护 | `PWR-08` 1S 保护整卡、`energy-battery` §5.4、`B3` 职责表 | adequate | reuse | TI `BQ29700` |
| H5 | 多节电池系统 | 仅串并公式、MNT 8S/LibreSolar 3–16S 案例、`PWR-08` 的“不适用”边界 | partial | new | TI `BQ76952` |
| H6 | 电池与外部供电共存 | `PWR-05` 整卡、`b1` 2^n 组合、`F27/F23/F25`、`P14` | adequate | reuse | TI `TPS2121` |
| H7 | 低功耗外围 | `B2` 整篇、`P01`、`PWR-01/04/14`、`module-integration` C11/C12 | adequate | reuse | TI `TPS22916` / `TPS7A02` |
| H8 | 低电量与维护 | `B3` §2.7/§2.8/§7、`energy-battery`、`P01`、`DM16`、`PWR-08` UVP | partial | supplement | TI `BQ27441-G1` / ADI `MAX17048` |

### H 组本轮必须新写/补充的内容

1. **`PWR-15` 一次电池与电池座（约 260 行）**：一次电池 vs 1S 锂电 vs 超级电容；化学体系（碱性/CR2032/Li-SOCl₂/Li-FeS₂）、标称/截止/容量-倍率/内阻-温度/自放电/保质期、座子接触电阻/防反、**无充电电路**与“不可充电”标识、CR2032 脉冲/2×AA 升压/ER14250 长寿命三个算例。
2. **`PWR-16` 多节电池包与 BMS 概览（约 320 行，2S–16S）**：AFE/monitor + 均衡 + CHG/DSG FET + 分流 + 预充 + 隔离通信；OVP/UVP 叠加、均衡电阻/电流/热、采样线序/断线、FET 并流、分流 Kelvin、4S Li-ion/8S LiFePO₄ 算例；引用 MNT/LibreSolar 但重算。
3. **H 组文件（约 550–650 行）**：H2/H3/H4/H6/H7 各 70–90 行“用户话术+路线表+采购字段+验证操作化”，不重写充电原理；H8 130 行新写阈值/迟滞/告警/有序关机/存储 SOC/维护/SOH/验证矩阵。
4. **H2/H3 补充**：standalone vs I²C/MCU 控制 vs 充电+升压 SoC vs 无 power path；电池包规格书清单；STAT/PG/I²C/看门狗/充电定时器/JEITA/ship mode 固件；电子负载/电池模拟器的 CC/CV/终止/再充/NTC/DPPM 测试设置。
5. **H4 补充**：买成品保护板 vs 自己做 vs 带保护电芯 vs 依赖充电器；“成品保护板验收表”（过流点/内阻/NTC/连接器/恢复/静态电流）；保护 IC 无通信时的检测/恢复/上报。
6. **H8 补充**：`末端电压+峰值压降+保护 UVP+系统 UVLO` 四方协调、告警阈值/迟滞/提前量、关机 hold-up、存储 SOC/温度、SOH、定期校准；`ship mode` 是降低不是归零。
7. **同步**：`PWR-08` 标题改“1S 电池保护（保护 IC + 背靠背 FET）”；`B2` 适用范围收窄或补一次电池降额；修 `p14` 25 mV→25 µV、`f02` Li-FeS₂ 1.8 V、`p01` Vgs(th)、`energy-battery` 线性充电功耗式；来源约 8–12 条。

---

## 9. I 常见主控与最小系统

审计结论：I5 完整；I2/I3/I6/I7/I8 补；I1/I4 空白。现有 MCU 卡只把 STM32F4 类讲透，跨家族/低成本/无线裸片/模拟主控没有入口。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| I1 | 低成本基础控制 | 仅 `MCU-01` F4 类最小系统、Arduino UNO/ATtiny88/EFM8BB21 案例 | missing | new | `CH32V003F4P6` |
| I2 | 通用 MCU | `MCU-01` 整卡 + `MCU-03/04/05/07/08`、`selection` §2 | partial | supplement | `STM32F103C8T6` |
| I3 | 无线 MCU 与模组 | `MCU-02` ESP32-C3、`RF-01/02/03/04`、`D4`、`P01/P04` | partial | supplement | `ESP32-C3-MINI-1` |
| I4 | 模拟能力较强的主控 | 仅 `MCU-01` VDDA/VREF+ 滤波、外部 `ANA-04/05`、`C1` | missing | new | `STM32G431CBU6` |
| I5 | 外部晶体与时钟 | `MCU-05/06` 整卡、`D2`、`x04`、`F05` | adequate | reuse | `ABM8-272-T3` |
| I6 | 外部复位与看门狗 | `MCU-03` 复位监控、`F24`；看门狗仅一句“本卡不展开” | partial | supplement | TI `TPS3823-33` |
| I7 | 下载与自动进入启动模式 | `MCU-07/08/04`、`MCU-02`、`F23/F24/F30`、`P04` | partial | supplement | `CH340C` |
| I8 | 外扩 Flash、EEPROM 与存储卡 | `RF-07/08`、`DM31`、`IF-01/03/04`；EEPROM 仅零散 WP 提示 | partial | supplement | `AT24C256C` |

### I 组本轮必须新写/补充的内容

1. **`MCU-09` 低成本控制（200–220 行）**：8 位 vs 小容量 32 位 vs 硬连线决策树；IO/ADC/定时器资源预算、内部 RC 精度、5 V vs 3.3 V、最小 BOM、单/双面板、下载/量产烧录、开发板 vs 芯片 vs 模组采购。
2. **`MCU-10` 通用 MCU（240–260 行）**：STM32F0/F1/G0/G4/L4/H5、GD32/CH32/AT32 家族矩阵；pinmux/ADC/定时器/DMA/USB/CAN 资源表模板；家族特殊脚/VCAP/BOOT/时钟差异；生命周期/PCN/替代边界。
3. **`MCU-11` 无线 MCU（240–260 行）**：Wi-Fi/BLE/Thread/Sub-GHz/蜂窝路线；模组 vs 裸片；BLE SoC 双晶振/巴伦/DC-DC/RF 前端；链路预算/占空比→平均电流→寿命；天线/认证边界。
4. **`MCU-12` 模拟主控（240–260 行）**：内置 PGA/运放/比较器/DAC/高分辨率 ADC vs 外部 AFE；ENOB/INL/DNL/噪声、PGA 增益误差/漂移、内部 VREF 精度/温漂；模拟分区/guard/校准/直方图/FFT 验证。
5. **`MCU-13` 看门狗（200–220 行）**：内部 IWDG/WWDG vs 外部看门狗；超时/窗口/WDI 脉宽/复位脉宽计算；WDI/RESET 线与、禁用跳线；喂狗序列/复位原因/挂死注入/低温测试。
6. **`MCU-14` 自动下载（220–240 行）**：SWD vs UART ISP vs USB DFU vs 夹具；DTR/RTS 双晶体管/单晶体管/隔离变体、BOOT0 自动控制、时序/电阻计算；生产口/pogo pin/重复下载/读保护救援。
7. **`MCU-15` EEPROM（180–200 行）**：SPI NOR vs QSPI vs EEPROM vs FRAM vs eMMC vs SD；endurance/retention/page/地址脚/WP 极性；擦写寿命/写周期预算/掉电写入；总线引用 `IF-01/03`。
8. **I 组路由文件（约 400 行）**：I1–I8 的用户话术、家族/形态决策树、资源表模板、采购字段；`MCU-01` 保持 F4 深内容不动。
9. **同步**：`design-cards/README.md` 加 MCU-09…MCU-15；`module-cards`/`digital.md`/`selection` 加入口；来源约 8–12 条；`source-register` MCU-S06 列错位修正。

---

## 10. J 数字总线与常见有线通信

审计结论：8 个主题全部 partial——物理层够，外设类别、模块、协议/驱动、采购层缺；J5/J7 还有确定性错误。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| J1 | I²C 外设 | `IF-01/02/12`、`x05`、`F06/F28`、`D1` §2–§7 | partial | supplement | `SHT40` / `AT24C256C` |
| J2 | SPI 外设 | `IF-03/04`、`F29`、`RF-05/07/08` | partial | supplement | `W25Q128JV` / `MCP3008` |
| J3 | UART 与串口模块 | `IF-05`、`MCU-08`、`D3` §3.6、`P04/P02` | partial | supplement | `CH340C` |
| J4 | RS-232 | `IF-06` 整卡、`D3` §3.3、`selection` §3.2 | partial | supplement | `MAX3232` |
| J5 | RS-485 | `IF-07` 整卡、`x06`、`F07`、`D3` §3.2/§6.2、`P02` | partial | supplement | TI `THVD1450` |
| J6 | CAN | `IF-08` 整卡、`x07`、`F08`、`D3` §3.1/§6.1、casebook | partial | supplement | TI `TCAN334` |
| J7 | USB 数据接口 | `IF-09/10`、`PWR-12/13`、`x08`、`F09/F27`、`P04` | partial | supplement | Microchip `USB2514B` |
| J8 | 以太网 | `IF-11` 整卡（仅 DP83822）、`D3` §3.5、`interconnect` §3.6 | partial | supplement | WIZnet `W5500` / `LAN8720A` |

### J 组本轮必须新写/补充的内容

1. **组文件 `j-buses.md` 约 1200–1350 行**：`## 0` 30–40；J1 140–160、J2 130–150、J3 150–170、J4 100–120、J5 150–170、J6 140–160、J7 160–180、J8 150–170；来源 50–60。
2. **J1**：外设类别表（温湿度/EEPROM/IO 扩展/OLED/RTC/ADC/多相同传感器）、地址预算/上电扫描、EEPROM endurance/retention/page/WP、IO 扩展 INT/上电默认、传感器转换时间/CRC、多器件 `Cb` 分配。
3. **J2**：SPI vs I²C vs QSPI/OSPI vs SDIO；Flash/SD/显示/ADC/传感器逐器件支持电路（WP/HOLD/QE、CD/CMD、IM/CS/DC/RST、REFIN/DRDY）、吞吐/DMA/片选译码、驱动初始化/擦写轮询。
4. **J3**：USB-UART 桥（CH340C/CP2102N/FT232RL）的 VIO/DTR/RTS/suspend/ESD、3.3 V LDO、TX/RX 分压、自动下载复位；无线串口/AT 模组的电源/EN/RESET/BOOT、峰值电流/bulk、AT 状态机。
5. **J4**：DB9 针序/DTE-DCE/null modem（列为阻断项，按对端手册核对）、3 线 vs 全握手、隔离 RS-232/隔离电源、系统级 ESD/浪涌、电缆长度 vs 波特率、MAX3243/SP3232E/ADM3251E 替代。
6. **J5**：收发器选型树（5 V/3.3 V、半/全双工、非隔离/隔离、内部 fail-safe vs 外部偏置、1/8 U.L.、限摆率、ESD）、隔离变体、Modbus RTU 驱动/CRC/重试、DE 时序、TVS/PTC/共模扼流协调；**必修 24 V 端接功率错误**。
7. **J6**：高速 CAN vs CAN FD vs 容错 vs 隔离；MCU 内置控制器 vs MCP2515/2518FD；VIO/STB、位定时/晶振 ppm/采样点、环路延时、bus-off 恢复、CANopen；CAN FD 显式标为超出 `IF-08` 范围。
8. **J7**：device/host/OTG/hub、FS vs HS、原生 USB vs 桥片；hub 晶振/复位/strap/端口电源/过流/ESD、Type-C 16/24-pin 映射、SS lane、枚举/描述符、USB-IF 一致性；修正低速上拉语义。
9. **J8**：PHY+MAC vs W5500 MAC+PHY+TCP/IP vs SPI 以太网 vs Wi-Fi；W5500/LAN8720A/KSZ8081 逐脚、RJ45 内置磁性 vs 分立、Bob Smith、PoE 检测/分级/隔离 DC-DC、RMII 时钟 ppm、TCP/IP 协议栈/验证。
10. **同步**：修 `i07` 端接功率、`i09` 低速措辞、`i03` 公式、`d3` 共模、`selection` 32 U.L.、`i10` 5.1 kΩ 指向；来源约 10–16 条。

---

## 11. K 开关、继电器与电机负载

审计结论：K1 强卡；K2/K3/K5/K6/K9 补；K4/K7/K8 空白。K 组最严重的问题是释放时间的线性近似错误，直接影响选型结论。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| K1 | 低侧 MOS 开关 | `DRV-01` 整卡、`selection/semiconductors` §4/§8、`F13/F30`、`E1` | adequate | reuse | Infineon `IRLZ44N` |
| K2 | 高侧开关 | `DRV-02` 整卡、`PWR-09`、`E1` §2.3、`selection/power-ics` §4.2 | partial | supplement | TI `TPS1H100-Q1` |
| K3 | 继电器 | `DRV-03` 整卡、`F14`、`E1` §2.4/§2.8/§5.3 | partial | supplement | Omron `G5LE-1` |
| K4 | 电磁阀与电磁铁 | `DRV-01/02` 算例、`E1` 峰值-保持、`F30` 误吸合；无独立主题 | partial | new | TI `DRV110` |
| K5 | 直流电机 | `DRV-05` 整卡、`DRV-04`、`x11`、`P03`、`F26/F13` | partial | supplement | TI `DRV8871` / `TB6612FNG` |
| K6 | 步进电机 | `DRV-06` 整卡（E2）、`DRV-05`、`DRV-S03` | partial | supplement | `TMC2209` / `DRV8825` |
| K7 | 风扇 | 仅热设计 `thermal/topic` L450、`E3` L113–122、`E1` 感性关断 | missing | new | Delta `AFB0812HH` / Microchip `EMC2301` |
| K8 | 舵机 | 仅 Pixhawk 舵机 5 V 轨案例、`E1` 电机类声明 | missing | new | `MG996R` + Pololu `D24V50F5` |
| K9 | 加热器 | `DRV-08` 整卡、`DM42/DM44`、`E1` 长线尖峰 | partial | supplement | `IRLZ44N` / `TPS1H100-Q1` |

### K 组本轮必须新写/补充的内容

1. **`DRV-09` 电磁阀（约 270 行）**：阀/电磁铁类型、AC vs DC、常开/常闭、两位三通/五通；电压驱动/PWM 保持/峰值-保持/恒流/H 桥双向/自锁；吸合/保持/must-release/ED/行程/压力/介质；DRV110/DRV103 时序、电流采样、阀卡滞检测、温升/寿命验证。
2. **`DRV-10` 风扇（约 250 行）**：2/3/4 线路线；额定/启动/堵转电流、最小启动占空比、25 kHz PWM、tach 每转脉冲/上拉、4 线 PWM 电平/内阻；低侧/高侧开关+续流、tach 分压/ESD、PWM 闭环/温控曲线、堵转/滤网堵塞、拔插/反接验证。
3. **`DRV-11` 舵机（约 250 行）**：模拟/数字、5 V vs 6/7.4/8.4 V HV、标准/微型/大扭矩、连续旋转；堵转电流/多舵机同时峰值、BEC/UBEC/独立电源轨、50 Hz PWM/脉宽、信号电平/串阻/长线、公共地/bulk、堵转检测/失控保护。
4. **K 组路由文件（约 400 行）**：低侧/高侧/继电器/SSR/负载开关决策表、电机类型决策表、跨主题必查、候选短表、常见误判。
5. **K2 补丁（+45 行）**：P-MOS 高侧（栅极上拉/下拉、NPN/N-MOS 移位、VGS 钳位、默认态、导通损耗）、容性负载浪涌 `I=C·dV/dt`、软启动/限流重试。
6. **K3 补丁（+55 行）**：SSR（过零/随机、漏电流、最小负载、通态压降/热、RC 吸收）、锁存/磁保持/簧片继电器、ULN2003/达林顿/BJT 驱动、must-operate/must-release 随温度、触点 RC/TVS/压敏。
7. **K5/K6 补丁**：电机机械量（转矩/转速-转矩/减速比/轮径/丝杆/编码器/轴向力）、PWM 频率/斜坡/制动/堵转检测、模块路线（TB6612/BTS7960/L298N）；步进补转矩-转速/惯量/共振/加减速/失步/归零、A4988/TMC/TB6600/ULN2003 路线。
8. **K9 补丁（+45 行）**：PTC 自调节（居里点/冷态浪涌）、镍铬丝/cartridge、AC SSR/接触器、相角 vs 过零/周波、热熔断器/恒温器、PID/热时间常数/超调、传感器断线/短路注入、AC 漏电/耐压。
9. **同步**：修 D01/D02/D03 释放时间与 `V_clamp` 符号、D08 1 kHz/冷热比；`README`/`SKILL` 计数 60→63、驱动 8→11；来源约 8–12 条。

---

## 12. L 显示、声音、按键与交互

审计结论：L4（SPI TFT）与 L9（Class-D）有强卡；L1/L6 补；L2/L3/L5/L7/L8 空白。HMI 的共性问题是“模块已集成什么”与“面板/开窗/ESD”没有统一判据。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| L1 | LED 指示 | `DRV-07` 恒流卡、`passives` §2.2、`calculate.py led`、`SL02`、`thermal` §3.5 | partial | supplement | 0603/0805 单色 LED（Everlight/Kingbright） |
| L2 | 数码管与矩阵显示 | 仅 Keyboardio 键矩阵（非显示）、`IF-01/03/04`、`SC39` | missing | new | Titan `TM1637` |
| L3 | OLED 与液晶模块 | 仅 `IF-01/02`、`F06/F28`、`module-integration` §10、`DM39` | missing | new | Solomon `SSD1306` |
| L4 | TFT 显示 | `RF-05` 整卡（ST7789V、背光、FPC）、`F15`、`DM39/40`、`P04` | partial | supplement | `ST7789V` |
| L5 | 触摸屏与电容触摸 | 仅 `DM40` 一句、`RF-05` 明确不做触摸、Fomu 触摸焊盘位号 | missing | new | `FT6236G` / `TTP223` |
| L6 | 机械按键 | `MCU-04/02/03`、Keyboardio 键矩阵、`P04`、`SC21/PL07` | partial | supplement | `TS-1088` |
| L7 | 旋钮与电位器 | 仅 `audio-analog-precision` 的 R39 满度余量记录；`ANA-01/04`、`RT22` | missing | new | ALPS `EC11` / `RK09K` |
| L8 | 蜂鸣器 | 仅 `module-cards` L46 一句分类；`DRV-01/03`、`E1` | missing | new | CUI `CEM-1203(42)` |
| L9 | 扬声器与简单音频 | `RF-06` Class-D 整卡、`DM37/38`、Braids/Clouds/Edges 案例 | partial | supplement | Maxim `MAX98357A` |

### L 组本轮必须新写/补充的内容

1. **组文件 `l-hmi.md` 约 700–830 行**：`## 0` 25–35；L1 50–60、L2 90–110、L3 80–100、L4 55–65、L5 85–100、L6 70–85、L7 75–90、L8 70–85、L9 55–70；来源 20–30。
2. **L1**：明确“指示 LED 默认电阻限流，恒流用于大电流/多串/背光”；亮度预算/视角/波长 bin、GPIO 总灌拉电流、PWM 频率/闪烁、共阳共阴、3.3 V 驱动 5 V 灯带、导光柱/开窗、WS2812B 链路末端压降。
3. **L2（90–110 行）**：直驱 → 74HC595 → TM1637/MAX7219/HT16K33 → 智能灯珠矩阵；段/位电流、1/N 占空比、扫描频率/闪烁、消隐防鬼影、位选驱动管、全亮电流预算。
4. **L3（80–100 行）**：OLED vs 字符 LCD vs 段码 LCD；3.3/5 V 模块是否带 LDO、I²C 0x3C/0x3D、电荷泵 C1/C2、RES/DC/CS、SSD1306 vs SH1106 不兼容、上拉归属/长线、低温/烧屏。
5. **L5（85–100 行）**：单键触摸 IC vs 触摸屏控制器 vs MCU CAP；电极尺寸/形状/走线、`C=εA/d`、overlay 厚度/材料、guard/寄生电容、基线校准/漂移/防水、戴手套/湿手/贴膜/装壳验证。
6. **L4/L9 补充**：L4 补选屏与带宽（SPI vs 8080 vs RGB vs MIPI-DSI/LVDS、分辨率×刷新率→带宽、帧缓冲/DMA/LVGL）、大屏多电源域/上电时序、屏模组完整料号/批次；L9 补蜂鸣器→PWM+RC+功放→DAC/I²S→MP3 模块路线、功放 PVCC/增益/最小负载/爆音、扬声器灵敏度/背腔/装壳频响。
7. **L6/L7/L8 新写**：L6 独立 GPIO vs 矩阵 vs ADC 按键、上拉/下拉归属、RC 去抖与 strap 冲突、二极管防鬼键、长按/双击/组合键、湿手/装壳手感；L7 电位器 vs 编码器 vs 数字电位器、三端接法/源阻抗/ADC 采样、taper/角度分辨率、正交解码/加速/掉电保存；L8 有源/无源、压电/电磁、驱动管/续流、谐振频率/占空比、声压/电流/低电压、声孔/声腔。
8. **同步**：`w06` related_checks DM37→DM38；`module-cards` 蜂鸣器移到 §8 并补链接；`w05` “不选屏”与选型表矛盾；`d07` §8 名称；`README` 注明显示/音频卡历史归类；来源 12–18 条。

---

## 13. M 无线、时间与常用功能模块

审计结论：M1/M2/M4/M5/M8 补；M3（Sub-GHz）/M7（NFC/RFID）空白；M6（RTC）只有能量/晶体，没有芯片级卡。

| ID | 主题 | 现有内容 | 判定 | 动作 | 首选型号 |
|---|---|---|---|---|---|
| M1 | Wi-Fi | `RF-01/02`、`D4`、`F18/F25/F03/F32`、`x12`、`P01/P04` | partial | supplement | `ESP32-C3-MINI-1` |
| M2 | BLE | 共享 `RF-01` 模组硬件、`P01` BLE 项目、`RF-02` 天线、32.768 kHz 晶体 | partial | supplement | Nordic `nRF52840` |
| M3 | Sub-GHz | 仅 `D4` L705 与 `F18` L82 的“另查”边界；无电路/选型/参数 | missing | new | Semtech `SX1268` |
| M4 | 蜂窝 | `RF-03` 仅 EG915N 2G 突发供电；无 LTE/NB-IoT/SIM/认证 | partial | supplement | Quectel `EG915N` / `EC200U-CN` |
| M5 | GNSS | `RF-04` 天线/NF/屏蔽/keep-out；无模组选型/接口/PPS/备份 | partial | supplement | u-blox `MAX-M10S` |
| M6 | RTC | `PWR-14` 备份能量、`MCU-05/D2` 32.768 kHz 晶体、`MCU-01` VBAT | partial | new | Maxim `DS3231SN` / `RV-3028-C7` |
| M7 | 身份与标签读取 | 全库无 NFC/RFID/条码内容；仅 I²C/SPI、天线匹配思路可借 | missing | new | NXP `PN5321A3HN` |
| M8 | 隔离与数字隔离器 | `SC38/RT10`、`DM45/46`、`I07/I08` 隔离收发器边界；无隔离器选型 | partial | new | TI `ISO7721DR` |

### M 组本轮必须新写/补充的内容

1. **M 组路由文件（约 350 行）**：M1–M8 用户话术/路线树、跨主题“无线+时间+隔离”参数/采购/认证总表、验证与常见误判总表。
2. **M1/M2**：补 Wi-Fi vs BLE vs Sub-GHz vs 有线、2.4/5 GHz、Wi-Fi 4/5/6、模组 vs 裸芯片；BLE 4.2–5.4（2M/Coded/AoA/AoD/Isochronous）、GATT/广播/连接参数/配对/DFU、BLE 占空比→平均电流→纽扣电池寿命算例、DTM/PER/RSSI 测试。
3. **M3（180–220 行，新写）**：433/470/868/915 法规与频段、LoRa vs FSK/OOK、SX1268/SX1262/CC1101/CMT2300A、链路预算/Friis、晶体 ppm/频偏、PA/T/R 开关/匹配、扩频因子/带宽/编码率/CAD、占空比/杂散、传导功率/灵敏度/PER vs 距离。
4. **M4**：补 2G vs LTE Cat 1/1bis/Cat M/NB-IoT、地区频段/运营商/退网、LTE-only 峰值/平均电流、PSM/eDRX、SIM/eSIM（MFF2）/ESD/检测、USB/UART/PCIe、AT/PDP/APN/MQTT、CE/FCC/SRRC/PTCRB。
5. **M5**：补模组选型（通道/更新率/TTFF/功耗/备份/PPS/接口）、UART/I²C/SPI/PPS/复位/备份电池、NMEA/UBX/AGPS、冷/温/热启动 TTFF、定位精度/PPS 抖动/共存/装壳 C/N0。
6. **M6（160–200 行，新写）**：MCU 内部 RTC vs 外部 RTC 芯片 vs GNSS/NTP；DS3231/PCF8563/RV-3028/MCP7940N；ppm→每天/每年秒差、温度补偿、备份电池/超级电容/ORing、RTC 晶体 guard/keepout、BCD/Unix/闰年/闹钟/校准、频率计/日差/温度循环/备份切换验证。
7. **M7（180–220 行，新写）**：13.56 MHz NFC vs 125 kHz LF vs UHF RFID vs 条码/二维码/磁条；PN532/MFRC522/ST25R3916/FM17550；线圈电感/电容/Q/谐振、场强/读距、EMC 滤波/匹配、ISO14443A/B/15693/NDEF/防冲突、金属环境/装壳读距、MIFARE Classic 安全边界。
8. **M8（180–220 行，新写）**：数字隔离器 vs 光耦 vs 电容/磁耦 vs 隔离收发器/隔离放大；Vrms/Vpeak/工作电压/瞬态/CMTI/传播延迟/脉宽失真/默认态/通道方向；隔离 DC-DC（SN6505+变压器/B0505S/ADuM5000）、两侧去耦/ESD、爬电/间隙/开槽、hipot/绝缘电阻/CMTI 验证；不声称认证。
9. **同步**：修 `p14` 25 mV→25 µV；`35+j0` 全部改为“按模组/芯片要求，疑似 S11≤−35 dB，待回读原页”；EG915N 2G 数据标“仅该型号 2G 条件”；`module-cards` L33 笔误；I07/I08/I05/I12/A07/A08/D03 加“见 IF-14”反链；来源 12–18 条。

---

## 14. 可复用内容地图

原则：**已有设计卡承担“电气理论与算例”，common-hardware 只承担“用户话术、路线选择、跨主题组合、采购与验证操作化”**。下表左列是复用源，右列是禁止重复写的内容。

| 复用源 | 能覆盖什么 | 被哪些组引用 | 复用边界（不要重复写） |
|---|---|---|---|
| `ANA-01/02/03/04/05` + `calculations/analog-adc.md` | 分压、缓冲、差放、ADC 驱动、基准、误差预算 | A1/A3、B1/B2、C1/C4、D1/D2、E1/E2/E3/E7、I4、L7 | 分压比/源阻抗/采集时间/基准六项误差公式 |
| `ANA-09` | 桥式传感器、四/六线、比率测量、INA/CMRR | D1/D2、E2、K9 | 桥式前端公式与误差预算 |
| `ANA-10` | RTD/NTC 的激励、自热、2/3/4 线、误差链 | A1/A3、D1、K9、M6 | RTD 拓扑与自热方法；NTC/RTD 专项补丁除外 |
| `C1` (`c1-sensor-to-adc-error-chain`) | 传感器→ADC 全链误差分类/合成/校准边界 | A/B/C/D/E/I | 误差链方法；不替代各传感器物理/气路/校准 |
| `IF-01`–`IF-12` + `x05` | I²C/SPI/UART/RS-232/RS-485/CAN/USB/以太网/电平 | A2/A5、C1–C7、D3、J1–J8、L3、M6/M7 | 总线电气/时序/上拉/端接/电平公式 |
| `PWR-05/09/10/11` + `b1` + `module-integration` §8 | 多源/ORing/反接/热插拔/eFuse/反灌/上电状态 | F/H/G/J7/K/L | 2^n 组合、RPP vs RCB、保护配合顺序 |
| `SC38`/`RT10`/`C2`/`DM45–46` | 隔离边界、爬电/间隙、屏障检查 | E5、G6、J5/J6、M8 | 隔离是整块边界；不给统一毫米值 |
| `thermal/topic.md` + `thermal/cases.md` + `power-thermal` | 热阻/结温/铜面积/热瞬态/LED/功放热 | E/G/H/K/L9 | θJA、热路径、降额公式 |
| `DRV-01`–`DRV-08` + `x11` + `P03` | 低侧/高侧/继电器/H 桥/步进/加热器功率级 | K1–K9、C5/C6、L8、B3 | 功率级拓扑、钳位、SOA、栅驱 |
| `RF-01`–`RF-08` + `D4` + `x12` + `F18/F25/F32` | Wi-Fi/BLE/蜂窝/GNSS/天线/整机 RF/认证边界 | I3、M1–M5、B8 | 模组供电/EN/strap/净空/装壳失谐 |
| `MCU-01`–`MCU-08` + `F03/F04/F23/F24` | 最小系统、复位、strap、晶体、SWD/ISP | I1–I8、J3、L6、M6 | F4 类 VCAP/BOOT/时钟数值；跨家族差异另写 |
| `DM24`/`PL24`/`PL25`/`G08`/`enclosure`/`MF14/16` | 传感器布置、气路、光窗、机械应力、涂覆/清洗 | A/B/C/D/K/L | 通用布置判据；各传感器滤膜/导压管/加热器另写 |
| `selection/*` + `lcsc-sourcing` + `replacement-classes` + `source-register` | 选型字段、替代分级、来源登记、C 号纪律 | 全部 | 采购流程；不写库存/价格/C 号 |
| `simulation-measurement` + `C4` + `SC/PL/RT` 检查 | 测量不确定度、差分探头、假通过、PCB/原理图检查 | 全部 | 测量方法与检查 ID；不重复条文 |

**可直接引用、只需 5–20 行外层内容的 15 个 adequate 主题**：E1、E2、F2、F5、F6、G1、G2、G3、H2、H3、H4、H6、H7、I5、K1。写作时只补“用户怎么说/怎么选/采购字段/验证操作化”，不得复制已有算例。

**可大量复用但需补本主题增量的 60 个 partial 主题**：按各组表的 `supplement`/`reuse` 动作执行；增量集中在“路线表、必查参数、程序、采购”四块。

---

## 15. 旧内容修正

写作前必须先修下表；新内容不得复制旧值。编号 `Cxx` 仅用于本文件追踪。

### 15.1 确定性数值/逻辑错误（先修）

| 编号 | 位置 | 问题 | 修正 | 审计 |
|---|---|---|---|---|
| C01 | `ANA-10` L39/L142–186 | Pt100“−200…850°C、20–400Ω”是设计包络，不是 IEC 60751 表值；400Ω 约对应 880°C；400Ω 点用 0.362Ω/°C 而非局部 0.29Ω/°C，温度误差低估约 25% | 改为“设计包络”，误差按局部 `dR/dT` 折算，或注明 0.362 是全量程平均 | A |
| C02 | `ANA-07` §5 L144–149 | `100 µV / 1 mΩ = 100 mA`，卡写 10 mA；RSS/最坏与“CMRR 主导”结论被低估 | 按同一假设重算：RSS 约 158.5 mA/1.59%，最坏 315.5 mA/3.16%；0.5 A 时失调主导 | E |
| C03 | `ANA-06` §3/§4 L86–88、L114 | 同相增益 `1+R_F/R_G` 与地差项 `V_GND_OS×(R_F/R_G)` 混用；`V_GND_OS×(G−1)` 与两种接法都不一致 | 明确同相 vs 差放拓扑，统一定义，重写 §4 步骤 6/§5 第 6 项与 R_G 落点 | E |
| C04 | `ANA-01` L181、`analog-adc` L209/L245–247 | 0–10 V/30 kΩ/10 kΩ 节点阶跃是 2.5 V，但 1085.50 LSB 按 3.3 V 阶跃算；10 µs 残差约 822 LSB，被高估约 32% | 明确“工具按 3.3 V 阶跃，需乘 2.5/3.3”，或给 `adc_settle` 加 `vin_step_V` 重跑 | E |
| C05 | `ANA-09` L151 | 淘汰 INA 增益 200 的理由写成“5 V 供电摆幅接近轨”，但 2 V 输出并不接近轨；增益不改变输入共模 | 改为零点/失调余量、噪声、CMRR、后级摆幅不足 | D |
| C06 | `ANA-09` L130 | “24 bit ADC 直接采，Code≈33,554 也可行”过于乐观；33,554 码仅约 15 bit，未计 ENOB/噪声/陷波/桥自热 | 加条件：ENOB、噪声、漂移、50/60 Hz 陷波满足预算时才可行 | D |
| C07 | `ANA-08` L96 | RCV420 输出“对地 10…5 V”与 0–5 V ADC 并列，易读成可直连 | 明确需电平移位/差分接收，不能直接进 0–5 V ADC | D/E |
| C08 | `IF-07` L208–212、L231 | 24 V 加在 A/B 两端时，两端 120 Ω 端接是并联，不是串联；每只约 4.8 W、合计 9.6 W，卡写 1.2 W/只、2.4 W 合计 | 拆三种故障模型：(a) 两端端接并联 4.8 W/只、9.6 W；(b) 单只 4.8 W；(c) 回路断开串联 1.2 W/只；按 (a) 选功率 | J |
| C09 | `IF-09` L98/L234 | “低全速设备在 D− 上接 1.5 kΩ”应为“低速（Low-Speed）设备”；L234 表述会让低速设备画错 | 改为“全速设备 D+；低速设备 D−；全速/高速能力设备不得在 D− 放 1.5 kΩ” | J |
| C10 | `IF-03` L110/L128/L146/L158 | §4 时序预算/串阻上限只剩文字判据，公式被删；§5 算例缺完整代入 | 恢复读方向 `T/2 ≥ tCLK_fwd + tCO(max) + tMISO_ret + tSU + jitter`、写方向偏斜、`tH` 用 `tCO(min)`、`1.2·Rs·C_L ≤ 余量` | J |
| C11 | `d3-off-board-interfaces` L129 vs L527/L618 | L129 把地差直接当共模并扣规范负端，与后文“地差不是共模”矛盾 | L129 改为“仅数量级对比；按 §6.2 发送共模+地差包络计算”，删除“还剩 5 V” | J |
| C12 | `DRV-01` L155 | 仅续流二极管释放时间用 `L·ΔI/V` 线性近似；`I·R=26.4 V` 远大于 0.7 V，126 ms 错误，RL 解约 12.2 ms | 改 RL 解 `i(t)=(I0+VF/R)e^(−t/τ)−VF/R`，用 must-release 电流判释放 | K |
| C13 | `DRV-03` L143/L165 | 仅二极管 21.4 ms 错误；`R=400Ω`、`I=30mA`、`τ=1.25ms`，到零约 3.6 ms；“仅二极管不满足 5 ms，淘汰”不成立 | 按 RL 解与 must-release 重算，再决定是否淘汰 | K |
| C14 | `DRV-01` L156、`DRV-03` L147 | 二极管+稳压管释放时间同样用线性式；D01 约 2.42 ms（卡写 3.56）、D03 约 0.50 ms（卡写 0.607） | 改 RL 解，保留结论方向但更新数值 | K |
| C15 | `DRV-02` L163 | `L×I/V≈1.25 ms` 忽略 `I·R=30 V`；RL 解约 0.93 ms | 改 RL 解；钳位能量/热结论不受影响 | K |
| C16 | `DRV-01`/`DRV-03` | `V_clamp` 在 D01 是“漏极对地最高电压”（含 `V_load`），D03 是“线圈两端反压”（不含 `V_coil`），跨卡混用会算两次 | 统一 `V_reverse`（线圈反压）与 `V_DS_peak`（漏极对地），公式旁注明 | K |
| C17 | `DRV-03` L115 | `V_DS ≥ V_coil(max) + V_clamp` 与同段“仅二极管约 V_coil + V_F”并列，`V_clamp` 可能已含 `V_coil` | 改为 `V_DS ≥ V_coil(max) + V_reverse` 并定义 `V_reverse` | K |
| C18 | `DRV-08` L115 vs §5 | “频率高于可听声（避免啸叫）”与 1 kHz 算例矛盾 | 统一为“>20 kHz 或接受 1 kHz 可听噪声”，算例频率与结论对齐 | K |
| C19 | `DRV-08` L139/L173 | 冷/热比 0.9、浪涌 1.11 倍只适用于冷热变化小的加热片；镍铬丝/PTC 冷态电流可能大得多 | 加“不适用于镍铬丝/PTC”限定，PTC 另按居里点/自限温曲线 | K |
| C20 | `PWR-14` L159 | “2.5 µA 在 10 s 内只掉 25 mV”；同文件 L136 正确计算是 `25 µC/1 F=25 µV`，放大 1000 倍 | 改为 25 µV | H/M |
| C21 | `F02` L95 | “锂铁 AA 单节约 1.8 V”；Li-FeS₂ 标称 1.5 V，1.8 V 是新电池 OCV | 改为“标称 1.5 V，新电池 OCV 约 1.8 V，按放电曲线重算” | H |
| C22 | `P01` L87 | Q1 用 `Vgs(th)` 当“可靠导通”判据，与 `power.md:22` 冲突 | 改为“`Rds(on)` 在 `Vgs=3.0 V` 有保证值，`Vgs(th)(max)` 远低于 3.0 V；不能用 Vgs(th) 证明导通” | H |
| C23 | `DM13` L28、`PWR-08` L48 | 把一次电池与可充体系并列谈“充电截止/充电参数”，有安全风险 | 改为“一次电池不可充电，不能套用锂离子/磷酸铁锂充电参数；只核对放电截止/温度/运输” | H |
| C24 | `W06` L8 | `related_checks` 写 `DM37`，Class-D 对应 `DM38` | 改为 `[SC39, PL16, RT22, DM38]` | L |
| C25 | `PWR-01` L262 | “反向电流 ≤5% 额定”写成通用对策；5% 是 TPS7A02 的限值 | 改为“按所选器件手册；TPS7A02 为 5% 且只允许短时间” | G |
| C26 | `PWR-01` L197/L292 | 称 TPS7A02 的 `TJ(max)`“未读到”；SBVS277C p.5 明确 −40…125°C | 补读并写明“125°C 是器件上限，110°C 是算例设计目标” | G |
| C27 | `PWR-01` §4 第 2 步 L107–111 | VDO 定义未写“VOUT 降到 95% 标称”的测试判据 | 补 SBVS277C p.7 注 4 的条件 | G |
| C28 | `PWR-03` §1 第 6 条 L43 | 写“电感+二极管直流通路”，同步 Boost 路径是高侧 FET 体二极管 | 改为“整流路径（二极管或高侧体二极管）”，保留同步/非同步区别 | G |
| C29 | `energy-battery` L106 | 线性充电功耗先写 `(Vin−Vbat)·Ichg + Vin·Iq`，下一句才提有 power path 要加系统电流 | 直接写成 `(Vin−Vbat)·Ichg + (Vin−Vout)·Isys + Vin·Iq` | H |
| C30 | `PWR-14` L136 | 均衡电阻 1 MΩ、两颗串联、2.5 µA 的接法未写清；若每颗并 1 MΩ 或单只跨组，总漏电是 5 µA | 按 PWR-S14 §2.4.1 实际接法写明，重算保持时间 | H |

### 15.2 过时结论/单型号外推/边界收窄

| 编号 | 位置 | 问题 | 修正 | 审计 |
|---|---|---|---|---|
| C31 | `selection/modules-connectors` L193 | 以 `BME280 温湿度气压` 作唯一传感器检索示例，属较老一代 | 补 SHT4x/BMP390/BME688 新旧对照，提示核对生命周期 | A |
| C32 | `selection/modules-connectors` L162 | 一行“磁/光/proximity”把环境光、反射、对射/槽型、磁接近混在一起 | 拆成环境光、反射式、对射/槽型、磁开关/线性霍尔、磁力计四/五行 | B/C |
| C33 | `DM24` L45 | 把温湿度/气压/气体/光学/惯性合并为“按物理测量条件布置”；IMU 不需要气路/窗口 | 拆环境传感器 vs 惯性/运动传感器；光学窗口/遮光/PIR 透镜/ToF 盖板单列 | A/B/C |
| C34 | `PL24` L36 | 只写气孔/气流/热/凝露，未覆盖光窗、遮光墙、发射-接收串扰、盖板间距、菲涅尔 | 拆“温湿压/气体”与“光学/热释电”两条；PL25 扩敏感轴/安装基准/旋转中心 | B/C |
| C35 | `PWR-06`/`PWR-07` | 4.16/4.20/4.23 V、2.2 µH/1.0 µH、VSYS 3.5 V、IINDPM 100 mA–3.2 A 都是具体型号条件 | 引用时保留型号条件，不能写成通用充电器值 | H |
| C36 | `BQ27441` | 10 mΩ/±25 mV/2.5 A 是 BQ27441 条件；5 A 负载必须换小分流或多串 monitor | 每次引用写条件；不套到所有 gauge | E/H |
| C37 | `DP83822` | `RBIAS=4.87 kΩ`、中心抽头 3.15–3.45 V、strap 2.2 kΩ 只适用该型号；selection L103 仍写成通用 PHY 条件 | selection 行加“DP83822 实例，换 PHY 必须重查” | J |
| C38 | `TPS7A02` | 270 mV、0.5–22 µF、5% 反向电流只属该型号 | 不得套到其他 LDO；G1 补 PSRR/噪声时另选型号核对 | G |
| C39 | `EG915N` | 2G 突发 2.0/2.5 A 被当蜂窝默认量级；2026 年 LTE-only/NB-IoT 不能套 | 标“仅 EG915N 2G 条件”，补 LTE-only 峰值/平均电流与退网提示 | M |
| C40 | `W02`/`D4`/`simulation-measurement` | “35+j0”S11 目标重复传播，来源笔记定义不完整，疑似应为 S11≤−35 dB | 回读 Espressif RF Tuning 原页；未确认前统一写“按模组/芯片要求” | M |
| C41 | `PWR-08` 标题 | 标题“1S 电池保护与 BMS”，正文只覆盖 1S 保护 IC，明确排除多串/均衡/电量计 | 改名“1S 电池保护（保护 IC + 背靠背 FET）”或加范围声明 | H |
| C42 | `B2` L26 | 声称适用于 AA/纽扣，但容量/截止/内阻示例全是 1S 锂电 | 补一次电池容量降额/峰值能力，或收窄适用范围 | H |
| C43 | `G08` | Bosch BME280 专用安装/清洗指南，被 `modules-connectors` L167 引用时未带边界 | 各环境传感器按各自原厂 handling 指南核对，不能强套 | A |
| C44 | `casebook/motor-power-industrial` L157/L173 | 气压计下方挖地原因作者未说明，原文已写“不能当定论” | 新 A6 不得升级为“气压计必须挖地”规则 | A |
| C45 | `P06` L153 | “按 Vishay Type 2 曲线选型（具体型号待查）”无 MPN | A1 补完后回填候选，注明 B 值/曲线不同不能直接替换 | A |
| C46 | `P01` L87 | RH ±2%、T ±0.3°C 是需求门槛，不是器件保证；未写量程/温度条件 | 拆成 20–80%RH/全温区/迟滞/长期漂移四项再核对 | A |
| C47 | `MIFARE Classic` | 加密已公开破解，不能当身份级安全方案 | 新 M7 明确只做低安全门禁/消费；身份级用 NTAG/ISO14443A-3/4/DESFire + 密钥体系 | M |

### 15.3 悬空/错向引用

| 编号 | 位置 | 问题 | 修正 | 审计 |
|---|---|---|---|---|
| C48 | `A02:55`、`A03:52` | 引用“隔离卡”，60 张卡库中不存在；`A06` 也无隔离内容 | 改指 E5 或新建 IF-14；不留悬空链接 | E |
| C49 | `ANA-01` L49 | 把隔离电压采样推给 `DM21/SC38`，DM21 是传感器误差链检查项，不是隔离入口 | 改为“SC38 + E5”，或明确“本卡不覆盖隔离” | E |
| C50 | `b1` L28、`PWR-05` L50 | 把 USB PD 指向 `PWR-12/PWR-13`，两卡都明确只做 5 V | 改为“PD 见 F3（待新写）/暂无现有卡” | F |
| C51 | `C3` L44/§2.5 | 把光电二极管归入“源阻抗>100 kΩ 查 Ib/Ios”的电压源判据；TIA 反相输入是虚地 | 加“跨阻接法不适用本条”，B2 单独写 `Ib×Rf`/`Cd-Cf` 稳定性 | B |
| C52 | `DM22` L43 | 把“热电偶”和“自热”并列，易让读者以为热电偶按 RTD 自热核算 | 改为“冷端/引线（热电偶）、自热（RTD/NTC）” | A |
| C53 | `x05` 标题 | 标题“I²C 温湿度传感器接口”，正文只有总线，无温湿度测量 | 改题“I²C 传感器接口（以温湿度为例）”或开头加边界 | A |
| C54 | `thermal/topic` §8.1 | 36–40 AWG 细线是“用热电偶测壳温”的方法，不是热电偶前端设计；补偿导线必须同合金 | 新 A4 与此节互链并注明边界 | A |
| C55 | `module-integration` L276、`energy-battery` L109 | “USB 输入电容<10 µF”被写成通用 USB 条件；这是 BQ2407x/USB 2.0 条件，Type-C VBUS 限值未读 | 加“BQ2407x/USB 2.0 条件；Type-C 另查” | F |
| C56 | `P12` L39 | 0.9 A 与 Type-C 0.5/1.5/3 A 档并列；0.9 A 是 USB 3.x 端口电流，不经 CC 广告 | 改为“USB2.0 500 mA / USB3.x 900 mA / Type-C 1.5/3 A”并注明 | F |
| C57 | `F09` L67/L83/L87 vs `P12` L88/L241 | 两套 CC 窗口（PWR-S16 Table 7 旧值 vs R2.5 Table 4-36 新值） | f09 加“两套窗口/按声明规范版本”，或同步 R2.5 并保留旧值对照 | F |
| C58 | `selection` L88 | “RS-485 最多 32 单位负载”易读成“最多 32 个节点” | 改“32 U.L. 是单位负载预算，不是节点数；1/8、1/4 U.L. 可更多” | J |
| C59 | `IF-10` L54 | 写“具体 Rp/Rd 本卡不写”，但 `x08`/`PWR-12` 已给 5.1 kΩ 等 | 加一句指向 `PWR-12/x08`（ST AN5225/TUSB320），并注明使用前按规范图表核对 | J |
| C60 | `IF-08` L182/L221 | “100 m/500 kbit/s 往返占 82.5%、建议 250 kbit/s”是特定最坏假设，不是通用降速规则 | 保留条件；实际收发器/控制器延时更优时用实际值重算 | J |
| C61 | `IF-06` L20/L282、`D3` L313 | DB9 针序、系统级 IEC 61000-4-2、隔离 RS-232 未核对 | 新增 J4 把针序列为阻断项，按对端手册/连接器图纸核对，不写“常见 DB9 2/3/5” | J |
| C62 | `IF-11` L22/L57/L222 | 单型号 DP83822 的 `RBIAS`/中心抽头值有边界声明，但 selection 仍写成通用 | selection 加“DP83822 实例，换 PHY 重查” | J |
| C63 | `W05` L41 vs L133 | “它不选屏”与选型表“屏/控制器：接口模式、时序…”自相矛盾 | L41 改“选屏判据见 L4，本卡只处理接口与背光” | L |
| C64 | `D07` L47 | 把 §8 称“显示/背光”，实际 §8 名为“显示、音频与人机” | 改为“§7 功率负载、§8 显示与人机” | L |
| C65 | `module-cards` L46/L50/L53 | 蜂鸣器分类句在 §7（功率负载），§8 才是 HMI；“深入”只链 RF-05/06，读者以为按键/LED/Codec 已有卡 | 蜂鸣器移到 §8；L1/L6/L9 新增后补链接或改“构成”措辞 | L |
| C66 | `DM37`/`DM38` L70/L71 | 两条都写“BTL 两端都是输出，不能把任一端当普通地” | 只保留在 DM38，DM37 改为指向 DM38 | L |
| C67 | `README` L93 | 显示/音频卡（RF-05/06）实际在 `wireless/` 目录，与 HMI 语义不符 | 分组标题下注明“显示/音频卡位于 wireless/ 是历史归类” | L |
| C68 | `source-register` PWR-S11/S13/S14 L84/86/87 | 第 7 列“不能推广”重复第 5 列/第 6 列，或误放公式 | 恢复各行“不能推广”内容；公式移到正文/支持内容 | F/G |
| C69 | `source-register` MCU-S06 L70 | 列错位，“不能推广”重复“支持内容”，限制丢失 | 改为“3.17 V/4%/6 mV 是 TPS389033/TPS3808 示例；§7–§9 看门狗只读目录级” | I |
| C70 | `MCU-07` L97/L130 | STDC14 脚表不完整：缺 pin1/2 Reserved、pin13/14 `T_VCP_RX/TX`，却推荐 STDC14 用于 VCP | 补全或注明“本表只列 SWD/JTAG，VCP 见 UM2448 Table 6” | I |
| C71 | `MCU-03` L124 | “TPS3808 内部感应迟滞仅 6 mV”缺具体变体/条件 | 改为“TPS3808G01（SLVAE47A §15 示例）6 mV；其它变体查手册” | I |
| C72 | `module-cards` L33 | “不固定某个模组的峰值电容”疑为“峰值电流/电容”笔误 | 改为“峰值电流/电容值” | M |

### 15.4 索引/计数/路由/测试契约同步（结构性）

| 编号 | 位置 | 问题 | 修正 |
|---|---|---|---|
| C73 | `design-cards/README.md`、`SKILL.md`、`docs/expansion-report.md`、`design-experience.md` | 现有计数 60 张卡、E1 42/E2 18、12 范例、4 项目、33 故障、35 场景、190 检查；新增卡后全部失效 | 按最终新增卡数统一重算；不允许多处不一致 |
| C74 | `SKILL.md` 按需读取表 | 没有运动/位置/转速、环境气体、光学/测距、HMI、电池一次/多节、隔离等入口 | 13 组各加一行路由；组内再按主题路由 |
| C75 | `module-cards.md` | §2/§5/§8/§10 的“深入”链接只覆盖旧卡，新增组/卡未链 | 逐节补链接；避免“构成”列了但“深入”没有 |
| C76 | `task-scenarios.md` / `assets/scenarios.json` | 缺运动、称重、压力、液位、流量、光学、HMI、Sub-GHz、NFC、一次电池、低电量等场景 | 每组补 1–3 个场景/反例；不追求数量，覆盖用户话术 |
| C77 | `examples/README.md`、`projects/README.md` | 新增范例/项目后计数与索引未同步 | 若本轮新增 x13–x15 等，统一更新计数 |
| C78 | `tests/test_common_hardware.py` | 13 组契约、`## 0. 本组怎么用`、12 个三级标题、`## 本组来源`、证据标签、相对链接、无未标注 C 号 | 新增/改名文件必须进 13 组清单；写作前先跑机械检查 |

---

## 16. 建议文件结构

### 16.1 架构决策（审计建议；本轮实际采用 13 组文件 + 12 个组合应用，见文首说明）

不采用“每主题一个文件”，也不采用“一个巨型文件”，而是三层：

1. **`common-hardware/<group>.md`（13 个）**：承载用户话术、路线选择、跨主题判据、每组来源与修正清单；每个主题一个 `##` 节，节内固定 12 个三级标题。复用型主题 40–60 行，补充型 60–90 行，新写型 90–130 行。
2. **提升卡（28 张）**：只给“深度大、跨组复用、必须逐脚/算例”的主题；完整 12 节，放在现有 `design-cards/` 分类下。组文件对应节压到 40–60 行，只留路由与增量，正文链接到卡。
3. **`combinations.md`（1 个）**：跨 3–5 组的组合应用；不放进任何单组文件。

### 16.2 `common-hardware/` 文件清单与篇幅

| 文件 | 承载 | 组文件行数 | 配套提升卡/补丁 | 说明 |
|---|---|---:|---|---|
| `README.md` | 13 组路由、102 主题索引、证据等级说明、写作/验收规则 | 120–150 | — | 只做导航，不写技术结论 |
| `a-environment.md` | A1–A7 | 约 420 | `SEN-01`–`SEN-05`（约 1080 行）+ `ANA-10` 补丁（约 140 行） | A1/A3 留在 `ANA-10`，不拆 NTC/RTD |
| `b-optics.md` | B1–B8 | 800–950 | — | 单文件；B1/B2 复用 ANA/C3，B3–B8 新写 |
| `c-motion.md` | C1–C7 | 800–900 | — | 单文件；C2/C4/C6/C7 引用现有卡 |
| `d-force.md` | D1–D7 | 约 430 | `SEN-06`–`SEN-12`（约 1520 行） | D1/D7 是补充卡，D2–D6 新卡 |
| `e-measurement.md` | E1–E7 | 约 695 | 修 `ANA-06/07/01` | E1/E2 只引用；E4/E5/E7 新写 |
| `f-low-voltage-power-input.md` | F1–F8 | 760–840 | — | F3 新写；F2/F5/F6 只引用 |
| `g-converters.md` | G1–G8 | 950–1150 | — | G5/G6 新写；G1–G4 引用 PWR |
| `h-battery.md` | H1–H8 | 550–650 | `PWR-15`、`PWR-16`（约 580 行） | H2/H3/H4/H6/H7 引用；H1/H5 新卡；H8 补 |
| `i-mcu.md` | I1–I8 | 约 400 | `MCU-09`–`MCU-15`（约 1590 行） | I5 引用；I1/I4 新卡；I2/I3/I6/I7/I8 补 |
| `j-buses.md` | J1–J8 | 1200–1350 | — | 单文件；8 节均“物理层引用+外设/协议增量” |
| `k-drive.md` | K1–K9 | 约 400 | `DRV-09`–`DRV-11`（约 770 行）+ 6 张补丁（约 267 行） | K1 引用；K4/K7/K8 新卡；其余补 |
| `l-hmi.md` | L1–L9 | 700–830 | — | L4/L9 引用；L2/L3/L5/L7/L8 新写 |
| `m-wireless-time.md` | M1–M8 | 约 350 | `RF-09`、`MCU-16`、`IF-13`、`IF-14`（约 780 行） | M1/M2/M4/M5 引用；M3/M6/M7/M8 新卡 |
| `combinations.md` | 跨组组合应用 | 250–350 | — | 8–10 个端到端配方 |

组文件合计约 **8860 行**；提升卡约 **6320 行**；加 `README.md` 与 `combinations.md` 约 **1.56 万行**。这是首轮完成 102 个主题的规划上限；实际写作按“能复算、能检查、能采购”裁剪，不追求行数。

### 16.3 提升卡命名与落点（解决审计间 ID 冲突）

审计中 A 的 `SEN-01..05`、D 的 `s01..s07`、I 的 `m09..m15`、M 的 `m09-rtc` 存在重名/目录冲突。统一如下：

| 目录 | 卡 | 主题 |
|---|---|---|
| `design-cards/sensing/` | `SEN-01` 数字温度 | A2 |
|  | `SEN-02` 热电偶 | A4 |
|  | `SEN-03` 温湿度 | A5 |
|  | `SEN-04` 气压/高度 | A6 |
|  | `SEN-05` 气体/空气质量 | A7 |
|  | `SEN-06` 称重产品化 | D1 |
|  | `SEN-07` 模拟压力 | D2 |
|  | `SEN-08` 数字压力 | D3 |
|  | `SEN-09` 液位 | D4 |
|  | `SEN-10` 土壤/介质湿度 | D5 |
|  | `SEN-11` 脉冲流量 | D6 |
|  | `SEN-12` 模拟过程量接口 | D7 |
| `design-cards/power/` | `PWR-15` 一次电池与电池座 | H1 |
|  | `PWR-16` 多节电池包与 BMS 概览 | H5 |
| `design-cards/mcu/` | `MCU-09` 低成本控制 | I1 |
|  | `MCU-10` 通用 MCU | I2 |
|  | `MCU-11` 无线 MCU | I3 |
|  | `MCU-12` 模拟主控 | I4 |
|  | `MCU-13` 看门狗 | I6 |
|  | `MCU-14` 自动下载 | I7 |
|  | `MCU-15` EEPROM | I8 |
|  | `MCU-16` RTC | M6 |
| `design-cards/drive/` | `DRV-09` 电磁阀 | K4 |
|  | `DRV-10` 风扇 | K7 |
|  | `DRV-11` 舵机 | K8 |
| `design-cards/wireless/` | `RF-09` Sub-GHz | M3 |
| `design-cards/interfaces/` | `IF-13` NFC/RFID | M7 |
|  | `IF-14` 数字隔离器 | M8 |

### 16.4 组合应用放在哪里

放 `common-hardware/combinations.md`，不放进任何组文件。理由：组合应用跨 3–5 组，放进单组会造成重复与路由错误；它需要“电源预算 + 接口契约 + 跨组检查 + 端到端验收”四类内容，正好是组文件没有的维度。建议 8–10 个配方，每个 25–40 行：

1. 电池供电 BLE 温湿度节点：A5 + I3 + H2/H7 + G1 + F2 + E6/H8。
2. USB-C 供电 + 1S 充电 + 电量：F2/F3 + H2/H3 + E6 + G1。
3. 12/24 V 有刷电机驱动板：K5 + E3 + F7 + G2 + I2 + C5/C6。
4. 工业 RS-485 隔离采集节点：J5 + D7 + E7 + F7 + G6 + M8。
5. 称重/压力数据采集：D1/D2 + E7 + I4 + F7。
6. 触屏 HMI：L4/L5 + I2 + G1 + J1 + F1。
7. 存在检测：B5/B8 + H7 + I3 + G1。
8. 隔离电流/电源：E5 + G6 + M8 + J5。
9. 环境监测（T/RH/P/AQ）：A5/A6/A7 + J1 + L3 + F2。
10. 加热控制：K9 + A1/A2 + F7 + K3。

每个配方固定四段：适用场景与用户话术；组合链（按电源→主控→接口→负载排序）；跨组检查点（预算/电平/地/隔离/默认态）；验收证据（测什么、用什么仪器、通过判据）。

### 16.5 为什么不采用每主题一个文件

- 102 个主题各一个文件会产生 102 个路由项；`SKILL.md` 按需读取表将无法维护，Agent 也很难在“测水温”与“测气压”之间选文件。
- 大量判据是跨主题共享的：ADC/基准链被 7 组引用，I²C/SPI 被 10 组引用，隔离边界被 4 组引用，保护链被 5 组引用。按主题拆会把同一段规则复制 5–10 次，后续修正必然不同步。
- 同组主题需要横向对照表（PIR vs mmWave、反射 vs 对射 vs ToF、NTC vs RTD vs 数字温度、低侧 vs 高侧 vs 隔离）。拆文件后这些表无处安放。
- 现有仓库的使用方式是“先读 1–2 张卡”；组文件正好是“1 张卡覆盖一组”，比 102 个小文件更符合加载习惯。
- 测试契约按 13 组检查；每主题一个文件会让机械检查与索引成本线性上升。

### 16.6 为什么不采用一个巨型文件

- 102 个主题 × 60–120 行 = 6000–12000 行；超过现有最大文件 `module-integration.md`（846 行）一个数量级，无法按需加载，也无法在单次编辑中安全修改。
- 多人/多轮写作会在同一文件产生冲突；组文件把冲突限制在单组。
- 巨型文件会让“按症状找”的检索失效；13 个组文件 + 组内 `##` 标题仍可用 Grep 定位。
- 单文件无法承载 28 张需要逐脚/算例的提升卡；这些卡必须独立，才能被其他组引用。

**拆分触发条件**：单组文件超过 1350 行，或单主题节超过 130 行，才拆为 `x-a.md`/`x-b.md` 或提升为卡；默认不拆。J 组 1200–1350 行是上限，超过则按 J1–J4 / J5–J8 拆两半，并同步测试清单。

---

## 17. 证据与来源计划

### 17.1 证据分级

- **E1**：实际打开原厂 datasheet/app note，记录文档号、版本、页码/节，结论可复算。
- **E2**：原厂资料存在但只读了部分章节，或数值需按具体后缀重查。
- **E3**：只有模块厂/卖家页/社区资料，参数不能当保证值；必须标注“仅趋势/教学”。
- 组文件每个主题开头 1–3 行“结论先行 + 证据标签”；提升卡在 §12 写来源表。

### 17.2 哪些需要原厂数据手册，哪些只需通用方法

| 组 | 需要 E1 原厂手册的锚点（每主题至少 1 个） | 只能 E2/E3 的模块/弱资料 | 仅复用通用方法、无需新来源 | 新增 CHW-S 预留 |
|---|---|---|---|---:|
| A | `NCP15XH103F03RC`、`PTS0603M1B100RP100`、`TMP117`、`MAX31855/31856`、`SHT40`、`BMP390`、`SGP41`/`SCD41` | `AHT20`、`MQ-135`（E2/E3） | A1/A3 的 RTD/NTC 电气部分引 `ANA-10`/`C1` | 6–10 |
| B | `BH1750FVI`/`OPT3001`、`BPW34`+`OPA320`、`TCRT5000`、`TCST1103`、`EKMC1601111`、`VL53L1X`、`MB1240`、`BGT60LTR11AIP` | `GL5528`、`HC-SR501`、`HC-SR04`、`LD2410C` | B1/B2 的运放/ADC 部分引 `ANA-02/04`、`C3` | 14–20 |
| C | `LIS2DH12`、`LSM6DS3`、`LIS3MDL`、`DRV5032`、`AS5600`、`EC11/PEC11R`、`D2F-5`、`TL-Q5MC1` | `A3144`、`QMC5883L`、`HC-SR501` 类模块 | C2 的 I²C/ESD 引 `D1/F28`；C6 的风扇 TACH 引 `E3` | 8–12 |
| D | `HX711`、`ADS1232`、`MPXV5010DP`、`BMP388`、`MS5837-30BA`、`JSN-SR04T`、`SEN0308`、`YF-S201`、`INA149` | `XKC-Y25`、土壤模块、`RCV420`（旧例） | D1 桥式引 `ANA-09`；D7 4–20 mA 引 `ANA-08` | 10–16 |
| E | `INA181`、`INA240`、`INA228`、`AMC1300`、`AMC1306`、`BQ27441/27542`、`ADS131M08/ADS8688` | 无（本组几乎全是芯片） | E1/E2/E3 主体引 `ANA-01/06/07`；E6 引 `B3` | 10–14 |
| F | `STUSB4500`、`TPD3S014`、`TPS2595`、`SMBJ5.0A`、`BQ24313`、`PJ-002A` | `CH224K`、`TP4056` 类模块 | F2/F5/F6 引 `PWR-12/09/11` | 8–12 |
| G | `TPS7A02`、`TPS54202H`、`TPS61023`、`TPS63802`、`TPS63710`、`SN6501`、`TPS22918`、`TPS2116` | `B0505S`、`MT3608` 模块 | G1–G4 主体引 `PWR-01/02/03/04` | 8–12 |
| H | `E91`、`CR2032`、`ER14250`、`MCP73831`、`BQ24074`、`BQ25619`、`BQ29700`、`BQ76952` | `TP4056`、`DW01A+FS8205A`、成品保护板 | H2/H3/H4/H6/H7 引 `PWR-06/07/08/05`、`B1/B2/B3` | 8–12 |
| I | `CH32V003`、`STM32F103/G030`、`ESP32-C3-MINI-1`、`STM32G431`、`TPS3823`、`CH340C`、`AT24C256` | `STC8G`、`PY32`、`HC-05` 类 | I5 引 `MCU-05/06`；I2 引 `MCU-01` | 8–12 |
| J | `THVD1450`、`TCAN334`、`W5500`、`USB2514B`、`CH340C`、`MAX3232`、`SHT40`/`AT24C256`/`TCA9555` | `HC-05`、ESP-AT 模组 | J1–J8 物理层引 `IF-01`–`IF-12` | 10–16 |
| K | `DRV110`、`EMC2301`、`MG996R`/`SG90`（厂商资料弱）、`TPS1H100`、`DRV8871`、`TMC2209`、`IRLZ44N` | `HC-SR501` 类、`BTS7960` 模块 | K1 引 `DRV-01`；K3 引 `DRV-03`；K9 引 `DRV-08` | 8–12 |
| L | `SSD1306`、`TM1637`、`MAX98357A`、`FT6236`、`ST7789V`、`WS2812B`、`CEM-1203` | 0.96 寸 OLED 模块、LED 灯带 | L1 引 `DRV-07`；L4 引 `RF-05`；L9 引 `RF-06` | 12–18 |
| M | `SX1268`、`EG915N`/`EC200U`、`MAX-M10S`、`DS3231`、`PN532`、`ISO7721`、`ESP32-C3` | `LD2410`、`HC-05`、`MFRC522` 模块 | M1/M2/M4/M5 引 `RF-01`–`RF-04`；M8 引 `SC38/RT10` | 12–18 |
| **合计** | 每主题至少 1 个锚点，复用主题不重复登记；去重后唯一型号少于 102 个 | 约 20–25 个模块/弱资料条目 | 约 35 个主题纯复用 | **122–184，预算 158** |

### 17.3 来源登记规则

- 每条：`CHW-Sxxx | 厂商 | 文档号 | 版本/日期 | 实读页/节 | 支持的结论 | 不能推广的部分 | URL`。
- 同一型号只登记一次；不同封装/后缀的差异写进“不能推广”。
- 模块/卖家页只能支撑“接口/尺寸/典型应用”，不能支撑精度/寿命/安规。
- 标准（IEC 60751、EN 50291、UL 2034、IEC 61000-4-5、IEC 60664、UN38.3、IEC 62133）未取得正文时，只写“需取得并核对”，不写“已满足”。
- 采购节只写检索字段与“待查”，不写 C 号/库存/价格/MOQ。

### 17.4 预计新增数量

按上表区间合计：**下限 122 条、上限 184 条**；按 **158 条**做预算。E1 条目按每个新写主题至少 1 个锚点登记；模块/卖家资料只占少数并统一标 E2/E3；其余为现有卡片的复用登记（不新增 ID，只补“不能推广”边界）。写作时先登记来源再写正文，避免“先写型号后补来源”。

---

## 18. 风险

| 风险 | 最可能出现的主题 | 具体表现 | 对应检查 |
|---|---|---|---|
| 典型值当保证值 | A2/A5/B6/B7、E3/E6、G1/G2、H2/H3、K5/K6 | TMP117 ±0.1°C、SHT40 ±1.8%RH、VL53L1X 4 m、MB1240 7.65 m、LDO 270 mV、P-MOS `Rds(on)`、INA 增益误差、BQ27441 2.5 A 被写成无条件值 | 每个数值必须带“型号/后缀/条件/min-max”；验收判据只用保证值；典型值标“typ”并说明不用于放行 |
| 模块与裸芯片混淆 | B3/B5/B7/B8、D4/D6、G6/G7、H1/H4、I1/I3、K7/K8、M3/M7 | HC-SR501/HC-SR04/LD2410/YF-S201/GL5528/MQ-135/TP4056/B0505S/ESP32 模组被当成芯片写逐脚；模块自带的 LDO/上拉/电平转换重复添加 | 每节开头写“模块/芯片”二选一；模块只写接口/供电/外围去重；裸芯片才写逐脚与外围 |
| 安规/气体报警越界 | A7、E5、F3、G6、K3/K9、M8 | CO/可燃气体写“满足 EN 50291/UL 2034”；隔离写“认证”；AC 加热/SSR 写“合规”；PoE/电池包写“已认证” | 统一写“通用 Skill 不声称认证，需取得标准并由专业人员签核”；标准正文未读时只写“需核对” |
| 分辨率/精度/量程混淆 | A2/A6、B1/B6、C5/C6、D1/D2、E1/E7、L2 | ADC 位数当精度、lux 量程当分辨率、气压噪声当高度精度、ToF 标称量程当全场景、称重额定当安全过载、编码器 PPR 当档位 | 每主题设“术语表”：分辨率/精度/重复性/量程/过载/条件；验收用误差与重复性，不用位数 |
| 环境/安装条件外推 | A5/A6/A7、B5/B6、C1/C2、D2/D4/D5、K7/K8 | 裸板数据当装壳后；IP 等级当防凝露；气孔/光窗/声孔被壳体/三防漆堵；PIR 被气流直吹；ToF 盖板串扰 | 每条结论带“裸板/装壳/介质/温度/气流”条件；组合应用强制“装壳前后对比” |
| 库存/价格/C 号编造 | 全部采购节 | 写具体 C 号、库存、价格、MOQ、交期；把“常见”当“有货” | 机械检查拦截 `C\d{4,}`；采购只写检索字段 + `待查`；候选型号不承诺供货 |
| 旧错误复制 | E3/E4、J5/J7、K1–K3、H1/H8、L2、M6 | 复制 126 ms/21.4 ms 释放时间、10 mA `V_os`、RS-485 1.2 W/只、25 mV、Pt100 0.362、1085 LSB | 写作前先执行第 15 节修正；对旧值做 Grep 黑名单；新卡引用旧卡时只引修正后结论 |
| 单型号外推 | F2/F3、G1/G4、H2/H3、I3、J8、M4 | DP83822 `RBIAS`、TPS7A02 5%、PWR-06 4.2 V、BQ27441 2.5 A、ESP32-C3 350 mA、DRV8825 0.4 Ω 被写成通用 | 每个型号段落写“仅该型号/后缀”；换型号必须重查的清单 |
| 校准/验证越界 | A4/A5/A7、D1–D6、E4–E6、H8、M6 | 没有恒温槽/砝码/标准气/电池模拟器，却写“已验证”；模型值当实测 | 区分“设计计算/仿真/首板/实测”；未执行标 `NOT RUN`；验收写仪器/接线/通过判据/停止条件 |
| 电池安全 | H1/H4/H5、A1/A4 | 一次电池写充电参数；Li-FeS₂ 标称 1.8 V；保护板当充电器；NTC 旁路；多节用 1S 保护板 | 化学体系表 + “一次电池禁止充电”硬约束；保护/充电/电量计职责表；多节必须 AFE/monitor |
| 假隔离 | E5、G6、J5/J6、M8 | 只加数字隔离器不加隔离 DC-DC；把“地分开”当隔离；给统一爬电毫米值；隔离侧调试口共地 | 强制检查“隔离电源、两侧地、跨屏障器件、爬电/间隙、调试口”；爬电只写“按标准/污染等级/材料组/海拔查” |
| 无线/法规越界 | F3、I3、M1–M5、M7 | “C 口就是 PD”“433 随便用”“模组有 FCC ID 就能卖”“LoRa 距离按 Wi-Fi 净空算” | 每个无线主题写目标市场/频段/占空比/功率；模组认证≠整机认证，引 `D4`；PD 高压另算爬电 |
| 组合应用“每块都对、合起来不对” | `combinations.md` 全部 | 电源预算只算典型、接口电平/地/默认态未对齐、天线/传感器互相干扰、保护协调缺失 | 每个配方强制四段：电源预算（峰值/同时性）、接口契约（电平/方向/上拉）、地/隔离、端到端验收 |
| 结构与计数漂移 | 索引/测试 | 13 组文件、60→63 卡、190 检查、12 范例、4 项目、35 场景多处不一致 | 最后一次统一重算；`tests/test_common_hardware.py` 机械检查；提交前 Grep 旧计数 |

---

## 19. 落地顺序与验收门槛

1. **第 0 步：修旧账**。先执行第 15 节 C01–C30（确定性错误），再动笔；否则新内容会复制旧值。
2. **第 1 步：13 个组文件骨架**。每组先写 `## 0. 本组怎么用` + 主题表 + 每主题 12 个三级标题的空壳 + `## 本组来源`；跑 `tests/test_common_hardware.py` 机械检查。
3. **第 2 步：按“missing → partial → adequate”顺序填内容**。先写 27 个 missing 的全新节/卡，再补 60 个 partial，最后给 15 个 adequate 加 5–20 行外层。
4. **第 3 步：提升卡**。优先 A（SEN-01..05）、D（SEN-06..12）、I（MCU-09..15）、K（DRV-09..11）、M（RF-09/MCU-16/IF-13/IF-14）、H（PWR-15/16）；每张卡完成后回填组文件链接。
5. **第 4 步：组合应用**。8–10 个配方，每个至少一条端到端验收；不做“每块都通过就算组合通过”。
6. **第 5 步：索引/场景/来源同步**。统一重算卡片/检查/范例/项目/场景计数；`source-register` 补齐 122–184 条预算内的实际条目。
7. **验收门槛**：每个主题至少 1 个 E1 锚点（或明确 E2/E3 边界）；每个数值有型号/条件；每个采购节无 C 号/价格/库存；每个组合应用有四段验收；`NOT RUN`/`BLOCKED` 如实标注；13 组机械检查全绿。
