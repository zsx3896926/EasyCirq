# 音频、模拟与精密电源组案例集（OSHW-18 ~ OSHW-21）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口)


**编号说明**：编号与 [sources.md](../../sources.md) 的 OSHW 台账一致；正文以项目名为准。

- 覆盖项目数：4。
- 实际读取的文件类别：EAGLE 5.x 二进制 `.sch/.brd`（3 项，自写解析器读取块表与网络）、KiCad 7/8 `.kicad_sch/.kicad_pcb`（EEZ，`version 20230121`）、README/LICENSE、GitHub commit/issue/tree、固件 `.cc/.h`（Braids/Clouds/Edges）。所有本地 EAGLE/KiCad 文件均与 GitHub master 逐一比对 SHA-256，一致。
- 未能读取的项目及原因：没有项目完全未读。限制如下：EEZ 的 `ac_input_sstart_bias.kicad_sch`、`fan_controller.kicad_sch` 不在本地快照，经 GitHub master 读取（与本地根图、PCB 同仓库、同一次核对）；EAGLE 三项目没有原生 EAGLE GUI，使用自写二进制解析器（字段偏移来自 KiCad `eagle_bin_parser.cpp` / pcb-rnd `io_eagle` 的格式表），未导出原生网表；未读 BOM xlsx、PDF 图纸、CE/LVD 报告、面板与 3D 文件；未做任何实测。

> 证据分级：A＝作者/维护者明确记录，或可直接复查的文件事实（位号、网络、坐标、层、宽度）；B＝原厂资料/通用机理支持，但本板未实测；C＝工程计算或推断，需后续验证；D＝未证实线索，只作线索。EAGLE 二进制没有“页码”，本文用 sheet 序号（从 1 起）加位号/网络定位；KiCad 用子图名加位号/网络定位。

---

### OSHW-18 Mutable Braids

- 领域：Eurorack 数字振荡器；16 位 SPI DAC 音频输出、12 位 SPI ADC 读 CV、±12 V 供电。
- 版本/提交：仓库 HEAD `f4cfa76970`；硬件文件最后修改 `61d7146`（2019-04-02）；本地 `braids_v50.sch/.brd` 与 GitHub master SHA-256 一致（A）。原理图版本号写在文件名 `v50`；未读到独立的标题栏 rev 字段。
- 许可证：硬件 CC BY-SA 3.0；STM32 代码 MIT、AVR 代码 GPL3（`repos/eurorack/README.md`，A）。
- 证据等级：A（元件、网络、坐标、层、宽度、提交/issue）；B（Sallen-Key、DAC 镜像、继电器/运放机理）；C（截止频率、增益、镜像抑制量等计算值）。
- 实际查阅：`repos/eurorack/braids_v50.sch` sheet 1（数字/MCU/ADC/DAC）、sheet 2（模拟 CV 与音频输出）、sheet 3（电源与基准）；`braids_v50.brd`（120 个 element、110 个 signal、3834 个 24 字节块）；`repos/eurorack/README.md`（许可证）与 `braids/README.md`（固件结构，经 GitHub 读取）；`braids/braids.cc:141`；`braids/drivers/dac.cc`；GitHub 提交 `af3d59d181ad`、`61d7146d9319`；issue #9。未读：BOM `Braids.xlsx`、面板图、实测波形。

**电路决定（一项）**

- 决定：DAC8551（IC5）的 0–2.5 V 单端输出先进入 2 阶单位增益 Sallen-Key 低通（R45/R46=39 k，C21/C22=100 p，IC10B TL072），再经 C24=10 µF 隔直、IC10A 反相放大约 −4.0（R50=24.9 k，R56=100 k，C29=47 p 反馈极点），最后经 R55=1 k 送到输出插孔 J6。也就是“先滤波、再隔直、再放大”的三段式输出链，而不是 DAC 直接接插孔或只用一个无源 RC。
- 位置证据：[A] `braids_v50.sch` sheet 1 网络 `AUDIO_OUT` 接 IC5.OUT 与 IC5.FB；`AREF` 接 IC5.VREF 与 IC4.VREF，并由 IC3（LM4040B25，2.5 V）经 R23=1 k 从 +3V3 建立。sheet 2 网络 `AUDIO_OUT` 接 R45 的一端；R45 另一端→`N$71`（R46、C21 的一端）；R46 另一端→`N$69`（IC10B 的 +IN、C22 的一端）；C22 另一端→GND；C21 另一端→`N$67`（IC10B 的 −IN、IC10B 的 OUT、C24.+）；C24.−→`N$68`→R50；R50 另一端→`N$75`（IC10A 的 −IN、R56 的一端、C29 的一端）；IC10A 的 OUT→`N$73`（C29 的另一端、R55 的一端）；R55 另一端→`N$72`（R56 的另一端、J6.3）。位号：IC5、IC10（A/B 两个 gate）、R45/R46/R50/R55/R56、C21/C22/C24/C29。[A] `braids_v50.brd` 中 IC5 在 (59.69, 56.20) mm、IC10 在 (52.70, 22.23) mm、J6 在 (72.39, 6.35) mm。
- 为什么这样做（机理）：[A] 固件把系统节拍设为 F_CPU/96000（`braids/braids.cc:141`），DAC 以 96 kHz 更新；DAC 输出频谱在 96 kHz−f 处有镜像，必须在下游抑制。[C] 按 R45=R46=39 k、C21=C22=100 p 计算，Sallen-Key 的 f0=1/(2πRC)≈40.8 kHz、Q=0.5（等 R 等 C、单位增益），在 96 kHz 处约 −16 dB；第二级反相放大器 R56/R50=100 k/24.9 k≈−4.0，反馈极点 1/(2π·100 k·47 p)≈33.9 kHz，在 96 kHz 再约 −9.5 dB；两级合计约 −26 dB。[C] DAC 满量程 2.5 V（AREF=2.5 V），C24 隔掉 1.25 V 直流，−4 增益把 2.5 Vpp 放大到约 10 Vpp，正好是 Eurorack 音频的常见电平；C24 与 R50 的高通转折约 0.64 Hz，不会削低频。[B] 这就是“有源 2 阶低通 + 隔直 + 增益”而不是单级无源 RC 的原因：单级 RC 在 96 kHz 只有约 −8 dB，且输出阻抗高、后级负载会改变截止频率。
- 迁移到其他项目必须保持的条件：[C] 滤波器 f0 必须低于目标采样率的 fs/2，并留出足够裕量；DAC 满量程、隔直电容、输入电阻与增益必须一起核算，保证目标输出电平且不削波；Sallen-Key 的反馈电容必须接在运放输出与 R45/R46 中点之间，不能接到虚地；第二级反馈极点要留在运放本地，R55 串阻放在插孔端。若换 24 位 DAC 或改变采样率，39 k/100 p 与 −4 增益都要重算。
- 不应照搬的部分：[C] 不要在没有核算 DAC 满量程和目标电平时照搬 39 k/100 p 与 −4 增益；这套链是单端、隔直、交流耦合，不能直接用于需要 DC 耦合的 CV 输出；也不要因为“DAC 后面有运放”就省掉 AREF 的基准去耦（本板 AREF 由 LM4040B25 + C8=470 n 提供，且同时供 ADC 与 DAC）。

