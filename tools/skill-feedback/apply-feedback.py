#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply-feedback - apply the 2026-10-26 WAF harden edits to the two skills.

Unlike `git apply`, this works by ANCHOR SEARCH, so it survives line drift between
skill releases, and it is idempotent: a second run reports ALREADY APPLIED instead
of duplicating text. Target edits stay within the skill root; exact backup journals and locks are
stored in a sibling .skill-feedback-state directory.

Targets (relative to the skill root you pass in):
  easyeda-agent/SKILL.md
  easyeda-agent/references/environment-setup.md
  easyeda-agent/scripts/parts-select.py
  easyeda-agent/scripts/net-discipline-audit.py   (new file)
  design-hardware/SKILL.md

Usage:
  python apply-feedback.py --check  <skill-root>     # dry run, exit 1 if edits pending
  python apply-feedback.py --apply  <skill-root>
  python apply-feedback.py --revert <skill-root>
"""
import argparse
import os
import sys
import json
import hashlib
import base64
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- payloads

EA_SKILL_BULLET = (
    "- 网络纪律：只经 CLI → daemon → 页面连接器访问嘉立创服务。禁止对 `*.lceda.cn` / `*.jlcpcb.com` /\n"
    "  `*.szlcsc.com` 发起脚本直连 HTTP（PowerShell / curl / python / 页面 `fetch()` 探针都算）：平台 WAF 按\n"
    "  不通过伪造 UA、TLS 指纹或更换出口绕过拦截。\n"
    "  遇到 `418` 或明确拦截证据时按 [接口限流与 418](references/environment-setup.md) 停止相关服务请求并保守冷却至少 10 分钟，\n"
    "  冷却期间不探测重试；共享出口的并行 Agent 共用受阻记录，不批量重放。\n"
)
EA_SKILL_TABLE_ROW = "| 418 / “访问被拦截” / 器件库查询恒为空 | [环境配置](references/environment-setup.md) |\n"

EA_ENV_SECTION = """## 接口限流与 418（访问被拦截）

出现 418 或明确拦截页时，先读本地日志，停止相关服务请求；不要脚本直连接口或用页面 fetch 探测。
本次事件记录提示共享出口可能受影响，客服口径为默认十分钟；这不是所有 418 的固定规则，
TLS 指纹、最初触发源和重试延长封禁尚需平台证据，不能仅凭时间相关性确定。

1. 读取 Documents/LCEDA-Pro/logs/warn 的相关日志，记录时间、服务、症状；对外分享前脱敏。
2. 采用从最后一次相关拦截起至少十分钟的保守冷却；有可信 Retry-After 时遵循更长时间。
   同一出口的 Agent 共用受阻记录，冷却期间不试探；计时结束只代表允许恢复验证，不代表已解封。
3. lists undefined、查询空或超时均不能单独证明限流或型号不存在，结合同时段日志判为待确认。
4. 优先做离线计算、文档、已有快照检查。已有 UUID 不保证放置无需网络；放置、保存、回读也可能联网，
   先确认是否依赖受阻服务，不得把客户端通道当成免限流通道。
5. 冷却后仅经受支持客户端路径做一次受控验证；失败继续退避，不重放写入。超时写入先对账。
6. 仅使用经用户授权且有官方说明的接口；不得猜测私有 API、伪造指纹或绕过服务限制。

离线辅助审计：python scripts/net-discipline-audit.py scan <dir> --json；
python scripts/net-discipline-audit.py eda-log --log <path> --json。
扫描不是网络沙箱；缺日志/读取失败输出 unknown，不能解释为安全或解封。

"""

PS_NOTE_OLD = """    NOTE: this is the ONLY code path that talks to jlcpcb.com, and it never
    runs unless --online is passed (issue #177: no silent second network path
    besides the daemon)."""
PS_NOTE_NEW = """    DANGER: direct JLC API calls are disabled after an access-block incident.
    Use offline catalogue data or a supported client workflow. An inherited
    environment variable cannot authorize direct requests. No network is sent."""

PS_FN_OLD = """def jlc_search(keyword, n=20, library_type=None):
    import urllib.request  # imported here: offline default never loads the network stack
    payload = {'keyword': keyword, 'currentPage': 1, 'pageSize': n}"""

PS_FN_NEW = """JLC_DIRECT_GUARD = 'disabled'


