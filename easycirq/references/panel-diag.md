# 面板与诊断包

> `easycirq panel` / `easycirq diag` —— 把已经存在的东西做得看得见。
> 目标见 `docs/goal-easycirq-product.md`。

---

## 一、面板解决什么问题

现在这些东西**都存在但看不见**：

| 已有 | 以前怎么看 | 问题 |
|---|---|---|
| 相位机 S0–DELIVER | `easycirq phase show` | 要记参数、认 JSON |
| 证据状态 | 同上 | `blocked` 和 `pending` 的区别只有读过代码的人知道 |
| 交付卡 | `easycirq card` | 纯文本，数字不好比 |
| 循环的拒绝理由 | `run` 的 stdout | **跑完就没了，"刚才为什么被拒"查不到** |

**面板只解决一件事：让「拒绝」和「缺证据」不可能被忽略。**

---

## 二、怎么用

```powershell
easycirq panel                       # 自动选端口并打开浏览器
easycirq panel --no-open             # 只打印 URL
easycirq panel --project <uuid>      # 指定工程
easycirq panel --port 23115          # 指定端口（被占用则报错，不会悄悄换）
```

启动后打印确切地址，例如：

```
面板已启动：http://127.0.0.1:23112/
（只监听 127.0.0.1；Ctrl+C 停止。关掉面板不影响 easycirq 命令。）
```

---

## 三、界面上有什么

### ① 概览：三秒可判

```
这块板能不能下单
⏳ 这块板还没检查过
把你想做的板子说给 AI 听就行；画完并检查过之后，这里会告诉你能不能打样

必查通过 0    未通过 0    缺证据 0    提醒 0
```

判词只有三种：`可以下单` / `还不能下单` / `还没检查过`。**没有第四种，也不模糊。**

### ② 相位条：五态 + 未接门

```
S0    S1    S2    S3    S4    S5    S6    交付
需求   图纸   编组   摆放   布线   校验   存盘   交付
 ✓通过 ✓通过 ✓通过 ✓通过 ✓通过 ○还没跑 – 未接门 – 未接门
```

| 状态 | 颜色 | 图标 | 含义 |
|---|---|---|---|
| `pass` | 绿 | ✓ | 有证据，且通过 |
| `fail` | 红 | ✕ | 跑了，但没通过 |
| `blocked` | 黄 | ! | 检查器没跑成（如 EDA 没连上）。**这不等于通过** |
| `pending` | 灰 | ○ | 有门但还没跑。**也不等于通过** |
| `stale` | 紫 | ⟳ | 板子改过，之前的证据已失效 |
| `unenforced` | 虚线灰 | – | 该相位还没接门：不阻塞，也不算通过 |

**颜色 + 文字 + 图标三者同时给**——只给颜色，色盲用户读不出来。

---

## 四、设计铁律（写在代码注释里，因为最容易被破坏）

### 1. 面板零判定逻辑

它不判断"能不能交付"，只把 `easycirq phase show --json` 和 `easycirq card --json`
的结果原样搬到浏览器。一旦这里出现第二套判断，就会有两个真相来源，**而用户看到的那个可能是错的**。

实现上：`/api/snapshot` 的每个字段都是 `json.RawMessage` —— 不解析、不汇总、不判断，只是搬运。

### 2. 只监听 `127.0.0.1`

显式写死 `"127.0.0.1:"` 而不是 `":"`。后者等于 `0.0.0.0`，**同一办公网里任何人都能看到你的板子和设计数据**。
这不是可配置项。

### 3. 面板挂了不影响 CLI

两者是独立进程，面板只是 CLI 的一个消费者。杀掉面板，`easycirq phase` 照常。

### 4. 页面 embed 进二进制

客户机不该为了看一眼状态去装 node。`//go:embed panel/index.html`，装完就有。

---

## 五、踩过的一个坑（值得记）

`card` 和 `status` 用**退出码**表达语义：`0` 可以下单 / `1` 不行 / `2` 还没检查过。
而 **exit 2 时它们照样打印完整 JSON**。

第一版把"非零退出"当成失败，直接丢弃了 stdout —— 结果面板永远显示不出
「还没检查过」这张卡，**而这恰恰是这层界面最该说清的状态**。

现在的规则：**只要 stdout 是合法 JSON 就用它**，退出码只管"命令有没有正常结束"。

---

## 六、诊断包

```powershell
easycirq diag
easycirq diag --out D:\tmp\easycirq-diag.zip
```

### 里面有什么

| 文件 | 内容 |
|---|---|
| `manifest.json` | 版本、连接器版本、平台、生成时间、**收了什么/没收录什么** |
| `README.txt` | 给人看的说明：这个包有什么、没有什么 |
| `doctor.txt` | `easycirq doctor` 的输出 |
| `phase.json` | 各相位的证据**状态**与板子指纹 |
| `env.json` | 少量环境变量（目录、编码）|

### 里面**没有**什么

- 网表内容
- 原理图 / BOM 内容
- 任何 API key、令牌、密码

### 为什么能保证

设计原则是**「默认不含」，不是「默认全含再删」**：

- 环境变量走**白名单**，不 dump 全部再过滤——过滤表永远会漏掉新加的变量
- 网表/原理图/BOM **根本不读**，不是读了再删
- 证据文件**按字段白名单挑**（`schema`/`phase`/`fingerprint`/`evidence` 的状态），
  未来加了别的字段也不会被无意带出去

**测试是"先把秘密放进去，再断言它没被带出来"**（`tests/test_diag_bundle.py`）：
故意往环境里放四个假密钥、往证据文件里塞一份假网表，然后扫描整个 zip。
只断言"README 里写了不含"等于相信承诺，不算验证。

---

## 七、验证

```powershell
python -m pytest tests/test_panel.py tests/test_diag_bundle.py -q
```

| 判据 | 测试 |
|---|---|
| A1 起得来、打印 URL | `test_panel_serves_the_page` |
| A2 只监听 loopback | `test_panel_listens_on_loopback_only`、`test_panel_is_not_reachable_on_a_non_loopback_address` |
| A5 exit=2 显示"还没检查过" | `test_snapshot_carries_not_measured_instead_of_an_error` |
| A9 杀面板 CLI 照常 | `test_cli_still_works_after_the_panel_dies` |
| A10 装完无构建步骤 | `test_page_is_embedded_never_read_from_disk` |
| 五态不为绿 | `test_non_pass_states_never_borrow_the_pass_class` |
| C19 诊断包脱敏 | `test_bundle_carries_no_secrets` 等 7 条 |
| B15 无遥测 | `test_panel_and_diag_never_call_out` |

---

## 八、还没做的

| 没做 | 说明 |
|---|---|
| 证据详情抽屉（点一格看 `howToFix`）| P1 剩余部分 |
| Agent 工作面（对话流、拒绝高亮）| P2 |
| 跑门 / 推进按钮 | P3 |
| 首次运行引导 | P4 |
| 深浅色已实现（跟随系统），但**未做过视觉走查** | P4 |
