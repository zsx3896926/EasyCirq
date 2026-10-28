# 并行任务 D 契约：Skill 知识结构审计与最小阅读导航

- 任务：`skill-knowledge-audit`（只读、离线、可重复）
- 工作树：`hds-ska-worktree`
- 分支：`feat/parallel-skill-knowledge-audit`
- 固定基线：`9a951edc21481dc3ae91460acc11aa3e08a7be8a`（main，v1.0.1）
- 交付目录：`easycirq/scripts/skill_knowledge_audit/`、
  `tests/skill_knowledge_audit/`、`benchmarks/skill-knowledge-audit/`、
  `docs/parallel-skill-knowledge-audit/`
- 工具版本：`0.1.0`；结构版本：`skill-knowledge-audit/v1`；目录版本：`2026-10-27.1`

本契约在 M0 冻结。实现、测试、场景和报告都以本文件中的字段名为准；后续
修改必须同步本文件并在 `handoff-current.md` 记录原因。

## 1. 边界与非目标

允许新增/修改的目录仅限任务书列出的四个目录。本任务：

- 只读 `SKILL.md`、`references/`、`scripts/`、`assets/`、`docs/` 与安装包内容；
- 不修改主 `SKILL.md`、现有 references、README、CHANGELOG、版本号、主
  `docs/handoff-current.md`、runtime、connector、protocol、distribution、CI、
  顶层依赖、feedback、compose、`design_engine`，不改任务 B/C 目录；
- 不调用 EDA（含只读）、Connector、旧执行器；不启动浏览器；不安装客户端；
- 不执行源文档中的代码块；不联网验证外链；不申请或配置外部模型 API；
- 所有“建议”只写入本任务的 proposal 文件，不直接套用源文件；
- 不宣称已改变客户端实际加载行为、实际画板提速或工程质量通过。

程序本身只读被扫描根；唯一写操作是用户通过 `--out`/`--cache-out` 指定的
输出文件。输出必须位于扫描根之外；指定根内路径时命令直接报错（退出 2），
防止跨命令自我污染。

## 2. 包与入口

```
easycirq/scripts/skill_knowledge_audit/
  __init__.py        # 版本、schema 常量
  __main__.py        # python -m skill_knowledge_audit
  cli.py             # argparse 与命令分发
  common.py          # 原子写、canonical JSON、路径/哈希/错误类型
  scan.py            # D1 文件发现、Markdown/锚点/链接/脚本引用
  graph.py           # D1 引用图、必读闭包、循环/孤立/过深/重复
  rules.py           # D2 规则抽取、候选、冲突分类、夹具评估
  plan.py            # D3 intent 解析、主题映射、预算、缓存
  bench.py           # D5 场景、基准、变形、指标
  render.py          # Markdown 渲染（索引/报告/计划）
  catalog/
    topics.json      # 任务→主题→文件映射（经人工审查）
    rules.json       # 规则记录 + 已审查关系（人工证据）
```

规则夹具的规范位置是 `benchmarks/skill-knowledge-audit/fixtures/rule-pairs.json`；
`rules` 命令默认解析到它，也支持 `--fixtures` 指定。CLI 使用文档在
`docs/parallel-skill-knowledge-audit/cli.md`（放在被扫描根之外，避免报告自我污染）。

运行方式（包目录需在 `sys.path`；文档给出可复制命令）：

```
cd easycirq/scripts
python -m skill_knowledge_audit scan --root ..
python -m skill_knowledge_audit rules --root ..
python -m skill_knowledge_audit plan --root .. --intent <intent.json> --out <plan.json>
python -m skill_knowledge_audit benchmark --root .. --scenarios ../benchmarks/skill-knowledge-audit/scenarios
```

兼容 Python 3.10+；本机实测 3.13.15，3.10 由语法审查与 CI 覆盖，未在本机
取得 3.10 运行证据。仅用标准库。

## 3. 通用输出约定

所有命令：

- stdout 只输出一个 UTF-8 JSON 对象（`ensure_ascii=false`、`sort_keys=true`、
  `\n` 结尾）；诊断/进度只写 stderr；
- 每个结果含 `schema`、`kind`、`tool`（`name`/`version`）、`catalog_version`、
  `source`（`root`、`git_sha`（可用时）、`scanned_at`、`duration_ms`）；
- 数组按稳定键排序（文件按 path，链接按 (path,line,column,target)）；
- 相同输入 + 相同工具/目录版本必须产生字节级相同的 `content` 部分（时间戳
  除外，测试比较时剥离 `scanned_at`/`duration_ms`）；
