# 摄像头 DVP FPC 设计卡（assumed 模板）

> **状态：assumed（模板）**。这是一份“常见模组”假设的起点，不是已核实的引脚定义。使用前逐项确认并落盘；否则交付门禁 G6 会 `BLOCKED`（见 [design-gates](../design-gates.md) `req_interface_pinout`）。

## 适用范围

- 并口摄像头（DVP）模组：24P FPC 常见排布，以 OV2640 / GC0328 等为例。
- 只作为 `requirements.interface_pinout` 的 `assumed` 记录模板；改为 `confirmed` 前不得据此做最终原理图/布线。

## 必须核对项（缺一不可）

1. **1 脚方向**：FPC 金手指正视/焊接面、连接器 Pin-1、排线接触面四方对照唯一（见 [跨模块组合与接口契约](../module-integration.md) §2 第 5 条）。
2. **电源域**：IOVDD/AVDD/DOVDD/CORE 电压与上电顺序，以及每轨电流。
3. **差分对**：时钟/数据线是否差分、对内等长与阻抗要求。
4. **时钟/同步**：PCLK/VSYNC/HSYNC/XCLK 方向、频率、是否可由主控输出。
5. **信号电平**：并行数据/控制脚 1.8 V 还是 3.3 V，与主控 IO 电压域匹配。
6. **复位/掉电**：RESETB/PWDN 极性、上电默认态、复位时序。

## 落到 design-state 的写法

```json
"requirements": {
  "interface_pinout": [
    {"module": "摄像头 DVP FPC", "model": "OV2640 24P", "status": "assumed",
     "source": "常见模组假设，待按模组规格书核对", "view": "FPC 正视 1 脚在左"}
  ]
}
```

核对完成后把 `status` 改为 `confirmed`，`source` 改为数据手册/规格书出处。
