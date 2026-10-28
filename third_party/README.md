# third_party — 复用来源清单

本目录只放**来源锚点**（仓库、固定提交、许可、逐文件哈希），不放重复源码：
实际复用的源码在 `runtime/` 与 `connector/`，机械变换规则在
`distribution/rebrand_runtime.py`、`distribution/rebrand_connector.py`，
可复现校验在 `distribution/verify_vendor.py`。

| 组件 | 来源 | 固定版本 | 许可 | 落点 |
| --- | --- | --- | --- | --- |
| easyeda-agent（Go 运行时） | github.com/zhoushoujianwork/easyeda-agent | tag `v1.15.0` / commit `d93d3dd` | MIT | `runtime/` |
| easyeda-agent（EasyEDA 连接器扩展） | 同上 | 同上 | MIT | `connector/` |
| Easy_EDA_PCB_Beautify（`connector/src/beautify/*`） | 上游扩展内嵌 | 随 v1.15.0 固定 | Apache-2.0 | `connector/src/beautify/LICENSE`，分发时随 `.eext` 附 NOTICE |
| easyeda-format schemas | 之前版本已收录 | 见 `design-hardware/vendor/easyeda-format/LICENSE` | MIT | `design-hardware/vendor/` |
| Go 依赖 | github.com/spf13/cobra v1.10.2、github.com/coder/websocket v1.8.15 | 锁定在 `runtime/go.sum` | Apache-2.0 / ISC | 构建时拉取，不随仓库分发 |
| npm 构建依赖 | esbuild、ts-node、typescript、jszip 等 | 锁定在 `connector/package-lock.json` | MIT/Apache-2.0 等 | 仅构建期，不随 `.eext` 分发 |

## 分发时的义务

1. `.eext` 内必须同时带 `LICENSE`（MIT，上游）与 `NOTICE`（本项目新增，含 Apache-2.0
   内嵌组件说明）。见 `connector/NOTICE`。
2. `runtime/` 内必须保留上游 `LICENSE` 与 `NOTICE`；本项目修改亦以 MIT 兼容方式提供。
3. 根目录 `LICENSE`（Apache-2.0）与 `NOTICE` 覆盖本项目原创部分，不覆盖上述第三方代码。
4. 不得把任何第三方 MIT/Apache 代码表述为完全自主原创。