- `--out` 使用同目录临时文件 + `os.replace` 原子写；父目录不存在时报错；
- 退出码：`0` 成功/无必须失败项，`1` 发现需要处理的问题，`2` 用法、
  IO、输入非法或抽取失败。不得沿用旧 PASS：异常/非法输入直接 `2`。

`ok` 字段定义：命令确实完成且没有 `error` 级别发现。`PASS` 不是工程结论。

## 4. D1 扫描与引用图

### 4.1 文件发现

- 递归 `*.md` 与 `*.json`（catalog/场景所需）、`*.py` 脚本清单；默认排除
  `.git`、`__pycache__`、`.venv`、`node_modules`、`dist`、输出路径；
- 符号链接：解析 `realpath`，越出声明 root 的链接记 `symlink_escape` 错误，
  不读取目标；目录链接不跟随；
- 单文件上限 8 MiB、总扫描上限 2000 万字符（可 `--max-file-bytes` 覆盖），
  超限记 `skipped_oversize`，不静默截断后当完整；
- 二进制/非 UTF-8 文件跳过并记 `skipped_encoding`；
- 保留 path（root 相对、`/` 分隔）、sha256、bytes、chars、lines、frontmatter。

### 4.2 标题与锚点

GitHub 风格 slug：转小写、去标点、空格转 `-`、保留 Unicode 字母/数字/`-`/`_`；
同名标题按出现顺序加 `-1`、`-2`。文件内重复标题记 `duplicate_heading_anchor`
（结构提示），跨文件不构成问题。链接锚点比较时做 `unquote`，并接受不带
slug 后缀的显式锚点（如 `#L12` 视为行锚点，单独分类 `line_anchor`）。

### 4.3 链接分类（只按文本证据，不按链接存在性）

每条链接记录：`line`、`column`（1-based）、`text`、`target`、`target_path`、
`anchor`、`kind`、`role`、`role_evidence`、`resolved`、`exists`、
`anchor_exists`、`case_mismatch`、`escapes_root`、`external`。

`kind`：`local_markdown`、`local_asset`、`script`、`external`、`anchor_only`、
`unknown`。

`role` 及判定（仅当行内/表格行文本明确表达时）：

| role | 判定证据（示例） |
|---|---|
| `required_read` | “先读/必须先读/务必读/始终遵循/必读/read first/must read/required reading” |
| `conditional_read` | “……时读/按需/按任务加载/when/if needed/按阶段” |
| `example` | “示例/范例/样例/example” |
| `background` | “背景/延伸阅读/资料入口/参考/更多/可选” |
| `script_call` | 目标是 `.py` 或行内出现 `python scripts/...` |
| `external_reference` | `http(s)://`、`mailto:` |
| `unknown` | 没有上述明确措辞 |

普通链接不得自动升为必读；`required_read` 必须能回指到触发短语的字符区间。
代码围栏内的链接不参与依赖图，但保留为 `in_code_fence=true` 供审计。

### 4.4 脚本引用

识别行内代码/围栏中的 `scripts/...py`、`python scripts/...`、`python3 ...`：
`path`、`line`、`exists`、`placeholder`（含 `<...>`、`...`、`{`、`$`、`*`、
`path/to`、示例占位）、`arguments`。占位参数或占位路径不报坏引用；真实
存在的路径在 `scripts` 清单中交叉核对。不执行脚本。

### 4.5 图分析

- 解析本地路径：相对当前文件目录，`unquote`，去 query/anchor；越界/绝对/
  盘符路径记 `unsafe_target` 错误（不打开）；
- 大小写：在 Windows/macOS 上请求路径存在但目录列表无精确大小写 → 
  `case_mismatch` 警告（不判坏）；
- 失效路径/锚点：`error`；
- 重复锚点：`warning`；引用循环、孤立资料、必读链深度 > 3、同主题重复：
  `info`/`warning`，按上下文分类为“结构提示”，不自动算 bug；
- 必读闭包：从 `SKILL.md` 出发，只沿 `required_read` 边；输出深度和文件集；
- 孤立：没有任何入链（不计 SKILL.md 自身），按目录/角色分类；
- 外链只记录 URL 与位置，`external_verified=false`，不发请求、不判失效。

### 4.6 忽略声明

格式（`--ignore-file`，JSON）：

```json
{"schema":"ska-ignore/v1","rules":[
  {"id":"IGN-001","check":"broken_link","target":"references/x.md#old",
   "reason":"外部规范要求保留历史锚点","scope":"file:references/x.md"}
]}
```

