# EasyEDA 官方 GitHub 与内置 CLI：能用到什么

> 来源：<https://github.com/EasyEDA>（17 个仓库）+ 本机 `lceda-pro.exe` V4.1.78 实测。
> 2026-11 收到用户指引后调研。**所有 API 结论都来自本机 dump，不是猜的。**

---

## 一、结论先行

三件事，按影响排序：

| # | 发现 | 对我们意味着什么 |
|---|---|---|
| 1 | **官方 API 全表可以从本机 dump** | **A2 彻底答了。** 不用问客户，不用猜，直接查 |
| 2 | **网表有官方接口**：`sch_ManufactureData.getNetlistFile()` | **转换器不用做了。** 我们连接器已经在用这个接口 |
| 3 | **官方自己做了 AI 桥接**（扩展 + skill + CLI + MCP） | 我们的执行层官方已提供。**但治理层没人做——那才是我们的位置** |

---

## 二、A2 彻底答了：API 全表在本机就能 dump

```bash
lceda-pro doc api                          # 列出全部类
lceda-pro doc api --class-name SCH_Netlist # 看某个类的方法
lceda-pro doc api --class-name SCH_Netlist --method-name getNetlist
```

全表已存 `reports/eda-api-classes.txt`。

**关键确认——命名空间和我们完全一致。** dump 出来的 `classToProperty` 映射：

```
DMT_Board → dmt_Board        SCH_Netlist → sch_Netlist
PCB_Document → pcb_Document  LIB_Device → lib_Device
SYS_WebSocket → sys_WebSocket
```

我们连接器调的就是 `eda.dmt_*` / `eda.sch_*` / `eda.pcb_*` / `eda.lib_*` / `eda.sys_*`。
**同构。A2 从"未知"变成"已验证"。**

而且 **`sys_WebSocket` 是官方一等公民接口**（`SYS_WebSocket` 类，注释「系统 / WebSocket 类」），
不是我们绕开官方的东西。

### 还有 `doc format` 和 `doc external`

```bash
lceda-pro doc format    # 设计文件格式规范（.eprj3 / .epro2）
lceda-pro doc external  # 扩展注入的外部 API
```

**`doc format` 回答了我们一直缺的那件事：工程文件格式规范。**
格式说明仓库也在：<https://github.com/easyeda/easyeda-eprj3-format>

---

## 三、网表问题：转换器不用做了

### 官方接口（实测查到的签名）

```js
// 网表 —— 返回 File 对象
await eda.sch_ManufactureData.getNetlistFile(fileName?, netlistType?)
// 返回值示例里的官方注释：
// "可以使用 SYS_FileSystem.saveFile 接口将文件导出到本地文件系统"

// BOM —— 返回 File 对象
await eda.sch_ManufactureData.getBomFile(fileName?, 'csv'|'xlsx', ...)
```

**网表类型枚举 `ESYS_NetlistType`（实测取值）：**

| 枚举 | 值 | 说明 |
|---|---|---|
| `ALLEGRO` | Allegro | |
| `PADS` | PADS | |
| `PROTEL2` | Protel2 | |
| **`JLCEDA_PRO`** | **JLCEDA** | **嘉立创 EDA 专业版原生** |
| `EASYEDA_PRO` | EasyEDA | |
| `DISA` | DISA | 数字化工业软件联盟 |
| `DISA_SIMULATION` | DSNET | 联盟仿真 |

### 好消息：我们的连接器已经在用正确接口

`connector/src/schematic-netlist-file.ts` 调的是
`eda.sch_ManufactureData.getNetlistFile(fileName, type)` ——
**是官方推荐的接口，不是废弃的那个。**

（`eda.sch_Netlist.getNetlist()` 已被官方标为 `deprecated`：**「请使用 SCH_ManufactureData.getNetlistFile 替代」**。
我们没用它，对的。）

而且这个 helper 还带**就绪同步**（`waitForSchematicReady` + 150ms 静默窗口），
应对「导出完成但标注仍在同步」的竞态。这是我们自己加的，官方文档没提。

### 所以

**不需要写 Protel2 转换器。** 工程师也不用手工导出文件。
`enterprise check --netlist` 的输入可以直接由连接器调 `getNetlistFile('...', 'JLCEDA')` 拿到。

---

## 四、官方已经有了 AI 桥接——和我们的执行层撞了

### `eext-run-api-gateway`（★100，Apache-2.0）

官方扩展，**WebSocket 客户端**，连一个 Bridge Server：

```
AI Agent ──HTTP/WS──► Bridge Server ──WebSocket──► 本扩展（EasyEDA 内）
         端口 49620-49629          （Node.js）       端口 49620-49629
```

- 自动扫描端口 **49620-49629**
- 握手校验 `easyeda-bridge`
- 心跳 + 断线重连
- **接收 AI 发来的代码，在 EDA 环境里执行并返回**

**这和我们的连接器 + daemon 几乎同构**（我们是 `.eext` → `ws://127.0.0.1:23111/eda`）。

### `easyeda-api-skill`（★1017）

配套 Skill，负责**启动 Bridge Server**、提供 API 文档与调用约定、完整 AI↔EDA 工作流。
支持 OpenCode / Claude Code / Cursor / Cline / Continue / Windsurf / QwenCode / KimiCode / Trae。

**这是我们这套东西的直接对照物，而且星数是我们的 1000 倍。**

