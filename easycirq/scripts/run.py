#!/usr/bin/env python3
"""easycirq run —— harness 的循环。

# 它是什么

把「按顺序调门、拒绝跳步、把 NOT RUN 当阻塞」这三条**自动执行**的循环。
相位与证据的判定在 `phase.py`，这里只负责：

    while 还没到 DELIVER:
        把「当前相位 + 证据状态 + 本相位允许的动作」交给模型
        模型返回工具调用
        执行工具调用（**动作白名单在这一层，越界的直接拒绝**）
        该推进时先跑门，再问 phase 能不能 advance
        被拒 → 把拒绝理由喂回模型

# 为什么白名单在循环里，不在 daemon 里

daemon 级白名单要给 184 个动作逐个分类，分错会**卡住正常工作流**，比没有强制更糟。
而模型是从这里调动作的——**在这里过滤，效果一样，代价小得多，改错的代价也小**。
（daemon 级强制留到有真实任务数据之后再谈。）

# 为什么要有 --fake

没有 API key 的环境也要能验证**编排**是否正确。`--fake <script.json>`
用一个固定剧本替代模型，于是"模型想跳步会不会被拒""门没过能不能推进"
这些都能确定性测出来，不依赖任何外部服务。
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import phase as ph  # noqa: E402

# ── 相位 → 允许的动作前缀 ────────────────────────────────────────────────
#
# 刻意**从窄开始**：只放这个阶段真正需要的东西。窄了会挡住正常工作流，
# 所以每一条都是"这个阶段不做就进行不下去"的最小集合。
#
# 表里没有的相位 → 不放行任何业务动作（只能查状态/跑门/推进）。
ALLOWED = {
    "S1": ["sch pages", "sch read", "doc ls", "project info", "project create"],
    "S2": ["sch pages", "sch read", "sch list", "sch block-apply", "sch group",
           "blocks ls", "project info"],
    "S3": ["sch pages", "sch read", "sch list", "sch place", "sch modify",
           "sch autoplace-free", "lib search", "project info"],
    "S4": ["sch pages", "sch read", "sch list", "sch wire", "sch connect",
           "sch autoconnect", "sch netflag", "sch no-connect", "project info"],
    "S5": ["sch pages", "sch read", "sch list", "sch check", "sch bridge-check",
           "sch drc", "sch gate", "project info"],
    "S6": ["sch pages", "sch read", "sch save", "project info"],
    "S0": ["project info", "sch pages"],
}

# 任何相位都可以用的元动作（由 harness 自己实现，不走 CLI）
META_TOOLS = ["phase_status", "run_gate", "phase_advance", "finish"]


def allowed_for(phase_name):
    return ALLOWED.get(phase_name, []) + META_TOOLS


def is_allowed(phase_name, argv):
    """argv 是 easycirq 的参数列表，例如 ["sch", "place", "--x", "1"]。"""
    joined = " ".join(argv)
    for prefix in ALLOWED.get(phase_name, []):
        # 必须**按词边界**匹配：裸 startswith 会把 `sch placeX` 当成 `sch place`。
        if joined == prefix or joined.startswith(prefix + " "):
            return True
    return False


# ── 执行 ────────────────────────────────────────────────────────────────
def run_cli(argv, timeout=1800):
    try:
        p = subprocess.run(["easycirq"] + argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError:
        return {"exit": None, "out": "easycirq not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"exit": None, "out": "timeout"}
    return {"exit": p.returncode,
            "out": ((p.stdout or "") + (p.stderr or "")).strip()[-1500:]}


class Harness:
    def __init__(self, project, max_rounds=12, verbose=True, goal=""):
        self.project = project
        # goal 要进对话。只打印不传，等于模型不知道要干什么。
        self.goal = goal
        self.max_rounds = max_rounds
        self.verbose = verbose
        self.log = []
        self.rounds = 0

    def say(self, msg):
        if self.verbose:
            print(msg)
        self.log.append({"at": round(time.time(), 3), "msg": msg})

    def state(self):
        d = ph.load(self.project)
        fp = ph.doc_fingerprint(self.project)
        return d, fp, {p: ph.evidence_state(d, p, fp) for p in ph.PHASES}

    def status_blob(self):
        d, fp, states = self.state()
        blockers = ph.blockers(d, "DELIVER", fp)
        return {
            "phase": d.get("phase"),
            "fingerprint": fp,
            "evidence": states,
            "blockersForDeliver": [{"phase": p, "state": s} for p, s in blockers],
            "allowedActions": allowed_for(d.get("phase")),
        }

    # 工具：跑门
    def tool_run_gate(self, phase_name=None):
        d, fp, _ = self.state()
        target = phase_name or d.get("phase")
        res = ph.run_gate(self.project, target, fp)
        d, _, _ = self.state()
        d.setdefault("evidence", {})[target] = {
            "verdict": res["verdict"], "detail": res["detail"],
            "cmd": res["cmd"], "exit": res["exit"], "fingerprint": fp,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        ph.save(self.project, d)
        self.say("  [gate %s] → %s" % (target, res["verdict"]))
        return {"phase": target, "verdict": res["verdict"],
                "detail": (res.get("detail") or "")[:600]}

    # 工具：推进
    def tool_phase_advance(self, to=None):
        d, fp, _ = self.state()
        ok, msg, bad = ph.advance(self.project, d, fp, to)
        self.say("  [advance] %s" % ("OK " + msg if ok else "REFUSED " + msg))
        return {"ok": ok, "message": msg,
                "blockers": [{"phase": p, "state": s} for p, s in bad]}

    # 工具：通用 CLI（受相位白名单约束）
    def tool_cli(self, argv):
        d, _, _ = self.state()
        cur = d.get("phase")
        if not is_allowed(cur, argv):
            self.say("  [cli] REFUSED %r（相位 %s 不许）" % (" ".join(argv), cur))
            return {"refused": True, "phase": cur,
                    "reason": "action %r is not allowed in phase %s"
                              % (" ".join(argv), cur),
                    "allowedInThisPhase": allowed_for(cur)}
        self.say("  [cli] easycirq %s" % " ".join(argv))
        return run_cli(argv)

    # 执行一次工具调用
    def execute(self, name, args):
        if name == "phase_status":
            return self.status_blob()
        if name == "run_gate":
            return self.tool_run_gate(args.get("phase"))
        if name == "phase_advance":
            return self.tool_phase_advance(args.get("to"))
        if name == "finish":
            return {"finished": True, "summary": args.get("summary", "")}
        if name == "easycirq":
            return self.tool_cli(args.get("argv") or [])
        return {"error": "unknown tool %r" % name}

    def done(self):
        d, _, _ = self.state()
        return d.get("phase") == "DELIVER"


# ── 模型客户端 ──────────────────────────────────────────────────────────
SYSTEM = """你是 EasyCirq 的工程 Agent。你在一个**门已经写进代码**的流程里工作。