def jlc_search(keyword, n=20, library_type=None):
    raise SystemExit('REFUSED: direct JLC API access is disabled. Use the offline '
                     'catalogue or a supported client workflow; no request was sent.')
    import urllib.request  # unreachable legacy body; retained to avoid unrelated edits
    payload = {'keyword': keyword, 'currentPage': 1, 'pageSize': n}"""

PS_MAIN_OLD = "if __name__ == '__main__':\n    sys.exit(main())\n"
PS_MAIN_NEW = (
    "if __name__ == '__main__':\n"
    "    # Windows consoles default to GBK; the check/cross output below raises\n"
    "    # UnicodeEncodeError and kills the run after a successful lookup.\n"
    "    for _stream in (sys.stdout, sys.stderr):\n"
    "        try:\n"
    "            _stream.reconfigure(encoding='utf-8', errors='replace')\n"
    "        except (AttributeError, ValueError):\n"
    "            pass\n"
    "    sys.exit(main())\n"
)

DH_ITEM = """
13. 查料走平台正常路径：不使用脚本直连未获官方支持的嘉立创服务接口，不用页面 fetch、伪造指纹或更换出口绕过拦截。
    遇到 418/拦截先读本地日志、停止相关请求，转离线工作；工具异常不代表型号不存在。
    按 [网络纪律与服务阻塞](references/network-discipline.md) 处理，共享出口的 Agent 协同退避。
