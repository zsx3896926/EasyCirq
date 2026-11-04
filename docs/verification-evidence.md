# 四条工作流的验收证据（重跑实录）

> 2026-11-04。本文件把每条终态的**实际命令与实际输出**集中在一处。
> 未跑的明确标 NOT RUN。所有输出都是本次运行的真实结果，不是回忆。

---

## A｜规模天花板

### A① 分块缓冲：**实现了，两条路径产物逐字节相同，但实测不划算 → 默认关闭**

实现：`_astar_c.pyx` 增加页表后端。`nodes > EASYCIRQ_ASTAR_DENSE_LIMIT` 时走
4 张页表 + `calloc` 按需分配；读写一律走 inline 访问器，**搜索逻辑一个字没改**。

**等价性证明**（两条路径同产物）：

```
$ EASYCIRQ_ASTAR_C=1 python easycirq/scripts/layout/equivalence.py --iters 3 --compare
  retrocam/frontier-i      plan identical (27a311f6f7f3332e…)
  selftest                 plan identical (d0c7ef5bdac4863c…)
等价性门禁：全部 spot 产物逐字节相同

$ EASYCIRQ_ASTAR_DENSE_LIMIT=0 python3 …/equivalence.py --iters 3 --compare   # 强制分块
  retrocam/frontier-i      plan identical (27a311f6f7f3332e…)
  selftest                 plan identical (d0c7ef5bdac4863c…)
等价性门禁：全部 spot 产物逐字节相同
```

**实测不划算**（`scale_bench.py --mode area`）：

| 档位 | 稠密峰值 | 分块峰值 | 省 | 稠密耗时 | 分块耗时 |
|---|---|---|---|---|---|
| x4 | 1,880 MB | 1,787 MB | 5% | 42.9 s | 46.6 s（**慢 9%**）|
| x8 | 7,027 MB | 6,851 MB | 2.5% | 143.5 s | 174.4 s（**慢 20%**）|

原因：一次 route 的 143 次检索并集会碰到大部分页，**没有稀疏性可利用**，
只多一层间接寻址。**所以默认关闭**（阈值设为实际不可达），
`EASYCIRQ_ASTAR_DENSE_LIMIT=<节点数>` 可开。

### A②③ 曲线与客户可懂的失效点

| 档位 | 节点 | 峰值 | 耗时(iters=1) | 状态 |
|---|---|---|---|---|
| x1 | 0.81 M | 186 MB | 4.95 s | 实测 |
| x2 | 3.36 M | 546 MB | 14.5 s | 实测 |
| x4 | 13.7 M | 1,880 MB | 42.9 s | 实测 |
| x8 | 55.3 M | 7,027 MB | 143.5 s | 实测 |
| x16 | ~221 M | ~28 GB（外推）| — | **NOT RUN**（可用 16.9 GB）|

**客户可懂的一句话**：16 GB 内存的机器上约 **1.2 亿节点**以内；
超了在动手前明确报错，不会跑到一半崩掉。

**入口预检反证**：

```
$ EASYCIRQ_MAX_NODES=1000 python easycirq/scripts/layout/scale_bench.py --mode area --factors 2
[area x2] FAIL MemoryError peak=41.0MB      ← 41 MB 就停，没走到分配
```

### A 的判据：改动前后两道闸

```
$ python easycirq/scripts/layout/bench.py --iters 3 --compare     # 含规模预检的版本
| retrocam/frontier-i | 53.5s vs 16.6s (3.22x) | same KPI |
| retrocam/frontier-i-fast | 11.9s vs 3.7s (3.22x) | same KPI |
| second-2layer | 2.1s vs 0.8s (2.62x) | same KPI |
| selftest | 0.1s vs 0.1s (1.00x) | same KPI |
identical KPI fingerprint
```

```
$ python easycirq/scripts/layout/scale_bench.py --mode area --factors 1,2 --iters 1   # 小档位不退化
| area x1 | OK | 536x378x4 | 810432 | 55 | 432 | 15 | 237 | 4.72s | 188.4 MB |
| area x2 | OK | 1088x773x4 | 3364096 | 55 | 425 | 10 | 108 | 14.5s | 544.1 MB |
```
（改动前：x1 4.95 s / 186.4 MB，x2 14.5 s / 546.2 MB —— 无退化，差值在测量噪声内）

---

## B｜剩余 34% 时间

### B① 归因（已在上文，见 `docs/time-attribution.md`）

x1→x4 总耗时 ×25.8 = **4.0（网络）× 1.62（重试）× 3.9（板变大）**；
单次 A* 归一化 **17.4 → 15.9 → 15.0 ms/M节点**（随规模变好，无规模病态）。

### B② `path_conflicts` 结论

占 route 的 **41%**；其中最显眼的浪费（重算 `board.center`）实测仅 **3%**
（2.84 M 次 / 0.34 s of 13.01 s），**不做**；空间索引是真正杠杆但属独立改动，**NOT DONE**。

### B③ 交付档位（25 轮）

**小板**：
```
$ python easycirq/scripts/layout/bench.py --iters 25
retrocam/frontier-i       25 iters   123.7s  tracks 550  clearance 146  CAM 837.8
retrocam/frontier-i-fast  25 iters    24.2s  tracks 494  clearance 225  CAM 621.4
```

