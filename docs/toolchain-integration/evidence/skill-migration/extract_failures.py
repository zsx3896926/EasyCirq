#!/usr/bin/env python3
"""Extract failing test blocks from an offline-suite log (migration evidence)."""
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
want = tuple(sys.argv[2:])
blocks = re.split(r'={70}', text)
for block in blocks:
    stripped = block.strip()
    if not stripped:
        continue
    first = stripped.splitlines()[0]
    if first.startswith(('FAIL:', 'ERROR:')) and (not want or any(w in first for w in want)):
        print(stripped[:1800])
        print('-' * 70)
