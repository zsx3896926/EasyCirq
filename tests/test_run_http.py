"""`easycirq run` 的**真实 HTTP 路径**测试。

`--fake` 绕过网络，所以它证明不了协议层。这里起一个真的 OpenAI 兼容服务端：

  · 真的监听端口、真的收 POST /v1/chat/completions
  · 校验 tools 有 5 个、Authorization 头带上了 key
  · 校验 messages 随轮次增长（工具结果回灌进了对话）
  · 校验工具调用的结果真的被执行（越界动作被拒）

它**不**验证模型聪不聪明——那需要真 key，本机没有。
"""
import json
import os
import pathlib
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"

TURNS = [
    [{"name": "phase_status", "args": {}}],
    [{"name": "easycirq", "args": {"argv": ["sch", "place", "--x", "1"]}}],
    [{"name": "phase_advance", "args": {}}],
    [{"name": "finish", "args": {"summary": "ok"}}],
]


def _serve(state):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            state["seen"].append({
                "path": self.path,
                "model": body.get("model"),
                "tools": len(body.get("tools") or []),
                "messages": len(body.get("messages") or []),
                "auth": (self.headers.get("Authorization") or "")[:14],
            })
            turn = TURNS[state["i"]] if state["i"] < len(TURNS) else []
            state["i"] += 1
            msg = {"role": "assistant", "content": ""}
            if turn:
                msg["tool_calls"] = [
                    {"id": "c%d_%d" % (state["i"], k), "type": "function",
                     "function": {"name": c["name"],
                                  "arguments": json.dumps(c["args"])}}
                    for k, c in enumerate(turn)]
            out = json.dumps({"choices": [{"index": 0, "message": msg}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


@pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")
def test_run_uses_the_real_http_path(tmp_path):
    state = {"i": 0, "seen": []}
    srv, port = _serve(state)
    try:
        env = {**os.environ, "EASYCIRQ_PHASE_DIR": str(tmp_path)}
        p = subprocess.run(
            [str(EXE), "run", "--goal", "http smoke", "--project", "http1",
             "--endpoint", "http://127.0.0.1:%d/v1" % port,
             "--model", "mock-model", "--api-key", "sk-test"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600, env=env)
    finally:
        srv.shutdown()

    out = (p.stdout or "") + (p.stderr or "")
    assert state["seen"], "服务端一个请求都没收到：HTTP 路径没走通\n" + out[-800:]

    seen = state["seen"][0]
    assert seen["path"].endswith("/v1/chat/completions"), seen
    assert seen["model"] == "mock-model", "model 没传过去"
    assert seen["tools"] == 5, "工具 schema 数量不对：%s" % seen["tools"]
    assert seen["auth"].startswith("Bearer sk-"), "key 没带上"

    # messages 随轮次增长 —— 说明工具结果真的回灌进了对话
    counts = [s["messages"] for s in state["seen"]]
    assert counts == sorted(counts) and counts[-1] > counts[0], counts

    # 越界动作被拒（这一条在 HTTP 路径上也要成立）
    assert "REFUSED" in out and "S0" in out, out[-600:]
