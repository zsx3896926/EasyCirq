import pathlib

p = pathlib.Path("easycirq/scripts/sch_status.py")
s = p.read_text(encoding="utf-8")

# 1. real leak: 回读 in the ready_to_write next step (the CLI was already fixed)
old1 = '"执行写入；写完保存、重开、回读，再跑一次检查"'
new1 = '"执行写入；写完保存、关掉重开，确认东西都还在，再跑一次检查"'
print("readback", s.count(old1))
s = s.replace(old1, new1)

# 2. real leak: the no-report next step points at a script and says 快照
old2 = '"先跑一轮离线检查（不是画图）：python scripts/sch_offline_pipeline.py --snapshot-dir <快照> --project <P> --page <P> --'
if old2 in s:
    start = s.find(old2)
    end = s.find('"', start + len(old2))
    whole = s[start:end + 1]
    print("offline-check hint length", len(whole))
    s = s.replace(whole, '"把你想做的板子说给 AI 听就行；画完并检查过之后，这里会告诉你还差什么"')

p.write_text(s, encoding="utf-8")
print("patched; remaining 回读:", s.count("回读"), "| 快照:", s.count("快照"))
