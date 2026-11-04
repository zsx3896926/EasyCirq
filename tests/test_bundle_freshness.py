"""守 1.3.86 包与仓库**内容一致**——而不是"HEAD 哈希相等"。

为什么要换判据：断言 `sourceCommit == HEAD` 会被之后任何一次提交自己绊倒，
包括只改文档的提交。而真正要保证的是**包里的代码就是仓库里的代码**。

所以逐文件比对：载荷里的 scripts/run.py、scripts/phase.py、
references/harness-run.md 必须与仓库当前字节完全相同。
"""
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist-release" / "easycirq-toolchain-1.3.86.zip"

# 发给客户的包里必须与仓库一致的文件
KEY_FILES = [
    "scripts/run.py",
    "scripts/phase.py",
    "scripts/sch_offline_pipeline.py",
    "references/harness-run.md",
    "references/phase-gate.md",
]


def _payload() -> dict:
    """返回 {载荷内相对路径: bytes}。

    注意包内不止一个 zip —— `payload/python/python313.zip` 是 Python 标准库，
    取 namelist() 里第一个 `.zip` 会抓到它（第一版就是这么错的）。
    """
    with zipfile.ZipFile(BUNDLE) as zf:
        names = zf.namelist()
        # toolchain 包本身是扁平的（payload/ 直接在顶层）；
        # 只有 installer 包才多套一层 zip。两种都支持。
        inner = [n for n in names
                 if n.endswith(".zip") and "easycirq-toolchain" in n]
        if inner:
            with zipfile.ZipFile(io.BytesIO(zf.read(inner[0]))) as z:
                return {n: z.read(n) for n in z.namelist()}
        return {n: zf.read(n) for n in names if not n.endswith("/")}


def _norm(b: bytes) -> bytes:
    """行尾归一：CRLF / CR → LF。只影响行尾，不动内容。"""
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

@pytest.mark.skipif(not BUNDLE.is_file(), reason="没有 1.3.86 包")
def test_payload_matches_the_repository_byte_for_byte():
    payload = _payload()
    prefix = "payload/skill/easycirq/"
    missing, differing = [], []
    for rel in KEY_FILES:
        name = prefix + rel
        repo = ROOT / "easycirq" / rel
        if name not in payload or not repo.is_file():
            missing.append(rel)
            continue
        # Windows 上 git 会把 LF 换成 CRLF，打包/读盘两侧可能一个 CRLF 一个 LF。
        # 那是行尾差异，不是内容差异——按行尾归一再比，否则这条测试只会
        # 一直在报"不一致"，而真正的内容漂移反而被淹没。
        got = _norm(payload[name])
        want = _norm(repo.read_bytes())
        if got != want:
            differing.append((rel,
                              hashlib.sha256(got).hexdigest()[:12],
                              hashlib.sha256(want).hexdigest()[:12]))
    assert not missing, "包里缺这些文件：%s" % missing
    assert not differing, ("包里的代码与仓库不一致（这是客户拿到的版本）：\n"
                           + "\n".join("  %s  包=%s 仓库=%s" % d for d in differing))


@pytest.mark.skipif(not BUNDLE.is_file(), reason="没有 1.3.86 包")
def test_bundle_verifies():
    out = subprocess.run([sys.executable, "distribution/easycirq_install.py",
                          "inspect-bundle", "--bundle", str(BUNDLE)],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=600, cwd=str(ROOT))
    txt = (out.stdout or "") + (out.stderr or "")
    i = txt.find("{")
    assert i >= 0, txt[-500:]
    d = json.loads(txt[i:])
    assert d["verdict"] == "ok", d
    assert d["corrupt"] == [], d
    assert d["provenance"]["sourceDirty"] is False


@pytest.mark.skipif(not BUNDLE.is_file(), reason="没有 1.3.86 包")
def test_bundle_ships_the_harness_entry_points():
    """`run` 与 `phase` 是这一版的关键，两个都得在载荷里。"""
    names = "|".join(_payload())
    assert "scripts/run.py" in names, "包里没有 harness 循环"
    assert "scripts/phase.py" in names, "包里没有相位机"
    assert any(n.endswith("bin/easycirq.exe") for n in _payload()), "包里没有运行时"