**PCB 决定（一项）**

- 决定：2 层板，Top/Bottom 双面 GND 铺铜并用 230 个过孔缝合；电源 VCC/VEE 主要用 0.4064 mm 走线，信号与音频用 0.254 mm；板框 78.72×106.68 mm。
- 位置证据：[A] `braids_v50.brd`：铜层只有 layer 1（Top）和 layer 16（Bottom）有走线（Top 1288 段、Bottom 184 段）；GND 信号在 layer 1/16 各 1 个 polygon，GND 焊盘连接 80 个；VCC 32 段 0.4064 mm（另 1 段 0.254 mm）、VEE 32 段 0.4064 mm、+3V3 101 段 0.4064 mm/54 段 0.254 mm；`AUDIO_OUT` 18 段全为 0.254 mm；过孔 230 个；Dimension 层板框 x 0–787.2、y 0–1066.8（0.1 µm 单位）。IC5 在 (59.69, 56.20) mm，IC10 在 (52.70, 22.23) mm，J6 在 (72.39, 6.35) mm。
- 为什么：[B] 2 层板没有专用地平面，双面铺铜加缝合过孔给 Top 走线提供连续回流路径，降低地阻抗和环路面积；电源加宽到 0.4064 mm 是按电流/压降和机械 robustness 留的余量；音频 0.254 mm 是常规信号宽度，不是阻抗控制线。[C] 230 个过孔相对 78.72×106.68 mm 的板面积约 2.7 个/cm²，属于“铺铜缝合”而不是“大量散热过孔”。
- 迁移条件：[B] 铺铜必须在 DAC、运放、SPI 走线下方连续，不能被长距离走线或挖槽切断；过孔要靠近层切换、连接器和晶振地；模拟与数字回流不要被迫挤过同一条窄颈。若改成 4 层，应把完整地平面放在第 2 层，而不是继续依赖双面铺铜。
- 不应照搬的部分：[C] 不要把 2 层共享 GND 当成精密模拟地：本板是成本敏感的 Eurorack 模块，数字回流与模拟回流共用铺铜；高分辨率、低噪声设计应评估 4 层、独立模拟地与单点连接。也不要照搬 0.254 mm 音频走线用于长距离、高容性负载或大电流。

**调试、制造或可维护性考虑（一项）**

- 事实：板上同时提供 SW3 `BOOT_FLASH`（BOOT0 经 R33=10 k 切换/下拉）、SW2 `RESET`（NRST 经 R22=10 k 上拉）、JP2 10 针 JTAG/SWD（M05X2）、JP3 6 针 UART（RX/TX 及 +3V3/GND）。
- 证据：[A] `braids_v50.sch` sheet 1 网络 `BOOT_FLASH`（SW3.P/SW3.P1、R33.2、UC1.BOOT0）、`RESET`（UC1.NRST、SW2.S/SW2.S1、R22.1、JP2.10）、`JTDI/JTDO/JTCK/JTMS`（JP2.8/6/4/2 与 UC1.PA15/PB3/PA14/PA13）、`RX/TX`（UC1.PA10/PA9 与 JP3.4/JP3.5）；位号 SW2、SW3、JP2、JP3、R22、R33。[A] `braids_v50.brd` 中 JP2 为 10 针、JP3 为 6 针通孔。
- 对 Agent 的启示：审图/改板时先确认“可恢复性三件套”——BOOT 选择、复位、调试/串口——是否都能从板外到达；量产后固件损坏能否不拆焊恢复。Braids 把 BOOT0 和 NRST 都做成按键/跳线，并同时留 JTAG 与 UART，这是比“只留 SWD 四针”更宽裕的维修设计；代价是面板/结构上要留出按键和排针开口。

**版本迭代/修板历史**

- 找到的记录（作者确认）：[A] 提交 `af3d59d181ad`（2015-11-14，“New PCB versions”）一次性加入 `braids_v50.sch/.brd`、`clouds_v30.sch/.brd`、`edges_v20.sch/.brd`；提交 `61d7146d9319`（2019-04-02，“Updated name on schematics and PCBs”）修改丝印/名称。之后没有硬件文件修改记录。[A] issue #9（2016-11-15）：用户报告 R39 标 120 k 时，COARSE 旋钮打到最大只有约 2.07 V 到 ADC，认为应为 100 k；作者回复“Not an issue”，R39=120 k 是正确值，100 k 会在 COARSE 满度时到 2.5 V，模块就无法再响应正的 V/O 输入；120 k 留出了约一个八度加纯五度的正向移调余量。位号 R39 在 sheet 2 的 PITCH_CV 缩放网络。
- 证据位置：上述两个 commit；issue #9 正文与作者回复；`braids_v50.sch` sheet 2 的 R39（120 k）、R54（100 k）、R53（24.9 k）网络。
- 仍未证实：v40→v50 的具体改动没有公开记录；是否有过飞线/返修、R39 是否在某批 BOM 中改过，资料不足，不能判断。[C] issue #9 的“2.07 V”是用户实测口径，作者只做了定性解释，未给出完整电压/码值复算。

**开放问题**

- DAC8551 符号把 `OUT` 与 `FB` 画成两个引脚，而 DAC8551 数据手册的 8 脚定义需要逐脚核对；本符号可能把外部缓冲/反馈合并绘制，不能仅凭符号名判断“DAC 内部有 FB 引脚”。[C]
- Sallen-Key 的实际 f0/Q、输出噪声、THD、96 kHz 镜像抑制量都未实测；40.8 kHz/Q=0.5 是计算值。[C]
- R39=120 k 的“一个八度+纯五度”是作者口径，未按 MCP3204 的 2.5 V 基准和运放增益复算。[C]
- 早期硬件版本（v40 及以前）的差异、BOM 与原理图是否完全一致，资料不足。

---

### OSHW-19 Mutable Clouds

