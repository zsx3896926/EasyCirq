# F1 rev3 首板固件与上电测试（ESP-01S / ESP8266）

对应硬件：`F1-USB-MCU-C` rev3，U101 = **Ai-Thinker ESP-01S（ESP8266，1MB）**。
依据：`docs/evidence/f1-c-2026-10-22/part-evidence.md`（身份与网表逐脚核对）。

## 1. 板级接口（权威来源：rev3 网表）

| U101 脚 | 信号 | 板上连接 | 备注 |
|---|---|---|---|
| 8 | VCC | 3V3（U102 AMS1117-3.3 输出） | 输入 5V 经 C101 10µF；输出 C107 22µF 钽 + C106 10µF + C102 100nF |
| 1 | GND | GND | |
| 6 | EN (CH_PD) | R103 10k → 3V3，C104 100nF → GND | 上电使能 |
| 7 | RST | R104 10k → 3V3，C105 100nF → GND，SW101 → GND | 复位键 |
| 3 | IO0 | R105 10k → 3V3，SW102 → GND | 下载模式：上电时拉低 |
| 2 | IO2 | R107 10k → 3V3 | 启动必须为高 |
| 4 | RXD | J102-3 | 3.3V TTL |
| 5 | TXD | J102-2 | 3.3V TTL |

J102 引脚：1=3V3，2=TXD，3=RXD，4=GND。D101 为 3V3 电源指示灯（R106 1k），**不占 GPIO**；
本板没有 GPIO 用户 LED/按键。

## 2. 构建与烧录（可复现命令）

```bash
# 构建（未在本机执行：平台未安装 PlatformIO，标记 NOT RUN）
cd firmware/f1-esp01s
pio run

# 烧录（USB-TTL 接 J102；烧录时 IO0 接地后上电/复位，烧完断开）
pio run -t upload --upload-port COM5

# 串口（115200 8N1；ESP8266 ROM 启动日志为 74880，属正常）
pio device monitor -p COM5 -b 115200
```

`platformio.ini` 固定 `platform=espressif8266`、`board=esp01_1m`、`framework=arduino`，
构建产物路径 `firmware/f1-esp01s/.pio/build/esp01_1m/firmware.bin`。若不用 PlatformIO，
可用 Arduino IDE（ESP8266 core 3.x，Generic ESP8266 Module / 1MB / 无 SPIFFS）+ esptool 烧录。

**构建状态：NOT RUN**（本机无 pio/esptool；命令已给出，未执行不得声称编译通过）。

## 3. 串口预期输出（用于首板判定）

```
[F1] board=rev3 fw=0.1.0
[F1] chip_id=00XXXXXX flash=1024KB sdk=...
[F1] cpu=80MHz free_heap=...
[F1] boot ok; heartbeat is 1 line / 2 s
[F1] alive uptime_ms=2000 heap=...
[F1] scan aps=N best_rssi=-XX      (首次约 15 s 后)
```

故障提示（固件内建）：`[F1][FAULT] wifi_scan failed code=<n>` → 射频/供电异常排查。

## 4. 上电前检查表（首板，务必按序）

| # | 检查 | 判据 | 结果 |
|---|---|---|---|
| 1 | 外观/焊接 | 无连锡、立碑、极性件方向正确（C107 钽、D101/D102、J101） | NOT RUN |
| 2 | 断电电阻 | 5V–GND、3V3–GND 均不短路（>1kΩ）；J102 3V3–GND 不短路 | NOT RUN |
| 3 | 限流上电 | 5V/100mA 限流；空载电流 <30mA | NOT RUN |
| 4 | 电源轨 | 5V≈5.0V；3V3=3.25–3.35V；纹波 ≤50mVpp | NOT RUN |
| 5 | 温升 | U102 表面温升 <30°C@空载，<50°C@满载 | NOT RUN |
| 6 | 启动日志 | 74880 出现 ROM 日志；115200 出现 `[F1] boot ok` | NOT RUN |
| 7 | 烧录 | 按 §2 烧录成功，重启后版本号变化 | NOT RUN |
| 8 | 心跳 | 每 2 s 一行 `alive`，free_heap 稳定 | NOT RUN |
| 9 | 射频 | `scan aps>0`（有 AP 环境）；TX 峰值电流 ≤250mA | NOT RUN |
| 10 | 复位/下载键 | SW101 复位后可重启；SW102 上电可进下载 | NOT RUN |
| 11 | J102 反灌 | 外接 USB-TTL 只接 GND/TXD/RXD，不接 3V3；确认无倒灌 | NOT RUN |
| 12 | 负载瞬态 | TX 峰值时 3V3 跌落 ≤100mV | NOT RUN |

## 5. 首板结果记录模板（M3）

```text
样机版本：F1 rev3 / PCB rev? / 装配日期
固件版本：0.1.0（git <sha>）
仪器：万用表 <型号>；示波器 <型号>；限流电源 <型号>
接线：5V 经 J101 USB-C；串口经 J102（GND/TXD/RXD）
条件：室温 __°C；输入 5.00V；限流 100mA→500mA
实测值：空载 __mA；TX 峰值 __mA；3V3 __V；纹波 __mVpp；U102 温升 __°C
通过判据：见 §4
结果：PASS/FAIL（逐项）
异常与处理：
```

## 6. 已知限制

- 本固件只验证供电/启动/串口/射频存在性，不实现业务功能（本板尚无业务外设）。
- Wi-Fi 扫描不需要凭据；若后续加联网功能，凭据必须走配网/构建注入，不得硬编码进仓库。
- 热与纹波判据为工程初值，首板实测后按结果收紧。
