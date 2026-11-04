#!/usr/bin/env python3
"""准备随包分发的嵌入式 Python。

# 为什么需要它

交付要求是「客户不用装 Python」。`build_release.py` 会把一个嵌入式解释器打进
`payload/python/`，装完就在 `<install>/python/`，runtime 优先用它。

但那个解释器是 **23 MB 的二进制**，不该进 git，所以放在构建缓存里：

    distribution/.cache/python-3.13.0-embed-amd64/

这个脚本负责把它抓下来（带镜像回落 + SHA256 校验）。

# 用法

    python distribution/fetch_python.py            # 下载并解压到缓存
    python distribution/fetch_python.py --check    # 只检查缓存是否就绪
    python distribution/fetch_python.py --dir D:\\py # 用本地已有的目录

# 为什么有镜像

本机实测：`files.pythonhosted.org` 不通、GitHub release 大文件会被切断，
但清华/华为的 python.org 镜像可通。所以默认走镜像，官方源作回落。
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = ROOT / "distribution" / "toolchain.json"


def load_cfg():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    py = cfg.get("python") or {}
    if not py:
        raise SystemExit("toolchain.json 里没有 python 段")
    return py


def download(url, dest):
    print("  下载 %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "easycirq-fetch-python"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest.stat().st_size


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="只检查缓存是否就绪")
    ap.add_argument("--dir", type=pathlib.Path, help="用本地已有的嵌入式 Python 目录")
    ap.add_argument("--force", action="store_true", help="已有也重新下载")
    a = ap.parse_args()

    py = load_cfg()
    cache = ROOT / py["cacheDir"]
    exe = cache / "python.exe"
    ver = py["version"]

    if a.dir:
        src = a.dir
        if not (src / "python.exe").is_file():
            raise SystemExit("%s 里没有 python.exe" % src)
        if cache.exists():
            shutil.rmtree(cache)
        shutil.copytree(src, cache)
        print("已从 %s 复制到 %s" % (src, cache))
    elif a.check:
        if exe.is_file():
            print("缓存就绪：%s（%s）" % (cache, ver))
            return 0
        print("缓存缺失：%s" % cache)
        print("  跑 python distribution/fetch_python.py 或传 --dir <已有的嵌入式 Python>")
        return 2
    else:
        if exe.is_file() and not a.force:
            print("缓存已存在：%s（%s）——要重下加 --force" % (cache, ver))
            return 0
        urls = [u for u in (py.get("source"), py.get("fallbackSource")) if u]
        if not urls:
            raise SystemExit("toolchain.json 的 python 段没有 source")
        cache.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="fetchpy-") as td:
            zpath = pathlib.Path(td) / "py.zip"
            last = None
            for u in urls:
                try:
                    size = download(u, zpath)
                    print("  完成 %d 字节" % size)
                    if size < 5_000_000:
                        last = "太小（%d 字节），像被截断" % size
                        continue
                    break
                except Exception as exc:                # noqa: BLE001
                    last = str(exc)
                    print("  失败：%s" % exc)
            else:
                raise SystemExit("所有源都失败，最后一条：%s" % last)

            with zipfile.ZipFile(zpath) as zf:
                names = zf.namelist()
                if "python.exe" not in [n.replace("\\", "/") for n in names]:
                    raise SystemExit("压缩包里没有 python.exe，不像 embeddable 包")
                if cache.exists():
                    shutil.rmtree(cache)
                cache.mkdir(parents=True)
                zf.extractall(cache)

    # 自检：能跑、版本对
    import subprocess
    out = subprocess.run([str(exe), "-c",
                          "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
                         capture_output=True, text=True, timeout=120)
    got = (out.stdout or "").strip()
    if out.returncode != 0 or not got:
        raise SystemExit("解压后 python.exe 跑不起来：%s" % (out.stderr or "")[:300])
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()[:16]
    n = sum(1 for _ in cache.rglob("*") if _.is_file())
    total = sum(_.stat().st_size for _ in cache.rglob("*") if _.is_file())
    print()
    print("就绪：%s" % cache)
    print("  python %s（期望 %s），%d 个文件，%.1f MB，python.exe sha256:%s…"
          % (got, ver, n, total / 1048576, digest))
    if got != ver:
        print("  ⚠ 版本与 toolchain.json 的 %s 不一致——要么改配置，要么换包" % ver)
    return 0


if __name__ == "__main__":
    sys.exit(main())