- 领域：Eurorack 纹理合成器；WM8731 立体声 codec、STM32F405 I2S 全双工音频、多路 CV/旋钮（STM32 ADC）、±12 V 供电。
- 版本/提交：仓库 HEAD `f4cfa76970`；硬件文件最后修改 `61d7146`（2019-04-02）；本地 `clouds_v30.sch/.brd` 与 GitHub master SHA-256 一致（A）。
- 许可证：硬件 CC BY-SA 3.0；STM32 代码 MIT（`repos/eurorack/README.md`，A）。
- 证据等级：A（元件、网络、坐标、层、宽度、提交/issue、固件源码）；B（I2S/I2C 接口机理、LDO 供电机理）；C（模拟增益、电源压降等计算/推断）。
- 实际查阅：`repos/eurorack/clouds_v30.sch` sheet 1（数字/MCU/codec）、sheet 2（模拟输入输出）、sheet 3（UI/LED/开关）、sheet 4（电源与基准）；`clouds_v30.brd`（156 个 element、107 个 signal）；`clouds/clouds.cc:114-115`、`clouds/drivers/codec.cc:97,278-286,340-367`、`clouds/drivers/version.h`（PB0 版本脚）；GitHub 提交 `af3d59d181ad`、`61d7146d9319`；issue #1。未读：BOM xlsx、面板图、实测音频指标。

**电路决定（一项）**

- 决定：WM8731（IC8）作为 I2S 主设备：它用 12.288 MHz 晶振 Q4（接 IC8.XTI/XTO）产生音频时钟；STM32F405（IC5）的 I2S2 设为 SlaveTx、I2S2_ext 设为从 RX，BCLK/LRCK 由 codec 驱动，DACLRC/ADCLRC 在 codec 端短接；DACDAT/ADCDAT 分别接 `I2S_SOUT`/`I2S_SIN`；控制走 I2C2（100 kHz，地址 0x1A），CSB 与 MODE 接地。
- 位置证据：[A] `clouds_v30.sch` sheet 1 网络：`I2S_SCK` 接 IC5.PB13/SPI2_SCK/I2S2_SCK 与 IC8.BCLK；`I2S_LRCK` 接 IC5.PB12/SPI2_NSS/I2S2_WS 与 IC8.DACLRC、IC8.ADCLRC；`I2S_SOUT` 接 IC5.PB15/SPI2_MOSI/I2S2_SD 与 IC8.DACDAT；`I2S_SIN` 接 IC5.PB14/SPI2_MISO 与 IC8.ADCDAT；`I2C_SCL` 接 IC5.PB10/I2C2_SCL、IC8.SCLK、R40（2.2 k 上拉）；`I2C_SDA` 接 IC5.PB11/I2C2_SDA、IC8.SDIN、R41（2.2 k 上拉）；GND 网络包含 IC8.CSB、IC8.MODE 和 IC5.PB0（硬件版本脚，接地）。Q4（12.288 MHz）两端接 `N$59`/`N$60`，即 IC8.XTO/IC8.XTI-MCLK，C47/C48=18 p 为负载电容。[A] `clouds/clouds.cc:114-115`：`bool master = !version.revised();`，随后 `codec.Init(master, 32000)`；`version.revised()` 读 PB0，PB0 低时为 true，所以本板 `master=false`（codec 为主）。[A] `clouds/drivers/codec.cc`：`CODEC_ADDRESS` 由 `W8731_ADDR_0`（0x1A）左移得到（第 97 行）；`InitializeAudioInterface` 在 `mcu_is_master=false` 时配置 `I2S_Mode_SlaveTx`、`I2S_MCLKOutput_Disable`，并用 `I2S_FullDuplexConfig` 配置扩展 RX（第 278–286 行）；`format_byte = CODEC_PROTOCOL_MASK_PHILIPS | CODEC_FORMAT_MASK_16_BIT`，`mcu_is_master=false` 时 codec 设为 `CODEC_FORMAT_MASTER`（第 340–343 行）；采样率参数为 32000，codec 侧对应 `CODEC_RATE_32K_32K`（第 345–367 行）。
- 为什么这样做（机理）：[B] 12.288 MHz 正好是 32 kHz 的 384 倍（也是 48 kHz 的 256 倍），codec 用这颗晶振直接产生低抖动的 BCLK/LRCK；STM32 作为 I2S 从设备只负责按外部时钟收发数据，避免 PLLI2S 的时钟抖动和额外的 MCLK 分配。[B] 单个 BCLK/LRCK 对同时给 ADC 和 DAC 提供字时钟，录音与回放处在同一采样时刻，不会出现两个时钟域的漂移或周期性滑码；16 位 Philips 格式与 STM32 I2S 数据寄存器/DMA 字宽匹配，减少打包/拆包；I2C 只用于上电配置，不参与音频数据，因此 100 kHz 的慢速总线不会影响音频时序。[C] 若 codec 与 MCU 各自为主，或 ADC/DAC 使用不同 LRCK，两个方向会出现采样率偏差和拍频，这是本设计要避免的。
- 迁移到其他项目必须保持的条件：[B] codec 必须支持主模式并有可用的晶振/时钟源；BCLK/LRCK 比例、字长（16 位）和帧格式（Philips）必须与 MCU 的 I2S 从模式配置一致；I2C 上拉、地址 strap（CSB/MODE）必须与器件手册一致；PB0 这类硬件版本脚的接法必须与固件的 `version.revised()` 逻辑匹配；两个方向共用同一采样率时才能这样短接 LRCK。若换 24 位 codec 或需要独立 ADC/DAC 采样率，必须改成两条 I2S 或 TDM。
- 不应照搬的部分：[C] 不要因为本板把 DACLRC/ADCLRC 短接，就在所有 codec 上照做；有些 codec 的 ADC 与 DAC 可以独立选率，短接会限制功能。也不要照搬 16 位/32 kHz 用于 24 位/高采样率音频链；更不要把 PB0 版本脚直接接地而不核对固件的 master/slave 分支——同一份 Clouds 固件在 PB0 为高时会走 MCU 主模式，时钟方向相反。

**PCB 决定（一项）**