每条必须含非空 `reason`、精确 `target`、受限 `scope`（`file:<path>` 或
`finding:<id>`）。拒绝无 scope、`*`/`**` 通配、无理由、过期条目；被忽略
发现仍出现在结果中（`ignored:true`、`ignore_reason`），不删除、不假绿。

### 4.7 输出骨架

```json
{
  "schema":"skill-knowledge-audit/v1","kind":"scan","tool":{"name":"skill_knowledge_audit","version":"0.1.0"},
  "catalog_version":"2026-10-27.1",
  "source":{"root":"...","git_sha":"...","scanned_at":"...","duration_ms":0},
  "files":[{"path":"easycirq/SKILL.md","sha256":"...","bytes":0,"chars":0,"lines":0,
            "title":"...","headings":[{"level":2,"text":"...","line":12,"anchor":"..."}],
            "links":[{"line":14,"column":5,"text":"安装与更新","target":"references/installation-updates.md",
                      "kind":"local_markdown","role":"required_read","role_evidence":"读取",
                      "resolved":"easycirq/references/installation-updates.md",
                      "exists":true,"anchor":null,"anchor_exists":true,
                      "external":false,"in_code_fence":false}],
            "script_refs":[{"line":15,"path":"scripts/skill_update.py","exists":true,"placeholder":false}]}],
  "graph":{"required_closure":["..."],"required_depth":2,"cycles":[["a","b"]],
           "orphans":["..."],"over_deep_required":[{"path":"...","depth":4}],
           "duplicate_topics":[{"topic":"...","paths":["..."]}],
           "missing_anchors":[{"source":"...","line":1,"target":"...","anchor":"..."}],
           "broken_links":[{"source":"...","line":1,"target":"...","reason":"missing_path"}],
           "case_mismatches":[], "unsafe_targets":[], "symlink_escapes":[]},
  "ignored":[{"id":"IGN-001","finding":"broken_link","target":"...","reason":"..."}],
  "counts":{"files":0,"links":0,"required_links":0,"broken":0,"missing_anchors":0,"errors":0,"warnings":0,"info":0},
  "excluded_outputs":["..."],
  "limits":{"max_file_bytes":8388608,"max_total_chars":20000000},
  "ok":true,
  "not_proof":"本结果只证明静态文档结构与引用关系，不证明 Skill 被加载、AI 遵守规则或硬件设计正确。"
}
```

`scan` 退出码：`errors>0` → 1；仅有 warning/info → 0；输入/IO → 2。

## 5. D2 规则结构化与潜在冲突

### 5.1 规则记录

```json
{"rule_id":"R-SKILL-001","text":"原文（≤500字符，保留省略标记）",
 "source":{"path":"easycirq/SKILL.md","line_start":96,"line_end":96,"quote_sha256":"..."},
 "condition":"用户说“确认后再布线”","task_scope":["schematic","pcb"],
 "action":"在对应边界等待用户确认","strength":"must|should|may|unknown",
 "exception":"任务已授权范围内自查并继续","evidence_required":["用户明确要求暂停"],
 "priority_declared":"项目专属约束优先","version_applicability":"v1.0.1",
 "provenance":"machine_extracted|maintainer_declared|inferred",
 "extraction":{"method":"pattern|curated|manual","confidence":"high|medium|low","notes":"..."}}
```

`provenance=inferred` 的字段（尤其 condition/exception）必须是 `unknown` 或
带“推测”标记，不得编造意图。`machine_extracted` 规则来自确定性正则，
`maintainer_declared` 必须来自真实读过的原文并由人工/模型审查记录。

### 5.2 抽取候选

沿 `SKILL.md` 与 references 中明确祈使句抽取：`必须/不得/务必/先/应/禁止/
需要/优先/默认/只有/仅当`，以及 `must/should/never/always/only`。每条保留
原文与行号；条件从句用确定性标记提取（`当/如果/若/除非/...时/when/if/unless`），
抽不出则 `condition:"unknown"`，不猜。

### 5.3 冲突候选与审查关系

`candidates` 只由确定性特征产生：动作族（APPROVAL/AUTONOMOUS、FULL_LOAD/
ON_DEMAND、DIRECT_WIRE/LABEL、STRICT/PERMISSIVE 等）、任务范围词、阶段词、
例外词、否定/引用/代码示例标记。字符串相似或矛盾关键词只能产生
`candidate`，**不得**输出 `confirmed_conflict`。

