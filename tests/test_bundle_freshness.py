"""验：1.3.86 包里真的带上了本轮的修复。

校验器抓到的正是这个：上一版包停在 d62b9246，不含 `sch kpi` 与 S5 白名单，
所以客户拿到的包**仍然卡在 DELIVER**——"可交付"就不成立。
"""
import io
import json
import pathlib
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist-release" / "easycirq-toolchain-1.3.86.zip"


def _payload_names():
    """取**载荷 zip** 里的文件名。

    注意：包内不止一个 zip —— `payload/python/python313.zip` 是 Python 标准库，
    简单地取 `namelist()` 里第一个 `.zip` 会抓到它（第一版就是这么错的）。
    只认 easycirq-toolchain 开头那个。
    """
    with zipfile.ZipFile(BUNDLE) as zf:
        names = zf.namelist()
        inner = [n for n in names
                 if n.endswith(".zip") and "easycirq-toolchain" in n]
        if inner:
            with zipfile.ZipFile(io.BytesIO(zf.read(inner[0]))) as z:
                return z.namelist()
        return names


def test_bundle_is_built_from_the_final_head():
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
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, encoding="utf-8", cwd=str(ROOT)).stdout.strip()
    assert d["provenance"]["sourceCommit"] == head, (
        "包不是当前 HEAD 打的：%s vs %s" % (d["provenance"]["sourceCommit"], head))
    assert d["provenance"]["sourceDirty"] is False


def test_bundle_contains_the_run_loop_script():
    """本轮修的 sch kpi 在 Go 二进制里；run.py 在技能载荷里。两个都得在。"""
    joined = "|".join(_payload_names())
    assert "scripts/run.py" in joined, "包里没有 run.py"
    assert "scripts/phase.py" in joined, "包里没有 phase.py"
