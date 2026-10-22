# L 显示、声音、按键与交互 盘点

> 审计对象：`C:\Users\jlc\work\hardware-design-skill`（分支 `feat/eda-schematic-quality`，HEAD `0fe5cf8`）。
> 方法：按 `SKILL.md` 按需读取表定位，再用 Grep 抽查；只读相关段落，未全量加载大文件。
> 证据口径沿 `references/evidence.md`：判定只针对"本组 11 问是否够用"，不代表仓库其他领域质量。
> 行号均为当前工作区文件的 1 起始行号；路径相对仓库根。

---

## L1 LED 指示

**现有内容**
- `design-hardware/references/design-cards/drive/d07-led-cc.md` L11–271（整卡）：LED 恒流/限流路线；L43 明写"串联限流电阻…只适合指示类 LED"；L131–180 12 V/3 灯珠/376 mA 算例；L182–194 选型；L196–209 逐脚；L219–231 PCB；L233–247 异常；L249–261 验证
- `design-hardware/references/design-cards/README.md` L90（DRV-07 索引，证据 E1）
- `design-hardware/references/selection/semiconductors.md` L141–151（§5 "Vf 是范围不是常数"）、L174（商城关键词 `0805 LED 红色 20mA`）
- `design-hardware/references/selection/passives.md` L85（LED 限流判据）、L98–105（5 V±5%、Vf 1.8–2.2 V、180 Ω±5% 的角落算例：13.49–20.18 mA、69.6 mW）
- `design-hardware/scripts/calculate.py` L6/L31/L61–66（`led` 模式：`vs_min_V/vs_max_V/vf_min_V/vf_max_V/r_ohm/r_tol` → `i_min_A/i_max_A/resistor_power_max_W`）
- `design-hardware/references/schematic-lessons.md` L20–23（SL02：电源灯等"不起眼支路"会吃掉低功耗预算）
- `design-hardware/references/thermal/topic.md` L209–222（§3.5 LED 热预算：`P_elec/P_heat/Rth_JS_real`）
- `design-hardware/references/thermal/cases.md` L184–225（C05 LED 6 串/350 mA 热阻链）
- `design-hardware/references/domain-design-details.md` L77–79（DM41–DM43）
- `design-hardware/references/pcb-placement-details.md` L13（PL07 人机位置：按钮/LED 与外壳开口一起定位）
- `design-hardware/references/projects/p04-usb-mcu-board.md` L54–58、L81–87（D101 KT-0603R + 1 kΩ，Vf 1.8/2.0/2.4 V → 1.5/1.3/0.9 mA，并声明"1 k 不是通用 LED 电阻"）
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md` L264（CHG 开漏脚直接驱动 LED）
- `design-hardware/references/task-scenarios.md` L9（S02 USB 小灯/指示器）、`design-hardware/references/starter-patterns.md` L7（USB 小灯/指示器骨架）

**判定：partial**

**已覆盖：** 单只指示 LED 用串联电阻时的最坏电流/电阻功耗计算、`Vf` 分档不能当常数、大电流改恒流（TL4242，E1）、LED 结温两种口径，以及低功耗下"电源灯常亮"的漏电提醒。

**缺口（对照 11 问）**
- 用户话术：缺"做个指示灯/状态灯/呼吸灯/氛围灯/RGB 灯"到路线的生活化分流；S02 只覆盖 USB 小灯一个入口。
- 路线选择：缺 单色指示（电阻限流）→ 多路状态（GPIO 直驱 vs 驱动 IC）→ RGB（共阳/共阴/双色）→ 可寻址灯珠（WS2812B/SK6812）的判据与代价；DM43（L79）只有一句"5V 灯带不自动兼容 3.3V 数据"。
- 必查参数：缺 发光强度/视角/波长分档/额定电流温度降额/反向漏电；缺 GPIO 单脚与端口总灌拉电流上限（`selection/modules-connectors.md` L53 只有一句"驱动 LED/栅极要算"）。
- 电路组成：缺 多路 LED 的公共极与驱动管、每路限流电阻、可寻址灯珠的串联链与末级供电/去耦。
- 参数确定：缺 亮度预算（环境光下是否可见）、PWM 频率与可见闪烁、不同颜色 `Vf` 差异下同一阻值亮度差、低占空比线性度。
- 原理图：缺 LED 极性/双色共阳共阴画法、3.3 V GPIO 驱动 5 V 灯带、灯灭时的反灌/微亮路径。
- PCB：缺 导光柱/面板开窗、灯珠间距与混光、可寻址链的走线顺序与末端压降。
- 程序：缺 PWM 亮度曲线（gamma）、非阻塞呼吸/闪烁、灯效状态机。
- 验证：缺 亮度/视角实测、强光与暗室可见性、PWM 纹波/EMI、待机漏电。
- 常见误判：缺"按典型 Vf 算 15 mA 就安全"（passives 有算例但未连到"亮度够不够"）、"灯亮=电源正常"、"可寻址灯珠颜色错=灯珠坏"。
- 采购：缺 颜色/亮度/波长 bin、封装 0603/0805/3528、可寻址灯珠版本差异。

**动作：supplement**（复用 d07 + passives §2.2 + calculate.py `led`，只补"指示"这一档的路线、亮度与多路/灯带边界）

**候选型号**
- 首选 通用单色贴片 LED 0603/0805（如 Everlight 17-21/19-217 系列、Kingbright APT1608 系列；具体亮度/波长 bin 待按商城检索核对）
- WS2812B（Worldsemi，5 V 可寻址，数据门限需核）
- SK6812MINI-E（小尺寸可寻址，内置 IC）
- TL4242（已有 E1 卡，仅作大电流恒流对照，不重写）

**备注：** d07 是"照明/背光"取向的恒流卡，正文只在 L43 一句带过"指示类可用电阻限流"，容易被读成"LED 都该恒流"。新增 L1 必须显式写"指示 LED 默认电阻限流，恒流用于大电流/多串/背光"，并链接 d07 而不是重抄公式。

---

## L2 数码管与矩阵显示

**现有内容**
- 无 7 段数码管/LED 点阵内容。可复用或相邻的只有：
  - `design-hardware/references/engineering-deepdives/casebook/hmi-connectors-thermal.md` L25（Keyboardio 4×8 **按键**矩阵 + 每键 1N4148，COL→二极管→按键→ROW；不是显示矩阵）
  - `design-hardware/references/schematic-details.md` L54（SC39 功率输出结构）、L55（SC40 连接器视角）
  - `design-hardware/references/starter-patterns.md` L12（"USB 小键盘/控制器"骨架，风险列"矩阵鬼键"，库内无解释）
  - `design-hardware/references/design-cards/interfaces/i01-i2c.md`、`i03-spi.md`、`i04-spi-multi.md`（I2C/SPI 电气、片选，可作驱动 IC 的接口基础）
  - `design-hardware/references/domain-design-details.md` L79（DM43 可寻址灯珠/显示链一句）

**判定：missing**

**已覆盖：** 除"键矩阵 + 二极管防鬼键"的真实开源实例与 I2C/SPI 通用电气外，没有数码管、LED 点阵、扫描驱动、亮度/鬼影/电流预算的任何内容。

**缺口（对照 11 问）**
- 用户话术：缺"做个计数器/倒计时/温度显示/点阵屏"的入口。
- 路线选择：缺 直驱（GPIO+限流）→ 移位寄存器（74HC595）→ 专用驱动（TM1637/MAX7219/HT16K33）→ 智能灯珠矩阵 的判据（键数、亮度、成本、占 GPIO）。
- 必查参数：段/位电流与峰值、扫描占空比与平均亮度、扫描频率、共阳/共阴、驱动 IC 的限流设定（RSET）。
- 电路组成：缺 位选/段选、限流电阻放段线还是位线、位选驱动管（PNP/NMOS/ULN2003）、去耦。
- 参数确定：缺 段电阻（含 1/N 占空比）、全 8 全亮电流预算、亮度均匀性、扫描频率下限（闪烁）。
- 原理图：缺 共阳/共阴符号与位选驱动、多位级联、按键扫描复用。
- PCB：缺 段/位电流回路、同批 LED 亮度一致性、矩阵交叉走线。
- 程序：缺 定时器/ISR 动态扫描、消隐（防鬼影）、亮度 PWM 叠加。
- 验证：缺 全段点亮电流/温升、鬼影/串亮、扫描闪烁、按键扫描互扰。
- 常见误判：缺"限流按静态 20 mA 算、忽略 1/8 占空比"、"鬼影当驱动坏"、"共阳共阴接反"。
- 采购：缺 模块（TM1637 4 位）vs 裸数码管、位数/颜色/共极、点阵尺寸。

**动作：new**

**候选型号**
- 首选 TM1637（Titan Micro，4 位 7 段 + 8 键扫描，2 线；手册简短完整，模块极常见）
- MAX7219/MAX7221（ADI/Maxim，8 位 7 段或 8×8 点阵，SPI，手册完整）
- HT16K33（Holtek，I2C 16×8，带 RAM 与按键扫描）
- 74HC595（Nexperia/TI，分立移位方案，用来讲清段/位与限流位置）

**备注：** 无既有错误。但 `module-cards.md` L50 的"按键/LED 及适用驱动"会让人以为矩阵/数码管已有内容，新增后应补链接。

---

## L3 OLED 与液晶模块

**现有内容**
- 无 OLED/字符 LCD 内容。可复用：
  - `design-hardware/references/design-cards/interfaces/i01-i2c.md`（上拉、总线电容、地址）
  - `design-hardware/references/design-cards/interfaces/i02-i2c-buffer.md`（长线/多设备）
  - `design-hardware/references/failures/f06-i2c-pullup.md`、`f28-i2c-unpowered-device-lockup.md`
  - `design-hardware/references/module-integration.md` L315–337（§10 已集成外围去重：上拉/LDO/电平转换做两遍或以为模块里有）
  - `design-hardware/references/domain-design-details.md` L72–73（DM39/DM40，只讲屏/FPC 与背光/触摸分验）
  - `design-hardware/references/design-cards/wireless/w05-display.md` L41（明说不覆盖触摸，也未覆盖 OLED）

**判定：missing**

**已覆盖：** 只有通用 I2C 电气与"模块已集成外围要去重"的原则，没有任何 OLED/字符 LCD 模组的供电、电荷泵、对比度、地址与初始化内容。

**缺口（对照 11 问）**
- 用户话术：缺"显示两行字/看温度/做菜单"的入口。
- 路线选择：缺 OLED（自发光、高对比、低温/烧屏）vs 字符 LCD（便宜、阳光下可读、需背光）vs 段码 LCD 的判据。
- 必查参数：供电（3.3/5 V、模块是否带 LDO）、逻辑电平、I2C 地址（0x3C/0x3D）、电荷泵电容、复位脚、对比度（V0/指令）、工作温度、视角。
- 电路组成：缺 模块 vs 裸屏、电荷泵电容（C1/C2）、复位 RC、I2C 上拉归属（模块自带 vs 主板再加 → F06 并联上拉）。
- 参数确定：缺 长排线的总线电容/上拉、128×64 全屏刷新的 I2C 时间量级、背光/对比度电阻。
- 原理图：缺 模块引脚（VCC/GND/SCL/SDA/RES/DC/CS）、地址选择、电源域。
- PCB：缺 视窗/开窗、FPC 或排针、模块背面器件高度、与按键的装配顺序。
- 程序：缺 初始化序列、页/列寻址、显存与局部刷新、字符库。
- 验证：缺 上电花屏/不亮、低温、长线、对比度、烧屏。
- 常见误判：缺"模块标 5 V 就直连 5 V IO"、"OLED 不亮=屏坏"（实际是复位/地址/电荷泵）、"I2C 扫不到=地址错"（可能是上拉/电平）。
- 采购：缺 0.96/1.3 寸、I2C/SPI、单色/双色、模块厂商差异。

**动作：new**

**候选型号**
- 首选 SSD1306（Solomon Systech，128×64 OLED，I2C/SPI；模块最常见，手册完整）
- SH1106（1.3 寸 132×64，RAM/寄存器与 SSD1306 不同，常被误当兼容）
- HD44780 兼容 1602/2004 字符 LCD + PCF8574 I2C 背板（讲并口 vs 背板、对比度 V0）
- ST7565（128×64 反射式 LCD，SPI；阳光下/低温对照）

**备注：** "SSD1306 与 SH1106 不完全兼容"是高频误判，库内无任何提醒。另 `module-cards.md` §8 的"屏/背光"笼统说法把 OLED（无背光）与 LCD（有背光）混在一起，新增时应纠正。

---

## L4 TFT 显示

**现有内容**
- `design-hardware/references/design-cards/wireless/w05-display.md` L1–209（整卡）：§1 L37–49 边界；§2 L51–64 必要输入；§3 L66–76 拓扑；§4 L78–105 参数步骤（ST7789V 时序 L92–98、TPS61169 背光 L99–105）；§5 L107–127 算例；§6 L129–142 选型；§7 L144–157 逐脚；§8 L158–162 原理图；§9 L164–177 PCB；§10 L179–190 异常；§11 L192–199 验证；§12 L201–209 来源
- `design-hardware/references/design-cards/README.md` L101（RF-05 索引）
- `design-hardware/references/domain-design-details.md` L72–73（DM39 完整料号/FPC/供电时序；DM40 背光/触摸分验）
- `design-hardware/references/failures/f15-fpc-pin1.md` L1–84（FPC Pin-1/接触面反向；L13 关联 SC40/PL04/DM39/MF09/RT18）
- `design-hardware/references/module-integration.md` L216–249（§7 连接器契约、三方脚序表、FPC 额外约束）
- `design-hardware/references/task-scenarios.md` L31（S24 改板：FPC 方向/Pin-1 反例）
- `design-hardware/references/analog-rf-highspeed.md` L12–15（音视频与显示：完整型号/供电顺序/lane/FPC）
- `design-hardware/references/domains.md` L16（显示/摄像头/音视频路由行）
- `design-hardware/references/pcb-placement-details.md` L13（PL07）、L25（PL16）
- `design-hardware/references/design-cards/interfaces/i03-spi.md`、`i04-spi-multi.md`（SPI 时序/片选）
- `design-hardware/references/enclosure-integration.md` L11（按钮/LED/屏的堆叠与装配顺序）

**判定：partial**（SPI-TFT 子场景接近 adequate；作为"TFT 显示"整体仍缺选屏、带宽、大屏接口、程序与采购）

**已覆盖：** SPI 4-line TFT（ST7789V）的接口模式、SPI 写周期上限、复位 10 µs/5 ms/120 ms 序列、背光恒流/升压参数与 FPC/EMI 约束，是本组最完整的一块，且证据为 E1。

**缺口（对照 11 问）**
- 路线选择：缺 SPI vs 8080 并口 vs RGB vs MIPI-DSI/LVDS 的判据（分辨率×刷新率→带宽、引脚数、MCU 是否有 LTDC/DSI、所需 RAM）；w05 L41 明说"不选屏"。
- 必查参数：缺 分辨率/刷新率/色深与带宽估算（15 MHz SPI 下 240×320 全屏刷新的时间量级）、驱动 IC 与屏厂模组的关系、亮度/视角/工作温度、背光串并数（w05 列出但要求查屏厂）。
- 电路组成：缺 并口/RGB 的 3.3 V/1.8 V 电平转换、MIPI 的 AVDD/AVEE/VGH/VGL 上电时序、TE 信号、触摸 FPC 复用。
- 参数确定：缺 帧率/带宽预算、背光与整机功耗预算、屏启动浪涌。
- 原理图：w05 已覆盖 SPI 场景；缺 大屏多电源域与上电顺序。
- PCB：w05 已覆盖 SPI/背光；缺 RGB/MIPI 的等长/阻抗/差分、FPC 屏蔽与 ESD。
- 程序：完全缺（初始化序列、帧缓冲、DMA、局部刷新、LVGL 类框架的资源需求）。
- 验证：w05 有 SPI/背光测量；缺 帧率、撕裂、低温、EMI 实测。
- 常见误判：缺"SPI 屏能点亮但刷新慢到不能用"、"同尺寸同针数可替换"（F15/DM39 有原则但无屏实例）、"背光亮=显示通"（DM40 仅一句）。
- 采购：缺 屏模组完整料号/版本/批次、亮度/视角/工作温度、供货周期。

**动作：supplement**（w05 几乎原样复用；新增只补"选屏与带宽"、"大屏接口"，以及程序/采购两节）

**候选型号**
- 首选 ST7789V（已有 E1 卡，240×320 SPI，生态最广）
- ILI9341（240×320 SPI，资料多，作对照）
- GC9A01（240×240 圆屏，圆形产品常见）
- ILI9488（320×480 SPI，用来暴露"SPI 带宽不够"的边界）

**备注：** w05 L41 "它不选屏"与 §6 L133 选型表里的"屏/控制器"行自相矛盾（表里给了屏的必看参数）；新增时把"选屏判据"放 L4，w05 保持"接口+背光"定位并加一句"选屏见 L4"。w05 已自述 ST7789V Table 6 列对齐需回读原图，引用时不得当保证值。

---

## L5 触摸屏与电容触摸

**现有内容**
- 无。仅有：
  - `design-hardware/references/domain-design-details.md` L73（DM40 一句"背光、电源与触摸/图像程序分开验"）
  - `design-hardware/references/design-cards/wireless/w05-display.md` L41、L199（明确不做触摸）
  - `design-hardware/references/engineering-deepdives/casebook/high-speed-rf-fpga.md` L195、L227、L265（Fomu Captouch Pads SW2，只有位号，未做触摸测试）
  - `design-hardware/references/engineering-deepdives/casebook/index.md` L23（自述"没有覆盖大尺寸 TFT/触摸/背光热设计的完整开源项目"）

**判定：missing**

**已覆盖：** 只有"触摸要与背光/显示分开验"一句话，以及一块没有实测的电容触摸焊盘位号。

**缺口（对照 11 问）**
- 用户话术：缺"想按一下/滑一下/隔着外壳摸"→ 机械按键 vs 电容触摸 vs 触摸屏。
- 路线选择：缺 单键触摸 IC（TTP223/CAP1203）vs 触摸屏控制器（FT6236/GT911）vs MCU 内置 CAP 外设 的判据。
- 必查参数：灵敏度/阈值、响应时间、扫描功耗、overlay 厚度与材料、工作电压、I2C 地址、ESD 等级。
- 电路组成：缺 感应电极（尺寸/形状/走线）、串联电阻、寄生电容预算、guard/屏蔽、触摸屏 FPC 的 I2C/RST/INT。
- 参数确定：缺 电极电容量级（`C=εA/d`）、overlay 厚度对灵敏度的衰减、扫描周期 vs 功耗。
- 原理图：缺 电极网络、RST/INT 上下拉、地址选择、与显示 FPC 的合并。
- PCB：缺 电极铺铜/网格、背面不走线、guard ring、地与壳体、装配后的手指路径。
- 程序：缺 基线校准、漂移补偿、防水/防误触、触摸与显示刷新互扰。
- 验证：缺 戴手套/湿手/贴膜/装壳后的灵敏度、ESD、误触。
- 常见误判：缺"能隔 3 mm 塑料就一定行"、"触摸不灵=IC 坏"（实际是 overlay/寄生/地）、"触摸 I2C 与显示 SPI 同排线就一定兼容"。
- 采购：缺 触摸屏（电容/电阻、贴合方式、盖板）vs 触摸 IC 的选型与供货。

**动作：new**

**候选型号**
- 首选 FT6236G（FocalTech，电容触摸屏控制器，I2C，自校准；原厂资料可得性待核）
- GT911（Goodix，常见于 3.5–7 寸模组；资料以模组厂提供为主，待核）
- TTP223（TonTouch，单键电容触摸，SOT-23-6，手册极简，适合讲"电极+阈值"）
- CAP1203（Microchip，3 通道，I2C，手册完整，适合讲低功耗与灵敏度寄存器）

**备注：** 无既有错误。casebook index L23 已承认显示/HMI 案例不足，新增时不能拿 Fomu 的触摸焊盘当"已验证触摸设计"。

---

## L6 机械按键

**现有内容**
- `design-hardware/references/engineering-deepdives/casebook/hmi-connectors-thermal.md` L20–59（Keyboardio Model01：4×8 键矩阵、每键 1N4148、COL→二极管→按键→ROW、每键命名测试点；L59 明确"矩阵极性/去抖/鬼键在固件中如何实现"仍开放）
- `design-hardware/references/design-cards/mcu/m04-boot-strap.md` L40（外围拖偏）、L74（按键/跳线到 GND）、L127（100 nF 使释放变慢、取消）、L179、L213（按键抖动）、L224（冷启动/按键复位各测 10 次）
- `design-hardware/references/design-cards/mcu/m02-module-mcu.md` L126、L191、L204、L216（EN/strap 按键与 RC 并联重算、按键并大电容的坑）
- `design-hardware/references/design-cards/mcu/m03-reset-supervisor.md`（复位按键/监控器边界）
- `design-hardware/references/projects/p04-usb-mcu-board.md` L54–58（SW101/SW102 TS-1088-AR02026，BOM 注明"按动寿命/手感未核对"）、L142、L154（按键+万用表/示波器验证"能被拉低并释放"）
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md` L47、L269、L393（BOOT 按键强制下载）
- `design-hardware/references/starter-patterns.md` L12（USB 小键盘/控制器，风险列"矩阵鬼键"）
- `design-hardware/references/selection/passives.md` L86（按键/复位上拉：漏电与湿气下的默认态）
- `design-hardware/references/schematic-details.md` L33（SC21 安全默认态）、L55（SC40 连接器视角）
- `design-hardware/references/pcb-placement-details.md` L13（PL07 按钮与外壳开口）
- `design-hardware/references/enclosure-integration.md` L11（按压行程/面板）
- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` L250–251（常开按键域、ship mode 唤醒路径）

**判定：partial**

**已覆盖：** 按键在启动 strap/复位/低功耗唤醒上的"默认态与误动作"风险、一个真实键矩阵（二极管防鬼键）的接线实例、按键可接近性与 BOM 位号。

**缺口（对照 11 问）**
- 用户话术：缺"一个按钮/一排按钮/做个键盘"的生活化分流。
- 路线选择：缺 独立 GPIO（≤N 键）vs 矩阵（行列）vs ADC 按键/编码器 的判据与键数临界。
- 必查参数：接触电阻/额定电流、按压力/行程/寿命、抖动时间（ms 量级）、ESD 等级、工作温度。
- 电路组成：缺 上拉/下拉归属、RC 去抖、串联电阻 + TVS/ESD、矩阵二极管方向与鬼键机理、多键同按。
- 参数确定：缺 RC 去抖时间常数与扫描周期配合、上拉电流在低功耗下的代价、湿气漏电下的余量。
- 原理图：缺 "按键接 GND+上拉" 与 "接 VCC+下拉" 的选择、复位/BOOT 复用、矩阵画法。
- PCB：缺 按键与外壳开孔/行程、ESD 泄放路径（靠板边）、矩阵走线与串扰。
- 程序：缺 去抖（时间/计数）、长按/双击、组合键、唤醒边沿/电平配置、矩阵扫描消隐。
- 验证：缺 抖动波形、万次按压、湿手/戴手套、装壳后手感与误触。
- 常见误判：缺"加 100 nF 就消抖"（实际拖慢释放、影响 strap）、"矩阵不加二极管也行"（鬼键）、"按下=低电平"（上/下拉接反）。
- 采购：缺 6×6/12 mm/带灯按键、行程/手感、寿命、面板开孔尺寸。

**动作：supplement**

**候选型号**
- 首选 TS-1088 系列 6×6 轻触开关（repo 的 F1 已用 TS-1088-AR02026，见 `projects/p04-usb-mcu-board.md` L57–58；寿命/手感待核）
- Omron B3F-1000/B3F-4000 系列（原厂 datasheet 完整，作参数对照）
- ALPS SKHH 系列（轻触，资料完整）
- 1N4148W（键矩阵防鬼键，SOD-123）

**备注：** `module-cards.md` L46 把"蜂鸣器须辨压电/电磁和有源/无源"放在 §7（电机/继电器/功率负载），而 §8（显示、音频与人机）没有按键/蜂鸣器内容，分类不一致。另 p04 的按键只做到"电平能翻转"，新增 L6 不能把该实例写成已验证手感/寿命。

---

## L7 旋钮与电位器

**现有内容**
- 仅 `design-hardware/references/engineering-deepdives/casebook/audio-analog-precision.md`：
  - L50（Braids issue #9：COARSE 旋钮 R39=120 k vs 100 k 的满度余量取舍，作者答"120 k 正确"——"电位器→ADC 满度/余量"的真实证据）
  - L65、L74（Clouds 多路 CV/旋钮接 STM32 ADC）
- 可复用的通用件：
  - `design-hardware/references/design-cards/analog/a01-divider.md`（分压器）
  - `design-hardware/references/design-cards/analog/a04-adc-driver.md`（源阻抗/采样保持）
  - `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md`
  - `design-hardware/references/pcb-routing-details.md` L34（RT22 高阻节点）
  - `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md`（常接分压的静态耗电）

**判定：missing**

**已覆盖：** 没有任何电位器/旋钮/编码器的电路内容；唯一可用证据是一位开源作者对"旋钮满度留多少余量"的取舍记录。

**缺口（对照 11 问）**
- 用户话术：缺"拧的旋钮/调音量/选菜单"→ 电位器 vs 旋转编码器 vs 按键加减。
- 路线选择：缺 电位器进 ADC（绝对位置、上电即知）vs 编码器（无磨损、无限位、需计数与掉电保存）vs 数字电位器 的判据。
- 必查参数：阻值/容差/线性度/taper（A/B/C）、机械角与电气角、旋转寿命、额定功率、端阻；编码器脉冲数/定位数/是否带按键。
- 电路组成：缺 电位器三端接法（两端接基准与地、中间进 ADC）、串阻、RC 滤波、编码器 A/B 上拉与 RC、消抖。
- 参数确定：缺 分压后源阻抗 vs ADC 采样时间（ANA-04）、ADC 位数→角度分辨率、taper 对"音量感"的影响、常接分压的静态电流。
- 原理图：缺 电位器/编码器符号与引脚（A/B/COM）、上电默认值、掉电保存。
- PCB：缺 面板开孔/轴长/固定脚、走线远离 PWM/电源、编码器机械应力。
- 程序：缺 ADC 中值滤波/迟滞、正交解码（中断/定时器）、加速（快转多走）、掉电保存。
- 验证：缺 全行程扫描（端点/死区）、抖动、长按、寿命、温漂。
- 常见误判：缺"电位器当可变电阻串在电路里"（两端悬空→非线性/易坏）、"编码器 A/B 接反只是方向反"（可能同时丢步）、"ADC 跳=电位器坏"（源阻抗/采样时间）。
- 采购：缺 6/9 mm 轴、带开关、阻值与 taper、编码器脉冲数/定位感。

**动作：new**

**候选型号**
- 首选 ALPS EC11 系列旋转编码器（EC11E15244B2 类，带按压开关，常见；具体后缀待核）
- ALPS RK09K/RK097 系列 10 kΩ 电位器（面板音量/位置，A 型 taper）
- Bourns PEC11R 系列（编码器，原厂 datasheet 完整，作参数对照）
- Bourns 3362P（微调电位器，用于校准而非面板）

**备注：** 无既有错误。Clouds 的 R39 取舍（L50）是很好的"满度余量"案例，但属 ±CV 合成器语境，不能直接当"电位器→ADC"通用值，引用须写条件。

---

## L8 蜂鸣器

**现有内容**
- `design-hardware/references/module-cards.md` L46（唯一一句："蜂鸣器须辨压电/电磁和有源/无源"）
- 可复用的驱动/感性负载内容：
  - `design-hardware/references/design-cards/drive/d01-low-side.md`（低侧开关）
  - `design-hardware/references/design-cards/drive/d03-relay.md`（线圈续流）
  - `design-hardware/references/engineering-deepdives/topics/e1-inductive-load-energy-path.md`
  - `design-hardware/references/schematic-details.md` L33（SC21 安全默认态）
  - `design-hardware/references/pcb-placement-details.md` L22（PL13 驱动回路）

**判定：missing**

**已覆盖：** 只有"先分清压电/电磁、有源/无源"一句分类提醒，没有驱动电路、参数或验证内容。

**缺口（对照 11 问）**
- 用户话术：缺"响一声/报警/滴滴滴/能调音量吗"。
- 路线选择：缺 有源蜂鸣器（给电就响）vs 无源（需方波、可调音）vs 扬声器（要语音/音乐）的判据。
- 必查参数：额定电压、谐振频率、声压级（dB @10 cm）、工作电流、驱动方式、工作温度。
- 电路组成：缺 GPIO→基极电阻→三极管/MOS→蜂鸣器；电磁式必须加续流二极管；压电式可串电阻；5 V 蜂鸣器在 3.3 V 下的电流/声压。
- 参数确定：缺 基极电阻（Ic/hFE）、蜂鸣器峰值对 LDO/电池的冲击、PWM 频率=谐振频率、占空比 50%。
- 原理图：缺 驱动管画法、续流二极管方向、默认关断（下拉）、测试点。
- PCB：缺 蜂鸣器开孔/声腔、驱动回路、与麦克风/传感器隔离。
- 程序：缺 有源=GPIO 电平；无源=PWM 频率/时长/节奏；关机"咔哒"声。
- 验证：缺 声压（手机 App 只能粗测）、电流、启停 pop、低电压下是否还能响。
- 常见误判：缺"无源蜂鸣器接直流不响=坏的"、"电磁式不加续流"（反向尖峰打穿 GPIO）、"3.3 V 驱动 5 V 蜂鸣器声音小是正常"（需说明）。
- 采购：缺 有源/无源、电压、频率、声压、尺寸（9×5.5/12×9.5）、引脚间距。

**动作：new**

**候选型号**
- 首选 CUI CEM-1203(42)（电磁式有源，5 V 类；电压/电流/声压待核）
- muRata PKLCS1212E4001-R1（压电无源，谐振 4.0 kHz，需外部方波）
- MMBT3904 / 2N7002（驱动管）+ 1N4148W（电磁式续流）
- 可选：自带三极管的有源蜂鸣器模块（新手路线，须标明"模块已集成驱动，不能重复加"）

**备注：** `module-cards.md` L46 位置问题同上；且该句没提"电磁式必须续流"，容易被读成"蜂鸣器随便接 GPIO"。

---

## L9 扬声器与简单音频

**现有内容**
- `design-hardware/references/design-cards/wireless/w06-classd.md` L1–199（整卡）：§1 L37–49；§2 L51–64；§3 L66–77；§4 L79–100（AD/BD、Type-1/2、f0/Q）；§5 L102–122（4 Ω/40 kHz → 12 µH+0.68 µF）；§6 L124–136；§7 L138–149；§8 L151–155；§9 L157–169；§10 L171–181；§11 L183–190；§12 L192–198
- `design-hardware/references/design-cards/README.md` L102（RF-06 索引，E1）
- `design-hardware/references/domain-design-details.md` L70–71（DM37 麦克风偏置/Codec/地；DM38 Class-D 阻抗/滤波/EMI）
- `design-hardware/references/module-cards.md` L49–53（§8 构成/核算/失效）
- `design-hardware/references/analog-rf-highspeed.md` L12–15（音频地回流、麦克风偏置、BTL 不当地）
- `design-hardware/references/domains.md` L19（音频功放/声学路由行）
- `design-hardware/references/engineering-deepdives/casebook/audio-analog-precision.md` L20–32（Braids：DAC8551→Sallen-Key 40.8 kHz→隔直→−4 增益→1 k 串阻）、L63–95（Clouds：WM8731 I2S 主模式、12.288 MHz、BCLK/LRCK、I2C 0x1A、bring-up 顺序）、L108–130（Edges：DAC/逻辑门混合、隔直与串阻）
- `design-hardware/references/engineering-deepdives/casebook/index.md` L19（4 个音频项目）
- `design-hardware/references/module-integration.md` L250–290（§8 合并负载/峰值——功放峰值电流）
- `design-hardware/references/thermal/topic.md` L34（功放属热失效器件）

**判定：partial**

**已覆盖：** Class-D 输出级（BTL 结构、是否需要 LC、Type-1/2、f0/Q、布局与 EMI）与真实开源音频链（I2S codec 时钟、DAC→滤波→隔直→增益）两块，方法 + 实例都较强。

**缺口（对照 11 问）**
- 用户话术：缺"放提示音/播语音/做个音箱/能调音量吗"的分流。
- 路线选择：缺 蜂鸣器（单音）→ PWM+RC+功放（低成本提示音）→ DAC/I2S 功放（语音/音乐）→ 成品 MP3 模块 的判据与成本/复杂度。
- 必查参数：功放 IC 的 PVCC/增益/最小负载/PSRR/关断电流/爆音抑制；扬声器阻抗/灵敏度（dB/W/m）/额定功率/谐振 F0/背腔。
- 电路组成：缺 输入耦合/RC、增益设定、静音/关断、扬声器连接器、麦克风偏置（若涉及）。
- 参数确定：缺 "要多大声"→功率→灵敏度的链路、峰值电流对电源/LDO 的冲击、背腔容积与低频。
- 原理图：w06 已覆盖功放块；缺 输入侧（PWM/RC/DAC）与音量控制。
- PCB：w06 已覆盖输出 LC/地；缺 扬声器腔体/出声孔/密封、麦克风与扬声器隔离。
- 程序：缺 采样率/位深、I2S 配置、PWM 音频（定时器分辨率/采样率）、音效与音量。
- 验证：w06 有频响/THD/EMI；缺 声压级、装壳后频响、爆音。
- 常见误判：缺"功放标 3 W 就能出 3 W"（受供电/负载/失真限制）、"扬声器 4 Ω 全频都是 4 Ω"（w06 已有原则）、"BTL 负极接地"（w06/DM37 已有）、"PWM 直接接扬声器"。
- 采购：缺 功放 IC 封装/散热、扬声器尺寸/腔体、连接器。

**动作：supplement**（w06 原样复用；新增补"简单音频路线选择 + 功放/扬声器选型 + 声学与装配 + 程序"）

**候选型号**
- 首选 MAX98357A（ADI/Maxim，I2S 输入 Class-D，3.2 W/4 Ω，无需输出 LC，ESP32 生态常见）
- PAM8302A（Diodes，模拟输入 2.5 W/4 Ω，讲"PWM/RC→模拟输入"路线）
- NS4168（国产 I2S 功放，成本路线；资料待核）
- 8 Ω/2 W 微型扬声器 + 背腔（型号按结构与腔体选，待核）

**备注：** w06 头 `related_checks` 写 `DM37`，但 Class-D 对应 `DM38`。另 w06 明确"不选功放、不做声学调音"，L9 必须补这两块，否则用户问"用哪个功放/喇叭"仍无答案。

---

## 复用关系

- **L1** → DRV-07 `d07-led-cc.md`（恒流/热）、`selection/semiconductors.md` §5、`selection/passives.md` §2.2、`calculate.py led`、`thermal/topic.md` §3.5、`schematic-lessons.md` SL02、DM41/DM42、PL07
- **L2** → IF-01/IF-03/IF-04（I2C/SPI/片选）、SC39（功率输出结构）、PL30（重复通道）、`module-integration.md` §8（全亮电流）
- **L3** → IF-01/IF-02（上拉/缓冲/长线）、F06/F28、`module-integration.md` §10（模块已集成上拉/LDO 去重）、DM39
- **L4** → RF-05 `w05-display.md`（接口+背光）、IF-03/IF-04、F15、SC40、DM39/DM40、`module-integration.md` §7（FPC 三方脚序表）、PL16/RT20/RT22、S24
- **L5** → IF-01（触摸 IC 的 I2C）、DM32/SC15（ESD）、F15（触摸 FPC）、DM40、`enclosure-integration.md`（盖板/开窗）
- **L6** → MCU-04/MCU-02/MCU-03（strap/EN/复位按键）、SC21、SC40、PL07、`b2-sleep-current-budget.md`（常开按键域/唤醒）、`selection/passives.md` L86、OSHW-25 案例
- **L7** → ANA-01（分压）、ANA-04（源阻抗/采样时间）、C1 专题、RT22、`b2-sleep`（常接分压耗电）
- **L8** → DRV-01（低侧开关）、DRV-03（续流）、E1 专题（感性负载能量路径）、SC21、PL13
- **L9** → RF-06 `w06-classd.md`（Class-D 输出）、DM38、`module-integration.md` §8（峰值/合并负载）、`audio-analog-precision.md`（I2S/DAC 链）、`thermal/topic.md` L34、PL16/RT22
- **跨组**：与"电源/电池"组共享功放/背光/蜂鸣器的峰值电流与 LDO 瞬态（`module-integration.md` §8.1）；与"MCU/数字"组共享 PWM 定时器、I2S 外设、GPIO 电流上限；与"接口"组共享 I2C 上拉与 SPI 带宽；与"结构/外壳"组共享开窗/导光/盖板/声孔（`enclosure-integration.md` L11–13）。

## 需要同步修正

1. `design-hardware/references/design-cards/wireless/w06-classd.md` L8：`related_checks: [SC39, PL16, RT22, DM37]` — Class-D 对应的是 **DM38**（DM37 是麦克风偏置/Codec/"BTL 不能当地"）。建议改为 `[SC39, PL16, RT22, DM38]`。
2. `design-hardware/references/module-cards.md` L46：蜂鸣器分类句在 §7（电机/继电器/功率负载），而 §8（显示、音频与人机）才是 HMI；建议移到 §8，§7 留"见 §8"。
3. `design-hardware/references/module-cards.md` L50/L53：§8 "构成"列了"Codec/功放/麦克风…按键/LED 及适用驱动"，但"深入"只链 RF-05/RF-06 两张卡——读者会以为按键/LED/Codec 已有卡。新增 L1/L6/L9 后必须补链接，或把"构成"改成与现有卡一致的措辞。
4. `design-hardware/references/domain-design-details.md` L70/L71：DM37 与 DM38 都写"BTL 两端都是输出，不能把任一端当普通地"；建议只保留在 DM38，DM37 改为指向 DM38。
5. `design-hardware/references/design-cards/wireless/w05-display.md` L41 "它不选屏"与 L133 "屏/控制器 | 接口模式、时序、供电、FPC" 自相矛盾；建议 L41 改为"选屏判据见 L4，本卡只处理接口与背光"。
6. `design-hardware/references/design-cards/drive/d07-led-cc.md` L47 把 §8 称作"显示/背光"，实际 §8 名为"显示、音频与人机"；建议改为"§7 功率负载、§8 显示与人机"。
7. `design-hardware/references/design-cards/README.md` L93：显示/音频卡（RF-05/RF-06）实际放在 `design-cards/wireless/` 目录，与"HMI"语义不符；新增 L 组引用时路径会显得奇怪，建议在该分组标题下注明"显示/音频卡位于 wireless/ 目录是历史归类"。
8. `design-hardware/references/starter-patterns.md` L12：用"矩阵鬼键"作风险词但库内无解释；新增 L6 后应加链接。

## 文件组织建议

**结论：本组用一个组文件，不拆分。** 按 `C:\Users\jlc\work\hds-common-scratch\authoring-guide.md`：每组一个 `design-hardware/references/common-hardware/<group>.md`，由 `scratch/groups/<group>/` 下的分文件拼装。

| 建议文件（scratch） | 内容 | 建议行数 |
|---|---|---:|
| `00-intro.md` | `## 0. 本组怎么用`：用户话术 → 先判断什么 → 路线 → 读哪个主题；组级复用说明 | 25–35 |
| `01-led-indicator.md` | L1 LED 指示（大量复用 d07/DRV-07、passives §2.2） | 50–60 |
| `02-seven-seg-matrix.md` | L2 数码管与矩阵（新写，含扫描/限流/亮度） | 90–110 |
| `03-oled-lcd-module.md` | L3 OLED 与液晶模块（新写） | 80–100 |
| `04-tft.md` | L4 TFT（复用 RF-05，补选屏/带宽/程序/采购） | 55–65 |
| `05-touch.md` | L5 触摸屏与电容触摸（新写） | 85–100 |
| `06-mechanical-key.md` | L6 机械按键（复用 MCU 卡 + OSHW-25 + F1 实例） | 70–85 |
| `07-knob-pot-encoder.md` | L7 旋钮与电位器（复用 ANA-01/ANA-04） | 75–90 |
| `08-buzzer.md` | L8 蜂鸣器（复用 DRV-01/DRV-03） | 70–85 |
| `09-speaker-audio.md` | L9 扬声器与简单音频（复用 RF-06） | 55–70 |
| `99-sources.md` | `## 本组来源`：CHW-S 编号、文档号/版本、实读章节、支持结论、不能推广部分、URL（建议预留 12–18 条） | 20–30 |
| `99-fixes.md` | `## 需要同步修正`（本文件"需要同步修正"1–8） | 12–18 |

合计约 **700–830 行**，与现有最大专题 `module-integration.md`（846 行）相当，单文件可维护；主题间强复用（I2C 上拉、FPC、ESD、峰值电流）也依赖同文件内互相引用。

**拆分条件（仅在触发时）：** 若 L2+L3+L5 三节各自超过 110 行、总文件超过 1100 行，再拆为 `l-hmi-display.md`（L1–L5）与 `l-hmi-input-audio.md`（L6–L9）；但需注意两半都会引用 I2C/FPC/ESD/电源峰值，拆分会造成重复或跨文件跳转，默认不做。

**每节结构：** 严格按 12 个三级标题（用户会怎么说 / 路线选择 / 必查参数 / 电路组成 / 参数与算例 / 原理图与逐脚 / PCB / 程序 / 验证 / 常见误判 / 采购与落地 / 来源与证据），复用型主题也不省略标题，正文用"见 [XXX] §N"压缩。
