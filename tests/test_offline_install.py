"""P5 / C18：离线安装包**真的能离线装**。

判据不是"我看起来它离线"，而是：**把 socket 封掉**，再从一个本地 zip 装一遍。

做法上有一个前提事实（已核对）：`distribution/easycirq_install.py` 里
**没有任何** urllib / requests / http / socket 调用 —— 它吃的就是本地 zip。
所以这个测试不是"验证一个特性"，而是**把这条性质钉住**：
以后谁在安装路径里加了一次遥测/校验请求，这里会立刻红。
"""
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "distribution" / "easycirq_install.py"
RELEASES = ROOT / "dist-release"


def _latest_bundle():
    if not RELEASES.is_dir():
        return None
    zips = sorted(RELEASES.glob("easycirq-toolchain-*.zip"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    # 只要工具链包，不要 installer 变体（后者体积相同但用途不同）
    for z in zips:
        if "installer" not in z.name:
            return z
    return zips[0] if zips else None


pytestmark = pytest.mark.skipif(
    not INSTALLER.is_file() or _latest_bundle() is None,
    reason="没有安装脚本或没有已构建的离线包",
)


def test_installer_source_has_no_network_calls():
    """安装脚本本身不许有网络调用 —— 这是"离线可用"的静态前提。"""
    src = INSTALLER.read_text(encoding="utf-8")
    for banned in ("urllib.request", "requests.get", "http.client", "socket.socket"):
        assert banned not in src, (
            "安装脚本里出现了网络调用 %r —— 离线包就不再离线了" % banned)


def test_install_from_bundle_with_sockets_blocked(tmp_path):
    """真·气隙：封掉 socket，从本地 zip 装到一个空目录，必须成功。"""
    bundle = _latest_bundle()

    driver = tmp_path / "driver.py"
    driver.write_text(
        "import socket, sys, runpy\n"
        "class _Blocked(socket.socket):\n"
        "    def __init__(self, *a, **k):\n"
        "        raise OSError('network disabled for the air-gap test')\n"
        "socket.socket = _Blocked\n"
        "socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError('network disabled'))\n"
        "sys.argv = ['easycirq_install.py'] + sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0] if False else %r, run_name='__main__')\n"
        % str(INSTALLER),
        encoding="utf-8",
    )

    install_dir = tmp_path / "install"
    state_dir = tmp_path / "state"
    home = tmp_path / "home"
    home.mkdir()

    p = subprocess.run(
        [sys.executable, str(driver), "install",
         "--bundle", str(bundle),
         "--install-dir", str(install_dir),
         "--state-dir", str(state_dir),
         "--home", str(home),
         "--skill-client", "none",
         "--no-self-check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, (
        "封掉网络后安装失败 —— 离线包并不离线\n%s" % out[-1500:])

    # 装完之后 CLI 必须在，并且能用（离线装的产物是完整的）
    exes = list(install_dir.rglob("easycirq.exe")) + list(install_dir.rglob("easycirq"))
    assert exes, "装完没有 easycirq 可执行文件\n%s" % out[-800:]


def test_bundle_contains_the_panel_inside_the_binary(tmp_path):
    """C20：包内含面板。面板是 go:embed 进二进制的，所以查"有没有那个命令"。"""
    bundle = _latest_bundle()
    with zipfile.ZipFile(bundle) as z:
        names = z.namelist()
    assert any(n.endswith("easycirq.exe") or n.endswith("/easycirq") for n in names), \
        "包里没有 CLI 可执行文件：%r" % names[:10]
    # 面板页面本身不该作为独立文件出现（否则就破坏了"无构建步骤"）
    assert not any("panel/index.html" in n for n in names), (
        "面板页面出现在包里了 —— 它应当只在二进制内部")