已审查关系来自 `catalog/rules.json` 的 `relations`，每条必须有：

```json
{"pair_id":"REL-001","rule_ids":["R-...","R-..."],
 "classification":"true_conflict|default_with_exception|different_stage|different_scope|stale_reference|ambiguity|user_authorized|technical_limit|negation|code_example|coexist",
 "overlap":{"condition":"两段条件如何重叠","scope":"..."},
 "scenario":"会同时触发的具体场景","exception":"是否/由谁覆盖",
 "resolution":"给维护者的 proposal（不是事实修复）",
 "evidence":[{"path":"...","line":96,"quote":"..."}]}
```

分类判定顺序（同时用于夹具评估）：

1. `code_example` / `negation`：引用代码或否定句使表象对立消解；
2. `different_scope`：任务范围词不相交（原理图 vs 制造等）；
3. `different_stage`：阶段词不相交（开工前 vs 布局后）；
4. `default_with_exception`：一方含 `除非/仅当/例外/except/unless` 且覆盖另一方；
5. `user_authorized`：一方以用户明确授权/要求为条件；
6. `technical_limit`：一方是工具/通道能力限制，另一方是设计偏好；
7. `stale_reference`：一方引用旧版本/已废弃路径；
8. `true_conflict`：动作族相反、条件与范围重叠、均非历史/示例/否定，
   且没有覆盖例外；仍需列出两段原文；
9. `ambiguity`：条件或意图无法确定，只能给待确认；
10. 其余 `coexist`。

`rules` 命令输出 `rules`（机器候选 + 目录记录）、`candidates`、
`reviewed_relations`、`fixtures`（分类准确率）、`summary`。退出码：目录
非法/重复 ID/空全集 → 2；`--strict` 且夹具分类错误 → 1；否则 0。

### 5.4 夹具

`catalog/rule_fixtures.json` 至少 12 对，覆盖：真冲突、默认+例外、不同阶段、
不同工程范围、引用过时、语言歧义、用户授权条件、技术限制、否定句、代码
示例、中英混合、跨段条件。每项含 `pair_id`、`a`、`b`（`text` + 可选
`source/line`）、`expected`、`rationale`、`synthetic`（是否构造文本）。
夹具只用于测试分类算法，不代表真实 Skill 存在该冲突。

实际冻结位置：`benchmarks/skill-knowledge-audit/fixtures/rule-pairs.json`（16 对，
覆盖全部 12 类；非构造引文逐条核到行）。

## 6. D3 任务驱动的最小阅读计划

### 6.1 intent

```json
{"schema":"ska-intent/v1","task_type":"schematic_new|schematic_edit|pcb_layout|pcb_route|four_layer_diff|bom_only|review_only|delivery_audit|offline_dev|full_product|knowledge_only",
 "stage":"read|requirements|concept|schematic|layout|route|check|delivery|firmware|build|unknown",
 "autonomous_authorized":true,"eda_available":false,"deliverables":["schematic"],
 "constraints":["keep mechanical outline"],"user_decision_pending":[],
 "already_read":[{"path":"easycirq/SKILL.md","sha256":"...","rules_version":"...","scope":"..."}],
 "budget_chars":120000,"notes":"..."}
```

任务类型可由中文/英文同义词映射（`原理图新建`、`局部改图`、`PCB布局`、
`四层差分`、`仅BOM`、`仅评审`、`离线开发` 等）；映射表在 `topics.json`，
未知词不猜，归 `task_type:"unknown"` 并输出 `unknown`。

### 6.2 计划

选择顺序：

1. `always` 保护主题（身份/目标绑定/证据真实性/事实状态），对任务类型适用
   即 required，不因预算或“更快”省略；
2. 任务类型 + 阶段匹配的主题（文件角色 required/conditional/optional）；
3. 沿选中文件的显式 `required_read` 边做闭包（深度 ≤3，越深标 unknown）；
4. 后续阶段只进 `next_stage_entry`，不预加载；
5. 排除主题（如仅 BOM 排除布线与热设计、仅评审排除写工程步骤）进
   `excluded` 并附理由；
6. 信息不足（未知领域、EDA 不可用导致无法回读、预算不足）进 `unknown`，
   `status` 为 `incomplete`，列出未覆盖关键要求。

