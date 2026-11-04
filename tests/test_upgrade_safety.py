"""升级安全性的结构性断言。

这一组测的不是"跑一次升级看库还在不在"（那需要一台装过旧版的机器），
而是**保证两个目录永远不重叠**这个不变量——只要它成立，升级就不可能碰到企业库。

依据：
- 运行时状态目录 = `~/.easycirq`（Go 侧 stateDir()）
- 安装目录 = `%LOCALAPPDATA%\\EasyCirq`（Python 侧 default_install_dir()）
- 安装器只替换 install_dir
"""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "distribution" / "easycirq_install.py"


def load_installer():
    """把安装器当模块加载，拿它的目录解析函数。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("easycirq_installer",
                                                  INSTALLER)
    if spec is None or spec.loader is None:
        pytest.skip("安装器无法加载")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not INSTALLER.is_file(), reason="安装器不存在")
def test_default_install_dir_is_not_the_state_dir():
    """安装目录和运行时状态目录必须是两个不同的地方。"""
    mod = load_installer()
    env = {k: v for k, v in os.environ.items()
           if k not in ("EASYCIRQ_INSTALL_DIR", "EASYCIRQ_STATE_DIR")}
    old = dict(os.environ)
    try:
        for k in ("EASYCIRQ_INSTALL_DIR", "EASYCIRQ_STATE_DIR"):
            os.environ.pop(k, None)
        install = pathlib.Path(mod.default_install_dir()).resolve()
    finally:
        os.environ.clear()
        os.environ.update(old)

    state = (pathlib.Path.home() / ".easycirq").resolve()
    assert install != state, "安装目录和状态目录重合，升级会清空企业库"
    # 不能有包含关系：谁包含谁都会出问题
    assert not str(install).startswith(str(state) + os.sep), \
        f"安装目录 {install} 在状态目录 {state} 里面"
    assert not str(state).startswith(str(install) + os.sep), \
        f"状态目录 {state} 在安装目录 {install} 里面——升级会清空它"


def test_default_knowledge_dir_is_outside_the_install_dir():
    """企业库默认位置必须在安装目录之外。"""
    sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
    import enterprise_rules

    env_backup = os.environ.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    try:
        dirs = enterprise_rules.layer_dirs()
    finally:
        if env_backup is not None:
            os.environ["EASYCIRQ_KNOWLEDGE_DIR"] = env_backup

    assert dirs, "layer_dirs() 不该为空"
    mod = load_installer()
    old = dict(os.environ)
    try:
        for k in ("EASYCIRQ_INSTALL_DIR", "EASYCIRQ_STATE_DIR"):
            os.environ.pop(k, None)
        install = pathlib.Path(mod.default_install_dir()).resolve()
    finally:
        os.environ.clear()
        os.environ.update(old)

    for layer, path in dirs:
        resolved = pathlib.Path(path).resolve()
        assert not str(resolved).startswith(str(install) + os.sep), (
            f"企业库默认位置 {resolved} 落在安装目录 {install} 里，"
            f"升级会把它清空")


def test_installer_only_replaces_the_install_dir():
    """安装器的删除动作只作用于 install_dir，不出现 HOME 或 .easycirq。

    这是源码级断言：只要安装器里没有删除 home / state 的代码，
    升级就动不到企业库。
    """
    src = INSTALLER.read_text(encoding="utf-8")
    for danger in ("_rmtree(home", "rmtree(Path.home()",
                   'rmtree(\'.easycirq', "rmtree(state_dir"):
        assert danger not in src, f"安装器出现危险删除：{danger}"
    # 状态目录只被读来放安装记录，不该被整体删除
    assert "_rmtree(install_dir)" in src or "rmtree(install_dir)" in src, \
        "没找到替换安装目录的动作，本测试的依据变了，需要重新核对"