- 决定：数字 3.3 V 与模拟 3.3 V_A 由两颗独立 LM1117-3.3 产生并分区布置：数字稳压器 IC2 在板右下（约 29.8, 85.4 mm），模拟稳压器 IC7 在板中（约 44.8, 43.2 mm），y 方向相差约 42 mm（直线约 45 mm）；数字稳压器输入经 R11=4.7 Ω + C2=47 µF，模拟稳压器从 VCC 直接取电并用 C1=47 µF；`+3V3_A` 只覆盖 codec 的 AVDD/HPVDD、MCU 的 VDDA 和模拟运放。
- 位置证据：[A] `clouds_v30.sch` sheet 4：`VCC`→R11.1，R11.2→`N$55`（IC2.VIN、C2.+）；IC2.VOUT→`+3V3`；IC7.VIN 直接接 `VCC`，IC7.VOUT→`+3V3_A`；C1 在 IC7 输入、C27/C26 在输出。sheet 1 `+3V3_A` 接 IC5.VDDA、IC8.HPVDD、IC8.AVDD、C12/C14/C31/C49/C32；`+3V3` 接 IC8.DBVDD/DCVDD、IC5.VDD_1..4。sheet 2 `+3V3_A` 接 IC4.V+、IC3.V+、C23/C15。[A] `clouds_v30.brd`：IC2 在 (29.84, 85.41) mm，IC7 在 (44.77, 43.18) mm，IC8 在 (66.04, 40.64) mm；`+3V3_A` 74 段、`+3V3` 119 段；GND 在 layer 1/16 各 1 个 polygon，过孔 148 个；板框 88.90×106.05 mm。
- 为什么：[B] 把数字稳压器与模拟稳压器分成两颗、并在数字支路串 R11/C2，可让 MCU 的开关电流在 R11 上形成压降/滤波，不直接污染 VCC 节点上的模拟稳压器输入；模拟 rail 单独走线到 codec 的 AVDD/HPVDD 和运放 V+，减少数字回流在模拟供电上的耦合。[C] R11=4.7 Ω 的压降取决于数字 3.3 V 负载电流：若负载 100 mA，压降约 0.47 V，LM1117 从 12 V 输入仍有充足裕量；若负载更大，需重新核算 dropout 和 R11 功耗。
- 迁移条件：[B] 保持两颗稳压器、两条 rail 不在板上直接短接；模拟 rail 的走线要伴随自己的回流（codec AGND/HPGND 回到模拟地），数字 rail 的回路不要穿过 codec 下方；R11/C2 的 RC 要按数字负载电流和允许压降选。若换低噪声 LDO，仍要保留 rail 分区，不能只换器件。
- 不应照搬的部分：[C] 不要照搬 2 层共享 GND；24 位 codec 的 AVDD 噪声和串扰要求更高，应评估 4 层、独立模拟地。也不要照搬 R11=4.7 Ω 而不算压降；更不要把 `+3V3_A` 当成“绝对干净”的模拟电源，它仍是 LM1117 从 +12 V 降下来的线性电源，PSRR 随频率下降。

**调试、制造或可维护性考虑（一项）**

- 事实：codec 没有硬件复位/静音跳线；CSB 与 MODE 硬接 GND，I2C 地址固定为 0x1A；codec 的上电配置完全依赖 MCU 通过 I2C 写入（`codec.cc` 先写 `CODEC_REG_RESET`，再写 line in、routing、power、format、rate 等寄存器）。板上没有第二路 I2C 地址选择或 codec 旁路。
- 证据：[A] `clouds_v30.sch` sheet 1 GND 网络包含 IC8.CSB、IC8.MODE；`I2C_SCL/I2C_SDA` 只到 IC5、IC8、R40/R41；[A] `clouds/drivers/codec.cc:320-343` 的初始化顺序；[A] `clouds_v30.brd` 中 IC8 周围没有地址/复位跳线。
- 对 Agent 的启示：音频 bring-up 的顺序应是“先确认 I2C ACK（0x1A）→ 再确认 BCLK/LRCK 存在且频率正确 → 最后查模拟链路”，而不是先换运放/查焊点。派生设计若需要多 codec 或硬件静音，必须加地址 strap/复位跳线或 mute 开关；否则 I2C 一旦不通，模拟通路没有已知的硬件默认状态。

**版本迭代/修板历史**

- 找到的记录（作者确认）：[A] 提交 `af3d59d181ad`（2015-11-14）加入 `clouds_v30.sch/.brd`；`61d7146d9319`（2019-04-02）改名/丝印。[A] issue #1（2016-03-23）：用户指出 Clouds/Elements/Rings/Warps 的 BOM 把 STM32F405RGT6 标成 TQFP64，实际应为 LQFP64；作者回复“It's a typo”。这是 BOM 文档修正，不是 PCB 改板。[A] 固件 `clouds/drivers/version.h` 用 PB0 读硬件版本，`clouds/clouds.cc:114-115` 用 `master = !version.revised()` 决定 I2S 主从；本板 PB0 接地，所以走 codec 主模式。这说明作者在固件里保留了两版时钟方向的兼容分支，是硬件版本差异的直接证据；但旧版板的具体 PB0 接法和晶振装配未在本地文件中读到（B/C）。
- 证据位置：上述 commit；issue #1 正文与作者回复；`clouds_v30.sch` sheet 1 IC5 的封装/型号、PB0 的 GND 连接、Q4 12.288 MHz 晶振；`clouds/clouds.cc:114-115`、`clouds/drivers/version.h`。
- 仍未证实：v1/v2→v30 的硬件改动没有公开记录；旧版是否 PB0 高、是否不装 Q4/由 MCU 主模式，需要旧版原理图或实物确认；是否有过模拟/电源修板、codec 配置变更，资料不足，不能判断。[C] issue #72（2026-09-26）是 Clouds 固件 STRETCH 模式的软件问题，不是硬件修板，不能拿来当硬件版本证据。

**开放问题**

- 本板 PB0 接地，`clouds.cc:114-115` 确认走 `master=false`（codec 主模式）、32 kHz；其他 Clouds 硬件版本若 PB0 为高，固件会走 MCU 主模式，时钟方向相反。那些版本的晶振是否装配、BCLK/LRCK 由谁驱动，需要按具体版本核对，不能把本板的 codec 主模式套过去。[C]
- 模拟输入/输出级的实际增益与电平未实测：输入 R57/R58=22 k、R46/R47=3.3 k（约 −0.15），输出 R49/R51=39 k/5.6 k（约 −7），但 codec 满量程、R59/R50 的 39 k 对地负载和实际听感电平需要测量。[C]
- `+3V3_A` 的负载电流、IC7 结温、R11 压降与数字负载的关系未实测。[C]
- WM8731 的 CSB/MODE 接法对应的 I2C 地址/模式需要逐页核对数据手册；本文只按固件 `W8731_ADDR_0=0x1A` 和网络连接推断。[C]

---

### OSHW-20 Mutable Edges

- 领域：Eurorack 四通道 chiptune 数字振荡器；ATXMEGA32A4U、MCP4822 双 12 位 DAC、MCP3208 8 通道 ADC、74AHC1G86/1G125 逻辑输出。
- 版本/提交：仓库 HEAD `f4cfa76970`；硬件文件最后修改 `61d7146`（2019-04-02）；本地 `edges_v20.sch/.brd` 与 GitHub master SHA-256 一致（A）。
- 许可证：硬件 CC BY-SA 3.0；AVR 代码 GPL3（`repos/eurorack/README.md`，A）。
- 证据等级：A（元件、网络、坐标、层、宽度、提交/issue、固件源码）；B（DAC 输出/AC 耦合/逻辑门机理）；C（增益、转折频率等计算值）。
- 实际查阅：`repos/eurorack/edges_v20.sch` sheet 1（MCU/DAC/ADC/门电路/接口）、sheet 2（CV 与音频输出模拟）、sheet 3（电源与基准）；`edges_v20.brd`（179 个 element、118 个 signal）；`edges/hardware_config.h:72-98`；GitHub 提交 `af3d59d181ad`、`61d7146d9319`；issue #8。未读：BOM `Edges.xlsx`、面板图、实测输出波形。