"""

EA_DH_ANCHOR6 = "\n## 6. 后台计算与自动化"
EA_SKILL_ANCHOR_BULLET = "- 原始观测不可改写；"
EA_SKILL_ANCHOR_ROW = ("| 连接、升级或保存异常 | [环境配置](references/environment-setup.md)、"
                       "[Action 边界](references/actions.md) |\n")
EA_ENV_ANCHOR = "## 上下文与缓存"

# (relative path, kind, anchor, payload, idempotency marker)
EDITS = [
    ("easyeda-agent/SKILL.md", "insert_before", EA_SKILL_ANCHOR_BULLET,
     EA_SKILL_BULLET, "网络纪律：只经 CLI"),
    ("easyeda-agent/SKILL.md", "insert_after", EA_SKILL_ANCHOR_ROW,
     EA_SKILL_TABLE_ROW, "418 / “访问被拦截”"),
    ("easyeda-agent/references/environment-setup.md", "insert_before", EA_ENV_ANCHOR,
     EA_ENV_SECTION, "## 接口限流与 418（访问被拦截）"),
    ("easyeda-agent/scripts/parts-select.py", "replace", PS_NOTE_OLD,
     PS_NOTE_NEW, "DANGER: this is the ONLY code path"),
    ("easyeda-agent/scripts/parts-select.py", "replace", PS_FN_OLD,
     PS_FN_NEW, "JLC_DIRECT_GUARD"),
    ("easyeda-agent/scripts/parts-select.py", "replace", PS_MAIN_OLD,
     PS_MAIN_NEW, "reconfigure(encoding='utf-8'"),
    ("design-hardware/SKILL.md", "insert_before", EA_DH_ANCHOR6, DH_ITEM,
     "查料走平台正常路径"),
]
NEW_FILES = [("easyeda-agent/scripts/net-discipline-audit.py", "net-discipline-audit.py")]


STATE_NAME = '.feedback-state.json'

def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None

def target(root, rel):
    p = root / rel
    if not p.resolve().is_relative_to(root.resolve()) or any(x.is_symlink() or (hasattr(x, 'is_junction') and x.is_junction()) for x in [p, *p.parents] if x != root.parent):
        raise ValueError('symlink/junction or escaping target: ' + rel)
    return p

def snapshot(p):
    return p.read_bytes() if p.is_file() else None

def encode(data):
    return base64.b64encode(data).decode('ascii') if data is not None else None

def decode(data):
    return base64.b64decode(data, validate=True) if data is not None else None

def atomic(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.feedback-', dir=p.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name, p)
    finally:
        if os.path.exists(name): os.unlink(name)

def save_state(path, state):
    atomic(path, json.dumps(state, ensure_ascii=False, indent=2).encode('utf8'))

def plan(root):
    contents, originals = {}, {}
    for rel, kind, anchor, payload, marker in EDITS:
        if rel not in contents:
            raw = snapshot(target(root, rel))
            if raw is None: raise ValueError('missing target: ' + rel)
            originals[rel] = raw
            contents[rel] = raw.decode('utf-8').replace('\r\n', '\n')
        text = contents[rel]
        if payload in text:
            if text.count(payload) != 1: raise ValueError('duplicate payload: ' + rel)
            continue
        if marker in text: raise ValueError('partial/conflicting patch: ' + rel)
        if text.count(anchor) != 1: raise ValueError('anchor missing or ambiguous: ' + rel)
        if kind == 'replace': text = text.replace(anchor, payload, 1)
        elif kind == 'insert_before': text = text.replace(anchor, payload + anchor, 1)
        else: text = text.replace(anchor, anchor + payload, 1)
        contents[rel] = text
    result = []
    for rel, text in contents.items():
        before = originals[rel]
        if b'\r\n' in before: text = text.replace('\n', '\r\n')
        after = text.encode('utf8')
        if after != before: result.append({'path': rel, 'before': encode(before), 'after': encode(after)})
    sources = [('easyeda-agent/scripts/net-discipline-audit.py', Path(__file__).with_name('net-discipline-audit.py')),
               ('design-hardware/references/network-discipline.md', Path(__file__).resolve().parents[2] / 'design-hardware/references/network-discipline.md')]
    for rel, source in sources:
        desired = source.read_bytes().replace(b'\r\n', b'\n')
        current = snapshot(target(root, rel))
        if current is None: result.append({'path': rel, 'before': None, 'after': encode(desired)})
        elif current.replace(b'\r\n', b'\n') != desired: raise ValueError('unowned/conflicting existing file: ' + rel)
    return result

def validate_state(root, state):
    if state.get('schema') != 'skill-feedback/v2' or state.get('root') != str(root):
        raise ValueError('state schema/root mismatch')
    seen = set()
    allowed = {x[0] for x in EDITS} | {'easyeda-agent/scripts/net-discipline-audit.py', 'design-hardware/references/network-discipline.md'}
    for row in state['files']:
        if row['path'] not in allowed or row['path'] in seen: raise ValueError('invalid state path')
        seen.add(row['path']); target(root, row['path'])
        decode(row['before']); decode(row['after'])

def execute(root, state, state_path, reverse=False):
    # Validate ALL files before touching any. Recover accepts either saved endpoint.
    changes = []
    for row in state['files']:
        p = target(root, row['path']); current = snapshot(p)
        before, after = decode(row['before']), decode(row['after'])
        expected = before if not reverse else after
        desired = after if not reverse else before
        if state['phase'] in ('prepared', 'applying', 'reverting', 'recovering'):
            if current not in (before, after): raise ValueError('edited during interrupted transaction: ' + row['path'])
        elif current != expected: raise ValueError('target changed; refusing overwrite: ' + row['path'])
        changes.append((p, desired))
    state['phase'] = 'reverting' if reverse else 'applying'
    save_state(state_path, state)
    for p, desired in changes:
        if desired is None:
            if p.exists(): p.unlink()
        else: atomic(p, desired)
    state['phase'] = 'reverted' if reverse else 'applied'
    save_state(state_path, state)

def main():
    ap = argparse.ArgumentParser(description='Offline anchored patch with exact backup/recovery; never contacts EDA.')
    modes = ap.add_mutually_exclusive_group(required=True)
    for mode in ('check', 'apply', 'revert', 'recover'): modes.add_argument('--' + mode, action='store_true')
    ap.add_argument('root')
    args = ap.parse_args()
    root = Path(args.root).absolute()
    if root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()): raise ValueError('root cannot be a link')
    root = root.resolve()
    if not (root/'easyeda-agent').is_dir() or not (root/'design-hardware').is_dir(): raise ValueError('both skill directories are required')
    state_dir = root.parent / '.skill-feedback-state' / hashlib.sha256(str(root).encode()).hexdigest()[:16]
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / STATE_NAME
    lock = state_dir/'lock'
    try: fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError: raise ValueError('patch locked; inspect recorded PID before removing stale lock: ' + str(lock))
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        state = json.loads(state_path.read_text('utf8')) if state_path.exists() else None
        if state: validate_state(root, state)
        if args.revert or args.recover:
            if not state: raise ValueError('no owned backup; refusing revert/recovery')
            if state['phase'] == 'reverted': print('nothing to revert'); return 0
            execute(root, state, state_path, reverse=True)
            print('restored exact original bytes'); return 0
        if state and state['phase'] in ('prepared', 'applying', 'reverting', 'recovering'):
            raise ValueError('interrupted transaction; inspect and use --recover')
        if state and state['phase'] == 'applied':
            for row in state['files']:
                if snapshot(target(root, row['path'])) != decode(row['after']):
                    raise ValueError('applied file changed; cannot verify: ' + row['path'])
        changes = plan(root)
        if not changes:
            print('nothing to apply'); return 0
        print('%d file(s) pending' % len(changes))
        if args.check: return 1
        if state and state['phase'] != 'reverted': raise ValueError('existing ownership journal conflicts; inspect before reapplying')
        # Journal stores exact backups and candidate bytes before the first mutation.
        state = {'schema':'skill-feedback/v2', 'root':str(root), 'phase':'prepared', 'files':changes}
        execute(root, state, state_path)
        print('applied; backup: ' + str(state_path)); return 0
    finally:
        lock.unlink(missing_ok=True)

if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf8', errors='replace')
    try: sys.exit(main())
    except (ValueError, OSError, KeyError, UnicodeError) as exc:
        print('REFUSED: ' + str(exc), file=sys.stderr); sys.exit(2)
