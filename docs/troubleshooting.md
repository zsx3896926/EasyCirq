# 排查记录

## 指标 1 的真实测量（2026-11-01，两段）

`tools/measure_first_use.py`，两段分开测，因为一整段在单机上做不干净：

```
bundle: easycirq-toolchain-1.3.38.zip

A1 install        2.55s  exit=0
A2 version        1.22s
A3 setup          0.10s

B  dispatch       1.79s  exit=1  audit lines 91348 -> 91349 (+1)

A+B = 4.34s（不含 EasyEDA 安装与插件导入）
```

### 三段结论

**1. A 段（解包 + 只读检查）可完全隔离，4.87s 里占 3.87s。**
在临时 HOME 里跑，不碰真实目录。

**2. 派发失败也会写审计。**
B 段的 `sch list` 缺 `--page` 参数，`exit=1`，但审计行数 **91348 → 91349（+1）**。
这是好消息：**「第一条审计」不要求一次成功的操作**，一次被记录的派发尝试就算。

**3. 完整指标 1 里最大的一段，我测不到。**
「装 EasyEDA 本体 + 导入插件 + 连接」是人工操作：下载安装 EasyEDA Pro、
导入 `.eext`、在插件设置里允许外部交互、重启 EasyEDA。

**这一段对首次使用者是分钟级的**，所以：

> 指标 1「首次可用时间 ≤5 分钟」只有在**不计 EasyEDA 安装与插件导入**时才成立。
> 如果对"首次可用"的理解包含装 EDA 本体，**5 分钟不可能达成**，目标值需要重新定义。

这不是我能替目标判定的——**它取决于"首次可用"从哪一步开始算**。

### B 段为什么不能隔离

`daemon start` 被 subprocess 拉起时**不返回**（实测 120s 超时，加 `DEVNULL` 也一样），
它是前台进程。而隔离 HOME 里的 daemon 拿不到 EasyEDA 连接，派发必然失败。
所以 B 段在真实环境跑，用"审计行数增减"确认，而不是靠隔离目录。

## 侧记：审计日志已经 2.6 GB

```
~/.easycirq/audit/2026-10-31.jsonl      2150.9 MB
~/.easycirq/audit/2026-11-01.jsonl         0.2 MB
```

`easycirq audit prune` 就是为这个写的（2026-11-01 加），默认 `--max-total-gb 2`。
长期跑下去需要它自动执行，否则单日文件会一直涨。

## 我这次自己制造的故障（值得记）

为了给指标 1 造一个隔离环境，我在 23190 端口起了第二个 daemon，
想用 `$env:USERPROFILE` 把它指到临时目录。**结果 `$env:HOME` 在 Windows 上是只读变量**，
隔离没生效，那个 daemon 把记录写进了**真实**的 `~/.easycirq/audit/`。

停了它之后，pid 文件里留下的是已经死掉的 pid，于是：

```
easycirq doctor
  verdict: degraded
  nextSteps: ["pid 文件（37496）与运行实例（21536）不一致：daemon 可能非正常退出过…"]
```

**doctor 说得很清楚**——是我先没看到（当时只 grep 了 `verdict` 和 `degraded`，
没看 `nextSteps`）。`easycirq daemon restart` 之后恢复 `verdict: ok`。

### 两个可以改进的点

1. **`doctor` 同时往 stdout 打 JSON、往 stderr 打人读摘要**，在终端里两股流会互相
   穿插成乱码。要么加 `--json` 让人选，要么摘要里不带 JSON。
2. **隔离测量需要真的隔离 HOME**：Windows 上不能改 `$env:HOME`，
   要靠进程级环境变量或 `--home` 之类参数，否则会污染真实目录。