规则（不是建议，是流程本身）：
- 你只能在当前相位允许的动作范围内操作。越界的调用会被直接拒绝。
- 每个相位都有门。**门没 pass 就推进不了**——`phase_advance` 会明确拒绝并告诉你缺什么。
- `blocked`（检查器没跑成）不是通过；`pending`（有门没跑）也不是通过。
- 不要声称做过没做的事。判不了就说判不了。

先调 phase_status 看当前状态，再决定下一步。"""


def call_model(endpoint, api_key, model, messages, tools, timeout=180):
    """POST {endpoint}/chat/completions（OpenAI 兼容）。"""
    import urllib.error
    import urllib.request

    url = endpoint.rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "messages": messages,
                       "tools": tools, "tool_choice": "auto"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": "HTTP %s: %s" % (e.code, e.read()[:400].decode(
            "utf-8", "replace"))}
    except Exception as e:                              # noqa: BLE001
        return {"error": "%s: %s" % (type(e).__name__, e)}


def tool_schemas():
    return [
        {"type": "function", "function": {
            "name": "phase_status",
            "description": "读取当前相位、各相位证据状态、以及本相位允许的动作。先调这个。",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "run_gate",
            "description": "跑某个相位的门并记录证据。",
            "parameters": {"type": "object", "properties": {
                "phase": {"type": "string", "description": "例如 S5；省略则跑当前相位"}}}}},
        {"type": "function", "function": {
            "name": "phase_advance",
            "description": "推进到下一相位。前置证据不是 pass 会被拒绝并说明原因。",
            "parameters": {"type": "object", "properties": {
                "to": {"type": "string", "description": "目标相位；省略则下一相位"}}}}},
        {"type": "function", "function": {
            "name": "easycirq",
            "description": "执行一条 easycirq 命令（受当前相位白名单约束）。",
            "parameters": {"type": "object", "properties": {
                "argv": {"type": "array", "items": {"type": "string"},
                         "description": "参数数组，例如 [\"sch\",\"place\",\"--x\",\"100\"]"}},
                "required": ["argv"]}}},
        {"type": "function", "function": {
            "name": "finish",
            "description": "结束本次运行并说明做完了什么、还差什么。",
            "parameters": {"type": "object", "properties": {
                "summary": {"type": "string"}}}}},
    ]


# ── 假模型：没有 key 也要能验证编排 ──────────────────────────────────────
class FakeModel:
    """按剧本返回固定的工具调用序列。

    剧本格式：[[{"name": "phase_status", "args": {}}, ...], ...]
    每一轮取一条。用完就返回 finish。

    为什么需要它：没有 API key 的环境也要能验证**编排**对不对——
    "模型想跳步会不会被拒""门没过能不能推进"必须是确定性可测的。
    """

    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def next_calls(self):
        if self.i >= len(self.script):
            return [{"name": "finish", "args": {"summary": "script exhausted"}}]
        turn = self.script[self.i]
        self.i += 1
        return turn


# ── 主循环 ──────────────────────────────────────────────────────────────
def loop(harness, model_call, max_rounds, verbose=True):
    """model_call(messages) -> {"tool_calls": [{"name","args"}], "text": str}"""
    messages = [{"role": "system", "content": SYSTEM}]
    messages.append({"role": "user", "content":
                     "目标：%s\n\n工程：%s\n\n先调 phase_status 看当前相位与证据状态，"
                     "再逐步推进。做完调 finish。"
                     % (harness.goal or "（未给目标）", harness.project)})
    finished = False
    for r in range(max_rounds):
        harness.rounds = r + 1
        if harness.done():
            harness.say("已达到 DELIVER，停止。")
            finished = True
            break
        reply = model_call(messages)
        if reply.get("error"):
            harness.say("模型调用失败：%s" % reply["error"])
            return {"ok": False, "reason": "model error",
                    "detail": reply["error"], "rounds": harness.rounds}
        calls = reply.get("tool_calls") or []
        if not calls:
            harness.say("模型没有返回工具调用，停止。")
            break
        messages.append({"role": "assistant", "content": reply.get("text") or "",
                         "tool_calls": calls})
        for c in calls:
            name, args = c.get("name"), c.get("args") or {}
            res = harness.execute(name, args)
            messages.append({"role": "tool", "name": name,
                             "content": json.dumps(res, ensure_ascii=False)[:4000]})
            if name == "finish":
                finished = True
                break
        if finished:
            break
    return {"ok": harness.done(), "rounds": harness.rounds,
            "phase": harness.state()[0].get("phase"), "log": harness.log}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--goal", required=True, help="这次要做成什么（自然语言）")
    ap.add_argument("--project", required=True)
    ap.add_argument("--endpoint", default=os.environ.get("EASYCIRQ_LLM_ENDPOINT"),
                    help="OpenAI 兼容端点，例如 https://api.deepseek.com/v1")
    ap.add_argument("--api-key", default=os.environ.get("EASYCIRQ_LLM_KEY"))
    ap.add_argument("--model", default=os.environ.get("EASYCIRQ_LLM_MODEL",
                                                      "deepseek-chat"))
    ap.add_argument("--max-rounds", type=int, default=12)
    ap.add_argument("--fake", help="用剧本替代模型（测试编排用，不需要 key）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    h = Harness(a.project, max_rounds=a.max_rounds, verbose=not a.json,
                goal=a.goal)

    if a.fake:
        script = json.loads(pathlib.Path(a.fake).read_text(encoding="utf-8"))
        fake = FakeModel(script)

        def model_call(_messages):
            return {"tool_calls": fake.next_calls(), "text": ""}
    else:
        if not a.endpoint:
            print("没有模型端点：给 --endpoint 或设 EASYCIRQ_LLM_ENDPOINT。"
                  "\n没有 key 时可以用 --fake <剧本.json> 验证编排。",
                  file=sys.stderr)
            return 2

        def model_call(messages):
            raw = call_model(a.endpoint, a.api_key, a.model, messages,
                             tool_schemas())
            if raw.get("error"):
                return {"error": raw["error"]}
            try:
                msg = raw["choices"][0]["message"]
            except Exception:                           # noqa: BLE001
                return {"error": "unexpected response shape: %s"
                                 % json.dumps(raw, ensure_ascii=False)[:300]}
            calls = []
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:                       # noqa: BLE001
                    args = {}
                calls.append({"name": fn.get("name"), "args": args})
            return {"tool_calls": calls, "text": msg.get("content") or ""}

    h.say("goal: %s" % a.goal)
    res = loop(h, model_call, a.max_rounds, verbose=not a.json)
    if a.json:
        print(json.dumps({k: v for k, v in res.items() if k != "log"},
                         ensure_ascii=False, indent=2))
    else:
        print()
        print("结果：%s  相位=%s  轮次=%d"
              % ("到 DELIVER" if res["ok"] else "未到 DELIVER",
                 res.get("phase"), res.get("rounds")))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
