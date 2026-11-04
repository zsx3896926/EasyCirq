"""跨进程文件锁，给共享知识库用。

# 为什么需要

知识库放公司共享目录，**没有锁**。2026-11-03 写进 known-failures 的缺陷：

> 两个人同时 promote，后保存的把先保存的整条规则抹掉，且没有任何提示。

修它不能只靠加锁——`promote` 原本是**整文件覆盖**，即使串行执行，
第二个人也会把第一个人的规则冲掉。所以这里同时做两件事：

1. 本模块：短暂互斥，防止交错读改写
2. `review_ledger.promote`：按 id **合并**，不是覆盖

# 为什么不用 OS 文件锁

`flock` / `LockFileEx` 在 Windows UNC 路径上语义不统一，而且共享盘常见 SMB
实现差异。**用锁文件 + O_EXCL** 是唯一在各平台行为一致的做法：
创建成功就是拿到锁，创建失败就是别人持有。

# 残留锁怎么办

进程崩了会留下锁文件。所以锁文件里写 pid + 时间；超过 `stale_seconds`
视为残留，接管并**在结果里说明接管了**——静默接管等于把真冲突也吃掉。
"""
import json
import os
import pathlib
import socket
import time

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_STALE_SECONDS = 60.0


class LockTimeout(RuntimeError):
    """在超时内没拿到锁。调用方要把它当作「别人正在改」，不是内部错误。"""


def _lock_path(target):
    return pathlib.Path(str(target) + ".lock")


def _read_holder(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


class FileLock:
    """用锁文件实现的互斥。用法：

        with FileLock(path) as lock:
            ...读改写...
        lock.took_over_stale   # 是否接管了残留锁

    超时抛 LockTimeout，消息说清是谁持着。
    """

    def __init__(self, target, timeout=DEFAULT_TIMEOUT_SECONDS,
                 stale_seconds=DEFAULT_STALE_SECONDS):
        self.target = pathlib.Path(target)
        self.lock_file = _lock_path(self.target)
        self.timeout = timeout
        self.stale_seconds = stale_seconds
        self.took_over_stale = False
        self._fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def acquire(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        payload = json.dumps({
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }, ensure_ascii=False)

        while True:
            try:
                # O_EXCL：文件已存在就失败。这是拿到锁的唯一凭据。
                self._fd = os.open(str(self.lock_file),
                                   os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.write(self._fd, payload.encode("utf-8"))
                return
            except FileExistsError:
                pass

            # 有人持有。看是不是残留。
            if self._is_stale():
                self.took_over_stale = True
                try:
                    os.unlink(self.lock_file)
                except FileNotFoundError:
                    pass
                continue

            if time.monotonic() >= deadline:
                holder = _read_holder(self.lock_file)
                who = (f"{holder.get('host', '?')} 上的 pid {holder.get('pid', '?')}"
                       if holder else "另一个进程")
                raise LockTimeout(
                    f"{self.target.name} 正被 {who} 修改"
                    f"（锁文件 {self.lock_file}）。等一下再试；"
                    f"如果确认对方已经不在了，删掉那个锁文件即可")
            time.sleep(0.05)

    def _is_stale(self):
        try:
            age = time.time() - self.lock_file.stat().st_mtime
        except FileNotFoundError:
            return False  # 刚被别人释放了，直接重试
        return age > self.stale_seconds

    def release(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            os.unlink(self.lock_file)
        except FileNotFoundError:
            pass