输出字段：`required`、`conditional`、`optional`、`excluded`、`unknown`，
每项含 `path`、`bytes`、`chars`、`role`、`reasons`、`rule_ids`、`topic`、
`selected`。`unknown` 项含机器可判定 `code`：
`task_unknown`、`stage_unspecified`、`domain_unspecified`、`eda_unavailable`、
`budget_insufficient`、`cache_invalidated`、`file_missing`、
`required_dependency_missing`、`already_read_stale`。

`execution_contract` 描述计划允许的动作（不执行）：
`{"actions":["read_skill","write_eda","read_eda","network","install","wait_user_approval","review_only","offline_analysis","order_parts"],"writes_allowed":false,"eda_required":false,"approval_gates":[],"decisions_required":[]}`。
`approval_gates` 只列用户明确要求或新增范围决策，不因“默认谨慎”自动插入。

`protected_constraints` 记录关键保护是否包含。`budget` 含
`limit_chars`、`required_chars`、`selected_chars`、`files`、`bytes`、
`token_estimate`（`low/high/method:"char-class heuristic, not a tokenizer"`，
中文 0.5–1.0 token/字、ASCII 0.25–0.5 token/字符）、`status`
（`within|exceeds|incomplete`）、`uncovered`。`not_proof` 说明计划只导航。

授权自主：不得自动生成“等待用户批准”步骤；但出现 `user_decision_pending`
（接口/尺寸/成本目标变化、新增范围）时列出 `decisions_required`。

纯离线/仅评审：`writes_allowed=false`，计划中不得有写工程步骤；EDA 文档
只作条件/排除，不要求连接。

### 6.3 缓存

`--cache-out` 写 `{"schema":"ska-cache/v1","catalog_version":"...","entries":{...}}`；
每条绑定 `path`、`sha256`、`rules_version`、`task_scope_hash`。读取时重新
计算哈希：文件变化、目录版本变化、任务扩展（scope hash 变化）都必须失效；
不使用 mtime。输出 `cache.hit/miss/invalidated[{path,reason}]`。

### 6.4 预算

`budget_chars` 按字符计（文件 chars），同时报告字节。非整数、bool、NaN、
Infinity、负数 → 2。required 超预算时**不裁剪** required，标
`status:"incomplete"` 并列出 `uncovered`；conditional/optional 按顺序装入
直到超预算。

## 7. D5 场景与基准

### 7.1 场景

`benchmarks/skill-knowledge-audit/scenarios/dev.json`、`holdout.json`：

```json
{"schema":"ska-scenarios/v1","split":"dev","frozen":{"git_sha":"...","catalog_version":"..."},
 "scenarios":[{"id":"dev-01","title":"...","intent":{...},
   "expected":{"must_include":["easycirq/references/evidence.md"],
               "must_exclude":["easycirq/references/pcb-routing-details.md"],
               "may_include":["..."],"required_unknown":["eda_unavailable"],
               "forbidden_plan_actions":["write_eda"],
               "required_approval_gates":[],
               "max_selected_bytes":0},
   "rationale":"为什么这些约束适用（不能只抄 planner 输出）"}]}
```

至少 18 个场景（实际冻结：dev 15 + holdout 5 = 20），覆盖任务书第 8 节全部类型。
holdout 由未看实现的独立评阅者/第二阶段设计，使用不同措辞；实现不得按场景编号
分支。`must_include` 是必要规则覆盖；遗漏任一 → 场景失败（`missing_critical`
>0），基准总退出 1。`required_unknown` 与 `required_approval_gates` 为期望
子集；`forbidden_plan_actions` 命中即失败。

### 7.2 指标

每个场景：`required_recall`、`missing_critical`、`forbidden_selected`、
`unknown_expected_missing`、`unrelated_bytes`（选中但不在
`must_include ∪ may_include` 的字节）、`selected_bytes`、
`baseline_all_markdown_bytes`、`budget_status`、`stable`（两次运行计划
digest 相同）、`duration_ms`。总基准比较“全部可达参考资料”策略与最小计划，
明确标注全量路径只是基线策略，不是用户先前实际执行；减少阅读量不等于
画板提速，端到端 NOT RUN。

### 7.3 变形与负例

变形（`--transforms`）：文件排序/换行、增加普通背景链接、标题更名、
内容哈希变化、任务同义表达、否定/条件变化、预算变小、外部修改。断言
必要规则覆盖不因无关变化下降；结果可重复。负例：路径遍历、越界符号链接、
超大输入、NaN/bool 预算、重复规则 ID、空规则全集、非法 JSON、旧输出
残留——都必须明确失败（退出 2/1），不得沿用 PASS。

## 8. 真实审计与报告（D4）

