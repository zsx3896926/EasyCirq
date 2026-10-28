# Offline feedback migration v2

Run only while the target skills are idle. This repository owns design-hardware;
the easyeda-agent edits are an anchored migration, not an upstream release.
Copying this tool alone is insufficient: keep its repository-relative resources.

```
python tools/skill-feedback/apply-feedback.py --check <skill-root>
python tools/skill-feedback/apply-feedback.py --apply <skill-root>
python tools/skill-feedback/apply-feedback.py --check <skill-root>
```

The root must contain easyeda-agent/ and design-hardware/. Check returns 1 for
pending changes, 0 for a fully matching patch, 2 for conflict/unknown. Anchors must
be unique. Unknown existing files and partial patches are refused before writing.
No requests are made. Direct online selection remains disabled, including when
EASYEDA_ALLOW_DIRECT_JLC_API=1 is inherited.

Original bytes and candidate bytes are journaled under the root parent's
.skill-feedback-state/<root-id>/. Preserve this private backup; do not publish it.
Writes use atomic file replacement. A transaction is recoverable, not globally
atomic: a failure can leave some files changed until recovery.

```
python tools/skill-feedback/apply-feedback.py --recover <skill-root>
python tools/skill-feedback/apply-feedback.py --revert <skill-root>
```

Both restore exact original bytes; modified files block recovery rather than
being overwritten. Interrupted runs may leave a lock: inspect its recorded PID
and confirm no writer is running before removing that specific stale lock.
Do not run two patch writers or skill updates concurrently.

Audit is advisory, not a network sandbox. Python static calls are inspected;
other script types use conservative heuristics. Dynamic calls may be missed.
REVIEW/violations/cooling return 1, unreadable or unknown inputs return 2.
A cooldown estimate expiring does not prove the service recovered. Coordinate
one recovery attempt through a supported client using the shared incident record.

Do not publish original incident logs: they may contain account, project,
customer, IP and tracing identifiers. The patch contains no original evidence.
