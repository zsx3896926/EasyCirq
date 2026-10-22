"""One-off: print verify tail, snapshot return dict, APPLY_JS dispatch."""
import inspect
import re

src = open('design-hardware/scripts/eda_exec.py', encoding='utf-8').read()

i = src.find('def verify_against_snapshot')
tail = src[i:i + 14000]
j = tail.rfind('results.append')
print('=====VERIFY tail around last append=====')
print(tail[max(0, j - 2500):j + 900])

k = src.find("SNAPSHOT_JS = r'''")
seg = src[k:k + 9000]
m = seg.find('return {')
print('=====SNAPSHOT return=====')
print(seg[m:m + 1500])

a = src.find("APPLY_JS = r'''")
aseg = src[a:a + 14000]
for mm in re.finditer(r"action\.op === '([a-z_]+)'", aseg):
    print('apply op:', mm.group(1), 'at', mm.start())
n = aseg.find("results.push")
print('=====APPLY readback push=====')
print(aseg[max(0, n - 1500):n + 700])