固定基线跑 `scan`、`rules`、`plan`（多 intent）、`benchmark`，结果冻结在
`benchmarks/skill-knowledge-audit/results/`。建议最多 10 条，每条含：触发
场景、原文位置、影响、建议变化、是否改变工程保护、验证场景。所有结论必须
来自本次实际读过的文件；找不到确定冲突时报告“未发现”，保留候选与已反驳
记录。机器清单另存，不把候选当已确认冲突。

## 9. 验收

见 `acceptance-matrix.md`。最低线：CLI 可运行、真实扫描报告、12 对夹具、
18+ 场景（≥4 holdout）、0 关键保护遗漏、测试通过、PR 创建。任何未实测项
（模型行为、EDA、3.10 运行时）必须写 NOT RUN / 未验证。

## 10. M1–M3 实施决策记录（冻结补充，与上文同等有效）

为避免并行开发歧义，实施时确认以下口径；后续改动必须同步本文件。

1. **always 集**：`SKILL.md` + `references/workflow.md` + `references/evidence.md`
   对所有非 `knowledge_only` 任务 required；`agent-collaboration.md` 只在
   full_product/多步骤任务按主题选；`design-gates.md` 对 SCH/PCB/交付类任务 required。
   依据 `SKILL.md:134` 的“始终遵循”只覆盖 workflow/evidence 两个文件。
2. **审批门 token**：`before_layout`、`before_route`、`before_delivery`、
   `before_manufacturing`、`scope_change`、`interface_change`、`cost_change`、
   `mechanical_change`、`missing_evidence`。planner 只复制 `intent.user_decision_pending`
   的合法 token，不自行推断；`wait_user_approval` 动作只在出现 `before_*` 门时加入，
   `scope_change` 等只进 `decisions_required`。
3. **依赖闭包**：从主题选中的文档（不含 `SKILL.md` 入口）沿显式 `required_read`
   边展开，深度 ≤2；命中主题 exclude 的目标不加入。入口自身的“先读”由主题映射
   决定，避免把全表链接误当全局必读。
4. **锚点约定**：精确 slug 匹配优先；仅前缀命中记 `anchor_prefix_match`，
   仅 Unicode NFKC 折叠命中记 `anchor_compat_match`，两者均为 warning 而非
   broken；外链不判失效。当前固定基线有 15 + 1 条此类结构警告。
5. **场景数量**：dev 15 + holdout 5；holdout 由独立评阅者设计。基准对
   `must_include` 缺失、`must_exclude` 命中、禁止动作、缺 unknown/门、
   两次运行不稳定判失败；预算 `incomplete` 由场景 `required_unknown` 决定是否失败
   （holdout-02 的预算缺口已在 `report.md` 作为已知覆盖缺口披露）。
6. **输出隔离**：CLI 文档与测试/结果均在 `easycirq` 扫描根之外；
   `scan`/`rules`/`plan`/`benchmark` 的 `--out` 与 `--cache-out` 落在根内时
   直接报错（退出 2），因此任意后续扫描都不会读到本任务输出。
7. **规则证据**：`rules` 每次运行都校验 `catalog/rules.json` 的已审引文与
   非构造夹具引文；引用或行号不符直接退出 2，不沿用旧结果。
8. **Python**：仅标准库，3.10+ 语法；本机 3.13.15 实测；CI 已实际运行
   3.10/3.13 并通过（PR #45），本机未直接运行 3.10。
9. **EDA 任务集**：`schematic_new`、`schematic_edit`、`pcb_layout`、`pcb_route`、
   `full_product` 都要求“先读后写”；EDA 可用时 actions 同时含 `read_eda` 与
   `write_eda`，EDA 不可用时 `writes_allowed=false` 并产出 `eda_unavailable`。
   纯 `review_only`/`bom_only`/`offline_dev` 不要求 EDA。
10. **基准下限**：`benchmark --split all` 默认强制 ≥18 场景、≥4 holdout，并在结果
    `requirements` 记录；`--split dev|holdout` 用于聚焦运行时不受此下限约束。
    指标字段名与 §7.2 对齐：`unknown_expected_missing`、`baseline_all_markdown_bytes`、
    `selected_vs_baseline_ratio`；另输出 `budget_incomplete_total` 与
    `plan_ok_false_total`。`ok/pass` 不代表计划预算完整。
11. **输出排除**：`scan`/`rules`/`plan`/`benchmark` 的 `--out` 与 `--cache-out`
    若位于扫描根内，均自动加入排除集，防止报告自我污染。
