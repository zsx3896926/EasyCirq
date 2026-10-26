"""One-off: map resistor/switch/module pin nets from the v3 Protel netlist."""
import re

raw = open('docs/evidence/f1-b-2026-10-22/v3-netlist.net', encoding='utf-8', errors='replace').read()

# Protel2 style: ( ... net-name ... component-pin pairs ) blocks; parse generically
blocks = re.findall(r'\((.*?)\)', raw, re.S)
interest = ('R101', 'R102', 'R103', 'R104', 'R105', 'SW101', 'SW102', 'U101', 'J101')
pin_net = {}
for b in blocks:
    lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
    if not lines:
        continue
    net = lines[0].split()[0] if lines[0].split() else ''
    for ln in lines[1:]:
        m = re.match(r'^("?)([A-Z]+\d+)\1-(\S+)$', ln.split()[0] if ln.split() else '')
        if m:
            pin_net[(m.group(2), m.group(3))] = net

for des in interest:
    rows = sorted((k[1], v) for k, v in pin_net.items() if k[0] == des)
    print(des, rows)