**电路决定（一项）**

- 决定：四个通道采用混合输出架构——通道 4 用 MCP4822 的 OUTA 产生模拟三角波，经 C28=10 µF 隔直、R60=10 k 输入、IC9 反相放大（R54=82 k 反馈、R49=1 k 串出）送到 J16.3；通道 1 用 74AHC1G125 缓冲 MCU 的 PD0，通道 2/3 用 74AHC1G86 XOR 把 MCU 的 PC4/PC0 与面板开关 SW2/SW3 组合后输出。也就是“方波走数字门、三角波走 DAC+运放”，而不是四通道都用 DAC 或都用 PWM。
- 位置证据：[A] `edges_v20.sch` sheet 1：`CHANNEL4` 接 IC15.OUTA（MCP4822）；`CHANNEL1` 接 IC5.O（74AHC1G125，输入 `N$48` 来自 IC16.PD0）；`CHANNEL2` 接 IC6.O（74AHC1G86，I0=`N$19` 来自 IC16.PC4，I1=SW2.P）；`CHANNEL3` 接 IC8.O（74AHC1G86，I0=`N$41` 来自 IC16.PC0，I1=SW3.P）。sheet 2：`CHANNEL4` 接 C28.+；C28.−→`N$32`→R60.1；R60.2→`N$33`（R54.1、IC9.−IN）；IC9.OUT→`N$34`→R49.1；`CHANNEL4_BUFFERED` 接 R54.2、R49.2、J16.3。位号：IC15、IC9、IC5、IC6、IC8、C28、R60、R54、R49。
- 为什么这样做（机理）：[B] MCP4822 是单电源、内部 2.048 V 基准的 12 位 DAC（增益位可 1×/2×，本板实际配置未核对），输出带约 1.024 V（1× 时）直流偏置；C28 隔直去掉偏置，R60/R54 反相放大 [C] −82 k/10 k≈−8.2，把 DAC 的约 2 Vpp 放大到约 16 Vpp 的满摆幅（实际三角波可能只用部分码值，约 8–10 Vpp）；R49=1 k 串在运放输出与插孔之间，隔离电缆电容、限制短路电流。[B] 方波通道不需要 DAC：74AHC1G125 提供三态缓冲/驱动，74AHC1G86 XOR 用面板开关实现反相/相位组合，边沿由 MCU 定时器和逻辑门决定，比“DAC 采样再比较”更简单、抖动更低。
- 迁移到其他项目必须保持的条件：[C] C28 与 R60 的高通转折 1/(2π·10 µF·10 k)≈1.6 Hz，必须低于最低音频；R54/R60 的增益要按 DAC 满量程和目标输出电平重算；R49 串阻要放在运放输出与连接器之间，反馈 R54 从串阻之后取，才能把电缆电容与反馈环隔开；数字通道要保证逻辑门供电与 MCU 电平匹配（本板 3.3 V AHC）。
- 不应照搬的部分：[C] 不要把这套 AC 耦合输出用于 CV 通道；不要把 −8.2 增益直接套到 0–5 V DAC（会削顶）；也不要在需要极低抖动的音频方波上随意换慢速逻辑族——AHC 的边沿和传输延迟是这套设计的一部分。

**PCB 决定（一项）**

- 决定：四个通道的输出缓冲/串阻就近各自的输出插孔放置，而不是集中到板中：IC2 距 J4 约 9.8 mm、IC7 距 J8 约 9.8 mm、IC9 距 J12 约 9.6 mm、DAC IC15 距 J16 约 13.9 mm；板框 97.77×102.87 mm，2 层，GND 双面铺铜，174 个过孔。
- 位置证据：[A] `edges_v20.brd`：IC2 (76.20, 82.87) mm、J4 (75.88, 92.71) mm；IC7 (76.20, 62.55) mm、J8 (75.88, 72.39) mm；IC9 (78.11, 42.55) mm、J12 (75.88, 52.07) mm；IC15 (80.64, 18.73) mm、J16 (75.88, 31.75) mm；GND 在 layer 1/16 各 1 个 polygon；DAC_SS 网络有 0.1016/0.1143/0.254 mm 的细走线，电源 +3V3 有 0.4064 mm/0.254 mm 两种宽度。
- 为什么：[B] 输出级的高电平节点和反馈节点对寄生电容/串扰敏感，把运放放在插孔附近可以缩短输出走线、减小被邻近数字线拾取的机会；每个通道的反馈网络留在运放本地，串阻放在插孔端，返回电流就近流回地。[C] 四路输出如果集中到板中再拉长线到插孔，会增加通道间串扰和电缆负载效应；本板用“每路一个本地运放”换布局面积。
- 迁移条件：[B] 保持“运放—反馈—串阻—插孔”四者本地化；输出走线不要回穿输入/CV 区域；每路的地回流要连续，避免共用一段高阻抗地。若换更高输出电流或更低负载，R49 的 1 k 会限制摆幅，需要重算。
- 不应照搬的部分：[C] 不要照搬 2 层板的长 CV 走线；Edges 的 8 路模拟输入（CH1–CH8）在 Top 层跨越较大区域，若做高精度 CV 或低串扰多通道，应评估 4 层与地屏蔽。也不要照搬 DAC_SS 的 0.1 mm 细走线用于长距离或大电流。

**调试、制造或可维护性考虑（一项）**

- 事实：固件用编译期宏 `OCTAL_ADC` 选择 ADC 通道数——定义时 `kNumAdcChannels=8`，不定义时 4；v20 板使用 MCP3208（8 通道），早期板使用 MCP3204（4 通道）并在软件里混合 CV 输入与频率电位器。作者在 issue #8 明确说“这取决于你装的是哪一版板”。
- 证据：[A] `edges/hardware_config.h:95-98`；[A] `edges_v20.sch` sheet 1 IC13 为 MCP3208，CH1–CH8 与 IC13.CH0–CH7 的对应不是顺序直连：CH1→CH0、CH2→CH1、CH3→CH4、CH4→CH5、CH5→CH2、CH6→CH3、CH7→CH6、CH8→CH7（按网络名核对）；[A] issue #8（2016-10-22 提出，作者 2016-10-25 回复）：早期 revision 用 quad ADC MCP3204，并在软件中混合 CV 输入和频率电位器；`EXTRA_DEFINES=-DOCTAL_ADC` 被注释掉会阻止通道 3/4 的 CV 与音高控制。
- 对 Agent 的启示：调试“某两路 CV/音高没反应”时，先核对固件编译宏与板上的 ADC 型号/通道数，再怀疑模拟前端；同一份源码不一定同时适配两版板。还要注意 CH1–CH8 与 MCP3208 CH0–CH7 的映射是交换的（例如 CH3→CH4、CH5→CH2），不能按“顺序直连”假设通道号；应按网表/固件通道表逐路核对。派生设计应把板版本写进 BOM/丝印，并在固件启动时读版本电阻或至少打印配置，避免“烧错宏”被误判为硬件故障。

