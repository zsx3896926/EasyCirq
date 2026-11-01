# 排查记录

## 指标 1 的真实测量：装到「第一条审计」

**结论：单独测安装是 3.65s，但那不是指标 1。**

用 `tools/measure_first_use.py` 在隔离目录里跑：

```
bundle: easycirq-toolchain-1.3.38.zip
1. install     2.35s  exit=0
2. version     1.16s  exit=0
3. setup       0.09s  exit=0  audit files 0 -> 0
4. action      0.06s  exit=0  audit files 0 -> 0
total 3.65s   target <= 300s   OK
```

**第 3、4 步没有产生任何审计文件。** 原因：`setup` 与 `capabilities` 都是本地只读，
不经过 daemon 派发，而审计只在派发时才写。

所以指标 1 的准确定义应该是：

> **装到第一条审计 = 从解包完成，到第一次 daemon 派发动作被记入 `~/.easycirq/audit/`。**

那需要：启动 daemon + EDA 连上 + 做一次真实读写。**这一整段我没有计时。**
所以指标 1 现在只能报「安装与只读检查 3.65s」，**不能报「≤5 分钟达成」**。

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
