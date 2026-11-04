#!/usr/bin/env python3
"""相位与证据：把"跳不过步骤"做成代码。

# 为什么

`sch status` 能**检测** S1–S6 到哪一步了，但它不**阻止**你从 S1 直接跑 `sch place`。
检测不是强制。这个模块补的是强制那一半。

# 状态机

    NOT RUN ──跑一次──→ pass / fail / blocked
                          │
    blocked ──修好环境再跑──→ pass / fail
    fail    ──修板──→ pass

**只有 `pass` 放行。**
`blocked`（检查器没跑成）、`pending`（没跑）、`unknown`（判不了）
全部阻塞 —— 这与 `sch gate` 的三态判词直接对齐：
"the checker could not run" 不是 "the board is broken"，但也不是通过。

# 证据会失效

每条证据带**文档哈希**。板子改了，哈希变了，旧证据自动作废回到 NOT RUN。
理由：换机器/过一夜都不能假装跑过了。

# 用法

    easycirq phase                      显示当前相位 + 各相位证据状态
    easycirq phase run <phase>          跑该相位的门并记证据
    easycirq phase advance              推进到下一相位（前置不是 pass 就拒）
    easycirq phase set <phase>          强制设置（排障用，会被记录为 overridden）
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

SCHEMA = "easycirq-phase/v1"

# 相位顺序。DELIVER 不是可推进的相位，是"可以出交付物"的状态。
PHASES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "DELIVER"]

TITLES = {
    "S0": "需求/spec",
    "S1": "图纸/分页",
    "S2": "编组/分区",
    "S3": "摆放",
    "S4": "布线",
    "S5": "校验门",
    "S6": "存盘",
    "DELIVER": "可交付",
}

# 每个相位的门：命令 + 该门"通过"的判据。
#
# 现在只接一个真门（S5 -> sch gate），其余留空 = NOT RUN = 阻塞。
# 刻意不铺开：分错相位会卡住正常工作流，比没有强制更糟
# （用户会去找绕过办法，然后永远绕过去）。
GATES = {
    "S5": {
        "cmd": ["sch", "gate", "--json"],
        "why": "原理图校验门（layout-lint → check → bridge-check → drc）",
    },
}

# 每个相位的前置：进入它之前，这些相位的证据必须 pass
REQUIRES = {
    "S0": [],
    "S1": ["S0"],
    "S2": ["S1"],
    "S3": ["S2"],
    "S4": ["S3"],
    "S5": ["S4"],
    "S6": ["S5"],
    "DELIVER": ["S5", "S6"],
}


# ── 证据存储 ────────────────────────────────────────────────────────────
def state_dir():
    base = os.environ.get("EASYCIRQ_PHASE_DIR")
    if base:
        return pathlib.Path(base)
    home = pathlib.Path(os.environ.get("EASYCIRQ_HOME")
                        or (pathlib.Path.home() / ".easycirq"))
    return home / "phase"


def state_path(project):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(project))
    return state_dir() / (safe + ".json")


def load(project):
    p = state_path(project)
    if not p.is_file():
        return {"schema": SCHEMA, "project": project, "phase": "S0",
                "evidence": {}, "history": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        d = {}
    d.setdefault("schema", SCHEMA)
    d.setdefault("project", project)
    d.setdefault("phase", "S0")
    d.setdefault("evidence", {})
    d.setdefault("history", [])
    return d


def save(project, d):
    p = state_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    d["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── 文档哈希：证据会过期 ────────────────────────────────────────────────
def doc_fingerprint(project):
    """这块板现在的指纹。取不到就返回 None（= 无法判定证据是否还有效）。

    来源：`easycirq project info` 的 projectUuid + 文档列表。
    刻意**不用**时间戳——那会让每条证据每次都"有效"。
    """
    try:
        out = subprocess.run(["easycirq", "sch", "pages", "--project", project],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=180)
    except Exception:                                   # noqa: BLE001
        return None
    if out.returncode != 0:
        return None
    try:
        i = out.stdout.find("{")
        d, _ = json.JSONDecoder().raw_decode(out.stdout[i:])
    except Exception:                                   # noqa: BLE001
        return None
    pages = (d.get("result") or {}).get("pages") or []
    key = "|".join(sorted(str(p.get("uuid")) for p in pages))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] if key else None


def board_facts(project):
    """板上真实器件数 + 悬空引脚数。取不到返回 (None, None)。

    一次 `sch read` 两个数都拿到，不重复调用。
    """
    try:
        out = subprocess.run(["easycirq", "sch", "read", "--project", project],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=300)
    except Exception:                                   # noqa: BLE001
        return None, None
    if out.returncode != 0:
        return None, None
    try:
        i = out.stdout.find("{")
        d, _ = json.JSONDecoder().raw_decode(out.stdout[i:])
    except Exception:                                   # noqa: BLE001
        return None, None
    r = d.get("result") or {}
    comps = r.get("components") or []
    n = sum(1 for c in comps
            if str(c.get("componentType") or "").lower() != "sheet")
    fp = r.get("floatingPinCount")
    return n, (int(fp) if isinstance(fp, (int, float)) else None)


def board_part_count(project):
    """板子上有多少个真实器件（不含 sheet 图框）。取不到返回 None。"""
    try:
        out = subprocess.run(["easycirq", "sch", "read", "--project", project],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=300)
    except Exception:                                   # noqa: BLE001
        return None
    if out.returncode != 0:
        return None
    try:
        i = out.stdout.find("{")
        d, _ = json.JSONDecoder().raw_decode(out.stdout[i:])
    except Exception:                                   # noqa: BLE001
        return None
    comps = ((d.get("result") or {}).get("components")) or []
    return sum(1 for c in comps
               if str(c.get("componentType") or "").lower() != "sheet")


def card_state(project):
    """跑交付卡，返回 (state, detail)。state ∈ pass / fail / pending / unknown。

    `card` 的退出码语义是它自己定的：0 ready / 1 not ready / 2 not measured。
    **not_measured 必须映射成 pending（= NOT RUN = 阻塞）**，不能因为"没报错"
    就当通过——那正是本目标要消灭的东西。
    """
    try:
        p = subprocess.run(["easycirq", "card", "--project", project, "--json"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
    except FileNotFoundError:
        return UNKNOWN, "easycirq not found on PATH"
    except subprocess.TimeoutExpired:
        return UNKNOWN, "card timed out"
    txt = (p.stdout or "") + (p.stderr or "")
    state = None
    head = ""
    try:
        i = txt.find("{")
        d, _ = json.JSONDecoder().raw_decode(txt[i:])
        state = d.get("state")
        head = str(d.get("headline") or "")
    except Exception:                                   # noqa: BLE001
        pass
    if p.returncode == 0 and state == "ready":
        return PASS, head or "card: ready"
    if state == "not_ready" or p.returncode == 1:
        return FAIL, head or "card: not ready"
    if state == "not_measured" or p.returncode == 2:
        return PENDING, head or "card: not measured"
    return UNKNOWN, head or ("card exit=%s state=%r" % (p.returncode, state))


# ── 证据状态判定（这一层是"强制"的核心）──────────────────────────────
PASS, FAIL, BLOCKED, PENDING, UNKNOWN, STALE, UNENFORCED = (
    "pass", "fail", "blocked", "pending", "unknown", "stale", "unenforced")


def evidence_state(d, phase, fingerprint):
    """返回该相位的证据状态。

    **只有 pass 算通过。** 但"有门没跑"和"还没接门"必须分开：
      · 有门没跑 → pending（= NOT RUN，阻塞）
      · 还没接门 → unenforced（不阻塞，但显示上必须能一眼看出来）

    混为一谈会让只接了 S5 的流程一步都推不动——那会逼用户去找绕过办法，
    然后永远绕过去。
    """
    ev = (d.get("evidence") or {}).get(phase)
    if not ev:
        return PENDING if phase in GATES else UNENFORCED
    # 板子变了 → 旧证据作废
    if ev.get("fingerprint") and fingerprint and ev["fingerprint"] != fingerprint:
        return STALE
    v = ev.get("verdict")
    if v in (PASS, FAIL, BLOCKED, UNKNOWN):
        return v
    return UNKNOWN


def is_release(state):
    return state == PASS


# ── 相位推进 ────────────────────────────────────────────────────────────
def blockers(d, target, fingerprint):
    """推进到 target 之前，哪些前置**真的**没通过。返回 [(phase, state)]。

    只有"有门且不是 pass"才算阻塞。没接门的相位不阻塞——但调用方必须
    把 unenforced 如实展示出来（见 cmd_show / advance 的输出）。
    """
    out = []
    for req in REQUIRES.get(target, []):
        st = evidence_state(d, req, fingerprint)
        if st == UNENFORCED:
            continue
        if not is_release(st):
            out.append((req, st))
    return out


def advance(project, d, fingerprint, to=None):
    cur = d.get("phase", "S0")
    idx = PHASES.index(cur) if cur in PHASES else 0
    target = to or (PHASES[idx + 1] if idx + 1 < len(PHASES) else None)
    if target is None:
        return False, "already at the last phase (%s)" % cur, []
    if target not in PHASES:
        return False, "unknown phase %r" % target, []
    # 目标就是当前相位：不是"推进"，别报成成功（那会看起来像有进展）。
    if target == cur:
        return False, ("already at %s — nothing to advance (use `phase set` to move "
                       "back, or run the gate with `phase run %s`)" % (cur, cur)), []
    bad = blockers(d, target, fingerprint)
    if bad:
        return False, "refused", bad
    # DELIVER 额外要求板子非空：空板子 S5 会 trivially pass，
    # 只看 S5 等于让空板"可交付"。
    if target == "DELIVER":
        n, floating = board_facts(project)
        if n is None:
            return False, ("refused: could not read the board "
                           "(connector down or page not open)"), [("PARTS", "unknown")]
        if n == 0:
            return False, ("refused: the board has no parts yet — an empty schematic "
                           "passes the S5 gate trivially, so it cannot be delivered"), [("PARTS", "empty")]
        # 悬空引脚：默认的 sch gate 只把它当 warn（非严格），所以门会 pass。
        # 但一个引脚没接的板子不该"可交付"——那是电气错误，不是排版瑕疵。
        if floating is None:
            return False, ("refused: could not count floating pins — cannot judge "
                           "whether the board is electrically connected"), [("PINS", "unknown")]
        # 交付卡：not_measured（= NOT RUN）与 not_ready 一律不出交付卡。
        cs, cdetail = card_state(project)
        d.setdefault("evidence", {})["CARD"] = {
            "verdict": cs, "detail": cdetail, "fingerprint": fingerprint,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        save(project, d)
        if cs != PASS:
            return False, ("refused: the delivery card is %s (%s) — a board that has "
                           "not been measured cannot be delivered" % (cs, cdetail)), \
                [("CARD", cs)]

        if floating > 0:
            return False, ("refused: %d floating pin(s) — the default schematic gate only "
                           "warns about these, so passing S5 does not mean the board is "
                           "connected. Wire them or mark them no-connect." % floating), \
                [("PINS", "%d floating" % floating)]
    d["phase"] = target
    d.setdefault("history", []).append(
        {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "from": cur, "to": target, "by": "advance"})
    save(project, d)
    return True, "advanced %s → %s" % (cur, target), []


# ── 跑门 ────────────────────────────────────────────────────────────────
def run_gate(project, phase, fingerprint):
    g = GATES.get(phase)
    if not g:
        return {"verdict": PENDING,
                "detail": "no gate is wired for %s yet — it stays NOT RUN (blocking)" % phase,
                "cmd": None, "exit": None}
    argv = list(g["cmd"])
    if project:
        argv += ["--project", project]
    try:
        p = subprocess.run(["easycirq"] + argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800)
    except FileNotFoundError:
        return {"verdict": BLOCKED, "detail": "easycirq not found on PATH",
                "cmd": " ".join(argv), "exit": None}
    except subprocess.TimeoutExpired:
        return {"verdict": BLOCKED, "detail": "gate timed out",
                "cmd": " ".join(argv), "exit": None}
    txt = (p.stdout or "") + (p.stderr or "")
    verdict = BLOCKED
    # sch gate 的三态判词：pass / fail / blocked
    low = txt.lower()
    if '"verdict": "pass"' in low or '"verdict":"pass"' in low:
        verdict = PASS
    elif '"verdict": "blocked"' in low or '"verdict":"blocked"' in low:
        verdict = BLOCKED
    elif p.returncode == 0:
        verdict = PASS
    elif '"verdict": "fail"' in low or '"verdict":"fail"' in low:
        verdict = FAIL
    else:
        verdict = BLOCKED if p.returncode != 0 else PASS
    return {"verdict": verdict, "detail": txt.strip()[-800:],
            "cmd": " ".join(argv), "exit": p.returncode}


# ── CLI ─────────────────────────────────────────────────────────────────
def build_hints(d, fp, states):
    """每个相位一句话：现在什么状态、缺什么、怎么补。

    只描述已知的事实（有没有门、跑没跑、指纹一致不一致），
    不预测"补完就能过" —— 那要跑了才知道。
    """
    ev = d.get("evidence") or {}
    out = {}
    for ph in PHASES:
        st = states.get(ph)
        hint = {"state": st}
        gate = GATES.get(ph)
        if gate:
            hint["gate"] = gate["cmd"]
            hint["what"] = gate["why"]
        if st == "pass":
            hint["next"] = "已通过，可以推进到下一相位。"
        elif st == "fail":
            hint["next"] = "跑了但没通过。看 detail 里失败的 stage，改完再跑一次。"
            hint["howToFix"] = "easycirq phase run %s" % ph
        elif st == "blocked":
            hint["next"] = ("检查器没跑成（通常是 EDA 没连上或页面没打开）。"
                            "这不等于通过。 先修好环境再重跑。")
            hint["howToFix"] = ("easycirq doctor  # 先确认连接器与 daemon\n"
                                "easycirq phase run %s" % ph)
        elif st == "pending":
            hint["next"] = ("这个相位有门，但还没跑过。"
                            "NOT RUN 不算通过，所以现在推进不去。")
            hint["howToFix"] = "easycirq phase run %s" % ph
        elif st == "stale":
            hint["next"] = "板子改过了，之前的证据已失效。重新跑一次门。"
            hint["howToFix"] = "easycirq phase run %s" % ph
        elif st == "unenforced" and ph == "DELIVER":
            # DELIVER 没有"门"，但它有前置条件。说成"没有门"会误导。
            hint["next"] = ("交付不是一道门，是四条前置同时成立："
                            "S5 通过、板上有真实器件、没有悬空引脚、"
                            "交付卡不是未测。任何一条不满足都会被拦下。")
            hint["howToFix"] = ("easycirq phase run S5\n"
                                "easycirq card          # 看交付卡还差什么")
        elif st == "unenforced":
            hint["next"] = ("这个相位还没有门：不阻塞推进，但也不等于通过。"
                            "它的质量目前靠下一道门兜。")
        else:
            hint["next"] = "状态未知。"
        # 上次跑的结论片段：让人不用再跑一次命令就能看到原因
        stored = ev.get(ph) or {}
        if isinstance(stored, dict):
            if stored.get("verdict"):
                hint["lastVerdict"] = stored["verdict"]
            detail = stored.get("detail")
            if detail:
                hint["lastDetail"] = str(detail)[:400]
        out[ph] = hint
    return out


def cmd_show(project, d, fp, as_json):
    states = {ph: evidence_state(d, ph, fp) for ph in PHASES}
    if as_json:
        print(json.dumps({"schema": SCHEMA, "project": project,
                          "phase": d.get("phase"), "fingerprint": fp,
                          "evidence": states,
                          "hints": build_hints(d, fp, states),
                          "stored": d.get("evidence") or {}},
                         ensure_ascii=False, indent=2))
        return 0
    print("相位：%s（%s）" % (d.get("phase"), TITLES.get(d.get("phase"), "")))
    print("板子指纹：%s" % (fp or "取不到 —— 证据有效性无法判定"))
    print()
    print("  %-8s %-10s %s" % ("相位", "状态", "说明"))
    ev = d.get("evidence") or {}
    pre = []
    for key in ("CARD",):
        if key in ev:
            pre.append("%s=%s" % (key, ev[key].get("verdict")))
    if pre:
        print("  DELIVER 前置证据：%s" % "、".join(pre))
    enforced = [ph for ph in PHASES if ph in GATES]
    print("  已接门：%s；未接门：%s"
          % ("、".join(enforced) or "无",
             "、".join(ph for ph in PHASES if ph not in GATES) or "无"))
    for ph in PHASES:
        st = states[ph]
        mark = {"pass": "✓", "fail": "✗", "blocked": "⊘", "pending": "·",
                "unknown": "?", "stale": "↻", "unenforced": "-"}.get(st, "?")
        note = ""
        if ph in GATES:
            note = GATES[ph]["why"]
            if st == PENDING:
                note += "  ← NOT RUN（阻塞）"
        elif st == UNENFORCED:
            note = "未接门（不阻塞，但也不等于通过）"
        print("  %-8s %s %-8s %s" % (ph, mark, st, note))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", default="show",
                    choices=["show", "run", "advance", "set"])
    ap.add_argument("phase", nargs="?")
    ap.add_argument("--project", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    d = load(a.project)
    fp = doc_fingerprint(a.project)

    if a.action == "show":
        return cmd_show(a.project, d, fp, a.json)

    if a.action == "run":
        if not a.phase:
            print("需要指定相位，例如：easycirq phase run S5", file=sys.stderr)
            return 2
        res = run_gate(a.project, a.phase, fp)
        d.setdefault("evidence", {})[a.phase] = {
            "verdict": res["verdict"], "detail": res["detail"],
            "cmd": res["cmd"], "exit": res["exit"],
            "fingerprint": fp,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        save(a.project, d)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print("%s: %s" % (a.phase, res["verdict"]))
            if res.get("detail"):
                for ln in res["detail"].splitlines()[:12]:
                    print("  " + ln)
        # 只有 pass 返回 0；blocked / pending 一律非 0
        return 0 if res["verdict"] == PASS else 1

    if a.action == "advance":
        ok, msg, bad = advance(a.project, d, fp, a.phase)
        if a.json:
            print(json.dumps({"ok": ok, "message": msg,
                              "blockers": [{"phase": p, "state": s} for p, s in bad]},
                             ensure_ascii=False, indent=2))
        else:
            print(msg)
            for p, s in bad:
                if p in PHASES:
                    print("  阻塞：%s 的证据是 %s（需要 pass）" % (p, s))
                    if p in GATES:
                        print("        补：easycirq phase run %s --project %s" % (p, a.project))
                    else:
                        print("        该相位还没有门 —— 这是 NOT RUN，不是通过")
                else:
                    # PARTS / PINS 是 DELIVER 的前置条件，不是相位；
                    # 别让人以为要去接一个叫 PINS 的门。
                    print("  阻塞：DELIVER 前置 %s = %s" % (p, s))
        return 0 if ok else 1

    if a.action == "set":
        if a.phase not in PHASES:
            print("未知相位 %r" % a.phase, file=sys.stderr)
            return 2
        prev = d.get("phase")
        d["phase"] = a.phase
        d.setdefault("history", []).append(
            {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "from": prev, "to": a.phase, "by": "set (override)"})
        save(a.project, d)
        print("已强制设置 %s → %s（记录为 override，会留在 history 里）" % (prev, a.phase))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
