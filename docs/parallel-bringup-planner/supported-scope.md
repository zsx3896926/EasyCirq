# 首期支持范围与明确不支持范围（bringup-planner v1）

> 范围判定只看**输入声明与参数**（`project.scope.supply_class`、`operations`、电压包线、`user_policy`），不靠项目名、文件名或自由文本猜测。
> 本工具是离线计划生成器：本文件描述"能生成什么样的计划"，不证明任何实物已被验证。所有真实上电/仪器测量在当前交付中均为 **NOT RUN**。

## 1. 支持的首板场景

首期只支持**低压直流供电、基础电源域、MCU 数字接口、简单模拟采集/传感、低边负载驱动**：

| 能力 | 支持内容 | 生成依据 |
|---|---|---|
| 供电 | 单路/多路低压直流（USB 5 V、适配器、LDO/buck 输出） | 声明的 `power_domains`、工作/绝对最大范围、依赖 |
| 电源域 | 1 个或多个域的依赖顺序、上电与断电检查 | `depends_on` DAG + 声明测点/设备 |
| MCU/数字 | GPIO、UART、I2C、SPI、USB 枚举/日志的**测量与前提** | 接口角色、逻辑电平、固件/主机前提 |
| 模拟 | 分压/NTC/比较器/ADC 读数的基本测量 | 声明测点、参考地、器件工作范围 |
| 负载 | LED、按键、低边 MOSFET 驱动已声明负载 | `load_output/led/button` + 声明负载 |
| 保护/装配 | 极性、DNP、跳线、外部供电断开、回灌冲突检查 | `assemblies/interfaces/testpoints` |

**硬性包线**：

- 最高工作电压 ≤ **30 V DC**；声明的单域绝对最大 ≤ **60 V DC**。超出即 `needs_specialist`。
- 所有测量必须能落到声明测点与参考地；无测点的域不生成"可执行"测量步骤。
- 所有限流/阈值必须有声明依据（`basis` + `source_ref/fact_id`）；没有依据就是 `blocked`。
- `user_policy.mode` 必须为 `plan_only`；工具从不执行、从不接管仪器。

## 2. 明确不支持（遇到即 `unsupported` / `needs_specialist`，不生成通用上电步骤）

| 类别 | 处理 | 原因 |
|---|---|---|
| 市电/AC 输入、并网、隔离边界 | `needs_specialist` | 触电/能量危险，需专业安规与设备 |
| 高压直流（>60 V 绝对 / >30 V 工作） | `needs_specialist` | 超出首期包线，探头/间隙/安全距离另有要求 |
| 锂电充放电、储能、BMS | `needs_specialist` | 热失控/能量危险，需专用测试与认证 |
| 复杂射频/无线认证、天线辐射测试 | `unsupported` | 需暗室/认证机构与法规流程 |
| 完整音频功率/BTL 输出验收 | `unsupported`（仅保留安全测量约束） | 首期不做音频功率验收；但会阻止单端接地错误测量 |
| 大电流负载、电机堵转、功率器件温升验收 | `unsupported` | 需要专用负载/热测试条件 |
| 任何需要工具自动执行的步骤（烧录、脚本、仪器程控） | `unsupported` | 工具边界：只计划、不执行 |
| 焊接返修、飞线改板 | 不生成操作步骤 | 属于装配/返修流程，需人工与工艺文件 |

### 特殊子场景

- **BTL/桥式/非地参考输出**：可以生成"检查前提 + 禁止单端接地测量"的步骤；若输入未声明差分探头/差分测法，相关测量步骤 `blocked`，不会给出"用普通示波器地夹夹到输出端"的建议。
- **外部 USB/调试器回灌**：可生成断开/隔离步骤与冲突告警；冲突未解决时上电步骤 `blocked`。
- **未装模块（DNP）/未烧固件**：分别生成装配核对/固件前提步骤；未烧录前不期待业务通信，也不会把"没反应"当失败。
- **负载不明**：不生成负载测试，输出 `unknown` 要求补负载参数/器件约束。

## 3. 判定顺序（实现见 `scope.py`）

1. `user_policy.mode != plan_only` → unsupported。
2. `project.scope.supply_class` ≠ `dc_low_voltage` → unsupported/needs_specialist。
3. 任一域 `operating_max_v > 30` → unsupported；任一域 `absolute_max_v > 60` → needs_specialist。
4. 板级所需操作（由域/接口/负载推导）未在 `project.scope.operations` 声明 → 缺口；未被 `user_policy.allowed_operations` 授权 → needs_information；被 forbidden → unsupported。
5. `user_policy.max_input_voltage_v` 低于最高工作电压 → 不得在声明电压上电（needs_information/blocked）。
6. 以上都通过 → `supported`，生成可执行（人工）步骤；否则只输出范围原因、缺口与待确认项。

## 4. "缺信息"不是"默认安全"

以下任一缺失都会让相关步骤 `blocked` 而非用默认值补齐：

- 启动/运行电流未知 → 无法给出限流依据（不会默认 100 mA/500 mA）。
- 观察窗口无依据 → 不编造精确秒数。
- 测点缺失/可达性未声明 → 不生成可执行测量。
- 示波器带宽/探头参数缺失 → 不宣称可测纹波/时钟/复位波形。
- 差分测法/差分探头缺失 → BTL/非地参考测量 blocked。
- `short_check_criterion` 缺失 → 断电电阻步骤判据为 `undefined`/`needs_interpretation`（不输出通用欧姆阈值）。
- 固件/主机前提未声明 → 不期待业务通信，不把无响应当失败。
- 安全边界（`user_policy`）缺失/矛盾 → 不上电。

## 5. 证据与结论边界

- 支持范围内的计划也只代表"离线一致、步骤可人工执行"；**真实测量、上电、烧录、EMC、温升、可靠性均不在本交付内**。
- 评估器的 `PASS` 仅表示"记录与计划/证据一致且为真实测量声明"；它不能验证仪器是否真的接对、读数是否真实、板子是否可靠。
- 任何 `synthetic` 记录最多得到 `SYNTHETIC_ONLY`，不可能升级为真实硬件 PASS。
- 现有冻结设计（temp-alarm、photo-led、mcu-i2c-s3）仅作为**只读设计意图/BOM 参考**；未打样/未贴片/未实测部分不得声称已验证。