**版本迭代/修板历史**

- 找到的记录（作者确认）：[A] issue #8（2016-10-22 提出，作者 2016-10-25 回复）确认存在两版 ADC 方案：早期四通道 MCP3204 + 软件混合，后期八通道 MCP3208；`OCTAL_ADC` 宏按板选择。[A] 提交 `af3d59d181ad`（2015-11-14）加入 `edges_v20.sch/.brd` 和 `edges_expander_v01.sch/.brd`；`61d7146d9319`（2019-04-02）改名/丝印并同时修改 expander。
- 证据位置：issue #8；`edges/hardware_config.h:95-98`；两个 commit 的文件列表；`edges_v20.sch` sheet 1 IC13=MCP3208。
- 仍未证实：早期板的正式 rev 号、MCP3204→MCP3208 之外是否还有模拟/电源改动、expander v01 与主板的配合方式，资料不足，不能判断。

**开放问题**

- MCP4822 的实际基准/增益配置（内部 2.048 V 还是外部基准）、通道 4 的输出幅度与 THD，未实测。[C]
- IC9 反馈网络的完整拓扑（R54/R49/R60 与 C 补偿）需要按运放稳定性复算；本文只按直流增益和 AC 耦合解释。[C]
- ATXMEGA32A4U 的引脚与原理图符号是否逐脚一致，未对照数据手册；`hardware_config.h` 的端口映射可作为交叉检查，但未做。[C]
- 早期 MCP3204 版本的板号/年份、两版板的机械/连接器差异，资料不足。

---

### OSHW-21 EEZ BB3 AUX-PS

- 领域：台式电源/测试仪器机箱的辅助电源板；AC 输入保护、软启动、隔离 AC/DC +5 V/+12 V、风扇控制、待机指示。
- 版本/提交：本地根图标题栏 `EEZ DIB AUX-PS`、`rev r3B7`、日期 `2024-01-02`；研究台账记录 `c3d30a6210`；本地 `aux-ps.kicad_sch/.kicad_pcb` 与 GitHub master SHA-256 一致（A）；KiCad 迁移提交 `3b2ae13a8081`（2024-01-02）。
- 许可证：TAPR Open Hardware License 1.0（`repos/eez/LICENSE.TXT`，A）；OSHWA UID HR000002（README，A）。
- 证据等级：A（元件、网络、坐标、层、宽度、提交/issue、标题栏）；B（NTC/继电器/隔离模块/EMI 机理）；C（定时、温升、压降、蠕电距离等未测量项）。
- 实际查阅：本地 `repos/eez/aux-ps.kicad_sch`（根图，2 个层次子图、连接器、安装孔、logo）、`aux-ps.kicad_pcb`（101 个 footprint、完整 net/pad/segment/zone）；本地 `README.md`、`LICENSE.TXT`；GitHub master 的 `aux-ps/EDA files/KiCad/ac_input_sstart_bias.kicad_sch`、`fan_controller.kicad_sch`；issue #83、#108、#23；提交 `3da39c578dc5`、`75d51457c595`、`b38fe93cc1f3`、`285dd1fb3210`、`3b2ae13a8081`。未读：BOM `1-click-bom.csv`、KiCad PDF 原理图、CE/LVD 证书、实物。

**电路决定（一项）**

- 决定：AC 输入软启动采用“NTC 串联 + 继电器旁路”，不再使用 r3B3 的 triac/opto-triac 方案。NTC1（B57236S0200M）串在 `AC_L_OUT` 与 K1 的 P 触点之间，K1 的 O 触点接 `AC_L_SS`；K2 的 P 触点直接接 `AC_L_OUT`、O 触点接 `AC_L_SS`，提供“直接/旁路”路径。K1/K2 为 ALQ105（5 V 线圈），分别由 Q1/Q2（MMBT5551）低边驱动，基极经 R3/R4=1 k 接 `PWR_SSTART`/`PWR_DIRECT`；D3/D4/ZD1 组成线圈的钳位/续流网络。SW1 为双极开关，同时切 L 与 N；TR1（IRM-10-5）、TR2（IRM-10-12）为隔离 AC/DC 模块，二次侧 +5 V/+12 V 以 GND 为参考；`AC_L_OUT`/`AC_N_OUT` 还经 X2/X3 送到下游功率模块，仍是市电输出，不是安全低压。
- 位置证据：[A] `aux-ps.kicad_pcb`：NTC1 pad1=`AC_L_OUT`、pad2=`Net-(K1-PadP)`；K1 P=`Net-(K1-PadP)`、O=`/AC input, soft start and bias power/AC_L_SS`、C1=`+5V`、C2=`Net-(D3-PadA)`；K2 P=`AC_L_OUT`、O=`AC_L_SS`、C1=`+5V`、C2=`PWR_DIR_OUT`；Q1 B=`Net-(Q1-PadB)`、C=`Net-(D3-PadA)`、E=GND；Q2 B=`Net-(Q2-PadB)`、C=`PWR_DIR_OUT`、E=GND；R3/R4 分别从 `PWR_SSTART`/`PWR_DIRECT` 到 Q1/Q2 基极；SW1 pad1/1A 与 pad2/2A 分别切 N/L；TR1/TR2 的 ACL/ACN 接 `AC_L_OUT`/`AC_N_OUT`，V+ 分别经 L1/L2（VLS6045AF-3R3N）到 `+5V`/`+12V`，V−=GND。[A] 原理图子图 `ac_input_sstart_bias.kicad_sch` 中 NTC1、K1/K2、Q1/Q2、R3/R4、D3/D4/ZD1、TR1/TR2 的位号与上述网络一致。
- 为什么这样做（机理）：[A] 作者在 issue #108 明确记录：r3B3 的 R4 是 opto-triac 的限流电阻；与 Mean Well LRS 的 F 型（全电压/自动切换）模块组合时，即使空载，opto-triac 也会被异常驱动，R4 在连续通电数天后过热甚至烧断；加 1 µF X2 + 47 Ω RC snubber 可缓解，但根本方案是换掉 triac。[A] issue #83 记录 CE 测试时的改动：由于 Mean Well IRM 与 LRS 组合的传导发射，AC 输入要加 DM/CM 滤波；把 triac 换成继电器（与 BP3C 同型号）；去掉 RC snubber；SAR 改贴片；去掉 TVS；增加第三只 MOV（L-N）。[B] 新方案的机理是：冷机时先吸合 K1，NTC 串入 L 线，限制 X2 电容和 IRM 模块输入电容的浪涌；延时后吸合 K2，K2 的 P–O 直接把 `AC_L_OUT` 接到 `AC_L_SS`，旁路 NTC；K1 可在 K2 吸合后释放。继电器线圈由 +5 V 供电、Q1/Q2 低边开关，线圈电流连续但远小于 triac 限流电阻的耗散。[C] 若 K2 在上电瞬间就吸合（或触点粘连），NTC 被直接旁路，浪涌不受限；若 K1 未吸合而 K2 吸合，同样没有软启动。失电时 K1/K2 均断开，负载失电；K2 触点粘连是需要注意的失效模式。因此 K1/K2 的吸合顺序必须由 `PWR_SSTART`/`PWR_DIRECT` 的固件时序保证。
- 迁移到其他项目必须保持的条件：[B] 继电器必须在 +5 V 稳定后按“先 K1（NTC）、后 K2（直接旁路）”的顺序吸合；NTC 的冷阻/稳态电流/重复浪涌能力要按负载电容和输入电压选；继电器触点额定（电压/电流/浪涌）要覆盖下游模块；线圈必须有续流/钳位；K2 不能在上电瞬间就吸合，否则 NTC 被直接旁路、浪涌不受限。若下游是纯阻性小负载，可以简化；若负载电容更大，必须重新核算 NTC 能量。
- 不应照搬的部分：[C] 不要照搬 r3B3 的 triac+opto-triac+R4 方案——作者已经用 issue #108 证明它在某些 AC/DC 模块组合下会过热；也不要把 NTC 软启动用在需要频繁开关、或稳态电流接近 NTC 额定值的场合而不加旁路。继电器的机械寿命、线圈功耗和吸合抖动都要按目标产品核算，不能因为“本板用了继电器”就默认通用。

