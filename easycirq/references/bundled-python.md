"""自带 Python：客户不需要自己装解释器。

> 2026-11-04 起，发行包内含一个嵌入式 CPython。装完即用；PATH 上的解释器排在后面。

---

## 一、为什么

`easycirq enterprise *` 每条命令最终都要跑 Python，离线 19 项判据也是 Python。
但企业受控电脑通常**没有 Python**，装它要走 IT 审批、甚至组策略禁用。

**这是这套东西里唯一一条「装完却用不了」的失败**——比慢、比缺功能都难解释。

---

## 二、怎么工作

发行包里有 `payload/python/`（嵌入式 CPython，约 24 MB / 37 个文件），装完在
`<install>/python/`。runtime 找解释器的顺序：

```
0. $EASYCIRQ_PYTHON         显式覆盖；设了但不可用是硬错误，不静默回落
1. <install>/python/python.exe   自带解释器（默认走这条）
2. python3 → python → py -3      PATH 上的（兜底）
```

自带排在 PATH 之前有两个理由：**客户不用装**，以及**版本是我们测过的那个**。

关掉它：`EASYCIRQ_NO_BUNDLED_PYTHON=1`（排障和测试用）。

找不到时的报错会**指名自带位置**：

```
no Python 3 interpreter found (tried the bundled python, then: python3, python, py -3);
the toolchain ships one under <install>/python — if that directory is missing the install
is incomplete, otherwise install Python 3 and put it on PATH, or set EASYCIRQ_PYTHON
```

「安装不完整」和「你机器上没装」是两件不同的事，报错必须分开说。

---

## 三、实测（本次验收）

```
装到干净目录：963 个文件，python\python.exe 存在，bin\easycirq.exe 存在
把 PATH 上所有 python/python3/py 全部隐藏
  → easycirq enterprise check 正常出结论（exit=1，命中 3 条规则）
反证：加 EASYCIRQ_NO_BUNDLED_PYTHON=1
  → exit=1，报错指名 <install>/python 缺失
```

**反证是关键**：证明的正是自带解释器在起作用，而不是机器上碰巧还有别的 Python。

---

## 四、构建

```bash
# 1. 准备嵌入式解释器（约 12 MB 下载，解压后 24 MB）
python distribution/fetch_python.py

# 2. 打包
python distribution/build_release.py --toolchain-only --toolchain-version <ver> \
    --connector-build never --runtime-exe <path-to-easycirq.exe>
```

`fetch_python.py` 默认走清华镜像（本机实测 `files.pythonhosted.org` 不通、
GitHub release 大文件会被切断），官方源作回落，抓到后自检能否运行与版本。

**缓存不入库**：`distribution/.cache/` 已 gitignore。这是 24 MB 二进制，
仓库里只留 `fetch_python.py` 和 `toolchain.json` 里的版本与源。

**找不到就不许打包**：
```
RuntimeError: no embeddable Python to bundle. Pass --python-dir <dir>, or drop it in
<cache>, or pass --allow-missing-python to ship without one
```
静默跳过会造成「装完了用不了」，所以宁可构建失败。

---

## 五、两道防线

| 环节 | 防什么 |
|---|---|
| **打包时** | 没有解释器就报错；有了但跑不起来（架构不对/损坏）也报错 |
| **安装时** | 包声称自带 Python 却不在清单里 → 当场拒绝；`fileCount` 太小（包被截断）→ 拒绝 |
| **运行时** | 自带缺失时明确说「安装不完整」，不静默降级成「命令不存在」 |

---

## 六、踩过的坑

**python 曾经被塞进 skill 组件**，结果 `skill.version` 变成 `3.13.0`，
安装器记录成错误的 skill 版本。python 是**独立组件**（自己的 version / installPath /
fileCount），有测试钉住这一点。

**缓存目录曾经解析到仓库根**：`cacheDir` 是相对仓库根的，而我想让它落在
`distribution/` 下，两处 ROOT 定义不一致会静默挪位。现在统一为
`distribution/.cache/python-3.13.0-embed-amd64`。

---

## 七、没做的

- **没有为 macOS/Linux 打自带解释器**：Windows 是当前交付目标；另两个平台的
  嵌入式布局不同（`python/bin/python3`），解析器已支持该路径但**未在那些平台上实测**。
- **没有做 pip 依赖**：我们的脚本是纯标准库，嵌入式包够用。若将来要装第三方包，
  嵌入式发行版默认禁用 site-packages，需要改 `python313._pth`。
- **没有做多版本共存**：一个安装目录一个解释器。
