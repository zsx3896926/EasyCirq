"""P5 自更新面板的验收。

两个硬约束必须同时成立：
  1. **A15 默认抓包零外连** —— 面板加载时不许联网，检查更新只能由人点击触发
  2. **面板不判定、不安装** —— 它只显示 `easycirq update --check --json` 的原样结果

第 2 条尤其重要：安装要替换正在运行的二进制、可能要 sudo、还要重启 daemon。
那不是"一按就好的网页按钮"该干的事。
"""
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"
HTML = ROOT / "runtime" / "internal" / "app" / "panel" / "index.html"

pytestmark = pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")


def test_snapshot_never_probes_the_network():
    """A15：面板的自动轮询里**不许**出现检查更新。

    这条是静态判据：`collectSnapshot` 里只允许那几个离线命令。
    一旦有人把 update 塞进快照，面板加载就会外连 —— 而用户没有点任何东西。
    """
    src = (ROOT / "runtime" / "internal" / "app" / "cmd_panel.go").read_text(encoding="utf-8")
    body = src[src.index("func collectSnapshot"):]
    body = body[:body.index("\n}")]
    assert "update" not in body.lower(), (
        "collectSnapshot 里出现了 update —— 面板加载时会自动外连，违反「默认抓包零外连」")
    # 快照只取这几样（顺序无关）
    for want in ('"phase", "show", "--json"', '"card", "--json"', '"status", "--json"'):
        assert want in body, "快照少了 %s" % want


def test_update_check_endpoint_rejects_get():
    """检查更新会联网，绝不能被 GET / 链接 / 预取触发。"""
    src = (ROOT / "runtime" / "internal" / "app" / "cmd_panel.go").read_text(encoding="utf-8")
    i = src.index("/api/update-check")
    seg = src[i:i + 800]
    assert "http.MethodPost" in seg, "检查更新端点没有限制 POST"
    assert "StatusMethodNotAllowed" in seg, "GET 应当返回 405"


def test_panel_never_installs_anything():
    """面板只检查、不安装：它不许调用 `update` 的安装路径。"""
    page = HTML.read_text(encoding="utf-8")
    # 前端不许把安装参数发出去
    assert "cli-only" not in page and "--force" not in page, "面板别碰安装参数"
    # 后端也不许：检查用的参数里必须带 --check
    go = (ROOT / "runtime" / "internal" / "app" / "cmd_panel_update.go").read_text(encoding="utf-8")
    assert '"--check"' in go, "后面跑的必须是 update --check"
    assert "easycirq update" in page, "要告诉用户真升级去终端跑什么"


def test_update_button_is_explicit_and_annotated():
    page = HTML.read_text(encoding="utf-8")
    assert 'id="actUpdateCheck"' in page, "没有检查更新按钮"
    assert "/api/update-check" in page, "按钮没接到后端"
    # 必须写明它是唯一会联网的按钮
    assert "唯一会联网" in page, "没说明它会联网 —— 用户无从知道这一下会外连"
    assert "不自动安装" in page or "不会自动安装" in page, "没说明它不会安装"