**PCB 决定（一项）**

- 决定：230.5×60 mm、2 层板；市电走线 2.032–2.184 mm、PE 2.54 mm，二次侧 +12 V/+5 V 1.524 mm，逻辑 0.254 mm；GND 铺铜只放在二次侧局部（B.Cu 约 x 73.8–114.2 mm、y 74.2–122.3 mm；F.Cu 约 x 73.8–91.8 mm、y 83.3–104.8 mm），市电功率区（X2/X3、K1/K2、VAR1-3、SAR1、NTC1 附近，约 x>185 mm）没有 GND 铺铜，风扇/连接器区也靠走线回流而不是铺铜；IRM-10 模块跨在隔离边界上。
- 位置证据：[A] `aux-ps.kicad_pcb`：板框 x 33.25–263.75 mm、y 75.00–135.00 mm（230.5×60 mm）；GND zone 的 B.Cu polygon 包围盒 (73.8, 74.2)–(114.2, 122.3) mm，F.Cu GND zone (73.8, 83.3)–(91.8, 104.8) mm；`AC_L_OUT` 还有一块 F.Cu zone（约 165.3–168.7 mm）；`AC_L_IN` 走线 7 段 2.032 mm、`AC_N_IN` 17 段 2.032 mm、`AC_L_SS` 5 段 2.1844 mm、PE 5 段 2.54 mm；`+12V` 9 段 1.524 mm、`+5V` 6 段 1.524 mm；`+3V3` 24 段 0.254 mm；IRM 模块 TR1 在 (172.9, 104.5) mm、TR2 在 (149.5, 76.2) mm；IEC  inlet J4 在 (263.75, 105.0) mm，AC 输出连接器 X2/X3 在 x≈221/234 mm。
- 为什么：[B] 市电区与二次侧分区、二次侧 GND 只做局部铺铜，可避免把市电浪涌/共模噪声直接耦合到二次地；IRM-10 模块本身提供隔离，但 PCB 仍要保证市电区与二次区的爬电/电气间隙。加宽市电走线是按电流、浪涌和机械 robustness 留余量；PE 2.54 mm 是安全地路径。二次侧 +12/+5 V 用 1.524 mm，逻辑 0.254 mm，是按负载电流和压降分级。[C] 230.5×60 mm 与 README 的“230.5×60 mm, 2-layer PCB”一致，说明这是面板/机箱尺寸约束下的长条形布局，不是按最小板面积优化。
- 迁移条件：[B] 必须按目标安规（如 IEC 62368-1/60950）重新核算市电—二次的爬电/电气间隙，不能只用“模块有隔离”代替；市电区不要铺 GND，不要在市电—二次边界放测试点/过孔；Y 电容的返回路径要短；PE 要独立、低阻抗。若换非隔离 AC/DC（如 buck 直接从市电取电），整个分区和间距都要重做。
- 不应照搬的部分：[C] 不要照搬“2 mm 走线”当作爬电距离——走线宽度不等于间距；也不要把局部 GND 铺铜当成“隔离屏障”，隔离主要靠 IRM 模块和板级间距。不要在没有 CE/安规复核的情况下照搬 230 V 输入部分的元件与间距。

**调试、制造或可维护性考虑（一项）**

- 事实：板上有 5 个测试点（TP1=`+5V`、TP2=`+12V`、TP3=GND、TP4=`PWR_DIRECT`、TP5=`PWR_SSTART`）和 4 个可切割/可选焊跳线（JP1 设 MAX31760 的 A0/I2C 地址，JP2 选风扇供电 `12V_PWM` 或 `+12V`，JP3 风扇电压微调，JP4 风扇回路线）；16 针 DIB 连接器 X1 把 +12 V、+5 V、GND、PE、`PWR_SSTART`、`PWR_DIRECT`、`SSCL`、`SSDA`、`~{FAULT}`、`AC_FREQ_OUT` 引到背板。
- 证据：[A] `aux-ps.kicad_pcb` 的 TP1–TP5、JP1–JP4、X1 pad→net 表；[A] `fan_controller.kicad_sch` 中 IC1=MAX31760AEE+、IC2=BD00FC0W、Q3=2N7002、R14/R18=39 k、R15/R16=3.3 k、C17=47 µF；`ac_input_sstart_bias.kicad_sch` 中 TP4/TP5 与软启动网络。
- 对 Agent 的启示：这类“市电+二次控制”的板，测试点应覆盖两路电源和软启动控制信号，而不只是 +5 V；配置项（I2C 地址、风扇电压、风扇供电来源）用可切割焊盘/跳线而不是只靠固件，返修和改配置更容易。审图时要问：JP2 的默认 COM-NC/COM-NO 是哪一个？如果默认把风扇直接接 +12 V，MAX31760 的 PWM 只控制风扇 PWM 脚，不控制电压；如果默认接 `12V_PWM`，则 LDO 的压降/热耗要核算。

