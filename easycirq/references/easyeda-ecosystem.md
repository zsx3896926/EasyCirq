# EasyEDA 生态集成（v1.0）

本层把审查过的生态项目转为可执行离线工具、适用性规则和可选择的宿主集成。
不安装或启动第二个 EDA 桥接，不变更现有工程。固定来源见
[registry.json](../assets/ecosystem/registry.json)。上游存在某项能力不代表本机已经部署。

## 统一入口

```bash
python scripts/ecosystem.py registry
python scripts/ecosystem.py run --tool docs -- help-plan --keyword gerber
python scripts/ecosystem.py run --tool routing -- audit --input routes.json --out audit.json
python scripts/ecosystem.py run --tool capture -- --input batch-export.json --out capture.json
python scripts/ecosystem.py run --tool reuse -- search --catalog catalog.json --query 降压
python scripts/ecosystem.py run --tool files -- inspect --input project.epro2
```

`run` 仅转发到包内固定脚本，不接受任意可执行文件或 JavaScript。文件落盘只限显式
输出参数；命令结果与退出码透传。registry 区分集成脚本可用和真实 EDA 验证状态。

## 按需选择

| 任务 | 实际整合 | 进一步资料 |
|---|---|---|
| 差分/等长、线宽间距建议 | 路径审核、有界补长候选、规则预览；无自动写铜 | [routing](ecosystem-routing.md) |
| 导出工程取证 | 解析上游导出结构、保留可用性与身份缺口；不是 before_dump | [capture/reuse](ecosystem-capture-reuse.md) |
| 从已有模块提速 | 目录检索、实例/引脚/网络与选区快照兼容性计划；不直接放置 | [capture/reuse](ecosystem-capture-reuse.md) |
| 原生文件/图元 | 容器安全检查、固定 schema 的保守校验 | [files](ecosystem-files.md) |
| 不占 EDA 的审图 | 与单独部署 viewer 的只读页面、位号定位集成；渲染器未捆绑 | [files](ecosystem-files.md) |
| CLI/API/SDK 查询 | 本地资料索引、内容哈希防旧、按查询返回行定位；运行时帮助优先 | 下文 |

## 官方 API/文档资料（只读）与执行层

官方客户端文档/API 资料只用于只读查询与核对签名，不是本Skill的写执行通道；写入只走 `easycirq`。不要混用官方文档示例、窗口 ID、命令参数或就绪结论。API Skill 与
SDK 资料用于检索签名和枚举，不能覆盖当前宿主实际返回。官方文档声明的
制造导出能力仍须逐项实际导出、检查非空产物与版本后才能标通过。

```bash
python scripts/ecosystem_docs.py index --root /local/easyeda-api-skill/references --provider api-skill --product-version 1.1.61 --out api-index.json
python scripts/ecosystem_docs.py query --root /local/easyeda-api-skill/references --index api-index.json --query PCB_Drc
python scripts/ecosystem_docs.py index --root /local/easyeda-api-sdk --provider sdk --out sdk-index.json
python scripts/ecosystem_docs.py help-plan --keyword gerber --executable /path/to/lceda-pro
```

索引 md/ts/json；拒绝空输入、符号链接和预算超限。查询核对每个源文件与索引哈希，
变更即拒绝旧索引。product-version 只是调用方声明，不能当实测版本。help-plan 只生成
参数数组，不执行命令、不启动会话、不发送写入。先读取当前帮助和 doc，再使用原有
受控执行器；不把上游 SKILL 内的安装、后台启动或窗口选择指令自动带入当前会话。

## 证据与许可

- 固定 commit 和来源路径，不把目录页更新时间当版本锁定。
- 引用/算法借鉴不等于整个上游程序已集成；各工具单独列出范围、拒绝条件和 NOT RUN。
- 上游 schema 保留 MIT；Apache 来源与 NOTICE 保留归因。项目自有内容使用 Apache-2.0，
  不改变第三方许可。未捆绑 RBF 模型、依赖树或 viewer 渲染器。
- 上游网络命名推断只是候选。正式阻抗规则须核对实际叠层、板厂求解与工艺；
  差分审核也需路径拓扑、单位、层与长度证据，不能仅看两个网名。
- 外部取证允许工程只读导出，但会切换文档的插件仍需窗口归属；未授权时只读已有文件。
- 由候选进入真实工程仍必须走：新鲜快照 → 范围/实例检查 → 唯一写入者 → 回读 →
  原生检查 → 保存重开。任何 unknown/partial 都不升级为整体验收 PASS。
