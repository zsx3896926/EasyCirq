import pathlib

p = pathlib.Path("easycirq/scripts/sch_offline_pipeline.py")
s = p.read_text(encoding="utf-8")

old = '''        bom = next((snap / name for name in ("bom.tsv", "bom.csv")
                    if (snap / name).is_file()), None)
        if bom is not None:
            bom_out = out / "bom-check.json"
            _run([HERE / "sch_bom_metrics.py", bom, "--out", bom_out, "--quiet"],
                 label="bom metrics", allow=(0, 1, 2))
            checks.append(("identity", bom_out))
            step("bom", True, str(bom_out.name))'''

new = '''        bom = next((snap / name for name in ("bom.tsv", "bom.csv")
                    if (snap / name).is_file()), None)
        if bom is not None:
            bom_out = out / "bom-check.json"
            _run([HERE / "sch_bom_metrics.py", bom, "--out", bom_out, "--quiet"],
                 label="bom metrics", allow=(0, 1, 2))
            checks.append(("identity", bom_out))
            step("bom", True, str(bom_out.name))

            # Schematic vs BOM: a BOM that stayed at an older revision ships the
            # wrong parts. On 2026-11-01 the delivered file was missing Q1 and R4 -
            # the transistor and its base resistor - while the card said ready.
            if listing.is_file():
                bom_match_out = out / "bom-match-check.json"
                _run([HERE / "sch_bom_match.py", "--schematic", listing,
                      "--bom", bom, "--json"],
                     label="schematic/bom match", allow=(0, 2),
                     stdout_to=bom_match_out)
                checks.append(("bom_match", bom_match_out))
                step("bom_match", True, str(bom_match_out.name))'''

print("found", s.count(old))
p.write_text(s.replace(old, new, 1), encoding="utf-8")
print("pipeline patched")
print("_run supports stdout_to:", "stdout_to" in s)
