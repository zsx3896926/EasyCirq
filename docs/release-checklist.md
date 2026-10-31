# 发版检查单

> 发版不是「跑一遍 build_release 就完了」。这份单子记录**必须逐条核对**的动作，
> 以及每条为什么存在——每一条背后都有一次真实事故。

## 一、必跑的三条命令

```bash
# 1. 打包
python distribution/build_release.py --toolchain-only \
  --toolchain-version <V> \
  --connector-build never \
  --runtime-exe <安装目录>/easycirq.exe \
  --require-clean --output dist-release

# 2. 隔离安装并自检
python distribution/easycirq_install.py install \
  --bundle dist-release/easycirq-toolchain-<V>.zip \
  --install-dir <tmp>/app --state-dir <tmp>/state --home <tmp>/home \
  --skill-client none --no-self-check
python distribution/easycirq_install.py verify --install-dir <tmp>/app

# 3. 内容一致性（不是版本号一致性）
python tools/check_release_consistency.py
```

## 一之二、两个基准自测（也必跑）

这两个脚本本身没有单测——它们的输出就是验证：

\\ash
python easycirq/scripts/schematic_benchmark.py          # 期望 status=ok, 8/8
python easycirq/scripts/pcb_placement_benchmark.py --all # 期望每个案例 OK
\
它们检查的是**布局判断能力**（去耦回路过长、功率回路、模拟区分离等），
不是代码正确性。改过布局相关代码后必须重跑：这两个过了，说明判断规则没被改坏。

## 二、为什么还要第 3 条（内容一致性）

第 3 条的输出必须是：

```
== repo vs bundle payload ==   all 12 key files equal
== repo vs installed ==        all 12 key files equal
CONSISTENT
```

## 二、为什么要第 3 条

**事故**：1.3.2 的 bundle 版本号是对的，但 payload 里的
`scripts/easycirq_mcp/runners.py`、`tools.py`、`sch_delivery_card.py`
都是**提交之前**的版本——三个文件都缺 `pcb_drc` 支持。

装 1.3.2 的人会拿到「✅ 原理图可以打样（PCB 未检查）」，而这正是那一版声称已修好的误导。

**结论**：版本号一致 ≠ 内容一致。必须比内容哈希。

## 三、这条检查自己也踩过坑

第一次运行时报了 12 个 MISSING，原因是它挑了
`easycirq-toolchain-installer-<V>.zip`（安装器包装），payload 嵌套结构不同。

已修：排除名字含 `installer` 的包。

**教训**：检查工具本身也要先验证一次——一个永远报错的检查器，和没有检查器一样糟。

## 四、同步技能副本：必须全量，不能只同步改过的文件

```powershell
Copy-Item easycirq/* ~/.agents/skills/easycirq -Recurse -Force
```

**为什么必须全量**：2026-11-01 把一致性检查从 12 个文件扩到 327 个时发现，
技能副本里有 **256 个文件内容过时**——因为过去每次只复制「当轮改过的文件」。
用户实际在 agents 客户端用的是那些旧副本。

检查命令（必须全绿）：

```bash
python tools/check_release_consistency.py   # 期望 all 327 key files equal
```

## 五、同步技能副本的正确姿势

```powershell
# 用字节复制，不要用 Get-Content/Set-Content（会改换行）
Copy-Item easycirq/SKILL.md ~/.agents/skills/easycirq/SKILL.md -Force

# 改过哪些文件就复制哪些 —— 但别只复制"这一轮改的"
# sch_wire_metrics.py 就这样漏了好几轮，直到一致性检查才抓到
```

同步后跑两份 `skill_selftest.py`，都必须 6 PASS。

**不要只同步「本轮改过的文件」**——之前改过但忘了同步的，会因为没人看而一直漂移。

## 五、装机与打包的顺序

1. 先构建 runtime 到安装目录（用正确版本号）
2. 重启 daemon 并确认 connector 已连接
3. 跑一遍客户四命令（setup / status / card / acceptance）
4. **再**打包（bundle 用的是安装目录里的 exe）

顺序反了会打出旧二进制。

## 六、发版后

| 检查 | 命令 | 期望 |
|---|---|---|
| 装机版本 | `easycirq version` | 新版本号 |
| 健康 | `easycirq doctor` | `verdict: ok` |
| 客户命令 | `easycirq setup` | 四行全 ✓ |
| 一致性 | `tools/check_release_consistency.py` | `CONSISTENT` |

## 七、明确不做

- 不发没跑过 `verify` 的包。
- 不在工作树脏的时候打包（`--require-clean` 会拒绝，别绕过）。
- 不用版本号替代内容检查。
- 不因为检查器报错就删检查器——先确认检查器本身是对的。
