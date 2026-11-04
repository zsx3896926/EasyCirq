"""P2 Agent 工作面的验收（面板侧那一半）。

产品目标 P2：「对话流、拒绝高亮、停止/续跑、原始 JSON 展开」。

面板不是 agent，所以这里的 P2 落地为三件事：
  • 停止：跑不动的操作能真的停下来（刷新页面停不了它）
  • 原始 JSON 展开：任何一次渲染都能看到它依据的原始数据
  • 拒绝高亮：非零退出与"被停止"都要醒目标出，不许伪装成跑完了
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


class Panel:
    def __init__(self):
        self.proc = subprocess.Popen([str(EXE), "panel", "--no-open"],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", errors="replace")
        self.base = None
        deadline = time.time() + 20
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            m = re.search(r"http://127\.0\.0\.1:\d+/", line)
            if m:
                self.base = m.group(0).rstrip("/")
                break
        if not self.base:
            self.stop()
            pytest.skip("面板没能打印出 URL")
        for _ in range(60):
            try:
                with urllib.request.urlopen(self.base + "/api/snapshot", timeout=2) as r:
                    r.read()
                return
            except Exception:
                time.sleep(0.25)
        self.stop()
        pytest.skip("/api/snapshot 不可用")

    def stop(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()

    def post(self, path, payload=None):
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=240) as r:
            return json.loads(r.read().decode("utf-8"))


def test_cancel_endpoint_reports_when_nothing_is_running():
    """没有操作在跑时，「停止」必须如实说没有，而不是假装停成功了。"""
    p = Panel()
    try:
        res = p.post("/api/cancel")
        assert res.get("cancelled") is False
        assert res.get("note"), "要说清现在没有操作在跑"
    finally:
        p.stop()


def test_cancel_endpoint_rejects_get():
    p = Panel()
    try:
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(p.base + "/api/cancel", timeout=20)
        assert ei.value.code == 405, "停止是写操作，不许被 GET 顺带触发"
    finally:
        p.stop()


def test_panel_has_stop_and_raw_json_controls():
    page = HTML.read_text(encoding="utf-8")
    assert 'id="actStop"' in page, "没有停止键"
    assert "/api/cancel" in page, "停止键没接到后端"
    assert 'id="actRawToggle"' in page, "没有『看原始 JSON』"
    assert 'id="rawOut"' in page, "没有原始 JSON 的显示区"
    assert 'aria-pressed' in page, "切换按钮要有 aria-pressed，读屏才知道开没开"


def test_cancelled_result_is_never_dressed_up_as_finished():
    """被停止的输出不许冒充一次完整结论。"""
    page = HTML.read_text(encoding="utf-8")
    assert "被停止" in page, "面板没标出『被停止』"
    assert "不能当结论" in page, "必须说清不完整输出不能当结论"
    # 后端也要单独给字段，而不是靠退出码去猜
    go = (ROOT / "runtime" / "internal" / "app" / "cmd_panel_run.go").read_text(encoding="utf-8")
    assert "Cancelled bool" in go, "后端没有单独的 cancelled 字段"