**放大板**（`scale_bench --mode nets --factors 2`，110 网络 / 1.71 M 节点）：
```
| nets x2 | OK | 1129x378x4 | 1707048 | 110 | 1529 | 4 | 767 | 912.98s | 396.6 MB |
```
**25 轮 = 912.98 s（15.2 分钟）**。

**70 轮：NOT RUN。** 原因：按 25 轮 913 s 线性推算约 42 分钟，单次运行超出本轮时间预算；
且 25 轮已足以给出交付量级。**不外推成结论。**

---

## D｜Python 依赖

### D① 包内嵌解释器

```
$ python distribution/easycirq_install.py inspect-bundle --bundle dist-release/easycirq-toolchain-1.3.80.zip
  version: "1.3.80"
  verdict: "ok"
  corrupt: []
  files: 962
  组件: ['connector', 'python', 'runtime', 'skill']
  components.python: {"name":"cpython-embed","version":"3.13.0","path":"payload/python",
                      "installPath":"python","fileCount":37,"size":24538766}
```
`payload/python/` **37 个文件 / 24.5 MB**，含 `python/python.exe`。

### D②③ 无 Python 时照常工作 + 明确指路

```
PATH 上 python=False  py=False        ← 已把 python/python3/py 从 PATH 全部剔除
$ easycirq enterprise check --netlist …/21-enterprise-violations.json
  exit=1（规则命中）
  企业规则判定：fail
    ✗ no-0402-packaging     禁用 0402 封装   [hard] R1 的封装是 R0402
    ✗ banned-transistor     禁用已停产器件 S8050 [hard] R1 的器件是 s8050
    ✗ no-test-net-naming    网络名不要用 TEST 前缀 [advisory]
```

**反证**（关掉自带解释器，PATH 上也没有）：

```
$ EASYCIRQ_NO_BUNDLED_PYTHON=1 easycirq enterprise check …
  exit=1
  no Python 3 interpreter found (tried the bundled python, then: python3, python, py -3);
  the toolchain ships one under <install>/python — if that directory is missing the
  install is incomplete, otherwise install Python 3 and put it on PATH, or set EASYCIRQ_PYTHON
```

→ 证明是**自带解释器**在起作用，不是机器上碰巧还有别的 Python。

---

## E｜历史工程 → 规则

### E① 聚类候选

```
$ easycirq enterprise harvest --drc ../retrocam-02/pcb --dump ../retrocam-02/pcb/dump2.json \
    --out reports/harvest-candidates.json
  读入 25 份，失败 1 份，非 DRC 已跳过 29 份，警告 11 条
  违规总数 3500，分成 16 类；带位号 2730 条（78%），不带 770 条
  三、候选（**必须人审，工具不采纳**）
    HARVEST-U5 → 禁用器件 ESP32-S3-WROOM-1（历史 DRC 高频）
      谓词: {'type': 'part_forbidden', 'parts': ['ESP32-S3-WROOM-1']}
    HARVEST-J3 → 禁用器件 FPC0.52H-WS-24P（历史 DRC 高频）
      谓词: {'type': 'part_forbidden', 'parts': ['FPC0.52H-WS-24P']}
  条目数: 2   | 有 disposition: False | 证据: U5 554 次 / J3 514 次
```

### E② 未人审时 promote 必须拒绝

```
$ python easycirq/scripts/review_ledger.py --ledger cand.json --promote --target lib
  exit: 2
  没有写入：
    ! entries[0]: disposition 必须是 rule 或 knowledge（实际 None）。**必须显式选边**
    ! entries[1]: disposition 必须是 rule 或 knowledge（实际 None）。**必须显式选边**
  库目录被创建了吗: False
```

### E③ 回放必须命中

```
$ python easycirq/scripts/enterprise_harvest.py --replay reports/harvest-candidates.json \
    --dump ../retrocam-02/pcb/dump2.json
  回放（用产生候选的那份 dump 重建最小网表，跑真正的规则引擎）
    ✓ HARVEST-U5   hit   规则在含 U5（ESP32-S3-WROOM-1）的最小网表上触发了
    ✓ HARVEST-J3   hit   规则在含 J3（FPC0.52H-WS-24P）的最小网表上触发了
  命中 2 条，unknown 0 条，**没有一条被标成 pass**
  exit=0
```

**这一步抓到了两个真 bug**（细节见 `docs/goal-four-workstreams.md`）：
1. harvest 发的 `part_forbidden` 谓词用了 `"patterns"`，而引擎读 **`"parts"`**
   —— 两条候选即使被采纳也**永远不会触发**。第一版回放结果是 `unknown 2 条`。
2. 回放造最小网表时型号要放 `otherProperty["Manufacturer Part"]`，那才是引擎字段。

---

## 回归基线（本轮结束）

```
pytest        （见本轮最后一次全量运行）
go test ./... 17 包无 FAIL
connector     npm test → tests 1240 / pass 1240 / fail 0
布局单测      124 passed, 2 skipped
layout verify 14 项全 PASS
发布          inspect-bundle verdict: "ok", corrupt: []（1.3.80，源 commit 8c606a5b）
```

**已知滞后**：1.3.80 的包构建自 commit `8c606a5b`，**早于本轮 A①/B③/E③ 的改动**。
发版前需要重新构建一次包。**这是 NOT DONE，不是已完成。**
