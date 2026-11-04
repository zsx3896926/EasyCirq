"""自带 Python 的守卫测试（安装期）。

守的是这一条失败：**包声称自带解释器、实际没带**。装完 enterprise 命令全废，
而安装过程一切正常——这是整套东西里最难解释的失败。

解析器优先用自带解释器（runtime/internal/app/python_bundled_test.go 覆盖），
这里覆盖**打包与安装**两端。
"""
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "distribution"


def _installer():
    spec = importlib.util.spec_from_file_location(
        "easycirq_install", DIST / "easycirq_install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest(**over):
    """造一份最小可用的 bundle manifest。

    schema 与兼容矩阵必须与安装器的常量一致，否则连"最小可用"都算不上。
    """
    ins = _installer()
    files = {
        "payload/bin/easycirq.exe": "a" * 64,
        "payload/connector/x.eext": "b" * 64,
        "payload/skill/easycirq/SKILL.md": "c" * 64,
    }
    m = {
        "schema": ins.BUNDLE_SCHEMA,
        "name": "easycirq-toolchain",
        "version": "1.3.80",
        "compat": {"cli": "1.3.80", "runtime": "1.3.80", "daemon": "1.3.80",
                   "connector": "1.0.22", "protocol": "easycirq-agent/v1",
                   "eda": ">=3.2.0",
                   **({"minPython": "3.10"} if False else {})},
        "components": {
            "runtime": {"version": "1.3.80", "path": "payload/bin/easycirq.exe"},
            "connector": {"version": "1.0.22", "path": "payload/connector/x.eext"},
            "skill": {"version": "1.1.0", "path": "payload/skill/easycirq"},
        },
        "files": files,
    }
    m.update(over)
    return m


def test_bundle_without_python_still_validates():
    """没声明自带 Python 的老包必须继续可用（向后兼容）。"""
    ins = _installer()
    ins.validate_bundle(_manifest())


def test_declared_python_must_be_in_the_inventory():
    """声明了自带 Python 却不在清单里 -> 安装必须当场拒绝。"""
    ins = _installer()
    m = _manifest()
    m["components"]["python"] = {"version": "3.13.0", "path": "payload/python",
                                 "fileCount": 37}
    try:
        ins.validate_bundle(m)
    except Exception as exc:                            # noqa: BLE001
        assert "not in the file inventory" in str(exc), exc
        return
    raise AssertionError("声称自带 Python 却没带，安装竟然通过了")


def test_declared_python_with_too_few_files_is_rejected():
    """fileCount 太小说明包被截断 -> 拒绝。"""
    ins = _installer()
    m = _manifest()
    m["files"]["payload/python/python.exe"] = "d" * 64
    m["components"]["python"] = {"version": "3.13.0", "path": "payload/python",
                                 "fileCount": 3}
    try:
        ins.validate_bundle(m)
    except Exception as exc:                            # noqa: BLE001
        assert "fileCount" in str(exc) or "truncated" in str(exc), exc
        return
    raise AssertionError("fileCount 只有 3 竟然通过了")


def test_declared_python_with_sane_counts_validates():
    ins = _installer()
    m = _manifest()
    for i in range(12):
        m["files"]["payload/python/f%d.dll" % i] = "d" * 64
    m["files"]["payload/python/python.exe"] = "d" * 64
    m["components"]["python"] = {"version": "3.13.0", "path": "payload/python",
                                 "fileCount": 13}
    ins.validate_bundle(m)


def test_python_is_not_smuggled_into_the_skill_component():
    """python 必须是独立组件。

    曾经把 python 的 version 塞进 skill 组件，结果 skill.version 变成 3.13.0，
    安装器记录成错误的 skill 版本——这是真发生过的。
    """
    bundle = ROOT / "dist-release" / "easycirq-toolchain-installer-1.3.80.zip"
    inner = ROOT / "dist-release" / "easycirq-toolchain-1.3.80.zip"
    src = bundle if bundle.is_file() else inner
    if not src.is_file():
        import pytest
        pytest.skip("没有构建产物，跳过（构建见 distribution/build_release.py）")
    import io
    import zipfile
    with zipfile.ZipFile(src) as zf:
        zname = "bundle.json" if "bundle.json" in zf.namelist() else None
        if zname is None:
            inner_name = [n for n in zf.namelist() if n.endswith(".zip")][0]
            with zipfile.ZipFile(io.BytesIO(zf.read(inner_name))) as z2:
                m = json.loads(z2.read("bundle.json"))
        else:
            m = json.loads(zf.read(zname))
    skill = m["components"]["skill"]
    assert skill["version"] != m["components"].get("python", {}).get("version"), (
        "skill.version 与 python.version 相同，说明 python 又被塞进 skill 了")
    assert "payload/python" in (m["components"].get("python") or {}).get("path", "")


def test_runtime_resolver_prefers_bundled_over_path():
    """Go 侧的优先顺序由 Go 测试保证；这里只确认源码里确实在 PATH 阶梯之前。"""
    src = (ROOT / "runtime" / "internal" / "app" / "python.go").read_text(
        encoding="utf-8")
    i_bundled = src.find("if path, ok := r.resolveBundled(); ok {")
    i_ladder = src.find("tried := make([]string, 0, len(pythonCandidates))")
    assert i_bundled > 0 and i_ladder > 0, "找不到两处分支"
    assert i_bundled < i_ladder, "自带解释器必须在 PATH 阶梯之前"