**版本迭代/修板历史**

- 找到的记录（作者/维护者确认）：[A] issue #108（2021-06-12，prasimix）：r3B3（Crowd Supply 绿色板）的 R4 是 opto-triac 限流电阻，和 Mean Well LRS F 型模块组合时连续通电数天会过热甚至烧断；建议 1 µF X2 + 47 Ω RC snubber 作为补救；后续重新设计。[A] issue #83（2020-08-17，prasimix）“AUX-PS module modifications for CE testing”：为通过 CE，AC 输入增加 DM/CM 滤波；用继电器替换 triac（与 BP3C 同型号）；去掉 RC snubber；THT SAR 改 SMD；去掉 TVS；增加第三只 MOV（L-N）。[A] 提交 `3da39c578dc5`（2021-02-15，“New AUX-PS, #70, #83, #84”）对应新 AUX-PS；`75d51457c595`（2019-08-09，“Fan LDO control fixed”）、`b38fe93cc1f3`（2019-08-28，“PWM pullup added”）、`285dd1fb3210`（2019-09-06，“AUX-PS softstart pull-downs changed”）；`3b2ae13a8081`（2024-01-02，KiCad 迁移）。[A] 本地根图标题栏 rev `r3B7`、日期 `2024-01-02`。
- 证据位置：issue #108 正文与评论；issue #83 正文；上述 commit 的文件列表；`aux-ps.kicad_sch` 标题栏；`aux-ps.kicad_pcb` 中 K1/K2、NTC1、VAR1-3、SAR1、L3/L4、C3/C6/C7/C8/C9/C10 的装配。
- 仍未证实：r3B4/r3B5/r3B6 之间的逐项 BOM/布局差异没有逐条记录；CE/LVD 证书和测试报告未读；r3B7 相对 r3B6 是否只有 EDA 迁移而无电气改动，资料不足。[C] issue #108 的“R4 烧断”是特定 Mean Well 组合的现场反馈，不能推广为所有 r3B3 都会失败。

**开放问题**

- NTC1（B57236S0200M）的冷阻、稳态电流、重复浪涌能量和继电器 ALQ105 的触点额定/机械寿命需要按数据手册核对；本文只按位号和网络判断拓扑。[C]
- K1/K2 的吸合时序、`PWR_SSTART`/`PWR_DIRECT` 的固件延时、掉电时的释放顺序未实测；若时序错误，NTC 可能被提前旁路。[C]
- 市电—二次的爬电/电气间隙未测量；GND 铺铜的局部边界是否满足目标安规，需要按实际板厚/涂层/污染等级核算。[C]
- 风扇 LDO IC2（BD00FC0W）的反馈网络 R14/R15/R16、JP2/JP3 的默认装配与输出电压未实测；`12V_PWM` 的实际电压/热耗需要测量。[C]
- `OK1`（TLP291）在原理图中标 `N.C.`，板上 footprint 仍在；`AC_FREQ_OUT` 的市电频率检测是否装配、R7/D5/C11/C15 等 N.C. 元件的实际装配状态，需要 BOM/实物确认。[C]

---

## 本组覆盖缺口

1. **EAGLE 二进制解析不是原生工具**：三块 Eurorack 板的 `.sch/.brd` 是 EAGLE 5.x 二进制（文件头 `0x10 0x80`），本地没有 EAGLE GUI，也没有原生网表导出。本文用自写 Python 解析器按 KiCad/pcb-rnd 的 24 字节块表和字段偏移读取；位号、网络、坐标已用已知器件（STM32、MCP3204、DAC8551、WM8731、MCP4822）交叉核对，但不能排除长字符串指针、旋转/镜像、少量文本字段的误读。所有 PCB 坐标/层/宽度结论建议用 EAGLE 或 KiCad 导入后再复核一遍。

2. **EEZ 子图不在本地快照**：本地只有根图 `aux-ps.kicad_sch` 和 `aux-ps.kicad_pcb`；`ac_input_sstart_bias.kicad_sch`、`fan_controller.kicad_sch` 是从 GitHub master 读取的，虽与本地根图/PCB 同仓库且本地文件哈希与 master 一致，但不能证明本地快照对应的 commit `c3d30a6210` 与 master 完全同一版本。若台账 commit 与 master 有差异，EEZ 的元件值/网络可能需要重读。

3. **无实测**：四个项目都没有示波器波形、频谱、THD/噪声、电源纹波、热像、浪涌电流、继电器吸合波形、EMI 预兼容或安规测试。所有“为什么”中涉及机理的部分只能标 B，涉及截止频率/增益/压降/温升/间距的数值只能标 C。尤其 Braids 的 40.8 kHz/26 dB、Clouds 的模拟增益、Edges 的 −8.2 增益、EEZ 的 NTC/继电器时序，都是计算或推断，不是测量。

4. **BOM/装配状态不完整**：本地没有 Braids/Clouds/Edges 的 `Braids.xlsx`、`Clouds`/`Edges` BOM，也没有 EEZ 的 `1-click-bom.csv`。因此“某颗 N.C. 是否装配”“某版本用 MCP3204 还是 MCP3208”“EEZ 的 OK1/AC 频率检测是否贴片”等，不能从现有文件下结论。

5. **版本对应不确定**：Eurorack 三个项目只有两次硬件提交（2015-11-14 加入、2019-04-02 改名），更早的 v40/v20 之前版本没有公开记录；EEZ 的 r3B4/B5/B6 差异只有 issue/commit 摘要，没有逐项 BOM diff。不能把 issue 里的某一版经验直接套到另一版。

6. **未做安规/EMC 复核**：EEZ 涉及 230 V 市电，本文只根据 PCB 的走线宽度、铺铜边界和模块位置讨论分区，没有按 IEC 62368-1/60950 测量爬电/电气间隙，也没有看 CE/LVD 证书。任何迁移到市电产品的设计，必须重新做安规间距、耐压、接地连续性、Y 电容漏电流和 EMC 预测试；本文的“2 mm 走线/局部铺铜”不是安规结论。

7. **未覆盖的电路细节**：Braids 的 DAC8551 符号 OUT/FB 与数据手册引脚定义的对应、Clouds 的 WM8731 CSB/MODE strap 表、Edges 的 MCP4822 基准/增益配置、EEZ 的 BD00FC0W 反馈网络，都只按原理图符号和网络判断，未逐页核对数据手册；这些是迁移前必须先查原厂资料的点。