### 关键差别：他们执行**任意代码**，我们执行**类型化动作**

| | 官方 Run API Gateway | EasyCirq |
|---|---|---|
| 执行单位 | 任意 JS 代码 | 184 个类型化动作 |
| 可审计 | 难（代码是自由文本） | 每个动作有名有参数 |
| 可判据 | 无 | 19 项 KPI + 门禁 |
| 人审 | 无 | review ledger + promote |
| 灵活性 | 高 | 低但确定 |

**这不是我们输了。这是分工。**

企业真正缺的不是「让 AI 能画板」——那个官方已经解决了。
企业缺的是「AI 画的东西**符合公司规范、可追溯、有人签字**」。

**我们的位置应该是治理层，不是执行层。**

---

## 五、客户端 V4.1.70+ 内置 CLI，还能当 MCP server

本机实测（`lceda-pro.exe` 4.1.78）：

```
lceda-pro <command>
  activate / open / stop / doctor
  session/  list | close | abort
  invoke    在编辑器里执行 JS（省略 extUuid 可独立运行）
  functions 列出已知扩展
  doc/      api | external | format
  --mcp stdio|http   ← MCP 服务器模式
```

```bash
lceda-pro session open
lceda-pro invoke --ext-uuid eda "eda.sys_Message.showMessage('Hello')"
lceda-pro --mcp http --port 3030
```

**含义**：

1. **不需要装任何扩展**就能驱动编辑器（`invoke` 执行 JS）
2. **官方 MCP server** —— 现代 AI 工具的标准接入方式
3. 内置 API 参考查询（就是上面第二节那个）

⚠️ 文档写明**要求 V4.1.70 及以上**。
**客户私有部署是 1.12.1，可能没有这套 CLI** —— 所以**不能**据此拆掉我们的连接器。

---

## 六、其他仓库，按有用程度排

| 仓库 | ★ | 有什么用 |
|---|---|---|
| `easyeda-api-sdk` | 78 | **扩展开发 SDK**（TypeScript）。我们连接器用的 `@jlceda/pro-api-types` 应该就来自这里 |
| `easyeda-eprj3-format` | 6 | **`.eprj3` 工程格式说明** —— 直接读工程文件、不启动 EDA 的可能路径 |
| `easyeda-viewer` | 4 | epro2/eprj3 **查看器**，可嵌入网页 |
| `easyeda-format-skill` | 14 | 让 AI 直接生成专业版文件格式 |
| `easyeda-eprj3-skill` | 78 | 让 AI 直接创建 eprj3 工程 |
| `easyeda-enhanced-schematic-skill` | 52 | 原理图增强 skill，**依赖 easyapi-api-skill** |
| `eext-easyeda-api-agent` | 10 | 基于大模型的扩展 API 助手 |
| `easyeda-simulation-engine` | 40 | NGspice + SimulIDE 仿真引擎（C） |
| `eext-freerouting-intergration` | 11 | Freerouting 自动布线扩展 |
| `eext-export-design-archive` | 1 | 批量导出工程/库压缩包 |
| `eext-mcad-integration-with-freecad` | 4 | PCB 3D 发到 FreeCAD |
| `eext-line-equal-spacing` | 0 | 等间距布线 |
| `eext-component-box` | 4 | 器件盒管理 |
| `spice-model-skill` | 0 | AI 造 SPICE 模型 |

---

## 七、建议：不拆连接器，但改三件事

### 1. 已做：用 `doc api` 核对了我们的调用

**结果：我们用的 61 个 `eda.<类>_` 属性，全部在官方 `classToProperty` 表里，零偏差。**

```
官方属性数: 97
官方前缀:   ['dmt', 'lib', 'pcb', 'pnl', 'sch', 'sys']
我们用了:   61 个
官方表里没有的: 无 —— 全部在官方表里
```

逐条核对脚本：`tools/check_against_official.py`，数据源 `reports/eda-api-classes.txt`。

**另外确认：我们没有用废弃接口。** `eda.sch_Netlist.getNetlist()` 已被官方标
`deprecated`（「请使用 SCH_ManufactureData.getNetlistFile 替代」），我们用的是后者。

**结论：连接器的 API 使用是干净的。** 这条疑虑可以放下。

### 2. 定位改口：我们是治理层，不是执行层

对外说法应该是：

> 「官方让你能画，EasyCirq 让画出来的东西**过得了公司的检查、留得下签字**。」

这也解释了为什么我们**不该**去做「更快的连接器」——那是在和官方的 1017 星 skill 比拼。

### 3. 不建议现在做：用官方 CLI 替换自研连接器

`lceda-pro invoke` 确实能替代我们的连接器，**但要求 V4.1.70+**，
而客户私有部署是 **1.12.1**。拆掉自研连接器 = 把私有部署客户丢掉。

**等确认私有部署 1.12.1 有没有这套 CLI 再谈。**

---

## 八、这次调研改变了什么

| 之前 | 现在 |
|---|---|
| A2 要问客户要 `.d.ts` | **本机就能 dump 全表**，已验证同构 |
| 要写 Protel2 网表转换器 | **不用写**，官方接口直接给网表文件 |
| 以为我们的连接器是独特资产 | 官方有同构实现（★100 + ★1017 skill） |
| 以为要自己造 MCP 接入 | **官方客户端内置 MCP server** |
| 不确定 `sys_WebSocket` 是否官方 | **是官方一等公民接口** |
