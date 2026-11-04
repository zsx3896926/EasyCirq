"""面板的验收判据（A1/A2/A5/A9/A10）。

这些测试都**真的起一个面板进程**再打它，不是读源码猜行为 ——
A2（只监听 loopback）这种判据，只有真起服务才能验。

不需要浏览器：判据落在 HTTP 响应和进程行为上。
渲染层（颜色/图标）由 parse 内置 HTML 里的状态映射来断言。
"""
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"
HTML = ROOT / "runtime" / "internal" / "app" / "panel" / "index.html"

pytestmark = pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")


def _free_port_range(start=24111, end=24130):
    """挑一段当前没被占的端口，避免和真 daemon 抢。"""
    for p in range(start, end):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            s.close()
    pytest.skip("找不到空闲端口")


@pytest.fixture()
def panel(tmp_path):
    port = _free_port_range()
    env = {**os.environ, "EASYCIRQ_PHASE_DIR": str(tmp_path / "phase")}
    proc = subprocess.Popen(
        [str(EXE), "panel", "--no-open", "--port", str(port), "--project", "demo"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", env=env)
    url = "http://127.0.0.1:%d" % port
    for _ in range(80):
        if proc.poll() is not None:
            out, err = proc.communicate()
            pytest.fail("面板起不来：\n%s\n%s" % (out, err))
        try:
            with urllib.request.urlopen(url + "/", timeout=1):
                break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("面板 8 秒内没起来")
    yield {"url": url, "port": port, "proc": proc, "env": env}
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=10)


def _get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.status, r.read()


# ── A1 起得来、打印确切 URL ──────────────────────────────────────────
def test_panel_serves_the_page(panel):
    status, body = _get(panel["url"] + "/")
    assert status == 200
    text = body.decode("utf-8")
    assert "EasyCirq" in text
    assert "相位与证据" in text


def test_panel_sends_a_restrictive_csp(panel):
    """CSP 默认只允许 self —— 面板不该往外面加载任何东西。"""
    with urllib.request.urlopen(panel["url"] + "/", timeout=10) as r:
        csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp, csp


# ── A2 只监听 127.0.0.1 ─────────────────────────────────────────────
def test_panel_listens_on_loopback_only(panel):
    """这条是安全判据：监听 0.0.0.0 意味着同网段的人都能看你的设计。"""
    port = panel["port"]
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60).stdout
    listening = [ln for ln in out.splitlines()
                 if (":%d" % port) in ln and "LISTEN" in ln.upper()]
    assert listening, "netstat 里找不到监听记录：\n" + out[:800]
    for ln in listening:
        assert "0.0.0.0:%d" % port not in ln, "面板监听在 0.0.0.0 上了：\n" + ln
        assert "127.0.0.1:%d" % port in ln, "监听地址不是 loopback：\n" + ln


def test_panel_is_not_reachable_on_a_non_loopback_address(panel):
    """从本机的非 loopback 地址连过去应该失败。"""
    port = panel["port"]
    try:
        target = socket.gethostbyname(socket.gethostname())
    except OSError:
        pytest.skip("拿不到本机非 loopback 地址")
    if target.startswith("127."):
        pytest.skip("本机解析出来就是 loopback")
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect((target, port))
        s.close()
        pytest.fail("面板在 %s:%d 上可达 —— 应该只监听 loopback" % (target, port))
    except (ConnectionRefusedError, socket.timeout, OSError):
        pass
    finally:
        s.close()


# ── A5 card exit=2 必须显示"还没检查过"，不是"通过" ──────────────────
def test_snapshot_carries_not_measured_instead_of_an_error(panel):
    """`card` 用退出码表达语义（0/1/2），exit 2 时**仍然输出完整 JSON**。

    早期实现把非零退出当失败丢弃 stdout，结果面板永远显示不出"还没检查过"，
    而这恰恰是这层界面最该说清的状态。
    """
    status, body = _get(panel["url"] + "/api/snapshot")
    assert status == 200
    snap = json.loads(body.decode("utf-8"))
    assert not snap.get("errors"), snap.get("errors")
    card = snap.get("card") or {}
    assert card.get("state") == "not_measured", card.get("state")
    assert "还没检查过" in (card.get("headline") or ""), card.get("headline")


def test_snapshot_passes_phase_evidence_through(panel):
    _, body = _get(panel["url"] + "/api/snapshot")
    snap = json.loads(body.decode("utf-8"))
    phase = snap.get("phase") or {}
    assert phase.get("phase"), "没拿到当前相位"
    assert isinstance(phase.get("evidence"), dict), phase.get("evidence")


# ── A9 杀掉面板不影响 CLI ────────────────────────────────────────────
def test_cli_still_works_after_the_panel_dies(panel):
    panel["proc"].kill()
    panel["proc"].wait(timeout=10)
    out = subprocess.run([str(EXE), "phase", "show", "--project", "demo", "--json"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=120, env=panel["env"])
    assert out.returncode == 0, out.stderr[-800:]
    assert '"schema"' in out.stdout or '"phase"' in out.stdout


# ── A10 装完就能用，没有构建步骤 ────────────────────────────────────
def test_page_is_embedded_never_read_from_disk(panel):
    """页面必须来自二进制里的 embed，不是安装目录里的静态文件。

    如果哪天有人把它改成读磁盘，安装包漏带一个文件就会白屏 ——
    而"装完就能用"是验收判据之一。
    """
    src = (ROOT / "runtime" / "internal" / "app" / "panel_embed.go").read_text(
        encoding="utf-8")
    assert "//go:embed panel/index.html" in src
    assert "var panelHTML" in src
    _, body = _get(panel["url"] + "/")
    assert len(body) > 5000, "页面太小，不像完整页面"


# ── 渲染层：五态映射必须齐，且 pending/stale 不能是"通过" ────────────
def test_state_mapping_covers_every_evidence_state():
    text = HTML.read_text(encoding="utf-8")
    for state in ("pass", "fail", "blocked", "pending", "stale", "unenforced"):
        assert state + ":" in text, "HTML 里缺状态映射：" + state


@pytest.mark.parametrize("state", ["pending", "blocked", "stale", "unenforced"])
def test_non_pass_states_never_borrow_the_pass_class(state):
    """`pending`/`blocked`/`stale` 永远不能渲染成 pass 的样子。

    这是整个产品最核心的一条：**没证据不许显示为通过。**
    直接解析 HTML 里的映射表，逐条比对 class。
    """
    text = HTML.read_text(encoding="utf-8")
    m = re.search(r'%s:\s*\{cls:"([^"]+)"' % state, text)
    assert m, "找不到 %s 的映射" % state
    assert m.group(1) != "pass", "%s 被映射到了 pass —— 绝对不能这样" % state
    assert m.group(1) == state, "%s 应该映射到自己的 class，实际 %s" % (state, m.group(1))


def test_every_state_shows_text_and_icon_not_only_colour():
    """状态必须"颜色+文字+图标"三件套：只给颜色，色盲用户就读不出来。"""
    text = HTML.read_text(encoding="utf-8")
    for state in ("pass", "fail", "blocked", "pending", "stale", "unenforced"):
        m = re.search(
            r'%s:\s*\{cls:"[^"]+",\s*ic:"([^"]+)",\s*txt:"([^"]+)"' % state,
            text)
        assert m, "%s 缺图标或文字" % state
        assert m.group(1).strip(), "%s 的图标是空的" % state
        assert m.group(2).strip(), "%s 的文字是空的" % state
